"""Servico de configuracao, renderizacao e envio de e-mails."""
import html as _html
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from extensions import db
from models import Setting
from services.settings_service import get_setting
from services.template_renderer import render_text_template


SMTP_ENV_KEYS = (
    "SMTP_HOST", "SMTP_PORT", "SMTP_TLS", "SMTP_USER", "SMTP_PASSWORD", "SMTP_PASSWORD_FILE",
    "SMTP_FROM_NAME", "SMTP_FROM_EMAIL", "SMTP_ENABLED",
)


DEFAULT_EMAIL_TEMPLATES = {
    "pacote_termos": {
        "subject": "[{empresa}] Termos aguardando sua assinatura",
        "body": (
            "Olá, {colaborador}!\n\n"
            "Você possui {quantidade} termo(s) para revisar e assinar: {termos}.\n\n"
            "Acesse a Central de Assinaturas pelo botão abaixo para visualizar cada documento "
            "e registrar sua assinatura.\n\n"
            "Este link expira em 7 dias. Em caso de dúvidas, contate o setor de TI."
        ),
        "button_label": "Revisar e Assinar Termos",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
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
    "laudo_editado_rh": {
        "subject": "[{empresa}] Laudo técnico corrigido — {colaborador}",
        "body": (
            "Olá!\n\n"
            "O laudo técnico referente à devolução de equipamentos de {colaborador} "
            "foi corrigido pelo administrador {editor}.\n\n"
            "Motivo da correção: {motivo}\n\n"
            "Acesse o sistema para verificar as alterações."
        ),
        "button_label": "Acessar o Sistema",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
    "laudo_editado_colab": {
        "subject": "[{empresa}] Atualização no laudo técnico — devolução de equipamentos",
        "body": (
            "Olá, {colaborador}!\n\n"
            "Informamos que o laudo técnico referente à devolução dos equipamentos "
            "sob sua responsabilidade foi atualizado.\n\n"
            "Motivo da correção: {motivo}\n\n"
            "Em caso de dúvidas, entre em contato com o setor de TI."
        ),
        "button_label": "Acessar o Sistema",
        "footer": "{empresa} - Sistema de Gestão de TI",
    },
}


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


def company_name():
    empresa = get_setting("empresa", {})
    return empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"


def smtp_env_available():
    return any(os.environ.get(key) for key in SMTP_ENV_KEYS)


def read_secret_file(path, max_bytes=4096):
    if not path:
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read(max_bytes).strip()
    except OSError:
        return ""


def smtp_env_password():
    return os.environ.get("SMTP_PASSWORD") or read_secret_file(os.environ.get("SMTP_PASSWORD_FILE"))


def get_email_config():
    """Le configuracao de e-mail do banco em uma unica query."""
    email_keys = {"email.source", "email.host", "email.port", "email.tls",
                  "email.user", "email.password", "email.from_name",
                  "email.from_email", "email.enabled"}
    rows = db.session.execute(
        db.select(Setting).where(Setting.key.in_(email_keys))
    ).scalars().all()

    def parse_setting_value(raw):
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return raw

    db_vals = {row.key: parse_setting_value(row.value) for row in rows}

    def setting_value(key, default=""):
        value = db_vals.get(key)
        return default if value is None else value

    source = clean_text(setting_value("email.source"), 20)
    if source not in ("app", "env"):
        source = "env" if smtp_env_available() else "app"

    app_cfg = {
        "host":       setting_value("email.host"),
        "port":       parse_int(setting_value("email.port", 587), default=587, minimum=1),
        "tls":        parse_bool(setting_value("email.tls", True), default=True),
        "user":       setting_value("email.user"),
        "password":   setting_value("email.password"),
        "from_name":  setting_value("email.from_name", "TI Control"),
        "from_email": setting_value("email.from_email"),
        "enabled":    parse_bool(setting_value("email.enabled", False), default=False),
    }

    if source == "app":
        return {**app_cfg, "source": "app", "env_available": smtp_env_available()}

    return {
        "host":         os.environ.get("SMTP_HOST") or app_cfg["host"],
        "port":         parse_int(os.environ.get("SMTP_PORT") or app_cfg["port"], default=587, minimum=1),
        "tls":          parse_bool(os.environ.get("SMTP_TLS"), default=app_cfg["tls"]),
        "user":         os.environ.get("SMTP_USER") or app_cfg["user"],
        "password":     smtp_env_password() or app_cfg["password"],
        "from_name":    os.environ.get("SMTP_FROM_NAME") or app_cfg["from_name"],
        "from_email":   os.environ.get("SMTP_FROM_EMAIL") or app_cfg["from_email"],
        "enabled":      parse_bool(os.environ.get("SMTP_ENABLED"), default=app_cfg["enabled"]),
        "source":       "env",
        "env_available": smtp_env_available(),
    }


def send_email(to, subject, body_html, body_text=""):
    """Envia e-mail via SMTP. Retorna {'ok': bool, 'error': str|None}."""
    cfg = get_email_config()
    if not cfg["enabled"]:
        return {"ok": False, "error": "E-mail desabilitado nas configurações."}
    if not cfg["host"] or not cfg["from_email"]:
        return {"ok": False, "error": "Servidor SMTP não configurado."}
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = to
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


def get_email_templates():
    saved = get_setting("email_templates", {})
    saved = saved if isinstance(saved, dict) else {}
    merged = {}
    for key, defaults in DEFAULT_EMAIL_TEMPLATES.items():
        custom = saved.get(key, {})
        custom = custom if isinstance(custom, dict) else {}
        merged[key] = {**defaults, **{k: v for k, v in custom.items() if k in defaults}}
    return merged


def normalize_email_templates(value):
    if not isinstance(value, dict):
        return None, "Templates de e-mail precisam ser um objeto."
    current = get_email_templates()
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


def render_email_template(kind, ctx):
    templates = get_email_templates()
    tpl = templates.get(kind, DEFAULT_EMAIL_TEMPLATES[kind])
    empresa = ctx.get("empresa") or "TI Control"
    full_ctx = {**ctx, "empresa": empresa}
    subject = clean_text(render_text_template(tpl["subject"], full_ctx), 180)
    body_text = render_text_template(tpl["body"], full_ctx)
    footer_text = render_text_template(tpl.get("footer", ""), full_ctx)
    button_label = render_text_template(tpl.get("button_label", "Abrir"), full_ctx)
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


def send_email_link_assinatura(to, colaborador, ativo_nome, link):
    subject, html, text = render_email_template("assinatura", {
        "empresa": company_name(),
        "colaborador": colaborador,
        "ativo": ativo_nome,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_link_devolucao(to, colaborador, link):
    subject, html, text = render_email_template("devolucao", {
        "empresa": company_name(),
        "colaborador": colaborador,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_laudo_rh(to, colaborador, tecnico, link):
    subject, html, text = render_email_template("laudo_rh", {
        "empresa": company_name(),
        "colaborador": colaborador,
        "tecnico": tecnico,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_laudo_editado_rh(to, colaborador, editor, motivo, link):
    subject, html, text = render_email_template("laudo_editado_rh", {
        "empresa": company_name(),
        "colaborador": colaborador,
        "editor": editor,
        "motivo": motivo,
        "link": link,
    })
    return send_email(to, subject, html, text)


def send_email_laudo_editado_colab(to, colaborador, motivo, link):
    subject, html, text = render_email_template("laudo_editado_colab", {
        "empresa": company_name(),
        "colaborador": colaborador,
        "motivo": motivo,
        "link": link,
    })
    return send_email(to, subject, html, text)
