"""Contrato de consulta detalhada, separado da busca de catálogo."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from emporio_agent.domain.product import Product
from emporio_agent.domain.promotion import Promotion


@dataclass(frozen=True)
class ProductDetails:
    product: Product
    specs: dict[str, Any]
    created_at: date
    active_promotions: tuple[Promotion, ...]


class ProductDetailsReader(Protocol):
    def get_details(self, product_id: int) -> ProductDetails | None:
        """Retorna produto de qualquer status e apenas suas promoções ativas.

        Retorna None quando o produto não existe. Promoções não confirmam
        disponibilidade e não são combinadas nem escolhidas nesta consulta.
        """
        ...
