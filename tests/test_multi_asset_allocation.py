import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class MultiAssetAllocationTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = tic.app.test_client()
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
            user = tic.SystemUser(
                id="U_TEST",
                username="admin",
                nome="Admin",
                email="admin@example.com",
                perfil="Administrador",
                status="Ativo",
            )
            user.set_senha("secret")
            tic.db.session.add(user)
            tic.db.session.add(tic.Colaborador(
                id="C_TEST",
                nome="Ana Teste",
                email="ana@example.com",
                setor="TI",
                unidade="Sede",
                status="Ativo",
            ))
            for aid, host, cat in (
                ("A_NOTE", "NOTE-001", "Notebook"),
                ("A_MON1", "MON-001", "Monitor"),
                ("A_MON2", "MON-002", "Monitor"),
            ):
                tic.db.session.add(tic.Asset(
                    id=aid,
                    hostname=host,
                    fabricante="Dell",
                    modelo="Teste",
                    categoria=cat,
                    patrimonio=f"PAT-{aid}",
                    status="Disponível",
                ))
            tic.db.session.commit()
        self.client.post("/login", data={"username": "admin", "senha": "secret"})

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_allocation_accepts_multiple_assets_and_blocks_reuse(self):
        payload = {
            "ativos": ["A_NOTE", "A_MON1", "A_MON2"],
            "colaborador": "Ana Teste",
            "setor": "TI",
            "unidade": "Sede",
            "email": "ana@example.com",
            "tipo": "Responsabilidade",
            "perifericos": [],
        }
        response = self.client.post("/api/allocations", json=payload)

        self.assertEqual(response.status_code, 201, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(len(data["ativos"]), 3)
        self.assertEqual(data["ativo"], "A_NOTE")

        with tic.app.app_context():
            self.assertEqual(tic.db.session.get(tic.Asset, "A_MON1").status, "Alocado")
            items = tic.db.session.execute(tic.db.select(tic.AllocationAsset)).scalars().all()
            self.assertEqual(len(items), 3)

        blocked = self.client.post("/api/allocations", json={
            "ativos": ["A_MON1"],
            "colaborador": "Ana Teste",
            "setor": "TI",
            "unidade": "Sede",
            "email": "ana@example.com",
            "tipo": "Responsabilidade",
        })
        self.assertEqual(blocked.status_code, 400)
        self.assertIn("alocação ativa", blocked.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
