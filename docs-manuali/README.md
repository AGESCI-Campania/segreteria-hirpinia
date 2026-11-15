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

## Read the Docs

I quattro manuali sono pubblicati sullo stesso sito della guida dei capigruppo, nella
sottocartella `assemblea/` (`.readthedocs.yaml`, passo `post_build`), e la guida li collega
dal menu «Assemblea di Zona». La versione `stable` segue l'ultima release:

| Manuale | Pagina | PDF |
| --- | --- | --- |
| Gestione | `https://segreteria-hirpinia.readthedocs.io/it/stable/assemblea/gestione/` | `…/assemblea/gestione/pdf/manuale-gestione.pdf` |
| Banco e seggi | `…/it/stable/assemblea/banco/` | `…/assemblea/banco/pdf/manuale-banco.pdf` |
| Voto in app | `…/it/stable/assemblea/voto-app/` | `…/assemblea/voto-app/pdf/manuale-voto-app.pdf` |
| Voto al seggio | `…/it/stable/assemblea/voto-seggio/` | `…/assemblea/voto-seggio/pdf/manuale-voto-seggio.pdf` |

Lo stile comune dei PDF (palette verde della Zona, limiti delle immagini) è in
`pdf/styles.scss`, usato anche dalla guida dei capigruppo. Alla pubblicazione di una
release il workflow `release-manuale.yml` genera e allega **solo i manuali cambiati**
dalla release precedente (`manuali_cambiati.py`): testi, pagine descritte in
`pagine.toml`, configurazione MkDocs, stile comune dei PDF o logo; per la guida dei
capigruppo `docs-utente/` e `mkdocs.yml`. Una release che non tocca nessun manuale non ha
PDF allegati: la versione sempre aggiornata resta quella di Read the Docs (`stable`).
