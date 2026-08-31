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
- **M11**: la nuova funzione "assegna ruolo direttamente" **esclude `Ruolo.Tipo.CG`**
  (resta derivato da incarico o dal percorso invito-con-gruppo, per non aprire un
  terzo punto di scrittura da allineare a D-35) e riusa il pattern di ricerca utente
  di `ImpersonaListaView` (icontains su email/username/codice socio), non la ricerca
  per email esatta stile D-34.
- **M12**: `ImpersonaListaView` senza query mostra l'elenco completo (paginato)
  invece di `Utente.objects.none()`. **Deviazione dichiarata** dal principio "niente
  elenco sfogliabile" (modellato su D-34) scritto nel docstring originale: qui il
  bersaglio è un elenco di account piattaforma, non l'anagrafica soci, e la pagina
  resta riservata a chi supera `puo_impersonare_qualcuno()` (oggi solo ADMIN diretto).
- **M10**: RDZ perde la **creazione** di inviti (`InvitoCreaView`) ma mantiene la
  **visualizzazione** dello storico (`InvitoListaView`) — nuova costante
  `RUOLI_INVITO_DIRETTO` distinta da `RUOLI_CHE_INVITANO`.

## Stato di avanzamento

Legenda: ✅ completata — 🔄 in corso — ⬜ da fare. Dettaglio per milestone nella
tabella "Riepilogo difficoltà" in fondo al documento.

## Mappa di dipendenza fra le milestone

```
M1  ✅ Rinomine testuali (Contributi→Moduli, Campagne Fo.Ca.→Contributo Fo.Ca.)  — nessuna dipendenza
M2  ✅ Allowlist gruppi → tab Amministrazione                                    — nessuna dipendenza
M3  ✅ Import unificato (voce Importa)                                           — indipendente
M4  ✅ Visualizza anagrafica: pulsanti Ricerca capo + Registro esportazioni      — dipende da M1 (label)
M4.5 ✅ Vincolo CG unico per gruppo reale + derivazione CG(E9001) da RDZ (D-35)  — nessuna dipendenza da M1-M4, prerequisito di M5
M5  ✅ Gestione gruppo — modello, permessi, view base, subview incarichi         — dipende da M4.5
M6  ✅ Assegna incarico: spostamento dentro Gestione gruppo + default gruppo     — dipende da M5
M7  ✅ Assegna incarico: ricerca con autocompletamento + branca condizionale     — dipende da M6 (stessa view)
M8  ✅ Template email configurabili con rich text                                — indipendente, va per ultima
M9  ✅ Icone nei tab della home                                                  — indipendente
M10 ✅ Invito diretto ristretto ad ADMIN/SEGRETERIA, fuso dentro "Ruoli"          — indipendente
M11 ✅ Assegna ruolo direttamente (senza invito) a un utente già attivo          — dipende da M10 (stesso template ruolo_lista.html)
M12 ✅ Elenco degli utenti impersonabili + voce di menu                          — indipendente
M13 ✅ Rifiniture breadcrumb: icona Home + Template email completo               — indipendente
M14 ✅ Autocomplete codice socio in "Inserisci partecipazione" (perimetro per ruolo) — indipendente
M15 ✅ Tipologia partecipazione "Altro (specificare)"                            — indipendente
M16 ⬜ Validazioni e campi minori (data_fine ≥ data_inizio, luogo opzionale, note) — indipendente
M17 ⬜ Quota versata obbligatoria con default 51,50€ per CCG/CFM/CFA              — dipende da M15 (stesso form)
```

M14-M17 nascono dall'unica sezione ancora aperta di `docs/TODO.md`, "Modulo contributo
Fo.Ca." → "inserisci partecipazione": 6 richieste emerse dal beta test, nessuna
corrispondente a una milestone M1-M13. M17 dipende da M15 perché entrambe toccano lo
stesso blocco JS "il campo reagisce al cambio di tipologia" in
`partecipazione_inserisci.html`: farle in sequenza evita di riscrivere due volte quella
logica.

Le voci A5 e C del TODO toccano la stessa view (`AssegnaIncaricoView`): farle in
sequenza (M6 poi M7) evita di riscrivere due volte template/test. Lo stesso vale per
M10/M11, che toccano entrambe `templates/accounts/ruolo_lista.html`.

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

## M4.5 — Vincolo CG unico per gruppo reale + derivazione CG(E9001) da RDZ (D-35)

Prerequisito di M5: la voce "Il mio gruppo" (M5.3) si appoggia al fatto che un CG abbia
al più due gruppi (il proprio + eventuale E9001). Regola completa in D-35
(`docs/Catello_Progettazione.md`), che corregge il testo precedente di D-33.

**File coinvolti**: `apps/accounts/ruoli_derivati.py`, nuovo `apps/accounts/ruoli.py`,
`apps/accounts/views.py`/`urls.py` (nuova view di revoca), `apps/anagrafica/
importazione_autorizzazioni.py`.

- **Nuovo service layer di revoca ruolo esplicito** (`apps/accounts/ruoli.py::
  revoca_ruolo_esplicito(*, utente, ruolo)`): oggi non esiste alcun flusso applicativo
  per chiudere un ruolo `RDZ`/`ADMIN`/`SEGRETERIA` — solo modifica diretta via Django
  admin, senza cascata sulle deleghe collegate (gap preesistente). La nuova funzione
  chiude il ruolo (`attivo=False`, `data_fine=oggi`), chiama
  `revoca_deleghe_di_ruolo(ruolo)` (`apps/accounts/deleghe.py`) e, se il ruolo è `RDZ`,
  richiama `sincronizza_cg_comitato_zona`. Nuova view minima di revoca (sul modello di
  `DelegaRevocaView`) per non lasciare l'admin come unica via che bypasserebbe il
  service layer.
