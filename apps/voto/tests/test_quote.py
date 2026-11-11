"""Quote per sesso nel voto (docs/plan_preparazione_assemblea.md, D1, D2,
D4-bis, D4-ter): urna, scrutinio dei nomi scritti, calcolo degli eletti,
ballottaggio."""

import pytest
from django.core.exceptions import ValidationError

from apps.assemblee import candidature, sedute, votazioni
from apps.assemblee.models import CanaleVoto, Candidato, SistemaVoto, TipoVotazione
from apps.voto import codici, scrutinio, urna

from .conftest import avente

pytestmark = pytest.mark.django_db

# Rossi M, Bianchi F, Verdi M, Neri F, Gialli F.
SESSI = {"Rossi": "M", "Bianchi": "F", "Verdi": "M", "Neri": "F", "Gialli": "F"}


@pytest.fixture
def costituita(seduta, assemblea, segreteria):
    for cognome, sesso in SESSI.items():
        assemblea.aventi_diritto.filter(cognome=cognome).update(sesso=sesso)
    for cognome in SESSI:
        sedute.registra_presenza(seduta, avente(assemblea, cognome), segreteria)
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


def _elezione(costituita, assemblea, segreteria, cognomi, **posti):
    posizione = candidature.aggiungi_posizione(
        assemblea, segreteria, incarico="Membro del Comitato", **posti
    )
    for cognome in cognomi:
        candidature.aggiungi_candidatura(posizione, segreteria, avente=avente(assemblea, cognome))
    return votazioni.apri_votazione(
        costituita, segreteria, tipo="", oggetto="", posizione=posizione
    )


def _c(votazione, cognome) -> int:
    return votazione.candidati.get(nome__startswith=cognome).pk


class TestUrna:
    def test_limiti_per_sesso(self, costituita, assemblea, segreteria):
        # 1 M + 1 F: al massimo una preferenza per sesso.
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        ok = urna.valida_scelte(
            elezione, urna.Scelte(candidati=(_c(elezione, "Rossi"), _c(elezione, "Bianchi")))
        )
        assert len(ok.candidati) == 2
        with pytest.raises(ValidationError, match="1 preferenza maschile"):
            urna.valida_scelte(
                elezione, urna.Scelte(candidati=(_c(elezione, "Rossi"), _c(elezione, "Verdi")))
            )

    def test_indifferenti_allargano_il_limite(self, costituita, assemblea, segreteria):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
            posti_indifferenti=1,
        )
        urna.valida_scelte(
            elezione, urna.Scelte(candidati=(_c(elezione, "Rossi"), _c(elezione, "Verdi")))
        )

    def test_nome_scritto_richiede_il_sesso_dichiarato(self, costituita, assemblea, segreteria):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        with pytest.raises(ValidationError, match="posto maschile o femminile"):
            urna.valida_scelte(elezione, urna.Scelte(liberi=("Luca Verdi",)))
        with pytest.raises(ValidationError, match="1 preferenza maschile"):
            urna.valida_scelte(
                elezione,
                urna.Scelte(
                    candidati=(_c(elezione, "Rossi"),), liberi=("Luca Verdi",), sessi_liberi=("M",)
                ),
            )
        scelte = urna.valida_scelte(
            elezione, urna.Scelte(liberi=("", "Luca Verdi"), sessi_liberi=("", "M"))
        )
        assert scelte.liberi == ("Luca Verdi",) and scelte.sessi_liberi == ("M",)
        assert scelte.come_json()["sessi_liberi"] == ["M"]

    def test_senza_quote_niente_cambia(self, costituita, assemblea, segreteria):
        elezione = _elezione(
            costituita, assemblea, segreteria, ["Rossi", "Verdi"], posti_indifferenti=2
        )
        scelte = urna.valida_scelte(elezione, urna.Scelte(liberi=("Pia Neri",)))
        assert "sessi_liberi" not in scelte.come_json()


def _vota(seduta, assemblea, cognome, utente, votazione, scelte):
    codici.emetti(seduta, avente(assemblea, cognome), utente)
    codice = codici.codice_attivo(seduta, avente(assemblea, cognome))
    return urna.vota(codice.pk, votazione, [scelte])


