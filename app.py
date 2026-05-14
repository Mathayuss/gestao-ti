"""
TI Control SRE — Sistema de Gestão de Ativos de TI com práticas de confiabilidade

Inclui autenticação, persistência em SQLite, métricas Prometheus, health checks,
request-id, endpoints operacionais e documentação SRE para operação do serviço.
"""
import os, io, uuid, warnings, csv, json, re, time as _time, hashlib, smtplib, base64, logging, html as _html
import sys
sys.modules.setdefault("app", sys.modules[__name__])
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from time import perf_counter
from datetime import date, datetime, timedelta
# Suppress Flask-Login's internal datetime.utcnow() deprecation (Python 3.12)
warnings.filterwarnings('ignore', message='.*utcnow.*', category=DeprecationWarning)
from functools import wraps
from flask import (Flask, jsonify, request, render_template,
                   send_file, redirect, url_for, session, Response, g)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from urllib.parse import urlsplit
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    )
    METRICS_OK = True
except ImportError:
    METRICS_OK = False

load_dotenv()
logger = logging.getLogger("ti_control")

# Falha rápida se SECRET_KEY não estiver definida explicitamente
_secret_key = os.environ.get("SECRET_KEY", "")
if not _secret_key:
    if os.environ.get("FLASK_DEBUG", "0") == "1":
        _secret_key = "ticontrol-dev-only-secret-DO-NOT-USE-IN-PROD"
        logger.warning("SECRET_KEY não definida; usando chave de desenvolvimento insegura")
    else:
        raise RuntimeError(
            "SECRET_KEY não definida. Configure a variável de ambiente SECRET_KEY antes de iniciar em produção."
        )

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

_is_production = os.environ.get("ENVIRONMENT", "development") not in ("development", "dev")
_session_secure = os.environ.get("SESSION_SECURE", "0") == "1"

app.config.update(
    SECRET_KEY                   = _secret_key,
    SQLALCHEMY_DATABASE_URI      = os.environ.get("DATABASE_URL", "sqlite:///ticontrol.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS = False,
    SQLALCHEMY_ENGINE_OPTIONS    = {
        "pool_pre_ping": True,
        "pool_recycle":  300,
    },
    JSON_SORT_KEYS               = False,
    APP_BASE_URL                 = os.environ.get("APP_BASE_URL", "http://localhost").rstrip("/"),
    SERVICE_NAME                 = os.environ.get("SERVICE_NAME", "ti-control-sre"),
    BUILD_VERSION                = os.environ.get("BUILD_VERSION", "dev"),
    ENVIRONMENT                  = os.environ.get("ENVIRONMENT", "development"),
    # Credenciais de demo: NUNCA mostrar a não ser que explicitamente ativado
    SHOW_DEMO_CREDENTIALS        = os.environ.get("SHOW_DEMO_CREDENTIALS", "0") == "1",
    # Session / cookie settings
    SESSION_COOKIE_HTTPONLY      = True,
    SESSION_COOKIE_SAMESITE      = "Lax",
    SESSION_COOKIE_SECURE        = _session_secure,
    SESSION_COOKIE_NAME          = "ticontrol_session",
    PERMANENT_SESSION_LIFETIME   = 86400 * 7,
    # Remember-me cookie
    REMEMBER_COOKIE_HTTPONLY     = True,
    REMEMBER_COOKIE_SAMESITE     = "Lax",
    REMEMBER_COOKIE_SECURE       = _session_secure,
    REMEMBER_COOKIE_DURATION     = 86400 * 7,
    # O frontend atual usa fetch/form posts sem token CSRF. Mantem a extensao
    # instalada, mas evita bloquear login e APIs ate a tela enviar tokens.
    WTF_CSRF_CHECK_DEFAULT       = False,
)

db   = SQLAlchemy(app)
csrf = CSRFProtect(app)
lm   = LoginManager(app)
lm.login_view = "login_page"

@app.template_filter("from_json")
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except Exception:
        return []

try:
    from flask_migrate import Migrate as _FlaskMigrate
    _flask_migrate = _FlaskMigrate(app, db)
    MIGRATE_OK = True
except ImportError:
    MIGRATE_OK = False

# ═══════════════════════════════════════════════════════════════════════════
# SRE / OBSERVABILITY
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
        "Exceções não tratadas observadas pelo middleware SRE.",
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
def sre_before_request():
    g.request_started_at = perf_counter()
    g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    g.metrics_active_request_tracked = False
    if request.endpoint not in {"health_live", "health_ready", "health_startup", "metrics", "ping"}:
        _maybe_run_scheduled_backup()
    if METRICS_OK:
        HTTP_ACTIVE_REQUESTS.inc()
        g.metrics_active_request_tracked = True


@app.after_request
def sre_after_request(response):
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
def sre_teardown_request(exc):
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

class SystemUser(UserMixin, db.Model):
    __tablename__ = "system_users"
    id           = db.Column(db.String(16), primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    nome         = db.Column(db.String(120))
    email        = db.Column(db.String(120))
    senha_hash   = db.Column(db.String(256))
    perfil       = db.Column(db.String(40), default="Visualizador")
    status       = db.Column(db.String(20), default="Ativo")
    ultimo_acesso= db.Column(db.DateTime)
    criado_em    = db.Column(db.Date, default=date.today)

    def set_senha(self, raw): self.senha_hash = generate_password_hash(raw)
    def check_senha(self, raw): return check_password_hash(self.senha_hash, raw)

    def to_dict(self):
        return {"id":self.id,"username":self.username,"nome":self.nome,"email":self.email,
                "perfil":self.perfil,"status":self.status,
                "ultimoAcesso":self.ultimo_acesso.isoformat() if self.ultimo_acesso else None,
                "criadoEm":str(self.criado_em)}


class Colaborador(db.Model):
    __tablename__ = "colaboradores"
    id           = db.Column(db.String(16), primary_key=True)
    nome         = db.Column(db.String(120), nullable=False)
    email        = db.Column(db.String(120))
    telefone     = db.Column(db.String(30))
    cargo        = db.Column(db.String(80))
    setor        = db.Column(db.String(80))
    unidade      = db.Column(db.String(80))
    status       = db.Column(db.String(20), default="Ativo")
    matricula    = db.Column(db.String(40))
    data_admissao= db.Column(db.String(10))
    data_cadastro= db.Column(db.String(10))
    data_desligamento = db.Column(db.String(10))
    observacao   = db.Column(db.Text, default="")

    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"email":self.email,"telefone":self.telefone,
                "cargo":self.cargo,"setor":self.setor,"unidade":self.unidade,"status":self.status,
                "matricula":self.matricula,"dataAdmissao":self.data_admissao,
                "dataCadastro":self.data_cadastro,"dataDesligamento":self.data_desligamento,
                "observacao":self.observacao}


ASSET_STATUS_VALID = ["Disponível","Alocado","Manutenção","Ativo",
                       "Baixado","Descartado","Extraviado","Vendido","Inativo"]

class Asset(db.Model):
    __tablename__ = "assets"
    id           = db.Column(db.String(16), primary_key=True)
    hostname     = db.Column(db.String(80))
    ip           = db.Column(db.String(40), default="DHCP")
    mac          = db.Column(db.String(20))
    service_tag  = db.Column(db.String(40))
    os           = db.Column(db.String(80))
    fabricante   = db.Column(db.String(60))
    modelo       = db.Column(db.String(80))
    patrimonio   = db.Column(db.String(40))
    nf           = db.Column(db.String(40))
    categoria    = db.Column(db.String(40))
    status       = db.Column(db.String(30), default="Disponível")
    colaborador  = db.Column(db.String(120), default="")
    setor        = db.Column(db.String(80), default="")
    unidade      = db.Column(db.String(80), default="")
    garantia     = db.Column(db.String(10))
    criado_em    = db.Column(db.Date, default=date.today)

    def to_dict(self):
        return {"id":self.id,"hostname":self.hostname,"ip":self.ip,"mac":self.mac,
                "serviceTag":self.service_tag,"os":self.os,"fabricante":self.fabricante,
                "modelo":self.modelo,"patrimonio":self.patrimonio,"nf":self.nf,
                "categoria":self.categoria,"status":self.status,"colaborador":self.colaborador,
                "setor":self.setor,"unidade":self.unidade,"garantia":self.garantia}


class Supply(db.Model):
    __tablename__ = "supplies"
    id       = db.Column(db.String(16), primary_key=True)
    nome     = db.Column(db.String(120), nullable=False)
    categoria= db.Column(db.String(40))
    unidade  = db.Column(db.String(80))
    estoque  = db.Column(db.Integer, default=0)
    minimo   = db.Column(db.Integer, default=0)
    preco    = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"categoria":self.categoria,
                "unidade":self.unidade,"estoque":self.estoque,
                "minimo":self.minimo,"preco":self.preco}


