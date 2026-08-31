# Catello

[![build](https://github.com/AGESCI-Campania/catello-hirpinia/actions/workflows/ci.yml/badge.svg)](https://github.com/AGESCI-Campania/catello-hirpinia/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0%2B-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%2B-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3.svg?logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![uv](https://img.shields.io/badge/packaged%20with-uv-DE5FE9.svg?logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Version](https://img.shields.io/badge/version-1.0.1-informational.svg)](pyproject.toml)

Piattaforma di segreteria della **AGESCI Zona Hirpinia** (Regione Campania).

Catello gestisce l'anagrafica dei capi della Zona e il contributo annuale per la
partecipazione ai campi di formazione. Usa lo stack e il tema grafico delle piattaforme
regionali AGESCI Campania, con autenticazione locale autonoma (non collegata a SSO).

## Moduli

| Modulo | Contenuto |
| --- | --- |
| **Anagrafica** | Importazione dei capi dall'export CSV "Ricerca Soci" di Buona Caccia e degli incarichi in unità dai PDF di autorizzazione dei gruppi; esportazione in xlsx/csv con filtri per unità, branca, ruolo e livello FoCa |
| **Contributo Formazione Capi** | Inserimento delle partecipazioni ai campi da parte dei gruppi (manuale o da file xlsx), valutazione del Comitato di Zona, calcolo automatico del contributo, generazione del file per i bonifici |

## Requisiti

- Python ≥ 3.14
- PostgreSQL ≥ 17
- [`uv`](https://github.com/astral-sh/uv) e [`mise`](https://mise.jdx.dev/)
- Docker e Docker Compose (per il database in sviluppo e per il deploy)

## Avvio in sviluppo

```bash
git clone https://github.com/AGESCI-Campania/catello-hirpinia.git
cd catello-hirpinia

mise install                 # Python e uv alla versione richiesta
uv sync                      # crea .venv e installa le dipendenze
cp .env.example .env         # e personalizza i valori

mise run db-up               # PostgreSQL in Docker
mise run migrate
uv run python manage.py createsuperuser
mise run dev
```

Applicazione su `http://127.0.0.1:8000/`.

Guida completa (task disponibili, reset del database, troubleshooting):
[`docs/docker.md`](docs/docker.md).

### Mailpit in sviluppo (opzionale)

Alternativa a `EMAIL_PROVIDER=console` (default) con interfaccia web invece di
terminale/file: utile per leggere il rendering HTML reale delle email.

```bash
mise run mailpit-up          # docker compose up -d mailpit
```

In `.env`:

```bash
EMAIL_PROVIDER=smtp
EMAIL_HOST=localhost
EMAIL_PORT=1025
EMAIL_USE_TLS=False
EMAIL_USE_SSL=False
```

Riavviare `mise run dev`, poi leggere le email inviate su `http://localhost:8025`
(mai consegnate davvero). `mise run mailpit-down` per fermarlo. Dettagli:
[`docs/email/sviluppo-e-test.md`](docs/email/sviluppo-e-test.md).

## Task disponibili

| Comando | Descrizione |
| --- | --- |
| `mise run dev` | Server di sviluppo |
| `mise run migrate` | Applica le migrazioni |
| `mise run makemigrations` | Genera le migrazioni |
| `mise run test` | Suite di test (pytest) |
| `mise run lint` | ruff + black + mypy |
| `mise run format` | Formattazione automatica |
| `mise run db-up` / `db-down` | PostgreSQL in Docker |
| `mise run mailpit-up` / `mailpit-down` | Mailpit in Docker (opzionale, alternativa a `console` con interfaccia web) |

## Produzione

Deploy interamente dockerizzato tranne il reverse proxy, selezionabile con
`./configure-prod.sh` (nginx in Docker, nginx su host, Apache su host).

Domini: `segreteria.agescihirpinia.it` (primario), `catello.agescihirpinia.it` (alias).

```bash
cp .env.example .env         # e personalizza SECRET_KEY, ALLOWED_HOSTS, POSTGRES_*, SITE_URL...
./configure-prod.sh
docker compose -f compose.prod.yaml up -d --build

# al primo deploy soltanto, dopo l'avvio:
docker compose -f compose.prod.yaml exec web python manage.py createcachetable
docker compose -f compose.prod.yaml exec web python manage.py createsuperuser
```

Se `./configure-prod.sh` genera l'opzione `nginx-docker`, avviare invece con:

```bash
docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d --build
```

Guida completa (variabili d'ambiente, TLS, redeploy, backup, troubleshooting):
[`docs/docker.md`](docs/docker.md).

### Mailpit in produzione (opzionale)

Interruttore per verificare l'invio reale senza recapitare email vere, senza toccare
`EMAIL_PROVIDER` né riavviare `web` — si attiva e disattiva da Impostazioni. Il
container non parte con `up -d --build` sopra: è dietro il profilo Compose `mailpit`.

```bash
docker compose -f compose.prod.yaml up -d mailpit   # solo se serve l'interruttore
```

In `.env`:

```bash
EMAIL_MAILPIT_HOST=mailpit   # nome del servizio Compose
EMAIL_MAILPIT_PORT=1025
```

poi riavviare `web` (`docker compose -f compose.prod.yaml up -d --build web`) perché
legga le variabili, e infine attivare "Invia le email su Mailpit invece del provider
configurato" in Amministrazione → Impostazioni. L'interfaccia web di Mailpit resta solo
su `127.0.0.1:8025` (mai esposta pubblicamente): consultarla via tunnel SSH
(`ssh -L 8025:localhost:8025 utente@server`). **Attenzione**: mentre attivo, nessuna
email reale (reset password, OTP, inviti) raggiunge i destinatari — ricordarsi di
disattivarlo a verifica conclusa. Dettagli e rischi:
[`docs/email/mailpit-override-produzione.md`](docs/email/mailpit-override-produzione.md).

## Accessi

Autenticazione locale con django-allauth (email + MFA), senza SSO. Gli account possono
essere attivati dalla segreteria o dai Responsabili di Zona con un invito OTP via email,
anche massivo, oppure registrati in autonomia dai gruppi in allowlist. Chi detiene un
ruolo può delegarlo ad altri utenti, con scadenza obbligatoria; gli amministratori
possono impersonare altri utenti con tracciamento della doppia identità.

## Invio email

Il provider si seleziona con `EMAIL_PROVIDER` in `.env`:

| Valore | Autenticazione |
| --- | --- |
| `console` / `locmem` | sviluppo e test |
| `smtp` | password + STARTTLS o SSL |
| `gmail_service_account` | service account Google con delega di dominio |
| `gmail_oauth` | OAuth utente, scope `gmail.send` |
| `microsoft_graph` | OAuth client credentials, permesso `Mail.Send` |

Le dipendenze del provider sono extra opzionali:

```bash
uv sync --extra gmail        # google-auth
uv sync --extra microsoft    # msal
```

Dettagli e configurazione lato Google/Microsoft: § 8 del documento di progettazione.

In sviluppo, `smtp` puntato su Mailpit locale (`mise run mailpit-up`) è un'alternativa a
`console` con interfaccia web su `http://localhost:8025` — vedi
[`docs/email/sviluppo-e-test.md`](docs/email/sviluppo-e-test.md). In produzione, un
interruttore separato in Impostazioni può reindirizzare temporaneamente ogni email su
Mailpit indipendentemente dal provider scelto — vedi
[`docs/email/mailpit-override-produzione.md`](docs/email/mailpit-override-produzione.md).

## Struttura

```
apps/
├── core/            template base, utility condivise
│   └── email/       backend di invio (SMTP, Gmail, Microsoft Graph)
├── organizzazione/  Gruppo, anno associativo, allowlist
├── accounts/        utenti, ruoli, deleghe, permessi
├── anagrafica/      capi, incarichi in unità, importazioni
│   └── parser/      parser dei PDF di autorizzazione e dei CSV Buona Caccia
└── contributi/      campagne, partecipazioni, calcolo, bonifici
```

> I file di anagrafica reali (CSV di Buona Caccia, PDF di autorizzazione) contengono
> dati personali e **non vanno mai versionati**: `data/`, `uploads/` e le fixture PDF e
> CSV sono esclusi in `.gitignore`.

## Documentazione

- [`docs/Catello_Progettazione.md`](docs/Catello_Progettazione.md) — documento di
  progettazione, fonte di verità per modello dati, regole di dominio e decisioni
  architetturali
- [`docs/docker.md`](docs/docker.md) — guida completa a installazione, configurazione ed
  esecuzione con Docker, in sviluppo e in produzione
- [`docs/email/`](docs/email/README.md) — guide passo-passo per configurare ciascun
  provider di invio email (SMTP, Gmail, Microsoft Graph)
- [`docs/TODO.md`](docs/TODO.md) — elenco delle modifiche da fare emerse durante il beta
  testing
- [`CLAUDE.md`](CLAUDE.md) — vincoli operativi per lo sviluppo assistito
- [`SETUP_PYCHARM.md`](SETUP_PYCHARM.md) — configurazione dell'IDE

## Crediti

Il parser dei PDF di autorizzazione in `apps/anagrafica/parser/` deriva dal progetto
`autorizzazioni-agesci` v1.0.1, dello stesso autore e con la stessa licenza.

## Licenza

Codice distribuito con licenza [MIT](LICENSE), copyright
[Andrea Bruno](https://bruand81.it).

Marchi, emblemi e palette AGESCI restano proprietà dell'Associazione e sono soggetti al
regolamento associativo sull'uso del marchio.
