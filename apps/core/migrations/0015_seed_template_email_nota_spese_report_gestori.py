"""Precompila il record di TemplateEmail per il report periodico ai
gestori D-64 (F7), stesso motivo delle migrazioni di seed precedenti."""

from django.db import migrations

_TEMPLATES = [
    {
        "codice": "nota_spese_report_gestori",
        "oggetto": "Catello — report note spese in sospeso",
        "corpo_testo": (
            "Ciao,\n\n"
            "report periodico delle note spese non ancora liquidate "
            "({{ numero_note }}):\n\n"
            "{{ elenco }}\n\n"
            "Elenco completo con evidenza delle eccezioni: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>report periodico delle note spese non ancora liquidate "
            "({{ numero_note }}):</p>"
            "{{ elenco_html }}"
            '<p>Elenco completo con evidenza delle eccezioni: <a href="{{ link }}">{{ link }}</a></p>'
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
]


def crea_template(apps, schema_editor):
    TemplateEmail = apps.get_model("core", "TemplateEmail")
    for dati in _TEMPLATES:
        TemplateEmail.objects.get_or_create(codice=dati["codice"], defaults=dati)


def rimuovi_template(apps, schema_editor):
    TemplateEmail = apps.get_model("core", "TemplateEmail")
    TemplateEmail.objects.filter(codice__in=[dati["codice"] for dati in _TEMPLATES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_alter_templateemail_codice"),
    ]

    operations = [
        migrations.RunPython(crea_template, rimuovi_template),
    ]
