from django import forms

from .models import Product


class ProductForm(forms.ModelForm):
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
        for field in self.fields.values():
            css = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css


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
