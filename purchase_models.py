"""Modelos do modulo de compras e reposicao."""
from datetime import datetime
from decimal import Decimal

from extensions import db


PURCHASE_STATUS = [
    "Rascunho",
    "Aguardando aprovacao do Gerente de TI",
    "Aprovada pelo Gerente de TI",
    "Aguardando aprovacao do Diretor",
    "Aprovada pelo Diretor",
    "Aprovada parcialmente",
    "Reprovada",
    "Devolvida para correcao",
    "Aguardando envio para Suprimentos",
    "Enviada para Suprimentos",
    "Em analise por Suprimentos",
    "Compra iniciada",
    "Em cotacao",
    "Aguardando emissao do pedido",
    "Pedido de compra emitido",
    "Aguardando entrega",
    "Recebida parcialmente",
    "Recebida",
    "Entrada no estoque realizada",
    "Concluida",
    "Cancelada",
]

PURCHASE_ITEM_TYPES = ["INSUMO", "PATRIMONIAL", "LICENCA", "SERVICO"]


def money(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value or 0)


class PurchaseRequest(db.Model):
    __tablename__ = "purchase_requests"

    id = db.Column(db.String(16), primary_key=True)
    numero = db.Column(db.String(30), unique=True, index=True)
    solicitante = db.Column(db.String(120), nullable=False)
    solicitante_id = db.Column(db.String(16), db.ForeignKey("system_users.id"), nullable=True)
    unidade = db.Column(db.String(80), default="")
    centro_custo = db.Column(db.String(80), default="")
    categoria = db.Column(db.String(80), default="")
    prioridade = db.Column(db.String(20), default="Normal")
    justificativa = db.Column(db.Text, default="")
    fornecedor_sugerido = db.Column(db.String(120), default="")
    prazo_desejado = db.Column(db.String(10), default="")
    status = db.Column(db.String(60), default="Rascunho", index=True)
    valor_estimado = db.Column(db.Numeric(14, 2), default=0)
    valor_aprovado = db.Column(db.Numeric(14, 2), default=0)
    valor_real = db.Column(db.Numeric(14, 2), default=0)
    enviado_suprimentos_em = db.Column(db.DateTime)
    enviado_suprimentos_por = db.Column(db.String(120), default="")
    responsavel_compra = db.Column(db.String(120), default="")
    fornecedor_final = db.Column(db.String(120), default="")
    numero_compra = db.Column(db.String(60), default="")
    numero_pedido = db.Column(db.String(60), default="")
    numero_processo = db.Column(db.String(60), default="")
    previsao_entrega = db.Column(db.String(10), default="")
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = db.Column(db.String(120), default="")

    items = db.relationship("PurchaseRequestItem", backref="request", cascade="all, delete-orphan", lazy=True)
    approvals = db.relationship("PurchaseApproval", backref="request", cascade="all, delete-orphan", lazy=True)
    approval_steps = db.relationship("PurchaseApprovalStep", backref="request", cascade="all, delete-orphan", lazy=True)
    actions = db.relationship("PurchaseProcurementAction", backref="request", cascade="all, delete-orphan", lazy=True)
    history = db.relationship("PurchaseStatusHistory", backref="request", cascade="all, delete-orphan", lazy=True)
    receipts = db.relationship("PurchaseReceipt", backref="request", cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_items=False, include_history=False):
        data = {
            "id": self.id,
            "numero": self.numero,
            "solicitante": self.solicitante,
            "solicitanteId": self.solicitante_id,
            "unidade": self.unidade,
            "centroCusto": self.centro_custo,
            "categoria": self.categoria,
            "prioridade": self.prioridade,
            "justificativa": self.justificativa,
            "fornecedorSugerido": self.fornecedor_sugerido,
            "prazoDesejado": self.prazo_desejado,
            "status": self.status,
            "valorEstimado": money(self.valor_estimado),
            "valorAprovado": money(self.valor_aprovado),
            "valorReal": money(self.valor_real),
            "enviadoSuprimentosEm": self.enviado_suprimentos_em.isoformat() if self.enviado_suprimentos_em else None,
            "enviadoSuprimentosPor": self.enviado_suprimentos_por,
            "responsavelCompra": self.responsavel_compra,
            "fornecedorFinal": self.fornecedor_final,
            "numeroCompra": self.numero_compra,
            "numeroPedido": self.numero_pedido,
            "numeroProcesso": self.numero_processo,
            "previsaoEntrega": self.previsao_entrega,
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
            "createdBy": self.created_by,
            "itemCount": len(self.items or []),
        }
        if include_items:
            data["items"] = [item.to_dict(include_links=True) for item in self.items]
        if include_history:
            data["approvals"] = [approval.to_dict() for approval in self.approvals]
            data["approvalSteps"] = [step.to_dict() for step in self.approval_steps]
            data["actions"] = [action.to_dict() for action in self.actions]
            data["history"] = [entry.to_dict() for entry in self.history]
            data["receipts"] = [receipt.to_dict() for receipt in self.receipts]
        return data