- **`sincronizza_cg_comitato_zona(*, utente)`** in `apps/accounts/ruoli_derivati.py`,
  sullo stesso schema di `sincronizza_ruoli_cg`: se l'utente ha `RDZ` attivo diretto →
  assicura `Ruolo(tipo=CG, gruppo=E9001, origine=DERIVATO)` attivo; altrimenti chiude
  l'eventuale CG derivato su E9001. Chiamata alla creazione di un ruolo RDZ
  (`apps/accounts/inviti.py::verifica_e_completa`) e da `revoca_ruolo_esplicito`.
- **Vincolo "un solo gruppo reale"**: in `sincronizza_ruoli_cg()` e nell'import
  autorizzazioni, se lo stesso capo risulta `CAPO_GRUPPO` su più gruppi reali → anomalia
  non bloccante (mai un blocco dell'intero import, mai una scelta arbitraria di quale
  gruppo tenere).
- **Vincolo "2 CG per gruppo, 1M+1F"**: usa il sesso **estratto dal PDF stesso** per
  ogni riga `CAPO GRUPPO` (`parser/autorizzazioni.py::_RE_GENDER`, già parsato ma finora
  scartato a valle) — verificato che non serve `Capo.sesso` (fonte diversa, dal CSV
  Buona Caccia): il dato del PDF è già disponibile ed è quello legato all'incarico
  stesso — e `CensimentoCapo.livello_foca` (già usato con lo stesso significato in M8).
  Due CG attivi dello stesso sesso sullo stesso gruppo → **errore bloccante** sulla riga
  (unica eccezione allo stile "mai bloccare per dati anomali" del resto degli import,
  perché la situazione non è rappresentabile nel dominio). Un solo CG, o
  `livello_foca != 5` per uno dei due → anomalia non bloccante. Sesso non riconosciuto
  dal parser per quella riga → niente blocco per quel capo, solo anomalia informativa.

**Difficoltà: alta** — introduce un service layer nuovo (revoca ruolo, oggi assente),
un vincolo che deve convivere con lo stile "mai bloccare per dati anomali" senza
diventarne un'eccezione silenziosa, e va tenuto sincronizzato con D-33/D-35 nel
documento di progettazione.

**Test**: `revoca_ruolo_esplicito` (cascata deleghe + CG(E9001) solo per RDZ, permesso
negato altrove); `sincronizza_cg_comitato_zona` (crea/chiude, non duplica, ignora RDZ
per delega); vincolo un-solo-gruppo-reale → anomalia, import non bloccato; vincolo
2CG/1M+1F → blocco su stesso sesso, anomalia su singolo CG e su livello FoCa, nessun
blocco con sesso non valorizzato.

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
  **non** ha `RUOLI_GESTIONE_GRUPPI` (altrimenti duplicherebbe "Gruppi"). **Grazie a
  D-35 (M4.5)**, un CG ha al più due gruppi (il proprio + eventuale E9001 se anche
  RDZ): niente lista arbitraria, gestire esplicitamente i due casi — 1 gruppo → link
  diretto a `gruppo_gestione`; 2 gruppi → piccolo elenco di 2 elementi. `_voce()`
  (`apps/core/menu.py`) va esteso per accettare argomenti di `reverse()`: oggi risolve
  solo `reverse(url_name)` senza parametri, nessun precedente nel menu per voci con URL
  specifico dell'utente.
- **Breadcrumb (decisione presa)**: mixin con attributo di classe. `breadcrumb()` in
  `apps/core/context_processors.py` oggi confronta `request.path` con le URL statiche
  del menu e non ha alcun meccanismo di estensione (verificato sul codice, il docstring
  lo dichiara esplicitamente) — le pagine figlie (come `gruppo_gestione/<codice>/`)
  mostrano solo Home. Introdurre un `BreadcrumbExtraMixin` (nuovo, in `apps/core/`) con
  un attributo/metodo di classe che il context processor legge via
  `request.resolver_match.func.view_class`, per ottenere `Anagrafica › Gruppi › <Nome
  gruppo> › Gestione` sulle pagine figlie. È un context processor **globale**: la
  modifica va scritta e testata perché il comportamento delle altre pagine resti
  invariato quando l'attributo non è presente.

### M5.4 — Subview incarichi del gruppo

- Sotto-pagina/tab che elenca `IncaricoUnita.objects.filter(gruppo_servizio=gruppo,
  cessato_il__isnull=True)` di default, con toggle per lo storico.
