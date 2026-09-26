# Migrazione a django-agesci-campania-coreui-theme

## Contesto

`django-agesci-campania-theme` (Bootstrap 5) è il pacchetto tema attualmente in uso.
L'associazione ha pubblicato `django-agesci-campania-coreui-theme` (PyPI 0.1.0, tag
`coreui-v0.1.0` nel repo `AGESCI-Campania/django-agesci-campania-theme`, cartella
`coreui/`): un secondo pacchetto ufficiale che **estende** il tema base con il layout
nativo CoreUI 5 (sidebar/header "admin", versione free/MIT) e alcuni componenti
aggiuntivi (`ag_nav_item`, `ag_nav_title`, `ag_callout`, `ag_avatar`, `ag_chip`,
`CampoChip`/`InputChip`). Il tema base resta obbligatorio come dipendenza (system
check `agesci_coreui.E001`): non è una sostituzione ma un'aggiunta che cambia il
layout.

Obiettivo: migrare l'intero progetto (nessuna coesistenza Bootstrap/CoreUI nello
stesso progetto — vincolo esplicito della documentazione ufficiale, perché
`{% ag_js %}` decide globalmente il prefisso `data-*`), sfruttando dove sensato i
nuovi componenti per migliorare UI e usabilità.

Lavoro svolto interamente sul branch `migrazione-coreui-theme`. **Nulla va su `main`**
finché la migrazione non è approvata esplicitamente.

Fonti consultate (verificate leggendo il codice sorgente, non a memoria):
`coreui/agesci_coreui/templates/agesci_coreui/base.html`, `docs/coreui.md`,
`coreui/pyproject.toml` al tag `coreui-v0.1.0` del repo del tema;
`config/settings/base.py`, `templates/base.html`,
`templates/agesci_theme/partials/{footer,breadcrumb,cookie_banner}.html`,
`apps/core/menu.py`, `apps/core/context_processors.py` in questo repo.

**Decisioni prese con l'utente** (vincolanti per l'implementazione):

- Migrazione completa in un'unica fase (non incrementale a moduli): imposta dal
  vincolo ufficiale "non mescolare pagine Bootstrap e pagine CoreUI nello stesso
  progetto".
- Footer: si mantengono le colonne attuali (logo, Informazioni, Contatti), non si
  passa al footer compatto di default di CoreUI.
- Si adottano i nuovi componenti CoreUI-nativi (`ag_chip`, `ag_callout`, `ag_avatar`)
  nei punti applicativi esistenti dove migliorano l'usabilità (Fase 3), non solo nel
  layout base.
- Commit automatico a fine fase sul branch dedicato, mai push/merge su `main` senza
  richiesta esplicita.

## Valutazione complessità e impatto

**Sintesi**: impatto poco disruptive sul resto del codice, complessità medio-bassa
concentrata in poche aree. La migrazione non tocca mai il layer dati (nessuna
migrazione, nessun model, nessuna logica di business/service layer) — è un intervento
confinato a template, `INSTALLED_APPS`/settings del tema e dipendenze, che non
richiede di riaprire o ripensare codice applicativo esistente al di fuori dell'area di
layout. Ogni modifica è reversibile con `git revert`/`git checkout` finché resta sul
branch dedicato.

**Perché l'impatto è contenuto** (fatti verificati con grep sul repo):

- **Un solo punto di aggancio reale**: `templates/base.html` è l'unico file che estende
  il tema (`{% extends "agesci_theme/base.html" %}` → `agesci_coreui/base.html`). Tutti
  gli altri **74 template applicativi** estendono `"base.html"` locale, mai il tema
  direttamente: restano quasi tutti invariati.
- **`data-bs-*` confinato**: gli unici attributi Bootstrap-JS-specifici da riscrivere in
  `data-coreui-*` sono dentro `templates/base.html` (4 usi: offcanvas, dismiss,
  collapse, dropdown). Nessun template applicativo ne usa altri (verificato via grep).