class PurchaseRequestItem(db.Model):
    __tablename__ = "purchase_request_items"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    supply_id = db.Column(db.String(16), db.ForeignKey("supplies.id"), nullable=True)
    produto = db.Column(db.String(160), nullable=False)
    categoria = db.Column(db.String(80), default="")
    tipo_item = db.Column(db.String(30), default="INSUMO")
    descricao = db.Column(db.Text, default="")
    especificacao = db.Column(db.Text, default="")
    marca_sugerida = db.Column(db.String(80), default="")
    modelo_sugerido = db.Column(db.String(120), default="")
    quantidade_solicitada = db.Column(db.Integer, default=1)
    quantidade_aprovada = db.Column(db.Integer, default=0)
    quantidade_comprada = db.Column(db.Integer, default=0)
    quantidade_recebida = db.Column(db.Integer, default=0)
    valor_unitario_estimado = db.Column(db.Numeric(14, 2), default=0)
    valor_unitario_aprovado = db.Column(db.Numeric(14, 2), default=0)
    valor_unitario_real = db.Column(db.Numeric(14, 2), default=0)
    fornecedor_sugerido = db.Column(db.String(120), default="")
    estoque_atual = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=0)
    justificativa = db.Column(db.Text, default="")
    observacao = db.Column(db.Text, default="")

    links = db.relationship("PurchaseItemLink", backref="item", cascade="all, delete-orphan", lazy=True)
    receipts = db.relationship("PurchaseReceipt", backref="item", cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_links=False):
        qtd = self.quantidade_solicitada or 0
        qtd_aprovada = self.quantidade_aprovada or 0
        qtd_comprada = self.quantidade_comprada or 0
        unit_est = money(self.valor_unitario_estimado)
        unit_apr = money(self.valor_unitario_aprovado)
        unit_real = money(self.valor_unitario_real)
        data = {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "supplyId": self.supply_id,
            "produto": self.produto,
            "categoria": self.categoria,
            "tipoItem": self.tipo_item,
            "descricao": self.descricao,
            "especificacao": self.especificacao,
            "marcaSugerida": self.marca_sugerida,
            "modeloSugerido": self.modelo_sugerido,
            "quantidadeSolicitada": qtd,
            "quantidadeAprovada": qtd_aprovada,
            "quantidadeComprada": qtd_comprada,
            "quantidadeRecebida": self.quantidade_recebida or 0,
            "valorUnitarioEstimado": unit_est,
            "valorUnitarioAprovado": unit_apr,
            "valorUnitarioReal": unit_real,
            "valorTotalEstimado": round(qtd * unit_est, 2),
            "valorTotalAprovado": round(qtd_aprovada * unit_apr, 2),
            "valorTotalReal": round(qtd_comprada * unit_real, 2),
            "fornecedorSugerido": self.fornecedor_sugerido,
            "estoqueAtual": self.estoque_atual or 0,
            "estoqueMinimo": self.estoque_minimo or 0,
            "justificativa": self.justificativa,
            "observacao": self.observacao,
        }
        if include_links:
            data["links"] = [link.to_dict() for link in self.links]
        return data


