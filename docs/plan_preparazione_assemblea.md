# Piano — Preparazione dell'assemblea in anticipo

Raccolta dei requisiti (dal 2026-11-11). Si sviluppa tutto insieme alla fine della
raccolta, dopo aver chiarito i dubbi elencati in fondo. Le regole definitive andranno in
D-70/D-71 di `Catello_Progettazione.md`.

## Stato dello sviluppo

- **Passo 1 — fatto (2026-11-11)**: R5, R6, R7, R9, R10 (D6, D13–D22, D26–D29).
- **Passo 2 — fatto (2026-11-11)**: R4 (D7–D12-ter).
- **Passo 3 — fatto (2026-11-11)**: R1/R2 (D3, D4, D6), più colonna sesso/email mancanti
  evidenziati nell'elenco degli aventi diritto (richiesta del 2026-11-11).
- **Passo 4 — fatto (2026-11-11)**: R3 (D1, D2, D4-bis, D4-ter, D5).
- Passo 5: R8 (etichetta Niimbot B1).
- Passo 6: R11 (manuali in PDF).

## Obiettivo

Preparare prima del giorno dell'assemblea tutto ciò che si può, invece di inserirlo
alla seduta.

## Requisiti raccolti

### R1 — Posizioni al voto e candidature

- Per ogni assemblea, l'elenco delle posizioni al voto (elezioni): incarico, numero di
  posti, quanti posti sono maschili e quanti femminili.
- Per ogni posizione, le candidature man mano che arrivano.
- All'apertura dell'elezione in seduta si parte dalla posizione preparata.

*Oggi*: incarico, posti e candidati si indicano solo all'apertura della votazione, in
una seduta costituita (`votazioni.apri_votazione()`); nessun dato sul sesso.

### R2 — Controllo sul sesso dei candidati

- Alcuni incarichi sono solo maschili o solo femminili: controllo sul sesso dei
  candidati **non bloccante** (il sesso non è noto per tutti).

### R3 — Preferenze per sesso nel voto

- Con più posti divisi per sesso (es. due posti vacanti di membro di Comitato, uno
  maschile e uno femminile), l'elettore esprime al più una preferenza maschile e al più
  una femminile; in generale, al più tante preferenze per sesso quanti sono i posti di
  quel sesso.

### R4 — Ufficio di presidenza e comitati, in anticipo

Da indicare già in preparazione, a livello di assemblea:

- **Presidente o presidenti**: al massimo due, e se sono due di sesso diverso.
- **Segretario**.
- **Comitato elettorale** (esiste già, per assemblea: `apps/assemblee/comitato.py`).
- **Comitato mozioni**.

*Oggi*: presidente, segretario, scrutatori e comitato mozioni sono testo libero nel
verbale di ogni seduta (`VerbaleSeduta`), compilati dopo; il comitato elettorale è per
assemblea ed entra nel verbale.

### R5 — Aggiornare i dati dei capi dall'anagrafica

- Una funzione che riallinea i dati dei capi dell'elenco con quelli del resto di Catello
  (anagrafica), soprattutto quelli aggiunti dopo l'import, come il sesso.
- **Non** si sovrascrive l'email impostata direttamente nel modulo Assemblee.
- Il sesso, che oggi l'elenco non ha, si può importare una prima volta già nella
  migrazione che aggiunge il campo, da `Capo.sesso`.

*Oggi*: `AventeDiritto` non ha il sesso; nome, cognome ed email si copiano solo all'import
(e con «aggiorna il gruppo» per i gruppi con nuovi censiti); l'email importata e quella
corretta nel modulo non si distinguono. Nel database di sviluppo `Capo.sesso` è valorizzato
per 187 capi su 189 (solo `M`/`F`); in produzione non verificato.

### R6 — Reimportare un capo eliminato

- Una funzione per riportare nell'elenco, con i dati dell'anagrafica, un capo eliminato
  nell'assemblea.

*Oggi*: esiste già «Ripristina» (`elenco.ripristina()`), visibile spuntando «Mostra anche
gli usciti»: annulla l'eliminazione ma **non** aggiorna i dati. Un capo mai entrato
nell'elenco (non censito all'apertura) si aggiunge solo a mano con «Nuovo capo».

### R7 — Assemblea vuota con capi scelti uno per uno

- Per assemblee e votazioni più ristrette o di prova: creare un'assemblea **senza**
  l'import automatico dei censiti, e poi scegliere i singoli capi da importare
  dall'anagrafica.

