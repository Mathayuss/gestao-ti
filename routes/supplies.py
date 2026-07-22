"""Rotas de insumos, estoque e movimentacoes."""
from flask import jsonify, request

from app import (
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
from models import Asset, Colaborador, Supply, SupplyMovement
from routes.blueprint import bp

@bp.route("/api/supplies", methods=["GET"])
@api_auth
def get_supplies():
    q = request.args.get("q","").lower()
    stmt = db.select(Supply)
    if q: stmt = stmt.where(db.or_(Supply.nome.ilike(f"%{q}%"), Supply.categoria.ilike(f"%{q}%")))
    return jsonify([s.to_dict() for s in db.session.execute(stmt).scalars().all()])


@bp.route("/api/supplies", methods=["POST"])
@requires("Administrador","Técnico TI")
def create_supply():
    d = request.get_json() or {}
    if not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do item é obrigatório."}), 400
    s = Supply(id=new_id("S"), nome=clean_text(d.get("nome"), 120), categoria=clean_text(d.get("categoria"), 40),
               unidade=clean_text(d.get("unidade"), 80), estoque=parse_int(d.get("estoque",0), minimum=0),
               minimo=parse_int(d.get("minimo",0), minimum=0), preco=parse_float(d.get("preco",0), minimum=0))
    db.session.add(s)
    m = SupplyMovement(id=new_id("MOV"), tipo="ENTRADA", ref_id=s.id, supply_nome=s.nome,
                       descricao=f"Cadastro inicial: {s.nome}", quantidade=s.estoque, motivo="Cadastro")
    db.session.add(m)
    audit("CRIAR", "insumos", s.id, f"Item {s.nome} cadastrado")
    db.session.commit()
    return jsonify(s.to_dict()), 201


@bp.route("/api/supplies/<sid>", methods=["PUT"])
@requires("Administrador","Técnico TI")
def update_supply(sid):
    s = db.get_or_404(Supply, sid)
    d = request.get_json() or {}
    if "nome" in d and not clean_text(d.get("nome")):
        return jsonify({"error":"Nome do item é obrigatório."}), 400
    s.nome = clean_text(d.get("nome", s.nome), 120); s.categoria = clean_text(d.get("categoria", s.categoria), 40)
    s.unidade = clean_text(d.get("unidade", s.unidade), 80); s.minimo = parse_int(d.get("minimo", s.minimo), minimum=0)
    s.preco = parse_float(d.get("preco", s.preco), minimum=0)
    audit("EDITAR", "insumos", sid, f"Item {s.nome} editado")
    db.session.commit()
    return jsonify(s.to_dict())


@bp.route("/api/supplies/<sid>/entrada", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_entrada(sid):
    d = request.get_json() or {}
    qty = parse_int(d.get("quantidade",1), default=1, minimum=1)
    s = get_supply_for_update(sid)
    if not s:
        return jsonify({"error":"Item não encontrado no estoque."}), 404
    s.estoque += qty
    m = SupplyMovement(id=new_id("MOV"), tipo="ENTRADA", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: +{qty}", quantidade=qty, motivo=d.get("motivo","Entrada"))
    db.session.add(m)
    audit("ENTRADA", "insumos", sid, f"{s.nome}: +{qty}")
    db.session.commit()
    return jsonify(s.to_dict())


@bp.route("/api/supplies/<sid>/saida", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_saida(sid):
    d = request.get_json() or {}
    colab   = clean_text(d.get("colaborador"), 120)
    ativo_id= clean_text(d.get("ativoId"), 16)
    motivo  = clean_text(d.get("motivo") or "Saída", 80)
    qty     = parse_int(d.get("quantidade",1), default=1, minimum=1)

    if not colab and not ativo_id:
        return jsonify({"error":"Vincule a saída a um colaborador ou ativo de TI."}), 400
    s = get_supply_for_update(sid)
    if not s:
        return jsonify({"error":"Item não encontrado no estoque."}), 404
    if s.estoque < qty:
        return jsonify({"error":f"Estoque insuficiente ({s.estoque} disponível)."}), 400
    if colab and not db.session.execute(db.select(Colaborador).filter_by(nome=colab)).scalar_one_or_none():
        return jsonify({"error":f"Colaborador '{colab}' não encontrado."}), 404
    if ativo_id and not db.session.get(Asset, ativo_id):
        return jsonify({"error":f"Ativo '{ativo_id}' não encontrado."}), 404

    s.estoque -= qty
    dest = f"colaborador {colab}" if colab else f"ativo {ativo_id}"
    m = SupplyMovement(id=new_id("MOV"), tipo="SAIDA", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: -{qty} → {dest}", quantidade=-qty,
                       colaborador=colab, ativo_id=ativo_id, motivo=motivo)
    db.session.add(m)
    audit("SAIDA", "insumos", sid, f"{s.nome}: -{qty} → {dest}")
    db.session.commit()
    return jsonify(s.to_dict())


@bp.route("/api/supplies/<sid>/devolucao", methods=["POST"])
@requires("Administrador","Técnico TI")
def supply_devolucao(sid):
    d = request.get_json() or {}
    colab = clean_text(d.get("colaborador"), 120)
    qty   = parse_int(d.get("quantidade",1), default=1, minimum=1)
    s = get_supply_for_update(sid)
    if not s:
        return jsonify({"error":"Item não encontrado no estoque."}), 404
    s.estoque += qty
    m = SupplyMovement(id=new_id("MOV"), tipo="DEVOLUCAO", ref_id=sid, supply_nome=s.nome,
                       descricao=f"{s.nome}: +{qty} ← {colab or 'N/I'}", quantidade=qty, colaborador=colab)
    db.session.add(m)
    audit("DEVOLUCAO", "insumos", sid, f"{s.nome}: +{qty} ← {colab}")
    db.session.commit()
    return jsonify(s.to_dict())


@bp.route("/api/supplies/kit-admissao", methods=["POST"])
@requires("Administrador","Técnico TI")
def kit_admissao():
    d = request.get_json() or {}
    colab = clean_text(d.get("colaborador",""), 120)
    if not colab: return jsonify({"error":"Colaborador obrigatório."}), 400
    items = d.get("items",[])
    # Valida estoque de todos antes de mover qualquer um
    erros = []
    requested = {}
    for item in items:
        supply_id = clean_text(item.get("id"), 16)
        qty = parse_int(item.get("quantidade",1), default=1, minimum=1)
        if supply_id:
            requested[supply_id] = requested.get(supply_id, 0) + qty
        else:
            erros.append("Item sem identificação.")
    locked_supplies = {
        s.id: s for s in db.session.execute(
            db.select(Supply)
            .where(Supply.id.in_(sorted(requested)))
            .with_for_update()
        ).scalars().all()
    } if requested else {}
    for supply_id, qty in requested.items():
        s = locked_supplies.get(supply_id)
        if not s: erros.append(f"Item '{supply_id}' não encontrado")
        elif s.estoque < qty: erros.append(f"'{s.nome}': estoque insuficiente ({s.estoque} / {qty} pedido)")
    if erros: return jsonify({"error":"Itens com problema:\n"+"\n".join(erros)}), 400

    resultado = []
    for supply_id, qty in requested.items():
        s = locked_supplies[supply_id]
        s.estoque -= qty
        m = SupplyMovement(id=new_id("MOV"), tipo="SAIDA", ref_id=s.id, supply_nome=s.nome,
                           descricao=f"Kit admissão — {colab}: {s.nome} -{qty}", quantidade=-qty,
                           colaborador=colab, motivo="Kit Admissão")
        db.session.add(m)
        resultado.append({"id":s.id,"nome":s.nome,"retirado":qty,"saldo":s.estoque})
    audit("KIT_ADMISSAO", "insumos", "", f"Kit para {colab}: {len(resultado)} itens")
    db.session.commit()
    return jsonify({"ok":True,"resultado":resultado})
