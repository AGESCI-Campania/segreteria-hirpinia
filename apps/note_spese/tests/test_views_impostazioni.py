"""F7/D-64: vista Impostazioni Nota spese (autorizzazione RdZ + report ai
gestori)."""

import pytest
from allauth.mfa.models import Authenticator

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.note_spese.models import AutorizzazioneRdzConfig, ImpostazioniNoteSpese

pytestmark = pytest.mark.django_db


def _persona(email: str, codice_socio: str | None = None) -> Utente:
    n = Utente.objects.count()
    return Utente.objects.create(
        username=f"u{n}",
        email=email,
        tipo=TipoUtente.PERSONA,
        codice_socio=codice_socio,
        stato=StatoUtente.ATTIVO,
    )


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


@pytest.fixture
def rdz() -> Utente:
    utente = _persona("rdz@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.RDZ)
    return _con_mfa_configurata(utente)


@pytest.fixture
def segreteria() -> Utente:
    utente = _persona("segreteria@campania.agesci.it")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    return _con_mfa_configurata(utente)


class TestImpostazioniNoteSpeseView:
    def test_segreteria_non_accede(self, client, segreteria) -> None:
        """D-35: solo admin e RdZ, non segreteria (perimetro più stretto di
        puo_gestire_note())."""
        client.force_login(segreteria)
        response = client.get("/note-spese/impostazioni/")
        assert response.status_code == 403

    def test_rdz_accede(self, client, rdz) -> None:
        client.force_login(rdz)
        response = client.get("/note-spese/impostazioni/")
        assert response.status_code == 200

    def test_salva_giorni_orario_e_destinatari(self, client, rdz) -> None:
        client.force_login(rdz)
        response = client.post(
            "/note-spese/impostazioni/",
            {
                "autorizzazione_rdz": AutorizzazioneRdzConfig.SINGOLA,
                "report_giorni_settimana": ["0", "3"],
                "report_orario": "09:00",
                "report_destinatari_segreteria": "on",
                "report_destinatari_rdz": "on",
            },
        )
        assert response.status_code == 302

        impostazioni = ImpostazioniNoteSpese.corrente()
        assert impostazioni.autorizzazione_rdz == AutorizzazioneRdzConfig.SINGOLA
        assert sorted(impostazioni.report_giorni_settimana) == [0, 3]
        assert impostazioni.report_orario is not None
        assert impostazioni.report_orario.strftime("%H:%M") == "09:00"
        assert impostazioni.report_destinatari_segreteria is True
        assert impostazioni.report_destinatari_rdz is True
        assert impostazioni.report_destinatari_admin is False

    def test_giorni_senza_orario_respinto(self, client, rdz) -> None:
        client.force_login(rdz)
        response = client.post(
            "/note-spese/impostazioni/",
            {
                "autorizzazione_rdz": AutorizzazioneRdzConfig.NESSUNA,
                "report_giorni_settimana": ["0"],
                "report_orario": "",
            },
        )
        assert response.status_code == 200
        assert "report_orario" in response.context["form"].errors
        impostazioni = ImpostazioniNoteSpese.corrente()
        assert impostazioni.report_giorni_settimana == []

    def test_nessun_giorno_selezionato_disattiva_il_report(self, client, rdz) -> None:
        ImpostazioniNoteSpese.objects.update_or_create(
            pk=1, defaults={"report_giorni_settimana": [0], "report_orario": "09:00"}
        )
        client.force_login(rdz)
        response = client.post(
            "/note-spese/impostazioni/",
            {
                "autorizzazione_rdz": AutorizzazioneRdzConfig.NESSUNA,
                "report_giorni_settimana": [],
                "report_orario": "",
            },
        )
        assert response.status_code == 302
        impostazioni = ImpostazioniNoteSpese.corrente()
        assert impostazioni.report_giorni_settimana == []
