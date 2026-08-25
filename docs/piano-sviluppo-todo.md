# Piano di sviluppo — docs/TODO.md (Interfaccia, Altre modifiche, Nuove funzionalità)

## Contesto

`docs/TODO.md` raccoglie le richieste emerse durante il beta test di Catello: rinomine
di sezioni del menu, riorganizzazione dei punti di ingresso alla gestione anagrafica
(import, export, ricerca capo, assegnazione incarico), una nuova funzione "Gestione
gruppo" che oggi non esiste, e template email configurabili da interfaccia. L'obiettivo
è chiarire i punti di attrito segnalati dai beta tester senza intaccare le regole di
dominio già consolidate (D-XX in CLAUDE.md), separando sempre "dove si trova il
pulsante" da "chi ha il permesso di premerlo" — la seconda cosa resta nel service
layer, mai nel template.

Stile a milestone piccole e testabili, coerente con M1..M8 già completate nel progetto.
Ogni milestone è mergeable e verificabile da sola.

**Decisioni prese con l'utente** (vincolanti per l'implementazione):
- Il form "Gestione gruppo" espone tutti e 5 i campi indirizzo (`indirizzo`, `civico`,
  `cap`, `comune`, `provincia`), non solo `indirizzo`.
- L'autocompletamento per la ricerca socio (voce C) si implementa con JS vanilla +
  dropdown Bootstrap del tema, endpoint AJAX dedicato — nessuna libreria nuova.
- L'editor rich text per i template email (voce E) è **TinyMCE**.
- La ricerca socio per l'assegnazione incarico (voce C) **può** trovare capi censiti in
  *altri* gruppi (per incarichi esterni), restituendo solo nome e cognome (mai dati
  riservati). **Deviazione dichiarata**: questo è un endpoint diverso da
  `cerca_capo_per_codice_socio` (D-34, riservato a ricerca per codice socio esatto,
  nessun elenco sfogliabile) — va documentato esplicitamente nel codice come *nuova e
  distinta* eccezione al perimetro standard, con limite di risultati e senza dati
  sensibili, per non essere confuso con D-34 né usato per aggirarla altrove.

## Stato di avanzamento

Legenda: ✅ completata — 🔄 in corso — ⬜ da fare. Dettaglio per milestone nella
tabella "Riepilogo difficoltà" in fondo al documento.

## Mappa di dipendenza fra le milestone

```
M1 ✅ Rinomine testuali (Contributi→Moduli, Campagne Fo.Ca.→Contributo Fo.Ca.)  — nessuna dipendenza
M2 ✅ Allowlist gruppi → tab Amministrazione                                    — nessuna dipendenza
M3 ✅ Import unificato (voce Importa)                                           — indipendente
M4 ✅ Visualizza anagrafica: pulsanti Ricerca capo + Registro esportazioni      — dipende da M1 (label)
M5 ⬜ Gestione gruppo — modello, permessi, view base, subview incarichi         — nessuna dipendenza da M1-M4
M6 ⬜ Assegna incarico: spostamento dentro Gestione gruppo + default gruppo     — dipende da M5
M7 ⬜ Assegna incarico: ricerca con autocompletamento + branca condizionale     — dipende da M6 (stessa view)
M8 ⬜ Template email configurabili con rich text                                — indipendente, va per ultima
```

Le voci A5 e C del TODO toccano la stessa view (`AssegnaIncaricoView`): farle in
sequenza (M6 poi M7) evita di riscrivere due volte template/test.

---

## M1 — Rinomine testuali

**File**: `apps/core/menu.py` (righe 99-105).

- Sezione "Contributi" → "Moduli"; voce "Campagne Fo.Ca." → "Contributo Fo.Ca.".
  Solo le due stringhe passate a `SezioneMenu(...)` e `_voce(...)`; `url_name`
  (`contributi:campagna_lista`) resta invariato.
- **Difficoltà: bassa.** Nessuna migrazione, nessun impatto su permessi.

**Test**: aggiornare eventuali asserzioni testuali sul menu (`apps/core/tests/`).

---

## M2 — Allowlist gruppi → tab Amministrazione

**File**: `apps/core/menu.py`.

