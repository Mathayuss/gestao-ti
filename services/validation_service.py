"""Validacao e normalizacao de entradas simples."""
import re


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PHONE_RE = re.compile(r"^[\d\s().+\-]{7,20}$")


def clean_text(value, max_len=None):
    value = "" if value is None else str(value).strip()
    if max_len and len(value) > max_len:
        value = value[:max_len]
    return value


def only_digits(value):
    return re.sub(r"\D+", "", "" if value is None else str(value))


def validate_cpf(value):
    cpf = only_digits(value)
    if not cpf:
        return None
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return "CPF inválido."
    total = sum(int(cpf[i]) * (10 - i) for i in range(9))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    if digit != int(cpf[9]):
        return "CPF inválido."
    total = sum(int(cpf[i]) * (11 - i) for i in range(10))
    digit = (total * 10) % 11
    if digit == 10:
        digit = 0
    if digit != int(cpf[10]):
        return "CPF inválido."
    return None


def cpf_matches(typed, expected):
    expected_digits = only_digits(expected)
    return bool(expected_digits) and only_digits(typed) == expected_digits


def parse_int(value, default=0, minimum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None and number < minimum:
        number = minimum
    return number


def parse_float(value, default=0.0, minimum=None):
    try:
        number = float(str(value).replace(",", "."))
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


def safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_text(value))
    return value.strip("_") or "arquivo"


def validate_email(value):
    v = clean_text(value)
    if v and not EMAIL_RE.match(v):
        return "E-mail inválido."
    return None


def validate_phone(value):
    v = clean_text(value)
    if v and not PHONE_RE.match(v):
        return "Telefone inválido (aceito: dígitos, espaços e ( ) - +, 7-20 chars)."
    return None
