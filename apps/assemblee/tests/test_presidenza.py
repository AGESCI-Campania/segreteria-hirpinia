"""Ufficio di presidenza e comitati in preparazione (presidenza.py), permessi
di presidenti e segretario, verbale precompilato."""

import datetime
import io

import pytest
from allauth.mfa.models import Authenticator
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from pypdf import PdfReader

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import comitato, duplica, elenco, odg, presidenza, sedute, verbale
from apps.assemblee.models import (
    Assemblea,
    IncaricoAssemblea,
    RuoloAssemblea,
    Seduta,
    TipoAssemblea,
)
from apps.assemblee.permessi import (
    assemblee_visibili,
    puo_compilare_verbale,
    puo_operare,
    puo_vedere_odg,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

P, S, M, SC = (
    RuoloAssemblea.PRESIDENTE,
    RuoloAssemblea.SEGRETARIO,
    RuoloAssemblea.MOZIONI,
    RuoloAssemblea.SCRUTATORE,
)


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
    for i, sesso in enumerate(["M", "F", "M", "F", "", "M"]):
        capo = Capo.objects.create(
            codice_socio=f"10{i}",
            nome="Nome",
            cognome=f"C{i}",
            sesso=sesso,
            email=f"c{i}@example.it",
        )
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22))
    elenco.importa_elenco(assemblea, segreteria)
    return assemblea


def _a(assemblea, i):
    return assemblea.aventi_diritto.get(codice_socio=f"10{i}")


class TestRegole:
    def test_due_presidenti_di_sesso_diverso(self, assemblea, segreteria):
        presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria, accesso=False)
        with pytest.raises(ValidationError, match="sesso diverso"):
            presidenza.aggiungi(assemblea, P, _a(assemblea, 2), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, P, _a(assemblea, 1), segreteria, accesso=False)
        with pytest.raises(ValidationError, match="al massimo 2"):
            presidenza.aggiungi(assemblea, P, _a(assemblea, 3), segreteria, accesso=False)

    def test_sesso_non_noto_ammesso_con_avviso(self, assemblea, segreteria):
        presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, P, _a(assemblea, 4), segreteria, accesso=False)
        assert any("non noto" in a.testo for a in presidenza.avvisi(assemblea))

    def test_un_segretario_tre_mozioni(self, assemblea, segreteria):
        presidenza.aggiungi(assemblea, S, _a(assemblea, 0), segreteria, accesso=False)
        with pytest.raises(ValidationError):
            presidenza.aggiungi(assemblea, S, _a(assemblea, 1), segreteria, accesso=False)
        for i in range(3):
            presidenza.aggiungi(assemblea, M, _a(assemblea, i), segreteria)
        with pytest.raises(ValidationError):
            presidenza.aggiungi(assemblea, M, _a(assemblea, 3), segreteria)
        assert not any("mozioni" in a.testo for a in presidenza.avvisi(assemblea))
        # Il comitato mozioni non ha accesso: nessun account, nessun invito.
        assert not IncaricoAssemblea.objects.filter(ruolo=M, utente__isnull=False).exists()

    def test_scrutatori_dal_comitato_elettorale(self, assemblea, segreteria):
        with pytest.raises(ValidationError, match="comitato elettorale"):
            presidenza.aggiungi(assemblea, SC, _a(assemblea, 0), segreteria)
        componente, _ = comitato.aggiungi(assemblea, _a(assemblea, 0), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, SC, _a(assemblea, 0), segreteria)
        # Chi esce dal comitato non è più scrutatore.
        comitato.rimuovi(componente, segreteria)
        assert not IncaricoAssemblea.objects.filter(ruolo=SC).exists()

    def test_doppione_e_fuori_elenco(self, assemblea, segreteria):
        presidenza.aggiungi(assemblea, M, _a(assemblea, 0), segreteria)
        with pytest.raises(ValidationError):
            presidenza.aggiungi(assemblea, M, _a(assemblea, 0), segreteria)
        uscito = _a(assemblea, 1)
        elenco.elimina([uscito], segreteria)
        uscito.refresh_from_db()
        with pytest.raises(ValidationError):
            presidenza.aggiungi(assemblea, M, uscito, segreteria)

    def test_solo_gestori(self, assemblea):
        capo = Utente.objects.create(username="c", email="c@example.it", stato=StatoUtente.ATTIVO)
        with pytest.raises(PermissionDenied):
            presidenza.aggiungi(assemblea, P, _a(assemblea, 0), capo)