class SupplyMovement(db.Model):
    __tablename__ = "supply_movements"
    id           = db.Column(db.String(20), primary_key=True)
    tipo         = db.Column(db.String(20))   # ENTRADA SAIDA DEVOLUCAO
    ref_id       = db.Column(db.String(16))   # supply_id
    supply_nome  = db.Column(db.String(120))
    descricao    = db.Column(db.Text)
    quantidade   = db.Column(db.Integer)
    colaborador  = db.Column(db.String(120), default="")
    ativo_id     = db.Column(db.String(16), default="")
    motivo       = db.Column(db.String(80), default="")
    data         = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"id":self.id,"tipo":self.tipo,"refId":self.ref_id,"supplyNome":self.supply_nome,
                "descricao":self.descricao,"quantidade":self.quantidade,"colaborador":self.colaborador,
                "ativoId":self.ativo_id,"motivo":self.motivo,
                "data":self.data.isoformat() if self.data else None}


class Allocation(db.Model):
    __tablename__ = "allocations"
    id           = db.Column(db.String(16), primary_key=True)
    ativo_id     = db.Column(db.String(16), db.ForeignKey("assets.id"))
    ativo_nome   = db.Column(db.String(200))
    colaborador  = db.Column(db.String(120))
    setor        = db.Column(db.String(80))
    unidade      = db.Column(db.String(80))
    email        = db.Column(db.String(120))
    data_aloc    = db.Column(db.String(10))
    data_encerramento = db.Column(db.String(10))
    motivo       = db.Column(db.String(80), default="Uso contínuo")
    status       = db.Column(db.String(20), default="Ativo")
    termo           = db.Column(db.String(30))
    termo_status    = db.Column(db.String(20), default="Pendente")
    data_assinatura = db.Column(db.DateTime)
    assinatura_ip   = db.Column(db.String(50))
    assinatura_img      = db.Column(db.Text)       # PNG base64 capturada no canvas (colaborador)
    sign_token          = db.Column(db.String(64), unique=True)
    sign_token_expiry   = db.Column(db.DateTime)
    assinatura_ti_img   = db.Column(db.Text)       # PNG base64 da assinatura do responsável TI
    assinatura_ti_nome  = db.Column(db.String(120))
    data_assinatura_ti  = db.Column(db.DateTime)
    items           = db.relationship("AllocationItem", backref="allocation",
                                     cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_items=False):
        d = {"id":self.id,"ativo":self.ativo_id,"ativoNome":self.ativo_nome,
             "colaborador":self.colaborador,"setor":self.setor,"unidade":self.unidade,
             "email":self.email,"dataAloc":self.data_aloc,"motivo":self.motivo,
             "dataEncerramento":self.data_encerramento,
             "status":self.status,"termo":self.termo,"termoStatus":self.termo_status,
             "dataAssinatura":self.data_assinatura.isoformat() if self.data_assinatura else None,
             "assinaturaIp": self.assinatura_ip or None,
             "signTokenExpiry":self.sign_token_expiry.isoformat() if self.sign_token_expiry else None,
             "hasSignImg": bool(self.assinatura_img),
             "assinaturaTiNome": self.assinatura_ti_nome or None,
             "dataAssinaturaTi": self.data_assinatura_ti.isoformat() if self.data_assinatura_ti else None,
             "hasSignTiImg": bool(self.assinatura_ti_img)}
        if include_items:
            d["perifericos"] = [i.to_dict() for i in self.items]
        return d


