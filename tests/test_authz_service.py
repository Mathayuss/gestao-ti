import unittest

from services.authz_service import (
    authorize_profile,
    permission_action_for_request,
    permission_module_for_path,
    profile_allows,
    profile_permissions,
)


class AuthzServiceTest(unittest.TestCase):
    def test_permission_module_for_regular_and_attachment_routes(self):
        self.assertEqual(permission_module_for_path("/api/assets/A1"), "ativos")
        self.assertEqual(permission_module_for_path("/api/maintenance/M1"), "manutencao")
        self.assertEqual(permission_module_for_path("/api/attachments/asset/A1"), "ativos")
        self.assertEqual(permission_module_for_path("/api/attachments/license/L1"), "licencas")
        self.assertIsNone(permission_module_for_path("/api/attachments/files/ATT1"))
        self.assertIsNone(permission_module_for_path("/api/desconhecido"))

    def test_permission_action_for_request(self):
        self.assertEqual(permission_action_for_request("/api/assets", "GET"), "view")
        self.assertEqual(permission_action_for_request("/api/assets", "POST"), "edit")
        self.assertEqual(permission_action_for_request("/api/assets/A1", "DELETE"), "delete")
        self.assertEqual(permission_action_for_request("/api/export/assets", "GET"), "export")
        self.assertEqual(permission_action_for_request("/api/backup.json", "GET"), "export")
        self.assertEqual(permission_action_for_request("/api/backups/files/x", "GET"), "export")

    def test_profile_permissions_fallback_and_profile_allows(self):
        self.assertEqual(profile_permissions("Perfil inexistente"), {})
        self.assertTrue(profile_allows("Administrador", "qualquer_modulo", "delete"))
        self.assertTrue(profile_allows("Técnico TI", "ativos", "edit"))
        self.assertFalse(profile_allows("Técnico TI", "ativos", "delete"))
        self.assertTrue(profile_allows("Gestor", "ativos", "export"))
        self.assertFalse(profile_allows("Gestor", "ativos", "edit"))
        self.assertFalse(profile_allows("Visualizador", "ativos", "view"))

    def test_custom_profile_permissions_are_used(self):
        configured = {
            "Operador": {
                "modulos": ["licencas"],
                "pode_editar": True,
                "pode_excluir": False,
                "pode_exportar": False,
            }
        }
        self.assertTrue(profile_allows("Operador", "licencas", "edit", configured))
        self.assertFalse(profile_allows("Operador", "ativos", "view", configured))

    def test_authorize_profile_preserves_dynamic_and_fixed_rules(self):
        allowed, error, status, module, action = authorize_profile(
            "Técnico TI", "Ativo", "/api/assets", "POST", ("Administrador",)
        )
        self.assertTrue(allowed)
        self.assertEqual((status, module, action), (200, "ativos", "edit"))
        self.assertEqual(error, "")

        allowed, error, status, module, action = authorize_profile(
            "Técnico TI", "Ativo", "/api/assets/A1", "DELETE", ("Administrador", "Técnico TI")
        )
        self.assertFalse(allowed)
        self.assertEqual(status, 403)
        self.assertEqual(module, "ativos")
        self.assertEqual(action, "delete")
        self.assertIn("sem permissão para delete em ativos", error)

    def test_authorize_profile_rejects_inactive_and_unknown_profile(self):
        allowed, error, status, module, action = authorize_profile(
            "Administrador", "Inativo", "/api/assets", "GET"
        )
        self.assertFalse(allowed)
        self.assertEqual((error, status, module, action), ("Conta desativada", 403, None, None))

        allowed, error, status, module, action = authorize_profile(
            "Visitante", "Ativo", "/api/settings", "GET", ("Administrador",)
        )
        self.assertFalse(allowed)
        self.assertEqual(status, 403)
        self.assertEqual((module, action), ("configuracoes", "view"))
        self.assertIn("sem acesso a esta ação", error)


if __name__ == "__main__":
    unittest.main()
