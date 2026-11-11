(function () {
  "use strict";

  // Comitato elettorale: ricerca fra gli aventi diritto dell'assemblea. Il
  // perimetro lo decide la view; qui solo cosa mostrare e quale id inviare.
  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-url-autocomplete]");
    var input = document.getElementById("ricerca-comitato");
    var lista = document.getElementById("ricerca-comitato-risultati");
    var selezionato = document.getElementById("ricerca-comitato-selezionato");
    var hiddenAvente = document.getElementById("id_avente");
    if (!script || !input || !lista || !hiddenAvente) {
      return;
    }

    window.AgesciAutocomplete.avvia({
      url: script.dataset.urlAutocomplete,
      input: input,
      lista: lista,
      onInput: function () {
        hiddenAvente.value = "";
        if (selezionato) {
          selezionato.textContent = "";
        }
      },
      renderVoce: function (risultato) {
        return risultato.cognome + " " + risultato.nome + " (" + risultato.gruppo + ")";
      },
      onSeleziona: function (risultato) {
        hiddenAvente.value = risultato.id;
        input.value = risultato.cognome + " " + risultato.nome;
        if (selezionato) {
          selezionato.textContent = "Selezionato: " + risultato.gruppo;
        }
      },
    });
  });
})();
