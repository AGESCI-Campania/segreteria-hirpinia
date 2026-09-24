"""Precompila i 4 record di TemplateEmail introdotti da F7 (D-62, modulo
Nota Spese) con gli stessi contenuti dei fallback .txt: stesso motivo di
`0003_seed_template_email.py`, il primo invio dopo il deploy non deve usare
un template vuoto."""

from django.db import migrations

_TEMPLATES = [
    {
        "codice": "nota_spese_rilievo",
        "oggetto": "Catello — la tua nota spese ha un rilievo",
        "corpo_testo": (
            "Ciao,\n\n"
            "la tua nota spese {{ numero }} ({{ evento }}) ha ricevuto un rilievo:\n\n"
            "{{ motivo }}\n\n"
            "Per i dettagli e per proseguire: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la tua nota spese {{ numero }} ({{ evento }}) ha ricevuto un rilievo:</p>"
            "<p>{{ motivo }}</p>"
            '<p>Per i dettagli e per proseguire: <a href="{{ link }}">{{ link }}</a></p>'
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "nota_spese_approvata",
        "oggetto": "Catello — nota spese approvata",
        "corpo_testo": (
            "Ciao,\n\n"
            "la tua nota spese {{ numero }} ({{ evento }}) è stata approvata.\n\n"
            "Dettagli: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la tua nota spese {{ numero }} ({{ evento }}) è stata approvata.</p>"
            '<p>Dettagli: <a href="{{ link }}">{{ link }}</a></p>'
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "nota_spese_respinta",
        "oggetto": "Catello — nota spese respinta",
        "corpo_testo": (
            "Ciao,\n\n"
            "la tua nota spese {{ numero }} ({{ evento }}) è stata respinta.\n\n"
            "Motivo: {{ causale }}\n\n"
            "Dettagli: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la tua nota spese {{ numero }} ({{ evento }}) è stata respinta.</p>"
            "<p>Motivo: {{ causale }}</p>"
            '<p>Dettagli: <a href="{{ link }}">{{ link }}</a></p>'
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "nota_spese_liquidata",
        "oggetto": "Catello — nota spese liquidata",
        "corpo_testo": (
            "Ciao,\n\n"
            "la tua nota spese {{ numero }} ({{ evento }}) è stata liquidata.\n\n"
            "Dettagli: {{ link }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la tua nota spese {{ numero }} ({{ evento }}) è stata liquidata.</p>"
            '<p>Dettagli: <a href="{{ link }}">{{ link }}</a></p>'
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
        ("core", "0010_alter_templateemail_codice"),
    ]

    operations = [
        migrations.RunPython(crea_template, rimuovi_template),
    ]
