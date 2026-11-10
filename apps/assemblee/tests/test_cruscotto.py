"""Cruscotto in tempo reale, vista proiettore e abilitazione in app (D-70)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, FunzioneIncarico, IncaricoUnita
from apps.assemblee import cruscotto, deleghe, elenco, sedute
from apps.assemblee.models import (
    Assemblea,
    OperatoreVoto,
    Provenienza,
    Seduta,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _persona(email: str, ruolo: str | None = None) -> Utente:
    n = Utente.objects.count()
    utente = Utente.objects.create(
        username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
        Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _persona("segreteria@campania.agesci.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def seduta(segreteria) -> Seduta:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for codice, cognome in (("1", "Rossi"), ("2", "Bianchi"), ("3", "Verdi")):
        capo = Capo.objects.create(codice_socio=codice, nome="Nome", cognome=cognome)
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    IncaricoUnita.objects.create(
        capo_id="3", anno_scout=2026, gruppo_servizio=gruppo, funzione=FunzioneIncarico.AE_GRUPPO
    )
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    seduta = Seduta.objects.create(
        assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22)
    )
    elenco.importa_elenco(assemblea, segreteria)
    elenco.inserisci(
        assemblea,
        segreteria,
        nome="Sara",
        cognome="Neri",
        gruppo=gruppo,
        provenienza=Provenienza.NON_NOTA,
    )
    sedute.apri_seduta(seduta, segreteria)
    for cognome in ("Rossi", "Neri", "Bianchi"):
        sedute.registra_presenza(seduta, assemblea.aventi_diritto.get(cognome=cognome), segreteria)
    # Verdi (AE) delega Rossi.
    deleghe.registra_delega(
        seduta,
        assemblea.aventi_diritto.get(cognome="Verdi"),
        assemblea.aventi_diritto.get(cognome="Rossi"),
        segreteria,
    )
    return seduta


def test_stato_senza_elenco_ha_solo_numeri(seduta):
    dati = cruscotto.stato_seduta(seduta)
    assert (dati["aventi_diritto"], dati["presenti"], dati["soglia"]) == (4, 4, 3)
    assert (dati["presenti_app"], dati["presenti_carta"]) == (3, 1)
    assert dati["raggiunto"]
    assert dati["soglie"] == {"deliberazioni": 3, "elezioni": 3, "revoca": 3}
    assert "elenco" not in dati


def test_elenco_dall_ultimo_arrivato_con_delega(seduta):
    presenti = cruscotto.elenco_presenti(seduta)
    assert [p.avente.cognome for p in presenti] == ["Verdi", "Bianchi", "Neri", "Rossi"]
    verdi = presenti[0]
    assert verdi.delegato.cognome == "Rossi"


def test_presenti_in_app_esclude_la_carta(seduta):
    assert "Neri" not in [p.avente.cognome for p in cruscotto.presenti_in_app(seduta)]


class TestViste:
    def _base(self, seduta):
        return f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}"

    def test_json_per_l_operatore(self, client, seduta):
        operatore = _persona("op@example.it")
        OperatoreVoto.objects.create(assemblea=seduta.assemblea, utente=operatore)
        client.force_login(operatore)
        response = client.get(f"{self._base(seduta)}/stato.json", {"elenco": "1"})
        assert response.status_code == 200
        assert response["Cache-Control"] == "no-store"
        assert len(response.json()["elenco"]) == 4

    def test_json_negato_a_un_capo_qualsiasi(self, client, seduta):
        client.force_login(_persona("capo@example.it"))
        assert client.get(f"{self._base(seduta)}/stato.json").status_code == 403

    def test_proiettore_senza_dati_personali(self, client, seduta, segreteria):
        client.force_login(segreteria)
        html = client.get(f"{self._base(seduta)}/proiettore/").content.decode()
        assert "presenti / aventi diritto" in html
        for cognome in ("Rossi", "Bianchi", "Neri", "Verdi"):
            assert cognome not in html

    def test_abilitazione_app_con_codice_del_delegato(self, client, seduta, segreteria):
        client.force_login(segreteria)
        response = client.get(f"{self._base(seduta)}/abilitazione-app/")
        righe = {p.avente.cognome: p for p in response.context["presenti"]}
        assert set(righe) == {"Rossi", "Bianchi", "Verdi"}
        html = response.content.decode()
        assert "Aggiorna" in html
        assert righe["Verdi"].delegato.codice_socio == "1"
