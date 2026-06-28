from django.db import migrations, models


def migrate_shipped_to_sold(apps, schema_editor):
    Product = apps.get_model("profittracker", "Product")
    Product.objects.filter(status="shipped").update(status="sold")


class Migration(migrations.Migration):

    dependencies = [
        ("profittracker", "0009_sellersettings_brand_keywords"),
    ]

    operations = [
        migrations.RunPython(migrate_shipped_to_sold, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="product",
            name="status",
            field=models.CharField(
                choices=[
                    ("purchased", "仕入れ済み"),
                    ("listed", "出品中"),
                    ("sold", "売却済み"),
                ],
                default="purchased",
                max_length=20,
                verbose_name="ステータス",
            ),
        ),
    ]
