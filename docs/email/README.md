# Invio email — guida per provider

Catello invia le email transazionali (verifica registrazione, reset password, inviti
OTP, notifiche di valutazione) tramite `django.core.mail`, come qualunque applicazione
Django standard. Il codice applicativo (incluso `django-allauth`) **non conosce mai** il
provider attivo: la scelta è isolata in un solo punto, la variabile d'ambiente
`EMAIL_PROVIDER`.

Questa cartella contiene una guida operativa per ciascun provider supportato: cosa
configurare lato Google/Microsoft/provider SMTP, e quali variabili impostare in `.env`.
Per le decisioni architetturali (perché esistono più provider, perché non SMTP su
Microsoft 365, ecc.) la fonte di verità resta **§ 8 di
[`docs/Catello_Progettazione.md`](../Catello_Progettazione.md)**: le guide qui sono il
"come fare", il documento di progettazione è il "perché".

## Provider disponibili

| `EMAIL_PROVIDER` | Uso | Guida |
| --- | --- | --- |
| `console` | Sviluppo: stampa le email sul terminale, non le invia | [sviluppo-e-test.md](sviluppo-e-test.md) |
| `locmem` | Test automatici: le email restano in memoria, mai inviate | [sviluppo-e-test.md](sviluppo-e-test.md) |
| `smtp` | Exchange on-premises, relay interni, provider transazionali (Brevo, Postmark, Mailgun…) | [smtp.md](smtp.md) |
| `gmail_service_account` | Gmail/Google Workspace — **consigliato** per Workspace | [gmail-service-account.md](gmail-service-account.md) |
| `gmail_oauth` | Gmail/Google Workspace, ripiego quando la delega di dominio non è disponibile | [gmail-oauth.md](gmail-oauth.md) |
| `microsoft_graph` | Microsoft 365 / Exchange Online | [microsoft-graph.md](microsoft-graph.md) |

## Come funziona la selezione

1. `EMAIL_PROVIDER` in `.env` seleziona il backend.
2. `apps/core/email/__init__.py::backend_path()` traduce il nome nel percorso della
   classe Django (`EMAIL_BACKEND`). Un valore non riconosciuto solleva
   `ImproperlyConfigured` **all'avvio** dell'applicazione: è una scelta deliberata,
   preferibile a scoprire in esercizio che le email non partono.
3. `config/settings/base.py` legge `EMAIL_PROVIDER` e imposta `EMAIL_BACKEND` di
   conseguenza, oltre a leggere le variabili comuni SMTP (`EMAIL_HOST`, `EMAIL_PORT`,
   ecc.) usate solo dal provider `smtp`.
4. I backend `gmail_service_account`, `gmail_oauth` e `microsoft_graph` estendono
   `apps/core/email/base.py::ApiEmailBackend`, che implementa la parte comune (MIME,
   `fail_silently`, cache del token di accesso, logging che non registra mai corpo del
   messaggio né token). Le sottoclassi in `apps/core/email/gmail.py` e
   `apps/core/email/microsoft.py` implementano solo `_richiedi_token()` e
   `_invia_mime()`.

> **Stato dell'implementazione.** `apps/core/email/__init__.py` (selezione del
> provider) e `apps/core/email/base.py` (base comune per i backend API) esistono già.
> `apps/core/email/gmail.py` e `apps/core/email/microsoft.py`, con i backend concreti,
> sono pianificati per M1 e non sono ancora scritti: con questi due provider selezionati
> oggi, l'invio fallirebbe all'`import`. I provider `console`, `locmem` e `smtp` sono
> invece backend Django standard e funzionano già. Le guide di questa cartella
> descrivono comunque la configurazione **lato Google/Microsoft**, che è indipendente
> dallo stato del codice e può essere preparata in anticipo.

## Requisiti trasversali (tutti i provider)

- Nessuna credenziale nel repository: tutto va in `.env`, mai committato (`.env` è in
  `.gitignore`; solo `.env.example`, senza valori reali, è versionato).
- `DEFAULT_FROM_EMAIL` deve coincidere con la casella autorizzata dal provider attivo:
  con service account e Graph, inviare da un mittente diverso da quello autorizzato
  fallisce sempre, indipendentemente dai permessi.
- Le dipendenze dei provider Gmail/Microsoft sono **extra opzionali**:
  ```bash
  uv add --extra gmail        # google-auth
  uv add --extra microsoft    # msal
  ```
  Un deploy che usa solo `smtp` non deve installare né l'uno né l'altro.
- Le email della piattaforma sono transazionali, volumi bassi: nessuna di queste
  configurazioni deve prevedere invio massivo o marketing.
- `console` e `locmem` sono provider di solo sviluppo/test e in produzione non sono solo
  sconsigliati: `config/settings/prod.py` solleva `ImproperlyConfigured` all'avvio se
  `EMAIL_PROVIDER` è impostato su uno dei due, quindi un `.env` di produzione dimenticato
  su questi valori fa fallire l'avvio del container invece di inviare email finte in
  silenzio. Dettagli in [`docs/docker.md`](../docker.md#log).
- Prima di aprire le registrazioni in produzione, verificare l'invio reale (quando
  esisterà il comando `manage.py test_email <destinatario>` previsto per M1) o, nel
  frattempo, con un invio manuale da shell Django (`python manage.py shell`):
  ```python
  from django.core.mail import send_mail
  send_mail("Prova Catello", "Corpo di prova.", None, ["destinatario@example.com"])
  ```

## Quale scegliere

- **Google Workspace** → `gmail_service_account` ([guida](gmail-service-account.md)).
  Usa `gmail_oauth` solo come ripiego se la delega di dominio non è disponibile
  ([guida](gmail-oauth.md), legge prima i vincoli sui refresh token).
- **Microsoft 365 / Exchange Online** → `microsoft_graph` ([guida](microsoft-graph.md)).
  Non usare SMTP: Microsoft sta ritirando l'autenticazione di base per SMTP AUTH.
- **Exchange on-premises, relay interno, provider transazionale (Brevo, Postmark,
  Mailgun…), o ripiego rapido** → `smtp` ([guida](smtp.md)).
- **Sviluppo locale e test automatici** → `console`/`locmem`
  ([guida](sviluppo-e-test.md)), già impostato di default in `.env.example`.
