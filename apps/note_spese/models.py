"""Modelli del modulo Nota Spese. F1: alberi di categorie di spesa e centri
di costo, budget annuale per centro di costo, e anagrafica delle località
usata dal calcolo del rimborso chilometrico (D-46, D-47, D-56). F2: testata
e righe della nota (D-44/D-45), evento (D-49), allegati (D-58) — la macchina
a stati vera e propria (transizioni con effetti di dominio) è F3, qui c'è
solo lo scheletro FSM, come già fatto per `Campagna` in M4."""

from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.db import models
from django_fsm import FSMField, FSMModelMixin, transition

from apps.organizzazione.iban import valida_iban


class TipoCalcolo(models.TextChoices):
    """Identificativo stabile del tipo di calcolo di una categoria di spesa
    (D-46): `CHILOMETRICO` va riconosciuto dal codice del calcolo rimborso
    (F4), non dedotto da `richiede_tratta` o da altri attributi
    d'anagrafica modificabili da interfaccia."""

    DOCUMENTALE = "DOCUMENTALE", "Documentale"
    CHILOMETRICO = "CHILOMETRICO", "Chilometrico"


class SottotipoChilometrico(models.TextChoices):
    """Identificativo stabile delle due sottocategorie auto con regole di
    calcolo diverse (D-53): non distinguibili da `nome` (anagrafica
    editabile) né da `richiede_tratta` (vero per entrambe). Vuoto per le
    categorie non chilometriche."""

    ANDATA_RITORNO = "ANDATA_RITORNO", "Auto andata e ritorno"
    ALTRO = "ALTRO", "Auto altri spostamenti"


class CategoriaSpesa(models.Model):
    """Nodo di un albero autoreferenziale a profondità libera (D-46). La
    struttura iniziale (Viaggio/Logistica/Altre spese con le sottocategorie
    di §5.2 dei requisiti) è popolata da una data migration idempotente."""

    nome = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="figli",
    )
    richiede_allegato = models.BooleanField(default=True)
    tipo_calcolo = models.CharField(
        max_length=20, choices=TipoCalcolo.choices, default=TipoCalcolo.DOCUMENTALE
    )
    sottotipo_chilometrico = models.CharField(
        max_length=20,
        choices=SottotipoChilometrico.choices,
        blank=True,
        help_text="Solo per tipo_calcolo=CHILOMETRICO (D-53): distingue andata/ritorno da altri spostamenti.",
    )
    richiede_tratta = models.BooleanField(default=False)
    richiede_descrizione = models.BooleanField(default=False)
    descrizione_obbligatoria = models.BooleanField(default=False)
    attivo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Categoria di spesa"
        verbose_name_plural = "Categorie di spesa"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "nome"], name="categoriaspesa_unica_per_genitore"
            )
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome

    def clean(self) -> None:
        if self.tipo_calcolo == TipoCalcolo.CHILOMETRICO and not self.sottotipo_chilometrico:
            raise ValidationError(
                {"sottotipo_chilometrico": "Obbligatorio per le categorie di tipo chilometrico."}
            )
        if self.tipo_calcolo != TipoCalcolo.CHILOMETRICO and self.sottotipo_chilometrico:
            raise ValidationError(
                {"sottotipo_chilometrico": "Va lasciato vuoto per le categorie non chilometriche."}
            )


class CentroCosto(models.Model):
    """Nodo di un albero autoreferenziale a profondità libera (D-47). Il
    budget non è un campo qui: è un modello separato (`BudgetCentroCosto`)
    perché il budget è annuale, non una proprietà stabile del nodo."""

    nome = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="figli",
    )
    attivo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Centro di costo"
        verbose_name_plural = "Centri di costo"
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "nome"], name="centrocosto_unico_per_genitore"
            )
        ]
        ordering = ["nome"]

    def __str__(self) -> str:
        return self.nome