- **Direzione delle dipendenze fra app (verificato, decisione presa)**: `grep -rn
  "anagrafica" apps/organizzazione/` non trova alcuna occorrenza — organizzazione è
  oggi completamente pulita rispetto ad anagrafica, coerente col commento di testa di
  `apps/organizzazione/gruppi.py` ("organizzazione è la base della catena di
  dipendenze"). Il pattern "importare il modello `IncaricoUnita` dentro organizzazione"
  **non è in uso altrove**: la subview va quindi scritta come vista in
  `apps/anagrafica` (non in `apps/organizzazione/gruppi.py`), che riceve il gruppo come
  parametro/URL — non un'eccezione nuova alla direzione delle dipendenze.
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

- **Fatto**: rimossa la voce menu indipendente "Assegna incarico" (`apps/core/menu.py`,
  anche l'import `RUOLI_ASSEGNAZIONE_INCARICHI` ora inutile lì).
- **Fatto**: pulsante "Assegna incarico" nella subview incarichi (M5.4,
  `templates/anagrafica/gruppo_incarichi.html`) → `AssegnaIncaricoView` con
  `?gruppo=<codice>`, letto in `AssegnaIncaricoView.get()` e passato come `initial`
  di `IncaricoManualeForm.gruppo_servizio` (già `ModelChoiceField` limitato a
  `gruppi_visibili`) — resta sempre modificabile (incarico esterno), mai readonly. Il
  default "gruppo di censimento quando si arriva dalla ricerca socio" resta di M7 (la
  ricerca socio con autocomplete non esiste ancora).
- **Verificato**: `_verifica_perimetro` in `apps/anagrafica/incarichi.py` non ha
  bisogno di modifiche, il perimetro dell'utente è già a monte.
- **Incarico duplicato (decisione presa, proposta usabilità #3) — verificato già
  presente, non implementato qui**: `IncaricoUnita.Meta.constraints` ha già un
  `UniqueConstraint` su `(capo, anno_scout, gruppo_servizio, codice_unita, funzione)`
  condizionato a `cessato_il__isnull=True`; `assegna_incarico_manuale` chiama
  `incarico.full_clean()` prima di salvare, quindi la violazione solleva già
  `ValidationError`, già gestita da `AssegnaIncaricoView` come ogni altro errore di
  validazione. Test `test_incarico_duplicato_rifiutato` in
  `apps/anagrafica/tests/test_incarichi_manuali.py` era già verde prima di M6.

**Difficoltà: media.** `assegna_incarico_manuale` non è cambiato; sono cambiati solo
punto di ingresso e valore iniziale del form.

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

## M9 — Icone nei tab della home

**File**: `apps/core/templates/core/home.html`.

- Aggiungere `{% load bootstrap_icons %}` (non ereditato dai blocchi del template
  genitore in Django, va caricato esplicitamente anche se `agesci_theme/base.html` lo
  fa già per sé) e usare lo stesso tag `{% bs_icon sezione.icona %}` / `{% bs_icon
  voce.icona %}` già in uso nella sidebar (`templates/base.html:34,46,48,54`), prima
  dell'etichetta nel `card-header` (riga 18 di `home.html`) e in ogni link della card
  (righe 21-23).
- Nessun dato nuovo: `sezione.icona`/`voce.icona` esistono già nel dataclass
  (`apps/core/menu.py:29-32,40-43`), già filtrati per ruolo da `sezioni_menu()`, e
  `home.html` riusa già lo stesso context processor della sidebar — stesso dato,
  stesso permesso, nessuna struttura nuova.

**Difficoltà: bassa.** Solo template, nessuna logica, nessun permesso da toccare.

**Test**: verifica visiva; eventualmente un test che verifica la presenza dell'icona
nel markup per una sezione nota.

---

## M10 — Invito diretto ristretto ad ADMIN/SEGRETERIA, fuso dentro "Ruoli"

**File coinvolti**: `apps/accounts/views.py` (`InvitoCreaView`, `InvitoListaView`),
`apps/accounts/forms.py::InvitoSingoloForm`, `apps/core/menu.py`,
`templates/accounts/ruolo_lista.html`, `templates/accounts/invito_crea.html`.

- Nuova costante `RUOLI_INVITO_DIRETTO = frozenset({ADMIN, SEGRETERIA})` in
  `apps/accounts/views.py`, distinta da `RUOLI_CHE_INVITANO` (resta ADMIN/SEGRETERIA/
  RDZ, `apps/accounts/views.py:21`, ora usata solo da `InvitoListaView` per la sola
  visualizzazione).
- `InvitoCreaView.ruoli_ammessi = RUOLI_INVITO_DIRETTO`: RDZ perde l'accesso alla
  creazione, mantiene l'accesso allo storico via `InvitoListaView` (invariata).
- `InvitoSingoloForm.ruolo_proposto` (`apps/accounts/forms.py:46-47`): scelte
  ristrette a `{ADMIN, SEGRETERIA}` (oggi espone tutto `Ruolo.Tipo.choices` più
  un'opzione vuota) e reso **obbligatorio** (oggi `required=False`): lo scopo della
  view diventa esplicitamente "invita per un ruolo amministrativo".
- **Menu**: rimuovere la voce indipendente "Inviti" (`apps/core/menu.py:116-117`).
  Aggiungere in `ruolo_lista.html` due link/pulsanti: "Nuovo invito" (visibile solo
  con `RUOLI_INVITO_DIRETTO`, verso `invito_crea`) e "Storico inviti" (visibile con
  `RUOLI_CHE_INVITANO`, quindi anche RDZ, verso `invito_lista`) — la pagina "Ruoli" è
  già raggiungibile da RDZ (`RUOLI_GESTIONE_RUOLI` lo include), quindi non serve una
  voce di menu diretta per lo storico.
- **Breadcrumb**: `InvitoCreaView` e `InvitoListaView` non combaciano più con nessuna
  voce di menu una volta rimossa "Inviti" — estendere entrambe con
  `BreadcrumbExtraMixin` (`apps/core/mixins.py`, stesso pattern già usato da
  `GruppoGestioneView`/`GruppoIncarichiView`), restituendo
  `[{"label": "Amministrazione"}, {"label": "Ruoli", "url": reverse("accounts:ruolo_lista")}, {"label": "Nuovo invito"}]`
  (e analogo per lo storico).

- **Fatto, non previsto esplicitamente nel testo originale della milestone**: il campo
  `gruppo` di `InvitoSingoloForm` (invito con account funzionale/CG) è stato
  **rimosso**, non solo reso secondario — reso `ruolo_proposto` obbligatorio lo
  rendeva incompatibile col ramo "solo gruppo, nessun ruolo" di
  `inviti.py::verifica_e_completa`. Verificato che il flusso massivo da allowlist
  (`AllowlistInvitoMassivoView`/`candidati_invito_massivo`) non passa mai da
  `InvitoSingoloForm`: nessuna regressione, l'invito con gruppo resta disponibile solo
  lì.

**Difficoltà: bassa-media.** Nessuna logica di dominio nuova, tre superfici da tenere
coerenti (permesso, menu, breadcrumb).

**Test**: RDZ riceve 403 su `invito_crea` ma 200 su `invito_lista`; il form rifiuta un
invio senza `ruolo_proposto`; le scelte del campo sono solo ADMIN/SEGRETERIA; la voce
"Inviti" non compare più in menu; i due pulsanti in `ruolo_lista.html` compaiono/
spariscono secondo permesso (ADMIN vede entrambi, RDZ solo "Storico inviti");
breadcrumb corretto su entrambe le pagine.

---

## M11 — Assegnare un ruolo direttamente (senza invito) a un utente già attivo

**File coinvolti**: nuovo in `apps/accounts/ruoli.py` (funzione), `apps/accounts/
views.py` (nuova view), `apps/accounts/forms.py` (nuovo form), `apps/accounts/urls.py`,
`templates/accounts/ruolo_lista.html`, nuovo template per la ricerca/creazione.

- **Nuova `crea_ruolo_esplicito(*, utente_assegnante, utente_destinatario, tipo,
  gruppo=None, branca="", settore="", data_fine=None)`** in `apps/accounts/ruoli.py`,
  accanto a `revoca_ruolo_esplicito`: stesso perimetro (`_verifica_ruolo_gestione_ruoli`,
  `RUOLI_GESTIONE_RUOLI`), `tipo` **esclude `Ruolo.Tipo.CG`** (decisione presa) —
  sollevare `ValueError`/`ValidationError` esplicito se richiesto, non ignorarlo in
  silenzio. Chiama `full_clean()` prima di `save()` per rispettare i vincoli già
  presenti in `Ruolo.clean()` (branca obbligatoria per IABZ; settore obbligatorio per
  ISZ; dominio email ammesso). Se `tipo == RDZ`, richiama `sincronizza_cg_comitato_zona`
  (stesso pattern già usato in `revoca_ruolo_esplicito` e in
  `inviti.py::verifica_e_completa`).
- **Blocco duplicato (proposta di usabilità, sul modello di M6/D-32)**: prima di
  creare, verificare se esiste già un `Ruolo` attivo identico per
  `utente_destinatario` + `tipo` (+ `branca`/`settore` quando applicabili) e sollevare
  `ValidationError` invece di creare un doppione — oggi `Ruolo` non ha alcun vincolo
  di unicità (`Meta` senza `constraints`), quindi senza questo controllo esplicito
  nulla impedirebbe due ruoli ADMIN attivi identici per lo stesso utente.
- **Vista a due passi**, sul modello di `RicercaCapoView` → `AssegnaIncaricoView`
  (D-32/D-34): `RuoloAssegnaCercaView` (ricerca utente, pattern di
  `ImpersonaListaView.get_queryset` — decisione presa) → `RuoloAssegnaView` (form
  tipo/branca/settore/data_fine condizionali, con `utente_destinatario` precompilato
  dalla query string, sul modello di `?codice_socio=`/`?gruppo=` già in uso in
  `AssegnaIncaricoView`).
- **Menu/template**: pulsante "Aggiungi ruolo" in `ruolo_lista.html`, visibile con
  `RUOLI_GESTIONE_RUOLI`.
- **Branca/settore condizionali in UI**: stesso principio di M7 (`static/js/
  ricerca-socio-autocomplete.js` ha già la logica di obbligatorietà/asterisco
  dinamico per `funzione`→`branca`); qui serve lo stesso meccanismo per
  `tipo`→`branca`/`settore` — la validazione reale resta comunque in
  `crea_ruolo_esplicito`/`Ruolo.clean()`, mai solo lato client.

**Difficoltà: alta.** Nessun servizio di creazione ruolo esiste oggi (solo la revoca);
tre campi mutuamente condizionati da validare due volte (UI + service layer); rischio
di un CG creato per errore da qui se l'esclusione non è applicata con lo stesso
rigore del form (`tipo` non deve mai includere CG fra le scelte, non solo essere
bloccato lato service).

**Test**: CG rifiutato esplicitamente (form non lo propone neppure, il service lo
blocca comunque se forzato); IABZ senza branca rifiutato; ISZ senza settore rifiutato;
ruolo duplicato rifiutato; RDZ creato da qui sincronizza il CG derivato su E9001 (D-35,
stesso comportamento di `inviti.py`); solo `RUOLI_GESTIONE_RUOLI` accede; ricerca
utente con lo stesso comportamento di `ImpersonaListaView`.

---

## M12 — Elenco degli utenti impersonabili + voce di menu

**File coinvolti**: `apps/accounts/views.py::ImpersonaListaView`,
`templates/accounts/impersona_lista.html`.

- **Deviazione dal testo del piano originale**: la voce di menu **esisteva già**
  (`templates/base.html:82-84`, dropdown utente, "Impersona un utente" verso
  `accounts:impersona_lista`, gated da `puo_impersonare_qualcuno` — commit `513cf80`,
  precedente alla sessione di pianificazione M9-M12). L'affermazione del piano
  originale ("nessuna voce di navigazione punta lì") era quindi errata: verificato
  con `git log -p` prima di aggiungere una seconda voce, che sarebbe stata
  ridondante. **Nessuna voce nuova aggiunta.**
- **Deviazione dichiarata da "niente elenco sfogliabile"** (decisione presa,
  implementata): senza query, `ImpersonaListaView.get_queryset()` torna l'elenco
  completo (`paginate_by = 20` già presente) invece di `Utente.objects.none()`.
  Motivazione nel docstring aggiornato: bersaglio sono account piattaforma non
  anagrafica soci, pagina già riservata al livello di privilegio più alto
  (`puo_impersonare_qualcuno`, oggi solo ADMIN diretto). La query resta comunque
  disponibile per filtrare un elenco lungo.
- Il template mostrava la tabella solo `{% if query %}`: tolto il condizionale, ora
  visibile sempre. Il pulsante "Impersona" per riga non cambia: già gated
  correttamente da `can_hijack`/`puo_impersonare()`.

**Difficoltà: media** (rivista a **bassa** in fase di implementazione: il vero lavoro
era solo la deviazione di postura sulla query, non la voce di menu che già esisteva).

**Test**: senza query, la lista mostra utenti (non più vuota) per chi ha
`puo_impersonare_qualcuno`, esclude sempre se stesso; la query continua a filtrare; il
pulsante impersona compare solo per gli utenti effettivamente impersonabili
(`can_hijack`, invariato); nessuna regressione sul flusso di impersonificazione
esistente (D-27, doppia identità registrata).

---

## M13 — Rifiniture breadcrumb: icona Home sempre visibile + Template email completo

Due segnalazioni comparse dopo M8/M9-M12, entrambe sul breadcrumb: non rientrano in
nessuna milestone esistente (M9 riguarda le icone nelle card della home page, non il
breadcrumb) — nuova milestone dedicata, indipendente dalle altre.

**File coinvolti**: `apps/core/views.py` (`TemplateEmailListaView`,
`TemplateEmailModificaView`), `apps/core/templates/core/template_email_lista.html`,
`apps/core/templates/core/template_email_modifica.html`, nuovo
`templates/agesci_theme/partials/breadcrumb.html`.

- **Template email senza pulsante "torna a Impostazioni" e senza breadcrumb**:
  gap reale lasciato da M8 — `TemplateEmailListaView`/`TemplateEmailModificaView`
  (`apps/core/views.py:44-99`, verificato) non ereditano `BreadcrumbExtraMixin`
  (`apps/core/mixins.py`, stesso pattern già usato da `GruppoGestioneView`/
  `InvitoCreaView` una volta fatto M10). Aggiungere `breadcrumb_extra` a entrambe
  (`[{"label": "Amministrazione"}, {"label": "Impostazioni", "url": reverse("core:impostazioni")}, {"label": "Template email"}]`,
  con un terzo elemento in più per la view di modifica) e un link "← Impostazioni" in
  cima a `template_email_lista.html` (la view di modifica ha già il link alla lista
  come punto di ritorno naturale, ma non ha comunque il breadcrumb).
- **Icona Home sempre presente nel breadcrumb, prima del testo**: il partial renderizzato
  è `agesci_theme/partials/breadcrumb.html` — **template di terze parti** (pacchetto
  `django-agesci-campania-theme`, verificato: `{% include %}` in
  `agesci_theme/base.html:56`), da non modificare direttamente nel `.venv`. Il progetto
  non ha oggi alcun override locale di template del tema (verificato,
  `templates/agesci_theme/` non esiste). Soluzione: creare
  `templates/agesci_theme/partials/breadcrumb.html` — Django lo sceglie automaticamente
  al posto della versione del pacchetto perché `TEMPLATES[0]["DIRS"]`
  (`BASE_DIR / "templates"`) ha priorità su `APP_DIRS` (`config/settings/base.py:104`) —
  copia del partial originale con `{% bs_icon "house-fill" %}` aggiunto solo per il
  primo elemento (`forloop.first`, sempre "Home" per costruzione di
  `apps/core/context_processors.py::breadcrumb()`), stesso tag già in uso ovunque nel
  progetto, nessun CSS custom.

**Difficoltà: bassa.** Nessuna logica nuova, solo template e un mixin già collaudato;
l'unico punto delicato è l'override di un template di terze parti, da tenere
sincronizzato manualmente se il pacchetto del tema aggiorna quel partial in futuro
(annotare la versione del tema nel commento del file copiato).

**Test**: `template-email/` e `template-email/<pk>/` mostrano un breadcrumb corretto e
un link di ritorno a Impostazioni; il breadcrumb su qualunque altra pagina esistente
mostra sempre "Home" con l'icona (regressione da verificare su almeno una pagina di
primo livello e una pagina figlia via `BreadcrumbExtraMixin`, es. `gruppo_gestione`).

---

## M14 — Autocomplete codice socio in "Inserisci partecipazione" (perimetro per ruolo) ✅

**File coinvolti**: `PartecipazioniRicercaSociAutocompleteView` in
`apps/contributi/views.py`, voce `partecipazioni_ricerca_soci_autocomplete` in
`apps/contributi/urls.py`, `apps/contributi/forms.py::PartecipazioneManualeForm`
(`codice_socio` da `CharField` libero a `forms.HiddenInput`), `templates/contributi/
partecipazione_inserisci.html`, nuovo `static/js/
ricerca-socio-contributo-autocomplete.js` (copia trimmata di `ricerca-socio-
autocomplete.js`, senza la logica di precompilazione gruppo/branca che qui non serve),
nuovo `apps/contributi/tests/test_views_ricerca_soci_autocomplete.py`.

**Deviazione rispetto al testo pianificato, scoperta in implementazione**: la query
filtra su `gruppi_visibili(request.user, campagna.anno).exclude(is_comitato_zona=True)`,
non solo su `gruppi_visibili(...)`. Come documentato in
`inserimento.py::risolvi_gruppo_competente`, **`gruppi_visibili()` da sola non esclude
E9001** per i ruoli a perimetro zona (SEGRETERIA/ADMIN/RDZ): senza l'esclusione
esplicita l'autocomplete avrebbe proposto censiti in E9001 che poi
`inserisci_partecipazione_manuale` avrebbe comunque rifiutato (A-8), con un'esperienza
confusa (risultato selezionabile ma non inseribile). Endpoint URL con `campagna_id`
(non `anno_scout_corrente()`): usa `campagna.anno`, coerente con
`risolvi_gruppo_competente`, che risolve sempre sull'anno della campagna in corso, non
sull'anno scout "oggi".

- **Verificato**: `codice_socio` oggi è un `forms.CharField(max_length=20)` senza
  autocomplete (`forms.py:27`); `capo` sul modello `Partecipazione` è una FK, non un
  campo `codice_socio` — il codice socio è la PK del capo (`inserimento.py:79`,
  `capo_id=codice_socio`).
- **Non riusare `RicercaSociAutocompleteView` di M7** (`apps/anagrafica/
  views.py:397-437`): quell'endpoint è **esplicitamente cross-gruppo per
  decisione presa in M7** (confermato dal test `test_cg_trova_capi_censiti_in_un_altro_gruppo`),
  incompatibile col perimetro per ruolo richiesto qui. **Non riusare nemmeno**
  `cerca_capo_per_codice_socio` (D-34: solo match esatto per codice socio, nessun
  elenco sfogliabile). Terzo endpoint di ricerca soci, con un terzo perimetro
  distinto: da documentare nel docstring della nuova view con un rimando esplicito a
  entrambi gli altri due, come già fatto in M7 verso D-34.
- Query: filtra `CensimentoCapo` dell'anno corrente per `gruppo_id` in
  `gruppi_visibili(request.user, anno_scout_corrente())` (stessa funzione già
  importata e usata da `apps/contributi/inserimento.py::risolvi_gruppo_competente`,
  righe 30-51: un CG vede solo il proprio gruppo, SEGRETERIA/ADMIN/RDZ tutta la zona),
  più gli stessi filtri icontains nome/cognome/codice_socio/gruppo di M7.
- Risposta JSON: `{"codice_socio", "nome", "cognome", "gruppo"}` — niente
  `gruppo_codice`: qui non c'è un campo "gruppo di servizio" da precompilare come in
  M7.
- Etichetta risultato in UI: `"[Nome] [Cognome] ([Codice Socio])"`, come da TODO
  (diversa dal formato `"nome cognome (gruppo)"` usato in M7).

**Difficoltà: media.** Nessuna logica di dominio nuova (riusa `gruppi_visibili`), ma un
terzo endpoint di ricerca soci da mantenere isolato dagli altri due: il rischio reale
è che in futuro qualcuno li "unifichi" senza notare che i tre perimetri sono diversi
per decisione esplicita (nullo in M7, esatto in D-34, per-ruolo qui).

**Test**: CG vede solo censiti nel proprio gruppo; SEGRETERIA/ADMIN/RDZ vedono tutta la
zona; censito in E9001 escluso (coerente con `risolvi_gruppo_competente`); risposta non
contiene dati riservati; meno di `MINIMO_CARATTERI_AUTOCOMPLETE` restituisce lista
vuota.

---

## M15 — Tipologia partecipazione "Altro (specificare)" ✅

**File coinvolti**: `apps/contributi/migrations/0004_seed_tipologia_altro.py` (stesso
pattern di `0002_seed_tipologie.py`, `RunPython` reversibile),
`apps/contributi/forms.py::PartecipazioneManualeForm`,
`apps/contributi/inserimento.py::inserisci_partecipazione_manuale`,
`apps/contributi/views.py::PartecipazioneInserisciView` (nuovo `_contesto()` che passa
`tipologia_altro_pk` al template), `apps/contributi/models.py::Partecipazione.clean()`,
`templates/contributi/partecipazione_inserisci.html`,
`static/js/ricerca-socio-contributo-autocomplete.js` (stesso file di M14: nuova
funzione `attivaDescrizioneAltroCondizionale()`, non un file separato).

**Deviazioni rispetto al testo pianificato, scoperte in implementazione**:
- Il meccanismo scelto per il toggle JS non confronta il `codice` della tipologia
  (non disponibile lato client senza rendering custom del `<select>`), ma il **pk**
  della riga "ALTRO": la view lo risolve una volta con una query
  (`TipologiaCampo.objects.filter(codice="ALTRO").values_list("pk", flat=True).first()`)
  e lo espone come `data-tipologia-altro-pk` sul tag `<script>`, letto dal JS e
  confrontato con `select.value`. Evita di introdurre un widget `Select` custom solo
  per questo.
- **Un test preesistente riusava il codice `"ALTRO"`** per una tipologia fittizia
  (`apps/contributi/tests/test_transizioni_campagna.py`, fixture `altro`, usata da
  `test_auto_approva_cfm_lascia_altro_inserita`), non collegata alla feature "Altro
  (specificare)": creava una riga con quel codice per testare che
  `avvia_valutazione` lasci INSERITA una tipologia non ad approvazione automatica.
  In conflitto con il vincolo di unicità di `TipologiaCampo.codice` dopo la migrazione
  0004. Rinominata la fixture in `non_auto` con codice `"ZONALE1"` e il test in
  `test_auto_approva_cfm_lascia_non_auto_inserita`: stesso comportamento testato,
  nessuna sovrapposizione semantica con la tipologia "Altro" reale.
- **Verificato**: `Partecipazione.descrizione_altro` esiste già sul modello
  (`models.py:154`, `CharField(max_length=200, blank=True)`) ma non è nel form né in
  `inserimento.py` né validato in `clean()` — costruito in anticipo, mai collegato.
  `TipologiaCampo` non è un enum ma un modello DB (`models.py:109-126`): "Altro" deve
  esistere come riga, non come scelta hardcoded nel form.
- Seed di `TipologiaCampo(codice="ALTRO", nome="Altro", livello=LivelloCampo.ALTRO,
  approvazione_automatica=False, quota_default=None)` — **decisione da confermare in
  fase di implementazione**: `approvazione_automatica=False` è coerente con D-11 ("le
  altre valutate dal Comitato"), da verificare che nessun ramo del service layer
  assuma implicitamente che solo CFM/CFA/CCG esistano come tipologie automatiche.
- `Partecipazione.clean()` (righe 193-210): aggiungere che `descrizione_altro` sia
  obbligatorio quando `self.tipologia.codice == "ALTRO"`, stesso stile del controllo
  già presente su `motivazione_respingimento` per lo stato RESPINTA.
- Form: campo `descrizione_altro` sempre presente, reso obbligatorio via JS solo
  quando la tipologia selezionata è "Altro" (mostra/nasconde il campo) — la
  validazione reale resta nel `clean()` del modello, mai solo lato client (stesso
  principio di branca/settore condizionali in M7/M11).

**Difficoltà: media.** Il campo modello esiste già (riduce il rischio), ma tocca
migrazione dati + validazione condizionale + JS, tre superfici da tenere coerenti.

**Test**: submit con tipologia "Altro" e `descrizione_altro` vuoto rifiutato dal
`clean()` anche forzando il form lato client; submit con "Altro" e descrizione
compilata accettato; le tre tipologie esistenti (CCG/CFM/CFA) restano invariate.

---

## M16 — Validazioni e campi minori (data_fine, luogo, note)

**File coinvolti**: `apps/contributi/models.py::Partecipazione` (nuovo campo `note` +
`clean()`), nuova migrazione `0005_partecipazione_note_luogo_blank.py`,
`apps/contributi/forms.py::PartecipazioneManualeForm`,
`apps/contributi/inserimento.py::inserisci_partecipazione_manuale`,
`templates/contributi/partecipazione_inserisci.html`.

- **Data fine ≥ data inizio**: nessun vincolo esiste oggi né in
  `PartecipazioneManualeForm` né in `Partecipazione.clean()` (righe 193-210) né nel
  service. Aggiungere in `clean()`, accanto al controllo di finestra associativa già
  presente (righe 203-208), `self.data_fine < self.data_inizio` →
  `ValidationError` su `data_fine` — "al massimo stessa data" per il TODO, quindi `<`
  non `<=` (stesso stile del controllo gemello già su `Campagna.clean()`, righe
  62-71).
- **Luogo non obbligatorio**: `luogo` oggi è `CharField(max_length=200)` senza
  `blank=True` sul modello (riga 157) e obbligatorio nel form (riga 31). Aggiungere
  `blank=True` al modello (nuova migrazione) e `required=False` al form;
  `inserimento.py` già passa `luogo` così com'è, nessuna modifica lì.
- **Campo Note**: nessun campo di note libere esiste (`motivazione_respingimento` ha
  semantica diversa: causale di respingimento, non note in inserimento). Nuovo `note =
  models.TextField(blank=True)` sul modello, nuovo campo nel form, propagato in
  `inserisci_partecipazione_manuale`.
- Le tre modifiche al modello (`note` nuovo, `luogo` `blank=True`) vanno in un'unica
  migrazione, non tre, per non sporcare la cronologia.

**Difficoltà: bassa.** Nessuna logica di dominio complessa, solo migrazioni additive e
validazione semplice.

**Test**: partecipazione con `data_fine < data_inizio` rifiutata; `data_fine ==
data_inizio` accettata; `luogo=""` accettato; `note` opzionale, salvata e mostrata nel
dettaglio campagna (verificare se `campagna_dettaglio.html` va esteso con la colonna).

---

## M17 — Quota versata obbligatoria con default 51,50€ per CCG/CFM/CFA

**File coinvolti**: `apps/contributi/forms.py::PartecipazioneManualeForm`,
`apps/contributi/views.py::PartecipazioneInserisciView`, `templates/contributi/
partecipazione_inserisci.html`, JS condiviso con M15.

- **Verificato**: `quota_default = Decimal("51.50")` è già seedato per CCG/CFM/CFA in
  `migrations/0002_seed_tipologie.py`; il fallback server-side quando
  `quota_versata is None` esiste già in `inserimento.py:70-74`
  (`quota = quota_versata if quota_versata is not None else tipologia.quota_default`).
  Il TODO chiede però il comportamento opposto in UI: campo visibilmente obbligatorio
  e precompilato, non lasciato vuoto contando sul fallback silenzioso.
- Il fallback server-side **resta invariato**: è la garanzia di ultima istanza per
  l'import massivo xlsx, che non passa da questo form (`inserimento.py` è condiviso
  fra form manuale e import — verificare in fase di implementazione quale funzione
  usa l'import xlsx, per assicurarsi che non venga toccata).
- Form: `quota_versata` da `required=False` a obbligatorio, con `initial` calcolato
  lato view in base alla tipologia eventualmente già selezionata, più JS che
  aggiorna il valore quando l'utente cambia la tendina tipologia (stesso blocco JS
  "reagisce al cambio tipologia" di M15 — motivo della dipendenza M17→M15). Il valore
  precompilato resta editabile: se l'utente lo modifica, prevale l'input manuale
  (comportamento naturale di un campo obbligatorio pre-riempito, nessun controllo
  aggiuntivo necessario).

**Difficoltà: bassa-media.** Cambiare `required=False` → obbligatorio è banale; il
punto delicato è non rompere il fallback usato dall'import massivo.

**Test**: submit senza `quota_versata` dal form manuale ora rifiutato (era accettato
prima); import massivo xlsx senza quota per CCG/CFM/CFA continua a usare il default
(nessuna regressione su quel percorso); cambiando la tipologia in UI il campo quota si
aggiorna via JS ma resta editabile.

---

## M18 — Proposte di usabilità aggiuntive (M14-M17)

Emerse durante l'esplorazione di M14-M17, non richieste esplicitamente nel TODO — da
discutere e decidere con l'utente prima dell'implementazione, sullo stesso modello
della sezione "Proposte di usabilità aggiuntive" già usata per M1-M13 più sotto.

1. ✅ **M14** — mostrare il gruppo di censimento accanto a ciascun risultato
   dell'autocomplete (stesso arricchimento non sensibile già fatto in M7), utile
   perché qui il perimetro può includere più gruppi (SEGRETERIA/ADMIN/RDZ).
   **Implementato**: l'endpoint restituiva già `gruppo` nel JSON (mai usato in UI);
   solo `mostraRisultati()` in `ricerca-socio-contributo-autocomplete.js` aggiornata
   per includerlo negli elementi della lista a discesa, mentre l'etichetta dopo la
   selezione resta quella già decisa in M14 (senza gruppo).
2. ✅ **M15** — tenere "Altro" come ultima opzione nella tendina "Tipologia
   partecipazione" (non alfabetica): `TipologiaCampo.Meta.ordering = ["codice"]` la
   piazzerebbe prima delle altre ("ALTRO" < "CCG"), serve un ordinamento esplicito nel
   form. **Implementato**: `queryset.order_by(Case(When(codice="ALTRO", then=1),
   default=0), "codice")` in `PartecipazioneManualeForm`.
3. ✅ **M17** — testo o badge accanto al campo quota ("precompilato, modificabile")
   quando il valore è stato riempito automaticamente dalla tipologia, per non farlo
   sembrare un valore già inserito da altri. **Implementato**: badge Bootstrap
   nascosto di default, mostrato dal JS al cambio tipologia insieme alla
   precompilazione, nascosto di nuovo al primo `input` manuale sul campo.
4. ✅ **M16** — campo Note visibile anche nel riepilogo/dettaglio partecipazione
   (`campagna_dettaglio.html`), ma **escluso dall'export bonifici**
   (`apps/contributi/bonifici.py::genera_righe_bonifici` — verificare prima di
   deciderlo) per lo stesso principio di minimizzazione già applicato altrove nel
   progetto (es. export anagrafica a profilo minimo). **Verificato**:
   `genera_righe_bonifici` aggrega solo per gruppo (`ContributoPartecipazione`), non
   legge mai campi della singola `Partecipazione` come `note`: nessuna modifica
   necessaria lì, l'esclusione è già garantita dalla struttura esistente.
5. ✅ **Generale** — valutare se documentare in CLAUDE.md una tabella comparativa dei tre
   perimetri di ricerca soci ora esistenti (D-34, M7, M14), per ridurre il rischio che
   vengano confusi o "unificati" per errore in futuro — modifica alla documentazione,
   non al codice, da proporre separatamente. **Implementato**: nuova sezione "Ricerca
   soci: tre perimetri distinti, non unificare" in CLAUDE.md con tabella comparativa.

Tutte e cinque discusse e accolte con l'utente il 2026-08-31; nessuna era
implementabile isolatamente prima, dato che dipendevano da M14-M17.

---

## Riepilogo difficoltà

| Milestone | Voce TODO | Difficoltà | Stato | Nota principale |
| --- | --- | --- | --- | --- |
| M1 | Contributi→Moduli | Bassa | ✅ completata | Solo stringhe |
| M2 | Allowlist→Amministrazione | Bassa | ✅ completata | Permessi non divergenti: Allowlist mantiene le deleghe, Impostazioni resta solo diretti |
| M3 | Importa unificato | Media | ✅ completata | Cruscotto aggrega in Python, badge da `bool(anomalie)`, liste esistenti raggiungibili come link |
| M4 | Visualizza anagrafica | Bassa-media | ✅ completata | Accesso view = unione dei 3 permessi, ogni scheda condizionata al proprio; nessun ruolo reale oggi ha RICERCA_CAPO/REGISTRO senza EXPORT |
| M4.5 | Vincolo CG unico per gruppo (D-35) | Alta | ✅ completata | Sesso preso dal PDF (record["genere"]), non da Capo.sesso; nuovo apps/accounts/ruoli.py per la revoca esplicita |
| M5 | Gestione gruppo (base) | Alta | ✅ completata | Subview incarichi spostata in apps.anagrafica (dipendenze verificate); breadcrumb via BreadcrumbExtraMixin |
| M6 | Assegna incarico → dentro Gestione gruppo | Media | ✅ completata | assegna_incarico_manuale invariato; blocco duplicati già coperto dal UniqueConstraint di IncaricoUnita, non da scrivere |
| M7 | Autocomplete + branca condizionale | Alta | ✅ completata | Modello IncaricoUnita.branca senza blank=True: fallback BrancaUnita.SCONOSCIUTA nel service layer, non nel form |
| M8 | Template email + rich text | Alta | ✅ completata | TinyMCE vendorizzato (no CDN/API key); motore ridotto legge anche il fallback grezzo (mai autoescape Django); auditlog già registrato in core |
| M9 | Icone nei tab della home | Bassa | ✅ completata | Dato già presente in `menu.py`, solo da renderizzare; scoperto un ramo morto preesistente in home.html (sezioni_menu non è mai vuota) |
| M10 | Invito diretto ristretto + fuso in Ruoli | Bassa-media | ✅ completata | Campo `gruppo` rimosso da InvitoSingoloForm (CG resta solo nel flusso massivo allowlist); RDZ mantiene solo la visualizzazione storico |
| M11 | Assegna ruolo diretto (senza invito) | Alta | ✅ completata | CG escluso (D-35); nuova crea_ruolo_esplicito() sul modello di revoca_ruolo_esplicito; blocco duplicati e RDZ→CG(E9001) coperti |
| M12 | Elenco utenti impersonabili | Media | ✅ completata | Deviazione dichiarata dal principio "niente elenco sfogliabile"; la voce di menu esisteva già nel dropdown utente, nessuna voce nuova da aggiungere |
| M13 | Rifiniture breadcrumb (Home + Template email) | Bassa | ✅ completata | Gap lasciato da M8 (BreadcrumbExtraMixin mancante); icona Home via override locale di un partial del tema (versione 2.4.1 annotata nel commento) |
| M14 | Autocomplete codice socio (perimetro per ruolo) | Media | ✅ completata | Terzo endpoint di ricerca soci, distinto da D-34 (match esatto) e da M7 (cross-gruppo): filtra per `gruppi_visibili()` come `risolvi_gruppo_competente`; E9001 escluso esplicitamente (A-8), come in `risolvi_gruppo_competente`, perché `gruppi_visibili()` da sola non lo fa |
| M15 | Tipologia "Altro (specificare)" | Media | ✅ completata | `descrizione_altro` esisteva già sul modello (mai collegato); nuova riga `TipologiaCampo` seedata via migrazione 0004; un test preesistente riusava il codice "ALTRO" per un'altra tipologia fittizia ed è stato rinominato |
| M16 | Validazioni e campi minori (data_fine, luogo, note) | Bassa | ✅ completata | Migrazione additiva unica per `note` + `luogo blank=True`; validazione `data_fine < data_inizio` nel `clean()`; colonna Note aggiunta a `campagna_dettaglio.html` (proposta M18 #4 accolta) |
| M17 | Quota versata obbligatoria + default 51,50€ CCG/CFM/CFA | Bassa-media | ✅ completata | `required` sul form, JS precompila su change tipologia (mai al load, per non sovrascrivere un valore già digitato in un ripresentazione dopo errore); fallback server-side e import massivo invariati (verificato) |

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
