# Changelog

Tutte le modifiche rilevanti di Catello sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il
progetto aderisce a [Semantic Versioning](https://semver.org/lang/it/).

Le versioni precedenti alla 1.1.16 non sono documentate qui: la cronologia
completa resta disponibile con `git log`.

## [1.11.0] - 2026-11-11

### Aggiunto

- Urne aperte: la pagina della votazione, il cruscotto e il proiettore mostrano,
  aggiornati da soli, quanti hanno votato in app e quanti mancano; pagina della
  votazione e cruscotto anche chi deve ancora votare (il proiettore solo i
  numeri).

### Modificato

- Seggio: la ricevuta torna a restare a schermo 30 secondi; il pulsante di
  chiusura è in evidenza in cima e in fondo alla pagina, anche sul dispositivo
  personale.

## [1.10.1] - 2026-11-11

### Modificato

- Seggio: la ricevuta del voto resta a schermo 10 secondi invece di 30, poi la
  pagina si azzera per il prossimo votante.

## [1.10.0] - 2026-11-11

### Modificato

- Presenze durante le votazioni: chi arriva (o è presente per delega) mentre
  una votazione è aperta vota e si aggiunge ai presenti di quella votazione;
  finché ci sono votazioni aperte non si può annullare una presenza né revocare
  una delega.

## [1.9.0] - 2026-11-11

### Aggiunto

- Votazioni: le elezioni preparate si creano insieme dall'elenco delle
  votazioni e, con il voto in app, se ne aprono subito le urne tutte insieme.

### Modificato

- «Nuova votazione»: il pulsante è «Crea la votazione» e la pagina spiega che
  con il voto in app si vota dopo aver aperto l'urna.

## [1.8.0] - 2026-11-11

### Aggiunto

- Cruscotto come punto centrale della seduta: per chi ne ha il permesso,
  presenze, deleghe, votazioni, seggi, elenco degli aventi diritto, apertura,
  costituzione, chiusura dei lavori e verifica del quorum, senza passare dalla
  pagina della seduta; dopo ogni azione si torna al cruscotto. Il verbale resta
  nella pagina della seduta.

## [1.7.0] - 2026-11-11

### Aggiunto

- Voto in app: più elezioni con l'urna aperta insieme, aperte in un colpo solo
  dall'elenco delle votazioni; chi vota compila tutte le schede nella stessa
  pagina e le conferma una volta sola; le urne si chiudono tutte insieme.
- Cruscotto: «Dichiara validamente costituita» appena il quorum è raggiunto.
- Pagina dell'assemblea ed elenco delle assemblee: collegamento alla seduta
  aperta; dalla seduta e dalle presenze i gestori raggiungono l'elenco degli
  aventi diritto.
- Vista proiettore: logo della Zona e sfondo rosso tenue finché manca il
  quorum, verde tenue quando è raggiunto.

### Modificato

- Presenze: l'AE che ha delegato compare come «Presente per delega» appena il
  delegato è registrato.
- Con la modalità «solo seggi» l'email del codice di voto non contiene il link
  per votare dal telefono.
- Manuali in PDF: icona dei riquadri a sinistra del titolo.

## [1.6.1] - 2026-11-11

### Aggiunto

- Assemblee: titolo facoltativo, scelto alla creazione o alla duplicazione e
  modificabile dalla pagina dell'assemblea.
- Manuali in PDF: manuale di voto in app, manuale di voto al seggio e manuale
  per il banco e i seggi al posto del manuale di voto unico, con il logo della
  Zona in copertina e la palette verde della Zona.

### Corretto

- Autocompletamento di presidenti, segretario, comitato mozioni, scrutatori e
  candidature: la ricerca non restituiva risultati.

## [1.6.0] - 2026-11-11

### Aggiunto

- Voto in app per le elezioni dell'Assemblea di Zona: codice di voto per
  email o al banco, urna da telefono o ai seggi in sala, scrutinio con
  interpretazione dei nomi scritti da parte della commissione elettorale,
  bacheca pubblica con impronta nel verbale e verifica della ricevuta.
- Etichetta 50×80 mm del codice di voto per l'etichettatrice, in PNG e PDF.
- Email degli aventi diritto, con Excel per gruppo da far verificare ai
  capigruppo.
- Preparazione dell'assemblea in anticipo:
  - comitato elettorale scelto fra gli aventi diritto, con account e invito
    di attivazione;
  - presidenti, segretario, comitato mozioni e scrutatori, che precompilano
    il verbale; presidenti e segretario possono vedere i risultati, scrivere
    la discussione dei punti e compilare il verbale;
  - posizioni al voto con posti maschili, femminili e indifferenti, e
    candidature con controllo del sesso;
  - elezioni con quote per sesso nel voto in app, nello scrutinio e nel
    calcolo degli eletti, con ballottaggio fra candidati dello stesso sesso.
- Elenco degli aventi diritto: sesso, sesso ed email mancanti evidenziati,
  riallineamento con l'anagrafica, «Aggiungi dall'anagrafica» per capo o per
  gruppo, selezione di tutti i capi visibili.
- Assemblee con elenco vuoto, assemblee di prova eliminabili con email solo
  su Mailpit, duplicazione di un'assemblea.
- Manuale di voto e manuale di gestione dell'assemblea in PDF, allegati alla
  release.

### Modificato

- Il voto elettronico di Catello si chiama «Voto in app»: votano tutti in
  app, la carta resta per chi ha problemi.
- PDF sulla carta intestata ufficiale della Zona, anche il riepilogo dei
  contributi.
- Email: migrazione alle impostazioni MAILERS di Django 6.1.

## [1.5.0] - 2026-11-10

### Aggiunto

- Assemblee, votazioni e verbali:
  - votazioni con le maggioranze del regolamento dell'Assemblea: deliberazioni
    ed elezioni sui presenti, mozioni d'ordine e nuovi punti all'ordine del
    giorno sui votanti, revoca sugli aventi diritto; voto palese per alzata di
    mano, scrutinio segreto in app e su carta per elezioni e revoca;
  - elezioni per incarico con più posti, ballottaggio fra i due più votati
    (solo su carta) e posti vacanti come da regolamento;
  - maggioranze richieste in tempo reale nel cruscotto e nella vista proiettore;
  - ordine del giorno con i punti tipici del modello nazionale;
  - verbale dell'assemblea in PDF sul modello nazionale, con presidenza,
    numeri del quorum, verifiche, discussione ed esito delle votazioni;
  - verbale di variazione del rappresentante legale (ed eventualmente della
    sede legale) in PDF, con i dati precompilati dall'anagrafica.

### Modificato

- Assemblee: se una verifica non conferma il quorum costitutivo l'Assemblea
  viene dichiarata chiusa; le votazioni precedenti restano valide.

## [1.4.0] - 2026-11-10

### Aggiunto

- Assemblee, il giorno dell'assemblea:
  - apertura della seduta e registrazione delle presenze all'ingresso, anche da
    smartphone, con calcolo del quorum costitutivo; dichiarazione di seduta
    costituita o non costituita e, se serve, seconda e terza convocazione;
  - deleghe degli Assistenti Ecclesiastici con le regole del regolamento
    dell'Assemblea;
  - verifica del quorum durante i lavori con un nuovo appello;
  - cruscotto che si aggiorna da solo con presenti, quorum e votanti in app e su
    carta, vista da proiettare in sala ed elenco dei presenti da abilitare
    nell'app di voto;
  - nel tracciato per l'app di voto, presenza e codice del delegato compilati.

## [1.3.0] - 2026-11-10

### Aggiunto

- Nuovo modulo **Assemblee** (Moduli › Assemblee), per amministratori, segreteria e
  Responsabili di Zona:
  - creazione di un'assemblea autunnale o primaverile con la prima convocazione;
    l'elenco degli aventi diritto si riempie subito dai censiti già in Catello (in
    autunno, per ogni gruppo, i dati dell'anno in corso se già disponibili, altrimenti
    quelli dell'anno precedente);
  - gestione dell'elenco: filtro per gruppo, eliminazione anche di più capi insieme e
    ripristino, trasferimento di gruppo, inserimento dei capi mancanti con provenienza
    (passaggio dal clan, nuovo ingresso, rientro, non nota) ed eventuali incarichi;
  - "Aggiorna gruppo" per allineare un gruppo quando arrivano i suoi dati dell'anno in
    corso, con anteprima delle modifiche;
  - per ogni capo, voto nell'app nazionale o su carta, con la possibilità di passare a
    carta chi era previsto in app e l'elenco di chi va tolto dall'app;
  - tracciato da importare nell'app di voto del Nazionale e foglio presenze in PDF da
    stampare;
  - nomina degli operatori di voto dell'assemblea.

## [1.2.1] - 2026-11-10

### Modificato

- Nel menu laterale le sezioni (Anagrafica, Moduli, Account, Amministrazione) sono
  ora richiudibili e partono chiuse, così il menu occupa meno spazio: si apre da sola
  la sezione della pagina in cui ci si trova, e aprirne un'altra chiude la precedente.
- Con il menu laterale ridotto alle sole icone, sono ora visibili anche le icone delle
  funzioni di Nota Spese.

## [1.2.0] - 2026-11-10

### Modificato

- Nuova veste grafica basata sulla serie 3 del tema AGESCI Campania (Bootstrap 6):
  menu laterale richiudibile, pulsanti, avvisi e moduli aggiornati in tutte le
  pagine. Nel menu laterale le funzioni di un modulo (es. Nota Spese) si aprono
  automaticamente quando si è su una di esse.
- Il piè di pagina mostra ora anche il nome della Zona e dell'associazione.
- Per usare la piattaforma servono browser recenti: Chrome/Edge 130, Firefox 132 o
  Safari 18 (o versioni successive).
- Aggiornati i componenti software della piattaforma.

## [1.1.22] - 2026-09-27

### Corretto

- Nel riepilogo di una campagna Fo.Ca. chiusa/liquidata, il testo non mostra
  più riferimenti alle variabili interne della formula ("(N)", "(B/N)").
- Tutti gli importi delle pagine di campagna Fo.Ca. mostrano ora il simbolo
  €, incluso il campo "Quota versata" durante l'inserimento di una
  partecipazione.

### Aggiunto

- Nel riepilogo di campagna, la "Quota proporzionale per partecipante" è
  ora accompagnata dalla "Quota erogata per partecipante" quando il tetto
  per partecipazione riduce l'importo effettivo.

## [1.1.21] - 2026-09-27

### Modificato

- Rinnovata la veste grafica della piattaforma: nuovo layout con menu
  laterale, intestazione e componenti nativi, più chiaro e coerente su
  desktop e mobile.
- Nell'elenco campagne Fo.Ca., la campagna in evidenza ha ora un riquadro più
  sobrio (bordo colorato) invece del blocco a tinta unita.

### Aggiunto

- In "Nuova nota spese", chi gestisce le note ora può cercare il beneficiario
  digitando nome, cognome o gruppo, invece di dover conoscere a memoria il
  codice socio.

### Corretto

- Le tabelle troppo larghe per lo schermo (su mobile o a bassa risoluzione)
  ora si possono scorrere invece di risultare tagliate.
- Nell'export "Visualizza anagrafica", le colonne Gruppo censimento/Gruppo
  servizio mostrano il nome del gruppo invece del codice.
- Il banner "stai operando per conto di" durante un'impersonificazione è ora
  visibile subito, non solo scorrendo la pagina fino in fondo.

## [1.1.20] - 2026-09-25

### Modificato

- Nel menu "Moduli", "Nota Spese" è ora un'unica voce (prima erano 4 voci
  separate: Note spese, Verifica note spese, Eventi, Esporta note spese),
  con una pagina di accesso dedicata e le singole funzioni raggiungibili da
  lì o come sottovoci della barra laterale. Il percorso mostrato in cima
  alla pagina (breadcrumb) segue la stessa struttura.

