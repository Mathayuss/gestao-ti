import os
import tempfile
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402


class BackupRestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_backup_dir = tic.BACKUP_DIR
        tic.BACKUP_DIR = self.tmpdir.name
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
        tic.BACKUP_DIR = self.old_backup_dir
        self.tmpdir.cleanup()

    def test_backup_restore_roundtrip_core_entities(self):
        with tic.app.app_context():
            tic.db.session.add(tic.Colaborador(
                id="C_TEST",
                nome="Ana Teste",
                email="ana@example.com",
                setor="TI",
                unidade="Sede",
                status="Ativo",
            ))
            tic.db.session.add(tic.Asset(
                id="A_TEST",
                hostname="NOTE-001",
                patrimonio="TI-000001",
                categoria="Notebook",
                status="Em uso",
                colaborador="Ana Teste",
                setor="TI",
                unidade="Sede",
            ))
            tic.db.session.add(tic.Supply(
                id="S_TEST",
                nome="Mouse USB",
                categoria="Periférico",
                unidade="un",
                estoque=12,
                minimo=2,
                preco=35.5,
            ))
            tic.db.session.add(tic.License(
                id="L_TEST",
                software="Suite Teste",
                fornecedor="Fornecedor",
                total=3,
                atribuidas=1,
                custo=10,
                tipo="Assinatura mensal",
            ))
            tic._set_setting("empresa", {"nome": "Empresa Teste"})
            tic.db.session.commit()

            payload = tic._build_backup_payload(generated_by="unittest")
            validation = tic._validate_backup_payload(payload)
            self.assertTrue(validation["valid"], validation)

            tic.db.session.add(tic.Asset(id="A_EXTRA", hostname="EXTRA", categoria="Desktop"))
            tic._set_setting("empresa", {"nome": "Empresa Alterada"})
            tic.db.session.commit()

            stats = tic._restore_from_payload(payload, restored_by="unittest")
            tic.db.session.commit()

            self.assertEqual(stats["assets"], 1)
            self.assertEqual(stats["colaboradores"], 1)
            self.assertEqual(stats["supplies"], 1)
            self.assertEqual(stats["licenses"], 1)
            self.assertIsNone(tic.db.session.get(tic.Asset, "A_EXTRA"))
            self.assertEqual(tic.db.session.get(tic.Asset, "A_TEST").hostname, "NOTE-001")
            self.assertEqual(tic.db.session.get(tic.Supply, "S_TEST").estoque, 12)
            restored_license = tic.db.session.get(tic.License, "L_TEST")
            self.assertEqual(restored_license.custo_mensal, 30)
            self.assertEqual(restored_license.custo_anual, 360)
            self.assertEqual(tic._get_setting("empresa", {}).get("nome"), "Empresa Teste")

    def test_login_rate_limit_records_and_marks_success(self):
        with tic.app.app_context():
            self.assertTrue(tic._check_login_rate_limit("127.0.0.88"))
            tic._record_login_success("127.0.0.88")

            attempt = tic.db.session.execute(
                tic.db.select(tic.LoginAttempt)
                .where(tic.LoginAttempt.ip == "127.0.0.88")
                .order_by(tic.LoginAttempt.id.desc())
                .limit(1)
            ).scalar_one()

            self.assertTrue(attempt.success)


if __name__ == "__main__":
    unittest.main()
