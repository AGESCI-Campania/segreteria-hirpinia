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

from .models import CodiceTemplateEmail, TemplateEmail
from .template_email import sostituisci_placeholder

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


def _contenuto_fallback(codice_template: str, contesto: dict[str, str]) -> tuple[str, str]:
    oggetto_default, percorso = _FALLBACK[codice_template]
    # .template.source legge la sorgente grezza del file, mai renderizzata
    # (quindi mai passata per l'autoescape di Django, che guasterebbe un URL
    # con "&" nella querystring): attributo non tipizzato da django-stubs,
    # ma parte dell'API pubblica di django.template.backends.django.Template.
    sorgente_grezza = get_template(percorso).template.source  # type: ignore[attr-defined]
    return oggetto_default, sostituisci_placeholder(sorgente_grezza, contesto)


def invia_email_template(
    *,
    codice_template: str,
    destinatari: list[str],
    contesto: dict[str, str],
    fail_silently: bool = True,
) -> None:
    """Sempre multipart: il corpo testo è sempre presente, l'HTML è
    un'alternativa solo se `corpo_html` è configurato. Se il record manca o
    è vuoto usa il fallback hardcoded (mai bloccare un invio critico come
    l'attivazione account)."""
    if not destinatari:
        return

    template = TemplateEmail.objects.filter(codice=codice_template).first()
    corpo_html_sorgente = ""
    if template is not None and (template.corpo_testo.strip() or template.corpo_html.strip()):
        oggetto = sostituisci_placeholder(template.oggetto, contesto)
        corpo_testo = sostituisci_placeholder(template.corpo_testo, contesto)
        corpo_html_sorgente = template.corpo_html
    else:
        oggetto, corpo_testo = _contenuto_fallback(codice_template, contesto)

    messaggio = EmailMultiAlternatives(subject=oggetto, body=corpo_testo, to=destinatari)
    if corpo_html_sorgente.strip():
        corpo_html = sostituisci_placeholder(corpo_html_sorgente, contesto)
        messaggio.attach_alternative(sanifica_html(corpo_html), "text/html")
    messaggio.send(fail_silently=fail_silently)
