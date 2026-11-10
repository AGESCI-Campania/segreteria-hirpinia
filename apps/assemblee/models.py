"""Assemblee di Zona (D-70).

L'elenco degli aventi diritto (`AventeDiritto`) è una copia di lavoro propria
di ogni assemblea, mai l'anagrafica: il modulo non scrive `Capo`,
`CensimentoCapo` o `IncaricoUnita`. Un avente diritto può non avere codice
socio (capi da precensire in autunno) e la sua eliminazione dall'elenco non è
un'uscita dall'associazione (D-22)."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.anagrafica.models import BrancaUnita, FunzioneIncarico


class TipoAssemblea(models.TextChoices):
    AUTUNNALE = "AUTUNNALE", "Autunnale"
    PRIMAVERILE = "PRIMAVERILE", "Primaverile"


class SessioneAssemblea(models.TextChoices):
    ORDINARIA = "ORDINARIA", "Ordinaria"
    STRAORDINARIA = "STRAORDINARIA", "Straordinaria"


class Assemblea(models.Model):
    tipo = models.CharField(max_length=20, choices=TipoAssemblea.choices)
    anno_scout = models.PositiveIntegerField(
        help_text="Anno associativo in cui si tiene l'assemblea (es. 2027 per il 2026/2027)."
    )
    sessione = models.CharField(
        max_length=20, choices=SessioneAssemblea.choices, default=SessioneAssemblea.ORDINARIA
    )
    conclusa_il = models.DateTimeField(null=True, blank=True)
    creata_il = models.DateTimeField(auto_now_add=True)
    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "assemblea"
        verbose_name_plural = "assemblee"
        ordering = ["-anno_scout", "-creata_il"]

    def __str__(self) -> str:
        return (
            f"Assemblea {self.get_tipo_display().lower()} {self.anno_scout - 1}/{self.anno_scout}"
        )

    @property
    def anno_censimento_base(self) -> int:
        """Anno dei censiti da cui parte l'elenco (D-70): in autunno i
        censimenti dell'anno in corso non sono ancora completi, quindi vale
        l'anno precedente, salvo i gruppi che hanno già i dati dell'anno in
        corso (`elenco.anno_per_gruppo`)."""
        if self.tipo == TipoAssemblea.AUTUNNALE:
            return self.anno_scout - 1
        return self.anno_scout

    @property
    def conclusa(self) -> bool:
        return self.conclusa_il is not None


class Seduta(models.Model):
    """Una convocazione dell'assemblea (D-70): la 2ª e la 3ª esistono solo se la
    precedente non ha raggiunto il quorum costitutivo, ciascuna con data, luogo
    e presenze proprie."""

    class Convocazione(models.IntegerChoices):
        PRIMA = 1, "Prima convocazione"
        SECONDA = 2, "Seconda convocazione"
        TERZA = 3, "Terza convocazione"

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="sedute")
    convocazione = models.PositiveSmallIntegerField(choices=Convocazione.choices)
    data = models.DateField()
    ora = models.TimeField(null=True, blank=True)
    luogo = models.CharField(max_length=255, blank=True)
    # Apertura della registrazione delle presenze; esito sul quorum costitutivo
    # (null finché non dichiarato); chiusura: fine lavori, o subito se la
    # seduta non è costituita.
    aperta_il = models.DateTimeField(null=True, blank=True)
    costituita = models.BooleanField(null=True, blank=True)
    chiusa_il = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "seduta"
        verbose_name_plural = "sedute"
        ordering = ["assemblea", "convocazione"]
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "convocazione"], name="seduta_unica_per_convocazione"
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_convocazione_display()} del {self.data:%d/%m/%Y}"

    @property
    def aperta(self) -> bool:
        return self.aperta_il is not None and self.chiusa_il is None

    @property
    def senza_quorum(self) -> bool:
        """In terza convocazione l'assemblea è valida qualunque sia il numero
        dei presenti (art. 4 c.3)."""
        return self.convocazione == Seduta.Convocazione.TERZA


class TipoAppello(models.TextChoices):
    INGRESSO = "INGRESSO", "Registrazione all'ingresso"
    VERIFICA = "VERIFICA", "Verifica del quorum"


class RichiedenteVerifica(models.TextChoices):
    """Chi può chiedere la verifica del quorum (art. 4 c.5)."""

    PRESIDENZA = "PRESIDENZA", "Presidenza dell'Assemblea"
    GRUPPI = "GRUPPI", "Almeno 1/3 dei gruppi, tramite i capigruppo"
    COMITATO = "COMITATO", "Due membri del Comitato di Zona"
    CAPI = "CAPI", "Almeno 1/3 dei capi presenti"


class Appello(models.Model):
    """Una rilevazione dei presenti di una seduta (D-70): quella all'ingresso e
    ogni verifica del quorum. Le presenze si registrano sempre nell'ultimo
    appello; il quorum si calcola sull'ultimo appello valido (l'ingresso, o una
    verifica chiusa) — vedi `apps/assemblee/quorum.py`."""

    seduta = models.ForeignKey(Seduta, on_delete=models.CASCADE, related_name="appelli")
    numero = models.PositiveSmallIntegerField()
    tipo = models.CharField(max_length=10, choices=TipoAppello.choices)
    richiedente = models.CharField(max_length=15, choices=RichiedenteVerifica.choices, blank=True)
    aperto_il = models.DateTimeField(auto_now_add=True)
    aperto_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    chiuso_il = models.DateTimeField(null=True, blank=True)
    # Esito fotografato alla chiusura di una verifica (per il verbale).
    presenti_rilevati = models.PositiveIntegerField(null=True, blank=True)
    soglia = models.PositiveIntegerField(null=True, blank=True)
    quorum_raggiunto = models.BooleanField(null=True, blank=True)

    class Meta:
        verbose_name = "appello"
        verbose_name_plural = "appelli"
        ordering = ["seduta", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["seduta", "numero"], name="appello_unico_per_numero")
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} n. {self.numero}"


class Presenza(models.Model):
    appello = models.ForeignKey(Appello, on_delete=models.CASCADE, related_name="presenze")
    avente = models.ForeignKey("AventeDiritto", on_delete=models.CASCADE, related_name="presenze")
    registrata_il = models.DateTimeField(auto_now_add=True)
    registrata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "presenza"
        verbose_name_plural = "presenze"
        constraints = [models.UniqueConstraint(fields=["appello", "avente"], name="presenza_unica")]

    def __str__(self) -> str:
        return f"{self.avente} — {self.appello}"


class OrigineAvente(models.TextChoices):
    IMPORT = "IMPORT", "Dal censimento"
    MANUALE = "MANUALE", "Inserito a mano"


class Provenienza(models.TextChoices):
    PASSAGGIO_CLAN = "PASSAGGIO_CLAN", "Passaggio dal clan"
    NUOVO_INGRESSO = "NUOVO_INGRESSO", "Nuovo ingresso"
    RIENTRO = "RIENTRO", "Rientro"
    NON_NOTA = "NON_NOTA", "Non nota"


class MotivoUscita(models.TextChoices):
    ELIMINATO = "ELIMINATO", "Eliminato"
    NON_CENSITO = "NON_CENSITO", "Non più censito"


class AventeDirittoQuerySet(models.QuerySet):
    def nell_elenco(self):
        """Aventi diritto non eliminati: gli unici che contano per quorum,
        tracciato e foglio presenze."""
        return self.filter(eliminato_il__isnull=True)


class AventeDiritto(models.Model):
    assemblea = models.ForeignKey(
        Assemblea, on_delete=models.CASCADE, related_name="aventi_diritto"
    )
    # Collegamento all'anagrafica solo in lettura (recapiti per il tracciato,
    # dati del rappresentante legale): null per chi non ha codice socio.
    capo = models.ForeignKey(
        "anagrafica.Capo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    codice_socio = models.CharField(max_length=20, blank=True)
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    gruppo = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Gruppo attuale nell'elenco, dopo eventuali trasferimenti.",
    )
    gruppo_origine = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Gruppo del censimento di riferimento: è quello che va nel tracciato.",
    )
    origine = models.CharField(max_length=10, choices=OrigineAvente.choices)
    provenienza = models.CharField(max_length=20, choices=Provenienza.choices, blank=True)
    # Anno dei censiti (BuonaStrada) usato per il gruppo di questo capo: nelle
    # autunnali cambia gruppo per gruppo (D-70, autorizzazioni parziali).
    anno_censimento = models.PositiveIntegerField()
    # Calcolato da un solo punto del service layer (CLAUDE.md § Assemblee),
    # mai impostato a mano da una view.
    vota_in_app = models.BooleanField(default=False)
    # Passaggio a carta di un votante in app (D-70): va poi tolto dall'app
    # nazionale da chi la gestisce.
    voto_cartaceo_il = models.DateTimeField(null=True, blank=True)
    voto_cartaceo_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    uscita = models.CharField(max_length=15, choices=MotivoUscita.choices, blank=True)
    # Qualifiche per le deleghe (art. 5), segnate a mano da chi gestisce
    # l'elenco: l'AE di gruppo invece si ricava dagli incarichi (elenco.py).
    ae_zona = models.BooleanField("AE di Zona", default=False)
    rdz = models.BooleanField("Responsabile di Zona", default=False)
    comitato = models.BooleanField("Membro del Comitato di Zona", default=False)
    eliminato_il = models.DateTimeField(null=True, blank=True)
    eliminato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    creato_il = models.DateTimeField(auto_now_add=True)
    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    objects = AventeDirittoQuerySet.as_manager()

    class Meta:
        verbose_name = "avente diritto"
        verbose_name_plural = "aventi diritto"
        ordering = ["cognome", "nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "codice_socio"],
                condition=~Q(codice_socio=""),
                name="avente_codice_socio_unico_per_assemblea",
            ),
            # Un capo inserito a mano ha sempre la provenienza (anche "non nota").
            models.CheckConstraint(
                condition=Q(origine=OrigineAvente.IMPORT) | ~Q(provenienza=""),
                name="avente_manuale_con_provenienza",
            ),
            # Un solo AE di Zona per assemblea.
            models.UniqueConstraint(
                fields=["assemblea"],
                condition=Q(ae_zona=True),
                name="un_ae_di_zona_per_assemblea",
            ),
            # Uscito dall'elenco se e solo se ha un motivo di uscita.
            models.CheckConstraint(
                condition=(Q(eliminato_il__isnull=True) & Q(uscita=""))
                | (Q(eliminato_il__isnull=False) & ~Q(uscita="")),
                name="avente_uscita_coerente",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cognome} {self.nome}"

    @property
    def eliminato(self) -> bool:
        return self.eliminato_il is not None

    @property
    def passato_a_carta(self) -> bool:
        return self.voto_cartaceo_il is not None

    @property
    def trasferito(self) -> bool:
        return self.gruppo_origine_id is not None and self.gruppo_origine_id != self.gruppo_id


class IncaricoDichiarato(models.Model):
    """Incarico in unità dichiarato per un capo inserito a mano: facoltativo,
    solo informativo per l'assemblea (non è un `IncaricoUnita`)."""

    avente = models.ForeignKey(AventeDiritto, on_delete=models.CASCADE, related_name="incarichi")
    funzione = models.CharField(max_length=30, choices=FunzioneIncarico.choices)
    branca = models.CharField(max_length=15, choices=BrancaUnita.choices, blank=True)
    nome_unita = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "incarico dichiarato"
        verbose_name_plural = "incarichi dichiarati"

    def __str__(self) -> str:
        return self.get_funzione_display()


