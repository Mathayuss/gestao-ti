"""Defaults iniciais de configuracao do sistema."""
from copy import deepcopy

from models import PERFIL_PERMISSOES
from services.backup_service import DEFAULT_BACKUP_CONFIG
from services.email_service import DEFAULT_EMAIL_TEMPLATES
from services.settings_schema_service import (
    CATEGORIAS_DEFAULT,
    CATEGORIAS_INSUMOS_DEFAULT,
    default_termo_avulso_modelo,
)
from services.validation_service import clean_text


def company_defaults(empresa=None):
    empresa = empresa if isinstance(empresa, dict) else {}
    return {
        "nome": clean_text(empresa.get("nome") or "TI Control", 120),
        "cnpj": clean_text(empresa.get("cnpj"), 30),
        "email": clean_text(empresa.get("email"), 120),
        "telefone": clean_text(empresa.get("telefone"), 40),
        "site": clean_text(empresa.get("site"), 120),
        "endereco": clean_text(empresa.get("endereco"), 240),
        "logo_base64": "",
    }


def termo_recebimento_default():
    return {
        "titulo": "TERMO DE RESPONSABILIDADE DE EQUIPAMENTO",
        "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido os seguintes equipamentos de propriedade da empresa:",
        "clausulas": [
            "Comprometo-me a:",
            "  1. Utilizar exclusivamente para fins profissionais;",
            "  2. Zelar pela conservação de todos os itens;",
            "  3. Comunicar ao TI qualquer dano, perda ou furto;",
            "  4. Devolver os equipamentos ao encerramento do vínculo.",
        ],
        "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
    }


def termo_devolucao_default():
    return {
        "titulo": "TERMO DE DEVOLUÇÃO DE EQUIPAMENTOS",
        "preambulo": "Atestamos a devolução dos equipamentos abaixo pelo(a) colaborador(a) {colaborador},\ndo setor {setor}, unidade {unidade}:",
        "clausulas": [],
        "declaracao": "Declaro ter devolvido todos os equipamentos listados acima em plenas condições.",
        "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
    }


def termo_emprestimo_default():
    return {
        "titulo": "TERMO DE EMPRÉSTIMO DE EQUIPAMENTO",
        "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro ter recebido em caráter de EMPRÉSTIMO TEMPORÁRIO o equipamento abaixo:",
        "clausulas": [
            "Comprometo-me a:",
            "  1. Utilizar exclusivamente para fins profissionais durante o período de empréstimo;",
            "  2. Zelar pela conservação do equipamento;",
            "  3. Devolver o equipamento na data prevista ou quando solicitado pelo setor de TI;",
            "  4. Comunicar imediatamente ao TI qualquer dano, perda ou furto.",
        ],
        "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
    }


def termo_vpn_default():
    return {
        "titulo": "TERMO DE ACESSO VPN / USO REMOTO",
        "preambulo": "Eu, {colaborador}, lotado(a) no setor de {setor}, unidade {unidade},\ndeclaro estar ciente das regras de acesso à VPN corporativa:",
        "clausulas": [
            "1. O acesso VPN é pessoal e intransferível;",
            "2. É proibido compartilhar credenciais com terceiros;",
            "3. O colaborador é responsável por todos os acessos realizados com suas credenciais;",
            "4. O uso deve ser restrito a atividades profissionais autorizadas;",
            "5. O descumprimento sujeita o colaborador a medidas disciplinares.",
        ],
        "rodape": "{empresa} — Termo gerado automaticamente pelo sistema de gestão de TI",
    }


def categorias_config_default():
    return {
        "Notebook": {"tipo_alocacao": "colaborador"},
        "Desktop": {"tipo_alocacao": "colaborador"},
        "Monitor": {"tipo_alocacao": "colaborador"},
        "Smartphone": {"tipo_alocacao": "colaborador"},
        "Dock Station": {"tipo_alocacao": "colaborador"},
        "Tablet": {"tipo_alocacao": "colaborador"},
        "Impressora": {"tipo_alocacao": "unidade"},
        "Switch": {"tipo_alocacao": "unidade"},
        "Firewall": {"tipo_alocacao": "unidade"},
        "Access Point": {"tipo_alocacao": "unidade"},
        "Servidor": {"tipo_alocacao": "unidade"},
        "Storage": {"tipo_alocacao": "unidade"},
        "Rack": {"tipo_alocacao": "unidade"},
        "Nobreak": {"tipo_alocacao": "unidade"},
        "DVR": {"tipo_alocacao": "unidade"},
        "NVR": {"tipo_alocacao": "unidade"},
        "Câmera IP": {"tipo_alocacao": "unidade"},
    }


