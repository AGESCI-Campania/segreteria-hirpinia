# Changelog

Tutte le modifiche rilevanti di Catello sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il
progetto aderisce a [Semantic Versioning](https://semver.org/lang/it/).

Le versioni precedenti alla 1.1.16 non sono documentate qui: la cronologia
completa resta disponibile con `git log`.

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
