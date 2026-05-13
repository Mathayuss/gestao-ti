"""
TI Control SRE — Sistema de Gestão de Ativos de TI com práticas de confiabilidade

Inclui autenticação, persistência em SQLite, métricas Prometheus, health checks,
request-id, endpoints operacionais e documentação SRE para operação do serviço.
"""
import os, io, uuid, warnings, csv, json, re, time as _time, hashlib, smtplib, base64, logging, html as _html
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
)

db  = SQLAlchemy(app)
lm  = LoginManager(app)
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

@app.route("/login", methods=["GET"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    return render_template("login.html", error=request.args.get("error"), show_demo=app.config["SHOW_DEMO_CREDENTIALS"])

@app.route("/login", methods=["POST"])
def do_login():
    ip = request.remote_addr or "unknown"
    if not _check_login_rate_limit(ip):
        return redirect(url_for("login_page", error="Muitas tentativas. Aguarde um momento."))

    username = (request.form.get("username") or "").strip()
    senha    = request.form.get("senha") or ""
    user = db.session.execute(db.select(SystemUser).filter_by(username=username)).scalar_one_or_none()
    if not user or not user.check_senha(senha):
        return redirect(url_for("login_page", error="Usuário ou senha inválidos"))
    if user.status != "Ativo":
        return redirect(url_for("login_page", error="Conta desativada"))
    _record_login_success(ip)
    from flask import session as flask_session
    flask_session.permanent = True
    login_user(user, remember=True)
    user.ultimo_acesso = datetime.now()
    db.session.commit()
    audit("LOGIN", "auth", username, "Login bem-sucedido")
    db.session.commit()
    requested_next = request.args.get("next")
    next_page = requested_next if is_safe_redirect_url(requested_next) else url_for("index")
    return redirect(next_page)

@app.route("/logout")
@login_required
def do_logout():
    audit("LOGOUT", "auth", current_user.username)
    db.session.commit()
    logout_user()
    return redirect(url_for("login_page"))

@app.route("/api/me")
@login_required
def me():
    return jsonify({"id":current_user.id,"username":current_user.username,
                    "nome":current_user.nome,"perfil":current_user.perfil,
                    "email":current_user.email})

# ═══════════════════════════════════════════════════════════════════════════
# FRONTEND
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/ping")
def ping():
    """Endpoint público para health-check — nunca retorna 401."""
    return jsonify({"ok": True, "authenticated": current_user.is_authenticated,
                    "user": current_user.username if current_user.is_authenticated else None})


@app.route("/health/live")
def health_live():
    """Liveness: usado pelo orquestrador para saber se o processo está vivo."""
    return jsonify({"status": "ok"}), 200


@app.route("/health/startup")
def health_startup():
    """Startup: confirma que a aplicação Flask inicializou."""
    return jsonify({"status": "ok"}), 200


@app.route("/health/ready")
def health_ready():
    """Readiness: usado pelo proxy/orquestrador para liberar tráfego."""
    db_health = _database_health()
    status_code = 200 if db_health["ok"] else 503
    payload = {"status": "ok" if db_health["ok"] else "degraded",
               "checks": {"database": {"ok": db_health["ok"]}}}
    return jsonify(payload), status_code


@app.route("/metrics")
def metrics():
    """Métricas Prometheus — requer token Bearer ou perfil Administrador."""
    metrics_token = os.environ.get("METRICS_TOKEN", "")
    if metrics_token:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {metrics_token}":
            return Response("Unauthorized", status=401,
                            headers={"WWW-Authenticate": "Bearer"})
    elif not current_user.is_authenticated or current_user.perfil != "Administrador":
        return Response("Unauthorized", status=401,
                        headers={"WWW-Authenticate": "Bearer"})
    if not METRICS_OK:
        return jsonify({"error": "prometheus_client não instalado"}), 503
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.route("/")
@login_required
def index():
    return render_template("index.html", app_base_url=app.config["APP_BASE_URL"])

@app.route("/asset/<aid>")
def asset_public(aid):
    a = db.session.get(Asset, aid)
    if not a: return "Ativo não encontrado", 404
    return render_template("asset_public.html", asset=a)

# ═══════════════════════════════════════════════════════════════════════════
# API — ASSETS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/assets", methods=["GET"])
@api_auth
def get_assets():
    q   = request.args.get("q","").lower()
    cat = request.args.get("categoria","")
    stmt = db.select(Asset)
    if q:
        stmt = stmt.where(db.or_(Asset.hostname.ilike(f"%{q}%"),
                                  Asset.colaborador.ilike(f"%{q}%"),
                                  Asset.service_tag.ilike(f"%{q}%"),
                                  Asset.fabricante.ilike(f"%{q}%")))
    if cat:
        stmt = stmt.where(Asset.categoria == cat)
    return jsonify([a.to_dict() for a in db.session.execute(stmt).scalars().all()])

@app.route("/api/assets", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_asset():
    d = request.get_json() or {}
    errors = validate_asset_payload(d)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    a = Asset(id=new_id("A"),
              hostname=clean_text(d.get("hostname"), 80), ip=clean_text(d.get("ip","DHCP"), 40) or "DHCP",
              mac=clean_text(d.get("mac"), 20), service_tag=clean_text(d.get("serviceTag"), 40),
              os=clean_text(d.get("os"), 80), fabricante=clean_text(d.get("fabricante"), 60),
              modelo=clean_text(d.get("modelo"), 80), patrimonio=clean_text(d.get("patrimonio"), 40),
              nf=clean_text(d.get("nf"), 40), categoria=clean_text(d.get("categoria"), 40),
              status=clean_text(d.get("status","Disponível"), 30) or "Disponível",
              colaborador=clean_text(d.get("colaborador"), 120),
              setor=clean_text(d.get("setor"), 80), unidade=clean_text(d.get("unidade"), 80),
              garantia=clean_text(d.get("garantia"), 10) or None)
    db.session.add(a)
    audit("CRIAR", "ativos", a.id, f"Ativo {a.hostname} cadastrado")
    db.session.commit()
    return jsonify(a.to_dict()), 201

@app.route("/api/assets/<aid>", methods=["GET"])
@api_auth
def get_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = a.to_dict()
    d["incidentes"]    = [i.to_dict() for i in db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalars().all()]
    d["alocacoes"]     = [al.to_dict() for al in db.session.execute(db.select(Allocation).filter_by(ativo_id=aid)).scalars().all()]
    d["auditLogs"]     = [l.to_dict() for l in db.session.execute(db.select(AuditLog).filter_by(ref_id=aid).order_by(AuditLog.data.desc()).limit(20)).scalars().all()]
    return jsonify(d)

@app.route("/api/assets/<aid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = request.get_json() or {}
    errors = validate_asset_payload(d, partial=True, exclude_id=aid)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    for k, v, max_len in [("hostname","hostname",80),("ip","ip",40),("mac","mac",20),("serviceTag","service_tag",40),
                  ("os","os",80),("fabricante","fabricante",60),("modelo","modelo",80),
                  ("patrimonio","patrimonio",40),("nf","nf",40),("categoria","categoria",40),
                  ("status","status",30),("colaborador","colaborador",120),
                  ("setor","setor",80),("unidade","unidade",80),("garantia","garantia",10)]:
        if k in d: setattr(a, v, clean_text(d[k], max_len))
    audit("EDITAR", "ativos", aid, f"Ativo {a.hostname} editado")
    db.session.commit()
    return jsonify(a.to_dict())

@app.route("/api/assets/<aid>", methods=["DELETE"])
@requires("Administrador")
def delete_asset(aid):
    """Baixa lógica — não remove fisicamente se houver histórico."""
    a = db.get_or_404(Asset, aid)
    has_allocs  = db.session.execute(db.select(Allocation).filter_by(ativo_id=aid)).scalar_one_or_none()
    has_inc     = db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalar_one_or_none()
    if has_allocs or has_inc:
        a.status = "Baixado"
        audit("BAIXA", "ativos", aid, f"Ativo {a.hostname} marcado como Baixado (histórico preservado)")
        db.session.commit()
        return jsonify({"ok":True, "msg":"Ativo marcado como Baixado (histórico preservado)."})
    db.session.delete(a)
    audit("EXCLUIR", "ativos", aid, f"Ativo {a.hostname} excluído")
    db.session.commit()
    return jsonify({"ok":True, "msg":"Ativo excluído."})


@app.route("/api/assets/<aid>/history")
@api_auth
def get_asset_history(aid):
    """Linha do tempo unificada do ativo: cadastro, edições, alocações,
    manutenções, incidentes, auditorias QR e movimentos de insumo."""
    a = db.get_or_404(Asset, aid)
    events = []

    # ── Mapa auxiliar ───────────────────────────────────────────────────
    _ICONE = {
        "CRIAR":"plus","EDITAR":"edit","BAIXA":"download","EXCLUIR":"trash",
        "AUDITORIA":"mapPin","AUDITORIA_QR_PUBLICA":"smartphone",
        "ALOCAR":"link","ENCERRAR_ALOCACAO":"undo","ASSINAR_TERMO":"check",
        "MANUTENCAO_ABERTA":"wrench","MANUTENCAO_ENCERRADA":"flag",
        "MANUTENCAO_PECA":"package","MANUTENCAO_ATUALIZADA":"clipboard",
        "INCIDENTE":"warning","SAIDA":"package","DEVOLUCAO":"package",
    }
    _COR = {
        "CRIAR":"green","EDITAR":"blue","BAIXA":"red","EXCLUIR":"red",
        "AUDITORIA":"purple","AUDITORIA_QR_PUBLICA":"purple",
        "ALOCAR":"blue","ENCERRAR_ALOCACAO":"green","ASSINAR_TERMO":"green",
        "MANUTENCAO_ABERTA":"amber","MANUTENCAO_ENCERRADA":"green",
        "MANUTENCAO_PECA":"gray","MANUTENCAO_ATUALIZADA":"gray",
        "INCIDENTE":"red","SAIDA":"gray","DEVOLUCAO":"gray",
    }

    def _ev(tipo, acao, descricao, usuario, data_iso, extra=None):
        return {"tipo":tipo,"acao":acao,"descricao":descricao,"usuario":usuario or "sistema",
                "data":data_iso,"icone":_ICONE.get(acao,"clipboard"),"cor":_COR.get(acao,"gray"),
                "extra":extra or {}}

    # 1. Audit logs diretos do ativo (exclui os que já vêm de dados estruturados)
    _skip_acoes = {"ALOCAR","MANUTENCAO_ABERTA","MANUTENCAO_ENCERRADA","INCIDENTE",
                   "MANUTENCAO_PECA","MANUTENCAO_PECA_REMOVIDA","MANUTENCAO_ATUALIZADA"}
    for log in db.session.execute(
            db.select(AuditLog).where(AuditLog.ref_id == aid)
            .order_by(AuditLog.data)).scalars().all():
        if log.acao in _skip_acoes:
            continue
        events.append(_ev("auditoria", log.acao, log.detalhe or log.acao,
                          log.usuario, log.data.isoformat() if log.data else None))

    # 2. Alocações (estruturado — tem dados de termo e status)
    for al in db.session.execute(
            db.select(Allocation).where(Allocation.ativo_id == aid)).scalars().all():
        events.append(_ev("alocacao","ALOCAR",
                          f"Alocado para {al.colaborador} — {al.setor} / {al.unidade}",
                          al.colaborador,
                          (al.data_aloc or "") + "T08:00:00" if al.data_aloc else None,
                          {"alocacaoId":al.id,"termo":al.termo,"termoStatus":al.termo_status,
                           "motivo":al.motivo,"email":al.email}))
        if al.termo_status == "Assinado" and al.data_assinatura:
            events.append(_ev("alocacao","ASSINAR_TERMO",
                              f"Termo {al.termo} assinado digitalmente",
                              al.colaborador,
                              al.data_assinatura.isoformat()))
        if al.data_encerramento:
            events.append(_ev("devolucao","ENCERRAR_ALOCACAO",
                              f"Devolução de {al.colaborador}",
                              al.colaborador,
                              al.data_encerramento + "T17:00:00"))

    # 3. Ordens de manutenção (aberta + encerramento + peças)
    for m in db.session.execute(
            db.select(MaintenanceOrder).where(MaintenanceOrder.asset_id == aid)).scalars().all():
        events.append(_ev("manutencao","MANUTENCAO_ABERTA",
                          f"OS {m.id}: {m.tipo} — {(m.descricao_defeito or '')[:80]}",
                          m.tecnico,
                          (m.data_abertura or "") + "T08:00:00" if m.data_abertura else None,
                          {"osId":m.id,"tipo":m.tipo,"status":m.status}))
        for p in m.parts:
            events.append(_ev("manutencao","MANUTENCAO_PECA",
                              f"Peça: {p.supply_nome} × {p.quantidade} — {p.custo_unitario:.2f}/un",
                              m.tecnico,
                              (m.data_abertura or "") + "T09:00:00" if m.data_abertura else None))
        if m.data_conclusao:
            cor_enc = "green" if m.status == "Concluída" else ("red" if m.status == "Sem reparo" else "gray")
            ic_enc  = "check" if m.status == "Concluída" else ("x" if m.status == "Sem reparo" else "square")
            events.append(_ev("manutencao","MANUTENCAO_ENCERRADA",
                              f"OS {m.id} encerrada: {m.status}"
                              + (f" · custo {m.custo_total:.2f}" if m.custo_total else ""),
                              m.tecnico,
                              m.data_conclusao + "T17:00:00",
                              {"osId":m.id,"status":m.status,"custoTotal":m.custo_total,
                               "icone":ic_enc,"cor":cor_enc}))

    # 4. Incidentes
    for inc in db.session.execute(
            db.select(Incident).where(Incident.ref_id == aid)).scalars().all():
        events.append(_ev("incidente","INCIDENTE",
                          f"{inc.tipo}: {(inc.descricao or '')[:80]}",
                          "sistema",
                          inc.data.isoformat() if inc.data else None,
                          {"incidenteId":inc.id,"status":inc.status}))

    # 5. Movimentos de insumo vinculados a este ativo
    for mov in db.session.execute(
            db.select(SupplyMovement).where(SupplyMovement.ativo_id == aid)).scalars().all():
        events.append(_ev("insumo", mov.tipo,
                          mov.descricao or f"{mov.tipo}: {mov.supply_nome}",
                          mov.colaborador,
                          mov.data.isoformat() if mov.data else None))

    events.sort(key=lambda e: e.get("data") or "")
    return jsonify({"asset": a.to_dict(), "totalEventos": len(events), "eventos": events})


# ═══════════════════════════════════════════════════════════════════════════
# API — SUPPLIES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/supplies", methods=["GET"])
@api_auth
def get_supplies():
    q = request.args.get("q","").lower()
    stmt = db.select(Supply)
    if q: stmt = stmt.where(db.or_(Supply.nome.ilike(f"%{q}%"), Supply.categoria.ilike(f"%{q}%")))
    return jsonify([s.to_dict() for s in db.session.execute(stmt).scalars().all()])

@app.route("/api/supplies", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_supply():
    d = request.get_json() or {}
    if not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do item é obrigatório."}), 400
    s = Supply(id=new_id("S"), nome=clean_text(d.get("nome"), 120), categoria=clean_text(d.get("categoria"), 40),
               unidade=clean_text(d.get("unidade"), 80), estoque=parse_int(d.get("estoque",0), minimum=0),
               minimo=parse_int(d.get("minimo",0), minimum=0), preco=parse_float(d.get("preco",0), minimum=0))
    db.session.add(s)
    m = SupplyMovement(id=new_id("MOV"), tipo="ENTRADA", ref_id=s.id, supply_nome=s.nome,
                       descricao=f"Cadastro inicial: {s.nome}", quantidade=s.estoque, motivo="Cadastro")
    db.session.add(m)
    audit("CRIAR", "insumos", s.id, f"Item {s.nome} cadastrado")
    db.session.commit()
    return jsonify(s.to_dict()), 201

@app.route("/api/supplies/<sid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_supply(sid):
    s = db.get_or_404(Supply, sid)
    d = request.get_json() or {}
    if "nome" in d and not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do item é obrigatório."}), 400
    s.nome = clean_text(d.get("nome", s.nome), 120); s.categoria = clean_text(d.get("categoria", s.categoria), 40)
    s.unidade = clean_text(d.get("unidade", s.unidade), 80); s.minimo = parse_int(d.get("minimo", s.minimo), minimum=0)
    s.preco = parse_float(d.get("preco", s.preco), minimum=0)
    audit("EDITAR", "insumos", sid, f"Item {s.nome} editado")
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/supplies/<sid>/entrada", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_entrada(sid):
    d = request.get_json() or {}
    qty = parse_int(d.get("quantidade",1), default=1, minimum=1)
    s = db.get_or_404(Supply, sid)
    s.estoque += qty
    m = SupplyMovement(id=new_id("MOV"), tipo="ENTRADA", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: +{qty}", quantidade=qty, motivo=d.get("motivo","Entrada"))
    db.session.add(m)
    audit("ENTRADA", "insumos", sid, f"{s.nome}: +{qty}")
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/supplies/<sid>/saida", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_saida(sid):
    d = request.get_json() or {}
    colab   = clean_text(d.get("colaborador"), 120)
    ativo_id= clean_text(d.get("ativoId"), 16)
    motivo  = clean_text(d.get("motivo") or "Saída", 80)
    qty     = parse_int(d.get("quantidade",1), default=1, minimum=1)

    if not colab and not ativo_id:
        return jsonify({"error":"Vincule a saída a um colaborador ou ativo de TI."}), 400
    s = db.get_or_404(Supply, sid)
    if s.estoque < qty:
        return jsonify({"error":f"Estoque insuficiente ({s.estoque} disponível)."}), 400
    if colab and not db.session.execute(db.select(Colaborador).filter_by(nome=colab)).scalar_one_or_none():
        return jsonify({"error":f"Colaborador '{colab}' não encontrado."}), 404
    if ativo_id and not db.session.get(Asset, ativo_id):
        return jsonify({"error":f"Ativo '{ativo_id}' não encontrado."}), 404

    s.estoque -= qty
    dest = f"colaborador {colab}" if colab else f"ativo {ativo_id}"
    m = SupplyMovement(id=new_id("MOV"), tipo="SAIDA", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: -{qty} → {dest}", quantidade=-qty,
                       colaborador=colab, ativo_id=ativo_id, motivo=motivo)
    db.session.add(m)
    audit("SAIDA", "insumos", sid, f"{s.nome}: -{qty} → {dest}")
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/supplies/<sid>/devolucao", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_devolucao(sid):
    d = request.get_json() or {}
    colab = clean_text(d.get("colaborador"), 120)
    qty   = parse_int(d.get("quantidade",1), default=1, minimum=1)
    s = db.get_or_404(Supply, sid)
    s.estoque += qty
    m = SupplyMovement(id=new_id("MOV"), tipo="DEVOLUCAO", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: +{qty} ← {colab or 'N/I'}", quantidade=qty, colaborador=colab)
    db.session.add(m)
    audit("DEVOLUCAO", "insumos", sid, f"{s.nome}: +{qty} ← {colab}")
    db.session.commit()
    return jsonify(s.to_dict())

@app.route("/api/supplies/kit-admissao", methods=["POST"])
@requires("Administrador","Técnico TI")
def kit_admissao():
    d = request.get_json() or {}
    colab = clean_text(d.get("colaborador",""), 120)
    if not colab: return jsonify({"error":"Colaborador obrigatório."}), 400
    items = d.get("items",[])
    # Valida estoque de todos antes de mover qualquer um
    erros = []
    for item in items:
        s = db.session.get(Supply, item.get("id"))
        qty = parse_int(item.get("quantidade",1), default=1, minimum=1)
        if not s: erros.append(f"Item '{item.get('id')}' não encontrado")
        elif s.estoque < qty: erros.append(f"'{s.nome}': estoque insuficiente ({s.estoque} / {qty} pedido)")
    if erros: return jsonify({"error":"Itens com problema:\n"+"\n".join(erros)}), 400

    resultado = []
    for item in items:
        s = db.session.get(Supply, item.get("id")); qty = parse_int(item.get("quantidade",1), default=1, minimum=1)
        s.estoque -= qty
        m = SupplyMovement(id=new_id("MOV"), tipo="SAIDA", ref_id=s.id, supply_nome=s.nome,
                           descricao=f"Kit admissão — {colab}: {s.nome} -{qty}", quantidade=-qty,
                           colaborador=colab, motivo="Kit Admissão")
        db.session.add(m)
        resultado.append({"id":s.id,"nome":s.nome,"retirado":qty,"saldo":s.estoque})
    audit("KIT_ADMISSAO", "insumos", "", f"Kit para {colab}: {len(resultado)} itens")
    db.session.commit()
    return jsonify({"ok":True,"resultado":resultado})

# ═══════════════════════════════════════════════════════════════════════════
# API — COLABORADORES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/colaboradores", methods=["GET"])
@api_auth
def get_colaboradores():
    q=request.args.get("q","").lower(); setor=request.args.get("setor",""); status=request.args.get("status","")
    stmt = db.select(Colaborador)
    if q:      stmt = stmt.where(db.or_(Colaborador.nome.ilike(f"%{q}%"), Colaborador.email.ilike(f"%{q}%"),
                                         Colaborador.cargo.ilike(f"%{q}%"), Colaborador.matricula.ilike(f"%{q}%")))
    if setor:  stmt = stmt.where(Colaborador.setor == setor)
    if status: stmt = stmt.where(Colaborador.status == status)
    return jsonify([c.to_dict() for c in db.session.execute(stmt).scalars().all()])

@app.route("/api/colaboradores", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_colaborador():
    d = request.get_json() or {}
    if not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do colaborador é obrigatório."}), 400
    status = clean_text(d.get("status","Ativo")) or "Ativo"
    if status not in ("Ativo", "Inativo", "Férias", "Afastado"):
        return jsonify({"error":f"Status de colaborador inválido: {status}."}), 400
    err_email = validate_email(d.get("email"))
    if err_email:
        return jsonify({"error": err_email}), 400
    err_phone = validate_phone(d.get("telefone"))
    if err_phone:
        return jsonify({"error": err_phone}), 400
    matricula = clean_text(d.get("matricula"), 40)
    if matricula:
        dup = db.session.execute(db.select(Colaborador).filter_by(matricula=matricula)).scalar_one_or_none()
        if dup:
            return jsonify({"error": f"Matrícula '{matricula}' já cadastrada para {dup.nome}."}), 409
    c = Colaborador(id=new_id("C"), nome=clean_text(d.get("nome"),120), email=clean_text(d.get("email"),120),
                    telefone=clean_text(d.get("telefone"),30), cargo=clean_text(d.get("cargo"),80),
                    setor=clean_text(d.get("setor"),80), unidade=clean_text(d.get("unidade"),80),
                    status=status, matricula=matricula,
                    data_admissao=clean_text(d.get("dataAdmissao"),10) or None, data_cadastro=str(date.today()),
                    observacao=clean_text(d.get("observacao","")))
    db.session.add(c)
    audit("CRIAR", "colaboradores", c.id, f"Colaborador {c.nome} cadastrado")
    db.session.commit()
    return jsonify(c.to_dict()), 201

@app.route("/api/colaboradores/<cid>", methods=["GET"])
@api_auth
def get_colaborador(cid):
    c = db.get_or_404(Colaborador, cid)
    d = c.to_dict()
    d["ativos"]      = [a.to_dict() for a in db.session.execute(db.select(Asset).filter_by(colaborador=c.nome)).scalars().all()]
    d["alocacoes"]   = [al.to_dict(include_items=True) for al in db.session.execute(db.select(Allocation).filter_by(colaborador=c.nome)).scalars().all()]
    d["perifericos"] = perifericos_do_colaborador(c.nome)
    return jsonify(d)

@app.route("/api/colaboradores/<cid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_colaborador(cid):
    c = db.get_or_404(Colaborador, cid)
    d = request.get_json() or {}
    if "nome" in d and not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do colaborador é obrigatório."}), 400
    if "status" in d and clean_text(d.get("status")) not in ("Ativo", "Inativo", "Férias", "Afastado"):
        return jsonify({"error":f"Status de colaborador inválido: {d.get('status')}."}), 400
    if "email" in d:
        err = validate_email(d.get("email"))
        if err:
            return jsonify({"error": err}), 400
    if "telefone" in d:
        err = validate_phone(d.get("telefone"))
        if err:
            return jsonify({"error": err}), 400
    if "matricula" in d:
        mat = clean_text(d.get("matricula"), 40)
        if mat:
            dup = db.session.execute(
                db.select(Colaborador).filter_by(matricula=mat).where(Colaborador.id != cid)
            ).scalar_one_or_none()
            if dup:
                return jsonify({"error": f"Matrícula '{mat}' já cadastrada para {dup.nome}."}), 409
    for k,v,max_len in [("nome","nome",120),("email","email",120),("telefone","telefone",30),("cargo","cargo",80),
                 ("setor","setor",80),("unidade","unidade",80),("status","status",20),
                 ("matricula","matricula",40),("dataAdmissao","data_admissao",10),("observacao","observacao",None)]:
        if k in d: setattr(c, v, clean_text(d[k], max_len))
    audit("EDITAR", "colaboradores", cid, f"Colaborador {c.nome} editado")
    db.session.commit()
    return jsonify(c.to_dict())

@app.route("/api/colaboradores/<cid>", methods=["DELETE"])
@requires("Administrador")
def delete_colaborador(cid):
    c = db.get_or_404(Colaborador, cid)
    if db.session.execute(db.select(Asset).filter_by(colaborador=c.nome)).scalar_one_or_none():
        return jsonify({"error":"Possui ativos alocados. Faça o desligamento primeiro."}), 409
    db.session.delete(c); audit("EXCLUIR","colaboradores",cid,c.nome); db.session.commit()
    return jsonify({"ok":True})

@app.route("/api/colaboradores/<cid>/perifericos")
@api_auth
def get_perifericos_colaborador(cid):
    c = db.get_or_404(Colaborador, cid)
    return jsonify(perifericos_do_colaborador(c.nome))

@app.route("/api/colaboradores/<cid>/offboarding", methods=["POST"])
@requires("Administrador","Técnico TI")
def colaborador_offboarding(cid):
    c = db.get_or_404(Colaborador, cid)
    ativos_dev, perifs_dev = [], []

    for a in db.session.execute(db.select(Asset).filter_by(colaborador=c.nome)).scalars().all():
        a.status="Disponível"; a.colaborador=""; a.setor=""; ativos_dev.append(a.hostname)

    for al in db.session.execute(db.select(Allocation).filter_by(colaborador=c.nome, status="Ativo")).scalars().all():
        al.status="Encerrado"; al.data_encerramento=str(date.today())

    for p in perifericos_do_colaborador(c.nome):
        s = db.session.get(Supply, p["supplyId"])
        if s:
            s.estoque += p["quantidade"]
            m = SupplyMovement(id=new_id("MOV"), tipo="DEVOLUCAO", ref_id=s.id, supply_nome=s.nome,
                               descricao=f"Desligamento {c.nome}: {p['quantidade']}x {s.nome}",
                               quantidade=p["quantidade"], colaborador=c.nome)
            db.session.add(m)
        perifs_dev.append(f"{p['quantidade']}x {p['nome']}")

    c.status="Inativo"; c.data_desligamento=str(date.today())
    audit("DESLIGAMENTO","colaboradores",cid,f"Ativos:{ativos_dev} Periféricos:{perifs_dev}")

    # Cria registro de Devolução com token para assinatura digital
    from datetime import timedelta
    dev_id = new_id("DEV")
    dev_token = uuid.uuid4().hex + uuid.uuid4().hex
    dev = Devolucao(
        id=dev_id, colaborador_id=cid, colaborador=c.nome,
        setor=c.setor or "", unidade=c.unidade or "",
        data_devolucao=str(date.today()),
        sign_token=dev_token,
        sign_token_expiry=datetime.now() + timedelta(days=7),
        status="Pendente",
        ativos_devolvidos=json.dumps(ativos_dev, ensure_ascii=False),
        perifericos_devolvidos=json.dumps(perifs_dev, ensure_ascii=False),
    )
    db.session.add(dev)
    db.session.commit()

    # Envia e-mail com link de assinatura se colaborador tiver e-mail
    link_assinatura = f"{app.config['APP_BASE_URL']}/devolver/{dev_token}"
    email_enviado = False
    if c.email:
        res = send_email_link_devolucao(c.email, c.nome, link_assinatura)
        email_enviado = res.get("ok", False)

    return jsonify({"ok":True,"colaborador":c.nome,"colaboradorId":cid,
                    "setor":c.setor or "—","unidade":c.unidade or "—",
                    "matricula":c.matricula or "—",
                    "ativosDevolvidos":ativos_dev,
                    "perifericosDevolvidos":perifs_dev,"dataDesligamento":str(date.today()),
                    "devolucaoId": dev_id,
                    "linkAssinaturaDevolucao": link_assinatura,
                    "emailEnviado": email_enviado})

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


@app.route("/api/colaboradores/<cid>/termo-devolucao.pdf")
@login_required
def termo_devolucao_pdf(cid):
    if not PDF_OK:
        return jsonify({"error":"Geração de PDF indisponível. Instale: pip install reportlab"}), 503
    c = db.get_or_404(Colaborador, cid)
    data_desl = c.data_desligamento or str(date.today())

    # Busca o registro de Devolução mais recente para este colaborador
    dev = db.session.execute(
        db.select(Devolucao).where(Devolucao.colaborador_id == cid)
        .order_by(Devolucao.data_devolucao.desc())
    ).scalar_one_or_none()

    alocacoes = db.session.execute(
        db.select(Allocation).where(
            Allocation.colaborador == c.nome,
            Allocation.status == "Encerrado",
            Allocation.data_encerramento == data_desl,
        )
    ).scalars().all()

    movs = db.session.execute(
        db.select(SupplyMovement).where(
            SupplyMovement.colaborador == c.nome,
            SupplyMovement.tipo == "DEVOLUCAO",
            func.date(SupplyMovement.data) == data_desl,
        )
    ).scalars().all()

    empresa  = _get_setting("empresa", {}) or {}
    td_cfg   = _get_setting("termo_devolucao", {}) or {}
    logo_b64 = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    ctx = {"colaborador": c.nome, "matricula": c.matricula or "—",
           "setor": c.setor or "—", "unidade": c.unidade or "—",
           "data": data_desl, "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else ""}

    titulo      = _render_termo_text(td_cfg.get("titulo", "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS"), ctx)
    preambulo   = _render_termo_text(td_cfg.get("preambulo", ""), ctx)
    clausulas   = td_cfg.get("clausulas", [])
    rodape_txt  = _render_termo_text(td_cfg.get("rodape", ""), ctx)
    decl_padrao = "Declaro ter devolvido todos os equipamentos listados acima em plenas condições."
    declaracao  = _render_termo_text(td_cfg.get("declaracao", decl_padrao), ctx)

    try:
        buf = io.BytesIO()
        cv = rl_canvas.Canvas(buf, pagesize=A4); w, h = A4

        # Logo e cabeçalho
        if logo_b64:
            _pdf_draw_logo(cv, logo_b64, 2*cm, h-3.5*cm, max_w=3*cm, max_h=1.5*cm)
        cv.setFont("Helvetica-Bold", 15)
        cv.drawCentredString(w/2, h-3*cm, titulo)
        cv.setFont("Helvetica", 10)
        cv.drawCentredString(w/2, h-3.7*cm, f"Data: {data_desl}  —  Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        if isinstance(empresa, dict) and empresa.get("nome"):
            cv.drawCentredString(w/2, h-4.2*cm, empresa["nome"])
        cv.line(2*cm, h-4.6*cm, w-2*cm, h-4.6*cm)

        cv.setFont("Helvetica", 11); y = h-6*cm
        for ln in [
            f"Colaborador : {c.nome}",
            f"Matrícula   : {c.matricula or '—'}",
            f"Setor       : {c.setor or '—'}   Unidade: {c.unidade or '—'}",
            f"Situação    : Desligamento em {data_desl}",
        ]:
            cv.drawString(2*cm, y, ln); y -= 0.65*cm
        y -= 0.4*cm

        if preambulo:
            cv.setFont("Helvetica", 10)
            for linha in preambulo.split("\n"):
                cv.drawString(2*cm, y, linha.strip()); y -= 0.6*cm
            y -= 0.3*cm

        cv.line(2*cm, y, w-2*cm, y); y -= 0.8*cm

        if alocacoes:
            cv.setFont("Helvetica-Bold", 11)
            cv.drawString(2*cm, y, "Equipamentos devolvidos:"); y -= 0.7*cm
            cv.setFont("Courier", 10)
            for al in alocacoes:
                cv.drawString(2.5*cm, y, f"[ATIVO]  {al.ativo_nome}   (Termo: {al.termo or '—'})"); y -= 0.6*cm
                for it in al.items:
                    cv.drawString(3.5*cm, y, f"+ {it.quantidade}x  {it.supply_nome}"); y -= 0.55*cm
            y -= 0.3*cm

        if movs:
            cv.setFont("Helvetica-Bold", 11)
            cv.drawString(2*cm, y, "Insumos / periféricos devolvidos:"); y -= 0.7*cm
            cv.setFont("Courier", 10)
            for mv in movs:
                cv.drawString(2.5*cm, y, f"• {mv.descricao}"); y -= 0.6*cm
            y -= 0.3*cm

        if not alocacoes and not movs:
            cv.setFont("Helvetica", 11)
            cv.drawString(2*cm, y, "Nenhum equipamento registrado para devolução."); y -= 0.7*cm

        if clausulas:
            cv.setFont("Helvetica", 10)
            for cl in clausulas:
                cv.drawString(2*cm, y, _render_termo_text(cl, ctx)); y -= 0.6*cm
            y -= 0.3*cm

        cv.line(2*cm, y, w-2*cm, y); y -= 0.5*cm
        cv.setFont("Helvetica", 10)
        cv.drawString(2*cm, y, declaracao); y -= 1.2*cm

        # Assinatura digital (se já capturada no Devolucao)
        if dev and dev.assinatura_img and dev.assinatura_img.startswith("data:image/png;base64,"):
            from reportlab.lib.utils import ImageReader as _IR
            raw_dev = base64.b64decode(dev.assinatura_img.split(",", 1)[1])
            cv.drawImage(_IR(io.BytesIO(raw_dev)), 2*cm, y-1.8*cm, width=5*cm, height=1.8*cm,
                        preserveAspectRatio=True, mask="auto")
            cv.setFont("Helvetica-Bold", 9)
            cv.drawString(2*cm, y-2.1*cm,
                          f"Assinado digitalmente em {dev.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {dev.assinatura_ip or '—'}")
            y -= 2.4*cm

        cv.line(2*cm, y, 9*cm, y); cv.line(12*cm, y, w-2*cm, y); y -= 0.5*cm
        cv.setFont("Helvetica", 9)
        cv.drawCentredString(5.5*cm, y, c.nome)
        cv.drawCentredString(16*cm, y, "Responsável TI")

        if rodape_txt:
            cv.setFont("Helvetica", 8)
            cv.setFillColorRGB(0.5, 0.5, 0.5)
            cv.drawCentredString(w/2, 1.5*cm, rodape_txt)
            cv.setFillColorRGB(0, 0, 0)

        cv.save(); buf.seek(0)
        nome_pdf = f"devolucao_{safe_filename(c.nome)}_{data_desl}.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)
    except Exception as exc:
        return jsonify({"error": f"Erro ao gerar PDF: {exc.__class__.__name__} — {exc}"}), 500


@app.route("/api/devolucoes/<did>/termo.pdf")
@login_required
def devolucao_pdf(did):
    """PDF do Termo de Devolução a partir do registro Devolucao (com assinatura digital)."""
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível."}), 503
    dev = db.get_or_404(Devolucao, did)
    c   = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None

    empresa  = _get_setting("empresa", {}) or {}
    td_cfg   = _get_setting("termo_devolucao", {}) or {}
    logo_b64 = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    ctx = {"colaborador": dev.colaborador, "setor": dev.setor or "—",
           "unidade": dev.unidade or "—", "data": dev.data_devolucao or str(date.today()),
           "matricula": (c.matricula if c else "—") or "—",
           "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else ""}

    titulo   = _render_termo_text(td_cfg.get("titulo", "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS"), ctx)
    preambulo= _render_termo_text(td_cfg.get("preambulo", ""), ctx)
    clausulas= td_cfg.get("clausulas", [])
    rodape_txt = _render_termo_text(td_cfg.get("rodape", ""), ctx)
    decl_padrao= "Declaro ter devolvido todos os equipamentos listados acima em plenas condições."
    declaracao = _render_termo_text(td_cfg.get("declaracao", decl_padrao), ctx)

    try:
        buf = io.BytesIO()
        cv  = rl_canvas.Canvas(buf, pagesize=A4); w, h = A4

        if logo_b64:
            _pdf_draw_logo(cv, logo_b64, 2*cm, h-3.5*cm, max_w=3*cm, max_h=1.5*cm)
        cv.setFont("Helvetica-Bold", 15)
        cv.drawCentredString(w/2, h-3*cm, titulo)
        cv.setFont("Helvetica", 10)
        cv.drawCentredString(w/2, h-3.7*cm, f"Data: {dev.data_devolucao}  —  Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        cv.line(2*cm, h-4.2*cm, w-2*cm, h-4.2*cm)

        cv.setFont("Helvetica", 11); y = h-5.5*cm
        cv.drawString(2*cm, y, f"Colaborador : {dev.colaborador}"); y -= 0.65*cm
        if c:
            cv.drawString(2*cm, y, f"Matrícula   : {c.matricula or '—'}"); y -= 0.65*cm
        cv.drawString(2*cm, y, f"Setor       : {dev.setor or '—'}   Unidade: {dev.unidade or '—'}"); y -= 0.65*cm

        if preambulo:
            y -= 0.3*cm
            cv.setFont("Helvetica", 10)
            for linha in preambulo.split("\n"):
                cv.drawString(2*cm, y, linha.strip()); y -= 0.6*cm

        y -= 0.4*cm
        cv.line(2*cm, y, w-2*cm, y); y -= 0.8*cm

        ativos = json.loads(dev.ativos_devolvidos or "[]")
        perifs = json.loads(dev.perifericos_devolvidos or "[]")

        if ativos:
            cv.setFont("Helvetica-Bold", 11)
            cv.drawString(2*cm, y, "Equipamentos devolvidos:"); y -= 0.7*cm
            cv.setFont("Courier", 10)
            for item in ativos:
                cv.drawString(2.5*cm, y, f"[ATIVO]  {item}"); y -= 0.6*cm
            y -= 0.3*cm

        if perifs:
            cv.setFont("Helvetica-Bold", 11)
            cv.drawString(2*cm, y, "Periféricos / insumos devolvidos:"); y -= 0.7*cm
            cv.setFont("Courier", 10)
            for item in perifs:
                cv.drawString(2.5*cm, y, f"• {item}"); y -= 0.6*cm
            y -= 0.3*cm

        if clausulas:
            cv.setFont("Helvetica", 10)
            for cl in clausulas:
                cv.drawString(2*cm, y, _render_termo_text(cl, ctx)); y -= 0.6*cm
            y -= 0.3*cm

        cv.line(2*cm, y, w-2*cm, y); y -= 0.5*cm
        cv.setFont("Helvetica", 10)
        cv.drawString(2*cm, y, declaracao); y -= 1.2*cm

        if dev.status == "Assinado" and dev.assinatura_img and dev.assinatura_img.startswith("data:image/png;base64,"):
            from reportlab.lib.utils import ImageReader as _IR
            raw = base64.b64decode(dev.assinatura_img.split(",", 1)[1])
            cv.drawImage(_IR(io.BytesIO(raw)), 2*cm, y-1.8*cm, width=5*cm, height=1.8*cm,
                        preserveAspectRatio=True, mask="auto")
            cv.setFont("Helvetica-Bold", 9)
            cv.drawString(2*cm, y-2.1*cm,
                          f"Assinado em {dev.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {dev.assinatura_ip or '—'}")
            y -= 2.4*cm

        cv.line(2*cm, y, 9*cm, y); cv.line(12*cm, y, w-2*cm, y); y -= 0.5*cm
        cv.setFont("Helvetica", 9)
        cv.drawCentredString(5.5*cm, y, dev.colaborador)
        cv.drawCentredString(16*cm, y, "Responsável TI")

        if rodape_txt:
            cv.setFont("Helvetica", 8)
            cv.setFillColorRGB(0.5, 0.5, 0.5)
            cv.drawCentredString(w/2, 1.5*cm, rodape_txt)

        cv.save(); buf.seek(0)
        nome_pdf = f"devolucao_{safe_filename(dev.colaborador)}_{dev.data_devolucao}.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)
    except Exception as exc:
        return jsonify({"error": f"Erro ao gerar PDF: {exc.__class__.__name__} — {exc}"}), 500

@app.route("/api/colaboradores/stats")
@api_auth
def colaboradores_stats():
    cols = db.session.execute(db.select(Colaborador)).scalars().all()
    ps = {}
    for c in cols: ps[c.setor or "—"] = ps.get(c.setor or "—", 0) + 1
    com_ativos = db.session.query(func.count(func.distinct(Asset.colaborador)))\
                   .filter(Asset.colaborador != "").scalar()
    return jsonify({"total":len(cols),"ativos":sum(1 for c in cols if c.status=="Ativo"),
                    "inativos":sum(1 for c in cols if c.status=="Inativo"),
                    "afastados":sum(1 for c in cols if c.status in ("Afastado","Férias")),
                    "porSetor":ps,"comAtivos":com_ativos or 0})

# ═══════════════════════════════════════════════════════════════════════════
# API — ALLOCATIONS (transacional)
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/allocations", methods=["GET"])
@api_auth
def get_allocations():
    q = request.args.get("q","").lower()
    stmt = db.select(Allocation)
    if q: stmt = stmt.where(db.or_(Allocation.colaborador.ilike(f"%{q}%"),
                                    Allocation.ativo_nome.ilike(f"%{q}%"),
                                    Allocation.setor.ilike(f"%{q}%")))
    return jsonify([a.to_dict(include_items=True) for a in db.session.execute(stmt).scalars().all()])

@app.route("/api/allocations", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_allocation():
    d = request.get_json() or {}
    erros = []
    regras = _get_setting("regras_usuario", {})

    # ── Valida ativo ─────────────────────────────────────────────────────
    asset = db.session.get(Asset, d.get("ativo",""))
    if not asset: erros.append("Ativo não encontrado.")
    elif asset.status not in ("Disponível","Ativo"):
        erros.append(f"Ativo não disponível para alocação (status: {asset.status}).")
    elif db.session.execute(db.select(Allocation).filter_by(ativo_id=asset.id, status="Ativo")).scalar_one_or_none():
        erros.append("Ativo já possui alocação ativa.")

    # ── Valida colaborador ───────────────────────────────────────────────
    colab_nome = clean_text(d.get("colaborador", ""), 120)
    colab = db.session.execute(db.select(Colaborador).filter_by(nome=colab_nome)).scalar_one_or_none()
    if not colab: erros.append(f"Colaborador '{colab_nome}' não encontrado.")
    elif colab.status not in ("Ativo","Férias"):
        erros.append(f"Colaborador com status '{colab.status}' não pode receber alocação.")
    elif not regras.get("permite_alocar_sem_email", False) and not clean_text(d.get("email") or colab.email):
        erros.append("Colaborador sem e-mail. Configure a exceção ou cadastre um e-mail antes da alocação.")

    # ── Valida periféricos — verifica estoque antes de qualquer mudança ──
    perifericos_in = d.get("perifericos",[]) or []
    total_perifericos = 0
    for p in perifericos_in:
        s = db.session.get(Supply, p.get("supplyId",""))
        qty = parse_int(p.get("quantidade",1), default=1, minimum=1)
        p["quantidade"] = qty
        total_perifericos += qty
        if not s: erros.append(f"Periférico '{p.get('supplyId')}' não encontrado.")
        elif s.estoque < qty: erros.append(f"'{s.nome}': estoque insuficiente ({s.estoque} disponível, {qty} solicitado).")
    max_perifs = parse_int(regras.get("max_perifericos_por_colab", 0), default=0, minimum=0)
    if max_perifs and total_perifericos > max_perifs:
        erros.append(f"Quantidade de periféricos acima do limite configurado ({total_perifericos}/{max_perifs}).")

    if erros:
        return jsonify({"error":"Alocação cancelada:\n" + "\n".join(erros)}), 400

    # ── Tudo OK — executa transação ──────────────────────────────────────
    aid = new_id("AL")
    alloc = Allocation(
        id=aid, ativo_id=asset.id,
        ativo_nome=f"{asset.hostname} ({asset.fabricante} {asset.modelo})",
        colaborador=colab.nome, setor=clean_text(d.get("setor") or colab.setor, 80),
        unidade=clean_text(d.get("unidade") or colab.unidade, 80), email=clean_text(d.get("email") or colab.email, 120),
        data_aloc=str(date.today()), motivo=clean_text(d.get("motivo") or "Uso contínuo", 80),
        status="Ativo", termo=f"TERMO-{aid}", termo_status="Pendente",
    )
    db.session.add(alloc)

    asset.status="Alocado"; asset.colaborador=colab.nome
    asset.setor=alloc.setor; asset.unidade=alloc.unidade

    # Baixa periféricos e cria AllocationItems
    for p in perifericos_in:
        s = db.session.get(Supply, p["supplyId"]); qty = parse_int(p["quantidade"], default=1, minimum=1)
        s.estoque -= qty
        db.session.add(AllocationItem(
            id=new_id("AI"), allocation_id=aid,
            supply_id=s.id, supply_nome=s.nome, quantidade=qty,
        ))
        db.session.add(SupplyMovement(
            id=new_id("MOV"), tipo="SAIDA", ref_id=s.id, supply_nome=s.nome,
            descricao=f"Alocação {aid} — {colab.nome}: {s.nome} x{qty}", quantidade=-qty,
            colaborador=colab.nome, motivo="Alocação",
        ))

    audit("ALOCACAO","alocacoes",aid,f"{asset.hostname} → {colab.nome} ({len(perifericos_in)} periféricos)")
    db.session.commit()
    return jsonify(alloc.to_dict(include_items=True)), 201

@app.route("/api/allocations/<aid>/sign", methods=["POST"])
@requires("Administrador","Técnico TI")
def sign_termo(aid):
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo":
        return jsonify({"error":"Não é possível assinar termo de alocação encerrada."}), 400
    al.termo_status="Assinado"; al.data_assinatura=datetime.now()
    al.assinatura_ip=request.remote_addr
    audit("ASSINAR_TERMO","alocacoes",aid,f"Termo {al.termo} assinado")
    db.session.commit()
    return jsonify(al.to_dict())

@app.route("/api/allocations/<aid>/perifericos")
@api_auth
def alloc_perifericos(aid):
    al = db.get_or_404(Allocation, aid)
    return jsonify([i.to_dict() for i in al.items])

@app.route("/api/allocations/<aid>/termo.pdf")
@login_required
def gerar_termo(aid):
    al = db.get_or_404(Allocation, aid)
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível. Instale: pip install reportlab"}), 503

    empresa   = _get_setting("empresa", {}) or {}
    tr_cfg    = _get_setting("termo_recebimento", {}) or {}
    logo_b64  = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    ctx = {"colaborador": al.colaborador, "setor": al.setor, "unidade": al.unidade,
           "ativo": al.ativo_nome, "data": al.data_aloc, "termo": al.termo or aid,
           "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else ""}

    titulo    = _render_termo_text(tr_cfg.get("titulo", "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO"), ctx)
    preambulo = _render_termo_text(
        tr_cfg.get("preambulo",
                   "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\n"
                   "declaro ter recebido os seguintes equipamentos de propriedade da empresa:"), ctx)
    clausulas_padrao = [
        "Comprometo-me a:",
        "  1. Utilizar exclusivamente para fins profissionais;",
        "  2. Zelar pela conservação de todos os itens;",
        "  3. Comunicar ao TI qualquer dano, perda ou furto;",
        "  4. Devolver os equipamentos ao encerramento do vínculo.",
    ]
    clausulas = tr_cfg.get("clausulas", clausulas_padrao)
    rodape_txt= _render_termo_text(tr_cfg.get("rodape", ""), ctx)

    try:
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4); w, h = A4

        if logo_b64:
            _pdf_draw_logo(c, logo_b64, 2*cm, h-3.5*cm, max_w=3*cm, max_h=1.5*cm)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(w/2, h-3*cm, titulo)
        c.setFont("Helvetica", 10)
        c.drawCentredString(w/2, h-3.7*cm, f"Nº {al.termo}  —  Data: {al.data_aloc}")
        if isinstance(empresa, dict) and empresa.get("nome"):
            c.drawCentredString(w/2, h-4.2*cm, empresa["nome"])
        c.line(2*cm, h-4.6*cm, w-2*cm, h-4.6*cm)
        c.setFont("Helvetica", 11); y = h-6*cm

        for linha in preambulo.split("\n"):
            c.drawString(2*cm, y, linha.strip()); y -= 0.7*cm
        y -= 0.3*cm
        c.setFillColorRGB(0.93, 0.93, 0.93); c.rect(2*cm, y-0.5*cm, w-4*cm, 1*cm, fill=True, stroke=False)
        c.setFillColorRGB(0,0,0); c.setFont("Courier-Bold", 11)
        c.drawString(2.5*cm, y, f"[ATIVO]  {al.ativo_nome}"); y -= 1.5*cm
        items = al.items
        if items:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(2*cm, y, "Periféricos entregues nesta alocação:"); y -= 0.7*cm
            c.setFont("Courier", 10)
            for p in items:
                c.drawString(2.5*cm, y, f"• {p.quantidade}x  {p.supply_nome}"); y -= 0.6*cm
            y -= 0.3*cm
        c.setFont("Helvetica", 10)
        for cl in clausulas:
            c.drawString(2*cm, y, _render_termo_text(cl, ctx)); y -= 0.6*cm

        if al.termo_status == "Assinado" and al.data_assinatura:
            y -= 0.3*cm
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2*cm, y, f"Assinado em {al.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {al.assinatura_ip or '—'}")
            y -= 0.5*cm

        y -= 0.5*cm
        from reportlab.lib.utils import ImageReader as _IR
        # Assinatura colaborador
        if al.assinatura_img and al.assinatura_img.startswith("data:image/png;base64,"):
            raw_col = base64.b64decode(al.assinatura_img.split(",",1)[1])
            c.drawImage(_IR(io.BytesIO(raw_col)), 2*cm, y-1.8*cm, width=5*cm, height=1.8*cm,
                        preserveAspectRatio=True, mask="auto")
        c.line(2*cm, y, 9*cm, y)
        # Assinatura TI
        if al.assinatura_ti_img and al.assinatura_ti_img.startswith("data:image/png;base64,"):
            raw_ti = base64.b64decode(al.assinatura_ti_img.split(",",1)[1])
            c.drawImage(_IR(io.BytesIO(raw_ti)), 12*cm, y-1.8*cm, width=5*cm, height=1.8*cm,
                        preserveAspectRatio=True, mask="auto")
        c.line(12*cm, y, w-2*cm, y)
        y -= 0.5*cm
        c.setFont("Helvetica", 9)
        c.drawCentredString(5.5*cm, y, al.colaborador)
        ti_label = al.assinatura_ti_nome or "Responsável TI"
        c.drawCentredString(16*cm, y, ti_label)

        if rodape_txt:
            c.setFont("Helvetica", 8)
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawCentredString(w/2, 1.5*cm, rodape_txt)

        c.save(); buf.seek(0)
        nome_pdf = f"termo_{safe_filename(al.colaborador)}_{safe_filename(al.termo or aid)}.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)
    except Exception as exc:
        return jsonify({"error": f"Erro ao gerar PDF: {exc.__class__.__name__} — {exc}"}), 500

@app.route("/api/allocations/<aid>/assinatura.png")
@login_required
def get_assinatura_img(aid):
    al = db.get_or_404(Allocation, aid)
    if not al.assinatura_img or not al.assinatura_img.startswith("data:image/png;base64,"):
        return jsonify({"error":"Sem assinatura capturada."}), 404
    import base64
    raw = base64.b64decode(al.assinatura_img.split(",", 1)[1])
    return Response(raw, mimetype="image/png",
                    headers={"Cache-Control":"private, max-age=3600"})

@app.route("/api/allocations/<aid>/assinatura-ti.png")
@login_required
def get_assinatura_ti_img(aid):
    al = db.get_or_404(Allocation, aid)
    if not al.assinatura_ti_img or not al.assinatura_ti_img.startswith("data:image/png;base64,"):
        return jsonify({"error":"Sem assinatura TI capturada."}), 404
    import base64
    raw = base64.b64decode(al.assinatura_ti_img.split(",", 1)[1])
    return Response(raw, mimetype="image/png",
                    headers={"Cache-Control":"private, max-age=3600"})

@app.route("/api/allocations/<aid>/sign-ti", methods=["POST"])
@requires("Administrador","Técnico TI")
def sign_termo_ti(aid):
    al = db.get_or_404(Allocation, aid)
    d = request.get_json(silent=True) or {}
    sig_data = d.get("assinatura","").strip()
    nome_ti  = d.get("nomeTi","").strip() or current_user.username
    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return jsonify({"error":"Assinatura inválida."}), 400
    al.assinatura_ti_img  = sig_data
    al.assinatura_ti_nome = nome_ti
    al.data_assinatura_ti = datetime.now()
    audit("ASSINAR_TERMO_TI","alocacoes",aid,f"Termo {al.termo} assinado pelo responsável TI: {nome_ti}")
    db.session.commit()
    return jsonify(al.to_dict())

# ── Assinatura remota ────────────────────────────────────────────────────

@app.route("/api/allocations/<aid>/sign-link", methods=["POST"])
@requires("Administrador","Técnico TI")
def gerar_link_assinatura(aid):
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo":
        return jsonify({"error":"Alocação encerrada — não é possível gerar link."}), 400
    if al.termo_status == "Assinado":
        return jsonify({"error":"Termo já assinado."}), 400
    from datetime import timedelta
    token = uuid.uuid4().hex + uuid.uuid4().hex   # 64 chars
    al.sign_token = token
    al.sign_token_expiry = datetime.now() + timedelta(days=7)
    audit("GERAR_LINK_ASSINATURA","alocacoes",aid,f"Link de assinatura gerado para {al.colaborador}")
    db.session.commit()
    url = f"{app.config['APP_BASE_URL']}/assinar/{token}"
    email_enviado = False
    if al.email:
        res = send_email_link_assinatura(al.email, al.colaborador, al.ativo_nome, url)
        email_enviado = res.get("ok", False)
    return jsonify({"url": url, "expiry": al.sign_token_expiry.isoformat(),
                    "emailEnviado": email_enviado})


@app.route("/api/allocations/<aid>/qrcode-termo")
@login_required
def allocation_qrcode_termo(aid):
    """Gera QR Code PNG do link de assinatura. Cria token automaticamente se ausente/expirado."""
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo" or al.termo_status == "Assinado":
        abort(404)
    from datetime import timedelta
    now = datetime.now()
    if not al.sign_token or (al.sign_token_expiry and al.sign_token_expiry < now):
        al.sign_token = uuid.uuid4().hex + uuid.uuid4().hex
        al.sign_token_expiry = now + timedelta(days=7)
        db.session.commit()
    url = f"{app.config['APP_BASE_URL']}/assinar/{al.sign_token}"
    if QR_OK:
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
           f'<rect width="200" height="200" fill="white"/>'
           f'<text x="100" y="90" text-anchor="middle" font-size="11" fill="#333">QR não disponível</text>'
           f'<text x="100" y="112" text-anchor="middle" font-size="8" fill="#666">instale qrcode[pil]</text>'
           f'</svg>')
    return svg, 200, {"Content-Type": "image/svg+xml"}


@app.route("/assinar/<token>", methods=["GET"])
def pagina_assinatura(token):
    al = db.session.execute(
        db.select(Allocation).filter_by(sign_token=token)
    ).scalar_one_or_none()
    erro = None
    if al is None:
        erro = "Link inválido ou não encontrado."
    elif al.termo_status == "Assinado":
        erro = "Este termo já foi assinado."
    elif al.sign_token_expiry and datetime.now() > al.sign_token_expiry:
        erro = "Este link de assinatura expirou."
    elif al.status != "Ativo":
        erro = "Esta alocação foi encerrada."

    perifericos = al.items if al else []
    return render_template("assinar.html", al=al, erro=erro,
                           perifericos=perifericos, token=token)


@app.route("/assinar/<token>", methods=["POST"])
def submeter_assinatura(token):
    al = db.session.execute(
        db.select(Allocation).filter_by(sign_token=token)
    ).scalar_one_or_none()
    if al is None:
        return render_template("assinar.html", al=None, token=token,
                               erro="Link inválido.", perifericos=[])
    if al.termo_status == "Assinado":
        return render_template("assinar.html", al=al, token=token,
                               erro="Já assinado.", perifericos=al.items)
    if al.sign_token_expiry and datetime.now() > al.sign_token_expiry:
        return render_template("assinar.html", al=al, token=token,
                               erro="Link expirado.", perifericos=al.items)

    sig_data = request.form.get("assinatura", "").strip()
    nome     = request.form.get("nome_confirm", "").strip()

    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return render_template("assinar.html", al=al, token=token, perifericos=al.items,
                               erro="Assinatura não capturada. Desenhe sua assinatura antes de confirmar.")
    if nome.lower() != al.colaborador.split()[0].lower() and nome.lower() != al.colaborador.lower():
        return render_template("assinar.html", al=al, token=token, perifericos=al.items,
                               erro=f"Nome digitado não confere. Digite seu primeiro nome ou nome completo.")

    al.assinatura_img  = sig_data
    al.termo_status    = "Assinado"
    al.data_assinatura = datetime.now()
    al.assinatura_ip   = request.remote_addr
    al.sign_token      = None   # invalida o link após uso
    al.sign_token_expiry = None
    audit("ASSINAR_TERMO_REMOTO","alocacoes",al.id,
          f"Termo {al.termo} assinado remotamente por {al.colaborador}")
    db.session.commit()
    return render_template("assinar.html", al=al, token=token,
                           sucesso=True, perifericos=al.items)

# ═══════════════════════════════════════════════════════════════════════════
# API — LICENSES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/licenses", methods=["GET"])
@api_auth
def get_licenses(): return jsonify([l.to_dict() for l in db.session.execute(db.select(License)).scalars().all()])

@app.route("/api/licenses", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_license():
    d = request.get_json()
    l = License(id=new_id("L"), software=d.get("software",""), fornecedor=d.get("fornecedor",""),
                total=int(d.get("total",0)), atribuidas=int(d.get("atribuidas",0)),
                vencimento=d.get("vencimento"), custo=float(d.get("custo",0)),
                tipo=d.get("tipo","Assinatura"))
    db.session.add(l); db.session.commit(); return jsonify(l.to_dict()), 201

@app.route("/api/licenses/<lid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_license(lid):
    l = db.get_or_404(License, lid); d = request.get_json()
    for k,v in [("software","software"),("fornecedor","fornecedor"),("tipo","tipo"),
                 ("vencimento","vencimento")]:
        if k in d: setattr(l, v, d[k])
    if "total"      in d: l.total = int(d["total"])
    if "atribuidas" in d: l.atribuidas = int(d["atribuidas"])
    if "custo"      in d: l.custo = float(d["custo"])
    db.session.commit(); return jsonify(l.to_dict())

# ═══════════════════════════════════════════════════════════════════════════
# API — INCIDENTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/incidents", methods=["GET"])
@api_auth
def get_incidents():
    ref = request.args.get("refId")
    qry = db.session.execute(db.select(Incident).filter_by(ref_id=ref)).scalars() if ref else Incident.query
    return jsonify([i.to_dict() for i in qry.all()])

@app.route("/api/incidents", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_incident():
    d = request.get_json() or {}
    ref_id   = clean_text(d.get("refId", ""), 16)
    tipo     = clean_text(d.get("tipo", ""), 40)
    descricao= clean_text(d.get("descricao", ""))
    if not tipo:
        return jsonify({"error": "Tipo do incidente é obrigatório."}), 400
    if not descricao:
        return jsonify({"error": "Descrição do incidente é obrigatória."}), 400
    if ref_id:
        asset_ok  = db.session.get(Asset, ref_id)
        supply_ok = db.session.get(Supply, ref_id)
        if not asset_ok and not supply_ok:
            return jsonify({"error": f"Referência '{ref_id}' não encontrada como Ativo ou Insumo."}), 404
    i = Incident(id=new_id("INC"), ref_id=ref_id, tipo=tipo, descricao=descricao)
    db.session.add(i); audit("INCIDENTE","ativos",i.ref_id,f"{i.tipo}: {i.descricao[:80]}")
    db.session.commit(); return jsonify(i.to_dict()), 201

# ═══════════════════════════════════════════════════════════════════════════
# API — MANUTENÇÃO
# ═══════════════════════════════════════════════════════════════════════════

MANUT_STATUS = ["Aberta","Em análise","Aguardando peça","Em reparo","Concluída","Sem reparo","Cancelada"]
MANUT_TIPO   = ["Corretiva","Preventiva","Melhoria"]
MANUT_ENCERRA = ["Concluída","Sem reparo","Cancelada"]


@app.route("/api/maintenance", methods=["GET"])
@api_auth
def get_maintenance():
    status   = request.args.get("status", "")
    asset_id = request.args.get("assetId", "")
    stmt = db.select(MaintenanceOrder).order_by(MaintenanceOrder.data_abertura.desc())
    if status:   stmt = stmt.where(MaintenanceOrder.status == status)
    if asset_id: stmt = stmt.where(MaintenanceOrder.asset_id == asset_id)
    return jsonify([m.to_dict() for m in db.session.execute(stmt).scalars().all()])


@app.route("/api/maintenance", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_maintenance():
    d = request.get_json() or {}
    asset_id = clean_text(d.get("assetId",""), 16)
    if not asset_id:
        return jsonify({"error":"ID do ativo é obrigatório."}), 400
    a = db.session.get(Asset, asset_id)
    if not a:
        return jsonify({"error":"Ativo não encontrado."}), 404
    tipo = clean_text(d.get("tipo","Corretiva"), 40)
    if tipo not in MANUT_TIPO:
        return jsonify({"error":f"Tipo inválido. Use: {', '.join(MANUT_TIPO)}."}), 400
    descricao = clean_text(d.get("descricaoDefeito",""))
    if not descricao:
        return jsonify({"error":"Descrição do defeito é obrigatória."}), 400
    status_anterior = a.status
    a.status = "Manutenção"
    m = MaintenanceOrder(
        id=new_id("MO"), asset_id=asset_id,
        asset_nome=f"{a.hostname} — {a.fabricante} {a.modelo}",
        tipo=tipo, status="Aberta", status_anterior=status_anterior,
        descricao_defeito=descricao,
        tecnico=clean_text(d.get("tecnico",""), 120),
        data_abertura=str(date.today()),
        observacao=clean_text(d.get("observacao",""))
    )
    db.session.add(m)
    audit("MANUTENCAO_ABERTA","manutencao",asset_id,f"OS {m.id}: {tipo} — {descricao[:80]}")
    db.session.commit()
    return jsonify(m.to_dict()), 201


@app.route("/api/maintenance/<mid>", methods=["GET"])
@api_auth
def get_maintenance_order(mid):
    return jsonify(db.get_or_404(MaintenanceOrder, mid).to_dict(include_parts=True))


@app.route("/api/maintenance/<mid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_maintenance(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem já encerrada."}), 400
    d = request.get_json() or {}
    if "status" in d:
        if d["status"] not in MANUT_STATUS:
            return jsonify({"error":"Status inválido."}), 400
        m.status = d["status"]
    for k, attr in [("diagnostico","diagnostico"),("tecnico","tecnico"),("observacao","observacao")]:
        if k in d: setattr(m, attr, clean_text(d[k]))
    if "custoTotal" in d: m.custo_total = parse_float(d["custoTotal"], minimum=0)
    audit("MANUTENCAO_ATUALIZADA","manutencao",mid,f"Status: {m.status}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))


@app.route("/api/maintenance/<mid>/parts", methods=["POST"])
@requires("Administrador","Técnico TI")
def add_maintenance_part(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem encerrada."}), 400
    d = request.get_json() or {}
    supply_id   = clean_text(d.get("supplyId",""), 16)
    qty         = parse_int(d.get("quantidade",1), default=1, minimum=1)
    custo_unit  = parse_float(d.get("custoUnitario",0), minimum=0)
    if not supply_id:
        return jsonify({"error":"Supply ID é obrigatório."}), 400
    s = db.session.get(Supply, supply_id)
    if not s:
        return jsonify({"error":"Item não encontrado no estoque."}), 404
    if s.estoque < qty:
        return jsonify({"error":f"Estoque insuficiente ({s.estoque} disponível)."}), 400
    s.estoque -= qty
    db.session.add(SupplyMovement(
        id=new_id("MOV"), tipo="SAIDA", ref_id=supply_id, supply_nome=s.nome,
        descricao=f"Manutenção {mid}: {s.nome} -{qty}", quantidade=-qty,
        ativo_id=m.asset_id, motivo=f"OS {mid}"))
    p = MaintenancePart(id=new_id("MP"), maintenance_id=mid, supply_id=supply_id,
                        supply_nome=s.nome, quantidade=qty, custo_unitario=custo_unit)
    m.custo_total = round(m.custo_total + qty * custo_unit, 2)
    db.session.add(p)
    audit("MANUTENCAO_PECA","manutencao",mid,f"Peça: {s.nome} x{qty}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True)), 201


@app.route("/api/maintenance/<mid>/parts/<pid>", methods=["DELETE"])
@requires("Administrador","Técnico TI")
def remove_maintenance_part(mid, pid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem encerrada."}), 400
    p = db.get_or_404(MaintenancePart, pid)
    if p.maintenance_id != mid:
        return jsonify({"error":"Peça não pertence a esta OS."}), 400
    s = db.session.get(Supply, p.supply_id)
    if s:
        s.estoque += p.quantidade
        db.session.add(SupplyMovement(
            id=new_id("MOV"), tipo="DEVOLUCAO", ref_id=p.supply_id, supply_nome=p.supply_nome,
            descricao=f"Estorno OS {mid}: {p.supply_nome} +{p.quantidade}",
            quantidade=p.quantidade, ativo_id=m.asset_id, motivo=f"Estorno OS {mid}"))
    m.custo_total = max(0, round(m.custo_total - p.quantidade * p.custo_unitario, 2))
    db.session.delete(p)
    audit("MANUTENCAO_PECA_REMOVIDA","manutencao",mid,f"Peça removida: {p.supply_nome}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))


@app.route("/api/maintenance/<mid>/close", methods=["POST"])
@requires("Administrador","Técnico TI")
def close_maintenance(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem já encerrada."}), 400
    d = request.get_json() or {}
    resultado = clean_text(d.get("resultado","Concluída"), 30)
    if resultado not in MANUT_ENCERRA:
        return jsonify({"error":"Resultado deve ser: Concluída, Sem reparo ou Cancelada."}), 400
    status_ativo = clean_text(d.get("statusAtivo","Disponível"), 30)
    if status_ativo not in ASSET_STATUS_VALID:
        return jsonify({"error":f"Status do ativo inválido: {status_ativo}."}), 400
    m.status = resultado
    if d.get("diagnostico"): m.diagnostico = clean_text(d["diagnostico"])
    m.data_conclusao = str(date.today())
    m.custo_total = parse_float(d.get("custoTotal", m.custo_total), minimum=0)
    a = db.session.get(Asset, m.asset_id)
    if a: a.status = status_ativo
    audit("MANUTENCAO_ENCERRADA","manutencao",mid,
          f"OS encerrada: '{resultado}'. Ativo → '{status_ativo}'")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))


# ═══════════════════════════════════════════════════════════════════════════
# API — SYSTEM USERS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/system-users", methods=["GET"])
@requires("Administrador")
def get_system_users(): return jsonify([u.to_dict() for u in db.session.execute(db.select(SystemUser)).scalars().all()])

@app.route("/api/system-users", methods=["POST"])
@requires("Administrador")
def create_system_user():
    d = request.get_json() or {}
    username = clean_text(d.get("username"), 80)
    senha = d.get("senha") or ""
    if not username:
        return jsonify({"error":"Username obrigatório."}), 400
    if len(senha) < 8:
        return jsonify({"error":"Senha deve ter ao menos 8 caracteres."}), 400
    _perfis_validos = _get_setting("perfil_permissoes", PERFIL_PERMISSOES) or PERFIL_PERMISSOES
    if clean_text(d.get("perfil", "Visualizador")) not in _perfis_validos:
        return jsonify({"error":"Perfil inválido."}), 400
    if db.session.execute(db.select(SystemUser).filter_by(username=username)).scalar_one_or_none():
        return jsonify({"error":"Username já existe."}), 409
    err_email = validate_email(d.get("email"))
    if err_email:
        return jsonify({"error": err_email}), 400
    u = SystemUser(id=new_id("SU"), username=username, nome=clean_text(d.get("nome"), 120),
                   email=clean_text(d.get("email"), 120), perfil=clean_text(d.get("perfil","Visualizador"), 40),
                   status=clean_text(d.get("status","Ativo"), 20) or "Ativo")
    u.set_senha(senha)
    db.session.add(u); audit("CRIAR","system_users",u.id,f"Usuário {u.username} criado")
    db.session.commit(); return jsonify(u.to_dict()), 201

@app.route("/api/system-users/<uid>", methods=["PUT"])
@requires("Administrador")
def update_system_user(uid):
    u = db.get_or_404(SystemUser, uid); d = request.get_json() or {}
    if "email" in d:
        err = validate_email(d.get("email"))
        if err:
            return jsonify({"error": err}), 400
    for k,v in [("nome","nome"),("email","email"),("perfil","perfil"),("status","status")]:
        if k in d: setattr(u, v, d[k])
    if d.get("senha"): u.set_senha(d["senha"])
    audit("EDITAR","system_users",uid,f"Usuário {u.username} editado")
    db.session.commit(); return jsonify(u.to_dict())

@app.route("/api/system-users/<uid>/toggle", methods=["POST"])
@requires("Administrador")
def toggle_system_user(uid):
    u = db.get_or_404(SystemUser, uid)
    if u.id == current_user.id: return jsonify({"error":"Não pode desativar a própria conta."}), 400
    u.status = "Inativo" if u.status == "Ativo" else "Ativo"
    db.session.commit(); return jsonify({"status":u.status})

@app.route("/api/system-users/<uid>/reset-senha", methods=["POST"])
@requires("Administrador")
def reset_senha(uid):
    d = request.get_json(); nova = d.get("senha","")
    if len(nova) < 8: return jsonify({"error":"Senha deve ter ao menos 8 caracteres."}), 400
    u = db.get_or_404(SystemUser, uid)
    u.set_senha(nova)
    audit("RESET_SENHA","system_users",uid,f"Senha de '{u.username}' redefinida")
    db.session.commit(); return jsonify({"ok":True})

@app.route("/api/system-users/perfis")
@login_required
def get_perfis():
    """Retorna perfis — do DB settings se customizados, senão do padrão."""
    custom = _get_setting("perfil_permissoes", None)
    return jsonify(custom if custom else PERFIL_PERMISSOES)

@app.route("/api/system-users/perfis/<perfil>", methods=["PUT"])
@requires("Administrador")
def update_perfil_perms(perfil):
    d = request.get_json()
    current = _get_setting("perfil_permissoes", dict(PERFIL_PERMISSOES))
    current[perfil] = d
    _set_setting("perfil_permissoes", current)
    audit("EDITAR_PERMISSOES","system_users",perfil,f"Permissões do perfil '{perfil}' atualizadas")
    db.session.commit()
    return jsonify(current[perfil])

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


SETTING_NORMALIZERS = {
    "empresa": _normalize_empresa_setting,
    "alertas": _normalize_alertas_setting,
    "regras_usuario": _normalize_regras_usuario_setting,
    "campos_ativo_obrigatorios": _normalize_campos_ativos_setting,
    "categorias_config": _normalize_categorias_config_setting,
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


@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    cfg_email = _get_email_config()
    # Nunca retorna a senha ao frontend
    cfg_email_safe = {k: v for k, v in cfg_email.items() if k != "password"}
    cfg_email_safe["password_configurado"] = bool(cfg_email.get("password"))
    cfg_email_safe["via_env"] = cfg_email.get("source") == "env" and bool(os.environ.get("SMTP_PASSWORD"))
    cfg_email_safe["env_disponivel"] = bool(cfg_email.get("env_available"))
    return jsonify({
        "empresa":      _get_setting("empresa", {}),
        "setores":      _get_setting("setores", []),
        "unidades":     _get_setting("unidades", []),
        "alertas":      _get_setting("alertas", {}),
        "regras_usuario":_get_setting("regras_usuario", {}),
        "campos_ativo_obrigatorios": _get_setting("campos_ativo_obrigatorios", []),
        "categorias_config": _get_setting("categorias_config", {}),
        "email":        cfg_email_safe,
        "email_templates": _get_email_templates(),
        "backup":       _get_backup_config(),
        "termo_recebimento": _get_setting("termo_recebimento", {}),
        "termo_devolucao":   _get_setting("termo_devolucao", {}),
    })

@app.route("/api/settings", methods=["PUT"])
@requires("Administrador")
def update_settings():
    d = json_payload()
    if not d:
        return jsonify({"error": "Payload JSON obrigatório."}), 400
    unsupported = sorted(set(d) - set(SETTING_NORMALIZERS))
    if unsupported:
        return jsonify({"error": "Configuração não suportada.", "details": unsupported}), 400
    for key, val in d.items():
        normalized, error = SETTING_NORMALIZERS[key](val)
        if error:
            return jsonify({"error": error}), 400
        _set_setting(key, normalized)
    audit("EDITAR","configuracoes","","Configurações atualizadas")
    db.session.commit()
    return get_settings()

@app.route("/api/settings/setores", methods=["POST"])
@requires("Administrador")
def add_setor():
    nome = clean_text(json_payload().get("nome"), 80)
    if not nome: return jsonify({"error":"Nome obrigatório"}), 400
    setores = _clean_list_setting(_get_setting("setores", []), 80) or []
    if any(s.casefold() == nome.casefold() for s in setores):
        return jsonify({"error":"Já existe"}), 409
    setores.append(nome); _set_setting("setores", setores); db.session.commit()
    return jsonify(setores)

@app.route("/api/settings/setores/<nome>", methods=["DELETE"])
@requires("Administrador")
def del_setor(nome):
    nome = clean_text(nome, 80)
    setores=[s for s in (_clean_list_setting(_get_setting("setores",[]), 80) or []) if s != nome]
    _set_setting("setores",setores); db.session.commit()
    return jsonify(setores)

@app.route("/api/settings/unidades", methods=["POST"])
@requires("Administrador")
def add_unidade():
    uns = _get_setting("unidades", [])
    uns = uns if isinstance(uns, list) else []
    unidade, error = _normalize_unidade_payload(json_payload())
    if error:
        return jsonify({"error": error}), 400
    if any((u.get("nome") or "").casefold() == unidade["nome"].casefold() for u in uns if isinstance(u, dict)):
        return jsonify({"error":"Unidade já existe"}), 409
    unidade["id"] = new_id("UN")
    uns.append(unidade); _set_setting("unidades",uns); db.session.commit()
    return jsonify(unidade),201

@app.route("/api/settings/unidades/<uid>", methods=["PUT"])
@requires("Administrador")
def update_unidade(uid):
    d=json_payload(); uns=_get_setting("unidades",[])
    uns = uns if isinstance(uns, list) else []
    for i,u in enumerate(uns):
        if isinstance(u, dict) and u.get("id")==uid:
            unidade, error = _normalize_unidade_payload(d, {**u, "id": uid})
            if error:
                return jsonify({"error": error}), 400
            uns[i]=unidade; _set_setting("unidades",uns); db.session.commit(); return jsonify(uns[i])
    return jsonify({"error":"Não encontrado"}),404

@app.route("/api/settings/unidades/<uid>", methods=["DELETE"])
@requires("Administrador")
def del_unidade(uid):
    unidades = _get_setting("unidades", [])
    unidades = unidades if isinstance(unidades, list) else []
    uns=[u for u in unidades if isinstance(u, dict) and u.get("id")!=uid]
    _set_setting("unidades",uns); db.session.commit(); return jsonify({"ok":True})


@app.route("/api/settings/email", methods=["PUT"])
@requires("Administrador")
def update_email_settings():
    d = json_payload()
    source = clean_text(d.get("source", _get_setting("email.source", "app")), 20)
    if source not in ("app", "env"):
        return jsonify({"error": "Origem SMTP inválida."}), 400
    _set_setting("email.source", source)

    text_fields = {
        "host": 160,
        "user": 160,
        "from_name": 120,
        "from_email": 120,
    }
    if "from_email" in d:
        err_email = validate_email(d.get("from_email"))
        if err_email:
            return jsonify({"error": err_email}), 400
    for key, max_len in text_fields.items():
        if key in d:
            _set_setting(f"email.{key}", clean_text(d.get(key), max_len))
    if "port" in d:
        port = parse_int(d.get("port"), default=587, minimum=1)
        if port > 65535:
            return jsonify({"error": "Porta SMTP inválida."}), 400
        _set_setting("email.port", port)
    for key in ("tls", "enabled"):
        if key in d:
            _set_setting(f"email.{key}", parse_bool(d.get(key), default=(key == "tls")))
    if parse_bool(d.get("enabled"), default=False) and source == "app":
        host = clean_text(d.get("host", _get_setting("email.host", "")), 160)
        from_email = clean_text(d.get("from_email", _get_setting("email.from_email", "")), 120)
        if not host:
            return jsonify({"error": "Servidor SMTP é obrigatório para ativar pela aplicação."}), 400
        if not from_email:
            return jsonify({"error": "E-mail remetente é obrigatório para ativar pela aplicação."}), 400
    # Senha salva separadamente apenas se fornecida (para não sobrescrever com vazio)
    if parse_bool(d.get("clear_password"), default=False):
        _set_setting("email.password", "")
    if d.get("password"):
        _set_setting("email.password", str(d["password"]))
    audit("EDITAR", "configuracoes", "", "Configurações de e-mail atualizadas")
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/settings/email/test", methods=["POST"])
@requires("Administrador")
def test_email_settings():
    dest = clean_text(json_payload().get("email"), 120) or current_user.email
    if not dest:
        return jsonify({"error": "Usuário sem e-mail cadastrado e nenhum endereço fornecido."}), 400
    err_email = validate_email(dest)
    if err_email:
        return jsonify({"error": err_email}), 400
    result = send_email(
        dest,
        "TI Control — Teste de e-mail",
        f"<p>E-mail de teste enviado com sucesso pelo TI Control.</p><p>Configuração SMTP ativa.</p>",
        "E-mail de teste enviado com sucesso pelo TI Control."
    )
    if result["ok"]:
        audit("TESTE_EMAIL", "configuracoes", "", f"E-mail de teste enviado para {dest}")
        db.session.commit()
    return jsonify(result), 200 if result["ok"] else 502


@app.route("/api/settings/email/templates", methods=["PUT"])
@requires("Administrador")
def update_email_templates():
    templates, error = _normalize_email_templates(json_payload())
    if error:
        return jsonify({"error": error}), 400
    _set_setting("email_templates", templates)
    audit("EDITAR", "configuracoes", "", "Templates de e-mail atualizados")
    db.session.commit()
    return jsonify(templates)


@app.route("/api/settings/backup", methods=["PUT"])
@requires("Administrador")
def update_backup_settings():
    cfg, error = _normalize_backup_config(json_payload())
    if error:
        return jsonify({"error": error}), 400
    _set_setting("backup", cfg)
    audit("EDITAR", "configuracoes", "", "Configuração de backup atualizada")
    db.session.commit()
    return jsonify(cfg)


@app.route("/api/settings/termos", methods=["PUT"])
@requires("Administrador")
def update_termos_settings():
    d = json_payload()
    if not d:
        return jsonify({"error": "Payload JSON obrigatório."}), 400
    for key in ("termo_recebimento", "termo_devolucao"):
        if key in d:
            normalized, error = _normalize_termo_setting(key, d[key])
            if error:
                return jsonify({"error": error}), 400
            _set_setting(key, normalized)
    audit("EDITAR", "configuracoes", "", "Personalização de termos atualizada")
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/devolucoes", methods=["GET"])
@requires("Administrador", "Técnico TI")
def get_devolucoes():
    devs = db.session.execute(db.select(Devolucao).order_by(Devolucao.data_devolucao.desc())).scalars().all()
    return jsonify([d.to_dict() for d in devs])


@app.route("/api/devolucoes/<did>", methods=["GET"])
@requires("Administrador", "Técnico TI")
def get_devolucao(did):
    d = db.get_or_404(Devolucao, did)
    return jsonify(d.to_dict())


@app.route("/api/devolucoes/<did>/sign-link", methods=["POST"])
@requires("Administrador", "Técnico TI")
def gerar_link_devolucao(did):
    from datetime import timedelta
    dev = db.get_or_404(Devolucao, did)
    if dev.status == "Assinado":
        return jsonify({"error": "Devolução já assinada."}), 400
    token = uuid.uuid4().hex + uuid.uuid4().hex
    dev.sign_token = token
    dev.sign_token_expiry = datetime.now() + timedelta(days=7)
    audit("GERAR_LINK_DEVOLUCAO", "devolucoes", did, f"Link gerado para {dev.colaborador}")
    db.session.commit()
    url = f"{app.config['APP_BASE_URL']}/devolver/{token}"
    # Envia e-mail se colaborador tiver e-mail
    email_result = None
    c = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
    email_dest = (c.email if c else "") or ""
    if email_dest:
        email_result = send_email_link_devolucao(email_dest, dev.colaborador, url)
    return jsonify({"url": url, "expiry": dev.sign_token_expiry.isoformat(),
                    "emailEnviado": email_result.get("ok") if email_result else False})


@app.route("/devolver/<token>", methods=["GET"])
def pagina_devolucao(token):
    dev = db.session.execute(db.select(Devolucao).filter_by(sign_token=token)).scalar_one_or_none()
    erro = None
    if dev is None:
        erro = "Link inválido ou não encontrado."
    elif dev.status == "Assinado":
        erro = "Esta devolução já foi assinada."
    elif dev.sign_token_expiry and datetime.now() > dev.sign_token_expiry:
        erro = "Este link expirou."
    return render_template("devolver.html", dev=dev, erro=erro, token=token)


@app.route("/devolver/<token>", methods=["POST"])
def submeter_devolucao(token):
    dev = db.session.execute(db.select(Devolucao).filter_by(sign_token=token)).scalar_one_or_none()
    if dev is None:
        return render_template("devolver.html", dev=None, token=token, erro="Link inválido.")
    if dev.status == "Assinado":
        return render_template("devolver.html", dev=dev, token=token, erro="Já assinado.", sucesso=False)
    if dev.sign_token_expiry and datetime.now() > dev.sign_token_expiry:
        return render_template("devolver.html", dev=dev, token=token, erro="Link expirado.")

    sig_data = request.form.get("assinatura", "").strip()
    nome     = request.form.get("nome_confirm", "").strip()

    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return render_template("devolver.html", dev=dev, token=token,
                               erro="Assinatura não capturada. Desenhe sua assinatura antes de confirmar.")
    if nome.lower() != dev.colaborador.split()[0].lower() and nome.lower() != dev.colaborador.lower():
        return render_template("devolver.html", dev=dev, token=token,
                               erro="Nome digitado não confere. Digite seu primeiro nome ou nome completo.")

    dev.assinatura_img   = sig_data
    dev.assinatura_ip    = request.remote_addr
    dev.data_assinatura  = datetime.now()
    dev.status           = "Assinado"
    dev.sign_token       = None
    dev.sign_token_expiry= None
    audit("ASSINAR_DEVOLUCAO", "devolucoes", dev.id,
          f"Devolução {dev.id} assinada por {dev.colaborador}")
    db.session.commit()
    return render_template("devolver.html", dev=dev, token=token, sucesso=True)


@app.route("/api/devolucoes/<did>/assinatura.png")
@login_required
def get_assinatura_devolucao(did):
    dev = db.get_or_404(Devolucao, did)
    if not dev.assinatura_img or not dev.assinatura_img.startswith("data:image/png;base64,"):
        return jsonify({"error": "Sem assinatura capturada."}), 404
    raw = base64.b64decode(dev.assinatura_img.split(",", 1)[1])
    return Response(raw, mimetype="image/png", headers={"Cache-Control": "private, max-age=3600"})


# ═══════════════════════════════════════════════════════════════════════════
# API — AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/audit-log")
@requires("Administrador","Técnico TI")
def get_audit_log():
    page = int(request.args.get("page",1))
    per  = int(request.args.get("per",50))
    total = db.session.execute(db.select(func.count()).select_from(AuditLog)).scalar()
    logs = db.session.execute(db.select(AuditLog).order_by(AuditLog.data.desc()).offset((page-1)*per).limit(per)).scalars().all()
    return jsonify({"total":total,"page":page,"items":[l.to_dict() for l in logs]})

# ═══════════════════════════════════════════════════════════════════════════
# API — DASHBOARD & ALERTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/alerts")
@api_auth
def get_alerts(): return jsonify(compute_alerts())

@app.route("/api/dashboard")
@api_auth
def get_dashboard():
    cats = dict(db.session.execute(
        db.select(Asset.categoria, func.count(Asset.id)).group_by(Asset.categoria)
    ).all())
    return jsonify({
        "totais": {
            "ativos":    db.session.execute(db.select(func.count()).select_from(Asset)).scalar(),
            "alocados":  db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Alocado")).scalar(),
            "disponiveis":db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Disponível")).scalar(),
            "manutencao":db.session.execute(db.select(func.count()).select_from(Asset).filter_by(status="Manutenção")).scalar(),
        },
        "categorias": cats,
        "alertas": compute_alerts(),
        "ultimasAlocacoes": [a.to_dict() for a in
                             db.session.execute(db.select(Allocation).order_by(Allocation.data_aloc.desc()).limit(5)).scalars().all()],
        "licencas": {
            "total":     db.session.query(func.sum(License.total)).scalar() or 0,
            "atribuidas":db.session.query(func.sum(License.atribuidas)).scalar() or 0,
            "custoAnual":db.session.query(func.sum(License.custo)).scalar() or 0,
        },
    })

@app.route("/api/sre/status")
@api_auth
def sre_status():
    """Resumo operacional para análise de confiabilidade e gestão de SLO."""
    db_health = _database_health()
    total_requests = None
    if METRICS_OK:
        try:
            total_requests = sum(sample.value for sample in HTTP_REQUESTS_TOTAL.collect()[0].samples if sample.name.endswith("_total"))
        except Exception:
            total_requests = None
    open_incidents = db.session.execute(
        db.select(func.count()).select_from(Incident).where(Incident.status != "Resolvido")
    ).scalar()
    pending_terms = db.session.execute(
        db.select(func.count()).select_from(Allocation).filter_by(termo_status="Pendente")
    ).scalar()
    low_stock = db.session.execute(
        db.select(func.count()).select_from(Supply).where(Supply.estoque <= Supply.minimo)
    ).scalar()
    return jsonify({
        **_service_metadata(),
        "health": {"database": db_health},
        "sloTargets": {
            "availability": "99.5% mensal",
            "latencyP95": "<= 500ms para rotas principais",
            "errorRate": "< 1% de respostas 5xx",
            "backup": "1 backup lógico diário"
        },
        "businessIndicators": {
            "incidentsOpen": open_incidents,
            "termsPendingSignature": pending_terms,
            "suppliesAtOrBelowMinimum": low_stock,
            "activeAlerts": len(compute_alerts())
        },
        "observability": {
            "metricsEnabled": METRICS_OK,
            "requestsObserved": total_requests
        }
    })


@app.route("/api/movements")
@api_auth
def get_movements():
    movs = db.session.execute(db.select(SupplyMovement).order_by(SupplyMovement.data.desc()).limit(50)).scalars().all()
    return jsonify([m.to_dict() for m in movs])

# ═══════════════════════════════════════════════════════════════════════════
# EXPORTAÇÃO E BACKUP
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/export/assets.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_assets_csv():
    rows = [a.to_dict() for a in db.session.execute(db.select(Asset).order_by(Asset.hostname)).scalars().all()]
    headers = ["id","hostname","ip","mac","serviceTag","os","fabricante","modelo","patrimonio","nf","categoria","status","colaborador","setor","unidade","garantia"]
    audit("EXPORTAR", "ativos", "", "Exportação CSV de ativos")
    db.session.commit()
    return csv_response("ativos_ti.csv", rows, headers)

@app.route("/api/export/colaboradores.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_colaboradores_csv():
    rows = [c.to_dict() for c in db.session.execute(db.select(Colaborador).order_by(Colaborador.nome)).scalars().all()]
    headers = ["id","nome","email","telefone","cargo","setor","unidade","status","matricula","dataAdmissao","dataCadastro","dataDesligamento","observacao"]
    audit("EXPORTAR", "colaboradores", "", "Exportação CSV de colaboradores")
    db.session.commit()
    return csv_response("colaboradores_ti.csv", rows, headers)

@app.route("/api/export/alocacoes.csv")
@requires("Administrador","Técnico TI","Gestor")
def export_alocacoes_csv():
    rows = [a.to_dict(include_items=False) for a in db.session.execute(db.select(Allocation).order_by(Allocation.data_aloc.desc())).scalars().all()]
    headers = ["id","ativo","ativoNome","colaborador","setor","unidade","email","dataAloc","motivo","dataEncerramento","status","termo","termoStatus","dataAssinatura"]
    audit("EXPORTAR", "alocacoes", "", "Exportação CSV de alocações")
    db.session.commit()
    return csv_response("alocacoes_ti.csv", rows, headers)

@app.route("/api/backup.json")
@requires("Administrador")
def backup_json():
    raw, checksum = _backup_bytes(generated_by=current_user.username, include_audit=_get_backup_config()["include_audit"])
    audit("BACKUP", "sistema", "", "Backup JSON baixado")
    db.session.commit()
    data = io.BytesIO(raw)
    resp = send_file(data, mimetype="application/json", as_attachment=True,
                     download_name=f"backup_ticontrol_{date.today()}.json")
    resp.headers["X-Content-SHA256"] = checksum
    return resp


@app.route("/api/backups")
@requires("Administrador")
def list_backups():
    return jsonify({"config": _get_backup_config(), "files": _list_backup_files()})


@app.route("/api/backups/run", methods=["POST"])
@requires("Administrador")
def run_backup():
    try:
        result = _write_backup_file("manual", generated_by=current_user.username)
        audit("BACKUP", "sistema", "", f"Backup armazenado: {result['filename']}")
        db.session.commit()
        return jsonify(result), 201
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Falha ao gerar backup: {exc}"}), 500


@app.route("/api/backups/files/<filename>")
@requires("Administrador")
def download_backup_file(filename):
    path = _backup_file_path(filename)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Backup não encontrado."}), 404
    audit("BACKUP_DOWNLOAD", "sistema", filename, "Backup salvo baixado")
    db.session.commit()
    return send_file(path, mimetype="application/json", as_attachment=True, download_name=os.path.basename(path))


@app.route("/api/backups/files/<filename>", methods=["DELETE"])
@requires("Administrador")
def delete_backup_file(filename):
    path = _backup_file_path(filename)
    if not path or not os.path.exists(path):
        return jsonify({"error": "Backup não encontrado."}), 404
    os.remove(path)
    audit("BACKUP_DELETE", "sistema", filename, "Backup salvo removido")
    db.session.commit()
    return jsonify({"ok": True})

# ═══════════════════════════════════════════════════════════════════════════
# QR CODE & AUDITORIA
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/assets/<aid>/qrcode")
@login_required
def asset_qrcode(aid):
    base = app.config["APP_BASE_URL"]
    url  = f"{base}/asset/{aid}"
    if QR_OK:
        img = qrcode.make(url); buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        return send_file(buf, mimetype="image/png")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="white"/><text x="60" y="60" text-anchor="middle" font-size="10" fill="#333">QR:{aid}</text></svg>'
    return svg, 200, {"Content-Type":"image/svg+xml"}

@app.route("/api/public/assets/<aid>/audit", methods=["POST"])
def public_asset_audit(aid):
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip, bucket="qr_public_audit"):
        return jsonify({"error": "Muitas requisições. Aguarde um momento."}), 429
    a = db.session.get(Asset, aid)
    if not a:
        return jsonify({"error":"Ativo não encontrado"}), 404
    d = request.get_json(silent=True) or {}
    local = clean_text(d.get("local") or a.unidade or "Não informado", 120)
    responsavel = clean_text(d.get("responsavel") or a.colaborador or "Não informado", 120)
    public_audit("AUDITORIA_QR_PUBLICA", "ativos", a.id, f"Local confirmado: {local}; responsável informado: {responsavel}")
    db.session.commit()
    return jsonify({"ok": True, "hostname": a.hostname, "status": a.status, "local": local})

@app.route("/api/audit-asset", methods=["POST"])
@login_required
def audit_asset_route():
    d = request.get_json()
    a = db.session.get(Asset, d.get("assetId",""))
    if not a: return jsonify({"error":"Ativo não encontrado"}), 404
    audit("AUDITORIA","ativos",a.id,f"Auditado em {d.get('local',a.unidade)} por {current_user.username}")
    db.session.commit()
    return jsonify({"ok":True,"hostname":a.hostname,"status":a.status,"colaborador":a.colaborador})

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
