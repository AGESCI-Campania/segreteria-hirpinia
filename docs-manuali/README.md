# Manuali dell'assemblea

Sorgenti dei manuali in PDF allegati a ogni release
(docs/plan_preparazione_assemblea.md, R11, D30–D35):

| Manuale | Configurazione | Pagine |
| --- | --- | --- |
| **Manuale di voto in app** (dal telefono) | `mkdocs-voto-app.yml` | `voto/` |
| **Manuale di voto al seggio** | `mkdocs-voto-seggio.yml` | `voto/` |
| **Manuale per il banco e i seggi** | `mkdocs-banco.yml` | `voto/` |
| **Manuale di gestione dell'assemblea** | `mkdocs-gestione.yml` | `gestione/` |

I tre manuali di voto condividono la cartella `voto/`: le pagine comuni (codice di voto,
scheda, controllo del voto, problemi) esistono una volta sola e ogni manuale le sceglie
con il proprio `nav`. Nei testi la piattaforma si chiama «la piattaforma», mai con il nome
del progetto.

## Quando si aggiornano

Solo se cambiano le pagine che descrivono, elencate in `pagine.toml`. La CI avvisa (senza
bloccare) quando una di quelle cambia e la cartella del manuale no
(`verifica_aggiornamento.py`). Se nulla cambia, testo e schermate restano quelli della
release precedente.

## Schermate

Si rifanno tutte con un comando, su un database di test usa e getta con **dati
inventati** (mai dati reali di soci):

```bash
mise run manuali-schermate
```

Lo script (`test_schermate.py`) crea un'assemblea di esempio, la apre in Chrome senza
interfaccia (Selenium, già fra le dipendenze di sviluppo; serve Chrome installato) e salva
le immagini in `voto/img/` e `gestione/img/`; prova anche nel browser alcune funzioni
(accesso all'urna, voto, autocompletamento). Su macOS, per WeasyPrint, serve
`DYLD_LIBRARY_PATH=/opt/homebrew/lib` (già nel task).

## PDF

```bash
mise run manuali-build   # site-voto-app/, site-voto-seggio/, site-banco/, site-gestione/
```

Lo stile comune dei PDF (palette verde della Zona, limiti delle immagini) è in
`pdf/styles.scss`, usato anche dalla guida dei capigruppo. Alla pubblicazione di una
release il workflow `release-manuale.yml` genera e allega i quattro manuali insieme alla
guida dei capigruppo.
