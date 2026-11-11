"""Codici di voto e sistema di voto (apps/voto/codici.py, apps/voto/sistema.py)."""

import re
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError

from apps.assemblee import elenco, sedute
from apps.assemblee.models import ModalitaVoto, SistemaVoto, TipoVotazione, Votazione
from apps.voto import codici, sistema
from apps.voto.models import CodiceVoto

from .conftest import avente, persona

pytestmark = pytest.mark.django_db


class TestFormato:
    def test_dieci_caratteri_senza_ambigui(self):
        for _ in range(200):
            codice = codici.genera()
            assert len(codice) == 10
            assert set(codice) <= set(codici.ALFABETO)
            assert not set(codice) & set("0O1IL")

    def test_normalizza_e_formatta(self):
        assert codici.normalizza(" k7qm-r4xp 2w ") == "K7QMR4XP2W"
        assert codici.formatta("K7QMR4XP2W") == "K7QM-R4XP-2W"

    def test_hash_indipendente_dalla_formattazione(self):
        assert codici.calcola_hash("K7QM-R4XP-2W") == codici.calcola_hash("k7qmr4xp2w")


class TestEmissione:
    def test_si_salva_solo_l_hash(self, seduta, assemblea, segreteria):
        codice = codici.emetti(seduta, avente(assemblea, "Rossi"), segreteria)
        registrato = CodiceVoto.objects.get()
        assert registrato.hash == codici.calcola_hash(codice)
        valori = [str(getattr(registrato, f.attname)) for f in CodiceVoto._meta.fields]
        assert not any(codice in valore for valore in valori)

    def test_rigenerare_revoca_il_precedente(self, seduta, assemblea, operatore):
        rossi = avente(assemblea, "Rossi")
        primo = codici.emetti(seduta, rossi, operatore)
        secondo = codici.emetti(seduta, rossi, operatore)
        attivo = codici.codice_attivo(seduta, rossi)
        assert attivo.hash == codici.calcola_hash(secondo) != codici.calcola_hash(primo)
        assert CodiceVoto.objects.filter(revocato_il__isnull=False).count() == 1

    def test_solo_con_il_voto_di_catello(self, seduta, assemblea, segreteria):
        assemblea.sistema_voto = SistemaVoto.NAZIONALE
        assemblea.save()
        with pytest.raises(ValidationError):
            codici.emetti(seduta, avente(assemblea, "Rossi"), segreteria)

    def test_solo_a_seduta_aperta(self, seduta, assemblea, segreteria):
        seduta.chiusa_il = seduta.aperta_il
        seduta.save()
        with pytest.raises(ValidationError):
            codici.emetti(seduta, avente(assemblea, "Rossi"), segreteria)

    def test_non_a_chi_vota_su_carta(self, seduta, assemblea, segreteria):
        rossi = avente(assemblea, "Rossi")
        elenco.passa_a_carta(rossi, segreteria)
        with pytest.raises(ValidationError):
            codici.emetti(seduta, rossi, segreteria)

    def test_solo_gestori_e_operatori(self, seduta, assemblea):
        with pytest.raises(PermissionDenied):
            codici.emetti(seduta, avente(assemblea, "Rossi"), persona("x@example.it"))

    def test_passare_a_carta_revoca_il_codice(self, seduta, assemblea, segreteria):
        rossi = avente(assemblea, "Rossi")
        codici.emetti(seduta, rossi, segreteria)
        elenco.passa_a_carta(rossi, segreteria)
        assert codici.codice_attivo(seduta, rossi) is None


class TestInvio:
    def test_invio_per_email_con_codice_e_link(self, seduta, assemblea, operatore):
        esito = codici.invia(seduta, avente(assemblea, "Rossi"), operatore)
        assert esito == codici.EsitoInvio.INVIATO
        assert mail.outbox[0].to == ["mario@example.it"]
        corpo = mail.outbox[0].body
        assert "/voto/#c=" in corpo
        registrato = CodiceVoto.objects.get()
        assert registrato.inviato_per_email

    def test_senza_email_nessun_codice(self, seduta, assemblea, operatore):
        esito = codici.invia(seduta, avente(assemblea, "Bianchi"), operatore)
        assert esito == codici.EsitoInvio.SENZA_EMAIL
        assert not CodiceVoto.objects.exists()
        assert mail.outbox == []

    def test_invio_fallito_revoca_il_codice(self, seduta, assemblea, operatore):
        with patch("apps.voto.codici.invia_email_template", side_effect=OSError("smtp giù")):
            esito = codici.invia(seduta, avente(assemblea, "Rossi"), operatore)
        assert esito == codici.EsitoInvio.INVIO_FALLITO
        assert codici.codice_attivo(seduta, avente(assemblea, "Rossi")) is None

    def test_dopo_la_presenza_una_volta_sola(self, seduta, assemblea, operatore):
        rossi = avente(assemblea, "Rossi")
        sedute.registra_presenza(seduta, rossi, operatore)
        assert codici.dopo_la_presenza(seduta, rossi, operatore) == codici.EsitoInvio.INVIATO
        assert codici.dopo_la_presenza(seduta, rossi, operatore) == codici.EsitoInvio.GIA_ATTIVO
        assert len(mail.outbox) == 1

    def test_dopo_la_presenza_con_l_app_nazionale(self, seduta, assemblea, segreteria):
        sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, segreteria)
        seduta.refresh_from_db()
        rossi = avente(assemblea, "Rossi")
        esito = codici.dopo_la_presenza(seduta, rossi, segreteria)
        assert esito == codici.EsitoInvio.NON_PREVISTO


