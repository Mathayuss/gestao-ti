"""Rotas para termos personalizados, mantendo nomes legados para compatibilidade."""
import base64
from datetime import timedelta
from app import _export_route_globals

globals().update(_export_route_globals())

TIPOS_TERMO_AVULSO = ["VPN", "BYOD", "Confidencialidade", "Outro"]


def _termo_detalhes_raw(termo):
    try:
        value = json.loads(termo.detalhes or "{}") if termo and termo.detalhes else {}
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _termo_modelo_registrado(termo):
    snapshot = _termo_detalhes_raw(termo).get("_modelo")
    if isinstance(snapshot, dict):
        return snapshot
    return _get_termo_avulso_modelo(termo.tipo)


def _send_termo_avulso_pdf(t, empresa, logo_b64, titulo, preambulo, clausulas, rodape_txt, ctx, detalhes_dict):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.7*cm, bottomMargin=2.1*cm, title=titulo)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TermTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=14, leading=17, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle(name="TermMeta", parent=styles["Normal"], fontSize=9, leading=11, alignment=TA_CENTER, textColor=colors.HexColor("#555555")))
    styles.add(ParagraphStyle(name="TermBody", parent=styles["BodyText"], fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=7))
    styles.add(ParagraphStyle(name="TermLabel", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=TA_LEFT))
    styles.add(ParagraphStyle(name="TermSmall", parent=styles["Normal"], fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.HexColor("#666666")))

    def para(text, style="TermBody"):
        return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), styles[style])

    def sig_img(data_url, max_w=5.6*cm, max_h=1.8*cm):
        if not data_url or not str(data_url).startswith("data:image/png;base64,"):
            return Spacer(max_w, max_h)
        raw = base64.b64decode(data_url.split(",", 1)[1])
        reader = ImageReader(io.BytesIO(raw))
        iw, ih = reader.getSize()
        scale = min(max_w / iw, max_h / ih)
        return Image(io.BytesIO(raw), width=iw * scale, height=ih * scale)

    story = []
    if logo_b64 and str(logo_b64).startswith("data:"):
        try:
            raw = base64.b64decode(logo_b64.split(",", 1)[1])
            reader = ImageReader(io.BytesIO(raw))
            iw, ih = reader.getSize()
            scale = min((3.2*cm)/iw, (1.5*cm)/ih)
            story.append(Table([[Image(io.BytesIO(raw), width=iw*scale, height=ih*scale)]], colWidths=[doc.width], style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
        except Exception:
            pass
    story.extend([para(titulo, "TermTitle"), para(f"Emitido em: {ctx.get('data')}", "TermMeta")])
    if isinstance(empresa, dict) and empresa.get("nome"):
        story.append(para(empresa["nome"], "TermMeta"))
    story.append(Spacer(1, 0.35*cm))

    for linha in str(preambulo or "").split("\n"):
        if linha.strip():
            story.append(para(linha.strip()))

    dados = [["Colaborador", t.colaborador], ["Setor / Unidade", f"{t.setor or '-'} / {t.unidade or '-'}"], ["Tipo de termo", t.tipo or "-"], ["Validade", t.validade or "-"], ["E-mail", t.email or "-"]]
    tbl = Table([[para(k, "TermLabel"), para(v)] for k, v in dados], colWidths=[3.4*cm, doc.width-3.4*cm])
    tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f1f3f5")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#d8dee4")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story.extend([tbl, Spacer(1, 0.35*cm)])

    if detalhes_dict:
        rows = [[para("Campo", "TermLabel"), para("Valor", "TermLabel")]]
        for k, v in detalhes_dict.items():
            rows.append([para(k), para(v)])
        dtable = Table(rows, colWidths=[4*cm, doc.width-4*cm], repeatRows=1)
        dtable.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eef2f7")),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#d8dee4")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([para("Detalhes especificos:", "TermLabel"), dtable, Spacer(1, 0.25*cm)])

    for cl in clausulas:
        story.append(para(_render_termo_text(cl, ctx)))
    if t.status == "Assinado" and t.data_assinatura:
        story.append(para(f"Assinado em {t.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {t.assinatura_ip or '-'}", "TermLabel"))

    sig_table = Table([[sig_img(t.assinatura_img), Spacer(5.6*cm, 1.8*cm)], [para(t.colaborador, "TermSmall"), para("Responsavel TI", "TermSmall")]], colWidths=[doc.width/2-0.4*cm, doc.width/2-0.4*cm], hAlign="CENTER")
    sig_table.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"BOTTOM"),("LINEABOVE",(0,1),(-1,1),0.7,colors.black),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
    story.extend([Spacer(1, 0.55*cm), KeepTogether([sig_table])])

    def footer(cv, doc_obj):
        cv.saveState()
        cv.setFont("Helvetica", 8)
        cv.setFillColor(colors.HexColor("#999999"))
        if rodape_txt:
            cv.drawCentredString(A4[0]/2, 1.25*cm, str(rodape_txt)[:160])
        cv.drawRightString(A4[0]-2*cm, 1.25*cm, f"Pagina {doc_obj.page}")
        cv.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    nome_pdf = f"termo_{safe_filename(t.tipo)}_{safe_filename(t.colaborador)}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)


