"""Urna elettronica (apps/voto/urna.py e pagine pubbliche)."""

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.assemblee import deleghe, elenco, sedute, votazioni
from apps.assemblee.models import TipoVotazione
from apps.voto import codici, urna
from apps.voto.models import CodiceVoto, Scheda, Votante

from .conftest import avente

pytestmark = pytest.mark.django_db


@pytest.fixture
def costituita(seduta, assemblea, segreteria):
    for cognome in ("Rossi", "Bianchi", "Verdi"):
        sedute.registra_presenza(seduta, avente(assemblea, cognome), segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


@pytest.fixture
def elezione(costituita, assemblea, segreteria):
    votazione = votazioni.apri_votazione(
        costituita,
        segreteria,
        tipo=TipoVotazione.ELEZIONE,
        oggetto="Elezione del Comitato",
        incarico="Membro del Comitato",
        posti=2,
        candidati=[avente(assemblea, "Verdi"), avente(assemblea, "Neri"), "Carlo Esterni"],
    )
    votazione.aperta_in_app_il = timezone.now()
    votazione.save()
    return votazione


def _codice(seduta, assemblea, cognome, utente) -> CodiceVoto:
    codici.emetti(seduta, avente(assemblea, cognome), utente)
    codice = codici.codice_attivo(seduta, avente(assemblea, cognome))
    assert codice is not None
    return codice


def _candidato(votazione, nome):
    return votazione.candidati.get(nome__icontains=nome).pk


class TestVota:
    def test_una_scheda_e_un_votante(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        esito = urna.vota(
            codice.pk, elezione, [urna.Scelte(candidati=(_candidato(elezione, "Verdi"),))]
        )
        assert len(esito.ricevute) == 1
        assert Votante.objects.get().avente.cognome == "Rossi"
        scheda = Scheda.objects.get()
        assert scheda.scelte["candidati"] == [_candidato(elezione, "Verdi")]
        assert scheda.ricevuta == esito.ricevute[0].ricevuta

    def test_un_solo_voto_per_votazione(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])
        assert Scheda.objects.count() == 1

    def test_fino_a_n_preferenze_contando_i_nomi_scritti(
        self, elezione, costituita, assemblea, segreteria
    ):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        troppe = urna.Scelte(
            candidati=(_candidato(elezione, "Verdi"), _candidato(elezione, "Neri")),
            liberi=("Gino Liberi",),
        )
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [troppe])
        giuste = urna.Scelte(candidati=(_candidato(elezione, "Verdi"),), liberi=(" Gino  Liberi ",))
        esito = urna.vota(codice.pk, elezione, [giuste])
        assert esito.ricevute[0].scelte.liberi == ("Gino Liberi",)

    def test_nessuna_preferenza_non_e_un_voto(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte()])

    def test_bianca_e_nulla_senza_preferenze(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        urna.vota(
            codice.pk,
            elezione,
            [urna.Scelte(esito=urna.ESITO_NULLA, candidati=(_candidato(elezione, "Verdi"),))],
        )
        assert Scheda.objects.get().scelte == {"esito": "NULLA", "candidati": [], "liberi": []}

    def test_candidato_di_un_altra_votazione(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte(candidati=(999999,))])

    def test_assente_rifiutato(self, elezione, costituita, assemblea, segreteria):
        # Neri non è stato registrato presente: un codice emesso per errore non basta.
        codice = _codice(costituita, assemblea, "Neri", segreteria)
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])

    def test_urna_chiusa_rifiutata(self, elezione, costituita, assemblea, segreteria):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        elezione.chiusa_in_app_il = timezone.now()
        elezione.save()
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])

    def test_codice_rigenerato_il_vecchio_non_vale(
        self, elezione, costituita, assemblea, segreteria
    ):
        vecchio = _codice(costituita, assemblea, "Rossi", segreteria)
        codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        with pytest.raises(ValidationError):
            urna.vota(vecchio.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])

    def test_passaggio_a_carta_dopo_il_voto_rifiutato(
        self, elezione, costituita, assemblea, segreteria
    ):
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])
        with pytest.raises(ValidationError):
            elenco.passa_a_carta(avente(assemblea, "Rossi"), segreteria)

    def test_revoca_del_mandato_non_si_vota_in_app(self, costituita, assemblea, segreteria):
        revoca = votazioni.apri_votazione(
            costituita, segreteria, tipo=TipoVotazione.REVOCA, oggetto="Revoca"
        )
        revoca.aperta_in_app_il = timezone.now()
        revoca.save()
        codice = _codice(costituita, assemblea, "Rossi", segreteria)
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, revoca, [urna.Scelte(esito=urna.ESITO_BIANCA)])