- **Un solo test fragile**: su 110 file di test nel repo, solo
  `apps/core/tests/test_breadcrumb.py` fa un assert su una classe CSS del markup del
  tema (`breadcrumb-agesci`) e va aggiornato. Tutti gli altri test di dominio/logica non
  dipendono dal markup del tema.
- **3 override locali da rilavorare**, non da inventare da zero: breadcrumb (diventa
  superfluo, si elimina), footer (si riporta il contenuto nel nuovo blocco `footer`),
  cookie banner (resta identico, cambia solo il punto di `{% include %}`).
- **Componenti del tema quasi inutilizzati lato applicazione**: solo `emblema_zona` è
  usato in un punto (`core/home.html`); nessun tag `ag_*`/`branca_bg` del tema base è
  usato nei template applicativi, quindi non c'è nulla da disimparare lì.
- Le sostituzioni badge→`ag_chip` (Fase 3) sono **additive e isolate**: 7 file, ognuno
  con 1-3 righe toccate, nessuna dipendenza tra loro — se una causasse un problema
  visivo, il rollback è locale a quel file.

**Dove si concentra davvero il lavoro/rischio**:

- **Riscrittura manuale della sidebar** (`templates/base.html`, blocco `sidebar_items`):
  è l'area con più codice da riscrivere ex novo (markup CoreUI nativo con
  `.nav-group`/`.nav-group-items` per i sottomenu) e quella con maggiore probabilità di
  introdurre bug di markup/attributi `data-coreui-*` non visibili a `mise run test`
  (nessun test HTML-level sulla sidebar oggi) — richiede verifica visiva manuale
  puntuale (Fase 2), non solo lint/test automatici.
- **Pacchetto pre-1.0**: `django-agesci-campania-coreui-theme` è alla versione 0.1.0,
  primo rilascio — possibile instabilità di API/nomi di blocchi nelle versioni
  successive (mitigato: si può restare pinnati a `0.1.0` finché non si decide un
  aggiornamento deliberato, stesso approccio già in uso per il tema base).
  `agesci_coreui/base.html` carica CoreUI 5.9.0 CSS/JS da CDN
  (`cdn.jsdelivr.net/npm/@coreui/coreui@...`): stesso pattern già in uso oggi per
  Bootstrap dal tema base, non introduce un nuovo tipo di dipendenza esterna.
- **`sidebar_user` e `header_actions`**: i link applicativi oggi nel dropdown utente
  (cambia password, preferenze, impersona, esci) non hanno un default nel layout
  CoreUI — se dimenticati nella riscrittura si perdono silenziosamente funzionalità
  esistenti (nessun test li copre a livello HTML); vanno verificati esplicitamente in
  Fase 2, non solo assunti presenti.
- **Assenza di test di rendering**: la superficie di regressione visiva
  (impaginazione, contrasto colori per branca, responsive) non è coperta da test
  automatici nel progetto — la Fase 2 (verifica manuale nel browser) è l'unico
  presidio, va eseguita con attenzione e non saltata.

**Stima qualitativa per fase** (S=piccola, M=media, L=grande):

| Fase | Complessità | Rischio di regressione |
| --- | --- | --- |
| 0 — Setup branch/dipendenza | S | Nullo (solo settings/dipendenze) |
| 1 — Layout base | L | Medio (sidebar riscritta a mano, nessun test HTML) |
| 2 — Verifica visiva | M (tempo, non codice) | — (è il presidio, non il rischio) |
| 3 — Adozione componenti | S/M | Basso (modifiche additive, isolate per file) |
| 4 — Pulizia e checklist | S | Basso |

## Cosa cambia strutturalmente (fatti verificati)

- **Nuovo layout**: `templates/agesci_coreui/base.html` sostituisce
  `agesci_theme/base.html`. Blocchi condivisi: `title`, `extra_head`, `sidebar`,
  `sidebar_class`, `brand_url`, `brand_text`, `sidebar_items`, `sidebar_user`,
  `header`, `header_nav`, `header_search`, `header_actions`, `main_class`, `messages`,
  `content`, `footer`, `footer_copyright`, `footer_links`, `extra_js`.
