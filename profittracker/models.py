from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


class SellerSettings(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_settings",
        verbose_name="所有者",
    )
    default_target_profit_rate = models.DecimalField("デフォルト目標利益率", max_digits=5, decimal_places=1, default=Decimal("20.0"))
    default_target_roi = models.DecimalField("デフォルト目標ROI", max_digits=5, decimal_places=1, default=Decimal("30.0"))
    default_shipping_cost_jpy = models.PositiveIntegerField("デフォルト送料", default=0)
    default_exchange_rate = models.DecimalField("デフォルト為替", max_digits=8, decimal_places=2, default=Decimal("150.00"))
    default_ebay_fee_rate = models.DecimalField("デフォルトeBay手数料率", max_digits=5, decimal_places=2, default=Decimal("15.00"))
    markdown_ok_days = models.PositiveIntegerField("値下げ余地あり日数", default=30)
    markdown_review_days = models.PositiveIntegerField("値下げ検討日数", default=45)
    loss_cut_days = models.PositiveIntegerField("損切り候補日数", default=60)
    long_inventory_days = models.PositiveIntegerField("長期在庫日数", default=90)
    low_profit_rate = models.DecimalField("低利益率判定", max_digits=5, decimal_places=1, default=Decimal("15.0"))
    brand_keywords = models.TextField(
        "ブランド自動入力辞書",
        default="Hermès\nBottega Veneta\nLouis Vuitton\nYves Saint Laurent\nSaint Laurent\nMaison Margiela\nComme des Garçons\nDolce & Gabbana\nPorter\nSeiko\nCanon",
        blank=True,
    )

    class Meta:
        verbose_name = "セラー設定"
        verbose_name_plural = "セラー設定"

    def __str__(self):
        return f"{self.owner} の設定"

    @classmethod
    def get_for_user(cls, user):
        settings_obj, _ = cls.objects.get_or_create(owner=user)
        return settings_obj

    @property
    def brand_keyword_list(self):
        return [line.strip() for line in self.brand_keywords.splitlines() if line.strip()]


