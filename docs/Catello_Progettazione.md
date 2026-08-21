# Catello — Piattaforma di segreteria AGESCI Zona Hirpinia

**Documento di progettazione** · v1.0 · agosto 2026
Autore: Andrea Bruno (<https://bruand81.it>) · Licenza codice: MIT

---

## 1. Scopo

Catello è la piattaforma di segreteria della **AGESCI Zona Hirpinia** (Regione Campania).
Nella versione 1 comprende due moduli:

1. **Anagrafica** — importazione dei capi dal gestionale associativo **Buona Caccia**
   (export CSV "Ricerca Soci") e degli incarichi in unità dai **PDF di autorizzazione**
   dei gruppi.
2. **Contributo Formazione Capi (FoCa)** — gestione del contributo annuale che la Zona
   eroga ai capi che partecipano ai campi di formazione, con calcolo automatico,
   valutazione da parte del Comitato e generazione del file per i bonifici.

Catello **non** è collegato a Sestante (IdP SSO della Regione Campania): ha
autenticazione locale autonoma. Eredita dalle piattaforme regionali lo stack tecnico e
il tema grafico, non l'identità.

### 1.1 Origine e rapporto con i progetti esistenti

Catello nasce da un audit di due progetti preesistenti:

| Progetto | Ruolo rispetto a Catello |
| --- | --- |
| `Dashboard_Zona` | Sorgente delle regole di dominio già validate dall'uso reale. Portate selettivamente (§ 2, D-01). |
| `autorizzazioni-agesci` v1.0.1 | Parser dei PDF di autorizzazione. Il codice è **incorporato** in Catello (D-07). |

`Dashboard_Zona` contiene anche i moduli `assemblee` e `pattuglie/riunioni` (verbali,
presenze, statistiche). **Non rientrano nella v1** di Catello e non vanno portati.

---

## 2. Decisioni architetturali

Ogni decisione è vincolante per l'implementazione. Le deviazioni vanno discusse, non
assunte.

### D-01 — Porting selettivo, non riscrittura integrale

Si porta ciò che incorpora regole di dominio validate; si riscrive ciò che dipende dal
soggetto dell'applicazione, che è cambiato.

| Componente di `Dashboard_Zona` | Azione |
| --- | --- |
| Formula di calcolo del contributo (`foca/views.py::_esegui_calcolo`) | Porting, con adeguamento del grano a partecipazione |
| Parsing CSV Buona Caccia (`_parse_valore`, `_parse_data`, uso di `csv.DictReader`) | Porting |
| Mappature branca / unità / capogruppo (`_processa_importazione_branche`) | Porting esteso (D-08) |
| Modelli `foca.*` | Porting con rinomina e nuovo grano |
| Modelli `anagrafica.Capo` / `anagrafica.Gruppo` | Porting con PK diversa (D-02) |
| `accounts.Ruolo`, `accounts.Delega` | Porting |
| `accounts.backends.EmailOrCodiceBackend`, login/reset custom | **Riscrittura** con allauth (D-05) |
| View, form, template, CSS custom (`bg-zona`, `card-header-zona`) | **Riscrittura** sul tema regionale (D-15) |
| `assemblee`, riunioni pattuglia, verbali, `templates_verbali/` | **Fuori scope v1** |

### D-02 — `Gruppo` ha per chiave primaria il codice ordinale

`Gruppo.codice` è un `CharField(max_length=8, primary_key=True)` che contiene il codice
ordinale AGESCI (es. `E0133` = AVELLINO 1, `E0134` = AVELLINO 2).

Verificato in audit: il campo `ORDINALE` di `RicercaSoci.csv` e il `codice_gruppo`
estratto dall'intestazione dei PDF di autorizzazione contengono lo **stesso valore**. È
la chiave di join naturale fra le due importazioni; nessuna euristica sul nome del
gruppo.

**Correzione rispetto a `Dashboard_Zona`:** l'import attuale usa
`Gruppo.objects.get_or_create(nome=...)`, quindi i dati anagrafici del gruppo vengono
scritti solo alla creazione e **non aggiornati mai più**. In Catello si usa
`update_or_create(codice=...)`.

`E9001` ("COM ZONA HIRPINIA") compare nell'export come un gruppo qualsiasi ma non è una
Comunità Capi: è il contenitore di censimento a livello di Zona e ospita gli account del
Comitato. Va marcato con `is_comitato_zona = True`; non ha autorizzazione da importare.
È escluso da partecipazioni e bonifici (A-8). **Non** è escluso da account,
allowlist né anagrafica: vedi **D-33**.

### D-03 — Modello utente unico con tipologia

L'utente che accede può essere una **persona** (segreteria, responsabili, membri di
comitato, delegati) o un **account funzionale di gruppo** (`avellino1@campania.agesci.it`).

```
Utente(AbstractUser)
    tipo            = PERSONA | GRUPPO
    gruppo          = FK(Gruppo, null=True)     # obbligatorio se tipo == GRUPPO
    codice_socio    = CharField(unique=True, null=True)  # solo per tipo PERSONA
```

Un solo modello di permessi per entrambi. Il numero di account funzionali per gruppo è
governato da `Gruppo.account_consentiti` (default 1, `E9001` vale 2): vedi **D-33**.

### D-04 — Ruoli e deleghe, entrambi con scadenza

Si porta il modello di `Dashboard_Zona`, che già implementa il requisito.

**Ruoli effettivi** (`Ruolo`): `ADMIN`, `SEGRETERIA`, `RDZ` (Responsabile di Zona),
`AEZ`, `MCZ` (Membro Comitato), `CG` (Capogruppo), `IABZ`, `ISZ`. Hanno `data_inizio`,
`data_fine` opzionale, flag `attivo`, e `assegnato_da`.

**Vincolo di dominio:** un ruolo effettivo può essere assegnato solo a un utente con
email su `@campania.agesci.it` o `@zonahirpinia.org`. Validazione nel form e nel
`clean()` del modello.

**Deleghe** (`Delega`): vedi **D-26**, che estende questa decisione consentendo la
delega a iniziativa del titolare del ruolo. In sintesi la delega:

- richiede `data_fine` **obbligatoria** (a differenza del ruolo effettivo);
- oltre la scadenza non concede alcun permesso — l'utente resta autenticabile ma senza
  accesso ai moduli, salvo altri titoli;
- non è ricorsiva: un delegato non può a sua volta delegare;
- non abilita l'impostazione di budget e parametri di campagna (D-11);
- può essere assegnata a un utente con email su **qualsiasi** dominio.

Il calcolo dei permessi effettivi è centralizzato in `apps/accounts/permessi.py`:
`Utente.ruoli_effettivi()` restituisce l'unione di ruoli attivi non scaduti e deleghe
attive non scadute. **Nessuna view deve interrogare direttamente `Ruolo` o `Delega`.**

### D-05 — Autenticazione con django-allauth

- Registrazione autonoma con verifica email obbligatoria.
- Login con email (non username).
- **MFA obbligatoria** per `ADMIN` e `SEGRETERIA`, opzionale per gli altri.
- `django-axes` per il rate limiting sui tentativi falliti.
- **Nessun social login, nessun SSO**: Catello non si collega a Sestante.
- `django-auditlog` su `Utente`, `Ruolo`, `Delega`, `Gruppo.iban`, `Partecipazione`,
  `Campagna`.

### D-06 — Allowlist dei gruppi derivata dall'anagrafica

L'export `RicercaSoci.csv` contiene già la colonna `EMAIL GRUPPO`
(es. `avellino2@campania.agesci.it`). L'allowlist si genera quindi **automaticamente**
dall'importazione anagrafica: coppia (`codice`, `email`) per ogni gruppo censito. Il
Comitato di Zona (`E9001`) è l'eccezione: le sue due voci si inseriscono a mano, perché
`EMAIL GRUPPO` riporta un indirizzo diverso da quelli dei RdZ (D-33).

Il caricamento CSV manuale dell'allowlist resta disponibile come **fallback** (gruppo di
nuova costituzione, email cambiata prima del censimento successivo), non come meccanismo
primario.

Flusso di registrazione:

1. L'utente si registra con email `@campania.agesci.it`.
2. Se l'email è in allowlist → account attivato dopo verifica email, associato al gruppo
   corrispondente, accesso immediato al modulo contributi.
3. Se non è in allowlist → account creato in stato `IN_ATTESA`: può autenticarsi, vede
   solo una pagina di cortesia, **nessun accesso ai moduli** finché la segreteria non
   approva e associa il gruppo.

### D-07 — Parser delle autorizzazioni internalizzato

Il codice di `autorizzazioni-agesci` v1.0.1 (stesso autore, stessa licenza MIT) è
**incorporato in Catello**, non consumato come dipendenza esterna. Catello dipende
direttamente da `pdfplumber`.

Posizione: `apps/anagrafica/parser/autorizzazioni.py`, con i test portati in
`apps/anagrafica/tests/test_parser_unit.py` e `test_parser_integration.py`.

Adattamenti rispetto all'originale:

- aggiunta la dataclass `ParseResult` (`data_aggiornamento`, `anno`, `gruppo_nome`,
  `gruppo_codice`, `records`, proprietà `is_valido`);
- aggiunta l'API pubblica `parse_pdf(source: Path | str | BinaryIO) -> ParseResult`, che
  accetta anche un file in memoria: è il flusso reale di Catello (upload da browser →
  parsing immediato), mentre `parse_year()` lavorava solo su cartelle;
- `parse_year()` è mantenuta per import batch da filesystem e per un eventuale comando
  di gestione;
- rimossa la CLI (`cli.py`) e i relativi test: non ha senso dentro un progetto Django.

**Le regex e le regole di riconoscimento non vanno toccate.** Sono il risultato di
tentativi successivi su un text layer che mescola le porzioni di testo, e sono validate
su un campione reale di 15 PDF / 12 gruppi / 218 record. Qualsiasi modifica richiede la
riesecuzione dei test di integrazione con le fixture.

**Conseguenza da accettare:** il codice è ora duplicato fra due repository. Se il parser
evolve altrove, l'allineamento è manuale. Data la stabilità del formato PDF di Buona
Caccia e l'unicità dell'autore, il costo è accettabile e in cambio Catello non dipende
dalla pubblicazione di un pacchetto esterno.

**Le fixture PDF non sono versionate:** contengono dati personali di soci reali. I test
di integrazione si auto-escludono se assenti (`pytest.mark.skipif`), quindi la CI resta
verde. Istruzioni in `apps/anagrafica/tests/fixtures/pdf/README.md`.

### D-08 — Gli incarichi in unità vanno persistiti, non solo derivati

`Dashboard_Zona` scarta l'incarico: cerca le sottostringhe `CAPO GRUPPO`, `SUPPORTO`,
`ASSISTENTE ECCLESIASTICO` per ricavare un flag booleano e una branca, e getta il resto.

Catello persiste il record completo in `IncaricoUnita`, da cui `branca` e `is_capogruppo`
sono **derivati**, non sostitutivi.

Vocabolario chiuso delle funzioni, verificato sui 218 record di test:

