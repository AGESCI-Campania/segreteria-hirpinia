(function () {
  "use strict";

  // Wiring per "Nuova nota spese": la ricerca/debounce/fetch è condivisa
  // (ricerca-autocomplete-comune.js, caricato prima di questo script). Qui
  // non c'è un campo nascosto separato: il campo visibile
  // `beneficiario_codice_socio` è già il valore da inviare (testo libero,
  // validato lato server in NotaCreaView), la selezione ci scrive
  // direttamente il codice socio.

  function attivaAutocomplete(script) {
    var input = document.getElementById("id_beneficiario_codice_socio");
    var lista = document.getElementById("beneficiario-ricerca-risultati");
    var selezionato = document.getElementById("beneficiario-ricerca-selezionato");
    if (!input || !lista) {
      return;
    }

    window.AgesciAutocomplete.avvia({
      url: script.dataset.urlAutocomplete,
      input: input,
      lista: lista,
      onInput: function () {
        if (selezionato) {
          selezionato.textContent = "";
        }
      },
      renderVoce: function (risultato) {
        return (
          risultato.nome + " " + risultato.cognome + " (" + risultato.codice_socio + ") — " +
          risultato.gruppo
        );
      },
      onSeleziona: function (risultato) {
        input.value = risultato.codice_socio;
        if (selezionato) {
          selezionato.textContent =
            risultato.nome + " " + risultato.cognome + " — " + risultato.gruppo;
        }
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-url-autocomplete][src*='nota-spese-beneficiario']");
    if (script) {
      attivaAutocomplete(script);
    }
  });
})();
