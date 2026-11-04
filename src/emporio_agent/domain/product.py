"""Dados de catálogo e regra de disponibilidade de um produto."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    category_id: int
    category_name: str
    description: str
    price_brl: Decimal
    stock_quantity: int
    status: str

    @property
    def is_available(self) -> bool:
        return self.status == "active" and self.stock_quantity > 0
