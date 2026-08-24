import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402
from models import Asset  # noqa: E402


class AppSmokeTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True)
        tic._rate_buckets.clear()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()

    def tearDown(self):
        os.environ.pop("PUBLIC_ASSETS_ENABLED", None)
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_create_app_returns_configured_flask_app(self):
        flask_app = tic.create_app()
        self.assertIs(flask_app, tic.app)
        self.assertIs(tic.Asset, Asset)
        self.assertIn("assets", tic.db.metadata.tables)

    def test_routes_blueprint_preserves_legacy_endpoint_names(self):
        endpoints = set(tic.app.view_functions)

        for endpoint in {
            "index",
            "login_page",
            "do_login",
            "do_logout",
            "devolucao_pdf",
            "pagina_assinatura_pacote",
            "next_print_job",
        }:
            self.assertIn(endpoint, endpoints)
        self.assertFalse(any(endpoint.startswith("auth.") for endpoint in endpoints))

    def test_route_modules_do_not_use_global_export_bridge(self):
        routes_dir = Path(__file__).resolve().parents[1] / "routes"
        offenders = []
        for path in routes_dir.glob("*.py"):
            if path.name in {"__init__.py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if "_export_route_globals" in text or "globals().update" in text:
                offenders.append(path.name)

        self.assertEqual([], sorted(offenders))

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
        self.assertEqual(response.get_json()["error"], "N\u00e3o autenticado")

    def test_asset_qr_uses_disabled_by_default_tokenized_public_page(self):
        client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.add(tic.Asset(
                id="A_PUBLIC",
                public_token="public-token-test",
                hostname="NOTE-PUBLIC",
                fabricante="Dell",
                modelo="Latitude",
                categoria="Notebook",
                patrimonio="TI-000777",
                service_tag="SERIAL-SECRET",
                colaborador="Ana Sigilosa",
                setor="RH",
                unidade="Sede",
                status="Alocado",
            ))
            tic.db.session.commit()

        self.assertEqual(client.get("/asset/A_PUBLIC").status_code, 302)
        self.assertEqual(client.get("/public/asset/public-token-test").status_code, 404)

        os.environ["PUBLIC_ASSETS_ENABLED"] = "1"
        response = client.get("/public/asset/public-token-test")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("NOTE-PUBLIC", html)
        self.assertIn("Restrito", html)
        self.assertNotIn("SERIAL-SECRET", html)
        self.assertNotIn("Ana Sigilosa", html)

    def test_public_asset_page_is_rate_limited(self):
        os.environ["PUBLIC_ASSETS_ENABLED"] = "1"
        client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.add(tic.Asset(
                id="A_RATE",
                public_token="rate-token-test",
                hostname="NOTE-RATE",
                categoria="Notebook",
                patrimonio="TI-000778",
                status="Disponível",
            ))
            tic.db.session.commit()

        statuses = [client.get("/public/asset/rate-token-test").status_code for _ in range(11)]

        self.assertEqual(statuses[:10], [200] * 10)
        self.assertEqual(statuses[10], 429)

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