class OperatoreVoto(models.Model):
    """Utente incaricato delle operazioni di voto di una sola assemblea (D-70):
    registra presenze, deleghe e risultati, non modifica l'elenco."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="operatori")
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="operatore_assemblee"
    )
    nominato_il = models.DateTimeField(auto_now_add=True)
    nominato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "operatore di voto"
        verbose_name_plural = "operatori di voto"
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "utente"], name="operatore_unico_per_assemblea"
            )
        ]

    def __str__(self) -> str:
        return str(self.utente)


class TipoFile(models.TextChoices):
    TRACCIATO_APP = "TRACCIATO_APP", "Tracciato per l'app di voto"
    FOGLIO_PRESENZE = "FOGLIO_PRESENZE", "Foglio presenze"


class ScaricamentoFile(models.Model):
    """Traccia di ogni file scaricato (D-70): il tracciato contiene email e
    cellulari dei capi. Solo i metadati, mai il file, come gli export
    dell'anagrafica (D-23)."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="scaricamenti")
    tipo = models.CharField(max_length=20, choices=TipoFile.choices)
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    numero_righe = models.PositiveIntegerField()
    scaricato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "file scaricato"
        verbose_name_plural = "file scaricati"
        ordering = ["-scaricato_il"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} — {self.scaricato_il:%d/%m/%Y %H:%M}"


class DelegaAE(models.Model):
    """Delega di un AE a un altro avente diritto per una seduta (art. 5, D-70):
    si registra al banco seduta per seduta. Le regole sono in deleghe.py."""

    seduta = models.ForeignKey(Seduta, on_delete=models.CASCADE, related_name="deleghe")
    delegante = models.ForeignKey(
        AventeDiritto, on_delete=models.CASCADE, related_name="deleghe_date"
    )
    delegato = models.ForeignKey(
        AventeDiritto, on_delete=models.CASCADE, related_name="deleghe_ricevute"
    )
    registrata_il = models.DateTimeField(auto_now_add=True)
    registrata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "delega AE"
        verbose_name_plural = "deleghe AE"
        constraints = [
            models.UniqueConstraint(fields=["seduta", "delegante"], name="una_delega_per_ae"),
            # Nessuno raccoglie più di una delega (art. 5 c.2).
            models.UniqueConstraint(fields=["seduta", "delegato"], name="una_delega_per_delegato"),
            models.CheckConstraint(
                condition=~Q(delegante=models.F("delegato")), name="delega_non_a_se_stessi"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.delegante} → {self.delegato}"
