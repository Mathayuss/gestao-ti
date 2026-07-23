"""Normalizacao e defaults de configuracoes do sistema."""
import base64
import re

from services.validation_service import clean_text, parse_bool, parse_int, validate_email


ASSET_REQUIRED_FIELDS_ALLOWED = {
    "hostname", "ip", "mac", "serviceTag", "os", "fabricante", "modelo",
    "patrimonio", "nf", "categoria", "status", "colaborador", "setor",
    "unidade", "garantia",
}

APARENCIA_LOGO_MAX_BYTES = 300 * 1024
APARENCIA_BG_MAX_BYTES = 8 * 1024 * 1024
APARENCIA_LOGO_MIMES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
APARENCIA_BG_MIMES = {"image/png", "image/jpeg", "image/webp"}
ASSET_CATEGORY_IMAGE_MAX_BYTES = 1024 * 1024
ASSET_CATEGORY_IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}

CATEGORIAS_DEFAULT = [
    "Notebook", "Desktop", "Monitor", "Smartphone", "Dock Station",
    "Switch", "Firewall", "Access Point", "Servidor", "Storage",
    "Rack", "Nobreak", "DVR", "NVR", "Câmera IP", "Tablet", "Impressora",
]

CATEGORIAS_INSUMOS_DEFAULT = [
    "Periférico", "Cabo", "Insumo", "Componente",
    "Toner", "Papel", "Bateria", "Adaptador",
]


def clean_list_setting(values, max_len=80):
    if not isinstance(values, list):
        return None
    cleaned, seen = [], set()
    for raw in values:
        item = clean_text(raw, max_len)
        key = item.casefold()
        if item and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned


def normalize_empresa_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Dados da empresa precisam ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    fields = {
        "nome": 120, "cnpj": 30, "email": 120, "telefone": 40,
        "site": 120, "endereco": 240, "logo_base64": None,
    }
    for key, max_len in fields.items():
        if key in value:
            result[key] = clean_text(value.get(key), max_len)
    err_email = validate_email(result.get("email"))
    if err_email:
        return None, err_email
    return result, None


def normalize_alertas_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Configurações de alertas precisam ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    if "dias_garantia" in value:
        result["dias_garantia"] = parse_int(value.get("dias_garantia"), default=60, minimum=1)
    if "dias_licenca" in value:
        result["dias_licenca"] = parse_int(value.get("dias_licenca"), default=60, minimum=1)
    if "estoque_minimo" in value:
        result["estoque_minimo"] = parse_bool(value.get("estoque_minimo"), default=True)
    if "notif_email" in value:
        result["notif_email"] = parse_bool(value.get("notif_email"), default=False)
    return result, None


def normalize_regras_usuario_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Regras de operação precisam ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    for key in ("exige_termo_alocacao", "permite_alocar_sem_email", "obriga_vinculo_saida"):
        if key in value:
            result[key] = parse_bool(value.get(key), default=bool(result.get(key)))
    if "max_perifericos_por_colab" in value:
        result["max_perifericos_por_colab"] = parse_int(
            value.get("max_perifericos_por_colab"), default=10, minimum=0
        )
    return result, None


def normalize_campos_ativos_setting(value):
    fields = clean_list_setting(value, max_len=40)
    if fields is None:
        return None, "Campos obrigatórios de ativo precisam ser uma lista."
    invalid = [field for field in fields if field not in ASSET_REQUIRED_FIELDS_ALLOWED]
    if invalid:
        return None, "Campos obrigatórios inválidos: " + ", ".join(invalid)
    return fields, None


def validate_data_image(value, allowed_mimes, max_bytes, label):
    if not value:
        return None
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    match = re.match(r"^data:([^;,]+);base64,(.*)$", value, flags=re.S)
    if not match:
        return f"{label} inválida."
    mime = match.group(1).lower()
    if mime not in allowed_mimes:
        return f"{label} deve ser PNG, JPG" + (", WEBP ou SVG." if "image/svg+xml" in allowed_mimes else " ou WEBP.")
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except Exception:
        return f"{label} inválida."
    if len(raw) > max_bytes:
        limit = max_bytes // (1024 * 1024) if max_bytes >= 1024 * 1024 else max_bytes // 1024
        unit = "MB" if max_bytes >= 1024 * 1024 else "KB"
        return f"{label} excede o limite de {limit} {unit}."
    return None


