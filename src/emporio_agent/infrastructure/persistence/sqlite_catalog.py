"""Adaptador de leitura do catálogo SQLite com consultas parametrizadas."""

import sqlite3
import unicodedata
from contextlib import closing
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.ports.catalog import ProductSearch
from emporio_agent.domain.product import Product


SQLITE_MAX_INTEGER = 2**63 - 1


def _normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.strip().casefold())
        if not unicodedata.combining(char)
    )


class SQLiteCatalog:
    def __init__(self, database: Path) -> None:
        self._database = database

    def search(self, filters: ProductSearch) -> list[Product]:
        conditions = []
        parameters: list[str | int] = []
        if filters.name is not None:
            conditions.append("instr(normalize(p.name), ?) > 0")
            parameters.append(_normalize(filters.name))
        if filters.category is not None:
            conditions.append("normalize(c.name) = ?")
            parameters.append(_normalize(filters.category))
        if filters.max_price_brl is not None:
            conditions.append("p.price_cents <= ?")
            # Um teto superior à capacidade do banco inclui todos os preços armazenáveis.
            max_price = min(filters.max_price_brl, Decimal(SQLITE_MAX_INTEGER) / 100)
            parameters.append(int(max_price * 100))
        if filters.available_only:
            conditions.append("p.status = 'active' AND p.stock_quantity > 0")
        where = " AND ".join(conditions) if conditions else "1 = 1"
        parameters.append(filters.limit)
        # O SQL é montado apenas com trechos fixos; valores entram como parâmetros.
        statement = f"""
            SELECT p.product_id, p.name, p.category_id, c.name AS category_name,
                   p.description, p.price_cents, p.stock_quantity, p.status
            FROM products AS p
            JOIN categories AS c ON c.category_id = p.category_id
            WHERE {where}
            ORDER BY p.price_cents, p.product_id
            LIMIT ?
        """
        # mode=ro impede alterações e não cria um banco vazio se o caminho estiver errado.
        uri = self._database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.create_function("normalize", 1, _normalize, deterministic=True)
            connection.row_factory = sqlite3.Row
            rows = connection.execute(statement, parameters).fetchall()
        return [
            Product(
                product_id=row["product_id"], name=row["name"],
                category_id=row["category_id"], category_name=row["category_name"],
                description=row["description"], price_brl=Decimal(row["price_cents"]) / 100,
                stock_quantity=row["stock_quantity"], status=row["status"],
            )
            for row in rows
        ]
