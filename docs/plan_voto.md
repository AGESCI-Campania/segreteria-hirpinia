# Piano — Voto elettronico per le elezioni (branch `app-voto`)

Bozza del 10/11/2026, rivista con Andrea. **Fasi V0–V6 implementate il 10/11/2026**: la
decisione consolidata è D-71 in `docs/Catello_Progettazione.md`, i vincoli per il codice
sono in `CLAUDE.md` (§ Voto elettronico).

## Stato dell'implementazione e scostamenti dal piano

| Punto del piano | Come è stato fatto | Perché |
| --- | --- | --- |
| Polling della pagina di voto a 5 s | 3 s, stato in cache per seduta 2 s | `CLAUDE.md` fissa il polling a 3 s (D-17); il carico è stato provato a 3 s |
| Tagliando con `apps/core/pdf.py` | Stampa dal browser della pagina «Rigenera e mostra» | Il codice si vede una volta sola: un PDF chiesto con una seconda richiesta richiederebbe di conservarlo |
| Limite ai tentativi per seduta e per postazione/sessione | Solo per sessione e per postazione | Un blocco per seduta permetterebbe a chiunque in sala di bloccare l'urna a tutti; a 50 bit la forza bruta online resta irrealistica |
| Link monouso del seggio | Segreto nel fragment (`/voto/seggio/#s=…`) | Nel percorso finirebbe nei log del reverse proxy |
| Interpretazione dei nomi scritti | Per testo (lo stesso testo vale per tutte le schede), in `InterpretazioneNome` | Coerenza fra schede uguali; nessun legame con la singola scheda |
| Ballottaggio in app | Senza nomi scritti | Si sceglie fra i due candidati proposti (art. 18 c.3) |
| Prova di carico su un ambiente di prova | Eseguita in locale (Mac di sviluppo); `GUNICORN_THREADS` aggiunto all'entrypoint (default 1, invariato) | Con 3 worker sync il p95 è al limite; con 4 thread rientra. Va ripetuta sul server |

Restano da fare (fuori dal codice): verifica di HTTPS su `segreteriahirpinia`, prova di
carico sul server, assemblea simulata.

## Contesto

Oggi le elezioni a scrutinio segreto passano dall'app del Nazionale, alimentata dal
tracciato .xlsx (D-70). Catello deve avere un proprio voto online per le **elezioni di
persone e i relativi ballottaggi**; delibere e mozioni restano per alzata di mano.

Requisiti:
- niente app da installare e niente account;
- voto anonimo, sicuro, non manipolabile e verificabile da chi vota;
- accessibile da qualsiasi dispositivo;
- circa 200 votanti contemporanei;
- è pubblico chi ha votato, non cosa ha votato.

Decisioni prese (10/11/2026):
- l'app **sostituisce** quella del Nazionale: vota in app qualsiasi presente con un codice,
  la carta resta possibile per singolo votante, il tracciato resta esportabile ma non serve più;
- verificabilità con **ricevuta + bacheca pubblica** a votazione chiusa;
- dispositivi: **personali + seggi** se il carico lo regge, altrimenti **solo seggi** →
  interruttore per assemblea e prova di carico prima di decidere;
