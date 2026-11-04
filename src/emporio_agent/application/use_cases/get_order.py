"""Consulta de pedido vinculada à identidade fornecida pela aplicação."""

from emporio_agent.application.ports.orders import OrderReader
from emporio_agent.domain.order import Order


class GetOrder:
    def __init__(self, orders: OrderReader, customer_id: int | None) -> None:
        if customer_id is not None and (type(customer_id) is not int or customer_id < 1):
            raise ValueError("customer_id: informe um inteiro positivo ou None")
        self._orders = orders
        self._customer_id = customer_id

    def execute(self, order_id: int) -> Order | None:
        if type(order_id) is not int or order_id < 1:
            raise ValueError("order_id: informe um inteiro positivo")
        if self._customer_id is None:
            raise PermissionError("Consulta de pedidos exige uma sessão com cliente identificado")
        return self._orders.get_for_customer(order_id, self._customer_id)
