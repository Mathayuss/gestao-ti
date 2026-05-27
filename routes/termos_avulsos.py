"""Rotas para Termos Avulsos — VPN, BYOD, Confidencialidade etc."""
import base64
from datetime import timedelta
from app import _export_route_globals

globals().update(_export_route_globals())

TIPOS_TERMO_AVULSO = ["VPN", "BYOD", "Confidencialidade", "Outro"]


@app.route("/api/termos-avulsos", methods=["GET"])
@api_auth
def list_termos_avulsos():
    q = request.args.get("q", "").lower()
    stmt = db.select(TermoAvulso).order_by(TermoAvulso.created_at.desc())
    if q:
        stmt = stmt.where(
            db.or_(
                TermoAvulso.colaborador.ilike(f"%{q}%"),
                TermoAvulso.tipo.ilike(f"%{q}%"),
                TermoAvulso.setor.ilike(f"%{q}%"),
            )
        )
    return jsonify([t.to_dict() for t in db.session.execute(stmt).scalars().all()])


@app.route("/api/termos-avulsos", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_termo_avulso():
    d = request.get_json() or {}
    erros = []

    tipo = clean_text(d.get("tipo", ""), 40)
    if not tipo:
        erros.append("Tipo do termo é obrigatório.")

    colaborador = clean_text(d.get("colaborador", ""), 120)
    if not colaborador:
        erros.append("Colaborador é obrigatório.")

    setor   = clean_text(d.get("setor", ""), 80)
    unidade = clean_text(d.get("unidade", ""), 80)
    email   = clean_text(d.get("email", ""), 120)
    validade = clean_text(d.get("validade", ""), 10) or None
    detalhes = d.get("detalhes") or {}
    if not isinstance(detalhes, dict):
        detalhes = {}

    if erros:
        return jsonify({"error": "\n".join(erros)}), 400

    try:
        tid = new_id("TA")
        termo = TermoAvulso(
            id=tid,
            tipo=tipo,
            colaborador=colaborador,
            setor=setor,
            unidade=unidade,
            email=email,
            validade=validade,
            detalhes=json.dumps(detalhes, ensure_ascii=False),
            status="Pendente",
            created_by=current_user.username,
        )
        db.session.add(termo)
        audit("CRIAR_TERMO_AVULSO", "alocacoes", tid,
              f"Termo {tipo} criado para {colaborador}")
        db.session.commit()
        return jsonify(termo.to_dict()), 201
    except Exception:
        db.session.rollback()
        raise


@app.route("/api/termos-avulsos/<tid>", methods=["GET"])
@api_auth
def get_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    return jsonify(t.to_dict())


@app.route("/api/termos-avulsos/<tid>", methods=["PUT"])
@requires("Administrador", "Técnico TI")
def update_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    d = request.get_json() or {}

    if "tipo" in d:
        t.tipo = clean_text(d["tipo"], 40) or t.tipo
    if "colaborador" in d:
        t.colaborador = clean_text(d["colaborador"], 120) or t.colaborador
    if "setor" in d:
        t.setor = clean_text(d["setor"], 80)
    if "unidade" in d:
        t.unidade = clean_text(d["unidade"], 80)
    if "email" in d:
        t.email = clean_text(d["email"], 120)
    if "validade" in d:
        t.validade = clean_text(d["validade"], 10) or None
    if "detalhes" in d:
        det = d["detalhes"]
        t.detalhes = json.dumps(det if isinstance(det, dict) else {}, ensure_ascii=False)

    audit("EDITAR_TERMO_AVULSO", "alocacoes", tid, f"Termo {t.tipo} de {t.colaborador} editado")
    db.session.commit()
    return jsonify(t.to_dict())


@app.route("/api/termos-avulsos/<tid>", methods=["DELETE"])
@requires("Administrador")
def delete_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    audit("EXCLUIR_TERMO_AVULSO", "alocacoes", tid,
          f"Termo {t.tipo} de {t.colaborador} excluído")
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/termos-avulsos/<tid>/sign-link", methods=["POST"])
@requires("Administrador", "Técnico TI")
def gerar_link_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    if t.status == "Assinado":
        return jsonify({"error": "Termo já assinado."}), 400
    token = uuid.uuid4().hex + uuid.uuid4().hex
    t.sign_token = token
    t.sign_token_expiry = datetime.now() + timedelta(days=7)
    audit("GERAR_LINK_TERMO_AVULSO", "alocacoes", tid,
          f"Link de assinatura gerado para {t.colaborador}")
    db.session.commit()
    url = f"{get_app_base_url()}/assinar-avulso/{token}"
    email_enviado = False
    if t.email:
        empresa = _get_setting("empresa", {})
        nome_empresa = empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"
        subject, html, text = _render_email_template("assinatura", {
            "empresa": nome_empresa,
            "colaborador": t.colaborador,
            "ativo": f"Termo {t.tipo}",
            "link": url,
        })
        res = send_email(t.email, subject, html, text)
        email_enviado = res.get("ok", False)
    return jsonify({"url": url, "expiry": t.sign_token_expiry.isoformat(),
                    "emailEnviado": email_enviado})


@app.route("/api/termos-avulsos/<tid>/termo.pdf")
@api_auth
def gerar_termo_avulso_pdf(tid):
    t = db.get_or_404(TermoAvulso, tid)
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível. Instale: pip install reportlab"}), 503

    empresa  = _get_setting("empresa", {}) or {}
    logo_b64 = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    # Seleciona template conforme tipo
    tpl_key = "termo_vpn" if t.tipo == "VPN" else "termo_vpn"
    tr_cfg  = _get_setting(tpl_key, {}) or {}

    ctx = {
        "colaborador": t.colaborador, "setor": t.setor, "unidade": t.unidade,
        "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else "",
        "tipo": t.tipo, "validade": t.validade or "—",
        "data": t.created_at.strftime("%Y-%m-%d") if t.created_at else str(date.today()),
    }
    titulo    = _render_termo_text(tr_cfg.get("titulo", f"TERMO DE {t.tipo.upper()}"), ctx)
    preambulo = _render_termo_text(
        tr_cfg.get("preambulo", f"Eu, {{colaborador}}, do setor {{setor}}, unidade {{unidade}},\ndeclaro estar ciente e de acordo com os termos abaixo:"),
        ctx)
    clausulas = tr_cfg.get("clausulas", [])
    rodape_txt = _render_termo_text(tr_cfg.get("rodape", ""), ctx)

    # Campos extras do detalhes
    detalhes_dict = json.loads(t.detalhes or "{}") if t.detalhes else {}

    try:
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        w, h = A4

        if logo_b64:
            _pdf_draw_logo(c, logo_b64, 2*cm, h-3.5*cm, max_w=3*cm, max_h=1.5*cm)
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(w/2, h-3*cm, titulo)
        c.setFont("Helvetica", 10)
        c.drawCentredString(w/2, h-3.7*cm, f"Emitido em: {ctx['data']}")
        if isinstance(empresa, dict) and empresa.get("nome"):
            c.drawCentredString(w/2, h-4.2*cm, empresa["nome"])
        c.line(2*cm, h-4.6*cm, w-2*cm, h-4.6*cm)

        c.setFont("Helvetica", 11)
        y = h - 6*cm
        for linha in preambulo.split("\n"):
            c.drawString(2*cm, y, linha.strip())
            y -= 0.7*cm
        y -= 0.3*cm

        # Bloco de identificação
        c.setFillColorRGB(0.93, 0.93, 0.93)
        c.rect(2*cm, y - 0.5*cm, w - 4*cm, 2.4*cm, fill=True, stroke=False)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Courier", 10)
        c.drawString(2.5*cm, y, f"Colaborador : {t.colaborador}")
        y -= 0.55*cm
        c.drawString(2.5*cm, y, f"Setor/Unidade: {t.setor} / {t.unidade}")
        y -= 0.55*cm
        c.drawString(2.5*cm, y, f"Tipo de Termo: {t.tipo}")
        if t.validade:
            c.drawString(10*cm, y, f"Validade: {t.validade}")
        y -= 0.55*cm
        if t.email:
            c.drawString(2.5*cm, y, f"E-mail : {t.email}")
            y -= 0.55*cm
        y -= 0.5*cm

        # Campos extras
        if detalhes_dict:
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2*cm, y, "Detalhes específicos:")
            y -= 0.5*cm
            c.setFont("Helvetica", 10)
            for k, v in detalhes_dict.items():
                c.drawString(2.5*cm, y, f"• {k}: {v}")
                y -= 0.5*cm
            y -= 0.3*cm

        c.setFont("Helvetica", 10)
        for cl in clausulas:
            c.drawString(2*cm, y, _render_termo_text(cl, ctx))
            y -= 0.6*cm

        if t.status == "Assinado" and t.data_assinatura:
            y -= 0.3*cm
            c.setFont("Helvetica-Bold", 10)
            c.drawString(2*cm, y, f"Assinado em {t.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {t.assinatura_ip or '—'}")
            y -= 0.5*cm

        y -= 0.5*cm
        from reportlab.lib.utils import ImageReader as _IR
        if t.assinatura_img and t.assinatura_img.startswith("data:image/png;base64,"):
            raw_col = base64.b64decode(t.assinatura_img.split(",", 1)[1])
            c.drawImage(_IR(io.BytesIO(raw_col)), 2*cm, y - 1.8*cm, width=5*cm, height=1.8*cm,
                        preserveAspectRatio=True, mask="auto")
        c.line(2*cm, y, 9*cm, y)
        c.line(12*cm, y, w - 2*cm, y)
        y -= 0.5*cm
        c.setFont("Helvetica", 9)
        c.drawCentredString(5.5*cm, y, t.colaborador)
        c.drawCentredString(16*cm, y, "Responsável TI")

        if rodape_txt:
            c.setFont("Helvetica", 8)
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawCentredString(w/2, 1.5*cm, rodape_txt)

        c.save()
        buf.seek(0)
        nome_pdf = f"termo_avulso_{safe_filename(t.tipo)}_{safe_filename(t.colaborador)}.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)
    except Exception as exc:
        return jsonify({"error": f"Erro ao gerar PDF: {exc.__class__.__name__} — {exc}"}), 500


