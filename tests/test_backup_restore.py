import os
import tempfile
import unittest
from datetime import datetime

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
            tic.db.session.add(tic.Allocation(
                id="AL_TEST",
                ativo_id="A_TEST",
                ativo_nome="NOTE-001",
                colaborador="Ana Teste",
                setor="TI",
                unidade="Sede",
                email="ana@example.com",
                data_aloc="2026-05-01",
                tipo="Empréstimo",
                data_devolucao_prevista="2026-06-01",
                termo="TERMO-AL_TEST",
                termo_status="Assinado",
                data_assinatura=datetime(2026, 5, 1, 10, 0, 0),
                assinatura_ip="127.0.0.1",
                assinatura_img="data:image/png;base64,ASSINATURA",
                sign_token="token-aloc",
                sign_token_expiry=datetime(2026, 6, 1, 10, 0, 0),
                assinatura_ti_img="data:image/png;base64,ASSINATURA_TI",
                assinatura_ti_nome="Tecnico TI",
                data_assinatura_ti=datetime(2026, 5, 1, 10, 5, 0),
            ))
            tic.db.session.add(tic.Devolucao(
                id="D_TEST",
                colaborador_id="C_TEST",
                colaborador="Ana Teste",
                setor="TI",
                unidade="Sede",
                data_devolucao="2026-05-02",
                assinatura_img="data:image/png;base64,DEVOLUCAO",
                assinatura_ip="127.0.0.2",
                sign_token="token-dev",
                sign_token_expiry=datetime(2026, 6, 2, 10, 0, 0),
                status="Assinado",
                ativos_devolvidos='[{"id":"A_TEST"}]',
                laudo_status="Finalizado",
                rh_token="token-rh",
                rh_token_expiry=datetime(2026, 6, 3, 10, 0, 0),
                rh_email="rh@example.com",
                rh_ciencia_ip="127.0.0.3",
            ))
            tic.db.session.add(tic.LaudoTecnico(
                id="LT_TEST",
                devolucao_id="D_TEST",
                tecnico="Tecnico TI",
                avaliacao_itens='[{"ativo":"A_TEST","estado":"Bom"}]',
                observacao_geral="Laudo preservado",
                tem_cobranca=True,
                valor_cobranca=99.9,
            ))
            tic.db.session.add(tic.AuditCampaign(
                id="AC_TEST",
                nome="Auditoria Teste",
                unidade="Sede",
                setor="TI",
                status="Aberta",
                criado_por="unittest",
            ))
            tic.db.session.add(tic.AuditCampaignItem(
                id="ACI_TEST",
                campaign_id="AC_TEST",
                asset_id="A_TEST",
                asset_nome="NOTE-001",
                patrimonio="TI-000001",
                status="Conferido",
                auditado_por="unittest",
                auditado_em=datetime(2026, 5, 3, 10, 0, 0),
            ))
            tic.db.session.add(tic.TermoAvulso(
                id="TA_TEST",
                tipo="VPN",
                colaborador="Ana Teste",
                setor="TI",
                unidade="Sede",
                email="ana@example.com",
                detalhes='{"acesso":"vpn"}',
                validade="2026-12-31",
                status="Assinado",
                sign_token="token-termo",
                sign_token_expiry=datetime(2026, 6, 4, 10, 0, 0),
                assinatura_img="data:image/png;base64,TERMO",
                assinatura_ip="127.0.0.4",
                data_assinatura=datetime(2026, 5, 4, 10, 0, 0),
                created_by="unittest",
            ))
            tic.db.session.add(tic.Attachment(
                id="ATT_TEST",
                entity_type="asset",
                entity_id="A_TEST",
                original_name="nota.pdf",
                stored_name="stored/nota-fiscal.pdf",
                content_type="application/pdf",
                size=123,
                category="Nota Fiscal",
                uploaded_by="unittest",
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
            self.assertEqual(stats["laudosTecnicos"], 1)
            self.assertEqual(stats["auditCampaigns"], 1)
            self.assertEqual(stats["termosAvulsos"], 1)
            self.assertEqual(stats["attachments"], 1)
            self.assertIsNone(tic.db.session.get(tic.Asset, "A_EXTRA"))
            self.assertEqual(tic.db.session.get(tic.Asset, "A_TEST").hostname, "NOTE-001")
            self.assertEqual(tic.db.session.get(tic.Supply, "S_TEST").estoque, 12)
            restored_license = tic.db.session.get(tic.License, "L_TEST")
            self.assertEqual(restored_license.custo_mensal, 30)
            self.assertEqual(restored_license.custo_anual, 360)
            restored_allocation = tic.db.session.get(tic.Allocation, "AL_TEST")
            self.assertEqual(restored_allocation.tipo, "Empréstimo")
            self.assertEqual(restored_allocation.data_devolucao_prevista, "2026-06-01")
            self.assertEqual(restored_allocation.assinatura_img, "data:image/png;base64,ASSINATURA")
            self.assertEqual(restored_allocation.assinatura_ti_img, "data:image/png;base64,ASSINATURA_TI")
            restored_devolucao = tic.db.session.get(tic.Devolucao, "D_TEST")
            self.assertEqual(restored_devolucao.assinatura_img, "data:image/png;base64,DEVOLUCAO")
            self.assertEqual(restored_devolucao.rh_ciencia_ip, "127.0.0.3")
            self.assertEqual(tic.db.session.get(tic.LaudoTecnico, "LT_TEST").observacao_geral, "Laudo preservado")
            self.assertEqual(tic.db.session.get(tic.AuditCampaignItem, "ACI_TEST").status, "Conferido")
            self.assertEqual(tic.db.session.get(tic.TermoAvulso, "TA_TEST").assinatura_img, "data:image/png;base64,TERMO")
            self.assertEqual(tic.db.session.get(tic.Attachment, "ATT_TEST").stored_name, "stored/nota-fiscal.pdf")
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
