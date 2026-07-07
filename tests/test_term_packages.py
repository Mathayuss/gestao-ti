import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class TermPackageTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
            user = tic.SystemUser(
                id="U_TERM_PACKAGE",
                username="admin",
                nome="Admin",
                perfil="Administrador",
                status="Ativo",
            )
            user.set_senha("secret")
            tic.db.session.add(user)
            tic.db.session.add(tic.Colaborador(
                id="C_PACKAGE",
                nome="Ana Costa",
                email="ana@example.com",
                setor="Financeiro",
                unidade="Sede",
                status="Ativo",
            ))
            tic._set_setting("termos_avulsos_tipos", ["VPN", "BYOD"])
            tic._set_setting("termos_avulsos_modelos", {
                "VPN": {
                    "titulo": "TERMO VPN PERSONALIZADO",
                    "preambulo": "VPN para {colaborador}",
                    "clausulas": ["Cláusula exclusiva VPN"],
                    "rodape": "Rodapé VPN",
                },
                "BYOD": {
                    "titulo": "TERMO BYOD PERSONALIZADO",
                    "preambulo": "BYOD para {colaborador}",
                    "clausulas": ["Cláusula exclusiva BYOD"],
                    "rodape": "Rodapé BYOD",
                },
            })
            tic.db.session.commit()
        self.client.post("/login", data={"username": "admin", "senha": "secret"})

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_multiple_terms_use_one_email_and_one_signature_center(self):
        payload = {
            "colaborador": "Ana Costa",
            "setor": "Financeiro",
            "unidade": "Sede",
            "email": "ana@example.com",
            "termos": [
                {"tipo": "VPN", "validade": "2026-12-31"},
                {"tipo": "BYOD", "validade": None},
            ],
        }
        with patch("routes.termos_avulsos.send_email", return_value={"ok": True}) as send_mock:
            created = self.client.post("/api/termos/pacotes", json=payload)

        self.assertEqual(created.status_code, 201, created.get_data(as_text=True))
        result = created.get_json()
        self.assertTrue(result["emailEnviado"])
        self.assertEqual(len(result["terms"]), 2)
        self.assertEqual(send_mock.call_count, 1)
        sent_content = " ".join(str(value) for value in send_mock.call_args.args[1:]).casefold()
        self.assertIn("termos", sent_content)
        self.assertIn("vpn", sent_content)
        self.assertNotIn("equipamento", sent_content)
        package_ids = {term["packageId"] for term in result["terms"]}
        self.assertEqual(package_ids, {result["packageId"]})

        with tic.app.app_context():
            tic._set_setting("termos_avulsos_modelos", {
                "VPN": {"titulo": "TÍTULO ALTERADO DEPOIS", "clausulas": ["Nova cláusula"]},
                "BYOD": {"titulo": "BYOD ALTERADO DEPOIS", "clausulas": ["Nova cláusula"]},
            })
            tic.db.session.commit()

        center = self.client.get(result["url"])
        html = center.get_data(as_text=True)
        self.assertEqual(center.status_code, 200)
        self.assertIn("Central de Assinaturas", html)
        self.assertIn("TERMO VPN PERSONALIZADO", html)
        self.assertIn("TERMO BYOD PERSONALIZADO", html)
        self.assertNotIn("TÍTULO ALTERADO DEPOIS", html)
        self.assertEqual(html.count('name="aceitos"'), 2)

        term_ids = [term["id"] for term in result["terms"]]
        signed = self.client.post(result["url"], data={
            "nome_confirm": "Ana",
            "assinatura": "data:image/png;base64,VEVTVEU=",
            "aceitos": term_ids,
        })
        self.assertEqual(signed.status_code, 200, signed.get_data(as_text=True))
        self.assertIn("Termos assinados com sucesso", signed.get_data(as_text=True))
        with tic.app.app_context():
            terms = tic.db.session.execute(
                tic.db.select(tic.TermoAvulso).where(tic.TermoAvulso.package_id == result["packageId"])
            ).scalars().all()
            self.assertEqual(len(terms), 2)
            self.assertTrue(all(term.status == "Assinado" for term in terms))
            self.assertTrue(all(term.assinatura_img for term in terms))
            backup = tic._build_backup_payload(generated_by="unittest")
            backed_up = [term for term in backup["termosAvulsos"] if term["packageId"] == result["packageId"]]
            self.assertEqual(len(backed_up), 2)
            self.assertTrue(all(term["packageToken"] for term in backed_up))

    def test_package_rejects_type_without_configured_model(self):
        response = self.client.post("/api/termos/pacotes", json={
            "colaborador": "Ana Costa",
            "termos": [{"tipo": "Modelo inexistente"}],
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("não está disponível", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