- Oggi la voce "Allowlist gruppi" (riga 93-95) è dentro `voci_anagrafica`, condizionata
  da `consentito(RUOLI_GESTIONE_GRUPPI)` (ADMIN/SEGRETERIA/RDZ, import da
  `apps.organizzazione.gruppi`). La sezione "Amministrazione" (riga 114-121) oggi
  contiene solo "Impostazioni" ed è condizionata da
  `consentito(RUOLI_GESTIONE_IMPOSTAZIONI, solo_diretti=True)`.
- `RUOLI_GESTIONE_GRUPPI` e `RUOLI_GESTIONE_IMPOSTAZIONI` sono insiemi di ruoli
  probabilmente coincidenti (ADMIN/SEGRETERIA/RDZ) ma da **verificare puntualmente**
  (`apps/core/views.py::RUOLI_GESTIONE_IMPOSTAZIONI`) prima di spostare: se divergono,
  la sezione "Amministrazione" deve comparire per **l'unione** dei due permessi, non
  richiederli entrambi, altrimenti un utente con solo permesso Allowlist perde la voce.
- Notare che `RUOLI_GESTIONE_IMPOSTAZIONI` usa `solo_diretti=True` (deleghe escluse):
  se `RUOLI_GESTIONE_GRUPPI` invece ammette deleghe, spostando la voce sotto
  Amministrazione un utente che ha Allowlist solo per delega perderebbe l'accesso
  finché non si allinea la condizione. Da decidere esplicitamente in fase di
  implementazione, non silenziosamente.
- Nessuna modifica a `apps/organizzazione/views.py`/`urls.py`: solo collocazione menu.

**Difficoltà: bassa**, attenzione media sulla condizione di visibilità della sezione.

**Test**: la voce non compare più sotto Anagrafica; compare sotto Amministrazione per
i ruoli ammessi, incluso il caso limite sopra (permesso via delega, se applicabile).

---

## M3 — Import unificato ("Importa anagrafica soci" + "Importa autorizzazioni" → "Importa")

**File coinvolti**: `apps/anagrafica/views.py`, `apps/anagrafica/urls.py`,
`apps/core/menu.py`, nuovo template `importazione_cruscotto.html`.

