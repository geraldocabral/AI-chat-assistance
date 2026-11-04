"""Construção transacional do banco local a partir dos CSVs validados.

Execute na raiz do repositório após instalar o pacote:
python -m emporio_agent.infrastructure.persistence.sqlite_import
"""

import argparse
import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from emporio_agent.infrastructure.persistence.csv_source import COLUMNS, load_csv_data


SCHEMA = {
    "categories": "category_id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL",
    "customers": "customer_id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, email TEXT NOT NULL, city TEXT NOT NULL",
    "products": """
        product_id INTEGER PRIMARY KEY, price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
        name TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(category_id),
        description TEXT NOT NULL, stock_quantity INTEGER NOT NULL CHECK(stock_quantity >= 0),
        status TEXT NOT NULL CHECK(status IN ('active', 'discontinued', 'coming_soon')),
        specs TEXT NOT NULL, created_at TEXT NOT NULL
    """,
    "promotions": """
        promotion_id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(product_id),
        discount_percent TEXT NOT NULL, description TEXT NOT NULL,
        is_active INTEGER NOT NULL CHECK(is_active IN (0, 1))
    """,
    "orders": """
        order_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
        order_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
        total_cents INTEGER NOT NULL CHECK(total_cents >= 0), payment_method TEXT NOT NULL,
        tracking_code TEXT, estimated_delivery TEXT, notes TEXT
    """,
    "order_items": """
        order_id INTEGER NOT NULL REFERENCES orders(order_id), quantity INTEGER NOT NULL CHECK(quantity > 0),
        product_id INTEGER NOT NULL REFERENCES products(product_id), PRIMARY KEY(order_id, product_id)
    """,
}

MONEY_COLUMNS = {"price_brl": "price_cents", "total_brl": "total_cents"}


def _sqlite_value(column: str, value: Any) -> Any:
    if column in MONEY_COLUMNS:
        cents = int(value * 100)
        if not 0 <= cents <= 2**63 - 1:
            raise ValueError(f"{column}: valor excede a capacidade de armazenamento em centavos")
        return cents
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def import_csv_to_sqlite(source: Path, destination: Path) -> dict[str, int]:
    """Recria as seis tabelas em uma transação, preservando o banco se houver erro.

    O destino deve ser um banco dedicado aos dados importados. Cada conexão
    futura de consulta também deve ativar PRAGMA foreign_keys = ON.
    """
    tables = load_csv_data(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(destination)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN")
        for table in reversed(SCHEMA):
            connection.execute(f'DROP TABLE IF EXISTS "{table}"')
        for table, definition in SCHEMA.items():
            connection.execute(f'CREATE TABLE "{table}" ({definition})')
            columns = COLUMNS[table]
            names = ", ".join(MONEY_COLUMNS.get(column, column) for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            connection.executemany(
                f'INSERT INTO "{table}" ({names}) VALUES ({placeholders})',
                [tuple(_sqlite_value(column, row[column]) for column in columns) for row in tables[table]],
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {table: len(rows) for table, rows in tables.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa os CSVs para um banco SQLite local dedicado.")
    parser.add_argument("--source", type=Path, default=Path("data"))
    parser.add_argument("--database", type=Path, default=Path("var/store.sqlite3"))
    args = parser.parse_args()
    try:
        counts = import_csv_to_sqlite(args.source, args.database)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"Falha na importação: {error}\n")
    print(f"Banco gerado: {args.database}")
    for table, count in counts.items():
        print(f"{table}: {count} registros")


if __name__ == "__main__":
    main()
