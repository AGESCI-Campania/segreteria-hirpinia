"""Precompila il record di TemplateEmail per l'email del codice di voto (D-71),
stesso motivo delle migrazioni di seed precedenti: senza il record il flusso
non compare in Impostazioni › Template email e non si può modificare.

Il testo è identico al fallback `templates/voto/email/codice_voto.txt`, e
`corpo_html` resta vuoto di proposito: `{{ come_votare }}` è un paragrafo in
testo semplice che cambia con la modalità di voto (con il link all'urna o
senza), e il motore ridotto non ha condizionali per costruirne una versione
HTML equivalente. Così l'email inviata resta quella di prima."""

from django.db import migrations

_TEMPLATES = [
    {
        "codice": "codice_voto",
        "oggetto": "Catello — il tuo codice di voto",
        "corpo_testo": (
            "Ciao {{ nome }},\n\n"
            "sei registrato fra i presenti di {{ assemblea }}. Questo è il tuo codice\n"
            "personale per votare:\n\n"
            "    {{ codice }}\n\n"
            "{{ come_votare }}\n\n"
            "Il codice vale per tutte le votazioni a scrutinio segreto di questa seduta.\n"
            "Non condividerlo: chi lo conosce può votare al posto tuo. Se lo perdi, chiedi\n"
            "alla segreteria un nuovo codice: quello vecchio smette di funzionare.\n"
        ),
        "corpo_html": "",
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
        ("core", "0016_alter_templateemail_codice"),
    ]

    operations = [
        migrations.RunPython(crea_template, rimuovi_template),
    ]
