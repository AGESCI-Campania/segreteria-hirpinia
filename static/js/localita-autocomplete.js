(function () {
  "use strict";

  // Autocompletamento località per le righe auto (D-52/D-53), applicato a
  // due campi indipendenti (partenza/arrivo) tramite il prefisso passato in
  // data-prefisso su ciascuno script. La ricerca/debounce/fetch è condivisa
  // (ricerca-autocomplete-comune.js, caricato prima di questo script).

  function etichetta(risultato) {
    return risultato.dettaglio ? risultato.nome + " (" + risultato.dettaglio + ")" : risultato.nome;
  }

  function attiva(prefisso) {
    var url = document.querySelector('script[data-url-autocomplete][data-prefisso="' + prefisso + '"]').dataset.urlAutocomplete;
    var input = document.getElementById("ricerca-localita-" + prefisso);
    var lista = document.getElementById("ricerca-localita-" + prefisso + "-risultati");
    var hidden = document.getElementById("id_localita_" + prefisso);
    if (!url || !input || !lista || !hidden) {
      return;
    }

    window.AgesciAutocomplete.avvia({
      url: url,
      input: input,
      lista: lista,
      onInput: function () {
        hidden.value = "";
      },
      renderVoce: etichetta,
      onSeleziona: function (risultato) {
        hidden.value = risultato.id;
        input.value = etichetta(risultato);
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("script[data-url-autocomplete][data-prefisso]").forEach(function (script) {
      attiva(script.dataset.prefisso);
    });
  });
})();
