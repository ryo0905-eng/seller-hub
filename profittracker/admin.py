from django.contrib import admin

from .models import Product, SellerSettings


@admin.register(SellerSettings)
class SellerSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "owner",
        "default_target_profit_rate",
        "default_target_roi",
        "default_shipping_cost_jpy",
        "default_exchange_rate",
        "default_ebay_fee_rate",
    )


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "title",
        "owner",
        "sales_channel",
        "status",
        "condition",
        "purchase_price_jpy",
        "expected_sale_price_usd",
        "expected_sale_price_jpy",
        "expected_profit_jpy",
        "actual_sale_price_usd",
        "actual_sale_price_jpy_manual",
        "actual_profit_jpy",
        "profit_gap_jpy",
        "days_to_sell",
        "inventory_age_days",
        "roi",
        "updated_at",
    )
    list_filter = ("sales_channel", "status", "condition", "category", "brand", "source", "buyer_country")
    search_fields = (
        "sku",
        "title",
        "brand",
        "category",
        "source",
        "memo",
        "buyer_country",
        "tracking_number",
        "owner__username",
    )
    readonly_fields = (
        "sale_price_jpy",
        "ebay_fee_jpy",
        "profit_jpy",
        "profit_rate",
        "actual_sale_price_jpy",
        "estimated_actual_ebay_fee_jpy",
        "actual_profit_jpy",
        "actual_profit_rate",
        "profit_gap_jpy",
        "roi",
        "days_to_sell",
        "holding_days",
        "inventory_age_days",
        "inventory_value_jpy",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        ("基本情報", {"fields": ("owner", "sku", "title", "brand", "category", "condition", "quantity", "source", "sales_channel", "status")}),
        (
            "想定利益",
            {
                "fields": (
                    "purchase_price_jpy",
                    "purchase_shipping_jpy",
                    "other_cost_jpy",
                    "expected_sale_price_usd",
                    "expected_sale_price_jpy",
                    "shipping_cost_jpy",
                    "exchange_rate",
                    "ebay_fee_rate",
                    "sale_price_jpy",
                    "ebay_fee_jpy",
                    "profit_jpy",
                    "profit_rate",
                    "roi",
                )
            },
        ),
        (
            "日付と実績",
            {
                "fields": (
                    "purchase_date",
                    "listed_date",
                    "sold_date",
                    "shipped_date",
                    "actual_sale_price_usd",
                    "actual_sale_price_jpy_manual",
                    "actual_exchange_rate",
                    "actual_shipping_cost_jpy",
                    "actual_ebay_fee_jpy",
                    "actual_sale_price_jpy",
                    "estimated_actual_ebay_fee_jpy",
                    "actual_profit_jpy",
                    "actual_profit_rate",
                    "profit_gap_jpy",
                    "days_to_sell",
                    "holding_days",
                    "inventory_age_days",
                    "inventory_value_jpy",
                )
            },
        ),
        ("URL・発送", {"fields": ("listing_url", "purchase_url", "image_url", "buyer_country", "tracking_number")}),
        ("メモ", {"fields": ("memo",)}),
        ("システム", {"fields": ("created_at", "updated_at")}),
    )
