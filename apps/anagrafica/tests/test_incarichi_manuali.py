"""Test dell'assegnazione manuale degli incarichi (M3b, D-32, D-34)."""

import datetime

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.incarichi import (
    RUOLI_RICERCA_CAPO,
    assegna_incarico_manuale,
    cerca_capo_per_codice_socio,
    cessa_incarico_manuale,
)
from apps.anagrafica.models import (
    BrancaUnita,
    Capo,
    CensimentoCapo,
    FunzioneIncarico,
    IncaricoUnita,
    OrigineIncarico,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str) -> Utente:
    return Utente.objects.create(username=email.split("@")[0], email=email, tipo=TipoUtente.PERSONA)


@pytest.fixture
def gruppo() -> Gruppo:
    return Gruppo.objects.create(
        codice="E0133", nome="AVELLINO 1", email_istituzionale="avellino1@campania.agesci.it"
    )


@pytest.fixture
def altro_gruppo() -> Gruppo:
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


@pytest.fixture
def capo(gruppo) -> Capo:
    c = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
    CensimentoCapo.objects.create(capo=c, anno_scout=ANNO, gruppo=gruppo)
    return c


@pytest.fixture
def cg_gruppo(gruppo) -> Utente:
    u = _persona("cg-avellino1@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
    return u


@pytest.fixture
def cg_altro_gruppo(altro_gruppo) -> Utente:
    u = _persona("cg-avellino2@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=altro_gruppo)
    return u


@pytest.fixture
def segreteria() -> Utente:
    u = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
    return u


class TestCercaCapoPerCodiceSocio:
    def test_trova_capo_censito(self, capo, gruppo):
        trovato = cerca_capo_per_codice_socio("10001", anno_scout=ANNO)

        assert trovato is not None
        assert trovato.nome == "MARIO"
        assert trovato.cognome == "ROSSI"
        assert trovato.gruppo_censimento_codice == gruppo.codice

    def test_non_espone_recapiti(self, capo, gruppo):
        trovato = cerca_capo_per_codice_socio("10001", anno_scout=ANNO)

        campi = vars(trovato)
        assert "email" not in campi
        assert "cellulare" not in campi

    def test_nessun_risultato_per_codice_inesistente(self, capo):
        assert cerca_capo_per_codice_socio("99999", anno_scout=ANNO) is None

    def test_ricerca_riservata_a_ruoli_di_zona(self):
        assert Ruolo.Tipo.CG not in RUOLI_RICERCA_CAPO
        assert Ruolo.Tipo.SEGRETERIA in RUOLI_RICERCA_CAPO


class TestAssegnaIncaricoManuale:
    def _dati(self, gruppo, **override):
        dati = {
            "codice_socio": "10001",
            "anno_scout": ANNO,
            "gruppo_servizio": gruppo,
            "codice_unita": "H1",
            "nome_unita": "BRANCO MISTO",
            "branca": BrancaUnita.LC,
            "genere_unita": "MISTO",
            "funzione": FunzioneIncarico.AIUTO_CAPO_UNITA,
            "livello_foca": None,
        }
        dati.update(override)
        return dati

    def test_cg_assegna_a_capo_del_proprio_gruppo(self, capo, gruppo, cg_gruppo):
        incarico = assegna_incarico_manuale(utente=cg_gruppo, **self._dati(gruppo))

        assert incarico.origine == OrigineIncarico.MANUALE
        assert incarico.assegnato_da == cg_gruppo
        assert incarico.cessato_il is None

    def test_cg_non_puo_assegnare_a_capo_censito_altrove(
        self, capo, gruppo, cg_altro_gruppo, altro_gruppo
    ):
        """Deciso con l'utente: D-32 vale alla lettera, un CG non assegna
        incarichi a capi censiti in un gruppo diverso dal proprio."""
        with pytest.raises(PermissionDenied):
            assegna_incarico_manuale(utente=cg_altro_gruppo, **self._dati(altro_gruppo))

    def test_segreteria_puo_assegnare_su_qualunque_gruppo(self, capo, gruppo, segreteria):
        incarico = assegna_incarico_manuale(utente=segreteria, **self._dati(gruppo))
        assert incarico.pk is not None

    def test_capo_non_censito_nellanno_rifiutato(self, capo, gruppo, segreteria):
        with pytest.raises(ValidationError):
            assegna_incarico_manuale(utente=segreteria, **self._dati(gruppo, anno_scout=2099))

    def test_incarico_duplicato_rifiutato(self, capo, gruppo, segreteria):
        assegna_incarico_manuale(utente=segreteria, **self._dati(gruppo))
        with pytest.raises(ValidationError):
            assegna_incarico_manuale(utente=segreteria, **self._dati(gruppo))

    def test_derivati_ricalcolati(self, capo, gruppo, segreteria):
        assegna_incarico_manuale(
            utente=segreteria,
            **self._dati(gruppo, funzione=FunzioneIncarico.CAPO_UNITA),
        )

        censimento = CensimentoCapo.objects.get(capo=capo, anno_scout=ANNO)
        assert censimento.a_disposizione is False

    def test_capo_gruppo_sincronizza_ruolo_cg(self, capo, gruppo, segreteria):
        persona = _persona("mario@campania.agesci.it")
        capo.utente = persona
        capo.save(update_fields=["utente"])

        assegna_incarico_manuale(
            utente=segreteria,
            **self._dati(
                gruppo,
                funzione=FunzioneIncarico.CAPO_GRUPPO,
                branca=BrancaUnita.ADULTI,
                codice_unita="G1",
                nome_unita="COMUNITA CAPI",
            ),
        )

        ruolo = Ruolo.objects.get(utente=persona, tipo=Ruolo.Tipo.CG)
        assert ruolo.gruppo_id == gruppo.codice
        assert ruolo.origine == Ruolo.Origine.DERIVATO

    def test_notifica_gruppo_censimento_e_segreteria(self, capo, gruppo, segreteria):
        mail.outbox.clear()

        assegna_incarico_manuale(utente=segreteria, **self._dati(gruppo))

        destinatari = {r for m in mail.outbox for r in m.to}
        assert gruppo.email_istituzionale in destinatari
        assert segreteria.email in destinatari


class TestBrancaCondizionale:
    """M7: branca obbligatoria solo per Capo unità/Aiuto capo unità."""

    def _dati(self, gruppo, **override):
        dati = {
            "codice_socio": "10001",
            "anno_scout": ANNO,
            "gruppo_servizio": gruppo,
            "codice_unita": "H1",
            "nome_unita": "BRANCO MISTO",
            "branca": "",
            "genere_unita": "MISTO",
            "funzione": FunzioneIncarico.AIUTO_CAPO_UNITA,
            "livello_foca": None,
        }
        dati.update(override)
        return dati

    def test_capo_unita_senza_branca_rifiutato(self, capo, gruppo, segreteria):
        with pytest.raises(ValidationError):
            assegna_incarico_manuale(
                utente=segreteria,
                **self._dati(gruppo, funzione=FunzioneIncarico.CAPO_UNITA, branca=""),
            )

    def test_aiuto_capo_unita_senza_branca_rifiutato(self, capo, gruppo, segreteria):
        with pytest.raises(ValidationError):
            assegna_incarico_manuale(
                utente=segreteria,
                **self._dati(gruppo, funzione=FunzioneIncarico.AIUTO_CAPO_UNITA, branca=""),
            )

    def test_capo_unita_con_branca_ok(self, capo, gruppo, segreteria):
        incarico = assegna_incarico_manuale(
            utente=segreteria,
            **self._dati(gruppo, funzione=FunzioneIncarico.CAPO_UNITA, branca=BrancaUnita.LC),
        )
        assert incarico.branca == BrancaUnita.LC

    def test_funzione_senza_branca_obbligatoria_usa_sconosciuta(self, capo, gruppo, segreteria):
        incarico = assegna_incarico_manuale(
            utente=segreteria,
            **self._dati(
                gruppo,
                funzione=FunzioneIncarico.SUPPORTO_GRUPPO,
                branca="",
                codice_unita="G1",
                nome_unita="COMUNITA CAPI",
            ),
        )
        assert incarico.branca == BrancaUnita.SCONOSCIUTA

    def test_funzione_senza_branca_obbligatoria_rispetta_branca_esplicita(
        self, capo, gruppo, segreteria
    ):
        incarico = assegna_incarico_manuale(
            utente=segreteria,
            **self._dati(
                gruppo,
                funzione=FunzioneIncarico.CAPO_GRUPPO,
                branca=BrancaUnita.ADULTI,
                codice_unita="G1",
                nome_unita="COMUNITA CAPI",
            ),
        )
        assert incarico.branca == BrancaUnita.ADULTI


class TestCessaIncaricoManuale:
    def test_cessa_incarico_manuale(self, capo, gruppo, segreteria):
        incarico = assegna_incarico_manuale(
            utente=segreteria,
            codice_socio="10001",
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            nome_unita="BRANCO",
            branca=BrancaUnita.LC,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            livello_foca=None,
        )

        cessa_incarico_manuale(utente=segreteria, incarico=incarico)

        incarico.refresh_from_db()
        assert incarico.cessato_il is not None
        censimento = CensimentoCapo.objects.get(capo=capo, anno_scout=ANNO)
        assert censimento.a_disposizione is True

    def test_incarico_import_non_cessabile_da_qui(self, capo, gruppo, segreteria):
        incarico = IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            branca=BrancaUnita.LC,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.CAPO_UNITA,
            origine=OrigineIncarico.IMPORT,
        )

        with pytest.raises(ValidationError):
            cessa_incarico_manuale(utente=segreteria, incarico=incarico)

    def test_incarico_gia_cessato_rifiutato(self, capo, gruppo, segreteria):
        incarico = IncaricoUnita.objects.create(
            capo=capo,
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            branca=BrancaUnita.LC,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.CAPO_UNITA,
            origine=OrigineIncarico.MANUALE,
            cessato_il=datetime.datetime.now(datetime.UTC),
        )

        with pytest.raises(ValidationError):
            cessa_incarico_manuale(utente=segreteria, incarico=incarico)

    def test_cg_non_cessa_incarico_fuori_perimetro(
        self, capo, gruppo, altro_gruppo, cg_altro_gruppo, segreteria
    ):
        incarico = assegna_incarico_manuale(
            utente=segreteria,
            codice_socio="10001",
            anno_scout=ANNO,
            gruppo_servizio=gruppo,
            codice_unita="H1",
            nome_unita="BRANCO",
            branca=BrancaUnita.LC,
            genere_unita="MISTO",
            funzione=FunzioneIncarico.AIUTO_CAPO_UNITA,
            livello_foca=None,
        )

        with pytest.raises(PermissionDenied):
            cessa_incarico_manuale(utente=cg_altro_gruppo, incarico=incarico)
