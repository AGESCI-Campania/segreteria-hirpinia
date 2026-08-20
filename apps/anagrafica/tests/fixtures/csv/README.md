# Fixture CSV per i test di integrazione

Il CSV "Ricerca Soci" di Buona Caccia contiene dati personali di soci reali e **non va
versionato** (`data/`, `uploads/` e questa cartella sono in `.gitignore` per il
contenuto CSV).

I test automatici del parser e dell'import (`test_parser_buonacaccia_unit.py`,
`test_importazione_buonacaccia.py`) usano solo CSV sintetici costruiti inline: non
dipendono da alcuna fixture reale e restano verdi anche a repository appena clonato.

Questa cartella serve solo per una verifica manuale del formato con un file reale, ad
esempio con il comando di import in modalità anteprima:

```
apps/anagrafica/tests/fixtures/csv/
└── 2026/
    └── RicercaSoci.csv
```

```bash
uv run python manage.py import_buonacaccia_csv \
  apps/anagrafica/tests/fixtures/csv/2026/RicercaSoci.csv \
  --utente segreteria@campania.agesci.it
```

**Anonimizza sempre il file prima di copiarlo qui**: nome, cognome, codice fiscale,
email, cellulare e indirizzo di soci reali non devono mai comparire, nemmeno
localmente, in un file che potrebbe finire per errore in un commit o in un allegato.