*Oggi*: la creazione importa sempre tutti i censiti (`elenco.importa_elenco()`, anno
scelto gruppo per gruppo); dopo si può solo eliminare, o aggiungere a mano con «Nuovo
capo» (dati scritti a mano, non presi dall'anagrafica). Il tipo è solo autunnale o
primaverile, e verbale, quorum e soglie sono quelli dell'Assemblea di Zona.

### R8 — Tagliando del codice di voto per etichettatrice (50×80 mm)

- Oltre alla stampa dal browser, il tagliando del codice («Rigenera e mostra») va
  scaricabile come **immagine o PDF di 50×80 mm**, da stampare con una Niimbot B1.

*Oggi*: `templates/voto/codice_mostra.html` ha solo «Stampa il tagliando»
(`window.print()` della pagina intera, formato del browser). Il codice in chiaro esiste
solo nella risposta di quella POST (`CodiceMostraView`, `never_cache`) e non si rilegge.

*Proposta tecnica*: generare l'etichetta **nella stessa risposta** che mostra il codice,
come file incorporato nella pagina (`data:` URI con link «Scarica»), così il codice non
passa da un'altra richiesta, dall'URL, dalla sessione o dal disco (D-71):
- PNG a 203 dpi (risoluzione della B1, da verificare): 50×80 mm ≈ 400×640 px, in bianco e
  nero puro, con codice a gruppi e QR (Pillow + `segno`, già dipendenze);
- PDF 50×80 mm (WeasyPrint, già usato per gli altri PDF);
- in più `@page { size: 50mm 80mm }` per la stampa diretta dal browser del solo
  tagliando.

### R9 — Assemblea di prova: email solo su Mailpit

- Un'assemblea di prova può essere impostata per **non inviare email reali**: tutto va
  su Mailpit.

*Oggi*: il reindirizzamento su Mailpit è globale (`ImpostazioniPiattaforma.email_su_mailpit`,
letto solo da `apps/core/email/override.py::MailpitOverridableBackend`, mailer `default`
di produzione). Email legate alle assemblee: codice di voto (`apps/voto/codici.py`) e
invito di attivazione degli account del comitato elettorale (`apps/accounts/inviti.py`
via `apps/assemblee/comitato.py`), in futuro anche di presidenza e segretario (D12).

*Proposta tecnica*: `invia_email_template()` riceve dal chiamante l'indicazione «solo
Mailpit» e la mette sul messaggio come contrassegno; `MailpitOverridableBackend` manda i
messaggi contrassegnati sempre all'alias `mailpit`, a prescindere dall'interruttore
globale. La scelta del trasporto resta confinata in `override.py` (eccezione dichiarata
in CLAUDE.md § Email, da estendere): il resto dell'applicazione passa solo
l'indicazione, senza conoscere il provider. In sviluppo e test (dove `override.py` non è
in uso) il contrassegno non cambia nulla: lì il provider non è mai reale per convenzione
(`docs/email/sviluppo-e-test.md`).

### R10 — Email dell'assemblea di prova visibili in Catello

- Nell'assemblea di prova «solo Mailpit» va visibile il collegamento alle email finite su
  Mailpit; Mailpit vale anche per il voto legato a quell'assemblea (codici di voto: già
  in D26).

*Oggi*: l'interfaccia web di Mailpit in produzione è solo su `127.0.0.1:8025` del server,
raggiungibile con un tunnel SSH, mai da internet
(`docs/email/mailpit-override-produzione.md`).

### R11 — Manuali in PDF allegati alla release

- **Manuale di voto** (solo il voto) e **manuale di gestione dell'assemblea**, in PDF,
  allegati alla release.

*Oggi*: `mkdocs.yml` genera da `docs-utente/` la guida dei capigruppo
(`site/pdf/guida-capigruppo.pdf`, plugin `with-pdf`), e
`.github/workflows/release-manuale.yml` la allega a ogni release pubblicata.
*Proposta tecnica*: una configurazione MkDocs per manuale (un PDF per configurazione con
`with-pdf`), stesse dipendenze (`uv sync --group docs`); il workflow li genera tutti e li
allega insieme alla guida dei capigruppo. Modificando il workflow si verificano le
ultime versioni delle action (istruzioni globali).

## Dubbi da chiarire

Tutti risolti il 2026-11-11: le risposte sono in «Decisioni prese» (D1–D25), che
prevalgono sulle proposte scritte nei requisiti.

