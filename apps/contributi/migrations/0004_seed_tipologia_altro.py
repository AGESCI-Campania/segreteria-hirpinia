from django.db import migrations

CODICE = "ALTRO"


def crea_tipologia_altro(apps, schema_editor):
    TipologiaCampo = apps.get_model("contributi", "TipologiaCampo")
    TipologiaCampo.objects.get_or_create(
        codice=CODICE,
        defaults={
            "nome": "Altro",
            "livello": "ALTRO",
            "approvazione_automatica": False,
            "quota_default": None,
        },
    )


def rimuovi_tipologia_altro(apps, schema_editor):
    TipologiaCampo = apps.get_model("contributi", "TipologiaCampo")
    TipologiaCampo.objects.filter(codice=CODICE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contributi", "0003_allegatopartecipazione_contributopartecipazione"),
    ]

    operations = [
        migrations.RunPython(crea_tipologia_altro, rimuovi_tipologia_altro),
    ]
