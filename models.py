"""Modelos SQLAlchemy do TI Control."""
import json
from datetime import date, datetime

from flask_login import UserMixin
from sqlalchemy import text
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db


class SystemUser(UserMixin, db.Model):
    __tablename__ = "system_users"
    id           = db.Column(db.String(16), primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    nome         = db.Column(db.String(120))
    email        = db.Column(db.String(120))
    senha_hash   = db.Column(db.String(256))
    perfil       = db.Column(db.String(40), default="Visualizador")
    status       = db.Column(db.String(20), default="Ativo")
    ultimo_acesso= db.Column(db.DateTime)
    criado_em    = db.Column(db.Date, default=date.today)

    def set_senha(self, raw): self.senha_hash = generate_password_hash(raw)
    def check_senha(self, raw): return check_password_hash(self.senha_hash, raw)

    def to_dict(self):
        return {"id":self.id,"username":self.username,"nome":self.nome,"email":self.email,
                "perfil":self.perfil,"status":self.status,
                "ultimoAcesso":self.ultimo_acesso.isoformat() if self.ultimo_acesso else None,
                "criadoEm":str(self.criado_em)}


class Colaborador(db.Model):
    __tablename__ = "colaboradores"
    id           = db.Column(db.String(16), primary_key=True)
    nome         = db.Column(db.String(120), nullable=False, index=True)
    email        = db.Column(db.String(120))
    telefone     = db.Column(db.String(30))
    cpf          = db.Column(db.String(20))
    cargo        = db.Column(db.String(80))
    setor        = db.Column(db.String(80))
    unidade      = db.Column(db.String(80))
    status       = db.Column(db.String(20), default="Ativo")
    matricula    = db.Column(db.String(40))
    data_admissao= db.Column(db.String(10))
    data_cadastro= db.Column(db.String(10))
    data_desligamento = db.Column(db.String(10))
    observacao   = db.Column(db.Text, default="")

    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"email":self.email,"telefone":self.telefone,"cpf":self.cpf,
                "cargo":self.cargo,"setor":self.setor,"unidade":self.unidade,"status":self.status,
                "matricula":self.matricula,"dataAdmissao":self.data_admissao,
                "dataCadastro":self.data_cadastro,"dataDesligamento":self.data_desligamento,
                "observacao":self.observacao}


ASSET_STATUS_VALID = ["Disponível","Alocado","Manutenção","Ativo",
                      "Baixado","Descartado","Extraviado","Vendido","Inativo"]


class Asset(db.Model):
    __tablename__ = "assets"
    __table_args__ = (
        db.Index(
            "ix_assets_patrimonio_unique_nonempty",
            "patrimonio",
            unique=True,
            sqlite_where=text("patrimonio IS NOT NULL AND patrimonio <> ''"),
            postgresql_where=text("patrimonio IS NOT NULL AND patrimonio <> ''"),
        ),
        db.Index(
            "ix_assets_service_tag_unique_nonempty",
            "service_tag",
            unique=True,
            sqlite_where=text("service_tag IS NOT NULL AND service_tag <> ''"),
            postgresql_where=text("service_tag IS NOT NULL AND service_tag <> ''"),
        ),
        db.Index(
            "ix_assets_mac_unique_nonempty",
            "mac",
            unique=True,
            sqlite_where=text("mac IS NOT NULL AND mac <> ''"),
            postgresql_where=text("mac IS NOT NULL AND mac <> ''"),
        ),
    )
    id           = db.Column(db.String(16), primary_key=True)
    hostname     = db.Column(db.String(80))
    ip           = db.Column(db.String(40), default="DHCP")
    mac          = db.Column(db.String(20))
    service_tag  = db.Column(db.String(40))
    os           = db.Column(db.String(80))
    fabricante   = db.Column(db.String(60))
    modelo       = db.Column(db.String(80))
    patrimonio   = db.Column(db.String(40))
    nf           = db.Column(db.String(40))
    categoria    = db.Column(db.String(40))
    status       = db.Column(db.String(30), default="Disponível", index=True)
    colaborador  = db.Column(db.String(120), default="", index=True)
    setor        = db.Column(db.String(80), default="")
    unidade      = db.Column(db.String(80), default="")
    garantia     = db.Column(db.String(10))
    criado_em    = db.Column(db.Date, default=date.today)
    public_token  = db.Column(db.String(80), unique=True, index=True)

    def to_dict(self):
        return {"id":self.id,"hostname":self.hostname,"ip":self.ip,"mac":self.mac,
                "serviceTag":self.service_tag,"os":self.os,"fabricante":self.fabricante,
                "modelo":self.modelo,"patrimonio":self.patrimonio,"nf":self.nf,
                "categoria":self.categoria,"status":self.status,"colaborador":self.colaborador,
                "setor":self.setor,"unidade":self.unidade,"garantia":self.garantia,
                "publicToken": self.public_token}


