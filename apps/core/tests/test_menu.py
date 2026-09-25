"""Sidebar (apps/core/menu.py): la voce "Allowlist gruppi" vive sotto
"Amministrazione", non più sotto "Anagrafica" (piano-sviluppo-todo.md M2).
"Assegna incarico" non è più una voce di primo livello: si raggiunge dalla
subview incarichi di "Gestione gruppo" (piano-sviluppo-todo.md M6)."""

import datetime

import pytest

from apps.accounts.models import Delega, Ruolo, StatoUtente, TipoUtente, Utente
from apps.core.menu import sezioni_menu

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _etichette(sezioni, nome_sezione: str) -> list[str]:
    for sezione in sezioni:
        if sezione.etichetta == nome_sezione:
            return [voce.etichetta for voce in sezione.voci]
    return []


def _sottoetichette(sezioni, nome_sezione: str, nome_voce: str) -> list[str]:
    for sezione in sezioni:
        if sezione.etichetta != nome_sezione:
            continue
        for voce in sezione.voci:
            if voce.etichetta == nome_voce:
                return [sotto.etichetta for sotto in voce.sottovoci]
    return []


class TestAllowlistSottoAmministrazione:
    def test_segreteria_diretta_vede_allowlist_in_amministrazione(self):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)

        sezioni = sezioni_menu(utente)

        assert "Allowlist gruppi" not in _etichette(sezioni, "Anagrafica")
        assert "Allowlist gruppi" in _etichette(sezioni, "Amministrazione")

    def test_delegato_di_segreteria_vede_comunque_allowlist(self):
        # RUOLI_GESTIONE_GRUPPI ammette le deleghe (a differenza di
        # RUOLI_GESTIONE_IMPOSTAZIONI, solo_diretti=True): lo spostamento sotto
        # Amministrazione non deve restringere questo permesso.
        segreteria = _persona("segreteria@campania.agesci.it")
        ruolo = Ruolo.objects.create(utente=segreteria, tipo=Ruolo.Tipo.SEGRETERIA)
        delegato = _persona("delegato@campania.agesci.it")
        Delega.objects.create(
            delegante=segreteria,
            delegato=delegato,
            ruolo=ruolo,
            data_fine=datetime.date.today() + datetime.timedelta(days=30),
        )

        sezioni = sezioni_menu(delegato)

        assert "Allowlist gruppi" in _etichette(sezioni, "Amministrazione")
        assert "Impostazioni" not in _etichette(sezioni, "Amministrazione")

    def test_cg_non_vede_allowlist_ne_amministrazione(self):
        from apps.organizzazione.models import Gruppo

        utente = _persona("cg@campania.agesci.it")
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)

        sezioni = sezioni_menu(utente)

        assert not any(s.etichetta == "Amministrazione" for s in sezioni)


class TestIlMioGruppo:
    def test_cg_senza_gestione_gruppi_vede_il_mio_gruppo(self):
        from apps.organizzazione.models import Gruppo

        utente = _persona("cg@campania.agesci.it")
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)

        sezioni = sezioni_menu(utente)

        etichette = _etichette(sezioni, "Anagrafica")
        assert "Il mio gruppo" in etichette
        assert "Gruppi" not in etichette

    def test_segreteria_non_vede_il_mio_gruppo(self):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)

        sezioni = sezioni_menu(utente)

        etichette = _etichette(sezioni, "Anagrafica")
        assert "Il mio gruppo" not in etichette
        assert "Gruppi" in etichette

    def test_cg_senza_gruppo_reale_non_vede_la_voce(self):
        # Caso limite difensivo: nessun ruolo CG con gruppo valorizzato.
        utente = _persona("senza-cg@campania.agesci.it")

        sezioni = sezioni_menu(utente)

        assert "Il mio gruppo" not in _etichette(sezioni, "Anagrafica")

    def test_cg_su_due_gruppi_mostra_una_voce_per_gruppo(self):
        # Caso raro (D-35 lo rende praticamente impossibile in pratica, dato
        # che il CG derivato su E9001 implica sempre RDZ, gia' coperto da
        # RUOLI_GESTIONE_GRUPPI), ma il ramo va comunque verificato: due ruoli
        # CG manuali su gruppi diversi non sono impediti dal modello dati.
        from apps.organizzazione.models import Gruppo

        utente = _persona("cg-doppio@campania.agesci.it")
        gruppo1 = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        gruppo2 = Gruppo.objects.create(codice="E0134", nome="AVELLINO 2")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo1)
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo2)

        sezioni = sezioni_menu(utente)

        etichette = _etichette(sezioni, "Anagrafica")
        assert "Il mio gruppo — AVELLINO 1" in etichette
        assert "Il mio gruppo — AVELLINO 2" in etichette


class TestNoteSpeseInMenu:
    """D-65: la voce compare per un capo qualsiasi, non solo per chi ha un
    ruolo di gestione — a differenza di tutte le altre voci di questa
    sezione, non passa da `consentito()`. "Nota Spese" è un'unica voce di
    primo livello in "Moduli" (non una per funzione): le singole funzioni
    sono sottovoci, stesso pattern da riusare per ogni futuro modulo."""

    def test_capo_qualsiasi_vede_solo_la_voce_nota_spese(self):
        utente = _persona("mario.rossi@example.it", codice_socio="123456A")

        sezioni = sezioni_menu(utente)

        assert _etichette(sezioni, "Moduli").count("Nota Spese") == 1
        assert "Note spese" not in _etichette(sezioni, "Moduli")
        assert "Note spese" in _sottoetichette(sezioni, "Moduli", "Nota Spese")

    def test_account_di_gruppo_senza_ruoli_non_vede_la_voce(self):
        utente = _persona("account.gruppo@example.it")

        sezioni = sezioni_menu(utente)

        assert "Nota Spese" not in _etichette(sezioni, "Moduli")

    def test_segreteria_vede_la_voce_anche_senza_codice_socio(self):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)

        sezioni = sezioni_menu(utente)

        assert "Nota Spese" in _etichette(sezioni, "Moduli")

    def test_capo_semplice_non_vede_le_funzioni_di_gestione(self):
        utente = _persona("mario.rossi@example.it", codice_socio="123456A")

        sezioni = sezioni_menu(utente)

        sottovoci = _sottoetichette(sezioni, "Moduli", "Nota Spese")
        assert "Verifica note spese" not in sottovoci
        assert "Eventi" not in sottovoci
        assert "Esporta note spese" not in sottovoci

    def test_segreteria_vede_tutte_le_funzioni_come_sottovoci(self):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)

        sezioni = sezioni_menu(utente)

        sottovoci = _sottoetichette(sezioni, "Moduli", "Nota Spese")
        assert sottovoci == [
            "Panoramica",
            "Note spese",
            "Verifica note spese",
            "Eventi",
            "Esporta note spese",
        ]


class TestAssegnaIncaricoNonPiuInMenu:
    def test_cg_non_vede_piu_assegna_incarico(self):
        from apps.organizzazione.models import Gruppo

        utente = _persona("cg@campania.agesci.it")
        gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)

        sezioni = sezioni_menu(utente)

        assert "Assegna incarico" not in _etichette(sezioni, "Anagrafica")

    def test_segreteria_non_vede_piu_assegna_incarico(self):
        utente = _persona("segreteria@campania.agesci.it")
        Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)

        sezioni = sezioni_menu(utente)

        assert "Assegna incarico" not in _etichette(sezioni, "Anagrafica")
