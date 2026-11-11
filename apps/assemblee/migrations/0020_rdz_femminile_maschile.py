from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("assemblee", "0019_esito_palese"),
    ]

    operations = [
        migrations.RenameField(
            model_name="verbaleseduta", old_name="rdz_1", new_name="rdz_femminile"
        ),
        migrations.RenameField(
            model_name="verbaleseduta", old_name="rdz_2", new_name="rdz_maschile"
        ),
        migrations.AlterField(
            model_name="verbaleseduta",
            name="rdz_femminile",
            field=models.CharField(
                blank=True,
                help_text="Lascia vuoto se il posto è vacante.",
                max_length=200,
                verbose_name="Responsabile di Zona femminile",
            ),
        ),
        migrations.AlterField(
            model_name="verbaleseduta",
            name="rdz_maschile",
            field=models.CharField(
                blank=True,
                help_text="Lascia vuoto se il posto è vacante.",
                max_length=200,
                verbose_name="Responsabile di Zona maschile",
            ),
        ),
    ]