- **Non esistono più**: `offcanvas_nav` (il menu mobile è la sidebar stessa, gestita
  nativamente), `footer_brand_text`, `footer_columns`, `footer_col*`, `footer_text` —
  se definiti nel template figlio vengono ignorati senza errore.
- **Breadcrumb**: non è più un partial separato
  (`agesci_theme/partials/breadcrumb.html`), è inline nel blocco `header`, pilotato
  dalla variabile di contesto `breadcrumb_items` — la stessa già prodotta da
  `apps/core/context_processors.py::breadcrumb()`. Non serve nessun lavoro sul
  context processor: funziona già "a costo zero". L'override locale attuale (icona
  Home + classe `breadcrumb-agesci`) diventa inutilizzato e va rimosso; il test
  `apps/core/tests/test_breadcrumb.py` (riga 87, `assertIn('class="breadcrumb-agesci"',
  ...)`) va riscritto per verificare il markup CoreUI nativo (`class="breadcrumb"`).
- **Sidebar**: markup completamente diverso (`.sidebar.sidebar-fixed`,
  `data-coreui="navigation"`, item con `{% ag_nav_item %}`/`{% ag_nav_title %}`,
  gruppi annidati con markup nativo `.nav-group`/`.nav-group-items`). La struttura dati
  `sezioni_menu()` (`apps/core/menu.py`, `SezioneMenu`/`VoceMenu`) resta invariata e
  riusata: nessuna modifica al menu, solo al template che la renderizza.
- **Toggle CoreUI**: tutti gli attributi `data-bs-*` presenti oggi in
  `templates/base.html` (`data-bs-toggle="offcanvas"`, `data-bs-dismiss="offcanvas"`,
  `data-bs-toggle="collapse"`, `data-bs-toggle="dropdown"`) vanno riscritti con
  `data-coreui-*` (CoreUI ignora `data-bs-*`, verificato nella doc del pacchetto).
  Nessun altro template applicativo usa `data-bs-*` (verificato via grep): il rischio
  è confinato a `templates/base.html`.
- **Footer**: i blocchi CoreUI nativi sono solo `footer`/`footer_copyright`/
  `footer_links` (niente colonne). Si mantengono le colonne attuali sovrascrivendo
  l'intero blocco `footer` con markup equivalente all'attuale
  `templates/agesci_theme/partials/footer.html`, dentro `templates/base.html` (non
  più come override di partial del tema, perché quel partial non esiste più in questo
  layout).
- **Cookie banner**: non ha alcun aggancio nel layout CoreUI (nessun block/include
  dedicato). Il partial `templates/agesci_theme/partials/cookie_banner.html` resta
  com'è (usa solo classi Bootstrap generiche, compatibili con CoreUI) ma va incluso
  esplicitamente (`{% include "agesci_theme/partials/cookie_banner.html" %}`) dentro
  il nuovo blocco `footer` sovrascritto in `templates/base.html`.
- **FORM_RENDERER**, context processor `agesci_theme.context_processors.agesci_theme`,
  settings `AGESCI_THEME_*`: invariati, il tema CoreUI li riusa dal tema base.
- **INSTALLED_APPS**: aggiungere `"agesci_coreui"` (prima di `agesci_theme` o comunque
  prima delle app allauth, stesso motivo già documentato nel commento esistente su
  `agesci_theme`), mantenendo `"agesci_theme"`.
- **Dipendenze**: aggiungere `django-agesci-campania-coreui-theme` (PyPI, richiede
  `django-agesci-campania-theme>=2.7.0` — va quindi alzato anche il pin del tema base,
  oggi `>=2.6.1`, in `pyproject.toml`/`uv.lock` via `uv add`, mai `pip install`
  diretto).

## Stato di avanzamento

Legenda: ✅ completata — 🔄 in corso — ⬜ da fare.

