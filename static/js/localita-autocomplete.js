(function () {
  "use strict";

  // Autocompletamento località per le righe auto (D-52/D-53): stesso
  // meccanismo di ricerca-socio-autocomplete.js (M14), applicato a due
  // campi indipendenti (partenza/arrivo) tramite il prefisso passato in
  // data-prefisso su ciascuno script.

  function attiva(prefisso) {
    var url = document.querySelector('script[data-url-autocomplete][data-prefisso="' + prefisso + '"]').dataset.urlAutocomplete;
    var input = document.getElementById("ricerca-localita-" + prefisso);
    var lista = document.getElementById("ricerca-localita-" + prefisso + "-risultati");
    var hidden = document.getElementById("id_localita_" + prefisso);
    if (!url || !input || !lista || !hidden) {
      return;
    }

    var timeoutId = null;
    var controllerCorrente = null;

    function nascondiLista() {
      lista.style.display = "none";
      lista.innerHTML = "";
    }

    function etichetta(risultato) {
      return risultato.dettaglio ? risultato.nome + " (" + risultato.dettaglio + ")" : risultato.nome;
    }

    function selezionaRisultato(risultato) {
      hidden.value = risultato.id;
      input.value = etichetta(risultato);
      nascondiLista();
    }

    function mostraRisultati(risultati) {
      lista.innerHTML = "";
      if (!risultati.length) {
        nascondiLista();
        return;
      }
      risultati.forEach(function (risultato) {
        var voce = document.createElement("li");
        voce.className = "list-group-item list-group-item-action";
        voce.style.cursor = "pointer";
        voce.textContent = etichetta(risultato);
        voce.addEventListener("click", function () {
          selezionaRisultato(risultato);
        });
        lista.appendChild(voce);
      });
      lista.style.display = "block";
    }

    input.addEventListener("input", function () {
      hidden.value = "";
      var termine = input.value.trim();
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (termine.length < 2) {
        nascondiLista();
        return;
      }
      timeoutId = setTimeout(function () {
        if (controllerCorrente) {
          controllerCorrente.abort();
        }
        controllerCorrente = new AbortController();
        fetch(url + "?q=" + encodeURIComponent(termine), { signal: controllerCorrente.signal })
          .then(function (risposta) {
            return risposta.json();
          })
          .then(function (dati) {
            mostraRisultati(dati.risultati || []);
          })
          .catch(function () {
            // Richiesta annullata da un termine più recente, o rete non
            // disponibile: nessuna azione, l'utente può riprovare.
          });
      }, 250);
    });

    document.addEventListener("click", function (event) {
      if (event.target !== input && !lista.contains(event.target)) {
        nascondiLista();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("script[data-url-autocomplete][data-prefisso]").forEach(function (script) {
      attiva(script.dataset.prefisso);
    });
  });
})();
