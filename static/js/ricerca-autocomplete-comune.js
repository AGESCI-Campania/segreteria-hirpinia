(function () {
  "use strict";

  // Meccanismo condiviso di ricerca con debounce/fetch/dropdown, usato dagli
  // script di autocompletamento della piattaforma (ricerca soci, località,
  // beneficiario). Ogni script resta responsabile solo di cosa mostrare in
  // ogni voce (renderVoce) e cosa fare alla selezione (onSeleziona): il
  // perimetro/endpoint di ricerca resta deciso nella view Django, mai qui.
  window.AgesciAutocomplete = {
    avvia: function (opzioni) {
      var url = opzioni.url;
      var input = opzioni.input;
      var lista = opzioni.lista;
      var minimoCaratteri = opzioni.minimoCaratteri || 2;
      var renderVoce = opzioni.renderVoce;
      var onSeleziona = opzioni.onSeleziona;
      var onInput = opzioni.onInput;
      if (!url || !input || !lista || !renderVoce || !onSeleziona) {
        return;
      }

      var timeoutId = null;
      var controllerCorrente = null;

      function nascondiLista() {
        lista.style.display = "none";
        lista.innerHTML = "";
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
          voce.textContent = renderVoce(risultato);
          voce.addEventListener("click", function () {
            onSeleziona(risultato);
            nascondiLista();
          });
          lista.appendChild(voce);
        });
        lista.style.display = "block";
      }

      input.addEventListener("input", function () {
        if (onInput) {
          onInput();
        }
        var termine = input.value.trim();
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        if (termine.length < minimoCaratteri) {
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
    },
  };
})();
