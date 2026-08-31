# Interruttore Mailpit in produzione

Meccanismo **diverso** dal Mailpit di sviluppo descritto in
[`sviluppo-e-test.md`](sviluppo-e-test.md): lì si sceglie `EMAIL_PROVIDER=smtp` in
`.env` (scelta all'avvio, come ogni altro provider). Qui invece l'interruttore è un
campo di "Impostazioni di piattaforma" nell'interfaccia, letto **a ogni invio**: quando
attivo, ogni email che l'applicazione proverebbe a inviare — verifica registrazione,
reset password, inviti OTP, notifiche di valutazione, template email (M8) — viene
reindirizzata su Mailpit invece di raggiungere il destinatario reale, senza toccare
`EMAIL_PROVIDER` né riavviare il container.

## Perché esiste

Serve a verificare in produzione, con dati e configurazione reali, che l'intera catena
di invio funzioni — comprese le personalizzazioni salvate in `TemplateEmail` — senza
inviare email vere a soci reali durante la verifica. Utile prima di aprire le
registrazioni, dopo una modifica ai template, o per riprodurre una segnalazione.

## Deviazione dichiarata

`CLAUDE.md` (§ Email) vieta di scegliere il trasporto altrove che con `EMAIL_PROVIDER`,
e vieta `if provider == ...` nel codice applicativo — regola pensata per impedire che
view, service layer o allauth debbano conoscere il provider attivo. Questo interruttore
la aggira per una scelta di prodotto esplicita, ma resta confinato a un solo modulo:
`apps/core/email/override.py::MailpitOverridableBackend`. Nessun'altra parte
dell'applicazione legge il flag o sa che esiste; tutte continuano a usare
`django.core.mail` come sempre. È l'unico backend selezionato incondizionatamente da
`config/settings/prod.py`, indipendentemente da `EMAIL_PROVIDER`.

## Configurazione

1. Avviare un Mailpit **raggiungibile solo dalla rete Docker interna**, mai esposto
   pubblicamente:
   ```bash
   docker compose -f compose.prod.yaml up -d mailpit
   ```
   (servizio dietro il profilo Compose `mailpit`: non parte con un `up -d` senza
   argomenti — vedi [`docs/docker.md`](../docker.md)). L'interfaccia web resta
   raggiungibile solo su `127.0.0.1:8025` sul server, mai da internet: un tunnel SSH
   (`ssh -L 8025:localhost:8025 ...`) è il modo previsto per consultarla.
2. In `.env`:
   ```bash
   EMAIL_MAILPIT_HOST=mailpit   # nome del servizio Compose, non un IP
   EMAIL_MAILPIT_PORT=1025
   ```
   e riavviare `web` perché le legga.
3. In Impostazioni di piattaforma (Amministrazione → Impostazioni), attivare "Invia le
   email su Mailpit invece del provider configurato". Il form rifiuta di salvarlo se
   `EMAIL_MAILPIT_HOST` non è configurato.

## Cosa NON fa

- Non richiede né tocca `EMAIL_PROVIDER`: il provider reale resta configurato e pronto,
  semplicemente non viene usato finché il flag è attivo.
- Non filtra per tipo di email o destinatario: **tutte** le email della piattaforma
  vengono deviate, senza eccezioni.
- Non si disattiva da solo: resta attivo finché qualcuno con
  `RUOLI_GESTIONE_IMPOSTAZIONI` (ADMIN/SEGRETERIA/RDZ diretti) non lo spegne
  dall'interfaccia. Ogni attivazione/disattivazione è tracciata in auditlog
  (`ImpostazioniPiattaforma` è registrato — vedi `apps/core/apps.py`), quindi è sempre
  ricostruibile chi e quando l'ha cambiato.

## Rischio operativo

Mentre il flag è attivo, **nessuna email reale parte**: un socio che chiede il reset
password, un invito, un'attivazione via OTP restano bloccati senza errore visibile
lato utente (l'invio "riesce", solo verso Mailpit). L'interfaccia mostra un avviso
esplicito accanto al campo proprio per questo. Prima di aprire un test in produzione:
avvisare chi gestisce la segreteria, e verificare subito dopo di averlo disattivato che
un invio reale funzioni ancora.
