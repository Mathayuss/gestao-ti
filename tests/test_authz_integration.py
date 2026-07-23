import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class AuthzIntegrationTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def _create_user(self, username, perfil, status="Ativo"):
        user = tic.SystemUser(
            id=f"U_{username.upper()}",
            username=username,
            nome=username.title(),
            perfil=perfil,
            status=status,
        )
        user.set_senha("secret123")
        tic.db.session.add(user)
        tic.db.session.commit()

    def _login(self, username):
        return self.client.post("/login", data={"username": username, "senha": "secret123"})

    def test_viewer_cannot_view_assets_api(self):
        with tic.app.app_context():
            self._create_user("viewer", "Visualizador")
        self._login("viewer")

        response = self.client.get("/api/assets", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "Perfil 'Visualizador' sem permissão para view em ativos.",
        )

    def test_tecnico_cannot_delete_asset_without_delete_permission(self):
        with tic.app.app_context():
            self._create_user("tecnico", "Técnico TI")
            tic.db.session.add(tic.Asset(
                id="A_AUTHZ",
                hostname="NOTE-AUTHZ",
                patrimonio="TI-009999",
                categoria="Notebook",
                status="Disponível",
            ))
            tic.db.session.commit()
        self._login("tecnico")

        response = self.client.delete("/api/assets/A_AUTHZ", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.get_json()["error"],
            "Perfil 'Técnico TI' sem acesso a esta ação",
        )

    def test_profile_wrapper_uses_defaults_without_app_context(self):
        self.assertTrue(tic._profile_allows("Técnico TI", "ativos", "edit"))
        self.assertFalse(tic._profile_allows("Técnico TI", "ativos", "delete"))


if __name__ == "__main__":
    unittest.main()