class Supply(db.Model):
    __tablename__ = "supplies"
    __table_args__ = (
        db.CheckConstraint("estoque >= 0", name="ck_supplies_estoque_nonnegative"),
    )
    id       = db.Column(db.String(16), primary_key=True)
    nome     = db.Column(db.String(120), nullable=False)
    categoria= db.Column(db.String(40))
    unidade  = db.Column(db.String(80))
    estoque  = db.Column(db.Integer, default=0)
    minimo   = db.Column(db.Integer, default=0)
    preco    = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {"id":self.id,"nome":self.nome,"categoria":self.categoria,
                "unidade":self.unidade,"estoque":self.estoque,
                "minimo":self.minimo,"preco":self.preco}


class SupplyMovement(db.Model):
    __tablename__ = "supply_movements"
    id           = db.Column(db.String(20), primary_key=True)
    tipo         = db.Column(db.String(20))
    ref_id       = db.Column(db.String(16), index=True)
    supply_nome  = db.Column(db.String(120))
    descricao    = db.Column(db.Text)
    quantidade   = db.Column(db.Integer)
    colaborador  = db.Column(db.String(120), default="", index=True)
    ativo_id     = db.Column(db.String(16), default="")
    motivo       = db.Column(db.String(80), default="")
    data         = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"id":self.id,"tipo":self.tipo,"refId":self.ref_id,"supplyNome":self.supply_nome,
                "descricao":self.descricao,"quantidade":self.quantidade,"colaborador":self.colaborador,
                "ativoId":self.ativo_id,"motivo":self.motivo,
                "data":self.data.isoformat() if self.data else None}


class PrintPrinter(db.Model):
    __tablename__ = "print_printers"
    id              = db.Column(db.String(60), primary_key=True)
    name            = db.Column(db.String(120))
    location        = db.Column(db.String(120))
    printer_type    = db.Column(db.String(40), default="USB/ZPL")
    windows_name    = db.Column(db.String(120))
    dpi             = db.Column(db.Integer, default=203)
    token_hash      = db.Column(db.String(64))
    status          = db.Column(db.String(20), default="Offline")
    last_seen       = db.Column(db.DateTime)
    created_at      = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "location": self.location,
            "type": self.printer_type,
            "windowsName": self.windows_name,
            "dpi": self.dpi or 203,
            "status": self.status,
            "lastSeen": self.last_seen.isoformat() if self.last_seen else None,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }


class PrintJob(db.Model):
    __tablename__ = "print_jobs"
    id          = db.Column(db.Integer, primary_key=True, autoincrement=True)
    printer_id  = db.Column(db.String(60), index=True)
    template    = db.Column(db.String(80))
    status      = db.Column(db.String(20), default="pending", index=True)
    copies      = db.Column(db.Integer, default=1)
    data        = db.Column(db.JSON, default=dict)
    zpl         = db.Column(db.Text)
    message     = db.Column(db.Text, default="")
    created_by  = db.Column(db.String(80))
    created_at  = db.Column(db.DateTime, default=datetime.now)
    picked_at   = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)

    def to_dict(self, include_zpl=False):
        data = {
            "id": self.id,
            "printerId": self.printer_id,
            "template": self.template,
            "status": self.status,
            "copies": self.copies,
            "data": self.data or {},
            "message": self.message or "",
            "createdBy": self.created_by,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "pickedAt": self.picked_at.isoformat() if self.picked_at else None,
            "finishedAt": self.finished_at.isoformat() if self.finished_at else None,
        }
        if include_zpl:
            data["zpl"] = self.zpl
        return data


