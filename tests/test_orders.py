"""Consulta de pedidos, dados históricos e isolamento entre clientes."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.use_cases.get_order import GetOrder
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite
from emporio_agent.infrastructure.persistence.sqlite_orders import SQLiteOrderReader


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "store.sqlite3"
        import_csv_to_sqlite(Path(__file__).resolve().parents[1] / "data", self.database)
        self.reader = SQLiteOrderReader(self.database)

    def test_shipped_order_includes_tracking_estimate_and_items(self):
        order = GetOrder(self.reader, customer_id=2).execute(8)
        self.assertEqual(order.order_id, 8)
        self.assertEqual(order.status, "shipped")
        self.assertEqual(order.order_date, date(2026, 2, 15))
        self.assertEqual(order.total_brl, Decimal("349.90"))
        self.assertEqual(order.payment_method, "debit")
        self.assertEqual(order.tracking_code, "BRJL5544332BR")
        self.assertEqual(order.estimated_delivery, date(2026, 2, 28))
        self.assertIsNone(order.cancellation_reason)
        self.assertEqual([(item.product_id, item.quantity) for item in order.items], [(120, 1)])
        self.assertTrue(order.items[0].product_name)

    def test_other_customers_order_and_nonexistent_order_have_same_result(self):
        lookup = GetOrder(self.reader, customer_id=3)
        self.assertIsNone(lookup.execute(8))
        self.assertIsNone(lookup.execute(9999))
        self.assertIsNotNone(lookup.execute(1))
        self.assertIsNotNone(lookup.execute(19))

    def test_large_identifiers_return_none_without_sqlite_overflow(self):
        self.assertIsNone(GetOrder(self.reader, customer_id=3).execute(10**100))
        self.assertIsNone(GetOrder(self.reader, customer_id=10**100).execute(1))

    def test_confirmed_pending_and_delivered_statuses_are_preserved(self):
        for order_id, customer_id, status in ((9, 6, "confirmed"), (13, 8, "pending"), (1, 3, "delivered")):
            with self.subTest(status=status):
                self.assertEqual(GetOrder(self.reader, customer_id).execute(order_id).status, status)

    def test_missing_tracking_and_estimate_are_not_invented(self):
        order = GetOrder(self.reader, customer_id=6).execute(9)
        self.assertIsNone(order.tracking_code)
        self.assertIsNone(order.estimated_delivery)

    def test_cancelled_order_preserves_reason_and_historical_total(self):
        order = GetOrder(self.reader, customer_id=7).execute(20)
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.total_brl, Decimal("1400"))
        self.assertEqual(order.cancellation_reason, "Endereço de entrega inválido informado pelo cliente")
        self.assertEqual([(item.product_id, item.quantity) for item in order.items], [(84, 1), (107, 1)])

    def test_item_quantity_and_total_do_not_depend_on_current_stock_or_price(self):
        order = GetOrder(self.reader, customer_id=12).execute(3)
        self.assertEqual(order.items[0].quantity, 2)
        self.assertEqual(order.total_brl, Decimal("3450"))

    def test_internal_notes_are_not_returned_for_non_cancelled_orders(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE orders SET notes = 'Observação interna' WHERE order_id = 1")
            connection.commit()
        self.assertIsNone(GetOrder(self.reader, customer_id=3).execute(1).cancellation_reason)

    def test_missing_database_is_not_created(self):
        missing = self.database.parent / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            GetOrder(SQLiteOrderReader(missing), customer_id=3).execute(1)
        self.assertFalse(missing.exists())


class OrderSessionTests(unittest.TestCase):
    def setUp(self):
        self.received = []
        received = self.received

        class MemoryOrders:
            def get_for_customer(self, order_id, customer_id):
                received.append((order_id, customer_id))
                return None

        self.reader = MemoryOrders()

    def test_anonymous_session_is_denied_before_querying(self):
        with self.assertRaises(PermissionError):
            GetOrder(self.reader, customer_id=None).execute(1)
        self.assertEqual(self.received, [])

    def test_session_identity_is_forwarded_by_application(self):
        self.assertIsNone(GetOrder(self.reader, customer_id=3).execute(1))
        self.assertEqual(self.received, [(1, 3)])

    def test_invalid_order_and_customer_identifiers_are_rejected(self):
        for value in (0, -1, True, "3", 3.0):
            with self.subTest(customer_id=value), self.assertRaises(ValueError):
                GetOrder(self.reader, customer_id=value)
        for value in (0, -1, True, "1", 1.0, None):
            with self.subTest(order_id=value), self.assertRaises(ValueError):
                GetOrder(self.reader, customer_id=3).execute(value)
        self.assertEqual(self.received, [])


if __name__ == "__main__":
    unittest.main()
