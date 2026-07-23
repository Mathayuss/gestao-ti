"""Configuracao centralizada do TI Control."""
import logging
import os

from dotenv import load_dotenv


ALEMBIC_SCHEMA_HEAD = "b7c4d2a93f10"
DEFAULT_BUILD_VERSION = "1.3.5"
DEFAULT_SECRET_KEY_DEV = "ticontrol-dev-only-secret-DO-NOT-USE-IN-PROD"

logger = logging.getLogger("ti_control")


def load_environment():
    load_dotenv()


def bool_env(name, default=False):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "t", "yes", "y", "sim", "s", "on"}


def int_env(name, default, minimum=None):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    return value


def float_env(name, default, minimum=None):
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    return value


def version_from_file(root_path=None, default=DEFAULT_BUILD_VERSION):
    version_path = os.path.join(root_path or os.path.dirname(__file__), "VERSION")
    try:
        with open(version_path, "r", encoding="utf-8") as fh:
            return fh.read().strip() or default
    except OSError:
        return default


def resolved_build_version(root_path=None):
    env_version = (os.environ.get("BUILD_VERSION") or "").strip()
    return env_version or version_from_file(root_path)


def resolve_secret_key():
    secret_key = os.environ.get("SECRET_KEY", "")
    if secret_key:
        return secret_key
    if os.environ.get("FLASK_DEBUG", "0") == "1":
        logger.warning("SECRET_KEY não definida; usando chave de desenvolvimento insegura")
        return DEFAULT_SECRET_KEY_DEV
    raise RuntimeError(
        "SECRET_KEY não definida. Configure a variável de ambiente SECRET_KEY antes de iniciar em produção."
    )


def database_engine_options(database_uri):
    options = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    if not str(database_uri or "").startswith("sqlite"):
        options.update({
            "pool_size": int_env("DATABASE_POOL_SIZE", 5, minimum=1),
            "max_overflow": int_env("DATABASE_MAX_OVERFLOW", 10, minimum=0),
            "pool_timeout": int_env("DATABASE_POOL_TIMEOUT", 30, minimum=1),
        })
    return options


def flask_config(root_path=None):
    database_uri = os.environ.get("DATABASE_URL", "sqlite:///ticontrol.db")
    session_secure = bool_env("SESSION_SECURE", default=False)
    return {
        "SECRET_KEY": resolve_secret_key(),
        "SQLALCHEMY_DATABASE_URI": database_uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": database_engine_options(database_uri),
        "JSON_SORT_KEYS": False,
        "APP_BASE_URL": os.environ.get("APP_BASE_URL", "http://localhost").rstrip("/"),
        "SERVICE_NAME": os.environ.get("SERVICE_NAME", "ti-control"),
        "BUILD_VERSION": resolved_build_version(root_path),
        "ENVIRONMENT": os.environ.get("ENVIRONMENT", "development"),
        "SHOW_DEMO_CREDENTIALS": bool_env("SHOW_DEMO_CREDENTIALS", default=False),
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": session_secure,
        "SESSION_COOKIE_NAME": "ticontrol_session",
        "PERMANENT_SESSION_LIFETIME": 86400 * 7,
        "REMEMBER_COOKIE_HTTPONLY": True,
        "REMEMBER_COOKIE_SAMESITE": "Lax",
        "REMEMBER_COOKIE_SECURE": session_secure,
        "REMEMBER_COOKIE_DURATION": 86400 * 7,
        "MAX_CONTENT_LENGTH": 16 * 1024 * 1024,
        "WTF_CSRF_CHECK_DEFAULT": True,
        "AUTO_CREATE_DB": bool_env("AUTO_CREATE_DB", default=True),
        "AUTO_LEGACY_MIGRATIONS": bool_env("AUTO_LEGACY_MIGRATIONS", default=True),
    }


def startup_retry_config():
    return (
        int_env("DB_STARTUP_RETRIES", 12, minimum=1),
        float_env("DB_STARTUP_RETRY_DELAY", 2, minimum=0),
    )


def runtime_server_config():
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int_env("FLASK_PORT", int_env("APP_PORT", 5000), minimum=1)
    debug = bool_env("FLASK_DEBUG", default=True)
    return host, port, debug
