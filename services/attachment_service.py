"""Regras de validacao, armazenamento e consulta de anexos."""
import os
import uuid

from flask import current_app
from flask_login import current_user
from werkzeug.utils import secure_filename

from extensions import db
from models import Asset, Attachment, License, MaintenanceOrder


ATTACHMENT_MAX_BYTES = 8 * 1024 * 1024
ATTACHMENT_ALLOWED_EXT = {
    "pdf", "png", "jpg", "jpeg", "webp", "txt", "csv", "doc", "docx", "xls", "xlsx",
}
ATTACHMENT_MIME_BY_EXT = {
    "pdf": {"application/pdf"},
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "webp": {"image/webp"},
    "txt": {"text/plain"},
    "csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
    "doc": {"application/msword", "application/octet-stream"},
    "docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip", "application/octet-stream"},
    "xls": {"application/vnd.ms-excel", "application/octet-stream"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/zip", "application/octet-stream"},
}


def clean_text(value, max_len=None):
    value = "" if value is None else str(value).strip()
    if max_len and len(value) > max_len:
        value = value[:max_len]
    return value


def new_id(prefix):
    return prefix + uuid.uuid4().hex[:6].upper()


def attachment_dir():
    return os.path.join(current_app.instance_path, "attachments")


def attachment_entity_exists(entity_type, entity_id):
    model_map = {
        "asset": Asset,
        "maintenance": MaintenanceOrder,
        "license": License,
    }
    model = model_map.get(entity_type)
    return bool(model and db.session.get(model, entity_id))


def attachment_path(stored_name):
    safe = secure_filename(stored_name or "")
    if not safe or safe != stored_name:
        return None
    base = os.path.abspath(attachment_dir())
    path = os.path.abspath(os.path.join(base, safe))
    if not path.startswith(base + os.sep):
        return None
    return path


def attachment_ext(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def attachment_magic_matches(ext, data):
    if ext == "pdf":
        return data.startswith(b"%PDF-")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in {"jpg", "jpeg"}:
        return data.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    if ext in {"docx", "xlsx"}:
        return data.startswith(b"PK\x03\x04")
    if ext in {"txt", "csv"}:
        return b"\x00" not in data[:2048]
    return True


def create_attachment_record(entity_type, entity_id, file, category="Documento", description="", uploaded_by=None):
    if not file or not file.filename:
        return None, ("Arquivo obrigatório.", 400)
    original = clean_text(file.filename, 180)
    ext = attachment_ext(original)
    if ext not in ATTACHMENT_ALLOWED_EXT:
        return None, ("Tipo de arquivo não permitido.", 400)
    content_length = getattr(file, "content_length", None)
    if content_length and content_length > ATTACHMENT_MAX_BYTES:
        return None, ("Arquivo excede o limite de 8 MB.", 400)
    data = file.read()
    if not data:
        return None, ("Arquivo vazio.", 400)
    if len(data) > ATTACHMENT_MAX_BYTES:
        return None, ("Arquivo excede o limite de 8 MB.", 400)

    mimetype = file.mimetype or "application/octet-stream"
    allowed_mimes = ATTACHMENT_MIME_BY_EXT.get(ext, set())
    if allowed_mimes and mimetype not in allowed_mimes:
        return None, ("Tipo de arquivo incompatível com a extensão.", 400)
    if not attachment_magic_matches(ext, data):
        return None, ("Conteúdo do arquivo não corresponde ao tipo informado.", 400)

    os.makedirs(attachment_dir(), exist_ok=True)
    att_id = new_id("ATT")
    safe_name = secure_filename(original) or f"anexo.{ext}"
    stored_name = f"{att_id}_{safe_name}"
    path = attachment_path(stored_name)
    if not path:
        return None, ("Nome de arquivo inválido.", 400)
    with open(path, "wb") as fh:
        fh.write(data)

    if uploaded_by:
        user_label = uploaded_by
    else:
        try:
            user_label = getattr(current_user, "username", None) or "sistema"
        except RuntimeError:
            user_label = "sistema"

    att = Attachment(
        id=att_id,
        entity_type=entity_type,
        entity_id=entity_id,
        original_name=original,
        stored_name=stored_name,
        content_type=mimetype,
        size=len(data),
        category=clean_text(category or "Documento", 40),
        description=clean_text(description or "", 500),
        uploaded_by=user_label,
    )
    db.session.add(att)
    return att, None
