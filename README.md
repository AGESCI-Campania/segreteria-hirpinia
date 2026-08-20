# Catello

[![build](https://github.com/AGESCI-Campania/catello-hirpinia/actions/workflows/ci.yml/badge.svg)](https://github.com/AGESCI-Campania/catello-hirpinia/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-6.0%2B-092E20.svg?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%2B-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Bootstrap](https://img.shields.io/badge/Bootstrap-5.3-7952B3.svg?logo=bootstrap&logoColor=white)](https://getbootstrap.com/)
[![uv](https://img.shields.io/badge/packaged%20with-uv-DE5FE9.svg?logo=uv&logoColor=white)](https://github.com/astral-sh/uv)
[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Version](https://img.shields.io/badge/version-0.1.0-informational.svg)](pyproject.toml)

Piattaforma di segreteria della **AGESCI Zona Hirpinia** (Regione Campania).

Catello gestisce l'anagrafica dei capi della Zona e il contributo annuale per la
partecipazione ai campi di formazione. Usa lo stack e il tema grafico delle piattaforme
regionali AGESCI Campania, con autenticazione locale autonoma (non collegata a SSO).

## Moduli

| Modulo | Contenuto |
| --- | --- |
| **Anagrafica** | Importazione dei capi dall'export CSV "Ricerca Soci" di Buona Caccia e degli incarichi in unità dai PDF di autorizzazione dei gruppi; esportazione in xlsx/csv con filtri per unità, ruolo e livello FoCa |
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

## Produzione

Deploy interamente dockerizzato tranne il reverse proxy, selezionabile con
`./configure-prod.sh` (nginx in Docker, nginx su host, Apache su host).

Domini: `segreteria.agescihirpinia.it` (primario), `catello.agescihirpinia.it` (alias).

```bash
./configure-prod.sh
docker compose -f compose.prod.yaml up -d
```

Se `./configure-prod.sh` genera l'opzione `nginx-docker`, avviare invece con:

```bash
docker compose -f compose.prod.yaml -f compose.prod.nginx.yaml up -d
```

**Al primo deploy**, oltre all'avvio, va creata una tantum la tabella della cache di
produzione (comando non idempotente, non incluso in `docker/entrypoint.sh`):

```bash
docker compose -f compose.prod.yaml exec web python manage.py createcachetable
```

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
- [`docs/email/`](docs/email/README.md) — guide passo-passo per configurare ciascun
  provider di invio email (SMTP, Gmail, Microsoft Graph)
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