class Allocation(db.Model):
    __tablename__ = "allocations"
    id           = db.Column(db.String(16), primary_key=True)
    ativo_id     = db.Column(db.String(16), db.ForeignKey("assets.id"), index=True)
    ativo_nome   = db.Column(db.String(200))
    colaborador  = db.Column(db.String(120))
    setor        = db.Column(db.String(80))
    unidade      = db.Column(db.String(80))
    email        = db.Column(db.String(120))
    data_aloc    = db.Column(db.String(10))
    data_encerramento = db.Column(db.String(10))
    motivo       = db.Column(db.String(80), default="Uso contínuo")
    status       = db.Column(db.String(20), default="Ativo")
    termo           = db.Column(db.String(30))
    termo_status    = db.Column(db.String(20), default="Pendente")
    data_assinatura = db.Column(db.DateTime)
    assinatura_ip   = db.Column(db.String(50))
    assinatura_img      = db.Column(db.Text)
    sign_token          = db.Column(db.String(64), unique=True)
    sign_token_expiry   = db.Column(db.DateTime)
    assinatura_ti_img   = db.Column(db.Text)
    assinatura_ti_nome  = db.Column(db.String(120))
    data_assinatura_ti  = db.Column(db.DateTime)
    tipo                = db.Column(db.String(30), default="Responsabilidade")
    data_devolucao_prevista = db.Column(db.String(10))
    items           = db.relationship("AllocationItem", backref="allocation",
                                     cascade="all, delete-orphan", lazy=True)
    asset_items     = db.relationship("AllocationAsset", backref="allocation",
                                     cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_items=False):
        ativos = [i.to_dict() for i in self.asset_items]
        if not ativos and self.ativo_id:
            ativos = [{"id": self.ativo_id, "nome": self.ativo_nome or self.ativo_id}]
        d = {"id":self.id,"ativo":self.ativo_id,"ativoNome":self.ativo_nome,
             "ativos": ativos,
             "colaborador":self.colaborador,"setor":self.setor,"unidade":self.unidade,
             "email":self.email,"dataAloc":self.data_aloc,"motivo":self.motivo,
             "dataEncerramento":self.data_encerramento,
             "tipo": self.tipo or "Responsabilidade",
             "dataDevolucaoPrevista": self.data_devolucao_prevista,
             "status":self.status,"termo":self.termo,"termoStatus":self.termo_status,
             "dataAssinatura":self.data_assinatura.isoformat() if self.data_assinatura else None,
             "assinaturaIp": self.assinatura_ip or None,
             "signTokenExpiry":self.sign_token_expiry.isoformat() if self.sign_token_expiry else None,
             "hasSignImg": bool(self.assinatura_img),
             "assinaturaTiNome": self.assinatura_ti_nome or None,
             "dataAssinaturaTi": self.data_assinatura_ti.isoformat() if self.data_assinatura_ti else None,
             "hasSignTiImg": bool(self.assinatura_ti_img)}
        if include_items:
            d["perifericos"] = [i.to_dict() for i in self.items]
        return d


class AllocationItem(db.Model):
    """Periféricos entregues junto com esta alocação — vinculados ao TERMO."""
    __tablename__ = "allocation_items"
    id           = db.Column(db.String(20), primary_key=True)
    allocation_id= db.Column(db.String(16), db.ForeignKey("allocations.id"))
    supply_id    = db.Column(db.String(16))
    supply_nome  = db.Column(db.String(120))
    quantidade   = db.Column(db.Integer)

    def to_dict(self):
        return {"id":self.id,"supplyId":self.supply_id,"nome":self.supply_nome,"quantidade":self.quantidade}


