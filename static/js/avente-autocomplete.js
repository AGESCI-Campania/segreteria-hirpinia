(function () {
  "use strict";

  // Ricerca di un avente diritto nell'elenco dell'assemblea, per i moduli della
  // pagina dell'assemblea (comitato elettorale, ufficio di presidenza). Ogni
  // contenitore [data-avente-autocomplete] porta l'URL della ricerca e contiene
  // il campo di testo, l'elenco dei risultati e il campo nascosto con l'id. Il
  // perimetro lo decide la view; qui solo cosa mostrare e quale id inviare.
  function attiva(contenitore) {
    var input = contenitore.querySelector(".js-cerca");
    var lista = contenitore.querySelector(".js-risultati");
    var selezionato = contenitore.querySelector(".js-selezionato");
    var hidden = contenitore.querySelector('input[type="hidden"]');
    if (!input || !lista || !hidden) {
      return;
    }
    window.AgesciAutocomplete.avvia({
      url: contenitore.dataset.aventeAutocomplete,
      input: input,
      lista: lista,
      onInput: function () {
        hidden.value = "";
        if (selezionato) {
          selezionato.textContent = "";
        }
      },
      renderVoce: function (risultato) {
        return risultato.cognome + " " + risultato.nome + " (" + risultato.gruppo + ")";
      },
      onSeleziona: function (risultato) {
        hidden.value = risultato.id;
        input.value = risultato.cognome + " " + risultato.nome;
        if (selezionato) {
          selezionato.textContent = "Selezionato: " + risultato.gruppo;
        }
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-avente-autocomplete]").forEach(attiva);
  });
})();
