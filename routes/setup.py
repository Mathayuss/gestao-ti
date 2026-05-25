"""Assistente inicial de instalação."""
import secrets
from urllib.parse import urlsplit

from app import _export_route_globals

globals().update(_export_route_globals())


def _setup_completed():
    completed = _get_setting("setup.completed", False)
    if completed:
        return True
    admin = db.session.execute(
        db.select(SystemUser).where(SystemUser.perfil == "Administrador")
    ).scalar_one_or_none()
    return bool(admin)


def _setup_token_valid(token):
    expected = clean_text(os.environ.get("SETUP_TOKEN", ""), 200)
    token = clean_text(token, 200)
    return bool(expected and token and secrets.compare_digest(expected, token))


def _database_info():
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    parsed = urlsplit(uri)
    scheme = parsed.scheme or "sqlite"
    if scheme.startswith("sqlite"):
        return {
            "engine": "SQLite",
            "host": "local",
            "port": "",
            "database": parsed.path or uri,
            "user": "",
        }
    engine = "PostgreSQL" if scheme.startswith("postgresql") else scheme
    return {
        "engine": engine,
        "host": parsed.hostname or "",
        "port": parsed.port or "",
        "database": (parsed.path or "").lstrip("/"),
        "user": parsed.username or "",
    }


def _setup_form_values():
    return {
        "empresa_nome": request.form.get("empresa_nome", ""),
        "empresa_cnpj": request.form.get("empresa_cnpj", ""),
        "empresa_email": request.form.get("empresa_email", ""),
        "empresa_telefone": request.form.get("empresa_telefone", ""),
        "empresa_site": request.form.get("empresa_site", ""),
        "empresa_endereco": request.form.get("empresa_endereco", ""),
        "admin_nome": request.form.get("admin_nome", ""),
        "admin_username": request.form.get("admin_username", "admin"),
        "admin_email": request.form.get("admin_email", ""),
        "app_base_url": request.form.get("app_base_url", app.config.get("APP_BASE_URL", "http://localhost")),
        "smtp_host": request.form.get("smtp_host", ""),
        "smtp_port": request.form.get("smtp_port", "587"),
        "smtp_user": request.form.get("smtp_user", ""),
        "smtp_from_name": request.form.get("smtp_from_name", ""),
        "smtp_from_email": request.form.get("smtp_from_email", ""),
        "smtp_enabled": request.form.get("smtp_enabled", ""),
        "smtp_tls": request.form.get("smtp_tls", "on"),
        "backup_enabled": request.form.get("backup_enabled", ""),
        "backup_frequency": request.form.get("backup_frequency", "daily"),
        "backup_retention": request.form.get("backup_retention", "7"),
    }


def _render_setup(token="", errors=None, values=None, authorized=True):
    values = values or _setup_form_values()
    return render_template(
        "setup.html",
        token=token,
        errors=errors or [],
        values=values,
        authorized=authorized,
        database=_database_info(),
        build_version=app.config.get("BUILD_VERSION", "0.1.2-BETA"),
    )


