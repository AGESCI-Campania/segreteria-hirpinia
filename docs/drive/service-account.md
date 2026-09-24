# Replica su Google Drive dei giustificativi/PDF (D-59, F9)

Alla liquidazione di una nota spese, Catello mette in coda una copia del PDF della
nota e di tutti i giustificativi delle sue righe verso un **Drive condiviso**
dell'organizzazione — una copia di sicurezza fuori dal database, indipendente dallo
storage primario (filesystem locale per default, D-59).

**Finché questa pagina non è stata seguita, la replica resta disattivata**: nessun
errore, `apps.note_spese.drive::replica_configurata()` restituisce `False` e il
comando di riconciliazione (`manage.py note_spese_drive_riconcilia`, invocato da un
loop in `compose.prod.yaml`) è un no-op silenzioso.

## Perché un Drive condiviso e non il "My Drive" del service account

Un service account **non ha spazio di archiviazione proprio**. Caricare file sul suo
"My Drive" personale fallisce con un errore di quota, non un errore di permessi — un
sintomo facile da fraintendere. Serve un **Drive condiviso** ("Shared Drive", ex "Team
Drive") dell'organizzazione, con il service account invitato come membro con permesso
di scrittura: la quota è quella dell'organizzazione, non quella dell'account.

## 1. Progetto Google Cloud e abilitazione dell'API

Si può riusare lo stesso progetto Google Cloud già usato per [Gmail via service
account](../email/gmail-service-account.md) (es. `catello-hirpinia`), oppure un
progetto dedicato.

1. [Google Cloud Console](https://console.cloud.google.com/) → il progetto scelto.
2. Menu ☰ → **API e servizi** → **Libreria**.
3. Cerca **Google Drive API** e clicca **Abilita**.

## 2. Service account

Si può riusare lo **stesso service account** già creato per Gmail (nessuna
controindicazione: sono scope diversi, `gmail.send` per la posta, `drive` per questo),
oppure crearne uno dedicato per separare nettamente i due usi — scelta
dell'operatore, non tecnica.

Per crearne uno nuovo, stessi passi di [`gmail-service-account.md` § 2](../email/gmail-service-account.md):
Credenziali → Crea credenziali → Account di servizio → salta i passaggi sui ruoli IAM
→ scheda Chiavi → Crea nuova chiave → JSON.

**Trattamento della chiave JSON**: stesso vincolo del service account Gmail — mai nel
repository, mai in un'email o un ticket, solo in `.env` o come file montato in sola
lettura (mai nell'immagine Docker).

## 3. Creazione del Drive condiviso e invito del service account

1. [Google Drive](https://drive.google.com/) con un account che abbia i permessi per
   creare Drive condivisi nell'organizzazione (di norma un amministratore Workspace).
2. Menu laterale → **Drive condivisi** → **Nuovo**. Nome, es. "Catello — Note spese".
3. Apri il Drive condiviso appena creato → **Gestisci utenti** (icona persona in alto).
4. Aggiungi l'**email del service account** (campo "client_email" nel file JSON
   scaricato, formato `nome@progetto.iam.gserviceaccount.com`), ruolo **Content
   Manager** (può caricare, modificare, eliminare — non serve "Gestore", che
   aggiungerebbe anche la gestione dei membri).
5. Annota l'**id del Drive condiviso**: apri il Drive condiviso nel browser, l'id è
   il segmento dopo `/drive/folders/` nell'URL.
6. Opzionale: crea una sottocartella dedicata dentro il Drive condiviso (es. "Note
   spese liquidate") e annota il suo id allo stesso modo — altrimenti i file finiscono
   nella radice del Drive condiviso.

## 4. Configurazione in `.env`

```bash
# Se si riusa lo stesso service account di Gmail, stesso contenuto di
# GMAIL_SERVICE_ACCOUNT_JSON. Se se ne crea uno dedicato, il JSON scaricato al passo 2.
DRIVE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...", ...}

# In alternativa al valore inline sopra: percorso di un file montato in sola lettura.
# Se entrambe le variabili sono valorizzate, DRIVE_SERVICE_ACCOUNT_JSON ha priorità
# (apps/note_spese/drive.py::_carica_service_account_info).
# DRIVE_SERVICE_ACCOUNT_FILE=/run/secrets/drive-service-account.json

# Id del Drive condiviso (passo 3.5) e della cartella di destinazione (passo 3.6,
# o lo stesso id del Drive condiviso se si usa la radice).
DRIVE_SHARED_DRIVE_ID=0AbCdEfGhIjKlMnOp...
DRIVE_FOLDER_ID=1AbCdEfGhIjKlMnOpQrStUvWxYz...

# In produzione, in docker/Dockerfile / compose.prod.yaml: installa l'extra Python
# che porta google-auth (indipendente da EMAIL_EXTRA, vedi docs/docker.md).
DRIVE_EXTRA=drive
```

In sviluppo (`uv sync`, fuori Docker): `uv sync --extra drive` per installare
`google-auth`/`requests` prima di testare la replica con un Drive condiviso reale.

## 5. Verifica

```bash
uv run python manage.py note_spese_drive_riconcilia
```

Con la configurazione completa e almeno una `CopiaDrive` in stato `IN_ATTESA` o
`FALLITO` (creata automaticamente alla liquidazione di una nota, `enqueue_copie_drive()`
in `apps/note_spese/transizioni.py::liquida()`), il comando stampa quante copie sono
riuscite. Gli esiti (incluso l'ultimo errore per le copie fallite) sono visibili da
Django admin su `CopiaDrive`.
