"""Rotas de incidentes e manutencoes."""
from datetime import date

from flask import jsonify, request

from app import (
    MANUT_ENCERRA,
    MANUT_STATUS,
    MANUT_TIPO,
    api_auth,
    audit,
    clean_text,
    get_supply_for_update,
    new_id,
    parse_float,
    parse_int,
    requires,
)
from extensions import db
from models import (
    ASSET_STATUS_VALID,
    Asset,
    Incident,
    MaintenanceOrder,
    MaintenancePart,
    Supply,
    SupplyMovement,
)
from routes.blueprint import bp
from services.attachment_service import create_attachment_record

@bp.route("/api/incidents", methods=["GET"])
@api_auth
def get_incidents():
    ref = request.args.get("refId")
    qry = db.session.execute(db.select(Incident).filter_by(ref_id=ref)).scalars() if ref else Incident.query
    return jsonify([i.to_dict() for i in qry.all()])


@bp.route("/api/incidents", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_incident():
    d = request.get_json() or {}
    ref_id   = clean_text(d.get("refId", ""), 16)
    tipo     = clean_text(d.get("tipo", ""), 40)
    descricao= clean_text(d.get("descricao", ""))
    if not tipo:
        return jsonify({"error": "Tipo do incidente é obrigatório."}), 400
    if not descricao:
        return jsonify({"error": "Descrição do incidente é obrigatória."}), 400
    if ref_id:
        asset_ok  = db.session.get(Asset, ref_id)
        supply_ok = db.session.get(Supply, ref_id)
        if not asset_ok and not supply_ok:
            return jsonify({"error": f"Referência '{ref_id}' não encontrada como Ativo ou Insumo."}), 404
    i = Incident(id=new_id("INC"), ref_id=ref_id, tipo=tipo, descricao=descricao)
    db.session.add(i); audit("INCIDENTE","ativos",i.ref_id,f"{i.tipo}: {i.descricao[:80]}")
    db.session.commit(); return jsonify(i.to_dict()), 201


@bp.route("/api/maintenance", methods=["GET"])
@api_auth
def get_maintenance():
    status   = request.args.get("status", "")
    asset_id = request.args.get("assetId", "")
    stmt = db.select(MaintenanceOrder).order_by(MaintenanceOrder.data_abertura.desc())
    if status:   stmt = stmt.where(MaintenanceOrder.status == status)
    if asset_id: stmt = stmt.where(MaintenanceOrder.asset_id == asset_id)
    return jsonify([m.to_dict() for m in db.session.execute(stmt).scalars().all()])


@bp.route("/api/maintenance", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_maintenance():
    d = request.get_json() or {}
    asset_id = clean_text(d.get("assetId",""), 16)
    if not asset_id:
        return jsonify({"error":"ID do ativo é obrigatório."}), 400
    a = db.session.get(Asset, asset_id)
    if not a:
        return jsonify({"error":"Ativo não encontrado."}), 404
    tipo = clean_text(d.get("tipo","Corretiva"), 40)
    if tipo not in MANUT_TIPO:
        return jsonify({"error":f"Tipo inválido. Use: {', '.join(MANUT_TIPO)}."}), 400
    descricao = clean_text(d.get("descricaoDefeito",""))
    if not descricao:
        return jsonify({"error":"Descrição do defeito é obrigatória."}), 400
    status_anterior = a.status
    a.status = "Manutenção"
    m = MaintenanceOrder(
        id=new_id("MO"), asset_id=asset_id,
        asset_nome=f"{a.hostname} — {a.fabricante} {a.modelo}",
        tipo=tipo, status="Aberta", status_anterior=status_anterior,
        descricao_defeito=descricao,
        tecnico=clean_text(d.get("tecnico",""), 120),
        data_abertura=str(date.today()),
        observacao=clean_text(d.get("observacao",""))
    )
    db.session.add(m)
    audit("MANUTENCAO_ABERTA","manutencao",asset_id,f"OS {m.id}: {tipo} — {descricao[:80]}")
    db.session.commit()
    return jsonify(m.to_dict()), 201


@bp.route("/api/maintenance/<mid>", methods=["GET"])
@api_auth
def get_maintenance_order(mid):
    return jsonify(db.get_or_404(MaintenanceOrder, mid).to_dict(include_parts=True))


@bp.route("/api/maintenance/<mid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_maintenance(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem já encerrada."}), 400
    d = request.get_json() or {}
    if "status" in d:
        if d["status"] not in MANUT_STATUS:
            return jsonify({"error":"Status inválido."}), 400
        m.status = d["status"]
    for k, attr in [("diagnostico","diagnostico"),("tecnico","tecnico"),("observacao","observacao")]:
        if k in d: setattr(m, attr, clean_text(d[k]))
    if "custoTotal" in d: m.custo_total = parse_float(d["custoTotal"], minimum=0)
    audit("MANUTENCAO_ATUALIZADA","manutencao",mid,f"Status: {m.status}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))


@bp.route("/api/maintenance/<mid>/upload", methods=["POST"])
@requires("Administrador","Técnico TI")
def upload_maintenance_attachment(mid):
    db.get_or_404(MaintenanceOrder, mid)
    att, error = create_attachment_record(
        "maintenance",
        mid,
        request.files.get("file"),
        request.form.get("category") or "Documento",
        request.form.get("description") or "",
    )
    if error:
        message, status = error
        return jsonify({"error": message}), status
    audit("ANEXO_UPLOAD", "manutencao", mid, f"Anexo {att.original_name} adicionado à OS {mid}")
    db.session.commit()
    return jsonify({"ok": True, "filename": att.original_name, "attachment": att.to_dict()}), 201


@bp.route("/api/maintenance/<mid>/parts", methods=["POST"])
@requires("Administrador","Técnico TI")
def add_maintenance_part(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem encerrada."}), 400
    d = request.get_json() or {}
    supply_id   = clean_text(d.get("supplyId",""), 16)
    qty         = parse_int(d.get("quantidade",1), default=1, minimum=1)
    custo_unit  = parse_float(d.get("custoUnitario",0), minimum=0)
    if not supply_id:
        return jsonify({"error":"Supply ID é obrigatório."}), 400
    s = get_supply_for_update(supply_id)
    if not s:
        return jsonify({"error":"Item não encontrado no estoque."}), 404
    if s.estoque < qty:
        return jsonify({"error":f"Estoque insuficiente ({s.estoque} disponível)."}), 400
    s.estoque -= qty
    db.session.add(SupplyMovement(
        id=new_id("MOV"), tipo="SAIDA", ref_id=supply_id, supply_nome=s.nome,
        descricao=f"Manutenção {mid}: {s.nome} -{qty}", quantidade=-qty,
        ativo_id=m.asset_id, motivo=f"OS {mid}"))
    p = MaintenancePart(id=new_id("MP"), maintenance_id=mid, supply_id=supply_id,
                        supply_nome=s.nome, quantidade=qty, custo_unitario=custo_unit)
    m.custo_total = round(m.custo_total + qty * custo_unit, 2)
    db.session.add(p)
    audit("MANUTENCAO_PECA","manutencao",mid,f"Peça: {s.nome} x{qty}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True)), 201


@bp.route("/api/maintenance/<mid>/parts/<pid>", methods=["DELETE"])
@requires("Administrador","Técnico TI")
def remove_maintenance_part(mid, pid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem encerrada."}), 400
    p = db.get_or_404(MaintenancePart, pid)
    if p.maintenance_id != mid:
        return jsonify({"error":"Peça não pertence a esta OS."}), 400
    s = get_supply_for_update(p.supply_id)
    if s:
        s.estoque += p.quantidade
        db.session.add(SupplyMovement(
            id=new_id("MOV"), tipo="DEVOLUCAO", ref_id=p.supply_id, supply_nome=p.supply_nome,
            descricao=f"Estorno OS {mid}: {p.supply_nome} +{p.quantidade}",
            quantidade=p.quantidade, ativo_id=m.asset_id, motivo=f"Estorno OS {mid}"))
    m.custo_total = max(0, round(m.custo_total - p.quantidade * p.custo_unitario, 2))
    db.session.delete(p)
    audit("MANUTENCAO_PECA_REMOVIDA","manutencao",mid,f"Peça removida: {p.supply_nome}")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))


@bp.route("/api/maintenance/<mid>/close", methods=["POST"])
@requires("Administrador","Técnico TI")
def close_maintenance(mid):
    m = db.get_or_404(MaintenanceOrder, mid)
    if m.status in MANUT_ENCERRA:
        return jsonify({"error":"Ordem já encerrada."}), 400
    d = request.get_json() or {}
    resultado = clean_text(d.get("resultado","Concluída"), 30)
    if resultado not in MANUT_ENCERRA:
        return jsonify({"error":"Resultado deve ser: Concluída, Sem reparo ou Cancelada."}), 400
    status_ativo = clean_text(d.get("statusAtivo","Disponível"), 30)
    if status_ativo not in ASSET_STATUS_VALID:
        return jsonify({"error":f"Status do ativo inválido: {status_ativo}."}), 400
    m.status = resultado
    if d.get("diagnostico"): m.diagnostico = clean_text(d["diagnostico"])
    m.data_conclusao = str(date.today())
    m.custo_total = parse_float(d.get("custoTotal", m.custo_total), minimum=0)
    a = db.session.get(Asset, m.asset_id)
    if a: a.status = status_ativo
    audit("MANUTENCAO_ENCERRADA","manutencao",mid,
          f"OS encerrada: '{resultado}'. Ativo → '{status_ativo}'")
    db.session.commit()
    return jsonify(m.to_dict(include_parts=True))
