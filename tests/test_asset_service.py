import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402
from services.asset_service import (  # noqa: E402
    next_patrimonio,
    normalize_asset_category_filter,
    validate_asset_payload,
)


class AssetServiceTest(unittest.TestCase):
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

    def test_normalize_asset_category_filter_handles_all_aliases(self):
        self.assertEqual(normalize_asset_category_filter("Todos"), "")
        self.assertEqual(normalize_asset_category_filter("todas"), "")
        self.assertEqual(normalize_asset_category_filter("all"), "")
        self.assertEqual(normalize_asset_category_filter("__all__"), "")
        self.assertEqual(normalize_asset_category_filter("Notebook"), "Notebook")

    def test_validate_asset_payload_checks_required_status_and_uniqueness(self):
        with tic.app.app_context():
            tic.db.session.add(tic.Asset(
                id="A_TEST",
                hostname="NOTE-001",
                patrimonio="TI-000001",
                service_tag="ABC123",
                mac="AA:BB:CC:DD:EE:FF",
                categoria="Notebook",
                status="Disponível",
            ))
            tic.db.session.commit()

            required_errors = validate_asset_payload({}, required_fields=["hostname", "patrimonio"])
            self.assertIn("Campo obrigatório ausente: hostname.", required_errors)
            self.assertIn("Campo obrigatório ausente: patrimonio.", required_errors)

            status_errors = validate_asset_payload({"status": "Quebrado"}, partial=True)
            self.assertIn("Status inválido: Quebrado.", status_errors)

            duplicate_errors = validate_asset_payload({
                "hostname": "NOTE-002",
                "patrimonio": "TI-000001",
                "serviceTag": "ABC123",
                "mac": "AA:BB:CC:DD:EE:FF",
                "categoria": "Notebook",
                "fabricante": "Dell",
                "modelo": "Latitude",
            })
            self.assertTrue(any("Patrimônio 'TI-000001'" in err for err in duplicate_errors))
            self.assertTrue(any("Service Tag 'ABC123'" in err for err in duplicate_errors))
            self.assertTrue(any("MAC 'AA:BB:CC:DD:EE:FF'" in err for err in duplicate_errors))

    def test_next_patrimonio_respects_prefix(self):
        with tic.app.app_context():
            tic.db.session.add(tic.Asset(id="A_TI", hostname="NOTE", patrimonio="TI-000009"))
            tic.db.session.add(tic.Asset(id="A_SUP", hostname="SUP", patrimonio="SUP-000050"))
            tic.db.session.add(tic.Asset(id="A_BAD", hostname="BAD", patrimonio="TI-LEGADO"))
            tic.db.session.commit()

            self.assertEqual(next_patrimonio("TI"), "TI-000010")
            self.assertEqual(next_patrimonio("SUP"), "SUP-000051")
            self.assertEqual(next_patrimonio("NEW"), "NEW-000001")


if __name__ == "__main__":
    unittest.main()
