"""Verifica importação real e falhas em cópias temporárias das fontes."""

import csv
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.infrastructure.persistence.csv_source import DataValidationError, load_csv_data
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


SOURCE = Path(__file__).resolve().parents[1] / "data"


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "data"
        self.source.mkdir()
        for path in SOURCE.glob("*.csv"):
            shutil.copyfile(path, self.source / path.name)
        self.database = self.root / "store.sqlite3"

    def edit_table(self, table, edit):
        path = self.source / f"{table}.csv"
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            rows = list(reader)
        edit(rows)
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_source_types_and_optional_fields(self):
        tables = load_csv_data(self.source)
        self.assertEqual(tables["products"][0]["price_brl"], Decimal("599.9"))
        self.assertIsInstance(tables["products"][0]["created_at"], date)
        self.assertEqual(tables["products"][0]["stock_quantity"], 12)
        self.assertIsNone(tables["orders"][0]["notes"])

    def test_import_counts_money_nulls_and_foreign_keys(self):
        tables = load_csv_data(self.source)
        counts = import_csv_to_sqlite(self.source, self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            for table, rows in tables.items():
                self.assertEqual(counts[table], len(rows))
                self.assertEqual(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], len(rows))
            self.assertEqual(connection.execute("SELECT price_cents FROM products WHERE product_id=81").fetchone()[0], 59990)
            self.assertIsNone(connection.execute("SELECT notes FROM orders WHERE order_id=1").fetchone()[0])
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("SELECT total_cents FROM orders WHERE order_id=3").fetchone()[0], 345000)

    def test_reimport_does_not_duplicate_records(self):
        first = import_csv_to_sqlite(self.source, self.database)
        self.assertEqual(import_csv_to_sqlite(self.source, self.database), first)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM products").fetchone()[0], first["products"])

    def test_invalid_values_report_file_line_and_field(self):
        cases = [
            ("price_brl", "NaN"), ("price_brl", "-1"), ("price_brl", "1.001"),
            ("stock_quantity", "-1"), ("created_at", "2026-02-30"),
            ("specs", "[]"), ("specs", "invalid"), ("status", "unknown"), ("name", ""),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                shutil.copyfile(SOURCE / "products.csv", self.source / "products.csv")
                self.edit_table("products", lambda rows: rows[0].update({field: value}))
                with self.assertRaisesRegex(DataValidationError, f"products.csv, linha 2, campo {field}"):
                    load_csv_data(self.source)

    def test_duplicate_key_rejected(self):
        self.edit_table("order_items", lambda rows: rows.append(rows[0].copy()))
        with self.assertRaisesRegex(DataValidationError, "chave duplicada"):
            load_csv_data(self.source)

    def test_missing_reference_rejected_before_creating_database(self):
        self.edit_table("products", lambda rows: rows[0].update(category_id="9999"))
        with self.assertRaisesRegex(DataValidationError, "referência inexistente"):
            import_csv_to_sqlite(self.source, self.database)
        self.assertFalse(self.database.exists())

    def test_missing_file_or_column_rejected(self):
        path = self.source / "categories.csv"
        path.unlink()
        with self.assertRaisesRegex(DataValidationError, "categories.csv: falha na leitura"):
            load_csv_data(self.source)
        path.write_text("category_id,name\n1,Guitarras\n", encoding="utf-8")
        with self.assertRaisesRegex(DataValidationError, "colunas incompatíveis"):
            load_csv_data(self.source)

    def test_failed_rebuild_restores_previous_database(self):
        import_csv_to_sqlite(self.source, self.database)
        # Válido como Decimal, mas grande demais para um inteiro SQLite.
        self.edit_table("products", lambda rows: rows[0].update(price_brl="100000000000000000"))
        with self.assertRaisesRegex(ValueError, "capacidade de armazenamento"):
            import_csv_to_sqlite(self.source, self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("SELECT price_cents FROM products WHERE product_id=81").fetchone()[0], 59990)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