class BudgetCentroCosto(models.Model):
    """Budget proprio di un centro di costo per un singolo anno associativo
    (D-47). Una nota imputata al nodo consuma solo questo budget: lo
    sforamento di un figlio non intacca quello del padre (calcolo di
    capienza aggregata a fini di reporting, non persistito qui — D-47)."""

    centro_costo = models.ForeignKey(
        CentroCosto, on_delete=models.PROTECT, related_name="budget_annuali"
    )
    anno_scout = models.IntegerField()
    importo = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Budget del centro di costo"
        verbose_name_plural = "Budget dei centri di costo"
        constraints = [
            models.UniqueConstraint(
                fields=["centro_costo", "anno_scout"], name="budget_unico_per_centro_e_anno"
            )
        ]
        ordering = ["-anno_scout", "centro_costo__nome"]

    def __str__(self) -> str:
        return f"{self.centro_costo.nome} {self.anno_scout}: {self.importo}"


class FasciaTariffaChilometrica(models.TextChoices):
    """Le tre fasce di D-52, identificate da un codice stabile (non dedotto
    da soglie hardcoded sparse nel codice)."""

    TRE_O_PIU = "TRE_O_PIU", "3 o più passeggeri"
    BREVE = "BREVE", "1 o 2 passeggeri, fino a 200 km"
    LUNGA = "LUNGA", "1 o 2 passeggeri, oltre 200 km"


class TariffaChilometrica(models.Model):
    """Tariffa €/km per fascia, con validità temporale (D-52): decisione
    presa con Andrea di tenerla in anagrafica, non costante nel codice,
    perché il regolamento AGESCI nazionale può cambiare. La tariffa
    applicabile a una riga è quella vigente alla **data della spesa**
    (`RigaSpesa.data`), non alla data di liquidazione — decisione presa con
    Andrea, 2026-09-16."""

    fascia = models.CharField(max_length=20, choices=FasciaTariffaChilometrica.choices)
    importo_km = models.DecimalField(max_digits=5, decimal_places=2)
    valida_dal = models.DateField()
    valida_al = models.DateField(null=True, blank=True, help_text="Vuoto se ancora in vigore.")

    class Meta:
        verbose_name = "Tariffa chilometrica"
        verbose_name_plural = "Tariffe chilometriche"
        ordering = ["fascia", "-valida_dal"]

    def __str__(self) -> str:
        fine = self.valida_al.isoformat() if self.valida_al else "in corso"
        return f"{self.fascia} {self.valida_dal.isoformat()}–{fine}: {self.importo_km} €/km"

    def clean(self) -> None:
        if self.valida_al is not None and self.valida_al < self.valida_dal:
            raise ValidationError({"valida_al": "Non può precedere la data di inizio validità."})
        sovrapposte = TariffaChilometrica.objects.filter(fascia=self.fascia).exclude(pk=self.pk)
        fine_propria = self.valida_al or datetime.date.max
        for altra in sovrapposte:
            fine_altra = altra.valida_al or datetime.date.max
            if altra.valida_dal <= fine_propria and self.valida_dal <= fine_altra:
                raise ValidationError(
                    "Il periodo di validità si sovrappone a un'altra tariffa della stessa fascia."
                )


class Localita(models.Model):
    """Anagrafica delle città usata dall'autocompletamento e dal calcolo
    del rimborso chilometrico (D-56). I comuni italiani sono popolati da
    una data migration a partire dall'elenco ISTAT (con centroide comunale
    come coordinate, calcolato dai confini amministrativi ufficiali: il
    CSV ISTAT dei codici comune non contiene lat/lon). Le località estere
    non hanno `codice_istat` e vengono create al primo geocoding riuscito
    (F4), non da questa migration."""

    nome = models.CharField(max_length=150)
    provincia = models.CharField(max_length=100, blank=True)
    codice_istat = models.CharField(max_length=6, unique=True, null=True, blank=True)
    estero = models.BooleanField(default=False)
    stato = models.CharField(max_length=100, blank=True)
    latitudine = models.DecimalField(max_digits=9, decimal_places=6)
    longitudine = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        verbose_name = "Località"
        verbose_name_plural = "Località"
        ordering = ["nome"]

    def __str__(self) -> str:
        return f"{self.nome} ({self.provincia})" if self.provincia else self.nome