# ── Página pública de assinatura ──────────────────────────────────────────────

@app.route("/assinar-avulso/<token>", methods=["GET"])
def pagina_assinatura_avulso(token):
    t = db.session.execute(
        db.select(TermoAvulso).filter_by(sign_token=token)
    ).scalar_one_or_none()
    erro = None
    if t is None:
        erro = "Link inválido ou não encontrado."
    elif t.status == "Assinado":
        erro = "Este termo já foi assinado."
    elif t.sign_token_expiry and datetime.now() > t.sign_token_expiry:
        erro = "Este link de assinatura expirou."
    return render_template("assinar_avulso.html", termo=t, erro=erro, token=token)


@app.route("/assinar-avulso/<token>", methods=["POST"])
def submeter_assinatura_avulso(token):
    t = db.session.execute(
        db.select(TermoAvulso).filter_by(sign_token=token)
    ).scalar_one_or_none()
    if t is None:
        return render_template("assinar_avulso.html", termo=None, token=token,
                               erro="Link inválido.", sucesso=False)
    if t.status == "Assinado":
        return render_template("assinar_avulso.html", termo=t, token=token,
                               erro="Já assinado.", sucesso=False)
    if t.sign_token_expiry and datetime.now() > t.sign_token_expiry:
        return render_template("assinar_avulso.html", termo=t, token=token,
                               erro="Link expirado.", sucesso=False)

    sig_data = request.form.get("assinatura", "").strip()
    nome     = request.form.get("nome_confirm", "").strip()

    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return render_template("assinar_avulso.html", termo=t, token=token,
                               erro="Assinatura não capturada. Desenhe sua assinatura antes de confirmar.",
                               sucesso=False)
    if nome.lower() != t.colaborador.split()[0].lower() and nome.lower() != t.colaborador.lower():
        return render_template("assinar_avulso.html", termo=t, token=token,
                               erro="Nome digitado não confere. Digite seu primeiro nome ou nome completo.",
                               sucesso=False)

    t.assinatura_img  = sig_data
    t.status          = "Assinado"
    t.data_assinatura = datetime.now()
    t.assinatura_ip   = request.remote_addr
    t.sign_token      = None
    t.sign_token_expiry = None
    db.session.commit()
    return render_template("assinar_avulso.html", termo=t, token=token, sucesso=True)