### Fase 0 — Setup branch e dipendenza ✅

- [x] Branch dedicato `migrazione-coreui-theme` da `main`
- [x] `uv add "django-agesci-campania-coreui-theme"`, bump del vincolo su
      `django-agesci-campania-theme` a `>=2.7.0` in `pyproject.toml`
- [x] `"agesci_coreui"` aggiunta a `INSTALLED_APPS` (`config/settings/base.py`)
- [x] `manage.py check` senza errori (`agesci_coreui.E001`)
- [x] Valutare aggiornamento `docs/docker.md`/`README.md` (nessun comando/dipendenza
      di setup è cambiato: `uv sync` resta invariato, nessun aggiornamento necessario)

### Fase 1 — Layout base ✅

- [x] `templates/base.html`: `{% extends "agesci_coreui/base.html" %}`
- [x] `sidebar_items` da `sezioni_menu` con `{% ag_nav_title %}`/`{% ag_nav_item %}`
      (markup `.nav-group`/`.nav-group-items` per le voci con `sottovoci`, es. "Nota
      Spese")
- [x] `sidebar_user` sovrascritto con `{% ag_avatar %}` per mantenere il dropdown
      (Cambia password, Preferenze, Impersona, Esci): il default CoreUI da solo non
      basta, non ha slot per questi link
- [x] `header_actions`/`header_nav`: nessun link da riportare — `offcanvas_nav`
      duplicava il menu della sidebar solo per mobile, ora la sidebar stessa è il menu
      mobile (nativo CoreUI), non c'era altro contenuto da preservare
- [x] Blocco `footer` riscritto (colonne + `{% include
      "agesci_theme/partials/cookie_banner.html" %}`)
- [x] Rimossi `templates/agesci_theme/partials/breadcrumb.html` e
      `templates/agesci_theme/partials/footer.html` (dead code)
- [x] Aggiornato `apps/core/tests/test_breadcrumb.py`: l'icona Home (override
      rimosso) non ha equivalente nel layout nativo, il test verifica ora solo la
      presenza del markup breadcrumb nativo (`class="breadcrumb"`)
- [x] `extra_js` verificato: script applicativi invariati (`table-filter.js`,
      `table-sort.js`, `cookie-banner.js`), nessuna dipendenza da Bootstrap JS

Verifica eseguita: `manage.py check`, `mise run lint`, `mise run test` (stessi 3
fallimenti PDF preesistenti su `main`, non correlati) e smoke test manuale via
Django test client su home e una pagina con voce di menu a sottovoci (Nota Spese) —
sidebar, `nav-group`, footer e breadcrumb renderizzano senza errori di template.

### Fase 2 — Verifica visiva end-to-end ✅

**Problemi trovati e corretti**:

- [x] Logo nel footer (`templates/base.html`, blocco `footer`) renderizzato a
      dimensione naturale enorme, sovrapposto al contenuto: avevo riportato la classe
      `ag-footer__logo` dal vecchio tema (definita solo in
      `agesci_theme/static/agesci_theme/css/agesci.min.css`, `height:48px`) senza
      verificare che il nuovo `agesci_coreui/static/agesci_coreui/css/
      agesci-coreui.min.css` **non** la includa (il namespace `.ag-footer*` non è stato
      portato nel tema CoreUI). Corretto con `style="height: 48px; width: auto;"`
      esplicito, indipendente dal CSS del tema. **Lezione**: ogni classe `ag-*`
      riportata da markup del vecchio tema va verificata contro il CSS del nuovo prima
      di assumerla esistente.
- [x] Banner di impersonificazione (D-27) invisibile finché non si scorreva oltre il
      footer: `HIJACK_INSERT_BEFORE = "</body>"` lo inserisce come ultimo elemento del
      `<body>`, dopo la sidebar `position: fixed` e il footer del nuovo layout —
      `position: sticky` da solo non basta se l'elemento nasce già fuori dal primo
      viewport. Spostato con `HIJACK_INSERT_BEFORE = '<div class="sidebar '`
      (`config/settings/base.py`): il banner ora è il primo elemento del `<body>`,
      visibile fin dal caricamento.