- R1/R3: con le quote per sesso, gli eletti si calcolano separatamente per sesso? E il
  ballottaggio? Serve il testo del regolamento/Statuto (le soglie si applicano alla
  lettera).
- R3: nomi scritti a mano sulla scheda per posizioni con quota: ammessi? Scheda oltre
  quota dopo l'interpretazione della commissione: nulla per intero o solo le preferenze
  in eccesso?
- R3: candidato con sesso non noto: «indifferente» o sesso obbligatorio prima di aprire
  l'elezione (unico punto bloccante)?
- R1: posizioni con posti in parte vincolati e in parte liberi?
- R3: su carta il vincolo non è verificabile a macchina: solo indicazione su scheda e
  verbale?
- R2: fonte del sesso: `Capo.sesso` (CSV, ritenuto poco affidabile) precompilato e
  modificabile, o solo inserimento manuale?
- R4: presidenza, segretario e comitato mozioni valgono per l'assemblea intera e si
  riportano nel verbale di ogni seduta (1ª, 2ª, 3ª convocazione), restando modificabili
  seduta per seduta? Oppure diventano solo per assemblea?
- R4: persone scelte dall'elenco degli aventi diritto (autocompletamento) o anche testo
  libero (es. presidente esterno all'elenco)?
- R4: con due presidenti, come si scrive nel verbale («la Presidenza, nelle persone
  di…»)? Il modello nazionale prevede un solo campo.
- R4: il comitato mozioni ha sempre tre membri (oggi l'help_text lo dice)? Vincolo o
  solo indicazione?
- R4: gli scrutatori del verbale (oggi due campi) coincidono con il comitato elettorale
  o restano un sottoinsieme da indicare?
- R4: presidenti e segretario devono avere un accesso a Catello (come il comitato
  elettorale), o sono solo nomi per il verbale?
- R5: quali dati si riallineano: nome, cognome, sesso, email (se non corretta nel
  modulo), anche il gruppo? Il gruppo oggi lo gestisce solo «aggiorna il gruppo» e
  conserva i trasferimenti fatti a mano.
- R5: per non toccare l'email corretta nel modulo serve sapere quale è stata corretta:
  da qui in avanti si può tracciare; per l'elenco già esistente, «diversa da quella
  dell'anagrafica» vale come «corretta a mano»?
- R5: il riallineamento è un'operazione esplicita (pulsante, con anteprima e conferma
  come gli altri import) o automatico? Per tutto l'elenco o per capo/gruppo? Anche ad
  assemblea conclusa (no, secondo la regola attuale)?
- R5: i capi inseriti a mano senza codice socio restano esclusi (non c'è un capo a cui
  agganciarli)?
- R6: basta aggiungere a «Ripristina» il riallineamento dei dati, o serve anche
  aggiungere un capo dell'anagrafica mai entrato nell'elenco cercandolo (per esempio
  censito dopo l'apertura, o di un anno diverso)? Con quale perimetro di ricerca?
- R5/R6: sesso dell'elenco modificabile a mano nel modulo (come l'email), senza scrivere
  l'anagrafica?
- R7: la scelta «vuota / tutti i censiti» si fa alla creazione (casella nel modulo)? E
  l'import di tutti si può lanciare anche dopo, su un'assemblea nata vuota?
- R7: perimetro della ricerca dei capi da importare: censiti dell'anno dell'assemblea
  (o del precedente per le autunnali, come l'import), di tutti i gruppi, Comitato
  compreso? Oppure qualsiasi capo dell'anagrafica? Sarebbe un nuovo perimetro di ricerca
  soci, distinto dai tre esistenti (CLAUDE.md § Ricerca soci).
- R7: oltre ai singoli capi, serve importare un gruppo intero in un colpo?
- R7: un'assemblea di prova va distinta da quelle vere (tipo «Prova», o un flag)? Per
  esempio per non comparire fra le assemblee ufficiali, avere verbali con dicitura di
  prova, o poter essere eliminata del tutto (oggi un'assemblea non si cancella
  dall'interfaccia). Per un'assemblea «ristretta» valgono comunque quorum e soglie
  dell'Assemblea di Zona?
- R7/R6: la stessa ricerca può servire a R6 per aggiungere un capo mai entrato
  nell'elenco: un'unica funzione per entrambi?
- R8: formato: immagine PNG, PDF o entrambi? Si stampa dall'app Niimbot sul telefono
  (che importa immagini/PDF) o dal computer con il driver?
- R8: orientamento: 50 mm di larghezza e 80 di altezza (etichetta verticale) o il
  contrario? La B1, se non sbaglio, stampa al massimo 48 mm di larghezza: margini da
  lasciare?
- R8: cosa va sull'etichetta: solo codice e QR, oppure anche nome del capo, assemblea e
  convocazione? Il nome rende il tagliando riconducibile alla persona se perso.
- R8: il QR (link all'urna con il codice nel fragment) va mantenuto anche sull'etichetta?

## Decisioni prese (risposte ai dubbi)

- **D1 (2026-11-11)**: con posti divisi per sesso, **graduatoria separata per sesso**:
  per ogni posto maschile è eletto il maschio più votato sopra soglia, per ogni posto
  femminile la femmina più votata sopra soglia, anche se un candidato dell'altro sesso
  ha più voti. Ballottaggio (posto scoperto o parità sull'ultimo posto) **solo fra
  candidati dello stesso sesso** del posto da coprire.
- **D2 (2026-11-11, corretta)**: nelle elezioni con quote per sesso i **nomi scritti
  restano ammessi**, ma per ogni nome scritto l'elettore **dichiara se è M o F** (per un
  candidato in lista il sesso è già noto). L'urna fa rispettare le quote usando il sesso
  dichiarato, quindi una scheda non può superarle. Se la commissione attribuisce il nome
  a un capo di sesso diverso da quello dichiarato, si annulla **solo quella preferenza**,
  anche se col sesso vero resterebbe entro la quota; il resto della scheda resta valido.
  (Sostituisce la prima versione: «si annullano tutti i nomi scritti di quel sesso».)
- **D3 (2026-11-11)**: in un'elezione con quote per sesso, **ogni candidato in lista deve
  avere il sesso prima dell'apertura**: è l'unico controllo bloccante sul sesso. Nelle
  elezioni senza quote il sesso mancante è solo un avviso.
- **D4 (2026-11-11)**: i posti di una posizione sono **maschili + femminili +
  indifferenti** (es. 4 = 1 M + 1 F + 2 liberi).
- **D4-bis (2026-11-11)**: con posti misti l'elettore dà al massimo tante preferenze
  quanti i posti in tutto, e per ciascun sesso al massimo i posti di quel sesso più gli
  indifferenti (es. 1 M + 1 F + 2 liberi: massimo 4, di cui al massimo 3 M e 3 F).
- **D4-ter (2026-11-11)**: assegnazione degli eletti con posti misti: **prima i posti
  vincolati** (posti M ai maschi più votati sopra soglia, posti F alle femmine più votate
  sopra soglia), poi i posti indifferenti ai più votati sopra soglia fra i rimanenti, di
  qualunque sesso.
- **D5 (2026-11-11)**: su carta le quote sono **indicate** (scheda/istruzioni e verbale);
  allo spoglio gli scrutatori applicano le stesse regole di D2 e inseriscono i voti già
  validati. Catello non genera la scheda cartacea.
- **D6 (2026-11-11)**: il sesso del candidato si prende da `Capo.sesso` attraverso
  l'elenco dell'assemblea (precompilato), **correggibile a mano nel modulo** senza
  scrivere l'anagrafica.
- **D7 (2026-11-11)**: presidenza, segretario e comitato mozioni si indicano **per
  l'assemblea** e precompilano il verbale di ogni convocazione, dove restano modificabili
  seduta per seduta.
- **D8 (2026-11-11)**: in preparazione si scelgono **solo fra gli aventi diritto
  dell'elenco** (autocompletamento). Il controllo «due presidenti di sesso diverso» usa il
  sesso dell'elenco (D6). Nel verbale della seduta i campi restano quelli attuali (testo,
  con suggerimenti dall'elenco), precompilati da qui.
- **D9 (2026-11-11)**: con due presidenti il verbale scrive «nelle persone di X e Y»; con
  uno solo resta la frase attuale.
- **D10 (2026-11-11)**: il comitato mozioni ha **sempre tre membri** (vincolo).
- **D10-bis (2026-11-11)**: in preparazione il comitato mozioni si salva con 0–3 membri,
  mai più di tre; finché non sono tre la pagina lo segnala e nel verbale i mancanti
  compaiono come «[…]».
- **D11 (2026-11-11, corretta)**: gli **scrutatori restano due**, scelti fra i
  componenti del comitato elettorale (non più testo libero). Resta anche la frase sul
  Comitato elettorale con l'elenco completo.
- **D12 (2026-11-11)**: anche presidenti e segretario hanno un **accesso a Catello**, per
  vedere i risultati delle votazioni ed eventualmente compilare il verbale. Come per il
  comitato elettorale l'accesso è facoltativo (account e invito di attivazione), non
  bloccante: possono anche non accedere mai.
- **D12-bis (2026-11-11)**: con l'accesso, presidenti e segretario: vedono risultati,
  cruscotto, presenze e quorum (sola lettura); **compilano il verbale** e ne scaricano il
  PDF; **vedono l'ordine del giorno senza modificarlo**. Non fanno operazioni di voto
  (quelle restano al comitato elettorale e ai gestori).
- **D12-quater (2026-11-11)**: l'ordine del giorno resta immutabile per presidenti e
  segretario (i punti li cambiano i gestori), ma **la discussione dei punti la possono
  scrivere** (è parte del verbale), anche ad assemblea conclusa. La variazione del
  rappresentante legale resta ai gestori; gli scrutatori si indicano anche in
  preparazione; togliere un incarico non cancella l'account (confermati).
- **D12-ter (2026-11-11)**: la casella «Crea l'account e invia l'invito» parte spuntata,
  per presidenza/segretario come per il comitato elettorale.
- **D13 (2026-11-11)**: il riallineamento (R5) aggiorna nome, cognome, sesso (salvo
  correzione nel modulo), email (salvo correzione nel modulo) **e gruppo** (vedi D13-bis).
- **D14 (2026-11-11)**: negli elenchi già esistenti un'email diversa da quella
  dell'anagrafica **vale come corretta a mano** e non si sovrascrive; da ora ogni
  correzione nel modulo si registra esplicitamente.
- **D13-bis (2026-11-11)**: per il gruppo vale la regola di «aggiorna il gruppo»: si
  aggiorna il gruppo del censimento (quello del tracciato); il gruppo attuale cambia solo
  se il capo non era stato trasferito a mano nell'assemblea.
- **D15 (2026-11-11)**: il riallineamento è un **pulsante per tutto l'elenco**, con
  anteprima delle modifiche e conferma esplicita; mai ad assemblea conclusa.
- **D16 (2026-11-11)**: i capi inseriti a mano senza codice socio sono **esclusi** dal
  riallineamento (li unisce eventualmente «aggiorna il gruppo», con conferma degli omonimi).
- **D17 (2026-11-11)**: il sesso dell'elenco è **correggibile a mano** nel modulo, senza
  scrivere l'anagrafica, e il riallineamento non sovrascrive la correzione.
- **D18 (2026-11-11)**: R6 = «Ripristina» riallinea anche i dati dall'anagrafica (regole
  D13–D17) **e** una funzione «Aggiungi dall'anagrafica» per un capo mai entrato
  nell'elenco, la stessa di R7.
- **D19 (2026-11-11)**: alla creazione si sceglie «tutti i censiti» o «vuota»; su
  un'assemblea nata vuota l'import di tutti si può lanciare anche dopo (idempotente).
- **D20 (2026-11-11)**: «Aggiungi dall'anagrafica» cerca fra i **censiti degli anni
  dell'import** (anno dell'assemblea; per le autunnali anche il precedente), tutti i
  gruppi compreso il Comitato, per nome, cognome, gruppo o codice socio; solo gestori.
  È un nuovo perimetro di ricerca, da documentare in CLAUDE.md § Ricerca soci.
- **D21 (2026-11-11)**: si può importare anche un **gruppo intero** (i suoi censiti non
  ancora in elenco).
- **D22 (2026-11-11)**: un'assemblea può essere **«di prova»** (flag alla creazione), ben
  indicata nelle pagine, con la dicitura «DI PROVA» nei PDF, ed è l'**unica eliminabile
  del tutto** dall'interfaccia. Resta nell'elenco delle assemblee insieme alle altre.
- **D22-bis (2026-11-11)**: anche per le assemblee di prova o ristrette quorum e soglie
  sono **quelli del regolamento**, calcolati sui loro aventi diritto.
- **D23 (2026-11-11)**: etichetta in **PNG e PDF**, entrambi scaricabili dalla pagina del
  codice, più la stampa diretta dal browser in formato 50×80 mm.
- **D24 (2026-11-11)**: etichetta **verticale** (50 mm di larghezza × 80 di altezza), con
  contenuto entro 48 mm (margine di 1 mm per lato).
- **D25 (2026-11-11)**: sull'etichetta codice a gruppi, QR (link all'urna con il codice
  nel fragment), assemblea e convocazione, **e nome del capo**.
- **D26 (2026-11-11)**: per le sole assemblee di prova c'è l'opzione **«Email solo su
  Mailpit»**, spuntata alla creazione e modificabile. Vale per tutte le email legate a
  quell'assemblea: codici di voto e inviti di attivazione di comitato elettorale,
  presidenza e segretario.
- **D27 (2026-11-11)**: se l'assemblea è «solo Mailpit» e Mailpit non è configurato (o
  non risponde), **l'email non parte e compare un errore esplicito**: mai un invio reale
  creduto deviato. Alla creazione (e alla modifica dell'opzione) si avvisa se Mailpit non
  è configurato sul server.
- **D28 (2026-11-11)**: niente link all'interfaccia di Mailpit e nessuna esposizione
  nuova: è **Catello a mostrare le email** dell'assemblea di prova, leggendole dall'API di
  Mailpit (rete interna di Compose), in una pagina **solo per i gestori** (ADMIN,
  SEGRETERIA, RdZ): destinatario, oggetto, ora e testo. Si vedono **solo le email di
  quell'assemblea**, riconosciute da un'etichetta che Catello aggiunge all'invio (tag di
  Mailpit, `X-Tags`). Serve una nuova variabile con l'indirizzo dell'API di Mailpit
  (porta web 8025 sulla rete interna) accanto a `EMAIL_MAILPIT_HOST`.