class Evento(models.Model):
    """Entità strutturata creabile dal capo (D-49): non trovata in Catello
    (V-5), definita qui da zero. Un evento creato da un capo entra subito
    nell'elenco comune, `validato=False`: chi gestisce il flusso lo valida,
    corregge o fonde con un altro (fusione: F6, operazione transazionale nel
    service layer, non qui). Campi inferiti dal testo di D-49 — non c'è una
    tabella campi nei requisiti, a differenza di `NotaSpese` (D-44): da
    rivedere se in fase di interfaccia (F6) emerge un bisogno diverso."""

    nome = models.CharField(max_length=150)
    data_inizio = models.DateField()
    data_fine = models.DateField(null=True, blank=True)
    validato = models.BooleanField(default=False)
    creato_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventi_note_spese_creati",
    )
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Evento"
        verbose_name_plural = "Eventi"
        ordering = ["-data_inizio"]

    def __str__(self) -> str:
        return self.nome

    def clean(self) -> None:
        if self.data_fine and self.data_fine < self.data_inizio:
            raise ValidationError(
                {"data_fine": "La data di fine non può precedere la data di inizio."}
            )


class StatoNota(models.TextChoices):
    """Stati della macchina D-37. Le transizioni con effetti di dominio
    (permessi, D-38, D-39, D-40) sono F3: qui c'è solo il vocabolario."""

    BOZZA = "BOZZA", "Bozza"
    INVIATA = "INVIATA", "Inviata"
    IN_VERIFICA = "IN_VERIFICA", "In verifica"
    DA_INTEGRARE = "DA_INTEGRARE", "Da integrare"
    DA_CONFERMARE = "DA_CONFERMARE", "Da confermare"
    APPROVATA = "APPROVATA", "Approvata"
    AUTORIZZATA_RDZ = "AUTORIZZATA_RDZ", "Autorizzata RdZ"
    LIQUIDATA = "LIQUIDATA", "Liquidata"
    RESPINTA = "RESPINTA", "Respinta"
    ANNULLATA = "ANNULLATA", "Annullata"
    DECADUTA = "DECADUTA", "Decaduta"


class ModalitaPagamento(models.TextChoices):
    CONTANTI = "CONTANTI", "Contanti"
    BONIFICO = "BONIFICO", "Bonifico"


