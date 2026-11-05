"""Adaptador de leitura do catálogo SQLite com consultas parametrizadas."""

import json
import sqlite3
import unicodedata
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.ports.catalog import ProductSearch, ProductSearchResult
from emporio_agent.application.ports.product_details import ProductDetails
from emporio_agent.domain.product import Product
from emporio_agent.domain.promotion import Promotion


SQLITE_MAX_INTEGER = 2**63 - 1


def _normalize(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", value.strip().casefold())
        if not unicodedata.combining(char)
    )


def _to_product(row: sqlite3.Row) -> Product:
    return Product(
        product_id=row["product_id"],
        name=row["name"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        description=row["description"],
        price_brl=Decimal(row["price_cents"]) / 100,
        stock_quantity=row["stock_quantity"],
        status=row["status"],
    )


class SQLiteCatalog:
    def __init__(self, database: Path) -> None:
        self._database = database

    def _connect(self) -> sqlite3.Connection:
        uri = self._database.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.create_function("normalize", 1, _normalize, deterministic=True)
        connection.row_factory = sqlite3.Row
        return connection

    def search(self, filters: ProductSearch) -> ProductSearchResult:
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
        if filters.min_price_brl is not None:
            if filters.min_price_brl > Decimal(SQLITE_MAX_INTEGER) / 100:
                conditions.append("0 = 1")
            else:
                conditions.append("p.price_cents >= ?")
                parameters.append(int(filters.min_price_brl * 100))
        if filters.available_only:
            conditions.append("p.status = 'active' AND p.stock_quantity > 0")
        where = " AND ".join(conditions) if conditions else "1 = 1"
        # O SQL é montado apenas com trechos fixos; valores entram como parâmetros.
        statement = f"""
            SELECT p.product_id, p.name, p.category_id, c.name AS category_name,
                   p.description, p.price_cents, p.stock_quantity, p.status
            FROM products AS p
            JOIN categories AS c ON c.category_id = p.category_id
            WHERE {where}
            ORDER BY p.price_cents, p.product_id
            LIMIT ? OFFSET ?
        """
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                f"""SELECT COUNT(*) FROM products AS p
                    JOIN categories AS c ON c.category_id = p.category_id
                    WHERE {where}""",
                parameters,
            ).fetchone()[0]
            rows = connection.execute(
                statement, [*parameters, filters.limit, min(filters.offset, SQLITE_MAX_INTEGER)],
            ).fetchall()
        return ProductSearchResult(
            products=[_to_product(row) for row in rows], total_count=total,
            offset=filters.offset, limit=filters.limit,
        )

    def get_details(self, product_id: int) -> ProductDetails | None:
        if product_id > SQLITE_MAX_INTEGER:
            return None
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT p.*, c.name AS category_name
                FROM products AS p
                JOIN categories AS c ON c.category_id = p.category_id
                WHERE p.product_id = ?
                """,
                (product_id,),
            ).fetchone()
            if row is None:
                return None
            promotions = connection.execute(
                """
                SELECT promotion_id, product_id, discount_percent, description
                FROM promotions
                WHERE product_id = ? AND is_active = 1
                ORDER BY promotion_id
                """,
                (product_id,),
            ).fetchall()
        return ProductDetails(
            product=_to_product(row),
            specs=json.loads(row["specs"]),
            created_at=date.fromisoformat(row["created_at"]),
            active_promotions=tuple(
                Promotion(
                    promotion_id=promotion["promotion_id"],
                    product_id=promotion["product_id"],
                    discount_percent=Decimal(promotion["discount_percent"]),
                    description=promotion["description"],
                )
                for promotion in promotions
            )
        )
