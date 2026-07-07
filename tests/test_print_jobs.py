import os
import base64
import zipfile
from io import BytesIO
import unittest

from PIL import Image

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class PrintJobsTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
            user = tic.SystemUser(
                id="U_PRINT",
                username="admin",
                nome="Admin",
                perfil="Administrador",
                status="Ativo",
            )
            user.set_senha("secret")
            tic.db.session.add(user)
            tic.db.session.add(tic.Asset(
                id="A_PRINT",
                hostname="NOTE-PRINT",
                fabricante="Dell",
                modelo="Latitude",
                categoria="Notebook",
                patrimonio="TI-000123",
                service_tag="ABC123456",
                setor="TI",
                status="Disponível",
            ))
            tic.db.session.commit()
        self.client.post("/login", data={"username": "admin", "senha": "secret"})

    def tearDown(self):
        os.environ.pop("SETUP_TOKEN", None)
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_agent_print_job_lifecycle(self):
        printer_resp = self.client.post("/api/print-printers", json={
            "id": "L42PRO-TESTE",
            "name": "L42Pro Teste",
            "windowsName": "ELGIN L42Pro",
            "location": "TI",
            "dpi": 300,
        })
        self.assertEqual(printer_resp.status_code, 201, printer_resp.get_data(as_text=True))
        printer_data = printer_resp.get_json()
        token = printer_data["token"]
        self.assertEqual(printer_data["dpi"], 300)

        job_resp = self.client.post("/api/print-jobs", json={
            "printerId": "L42PRO-TESTE",
            "ids": ["A_PRINT"],
            "copies": 1,
            "config": {"size": "personalizada", "customW": 50.5, "customH": 30.5},
        })
        self.assertEqual(job_resp.status_code, 201, job_resp.get_data(as_text=True))
        job_id = job_resp.get_json()["jobs"][0]["id"]

        next_resp = self.client.get(
            "/api/print-jobs/next?printer_id=L42PRO-TESTE",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(next_resp.status_code, 200, next_resp.get_data(as_text=True))
        next_job = next_resp.get_json()
        self.assertEqual(next_job["id"], job_id)
        self.assertIn("^XA", next_job["zpl"])
        self.assertIn("^PW596", next_job["zpl"])
        self.assertIn("^LL360", next_job["zpl"])
        self.assertIn("TI-000123", next_job["zpl"])

        status_resp = self.client.post(
            f"/api/print-jobs/{job_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "printed", "message": "ok"},
        )
        self.assertEqual(status_resp.status_code, 200, status_resp.get_data(as_text=True))
        self.assertEqual(status_resp.get_json()["status"], "printed")

    def test_download_print_agent_package(self):
        response = self.client.get("/api/print-agent/download?printer_id=L42PRO-TESTE&windows_printer=ELGIN%20L42Pro")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/zip")
        with zipfile.ZipFile(BytesIO(response.data)) as package:
            names = set(package.namelist())
        self.assertIn("l42pro_print_agent.py", names)
        self.assertIn("requirements.txt", names)
        self.assertIn("agent.env.example", names)
        self.assertIn("run-agent.bat", names)

    def test_agent_settings_update_and_explicit_token_renewal(self):
        created = self.client.post("/api/print-printers", json={
            "id": "ETIQUETAS-01",
            "name": "Etiqueta Recepção",
            "windowsName": "ELGIN L42Pro",
            "dpi": 203,
        })
        self.assertEqual(created.status_code, 201)
        old_token = created.get_json()["token"]

        duplicate = self.client.post("/api/print-printers", json={"id": "ETIQUETAS-01"})
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.put("/api/print-printers/ETIQUETAS-01", json={
            "name": "Etiqueta Almoxarifado",
            "location": "Almoxarifado",
            "windowsName": "ZDesigner ZD220",
            "dpi": 300,
        })
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        self.assertNotIn("token", updated.get_json())
        self.assertEqual(updated.get_json()["dpi"], 300)

        old_token_check = self.client.get(
            "/api/print-jobs/next?printer_id=ETIQUETAS-01",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        self.assertEqual(old_token_check.status_code, 200)
        self.assertIsNone(old_token_check.get_json()["job"])

        renewed = self.client.post("/api/print-printers/ETIQUETAS-01/token", json={})
        self.assertEqual(renewed.status_code, 200)
        new_token = renewed.get_json()["token"]
        self.assertNotEqual(old_token, new_token)

        rejected_old_token = self.client.get(
            "/api/print-jobs/next?printer_id=ETIQUETAS-01",
            headers={"Authorization": f"Bearer {old_token}"},
        )
        self.assertEqual(rejected_old_token.status_code, 401)
        accepted_new_token = self.client.get(
            "/api/print-jobs/next?printer_id=ETIQUETAS-01",
            headers={"Authorization": f"Bearer {new_token}"},
        )
        self.assertEqual(accepted_new_token.status_code, 200)
        self.assertIsNone(accepted_new_token.get_json()["job"])

    def test_initial_setup_can_create_print_agent(self):
        os.environ["SETUP_TOKEN"] = "setup-test-token"
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
        client = tic.app.test_client()
        response = client.post("/setup?token=setup-test-token", data={
            "token": "setup-test-token",
            "empresa_nome": "Empresa Teste",
            "admin_nome": "Administrador",
            "admin_username": "setupadmin",
            "admin_email": "admin@example.com",
            "admin_password": "senha-segura",
            "admin_password_confirm": "senha-segura",
            "app_base_url": "http://localhost:5000",
            "print_agent_enabled": "on",
            "print_agent_id": "ETIQUETAS-SETUP",
            "print_agent_name": "Etiquetas Setup",
            "print_agent_windows_name": "ELGIN L42Pro",
            "print_agent_location": "TI",
            "print_agent_dpi": "203",
            "backup_frequency": "daily",
            "backup_retention": "7",
        })
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("Instalação concluída", response.get_data(as_text=True))
        self.assertIn("ETIQUETAS-SETUP", response.get_data(as_text=True))
        with tic.app.app_context():
            printer = tic.db.session.get(tic.PrintPrinter, "ETIQUETAS-SETUP")
            self.assertIsNotNone(printer)
            self.assertTrue(printer.token_hash)

    def test_small_custom_label_uses_compact_zpl(self):
        printer_resp = self.client.post("/api/print-printers", json={
            "id": "L42PRO-PEQUENA",
            "name": "L42Pro Pequena",
            "windowsName": "ELGIN L42Pro",
            "dpi": 300,
        })
        self.assertEqual(printer_resp.status_code, 201, printer_resp.get_data(as_text=True))
        token = printer_resp.get_json()["token"]

        job_resp = self.client.post("/api/print-jobs", json={
            "printerId": "L42PRO-PEQUENA",
            "ids": ["A_PRINT"],
            "copies": 1,
            "config": {"size": "personalizada", "customW": 39, "customH": 19},
        })
        self.assertEqual(job_resp.status_code, 201, job_resp.get_data(as_text=True))

        next_resp = self.client.get(
            "/api/print-jobs/next?printer_id=L42PRO-PEQUENA",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(next_resp.status_code, 200, next_resp.get_data(as_text=True))
        zpl = next_resp.get_json()["zpl"]
        self.assertIn("^PW461", zpl)
        self.assertIn("^LL224", zpl)
        self.assertIn("TI-000123", zpl)
        self.assertIn("NOTE-PRINT", zpl)
        self.assertIn("ABC123456", zpl)
        self.assertNotIn("Latitude", zpl)
        self.assertNotIn("Setor:", zpl)

    def test_qr_only_layout_sends_only_qr_to_agent(self):
        printer_resp = self.client.post("/api/print-printers", json={
            "id": "L42PRO-QR",
            "name": "L42Pro QR",
            "windowsName": "ELGIN L42Pro",
            "dpi": 203,
        })
        self.assertEqual(printer_resp.status_code, 201, printer_resp.get_data(as_text=True))
        token = printer_resp.get_json()["token"]

        job_resp = self.client.post("/api/print-jobs", json={
            "printerId": "L42PRO-QR",
            "ids": ["A_PRINT"],
            "copies": 1,
            "config": {
                "size": "media",
                "layout": "qr-only",
                "campos": {
                    "hostname": True,
                    "patrimonio": True,
                    "serviceTag": True,
                    "setor": True,
                },
            },
        })
        self.assertEqual(job_resp.status_code, 201, job_resp.get_data(as_text=True))

        next_resp = self.client.get(
            "/api/print-jobs/next?printer_id=L42PRO-QR",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(next_resp.status_code, 200, next_resp.get_data(as_text=True))
        zpl = next_resp.get_json()["zpl"]
        self.assertIn("^BQN", zpl)
        self.assertIn("/asset/A_PRINT", zpl)
        self.assertNotIn("NOTE-PRINT", zpl)
        self.assertNotIn("TI-000123", zpl)
        self.assertNotIn("ABC123456", zpl)
        self.assertNotIn("TI Control", zpl)

    def test_logo_is_composed_in_compact_qr_for_pdf_and_agent(self):
        logo_buffer = BytesIO()
        Image.new("RGB", (16, 16), "black").save(logo_buffer, format="PNG")
        logo_data = "data:image/png;base64," + base64.b64encode(logo_buffer.getvalue()).decode("ascii")
        with tic.app.app_context():
            tic._set_setting("empresa", {"nome": "Empresa Teste", "logo_base64": logo_data})
            tic.db.session.commit()

        printer_resp = self.client.post("/api/print-printers", json={
            "id": "L42PRO-LOGO",
            "name": "L42Pro Logo",
            "windowsName": "ELGIN L42Pro",
            "dpi": 300,
        })
        self.assertEqual(printer_resp.status_code, 201)
        token = printer_resp.get_json()["token"]
        config = {
            "size": "personalizada",
            "customW": 39,
            "customH": 19,
            "layout": "compact",
            "logoNoQr": True,
        }

        pdf_resp = self.client.post("/api/assets/labels.pdf", json={"ids": ["A_PRINT"], "config": config})
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp.mimetype, "application/pdf")

        job_resp = self.client.post("/api/print-jobs", json={
            "printerId": "L42PRO-LOGO",
            "ids": ["A_PRINT"],
            "copies": 1,
            "config": config,
        })
        self.assertEqual(job_resp.status_code, 201, job_resp.get_data(as_text=True))
        next_resp = self.client.get(
            "/api/print-jobs/next?printer_id=L42PRO-LOGO",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(next_resp.status_code, 200)
        zpl = next_resp.get_json()["zpl"]
        self.assertIn("^GFA", zpl)
        self.assertNotIn("^BQN", zpl)


if __name__ == "__main__":
    unittest.main()