class NotaSpese(FSMModelMixin, models.Model):
    """Testata della nota spese (D-44): raggruppa più `RigaSpesa` riferite
    alla stessa occasione — un solo evento, un solo incarico, un solo centro
    di costo, un solo IBAN.

    **Trappola nota (D-41)**: `anno_contabilizzazione` resta `None` finché la
    nota non è liquidata. Non valorizzarlo qui né altrove fuori dalla
    transizione di liquidazione (F3).

    `numero`: assegnato — non qui, ma dalla transizione BOZZA→INVIATA in F3,
    non alla creazione. La tabella D-44 lo elenca come campo della testata
    ma non specifica quando si valorizza; l'ho dedotto dal fatto che
    `anno_spesa` (da cui dipende il formato AAAA/NNNN deciso con Andrea) è
    derivato dalle date delle righe, non ancora note quando la nota è
    ancora vuota in BOZZA — scostamento dichiarato, non deciso in silenzio."""

    numero = models.CharField(max_length=20, unique=True, null=True, blank=True)

    beneficiario = models.ForeignKey(
        "anagrafica.Capo", on_delete=models.PROTECT, related_name="note_spese_beneficiario"
    )
    compilatore = models.ForeignKey(
        "anagrafica.Capo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="note_spese_compilate",
        help_text="Valorizzato solo se diverso dal beneficiario (D-36).",
    )
    gruppo_censimento = models.ForeignKey(
        "organizzazione.Gruppo",
        on_delete=models.PROTECT,
        related_name="note_spese",
        help_text="Derivato da CensimentoCapo alla creazione, congelato (D-34/D-44).",
    )
    evento = models.ForeignKey(Evento, on_delete=models.PROTECT, related_name="note_spese")
    incarico = models.ForeignKey(
        "anagrafica.IncaricoUnita",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="note_spese",
    )
    incarico_altro = models.CharField(
        max_length=100,
        blank=True,
        help_text="Obbligatorio se 'incarico' è nullo (D-50).",
    )
    centro_costo = models.ForeignKey(
        "CentroCosto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="note_spese",
        help_text="Imputato da segreteria/RdZ, non alla creazione.",
    )
    stato = FSMField(default=StatoNota.BOZZA, choices=StatoNota.choices, protected=True)

    iban = models.CharField(max_length=34, blank=True)
    intestatario_iban = models.CharField(max_length=150, blank=True)
    modalita_pagamento = models.CharField(
        max_length=10, choices=ModalitaPagamento.choices, blank=True
    )
    data_pagamento = models.DateField(null=True, blank=True)
    riferimento_tracciabilita = models.CharField(max_length=100, blank=True)

    anno_spesa = models.IntegerField(
        null=True,
        blank=True,
        help_text="Derivato dalle date delle righe (D-41), ricalcolato dal service layer.",
    )
    anno_contabilizzazione = models.IntegerField(
        null=True,
        blank=True,
        help_text="Valorizzato solo alla transizione verso LIQUIDATA (D-41). Vedi trappola in docstring.",
    )

    nota_originale = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="derivate",
        help_text="Clonazione (D-43) o nota di integrazione (D-40).",
    )

    eliminata_il = models.DateTimeField(
        null=True, blank=True, help_text="Soft delete (§2): mai un delete reale da qui."
    )

    rilievo_riga = models.ForeignKey(
        "RigaSpesa",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="rilievi",
        help_text="Riga oggetto del rilievo in DA_INTEGRARE/DA_CONFERMARE (D-38).",
    )
    rilievo_nota = models.TextField(
        blank=True, help_text="Nota testuale del verificatore sul rilievo (D-38)."
    )
    rilievo_il = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp del rilievo: un nuovo allegato successivo sblocca DA_INTEGRARE (D-38).",
    )
    causale_respinta = models.TextField(
        blank=True,
        help_text=(
            "Motivazione del respingimento. Non specificata in una decisione D-xx per "
            "Nota Spese: obbligatoria per coerenza con lo stesso principio già applicato "
            "altrove in Catello, non un requisito testuale di questo modulo."
        ),
    )

    creata_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="note_spese_create",
    )
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nota spese"
        verbose_name_plural = "Note spese"
        ordering = ["-creata_il"]

    def __str__(self) -> str:
        return self.numero or f"Nota spese #{self.pk} (bozza)"

    def clean(self) -> None:
        errori: dict[str, str] = {}
        if not self.incarico_id and not self.incarico_altro:
            errori["incarico_altro"] = "Obbligatorio se non si seleziona un incarico strutturato."
        if self.compilatore_id and self.compilatore_id == self.beneficiario_id:
            errori["compilatore"] = "Va valorizzato solo se diverso dal beneficiario."
        if self.iban:
            try:
                valida_iban(self.iban)
            except ValidationError as errore:
                errori["iban"] = str(errore.message)
        if errori:
            raise ValidationError(errori)

    # Transizioni D-37: corpo intenzionalmente vuoto, stesso pattern di
    # `Campagna` in apps/contributi/models.py — permessi ed effetti collaterali
    # vivono in apps/note_spese/transizioni.py, mai qui.

    @transition(field=stato, source=StatoNota.BOZZA, target=StatoNota.INVIATA)
    def invia(self) -> None:
        """apps/note_spese/transizioni.py::invia_nota (assegna `numero`/`anno_spesa`)."""

    @transition(field=stato, source=StatoNota.INVIATA, target=StatoNota.IN_VERIFICA)
    def prendi_in_carico(self) -> None:
        """apps/note_spese/transizioni.py::prendi_in_carico."""

    @transition(field=stato, source=StatoNota.IN_VERIFICA, target=StatoNota.DA_INTEGRARE)
    def richiedi_integrazione(self) -> None:
        """apps/note_spese/transizioni.py::richiedi_integrazione (D-38)."""

    @transition(field=stato, source=StatoNota.IN_VERIFICA, target=StatoNota.DA_CONFERMARE)
    def richiedi_conferma(self) -> None:
        """apps/note_spese/transizioni.py::richiedi_conferma (D-38)."""

    @transition(field=stato, source=StatoNota.DA_INTEGRARE, target=StatoNota.IN_VERIFICA)
    def conferma_integrazione(self) -> None:
        """apps/note_spese/transizioni.py::conferma_integrazione — sblocca **solo**
        con un nuovo allegato (D-38), verificato nel service layer."""

    @transition(field=stato, source=StatoNota.DA_CONFERMARE, target=StatoNota.IN_VERIFICA)
    def conferma_correzione(self) -> None:
        """apps/note_spese/transizioni.py::conferma_correzione — sblocca con un
        semplice assenso del capo (D-38)."""

    @transition(field=stato, source=StatoNota.IN_VERIFICA, target=StatoNota.APPROVATA)
    def approva(self) -> None:
        """apps/note_spese/transizioni.py::approva."""

    @transition(field=stato, source=StatoNota.APPROVATA, target=StatoNota.AUTORIZZATA_RDZ)
    def autorizza_rdz(self) -> None:
        """apps/note_spese/transizioni.py::autorizza_rdz (D-35: SINGOLA/DOPPIA)."""

    @transition(
        field=stato,
        source=[StatoNota.APPROVATA, StatoNota.AUTORIZZATA_RDZ],
        target=StatoNota.LIQUIDATA,
    )
    def liquida(self) -> None:
        """apps/note_spese/transizioni.py::liquida — unica transizione che
        valorizza `anno_contabilizzazione` (D-41) ed è terminale (D-40)."""

    @transition(field=stato, source=StatoNota.IN_VERIFICA, target=StatoNota.RESPINTA)
    def respingi(self) -> None:
        """apps/note_spese/transizioni.py::respingi — causale obbligatoria."""

    @transition(
        field=stato, source=[StatoNota.BOZZA, StatoNota.INVIATA], target=StatoNota.ANNULLATA
    )
    def annulla(self) -> None:
        """apps/note_spese/transizioni.py::annulla — solo prima della presa in carico."""

    @transition(field=stato, source=StatoNota.BOZZA, target=StatoNota.DECADUTA)
    def decadi(self) -> None:
        """D-42: transizione di sistema, non manuale. Il task periodico che la
        invoca è F7, fuori dallo scopo di F3 — qui c'è solo la transizione."""


