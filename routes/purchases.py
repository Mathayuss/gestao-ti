"""Rotas do modulo de compras e reposicao."""

from flask import jsonify, request
from flask_login import current_user

from app import (
    DEFAULT_COMPRAS_CONFIG,
    _get_setting,
    api_auth,
    audit,
    clean_text,
    json_payload,
    requires,
)
from extensions import db
from purchase_models import PURCHASE_STATUS, PurchaseApprovalRule, PurchaseRequest
from routes.blueprint import bp
from services.purchase_service import (
    PurchaseError,
    apply_rule_payload,
    approve_purchase as service_approve_purchase,
    create_purchase as service_create_purchase,
    ensure_default_approval_rules,
    procurement_action as service_procurement_action,
    receive_purchase as service_receive_purchase,
    send_to_procurement as service_send_to_procurement,
    submit_purchase as service_submit_purchase,
    update_purchase as service_update_purchase,
    new_id,
)

def _purchase_settings():
    saved = _get_setting("compras", {}) or {}
    if not isinstance(saved, dict):
        saved = {}
    return {**DEFAULT_COMPRAS_CONFIG, **saved}


def _purchases_enabled():
    return bool(_purchase_settings().get("enabled"))


def _require_purchases_enabled():
    if not _purchases_enabled():
        return jsonify({"error": "Modulo de compras desabilitado em Configuracoes."}), 403
    return None


def _handle_purchase_error(exc):
    db.session.rollback()
    return jsonify({"error": exc.message}), exc.status_code


@bp.route("/api/purchases/status")
@requires("Administrador")
def purchase_status():
    return jsonify({"settings": _purchase_settings(), "statuses": PURCHASE_STATUS})


@bp.route("/api/purchases", methods=["GET"])
@api_auth
def list_purchases():
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    status = clean_text(request.args.get("status"), 60)
    q = clean_text(request.args.get("q"), 120)
    stmt = db.select(PurchaseRequest).order_by(PurchaseRequest.created_at.desc())
    if status:
        stmt = stmt.where(PurchaseRequest.status == status)
    if q:
        stmt = stmt.where(db.or_(PurchaseRequest.numero.ilike(f"%{q}%"), PurchaseRequest.solicitante.ilike(f"%{q}%")))
    rows = db.session.execute(stmt).scalars().all()
    return jsonify([row.to_dict() for row in rows])


@bp.route("/api/purchases", methods=["POST"])
@api_auth
def create_purchase():
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    try:
        req = service_create_purchase(json_payload(), current_user, audit=audit)
        audit("CRIAR", "compras", req.id, f"Solicitacao {req.numero} criada")
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True)), 201
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>", methods=["GET"])
@api_auth
def get_purchase(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    return jsonify(req.to_dict(include_items=True, include_history=True))


@bp.route("/api/purchases/<pid>", methods=["PUT"])
@api_auth
def update_purchase(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_update_purchase(req, json_payload(), current_user, audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>/submit", methods=["POST"])
@api_auth
def submit_purchase(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_submit_purchase(req, current_user, audit=audit)
        if _purchase_settings().get("auto_send_to_procurement") and req.status == "Aguardando envio para Suprimentos":
            service_send_to_procurement(req, current_user, {"observacao": "Envio automatico configurado."}, audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>/approve", methods=["POST"])
@api_auth
def approve_purchase(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_approve_purchase(req, current_user, json_payload(), audit=audit, ip_address=request.remote_addr or "")
        if _purchase_settings().get("auto_send_to_procurement") and req.status == "Aguardando envio para Suprimentos":
            service_send_to_procurement(req, current_user, {"observacao": "Envio automatico configurado."}, audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>/send-procurement", methods=["POST"])
@api_auth
def send_purchase_to_procurement(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_send_to_procurement(req, current_user, json_payload(), audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>/procurement-action", methods=["POST"])
@api_auth
def register_procurement_action(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_procurement_action(req, current_user, json_payload(), audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/<pid>/receipts", methods=["POST"])
@api_auth
def receive_purchase(pid):
    blocked = _require_purchases_enabled()
    if blocked:
        return blocked
    req = db.get_or_404(PurchaseRequest, pid)
    try:
        service_receive_purchase(req, current_user, json_payload(), audit=audit)
        db.session.commit()
        return jsonify(req.to_dict(include_items=True, include_history=True))
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/approval-rules", methods=["GET"])
@requires("Administrador")
def list_purchase_rules():
    ensure_default_approval_rules()
    db.session.commit()
    rules = db.session.execute(
        db.select(PurchaseApprovalRule).order_by(PurchaseApprovalRule.ordem_aprovacao, PurchaseApprovalRule.valor_minimo)
    ).scalars().all()
    return jsonify([rule.to_dict() for rule in rules])


@bp.route("/api/purchases/approval-rules", methods=["POST"])
@requires("Administrador")
def create_purchase_rule():
    rule = PurchaseApprovalRule(id=new_id("PR"), nome="Nova regra")
    try:
        apply_rule_payload(rule, json_payload())
        db.session.add(rule)
        audit("CRIAR_ALCADA", "compras", rule.id, f"Regra {rule.nome} criada")
        db.session.commit()
        return jsonify(rule.to_dict()), 201
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/approval-rules/<rid>", methods=["PUT"])
@requires("Administrador")
def update_purchase_rule(rid):
    rule = db.get_or_404(PurchaseApprovalRule, rid)
    try:
        apply_rule_payload(rule, json_payload())
        audit("EDITAR_ALCADA", "compras", rid, f"Regra {rule.nome} editada")
        db.session.commit()
        return jsonify(rule.to_dict())
    except PurchaseError as exc:
        return _handle_purchase_error(exc)


@bp.route("/api/purchases/approval-rules/<rid>", methods=["DELETE"])
@requires("Administrador")
def delete_purchase_rule(rid):
    rule = db.get_or_404(PurchaseApprovalRule, rid)
    db.session.delete(rule)
    audit("EXCLUIR_ALCADA", "compras", rid, rule.nome)
    db.session.commit()
    return jsonify({"ok": True})
