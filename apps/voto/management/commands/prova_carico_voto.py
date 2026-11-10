"""Dati per la prova di carico del voto (docs/plan_voto.md, V6).

Crea un'assemblea di prova con il voto di Catello, N aventi diritto presenti,
una seduta costituita e un'elezione con l'urna aperta, emette N codici e li
scrive **in chiaro** in un file per `scripts/carico_voto.py`. Per questo
funziona solo con DEBUG attivo: mai in produzione, mai su dati reali.

    manage.py prova_carico_voto prepara --votanti 400 --file /tmp/codici.txt
    manage.py prova_carico_voto verifica <assemblea>
    manage.py prova_carico_voto elimina <assemblea>
"""

from __future__ import annotations

import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.assemblee.models import (
    Appello,
    Assemblea,
    AventeDiritto,
    Candidato,
    OrigineAvente,
    Presenza,
    Provenienza,
    Seduta,
    SistemaVoto,
    TipoAppello,
    TipoAssemblea,
    TipoVotazione,
    Votazione,
)
from apps.organizzazione.models import Gruppo
from apps.voto import codici
from apps.voto.models import CodiceVoto, Scheda, Votante

GRUPPO_PROVA = "E9998"
ANNO_PROVA = 2099


class Command(BaseCommand):
    help = "Prepara, verifica o elimina i dati della prova di carico del voto (solo DEBUG)."

    def add_arguments(self, parser):
        sotto = parser.add_subparsers(dest="azione", required=True)
        prepara = sotto.add_parser("prepara")
        prepara.add_argument("--votanti", type=int, default=400)
        prepara.add_argument("--file", required=True, help="Dove scrivere i codici in chiaro.")
        for nome in ("verifica", "elimina"):
            sotto.add_parser(nome).add_argument("assemblea", type=int)

    def handle(self, *args, **opzioni):
        if not settings.DEBUG:
            raise CommandError("Solo con DEBUG attivo: i codici finiscono in chiaro in un file.")
        getattr(self, f"_{opzioni['azione']}")(opzioni)

    @transaction.atomic
    def _prepara(self, opzioni):
        votanti = opzioni["votanti"]
        gruppo, _ = Gruppo.objects.get_or_create(
            codice=GRUPPO_PROVA, defaults={"nome": "PROVA CARICO VOTO"}
        )
        assemblea = Assemblea.objects.create(
            tipo=TipoAssemblea.PRIMAVERILE, anno_scout=ANNO_PROVA, sistema_voto=SistemaVoto.CATELLO
        )
        aventi = AventeDiritto.objects.bulk_create(
            AventeDiritto(
                assemblea=assemblea,
                nome=f"Votante{i}",
                cognome="Prova",
                gruppo=gruppo,
                origine=OrigineAvente.MANUALE,
                provenienza=Provenienza.NON_NOTA,
                anno_censimento=ANNO_PROVA,
                vota_in_app=True,
            )
            for i in range(votanti)
        )
        ora = timezone.now()
        seduta = Seduta.objects.create(
            assemblea=assemblea,
            convocazione=Seduta.Convocazione.PRIMA,
            data=datetime.date.today(),
            aperta_il=ora,
            costituita=True,
        )
        appello = Appello.objects.create(seduta=seduta, numero=1, tipo=TipoAppello.INGRESSO)
        Presenza.objects.bulk_create(Presenza(appello=appello, avente=a) for a in aventi)
        votazione = Votazione.objects.create(
            seduta=seduta,
            tipo=TipoVotazione.ELEZIONE,
            oggetto="Prova di carico",
            incarico="Prova",
            presenti=votanti,
            aventi_diritto=votanti,
            aperta_in_app_il=ora,
        )
        for nome in ("Candidato A", "Candidato B", "Candidato C"):
            Candidato.objects.create(votazione=votazione, nome=nome)
        in_chiaro = [codici.genera() for _ in aventi]
        CodiceVoto.objects.bulk_create(
            CodiceVoto(seduta=seduta, avente=a, hash=codici.calcola_hash(c))
            for a, c in zip(aventi, in_chiaro, strict=True)
        )
        Path(opzioni["file"]).write_text("\n".join(in_chiaro) + "\n", encoding="utf-8")
        self.stdout.write(
            f"Assemblea di prova {assemblea.pk}: {votanti} codici in {opzioni['file']}."
        )

    def _verifica(self, opzioni):
        votazione = Votazione.objects.get(seduta__assemblea_id=opzioni["assemblea"])
        schede = Scheda.objects.filter(votazione=votazione).count()
        votanti = Votante.objects.filter(votazione=votazione).count()
        esito = "OK" if schede == votanti else "INCOERENTE"
        self.stdout.write(f"Schede {schede}, votanti {votanti}: {esito}.")

    @transaction.atomic
    def _elimina(self, opzioni):
        assemblea = Assemblea.objects.get(pk=opzioni["assemblea"], anno_scout=ANNO_PROVA)
        Votante.objects.filter(votazione__seduta__assemblea=assemblea).delete()
        assemblea.delete()
        self.stdout.write("Assemblea di prova eliminata.")
