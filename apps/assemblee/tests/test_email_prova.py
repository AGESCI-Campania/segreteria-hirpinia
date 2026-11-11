"""Assemblee di prova «solo Mailpit»: codici e inviti contrassegnati, pagina
delle email lette da Mailpit con il codice degli inviti oscurato."""

import datetime
import io
import json
from unittest.mock import patch

import pytest
from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import comitato, elenco, prova, sedute
from apps.assemblee.models import Assemblea, Seduta, SistemaVoto, TipoAssemblea
from apps.core.email import mailpit_api
from apps.core.email.override import HEADER_SOLO_MAILPIT
from apps.organizzazione.models import Gruppo
from apps.voto import codici

pytestmark = pytest.mark.django_db


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


def _assemblea(segreteria, *, di_prova=True, solo_mailpit=True) -> Assemblea:
    gruppo, _ = Gruppo.objects.get_or_create(codice="E0133", defaults={"nome": "AVELLINO 1"})
    for i in range(2):
        capo, _ = Capo.objects.get_or_create(
            codice_socio=f"10{i}",
            defaults={"nome": "Nome", "cognome": f"C{i}", "email": f"c{i}@example.it"},
        )
        CensimentoCapo.objects.get_or_create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(
        tipo=TipoAssemblea.AUTUNNALE,
        anno_scout=2027,
        sistema_voto=SistemaVoto.CATELLO,
        di_prova=di_prova,
        email_solo_mailpit=solo_mailpit,
    )
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def test_codice_di_voto_contrassegnato(segreteria):
    assemblea = _assemblea(segreteria)
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    avente = assemblea.aventi_diritto.first()
    assert codici.invia(seduta, avente, segreteria) == codici.EsitoInvio.INVIATO
    messaggio = mail.outbox[-1]
    assert messaggio.extra_headers[HEADER_SOLO_MAILPIT] == "1"
    assert messaggio.extra_headers["X-Tags"] == f"catello-assemblea-{assemblea.pk}, codice-voto"


def test_invito_del_comitato_contrassegnato(segreteria):
    assemblea = _assemblea(segreteria)
    comitato.aggiungi(assemblea, assemblea.aventi_diritto.first(), segreteria)
    assert mail.outbox[-1].extra_headers["X-Tags"].endswith(", invito")


def test_assemblea_vera_non_contrassegna(segreteria):
    assemblea = _assemblea(segreteria, di_prova=False, solo_mailpit=False)
    comitato.aggiungi(assemblea, assemblea.aventi_diritto.first(), segreteria)
    assert HEADER_SOLO_MAILPIT not in mail.outbox[-1].extra_headers


def test_opzione_solo_per_le_prove(segreteria):
    vera = _assemblea(segreteria, di_prova=False, solo_mailpit=False)
    with pytest.raises(ValidationError):
        prova.imposta_email_solo_mailpit(vera, True, segreteria)
    di_prova = _assemblea(segreteria, solo_mailpit=False)
    prova.imposta_email_solo_mailpit(di_prova, True, segreteria)
    di_prova.refresh_from_db()
    assert di_prova.email_solo_mailpit


class _RispostaFinta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _mailpit_finto(messaggi: dict[str, dict]):
    """urlopen finto: ricerca per tag e dettaglio dei messaggi."""

    def urlopen(url, timeout):
        if "/api/v1/search" in url:
            voci = [
                {
                    "ID": id_,
                    "To": [{"Address": m["a"]}],
                    "Subject": m["oggetto"],
                    "Created": "2026-11-22T09:30:00Z",
                    "Tags": m["tag"],
                }
                for id_, m in messaggi.items()
            ]
            return _RispostaFinta(json.dumps({"messages": voci}).encode())
        id_ = url.rsplit("/", 1)[1]
        return _RispostaFinta(json.dumps({"Text": messaggi[id_]["testo"]}).encode())

    return urlopen


def test_pagina_email_con_codice_invito_oscurato(client, settings, segreteria):
    settings.EMAIL_MAILPIT_API_URL = "http://mailpit:8025"
    settings.EMAIL_MAILPIT_HOST = "mailpit"
    assemblea = _assemblea(segreteria)
    tag = prova.etichetta(assemblea)
    finto = _mailpit_finto(
        {
            "1": {
                "a": "c0@example.it",
                "oggetto": "Invito",
                "tag": [tag, "invito"],
                "testo": "Il tuo codice è K7QMR4XP, scade domani.",
            },
            "2": {
                "a": "c1@example.it",
                "oggetto": "Codice",
                "tag": [tag, "codice-voto"],
                "testo": "Codice K7QM-R4XP-2W",
            },
        }
    )
    with patch("apps.core.email.mailpit_api.urllib.request.urlopen", finto):
        messaggi = prova.email_su_mailpit(assemblea, segreteria)
        client.force_login(segreteria)
        pagina = client.get(f"/assemblee/{assemblea.pk}/email-prova/").content.decode()
    testi = {m.oggetto: m.testo for m in messaggi}
    assert "K7QMR4XP" not in testi["Invito"] and "••••••••" in testi["Invito"]
    assert testi["Codice"] == "Codice K7QM-R4XP-2W"
    assert "K7QMR4XP" not in pagina and "K7QM-R4XP-2W" in pagina


def test_mailpit_che_non_risponde(client, settings, segreteria):
    settings.EMAIL_MAILPIT_API_URL = "http://mailpit:8025"
    assemblea = _assemblea(segreteria)

    def rotto(url, timeout):
        raise OSError("rifiutata")

    with patch("apps.core.email.mailpit_api.urllib.request.urlopen", rotto):
        with pytest.raises(mailpit_api.MailpitNonRaggiungibile):
            prova.email_su_mailpit(assemblea, segreteria)
        client.force_login(segreteria)
        pagina = client.get(f"/assemblee/{assemblea.pk}/email-prova/").content.decode()
    assert "Mailpit non risponde" in pagina


def test_solo_gestori_e_solo_prove(client, segreteria):
    vera = _assemblea(segreteria, di_prova=False, solo_mailpit=False)
    with pytest.raises(ValidationError):
        prova.email_su_mailpit(vera, segreteria)
    capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        prova.email_su_mailpit(_assemblea(segreteria), capo)
    client.force_login(segreteria)
    assert client.get(f"/assemblee/{vera.pk}/email-prova/").status_code == 404


def test_interruttore_dalla_pagina(client, segreteria):
    assemblea = _assemblea(segreteria)
    client.force_login(segreteria)
    client.post(f"/assemblee/{assemblea.pk}/email-prova/", {"email_solo_mailpit": "0"})
    assemblea.refresh_from_db()
    assert not assemblea.email_solo_mailpit
