from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Product
from .forms import ProductForm


class FakeExchangeRateResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return b'{"base":"USD","date":"2026-06-21","rates":{"JPY":157.891}}'


class ProductCalculationTests(TestCase):
    def test_profit_values_are_calculated_from_inputs(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Vintage Bag",
            purchase_price_jpy=10000,
            expected_sale_price_usd=Decimal("150.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
            ebay_fee_rate=Decimal("13.25"),
        )

        self.assertEqual(product.sale_price_jpy, 22500)
        self.assertEqual(product.ebay_fee_jpy, 2981)
        self.assertEqual(product.profit_jpy, 7019)
        self.assertEqual(product.profit_rate, Decimal("31.2"))

    def test_default_ebay_fee_rate_is_conservative(self):
        product = Product(
            owner=get_user_model().objects.create_user(username="seller", password="pass"),
            title="Default Fee Item",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
        )

        self.assertEqual(product.ebay_fee_rate, Decimal("15.00"))

    def test_product_form_initial_ebay_fee_rate_is_15_percent(self):
        form = ProductForm()
        self.assertEqual(form.fields["ebay_fee_rate"].initial, Decimal("15.00"))
        self.assertIn("15%", form.fields["actual_ebay_fee_jpy"].help_text)

    def test_actual_ebay_fee_defaults_to_15_percent_estimate_when_blank(self):
        product = Product(
            owner=get_user_model().objects.create_user(username="seller", password="pass"),
            title="Actual Fee Estimate",
            purchase_price_jpy=10000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            actual_sale_price_usd=Decimal("100.00"),
            actual_exchange_rate=Decimal("150.00"),
        )

        self.assertEqual(product.ebay_fee_rate, Decimal("15.00"))
        self.assertEqual(product.estimated_actual_ebay_fee_jpy, 2250)
        self.assertEqual(product.actual_fee_for_profit_jpy, 2250)

    def test_actual_profit_and_timing_values_are_calculated(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Watch",
            purchase_price_jpy=10000,
            purchase_shipping_jpy=1000,
            other_cost_jpy=500,
            expected_sale_price_usd=Decimal("150.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
            ebay_fee_rate=Decimal("13.25"),
            purchase_date=date(2026, 6, 1),
            listed_date=date(2026, 6, 5),
            sold_date=date(2026, 6, 15),
            actual_sale_price_usd=Decimal("180.00"),
            actual_exchange_rate=Decimal("152.00"),
            actual_shipping_cost_jpy=2800,
            actual_ebay_fee_jpy=3600,
        )

        self.assertEqual(product.actual_sale_price_jpy, 27360)
        self.assertEqual(product.actual_profit_jpy, 9460)
        self.assertEqual(product.actual_profit_rate, Decimal("34.6"))
        self.assertEqual(product.days_to_sell, 10)
        self.assertEqual(product.holding_days, 14)
        self.assertEqual(product.profit_gap_jpy, 3941)
        self.assertEqual(product.roi, Decimal("82.3"))


class ProductViewTests(TestCase):
    def test_login_required_for_product_list(self):
        response = self.client.get(reverse("product_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_product_list_renders_for_owner(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Camera Lens",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
            ebay_fee_rate=Decimal("13.00"),
            status=Product.Status.LISTED,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Camera Lens")
        self.assertContains(response, "出品中")

    def test_exchange_rate_api_requires_login(self):
        response = self.client.get(reverse("exchange_rate_api"))
        self.assertEqual(response.status_code, 302)

    def test_analytics_requires_login(self):
        response = self.client.get(reverse("analytics"))
        self.assertEqual(response.status_code, 302)

    def test_analytics_renders_charts_and_insights(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Profitable Lens",
            category="Camera",
            source="Mercari",
            purchase_price_jpy=10000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            sold_date=date(2026, 6, 10),
            actual_sale_price_usd=Decimal("140.00"),
            actual_exchange_rate=Decimal("150.00"),
            actual_shipping_cost_jpy=2000,
        )
        Product.objects.create(
            owner=user,
            title="Loss Item",
            category="Watch",
            source="Yahoo Auction",
            purchase_price_jpy=20000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
            sold_date=date(2026, 6, 12),
            actual_sale_price_usd=Decimal("100.00"),
            actual_exchange_rate=Decimal("150.00"),
            actual_shipping_cost_jpy=3000,
        )
        Product.objects.create(
            owner=user,
            title="Long Inventory",
            category="Bag",
            source="Thrift",
            purchase_price_jpy=5000,
            expected_sale_price_usd=Decimal("80.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            purchase_date=date(2026, 1, 1),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "月別 実利益")
        self.assertContains(response, "category-profit-labels")
        self.assertContains(response, "Loss Item")
        self.assertContains(response, "Long Inventory")

    @patch("profittracker.views.urlopen", return_value=FakeExchangeRateResponse())
    def test_exchange_rate_api_returns_usd_jpy_rate(self, mocked_urlopen):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        self.client.force_login(user)

        response = self.client.get(reverse("exchange_rate_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rate"], "157.89")
        self.assertEqual(response.json()["provider"], "Frankfurter")
