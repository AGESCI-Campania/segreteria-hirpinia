# CLAUDE.md — Catello (AGESCI Zona Hirpinia)

Riferimento operativo per Claude Code su questo repository.
**Il documento di progettazione è `docs/Catello_Progettazione.md` ed è la fonte di
verità.** Questo file contiene i vincoli di lavoro, non le specifiche.

---

## Vincoli non negoziabili

### 1. Anti-confabulazione

- **Verifica prima di modificare.** Prima di toccare qualsiasi cosa, controlla lo stato
  reale del codice con `rg`/`grep`. Non assumere che un modello, un campo o una funzione
  esistano perché "dovrebbero".
- **Dichiara le inferenze.** Se stai deducendo qualcosa invece di leggerlo, scrivilo
  esplicitamente nella risposta. Non presentare una supposizione come un fatto.
- **Se i dati non bastano, dillo.** Meglio "non posso determinarlo dal codice
  disponibile" che una risposta plausibile e inventata.
- **Non inventare valori dai dati.** Se un valore importato non corrisponde a un
  vocabolario atteso, va nel report anomalie — mai normalizzato per somiglianza, mai
  "corretto" indovinando.

### 2. Lingua

- Interazione, commit message e documentazione: **italiano**.
- Codice di dominio (modelli, campi, label, testi utente): **italiano**
  (`Gruppo`, `Capo`, `quota_versata`, `Partecipazione`).
- Identificatori tecnici generici: inglese (`get_queryset`, `save`, `parse_pdf`).

### 3. Licenza e attribuzione

MIT, copyright Andrea Bruno. Ogni nuovo file sostanziale non deve contraddire
`LICENSE`. Non aggiungere intestazioni di licenza per file.

### 4. Ambiente

