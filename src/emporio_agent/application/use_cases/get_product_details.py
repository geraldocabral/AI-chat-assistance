"""Consulta de produto por identificador, incluindo os indisponíveis."""

from emporio_agent.application.ports.product_details import ProductDetails, ProductDetailsReader


class GetProductDetails:
    def __init__(self, catalog: ProductDetailsReader) -> None:
        self._catalog = catalog

    def execute(self, product_id: int) -> ProductDetails | None:
        if type(product_id) is not int or product_id < 1:
            raise ValueError("product_id: informe um inteiro positivo")
        return self._catalog.get_details(product_id)
