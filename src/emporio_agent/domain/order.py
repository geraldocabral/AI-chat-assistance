"""Informações de pedido necessárias para o atendimento ao cliente."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    product_name: str
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: int
    order_date: date
    status: str
    total_brl: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    cancellation_reason: str | None
    items: tuple[OrderItem, ...]
