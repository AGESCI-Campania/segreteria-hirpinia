# Docker — installazione, configurazione ed esecuzione

Guida operativa per eseguire Catello con Docker, sia in sviluppo che in produzione. Per
le decisioni architetturali dietro queste scelte (perché solo il database è
containerizzato in sviluppo, perché il reverse proxy è selezionabile, perché
`createcachetable` non è nell'entrypoint) la fonte di verità resta
[`docs/Catello_Progettazione.md`](Catello_Progettazione.md) § D-17/D-18; questa guida è
il "come fare".

## Panoramica

Catello usa Docker in due modi diversi, non intercambiabili:

| | Sviluppo | Produzione |
| --- | --- | --- |
| File compose | `compose.yaml` | `compose.prod.yaml` (+ `compose.prod.nginx.yaml` opzionale) |
| Cosa gira in Docker | Solo PostgreSQL | PostgreSQL + applicazione (Gunicorn), reverse proxy incluso solo con l'opzione `nginx-docker` |
| Cosa gira sull'host | Django (`manage.py runserver`), via `uv`/`mise` | Nulla, salvo eventualmente il reverse proxy (`nginx-host`/`apache-host`) |
| Server applicativo | `runserver` (autoreload, debug toolbar) | `gunicorn` |
| Immagine applicativa | Non costruita | Costruita da `docker/Dockerfile` |

Non esiste un solo `docker-compose.yml`: usare il file giusto per l'ambiente giusto è
essenziale, altrimenti si finisce per costruire un'immagine di produzione mentre si
lavora in locale, o viceversa.

## Prerequisiti

- **Sviluppo**: Docker Engine + plugin Compose (`docker compose version`), [`uv`
  ](https://github.com/astral-sh/uv), [`mise`](https://mise.jdx.dev/), Python ≥ 3.14
  (installato da `mise`, non serve installarlo a parte).
- **Produzione**: solo Docker Engine + plugin Compose sul server. Non serve Python, `uv`
  né `mise` sull'host: tutto vive dentro l'immagine costruita da `docker/Dockerfile`.

Verifica rapida:

```bash
docker compose version   # richiede il plugin "compose", non il vecchio docker-compose standalone
```

---

## Sviluppo

In sviluppo **solo PostgreSQL gira in Docker**; Django gira sull'host per avere
autoreload, debug toolbar e un ciclo di modifica/verifica rapido.

### 1. Clona e installa i tool

```bash
git clone https://github.com/AGESCI-Campania/catello-hirpinia.git
cd catello-hirpinia

mise install   # installa Python 3.14 e uv alla versione richiesta da .mise.toml
uv sync        # crea .venv e installa le dipendenze (mai pip install diretto)
```

### 2. Configura l'ambiente

```bash
cp .env.example .env
```

Per lo sviluppo i valori di default in `.env.example` funzionano quasi tutti così come
sono (`DEBUG=True`, `EMAIL_PROVIDER=console`, credenziali PostgreSQL locali). Da
personalizzare comunque:

- `SECRET_KEY` — qualunque stringa casuale va bene in locale, ma **non riusare mai** il
  valore di sviluppo in produzione.
- `DOMINI_RUOLI_EFFETTIVI` ed `EMAIL_SEGRETERIA` se si vuole testare l'attivazione
  account con domini reali.

Il resto delle variabili (email, provider Gmail/Microsoft) è documentato in
[`docs/email/README.md`](email/README.md); in sviluppo il default `EMAIL_PROVIDER=console`
non richiede altro.

### 3. Avvia PostgreSQL in Docker

```bash
mise run db-up        # equivalente a: docker compose up -d db
```

`compose.yaml` espone PostgreSQL su `localhost:5432` con le credenziali lette da `.env`
(default `catello`/`catello` se non impostate), e persiste i dati nel volume Docker
`postgres_data` — sopravvive a `docker compose down`, non a `docker compose down -v`.

```bash
mise run db-down       # ferma il container, i dati restano nel volume
docker compose down -v # ATTENZIONE: cancella anche il volume, quindi tutti i dati
```

### 4. Migrazioni e superuser

```bash
mise run migrate
uv run python manage.py createsuperuser
```

### 5. Avvia il server

```bash
mise run dev
```

Applicazione su `http://127.0.0.1:8000/`. La debug toolbar di Django è attiva
automaticamente in `config/settings/dev.py` (limitata a `INTERNAL_IPS = ["127.0.0.1"]`).

### Task `mise` disponibili

| Comando | Descrizione |
| --- | --- |
| `mise run dev` | Server di sviluppo (`manage.py runserver`) |
| `mise run migrate` | Applica le migrazioni |
| `mise run makemigrations` | Genera le migrazioni |
| `mise run shell` | Shell Django (`manage.py shell`) |
| `mise run test` | Suite di test (`pytest`, richiede PostgreSQL attivo) |
| `mise run lint` | ruff + black --check + mypy |
| `mise run format` | ruff --fix + black |
| `mise run db-up` / `mise run db-down` | Avvia/ferma PostgreSQL in Docker |

### Reset completo del database di sviluppo

```bash
mise run db-down
docker compose down -v   # rimuove anche il volume postgres_data
mise run db-up
mise run migrate
```

### Eseguire i test

I test richiedono PostgreSQL attivo (`mise run db-up`), non un database separato: pytest
crea e distrugge un database di test a ogni esecuzione.

```bash
mise run test
```

I test che toccano il report PDF (WeasyPrint) richiedono le librerie native
Pango/Cairo/GObject nel percorso di link dinamico. Su macOS/Homebrew, se non sono nel
percorso di default:

```bash
DYLD_LIBRARY_PATH=/opt/homebrew/lib mise run test
```

In Docker (sia in CI sia in produzione) non serve: `docker/Dockerfile` installa quelle
librerie di sistema e il percorso è già quello standard.

---

## Produzione

In produzione **tutto gira in Docker tranne, facoltativamente, il reverse proxy**:
PostgreSQL, l'applicazione (Gunicorn) e — solo con l'opzione `nginx-docker` — anche
nginx.

### Requisiti del server

- Docker Engine + plugin Compose.
- Un dominio che punta al server (per Catello: `segreteria.agescihirpinia.it`, con
  `catello.agescihirpinia.it` come alias).
- Directory sul filesystem host per i dati persistenti dell'applicazione:

  ```bash
  sudo mkdir -p /srv/catello/{static,media,log}
  ```

  `compose.prod.yaml` monta questi percorsi come bind mount nel container; se non
  esistono, Docker li crea automaticamente al primo avvio ma di proprietà di `root`
  (il container gira come `root`, quindi funziona comunque) — crearli prima è solo più
  chiaro da amministrare.

### 1. Clona il repository sul server

```bash
git clone https://github.com/AGESCI-Campania/catello-hirpinia.git /opt/catello
cd /opt/catello
```

(o il percorso che si preferisce: nessuno script assume una posizione fissa).

### 2. Configura `.env` di produzione

```bash
cp .env.example .env
```

Variabili **da cambiare rispetto al default di sviluppo** prima di avviare qualunque
container:

| Variabile | Valore atteso in produzione |
| --- | --- |
| `SECRET_KEY` | Stringa casuale lunga, generata una tantum, mai riusata da sviluppo (`python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | `False` — in realtà ignorato: `config/settings/prod.py` forza `DEBUG = False` a prescindere da questa variabile, ma è comunque buona norma allinearla |
| `ALLOWED_HOSTS` | I domini reali, es. `segreteria.agescihirpinia.it,catello.agescihirpinia.it` |
| `CSRF_TRUSTED_ORIGINS` | Gli stessi domini con schema, es. `https://segreteria.agescihirpinia.it,https://catello.agescihirpinia.it` |
| `POSTGRES_PASSWORD` | Password reale, non `cambiami` |
| `POSTGRES_HOST` | **Non serve impostarlo**: `compose.prod.yaml` lo forza a `db` (il nome del servizio PostgreSQL nella rete Docker interna), sovrascrivendo qualunque valore in `.env` |
| `DJANGO_SETTINGS_MODULE` | **Non serve impostarlo**: `compose.prod.yaml` lo forza a `config.settings.prod` allo stesso modo |
| `EMAIL_PROVIDER` e le variabili del provider scelto | Vedi [`docs/email/README.md`](email/README.md) — `console`/`locmem` non vanno mai usati in produzione |
| `SITE_URL` | `https://segreteria.agescihirpinia.it` — **non presente in `.env.example`**, va aggiunta a mano: usata per costruire i link assoluti nelle email (attivazione, recupero OTP). Se assente, `config/settings/base.py` la fa cadere su `http://localhost:8000`, che produce link rotti nelle email reali. |

Variabili opzionali, lette solo da `config/settings/prod.py` o dall'entrypoint, anch'esse
assenti da `.env.example` (aggiungerle solo se serve cambiare il default):

| Variabile | Default | Effetto |
| --- | --- | --- |
| `DJANGO_SECURE_SSL_REDIRECT` | `False` | Redirect forzato HTTP→HTTPS. **Attivare solo dopo** aver messo un reverse proxy TLS reale davanti all'app: altrimenti l'health check e ogni accesso diretto vanno in loop di redirect |
| `DJANGO_SESSION_COOKIE_SECURE` | `False` | Cookie di sessione solo su HTTPS — stessa avvertenza |
| `DJANGO_CSRF_COOKIE_SECURE` | `False` | Cookie CSRF solo su HTTPS — stessa avvertenza |
| `GUNICORN_WORKERS` | `3` | Numero di worker Gunicorn (`docker/entrypoint.sh`) |
| `GUNICORN_TIMEOUT` | `120` | Timeout per richiesta, in secondi |

### 3. Scegli il reverse proxy

```bash
./configure-prod.sh
```

Lo script è **idempotente e non esegue mai comandi con privilegi elevati** (niente
`sudo`/`systemctl`/`apt`): genera solo file di configurazione, mai azioni di sistema.
Richiede che `.env` esista già (fallisce con un messaggio chiaro altrimenti). Propone tre
opzioni:

- **`nginx-docker`** — genera `docker/nginx/catello.conf` e `compose.prod.nginx.yaml`
  (override che aggiunge il servizio `nginx` a `compose.prod.yaml`). Da avviare con:

  ```bash
  docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d
  ```

- **`nginx-host`** — genera `deploy/nginx.conf.example`: un vhost nginx per un host che
  gestisce il reverse proxy **fuori** da Docker. Va copiato manualmente in
  `/etc/nginx/sites-available/`, abilitato, verificato (`nginx -t`) e ricaricato — lo
  script non lo fa, solo genera il file. `compose.prod.yaml` (senza override) espone
  comunque l'app su `127.0.0.1:8000`, pronta per essere raggiunta dal proxy sull'host.

- **`apache-host`** — stesso principio di `nginx-host`, ma genera
  `deploy/apache.conf.example` (richiede `mod_proxy`/`mod_proxy_http` abilitati:
  `a2enmod proxy proxy_http`).

La scelta fatta si salva in `.deploy-config` (non versionato). Per cambiarla:

```bash
./configure-prod.sh --force
# oppure, senza il menu interattivo:
./configure-prod.sh --proxy=nginx-docker --force
```

**Nessuna delle tre opzioni configura TLS**: sono tutte bozze HTTP semplici, da
completare con un certificato reale (es. certbot) prima di un go-live. Solo dopo aver
verificato che HTTPS funziona attivare `DJANGO_SECURE_SSL_REDIRECT` e i cookie `*_SECURE`
in `.env`.

### 4. Costruisci e avvia i container

Con `nginx-docker`:

```bash
docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d --build
```

Con `nginx-host`/`apache-host` (o senza reverse proxy in Docker):

```bash
docker compose -f compose.prod.yaml up -d --build
```

Al primo avvio, `docker/entrypoint.sh` esegue automaticamente, in quest'ordine:

1. `manage.py migrate --noinput`
2. `manage.py collectstatic --noinput`
3. Avvio di `gunicorn` su `0.0.0.0:8000`, con `GUNICORN_WORKERS`/`GUNICORN_TIMEOUT`

Nessuno di questi tre passi va eseguito a mano: succede ad ogni avvio del container,
migrazioni comprese (idempotenti per costruzione).

### 5. Passi manuali del primo deploy

Due operazioni **non** sono nell'entrypoint perché non idempotenti o perché richiedono
interazione, e vanno eseguite una sola volta a mano dopo il primo `up -d`:

```bash
# Tabella della cache (backend "db" in produzione): fallisce se rieseguita, per
# questo NON è nell'entrypoint — altrimenti romperebbe ogni riavvio successivo.
docker compose -f compose.prod.yaml exec web python manage.py createcachetable

# Primo account amministratore
docker compose -f compose.prod.yaml exec web python manage.py createsuperuser
```

### 6. Verifica

```bash
docker compose -f compose.prod.yaml ps        # entrambi i servizi "healthy"/"running"
docker compose -f compose.prod.yaml logs -f web
curl -I http://127.0.0.1:8000/                # dall'host, se non c'è ancora un proxy davanti
```

---

## Operazioni ricorrenti in produzione

### Redeploy di una nuova versione

```bash
cd /opt/catello
git pull
docker compose -f compose.prod.yaml up -d --build
```

Non serve fermare i container prima (`up -d --build` ricrea solo l'immagine e il
servizio `web`, `db` resta invariato) né rieseguire i passi manuali del punto 5: sono
one-shot, non per-versione. Le migrazioni della nuova versione partono da sole
nell'entrypoint.

### Backup e restore di PostgreSQL

```bash
# Backup
docker compose -f compose.prod.yaml exec db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup_$(date +%F).sql

# Restore (su un database vuoto)
docker compose -f compose.prod.yaml exec -T db \
  psql -U "$POSTGRES_USER" "$POSTGRES_DB" < backup_2026-08-21.sql
```

I dati di PostgreSQL vivono nel volume Docker `postgres_data`, non in un bind mount: un
`docker compose down` (senza `-v`) non li tocca; solo `-v` li cancella. Non eseguire mai
`docker compose down -v` in produzione senza un backup verificato.

### Log

```bash
docker compose -f compose.prod.yaml logs -f web      # stdout/stderr del container
tail -f /srv/catello/log/catello.log                  # log applicativo su file (rotazione automatica, 5×10MB)
```

### Riavvio / arresto

```bash
docker compose -f compose.prod.yaml restart web   # riavvia solo l'app, utile dopo un cambio in .env
docker compose -f compose.prod.yaml down           # ferma tutto, il volume postgres_data resta
```

Dopo una modifica a `.env`, `restart` non basta se la variabile è letta solo in fase di
build (nessuna, oggi, lo è): per le variabili d'ambiente a runtime `restart` è
sufficiente, Compose rilegge `.env` ad ogni comando.

---

## Risoluzione problemi comuni

| Sintomo | Causa probabile |
| --- | --- |
| `docker compose` non trovato / `docker-compose: command not found` | Serve il plugin Compose v2 (`docker compose`), non il binario standalone `docker-compose` v1 |
| `mise run db-up` fallisce con la porta 5432 occupata | Un altro PostgreSQL (locale o un'altra istanza Docker) sta già ascoltando su 5432; fermalo o cambia la porta esposta in `compose.yaml` |
| L'app in produzione risponde ma reindirizza in loop su HTTPS | `DJANGO_SECURE_SSL_REDIRECT=True` senza un reverse proxy TLS reale davanti: disattivarlo finché TLS non è configurato |
| Le email non partono in produzione | `EMAIL_PROVIDER` ancora su `console`/`locmem` (validi solo per sviluppo/test), oppure le librerie `gmail`/`microsoft` mancanti nell'immagine — vedi [`docs/email/README.md`](email/README.md) |
| `createcachetable` fallisce con "la tabella esiste già" | È già stato eseguito: comando non idempotente per natura, va lanciato una sola volta per installazione, non ad ogni deploy |
| I file statici non si vedono (404 su `/static/...`) dietro `nginx-docker` | `docker/nginx/catello.conf` punta a `/srv/catello/static/`: verificare che la directory sul host esista e coincida con il volume montato in `compose.prod.yaml` |
| I test locali su macOS falliscono sul rendering PDF | Librerie WeasyPrint (Pango/Cairo) non nel percorso di link dinamico di Homebrew: eseguire con `DYLD_LIBRARY_PATH=/opt/homebrew/lib`, non serve in Docker/CI |