- obiettivo: **assemblea primaverile** (il 22/11/2026 si usa ancora l'app del Nazionale).

Decisioni prese (10/11/2026, seconda parte):
- il **sistema di voto** si sceglie per assemblea, alla creazione: «app nazionale» (flusso
  di oggi: tracciato, risultati copiati a mano, carta per chi ha problemi, nulla cambia) o
  «voto Catello». Si può cambiare **fino all'apertura della prima votazione** dell'assemblea (confermato);
  se si passa a «app nazionale» dopo l'invio dei codici, i codici vengono revocati;
- **codice di 10 caratteri**, pensato per essere copiato a mano: la stampante al banco non
  è necessaria, ma se c'è si usa (tagliando facoltativo);
- **email sull'avente diritto** (`AventeDiritto.email`), precompilata dall'anagrafica,
  inseribile a mano anche al banco durante la registrazione della presenza;
- **export/import Excel delle email per gruppo**, da far verificare ai capigruppo in fase
  di preparazione. L'import lo fanno i gestori dell'assemblea e, **dalla prossima
  autunnale**, anche il capogruppo per il proprio gruppo (non per il 22/11: non c'è tempo).

Regolamento (verificato sul PDF):
- art. 9 c.1: ammette «strumenti telematici»;
- art. 14 c.3: scrutinio segreto per le deliberazioni che riguardano persone;
- art. 18: soglie, già implementate in `apps/assemblee/votazioni.py`.

Il regolamento **non dice** quante preferenze si esprimono in un'elezione con N posti
(vedi Domande aperte).

Contesto tecnico verificato:
- Django 6.1.3;
- gunicorn sync con `GUNICORN_WORKERS` di default a 3 (`docker/entrypoint.sh`);
- cache su DB in produzione, locmem in sviluppo e test;
- polling a 3 s già usato dal cruscotto (D-17).

Prerequisito: la migrazione ai mailers di Django 6.1 (fase F0, separata da questo piano),
perché il voto invia i codici via email.

---

## Architettura

Nuova app **`apps/voto`**, separata da `apps/assemblee`: è l'unica superficie pubblica
senza login e va isolata (URL `/voto/…`, template minimali senza sidebar). Usa `Seduta`,
`Votazione`, `Candidato`, `AventeDiritto` e `DelegaAE`. **Non** scrive mai `Capo`,
`CensimentoCapo` o `IncaricoUnita` (D-70).

### Modello dati

| Modello | Campi chiave | Note |
| --- | --- | --- |
| `CodiceVoto` | `seduta`, `avente` FK, `hash` (HMAC-SHA256 con chiave derivata da `SECRET_KEY`), `emesso_il`, `emesso_da`, `revocato_il` | Uno attivo per avente e seduta, **solo hash** (come l'OTP di D-20). Rigenerarlo revoca il precedente |
| `Votante` | `votazione`, `avente` FK, `tramite` FK null (il delegato) | «Chi ha votato». Unique `(votazione, avente)`. **Nessun timestamp** |
| `Scheda` | `id` UUID4, `votazione`, `ricevuta` (casuale, unique), `scelte` (JSON: id candidati, nomi liberi, oppure `BIANCA` / `NULLA`), `interpretazione` (JSON, null finché non c'è un nome libero da interpretare) | **Nessuna FK** ad avente, codice o votante; **nessun timestamp** |
| `Postazione` | `seduta`, `nome`, `token_hash`, `attiva` | Seggio: tablet/PC della Zona |
| campi su `Votazione` | `in_app` bool, `aperta_in_app_il`, `chiusa_in_app_il`, `hash_bacheca` | Apertura e chiusura dell'urna elettronica |
| campi su `Assemblea` | `sistema_voto`: `NAZIONALE` / `CATELLO`; `modalita_voto`: `PERSONALE_E_SEGGIO` / `SOLO_SEGGIO` | `sistema_voto` si sceglie alla creazione e si può cambiare fino all'inizio delle operazioni di voto; con `NAZIONALE` tutto resta come oggi (D-70). `modalita_voto` esiste solo con `CATELLO` ed è modificabile anche il giorno stesso |
| campo su `AventeDiritto` | `email` (facoltativo) | Precompilato da `capo.email` all'import dell'elenco, compilabile a mano (inserimento, banco, import Excel). All'invio vale questo, non quello dell'anagrafica. Non scrive mai `Capo` (D-70) |

### Flussi

1. **Emissione del codice** (`apps/voto/codici.py`).
   - Quando `registra_presenza()` (`apps/assemblee/sedute.py`) registra un avente che vota
     in app, il service genera un codice di 10 caratteri (alfabeto senza caratteri ambigui:
     niente 0/O, 1/I/L; circa 50 bit), ne salva solo l'hash e lo invia con
     `invia_email_template()` (nuovo `TemplateEmail` «codice di voto») all'indirizzo di
     `AventeDiritto.email`.
   - Il codice si mostra a gruppi (`K7QM-R4XP-2W`) per essere copiato a mano; la pagina di
     voto lo accetta anche senza trattini e in minuscolo.
   - Se l'avente non ha email, l'operatore la inserisce durante la registrazione della
     presenza e il codice parte subito.
   - Il link è `/voto/#c=CODICE`: il codice sta nel *fragment*, quindi non finisce nei log
     del server.
   - Chi non ha proprio un'email o non l'ha ricevuta chiede al banco, dove un operatore fa
     **«Rigenera e mostra»**: il codice precedente viene revocato e il nuovo si vede **una
     volta sola sullo schermo del banco**, in chiaro e come QR (da copiare o inquadrare con
     il telefono). Se al banco c'è una stampante, dalla stessa schermata si può stampare
     anche il tagliando (`apps/core/pdf.py`); senza stampante il flusso funziona lo stesso.
     Il codice in chiaro non si può rileggere: esiste solo l'hash.

2. **Votare** (`apps/voto/urna.py::vota()`, unico punto, in `transaction.atomic` con
   `select_for_update` sul codice). Il codice viene accettato solo se:
   - è attivo e appartiene alla seduta;
   - la votazione è aperta in app;
   - l'avente è fra i **presenti dell'ultimo appello valido** (logica già in
     `apps/assemblee/quorum.py`: va riusata, non riscritta);
   - l'avente non è passato a carta;
   - non esiste già un `Votante` per quella votazione.

   **Deleghe**: se il votante ha una delega registrata nella seduta (`DelegaAE`) e il
   delegante vota in app, lo stesso codice vale per **due schede**: due `Votante` (il
   secondo con `tramite`) e due `Scheda`. L'art. 5 ammette al massimo una delega, quindi al
   massimo due schede.

   Dopo l'invio compaiono la ricevuta (o le due ricevute) e il riepilogo delle scelte.

3. **Seggio**.
   - Un operatore apre su un tablet un link monouso che registra la `Postazione` (token in
     un cookie firmato).
   - La pagina funziona da chiosco: inserimento del codice, voto, ricevuta mostrata per
     30 s, poi azzeramento.
   - In `SOLO_SEGGIO` l'urna accetta voti solo dalle postazioni attive.

4. **Chiusura e scrutinio** (`apps/voto/scrutinio.py`).
   - Verifica bloccante: il numero di `Scheda` deve coincidere con il numero di `Votante`.
   - **Rimescolamento**: le schede vengono riscritte in ordine casuale in un'unica
     transazione (vedi Anonimato).
   - Interpretazione dei nomi liberi da parte della commissione elettorale (vedi «Scheda:
     decisioni prese»): il conteggio non parte finché ne resta uno da interpretare.
   - Conteggio, scritto in `Candidato.voti_app` e `RisultatoCanale(APP)` (bianche e nulle)
     al posto dell'inserimento manuale. Esito e soglie restano in `votazioni.py::esito()`.
   - Pubblicazione della **bacheca** `/voto/bacheca/<votazione>/` (ricevuta → scelte), con
     lo SHA-256 dell'elenco ordinato riportato nel verbale.
   - Durante la votazione operatori e gestori vedono solo il numero dei votanti, mai
     risultati parziali.

5. **Verifica personale**: `/voto/verifica/` con la ricevuta. Prima della chiusura dice
   «scheda nell'urna», dopo mostra la scheda come appare in bacheca.

6. **Carta e app insieme**.
   - Il passaggio a carta di un avente che ha già votato in app in quella votazione è
     rifiutato.
   - Il passaggio inverso è possibile solo con un codice non ancora usato.
   - Il conteggio cartaceo resta manuale come oggi.

### Anonimato e integrità: cosa garantisce e cosa no (da dichiarare in D-71)

- **Nessun collegamento** nel modello fra `Scheda` e `Votante`: niente FK, ID casuali,
  niente orari.
- **Correlazione dal database**: i due record nascono nella stessa transazione, quindi
  chi ha accesso da superutente al database potrebbe correlarli dall'ordine fisico o dallo
  `xmin` di Postgres. Il **rimescolamento alla chiusura** cancella questa traccia nel dato
  a regime.
- **Rischio residuo dichiarato**: chi amministra il server *durante* la votazione (WAL,
  codice modificato) può in teoria correlare. L'anonimato verso l'amministratore è
  **organizzativo**, non crittografico: è lo stesso livello di fiducia che si dà a chi
  custodisce l'urna. Non è un sistema end-to-end verificabile (tipo Helios).
- **Bacheca**: garantisce che la scheda registrata è quella espressa (ognuno controlla la
  propria) e che il conteggio è giusto (chiunque può ricontare). Limite accettato: con la
  ricevuta si può dimostrare a terzi il proprio voto.
- **Codice letto da altri**: chi legge la mail di un altro potrebbe votare al suo posto, ma
  solo se quella persona risulta presente. Il titolare se ne accorge («codice già usato») e
  il fatto resta tracciato in `Votante`, ma il voto non si può annullare. Mitigazione: si
  può scegliere di non inviare email e usare solo il banco o il seggio.
- **Log**: le view di voto non registrano codici né ricevute (arrivano in POST o nel
  fragment). Nessun voto, codice o ricevuta passa da auditlog. Restano tracciate apertura,
  chiusura, emissione e revoca dei codici.
- **Forza bruta**: il limite ai tentativi è per seduta e per postazione/sessione, **non per
  IP**, perché in sala 200 telefoni escono dallo stesso NAT.
- **HTTPS obbligatorio**: le configurazioni generate da `configure-prod.sh` non includono
  TLS. È un prerequisito bloccante da verificare su `segreteriahirpinia` prima di
  qualunque prova reale.

### Carico (stima da confermare con la prova)

- **Voto**: circa 3 richieste per votante; anche con 200 voti in 60 s fanno circa 10 req/s,
  nulla per Django con 3 worker.
- **Polling** della pagina di voto («la votazione è aperta?»): è il vero carico. A 5 s, con
  risposta in cache per 2 s, fanno circa 40 req/s di JSON minimi: ampiamente nei limiti.
- **Collo di bottiglia probabile**: la **rete della sala** (Wi-Fi o celle mobili con 200
  telefoni), non il server. È il motivo concreto dell'interruttore `SOLO_SEGGIO`.
- **Prova di carico**: script `scripts/carico_voto.py` (solo stdlib: `urllib` +
  `concurrent.futures`) con **400** votanti simulati, il doppio del previsto, su un ambiente
  di prova.
  - Criteri: p95 sotto 500 ms, nessun errore, schede = votanti.
  - Se fallisce: più worker gunicorn (o `gthread`), oppure `SOLO_SEGGIO`.

---

## Fasi (una alla volta, ognuna verificata e poi stop)

| Fase | Contenuto |
| --- | --- |
| **V0** | Email degli aventi diritto, utile anche con l'app nazionale (le email vanno nel tracciato): campo `AventeDiritto.email` precompilato da `capo.email`; export `.xlsx` per gruppo (nome, cognome, codice socio, email, id dell'avente in colonna nascosta per l'abbinamento), tracciato come l'export anagrafica; import con anteprima e conferma, `transaction.atomic`, idempotente, parsing in funzione pura, report anomalie (email malformata, riga non trovata, riga di un altro gruppo, id manomesso, email diversa dall'anagrafica). Aggiorna solo `email`. Import riservato ai gestori dell'assemblea; quello del capogruppo per il proprio gruppo arriva dalla prossima autunnale |
| **V1** | `apps/voto`: modelli, migrazioni, `sistema_voto` in creazione assemblea, `codici.py` (emissione, rigenera, revoca, hash), aggancio a `registra_presenza` (con inserimento dell'email al banco) e a `DelegaAE`, template email, banco «Rigenera e mostra» con QR a schermo e tagliando stampabile facoltativo (nuova dipendenza `segno`, pura Python, da confermare) |
| **V2** | Urna: pagina pubblica mobile-first (markup Bootstrap 6 del tema), `urna.py::vota()`, scheda con fino a N preferenze, bianca, nulla e nome libero, deleghe a due schede, ricevute, polling |
| **V3** | Apertura e chiusura in app dalla pagina votazione esistente, scrutinio con rimescolamento, interpretazione dei nomi liberi da parte della commissione (bloccante prima del conteggio), scrittura dei risultati app, bacheca, verifica della ricevuta, hash nel verbale (`apps/assemblee/verbale.py`) |
| **V4** | Seggi: `Postazione`, chiosco, `modalita_voto` |
| **V5** | Ballottaggio in app (oggi `canali()` in `votazioni.py` lo forza a solo carta per un limite dell'app nazionale, non del regolamento) |
| **V6** | Prova di carico, security review e documentazione: nuova **D-71** in `docs/Catello_Progettazione.md` (aggiorna D-70), sezione CLAUDE.md «Voto elettronico» con i vincoli non negoziabili, README, TODO. Assemblea simulata prima della primaverile |

### Deviazioni da D-70 da dichiarare

- `vota_in_app` non significa più «ha dati BuonaStrada» ma «vota con il codice»: le
  occorrenze nel codice vanno riviste in V1.
- Il ballottaggio non è più solo cartaceo.
- I risultati app non si inseriscono più a mano.

### Riuso (da non reimplementare)

- `quorum.py`: presenti dell'ultimo appello valido, `meta_piu_uno`;
- `votazioni.py`: `esito()`, `soglia()`, `canali()`, `frase_esito()`;
- `deleghe.py`: deleghe della seduta;
- `permessi.py::puo_operare`;
- `invio_email.py::invia_email_template()`;
- `apps/core/pdf.py` per il tagliando stampabile;
- lo schema di polling di `cruscotto.py` + `static/js/assemblea-cruscotto.js`.

---

## Verifica

- **Test unitari** per ogni service:
  - codice monouso per votazione;
  - delegato con due schede, mai tre;
  - delega revocata → una sola scheda;
  - assente rifiutato, cartaceo rifiutato;
  - votazione chiusa rifiutata;
  - codice rigenerato: il vecchio non vale più;
  - nessun campo di `Scheda` collega all'avente (test sul `_meta` del modello);
  - il rimescolamento cambia ordine e ID;
  - schede ≠ votanti → chiusura bloccata;
  - bacheca e hash deterministici;
  - `SOLO_SEGGIO` rifiuta chi non è in postazione;
  - codice salvato solo come hash.
- **Qualità**: `mise run lint` e `mise run test` verdi; migrazioni applicabili su database
  vuoto ed esistente.
- **Prova end-to-end in sviluppo**: seduta aperta, presenze, email in Mailpit, voto da
  «telefono» e da postazione, delega, chiusura, bacheca, verifica della ricevuta.
- **Prova di carico** con `scripts/carico_voto.py` prima di scegliere la modalità.
- **Assemblea simulata** con alcuni capi prima della primaverile.

## Scheda: decisioni prese (10/11/2026, chiudono le domande di V2)

1. **Preferenze**: in un'elezione con N posti ogni scheda esprime **fino a N** preferenze
   (anche meno). I nomi liberi contano nel limite.
2. **Bianca, nulla e nome libero**: oltre ai candidati la scheda offre «scheda bianca»,
   «annulla la scheda» (contata fra le nulle, come sulla carta) e, per compatibilità con il
   voto cartaceo, un **nome libero** scritto dall'elettore.
   - Alla chiusura, **prima del conteggio definitivo**, la commissione elettorale interpreta
     la volontà dell'elettore: associa ogni nome libero a uno degli aventi diritto al voto,
     oppure lo dichiara nullo. Finché resta un nome libero da interpretare l'esito non si
     calcola (blocco nello scrutinio, non nel template).
   - L'interpretazione è tracciata (chi, quando, nome scritto → avente o nullo) e finisce
     nel verbale.
   - Un nome associato a un avente che non è fra i `Candidato` della votazione viene
     aggiunto come candidato al momento dell'interpretazione, perché il conteggio e
     `esito()` ragionano su `Candidato` (confermato; in V2 va solo verificato il punto
     esatto in `votazioni.py`).
   - **Rischi da dichiarare in D-71**:
     - il testo libero può servire da **segno di riconoscimento** (es. una firma
       concordata), come sulla carta: in bacheca e nel verbale compare **solo**
       l'interpretazione
       della commissione (avente o nullo), non il testo grezzo. Il testo grezzo lo vedono
       solo la commissione, durante lo scrutinio, e chi ha la ricevuta;
     - il testo è dato personale non controllato: lunghezza massima breve, nessun HTML,
       mai in log né in auditlog, come il resto della scheda.
3. **Revoca del mandato** (art. 19): **resta su carta**. In app solo elezioni e
   ballottaggi.

## Fuori scopo, per la prossima autunnale

- **Preautorizzazioni inserite dai capigruppo** in autonomia, entro una scadenza fissata per
  assemblea (per il 22/11/2026 la scadenza era il 12/11). È la fase di **aggiornamento delle
  liste elettorali** quando i dati di BuonaStrada non sono ancora aggiornati: il nome
  viene dalle autorizzazioni di BuonaStrada. Da definire prima di progettarla: cosa può fare il capogruppo (aggiungere,
  togliere, correggere aventi del proprio gruppo), come si traccia, cosa succede alla
  scadenza e come si riconcilia con i dati di BuonaStrada quando arrivano.
- **Import Excel delle email da parte del capogruppo** per il proprio gruppo (V0 lo prepara
  con lo stesso service).
