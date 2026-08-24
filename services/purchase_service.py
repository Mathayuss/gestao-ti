"""Regras de negocio do modulo de compras."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlsplit

from extensions import db
from models import Supply, SupplyMovement
from purchase_models import (
    PURCHASE_ITEM_TYPES,
    PURCHASE_STATUS,
    PurchaseApproval,
    PurchaseApprovalRule,
    PurchaseApprovalStep,
    PurchaseItemLink,
    PurchaseProcurementAction,
    PurchaseReceipt,
    PurchaseRequest,
    PurchaseRequestItem,
    PurchaseStatusHistory,
    money,
)


class PurchaseError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def new_id(prefix):
    return f"{prefix}{uuid.uuid4().hex[:10].upper()}"[:20]


def clean_text(value, max_len=None):
    if value is None:
        return ""
    value = str(value).strip()
    if max_len is not None:
        value = value[:max_len]
    return value


def parse_int(value, default=0, minimum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    return result


def parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().casefold() in {"1", "true", "sim", "yes", "on"}


def decimal_money(value, default="0"):
    try:
        result = Decimal(str(value if value not in (None, "") else default))
    except (InvalidOperation, ValueError):
        result = Decimal(default)
    if result < 0:
        result = Decimal("0")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def next_purchase_number():
    year = datetime.now().year
    prefix = f"SC-{year}-"
    count = db.session.execute(
        db.select(db.func.count()).select_from(PurchaseRequest).where(PurchaseRequest.numero.like(f"{prefix}%"))
    ).scalar() or 0
    return f"{prefix}{count + 1:05d}"


def ensure_default_approval_rules():
    if db.session.execute(db.select(PurchaseApprovalRule)).first():
        return
    db.session.add_all([
        PurchaseApprovalRule(
            id=new_id("PR"), nome="Compras de TI ate R$ 10.000", valor_minimo=Decimal("0.01"),
            valor_maximo=Decimal("10000.00"), ordem_aprovacao=1,
            permission_code="compras.aprovar_gerente", perfil_aprovador="Gerente de TI",
            obrigatoria=True, ativa=True, observacao="Regra inicial criada automaticamente.",
        ),
        PurchaseApprovalRule(
            id=new_id("PR"), nome="Gerente para compras acima de R$ 10.000", valor_minimo=Decimal("10000.01"),
            valor_maximo=None, ordem_aprovacao=1,
            permission_code="compras.aprovar_gerente", perfil_aprovador="Gerente de TI",
            obrigatoria=True, ativa=True, observacao="Regra inicial criada automaticamente.",
        ),
        PurchaseApprovalRule(
            id=new_id("PR"), nome="Diretor para compras acima de R$ 10.000", valor_minimo=Decimal("10000.01"),
            valor_maximo=None, ordem_aprovacao=2,
            permission_code="compras.aprovar_diretor", perfil_aprovador="Diretor",
            obrigatoria=True, ativa=True, observacao="Regra inicial criada automaticamente.",
        ),
    ])
    db.session.flush()


def recalculate_purchase(req):
    estimated = Decimal("0")
    approved = Decimal("0")
    real = Decimal("0")
    for item in req.items:
        estimated += Decimal(item.quantidade_solicitada or 0) * decimal_money(item.valor_unitario_estimado)
        qty_approved = item.quantidade_aprovada or 0
        unit_approved = decimal_money(item.valor_unitario_aprovado)
        if not qty_approved:
            qty_approved = item.quantidade_solicitada or 0
        if unit_approved == 0:
            unit_approved = decimal_money(item.valor_unitario_estimado)
        approved += Decimal(qty_approved) * unit_approved
        real += Decimal(item.quantidade_comprada or 0) * decimal_money(item.valor_unitario_real)
    req.valor_estimado = estimated.quantize(Decimal("0.01"))
    req.valor_aprovado = (approved if approved else estimated).quantize(Decimal("0.01"))
    req.valor_real = real.quantize(Decimal("0.01"))
    req.updated_at = datetime.now()


def rules_for_purchase(req):
    ensure_default_approval_rules()
    total = decimal_money(req.valor_aprovado or req.valor_estimado)
    rules = db.session.execute(
        db.select(PurchaseApprovalRule)
        .where(PurchaseApprovalRule.ativa == True)  # noqa: E712
        .order_by(PurchaseApprovalRule.ordem_aprovacao, PurchaseApprovalRule.valor_minimo)
    ).scalars().all()
    matched = []
    for rule in rules:
        if rule.unidade and rule.unidade != req.unidade:
            continue
        if rule.centro_custo and rule.centro_custo != req.centro_custo:
            continue
        if rule.categoria and rule.categoria != req.categoria:
            continue
        if total < decimal_money(rule.valor_minimo):
            continue
        if rule.valor_maximo is not None and total > decimal_money(rule.valor_maximo):
            continue
        matched.append(rule)
    return sorted(matched, key=lambda r: (r.ordem_aprovacao or 1, decimal_money(r.valor_minimo)))


def transition_purchase(req, action, user, payload=None, audit=None, ip_address=""):
    payload = payload or {}
    action = clean_text(action, 80)
    status_before = req.status
    status_after = payload.get("status_novo") or req.status
    if status_after and status_after not in PURCHASE_STATUS:
        raise PurchaseError("Status invalido.", 400)
    if status_after:
        req.status = status_after
    hist = PurchaseStatusHistory(
        id=new_id("PH"), purchase_request_id=req.id, status_anterior=status_before,
        status_novo=req.status, acao=action, usuario_id=getattr(user, "id", "") or "",
        usuario_nome=getattr(user, "nome", "") or getattr(user, "username", ""),
        observacao=clean_text(payload.get("observacao"), 2000),
    )
    db.session.add(hist)
    db.session.add(PurchaseProcurementAction(
        id=new_id("PA"), purchase_request_id=req.id,
        responsavel_id=getattr(user, "id", "") or "",
        responsavel_nome=getattr(user, "nome", "") or getattr(user, "username", ""),
        acao=action, status_anterior=status_before, status_novo=req.status,
        fornecedor=clean_text(payload.get("fornecedor"), 120),
        numero_compra=clean_text(payload.get("numero_compra"), 60),
        valor_compra=decimal_money(payload.get("valor_compra", 0)),
        observacao=clean_text(payload.get("observacao"), 2000),
    ))
    if audit:
        audit("COMPRAS_ACAO", "compras", req.id, f"{action}: {status_before} -> {req.status}")


def safe_purchase_link(raw_url):
    url = clean_text(raw_url, 1000)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        return ""
    if re.match(r"(?i)^javascript:", url):
        return ""
    return url


def apply_request_payload(req, data, user=None, creating=False):
    fields = {
        "solicitante": ("solicitante", 120), "unidade": ("unidade", 80),
        "centroCusto": ("centro_custo", 80), "categoria": ("categoria", 80),
        "prioridade": ("prioridade", 20), "justificativa": ("justificativa", 3000),
        "fornecedorSugerido": ("fornecedor_sugerido", 120), "prazoDesejado": ("prazo_desejado", 10),
        "observacao": ("observacao", 3000),
    }
    for source, (target, max_len) in fields.items():
        if source in data or creating:
            setattr(req, target, clean_text(data.get(source), max_len))
    if not req.solicitante and user is not None:
        req.solicitante = getattr(user, "nome", "") or getattr(user, "username", "")
    if user is not None and not req.solicitante_id:
        req.solicitante_id = getattr(user, "id", None)
    if not req.solicitante:
        raise PurchaseError("Solicitante obrigatorio.", 400)


def replace_items(req, items_data, user=None):
    if not isinstance(items_data, list) or not items_data:
        raise PurchaseError("Informe ao menos um item.", 400)
    req.items = []
    for idx, raw in enumerate(items_data, 1):
        raw = raw if isinstance(raw, dict) else {}
        produto = clean_text(raw.get("produto") or raw.get("item"), 160)
        if not produto:
            raise PurchaseError(f"Item {idx}: produto obrigatorio.", 400)
        tipo_item = clean_text(raw.get("tipoItem") or raw.get("tipo_item") or "INSUMO", 30).upper()
        if tipo_item not in PURCHASE_ITEM_TYPES:
            raise PurchaseError(f"Item {idx}: tipo de item invalido.", 400)
        item = PurchaseRequestItem(
            id=new_id("PI"), produto=produto, tipo_item=tipo_item,
            supply_id=clean_text(raw.get("supplyId"), 16) or None,
            categoria=clean_text(raw.get("categoria"), 80), descricao=clean_text(raw.get("descricao"), 3000),
            especificacao=clean_text(raw.get("especificacao"), 3000), marca_sugerida=clean_text(raw.get("marcaSugerida"), 80),
            modelo_sugerido=clean_text(raw.get("modeloSugerido"), 120),
            quantidade_solicitada=parse_int(raw.get("quantidadeSolicitada", raw.get("quantidade")), 1, 1),
            quantidade_aprovada=parse_int(raw.get("quantidadeAprovada"), 0, 0),
            quantidade_comprada=parse_int(raw.get("quantidadeComprada"), 0, 0),
            quantidade_recebida=parse_int(raw.get("quantidadeRecebida"), 0, 0),
            valor_unitario_estimado=decimal_money(raw.get("valorUnitarioEstimado", raw.get("valorUnitario"))),
            valor_unitario_aprovado=decimal_money(raw.get("valorUnitarioAprovado")),
            valor_unitario_real=decimal_money(raw.get("valorUnitarioReal")),
            fornecedor_sugerido=clean_text(raw.get("fornecedorSugerido"), 120),
            estoque_atual=parse_int(raw.get("estoqueAtual"), 0, 0), estoque_minimo=parse_int(raw.get("estoqueMinimo"), 0, 0),
            justificativa=clean_text(raw.get("justificativa"), 2000), observacao=clean_text(raw.get("observacao"), 2000),
        )
        links = raw.get("links") or []
        main_seen = False
        if isinstance(links, list):
            for link_raw in links:
                if not isinstance(link_raw, dict):
                    continue
                url = safe_purchase_link(link_raw.get("url"))
                if not url:
                    continue
                principal = parse_bool(link_raw.get("linkPrincipal"), default=False) and not main_seen
                main_seen = main_seen or principal
                item.links.append(PurchaseItemLink(
                    id=new_id("PL"), url=url, descricao=clean_text(link_raw.get("descricao"), 240),
                    fornecedor=clean_text(link_raw.get("fornecedor"), 120), link_principal=principal,
                    usuario_id=getattr(user, "id", "") if user is not None else "",
                    observacao=clean_text(link_raw.get("observacao"), 1000),
                ))
        req.items.append(item)


def create_purchase(data, user, audit=None):
    req = PurchaseRequest(id=new_id("SC"), numero=next_purchase_number(), created_by=getattr(user, "username", ""))
    apply_request_payload(req, data, user=user, creating=True)
    replace_items(req, data.get("items") or [], user=user)
    recalculate_purchase(req)
    db.session.add(req)
    db.session.flush()
    transition_purchase(req, "Criacao da solicitacao", user, {"status_novo": req.status}, audit=audit)
    return req


def update_purchase(req, data, user, audit=None):
    if req.status not in ("Rascunho", "Devolvida para correcao"):
        raise PurchaseError("Somente rascunhos ou solicitacoes devolvidas podem ser editados.", 409)
    apply_request_payload(req, data, user=user)
    if "items" in data:
        replace_items(req, data.get("items") or [], user=user)
    recalculate_purchase(req)
    transition_purchase(req, "Edicao da solicitacao", user, {"status_novo": req.status}, audit=audit)
    return req


def submit_purchase(req, user, audit=None):
    if req.status not in ("Rascunho", "Devolvida para correcao"):
        raise PurchaseError("Solicitacao nao pode ser enviada neste status.", 409)
    recalculate_purchase(req)
    req.approval_steps = []
    rules = rules_for_purchase(req)
    for rule in rules:
        req.approval_steps.append(PurchaseApprovalStep(
            id=new_id("PS"), regra_aprovacao_id=rule.id, ordem=rule.ordem_aprovacao or 1,
            permission_code=rule.permission_code or "compras.aprovar_gerente",
            perfil_aprovador=rule.perfil_aprovador, usuario_aprovador_id=rule.usuario_aprovador_id,
            status="Pendente", valor_no_momento=req.valor_aprovado,
        ))
    next_status = status_for_next_step(req) or "Aguardando envio para Suprimentos"
    transition_purchase(req, "Envio para aprovacao", user, {"status_novo": next_status}, audit=audit)
    return req


def status_for_next_step(req):
    pending = sorted([s for s in req.approval_steps if s.status == "Pendente"], key=lambda s: s.ordem)
    if not pending:
        return None
    step = pending[0]
    if step.permission_code == "compras.aprovar_diretor" or step.ordem > 1:
        return "Aguardando aprovacao do Diretor"
    return "Aguardando aprovacao do Gerente de TI"


def approve_purchase(req, user, data, audit=None, ip_address=""):
    if not req.status.startswith("Aguardando aprovacao"):
        raise PurchaseError("Solicitacao nao esta aguardando aprovacao.", 409)
    decisao = clean_text(data.get("decisao") or "Aprovada", 40)
    if decisao not in ("Aprovada", "Aprovada parcialmente", "Reprovada", "Devolvida para correcao"):
        raise PurchaseError("Decisao invalida.", 400)
    justificativa = clean_text(data.get("justificativa"), 2000)
    if decisao in ("Reprovada", "Devolvida para correcao") and not justificativa:
        raise PurchaseError("Justificativa obrigatoria para reprovar ou devolver.", 400)
    step = next((s for s in sorted(req.approval_steps, key=lambda s: s.ordem) if s.status == "Pendente"), None)
    if step is None:
        raise PurchaseError("Nao ha etapa de aprovacao pendente.", 409)
    if decisao in ("Aprovada", "Aprovada parcialmente"):
        for item in req.items:
            if not item.quantidade_aprovada:
                item.quantidade_aprovada = item.quantidade_solicitada or 0
            if not item.valor_unitario_aprovado:
                item.valor_unitario_aprovado = item.valor_unitario_estimado or 0
    recalculate_purchase(req)
    approved_value = decimal_money(data.get("valorAprovado", req.valor_aprovado))
    step.status = "Aprovada" if decisao.startswith("Aprovada") else decisao
    step.aprovador_id = getattr(user, "id", "")
    step.aprovador_nome = getattr(user, "nome", "") or getattr(user, "username", "")
    step.valor_no_momento = req.valor_estimado
    step.valor_aprovado = approved_value
    step.justificativa = justificativa
    step.decided_at = datetime.now()
    db.session.flush()
    db.session.add(PurchaseApproval(
        id=new_id("AP"), purchase_request_id=req.id, regra_aprovacao_id=step.regra_aprovacao_id,
        step_id=step.id, aprovador_id=step.aprovador_id, aprovador_nome=step.aprovador_nome,
        aprovador_perfil=getattr(user, "perfil", ""), ordem=step.ordem, decisao=decisao,
        valor_no_momento=req.valor_estimado, valor_aprovado=approved_value,
        justificativa=justificativa, ip_address=ip_address,
    ))
    if decisao == "Reprovada":
        next_status = "Reprovada"
    elif decisao == "Devolvida para correcao":
        next_status = "Devolvida para correcao"
    else:
        next_status = status_for_next_step(req) or "Aguardando envio para Suprimentos"
    transition_purchase(req, f"Decisao de aprovacao: {decisao}", user, {"status_novo": next_status, "observacao": justificativa}, audit=audit)
    return req


def send_to_procurement(req, user, data=None, audit=None):
    if req.status != "Aguardando envio para Suprimentos":
        raise PurchaseError("Solicitacao ainda nao esta liberada para Suprimentos.", 409)
    req.enviado_suprimentos_em = datetime.now()
    req.enviado_suprimentos_por = getattr(user, "nome", "") or getattr(user, "username", "")
    transition_purchase(req, "Envio para Suprimentos", user, {"status_novo": "Enviada para Suprimentos", "observacao": (data or {}).get("observacao")}, audit=audit)
    return req


def procurement_action(req, user, data, audit=None):
    status = clean_text(data.get("status"), 60)
    if status and status not in PURCHASE_STATUS:
        raise PurchaseError("Status invalido.", 400)
    allowed_from = {"Enviada para Suprimentos", "Em analise por Suprimentos", "Compra iniciada", "Em cotacao", "Aguardando emissao do pedido", "Pedido de compra emitido", "Aguardando entrega", "Recebida parcialmente"}
    if req.status not in allowed_from:
        raise PurchaseError("Suprimentos nao pode atuar neste status.", 409)
    if status == "Compra iniciada":
        req.responsavel_compra = clean_text(data.get("responsavelCompra"), 120) or getattr(user, "nome", "") or getattr(user, "username", "")
    for source, attr, max_len in (
        ("fornecedorFinal", "fornecedor_final", 120), ("numeroCompra", "numero_compra", 60),
        ("numeroPedido", "numero_pedido", 60), ("numeroProcesso", "numero_processo", 60),
        ("previsaoEntrega", "previsao_entrega", 10),
    ):
        if source in data:
            setattr(req, attr, clean_text(data.get(source), max_len))
    if "valorReal" in data:
        req.valor_real = decimal_money(data.get("valorReal"))
    transition_purchase(req, clean_text(data.get("acao"), 80) or "Atualizacao de Suprimentos", user, {
        "status_novo": status or req.status, "observacao": data.get("observacao"),
        "fornecedor": req.fornecedor_final, "numero_compra": req.numero_compra, "valor_compra": req.valor_real,
    }, audit=audit)
    return req


def receive_purchase(req, user, data, audit=None):
    if req.status not in {"Pedido de compra emitido", "Aguardando entrega", "Recebida parcialmente", "Recebida"}:
        raise PurchaseError("Recebimento nao permitido neste status.", 409)
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        raise PurchaseError("Informe os itens recebidos.", 400)
    any_received = False
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item_id = clean_text(raw.get("itemId") or raw.get("purchaseItemId"), 20)
        qty = parse_int(raw.get("quantidade"), 0, 1)
        item = next((i for i in req.items if i.id == item_id), None)
        if item is None:
            raise PurchaseError("Item de compra nao encontrado.", 404)
        limit = item.quantidade_aprovada or item.quantidade_solicitada or 0
        pending = max(0, limit - (item.quantidade_recebida or 0))
        if qty > pending:
            raise PurchaseError(f"Quantidade recebida excede o pendente para {item.produto}.", 400)
        supply_id = clean_text(raw.get("supplyId") or item.supply_id, 16)
        if item.tipo_item == "INSUMO":
            if not supply_id:
                raise PurchaseError(f"Item {item.produto} precisa estar vinculado a um insumo para entrada no estoque.", 400)
            supply = db.session.get(Supply, supply_id)
            if supply is None:
                raise PurchaseError("Insumo vinculado ao recebimento nao encontrado.", 404)
            supply.estoque = (supply.estoque or 0) + qty
            db.session.add(SupplyMovement(
                id=new_id("MOV"), tipo="ENTRADA_COMPRA", ref_id=req.numero or req.id,
                supply_nome=supply.nome, descricao=f"{supply.nome}: +{qty} via {req.numero}",
                quantidade=qty, colaborador=req.solicitante, ativo_id=req.numero or req.id,
                motivo="Recebimento de compra",
            ))
            item.supply_id = supply.id
        item.quantidade_recebida = (item.quantidade_recebida or 0) + qty
        if not item.quantidade_comprada:
            item.quantidade_comprada = item.quantidade_recebida
        if raw.get("valorUnitario") not in (None, ""):
            item.valor_unitario_real = decimal_money(raw.get("valorUnitario"))
        db.session.add(PurchaseReceipt(
            id=new_id("RC"), purchase_request_id=req.id, purchase_item_id=item.id,
            supply_id=supply_id or None, quantidade=qty, numero_nota=clean_text(data.get("numeroNota"), 60),
            numero_compra=clean_text(data.get("numeroCompra") or req.numero_compra, 60),
            valor_unitario=decimal_money(raw.get("valorUnitario", item.valor_unitario_real)),
            recebido_por_id=getattr(user, "id", "") or "",
            recebido_por_nome=getattr(user, "nome", "") or getattr(user, "username", ""),
            observacao=clean_text(data.get("observacao"), 2000),
        ))
        any_received = True
    if not any_received:
        raise PurchaseError("Nenhum item recebido.", 400)
    recalculate_purchase(req)
    all_done = all((i.quantidade_recebida or 0) >= (i.quantidade_aprovada or i.quantidade_solicitada or 0) for i in req.items)
    next_status = "Recebida" if all_done else "Recebida parcialmente"
    transition_purchase(req, "Recebimento de compra", user, {"status_novo": next_status, "observacao": data.get("observacao")}, audit=audit)
    if all_done and all((i.tipo_item != "INSUMO") or i.supply_id for i in req.items):
        transition_purchase(req, "Entrada no estoque", user, {"status_novo": "Entrada no estoque realizada"}, audit=audit)
    return req


def apply_rule_payload(rule, data):
    rule.nome = clean_text(data.get("nome", rule.nome), 160)
    rule.valor_minimo = decimal_money(data.get("valorMinimo", rule.valor_minimo))
    raw_max = data.get("valorMaximo", rule.valor_maximo)
    rule.valor_maximo = None if raw_max in (None, "", "Sem limite") else decimal_money(raw_max)
    rule.ordem_aprovacao = parse_int(data.get("ordemAprovacao", rule.ordem_aprovacao), 1, 1)
    rule.permission_code = clean_text(data.get("permissionCode", rule.permission_code), 80) or ("compras.aprovar_diretor" if rule.ordem_aprovacao > 1 else "compras.aprovar_gerente")
    rule.perfil_aprovador = clean_text(data.get("perfilAprovador", rule.perfil_aprovador), 60)
    rule.usuario_aprovador_id = clean_text(data.get("usuarioAprovadorId", rule.usuario_aprovador_id), 16)
    rule.unidade = clean_text(data.get("unidade", rule.unidade), 80)
    rule.centro_custo = clean_text(data.get("centroCusto", rule.centro_custo), 80)
    rule.categoria = clean_text(data.get("categoria", rule.categoria), 80)
    rule.obrigatoria = parse_bool(data.get("obrigatoria", rule.obrigatoria), default=True)
    rule.ativa = parse_bool(data.get("ativa", rule.ativa), default=True)
    rule.vigencia_inicio = clean_text(data.get("vigenciaInicio", rule.vigencia_inicio), 10)
    rule.vigencia_fim = clean_text(data.get("vigenciaFim", rule.vigencia_fim), 10)
    rule.observacao = clean_text(data.get("observacao", rule.observacao), 2000)
    if not rule.nome:
        raise PurchaseError("Nome da regra obrigatorio.", 400)
    if not rule.permission_code:
        raise PurchaseError("Permissao da regra obrigatoria.", 400)
    return rule
