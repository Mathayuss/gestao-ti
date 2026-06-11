"""Regras de configuracao e agendamento de backup."""
import re
from datetime import date, datetime, timedelta


DEFAULT_BACKUP_CONFIG = {
    "enabled": False,
    "frequency": "daily",
    "schedule_time": "02:00",
    "weekly_day": 1,
    "monthly_day": 1,
    "retention": 7,
    "include_audit": False,
    "last_run": "",
    "last_file": "",
    "last_status": "Nunca executado",
    "last_error": "",
}

BACKUP_FREQUENCIES = {"daily", "weekly", "monthly"}


def clean_text(value, max_len=None):
    value = "" if value is None else str(value).strip()
    if max_len and len(value) > max_len:
        value = value[:max_len]
    return value


def parse_int(value, default=0, minimum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None and number < minimum:
        number = minimum
    return number


def parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "sim", "s", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "nao", "não", "off"}:
        return False
    return default


def parse_backup_schedule_time(value):
    raw = clean_text(value, 5)
    if not re.fullmatch(r"\d{1,2}:\d{2}", raw):
        return None
    hour_raw, minute_raw = raw.split(":", 1)
    hour = parse_int(hour_raw, default=-1)
    minute = parse_int(minute_raw, default=-1)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()


def normalize_backup_schedule_time(value, default="02:00"):
    parsed = parse_backup_schedule_time(value) or parse_backup_schedule_time(default)
    return parsed.strftime("%H:%M")


def last_day_of_month(year, month):
    if month == 12:
        first_next_month = date(year + 1, 1, 1)
    else:
        first_next_month = date(year, month + 1, 1)
    return (first_next_month - timedelta(days=1)).day


def normalize_backup_config(saved=None):
    """Normaliza configuracao persistida, preservando campos de status."""
    saved = saved if isinstance(saved, dict) else {}
    cfg = {**DEFAULT_BACKUP_CONFIG, **saved}
    cfg["enabled"] = parse_bool(cfg.get("enabled"), default=False)
    cfg["frequency"] = cfg.get("frequency") if cfg.get("frequency") in BACKUP_FREQUENCIES else "daily"
    cfg["schedule_time"] = normalize_backup_schedule_time(cfg.get("schedule_time"), default="02:00")
    cfg["weekly_day"] = min(max(parse_int(cfg.get("weekly_day"), default=1), 0), 6)
    cfg["monthly_day"] = min(max(parse_int(cfg.get("monthly_day"), default=1, minimum=1), 1), 31)
    cfg["retention"] = parse_int(cfg.get("retention"), default=7, minimum=1)
    cfg["include_audit"] = parse_bool(cfg.get("include_audit"), default=False)
    return cfg


def update_backup_config(current, changes):
    """Aplica alteracoes de configuracao vindas da API, retornando (cfg, erro)."""
    if not isinstance(changes, dict):
        return None, "Configuração de backup precisa ser um objeto."
    cfg = normalize_backup_config(current)
    if "enabled" in changes:
        cfg["enabled"] = parse_bool(changes.get("enabled"), default=False)
    if "frequency" in changes:
        freq = clean_text(changes.get("frequency"), 20)
        if freq not in BACKUP_FREQUENCIES:
            return None, "Frequência de backup inválida."
        cfg["frequency"] = freq
    if "schedule_time" in changes:
        parsed = parse_backup_schedule_time(changes.get("schedule_time"))
        if not parsed:
            return None, "Horário de backup inválido."
        cfg["schedule_time"] = parsed.strftime("%H:%M")
    if "weekly_day" in changes:
        weekly_day = parse_int(changes.get("weekly_day"), default=1)
        if weekly_day < 0 or weekly_day > 6:
            return None, "Dia da semana do backup inválido."
        cfg["weekly_day"] = weekly_day
    if "monthly_day" in changes:
        monthly_day = parse_int(changes.get("monthly_day"), default=1)
        if monthly_day < 1 or monthly_day > 31:
            return None, "Dia do mês do backup inválido."
        cfg["monthly_day"] = monthly_day
    if "retention" in changes:
        cfg["retention"] = min(parse_int(changes.get("retention"), default=7, minimum=1), 90)
    if "include_audit" in changes:
        cfg["include_audit"] = parse_bool(changes.get("include_audit"), default=False)
    return cfg, None


def backup_scheduled_at_for_period(cfg, now=None):
    cfg = normalize_backup_config(cfg)
    now = now or datetime.now()
    schedule_time = parse_backup_schedule_time(cfg.get("schedule_time")) or parse_backup_schedule_time("02:00")
    frequency = cfg["frequency"]
    if frequency == "daily":
        scheduled_date = now.date()
    elif frequency == "weekly":
        current_weekday = (now.weekday() + 1) % 7
        week_start = now.date() - timedelta(days=current_weekday)
        scheduled_date = week_start + timedelta(days=cfg["weekly_day"])
    else:
        scheduled_day = min(cfg["monthly_day"], last_day_of_month(now.year, now.month))
        scheduled_date = date(now.year, now.month, scheduled_day)
    return datetime.combine(scheduled_date, schedule_time)


def backup_is_due(cfg, now=None):
    cfg = normalize_backup_config(cfg)
    if not cfg["enabled"]:
        return False
    now = now or datetime.now()
    scheduled_at = backup_scheduled_at_for_period(cfg, now)
    if now < scheduled_at:
        return False
    try:
        last_run = datetime.fromisoformat(cfg.get("last_run") or "")
    except (TypeError, ValueError):
        last_run = None
    if not last_run:
        return True
    return last_run < scheduled_at