class AllocationItem(db.Model):
    """Periféricos entregues junto com esta alocação — vinculados ao TERMO."""
    __tablename__ = "allocation_items"
    id           = db.Column(db.String(20), primary_key=True)
    allocation_id= db.Column(db.String(16), db.ForeignKey("allocations.id"))
    supply_id    = db.Column(db.String(16))
    supply_nome  = db.Column(db.String(120))
    quantidade   = db.Column(db.Integer)

    def to_dict(self):
        return {"supplyId":self.supply_id,"nome":self.supply_nome,"quantidade":self.quantidade}


class License(db.Model):
    __tablename__ = "licenses"
    id          = db.Column(db.String(16), primary_key=True)
    software    = db.Column(db.String(120))
    fornecedor  = db.Column(db.String(80))
    total       = db.Column(db.Integer, default=0)
    atribuidas  = db.Column(db.Integer, default=0)
    vencimento  = db.Column(db.String(10))
    custo       = db.Column(db.Float, default=0.0)
    tipo        = db.Column(db.String(40))

    def to_dict(self):
        return {"id":self.id,"software":self.software,"fornecedor":self.fornecedor,
                "total":self.total,"atribuidas":self.atribuidas,"vencimento":self.vencimento,
                "custo":self.custo,"tipo":self.tipo}


class Incident(db.Model):
    __tablename__ = "incidents"
    id       = db.Column(db.String(16), primary_key=True)
    ref_id   = db.Column(db.String(16))
    tipo     = db.Column(db.String(40))
    descricao= db.Column(db.Text)
    status   = db.Column(db.String(20), default="Aberto")
    data     = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"id":self.id,"refId":self.ref_id,"tipo":self.tipo,"descricao":self.descricao,
                "status":self.status,"data":self.data.isoformat() if self.data else None}


class MaintenanceOrder(db.Model):
    """Ordem de Serviço de manutenção de um ativo."""
    __tablename__ = "maintenance_orders"
    id                = db.Column(db.String(16), primary_key=True)
    asset_id          = db.Column(db.String(16), db.ForeignKey("assets.id"))
    asset_nome        = db.Column(db.String(200))
    tipo              = db.Column(db.String(40), default="Corretiva")
    status            = db.Column(db.String(30), default="Aberta")
    status_anterior   = db.Column(db.String(30), default="Disponível")
    descricao_defeito = db.Column(db.Text)
    diagnostico       = db.Column(db.Text)
    tecnico           = db.Column(db.String(120))
    data_abertura     = db.Column(db.String(10))
    data_conclusao    = db.Column(db.String(10))
    custo_total       = db.Column(db.Float, default=0.0)
    observacao        = db.Column(db.Text)
    parts             = db.relationship("MaintenancePart", backref="order",
                                        cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_parts=False):
        d = {"id": self.id, "assetId": self.asset_id, "assetNome": self.asset_nome,
             "tipo": self.tipo, "status": self.status, "statusAnterior": self.status_anterior,
             "descricaoDefeito": self.descricao_defeito, "diagnostico": self.diagnostico,
             "tecnico": self.tecnico, "dataAbertura": self.data_abertura,
             "dataConclusao": self.data_conclusao, "custoTotal": self.custo_total,
             "observacao": self.observacao}
        if include_parts:
            d["pecas"] = [p.to_dict() for p in self.parts]
        return d


class MaintenancePart(db.Model):
    """Peça ou insumo consumido em uma OS de manutenção."""
    __tablename__ = "maintenance_parts"
    id             = db.Column(db.String(20), primary_key=True)
    maintenance_id = db.Column(db.String(16), db.ForeignKey("maintenance_orders.id"))
    supply_id      = db.Column(db.String(16))
    supply_nome    = db.Column(db.String(120))
    quantidade     = db.Column(db.Integer, default=1)
    custo_unitario = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {"id": self.id, "supplyId": self.supply_id, "nome": self.supply_nome,
                "quantidade": self.quantidade, "custoUnitario": self.custo_unitario,
                "custoTotal": round(self.quantidade * self.custo_unitario, 2)}


class AuditLog(db.Model):
    """Log imutável de todas as ações do sistema."""
    __tablename__ = "audit_logs"
    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario   = db.Column(db.String(80))
    acao      = db.Column(db.String(60))
    modulo    = db.Column(db.String(40))
    ref_id    = db.Column(db.String(20))
    detalhe   = db.Column(db.Text)
    ip        = db.Column(db.String(50))
    data      = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"id":self.id,"usuario":self.usuario,"acao":self.acao,"modulo":self.modulo,
                "refId":self.ref_id,"detalhe":self.detalhe,"ip":self.ip,
                "data":self.data.isoformat() if self.data else None}


class Setting(db.Model):
    """Configurações key-value JSON."""
    __tablename__ = "settings"
    key   = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)


class LoginAttempt(db.Model):
    """Tentativas de login — persiste entre workers para rate-limiting real."""
    __tablename__ = "login_attempts"
    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip        = db.Column(db.String(50), nullable=False, index=True)
    timestamp = db.Column(db.Float, nullable=False)
    success   = db.Column(db.Boolean, default=False)


