"""Renderer unico degli invii email basati su `TemplateEmail` (M8.3). Punto
unico da cui i service layer coinvolti (`apps/accounts/inviti.py`,
`apps/accounts/deleghe.py`, `apps/accounts/signals.py`,
`apps/anagrafica/incarichi.py`) devono passare invece di chiamare
`render_to_string`/`send_mail` direttamente. Non sceglie mai il trasporto:
`EMAIL_PROVIDER` resta l'unico selettore (CLAUDE.md), qui si costruisce solo
il messaggio."""

from __future__ import annotations

import bleach
from bleach.css_sanitizer import CSSSanitizer
from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

from .models import CodiceTemplateEmail, ImpostazioniPiattaforma, TemplateEmail
from .template_email import (
    applica_prefisso_oggetto,
    contesto_con_variabili_globali,
    sostituisci_placeholder,
)

# Vocabolario ridotto: solo markup semantico, niente <script>/<style>/eventi
# inline. `strip=True` rimuove i tag non ammessi invece di limitarsi a
# neutralizzarli (mai lasciare traccia di markup pericoloso nell'output).
_TAG_AMMESSI = [
    "p",
    "br",
    "strong",
    "em",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "h1",
    "h2",
    "h3",
    "span",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "colgroup",
    "col",
    "img",
]
# Attributi tabelle/immagini (M-tabelle-immagini): allowlist verificata
# empiricamente contro il markup reale prodotto da TinyMCE 8.8.2 (vedi
# template_email_modifica.html), non solo dedotta dalla documentazione — la
# larghezza di <table> e <col> arriva SEMPRE come `style="width:...px"`,
# mai come attributo `width` (la documentazione TinyMCE per <col> dichiara
# solo l'attributo, ma non è quello che il plugin genera davvero). <td>/<th>
# non portano mai una propria larghezza: vive solo su <col>.
_ATTRIBUTI_AMMESSI = {
    "a": ["href", "title"],
    "table": ["border", "cellpadding", "cellspacing", "style"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
    "col": ["style"],
    "img": ["src", "alt", "width", "height"],
}
_PROTOCOLLI_AMMESSI = ["http", "https", "mailto"]
# Solo "width": è l'unica proprietà CSS che serve a "bordi e larghezza" (il
# bordo è già coperto dall'attributo HTML `border`). Un allowlist più ampio
# sarebbe superficie di attacco non necessaria.
_PROPRIETA_CSS_AMMESSE = ["width"]
_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=_PROPRIETA_CSS_AMMESSE)

# Fallback hardcoded (M8.3): stessi file .txt già usati prima di M8, letti
# come sorgente grezza (mai renderizzati con l'autoescape di Django, che
# guasterebbe URL con "&" nella querystring) e passati allo stesso motore di
# sostituzione ridotto del contenuto configurabile — un solo motore, due
# sorgenti possibili.
_FALLBACK: dict[str, tuple[str, str]] = {
    CodiceTemplateEmail.INVITO_ATTIVAZIONE: (
        "Catello — attiva il tuo account",
        "accounts/email/invito_attivazione.txt",
    ),
    CodiceTemplateEmail.FINE_IMPERSONIFICAZIONE: (
        "Catello — è terminata una sessione di assistenza sul tuo account",
        "accounts/email/fine_impersonificazione.txt",
    ),
    CodiceTemplateEmail.DELEGA_CREATA: (
        "Catello — hai concesso una delega",
        "accounts/email/delega_creata.txt",
    ),
    CodiceTemplateEmail.DELEGA_REVOCATA: (
        "Catello — una tua delega è stata revocata",
        "accounts/email/delega_revocata.txt",
    ),
    CodiceTemplateEmail.INCARICO_ASSEGNATO: (
        "Catello — nuovo incarico assegnato",
        "anagrafica/email/incarico_assegnato.txt",
    ),
    CodiceTemplateEmail.INCARICO_CESSATO: (
        "Catello — incarico cessato",
        "anagrafica/email/incarico_cessato.txt",
    ),
}


