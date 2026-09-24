import datetime

import pytest

from apps.accounts.models import Delega, Ruolo, TipoUtente, Utente
from apps.accounts.permessi import gruppi_visibili, ruoli_effettivi, utenti_con_ruoli
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

OGGI = datetime.date.today()
IERI = OGGI - datetime.timedelta(days=1)
DOMANI = OGGI + datetime.timedelta(days=1)


@pytest.fixture
def gruppo_a():
    return Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")


@pytest.fixture
def gruppo_b():
    return Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")


def _persona(email="p@campania.agesci.it", **kwargs):
    n = Utente.objects.count()
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


class TestRuoliEffettivi:
    def test_ruolo_diretto_attivo_e_incluso(self, gruppo_a):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
        effettivi = ruoli_effettivi(u)
        assert len(effettivi) == 1
        assert effettivi[0].tipo == Ruolo.Tipo.CG
        assert effettivi[0].is_delega is False

    def test_ruolo_scaduto_e_escluso(self, gruppo_a):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a, data_fine=IERI)
        assert ruoli_effettivi(u) == []

    def test_ruolo_non_attivo_e_escluso(self, gruppo_a):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a, attivo=False)
        assert ruoli_effettivi(u) == []

    def test_delega_attiva_e_inclusa(self, gruppo_a):
        delegante = _persona(email="d1@campania.agesci.it")
        delegato = _persona(email="d2@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=delegante, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
        Delega.objects.create(delegante=delegante, delegato=delegato, ruolo=ruolo, data_fine=DOMANI)

        effettivi = ruoli_effettivi(delegato)
        assert len(effettivi) == 1
        assert effettivi[0].is_delega is True
        assert effettivi[0].tipo == Ruolo.Tipo.CG

    def test_cascata_lazy_ruolo_di_origine_scaduto(self, gruppo_a):
        """Il ruolo di origine scade per data (senza revoca esplicita): la
        delega derivata smette di contare da sola (D-26)."""
        delegante = _persona(email="d1@campania.agesci.it")
        delegato = _persona(email="d2@campania.agesci.it")
        ruolo = Ruolo.objects.create(
            utente=delegante, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a, data_fine=IERI
        )
        # La delega stessa non è scaduta: solo il ruolo di origine lo è.
        Delega(delegante=delegante, delegato=delegato, ruolo=ruolo, data_fine=DOMANI).save()

        assert ruoli_effettivi(delegato) == []

    def test_piu_ruoli_su_perimetri_diversi_si_uniscono(self, gruppo_a, gruppo_b):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.MCZ)
        tipi = {r.tipo for r in ruoli_effettivi(u)}
        assert tipi == {Ruolo.Tipo.CG, Ruolo.Tipo.MCZ}


class TestGruppiVisibili:
    def test_cg_vede_solo_il_proprio_gruppo(self, gruppo_a, gruppo_b):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
        visibili = set(gruppi_visibili(u, 2026).values_list("codice", flat=True))
        assert visibili == {gruppo_a.codice}

    def test_cg_non_vede_gruppo_disattivato(self, gruppo_a):
        from apps.organizzazione.models import StatoGruppoAnno

        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo_a)
        StatoGruppoAnno.objects.create(gruppo=gruppo_a, anno_scout=2026, attivo=False)
        assert gruppi_visibili(u, 2026).count() == 0

    def test_ruolo_di_zona_vede_tutti_i_gruppi_attivi(self, gruppo_a, gruppo_b):
        u = _persona()
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
        visibili = set(gruppi_visibili(u, 2026).values_list("codice", flat=True))
        assert gruppo_a.codice in visibili
        assert gruppo_b.codice in visibili

    def test_mai_da_utente_gruppo(self, gruppo_a):
        """Un utente con `gruppo` valorizzato ma senza alcun Ruolo non vede
        nulla: il perimetro non deve mai derivare da Utente.gruppo (D-28)."""
        u = Utente.objects.create(
            username="funz",
            email="funz@campania.agesci.it",
            tipo=TipoUtente.GRUPPO,
            gruppo=gruppo_a,
        )
        assert gruppi_visibili(u, 2026).count() == 0

    def test_utente_senza_ruoli_non_vede_nulla(self, gruppo_a):
        u = _persona()
        assert gruppi_visibili(u, 2026).count() == 0


class TestUtentiConRuoli:
    def test_ruolo_diretto_incluso(self):
        u = _persona(email="segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
        assert set(utenti_con_ruoli([Ruolo.Tipo.SEGRETERIA])) == {u}

    def test_ruolo_per_delega_incluso(self):
        delegante = _persona(email="d1@campania.agesci.it")
        delegato = _persona(email="d2@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=delegante, tipo=Ruolo.Tipo.RDZ)
        Delega.objects.create(delegante=delegante, delegato=delegato, ruolo=ruolo, data_fine=DOMANI)

        risultato = set(utenti_con_ruoli([Ruolo.Tipo.RDZ]))

        assert delegante in risultato
        assert delegato in risultato

    def test_ruolo_scaduto_escluso(self):
        u = _persona(email="scaduto@campania.agesci.it")
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.ADMIN, data_fine=IERI)
        assert set(utenti_con_ruoli([Ruolo.Tipo.ADMIN])) == set()

    def test_delega_scaduta_esclusa(self):
        delegante = _persona(email="d3@campania.agesci.it")
        delegato = _persona(email="d4@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=delegante, tipo=Ruolo.Tipo.RDZ)
        Delega.objects.create(delegante=delegante, delegato=delegato, ruolo=ruolo, data_fine=IERI)

        risultato = set(utenti_con_ruoli([Ruolo.Tipo.RDZ]))

        assert delegato not in risultato
        assert delegante in risultato

    def test_tipo_non_richiesto_escluso(self):
        u = _persona(email="cg@campania.agesci.it")
        gruppo = Gruppo.objects.create(codice="E0199", nome="TEST")
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.CG, gruppo=gruppo)
        assert set(utenti_con_ruoli([Ruolo.Tipo.SEGRETERIA])) == set()

    def test_nessun_duplicato_con_piu_ruoli(self):
        u = _persona(email="doppio@campania.agesci.it")
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.SEGRETERIA)
        Ruolo.objects.create(utente=u, tipo=Ruolo.Tipo.RDZ)
        risultato = list(utenti_con_ruoli([Ruolo.Tipo.SEGRETERIA, Ruolo.Tipo.RDZ]))
        assert risultato == [u]
