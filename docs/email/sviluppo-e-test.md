# `console`, `locmem` e Mailpit — sviluppo e test

Nessuna configurazione lato provider: sono backend Django standard, già pronti all'uso.
Mailpit fa eccezione solo perché serve un container in più (opzionale), non perché
richieda un backend dedicato — usa lo stesso provider `smtp` già documentato in
[`smtp.md`](smtp.md), solo puntato su un catcher locale invece che su un server reale.

## `console` — sviluppo locale

Le email non vengono inviate: il contenuto (intestazioni comprese) viene stampato
sull'output del server di sviluppo (`mise run dev`) **e**, in più rispetto al backend
console standard di Django, duplicato in un file di log
(`apps.core.email.console.ConsoleFileEmailBackend`). È utile perché nel flusso reale di
sviluppo l'email va spesso riletta più tardi o da un altro terminale rispetto a quello
con `runserver` in esecuzione. È il default in `.env.example` ed è sufficiente per
sviluppare qualunque flusso che invia email (verifica registrazione, inviti OTP, reset
password) senza avere un provider reale configurato. **Solo per sviluppo**: non pensato
per la produzione (nessuna rotazione, nessun limite di dimensione del file).

```bash
# .env
EMAIL_PROVIDER=console
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>

# Percorso del file di log, opzionale — default log/email-console.log
# EMAIL_CONSOLE_LOG_FILE=log/email-console.log
```

Verifica: avviare `mise run dev`, innescare un invio (es. registrazione utente quando
implementata) e osservare il contenuto dell'email sia nel terminale dove gira
`runserver`, sia in coda al file di log:

```bash
tail -f log/email-console.log
```

Il file si trova nella cartella `log/`, già esclusa da `.gitignore`: non va mai
versionato, anche se contiene solo email di prova.

## Mailpit — alternativa a `console` con interfaccia web

`console` stampa le email su terminale/file: leggibile, ma scomodo per verificare
rendering HTML, allegati o intestazioni come li vedrebbe davvero un client di posta.
Mailpit è un catcher SMTP con interfaccia web che cattura ogni email inviata con
`EMAIL_PROVIDER=smtp` puntato su di lui, senza consegnarla mai davvero.

```bash
mise run mailpit-up   # docker compose up -d mailpit — vedi docs/docker.md
```

```bash
# .env
EMAIL_PROVIDER=smtp
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>
EMAIL_HOST=localhost
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_USE_SSL=False
```

Verifica: avviare `mise run dev`, innescare un invio, poi aprire
`http://localhost:8025` — l'email compare nell'elenco con anteprima HTML e testo,
intestazioni comprese. `mise run mailpit-down` ferma il container; i messaggi restano
solo in memoria, non sopravvivono a un riavvio.

Non è pensato per la produzione con questo meccanismo (`EMAIL_PROVIDER=smtp` punterebbe
altrove): il caso d'uso di produzione — un interruttore in Impostazioni che reindirizza
temporaneamente le email reali su Mailpit — è un meccanismo diverso, documentato in
[`mailpit-override-produzione.md`](mailpit-override-produzione.md).

## `locmem` — test automatici

Le email restano in memoria nel processo, accessibili in test tramite
`django.core.mail.outbox`, e non vengono mai inviate realmente. **`config/settings/test.py`
forza questo backend in modo hardcoded**, indipendentemente dal valore di
`EMAIL_PROVIDER` nell'ambiente: è una garanzia in profondità, coerente con il vincolo
del progetto per cui nessun test deve poter inviare email reali, anche se qualcuno per
errore configurasse `EMAIL_PROVIDER=smtp` nell'ambiente di CI.

Non richiede alcuna variabile d'ambiente dedicata. Esempio d'uso in un test:

```python
from django.core import mail

def test_invio_email(...):
    ...
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["destinatario@example.com"]
```

## Quando passare a un provider reale

Questi due backend non vanno mai usati in produzione: nessuna email arriverebbe
davvero. Per la produzione, vedi [`README.md`](README.md) per scegliere fra
[`smtp`](smtp.md), [`gmail_service_account`](gmail-service-account.md),
[`gmail_oauth`](gmail-oauth.md) o [`microsoft_graph`](microsoft-graph.md).
