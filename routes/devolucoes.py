"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

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


@app.route("/api/devolucoes/<did>/laudo", methods=["POST"])
@requires("Administrador", "Técnico TI")
def registrar_laudo(did):
    """Técnico registra avaliação dos equipamentos. Dispara e-mail de ciência para o RH."""
    from datetime import timedelta
    dev = db.get_or_404(Devolucao, did)
    if dev.laudo_status not in (None, "Aguardando Laudo"):
        return jsonify({"error": f"Laudo já registrado (status: {dev.laudo_status})."}), 400

    d = json_payload()
    rh_email = clean_text(d.get("rhEmail"), 120)
    if not rh_email:
        return jsonify({"error": "E-mail do RH (rhEmail) é obrigatório."}), 400

    tecnico         = clean_text(d.get("tecnico") or session.get("user", "Técnico"), 120)
    avaliacao_itens = d.get("avaliacaoItens", [])
    observacao      = clean_text(d.get("observacaoGeral", ""), 2000)
    tem_cobranca    = bool(d.get("temCobranca", False))
    valor_cobranca  = float(d.get("valorCobranca", 0) or 0)

    if not isinstance(avaliacao_itens, list):
        return jsonify({"error": "avaliacaoItens deve ser uma lista."}), 400

    laudo = LaudoTecnico(
        id=new_id("LAU"),
        devolucao_id=did,
        tecnico=tecnico,
        avaliacao_itens=json.dumps(avaliacao_itens, ensure_ascii=False),
        observacao_geral=observacao,
        tem_cobranca=tem_cobranca,
        valor_cobranca=valor_cobranca,
        data_avaliacao=datetime.now(),
    )
    db.session.add(laudo)

    rh_token = uuid.uuid4().hex + uuid.uuid4().hex
    dev.laudo_status    = "Aguardando RH"
    dev.rh_token        = rh_token
    dev.rh_token_expiry = datetime.now() + timedelta(days=7)
    dev.rh_email        = rh_email
    dev.cobranca_valor  = valor_cobranca if tem_cobranca else 0.0
    db.session.commit()

    link_rh = f"{app.config['APP_BASE_URL']}/rh/laudo/{rh_token}"
    email_enviado = False
    res = send_email_laudo_rh(rh_email, dev.colaborador, tecnico, link_rh)
    email_enviado = res.get("ok", False)

    audit("LAUDO_TECNICO", "devolucoes", did,
          f"Laudo de {tecnico} para {dev.colaborador} — cobrança: {tem_cobranca}")
    return jsonify({
        "ok": True, "laudoId": laudo.id,
        "laudoStatus": "Aguardando RH",
        "linkRH": link_rh,
        "emailRHEnviado": email_enviado,
    })


@app.route("/api/devolucoes/<did>/laudo", methods=["PUT"])
@requires("Administrador")
def editar_laudo(did):
    """Administrador edita/corrige um laudo já registrado após envio ao RH."""
    dev = db.get_or_404(Devolucao, did)
    if not dev.laudo_status or dev.laudo_status == "Aguardando Laudo":
        return jsonify({"error": "Laudo ainda não registrado nesta devolução."}), 400

    laudo = db.session.execute(
        db.select(LaudoTecnico).filter_by(devolucao_id=did)
        .order_by(LaudoTecnico.data_avaliacao.desc())
    ).scalar_one_or_none()
    if not laudo:
        return jsonify({"error": "Laudo não encontrado."}), 404

    d = json_payload()
    motivo = clean_text(d.get("motivoCorrecao", ""), 500)
    if not motivo:
        return jsonify({"error": "Motivo da correção é obrigatório."}), 400

    if "avaliacaoItens" in d:
        itens = d.get("avaliacaoItens")
        if not isinstance(itens, list):
            return jsonify({"error": "avaliacaoItens deve ser uma lista."}), 400
        laudo.avaliacao_itens = json.dumps(itens, ensure_ascii=False)

    if "observacaoGeral" in d:
        laudo.observacao_geral = clean_text(d.get("observacaoGeral", ""), 2000)
    if "temCobranca" in d:
        laudo.tem_cobranca = bool(d.get("temCobranca", False))
    if "valorCobranca" in d:
        laudo.valor_cobranca = float(d.get("valorCobranca", 0) or 0)

    laudo.editado_em  = datetime.now()
    laudo.editado_por = clean_text(session.get("user", "Administrador"), 120)
    laudo.motivo_edicao = motivo

    if "temCobranca" in d or "valorCobranca" in d:
        dev.cobranca_valor = laudo.valor_cobranca if laudo.tem_cobranca else 0.0

    db.session.commit()
    audit("LAUDO_EDITADO", "laudos_tecnicos", laudo.id,
          f"Laudo editado por {laudo.editado_por} — motivo: {motivo}")
    return jsonify({"ok": True, "laudo": laudo.to_dict()})