| Valore nel PDF | Costante |
| --- | --- |
| `CAPO UNITÀ` | `CAPO_UNITA` |
| `AIUTO CAPO UNITÀ` | `AIUTO_CAPO_UNITA` |
| `CAPO GRUPPO` | `CAPO_GRUPPO` |
| `ASSISTENTE ECCLESIASTICO DI GRUPPO` | `AE_GRUPPO` |
| `ASSISTENTE ECCLESIASTICO DI UNITA` | `AE_UNITA` |
| `SERVIZIO DI SUPPORTO AL GRUPPO` | `SUPPORTO_GRUPPO` |
| `SERVIZIO DI SUPPORTO ALL'AZIONE EDUCATIVA` | `SUPPORTO_AZIONE_EDUCATIVA` |
| `MAESTRO DEI NOVIZI` | `MAESTRO_NOVIZI` |
| *(nessun incarico nell'anno)* | `A_DISPOSIZIONE` — valore **derivato**, mai presente nel PDF né persistito in `IncaricoUnita` (D-31) |

Codici unità osservati, deterministici:

| Prefisso | Branca | Genere unità |
| --- | --- | --- |
| `G1` | Adulti (Comunità Capi) | — |
| `H1` / `I1` | L/C | maschile / femminile |
| `L1` | L/C | misto |
| `M1` / `N1` | E/G | maschile / femminile |
| `O1` | E/G | misto |
| `T1` | R/S | misto |

> *Inferenza da verificare su più annualità:* l'associazione `H1`/`M1` → maschile e
> `I1`/`N1` → femminile è dedotta dal campione 2026 (16 unità maschili e 16 femminili,
> conteggi coerenti). Il valore autorevole resta `genere_unita` restituito dal parser,
> che va usato in scrittura; la tabella serve solo come controllo di coerenza.

**Gestione delle anomalie.** Sul campione, 1 record su 218 (0,5 %) presenta testo
corrotto da interleaving del text layer:
`funzione = "SERVIZIO DIin CSsoli R SUPPORTO AL GRUPPO"` (socio 415049, gruppo E2000).

Regola: ciò che **non corrisponde esattamente** a un valore del vocabolario chiuso **non
viene scritto** e finisce nel report anomalie dell'importazione per risoluzione manuale.
È vietato normalizzare per somiglianza, fare fuzzy matching o "indovinare" il valore
più probabile.

### D-09 — Snapshot delle autorizzazioni: la più recente vince, contro il database

I PDF sono **snapshot datati** della stessa autorizzazione di gruppo. Verificato:
Avellino 3 ha due file, aggiornati al 29/10/2025 (23 record) e al 08/05/2026 (22
record), con stesse unità, due uscite e un ingresso.

Regole di importazione:

1. Ogni gruppo ha in database `data_autorizzazione` (l'ultima importata).
2. Un PDF con `data_aggiornamento` **anteriore o uguale** a quella già registrata viene
   **rifiutato** e segnalato, mai applicato. Senza questo controllo, ricaricare un file
   vecchio resuscita capi già usciti.
3. Se un caricamento contiene più PDF, si processano in ordine di `data_aggiornamento`
   **crescente**, e per ogni codice gruppo si applica solo il più recente.
4. Un socio può comparire in gruppi diversi nello stesso anno: verificato, il socio
   1690974 risulta in E3471 (15/01/2026) e in E1681 (08/05/2026). Con
   `unique_together (codice_socio, anno_scout)` vince l'ultima scrittura, quindi
   **l'ordine deterministico del punto 3 è ciò che rende corretto il risultato**.
5. L'importazione è idempotente: rieseguire lo stesso file non cambia lo stato.

### D-10 — Regole di calcolo del contributo

**Unità di contributo: la partecipazione**, non il capo. Un capo che frequenta due campi
nello stesso anno associativo genera due partecipazioni e conta due volte nel divisore.

Sia:

- `B` = budget della campagna (`Campagna.budget`)
- `N` = numero di partecipazioni in stato `APPROVATA` (le respinte e le non valutate
  sono escluse)
- `T` = tetto massimo per partecipazione (`Campagna.tetto_per_partecipazione`, default
  50,00 €)
- `q_i` = quota di iscrizione effettivamente versata per la partecipazione *i*

Allora:

```
quota_proporzionale = B / N                       (Decimal, nessun arrotondamento qui)
importo_i = min(quota_proporzionale, T, q_i)      arrotondato a 2 decimali ROUND_DOWN
```

Il troncamento per difetto garantisce `Σ importo_i ≤ B` in ogni caso.

**Residuo.** `B − Σ importo_i` **resta alla Zona**: nessuna redistribuzione, nessun
secondo giro di calcolo. Il residuo è mostrato nel riepilogo come voce esplicita.

**Anno associativo:** 1 ottobre → 30 settembre dell'anno successivo. `Campagna.anno` è
l'anno di chiusura (es. campagna 2026 = 01/10/2025 – 30/09/2026). Le partecipazioni sono
ammissibili solo se `data_inizio` cade nella finestra.

L'implementazione vive in **`apps/contributi/calcolo.py`** ed è l'**unica** fonte di
verità: view, simulazione, export e report chiamano la stessa funzione. Nessuna
duplicazione della formula altrove.

### D-11 — Tipologie di campo, approvazione e quota di default

```
TipologiaCampo
    codice                  # CFM, CFA, CCG, ALTRO, ...
    nome
    approvazione_automatica = BooleanField
    quota_default           = DecimalField(null=True)
    livello                 = ZONA | REG | NAZ | ALTRO
    attiva                  = BooleanField
```

- `CFM`, `CFA`, `CCG`: `approvazione_automatica = True`, `quota_default = 51.50`.
  La segreteria verifica solo l'effettiva partecipazione; non serve delibera del Comitato.
- Tutte le altre tipologie: `approvazione_automatica = False`, valutazione del Comitato
  di Zona con esito motivato.

`quota_default` **precompila** `Partecipazione.quota_versata`, che resta **modificabile
dal gruppo**: è la spesa reale sostenuta e concorre al tetto `min(...)` di D-10. Non è
un tetto in sé.

**Chi imposta budget, tetto e parametri di campagna:** ruoli effettivi da `SEGRETERIA` in
su, inclusi i Responsabili di Zona. **I delegati sono esclusi** da queste operazioni,
anche se delegati a un ruolo che le consentirebbe.

**Documentazione probatoria:** non obbligatoria all'inserimento. Il Comitato può
richiederla su una singola partecipazione; la richiesta porta la partecipazione in stato
`DOCUMENTI_RICHIESTI` e il gruppo carica un allegato. Nessun upload obbligatorio nel
flusso ordinario.

### D-12 — Macchine a stati (django-fsm-2)

**`Campagna`**

```
APERTA ──► IN_VALUTAZIONE ──► CHIUSA ──► LIQUIDATA
```

| Transizione | Chi | Effetto |
| --- | --- | --- |
| `APERTA → IN_VALUTAZIONE` | Segreteria+ | Blocca l'inserimento; le auto-approvabili passano ad `APPROVATA` |
| `IN_VALUTAZIONE → CHIUSA` | Segreteria+ | Esegue il calcolo definitivo, congela gli importi, sblocca la visibilità cross-gruppo |
| `CHIUSA → LIQUIDATA` | Segreteria+ | Registra l'avvenuto bonifico (data + riferimento) |

Il passaggio a `CHIUSA` è consentito solo se **nessuna** partecipazione è in
`INSERITA` o `DOCUMENTI_RICHIESTI`.

**`Partecipazione`**

```
INSERITA ──► APPROVATA
         └─► RESPINTA
         └─► DOCUMENTI_RICHIESTI ──► APPROVATA | RESPINTA
```

`RESPINTA` richiede **sempre** una causale non vuota, senza eccezioni. Per il
respingimento automatico dovuto alla disattivazione del gruppo la causale è «Gruppo non
più attivo» (D-24). Tutte le transizioni sono tracciate
(`valutata_da`, `data_valutazione`) e registrate in auditlog.

### D-13 — Visibilità

| Soggetto | Prima della chiusura | Dopo `CHIUSA` |
| --- | --- | --- |
| Account di gruppo | Solo le proprie partecipazioni e i propri importi | Le proprie in dettaglio + **totali** degli altri gruppi |
| Segreteria / RdZ / Comitato | Tutto | Tutto |
| Delegato | Come il ruolo delegato, meno i parametri di campagna | idem |

Il dettaglio nominativo dei capi di **altri** gruppi non è mai esposto agli account di
gruppo: dopo la chiusura vedono l'importo totale per gruppo, non l'elenco dei capi.

La funzione `partecipazioni_visibili(utente, campagna)` in
`apps/contributi/visibilita.py` è l'unica fonte di verità, usata da view, export e
futura API.

### D-14 — Dati bancari e file bonifici

`Gruppo.iban` e `Gruppo.intestazione_conto` sono inseriti **dal gruppo stesso**.

- Validazione IBAN completa: lunghezza per paese e **checksum mod-97** (ISO 13616), non
  solo regex di forma.
- Ogni modifica è registrata in auditlog con utente e timestamp.
- Visibile solo al gruppo proprietario e ai ruoli da `SEGRETERIA` in su. Mai in liste,
  mai in export non bancari, mai nei log applicativi.
- Il passaggio della campagna a `CHIUSA` richiede che tutti i gruppi con almeno una
  partecipazione approvata abbiano un IBAN valido; in caso contrario, elenco bloccante.

**File bonifici:** calcolato **al momento della generazione** sommando le partecipazioni
secondo l'attribuzione corrente (D-29), non da un aggregato congelato alla chiusura.
Esportazione **CSV e XLSX** con una riga per gruppo
(`codice`, `denominazione`, `intestazione_conto`, `iban`, `importo`, `causale`). Un unico
bonifico annuale dopo il 20 settembre. Causale standard parametrizzabile, default:
`Contributo FoCa <anno> - AGESCI Zona Hirpinia`.

SEPA XML `pain.001.001.03` è **rinviato a v1.1**: valutato in progettazione, non
necessario per la v1 (il volume è di ~12 bonifici l'anno, il data entry manuale è
sostenibile e il formato XML richiede dati aggiuntivi dell'ordinante non ancora
disponibili).

### D-15 — Tema e branding

`django-agesci-campania-theme >= 2.3.0` (PyPI), installato con `uv add`.

```python
AGESCI_THEME_BRANCA = "capi"           # viola, coerente con l'emblema di Zona
AGESCI_THEME_NOME = "Zona Hirpinia"
AGESCI_THEME_LOGO_NAVBAR = "core/img/CAMPANIA_HIRPINIA.png"
```

Il tema fornisce già l'emblema Hirpinia via `{% emblema_zona "hirpinia" %}`.
**Nessun CSS custom**: i colori si ottengono dalle utility del tema
(`bg-ag-viola`, `text-ag-*`, `{% branca_bg %}`). Le classi `bg-zona` e
`card-header-zona` di `Dashboard_Zona` non vanno portate.

Palette ufficiale di riferimento: viola `#7A1E99`, viola scuro `#622599`, oro `#FFCC1E`.
Il rosso R/S corretto è `#EF3340` (il valore RGB del manuale 2011 per il Pantone 032C è
un refuso di stampa confermato).

### D-16 — Simulazione del calcolo

Si mantiene il flag `is_simulazione` di `Dashboard_Zona`: la segreteria può eseguire il
calcolo a vuoto quante volte vuole prima di chiudere, senza scrivere gli importi
definitivi. Funzionalità non richiesta esplicitamente ma già presente, utile e a costo
zero nel porting.

### D-17 — Niente Celery in v1

Le operazioni pesanti (import CSV ~200 righe, parsing di ~15 PDF, calcolo su ~50
partecipazioni) sono rare e completano in pochi secondi. Introdurre Celery aggiungerebbe
broker, worker e complessità di deploy senza beneficio.

L'import PDF gira **in-request** con `transaction.atomic`. Se in esercizio i tempi
superano i 30 s, si valuta Celery in v1.1 (l'interfaccia di importazione va scritta in
modo da non precludere l'asincronia: funzione pura chiamata da view, non logica
nella view).

Di conseguenza **Redis non è previsto** nella v1: cache locmem in dev, database cache in
prod.

### D-18 — Deploy

Docker Compose sul pattern Plancia:

- **Sviluppo:** PostgreSQL in Docker, Django sull'host.
- **Produzione:** tutto in Docker tranne il reverse proxy, selezionabile con
  `configure-prod.sh` (nginx in Docker, nginx su host, Apache su host).

Domini: `segreteria.agescihirpinia.it` (primario), `catello.agescihirpinia.it` (alias).
Entrambi in `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS`.

### D-19 — Invio email: provider selezionabile, autenticazione moderna

L'invio email è un componente astratto con più implementazioni, selezionabile con la
variabile d'ambiente `EMAIL_PROVIDER`. Tutto il codice applicativo (incluso allauth)
usa `django.core.mail` e **non conosce il provider attivo**.

| `EMAIL_PROVIDER` | Autenticazione | Uso previsto |
| --- | --- | --- |
| `console` | — | Sviluppo |
| `locmem` | — | Test |
| `smtp` | Password + STARTTLS/SSL | Provider generici, Exchange on-premises, fallback |
| `gmail_service_account` | Service account + delega di dominio | Gmail/Workspace, senza token da rinnovare |
| `gmail_oauth` | OAuth utente, scope `gmail.send` | Gmail, quando la delega di dominio non è disponibile |
| `microsoft_graph` | OAuth client credentials, permesso `Mail.Send` | Microsoft 365 / Exchange Online |

Dettaglio in **§ 8**.

### D-20 — Attivazione degli account tramite OTP inviata per email

Accanto alla registrazione autonoma (D-06) esiste un percorso **su iniziativa della
Zona**: `SEGRETERIA`, `ADMIN` e `RDZ` possono attivare gli account delle caselle
istituzionali — dei gruppi e dei Responsabili di Zona — inviando un codice monouso via
email, **anche in modo massivo** selezionando più destinatari.

```
InvitoAttivazione
    email             Email               destinatario
    gruppo            FK(Gruppo, null)    valorizzato per gli account di gruppo
    ruolo_proposto    Char(null)          es. RDZ, per gli account personali
    codice_hash       Char                OTP salvata con hash, mai in chiaro
    stato             INVIATO | USATO | SCADUTO | REVOCATO
    scadenza          DateTime            default: 7 giorni
    tentativi         Int                 massimo 5, poi REVOCATO
    creato_da         FK(Utente)
    inviato_il, usato_il
```

Regole:

- **L'OTP non è mai salvata in chiaro**: si conserva l'hash, si invia il valore una sola
  volta nell'email. Un invito smarrito si riemette, non si recupera.
- Emettere un nuovo invito per lo stesso indirizzo **revoca** il precedente.
- L'OTP consente solo di **impostare la password** e completare il profilo: non
  autentica da sola e non concede permessi prima che la password sia impostata.
- L'invito implica pre-autorizzazione: l'account nasce già associato al gruppo e in
  stato `ATTIVO`, saltando l'approvazione della segreteria prevista da D-06.
- Per `RDZ` (e per ogni ruolo che richiede MFA, D-05) l'attivazione **impone**
  l'iscrizione al secondo fattore prima del primo accesso ai moduli.
- L'invio massivo è tracciato: un record per destinatario, con esito. Un fallimento di
  invio non deve interrompere il lotto.
- Rate limiting sull'inserimento del codice tramite `django-axes`, come per il login.

L'email contiene sia il codice sia un collegamento che lo precompila; entrambi
risolvono allo stesso token monouso.

### D-21 — Caricamento massivo delle partecipazioni da xlsx

Oltre all'inserimento manuale (§ 7), le partecipazioni si possono caricare da file
**xlsx** (accettato anche CSV, stesso schema di colonne).

**Perimetro per ruolo — vincolo di sicurezza, non solo di comodità:**

| Chi carica | Righe ammesse |
| --- | --- |
| Account di gruppo | Solo capi il cui censimento dell'anno riporta **lo stesso ordinale** del gruppo che carica |
| `SEGRETERIA`, `ADMIN`, `RDZ` | Tutti i gruppi della Zona |

Una riga fuori perimetro è un **errore bloccante segnalato**, mai una riga scartata in
silenzio: un gruppo che sbaglia file deve accorgersene.

Colonne del tracciato (modello scaricabile dalla piattaforma):
`codice_socio`, `cognome`, `nome`, `codice_tipologia`, `data_inizio`, `data_fine`,
`luogo`, `quota_versata`. `cognome` e `nome` sono **campi di controllo**: se non
corrispondono all'anagrafica, la riga è segnalata come sospetta e non importata.
`quota_versata` vuota viene precompilata dal `quota_default` della tipologia (D-11).

Flusso obbligatorio in **due fasi**: caricamento → **anteprima** con righe valide,
sospette e in errore → conferma esplicita. Nessuna scrittura prima della conferma.

Idempotenza: la chiave logica è (`campagna`, `capo`, `tipologia`, `data_inizio`). Una
riga già presente non crea un duplicato; se differisce nei restanti campi viene
segnalata come conflitto e lasciata alla decisione dell'utente.

Il caricamento è consentito solo con campagna in stato `APERTA` e dentro la finestra di
inserimento.

### D-22 — Identità persistente del capo e disattivazione (revisione del modello)

**Questa decisione corregge il modello portato da `Dashboard_Zona`.**

Nel progetto originale `Capo` ha `unique_together = ("codice_socio", "anno_scout")`:
un record per persona **per anno**. Con quello schema il requisito "disattivare i capi
non presenti nell'import dell'anno, ma non cancellarli se hanno partecipazioni" non è
esprimibile: un capo assente dall'import semplicemente non ha un record per quell'anno,
quindi non c'è nulla da disattivare, e le partecipazioni degli anni precedenti puntano
a record distinti della stessa persona.

Il modello si separa quindi in **identità** e **censimento annuale**:

```
Capo                                    CensimentoCapo
    codice_socio   Char PK                  capo          FK(Capo)
    nome, cognome                           anno_scout    Int
    sesso, data_nascita, CF                 gruppo        FK(Gruppo)
    email, cellulare                        branca        derivata
    attivo         Bool                     is_capogruppo derivata
    data_disattivazione                     livello_foca  Int
    utente         FK(Utente, null)         comunita_socio, status_socio
                                            unique: (capo, anno_scout)
```

Regole di disattivazione:

1. L'import CSV dell'anagrafica (§ 6.1) è **l'unica fonte** che disattiva: è l'elenco
   autorevole dei censiti. L'import delle autorizzazioni non disattiva nessuno.
2. La disattivazione si applica **solo entro il perimetro del file importato**: i capi
   dei gruppi presenti nel file e assenti dalle sue righe. Se un import copre parte
   della Zona, i capi degli altri gruppi restano invariati.
3. Disattivare significa `attivo = False` più `data_disattivazione`. **Nessuna
   cancellazione**, mai automatica.
4. La disattivazione è **reversibile**: se il capo ricompare in un import successivo,
   torna attivo e la data si azzera.
5. Un capo disattivato non è selezionabile per nuove partecipazioni, ma resta
   consultabile e conserva lo storico.

Regole di cancellazione:

- `Partecipazione.capo` usa `on_delete=PROTECT`. Un capo con almeno una partecipazione
  **non è cancellabile**, in nessuna circostanza e da nessun ruolo.
- La cancellazione di un capo senza partecipazioni è riservata ad `ADMIN`, manuale,
  con conferma esplicita, e registrata in auditlog.
- Coerente con A-4: nessuna procedura automatica di purge.

Il report dell'importazione elenca sempre, in sezione separata, i capi disattivati in
quella esecuzione: è l'informazione che la segreteria usa per verificare i trasferimenti
e le uscite dalla Comunità Capi.

### D-23 — Esportazione dell'anagrafica

Export dei capi in **xlsx** e **csv**, con filtri e raggruppamenti.

Filtri: anno associativo, gruppo (di censimento **o** di servizio), unità, funzione,
livello FoCa, stato (attivi / disattivati / entrambi).

Ogni riga riporta **entrambe** le colonne, `gruppo_censimento` e `gruppo_servizio`
(D-34): un export che ne mostri una sola è ambiguo.

Raggruppamento selezionabile, che determina la struttura del file:

| Raggruppamento | xlsx | csv |
| --- | --- | --- |
| Nessuno | foglio unico | file unico |
| Per unità di servizio | un foglio per unità | colonna `unita` + ordinamento |
| Per funzione (ruolo) | un foglio per funzione, incluso «A disposizione» | colonna `funzione` + ordinamento |
| Per livello FoCa | un foglio per livello | colonna `livello_foca` + ordinamento |

Un capo con incarichi in più unità compare in più fogli: è corretto, riflette il
servizio reale. Il conteggio totale va quindi indicato come numero di **capi distinti**,
non come somma delle righe, per non generare letture errate.

**Perimetro:** un account di gruppo esporta solo i propri capi; `SEGRETERIA`, `ADMIN` e
`RDZ` tutta la Zona.

**Protezione dei dati.** L'export contiene dati personali (codice fiscale, residenza,
recapiti). Quindi:

- due profili di colonne: **minimo** (nome, cognome, gruppo, unità, funzione, livello
  FoCa) come default, ed **esteso** (con recapiti e dati anagrafici) selezionabile
  esplicitamente;
- ogni esportazione è registrata (`EsportazioneAnagrafica`: utente, filtri, profilo
  colonne, numero di righe, timestamp) e visibile ad `ADMIN`;
- il file non viene conservato sul server dopo il download.

CSV in UTF-8 **con BOM** e separatore `;`, per apertura diretta in Excel italiano.
Non si replica la riga `sep=,` di Buona Caccia: è una stranezza del gestionale, non uno
standard da propagare.

### D-24 — Ciclo di vita del gruppo, gestito da interfaccia

Lo stato di un gruppo **non** è un booleano: è una proprietà dell'anno associativo, e
un gruppo può entrare o uscire in corso d'anno.

```
StatoGruppoAnno
    gruppo        FK(Gruppo)
    anno_scout    Int
    attivo        Bool
    motivo        Text
    disposto_da   FK(Utente)
    disposto_il   DateTime
    unique: (gruppo, anno_scout)
```

Risoluzione dello stato per un anno *X*: vale il record con `anno_scout` più alto fra
quelli ≤ *X*. Così una disattivazione **si propaga agli anni successivi** finché non
viene disposto un nuovo stato, che è esattamente il comportamento richiesto. Il metodo
`Gruppo.e_attivo(anno)` è l'unico punto che implementa questa risoluzione.

**La disattivazione vale per l'intero anno associativo in cui avviene**, quindi
retroattivamente dal 1° ottobre. Conseguenze:

- l'account funzionale del gruppo non può più autenticarsi;
- il gruppo non compare fra i destinatari degli inviti (D-20), né nei bonifici;
- i suoi capi non sono selezionabili per nuove partecipazioni. `Capo.attivo` **non**
  viene toccato: resta governato dall'import (D-22), e la selezionabilità si calcola
  come `capo.attivo AND gruppo.e_attivo(anno)`. Due fonti di verità sullo stesso flag
  divergerebbero.

**Durata minima.** Una disattivazione copre **almeno l'intero anno associativo** in cui
avviene. Non è quindi possibile riattivare un gruppo nello stesso anno in cui è stato
disattivato: la riattivazione può disporsi al più presto per l'anno successivo, anche in
corso d'anno.

**Effetto sul contributo (A-6, deciso).** Un gruppo disattivato **non ha diritto ad
alcun contributo per quell'anno**, nemmeno per il periodo in cui era attivo. Le sue
partecipazioni passano a `RESPINTA` con causale «Gruppo non più attivo» e, essendo
respinte, escono dal divisore *N* (D-10).

La causale di respingimento è **sempre obbligatoria**, per qualunque respingimento e non
solo per questo: una partecipazione respinta senza motivazione è indistinguibile da un
errore.

**Ordine delle operazioni.** Prima si ri-attribuiscono le partecipazioni dei capi
trasferiti al nuovo gruppo (D-29), poi si respinge ciò che resta attribuito al gruppo
disattivato. Invertendo l'ordine si respingerebbero partecipazioni di capi che nel
frattempo sono passati a un gruppo attivo e che quindi il contributo lo meritano.

La disattivazione richiede motivazione obbligatoria e conferma esplicita che elenca
quante partecipazioni verranno respinte e quante ri-attribuite altrove.

**Disattivazione a campagna già chiusa (A-10, deciso).** Se la campagna è `CHIUSA` con
importi già congelati e comunicati, ma il bonifico non è ancora partito:

1. **Prima** si ri-attribuiscono le partecipazioni dei capi nel frattempo passati ad
   altri gruppi (D-29). L'importo congelato non cambia: cambia solo il destinatario, e il
   nuovo gruppo lo incassa regolarmente.
2. **Poi** le partecipazioni che restano attribuite al gruppo disattivato non vengono
   pagate.
3. Gli importi degli **altri** gruppi restano invariati: nessun ricalcolo, nessuna
   ridistribuzione. Erano già stati comunicati e ricalcolarli significherebbe smentirli.
4. La somma non erogata confluisce nel **residuo che torna alla Zona** (D-10).

A campagna `LIQUIDATA` non si fa nulla: il denaro è già uscito, e la disattivazione
produce effetti solo dall'anno successivo.

Il fatto che il totale per gruppo si calcoli al momento della generazione del file
bonifici (D-29) è ciò che rende possibile tutto questo senza ricalcoli: la
ri-attribuzione sposta una riga da un gruppo all'altro, non tocca gli importi.

> **Nota sull'attribuzione a cavallo d'anno.** Il bonifico si dispone dopo il 20 settembre,
> a ridosso della chiusura dell'anno associativo. Se un ritardo lo porta oltre il 1°
> ottobre e nel frattempo l'anagrafica del nuovo anno registra un trasferimento, vale
> l'attribuzione **in essere al momento della generazione del file**. È la lettura
> coerente con «il contributo segue il capo», ed è l'unica che non richiede di
> ricostruire uno stato passato al momento di pagare.

**Aggiunta di un gruppo in corso d'anno**, da interfaccia, per `SEGRETERIA` in su:

1. **Riattivazione** di un gruppo esistente: nuovo `StatoGruppoAnno` con `attivo=True`,
   per un anno **successivo** a quello della disattivazione. Anagrafica, capi e storico
   restano quelli di prima.
2. **Nuovo gruppo**: `codice` (ordinale) **obbligatorio**, validato nel formato
   osservato (`E` + 4 cifre) e univoco. Se l'ordinale corrisponde a un gruppo esistente
   ma disattivato, l'interfaccia **non crea un duplicato**: propone la riattivazione.

Il gruppo creato manualmente ha `origine = MANUALE`; l'import successivo di Buona Caccia
ne aggiorna i dati senza sovrascrivere lo stato disposto da interfaccia. Alla creazione
va inserita l'email istituzionale, che alimenta l'allowlist (D-06) e rende possibile
l'invito con OTP.

### D-25 — Recupero autonomo dell'OTP scaduta

L'email di attivazione (D-20) contiene, oltre al codice e alle istruzioni, anche
**come procedere se il codice è scaduto**: un collegamento alla pagina di richiesta di
un nuovo codice, utilizzabile dal destinatario senza passare dalla segreteria.

Regole della pagina di recupero:

- richiede solo l'indirizzo email;
- risponde **sempre allo stesso modo**, che l'indirizzo esista o meno: non deve
  rivelare quali caselle sono censite (prevenzione dell'enumerazione);
- emette un nuovo codice solo se per quell'indirizzo esiste un invito in stato
  `SCADUTO` o `INVIATO`, e se il gruppo o il ruolo associato è ancora attivo (D-24);
- il nuovo codice **revoca** il precedente;
- rate limiting per indirizzo e per IP (`django-axes`), per evitare che diventi un
  canale di invio massivo verso terzi;
- un invito in stato `REVOCATO` (per esaurimento tentativi) **non** è recuperabile in
  autonomia: richiede l'intervento della segreteria. È la differenza fra «ho aspettato
  troppo» e «qualcuno ha provato a indovinare».

### D-26 — Delega a iniziativa del titolare del ruolo

**Questa decisione estende D-04**, dove la delega era prerogativa dei soli `ADMIN`.

Chi detiene un ruolo **effettivo** può delegarlo. Un account di gruppo può quindi
abilitare in autonomia altre persone — un capogruppo, un incaricato di segreteria — allo
stesso ruolo e sullo stesso perimetro, senza passare dalla Zona.

Vincoli:

| Regola | Motivo |
| --- | --- |
| Solo un ruolo **effettivo** è delegabile; un delegato non può ri-delegare | Evita la propagazione incontrollata (già in D-04) |
| La delega **non può eccedere** la scadenza del ruolo di origine | Un delegato non deve sopravvivere al delegante |
| Revoca o scadenza del ruolo di origine **revoca a cascata** le sue deleghe | Altrimenti un gruppo disattivato lascerebbe accessi attivi |
| Perimetro identico a quello del delegante, mai più ampio | Un CG del gruppo E0133 delega solo su E0133 |
| Numero massimo di deleghe attive per ruolo: **3**, configurabile | Limite pratico contro la diffusione silenziosa degli accessi |
| `SEGRETERIA` e `ADMIN` vedono e revocano **qualsiasi** delega | Serve una via di rimedio centrale |
| I parametri di campagna restano preclusi ai delegati (D-11) | Invariato |

**Invito del delegato.** Se la persona non ha ancora un account, il delegante la invita
direttamente per email: si riusa `InvitoAttivazione` (D-20) con `ruolo_proposto`
valorizzato e un riferimento alla `Delega` creata in stato pendente. La delega diventa
effettiva **solo** ad attivazione completata; se l'invito scade o viene revocato, decade
anche la delega pendente.

Ogni creazione, attivazione e revoca di delega è notificata per email al delegante e
registrata in auditlog. La segreteria ha una vista d'insieme di tutte le deleghe attive
nella Zona, con scadenza: senza quella vista, la delega distribuita diventa un accesso
non governato.

### D-27 — Impersonificazione da parte degli amministratori

Gli `ADMIN` possono operare come un altro utente, con `django-hijack`.

- Solo `ADMIN`. Nessun altro ruolo, nemmeno per delega.
- **Banner permanente e non chiudibile** durante l'impersonificazione, con l'indicazione
  di chi si sta impersonando e il pulsante per uscire.
- Inizio e fine sono registrati in auditlog. Ogni azione compiuta in impersonificazione
  conserva **entrambe** le identità: `eseguito_da` (l'utente impersonato) e
  `eseguito_da_reale` (l'amministratore). Un'azione tracciata su una sola identità
  renderebbe l'audit inutilizzabile proprio nei casi in cui serve.
- **Azioni precluse durante l'impersonificazione**, anche se il ruolo impersonato le
  consentirebbe:
  - modifica di IBAN e intestazione del conto;
  - modifica di password, email e MFA dell'utente impersonato;
  - cancellazioni;
  - transizioni di campagna verso `CHIUSA` e `LIQUIDATA`.

  Sono le azioni irreversibili o che spostano denaro: devono richiedere che il
  legittimo titolare sia realmente presente.
- L'utente impersonato riceve una notifica email a fine sessione, con data e nome
  dell'amministratore. È una scelta di trasparenza, non un requisito tecnico.

Oltre all'impersonificazione di un utente reale, l'interfaccia offre una **vista di
prova per ruolo** in sola lettura («vedi la piattaforma come un account di gruppo»),
utile per verificare i permessi senza toccare l'account di nessuno.

### D-28 — Molteplicità dei ruoli

Un utente può detenere **più ruoli contemporaneamente**, effettivi o per delega, anche
su perimetri diversi: una persona può essere CG del gruppo E0133, delegata al ruolo del
gruppo E0134 e membro del Comitato di Zona.

- Nessun vincolo di unicità su `Ruolo.utente`: il modello lo consente già.
- I permessi sono l'**unione** dei ruoli attivi non scaduti e delle deleghe attive non
  scadute. `ruoli_effettivi()` (D-04) restituisce un insieme, mai un singolo valore.
- Il perimetro è a sua volta l'unione: `gruppi_visibili(utente, anno)` in
  `apps/accounts/permessi.py` restituisce l'insieme dei gruppi su cui l'utente può
  operare, tenendo conto sia dei ruoli sia dello stato del gruppo per quell'anno (D-24).
  **Nessuna view deve ricavare il gruppo da `utente.gruppo`**: quel campo identifica
  l'account funzionale, non il perimetro operativo.
- Quando i ruoli danno permessi diversi, vale il più permissivo; le esclusioni esplicite
  (parametri di campagna preclusi ai delegati, D-11) restano tali anche se l'utente ha
  contemporaneamente una delega e un ruolo effettivo minore.
- L'interfaccia mostra i ruoli attivi dell'utente e, dove il perimetro è ambiguo (più
  gruppi), richiede la selezione esplicita del gruppo su cui si sta operando prima di
  scrivere dati.

### D-29 — Mobilità dei capi fra gruppi

Un capo cambia gruppo nel corso degli anni, e può cambiarlo anche **in corso d'anno**:
verificato in audit, il socio 1690974 compare nell'autorizzazione di E3471 aggiornata al
15/01/2026 e in quella di E1681 aggiornata al 08/05/2026.

La separazione fra `Capo` (identità, PK `codice_socio`) e `CensimentoCapo` (anno +
gruppo) introdotta da D-22 regge la mobilità senza modifiche. Ne discendono però quattro
regole che vanno rispettate ovunque.

**1. Il gruppo di appartenenza è sempre relativo a un anno.** Non esiste «il gruppo di
un capo»: esiste il gruppo del suo censimento per un dato anno. Ogni query che collega
un capo a un gruppo deve passare da `CensimentoCapo` con l'anno esplicito. Un accesso a
`capo.gruppo` non deve essere possibile, perché il campo non esiste sul modello.

**2. Il contributo segue il capo.** Se un capo cambia gruppo, la sua partecipazione viene
**ri-attribuita** al nuovo gruppo, che diventa il destinatario del bonifico.

Questo corregge una scelta opposta, precedentemente adottata in questo documento, per cui
`Partecipazione.gruppo` restava congelato al gruppo di appartenenza al momento del campo.
La regola vigente è la ri-attribuzione.

Conseguenze operative:

- `Partecipazione.gruppo` è **aggiornabile** in seguito a un trasferimento rilevato, e
  ogni aggiornamento è tracciato in auditlog con il gruppo di provenienza.
- **Gli aggregati per gruppo non si congelano.** A campagna `CHIUSA` si congelano gli
  importi **per partecipazione** (`ContributoPartecipazione`); il totale per gruppo e il
  file bonifici si calcolano **al momento della generazione**, sommando le
  partecipazioni secondo l'attribuzione corrente. Congelare `ContributoGruppo` alla
  chiusura renderebbe impossibile spostare il versamento senza ricalcolare tutto.
- La ri-attribuzione **non cambia l'importo**: sposta il destinatario, non la cifra.
- A campagna `LIQUIDATA` non si ri-attribuisce più nulla: il bonifico è già partito.

Conseguenza sulla visibilità (D-13): un gruppo vede le partecipazioni attualmente
attribuite a sé. Il gruppo di provenienza smette di vedere quelle trasferite; il gruppo
di destinazione le vede, importo compreso, perché ne è il destinatario.

**3. Un trasferimento non è un'uscita.** Nella disattivazione dei capi (D-22), un capo è
disattivato solo se assente da **tutte** le righe dell'import, non se assente dalle
righe del gruppo che aveva prima. Se compare sotto un altro ordinale, è un
trasferimento: il censimento dell'anno viene aggiornato al nuovo gruppo e il capo resta
attivo.

Questa distinzione conta anche oltre l'anagrafica: nei conteggi di ricambio della
Comunità Capi, i trasferimenti fra gruppi della stessa Zona non sono né uscite né
ingressi, e sommarli produce numeri gonfiati su entrambi i lati.

**4. Il trasferimento va registrato, non solo applicato.**

```
TrasferimentoCapo
    capo             FK(Capo)
    anno_scout       Int
    gruppo_origine   FK(Gruppo)
    gruppo_destino   FK(Gruppo)
    rilevato_il      DateTime
    origine          IMPORT_CSV | IMPORT_AUTORIZZAZIONI | MANUALE
```

`CensimentoCapo` resta unico per (capo, anno): rappresenta la situazione corrente, non
la cronologia. Il registro dei trasferimenti conserva la storia, compare in una sezione
dedicata del report di importazione ed è ciò che la segreteria consulta quando i conti
di un gruppo non tornano.

**Ordine di applicazione.** Con più fonti nello stesso anno vale la regola di D-09: si
processa in ordine di `data_aggiornamento` crescente e l'ultima rilevazione determina il
censimento corrente. Senza quell'ordine, il gruppo assegnato dipenderebbe dall'ordine dei
file caricati.

**Ruoli legati al gruppo di provenienza.** Vedi **D-30**: il trasferimento **revoca** i
ruoli il cui perimetro è il gruppo che il capo ha lasciato.

### D-30 — `CG` è un ruolo derivato, non un atto amministrativo

I ruoli di Catello non sono tutti della stessa natura, e trattarli allo stesso modo
produce disallineamenti.

| Natura | Ruoli | Origine | Revoca |
| --- | --- | --- | --- |
| **Derivato** | `CG` | L'incarico `CAPO GRUPPO` nell'autorizzazione del gruppo | Automatica, quando il fatto che lo genera cessa |
| **Amministrativo** | `ADMIN`, `SEGRETERIA`, `RDZ`, `AEZ`, `MCZ`, `IABZ`, `ISZ` | Assegnazione esplicita da interfaccia | Solo manuale |

Essere capogruppo è un **fatto della Comunità Capi**, non una concessione della
piattaforma: risulta dal PDF di autorizzazione. Quando il fatto cambia, il ruolo deve
seguirlo.

**Sincronizzazione all'import.** Il `Ruolo` di tipo `CG`, con perimetro sul gruppo,
si allinea a `CensimentoCapo.is_capogruppo`:

- il capo compare come `CAPO GRUPPO` nell'autorizzazione → il ruolo viene aperto (o
  riaperto) sul gruppo corrispondente;
- il capo si trasferisce a un altro gruppo → il ruolo sul gruppo di **provenienza** viene
  chiuso (`data_fine` alla data di rilevazione, `attivo = False`). Se nel gruppo di
  destinazione risulta capogruppo, ne riceve uno nuovo su quel perimetro;
- il capo resta nel gruppo ma perde l'incarico → il ruolo viene chiuso.

**La revoca è una chiusura, non una cancellazione.** Si valorizza `data_fine`, il record
resta e l'operazione è tracciata in auditlog e riportata in una sezione del report di
importazione. Rimane quindi visibile chi era CG e fino a quando, ed è possibile
correggere a mano un import sbagliato.

**Effetto a cascata sulle deleghe (D-26).** La chiusura del ruolo `CG` revoca le deleghe
che ne discendono. È l'aspetto più importante di questa decisione: senza, un capogruppo
che si trasferisce lascerebbe dietro di sé persone con accesso attivo a un gruppo a cui
nessuno dei due appartiene più.

**Perimetro della revoca.** Si chiudono **solo** i ruoli il cui perimetro è il gruppo
lasciato. I ruoli di Zona — `SEGRETERIA`, `RDZ`, `MCZ`, `IABZ`, `AEZ`, `ISZ` — non
dipendono dal gruppo di appartenenza e **non** vengono toccati da un trasferimento: un
membro del Comitato di Zona che cambia gruppo resta membro del Comitato.

**Account.** La sincronizzazione agisce sul `Ruolo` solo se il capo ha un account
collegato (`Capo.utente`). Se non ce l'ha, non c'è nulla da aprire o chiudere: il ruolo
verrà creato all'attivazione dell'account, sulla base del censimento corrente.

### D-31 — Capi senza incarico: «A disposizione»

Un capo censito che nell'anno non ha alcun incarico in unità è **a disposizione** del
proprio gruppo. Non è un'assenza di dato: è una posizione di servizio, e come tale va
mostrata, filtrata ed esportata.

**Come si ottiene.** È un valore **derivato**, non letto dal PDF: nessuna autorizzazione
contiene la dicitura «A disposizione». Segue lo stesso trattamento di `branca` e
`is_capogruppo` (D-08), cioè si calcola all'import e si memorizza sul censimento:

```
CensimentoCapo.a_disposizione = (nessun IncaricoUnita attivo per quel capo in quell'anno)
```

dove «attivo» significa `cessato_il` nullo (D-32). Ricalcolato a ogni importazione delle
autorizzazioni, a ogni assegnazione manuale di incarico e **a ogni trasferimento
rilevato**: chi cambia Co.Ca. torna a disposizione fino a nuovo incarico. **Non si crea alcun record
sintetico in `IncaricoUnita`**: quella tabella contiene solo ciò che il PDF dichiara, e
inserirvi una funzione inventata violerebbe il vincolo di non fabbricare dati.
`A_DISPOSIZIONE` esiste quindi come voce del vocabolario delle funzioni **solo ai fini di
visualizzazione e raggruppamento**, mai come valore persistito.

Conseguenze:

- **Branca**: un capo a disposizione non ha branca di servizio (`NON_ASSEGNATA`), e non
  entra in nessuna pattuglia di branca.
- **Export per funzione** (D-23): «A disposizione» è uno dei fogli, alla pari degli
  altri. Un capo che vi compare non compare in nessun altro foglio.
- **Elenchi e schede**: la posizione è mostrata esplicitamente, non come campo vuoto. Un
  campo vuoto si legge come dato mancante; «A disposizione» si legge come informazione.
- **Contributo formazione capi**: nessun effetto. Un capo a disposizione è censito e può
  partecipare ai campi come chiunque altro.
- **`E9001`**: si applica eccome, ed è anzi la posizione tipica dei censiti a livello di
  Zona, che non prestano servizio in una Comunità Capi di gruppo. Fanno eccezione i
  detentori di un ruolo di Zona, mostrati con quel ruolo — vedi D-33.
- **Segnale per la segreteria**: il report di importazione riporta il conteggio dei capi
  a disposizione per gruppo. Un numero anomalo indica quasi sempre un'autorizzazione non
  caricata o caricata parziale, non una Co.Ca. con molti capi fuori servizio.

### D-32 — Incarichi al trasferimento e assegnazione manuale

**Il trasferimento azzera gli incarichi.** Quando l'import anagrafico rileva che un capo
è passato a un'altra Co.Ca. (D-29), gli incarichi che aveva nel gruppo di provenienza
**cessano** per quell'anno: appartenevano a quella Comunità Capi, non alla persona. Il
capo entra nel gruppo di destinazione come **«A disposizione»** e ci resta finché non
accade una di queste due cose:

1. viene importata l'autorizzazione del gruppo di destinazione, che dichiara il nuovo
   incarico;
2. un incarico viene assegnato **manualmente** da interfaccia.

Questo risolve una finestra temporale reale: l'anagrafica rivela il trasferimento
appena la segreteria importa il CSV, ma l'autorizzazione aggiornata del gruppo di
destinazione può arrivare mesi dopo. Nel frattempo il capo non deve risultare né in un
limbo né, peggio, ancora capo unità in un gruppo che ha lasciato.

**Cessazione, non cancellazione.** `IncaricoUnita` acquisisce `cessato_il` (nullable):
gli incarichi del gruppo di provenienza vengono chiusi, non eliminati. Gli incarichi
*attivi* sono quelli con `cessato_il` nullo, ed è su questi che si calcolano branca,
`is_capogruppo` e `a_disposizione`.

**Assegnazione manuale.**

| Chi | Perimetro |
| --- | --- |
| Account di gruppo | Solo capi censiti nel proprio gruppo nell'anno corrente |
| `SEGRETERIA`, `ADMIN`, `RDZ` | Tutti i gruppi della Zona |

L'incarico manuale ha `origine = MANUALE`, registra autore e data, ed è tracciato in
auditlog. Vale lo stesso vocabolario chiuso di D-08: nessuna funzione libera.

**L'autorizzazione importata prevale sempre.** Quando arriva il PDF di un gruppo, esso
**sostituisce integralmente** gli incarichi di quel gruppo per quell'anno, manuali
compresi. L'assegnazione manuale è un ponte fino all'arrivo del documento ufficiale, non
una fonte concorrente. Gli incarichi manuali sostituiti vengono cessati, non cancellati,
così resta traccia di chi aveva assegnato cosa e per quanto tempo.

**Ruolo `CG` manuale.** Se l'incarico assegnato a mano è `CAPO_GRUPPO`, la
sincronizzazione di D-30 si applica identica: il ruolo di piattaforma segue l'incarico,
qualunque ne sia l'origine.

### D-33 — `E9001`: censimento di Zona e account del Comitato

**Questa decisione corregge D-02 e D-03.**

`E9001` — «COM ZONA HIRPINIA» — non è una Comunità Capi. Assolve a due funzioni distinte
che vanno tenute separate nel modello.

**1. È il contenitore di censimento a livello di Zona.** Vi sono censiti:

- l'**Assistente Ecclesiastico di Zona**, sempre censito in Zona quando la Zona ne ha uno;
- i **capi «a disposizione» della Zona**, cioè adulti censiti che non prestano servizio
  in una Comunità Capi di gruppo.

La composizione è **contingente e variabile**: non è un elenco fisso, non ha una
numerosità attesa, e nessuna logica deve dipendere da quanti o quali soci vi si trovino
in un dato anno. Nel campione 2026 i censiti sono due, ma è una circostanza di
quell'anno, non una regola.

**2. Ospita gli account funzionali del Comitato di Zona**, che sono due:

- `rzm.zonahirpinia@campania.agesci.it` — Responsabile di Zona Maschile
- `rzf.zonahirpinia@campania.agesci.it` — Responsabile di Zona Femminile

**I due RdZ sono censiti nei propri gruppi di appartenenza, non in `E9001`.** L'account
è legato all'organo, la persona al suo gruppo: sono due cose diverse e il modello non
deve confonderle.

#### Conseguenza: account e censimento sono disaccoppiati

`Utente.gruppo` identifica **l'account funzionale**, non dove la persona è censita. Per i
RdZ vale `Utente.gruppo = E9001` mentre il loro `CensimentoCapo.gruppo` è il gruppo di
origine — e può cambiare di anno in anno senza alcun effetto sull'account.

Ne discende, in forma già enunciata da D-28 ma qui decisiva: **il perimetro operativo si
ricava sempre da `gruppi_visibili(utente, anno)`, mai da `utente.gruppo`**. Per un RdZ il
perimetro è l'intera Zona e deriva dal ruolo `RDZ`, non dall'ordinale del suo account.

Un RdZ che sia anche capogruppo del proprio gruppo detiene semplicemente due ruoli
(D-28): `RDZ` sulla Zona e `CG` sul gruppo dove è censito.

#### Numero di account per gruppo

Il vincolo di unicità di D-03 è sostituito da un limite per gruppo:

```
Gruppo.account_consentiti   PositiveSmallInteger, default 1
```

`E9001` vale 2. Il controllo sta nel `clean()` del modello e nel form di attivazione, non
come `UniqueConstraint`, perché il limite non è più uniforme.

**Eccezione all'allowlist derivata (D-06):** per `E9001` l'allowlist **non** si ricava da
`EMAIL GRUPPO`, che nel campione riporta `zonahirpinia@campania.agesci.it`, un indirizzo
diverso da entrambi quelli dei RdZ. Le due voci vanno inserite manualmente e l'import non
deve sovrascriverle.

#### Incarichi e posizione dei censiti in Zona

`E9001` **non ha unità e non ha PDF di autorizzazione** — verificato: nessuno dei 15
documenti del campione lo riguarda. Quindi per i suoi censiti non esistono incarichi in
unità, e la derivazione di D-31 si applica con una sola distinzione:

- chi detiene un **ruolo di Zona** (tipicamente l'AE con `AEZ`) è mostrato con quel
  ruolo;
- tutti gli altri risultano **«A disposizione»**, che per `E9001` non è un residuo ma la
  descrizione esatta della loro posizione.

Non è un'anomalia e non va segnalata come tale: essere censiti in Zona senza incarico è
la situazione normale per questo ordinale.

#### Cosa vale e cosa non vale per `E9001`

| Ambito | Comportamento |
| --- | --- |
| Anagrafica e censimenti | **Incluso** |
| «A disposizione» (D-31) | **Incluso** |
| Account e allowlist | **Incluso**, due voci inserite a mano |
| Invito con OTP (D-20) | **Incluso** |
| Incarichi in unità | **Non applicabile**: nessuna unità, nessuna autorizzazione |
| Inserimento partecipazioni e bonifici | **Escluso** (A-8) |

**A-8 — deciso: `E9001` è escluso dal contributo formazione capi.** Non rappresenta un
gruppo reale ma un contenitore per i capi a disposizione e per l'AE di Zona, e non ha un
IBAN cui liquidare alcunché. I suoi censiti non sono selezionabili per le partecipazioni
e non compaiono nel file bonifici.

L'esclusione riguarda anche i censiti in `E9001` che prestino servizio in un gruppo
reale: poiché la competenza sul contributo segue il **censimento** (A-9), e il loro
gruppo di censimento è escluso, non esiste un gruppo competente a inserire la
partecipazione. Vedi la nota in D-34.

Il flag `Gruppo.is_comitato_zona` governa l'esclusione da partecipazioni e bonifici e
l'assenza di autorizzazione da importare. Non governa account, allowlist né derivazione
di «A disposizione».

### D-34 — Censimento e servizio sono due gruppi distinti

Un capo può essere **censito** in un gruppo e prestare **servizio** in un altro: risulta
nell'anagrafica sotto l'ordinale A e compare con un incarico nell'autorizzazione del
gruppo B. Non è un'anomalia né un trasferimento: è una situazione ordinaria.

Le due informazioni hanno fonti diverse e non vanno mai confuse:

| Concetto | Fonte autorevole | Dove vive |
| --- | --- | --- |
| **Gruppo di censimento** | `RicercaSoci.csv`, campo `ORDINALE` | `CensimentoCapo.gruppo` |
| **Gruppo di servizio** | Intestazione del PDF di autorizzazione | `IncaricoUnita.gruppo_servizio` |

`IncaricoUnita` acquisisce quindi `gruppo_servizio` (FK a `Gruppo`), valorizzato con il
gruppo la cui autorizzazione dichiara l'incarico. Un capo può avere incarichi attivi in
**più gruppi** contemporaneamente.

**L'import delle autorizzazioni non determina più il gruppo del capo.** Prima scriveva
il gruppo sul capo; ora scrive `gruppo_servizio` sull'incarico e non tocca il censimento.
Il censimento si aggiorna esclusivamente dall'anagrafica.

#### Revisione di D-29: come si rileva un trasferimento

Un trasferimento è un **cambio di gruppo di censimento**, e si rileva **solo**
dall'import di `RicercaSoci.csv`. La comparsa in un'altra autorizzazione non è più
indizio di trasferimento.

> **Correzione di un'inferenza precedente.** Il caso del socio 1690974, presente nelle
> autorizzazioni di E3471 (15/01/2026) e di E1681 (08/05/2026), era stato letto come un
> trasferimento in corso d'anno. Alla luce di questa distinzione è **ambiguo**: può
> essere un trasferimento oppure servizio in due gruppi. Solo il CSV anagrafico lo
> stabilisce, e nel campione disponibile non è verificabile. Va trattato come caso di
> test da chiarire sui dati reali, non come comportamento accertato.

Conseguenze sulle regole già scritte:

- **D-22, disattivazione**: invariata, si basa già sul solo CSV.
- **D-29, cessazione degli incarichi al trasferimento**: si applica agli incarichi nel
  gruppo di **censimento** che il capo lascia. Gli incarichi in un terzo gruppo di
  servizio **non** vengono toccati: dipendono dall'autorizzazione di quel gruppo, non da
  dove il capo è censito.
- **D-30, ruolo `CG`**: il perimetro è il **gruppo di servizio**. Un capogruppo è
  capogruppo del gruppo che guida, indipendentemente da dove è censito.
- **D-31, «A disposizione»**: vale se il capo non ha incarichi attivi in **nessun**
  gruppo. È mostrato come a disposizione del proprio gruppo di censimento.
- **D-21, caricamento xlsx**: il perimetro resta il gruppo di **censimento**, come già
  definito.
- **D-23, export**: il capo compare per il gruppo di censimento e per ciascun gruppo di
  servizio. Le due colonne sono distinte e sempre entrambe presenti; un export che ne
  riporti una sola è ambiguo e va evitato.

#### Visibilità

Un gruppo vede i capi censiti presso di sé **e** quelli che vi prestano servizio pur
essendo censiti altrove. `gruppi_visibili()` (D-28) resta il punto unico che risolve il
perimetro; la funzione simmetrica `capi_visibili(utente, anno)` deve considerare
entrambe le relazioni.

#### Competenza sul contributo: il gruppo di censimento (A-9, deciso)

Quando censimento e servizio divergono, **competente è il gruppo di censimento**: è quel
gruppo a inserire la partecipazione e a riceverne il bonifico.

La scelta ha tre effetti che semplificano il modello:

- **nessuna ambiguità con più gruppi di servizio.** Il censimento è unico per anno
  (`unique_together` su `CensimentoCapo`), quindi il competente è sempre uno solo e non
  serve chiedere all'utente di sceglierlo;
- **coerenza con la ri-attribuzione** di D-29. Un trasferimento *è* un cambio di gruppo
  di censimento, e la competenza segue il censimento: le due regole descrivono lo stesso
  movimento, e la partecipazione si sposta esattamente quando cambia il competente;
- **il perimetro di D-21** (caricamento xlsx delle partecipazioni), già definito sul
  censimento dell'anno, resta valido senza modifiche.

Il gruppo di servizio non acquisisce alcun titolo sul contributo: vede il capo in
anagrafica e ne gestisce gli incarichi, ma non ne inserisce le partecipazioni.

> **Conseguenza da verificare.** Combinata con A-8, questa regola esclude dal contributo
> i censiti in `E9001` **anche quando prestano servizio in un gruppo reale**: il loro
> gruppo di censimento è escluso, e il gruppo di servizio non è competente. Riguarda l'AE
> di Zona e i capi a disposizione della Zona. Se l'intenzione era di ammetterli tramite
> il gruppo di servizio, questa è la riga da cambiare; l'esclusione piena resta comunque
> coerente, se la Zona copre già altrimenti la loro formazione.

#### Ricerca di un capo censito altrove (A-9, deciso)

Per assegnare un incarico a un capo censito in un altro gruppo (D-32), un account di
gruppo lo cerca **esclusivamente per codice socio**. Nessuna ricerca per cognome, nessun
elenco sfogliabile, nessun suggerimento automatico: chi assegna l'incarico conosce già la
persona e ne ha il codice. Un campo di ricerca libero trasformerebbe ogni account di
gruppo in un motore di interrogazione sull'anagrafica dell'intera Zona.

La ricerca restituisce i soli dati necessari a confermare l'identità e ad assegnare
l'incarico — nome, cognome, gruppo di censimento — mai recapiti né dati anagrafici.
L'assegnazione è notificata al gruppo di censimento e alla segreteria, e registrata in
auditlog.

Per `SEGRETERIA`, `ADMIN` e `RDZ` esiste la via alternativa dell'**import
dell'autorizzazione** del gruppo di servizio, che popola gli incarichi in blocco senza
ricerche manuali.

---

## 3. Stack

| Ambito | Scelta |
| --- | --- |
| Linguaggio | Python ≥ 3.14 |
| Framework | Django ≥ 6.0 |
| Database | PostgreSQL ≥ 17 |
| Gestione ambiente | `uv` + `pyproject.toml` (hatchling), `mise` per i task |
| Autenticazione | `django-allauth` (email + MFA), `django-axes` |
| Audit | `django-auditlog` |
| Permessi oggetto | nessuna dipendenza dedicata: visibilità e perimetro sono nel service layer (`gruppi_visibili()`, `partecipazioni_visibili()`, D-13) |
| Impersonificazione | `django-hijack` (D-27) |
| Macchine a stati | `django-fsm-2` |
| Parsing autorizzazioni | `pdfplumber` (parser interno, D-07) |
| Export | `openpyxl` (XLSX), `csv` stdlib, `WeasyPrint` (PDF report) |
| Frontend | Bootstrap 5 via `django-agesci-campania-theme >= 2.3.0` |
| Qualità | `ruff`, `black`, `mypy`, `pytest` + `pytest-django` |
| CI | GitHub Actions |
| Invio email | SMTP, Gmail API (`google-auth`), Microsoft Graph (`msal`) — extra opzionali |
| Server | `gunicorn` |

---

## 4. Struttura del repository

```
catello-hirpinia/
├── .github/workflows/ci.yml
├── config/
│   ├── settings/{base,dev,prod,test}.py
│   ├── urls.py, wsgi.py, asgi.py
├── apps/
│   ├── core/            # template base, context processor, utility
│   │   └── email/       # backend di invio: SMTP, Gmail, Microsoft Graph
│   ├── organizzazione/  # Gruppo, AnnoAssociativo, AllowlistGruppo
│   ├── accounts/        # Utente, Ruolo, Delega, permessi, allauth adapter
│   ├── anagrafica/      # Capo, IncaricoUnita, Importazione*, importer
│   └── contributi/      # Campagna, TipologiaCampo, Partecipazione,
│                        # Contributo*, calcolo.py, visibilita.py, bonifici.py
├── docker/
├── docs/Catello_Progettazione.md
├── static/, templates/
├── compose.yaml, compose.prod.yaml, configure-prod.sh
├── pyproject.toml, .mise.toml, .env.example
├── CLAUDE.md, README.md, LICENSE, .gitignore
└── manage.py
```

---

## 5. Modello di dominio

### 5.1 `organizzazione`

**`Gruppo`**

| Campo | Tipo | Note |
| --- | --- | --- |
| `codice` | Char(8) **PK** | Ordinale AGESCI, es. `E0133` |
| `nome` | Char(100) | Es. `AVELLINO 1` |
| `is_comitato_zona` | Bool | `True` per `E9001`; esclude da account e contributi |
| `email_istituzionale` | Email | Da `EMAIL GRUPPO` del CSV |
| `indirizzo`, `civico`, `cap`, `comune`, `provincia`, `telefono` | Char | Da CSV |
| `codice_fiscale`, `denominazione_sociale`, `parrocchia`, `diocesi` | Char | Da CSV |
| `iban`, `intestazione_conto` | Char | Inseriti dal gruppo, validati (D-14) |
| `data_autorizzazione` | Date, null | Ultima `data_aggiornamento` importata (D-09) |
| `origine` | `IMPORT` / `MANUALE` | Creato da import Buona Caccia o da interfaccia (D-24) |
| `account_consentiti` | PositiveSmallInt, default 1 | `E9001` vale 2 (D-33) |

Lo stato attivo/disattivo **non è un campo di `Gruppo`**: vive in `StatoGruppoAnno` e si
risolve con `Gruppo.e_attivo(anno)` (D-24).

**`StatoGruppoAnno`** — `gruppo`, `anno_scout`, `attivo`, `motivo`, `disposto_da`,
`disposto_il`; `unique_together = ("gruppo", "anno_scout")`.

**`AnnoAssociativo`** — `anno` (int, unique, = anno di chiusura), proprietà
`data_inizio` (1/10/anno−1) e `data_fine` (30/9/anno).

**`AllowlistGruppo`** — `codice_gruppo`, `email`, `origine` (`IMPORT` | `MANUALE`),
`creata_il`, `creata_da`.

### 5.2 `accounts`

**`Utente(AbstractUser)`** — vedi D-03. Stati: `ATTIVO`, `IN_ATTESA`, `SOSPESO`.

**`Ruolo`** — `utente`, `tipo`, `gruppo` (per `CG`), `branca` (per `IABZ`), `settore`
(per `ISZ`), `attivo`, `data_inizio`, `data_fine`, `assegnato_da`, `origine`
(`DERIVATO` per `CG`, `AMMINISTRATIVO` per gli altri — vedi D-30).

**`Delega`** — `delegante`, `delegato`, `ruolo`, `attiva`, `data_inizio`,
`data_fine` (**obbligatoria**), `note`.

**`InvitoAttivazione`** — attivazione tramite OTP (D-20), riusato anche per invitare i
delegati (D-26): `delega_pendente` FK opzionale.

Nessun vincolo di unicità su `Ruolo.utente` né su `Delega.delegato`: un utente può
detenere più ruoli e più deleghe (D-28).

### 5.3 `anagrafica`

**`Capo`** — identità persistente della persona (D-22).

| Campo | Note |
| --- | --- |
| `codice_socio` | Char **PK** |
| `nome`, `cognome`, `sesso`, `data_nascita`, `comune_nascita` | Da CSV |
| `codice_fiscale`, `nazionalita`, indirizzo/residenza | Da CSV |
| `email`, `cellulare`, `professione` | Da CSV |
| `attivo` | `False` se assente dall'ultimo import del proprio gruppo |
| `data_disattivazione` | Valorizzata alla disattivazione, azzerata alla riattivazione |
| `utente` | FK opzionale verso l'account personale |

**`CensimentoCapo`** — fotografia annuale della persona.

| Campo | Note |
| --- | --- |
| `capo` | FK |
| `anno_scout` | int |
| `gruppo` | FK — l'ordinale usato per il perimetro di D-21 |
| `branca`, `is_capogruppo` | Derivati dagli incarichi (D-08) |
| `a_disposizione` | Derivato: nessun incarico nell'anno (D-31) |
| `livello_foca`, `comunita_socio`, `status_socio`, `ingresso_coca` | Da CSV |

`unique_together = ("capo", "anno_scout")`

**`IncaricoUnita`** — nuovo rispetto a `Dashboard_Zona`.

| Campo | Note |
| --- | --- |
| `capo` | FK |
| `anno_scout` | int |
| `gruppo_servizio` | FK(Gruppo) — il gruppo la cui autorizzazione dichiara l'incarico (D-34) |
| `codice_unita` | `G1`, `L1`, `O1`, `T1`, … |
| `nome_unita` | `BRANCO/CERCHIO MISTO`, … |
| `branca` | `LC` / `EG` / `RS` / `ADULTI` / `SCONOSCIUTA` |
| `genere_unita` | `MASCHILE` / `FEMMINILE` / `MISTO` (valore dal parser) |
| `funzione` | Vocabolario chiuso (D-08) |
| `livello_foca` | int |
| `origine` | `IMPORT` / `MANUALE` (D-32) |
| `cessato_il` | DateTime null — attivo se nullo (D-32) |
| `assegnato_da` | FK(Utente) null, per gli incarichi manuali |

`unique_together = ("capo", "anno_scout", "gruppo_servizio", "codice_unita", "funzione")`
sui soli incarichi attivi (`UniqueConstraint` con `condition=Q(cessato_il__isnull=True)`).

**`Pattuglia` / `MembroPattuglia`** — pattuglie di Zona per branca (`LC`, `EG`, `RS`),
popolate a partire dagli `IncaricoUnita` con branca corrispondente.

**`TrasferimentoCapo`** — registro dei passaggi fra gruppi, vedi D-29.

**`Pattuglia` / `MembroPattuglia`** e **`IncaricoUnita`** fanno riferimento al
`CensimentoCapo` dell'anno, non al `Capo`.

**`ImportazioneCSV`** e **`ImportazioneAutorizzazioni`** — tracciano ogni esecuzione:
file, anno, conteggi, anomalie in JSON, **capi disattivati**, utente, timestamp. Report
scaricabile in CSV.

**`EsportazioneAnagrafica`** — traccia di ogni export di dati personali, vedi D-23.

### 5.4 `contributi`

**`Campagna`** — `anno` (unique), `budget`, `tetto_per_partecipazione` (default 50,00),
`data_inizio_inserimento`, `data_fine_inserimento`, `stato` (FSM), `creata_da`,
`chiusa_il`, `liquidata_il`, `riferimento_bonifico`.

**`TipologiaCampo`** — vedi D-11.

**`Partecipazione`** — `campagna`, `capo` (**`on_delete=PROTECT`**, D-22), `gruppo`,
`tipologia`, `descrizione_altro`,
`data_inizio`, `data_fine`, `luogo`, `quota_versata`, `stato` (FSM),
`motivazione_respingimento`, `inserita_da`, `valutata_da`, `data_valutazione`.

**`AllegatoPartecipazione`** — file, tipo, caricato_da; solo per
`DOCUMENTI_RICHIESTI`.

**`ContributoPartecipazione`** — importo congelato alla chiusura, con `is_simulazione`
(D-16). È l'unico aggregato persistito: il totale per gruppo si calcola sommando le
partecipazioni secondo l'attribuzione corrente (D-29), così una ri-attribuzione sposta il
versamento senza ricalcoli.

---

## 6. Importazione anagrafica

### 6.1 CSV "Ricerca Soci" di Buona Caccia

Trappole del formato, tutte verificate sul file di test (187 righe, 81 colonne):

1. La **prima riga è `sep=,`** e va saltata.
2. Encoding **UTF-8 con BOM** → `encoding="utf-8-sig"`.
3. La maggior parte dei valori è racchiusa come `="valore"` → va scartato l'involucro.
   **Le date no**: `25/02/1981` è nudo.
4. Ogni riga dati ha una **virgola finale**: 81 intestazioni contro 82 campi.
   `csv.DictReader` gestisce l'eccedenza in `restkey` senza slittamento di colonne;
   **pandas con impostazioni di default corromperebbe silenziosamente l'allineamento**.
   Usare `csv.DictReader`. Se in futuro servisse pandas, obbligatorio `index_col=False`.
5. Le colonne `INCARICO`, `UNITA INCARICO`, `INCARICO IN ZONA`, `INIZIO MANDATO`,
   `SCADENZA MANDATO` sono **vuote** nell'export filtrato sulle Comunità Capi (verificato:
   0 valorizzate su 187). Gli incarichi **non** sono ricavabili da qui: servono i PDF.
6. `BRANCA` vale sempre `Adulti` e `TIPO UNITA` sempre `` COMUNITA` CAPI `` nello stesso
   export: non usarli per dedurre la branca di servizio.

**Disattivazione dei capi assenti (D-22, D-29).** Al termine della scrittura, l'import
calcola il delta sui gruppi presenti nel file: un capo che aveva un censimento e non
compare in **nessuna** riga dell'import passa ad `attivo = False`. Se compare sotto un
ordinale diverso non è un'uscita ma un **trasferimento**: si aggiorna il censimento e si
registra in `TrasferimentoCapo`. Questo è l'**unico** punto in cui si rileva un
trasferimento (D-34): l'import delle autorizzazioni non ne rileva mai. Nessuna cancellazione, mai. I capi dei gruppi **non**
presenti nel file restano invariati. Disattivati e trasferiti sono due sezioni distinte
del report.

Chi può eseguire: ruoli da `SEGRETERIA` in su.

### 6.2 PDF di autorizzazione

Flusso: upload multiplo → per ogni file `apps.anagrafica.parser.parse_pdf()` → ordinamento per
`data_aggiornamento` crescente → controllo contro `Gruppo.data_autorizzazione` (D-09) →
scrittura `IncaricoUnita` → derivazione di `branca`, `is_capogruppo` e pattuglie →
report anomalie.

**Il gruppo dell'autorizzazione è il gruppo di servizio (D-34)**, non il gruppo del capo:
si scrive su `IncaricoUnita.gruppo_servizio` e **non** aggiorna `CensimentoCapo.gruppo`.
Un capo che compare nell'autorizzazione di un gruppo diverso da quello di censimento non
è un trasferimento: presta servizio altrove.

**Derivazione della branca principale** (porting da `Dashboard_Zona`, esteso): prima
branca fra `LC`/`EG`/`RS` presente negli incarichi del capo; se assente,
`SUPPORTO_GRUPPO`/`SUPPORTO_AZIONE_EDUCATIVA` → `SG`, `AE_GRUPPO`/`AE_UNITA` → `AE`;
altrimenti invariata.

**Capigruppo:** azzeramento in blocco di `is_capogruppo` per l'anno, poi riassegnazione
in base agli incarichi `CAPO_GRUPPO`. Comportamento portato e da mantenere: senza il
reset, un capogruppo uscente resterebbe tale. Il `Ruolo` di piattaforma `CG` si allinea
allo stesso calcolo (D-30), deleghe comprese.

**A disposizione:** i capi censiti senza alcun incarico **attivo** nell'anno ricevono
`a_disposizione = True` (D-31). Il flag va azzerato e ricalcolato a ogni import, non
aggiornato in modo incrementale.

**Sostituzione integrale (D-32):** l'autorizzazione importata sostituisce tutti gli
incarichi di quel gruppo per quell'anno, **inclusi quelli assegnati manualmente**. La
sostituzione cessa i precedenti (`cessato_il`), non li cancella.

**Trasferimenti (D-29, D-32):** i capi risultati trasferiti vedono cessati gli incarichi
del gruppo di provenienza e passano ad «A disposizione» nel gruppo di destinazione, in
attesa dell'autorizzazione o di un'assegnazione manuale.

Un capo presente nei PDF ma assente in anagrafica **non viene creato**: finisce nel report
anomalie. L'anagrafica CSV è la fonte autorevole delle persone.

---

## 7. Flusso operativo del contributo

1. **Apertura** (segreteria): crea la campagna dell'anno, imposta budget, tetto e
   finestra di inserimento.
2. **Inserimento** (gruppi): ogni gruppo inserisce le partecipazioni dei propri capi,
   una alla volta oppure caricando un file xlsx (D-21). `quota_versata` precompilata da
   `TipologiaCampo.quota_default`. Solo capi **attivi**, censiti nell'anno e
   appartenenti al gruppo. Segreteria, `ADMIN` e `RDZ` possono caricare per tutti i
   gruppi. Se il capo si trasferisce, la partecipazione viene ri-attribuita al nuovo
   gruppo, che diventa destinatario del bonifico (D-29).
3. **Valutazione** (`IN_VALUTAZIONE`): CFM/CFA/CCG passano automaticamente ad
   `APPROVATA` (la segreteria verifica solo l'effettiva partecipazione). Le altre sono
   valutate dal Comitato, con facoltà di richiedere documentazione.
4. **Simulazione** (segreteria): calcolo a vuoto, ripetibile.
5. **Chiusura** (`CHIUSA`): calcolo definitivo, importi congelati, visibilità
   cross-gruppo sbloccata. Richiede IBAN validi e nessuna partecipazione pendente.
6. **Bonifici**: export CSV/XLSX, un'unica disposizione dopo il 20 settembre.
7. **Liquidazione** (`LIQUIDATA`): registrazione di data e riferimento del bonifico.

---

## 8. Invio delle email

### 8.1 Architettura

Un solo punto di configurazione (`EMAIL_PROVIDER`), un solo punto di traduzione
(`apps/core/email/__init__.py::backend_path()`), nessuna conoscenza del provider nel
codice applicativo. Un provider sconosciuto solleva `ImproperlyConfigured`
**all'avvio**: è preferibile un mancato boot a una piattaforma che gira senza mandare
email di verifica.

```
apps/core/email/
├── __init__.py      mappa EMAIL_PROVIDER -> backend, backend_path()
├── base.py          ApiEmailBackend: MIME, fail_silently, cache del token
├── gmail.py         GmailServiceAccountBackend, GmailOAuthBackend
└── microsoft.py     MicrosoftGraphBackend
```

`base.ApiEmailBackend` implementa già la parte comune fra Gmail e Graph: conversione del
messaggio Django in MIME (`message.message().as_bytes(linesep="\r\n")`), rispetto di
`fail_silently`, cache del token di accesso e logging che **non registra mai il corpo
del messaggio né il token**. Le sottoclassi implementano solo `_richiedi_token()` e
`_invia_mime()`.

I token di accesso durano un'ora: vanno tenuti nella cache di Django (chiave distinta
per provider), non richiesti a ogni invio. Su risposta `429` o `5xx` serve un retry con
backoff esponenziale, massimo 3 tentativi.

Le dipendenze dei provider sono **extra opzionali** in `pyproject.toml`
(`uv sync --extra gmail`, `uv sync --extra microsoft`): un deploy SMTP non installa né
`google-auth` né `msal`.

### 8.2 Gmail — service account (consigliato)

Richiede Google Workspace. Il service account impersona la casella mittente tramite
**delega a livello di dominio**; non esiste alcun token utente da rinnovare e un cambio
password della casella non interrompe l'invio.

Configurazione lato Google:

1. Progetto in Google Cloud Console, API Gmail abilitata.
2. Service account con chiave JSON.
3. In Admin Console Workspace → *Sicurezza → Controllo API → Delega a livello di
   dominio*: autorizzare il Client ID del service account **solo** per lo scope
   `https://www.googleapis.com/auth/gmail.send`.

Implementazione: `google.oauth2.service_account.Credentials.from_service_account_info(...)`
con `.with_subject(GMAIL_MITTENTE)` e scope `gmail.send`; invio in POST su
`https://gmail.googleapis.com/gmail/v1/users/me/messages/send` con il MIME in
base64 **url-safe** nel campo `raw`.

La chiave JSON sta in `.env` (o in un file montato read-only), mai nel repository.
Rotazione annuale.

### 8.3 Gmail — OAuth utente (`gmail.send`)

Alternativa quando la delega di dominio non è disponibile. Si usano client id, client
secret e refresh token; l'access token si rinnova da solo.

Vincoli da conoscere prima di sceglierla:

- un'app con schermata di consenso **esterna** in stato *Testing* riceve refresh token
  che **scadono dopo 7 giorni**: inutilizzabile in produzione;
- pubblicare l'app richiede la verifica Google con audit di sicurezza, perché gli scope
  Gmail sono *restricted*;
- se l'app è **interna** a un'organizzazione Workspace, non si applicano né la scadenza
  a 7 giorni né il limite di utenti di test — è l'unica configurazione OAuth utente
  praticabile;
- un cambio password della casella **revoca** il refresh token quando questo contiene
  scope Gmail: l'invio si interrompe finché non si ri-autorizza.

Per queste ragioni il service account resta la prima scelta e questa modalità è il
ripiego, non il default.

### 8.4 Microsoft 365 / Exchange Online — Microsoft Graph

È l'equivalente Microsoft del service account: autenticazione **client credentials**
(app-only), nessun utente coinvolto, nessun token da rinnovare a mano.

Configurazione lato Entra ID:

1. Registrazione applicazione; annotare `tenant_id` e `client_id`.
2. Permesso **applicativo** `Mail.Send`, con consenso amministratore.
3. **Application Access Policy** (`New-ApplicationAccessPolicy` in Exchange Online
   PowerShell) per restringere l'applicazione alla **sola** casella mittente. Senza
   questo passaggio `Mail.Send` applicativo consente l'invio da qualunque cassetta del
   tenant: è il punto più importante dell'intera configurazione.
4. Segreto client con scadenza in calendario, oppure certificato.

Implementazione: `msal.ConfidentialClientApplication` con scope
`https://graph.microsoft.com/.default`; invio in POST su
`https://graph.microsoft.com/v1.0/users/{mittente}/sendMail` con il MIME in base64 e
`Content-Type: text/plain`.

**Perché non SMTP su Microsoft 365.** Microsoft sta ritirando l'autenticazione di base
per SMTP AUTH in Exchange Online: comportamento invariato fino a dicembre 2026,
disattivazione predefinita per i tenant esistenti a fine dicembre 2026 (con possibilità
di riabilitazione da parte dell'amministratore), indisponibilità per i nuovi tenant e
rimozione definitiva prevista nel 2027. Una piattaforma che entra in esercizio adesso
non deve nascere su un meccanismo con data di scadenza nota.

> *Nota:* il calendario è stato rivisto più volte da Microsoft. Va verificato sulla
> documentazione ufficiale prima del deploy.

### 8.5 SMTP con password

Mantenuto e pienamente supportato: `django.core.mail.backends.smtp.EmailBackend`
standard, con STARTTLS (porta 587) o SSL implicito (porta 465).

Casi d'uso legittimi:

- **Exchange on-premises**, dove la deprecazione di Exchange Online non si applica;
- relay SMTP interno o di ente;
- provider transazionali (Brevo, Postmark, Mailgun) con API key come password;
- Gmail con password per le app, come ripiego temporaneo.

Requisiti: cifratura sempre attiva (`EMAIL_USE_TLS` **oppure** `EMAIL_USE_SSL`, mai
entrambe, mai nessuna delle due), credenziali solo in `.env`.

### 8.6 Requisiti trasversali

- Nessuna credenziale nel repository, nei log o nei messaggi di errore.
- `DEFAULT_FROM_EMAIL` coerente con la casella autorizzata dal provider: con service
  account e Graph, inviare da un mittente diverso da quello autorizzato fallisce.
- Comando di verifica `manage.py test_email <destinatario>` che invia un messaggio di
  prova e riporta il provider attivo: serve in fase di deploy per validare la
  configurazione prima di aprire le registrazioni.
- Test con `locmem`, mai invii reali nella suite.
- Le email della piattaforma sono transazionali (verifica registrazione, reset
  password, notifiche di valutazione): volumi bassi, nessun invio massivo.

## 9. Milestone

| # | Contenuto | Dipendenze |
| --- | --- | --- |
| **M0** | Scaffold: settings split, uv, mise, Docker, tema, CI, `.env.example` | — |
| **M1** | `organizzazione` + `accounts`: Gruppo, `StatoGruppoAnno`, Utente, Ruolo, Delega multipla, `ruoli_effettivi()` e `gruppi_visibili()`, allauth, MFA, allowlist, backend email (§ 8) | M0 |
| **M1b** | Attivazione con OTP massiva (D-20), recupero autonomo (D-25), delega a iniziativa del titolare con invito (D-26), impersonificazione (D-27) | M1 |
| **M2** | Import CSV Buona Caccia: `Capo` + `CensimentoCapo`, disattivazione dei non censiti (D-22), rilevazione dei trasferimenti (D-29), report anomalie | M1 |
| **M3** | Import autorizzazioni: `IncaricoUnita`, pattuglie, derivazioni (branca, capogruppo, a disposizione), sincronizzazione del ruolo `CG` (D-30), controllo snapshot | M2 |
| **M3b** | Assegnazione manuale degli incarichi con perimetro per ruolo (D-32), servizio fuori dal gruppo di censimento (D-34) | M3 |
| **M4** | `contributi` — modelli, FSM, inserimento manuale e caricamento xlsx con perimetro per ruolo (D-21) | M2 |
| **M5** | Valutazione, `calcolo.py`, simulazione, chiusura | M4 |
| **M6** | IBAN validato, export bonifici CSV/XLSX, liquidazione | M5 |
| **M7** | Visibilità cross-gruppo, report PDF, rifiniture | M5 |
| **M7b** | Ciclo di vita del gruppo da interfaccia: disattivazione con effetto sulle partecipazioni, riattivazione, nuovo gruppo (D-24) | M5 |
| **M8** | Export anagrafica xlsx/csv con filtri e raggruppamenti (D-23) | M3 |

**M3 e M8 sono parallelizzabili** rispetto a M4–M6: i due rami condividono solo `Capo`.
**M5 è la milestone a rischio più alto**: concentra FSM, calcolo monetario e permessi.
**M1b è la seconda per rischio**: OTP, deleghe a cascata e impersonificazione sono tutte
superfici di sicurezza, e vanno implementate con test espliciti sui casi negativi
(codice scaduto, delega di secondo livello, azione preclusa in impersonificazione).

Non esistono prerequisiti esterni: il parser è già dentro il repository (D-07), quindi
M3 dipende solo da M2.

---

## 10. Decisioni operative

Tutti i punti aperti sono stati chiusi. Restano tre **verifiche** da eseguire sui dati
reali o sull'ambiente, elencate in § 10.1.

| # | Questione | Decisione |
| --- | --- | --- |
| A-1 | Parser delle autorizzazioni | Codice **internalizzato** nel progetto, nessuna dipendenza esterna (D-07) |
| A-2 | Amministratori iniziali | Creati in fase di inizializzazione con `manage.py createsuperuser`. Vanno creati **almeno due** account prima della messa in esercizio, per non avere un unico punto di fallimento sulla piattaforma che gestisce i bonifici |
| A-3 | Email transazionali | Provider selezionabile via `EMAIL_PROVIDER`: Gmail con service account (consigliato) o OAuth `gmail.send`, Microsoft 365 via Graph, SMTP con password per Exchange on-premises e provider generici. Dettaglio in § 8 |
| A-4 | Retention | **Tutte** le annualità restano consultabili a tempo indeterminato. La cancellazione è solo manuale, riservata a `ADMIN`, e passa da una conferma esplicita. Nessuna procedura automatica di purge |
| A-5 | Causale del bonifico | Configurabile in due punti: valore predefinito nella **pagina impostazioni** (accessibile da `SEGRETERIA` in su) e sovrascrivibile **al momento della generazione** dell'export. Default: `Contributo FoCa <anno> - AGESCI Zona Hirpinia` |
| A-6 | Disattivazione di un gruppo con partecipazioni | **Deciso:** nessun contributo per l'intero anno, partecipazioni `RESPINTA` con causale «Gruppo non più attivo»; quelle dei capi trasferiti seguono il capo (D-24, D-29) |
| A-7 | I RdZ nell'assegnazione manuale degli incarichi | **Deciso:** sì, stesso perimetro di segreteria e superadmin (D-32) |
| A-8 | Trattamento di `E9001` nel contributo | **Deciso:** escluso da partecipazioni e bonifici (D-33) |
| A-9 | Competenza quando censimento e servizio divergono; ricerca dei capi | **Deciso:** competente è il gruppo di **censimento**; ricerca solo per codice socio, oppure import dell'autorizzazione per segreteria/admin/RdZ (D-34) |
| A-10 | Disattivazione di un gruppo a campagna già `CHIUSA` e non ancora liquidata | **Deciso:** prima si ri-attribuiscono le partecipazioni dei capi trasferiti, poi il gruppo non viene pagato; importi degli altri invariati e somma non erogata al residuo (D-24) |

### 10.1 Verifiche pendenti

Non sono decisioni, ma controlli da fare prima o durante l'implementazione.

| # | Verifica | Quando |
| --- | --- | --- |
| V-1 | Il socio 1690974, presente nelle autorizzazioni di E3471 (15/01/2026) e E1681 (08/05/2026): trasferimento o servizio in due gruppi? Solo il CSV anagrafico lo stabilisce | Caso di test naturale per M3 |
| V-2 | La mappatura `H1`/`M1` → maschile e `I1`/`N1` → femminile, dedotta dal campione 2026. In scrittura vale comunque `genere_unita` dal parser; la tabella serve solo come controllo di coerenza | Su una seconda annualità |
| V-3 | `zonahirpinia.org` è su Google Workspace o è una casella Gmail consumer? Determina quale provider email configurare (§ 8) | Prima del deploy |

### Impostazioni di piattaforma

A-5 introduce la necessità di un modello di configurazione a riga singola, sul pattern
`SiteConfig` di `Dashboard_Zona`:

```
ImpostazioniPiattaforma  (singleton, pk=1)
    causale_bonifico_default   Char
    tetto_partecipazione_default  Decimal   # valore proposto alle nuove campagne
    email_segreteria           Email
    manutenzione               Bool
```

Modificabile da `SEGRETERIA` in su, **esclusi i delegati** (coerente con D-11).

## 11. Riferimenti

- `django-agesci-campania-theme` — https://github.com/AGESCI-Campania/django-agesci-campania-theme
- `autorizzazioni-agesci` v1.0.1 — progetto di origine del parser PDF incorporato in
  `apps/anagrafica/parser/` (Andrea Bruno, MIT)
- *Manuale AGESCI Immagine coordinata 2011*, sez. 7 (colori)
- Progetto di riferimento per il deploy: **Plancia** (AGESCI Campania)
- Gmail API, invio messaggi — https://developers.google.com/gmail/api/guides/sending
- Google OAuth 2.0, scadenza dei refresh token — https://developers.google.com/identity/protocols/oauth2
- Microsoft Graph, `sendMail` — https://learn.microsoft.com/graph/api/user-sendmail
- Deprecazione Basic auth per SMTP AUTH in Exchange Online — https://techcommunity.microsoft.com/blog/exchange/updated-exchange-online-smtp-auth-basic-authentication-deprecation-timeline/4489835
