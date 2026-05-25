"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

import shutil
import subprocess
import threading


APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run_update_command(args, timeout=30):
    try:
        result = subprocess.run(
            args,
            cwd=APP_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "Tempo limite excedido ao executar comando de atualização."
    except OSError as exc:
        return None, str(exc)
    return result, None


def _git_value(*args, timeout=10):
    result, error = _run_update_command(["git", *args], timeout=timeout)
    if error or result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _set_env_file_value(name, value):
    env_path = os.path.join(APP_ROOT, ".env")
    if not os.path.exists(env_path):
        return False
    with open(env_path, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    found = False
    updated = []
    for line in lines:
        if line.startswith(f"{name}="):
            updated.append(f"{name}={value}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"{name}={value}")
    with open(env_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(updated) + "\n")
    return True


def _app_version_from_file(default=None):
    version_path = os.path.join(APP_ROOT, "VERSION")
    try:
        with open(version_path, "r", encoding="utf-8") as fh:
            version = fh.read().strip()
            return version or default
    except OSError:
        return default


def _app_version_from_git_ref(ref, default=""):
    if not ref:
        return default
    version = _git_value("show", f"{ref}:VERSION")
    return version.strip() if version else default


def _self_update_enabled():
    return os.environ.get("SELF_UPDATE_ENABLED", "1") == "1"


def _schedule_self_restart():
    if os.environ.get("SELF_UPDATE_AUTO_RESTART", "1") != "1":
        return False

    def _restart():
        logger.warning("Reiniciando aplicação após atualização self-update")
        os._exit(0)

    threading.Timer(2.0, _restart).start()
    return True


def _system_update_status(fetch=False):
    git_path = shutil.which("git")
    has_repo = os.path.isdir(os.path.join(APP_ROOT, ".git"))
    enabled = _self_update_enabled()
    supported = bool(enabled and git_path and has_repo)
    current = app.config.get("BUILD_VERSION", "1.0.0")
    status = {
        "supported": supported,
        "enabled": enabled,
        "gitAvailable": bool(git_path),
        "repositoryAvailable": has_repo,
        "currentVersion": current,
        "availableVersion": "",
        "currentCommit": "",
        "branch": "",
        "remote": "",
        "dirty": False,
        "ahead": 0,
        "behind": 0,
        "updateAvailable": False,
        "canApply": supported,
        "mode": "git" if supported else "manual",
        "lastCheck": None,
        "message": "",
        "manualCommand": ".\\scripts\\update-windows.ps1 ou ./scripts/update-linux.sh",
    }
    if not enabled:
        status["message"] = "Atualização pela interface desativada por configuração do ambiente."
        return status
    if not supported:
        status["message"] = "Atualização manual pelo servidor. Esta instalação precisa ser reconstruída uma vez para ativar a atualização automática pela interface."
        return status

    status["currentCommit"] = _git_value("rev-parse", "--short", "HEAD")
    status["branch"] = _git_value("rev-parse", "--abbrev-ref", "HEAD")
    status["remote"] = _git_value("config", "--get", f"branch.{status['branch']}.remote") or "origin"
    status["dirty"] = bool(_git_value("status", "--porcelain"))

    if fetch:
        result, error = _run_update_command(["git", "fetch", "--prune", status["remote"]], timeout=120)
        status["lastCheck"] = datetime.now().isoformat()
        if error or result.returncode != 0:
            status["message"] = error or (result.stderr or result.stdout or "Falha ao verificar atualizações.").strip()
            return status

    upstream = _git_value("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if upstream:
        status["availableVersion"] = _app_version_from_git_ref(upstream, "")
        counts = _git_value("rev-list", "--left-right", "--count", f"HEAD...{upstream}")
        parts = counts.split()
        if len(parts) == 2 and all(p.isdigit() for p in parts):
            status["ahead"] = int(parts[0])
            status["behind"] = int(parts[1])
            status["updateAvailable"] = status["behind"] > 0
            status["message"] = "Atualização disponível." if status["updateAvailable"] else "Sistema já está na versão mais recente conhecida."
    else:
        status["message"] = "Branch atual não possui upstream configurado."
    return status

@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    cfg_email = _get_email_config()
    # Nunca retorna a senha ao frontend
    cfg_email_safe = {k: v for k, v in cfg_email.items() if k != "password"}
    cfg_email_safe["password_configurado"] = bool(cfg_email.get("password"))
    cfg_email_safe["via_env"] = cfg_email.get("source") == "env" and bool(os.environ.get("SMTP_PASSWORD"))
    cfg_email_safe["env_disponivel"] = bool(cfg_email.get("env_available"))
    return jsonify({
        "empresa":      _get_setting("empresa", {}),
        "setores":      _get_setting("setores", []),
        "unidades":     _get_setting("unidades", []),
        "alertas":      _get_setting("alertas", {}),
        "regras_usuario":_get_setting("regras_usuario", {}),
        "campos_ativo_obrigatorios": _get_setting("campos_ativo_obrigatorios", []),
        "categorias_config": _get_setting("categorias_config", {}),
        "categorias":         _get_setting("categorias", CATEGORIAS_DEFAULT),
        "categorias_insumos": _get_setting("categorias_insumos", CATEGORIAS_INSUMOS_DEFAULT),
        "categorias_compat":  _get_setting("categorias_compat", {}),
        "email":        cfg_email_safe,
        "email_templates": _get_email_templates(),
        "backup":       _get_backup_config(),
        "termo_recebimento": _get_setting("termo_recebimento", {}),
        "termo_devolucao":   _get_setting("termo_devolucao", {}),
        "aparencia":    _get_setting("aparencia", {}),
        "patrimonio_prefixo": _get_setting("patrimonio.prefixo", "TI"),
        "app_base_url": get_app_base_url(),
    })


@app.route("/api/settings", methods=["PUT"])
@requires("Administrador")
def update_settings():
    d = json_payload()
    if not d:
        return jsonify({"error": "Payload JSON obrigatório."}), 400
    unsupported = sorted(set(d) - set(SETTING_NORMALIZERS))
    if unsupported:
        return jsonify({"error": "Configuração não suportada.", "details": unsupported}), 400
    for key, val in d.items():
        normalized, error = SETTING_NORMALIZERS[key](val)
        if error:
            return jsonify({"error": error}), 400
        _set_setting(key, normalized)
    audit("EDITAR","configuracoes","","Configurações atualizadas")
    db.session.commit()
    return get_settings()


@app.route("/api/settings/setores", methods=["POST"])
@requires("Administrador")
def add_setor():
    nome = clean_text(json_payload().get("nome"), 80)
    if not nome: return jsonify({"error":"Nome obrigatório"}), 400
    setores = _clean_list_setting(_get_setting("setores", []), 80) or []
    if any(s.casefold() == nome.casefold() for s in setores):
        return jsonify({"error":"Já existe"}), 409
    setores.append(nome); _set_setting("setores", setores); db.session.commit()
    return jsonify(setores)


@app.route("/api/settings/setores/<nome>", methods=["DELETE"])
@requires("Administrador")
def del_setor(nome):
    nome = clean_text(nome, 80)
    setores=[s for s in (_clean_list_setting(_get_setting("setores",[]), 80) or []) if s != nome]
    _set_setting("setores",setores); db.session.commit()
    return jsonify(setores)


@app.route("/api/settings/unidades", methods=["POST"])
@requires("Administrador")
def add_unidade():
    uns = _get_setting("unidades", [])
    uns = uns if isinstance(uns, list) else []
    unidade, error = _normalize_unidade_payload(json_payload())
    if error:
        return jsonify({"error": error}), 400
    if any((u.get("nome") or "").casefold() == unidade["nome"].casefold() for u in uns if isinstance(u, dict)):
        return jsonify({"error":"Unidade já existe"}), 409
    unidade["id"] = new_id("UN")
    uns.append(unidade); _set_setting("unidades",uns); db.session.commit()
    return jsonify(unidade),201


@app.route("/api/settings/unidades/<uid>", methods=["PUT"])
@requires("Administrador")
def update_unidade(uid):
    d=json_payload(); uns=_get_setting("unidades",[])
    uns = uns if isinstance(uns, list) else []
    for i,u in enumerate(uns):
        if isinstance(u, dict) and u.get("id")==uid:
            unidade, error = _normalize_unidade_payload(d, {**u, "id": uid})
            if error:
                return jsonify({"error": error}), 400
            uns[i]=unidade; _set_setting("unidades",uns); db.session.commit(); return jsonify(uns[i])
    return jsonify({"error":"Não encontrado"}),404


@app.route("/api/settings/unidades/<uid>", methods=["DELETE"])
@requires("Administrador")
def del_unidade(uid):
    unidades = _get_setting("unidades", [])
    unidades = unidades if isinstance(unidades, list) else []
    uns=[u for u in unidades if isinstance(u, dict) and u.get("id")!=uid]
    _set_setting("unidades",uns); db.session.commit(); return jsonify({"ok":True})


@app.route("/api/settings/email", methods=["PUT"])
@requires("Administrador")
def update_email_settings():
    d = json_payload()
    source = clean_text(d.get("source", _get_setting("email.source", "app")), 20)
    if source not in ("app", "env"):
        return jsonify({"error": "Origem SMTP inválida."}), 400
    _set_setting("email.source", source)

    text_fields = {
        "host": 160,
        "user": 160,
        "from_name": 120,
        "from_email": 120,
    }
    if "from_email" in d:
        err_email = validate_email(d.get("from_email"))
        if err_email:
            return jsonify({"error": err_email}), 400
    for key, max_len in text_fields.items():
        if key in d:
            _set_setting(f"email.{key}", clean_text(d.get(key), max_len))
    if "port" in d:
        port = parse_int(d.get("port"), default=587, minimum=1)
        if port > 65535:
            return jsonify({"error": "Porta SMTP inválida."}), 400
        _set_setting("email.port", port)
    for key in ("tls", "enabled"):
        if key in d:
            _set_setting(f"email.{key}", parse_bool(d.get(key), default=(key == "tls")))
    if parse_bool(d.get("enabled"), default=False) and source == "app":
        host = clean_text(d.get("host", _get_setting("email.host", "")), 160)
        from_email = clean_text(d.get("from_email", _get_setting("email.from_email", "")), 120)
        if not host:
            return jsonify({"error": "Servidor SMTP é obrigatório para ativar pela aplicação."}), 400
        if not from_email:
            return jsonify({"error": "E-mail remetente é obrigatório para ativar pela aplicação."}), 400
    # Senha salva separadamente apenas se fornecida (para não sobrescrever com vazio)
    if parse_bool(d.get("clear_password"), default=False):
        _set_setting("email.password", "")
    if d.get("password"):
        _set_setting("email.password", str(d["password"]))
    audit("EDITAR", "configuracoes", "", "Configurações de e-mail atualizadas")
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/settings/email/test", methods=["POST"])
@requires("Administrador")
def test_email_settings():
    dest = clean_text(json_payload().get("email"), 120) or current_user.email
    if not dest:
        return jsonify({"error": "Usuário sem e-mail cadastrado e nenhum endereço fornecido."}), 400
    err_email = validate_email(dest)
    if err_email:
        return jsonify({"error": err_email}), 400
    result = send_email(
        dest,
        "TI Control — Teste de e-mail",
        f"<p>E-mail de teste enviado com sucesso pelo TI Control.</p><p>Configuração SMTP ativa.</p>",
        "E-mail de teste enviado com sucesso pelo TI Control."
    )
    if result["ok"]:
        audit("TESTE_EMAIL", "configuracoes", "", f"E-mail de teste enviado para {dest}")
        db.session.commit()
    return jsonify(result), 200 if result["ok"] else 502


@app.route("/api/settings/email/templates", methods=["PUT"])
@requires("Administrador")
def update_email_templates():
    templates, error = _normalize_email_templates(json_payload())
    if error:
        return jsonify({"error": error}), 400
    _set_setting("email_templates", templates)
    audit("EDITAR", "configuracoes", "", "Templates de e-mail atualizados")
    db.session.commit()
    return jsonify(templates)


@app.route("/api/settings/backup", methods=["PUT"])
@requires("Administrador")
def update_backup_settings():
    cfg, error = _normalize_backup_config(json_payload())
    if error:
        return jsonify({"error": error}), 400
    _set_setting("backup", cfg)
    audit("EDITAR", "configuracoes", "", "Configuração de backup atualizada")
    db.session.commit()
    return jsonify(cfg)


@app.route("/api/system/update/status")
@requires("Administrador")
def system_update_status():
    fetch = request.args.get("fetch") == "1"
    return jsonify(_system_update_status(fetch=fetch))


@app.route("/api/system/update/apply", methods=["POST"])
@requires("Administrador")
def system_update_apply():
    status = _system_update_status(fetch=True)
    if not status["supported"]:
        return jsonify({"error": status["message"], "status": status}), 409
    if status["dirty"]:
        return jsonify({"error": "Existem alterações locais no servidor. Resolva antes de atualizar.", "status": status}), 409
    if status["ahead"]:
        return jsonify({"error": "O servidor possui commits locais à frente do repositório remoto. Atualização automática bloqueada.", "status": status}), 409

    try:
        backup = _write_backup_file("manual", generated_by=f"pre_update:{current_user.username}")
    except Exception as exc:
        return jsonify({"error": f"Falha ao gerar backup pré-atualização: {exc}", "status": status}), 500

    result, error = _run_update_command(["git", "pull", "--ff-only"], timeout=180)
    if error or result.returncode != 0:
        return jsonify({
            "error": error or (result.stderr or result.stdout or "Falha ao aplicar atualização.").strip(),
            "backup": backup,
            "status": status,
        }), 500

    new_commit = _git_value("rev-parse", "--short", "HEAD")
    new_version = _app_version_from_file(new_commit or "0.1.1-BETA")
    env_updated = _set_env_file_value("BUILD_VERSION", new_version) if new_version else False
    audit("ATUALIZAR_SISTEMA", "configuracoes", "", f"Atualização aplicada para {new_version or new_commit or 'versão desconhecida'}")
    db.session.commit()
    restart_scheduled = _schedule_self_restart()
    return jsonify({
        "ok": True,
        "backup": backup,
        "previous": status,
        "newVersion": new_version,
        "newCommit": new_commit,
        "envUpdated": env_updated,
        "restartRequired": not restart_scheduled,
        "restartScheduled": restart_scheduled,
        "message": "Atualização aplicada. A aplicação será reiniciada automaticamente." if restart_scheduled else "Atualização aplicada. Reinicie/recrie a aplicação para carregar o novo código.",
        "output": (result.stdout or "").strip()[-2000:],
    })


@app.route("/api/settings/termos", methods=["PUT"])
@requires("Administrador")
def update_termos_settings():
    d = json_payload()
    if not d:
        return jsonify({"error": "Payload JSON obrigatório."}), 400
    for key in ("termo_recebimento", "termo_devolucao"):
        if key in d:
            normalized, error = _normalize_termo_setting(key, d[key])
            if error:
                return jsonify({"error": error}), 400
            _set_setting(key, normalized)
    audit("EDITAR", "configuracoes", "", "Personalização de termos atualizada")
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/settings/categorias", methods=["POST"])
@requires("Administrador")
def add_categoria():
    nome = clean_text((json_payload() or {}).get("nome"), 60)
    if not nome:
        return jsonify({"error": "Nome obrigatório"}), 400
    cats = _get_setting("categorias", CATEGORIAS_DEFAULT) or list(CATEGORIAS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_DEFAULT)
    if any(c.casefold() == nome.casefold() for c in cats):
        return jsonify({"error": "Categoria já existe"}), 409
    cats.append(nome)
    _set_setting("categorias", cats)
    audit("CRIAR", "configuracoes", "", f"Categoria '{nome}' adicionada")
    db.session.commit()
    return jsonify(cats), 201


@app.route("/api/settings/categorias/<nome>", methods=["DELETE"])
@requires("Administrador")
def del_categoria(nome):
    nome = clean_text(nome, 60)
    cats = _get_setting("categorias", CATEGORIAS_DEFAULT) or list(CATEGORIAS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_DEFAULT)
    cats = [c for c in cats if c != nome]
    if not cats:
        return jsonify({"error": "Não é possível remover a última categoria."}), 400
    _set_setting("categorias", cats)
    audit("EXCLUIR", "configuracoes", "", f"Categoria '{nome}' removida")
    db.session.commit()
    return jsonify(cats)


@app.route("/api/settings/categorias/<nome>", methods=["PUT"])
@requires("Administrador")
def rename_categoria(nome):
    nome = clean_text(nome, 60)
    novo = clean_text((json_payload() or {}).get("nome"), 60)
    if not novo:
        return jsonify({"error": "Novo nome obrigatório"}), 400
    cats = _get_setting("categorias", CATEGORIAS_DEFAULT) or list(CATEGORIAS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_DEFAULT)
    if nome not in cats:
        return jsonify({"error": "Categoria não encontrada"}), 404
    if any(c.casefold() == novo.casefold() and c != nome for c in cats):
        return jsonify({"error": "Já existe uma categoria com esse nome"}), 409
    cats = [novo if c == nome else c for c in cats]
    _set_setting("categorias", cats)
    audit("EDITAR", "configuracoes", "", f"Categoria '{nome}' renomeada para '{novo}'")
    db.session.commit()
    return jsonify(cats)


# ── Categorias de Insumos/Periféricos ────────────────────────────────────────

@app.route("/api/settings/categorias-insumos", methods=["POST"])
@requires("Administrador")
def add_categoria_insumo():
    nome = clean_text((json_payload() or {}).get("nome"), 60)
    if not nome:
        return jsonify({"error": "Nome obrigatório"}), 400
    cats = _get_setting("categorias_insumos", CATEGORIAS_INSUMOS_DEFAULT) or list(CATEGORIAS_INSUMOS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_INSUMOS_DEFAULT)
    if any(c.casefold() == nome.casefold() for c in cats):
        return jsonify({"error": "Categoria já existe"}), 409
    cats.append(nome)
    _set_setting("categorias_insumos", cats)
    audit("CRIAR", "configuracoes", "", f"Categoria de insumo '{nome}' adicionada")
    db.session.commit()
    return jsonify(cats), 201


@app.route("/api/settings/categorias-insumos/<nome>", methods=["DELETE"])
@requires("Administrador")
def del_categoria_insumo(nome):
    nome = clean_text(nome, 60)
    cats = _get_setting("categorias_insumos", CATEGORIAS_INSUMOS_DEFAULT) or list(CATEGORIAS_INSUMOS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_INSUMOS_DEFAULT)
    cats = [c for c in cats if c != nome]
    if not cats:
        return jsonify({"error": "Não é possível remover a última categoria."}), 400
    _set_setting("categorias_insumos", cats)
    audit("EXCLUIR", "configuracoes", "", f"Categoria de insumo '{nome}' removida")
    db.session.commit()
    return jsonify(cats)


@app.route("/api/settings/categorias-insumos/<nome>", methods=["PUT"])
@requires("Administrador")
def rename_categoria_insumo(nome):
    nome = clean_text(nome, 60)
    novo = clean_text((json_payload() or {}).get("nome"), 60)
    if not novo:
        return jsonify({"error": "Novo nome obrigatório"}), 400
    cats = _get_setting("categorias_insumos", CATEGORIAS_INSUMOS_DEFAULT) or list(CATEGORIAS_INSUMOS_DEFAULT)
    if not isinstance(cats, list):
        cats = list(CATEGORIAS_INSUMOS_DEFAULT)
    if nome not in cats:
        return jsonify({"error": "Categoria não encontrada"}), 404
    if any(c.casefold() == novo.casefold() and c != nome for c in cats):
        return jsonify({"error": "Já existe uma categoria com esse nome"}), 409
    cats = [novo if c == nome else c for c in cats]
    _set_setting("categorias_insumos", cats)
    audit("EDITAR", "configuracoes", "", f"Categoria de insumo '{nome}' renomeada para '{novo}'")
    db.session.commit()
    return jsonify(cats)

