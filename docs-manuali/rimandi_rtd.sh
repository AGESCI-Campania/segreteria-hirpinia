#!/bin/sh
# Read the Docs (.readthedocs.yaml, post_build): i tre manuali di voto
# condividono docs-manuali/voto/ con un'introduzione diversa per ciascuno
# (index-banco.md…) e non hanno index.html alla radice. Un rimando tiene
# validi i link brevi assemblea/<manuale>/. Uso: rimandi_rtd.sh <cartella html>
set -eu
base="$1/assemblea"
rimando() {
    printf '<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url=%s/"><a href="%s/">%s</a>\n' \
        "$2" "$2" "$3" > "$base/$1/index.html"
}
rimando banco index-banco "Manuale per il banco e i seggi"
rimando voto-app index-app "Manuale di voto in app"
rimando voto-seggio index-seggio "Manuale di voto al seggio"