class PurchaseItemLink(db.Model):
    __tablename__ = "purchase_item_links"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_item_id = db.Column(db.String(20), db.ForeignKey("purchase_request_items.id"), nullable=False)
    url = db.Column(db.String(1000), nullable=False)
    descricao = db.Column(db.String(240), default="")
    fornecedor = db.Column(db.String(120), default="")
    link_principal = db.Column(db.Boolean, default=False)
    usuario_id = db.Column(db.String(16), default="")
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "descricao": self.descricao,
            "fornecedor": self.fornecedor,
            "linkPrincipal": bool(self.link_principal),
            "usuarioId": self.usuario_id,
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class PurchaseApprovalRule(db.Model):
    __tablename__ = "purchase_approval_rules"

    id = db.Column(db.String(20), primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    valor_minimo = db.Column(db.Numeric(14, 2), default=0)
    valor_maximo = db.Column(db.Numeric(14, 2))
    ordem_aprovacao = db.Column(db.Integer, default=1)
    permission_code = db.Column(db.String(80), default="")
    perfil_aprovador = db.Column(db.String(60), default="")
    usuario_aprovador_id = db.Column(db.String(16), default="")
    unidade = db.Column(db.String(80), default="")
    centro_custo = db.Column(db.String(80), default="")
    categoria = db.Column(db.String(80), default="")
    obrigatoria = db.Column(db.Boolean, default=True)
    ativa = db.Column(db.Boolean, default=True)
    vigencia_inicio = db.Column(db.String(10), default="")
    vigencia_fim = db.Column(db.String(10), default="")
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "valorMinimo": money(self.valor_minimo),
            "valorMaximo": None if self.valor_maximo is None else money(self.valor_maximo),
            "ordemAprovacao": self.ordem_aprovacao or 1,
            "permissionCode": self.permission_code,
            "perfilAprovador": self.perfil_aprovador,
            "usuarioAprovadorId": self.usuario_aprovador_id,
            "unidade": self.unidade,
            "centroCusto": self.centro_custo,
            "categoria": self.categoria,
            "obrigatoria": bool(self.obrigatoria),
            "ativa": bool(self.ativa),
            "vigenciaInicio": self.vigencia_inicio,
            "vigenciaFim": self.vigencia_fim,
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }


class PurchaseApprovalStep(db.Model):
    __tablename__ = "purchase_approval_steps"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    regra_aprovacao_id = db.Column(db.String(20), db.ForeignKey("purchase_approval_rules.id"))
    ordem = db.Column(db.Integer, nullable=False)
    permission_code = db.Column(db.String(80), nullable=False)
    perfil_aprovador = db.Column(db.String(60), default="")
    usuario_aprovador_id = db.Column(db.String(16), default="")
    status = db.Column(db.String(20), default="Pendente")
    aprovador_id = db.Column(db.String(16))
    aprovador_nome = db.Column(db.String(120), default="")
    valor_no_momento = db.Column(db.Numeric(14, 2), default=0)
    valor_aprovado = db.Column(db.Numeric(14, 2), default=0)
    justificativa = db.Column(db.Text)
    decided_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "regraAprovacaoId": self.regra_aprovacao_id,
            "ordem": self.ordem,
            "permissionCode": self.permission_code,
            "perfilAprovador": self.perfil_aprovador,
            "usuarioAprovadorId": self.usuario_aprovador_id,
            "status": self.status,
            "aprovadorId": self.aprovador_id,
            "aprovadorNome": self.aprovador_nome,
            "valorNoMomento": money(self.valor_no_momento),
            "valorAprovado": money(self.valor_aprovado),
            "justificativa": self.justificativa,
            "decidedAt": self.decided_at.isoformat() if self.decided_at else None,
        }