class Devolucao(db.Model):
    """Evento de devolução de equipamentos — captura assinatura digital do colaborador."""
    __tablename__ = "devolucoes"
    id                    = db.Column(db.String(16), primary_key=True)
    colaborador_id        = db.Column(db.String(16), db.ForeignKey("colaboradores.id"), nullable=True)
    colaborador           = db.Column(db.String(120), nullable=False)
    setor                 = db.Column(db.String(80), default="")
    unidade               = db.Column(db.String(80), default="")
    data_devolucao        = db.Column(db.String(10))
    sign_token            = db.Column(db.String(64), unique=True)
    sign_token_expiry     = db.Column(db.DateTime)
    assinatura_img        = db.Column(db.Text)
    assinatura_ip         = db.Column(db.String(50))
    data_assinatura       = db.Column(db.DateTime)
    status                = db.Column(db.String(20), default="Pendente")
    ativos_devolvidos     = db.Column(db.Text, default="[]")   # JSON list
    perifericos_devolvidos= db.Column(db.Text, default="[]")   # JSON list
    laudo_status          = db.Column(db.String(30), default="Aguardando Laudo")
    rh_token              = db.Column(db.String(64), unique=True)
    rh_token_expiry       = db.Column(db.DateTime)
    rh_email              = db.Column(db.String(120))
    rh_ciencia_ip         = db.Column(db.String(50))
    rh_data_ciencia       = db.Column(db.DateTime)
    cobranca_valor        = db.Column(db.Float, default=0.0)
    cobranca_obs          = db.Column(db.Text, default="")

    def to_dict(self):
        return {
            "id": self.id, "colaboradorId": self.colaborador_id,
            "colaborador": self.colaborador, "setor": self.setor, "unidade": self.unidade,
            "dataDevolucao": self.data_devolucao, "status": self.status,
            "dataAssinatura": self.data_assinatura.isoformat() if self.data_assinatura else None,
            "assinaturaIp": self.assinatura_ip,
            "hasAssinatura": bool(self.assinatura_img),
            "signTokenExpiry": self.sign_token_expiry.isoformat() if self.sign_token_expiry else None,
            "ativosDevolvidos": json.loads(self.ativos_devolvidos or "[]"),
            "perifericosDevolvidos": json.loads(self.perifericos_devolvidos or "[]"),
            "laudoStatus": self.laudo_status,
            "rhEmail": self.rh_email,
            "rhDataCiencia": self.rh_data_ciencia.isoformat() if self.rh_data_ciencia else None,
            "cobrancaValor": self.cobranca_valor,
            "cobrancaObs": self.cobranca_obs,
        }


class LaudoTecnico(db.Model):
    """Avaliação técnica dos equipamentos no processo de desligamento."""
    __tablename__ = "laudos_tecnicos"
    id               = db.Column(db.String(16), primary_key=True)
    devolucao_id     = db.Column(db.String(16), db.ForeignKey("devolucoes.id"), nullable=False)
    tecnico          = db.Column(db.String(120), nullable=False)
    avaliacao_itens  = db.Column(db.Text, default="[]")  # JSON: [{ativo, estado, observacao}]
    observacao_geral = db.Column(db.Text, default="")
    tem_cobranca     = db.Column(db.Boolean, default=False)
    valor_cobranca   = db.Column(db.Float, default=0.0)
    data_avaliacao   = db.Column(db.DateTime, default=datetime.now)
    editado_em       = db.Column(db.DateTime, nullable=True)
    editado_por      = db.Column(db.String(120), nullable=True)
    motivo_edicao    = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "devolucaoId": self.devolucao_id,
            "tecnico": self.tecnico,
            "avaliacaoItens": json.loads(self.avaliacao_itens or "[]"),
            "observacaoGeral": self.observacao_geral,
            "temCobranca": self.tem_cobranca,
            "valorCobranca": self.valor_cobranca,
            "dataAvaliacao": self.data_avaliacao.isoformat() if self.data_avaliacao else None,
            "editadoEm": self.editado_em.isoformat() if self.editado_em else None,
            "editadoPor": self.editado_por,
            "motivoEdicao": self.motivo_edicao,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PERMISSION PROFILES
# ═══════════════════════════════════════════════════════════════════════════

PERFIL_PERMISSOES = {
    "Administrador": {
        "label":"Acesso total ao sistema","cor":"red",
        "modulos":["dashboard","ativos","insumos","colaboradores","alocacoes",
                   "qrcode","licencas","alertas","system_users","configuracoes"],
        "pode_editar":True,"pode_excluir":True,"pode_exportar":True,
    },
    "Técnico TI": {
        "label":"Gestão operacional de TI","cor":"blue",
        "modulos":["dashboard","ativos","insumos","alocacoes","qrcode","alertas","colaboradores"],
        "pode_editar":True,"pode_excluir":False,"pode_exportar":True,
    },
    "Gestor": {
        "label":"Visualização gerencial e relatórios","cor":"amber",
        "modulos":["dashboard","ativos","colaboradores","licencas","alertas"],
        "pode_editar":False,"pode_excluir":False,"pode_exportar":True,
    },
    "Visualizador": {
        "label":"Somente leitura","cor":"gray",
        "modulos":["dashboard","alertas"],
        "pode_editar":False,"pode_excluir":False,"pode_exportar":False,
    },
}

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
    """Normaliza texto vindo de formulários/API."""
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


def parse_float(value, default=0.0, minimum=None):
    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        number = default
    if minimum is not None and number < minimum:
        number = minimum
    return number


def parse_bool(value, default=False):
    """Converte valores comuns de formulários/API para booleano."""
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
    """Valida duplicidade dos principais identificadores patrimoniais."""
    checks = [
        ("patrimonio", "patrimonio", "Patrimônio"),
        ("serviceTag", "service_tag", "Service Tag"),
        ("mac", "mac", "MAC"),
    ]
    ignore_values = {"", "n/a", "na", "não se aplica", "nao se aplica", "dhcp", "-"}
    conflicts = []
    for input_key, attr, label in checks:
        value = clean_text(payload.get(input_key))
        if value.lower() in ignore_values:
            continue
        column = getattr(Asset, attr)
        stmt = db.select(Asset).where(column == value)
        if exclude_id:
            stmt = stmt.where(Asset.id != exclude_id)
        existing = db.session.execute(stmt).scalar_one_or_none()
        if existing:
            conflicts.append(f"{label} '{value}' já está cadastrado no ativo {existing.hostname or existing.id}.")
    return conflicts


def validate_asset_payload(payload, partial=False, exclude_id=None):
    errors = []
    required = _get_setting("campos_ativo_obrigatorios", ["hostname", "fabricante", "modelo", "categoria", "patrimonio"])
    if not partial:
        for field in required:
            if not clean_text(payload.get(field)):
                errors.append(f"Campo obrigatório ausente: {field}.")
    status = payload.get("status")
    if status and status not in ASSET_STATUS_VALID:
        errors.append(f"Status inválido: {status}.")
    errors.extend(_asset_unique_conflicts(payload, exclude_id=exclude_id))
    return errors


def csv_response(filename, rows, headers):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", delimiter=";")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(data, mimetype="text/csv; charset=utf-8", as_attachment=True, download_name=filename)


def safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", clean_text(value))
    return value.strip("_") or "arquivo"


# ── Validadores de formato ────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
_PHONE_RE = re.compile(r"^[\d\s().+\-]{7,20}$")


def validate_email(value):
    """Retorna mensagem de erro ou None se o e-mail for válido (ou vazio)."""
    v = clean_text(value)
    if v and not _EMAIL_RE.match(v):
        return "E-mail inválido."
    return None


def validate_phone(value):
    """Retorna mensagem de erro ou None se o telefone for válido (ou vazio)."""
    v = clean_text(value)
    if v and not _PHONE_RE.match(v):
        return "Telefone inválido (aceito: dígitos, espaços e ( ) - +, 7-20 chars)."
    return None


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


def _check_login_rate_limit(ip: str) -> bool:
    """Rate limiter via DB — funciona com múltiplos workers. Retorna True se dentro do limite."""
    now = _time.time()
    cutoff = now - _RATE_WINDOW
    try:
        from sqlalchemy import text as _txt
        # Limpa entradas antigas e conta falhas recentes
        db.session.execute(_txt("DELETE FROM login_attempts WHERE timestamp < :cutoff"), {"cutoff": cutoff})
        count = db.session.execute(
            _txt("SELECT COUNT(*) FROM login_attempts WHERE ip = :ip AND success = 0 AND timestamp >= :cutoff"),
            {"ip": ip, "cutoff": cutoff}
        ).scalar() or 0
        db.session.commit()
        if count >= _RATE_LIMIT:
            return False
        # Registra tentativa (success=False — será atualizado em caso de sucesso)
        db.session.add(LoginAttempt(ip=ip, timestamp=now, success=False))
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        # Se o DB falhar, usa fallback in-memory
        return _check_rate_limit(ip, "login_fallback")


def _record_login_success(ip: str):
    """Marca a última tentativa do IP como bem-sucedida."""
    try:
        from sqlalchemy import text as _txt
        db.session.execute(
            _txt("UPDATE login_attempts SET success=1 WHERE ip=:ip ORDER BY id DESC LIMIT 1"),
            {"ip": ip}
        )
        db.session.commit()
    except Exception:
        db.session.rollback()

