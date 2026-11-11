"""Apertura, chiusura e scrutinio dell'urna (apps/voto/scrutinio.py)."""

import pytest
from django.core.exceptions import ValidationError

from apps.assemblee import sedute, verbale, votazioni
from apps.assemblee.models import CanaleVoto, SistemaVoto, TipoVotazione
from apps.voto import codici, scrutinio, urna
from apps.voto.models import Scheda

from .conftest import avente

pytestmark = pytest.mark.django_db

PRESENTI = ("Rossi", "Bianchi", "Verdi", "Neri")


@pytest.fixture
def costituita(seduta, assemblea, segreteria):
    for cognome in PRESENTI:
        sedute.registra_presenza(seduta, avente(assemblea, cognome), segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


@pytest.fixture
def elezione(costituita, assemblea, segreteria):
    return votazioni.apri_votazione(
        costituita,
        segreteria,
        tipo=TipoVotazione.ELEZIONE,
        oggetto="Elezione del Responsabile",
        incarico="Responsabile di Zona",
        posti=1,
        candidati=[avente(assemblea, "Verdi"), avente(assemblea, "Neri")],
    )


def _vota(seduta, assemblea, cognome, utente, votazione, scelte):
    codici.emetti(seduta, avente(assemblea, cognome), utente)
    codice = codici.codice_attivo(seduta, avente(assemblea, cognome))
    return urna.vota(codice.pk, votazione, [scelte])


def _candidato(votazione, cognome):
    return votazione.candidati.get(nome__startswith=cognome).pk


@pytest.fixture
def urna_votata(elezione, costituita, assemblea, segreteria):
    """Rossi: Verdi; Bianchi: bianca; Verdi: «mario ROSSI» scritto; Neri: Neri."""
    scrutinio.apri_urna(elezione, segreteria)
    _vota(
        costituita,
        assemblea,
        "Rossi",
        segreteria,
        elezione,
        urna.Scelte(candidati=(_candidato(elezione, "Verdi"),)),
    )
    _vota(
        costituita, assemblea, "Bianchi", segreteria, elezione, urna.Scelte(esito=urna.ESITO_BIANCA)
    )
    _vota(
        costituita, assemblea, "Verdi", segreteria, elezione, urna.Scelte(liberi=("mario  ROSSI",))
    )
    _vota(
        costituita,
        assemblea,
        "Neri",
        segreteria,
        elezione,
        urna.Scelte(candidati=(_candidato(elezione, "Neri"),)),
    )
    return elezione


class TestUrna:
    def test_apri_solo_con_il_voto_di_catello(self, elezione, assemblea, segreteria):
        assemblea.sistema_voto = SistemaVoto.NAZIONALE
        assemblea.save()
        with pytest.raises(ValidationError):
            scrutinio.apri_urna(elezione, segreteria)

    def test_piu_urne_aperte_si_votano_insieme_e_si_chiudono_insieme(
        self, elezione, costituita, assemblea, segreteria
    ):
        seconda = votazioni.apri_votazione(
            costituita,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Altra",
            incarico="X",
            candidati=["Tizio"],
        )
        scrutinio.apri_urne(costituita, [elezione, seconda], segreteria)
        assert urna.votazioni_aperte(costituita) == [elezione, seconda]

        codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        codice = codici.codice_attivo(costituita, avente(assemblea, "Rossi"))
        assert [v for v, _ in urna.da_votare(codice)] == [elezione, seconda]
        voto_uno = {elezione.pk: [urna.Scelte(candidati=(_candidato(elezione, "Verdi"),))]}
        # Tutte o nessuna: una sola delle due non basta.
        with pytest.raises(ValidationError, match="cambiate"):
            urna.vota_insieme(codice.pk, voto_uno)
        esiti = urna.vota_insieme(
            codice.pk, {**voto_uno, seconda.pk: [urna.Scelte(esito=urna.ESITO_BIANCA)]}
        )
        assert [v for v, _ in esiti] == [elezione, seconda]
        assert scrutinio.numero_votanti(elezione) == scrutinio.numero_votanti(seconda) == 1
        assert urna.da_votare(codice) == []

        assert scrutinio.chiudi_urne(costituita, segreteria) == [elezione, seconda]
        assert urna.votazioni_aperte(costituita) == []
        with pytest.raises(ValidationError):
            scrutinio.chiudi_urne(costituita, segreteria)

    def test_un_errore_in_una_scheda_non_registra_nulla(
        self, elezione, costituita, assemblea, segreteria
    ):
        seconda = votazioni.apri_votazione(
            costituita,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Altra",
            incarico="X",
            candidati=["Tizio"],
        )
        scrutinio.apri_urne(costituita, [elezione, seconda], segreteria)
        codici.emetti(costituita, avente(assemblea, "Rossi"), segreteria)
        codice = codici.codice_attivo(costituita, avente(assemblea, "Rossi"))
        with pytest.raises(ValidationError):
            urna.vota_insieme(
                codice.pk,
                {
                    elezione.pk: [urna.Scelte(esito=urna.ESITO_BIANCA)],
                    seconda.pk: [urna.Scelte(candidati=(999999,))],
                },
            )
        assert Scheda.objects.count() == 0
        assert scrutinio.numero_votanti(elezione) == 0

    def test_con_urne_aperte_non_se_ne_aprono_altre(
        self, elezione, costituita, assemblea, segreteria
    ):
        scrutinio.apri_urna(elezione, segreteria)
        seconda = votazioni.apri_votazione(
            costituita,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Altra",
            incarico="X",
            candidati=["Tizio"],
        )
        with pytest.raises(ValidationError, match="già urne aperte"):
            scrutinio.apri_urna(seconda, segreteria)
        scrutinio.chiudi_urne(costituita, segreteria)
        scrutinio.apri_urna(seconda, segreteria)

    def test_apertura_insieme_dall_elenco(
        self, client, elezione, costituita, assemblea, segreteria
    ):
        seconda = votazioni.apri_votazione(
            costituita,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Altra",
            incarico="X",
            candidati=["Tizio"],
        )
        client.force_login(segreteria)
        base = f"/assemblee/{assemblea.pk}/sedute/{costituita.pk}"
        assert "Apri le urne selezionate" in client.get(f"{base}/votazioni/").content.decode()
        client.post(
            f"/voto/gestione/{assemblea.pk}/sedute/{costituita.pk}/urne/apri/",
            {"votazioni": [elezione.pk, seconda.pk]},
        )
        assert urna.votazioni_aperte(costituita) == [elezione, seconda]
        assert "Urne aperte" in client.get(f"{base}/votazioni/").content.decode()

    def test_le_palesi_non_hanno_urna(self, costituita, segreteria):
        mozione = votazioni.apri_votazione(
            costituita, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Mozione"
        )
        with pytest.raises(ValidationError):
            scrutinio.apri_urna(mozione, segreteria)

    def test_chiusura_rimescola_ricevute_intatte(self, urna_votata, segreteria):
        prima = dict(Scheda.objects.values_list("ricevuta", "id"))
        scrutinio.chiudi_urna(urna_votata, segreteria)
        dopo = dict(Scheda.objects.values_list("ricevuta", "id"))
        assert set(prima) == set(dopo)
        assert not set(prima.values()) & set(dopo.values())

    def test_schede_diverse_dai_votanti_bloccano(self, urna_votata, segreteria):
        Scheda.objects.first().delete()
        with pytest.raises(ValidationError):
            scrutinio.chiudi_urna(urna_votata, segreteria)
        urna_votata.refresh_from_db()
        assert urna_votata.urna_aperta

    def test_annullare_una_votazione_con_l_urna_aperta(self, urna_votata, segreteria):
        with pytest.raises(ValidationError):
            votazioni.annulla_votazione(urna_votata, segreteria)


class TestScrutinio:
    def test_risultati_bloccati_a_urna_aperta(self, urna_votata, segreteria):
        with pytest.raises(ValidationError):
            votazioni.registra_risultati(urna_votata, segreteria, per_canale={})

    def test_risultati_bloccati_con_nomi_da_interpretare(self, urna_votata, segreteria):
        scrutinio.chiudi_urna(urna_votata, segreteria)
        assert [n.testo for n in scrutinio.nomi_da_interpretare(urna_votata)] == ["mario ROSSI"]
        with pytest.raises(ValidationError):
            votazioni.registra_risultati(urna_votata, segreteria, per_canale={})

    def test_nome_attribuito_diventa_candidato_e_conta(self, urna_votata, assemblea, segreteria):
        scrutinio.chiudi_urna(urna_votata, segreteria)
        scrutinio.interpreta(urna_votata, "Mario Rossi", avente(assemblea, "Rossi"), segreteria)
        votazioni.registra_risultati(
            urna_votata,
            segreteria,
            # I voti in app passati a mano si ignorano.
            per_canale={CanaleVoto.APP: {"bianche": 99}, CanaleVoto.CARTA: {"nulle": 0}},
        )
        voti = {c.nome: (c.voti_app, c.voti_carta) for c in urna_votata.candidati.all()}
        assert voti == {"Verdi Luca": (1, 0), "Neri Pia": (1, 0), "Rossi Mario": (1, 0)}
        app = urna_votata.risultati.get(canale=CanaleVoto.APP)
        assert (app.bianche, app.nulle) == (1, 0)
        assert len(urna_votata.hash_bacheca) == 64

    def test_nome_nullo_rende_nulla_la_scheda(self, urna_votata, segreteria):
        scrutinio.chiudi_urna(urna_votata, segreteria)
        scrutinio.interpreta(urna_votata, "mario rossi", None, segreteria)
        votazioni.registra_risultati(urna_votata, segreteria, per_canale={})
        app = urna_votata.risultati.get(canale=CanaleVoto.APP)
        assert (app.bianche, app.nulle) == (1, 1)

    def test_votazione_tutta_su_carta(self, elezione, segreteria):
        # Urna mai aperta: valgono solo i voti su carta.
        votazioni.registra_risultati(
            elezione,
            segreteria,
            per_canale={CanaleVoto.CARTA: {}},
            voti_candidati={_candidato(elezione, "Verdi"): {"voti_carta": 3}},
        )
        assert elezione.candidati.get(nome__startswith="Verdi").voti == 3
        assert elezione.hash_bacheca == ""


class TestBachecaEVerifica:
    @pytest.fixture
    def scrutinata(self, urna_votata, assemblea, segreteria):
        scrutinio.chiudi_urna(urna_votata, segreteria)
        scrutinio.interpreta(urna_votata, "mario rossi", avente(assemblea, "Rossi"), segreteria)
        votazioni.registra_risultati(urna_votata, segreteria, per_canale={})
        urna_votata.refresh_from_db()
        return urna_votata

    def test_bacheca_deterministica_senza_testi_scritti(self, scrutinata):
        righe = scrutinio.righe_bacheca(scrutinata)
        assert len(righe) == 4
        assert righe == sorted(righe)
        assert scrutinio.impronta(righe) == scrutinata.hash_bacheca
        assert not any("mario  ROSSI" in r or "mario ROSSI" in r for r in righe)
        assert any(r.endswith(": Rossi Mario") for r in righe)

    def test_verifica_prima_e_dopo(self, urna_votata, assemblea, segreteria):
        ricevuta = Scheda.objects.first().ricevuta
        prima = scrutinio.verifica_ricevuta(ricevuta.lower())
        assert prima.trovata and not prima.pubblicata
        scrutinio.chiudi_urna(urna_votata, segreteria)
        scrutinio.interpreta(urna_votata, "mario rossi", None, segreteria)
        votazioni.registra_risultati(urna_votata, segreteria, per_canale={})
        dopo = scrutinio.verifica_ricevuta(ricevuta)
        assert dopo.pubblicata and dopo.riga.startswith(ricevuta)
        assert not scrutinio.verifica_ricevuta("ZZZZ-ZZZZ-ZZZZ").trovata

    def test_nota_nel_verbale(self, scrutinata, costituita):
        nota = scrutinio.nota_verbale(scrutinata)
        assert scrutinata.hash_bacheca in nota
        assert "1 attribuiti" in nota and "rossi" not in nota.lower()
        voci = verbale.contesto_verbale(costituita)["senza_punto"]
        assert voci[0].nota_app == nota

    def test_pagine_pubbliche(self, client, scrutinata):
        risposta = client.get(f"/voto/bacheca/{scrutinata.pk}/")
        assert risposta.status_code == 200
        assert scrutinata.hash_bacheca in risposta.content.decode()
        ricevuta = Scheda.objects.first().ricevuta
        verifica = client.post("/voto/verifica/", {"ricevuta": ricevuta})
        assert "è stata contata così" in verifica.content.decode()

    def test_bacheca_solo_a_risultati_registrati(self, client, urna_votata):
        assert client.get(f"/voto/bacheca/{urna_votata.pk}/").status_code == 404


class TestVisteGestione:
    def test_apri_e_chiudi_dalla_pagina(self, client, elezione, costituita, assemblea, operatore):
        client.force_login(operatore)
        url = f"/voto/gestione/{assemblea.pk}/sedute/{costituita.pk}/votazioni/{elezione.pk}/urna/"
        client.post(url, {"azione": "apri"})
        elezione.refresh_from_db()
        assert elezione.urna_aperta
        pagina = client.get(
            f"/assemblee/{assemblea.pk}/sedute/{costituita.pk}/votazioni/{elezione.pk}/"
        ).content.decode()
        assert "hanno votato in app" in pagina
        client.post(url, {"azione": "chiudi"})  # senza conferma: resta aperta
        elezione.refresh_from_db()
        assert elezione.urna_aperta
        client.post(url, {"azione": "chiudi", "conferma": "1"})
        elezione.refresh_from_db()
        assert elezione.chiusa_in_app_il is not None

    def test_commissione_interpreta(self, client, urna_votata, costituita, assemblea, operatore):
        scrutinio.chiudi_urna(urna_votata, operatore)
        client.force_login(operatore)
        url = (
            f"/voto/gestione/{assemblea.pk}/sedute/{costituita.pk}/votazioni/"
            f"{urna_votata.pk}/nomi/"
        )
        assert "mario ROSSI" in client.get(url).content.decode()
        client.post(url, {"testo": "mario ROSSI", "avente": "nullo"})
        assert not scrutinio.nomi_da_interpretare(urna_votata)

    def test_form_risultati_senza_campi_app(
        self, client, elezione, costituita, assemblea, operatore
    ):
        client.force_login(operatore)
        pagina = client.get(
            f"/assemblee/{assemblea.pk}/sedute/{costituita.pk}/votazioni/{elezione.pk}/"
        ).content.decode()
        assert "(carta)" in pagina and "(app)" not in pagina
