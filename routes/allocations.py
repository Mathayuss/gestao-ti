"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
import base64
from datetime import timedelta
from app import _export_route_globals

globals().update(_export_route_globals())


def _send_allocation_term_pdf(al, aid, empresa, logo_b64, titulo, preambulo, clausulas, rodape_txt, ctx):
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer,
        Table, TableStyle,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.7 * cm,
        bottomMargin=2.1 * cm,
        title=titulo,
        author=empresa.get("nome", "") if isinstance(empresa, dict) else "",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TermTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=14, leading=17, alignment=TA_CENTER, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        name="TermMeta", parent=styles["Normal"], fontSize=9, leading=11,
        alignment=TA_CENTER, textColor=colors.HexColor("#555555"),
    ))
    styles.add(ParagraphStyle(
        name="TermBody", parent=styles["BodyText"], fontSize=10, leading=14,
        alignment=TA_JUSTIFY, spaceAfter=7,
    ))
    styles.add(ParagraphStyle(
        name="TermLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10, leading=13, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="TermSmall", parent=styles["Normal"], fontSize=8, leading=10,
        alignment=TA_CENTER, textColor=colors.HexColor("#666666"),
    ))

    def para(text, style="TermBody"):
        txt = escape(str(text or "")).replace("\n", "<br/>")
        return Paragraph(txt, styles[style])

    def data_image_flowable(data_url, max_w=5.6 * cm, max_h=1.8 * cm):
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
            raw_logo = base64.b64decode(logo_b64.split(",", 1)[1])
            reader = ImageReader(io.BytesIO(raw_logo))
            iw, ih = reader.getSize()
            scale = min((3.2 * cm) / iw, (1.5 * cm) / ih)
            logo = Image(io.BytesIO(raw_logo), width=iw * scale, height=ih * scale)
            story.append(Table([[logo]], colWidths=[doc.width], style=[
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
        except Exception:
            pass

    story.extend([
        para(titulo, "TermTitle"),
        para(f"No. {al.termo or aid} - Data: {al.data_aloc}", "TermMeta"),
    ])
    if isinstance(empresa, dict) and empresa.get("nome"):
        story.append(para(empresa["nome"], "TermMeta"))
    story.append(Spacer(1, 0.35 * cm))

    for linha in str(preambulo or "").split("\n"):
        if linha.strip():
            story.append(para(linha.strip()))

    ativo_table = Table(
        [[para("Ativo", "TermLabel"), para(al.ativo_nome or al.ativo_id or "-", "TermBody")]],
        colWidths=[2.5 * cm, doc.width - 2.5 * cm],
    )
    ativo_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f3f5")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8dee4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([Spacer(1, 0.15 * cm), ativo_table, Spacer(1, 0.35 * cm)])

    if (al.tipo or "Responsabilidade") == "Empréstimo" and al.data_devolucao_prevista:
        story.append(para(f"Devolucao prevista: {al.data_devolucao_prevista}", "TermLabel"))

    if al.items:
        item_rows = [[para("Qtd.", "TermLabel"), para("Periferico entregue", "TermLabel")]]
        for p in al.items:
            item_rows.append([para(str(p.quantidade), "TermBody"), para(p.supply_nome, "TermBody")])
        items_table = Table(item_rows, colWidths=[2 * cm, doc.width - 2 * cm], repeatRows=1)
        items_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d8dee4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([para("Perifericos entregues nesta alocacao:", "TermLabel"), items_table, Spacer(1, 0.3 * cm)])

    for cl in clausulas:
        story.append(para(_render_termo_text(cl, ctx)))

    if al.termo_status == "Assinado" and al.data_assinatura:
        story.append(Spacer(1, 0.15 * cm))
        story.append(para(
            f"Assinado em {al.data_assinatura.strftime('%d/%m/%Y %H:%M')}  IP: {al.assinatura_ip or '-'}",
            "TermLabel",
        ))

    ti_label = al.assinatura_ti_nome or "Responsavel TI"
    sig_table = Table(
        [
            [data_image_flowable(al.assinatura_img), data_image_flowable(al.assinatura_ti_img)],
            [para(al.colaborador, "TermSmall"), para(ti_label, "TermSmall")],
        ],
        colWidths=[doc.width / 2 - 0.4 * cm, doc.width / 2 - 0.4 * cm],
        hAlign="CENTER",
    )
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LINEABOVE", (0, 1), (-1, 1), 0.7, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([Spacer(1, 0.55 * cm), KeepTogether([sig_table])])

    def footer(cv, doc_obj):
        cv.saveState()
        cv.setFont("Helvetica", 8)
        cv.setFillColor(colors.HexColor("#999999"))
        if rodape_txt:
            cv.drawCentredString(A4[0] / 2, 1.25 * cm, str(rodape_txt)[:160])
        cv.drawRightString(A4[0] - 2 * cm, 1.25 * cm, f"Pagina {doc_obj.page}")
        cv.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)
    nome_pdf = f"termo_{safe_filename(al.colaborador)}_{safe_filename(al.termo or aid)}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=nome_pdf)


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
    perifericos_raw = d.get("perifericos", []) or []
    if not isinstance(perifericos_raw, list):
        perifericos_raw = []
        erros.append("Lista de periféricos inválida.")
    perifericos_map = {}
    for p in perifericos_raw:
        if not isinstance(p, dict):
            erros.append("Item de periférico inválido.")
            continue
        supply_id = clean_text(p.get("supplyId", ""), 16)
        qty = parse_int(p.get("quantidade", 1), default=1, minimum=1)
        if not supply_id:
            erros.append("Periférico sem identificação.")
            continue
        perifericos_map[supply_id] = perifericos_map.get(supply_id, 0) + qty
    perifericos_in = [{"supplyId": sid, "quantidade": qty} for sid, qty in perifericos_map.items()]
    total_perifericos = 0
    for p in perifericos_in:
        s = db.session.get(Supply, p.get("supplyId",""))
        qty = p["quantidade"]
        total_perifericos += qty
        if not s: erros.append(f"Periférico '{p.get('supplyId')}' não encontrado.")
        elif s.estoque < qty: erros.append(f"'{s.nome}': estoque insuficiente ({s.estoque} disponível, {qty} solicitado).")
    max_perifs = parse_int(regras.get("max_perifericos_por_colab", 0), default=0, minimum=0)
    if max_perifs and total_perifericos > max_perifs:
        erros.append(f"Quantidade de periféricos acima do limite configurado ({total_perifericos}/{max_perifs}).")

    if erros:
        return jsonify({"error":"Alocação cancelada:\n" + "\n".join(erros)}), 400

    # ── Tudo OK — executa transação ──────────────────────────────────────
    try:
        aid = new_id("AL")
        tipo_aloc = clean_text(d.get("tipo") or "Responsabilidade", 30)
        if tipo_aloc not in ("Responsabilidade", "Empréstimo"):
            tipo_aloc = "Responsabilidade"
        data_dev = clean_text(d.get("dataDevolucaoPrevista") or "", 10) or None
        alloc = Allocation(
            id=aid, ativo_id=asset.id,
            ativo_nome=f"{asset.hostname} ({asset.fabricante} {asset.modelo})",
            colaborador=colab.nome, setor=clean_text(d.get("setor") or colab.setor, 80),
            unidade=clean_text(d.get("unidade") or colab.unidade, 80), email=clean_text(d.get("email") or colab.email, 120),
            data_aloc=str(date.today()), motivo=clean_text(d.get("motivo") or "Uso contínuo", 80),
            status="Ativo", termo=f"TERMO-{aid}", termo_status="Pendente",
            tipo=tipo_aloc, data_devolucao_prevista=data_dev,
        )
        db.session.add(alloc)

        asset.status="Alocado"; asset.colaborador=colab.nome
        asset.setor=alloc.setor; asset.unidade=alloc.unidade

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
                colaborador=colab.nome, ativo_id=asset.id, motivo="Alocação",
            ))

        audit("ALOCACAO","alocacoes",aid,f"{asset.hostname} → {colab.nome} ({len(perifericos_in)} periféricos)")
        db.session.commit()
        return jsonify(alloc.to_dict(include_items=True)), 201
    except Exception:
        db.session.rollback()
        raise


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


