import unittest

from services.initial_settings_service import (
    company_defaults,
    demo_settings_defaults,
    initial_settings_defaults,
    new_term_settings_defaults,
)


class InitialSettingsServiceTest(unittest.TestCase):
    def test_company_defaults_normalizes_input(self):
        company = company_defaults({
            "nome": "  Empresa X  ",
            "email": " ti@example.com ",
            "telefone": " 123 ",
        })

        self.assertEqual(company["nome"], "Empresa X")
        self.assertEqual(company["email"], "ti@example.com")
        self.assertEqual(company["telefone"], "123")
        self.assertEqual(company["logo_base64"], "")

    def test_initial_settings_defaults_include_full_beta_settings(self):
        defaults = initial_settings_defaults({"nome": "Cliente Beta"})

        self.assertEqual(defaults["empresa"]["nome"], "Cliente Beta")
        self.assertIn("termo_recebimento", defaults)
        self.assertIn("termo_devolucao", defaults)
        self.assertIn("termo_emprestimo", defaults)
        self.assertIn("termo_vpn", defaults)
        self.assertIn("termos_avulsos_modelos", defaults)
        self.assertIn("perfil_permissoes", defaults)
        self.assertEqual(defaults["categorias_config"]["Notebook"]["tipo_alocacao"], "colaborador")
        self.assertEqual(defaults["categorias_config"]["Switch"]["tipo_alocacao"], "unidade")

    def test_initial_settings_defaults_are_deep_copied(self):
        first = initial_settings_defaults()
        first["categorias"].append("Mutacao")
        first["backup"]["enabled"] = True
        first["termos_avulsos_modelos"]["VPN"]["clausulas"].append("Mutacao")

        second = initial_settings_defaults()

        self.assertNotIn("Mutacao", second["categorias"])
        self.assertFalse(second["backup"]["enabled"])
        self.assertNotIn("Mutacao", second["termos_avulsos_modelos"]["VPN"]["clausulas"])

    def test_demo_settings_defaults_match_demo_seed_scope(self):
        defaults = demo_settings_defaults()

        self.assertEqual(defaults["empresa"]["nome"], "Empresa Tecnologia SA")
        self.assertIn("Jurídico", defaults["setores"])
        self.assertEqual(len(defaults["unidades"]), 4)
        self.assertIn("termo_recebimento", defaults)
        self.assertIn("termo_devolucao", defaults)
        self.assertNotIn("termo_emprestimo", defaults)
        self.assertNotIn("aparencia", defaults)

    def test_new_term_settings_defaults_are_centralized(self):
        defaults = new_term_settings_defaults()

        self.assertEqual(defaults["termo_emprestimo"]["titulo"], "TERMO DE EMPRÉSTIMO DE EQUIPAMENTO")
        self.assertEqual(defaults["termo_vpn"]["titulo"], "TERMO DE ACESSO VPN / USO REMOTO")


if __name__ == "__main__":
    unittest.main()
