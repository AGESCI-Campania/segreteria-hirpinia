# Changelog

Tutte le modifiche rilevanti di Catello sono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.1.0/) e il
progetto aderisce a [Semantic Versioning](https://semver.org/lang/it/).

Le versioni precedenti alla 1.1.16 non sono documentate qui: la cronologia
completa resta disponibile con `git log`.

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
