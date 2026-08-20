# `microsoft_graph` — Microsoft 365 / Exchange Online

Autenticazione **client credentials** (app-only, `msal`): nessun utente coinvolto,
nessun token da rinnovare a mano. È l'**unica modalità consigliata** per Microsoft 365 /
Exchange Online — vedi il motivo in fondo a questa pagina.

## 1. Registrazione dell'applicazione in Entra ID

1. Vai su [portal.azure.com](https://portal.azure.com/) → **Microsoft Entra ID** →
   **Registrazioni app** → **Nuova registrazione**.
2. Nome: es. `Catello - invio email`.
3. Tipi di account supportati: **Solo gli account in questa directory organizzativa**
   (single tenant) — non serve accesso multi-tenant per questo uso.
4. URI di reindirizzamento: lasciare vuoto (non serve, è un flusso app-only senza
   interazione utente).
5. **Registra**.
6. Nella pagina **Panoramica** dell'app appena creata, annotare:
   - **ID applicazione (client)** → sarà `MS_CLIENT_ID`;
   - **ID directory (tenant)** → sarà `MS_TENANT_ID`.

## 2. Permesso applicativo `Mail.Send`

1. Nella app registrata: **Autorizzazioni API** → **Aggiungi un'autorizzazione**.
2. **Microsoft Graph** → **Autorizzazioni applicazione** (non "Autorizzazioni delegate":
   qui serve il permesso *app-only*, non legato a un utente che effettua il login).
3. Cercare e selezionare **`Mail.Send`**.
4. **Aggiungi autorizzazioni**.
5. Tornati alla schermata **Autorizzazioni API**, cliccare **Concedi consenso
   amministratore per <organizzazione>** e confermare. Senza questo passaggio il
   permesso resta "non concesso" e ogni invio fallisce con un errore di autorizzazione,
   anche se il permesso compare nell'elenco.

## 3. Segreto client o certificato

1. Nella app registrata: **Certificati e segreti** → **Nuovo segreto client**.
2. Descrizione libera, scadenza: scegliere la durata massima consentita
   dall'organizzazione (spesso 12 o 24 mesi) — **mai "Non scade mai"** se disponibile:
   un segreto senza scadenza è un rischio permanente.
3. **Copiare subito il valore (`Value`)**, non il "Secret ID": è visibile **una sola
   volta**, non più recuperabile dopo aver lasciato la pagina.
4. **Segnare in calendario la data di scadenza** (vedi § 2 dell'organizzazione): un
   segreto scaduto interrompe l'invio senza preavviso automatico da parte di Azure.

In alternativa al segreto, per un livello di sicurezza superiore, si può registrare un
**certificato** invece di un segreto client — non trattato qui in dettaglio: è
un'opzione più complessa da gestire operativamente per un volume di invii come quello
di Catello (transazionale, basso volume), il segreto client con scadenza tracciata è
sufficiente e più semplice da ruotare.

## 4. Application Access Policy — passaggio critico

> **Questo è il passaggio più importante dell'intera configurazione.** Senza, il
> permesso applicativo `Mail.Send` concesso al punto 2 autorizza l'app a inviare email
> **da qualunque cassetta postale dell'intero tenant**, non solo dalla casella
> mittente prevista. È un problema di sicurezza reale, non solo di buona pratica.

Va creato un **gruppo di distribuzione** (o un gruppo di sicurezza abilitato alla posta)
che contiene **solo** la casella mittente (es. `segreteria@zonahirpinia.org`), poi una
Application Access Policy che lega l'app a quel gruppo. Da **Exchange Online
PowerShell** (richiede un account con ruolo di amministratore Exchange):

```powershell
Connect-ExchangeOnline

# Gruppo di distribuzione con la sola casella mittente
New-DistributionGroup -Name "CatelloMailSenders" -Members "segreteria@zonahirpinia.org"

# Policy che limita l'app registrata (usare l'App ID del punto 1.6) a quel gruppo
New-ApplicationAccessPolicy `
    -AppId "<MS_CLIENT_ID annotato al punto 1.6>" `
    -PolicyScopeGroupId "CatelloMailSenders" `
    -AccessRight RestrictAccess `
    -Description "Limita Catello all'invio dalla sola casella segreteria"

# Verifica: deve rispondere "Access to mailbox X is Granted; App: <MS_CLIENT_ID>."
Test-ApplicationAccessPolicy -Identity "segreteria@zonahirpinia.org" -AppId "<MS_CLIENT_ID>"
```

Se `Test-ApplicationAccessPolicy` non riporta l'accesso come concesso proprio e solo
per la casella prevista, **non procedere** all'uso in produzione finché non risulta
corretto.

## 5. Configurazione in `.env`

```bash
EMAIL_PROVIDER=microsoft_graph
DEFAULT_FROM_EMAIL=Catello <segreteria@zonahirpinia.org>

MS_TENANT_ID=il-tenant-id-del-punto-1.6
MS_CLIENT_ID=il-client-id-del-punto-1.6
MS_CLIENT_SECRET=il-segreto-del-punto-3.3
MS_MITTENTE=segreteria@zonahirpinia.org
```

`MS_MITTENTE` deve coincidere con `DEFAULT_FROM_EMAIL` e con l'unica casella coperta
dall'Application Access Policy del punto 4.

## 6. Rotazione del segreto

Prima della scadenza segnata al punto 3.4:

1. **Certificati e segreti** → **Nuovo segreto client**, con nuova scadenza.
2. Aggiornare `MS_CLIENT_SECRET` in produzione con il nuovo valore e riavviare
   l'applicazione.
3. Solo dopo aver verificato che l'invio funzioni con il nuovo segreto, **eliminare**
   quello precedente dalla stessa pagina.

## 7. Verifica

```bash
uv run python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail("Prova Catello", "Corpo di prova.", None, ["un-indirizzo-che-controlli@example.com"])
```

Errori comuni:

- **`ErrorAccessDenied` / consenso non concesso**: manca il consenso amministratore al
  punto 2.5, oppure la Application Access Policy del punto 4 non include la casella
  mittente — ripetere `Test-ApplicationAccessPolicy`.
- **`Forbidden` con messaggio sul tenant**: `MS_MITTENTE` non corrisponde alla casella
  prevista dalla policy, o al dominio del tenant indicato in `MS_TENANT_ID`.
- **`invalid_client`**: `MS_CLIENT_ID`/`MS_CLIENT_SECRET`/`MS_TENANT_ID` non
  corrispondono, oppure il segreto è scaduto (§ 3.4) o è stato eliminato.

## Perché non SMTP su Microsoft 365

Microsoft sta ritirando l'autenticazione di base per SMTP AUTH in Exchange Online:
comportamento invariato annunciato fino a **dicembre 2026**, disattivazione predefinita
per i tenant esistenti prevista **fine dicembre 2026** (riattivabile dall'amministratore
finché disponibile), non disponibile per i **nuovi tenant**, e rimozione definitiva
prevista nel **2027**. Il calendario è stato rivisto più volte da Microsoft: va
riverificato sulla documentazione ufficiale prima di ogni deploy che si affidi a questa
timeline. Una piattaforma che entra in esercizio oggi non deve nascere su un
meccanismo con una data di scadenza nota: da qui la scelta di Graph come unica modalità
per Microsoft 365.

## Riferimenti

- Microsoft Graph, `sendMail` — https://learn.microsoft.com/graph/api/user-sendmail
- Deprecazione Basic auth per SMTP AUTH in Exchange Online —
  https://techcommunity.microsoft.com/blog/exchange/updated-exchange-online-smtp-auth-basic-authentication-deprecation-timeline/4489835

## Requisiti trasversali

Vedi [`README.md`](README.md#requisiti-trasversali-tutti-i-provider). Ricorda inoltre:
`uv add --extra microsoft` per installare `msal`.
