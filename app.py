"""
TI Control — Sistema de Gestão de Ativos de TI

Inclui autenticação, persistência relacional, métricas Prometheus, health checks,
request-id e endpoints operacionais para monitoramento do serviço.
"""
import os, io, uuid, warnings, csv, json, re, time as _time, hashlib, base64, logging
import sys
sys.modules.setdefault("app", sys.modules[__name__])
import threading
from collections import defaultdict
from time import perf_counter
from datetime import date, datetime, timedelta
# Suppress Flask-Login's internal datetime.utcnow() deprecation (Python 3.12)
warnings.filterwarnings('ignore', message='.*utcnow.*', category=DeprecationWarning)
from functools import wraps
from flask import (Flask, jsonify, request, render_template, render_template_string,
                   send_file, redirect, url_for, session, Response, g)
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlsplit
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFError

from config import (
    ALEMBIC_SCHEMA_HEAD,
    flask_config,
    load_environment,
    runtime_server_config,
    startup_retry_config,
)
from extensions import MIGRATE_OK, csrf, db, lm, migrate

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    )
    METRICS_OK = True
except ImportError:
    METRICS_OK = False

load_environment()
logger = logging.getLogger("ti_control")

# ── PDF (opcional) ────────────────────────────────────────────────────────
try:
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ── QR Code (opcional) ───────────────────────────────────────────────────
try:
    import qrcode
    QR_OK = True
except ImportError:
    QR_OK = False

# ═══════════════════════════════════════════════════════════════════════════
# APP CONFIG
# ═══════════════════════════════════════════════════════════════════════════

app = Flask(__name__)

# ProxyFix: corrige remote_addr quando rodando atrás de nginx/load-balancer
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config.update(flask_config(app.root_path))
_session_secure = app.config["SESSION_COOKIE_SECURE"]

db.init_app(app)
csrf.init_app(app)
lm.init_app(app)
lm.login_view = "login_page"

@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except Exception:
        return []

if migrate is not None:
    migrate.init_app(app, db)

# ═══════════════════════════════════════════════════════════════════════════
# OBSERVABILITY
# ═══════════════════════════════════════════════════════════════════════════

SERVICE_STARTED_AT = datetime.now()

if METRICS_OK:
    HTTP_REQUESTS_TOTAL = Counter(
        "ticontrol_http_requests_total",
        "Total de requisições HTTP recebidas pelo TI Control.",
        ["method", "endpoint", "status"]
    )
    HTTP_REQUEST_DURATION_SECONDS = Histogram(
        "ticontrol_http_request_duration_seconds",
        "Duração das requisições HTTP em segundos.",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
    )
    HTTP_ACTIVE_REQUESTS = Gauge(
        "ticontrol_http_active_requests",
        "Requisições HTTP em processamento no momento."
    )
    HTTP_EXCEPTIONS_TOTAL = Counter(
        "ticontrol_http_exceptions_total",
        "Exceções não tratadas observadas pelo middleware de observabilidade.",
        ["exception_type"]
    )
    APP_INFO = Gauge(
        "ticontrol_app_info",
        "Informações de versão do serviço.",
        ["service", "version", "environment"]
    )
    APP_INFO.labels(
        app.config["SERVICE_NAME"],
        app.config["BUILD_VERSION"],
        app.config["ENVIRONMENT"]
    ).set(1)


def _uptime_seconds():
    return int((datetime.now() - SERVICE_STARTED_AT).total_seconds())


def _endpoint_label():
    return request.endpoint or request.path or "unknown"


@app.before_request
def observability_before_request():
    g.request_started_at = perf_counter()
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    g.metrics_active_request_tracked = False
    if current_user.is_authenticated and getattr(current_user, "status", None) != "Ativo":
        allowed_endpoints = {"do_logout", "login_page", "static", "health_live", "health_ready", "health_startup", "ping"}
        if request.endpoint not in allowed_endpoints:
            if wants_json_response():
                return jsonify({"error": "Conta desativada"}), 403
            return redirect(url_for("do_logout"))
    if request.endpoint not in {"health_live", "health_ready", "health_startup", "metrics", "ping"}:
        _maybe_run_scheduled_backup()
    if METRICS_OK:
        HTTP_ACTIVE_REQUESTS.inc()
        g.metrics_active_request_tracked = True


@app.after_request
def observability_after_request(response):
    response.headers["X-Request-ID"] = getattr(g, "request_id", "")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "font-src 'self'; connect-src 'self'; frame-ancestors 'none';"
    )
    if _session_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if METRICS_OK:
        duration = perf_counter() - getattr(g, "request_started_at", perf_counter())
        endpoint = _endpoint_label()
        HTTP_REQUEST_DURATION_SECONDS.labels(request.method, endpoint).observe(duration)
        HTTP_REQUESTS_TOTAL.labels(request.method, endpoint, str(response.status_code)).inc()
        if getattr(g, "metrics_active_request_tracked", False):
            HTTP_ACTIVE_REQUESTS.dec()
            g.metrics_active_request_tracked = False
    return response


@app.teardown_request
def observability_teardown_request(exc):
    if exc is not None and METRICS_OK:
        HTTP_EXCEPTIONS_TOTAL.labels(exc.__class__.__name__).inc()
    if METRICS_OK and getattr(g, "metrics_active_request_tracked", False):
        HTTP_ACTIVE_REQUESTS.dec()
        g.metrics_active_request_tracked = False


def _database_health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"ok": True, "status": "ok"}
    except Exception as exc:
        db.session.rollback()
        return {"ok": False, "status": "erro", "error": exc.__class__.__name__}


def _service_metadata():
    return {
        "service": app.config["SERVICE_NAME"],
        "version": app.config["BUILD_VERSION"],
        "environment": app.config["ENVIRONMENT"],
        "uptimeSeconds": _uptime_seconds(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MODELS
# ═══════════════════════════════════════════════════════════════════════════

from models import (
    ASSET_STATUS_VALID,
    PERFIL_PERMISSOES,
    Allocation,
    AllocationAsset,
    AllocationItem,
    Asset,
    Attachment,
    AuditCampaign,
    AuditCampaignItem,
    AuditLog,
    Colaborador,
    Devolucao,
    Incident,
    LaudoTecnico,
    License,
    LoginAttempt,
    MaintenanceOrder,
    MaintenancePart,
    PrintJob,
    PrintPrinter,
    Setting,
    Supply,
    SupplyMovement,
    SystemUser,
    TermoAvulso,
)
from services.asset_service import (
    asset_unique_conflicts as service_asset_unique_conflicts,
    next_patrimonio as service_next_patrimonio,
    normalize_asset_category_filter,
    validate_asset_payload as service_validate_asset_payload,
)
from services.backup_service import (
    DEFAULT_BACKUP_CONFIG,
    backup_is_due as service_backup_is_due,
    backup_scheduled_at_for_period as service_backup_scheduled_at_for_period,
    last_day_of_month as service_last_day_of_month,
    normalize_backup_config as service_normalize_backup_config,
    normalize_backup_schedule_time as service_normalize_backup_schedule_time,
    parse_backup_schedule_time as service_parse_backup_schedule_time,
    update_backup_config as service_update_backup_config,
)
from services import attachment_service
from services import authz_service
from services import email_service
from services import settings_service
from services import validation_service
from services.template_renderer import render_text_template as service_render_text_template

# ═══════════════════════════════════════════════════════════════════════════
# HELPERS & DECORATORS
# ═══════════════════════════════════════════════════════════════════════════

def new_id(prefix):
    return prefix + uuid.uuid4().hex[:6].upper()

def days_until(d):
    if not d: return 9999
    try: return (datetime.strptime(str(d), "%Y-%m-%d").date() - date.today()).days
    except: return 9999

def audit(acao, modulo, ref_id="", detalhe=""):
    username = current_user.username if current_user.is_authenticated else "sistema"
    ip = request.remote_addr
    log = AuditLog(usuario=username, acao=acao, modulo=modulo,
                   ref_id=ref_id, detalhe=detalhe[:500], ip=ip)
    db.session.add(log)

def clean_text(value, max_len=None):
    return validation_service.clean_text(value, max_len)


def only_digits(value):
    return validation_service.only_digits(value)


def validate_cpf(value):
    return validation_service.validate_cpf(value)


def cpf_matches(typed, expected):
    return validation_service.cpf_matches(typed, expected)


def parse_int(value, default=0, minimum=None):
    return validation_service.parse_int(value, default, minimum)


def parse_float(value, default=0.0, minimum=None):
    return validation_service.parse_float(value, default, minimum)


def parse_bool(value, default=False):
    return validation_service.parse_bool(value, default)


def json_payload():
    """Retorna payload JSON como dict; payload vazio/inválido vira dict vazio."""
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def wants_json_response():
    return request.path.startswith("/api/") or request.is_json or "application/json" in (request.headers.get("Accept") or "")


def is_safe_redirect_url(target):
    """Permite redirecionar apenas para caminhos locais da própria aplicação."""
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(target)
    if not test_url.netloc:
        return test_url.path.startswith("/")
    return (test_url.scheme, test_url.netloc) == (ref_url.scheme, ref_url.netloc)


def public_audit(acao, modulo, ref_id="", detalhe=""):
    """Registra log originado por QR público, sem depender de sessão autenticada."""
    db.session.add(AuditLog(usuario="qr_publico", acao=acao, modulo=modulo,
                            ref_id=ref_id, detalhe=detalhe[:500], ip=request.remote_addr))


def _asset_unique_conflicts(payload, exclude_id=None):
    return service_asset_unique_conflicts(payload or {}, exclude_id=exclude_id)


def validate_asset_payload(payload, partial=False, exclude_id=None):
    required = _get_setting("campos_ativo_obrigatorios", ["hostname", "fabricante", "modelo", "categoria", "patrimonio"])
    return service_validate_asset_payload(
        payload or {},
        required_fields=required,
        partial=partial,
        exclude_id=exclude_id,
    )


def proximo_patrimonio():
    prefix = ((_get_setting("patrimonio.prefixo") or "TI")).strip().upper()
    return service_next_patrimonio(prefix)


def csv_response(filename, rows, headers):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=filename)


def safe_filename(value):
    return validation_service.safe_filename(value)


def validate_email(value):
    return validation_service.validate_email(value)


def validate_phone(value):
    return validation_service.validate_phone(value)


# ── Rate limiting ─────────────────────────────────────────────────────────────
# Login: persiste no DB — funciona com múltiplos workers Gunicorn
# QR público: in-memory (menos crítico, sem estado de negócio)

_rate_buckets: dict = defaultdict(list)
_RATE_LIMIT = 10
_RATE_WINDOW = 60


def _check_rate_limit(ip: str, bucket: str = "default") -> bool:
    """Rate limiter in-memory (usar apenas para endpoints não críticos)."""
    key = f"{bucket}:{ip}"
    now = _time.time()
    cutoff = now - _RATE_WINDOW
    _rate_buckets[key] = [t for t in _rate_buckets[key] if t > cutoff]
    if len(_rate_buckets[key]) >= _RATE_LIMIT:
        return False
    _rate_buckets[key].append(now)
    return True


def check_public_token_rate_limit(bucket, token=""):
    key = f"{request.remote_addr or 'unknown'}:{clean_text(token, 32)}"
    return _check_rate_limit(key, bucket=bucket)


def _check_login_rate_limit(ip: str) -> bool:
    """Rate limiter via DB — funciona com múltiplos workers. Retorna True se dentro do limite."""
    now = _time.time()
    cutoff = now - _RATE_WINDOW
    try:
        db.session.execute(db.delete(LoginAttempt).where(
            LoginAttempt.ip == ip,
            LoginAttempt.timestamp < cutoff,
        ))
        count = db.session.execute(
            db.select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.ip == ip,
                LoginAttempt.success.is_(False),
                LoginAttempt.timestamp >= cutoff,
            )
        ).scalar() or 0
        if count >= _RATE_LIMIT:
            db.session.rollback()
            return False
        db.session.add(LoginAttempt(ip=ip, timestamp=now, success=False))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        return _check_rate_limit(ip, "login_fallback")