@app.route("/api/termos", methods=["GET"])
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


@app.route("/api/termos", methods=["POST"])
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
    detalhes = {**detalhes, "_modelo": _get_termo_avulso_modelo(tipo)} if tipo else detalhes

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


def _termos_do_pacote(package_id):
    return db.session.execute(
        db.select(TermoAvulso)
        .where(TermoAvulso.package_id == clean_text(package_id, 16))
        .order_by(TermoAvulso.created_at.asc(), TermoAvulso.id.asc())
    ).scalars().all()


def _enviar_email_pacote(termos, url):
    if not termos or not termos[0].email:
        return False
    empresa = _get_setting("empresa", {}) or {}
    nome_empresa = empresa.get("nome", "TI Control") if isinstance(empresa, dict) else "TI Control"
    tipos = ", ".join(t.tipo for t in termos)
    subject, html, text = _render_email_template("pacote_termos", {
        "empresa": nome_empresa,
        "colaborador": termos[0].colaborador,
        "quantidade": len(termos),
        "termos": tipos,
        "link": url,
    })
    return bool(send_email(termos[0].email, subject, html, text).get("ok"))


def _gerar_link_pacote(termos):
    token = uuid.uuid4().hex + uuid.uuid4().hex
    expiry = datetime.now() + timedelta(days=7)
    for termo in termos:
        termo.package_token = token
        termo.package_token_expiry = expiry
    url = f"{get_app_base_url()}/assinar-termos/{token}"
    return token, expiry, url