class AllocationAsset(db.Model):
    """Ativos patrimoniais vinculados ao mesmo termo de alocação."""
    __tablename__ = "allocation_assets"
    id            = db.Column(db.String(20), primary_key=True)
    allocation_id = db.Column(db.String(16), db.ForeignKey("allocations.id"), index=True)
    asset_id      = db.Column(db.String(16), db.ForeignKey("assets.id"), index=True)
    asset_nome    = db.Column(db.String(200))
    categoria     = db.Column(db.String(40))
    patrimonio    = db.Column(db.String(40))
    service_tag   = db.Column(db.String(40))

    def to_dict(self):
        return {
            "id": self.asset_id,
            "itemId": self.id,
            "nome": self.asset_nome,
            "categoria": self.categoria,
            "patrimonio": self.patrimonio,
            "serviceTag": self.service_tag,
        }


class License(db.Model):
    __tablename__ = "licenses"
    id          = db.Column(db.String(16), primary_key=True)
    software    = db.Column(db.String(120))
    fornecedor  = db.Column(db.String(80))
    total       = db.Column(db.Integer, default=0)
    atribuidas  = db.Column(db.Integer, default=0)
    vencimento  = db.Column(db.String(10))
    custo       = db.Column(db.Float, default=0.0)
    tipo        = db.Column(db.String(40))
    attachments = db.Column(db.JSON, default=list)

    @property
    def tipo_normalizado(self):
        tipo = (self.tipo or "").strip()
        if tipo in ("Assinatura", "Mensal", "Assinatura mensal"):
            return "Assinatura mensal"
        return tipo

    @property
    def custo_total(self):
        custo = self.custo or 0
        return round(custo * (self.total or 0), 2)

    @property
    def custo_mensal(self):
        if self.tipo_normalizado == "Assinatura mensal":
            return self.custo_total
        return 0

    @property
    def custo_anual(self):
        if self.tipo_normalizado == "Assinatura mensal":
            return round(self.custo_mensal * 12, 2)
        if self.tipo_normalizado == "Anual":
            return self.custo_total
        return 0

    def to_dict(self):
        saldo = (self.total or 0) - (self.atribuidas or 0)
        situacao = "Excedido" if saldo < 0 else ("Sem saldo" if saldo == 0 else "Regular")
        return {"id":self.id,"software":self.software,"fornecedor":self.fornecedor,
                "total":self.total,"atribuidas":self.atribuidas,"vencimento":self.vencimento,
                "custo":self.custo,"custoUnitario":self.custo,"custoTotal":self.custo_total,
                "custoMensal":self.custo_mensal,"custoAnual":self.custo_anual,
                "tipo":self.tipo_normalizado,"attachments":self.attachments or [],
                "saldo":saldo,"situacao":situacao}


class Incident(db.Model):
    __tablename__ = "incidents"
    id       = db.Column(db.String(16), primary_key=True)
    ref_id   = db.Column(db.String(16), index=True)
    tipo     = db.Column(db.String(40))
    descricao= db.Column(db.Text)
    status   = db.Column(db.String(20), default="Aberto")
    data     = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {"id":self.id,"refId":self.ref_id,"tipo":self.tipo,"descricao":self.descricao,
                "status":self.status,"data":self.data.isoformat() if self.data else None}


