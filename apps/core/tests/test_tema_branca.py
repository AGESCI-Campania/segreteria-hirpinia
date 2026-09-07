"""Schema colori piattaforma (issue #7): precedenza preferenza personale >
default di sistema > default del tema (apps.core.context_processors.tema_branca)."""

import pytest
from allauth.mfa.models import Authenticator
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.models import StatoUtente, TipoUtente, Utente
from apps.core.context_processors import tema_branca
from apps.core.models import ImpostazioniPiattaforma

pytestmark = pytest.mark.django_db


def _persona(email: str, **kwargs) -> Utente:
    n = Utente.objects.count()
    kwargs.setdefault("stato", StatoUtente.ATTIVO)
    return Utente.objects.create(username=f"u{n}", email=email, tipo=TipoUtente.PERSONA, **kwargs)


def _con_mfa_configurata(utente: Utente) -> Utente:
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={"secret": "x"})
    return utente


def _request(utente):
    request = RequestFactory().get("/")
    request.user = utente
    return request


def test_anonimo_nessuna_sovrascrittura():
    assert tema_branca(_request(AnonymousUser())) == {}


def test_autenticato_senza_preferenze_nessuna_sovrascrittura():
    utente = _con_mfa_configurata(_persona("a@campania.agesci.it"))
    assert tema_branca(_request(utente)) == {}


def test_default_di_sistema_applicato_senza_preferenza_personale():
    utente = _con_mfa_configurata(_persona("b@campania.agesci.it"))
    impostazioni = ImpostazioniPiattaforma.corrente()
    impostazioni.branca_tema_default = "lc"
    impostazioni.save()

    assert tema_branca(_request(utente)) == {"agesci_theme_branca": "lc"}


def test_preferenza_personale_vince_sul_default_di_sistema():
    utente = _con_mfa_configurata(_persona("c@campania.agesci.it"))
    utente.branca_tema_preferita = "eg"
    utente.save()
    impostazioni = ImpostazioniPiattaforma.corrente()
    impostazioni.branca_tema_default = "lc"
    impostazioni.save()

    assert tema_branca(_request(utente)) == {"agesci_theme_branca": "eg"}


def test_cambio_default_di_sistema_non_sovrascrive_preferenza_gia_impostata():
    # Caso esplicito della richiesta: un privilegiato cambia il default di
    # sistema DOPO che un altro utente ha già impostato una preferenza
    # personale — quest'ultima non deve cambiare.
    utente_a = _con_mfa_configurata(_persona("d@campania.agesci.it"))
    utente_a.branca_tema_preferita = "rs"
    utente_a.save()

    impostazioni = ImpostazioniPiattaforma.corrente()
    impostazioni.branca_tema_default = "generico"
    impostazioni.save()

    assert tema_branca(_request(utente_a)) == {"agesci_theme_branca": "rs"}
