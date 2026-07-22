"""Rotas para anexos de ativos, manutenções e licenças."""
from app import _export_route_globals

globals().update(_export_route_globals())
from routes.blueprint import bp


ATTACHMENT_ENTITY_LABEL = {
    "asset": "ativo",
    "maintenance": "manutencao",
    "license": "licenca",
}


def _attachment_query(entity_type, entity_id):
    return db.select(Attachment).where(
        Attachment.entity_type == entity_type,
        Attachment.entity_id == entity_id,
    ).order_by(Attachment.uploaded_at.desc())


@bp.route("/api/attachments/<entity_type>/<entity_id>", methods=["GET"])
@api_auth
def list_attachments(entity_type, entity_id):
    entity_type = clean_text(entity_type, 30)
    entity_id = clean_text(entity_id, 16)
    if entity_type not in ATTACHMENT_ENTITY_LABEL:
        return jsonify({"error": "Tipo de entidade inválido."}), 400
    if not _attachment_entity_exists(entity_type, entity_id):
        return jsonify({"error": "Entidade não encontrada."}), 404
    items = db.session.execute(_attachment_query(entity_type, entity_id)).scalars().all()
    return jsonify([a.to_dict() for a in items])


@bp.route("/api/attachments/<entity_type>/<entity_id>", methods=["POST"])
@requires("Administrador", "Técnico TI")
def upload_attachment(entity_type, entity_id):
    entity_type = clean_text(entity_type, 30)
    entity_id = clean_text(entity_id, 16)
    if entity_type not in ATTACHMENT_ENTITY_LABEL:
        return jsonify({"error": "Tipo de entidade inválido."}), 400
    if not _attachment_entity_exists(entity_type, entity_id):
        return jsonify({"error": "Entidade não encontrada."}), 404

    att, error = _create_attachment_record(
        entity_type,
        entity_id,
        request.files.get("file"),
        request.form.get("category") or "Documento",
        request.form.get("description") or "",
    )
    if error:
        message, status = error
        return jsonify({"error": message}), status
    audit("ANEXO_UPLOAD", ATTACHMENT_ENTITY_LABEL[entity_type], entity_id, f"Anexo enviado: {att.original_name}")
    db.session.commit()
    return jsonify(att.to_dict()), 201


@bp.route("/api/attachments/files/<attachment_id>", methods=["GET"])
@api_auth
def download_attachment(attachment_id):
    att = db.get_or_404(Attachment, attachment_id)
    module = ATTACHMENT_MODULE_BY_ENTITY.get(att.entity_type)
    if module and not _profile_allows(current_user.perfil, module, "view"):
        return jsonify({"error": "Sem permissão para acessar este anexo."}), 403
    path = _attachment_path(att.stored_name)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Arquivo não encontrado."}), 404
    return send_file(path, mimetype=att.content_type, as_attachment=True, download_name=att.original_name)


@bp.route("/api/attachments/files/<attachment_id>", methods=["DELETE"])
@api_auth
def delete_attachment(attachment_id):
    att = db.get_or_404(Attachment, attachment_id)
    module = ATTACHMENT_MODULE_BY_ENTITY.get(att.entity_type)
    if module and not _profile_allows(current_user.perfil, module, "delete"):
        return jsonify({"error": "Sem permissão para remover este anexo."}), 403
    path = _attachment_path(att.stored_name)
    if path and os.path.exists(path):
        os.remove(path)
    audit("ANEXO_DELETE", ATTACHMENT_ENTITY_LABEL.get(att.entity_type, "anexos"),
          att.entity_id, f"Anexo removido: {att.original_name}")
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True})
