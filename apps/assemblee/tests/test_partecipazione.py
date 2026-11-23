"""Statistiche di partecipazione dei gruppi alle assemblee (pagina, serie
storica e report PDF)."""

import datetime
from decimal import Decimal
from io import BytesIO

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, partecipazione, sedute
from apps.assemblee.models import (
    Assemblea,
    AventeDiritto,
    DelegaAE,
    RichiedenteVerifica,
    Seduta,
    Sesso,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


def _utente(username: str, ruolo: str | None) -> Utente:
    utente = Utente.objects.create(
        username=username,
        email=f"{username}@example.it",
        tipo=TipoUtente.PERSONA,
        stato=StatoUtente.ATTIVO,
    )
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _utente("segr", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def gruppi():
    g1 = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    g2 = Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")
    g3 = Gruppo.objects.create(codice="E0135", nome="ARIANO 1")
    comitato, _ = Gruppo.objects.get_or_create(
        codice="E9001", defaults={"nome": "COM ZONA HIRPINIA", "is_comitato_zona": True}
    )
    # Codici socio: 1xx nel primo gruppo, 2xx nel secondo, 3xx nel terzo, 9xx Comitato.
    for gruppo, codici in (
        (g1, range(100, 104)),
        (g2, (200, 201)),
        (g3, (300,)),
        (comitato, (900,)),
    ):
        for codice in codici:
            capo = Capo.objects.create(codice_socio=str(codice), nome="N", cognome=f"C{codice}")
            CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    return g1, g2, g3, comitato


def _assemblea(segreteria, **campi) -> Assemblea:
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, **campi)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _avente(assemblea, codice):
    return assemblea.aventi_diritto.get(codice_socio=str(codice))


def _presenti(seduta, utente, codici):
    for codice in codici:
        sedute.registra_presenza(seduta, _avente(seduta.assemblea, codice), utente)


def _concludi(assemblea, utente):
    sedute.concludi_assemblea(assemblea, utente)
    assemblea.refresh_from_db()


@pytest.fixture
def assemblea(segreteria, gruppi) -> Assemblea:
    """Prima convocazione senza quorum, seconda costituita: 100, 101 e 900
    presenti, 102 presente per delega di 101; il terzo gruppo assente."""
    assemblea = _assemblea(segreteria)
    prima = assemblea.sedute.get()
    sedute.apri_seduta(prima, segreteria)
    _presenti(prima, segreteria, [200])
    sedute.dichiara_non_costituita(prima, segreteria)
    seconda = sedute.crea_convocazione_successiva(
        assemblea, segreteria, data=datetime.date(2026, 11, 23)
    )
    sedute.apri_seduta(seconda, segreteria)
    _presenti(seconda, segreteria, [100, 101, 900])
    DelegaAE.objects.create(
        seduta=seconda, delegante=_avente(assemblea, 102), delegato=_avente(assemblea, 101)
    )
    # Quorum non raggiunto (4 su 8): qui conta solo che sia la seduta dei lavori.
    Seduta.objects.filter(pk=seconda.pk).update(costituita=True)
    seconda.refresh_from_db()
    sedute.chiudi_lavori(seconda, segreteria)
    AventeDiritto.objects.filter(assemblea=assemblea, codice_socio="100").update(
        sesso=Sesso.FEMMINILE
    )
    AventeDiritto.objects.filter(assemblea=assemblea, codice_socio="101").update(
        sesso=Sesso.MASCHILE
    )
    _concludi(assemblea, segreteria)
    return assemblea


def _riga(p, gruppo):
    return next(r for r in p.gruppi if r.gruppo == gruppo)


def test_conta_i_presenti_della_seduta_dei_lavori(assemblea, gruppi):
    g1, g2, g3, comitato = gruppi
    p = partecipazione.partecipazione(assemblea)
    assert p.seduta.convocazione == 2
    uno = _riga(p, g1).conteggio
    assert (uno.aventi_diritto, uno.presenti, uno.per_delega) == (4, 3, 1)
    assert (uno.maschi, uno.femmine, uno.sesso_non_noto) == (1, 1, 1)
    assert uno.percentuale == Decimal("75.0")
    # Il presente della prima convocazione (senza quorum) non conta.
    assert _riga(p, g2).conteggio.presenti == 0
    assert [r.gruppo for r in p.gruppi] == [g3, g1, g2]  # per nome
    assert p.gruppi_rappresentati == 1
    assert p.comitato.gruppo == comitato and p.comitato.conteggio.presenti == 1
    # Il Comitato conta nel totale di Zona, non fra i gruppi.
    assert (p.totale.aventi_diritto, p.totale.presenti, p.totale.per_delega) == (8, 4, 1)
    assert p.totale.percentuale == Decimal("50.0")


def test_elenco_nominativo_con_il_delegato(assemblea, gruppi):
    p = partecipazione.partecipazione(assemblea)
    presenti = _riga(p, gruppi[0]).presenti
    assert [x.avente.codice_socio for x in presenti] == ["100", "101", "102"]
    assert presenti[2].delegato.codice_socio == "101"
    assert presenti[0].delegato is None


def test_presenti_a_fine_lavori_dopo_la_verifica(segreteria, gruppi):
    assemblea = _assemblea(segreteria)
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    _presenti(seduta, segreteria, [100, 101, 102, 103, 200])
    sedute.dichiara_costituita(seduta, segreteria)
    sedute.apri_verifica(seduta, RichiedenteVerifica.CAPI, segreteria)
    _presenti(seduta, segreteria, [100, 101, 102, 103, 900])
    sedute.chiudi_verifica(seduta, segreteria)
    p = partecipazione.partecipazione(assemblea)
    assert _riga(p, gruppi[1]).conteggio.presenti == 0
    assert p.comitato.conteggio.presenti == 1
    assert p.totale.presenti == 5


def test_trasferito_conta_nel_gruppo_attuale(segreteria, gruppi):
    g1, g2, *_ = gruppi
    assemblea = _assemblea(segreteria)
    elenco.trasferisci(_avente(assemblea, 100), g2, segreteria)
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    _presenti(seduta, segreteria, [100])
    p = partecipazione.partecipazione(assemblea)
    assert _riga(p, g1).conteggio.aventi_diritto == 3
    assert (_riga(p, g2).conteggio.aventi_diritto, _riga(p, g2).conteggio.presenti) == (3, 1)


def test_senza_presenze_nessun_presente(segreteria, gruppi):
    assemblea = _assemblea(segreteria)
    p = partecipazione.partecipazione(assemblea)
    assert p.totale.presenti == 0 and p.totale.aventi_diritto == 8
    assert partecipazione.percentuale(0, 0) is None


def test_disponibile_solo_a_conclusione(segreteria, gruppi):
    assemblea = _assemblea(segreteria)
    with pytest.raises(ValidationError):
        partecipazione.verifica_disponibile(assemblea)


def test_serie_solo_assemblee_vere_e_concluse(assemblea, segreteria, gruppi):
    g1, g2, g3, _ = gruppi
    # Seconda assemblea vera e conclusa, dopo; una di prova e una aperta, escluse.
    seconda = Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027, titolo="Straordinaria"
    )
    Seduta.objects.create(assemblea=seconda, convocazione=1, data=datetime.date(2027, 4, 10))
    elenco.importa_elenco(seconda, segreteria)
    Assemblea.objects.filter(pk=seconda.pk).update(conclusa_il=timezone.now())
    Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE, anno_scout=2028, di_prova=True, conclusa_il=timezone.now()
    )
    Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2028)

    serie = partecipazione.serie_storica()
    assert [p.assemblea for p in serie.assemblee] == [assemblea, seconda]
    riga = next(r for r in serie.gruppi if r.gruppo == g1)
    assert [c.presenti for c in riga.celle] == [3, 0]
    # Complessivo: somma dei presenti sulla somma degli aventi, non media.
    assert riga.complessivo.percentuale == Decimal("37.5")
    assert (riga.assemblee_rappresentato, riga.assemblee_con_aventi) == (1, 2)
    assert serie.comitato is not None
    assert all(not r.gruppo.is_comitato_zona for r in serie.gruppi)


