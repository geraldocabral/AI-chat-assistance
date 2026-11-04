"""Consulta somente para leitura, filtrando pedido e proprietário no SQL."""

import sqlite3
from contextlib import closing
from datetime import date
from decimal import Decimal
from pathlib import Path

from emporio_agent.domain.order import Order, OrderItem


SQLITE_MAX_INTEGER = 2**63 - 1


class SQLiteOrderReader:
    def __init__(self, database: Path) -> None:
        self._database = database

    def get_for_customer(self, order_id: int, customer_id: int) -> Order | None:
        if order_id > SQLITE_MAX_INTEGER or customer_id > SQLITE_MAX_INTEGER:
            return None
        uri = self._database.resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT order_id, order_date, status, total_cents, payment_method,
                       tracking_code, estimated_delivery, notes
                FROM orders WHERE order_id = ? AND customer_id = ?
                """,
                (order_id, customer_id),
            ).fetchone()
            if row is None:
                return None
            items = connection.execute(
                """
                SELECT i.product_id, p.name, i.quantity
                FROM order_items AS i
                JOIN products AS p ON p.product_id = i.product_id
                WHERE i.order_id = ?
                ORDER BY i.product_id
                """,
                (order_id,),
            ).fetchall()
        return Order(
            order_id=row["order_id"],
            order_date=date.fromisoformat(row["order_date"]),
            status=row["status"],
            total_brl=Decimal(row["total_cents"]) / 100,
            payment_method=row["payment_method"],
            tracking_code=row["tracking_code"],
            estimated_delivery=(
                date.fromisoformat(row["estimated_delivery"]) if row["estimated_delivery"] else None
            ),
            cancellation_reason=row["notes"] if row["status"] == "cancelled" else None,
            items=tuple(
                OrderItem(product_id=item["product_id"], product_name=item["name"], quantity=item["quantity"])
                for item in items
            ),
        )