class TestAccesso:
    def test_presidente_con_account_e_invito(self, assemblea, segreteria):
        incarico, inviato = presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria)
        assert inviato and incarico.utente.email == "c0@example.it"
        assert mail.outbox[-1].to == ["c0@example.it"]

    def test_accesso_dato_dopo(self, assemblea, segreteria):
        incarico, _ = presidenza.aggiungi(assemblea, S, _a(assemblea, 1), segreteria, accesso=False)
        assert incarico.utente is None
        assert presidenza.dai_accesso(incarico, segreteria)
        incarico.refresh_from_db()
        assert incarico.utente is not None
        mozioni, _ = presidenza.aggiungi(assemblea, M, _a(assemblea, 2), segreteria)
        with pytest.raises(ValidationError):
            presidenza.dai_accesso(mozioni, segreteria)

    def test_permessi_della_presidenza(self, assemblea, segreteria):
        incarico, _ = presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria)
        utente = incarico.utente
        assert puo_compilare_verbale(utente, assemblea)
        assert puo_vedere_odg(utente, assemblea)
        assert not puo_operare(utente, assemblea)
        assert list(assemblee_visibili(utente)) == [assemblea]
        with pytest.raises(PermissionDenied):
            odg.aggiungi_punto(assemblea, utente, "Nuovo punto")
        # Il comitato mozioni non vede nulla.
        mozioni = Utente.objects.create(
            username="m", email="m@example.it", stato=StatoUtente.ATTIVO
        )
        assert not puo_compilare_verbale(mozioni, assemblea)

    def test_presidenza_vede_anche_ad_assemblea_conclusa(self, assemblea, segreteria):
        from django.utils import timezone

        incarico, _ = presidenza.aggiungi(assemblea, S, _a(assemblea, 0), segreteria)
        assemblea.conclusa_il = timezone.now()
        assemblea.save()
        assert list(assemblee_visibili(incarico.utente)) == [assemblea]

    def test_rimozione_toglie_l_accesso(self, assemblea, segreteria):
        incarico, _ = presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria)
        utente = incarico.utente
        presidenza.rimuovi(incarico, segreteria)
        assert Utente.objects.filter(pk=utente.pk).exists()
        assert not puo_compilare_verbale(utente, assemblea)


