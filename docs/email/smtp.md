# `smtp` — SMTP con password

Backend Django standard (`django.core.mail.backends.smtp.EmailBackend`), autenticazione
utente/password, cifratura STARTTLS o SSL implicito. Nessuna dipendenza aggiuntiva da
installare.

## Quando usarlo

- **Exchange on-premises**: la deprecazione dell'autenticazione di base per SMTP AUTH
  riguarda solo **Exchange Online** (Microsoft 365 cloud), non un'installazione on-prem.
  Per Microsoft 365 vero e proprio, usare invece [`microsoft_graph`](microsoft-graph.md).
- **Relay SMTP interno** dell'ente o dell'hosting.
- **Provider transazionali** (Brevo, Postmark, Mailgun, SendGrid…), quasi sempre
  utilizzabili anche via SMTP con l'API key come password.
- **Gmail con password per le app**, come ripiego temporaneo — non la modalità
  consigliata per Gmail: preferire [`gmail_service_account`](gmail-service-account.md).

## Configurazione lato provider

Varia per fornitore; in generale servono, dal pannello del provider:

1. Un host SMTP (es. `smtp.dominio.it`, `smtp-relay.brevo.com`, `smtp.postmarkapp.com`).
2. Una porta: **587** con STARTTLS (la più comune), oppure **465** con SSL implicito.
3. Credenziali: uno username (spesso l'indirizzo email stesso, o un identificativo
   fornito dal provider) e una password o API key.
4. Se il provider lo richiede, l'indirizzo mittente va **verificato** (SPF/DKIM
   configurati sul dominio) prima che l'invio funzioni: senza, i messaggi finiscono in
   spam o vengono rifiutati. Questo passaggio è lato DNS del dominio mittente, non lato
   Catello.

## Configurazione in `.env`

```bash
EMAIL_PROVIDER=smtp
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>

EMAIL_HOST=smtp.dominio.it
EMAIL_PORT=587
EMAIL_HOST_USER=segreteria@zonahirpinia.org
EMAIL_HOST_PASSWORD=la-password-o-api-key
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=20
```

**Vincolo non negoziabile**: attivare **una sola** fra `EMAIL_USE_TLS` e
`EMAIL_USE_SSL`, mai entrambe, mai nessuna delle due. `config/settings/base.py`
verifica questo vincolo all'avvio e solleva `ImproperlyConfigured` se sono entrambe
`True` — il boot dell'applicazione si ferma piuttosto che partire con una
configurazione ambigua.

Regola pratica per la scelta della porta:

| Porta | `EMAIL_USE_TLS` | `EMAIL_USE_SSL` | Uso |
| --- | --- | --- | --- |
| 587 | `True` | `False` | STARTTLS — la scelta più comune, compatibile con la maggior parte dei provider |
| 465 | `False` | `True` | SSL implicito — usare solo se il provider lo richiede esplicitamente |
| 25 | — | — | Da evitare: quasi mai cifrata, spesso bloccata dagli hosting |

## Esempi per provider comuni

**Brevo (ex Sendinblue)**
```bash
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<il tuo login SMTP Brevo>
EMAIL_HOST_PASSWORD=<la SMTP key generata nel pannello Brevo>
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
```

**Postmark**
```bash
EMAIL_HOST=smtp.postmarkapp.com
EMAIL_PORT=587
EMAIL_HOST_USER=<Server API Token>
EMAIL_HOST_PASSWORD=<lo stesso Server API Token>
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
```

**Gmail con password per le app (ripiego, non consigliato)**
```bash
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=segreteria@zonahirpinia.org
EMAIL_HOST_PASSWORD=<password per le app a 16 caratteri, generata nell'account Google>
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
```
Richiede la verifica in due passaggi attiva sull'account Google e la generazione di una
"password per le app" dedicata (mai la password normale dell'account). Va rigenerata se
revocata; per un uso stabile su Workspace preferire
[`gmail_service_account`](gmail-service-account.md).

## Verifica

```bash
uv run python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail("Prova Catello", "Corpo di prova.", None, ["un-indirizzo-che-controlli@example.com"])
```
Se solleva un'eccezione di autenticazione, verificare prima username/password, poi la
combinazione porta/TLS/SSL, infine eventuali restrizioni del provider (SPF/DKIM,
IP consentiti).

## Requisiti trasversali

Vedi [`README.md`](README.md#requisiti-trasversali-tutti-i-provider): nessuna
credenziale nel repository, `DEFAULT_FROM_EMAIL` coerente con la casella autorizzata,
`.env` mai versionato.