class MaintenanceOrder(db.Model):
    """Ordem de Serviço de manutenção de um ativo."""
    __tablename__ = "maintenance_orders"
    id                = db.Column(db.String(16), primary_key=True)
    asset_id          = db.Column(db.String(16), db.ForeignKey("assets.id"))
    asset_nome        = db.Column(db.String(200))
    tipo              = db.Column(db.String(40), default="Corretiva")
    status            = db.Column(db.String(30), default="Aberta")
    status_anterior   = db.Column(db.String(30), default="Disponível")
    descricao_defeito = db.Column(db.Text)
    diagnostico       = db.Column(db.Text)
    tecnico           = db.Column(db.String(120))
    data_abertura     = db.Column(db.String(10))
    data_conclusao    = db.Column(db.String(10))
    custo_total       = db.Column(db.Float, default=0.0)
    observacao        = db.Column(db.Text)
    attachments       = db.Column(db.JSON, default=list)
    parts             = db.relationship("MaintenancePart", backref="order",
                                        cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_parts=False):
        d = {"id": self.id, "assetId": self.asset_id, "assetNome": self.asset_nome,
             "tipo": self.tipo, "status": self.status, "statusAnterior": self.status_anterior,
             "descricaoDefeito": self.descricao_defeito, "diagnostico": self.diagnostico,
             "tecnico": self.tecnico, "dataAbertura": self.data_abertura,
             "dataConclusao": self.data_conclusao, "custoTotal": self.custo_total,
             "observacao": self.observacao, "attachments": self.attachments}
        if include_parts:
            d["pecas"] = [p.to_dict() for p in self.parts]
        return d


class MaintenancePart(db.Model):
    """Peça ou insumo consumido em uma OS de manutenção."""
    __tablename__ = "maintenance_parts"
    id             = db.Column(db.String(20), primary_key=True)
    maintenance_id = db.Column(db.String(16), db.ForeignKey("maintenance_orders.id"))
    supply_id      = db.Column(db.String(16))
    supply_nome    = db.Column(db.String(120))
    quantidade     = db.Column(db.Integer, default=1)
    custo_unitario = db.Column(db.Float, default=0.0)

    def to_dict(self):
        return {"id": self.id, "supplyId": self.supply_id, "nome": self.supply_nome,
                "quantidade": self.quantidade, "custoUnitario": self.custo_unitario,
                "custoTotal": round(self.quantidade * self.custo_unitario, 2)}


class AuditLog(db.Model):
    """Log imutável de todas as ações do sistema."""
    __tablename__ = "audit_logs"
    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario   = db.Column(db.String(80))
    acao      = db.Column(db.String(60))
    modulo    = db.Column(db.String(40))
    ref_id    = db.Column(db.String(120), index=True)
    detalhe   = db.Column(db.Text)
    ip        = db.Column(db.String(50))
    data      = db.Column(db.DateTime, default=datetime.now, index=True)

    def to_dict(self):
        return {"id":self.id,"usuario":self.usuario,"acao":self.acao,"modulo":self.modulo,
                "refId":self.ref_id,"detalhe":self.detalhe,"ip":self.ip,
                "data":self.data.isoformat() if self.data else None}


class AuditCampaign(db.Model):
    """Campanha de conferência física de ativos por unidade/setor."""
    __tablename__ = "audit_campaigns"
    id             = db.Column(db.String(16), primary_key=True)
    nome           = db.Column(db.String(120), nullable=False)
    unidade        = db.Column(db.String(80), default="")
    setor          = db.Column(db.String(80), default="")
    status         = db.Column(db.String(20), default="Aberta")
    data_inicio    = db.Column(db.String(10), default=lambda: str(date.today()))
    data_fim       = db.Column(db.String(10))
    criado_por     = db.Column(db.String(80), default="")
    criado_em      = db.Column(db.DateTime, default=datetime.now)
    observacao     = db.Column(db.Text, default="")
    items          = db.relationship("AuditCampaignItem", backref="campaign",
                                     cascade="all, delete-orphan", lazy=True)

    def to_dict(self, include_items=False):
        counts = {}
        for i in self.items:
            counts[i.status] = counts.get(i.status, 0) + 1
        total = len(self.items)
        conferidos  = counts.get("Conferido", 0)
        divergentes = counts.get("Divergente", 0)
        extras      = counts.get("Extra", 0)
        pendentes    = counts.get("Pendente", 0)
        auditados    = max(0, total - pendentes)
        d = {
            "id": self.id, "nome": self.nome, "unidade": self.unidade,
            "setor": self.setor, "status": self.status,
            "dataInicio": self.data_inicio, "dataFim": self.data_fim,
            "criadoPor": self.criado_por, "criadoEm": self.criado_em.isoformat() if self.criado_em else None,
            "observacao": self.observacao,
            "stats": {
                "total": total, "conferidos": conferidos,
                "pendentes": pendentes, "auditados": auditados,
                "divergentes": divergentes, "extras": extras,
                "progresso": round((auditados / total) * 100) if total else 0,
            },
        }
        if include_items:
            d["items"] = [i.to_dict() for i in self.items]
        return d


