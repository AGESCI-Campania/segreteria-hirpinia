"""Email di nomina con i manuali (nomina.py), dalle pagine del comitato
elettorale e della presidenza."""

import datetime
from unittest import mock

import pytest
from allauth.mfa.models import Authenticator
from django.core import mail
from django.template.loader import get_template

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import comitato, elenco, nomina
from apps.assemblee.models import Assemblea, RuoloAssemblea, Seduta, TipoAssemblea
from apps.core.models import CodiceTemplateEmail, TemplateEmail
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

STABLE = "https://segreteria-hirpinia.readthedocs.io/it/stable/assemblea"


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def assemblea(segreteria) -> Assemblea:
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i in range(4):
        capo = Capo.objects.create(
            codice_socio=f"10{i}",
            nome=f"Nome{i}",
            cognome=f"Capo{i}",
            email=f"capo{i}@example.it" if i < 3 else "",
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _avente(assemblea, codice):
    return assemblea.aventi_diritto.get(codice_socio=codice)


def _nomine(indirizzo: str) -> list:
    return [m for m in mail.outbox if m.to == [indirizzo] and "nomina" in m.subject]


class TestTesto:
    def test_manuali_per_incarico(self):
        banco = f"{STABLE}/banco/pdf/manuale-banco.pdf"
        gestione = f"{STABLE}/gestione/"
        voto_app = f"{STABLE}/voto-app/pdf/manuale-voto-app.pdf"
        comitato_testo = nomina.testo_manuali(nomina.COMITATO_ELETTORALE)
        assert banco in comitato_testo and gestione in comitato_testo
        presidente = nomina.testo_manuali(RuoloAssemblea.PRESIDENTE)
        assert gestione in presidente and banco not in presidente
        # I manuali di voto, da girare ai votanti, a tutti.
        assert voto_app in comitato_testo and voto_app in presidente

    def test_template_seminato_uguale_al_fallback(self):
        template = TemplateEmail.objects.get(codice=CodiceTemplateEmail.NOMINA_ASSEMBLEA)
        sorgente = get_template("assemblee/email/nomina.txt").template.source
        assert template.corpo_testo == sorgente and template.corpo_html == ""


class TestDallePagine:
    def test_comitato_elettorale(self, client, assemblea, segreteria):
        client.force_login(segreteria)
        client.post(
            f"/assemblee/{assemblea.pk}/comitato/aggiungi/",
            {"avente": _avente(assemblea, "100").pk, "accesso": "on"},
        )
        (email,) = _nomine("capo0@example.it")
        assert "Ciao Nome0" in email.body
        assert "componente del comitato elettorale" in email.body
        assert "22/11/2026" in email.body
        assert f"{STABLE}/banco/" in email.body
        # L'invito di attivazione resta un'email a parte.
        assert len([m for m in mail.outbox if m.to == ["capo0@example.it"]]) == 2

    def test_anche_senza_accesso_e_con_account_gia_attivo(self, client, assemblea, segreteria):
        esistente = Utente.objects.create(
            username="x", email="capo1@example.it", codice_socio="101", stato=StatoUtente.ATTIVO
        )
        esistente.set_password("una-password-qualsiasi")
        esistente.save()
        client.force_login(segreteria)
        client.post(
            f"/assemblee/{assemblea.pk}/comitato/aggiungi/",
            {"avente": _avente(assemblea, "101").pk, "accesso": "on"},
        )
        client.post(
            f"/assemblee/{assemblea.pk}/comitato/aggiungi/",
            {"avente": _avente(assemblea, "102").pk},
        )
        assert len(_nomine("capo1@example.it")) == 1
        assert len(_nomine("capo2@example.it")) == 1

    def test_presidenza_e_scrutatori_non_comitato_mozioni(self, client, assemblea, segreteria):
        comitato.aggiungi(assemblea, _avente(assemblea, "102"), segreteria, accesso=False)
        mail.outbox.clear()
        client.force_login(segreteria)
        base = f"/assemblee/{assemblea.pk}/incarichi/aggiungi/"
        client.post(
            base, {"ruolo": RuoloAssemblea.PRESIDENTE, "avente": _avente(assemblea, "100").pk}
        )
        client.post(base, {"ruolo": RuoloAssemblea.MOZIONI, "avente": _avente(assemblea, "101").pk})
        client.post(
            base, {"ruolo": RuoloAssemblea.SCRUTATORE, "avente": _avente(assemblea, "102").pk}
        )
        (presidente,) = _nomine("capo0@example.it")
        assert "l'incarico di presidente" in presidente.body
        assert f"{STABLE}/banco/" not in presidente.body
        assert _nomine("capo1@example.it") == []
        (scrutatore,) = _nomine("capo2@example.it")
        assert "l'incarico di scrutatore" in scrutatore.body

    def test_senza_email_nessun_invio(self, client, assemblea, segreteria):
        client.force_login(segreteria)
        risposta = client.post(
            f"/assemblee/{assemblea.pk}/comitato/aggiungi/",
            {"avente": _avente(assemblea, "103").pk},
            follow=True,
        )
        assert mail.outbox == []
        assert "non è partita" not in risposta.content.decode()

    def test_invio_fallito_la_nomina_resta(self, client, assemblea, segreteria):
        client.force_login(segreteria)
        with mock.patch.object(nomina, "invia_email_template", side_effect=OSError):
            risposta = client.post(
                f"/assemblee/{assemblea.pk}/comitato/aggiungi/",
                {"avente": _avente(assemblea, "102").pk},
                follow=True,
            )
        assert assemblea.operatori.filter(avente__codice_socio="102").exists()
        assert "L&#x27;email di nomina con i manuali" in risposta.content.decode()


def test_assemblea_di_prova_solo_mailpit(assemblea):
    assemblea.di_prova = True
    assemblea.email_solo_mailpit = True
    assemblea.save()
    with mock.patch.object(nomina, "invia_email_template") as invio:
        nomina.invia(assemblea, _avente(assemblea, "100"), RuoloAssemblea.SEGRETARIO)
    assert invio.call_args.kwargs["solo_mailpit"] is True
