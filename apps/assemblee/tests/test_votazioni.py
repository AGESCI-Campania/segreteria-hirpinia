"""Votazioni, soglie ed esiti alla lettera dal regolamento (apps/assemblee/votazioni.py)."""

import datetime

import pytest
from allauth.mfa.models import Authenticator
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import Ruolo, StatoUtente, TipoUtente, Utente
from apps.anagrafica.models import Capo, CensimentoCapo
from apps.assemblee import elenco, sedute, votazioni
from apps.assemblee.models import (
    Assemblea,
    CanaleVoto,
    RichiedenteVerifica,
    Seduta,
    TipoAssemblea,
    TipoVotazione,
    Votazione,
)
from apps.organizzazione.models import Gruppo

pytestmark = pytest.mark.django_db

PRESENTI = 120
AVENTI = 186


@pytest.fixture
def segreteria() -> Utente:
    utente = Utente.objects.create(
        username="segr", email="s@example.it", tipo=TipoUtente.PERSONA, stato=StatoUtente.ATTIVO
    )
    Ruolo.objects.create(utente=utente, tipo=Ruolo.Tipo.SEGRETERIA)
    Authenticator.objects.create(user=utente, type=Authenticator.Type.TOTP, data={})
    return utente


@pytest.fixture
def seduta(segreteria) -> Seduta:
    """Seduta costituita con 4 aventi diritto e 3 presenti (per le operazioni)."""
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    for i in range(4):
        capo = Capo.objects.create(codice_socio=str(i), nome="Nome", cognome=f"C{i}")
        CensimentoCapo.objects.create(capo=capo, anno_scout=2026, gruppo=gruppo)
    assemblea = Assemblea.objects.create(tipo=TipoAssemblea.AUTUNNALE, anno_scout=2027)
    seduta = Seduta.objects.create(
        assemblea=assemblea, convocazione=1, data=datetime.date(2026, 11, 22)
    )
    elenco.importa_elenco(assemblea, segreteria)
    sedute.apri_seduta(seduta, segreteria)
    for i in range(3):
        sedute.registra_presenza(
            seduta, assemblea.aventi_diritto.get(codice_socio=str(i)), segreteria
        )
    sedute.dichiara_costituita(seduta, segreteria)
    return seduta


def _votazione(seduta, tipo, *, presenti=PRESENTI, aventi=AVENTI, posti=1, candidati=()):
    """Votazione con numeri fotografati arbitrari, per provare le soglie."""
    v = Votazione.objects.create(
        seduta=seduta,
        tipo=tipo,
        oggetto="Prova",
        incarico="Membro del Comitato di Zona" if candidati else "",
        posti=posti,
        presenti=presenti,
        aventi_diritto=aventi,
    )
    for nome in candidati:
        v.candidati.create(nome=nome)
    return v


def _palese(votazione, utente, fav, contr, ast):
    canale = votazioni.canali(votazione)[0]
    return votazioni.registra_risultati(
        votazione,
        utente,
        per_canale={canale: {"favorevoli": fav, "contrari": contr, "astenuti": ast}},
    )


def _elezione(votazione, utente, voti_carta: dict[str, int], bianche=0, nulle=0):
    voti = {c.pk: {"voti_carta": voti_carta[c.nome]} for c in votazione.candidati.all()}
    per_canale = {CanaleVoto.CARTA.value: {"bianche": bianche, "nulle": nulle}}
    return votazioni.registra_risultati(
        votazione, utente, per_canale=per_canale, voti_candidati=voti
    )