- [x] Tutte le tabelle dell'app (27 template su tutto il repo, non solo quelle nel
      giro di verifica) erano senza il wrapper `.table-responsive`: su mobile/basse
      risoluzioni una tabella larga va in overflow orizzontale oltre il viewport senza
      modo ovvio di raggiungerne il resto. **Problema ereditato dal tema Bootstrap**
      (non introdotto da questa migrazione: mancava anche prima), corretto comunque in
      questo giro perché emerso dalla verifica visiva. Esclusi i due template per
      WeasyPrint (`note_spese/nota_pdf.html`, `contributi/riepilogo_pdf.html`, mai
      renderizzati in browser).
- [x] "Visualizza anagrafica" (`apps/anagrafica/esportazione.py`) mostrava i codici
      gruppo invece dei nomi nelle colonne "Gruppo censimento"/"Gruppo servizio", pur
      avendo già i campi `_nome` calcolati e mai usati — **problema ereditato**, non
      introdotto dalla migrazione. Corretto usando i campi `_nome`.
- [x] `templates/anagrafica/esportazione_form.html` aveva `{% csrf_token %}` dentro un
      `<form method="get">`: il token finiva nella querystring della ricerca (CSRF
      protegge solo le richieste che cambiano stato, qui non serve). **Problema
      ereditato**, verificato "ovunque" nel repo (unico caso). Il token serve solo ai
      due bottoni "Esporta" (`formmethod="post"`): ora `disabled` di default,
      riabilitato via JS solo al click su quei bottoni.
- [x] Codici di decisione (`D-36`) ancora visibili in UI in `apps/note_spese/forms.py`
      (help_text di "Nuova nota spese") e in altri 16 punti di
      `apps/note_spese/models.py`/`forms.py` non ancora emersi a schermo — vincolo di
      `CLAUDE.md` (nessun `D-NN`/`M-NN` in testo utente). Rimossi tutti, migrazione
      `0014_alter_categoriaspesa_sottotipo_chilometrico_and_more` generata (solo
      `help_text`/`choices`, nessun cambio di schema).

**Deviazione dal piano di questa fase**: aggiunto anche l'autocompletamento per
"Codice socio del beneficiario" in "Nuova nota spese" (`BeneficiarioRicercaAutocompleteView`
in `apps/note_spese/views.py`, perimetro come `RicercaSociAutocompleteView` di M7 —
tutti i gruppi, non solo `gruppi_visibili`, riservato a chi gestisce le note). Non era
un problema introdotto dalla migrazione, ma un gap UX notato durante la stessa verifica
visiva e risolto su richiesta esplicita dell'utente.

- [x] `mise run dev`: home, lista con tabella filtrabile, form con
      `AgesciFormRenderer`, flusso impersonificazione, mobile (sidebar overlay sotto
      992px) e desktop (sidebar comprimibile) — verificati da Andrea con screenshot
      (`docs/ignored/checklist-verifica-coreui-fase2.md`, non versionato) e via browser
      automation per i fix sopra.
