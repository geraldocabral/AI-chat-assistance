"""Condições de pagamento de um produto consultado no catálogo."""

from dataclasses import dataclass

from emporio_agent.application.ports.product_details import ProductDetailsReader
from emporio_agent.application.use_cases.get_product_details import GetProductDetails
from emporio_agent.domain.payment import PaymentQuote, calculate_payment_quote
from emporio_agent.domain.product import Product


@dataclass(frozen=True)
class ProductPaymentOptions:
    product: Product
    quote: PaymentQuote | None


class GetPaymentOptions:
    def __init__(self, catalog: ProductDetailsReader) -> None:
        self._get_details = GetProductDetails(catalog)

    def execute(self, product_id: int) -> ProductPaymentOptions | None:
        details = self._get_details.execute(product_id)
        if details is None:
            return None
        quote = None
        if details.product.is_available:
            quote = calculate_payment_quote(details.product.price_brl, details.active_promotions)
        return ProductPaymentOptions(product=details.product, quote=quote)
