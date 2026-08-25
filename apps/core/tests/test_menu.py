"""Sidebar (apps/core/menu.py): la voce "Allowlist gruppi" vive sotto
"Amministrazione", non più sotto "Anagrafica" (piano-sviluppo-todo.md M2)."""

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
