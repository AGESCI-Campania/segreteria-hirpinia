(function () {
  "use strict";

  // «Aggiungi dall'anagrafica»: ricerca fra i censiti che si possono aggiungere
  // all'elenco. Il perimetro lo decide la view; qui solo cosa mostrare e quale
  // codice socio inviare.
  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-url-autocomplete]");
    var input = document.getElementById("ricerca-censito");
    var lista = document.getElementById("ricerca-censito-risultati");
    var selezionato = document.getElementById("ricerca-censito-selezionato");
    var hiddenCodice = document.getElementById("id_codice_socio");
    if (!script || !input || !lista || !hiddenCodice) {
      return;
    }

    window.AgesciAutocomplete.avvia({
      url: script.dataset.urlAutocomplete,
      input: input,
      lista: lista,
      onInput: function () {
        hiddenCodice.value = "";
        if (selezionato) {
          selezionato.textContent = "";
        }
      },
      renderVoce: function (risultato) {
        return risultato.cognome + " " + risultato.nome + " (" + risultato.gruppo + ")";
      },
      onSeleziona: function (risultato) {
        hiddenCodice.value = risultato.codice_socio;
        input.value = risultato.cognome + " " + risultato.nome;
        if (selezionato) {
          selezionato.textContent = "Selezionato: " + risultato.gruppo + " — " + risultato.codice_socio;
        }
      },
    });
  });
})();
