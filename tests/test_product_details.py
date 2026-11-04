"""Verificações de especificações, disponibilidade e vigência de promoções."""

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.use_cases.get_product_details import GetProductDetails
from emporio_agent.infrastructure.persistence.sqlite_catalog import SQLiteCatalog
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


class ProductDetailsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "store.sqlite3"
        import_csv_to_sqlite(Path(__file__).resolve().parents[1] / "data", self.database)
        self.get_details = GetProductDetails(SQLiteCatalog(self.database))

    def test_details_include_specs_category_date_and_exact_price(self):
        details = self.get_details.execute(81)
        self.assertEqual(details.product.name, "Yamaha C40 Nylon Natural")
        self.assertEqual(details.product.category_name, "Violões")
        self.assertEqual(details.product.price_brl, Decimal("599.90"))
        self.assertEqual(details.specs["strings"], "nylon")
        self.assertEqual(details.specs["top"], "Spruce")
        self.assertEqual(details.created_at, date(2021, 3, 15))
        self.assertTrue(details.product.is_available)
        self.assertEqual(details.active_promotions, ())

    def test_active_promotions_are_associated_with_the_correct_products(self):
        for product_id, promotion_id, discount in ((127, 12, "10"), (121, 14, "20"), (90, 19, "18"), (94, 24, "8")):
            with self.subTest(product_id=product_id):
                promotions = self.get_details.execute(product_id).active_promotions
                self.assertEqual(len(promotions), 1)
                self.assertEqual(promotions[0].product_id, product_id)
                self.assertEqual(promotions[0].promotion_id, promotion_id)
                self.assertEqual(promotions[0].discount_percent, Decimal(discount))
                self.assertTrue(promotions[0].description)

    def test_inactive_campaigns_are_not_returned_even_with_multiple_records(self):
        for product_id in (93, 96, 99):
            with self.subTest(product_id=product_id):
                self.assertEqual(self.get_details.execute(product_id).active_promotions, ())

    def test_unavailable_products_still_have_details(self):
        for product_id, status in ((96, "active"), (113, "discontinued"), (136, "discontinued"), (130, "coming_soon")):
            with self.subTest(product_id=product_id):
                details = self.get_details.execute(product_id)
                self.assertEqual(details.product.status, status)
                self.assertFalse(details.product.is_available)
                self.assertTrue(details.specs)

    def test_multiple_active_promotions_are_preserved_without_combining_them(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "INSERT INTO promotions VALUES (?, ?, ?, ?, ?)",
                (26, 94, "5", "Campanha de teste", 1),
            )
            connection.commit()
        details = self.get_details.execute(94)
        self.assertEqual([promotion.promotion_id for promotion in details.active_promotions], [24, 26])
        self.assertEqual(details.product.price_brl, Decimal("5999"))

    def test_active_promotion_does_not_make_out_of_stock_product_available(self):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("UPDATE promotions SET is_active = 1 WHERE promotion_id = 8")
            connection.commit()
        details = self.get_details.execute(96)
        self.assertEqual(len(details.active_promotions), 1)
        self.assertFalse(details.product.is_available)

    def test_nonexistent_product_returns_none_including_large_identifiers(self):
        self.assertIsNone(self.get_details.execute(9999))
        self.assertIsNone(self.get_details.execute(10**100))


class GetProductDetailsValidationTests(unittest.TestCase):
    def test_use_case_validates_id_without_accessing_storage(self):
        received = []

        class MemoryReader:
            def get_details(self, product_id):
                received.append(product_id)
                return None

        use_case = GetProductDetails(MemoryReader())
        for product_id in (0, -1, True, "81", 81.0, None):
            with self.subTest(product_id=product_id), self.assertRaises(ValueError):
                use_case.execute(product_id)
        self.assertEqual(received, [])
        self.assertIsNone(use_case.execute(81))
        self.assertEqual(received, [81])


if __name__ == "__main__":
    unittest.main()
