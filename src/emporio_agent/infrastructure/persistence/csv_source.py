"""Leitura e validação dos arquivos de origem, sem modificar seu conteúdo."""

import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


class DataValidationError(ValueError):
    """Dados de origem incompatíveis com o formato esperado."""


COLUMNS = {
    "categories": ("category_id", "name", "description"),
    "customers": ("customer_id", "name", "phone", "email", "city"),
    "products": (
        "product_id", "price_brl", "name", "category_id", "description",
        "stock_quantity", "status", "specs", "created_at",
    ),
    "promotions": (
        "promotion_id", "product_id", "discount_percent", "description", "is_active",
    ),
    "orders": (
        "order_id", "customer_id", "order_date", "status", "total_brl",
        "payment_method", "tracking_code", "estimated_delivery", "notes",
    ),
    "order_items": ("order_id", "quantity", "product_id"),
}

PRIMARY_KEYS = {
    "categories": ("category_id",),
    "customers": ("customer_id",),
    "products": ("product_id",),
    "promotions": ("promotion_id",),
    "orders": ("order_id",),
    "order_items": ("order_id", "product_id"),
}

FOREIGN_KEYS = (
    ("products", "category_id", "categories"),
    ("promotions", "product_id", "products"),
    ("orders", "customer_id", "customers"),
    ("order_items", "order_id", "orders"),
    ("order_items", "product_id", "products"),
)

OPTIONAL = {"tracking_code", "estimated_delivery", "notes"}
STATUSES = {
    "products": {"active", "discontinued", "coming_soon"},
    "orders": {"pending", "confirmed", "shipped", "delivered", "cancelled"},
}


def _convert(table: str, column: str, raw: str) -> Any:
    value = raw.strip()
    if not value:
        if table == "orders" and column in OPTIONAL:
            return None
        raise ValueError("campo obrigatório vazio")

    if column.endswith("_id") or column in {"quantity", "stock_quantity", "is_active"}:
        number = int(value)
        minimum = 0 if column in {"stock_quantity", "is_active"} else 1
        if number < minimum:
            raise ValueError(f"inteiro deve ser maior ou igual a {minimum}")
        if column == "is_active" and number not in {0, 1}:
            raise ValueError("indicador deve ser 0 ou 1")
        return number

    if column in {"price_brl", "total_brl", "discount_percent"}:
        number = Decimal(value)
        if not number.is_finite() or number < 0:
            raise ValueError("número deve ser finito e não negativo")
        if column == "discount_percent":
            if number > 100:
                raise ValueError("desconto deve estar entre 0 e 100")
        elif number != number.quantize(Decimal("0.01")):
            raise ValueError("valor monetário deve ter no máximo duas casas decimais")
        return number

    if column in {"created_at", "order_date", "estimated_delivery"}:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("data deve usar o formato AAAA-MM-DD")
        return parsed

    if column == "status" and value not in STATUSES[table]:
        raise ValueError("status desconhecido")
    if column == "specs" and not isinstance(json.loads(value), dict):
        raise ValueError("especificações devem conter um objeto JSON")
    return value


def load_csv_data(directory: Path) -> dict[str, list[dict[str, Any]]]:
    """Carrega todas as tabelas ou interrompe com arquivo, linha e campo do erro.

    Valores monetários são Decimal, datas são date e opcionais vazios são None.
    Valores históricos de pedidos são preservados, sem recalcular pelo catálogo.
    """
    tables: dict[str, list[dict[str, Any]]] = {}
    for table, columns in COLUMNS.items():
        path = directory / f"{table}.csv"
        rows = []
        seen = set()
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames is None or sorted(reader.fieldnames) != sorted(columns):
                    raise DataValidationError(f"{path.name}: colunas incompatíveis; esperadas: {', '.join(columns)}")
                for row in reader:
                    location = f"{path.name}, linha {reader.line_num}"
                    if None in row or any(value is None for value in row.values()):
                        raise DataValidationError(f"{location}: quantidade de campos inválida")
                    converted = {}
                    for column in columns:
                        try:
                            converted[column] = _convert(table, column, row[column])
                        except (ValueError, InvalidOperation) as error:
                            raise DataValidationError(f"{location}, campo {column}: {error}") from error
                    key = tuple(converted[column] for column in PRIMARY_KEYS[table])
                    if key in seen:
                        raise DataValidationError(f"{location}: chave duplicada {key}")
                    seen.add(key)
                    rows.append(converted)
        except (OSError, UnicodeError, csv.Error) as error:
            raise DataValidationError(f"{path.name}: falha na leitura: {error}") from error
        tables[table] = rows

    for table, column, target in FOREIGN_KEYS:
        valid_ids = {row[column] for row in tables[target]}
        for row in tables[table]:
            if row[column] not in valid_ids:
                key = tuple(row[field] for field in PRIMARY_KEYS[table])
                raise DataValidationError(
                    f"{table}.csv, chave {key}, campo {column}: referência inexistente em {target}"
                )
    return tables
