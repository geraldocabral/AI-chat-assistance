"""Cenários de catálogo com os dados fornecidos e filtros de fronteira."""

import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.ports.catalog import ProductSearch, ProductSearchResult
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
        results = self.search.execute(ProductSearch(category="Violões", max_price_brl=Decimal("1000"))).products
        self.assertEqual(
            {product.product_id for product in results},
            {81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 107, 112},
        )
        self.assertTrue(all(product.is_available for product in results))
        self.assertTrue(all(product.price_brl <= Decimal("1000") for product in results))
        self.assertEqual(results, sorted(results, key=lambda product: (product.price_brl, product.product_id)))

    def test_price_boundary_is_inclusive_and_exact(self):
        filters = dict(name="Yamaha C40")
        self.assertEqual(self.search.execute(ProductSearch(**filters, max_price_brl=Decimal("599.89"))).products, [])
        result = self.search.execute(ProductSearch(**filters, max_price_brl=Decimal("599.90"))).products
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].price_brl, Decimal("599.90"))
        self.assertEqual(result[0].category_name, "Violões")

    def test_name_and_category_ignore_case_accents_and_surrounding_spaces(self):
        result = self.search.execute(ProductSearch(name="  AÇO  ", category=" VIoloes ")).products
        self.assertTrue(result)
        self.assertTrue(all(product.category_name == "Violões" and "Aço" in product.name for product in result))

    def test_out_of_stock_discontinued_and_coming_soon_are_not_offered(self):
        for name in ("Giannini GF-3D", "Shelby SN-7C", "Ibanez Bass 2X", "Kala KA-ABP-CTG"):
            with self.subTest(name=name):
                self.assertEqual(self.search.execute(ProductSearch(name=name)).products, [])
                results = self.search.execute(ProductSearch(name=name, available_only=False)).products
                self.assertEqual(len(results), 1)
                self.assertFalse(results[0].is_available)

    def test_limit_order_and_empty_results(self):
        results = self.search.execute(ProductSearch(limit=2)).products
        self.assertEqual(len(results), 2)
        all_results = self.search.execute(ProductSearch(limit=100)).products
        self.assertEqual(results, all_results[:2])
        self.assertEqual(self.search.execute(ProductSearch(category="Categoria inexistente")).products, [])
        self.assertEqual(self.search.execute(ProductSearch(max_price_brl=Decimal("0"))).products, [])

    def test_search_input_is_literal_and_does_not_change_query(self):
        for name in ("%", "_", "' OR 1=1 --"):
            with self.subTest(name=name):
                self.assertEqual(self.search.execute(ProductSearch(name=name)).products, [])
        self.assertTrue(self.search.execute(ProductSearch(name="Yamaha")).products)

    def test_missing_database_is_not_created(self):
        missing = self.database.parent / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            SQLiteCatalog(missing).search(ProductSearch())
        self.assertFalse(missing.exists())

    def test_price_above_sqlite_capacity_includes_all_stored_prices(self):
        expected = self.search.execute(ProductSearch(limit=100))
        results = self.search.execute(ProductSearch(max_price_brl=Decimal("1e100"), limit=100))
        self.assertEqual(results, expected)

    def test_price_range_is_applied_before_limit(self):
        result = self.search.execute(ProductSearch(
            category="Violões", min_price_brl=Decimal("1500"), max_price_brl=Decimal("2000"), limit=5,
        ))
        self.assertEqual([product.product_id for product in result.products], [111, 114, 104])
        self.assertEqual(result.total_count, 3)
        self.assertFalse(result.has_more)
        self.assertIsNone(result.next_offset)

    def test_both_price_boundaries_are_inclusive(self):
        result = self.search.execute(ProductSearch(
            category="Violões", min_price_brl=Decimal("1699"), max_price_brl=Decimal("1899"),
        ))
        self.assertEqual([product.product_id for product in result.products], [111, 114, 104])
        exact = self.search.execute(ProductSearch(
            category="Violões", min_price_brl=Decimal("1699"), max_price_brl=Decimal("1699"),
        ))
        self.assertEqual(exact.total_count, 2)

    def test_pagination_reaches_all_matches_without_repetitions(self):
        expected = self.search.execute(ProductSearch(category="Violões", max_price_brl=Decimal("2000"), limit=100))
        identifiers = []
        offset = 0
        while True:
            page = self.search.execute(ProductSearch(
                category="Violões", max_price_brl=Decimal("2000"), limit=5, offset=offset,
            ))
            self.assertEqual(page.total_count, expected.total_count)
            identifiers.extend(product.product_id for product in page.products)
            if not page.has_more:
                self.assertIsNone(page.next_offset)
                break
            self.assertGreater(page.next_offset, offset)
            offset = page.next_offset
        self.assertEqual(identifiers, [product.product_id for product in expected.products])
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertIn(104, identifiers)

    def test_exact_full_page_does_not_incorrectly_report_more_results(self):
        result = self.search.execute(ProductSearch(name="Yamaha C40", limit=1))
        self.assertEqual(result.total_count, 1)
        self.assertFalse(result.has_more)
        self.assertIsNone(result.next_offset)

    def test_empty_page_preserves_total_and_large_minimum_has_no_matches(self):
        result = self.search.execute(ProductSearch(name="Yamaha C40", offset=10**100))
        self.assertEqual(result.products, [])
        self.assertEqual(result.total_count, 1)
        self.assertFalse(result.has_more)
        self.assertEqual(self.search.execute(ProductSearch(min_price_brl=Decimal("1e100"))).total_count, 0)


class ProductSearchValidationTests(unittest.TestCase):
    def test_invalid_filters_are_rejected(self):
        cases = [
            {"name": " "}, {"category": 5}, {"max_price_brl": 100.0},
            {"max_price_brl": Decimal("NaN")}, {"max_price_brl": Decimal("Infinity")},
            {"max_price_brl": Decimal("-1")}, {"max_price_brl": Decimal("1.001")},
            {"available_only": "false"},
            {"limit": 0}, {"limit": 101}, {"limit": True},
            {"min_price_brl": 1500}, {"min_price_brl": Decimal("NaN")},
            {"min_price_brl": Decimal("-1")}, {"min_price_brl": Decimal("1.001")},
            {"min_price_brl": Decimal("2000"), "max_price_brl": Decimal("1500")},
            {"offset": -1}, {"offset": True}, {"offset": "5"},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                ProductSearch(**arguments)

    def test_large_prices_and_trailing_zeros_are_valid_application_inputs(self):
        for price in (Decimal("1e100"), Decimal("1.2300"), Decimal("0.0000")):
            with self.subTest(price=price):
                self.assertEqual(ProductSearch(max_price_brl=price).max_price_brl, price)
                self.assertEqual(ProductSearch(min_price_brl=price).min_price_brl, price)

    def test_use_case_accepts_a_catalog_without_sqlite(self):
        product = Product(1, "Violão", 5, "Violões", "Estudo", Decimal("500"), 2, "active")
        result = ProductSearchResult([product], total_count=1, offset=0, limit=20)
        received = []

        class MemoryCatalog:
            def search(self, filters):
                received.append(filters)
                return result

        filters = ProductSearch(name="Violão")
        self.assertEqual(SearchProducts(MemoryCatalog()).execute(filters), result)
        self.assertEqual(received, [filters])


if __name__ == "__main__":
    unittest.main()
