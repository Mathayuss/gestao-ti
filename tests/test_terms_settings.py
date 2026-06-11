import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class TermSettingsTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True)
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_custom_term_models_are_independent_by_type(self):
        with tic.app.app_context():
            tic._set_setting("termos_avulsos_tipos", ["VPN", "BYOD"])
            tic._set_setting("termos_avulsos_modelos", {
                "VPN": {
                    "titulo": "TERMO VPN CUSTOM",
                    "preambulo": "VPN para {colaborador}",
                    "clausulas": ["Clausula VPN"],
                    "rodape": "Rodape VPN",
                },
                "BYOD": {
                    "titulo": "TERMO BYOD CUSTOM",
                    "preambulo": "BYOD para {colaborador}",
                    "clausulas": ["Clausula BYOD"],
                    "rodape": "Rodape BYOD",
                },
            })
            tic.db.session.commit()

            vpn = tic._get_termo_avulso_modelo("VPN")
            byod = tic._get_termo_avulso_modelo("BYOD")
            novo = tic._get_termo_avulso_modelo("Confidencialidade")

            self.assertEqual(vpn["titulo"], "TERMO VPN CUSTOM")
            self.assertEqual(byod["titulo"], "TERMO BYOD CUSTOM")
            self.assertNotEqual(vpn["clausulas"], byod["clausulas"])
            self.assertIn("CONFIDENCIALIDADE", novo["titulo"])

    def test_normalize_term_models_rejects_invalid_clauses(self):
        with tic.app.app_context():
            _, error = tic._normalize_termos_avulsos_modelos({"VPN": {"clausulas": "texto solto"}})

            self.assertEqual(error, "Cláusulas do termo 'VPN' precisam ser uma lista.")


if __name__ == "__main__":
    unittest.main()
