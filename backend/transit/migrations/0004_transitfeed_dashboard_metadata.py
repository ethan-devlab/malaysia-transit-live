from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("transit", "0003_vehiclesnapshot")]

    operations = [
        migrations.AddField(
            model_name="transitfeed",
            name="operator_key",
            field=models.SlugField(default="", max_length=80),
        ),
        migrations.AddField(
            model_name="transitfeed",
            name="operator_name",
            field=models.CharField(default="", max_length=160),
        ),
        migrations.AddField(
            model_name="transitfeed",
            name="region_key",
            field=models.SlugField(default="", max_length=80),
        ),
        migrations.AddField(
            model_name="transitfeed",
            name="region_name",
            field=models.CharField(default="", max_length=160),
        ),
    ]