- `uv` per le dipendenze — **mai** `pip install` diretto.
- `mise` per i task: `mise run dev`, `mise run test`, `mise run lint`.
- Python ≥ 3.14, Django ≥ 6.0, PostgreSQL ≥ 17.
- Docker: in sviluppo solo il database (`compose.yaml`); in produzione tutto tranne il
  reverse proxy (`compose.prod.yaml`). Guida completa in `docs/docker.md`, vincoli
  operativi in [Docker e deploy](#docker-e-deploy) più sotto.

---

## Regole di implementazione

### Service layer unico

Queste funzioni sono l'**unica** fonte di verità. View, export, comandi di gestione e
futura API devono chiamarle, mai reimplementarne la logica:

| Funzione | Responsabilità |
| --- | --- |
| `apps/contributi/calcolo.py` | Calcolo degli importi (D-10) |
| `apps/contributi/visibilita.py::partecipazioni_visibili()` | Chi vede cosa (D-13) |
| `apps/accounts/permessi.py::ruoli_effettivi()` | Ruoli + deleghe non scadute (D-04) |

Se ti accorgi di stare scrivendo una seconda volta la stessa regola, fermati: va estratta
nel service layer.

### Denaro

- **Sempre `Decimal`**, mai `float`, in nessun punto della catena.
- Arrotondamento: `ROUND_DOWN` a 2 decimali, solo nel punto finale indicato in D-10.
- Ogni funzione di calcolo deve avere test con: divisione non esatta (es. 1000/30),
  tetto per partecipazione raggiunto, quota versata inferiore al proporzionale,
  `N = 0`, budget nullo.

### Importazioni

- Sempre dentro `transaction.atomic`.
- Sempre idempotenti: rieseguire lo stesso file non deve cambiare lo stato.
- Sempre con report anomalie persistito e scaricabile.
- La logica di parsing sta in una **funzione pura**, chiamata dalla view. Non scrivere
  logica di importazione dentro una view: preclude il passaggio ad asincrono.

### Importazioni con perimetro e cancellazioni

- Il perimetro per ruolo del caricamento partecipazioni (D-21) è un **controllo di
  sicurezza**: una riga fuori perimetro è un errore bloccante segnalato, mai una riga
  scartata in silenzio. Il controllo si fa contro il `CensimentoCapo` dell'anno, non
  contro il gruppo indicato nel file.
- Ogni import massivo ha due fasi: anteprima e conferma. Nessuna scrittura prima della
  conferma esplicita.
- **Non cancellare mai capi automaticamente** (D-22). Assente dall'import = `attivo`
  a `False`, reversibile. `Partecipazione.capo` è `PROTECT`: se una cancellazione
  solleva `ProtectedError`, è il comportamento voluto, non un bug da aggirare.
- La disattivazione si applica solo ai gruppi presenti nel file importato, e solo ai capi
  assenti da **tutte** le righe: chi compare sotto un altro ordinale si è trasferito
  (D-29), non è uscito.
- **Censimento e servizio sono gruppi diversi (D-34).** `CensimentoCapo.gruppo` viene solo
  dal CSV anagrafico; `IncaricoUnita.gruppo_servizio` viene solo dall'autorizzazione.
  L'import delle autorizzazioni **non** deve mai scrivere sul censimento.
- Un trasferimento si rileva **solo** dal CSV anagrafico. Comparire nell'autorizzazione di
  un altro gruppo significa prestarvi servizio, non essersi trasferiti.
- Un capo può avere incarichi attivi in più gruppi: nessuna query deve assumerne uno solo.
- **La competenza sul contributo segue il censimento, non il servizio** (D-34). Il gruppo
  di servizio gestisce gli incarichi, non inserisce partecipazioni.
- La ricerca di un capo censito altrove è **solo per codice socio esatto**: niente ricerca
  per cognome, niente elenco sfogliabile, niente autocompletamento. Restituisce nome,
  cognome e gruppo di censimento, mai recapiti.
- **`Capo` non ha il campo `gruppo`.** Il gruppo di un capo esiste solo relativamente a
  un anno, in `CensimentoCapo`. Se stai scrivendo `capo.gruppo`, il modello ti sta
  dicendo che manca l'anno.
- `Partecipazione.gruppo` **si aggiorna** quando il capo si trasferisce: il contributo
  segue il capo (D-29). Ogni ri-attribuzione va tracciata con il gruppo di provenienza.
- **Non congelare i totali per gruppo.** Alla chiusura si congelano gli importi per
  partecipazione; il totale di gruppo e il file bonifici si calcolano alla generazione.
  Un aggregato congelato impedirebbe di spostare il versamento (D-29).
- Un respingimento senza causale non deve essere possibile, in nessun percorso, nemmeno
  in quelli automatici (D-24).
- Disattivando un gruppo, l'ordine è sempre: **prima** ri-attribuire le partecipazioni dei
  capi trasferiti, **poi** respingere o non pagare il resto. Invertirlo penalizza capi che
  sono già in un gruppo attivo (D-24).
- Una disattivazione a campagna `CHIUSA` **non ricalcola** gli importi degli altri gruppi:
  la somma non erogata va nel residuo. A `LIQUIDATA` non si tocca nulla.
- L'import **sincronizza** il ruolo `CG`, che è derivato dall'incarico (D-30): apertura,
  chiusura sul gruppo di provenienza in caso di trasferimento, e revoca a cascata delle
  deleghe che ne discendono. Chiusura significa `data_fine` valorizzata, **mai** delete.
- L'import **non tocca** i ruoli amministrativi (`ADMIN`, `SEGRETERIA`, `RDZ`, `MCZ`,
  `AEZ`, `IABZ`, `ISZ`): non dipendono dal gruppo di appartenenza.
- «A disposizione» (D-31) è un flag **derivato** su `CensimentoCapo`, ricalcolato da zero
  a ogni import, a ogni assegnazione manuale e a ogni trasferimento rilevato. Non creare
  record sintetici in `IncaricoUnita` con funzione `A_DISPOSIZIONE`. Nell'export anagrafica
  (D-23) i capi «a disposizione» mostrano comunque unità «COMUNITA' CAPI» e branca Co.Ca.
  (`BrancaUnita.ADULTI`): è un valore convenzionale calcolato in `esportazione.py`, non un
  `IncaricoUnita` reale.
