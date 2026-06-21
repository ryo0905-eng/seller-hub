import csv
import io
import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import ProductCsvImportForm, ProductForm, ProductQuickUpdateForm
from .models import Product


@login_required
def exchange_rate_api(request):
    try:
        api_request = Request(
            settings.EXCHANGE_RATE_API_URL,
            headers={"User-Agent": "eBay-Profit-Tracker/1.0"},
        )
        with urlopen(api_request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rate = Decimal(str(payload["rates"]["JPY"]))
    except (KeyError, InvalidOperation, TypeError, ValueError, URLError, TimeoutError) as exc:
        return JsonResponse(
            {"ok": False, "error": "為替レートを取得できませんでした。手入力してください。"},
            status=503,
        )

    return JsonResponse(
        {
            "ok": True,
            "base": payload.get("base", "USD"),
            "target": "JPY",
            "rate": str(rate.quantize(Decimal("0.01"))),
            "date": payload.get("date", ""),
            "provider": "Frankfurter",
        }
    )


class OwnerQuerysetMixin(LoginRequiredMixin):
    model = Product

    def get_queryset(self):
        return Product.objects.filter(owner=self.request.user)


class ProductListView(OwnerQuerysetMixin, ListView):
    template_name = "profittracker/product_list.html"
    context_object_name = "products"

    def get_queryset(self):
        queryset = super().get_queryset()
        status = self.request.GET.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = list(self.get_queryset())
        sold_products = [product for product in products if product.actual_profit_jpy is not None]
        days_to_sell = [product.days_to_sell for product in products if product.days_to_sell is not None]
        context["status_choices"] = Product.Status.choices
        context["quick_update_forms"] = {product.pk: ProductQuickUpdateForm(instance=product) for product in products}
        context["current_status"] = self.request.GET.get("status", "")
        context["total_profit"] = sum(product.expected_profit_jpy for product in products)
        context["total_actual_profit"] = sum(product.actual_profit_jpy for product in sold_products)
        context["inventory_value"] = sum(product.inventory_value_jpy for product in products)
        context["average_days_to_sell"] = round(sum(days_to_sell) / len(days_to_sell), 1) if days_to_sell else None
        context["product_count"] = len(products)
        context["status_counts"] = dict(
            self.request.user.products.values("status").annotate(total=Count("id")).values_list("status", "total")
        )
        return context


class AnalyticsView(LoginRequiredMixin, TemplateView):
    template_name = "profittracker/analytics.html"

    @staticmethod
    def add_to_group(groups, key, amount):
        groups[key] = groups.get(key, 0) + amount

    def get_date_range(self):
        today = timezone.localdate()
        period = self.request.GET.get("period", "all")
        start = None
        end = None

        if period == "this_month":
            start = today.replace(day=1)
            end = today
        elif period == "last_month":
            first_this_month = today.replace(day=1)
            end = first_this_month - timedelta(days=1)
            start = end.replace(day=1)
        elif period == "last_3_months":
            start = today - timedelta(days=90)
            end = today
        elif period == "this_year":
            start = today.replace(month=1, day=1)
            end = today
        elif period == "custom":
            try:
                start = timezone.datetime.fromisoformat(self.request.GET.get("start", "")).date()
            except ValueError:
                start = None
            try:
                end = timezone.datetime.fromisoformat(self.request.GET.get("end", "")).date()
            except ValueError:
                end = None

        return period, start, end

    @staticmethod
    def in_range(product, start, end):
        if start is None and end is None:
            return True
        if product.sold_date is None:
            return False
        if start and product.sold_date < start:
            return False
        if end and product.sold_date > end:
            return False
        return True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = list(Product.objects.filter(owner=self.request.user))
        period, start_date, end_date = self.get_date_range()
        filtered_products = [product for product in products if self.in_range(product, start_date, end_date)]
        actual_products = [product for product in filtered_products if product.actual_profit_jpy is not None]
        days_to_sell = [product.days_to_sell for product in filtered_products if product.days_to_sell is not None]
        roi_values = [product.roi for product in actual_products]

        monthly_profit = {}
        category_profit = {}
        source_profit = {}
        status_counts = {label: 0 for value, label in Product.Status.choices}

        for product in products:
            status_counts[product.get_status_display()] = status_counts.get(product.get_status_display(), 0) + 1

        for product in filtered_products:
            if product.actual_profit_jpy is None:
                continue

            if product.sold_date:
                month_key = product.sold_date.strftime("%Y-%m")
                self.add_to_group(monthly_profit, month_key, product.actual_profit_jpy)

            category_key = product.category or "未分類"
            source_key = product.source or "未入力"
            self.add_to_group(category_profit, category_key, product.actual_profit_jpy)
            self.add_to_group(source_profit, source_key, product.actual_profit_jpy)

        red_products = sorted(
            [product for product in actual_products if product.actual_profit_jpy < 0],
            key=lambda product: product.actual_profit_jpy,
        )[:8]
        long_inventory_products = sorted(
            [product for product in products if product.inventory_age_days is not None],
            key=lambda product: product.inventory_age_days,
            reverse=True,
        )[:8]

        context.update(
            {
                "total_actual_profit": sum(product.actual_profit_jpy for product in actual_products),
                "average_roi": round(sum(roi_values) / len(roi_values), 1) if roi_values else None,
                "average_days_to_sell": round(sum(days_to_sell) / len(days_to_sell), 1) if days_to_sell else None,
                "inventory_value": sum(product.inventory_value_jpy for product in products),
                "actual_sales_count": len(actual_products),
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
                "monthly_profit_labels": list(sorted(monthly_profit.keys())),
                "monthly_profit_values": [monthly_profit[key] for key in sorted(monthly_profit.keys())],
                "category_profit_labels": list(category_profit.keys()),
                "category_profit_values": list(category_profit.values()),
                "status_count_labels": list(status_counts.keys()),
                "status_count_values": list(status_counts.values()),
                "source_profit_rows": sorted(source_profit.items(), key=lambda item: item[1], reverse=True)[:8],
                "red_products": red_products,
                "long_inventory_products": long_inventory_products,
            }
        )
        return context


class ProductDetailView(OwnerQuerysetMixin, DetailView):
    template_name = "profittracker/product_detail.html"
    context_object_name = "product"


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "profittracker/product_form.html"
    success_url = reverse_lazy("product_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        messages.success(self.request, "商品を登録しました。")
        return super().form_valid(form)


class ProductUpdateView(OwnerQuerysetMixin, UpdateView):
    form_class = ProductForm
    template_name = "profittracker/product_form.html"
    success_url = reverse_lazy("product_list")

    def form_valid(self, form):
        messages.success(self.request, "商品を更新しました。")
        return super().form_valid(form)


class ProductDeleteView(OwnerQuerysetMixin, DeleteView):
    template_name = "profittracker/product_confirm_delete.html"
    success_url = reverse_lazy("product_list")

    def form_valid(self, form):
        messages.success(self.request, "商品を削除しました。")
        return super().form_valid(form)


class ProductQuickUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk, owner=request.user)
        form = ProductQuickUpdateForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "商品をクイック更新しました。")
        else:
            messages.error(request, "クイック更新に失敗しました。入力内容を確認してください。")
        return redirect(request.POST.get("next") or reverse("product_list"))


