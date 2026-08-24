import os
import unittest
from decimal import Decimal
from types import SimpleNamespace
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["SHOW_DEMO_CREDENTIALS"] = "0"

import app as tic  # noqa: E402
from models import Supply, SupplyMovement, SystemUser  # noqa: E402
from services.purchase_service import (  # noqa: E402
    approve_purchase,
    create_purchase,
    procurement_action,
    receive_purchase,
    send_to_procurement,
    submit_purchase,
)


class PurchaseServiceTest(unittest.TestCase):
    def setUp(self):
        tic.app.config.update(TESTING=True)
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()
            tic.db.create_all()
            persisted = SystemUser(id="U001", username="admin.ti", nome="Admin TI", perfil="Administrador", status="Ativo")
            tic.db.session.add(persisted)
            tic.db.session.commit()
            self.user = SimpleNamespace(id="U001", username="admin.ti", nome="Admin TI", perfil="Administrador", status="Ativo")

    def tearDown(self):
        with tic.app.app_context():
            tic.db.session.remove()
            tic.db.drop_all()

    def test_submit_snapshots_two_approval_steps_for_high_value_purchase(self):
        with tic.app.app_context():
            req = create_purchase({
                "solicitante": "Admin TI",
                "items": [{
                    "produto": "Notebook",
                    "tipoItem": "PATRIMONIAL",
                    "quantidadeSolicitada": 2,
                    "valorUnitarioEstimado": "6000.00",
                }],
            }, self.user)

            submit_purchase(req, self.user)
            tic.db.session.commit()

            self.assertEqual(req.status, "Aguardando aprovacao do Gerente de TI")
            self.assertEqual(len(req.approval_steps), 2)
            self.assertEqual([s.permission_code for s in sorted(req.approval_steps, key=lambda s: s.ordem)], [
                "compras.aprovar_gerente",
                "compras.aprovar_diretor",
            ])

            approve_purchase(req, self.user, {"decisao": "Aprovada"})
            self.assertEqual(req.status, "Aguardando aprovacao do Diretor")
            approve_purchase(req, self.user, {"decisao": "Aprovada"})
            self.assertEqual(req.status, "Aguardando envio para Suprimentos")

    def test_receipt_of_supply_purchase_increments_stock_and_records_movement(self):
        with tic.app.app_context():
            supply = Supply(id="S001", nome="Mouse USB", categoria="Periferico", estoque=2, minimo=1, preco=30)
            tic.db.session.add(supply)
            req = create_purchase({
                "solicitante": "Admin TI",
                "items": [{
                    "produto": "Mouse USB",
                    "tipoItem": "INSUMO",
                    "supplyId": "S001",
                    "quantidadeSolicitada": 3,
                    "valorUnitarioEstimado": "35.00",
                }],
            }, self.user)
            submit_purchase(req, self.user)
            approve_purchase(req, self.user, {"decisao": "Aprovada"})
            send_to_procurement(req, self.user, {})
            procurement_action(req, self.user, {"status": "Pedido de compra emitido", "numeroCompra": "OC-1"})

            receive_purchase(req, self.user, {
                "numeroNota": "NF-1",
                "numeroCompra": "OC-1",
                "items": [{"itemId": req.items[0].id, "quantidade": 3, "supplyId": "S001", "valorUnitario": "32.50"}],
            })
            tic.db.session.commit()

            self.assertEqual(supply.estoque, 5)
            self.assertEqual(req.status, "Entrada no estoque realizada")
            self.assertEqual(req.items[0].quantidade_recebida, 3)
            self.assertEqual(req.items[0].valor_unitario_real, Decimal("32.50"))
            movement = tic.db.session.execute(tic.db.select(SupplyMovement)).scalar_one()
            self.assertEqual(movement.tipo, "ENTRADA_COMPRA")
            self.assertEqual(movement.quantidade, 3)
            self.assertEqual(movement.supply_nome, "Mouse USB")


if __name__ == "__main__":
    unittest.main()