class Product(models.Model):
    class SalesChannel(models.TextChoices):
        EBAY = "ebay", "eBay"
        MERCARI = "mercari", "メルカリ"
        YAHOO_AUCTION = "yahoo_auction", "ヤフオク"
        RAKUMA = "rakuma", "ラクマ"
        OTHER = "other", "その他"

    class Status(models.TextChoices):
        PURCHASED = "purchased", "仕入れ済み"
        LISTED = "listed", "出品中"
        SOLD = "sold", "売却済み"

    class Condition(models.TextChoices):
        NEW = "new", "新品"
        USED = "used", "中古"
        FOR_PARTS = "for_parts", "ジャンク"
        OTHER = "other", "その他"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="所有者",
    )
    sku = models.CharField("SKU / 管理番号", max_length=80, blank=True)
    title = models.CharField("商品名", max_length=200)
    brand = models.CharField("ブランド", max_length=100, blank=True)
    category = models.CharField("カテゴリ", max_length=100, blank=True)
    condition = models.CharField("状態", max_length=20, choices=Condition.choices, default=Condition.USED)
    quantity = models.PositiveIntegerField("数量", default=1)
    source = models.CharField("仕入先", max_length=100, blank=True)
    purchase_price_jpy = models.PositiveIntegerField("仕入価格")
    purchase_shipping_jpy = models.PositiveIntegerField("仕入れ時送料", default=0)
    other_cost_jpy = models.PositiveIntegerField("その他コスト", default=0)
    expected_sale_price_usd = models.DecimalField("想定売価USD", max_digits=10, decimal_places=2, null=True, blank=True)
    expected_sale_price_jpy = models.PositiveIntegerField("想定売価JPY", null=True, blank=True)
    shipping_cost_jpy = models.PositiveIntegerField("送料")
    exchange_rate = models.DecimalField("為替", max_digits=8, decimal_places=2)
    ebay_fee_rate = models.DecimalField("販売手数料率", max_digits=5, decimal_places=2, default=Decimal("15.00"))
    purchase_date = models.DateField("仕入れ日", null=True, blank=True)
    listed_date = models.DateField("出品日", null=True, blank=True)
    sold_date = models.DateField("売却日", null=True, blank=True)
    shipped_date = models.DateField("発送日", null=True, blank=True)
    actual_sales_channel = models.CharField("売れたチャネル", max_length=20, choices=SalesChannel.choices, blank=True)
    actual_sale_price_usd = models.DecimalField("実売価格USD", max_digits=10, decimal_places=2, null=True, blank=True)
    actual_sale_price_jpy_manual = models.PositiveIntegerField("実売価格JPY", null=True, blank=True)
    actual_exchange_rate = models.DecimalField("実際の為替", max_digits=8, decimal_places=2, null=True, blank=True)
    actual_shipping_cost_jpy = models.PositiveIntegerField("実送料", null=True, blank=True)
    actual_ebay_fee_jpy = models.PositiveIntegerField("実販売手数料", null=True, blank=True)
    listing_url = models.URLField("販売ページURL", blank=True)
    purchase_url = models.URLField("仕入れ元URL", blank=True)
    image_url = models.URLField("商品画像URL", blank=True)
    buyer_country = models.CharField("販売先国", max_length=100, blank=True)
    tracking_number = models.CharField("追跡番号", max_length=100, blank=True)
    status = models.CharField("ステータス", max_length=20, choices=Status.choices, default=Status.PURCHASED)
    memo = models.TextField("メモ", blank=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "sku"],
                condition=~models.Q(sku=""),
                name="unique_owner_sku_when_set",
            )
        ]
        verbose_name = "商品"
        verbose_name_plural = "商品"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("product_list")

    @staticmethod
    def yen(value):
        return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def sale_price_jpy(self):
        if self.expected_sale_price_jpy is not None:
            return self.expected_sale_price_jpy
        if self.expected_sale_price_usd is not None:
            return self.yen(self.expected_sale_price_usd * self.exchange_rate)
        return 0

    @property
    def ebay_fee_jpy(self):
        fee = Decimal(self.sale_price_jpy) * self.ebay_fee_rate / Decimal("100")
        return self.yen(fee)

    @property
    def expected_ebay_fee_jpy(self):
        return self.ebay_fee_jpy

    @property
    def profit_jpy(self):
        return (
            self.sale_price_jpy
            - self.ebay_fee_jpy
            - self.purchase_price_jpy
            - self.purchase_shipping_jpy
            - self.shipping_cost_jpy
            - self.other_cost_jpy
        )

    @property
    def expected_profit_jpy(self):
        return self.profit_jpy

    @property
    def profit_rate(self):
        if self.sale_price_jpy == 0:
            return Decimal("0.0")
        rate = Decimal(self.profit_jpy) / Decimal(self.sale_price_jpy) * Decimal("100")
        return rate.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def actual_sale_price_jpy(self):
        if self.actual_sale_price_jpy_manual is not None:
            return self.actual_sale_price_jpy_manual
        if self.actual_sale_price_usd is None:
            return None
        rate = self.actual_exchange_rate or self.exchange_rate
        return self.yen(self.actual_sale_price_usd * rate)

    @property
    def estimated_actual_ebay_fee_jpy(self):
        if self.actual_sale_price_jpy is None:
            return None
        fee = Decimal(self.actual_sale_price_jpy) * self.ebay_fee_rate / Decimal("100")
        return self.yen(fee)

    @property
    def actual_fee_for_profit_jpy(self):
        if self.actual_ebay_fee_jpy is not None:
            return self.actual_ebay_fee_jpy
        return self.estimated_actual_ebay_fee_jpy

    @property
    def actual_shipping_for_profit_jpy(self):
        if self.actual_shipping_cost_jpy is not None:
            return self.actual_shipping_cost_jpy
        return self.shipping_cost_jpy

    @property
    def actual_profit_jpy(self):
        if self.actual_sale_price_jpy is None or self.actual_fee_for_profit_jpy is None:
            return None
        return (
            self.actual_sale_price_jpy
            - self.actual_fee_for_profit_jpy
            - self.purchase_price_jpy
            - self.purchase_shipping_jpy
            - self.actual_shipping_for_profit_jpy
            - self.other_cost_jpy
        )

    @property
    def actual_profit_rate(self):
        if self.actual_sale_price_jpy in (None, 0) or self.actual_profit_jpy is None:
            return None
        rate = Decimal(self.actual_profit_jpy) / Decimal(self.actual_sale_price_jpy) * Decimal("100")
        return rate.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def profit_gap_jpy(self):
        if self.actual_profit_jpy is None:
            return None
        return self.actual_profit_jpy - self.expected_profit_jpy

    @property
    def actual_entry_missing_labels(self):
        if self.status != self.Status.SOLD and self.sold_date is None:
            return []

        missing = []
        if self.sold_date is None:
            missing.append("売却日")
        if not self.actual_sales_channel:
            missing.append("売れたチャネル")
        if self.actual_sale_price_jpy is None:
            missing.append("実売価格")
        if self.actual_shipping_cost_jpy is None:
            missing.append("実送料")
        return missing

    @property
    def actual_entry_complete(self):
        return self.status == self.Status.SOLD and not self.actual_entry_missing_labels

    @property
    def roi(self):
        invested = self.purchase_price_jpy + self.purchase_shipping_jpy + self.other_cost_jpy
        if invested == 0:
            return Decimal("0.0")
        profit = self.actual_profit_jpy if self.actual_profit_jpy is not None else self.expected_profit_jpy
        rate = Decimal(profit) / Decimal(invested) * Decimal("100")
        return rate.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    @property
    def days_to_sell(self):
        if self.listed_date and self.sold_date:
            return (self.sold_date - self.listed_date).days
        return None

    @property
    def sell_through_days(self):
        return self.days_to_sell

    @property
    def holding_days(self):
        if not self.purchase_date:
            return None
        end_date = self.sold_date or timezone.localdate()
        return (end_date - self.purchase_date).days

    @property
    def inventory_age_days(self):
        if self.sold_date:
            return None
        return self.holding_days

    @property
    def inventory_value_jpy(self):
        if self.status == self.Status.SOLD:
            return 0
        return self.purchase_price_jpy + self.purchase_shipping_jpy + self.other_cost_jpy
