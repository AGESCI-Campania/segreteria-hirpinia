# `gmail_service_account` — Gmail/Google Workspace (consigliato)

Autenticazione **service account con delega a livello di dominio**: nessun token
utente da rinnovare, nessuna sessione che scade, un cambio password della casella
mittente non interrompe l'invio. È la modalità **consigliata** per Gmail/Google
Workspace, preferibile a [`gmail_oauth`](gmail-oauth.md).

**Richiede Google Workspace** (non funziona con un account Gmail personale/consumer:
la delega a livello di dominio è una funzionalità dell'Admin Console di Workspace).

## 1. Progetto Google Cloud e abilitazione dell'API

1. Vai su [Google Cloud Console](https://console.cloud.google.com/) con un account che
   abbia i permessi per creare progetti nell'organizzazione, o usa un progetto
   esistente dedicato all'ente.
2. **Crea un nuovo progetto** (o selezionane uno esistente) — es. `catello-hirpinia`.
3. Menu ☰ → **API e servizi** → **Libreria**.
4. Cerca **Gmail API** e clicca **Abilita**.

## 2. Creazione del service account

1. Menu ☰ → **API e servizi** → **Credenziali**.
2. **Crea credenziali** → **Account di servizio**.
3. Nome: es. `catello-invio-email`. Descrizione libera. **Crea e continua**.
4. Nei passaggi "Concedi a questo account di servizio l'accesso al progetto" e
   "Concedi agli utenti l'accesso a questo account di servizio": **salta entrambi**
   (non servono ruoli IAM sul progetto per inviare email, solo la delega di dominio
   configurata al passo 4). Clicca **Fine**.
5. Nell'elenco degli account di servizio, apri quello appena creato.
6. Scheda **Chiavi** → **Aggiungi chiave** → **Crea nuova chiave** → tipo **JSON** →
   **Crea**. Il browser scarica un file `.json`: è l'**unica copia scaricabile**, non
   riottenibile in seguito (si può solo revocarla e generarne una nuova).
7. Annota il **Client ID numerico** dell'account di servizio (visibile nella stessa
   pagina, campo "ID cliente univoco"): serve al passo successivo.

**Trattamento della chiave JSON**: contiene una chiave privata. Non va mai committata
nel repository, né allegata a un'email o a un ticket. Va conservata in `.env` (come
contenuto su una riga, vedi § 4) oppure come file montato in sola lettura nel
container, mai nell'immagine Docker (verificare che non finisca copiata dal contesto
di build: `.dockerignore` del progetto già esclude `.env*`, ma un file `.json` separato
andrebbe escluso esplicitamente se posizionato nella cartella del progetto).

## 3. Delega a livello di dominio (Admin Console Workspace)

Questo passaggio autorizza il service account a inviare email **come se fosse** la
casella mittente, ma solo per lo scope specificato — non per l'intera cassetta.

1. Vai su [Admin Console Google Workspace](https://admin.google.com/) con un account
   **super amministratore** del dominio.
2. Menu ☰ → **Sicurezza** → **Controllo API** → **Delega a livello di dominio**.
3. **Aggiungi nuovo**.
4. **ID cliente**: incolla il Client ID numerico annotato al passo 2.7 (non il "nome"
   del service account, il numero).
5. **Ambiti OAuth autorizzati**: incolla **esattamente**
   ```
   https://www.googleapis.com/auth/gmail.send
   ```
   Non aggiungere altri scope: il principio di minimo privilegio limita il service
   account al solo invio, non alla lettura o gestione della posta.
6. **Autorizza**.

Senza questo passaggio, il service account esiste ma non può impersonare nessuna
casella: ogni invio fallirebbe con un errore di autorizzazione.

## 4. Configurazione in `.env`

```bash
EMAIL_PROVIDER=gmail_service_account
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>

# Contenuto del file JSON scaricato al passo 2.6, su UNA riga (rimuovere gli a-capo)
GMAIL_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n","client_email":"catello-invio-email@catello-hirpinia.iam.gserviceaccount.com","client_id":"...", ...}

# In alternativa al valore inline sopra: percorso di un file montato in sola lettura
# (utile in Docker con un secret montato). Se entrambe le variabili sono valorizzate,
# vale quella che il codice del backend privilegia — verificarlo in
# apps/core/email/gmail.py quando sarà implementato; nel dubbio, valorizzarne una sola.
# GMAIL_SERVICE_ACCOUNT_FILE=/run/secrets/gmail-service-account.json

# Casella impersonata: DEVE coincidere con DEFAULT_FROM_EMAIL sopra
GMAIL_MITTENTE=segreteria@zonahirpinia.org
```

Per produrre il valore su una riga da un file scaricato:

```bash
cat service-account.json | tr -d '\n'
```

## 5. Rotazione della chiave

La chiave JSON non scade automaticamente, ma va **ruotata annualmente** per buona
pratica di sicurezza:

1. Admin Console del progetto Cloud → account di servizio → scheda **Chiavi** →
   **Aggiungi chiave** → nuova chiave JSON.
2. Aggiornare `GMAIL_SERVICE_ACCOUNT_JSON`/`GMAIL_SERVICE_ACCOUNT_FILE` in produzione
   con il nuovo valore e riavviare l'applicazione.
3. Solo dopo aver verificato che l'invio funzioni con la nuova chiave, **eliminare**
   la chiave precedente dalla stessa scheda (non prima: eliminarla subito
   interromperebbe l'invio se il deploy della nuova chiave avesse un problema).

## 6. Verifica

```bash
uv run python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail("Prova Catello", "Corpo di prova.", None, ["un-indirizzo-che-controlli@example.com"])
```

Errori comuni:

- **`unauthorized_client` / `invalid_grant`**: la delega di dominio (§ 3) non è
  configurata, o lo scope non corrisponde esattamente a
  `https://www.googleapis.com/auth/gmail.send`, o l'ID cliente inserito non è quello
  del service account.
- **`403` sull'invio**: `GMAIL_MITTENTE` non coincide con `DEFAULT_FROM_EMAIL`, oppure
  la casella impersonata non esiste nel dominio Workspace.
- **Errore di parsing della chiave**: il JSON in `GMAIL_SERVICE_ACCOUNT_JSON` contiene
  interruzioni di riga letterali invece di essere su una sola riga con `\n` all'interno
  della stringa `private_key` (così come lo produce il file scaricato, se convertito
  correttamente con `tr -d '\n'` **solo sulle interruzioni di riga del file**, non
  dentro le stringhe JSON — il comando sopra è corretto perché il file scaricato da
  Google è già JSON valido su più righe "fisiche" ma senza a-capo dentro le stringhe).

## Riferimenti

- Gmail API, invio messaggi — https://developers.google.com/gmail/api/guides/sending
- Panoramica delega a livello di dominio — parte della documentazione Google Workspace
  Admin, raggiungibile dalla stessa pagina di **Controllo API** dell'Admin Console.

## Requisiti trasversali

Vedi [`README.md`](README.md#requisiti-trasversali-tutti-i-provider). Ricorda inoltre:
`uv add --extra gmail` per installare `google-auth`, non necessaria se si usa solo
`smtp`/`microsoft_graph`.
