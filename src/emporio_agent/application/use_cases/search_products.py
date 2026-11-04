"""Busca de catálogo sem conhecimento da implementação de persistência."""

from emporio_agent.application.ports.catalog import Catalog, ProductSearch
from emporio_agent.domain.product import Product


class SearchProducts:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog

    def execute(self, filters: ProductSearch) -> list[Product]:
        return self._catalog.search(filters)
