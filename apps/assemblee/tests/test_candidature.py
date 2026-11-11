"""Posizioni al voto e candidature preparate in anticipo (candidature.py) e
apertura dell'elezione da una posizione."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import candidature, duplica, elenco, odg, sedute, votazioni
from apps.assemblee.models import (
    Assemblea,
    PosizioneVoto,
    Seduta,
    TipoAssemblea,
    TipoVotazione,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def assemblea(segreteria) -> Assemblea:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i, sesso in enumerate(["M", "F", "M", ""]):
        capo = Capo.objects.create(codice_socio=f"10{i}", nome="Nome", cognome=f"C{i}", sesso=sesso)
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _a(assemblea, i):
    return assemblea.aventi_diritto.get(codice_socio=f"10{i}")


def _comitato(assemblea, segreteria, **posti) -> PosizioneVoto:
    return candidature.aggiungi_posizione(
        assemblea, segreteria, incarico="Membro del Comitato di Zona", **posti
    )


class TestPosizioni:
    def test_almeno_un_posto(self, assemblea, segreteria):
        with pytest.raises(ValidationError):
            _comitato(assemblea, segreteria)
        with pytest.raises(ValidationError):
            _comitato(assemblea, segreteria, posti_maschili=-1, posti_femminili=2)
        with pytest.raises(IntegrityError):
            PosizioneVoto.objects.create(assemblea=assemblea, incarico="X")

    def test_posti_e_quote(self, assemblea, segreteria):
        posizione = _comitato(
            assemblea, segreteria, posti_maschili=1, posti_femminili=1, posti_indifferenti=2
        )
        assert posizione.posti == 4 and posizione.con_quote
        libera = _comitato(assemblea, segreteria, posti_indifferenti=2)
        assert not libera.con_quote

    def test_punto_dell_assemblea(self, assemblea, segreteria):
        altra = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=2027)
        punto = odg.aggiungi_punto(altra, segreteria, "Elezioni")
        with pytest.raises(ValidationError):
            _comitato(assemblea, segreteria, posti_indifferenti=1, punto=punto)

    def test_solo_gestori(self, assemblea):
        capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
        with pytest.raises(PermissionDenied):
            _comitato(assemblea, capo, posti_indifferenti=1)


class TestCandidature:
    def test_avente_e_nome_scritto(self, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_indifferenti=2)
        dall_elenco = candidature.aggiungi_candidatura(
            posizione, segreteria, avente=_a(assemblea, 1), sesso="M"
        )
        # Per un avente vale il sesso dell'elenco, non quello passato.
        assert dall_elenco.sesso_effettivo == "F" and dall_elenco.sesso == ""
        esterno = candidature.aggiungi_candidatura(
            posizione, segreteria, nome="Mario Esterno", sesso="M"
        )
        assert esterno.sesso_effettivo == "M"
        with pytest.raises(ValidationError):
            candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 1))
        with pytest.raises(ValidationError):
            candidature.aggiungi_candidatura(posizione, segreteria)

    def test_avvisi_sul_sesso(self, assemblea, segreteria):
        solo_maschile = _comitato(assemblea, segreteria, posti_maschili=1)
        candidature.aggiungi_candidatura(solo_maschile, segreteria, avente=_a(assemblea, 1))
        candidature.aggiungi_candidatura(solo_maschile, segreteria, avente=_a(assemblea, 3))
        avvisi = candidature.avvisi(solo_maschile)
        assert any("C1 Nome: candidatura femminile per posti solo maschili" in a for a in avvisi)
        assert any("C3 Nome: sesso non noto, va indicato" in a for a in avvisi)
        assert any("Posti maschili: 1, candidature maschili: 0" in a for a in avvisi)
        vuota = _comitato(assemblea, segreteria, posti_indifferenti=1)
        assert candidature.avvisi(vuota) == ["Nessuna candidatura."]


def _seduta(assemblea, segreteria) -> Seduta:
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in assemblea.aventi_diritto.nell_elenco():
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


class TestApertura:
    def test_apre_da_posizione(self, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_maschili=1, posti_femminili=1)
        for i in (0, 1):
            candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, i))
        candidature.aggiungi_candidatura(posizione, segreteria, nome="Esterna", sesso="F")
        seduta = _seduta(assemblea, segreteria)
        votazione = votazioni.apri_votazione(
            seduta, segreteria, tipo="", oggetto="", posizione=posizione
        )
        assert votazione.tipo == TipoVotazione.ELEZIONE
        assert votazione.oggetto == "Elezione: Membro del Comitato di Zona"
        assert (votazione.posti, votazione.posti_maschili, votazione.posti_femminili) == (2, 1, 1)
        assert sorted((c.nome, c.sesso) for c in votazione.candidati.all()) == [
            ("C0 Nome", "M"),
            ("C1 Nome", "F"),
            ("Esterna", "F"),
        ]

    def test_con_quote_serve_il_sesso_di_tutti(self, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_maschili=1, posti_indifferenti=1)
        candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 3))
        seduta = _seduta(assemblea, segreteria)
        with pytest.raises(ValidationError, match="indica il sesso di C3 Nome"):
            votazioni.apri_votazione(seduta, segreteria, tipo="", oggetto="", posizione=posizione)
        # Corretto nell'elenco, si apre.
        elenco.aggiorna_sesso(_a(assemblea, 3), "M", segreteria)
        votazioni.apri_votazione(seduta, segreteria, tipo="", oggetto="", posizione=posizione)

    def test_senza_quote_basta_un_avviso(self, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_indifferenti=1)
        candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 3))
        seduta = _seduta(assemblea, segreteria)
        votazioni.apri_votazione(seduta, segreteria, tipo="", oggetto="", posizione=posizione)

    def test_senza_candidature_e_usciti(self, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_indifferenti=1)
        candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 0))
        elenco.elimina([_a(assemblea, 0)], segreteria)
        seduta = _seduta(assemblea, segreteria)
        with pytest.raises(ValidationError, match="non ci sono candidature"):
            votazioni.apri_votazione(seduta, segreteria, tipo="", oggetto="", posizione=posizione)

    def test_dalla_pagina_nuova_votazione(self, client, assemblea, segreteria):
        posizione = _comitato(assemblea, segreteria, posti_indifferenti=1)
        candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 0))
        seduta = _seduta(assemblea, segreteria)
        client.force_login(segreteria)
        client.post(
            f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/votazioni/nuova/",
            {"posizione": posizione.pk},
        )
        votazione = seduta.votazioni.get()
        assert votazione.posizione == posizione and votazione.candidati.count() == 1


def test_pagina_elezioni(client, assemblea, segreteria):
    client.force_login(segreteria)
    url = f"/assemblee/{assemblea.pk}/elezioni/"
    client.post(
        url,
        {
            "azione": "nuova_posizione",
            "incarico": "Responsabile di Zona",
            "posti_maschili": "1",
            "posti_femminili": "1",
            "posti_indifferenti": "0",
        },
    )
    posizione = assemblea.posizioni.get()
    client.post(
        url, {"azione": "candidatura", "posizione": posizione.pk, "avente": _a(assemblea, 0).pk}
    )
    client.post(
        url,
        {
            "azione": "candidatura",
            "posizione": posizione.pk,
            "nome": "Anna Esterna",
            "sesso": "F",
            "arrivata_il": "2026-11-01",
        },
    )
    assert posizione.candidature.count() == 2
    pagina = client.get(url).content.decode()
    assert "Responsabile di Zona" in pagina and "Anna Esterna" in pagina
    candidatura = posizione.candidature.get(nome="Anna Esterna")
    client.post(url, {"azione": "rimuovi_candidatura", "candidatura": candidatura.pk})
    assert posizione.candidature.count() == 1
    client.post(
        url,
        {
            "azione": "modifica_posizione",
            "posizione": posizione.pk,
            f"p{posizione.pk}-incarico": "Responsabile di Zona",
            f"p{posizione.pk}-posti_maschili": "1",
            f"p{posizione.pk}-posti_femminili": "0",
            f"p{posizione.pk}-posti_indifferenti": "0",
        },
    )
    posizione.refresh_from_db()
    assert posizione.posti == 1
    client.post(url, {"azione": "elimina_posizione", "posizione": posizione.pk})
    assert not assemblea.posizioni.exists()


def test_duplicazione_copia_posizioni_e_candidature(assemblea, segreteria):
    punto = odg.aggiungi_punto(assemblea, segreteria, "Elezioni")
    posizione = _comitato(assemblea, segreteria, posti_indifferenti=1, punto=punto)
    candidature.aggiungi_candidatura(posizione, segreteria, avente=_a(assemblea, 0))
    candidature.aggiungi_candidatura(posizione, segreteria, nome="Esterno", sesso="M")
    nuova = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=nuova, convocazione=1, data=datetime.date(2026, 12, 1))
    duplica.copia_in(assemblea, nuova, segreteria)
    copia = nuova.posizioni.get()
    assert copia.punto.assemblea == nuova
    assert sorted(c.nome_completo for c in copia.candidature.all()) == ["C0 Nome", "Esterno"]
    assert all(c.avente is None or c.avente.assemblea == nuova for c in copia.candidature.all())


class TestCreazioneInsieme:
    def _due(self, assemblea, segreteria):
        prima = _comitato(assemblea, segreteria, posti_indifferenti=1)
        candidature.aggiungi_candidatura(prima, segreteria, avente=_a(assemblea, 0))
        seconda = candidature.aggiungi_posizione(
            assemblea, segreteria, incarico="Incaricato Fo.Ca.", posti_indifferenti=1
        )
        candidature.aggiungi_candidatura(seconda, segreteria, avente=_a(assemblea, 1))
        return prima, seconda

    def test_crea_tutte_o_nessuna(self, assemblea, segreteria):
        prima, seconda = self._due(assemblea, segreteria)
        vuota = _comitato(assemblea, segreteria, posti_indifferenti=1)
        seduta = _seduta(assemblea, segreteria)
        assert votazioni.posizioni_da_votare(seduta) == [prima, seconda, vuota]
        with pytest.raises(ValidationError):
            votazioni.crea_elezioni(seduta, segreteria, [prima, vuota])
        assert not seduta.votazioni.exists()
        create = votazioni.crea_elezioni(seduta, segreteria, [prima, seconda])
        assert [v.posizione for v in create] == [prima, seconda]
        assert votazioni.posizioni_da_votare(seduta) == [vuota]

    def test_dalla_pagina_con_apertura_delle_urne(self, client, assemblea, segreteria):
        from apps.assemblee.models import SistemaVoto
        from apps.voto import urna

        assemblea.sistema_voto = SistemaVoto.CATELLO
        assemblea.save()
        prima, seconda = self._due(assemblea, segreteria)
        seduta = _seduta(assemblea, segreteria)
        client.force_login(segreteria)
        base = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/votazioni/"
        assert "Elezioni preparate" in client.get(base).content.decode()
        client.post(base + "elezioni/", {"posizioni": [prima.pk, seconda.pk], "apri_urne": "1"})
        aperte = urna.votazioni_aperte(seduta)
        assert [v.posizione for v in aperte] == [prima, seconda]
