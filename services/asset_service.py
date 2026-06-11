"""Regras de negocio para ativos de TI."""
from extensions import db
from models import ASSET_STATUS_VALID, Asset


DEFAULT_REQUIRED_FIELDS = ["hostname", "fabricante", "modelo", "categoria", "patrimonio"]
IGNORED_UNIQUE_VALUES = {"", "n/a", "na", "não se aplica", "nao se aplica", "dhcp", "-"}
ALL_CATEGORY_FILTERS = {"todos", "todas", "all", "__all__"}


def clean_text(value, max_len=None):
    value = "" if value is None else str(value).strip()
    if max_len and len(value) > max_len:
        value = value[:max_len]
    return value


def normalize_asset_category_filter(value):
    category = clean_text(value, 40)
    if category.lower() in ALL_CATEGORY_FILTERS:
        return ""
    return category


def asset_unique_conflicts(payload, exclude_id=None):
    """Valida duplicidade dos principais identificadores patrimoniais."""
    checks = [
        ("patrimonio", "patrimonio", "Patrimônio"),
        ("serviceTag", "service_tag", "Service Tag"),
        ("mac", "mac", "MAC"),
    ]
    conflicts = []
    for input_key, attr, label in checks:
        value = clean_text(payload.get(input_key))
        if value.lower() in IGNORED_UNIQUE_VALUES:
            continue
        column = getattr(Asset, attr)
        stmt = db.select(Asset).where(column == value)
        if exclude_id:
            stmt = stmt.where(Asset.id != exclude_id)
        existing = db.session.execute(stmt).scalar_one_or_none()
        if existing:
            conflicts.append(f"{label} '{value}' já está cadastrado no ativo {existing.hostname or existing.id}.")
    return conflicts


def validate_asset_payload(payload, required_fields=None, partial=False, exclude_id=None):
    """Valida campos e unicidade antes de criar/editar ativos."""
    payload = payload or {}
    required = required_fields or DEFAULT_REQUIRED_FIELDS
    errors = []
    if not partial:
        for field in required:
            if not clean_text(payload.get(field)):
                errors.append(f"Campo obrigatório ausente: {field}.")
    status = payload.get("status")
    if status and status not in ASSET_STATUS_VALID:
        errors.append(f"Status inválido: {status}.")
    errors.extend(asset_unique_conflicts(payload, exclude_id=exclude_id))
    return errors


def next_patrimonio(prefix="TI"):
    """Gera o próximo número de patrimônio sequencial com base no prefixo."""
    prefix = clean_text(prefix or "TI", 20).upper() or "TI"
    pattern = f"{prefix}-%"
    max_num = 0
    patrimonios = db.session.execute(
        db.select(Asset.patrimonio).where(Asset.patrimonio.like(pattern))
    ).scalars().all()
    for patrimonio in patrimonios:
        try:
            max_num = max(max_num, int(str(patrimonio).rsplit("-", 1)[-1]))
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{(max_num + 1):06d}"