- **D29 (2026-11-11)**: nella pagina, il **codice degli inviti di attivazione è
  oscurato** (gli account sono reali: chi lo vedesse potrebbe attivare l'account di un
  altro); i **codici di voto di prova restano visibili**, servono per provare l'urna.
  Deviazione dichiarata da D-71 («il codice in chiaro esiste solo nel valore restituito da
  `codici.emetti()`»), limitata alle assemblee di prova «solo Mailpit».
  *Conseguenza*: un componente di un'assemblea di prova senza account attivo non riceve
  il codice di attivazione; per farlo entrare si toglie temporaneamente «solo Mailpit» e
  si usa «Invia invito», oppure si usano account già attivi.
- **D30 (2026-11-11)**: **manuale di voto** per elettori **e** seggi: per chi vota (codice
  via email, QR o tagliando; voto da telefono e al seggio; preferenze e quote per sesso;
  nomi scritti con il sesso dichiarato; ricevuta e verifica in bacheca; cosa fare se
  qualcosa non va) più una parte per banco e seggi (attivazione postazioni, «Rigenera e
  mostra», etichetta, passaggio a carta).
- **D31 (2026-11-11)**: **manuale di gestione** per gestori (ADMIN, SEGRETERIA, RdZ),
  comitato elettorale e presidenza/segretario, una sezione per ruolo.
