# Data migration idempotente con la struttura iniziale delle categorie di
# spesa (§5.2 dei requisiti Nota Spese). Rieseguirla non duplica: ogni nodo
# è cercato per (parent, nome) prima di crearlo.

from typing import Any

from django.db import migrations

STRUTTURA: list[tuple[str, dict[str, Any], list[tuple[str, dict[str, Any]]]]] = [
    (
        "Viaggio",
        {},
        [
            (
                "Auto (andata e ritorno)",
                {
                    "richiede_allegato": False,
                    "tipo_calcolo": "CHILOMETRICO",
                    "richiede_tratta": True,
                },
            ),
            (
                "Auto (altri spostamenti)",
                {
                    "richiede_allegato": False,
                    "tipo_calcolo": "CHILOMETRICO",
                    "richiede_tratta": True,
                },
            ),
            ("Treno/Nave", {"richiede_allegato": True, "richiede_tratta": True}),
            ("Aereo", {"richiede_allegato": True, "richiede_tratta": True}),
            ("Bus/Metro/Taxi", {"richiede_allegato": True, "richiede_tratta": True}),
            (
                "Parcheggio",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": False,
                },
            ),
        ],
    ),
    (
        "Logistica",
        {},
        [
            (
                "Alloggio",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": True,
                },
            ),
            (
                "Vitto",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": True,
                },
            ),
        ],
    ),
    (
        "Altre spese",
        {},
        [
            (
                "Cancelleria",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": True,
                },
            ),
            (
                "Materiale",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": True,
                },
            ),
            (
                "Varie",
                {
                    "richiede_allegato": True,
                    "richiede_descrizione": True,
                    "descrizione_obbligatoria": True,
                },
            ),
        ],
    ),
]


def crea_categorie(apps, schema_editor):
    CategoriaSpesa = apps.get_model("note_spese", "CategoriaSpesa")
    for nome_padre, attributi_padre, figli in STRUTTURA:
        padre, _ = CategoriaSpesa.objects.get_or_create(
            nome=nome_padre, parent=None, defaults=attributi_padre
        )
        for nome_figlio, attributi_figlio in figli:
            CategoriaSpesa.objects.get_or_create(
                nome=nome_figlio, parent=padre, defaults=attributi_figlio
            )


def rimuovi_categorie(apps, schema_editor):
    CategoriaSpesa = apps.get_model("note_spese", "CategoriaSpesa")
    nomi_padre = [nome for nome, _, _ in STRUTTURA]
    CategoriaSpesa.objects.filter(parent__nome__in=nomi_padre).delete()
    CategoriaSpesa.objects.filter(nome__in=nomi_padre, parent__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("note_spese", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crea_categorie, rimuovi_categorie),
    ]
