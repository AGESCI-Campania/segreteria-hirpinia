# Configurazione PyCharm

## 1. Apertura del progetto

`File → Open` e seleziona la cartella `catello-hirpinia`.

## 2. Interprete Python

L'ambiente è gestito da `uv` tramite `mise`. Prima di configurare l'IDE, da terminale:

```bash
mise install
uv sync
```

Poi in PyCharm: `Settings → Project → Python Interpreter → Add Interpreter →
Add Local Interpreter → Select existing` e indica `.venv/bin/python` nella radice del
progetto.

Non usare "Poetry", "Pipenv" o la creazione automatica del virtualenv: l'ambiente è
già creato da `uv` e va solo selezionato.

## 3. Supporto Django

`Settings → Languages & Frameworks → Django`:

- **Enable Django Support**: sì
- **Django project root**: radice del progetto
- **Settings**: `config/settings/dev.py`
- **Manage script**: `manage.py`

## 4. Configurazione di esecuzione

`Run → Edit Configurations → + → Django Server`:

- **Host**: `127.0.0.1`, **Port**: `8000`
- **Environment variables**: `DJANGO_SETTINGS_MODULE=config.settings.dev`
- **Python interpreter**: `.venv` del progetto
- Spunta *Enable Django Debug Toolbar* se installata

Per i test, `+ → pytest`:

- **Target**: `apps`
- **Environment variables**: `DJANGO_SETTINGS_MODULE=config.settings.test`

## 5. Qualità del codice

`Settings → Tools → Black`: abilita "On save", con `.venv/bin/black`.

Per ruff installa il plugin *Ruff* e indica `.venv/bin/ruff`.

Larghezza righe: `Settings → Editor → Code Style → Hard wrap at 100`.

## 6. Database

`View → Tool Windows → Database → + → Data Source → PostgreSQL`, con i valori di `.env`
(default: host `localhost`, porta `5432`, database `catello`).

Avvia prima il container: `mise run db-up`.

## 7. Claude Code

Installa il plugin *Claude Code* dal marketplace JetBrains. Il file `CLAUDE.md` nella
radice viene letto automaticamente come contesto: contiene i vincoli di progetto e
rimanda a `docs/Catello_Progettazione.md` per le specifiche.