def requires(*perfis):
    """Decorator: exige autenticação + perfil."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({"error":"Não autenticado"}), 401
            if current_user.status != "Ativo":
                return jsonify({"error":"Conta desativada"}), 403
            if perfis and current_user.perfil not in perfis:
                return jsonify({"error":f"Perfil '{current_user.perfil}' sem acesso a esta ação"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator

api_auth = requires()  # exige apenas login, sem filtro de perfil

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
    alerts = []
    cfg_dias_gar = 60
    cfg_dias_lic = 60
    s_gar = db.session.get(Setting, "alertas.dias_garantia")
    s_lic = db.session.get(Setting, "alertas.dias_licenca")
    if s_gar: cfg_dias_gar = int(s_gar.value)
    if s_lic: cfg_dias_lic = int(s_lic.value)

    for a in db.session.execute(db.select(Asset).where(Asset.status.notin_(["Baixado","Descartado","Vendido"]))).scalars().all():
        d = days_until(a.garantia)
        if 0 <= d <= cfg_dias_gar:
            alerts.append({"tipo":"garantia","nivel":"danger" if d<=30 else "warning",
                           "titulo":f"Garantia vencendo: {a.hostname}","detalhe":f"{d} dias","ref":a.id})
    for s in db.session.execute(db.select(Supply)).scalars().all():
        if s.estoque == 0:
            alerts.append({"tipo":"estoque","nivel":"danger","titulo":f"Estoque zerado: {s.nome}","detalhe":"Repor imediatamente","ref":s.id})
        elif s.estoque <= s.minimo:
            alerts.append({"tipo":"estoque","nivel":"warning","titulo":f"Estoque mínimo: {s.nome}","detalhe":f"{s.estoque} un (mín: {s.minimo})","ref":s.id})
    for l in db.session.execute(db.select(License)).scalars().all():
        d = days_until(l.vencimento)
        if 0 <= d <= cfg_dias_lic:
            alerts.append({"tipo":"licenca","nivel":"danger" if d<=30 else "warning",
                           "titulo":f"Licença vencendo: {l.software}","detalhe":f"{d} dias","ref":l.id})
        if l.atribuidas > l.total:
            alerts.append({"tipo":"licenca","nivel":"danger","titulo":f"Licença excedida: {l.software}",
                           "detalhe":f"{l.atribuidas}/{l.total} atribuídas","ref":l.id})
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

# ═══════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# FRONTEND
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — ASSETS
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — SUPPLIES
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — COLABORADORES
# ═══════════════════════════════════════════════════════════════════════════

def _render_termo_text(template_str: str, ctx: dict) -> str:
    """Renderiza texto de termo com substituição de variáveis {chave}."""
    try:
        from jinja2 import Template
        return Template(template_str).render(**ctx)
    except Exception:
        try:
            return template_str.format_map({k: v or "" for k, v in ctx.items()})
        except Exception:
            return template_str


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


# ═══════════════════════════════════════════════════════════════════════════
# API — ALLOCATIONS (transacional)
# ═══════════════════════════════════════════════════════════════════════════

# ── Assinatura remota ────────────────────────────────────────────────────

# ═══════════════════════════════════════════════════════════════════════════
# API — LICENSES
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — INCIDENTS
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — MANUTENÇÃO
# ═══════════════════════════════════════════════════════════════════════════

MANUT_STATUS = ["Aberta","Em análise","Aguardando peça","Em reparo","Concluída","Sem reparo","Cancelada"]
MANUT_TIPO   = ["Corretiva","Preventiva","Melhoria"]
MANUT_ENCERRA = ["Concluída","Sem reparo","Cancelada"]


# ═══════════════════════════════════════════════════════════════════════════
# API — SYSTEM USERS
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# E-MAIL
# ═══════════════════════════════════════════════════════════════════════════

SMTP_ENV_KEYS = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_TLS", "SMTP_USER", "SMTP_PASSWORD",
    "SMTP_FROM_NAME", "SMTP_FROM_EMAIL", "SMTP_ENABLED",
)


def _smtp_env_available() -> bool:
    return any(os.environ.get(key) for key in SMTP_ENV_KEYS)


def _get_email_config() -> dict:
    """Lê configuração de e-mail do banco da aplicação ou das variáveis do servidor."""
    source = clean_text(_get_setting("email.source", ""), 20)
    if source not in ("app", "env"):
        source = "env" if _smtp_env_available() else "app"

    app_cfg = {
        "host":       _get_setting("email.host", ""),
        "port":       parse_int(_get_setting("email.port", 587), default=587, minimum=1),
        "tls":        parse_bool(_get_setting("email.tls", True), default=True),
        "user":       _get_setting("email.user", ""),
        "password":   _get_setting("email.password", ""),
        "from_name":  _get_setting("email.from_name", "TI Control"),
        "from_email": _get_setting("email.from_email", ""),
        "enabled":    parse_bool(_get_setting("email.enabled", False), default=False),
    }

    if source == "app":
        return {**app_cfg, "source": "app", "env_available": _smtp_env_available()}

    return {
        "host":         os.environ.get("SMTP_HOST") or app_cfg["host"],
        "port":         parse_int(os.environ.get("SMTP_PORT") or app_cfg["port"], default=587, minimum=1),
        "tls":          parse_bool(os.environ.get("SMTP_TLS"), default=app_cfg["tls"]),
        "user":         os.environ.get("SMTP_USER") or app_cfg["user"],
        "password":     os.environ.get("SMTP_PASSWORD") or app_cfg["password"],
        "from_name":    os.environ.get("SMTP_FROM_NAME") or app_cfg["from_name"],
        "from_email":   os.environ.get("SMTP_FROM_EMAIL") or app_cfg["from_email"],
        "enabled":      parse_bool(os.environ.get("SMTP_ENABLED"), default=app_cfg["enabled"]),
        "source":       "env",
        "env_available": _smtp_env_available(),
    }


def send_email(to: str, subject: str, body_html: str, body_text: str = "") -> dict:
    """Envia e-mail via SMTP. Retorna {'ok': bool, 'error': str|None}."""
    cfg = _get_email_config()
    if not cfg["enabled"]:
        return {"ok": False, "error": "E-mail desabilitado nas configurações."}
    if not cfg["host"] or not cfg["from_email"]:
        return {"ok": False, "error": "Servidor SMTP não configurado."}
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"]      = to
        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as srv:
            srv.ehlo()
            if cfg["tls"]:
                srv.starttls()
                srv.ehlo()
            if cfg["user"] and cfg["password"]:
                srv.login(cfg["user"], cfg["password"])
            srv.sendmail(cfg["from_email"], [to], msg.as_string())
        return {"ok": True, "error": None}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Falha de autenticação SMTP. Verifique usuário e senha."}
    except smtplib.SMTPConnectError:
        return {"ok": False, "error": f"Não foi possível conectar ao servidor {cfg['host']}:{cfg['port']}."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


DEFAULT_EMAIL_TEMPLATES = {
    "assinatura": {
        "subject": "[{empresa}] Termo de Responsabilidade - assinatura necessária",
        "body": (
            "Olá, {colaborador}!\n\n"
            "Você recebeu o equipamento {ativo}.\n\n"
            "Para confirmar o recebimento, clique no botão abaixo e assine digitalmente "
            "o Termo de Responsabilidade.\n\n"
            "Este link expira em 7 dias. Em caso de dúvidas, contate o setor de TI."
        ),
        "button_label": "Assinar Termo",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
    "devolucao": {
        "subject": "[{empresa}] Termo de Devolução - assinatura necessária",
        "body": (
            "Olá, {colaborador}!\n\n"
            "Foi registrada a devolução dos equipamentos sob sua responsabilidade.\n\n"
            "Por favor, acesse o link abaixo e assine o Termo de Devolução.\n\n"
            "Este link expira em 7 dias."
        ),
        "button_label": "Assinar Devolução",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
    "laudo_rh": {
        "subject": "[{empresa}] Laudo técnico aguardando sua ciência — {colaborador}",
        "body": (
            "Olá!\n\n"
            "O técnico {tecnico} concluiu a avaliação dos equipamentos de {colaborador} "
            "no processo de desligamento.\n\n"
            "Por favor, acesse o link abaixo para visualizar o laudo e dar ciência. "
            "Não é necessário fazer login.\n\n"
            "Este link expira em 7 dias."
        ),
        "button_label": "Ver Laudo e Dar Ciência",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
}


def _get_email_templates():
    saved = _get_setting("email_templates", {})
    saved = saved if isinstance(saved, dict) else {}
    merged = {}
    for key, defaults in DEFAULT_EMAIL_TEMPLATES.items():
        custom = saved.get(key, {})
        custom = custom if isinstance(custom, dict) else {}
        merged[key] = {**defaults, **{k: v for k, v in custom.items() if k in defaults}}
    return merged


def _normalize_email_templates(value):
    if not isinstance(value, dict):
        return None, "Templates de e-mail precisam ser um objeto."
    current = _get_email_templates()
    limits = {"subject": 180, "body": 4000, "button_label": 80, "footer": 500}
    for kind in DEFAULT_EMAIL_TEMPLATES:
        if kind not in value:
            continue
        incoming = value.get(kind)
        if not isinstance(incoming, dict):
            return None, f"Template '{kind}' precisa ser um objeto."
        for field, max_len in limits.items():
            if field in incoming:
                current[kind][field] = clean_text(incoming.get(field), max_len)
        if not current[kind]["subject"]:
            return None, f"Assunto do template '{kind}' é obrigatório."
        if not current[kind]["body"]:
            return None, f"Corpo do template '{kind}' é obrigatório."
        if not current[kind]["button_label"]:
            return None, f"Texto do botão do template '{kind}' é obrigatório."
    return current, None


def _render_email_template(kind: str, ctx: dict):
    templates = _get_email_templates()
    tpl = templates.get(kind, DEFAULT_EMAIL_TEMPLATES[kind])
    empresa = ctx.get("empresa") or "TI Control"
    full_ctx = {**ctx, "empresa": empresa}
    subject = clean_text(_render_termo_text(tpl["subject"], full_ctx), 180)
    body_text = _render_termo_text(tpl["body"], full_ctx)
    footer_text = _render_termo_text(tpl.get("footer", ""), full_ctx)
    button_label = _render_termo_text(tpl.get("button_label", "Abrir"), full_ctx)
    link = full_ctx.get("link", "")
    accent = "#059669" if kind == "devolucao" else "#1e40af"

    html_body = _html.escape(body_text).replace("\n", "<br>")
    html_footer = _html.escape(footer_text).replace("\n", "<br>")
    html_button = _html.escape(button_label)
    html_link = _html.escape(link, quote=True)
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#111827">
      <div style="line-height:1.6;font-size:14px">{html_body}</div>
      <p style="text-align:center;margin:30px 0">
        <a href="{html_link}" style="background:{accent};color:white;padding:12px 28px;border-radius:6px;
           text-decoration:none;font-weight:bold;display:inline-block">{html_button}</a>
      </p>
      <p style="word-break:break-all;color:#6b7280;font-size:12px">{html_link}</p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin-top:24px">
      <p style="color:#9ca3af;font-size:11px">{html_footer}</p>
    </div>"""
    text = f"{body_text}\n\n{button_label}: {link}\n\n{footer_text}"
    return subject, html, text


