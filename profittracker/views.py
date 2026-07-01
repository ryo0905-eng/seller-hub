import csv
import io
import json
import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import IntegrityError
from django.db.models import Q
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, TemplateView, UpdateView

from .forms import ProductCsvImportForm, ProductForm, ProductQuickUpdateForm, SellerSettingsForm, SourcingSimulatorForm
from .models import Product, SellerSettings


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
    default_visible_statuses = (Product.Status.PURCHASED, Product.Status.LISTED)
    visible_modes = {"cards", "table"}

    @staticmethod
    def yen(value):
        return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def selected_statuses(self):
        valid_statuses = {value for value, _label in Product.Status.choices}
        if "status" not in self.request.GET:
            return list(self.default_visible_statuses)
        return [status for status in self.request.GET.getlist("status") if status in valid_statuses]

    def get_queryset(self):
        queryset = super().get_queryset()
        statuses = self.selected_statuses()
        query = self.request.GET.get("q", "").strip()
        queryset = queryset.filter(status__in=statuses)
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(sku__icontains=query)
                | Q(brand__icontains=query)
                | Q(category__icontains=query)
                | Q(source__icontains=query)
            )
        return queryset

    def pricing_snapshot(self, product, seller_settings):
        total_cost_jpy = product.purchase_price_jpy + product.purchase_shipping_jpy + product.other_cost_jpy + product.shipping_cost_jpy
        fee_multiplier = Decimal("1") - product.ebay_fee_rate / Decimal("100")
        breakeven_jpy = None
        breakeven_usd = None
        target_sale_jpy = None
        target_sale_usd = None

        if fee_multiplier > 0 and product.exchange_rate > 0:
            breakeven_jpy = self.yen(Decimal(total_cost_jpy) / fee_multiplier)
            if product.expected_sale_price_usd is not None:
                breakeven_usd = (Decimal(breakeven_jpy) / product.exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            target_multiplier = fee_multiplier - seller_settings.default_target_profit_rate / Decimal("100")
            if target_multiplier > 0:
                target_sale_jpy = self.yen(Decimal(total_cost_jpy) / target_multiplier)
                if product.expected_sale_price_usd is not None:
                    target_sale_usd = (Decimal(target_sale_jpy) / product.exchange_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        def discount_snapshot(percent):
            sale_price_usd = None
            if product.expected_sale_price_usd is not None:
                sale_price_usd = (product.expected_sale_price_usd * (Decimal("100") - Decimal(percent)) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                sale_price_jpy = self.yen(sale_price_usd * product.exchange_rate)
            else:
                sale_price_jpy = self.yen(Decimal(product.sale_price_jpy) * (Decimal("100") - Decimal(percent)) / Decimal("100"))
            ebay_fee_jpy = self.yen(Decimal(sale_price_jpy) * product.ebay_fee_rate / Decimal("100"))
            profit_jpy = sale_price_jpy - ebay_fee_jpy - total_cost_jpy
            return {
                "percent": percent,
                "sale_price_usd": sale_price_usd,
                "sale_price_jpy": sale_price_jpy,
                "profit_jpy": profit_jpy,
            }

        discount_10 = discount_snapshot(10)
        discount_20 = discount_snapshot(20)
        age = product.inventory_age_days
        profit_rate = product.profit_rate

        if product.status == Product.Status.SOLD:
            if product.actual_profit_jpy is not None and product.actual_profit_jpy < 0:
                decision = {"label": "赤字確定", "class": "danger", "message": "実績を分析"}
            else:
                decision = {"label": "売却済み", "class": "success", "message": "実績確認"}
        elif age is None:
            decision = {"label": "日付未入力", "class": "warning", "message": "仕入れ日を入力"}
        elif product.expected_profit_jpy < 0:
            decision = {"label": "要見直し", "class": "danger", "message": "現売価で赤字"}
        elif (
            age is not None
            and age >= seller_settings.long_inventory_days
            and profit_rate < seller_settings.low_profit_rate
        ) or (
            age is not None
            and age >= seller_settings.loss_cut_days
            and discount_20["profit_jpy"] < 0
        ):
            decision = {"label": "損切り候補", "class": "danger", "message": "回転優先で再価格"}
        elif age is not None and age >= seller_settings.markdown_review_days:
            decision = {"label": "値下げ検討", "class": "warning", "message": "10%下げを確認"}
        elif age is not None and age >= seller_settings.markdown_ok_days and discount_10["profit_jpy"] >= 0:
            decision = {"label": "値下げ余地あり", "class": "success", "message": "10%下げても黒字"}
        else:
            decision = {"label": "維持", "class": "neutral", "message": "現価格で様子見"}

        return {
            "total_cost_jpy": total_cost_jpy,
            "breakeven_jpy": breakeven_jpy,
            "breakeven_usd": breakeven_usd,
            "target_sale_jpy": target_sale_jpy,
            "target_sale_usd": target_sale_usd,
            "discount_10": discount_10,
            "discount_20": discount_20,
            "decision": decision,
        }

    def status_timeline(self, product):
        statuses = [value for value, _label in Product.Status.choices]
        current_index = statuses.index(product.status)
        steps = []
        for index, (value, label) in enumerate(Product.Status.choices):
            if index < current_index:
                state = "done"
            elif index == current_index:
                state = "current"
            else:
                state = "pending"
            steps.append(
                {
                    "value": value,
                    "label": label,
                    "state": state,
                }
            )
        return steps

    def sort_products(self, products):
        sort = self.request.GET.get("sort", "updated")
        if sort == "sku_asc":
            return sorted(products, key=lambda product: (not product.sku, (product.sku or "").casefold()))
        if sort == "age_desc":
            return sorted(products, key=lambda product: product.inventory_age_days or -1, reverse=True)
        if sort == "profit_asc":
            return sorted(products, key=lambda product: product.expected_profit_jpy)
        if sort == "profit_rate_asc":
            return sorted(products, key=lambda product: product.profit_rate)
        if sort == "roi_asc":
            return sorted(products, key=lambda product: product.roi)
        return products

    def current_view_mode(self):
        mode = self.request.GET.get("view", "cards")
        if mode not in self.visible_modes:
            return "cards"
        return mode

    def querystring_for_view(self, mode):
        params = self.request.GET.copy()
        if mode == "cards":
            params.pop("view", None)
        else:
            params["view"] = mode
        return params.urlencode()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        seller_settings = SellerSettings.get_for_user(self.request.user)
        products = self.sort_products(list(self.get_queryset()))
        sold_products = [product for product in products if product.actual_profit_jpy is not None]
        days_to_sell = [product.days_to_sell for product in products if product.days_to_sell is not None]
        product_cards = [
            {
                "product": product,
                "pricing": self.pricing_snapshot(product, seller_settings),
                "status_timeline": self.status_timeline(product),
            }
            for product in products
        ]
        context["status_choices"] = Product.Status.choices
        context["products"] = products
        context["product_cards"] = product_cards
        context["current_statuses"] = self.selected_statuses()
        context["current_query"] = self.request.GET.get("q", "").strip()
        context["current_sort"] = self.request.GET.get("sort", "updated")
        context["current_view"] = self.current_view_mode()
        context["card_view_querystring"] = self.querystring_for_view("cards")
        context["table_view_querystring"] = self.querystring_for_view("table")
        context["review_count"] = sum(1 for card in product_cards if card["pricing"]["decision"]["class"] in {"danger", "warning"})
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

    @staticmethod
    def percentage(part, total):
        if total == 0:
            return Decimal("0.0")
        return (Decimal(part) / Decimal(total) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @staticmethod
    def average_yen(total, count):
        if count == 0:
            return None
        return int((Decimal(total) / Decimal(count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

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

    def performance_rows(self, products, key_func):
        groups = {}
        for product in products:
            if product.actual_profit_jpy is None:
                continue
            key = key_func(product)
            row = groups.setdefault(
                key,
                {
                    "label": key,
                    "sales_count": 0,
                    "total_profit": 0,
                    "total_roi": Decimal("0.0"),
                    "loss_count": 0,
                    "days_total": 0,
                    "days_count": 0,
                },
            )
            row["sales_count"] += 1
            row["total_profit"] += product.actual_profit_jpy
            row["total_roi"] += product.roi
            if product.actual_profit_jpy < 0:
                row["loss_count"] += 1
            if product.days_to_sell is not None:
                row["days_total"] += product.days_to_sell
                row["days_count"] += 1

        rows = []
        for row in groups.values():
            rows.append(
                {
                    "label": row["label"],
                    "sales_count": row["sales_count"],
                    "total_profit": row["total_profit"],
                    "average_profit": self.average_yen(row["total_profit"], row["sales_count"]),
                    "average_roi": (row["total_roi"] / Decimal(row["sales_count"])).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
                    "loss_rate": self.percentage(row["loss_count"], row["sales_count"]),
                    "average_days_to_sell": round(row["days_total"] / row["days_count"], 1) if row["days_count"] else None,
                }
            )
        return sorted(rows, key=lambda row: (row["total_profit"], row["sales_count"]), reverse=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = list(Product.objects.filter(owner=self.request.user))
        period, start_date, end_date = self.get_date_range()
        filtered_products = [product for product in products if self.in_range(product, start_date, end_date)]
        actual_products = [product for product in filtered_products if product.actual_profit_jpy is not None]
        days_to_sell = [product.days_to_sell for product in filtered_products if product.days_to_sell is not None]
        roi_values = [product.roi for product in actual_products]
        total_actual_profit = sum(product.actual_profit_jpy for product in actual_products)
        loss_count = sum(1 for product in actual_products if product.actual_profit_jpy < 0)

        monthly_profit = {}
        category_profit = {}
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
            self.add_to_group(category_profit, category_key, product.actual_profit_jpy)

        red_products = sorted(
            [product for product in actual_products if product.actual_profit_jpy < 0],
            key=lambda product: product.actual_profit_jpy,
        )[:8]
        underperforming_products = sorted(
            [product for product in actual_products if product.profit_gap_jpy is not None and product.profit_gap_jpy < 0],
            key=lambda product: product.profit_gap_jpy,
        )[:8]
        sold_products = sorted(
            [
                product
                for product in filtered_products
                if product.status == Product.Status.SOLD or product.sold_date is not None
            ],
            key=lambda product: product.sold_date or timezone.datetime.min.date(),
            reverse=True,
        )
        incomplete_actual_products = sorted(
            [
                product
                for product in filtered_products
                if product.status == Product.Status.SOLD and product.actual_profit_jpy is None
            ],
            key=lambda product: product.sold_date or timezone.localdate(),
            reverse=True,
        )[:8]
        long_inventory_products = sorted(
            [product for product in products if product.inventory_age_days is not None],
            key=lambda product: product.inventory_age_days,
            reverse=True,
        )[:8]

        context.update(
            {
                "total_actual_profit": total_actual_profit,
                "average_actual_profit": self.average_yen(total_actual_profit, len(actual_products)),
                "average_roi": round(sum(roi_values) / len(roi_values), 1) if roi_values else None,
                "average_days_to_sell": round(sum(days_to_sell) / len(days_to_sell), 1) if days_to_sell else None,
                "loss_rate": self.percentage(loss_count, len(actual_products)) if actual_products else None,
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
                "source_profit_rows": self.performance_rows(actual_products, lambda product: product.source or "未入力")[:8],
                "category_performance_rows": self.performance_rows(actual_products, lambda product: product.category or "未分類")[:8],
                "red_products": red_products,
                "underperforming_products": underperforming_products,
                "sold_products": sold_products,
                "incomplete_actual_products": incomplete_actual_products,
                "long_inventory_products": long_inventory_products,
            }
        )
        return context


class SourcingSimulatorView(LoginRequiredMixin, FormView):
    template_name = "profittracker/sourcing_simulator.html"
    form_class = SourcingSimulatorForm

    @staticmethod
    def yen(value):
        return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def calculate(self, cleaned_data):
        sale_price_jpy = self.yen(cleaned_data["expected_sale_price_usd"] * cleaned_data["exchange_rate"])
        ebay_fee_jpy = self.yen(Decimal(sale_price_jpy) * cleaned_data["ebay_fee_rate"] / Decimal("100"))
        profit_jpy = sale_price_jpy - ebay_fee_jpy - cleaned_data["purchase_price_jpy"] - cleaned_data["shipping_cost_jpy"]
        profit_rate = Decimal("0.0")
        if sale_price_jpy:
            profit_rate = (Decimal(profit_jpy) / Decimal(sale_price_jpy) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        invested = cleaned_data["purchase_price_jpy"]
        roi = Decimal("0.0")
        if invested:
            roi = (Decimal(profit_jpy) / Decimal(invested) * Decimal("100")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        gross_remaining_jpy = sale_price_jpy - ebay_fee_jpy - cleaned_data["shipping_cost_jpy"]
        max_purchase_by_roi_jpy = self.yen(
            Decimal(gross_remaining_jpy) / (Decimal("1") + cleaned_data["target_roi"] / Decimal("100"))
        )
        max_purchase_by_profit_rate_jpy = self.yen(
            Decimal(gross_remaining_jpy) - Decimal(sale_price_jpy) * cleaned_data["target_profit_rate"] / Decimal("100")
        )
        max_purchase_price_jpy = min(max_purchase_by_roi_jpy, max_purchase_by_profit_rate_jpy)

        fee_multiplier = Decimal("1") - cleaned_data["ebay_fee_rate"] / Decimal("100")
        needed_sale_price_for_roi_usd = None
        needed_sale_price_for_profit_rate_usd = None
        if fee_multiplier > 0 and cleaned_data["exchange_rate"] > 0:
            needed_profit_for_roi = Decimal(cleaned_data["purchase_price_jpy"]) * cleaned_data["target_roi"] / Decimal("100")
            needed_sale_price_for_roi_jpy = (
                Decimal(cleaned_data["purchase_price_jpy"] + cleaned_data["shipping_cost_jpy"]) + needed_profit_for_roi
            ) / fee_multiplier
            needed_sale_price_for_roi_usd = (needed_sale_price_for_roi_jpy / cleaned_data["exchange_rate"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            profit_rate_multiplier = fee_multiplier - cleaned_data["target_profit_rate"] / Decimal("100")
            if profit_rate_multiplier > 0:
                needed_sale_price_for_profit_rate_jpy = Decimal(cleaned_data["purchase_price_jpy"] + cleaned_data["shipping_cost_jpy"]) / profit_rate_multiplier
                needed_sale_price_for_profit_rate_usd = (needed_sale_price_for_profit_rate_jpy / cleaned_data["exchange_rate"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if profit_rate >= cleaned_data["target_profit_rate"] and roi >= cleaned_data["target_roi"]:
            decision = "OK"
            decision_class = "success"
            decision_message = "仕入れ候補として良さそうです。"
        elif profit_rate >= cleaned_data["target_profit_rate"] / Decimal("2") and roi >= cleaned_data["target_roi"] / Decimal("2"):
            decision = "注意"
            decision_class = "warning"
            decision_message = "条件次第です。値下げ余地や回転日数を確認しましょう。"
        else:
            decision = "見送り"
            decision_class = "danger"
            decision_message = "利益が薄いので、仕入価格を下げるか売価を見直した方がよさそうです。"

        return {
            "sale_price_jpy": sale_price_jpy,
            "ebay_fee_jpy": ebay_fee_jpy,
            "profit_jpy": profit_jpy,
            "profit_rate": profit_rate,
            "roi": roi,
            "max_purchase_price_jpy": max_purchase_price_jpy,
            "max_purchase_by_roi_jpy": max_purchase_by_roi_jpy,
            "max_purchase_by_profit_rate_jpy": max_purchase_by_profit_rate_jpy,
            "needed_sale_price_for_roi_usd": needed_sale_price_for_roi_usd,
            "needed_sale_price_for_profit_rate_usd": needed_sale_price_for_profit_rate_usd,
            "decision": decision,
            "decision_class": decision_class,
            "decision_message": decision_message,
        }

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["seller_settings"] = SellerSettings.get_for_user(self.request.user)
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        seller_settings = SellerSettings.get_for_user(self.request.user)
        initial.update(
            {
                "exchange_rate": self.request.GET.get("exchange_rate", seller_settings.default_exchange_rate),
                "shipping_cost_jpy": seller_settings.default_shipping_cost_jpy,
                "ebay_fee_rate": self.request.GET.get("ebay_fee_rate", seller_settings.default_ebay_fee_rate),
                "target_profit_rate": seller_settings.default_target_profit_rate,
                "target_roi": seller_settings.default_target_roi,
            }
        )
        return initial

    def form_valid(self, form):
        context = self.get_context_data(form=form)
        context["result"] = self.calculate(form.cleaned_data)
        context["register_params"] = {
            "title": form.cleaned_data.get("title", ""),
            "purchase_price_jpy": form.cleaned_data["purchase_price_jpy"],
            "expected_sale_price_usd": form.cleaned_data["expected_sale_price_usd"],
            "shipping_cost_jpy": form.cleaned_data["shipping_cost_jpy"],
            "exchange_rate": form.cleaned_data["exchange_rate"],
            "ebay_fee_rate": form.cleaned_data["ebay_fee_rate"],
        }
        return self.render_to_response(context)


class SellerSettingsView(LoginRequiredMixin, UpdateView):
    form_class = SellerSettingsForm
    template_name = "profittracker/seller_settings.html"
    success_url = reverse_lazy("seller_settings")

    def get_object(self, queryset=None):
        return SellerSettings.get_for_user(self.request.user)

    def form_valid(self, form):
        messages.success(self.request, "設定を保存しました。")
        return super().form_valid(form)


class ProductDetailView(OwnerQuerysetMixin, DetailView):
    template_name = "profittracker/product_detail.html"
    context_object_name = "product"


class ProductFormContextMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["owner"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["brand_keywords"] = SellerSettings.get_for_user(self.request.user).brand_keyword_list
        return context


class ProductCreateView(ProductFormContextMixin, LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = "profittracker/product_form.html"
    success_url = reverse_lazy("product_list")

    def next_sku(self, target_date=None):
        target_date = target_date or timezone.localdate()
        prefix = target_date.strftime("%Y%m%d")
        pattern = re.compile(rf"^{prefix}-(\d+)$")
        serials = []
        for sku in self.request.user.products.filter(sku__startswith=f"{prefix}-").values_list("sku", flat=True):
            match = pattern.match(sku or "")
            if match:
                serials.append(int(match.group(1)))
        return f"{prefix}-{(max(serials) if serials else 0) + 1:03d}"

    def get_initial(self):
        initial = super().get_initial()
        seller_settings = SellerSettings.get_for_user(self.request.user)
        initial.update(
            {
                "shipping_cost_jpy": seller_settings.default_shipping_cost_jpy,
                "exchange_rate": seller_settings.default_exchange_rate,
                "ebay_fee_rate": seller_settings.default_ebay_fee_rate,
                "sku": self.next_sku(),
            }
        )
        for field in [
            "title",
            "sku",
            "purchase_price_jpy",
            "expected_sale_price_usd",
            "expected_sale_price_jpy",
            "shipping_cost_jpy",
            "exchange_rate",
            "ebay_fee_rate",
        ]:
            if self.request.GET.get(field):
                initial[field] = self.request.GET[field]
        return initial

    def form_valid(self, form):
        form.instance.owner = self.request.user
        if not form.instance.sku:
            form.instance.sku = self.next_sku(form.cleaned_data.get("purchase_date"))
        messages.success(self.request, "商品を登録しました。")
        return super().form_valid(form)


class ProductUpdateView(ProductFormContextMixin, OwnerQuerysetMixin, UpdateView):
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
        "expected_sale_price_jpy",
        "shipping_cost_jpy",
        "exchange_rate",
        "ebay_fee_rate",
        "purchase_date",
        "listed_date",
        "sold_date",
        "actual_sales_channel",
        "actual_sale_price_usd",
        "actual_sale_price_jpy_manual",
        "actual_exchange_rate",
        "actual_shipping_cost_jpy",
        "actual_ebay_fee_jpy",
        "listing_url",
        "purchase_url",
        "image_url",
        "buyer_country",
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
        "expected_sale_price_jpy",
        "shipping_cost_jpy",
        "actual_sale_price_jpy_manual",
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
                values["status"] = Product.status_from_dates(
                    purchase_date=values.get("purchase_date"),
                    listed_date=values.get("listed_date"),
                    sold_date=values.get("sold_date"),
                )
                Product.objects.create(owner=self.request.user, **values)
                imported += 1
            except (IntegrityError, ValueError, InvalidOperation, TypeError) as exc:
                errors.append(f"{index}行目: {exc}")

        if errors:
            messages.warning(self.request, f"{imported}件を取り込みました。一部エラー: " + " / ".join(errors[:3]))
        else:
            messages.success(self.request, f"{imported}件の商品を取り込みました。")
        return super().form_valid(form)