class TestScrutinio:
    def test_nome_scritto_col_sesso_sbagliato_non_conta(self, costituita, assemblea, segreteria):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        scrutinio.apri_urna(elezione, segreteria)
        # Rossi sceglie Bianchi e scrive «Pia Neri» per il posto maschile: non conta.
        _vota(
            costituita,
            assemblea,
            "Rossi",
            segreteria,
            elezione,
            urna.Scelte(
                candidati=(_c(elezione, "Bianchi"),), liberi=("Pia Neri",), sessi_liberi=("M",)
            ),
        )
        # Verdi la scrive per il posto femminile: conta.
        _vota(
            costituita,
            assemblea,
            "Verdi",
            segreteria,
            elezione,
            urna.Scelte(liberi=("Pia Neri",), sessi_liberi=("F",)),
        )
        scrutinio.chiudi_urna(elezione, segreteria)
        scrutinio.interpreta(elezione, "Pia Neri", avente(assemblea, "Neri"), segreteria)
        conto = scrutinio.conteggio(elezione)
        neri = elezione.candidati.get(avente=avente(assemblea, "Neri"))
        assert neri.sesso == "F"
        assert conto.voti[neri.pk] == 1
        assert conto.voti[_c(elezione, "Bianchi")] == 1
        # La bacheca riporta la stessa interpretazione.
        righe = scrutinio.righe_bacheca(elezione)
        assert sum("Neri" in r for r in righe) == 1

    def test_con_quote_si_attribuisce_solo_a_chi_ha_il_sesso(
        self, costituita, assemblea, segreteria
    ):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        scrutinio.apri_urna(elezione, segreteria)
        _vota(
            costituita,
            assemblea,
            "Rossi",
            segreteria,
            elezione,
            urna.Scelte(liberi=("Sara Gialli",), sessi_liberi=("F",)),
        )
        scrutinio.chiudi_urna(elezione, segreteria)
        assemblea.aventi_diritto.filter(cognome="Gialli").update(sesso="")
        with pytest.raises(ValidationError, match="non è noto"):
            scrutinio.interpreta(elezione, "Sara Gialli", avente(assemblea, "Gialli"), segreteria)


@pytest.fixture
def cartacea(assemblea):
    """Risultati inseriti a mano (sistema del Nazionale): per provare l'esito."""
    assemblea.sistema_voto = SistemaVoto.NAZIONALE
    assemblea.save()
    return assemblea


def _registra(votazione, utente, voti: dict[str, int]):
    voti_candidati = {
        c.pk: {"voti_carta": voti[c.nome.split()[0]]} for c in votazione.candidati.all()
    }
    votazioni.registra_risultati(
        votazione,
        utente,
        per_canale={CanaleVoto.CARTA.value: {"bianche": 0, "nulle": 0}},
        voti_candidati=voti_candidati,
    )
    votazione.refresh_from_db()
    return votazioni.esito(votazione)


