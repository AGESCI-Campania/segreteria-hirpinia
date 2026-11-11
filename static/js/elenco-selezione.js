(function () {
  "use strict";

  // Elenco degli aventi diritto: la casella in testa alla colonna seleziona
  // tutte le righe visibili (quelle del filtro corrente), e sopra la tabella
  // si vede quanti sono selezionati. Solo un aiuto: cosa eliminare lo decide
  // comunque il service layer.
  document.addEventListener("DOMContentLoaded", function () {
    var tutti = document.getElementById("seleziona-tutti");
    var conteggio = document.getElementById("conteggio-selezionati");
    var caselle = Array.prototype.slice.call(
      document.querySelectorAll('input[type="checkbox"][name="aventi"][form="form-elimina"]')
    );
    if (!tutti) {
      return;
    }
    if (!caselle.length) {
      tutti.disabled = true;
      return;
    }

    function aggiorna() {
      var selezionati = caselle.filter(function (casella) {
        return casella.checked;
      }).length;
      tutti.checked = selezionati === caselle.length;
      tutti.indeterminate = selezionati > 0 && selezionati < caselle.length;
      if (conteggio) {
        conteggio.hidden = selezionati === 0;
        conteggio.textContent =
          selezionati === 1 ? "1 avente diritto selezionato" : selezionati + " aventi diritto selezionati";
      }
    }

    tutti.addEventListener("change", function () {
      caselle.forEach(function (casella) {
        casella.checked = tutti.checked;
      });
      aggiorna();
    });
    caselle.forEach(function (casella) {
      casella.addEventListener("change", aggiorna);
    });
    aggiorna();
  });
})();