- [x] Confronto con la demo ufficiale
      (https://agesci-campania.github.io/django-agesci-campania-theme/coreui/) —
      nessuna discrepanza rilevata da Andrea.
- [x] Verifica palette per branca (`data-branca`, variabili `--cui-*`) — nessun
      problema rilevato da Andrea.

Verifica eseguita: `mise run lint` e `mise run test` verdi (stessi 3 fallimenti
PDF/WeasyPrint preesistenti su `main`, non correlati).

### Fase 3 — Adozione componenti CoreUI nei template applicativi ✅

- [x] `ag_chip` al posto di `<span class="badge ...">` in:
      `templates/accounts/sessioni_lista.html`, `templates/accounts/
      sessioni_tutte_lista.html` ("Sessione corrente" → `variant="secondary"`),
      `templates/anagrafica/importazione_cruscotto.html` (anomalie →
      `variant="warning"/"success"`), `templates/note_spese/evento_lista.html`
      (validato/non validato → `variant="success"/"warning"`),
      `templates/note_spese/nota_verifica_lista.html` (incarico "Altro"/doppione →
      `variant="warning"`), `templates/contributi/campagna_riepilogo_gruppi.html`
      (Sì/No, stato rimborso → `variant="success"/"danger"/"warning"/"secondary"`).
      **Eccezione dichiarata**: il badge "Capienza sforata (residuo indicativo
      …)" in `nota_verifica_lista.html` è rimasto uno `<span>` semplice — l'etichetta
      di `ag_chip` è una singola espressione di template, concatenarci un valore
      calcolato a runtime (il residuo) è più fragile del guadagno visivo.
      Verificato in browser (`mise run dev`): contrasto e colore corretti per ogni
      variante.
