# Fixture PDF per i test di integrazione

I PDF di autorizzazione contengono dati personali di soci reali e **non vanno
versionati** (`data/`, `uploads/` e questa cartella sono in `.gitignore` per il
contenuto binario).

Per eseguire i test di integrazione del parser, copia i PDF di un anno in una
sottocartella con l'anno come nome (`parse_year()` si aspetta sottocartelle per anno):

```
apps/anagrafica/tests/fixtures/pdf/
└── 2026/
    ├── AutorizzazionePrimariaAvellino1.pdf
    ├── AutorizzazioneSecondariaAvellino3.pdf
    └── ...
```

In assenza dei file i test si auto-escludono (`pytest.mark.skipif`), quindi la CI
resta verde. I valori attesi nei test (218 record, 12 gruppi) si riferiscono al
campione 2026: se usi un campione diverso, aggiornali.
