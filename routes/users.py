"""Rotas de usuarios do sistema e perfis."""
from flask import jsonify, request
from flask_login import current_user

from app import (
    _get_setting,
    _set_setting,
    audit,
    clean_text,
    new_id,
    requires,
    validate_email,
)
from extensions import db
from models import PERFIL_PERMISSOES, SystemUser
from routes.blueprint import bp

@bp.route("/api/system-users", methods=["GET"])
@requires("Administrador")
def get_system_users(): return jsonify([u.to_dict() for u in db.session.execute(db.select(SystemUser)).scalars().all()])


@bp.route("/api/system-users", methods=["POST"])
@requires("Administrador")
def create_system_user():
    d = request.get_json() or {}
    username = clean_text(d.get("username"), 80)
    senha = d.get("senha") or ""
    if not username:
        return jsonify({"error":"Username obrigatório."}), 400
    if len(senha) < 8:
        return jsonify({"error":"Senha deve ter ao menos 8 caracteres."}), 400
    _perfis_validos = _get_setting("perfil_permissoes", PERFIL_PERMISSOES) or PERFIL_PERMISSOES
    if clean_text(d.get("perfil", "Visualizador")) not in _perfis_validos:
        return jsonify({"error":"Perfil inválido."}), 400
    if db.session.execute(db.select(SystemUser).filter_by(username=username)).scalar_one_or_none():
        return jsonify({"error":"Username já existe."}), 409
    err_email = validate_email(d.get("email"))
    if err_email:
        return jsonify({"error": err_email}), 400
    u = SystemUser(id=new_id("SU"), username=username, nome=clean_text(d.get("nome"), 120),
                   email=clean_text(d.get("email"), 120), perfil=clean_text(d.get("perfil","Visualizador"), 40),
                   status=clean_text(d.get("status","Ativo"), 20) or "Ativo")
    u.set_senha(senha)
    db.session.add(u); audit("CRIAR","system_users",u.id,f"Usuário {u.username} criado")
    db.session.commit(); return jsonify(u.to_dict()), 201


@bp.route("/api/system-users/<uid>", methods=["PUT"])
@requires("Administrador")
def update_system_user(uid):
    u = db.get_or_404(SystemUser, uid); d = request.get_json() or {}
    if "email" in d:
        err = validate_email(d.get("email"))
        if err:
            return jsonify({"error": err}), 400
    _perfis_validos = _get_setting("perfil_permissoes", PERFIL_PERMISSOES) or PERFIL_PERMISSOES
    if "perfil" in d and d["perfil"] not in _perfis_validos:
        return jsonify({"error":"Perfil inválido."}), 400
    for k,v in [("nome","nome"),("email","email"),("perfil","perfil"),("status","status")]:
        if k in d: setattr(u, v, d[k])
    if d.get("senha"): u.set_senha(d["senha"])
    audit("EDITAR","system_users",uid,f"Usuário {u.username} editado")
    db.session.commit(); return jsonify(u.to_dict())


@bp.route("/api/system-users/<uid>/toggle", methods=["POST"])
@requires("Administrador")
def toggle_system_user(uid):
    u = db.get_or_404(SystemUser, uid)
    if u.id == current_user.id: return jsonify({"error":"Não pode desativar a própria conta."}), 400
    u.status = "Inativo" if u.status == "Ativo" else "Ativo"
    db.session.commit(); return jsonify({"status":u.status})


@bp.route("/api/system-users/<uid>/reset-senha", methods=["POST"])
@requires("Administrador")
def reset_senha(uid):
    d = request.get_json() or {}; nova = d.get("senha","")
    if len(nova) < 8: return jsonify({"error":"Senha deve ter ao menos 8 caracteres."}), 400
    u = db.get_or_404(SystemUser, uid)
    u.set_senha(nova)
    audit("RESET_SENHA","system_users",uid,f"Senha de '{u.username}' redefinida")
    db.session.commit(); return jsonify({"ok":True})


@bp.route("/api/system-users/perfis")
@requires("Administrador")
def get_perfis():
    """Retorna perfis — do DB settings se customizados, senão do padrão."""
    custom = _get_setting("perfil_permissoes", None)
    return jsonify(custom if custom else PERFIL_PERMISSOES)


@bp.route("/api/system-users/perfis/<perfil>", methods=["PUT"])
@requires("Administrador")
def update_perfil_perms(perfil):
    d = request.get_json()
    current = _get_setting("perfil_permissoes", dict(PERFIL_PERMISSOES))
    current[perfil] = d
    _set_setting("perfil_permissoes", current)
    audit("EDITAR_PERMISSOES","system_users",perfil,f"Permissões do perfil '{perfil}' atualizadas")
    db.session.commit()
    return jsonify(current[perfil])
