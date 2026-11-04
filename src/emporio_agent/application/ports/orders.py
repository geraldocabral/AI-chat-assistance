"""Contrato de consulta restrita aos pedidos do cliente da sessão."""

from typing import Protocol

from emporio_agent.domain.order import Order


class OrderReader(Protocol):
    def get_for_customer(self, order_id: int, customer_id: int) -> Order | None:
        """Retorna None tanto para pedido inexistente quanto de outro cliente."""
        ...