@app.route("/rh/laudo/<rh_token>", methods=["GET"])
def pagina_rh_laudo(rh_token):
    """Página pública para o RH visualizar o laudo e dar ciência (sem login)."""
    dev = db.session.execute(db.select(Devolucao).filter_by(rh_token=rh_token)).scalar_one_or_none()
    erro = None
    if dev is None:
        erro = "Link inválido ou não encontrado."
    elif dev.laudo_status == "Aprovado":
        erro = None  # mostra tela de sucesso
    elif dev.rh_token_expiry and datetime.now() > dev.rh_token_expiry:
        erro = "Este link expirou. Solicite ao técnico de TI um novo link."

    laudo = None
    if dev:
        laudo = db.session.execute(
            db.select(LaudoTecnico).filter_by(devolucao_id=dev.id)
            .order_by(LaudoTecnico.data_avaliacao.desc())
        ).scalar_one_or_none()

    return render_template("rh_laudo.html", dev=dev, laudo=laudo, erro=erro, rh_token=rh_token)


@app.route("/rh/laudo/<rh_token>", methods=["POST"])
def submeter_ciencia_rh(rh_token):
    """RH dá ciência do laudo. Após aprovação, gera link de assinatura para o colaborador."""
    from datetime import timedelta
    dev = db.session.execute(db.select(Devolucao).filter_by(rh_token=rh_token)).scalar_one_or_none()
    laudo = None
    if dev:
        laudo = db.session.execute(
            db.select(LaudoTecnico).filter_by(devolucao_id=dev.id)
            .order_by(LaudoTecnico.data_avaliacao.desc())
        ).scalar_one_or_none()

    if dev is None:
        return render_template("rh_laudo.html", dev=None, laudo=None, rh_token=rh_token,
                               erro="Link inválido.")
    if dev.laudo_status == "Aprovado":
        return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                               erro=None, sucesso=True)
    if dev.rh_token_expiry and datetime.now() > dev.rh_token_expiry:
        return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                               erro="Link expirado.")

    cobranca_obs   = request.form.get("cobranca_obs", "").strip()[:2000]
    cobranca_valor = request.form.get("cobranca_valor", "0").strip()
    try:
        cobranca_valor = float(cobranca_valor)
    except ValueError:
        cobranca_valor = dev.cobranca_valor or 0.0

    dev.laudo_status    = "Aprovado"
    dev.rh_ciencia_ip   = request.remote_addr
    dev.rh_data_ciencia = datetime.now()
    dev.cobranca_obs    = cobranca_obs
    dev.cobranca_valor  = cobranca_valor
    dev.rh_token        = None
    dev.rh_token_expiry = None

    # Gera link de assinatura para o colaborador
    sign_token = uuid.uuid4().hex + uuid.uuid4().hex
    dev.sign_token        = sign_token
    dev.sign_token_expiry = datetime.now() + timedelta(days=7)
    db.session.commit()

    link_assinatura = f"{app.config['APP_BASE_URL']}/devolver/{sign_token}"
    email_colab_enviado = False
    colab = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
    if colab and colab.email:
        res = send_email_link_devolucao(colab.email, dev.colaborador, link_assinatura)
        email_colab_enviado = res.get("ok", False)

    audit("CIENCIA_RH", "devolucoes", dev.id,
          f"RH deu ciência do laudo de {dev.colaborador}. E-mail colaborador: {email_colab_enviado}")
    return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                           sucesso=True, link_assinatura=link_assinatura,
                           email_colab_enviado=email_colab_enviado)


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

