import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
            user = tic.SystemUser(
                id="U_SETTINGS",
                username="admin",
                nome="Admin",
                perfil="Administrador",
                status="Ativo",
            )
            user.set_senha("secret123")
            tic.db.session.add(user)
            tic.db.session.commit()
        self.client.post("/login", data={"username": "admin", "senha": "secret123"})

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_update_settings_uses_schema_normalizers(self):
        response = self.client.put("/api/settings", json={
            "alertas": {"dias_garantia": "0", "notif_email": "sim"},
            "patrimonio.prefixo": " ti-01 ",
            "categorias": ["Notebook", "Notebook", "Monitor"],
        })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["alertas"]["dias_garantia"], 1)
        self.assertTrue(payload["alertas"]["notif_email"])
        self.assertEqual(payload["patrimonio_prefixo"], "TI01")
        self.assertEqual(payload["categorias"], ["Notebook", "Monitor"])

    def test_update_settings_rejects_unsupported_and_invalid_payload(self):
        unsupported = self.client.put("/api/settings", json={"nao_existe": True})
        self.assertEqual(unsupported.status_code, 400)
        self.assertEqual(unsupported.get_json()["error"], "Configuração não suportada.")

        invalid = self.client.put("/api/settings", json={"aparencia": {"cor_hover": "blue"}})
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(
            invalid.get_json()["error"],
            "Cor inválida para 'cor_hover': use formato #RRGGBB.",
        )


if __name__ == "__main__":
    unittest.main()
