"""Cálculos de preço e parcelamento, sem dependência do LLM ou do banco."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from emporio_agent.domain.promotion import Promotion


CENT = Decimal("0.01")
PIX_DISCOUNT_PERCENT = Decimal("5")


@dataclass(frozen=True)
class InstallmentPlan:
    amounts_brl: tuple[Decimal, ...]

    @property
    def count(self) -> int:
        return len(self.amounts_brl)


@dataclass(frozen=True)
class PaymentQuote:
    list_price_brl: Decimal
    sale_price_brl: Decimal
    pix_price_brl: Decimal
    applied_promotion: Promotion | None
    credit_plans: tuple[InstallmentPlan, ...]


def _minimum_installment_cents(count: int) -> int:
    if count <= 3:
        return 5000
    if count <= 6:
        return 8000
    return 10000


def _credit_plans(total: Decimal) -> tuple[InstallmentPlan, ...]:
    total_cents = int(total * 100)
    if total_cents == 0:
        return ()
    plans = [InstallmentPlan((total,))]
    for count in range(2, 13):
        base_cents, remainder = divmod(total_cents, count)
        if base_cents < _minimum_installment_cents(count):
            continue
        # Distribui os centavos restantes nas primeiras parcelas, preservando o total.
        amounts = tuple(
            Decimal(base_cents + (index < remainder)) / 100
            for index in range(count)
        )
        plans.append(InstallmentPlan(amounts))
    return tuple(plans)


def calculate_payment_quote(
    list_price: Decimal, active_promotions: tuple[Promotion, ...] = (),
) -> PaymentQuote:
    """Calcula condições de uma unidade; recebe somente promoções ativas do produto.

    Em empate de desconto, escolhe o menor identificador para resultado estável.
    A vigência e a disponibilidade são verificadas antes pelo caso de uso.
    """
    if not isinstance(list_price, Decimal) or not list_price.is_finite() or list_price < 0:
        raise ValueError("list_price: informe um Decimal finito e não negativo")
    if list_price != list_price.quantize(CENT):
        raise ValueError("list_price: valor tem frações de centavo")
    for promotion in active_promotions:
        discount = promotion.discount_percent
        if not isinstance(discount, Decimal) or not discount.is_finite() or not 0 <= discount <= 100:
            raise ValueError("discount_percent: informe um Decimal entre 0 e 100")

    promotion = min(
        active_promotions,
        key=lambda item: (-item.discount_percent, item.promotion_id),
        default=None,
    )
    discount = promotion.discount_percent if promotion else Decimal("0")
    sale_price = (list_price * (1 - discount / 100)).quantize(CENT, rounding=ROUND_HALF_UP)
    pix_price = sale_price if promotion else (
        list_price * (1 - PIX_DISCOUNT_PERCENT / 100)
    ).quantize(CENT, rounding=ROUND_HALF_UP)
    return PaymentQuote(
        list_price_brl=list_price,
        sale_price_brl=sale_price,
        pix_price_brl=pix_price,
        applied_promotion=promotion,
        credit_plans=_credit_plans(sale_price),
    )