def normalize_categorias_config_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Configuração de categorias precisa ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    for raw_cat, cfg in value.items():
        cat = clean_text(raw_cat, 40)
        if not cat:
            continue
        cfg = cfg if isinstance(cfg, dict) else {}
        tipo = clean_text(cfg.get("tipo_alocacao"), 20)
        if tipo not in ("colaborador", "unidade"):
            return None, f"Tipo de alocação inválido para categoria '{cat}'."
        current_cat = result.get(cat) if isinstance(result.get(cat), dict) else {}
        image = clean_text(cfg.get("image", current_cat.get("image", "")), None)
        if image:
            if not image.startswith("data:"):
                return None, f"Imagem da categoria '{cat}' inválida."
            err = validate_data_image(
                image,
                ASSET_CATEGORY_IMAGE_MIMES,
                ASSET_CATEGORY_IMAGE_MAX_BYTES,
                f"Imagem da categoria '{cat}'",
            )
            if err:
                return None, err
        result[cat] = {"tipo_alocacao": tipo}
        if image:
            result[cat]["image"] = image
    return result, None


def normalize_unidade_payload(payload, current=None):
    if not isinstance(payload, dict):
        return None, "Dados da unidade precisam ser um objeto."
    current = current if isinstance(current, dict) else {}
    result = dict(current)
    fields = {"nome": 80, "tipo": 40, "cep": 9, "cidade": 80, "estado": 2}
    for key, max_len in fields.items():
        if key in payload or key not in result:
            result[key] = clean_text(payload.get(key, result.get(key, "")), max_len)
    result["estado"] = clean_text(result.get("estado"), 2).upper()
    if "id" in current:
        result["id"] = current["id"]
    if not result.get("nome"):
        return None, "Nome da unidade é obrigatório."
    return result, None


def normalize_termo_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Personalização de termo precisa ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    text_fields = {"titulo": 160, "preambulo": 3000, "rodape": 500, "declaracao": 1200}
    for field, max_len in text_fields.items():
        if field in value:
            result[field] = clean_text(value.get(field), max_len)
    if "clausulas" in value:
        clauses = clean_list_setting(value.get("clausulas"), max_len=1000)
        if clauses is None:
            return None, "Cláusulas do termo precisam ser uma lista."
        result["clausulas"] = clauses
    return result, None


def default_termo_avulso_modelo(tipo):
    tipo = clean_text(tipo, 60) or "Termo"
    tipo_upper = tipo.upper()
    base = {
        "titulo": f"TERMO DE {tipo_upper}",
        "preambulo": (
            "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente "
            "e de acordo com as regras referentes a {tipo}, com validade até {validade}."
        ),
        "clausulas": [
            "O recurso, acesso ou obrigação descrito neste termo é pessoal e intransferível.",
            "O uso deve respeitar as políticas internas, normas de segurança da informação e orientações da área de TI.",
            "O descumprimento das regras poderá resultar em revogação do acesso e medidas administrativas cabíveis.",
        ],
        "rodape": "{empresa} — Termo {tipo} emitido em {data} pelo Sistema de Gestão de TI",
    }
    if tipo.casefold() == "vpn":
        base.update({
            "titulo": "TERMO DE ACESSO VPN / USO REMOTO",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro estar ciente "
                "das regras para uso de VPN corporativa, com validade até {validade}."
            ),
            "clausulas": [
                "O acesso VPN é pessoal, intransferível e deve ser utilizado apenas para atividades profissionais autorizadas.",
                "É proibido compartilhar credenciais, tokens, certificados ou qualquer meio de autenticação com terceiros.",
                "O colaborador é responsável pelos acessos realizados com suas credenciais e deve comunicar suspeitas de uso indevido imediatamente.",
                "A empresa poderá revogar o acesso a qualquer momento por motivo de segurança, desligamento, mudança de função ou fim da necessidade operacional.",
            ],
        })
    elif tipo.casefold() == "byod":
        base.update({
            "titulo": "TERMO DE USO DE DISPOSITIVO PESSOAL (BYOD)",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, solicito ou autorizo o uso "
                "de dispositivo pessoal para atividades profissionais conforme as condições abaixo."
            ),
            "clausulas": [
                "O dispositivo pessoal deve manter bloqueio de tela, sistema atualizado e recursos mínimos de segurança definidos pela TI.",
                "Dados corporativos acessados no dispositivo não podem ser compartilhados, copiados para locais não autorizados ou expostos a terceiros.",
                "A empresa poderá remover acessos corporativos do dispositivo quando houver desligamento, incidente de segurança ou fim da necessidade de uso.",
            ],
        })
    elif "confidencial" in tipo.casefold():
        base.update({
            "titulo": "TERMO DE CONFIDENCIALIDADE",
            "preambulo": (
                "Eu, {colaborador}, do setor {setor}, unidade {unidade}, declaro ciência sobre "
                "minhas responsabilidades de sigilo e proteção das informações corporativas."
            ),
            "clausulas": [
                "Informações internas, credenciais, documentos, dados de clientes e dados operacionais devem ser tratados como confidenciais.",
                "É proibida a divulgação, cópia, envio ou armazenamento de informações corporativas em meios não autorizados.",
                "A obrigação de confidencialidade permanece válida mesmo após mudança de função, encerramento de acesso ou desligamento.",
            ],
        })
    return base