## [1.1.19] - 2026-09-24

### Aggiunto

- Nuovo modulo "Nota Spese": i capi possono compilare e inviare note spese
  digitali per il rimborso di spese sostenute per conto del gruppo/zona,
  documentali o chilometriche (calcolo automatico su tariffa e distanza, con
  segnalazione di eventuali doppioni). Le note passano da bozza a verifica e
  approvazione dei gestori, fino alla liquidazione; ogni nota può avere fino a
  10 giustificativi allegati per riga. Notifiche puntuali e promemoria al
  capo, report periodico ai gestori, esportazione PDF della nota e replica
  automatica dei documenti su Google Drive.
- Possibilità di riaprire una campagna Contributo Fo.Ca. già in valutazione,
  per correggere un errore scoperto durante la valutazione senza dover
  ricreare la campagna.
- Breadcrumb di navigazione su tutte le pagine del modulo Contributo Fo.Ca.
- Nell'elenco campagne Fo.Ca., l'ultima campagna è ora messa in evidenza in
  cima alla pagina.
- Nella tabella di valutazione delle partecipazioni Fo.Ca., ora sono visibili
  anche la descrizione libera per la tipologia "Altro" e il motivo di un
  eventuale respingimento.

### Corretto

- I pulsanti "Impostazioni" e "Nuova campagna" nell'elenco campagne Fo.Ca. non
  compaiono più a chi non ha il permesso per usarli.
