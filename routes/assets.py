"""Rotas Flask extraidas do app.py.

Este modulo usa uma ponte temporaria para acessar modelos, helpers e extensoes
definidos em app.py. Em uma proxima etapa, esses itens podem migrar para
pacotes dedicados como models, services e extensions.
"""
from app import _export_route_globals

globals().update(_export_route_globals())

@app.route("/")
@login_required
def index():
    return render_template("index.html",
        app_base_url=app.config["APP_BASE_URL"],
        build_version=app.config.get("BUILD_VERSION", "1.0"),
    )


@app.route("/asset/<aid>")
def asset_public(aid):
    a = db.session.get(Asset, aid)
    if not a: return "Ativo não encontrado", 404
    return render_template("asset_public.html", asset=a)


@app.route("/api/assets", methods=["GET"])
@api_auth
def get_assets():
    q   = request.args.get("q","").lower()
    cat = request.args.get("categoria","")
    stmt = db.select(Asset)
    if q:
        stmt = stmt.where(db.or_(Asset.hostname.ilike(f"%{q}%"),
                                  Asset.colaborador.ilike(f"%{q}%"),
                                  Asset.service_tag.ilike(f"%{q}%"),
                                  Asset.fabricante.ilike(f"%{q}%")))
    if cat:
        stmt = stmt.where(Asset.categoria == cat)
    return jsonify([a.to_dict() for a in db.session.execute(stmt).scalars().all()])


@app.route("/api/assets/proximo-patrimonio", methods=["GET"])
@api_auth
def get_proximo_patrimonio():
    return jsonify({"patrimonio": proximo_patrimonio()})