class AuditCampaignItem(db.Model):
    __tablename__ = "audit_campaign_items"
    id                    = db.Column(db.String(20), primary_key=True)
    campaign_id           = db.Column(db.String(16), db.ForeignKey("audit_campaigns.id"), nullable=False)
    asset_id              = db.Column(db.String(16), db.ForeignKey("assets.id"))
    asset_nome            = db.Column(db.String(200))
    patrimonio            = db.Column(db.String(40))
    service_tag           = db.Column(db.String(40))
    expected_unidade      = db.Column(db.String(80), default="")
    expected_setor        = db.Column(db.String(80), default="")
    expected_colaborador  = db.Column(db.String(120), default="")
    observed_unidade      = db.Column(db.String(80), default="")
    observed_setor        = db.Column(db.String(80), default="")
    observed_local        = db.Column(db.String(120), default="")
    observed_responsavel  = db.Column(db.String(120), default="")
    status                = db.Column(db.String(20), default="Pendente")
    divergencia           = db.Column(db.Text, default="")
    observacao            = db.Column(db.Text, default="")
    auditado_por          = db.Column(db.String(80), default="")
    auditado_em           = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id, "campaignId": self.campaign_id, "assetId": self.asset_id,
            "assetNome": self.asset_nome, "patrimonio": self.patrimonio,
            "serviceTag": self.service_tag,
            "expectedUnidade": self.expected_unidade,
            "expectedSetor": self.expected_setor,
            "expectedColaborador": self.expected_colaborador,
            "observedUnidade": self.observed_unidade,
            "observedSetor": self.observed_setor,
            "observedLocal": self.observed_local,
            "observedResponsavel": self.observed_responsavel,
            "status": self.status, "divergencia": self.divergencia,
            "observacao": self.observacao, "auditadoPor": self.auditado_por,
            "auditadoEm": self.auditado_em.isoformat() if self.auditado_em else None,
        }


class Attachment(db.Model):
    """Arquivo anexado a ativos, ordens de manutenção ou licenças."""
    __tablename__ = "attachments"
    id            = db.Column(db.String(20), primary_key=True)
    entity_type   = db.Column(db.String(30), nullable=False, index=True)
    entity_id     = db.Column(db.String(16), nullable=False, index=True)
    original_name = db.Column(db.String(180), nullable=False)
    stored_name   = db.Column(db.String(220), nullable=False)
    content_type  = db.Column(db.String(120), default="application/octet-stream")
    size          = db.Column(db.Integer, default=0)
    category      = db.Column(db.String(40), default="Documento")
    description   = db.Column(db.Text, default="")
    uploaded_by   = db.Column(db.String(80), default="")
    uploaded_at   = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id, "entityType": self.entity_type, "entityId": self.entity_id,
            "originalName": self.original_name, "contentType": self.content_type,
            "size": self.size, "category": self.category, "description": self.description,
            "uploadedBy": self.uploaded_by,
            "uploadedAt": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


class Setting(db.Model):
    """Configurações key-value JSON."""
    __tablename__ = "settings"
    key   = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text)


class LoginAttempt(db.Model):
    """Tentativas de login — persiste entre workers para rate-limiting real."""
    __tablename__ = "login_attempts"
    id        = db.Column(db.Integer, primary_key=True, autoincrement=True)
    ip        = db.Column(db.String(50), nullable=False, index=True)
    timestamp = db.Column(db.Float, nullable=False)
    success   = db.Column(db.Boolean, default=False)


