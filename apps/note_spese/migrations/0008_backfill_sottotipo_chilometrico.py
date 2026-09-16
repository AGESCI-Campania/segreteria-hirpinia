# Backfill idempotente di sottotipo_chilometrico sulle due categorie auto
# create dalla data migration 0002 su installazioni preesistenti (rieseguirla
# non cambia nulla: filtra per nome+padre, non per assenza del campo).

from django.db import migrations

MAPPATURA = {
    "Auto (andata e ritorno)": "ANDATA_RITORNO",
    "Auto (altri spostamenti)": "ALTRO",
}


def backfill(apps, schema_editor):
    CategoriaSpesa = apps.get_model("note_spese", "CategoriaSpesa")
    for nome, sottotipo in MAPPATURA.items():
        CategoriaSpesa.objects.filter(nome=nome, parent__nome="Viaggio").update(
            sottotipo_chilometrico=sottotipo
        )


def svuota(apps, schema_editor):
    CategoriaSpesa = apps.get_model("note_spese", "CategoriaSpesa")
    CategoriaSpesa.objects.filter(nome__in=MAPPATURA.keys(), parent__nome="Viaggio").update(
        sottotipo_chilometrico=""
    )


class Migration(migrations.Migration):

    dependencies = [
        ("note_spese", "0007_categoriaspesa_sottotipo_chilometrico"),
    ]

    operations = [
        migrations.RunPython(backfill, svuota),
    ]
