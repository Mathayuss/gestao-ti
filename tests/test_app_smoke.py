import os
import re
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402
from models import Asset  # noqa: E402


class AppSmokeTest(unittest.TestCase):
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

    def test_create_app_returns_configured_flask_app(self):
        flask_app = tic.create_app()
        self.assertIs(flask_app, tic.app)
        self.assertIs(tic.Asset, Asset)
        self.assertIn("assets", tic.db.metadata.tables)

    def test_health_endpoints_are_available(self):
        client = tic.app.test_client()

        live = client.get("/health/live")
        startup = client.get("/health/startup")
        ready = client.get("/health/ready")

        self.assertEqual(live.status_code, 200)
        self.assertEqual(startup.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.get_json()["checks"]["database"]["ok"])

    def test_login_page_renders_without_authentication(self):
        response = tic.app.test_client().get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"csrf_token", response.data)

    def test_api_requires_authentication(self):
        response = tic.app.test_client().get("/api/assets", headers={"Accept": "application/json"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "Não autenticado")

    def test_dashboard_shell_references_versioned_static_assets(self):
        client = tic.app.test_client()
        with tic.app.test_request_context("/"):
            html = tic.app.jinja_env.get_template("index.html").render(build_version="smoke-build")

        self.assertIn("/static/css/app.css?v=smoke-build", html)
        self.assertIn("/static/js/core/app-core.js?v=smoke-build", html)
        self.assertIn("/static/js/modules/settings/main.js?v=smoke-build", html)
        self.assertIn("TICONTROL_BOOT", html)
        self.assertNotIn('/static/js/modules/settings.js"', html)
        self.assertNotIn('/static/js/app.js"', html)

        refs = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
        self.assertGreaterEqual(len(refs), 20)
        for ref in refs:
            response = client.get(ref)
            try:
                self.assertEqual(response.status_code, 200, ref)
                self.assertGreater(len(response.get_data()), 0, ref)
            finally:
                response.close()


if __name__ == "__main__":
    unittest.main()
