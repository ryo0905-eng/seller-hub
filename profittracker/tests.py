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
        self.assertIn("販売手数料率", form.fields["actual_ebay_fee_jpy"].help_text)

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
                "expected_sale_price_jpy": "15500",
                "shipping_cost_jpy": "2500",
                "exchange_rate": "155.00",
                "ebay_fee_rate": "15.00",
                "status": Product.Status.PURCHASED,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["expected_sale_price_usd"], None)
        self.assertEqual(form.cleaned_data["expected_sale_price_jpy"], 15500)

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

        self.assertEqual(form.initial["expected_sale_price_jpy"], 15500)

    def test_jpy_sale_price_product_uses_jpy_for_profit(self):
        form = ProductForm(
            data={
                "title": "JPY Sale Item",
                "condition": Product.Condition.USED,
                "quantity": "1",
                "purchase_price_jpy": "7000",
                "purchase_shipping_jpy": "0",
                "other_cost_jpy": "0",
                "expected_sale_price_usd": "",
                "expected_sale_price_jpy": "12000",
                "shipping_cost_jpy": "1000",
                "exchange_rate": "",
                "ebay_fee_rate": "10.00",
                "status": Product.Status.PURCHASED,
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        product.owner = get_user_model().objects.create_user(username="jpy-channel-seller", password="pass")
        self.assertEqual(product.expected_sale_price_usd, None)
        self.assertEqual(product.exchange_rate, Decimal("1.00"))
        self.assertEqual(product.ebay_fee_rate, Decimal("10.00"))
        self.assertEqual(product.sale_price_jpy, 12000)
        self.assertEqual(product.ebay_fee_jpy, 1200)
        self.assertEqual(product.expected_profit_jpy, 2800)

    def test_actual_sales_channel_can_be_recorded(self):
        form = ProductForm(
            data={
                "title": "Sold on Mercari",
                "condition": Product.Condition.USED,
                "quantity": "1",
                "purchase_price_jpy": "7000",
                "purchase_shipping_jpy": "0",
                "other_cost_jpy": "0",
                "expected_sale_price_usd": "",
                "expected_sale_price_jpy": "12000",
                "shipping_cost_jpy": "1000",
                "exchange_rate": "",
                "ebay_fee_rate": "10.00",
                "status": Product.Status.SOLD,
                "actual_sales_channel": Product.SalesChannel.MERCARI,
                "actual_sale_price_jpy_manual": "12000",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["actual_sales_channel"], Product.SalesChannel.MERCARI)

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
            purchase_url="https://example.com/source",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Camera Lens")
        self.assertContains(response, "出品中")
        self.assertContains(response, "status-timeline")
        self.assertContains(response, "status-progress")
        self.assertContains(response, "status-step-current status-step-listed")
        self.assertContains(response, "価格改定ボード")
        self.assertContains(response, "仕入れ値")
        self.assertContains(response, "想定売価")
        self.assertContains(response, "赤字売価")
        self.assertContains(response, "想定利益率")
        self.assertContains(response, "想定ROI")
        self.assertContains(response, "在庫未入力")
        self.assertContains(response, "仕入れ元")
        self.assertContains(response, 'href="https://example.com/source"')
        self.assertNotContains(response, "10%値下げ")
        self.assertContains(response, "日付未入力")
        self.assertContains(response, "編集・実績入力")
        self.assertNotContains(response, "実売USD")

    def test_product_list_search_filters_products(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Camera Lens",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
        )
        Product.objects.create(
            owner=user,
            title="Vintage Watch",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"), {"q": "watch"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vintage Watch")
        self.assertNotContains(response, "Camera Lens")

    def test_product_list_hides_sold_statuses_by_default(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Active Item",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.LISTED,
        )
        Product.objects.create(
            owner=user,
            title="Sold Item",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.SOLD,
        )
        Product.objects.create(
            owner=user,
            title="Shipped Item",
            purchase_price_jpy=7000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.SHIPPED,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active Item")
        self.assertNotContains(response, "Sold Item")
        self.assertNotContains(response, "Shipped Item")

    def test_product_list_can_include_sold_statuses_when_selected(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Active Item",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.LISTED,
        )
        Product.objects.create(
            owner=user,
            title="Sold Item",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.SOLD,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("product_list"),
            {"status": [Product.Status.LISTED, Product.Status.SOLD]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active Item")
        self.assertContains(response, "Sold Item")

    def test_product_list_filters_by_multiple_statuses(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            title="Purchased Item",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.PURCHASED,
        )
        Product.objects.create(
            owner=user,
            title="Listed Item",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.LISTED,
        )
        Product.objects.create(
            owner=user,
            title="Sold Item",
            purchase_price_jpy=7000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            status=Product.Status.SOLD,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("product_list"),
            {"status": [Product.Status.PURCHASED, Product.Status.LISTED]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Purchased Item")
        self.assertContains(response, "Listed Item")
        self.assertNotContains(response, "Sold Item")

    def test_product_list_sorts_by_sku(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        Product.objects.create(
            owner=user,
            sku="B-002",
            title="Second SKU Item",
            purchase_price_jpy=12000,
            expected_sale_price_usd=Decimal("200.00"),
            shipping_cost_jpy=3000,
            exchange_rate=Decimal("150.00"),
        )
        Product.objects.create(
            owner=user,
            sku="A-001",
            title="First SKU Item",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("120.00"),
            shipping_cost_jpy=2500,
            exchange_rate=Decimal("150.00"),
        )
        Product.objects.create(
            owner=user,
            title="No SKU Item",
            purchase_price_jpy=7000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"), {"sort": "sku_asc"})

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index("First SKU Item"), content.index("Second SKU Item"))
        self.assertLess(content.index("Second SKU Item"), content.index("No SKU Item"))

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

        settings_response = self.client.get(reverse("seller_settings"))
        self.assertEqual(settings_response.status_code, 200)
        self.assertContains(settings_response, "ブランド自動入力辞書")

        response = self.client.post(
            reverse("seller_settings"),
            {
                "default_target_profit_rate": "25.0",
                "default_target_roi": "40.0",
                "default_shipping_cost_jpy": "1800",
                "default_exchange_rate": "158.25",
                "default_ebay_fee_rate": "16.00",
                "markdown_ok_days": "35",
                "markdown_review_days": "50",
                "loss_cut_days": "70",
                "long_inventory_days": "100",
                "low_profit_rate": "12.5",
                "brand_keywords": "Bottega Veneta\nPorter",
            },
        )

        self.assertEqual(response.status_code, 302)
        settings = SellerSettings.get_for_user(user)
        self.assertEqual(settings.default_target_profit_rate, Decimal("25.0"))
        self.assertEqual(settings.default_target_roi, Decimal("40.0"))
        self.assertEqual(settings.default_shipping_cost_jpy, 1800)
        self.assertEqual(settings.default_exchange_rate, Decimal("158.25"))
        self.assertEqual(settings.default_ebay_fee_rate, Decimal("16.00"))
        self.assertEqual(settings.markdown_ok_days, 35)
        self.assertEqual(settings.markdown_review_days, 50)
        self.assertEqual(settings.loss_cut_days, 70)
        self.assertEqual(settings.long_inventory_days, 100)
        self.assertEqual(settings.low_profit_rate, Decimal("12.5"))
        self.assertEqual(settings.brand_keyword_list, ["Bottega Veneta", "Porter"])

        simulator_response = self.client.get(reverse("sourcing_simulator"))
        self.assertContains(simulator_response, 'value="1800"')
        self.assertContains(simulator_response, 'value="158.25"')
        self.assertContains(simulator_response, 'value="16.00"')
        self.assertContains(simulator_response, 'value="25.0"')
        self.assertContains(simulator_response, 'value="40.0"')

    def test_product_list_uses_seller_pricing_rule_settings(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        SellerSettings.objects.create(
            owner=user,
            markdown_ok_days=60,
            markdown_review_days=75,
            loss_cut_days=90,
            long_inventory_days=120,
            low_profit_rate=Decimal("10.0"),
        )
        Product.objects.create(
            owner=user,
            title="Custom Rule Item",
            purchase_price_jpy=5000,
            expected_sale_price_usd=Decimal("100.00"),
            shipping_cost_jpy=1000,
            exchange_rate=Decimal("150.00"),
            purchase_date=date(2026, 5, 10),
            status=Product.Status.LISTED,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom Rule Item")
        self.assertContains(response, "維持")

    def test_product_create_uses_seller_settings_defaults(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        SellerSettings.objects.create(
            owner=user,
            default_shipping_cost_jpy=2200,
            default_exchange_rate=Decimal("159.50"),
            default_ebay_fee_rate=Decimal("16.50"),
            brand_keywords="Bottega Veneta\nPorter",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="shipping_cost_jpy" value="2200"')
        self.assertContains(response, 'name="exchange_rate" value="159.50"')
        self.assertContains(response, 'name="ebay_fee_rate" value="16.50"')
        self.assertContains(response, "brand-keywords-data")
        self.assertContains(response, "Bottega Veneta")

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
        Product.objects.create(
            owner=user,
            title="Missing Actual",
            category="Camera",
            source="Mercari",
            purchase_price_jpy=8000,
            expected_sale_price_usd=Decimal("90.00"),
            shipping_cost_jpy=2000,
            exchange_rate=Decimal("150.00"),
            sold_date=date(2026, 6, 15),
            status=Product.Status.SOLD,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("analytics"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "月別 実利益")
        self.assertContains(response, "販売数")
        self.assertContains(response, "平均利益")
        self.assertContains(response, "赤字率")
        self.assertContains(response, "カテゴリ別パフォーマンス")
        self.assertContains(response, "想定より下振れ")
        self.assertContains(response, "実績入力待ち")
        self.assertContains(response, "category-profit-labels")
        self.assertContains(response, "Loss Item")
        self.assertContains(response, "Missing Actual")
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
        self.assertContains(response, "削除")

    def test_product_delete_confirmation_renders_before_delete(self):
        user = get_user_model().objects.create_user(username="seller", password="pass")
        product = Product.objects.create(
            owner=user,
            title="Delete Candidate",
            purchase_price_jpy=1000,
            expected_sale_price_usd=Decimal("20.00"),
            shipping_cost_jpy=500,
            exchange_rate=Decimal("150.00"),
        )
        self.client.force_login(user)

        response = self.client.get(reverse("product_delete", args=[product.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "商品を削除しますか？")
        self.assertContains(response, "Delete Candidate")

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