class TestDeliberazioni:
    @pytest.mark.parametrize(
        "tipo",
        [TipoVotazione.MOZIONE, TipoVotazione.BILANCIO, TipoVotazione.RACCOMANDAZIONE],
    )
    def test_soglia_meta_dei_presenti_piu_uno(self, seduta, segreteria, tipo):
        respinta = _palese(_votazione(seduta, tipo), segreteria, 60, 30, 30)
        approvata = _palese(_votazione(seduta, tipo), segreteria, 61, 30, 29)
        assert (respinta.soglia, respinta.approvata) == (61, False)
        assert approvata.approvata

    def test_astenuti_pesano_come_non_favorevoli(self, seduta, segreteria):
        """Esempio concordato: 120 presenti, 55 favorevoli → respinta."""
        assert not _palese(
            _votazione(seduta, TipoVotazione.MOZIONE), segreteria, 55, 40, 25
        ).approvata

    def test_palese_un_solo_canale(self, seduta):
        assert votazioni.canali(_votazione(seduta, TipoVotazione.MOZIONE)) == [CanaleVoto.PALESE]

    def test_mozione_d_ordine_sui_votanti(self, seduta, segreteria):
        esito = _palese(_votazione(seduta, TipoVotazione.MOZIONE_ORDINE), segreteria, 30, 20, 9)
        assert (esito.base_nome, esito.base, esito.soglia, esito.approvata) == (
            "votanti",
            59,
            30,
            True,
        )

    def test_revoca_sugli_aventi_diritto(self, seduta, segreteria):
        revoca = _votazione(seduta, TipoVotazione.REVOCA)
        assert votazioni.canali(revoca) == [CanaleVoto.APP, CanaleVoto.CARTA]
        esito = votazioni.registra_risultati(
            revoca,
            segreteria,
            per_canale={
                CanaleVoto.APP.value: {"favorevoli": 60},
                CanaleVoto.CARTA.value: {"favorevoli": 33},
            },
        )
        # 93 favorevoli su 120 presenti, ma servono 94 degli aventi diritto.
        assert (esito.soglia, esito.approvata) == (94, False)

    def test_voti_oltre_i_presenti_rifiutati(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            _palese(_votazione(seduta, TipoVotazione.MOZIONE), segreteria, 100, 20, 1)


class TestElezioni:
    def test_eletto_al_primo_turno(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno"])
        esito = _elezione(v, segreteria, {"Anna": 70, "Bruno": 40}, bianche=10)
        assert [c.nome for c in esito.eletti] == ["Anna"]
        assert esito.posti_vacanti == 0

    def test_nessuno_eletto_ballottaggio_fra_i_primi_due(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno", "Carla"])
        esito = _elezione(v, segreteria, {"Anna": 55, "Bruno": 50, "Carla": 10})
        assert esito.eletti == []
        assert [c.nome for c in esito.ballottaggio_proposto] == ["Anna", "Bruno"]

    def test_candidatura_unica_senza_quorum_posto_vacante(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna"])
        esito = _elezione(v, segreteria, {"Anna": 55})
        assert esito.posti_vacanti == 1 and esito.ballottaggio_proposto == []

    def test_piu_posti(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, posti=2, candidati=["A", "B", "C"])
        esito = _elezione(v, segreteria, {"A": 80, "B": 65, "C": 30})
        assert [c.nome for c in esito.eletti] == ["A", "B"]

    def test_piu_posti_con_posto_scoperto(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, posti=2, candidati=["A", "B", "C"])
        esito = _elezione(v, segreteria, {"A": 80, "B": 50, "C": 45})
        assert [c.nome for c in esito.eletti] == ["A"]
        assert [c.nome for c in esito.ballottaggio_proposto] == ["B", "C"]

    def test_parita_sull_ultimo_posto(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, posti=2, candidati=["A", "B", "C"])
        esito = _elezione(v, segreteria, {"A": 90, "B": 70, "C": 70})
        assert [c.nome for c in esito.eletti] == ["A"]
        assert {c.nome for c in esito.ballottaggio_proposto} == {"B", "C"}

    def test_ballottaggio_solo_carta_e_un_solo_turno(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno", "Carla"])
        _elezione(v, segreteria, {"Anna": 55, "Bruno": 50, "Carla": 10})
        ballottaggio = votazioni.apri_ballottaggio(v, segreteria)
        assert votazioni.canali(ballottaggio) == [CanaleVoto.CARTA]
        assert sorted(c.nome for c in ballottaggio.candidati.all()) == ["Anna", "Bruno"]
        with pytest.raises(ValidationError):
            votazioni.apri_ballottaggio(v, segreteria)

    def test_ballottaggio_senza_maggioranza_posto_vacante(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno", "Carla"])
        _elezione(v, segreteria, {"Anna": 55, "Bruno": 50, "Carla": 10})
        ballottaggio = votazioni.apri_ballottaggio(v, segreteria)
        # Il ballottaggio fotografa i presenti della seduta (3 nella fixture).
        esito = _elezione(ballottaggio, segreteria, {"Anna": 1, "Bruno": 1})
        assert esito.eletti == [] and esito.posti_vacanti == 1
        assert esito.ballottaggio_proposto == []

    def test_frase_di_esito(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno"])
        _elezione(v, segreteria, {"Anna": 70, "Bruno": 40}, bianche=2)
        frase = votazioni.frase_esito(v)
        assert "Anna 70 voti" in frase and "eletto: Anna" in frase and "soglia 61" in frase


class TestApertura:
    def test_fotografa_i_presenti_e_aggiunge_chi_arriva(self, seduta, segreteria):
        v = votazioni.apri_votazione(
            seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Bilancio"
        )
        assert (v.presenti, v.aventi_diritto) == (3, 4)
        arrivato = seduta.assemblea.aventi_diritto.get(codice_socio="3")
        sedute.registra_presenza(seduta, arrivato, segreteria)
        v.refresh_from_db()
        # Arrivato a votazione aperta: vota ed entra nella base della maggioranza.
        assert v.presenti == 4
        # Togliere una presenza a votazione aperta cambierebbe la base: non si può.
        with pytest.raises(ValidationError, match="votazione aperta"):
            sedute.annulla_presenza(seduta, arrivato, segreteria)

    def test_a_votazione_chiusa_la_base_non_cambia(self, seduta, segreteria):
        v = votazioni.apri_votazione(
            seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Bilancio"
        )
        votazioni.registra_risultati(
            v, segreteria, per_canale={"PALESE": {"favorevoli": 3, "contrari": 0, "astenuti": 0}}
        )
        arrivato = seduta.assemblea.aventi_diritto.get(codice_socio="3")
        sedute.registra_presenza(seduta, arrivato, segreteria)
        v.refresh_from_db()
        assert v.presenti == 3
        sedute.annulla_presenza(seduta, arrivato, segreteria)

    def test_elezione_richiede_incarico_e_candidati(self, seduta, segreteria):
        with pytest.raises(ValidationError):
            votazioni.apri_votazione(
                seduta, segreteria, tipo=TipoVotazione.ELEZIONE, oggetto="Comitato"
            )
        v = votazioni.apri_votazione(
            seduta,
            segreteria,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Comitato",
            incarico="Membro del Comitato",
            candidati=[seduta.assemblea.aventi_diritto.get(codice_socio="0"), "Esterno Mario"],
        )
        assert v.candidati.count() == 2
        assert v.candidati.filter(avente__isnull=False).count() == 1

    def test_solo_in_seduta_costituita(self, seduta, segreteria):
        Seduta.objects.filter(pk=seduta.pk).update(costituita=None)
        seduta.refresh_from_db()
        with pytest.raises(ValidationError):
            votazioni.apri_votazione(seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="X")

    def test_solo_gestori_e_operatori(self, seduta):
        capo = Utente.objects.create(username="capo", email="c@example.it")
        with pytest.raises(PermissionDenied):
            votazioni.apri_votazione(seduta, capo, tipo=TipoVotazione.MOZIONE, oggetto="X")

    def test_annulla_solo_prima_dei_risultati(self, seduta, segreteria):
        v = votazioni.apri_votazione(seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="X")
        _palese(v, segreteria, 2, 1, 0)
        with pytest.raises(ValidationError):
            votazioni.annulla_votazione(v, segreteria)


def test_soglie_correnti():
    assert votazioni.soglie_correnti(120, 186) == {
        "deliberazioni": 61,
        "elezioni": 61,
        "revoca": 94,
    }


def test_flusso_dalle_pagine(client, seduta, segreteria):
    client.force_login(segreteria)
    base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/votazioni/"
    client.post(f"{base}nuova/", {"tipo": TipoVotazione.MOZIONE, "oggetto": "Bilancio", "posti": 1})
    v = Votazione.objects.get()
    client.post(
        f"{base}{v.pk}/",
        {"PALESE_favorevoli": 2, "PALESE_contrari": 1, "PALESE_astenuti": 0},
    )
    v.refresh_from_db()
    assert v.chiusa
    assert votazioni.esito(v).approvata
    pagina = client.get(base)
    assert "Approvata con 2 voti favorevoli" in pagina.content.decode()


def _verifica(seduta, utente, codici):
    sedute.apri_verifica(seduta, RichiedenteVerifica.COMITATO, utente)
    for codice in codici:
        sedute.registra_presenza(
            seduta, seduta.assemblea.aventi_diritto.get(codice_socio=codice), utente
        )
    return sedute.chiudi_verifica(seduta, utente)


class TestVerificaDelQuorum:
    def test_quorum_venuto_meno_chiude_la_seduta(self, seduta, segreteria):
        prima = votazioni.apri_votazione(
            seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Prima"
        )
        _palese(prima, segreteria, 2, 1, 0)
        assert not _verifica(seduta, segreteria, ["0"]).quorum_raggiunto
        seduta.refresh_from_db()
        assert not seduta.aperta
        with pytest.raises(ValidationError):
            votazioni.apri_votazione(seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="X")
        # Art. 4 c.6: quanto fatto prima della verifica resta valido.
        assert votazioni.esito(prima).approvata

    def test_verifica_confermata_cambia_la_maggioranza(self, seduta, segreteria):
        _verifica(seduta, segreteria, ["0", "1", "2", "3"])
        seduta.refresh_from_db()
        assert seduta.aperta
        v = votazioni.apri_votazione(seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="X")
        assert v.presenti == 4
        assert _palese(v, segreteria, 2, 2, 0).soglia == 3


class TestRisultatiDaProiettare:
    def test_solo_elezioni_chiuse_al_massimo_tre(self, seduta, segreteria):
        chiuse = []
        for nome in ("Anna", "Bruno", "Carla", "Dario"):
            v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=[nome, "Zeta"])
            _elezione(v, segreteria, {nome: 70, "Zeta": 40})
            chiuse.append(v)
        aperta = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Ugo"])
        mozione = _palese(_votazione(seduta, TipoVotazione.MOZIONE), segreteria, 70, 10, 0)
        assert mozione.approvata
        assert votazioni.proiettabili(seduta) == chiuse
        assert votazioni.da_proiettare(seduta, [chiuse[0].pk, chiuse[2].pk]) == [
            chiuse[0],
            chiuse[2],
        ]
        with pytest.raises(ValidationError, match="al massimo 3"):
            votazioni.da_proiettare(seduta, [v.pk for v in chiuse])
        with pytest.raises(ValidationError):
            votazioni.da_proiettare(seduta, [aperta.pk])
        with pytest.raises(ValidationError):
            votazioni.da_proiettare(seduta, [])

    def test_pagina_con_voti_ed_eletti(self, client, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna", "Bruno", "Carla"])
        _elezione(v, segreteria, {"Anna": 55, "Bruno": 50, "Carla": 10}, bianche=3)
        risultati = votazioni.risultati_per_proiettore(v)
        assert [c["nome"] for c in risultati["candidati"]] == ["Anna", "Bruno", "Carla"]
        assert risultati["vacanti"] == "ballottaggio fra Anna e Bruno"
        client.force_login(segreteria)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}"
        assert "Proietta i risultati" in client.get(f"{base}/votazioni/").content.decode()
        pagina = client.get(f"{base}/proiettore/risultati/?v={v.pk}").content.decode()
        assert "Carla" in pagina and "Ballottaggio fra Anna e Bruno" in pagina
        eletta = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Dora", "Ezio"])
        _elezione(eletta, segreteria, {"Dora": 70, "Ezio": 40})
        pagina = client.get(f"{base}/proiettore/risultati/?v={v.pk}&v={eletta.pk}").content.decode()
        assert pagina.count('id="mdi-crown"') == 1 and "Dora" in pagina
        # Una votazione non proiettabile riporta all'elenco.
        assert client.get(f"{base}/proiettore/risultati/?v=999999").status_code == 302


class TestPuntoOdG:
    def test_si_collega_anche_a_votazione_chiusa(self, client, seduta, segreteria):
        from apps.assemblee.models import Assemblea, PuntoOdG

        punto = PuntoOdG.objects.create(assemblea=seduta.assemblea, ordine=1, titolo="Bilancio")
        v = _palese(
            votazioni.apri_votazione(
                seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Bilancio"
            ),
            segreteria,
            3,
            0,
            0,
        )
        votazione = seduta.votazioni.get()
        assert v.approvata and votazione.chiusa
        client.force_login(segreteria)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/votazioni/{votazione.pk}/"
        assert 'name="punto"' in client.get(base).content.decode()
        client.post(base + "azione/", {"azione": "punto", "punto": punto.pk})
        votazione.refresh_from_db()
        assert votazione.punto == punto
        client.post(base + "azione/", {"azione": "punto", "punto": ""})
        votazione.refresh_from_db()
        assert votazione.punto is None

        altra = Assemblea.objects.create(tipo=seduta.assemblea.tipo, anno_scout=2028)
        estraneo = PuntoOdG.objects.create(assemblea=altra, ordine=1, titolo="Altro")
        with pytest.raises(ValidationError):
            votazioni.collega_punto(votazione, segreteria, estraneo)
        capo = Utente.objects.create(username="capo-punto", email="cp@example.it")
        with pytest.raises(PermissionDenied):
            votazioni.collega_punto(votazione, capo, punto)


class TestPalese:
    def test_approvata_palese(self, client, seduta, segreteria):
        v = votazioni.apri_votazione(
            seduta, segreteria, tipo=TipoVotazione.MOZIONE, oggetto="Mozione"
        )
        client.force_login(segreteria)
        base = f"/assemblee/{seduta.assemblea_id}/sedute/{seduta.pk}/votazioni/{v.pk}/"
        assert 'value="palese"' in client.get(base).content.decode()
        client.post(base + "azione/", {"azione": "palese"})
        v.refresh_from_db()
        assert v.chiusa and v.esito_palese
        esito = votazioni.esito(v)
        assert esito.approvata and esito.totali.favorevoli == v.presenti
        assert esito.totali.contrari == esito.totali.astenuti == 0
        assert votazioni.frase_esito(v).startswith("Approvata a voto palese")

    def test_non_per_le_segrete(self, seduta, segreteria):
        v = _votazione(seduta, TipoVotazione.ELEZIONE, candidati=["Anna"])
        with pytest.raises(ValidationError):
            votazioni.registra_palese(v, segreteria)
        assert not v.chiusa
