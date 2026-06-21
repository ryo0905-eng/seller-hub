import json
from decimal import Decimal, InvalidOperation
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from .forms import ProductForm
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = list(Product.objects.filter(owner=self.request.user))
        actual_products = [product for product in products if product.actual_profit_jpy is not None]
        days_to_sell = [product.days_to_sell for product in products if product.days_to_sell is not None]
        roi_values = [product.roi for product in actual_products]

        monthly_profit = {}
        category_profit = {}
        source_profit = {}
        status_counts = {label: 0 for value, label in Product.Status.choices}

        for product in products:
            status_counts[product.get_status_display()] = status_counts.get(product.get_status_display(), 0) + 1

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
