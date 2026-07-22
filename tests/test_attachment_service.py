import os
import tempfile
import unittest
from io import BytesIO

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"

import app as tic  # noqa: E402
from services.attachment_service import (  # noqa: E402
    attachment_magic_matches,
    attachment_path,
    create_attachment_record,
)
from werkzeug.datastructures import FileStorage  # noqa: E402


class AttachmentServiceTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True)
        self.tmp = tempfile.TemporaryDirectory()
        self.old_instance_path = tic.app.instance_path
        tic.app.instance_path = self.tmp.name
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
        tic.app.instance_path = self.old_instance_path
        self.tmp.cleanup()

    def test_attachment_path_rejects_unsafe_names(self):
        with tic.app.app_context():
            self.assertIsNone(attachment_path("../nota.pdf"))
            self.assertIsNone(attachment_path("pasta/nota.pdf"))
            self.assertTrue(attachment_path("ATT_TEST_nota.pdf").endswith("ATT_TEST_nota.pdf"))

    def test_attachment_magic_validation(self):
        self.assertTrue(attachment_magic_matches("pdf", b"%PDF-1.7\n"))
        self.assertFalse(attachment_magic_matches("pdf", b"nao e pdf"))
        self.assertFalse(attachment_magic_matches("txt", b"texto\x00com-null"))

    def test_create_attachment_record_persists_file_and_model(self):
        with tic.app.app_context():
            tic.db.session.add(tic.Asset(id="A_ATT", hostname="NOTE-ATT", status="Disponível"))
            tic.db.session.commit()

            upload = FileStorage(
                stream=BytesIO(b"%PDF-1.7\nconteudo"),
                filename="nota fiscal.pdf",
                content_type="application/pdf",
            )
            att, error = create_attachment_record(
                "asset",
                "A_ATT",
                upload,
                category="Nota Fiscal",
                description="Compra",
                uploaded_by="tester",
            )

            self.assertIsNone(error)
            self.assertEqual(att.entity_type, "asset")
            self.assertEqual(att.uploaded_by, "tester")
            tic.db.session.commit()

            saved = tic.db.session.get(tic.Attachment, att.id)
            self.assertIsNotNone(saved)
            self.assertTrue(os.path.exists(attachment_path(saved.stored_name)))

    def test_create_attachment_record_rejects_mismatched_content(self):
        with tic.app.app_context():
            upload = FileStorage(
                stream=BytesIO(b"texto simples"),
                filename="arquivo.pdf",
                content_type="application/pdf",
            )
            att, error = create_attachment_record("asset", "A_ATT", upload, uploaded_by="tester")

            self.assertIsNone(att)
            self.assertEqual(error, ("Conteúdo do arquivo não corresponde ao tipo informado.", 400))

    def test_create_attachment_record_uses_system_user_without_request_context(self):
        with tic.app.app_context():
            upload = FileStorage(
                stream=BytesIO(b"texto sem contexto http"),
                filename="observacao.txt",
                content_type="text/plain",
            )
            att, error = create_attachment_record("asset", "A_ATT", upload)

            self.assertIsNone(error)
            self.assertEqual(att.uploaded_by, "sistema")


if __name__ == "__main__":
    unittest.main()
