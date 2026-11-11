"""Votazioni (D-70): soglie ed esiti alla lettera dal regolamento dell'Assemblea.

Unico punto delle soglie (CLAUDE.md § Assemblee): view, cruscotto e verbali
chiamano `soglia()` ed `esito()`, non le reimplementano.

| Votazione                                   | Base                | Articolo   |
| ------------------------------------------- | ------------------- | ---------- |
| Mozione, raccomandazione, bilancio,         | presenti            | art. 14    |
| regolamento, altra deliberazione            |                     |            |
| Elezione (per candidato)                    | presenti            | art. 18    |
| Ballottaggio                                | presenti            | art. 18 c.4|
| Mozione d'ordine, nuovo punto all'OdG       | votanti (f + c + a) | art. 13    |
| Revoca di un mandato                        | aventi diritto      | art. 19 c.3|

La soglia è sempre `meta_piu_uno(base)` (quorum.py)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Utente

from .models import (
    AventeDiritto,
    CanaleVoto,
    Candidato,
    PosizioneVoto,
    RisultatoCanale,
    Seduta,
    TipoVotazione,
    Votazione,
)
from .permessi import puo_operare
from .quorum import meta_piu_uno, stato_quorum

BASE_PRESENTI = "presenti"
BASE_VOTANTI = "votanti"
BASE_AVENTI_DIRITTO = "aventi diritto"

VOTAZIONI_SU_VOTANTI = frozenset({TipoVotazione.MOZIONE_ORDINE, TipoVotazione.NUOVO_PUNTO_ODG})


def canali(votazione: Votazione) -> list[str]:
    """Canali in cui si registrano i voti: alzata di mano per le palesi, app e
    carta per le segrete. Il ballottaggio con l'app del Nazionale è solo su
    carta (limite di quell'app, non del regolamento); con il voto di Catello
    si vota anche in app (docs/plan_voto.md, V5)."""
    if votazione.tipo == TipoVotazione.BALLOTTAGGIO and not votazione.seduta.assemblea.voto_catello:
        return [CanaleVoto.CARTA]
    if votazione.segreta:
        return [CanaleVoto.APP, CanaleVoto.CARTA]
    return [CanaleVoto.PALESE]


@dataclass(frozen=True)
class Totali:
    favorevoli: int = 0
    contrari: int = 0
    astenuti: int = 0
    bianche: int = 0
    nulle: int = 0

    @property
    def votanti(self) -> int:
        """Art. 4 c.4: chi esprime il voto ed è presente; astenuti compresi."""
        return self.favorevoli + self.contrari + self.astenuti + self.bianche + self.nulle


def totali(votazione: Votazione) -> Totali:
    risultati = list(votazione.risultati.all())
    return Totali(
        favorevoli=sum(r.favorevoli for r in risultati),
        contrari=sum(r.contrari for r in risultati),
        astenuti=sum(r.astenuti for r in risultati),
        bianche=sum(r.bianche for r in risultati),
        nulle=sum(r.nulle for r in risultati),
    )


def soglia(votazione: Votazione) -> tuple[str, int, int]:
    """(nome della base, valore della base, soglia) per `votazione`."""
    if votazione.tipo == TipoVotazione.REVOCA:
        base_nome, base = BASE_AVENTI_DIRITTO, votazione.aventi_diritto
    elif votazione.tipo in VOTAZIONI_SU_VOTANTI:
        base_nome, base = BASE_VOTANTI, totali(votazione).votanti
    else:
        base_nome, base = BASE_PRESENTI, votazione.presenti
    return base_nome, base, meta_piu_uno(base)


def soglie_correnti(presenti: int, aventi_diritto: int) -> dict[str, int]:
    """Soglie per tipo di votazione sui numeri di questo momento, per cruscotto
    e proiettore: stessa tabella di `soglia()`. La mozione d'ordine dipende dai
    votanti, noti solo a votazione fatta, quindi non compare."""
    return {
        "deliberazioni": meta_piu_uno(presenti),
        "elezioni": meta_piu_uno(presenti),
        "revoca": meta_piu_uno(aventi_diritto),
    }


@dataclass
class Esito:
    base_nome: str
    base: int
    soglia: int
    totali: Totali
    # Votazioni sì/no.
    approvata: bool | None = None
    # Elezioni e ballottaggi.
    eletti: list[Candidato] = field(default_factory=list)
    posti_vacanti: int = 0
    ballottaggio_proposto: list[Candidato] = field(default_factory=list)


def esito(votazione: Votazione) -> Esito:
    base_nome, base, valore_soglia = soglia(votazione)
    risultato = Esito(base_nome, base, valore_soglia, totali(votazione))
    if votazione.tipo not in (TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO):
        risultato.approvata = risultato.totali.favorevoli >= valore_soglia
        return risultato

    candidati = sorted(votazione.candidati.all(), key=lambda c: c.voti, reverse=True)
    sopra = [c for c in candidati if c.voti >= valore_soglia]
    posti = votazione.posti
    eletti = sopra[:posti]
    # Parità sull'ultimo posto utile: nessuno dei pari è eletto (art. 18 c.3).
    if len(sopra) > posti and sopra[posti].voti == sopra[posti - 1].voti:
        pari = sopra[posti - 1].voti
        eletti = [c for c in eletti if c.voti > pari]
    risultato.eletti = eletti
    risultato.posti_vacanti = posti - len(eletti)

    if votazione.tipo == TipoVotazione.ELEZIONE and risultato.posti_vacanti:
        non_eletti = [c for c in candidati if c not in eletti]
        # Ballottaggio fra i due più votati non eletti; con un solo candidato
        # (o uno solo rimasto) niente ballottaggio: il posto resta vacante.
        if len(non_eletti) >= 2:
            risultato.ballottaggio_proposto = non_eletti[:2]
    return risultato


# --- Operazioni -------------------------------------------------------------------


def _verifica_operatore(utente: Utente, seduta: Seduta) -> None:
    if not puo_operare(utente, seduta.assemblea):
        raise PermissionDenied


def _verifica_seduta(seduta: Seduta) -> None:
    if not seduta.aperta or seduta.costituita is not True:
        raise ValidationError("Si vota solo in una seduta costituita e aperta.")


@transaction.atomic
def apri_votazione(
    seduta: Seduta,
    utente: Utente,
    *,
    tipo: str,
    oggetto: str,
    punto=None,
    incarico: str = "",
    posti: int = 1,
    candidati: Iterable[AventeDiritto | str] = (),
    posizione: PosizioneVoto | None = None,
) -> Votazione:
    """Apre una votazione fotografando presenti e aventi diritto in quel
    momento: sono la base delle soglie e non cambiano dopo. Con `posizione`
    è l'elezione preparata (R1): incarico, posti, quote per sesso e
    candidati vengono da lì, e gli argomenti relativi si ignorano."""
    _verifica_operatore(utente, seduta)
    _verifica_seduta(seduta)
    if posizione is not None:
        return _apri_da_posizione(seduta, utente, posizione, oggetto=oggetto, punto=punto)
    if tipo == TipoVotazione.BALLOTTAGGIO:
        raise ValidationError("Il ballottaggio si apre dall'esito di un'elezione.")
    if tipo not in TipoVotazione.values:
        raise ValidationError("Tipo di votazione non valido.")
    candidati = list(candidati)
    if tipo == TipoVotazione.ELEZIONE:
        if not incarico.strip():
            raise ValidationError("Indica l'incarico da eleggere.")
        if posti < 1:
            raise ValidationError("I posti da eleggere devono essere almeno uno.")
        if not candidati:
            raise ValidationError("Un'elezione ha almeno un candidato.")
    stato = stato_quorum(seduta)
    votazione = Votazione.objects.create(
        seduta=seduta,
        punto=punto,
        tipo=tipo,
        oggetto=oggetto.strip(),
        incarico=incarico.strip(),
        posti=posti if tipo == TipoVotazione.ELEZIONE else 1,
        presenti=stato.presenti,
        aventi_diritto=stato.aventi_diritto,
        aperta_da=utente,
    )
    _crea_candidati(votazione, candidati)
    return votazione


def _crea_candidati(votazione: Votazione, candidati: Iterable[AventeDiritto | str]) -> None:
    for candidato in candidati:
        if isinstance(candidato, AventeDiritto):
            nome = f"{candidato.cognome} {candidato.nome}"
            Candidato.objects.create(
                votazione=votazione, avente=candidato, nome=nome, sesso=candidato.sesso
            )
        elif candidato.strip():
            Candidato.objects.create(votazione=votazione, nome=candidato.strip())


def _apri_da_posizione(
    seduta: Seduta, utente: Utente, posizione: PosizioneVoto, *, oggetto: str, punto
) -> Votazione:
    # Lazy: candidature.py usa le regole di questo modulo.
    from .candidature import verifica_apribile

    if posizione.assemblea_id != seduta.assemblea_id:
        raise ValidationError("La posizione non è di questa assemblea.")
    candidature = verifica_apribile(posizione)
    stato = stato_quorum(seduta)
    votazione = Votazione.objects.create(
        seduta=seduta,
        punto=punto or posizione.punto,
        tipo=TipoVotazione.ELEZIONE,
        oggetto=(oggetto or "").strip() or f"Elezione: {posizione.incarico}",
        incarico=posizione.incarico,
        posti=posizione.posti,
        posti_maschili=posizione.posti_maschili,
        posti_femminili=posizione.posti_femminili,
        posizione=posizione,
        presenti=stato.presenti,
        aventi_diritto=stato.aventi_diritto,
        aperta_da=utente,
    )
    for candidatura in candidature:
        Candidato.objects.create(
            votazione=votazione,
            avente=candidatura.avente,
            nome=candidatura.nome_completo,
            sesso=candidatura.sesso_effettivo,
        )
    return votazione


@transaction.atomic
def registra_risultati(
    votazione: Votazione,
    utente: Utente,
    *,
    per_canale: Mapping[str, Mapping[str, int]],
    voti_candidati: Mapping[int, Mapping[str, int]] | None = None,
) -> Esito:
    """Registra i voti e chiude la votazione. `per_canale` ha una voce per
    ciascun canale della votazione (favorevoli, contrari, astenuti, bianche,
    nulle); `voti_candidati` mappa l'id del candidato su voti_app/voti_carta.
    I voti non possono superare i presenti fotografati all'apertura.

    Con il voto di Catello i voti in app non si inseriscono a mano: arrivano
    dallo scrutinio dell'urna (`apps/voto/scrutinio.conteggio()`), che blocca
    finché l'urna è aperta o restano nomi scritti da interpretare; quelli
    passati qui per il canale app si ignorano."""
    _verifica_operatore(utente, votazione.seduta)
    if votazione.chiusa:
        raise ValidationError("I risultati di questa votazione sono già registrati.")
    ammessi = canali(votazione)
    if set(per_canale) - set(ammessi):
        raise ValidationError("Canale di voto non previsto per questa votazione.")
    elezione = votazione.tipo in (TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO)
    dall_urna = None
    if votazione.seduta.assemblea.voto_catello and CanaleVoto.APP in ammessi:
        # Lazy: apps.voto dipende da questo modulo, non il contrario.
        from apps.voto import scrutinio

        dall_urna = scrutinio.conteggio(votazione)
        carta = voti_candidati or {}
        # Il conteggio può aver aggiunto candidati (nomi scritti attribuiti).
        voti_candidati = {
            c.pk: {
                "voti_app": dall_urna.voti.get(c.pk, 0),
                "voti_carta": carta.get(c.pk, {}).get("voti_carta", 0),
            }
            for c in votazione.candidati.all()
        }
    for canale in ammessi:
        dati = per_canale.get(canale, {})
        if dall_urna is not None and canale == CanaleVoto.APP:
            dati = {"bianche": dall_urna.bianche, "nulle": dall_urna.nulle}
        if elezione:
            dati = {"bianche": dati.get("bianche", 0), "nulle": dati.get("nulle", 0)}
        else:
            dati = {k: dati.get(k, 0) for k in ("favorevoli", "contrari", "astenuti")}
        if any(v < 0 for v in dati.values()):
            raise ValidationError("I voti non possono essere negativi.")
        RisultatoCanale.objects.create(votazione=votazione, canale=canale, **dati)
    if elezione:
        voti_candidati = voti_candidati or {}
        for candidato in votazione.candidati.all():
            voti = voti_candidati.get(candidato.pk, {})
            candidato.voti_app = voti.get("voti_app", 0) if CanaleVoto.APP in ammessi else 0
            candidato.voti_carta = voti.get("voti_carta", 0)
            if candidato.voti_app < 0 or candidato.voti_carta < 0:
                raise ValidationError("I voti non possono essere negativi.")
            candidato.save(update_fields=["voti_app", "voti_carta"])
    _verifica_coerenza(votazione)
    votazione.chiusa_il = timezone.now()
    votazione.save(update_fields=["chiusa_il"])
    if dall_urna is not None:
        scrutinio.pubblica_bacheca(votazione)
    return esito(votazione)


def _verifica_coerenza(votazione: Votazione) -> None:
    """Le schede o le alzate di mano non possono superare i presenti."""
    tot = totali(votazione)
    if votazione.tipo in (TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO):
        # Ogni candidato non può avere più voti dei presenti; le schede
        # bianche e nulle si sommano ai voti del candidato più votato solo in
        # un'elezione a un posto (una scheda, un voto).
        massimo = max((c.voti for c in votazione.candidati.all()), default=0)
        espressi = massimo + tot.bianche + tot.nulle if votazione.posti == 1 else massimo
    else:
        espressi = tot.votanti
    if espressi > votazione.presenti:
        raise ValidationError(
            f"I voti ({espressi}) superano i presenti all'apertura della votazione "
            f"({votazione.presenti})."
        )


@transaction.atomic
def apri_ballottaggio(votazione: Votazione, utente: Utente) -> Votazione:
    """Ballottaggio fra i due candidati proposti dall'esito dell'elezione
    (art. 18 c.3), per un posto: solo su carta con l'app del Nazionale, anche
    in app con il voto di Catello (`canali()`). Si fa un solo turno."""
    _verifica_operatore(utente, votazione.seduta)
    _verifica_seduta(votazione.seduta)
    if votazione.tipo != TipoVotazione.ELEZIONE or not votazione.chiusa:
        raise ValidationError("Il ballottaggio segue un'elezione già scrutinata.")
    if votazione.ballottaggi.exists():
        raise ValidationError("Il ballottaggio di questa elezione è già stato aperto.")
    proposti = esito(votazione).ballottaggio_proposto
    if len(proposti) < 2:
        raise ValidationError("Per questa elezione non è previsto il ballottaggio.")
    stato = stato_quorum(votazione.seduta)
    ballottaggio = Votazione.objects.create(
        seduta=votazione.seduta,
        punto=votazione.punto,
        tipo=TipoVotazione.BALLOTTAGGIO,
        oggetto=votazione.oggetto,
        incarico=votazione.incarico,
        posti=1,
        ballottaggio_di=votazione,
        presenti=stato.presenti,
        aventi_diritto=stato.aventi_diritto,
        aperta_da=utente,
    )
    for candidato in proposti:
        Candidato.objects.create(
            votazione=ballottaggio,
            avente=candidato.avente,
            nome=candidato.nome,
            sesso=candidato.sesso,
        )
    return ballottaggio


@transaction.atomic
def annulla_votazione(votazione: Votazione, utente: Utente) -> None:
    """Solo prima di registrare i risultati (aperta per errore)."""
    _verifica_operatore(utente, votazione.seduta)
    if votazione.chiusa:
        raise ValidationError("Una votazione con i risultati registrati non si annulla.")
    if votazione.aperta_in_app_il is not None:
        raise ValidationError("Una votazione con l'urna elettronica già aperta non si annulla.")
    votazione.delete()


def _voti(n: int, singolare: str, plurale: str) -> str:
    return f"{n} {singolare if n == 1 else plurale}"


def frase_esito(votazione: Votazione) -> str:
    """Esito in una frase, uguale nella pagina della votazione e nel verbale."""
    if not votazione.chiusa:
        return "Votazione in corso."
    e = esito(votazione)
    base = f"su {e.base} {e.base_nome}, soglia {e.soglia}"
    if e.approvata is not None:
        t = e.totali
        dettaglio = ", ".join(
            [
                _voti(t.favorevoli, "voto favorevole", "voti favorevoli"),
                _voti(t.contrari, "contrario", "contrari"),
                _voti(t.astenuti, "astenuto", "astenuti"),
            ]
        )
        verbo = "approvata" if e.approvata else "respinta"
        return f"{verbo.capitalize()} con {dettaglio} ({base})."
    candidati = sorted(votazione.candidati.all(), key=lambda c: (-c.voti, c.nome))
    voti = "; ".join(f"{c.nome} {_voti(c.voti, 'voto', 'voti')}" for c in candidati)
    parti = [f"Voti: {voti}"]
    if e.totali.bianche or e.totali.nulle:
        parti.append(f"schede bianche {e.totali.bianche}, nulle {e.totali.nulle}")
    if e.eletti:
        nomi = ", ".join(c.nome for c in e.eletti)
        parti.append(f"{'eletto' if len(e.eletti) == 1 else 'eletti'}: {nomi}")
    if e.posti_vacanti:
        if e.ballottaggio_proposto:
            nomi = " e ".join(c.nome for c in e.ballottaggio_proposto)
            parti.append(f"ballottaggio fra {nomi}")
        else:
            parti.append(f"{_voti(e.posti_vacanti, 'posto vacante', 'posti vacanti')}")
    return "; ".join(parti) + f" ({base})."