class Devolucao(db.Model):
    """Evento de devolução de equipamentos — captura assinatura digital do colaborador."""
    __tablename__ = "devolucoes"
    id                    = db.Column(db.String(16), primary_key=True)
    colaborador_id        = db.Column(db.String(16), db.ForeignKey("colaboradores.id"), nullable=True)
    colaborador           = db.Column(db.String(120), nullable=False)
    setor                 = db.Column(db.String(80), default="")
    unidade               = db.Column(db.String(80), default="")
    data_devolucao        = db.Column(db.String(10))
    sign_token            = db.Column(db.String(64), unique=True)
    sign_token_expiry     = db.Column(db.DateTime)
    assinatura_img        = db.Column(db.Text)
    assinatura_ip         = db.Column(db.String(50))
    data_assinatura       = db.Column(db.DateTime)
    status                = db.Column(db.String(20), default="Pendente")
    ativos_devolvidos     = db.Column(db.Text, default="[]")
    perifericos_devolvidos= db.Column(db.Text, default="[]")
    laudo_status          = db.Column(db.String(30), default="Aguardando Laudo", index=True)
    rh_token              = db.Column(db.String(64), unique=True)
    rh_token_expiry       = db.Column(db.DateTime)
    rh_email              = db.Column(db.String(120))
    rh_ciencia_ip         = db.Column(db.String(50))
    rh_data_ciencia       = db.Column(db.DateTime)
    cobranca_aplicada     = db.Column(db.Boolean, nullable=True)
    cobranca_valor        = db.Column(db.Float, default=0.0)
    cobranca_obs          = db.Column(db.Text, default="")

    def to_dict(self):
        return {
            "id": self.id, "colaboradorId": self.colaborador_id,
            "colaborador": self.colaborador, "setor": self.setor, "unidade": self.unidade,
            "dataDevolucao": self.data_devolucao, "status": self.status,
            "dataAssinatura": self.data_assinatura.isoformat() if self.data_assinatura else None,
            "assinaturaIp": self.assinatura_ip,
            "hasAssinatura": bool(self.assinatura_img),
            "signTokenExpiry": self.sign_token_expiry.isoformat() if self.sign_token_expiry else None,
            "ativosDevolvidos": json.loads(self.ativos_devolvidos or "[]"),
            "perifericosDevolvidos": json.loads(self.perifericos_devolvidos or "[]"),
            "laudoStatus": self.laudo_status,
            "rhEmail": self.rh_email,
            "rhDataCiencia": self.rh_data_ciencia.isoformat() if self.rh_data_ciencia else None,
            "cobrancaAplicada": self.cobranca_aplicada,
            "cobrancaValor": self.cobranca_valor,
            "cobrancaObs": self.cobranca_obs,
        }


class LaudoTecnico(db.Model):
    """Avaliação técnica dos equipamentos no processo de desligamento."""
    __tablename__ = "laudos_tecnicos"
    id               = db.Column(db.String(16), primary_key=True)
    devolucao_id     = db.Column(db.String(16), db.ForeignKey("devolucoes.id"), nullable=False)
    tecnico          = db.Column(db.String(120), nullable=False)
    avaliacao_itens  = db.Column(db.Text, default="[]")
    observacao_geral = db.Column(db.Text, default="")
    tem_cobranca     = db.Column(db.Boolean, default=False)
    valor_cobranca   = db.Column(db.Float, default=0.0)
    data_avaliacao   = db.Column(db.DateTime, default=datetime.now)
    editado_em       = db.Column(db.DateTime, nullable=True)
    editado_por      = db.Column(db.String(120), nullable=True)
    motivo_edicao    = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "devolucaoId": self.devolucao_id,
            "tecnico": self.tecnico,
            "avaliacaoItens": json.loads(self.avaliacao_itens or "[]"),
            "observacaoGeral": self.observacao_geral,
            "temCobranca": self.tem_cobranca,
            "valorCobranca": self.valor_cobranca,
            "dataAvaliacao": self.data_avaliacao.isoformat() if self.data_avaliacao else None,
            "editadoEm": self.editado_em.isoformat() if self.editado_em else None,
            "editadoPor": self.editado_por,
            "motivoEdicao": self.motivo_edicao,
        }