class RigaSpesa(models.Model):
    """Riga di spesa (D-44/D-45): l'importo non è un dato stabile per le
    categorie chilometriche (il calcolo vive nel service layer a livello di
    nota, F4) — qui è solo la colonna cache, popolata da F4 in poi."""

    nota = models.ForeignKey(NotaSpese, on_delete=models.CASCADE, related_name="righe")
    categoria = models.ForeignKey("CategoriaSpesa", on_delete=models.PROTECT, related_name="righe")
    data = models.DateField()
    descrizione = models.TextField(blank=True)

    tratta_testo = models.CharField(
        max_length=200,
        blank=True,
        help_text="Tratta da/a in testo libero (Treno/Nave, Aereo, Bus/Metro/Taxi).",
    )
    localita_partenza = models.ForeignKey(
        "Localita",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="righe_spesa_partenza",
        help_text="Solo categorie Auto (D-53): tratta strutturata per il calcolo distanza.",
    )
    localita_arrivo = models.ForeignKey(
        "Localita",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="righe_spesa_arrivo",
    )
    targa = models.CharField(max_length=15, blank=True)

    distanza_km = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True, help_text="D-54: congelata."
    )
    distanza_backend = models.CharField(max_length=30, blank=True)
    distanza_calcolata_il = models.DateTimeField(null=True, blank=True)
    distanza_corretta_km = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Correzione manuale del verificatore (D-54).",
    )

    importo = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Inserito per le categorie documentali, cache calcolata per le chilometriche (D-45).",
    )
    importo_originale = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "D-39: congelato alla prima correzione di 'importo' dopo l'invio della "
            "nota, mai più sovrascritto. Nullo se la riga non è mai stata corretta."
        ),
    )

    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Riga di spesa"
        verbose_name_plural = "Righe di spesa"
        ordering = ["nota", "data"]

    def __str__(self) -> str:
        return f"{self.categoria.nome} — {self.data} — {self.nota_id}"


