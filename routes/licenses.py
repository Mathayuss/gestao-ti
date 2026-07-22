"""Rotas de licencas de software."""
from app import _export_route_globals

globals().update(_export_route_globals())
from routes.blueprint import bp


LICENSE_TYPES = ("Assinatura mensal", "Anual", "Perpétua", "Por uso")
LICENSE_TYPE_ALIASES = {
    "Assinatura": "Assinatura mensal",
    "Mensal": "Assinatura mensal",
}


def _license_int(value, default, label, errors):
    if value in (None, ""):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors.append(f"{label} deve ser um número inteiro.")
        return default
    if parsed < 0:
        errors.append(f"{label} não pode ser negativo.")
        return default
    return parsed


def _license_float(value, default, label, errors):
    if value in (None, ""):
        return default
    try:
        parsed = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        errors.append(f"{label} deve ser um número válido.")
        return default
    if parsed < 0:
        errors.append(f"{label} não pode ser negativo.")
        return default
    return parsed


def _normalize_license_payload(data, current=None):
    data = data or {}
    errors = []
    software = clean_text(data.get("software", getattr(current, "software", "")), 120)
    fornecedor = clean_text(data.get("fornecedor", getattr(current, "fornecedor", "")), 80)
    tipo = clean_text(data.get("tipo", getattr(current, "tipo", "Assinatura mensal")) or "Assinatura mensal", 40)
    tipo = LICENSE_TYPE_ALIASES.get(tipo, tipo)
    vencimento = clean_text(data.get("vencimento", getattr(current, "vencimento", "")), 10) or None
    total = _license_int(data.get("total", getattr(current, "total", 0)), 0, "Total", errors)
    atribuidas = _license_int(data.get("atribuidas", getattr(current, "atribuidas", 0)), 0, "Atribuídas", errors)
    custo = _license_float(data.get("custo", getattr(current, "custo", 0.0)), 0.0, "Custo", errors)

    if not software:
        errors.append("Software é obrigatório.")
    if tipo not in LICENSE_TYPES:
        errors.append(f"Tipo inválido. Use: {', '.join(LICENSE_TYPES)}.")
    if vencimento:
        try:
            datetime.strptime(vencimento, "%Y-%m-%d")
        except ValueError:
            errors.append("Vencimento deve estar no formato AAAA-MM-DD.")

    return {
        "software": software,
        "fornecedor": fornecedor,
        "total": total,
        "atribuidas": atribuidas,
        "vencimento": vencimento,
        "custo": custo,
        "tipo": tipo,
    }, errors


@bp.route("/api/licenses", methods=["GET"])
@api_auth
def get_licenses():
    licenses = db.session.execute(db.select(License).order_by(License.software.asc())).scalars().all()
    return jsonify([l.to_dict() for l in licenses])


@bp.route("/api/licenses", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_license():
    payload, errors = _normalize_license_payload(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"error": "Validação da licença falhou.", "details": errors}), 400
    license_obj = License(id=new_id("L"), **payload)
    db.session.add(license_obj)
    audit("CRIAR", "licencas", license_obj.id, f"Licença {license_obj.software} cadastrada")
    db.session.commit()
    return jsonify(license_obj.to_dict()), 201


@bp.route("/api/licenses/<lid>", methods=["PUT"])
@requires("Administrador", "Técnico TI")
def update_license(lid):
    license_obj = db.get_or_404(License, lid)
    payload, errors = _normalize_license_payload(request.get_json(silent=True) or {}, license_obj)
    if errors:
        return jsonify({"error": "Validação da licença falhou.", "details": errors}), 400
    for attr, value in payload.items():
        setattr(license_obj, attr, value)
    audit("EDITAR", "licencas", lid, f"Licença {license_obj.software} atualizada")
    db.session.commit()
    return jsonify(license_obj.to_dict())


@bp.route("/api/licenses/<lid>/upload", methods=["POST"])
@requires("Administrador", "Técnico TI")
def upload_license_attachment(lid):
    license_obj = db.get_or_404(License, lid)
    att, error = _create_attachment_record(
        "license",
        lid,
        request.files.get("file"),
        request.form.get("category") or "Documento",
        request.form.get("description") or "",
    )
    if error:
        message, status = error
        return jsonify({"error": message}), status
    audit("ANEXO_UPLOAD", "licencas", lid, f"Anexo {att.original_name} adicionado à licença {license_obj.software}")
    db.session.commit()
    return jsonify({"ok": True, "filename": att.original_name, "attachment": att.to_dict()}), 201