- **D32 (2026-11-11)**: **con schermate**, catturate da un'assemblea di prova con dati
  fittizi (mai dati reali di soci, CLAUDE.md § Dati sensibili), salvate nel repository.
- **D33 (2026-11-11)**: i manuali si scrivono **in fondo**, a funzioni finite (ultimo
  passo del piano), insieme alla modifica del workflow di release.
- **D34 (2026-11-11)**: i manuali (testo e schermate) si **rifanno solo se cambiano le
  pagine che descrivono**. Per ogni manuale un elenco dei template e dei file di codice
  delle pagine descritte; se nessuno è cambiato restano testo e schermate della release
  precedente. Un controllo in CI avvisa quando una pagina descritta cambia senza che il
  relativo manuale sia aggiornato. Le schermate sono obbligatorie (D32).
- **D35 (2026-11-11)**: le schermate le produce uno **script automatico**: crea
  un'assemblea di prova con dati fittizi e cattura le pagine con un browser senza
  interfaccia (Playwright, **solo dipendenza di sviluppo**, mai fra quelle obbligatorie),
  così si rifanno con un comando quando le pagine cambiano. Le immagini stanno nel
  repository accanto ai sorgenti del manuale.
- **D36 (2026-11-11)**: scheda di carta oltre quota: va bene l'indicazione data agli
  scrutatori nella pagina della votazione (per ciascun sesso contano al massimo le
  preferenze ammesse da posti di quel sesso più indifferenti).
- **D37 (2026-11-11)**: un solo ballottaggio per elezione anche con le quote: si propone
  per il primo posto vacante (maschile, poi femminile, poi indifferente) che ha almeno due
  candidati; gli altri posti restano vacanti.
