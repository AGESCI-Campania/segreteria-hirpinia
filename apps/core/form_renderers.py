from pathlib import Path

import django.forms.renderers
from django.conf import settings
from django.forms.renderers import DjangoTemplates
from django.utils.functional import cached_property

DJANGO_FORMS_TEMPLATES_DIR = Path(django.forms.renderers.__file__).resolve().parent / "templates"


class TemaFormRenderer(DjangoTemplates):
    """Renderer dei widget di form: cerca prima gli override Bootstrap del progetto
    (``templates/django/forms/``), poi ricade sui template di default di Django."""

    @cached_property
    def engine(self):
        return self.backend(
            {
                "APP_DIRS": True,
                "DIRS": [Path(settings.BASE_DIR) / "templates", DJANGO_FORMS_TEMPLATES_DIR],
                "NAME": "catelloforms",
                "OPTIONS": {},
            }
        )
