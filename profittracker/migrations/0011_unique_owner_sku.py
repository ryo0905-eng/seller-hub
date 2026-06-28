from django.db import migrations, models


def deduplicate_skus(apps, schema_editor):
    Product = apps.get_model("profittracker", "Product")
    max_length = Product._meta.get_field("sku").max_length
    used_by_owner = {}

    for product in Product.objects.order_by("owner_id", "id"):
        if not product.sku:
            continue

        used_skus = used_by_owner.setdefault(product.owner_id, set())
        if product.sku not in used_skus:
            used_skus.add(product.sku)
            continue

        suffix = 2
        while True:
            suffix_text = f"-{suffix}"
            candidate = f"{product.sku[: max_length - len(suffix_text)]}{suffix_text}"
            if candidate not in used_skus:
                product.sku = candidate
                product.save(update_fields=["sku"])
                used_skus.add(candidate)
                break
            suffix += 1


class Migration(migrations.Migration):

    dependencies = [
        ("profittracker", "0010_remove_shipped_status"),
    ]

    operations = [
        migrations.RunPython(deduplicate_skus, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(
                condition=~models.Q(sku=""),
                fields=("owner", "sku"),
                name="unique_owner_sku_when_set",
            ),
        ),
    ]
