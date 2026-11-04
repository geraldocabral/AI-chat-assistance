"""Contrato de consulta ao catálogo, independente do armazenamento."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from emporio_agent.domain.product import Product


@dataclass(frozen=True)
class ProductSearch:
    """Filtros de busca; o preço máximo se refere ao preço de tabela."""

    name: str | None = None
    category: str | None = None
    max_price_brl: Decimal | None = None
    available_only: bool = True
    limit: int = 20

    def __post_init__(self) -> None:
        for field in ("name", "category"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field}: informe um texto não vazio")
        price = self.max_price_brl
        if price is not None:
            if not isinstance(price, Decimal) or not price.is_finite() or price < 0:
                raise ValueError("max_price_brl: informe um Decimal finito e não negativo")
            _, digits, exponent = price.as_tuple()
            # Zeros após os centavos são permitidos, como em Decimal("1.2300").
            if exponent < -2 and any(digits[exponent + 2:]):
                raise ValueError("max_price_brl: valor tem frações de centavo")
        if type(self.available_only) is not bool:
            raise ValueError("available_only: informe um booleano")
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit: informe um inteiro entre 1 e 100")


class Catalog(Protocol):
    def search(self, filters: ProductSearch) -> list[Product]:
        """Busca por trecho do nome e categoria exata, ignorando caixa e acentos.

        Retorna até limit produtos, ordenados por preço de tabela e identificador.
        available_only restringe a produtos ativos com estoque positivo.
        """
        ...
