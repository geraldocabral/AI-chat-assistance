"""Contrato de consulta ao catálogo, independente do armazenamento."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from emporio_agent.domain.product import Product


@dataclass(frozen=True)
class ProductSearch:
    """Filtros de busca; limites inclusivos sobre o preço de tabela."""

    name: str | None = None
    category: str | None = None
    max_price_brl: Decimal | None = None
    min_price_brl: Decimal | None = None
    available_only: bool = True
    limit: int = 20
    offset: int = 0

    def __post_init__(self) -> None:
        for field in ("name", "category"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field}: informe um texto não vazio")
        for field in ("min_price_brl", "max_price_brl"):
            price = getattr(self, field)
            if price is None:
                continue
            if not isinstance(price, Decimal) or not price.is_finite() or price < 0:
                raise ValueError(f"{field}: informe um Decimal finito e não negativo")
            _, digits, exponent = price.as_tuple()
            # Zeros após os centavos são permitidos, como em Decimal("1.2300").
            if exponent < -2 and any(digits[exponent + 2:]):
                raise ValueError(f"{field}: valor tem frações de centavo")
        if self.min_price_brl is not None and self.max_price_brl is not None:
            if self.min_price_brl > self.max_price_brl:
                raise ValueError("O preço mínimo não pode superar o máximo")
        if type(self.available_only) is not bool:
            raise ValueError("available_only: informe um booleano")
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit: informe um inteiro entre 1 e 100")
        if type(self.offset) is not int or self.offset < 0:
            raise ValueError("offset: informe um inteiro não negativo")


@dataclass(frozen=True)
class ProductSearchResult:
    products: list[Product]
    total_count: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.products) < self.total_count

    @property
    def next_offset(self) -> int | None:
        return self.offset + len(self.products) if self.has_more else None


class Catalog(Protocol):
    def search(self, filters: ProductSearch) -> ProductSearchResult:
        """Busca por trecho do nome e categoria exata, ignorando caixa e acentos.

        Filtra antes de paginar e informa o total exato para os mesmos filtros.
        Retorna até limit produtos a partir de offset, ordenados por preço e ID.
        available_only restringe a produtos ativos com estoque positivo.
        """
        ...
