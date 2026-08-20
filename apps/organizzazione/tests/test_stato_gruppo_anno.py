import pytest
from django.db import IntegrityError, transaction

from apps.organizzazione.models import Gruppo, StatoGruppoAnno

pytestmark = pytest.mark.django_db


def test_unique_together_gruppo_anno_scout():
    gruppo = Gruppo.objects.create(codice="E0133", nome="AVELLINO 1")
    StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=True)
    with pytest.raises(IntegrityError), transaction.atomic():
        StatoGruppoAnno.objects.create(gruppo=gruppo, anno_scout=2026, attivo=False)