def _record_login_success(ip: str):
    """Marca a última tentativa do IP como bem-sucedida."""
    try:
        attempt = db.session.execute(
            db.select(LoginAttempt)
            .where(LoginAttempt.ip == ip)
            .order_by(LoginAttempt.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if attempt:
            attempt.success = True
        db.session.commit()
    except Exception:
        db.session.rollback()


PERMISSION_MODULE_PREFIXES = authz_service.PERMISSION_MODULE_PREFIXES
ATTACHMENT_MODULE_BY_ENTITY = authz_service.ATTACHMENT_MODULE_BY_ENTITY


def _permission_module_for_request(path: str):
    return authz_service.permission_module_for_path(path)


def _permission_action_for_request(path: str, method: str):
    return authz_service.permission_action_for_request(path, method)


def _configured_profile_permissions():
    try:
        return _get_setting("perfil_permissoes", PERFIL_PERMISSOES)
    except RuntimeError:
        return PERFIL_PERMISSOES


def _profile_permissions(perfil: str):
    return authz_service.profile_permissions(perfil, _configured_profile_permissions())


def _profile_allows(perfil: str, module: str, action: str):
    return authz_service.profile_allows(perfil, module, action, _configured_profile_permissions())


def requires(*perfis):
    """Decorator: exige autenticação e aplica perfil/permissões por módulo."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error":"Não autenticado"}), 401
            allowed, error, status_code, _module, _action = authz_service.authorize_profile(
                current_user.perfil,
                current_user.status,
                request.path,
                request.method,
                perfis,
                _configured_profile_permissions(),
            )
            if not allowed:
                return jsonify({"error": error}), status_code
            return f(*args, **kwargs)
        return decorated
    return decorator

api_auth = requires()  # exige apenas login, sem filtro de perfil


def get_supply_for_update(supply_id):
    return db.session.execute(
        db.select(Supply).where(Supply.id == supply_id).with_for_update()
    ).scalar_one_or_none()


def get_assets_for_update(asset_ids):
    ids = [asset_id for asset_id in (asset_ids or []) if asset_id]
    if not ids:
        return {}
    rows = db.session.execute(
        db.select(Asset)
        .where(Asset.id.in_(ids))
        .order_by(Asset.id)
        .with_for_update()
    ).scalars().all()
    return {asset.id: asset for asset in rows}


def asset_integrity_error_response(exc=None):
    db.session.rollback()
    return jsonify({
        "error": "Identificador de ativo duplicado.",
        "details": [
            "Patrimônio, Service Tag e MAC devem ser únicos quando preenchidos.",
            "Recarregue a tela e tente novamente com identificadores diferentes.",
        ],
    }), 409


def perifericos_do_colaborador(nome_colaborador):
    """Saldo de periféricos (movimentos SAIDA - DEVOLUCAO) por colaborador."""
    movs = db.session.execute(db.select(SupplyMovement).filter_by(colaborador=nome_colaborador)).scalars().all()
    saldo = {}
    for m in movs:
        sid = m.ref_id; qty = abs(m.quantidade or 1)
        if m.tipo == "SAIDA":
            saldo.setdefault(sid, {"nome": m.supply_nome or sid, "qty": 0})
            saldo[sid]["qty"] += qty
        elif m.tipo == "DEVOLUCAO":
            if sid in saldo: saldo[sid]["qty"] = max(0, saldo[sid]["qty"] - qty)
    return [{"supplyId":k,"nome":v["nome"],"quantidade":v["qty"]}
            for k, v in saldo.items() if v["qty"] > 0]

def compute_alerts():
    """Calcula alertas e faz cache no contexto do request (g) para evitar queries duplicadas."""
    if hasattr(g, "_alerts_cache"):
        return g._alerts_cache

    alerts = []
    cfg_dias_gar = 60
    cfg_dias_lic = 60
    s_gar = db.session.get(Setting, "alertas.dias_garantia")
    s_lic = db.session.get(Setting, "alertas.dias_licenca")
    if s_gar: cfg_dias_gar = int(s_gar.value)
    if s_lic: cfg_dias_lic = int(s_lic.value)

    today_iso = date.today().isoformat()
    gar_cutoff = (date.today() + timedelta(days=cfg_dias_gar)).isoformat()
    lic_cutoff = (date.today() + timedelta(days=cfg_dias_lic)).isoformat()
    for a in db.session.execute(
        db.select(Asset)
        .where(Asset.status.notin_(["Baixado","Descartado","Vendido"]))
        .where(Asset.garantia.isnot(None))
        .where(Asset.garantia >= today_iso)
        .where(Asset.garantia <= gar_cutoff)
    ).scalars().all():
        d = days_until(a.garantia)
        alerts.append({"tipo":"garantia","nivel":"danger" if d<=30 else "warning",
                       "titulo":f"Garantia vencendo: {a.hostname}","detalhe":f"{d} dias","ref":a.id})
    for s in db.session.execute(
        db.select(Supply).where(Supply.estoque <= Supply.minimo)
    ).scalars().all():
        if s.estoque == 0:
            alerts.append({"tipo":"estoque","nivel":"danger","titulo":f"Estoque zerado: {s.nome}","detalhe":"Repor imediatamente","ref":s.id})
        else:
            alerts.append({"tipo":"estoque","nivel":"warning","titulo":f"Estoque mínimo: {s.nome}","detalhe":f"{s.estoque} un (mín: {s.minimo})","ref":s.id})
    for l in db.session.execute(
        db.select(License).where(
            db.or_(
                db.and_(License.vencimento.isnot(None), License.vencimento >= today_iso, License.vencimento <= lic_cutoff),
                License.atribuidas > License.total,
            )
        )
    ).scalars().all():
        d = days_until(l.vencimento)
        if 0 <= d <= cfg_dias_lic:
            alerts.append({"tipo":"licenca","nivel":"danger" if d<=30 else "warning",
                           "titulo":f"Licença vencendo: {l.software}","detalhe":f"{d} dias","ref":l.id})
        if l.atribuidas > l.total:
            alerts.append({"tipo":"licenca","nivel":"danger","titulo":f"Licença excedida: {l.software}",
                           "detalhe":f"{l.atribuidas}/{l.total} atribuídas","ref":l.id})
    g._alerts_cache = alerts
    return alerts

@lm.user_loader
def load_user(uid):
    try:
        return db.session.get(SystemUser, uid)
    except Exception:
        return None

@lm.unauthorized_handler
def unauthorized():
    """API requests get JSON 401; browser requests get redirect to login."""
    if request.is_json or request.path.startswith('/api/'):
        return jsonify({"error": "Não autenticado", "redirect": "/login"}), 401
    return redirect(url_for("login_page", next=request.url))


@app.errorhandler(CSRFError)
def handle_csrf_error(err):
    message = "Sua sessão de segurança expirou. Recarregue a página e tente novamente."
    if request.path.startswith("/api/") or wants_json_response():
        return jsonify({"error": message, "code": "csrf_expired", "refresh": True}), 400
    if request.endpoint == "do_login":
        return redirect(url_for("login_page", error=message))
    return render_template_string(
        """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Sessão expirada</title></head>
        <body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#0f1117;color:#f8fafc;display:grid;place-items:center;min-height:100vh;margin:0">
          <main style="max-width:520px;padding:28px;border:1px solid #334155;border-radius:12px;background:#171b24">
            <h1 style="font-size:22px;margin:0 0 10px">Sessão expirada</h1>
            <p style="line-height:1.5;color:#cbd5e1">Sua sessão de segurança expirou. Recarregue a página e tente novamente.</p>
            <a href="/" style="display:inline-block;margin-top:12px;color:#fff;background:#2563eb;padding:10px 14px;border-radius:8px;text-decoration:none">Voltar ao sistema</a>
          </main>
        </body></html>"""
    ), 400


@app.errorhandler(404)
def not_found(err):
    if wants_json_response():
        return jsonify({"error": "Recurso não encontrado"}), 404
    return "Recurso não encontrado", 404

@app.errorhandler(500)
def internal_error(err):
    db.session.rollback()
    if wants_json_response():
        return jsonify({"error": "Erro interno no servidor"}), 500
    return "Erro interno no servidor", 500

def _render_termo_text(template_str: str, ctx: dict) -> str:
    """Renderiza texto com variáveis no formato {chave} e, se usado, {{ chave }}."""
    return service_render_text_template(template_str, ctx)


def _pdf_draw_logo(cv, logo_b64: str, x, y, max_w=None, max_h=None):
    """Desenha logo no PDF se disponível."""
    if not logo_b64:
        return
    try:
        from reportlab.lib.units import cm as _cm
        from reportlab.lib.utils import ImageReader
        _max_w = max_w if max_w is not None else 4 * _cm
        _max_h = max_h if max_h is not None else 2 * _cm
        if "," in logo_b64:
            logo_b64 = logo_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(logo_b64)
        img_reader = ImageReader(io.BytesIO(img_bytes))
        cv.drawImage(img_reader, x, y, width=_max_w, height=_max_h,
                     preserveAspectRatio=True, mask="auto")
    except Exception:
        pass


MANUT_STATUS = ["Aberta","Em análise","Aguardando peça","Em reparo","Concluída","Sem reparo","Cancelada"]
MANUT_TIPO   = ["Corretiva","Preventiva","Melhoria"]
MANUT_ENCERRA = ["Concluída","Sem reparo","Cancelada"]


# ═══════════════════════════════════════════════════════════════════════════
# E-MAIL
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_EMAIL_TEMPLATES = email_service.DEFAULT_EMAIL_TEMPLATES


def _smtp_env_available() -> bool:
    return email_service.smtp_env_available()


def _read_secret_file(path, max_bytes=4096):
    return email_service.read_secret_file(path, max_bytes)


def _smtp_env_password():
    return email_service.smtp_env_password()


def _get_email_config() -> dict:
    return email_service.get_email_config()


def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> dict:
    return email_service.send_email(to, subject, body_html, body_text)


def _get_email_templates():
    return email_service.get_email_templates()


def _normalize_email_templates(value):
    return email_service.normalize_email_templates(value)


def _render_email_template(kind: str, ctx: dict):
    return email_service.render_email_template(kind, ctx)


def send_email_link_assinatura(to: str, colaborador: str, ativo_nome: str, link: str) -> dict:
    return email_service.send_email_link_assinatura(to, colaborador, ativo_nome, link)


def send_email_link_devolucao(to: str, colaborador: str, link: str) -> dict:
    return email_service.send_email_link_devolucao(to, colaborador, link)


def send_email_laudo_rh(to: str, colaborador: str, tecnico: str, link: str) -> dict:
    return email_service.send_email_laudo_rh(to, colaborador, tecnico, link)


def _send_email_async(fn, *args):
    """Dispara envio de e-mail em thread daemon para não bloquear o worker HTTP."""
    from flask import current_app
    _app = current_app._get_current_object()

    def _run():
        with _app.app_context():
            try:
                fn(*args)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()


def send_email_laudo_editado_rh(to: str, colaborador: str, editor: str, motivo: str) -> dict:
    return email_service.send_email_laudo_editado_rh(
        to, colaborador, editor, motivo, get_public_url_for_email()
    )


def send_email_laudo_editado_colab(to: str, colaborador: str, motivo: str) -> dict:
    return email_service.send_email_laudo_editado_colab(
        to, colaborador, motivo, get_public_url_for_email()
    )


def _get_setting(key, default=None):
    return settings_service.get_setting(key, default)

def _set_setting(key, value):
    settings_service.set_setting(key, value)


def get_app_base_url():
    """Retorna a URL base da aplicação para links gerados durante uma request HTTP.

    Prioridade:
    1. Auto-detecção via request atual (honra ProxyFix / X-Forwarded-Host / HTTPS)
    2. Valor salvo no banco — fallback para contextos sem request (e-mails agendados)
    3. Env var APP_BASE_URL (fallback estático final)
    """
    try:
        from flask import request as _req
        if _req and _req.host_url:
            return _req.host_url.rstrip("/")
    except RuntimeError:
        pass  # fora de contexto de request
    saved = _get_setting("app.base_url", "")
    if isinstance(saved, str) and saved.strip():
        return clean_text(saved, 180).rstrip("/")
    return app.config["APP_BASE_URL"]


def get_public_url_for_email():
    """Retorna a URL pública configurada para uso em e-mails e tarefas em segundo plano.

    Usa o valor explicitamente configurado pelo admin (banco/env), nunca o host da
    request atual — assim links em e-mails sempre apontam para o endereço público
    acessível pelos destinatários, independente de onde o admin está navegando.
    """
    saved = _get_setting("app.base_url", "")
    if isinstance(saved, str) and saved.strip():
        return clean_text(saved, 180).rstrip("/")
    return app.config["APP_BASE_URL"]


ASSET_REQUIRED_FIELDS_ALLOWED = {
    "hostname", "ip", "mac", "serviceTag", "os", "fabricante", "modelo",
    "patrimonio", "nf", "categoria", "status", "colaborador", "setor",
    "unidade", "garantia",
}


def _clean_list_setting(values, max_len=80):
    if not isinstance(values, list):
        return None
    cleaned, seen = [], set()
    for raw in values:
        item = clean_text(raw, max_len)
        key = item.casefold()
        if item and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned


def _normalize_empresa_setting(value):
    if not isinstance(value, dict):
        return None, "Dados da empresa precisam ser um objeto."
    current = _get_setting("empresa", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    fields = {
        "nome": 120, "cnpj": 30, "email": 120, "telefone": 40,
        "site": 120, "endereco": 240, "logo_base64": None,
    }
    for key, max_len in fields.items():
        if key in value:
            result[key] = clean_text(value.get(key), max_len)
    err_email = validate_email(result.get("email"))
    if err_email:
        return None, err_email
    return result, None


def _normalize_alertas_setting(value):
    if not isinstance(value, dict):
        return None, "Configurações de alertas precisam ser um objeto."
    current = _get_setting("alertas", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    if "dias_garantia" in value:
        result["dias_garantia"] = parse_int(value.get("dias_garantia"), default=60, minimum=1)
    if "dias_licenca" in value:
        result["dias_licenca"] = parse_int(value.get("dias_licenca"), default=60, minimum=1)
    if "estoque_minimo" in value:
        result["estoque_minimo"] = parse_bool(value.get("estoque_minimo"), default=True)
    if "notif_email" in value:
        result["notif_email"] = parse_bool(value.get("notif_email"), default=False)
    return result, None


def _normalize_regras_usuario_setting(value):
    if not isinstance(value, dict):
        return None, "Regras de operação precisam ser um objeto."
    current = _get_setting("regras_usuario", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    for key in ("exige_termo_alocacao", "permite_alocar_sem_email", "obriga_vinculo_saida"):
        if key in value:
            result[key] = parse_bool(value.get(key), default=bool(result.get(key)))
    if "max_perifericos_por_colab" in value:
        result["max_perifericos_por_colab"] = parse_int(
            value.get("max_perifericos_por_colab"), default=10, minimum=0
        )
    return result, None


def _normalize_campos_ativos_setting(value):
    fields = _clean_list_setting(value, max_len=40)
    if fields is None:
        return None, "Campos obrigatórios de ativo precisam ser uma lista."
    invalid = [field for field in fields if field not in ASSET_REQUIRED_FIELDS_ALLOWED]
    if invalid:
        return None, "Campos obrigatórios inválidos: " + ", ".join(invalid)
    return fields, None


def _normalize_categorias_config_setting(value):
    if not isinstance(value, dict):
        return None, "Configuração de categorias precisa ser um objeto."
    current = _get_setting("categorias_config", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    for raw_cat, cfg in value.items():
        cat = clean_text(raw_cat, 40)
        if not cat:
            continue
        cfg = cfg if isinstance(cfg, dict) else {}
        tipo = clean_text(cfg.get("tipo_alocacao"), 20)
        if tipo not in ("colaborador", "unidade"):
            return None, f"Tipo de alocação inválido para categoria '{cat}'."
        current_cat = result.get(cat) if isinstance(result.get(cat), dict) else {}
        image = cfg.get("image", current_cat.get("image", ""))
        image = clean_text(image, None)
        if image:
            if not image.startswith("data:"):
                return None, f"Imagem da categoria '{cat}' inválida."
            err = _validate_data_image(
                image,
                ASSET_CATEGORY_IMAGE_MIMES,
                ASSET_CATEGORY_IMAGE_MAX_BYTES,
                f"Imagem da categoria '{cat}'",
            )
            if err:
                return None, err
        result[cat] = {"tipo_alocacao": tipo}
        if image:
            result[cat]["image"] = image
    return result, None


def _normalize_unidade_payload(payload, current=None):
    if not isinstance(payload, dict):
        return None, "Dados da unidade precisam ser um objeto."
    current = current if isinstance(current, dict) else {}
    result = dict(current)
    fields = {"nome": 80, "tipo": 40, "cep": 9, "cidade": 80, "estado": 2}
    for key, max_len in fields.items():
        if key in payload or key not in result:
            result[key] = clean_text(payload.get(key, result.get(key, "")), max_len)
    result["estado"] = clean_text(result.get("estado"), 2).upper()
    if "id" in current:
        result["id"] = current["id"]
    if not result.get("nome"):
        return None, "Nome da unidade é obrigatório."
    return result, None


def _normalize_termo_setting(key, value):
    if not isinstance(value, dict):
        return None, "Personalização de termo precisa ser um objeto."
    current = _get_setting(key, {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    text_fields = {"titulo": 160, "preambulo": 3000, "rodape": 500, "declaracao": 1200}
    for field, max_len in text_fields.items():
        if field in value:
            result[field] = clean_text(value.get(field), max_len)
    if "clausulas" in value:
        clauses = _clean_list_setting(value.get("clausulas"), max_len=1000)
        if clauses is None:
            return None, "Cláusulas do termo precisam ser uma lista."
        result["clausulas"] = clauses
    return result, None


def _default_termo_avulso_modelo(tipo):
    tipo = clean_text(tipo, 60) or "Termo"
    tipo_upper = tipo.upper()
    base = {
        "titulo": f"TERMO DE {tipo_upper}",
        "preambulo": (
            "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente "
            "e de acordo com as regras referentes a {tipo}, com validade até {validade}."
        ),
        "clausulas": [
            "O recurso, acesso ou obrigação descrito neste termo é pessoal e intransferível.",
            "O uso deve respeitar as políticas internas, normas de segurança da informação e orientações da área de TI.",
            "O descumprimento das regras poderá resultar em revogação do acesso e medidas administrativas cabíveis.",
        ],
        "rodape": "{empresa} — Termo {tipo} emitido em {data} pelo Sistema de Gestão de TI",
    }
    if tipo.casefold() == "vpn":
        base.update({
            "titulo": "TERMO DE ACESSO VPN / USO REMOTO",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente "
                "das regras para uso de VPN corporativa, com validade até {validade}."
            ),
            "clausulas": [
                "O acesso VPN é pessoal, intransferível e deve ser utilizado apenas para atividades profissionais autorizadas.",
                "É proibido compartilhar credenciais, tokens, certificados ou qualquer meio de autenticação com terceiros.",
                "O colaborador é responsável pelos acessos realizados com suas credenciais e deve comunicar suspeitas de uso indevido imediatamente.",
                "A empresa poderá revogar o acesso a qualquer momento por motivo de segurança, desligamento, mudança de função ou fim da necessidade operacional.",
            ],
        })
    elif tipo.casefold() == "byod":
        base.update({
            "titulo": "TERMO DE USO DE DISPOSITIVO PESSOAL (BYOD)",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, solicito ou autorizo o uso "
                "de dispositivo pessoal para atividades profissionais conforme as condições abaixo."
            ),
            "clausulas": [
                "O dispositivo pessoal deve manter bloqueio de tela, sistema atualizado e recursos mínimos de segurança definidos pela TI.",
                "Dados corporativos acessados no dispositivo não podem ser compartilhados, copiados para locais não autorizados ou expostos a terceiros.",
                "A empresa poderá remover acessos corporativos do dispositivo quando houver desligamento, incidente de segurança ou fim da necessidade de uso.",
            ],
        })
    elif "confidencial" in tipo.casefold():
        base.update({
            "titulo": "TERMO DE CONFIDENCIALIDADE",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro ciência sobre "
                "minhas responsabilidades de sigilo e proteção das informações corporativas."
            ),
            "clausulas": [
                "Informações internas, credenciais, documentos, dados de clientes e dados operacionais devem ser tratados como confidenciais.",
                "É proibida a divulgação, cópia, envio ou armazenamento de informações corporativas em meios não autorizados.",
                "A obrigação de confidencialidade permanece válida mesmo após mudança de função, encerramento de acesso ou desligamento.",
            ],
        })
    return base


def _normalize_termos_avulsos_modelos(value):
    if not isinstance(value, dict):
        return None, "Modelos de termos precisam ser um objeto."
    result = {}
    for raw_tipo, raw_model in value.items():
        tipo = clean_text(raw_tipo, 60)
        if not tipo:
            continue
        if not isinstance(raw_model, dict):
            return None, f"Modelo do termo '{tipo}' precisa ser um objeto."
        base = _default_termo_avulso_modelo(tipo)
        model = dict(base)
        text_fields = {"titulo": 160, "preambulo": 3000, "rodape": 500, "declaracao": 1200}
        for field, max_len in text_fields.items():
            if field in raw_model:
                model[field] = clean_text(raw_model.get(field), max_len)
        if "clausulas" in raw_model:
            clauses = _clean_list_setting(raw_model.get("clausulas"), max_len=1000)
            if clauses is None:
                return None, f"Cláusulas do termo '{tipo}' precisam ser uma lista."
            model["clausulas"] = clauses
        result[tipo] = model
    return result, None


def _get_termos_avulsos_modelos():
    tipos = _get_setting("termos_avulsos_tipos", ["VPN", "BYOD", "Confidencialidade", "Outro"])
    tipos = _clean_list_setting(tipos, 60) or ["VPN", "BYOD", "Confidencialidade", "Outro"]
    saved = _get_setting("termos_avulsos_modelos", {}) or {}
    saved = saved if isinstance(saved, dict) else {}
    result = {}
    for tipo in tipos:
        defaults = _default_termo_avulso_modelo(tipo)
        custom = saved.get(tipo) if isinstance(saved.get(tipo), dict) else {}
        result[tipo] = {**defaults, **custom}
        if not isinstance(result[tipo].get("clausulas"), list):
            result[tipo]["clausulas"] = defaults["clausulas"]
    for tipo, custom in saved.items():
        tipo = clean_text(tipo, 60)
        if tipo and tipo not in result and isinstance(custom, dict):
            defaults = _default_termo_avulso_modelo(tipo)
            result[tipo] = {**defaults, **custom}
            if not isinstance(result[tipo].get("clausulas"), list):
                result[tipo]["clausulas"] = defaults["clausulas"]
    return result


def _get_termo_avulso_modelo(tipo):
    tipo = clean_text(tipo, 60)
    modelos = _get_termos_avulsos_modelos()
    return modelos.get(tipo) or _default_termo_avulso_modelo(tipo)


APARENCIA_LOGO_MAX_BYTES = 300 * 1024
APARENCIA_BG_MAX_BYTES = 8 * 1024 * 1024
APARENCIA_LOGO_MIMES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
APARENCIA_BG_MIMES = {"image/png", "image/jpeg", "image/webp"}
ASSET_CATEGORY_IMAGE_MAX_BYTES = 1024 * 1024
ASSET_CATEGORY_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}


def _validate_data_image(value, allowed_mimes, max_bytes, label):
    if not value:
        return None
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    match = re.match(r"^data:([^;,]+);base64,(.*)$", value, flags=re.S)
    if not match:
        return f"{label} inválida."
    mime = match.group(1).lower()
    if mime not in allowed_mimes:
        return f"{label} deve ser PNG, JPG" + (", WEBP ou SVG." if "image/svg+xml" in allowed_mimes else " ou WEBP.")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except Exception:
        return f"{label} inválida."
    if len(raw) > max_bytes:
        return f"{label} excede o limite de {max_bytes // (1024 * 1024) if max_bytes >= 1024 * 1024 else max_bytes // 1024} {'MB' if max_bytes >= 1024 * 1024 else 'KB'}."
    return None


def _normalize_aparencia_setting(value):
    if not isinstance(value, dict):
        return None, "Configurações de aparência precisam ser um objeto."
    current = _get_setting("aparencia", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    for key, max_len in (("nome_sistema", 80), ("slogan_sistema", 120)):
        if key in value:
            result[key] = clean_text(value.get(key), max_len)
    for key in ("logo_sistema", "favicon", "bg_login"):
        if key in value:
            v = clean_text(value.get(key), None)
            err = _validate_data_image(
                v,
                APARENCIA_BG_MIMES if key == "bg_login" else APARENCIA_LOGO_MIMES,
                APARENCIA_BG_MAX_BYTES if key == "bg_login" else APARENCIA_LOGO_MAX_BYTES,
                "Imagem de fundo" if key == "bg_login" else ("Favicon" if key == "favicon" else "Logo do sistema"),
            )
            if err:
                return None, err
            result[key] = v
    for key in ("cor_primaria", "cor_botao", "cor_hover"):
        if key in value:
            v = clean_text(value.get(key), 20)
            if v and not re.match(r'^#[0-9a-fA-F]{3,8}$', v):
                return None, f"Cor inválida para '{key}': use formato #RRGGBB."
            result[key] = v
    if 'login_box_transparencia' in value:
        try:
            result['login_box_transparencia'] = max(0, min(100, int(value['login_box_transparencia'])))
        except (TypeError, ValueError):
            result['login_box_transparencia'] = 0
    return result, None


def _normalize_patrimonio_prefixo(value):
    v = clean_text(value, 10)
    if not v:
        return None, "Prefixo de patrimônio não pode ser vazio."
    v = re.sub(r"[^A-Za-z0-9]", "", v).upper()
    if not v:
        return None, "Prefixo deve conter letras ou números."
    return v, None


CATEGORIAS_DEFAULT = [
    "Notebook", "Desktop", "Monitor", "Smartphone", "Dock Station",
    "Switch", "Firewall", "Access Point", "Servidor", "Storage",
    "Rack", "Nobreak", "DVR", "NVR", "Câmera IP", "Tablet", "Impressora",
]

CATEGORIAS_INSUMOS_DEFAULT = [
    "Periférico", "Cabo", "Insumo", "Componente",
    "Toner", "Papel", "Bateria", "Adaptador",
]


def _normalize_categorias_list_setting(value):
    if not isinstance(value, list):
        return None, "Categorias deve ser uma lista."
    cats = []
    for v in value:
        c = clean_text(v, 60)
        if c and c not in cats:
            cats.append(c)
    if not cats:
        return None, "A lista de categorias não pode ser vazia."
    return cats, None


def _normalize_categorias_compat_setting(value):
    """Valida mapa {categoria_ativo: [categoria_insumo, ...]}."""
    if not isinstance(value, dict):
        return None, "Compatibilidade deve ser um objeto."
    result = {}
    for raw_cat, supply_cats in value.items():
        cat = clean_text(raw_cat, 60)
        if not cat:
            continue
        if not isinstance(supply_cats, list):
            return None, f"Lista de insumos inválida para categoria '{cat}'."
        result[cat] = [c for c in (clean_text(v, 60) for v in supply_cats) if c]
    return result, None


SETTING_NORMALIZERS = {
    "empresa": _normalize_empresa_setting,
    "alertas": _normalize_alertas_setting,
    "regras_usuario": _normalize_regras_usuario_setting,
    "campos_ativo_obrigatorios": _normalize_campos_ativos_setting,
    "categorias_config": _normalize_categorias_config_setting,
    "categorias": _normalize_categorias_list_setting,
    "categorias_insumos": _normalize_categorias_list_setting,
    "termos_avulsos_tipos": _normalize_categorias_list_setting,
    "termos_avulsos_modelos": _normalize_termos_avulsos_modelos,
    "categorias_compat": _normalize_categorias_compat_setting,
    "aparencia": _normalize_aparencia_setting,
    "patrimonio.prefixo": _normalize_patrimonio_prefixo,
    "termo_emprestimo": lambda v: _normalize_termo_setting("termo_emprestimo", v),
    "termo_vpn": lambda v: _normalize_termo_setting("termo_vpn", v),
}


BACKUP_DIR = os.path.join(app.instance_path, "backups")
BACKUP_FILE_RE = re.compile(r"^backup_ticontrol_\d{8}_\d{6}_(manual|auto|pre_restore)\.json$")
BACKUP_UPLOAD_MAX_BYTES = 20 * 1024 * 1024
_backup_last_check = 0
_backup_lock = threading.Lock()
ATTACHMENT_MAX_BYTES = attachment_service.ATTACHMENT_MAX_BYTES
ATTACHMENT_ALLOWED_EXT = attachment_service.ATTACHMENT_ALLOWED_EXT
ATTACHMENT_MIME_BY_EXT = attachment_service.ATTACHMENT_MIME_BY_EXT

def _parse_backup_schedule_time(value):
    return service_parse_backup_schedule_time(value)


def _normalize_backup_schedule_time(value, default="02:00"):
    return service_normalize_backup_schedule_time(value, default=default)


def _last_day_of_month(year, month):
    return service_last_day_of_month(year, month)


def _backup_scheduled_at_for_period(cfg, now=None):
    return service_backup_scheduled_at_for_period(cfg, now=now)


def _auto_seed_demo_enabled():
    raw = os.environ.get("AUTO_SEED_DEMO")
    if raw is not None:
        return parse_bool(raw, default=False)
    return (
        app.config["ENVIRONMENT"] in ("development", "dev")
        and str(app.config["SQLALCHEMY_DATABASE_URI"]).startswith("sqlite")
    )


def _initial_settings_defaults(empresa=None):
    empresa = empresa if isinstance(empresa, dict) else {}
    company = {
        "nome": clean_text(empresa.get("nome") or "TI Control", 120),
        "cnpj": clean_text(empresa.get("cnpj"), 30),
        "email": clean_text(empresa.get("email"), 120),
        "telefone": clean_text(empresa.get("telefone"), 40),
        "site": clean_text(empresa.get("site"), 120),
        "endereco": clean_text(empresa.get("endereco"), 240),
        "logo_base64": "",
    }
    return {
        "empresa": company,
        "termo_recebimento": {
            "titulo": "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO",
            "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido os seguintes equipamentos de propriedade da empresa:",
            "clausulas": [
                "Comprometo-me a:",
                "  1. Utilizar exclusivamente para fins profissionais;",
                "  2. Zelar pela conservação de todos os itens;",
                "  3. Comunicar ao TI qualquer dano, perda ou furto;",
                "  4. Devolver os equipamentos ao encerramento do vínculo.",
            ],
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "termo_devolucao": {
            "titulo": "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS",
            "preambulo": "Atestamos a devolução dos equipamentos abaixo pelo(a) colaborador(a) {colaborador},\ndo setor {setor}, unidade {unidade}:",
            "clausulas": [],
            "declaracao": "Declaro ter devolvido todos os equipamentos listados acima em plenas condições.",
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "termo_emprestimo": {
            "titulo": "TERMO DE EMPRÉSTIMO DE EQUIPAMENTO",
            "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido em caráter de EMPRÉSTIMO TEMPORÁRIO o equipamento abaixo:",
            "clausulas": [
                "Comprometo-me a:",
                "  1. Utilizar exclusivamente para fins profissionais durante o período de empréstimo;",
                "  2. Zelar pela conservação do equipamento;",
                "  3. Devolver o equipamento na data prevista ou quando solicitado pelo setor de TI;",
                "  4. Comunicar imediatamente ao TI qualquer dano, perda ou furto.",
            ],
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "termo_vpn": {
            "titulo": "TERMO DE ACESSO VPN / USO REMOTO",
            "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro estar ciente das regras de acesso à VPN corporativa:",
            "clausulas": [
                "1. O acesso VPN é pessoal e intransferível;",
                "2. É proibido compartilhar credenciais com terceiros;",
                "3. O colaborador é responsável por todos os acessos realizados com suas credenciais;",
                "4. O uso deve ser restrito a atividades profissionais autorizadas;",
                "5. O descumprimento sujeita o colaborador a medidas disciplinares.",
            ],
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "termos_avulsos_tipos": ["VPN", "BYOD", "Confidencialidade", "Outro"],
        "termos_avulsos_modelos": {
            "VPN": _default_termo_avulso_modelo("VPN"),
            "BYOD": _default_termo_avulso_modelo("BYOD"),
            "Confidencialidade": _default_termo_avulso_modelo("Confidencialidade"),
            "Outro": _default_termo_avulso_modelo("Outro"),
        },
        "email_templates": DEFAULT_EMAIL_TEMPLATES,
        "backup": DEFAULT_BACKUP_CONFIG,
        "setores": ["TI", "Financeiro", "RH", "Vendas", "Marketing", "Operações"],
        "unidades": [],
        "alertas": {"dias_garantia": 60, "dias_licenca": 60, "estoque_minimo": True, "notif_email": False},
        "regras_usuario": {
            "exige_termo_alocacao": True,
            "permite_alocar_sem_email": False,
            "max_perifericos_por_colab": 10,
            "obriga_vinculo_saida": True,
        },
        "campos_ativo_obrigatorios": ["hostname", "fabricante", "modelo", "categoria", "patrimonio"],
        "categorias": CATEGORIAS_DEFAULT,
        "categorias_insumos": CATEGORIAS_INSUMOS_DEFAULT,
        "categorias_compat": {},
        "categorias_config": {
            "Notebook": {"tipo_alocacao": "colaborador"},
            "Desktop": {"tipo_alocacao": "colaborador"},
            "Monitor": {"tipo_alocacao": "colaborador"},
            "Smartphone": {"tipo_alocacao": "colaborador"},
            "Dock Station": {"tipo_alocacao": "colaborador"},
            "Tablet": {"tipo_alocacao": "colaborador"},
            "Impressora": {"tipo_alocacao": "unidade"},
            "Switch": {"tipo_alocacao": "unidade"},
            "Firewall": {"tipo_alocacao": "unidade"},
            "Access Point": {"tipo_alocacao": "unidade"},
            "Servidor": {"tipo_alocacao": "unidade"},
            "Storage": {"tipo_alocacao": "unidade"},
            "Rack": {"tipo_alocacao": "unidade"},
            "Nobreak": {"tipo_alocacao": "unidade"},
            "DVR": {"tipo_alocacao": "unidade"},
            "NVR": {"tipo_alocacao": "unidade"},
            "Câmera IP": {"tipo_alocacao": "unidade"},
        },
        "perfil_permissoes": PERFIL_PERMISSOES,
        "aparencia": {
            "nome_sistema": "TI Control",
            "slogan_sistema": "Gestão de Ativos de TI",
            "cor_primaria": "#2563eb",
            "cor_botao": "#2563eb",
            "cor_hover": "#eff6ff",
            "login_box_transparencia": 0,
        },
    }


def _ensure_initial_settings(empresa=None):
    for key, value in _initial_settings_defaults(empresa).items():
        if db.session.get(Setting, key) is None:
            _set_setting(key, value)


def _get_backup_config():
    saved = _get_setting("backup", {})
    return service_normalize_backup_config(saved)


def _normalize_backup_config(value):
    return service_update_backup_config(_get_backup_config(), value)


def _redact_secret_value(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(token in lowered for token in ("password", "senha", "secret", "token")):
                redacted[key] = "__REDACTED__" if item else ""
            else:
                redacted[key] = _redact_secret_value(item)
        return redacted
    if isinstance(value, list):
        return [_redact_secret_value(item) for item in value]
    return value


def _safe_settings_payload():
    settings = {}
    for setting in db.session.execute(db.select(Setting)).scalars().all():
        value = _get_setting(setting.key)
        lowered = setting.key.lower()
        if any(token in lowered for token in ("password", "senha", "secret", "token")):
            settings[setting.key] = "__REDACTED__" if value else ""
        else:
            settings[setting.key] = _redact_secret_value(value)
    return settings


def _build_backup_payload(generated_by="sistema", include_audit=False):
    return {
        "geradoEm": datetime.now().isoformat(),
        "geradoPor": generated_by,
        "versao": app.config["BUILD_VERSION"],
        "observacao": "system_users e segredos sensíveis são excluídos/redigidos intencionalmente.",
        "assets": [a.to_dict() for a in db.session.execute(db.select(Asset)).scalars().all()],
        "colaboradores": [c.to_dict() for c in db.session.execute(db.select(Colaborador)).scalars().all()],
        "supplies": [s.to_dict() for s in db.session.execute(db.select(Supply)).scalars().all()],
        "supplyMovements": [m.to_dict() for m in db.session.execute(db.select(SupplyMovement)).scalars().all()],
        "allocations": [_allocation_backup_dict(a) for a in db.session.execute(db.select(Allocation)).scalars().all()],
        "licenses": [l.to_dict() for l in db.session.execute(db.select(License)).scalars().all()],
        "incidents": [i.to_dict() for i in db.session.execute(db.select(Incident)).scalars().all()],
        "maintenance": [m.to_dict(include_parts=True) for m in db.session.execute(db.select(MaintenanceOrder)).scalars().all()],
        "devolucoes": [_devolucao_backup_dict(d) for d in db.session.execute(db.select(Devolucao)).scalars().all()],
        "laudosTecnicos": [l.to_dict() for l in db.session.execute(db.select(LaudoTecnico)).scalars().all()],
        "auditCampaigns": [c.to_dict(include_items=True) for c in db.session.execute(db.select(AuditCampaign)).scalars().all()],
        "termosAvulsos": [_termo_avulso_backup_dict(t) for t in db.session.execute(db.select(TermoAvulso)).scalars().all()],
        "attachments": [_attachment_backup_dict(a) for a in db.session.execute(db.select(Attachment)).scalars().all()],
        "settings": _safe_settings_payload(),
        "auditLogs": [a.to_dict() for a in db.session.execute(db.select(AuditLog).order_by(AuditLog.data.desc()).limit(1000)).scalars().all()] if include_audit else [],
    }


def _allocation_backup_dict(allocation):
    data = allocation.to_dict(include_items=True)
    data.pop("signToken", None)
    data.update({
        "assinaturaTiNome": allocation.assinatura_ti_nome,
    })
    if _backup_include_signature_images():
        data.update({
            "assinaturaImg": allocation.assinatura_img,
            "assinaturaTiImg": allocation.assinatura_ti_img,
        })
    return data


def _devolucao_backup_dict(devolucao):
    data = devolucao.to_dict()
    data.pop("signToken", None)
    data.pop("rhToken", None)
    data.update({
        "rhCienciaIp": devolucao.rh_ciencia_ip,
    })
    if _backup_include_signature_images():
        data["assinaturaImg"] = devolucao.assinatura_img
    return data


def _attachment_backup_dict(attachment):
    data = attachment.to_dict()
    data["storedName"] = attachment.stored_name
    return data


def _termo_avulso_backup_dict(termo):
    data = termo.to_dict()
    data.pop("signToken", None)
    data.pop("packageToken", None)
    data.pop("packageTokenExpiry", None)
    data.update({
        "detalhesRaw": termo.detalhes,
    })
    if _backup_include_signature_images():
        data["assinaturaImg"] = termo.assinatura_img
    return data


def _backup_include_signature_images():
    return parse_bool(os.environ.get("BACKUP_INCLUDE_SIGNATURE_IMAGES"), default=False)


def _backup_bytes(generated_by="sistema", include_audit=False):
    payload = _build_backup_payload(generated_by=generated_by, include_audit=include_audit)
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return raw, hashlib.sha256(raw).hexdigest()


def _backup_file_path(filename):
    filename = os.path.basename(filename or "")
    if not BACKUP_FILE_RE.match(filename):
        return None
    path = os.path.abspath(os.path.join(BACKUP_DIR, filename))
    base = os.path.abspath(BACKUP_DIR)
    if not path.startswith(base + os.sep):
        return None
    return path


def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
    try:
        os.chmod(BACKUP_DIR, 0o700)
    except OSError:
        pass


def _list_backup_files():
    _ensure_backup_dir()
    files = []
    for filename in sorted(os.listdir(BACKUP_DIR), reverse=True):
        path = _backup_file_path(filename)
        if not path or not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            checksum = hashlib.sha256(fh.read()).hexdigest()
        stat = os.stat(path)
        files.append({
            "filename": filename,
            "size": stat.st_size,
            "createdAt": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "sha256": checksum,
        })
    return files


def _prune_backups(retention):
    files = _list_backup_files()
    for item in files[retention:]:
        path = _backup_file_path(item["filename"])
        if path and os.path.exists(path):
            os.remove(path)


def _write_backup_file(kind="manual", generated_by="sistema"):
    cfg = _get_backup_config()
    _ensure_backup_dir()
    raw, checksum = _backup_bytes(generated_by=generated_by, include_audit=cfg["include_audit"])
    filename = f"backup_ticontrol_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{kind}.json"
    path = _backup_file_path(filename)
    if not path:
        raise RuntimeError("Nome de backup inválido.")
    with open(path, "wb") as fh:
        fh.write(raw)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    cfg.update({
        "last_run": datetime.now().isoformat(),
        "last_file": filename,
        "last_status": "OK",
        "last_error": "",
    })
    _set_setting("backup", cfg)
    _prune_backups(cfg["retention"])
    return {"filename": filename, "size": len(raw), "sha256": checksum, "createdAt": cfg["last_run"]}


def _backup_is_due(cfg):
    return service_backup_is_due(cfg)


def _run_scheduled_backup_once():
    try:
        cfg = _get_backup_config()
        if not _backup_is_due(cfg):
            return
        result = _write_backup_file("auto", generated_by="rotina_automatica")
        audit("BACKUP_AUTO", "sistema", "", f"Backup automático gerado: {result['filename']}")
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        cfg = _get_backup_config()
        cfg.update({"last_status": "ERRO", "last_error": clean_text(str(exc), 300)})
        _set_setting("backup", cfg)
        db.session.commit()
        logger.exception("Falha na rotina automática de backup")


def _scheduled_backup_worker():
    with app.app_context():
        try:
            _run_scheduled_backup_once()
        finally:
            db.session.remove()
            _backup_lock.release()


def _maybe_run_scheduled_backup():
    global _backup_last_check
    now = _time.time()
    if now - _backup_last_check < 300:
        return
    _backup_last_check = now
    if not _backup_lock.acquire(blocking=False):
        return
    threading.Thread(target=_scheduled_backup_worker, name="ticontrol-backup", daemon=True).start()


_BACKUP_REQUIRED_LISTS = (
    "assets", "colaboradores", "supplies", "supplyMovements",
    "allocations", "licenses", "incidents", "maintenance",
    "devolucoes", "attachments",
)

_BACKUP_OPTIONAL_LISTS = ("laudosTecnicos", "auditCampaigns", "termosAvulsos", "auditLogs")


def _parse_backup_dt(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None


def _validate_backup_payload(payload):
    errors, warnings, summary = [], [], {}
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["Arquivo não é um objeto JSON válido."],
                "warnings": [], "summary": {}, "geradoEm": None, "geradoPor": None, "versao": None}
    for key in _BACKUP_REQUIRED_LISTS:
        val = payload.get(key)
        if val is None:
            errors.append(f"Chave obrigatória ausente: '{key}'.")
        elif not isinstance(val, list):
            errors.append(f"'{key}' deve ser uma lista.")
        else:
            summary[key] = len(val)
    for key in _BACKUP_OPTIONAL_LISTS:
        val = payload.get(key, [])
        if val is not None and not isinstance(val, list):
            errors.append(f"'{key}' deve ser uma lista.")
        elif isinstance(val, list):
            summary[key] = len(val)
    settings_val = payload.get("settings")
    if settings_val is None:
        errors.append("Chave obrigatória ausente: 'settings'.")
    elif not isinstance(settings_val, dict):
        errors.append("'settings' deve ser um objeto.")
    else:
        summary["settings"] = len(settings_val)
    if "geradoEm" not in payload:
        warnings.append("Metadado 'geradoEm' ausente — data do backup desconhecida.")
    if "versao" not in payload:
        warnings.append("Metadado 'versao' ausente — versão desconhecida.")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings, "summary": summary,
                "geradoEm": payload.get("geradoEm"), "geradoPor": payload.get("geradoPor"),
                "versao": payload.get("versao")}
    # Deep checks
    asset_ids = set()
    for a in payload.get("assets", []):
        if not isinstance(a, dict) or not a.get("id"):
            errors.append("Um ou mais ativos sem campo 'id'.")
            break
        asset_ids.add(a["id"])
    for c in payload.get("colaboradores", []):
        if not isinstance(c, dict) or not c.get("id"):
            errors.append("Um ou mais colaboradores sem campo 'id'.")
            break
    orphan_allocs = sum(1 for al in payload.get("allocations", [])
                        if isinstance(al, dict) and al.get("ativo") and al["ativo"] not in asset_ids)
    if orphan_allocs:
        warnings.append(f"{orphan_allocs} alocação(ões) referencia(m) ativos não encontrados no backup.")
    orphan_maint = sum(1 for m in payload.get("maintenance", [])
                       if isinstance(m, dict) and m.get("assetId") and m["assetId"] not in asset_ids)
    if orphan_maint:
        warnings.append(f"{orphan_maint} ordem(ns) de manutenção referencia(m) ativos não encontrados no backup.")
    legacy_token_count = 0
    for collection, keys in (
        ("allocations", ("signToken",)),
        ("devolucoes", ("signToken", "rhToken")),
        ("termosAvulsos", ("signToken", "packageToken")),
    ):
        for item in payload.get(collection, []):
            if isinstance(item, dict) and any(item.get(key) for key in keys):
                legacy_token_count += 1
    if legacy_token_count:
        warnings.append(
            f"{legacy_token_count} registro(s) contêm tokens legados; eles serão descartados na restauração."
        )
    if payload.get("attachments"):
        warnings.append("Metadados de anexos serão restaurados, mas os arquivos físicos NÃO são restaurados via JSON (ficam em instance/attachments).")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
        "geradoEm": payload.get("geradoEm"),
        "geradoPor": payload.get("geradoPor"),
        "versao": payload.get("versao"),
    }


def _restore_from_payload(payload, restored_by="sistema"):
    try:
        _write_backup_file("pre_restore", generated_by=f"pre_restore:{restored_by}")
    except Exception as exc:
        logger.warning("Backup pré-restauração falhou: %s", exc)

    def flush_stage(stage):
        try:
            db.session.flush()
        except Exception as exc:
            logger.exception("Falha na etapa de restauração: %s", stage)
            raise RuntimeError(f"Falha ao restaurar {stage} ({exc.__class__.__name__}).") from exc

    # Deleção em ordem segura de FK. O flush separa definitivamente os
    # registros antigos dos novos objetos que reutilizam as mesmas chaves.
    for model in (AuditCampaignItem, AuditCampaign, LaudoTecnico, TermoAvulso, MaintenancePart,
                  AllocationItem, AllocationAsset, Devolucao, Allocation, Incident, MaintenanceOrder,
                  Attachment, SupplyMovement, Supply, License, Asset, Colaborador):
        db.session.execute(db.delete(model).execution_options(synchronize_session=False))
    flush_stage("limpeza dos dados atuais")
    db.session.expunge_all()

    stats = {}

    colabs = [c for c in payload.get("colaboradores", []) if isinstance(c, dict) and c.get("id")]
    for c in colabs:
        db.session.add(Colaborador(
            id=c["id"], nome=c.get("nome", ""), email=c.get("email"),
            telefone=c.get("telefone"), cpf=c.get("cpf"), cargo=c.get("cargo"), setor=c.get("setor"),
            unidade=c.get("unidade"), status=c.get("status", "Ativo"),
            matricula=c.get("matricula"), data_admissao=c.get("dataAdmissao"),
            data_cadastro=c.get("dataCadastro"), data_desligamento=c.get("dataDesligamento"),
            observacao=c.get("observacao", ""),
        ))
    stats["colaboradores"] = len(colabs)

    assets = [a for a in payload.get("assets", []) if isinstance(a, dict) and a.get("id")]
    for a in assets:
        db.session.add(Asset(
            id=a["id"], hostname=a.get("hostname"), ip=a.get("ip", "DHCP"),
            mac=a.get("mac"), service_tag=a.get("serviceTag"),
            os=a.get("os"), fabricante=a.get("fabricante"), modelo=a.get("modelo"),
            patrimonio=a.get("patrimonio"), nf=a.get("nf"),
            categoria=a.get("categoria"), status=a.get("status", "Disponível"),
            colaborador=a.get("colaborador", ""), setor=a.get("setor", ""),
            unidade=a.get("unidade", ""), garantia=a.get("garantia"),
        ))
    stats["assets"] = len(assets)

    supplies = [s for s in payload.get("supplies", []) if isinstance(s, dict) and s.get("id")]
    for s in supplies:
        db.session.add(Supply(
            id=s["id"], nome=s.get("nome", ""), categoria=s.get("categoria"),
            unidade=s.get("unidade"), estoque=s.get("estoque", 0),
            minimo=s.get("minimo", 0), preco=s.get("preco", 0.0),
        ))
    stats["supplies"] = len(supplies)

    movements = [m for m in payload.get("supplyMovements", []) if isinstance(m, dict) and m.get("id")]
    for m in movements:
        db.session.add(SupplyMovement(
            id=m["id"], tipo=m.get("tipo"), ref_id=m.get("refId"),
            supply_nome=m.get("supplyNome"), descricao=m.get("descricao"),
            quantidade=m.get("quantidade"), colaborador=m.get("colaborador", ""),
            ativo_id=m.get("ativoId", ""), motivo=m.get("motivo", ""),
            data=_parse_backup_dt(m.get("data")),
        ))
    stats["supplyMovements"] = len(movements)

    licenses = [l for l in payload.get("licenses", []) if isinstance(l, dict) and l.get("id")]
    for l in licenses:
        db.session.add(License(
            id=l["id"], software=l.get("software"), fornecedor=l.get("fornecedor"),
            total=l.get("total", 0), atribuidas=l.get("atribuidas", 0),
            vencimento=l.get("vencimento"), custo=l.get("custo", 0.0),
            tipo=l.get("tipo"), attachments=l.get("attachments", []),
        ))
    stats["licenses"] = len(licenses)

    incidents = [i for i in payload.get("incidents", []) if isinstance(i, dict) and i.get("id")]
    for i in incidents:
        db.session.add(Incident(
            id=i["id"], ref_id=i.get("refId"), tipo=i.get("tipo"),
            descricao=i.get("descricao"), status=i.get("status", "Aberto"),
            data=_parse_backup_dt(i.get("data")),
        ))
    stats["incidents"] = len(incidents)

    # PostgreSQL valida as FKs durante cada flush. Pais precisam existir antes
    # de ordens, alocações e demais entidades dependentes.
    flush_stage("entidades principais")

    maintenances = [m for m in payload.get("maintenance", []) if isinstance(m, dict) and m.get("id")]
    maintenance_parts = []
    for mo in maintenances:
        db.session.add(MaintenanceOrder(
            id=mo["id"], asset_id=mo.get("assetId"), asset_nome=mo.get("assetNome"),
            tipo=mo.get("tipo", "Corretiva"), status=mo.get("status", "Aberta"),
            status_anterior=mo.get("statusAnterior", "Disponível"),
            descricao_defeito=mo.get("descricaoDefeito"), diagnostico=mo.get("diagnostico"),
            tecnico=mo.get("tecnico"), data_abertura=mo.get("dataAbertura"),
            data_conclusao=mo.get("dataConclusao"), custo_total=mo.get("custoTotal", 0.0),
            observacao=mo.get("observacao"), attachments=mo.get("attachments", []),
        ))
        for p in (mo.get("pecas") or []):
            if not isinstance(p, dict) or not p.get("id"):
                continue
            maintenance_parts.append(MaintenancePart(
                id=p["id"], maintenance_id=mo["id"],
                supply_id=p.get("supplyId"), supply_nome=p.get("nome"),
                quantidade=p.get("quantidade", 1), custo_unitario=p.get("custoUnitario", 0.0),
            ))
    stats["maintenance"] = len(maintenances)
    flush_stage("ordens de manutenção")
    db.session.add_all(maintenance_parts)
    flush_stage("peças de manutenção")

    allocations = [a for a in payload.get("allocations", []) if isinstance(a, dict) and a.get("id")]
    allocation_items = []
    allocation_assets = []
    for al in allocations:
        db.session.add(Allocation(
            id=al["id"], ativo_id=al.get("ativo"), ativo_nome=al.get("ativoNome"),
            colaborador=al.get("colaborador"), setor=al.get("setor"),
            unidade=al.get("unidade"), email=al.get("email"),
            data_aloc=al.get("dataAloc"), data_encerramento=al.get("dataEncerramento"),
            motivo=al.get("motivo", "Uso contínuo"), status=al.get("status", "Ativo"),
            tipo=al.get("tipo", "Responsabilidade"),
            data_devolucao_prevista=al.get("dataDevolucaoPrevista"),
            termo=al.get("termo"), termo_status=al.get("termoStatus", "Pendente"),
            data_assinatura=_parse_backup_dt(al.get("dataAssinatura")),
            assinatura_ip=al.get("assinaturaIp"),
            assinatura_img=al.get("assinaturaImg"),
            sign_token=None,
            sign_token_expiry=None,
            assinatura_ti_img=al.get("assinaturaTiImg"),
            assinatura_ti_nome=al.get("assinaturaTiNome"),
            data_assinatura_ti=_parse_backup_dt(al.get("dataAssinaturaTi")),
        ))
        for item in (al.get("perifericos") or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            allocation_items.append(AllocationItem(
                id=item["id"], allocation_id=al["id"],
                supply_id=item.get("supplyId"), supply_nome=item.get("nome"),
                quantidade=item.get("quantidade", 1),
            ))
        ativos_al = al.get("ativos") or []
        if not ativos_al and al.get("ativo"):
            ativos_al = [{"id": al.get("ativo"), "nome": al.get("ativoNome")}]
        for idx, item in enumerate(ativos_al):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            allocation_assets.append(AllocationAsset(
                id=item.get("itemId") or new_id("AA"),
                allocation_id=al["id"],
                asset_id=item.get("id"),
                asset_nome=item.get("nome") or item.get("assetNome") or item.get("id"),
                categoria=item.get("categoria"),
                patrimonio=item.get("patrimonio"),
                service_tag=item.get("serviceTag"),
            ))
    stats["allocations"] = len(allocations)
    flush_stage("alocações")
    db.session.add_all(allocation_items)
    db.session.add_all(allocation_assets)
    flush_stage("itens das alocações")

    devolucoes = [d for d in payload.get("devolucoes", []) if isinstance(d, dict) and d.get("id")]
    for d in devolucoes:
        ativos = d.get("ativosDevolvidos", [])
        peris = d.get("perifericosDevolvidos", [])
        db.session.add(Devolucao(
            id=d["id"], colaborador_id=d.get("colaboradorId"),
            colaborador=d.get("colaborador", ""), setor=d.get("setor", ""),
            unidade=d.get("unidade", ""), data_devolucao=d.get("dataDevolucao"),
            data_assinatura=_parse_backup_dt(d.get("dataAssinatura")),
            assinatura_img=d.get("assinaturaImg"),
            assinatura_ip=d.get("assinaturaIp"),
            sign_token=None,
            sign_token_expiry=None,
            status=d.get("status", "Pendente"),
            ativos_devolvidos=json.dumps(ativos if isinstance(ativos, list) else []),
            perifericos_devolvidos=json.dumps(peris if isinstance(peris, list) else []),
            laudo_status=d.get("laudoStatus", "Aguardando Laudo"),
            rh_token=None,
            rh_token_expiry=None,
            rh_email=d.get("rhEmail"),
            rh_ciencia_ip=d.get("rhCienciaIp"),
            rh_data_ciencia=_parse_backup_dt(d.get("rhDataCiencia")),
            cobranca_aplicada=d.get("cobrancaAplicada"),
            cobranca_valor=d.get("cobrancaValor", 0.0),
            cobranca_obs=d.get("cobrancaObs", ""),
        ))
    stats["devolucoes"] = len(devolucoes)
    flush_stage("devoluções")

    laudos = [l for l in payload.get("laudosTecnicos", []) if isinstance(l, dict) and l.get("id")]
    for l in laudos:
        avaliacao = l.get("avaliacaoItens", [])
        db.session.add(LaudoTecnico(
            id=l["id"], devolucao_id=l.get("devolucaoId"),
            tecnico=l.get("tecnico", ""),
            avaliacao_itens=json.dumps(avaliacao if isinstance(avaliacao, list) else []),
            observacao_geral=l.get("observacaoGeral", ""),
            tem_cobranca=bool(l.get("temCobranca")),
            valor_cobranca=l.get("valorCobranca", 0.0),
            data_avaliacao=_parse_backup_dt(l.get("dataAvaliacao")),
            editado_em=_parse_backup_dt(l.get("editadoEm")),
            editado_por=l.get("editadoPor"),
            motivo_edicao=l.get("motivoEdicao"),
        ))
    stats["laudosTecnicos"] = len(laudos)
    flush_stage("laudos técnicos")

    campaigns = [c for c in payload.get("auditCampaigns", []) if isinstance(c, dict) and c.get("id")]
    campaign_items = []
    for campaign in campaigns:
        db.session.add(AuditCampaign(
            id=campaign["id"], nome=campaign.get("nome", ""),
            unidade=campaign.get("unidade", ""), setor=campaign.get("setor", ""),
            status=campaign.get("status", "Aberta"),
            data_inicio=campaign.get("dataInicio"),
            data_fim=campaign.get("dataFim"),
            criado_por=campaign.get("criadoPor", ""),
            criado_em=_parse_backup_dt(campaign.get("criadoEm")),
            observacao=campaign.get("observacao", ""),
        ))
        for item in (campaign.get("items") or []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            campaign_items.append(AuditCampaignItem(
                id=item["id"], campaign_id=campaign["id"],
                asset_id=item.get("assetId"), asset_nome=item.get("assetNome"),
                patrimonio=item.get("patrimonio"), service_tag=item.get("serviceTag"),
                expected_unidade=item.get("expectedUnidade", ""),
                expected_setor=item.get("expectedSetor", ""),
                expected_colaborador=item.get("expectedColaborador", ""),
                observed_unidade=item.get("observedUnidade", ""),
                observed_setor=item.get("observedSetor", ""),
                observed_local=item.get("observedLocal", ""),
                observed_responsavel=item.get("observedResponsavel", ""),
                status=item.get("status", "Pendente"),
                divergencia=item.get("divergencia", ""),
                observacao=item.get("observacao", ""),
                auditado_por=item.get("auditadoPor", ""),
                auditado_em=_parse_backup_dt(item.get("auditadoEm")),
            ))
    stats["auditCampaigns"] = len(campaigns)
    flush_stage("campanhas de auditoria")
    db.session.add_all(campaign_items)
    flush_stage("itens das campanhas de auditoria")

    termos_avulsos = [t for t in payload.get("termosAvulsos", []) if isinstance(t, dict) and t.get("id")]
    for t in termos_avulsos:
        detalhes = t.get("detalhesRaw")
        if detalhes is None:
            raw_detalhes = t.get("detalhes", {})
            detalhes = json.dumps(raw_detalhes if isinstance(raw_detalhes, dict) else {})
        db.session.add(TermoAvulso(
            id=t["id"], tipo=t.get("tipo"), colaborador=t.get("colaborador"),
            setor=t.get("setor"), unidade=t.get("unidade"), email=t.get("email"),
            detalhes=detalhes, validade=t.get("validade"),
            status=t.get("status", "Pendente"),
            sign_token=None,
            sign_token_expiry=None,
            package_id=t.get("packageId"),
            package_token=None,
            package_token_expiry=None,
            assinatura_img=t.get("assinaturaImg"),
            assinatura_ip=t.get("assinaturaIp"),
            data_assinatura=_parse_backup_dt(t.get("dataAssinatura")),
            created_at=_parse_backup_dt(t.get("createdAt")),
            created_by=t.get("createdBy"),
        ))
    stats["termosAvulsos"] = len(termos_avulsos)

    att_list = [a for a in payload.get("attachments", []) if isinstance(a, dict) and a.get("id")]
    for a in att_list:
        db.session.add(Attachment(
            id=a["id"], entity_type=a.get("entityType", ""), entity_id=a.get("entityId", ""),
            original_name=a.get("originalName", "arquivo"), stored_name=a.get("storedName") or a.get("id", a.get("originalName", "arquivo")),
            content_type=a.get("contentType", "application/octet-stream"),
            size=a.get("size", 0), category=a.get("category", "Documento"),
            description=a.get("description", ""), uploaded_by=a.get("uploadedBy", ""),
            uploaded_at=_parse_backup_dt(a.get("uploadedAt")),
        ))
    stats["attachments"] = len(att_list)
    flush_stage("dados complementares")

    settings_payload = payload.get("settings", {})
    count = 0
    if isinstance(settings_payload, dict):
        for key, value in settings_payload.items():
            if value == "__REDACTED__":
                continue
            if isinstance(value, str) and "__REDACTED__" in value:
                continue
            _set_setting(key, value)
            count += 1
    stats["settings"] = count

    return stats


def _attachment_entity_exists(entity_type, entity_id):
    return attachment_service.attachment_entity_exists(entity_type, entity_id)


def _attachment_path(stored_name):
    return attachment_service.attachment_path(stored_name)


def _attachment_ext(filename):
    return attachment_service.attachment_ext(filename)


def _attachment_magic_matches(ext, data):
    return attachment_service.attachment_magic_matches(ext, data)


def _create_attachment_record(entity_type, entity_id, file, category="Documento", description=""):
    return attachment_service.create_attachment_record(
        entity_type, entity_id, file, category, description
    )


# ═══════════════════════════════════════════════════════════════════════════
# SEED DATA
# ═══════════════════════════════════════════════════════════════════════════

def seed():
    if db.session.execute(db.select(SystemUser)).scalars().first() is not None:
        return  # já populado

    # Sistema users
    # IDs FIXOS — garante que sessões existentes continuem válidas após reinício
    users = [
        ("SU001","admin.ti","Juliana Ramos","juliana.ramos@empresa.com","Administrador","admin123"),
        ("SU002","marcos.souza","Marcos Souza","marcos.souza@empresa.com","Técnico TI","tecnico123"),
        ("SU003","roberto.faria","Roberto Faria","roberto.faria@empresa.com","Gestor","gestor123"),
        ("SU004","viewer","Visualizador Geral","viewer@empresa.com","Visualizador","viewer123"),
    ]
    for uid,uname,nome,email,perfil,pwd in users:
        u = SystemUser(id=uid,username=uname,nome=nome,email=email,
                       perfil=perfil,status="Ativo",criado_em=date.today())
        u.set_senha(pwd); db.session.add(u)

    # Colaboradores
    colabs_data = [
        ("Ana Costa","ana.costa@empresa.com","(11)98800-0001","Analista Financeira","Financeiro","Sede SP","Ativo","MAT-2022-001","2022-04-01"),
        ("Carlos Melo","carlos.melo@empresa.com","(11)98800-0002","Analista de RH","RH","Sede SP","Ativo","MAT-2021-007","2021-08-15"),
        ("Pedro Lins","pedro.lins@empresa.com","(21)97700-0003","Executivo de Vendas","Vendas","Filial RJ","Ativo","MAT-2023-014","2023-02-20"),
        ("Juliana Ramos","juliana.ramos@empresa.com","(11)98800-0004","Gerente de TI","TI","Sede SP","Ativo","MAT-2020-003","2020-06-01"),
        ("Marcos Souza","marcos.souza@empresa.com","(11)98800-0005","Desenvolvedor Sênior","TI","Sede SP","Ativo","MAT-2021-019","2021-11-08"),
        ("Fernanda Torres","fernanda.torres@empresa.com","(11)98800-0006","Designer Gráfica","Marketing","Sede SP","Férias","MAT-2022-031","2022-09-12"),
        ("Roberto Faria","roberto.faria@empresa.com","(11)98800-0007","Controller Financeiro","Financeiro","Sede SP","Ativo","MAT-2019-005","2019-03-04"),
        ("Camila Dias","camila.dias@empresa.com","(31)96600-0008","Analista de Suporte","TI","Filial BH","Afastado","MAT-2023-042","2023-07-17"),
    ]
    colab_ids = {}
    for nome,email,tel,cargo,setor,unid,status,mat,adm in colabs_data:
        c = Colaborador(id=new_id("C"),nome=nome,email=email,telefone=tel,cargo=cargo,setor=setor,
                        unidade=unid,status=status,matricula=mat,data_admissao=adm,
                        data_cadastro="2024-01-01",observacao=""); db.session.add(c)
        colab_ids[nome] = c.id

    # Assets
    assets_data = [
        ("A001","NB-FINANCEIRO-01","192.168.1.101","00:1A:2B:3C:4D:5E","H3X92T3","Windows 11 Pro","Dell","Latitude 5540","PAT-2024-001","Notebook","Alocado","Ana Costa","Financeiro","Sede SP","2026-08-15","NF-2024-1234"),
        ("A002","DESK-RH-03","192.168.1.45","00:1B:3C:4D:5E:6F","J7K31P9","Windows 10 Pro","Lenovo","ThinkCentre M70q","PAT-2024-002","Desktop","Alocado","Carlos Melo","RH","Sede SP","2025-06-20","NF-2024-1235"),
        ("A003","MON-TI-01","DHCP","N/A","ZP901KL","N/A","LG","27UL500","PAT-2024-003","Monitor","Disponível","","","Almoxarifado","2026-12-01","NF-2024-1236"),
        ("A004","SW-ANDAR2-01","192.168.10.1","AA:BB:CC:DD:EE:FF","SW445XP","Cisco IOS 15.2","Cisco","Catalyst 2960-X","PAT-2023-041","Switch","Ativo","","TI","Sede SP","2025-03-10","NF-2023-0887"),
        ("A005","NB-VENDAS-07","DHCP","11:22:33:44:55:66","VK219MX","Windows 11 Home","HP","EliteBook 840 G9","PAT-2024-005","Notebook","Alocado","Pedro Lins","Vendas","Filial RJ","2027-01-30","NF-2024-2201"),
        ("A006","FW-SEDE-01","10.0.0.1","FF:EE:DD:CC:BB:AA","FW990ZZ","pfSense 2.7","Netgate","6100","PAT-2023-010","Firewall","Ativo","","TI","Sede SP","2025-05-15","NF-2023-0312"),
    ]
    for (id_,hn,ip,mac,st,os_,fab,mod,pat,cat,status,colab,setor,unid,gar,nf) in assets_data:
        a=Asset(id=id_,hostname=hn,ip=ip,mac=mac,service_tag=st,os=os_,fabricante=fab,
                modelo=mod,patrimonio=pat,categoria=cat,status=status,colaborador=colab,
                setor=setor,unidade=unid,garantia=gar,nf=nf); db.session.add(a)

    # Supplies
    supplies_data = [
        ("Mouse USB Logitech M90","Periférico","Sede SP",8,5,45.90),
        ("Teclado USB Multilaser","Periférico","Sede SP",4,5,65.00),
        ("Fone Headset Intelbras","Periférico","Sede SP",2,3,89.90),
        ("Cabo HDMI 2m","Cabo","Almoxarifado",15,10,22.50),
        ("Toner HP LaserJet CF217A","Insumo","Sede SP",1,2,145.00),
        ("SSD 480GB SATA","Componente","Almoxarifado",3,2,219.90),
        ("Memória RAM 8GB DDR4","Componente","Almoxarifado",5,4,159.00),
        ("Mousepad Grande","Periférico","Filial RJ",0,3,35.00),
    ]
    SUPPLY_IDS = ["S001","S002","S003","S004","S005","S006","S007","S008"]
    supply_ids = []
    for idx,(nome,cat,unid,est,mn,preco) in enumerate(supplies_data):
        s=Supply(id=SUPPLY_IDS[idx],nome=nome,categoria=cat,unidade=unid,estoque=est,minimo=mn,preco=preco)
        db.session.add(s); supply_ids.append(s)

    # Allocations with items
    db.session.flush()  # get IDs

    for aid_str, asset_hn, colab_nome, setor_, unidade_, email_, data_, perifs in [
        (None,"NB-FINANCEIRO-01","Ana Costa","Financeiro","Sede SP","ana.costa@empresa.com","2024-03-15",[("Mouse USB Logitech M90",1),("Teclado USB Multilaser",1),("Fone Headset Intelbras",1)]),
        (None,"DESK-RH-03","Carlos Melo","RH","Sede SP","carlos.melo@empresa.com","2024-01-10",[("Mouse USB Logitech M90",1),("Teclado USB Multilaser",1)]),
        (None,"NB-VENDAS-07","Pedro Lins","Vendas","Filial RJ","pedro.lins@empresa.com","2024-07-22",[]),
    ]:
        a = db.session.execute(db.select(Asset).filter_by(hostname=asset_hn)).scalar_one_or_none()
        if not a: continue
        al_id = new_id("AL")
        al = Allocation(id=al_id, ativo_id=a.id,
                        ativo_nome=f"{a.hostname} ({a.fabricante} {a.modelo})",
                        colaborador=colab_nome, setor=setor_, unidade=unidade_, email=email_,
                        data_aloc=data_, status="Ativo",
                        termo=f"TERMO-{al_id}", termo_status="Assinado",
                        data_assinatura=datetime.now())
        db.session.add(al)
        for s_nome, qty in perifs:
            s = db.session.execute(db.select(Supply).filter_by(nome=s_nome)).scalar_one_or_none()
            if s:
                db.session.add(AllocationItem(id=new_id("AI"), allocation_id=al_id,
                               supply_id=s.id, supply_nome=s.nome, quantidade=qty))
                s.estoque = max(0, (s.estoque or 0) - qty)
                # Movimentação de saída retroativa
                db.session.add(SupplyMovement(id=new_id("MOV"), tipo="SAIDA", ref_id=s.id,
                               supply_nome=s.nome,
                               descricao=f"Alocação {al_id} — {colab_nome}: {s.nome} x{qty}",
                               quantidade=-qty, colaborador=colab_nome, motivo="Alocação"))

    # Licenses
    licenses_data = [
        ("Microsoft 365 Business","Microsoft",50,47,"2025-07-31",598,"Assinatura mensal"),
        ("Adobe Creative Cloud","Adobe",5,5,"2025-06-15",900,"Assinatura mensal"),
        ("Antivírus Kaspersky","Kaspersky",60,53,"2025-09-30",60,"Anual"),
        ("VPN Cisco AnyConnect","Cisco",30,22,"2026-01-15",266.67,"Perpétua"),
        ("AutoCAD 2024","Autodesk",3,3,"2025-05-20",4000,"Assinatura mensal"),
    ]
    for sw,forn,tot,atr,venc,custo,tipo in licenses_data:
        db.session.add(License(id=new_id("L"),software=sw,fornecedor=forn,total=tot,
                               atribuidas=atr,vencimento=venc,custo=custo,tipo=tipo))

    # Settings
    settings = {
        "empresa": {"nome":"Empresa Tecnologia SA","cnpj":"12.345.678/0001-90",
                    "email":"ti@empresa.com","telefone":"(11) 3000-0000",
                    "site":"www.empresa.com.br","endereco":"Av. Paulista, 1000 — São Paulo, SP",
                    "logo_base64":""},
        "termo_recebimento": {
            "titulo": "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO",
            "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido os seguintes equipamentos de propriedade da empresa:",
            "clausulas": [
                "Comprometo-me a:",
                "  1. Utilizar exclusivamente para fins profissionais;",
                "  2. Zelar pela conservação de todos os itens;",
                "  3. Comunicar ao TI qualquer dano, perda ou furto;",
                "  4. Devolver os equipamentos ao encerramento do vínculo.",
            ],
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "termo_devolucao": {
            "titulo": "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS",
            "preambulo": "Atestamos a devolução dos equipamentos abaixo pelo(a) colaborador(a) {colaborador},\ndo setor {setor}, unidade {unidade}:",
            "clausulas": [],
            "declaracao": "Declaro ter devolvido todos os equipamentos listados acima em plenas condições.",
            "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
        },
        "email_templates": DEFAULT_EMAIL_TEMPLATES,
        "backup": DEFAULT_BACKUP_CONFIG,
        "setores": ["TI","Financeiro","RH","Vendas","Marketing","Operações","Jurídico"],
        "unidades": [{"id":"UN1","nome":"Sede SP","cidade":"São Paulo","estado":"SP","tipo":"Sede"},
                     {"id":"UN2","nome":"Filial RJ","cidade":"Rio de Janeiro","estado":"RJ","tipo":"Filial"},
                     {"id":"UN3","nome":"Filial BH","cidade":"Belo Horizonte","estado":"MG","tipo":"Filial"},
                     {"id":"UN4","nome":"Almoxarifado","cidade":"São Paulo","estado":"SP","tipo":"Depósito"}],
        "alertas": {"dias_garantia":60,"dias_licenca":60,"estoque_minimo":True,"notif_email":False},
        "regras_usuario": {"exige_termo_alocacao":True,"permite_alocar_sem_email":False,
                           "max_perifericos_por_colab":10,"obriga_vinculo_saida":True},
        "campos_ativo_obrigatorios": ["hostname","fabricante","modelo","categoria","patrimonio"],
        "categorias_config": {
            "Notebook":     {"tipo_alocacao":"colaborador"},
            "Desktop":      {"tipo_alocacao":"colaborador"},
            "Monitor":      {"tipo_alocacao":"colaborador"},
            "Smartphone":   {"tipo_alocacao":"colaborador"},
            "Dock Station": {"tipo_alocacao":"colaborador"},
            "Tablet":       {"tipo_alocacao":"colaborador"},
            "Impressora":   {"tipo_alocacao":"unidade"},
            "Switch":       {"tipo_alocacao":"unidade"},
            "Firewall":     {"tipo_alocacao":"unidade"},
            "Access Point": {"tipo_alocacao":"unidade"},
            "Servidor":     {"tipo_alocacao":"unidade"},
            "Storage":      {"tipo_alocacao":"unidade"},
            "Rack":         {"tipo_alocacao":"unidade"},
            "Nobreak":      {"tipo_alocacao":"unidade"},
            "DVR":          {"tipo_alocacao":"unidade"},
            "NVR":          {"tipo_alocacao":"unidade"},
            "Câmera IP":    {"tipo_alocacao":"unidade"},
        },
    }
    for k, v in settings.items():
        db.session.add(Setting(key=k, value=json.dumps(v, ensure_ascii=False)))

    db.session.commit()
    print("Dados iniciais inseridos")

# ═══════════════════════════════════════════════════════════════════════════
# INIT
# ═══════════════════════════════════════════════════════════════════════════

def _migrate_db():
    """Adiciona colunas/tabelas novas em DBs existentes sem apagar dados. Suporta SQLite e PostgreSQL."""
    from sqlalchemy import text as _text, inspect as _inspect
    needed_cols = {
        "allocations": [
            ("assinatura_img",     "TEXT"),
            ("sign_token",         "TEXT"),
            ("sign_token_expiry",  "TEXT"),
            ("assinatura_ti_img",  "TEXT"),
            ("assinatura_ti_nome", "VARCHAR(120)"),
            ("data_assinatura_ti", "TEXT"),
        ],
        "maintenance_orders": [
            ("status_anterior", "VARCHAR(30)"),
            ("attachments",     "JSON"),
        ],
        "licenses": [
            ("attachments", "JSON"),
        ],
        "assets": [
            ("public_token", "VARCHAR(80)"),
        ],
        "devolucoes": [
            ("laudo_status",    "VARCHAR(30)"),
            ("rh_token",        "VARCHAR(64)"),
            ("rh_token_expiry", "TEXT"),
            ("rh_email",        "VARCHAR(120)"),
            ("rh_ciencia_ip",   "VARCHAR(50)"),
            ("rh_data_ciencia", "TEXT"),
            ("cobranca_aplicada", "BOOLEAN"),
            ("cobranca_valor",  "REAL"),
            ("cobranca_obs",    "TEXT"),
        ],
        "colaboradores": [
            ("cpf", "VARCHAR(20)"),
        ],
        "laudos_tecnicos": [
            ("editado_em",    "TEXT"),
            ("editado_por",   "VARCHAR(120)"),
            ("motivo_edicao", "TEXT"),
        ],
        "attachments": [
            ("description", "TEXT"),
        ],
        "audit_campaign_items": [
            ("observed_unidade", "VARCHAR(80)"),
            ("observed_setor", "VARCHAR(80)"),
        ],
        "allocations": [
            ("assinatura_img",          "TEXT"),
            ("sign_token",              "TEXT"),
            ("sign_token_expiry",       "TEXT"),
            ("assinatura_ti_img",       "TEXT"),
            ("assinatura_ti_nome",      "VARCHAR(120)"),
            ("data_assinatura_ti",      "TEXT"),
            ("tipo",                    "VARCHAR(30)"),
            ("data_devolucao_prevista", "VARCHAR(10)"),
        ],
        "print_printers": [
            ("dpi", "INTEGER"),
        ],
        "termos_avulsos": [
            ("package_id", "VARCHAR(16)"),
            ("package_token", "VARCHAR(64)"),
            ("package_token_expiry", "TIMESTAMP"),
        ],
    }
    dialect_name = db.engine.dialect.name
    is_sqlite = dialect_name == "sqlite"
    with db.engine.connect() as conn:
        inspector = _inspect(db.engine)
        existing_tables = inspector.get_table_names()
        for tbl, cols in needed_cols.items():
            if tbl not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(tbl)}
            for col, typ in cols:
                if col not in existing_cols:
                    try:
                        conn.execute(_text(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}"))
                    except Exception:
                        pass
        # Create termos_avulsos if missing
        if "termos_avulsos" not in existing_tables:
            try:
                conn.execute(_text("""
                    CREATE TABLE termos_avulsos (
                        id VARCHAR(16) PRIMARY KEY,
                        tipo VARCHAR(40),
                        colaborador VARCHAR(120),
                        setor VARCHAR(80),
                        unidade VARCHAR(80),
                        email VARCHAR(120),
                        detalhes TEXT,
                        validade VARCHAR(10),
                        status VARCHAR(20) DEFAULT 'Pendente',
                        sign_token VARCHAR(64) UNIQUE,
                        sign_token_expiry TEXT,
                        package_id VARCHAR(16),
                        package_token VARCHAR(64),
                        package_token_expiry TIMESTAMP,
                        assinatura_img TEXT,
                        assinatura_ip VARCHAR(50),
                        data_assinatura TEXT,
                        created_at TEXT,
                        created_by VARCHAR(120)
                    )
                """))
            except Exception:
                pass
        if dialect_name == "postgresql" and "termos_avulsos" in existing_tables:
            try:
                conn.execute(_text("""
                    ALTER TABLE termos_avulsos
                    ALTER COLUMN package_token_expiry TYPE TIMESTAMP WITHOUT TIME ZONE
                    USING NULLIF(package_token_expiry::text, '')::timestamp
                """))
            except Exception:
                pass
        if "allocation_assets" not in existing_tables:
            try:
                conn.execute(_text("""
                    CREATE TABLE allocation_assets (
                        id VARCHAR(20) PRIMARY KEY,
                        allocation_id VARCHAR(16),
                        asset_id VARCHAR(16),
                        asset_nome VARCHAR(200),
                        categoria VARCHAR(40),
                        patrimonio VARCHAR(40),
                        service_tag VARCHAR(40)
                    )
                """))
            except Exception:
                pass
            try:
                conn.execute(_text("""
                    INSERT INTO allocation_assets (id, allocation_id, asset_id, asset_nome, categoria, patrimonio, service_tag)
                    SELECT 'AA' || substr(id, 3), id, ativo_id, ativo_nome, NULL, NULL, NULL
                    FROM allocations
                    WHERE ativo_id IS NOT NULL AND ativo_id <> ''
                """))
            except Exception:
                pass
        if "print_printers" not in existing_tables:
            try:
                conn.execute(_text("""
                    CREATE TABLE print_printers (
                        id VARCHAR(60) PRIMARY KEY,
                        name VARCHAR(120),
                        location VARCHAR(120),
                        printer_type VARCHAR(40),
                        windows_name VARCHAR(120),
                        dpi INTEGER,
                        token_hash VARCHAR(64),
                        status VARCHAR(20),
                        last_seen TEXT,
                        created_at TEXT
                    )
                """))
            except Exception:
                pass
        if "print_jobs" not in existing_tables:
            try:
                if is_sqlite:
                    print_job_id_sql = "INTEGER PRIMARY KEY AUTOINCREMENT"
                elif dialect_name == "postgresql":
                    print_job_id_sql = "SERIAL PRIMARY KEY"
                else:
                    print_job_id_sql = "INTEGER PRIMARY KEY AUTO_INCREMENT"
                conn.execute(_text("""
                    CREATE TABLE print_jobs (
                        id %s,
                        printer_id VARCHAR(60),
                        template VARCHAR(80),
                        status VARCHAR(20),
                        copies INTEGER,
                        data JSON,
                        zpl TEXT,
                        message TEXT,
                        created_by VARCHAR(80),
                        created_at TEXT,
                        picked_at TEXT,
                        finished_at TEXT
                    )
                """ % print_job_id_sql))
            except Exception:
                pass
        if "assets" in existing_tables and dialect_name in ("sqlite", "postgresql"):
            for idx_name, col in [
                ("ix_assets_public_token", "public_token"),
                ("ix_assets_patrimonio_unique_nonempty", "patrimonio"),
                ("ix_assets_service_tag_unique_nonempty", "service_tag"),
                ("ix_assets_mac_unique_nonempty", "mac"),
            ]:
                if col not in {c["name"] for c in inspector.get_columns("assets")}:
                    continue
                where = "" if col == "public_token" else f" WHERE {col} IS NOT NULL AND {col} <> ''"
                try:
                    conn.execute(_text(
                        f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} ON assets ({col}){where}"
                    ))
                except Exception:
                    logger.warning("Índice legado %s não criado; verifique duplicidades existentes.", idx_name)
        if "supplies" in existing_tables and dialect_name == "postgresql":
            try:
                conn.execute(_text("""
                    ALTER TABLE supplies
                    ADD CONSTRAINT ck_supplies_estoque_nonnegative CHECK (estoque >= 0) NOT VALID
                """))
            except Exception:
                pass
        conn.commit()

    # Inicializa settings de termos novos (para instalações existentes que nunca passaram pelo /setup)
    try:
        new_setting_defaults = {
            "termo_emprestimo": {
                "titulo": "TERMO DE EMPRÉSTIMO DE EQUIPAMENTO",
                "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido em caráter de EMPRÉSTIMO TEMPORÁRIO o equipamento abaixo:",
                "clausulas": [
                    "Comprometo-me a:",
                    "  1. Utilizar exclusivamente para fins profissionais durante o período de empréstimo;",
                    "  2. Zelar pela conservação do equipamento;",
                    "  3. Devolver o equipamento na data prevista ou quando solicitado pelo setor de TI;",
                    "  4. Comunicar imediatamente ao TI qualquer dano, perda ou furto.",
                ],
                "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
            },
            "termo_vpn": {
                "titulo": "TERMO DE ACESSO VPN / USO REMOTO",
                "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro estar ciente das regras de acesso à VPN corporativa:",
                "clausulas": [
                    "1. O acesso VPN é pessoal e intransferível;",
                    "2. É proibido compartilhar credenciais com terceiros;",
                    "3. O colaborador é responsável por todos os acessos realizados com suas credenciais;",
                    "4. O uso deve ser restrito a atividades profissionais autorizadas;",
                    "5. O descumprimento sujeita o colaborador a medidas disciplinares.",
                ],
                "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
            },
        }
        with db.engine.connect() as _c2:
            for _key, _val in new_setting_defaults.items():
                _row = _c2.execute(_text("SELECT 1 FROM settings WHERE key = :k"), {"k": _key}).fetchone()
                if _row is None:
                    _c2.execute(
                        _text("INSERT INTO settings (key, value) VALUES (:k, :v)"),
                        {"k": _key, "v": json.dumps(_val, ensure_ascii=False)}
                    )
            _c2.commit()
    except Exception:
        pass


def register_route_modules():
    """Importa modulos de rotas para registrar os endpoints Flask."""
    from routes.blueprint import bp as routes_bp
    from routes import (
        setup, auth, assets, supplies, colaboradores, allocations,
        licenses, operations, users, settings, devolucoes, reports, audit_campaigns, attachments,
        termos_avulsos, print_jobs,
    )
    app.register_blueprint(routes_bp, name="")
    return (setup, auth, assets, supplies, colaboradores, allocations, licenses, operations, users, settings, devolucoes, reports, audit_campaigns, attachments, termos_avulsos, print_jobs)

register_route_modules()


def _alembic_schema_at_head():
    """Retorna True quando o banco ja foi atualizado pelo Alembic ate o head atual."""
    try:
        with db.engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            return version == ALEMBIC_SCHEMA_HEAD
    except Exception:
        return False


def _run_startup_db_tasks_once():
    """Executa bootstrap/migração uma vez, com lock no PostgreSQL para múltiplos workers."""
    lock_conn = None
    try:
        if db.engine.dialect.name == "postgresql":
            lock_conn = db.engine.connect()
            lock_conn.execute(text("SELECT pg_advisory_lock(54720191)"))
        if app.config["AUTO_CREATE_DB"]:
            db.create_all()
        if app.config["AUTO_LEGACY_MIGRATIONS"] and not _alembic_schema_at_head():
            _migrate_db()
        if _auto_seed_demo_enabled():
            seed()
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock(54720191)"))
            finally:
                lock_conn.close()


def _run_startup_db_tasks():
    """Executa bootstrap/migração com retry para tolerar atraso do banco no boot."""
    retries, delay = startup_retry_config()
    for attempt in range(1, retries + 1):
        try:
            _run_startup_db_tasks_once()
            return
        except Exception as exc:
            db.session.remove()
            db.engine.dispose()
            if attempt >= retries:
                logger.exception(
                    "Falha ao inicializar banco de dados apos %s tentativa(s)", retries
                )
                raise
            logger.warning(
                "Banco indisponivel na inicializacao (%s/%s): %s. Nova tentativa em %.1fs.",
                attempt,
                retries,
                exc.__class__.__name__,
                delay,
            )
            _time.sleep(delay)


def create_app():
    """Retorna a instancia Flask configurada para WSGI, testes e Flask CLI."""
    return app


with app.app_context():
    _run_startup_db_tasks()

if __name__ == "__main__":
    host, port, debug = runtime_server_config()

    print("\nTI Control — Flask + Auth + Observabilidade")
    print(f"   DB:    {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"   URL:   {app.config['APP_BASE_URL']}")
    print(f"   Host:  {host}")
    print(f"   Porta: {port}")
    print(f"   Debug: {debug}")
    print(f"   Acesse pela VM: http://IP_DA_VM:{port}\n")

    app.run(host=host, port=port, debug=debug)