class RigaSpesaPasseggero(models.Model):
    """Passeggero di una riga auto (D-53/D-57): capo strutturato oppure nome
    libero (voce 'Altro', stesso pattern di D-50 per l'incarico). Serve al
    controllo anti-doppione di F4, ma è struttura dati, non calcolo: per
    questo è qui in F2 (deciso con Andrea in questa sessione)."""

    riga = models.ForeignKey(RigaSpesa, on_delete=models.CASCADE, related_name="passeggeri")
    capo = models.ForeignKey(
        "anagrafica.Capo",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="passeggeri_note_spese",
    )
    nome_libero = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "Passeggero"
        verbose_name_plural = "Passeggeri"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capo__isnull=False) | ~models.Q(nome_libero=""),
                name="passeggero_capo_o_nome_libero",
            )
        ]

    def __str__(self) -> str:
        return self.nome_libero if self.capo_id is None else str(self.capo_id)


class Allegato(models.Model):
    """Giustificativo (D-58): relazione molti-a-molti con le righe — un
    documento cumulativo può coprire più righe, e più allegati possono
    coprire la stessa riga. Storage sull'alias dedicato `note_spese_allegati`
    (D-59, F5), non quello "default" del progetto: il backend si sostituisce
    da `NOTA_SPESE_ALLEGATI_STORAGE_BACKEND` senza toccare questo campo."""

    file = models.FileField(
        upload_to="allegati_note_spese/%Y/", storage=storages["note_spese_allegati"]
    )
    righe = models.ManyToManyField(RigaSpesa, related_name="allegati")
    caricato_da = models.ForeignKey(
        "accounts.Utente",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="allegati_note_spese_caricati",
    )
    caricato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Allegato"
        verbose_name_plural = "Allegati"
        ordering = ["-caricato_il"]

    def __str__(self) -> str:
        return self.file.name or f"Allegato #{self.pk}"


class GenereRdz(models.TextChoices):
    MASCHILE = "M", "Maschile"
    FEMMINILE = "F", "Femminile"


class AutorizzazioneRdz(models.Model):
    """Firma di un RdZ su una nota (D-35, caso `SINGOLA`/`DOPPIA`). `genere` è
    congelato al momento della firma leggendo l'email dell'utente contro
    `settings.NOTA_SPESE_RDZ_EMAIL_MASCHILE`/`_FEMMINILE` (deciso con Andrea:
    account funzionali, mai condivisi, un solo titolare alla volta per
    casella) — non ricalcolato più tardi, così resta corretto anche se in
    futuro l'account cambia titolare. `unique_together` impedisce due firme
    dello stesso genere sulla stessa nota (necessario per `DOPPIA`: serve
    esattamente una firma M e una F, non due qualsiasi)."""

    nota = models.ForeignKey(
        "NotaSpese", on_delete=models.CASCADE, related_name="autorizzazioni_rdz"
    )
    utente = models.ForeignKey(
        "accounts.Utente", on_delete=models.PROTECT, related_name="autorizzazioni_rdz_firmate"
    )
    genere = models.CharField(max_length=1, choices=GenereRdz.choices)
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Autorizzazione RdZ"
        verbose_name_plural = "Autorizzazioni RdZ"
        constraints = [
            models.UniqueConstraint(
                fields=["nota", "genere"], name="autorizzazione_rdz_unica_per_genere"
            )
        ]
        ordering = ["-creata_il"]

    def __str__(self) -> str:
        return f"{self.nota_id}: {self.get_genere_display()} — {self.utente_id}"


