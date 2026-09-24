# TODO bugfixes — issue GitHub aperte

Tracciamento di lavoro delle issue GitHub del repository, aggiornato a mano a mano
che si decide/lavora su ciascuna. Le issue sono pubbliche e questo file non contiene
dati sensibili: è versionato normalmente insieme al codice.

## Stato

**Codici stato**: `OK` pianifichiamo la soluzione · `IGN` ignorata per ora ·
`NO: <motivo>` scartata (chiude la issue con motivazione) · `WIP` pianificato, in
lavorazione (issue aggiornata con causa + annuncio fix in arrivo) · `WVER` sviluppo
completato, in attesa di verifica · `VER` verificata da Andrea · `DONE: <hash>` fatta,
verificata, committata (chiude la issue).

### Da gestire

_Nessuna issue in questo stato al momento._

### Gestite

| # | Titolo | Urgenza | Complessità | Impatto utente | Impatto codice | Stato | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [#11](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/11) | Riepilogo contributi | Media | Medio-alta | Alto | Medio | DONE: 1fb4bfe | Tabella stato invio Fo.Ca. per gruppo, con semafori; flag "nessun rimborso richiesto"; rilasciato in v1.1.18, deployato in produzione — issue chiusa |
| [#12](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/12) | Sessioni scadute non ripulite automaticamente | Media | Bassa | Basso | Basso | DONE: 249fb23 | Nuovo servizio `pulizia-sessioni` in `compose.prod.yaml`; rilasciato in v1.1.18, deployato e verificato in produzione — issue chiusa |
| [#1](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/1) | Errore form partecipazione ai campi | Media | Bassa | Alto | Basso | DONE: a579d82 | Errori ora su `form.errors["data_inizio"]`/`"descrizione_altro"`, messaggio con date finestra — issue chiusa |
| [#2](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/2) | Pulsanti da nascondere se non si ha permesso | Bassa-media | Bassa | Medio | Molto basso | DONE: a579d82 | 9 pulsanti in campagna_dettaglio.html ora dietro `puo_gestire_campagna`/`puo_valutare_partecipazioni` — issue chiusa |
| [#3](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/3) | Personalizzazione errori (403/404/500 + mail admin) | Bassa (utente) / medio-alta (operativa) | Media | Medio | Medio | DONE: a579d82 | Template 403/404/500 + `ADMINS`/`AdminEmailHandler` in prod.py — issue chiusa |
| [#4](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/4) | Codici decisioni (D-NN) nei messaggi utente | Bassa-media | Bassa (concettuale) / media (estensione) | Medio-basso | Ampio ma meccanico | DONE: a579d82 | `apps/core/messaggi.py`, `_messaggio()` duplicato rimosso da 4 file — issue chiusa |
| [#5](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/5) | Manca una documentazione per i gruppi (primo nucleo: ruolo CG) | Alta | Media | Alto | Basso | DONE: 92ac3d3 | Prerequisito IBAN (a7e4102) + guida CG (92ac3d3) committati, pushati e deployati; verificato da Andrea — issue chiusa |
| [#6](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/6) | Miglioramento usabilità Impostazioni Template email | Bassa-media | Media | Medio | Medio | DONE: 13cc092 | Implementate le 4 richieste + validazione anti-duplicazione prefisso; deployato in produzione, verificato da Andrea — issue chiusa |
| [#7](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/7) | Possibilità di cambiare template colori della piattaforma | Bassa | Bassa-media | Medio | Basso-medio | DONE: f6c8cd6 | Preferenza personale + default di sistema, v1.1.9, deployato in produzione, verificato da Andrea — issue chiusa |
| [#8](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/8) | Allowlist: data ultimo accesso | Bassa | Bassa | Basso-medio | Basso | DONE: 4aa8519 | Colonna "Stato accesso" mostra ora anche `Utente.last_login`; rilasciato in v1.1.11, deployato in produzione — issue chiusa |
| [#9](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/9) | Sessione utente (proprie + tutte per Admin/Segreteria) | Media | Bassa (p.1) / Media (p.2) | Medio | Basso (p.1) / Medio (p.2) | DONE: 3620150 | `allauth.usersessions` attivato per il model, viste/template/menu propri; rilasciato in v1.1.11, deployato in produzione — issue chiusa |
| [#10](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/10) | Passkey ruoli amministrativi | Bassa | Media | Medio | Medio | DONE: 9826e6e | Rilasciato in v1.1.17, deployato in produzione, verificato da Andrea — issue chiusa |
| [#13](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/13) | Manca breadcrumb (Contributo Fo.Ca.) | Bassa | Bassa | Basso | Basso | DONE: 9458232 | `BreadcrumbExtraMixin` sulle 10 view figlie di una campagna in `apps/contributi/views.py`, stesso pattern di `GruppoGestioneView`; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |
| [#14](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/14) | Tasto da nascondere senza permessi (Impostazioni/Nuova campagna) | Bassa-media | Bassa | Medio | Molto basso | DONE: 9458232 | Stesso schema di #2 (già chiuso), esteso a `campagna_lista.html`; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |
| [#15](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/15) | Visibilità ultime campagne Contributo Fo.Ca. | Bassa | Bassa | Medio | Basso | DONE: 9458232 | Jumbotron con CTA per l'ultima campagna sopra la tabella esistente; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |
| [#16](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/16) | Errore tabella riepilogo gruppi | Media | Bassa | Medio-alto | Basso | DONE: 9458232 | `_stato_semaforo()` riscritta secondo le 4 regole della issue; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |
| [#17](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/17) | Colonna descrizione altro per tipologia campo | Media | Bassa | Alto | Molto basso | DONE: 9458232 | `Partecipazione.descrizione_altro` ora mostrata in `campagna_dettaglio.html`; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |
| [#18](https://github.com/AGESCI-Campania/segreteria-hirpinia/issues/18) | Possibilità di riaprire campagna in valutazione | Media | Media | Alto | Medio | DONE: 9458232 | Nuova transizione FSM IN_VALUTAZIONE → APERTA (`riapri_campagna`); motivo del respingimento ora mostrato in tabella; verificato da Andrea, in attesa di merge/deploy — vedi dettaglio sotto |

---

# Gestite

## #11 — Riepilogo contributi

**Testo della issue**: per i ruoli Admin/Segreteria/RdZ e per i capigruppo, una
tabella riassuntiva della situazione di invio dei gruppi sul contributo Fo.Ca.:
nome gruppo, stato attivazione (almeno un accesso), IBAN caricato, capi inseriti
per il rimborso (con conteggio), stato complessivo (semaforo verde/giallo/rosso).
Per il punto 4 serve anche un flag che un gruppo può impostare per dichiarare
"caricamento completato senza capi" (nessun rimborso richiesto per la campagna).
Dopo la chiusura campagna va mostrato anche il contributo che il gruppo riceve.
Va aggiornato anche il manuale per capigruppo.

**Origine reale (verificata nel codice, non dedotta):** nessuna delle 5 colonne
richieste esiste oggi come vista aggregata per gruppo — vanno costruite da dati
già presenti in modelli diversi, nessuno dei quali oggi le espone insieme:

1. **Nome gruppo**: `Gruppo.nome`/`Gruppo.codice` (`apps/organizzazione/models.py:30-78`).
2. **Almeno un accesso**: `Utente` ha già un collegamento **diretto** a `Gruppo`
   per gli account funzionali (`Utente.gruppo`, FK valorizzata solo per
   `tipo=TipoUtente.GRUPPO`, `apps/accounts/models.py:50`) e il campo standard
   Django `last_login` (popolato dal segnale `user_logged_in`, già usato per lo
   stesso scopo in #8/`AllowlistListaView`). **Non serve il match per email**
   usato in #8/`candidati_invito_massivo()` (quello serve prima della
   registrazione, qui l'account esiste già): basta
   `Utente.objects.filter(tipo=GRUPPO, gruppo=g).last_login` (un gruppo può
   avere più account, `Gruppo.account_consentiti` — va deciso se "attivato"
   significa *almeno uno* degli account ha fatto login, coerente col fatto che
   basta un accesso perché qualcuno possa operare per il gruppo).
3. **IBAN caricato**: `Gruppo.iban` non vuoto (`apps/organizzazione/models.py:60`)
   — già validato da `valida_iban()` all'inserimento (D-verificato altrove), qui
   serve solo il controllo di presenza. **Attenzione al vincolo CLAUDE.md**: IBAN
   "mai in log applicativi, mai in messaggi di errore, mai in export non
   bancari, mai in viste di elenco" — la tabella richiesta è per l'appunto una
   vista di elenco: va mostrato solo il semaforo booleano (presente/assente),
   **mai il valore dell'IBAN**, per non violare quel vincolo.
4. **Capi inseriti per il rimborso**: `Partecipazione` filtrate per
   `campagna` e `gruppo` (`apps/contributi/models.py:144-150`), con conteggio
   distinto capi (`values("capo").distinct().count()`, dato che un capo può
   avere più partecipazioni/campi nella stessa campagna) — da definire se il
   conteggio richiesto in issue è "partecipazioni" o "capi distinti", la issue
   dice "capi per i quali si richiede il rimborso" quindi probabilmente capi
   distinti, non partecipazioni. **Nuovo**: il flag "completato senza capi" non
   esiste in nessun modello — serve un nuovo campo persistito, verosimilmente su
   un nuovo model `DichiarazioneGruppoCampagna` (o simile) con FK a `Campagna` +
   `Gruppo` + booleano + chi/quando ha dichiarato, dato che oggi non c'è alcuna
   relazione diretta gruppo↔campagna a parte le `Partecipazione` stesse.
5. **Stato complessivo**: nessun calcolo esiste — va scritto come funzione pura
   nel service layer (semaforo verde se 2+3+4 tutti verificati, rosso se
   nessuno, giallo altrimenti), coerente con "service layer unico" di
   CLAUDE.md.
6. **Contributo ricevuto dopo chiusura**: `ContributoPartecipazione` (già usato
   da `calcola_riepilogo()` in `apps/contributi/riepilogo.py`) ha gli importi
   congelati per partecipazione — un totale per gruppo si calcola sommando quelle
   righe filtrate per gruppo, **mai congelato per gruppo** (vincolo CLAUDE.md
   "non congelare i totali per gruppo": il totale si calcola alla generazione,
   non si persiste — la nuova tabella deve rispettare lo stesso principio, non
   introdurre un campo `totale_gruppo` persistito).

**Perimetro**: la issue chiede la tabella sia per Admin/Segreteria/RdZ (tutti i
gruppi) sia per i capigruppo (probabilmente solo il proprio gruppo, coerente col
perimetro generale D-13/D-21 già in vigore in tutta l'app contributi — **non
esplicitato nella issue**, da confermare in pianificazione: dichiaro qui
l'inferenza, non è un fatto verificato nel testo della issue). Il service layer
di riferimento più vicino è `apps/contributi/visibilita.py::partecipazioni_visibili()`
(D-13) — probabile che la nuova funzione di riepilogo-gruppi debba seguire lo
stesso principio di filtro per ruolo, non essere scritta da zero.

**Esclusione E9001**: come già per M14 (`PartecipazioniRicercaSociAutocompleteView`,
A-8), il Comitato di Zona non genera contributo — da valutare se escluderlo anche
da questa tabella (probabile sì, ma non è nella issue: altra inferenza dichiarata).

- **Impatto utente**: alto. È una richiesta esplicita di visibilità operativa per
  chi segue le campagne (Admin/Segreteria/RdZ) e per i capigruppo, oggi assente:
  non esiste alcun modo di vedere collettivamente "chi manca" prima della
  chiusura campagna.
- **Impatto sul codice esistente**: medio.
  - Nuova migrazione per il flag "completato senza capi" (nuovo model o campo).
  - Nuova funzione pura nel service layer (`apps/contributi/riepilogo.py` sembra
    la collocazione naturale, già ha la logica di riepilogo campagna, ma questa
    è una vista **per gruppo**, non aggregata: valutare se estendere quel file o
    crearne uno dedicato, es. `apps/contributi/riepilogo_gruppi.py`, per non
    mescolare due concetti — il riepilogo D-13 esistente presuppone campagna
    CHIUSA/LIQUIDATA, mentre questa tabella deve essere utile **anche durante**
    l'inserimento, cioè a campagna ancora APERTA).
  - Nuova view + template, nuova voce di menu (pattern già visto per
    Allowlist/Sessioni: `RuoloRequiredMixin` per Admin/Segreteria/RdZ, perimetro
    ridotto per CG).
  - Aggiornamento del manuale capigruppo (`docs-utente/capogruppo/`, introdotto
    per #5) con la nuova pagina.
- **Complessità**: medio-alta. Non c'è un singolo punto difficile, ma tocca
  contemporaneamente: un nuovo model/migrazione, una nuova funzione di
  aggregazione multi-modello (Utente, Gruppo, Partecipazione,
  ContributoPartecipazione), due perimetri di visibilità diversi (tutti i
  gruppi vs. proprio gruppo) e la documentazione utente.
- **Urgenza (mia valutazione)**: media. Non blocca l'operatività attuale (le
  informazioni sono già recuperabili singolarmente, solo non aggregate in una
  vista), ma il valore per il follow-up delle campagne è alto e cresce a ogni
  campagna aperta.

**Decisione di Andrea (2026-09-13)**: la tabella non contiene dati sensibili,
quindi va mostrata **a tutti i gruppi, per chiunque acceda** — nessun
perimetro per-gruppo in lettura come nel resto dell'app contributi. Il
perimetro `gruppi_visibili()` resta usato solo per decidere, riga per riga, se
l'utente può *agire* (dichiarare "nessun rimborso").

**Implementazione (DONE: 1fb4bfe):**
- Nuovo model `DichiarazioneNessunRimborso` (`apps/contributi/models.py`,
  migrazione `0006_dichiarazionenessunrimborso`): FK `campagna`+`gruppo`
  (unique together), `dichiarata_da`, `dichiarata_il`.
- Nuovo service layer `apps/contributi/riepilogo_gruppi.py` (separato da
  `riepilogo.py`, che presuppone CHIUSA/LIQUIDATA): `riepilogo_gruppi(campagna)`
  ritorna una riga per ogni gruppo attivo (esclusa E9001), con i 4 booleani/
  conteggio richiesti dalla issue e il semaforo (`StatoSemaforo`); il
  contributo ricevuto è `None` prima della chiusura, mai congelato (calcolato
  a runtime da `ContributoPartecipazione`, stesso principio di
  `calcola_riepilogo()`). `dichiara_nessun_rimborso()`/
  `revoca_dichiarazione_nessun_rimborso()` verificano il permesso con lo
  stesso pattern di `risolvi_gruppo_competente()`
  (`apps/contributi/inserimento.py`): il gruppo deve stare in
  `gruppi_visibili(utente, anno)`, altrimenti `PermissionDenied`. La
  dichiarazione è rifiutata se il gruppo ha già partecipazioni inserite o se
  la campagna non è APERTA.
- Nuova `CampagnaRiepilogoGruppiView` (`apps/contributi/views.py`), stesso
  perimetro di accesso di `CampagnaDettaglioView`
  (`RUOLI_GESTIONE_PARTECIPAZIONI = {ADMIN, SEGRETERIA, RDZ, CG}`), URL
  `campagne/<int:pk>/gruppi/`. Nuovo template
  `templates/contributi/campagna_riepilogo_gruppi.html` (badge Bootstrap
  `text-bg-success`/`text-bg-warning`/`text-bg-danger`, stesso pattern già
  in uso in `importazione_cruscotto.html`), pulsante "Riepilogo gruppi"
  aggiunto a `campagna_dettaglio.html`. Il pulsante "Dichiara nessun
  rimborso"/"Revoca dichiarazione" compare solo sulla riga del gruppo su cui
  l'utente può agire (cosmetico, come da issue #2: il controllo reale resta
  nel service layer).
- Test: `apps/contributi/tests/test_riepilogo_gruppi.py` (semaforo
  verde/giallo/rosso, esclusione E9001, conteggio capi distinti, contributo
  `None`/valorizzato, permesso CG solo sul proprio gruppo vs.
  ADMIN/SEGRETERIA su qualunque, dichiarazione rifiutata con partecipazioni
  già presenti o a campagna non aperta, revoca), `test_views_riepilogo_gruppi.py`
  (403 per ruoli non ammessi, CG vede comunque tutti i gruppi, POST
  dichiara/revoca con perimetro rispettato). Un fixture SEGRETERIA nei test
  della vista deve avere un TOTP configurato (`MFAEnforcementMiddleware`),
  altrimenti la richiesta viene intercettata prima di arrivare alla view — lo
  stesso accorgimento già presente in `test_views_riepilogo.py`.
- Nuova pagina utente `docs-utente/capogruppo/riepilogo-contributi.md`
  (aggiunta a `mkdocs.yml` e a `docs-utente/index.md`) — **deviazione
  dichiarata**: a differenza della documentazione scritta per #5, questa
  pagina non ha screenshot reali (avrebbe richiesto un giro aggiuntivo di
  cattura in browser con dati fittizi): solo testo. Se serve, si possono
  aggiungere in un secondo momento.
- `mise run lint` pulito, `mise run test` verde (758 passati, nessuna
  regressione). Build `mkdocs build` verificata (con
  `DYLD_LIBRARY_PATH=/opt/homebrew/lib` per WeasyPrint su macOS, stesso
  problema noto già documentato).
- Commit `1fb4bfe`, rilasciato in v1.1.18 (tag e release GitHub creati),
  deployato in produzione (verificato con `docker compose ps`/`logs` e una
  richiesta HTTPS reale). Issue chiusa.

---

## #12 — Sessioni scadute non ripulite automaticamente

**Origine della issue**: segnalato da Andrea (2026-09-13) osservando in
produzione, nell'elenco "Sessioni utente" (Amministrazione, introdotto da #9),
sessioni molto vecchie ancora presenti, dovute rimuovere a mano.

**Origine reale (verificata nel codice, non dedotta):** `UserSession.purge()`
(pacchetto `allauth.usersessions`,
`.venv/lib/python3.14/site-packages/allauth/usersessions/models.py:111-122`,
richiamato da `sessioni_di()`/`tutte_le_sessioni()` in
`apps/accounts/sessioni.py:22-37`, introdotte per #9) scarta una sessione solo
se `self.exists()` è `False` — e `exists()` (riga 108-109) fa
`SessionStore.exists(session_key)`, cioè verifica solo che la riga esista
ancora nella tabella `django_session`, **senza controllare `expire_date`**. Il
backend sessioni in uso è quello di default di Django (nessun `SESSION_ENGINE`
in `config/settings/base.py`/`prod.py`, quindi `django.contrib.sessions.backends.db`):
la scadenza viene verificata solo quando la sessione viene effettivamente
caricata per autenticare una richiesta (`SessionStore.load()`), non da
`exists()`. Una riga scaduta ma mai più utilizzata resta quindi nella tabella
`django_session` a tempo indeterminato.

Django prevede per questo il comando integrato `manage.py clearsessions`
(pulizia periodica delle sessioni scadute), da schedulare esternamente (tipicamente
cron): **verificato che non è presente da nessuna parte nel progetto** — non in
`docker/entrypoint.sh` (che esegue solo `migrate` → `collectstatic` →
`gunicorn`, coerente col vincolo CLAUDE.md sui soli passi idempotenti lì
dentro), non nei task di `mise` (`mise.toml`), nessuno scheduling nei file
Docker Compose (`compose.yaml`/`compose.prod.yaml`). `SESSION_COOKIE_AGE` non è
mai impostato, quindi resta il default Django di 2 settimane.

- **Impatto utente**: basso. Nessun rischio di sicurezza reale (una sessione
  scaduta non è comunque più utilizzabile per autenticarsi, il controllo di
  validità avviene comunque al momento dell'uso) — è un problema di igiene dei
  dati e di leggibilità della pagina "Sessioni utente", che mostra righe non
  più significative.
- **Impatto sul codice esistente**: basso. Non tocca il service layer né i
  modelli applicativi: `clearsessions` è un comando Django già pronto, agisce
  solo sulla tabella `django_session` (nessuna relazione con `UserSession` di
  allauth, che si auto-ripulisce già correttamente non appena la riga
  `django_session` sottostante sparisce).
- **Complessità**: bassa. Nessuna migrazione, nessun nuovo model. Va solo
  deciso **dove** schedularlo, coerente col vincolo CLAUDE.md "niente
  Celery/Redis/broker" (D-17) e "niente comandi con privilegi elevati in
  `configure-prod.sh`": le opzioni realistiche sono un cron di sistema
  sull'host (fuori dalla portata di uno script che non deve toccare systemd) o
  un servizio schedulato dedicato nel `compose.prod.yaml` (es. un container
  supplementare con un semplice loop + sleep, oppure `ofelia`/`cron` nello
  stesso container `web` — da valutare in pianificazione, nessuna delle due
  opzioni è oggi presente nel progetto).
- **Urgenza (mia valutazione)**: media. Non è un problema di sicurezza né di
  correttezza funzionale, ma è destinato a peggiorare nel tempo (righe
  accumulate senza limite in `django_session`) e il fix è a basso rischio.

**Decisione di Andrea (2026-09-13)**: servizio schedulato dentro
`compose.prod.yaml`, non cron di sistema sull'host — coerente con la scelta già
fatta dal progetto di tenere in Compose tutto tranne il reverse proxy, così il
comportamento resta versionato e riproducibile su un nuovo host senza passi
manuali. Da tenere minimale: stesso image `web` già buildato, nessuna nuova
dipendenza, un semplice loop shell con `sleep` (es. una volta al giorno) invece
di introdurre uno scheduler dedicato (`ofelia`) per un solo comando.

**Implementazione (DONE: 249fb23):**
- `compose.prod.yaml`: aggiunto `image: catello-web:latest` esplicito al
  servizio `web` (così un altro servizio può riferirsi alla stessa immagine
  senza ribuildarla) e nuovo servizio `pulizia-sessioni`, stessa immagine,
  `env_file`/`environment` identici a `web` (necessari perché
  `config.settings.prod` carica per intero i settings anche solo per
  eseguire `manage.py clearsessions`). `entrypoint`/`command` sovrascritti
  (`/bin/sh -c` + loop `while true; do clearsessions; sleep 86400; done`) per
  non ereditare la sequenza fissa di `docker/entrypoint.sh`
  (migrate/collectstatic/gunicorn, pensata solo per `web`). Nessun
  `profiles:`, a differenza di Mailpit: parte con il normale
  `docker compose -f compose.prod.yaml up -d --build`.
- `docs/docker.md`: nuova voce nella tabella "Panoramica", paragrafo dopo la
  descrizione della sequenza fissa dell'entrypoint con il comando per
  vederne i log, nota nel paragrafo "Redeploy" che `up -d --build` ricrea
  anche `pulizia-sessioni` (stessa immagine di `web`).
- Verificato con `docker compose -f compose.prod.yaml --env-file .env.example
  config` che il file resta sintatticamente valido e che il nuovo servizio si
  espande correttamente (comando, entrypoint, variabili d'ambiente).
- Verificato in produzione dopo il deploy: `docker compose ps` mostra
  `catello_pulizia_sessioni` in esecuzione, `docker top catello_pulizia_sessioni`
  conferma il loop attivo (`clearsessions` già eseguito una volta, `sleep 86400`
  in corsa), il sito pubblico risponde correttamente
  (`https://segreteria.agescihirpinia.it/` → 302 verso il login).
- Commit `249fb23`, rilasciato in v1.1.18 (tag e release GitHub creati),
  deployato in produzione. Issue chiusa.

---

## #1 — Errore form partecipazione ai campi

**Origine reale (verificata nel codice, non dedotta):**
`apps/contributi/models.py::Partecipazione.clean()` (righe 194-219) **già** produce
errori per-campo in un dizionario (`data_inizio`, `data_fine`,
`descrizione_altro`, `motivazione_respingimento`), sollevati come
`ValidationError(errors)` da `full_clean()` dentro
`inserisci_partecipazione_manuale()` (`apps/contributi/inserimento.py:93`).

Il bug è nella view: `PartecipazioneInserisciView.post`
(`apps/contributi/views.py:178-179`) cattura l'eccezione come `ValidationError`
generica e la passa a `form.add_error(None, _messaggio(exc))` — `None` = errore non
di campo. La struttura per-campo esiste già a monte e viene buttata via qui: tutti gli
errori finiscono concatenati in un unico messaggio in cima al form, nessun campo
evidenziato.

In più, il messaggio per `data_inizio` (models.py:207-209) riporta solo l'anno, non
l'intervallo richiesto dall'utente nella issue: *"Fuori dalla finestra dell'anno
associativo 2026 (D-10)."* invece di *"deve essere tra dd/mm/yyyy e dd/mm/yyyy"* — i
valori `inizio`/`fine` sono già disponibili in quel punto (`self.campagna.finestra_associativa`),
manca solo di interpolarli nel messaggio.

- **Impatto utente**: alto per usabilità — chi inserisce partecipazioni manuali (CG e
  ruoli di gestione partecipazioni, uso frequente) riceve un errore generico invece di
  capire subito quale campo correggere. Non blocca l'operazione, la rende solo
  frustrante.
- **Impatto sul codice esistente**: basso e localizzato. Non tocca il service layer né
  il modello (la logica di validazione è già corretta). Serve solo:
  1. In `Partecipazione.clean()`, arricchire il messaggio di `data_inizio` con le date
     della finestra.
  2. Nella view, propagare gli errori per campo (`exc.error_dict` quando presente,
     altrimenti fallback a `form.add_error(None, ...)`) invece di appiattire tutto.
  3. Nel template, verificare che `form.data_inizio.errors` ecc. siano già renderizzati
     accanto al campo (probabile, essendo un `forms.Form` Bootstrap-style) — solo da
     controllare, non da riscrivere.
- **Complessità**: bassa. Nessuna migrazione, nessun cambio di contratto del service
  layer, un solo punto di vista da correggere (pattern `_messaggio`/`form.add_error`
  potrebbe ripetersi in altre view: da verificare se vale la pena un helper comune —
  vedi sovrapposizione con #4 sotto).
- **Urgenza (mia valutazione)**: media. Non è un bug bloccante né di sicurezza, ma è ad
  alta frequenza d'uso (ogni inserimento partecipazione) e il fix è a basso rischio:
  buon rapporto beneficio/sforzo.

---

## #2 — Pulsanti da nascondere se non si ha permesso

**Origine reale (verificata):** `templates/contributi/campagna_dettaglio.html:24-26`
mostra il pulsante "Avvia valutazione" senza alcun controllo di permesso — nessun
`{% if %}` sul ruolo. La view che renderizza la pagina,
`CampagnaDettaglioView` (`apps/contributi/views.py:106-121`), è protetta solo da
`RuoloRequiredMixin` con `ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI`, un perimetro
**più ampio** di quello richiesto dall'azione: `PartecipazioneCampagnaAvviaValutazioneView`
chiama `avvia_valutazione()` → `verifica_ruolo_gestione_campagna()`
(`apps/contributi/campagne.py:42-51`), che richiede `RUOLI_GESTIONE_CAMPAGNA`
(SEGRETERIA/ADMIN/RDZ, anche per delega) — un sottoinsieme più stretto.

Un utente con solo ruolo di gestione-partecipazioni (es. CG) vede quindi un pulsante
che non può usare, e ottiene il 403 già gestito correttamente lato service layer (D-27:
il controllo di accesso è già nel service layer, non nel template — questo è rispettato;
manca solo il *nascondere* lato UI, che è cosmetico, non un buco di sicurezza).
- **Impatto utente**: medio — confusione/frustrazione per chi vede un'azione che non
  può eseguire, ma nessun rischio di sicurezza (il controllo reale è a posto).
- **Impatto sul codice esistente**: molto basso. Serve solo passare al contesto del
  template un flag calcolato con `ruoli_effettivi(request.user)` (già esiste, D-04) o
  con una funzione di verifica "read-only" equivalente a
  `verifica_ruolo_gestione_campagna` ma che ritorna `bool` invece di sollevare, e
  condizionare il blocco `<form>` nel template.
- **Complessità**: bassa. Nessuna migrazione, nessun service layer nuovo. Attenzione:
  se ci sono altri pulsanti con lo stesso problema (chiudi campagna, liquida, genera
  bonifici, ecc. in altri template) andrebbero verificati insieme per non doverlo
  rifare issue per issue — vale la pena un controllo sistematico di tutti i pulsanti di
  azione nei template di `contributi/` e `organizzazione/` prima di considerarla chiusa,
  non solo "Avvia valutazione".
- **Urgenza (mia valutazione)**: bassa-media. Non è un bug bloccante né di sicurezza,
  ma è visibile e facile da risolvere bene in un colpo solo se estesa a tutti i pulsanti
  analoghi.

---

## #3 — Personalizzazione errori (403/404/500 + mail admin)

**Origine reale (verificata):** non esistono `403.html`/`404.html`/`500.html`
personalizzati nel progetto (solo quelli di default di `django.contrib.admin`, non
usati per errori applicativi). Non esiste alcun `handler403`/`handler404`/`handler500`
in `config/urls.py`, né `ADMINS` in `config/settings/base.py`/`prod.py`, né un
`AdminEmailHandler` in `LOGGING` (verificato in `config/settings/base.py:214` e
`config/settings/prod.py:49`). In produzione, con `DEBUG=False`, Django serve le
pagine di errore stock, senza tema e senza notifica.

Questa è una feature nuova, non un fix di una regressione: tre pezzi distinti.
- **Impatto utente**: medio — le pagine di errore stock rompono la coerenza visiva
  (rilevato dallo screenshot allegato alla issue) e non aiutano l'utente in caso di 403/404.
  Il beneficio principale però è operativo/per gli admin (notifica immediata degli errori
  500), non per l'utente finale.
- **Impatto sul codice esistente**: medio.
  1. Template 403/404/500 in tema (`agesci_theme/base.html`, coerente col vincolo
     "Tema" di CLAUDE.md — **nessun CSS custom**, solo utility del tema).
  2. `ADMINS` in `config/settings/prod.py` + verificare che `EMAIL_PROVIDER` sia già
     collegato correttamente per l'invio delle mail di errore (il progetto ha già
     un'infrastruttura email solida per M8 template, ma le mail di errore Django
     passano dal canale standard `mail_admins`/`AdminEmailHandler`, **non** dal motore
     `TemplateEmail` — sono due percorsi distinti, da non confondere: le mail di errore
     sono testo semplice generato da Django, non passano da `invia_email_template()`).
  3. Per la mail con "log e descrizione errore" serve un logger dedicato con handler
     `AdminEmailHandler` sul logger `django.request` (standard Django) — attenzione al
     vincolo "mai loggare token/segreti/corpo messaggi" già in CLAUDE.md: verificare che
     il traceback non esponga IBAN o dati sensibili delle request coinvolte (es. request
     POST con IBAN in chiaro finirebbe nella mail di errore se non filtrata — Django ha
     `sensitive_variables`/`sensitive_post_parameters` per questo, da applicare alle view
     che maneggiano `Gruppo.iban`).
- **Complessità**: medio. Non tecnicamente difficile, ma con più parti (3 template +
  settings + eventuale filtro dati sensibili) e un punto di attenzione reale sulla
  sicurezza (vincolo IBAN mai in log/errori, esistente in CLAUDE.md) che va rispettato
  anche nelle mail di errore automatiche, non solo nei log applicativi.
- **Urgenza (mia valutazione)**: bassa per l'utente (cosmetica), ma medio-alta dal
  punto di vista operativo: oggi un errore 500 in produzione non genera alcun avviso,
  quindi un problema reale potrebbe passare inosservato. Consiglio di scorporare la
  mail admin (valore operativo alto, rischio basso) dalla personalizzazione grafica
  delle pagine (valore cosmetico) se si vuole rilasciare la parte utile prima.

---

## #4 — Codici decisioni (D-NN) nei messaggi utente

**Origine reale (verificata):** i codici `D-NN` compaiono letteralmente in decine di
stringhe passate a `ValidationError`/`PermissionDenied` nel service layer — non un
caso isolato. Occorrenze confermate in almeno: `apps/contributi/campagne.py`,
`apps/contributi/valutazione.py`, `apps/contributi/models.py`,
`apps/contributi/inserimento.py`, `apps/contributi/bonifici.py`,
`apps/contributi/riepilogo.py`, `apps/organizzazione/gruppi.py`,
`apps/anagrafica/incarichi.py`, `apps/anagrafica/importazione_autorizzazioni.py`,
`apps/accounts/models.py`, `apps/accounts/audit.py`.

Confermato che questi messaggi **arrivano davvero all'utente**, non solo ai log: sia
`apps/contributi/views.py:634-637` sia `apps/organizzazione/views.py:270-273`
definiscono un identico helper `_messaggio(exc)` che fa `str(exc)` (o
`"; ".join(exc.messages)`) e lo passa direttamente a `form.add_error(...)` /
`messages.error(...)` — nessun filtro, nessuna distinzione fra utente e admin. Non
esiste una via separata "log per amministratori": oggi il D-NN è nello stesso identico
messaggio mostrato a chiunque.

- **Impatto utente**: medio-basso in sé (i codici non sono pericolosi, solo rumore
  interno di progettazione visibile a persone che non hanno motivo di conoscerli), ma
  è un problema di percezione di qualità/professionalità della piattaforma, come
  segnalato nella issue.
- **Impatto sul codice esistente**: **ampio in estensione, ma meccanico**. Non è un
  fix concettualmente complesso — è ripetuto in decine di punti. Due strade:
  1. **Chirurgica**: rimuovere `(D-NN)` da ogni stringa di errore user-facing una per
     una (~30-40 occorrenze in stringhe di eccezione, da distinguere da quelle in
     docstring/commenti/help_text che non sono un problema, essendo visibili solo a chi
     legge il codice). Nessun rischio, nessuna astrazione nuova, ma tocca molti file.
  2. **Strutturale**: introdurre in `_messaggio()` (unificarla in un solo posto, oggi
     duplicata identica in due file — occasione per estrarla in un modulo comune) uno
     strip automatico via regex del pattern `\s*\(D-\d+(/D-\d+)*\)` a fine stringa,
     così i D-NN restano nei messaggi grezzi del service layer (utili come riferimento
     per chi legge il codice/i test) ma non arrivano mai al rendering utente. Più
     robusto a dimenticanze future, ma introduce una trasformazione "magica" sul testo
     che va documentata bene per non sorprendere chi scrive un nuovo messaggio.
- **Complessità**: bassa concettualmente, media in estensione per l'opzione 1; bassa e
  bassa per l'opzione 2 (un solo punto, ma da verificare che non rompa messaggi che
  legittimamente contengono "D-" per altri motivi — nessuno trovato nei grep fatti).
  Consiglio l'opzione 2: un solo punto di verità, coerente con lo spirito
  "service layer unico" già richiesto da CLAUDE.md, e riduce il rischio che un nuovo
  messaggio futuro dimentichi la regola.
- **Urgenza (mia valutazione)**: bassa-media. Nessun impatto funzionale, ma è a bassa
  complessità/rischio con l'approccio strutturale: buon rapporto costo/beneficio,
  anche se non urgente in senso stretto.

**Nota di sovrapposizione con #1**: il fix per #1 punto 2 (propagare gli errori per
campo invece di appiattirli) e il fix per #4 (centralizzare `_messaggio()`) toccano lo
stesso punto del codice — se si lavora su entrambe conviene farle insieme per non
riscrivere `_messaggio()` due volte.

---

## #5 — Manca una documentazione per i gruppi (primo nucleo: ruolo CG)

**Precisazione di Andrea (non nella issue originale)**: la documentazione richiesta
riguarda **solo** gli utenti con ruolo CG (account funzionale email di gruppo), come
primo nucleo — da estendere in futuro agli altri ruoli (segreteria/RDZ/ecc.), ma non
ora. Urgenza alta per questo primo nucleo.

**Origine reale (verificata nel codice, non dedotta):** non esiste alcuna
documentazione rivolta al ruolo CG nel repository — solo materiale tecnico/di
progettazione in `docs/` (`Catello_Progettazione.md`, `TODO.md`,
`piano-sviluppo-todo.md`, `docker.md`, `email/*.md`). Non esiste `docs/user/`, né
`mkdocs.yml`/`conf.py`/`.readthedocs.yaml`.

**Perimetro reale del ruolo CG (verificato nel codice)**: la stima iniziale di Andrea
("set molto ristretto: solo IBAN e partecipazioni Fo.Ca.") **non è confermata dal
codice** — il perimetro CG è più ampio. Funzioni raggiungibili da un utente con
`Ruolo.Tipo.CG` (dirette o per delega, salvo dove indicato):

1. **IBAN e intestazione conto del gruppo** — `GruppoGestioneView`
   (`apps/organizzazione/views.py:147-182`), URL `/gruppi/<codice>/gestione/`,
   permesso per-oggetto `verifica_ruolo_gestione_dati_gruppo` (CG solo sul proprio
   gruppo). **Non esisteva nel form/service layer fino a oggi** (vedi sotto,
   implementato in questo stesso intervento).
2. **Inserimento manuale partecipazione Fo.Ca.** — `PartecipazioneInserisciView`
   (`apps/contributi/views.py:132-199`), perimetro
   `RUOLI_GESTIONE_PARTECIPAZIONI = {ADMIN, SEGRETERIA, RDZ, CG}`
   (`apps/contributi/inserimento.py:25-27`).
3. **Import massivo partecipazioni (anteprima + conferma)** — stesso perimetro,
   `PartecipazioniImportAnteprimaView`/`PartecipazioniImportConfermaView`
   (`apps/contributi/views.py:255-338`), più il download del modello XLSX
   (`ModelloXlsxPartecipazioniView`) e il dettaglio importazione.
4. **Allegati a una partecipazione** — `AllegatoPartecipazioneCaricaView`
   (`apps/contributi/views.py:575`), stesso perimetro.
5. **Assegnazione manuale di incarichi nel proprio gruppo** — `RUOLI_ASSEGNAZIONE_INCARICHI`
   include CG (`apps/anagrafica/incarichi.py:39-42`).
6. **Esportazione anagrafica del proprio gruppo** — `RUOLI_EXPORT_ANAGRAFICA` include CG
   (`apps/anagrafica/esportazione.py:44-46`).

**Esplicitamente escluso per CG** (da non documentare come disponibile): gestione
campagna (crea/apri/chiudi/simula/bonifici/liquida/report PDF — solo
ADMIN/SEGRETERIA/RDZ), valutazione partecipazioni, ricerca capo cross-gruppo
(`apps/anagrafica/incarichi.py:44-46`).

**Gap risolto in questo stesso intervento**: il form `GruppoModificaForm`
(`apps/organizzazione/forms.py`) e la funzione di service `modifica_dati_gruppo()`
(`apps/organizzazione/gruppi.py`) **non includevano `iban`/`intestazione_conto`** —
un CG non poteva impostare l'IBAN da interfaccia, solo da Django admin (a cui non ha
accesso). Implementato: campi aggiunti al form, `clean_iban()` che sanifica l'errore
di `valida_iban()` (che altrimenti includerebbe il valore non valido nel messaggio,
violando il vincolo CLAUDE.md "IBAN mai nei messaggi di errore" — stesso motivo per
cui `apps/contributi/campagne.py::chiudi_campagna` già scarta quel messaggio),
`Gruppo` già tracciato da `django-auditlog`. Test aggiunti in
`apps/organizzazione/tests/test_gruppi.py` e `test_views_gruppi.py` (incluso un test
che verifica che un IBAN non valido non compaia nel messaggio d'errore restituito).

- **Impatto utente**: alto. Le due funzioni che Andrea vuole documentare per prime
  (IBAN e partecipazioni) sono quelle a maggior impatto pratico per il CG, e fino a
  oggi una delle due (IBAN) era di fatto inutilizzabile.
- **Impatto sul codice esistente**: basso per la documentazione in sé (additiva); il
  prerequisito IBAN è **già implementato e testato** (vedi sopra), non resta più da
  fare lato codice per questo primo nucleo.
- **Complessità**: media per il primo nucleo (2 flussi, non l'intera piattaforma:
  IBAN/intestazione conto + inserimento/import partecipazioni), non più "alta" come
  nella stima iniziale che copriva tutti i flussi capogruppo. Resta da decidere
  formato/toolchain (MkDocs + Read the Docs + export PDF, ancora da introdurre — nessun
  toolchain esiste oggi nel repository).
- **Urgenza (mia valutazione, allineata a quella di Andrea)**: alta per questo primo
  nucleo — Andrea ha confermato esplicitamente che è la priorità corrente, il resto
  (altri ruoli) è rimandato a un secondo momento.

**Implementazione (WVER, in attesa di push/deploy e collegamento Read the Docs):**
- Toolchain **MkDocs + Material** (scelta esplicita di Andrea, non Sphinx): nuovo
  gruppo di dipendenze `docs` in `pyproject.toml` (`mkdocs`, `mkdocs-material`,
  `mkdocs-with-pdf`), `mkdocs.yml` in root con `docs_dir: docs-utente` (per non
  toccare `docs/`, già usato per la documentazione tecnica), export PDF verso
  `site/pdf/guida-capigruppo.pdf`, `.readthedocs.yaml` pronto per il collegamento
  (da fare a mano da Andrea: creazione progetto su readthedocs.org — fuori dalla mia
  portata, richiede le sue credenziali).
- Contenuti in `docs-utente/`: `index.md` (introduzione, accesso, MFA obbligatoria) +
  `capogruppo/iban-gruppo.md` + `capogruppo/partecipazioni-foca.md` (inserimento
  singolo e import massivo, con avvisi sul blocco bonifico per IBAN errato e sul
  flusso anteprima/conferma D-21 già documentato in CLAUDE.md).
- **Screenshot reali**, non segnaposto (scelta esplicita di Andrea): catturati in
  locale con browser automatizzato, loggato come CG con un gruppo (`E0900`) e un
  capo (`DEMO0001`) di prova — nomi chiaramente fittizi, mai dati reali di soci
  (vincolo CLAUDE.md sui dati sensibili). Verificato end-to-end anche il fix IBAN di
  questa stessa issue: salvataggio riuscito con messaggio "Dati del gruppo
  aggiornati". Dati di prova rimossi dal DB locale a fine sessione.
- Nuovi task `mise run docs-serve`/`docs-build`, documentati in README.md insieme al
  nuovo gruppo di dipendenze; `site/` aggiunto a `.gitignore` (output generato).
- Build verificata **due volte**: `mkdocs build` locale (HTML + PDF, con
  `DYLD_LIBRARY_PATH=/opt/homebrew/lib` per WeasyPrint su macOS, stesso problema noto
  già documentato per i test) e resa visiva delle pagine HTML in browser (menu,
  indice, immagini incluse correttamente).
- `mise run lint` pulito, `mise run test` verde (696 passati, unico fallimento
  pre-esistente WeasyPrint locale, non collegato a questa modifica).
- **Non ancora fatto**: commit/push/deploy (in attesa di conferma di Andrea, come per
  le altre due modifiche di questa sessione) e collegamento dell'account Read the
  Docs (fuori dalla mia portata).

---

## #6 — Miglioramento usabilità Impostazioni Template email

**Origine reale (verificata nel codice, non dedotta):** riguarda `TemplateEmail` (M8):
`apps/core/models.py`, `apps/core/templates/core/template_email_modifica.html`,
`apps/core/template_email.py`. Le 4 richieste sono indipendenti fra loro, nessuna
esiste oggi:

1. **Prefisso oggetto comune** — non esiste. `ImpostazioniPiattaforma`
   (`apps/core/models.py:76-102`) ha solo `causale_bonifico_default` e
   `email_su_mailpit`: nessun campo prefisso/subject in tutto il dominio email.
2. **Firma comune (RichText + fallback testo)** — non esiste. Nessun campo
   "firma"/"signature" nel dominio email (gli unici hit di "firma" nel codebase sono
   una docstring e una firma di funzione, non pertinenti).
3. **Pulsante copia RichText → fallback testo** — non esiste. Nel template
   `template_email_modifica.html` i campi `corpo_html` e `corpo_testo` sono renderizzati
   come form field indipendenti, senza alcun pulsante o script di generazione
   automatica dell'uno a partire dall'altro.
4. **Editor codice HTML in TinyMCE** — assente. L'inizializzazione
   `tinymce.init({...})` nello stesso template configura
   `plugins: "lists link autolink table image"` e
   `toolbar: "undo redo | bold italic underline | bullist numlist | link table image"`:
   nessun plugin/pulsante `code` (sorgente HTML).

L'elenco dei tag/placeholder disponibili per template **esiste già** (non è nella
issue come richiesta nuova, ma come vincolo da rispettare per il nuovo tag
`subjectPrefix`): è mostrato in `template_email_modifica.html:10-12`, popolato da
`VARIABILI_PER_CODICE` (`apps/core/template_email.py:22-42`). Il motore ridotto
(`sostituisci_placeholder()`, righe 90-98) fa solo match `\{\{\s*(\w+)\s*\}\}` contro il
dizionario di contesto passato dal chiamante: non esistono oggi variabili globali
predefinite (come sarebbe `subjectPrefix`) iniettate automaticamente in ogni template.

- **Impatto utente**: medio. Nessuna delle 4 richieste è bloccante; migliorano
  coerenza (prefisso/firma uniformi su tutte le comunicazioni) ed efficienza di editing
  per chi gestisce i template (probabilmente SEGRETERIA/ADMIN, uso non frequente).
- **Impatto sul codice esistente**: medio.
  - Prefisso e firma richiedono nuovi campi su `ImpostazioniPiattaforma` (migrazione)
    e un punto di applicazione: **non** nel motore ridotto per l'oggetto (la issue
    chiede esplicitamente che `subjectPrefix` non sia utilizzabile nell'oggetto per
    evitare duplicazioni, essendo già inserito automaticamente lì), ma va comunque reso
    disponibile come variabile nel corpo — quindi va iniettato nel contesto di
    `sostituisci_placeholder()` a monte, in `invia_email_template()`
    (`apps/core/invio_email.py`), senza toccare le 6 email applicative che già passano
    da lì. La firma (HTML e testo) va sanificata con `sanifica_html()` come già fatto
    per `corpo_html` (vincolo esistente in CLAUDE.md), essendo anch'essa RichText
    modificabile da interfaccia.
  - Il pulsante di copia RichText→testo è puro JS lato editor (nessun impatto
    backend): serve solo estrarre il testo semplice dal contenuto TinyMCE
    (`tinymce.get(...).getContent({format: "text"})`) e popolare il campo
    `corpo_testo`.
  - Il plugin `code` di TinyMCE va vendorizzato con la stessa identica procedura già
    documentata in CLAUDE.md per `table`/`image` (stessa versione 8.8.2, stessa fonte,
    stesso file di licenza) — non `latest`.
- **Complessità**: media. Nessun punto singolarmente difficile, ma 4 modifiche
  distinte con superfici diverse (model+migrazione, service layer email, JS editor,
  vendoring TinyMCE): da trattare come 4 unità di lavoro separate anche se rilasciate
  insieme, per non mescolare rischi diversi in un solo commit.
- **Urgenza (mia valutazione)**: bassa-media. Miglioramento di usabilità per un
  pannello a bassa frequenza d'uso, nessun rischio per dati sensibili se implementato
  rispettando i vincoli già esistenti su sanificazione e vendoring.

**Implementazione (WVER, in attesa di verifica utente):**
- `ImpostazioniPiattaforma`: nuovi campi `prefisso_oggetto_email`, `firma_html`,
  `firma_testo` (migrazione `0006_impostazionipiattaforma_firma_html_and_more`).
- `apps/core/template_email.py`: `applica_prefisso_oggetto()` e
  `contesto_con_variabili_globali()` (funzioni pure), variabile globale
  `{{ subjectPrefix }}` (`VARIABILI_GLOBALI`).
- `apps/core/invio_email.py`: nuova `comporre_contenuto()` — unico punto che applica
  prefisso oggetto e firma, usato sia da `invia_email_template()` sia dall'anteprima in
  `TemplateEmailModificaView` (nessuna duplicazione della regola).
- `TemplateEmailForm.clean_oggetto()`: rifiuta `{{ subjectPrefix }}` nell'oggetto del
  singolo template (evita la duplicazione segnalata in issue), ammesso in corpo e firma.
- Pulsante "Genera dal contenuto HTML" (JS, `tinymce.get(...).getContent({format:
  "text"})`) sia in `template_email_modifica.html` (corpo) sia in `impostazioni.html`
  (firma).
- Plugin `code` di TinyMCE vendorizzato in `static/vendor/tinymce/plugins/code/` —
  stessa versione 8.8.2, stessa fonte (pacchetto npm ufficiale `tinymce`), stessa
  licenza già presente, verificato con `diff` byte-a-byte contro un plugin già
  vendorizzato (`table`) per confermare la fonte. Abilitato in entrambi gli editor
  (corpo template e firma HTML).
- Elenco variabili globali mostrato in UI accanto a quelle per-template, con link a
  Impostazioni.
- Test aggiunti: `apps/core/tests/test_invio_email.py` (prefisso su template/fallback,
  variabile nel corpo, firma testo/HTML, nessuna firma = nessun cambiamento),
  `test_views_template_email.py` (validazione `subjectPrefix` in oggetto),
  `test_impostazioni.py` (salvataggio dei nuovi campi). `mise run lint` pulito,
  `mise run test` verde (unico fallimento residuo: WeasyPrint su macOS locale,
  pre-esistente e non collegato a questa modifica).

---

## #7 — Possibilità di cambiare template colori della piattaforma

**Origine reale (verificata nel codice, non dedotta):** il tema
`django-agesci-campania-theme` (v2.4.1, `.venv/lib/python3.14/site-packages/agesci_theme/`)
supporta nativamente **6 schemi colore fissi**, ma legati al concetto di branca scout, non
a una palette libera: mappa SCSS `$branche` in `static/agesci_theme/scss/_branche.scss`
(`generico`, `capi`, `lc`, `eg`, `rs`, `viola` come alias di `capi`). Il mixin
`tema-primario()` genera per ciascuna un set di custom property CSS (`--bs-primary`,
`--ag-primary`, `--ag-primary-hover`, `--ag-primary-active`, `--ag-primary-subtle`,
`--ag-on-primary`, `--bs-link-color`), applicate via `[data-branca="nome"]` sul tag
`<html>` (impostato dal `base.html` del pacchetto:
`<html data-branca="{{ agesci_theme_branca|default:'generico' }}">`).

Oggi la branca è **hardcoded** in `config/settings/base.py:219`
(`AGESCI_THEME_BRANCA = "capi"`), letta a livello di processo da
`agesci_theme.context_processors.agesci_theme` e iniettata in ogni template come
`agesci_theme_branca` — non è né per-utente né configurabile da interfaccia. Le utility
citate in CLAUDE.md (`bg-ag-viola`, `text-ag-*`, `{% branca_bg %}`) leggono le stesse
variabili derivate dalla branca attiva, non sono selezionabili indipendentemente.
`ImpostazioniPiattaforma` (`apps/core/models.py:76-122`, singleton `pk=1` +
`corrente()`) non ha oggi alcun campo relativo a tema/colori.

- **Impatto utente**: medio. Nessun blocco funzionale; personalizzazione visiva
  richiesta esplicitamente da Andrea, probabilmente per riflettere l'identità del
  gruppo/zona invece del viola Co.Ca. fisso attuale.
- **Impatto sul codice esistente**: basso-medio. **Nessun CSS custom da scrivere** (le
  6 palette esistono già nel tema, coerente col vincolo CLAUDE.md "non scrivere CSS
  custom per i colori, chiedi prima"). Serve:
  1. Nuovo campo su `ImpostazioniPiattaforma` (es. `branca_tema`, scelte vincolate a
     `{"generico", "capi", "lc", "eg", "rs", "viola"}` — lo stesso insieme già validato
     in `agesci_theme/context_processors.py`, da non reinventare) + migrazione.
  2. Un context processor applicativo che sovrascriva/wrappi
     `agesci_theme_branca` leggendo `ImpostazioniPiattaforma.corrente().branca_tema`
     invece del valore statico di `settings.py` — il tema non offre un hook più diretto
     di questo.
  3. Estendere la pagina Impostazioni già esistente (stessa usata per causale bonifico,
     prefisso oggetto e firma email) con il nuovo campo, nessuna nuova view.
- **Complessità**: bassa-media. Un solo punto di lettura configurabile, nessuna
  migrazione di dati esistenti, nessuna nuova infrastruttura — ma tocca un
  context processor globale (superficie ampia: ogni pagina), da testare con
  attenzione per non rompere il rendering quando il valore non è ancora impostato
  (default `"generico"` o `"capi"`, coerente con l'attuale).
- **Urgenza (mia valutazione)**: bassa. Puramente estetica/di brand, nessun rischio né
  blocco per l'operatività; fattibile con sforzo contenuto quando si deciderà di
  pianificarla.

**Specifiche di Andrea per la pianificazione:**
- Un utente non privilegiato può cambiare lo schema colori solo per sé: al login vede
  la piattaforma con il tema scelto, per gli altri resta quello di sistema.
- Un utente privilegiato (Admin/Segreteria/RDZ) può scegliere se cambiare la palette
  solo per sé o per tutti (default di sistema), senza mai sovrascrivere le preferenze
  personali già impostate da altri.

**Implementazione (WIP, sviluppata e testata in locale, non ancora committata):**
- `apps/core/tema.py` (nuovo): `SCELTE_BRANCA_TEMA`, le 5 palette distinte del tema
  (esclusa `viola`, alias di `capi`), condivise fra i due nuovi campi.
- `Utente.branca_tema_preferita` (`apps/accounts/models.py`, migrazione
  `0005_utente_branca_tema_preferita`): preferenza personale, vuoto = eredita dal
  sistema.
- `ImpostazioniPiattaforma.branca_tema_default` (`apps/core/models.py`, migrazione
  `0007_impostazionipiattaforma_branca_tema_default`): default di sistema, vuoto =
  resta il default del tema. Aggiunto a `ImpostazioniPiattaformaForm`, compare
  automaticamente nella pagina Impostazioni già gated da `RUOLI_GESTIONE_IMPOSTAZIONI`.
- Nuovo context processor `apps.core.context_processors.tema_branca`, registrato
  **dopo** `agesci_theme.context_processors.agesci_theme` in
  `config/settings/base.py`: preferenza personale (se presente) > default di sistema
  (se presente) > default del tema, invariato. Query singola su PK, nessuna cache
  introdotta.
- Nuova pagina "Preferenze" per **qualunque** utente loggato: `PreferenzeView`
  (`apps/accounts/views.py`, solo `LoginRequiredMixin`, nessun gate di ruolo),
  `PreferenzeUtenteForm` (`apps/accounts/forms.py`), route
  `accounts:preferenze` (`/accounts/preferenze/`), template
  `apps/accounts/templates/accounts/preferenze.html`, voce nel dropdown utente
  (`templates/base.html`, tra "Cambia password" e "Esci").
- Test aggiunti: `apps/core/tests/test_tema_branca.py` (precedenza personale/sistema/
  tema, incluso il caso esplicito richiesto: il cambio del default di sistema non
  tocca una preferenza personale già impostata da un altro utente),
  `apps/core/tests/test_impostazioni.py::TestBrancaTemaDefault` (solo i privilegiati
  possono impostare il default), `apps/accounts/tests/test_views_preferenze.py`
  (qualunque utente loggato accede e salva, senza impattare altri utenti).
- Verificato anche end-to-end via `Client` di Django (non solo unit test): utente CG
  senza preferenza eredita il default di sistema, con preferenza personale la
  preferenza vince sempre, `/impostazioni/` resta 403 per il CG, `/accounts/preferenze/`
  200 e salva correttamente. Dati di prova rimossi dal DB locale a fine sessione.
- `mise run lint` pulito, `mise run test` verde (710 passati, unico fallimento
  pre-esistente WeasyPrint su macOS locale, non collegato a questa modifica —
  confermato passare con `DYLD_LIBRARY_PATH` impostato).
- **Non ancora fatto**: commit/push/deploy, in attesa di conferma di Andrea.

---

## #8 — Allowlist: data ultimo accesso

**Origine reale (verificata nel codice, non dedotta):** la pagina è
`AllowlistListaView` (`apps/organizzazione/views.py:185-201`), template
`organizzazione/allowlist_lista.html`. La colonna **"Stato accesso" esiste già**
(riga 25 del template) ma mostra solo un testo statico calcolato in
`get_context_data` (righe 193-201): un booleano `voce.mai_effettuato_accesso`, reso
come "Mai effettuato l'accesso" oppure "Account già attivo o gruppo non attivo"
(righe 41-47) — nessuna data.

`AllowlistGruppo` (`apps/organizzazione/models.py:154-182`) non ha una FK a `Utente`:
il collegamento riga↔account è solo per email. `Utente` (`apps/accounts/models.py:45-108`)
eredita da `AbstractUser` il campo standard **`last_login`**, popolato dal meccanismo
Django standard (`user_logged_in` signal), non da allauth né da codice custom — nessun
override trovato. Il campo è già usato oggi in
`apps/accounts/inviti.py:125-141::candidati_invito_massivo()` per determinare
(per email, case-insensitive) chi ha già effettuato l'accesso — stesso identico match
che serve qui, oggi ridotto a booleano.

- **Impatto utente**: basso-medio. Nessun blocco, solo un'informazione in più utile a
  chi gestisce l'allowlist (probabilmente ADMIN/SEGRETERIA) per capire da quanto tempo
  un account è inattivo, non solo se lo è.
- **Impatto sul codice esistente**: basso. Nessuna migrazione (il campo esiste già).
  Serve solo:
  1. In `AllowlistListaView.get_context_data`, costruire una mappa email→`last_login`
     (stesso pattern/query di `candidati_invito_massivo()`, non da duplicare
     ma eventualmente da fattorizzare in una funzione condivisa se il testo della
     query è identico) e assegnarla per riga, accanto a `mai_effettuato_accesso`.
  2. Nel template (righe 41-47), mostrare la data quando presente (es.
     `{{ voce.ultimo_accesso|date:"d/m/Y H:i" }}"`), mantenendo il messaggio attuale
     quando `None`.
- **Complessità**: bassa. Un solo file di view + un solo template, nessun nuovo
  service layer, nessuna migrazione.
- **Urgenza (mia valutazione)**: bassa. Miglioramento informativo puro, nessun
  rischio né blocco operativo.

**Implementazione (WVER, in attesa di verifica utente):**
- `AllowlistListaView.get_context_data` (`apps/organizzazione/views.py`): mappa
  email→`last_login` costruita con lo stesso match case-insensitive di
  `candidati_invito_massivo()`, assegnata per riga come `voce.ultimo_accesso`.
- Template (`allowlist_lista.html`): terzo ramo nella colonna "Stato accesso" —
  data (`d/m/Y H:i`) quando presente, altrimenti il testo esistente invariato.
  Nessuna migrazione (il campo `last_login` esisteva già).
- Test aggiunti in `apps/organizzazione/tests/test_views_allowlist.py`
  (`TestAllowlistUltimoAccesso`): data mostrata quando l'utente ha
  `last_login`, non mostrata (resta "Mai effettuato l'accesso") quando non
  l'ha mai effettuato. `mise run lint` pulito, `mise run test` verde (725
  passati, unico fallimento residuo WeasyPrint su macOS locale, pre-esistente
  e non collegato a questa modifica).
- Commit `4aa8519`, rilasciato in v1.1.11, deployato in produzione (verificato
  con `docker compose ps`/`logs` e una richiesta HTTP reale). Issue chiusa.

---

## #9 — Sessione utente

**Correzione rispetto alla mia prima valutazione**: avevo scritto "nessuna
infrastruttura riusabile" e "va scritto ex novo" senza controllare se `django-allauth`
(già dipendenza del progetto, `pyproject.toml:13`,
`"django-allauth[mfa]>=65.0"`) includesse già questa funzione — un errore di
verifica, non solo di formulazione. Andrea ha segnalato il gap (2026-09-08) chiedendo
di `allauth-usersessions`: verificato che non è un package a parte, ma un
**sotto-modulo incluso nella stessa dipendenza già installata**,
`allauth.usersessions` (confermato in
`.venv/lib/python3.14/site-packages/allauth/usersessions/`), oggi **non elencato**
in `INSTALLED_APPS` (`config/settings/base.py:63-65` ha solo `allauth`,
`allauth.account`, `allauth.mfa`). Nessuna nuova dipendenza da aggiungere.

**Cosa offre già `allauth.usersessions` (letto il codice del pacchetto, non dedotto
dalla documentazione)**:
- `UserSession` (model): `user` (FK), `session_key`, `ip`, `user_agent`,
  `created_at`, `last_seen_at` — popolato da `UserSessionManager.create_from_request`,
  agganciato al segnale `user_logged_in` (`apps.py::ready()`). Nessun decode manuale
  di `django_session` necessario: il collegamento sessione↔utente è già denormalizzato
  nel model.
- `ListUserSessionsView` (`views.py`) + `usersessions/usersession_list.html`
  (template già pronto nel pacchetto, in stile allauth): elenca le sessioni
  dell'utente corrente, evidenzia quella corrente (`session.is_current`), azione
  "Sign Out Other Sessions" → `ManageUserSessionsForm.save()` →
  `flows.sessions.end_other_sessions()`.
- **Limite reale verificato**: `end_other_sessions()` termina *tutte le altre*
  sessioni in un colpo solo (`for session in ... if not session.is_current(): ...`),
  **non permette di selezionarne una specifica**. Se la issue richiede di poter
  terminare una singola sessione a scelta (non tutte le altre insieme), serve
  comunque una piccola estensione sopra il flow esistente — il model e la vista di
  base restano riusabili, cambia solo la form/azione.
- `UserSessionAdmin` (`admin.py`): registra `UserSession` nel **Django admin**
  (list_display `user`/`created_at`/`last_seen_at`/`ip`/`user_agent`, ricerca per
  utente/ip) — dà già una vista di tutte le sessioni con dati puliti, **ma** gated dai
  permessi Django admin (staff/superuser), **non** dal sistema di ruoli Catello
  (`ADMIN`/`SEGRETERIA`/`RDZ`): non soddisfa da solo il requisito del punto 2 ("Admin e
  Segreteria, non RDZ" + "un menu in amministrazione" dell'app, non Django admin).
- `USERSESSIONS_TRACK_ACTIVITY` (default `False`): se non attivato, `last_seen_at` non
  viene aggiornato — da valutare se attivarlo (comporta un aggiornamento ad ogni
  richiesta via `UserSessionsMiddleware`, verificarne il costo prima di abilitarlo).

**Per il perimetro "Admin e Segreteria (non RDZ)" del punto 2**: il pattern di
`RuoloRequiredMixin` + `ruoli_ammessi` esiste già (come in
`AllowlistListaView.ruoli_ammessi = RUOLI_GESTIONE_GRUPPI`), ma va definito un nuovo
`frozenset` **senza RDZ** — quello più simile oggi, `RUOLI_GESTIONE_RUOLI`
(`apps/accounts/ruoli.py:17`), include invece RDZ e non è riusabile direttamente.

`django-hijack`, presente per l'impersonificazione, resta non pertinente: gestisce le
proprie sessioni internamente (id utente originale nella sessione Django corrente) e
il progetto traccia solo le sessioni di *impersonificazione* con
`SessioneImpersonificazione` (`apps/accounts/models.py:338-360`) — un modello
analogo ma per un caso d'uso diverso.

- **Impatto utente**: medio. Nessun blocco funzionale, ma è una richiesta di
  sicurezza/controllo genuina (chiudere una sessione dimenticata su un dispositivo
  condiviso; per Admin/Segreteria, visibilità su accessi anomali).
- **Impatto sul codice esistente**: **basso per il punto 1** (ridimensionato rispetto
  alla prima valutazione), medio per il punto 2:
  1. **Proprie sessioni** (punto 1): aggiungere `"allauth.usersessions"` a
     `INSTALLED_APPS`, includere le sue `urls.py` (route `usersessions_list`),
     eventualmente integrare il template nel tema (`agesci_theme/base.html`, come già
     fatto per gli altri template allauth — vedi il commento in
     `config/settings/base.py:57-60` sull'ordine app tema/allauth), voce nel menu
     utente (`templates/base.html:68-86`). Se serve la terminazione selettiva
     (non solo "tutte le altre"), estendere `ManageUserSessionsForm`/il flow con la
     selezione per `pk`, verificando che un utente non possa terminare una sessione
     non propria (`UserSession.objects.filter(user=request.user, pk=...)`, mai un
     `get()` non filtrato per utente).
  2. **Tutte le sessioni** (punto 2): nuova vista applicativa (non Django admin)
     sopra `UserSession.objects.all()` — **senza decode di `django_session`**, il
     model espone già `user`/`ip`/`user_agent`/`created_at`/`last_seen_at` — protetta
     da un nuovo `frozenset {ADMIN, SEGRETERIA}` via `RuoloRequiredMixin`, voce nel
     menu "Amministrazione" (stesso pattern di "Allowlist gruppi"), azione di
     terminazione che opera su `UserSession` di un utente arbitrario (superficie più
     delicata: terminare la sessione di un altro utente è un'azione con impatto
     diretto su un account non proprio, da tracciare quantomeno nei log applicativi).
- **Complessità**: bassa per il punto 1 (attivazione di un modulo già incluso nella
  dipendenza esistente + integrazione tema/menu, non sviluppo ex novo), media per il
  punto 2 (vista + perimetro di ruolo nuovi, ma sul model già pronto di
  `allauth.usersessions`, non su `django_session` grezza).
- **Urgenza (mia valutazione)**: media. Non blocca l'operatività quotidiana, ma il
  punto 1 ha ora un rapporto costo/beneficio molto migliore della prima stima —
  vale la pena considerarlo a sé, a basso rischio, indipendentemente da quando si
  pianifica il punto 2 (perimetro di ruolo da definire con cura).

**Implementazione (WVER, in attesa di verifica utente):**
- **Deviazione dichiarata rispetto al piano**: non ho collegato le viste/URL/template
  di default di `allauth.usersessions` (`ListUserSessionsView` + `/accounts/sessions/`),
  attivate comunque in automatico da `allauth.urls` una volta aggiunta l'app —
  restano raggiungibili come percorso alternativo, gated da login, non linkate da
  nessun menu. Ho scritto viste/template/URL propri (`apps/accounts/sessioni.py`,
  `SessioniListaView`/`SessioneTerminaView`/`SessioniTutteListaView`/
  `SessioneTerminaAltruiView` in `views.py`) perché il flow di allauth termina solo
  "tutte le altre sessioni insieme", non una selezionata, e non ha un equivalente
  applicativo (con perimetro di ruolo Catello) per il punto 2. **Riuso reale**: il
  model `UserSession` (popolamento automatico via segnale, niente decode di
  `django_session`) e i suoi metodi `purge()`/`purge_and_list()`/`is_current()`/`end()`.
- `apps/accounts/sessioni.py` (nuovo, service layer): `RUOLI_GESTIONE_SESSIONI =
  {ADMIN, SEGRETERIA}` (RDZ escluso di proposito), `sessioni_di()`/`tutte_le_sessioni()`
  (basate su `purge()`, righe fantasma scartate), `termina_sessione_propria()`
  (perimetro: proprietà della sessione, non ruolo) e `termina_sessione_di_altri()`
  (verifica ruolo nel service layer, D-27). Se la sessione terminata è quella
  corrente, `django.contrib.auth.logout()` viene chiamato esplicitamente (altrimenti
  la richiesta in corso resterebbe autenticata fino alla successiva).
- `config/settings/base.py`: `"allauth.usersessions"` in `INSTALLED_APPS` (solo per
  il model, commentato esplicitamente), `UserSessionsMiddleware` in `MIDDLEWARE`,
  `USERSESSIONS_TRACK_ACTIVITY = True` (altrimenti "ultima attività" coinciderebbe
  sempre con "accesso effettuato il", vanificando la pagina).
- 4 nuove view in `apps/accounts/views.py` + route in `apps/accounts/urls.py`
  (`/accounts/sessioni/`, `/accounts/sessioni/<pk>/termina/`,
  `/accounts/sessioni/tutte/`, `/accounts/sessioni/tutte/<pk>/termina/`), 2 nuovi
  template (`templates/accounts/sessioni_lista.html`,
  `templates/accounts/sessioni_tutte_lista.html`), stesso stile tabellare di
  `ruolo_lista.html`/`deleghe_lista.html`.
- Menu (`apps/core/menu.py`): "Le mie sessioni" in Account (chiunque loggato),
  "Sessioni utente" in Amministrazione (`RUOLI_GESTIONE_SESSIONI`, `solo_diretti=True`
  — stesso trattamento di Ruoli/Impostazioni, non delegabile: scelta dichiarata, la
  issue non specifica se le deleghe contano, ho scelto il perimetro più stretto per
  un'azione che termina la sessione di un altro utente).
- Test aggiunti: `apps/accounts/tests/test_sessioni.py` (isolamento fra utenti,
  divieto di terminare sessioni altrui dal proprio endpoint, perimetro
  ADMIN/SEGRETERIA con RDZ esplicitamente escluso, terminazione altrui da parte di
  ADMIN/SEGRETERIA), `apps/organizzazione/tests/test_views_allowlist.py` per #8.
  Verificato anche manualmente via test client con una sessione reale (login
  completo su `SessionStore`, non solo `_auth_user_id`) per escludere falsi
  positivi dovuti a `purge()` che scarta le sessioni non valide.
- `mise run lint` pulito, `mise run test` verde (725 passati, unico fallimento
  residuo WeasyPrint su macOS locale, pre-esistente e non collegato a questa
  modifica). Migrazione applicata: `usersessions.0001_initial` (del pacchetto
  `allauth`, non generata da noi).
- Commit `3620150`, rilasciato in v1.1.11, deployato in produzione (verificato
  con `docker compose ps`/`logs` e una richiesta HTTP reale). Issue chiusa.
  **Non ancora fatto**: verifica visiva in browser della resa nel tema (solo
  via test client finora) — da fare se si vuole controllare a occhio.

---

## #10 — Passkey ruoli amministrativi

**Testo della issue**: "Sarebbe utile per i ruoli amministrativi (admin e segreteria)
poter definire delle passkey per poter velocizzare l'accesso. Ovviamente in questo
caso non serve il MFA".

**Origine reale (verificata nel codice, non dedotta):** oggi l'MFA è gestito da
`django-allauth[mfa]` v65.19.1 (`pyproject.toml:13`), con
`MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]` (`config/settings/base.py:200`) —
**nessun supporto WebAuthn/passkey attivato**, ma il pacchetto già installato lo
offre nativamente: `allauth.mfa.webauthn` esiste in
`.venv/lib/python3.14/site-packages/allauth/mfa/webauthn/` (stages, forms, views,
`internal/auth.py`), e `allauth.mfa.app_settings.AppSettings.PASSKEY_LOGIN_ENABLED`
(righe 102-106) è già predisposto per il login **senza password**, tramite sola
passkey, quando `"webauthn"` è in `MFA_SUPPORTED_TYPES` e
`MFA_PASSKEY_LOGIN_ENABLED = True`. **Nessuna nuova dipendenza**: il pacchetto
`fido2` (richiesto da WebAuthn) è già presente nel venv, tirato dentro
dall'extra `[mfa]` già dichiarato.

**Il punto delicato è la seconda frase della issue** ("non serve il MFA"), che va
letta contro l'enforcement esistente: `MFAEnforcementMiddleware`
(`apps/accounts/middleware.py:82-112`) reindirizza a `mfa_activate_totp` chiunque
abbia (direttamente, non per delega) un ruolo in `RUOLI_MFA_OBBLIGATORIA =
{"ADMIN", "SEGRETERIA", "RDZ"}` (`config/settings/base.py:223`) e non abbia
**TOTP** configurato — il controllo (`_richiede_mfa_non_configurata`, riga 112) è
scritto esplicitamente per il tipo `Authenticator.Type.TOTP`, ignora ogni altro
authenticator. Con l'implementazione attuale, un ADMIN/SEGRETERIA con **solo** una
passkey configurata verrebbe comunque rimandato ad attivare il TOTP: la richiesta
"non serve il MFA" non è soddisfatta senza toccare anche questa logica, non solo
abilitando `webauthn` fra i tipi supportati.

Nota: la issue nomina solo "admin e segreteria", `RUOLI_MFA_OBBLIGATORIA` include
anche RDZ — da chiarire in pianificazione se RDZ resta escluso dalla nuova opzione
o va incluso per coerenza con l'obbligo MFA esistente (i tre ruoli oggi condividono
lo stesso enforcement).

- **Impatto utente**: medio. Nessun blocco: è un miglioramento di comodità/velocità
  di accesso per i ruoli a maggiore frequenza d'uso (ADMIN/SEGRETERIA), che oggi
  devono comunque password + TOTP a ogni login.
- **Impatto sul codice esistente**: medio.
  1. Aggiungere `"webauthn"` a `MFA_SUPPORTED_TYPES` e `MFA_PASSKEY_LOGIN_ENABLED =
     True` (o equivalente) — attiva le view/URL di `allauth.mfa.webauthn` già
     pronte nel pacchetto (registrazione, gestione, login) senza scriverle da zero.
  2. Decidere e implementare la relazione fra passkey e obbligo MFA: la lettura più
     coerente con la issue è che il possesso di **una passkey verificata** soddisfi
     da solo `RUOLI_MFA_OBBLIGATORIA` per quel ruolo, sostituendo (non affiancando)
     il requisito TOTP — richiede modificare `_richiede_mfa_non_configurata` per
     controllare `types=[Authenticator.Type.TOTP, Authenticator.Type.WEBAUTHN]`
     invece del solo TOTP, e verificare lo stesso punto in
     `apps/accounts/adapters.py:57` (stessa costante, altro uso di
     `RUOLI_MFA_OBBLIGATORIA` da non dimenticare).
  3. Template/menu: `allauth.mfa.webauthn` porta proprie pagine di gestione
     (aggiungi/rinomina/rimuovi passkey) — da integrare nel tema come già fatto per
     le altre pagine allauth (`config/settings/base.py:57-60`, stesso ordine
     app tema/allauth già commentato per #9), non da riscrivere.
- **Complessità**: media. Nessuna nuova dipendenza né migrazione di dati esistenti
  (il model `Authenticator` di allauth.mfa è generico, già usato per TOTP), ma la
  modifica dell'enforcement MFA tocca un punto di sicurezza attivo in produzione
  (D-05) — da testare con attenzione i casi limite: utente con solo TOTP, solo
  passkey, entrambi, nessuno dei due, e delega di ruolo (l'enforcement si applica
  solo a chi ha il ruolo direttamente, non per delega — comportamento esistente da
  preservare).
- **Urgenza (mia valutazione)**: bassa. Nessun rischio né blocco, comodità per un
  numero ristretto di utenti (ADMIN/SEGRETERIA); da pianificare quando c'è
  disponibilità, non prioritaria.

**Decisioni di Andrea (2026-09-11)**:
1. **Sostituzione con fallback**: una passkey verificata soddisfa da sola
   `RUOLI_MFA_OBBLIGATORIA` per ADMIN/SEGRETERIA (non serve avere anche il TOTP
   attivo), ma deve restare disponibile un fallback per la perdita del dispositivo
   — i **recovery codes** (già supportati da `MFA_SUPPORTED_TYPES`), non il TOTP
   come alternativa equivalente.
2. **RDZ resta escluso, ma ADMIN/SEGRETERIA vincono sempre**: RDZ è un incarico
   di funzione (non personale come ADMIN/SEGRETERIA), resta con il solo obbligo
   TOTP. Un utente con ruoli diretti multipli (es. ADMIN **e** RDZ) è comunque
   coperto dall'insieme più ampio: se ha ADMIN o SEGRETERIA, la passkey basta,
   indipendentemente dal fatto che abbia anche RDZ — non vince il perimetro più
   stretto. `RUOLI_MFA_OBBLIGATORIA` resta `{"ADMIN", "SEGRETERIA", "RDZ"}`
   invariata per l'obbligo di *avere un secondo fattore*; cambia solo *quali tipi*
   lo soddisfano, tramite la nuova `RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN",
   "SEGRETERIA"}`.

**Implementazione (WVER, in attesa di verifica utente):**
- `config/settings/base.py`: `MFA_SUPPORTED_TYPES` include ora `"webauthn"`,
  `MFA_PASSKEY_LOGIN_ENABLED = True` (login diretto con passkey, nessuna nuova
  dipendenza: `fido2` è già nel venv via l'extra `django-allauth[mfa]`),
  `RUOLI_MFA_ACCETTA_PASSKEY = {"ADMIN", "SEGRETERIA"}`.
- `apps/accounts/mfa.py` (nuovo, service layer unico): `tipi_mfa_accettati()`
  calcola l'unione dei tipi accettati sui ruoli diretti obbligati dell'utente —
  unico punto di verità, usato sia dall'enforcement sia dalla cancellazione.
- `apps/accounts/middleware.py::MFAEnforcementMiddleware`: usa
  `tipi_mfa_accettati()` invece del solo TOTP; redirect verso `mfa_index`
  (pagina generale di gestione MFA) invece del vecchio `mfa_activate_totp`
  hardcoded.
- `apps/accounts/adapters.py::CatelloMFAAdapter.can_delete_authenticator`:
  stessa logica, estesa da "impedisci l'ultimo TOTP" a "impedisci l'ultimo
  fattore fra quelli accettati" — i recovery codes non contano mai come fattore
  a sé (restano il fallback, coerente con la decisione 1).
- `apps/core/menu.py`: nuova voce "Sicurezza account" → `mfa_index` nella
  sezione Account (visibile a chiunque, come "Le mie sessioni"), altrimenti
  l'unico modo di raggiungere la pagina sarebbe il redirect forzato.
- **Bug trovato e corretto durante la verifica manuale** (non dal codice
  esistente, introdotto abilitando `webauthn`): la pagina
  `mfa/webauthn/authenticator_list.html` di allauth usa `{% load humanize %}`
  (per mostrare "creata il"/"usata l'ultima volta" in modo relativo), ma
  `django.contrib.humanize` non era fra le `INSTALLED_APPS` — la pagina andava
  in `TemplateSyntaxError` (500). Aggiunta l'app, verificato con `Client` di
  Django che `mfa_index`/`mfa_list_webauthn` rispondono 200 e `mfa_add_webauthn`
  reindirizza correttamente alla ri-autenticazione richiesta da allauth per
  operazioni sensibili (comportamento standard, non un bug).
- Template: **nessun template nuovo scritto**. Verificata nel codice la catena
  di ereditarietà `mfa/webauthn/base.html` → `mfa/base_manage.html` →
  `allauth/layouts/manage.html` → `allauth/layouts/base.html`, quest'ultimo già
  sovrascritto dal tema (stesso meccanismo di TOTP/recovery codes, nessuna
  novità architetturale).
- Test aggiunti in `apps/accounts/tests/test_allauth_adapter.py`: enforcement
  per ADMIN con sola passkey (ammesso), RDZ con sola passkey (bloccato, richiede
  comunque TOTP), ADMIN+RDZ diretti insieme (passkey basta, vince il perimetro
  più ampio); cancellazione dell'ultimo fattore accettato bloccata, permessa se
  ne resta un altro, recovery codes sempre cancellabili liberamente, nessun
  vincolo per chi non ha ruoli obbligati.
- `mise run lint` pulito, `mise run test` verde (741 passati, unico fallimento
  residuo WeasyPrint su macOS locale, pre-esistente e non collegato).
- Commit `9826e6e`, rilasciato in v1.1.17 (tag e release GitHub creati),
  deployato in produzione (verificato con `docker compose ps`/`logs` e una
  richiesta HTTP reale) e verificato end-to-end da Andrea con un dispositivo
  reale. Issue chiusa.

## #13 — Manca breadcrumb (Contributo Fo.Ca.)

**Origine reale (verificata):** `apps/core/context_processors.py::breadcrumb()`
genera automaticamente Home › Sezione › Voce solo quando `request.path` coincide
esattamente con una voce di `sezioni_menu()` — e l'unica voce di menu di questo
modulo è "Contributo Fo.Ca." → `contributi:campagna_lista`
(`apps/core/menu.py:113-114`). Ogni pagina "figlia" (`campagna_dettaglio`,
`campagna_riepilogo_gruppi`, `partecipazione_inserisci`, ecc.) mostra quindi solo
"Home", a meno che la view implementi `BreadcrumbExtraMixin`
(`apps/core/mixins.py`) — meccanismo già usato altrove nel repo (es.
`GruppoGestioneView` in `apps/organizzazione/views.py:148`, `GruppoIncarichiView`
in `apps/anagrafica/views.py:528`) ma **mai adottato in `apps/contributi/views.py`**:
nessuna delle sue view lo eredita.

Le tre URL riportate nella issue sono solo un campione: verificato che il problema
è sistemico su **tutte** le 10 view di `contributi` che renderizzano un template
(`template_name` impostato, vedi elenco sotto) tranne quella già in menu.

- **Impatto utente**: basso — non è un blocco funzionale, solo un vuoto di
  orientamento (l'utente non vede "dove si trova" navigando dentro una campagna).
- **Impatto sul codice esistente**: basso. Nessuna migrazione, nessuna modifica a
  service layer. Solo `BreadcrumbExtraMixin` + un metodo `breadcrumb_extra()` per
  vista, sul modello già in uso.
- **Complessità**: bassa, ma ampia in numero di view (10) — mai una modifica di
  logica, solo aggiunta meccanica dello stesso pattern.

**Soluzione proposta:**

Aggiungere `BreadcrumbExtraMixin` e `breadcrumb_extra()` a ciascuna view, con la
stessa etichetta di sezione "Contributo Fo.Ca." e la campagna come primo livello
(`Campagna {{ anno }}`), poi l'etichetta della sotto-pagina:

| View | Catena dopo Home |
| --- | --- |
| `CampagnaCreaView` | Contributo Fo.Ca. › Nuova campagna |
| `CampagnaDettaglioView` | Contributo Fo.Ca. › Campagna {anno} |
| `CampagnaRiepilogoGruppiView` | Contributo Fo.Ca. › Campagna {anno} › Riepilogo gruppi |
| `PartecipazioneInserisciView` | Contributo Fo.Ca. › Campagna {anno} › Inserisci partecipazione |
| `PartecipazioniImportAnteprimaView` | Contributo Fo.Ca. › Campagna {anno} › Carica da xlsx/CSV |
| `ImportazionePartecipazioniDettaglioView` | Contributo Fo.Ca. › Campagna {anno} › Registro importazioni |
| `BonificiGeneraView` | Contributo Fo.Ca. › Campagna {anno} › Genera bonifici |
| `CampagnaLiquidaView` | Contributo Fo.Ca. › Campagna {anno} › Liquida campagna |
| `PartecipazioneRespingiView` | Contributo Fo.Ca. › Campagna {anno} › Respingi partecipazione |
| `AllegatoPartecipazioneCaricaView` | Contributo Fo.Ca. › Campagna {anno} › Carica allegato |

`breadcrumb_extra()` legge `campagna_id`/`pk` da `request.resolver_match.kwargs` e
risolve `Campagna.objects.filter(pk=...).first()` per l'etichetta dell'anno (con
fallback al pk grezzo se non trovata, stesso schema difensivo di
`GruppoGestioneView.breadcrumb_extra`). Per le view annidate sotto una
partecipazione (`PartecipazioneRespingiView`, `AllegatoPartecipazioneCaricaView`)
serve risalire da `partecipazione_id` a `partecipazione.campagna` per l'anno.

Nessun test dedicato al breadcrumb esiste altrove nel repo (verificato con `rg
breadcrumb apps/*/tests`): non introdurne uno nuovo solo per questo modulo
romperebbe la coerenza — una verifica manuale a schermo (come già fatto per F6d)
resta sufficiente, coerente con la prassi già in uso.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- `apps/contributi/views.py`: `BreadcrumbExtraMixin` aggiunto a tutte le 10 view
  della tabella sopra, ciascuna con il proprio `breadcrumb_extra()` classmethod.
  Nuova funzione privata `_etichetta_campagna(pk)` (stesso schema difensivo di
  `GruppoGestioneView.breadcrumb_extra`: fallback al pk grezzo se la campagna
  non viene trovata), riusata dalle 7 view che hanno una campagna in kwargs —
  evita di duplicare la stessa query 7 volte.
- `ImportazionePartecipazioniDettaglioView` risolve `campagna_id` da
  `ImportazionePartecipazioni.objects.filter(pk=pk)` (l'unica delle 10 che non
  ha `campagna_id`/`pk`-campagna direttamente nei kwargs).
- `CampagnaCreaView` non risolve alcuna campagna (non ancora creata): solo
  "Contributo Fo.Ca. › Nuova campagna", come da tabella.
- Nessun test nuovo (coerente con l'assenza di test dedicati al breadcrumb nel
  resto del repo, verificato sopra). `mise run lint` pulito (ruff+black+mypy),
  `mise run test` verde (1078 passati, nessuna regressione; i 3 fallimenti
  osservati alla prima esecuzione erano solo il DB di sviluppo non avviato —
  risolti con `mise run db-up`, non collegati a questa modifica).
- Verificato da Andrea, commit `9458232` — in attesa di merge su `main` e deploy.

---

## #14 — Tasto da nascondere senza permessi (Impostazioni/Nuova campagna)

**Origine reale (verificata):** `templates/contributi/campagna_lista.html:8-9`
mostra sempre i pulsanti "Impostazioni" (→ `core:impostazioni`) e "Nuova campagna"
(→ `contributi:campagna_crea`), senza alcun controllo di permesso — stesso tipo di
problema già risolto per issue #2 (chiusa, DONE: a579d82), ma lì il giro di
verifica sistematico si era fermato ai pulsanti di `campagna_dettaglio.html`,
lasciando fuori `campagna_lista.html`.

`CampagnaListaView` è protetta da `RuoloRequiredMixin` con
`ruoli_ammessi = RUOLI_GESTIONE_PARTECIPAZIONI` (`apps/contributi/views.py:83`), un
perimetro **più ampio** di quanto serva per i due pulsanti:
- "Nuova campagna" porta a `CampagnaCreaView`, che richiede
  `RUOLI_GESTIONE_CAMPAGNA` con `ruoli_ammessi_solo_diretti = True`
  (`apps/contributi/views.py:92-93`) — SEGRETERIA/ADMIN/RDZ, **esclusi i delegati**
  (D-11).
- "Impostazioni" porta a `core:impostazioni`, che richiede
  `RUOLI_GESTIONE_IMPOSTAZIONI` con `ruoli_ammessi_solo_diretti = True`
  (`apps/core/views.py:23,40-41`) — stesso insieme di ruoli
  (`{ADMIN, SEGRETERIA, RDZ}`), stessa esclusione dei delegati.

Un utente con solo ruolo di gestione-partecipazioni (es. CG, che accede
legittimamente alla lista campagne) vede quindi due pulsanti che portano
entrambi a un 403 già gestito correttamente lato view (nessun buco di sicurezza,
solo UX).

- **Impatto utente**: medio — stesso tipo di confusione già descritto per #2.
- **Impatto sul codice esistente**: molto basso. Nessun nuovo service layer:
  `apps/core/menu.py` calcola già la stessa condizione per la voce di menu
  "Impostazioni" (`consentito(RUOLI_GESTIONE_IMPOSTAZIONI, solo_diretti=True)`,
  `apps/core/menu.py:148`) — va solo esposta al contesto di `CampagnaListaView`,
  non reinventata.
- **Complessità**: bassa.

**Soluzione proposta:** in `CampagnaListaView.get_context_data()` (da introdurre,
oggi la view usa solo `get_queryset()` implicito di `ListView`), calcolare due
booleani con `ruoli_effettivi(request.user)` filtrati `not r.is_delega`:
`puo_gestire_campagna` (`RUOLI_GESTIONE_CAMPAGNA`, già esiste come funzione
non-raising in `apps/contributi/campagne.py:54` — **attenzione**: quella funzione
non esclude i delegati, mentre `CampagnaCreaView` sì; serve quindi il controllo
esplicito `solo_diretti`, non riusare `puo_gestire_campagna()` così com'è, o
riesporrebbe il pulsante a un delegato che poi otterrebbe comunque 403) e
`puo_gestire_impostazioni` (stesso controllo su `RUOLI_GESTIONE_IMPOSTAZIONI`).
Condizionare i due `<a>` nel template con questi flag.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- `CampagnaListaView.get_context_data()` (`apps/contributi/views.py`): calcola
  `tipi_diretti = {r.tipo for r in ruoli_effettivi(request.user) if not
  r.is_delega}`, poi `puo_gestire_campagna`/`puo_gestire_impostazioni` per
  intersezione con `RUOLI_GESTIONE_CAMPAGNA`/`RUOLI_GESTIONE_IMPOSTAZIONI` —
  esattamente il controllo "solo diretti" proposto, non la versione non-raising
  esistente che non esclude i delegati.
- Template (`campagna_lista.html`): i due `<a>` "Impostazioni"/"Nuova campagna"
  condizionati dai due flag.
- Test in `apps/contributi/tests/test_views_campagna_lista.py`
  (`TestPulsantiCampagnaLista`): CG non vede nessuno dei due pulsanti,
  SEGRETERIA li vede entrambi.
- `mise run lint` pulito, `mise run test` verde (vedi riepilogo cumulativo a
  fondo pagina per #13-#18).

---

## #15 — Visibilità ultime campagne Contributo Fo.Ca.

**Origine reale (verificata):** `templates/contributi/campagna_lista.html` mostra
solo una tabella (tutte le campagne appiattite, nessuna gerarchia visiva).
`Campagna.Meta.ordering = ["-anno"]` (`apps/contributi/models.py:57`), quindi
`Campagna.objects.all()` (già usato da `CampagnaListaView.get_queryset()`) ha già
l'ultima campagna come primo elemento — non serve una query aggiuntiva.

- **Impatto utente**: medio — è la pagina di ingresso al modulo più usato, l'ultima
  campagna (quella su cui c'è lavoro attivo) si perde nella tabella tra le
  precedenti.
- **Impatto sul codice esistente**: basso. Solo template + un valore di contesto
  in più, nessun cambiamento alla query esistente né al service layer.
- **Complessità**: bassa.

**Soluzione proposta:** `CampagnaListaView` passa anche `ultima_campagna =
campagne.first() if campagne else None` al contesto. Nel template, un blocco
jumbotron (`bg-ag-viola`/utility del tema, non CSS custom — vincolo di CLAUDE.md)
sopra la tabella esistente con anno, stato, e un pulsante call-to-action verso
`contributi:campagna_dettaglio` dell'ultima campagna. La issue chiarisce
esplicitamente che l'ultima campagna **resta anche in tabella** (nessuna
esclusione, la duplicazione visiva è accettata): la tabella non cambia.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- `CampagnaListaView.get_context_data()`: `ultima_campagna = campagne[0] if
  campagne else None` (stesso `get_context_data` introdotto per #14, unica
  query già ordinata da `Campagna.Meta.ordering`, nessuna query aggiuntiva).
- Template: blocco `bg-ag-viola` sopra la tabella con anno/stato e pulsante
  "Vai alla campagna" verso `campagna_dettaglio`; la tabella sotto resta
  invariata (l'ultima campagna vi compare comunque, come da issue).
  Nessuna nuova voce CSS: solo utility del tema.
- Test in `test_views_campagna_lista.py` (`TestJumbotronUltimaCampagna`):
  ultima campagna è la più recente per anno, resta comunque nel queryset
  `campagne`, `None` quando non ci sono campagne.
- `mise run lint` pulito, `mise run test` verde.

---

## #16 — Errore tabella riepilogo gruppi

**Origine reale (verificata):** `apps/contributi/riepilogo_gruppi.py:50-55`,
`_stato_semaforo()`:

```python
def _stato_semaforo(condizioni: list[bool]) -> StatoSemaforo:
    if all(condizioni):
        return StatoSemaforo.VERDE
    if not any(condizioni):
        return StatoSemaforo.ROSSO
    return StatoSemaforo.GIALLO
```

chiamata con **tre** condizioni (`apps/contributi/riepilogo_gruppi.py:98-100`):
`account_attivato`, `iban_caricato`, `capi_inseriti > 0 or
nessun_rimborso_dichiarato`. Due problemi, entrambi confermati leggendo il codice
contro le 4 regole della issue:

1. **`account_attivato` pesa nel calcolo**, ma la issue è esplicita: "La colonna
   'Account attivato' viene visualizzata, ma non utilizzata nel computo". Oggi
   invece un gruppo con IBAN caricato e capi inseriti ma senza account mai
   attivato risulta GIALLO (parziale) invece di VERDE (completo).
2. **La dichiarazione "nessun rimborso" non prevale su IBAN mancante**: con
   `account_attivato=True` (per isolare l'effetto), `iban_caricato=False`,
   `nessun_rimborso_dichiarato=True` → condizioni `[True, False, True]` → non
   tutte vere, non tutte false → GIALLO. La regola 1 della issue vuole invece
   "Completo" incondizionatamente quando è dichiarato nessun rimborso, IBAN
   incluso — logico: se il gruppo non riceve soldi, l'IBAN è irrilevante.

- **Impatto utente**: medio-alto — è un indicatore di stato mostrato a chi segue
  l'andamento della campagna (probabilmente RdZ/segreteria): uno stato sbagliato
  può far perdere di vista gruppi realmente in ritardo o segnalarne come in
  ritardo gruppi già a posto.
- **Impatto sul codice esistente**: basso. Isolato in una funzione pura già
  testata (verificare `apps/contributi/tests/` per i test esistenti su
  `_stato_semaforo`/`riepilogo_gruppi` prima di modificare, da aggiornare in
  base alle nuove regole).
- **Complessità**: bassa — pura riscrittura della funzione di calcolo, nessuna
  migrazione, nessun cambiamento al modello.

**Soluzione proposta:** riscrivere `_stato_semaforo` seguendo letteralmente le 4
regole della issue, senza più il pattern generico "conta quante condizioni sono
vere":

```python
def _stato_semaforo(*, iban_caricato: bool, capi_inseriti: int, nessun_rimborso_dichiarato: bool) -> StatoSemaforo:
    if nessun_rimborso_dichiarato:
        return StatoSemaforo.VERDE
    capi_ok = capi_inseriti > 0
    if iban_caricato and capi_ok:
        return StatoSemaforo.VERDE
    if not iban_caricato and not capi_ok:
        return StatoSemaforo.ROSSO
    return StatoSemaforo.GIALLO
```

`account_attivato` resta calcolato e passato a `RiepilogoGruppo` (la colonna
continua a essere mostrata, la issue lo chiede esplicitamente), solo non entra
più nella chiamata alla funzione di stato. Aggiornare la chiamata a
`riepilogo_gruppi()` di conseguenza (`apps/contributi/riepilogo_gruppi.py:98-100`)
e i test esistenti sulle 4 combinazioni esplicite della issue.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- `_stato_semaforo()` (`apps/contributi/riepilogo_gruppi.py`) riscritta con
  firma a parole chiave (`iban_caricato`, `capi_inseriti`,
  `nessun_rimborso_dichiarato`), esattamente le regole proposte:
  dichiarazione "nessun rimborso" → VERDE incondizionato; altrimenti IBAN+capi
  entrambi presenti → VERDE; nessuno dei due → ROSSO; solo uno → GIALLO.
  `account_attivato` resta calcolato per `RiepilogoGruppo` (colonna mostrata),
  non più passato alla funzione di stato.
- I 3 test esistenti (`test_stato_rosso_senza_nulla`,
  `test_stato_giallo_parziale`, `test_stato_verde_completo`) restano validi
  invariati (stesso esito con le nuove regole, verificato non a caso ma
  ricalcolando a mano le combinazioni). Aggiunti 2 nuovi test mirati alle due
  regole corrette dal bug: `test_account_non_attivato_non_pesa_sul_semaforo`
  (IBAN+capi bastano per VERDE anche senza account mai attivato) e
  `test_nessun_rimborso_prevale_su_iban_mancante` (dichiarazione vince anche
  con IBAN assente).
- `mise run lint` pulito, `mise run test` verde.

---

## #17 — Colonna descrizione altro per tipologia campo

**Origine reale (verificata):** `apps/contributi/models.py:154`,
`Partecipazione.descrizione_altro` — obbligatorio quando `tipologia.codice ==
"ALTRO"` (validato in `clean()`, `apps/contributi/models.py:215-218`) e raccolto
correttamente all'inserimento (`templates/contributi/partecipazione_inserisci.html:39`,
con toggle JS sul campo). Ma **non è mai mostrato in nessuna vista di lettura**:
verificato con `rg descrizione_altro templates/` che l'unica occorrenza nei
template è quella del form di inserimento — `campagna_dettaglio.html` (la tabella
usata da segreteria/RdZ per valutare le partecipazioni) mostra solo la colonna
"Tipologia" con `{{ p.tipologia }}` (`templates/contributi/campagna_dettaglio.html:108,120`),
mai la descrizione libera.

Chi valuta una partecipazione con tipologia "Altro" non ha quindi modo di sapere
*cosa* sia stato dichiarato, senza uscire dall'interfaccia (es. Django admin) —
esattamente il problema descritto nella issue ("altrimenti non è possibile una
corretta valutazione").

- **Impatto utente**: alto — blocca concretamente una valutazione informata per
  ogni partecipazione con tipologia "Altro", non è solo un difetto estetico.
- **Impatto sul codice esistente**: molto basso — nessuna query nuova
  (`descrizione_altro` è già sul modello e già nella queryset di
  `CampagnaDettaglioView`, che seleziona l'intera `Partecipazione`), solo
  template.
- **Complessità**: molto bassa.

**Soluzione proposta:** in `templates/contributi/campagna_dettaglio.html`, cella
"Tipologia" (riga 120), mostrare la descrizione quando presente:

```html
<td>
  {{ p.tipologia }}
  {% if p.descrizione_altro %}<br><small class="text-muted">{{ p.descrizione_altro }}</small>{% endif %}
</td>
```

Verificare se lo stesso problema si ripete nelle altre viste che elencano
partecipazioni con tipologia (es. export/riepilogo, se esistenti) prima di
considerarla chiusa — stessa cautela già applicata a #2 per non dover riaprire la
issue con un secondo giro.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- `campagna_dettaglio.html`, cella "Tipologia": mostra `descrizione_altro`
  quando presente, esattamente come proposto.
- Verificato con `rg "\.tipologia }}" templates/` che `campagna_dettaglio.html`
  è l'**unica** vista che elenca la tipologia per partecipazione (nessun'altra
  vista/export da toccare, incluso il PDF riepilogo che è aggregato, non per
  singola partecipazione).
- Test in `apps/contributi/tests/test_views_campagna_dettaglio_display.py`
  (`TestDescrizioneAltroVisibile`): descrizione mostrata quando presente,
  nessuna riga extra quando assente.
- `mise run lint` pulito, `mise run test` verde.

## #18 — Possibilità di riaprire campagna in valutazione

**Origine reale (verificata):** la issue ha due parti distinte, entrambe
confermate nel codice.

**Parte 1 — nessuna transizione all'indietro.** Le transizioni FSM di
`Campagna` (`apps/contributi/models.py:84-99`) sono solo in avanti: `APERTA →
IN_VALUTAZIONE` (`avvia_valutazione`), `IN_VALUTAZIONE → CHIUSA` (`chiudi`),
`CHIUSA → LIQUIDATA` (`liquida`). Non esiste alcuna transizione
`IN_VALUTAZIONE → APERTA`: una volta avviata la valutazione, l'unico modo per
inserire ulteriori partecipazioni sarebbe creare una nuova campagna, perdendo il
contesto di quella in corso.

Le valutazioni già fatte (`Partecipazione.stato` in `APPROVATA`/`RESPINTA`, con
`valutata_da`/`data_valutazione`/`motivazione_respingimento` già valorizzati) **non
sono a rischio per costruzione**: sono sullo stato della singola partecipazione,
non della campagna, e nessuna transizione esistente le tocca. L'unico stato
collaterale della campagna da ripulire alla riapertura sono le simulazioni
(`ContributoPartecipazione.is_simulazione=True`, scritte da "Simula calcolo",
`apps/contributi/simulazione.py`): diventerebbero stale se, dopo la riapertura,
si inseriscono nuove partecipazioni o si valuta diversamente, e verrebbero
comunque mostrate nella tabella (`campagna_dettaglio.html:135-138`, tag
"(simulato)"). Lo stesso pattern di pulizia esiste già sia in `chiudi_campagna`
sia in `simula_calcolo` (`ContributoPartecipazione.objects.filter(...,
is_simulazione=True).delete()` prima di scrivere il nuovo risultato): va
riapplicato qui per coerenza, non inventato da zero.

**Parte 2 — motivo del respingimento mai mostrato.**
`Partecipazione.motivazione_respingimento` (`apps/contributi/models.py:163`) è
obbligatorio ad ogni respingimento (validato in `clean()`, righe 197-202 — D-24:
"un respingimento senza causale non è possibile, in nessun percorso") ma non
compare in nessun template: verificato con `rg motivazione_respingimento
templates/` — zero risultati. Chi guarda la tabella delle partecipazioni durante
la valutazione (`campagna_dettaglio.html`, colonna "Valutazione" visibile solo a
`campagna.stato == "IN_VALUTAZIONE"`) non vede perché una riga è stata respinta
senza uscire dall'interfaccia — stesso tipo di gap già pianificato per #17 sulla
colonna "Tipologia", stesso file.

- **Impatto utente**: alto — senza la riapertura, un errore scoperto durante la
  valutazione (partecipazione dimenticata, dato da correggere) costringe a
  ricreare la campagna da capo; senza il motivo visibile, chi rivede le
  valutazioni non ha modo di capire un respingimento senza uscire
  dall'interfaccia.
- **Impatto sul codice esistente**: medio per la parte 1 (nuova transizione FSM
  + service layer + vista + pulsante, migrazione per il nuovo stato nella
  `choices` non serve perché `IN_VALUTAZIONE`/`APERTA` esistono già), molto
  basso per la parte 2 (solo template, stesso schema di #17).
- **Complessità**: media — la parte FSM richiede di ragionare sugli effetti
  collaterali (simulazioni stale), non è solo un `@transition` vuoto.

**Soluzione proposta (parte 1):**

Nuova transizione in `apps/contributi/models.py`:

```python
@transition(field=stato, source=StatoCampagna.IN_VALUTAZIONE, target=StatoCampagna.APERTA)
def riapri(self) -> None:
    """Corpo intenzionalmente vuoto: la pulizia delle simulazioni stale vive
    nel service layer (apps/contributi/campagne.py::riapri_campagna), non qui
    — stesso schema delle altre transizioni di Campagna."""
```

Nuova funzione in `apps/contributi/campagne.py`, accanto a `chiudi_campagna`
(stessa firma/pattern, **senza** `@vieta_in_impersonificazione` — non è
un'operazione economicamente sensibile come chiudere/liquidare, ma valutare se
Andrea la vuole comunque per coerenza con le altre azioni di gestione campagna):

```python
@transaction.atomic
def riapri_campagna(*, utente: Utente, campagna: Campagna) -> Campagna:
    verifica_ruolo_gestione_campagna(utente)
    if campagna.stato != StatoCampagna.IN_VALUTAZIONE:
        raise ValidationError("La campagna non è IN_VALUTAZIONE: impossibile riaprirla.")

    ContributoPartecipazione.objects.filter(
        partecipazione__campagna=campagna, is_simulazione=True
    ).delete()
    campagna.riapri()
    campagna.full_clean(exclude=["stato"])
    campagna.save()
    return campagna
```

Nessun tocco a `Partecipazione`: le valutazioni restano esattamente come sono,
per costruzione (nessuna transizione le referenzia). `avvia_valutazione()`
(`apps/contributi/campagne.py:90-114`) è già sicura da richiamare una seconda
volta dopo una riapertura: auto-approva solo le partecipazioni ancora
`INSERITA` con tipologia ad approvazione automatica, non tocca quelle già
`APPROVATA`/`RESPINTA`.

Nuova view `CampagnaRiapriView` (stesso schema minimale di
`CampagnaAvviaValutazioneView`/`CampagnaChiudiView`, solo POST + redirect), nuovo
pulsante in `campagna_dettaglio.html` nel blocco `IN_VALUTAZIONE` (accanto a
"Simula calcolo"/"Chiudi campagna", dietro lo stesso `puo_gestire_campagna`).
Da chiedere ad Andrea se serve una conferma esplicita (modale/pagina intermedia,
come "Liquida campagna") o basta il pulsante diretto come "Avvia
valutazione"/"Simula calcolo" — la issue non lo specifica, e l'azione, pur non
distruttiva sui dati, riapre un flusso che l'utente potrebbe considerare
"chiuso".

**Soluzione proposta (parte 2):** in `campagna_dettaglio.html`, riga della
tabella partecipazioni, colonna "Stato" (o "Valutazione"), mostrare la
motivazione quando `p.stato == "RESPINTA"`:

```html
<td>
  {{ p.get_stato_display }}
  {% if p.stato == "RESPINTA" and p.motivazione_respingimento %}
    <br><small class="text-muted">{{ p.motivazione_respingimento }}</small>
  {% endif %}
</td>
```

Da valutare insieme a #17 (stessa tabella, stesso giro di modifica al
template) per non toccare `campagna_dettaglio.html` due volte in due commit
separati.

**Implementazione (DONE: 9458232, verificato da Andrea):**
- **Parte 1**: nuova transizione `Campagna.riapri()` (`apps/contributi/models.py`,
  `@transition(source=IN_VALUTAZIONE, target=APERTA)`, corpo vuoto come le
  altre). Nuova `riapri_campagna()` (`apps/contributi/campagne.py`, accanto a
  `chiudi_campagna`): verifica ruolo con `verifica_ruolo_gestione_campagna`
  (non esclude i delegati, come `chiudi`/`simula`, a differenza di
  `apri_campagna`), richiede stato `IN_VALUTAZIONE`, ripulisce le simulazioni
  stale (`ContributoPartecipazione.objects.filter(is_simulazione=True).delete()`,
  stesso pattern di `chiudi_campagna`/`simula_calcolo`), poi `campagna.riapri()`
  + `full_clean(exclude=["stato"])` + `save()`. **Nessun**
  `@vieta_in_impersonificazione`, come proposto (non è un'operazione
  economicamente sensibile). Nessuna migrazione (il campo `stato` non cambia,
  verificato con `manage.py makemigrations --check --dry-run`).
- Nuova `CampagnaRiapriView` (`apps/contributi/views.py`, POST-only, stesso
  schema minimale di `CampagnaChiudiView`), URL
  `campagne/<int:pk>/riapri/` → `contributi:campagna_riapri`. Nuovo pulsante
  "Riapri campagna" in `campagna_dettaglio.html`, nel blocco
  `IN_VALUTAZIONE` dietro `puo_gestire_campagna`, accanto a "Chiudi campagna"
  — **deviazione dichiarata**: nessuna conferma intermedia (modale/pagina),
  stesso pattern diretto di "Avvia valutazione"/"Simula calcolo", non quello di
  "Liquida campagna" (che ha una pagina di conferma con form). La issue non
  specificava quale dei due schemi, scelto quello più semplice essendo
  un'azione reversibile e non distruttiva sui dati.
- **Parte 2**: cella "Stato" in `campagna_dettaglio.html` mostra
  `motivazione_respingimento` quando `p.stato == "RESPINTA"`, stessa modifica
  (via #17) alla stessa tabella.
- Test: `apps/contributi/tests/test_transizioni_campagna.py`
  (`TestRiapriCampagna`): richiede ruolo, richiede stato `IN_VALUTAZIONE`,
  riapre e ripulisce le simulazioni stale, le valutazioni già fatte
  (`Partecipazione.stato`) non vengono toccate.
  `apps/contributi/tests/test_views_campagna_dettaglio_permessi.py`: CG non
  vede il pulsante "Riapri campagna" (esteso il test esistente su
  simula/chiudi), CG forza l'URL e riceve comunque 403, SEGRETERIA riapre con
  successo (302 + stato `APERTA`).
  `apps/contributi/tests/test_views_campagna_dettaglio_display.py`
  (`TestMotivazioneRespingimentoVisibile`): motivazione mostrata per una
  partecipazione respinta.
- `mise run lint` pulito, `mise run test` verde: 1094 test totali passati
  (partendo da 1078 prima di #13, +16 nuovi test fra #16/#18/nuovi file di
  test per #14/#15/#17), nessuna regressione, nessun fallimento residuo oltre
  a WeasyPrint su macOS locale (risolto con `DYLD_LIBRARY_PATH`, pre-esistente
  e non collegato a queste modifiche).
- Verificato da Andrea, incluso lo schema "pulsante diretto senza conferma"
  per la parte 1 (deviazione dichiarata sopra). Commit `9458232` — in attesa
  di merge su `main` e deploy.