@app.route("/api/allocations/<aid>/perifericos/<item_id>/troca", methods=["POST"])
@requires("Administrador","TÃ©cnico TI")
def trocar_periferico_defeituoso(aid, item_id):
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo":
        return jsonify({"error":"NÃ£o Ã© possÃ­vel trocar perifÃ©rico de alocaÃ§Ã£o encerrada."}), 400

    item = db.session.execute(
        db.select(AllocationItem).filter_by(id=item_id, allocation_id=aid)
    ).scalar_one_or_none()
    if not item:
        return jsonify({"error":"PerifÃ©rico vinculado Ã  alocaÃ§Ã£o nÃ£o encontrado."}), 404

    d = request.get_json() or {}
    qty = parse_int(d.get("quantidade", 1), default=1, minimum=1)
    if qty > (item.quantidade or 0):
        return jsonify({"error":f"Quantidade acima do vÃ­nculo atual ({item.quantidade} disponÃ­vel para troca)."}), 400

    novo_supply_id = clean_text(d.get("novoSupplyId") or item.supply_id, 16)
    novo_supply = db.session.get(Supply, novo_supply_id)
    if not novo_supply:
        return jsonify({"error":"PerifÃ©rico substituto nÃ£o encontrado no estoque."}), 404
    if (novo_supply.estoque or 0) < qty:
        return jsonify({"error":f"Estoque insuficiente para substituiÃ§Ã£o ({novo_supply.estoque} disponÃ­vel, {qty} solicitado)."}), 400

    motivo = clean_text(d.get("motivo") or "Defeito", 80)
    observacao = clean_text(d.get("observacao") or "", 240)
    detalhe_obs = f" â€” {observacao}" if observacao else ""
    asset = db.session.get(Asset, al.ativo_id) if al.ativo_id else None

    try:
        antigo_nome = item.supply_nome
        antigo_supply_id = item.supply_id
        novo_supply.estoque -= qty

        db.session.add(SupplyMovement(
            id=new_id("MOV"), tipo="DEFEITO", ref_id=antigo_supply_id, supply_nome=antigo_nome,
            descricao=f"Troca por defeito na alocaÃ§Ã£o {aid}: {antigo_nome} x{qty} ({motivo}){detalhe_obs}",
            quantidade=qty, colaborador=al.colaborador, ativo_id=al.ativo_id, motivo=motivo,
        ))
        db.session.add(SupplyMovement(
            id=new_id("MOV"), tipo="SAIDA", ref_id=novo_supply.id, supply_nome=novo_supply.nome,
            descricao=f"SubstituiÃ§Ã£o de perifÃ©rico na alocaÃ§Ã£o {aid}: {novo_supply.nome} x{qty}",
            quantidade=-qty, colaborador=al.colaborador, ativo_id=al.ativo_id, motivo="Troca por defeito",
        ))

        if novo_supply.id == antigo_supply_id:
            item.supply_nome = novo_supply.nome
        else:
            item.quantidade -= qty
            destino = db.session.execute(
                db.select(AllocationItem).filter_by(allocation_id=aid, supply_id=novo_supply.id)
            ).scalar_one_or_none()
            if destino:
                destino.quantidade = (destino.quantidade or 0) + qty
                destino.supply_nome = novo_supply.nome
            else:
                db.session.add(AllocationItem(
                    id=new_id("AI"), allocation_id=aid,
                    supply_id=novo_supply.id, supply_nome=novo_supply.nome, quantidade=qty,
                ))
            if item.quantidade <= 0:
                db.session.delete(item)

        ativo_ref = asset.hostname if asset else (al.ativo_nome or al.ativo_id)
        audit("TROCA_PERIFERICO","alocacoes",aid,
              f"{ativo_ref}: {antigo_nome} x{qty} substituÃ­do por {novo_supply.nome} ({motivo})")
        db.session.commit()
        return jsonify(al.to_dict(include_items=True))
    except Exception:
        db.session.rollback()
        raise