def sanifica_html(html: str) -> str:
    return bleach.clean(
        html,
        tags=_TAG_AMMESSI,
        attributes=_ATTRIBUTI_AMMESSI,
        protocols=_PROTOCOLLI_AMMESSI,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,
    )


def _contenuto_fallback(codice_template: str) -> tuple[str, str]:
    oggetto_default, percorso = _FALLBACK[codice_template]
    # .template.source legge la sorgente grezza del file, mai renderizzata
    # (quindi mai passata per l'autoescape di Django, che guasterebbe un URL
    # con "&" nella querystring): attributo non tipizzato da django-stubs,
    # ma parte dell'API pubblica di django.template.backends.django.Template.
    # La sostituzione dei placeholder avviene sempre dopo, in
    # `comporre_contenuto()`, per non farla due volte.
    sorgente_grezza = get_template(percorso).template.source  # type: ignore[attr-defined]
    return oggetto_default, sorgente_grezza


def comporre_contenuto(
    *, oggetto: str, corpo_testo: str, corpo_html: str, contesto: dict[str, str]
) -> tuple[str, str, str]:
    """Applica prefisso oggetto e firma comuni (Impostazioni piattaforma) a
    un contenuto grezzo (template configurato o fallback): unico punto usato
    sia dall'invio reale (`invia_email_template`) sia dall'anteprima
    (`TemplateEmailModificaView`), per non duplicare la regola in due posti."""
    impostazioni = ImpostazioniPiattaforma.corrente()
    contesto_esteso = contesto_con_variabili_globali(contesto, impostazioni.prefisso_oggetto_email)

    oggetto_finale = applica_prefisso_oggetto(
        sostituisci_placeholder(oggetto, contesto), impostazioni.prefisso_oggetto_email
    )
    corpo_testo_finale = sostituisci_placeholder(corpo_testo, contesto_esteso)
    corpo_html_finale = sostituisci_placeholder(corpo_html, contesto_esteso)

    if impostazioni.firma_testo.strip():
        corpo_testo_finale = (
            f"{corpo_testo_finale}\n\n"
            f"{sostituisci_placeholder(impostazioni.firma_testo, contesto_esteso)}"
        )
    if impostazioni.firma_html.strip():
        corpo_html_finale = (
            f"{corpo_html_finale}"
            f"{sostituisci_placeholder(impostazioni.firma_html, contesto_esteso)}"
        )

    return oggetto_finale, corpo_testo_finale, corpo_html_finale


def invia_email_template(
    *,
    codice_template: str,
    destinatari: list[str],
    contesto: dict[str, str],
    fail_silently: bool = True,
) -> None:
    """Sempre multipart: il corpo testo è sempre presente, l'HTML è
    un'alternativa solo se il corpo o la firma configurano contenuto HTML. Se
    il record manca o è vuoto usa il fallback hardcoded (mai bloccare un
    invio critico come l'attivazione account)."""
    if not destinatari:
        return

    template = TemplateEmail.objects.filter(codice=codice_template).first()
    if template is not None and (template.corpo_testo.strip() or template.corpo_html.strip()):
        oggetto_grezzo = template.oggetto
        corpo_testo_grezzo = template.corpo_testo
        corpo_html_grezzo = template.corpo_html
    else:
        oggetto_grezzo, corpo_testo_grezzo = _contenuto_fallback(codice_template)
        corpo_html_grezzo = ""

    oggetto, corpo_testo, corpo_html = comporre_contenuto(
        oggetto=oggetto_grezzo,
        corpo_testo=corpo_testo_grezzo,
        corpo_html=corpo_html_grezzo,
        contesto=contesto,
    )

    messaggio = EmailMultiAlternatives(subject=oggetto, body=corpo_testo, to=destinatari)
    if corpo_html.strip():
        messaggio.attach_alternative(sanifica_html(corpo_html), "text/html")
    messaggio.send(fail_silently=fail_silently)
