"""Rotas de devolucoes, laudos tecnicos e assinatura publica."""
import base64
import io
import json
import uuid
from datetime import date, datetime, timedelta

from flask import Response, jsonify, render_template, request, send_file
from flask_login import current_user

from app import (
    PDF_OK,
    _get_email_config,
    _get_setting,
    _pdf_draw_logo,
    _render_termo_text,
    _send_email_async,
    api_auth,
    audit,
    check_public_token_rate_limit,
    clean_text,
    cpf_matches,
    get_app_base_url,
    json_payload,
    new_id,
    parse_float,
    requires,
    safe_filename,
    send_email_laudo_editado_colab,
    send_email_laudo_editado_rh,
    send_email_laudo_rh,
    send_email_link_devolucao,
    validate_email,
    app,
)
from extensions import db
from models import Colaborador, Devolucao, LaudoTecnico
from routes.blueprint import bp

if PDF_OK:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas as rl_canvas


def _send_devolucao_term_pdf(dev, c, empresa, logo_b64, titulo, preambulo, clausulas, declaracao, rodape_txt, ctx, ativos, perifs):
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
        reader = ImageReader(io.BytesIO(raw)); iw, ih = reader.getSize()
        scale = min(max_w / iw, max_h / ih)
        return Image(io.BytesIO(raw), width=iw * scale, height=ih * scale)

    story = []
    if logo_b64 and str(logo_b64).startswith("data:"):
        try:
            raw = base64.b64decode(logo_b64.split(",", 1)[1])
            reader = ImageReader(io.BytesIO(raw)); iw, ih = reader.getSize()
            scale = min((3.2*cm)/iw, (1.5*cm)/ih)
            story.append(Table([[Image(io.BytesIO(raw), width=iw*scale, height=ih*scale)]], colWidths=[doc.width], style=[("ALIGN",(0,0),(-1,-1),"CENTER"),("BOTTOMPADDING",(0,0),(-1,-1),8)]))
        except Exception:
            pass
    story += [para(titulo, "TermTitle"), para(f"Data: {dev.data_devolucao} - Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", "TermMeta")]
    if isinstance(empresa, dict) and empresa.get("nome"):
        story.append(para(empresa["nome"], "TermMeta"))
    story.append(Spacer(1, 0.35*cm))

    dados = [["Colaborador", dev.colaborador], ["Matricula", (c.matricula if c else "") or "-"], ["Setor / Unidade", f"{dev.setor or '-'} / {dev.unidade or '-'}"]]
    tbl = Table([[para(k, "TermLabel"), para(v)] for k, v in dados], colWidths=[3.2*cm, doc.width-3.2*cm])
    tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f1f3f5")),("BOX",(0,0),(-1,-1),0.5,colors.HexColor("#d8dee4")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
    story += [tbl, Spacer(1, 0.35*cm)]

    for linha in str(preambulo or "").split("\n"):
        if linha.strip():
            story.append(para(linha.strip()))

    def item_table(title, rows):
        if not rows:
            return
        data = [[para(title, "TermLabel")]] + [[para(str(x))] for x in rows]
        t = Table(data, colWidths=[doc.width], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#eef2f7")),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#d8dee4")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        story.extend([t, Spacer(1, 0.25*cm)])

    item_table("Equipamentos devolvidos", ativos)
    item_table("Perifericos / insumos devolvidos", perifs)
    if dev.cobranca_aplicada is not None or dev.cobranca_obs:
        status_cobranca = "Sera cobrado" if dev.cobranca_aplicada else "Nao sera cobrado"
        linhas_cobranca = [f"Decisao do RH: {status_cobranca}"]
        if dev.cobranca_aplicada:
            linhas_cobranca.append(f"Valor confirmado: R$ {(dev.cobranca_valor or 0):.2f}")
        if dev.cobranca_obs:
            linhas_cobranca.append(f"Observacao do RH: {dev.cobranca_obs}")
        item_table("Cobranca por dano", linhas_cobranca)
    for cl in clausulas:
        story.append(para(_render_termo_text(cl, ctx)))
    if declaracao:
        story += [Spacer(1, 0.15*cm), para(declaracao, "TermLabel")]
    if dev.status == "Assinado" and dev.data_assinatura:
        story.append(para(f"Assinado em {dev.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {dev.assinatura_ip or '-'}", "TermLabel"))
    sig_table = Table([[sig_img(dev.assinatura_img), Spacer(5.6*cm, 1.8*cm)], [para(dev.colaborador, "TermSmall"), para("Responsavel TI", "TermSmall")]], colWidths=[doc.width/2-0.4*cm, doc.width/2-0.4*cm], hAlign="CENTER")
    sig_table.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER"),("VALIGN",(0,0),(-1,-1),"BOTTOM"),("LINEABOVE",(0,1),(-1,1),0.7,colors.black),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6)]))
    story += [Spacer(1, 0.55*cm), KeepTogether([sig_table])]

    def footer(cv, doc_obj):
        cv.saveState(); cv.setFont("Helvetica", 8); cv.setFillColor(colors.HexColor("#999999"))
        if rodape_txt: cv.drawCentredString(A4[0]/2, 1.25*cm, str(rodape_txt)[:160])
        cv.drawRightString(A4[0]-2*cm, 1.25*cm, f"Pagina {doc_obj.page}"); cv.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=f"devolucao_{safe_filename(dev.colaborador)}_{dev.data_devolucao}.pdf")


