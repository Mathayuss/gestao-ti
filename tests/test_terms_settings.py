import os
import tempfile
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
        os.environ.pop("SMTP_PASSWORD", None)
        os.environ.pop("SMTP_PASSWORD_FILE", None)
        os.environ.pop("SMTP_HOST", None)
        os.environ.pop("SMTP_ENABLED", None)
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

    def test_email_template_single_brace_tags_are_rendered(self):
        with tic.app.app_context():
            subject, html, text = tic._render_email_template("laudo_rh", {
                "empresa": "Platinaa",
                "colaborador": "Maria Silva",
                "tecnico": "Analista TI",
                "link": "https://ti.example/rh/laudo/token",
            })

            combined = subject + html + text
            self.assertIn("Analista TI", combined)
            self.assertIn("Maria Silva", combined)
            self.assertIn("Platinaa", combined)
            self.assertNotIn("{tecnico}", combined)
            self.assertNotIn("{colaborador}", combined)
            self.assertNotIn("{empresa}", combined)

    def test_render_text_keeps_jinja_style_support(self):
        rendered = tic._render_termo_text("Olá {{ colaborador }} de {empresa}", {
            "colaborador": "Ana",
            "empresa": "TI Control",
        })

        self.assertEqual(rendered, "Olá Ana de TI Control")

    def test_smtp_password_file_overrides_database_password(self):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as secret:
            secret.write("senha-via-secret\n")
            secret_path = secret.name
        self.addCleanup(lambda: os.path.exists(secret_path) and os.unlink(secret_path))

        os.environ["SMTP_PASSWORD_FILE"] = secret_path
        os.environ["SMTP_HOST"] = "smtp.example.com"
        os.environ["SMTP_ENABLED"] = "1"

        with tic.app.app_context():
            tic._set_setting("email.source", "env")
            tic._set_setting("email.password", "senha-do-banco")
            tic.db.session.commit()

            cfg = tic._get_email_config()

        self.assertEqual(cfg["password"], "senha-via-secret")
        self.assertEqual(cfg["source"], "env")


if __name__ == "__main__":
    unittest.main()
