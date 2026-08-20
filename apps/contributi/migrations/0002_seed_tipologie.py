from decimal import Decimal

from django.db import migrations

TIPOLOGIE = [
    {
        "codice": "CFM",
        "nome": "Campo di Formazione Metodologica",
        "livello": "REG",
        "approvazione_automatica": True,
        "quota_default": Decimal("51.50"),
    },
    {
        "codice": "CFA",
        "nome": "Campo di Formazione Associativa",
        "livello": "NAZ",
        "approvazione_automatica": True,
        "quota_default": Decimal("51.50"),
    },
    {
        "codice": "CCG",
        "nome": "Campo Capi Gruppo",
        "livello": "REG",
        "approvazione_automatica": True,
        "quota_default": Decimal("51.50"),
    },
]


def crea_tipologie(apps, schema_editor):
    TipologiaCampo = apps.get_model("contributi", "TipologiaCampo")
    for dati in TIPOLOGIE:
        codice = dati.pop("codice")
        TipologiaCampo.objects.get_or_create(codice=codice, defaults=dati)
        dati["codice"] = codice


def rimuovi_tipologie(apps, schema_editor):
    TipologiaCampo = apps.get_model("contributi", "TipologiaCampo")
    TipologiaCampo.objects.filter(codice__in=[t["codice"] for t in TIPOLOGIE]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contributi", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crea_tipologie, rimuovi_tipologie),
    ]
