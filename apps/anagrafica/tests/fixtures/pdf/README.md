# Fixture PDF per i test di integrazione

I PDF di autorizzazione contengono dati personali di soci reali e **non vanno
versionati** (`data/`, `uploads/` e questa cartella sono in `.gitignore` per il
contenuto binario).

Per eseguire i test di integrazione del parser, copia qui i PDF di un anno:

```
apps/anagrafica/tests/fixtures/pdf/
├── AutorizzazionePrimariaAvellino1.pdf
├── AutorizzazioneSecondariaAvellino3.pdf
└── ...
```

In assenza dei file i test si auto-escludono (`pytest.mark.skipif`), quindi la CI
resta verde. I valori attesi nei test (218 record, 12 gruppi) si riferiscono al
campione 2026: se usi un campione diverso, aggiornali.