class AutorizzazioneRdzConfig(models.TextChoices):
    NESSUNA = "NESSUNA", "Nessuna (la segreteria chiude autonomamente)"
    SINGOLA = "SINGOLA", "Singola (un RdZ qualsiasi)"
    DOPPIA = "DOPPIA", "Doppia (un RdZ maschile e uno femminile)"


class GiornoSettimana(models.IntegerChoices):
    """D-64: stessa convenzione di `promemoria.py` (`date.weekday()`,
    0=lunedì) — non i valori ISO (dove lunedì è 1), per restare coerenti
    con l'unico altro punto del modulo che ragiona per giorno della
    settimana."""

    LUNEDI = 0, "Lunedì"
    MARTEDI = 1, "Martedì"
    MERCOLEDI = 2, "Mercoledì"
    GIOVEDI = 3, "Giovedì"
    VENERDI = 4, "Venerdì"
    SABATO = 5, "Sabato"
    DOMENICA = 6, "Domenica"


class ImpostazioniNoteSpese(models.Model):
    """Impostazioni di sistema del modulo (D-35/D-64), singleton — stesso
    pattern di `ImpostazioniPiattaforma` in `apps.core`, ma dedicato a
    questo modulo invece di allargare quello generico. Modificabile da
    admin e RdZ (`permessi.py::puo_modificare_impostazioni`): il controllo
    di accesso è nella view (F6/F7), non qui."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    autorizzazione_rdz = models.CharField(
        max_length=10,
        choices=AutorizzazioneRdzConfig.choices,
        default=AutorizzazioneRdzConfig.NESSUNA,
    )

    # D-64: report periodico ai gestori. Vuoto/nullo = disattivato — nessun
    # flag "attivo" a parte, sarebbe uno stato incoerente esprimibile in più
    # modi (attivo=True ma giorni vuoti?).
    report_giorni_settimana = models.JSONField(
        default=list,
        blank=True,
        help_text="Giorni della settimana in cui inviare il report ai gestori. Vuoto: report disattivato.",
    )
    report_orario = models.TimeField(
        null=True,
        blank=True,
        help_text="Orario di invio nei giorni selezionati sopra.",
    )
    report_destinatari_segreteria = models.BooleanField(default=False, verbose_name="Segreteria")
    report_destinatari_rdz = models.BooleanField(default=False, verbose_name="RdZ")
    report_destinatari_admin = models.BooleanField(default=False, verbose_name="Admin")
    # Non esposto in form (D-64 non lo richiede, è uno stato interno):
    # evita un secondo invio nello stesso giorno se il loop esterno
    # controlla più volte prima e dopo l'orario configurato.
    report_ultimo_invio = models.DateField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Impostazioni Nota Spese"
        verbose_name_plural = "Impostazioni Nota Spese"

    def __str__(self) -> str:
        return "Impostazioni Nota Spese"

    def save(self, *args, **kwargs) -> None:
        self.id = 1
        super().save(*args, **kwargs)

    def clean(self) -> None:
        if self.report_giorni_settimana and self.report_orario is None:
            raise ValidationError(
                {"report_orario": "Obbligatorio se sono selezionati giorni per il report (D-64)."}
            )

    @classmethod
    def corrente(cls) -> ImpostazioniNoteSpese:
        return cls.objects.get_or_create(pk=1)[0]