def _costituita(assemblea, segreteria) -> Seduta:
    seduta = assemblea.sedute.get()
    sedute.apri_seduta(seduta, segreteria)
    for avente in assemblea.aventi_diritto.all():
        sedute.registra_presenza(seduta, avente, segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


class TestVerbale:
    def _prepara(self, assemblea, segreteria):
        presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, P, _a(assemblea, 1), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, S, _a(assemblea, 2), segreteria, accesso=False)
        presidenza.aggiungi(assemblea, M, _a(assemblea, 3), segreteria)
        for i in (4, 5):
            comitato.aggiungi(assemblea, _a(assemblea, i), segreteria, accesso=False)
            presidenza.aggiungi(assemblea, SC, _a(assemblea, i), segreteria)

    def test_precompilato_e_ripreso(self, assemblea, segreteria):
        self._prepara(assemblea, segreteria)
        seduta = _costituita(assemblea, segreteria)
        dati = verbale.verbale_della_seduta(seduta)
        assert (dati.presidente, dati.presidente_2, dati.segretario) == (
            "C0 Nome",
            "C1 Nome",
            "C2 Nome",
        )
        assert dati.comitato_mozioni == "C3 Nome"
        assert (dati.scrutatore_1, dati.scrutatore_2) == ("C4 Nome", "C5 Nome")
        # Modificabile seduta per seduta, poi ripreso dalla preparazione.
        dati.segretario = "Altro"
        dati.save()
        verbale.riprendi_dalla_preparazione(seduta, segreteria)
        dati.refresh_from_db()
        assert dati.segretario == "C2 Nome"

    def test_pdf_due_presidenti_e_mozioni_mancanti(self, assemblea, segreteria):
        self._prepara(assemblea, segreteria)
        seduta = _costituita(assemblea, segreteria)
        contenuto = verbale.genera_verbale_pdf(seduta, segreteria)
        testo = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenuto)).pages)
        testo = " ".join(testo.split())
        assert "nelle persone di C0 Nome e C1 Nome" in testo
        assert "formato da C3 Nome, […], […]" in testo

    def test_presidente_compila_il_verbale_dalla_pagina(self, client, assemblea, segreteria):
        incarico, _ = presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria)
        seduta = _costituita(assemblea, segreteria)
        client.force_login(incarico.utente)
        url = f"/assemblee/{assemblea.pk}/sedute/{seduta.pk}/verbale/"
        pagina = client.get(url)
        assert pagina.status_code == 200
        assert "Variazione del rappresentante legale" not in pagina.content.decode()
        assert client.get(f"/assemblee/{assemblea.pk}/odg/").status_code == 200
        assert client.get(url + "rappresentante-legale/").status_code == 403

    def test_scrutatori_scelti_dal_comitato(self, assemblea, segreteria):
        from apps.assemblee.forms import VerbaleForm

        form = VerbaleForm(nomi_comitato=["C4 Nome"])
        assert [v for v, _ in form.fields["scrutatore_1"].choices] == ["", "C4 Nome"]


def test_duplicazione_copia_gli_incarichi(assemblea, segreteria):
    presidenza.aggiungi(assemblea, P, _a(assemblea, 0), segreteria)
    nuova = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    Seduta.objects.create(assemblea=nuova, convocazione=1, data=datetime.date(2026, 12, 1))
    duplica.copia_in(assemblea, nuova, segreteria)
    copia = nuova.incarichi.get()
    assert copia.ruolo == P and copia.avente.assemblea == nuova
    assert copia.utente_id == assemblea.incarichi.get().utente_id


def test_pagina_assemblea_e_aggiunta(client, assemblea, segreteria):
    client.force_login(segreteria)
    client.post(
        f"/assemblee/{assemblea.pk}/incarichi/aggiungi/",
        {"ruolo": S, "avente": _a(assemblea, 0).pk, "accesso": "on"},
    )
    incarico = IncaricoAssemblea.objects.get()
    assert incarico.utente is not None
    pagina = client.get(f"/assemblee/{assemblea.pk}/").content.decode()
    assert "Ufficio di presidenza" in pagina and "Invito da attivare" in pagina
    client.post(f"/assemblee/{assemblea.pk}/incarichi/{incarico.pk}/rimuovi/")
    assert not IncaricoAssemblea.objects.exists()


def test_presidenza_scrive_la_discussione_ma_non_cambia_i_punti(client, assemblea, segreteria):
    punto = odg.aggiungi_punto(assemblea, segreteria, "Bilancio")
    incarico, _ = presidenza.aggiungi(assemblea, S, _a(assemblea, 0), segreteria)
    odg.scrivi_discussione(punto, incarico.utente, "Il tesoriere illustra.")
    with pytest.raises(PermissionDenied):
        odg.modifica_punto(punto, incarico.utente, titolo="Altro", testo="")
    capo = Utente.objects.create(username="x", email="x@example.it", stato=StatoUtente.ATTIVO)
    with pytest.raises(PermissionDenied):
        odg.scrivi_discussione(punto, capo, "No")

    client.force_login(incarico.utente)
    url = f"/assemblee/{assemblea.pk}/odg/{punto.pk}/"
    client.post(url, {"titolo": "Cambiato", "testo": "Dalla pagina."})
    punto.refresh_from_db()
    assert punto.titolo == "Bilancio" and punto.testo == "Dalla pagina."
