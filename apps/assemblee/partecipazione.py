"""Statistiche di partecipazione dei gruppi alle assemblee (decisioni di
Andrea del 23/11/2026).

Unico punto del calcolo: la pagina dell'assemblea conclusa e la serie storica
lo chiamano, non lo reimplementano. Le presenze vengono da quorum.py:

- la seduta di riferimento è quella in cui si sono svolti i lavori (la
  costituita), altrimenti l'ultima convocazione;
- presente = presente **a fine lavori**, cioè nell'appello effettivo
  dell'ultimo momento (ingresso o ultima verifica del quorum chiusa), di
  persona o per delega (art. 4 c.2), con i presenti per delega contati anche
  a parte;
- il gruppo è quello attuale nell'elenco (dopo eventuali trasferimenti);
- il Comitato di Zona è una riga a parte: conta nel totale di Zona, non fra i
  gruppi rappresentati.

La serie storica conta solo le assemblee vere (non di prova) e concluse."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts.models import Utente
from apps.core.pdf import contesto_carta_intestata
from apps.organizzazione.models import Gruppo

from .models import Assemblea, AventeDiritto, Seduta, Sesso
from .permessi import puo_gestire_assemblee
from .quorum import appello_effettivo, presenti_nell_appello


def percentuale(parte: int, totale: int) -> Decimal | None:
    """Rapporto in percentuale con un decimale; None se non c'è nessun avente."""
    if not totale:
        return None
    return (Decimal(parte) * 100 / Decimal(totale)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class Conteggio:
    aventi_diritto: int = 0
    presenti: int = 0
    per_delega: int = 0
    maschi: int = 0
    femmine: int = 0
    sesso_non_noto: int = 0

    @property
    def percentuale(self) -> Decimal | None:
        return percentuale(self.presenti, self.aventi_diritto)

    @property
    def rappresentato(self) -> bool:
        return self.presenti > 0

    def somma(self, altro: Conteggio) -> None:
        for campo in (
            "aventi_diritto",
            "presenti",
            "per_delega",
            "maschi",
            "femmine",
            "sesso_non_noto",
        ):
            setattr(self, campo, getattr(self, campo) + getattr(altro, campo))


@dataclass(frozen=True)
class PresenteNominativo:
    """Per il solo PDF dell'assemblea (la serie storica non ha nomi)."""

    avente: AventeDiritto
    # Per un AE presente per delega: chi lo rappresentava.
    delegato: AventeDiritto | None = None


@dataclass
class RigaGruppo:
    gruppo: Gruppo
    conteggio: Conteggio
    presenti: list[PresenteNominativo] = field(default_factory=list)


@dataclass
class Partecipazione:
    assemblea: Assemblea
    seduta: Seduta | None
    gruppi: list[RigaGruppo]
    comitato: RigaGruppo | None
    totale: Conteggio

    @property
    def gruppi_rappresentati(self) -> int:
        return sum(1 for r in self.gruppi if r.conteggio.rappresentato)


def seduta_di_riferimento(assemblea: Assemblea) -> Seduta | None:
    """La seduta in cui si sono svolti i lavori: la costituita (al più una:
    la convocazione successiva si crea solo dopo una seduta senza quorum),
    altrimenti l'ultima convocazione."""
    sedute = list(assemblea.sedute.all())
    costituita = next((s for s in sedute if s.costituita), None)
    if costituita is not None:
        return costituita
    return max(sedute, key=lambda s: s.convocazione, default=None)


def verifica_disponibile(assemblea: Assemblea) -> None:
    """Le statistiche di un'assemblea si vedono solo da conclusa: prima le
    presenze possono ancora cambiare."""
    if not assemblea.conclusa:
        raise ValidationError(
            "Le statistiche di partecipazione sono disponibili quando l'assemblea è conclusa."
        )


def partecipazione(assemblea: Assemblea) -> Partecipazione:
    """Aventi diritto e presenti a fine lavori, gruppo per gruppo."""
    seduta = seduta_di_riferimento(assemblea)
    appello = appello_effettivo(seduta) if seduta is not None else None
    presenti: set[int] = set()
    di_persona: set[int] = set()
    if appello is not None:
        presenti = set(presenti_nell_appello(appello).values_list("pk", flat=True))
        di_persona = set(
            assemblea.aventi_diritto.nell_elenco()
            .filter(presenze__appello=appello)
            .values_list("pk", flat=True)
        )

    delegati = (
        {d.delegante_id: d.delegato for d in seduta.deleghe.select_related("delegato")}
        if seduta is not None
        else {}
    )

    # Chiave: codice del gruppo (la sua chiave primaria).
    conteggi: dict[str, Conteggio] = defaultdict(Conteggio)
    nominativi: dict[str, list[PresenteNominativo]] = defaultdict(list)
    gruppi: dict[str, Gruppo] = {}
    aventi = assemblea.aventi_diritto.nell_elenco().select_related("gruppo")
    for avente in aventi.order_by("cognome", "nome"):
        gruppi[avente.gruppo_id] = avente.gruppo
        c = conteggi[avente.gruppo_id]
        c.aventi_diritto += 1
        if avente.pk not in presenti:
            continue
        c.presenti += 1
        delegato = None
        if avente.pk not in di_persona:
            c.per_delega += 1
            delegato = delegati.get(avente.pk)
        nominativi[avente.gruppo_id].append(PresenteNominativo(avente, delegato))
        if avente.sesso == Sesso.MASCHILE:
            c.maschi += 1
        elif avente.sesso == Sesso.FEMMINILE:
            c.femmine += 1
        else:
            c.sesso_non_noto += 1

    righe = sorted(
        (RigaGruppo(gruppi[pk], c, nominativi[pk]) for pk, c in conteggi.items()),
        key=lambda r: (r.gruppo.nome, r.gruppo.codice),
    )
    comitato = next((r for r in righe if r.gruppo.is_comitato_zona), None)
    totale = Conteggio()
    for riga in righe:
        totale.somma(riga.conteggio)
    return Partecipazione(
        assemblea=assemblea,
        seduta=seduta,
        gruppi=[r for r in righe if not r.gruppo.is_comitato_zona],
        comitato=comitato,
        totale=totale,
    )


# --- Serie storica ---------------------------------------------------------------


def assemblee_della_serie():
    """Solo le assemblee vere e concluse, dalla più vecchia."""
    return (
        Assemblea.objects.filter(di_prova=False, conclusa_il__isnull=False)
        .prefetch_related("sedute")
        .order_by("anno_scout", "conclusa_il")
    )


@dataclass
class RigaSerie:
    gruppo: Gruppo
    # Una cella per assemblea della serie, None se il gruppo non aveva
    # aventi diritto in quell'assemblea.
    celle: list[Conteggio | None]
    complessivo: Conteggio = field(default_factory=Conteggio)

    @property
    def assemblee_con_aventi(self) -> int:
        return sum(1 for c in self.celle if c is not None)

    @property
    def assemblee_rappresentato(self) -> int:
        return sum(1 for c in self.celle if c is not None and c.rappresentato)


@dataclass
class SerieStorica:
    assemblee: list[Partecipazione]
    gruppi: list[RigaSerie]
    comitato: RigaSerie | None

    @property
    def totali(self) -> list[Conteggio]:
        return [p.totale for p in self.assemblee]


def serie_storica() -> SerieStorica:
    """Partecipazione di ogni gruppo a ogni assemblea della serie. Il dato
    complessivo di un gruppo è il rapporto fra la somma dei presenti e la
    somma degli aventi diritto (non la media delle percentuali: un'assemblea
    con due aventi pesa meno di una con venti)."""
    assemblee = [partecipazione(a) for a in assemblee_della_serie()]
    gruppi: dict[str, Gruppo] = {}
    celle: dict[str, list[Conteggio | None]] = {}
    for indice, p in enumerate(assemblee):
        righe = p.gruppi + ([p.comitato] if p.comitato else [])
        for riga in righe:
            gruppi[riga.gruppo.pk] = riga.gruppo
            celle.setdefault(riga.gruppo.pk, [None] * len(assemblee))[indice] = riga.conteggio

    righe_serie = []
    for pk, valori in celle.items():
        riga_serie = RigaSerie(gruppo=gruppi[pk], celle=valori)
        for c in valori:
            if c is not None:
                riga_serie.complessivo.somma(c)
        righe_serie.append(riga_serie)
    righe_serie.sort(key=lambda r: (r.gruppo.nome, r.gruppo.codice))
    return SerieStorica(
        assemblee=assemblee,
        gruppi=[r for r in righe_serie if not r.gruppo.is_comitato_zona],
        comitato=next((r for r in righe_serie if r.gruppo.is_comitato_zona), None),
    )


# --- Grafico ---------------------------------------------------------------------

LARGHEZZA_GRAFICO = 640
ALTEZZA_GRAFICO = 220
MARGINE = {"sinistra": 44, "destra": 16, "alto": 16, "basso": 36}


@dataclass(frozen=True)
class PuntoGrafico:
    x: float
    y: float
    etichetta: str
    valore: Decimal

    @property
    def y_valore(self) -> float:
        return self.y - 8


def punti_grafico(serie: SerieStorica) -> list[PuntoGrafico]:
    """Coordinate SVG della percentuale di Zona per ciascuna assemblea della
    serie (asse y da 0 a 100%), per un grafico a linee senza librerie."""
    utili = [
        (p.assemblea, p.totale.percentuale)
        for p in serie.assemblee
        if p.totale.percentuale is not None
    ]
    larghezza = LARGHEZZA_GRAFICO - MARGINE["sinistra"] - MARGINE["destra"]
    altezza = ALTEZZA_GRAFICO - MARGINE["alto"] - MARGINE["basso"]
    punti = []
    for i, (assemblea, valore) in enumerate(utili):
        passo = larghezza / (len(utili) - 1) if len(utili) > 1 else 0
        x = MARGINE["sinistra"] + (i * passo if len(utili) > 1 else larghezza / 2)
        y = MARGINE["alto"] + altezza * (1 - float(valore) / 100)
        punti.append(PuntoGrafico(round(x, 1), round(y, 1), etichetta_breve(assemblea), valore))
    return punti


def etichetta_breve(assemblea: Assemblea) -> str:
    """Es. «Aut. 2026/27», per l'asse del grafico e le intestazioni della tabella."""
    tipo = assemblea.get_tipo_display()[:3]
    return f"{tipo}. {assemblea.anno_scout - 1}/{str(assemblea.anno_scout)[-2:]}"


@dataclass(frozen=True)
class Barra:
    etichetta: str
    y: float
    larghezza: float
    valore: Decimal | None
    presenti: int
    aventi_diritto: int

    @property
    def y_testo(self) -> float:
        return self.y + 11


@dataclass(frozen=True)
class GraficoBarre:
    barre: list[Barra]
    altezza: float
    # Posizione x della percentuale di Zona, linea di riferimento.
    x_zona: float | None
    valore_zona: Decimal | None
    x_inizio: float = 150
    larghezza_utile: float = 430
    altezza_barra: float = 14
    larghezza: float = LARGHEZZA_GRAFICO

    @property
    def x_etichette(self) -> float:
        return self.x_inizio - 6

    @property
    def x_valori(self) -> float:
        return self.x_inizio + self.larghezza_utile + 6

    @property
    def y_fine_linea(self) -> float:
        return self.altezza - 16

    @property
    def y_testo_zona(self) -> float:
        return self.altezza - 4


def barre_grafico(p: Partecipazione) -> GraficoBarre:
    """Barre orizzontali della percentuale di presenti per gruppo (Comitato di
    Zona in fondo), con la linea della percentuale di Zona."""
    righe = p.gruppi + ([p.comitato] if p.comitato else [])
    passo, alto = 22, 8
    inizio, utile = 150, 430
    barre = [
        Barra(
            etichetta=r.gruppo.nome,
            y=alto + i * passo,
            larghezza=round(utile * float(r.conteggio.percentuale or 0) / 100, 1),
            valore=r.conteggio.percentuale,
            presenti=r.conteggio.presenti,
            aventi_diritto=r.conteggio.aventi_diritto,
        )
        for i, r in enumerate(righe)
    ]
    zona = p.totale.percentuale
    return GraficoBarre(
        barre=barre,
        altezza=alto + len(barre) * passo + 20,
        x_zona=None if zona is None else round(inizio + utile * float(zona) / 100, 1),
        valore_zona=zona,
        x_inizio=inizio,
        larghezza_utile=utile,
    )


@dataclass(frozen=True)
class GraficoLinee:
    punti: list[PuntoGrafico]
    larghezza: int = LARGHEZZA_GRAFICO
    altezza: int = ALTEZZA_GRAFICO
    x_inizio: int = MARGINE["sinistra"]
    x_fine: int = LARGHEZZA_GRAFICO - MARGINE["destra"]

    @property
    def polilinea(self) -> str:
        return " ".join(f"{p.x},{p.y}" for p in self.punti)

    @property
    def griglia(self) -> list[tuple[int, float, float]]:
        """Linee orizzontali a 0, 25, 50, 75 e 100%: valore, y della linea, y
        dell'etichetta."""
        altezza = ALTEZZA_GRAFICO - MARGINE["alto"] - MARGINE["basso"]
        righe = []
        for v in range(0, 101, 25):
            y = round(MARGINE["alto"] + altezza * (1 - v / 100), 1)
            righe.append((v, y, y + 3))
        return righe

    @property
    def x_etichette(self) -> int:
        return self.x_inizio - 6

    @property
    def y_etichette_asse(self) -> int:
        return ALTEZZA_GRAFICO - MARGINE["basso"] + 16


def grafico_linee(serie: SerieStorica) -> GraficoLinee:
    return GraficoLinee(punti=punti_grafico(serie))


# --- PDF -------------------------------------------------------------------------

# Colonne di assemblee per tabella nel PDF della serie storica: oltre, la
# tabella prosegue in un blocco successivo (la pagina A4 verticale della carta
# intestata non ne contiene di più).
ASSEMBLEE_PER_TABELLA_PDF = 6


def _verifica_gestore(utente: Utente) -> None:
    if not puo_gestire_assemblee(utente):
        raise PermissionDenied


def genera_pdf_assemblea(assemblea: Assemblea, utente: Utente) -> bytes:
    from weasyprint import HTML

    _verifica_gestore(utente)
    verifica_disponibile(assemblea)
    p = partecipazione(assemblea)
    contesto = {
        "p": p,
        "assemblea": assemblea,
        "grafico": barre_grafico(p),
        "colore": "#5C5291",
        "generato_il": timezone.localtime(),
        **contesto_carta_intestata(),
    }
    html = render_to_string("assemblee/partecipazione_pdf.html", contesto)
    return HTML(string=html).write_pdf()


def genera_pdf_serie(utente: Utente) -> bytes:
    from weasyprint import HTML

    _verifica_gestore(utente)
    serie = serie_storica()
    n = ASSEMBLEE_PER_TABELLA_PDF
    blocchi = []
    for inizio in range(0, len(serie.assemblee), n):
        fine = inizio + n
        blocchi.append(
            {
                "assemblee": serie.assemblee[inizio:fine],
                "gruppi": [(r, r.celle[inizio:fine]) for r in serie.gruppi],
                "comitato": (
                    (serie.comitato, serie.comitato.celle[inizio:fine]) if serie.comitato else None
                ),
                "ultimo": fine >= len(serie.assemblee),
            }
        )
    contesto = {
        "serie": serie,
        "blocchi": blocchi,
        "grafico": grafico_linee(serie),
        "colore": "#5C5291",
        "generato_il": timezone.localtime(),
        **contesto_carta_intestata(),
    }
    html = render_to_string("assemblee/partecipazione_serie_pdf.html", contesto)
    return HTML(string=html).write_pdf()
