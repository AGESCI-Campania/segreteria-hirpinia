"""Service layer dell'elenco degli aventi diritto (apps/assemblee/elenco.py, D-70)."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo, FunzioneIncarico
from apps.assemblee import elenco
from apps.assemblee.models import (
    Assemblea,
    AventeDiritto,
    MotivoUscita,
    OperatoreVoto,
    OrigineAvente,
    Provenienza,
    TipoAssemblea,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

CORRENTE = 2027
PRECEDENTE = 2026


def _utente(email: str, ruolo: str | None = None) -> Utente:
    n = Utente.objects.count()
    utente = Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA)
    if ruolo:
        Ruolo.objects.create(utente=utente, tipo=ruolo)
    return utente


@pytest.fixture
def segreteria() -> Utente:
    return _utente("segreteria@example.it", Ruolo.Tipo.SEGRETERIA)


@pytest.fixture
def avellino() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def ariano() -> Gruppo:
    return Gruppo.objects.create(codice="E2913", nome="ARIANO 1")


@pytest.fixture
def comitato() -> Gruppo:
    # E9001 lo crea già una migrazione di dati.
    gruppo, _ = Gruppo.objects.get_or_create(
        codice="E9001", defaults={"nome": "COM ZONA HIRPINIA", "is_comitato_zona": True}
    )
    return gruppo


def _censisci(codice: str, gruppo: Gruppo, anno: int, nome="Nome", cognome=None) -> Capo:
    capo, _ = Capo.objects.get_or_create(
        codice_socio=codice, defaults={"nome": nome, "cognome": cognome or f"Cognome{codice}"}
    )
    CensimentoCapo.objects.create(capo=capo, anno_scout=anno, gruppo=gruppo)
    return capo


def _autunnale() -> Assemblea:
    return Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=CORRENTE)


def _per_codice(assemblea: Assemblea, codice: str) -> AventeDiritto:
    return assemblea.aventi_diritto.get(codice_socio=codice)


class TestAnnoPerGruppo:
    def test_autunnale_senza_dati_correnti_usa_l_anno_precedente(self, avellino):
        _censisci("1", avellino, PRECEDENTE)
        assert elenco.anno_per_gruppo(_autunnale(), avellino) == PRECEDENTE

    def test_autunnale_con_dati_correnti_usa_l_anno_corrente(self, avellino):
        _censisci("1", avellino, CORRENTE)
        assert elenco.anno_per_gruppo(_autunnale(), avellino) == CORRENTE

    def test_primaverile_sempre_anno_corrente(self, avellino):
        primaverile = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=CORRENTE)
        assert elenco.anno_per_gruppo(primaverile, avellino) == CORRENTE


class TestImporta:
    def test_autunnale_con_autorizzazioni_parziali(self, segreteria, avellino, ariano, comitato):
        _censisci("A1", avellino, PRECEDENTE)
        _censisci("A2", avellino, PRECEDENTE)
        # Ariano ha già i dati dell'anno corrente: vale solo quello.
        _censisci("B1", ariano, PRECEDENTE)
        _censisci("B2", ariano, CORRENTE)
        _censisci("C1", comitato, PRECEDENTE)
        assemblea = _autunnale()

        assert elenco.importa_elenco(assemblea, segreteria) == 4
        assert set(assemblea.aventi_diritto.values_list("codice_socio", flat=True)) == {
            "A1",
            "A2",
            "B2",
            "C1",
        }
        assert _per_codice(assemblea, "A1").anno_censimento == PRECEDENTE
        assert _per_codice(assemblea, "B2").anno_censimento == CORRENTE
        assert all(a.vota_in_app for a in assemblea.aventi_diritto.all())
        assert all(a.gruppo_origine_id == a.gruppo_id for a in assemblea.aventi_diritto.all())

    def test_idempotente(self, segreteria, avellino):
        _censisci("A1", avellino, PRECEDENTE)
        assemblea = _autunnale()
        elenco.importa_elenco(assemblea, segreteria)
        assert elenco.importa_elenco(assemblea, segreteria) == 0
        assert assemblea.aventi_diritto.count() == 1

    def test_primaverile_ignora_l_anno_precedente(self, segreteria, avellino):
        _censisci("A1", avellino, PRECEDENTE)
        _censisci("A2", avellino, CORRENTE)
        primaverile = Assemblea.objects.create(tipo=TipoAssemblea.PRIMAVERILE, anno_scout=CORRENTE)
        elenco.importa_elenco(primaverile, segreteria)
        assert list(primaverile.aventi_diritto.values_list("codice_socio", flat=True)) == ["A2"]

    def test_solo_i_gestori(self, avellino):
        capogruppo = _utente("cg@example.it", Ruolo.Tipo.CG)
        with pytest.raises(PermissionDenied):
            elenco.importa_elenco(_autunnale(), capogruppo)


class TestInserisci:
    def test_nuovo_capo_senza_codice_vota_su_carta(self, segreteria, avellino):
        assemblea = _autunnale()
        avente = elenco.inserisci(
            assemblea,
            segreteria,
            nome="Anna",
            cognome="Bianchi",
            gruppo=avellino,
            provenienza=Provenienza.PASSAGGIO_CLAN,
            incarichi=[{"funzione": FunzioneIncarico.AIUTO_CAPO_UNITA, "branca": "EG"}, {}],
        )
        assert not avente.vota_in_app
        assert avente.origine == OrigineAvente.MANUALE
        assert avente.anno_censimento == PRECEDENTE
        assert list(avente.incarichi.values_list("funzione", flat=True)) == [
            FunzioneIncarico.AIUTO_CAPO_UNITA
        ]

    def test_codice_socio_censito_vota_in_app(self, segreteria, avellino, ariano):
        """Un capo eliminato per errore e reinserito, o censito l'anno scorso in
        un altro gruppo della Zona: ha dati da BuonaStrada, vota in app."""
        _censisci("B1", ariano, PRECEDENTE)
        avente = elenco.inserisci(
            _autunnale(),
            segreteria,
            nome="Nome",
            cognome="CognomeB1",
            gruppo=avellino,
            provenienza=Provenienza.RIENTRO,
            codice_socio="B1",
        )
        assert avente.vota_in_app
        assert avente.capo_id == "B1"

    def test_codice_socio_duplicato(self, segreteria, avellino):
        _censisci("A1", avellino, PRECEDENTE)
        assemblea = _autunnale()
        elenco.importa_elenco(assemblea, segreteria)
        with pytest.raises(ValidationError):
            elenco.inserisci(
                assemblea,
                segreteria,
                nome="X",
                cognome="Y",
                gruppo=avellino,
                provenienza=Provenienza.NON_NOTA,
                codice_socio="A1",
            )


class TestModifiche:
    @pytest.fixture
    def assemblea(self, segreteria, avellino) -> Assemblea:
        _censisci("A1", avellino, PRECEDENTE)
        _censisci("A2", avellino, PRECEDENTE)
        assemblea = _autunnale()
        elenco.importa_elenco(assemblea, segreteria)
        return assemblea

    def test_elimina_e_ripristina(self, assemblea, segreteria):
        a1 = _per_codice(assemblea, "A1")
        assert elenco.elimina(assemblea.aventi_diritto.all(), segreteria) == 2
        a1.refresh_from_db()
        assert a1.uscita == MotivoUscita.ELIMINATO
        assert a1.eliminato_da == segreteria
        assert assemblea.aventi_diritto.nell_elenco().count() == 0

        elenco.ripristina(a1, segreteria)
        assert list(assemblea.aventi_diritto.nell_elenco()) == [a1]

    def test_trasferimento_conserva_origine_e_voto(self, assemblea, segreteria, avellino, ariano):
        a1 = _per_codice(assemblea, "A1")
        elenco.trasferisci(a1, ariano, segreteria)
        a1.refresh_from_db()
        assert a1.gruppo == ariano
        assert a1.gruppo_origine == avellino
        assert a1.trasferito
        assert a1.vota_in_app

    def test_passaggio_a_carta_da_operatore(self, assemblea):
        operatore = _utente("operatore@example.it")
        OperatoreVoto.objects.create(assemblea=assemblea, utente=operatore)
        a1 = _per_codice(assemblea, "A1")

        elenco.passa_a_carta(a1, operatore)
        assert not a1.vota_in_app
        assert a1.passato_a_carta
        assert a1.voto_cartaceo_da == operatore

        elenco.annulla_passaggio_a_carta(a1, operatore)
        assert a1.vota_in_app
        assert not a1.passato_a_carta

    def test_passaggio_a_carta_vietato_a_chi_non_opera(self, assemblea):
        with pytest.raises(PermissionDenied):
            elenco.passa_a_carta(_per_codice(assemblea, "A1"), _utente("capo@example.it"))

    def test_assemblea_conclusa_non_modificabile(self, assemblea, segreteria):
        assemblea.conclusa_il = timezone.now()
        assemblea.save()
        with pytest.raises(ValidationError):
            elenco.elimina(assemblea.aventi_diritto.all(), segreteria)


class TestAggiornaGruppo:
    @pytest.fixture
    def assemblea(self, segreteria, avellino, ariano) -> Assemblea:
        _censisci("A1", avellino, PRECEDENTE)  # resta censito
        _censisci("A2", avellino, PRECEDENTE)  # non più censito
        _censisci("A3", avellino, PRECEDENTE)  # eliminato a mano, ma censito
        _censisci("A4", avellino, PRECEDENTE)  # trasferito a mano ad Ariano
        _censisci("B1", ariano, PRECEDENTE)  # ora censito in Avellino
        assemblea = _autunnale()
        elenco.importa_elenco(assemblea, segreteria)
        elenco.elimina([_per_codice(assemblea, "A3")], segreteria)
        elenco.trasferisci(_per_codice(assemblea, "A4"), ariano, segreteria)
        elenco.inserisci(
            assemblea,
            segreteria,
            nome="Luca",
            cognome="Verdi",
            gruppo=avellino,
            provenienza=Provenienza.NON_NOTA,
        )
        elenco.inserisci(
            assemblea,
            segreteria,
            nome="Sara",
            cognome="Neri",
            gruppo=avellino,
            provenienza=Provenienza.NUOVO_INGRESSO,
            codice_socio="A6",
        )
        # Arrivano i censiti dell'anno corrente di Avellino.
        for codice in ("A1", "A3", "B1"):
            _censisci(codice, avellino, CORRENTE)
        _censisci("A5", avellino, CORRENTE, nome="Luca", cognome="Verdi")
        _censisci("A6", avellino, CORRENTE, nome="Sara", cognome="Neri")
        _censisci("A7", avellino, CORRENTE)
        return assemblea

    def test_gruppi_da_aggiornare(self, assemblea, avellino):
        assert elenco.gruppi_da_aggiornare(assemblea) == [avellino]

    def test_anteprima(self, assemblea, avellino):
        anteprima = elenco.anteprima_aggiorna_gruppo(assemblea, avellino)
        assert [c.capo_id for c in anteprima.entrano] == ["A7"]
        assert {a.codice_socio for a in anteprima.aggiornati} == {"A1", "B1"}
        assert [a.codice_socio for a, _ in anteprima.da_manuale] == ["A6"]
        assert [(a.cognome, c.capo_id) for a, c in anteprima.omonimi] == [("Verdi", "A5")]
        assert [a.codice_socio for a in anteprima.escono] == ["A2"]
        assert [a.codice_socio for a in anteprima.restano_eliminati] == ["A3"]

    def test_applica_con_omonimo_confermato(self, assemblea, segreteria, avellino, ariano):
        verdi = assemblea.aventi_diritto.get(cognome="Verdi")
        elenco.applica_aggiorna_gruppo(
            assemblea, avellino, segreteria, omonimi_confermati=[verdi.pk]
        )

        a1 = _per_codice(assemblea, "A1")
        assert a1.anno_censimento == CORRENTE and a1.vota_in_app
        assert _per_codice(assemblea, "A2").uscita == MotivoUscita.NON_CENSITO
        assert _per_codice(assemblea, "A3").uscita == MotivoUscita.ELIMINATO
        a4 = _per_codice(assemblea, "A4")
        assert not a4.eliminato and a4.gruppo == ariano
        b1 = _per_codice(assemblea, "B1")
        assert b1.gruppo == avellino and b1.gruppo_origine == avellino
        verdi.refresh_from_db()
        assert verdi.codice_socio == "A5"
        assert verdi.origine == OrigineAvente.IMPORT and verdi.vota_in_app
        neri = _per_codice(assemblea, "A6")
        assert neri.origine == OrigineAvente.IMPORT and neri.vota_in_app
        assert _per_codice(assemblea, "A7").vota_in_app
        assert elenco.gruppi_da_aggiornare(assemblea) == []

    def test_omonimo_non_confermato_entra_come_capo_distinto(self, assemblea, segreteria, avellino):
        elenco.applica_aggiorna_gruppo(assemblea, avellino, segreteria)
        verdi = assemblea.aventi_diritto.filter(cognome="Verdi")
        assert verdi.count() == 2
        assert set(verdi.values_list("codice_socio", flat=True)) == {"", "A5"}

    def test_riallineare_due_volte_non_cambia_nulla(self, assemblea, segreteria, avellino):
        elenco.applica_aggiorna_gruppo(assemblea, avellino, segreteria)
        assert elenco.anteprima_aggiorna_gruppo(assemblea, avellino).vuota