class TestEsito:
    def test_graduatoria_per_sesso(self, cartacea, costituita, assemblea, segreteria):
        # 5 presenti: soglia 3. Rossi 5, Verdi 4 (M), Bianchi 3 (F): 1 M + 1 F.
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        esito = _registra(elezione, segreteria, {"Rossi": 5, "Verdi": 4, "Bianchi": 3})
        assert sorted(c.nome.split()[0] for c in esito.eletti) == ["Bianchi", "Rossi"]
        assert esito.posti_vacanti == 0

    def test_prima_i_vincolati_poi_gli_indifferenti(
        self, cartacea, costituita, assemblea, segreteria
    ):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi", "Neri"],
            posti_maschili=1,
            posti_femminili=1,
            posti_indifferenti=1,
        )
        esito = _registra(elezione, segreteria, {"Rossi": 5, "Verdi": 4, "Bianchi": 3, "Neri": 5})
        # M: Rossi; F: Neri; indifferente: Verdi (4) prima di Bianchi (3).
        assert sorted(c.nome.split()[0] for c in esito.eletti) == ["Neri", "Rossi", "Verdi"]

    def test_posto_vacante_e_ballottaggio_dello_stesso_sesso(
        self, cartacea, costituita, assemblea, segreteria
    ):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi", "Neri"],
            posti_maschili=1,
            posti_femminili=1,
        )
        # Rossi eletto; le due femmine sotto soglia (3): posto femminile vacante.
        esito = _registra(elezione, segreteria, {"Rossi": 5, "Verdi": 4, "Bianchi": 2, "Neri": 1})
        assert [c.nome.split()[0] for c in esito.eletti] == ["Rossi"]
        assert esito.vacanti_per_sesso == {"F": 1}
        # Il ballottaggio è fra le due femmine, non con Verdi più votato.
        assert sorted(c.nome.split()[0] for c in esito.ballottaggio_proposto) == ["Bianchi", "Neri"]
        assert esito.ballottaggio_sesso == "F"
        assert "1 femminile" in votazioni.frase_esito(
            elezione
        ) or "ballottaggio" in votazioni.frase_esito(elezione)
        ballottaggio = votazioni.apri_ballottaggio(elezione, segreteria)
        assert (ballottaggio.posti_maschili, ballottaggio.posti_femminili) == (0, 1)
        assert all(c.sesso == "F" for c in ballottaggio.candidati.all())

    def test_parita_sull_ultimo_posto_di_un_sesso(
        self, cartacea, costituita, assemblea, segreteria
    ):
        elezione = _elezione(
            costituita,
            assemblea,
            segreteria,
            ["Rossi", "Verdi", "Bianchi"],
            posti_maschili=1,
            posti_femminili=1,
        )
        esito = _registra(elezione, segreteria, {"Rossi": 4, "Verdi": 4, "Bianchi": 3})
        assert [c.nome.split()[0] for c in esito.eletti] == ["Bianchi"]
        assert esito.vacanti_per_sesso == {"M": 1}
        assert sorted(c.nome.split()[0] for c in esito.ballottaggio_proposto) == ["Rossi", "Verdi"]

    def test_senza_quote_regola_di_sempre(self, cartacea, costituita, assemblea, segreteria):
        elezione = votazioni.apri_votazione(
            costituita,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="E",
            incarico="X",
            posti=2,
            candidati=[
                avente(assemblea, "Rossi"),
                avente(assemblea, "Verdi"),
                avente(assemblea, "Bianchi"),
            ],
        )
        esito = _registra(elezione, segreteria, {"Rossi": 5, "Verdi": 4, "Bianchi": 3})
        assert sorted(c.nome.split()[0] for c in esito.eletti) == ["Rossi", "Verdi"]
        assert Candidato.objects.get(votazione=elezione, nome__startswith="Rossi").sesso == "M"


def test_scheda_con_quote_dalla_pagina(client, costituita, assemblea, segreteria):
    elezione = _elezione(
        costituita, assemblea, segreteria, ["Rossi", "Bianchi"], posti_maschili=1, posti_femminili=1
    )
    scrutinio.apri_urna(elezione, segreteria)
    codice = codici.emetti(costituita, avente(assemblea, "Verdi"), segreteria)
    client.post("/voto/accedi/", {"codice": codici.formatta(codice)})
    pagina = client.get("/voto/scheda/").content.decode()
    assert "Posti maschili 1, femminili 1" in pagina and 'name="sessi_liberi_0"' in pagina
    dati = {
        "votazione": elezione.pk,
        "candidati_0": [_c(elezione, "Bianchi")],
        "liberi_0": ["Luca Verdi", ""],
        "sessi_liberi_0": ["M", ""],
        "esito_0": "VOTO",
    }
    riepilogo = client.post("/voto/scheda/", {**dati, "azione": "rivedi"}).content.decode()
    assert "«Luca Verdi» (nome scritto, posto maschile)" in riepilogo
    troppi = client.post(
        "/voto/scheda/",
        {**dati, "candidati_0": [_c(elezione, "Rossi")], "azione": "rivedi"},
    ).content.decode()
    assert "al massimo 1 preferenza maschile" in troppi
