"""Rotas de campanhas de auditoria fisica de ativos."""
from app import _export_route_globals

globals().update(_export_route_globals())


AUDIT_CAMPAIGN_STATUS = {"Aberta", "Encerrada"}
AUDIT_ITEM_STATUS = {"Pendente", "Conferido", "Divergente", "Extra"}


def _campaign_scope_stmt(unidade="", setor=""):
    stmt = db.select(Asset).where(~Asset.status.in_(["Baixado", "Descartado", "Vendido", "Inativo"]))
    if unidade:
        stmt = stmt.where(Asset.unidade == unidade)
    if setor:
        stmt = stmt.where(Asset.setor == setor)
    return stmt.order_by(Asset.unidade, Asset.setor, Asset.hostname)


def _campaign_item_for_asset(campaign_id, asset_id):
    return db.session.execute(
        db.select(AuditCampaignItem).where(
            AuditCampaignItem.campaign_id == campaign_id,
            AuditCampaignItem.asset_id == asset_id,
        )
    ).scalar_one_or_none()


def _extract_asset_identifier(raw):
    value = clean_text(raw, 200).rstrip("/")
    if "/asset/" in value:
        value = value.rsplit("/asset/", 1)[-1].split("?", 1)[0].split("#", 1)[0].strip("/")
    return value


def _find_asset_for_audit(raw_identifier):
    ident = _extract_asset_identifier(raw_identifier)
    if not ident:
        return None
    asset = db.session.get(Asset, ident)
    if asset:
        return asset
    return db.session.execute(
        db.select(Asset).where(db.or_(
            Asset.patrimonio == ident,
            Asset.service_tag == ident,
            Asset.hostname == ident,
        ))
    ).scalar_one_or_none()


def _check_campaign_item(item, payload, user_label):
    was_extra = item.status == "Extra"
    local = clean_text(payload.get("local") or payload.get("observedLocal") or item.expected_unidade, 120)
    responsavel = clean_text(
        payload.get("responsavel") or payload.get("observedResponsavel") or item.expected_colaborador,
        120,
    )
    observacao = clean_text(payload.get("observacao") or "", 500)
    divergencias = []
    if local and item.expected_unidade and local.casefold() != item.expected_unidade.casefold():
        divergencias.append(f"Local esperado: {item.expected_unidade}; informado: {local}")
    if responsavel and item.expected_colaborador and responsavel.casefold() != item.expected_colaborador.casefold():
        divergencias.append(f"Responsável esperado: {item.expected_colaborador}; informado: {responsavel}")

    forced_status = clean_text(payload.get("status") or "", 20)
    if forced_status and forced_status not in AUDIT_ITEM_STATUS:
        return None, "Status inválido."

    item.observed_local = local
    item.observed_responsavel = responsavel
    item.observacao = observacao
    if was_extra:
        divergencias.insert(0, "Ativo fora do escopo original da campanha.")
    item.divergencia = "; ".join(divergencias)
    item.status = forced_status or ("Extra" if was_extra else ("Divergente" if divergencias else "Conferido"))
    item.auditado_por = user_label
    item.auditado_em = datetime.now()
    return item, None


def _check_campaign_item_v2(item, payload, user_label):
    was_extra = item.status == "Extra"
    unidade = clean_text(
        payload.get("unidade") or payload.get("observedUnidade") or payload.get("local") or item.expected_unidade,
        80,
    )
    setor = clean_text(payload.get("setor") or payload.get("observedSetor") or item.expected_setor, 80)
    local = clean_text(payload.get("localFisico") or payload.get("observedLocal") or "", 120)
    responsavel = clean_text(
        payload.get("responsavel") or payload.get("observedResponsavel") or item.expected_colaborador,
        120,
    )
    observacao = clean_text(payload.get("observacao") or "", 500)
    divergencias = []
    if unidade and item.expected_unidade and unidade.casefold() != item.expected_unidade.casefold():
        divergencias.append(f"Unidade esperada: {item.expected_unidade}; informada: {unidade}")
    if setor and item.expected_setor and setor.casefold() != item.expected_setor.casefold():
        divergencias.append(f"Setor esperado: {item.expected_setor}; informado: {setor}")
    if responsavel and item.expected_colaborador and responsavel.casefold() != item.expected_colaborador.casefold():
        divergencias.append(f"Responsavel esperado: {item.expected_colaborador}; informado: {responsavel}")

    forced_status = clean_text(payload.get("status") or "", 20)
    if forced_status and forced_status not in AUDIT_ITEM_STATUS:
        return None, "Status invalido."
    if forced_status == "Conferido" and divergencias:
        return None, "Nao e possivel marcar como Conferido quando ha divergencia. Corrija os dados observados ou use Divergente."

    item.observed_unidade = unidade
    item.observed_setor = setor
    item.observed_local = local
    item.observed_responsavel = responsavel
    item.observacao = observacao
    if was_extra:
        divergencias.insert(0, "Ativo fora do escopo original da campanha.")
    item.divergencia = "; ".join(divergencias)
    item.status = forced_status or ("Extra" if was_extra else ("Divergente" if divergencias else "Conferido"))
    item.auditado_por = user_label
    item.auditado_em = datetime.now()
    return item, None


@app.route("/api/audit-campaigns", methods=["GET"])
@api_auth
def list_audit_campaigns():
    status = clean_text(request.args.get("status", ""), 20)
    stmt = db.select(AuditCampaign).order_by(AuditCampaign.criado_em.desc())
    if status:
        stmt = stmt.where(AuditCampaign.status == status)
    return jsonify([c.to_dict() for c in db.session.execute(stmt).scalars().all()])


