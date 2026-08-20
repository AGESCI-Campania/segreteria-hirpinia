from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpRequest

from .models import Utente
from .permessi import ruoli_effettivi


class RuoloRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Consente l'accesso solo a chi detiene (diretto o per delega, salvo
    `ruoli_ammessi_solo_diretti`) uno dei ruoli in `ruoli_ammessi`."""

    request: HttpRequest
    ruoli_ammessi: frozenset[str] = frozenset()
    ruoli_ammessi_solo_diretti = False

    def test_func(self) -> bool:
        # LoginRequiredMixin garantisce l'autenticazione prima di test_func().
        assert isinstance(self.request.user, Utente)
        ruoli = ruoli_effettivi(self.request.user)
        if self.ruoli_ammessi_solo_diretti:
            ruoli = [r for r in ruoli if not r.is_delega]
        return any(r.tipo in self.ruoli_ammessi for r in ruoli)
