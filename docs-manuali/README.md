# Manuali di voto e di gestione dell'assemblea

Sorgenti dei due manuali in PDF allegati a ogni release
(docs/plan_preparazione_assemblea.md, R11, D30–D35):

- `voto/` → **Manuale di voto** (`mkdocs-voto.yml`): elettori, banco e seggi;
- `gestione/` → **Manuale di gestione dell'assemblea** (`mkdocs-gestione.yml`): gestori,
  comitato elettorale, presidenza e segretario.

## Quando si aggiornano

Solo se cambiano le pagine che descrivono, elencate in `pagine.toml`. La CI avvisa (senza
bloccare) quando una di quelle cambia e il manuale no
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
le immagini in `voto/img/` e `gestione/img/`. Su macOS, per WeasyPrint, serve
`DYLD_LIBRARY_PATH=/opt/homebrew/lib` (già nel task).

## PDF

```bash
mise run manuali-build   # site-voto/pdf/manuale-voto.pdf, site-gestione/pdf/manuale-gestione.pdf
```

Lo stile comune dei PDF è in `pdf/styles.scss`. Alla pubblicazione di una release il
workflow `release-manuale.yml` genera e allega i due manuali insieme alla guida dei
capigruppo.
