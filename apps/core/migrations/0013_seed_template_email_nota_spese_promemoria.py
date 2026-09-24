"""Precompila il record di TemplateEmail per il promemoria D-63 (F7),
stesso motivo di `0003_seed_template_email.py`/`0011_seed_template_email_nota_spese.py`."""

from django.db import migrations

_TEMPLATES = [
    {
        "codice": "nota_spese_promemoria",
        "oggetto": "Catello — hai note spese in sospeso",
        "corpo_testo": (
            "Ciao,\n\n"
            "hai delle note spese che richiedono un'azione da parte tua:\n\n"
            "{{ elenco }}\n\n"
            "Puoi visualizzarle qui: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>hai delle note spese che richiedono un'azione da parte tua:</p>"
            "{{ elenco_html }}"
            '<p>Puoi visualizzarle qui: <a href="{{ link }}">{{ link }}</a></p>'
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
        ("core", "0012_alter_templateemail_codice"),
    ]

    operations = [
        migrations.RunPython(crea_template, rimuovi_template),
    ]