@app.route("/api/audit-campaigns", methods=["POST"])
@requires("Administrador", "Técnico TI")
def create_audit_campaign():
    d = json_payload()
    nome = clean_text(d.get("nome"), 120)
    if not nome:
        return jsonify({"error": "Nome da campanha é obrigatório."}), 400
    unidade = clean_text(d.get("unidade"), 80)
    setor = clean_text(d.get("setor"), 80)
    assets = db.session.execute(_campaign_scope_stmt(unidade, setor)).scalars().all()
    if not assets:
        return jsonify({"error": "Nenhum ativo encontrado para o escopo informado."}), 400
    c = AuditCampaign(
        id=new_id("AC"),
        nome=nome,
        unidade=unidade,
        setor=setor,
        criado_por=current_user.username,
        observacao=clean_text(d.get("observacao"), 1000),
    )
    db.session.add(c)
    for a in assets:
        db.session.add(AuditCampaignItem(
            id=new_id("ACI"),
            campaign_id=c.id,
            asset_id=a.id,
            asset_nome=a.hostname or a.id,
            patrimonio=a.patrimonio,
            service_tag=a.service_tag,
            expected_unidade=a.unidade,
            expected_setor=a.setor,
            expected_colaborador=a.colaborador,
        ))
    audit("CRIAR_CAMPANHA_AUDITORIA", "auditorias", c.id, f"Campanha {nome} criada com {len(assets)} ativo(s)")
    db.session.commit()
    return jsonify(c.to_dict(include_items=True)), 201


@app.route("/api/audit-campaigns/<cid>", methods=["GET"])
@api_auth
def get_audit_campaign(cid):
    c = db.get_or_404(AuditCampaign, cid)
    return jsonify(c.to_dict(include_items=True))


@app.route("/api/audit-campaigns/<cid>", methods=["PUT"])
@requires("Administrador", "Técnico TI")
def update_audit_campaign(cid):
    c = db.get_or_404(AuditCampaign, cid)
    d = json_payload()
    if "status" in d:
        status = clean_text(d.get("status"), 20)
        if status not in AUDIT_CAMPAIGN_STATUS:
            return jsonify({"error": "Status inválido."}), 400
        pendentes = sum(1 for i in c.items if i.status == "Pendente")
        if status == "Encerrada" and pendentes and not d.get("confirmarPendencias"):
            return jsonify({"error": f"A campanha ainda possui {pendentes} item(ns) pendente(s). Confirme o encerramento com pendencias."}), 400
        c.status = status
        c.data_fim = str(date.today()) if status == "Encerrada" else None
    for key, attr, max_len in [("nome", "nome", 120), ("observacao", "observacao", 1000)]:
        if key in d:
            setattr(c, attr, clean_text(d.get(key), max_len))
    audit("EDITAR_CAMPANHA_AUDITORIA", "auditorias", c.id, f"Campanha {c.nome} atualizada")
    db.session.commit()
    return jsonify(c.to_dict(include_items=True))


@app.route("/api/audit-campaigns/<cid>/items/<item_id>/check", methods=["POST"])
@requires("Administrador", "Técnico TI")
def check_audit_campaign_item(cid, item_id):
    c = db.get_or_404(AuditCampaign, cid)
    if c.status != "Aberta":
        return jsonify({"error": "Campanha encerrada."}), 400
    item = db.get_or_404(AuditCampaignItem, item_id)
    if item.campaign_id != cid:
        return jsonify({"error": "Item não pertence a esta campanha."}), 400
    item, error = _check_campaign_item_v2(item, json_payload(), current_user.username)
    if error:
        return jsonify({"error": error}), 400
    audit("CONFERIR_ATIVO_CAMPANHA", "auditorias", item.asset_id or item.id,
          f"{c.nome}: {item.asset_nome} marcado como {item.status}")
    db.session.commit()
    return jsonify(c.to_dict(include_items=True))


@app.route("/api/audit-campaigns/<cid>/assets/<aid>/check", methods=["POST"])
@requires("Administrador", "Técnico TI")
def check_audit_campaign_asset(cid, aid):
    c = db.get_or_404(AuditCampaign, cid)
    if c.status != "Aberta":
        return jsonify({"error": "Campanha encerrada."}), 400
    a = _find_asset_for_audit(aid)
    if not a:
        return jsonify({"error": "Ativo nao encontrado por ID, URL, patrimonio, Service Tag ou hostname."}), 404
    item = _campaign_item_for_asset(cid, a.id)
    if not item:
        item = AuditCampaignItem(
            id=new_id("ACI"),
            campaign_id=cid,
            asset_id=a.id,
            asset_nome=a.hostname or a.id,
            patrimonio=a.patrimonio,
            service_tag=a.service_tag,
            expected_unidade=a.unidade,
            expected_setor=a.setor,
            expected_colaborador=a.colaborador,
            status="Extra",
        )
        db.session.add(item)
    item, error = _check_campaign_item_v2(item, json_payload(), current_user.username)
    if error:
        return jsonify({"error": error}), 400
    audit("CONFERIR_ATIVO_CAMPANHA", "auditorias", a.id,
          f"{c.nome}: {a.hostname} marcado como {item.status}")
    db.session.commit()
    return jsonify(c.to_dict(include_items=True))
