# Data migration idempotente che popola i comuni italiani in `Localita`
# (D-56). Fonte: confini amministrativi ufficiali ISTAT 2026 (licenza
# IODL, https://www.istat.it/storage/cartografia/confini_amministrativi/
# generalizzati/2026/Limiti01012026_g.zip) per il centroide comunale — il
# CSV ISTAT dei codici comune non contiene lat/lon (verificato scaricandolo,
# vedi docs/ignored/PLAN-nota-spese.md) — incrociato con l'elenco ISTAT dei
# codici/denominazioni (https://www.istat.it/storage/codici-unita-
# amministrative/Elenco-comuni-italiani.xlsx) per nome/provincia. 7893
# comuni su 7896: 3 mancano perché fusi in un nuovo comune (Castegnero
# Nanto) non ancora presente nello shapefile alla data dell'estrazione,
# accettato come scostamento noto invece di inventare le coordinate
# mancanti.

import csv
from decimal import Decimal
from pathlib import Path

from django.db import migrations

FILE_COMUNI = Path(__file__).resolve().parent.parent / "data" / "comuni_italiani.csv"


def crea_localita(apps, schema_editor):
    Localita = apps.get_model("note_spese", "Localita")
    with FILE_COMUNI.open(encoding="utf-8", newline="") as f:
        for riga in csv.DictReader(f):
            Localita.objects.get_or_create(
                codice_istat=riga["codice_istat"],
                defaults={
                    "nome": riga["nome"],
                    "provincia": riga["provincia"],
                    "estero": False,
                    "latitudine": Decimal(riga["latitudine"]),
                    "longitudine": Decimal(riga["longitudine"]),
                },
            )


def rimuovi_localita(apps, schema_editor):
    Localita = apps.get_model("note_spese", "Localita")
    Localita.objects.filter(estero=False, codice_istat__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("note_spese", "0002_categorie_iniziali"),
    ]

    operations = [
        migrations.RunPython(crea_localita, rimuovi_localita),
    ]
