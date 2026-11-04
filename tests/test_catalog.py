"""Cenários de catálogo com os dados fornecidos e filtros de fronteira."""

import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.ports.catalog import ProductSearch
from emporio_agent.application.use_cases.search_products import SearchProducts
from emporio_agent.domain.product import Product
from emporio_agent.infrastructure.persistence.sqlite_catalog import SQLiteCatalog
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "store.sqlite3"
        import_csv_to_sqlite(Path(__file__).resolve().parents[1] / "data", self.database)
        self.search = SearchProducts(SQLiteCatalog(self.database))

    def test_available_acoustic_guitars_up_to_1000(self):
        results = self.search.execute(ProductSearch(category="Violões", max_price_brl=Decimal("1000")))
        self.assertEqual(
            {product.product_id for product in results},
            {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112},
        )
        self.assertTrue(all(product.is_available for product in results))
        self.assertTrue(all(product.price_brl <= Decimal("1000") for product in results))
        self.assertEqual(results, sorted(results, key=lambda product: (product.price_brl, product.product_id)))

    def test_price_boundary_is_inclusive_and_exact(self):
        filters = dict(name="Yamaha C40")
        self.assertEqual(self.search.execute(ProductSearch(**filters, max_price_brl=Decimal("599.89"))), [])
        result = self.search.execute(ProductSearch(**filters, max_price_brl=Decimal("599.90")))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].price_brl, Decimal("599.90"))
        self.assertEqual(result[0].category_name, "Violões")

    def test_name_and_category_ignore_case_accents_and_surrounding_spaces(self):
        result = self.search.execute(ProductSearch(name="  AÇO  ", category=" VIoloes "))
        self.assertTrue(result)
        self.assertTrue(all(product.category_name == "Violões" and "Aço" in product.name for product in result))

    def test_out_of_stock_discontinued_and_coming_soon_are_not_offered(self):
        for name in ("Giannini GF-3D", "Shelby SN-7C", "Ibanez Bass 2X", "Kala KA-ABP-CTG"):
            with self.subTest(name=name):
                self.assertEqual(self.search.execute(ProductSearch(name=name)), [])
                results = self.search.execute(ProductSearch(name=name, available_only=False))
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0].is_available)

    def test_limit_order_and_empty_results(self):
        results = self.search.execute(ProductSearch(limit=2))
        self.assertEqual(len(results), 2)
        all_results = self.search.execute(ProductSearch(limit=100))
        self.assertEqual(results, all_results[:2])
        self.assertEqual(self.search.execute(ProductSearch(category="Categoria inexistente")), [])
        self.assertEqual(self.search.execute(ProductSearch(max_price_brl=Decimal("0"))), [])

    def test_search_input_is_literal_and_does_not_change_query(self):
        for name in ("%", "_", "' OR 1=1 --"):
            with self.subTest(name=name):
                self.assertEqual(self.search.execute(ProductSearch(name=name)), [])
        self.assertTrue(self.search.execute(ProductSearch(name="Yamaha")))

    def test_missing_database_is_not_created(self):
        missing = self.database.parent / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            SQLiteCatalog(missing).search(ProductSearch())
        self.assertFalse(missing.exists())

    def test_price_above_sqlite_capacity_includes_all_stored_prices(self):
        expected = self.search.execute(ProductSearch(limit=100))
        results = self.search.execute(ProductSearch(max_price_brl=Decimal("1e100"), limit=100))
        self.assertEqual(results, expected)


class ProductSearchValidationTests(unittest.TestCase):
    def test_invalid_filters_are_rejected(self):
        cases = [
            {"name": " "}, {"category": 5}, {"max_price_brl": 100.0},
            {"max_price_brl": Decimal("NaN")}, {"max_price_brl": Decimal("Infinity")},
            {"max_price_brl": Decimal("-1")}, {"max_price_brl": Decimal("1.001")},
            {"available_only": "false"},
            {"limit": 0}, {"limit": 101}, {"limit": True},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                ProductSearch(**arguments)

    def test_large_prices_and_trailing_zeros_are_valid_application_inputs(self):
        for price in (Decimal("1e100"), Decimal("1.2300"), Decimal("0.0000")):
            with self.subTest(price=price):
                self.assertEqual(ProductSearch(max_price_brl=price).max_price_brl, price)

    def test_use_case_accepts_a_catalog_without_sqlite(self):
        product = Product(1, "Violão", 5, "Violões", "Estudo", Decimal("500"), 2, "active")
        received = []

        class MemoryCatalog:
            def search(self, filters):
                received.append(filters)
                return [product]

        filters = ProductSearch(name="Violão")
        self.assertEqual(SearchProducts(MemoryCatalog()).execute(filters), [product])
        self.assertEqual(received, [filters])


if __name__ == "__main__":
    unittest.main()
