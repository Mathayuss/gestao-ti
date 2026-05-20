"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

@app.route("/login", methods=["GET"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    aparencia = _get_setting("aparencia", {}) or {}
    empresa   = _get_setting("empresa", {}) or {}
    return render_template(
        "login.html",
        error=request.args.get("error"),
        show_demo=app.config["SHOW_DEMO_CREDENTIALS"],
        aparencia=aparencia,
        empresa=empresa,
        build_version=app.config.get("BUILD_VERSION", "0.1.1-BETA"),
    )


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