def test_grafici(assemblea):
    p = partecipazione.partecipazione(assemblea)
    barre = partecipazione.barre_grafico(p)
    assert len(barre.barre) == 4  # tre gruppi + Comitato
    assert barre.x_zona == barre.x_inizio + barre.larghezza_utile / 2
    linee = partecipazione.grafico_linee(partecipazione.serie_storica())
    assert len(linee.punti) == 1 and linee.punti[0].valore == Decimal("50.0")


def test_pdf(assemblea, segreteria):
    testo = (
        PdfReader(BytesIO(partecipazione.genera_pdf_assemblea(assemblea, segreteria)))
        .pages[0]
        .extract_text()
    )
    assert "Partecipazione dei gruppi" in testo
    serie = PdfReader(BytesIO(partecipazione.genera_pdf_serie(segreteria)))
    assert "Partecipazione dei gruppi alle assemblee" in serie.pages[0].extract_text()


def test_pdf_nomi_solo_nel_report_dell_assemblea(assemblea, segreteria):
    def testo(contenuto):
        return " ".join(p.extract_text() for p in PdfReader(BytesIO(contenuto)).pages)

    assert "C102" in testo(partecipazione.genera_pdf_assemblea(assemblea, segreteria))
    assert "C102" not in testo(partecipazione.genera_pdf_serie(segreteria))


