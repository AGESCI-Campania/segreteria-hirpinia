from django.db import migrations


def crea_e9001(apps, schema_editor):
    Gruppo = apps.get_model("organizzazione", "Gruppo")
    AllowlistGruppo = apps.get_model("organizzazione", "AllowlistGruppo")

    Gruppo.objects.get_or_create(
        codice="E9001",
        defaults={
            "nome": "COM ZONA HIRPINIA",
            "is_comitato_zona": True,
            "account_consentiti": 2,
            "origine": "MANUALE",
        },
    )
    # D-33: le due voci dei RdZ non si derivano da EMAIL GRUPPO, vanno inserite
    # a mano e l'import non deve mai sovrascriverle.
    for email in (
        "rzm.zonahirpinia@campania.agesci.it",
        "rzf.zonahirpinia@campania.agesci.it",
    ):
        AllowlistGruppo.objects.get_or_create(
            email=email, defaults={"codice_gruppo": "E9001", "origine": "MANUALE"}
        )


def rimuovi_e9001(apps, schema_editor):
    Gruppo = apps.get_model("organizzazione", "Gruppo")
    AllowlistGruppo = apps.get_model("organizzazione", "AllowlistGruppo")
    AllowlistGruppo.objects.filter(codice_gruppo="E9001").delete()
    Gruppo.objects.filter(codice="E9001").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("organizzazione", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crea_e9001, rimuovi_e9001),
    ]