- La mappatura unità → branca (`_branca()` in `parser/autorizzazioni.py`, D-08/§5.3) è:
  BRANCO/CERCHIO → L/C, REPARTO → E/G, CLAN/FUOCO → R/S, COMUNITA (CAPI) → Adulti/Co.Ca.
  Un capo può avere più incarichi in branche diverse contemporaneamente: Co.Ca. emerge
  solo quando non c'è **nessun altro** incarico attivo nell'anno (coincide con «a
  disposizione»), mai come branca assegnata "di default" in presenza di altri incarichi.
- Gli incarichi non si cancellano: si cessano (`cessato_il`). «Attivo» significa sempre
  `cessato_il__isnull=True` — filtro obbligatorio in ogni query su `IncaricoUnita`.
- L'autorizzazione importata **sostituisce** gli incarichi manuali di quel gruppo per
  quell'anno (D-32). Il manuale è un ponte, non una fonte concorrente: non scrivere
  logica che lo preservi. La sostituzione resta automatica, ma non silenziosa: l'anteprima
  segnala con un avviso (non bloccante) ogni incarico manuale che verrà sostituito, prima
  della conferma esplicita già prevista dal flusso a due fasi.
- **D-09, snapshot delle autorizzazioni**: un PDF con `data_aggiornamento` **strettamente
  precedente** a `Gruppo.data_autorizzazione` viene scartato; **uguale** viene applicato
  (reimport dello stesso snapshot, deve sovrascrivere senza errore). Solo l'anteriorità
  stretta è un errore bloccante.
- **Non assumere un solo account per gruppo**: il limite è `Gruppo.account_consentiti`,
  e la Comitato di Zona ne ha due (D-33).

### Ricerca soci: tre perimetri distinti, non unificare

Esistono tre endpoint/funzioni di ricerca soci, ciascuno con perimetro e finalità diversi
per decisione esplicita di prodotto. Non riusare l'uno al posto dell'altro, non fonderli
"per DRY": la differenza è la regola, non una duplicazione accidentale.

| | `cerca_capo_per_codice_socio` (D-34) | `RicercaSociAutocompleteView` (M7) | `PartecipazioniRicercaSociAutocompleteView` (M14) |
| --- | --- | --- | --- |
| File | `apps/anagrafica/incarichi.py` | `apps/anagrafica/views.py` | `apps/contributi/views.py` |
| Usato da | "Cerca capo censito altrove" (Gestione gruppo) | Assegnazione incarico manuale | Inserimento manuale partecipazione |
| Perimetro | Nessuno: cerca su tutta l'anagrafica | Tutti i gruppi (non `gruppi_visibili`), per decisione utente | `gruppi_visibili(utente, anno)`, **esclude E9001** (A-8) |
| Match | Solo codice socio **esatto** | Nome, cognome, gruppo, codice socio (parziale) | Nome, cognome, gruppo, codice socio (parziale) |
| Elenco sfogliabile | **No** | Sì | Sì |
| Campi restituiti | Nome, cognome, gruppo di censimento — mai recapiti | Nome, cognome, gruppo (+ `gruppo_codice` per precompilare) | Nome, cognome, gruppo |

Punti da non confondere:
- Il perimetro di D-34 e quello di M14 sembrano simili (entrambi legati al censimento) ma
  non coincidono: D-34 non ha perimetro di gruppo perché è pensato per capi già fuori dal
  perimetro dell'utente (per questo niente elenco, solo match esatto); M14 filtra invece su
  `gruppi_visibili()` perché l'inserimento partecipazioni deve restare dentro il perimetro
  di chi inserisce.
- M7 è l'unico dei tre a coprire esplicitamente **tutti** i gruppi indipendentemente dal
  ruolo di chi cerca: è una decisione di prodotto della milestone, non un'omissione del
  filtro di perimetro.