@app.route("/setup", methods=["GET", "POST"])
def setup_wizard():
    if _setup_completed():
        return redirect(url_for("login_page"))

    token = request.values.get("token") or request.headers.get("X-Setup-Token", "")
    if not _setup_token_valid(token):
        return _render_setup(token=token, authorized=False), 403

    if request.method == "GET":
        return _render_setup(token=token)

    values = _setup_form_values()
    errors = []
    empresa = {
        "nome": clean_text(values["empresa_nome"], 120),
        "cnpj": clean_text(values["empresa_cnpj"], 30),
        "email": clean_text(values["empresa_email"], 120),
        "telefone": clean_text(values["empresa_telefone"], 40),
        "site": clean_text(values["empresa_site"], 120),
        "endereco": clean_text(values["empresa_endereco"], 240),
    }
    admin_nome = clean_text(request.form.get("admin_nome"), 120)
    admin_username = clean_text(request.form.get("admin_username"), 80)
    admin_email = clean_text(request.form.get("admin_email"), 120)
    admin_password = request.form.get("admin_password") or ""
    admin_password_confirm = request.form.get("admin_password_confirm") or ""
    app_base_url = clean_text(values["app_base_url"], 180).rstrip("/")

    if not empresa["nome"]:
        errors.append("Informe o nome da empresa.")
    err_empresa_email = validate_email(empresa["email"])
    if err_empresa_email:
        errors.append(err_empresa_email)
    if not admin_nome:
        errors.append("Informe o nome do administrador.")
    if not re.match(r"^[A-Za-z0-9_.-]{3,80}$", admin_username or ""):
        errors.append("Usuário administrador deve ter 3 a 80 caracteres e usar letras, números, ponto, hífen ou underline.")
    err_admin_email = validate_email(admin_email)
    if err_admin_email:
        errors.append(err_admin_email)
    if len(admin_password) < 8:
        errors.append("Senha do administrador deve ter pelo menos 8 caracteres.")
    if admin_password != admin_password_confirm:
        errors.append("Confirmação de senha não confere.")
    if app_base_url:
        parsed = urlsplit(app_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("URL pública deve começar com http:// ou https://.")
    if db.session.execute(db.select(SystemUser).filter_by(username=admin_username)).scalar_one_or_none():
        errors.append("Já existe um usuário com este username.")

    smtp_enabled = request.form.get("smtp_enabled") == "on"
    if smtp_enabled:
        if not clean_text(values["smtp_host"], 160):
            errors.append("Servidor SMTP é obrigatório quando o e-mail está ativado.")
        smtp_from_email = clean_text(values["smtp_from_email"], 120)
        if not smtp_from_email:
            errors.append("E-mail remetente SMTP é obrigatório quando o e-mail está ativado.")
        else:
            smtp_email_error = validate_email(smtp_from_email)
            if smtp_email_error:
                errors.append(smtp_email_error)
        smtp_port = parse_int(values["smtp_port"], default=587, minimum=1)
        if smtp_port > 65535:
            errors.append("Porta SMTP inválida.")

    if errors:
        return _render_setup(token=token, errors=errors, values=values), 400

    _ensure_initial_settings(empresa)
    admin = SystemUser(
        id=new_id("SU"),
        username=admin_username,
        nome=admin_nome,
        email=admin_email,
        perfil="Administrador",
        status="Ativo",
        criado_em=date.today(),
    )
    admin.set_senha(admin_password)
    db.session.add(admin)

    backup_cfg = _get_backup_config()
    backup_cfg.update({
        "enabled": request.form.get("backup_enabled") == "on",
        "frequency": clean_text(values["backup_frequency"], 20) if values["backup_frequency"] in ("daily", "weekly", "monthly") else "daily",
        "retention": parse_int(values["backup_retention"], default=7, minimum=1),
    })
    _set_setting("backup", backup_cfg)

    if app_base_url:
        app.config["APP_BASE_URL"] = app_base_url
        _set_setting("app.base_url", app_base_url)

    if smtp_enabled:
        _set_setting("email.source", "app")
        _set_setting("email.enabled", True)
        _set_setting("email.host", clean_text(values["smtp_host"], 160))
        _set_setting("email.port", parse_int(values["smtp_port"], default=587, minimum=1))
        _set_setting("email.tls", request.form.get("smtp_tls") == "on")
        _set_setting("email.user", clean_text(values["smtp_user"], 160))
        _set_setting("email.from_name", clean_text(values["smtp_from_name"], 120))
        _set_setting("email.from_email", clean_text(values["smtp_from_email"], 120))
        if request.form.get("smtp_password"):
            _set_setting("email.password", request.form.get("smtp_password"))

    _set_setting("setup.completed", {
        "completed": True,
        "completed_at": datetime.now().isoformat(),
        "admin": admin_username,
        "database": _database_info(),
    })
    audit("SETUP", "sistema", "", "Assistente inicial concluído")
    db.session.commit()
    login_user(admin, remember=False)
    return redirect(url_for("index"))
