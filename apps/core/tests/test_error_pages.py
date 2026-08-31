"""Issue GitHub #3: pagine 403/404/500 personalizzate in tema, e
configurazione di ADMINS/mail_admins in produzione."""

import pytest
from django.test import Client, RequestFactory, override_settings
from django.views import defaults

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.organizzazione.models import Gruppo


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_pagina_404_personalizzata():
    response = Client(raise_request_exception=False).get("/percorso/che/non/esiste/")
    assert response.status_code == 404
    content = response.content.decode()
    assert "Pagina non trovata" in content


@pytest.mark.django_db
@override_settings(DEBUG=False)
def test_pagina_403_personalizzata():
    # CampagnaCreaView (apps/contributi/views.py) è riservata a
    # RUOLI_GESTIONE_CAMPAGNA: un CG riceve 403 dal RuoloRequiredMixin senza
    # bisogno di alcun oggetto in più.
    utente = Utente.objects.create(
        username="cg-senza-permesso",
        email="cg-senza-permesso@campania.agesci.it",
        tipo=TipoUtente.PERSONA,
        stato=StatoUtente.ATTIVO,
    )
    gruppo = Gruppo.objects.create(codice="E0199", nome="TEST")
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.CG, gruppo=gruppo)

    client = Client(raise_request_exception=False)
    client.force_login(utente)
    response = client.get("/contributi/campagne/nuova/")
    assert response.status_code == 403
    content = response.content.decode()
    assert "Accesso negato" in content


def test_pagina_500_personalizzata_senza_eccezioni_proprie():
    request = RequestFactory().get("/")
    response = defaults.server_error(request)
    assert response.status_code == 500
    content = response.content.decode()
    assert "errore imprevisto" in content
