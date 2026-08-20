"""Ciclo di vita del gruppo da interfaccia (D-24): permessi, creazione con
allowlist, disattivazione, riattivazione."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.organizzazione.gruppi import crea_gruppo, disattiva_gruppo, riattiva_gruppo
from apps.organizzazione.models import AllowlistGruppo, Gruppo, StatoGruppoAnno, anno_scout_corrente

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return utente


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


class TestPermessi:
    def test_senza_ruolo_non_crea(self):
        estraneo = _persona("estraneo@campania.agesci.it")
        with pytest.raises(PermissionDenied):
            crea_gruppo(utente=estraneo, codice="E0199", nome="NUOVO", email_istituzionale="n@x.it")

    def test_cg_non_disattiva(self, gruppo):
        cg = _persona("cg@campania.agesci.it")
        Ruolo.objects.create(utente=cg, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        with pytest.raises(PermissionDenied):
            disattiva_gruppo(utente=cg, gruppo=gruppo, motivo="Sciolto")


class TestCreaGruppo:
    def test_crea_e_alimenta_allowlist(self, segreteria):
        gruppo = crea_gruppo(
            utente=segreteria,
            codice="E0199",
            nome="NUOVO GRUPPO",
            email_istituzionale="nuovo@campania.agesci.it",
        )
        assert gruppo.origine == "MANUALE"
        assert AllowlistGruppo.objects.filter(
            email="nuovo@campania.agesci.it", codice_gruppo="E0199"
        ).exists()

    def test_email_obbligatoria(self, segreteria):
        with pytest.raises(ValidationError):
            crea_gruppo(utente=segreteria, codice="E0199", nome="NUOVO", email_istituzionale=" ")

    def test_codice_esistente_rifiutato(self, segreteria, gruppo):
        with pytest.raises(ValidationError):
            crea_gruppo(
                utente=segreteria,
                codice=gruppo.codice,
                nome="DUPLICATO",
                email_istituzionale="d@x.it",
            )


class TestDisattivaGruppo:
    def test_motivo_obbligatorio(self, segreteria, gruppo):
        with pytest.raises(ValidationError):
            disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="  ")

    def test_disattiva_crea_stato_anno_corrente(self, segreteria, gruppo):
        stato = disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")
        assert stato.anno_scout == anno_scout_corrente()
        assert stato.attivo is False
        assert stato.disposto_da == segreteria
        assert not gruppo.e_attivo(anno_scout_corrente())

    def test_doppia_disposizione_stesso_anno_rifiutata(self, segreteria, gruppo):
        disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Sciolto")
        with pytest.raises(ValidationError):
            disattiva_gruppo(utente=segreteria, gruppo=gruppo, motivo="Di nuovo")


class TestRiattivaGruppo:
    def test_blocca_stesso_anno_della_disattivazione(self, segreteria, gruppo):
        anno = anno_scout_corrente()
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=anno, attivo=False)
        with pytest.raises(ValidationError):
            riattiva_gruppo(utente=segreteria, gruppo=gruppo, anno_scout=anno, motivo="Riattivo")

    def test_consente_anno_successivo(self, segreteria, gruppo):
        anno = anno_scout_corrente()
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=anno, attivo=False)
        stato = riattiva_gruppo(
            utente=segreteria, gruppo=gruppo, anno_scout=anno + 1, motivo="Riattivo"
        )
        assert stato.attivo is True
        assert gruppo.e_attivo(anno + 1) is True