@app.route("/api/termos/pacotes", methods=["POST"])
@app.route("/api/termos-avulsos/pacotes", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_pacote_termos():
    data = request.get_json(silent=True) or {}
    items = data.get("termos")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Adicione ao menos um termo ao pacote."}), 400
    if len(items) > 20:
        return jsonify({"error": "Cada pacote pode conter no máximo 20 termos."}), 400

    colaborador = clean_text(data.get("colaborador"), 120)
    setor = clean_text(data.get("setor"), 80)
    unidade = clean_text(data.get("unidade"), 80)
    email = clean_text(data.get("email"), 120)
    if not colaborador:
        return jsonify({"error": "Colaborador é obrigatório."}), 400
    email_error = validate_email(email)
    if email_error:
        return jsonify({"error": email_error}), 400

    modelos = _get_termos_avulsos_modelos()
    tipos_vistos = set()
    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            return jsonify({"error": "Termo inválido no pacote."}), 400
        tipo = clean_text(item.get("tipo"), 40)
        if not tipo or tipo not in modelos:
            return jsonify({"error": f"O modelo '{tipo or 'sem nome'}' não está disponível em Configurações > Termos."}), 400
        if tipo.casefold() in tipos_vistos:
            return jsonify({"error": f"O termo '{tipo}' foi adicionado mais de uma vez."}), 400
        tipos_vistos.add(tipo.casefold())
        detalhes = item.get("detalhes") if isinstance(item.get("detalhes"), dict) else {}
        detalhes = {**detalhes, "_modelo": modelos[tipo]}
        normalized_items.append({
            "tipo": tipo,
            "validade": clean_text(item.get("validade"), 10) or None,
            "detalhes": detalhes,
        })

    package_id = new_id("TP")
    termos = []
    for item in normalized_items:
        termo = TermoAvulso(
            id=new_id("TA"),
            package_id=package_id,
            tipo=item["tipo"],
            colaborador=colaborador,
            setor=setor,
            unidade=unidade,
            email=email,
            validade=item["validade"],
            detalhes=json.dumps(item["detalhes"], ensure_ascii=False),
            status="Pendente",
            created_by=current_user.username,
        )
        db.session.add(termo)
        termos.append(termo)

    _, expiry, url = _gerar_link_pacote(termos)
    audit("CRIAR_PACOTE_TERMOS", "alocacoes", package_id,
          f"Pacote com {len(termos)} termo(s) criado para {colaborador}")
    db.session.commit()
    email_enviado = _enviar_email_pacote(termos, url)
    return jsonify({
        "packageId": package_id,
        "terms": [t.to_dict() for t in termos],
        "url": url,
        "expiry": expiry.isoformat(),
        "emailEnviado": email_enviado,
    }), 201


@app.route("/api/termos/pacotes/<package_id>/sign-link", methods=["POST"])
@app.route("/api/termos-avulsos/pacotes/<package_id>/sign-link", methods=["POST"])
@requires("Administrador", "Técnico TI")
def gerar_link_pacote_termos(package_id):
    termos = _termos_do_pacote(package_id)
    if not termos:
        return jsonify({"error": "Pacote de termos não encontrado."}), 404
    pendentes = [t for t in termos if t.status != "Assinado"]
    if not pendentes:
        return jsonify({"error": "Todos os termos deste pacote já foram assinados."}), 400
    _, expiry, url = _gerar_link_pacote(termos)
    audit("GERAR_LINK_PACOTE_TERMOS", "alocacoes", package_id,
          f"Link do pacote gerado para {termos[0].colaborador}")
    db.session.commit()
    email_enviado = _enviar_email_pacote(termos, url)
    return jsonify({"url": url, "expiry": expiry.isoformat(), "emailEnviado": email_enviado})


@app.route("/api/termos/<tid>", methods=["GET"])
@app.route("/api/termos-avulsos/<tid>", methods=["GET"])
@api_auth
def get_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    return jsonify(t.to_dict())


@app.route("/api/termos/<tid>", methods=["PUT"])
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
        current_details = _termo_detalhes_raw(t)
        snapshot = current_details.get("_modelo")
        normalized = det if isinstance(det, dict) else {}
        if snapshot:
            normalized = {**normalized, "_modelo": snapshot}
        t.detalhes = json.dumps(normalized, ensure_ascii=False)

    audit("EDITAR_TERMO_AVULSO", "alocacoes", tid, f"Termo {t.tipo} de {t.colaborador} editado")
    db.session.commit()
    return jsonify(t.to_dict())


@app.route("/api/termos/<tid>", methods=["DELETE"])
@app.route("/api/termos-avulsos/<tid>", methods=["DELETE"])
@requires("Administrador")
def delete_termo_avulso(tid):
    t = db.get_or_404(TermoAvulso, tid)
    audit("EXCLUIR_TERMO_AVULSO", "alocacoes", tid,
          f"Termo {t.tipo} de {t.colaborador} excluído")
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/termos/<tid>/sign-link", methods=["POST"])
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
    url = f"{get_app_base_url()}/assinar-termo/{token}"
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


@app.route("/api/termos/<tid>/termo.pdf")
@app.route("/api/termos-avulsos/<tid>/termo.pdf")
@api_auth
def gerar_termo_avulso_pdf(tid):
    t = db.get_or_404(TermoAvulso, tid)
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível. Instale: pip install reportlab"}), 503

    empresa  = _get_setting("empresa", {}) or {}
    logo_b64 = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    tr_cfg = _termo_modelo_registrado(t)

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
    detalhes_dict = _termo_detalhes_raw(t)
    detalhes_dict.pop("_modelo", None)

    try:
        return _send_termo_avulso_pdf(t, empresa, logo_b64, titulo, preambulo, clausulas, rodape_txt, ctx, detalhes_dict)
    except Exception:
        app.logger.exception("Falha no layout novo do termo; usando gerador legado.")

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
        nome_pdf = f"termo_{safe_filename(t.tipo)}_{safe_filename(t.colaborador)}.pdf"
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)
    except Exception as exc:
        return jsonify({"error": f"Erro ao gerar PDF: {exc.__class__.__name__} — {exc}"}), 500


# ── Página pública de assinatura ──────────────────────────────────────────────

