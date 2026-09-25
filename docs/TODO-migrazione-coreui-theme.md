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

### Fase 0 — Setup branch e dipendenza ⬜

- [ ] Branch dedicato `migrazione-coreui-theme` da `main`
- [ ] `uv add "django-agesci-campania-coreui-theme"`, bump del vincolo su
      `django-agesci-campania-theme` a `>=2.7.0` in `pyproject.toml`
- [ ] `"agesci_coreui"` aggiunta a `INSTALLED_APPS` (`config/settings/base.py`)
- [ ] `manage.py check` senza errori (`agesci_coreui.E001`)
- [ ] Valutare aggiornamento `docs/docker.md`/`README.md`

### Fase 1 — Layout base ⬜

- [ ] `templates/base.html`: `{% extends "agesci_coreui/base.html" %}`
- [ ] `sidebar_items` da `sezioni_menu` con `{% ag_nav_title %}`/`{% ag_nav_item %}`
      (markup `.nav-group`/`.nav-group-items` per le voci con `sottovoci`, es. "Nota
      Spese")
- [ ] `sidebar_user`: valutare se basta il default CoreUI (avatar + nome) o va
      sovrascritto per mantenere il dropdown (Cambia password, Preferenze, Impersona,
      Esci)
- [ ] `header_actions`/`header_nav`: riportare eventuali link persi dalla rimozione di
      `offcanvas_nav`
- [ ] Blocco `footer` riscritto (colonne + `{% include
      "agesci_theme/partials/cookie_banner.html" %}`)
- [ ] Rimuovere `templates/agesci_theme/partials/breadcrumb.html` e
      `templates/agesci_theme/partials/footer.html` (dead code)
- [ ] Aggiornare `apps/core/tests/test_breadcrumb.py` (riga 87) per il markup CoreUI
- [ ] Verificare `extra_js` (script applicativi invariati, non dipendono da Bootstrap
      JS)

### Fase 2 — Verifica visiva end-to-end ⬜

- [ ] `mise run dev`: home, lista con tabella filtrabile, form con
      `AgesciFormRenderer`, flusso impersonificazione, mobile (sidebar overlay sotto
      992px) e desktop (sidebar comprimibile)
- [ ] Confronto con la demo ufficiale
      (https://agesci-campania.github.io/django-agesci-campania-theme/coreui/)
- [ ] Verifica palette per branca (`data-branca`, variabili `--cui-*`)

### Fase 3 — Adozione componenti CoreUI nei template applicativi ⬜

- [ ] `ag_chip` al posto di `<span class="badge ...">` in:
      `templates/accounts/sessioni_lista.html:30`,
      `templates/accounts/sessioni_tutte_lista.html:31` ("Sessione corrente"),
      `templates/anagrafica/importazione_cruscotto.html:37,39` (anomalie),
      `templates/note_spese/evento_lista.html:30,32` (validato/non validato),
      `templates/note_spese/nota_verifica_lista.html:45,48,51` (incarico "Altro"/
      doppione/anomalie), `templates/contributi/campagna_riepilogo_gruppi.html:31-55`
      (Sì/No, stato rimborso) — `variant="primary"` segue la branca, per questi usi
      semantici restano `variant="success"/"warning"/"danger"`
- [ ] `ag_callout` per box informativi statici (non i messaggi Django, quelli restano
      gestiti dal blocco `messages` del layout) — valutare caso per caso
- [ ] `ag_avatar` per l'iniziale utente in `sidebar_user` (oggi uno `<span>` con
      iniziale fatta a mano)
- [ ] `CampoChip`/`InputChip`: nessun campo multi-valore libero individuato nel
      dominio attuale (i multi-select esistenti usano `SelectMultiploADiscesa`) — non
      applicabile ora, opportunità futura

### Fase 4 — Pulizia e checklist finale ⬜

- [ ] Rimuovere residui Bootstrap-specifici non più necessari
- [ ] Checklist di `CLAUDE.md`: `mise run lint`, `mise run test`, nessuna logica
      duplicata, `README.md`/`docs/` aggiornati se necessario
- [ ] Valutare con l'utente se questa migrazione va tracciata anche in
      `docs/piano-sviluppo-todo.md` (fuori dallo schema M1-M13 esistente) o resta un
      piano a sé
- [ ] Elencare esplicitamente ogni deviazione da questo piano

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
