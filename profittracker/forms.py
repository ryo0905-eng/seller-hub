from django import forms
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .models import Product, SellerSettings


class ProductForm(forms.ModelForm):
    expected_sale_price_jpy_input = forms.IntegerField(
        label="想定売価JPY",
        min_value=1,
        required=False,
        help_text="円で入力すると、為替を使ってUSDへ自動換算します。",
    )

    class Meta:
        model = Product
        fields = [
            "sku",
            "title",
            "brand",
            "category",
            "condition",
            "quantity",
            "source",
            "purchase_price_jpy",
            "purchase_shipping_jpy",
            "other_cost_jpy",
            "expected_sale_price_usd",
            "shipping_cost_jpy",
            "exchange_rate",
            "ebay_fee_rate",
            "purchase_date",
            "listed_date",
            "sold_date",
            "shipped_date",
            "actual_sale_price_usd",
            "actual_exchange_rate",
            "actual_shipping_cost_jpy",
            "actual_ebay_fee_jpy",
            "listing_url",
            "purchase_url",
            "image_url",
            "buyer_country",
            "tracking_number",
            "status",
            "memo",
        ]
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "listed_date": forms.DateInput(attrs={"type": "date"}),
            "sold_date": forms.DateInput(attrs={"type": "date"}),
            "shipped_date": forms.DateInput(attrs={"type": "date"}),
            "memo": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "actual_ebay_fee_jpy": "未入力の場合は、eBay手数料率 15% を基準に実売価格から自動概算します。",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["expected_sale_price_usd"].required = False
        self.fields["expected_sale_price_usd"].help_text = "USDまたはJPYのどちらかを入力してください。"
        self.fields["expected_sale_price_usd"].widget.attrs["data-sale-price-usd"] = "true"
        self.fields["expected_sale_price_jpy_input"].widget.attrs["data-sale-price-jpy"] = "true"
        self.fields["exchange_rate"].widget.attrs["data-sale-price-exchange-rate"] = "true"

        if not self.is_bound:
            self.set_initial_expected_sale_price_jpy()

        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css

    @staticmethod
    def yen(value):
        return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def set_initial_expected_sale_price_jpy(self):
        if self.initial.get("expected_sale_price_jpy_input"):
            return

        usd = self.initial.get("expected_sale_price_usd")
        rate = self.initial.get("exchange_rate")
        if usd is None and self.instance and self.instance.pk:
            usd = self.instance.expected_sale_price_usd
        if rate is None and self.instance and self.instance.pk:
            rate = self.instance.exchange_rate

        if usd in (None, "") or rate in (None, ""):
            return

        try:
            self.initial["expected_sale_price_jpy_input"] = self.yen(Decimal(str(usd)) * Decimal(str(rate)))
        except (InvalidOperation, TypeError, ValueError):
            return

    def clean(self):
        cleaned_data = super().clean()
        usd = cleaned_data.get("expected_sale_price_usd")
        jpy = cleaned_data.get("expected_sale_price_jpy_input")
        exchange_rate = cleaned_data.get("exchange_rate")

        if usd is None and jpy is None:
            self.add_error("expected_sale_price_usd", "想定売価はUSDまたはJPYのどちらかを入力してください。")
            return cleaned_data

        if usd is None and jpy is not None:
            if exchange_rate is None:
                self.add_error("exchange_rate", "JPYから換算するには為替を入力してください。")
                return cleaned_data
            cleaned_data["expected_sale_price_usd"] = (Decimal(jpy) / exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return cleaned_data


class ProductQuickUpdateForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "status",
            "actual_sale_price_usd",
            "sold_date",
            "shipped_date",
            "tracking_number",
        ]
        widgets = {
            "sold_date": forms.DateInput(attrs={"type": "date"}),
            "shipped_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["actual_sale_price_usd"].widget.attrs["placeholder"] = "実売USD"
        self.fields["sold_date"].widget.attrs["placeholder"] = "売却日"
        self.fields["shipped_date"].widget.attrs["placeholder"] = "発送日"
        self.fields["tracking_number"].widget.attrs["placeholder"] = "追跡番号"
        for field in self.fields.values():
            css = "form-select form-select-sm" if isinstance(field.widget, forms.Select) else "form-control form-control-sm"
            field.widget.attrs["class"] = css


class ProductCsvImportForm(forms.Form):
    csv_file = forms.FileField(label="CSVファイル")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["csv_file"].widget.attrs["class"] = "form-control"


class SourcingSimulatorForm(forms.Form):
    title = forms.CharField(label="商品名", max_length=200, required=False)
    expected_sale_price_usd = forms.DecimalField(label="想定売価USD", max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    purchase_price_jpy = forms.IntegerField(label="仕入価格", min_value=0)
    shipping_cost_jpy = forms.IntegerField(label="送料", min_value=0, initial=0)
    exchange_rate = forms.DecimalField(label="為替", max_digits=8, decimal_places=2, min_value=Decimal("0.01"))
    ebay_fee_rate = forms.DecimalField(label="eBay手数料率", max_digits=5, decimal_places=2, min_value=0, initial=Decimal("15.00"))
    target_profit_rate = forms.DecimalField(label="目標利益率", max_digits=5, decimal_places=1, min_value=0, initial=Decimal("20.0"))
    target_roi = forms.DecimalField(label="目標ROI", max_digits=5, decimal_places=1, min_value=0, initial=Decimal("30.0"))

    def __init__(self, *args, seller_settings=None, **kwargs):
        super().__init__(*args, **kwargs)
        if seller_settings:
            self.fields["shipping_cost_jpy"].initial = seller_settings.default_shipping_cost_jpy
            self.fields["ebay_fee_rate"].initial = seller_settings.default_ebay_fee_rate
            self.fields["target_profit_rate"].initial = seller_settings.default_target_profit_rate
            self.fields["target_roi"].initial = seller_settings.default_target_roi
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class SellerSettingsForm(forms.ModelForm):
    class Meta:
        model = SellerSettings
        fields = [
            "default_target_profit_rate",
            "default_target_roi",
            "default_shipping_cost_jpy",
            "default_exchange_rate",
            "default_ebay_fee_rate",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
