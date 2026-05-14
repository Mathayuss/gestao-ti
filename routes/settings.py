"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

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
        "aparencia":    _get_setting("aparencia", {}),
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