def new_term_settings_defaults():
    return {
        "termo_emprestimo": termo_emprestimo_default(),
        "termo_vpn": termo_vpn_default(),
    }


def initial_settings_defaults(empresa=None):
    defaults = {
        "empresa": company_defaults(empresa),
        "termo_recebimento": termo_recebimento_default(),
        "termo_devolucao": termo_devolucao_default(),
        "termo_emprestimo": termo_emprestimo_default(),
        "termo_vpn": termo_vpn_default(),
        "termos_avulsos_tipos": ["VPN", "BYOD", "Confidencialidade", "Outro"],
        "termos_avulsos_modelos": {
            "VPN": default_termo_avulso_modelo("VPN"),
            "BYOD": default_termo_avulso_modelo("BYOD"),
            "Confidencialidade": default_termo_avulso_modelo("Confidencialidade"),
            "Outro": default_termo_avulso_modelo("Outro"),
        },
        "email_templates": DEFAULT_EMAIL_TEMPLATES,
        "backup": DEFAULT_BACKUP_CONFIG,
        "setores": ["TI", "Financeiro", "RH", "Vendas", "Marketing", "Operações"],
        "unidades": [],
        "alertas": {"dias_garantia": 60, "dias_licenca": 60, "estoque_minimo": True, "notif_email": False},
        "regras_usuario": {
            "exige_termo_alocacao": True,
            "permite_alocar_sem_email": False,
            "max_perifericos_por_colab": 10,
            "obriga_vinculo_saida": True,
        },
        "campos_ativo_obrigatorios": ["hostname", "fabricante", "modelo", "categoria", "patrimonio"],
        "categorias": CATEGORIAS_DEFAULT,
        "categorias_insumos": CATEGORIAS_INSUMOS_DEFAULT,
        "categorias_compat": {},
        "categorias_config": categorias_config_default(),
        "perfil_permissoes": PERFIL_PERMISSOES,
        "aparencia": {
            "nome_sistema": "TI Control",
            "slogan_sistema": "Gestão de Ativos de TI",
            "cor_primaria": "#2563eb",
            "cor_botao": "#2563eb",
            "cor_hover": "#eff6ff",
            "login_box_transparencia": 0,
        },
    }
    return deepcopy(defaults)


def demo_settings_defaults():
    defaults = {
        "empresa": {
            "nome": "Empresa Tecnologia SA",
            "cnpj": "12.345.678/0001-90",
            "email": "ti@empresa.com",
            "telefone": "(11) 3000-0000",
            "site": "www.empresa.com.br",
            "endereco": "Av. Paulista, 1000 — São Paulo, SP",
            "logo_base64": "",
        },
        "termo_recebimento": termo_recebimento_default(),
        "termo_devolucao": termo_devolucao_default(),
        "email_templates": DEFAULT_EMAIL_TEMPLATES,
        "backup": DEFAULT_BACKUP_CONFIG,
        "setores": ["TI", "Financeiro", "RH", "Vendas", "Marketing", "Operações", "Jurídico"],
        "unidades": [
            {"id": "UN1", "nome": "Sede SP", "cidade": "São Paulo", "estado": "SP", "tipo": "Sede"},
            {"id": "UN2", "nome": "Filial RJ", "cidade": "Rio de Janeiro", "estado": "RJ", "tipo": "Filial"},
            {"id": "UN3", "nome": "Filial BH", "cidade": "Belo Horizonte", "estado": "MG", "tipo": "Filial"},
            {"id": "UN4", "nome": "Almoxarifado", "cidade": "São Paulo", "estado": "SP", "tipo": "Depósito"},
        ],
        "alertas": {"dias_garantia": 60, "dias_licenca": 60, "estoque_minimo": True, "notif_email": False},
        "regras_usuario": {
            "exige_termo_alocacao": True,
            "permite_alocar_sem_email": False,
            "max_perifericos_por_colab": 10,
            "obriga_vinculo_saida": True,
        },
        "campos_ativo_obrigatorios": ["hostname", "fabricante", "modelo", "categoria", "patrimonio"],
        "categorias_config": categorias_config_default(),
    }
    return deepcopy(defaults)