- I due flussi restano **backend separati**: `ImportazioneCSV`/`ImportazioneAutorizzazioni`
  sono modelli distinti, con parser distinti (`parser/buonacaccia.py`,
  `parser/autorizzazioni.py`) che **non vanno toccati** (vincolo CLAUDE.md: parsing in
  funzione pura, importazioni idempotenti e in `transaction.atomic` — già rispettato,
  non c'è motivo di fonderli).
- Nuova view "cruscotto" (es. `ImportazioneCruscottoView`) come unico punto di ingresso:
  due pulsanti/form di upload (CSV / PDF) sulla stessa pagina, più una tabella che
  concatena i due queryset (`ImportazioneCSV.objects` e
  `ImportazioneAutorizzazioni.objects`) ordinati per data con una colonna "Tipo" che li
  distingue. Non è un `UNION` SQL (modelli diversi): aggregazione in Python nel
  contesto della view.
- Le view di anteprima/conferma/dettaglio restano quelle esistenti e invariate: il
  cruscotto è solo punto di ingresso e riepilogo, non sostituisce il flusso interno a
  due fasi già presente (anteprima → conferma esplicita, già conforme al vincolo
  "nessuna scrittura prima della conferma").
- `apps/core/menu.py`: sostituire le due voci con una singola
  `_voce("Importa", "anagrafica:importazione_cruscotto", "cloud-upload")`.
- Verificare `RUOLI_IMPORT_ANAGRAFICA` (unico per entrambi i flussi, da conferma sul
  codice): se coincide, il controllo di accesso alla nuova view è unico e semplice.
- **Decisione da dichiarare**: le URL esistenti (`importazione_lista`,
  `importazione_autorizzazioni_lista`) restano raggiungibili solo come link interni dal
  cruscotto, senza redirect — non ci sono bookmark/link esterni noti da preservare in
  un progetto interno alla Zona.
- **Badge di stato (decisione presa, proposta usabilità #1)**: né `ImportazioneCSV` né
  `ImportazioneAutorizzazioni` hanno un campo di stato — il record si crea solo a
  conferma avvenuta, dentro la stessa transazione (vedi i due `Meta`/docstring dei
  modelli). Uno stato "in corso" **non esiste nei dati** e non va inventato in UI: il
  badge nella tabella del cruscotto ha quindi solo due valori, calcolati da
  `bool(anomalie)` — "Con anomalie" (`anomalie` non vuoto) / "Senza anomalie" (`anomalie`
  vuoto) — niente terzo stato.

**Difficoltà: media** — non tocca la logica di dominio, ma richiede una view di
aggregazione UI su due modelli distinti.

**Test**: la view mostra entrambi i tipi in ordine cronologico; permessi (403 per chi
non ha `RUOLI_IMPORT_ANAGRAFICA`); nessun nuovo test di idempotenza (logica invariata).

---

## M4 — "Visualizza anagrafica": pulsanti Ricerca capo e Registro esportazioni

**File**: `apps/core/menu.py`, `apps/anagrafica/views.py` (rinomina label/`<h1>`),
template `esportazione_form.html`.

- Rinominare "Esporta anagrafica" → "Visualizza anagrafica" in menu, `<title>`, `<h1>`,
  breadcrumb.
- Rimuovere dal menu le voci indipendenti "Cerca capo censito altrove" (rinominata
  "Cerca capo in servizio esterno al gruppo") e "Registro esportazioni": diventano
  pulsanti dentro `esportazione_form.html`, verso `anagrafica:ricerca_capo` e
  `anagrafica:esportazione_lista` rispettivamente, visibili solo se l'utente ha
  `RUOLI_RICERCA_CAPO` / `RUOLI_VISUALIZZAZIONE_ESPORTAZIONI` (il controllo reale resta
  nella view di destinazione, il template nasconde solo il link).
- **Punto critico da risolvere esplicitamente**: `RUOLI_EXPORT_ANAGRAFICA` (chi accede
  a "Visualizza anagrafica"), `RUOLI_RICERCA_CAPO` e `RUOLI_VISUALIZZAZIONE_ESPORTAZIONI`
  (quest'ultimo pare limitato a solo ADMIN) non sono garantiti coincidenti. Se un utente
  ha `RUOLI_RICERCA_CAPO` ma non `RUOLI_EXPORT_ANAGRAFICA`, perderebbe ogni accesso alla
  ricerca capo una volta che la voce di menu indipendente sparisce. Soluzione: allargare
  il controllo di accesso alla view "Visualizza anagrafica" all'unione dei tre permessi,
  mostrando solo i pulsanti/la tabella per cui l'utente è effettivamente autorizzato
  (nascondere la tabella di export se manca `RUOLI_EXPORT_ANAGRAFICA` ma mostrare
  comunque il pulsante di ricerca capo se ha solo quel permesso).
- **Layout (decisione presa, proposta usabilità #2)**: tab Bootstrap (`nav-tabs` del
  tema), una scheda per funzione — Esporta / Cerca capo / Registro esportazioni — non
  pulsanti in fondo pagina. Ogni scheda resta condizionata al permesso corrispondente
  come sopra: se l'utente ha una sola scheda visibile, si può renderla l'unica scheda
  attiva senza mostrare la barra di navigazione (un solo tab non ha senso da
  selezionare).

**Difficoltà: bassa-media**, per via del punto critico sui permessi disallineati.

**Test**: pulsanti visibili/non visibili per ruolo; test di regressione sul caso limite
(utente con solo `RUOLI_RICERCA_CAPO`, deve continuare a poter accedere alla ricerca).

---

## M5 — "Gestione gruppo": modello, permessi, view base, subview incarichi

Milestone più corposa. Sotto-step:

### M5.1 — Modello

- `apps/organizzazione/models.py::Gruppo`: aggiungere
  `email_alternativa = models.EmailField(blank=True)`. Migrazione dedicata.
- `codice_fiscale`, `indirizzo`, `civico`, `cap`, `comune`, `provincia` esistono già:
  nessuna migrazione per questi.
- **IBAN e intestazione conto non entrano nel form di Gestione gruppo**: non richiesti
  dal TODO e sono dati sensibili con vincoli extra (mai in log/export non bancari/viste
  di elenco, sempre tracciati da `django-auditlog` — CLAUDE.md). Da dichiarare come
  esclusione intenzionale, non dimenticanza.

### M5.2 — Service layer

- Estendere `apps/organizzazione/gruppi.py` (non creare un nuovo modulo: è già la sede
  del ciclo di vita del gruppo) con `modifica_dati_gruppo(*, utente, gruppo,
  email_alternativa, indirizzo, civico, cap, comune, provincia, codice_fiscale)`.
- Perimetro a due livelli, riusando `ruoli_effettivi(utente)` (già gestisce le deleghe):
  - `RUOLI_GESTIONE_GRUPPI` (ADMIN/SEGRETERIA/RDZ) → può modificare qualunque gruppo,
    incluso E9001 (Comitato di Zona);
  - altrimenti, ruolo `Ruolo.Tipo.CG` (diretto o per delega) con `ruolo.gruppo ==
    gruppo` → può modificare solo quel gruppo;
  - altrimenti `PermissionDenied`, sul modello di `_verifica_ruolo_gestione_gruppi`
    già presente in questo file.
- `email_istituzionale` **non è mai parametro** di questa funzione: nessun path la
  sovrascrive da qui.

### M5.3 — Form, view, url, template

- `GruppoModificaForm` (ModelForm su `Gruppo`, `fields` esplicito = i 6 campi sopra,
  `email_istituzionale` mai incluso).
- `GruppoGestioneView` (GET dati+form, POST → `modifica_dati_gruppo`), url
  `organizzazione:gruppo_gestione` con parametro `codice`.
- In `gruppo_lista.html`: il nome gruppo diventa link a `gruppo_gestione` per ogni riga
  visibile all'utente, incluso E9001 (verificare che compaia già nella queryset passata
  da `GruppoListaView`, dato che oggi la riga di E9001 nasconde i pulsanti
  Disattiva/Riattiva ma potrebbe essere comunque presente in tabella).
- **Voce menu diretta per CG (decisione presa, proposta usabilità #4)**: sì. Un CG
  senza `RUOLI_GESTIONE_GRUPPI` non vede la lista `Gruppi` (voce condizionata da quel
  permesso in `apps/core/menu.py`), quindi non avrebbe altrimenti un punto di accesso a
  `gruppo_gestione` per il proprio gruppo. Aggiungere in `voci_anagrafica` una voce "Il
  mio gruppo" visibile quando l'utente ha `Ruolo.Tipo.CG` (diretto o per delega) e
  **non** ha `RUOLI_GESTIONE_GRUPPI` (altrimenti duplicherebbe "Gruppi"), che punta
  direttamente a `gruppo_gestione` con il codice del gruppo del ruolo CG. Se l'utente ha
  più ruoli CG su gruppi diversi (caso raro ma non escluso da CLAUDE.md: "un capo può
  avere incarichi attivi in più gruppi"), la voce elenca i gruppi invece di puntare
  diretta a uno solo — da verificare in fase di implementazione se il caso si presenta
  davvero per un ruolo (non incarico) CG.
- **Breadcrumb (decisione presa, proposta usabilità #4)**: `breadcrumb()` in
  `apps/core/context_processors.py` oggi genera solo Home + Sezione + Voce quando
  `request.path` combacia esattamente con una voce di menu — le pagine figlie (come
  `gruppo_gestione/<codice>/`) mostrano solo Home, perché non sono nel menu. Estendere
  il context processor con un meccanismo esplicito per le pagine figlie (es. la view
  imposta `self.extra_context["breadcrumb_extra"] = [...]` o un attributo di classe
  risolto dal context processor) per ottenere `Anagrafica › Gruppi › <Nome gruppo> ›
  Gestione`, senza duplicare la logica di traduzione permesso→voce già presente lì.
  Questo è un'estensione del meccanismo esistente, non una riscrittura.

### M5.4 — Subview incarichi del gruppo

- Sotto-pagina/tab (url separata `organizzazione:gruppo_incarichi` o sezione della
  stessa view) che elenca `IncaricoUnita.objects.filter(gruppo_servizio=gruppo,
  cessato_il__isnull=True)` di default, con toggle per lo storico.
- **Direzione delle dipendenze fra app**: il commento in testa a
  `apps/organizzazione/gruppi.py` è esplicito — "organizzazione è la base della catena
  di dipendenze", non deve importare logica di servizio da `apps.anagrafica`. La query
  sugli incarichi in questa subview importa solo il *modello* `IncaricoUnita` (dato,
  non logica), non funzioni da `apps/anagrafica/incarichi.py`: verificare che questo
  pattern (import di un modello di un'altra app) sia già in uso altrove in
  `organizzazione` prima di darlo per scontato, altrimenti la subview va spostata come
  vista in `apps/anagrafica` che riceve il gruppo come parametro.
- **Filtro/ricerca rapida (decisione presa, proposta usabilità #5)**: riusare
  `static/js/table-filter.js` e `static/js/table-sort.js`, già presenti nel repo e usati
  per altre tabelle del tema — nessun JS nuovo da scrivere, solo applicare gli stessi
  attributi/hook della tabella alla lista incarichi.

**Difficoltà: alta** — perimetro CG-vs-Zona su una risorsa nuova (incluse le deleghe),
caso speciale E9001, verifica della direzione delle dipendenze fra app.

**Test**: CG modifica solo il proprio gruppo (anche via delega); Segreteria/RdZ/Admin
modificano qualunque gruppo incluso E9001; CG che tenta un altro gruppo →
`PermissionDenied`; `email_istituzionale` mai modificabile da questo path anche
forzando il campo nel POST; subview incarichi filtrata correttamente per
gruppo/attivo-storico e perimetro di visibilità coerente.

---

## M6 — Spostare "Assegna incarico" dentro Gestione gruppo, default gruppo di censimento

**File**: `apps/core/menu.py`, `apps/anagrafica/forms.py::IncaricoManualeForm`,
template `assegna_incarico.html`, subview di M5.4.

- Rimuovere la voce menu indipendente "Assegna incarico".
- Pulsante "Assegna incarico" nella subview incarichi (M5.4) → `AssegnaIncaricoView`
  con `gruppo_servizio` precompilato al gruppo corrente.
- `IncaricoManualeForm.gruppo_servizio` (già `ModelChoiceField` limitato a
  `gruppi_visibili`): impostare `initial` al gruppo di censimento (`CensimentoCapo.gruppo`
  dell'anno corrente) quando si arriva dalla ricerca socio (M7), o al gruppo corrente
  quando si arriva da Gestione gruppo — resta sempre modificabile (incarico esterno),
  mai readonly.
- Verificare che `_verifica_perimetro` in `apps/anagrafica/incarichi.py` accetti
  comunque il default proposto (dovrebbe, essendo il perimetro dell'utente già a monte).
- **Incarico duplicato (decisione presa, proposta usabilità #3)**: blocco, non doppia
  conferma. `assegna_incarico_manuale` verifica, prima di creare l'`IncaricoUnita`, se
  esiste già un incarico **attivo** (`cessato_il__isnull=True`) per la stessa
  combinazione capo + `gruppo_servizio` + `codice_unita` + `funzione` + `anno_scout`; se
  sì, solleva `ValidationError` (stesso pattern degli errori di perimetro già gestiti
  dalla view, nessun nuovo ramo in `AssegnaIncaricoView`). Niente flag di conferma nel
  form: un doppio click o un reinvio ripropone lo stesso errore invece di creare un
  duplicato, coerente con "gli incarichi non si cancellano, si cessano" — non c'è un
  caso legittimo di due incarichi identici attivi contemporaneamente.

**Difficoltà: media.** `assegna_incarico_manuale` non cambia; cambiano punto di
ingresso e valore iniziale. Attenzione ai test esistenti su `AssegnaIncaricoView` che
oggi presuppongono l'arrivo da `ricerca_capo` con `?codice_socio=...`.

**Test**: default `gruppo_servizio` = gruppo di censimento quando disponibile; resta
possibile scegliere un gruppo diverso; voce menu non più di primo livello; navigazione
da Gestione gruppo con parametri corretti.

---

## M7 — Ricerca socio con autocompletamento e branca condizionale

**File**: nuovo endpoint in `apps/anagrafica/views.py` (es.
`RicercaSociAutocompleteView`), `apps/anagrafica/urls.py`, nuovo script JS (stile
`static/js/table-filter.js`), `apps/anagrafica/forms.py::IncaricoManualeForm`,
`apps/anagrafica/incarichi.py::assegna_incarico_manuale`.

- **Autocompletamento** (decisione presa: JS vanilla + dropdown Bootstrap, nessuna
  libreria nuova): endpoint AJAX che restituisce un elenco limitato (max 10-20
  risultati) di soci per nome/cognome/gruppo/codice socio. Per decisione dell'utente,
  la ricerca **copre tutti i gruppi**, non solo quelli visibili all'utente, ma
  restituisce **solo nome, cognome e gruppo di censimento** (mai altri dati). Questo
  endpoint è **esplicitamente diverso** da `cerca_capo_per_codice_socio` (D-34): va
  commentato nel codice per marcare la distinzione (ricerca per nome cross-gruppo
  ammessa solo qui, con output minimale, mai riusata per il flusso di ricerca capo
  censito altrove).
  - **Gruppo nel risultato (decisione presa, proposta usabilità #6)**: il nome breve del
    gruppo di censimento compare accanto a ciascun risultato per distinguere omonimi.
    Non è un dato riservato (il nome del gruppo, a differenza di recapiti/indirizzo, non
    rientra nella restrizione D-34 sui "mai recapiti") — resta comunque **solo** il
    gruppo, mai altri campi anagrafici.
- Sostituisce l'attuale `codice_socio` come `HiddenInput` popolato solo via querystring
  in `AssegnaIncaricoView`: la nuova UI permette di digitare e scegliere dal dropdown,
  che poi valorizza il campo nascosto con il `codice_socio` scelto.
- **Branca condizionale**: `IncaricoManualeForm.branca` diventa `required=False`; JS
  lato client rende il campo obbligatorio in UI quando `funzione` è "Capo unità" o
  "Aiuto capo unità" (valori di `FunzioneIncarico`); la validazione reale resta nel
  service layer (`assegna_incarico_manuale` o `IncaricoManualeForm.clean()`) — mai
  fidarsi solo del client.
  - **Asterisco dinamico (decisione presa, proposta usabilità #7)**: lo stesso script
    che rende `branca` obbligatorio aggiunge/rimuove un asterisco accanto alla label del
    campo quando `funzione` cambia — puramente visivo, nessun nuovo stato server-side.

**Difficoltà: alta** — nessuna infrastruttura di autocomplete esistente nel progetto
(va scritta da zero: endpoint, limite risultati, JS); rischio concreto di confondere le
due regole di ricerca (D-34 vs questo nuovo endpoint) se non isolate chiaramente nel
codice e nei test.

**Test**: assegnazione con `funzione=CAPO_UNITA` e `branca` mancante → errore;
`funzione` diversa e `branca` mancante → OK; endpoint autocomplete restituisce solo
nome/cognome (mai altri campi), risultati limitati in numero; non regressione su
`cerca_capo_per_codice_socio` (D-34 invariato, nessuna ricerca per cognome in quel
flusso).

---

## M8 — Template email configurabili con rich text (TinyMCE)

Milestone più impegnativa architetturalmente. Sotto-step:

### M8.1 — Modello

- Nuovo modello `TemplateEmail` in `apps/core/models.py` (accanto a
  `ImpostazioniPiattaforma`, coerente col commento già presente su quel modello):
  `codice` (chiave stabile: `invito_attivazione`, `fine_impersonificazione`,
  `delega_creata`, `delega_revocata`, `incarico_assegnato`, `incarico_cessato` — i 6
  tipi oggi esistenti), `oggetto`, `corpo_html`, `corpo_testo` (fallback plain-text).
- **Data migration** che precompila i 6 record con i contenuti attuali dei template
  `.txt` esistenti (`templates/accounts/email/*.txt`,
  `templates/anagrafica/email/*.txt`), altrimenti il primo invio dopo il deploy
  userebbe un template vuoto.
- Tracciamento con `django-auditlog` (già usato per `Gruppo.iban`/`intestazione_conto`,
  stesso pattern): permette di vedere chi ha modificato un template e tornare indietro.

### M8.2 — Motore di sostituzione tag

- Elenco variabili disponibili per `codice`, definito staticamente in Python (non in
  DB), mostrato in UI come legenda.
- **Decisione di sicurezza da dichiarare esplicitamente**: il contenuto arriva ora da
  un admin via form, non più da un file sotto controllo di versione. Va usato un
  motore di sostituzione **ridotto** (placeholder semplici `{{ variabile }}` senza tag
  logici Django come `{% load %}`/`{% include %}`), non il motore template completo di
  Django, per non ampliare la superficie di attacco anche per utenti fidati
  (ADMIN/SEGRETERIA/RDZ non sono necessariamente sviluppatori).

### M8.3 — Renderer unico e refactor dei punti di invio

- Nuova funzione, es. `apps/core/email.py::invia_email_template(*, codice_template,
  destinatari, contesto)`: carica `TemplateEmail`, fa il render, usa
  `EmailMultiAlternatives` per inviare testo (sempre presente) + HTML (alternative),
  sanitizza l'HTML con **bleach** (nuova dipendenza) prima dell'invio. Fallback al
  contenuto hardcoded esistente se il record manca o è vuoto (mai bloccare un invio
  critico come l'attivazione account).
- Sostituire le chiamate dirette a `render_to_string(...)` + `send_mail(...)` nei
  service layer coinvolti (`apps/accounts/inviti.py`, `apps/accounts/deleghe.py` o
  segnali equivalenti, `apps/anagrafica/incarichi.py` per assegnato/cessato) con la
  nuova funzione, passando lo stesso contesto già costruito oggi.
- **Vincolo invariato**: `EMAIL_PROVIDER` resta l'unico selettore di trasporto SMTP/API
  (CLAUDE.md) — questo refactor tocca solo contenuto, non configurazione provider.
  Resta sincrono, nessun Celery/Redis (D-17).

### M8.4 — UI in "Impostazioni"

- Nuova vista `TemplateEmailListaView`/`TemplateEmailModificaView` (più adatta della
  singleton `ImpostazioniPiattaformaView` data la cardinalità N template), stessi
  `RUOLI_GESTIONE_IMPOSTAZIONI`.
- **TinyMCE** per `corpo_html`, caricato come progressive enhancement su una
  `<textarea>` semplice: se il JS non carica, il campo resta comunque modificabile come
  testo — nessuna perdita di funzionalità in caso di problemi col plugin. Assets
  TinyMCE inevitabilmente portano CSS/JS propri per la toolbar: da dichiarare come
  eccezione minima al vincolo "niente CSS custom" (limitata all'editor, non al resto
  del tema).
- Pulsante "Anteprima" che renderizza il template con un contesto di esempio prima del
  salvataggio.
- **Pulsante "Invia email di test a me stesso" (decisione presa, proposta usabilità
  #8)**: sì, accanto ad "Anteprima". Invia il template renderizzato (contesto di
  esempio) all'indirizzo email dell'utente loggato, usando la stessa
  `invia_email_template` di M8.3 — nessun percorso di invio parallelo. **Vincolo da
  CLAUDE.md**: in ambiente di test/dev il provider è `locmem`/`console`, quindi
  quest'invio non deve mai raggiungere un destinatario reale nei test automatici, solo
  in un ambiente configurato con un provider reale.

**Difficoltà: alta** — nessuna infrastruttura preesistente (modello, sanitizzazione,
editor rich text, motore tag); superficie di sicurezza nuova (HTML modificabile da UI);
refactor trasversale su più file di più app; nuova dipendenza frontend (TinyMCE) e
backend (bleach).

**Test**: rendering con tag sostituiti correttamente, tag mancanti nel contesto non
bloccano l'invio; fallback al default hardcoded se il record manca/è vuoto;
sanitizzazione rimuove markup pericoloso (`<script>`, `onerror=`); email inviata è
multipart (testo+HTML); solo `RUOLI_GESTIONE_IMPOSTAZIONI` modifica i template; non
regressione sui 6 flussi di invio esistenti con i template di default precompilati.

---

## Riepilogo difficoltà

| Milestone | Voce TODO | Difficoltà | Stato | Nota principale |
| --- | --- | --- | --- | --- |
| M1 | Contributi→Moduli | Bassa | ✅ completata | Solo stringhe |
| M2 | Allowlist→Amministrazione | Bassa | ✅ completata | Permessi non divergenti: Allowlist mantiene le deleghe, Impostazioni resta solo diretti |
| M3 | Importa unificato | Media | ✅ completata | Cruscotto aggrega in Python, badge da `bool(anomalie)`, liste esistenti raggiungibili come link |
| M4 | Visualizza anagrafica | Bassa-media | ✅ completata | Accesso view = unione dei 3 permessi, ogni scheda condizionata al proprio; nessun ruolo reale oggi ha RICERCA_CAPO/REGISTRO senza EXPORT |
| M5 | Gestione gruppo (base) | Alta | ⬜ da fare | Perimetro CG-vs-Zona, caso E9001, dipendenze fra app |
| M6 | Assegna incarico → dentro Gestione gruppo | Media | ⬜ da fare | Punto di ingresso e default, logica invariata |
| M7 | Autocomplete + branca condizionale | Alta | ⬜ da fare | Nessuna infrastruttura esistente; isolare da D-34 |
| M8 | Template email + rich text | Alta | ⬜ da fare | Nessuna infrastruttura; superficie sicurezza nuova; refactor trasversale |

---

## Proposte di usabilità aggiuntive

Discusse con l'utente il 2026-08-25: tutte accolte come decisioni di design, incorporate
nel testo della milestone corrispondente (nessuna implementazione ancora, dato che
M3-M8 sono ⬜). Nessuna era implementabile isolatamente: dipendono tutte da una
milestone non ancora costruita, salvo la #9 che è un criterio trasversale già in atto.

1. ✅ **M3** — badge di stato nella lista unificata degli import. **Decisione**: solo due
   valori, "Con anomalie"/"Senza anomalie" da `bool(anomalie)` — uno stato "in corso" non
   esiste nei dati (il record si crea solo a conferma avvenuta), non va aggiunto in UI.
   Dettaglio nella sezione M3.
2. ✅ **M4** — tab Bootstrap invece di pulsanti in fondo pagina, una scheda per funzione.
   Dettaglio nella sezione M4.
3. ✅ **M6/M7** — niente doppia conferma: blocco (`ValidationError`) in
   `assegna_incarico_manuale` se esiste già un incarico attivo identico
   (capo+gruppo+unità+funzione+anno). Dettaglio nella sezione M6.
4. ✅ **M5** — voce menu diretta "Il mio gruppo" per CG senza `RUOLI_GESTIONE_GRUPPI`;
   breadcrumb esteso con un meccanismo esplicito per le pagine figlie non presenti nel
   menu. Dettaglio nella sezione M5.3.
5. ✅ **M5.4** — filtro/ricerca rapida: riuso diretto di `table-filter.js`/`table-sort.js`
   (già caricati globalmente in `templates/base.html`), nessun JS nuovo. Dettaglio nella
   sezione M5.4.
6. ✅ **M7** — gruppo di censimento accanto a ciascun risultato dell'autocomplete: non è
   dato riservato (a differenza dei recapiti, resta comunque escluso). Dettaglio nella
   sezione M7.
7. ✅ **M7** — asterisco dinamico sulla label di `branca`, stesso script della
   obbligatorietà condizionale. Dettaglio nella sezione M7.
8. ✅ **M8** — pulsante "Invia email di test a me stesso" accanto ad "Anteprima", stesso
   `invia_email_template` di M8.3. Dettaglio nella sezione M8.4.
9. **Generale** — verificare ad ogni milestone, come criterio di accettazione, che il
   breadcrumb resti presente su ogni nuova pagina. Nessuna decisione da prendere: è già
   un criterio applicato (completato nel primo beta test), da mantenere anche per le
   pagine nuove di M3-M8.

---

## Verifica end-to-end

Per ogni milestone, dopo l'implementazione:
- `mise run test` verde, inclusi i nuovi test di permessi/perimetro elencati sopra.
- `mise run lint` pulito.
- Migrazioni applicabili su database vuoto e su database esistente (M5.1, M8.1).
- Verifica manuale nel browser con almeno due ruoli diversi per milestone (es. per M5:
  un utente CG del proprio gruppo e un utente SEGRETERIA su un gruppo altrui e su
  E9001) per confermare che il perimetro di permessi si comporti come da test.
- Per M8: invio di test reale con provider `locmem`/`console` in locale, mai verso
  destinatari reali, verificando che il messaggio generato contenga sia parte testo sia
  parte HTML sanificata.
