from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Product, SellerSettings
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

    def test_product_form_accepts_expected_sale_price_jpy_input(self):
        form = ProductForm(
            data={
                "title": "JPY Sale Item",
                "condition": Product.Condition.USED,
                "quantity": "1",
                "purchase_price_jpy": "7000",
                "purchase_shipping_jpy": "0",
                "other_cost_jpy": "0",
                "expected_sale_price_usd": "",
                "expected_sale_price_jpy_input": "15500",
                "shipping_cost_jpy": "2500",
                "exchange_rate": "155.00",
                "ebay_fee_rate": "15.00",
                "status": Product.Status.PURCHASED,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expected_sale_price_usd"], Decimal("100.00"))

    def test_product_form_initializes_expected_sale_price_jpy_input(self):
        user = get_user_model().objects.create_user(username="jpy-seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Existing JPY Item",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("155.00"),
        )

        form = ProductForm(instance=product)

        self.assertEqual(form.initial["expected_sale_price_jpy_input"], 15500)

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

    def test_sourcing_simulator_requires_login(self):
        response = self.client.get(reverse("sourcing_simulator"))
        self.assertEqual(response.status_code, 302)

    def test_sourcing_simulator_calculates_decision(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        self.client.force_login(user)

        response = self.client.post(
            reverse("sourcing_simulator"),
            {
                "title": "Research Item",
                "expected_sale_price_usd": "100.00",
                "purchase_price_jpy": "7000",
                "shipping_cost_jpy": "2500",
                "exchange_rate": "155.00",
                "ebay_fee_rate": "15.00",
                "target_profit_rate": "20.0",
                "target_roi": "30.0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "判定")
        self.assertContains(response, "商品登録へ引き継ぐ")
        self.assertContains(response, "上限仕入価格")

    def test_seller_settings_update_and_defaults(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        self.client.force_login(user)

        response = self.client.post(
            reverse("seller_settings"),
            {
                "default_target_profit_rate": "25.0",
                "default_target_roi": "40.0",
                "default_shipping_cost_jpy": "1800",
                "default_exchange_rate": "158.25",
                "default_ebay_fee_rate": "16.00",
            },
        )

        self.assertEqual(response.status_code, 302)
        settings = SellerSettings.get_for_user(user)
        self.assertEqual(settings.default_target_profit_rate, Decimal("25.0"))
        self.assertEqual(settings.default_target_roi, Decimal("40.0"))
        self.assertEqual(settings.default_shipping_cost_jpy, 1800)
        self.assertEqual(settings.default_exchange_rate, Decimal("158.25"))
        self.assertEqual(settings.default_ebay_fee_rate, Decimal("16.00"))

        simulator_response = self.client.get(reverse("sourcing_simulator"))
        self.assertContains(simulator_response, 'value="1800"')
        self.assertContains(simulator_response, 'value="158.25"')
        self.assertContains(simulator_response, 'value="16.00"')
        self.assertContains(simulator_response, 'value="25.0"')
        self.assertContains(simulator_response, 'value="40.0"')

    def test_product_create_uses_seller_settings_defaults(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        SellerSettings.objects.create(
            owner=user,
            default_shipping_cost_jpy=2200,
            default_exchange_rate=Decimal("159.50"),
            default_ebay_fee_rate=Decimal("16.50"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="shipping_cost_jpy" value="2200"')
        self.assertContains(response, 'name="exchange_rate" value="159.50"')
        self.assertContains(response, 'name="ebay_fee_rate" value="16.50"')

    def test_product_create_accepts_simulator_initial_values(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        self.client.force_login(user)

        response = self.client.get(
            reverse("product_create"),
            {
                "title": "Research Item",
                "purchase_price_jpy": "7000",
                "expected_sale_price_usd": "100.00",
                "shipping_cost_jpy": "2500",
                "exchange_rate": "155.00",
                "ebay_fee_rate": "15.00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Research Item")
        self.assertContains(response, "100.00")

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

    def test_product_detail_renders_for_owner(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Detail Item",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_detail", args=[product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Item")
        self.assertContains(response, "基本情報")

    def test_quick_update_changes_sales_fields(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Quick Item",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("product_quick_update", args=[product.pk]),
            {
                "status": Product.Status.SOLD,
                "actual_sale_price_usd": "30.00",
                "sold_date": "2026-06-20",
                "shipped_date": "",
                "tracking_number": "TRACK123",
            },
        )

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.Status.SOLD)
        self.assertEqual(product.actual_sale_price_usd, Decimal("30.00"))
        self.assertEqual(product.sold_date, date(2026, 6, 20))
        self.assertEqual(product.tracking_number, "TRACK123")

    def test_csv_export_and_import(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Export Item",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        export_response = self.client.get(reverse("product_export"))
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("products.csv", export_response["Content-Disposition"])

        csv_content = b"title,purchase_price_jpy,expected_sale_price_usd,shipping_cost_jpy,exchange_rate\nImported Item,2000,40.00,700,150.00\n"
        import_response = self.client.post(
            reverse("product_import"),
            {"csv_file": BytesIO(csv_content)},
            format="multipart",
        )

        self.assertEqual(import_response.status_code, 302)
        self.assertTrue(Product.objects.filter(owner=user, title="Imported Item").exists())

    def test_analytics_period_filter_renders(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Filtered Sale",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
            sold_date=date(2026, 6, 20),
            actual_sale_price_usd=Decimal("30.00"),
            actual_exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("analytics"), {"period": "custom", "start": "2026-06-01", "end": "2026-06-30"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2026-06")

    @patch("profittracker.views.urlopen", return_value=FakeExchangeRateResponse())
    def test_exchange_rate_api_returns_usd_jpy_rate(self, mocked_urlopen):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        self.client.force_login(user)

        response = self.client.get(reverse("exchange_rate_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["rate"], "157.89")
        self.assertEqual(response.json()["provider"], "Frankfurter")
