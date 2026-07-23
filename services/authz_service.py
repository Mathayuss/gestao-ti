"""Regras de autorizacao e RBAC."""
from models import PERFIL_PERMISSOES


PERMISSION_MODULE_PREFIXES = (
    ("/api/assets", "ativos"),
    ("/api/allocations", "alocacoes"),
    ("/api/supplies", "insumos"),
    ("/api/colaboradores", "colaboradores"),
    ("/api/devolucoes", "colaboradores"),
    ("/api/licenses", "licencas"),
    ("/api/maintenance", "manutencao"),
    ("/api/incidents", "manutencao"),
    ("/api/audit-campaigns", "auditorias"),
    ("/api/audit-asset", "auditorias"),
    ("/api/audit-log", "auditorias"),
    ("/api/dashboard", "dashboard"),
    ("/api/alerts", "alertas"),
    ("/api/movements", "dashboard"),
    ("/api/system-users", "system_users"),
    ("/api/settings", "configuracoes"),
    ("/api/system/update", "configuracoes"),
    ("/api/backups", "configuracoes"),
    ("/api/backup.json", "configuracoes"),
    ("/api/export", "configuracoes"),
    ("/api/termos", "alocacoes"),
    ("/api/termos-avulsos", "alocacoes"),
    ("/api/emprestimos", "alocacoes"),
)

ATTACHMENT_MODULE_BY_ENTITY = {
    "asset": "ativos",
    "maintenance": "manutencao",
    "license": "licencas",
}


def permission_module_for_path(path):
    path = path or ""
    if path.startswith("/api/attachments/"):
        parts = path.split("/")
        if len(parts) > 3 and parts[3] != "files":
            return ATTACHMENT_MODULE_BY_ENTITY.get(parts[3])
        return None
    for prefix, module in PERMISSION_MODULE_PREFIXES:
        if path.startswith(prefix):
            return module
    return None


def permission_action_for_request(path, method):
    path = path or ""
    method = (method or "GET").upper()
    if path.startswith("/api/export") or path == "/api/backup.json":
        return "export"
    if method == "GET" and path.startswith("/api/backups/files"):
        return "export"
    if method == "DELETE":
        return "delete"
    if method in {"POST", "PUT", "PATCH"}:
        return "edit"
    return "view"


def profile_permissions(perfil, configured_permissions=None):
    configured = configured_permissions if isinstance(configured_permissions, dict) else PERFIL_PERMISSOES
    info = configured.get(perfil) or PERFIL_PERMISSOES.get(perfil) or {}
    return info if isinstance(info, dict) else {}


def profile_allows(perfil, module, action, configured_permissions=None):
    if perfil == "Administrador":
        return True
    info = profile_permissions(perfil, configured_permissions)
    if module and module not in (info.get("modulos") or []):
        return False
    if action == "view":
        return True
    if action == "edit":
        return bool(info.get("pode_editar"))
    if action == "delete":
        return bool(info.get("pode_excluir"))
    if action == "export":
        return bool(info.get("pode_exportar"))
    return False


def authorize_profile(perfil, status, path, method, required_profiles=(), configured_permissions=None):
    if status != "Ativo":
        return False, "Conta desativada", 403, None, None

    module = permission_module_for_path(path)
    action = permission_action_for_request(path, method)
    dynamic_allowed = bool(module and profile_allows(perfil, module, action, configured_permissions))
    fixed_allowed = not required_profiles or perfil in required_profiles

    if required_profiles and not fixed_allowed and not dynamic_allowed:
        return False, f"Perfil '{perfil}' sem acesso a esta ação", 403, module, action
    if module and not dynamic_allowed:
        return False, f"Perfil '{perfil}' sem permissão para {action} em {module}.", 403, module, action
    return True, "", 200, module, action