def _termo_avulso_assinatura_modelo(t):
    if not t:
        return {}
    empresa = _get_setting("empresa", {}) or {}
    cfg = _termo_modelo_registrado(t)
    ctx = {
        "colaborador": t.colaborador,
        "setor": t.setor,
        "unidade": t.unidade,
        "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else "",
        "tipo": t.tipo,
        "validade": t.validade or "—",
        "data": t.created_at.strftime("%Y-%m-%d") if t.created_at else str(date.today()),
    }
    return {
        "titulo": _render_termo_text(cfg.get("titulo", f"TERMO DE {str(t.tipo or 'TERMO').upper()}"), ctx),
        "preambulo": _render_termo_text(cfg.get("preambulo", ""), ctx),
        "clausulas": [_render_termo_text(cl, ctx) for cl in (cfg.get("clausulas") or [])],
        "rodape": _render_termo_text(cfg.get("rodape", ""), ctx),
    }


@app.route("/assinar-termo/<token>", methods=["GET"])
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
    colab = None
    if t:
        if t.email:
            colab = db.session.execute(db.select(Colaborador).filter_by(email=t.email)).scalar_one_or_none()
        if not colab:
            colab = db.session.execute(db.select(Colaborador).filter_by(nome=t.colaborador)).scalar_one_or_none()
    return render_template("assinar_avulso.html", termo=t, termo_modelo=_termo_avulso_assinatura_modelo(t), erro=erro, token=token,
                           cpf_required=bool(colab and colab.cpf))


@app.route("/assinar-termo/<token>", methods=["POST"])
@app.route("/assinar-avulso/<token>", methods=["POST"])
def submeter_assinatura_avulso(token):
    t = db.session.execute(
        db.select(TermoAvulso).filter_by(sign_token=token)
    ).scalar_one_or_none()
    if t is None:
        return render_template("assinar_avulso.html", termo=None, token=token,
                               termo_modelo={}, erro="Link inválido.", sucesso=False)
    colab = db.session.execute(db.select(Colaborador).filter_by(email=t.email)).scalar_one_or_none() if t.email else None
    if not colab:
        colab = db.session.execute(db.select(Colaborador).filter_by(nome=t.colaborador)).scalar_one_or_none()
    cpf_required = bool(colab and colab.cpf)
    if t.status == "Assinado":
        return render_template("assinar_avulso.html", termo=t, token=token,
                               termo_modelo=_termo_avulso_assinatura_modelo(t),
                               erro="Já assinado.", sucesso=False, cpf_required=cpf_required)
    if t.sign_token_expiry and datetime.now() > t.sign_token_expiry:
        return render_template("assinar_avulso.html", termo=t, token=token,
                               termo_modelo=_termo_avulso_assinatura_modelo(t),
                               erro="Link expirado.", sucesso=False, cpf_required=cpf_required)

    sig_data = request.form.get("assinatura", "").strip()
    nome     = request.form.get("nome_confirm", "").strip()
    cpf      = request.form.get("cpf_confirm", "").strip()

    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return render_template("assinar_avulso.html", termo=t, token=token,
                               termo_modelo=_termo_avulso_assinatura_modelo(t),
                               erro="Assinatura não capturada. Desenhe sua assinatura antes de confirmar.",
                               sucesso=False, cpf_required=cpf_required)
    if cpf_required and not cpf_matches(cpf, colab.cpf):
        return render_template("assinar_avulso.html", termo=t, token=token,
                               termo_modelo=_termo_avulso_assinatura_modelo(t),
                               erro="CPF digitado não confere com o cadastro do colaborador.",
                               sucesso=False, cpf_required=cpf_required)
    if not cpf_required and nome.lower() != t.colaborador.split()[0].lower() and nome.lower() != t.colaborador.lower():
        return render_template("assinar_avulso.html", termo=t, token=token,
                               termo_modelo=_termo_avulso_assinatura_modelo(t),
                               erro="Nome digitado não confere. Digite seu primeiro nome ou nome completo.",
                               sucesso=False, cpf_required=cpf_required)

    t.assinatura_img  = sig_data
    t.status          = "Assinado"
    t.data_assinatura = datetime.now()
    t.assinatura_ip   = request.remote_addr
    t.sign_token      = None
    t.sign_token_expiry = None
    db.session.commit()
    return render_template("assinar_avulso.html", termo=t, token=token, termo_modelo=_termo_avulso_assinatura_modelo(t), sucesso=True, cpf_required=cpf_required)