def test_pdf_solo_gestori(assemblea):
    capo = _utente("capo", None)
    with pytest.raises(PermissionDenied):
        partecipazione.genera_pdf_assemblea(assemblea, capo)
    with pytest.raises(PermissionDenied):
        partecipazione.genera_pdf_serie(capo)


class TestViste:
    def test_pagine_per_i_gestori(self, client, assemblea, segreteria):
        client.force_login(segreteria)
        risposta = client.get(f"/assemblee/{assemblea.pk}/partecipazione/")
        assert risposta.status_code == 200
        assert "Gruppi rappresentati" in risposta.content.decode()
        assert "C102" not in risposta.content.decode()
        risposta = client.get("/assemblee/partecipazione/")
        assert risposta.status_code == 200 and "AVELLINO 1" in risposta.content.decode()
        pdf = client.get(f"/assemblee/{assemblea.pk}/partecipazione/report.pdf")
        assert pdf["Content-Type"] == "application/pdf"
        assert client.get("/assemblee/partecipazione/report.pdf").status_code == 200

    def test_assemblea_non_conclusa_torna_al_riepilogo(self, client, segreteria, gruppi):
        assemblea = _assemblea(segreteria)
        client.force_login(segreteria)
        risposta = client.get(f"/assemblee/{assemblea.pk}/partecipazione/")
        assert risposta.status_code == 302
        assert risposta.url == f"/assemblee/{assemblea.pk}/"

    def test_non_gestori_esclusi(self, client, assemblea):
        client.force_login(_utente("capo", None))
        for url in (
            f"/assemblee/{assemblea.pk}/partecipazione/",
            f"/assemblee/{assemblea.pk}/partecipazione/report.pdf",
            "/assemblee/partecipazione/",
            "/assemblee/partecipazione/report.pdf",
        ):
            assert client.get(url).status_code == 403

    def test_serie_vuota(self, client, segreteria):
        client.force_login(segreteria)
        risposta = client.get("/assemblee/partecipazione/")
        assert "Non c'è ancora nessuna assemblea conclusa" in risposta.content.decode()