def normalize_termos_avulsos_modelos(value):
    if not isinstance(value, dict):
        return None, "Modelos de termos precisam ser um objeto."
    result = {}
    for raw_tipo, raw_model in value.items():
        tipo = clean_text(raw_tipo, 60)
        if not tipo:
            continue
        if not isinstance(raw_model, dict):
            return None, f"Modelo do termo '{tipo}' precisa ser um objeto."
        model = dict(default_termo_avulso_modelo(tipo))
        text_fields = {"titulo": 160, "preambulo": 3000, "rodape": 500, "declaracao": 1200}
        for field, max_len in text_fields.items():
            if field in raw_model:
                model[field] = clean_text(raw_model.get(field), max_len)
        if "clausulas" in raw_model:
            clauses = clean_list_setting(raw_model.get("clausulas"), max_len=1000)
            if clauses is None:
                return None, f"Cláusulas do termo '{tipo}' precisam ser uma lista."
            model["clausulas"] = clauses
        result[tipo] = model
    return result, None


def merge_termos_avulsos_modelos(tipos, saved):
    tipos = clean_list_setting(tipos, 60) or ["VPN", "BYOD", "Confidencialidade", "Outro"]
    saved = saved if isinstance(saved, dict) else {}
    result = {}
    for tipo in tipos:
        defaults = default_termo_avulso_modelo(tipo)
        custom = saved.get(tipo) if isinstance(saved.get(tipo), dict) else {}
        result[tipo] = {**defaults, **custom}
        if not isinstance(result[tipo].get("clausulas"), list):
            result[tipo]["clausulas"] = defaults["clausulas"]
    for tipo, custom in saved.items():
        tipo = clean_text(tipo, 60)
        if tipo and tipo not in result and isinstance(custom, dict):
            defaults = default_termo_avulso_modelo(tipo)
            result[tipo] = {**defaults, **custom}
            if not isinstance(result[tipo].get("clausulas"), list):
                result[tipo]["clausulas"] = defaults["clausulas"]
    return result


def get_termo_avulso_modelo(tipo, modelos=None):
    tipo = clean_text(tipo, 60)
    modelos = modelos if isinstance(modelos, dict) else {}
    return modelos.get(tipo) or default_termo_avulso_modelo(tipo)


def normalize_aparencia_setting(value, current=None):
    if not isinstance(value, dict):
        return None, "Configurações de aparência precisam ser um objeto."
    result = dict(current) if isinstance(current, dict) else {}
    for key, max_len in (("nome_sistema", 80), ("slogan_sistema", 120)):
        if key in value:
            result[key] = clean_text(value.get(key), max_len)
    for key in ("logo_sistema", "favicon", "bg_login"):
        if key in value:
            v = clean_text(value.get(key), None)
            err = validate_data_image(
                v,
                APARENCIA_BG_MIMES if key == "bg_login" else APARENCIA_LOGO_MIMES,
                APARENCIA_BG_MAX_BYTES if key == "bg_login" else APARENCIA_LOGO_MAX_BYTES,
                "Imagem de fundo" if key == "bg_login" else ("Favicon" if key == "favicon" else "Logo do sistema"),
            )
            if err:
                return None, err
            result[key] = v
    for key in ("cor_primaria", "cor_botao", "cor_hover"):
        if key in value:
            v = clean_text(value.get(key), 20)
            if v and not re.match(r'^#[0-9a-fA-F]{3,8}$', v):
                return None, f"Cor inválida para '{key}': use formato #RRGGBB."
            result[key] = v
    if "login_box_transparencia" in value:
        try:
            result["login_box_transparencia"] = max(0, min(100, int(value["login_box_transparencia"])))
        except (TypeError, ValueError):
            result["login_box_transparencia"] = 0
    return result, None


def normalize_patrimonio_prefixo(value):
    v = clean_text(value, 10)
    if not v:
        return None, "Prefixo de patrimônio não pode ser vazio."
    v = re.sub(r"[^A-Za-z0-9]", "", v).upper()
    if not v:
        return None, "Prefixo deve conter letras ou números."
    return v, None


def normalize_categorias_list_setting(value):
    if not isinstance(value, list):
        return None, "Categorias deve ser uma lista."
    cats = []
    for v in value:
        c = clean_text(v, 60)
        if c and c not in cats:
            cats.append(c)
    if not cats:
        return None, "A lista de categorias não pode ser vazia."
    return cats, None


def normalize_categorias_compat_setting(value):
    if not isinstance(value, dict):
        return None, "Compatibilidade deve ser um objeto."
    result = {}
    for raw_cat, supply_cats in value.items():
        cat = clean_text(raw_cat, 60)
        if not cat:
            continue
        if not isinstance(supply_cats, list):
            return None, f"Lista de insumos inválida para categoria '{cat}'."
        result[cat] = [c for c in (clean_text(v, 60) for v in supply_cats) if c]
    return result, None
