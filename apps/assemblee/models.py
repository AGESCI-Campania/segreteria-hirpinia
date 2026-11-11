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


class SistemaVoto(models.TextChoices):
    """Come si vota a scrutinio segreto (docs/plan_voto.md): con l'app del
    Nazionale (tracciato, risultati copiati a mano, D-70) o con il voto
    elettronico di Catello (`apps/voto`)."""

    NAZIONALE = "NAZIONALE", "App del Nazionale"
    CATELLO = "CATELLO", "Voto in app"


class ModalitaVoto(models.TextChoices):
    PERSONALE_E_SEGGIO = "PERSONALE_E_SEGGIO", "Dispositivi personali e seggi"
    SOLO_SEGGIO = "SOLO_SEGGIO", "Solo seggi"


class Assemblea(models.Model):
    tipo = models.CharField(max_length=20, choices=TipoAssemblea.choices)
    anno_scout = models.PositiveIntegerField(
        help_text="Anno associativo in cui si tiene l'assemblea (es. 2027 per il 2026/2027)."
    )
    sessione = models.CharField(
        max_length=20, choices=SessioneAssemblea.choices, default=SessioneAssemblea.ORDINARIA
    )
    # Si cambia solo fino all'apertura della prima votazione (apps/voto/sistema.py).
    sistema_voto = models.CharField(
        "Sistema di voto",
        max_length=10,
        choices=SistemaVoto.choices,
        default=SistemaVoto.NAZIONALE,
    )
    # Solo con il voto di Catello; modificabile anche il giorno stesso.
    modalita_voto = models.CharField(
        "Modalità di voto",
        max_length=20,
        choices=ModalitaVoto.choices,
        default=ModalitaVoto.PERSONALE_E_SEGGIO,
    )
    # Si sceglie solo alla creazione e non cambia più: solo un'assemblea di
    # prova si può eliminare del tutto (docs/plan_preparazione_assemblea.md, D22).
    di_prova = models.BooleanField(
        "Assemblea di prova",
        default=False,
        help_text=(
            "Per provare il voto o per votazioni ristrette: è indicata come «di prova» nelle "
            "pagine e nei PDF e si può eliminare del tutto. Non si può cambiare dopo."
        ),
    )
    # Solo per le assemblee di prova (D26): le email legate all'assemblea
    # (codici di voto, inviti) vanno sempre su Mailpit, mai al provider reale.
    email_solo_mailpit = models.BooleanField(
        "Email solo su Mailpit",
        default=False,
        help_text=(
            "Codici di voto e inviti di questa assemblea non arrivano ai destinatari: restano su "
            "Mailpit e si leggono dalla pagina dell'assemblea."
        ),
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
        constraints = [
            models.CheckConstraint(
                condition=Q(di_prova=True) | Q(email_solo_mailpit=False),
                name="email_solo_mailpit_solo_di_prova",
            )
        ]

    def __str__(self) -> str:
        nome = (
            f"Assemblea {self.get_tipo_display().lower()} {self.anno_scout - 1}/{self.anno_scout}"
        )
        return f"{nome} (di prova)" if self.di_prova else nome

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

    @property
    def voto_catello(self) -> bool:
        return self.sistema_voto == SistemaVoto.CATELLO


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
    # Fotografia alla dichiarazione dell'esito, per la frase sul quorum del verbale.
    costituita_il = models.DateTimeField(null=True, blank=True)
    aventi_alla_costituzione = models.PositiveIntegerField(null=True, blank=True)
    presenti_alla_costituzione = models.PositiveIntegerField(null=True, blank=True)
    presenti_app_alla_costituzione = models.PositiveIntegerField(null=True, blank=True)
    presenti_carta_alla_costituzione = models.PositiveIntegerField(null=True, blank=True)

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


class Sesso(models.TextChoices):
    """Sesso del capo nell'elenco: precompilato da `Capo.sesso`, correggibile
    nel modulo senza scrivere l'anagrafica (docs/plan_preparazione_assemblea.md,
    D6/D17). Vuoto se non noto."""

    MASCHILE = "M", "Maschile"
    FEMMINILE = "F", "Femminile"


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
    # Recapito per l'assemblea (tracciato, codice di voto): precompilato da
    # `capo.email` all'import, poi corretto qui (a mano, al banco o con l'Excel
    # dei capigruppo) senza mai scrivere l'anagrafica.
    email = models.EmailField(blank=True)
    # Email corretta nel modulo (a mano, al banco o con l'Excel dei capigruppo):
    # il riallineamento con l'anagrafica non la sovrascrive (D14).
    email_corretta = models.BooleanField(default=False)
    sesso = models.CharField(max_length=1, choices=Sesso.choices, blank=True)
    # Sesso corretto nel modulo: il riallineamento non lo sovrascrive (D17).
    sesso_corretto = models.BooleanField(default=False)
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
    """Componente del comitato elettorale di una sola assemblea (D-70): un
    avente diritto scelto da chi gestisce le assemblee. Con l'account
    (`utente`) registra presenze, deleghe e risultati, ma non modifica
    l'elenco; senza account compare solo nel verbale. Le righe precedenti al
    comitato elettorale hanno solo `utente`, senza `avente`."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="operatori")
    avente = models.ForeignKey(
        AventeDiritto,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="comitato_elettorale",
    )
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="operatore_assemblee",
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
        verbose_name = "componente del comitato elettorale"
        verbose_name_plural = "comitato elettorale"
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "utente"], name="operatore_unico_per_assemblea"
            ),
            models.UniqueConstraint(
                fields=["assemblea", "avente"], name="comitato_avente_unico_per_assemblea"
            ),
            models.CheckConstraint(
                condition=models.Q(avente__isnull=False) | models.Q(utente__isnull=False),
                name="comitato_avente_o_utente",
            ),
        ]

    def __str__(self) -> str:
        return self.nome_completo

    @property
    def nome_completo(self) -> str:
        if self.avente is not None:
            return f"{self.avente.cognome} {self.avente.nome}"
        assert self.utente is not None  # garantito dal vincolo comitato_avente_o_utente
        return self.utente.get_full_name() or str(self.utente)


class TipoFile(models.TextChoices):
    TRACCIATO_APP = "TRACCIATO_APP", "Tracciato per l'app di voto"
    FOGLIO_PRESENZE = "FOGLIO_PRESENZE", "Foglio presenze"
    EMAIL_GRUPPO = "EMAIL_GRUPPO", "Email degli aventi diritto per gruppo"


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


class ImportazioneEmail(models.Model):
    """Import dell'Excel delle email di un gruppo, compilato dal capogruppo:
    il report delle anomalie resta scaricabile. Il file non si conserva:
    contiene solo recapiti, già applicati agli aventi diritto."""

    assemblea = models.ForeignKey(
        Assemblea, on_delete=models.CASCADE, related_name="importazioni_email"
    )
    nome_file = models.CharField(max_length=255)
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    importata_il = models.DateTimeField(auto_now_add=True)
    righe_lette = models.PositiveIntegerField(default=0)
    email_aggiornate = models.PositiveIntegerField(default=0)
    # Elenco di {"riga", "avente", "messaggio", "bloccante"}.
    anomalie = models.JSONField(default=list)

    class Meta:
        verbose_name = "importazione delle email"
        verbose_name_plural = "importazioni delle email"
        ordering = ["-importata_il"]

    def __str__(self) -> str:
        return f"{self.nome_file} — {self.importata_il:%d/%m/%Y %H:%M}"


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


class RuoloAssemblea(models.TextChoices):
    """Ufficio di presidenza e comitati indicati in preparazione
    (docs/plan_preparazione_assemblea.md, R4)."""

    PRESIDENTE = "PRESIDENTE", "Presidente"
    SEGRETARIO = "SEGRETARIO", "Segretario"
    MOZIONI = "MOZIONI", "Comitato mozioni"
    SCRUTATORE = "SCRUTATORE", "Scrutatore"


# Quanti per ruolo (D-10/D10-bis: comitato mozioni sempre di tre, si raccoglie
# fino a tre; D11: due scrutatori; R4: al massimo due presidenti).
POSTI_RUOLO_ASSEMBLEA = {
    RuoloAssemblea.PRESIDENTE: 2,
    RuoloAssemblea.SEGRETARIO: 1,
    RuoloAssemblea.MOZIONI: 3,
    RuoloAssemblea.SCRUTATORE: 2,
}
# Ruoli che possono avere un accesso a Catello (D12): vedono risultati e
# ordine del giorno, compilano il verbale.
RUOLI_CON_ACCESSO = (RuoloAssemblea.PRESIDENTE, RuoloAssemblea.SEGRETARIO)


class IncaricoAssemblea(models.Model):
    """Un avente diritto nell'ufficio di presidenza o in un comitato
    dell'assemblea (R4). Si indica in preparazione e precompila il verbale di
    ogni seduta. Solo presidenti e segretario possono avere `utente`."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="incarichi")
    ruolo = models.CharField(max_length=15, choices=RuoloAssemblea.choices)
    avente = models.ForeignKey(
        AventeDiritto, on_delete=models.CASCADE, related_name="incarichi_assemblea"
    )
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incarichi_assemblea",
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
        verbose_name = "incarico dell'assemblea"
        verbose_name_plural = "incarichi dell'assemblea"
        ordering = ["assemblea", "ruolo", "nominato_il"]
        constraints = [
            models.UniqueConstraint(
                fields=["assemblea", "ruolo", "avente"], name="incarico_assemblea_unico"
            ),
            models.CheckConstraint(
                condition=Q(utente__isnull=True)
                | Q(ruolo__in=[RuoloAssemblea.PRESIDENTE, RuoloAssemblea.SEGRETARIO]),
                name="incarico_assemblea_accesso_solo_presidenza",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_ruolo_display()}: {self.avente}"


class PuntoOdG(models.Model):
    """Punto all'ordine del giorno dell'assemblea, con il testo della
    discussione per il verbale."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="punti_odg")
    ordine = models.PositiveSmallIntegerField()
    titolo = models.CharField(max_length=500)
    testo = models.TextField(blank=True)

    class Meta:
        verbose_name = "punto all'ordine del giorno"
        verbose_name_plural = "punti all'ordine del giorno"
        ordering = ["assemblea", "ordine"]

    def __str__(self) -> str:
        return f"{self.ordine}. {self.titolo}"


class PosizioneVoto(models.Model):
    """Una posizione al voto preparata in anticipo (docs/plan_preparazione_
    assemblea.md, R1, D4): l'incarico da eleggere con i suoi posti, divisi in
    maschili, femminili e indifferenti, e le candidature man mano che
    arrivano. Il giorno dell'assemblea l'elezione si apre da qui
    (`votazioni.apri_votazione(posizione=...)`)."""

    assemblea = models.ForeignKey(Assemblea, on_delete=models.CASCADE, related_name="posizioni")
    incarico = models.CharField(max_length=200)
    punto = models.ForeignKey(
        "PuntoOdG", on_delete=models.SET_NULL, null=True, blank=True, related_name="posizioni"
    )
    posti_maschili = models.PositiveSmallIntegerField(default=0)
    posti_femminili = models.PositiveSmallIntegerField(default=0)
    posti_indifferenti = models.PositiveSmallIntegerField(default=0)
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "posizione al voto"
        verbose_name_plural = "posizioni al voto"
        ordering = ["assemblea", "creata_il"]
        constraints = [
            models.CheckConstraint(
                condition=Q(posti_maschili__gt=0)
                | Q(posti_femminili__gt=0)
                | Q(posti_indifferenti__gt=0),
                name="posizione_almeno_un_posto",
            )
        ]

    def __str__(self) -> str:
        return self.incarico

    @property
    def posti(self) -> int:
        return self.posti_maschili + self.posti_femminili + self.posti_indifferenti

    @property
    def con_quote(self) -> bool:
        return self.posti_maschili > 0 or self.posti_femminili > 0


class Candidatura(models.Model):
    """Candidatura arrivata per una posizione: un avente diritto dell'elenco
    (il sesso è quello dell'elenco, D6) oppure un nome scritto a mano, con il
    suo sesso se noto."""

    posizione = models.ForeignKey(
        PosizioneVoto, on_delete=models.CASCADE, related_name="candidature"
    )
    avente = models.ForeignKey(
        AventeDiritto, on_delete=models.CASCADE, null=True, blank=True, related_name="candidature"
    )
    nome = models.CharField(max_length=200, blank=True)
    sesso = models.CharField(max_length=1, choices=Sesso.choices, blank=True)
    arrivata_il = models.DateField("Arrivata il", null=True, blank=True)
    inserita_il = models.DateTimeField(auto_now_add=True)
    inserita_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "candidatura"
        verbose_name_plural = "candidature"
        ordering = ["posizione", "inserita_il"]
        constraints = [
            models.UniqueConstraint(
                fields=["posizione", "avente"],
                condition=Q(avente__isnull=False),
                name="candidatura_unica_per_avente",
            ),
            models.CheckConstraint(
                condition=Q(avente__isnull=False) | ~Q(nome=""),
                name="candidatura_avente_o_nome",
            ),
        ]

    def __str__(self) -> str:
        return self.nome_completo

    @property
    def nome_completo(self) -> str:
        if self.avente is not None:
            return f"{self.avente.cognome} {self.avente.nome}"
        return self.nome

    @property
    def sesso_effettivo(self) -> str:
        """Per un avente diritto vale il sesso dell'elenco (corretto lì se serve)."""
        return self.avente.sesso if self.avente is not None else self.sesso


class TipoVotazione(models.TextChoices):
    MOZIONE = "MOZIONE", "Mozione"
    RACCOMANDAZIONE = "RACCOMANDAZIONE", "Raccomandazione"
    BILANCIO = "BILANCIO", "Bilancio"
    REGOLAMENTO = "REGOLAMENTO", "Modifica del regolamento"
    ALTRA_DELIBERA = "ALTRA_DELIBERA", "Altra deliberazione"
    MOZIONE_ORDINE = "MOZIONE_ORDINE", "Mozione d'ordine"
    NUOVO_PUNTO_ODG = "NUOVO_PUNTO_ODG", "Inserimento di un punto all'ordine del giorno"
    ELEZIONE = "ELEZIONE", "Elezione"
    BALLOTTAGGIO = "BALLOTTAGGIO", "Ballottaggio"
    REVOCA = "REVOCA", "Revoca di un mandato"


# Votazioni a scrutinio segreto (art. 14 c.3, art. 19 c.3): risultati separati
# fra app e carta. Le altre sono palesi, per alzata di mano.
VOTAZIONI_SEGRETE = frozenset(
    {TipoVotazione.ELEZIONE, TipoVotazione.BALLOTTAGGIO, TipoVotazione.REVOCA}
)


class CanaleVoto(models.TextChoices):
    PALESE = "PALESE", "Alzata di mano"
    APP = "APP", "App"
    CARTA = "CARTA", "Carta"


class Votazione(models.Model):
    """Una votazione della seduta (D-70). Presenti e aventi diritto sono
    fotografati all'apertura: sono la base delle soglie (votazioni.py)."""

    seduta = models.ForeignKey(Seduta, on_delete=models.CASCADE, related_name="votazioni")
    punto = models.ForeignKey(
        PuntoOdG, on_delete=models.SET_NULL, null=True, blank=True, related_name="votazioni"
    )
    tipo = models.CharField(max_length=20, choices=TipoVotazione.choices)
    oggetto = models.CharField(max_length=500)
    # Solo elezioni e ballottaggi.
    incarico = models.CharField(max_length=200, blank=True)
    posti = models.PositiveSmallIntegerField(default=1)
    # Quote per sesso (D4): i posti non maschili né femminili sono indifferenti.
    posti_maschili = models.PositiveSmallIntegerField(default=0)
    posti_femminili = models.PositiveSmallIntegerField(default=0)
    posizione = models.ForeignKey(
        PosizioneVoto, on_delete=models.SET_NULL, null=True, blank=True, related_name="votazioni"
    )
    ballottaggio_di = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="ballottaggi"
    )
    presenti = models.PositiveIntegerField()
    aventi_diritto = models.PositiveIntegerField()
    aperta_il = models.DateTimeField(auto_now_add=True)
    aperta_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    chiusa_il = models.DateTimeField(null=True, blank=True)
    # Urna elettronica (voto di Catello, apps/voto): aperta e chiusa a parte
    # rispetto alla votazione, che si chiude solo con i risultati registrati.
    aperta_in_app_il = models.DateTimeField(null=True, blank=True)
    chiusa_in_app_il = models.DateTimeField(null=True, blank=True)
    # SHA-256 dell'elenco ordinato delle schede pubblicato in bacheca: va nel verbale.
    hash_bacheca = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "votazione"
        verbose_name_plural = "votazioni"
        ordering = ["seduta", "aperta_il"]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()}: {self.oggetto}"

    @property
    def segreta(self) -> bool:
        return self.tipo in VOTAZIONI_SEGRETE

    @property
    def chiusa(self) -> bool:
        return self.chiusa_il is not None

    @property
    def urna_aperta(self) -> bool:
        return (
            self.aperta_in_app_il is not None
            and self.chiusa_in_app_il is None
            and self.chiusa_il is None
        )


class RisultatoCanale(models.Model):
    """Voti espressi in un canale: alzata di mano per le palesi, app e carta
    per le segrete. Per le elezioni favorevoli/contrari/astenuti non si usano:
    i voti stanno sui candidati."""

    votazione = models.ForeignKey(Votazione, on_delete=models.CASCADE, related_name="risultati")
    canale = models.CharField(max_length=10, choices=CanaleVoto.choices)
    favorevoli = models.PositiveIntegerField(default=0)
    contrari = models.PositiveIntegerField(default=0)
    astenuti = models.PositiveIntegerField(default=0)
    bianche = models.PositiveIntegerField(default=0)
    nulle = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "risultato per canale"
        verbose_name_plural = "risultati per canale"
        constraints = [
            models.UniqueConstraint(fields=["votazione", "canale"], name="un_risultato_per_canale")
        ]

    def __str__(self) -> str:
        return f"{self.votazione} — {self.get_canale_display()}"


class Candidato(models.Model):
    votazione = models.ForeignKey(Votazione, on_delete=models.CASCADE, related_name="candidati")
    # Collegato all'elenco quando possibile (serve al verbale del rappresentante
    # legale), altrimenti solo il nome.
    avente = models.ForeignKey(
        AventeDiritto, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    nome = models.CharField(max_length=200)
    # Copiato all'apertura (dall'elenco o dalla candidatura): serve alle quote.
    sesso = models.CharField(max_length=1, choices=Sesso.choices, blank=True)
    voti_app = models.PositiveIntegerField(default=0)
    voti_carta = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "candidato"
        verbose_name_plural = "candidati"
        ordering = ["votazione", "nome"]

    def __str__(self) -> str:
        return self.nome

    @property
    def voti(self) -> int:
        return self.voti_app + self.voti_carta


class VerbaleSeduta(models.Model):
    """Dati del verbale dell'assemblea (modello nazionale) per la seduta
    costituita: ufficio di presidenza, orari e firmatari. I nomi sono testo:
    si scelgono fra i suggerimenti dell'elenco o si scrivono a mano."""

    seduta = models.OneToOneField(Seduta, on_delete=models.CASCADE, related_name="verbale")
    ora_apertura = models.TimeField(null=True, blank=True)
    ora_chiusura = models.TimeField(null=True, blank=True)
    luogo = models.CharField(max_length=255, blank=True)
    presidente = models.CharField(max_length=300, blank=True)
    # Il secondo presidente, se la presidenza è affidata a due persone (R4/D9).
    presidente_2 = models.CharField("Secondo presidente", max_length=300, blank=True)
    segretario = models.CharField(max_length=200, blank=True)
    scrutatore_1 = models.CharField(max_length=200, blank=True)
    scrutatore_2 = models.CharField(max_length=200, blank=True)
    comitato_mozioni = models.CharField(
        max_length=500, blank=True, help_text="I tre membri, separati da virgola."
    )
    # Uno o due: un posto di Responsabile di Zona può essere vacante.
    rdz_1 = models.CharField("Responsabile di Zona", max_length=200, blank=True)
    rdz_2 = models.CharField("Secondo Responsabile di Zona", max_length=200, blank=True)
    note_finali = models.TextField(
        blank=True, help_text="Testo libero prima della chiusura (es. dichiarazioni a verbale)."
    )
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "verbale della seduta"
        verbose_name_plural = "verbali delle sedute"

    def __str__(self) -> str:
        return f"Verbale — {self.seduta}"


class VariazioneRappresentante(models.Model):
    """Dati del verbale di variazione della rappresentanza legale (e
    dell'eventuale sede legale) della Zona, modello nazionale. Presidenza e
    firmatari sono quelli di VerbaleSeduta: è la stessa seduta. I dati del
    rappresentante si precompilano dall'anagrafica e restano modificabili."""

    seduta = models.OneToOneField(
        Seduta, on_delete=models.CASCADE, related_name="variazione_rappresentante"
    )
    ora_apertura = models.TimeField(null=True, blank=True)
    ora_chiusura = models.TimeField(null=True, blank=True)
    rappresentante = models.ForeignKey(
        AventeDiritto, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    cognome = models.CharField(max_length=100, blank=True)
    nome = models.CharField(max_length=100, blank=True)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    comune_nascita = models.CharField(max_length=100, blank=True)
    provincia_nascita = models.CharField(max_length=5, blank=True)
    data_nascita = models.DateField(null=True, blank=True)
    indirizzo = models.CharField(max_length=200, blank=True)
    civico = models.CharField(max_length=10, blank=True)
    cap = models.CharField(max_length=10, blank=True)
    comune_residenza = models.CharField(max_length=100, blank=True)
    provincia_residenza = models.CharField(max_length=5, blank=True)
    varia_sede = models.BooleanField("Variazione della sede legale", default=False)
    sede_indirizzo = models.CharField(max_length=200, blank=True)
    sede_civico = models.CharField(max_length=10, blank=True)
    sede_cap = models.CharField(max_length=10, blank=True)
    sede_comune = models.CharField(max_length=100, blank=True)
    sede_provincia = models.CharField(max_length=5, blank=True)
    varie = models.TextField("Varie ed eventuali", blank=True)
    aggiornato_il = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "variazione del rappresentante legale"
        verbose_name_plural = "variazioni del rappresentante legale"

    def __str__(self) -> str:
        return f"Variazione rappresentante legale — {self.seduta}"