- Solo M14 esclude E9001 esplicitamente (i censiti in Comitato di Zona non generano
  contributo, A-8): non è un caso che gli altri due non lo facciano, dato che la ricerca
  capo/incarico non ha lo stesso vincolo.

### Ruoli, perimetro, impersonificazione

- **Mai ricavare il perimetro da `utente.gruppo`.** Quel campo identifica l'account
  funzionale, non i gruppi su cui l'utente può operare: si usa sempre
  `gruppi_visibili(utente, anno)`. Un utente può avere più ruoli e più deleghe (D-28).
- **Mai leggere `Gruppo.attivo`**: non esiste. Lo stato è per anno associativo, si
  ottiene solo da `Gruppo.e_attivo(anno)` (D-24).
- La revoca o la scadenza di un ruolo deve revocare a cascata le sue deleghe (D-26).
  Se stai scrivendo un filtro sulle deleghe che non guarda il ruolo di origine, manca
  quel pezzo.
- **La revoca di un ruolo esplicito (RDZ/ADMIN/SEGRETERIA/ecc.) passa sempre da
  `apps/accounts/ruoli.py::revoca_ruolo_esplicito()`** (D-35), mai da una scrittura
  diretta di `Ruolo.attivo`/`data_fine` in una view o da Django admin: è l'unico punto
  che fa la cascata sulle deleghe e, per RDZ, sul `CG` derivato di E9001
  (`sincronizza_cg_comitato_zona`). Un `Ruolo(origine=DERIVATO)` non si revoca mai da
  qui: si chiude da solo quando cessa la condizione che lo genera
  (`sincronizza_ruoli_cg`/`sincronizza_cg_comitato_zona`).
- **Un CG ha ruolo attivo su un solo gruppo reale** (D-35); l'unica eccezione è il `CG`
  derivato su `E9001` per chi ha ruolo `RDZ` diretto, che può coesistere col `CG` del
  proprio gruppo di censimento. Non scrivere codice che assuma un CG possa avere più di
  un gruppo reale contemporaneamente.
- Le azioni precluse in impersonificazione (D-27) si verificano nel service layer, non
  nel template: nascondere un pulsante non è un controllo di accesso.
- Ogni azione compiuta in impersonificazione registra **due** identità, quella
  impersonata e quella reale.

### Codici monouso

- L'OTP di attivazione (D-20) si salva **solo come hash**, mai in chiaro, nemmeno
  temporaneamente e nemmeno nei log.
- Monouso, con scadenza; un nuovo invito revoca il precedente; tentativi limitati.
- Il codice consente di impostare la password, non di autenticarsi: non concede alcun
  permesso prima che la password sia stata impostata.

### Dati sensibili

Anagrafiche, PDF di autorizzazione e CSV di Buona Caccia contengono dati personali di
minori e adulti: non vanno versionati, non vanno allegati a issue, non vanno inclusi
nelle fixture di test.

`Gruppo.iban` e `Gruppo.intestazione_conto`:

- mai in log applicativi, mai in messaggi di errore, mai in export non bancari;
- mai in viste di elenco;
- ogni modifica tracciata da `django-auditlog`.

### Email

- Il provider si sceglie **solo** con `EMAIL_PROVIDER`. Non scrivere mai `EMAIL_BACKEND`
  a mano nei settings d'ambiente e non introdurre `if provider == ...` nel codice
  applicativo: allauth e le view usano `django.core.mail` e basta.
- I backend Gmail e Graph estendono `apps/core/email/base.py::ApiEmailBackend` e
  implementano solo `_richiedi_token()` e `_invia_mime()`. Se stai riscrivendo la
  conversione MIME o la gestione di `fail_silently`, sei nel posto sbagliato.
- **Mai loggare token, segreti client, chiavi JSON o il corpo dei messaggi.** In caso di
  errore si registrano provider, numero di destinatari ed eccezione, nient'altro.