@app.route("/api/assets/lote", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_asset_lote():
    d = request.get_json() or {}
    try:
        quantidade = int(d.get("quantidade", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Quantidade inválida para entrada em lote."}), 400
    if quantidade < 1 or quantidade > 100:
        return jsonify({"error": "Quantidade deve estar entre 1 e 100."}), 400
    criados = []
    for _ in range(quantidade):
        pat = proximo_patrimonio()
        payload = dict(d)
        payload["patrimonio"] = pat
        if not clean_text(payload.get("hostname")):
            payload["hostname"] = f"{clean_text(payload.get('categoria'), 20) or 'ATIVO'}-{pat}"
        errors = validate_asset_payload(payload)
        if errors:
            db.session.rollback()
            return jsonify({"error": "Validação falhou", "details": errors}), 400
        a = Asset(
            id=new_id("A"),
            hostname=clean_text(payload.get("hostname"), 80),
            ip=clean_text(d.get("ip", "DHCP"), 40) or "DHCP",
            mac=clean_text(d.get("mac"), 20),
            service_tag=clean_text(d.get("serviceTag"), 40),
            os=clean_text(d.get("os"), 80),
            fabricante=clean_text(d.get("fabricante"), 60),
            modelo=clean_text(d.get("modelo"), 80),
            patrimonio=pat,
            nf=clean_text(d.get("nf"), 40),
            categoria=clean_text(d.get("categoria"), 40),
            status="Disponível",
            garantia=clean_text(d.get("garantia"), 10) or None,
        )
        db.session.add(a)
        audit("CRIAR", "ativos", a.id, f"Ativo {a.fabricante} {a.modelo} cadastrado em lote — {pat}")
        criados.append(a)
    db.session.commit()
    return jsonify([a.to_dict() for a in criados]), 201


@app.route("/api/assets", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_asset():
    d = request.get_json() or {}
    # Auto-gera patrimônio se não informado
    if not clean_text(d.get("patrimonio")):
        d = dict(d)
        d["patrimonio"] = proximo_patrimonio()
    if not clean_text(d.get("hostname")):
        d = dict(d)
        d["hostname"] = f"{clean_text(d.get('categoria'), 20) or 'ATIVO'}-{d['patrimonio']}"
    errors = validate_asset_payload(d)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    a = Asset(id=new_id("A"),
              hostname=clean_text(d.get("hostname"), 80), ip=clean_text(d.get("ip","DHCP"), 40) or "DHCP",
              mac=clean_text(d.get("mac"), 20), service_tag=clean_text(d.get("serviceTag"), 40),
              os=clean_text(d.get("os"), 80), fabricante=clean_text(d.get("fabricante"), 60),
              modelo=clean_text(d.get("modelo"), 80), patrimonio=clean_text(d.get("patrimonio"), 40),
              nf=clean_text(d.get("nf"), 40), categoria=clean_text(d.get("categoria"), 40),
              status=clean_text(d.get("status","Disponível"), 30) or "Disponível",
              colaborador=clean_text(d.get("colaborador"), 120),
              setor=clean_text(d.get("setor"), 80), unidade=clean_text(d.get("unidade"), 80),
              garantia=clean_text(d.get("garantia"), 10) or None)
    db.session.add(a)
    audit("CRIAR", "ativos", a.id, f"Ativo {a.hostname} cadastrado — patrimônio {a.patrimonio}")
    db.session.commit()
    return jsonify(a.to_dict()), 201


@app.route("/api/assets/<aid>", methods=["GET"])
@api_auth
def get_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = a.to_dict()
    d["incidentes"]    = [i.to_dict() for i in db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalars().all()]
    d["alocacoes"]     = [al.to_dict() for al in db.session.execute(db.select(Allocation).filter_by(ativo_id=aid)).scalars().all()]
    d["auditLogs"]     = [l.to_dict() for l in db.session.execute(db.select(AuditLog).filter_by(ref_id=aid).order_by(AuditLog.data.desc()).limit(20)).scalars().all()]
    return jsonify(d)


@app.route("/api/assets/<aid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_asset(aid):
    a = db.get_or_404(Asset, aid)
    d = request.get_json() or {}
    errors = validate_asset_payload(d, partial=True, exclude_id=aid)
    if errors:
        return jsonify({"error":"Validação do ativo falhou", "details": errors}), 400
    for k, v, max_len in [("hostname","hostname",80),("ip","ip",40),("mac","mac",20),("serviceTag","service_tag",40),
                  ("os","os",80),("fabricante","fabricante",60),("modelo","modelo",80),
                  ("patrimonio","patrimonio",40),("nf","nf",40),("categoria","categoria",40),
                  ("status","status",30),("colaborador","colaborador",120),
                  ("setor","setor",80),("unidade","unidade",80),("garantia","garantia",10)]:
        if k in d: setattr(a, v, clean_text(d[k], max_len))
    audit("EDITAR", "ativos", aid, f"Ativo {a.hostname} editado")
    db.session.commit()
    return jsonify(a.to_dict())


@app.route("/api/assets/<aid>/upload", methods=["POST"])
@requires("Administrador","Técnico TI")
def upload_asset_attachment(aid):
    a = db.get_or_404(Asset, aid)
    att, error = _create_attachment_record(
        "asset",
        aid,
        request.files.get("file"),
        request.form.get("category") or "Documento",
        request.form.get("description") or "",
    )
    if error:
        message, status = error
        return jsonify({"error": message}), status
    audit("ANEXO_UPLOAD", "ativos", aid, f"Anexo {att.original_name} adicionado ao ativo {a.hostname}")
    db.session.commit()
    return jsonify({"ok": True, "filename": att.original_name, "attachment": att.to_dict()}), 201


@app.route("/api/assets/<aid>", methods=["DELETE"])
@requires("Administrador")
def delete_asset(aid):
    """Baixa lógica — não remove fisicamente se houver histórico."""
    a = db.get_or_404(Asset, aid)
    has_allocs  = db.session.execute(db.select(Allocation).filter_by(ativo_id=aid)).scalar_one_or_none()
    has_inc     = db.session.execute(db.select(Incident).filter_by(ref_id=aid)).scalar_one_or_none()
    if has_allocs or has_inc:
        a.status = "Baixado"
        audit("BAIXA", "ativos", aid, f"Ativo {a.hostname} marcado como Baixado (histórico preservado)")
        db.session.commit()
        return jsonify({"ok":True, "msg":"Ativo marcado como Baixado (histórico preservado)."})
    db.session.delete(a)
    audit("EXCLUIR", "ativos", aid, f"Ativo {a.hostname} excluído")
    db.session.commit()
    return jsonify({"ok":True, "msg":"Ativo excluído."})


@app.route("/api/assets/<aid>/history")
@api_auth
def get_asset_history(aid):
    """Linha do tempo unificada do ativo: cadastro, edições, alocações,
    manutenções, incidentes, auditorias QR e movimentos de insumo."""
    a = db.get_or_404(Asset, aid)
    events = []

    # ── Mapa auxiliar ───────────────────────────────────────────────────
    _ICONE = {
        "CRIAR":"plus","EDITAR":"edit","BAIXA":"download","EXCLUIR":"trash",
        "AUDITORIA":"mapPin","AUDITORIA_QR_PUBLICA":"smartphone",
        "ALOCAR":"link","ENCERRAR_ALOCACAO":"undo","ASSINAR_TERMO":"check",
        "MANUTENCAO_ABERTA":"wrench","MANUTENCAO_ENCERRADA":"flag",
        "MANUTENCAO_PECA":"package","MANUTENCAO_ATUALIZADA":"clipboard",
        "INCIDENTE":"warning","SAIDA":"package","DEVOLUCAO":"package",
    }
    _COR = {
        "CRIAR":"green","EDITAR":"blue","BAIXA":"red","EXCLUIR":"red",
        "AUDITORIA":"purple","AUDITORIA_QR_PUBLICA":"purple",
        "ALOCAR":"blue","ENCERRAR_ALOCACAO":"green","ASSINAR_TERMO":"green",
        "MANUTENCAO_ABERTA":"amber","MANUTENCAO_ENCERRADA":"green",
        "MANUTENCAO_PECA":"gray","MANUTENCAO_ATUALIZADA":"gray",
        "INCIDENTE":"red","SAIDA":"gray","DEVOLUCAO":"gray",
    }

    def _ev(tipo, acao, descricao, usuario, data_iso, extra=None):
        return {"tipo":tipo,"acao":acao,"descricao":descricao,"usuario":usuario or "sistema",
                "data":data_iso,"icone":_ICONE.get(acao,"clipboard"),"cor":_COR.get(acao,"gray"),
                "extra":extra or {}}

    # 1. Audit logs diretos do ativo (exclui os que já vêm de dados estruturados)
    _skip_acoes = {"ALOCAR","MANUTENCAO_ABERTA","MANUTENCAO_ENCERRADA","INCIDENTE",
                   "MANUTENCAO_PECA","MANUTENCAO_PECA_REMOVIDA","MANUTENCAO_ATUALIZADA"}
    for log in db.session.execute(
            db.select(AuditLog).where(AuditLog.ref_id == aid)
            .order_by(AuditLog.data)).scalars().all():
        if log.acao in _skip_acoes:
            continue
        events.append(_ev("auditoria", log.acao, log.detalhe or log.acao,
                          log.usuario, log.data.isoformat() if log.data else None))

    # 2. Alocações (estruturado — tem dados de termo e status)
    for al in db.session.execute(
            db.select(Allocation).where(Allocation.ativo_id == aid)).scalars().all():
        events.append(_ev("alocacao","ALOCAR",
                          f"Alocado para {al.colaborador} — {al.setor} / {al.unidade}",
                          al.colaborador,
                          (al.data_aloc or "") + "T08:00:00" if al.data_aloc else None,
                          {"alocacaoId":al.id,"termo":al.termo,"termoStatus":al.termo_status,
                           "motivo":al.motivo,"email":al.email}))
        if al.termo_status == "Assinado" and al.data_assinatura:
            events.append(_ev("alocacao","ASSINAR_TERMO",
                              f"Termo {al.termo} assinado digitalmente",
                              al.colaborador,
                              al.data_assinatura.isoformat()))
        if al.data_encerramento:
            events.append(_ev("devolucao","ENCERRAR_ALOCACAO",
                              f"Devolução de {al.colaborador}",
                              al.colaborador,
                              al.data_encerramento + "T17:00:00"))

    # 3. Ordens de manutenção (aberta + encerramento + peças)
    for m in db.session.execute(
            db.select(MaintenanceOrder).where(MaintenanceOrder.asset_id == aid)).scalars().all():
        events.append(_ev("manutencao","MANUTENCAO_ABERTA",
                          f"OS {m.id}: {m.tipo} — {(m.descricao_defeito or '')[:80]}",
                          m.tecnico,
                          (m.data_abertura or "") + "T08:00:00" if m.data_abertura else None,
                          {"osId":m.id,"tipo":m.tipo,"status":m.status}))
        for p in m.parts:
            events.append(_ev("manutencao","MANUTENCAO_PECA",
                              f"Peça: {p.supply_nome} × {p.quantidade} — {p.custo_unitario:.2f}/un",
                              m.tecnico,
                              (m.data_abertura or "") + "T09:00:00" if m.data_abertura else None))
        if m.data_conclusao:
            cor_enc = "green" if m.status == "Concluída" else ("red" if m.status == "Sem reparo" else "gray")
            ic_enc  = "check" if m.status == "Concluída" else ("x" if m.status == "Sem reparo" else "square")
            events.append(_ev("manutencao","MANUTENCAO_ENCERRADA",
                              f"OS {m.id} encerrada: {m.status}"
                              + (f" · custo {m.custo_total:.2f}" if m.custo_total else ""),
                              m.tecnico,
                              m.data_conclusao + "T17:00:00",
                              {"osId":m.id,"status":m.status,"custoTotal":m.custo_total,
                               "icone":ic_enc,"cor":cor_enc}))

    # 4. Incidentes
    for inc in db.session.execute(
            db.select(Incident).where(Incident.ref_id == aid)).scalars().all():
        events.append(_ev("incidente","INCIDENTE",
                          f"{inc.tipo}: {(inc.descricao or '')[:80]}",
                          "sistema",
                          inc.data.isoformat() if inc.data else None,
                          {"incidenteId":inc.id,"status":inc.status}))

    # 5. Movimentos de insumo vinculados a este ativo
    for mov in db.session.execute(
            db.select(SupplyMovement).where(SupplyMovement.ativo_id == aid)).scalars().all():
        events.append(_ev("insumo", mov.tipo,
                          mov.descricao or f"{mov.tipo}: {mov.supply_nome}",
                          mov.colaborador,
                          mov.data.isoformat() if mov.data else None))

    events.sort(key=lambda e: e.get("data") or "")
    return jsonify({"asset": a.to_dict(), "totalEventos": len(events), "eventos": events})


@app.route("/api/assets/<aid>/qrcode")
@api_auth
def asset_qrcode(aid):
    base = app.config["APP_BASE_URL"]
    url  = f"{base}/asset/{aid}"
    if QR_OK:
        img = qrcode.make(url); buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
        return send_file(buf, mimetype="image/png")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="white"/><text x="60" y="60" text-anchor="middle" font-size="10" fill="#333">QR:{aid}</text></svg>'
    return svg, 200, {"Content-Type":"image/svg+xml"}


@app.route("/api/public/assets/<aid>/audit", methods=["POST"])
def public_asset_audit(aid):
    ip = request.remote_addr or "unknown"
    if not _check_rate_limit(ip, bucket="qr_public_audit"):
        return jsonify({"error": "Muitas requisições. Aguarde um momento."}), 429
    a = db.session.get(Asset, aid)
    if not a:
        return jsonify({"error":"Ativo não encontrado"}), 404
    d = request.get_json(silent=True) or {}
    local = clean_text(d.get("local") or a.unidade or "Não informado", 120)
    responsavel = clean_text(d.get("responsavel") or a.colaborador or "Não informado", 120)
    public_audit("AUDITORIA_QR_PUBLICA", "ativos", a.id, f"Local confirmado: {local}; responsável informado: {responsavel}")
    db.session.commit()
    return jsonify({"ok": True, "assetId": a.id, "status": a.status, "local": local})


@app.route("/api/audit-asset", methods=["POST"])
@requires("Administrador","Técnico TI")
def audit_asset_route():
    d = request.get_json()
    a = db.session.get(Asset, d.get("assetId",""))
    if not a: return jsonify({"error":"Ativo não encontrado"}), 404
    audit("AUDITORIA","ativos",a.id,f"Auditado em {d.get('local',a.unidade)} por {current_user.username}")
    db.session.commit()
    return jsonify({"ok":True,"hostname":a.hostname,"status":a.status,"colaborador":a.colaborador})