- Lo stato "semaforo" del riepilogo gruppi per campagna ora segue
  correttamente le regole previste: l'attivazione dell'account non incide più
  sullo stato, e la dichiarazione "nessun rimborso richiesto" da parte di un
  gruppo prevale sempre, anche senza IBAN caricato.

## [1.1.18] - 2026-09-13

### Aggiunto

- Riepilogo gruppi per campagna: una tabella, per Amministratore/Segreteria/
  RdZ e capigruppo, con lo stato di invio del contributo Fo.Ca. di ogni
  gruppo (account attivato, IBAN caricato, capi inseriti, stato complessivo
  con semaforo). Un gruppo senza capi da rimborsare può dichiararlo
  esplicitamente ("nessun rimborso richiesto").
- Pulizia periodica delle sessioni scadute in produzione: le sessioni ormai
  inutilizzabili non restavano più visibili a tempo indeterminato
  nell'elenco "Sessioni utente".

## [1.1.17] - 2026-09-11

### Aggiunto

- Login con passkey (WebAuthn) per i ruoli Amministratore e Segreteria: la
  passkey sostituisce il secondo fattore TOTP, restano i codici di recupero
  come ripiego in caso di perdita del dispositivo. Il ruolo RDZ resta
  vincolato al solo TOTP.

### Sicurezza

- Il codice di attivazione account non compare più nell'URL del link inviato
  via email: restava altrimenti nei log del server/proxy e nella cronologia
  del browser. Il codice resta comunque leggibile in chiaro nel corpo
  dell'email.

## [1.1.16] - 2026-09-09

### Aggiunto

- Timeout di sessione per inattività: un utente autenticato viene
  disconnesso automaticamente dopo un periodo di inattività configurabile
  da interfaccia (Impostazioni di piattaforma), di default 60 minuti.