class ProductCsvExportView(LoginRequiredMixin, View):
    export_fields = [
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

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="products.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(self.export_fields)
        for product in Product.objects.filter(owner=request.user):
            writer.writerow([getattr(product, field) or "" for field in self.export_fields])
        return response


class ProductCsvImportView(LoginRequiredMixin, FormView):
    template_name = "profittracker/product_import.html"
    form_class = ProductCsvImportForm
    success_url = reverse_lazy("product_list")

    required_fields = {
        "title",
        "purchase_price_jpy",
        "expected_sale_price_usd",
        "shipping_cost_jpy",
        "exchange_rate",
    }

    integer_fields = {
        "quantity",
        "purchase_price_jpy",
        "purchase_shipping_jpy",
        "other_cost_jpy",
        "shipping_cost_jpy",
        "actual_shipping_cost_jpy",
        "actual_ebay_fee_jpy",
    }
    decimal_fields = {
        "expected_sale_price_usd",
        "exchange_rate",
        "ebay_fee_rate",
        "actual_sale_price_usd",
        "actual_exchange_rate",
    }
    date_fields = {"purchase_date", "listed_date", "sold_date", "shipped_date"}

    def clean_value(self, field, value):
        value = (value or "").strip()
        if value == "":
            return None
        if field in self.integer_fields:
            return int(value)
        if field in self.decimal_fields:
            return Decimal(value)
        if field in self.date_fields:
            return timezone.datetime.fromisoformat(value).date()
        return value

    def form_valid(self, form):
        raw = form.cleaned_data["csv_file"].read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw))
        if not reader.fieldnames or not self.required_fields.issubset(set(reader.fieldnames)):
            form.add_error("csv_file", "CSVヘッダーに title, purchase_price_jpy, expected_sale_price_usd, shipping_cost_jpy, exchange_rate が必要です。")
            return self.form_invalid(form)

        imported = 0
        errors = []
        model_fields = {field.name for field in Product._meta.fields}
        for index, row in enumerate(reader, start=2):
            try:
                values = {
                    field: self.clean_value(field, row.get(field))
                    for field in row
                    if field in model_fields and field not in {"id", "owner", "created_at", "updated_at"}
                }
                values = {key: value for key, value in values.items() if value is not None}
                Product.objects.create(owner=self.request.user, **values)
                imported += 1
            except (ValueError, InvalidOperation, TypeError) as exc:
                errors.append(f"{index}行目: {exc}")

        if errors:
            messages.warning(self.request, f"{imported}件を取り込みました。一部エラー: " + " / ".join(errors[:3]))
        else:
            messages.success(self.request, f"{imported}件の商品を取り込みました。")
        return super().form_valid(form)
