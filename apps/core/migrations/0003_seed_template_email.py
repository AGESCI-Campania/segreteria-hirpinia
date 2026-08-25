"""Precompila i 6 record di TemplateEmail con i contenuti attuali dei
template .txt esistenti (M8), riscritti sul motore di sostituzione ridotto
(solo `{{ variabile }}`, mai tag Django): altrimenti il primo invio dopo il
deploy userebbe un template vuoto. Il testo hardcoded qui è la migrazione
storica del contenuto al momento di M8: non va aggiornato per seguire futuri
cambi applicativi, quelli si fanno da interfaccia."""

from django.db import migrations

_TEMPLATES = [
    {
        "codice": "invito_attivazione",
        "oggetto": "Catello — attiva il tuo account",
        "corpo_testo": (
            "Ciao,\n\n"
            "la segreteria della Zona Hirpinia ti invita ad attivare il tuo account "
            "su Catello.\n\n"
            "Codice di attivazione: {{ codice }}\n\n"
            "Per attivare l'account, vai su:\n"
            "{{ link_attivazione }}\n\n"
            "Il codice scade il {{ scadenza }}. Se nel frattempo scade, potrai "
            "richiederne uno nuovo dalla pagina di recupero:\n"
            "{{ link_recupero }}\n"
            "{{ paragrafo_gruppo }}"
            "Se non hai richiesto tu questo invito, ignora questa email.\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la segreteria della Zona Hirpinia ti invita ad attivare il tuo "
            "account su Catello.</p>"
            "<p>Codice di attivazione: <strong>{{ codice }}</strong></p>"
            '<p>Per attivare l\'account: <a href="{{ link_attivazione }}">'
            "{{ link_attivazione }}</a></p>"
            "<p>Il codice scade il {{ scadenza }}. Se nel frattempo scade, puoi "
            'richiederne uno nuovo dalla <a href="{{ link_recupero }}">pagina di '
            "recupero</a>.</p>"
            "{{ paragrafo_gruppo }}"
            "<p>Se non hai richiesto tu questo invito, ignora questa email.</p>"
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "fine_impersonificazione",
        "oggetto": "Catello — è terminata una sessione di assistenza sul tuo account",
        "corpo_testo": (
            "Ciao,\n\n"
            "ti informiamo che il {{ quando }} {{ amministratore }} ha concluso una "
            "sessione di assistenza sul tuo account Catello (impersonificazione).\n\n"
            "Se non eri a conoscenza di questa richiesta di assistenza, contatta la "
            "segreteria di Zona.\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>ti informiamo che il {{ quando }} {{ amministratore }} ha concluso "
            "una sessione di assistenza sul tuo account Catello "
            "(impersonificazione).</p>"
            "<p>Se non eri a conoscenza di questa richiesta di assistenza, contatta "
            "la segreteria di Zona.</p>"
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "delega_creata",
        "oggetto": "Catello — hai concesso una delega",
        "corpo_testo": (
            "Ciao,\n\n"
            "hai concesso una delega per il ruolo {{ ruolo }} a {{ delegato }}, con "
            "scadenza {{ scadenza }}.\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>hai concesso una delega per il ruolo {{ ruolo }} a {{ delegato }}, "
            "con scadenza {{ scadenza }}.</p>"
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "delega_revocata",
        "oggetto": "Catello — una tua delega è stata revocata",
        "corpo_testo": (
            "Ciao,\n\n"
            "la delega che avevi concesso per il ruolo {{ ruolo }} a {{ delegato }} "
            "è stata revocata{{ revocata_da_frase }}.\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>la delega che avevi concesso per il ruolo {{ ruolo }} a "
            "{{ delegato }} è stata revocata{{ revocata_da_frase }}.</p>"
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "incarico_assegnato",
        "oggetto": "Catello — nuovo incarico assegnato",
        "corpo_testo": (
            "Ciao,\n\n"
            "è stato assegnato manualmente un nuovo incarico:\n\n"
            "Capo: {{ capo }}\n"
            "Gruppo di servizio: {{ gruppo_servizio }}\n"
            "Unità: {{ unita }}\n"
            "Funzione: {{ funzione }}\n"
            "Assegnato da: {{ assegnato_da }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>è stato assegnato manualmente un nuovo incarico:</p>"
            "<ul>"
            "<li>Capo: {{ capo }}</li>"
            "<li>Gruppo di servizio: {{ gruppo_servizio }}</li>"
            "<li>Unità: {{ unita }}</li>"
            "<li>Funzione: {{ funzione }}</li>"
            "<li>Assegnato da: {{ assegnato_da }}</li>"
            "</ul>"
            "<p>— Catello, AGESCI Zona Hirpinia</p>"
        ),
    },
    {
        "codice": "incarico_cessato",
        "oggetto": "Catello — incarico cessato",
        "corpo_testo": (
            "Ciao,\n\n"
            "è stato cessato un incarico assegnato manualmente:\n\n"
            "Capo: {{ capo }}\n"
            "Gruppo di servizio: {{ gruppo_servizio }}\n"
            "Unità: {{ unita }}\n"
            "Funzione: {{ funzione }}\n\n"
            "— Catello, AGESCI Zona Hirpinia"
        ),
        "corpo_html": (
            "<p>Ciao,</p>"
            "<p>è stato cessato un incarico assegnato manualmente:</p>"
            "<ul>"
            "<li>Capo: {{ capo }}</li>"
            "<li>Gruppo di servizio: {{ gruppo_servizio }}</li>"
            "<li>Unità: {{ unita }}</li>"
            "<li>Funzione: {{ funzione }}</li>"
            "</ul>"
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
        ("core", "0002_templateemail"),
    ]

    operations = [
        migrations.RunPython(crea_template, rimuovi_template),
    ]