class TermoAvulso(db.Model):
    """Termo avulso não vinculado a ativo físico — VPN, BYOD, Confidencialidade, etc."""
    __tablename__ = "termos_avulsos"
    id                = db.Column(db.String(16), primary_key=True)
    tipo              = db.Column(db.String(40))
    colaborador       = db.Column(db.String(120))
    setor             = db.Column(db.String(80))
    unidade           = db.Column(db.String(80))
    email             = db.Column(db.String(120))
    detalhes          = db.Column(db.Text)
    validade          = db.Column(db.String(10))
    status            = db.Column(db.String(20), default="Pendente")
    sign_token        = db.Column(db.String(64), unique=True)
    sign_token_expiry = db.Column(db.DateTime)
    package_id        = db.Column(db.String(16), index=True)
    package_token     = db.Column(db.String(64), index=True)
    package_token_expiry = db.Column(db.DateTime)
    assinatura_img    = db.Column(db.Text)
    assinatura_ip     = db.Column(db.String(50))
    data_assinatura   = db.Column(db.DateTime)
    created_at        = db.Column(db.DateTime, default=datetime.now)
    created_by        = db.Column(db.String(120))

    def to_dict(self):
        def iso(value):
            if not value:
                return None
            return value.isoformat() if hasattr(value, "isoformat") else str(value)

        details = json.loads(self.detalhes or "{}") if self.detalhes else {}
        public_details = {key: value for key, value in details.items() if not str(key).startswith("_")}
        return {
            "id": self.id,
            "tipo": self.tipo,
            "colaborador": self.colaborador,
            "setor": self.setor,
            "unidade": self.unidade,
            "email": self.email,
            "detalhes": public_details,
            "validade": self.validade,
            "status": self.status,
            "signTokenExpiry": iso(self.sign_token_expiry),
            "packageId": self.package_id,
            "packageTokenExpiry": iso(self.package_token_expiry),
            "hasSignImg": bool(self.assinatura_img),
            "assinaturaIp": self.assinatura_ip,
            "dataAssinatura": iso(self.data_assinatura),
            "createdAt": iso(self.created_at),
            "createdBy": self.created_by,
        }


PERFIL_PERMISSOES = {
    "Administrador": {
        "label":"Acesso total ao sistema","cor":"red",
        "modulos":["dashboard","ativos","insumos","compras","colaboradores","alocacoes",
                   "auditorias","qrcode","licencas","alertas","manutencao","system_users","configuracoes"],
        "pode_editar":True,"pode_excluir":True,"pode_exportar":True,
    },
    "Técnico TI": {
        "label":"Gestão operacional de TI","cor":"blue",
        "modulos":["dashboard","ativos","insumos","compras","alocacoes","auditorias","qrcode","alertas","colaboradores","manutencao"],
        "pode_editar":True,"pode_excluir":False,"pode_exportar":True,
    },
    "Gestor": {
        "label":"Visualização gerencial e relatórios","cor":"amber",
        "modulos":["dashboard","ativos","auditorias","colaboradores","licencas","alertas"],
        "pode_editar":False,"pode_excluir":False,"pode_exportar":True,
    },
    "Visualizador": {
        "label":"Somente leitura","cor":"gray",
        "modulos":["dashboard","alertas"],
        "pode_editar":False,"pode_excluir":False,"pode_exportar":False,
    },
}


__all__ = [
    "ASSET_STATUS_VALID",
    "PERFIL_PERMISSOES",
    "Allocation",
    "AllocationItem",
    "Asset",
    "Attachment",
    "AuditCampaign",
    "AuditCampaignItem",
    "AuditLog",
    "Colaborador",
    "Devolucao",
    "Incident",
    "LaudoTecnico",
    "License",
    "LoginAttempt",
    "MaintenanceOrder",
    "MaintenancePart",
    "PrintJob",
    "PrintPrinter",
    "Setting",
    "Supply",
    "SupplyMovement",
    "SystemUser",
    "TermoAvulso",
]