- Le dipendenze dei provider sono extra opzionali (`--extra gmail`, `--extra microsoft`):
  non spostarle fra le dipendenze obbligatorie.
- I test usano il provider `locmem`. Nessun test deve inviare email reali.
- **Il contenuto delle 6 email applicative passa da `TemplateEmail` (M8), mai più
  `render_to_string` + `send_mail` diretti.** Unico punto di invio:
  `apps/core/invio_email.py::invia_email_template()`. Il corpo (`corpo_html`/
  `corpo_testo`) è renderizzato con il motore ridotto di `apps/core/template_email.py`
  (solo placeholder `{{ variabile }}`, **mai** tag Django `{% %}`, perché il contenuto
  arriva da un form via interfaccia): non usare mai il motore template completo di
  Django su `corpo_html`/`corpo_testo`. Il fallback quando il record manca/è vuoto legge
  la sorgente grezza dei file `.txt` esistenti (mai renderizzata con l'autoescape di
  Django, che romperebbe gli URL con `&` nella querystring) con lo stesso motore ridotto.
  `corpo_html` va sempre sanitizzato con `apps/core/invio_email.py::sanifica_html()`
  (bleach) prima dell'invio.
- **`config/settings/prod.py` blocca l'avvio se `EMAIL_PROVIDER` è `console` o
  `locmem`** (`ImproperlyConfigured`, subito dopo `DEBUG = False`): non è codice morto
  né una ridondanza col controllo di `base.py` su `EMAIL_USE_TLS`/`EMAIL_USE_SSL` — è
  un vincolo distinto, non rimuoverlo né spostarlo in `base.py` (dev/test lo usano
  legittimamente). Test in `apps/core/tests/test_settings_prod.py`.

### Tema

Usa `django-agesci-campania-theme`. **Non scrivere CSS custom** per i colori: usa le
utility del tema (`bg-ag-viola`, `text-ag-*`, `{% branca_bg %}`) e i blocchi di
`agesci_theme/base.html`. Se serve davvero una regola CSS nuova, chiedi prima.

**Eccezione dichiarata**: TinyMCE (editor rich text di `TemplateEmail.corpo_html`, M8)
porta il proprio CSS/JS di toolbar, vendorizzato in `static/vendor/tinymce/` (nessuna
API key, nessun CDN esterno — build self-hosted, licenza GPL in
`static/vendor/tinymce/LICENSE-tinymce.md`). Limitata alla sola pagina di modifica
template email: non toccare né estendere per altre parti del tema.

### Parsing PDF

Il parser vive in `apps/anagrafica/parser/autorizzazioni.py` ed è codice **portato e
validato** (derivato da `autorizzazioni-agesci` v1.0.1, stesso autore, MIT).

- **Non riscrivere le regex.** Sono il risultato di tentativi successivi su un text
  layer che mescola le porzioni di testo. Sembrano fragili perché il problema lo è.
- Ogni modifica al parser richiede la riesecuzione dei test di integrazione con le
  fixture PDF (`apps/anagrafica/tests/fixtures/pdf/2026/`), non solo dei test unitari.
- Le fixture PDF **non vanno versionate**: contengono dati personali di soci reali.
  I test si auto-escludono se assenti; non "sistemare" quello skip.
- L'API da usare nelle view è `parse_pdf(source)`, che accetta un file-like: non
  scrivere il caricato su disco solo per poterlo passare come percorso.

### Docker e deploy

Guida operativa completa: `docs/docker.md`. Qui solo i vincoli che un intervento su
Docker/deploy non deve violare:

- **`configure-prod.sh` non esegue mai comandi con privilegi elevati** (niente
  `sudo`/`systemctl`/`apt`/riavvii di servizi): genera solo file di configurazione
  (`docker/nginx/catello.conf`, `compose.prod.nginx.yaml`, `deploy/*.example`). Se un
  passo richiede privilegi di sistema, lo script stampa istruzioni per l'operatore, non
  le esegue.