- [x] `ag_callout` per box informativi statici, valutato caso per caso: solo 2
      candidati genuini trovati su 15 paragrafi `text-muted` nel repo — un avviso
      su comportamento/conseguenze, non solo una descrizione di campo — in
      `templates/accounts/impersona_lista.html` (`variant="warning"`, perimetro
      impersonificazione) e `templates/note_spese/nota_verifica_lista.html`
      (`variant="info"`, le eccezioni non bloccano l'approvazione). Gli altri
      `text-muted` restano testo semplice: non ogni paragrafo informativo merita un
      riquadro.
- [x] `ag_avatar` per l'iniziale utente in `sidebar_user`: **già fatto in Fase 1**
      (`templates/base.html:42`), voce ridondante in questo elenco.
- [x] `CampoChip`/`InputChip`: confermato non applicabile, nessuna azione (nessun
      campo multi-valore libero nel dominio attuale).

Verifica eseguita: `manage.py check`, `mise run lint`, `mise run test` (stessi 3
fallimenti PDF/WeasyPrint preesistenti su `main`, non correlati) e verifica visiva
in browser di eventi, verifica note spese, cruscotto importazioni e impersona
utente.

### Fase 4 — Pulizia e checklist finale ✅

- [x] Rimuovere residui Bootstrap-specifici non più necessari — verificato con grep
      mirato: nessun `data-bs-*` residuo, `templates/agesci_theme/` contiene solo
      `partials/cookie_banner.html` (tenuto per scelta), `agesci_theme/css/
      agesci.min.css` è caricato solo da `templates/500.html` (pagina standalone che
      non estende il tema, per scelta esplicita già documentata lì). I due `<span
      class="badge ...">` rimasti (`nota_verifica_lista.html`, eccezione dichiarata in
      Fase 3; `contributi/partecipazione_inserisci.html`, badge JS-controllato fuori
      dall'elenco Fase 3) non sono residui da rimuovere, sono scelte deliberate.
- [x] Checklist di `CLAUDE.md`: `mise run lint` e `mise run test` verdi ad ogni fase
      (stessi 3 fallimenti PDF/WeasyPrint preesistenti su `main`); nessuna logica
      duplicata introdotta al di fuori del pattern già presente nel repo (i 4 endpoint
      di ricerca soci restano volutamente separati, stesso principio già in
      `CLAUDE.md` per gli altri 3); `README.md`/`docs/Catello_Progettazione.md`
      **non** aggiornati — descrivono lo stato di `main` (ancora sul tema Bootstrap):
      aggiornarli ora, a migrazione non ancora approvata/mergiata, li renderebbe
      disallineati dal codice realmente in produzione. Da fare in Fase 4 solo al
      momento del merge.
- [x] Valutare con l'utente se questa migrazione va tracciata anche in
      `docs/piano-sviluppo-todo.md` (fuori dallo schema M1-M13 esistente) o resta un
      piano a sé — **deciso con Andrea: resta un piano a sé**, non è una milestone di
      prodotto come M1-M13 ma un intervento di layout trasversale, questo file basta
      da solo.
- [x] Elencare esplicitamente ogni deviazione da questo piano — vedi sezione
      "Deviazioni dal piano" più sotto

## Deviazioni dal piano

- **Correzioni di bug ereditati dal tema Bootstrap, non introdotti da questa
  migrazione**, emersi durante la verifica visiva di Fase 2 e corretti nello stesso
  giro invece di essere solo segnalati: tabelle senza `.table-responsive` (27
  template su tutto il repo), codici invece di nomi gruppo nell'export anagrafica,
  `csrfmiddlewaretoken` in una querystring GET. Motivazione: erano bug reali trovati
  mentre si verificava proprio quelle pagine, rimandarli avrebbe richiesto una
  seconda sessione di verifica sulle stesse schermate.
- **Nuova funzionalità aggiunta durante la Fase 2**, non nel piano originale:
  autocompletamento per "Codice socio del beneficiario" in "Nuova nota spese"
  (`BeneficiarioRicercaAutocompleteView`, perimetro come `RicercaSociAutocompleteView`
  di M7). Motivazione: gap UX notato durante la verifica visiva e richiesto
  esplicitamente dall'utente nello stesso giro.
- **Pulizia D-NN in UI più ampia del previsto**: oltre al punto segnalato a schermo
  (`apps/note_spese/forms.py`), rimossi altri 16 riferimenti a `D-NN` in `help_text`
  di model/form field di `note_spese` non ancora emersi visivamente ma che
  violavano lo stesso vincolo di `CLAUDE.md`. Migrazione generata (solo `help_text`/
  `choices`, nessun cambio di schema).
- **Fase 3, `ag_callout`**: il piano lasciava "valutare caso per caso" senza
  elencare file. Convertiti solo 2 paragrafi su 15 candidati `text-muted` nel
  repo (quelli che sono un avviso su comportamento/conseguenze, non solo la
  descrizione di un campo) — una scelta di giudizio, non un'applicazione
  esaustiva a ogni testo informativo.
- **Fase 3, `ag_chip`**: un badge nell'elenco originale (`nota_verifica_lista.html`,
  "Capienza sforata (residuo indicativo …)") non è stato convertito: l'etichetta di
  `ag_chip` è una singola espressione di template, concatenarci un valore calcolato
  a runtime è più fragile del guadagno visivo. Resta uno `<span>` Bootstrap.
- **Fase 3, `ag_avatar`**: la voce del piano era già stata completata in Fase 1
  (`templates/base.html:42`) — nessun lavoro aggiuntivo necessario, solo una
  voce ridondante nell'elenco originale.

## File critici

- `config/settings/base.py` (`INSTALLED_APPS`, context processors, `FORM_RENDERER`)
- `templates/base.html` (riscrittura completa: `sidebar`, `sidebar_items`,
  `sidebar_user`, `footer`, `header_actions`)
- `templates/agesci_theme/partials/breadcrumb.html` (da rimuovere)
- `templates/agesci_theme/partials/footer.html` (da rimuovere, contenuto portato
  dentro `templates/base.html`)
- `templates/agesci_theme/partials/cookie_banner.html` (invariato, solo ripristinare
  l'`{% include %}`)
- `apps/core/tests/test_breadcrumb.py` (riga 87, da riscrivere)
- `pyproject.toml`/`uv.lock` (nuova dipendenza + bump vincolo tema base)
- Template con badge da valutare per `ag_chip` (elenco Fase 3)

## Verifica

- `mise run lint` e `mise run test` verdi ad ogni fase
- `manage.py check` per il system check `agesci_coreui.E001`
- Verifica manuale nel browser (`mise run dev`) di: home, sidebar desktop/mobile,
  breadcrumb su una pagina con sottovoce (Nota Spese), footer, cookie banner al primo
  accesso, form con `AgesciFormRenderer`, una lista con `ag_chip`, palette per branca
  diversa da quella di default
- Nessun push/merge su `main`: il lavoro resta sul branch dedicato fino ad
  approvazione esplicita
