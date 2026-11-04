"""Regras de descontos, limites de parcelamento e consulta de pagamento."""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from emporio_agent.application.use_cases.get_payment_options import GetPaymentOptions
from emporio_agent.domain.payment import calculate_payment_quote
from emporio_agent.domain.promotion import Promotion
from emporio_agent.infrastructure.persistence.sqlite_catalog import SQLiteCatalog
from emporio_agent.infrastructure.persistence.sqlite_import import import_csv_to_sqlite


class PaymentRulesTests(unittest.TestCase):
    def test_pix_discount_without_promotion(self):
        quote = calculate_payment_quote(Decimal("599.90"))
        self.assertEqual(quote.sale_price_brl, Decimal("599.90"))
        self.assertEqual(quote.pix_price_brl, Decimal("569.91"))
        self.assertIsNone(quote.applied_promotion)

    def test_promotion_replaces_pix_discount(self):
        promotion = Promotion(1, 81, Decimal("10"), "Oferta")
        quote = calculate_payment_quote(Decimal("1000"), (promotion,))
        self.assertEqual(quote.sale_price_brl, Decimal("900"))
        self.assertEqual(quote.pix_price_brl, Decimal("900"))
        self.assertEqual(quote.applied_promotion, promotion)

    def test_best_promotion_and_tie_break_are_stable(self):
        smaller = Promotion(1, 81, Decimal("10"), "Oferta A")
        best = Promotion(2, 81, Decimal("20"), "Oferta B")
        tie = Promotion(3, 81, Decimal("20"), "Oferta C")
        for promotions in ((smaller, best, tie), (tie, best, smaller)):
            quote = calculate_payment_quote(Decimal("1000"), promotions)
            self.assertEqual(quote.sale_price_brl, Decimal("800"))
            self.assertEqual(quote.applied_promotion, best)

    def test_small_promotion_does_not_accumulate_or_get_replaced_by_pix(self):
        quote = calculate_payment_quote(
            Decimal("100"), (Promotion(1, 81, Decimal("2"), "Oferta"),),
        )
        self.assertEqual(quote.pix_price_brl, Decimal("98"))

    def test_half_cent_uses_half_up_rounding(self):
        self.assertEqual(calculate_payment_quote(Decimal("0.30")).pix_price_brl, Decimal("0.29"))
        quote = calculate_payment_quote(
            Decimal("0.05"), (Promotion(1, 81, Decimal("10"), "Oferta"),),
        )
        self.assertEqual(quote.sale_price_brl, Decimal("0.05"))

    def test_installment_thresholds_are_inclusive(self):
        for count, minimum_total in ((2, "100"), (3, "150"), (4, "320"), (6, "480"), (7, "700"), (12, "1200")):
            with self.subTest(count=count):
                threshold = Decimal(minimum_total)
                below = calculate_payment_quote(threshold - Decimal("0.01"))
                exact = calculate_payment_quote(threshold)
                self.assertNotIn(count, [plan.count for plan in below.credit_plans])
                self.assertIn(count, [plan.count for plan in exact.credit_plans])

    def test_remainder_preserves_total_and_smallest_installment(self):
        quote = calculate_payment_quote(Decimal("1000"))
        plan = next(plan for plan in quote.credit_plans if plan.count == 3)
        self.assertEqual(plan.amounts_brl, (Decimal("333.34"), Decimal("333.33"), Decimal("333.33")))
        for plan in quote.credit_plans:
            self.assertEqual(sum(plan.amounts_brl), quote.sale_price_brl)
            self.assertLessEqual(plan.count, 12)

    def test_promotion_can_reduce_available_installments(self):
        quote = calculate_payment_quote(
            Decimal("1200"), (Promotion(1, 81, Decimal("10"), "Oferta"),),
        )
        self.assertNotIn(12, [plan.count for plan in quote.credit_plans])
        self.assertEqual(max(plan.count for plan in quote.credit_plans), 10)

    def test_small_or_zero_total(self):
        quote = calculate_payment_quote(Decimal("49.99"))
        self.assertEqual([plan.count for plan in quote.credit_plans], [1])
        self.assertEqual(calculate_payment_quote(Decimal("0")).credit_plans, ())
        free = calculate_payment_quote(
            Decimal("100"), (Promotion(1, 81, Decimal("100"), "Oferta"),),
        )
        self.assertEqual(free.pix_price_brl, Decimal("0"))
        self.assertEqual(free.credit_plans, ())

    def test_invalid_values_are_rejected(self):
        for price in (100.0, Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), Decimal("1.001")):
            with self.subTest(price=price), self.assertRaises(ValueError):
                calculate_payment_quote(price)
        for discount in (Decimal("-1"), Decimal("101"), Decimal("NaN"), 10):
            with self.subTest(discount=discount), self.assertRaises(ValueError):
                calculate_payment_quote(Decimal("100"), (Promotion(1, 81, discount, "Oferta"),))


class PaymentOptionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = Path(self.temp.name) / "store.sqlite3"
        import_csv_to_sqlite(Path(__file__).resolve().parents[1] / "data", database)
        self.get_options = GetPaymentOptions(SQLiteCatalog(database))

    def test_reads_active_promotion_and_calculates_prices(self):
        result = self.get_options.execute(94)
        self.assertEqual(result.quote.list_price_brl, Decimal("5999"))
        self.assertEqual(result.quote.sale_price_brl, Decimal("5519.08"))
        self.assertEqual(result.quote.pix_price_brl, Decimal("5519.08"))
        self.assertEqual(result.quote.applied_promotion.promotion_id, 24)

    def test_inactive_promotion_does_not_prevent_pix_discount(self):
        result = self.get_options.execute(93)
        self.assertIsNone(result.quote.applied_promotion)
        self.assertEqual(result.quote.pix_price_brl, Decimal("10924.05"))

    def test_unavailable_product_has_no_payment_offer(self):
        for product_id in (96, 113, 130, 136):
            with self.subTest(product_id=product_id):
                result = self.get_options.execute(product_id)
                self.assertFalse(result.product.is_available)
                self.assertIsNone(result.quote)

    def test_nonexistent_and_invalid_products(self):
        self.assertIsNone(self.get_options.execute(9999))
        with self.assertRaises(ValueError):
            self.get_options.execute(True)


if __name__ == "__main__":
    unittest.main()