@app.route("/api/allocations/<aid>/termo.pdf")
@api_auth
def gerar_termo(aid):
    al = db.get_or_404(Allocation, aid)
    if not PDF_OK:
        return jsonify({"error": "Geração de PDF indisponível. Instale: pip install reportlab"}), 503

    empresa   = _get_setting("empresa", {}) or {}
    # Seleciona template conforme tipo da alocação
    tipo_aloc = (al.tipo or "Responsabilidade")
    if tipo_aloc == "Empréstimo":
        tr_cfg = _get_setting("termo_emprestimo", {}) or {}
        titulo_default = "TERMO DE EMPRÉSTIMO DE EQUIPAMENTO"
        preambulo_default = ("Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\n"
                             "declaro ter recebido em caráter de EMPRÉSTIMO TEMPORÁRIO o equipamento abaixo:")
        clausulas_padrao = [
            "Comprometo-me a:",
            "  1. Utilizar exclusivamente para fins profissionais durante o período de empréstimo;",
            "  2. Zelar pela conservação do equipamento;",
            "  3. Devolver o equipamento na data prevista ou quando solicitado pelo setor de TI;",
            "  4. Comunicar imediatamente ao TI qualquer dano, perda ou furto.",
        ]
    else:
        tr_cfg = _get_setting("termo_recebimento", {}) or {}
        titulo_default = "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO"
        preambulo_default = ("Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\n"
                             "declaro ter recebido os seguintes equipamentos de propriedade da empresa:")
        clausulas_padrao = [
            "Comprometo-me a:",
            "  1. Utilizar exclusivamente para fins profissionais;",
            "  2. Zelar pela conservação de todos os itens;",
            "  3. Comunicar ao TI qualquer dano, perda ou furto;",
            "  4. Devolver os equipamentos ao encerramento do vínculo.",
        ]
    logo_b64  = empresa.get("logo_base64", "") if isinstance(empresa, dict) else ""

    ctx = {"colaborador": al.colaborador, "setor": al.setor, "unidade": al.unidade,
           "ativo": al.ativo_nome, "data": al.data_aloc, "termo": al.termo or aid,
           "empresa": empresa.get("nome", "") if isinstance(empresa, dict) else "",
           "dataDevolucao": al.data_devolucao_prevista or ""}

    titulo    = _render_termo_text(tr_cfg.get("titulo", titulo_default), ctx)
    preambulo = _render_termo_text(tr_cfg.get("preambulo", preambulo_default), ctx)
    clausulas = tr_cfg.get("clausulas", clausulas_padrao)
    rodape_txt= _render_termo_text(tr_cfg.get("rodape", ""), ctx)

    try:
        return _send_allocation_term_pdf(al, aid, empresa, logo_b64, titulo, preambulo, clausulas, rodape_txt, ctx)
    except Exception:
        app.logger.exception("Falha no layout novo do termo; usando gerador legado.")

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
        if (al.tipo or "Responsabilidade") == "Empréstimo" and al.data_devolucao_prevista:
            c.setFont("Helvetica-Bold", 10)
            c.setFillColorRGB(0.8, 0.2, 0.0)
            c.drawString(2*cm, y, f"⚠  Devolução prevista: {al.data_devolucao_prevista}")
            c.setFillColorRGB(0, 0, 0)
            y -= 0.8*cm
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
@api_auth
def get_assinatura_img(aid):
    al = db.get_or_404(Allocation, aid)
    if not al.assinatura_img or not al.assinatura_img.startswith("data:image/png;base64,"):
        return jsonify({"error":"Sem assinatura capturada."}), 404
    raw = base64.b64decode(al.assinatura_img.split(",", 1)[1])
    return Response(raw, mimetype="image/png",
                    headers={"Cache-Control":"private, max-age=3600"})


