"""Riepilogo per gruppo dello stato di invio del contributo Fo.Ca. (issue
#11): semaforo, esclusione E9001, perimetro della dichiarazione "nessun
rimborso" (CG solo sul proprio gruppo, ADMIN/SEGRETERIA/RDZ su qualunque)."""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, TipoUtente, Utente
from apps.anagrafica.models import Capo
from apps.contributi.models import (
    Campagna,
    ContributoPartecipazione,
    DichiarazioneNessunRimborso,
    Partecipazione,
    StatoCampagna,
    StatoPartecipazione,
    TipologiaCampo,
)
from apps.contributi.riepilogo_gruppi import (
    StatoSemaforo,
    dichiara_nessun_rimborso,
    revoca_dichiarazione_nessun_rimborso,
    riepilogo_gruppi,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

ANNO = 2026


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


@pytest.fixture
def cfm() -> TipologiaCampo:
    return TipologiaCampo.objects.get(codice="CFM")


@pytest.fixture
def campagna_aperta() -> Campagna:
    return Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def campagna_chiusa() -> Campagna:
    c = Campagna.objects.create(
        anno=ANNO,
        budget=Decimal("1000.00"),
        tetto_per_partecipazione=Decimal("50.00"),
        data_inizio_inserimento=datetime.date(2025, 10, 1),
        data_fine_inserimento=datetime.date(2026, 9, 30),
    )
    Campagna.objects.filter(pk=c.pk).update(stato=StatoCampagna.CHIUSA)
    c.refresh_from_db()
    return c


def _partecipazione(campagna, gruppo, tipologia, codice_socio, *, importo=None) -> Partecipazione:
    capo = Capo.objects.create(codice_socio=codice_socio, nome="MARIO", cognome="ROSSI")
    p = Partecipazione(
        campagna=campagna,
        capo=capo,
        gruppo=gruppo,
        tipologia=tipologia,
        data_inizio=datetime.date(campagna.anno, 6, 1),
        data_fine=datetime.date(campagna.anno, 6, 8),
        luogo="Base scout",
        quota_versata=Decimal("51.50"),
        stato=StatoPartecipazione.APPROVATA,
    )
    p.full_clean(exclude=["stato"])
    p.save()
    if importo is not None:
        ContributoPartecipazione.objects.create(
            partecipazione=p, importo=importo, is_simulazione=False
        )
    return p


class TestRiepilogoGruppi:
    def test_esclude_comitato_zona(self):
        # E9001 è già seedato da apps/organizzazione/migrations/0002_seed_e9001.py.
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        campagna = Campagna.objects.create(
            anno=ANNO,
            budget=Decimal("1000.00"),
            data_inizio_inserimento=datetime.date(2025, 10, 1),
            data_fine_inserimento=datetime.date(2026, 9, 30),
        )
        righe = riepilogo_gruppi(campagna)
        assert [r.gruppo_codice for r in righe] == [gruppo.codice]

    def test_stato_rosso_senza_nulla(self, campagna_aperta):
        Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        riga = riepilogo_gruppi(campagna_aperta)[0]
        assert riga.account_attivato is False
        assert riga.iban_caricato is False
        assert riga.capi_inseriti == 0
        assert riga.stato == StatoSemaforo.ROSSO

    def test_stato_giallo_parziale(self, campagna_aperta):
        gruppo = Gruppo.objects.create(
            codice="E0133", nome="AVELLINO 1", iban="IT60X0542811101000000123456"
        )
        Utente.objects.create(
            username="cg1",
            email="cg@x.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=gruppo,
            last_login=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        riga = riepilogo_gruppi(campagna_aperta)[0]
        assert riga.account_attivato is True
        assert riga.iban_caricato is True
        assert riga.capi_inseriti == 0
        assert riga.stato == StatoSemaforo.GIALLO

    def test_stato_verde_completo(self, campagna_aperta, cfm):
        gruppo = Gruppo.objects.create(
            codice="E0133", nome="AVELLINO 1", iban="IT60X0542811101000000123456"
        )
        Utente.objects.create(
            username="cg1",
            email="cg@x.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=gruppo,
            last_login=datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC),
        )
        _partecipazione(campagna_aperta, gruppo, cfm, "10001")
        riga = riepilogo_gruppi(campagna_aperta)[0]
        assert riga.capi_inseriti == 1
        assert riga.stato == StatoSemaforo.VERDE

    def test_capi_inseriti_conta_capi_distinti(self, campagna_aperta, cfm):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        capo = Capo.objects.create(codice_socio="10001", nome="MARIO", cognome="ROSSI")
        # due partecipazioni dello stesso capo, date diverse
        campo_estivo = TipologiaCampo.objects.get(codice="CFM")
        p1 = Partecipazione(
            campagna=campagna_aperta,
            capo=capo,
            gruppo=gruppo,
            tipologia=campo_estivo,
            data_inizio=datetime.date(2026, 6, 1),
            data_fine=datetime.date(2026, 6, 8),
            luogo="Base",
            quota_versata=Decimal("51.50"),
            stato=StatoPartecipazione.APPROVATA,
        )
        p1.full_clean(exclude=["stato"])
        p1.save()
        p2 = Partecipazione(
            campagna=campagna_aperta,
            capo=capo,
            gruppo=gruppo,
            tipologia=campo_estivo,
            data_inizio=datetime.date(2026, 7, 1),
            data_fine=datetime.date(2026, 7, 8),
            luogo="Base",
            quota_versata=Decimal("51.50"),
            stato=StatoPartecipazione.APPROVATA,
        )
        p2.full_clean(exclude=["stato"])
        p2.save()
        riga = riepilogo_gruppi(campagna_aperta)[0]
        assert riga.capi_inseriti == 1

    def test_contributo_none_prima_della_chiusura(self, campagna_aperta, cfm):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        _partecipazione(campagna_aperta, gruppo, cfm, "10001", importo=Decimal("50.00"))
        riga = riepilogo_gruppi(campagna_aperta)[0]
        assert riga.contributo_ricevuto is None

    def test_contributo_valorizzato_dopo_chiusura(self, campagna_chiusa, cfm):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        _partecipazione(campagna_chiusa, gruppo, cfm, "10001", importo=Decimal("50.00"))
        riga = riepilogo_gruppi(campagna_chiusa)[0]
        assert riga.contributo_ricevuto == Decimal("50.00")


class TestDichiaraNessunRimborso:
    def test_cg_puo_dichiarare_solo_sul_proprio_gruppo(self, campagna_aperta):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        altro_gruppo = Gruppo.objects.create(codice="E0199", nome="ALTRO GRUPPO")
        cg = _persona("cg@x.it")
        Ruolo.objects.create(utente=cg, tipo=Ruolo.Tipo.CG, gruppo=gruppo)

        dichiara_nessun_rimborso(utente=cg, campagna=campagna_aperta, gruppo=gruppo)
        assert DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()

        with pytest.raises(PermissionDenied):
            dichiara_nessun_rimborso(utente=cg, campagna=campagna_aperta, gruppo=altro_gruppo)

    def test_segreteria_puo_dichiarare_su_qualunque_gruppo(self, campagna_aperta):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        segreteria = _persona("segreteria@x.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)

        dichiara_nessun_rimborso(utente=segreteria, campagna=campagna_aperta, gruppo=gruppo)
        assert DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()

    def test_rifiuta_se_gia_ci_sono_partecipazioni(self, campagna_aperta, cfm):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        _partecipazione(campagna_aperta, gruppo, cfm, "10001")
        segreteria = _persona("segreteria@x.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)

        with pytest.raises(ValidationError):
            dichiara_nessun_rimborso(utente=segreteria, campagna=campagna_aperta, gruppo=gruppo)

    def test_rifiuta_fuori_da_campagna_aperta(self, campagna_chiusa):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        segreteria = _persona("segreteria@x.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)

        with pytest.raises(ValidationError):
            dichiara_nessun_rimborso(utente=segreteria, campagna=campagna_chiusa, gruppo=gruppo)

    def test_revoca(self, campagna_aperta):
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        segreteria = _persona("segreteria@x.it")
        Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        dichiara_nessun_rimborso(utente=segreteria, campagna=campagna_aperta, gruppo=gruppo)

        revoca_dichiarazione_nessun_rimborso(
            utente=segreteria, campagna=campagna_aperta, gruppo=gruppo
        )

        assert not DichiarazioneNessunRimborso.objects.filter(
            campagna=campagna_aperta, gruppo=gruppo
        ).exists()