def _termos_por_package_token(token):
    return db.session.execute(
        db.select(TermoAvulso)
        .where(TermoAvulso.package_token == clean_text(token, 64))
        .order_by(TermoAvulso.created_at.asc(), TermoAvulso.id.asc())
    ).scalars().all()


def _colaborador_do_pacote(termos):
    if not termos:
        return None
    first = termos[0]
    colaborador = None
    if first.email:
        colaborador = db.session.execute(
            db.select(Colaborador).where(Colaborador.email == first.email)
        ).scalar_one_or_none()
    if not colaborador:
        colaborador = db.session.execute(
            db.select(Colaborador).where(Colaborador.nome == first.colaborador)
        ).scalar_one_or_none()
    return colaborador


def _render_assinatura_pacote(token, termos, erro=None, sucesso=False, status=200):
    colaborador = _colaborador_do_pacote(termos)
    documentos = [{"termo": termo, "modelo": _termo_avulso_assinatura_modelo(termo)} for termo in termos]
    return render_template(
        "assinar_pacote.html",
        token=token,
        termos=termos,
        documentos=documentos,
        erro=erro,
        sucesso=sucesso,
        cpf_required=bool(colaborador and colaborador.cpf),
    ), status


@app.route("/assinar-termos/<token>", methods=["GET"])
def pagina_assinatura_pacote(token):
    termos = _termos_por_package_token(token)
    if not termos:
        return _render_assinatura_pacote(token, [], erro="Link inválido ou não encontrado.", status=404)
    expiry = min((t.package_token_expiry for t in termos if t.package_token_expiry), default=None)
    if expiry and datetime.now() > expiry:
        return _render_assinatura_pacote(token, termos, erro="Este link de assinatura expirou.", status=410)
    return _render_assinatura_pacote(
        token,
        termos,
        sucesso=all(t.status == "Assinado" for t in termos),
    )


@app.route("/assinar-termos/<token>", methods=["POST"])
def submeter_assinatura_pacote(token):
    termos = _termos_por_package_token(token)
    if not termos:
        return _render_assinatura_pacote(token, [], erro="Link inválido ou não encontrado.", status=404)
    expiry = min((t.package_token_expiry for t in termos if t.package_token_expiry), default=None)
    if expiry and datetime.now() > expiry:
        return _render_assinatura_pacote(token, termos, erro="Este link de assinatura expirou.", status=410)

    pendentes = [t for t in termos if t.status != "Assinado"]
    if not pendentes:
        return _render_assinatura_pacote(token, termos, sucesso=True)

    accepted_ids = set(request.form.getlist("aceitos"))
    pending_ids = {t.id for t in pendentes}
    if not pending_ids.issubset(accepted_ids):
        return _render_assinatura_pacote(
            token,
            termos,
            erro="Leia e aceite todos os termos pendentes antes de assinar.",
            status=400,
        )

    signature = request.form.get("assinatura", "").strip()
    nome = request.form.get("nome_confirm", "").strip()
    cpf = request.form.get("cpf_confirm", "").strip()
    colaborador = _colaborador_do_pacote(termos)
    cpf_required = bool(colaborador and colaborador.cpf)
    if not signature.startswith("data:image/png;base64,"):
        return _render_assinatura_pacote(token, termos, erro="Desenhe sua assinatura antes de confirmar.", status=400)
    if cpf_required and not cpf_matches(cpf, colaborador.cpf):
        return _render_assinatura_pacote(token, termos, erro="CPF digitado não confere com o cadastro.", status=400)
    expected_name = termos[0].colaborador or ""
    first_name = expected_name.split()[0].casefold() if expected_name.split() else ""
    if not cpf_required and nome.casefold() not in {first_name, expected_name.casefold()}:
        return _render_assinatura_pacote(token, termos, erro="Nome digitado não confere com o cadastro.", status=400)

    signed_at = datetime.now()
    for termo in pendentes:
        termo.assinatura_img = signature
        termo.status = "Assinado"
        termo.data_assinatura = signed_at
        termo.assinatura_ip = request.remote_addr
    audit("ASSINAR_PACOTE_TERMOS", "alocacoes", termos[0].package_id or "",
          f"{len(pendentes)} termo(s) assinados por {expected_name}")
    db.session.commit()
    return _render_assinatura_pacote(token, termos, sucesso=True)