@app.route("/api/allocations/<aid>/assinatura-ti.png")
@api_auth
def get_assinatura_ti_img(aid):
    al = db.get_or_404(Allocation, aid)
    if not al.assinatura_ti_img or not al.assinatura_ti_img.startswith("data:image/png;base64,"):
        return jsonify({"error":"Sem assinatura TI capturada."}), 404
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


@app.route("/api/allocations/<aid>/sign-link", methods=["POST"])
@requires("Administrador","Técnico TI")
def gerar_link_assinatura(aid):
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo":
        return jsonify({"error":"Alocação encerrada — não é possível gerar link."}), 400
    if al.termo_status == "Assinado":
        return jsonify({"error":"Termo já assinado."}), 400
    token = uuid.uuid4().hex + uuid.uuid4().hex   # 64 chars
    al.sign_token = token
    al.sign_token_expiry = datetime.now() + timedelta(days=7)
    audit("GERAR_LINK_ASSINATURA","alocacoes",aid,f"Link de assinatura gerado para {al.colaborador}")
    db.session.commit()
    url = f"{get_app_base_url()}/assinar/{token}"
    email_enviado = False
    if al.email:
        res = send_email_link_assinatura(al.email, al.colaborador, al.ativo_nome, url)
        email_enviado = res.get("ok", False)
    return jsonify({"url": url, "expiry": al.sign_token_expiry.isoformat(),
                    "emailEnviado": email_enviado})


@app.route("/api/allocations/<aid>/qrcode-termo")
@api_auth
def allocation_qrcode_termo(aid):
    """Gera QR Code PNG do link de assinatura. Cria token automaticamente se ausente/expirado."""
    al = db.get_or_404(Allocation, aid)
    if al.status != "Ativo" or al.termo_status == "Assinado":
        abort(404)
    now = datetime.now()
    if not al.sign_token or (al.sign_token_expiry and al.sign_token_expiry < now):
        al.sign_token = uuid.uuid4().hex + uuid.uuid4().hex
        al.sign_token_expiry = now + timedelta(days=7)
        db.session.commit()
    url = f"{get_app_base_url()}/assinar/{al.sign_token}"
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


@app.route("/api/emprestimos/vencidos")
@api_auth
def emprestimos_vencidos():
    """Retorna alocações do tipo Empréstimo com data de devolução vencida."""
    hoje = str(date.today())
    vencidos = db.session.execute(
        db.select(Allocation).where(
            Allocation.tipo == "Empréstimo",
            Allocation.status == "Ativo",
            Allocation.data_devolucao_prevista.isnot(None),
            Allocation.data_devolucao_prevista < hoje,
        )
    ).scalars().all()
    return jsonify([a.to_dict() for a in vencidos])