class PurchaseApproval(db.Model):
    __tablename__ = "purchase_approvals"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    regra_aprovacao_id = db.Column(db.String(20), db.ForeignKey("purchase_approval_rules.id"))
    step_id = db.Column(db.String(20), db.ForeignKey("purchase_approval_steps.id"))
    aprovador_id = db.Column(db.String(16), default="")
    aprovador_nome = db.Column(db.String(120), default="")
    aprovador_perfil = db.Column(db.String(60), default="")
    ordem = db.Column(db.Integer, default=1)
    decisao = db.Column(db.String(40), default="")
    valor_no_momento = db.Column(db.Numeric(14, 2), default=0)
    valor_aprovado = db.Column(db.Numeric(14, 2), default=0)
    justificativa = db.Column(db.Text, default="")
    ip_address = db.Column(db.String(50), default="")
    approved_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "regraAprovacaoId": self.regra_aprovacao_id,
            "stepId": self.step_id,
            "aprovadorId": self.aprovador_id,
            "aprovadorNome": self.aprovador_nome,
            "aprovadorPerfil": self.aprovador_perfil,
            "ordem": self.ordem or 1,
            "decisao": self.decisao,
            "valorNoMomento": money(self.valor_no_momento),
            "valorAprovado": money(self.valor_aprovado),
            "justificativa": self.justificativa,
            "ipAddress": self.ip_address,
            "approvedAt": self.approved_at.isoformat() if self.approved_at else None,
        }


class PurchaseProcurementAction(db.Model):
    __tablename__ = "purchase_procurement_actions"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    responsavel_id = db.Column(db.String(16), default="")
    responsavel_nome = db.Column(db.String(120), default="")
    acao = db.Column(db.String(80), nullable=False)
    status_anterior = db.Column(db.String(60), default="")
    status_novo = db.Column(db.String(60), default="")
    fornecedor = db.Column(db.String(120), default="")
    numero_compra = db.Column(db.String(60), default="")
    valor_compra = db.Column(db.Numeric(14, 2), default=0)
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "responsavelId": self.responsavel_id,
            "responsavelNome": self.responsavel_nome,
            "acao": self.acao,
            "statusAnterior": self.status_anterior,
            "statusNovo": self.status_novo,
            "fornecedor": self.fornecedor,
            "numeroCompra": self.numero_compra,
            "valorCompra": money(self.valor_compra),
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseStatusHistory(db.Model):
    __tablename__ = "purchase_status_history"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    status_anterior = db.Column(db.String(60), default="")
    status_novo = db.Column(db.String(60), default="")
    acao = db.Column(db.String(80), default="")
    usuario_id = db.Column(db.String(16), default="")
    usuario_nome = db.Column(db.String(120), default="")
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "statusAnterior": self.status_anterior,
            "statusNovo": self.status_novo,
            "acao": self.acao,
            "usuarioId": self.usuario_id,
            "usuarioNome": self.usuario_nome,
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class PurchaseReceipt(db.Model):
    __tablename__ = "purchase_receipts"

    id = db.Column(db.String(20), primary_key=True)
    purchase_request_id = db.Column(db.String(16), db.ForeignKey("purchase_requests.id"), nullable=False)
    purchase_item_id = db.Column(db.String(20), db.ForeignKey("purchase_request_items.id"), nullable=False)
    supply_id = db.Column(db.String(16), db.ForeignKey("supplies.id"), nullable=True)
    quantidade = db.Column(db.Integer, nullable=False)
    numero_nota = db.Column(db.String(60), default="")
    numero_compra = db.Column(db.String(60), default="")
    valor_unitario = db.Column(db.Numeric(14, 2), default=0)
    recebido_por_id = db.Column(db.String(16), default="")
    recebido_por_nome = db.Column(db.String(120), default="")
    observacao = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "purchaseRequestId": self.purchase_request_id,
            "purchaseItemId": self.purchase_item_id,
            "supplyId": self.supply_id,
            "quantidade": self.quantidade,
            "numeroNota": self.numero_nota,
            "numeroCompra": self.numero_compra,
            "valorUnitario": money(self.valor_unitario),
            "recebidoPorId": self.recebido_por_id,
            "recebidoPorNome": self.recebido_por_nome,
            "observacao": self.observacao,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }
