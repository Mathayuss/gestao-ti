"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

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

    try:
        c.status="Inativo"; c.data_desligamento=str(date.today())
        audit("DESLIGAMENTO","colaboradores",cid,f"Ativos:{ativos_dev} Periféricos:{perifs_dev}")

        dev_id = new_id("DEV")
        dev = Devolucao(
            id=dev_id, colaborador_id=cid, colaborador=c.nome,
            setor=c.setor or "", unidade=c.unidade or "",
            data_devolucao=str(date.today()),
            status="Pendente",
            laudo_status="Aguardando Laudo",
            ativos_devolvidos=json.dumps(ativos_dev, ensure_ascii=False),
            perifericos_devolvidos=json.dumps(perifs_dev, ensure_ascii=False),
        )
        db.session.add(dev)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return jsonify({"ok":True,"colaborador":c.nome,"colaboradorId":cid,
                    "setor":c.setor or "—","unidade":c.unidade or "—",
                    "matricula":c.matricula or "—",
                    "ativosDevolvidos":ativos_dev,
                    "perifericosDevolvidos":perifs_dev,"dataDesligamento":str(date.today()),
                    "devolucaoId": dev_id,
                    "laudoStatus": "Aguardando Laudo",
                    "proximoPasso": "Registre o laudo técnico em POST /api/devolucoes/{}/laudo".format(dev_id)})


@app.route("/api/colaboradores/<cid>/termo-devolucao.pdf")
@api_auth
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