@bp.route("/api/devolucoes/<did>/termo.pdf")
@api_auth
def devolucao_pdf(did):
    """PDF do Termo de Devolução a partir do registro Devolucao (com assinatura digital)."""
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível."}), 503
    dev = db.get_or_404(Devolucao, did)
    c   = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None

    empresa  = _get_setting("empresa", {}) or {}
    td_cfg   = _get_setting("termo_devolucao", {}) or {}
    logo_b64 = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    cobranca_status = "Será cobrado" if dev.cobranca_aplicada else "Não será cobrado"
    ctx = {"colaborador": dev.colaborador, "setor": dev.setor or "—",
           "unidade": dev.unidade or "—", "data": dev.data_devolucao or str(date.today()),
           "matricula": (c.matricula if c else "—") or "—",
           "cobranca_status": cobranca_status, "cobranca_valor": f"{(dev.cobranca_valor or 0):.2f}",
           "cobranca_obs": dev.cobranca_obs or "",
           "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else ""}

    titulo   = _render_termo_text(td_cfg.get("titulo", "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS"), ctx)
    preambulo= _render_termo_text(td_cfg.get("preambulo", ""), ctx)
    clausulas= td_cfg.get("clausulas", [])
    rodape_txt = _render_termo_text(td_cfg.get("rodape", ""), ctx)
    decl_padrao= "Declaro ter devolvido todos os equipamentos listados acima em plenas condições."
    declaracao = _render_termo_text(td_cfg.get("declaracao", decl_padrao), ctx)

    try:
        ativos = json.loads(dev.ativos_devolvidos or "[]")
        perifs = json.loads(dev.perifericos_devolvidos or "[]")
        return _send_devolucao_term_pdf(dev, c, empresa, logo_b64, titulo, preambulo, clausulas, declaracao, rodape_txt, ctx, ativos, perifs)
    except Exception:
        app.logger.exception("Falha no layout novo do termo de devolucao; usando gerador legado.")

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

        if dev.cobranca_aplicada is not None or dev.cobranca_obs:
            cv.setFont("Helvetica-Bold", 11)
            cv.drawString(2*cm, y, "Cobrança por dano:"); y -= 0.65*cm
            cv.setFont("Helvetica", 10)
            cv.drawString(2.5*cm, y, f"Decisão do RH: {'Será cobrado' if dev.cobranca_aplicada else 'Não será cobrado'}"); y -= 0.55*cm
            if dev.cobranca_aplicada:
                cv.drawString(2.5*cm, y, f"Valor confirmado: R$ {(dev.cobranca_valor or 0):.2f}"); y -= 0.55*cm
            if dev.cobranca_obs:
                for linha in str(dev.cobranca_obs).split("\n"):
                    cv.drawString(2.5*cm, y, f"Obs.: {linha[:90]}"); y -= 0.55*cm
            y -= 0.2*cm

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


@bp.route("/api/devolucoes/<did>/laudo", methods=["POST"])
@requires("Administrador", "Técnico TI")
def registrar_laudo(did):
    """Técnico registra avaliação dos equipamentos. Dispara e-mail de ciência para o RH."""
    dev = db.get_or_404(Devolucao, did)
    if dev.laudo_status not in (None, "Aguardando Laudo"):
        return jsonify({"error": f"Laudo já registrado (status: {dev.laudo_status})."}), 400

    d = json_payload()
    rh_email = clean_text(d.get("rhEmail"), 120)
    if not rh_email:
        return jsonify({"error": "E-mail do RH (rhEmail) é obrigatório."}), 400
    err_email = validate_email(rh_email)
    if err_email:
        return jsonify({"error": err_email}), 400

    tecnico         = clean_text(d.get("tecnico") or current_user.nome or current_user.username, 120)
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

    link_rh = f"{get_app_base_url()}/rh/laudo/{rh_token}"
    cfg = _get_email_config()
    email_configurado = bool(cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"))
    if email_configurado:
        _send_email_async(send_email_laudo_rh, rh_email, dev.colaborador, tecnico, link_rh)

    audit("LAUDO_TECNICO", "devolucoes", did,
          f"Laudo de {tecnico} para {dev.colaborador} — cobrança: {tem_cobranca}")
    return jsonify({
        "ok": True, "laudoId": laudo.id,
        "laudoStatus": "Aguardando RH",
        "linkRH": link_rh,
        "emailRHEnviado": email_configurado,
    })


@bp.route("/api/devolucoes/<did>/laudo", methods=["PUT"])
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
    laudo.editado_por = clean_text(current_user.nome or current_user.username, 120)
    laudo.motivo_edicao = motivo

    if "temCobranca" in d or "valorCobranca" in d:
        dev.cobranca_valor = laudo.valor_cobranca if laudo.tem_cobranca else 0.0

    db.session.commit()
    audit("LAUDO_EDITADO", "laudos_tecnicos", laudo.id,
          f"Laudo editado por {laudo.editado_por} — motivo: {motivo}")

    editor = laudo.editado_por
    cfg = _get_email_config()
    email_configurado = bool(cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"))

    email_rh_ok = False
    email_colab_ok = False
    if email_configurado:
        if dev.rh_email:
            _send_email_async(send_email_laudo_editado_rh, dev.rh_email, dev.colaborador, editor, motivo)
            email_rh_ok = True
        colab = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
        if colab and colab.email:
            _send_email_async(send_email_laudo_editado_colab, colab.email, dev.colaborador, motivo)
            email_colab_ok = True

    return jsonify({
        "ok": True,
        "laudo": laudo.to_dict(),
        "emailRHEnviado": email_rh_ok,
        "emailColabEnviado": email_colab_ok,
    })


@bp.route("/api/devolucoes/<did>/reenviar-rh", methods=["POST"])
@requires("Administrador", "Técnico TI")
def reenviar_laudo_rh(did):
    """Reenvia ou renova o link de ciência do laudo para o RH.

    A resposta sempre inclui o link para cópia manual, funcionando como backup
    quando o SMTP estiver desabilitado ou o envio falhar.
    """
    dev = db.get_or_404(Devolucao, did)
    if not dev.laudo_status or dev.laudo_status == "Aguardando Laudo":
        return jsonify({"error": "Registre o laudo técnico antes de enviar para o RH."}), 400
    if dev.laudo_status == "Aprovado":
        return jsonify({"error": "O RH já deu ciência deste laudo."}), 400

    laudo = db.session.execute(
        db.select(LaudoTecnico).filter_by(devolucao_id=did)
        .order_by(LaudoTecnico.data_avaliacao.desc())
    ).scalar_one_or_none()
    if not laudo:
        return jsonify({"error": "Laudo técnico não encontrado para esta devolução."}), 404

    d = json_payload()
    rh_email = clean_text(d.get("rhEmail") or dev.rh_email, 120)
    if not rh_email:
        return jsonify({"error": "Informe o e-mail do RH para reenviar o laudo."}), 400
    err_email = validate_email(rh_email)
    if err_email:
        return jsonify({"error": err_email}), 400

    renovado = False
    if not dev.rh_token or (dev.rh_token_expiry and datetime.now() > dev.rh_token_expiry):
        dev.rh_token = uuid.uuid4().hex + uuid.uuid4().hex
        renovado = True
    dev.rh_token_expiry = datetime.now() + timedelta(days=7)
    dev.rh_email = rh_email
    dev.laudo_status = "Aguardando RH"
    db.session.commit()

    link_rh = f"{get_app_base_url()}/rh/laudo/{dev.rh_token}"
    cfg = _get_email_config()
    email_configurado = bool(cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"))
    email_result = {"ok": False, "error": "SMTP não configurado."}
    if email_configurado:
        email_result = send_email_laudo_rh(rh_email, dev.colaborador, laudo.tecnico, link_rh)

    audit("REENVIAR_LAUDO_RH", "devolucoes", did,
          f"Link RH reenviado para {rh_email}; email_ok={email_result.get('ok', False)}; renovado={renovado}")
    return jsonify({
        "ok": True,
        "url": link_rh,
        "expiry": dev.rh_token_expiry.isoformat(),
        "rhEmail": rh_email,
        "emailEnviado": bool(email_result.get("ok")),
        "emailErro": "" if email_result.get("ok") else clean_text(email_result.get("error"), 300),
        "renovado": renovado,
    })


@bp.route("/rh/laudo/<rh_token>", methods=["GET"])
def pagina_rh_laudo(rh_token):
    """Página pública para o RH visualizar o laudo e dar ciência (sem login)."""
    if not check_public_token_rate_limit("rh_laudo", rh_token):
        return render_template("rh_laudo.html", dev=None, laudo=None, erro="Muitas tentativas. Aguarde um momento.", rh_token=rh_token), 429
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


@bp.route("/rh/laudo/<rh_token>", methods=["POST"])
def submeter_ciencia_rh(rh_token):
    """RH dá ciência do laudo. Após aprovação, gera link de assinatura para o colaborador."""
    if not check_public_token_rate_limit("rh_laudo", rh_token):
        return render_template("rh_laudo.html", dev=None, laudo=None, rh_token=rh_token,
                               erro="Muitas tentativas. Aguarde um momento."), 429
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

    cobranca_obs = request.form.get("cobranca_obs", "").strip()[:2000]
    cobranca_decisao = request.form.get("cobranca_decisao", "").strip().lower()
    cobranca_aplicada = False
    cobranca_valor = 0.0
    if laudo and laudo.tem_cobranca:
        if cobranca_decisao not in ("sim", "nao"):
            return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                                   erro="Informe se o valor do dano será cobrado ou não.")
        cobranca_aplicada = cobranca_decisao == "sim"
        if cobranca_aplicada:
            cobranca_valor = parse_float(request.form.get("cobranca_valor"), default=0.0, minimum=0.0)
            if cobranca_valor <= 0:
                return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                                       erro="Informe um valor maior que zero para confirmar a cobrança.")

    dev.laudo_status    = "Aprovado"
    dev.rh_ciencia_ip   = request.remote_addr
    dev.rh_data_ciencia = datetime.now()
    dev.cobranca_obs    = cobranca_obs
    dev.cobranca_aplicada = cobranca_aplicada if laudo and laudo.tem_cobranca else False
    dev.cobranca_valor  = cobranca_valor
    dev.rh_token        = None
    dev.rh_token_expiry = None

    # Gera link de assinatura para o colaborador
    sign_token = uuid.uuid4().hex + uuid.uuid4().hex
    dev.sign_token        = sign_token
    dev.sign_token_expiry = datetime.now() + timedelta(days=7)
    db.session.commit()

    link_assinatura = f"{get_app_base_url()}/devolver/{sign_token}"
    email_colab_enviado = False
    colab = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
    cfg = _get_email_config()
    if colab and colab.email and cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"):
        _send_email_async(send_email_link_devolucao, colab.email, dev.colaborador, link_assinatura)
        email_colab_enviado = True

    audit("CIENCIA_RH", "devolucoes", dev.id,
          f"RH deu ciência do laudo de {dev.colaborador}. E-mail colaborador: {email_colab_enviado}")
    return render_template("rh_laudo.html", dev=dev, laudo=laudo, rh_token=rh_token,
                           sucesso=True, link_assinatura=link_assinatura,
                           email_colab_enviado=email_colab_enviado)


@bp.route("/api/devolucoes", methods=["GET"])
@requires("Administrador", "Técnico TI")
def get_devolucoes():
    devs = db.session.execute(db.select(Devolucao).order_by(Devolucao.data_devolucao.desc())).scalars().all()
    return jsonify([d.to_dict() for d in devs])


@bp.route("/api/devolucoes/<did>", methods=["GET"])
@requires("Administrador", "Técnico TI")
def get_devolucao(did):
    d = db.get_or_404(Devolucao, did)
    result = d.to_dict()
    laudo = db.session.execute(
        db.select(LaudoTecnico).filter_by(devolucao_id=did)
        .order_by(LaudoTecnico.data_avaliacao.desc())
    ).scalar_one_or_none()
    result["laudo"] = laudo.to_dict() if laudo else None
    return jsonify(result)


@bp.route("/api/devolucoes/<did>/sign-link", methods=["POST"])
@requires("Administrador", "Técnico TI")
def gerar_link_devolucao(did):
    dev = db.get_or_404(Devolucao, did)
    if dev.status == "Assinado":
        return jsonify({"error": "Devolução já assinada."}), 400
    token = uuid.uuid4().hex + uuid.uuid4().hex
    dev.sign_token = token
    dev.sign_token_expiry = datetime.now() + timedelta(days=7)
    audit("GERAR_LINK_DEVOLUCAO", "devolucoes", did, f"Link gerado para {dev.colaborador}")
    db.session.commit()
    url = f"{get_app_base_url()}/devolver/{token}"
    # Envia e-mail se colaborador tiver e-mail e SMTP configurado
    email_enviado = False
    c = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
    email_dest = (c.email if c else "") or ""
    cfg = _get_email_config()
    if email_dest and cfg.get("enabled") and cfg.get("host") and cfg.get("from_email"):
        _send_email_async(send_email_link_devolucao, email_dest, dev.colaborador, url)
        email_enviado = True
    return jsonify({"url": url, "expiry": dev.sign_token_expiry.isoformat(),
                    "emailEnviado": email_enviado})


@bp.route("/devolver/<token>", methods=["GET"])
def pagina_devolucao(token):
    if not check_public_token_rate_limit("sign_devolucao", token):
        return render_template("devolver.html", dev=None, token=token, erro="Muitas tentativas. Aguarde um momento."), 429
    dev = db.session.execute(db.select(Devolucao).filter_by(sign_token=token)).scalar_one_or_none()
    erro = None
    if dev is None:
        erro = "Link inválido ou não encontrado."
    elif dev.status == "Assinado":
        erro = "Esta devolução já foi assinada."
    elif dev.sign_token_expiry and datetime.now() > dev.sign_token_expiry:
        erro = "Este link expirou."
    colab = db.session.get(Colaborador, dev.colaborador_id) if dev and dev.colaborador_id else None
    return render_template("devolver.html", dev=dev, erro=erro, token=token,
                           cpf_required=bool(colab and colab.cpf))


@bp.route("/devolver/<token>", methods=["POST"])
def submeter_devolucao(token):
    if not check_public_token_rate_limit("sign_devolucao", token):
        return render_template("devolver.html", dev=None, token=token, erro="Muitas tentativas. Aguarde um momento."), 429
    dev = db.session.execute(db.select(Devolucao).filter_by(sign_token=token)).scalar_one_or_none()
    if dev is None:
        return render_template("devolver.html", dev=None, token=token, erro="Link inválido.")
    colab = db.session.get(Colaborador, dev.colaborador_id) if dev.colaborador_id else None
    cpf_required = bool(colab and colab.cpf)
    if dev.status == "Assinado":
        return render_template("devolver.html", dev=dev, token=token, erro="Já assinado.", sucesso=False,
                               cpf_required=cpf_required)
    if dev.sign_token_expiry and datetime.now() > dev.sign_token_expiry:
        return render_template("devolver.html", dev=dev, token=token, erro="Link expirado.",
                               cpf_required=cpf_required)

    sig_data = request.form.get("assinatura", "").strip()
    nome     = request.form.get("nome_confirm", "").strip()
    cpf      = request.form.get("cpf_confirm", "").strip()

    if not sig_data or not sig_data.startswith("data:image/png;base64,"):
        return render_template("devolver.html", dev=dev, token=token,
                               erro="Assinatura não capturada. Desenhe sua assinatura antes de confirmar.",
                               cpf_required=cpf_required)
    if cpf_required and not cpf_matches(cpf, colab.cpf):
        return render_template("devolver.html", dev=dev, token=token,
                               erro="CPF digitado não confere com o cadastro do colaborador.",
                               cpf_required=cpf_required)
    if not cpf_required and nome.lower() != dev.colaborador.split()[0].lower() and nome.lower() != dev.colaborador.lower():
        return render_template("devolver.html", dev=dev, token=token,
                               erro="Nome digitado não confere. Digite seu primeiro nome ou nome completo.",
                               cpf_required=cpf_required)

    dev.assinatura_img   = sig_data
    dev.assinatura_ip    = request.remote_addr
    dev.data_assinatura  = datetime.now()
    dev.status           = "Assinado"
    dev.sign_token       = None
    dev.sign_token_expiry= None
    audit("ASSINAR_DEVOLUCAO", "devolucoes", dev.id,
          f"Devolução {dev.id} assinada por {dev.colaborador}")
    db.session.commit()
    return render_template("devolver.html", dev=dev, token=token, sucesso=True, cpf_required=cpf_required)


@bp.route("/api/devolucoes/<did>/assinatura.png")
@api_auth
def get_assinatura_devolucao(did):
    dev = db.get_or_404(Devolucao, did)
    if not dev.assinatura_img or not dev.assinatura_img.startswith("data:image/png;base64,"):
        return jsonify({"error": "Sem assinatura capturada."}), 404
    raw = base64.b64decode(dev.assinatura_img.split(",", 1)[1])
    return Response(raw, mimetype="image/png", headers={"Cache-Control": "private, max-age=3600"})