def send_email_link_assinatura(to: str, colaborador: str, ativo_nome: str, link: str) -> dict:
    """Atalho: envia link de assinatura de termo."""
    empresa = _get_setting("empresa", {})
    nome_empresa = empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"
    subject, html, text = _render_email_template("assinatura", {
        "empresa": nome_empresa,
        "colaborador": colaborador,
        "ativo": ativo_nome,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_link_devolucao(to: str, colaborador: str, link: str) -> dict:
    """Atalho: envia link de assinatura do termo de devolução."""
    empresa = _get_setting("empresa", {})
    nome_empresa = empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"
    subject, html, text = _render_email_template("devolucao", {
        "empresa": nome_empresa,
        "colaborador": colaborador,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_laudo_rh(to: str, colaborador: str, tecnico: str, link: str) -> dict:
    """Envia link de ciência do laudo técnico para o RH."""
    empresa = _get_setting("empresa", {})
    nome_empresa = empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"
    subject, html, text = _render_email_template("laudo_rh", {
        "empresa": nome_empresa,
        "colaborador": colaborador,
        "tecnico": tecnico,
        "link": link,
    })
    return send_email(to, subject, html, text)


# ═══════════════════════════════════════════════════════════════════════════
# API — SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

def _get_setting(key, default=None):
    s = db.session.get(Setting, key)
    if s is None: return default
    try: return json.loads(s.value)
    except: return s.value

def _set_setting(key, value):
    s = db.session.get(Setting, key)
    raw = json.dumps(value, ensure_ascii=False)
    if s: s.value = raw
    else: db.session.add(Setting(key=key, value=raw))


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
        result[cat] = {"tipo_alocacao": tipo}
    return result, None


def _normalize_unidade_payload(payload, current=None):
    if not isinstance(payload, dict):
        return None, "Dados da unidade precisam ser um objeto."
    current = current if isinstance(current, dict) else {}
    result = dict(current)
    fields = {"nome": 80, "tipo": 40, "cidade": 80, "estado": 2}
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


def _normalize_aparencia_setting(value):
    if not isinstance(value, dict):
        return None, "Configurações de aparência precisam ser um objeto."
    current = _get_setting("aparencia", {}) or {}
    result = dict(current) if isinstance(current, dict) else {}
    for key, max_len in (("nome_sistema", 80), ("slogan_sistema", 120)):
        if key in value:
            result[key] = clean_text(value.get(key), max_len)
    for key in ("logo_sistema", "bg_login"):
        if key in value:
            result[key] = clean_text(value.get(key), None)
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


SETTING_NORMALIZERS = {
    "empresa": _normalize_empresa_setting,
    "alertas": _normalize_alertas_setting,
    "regras_usuario": _normalize_regras_usuario_setting,
    "campos_ativo_obrigatorios": _normalize_campos_ativos_setting,
    "categorias_config": _normalize_categorias_config_setting,
    "aparencia": _normalize_aparencia_setting,
}


BACKUP_DIR = os.path.join(app.instance_path, "backups")
BACKUP_FILE_RE = re.compile(r"^backup_ticontrol_\d{8}_\d{6}_(manual|auto)\.json$")
_backup_last_check = 0

DEFAULT_BACKUP_CONFIG = {
    "enabled": False,
    "frequency": "daily",
    "retention": 7,
    "include_audit": False,
    "last_run": "",
    "last_file": "",
    "last_status": "Nunca executado",
    "last_error": "",
}


def _get_backup_config():
    saved = _get_setting("backup", {})
    saved = saved if isinstance(saved, dict) else {}
    cfg = {**DEFAULT_BACKUP_CONFIG, **saved}
    cfg["enabled"] = parse_bool(cfg.get("enabled"), default=False)
    cfg["frequency"] = cfg.get("frequency") if cfg.get("frequency") in ("daily", "weekly", "monthly") else "daily"
    cfg["retention"] = parse_int(cfg.get("retention"), default=7, minimum=1)
    cfg["include_audit"] = parse_bool(cfg.get("include_audit"), default=False)
    return cfg


def _normalize_backup_config(value):
    if not isinstance(value, dict):
        return None, "Configuração de backup precisa ser um objeto."
    cfg = _get_backup_config()
    if "enabled" in value:
        cfg["enabled"] = parse_bool(value.get("enabled"), default=False)
    if "frequency" in value:
        freq = clean_text(value.get("frequency"), 20)
        if freq not in ("daily", "weekly", "monthly"):
            return None, "Frequência de backup inválida."
        cfg["frequency"] = freq
    if "retention" in value:
        cfg["retention"] = min(parse_int(value.get("retention"), default=7, minimum=1), 90)
    if "include_audit" in value:
        cfg["include_audit"] = parse_bool(value.get("include_audit"), default=False)
    return cfg, None


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
        "allocations": [a.to_dict(include_items=True) for a in db.session.execute(db.select(Allocation)).scalars().all()],
        "licenses": [l.to_dict() for l in db.session.execute(db.select(License)).scalars().all()],
        "incidents": [i.to_dict() for i in db.session.execute(db.select(Incident)).scalars().all()],
        "maintenance": [m.to_dict(include_parts=True) for m in db.session.execute(db.select(MaintenanceOrder)).scalars().all()],
        "devolucoes": [d.to_dict() for d in db.session.execute(db.select(Devolucao)).scalars().all()],
        "settings": _safe_settings_payload(),
        "auditLogs": [a.to_dict() for a in db.session.execute(db.select(AuditLog).order_by(AuditLog.data.desc()).limit(1000)).scalars().all()] if include_audit else [],
    }


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


def _list_backup_files():
    os.makedirs(BACKUP_DIR, exist_ok=True)
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
    os.makedirs(BACKUP_DIR, exist_ok=True)
    raw, checksum = _backup_bytes(generated_by=generated_by, include_audit=cfg["include_audit"])
    filename = f"backup_ticontrol_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{kind}.json"
    path = _backup_file_path(filename)
    if not path:
        raise RuntimeError("Nome de backup inválido.")
    with open(path, "wb") as fh:
        fh.write(raw)
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
    if not cfg["enabled"]:
        return False
    if not cfg.get("last_run"):
        return True
    try:
        last_run = datetime.fromisoformat(cfg["last_run"])
    except ValueError:
        return True
    delta = {"daily": timedelta(days=1), "weekly": timedelta(days=7), "monthly": timedelta(days=30)}[cfg["frequency"]]
    return datetime.now() - last_run >= delta


def _maybe_run_scheduled_backup():
    global _backup_last_check
    now = _time.time()
    if now - _backup_last_check < 300:
        return
    _backup_last_check = now
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


# ═══════════════════════════════════════════════════════════════════════════
# API — AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# API — DASHBOARD & ALERTS
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# EXPORTAÇÃO E BACKUP
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# QR CODE & AUDITORIA
# ═══════════════════════════════════════════════════════════════════════════

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
        ("Microsoft 365 Business","Microsoft",50,47,"2025-07-31",29900,"Assinatura"),
        ("Adobe Creative Cloud","Adobe",5,5,"2025-06-15",4500,"Assinatura"),
        ("Antivírus Kaspersky","Kaspersky",60,53,"2025-09-30",3600,"Anual"),
        ("VPN Cisco AnyConnect","Cisco",30,22,"2026-01-15",8000,"Perpétua"),
        ("AutoCAD 2024","Autodesk",3,3,"2025-05-20",12000,"Assinatura"),
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
        ],
        "devolucoes": [
            ("laudo_status",    "VARCHAR(30)"),
            ("rh_token",        "VARCHAR(64)"),
            ("rh_token_expiry", "TEXT"),
            ("rh_email",        "VARCHAR(120)"),
            ("rh_ciencia_ip",   "VARCHAR(50)"),
            ("rh_data_ciencia", "TEXT"),
            ("cobranca_valor",  "REAL"),
            ("cobranca_obs",    "TEXT"),
        ],
        "laudos_tecnicos": [
            ("editado_em",    "TEXT"),
            ("editado_por",   "VARCHAR(120)"),
            ("motivo_edicao", "TEXT"),
        ],
    }
    is_sqlite = "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]
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
        conn.commit()

    # Garante que as novas tabelas (login_attempts, devolucoes) existam
    db.create_all()


def _export_route_globals():
    """Compatibilidade temporaria para modulos de rotas durante a refatoracao."""
    return {name: value for name, value in globals().items() if not name.startswith("__")}


def register_route_modules():
    """Importa modulos de rotas para registrar os endpoints Flask."""
    from routes import (
        auth, assets, supplies, colaboradores, allocations,
        operations, users, settings, devolucoes, reports,
    )
    return (auth, assets, supplies, colaboradores, allocations, operations, users, settings, devolucoes, reports)

register_route_modules()

with app.app_context():
    db.create_all()
    _migrate_db()
    seed()

if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "1") == "1"

    print("\nTI Control SRE — Flask + Auth + Observabilidade")
    print(f"   DB:    {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"   URL:   {app.config['APP_BASE_URL']}")
    print(f"   Host:  {host}")
    print(f"   Porta: {port}")
    print(f"   Debug: {debug}")
    print(f"   Acesse pela VM: http://IP_DA_VM:{port}\n")

    app.run(host=host, port=port, debug=debug)
