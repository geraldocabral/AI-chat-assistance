"""Dados de uma promoção consultada no catálogo."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str