class TestDeleghe:
    @pytest.fixture
    def delega(self, costituita, assemblea, segreteria):
        # Neri è AE di Zona (assente), delega Bianchi, membro del Comitato.
        neri, bianchi = avente(assemblea, "Neri"), avente(assemblea, "Bianchi")
        deleghe.aggiorna_qualifiche(neri, segreteria, ae_zona=True, rdz=False, comitato=False)
        deleghe.aggiorna_qualifiche(bianchi, segreteria, ae_zona=False, rdz=False, comitato=True)
        return deleghe.registra_delega(costituita, neri, bianchi, segreteria)

    def test_il_delegato_esprime_due_schede(
        self, delega, elezione, costituita, assemblea, segreteria
    ):
        codice = _codice(costituita, assemblea, "Bianchi", segreteria)
        spettanti = urna.schede_spettanti(codice, elezione)
        assert [s.avente.cognome for s in spettanti] == ["Bianchi", "Neri"]
        bianca = urna.Scelte(esito=urna.ESITO_BIANCA)
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [bianca])
        with pytest.raises(ValidationError):
            urna.vota(codice.pk, elezione, [bianca, bianca, bianca])
        esito = urna.vota(codice.pk, elezione, [bianca, bianca])
        assert len(esito.ricevute) == 2
        neri = Votante.objects.get(avente__cognome="Neri")
        assert neri.tramite.cognome == "Bianchi"
        assert Scheda.objects.count() == 2

    def test_delega_revocata_una_sola_scheda(
        self, delega, elezione, costituita, assemblea, segreteria
    ):
        deleghe.revoca_delega(delega, segreteria)
        codice = _codice(costituita, assemblea, "Bianchi", segreteria)
        assert len(urna.schede_spettanti(codice, elezione)) == 1

    def test_delegante_passato_a_carta(self, delega, elezione, costituita, assemblea, segreteria):
        elenco.passa_a_carta(avente(assemblea, "Neri"), segreteria)
        codice = _codice(costituita, assemblea, "Bianchi", segreteria)
        assert len(urna.schede_spettanti(codice, elezione)) == 1


class TestAnonimato:
    def test_la_scheda_non_collega_nessuno(self):
        campi = {f.name for f in Scheda._meta.get_fields()}
        assert campi == {"id", "votazione", "ricevuta", "scelte", "interpretazione"}
        for modello in (Scheda, Votante):
            tipi = {type(f).__name__ for f in modello._meta.get_fields()}
            assert "DateTimeField" not in tipi and "DateField" not in tipi


class TestPagine:
    def _accedi(self, client, seduta, assemblea, cognome, utente):
        codice = codici.emetti(seduta, avente(assemblea, cognome), utente)
        return client.post("/voto/accedi/", {"codice": codici.formatta(codice).lower()})

    def test_voto_completo(self, client, elezione, costituita, assemblea, segreteria):
        risposta = self._accedi(client, costituita, assemblea, "Rossi", segreteria)
        assert risposta.url == "/voto/scheda/"
        pagina = client.get("/voto/scheda/").content.decode()
        assert "Carlo Esterni" in pagina and "Elezione del Comitato" in pagina
        dati = {
            "votazione": elezione.pk,
            "candidati_0": [_candidato(elezione, "Verdi")],
            "liberi_0": ["Gino Liberi", ""],
            "esito_0": "VOTO",
        }
        riepilogo = client.post("/voto/scheda/", {**dati, "azione": "rivedi"})
        assert "Conferma il voto" in riepilogo.content.decode()
        assert not Scheda.objects.exists()
        ricevuta = client.post("/voto/scheda/", {**dati, "azione": "conferma"})
        testo = ricevuta.content.decode()
        assert Scheda.objects.get().ricevuta in testo
        assert "no-store" in ricevuta["Cache-Control"]
        assert "Hai votato" in client.get("/voto/scheda/").content.decode()

    def test_errore_resta_sulla_scheda(self, client, elezione, costituita, assemblea, segreteria):
        self._accedi(client, costituita, assemblea, "Rossi", segreteria)
        risposta = client.post(
            "/voto/scheda/", {"votazione": elezione.pk, "azione": "rivedi", "esito_0": "VOTO"}
        )
        assert "Scegli almeno un candidato" in risposta.content.decode()

    def test_codice_sbagliato_e_tentativi_limitati(self, client, costituita):
        for _ in range(10):
            client.post("/voto/accedi/", {"codice": "AAAA-AAAA-AA"})
        codici_validi = client.post("/voto/accedi/", {"codice": "AAAA-AAAA-AA"})
        assert codici_validi.url == "/voto/"
        assert "Troppi tentativi" in client.get("/voto/").content.decode()

    def test_stato_per_il_polling(self, client, elezione, costituita, assemblea, segreteria):
        assert client.get("/voto/stato.json").json() == {"accesso": False}
        self._accedi(client, costituita, assemblea, "Rossi", segreteria)
        assert client.get("/voto/stato.json").json() == {
            "accesso": True,
            "votazione": elezione.pk,
        }

    def test_in_attesa_senza_votazioni(self, client, costituita, assemblea, segreteria):
        self._accedi(client, costituita, assemblea, "Rossi", segreteria)
        assert "In attesa" in client.get("/voto/scheda/").content.decode()

    def test_in_sessione_mai_il_codice_in_chiaro(self, client, costituita, assemblea, segreteria):
        codice = codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        client.post("/voto/accedi/", {"codice": codice})
        valori = " ".join(str(v) for v in client.session.values())
        assert codice not in valori


def test_l_assemblea_con_voti_si_puo_eliminare(elezione, costituita, assemblea, segreteria):
    codice = _codice(costituita, assemblea, "Rossi", segreteria)
    urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])
    assemblea.delete()
    assert not Votante.objects.exists() and not Scheda.objects.exists()


def test_l_avente_che_ha_votato_non_si_cancella(elezione, costituita, assemblea, segreteria):
    from django.db.models import RestrictedError

    codice = _codice(costituita, assemblea, "Rossi", segreteria)
    urna.vota(codice.pk, elezione, [urna.Scelte(esito=urna.ESITO_BIANCA)])
    with pytest.raises(RestrictedError):
        avente(assemblea, "Rossi").delete()