- **Lo script è idempotente**: una riesecuzione senza `--force` non rigenera nulla, si
  limita a segnalare la configurazione già presente in `.deploy-config`.
- **`manage.py createcachetable` non va mai spostato in `docker/entrypoint.sh`**: non è
  idempotente (fallisce se la tabella esiste già) e romperebbe ogni riavvio successivo
  del container. Resta un passo manuale one-shot al primo deploy.
- **`docker/entrypoint.sh` esegue sempre, in questo ordine, `migrate` →
  `collectstatic` → `gunicorn`**: tutti idempotenti per costruzione. Non aggiungere
  passi non idempotenti qui: vanno documentati come manuali in `docs/docker.md`, come
  già `createcachetable`.
- **`DJANGO_SECURE_SSL_REDIRECT`/`DJANGO_SESSION_COOKIE_SECURE`/`DJANGO_CSRF_COOKIE_SECURE`
  restano `False` di default** in `config/settings/prod.py`: attivarli richiede un
  reverse proxy TLS reale già funzionante, altrimenti si genera un loop di redirect.
  Non cambiare questi default senza che sia esplicitamente richiesto.
- Nessuna delle tre opzioni di reverse proxy generate da `configure-prod.sh` configura
  TLS: è dichiarato esplicitamente nell'output dello script e in `docs/docker.md`, non
  va presentato come già pronto per un go-live.
- **Tutti i log di produzione vivono in `LOG_DIR` (`BASE_DIR/log`, montato su
  `/srv/catello/log`)**: `catello.log` (applicativo) ed `email-console.log` (se mai
  raggiungibile) condividono la stessa directory per costruzione, non per coincidenza —
  non spostare uno dei due altrove senza spostare anche il volume in
  `compose.prod.yaml`. `email-console.log` in produzione non dovrebbe mai comparire:
  vedi il vincolo su `EMAIL_PROVIDER` in [Email](#email).

---

## Checklist prima di consegnare una milestone

- [ ] `mise run lint` pulito (ruff + black + mypy)
- [ ] `mise run test` verde, con test sui casi limite del calcolo
- [ ] Migrazioni generate e applicabili su database vuoto **e** su database esistente
- [ ] Nessun `float` nel codice che tratta denaro (`rg "float\(" apps/contributi`)
- [ ] Nessuna logica duplicata rispetto al service layer
- [ ] Nessun IBAN in log, export generici o viste di elenco
- [ ] Nessuna OTP in chiaro nel database o nei log
- [ ] Gli export di anagrafica sono tracciati e usano il profilo colonne minimo per
      default
- [ ] `README.md` aggiornato se sono cambiati comandi o dipendenze
- [ ] Le deviazioni dal documento di progettazione sono elencate esplicitamente nella
      risposta, con motivazione

---

## Cosa NON fare

- Non portare `assemblee`, riunioni di pattuglia, verbali o `templates_verbali/` da
  `Dashboard_Zona`: fuori scope v1.
- Non introdurre Celery, Redis o un broker (D-17).
- Non reintrodurre `autorizzazioni-agesci` come dipendenza esterna: il codice è
  internalizzato per scelta (D-07).
- Non aggiungere procedure automatiche di cancellazione delle annualità storiche: la
  retention è illimitata e la cancellazione è solo manuale (A-4).
- Non collegare Catello a Sestante o a qualsiasi SSO.
- Non aggiungere social login.
- Non riscrivere la formula del contributo "in modo più elegante" senza test che
  dimostrino l'equivalenza.
- Non rendere obbligatorie `google-auth` o `msal`: un deploy SMTP non deve installarle.
- Non impostare contemporaneamente `EMAIL_USE_TLS` e `EMAIL_USE_SSL`.
- Non usare `pandas` per leggere i CSV di Buona Caccia senza `index_col=False`
  (§ 6.1 del documento di progettazione: la virgola finale corrompe l'allineamento).
