(function () {
  "use strict";

  // Variante di ricerca-socio-contributo-autocomplete.js (M14) per "Nuova
  // nota spese": qui non c'è un campo nascosto separato, il campo visibile
  // `beneficiario_codice_socio` è già il valore da inviare (testo libero,
  // validato lato server in NotaCreaView), quindi la selezione scrive
  // direttamente lì il codice socio invece di un'etichetta "Nome Cognome".

  function attivaAutocomplete(script) {
    var url = script.dataset.urlAutocomplete;
    var input = document.getElementById("id_beneficiario_codice_socio");
    var lista = document.getElementById("beneficiario-ricerca-risultati");
    var selezionato = document.getElementById("beneficiario-ricerca-selezionato");
    if (!url || !input || !lista) {
      return;
    }

    var timeoutId = null;
    var controllerCorrente = null;

    function nascondiLista() {
      lista.style.display = "none";
      lista.innerHTML = "";
    }

    function selezionaRisultato(risultato) {
      input.value = risultato.codice_socio;
      if (selezionato) {
        selezionato.textContent =
          risultato.nome + " " + risultato.cognome + " — " + risultato.gruppo;
      }
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
        voce.textContent =
          risultato.nome + " " + risultato.cognome + " (" + risultato.codice_socio + ") — " +
          risultato.gruppo;
        voce.addEventListener("click", function () {
          selezionaRisultato(risultato);
        });
        lista.appendChild(voce);
      });
      lista.style.display = "block";
    }

    input.addEventListener("input", function () {
      if (selezionato) {
        selezionato.textContent = "";
      }
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
            // Richiesta annullata da un termine di ricerca più recente, o
            // rete non disponibile: nessuna azione, l'utente può riprovare.
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
    var script = document.querySelector("script[data-url-autocomplete][src*='nota-spese-beneficiario']");
    if (script) {
      attivaAutocomplete(script);
    }
  });
})();