class TestSistema:
    def test_inserito_a_mano_vota_in_app_solo_con_catello(self, assemblea, segreteria):
        gialli = avente(assemblea, "Gialli")
        assert gialli.vota_in_app
        sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, segreteria)
        gialli.refresh_from_db()
        assert not gialli.vota_in_app
        assert avente(assemblea, "Rossi").vota_in_app

    def test_tornare_al_nazionale_revoca_i_codici(self, seduta, assemblea, segreteria):
        codici.emetti(seduta, avente(assemblea, "Rossi"), segreteria)
        sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, segreteria)
        assert not CodiceVoto.objects.filter(revocato_il__isnull=True).exists()

    def test_bloccato_dopo_la_prima_votazione(self, seduta, assemblea, segreteria):
        Votazione.objects.create(
            seduta=seduta, tipo=TipoVotazione.MOZIONE, oggetto="x", presenti=1, aventi_diritto=5
        )
        with pytest.raises(ValidationError):
            sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, segreteria)

    def test_modalita_solo_con_catello(self, assemblea, segreteria):
        sistema.imposta_modalita(assemblea, "SOLO_SEGGIO", segreteria)
        assemblea.refresh_from_db()
        assert assemblea.modalita_voto == "SOLO_SEGGIO"
        sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, segreteria)
        with pytest.raises(ValidationError):
            sistema.imposta_modalita(assemblea, "PERSONALE_E_SEGGIO", segreteria)

    def test_solo_i_gestori(self, assemblea, operatore):
        with pytest.raises(PermissionDenied):
            sistema.imposta_sistema(assemblea, SistemaVoto.NAZIONALE, operatore)


class TestViste:
    def test_presenza_invia_il_codice(self, client, seduta, assemblea, operatore):
        client.force_login(operatore)
        rossi = avente(assemblea, "Rossi")
        client.post(f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/presenze/{rossi.pk}/")
        assert len(mail.outbox) == 1
        risposta = client.get(f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/presenze/")
        assert "codice inviato per email" in risposta.content.decode()

    def test_email_inserita_al_banco(self, client, seduta, assemblea, operatore):
        client.force_login(operatore)
        bianchi = avente(assemblea, "Bianchi")
        url = f"/voto/gestione/{assemblea.pk}/sedute/{seduta.pk}/codici/{bianchi.pk}/invia/"
        client.post(url, {"email": "anna@example.it"})
        bianchi.refresh_from_db()
        assert bianchi.email == "anna@example.it"
        assert mail.outbox[0].to == ["anna@example.it"]

    def test_rigenera_e_mostra(self, client, seduta, assemblea, operatore):
        client.force_login(operatore)
        gialli = avente(assemblea, "Gialli")
        url = f"/voto/gestione/{assemblea.pk}/sedute/{seduta.pk}/codici/{gialli.pk}/mostra/"
        risposta = client.post(url)
        assert risposta.status_code == 200
        assert "no-store" in risposta["Cache-Control"]
        testo = risposta.content.decode()
        assert 'src="data:image/svg+xml' in testo
        registrato = CodiceVoto.objects.get(avente=gialli)
        mostrati = re.findall(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{2}", testo)
        assert any(codici.calcola_hash(c) == registrato.hash for c in mostrati)
        # Ricaricare in GET non rigenera.
        assert client.get(url).status_code == 302
        assert CodiceVoto.objects.filter(avente=gialli).count() == 1

    def test_mostra_rifiutato_a_chi_non_opera(self, client, seduta, assemblea):
        client.force_login(persona("x@example.it"))
        gialli = avente(assemblea, "Gialli")
        url = f"/voto/gestione/{assemblea.pk}/sedute/{seduta.pk}/codici/{gialli.pk}/mostra/"
        assert client.post(url).status_code == 404
        assert not CodiceVoto.objects.exists()

    def test_creazione_con_il_voto_di_catello(self, client, segreteria, avellino):
        client.force_login(segreteria)
        client.post(
            "/assemblee/nuova/",
            {
                "tipo": "PRIMAVERILE",
                "anno_scout": 2027,
                "sessione": "ORDINARIA",
                "sistema_voto": "CATELLO",
                "modalita_voto": "PERSONALE_E_SEGGIO",
                "data_convocazione": "2027-04-10",
            },
        )
        from apps.assemblee.models import Assemblea

        assert Assemblea.objects.latest("creata_il").voto_catello

    def test_pagina_pubblica_senza_login(self, client):
        assert client.get("/voto/").status_code == 200


def test_mostra_non_rimanda_fuori_dal_sito(client, seduta, assemblea, operatore):
    client.force_login(operatore)
    gialli = avente(assemblea, "Gialli")
    url = f"/voto/gestione/{assemblea.pk}/sedute/{seduta.pk}/codici/{gialli.pk}/mostra/"
    testo = client.post(url, {"next": "javascript:alert(1)"}).content.decode()
    assert "javascript:" not in testo


class TestEmailSecondoLaModalita:
    def test_con_dispositivi_personali_c_e_il_link(self, seduta, assemblea, segreteria):
        rossi = avente(assemblea, "Rossi")
        assert codici.invia(seduta, rossi, segreteria) == codici.EsitoInvio.INVIATO
        corpo = mail.outbox[-1].body
        assert "/voto/#c=" in corpo and "seggio in sala" in corpo

    def test_solo_seggi_senza_link(self, seduta, assemblea, segreteria):
        assemblea.modalita_voto = ModalitaVoto.SOLO_SEGGIO
        assemblea.save()
        rossi = avente(assemblea, "Rossi")
        assert codici.invia(seduta, rossi, segreteria) == codici.EsitoInvio.INVIATO
        corpo = mail.outbox[-1].body
        assert "/voto/" not in corpo and "#c=" not in corpo
        assert "si vota solo ai seggi in sala" in corpo
        # Il codice c'è comunque.
        assert re.search(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{2}", corpo)
