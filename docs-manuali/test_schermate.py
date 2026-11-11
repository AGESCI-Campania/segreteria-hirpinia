"""Schermate dei manuali di voto e di gestione dell'assemblea
(docs/plan_preparazione_assemblea.md, R11, D32-D35).

Crea un'assemblea con **dati inventati** su un database di test usa e getta,
la apre in Chrome senza interfaccia (Selenium, dipendenza di sviluppo) e
salva le schermate in docs-manuali/<manuale>/img/. Non tocca il database di
sviluppo né dati reali. Non fa parte della suite: si lancia a mano

    mise run manuali-schermate

quando cambiano le pagine descritte (vedi docs-manuali/README.md)."""

from __future__ import annotations

import datetime
import io
import os
from pathlib import Path

import pytest
from allauth.mfa.models import Authenticator
from django.conf import settings
from django.test import Client
from PIL import Image

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import candidature, comitato, odg, presidenza, sedute, votazioni
from apps.assemblee import elenco as elenco_assemblea
from apps.assemblee.models import (
    Assemblea,
    CanaleVoto,
    RuoloAssemblea,
    Seduta,
    SistemaVoto,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo
from apps.voto import codici, scrutinio, urna

pytestmark = pytest.mark.django_db(transaction=True)

CARTELLA = Path(__file__).parent
DESKTOP = (1280, 900)
TELEFONO = (412, 900)

# Nomi inventati: nessun dato reale (CLAUDE.md § Dati sensibili).
CAPI = [
    ("Rossi", "Marco", "M"),
    ("Bianchi", "Giulia", "F"),
    ("Esposito", "Luca", "M"),
    ("Russo", "Chiara", "F"),
    ("Romano", "Paolo", "M"),
    ("Colombo", "Sara", "F"),
    ("Ricci", "Andrea", "M"),
    ("Marino", "Elena", "F"),
    ("Greco", "Davide", "M"),
    ("Bruno", "Marta", "F"),
    ("Gallo", "Stefano", "M"),
    ("Conti", "Anna", "F"),
    ("De Luca", "Matteo", "M"),
    ("Mancini", "Laura", ""),
    ("Costa", "Simone", "M"),
    ("Giordano", "Francesca", "F"),
]
GRUPPI = [("E9101", "BORGO ESEMPIO 1"), ("E9102", "VALLE ESEMPIO 2")]


@pytest.fixture
def browser():
    from selenium import webdriver

    opzioni = webdriver.ChromeOptions()
    opzioni.add_argument("--headless=new")
    opzioni.add_argument("--hide-scrollbars")
    opzioni.add_argument("--force-device-scale-factor=1")
    driver = webdriver.Chrome(options=opzioni)
    yield driver
    driver.quit()


def _persona(username: str, email: str, nome: str, cognome: str, ruolo: str | None = None):
    utente = Utente.objects.create(
        username=username,
        email=email,
        first_name=nome,
        last_name=cognome,
        tipo=TipoUtente.PERSONA,
        stato=StatoUtente.ATTIVO,
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


# Quanto contenuto resta nascosto nel contenitore che scorre più in basso
# della finestra (o nella pagina stessa, per le pagine senza layout fisso).
_MANCANTE = """
var massimo = document.documentElement.scrollHeight - window.innerHeight;
document.querySelectorAll('*').forEach(function (e) {
  var stile = getComputedStyle(e);
  if ((stile.overflowY === 'auto' || stile.overflowY === 'scroll') && e.clientHeight > 100) {
    massimo = Math.max(massimo, e.scrollHeight - e.clientHeight);
  }
});
return massimo;
"""


class Fotografo:
    def __init__(self, driver, base_url: str):
        self.driver = driver
        self.base = base_url

    def accedi(self, utente: Utente) -> None:
        client = Client()
        client.force_login(utente)
        self.driver.get(self.base + "/static/css/catello.css")
        self.driver.delete_all_cookies()
        self.driver.add_cookie(
            {
                "name": settings.SESSION_COOKIE_NAME,
                "value": client.cookies[settings.SESSION_COOKIE_NAME].value,
                "path": "/",
            }
        )

    def apri(self, percorso: str, dimensioni=DESKTOP) -> None:
        self.driver.set_window_size(*dimensioni)
        self.driver.get(self.base + percorso)

    def scatta(self, manuale: str, nome: str, dimensioni=DESKTOP, intera: bool = True) -> None:
        """Schermata della pagina corrente in JPEG (pagina intera, fino a 4000 px)."""
        larghezza, altezza = dimensioni
        self.driver.set_window_size(larghezza, altezza)
        # Il banner dei cookie si chiude come farebbe l'utente.
        self.driver.execute_script(
            "var b=document.getElementById('ag-cookie-banner'); if (b) { b.remove(); }"
        )
        if intera:
            # Il tema ha un layout a viewport fisso: scorre un contenitore
            # interno. Si allarga la finestra di quanto manca a mostrarlo tutto.
            for _ in range(4):
                mancante = self.driver.execute_script(_MANCANTE)
                if mancante <= 0:
                    break
                attuale = self.driver.get_window_size()["height"]
                self.driver.set_window_size(larghezza, min(attuale + int(mancante) + 10, 4000))
        png = self.driver.get_screenshot_as_png()
        immagine = Image.open(io.BytesIO(png)).convert("RGB")
        destinazione = CARTELLA / manuale / "img" / f"{nome}.jpg"
        destinazione.parent.mkdir(parents=True, exist_ok=True)
        immagine.save(destinazione, "JPEG", quality=82, optimize=True)


def _scenario():
    """Un'assemblea primaverile con voto in app, preparata e in corso."""
    segreteria = _persona(
        "segreteria", "segreteria@example.it", "Ufficio", "Segreteria", Ruolo.Tipo.SEGRETERIA
    )
    gruppi = [Gruppo.objects.create(codice=c, nome=n) for c, n in GRUPPI]
    anno = 2027
    for i, (cognome, nome, sesso) in enumerate(CAPI):
        capo = Capo.objects.create(
            codice_socio=str(900100 + i),
            nome=nome,
            cognome=cognome,
            sesso=sesso,
            email="" if i == 5 else f"{nome.lower()}.{cognome.lower().replace(' ', '')}@example.it",
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=anno, gruppo=gruppi[i % 2])
    assemblea = Assemblea.objects.create(
        tipo=TipoAssemblea.PRIMAVERILE,
        anno_scout=anno,
        sistema_voto=SistemaVoto.CATELLO,
        creata_da=segreteria,
    )
    seduta = Seduta.objects.create(
        assemblea=assemblea,
        convocazione=1,
        data=datetime.date(2027, 4, 10),
        ora=datetime.time(9, 30),
        luogo="Sala esempio, Avellino",
    )
    elenco_assemblea.importa_elenco(assemblea, segreteria)

    def avente(cognome):
        return assemblea.aventi_diritto.get(cognome=cognome)

    # Preparazione: comitato elettorale, presidenza, odg, posizioni e candidature.
    for cognome in ("Gallo", "Conti"):
        comitato.aggiungi(assemblea, avente(cognome), segreteria)
    comitato.aggiungi(assemblea, avente("Costa"), segreteria, accesso=False)
    presidenza.aggiungi(assemblea, RuoloAssemblea.PRESIDENTE, avente("Romano"), segreteria)
    presidenza.aggiungi(
        assemblea, RuoloAssemblea.PRESIDENTE, avente("Colombo"), segreteria, accesso=False
    )
    presidenza.aggiungi(assemblea, RuoloAssemblea.SEGRETARIO, avente("Greco"), segreteria)
    for cognome in ("Ricci", "Marino"):
        presidenza.aggiungi(assemblea, RuoloAssemblea.MOZIONI, avente(cognome), segreteria)
    for cognome in ("Gallo", "Conti"):
        presidenza.aggiungi(assemblea, RuoloAssemblea.SCRUTATORE, avente(cognome), segreteria)
    for titolo in (
        "Approvazione del verbale della seduta precedente",
        "Bilancio consuntivo",
        "Elezioni",
    ):
        odg.aggiungi_punto(assemblea, segreteria, titolo)
    punto_elezioni = assemblea.punti_odg.get(titolo="Elezioni")
    comitato_zona = candidature.aggiungi_posizione(
        assemblea,
        segreteria,
        incarico="Membro del Comitato di Zona",
        posti_maschili=1,
        posti_femminili=1,
        punto=punto_elezioni,
    )
    for cognome in ("Rossi", "Esposito", "Bianchi", "Russo"):
        candidature.aggiungi_candidatura(
            comitato_zona,
            segreteria,
            avente=avente(cognome),
            arrivata_il=datetime.date(2027, 3, 20),
        )
    candidature.aggiungi_candidatura(comitato_zona, segreteria, avente=avente("Mancini"))
    foca = candidature.aggiungi_posizione(
        assemblea, segreteria, incarico="Incaricato alla Formazione Capi", posti_indifferenti=1
    )
    for cognome in ("Greco", "Marino"):
        candidature.aggiungi_candidatura(foca, segreteria, avente=avente(cognome))
    return segreteria, assemblea, seduta, avente, comitato_zona, foca


def _in_corso(segreteria, assemblea, seduta, avente):
    sedute.apri_seduta(seduta, segreteria)
    for i, a in enumerate(assemblea.aventi_diritto.order_by("cognome")):
        if i < 13:
            sedute.registra_presenza(seduta, a, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)


def _verifica_autocompletamento(browser, campo: str, testo: str, atteso: str) -> None:
    """Prova nel browser vero che l'autocompletamento mostri i risultati."""
    from selenium.webdriver.support.ui import WebDriverWait

    elemento = browser.find_element("id", campo)
    elemento.clear()
    elemento.send_keys(testo)
    lista = elemento.find_element("xpath", "following-sibling::ul")
    WebDriverWait(browser, 5).until(lambda _: atteso in lista.text)
    elemento.clear()


def test_schermate(live_server, browser, settings):
    settings.SITE_URL = live_server.url
    f = Fotografo(browser, live_server.url)
    segreteria, assemblea, seduta, avente, posizione, foca = _scenario()
    pk, spk = assemblea.pk, seduta.pk

    # --- Manuale di gestione: preparazione ---------------------------------------
    f.accedi(segreteria)
    f.apri("/assemblee/")
    f.scatta("gestione", "assemblee-elenco")
    f.apri("/assemblee/nuova/")
    f.scatta("gestione", "assemblea-nuova")
    f.apri(f"/assemblee/{pk}/")
    f.scatta("gestione", "assemblea-dettaglio")
    # Autocompletamento dell'ufficio di presidenza: l'URL ha già ?per=incarichi.
    _verifica_autocompletamento(browser, "ricerca-incarico", "Bru", "Bruno Marta")
    _verifica_autocompletamento(browser, "ricerca-comitato", "Bru", "Bruno Marta")
    f.apri(f"/assemblee/{pk}/elenco/")
    f.scatta("gestione", "aventi-elenco")
    f.apri(f"/assemblee/{pk}/elenco/{avente('Mancini').pk}/email/")
    f.scatta("gestione", "aventi-dati")
    f.apri(f"/assemblee/{pk}/elenco/aggiungi/")
    f.scatta("gestione", "aventi-aggiungi")
    Capo.objects.filter(cognome="Mancini").update(sesso="F")
    f.apri(f"/assemblee/{pk}/elenco/riallinea/")
    f.scatta("gestione", "aventi-riallinea")
    elenco_assemblea.applica_riallinea(assemblea, segreteria)
    f.apri(f"/assemblee/{pk}/elezioni/")
    f.scatta("gestione", "elezioni-candidature")
    f.apri(f"/assemblee/{pk}/odg/")
    f.scatta("gestione", "ordine-del-giorno")
    f.apri(f"/assemblee/{pk}/duplica/")
    f.scatta("gestione", "assemblea-duplica")

    # --- Il giorno dell'assemblea --------------------------------------------------
    f.apri(f"/assemblee/{pk}/sedute/{spk}/")
    f.scatta("gestione", "seduta-da-aprire")
    _in_corso(segreteria, assemblea, seduta, avente)
    f.apri(f"/assemblee/{pk}/sedute/{spk}/")
    f.scatta("gestione", "seduta-costituita")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/presenze/")
    f.scatta("gestione", "presenze")
    f.scatta("voto", "presenze")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/deleghe/")
    f.scatta("gestione", "deleghe")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/cruscotto/")
    f.scatta("gestione", "cruscotto")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/proiettore/")
    f.scatta("gestione", "proiettore", intera=False)
    f.apri(f"/voto/gestione/{pk}/sedute/{spk}/seggi/")
    f.scatta("gestione", "seggi")
    f.scatta("voto", "seggi")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/votazioni/nuova/")
    f.scatta("gestione", "votazione-nuova")

    elezione = votazioni.apri_votazione(
        seduta, segreteria, tipo="", oggetto="", posizione=posizione
    )
    vpk = elezione.pk
    f.apri(f"/assemblee/{pk}/sedute/{spk}/votazioni/{vpk}/")
    f.scatta("gestione", "votazione-aperta")
    # Due elezioni con l'urna aperta insieme: si votano nella stessa pagina.
    elezione_foca = votazioni.apri_votazione(
        seduta, segreteria, tipo="", oggetto="", posizione=foca
    )
    f.apri(f"/assemblee/{pk}/sedute/{spk}/votazioni/")
    f.scatta("gestione", "votazioni-apri-urne")
    scrutinio.apri_urne(seduta, [elezione, elezione_foca], segreteria)
    candidato_foca = {c.nome.split()[0]: c.pk for c in elezione_foca.candidati.all()}

    # --- Manuale di voto: l'elettore -------------------------------------------------
    candidato = {c.nome.split()[0]: c.pk for c in elezione.candidati.all()}
    elettore = avente("Bruno")
    codice = codici.emetti(seduta, elettore, segreteria)
    browser.delete_all_cookies()
    f.apri("/voto/", TELEFONO)
    f.scatta("voto", "urna-accesso", TELEFONO)
    browser.find_element("name", "codice").send_keys(codici.formatta(codice))
    browser.find_element("css selector", "form button[type=submit]").click()
    f.scatta("voto", "scheda", TELEFONO)
    browser.find_element("id", f"c{vpk}_0-{candidato['Rossi']}").click()
    campo = browser.find_elements("name", f"liberi_{vpk}_0")[0]
    campo.send_keys("Anna Conti")
    from selenium.webdriver.support.ui import Select

    Select(browser.find_elements("name", f"sessi_liberi_{vpk}_0")[0]).select_by_value("F")
    browser.find_element("id", f"c{elezione_foca.pk}_0-{candidato_foca['Greco']}").click()
    f.scatta("voto", "scheda-compilata", TELEFONO)
    browser.find_element(
        "css selector", "form[action$='/voto/scheda/'] button[type=submit]"
    ).click()
    f.scatta("voto", "riepilogo", TELEFONO)
    browser.find_element(
        "css selector", "form[action$='/voto/scheda/'] button.theme-success"
    ).click()
    f.scatta("voto", "ricevuta", TELEFONO)
    f.apri("/voto/scheda/", TELEFONO)
    f.scatta("voto", "attesa", TELEFONO)

    # Altri voti in app, poi chiusura, nomi scritti, risultati e bacheca.
    for cognome, scelte in (
        ("Rossi", urna.Scelte(candidati=(candidato["Esposito"], candidato["Bianchi"]))),
        ("Bianchi", urna.Scelte(candidati=(candidato["Rossi"], candidato["Bianchi"]))),
        ("Colombo", urna.Scelte(esito=urna.ESITO_BIANCA)),
        ("Conti", urna.Scelte(candidati=(candidato["Esposito"], candidato["Russo"]))),
        ("Costa", urna.Scelte(candidati=(candidato["Rossi"], candidato["Russo"]))),
    ):
        votante = avente(cognome)
        if not votante.presenze.exists():
            continue
        codici.emetti(seduta, votante, segreteria)
        urna.vota_insieme(
            codici.codice_attivo(seduta, votante).pk,
            {
                elezione.pk: [scelte],
                elezione_foca.pk: [urna.Scelte(candidati=(candidato_foca["Marino"],))],
            },
        )

    # Il banco: codice a schermo con l'etichetta.
    f.accedi(segreteria)
    browser.set_window_size(*DESKTOP)
    f.apri(f"/assemblee/{pk}/sedute/{spk}/presenze/")
    browser.execute_script(
        "var f=document.querySelector('form[action*=\"/mostra/\"]'); if (f) { f.submit(); }"
    )
    f.scatta("voto", "banco-codice-etichetta")

    f.apri(f"/assemblee/{pk}/sedute/{spk}/votazioni/{vpk}/")
    f.scatta("gestione", "votazione-urna-aperta")
    scrutinio.chiudi_urne(seduta, segreteria)
    elezione.refresh_from_db()
    f.apri(f"/voto/gestione/{pk}/sedute/{spk}/votazioni/{vpk}/nomi/")
    f.scatta("gestione", "nomi-scritti")
    scrutinio.interpreta(elezione, "Anna Conti", avente("Conti"), segreteria)
    voti_carta = {c.pk: {"voti_carta": 0} for c in elezione.candidati.all()}
    votazioni.registra_risultati(
        elezione,
        segreteria,
        per_canale={CanaleVoto.CARTA.value: {"bianche": 0, "nulle": 0}},
        voti_candidati=voti_carta,
    )
    f.apri(f"/assemblee/{pk}/sedute/{spk}/votazioni/{vpk}/")
    f.scatta("gestione", "votazione-esito")
    f.apri(f"/assemblee/{pk}/sedute/{spk}/verbale/")
    f.scatta("gestione", "verbale")

    browser.delete_all_cookies()
    f.apri(f"/voto/bacheca/{vpk}/", TELEFONO)
    f.scatta("voto", "bacheca", TELEFONO)
    f.apri("/voto/verifica/", TELEFONO)
    f.scatta("voto", "verifica", TELEFONO)

    # Presidente con l'accesso: cosa vede.
    presidente = assemblea.incarichi.filter(ruolo=RuoloAssemblea.PRESIDENTE).first().utente
    presidente.set_password("non-usata")
    presidente.save()
    f.accedi(presidente)
    f.apri(f"/assemblee/{pk}/")
    f.scatta("gestione", "presidenza-assemblea")
    assert os.listdir(CARTELLA / "gestione" / "img")
