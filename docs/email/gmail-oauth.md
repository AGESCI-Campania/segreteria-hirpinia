# `gmail_oauth` — Gmail/Google Workspace via OAuth utente (ripiego)

> **Leggere prima di procedere.** Questa modalità è il **ripiego**, non la scelta
> predefinita: se hai accesso all'Admin Console di un Google Workspace, usa
> [`gmail_service_account`](gmail-service-account.md), più semplice da mantenere e
> senza token che scadono. Usa `gmail_oauth` solo se la delega a livello di dominio non
> è disponibile (account amministrativo non concesso, policy dell'organizzazione, o un
> account Gmail che non è Workspace ma comunque non vuoi usare una password per le app).

## Vincoli da conoscere prima di scegliere questa modalità

- Un'app con schermata di consenso OAuth **esterna** in stato **Testing** riceve
  refresh token che **scadono dopo 7 giorni**: inutilizzabile in produzione così com'è.
- **Pubblicare** l'app (uscire da "Testing") richiede la **verifica di sicurezza di
  Google**, con audit, perché lo scope `gmail.send` è classificato come *restricted*.
  È un processo che può richiedere settimane.
- Se l'app è **interna** a un'organizzazione Google Workspace (schermata di consenso di
  tipo "Interno", non "Esterno"), **non si applicano** né la scadenza a 7 giorni né il
  limite di utenti di test: è l'**unica configurazione OAuth utente realisticamente
  praticabile in produzione**, e richiede comunque un Workspace (non un Gmail
  consumer).
- Un **cambio password** della casella Google **revoca** il refresh token quando questo
  contiene scope Gmail: l'invio si interrompe silenziosamente finché non si
  ri-autorizza manualmente. È il motivo principale per cui questa modalità è un
  ripiego e non la scelta di default.

Se nessuna delle due condizioni sopra (Workspace con app interna) è soddisfatta, non
proseguire con questa modalità: usare [`smtp`](smtp.md) con password per le app come
ripiego più semplice, o richiedere l'accesso Admin Console per usare
[`gmail_service_account`](gmail-service-account.md).

## 1. Progetto Google Cloud e abilitazione dell'API

1. [Google Cloud Console](https://console.cloud.google.com/) → crea o seleziona un
   progetto.
2. Menu ☰ → **API e servizi** → **Libreria** → cerca **Gmail API** → **Abilita**.

## 2. Schermata di consenso OAuth

1. Menu ☰ → **API e servizi** → **Schermata consenso OAuth**.
2. **Tipo utente**: scegliere **Interno** se il Google Cloud project è collegato a
   un'organizzazione Google Workspace (evita la scadenza a 7 giorni, vedi sopra). Se
   compare solo "Esterno", il progetto non è associato a un'organizzazione Workspace:
   valutare se questa è davvero la strada giusta prima di proseguire.
3. Compilare nome dell'app, email di supporto, email di contatto dello sviluppatore.
4. Nella sezione **Ambiti**, aggiungere `https://www.googleapis.com/auth/gmail.send`.
5. Salvare.

## 3. Credenziali OAuth client

1. Menu ☰ → **API e servizi** → **Credenziali** → **Crea credenziali** → **ID client
   OAuth**.
2. Tipo applicazione: **App per computer** (Desktop app) — è il tipo più semplice per
   generare un refresh token da riga di comando, senza dover ospitare un redirect URI
   pubblico.
3. Annotare **Client ID** e **Client secret** mostrati dopo la creazione.

## 4. Generazione del refresh token

Serve un flusso OAuth eseguito **una volta** con l'account Google della casella
mittente, per ottenere un refresh token da usare poi in modo continuativo dal server.

Con Python e la libreria `google-auth-oauthlib` (da eseguire su una macchina con
browser, non necessariamente sul server — è un passo manuale una tantum):

```bash
pip install google-auth-oauthlib   # solo per questo script una tantum, non è una dipendenza del progetto
```

```python
# genera_refresh_token.py
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": "IL_TUO_CLIENT_ID",
            "client_secret": "IL_TUO_CLIENT_SECRET",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    SCOPES,
)
creds = flow.run_local_server(port=0)
print("Refresh token:", creds.refresh_token)
```

```bash
python genera_refresh_token.py
```

Si apre il browser: accedere con l'account Google della **casella mittente** (es.
`segreteria@zonahirpinia.org`) e concedere il consenso allo scope `gmail.send`. Lo
script stampa il refresh token in output.

## 5. Configurazione in `.env`

```bash
EMAIL_PROVIDER=gmail_oauth
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>

GMAIL_CLIENT_ID=il-client-id-del-passo-3
GMAIL_CLIENT_SECRET=il-client-secret-del-passo-3
GMAIL_REFRESH_TOKEN=il-refresh-token-del-passo-4
```

L'access token si rinnova automaticamente a partire dal refresh token: non richiede
ulteriori interventi finché il refresh token resta valido (vedi i vincoli sopra su
scadenza a 7 giorni e revoca al cambio password).

## 6. Verifica

```bash
uv run python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail("Prova Catello", "Corpo di prova.", None, ["un-indirizzo-che-controlli@example.com"])
```

Se l'invio fallisce con un errore di token non valido o scaduto, e sono passati più di
7 giorni dalla generazione: probabile causa la schermata di consenso ancora in stato
"Testing" (§ 2) — verificare lo stato di pubblicazione dell'app nella Google Cloud
Console. Se invece l'app era "Interno" e l'errore compare comunque dopo un cambio
password della casella, va rigenerato il refresh token dal punto 4.

## Percorso di uscita da questa modalità

Se in futuro diventa disponibile l'accesso Admin Console del Workspace, migrare a
[`gmail_service_account`](gmail-service-account.md): elimina sia il problema della
scadenza sia quello della revoca al cambio password, senza richiedere la verifica di
sicurezza Google per uscire da "Testing".

## Riferimenti

- Scadenza dei refresh token OAuth 2.0 —
  https://developers.google.com/identity/protocols/oauth2
- Gmail API, invio messaggi — https://developers.google.com/gmail/api/guides/sending

## Requisiti trasversali

Vedi [`README.md`](README.md#requisiti-trasversali-tutti-i-provider). Ricorda inoltre:
`uv add --extra gmail` per installare `google-auth`.
