(function () {
  "use strict";

  // Funzioni per cui la branca è obbligatoria (M7, D-08): deve combaciare con
  // FUNZIONI_CON_BRANCA_OBBLIGATORIA in apps/anagrafica/incarichi.py — questo
  // è solo un aiuto visivo, la validazione reale resta lì, mai fidarsi solo
  // di questo script.
  var FUNZIONI_CON_BRANCA_OBBLIGATORIA = ["CAPO_UNITA", "AIUTO_CAPO_UNITA"];

  function attivaAutocomplete(script) {
    var url = script.dataset.urlAutocomplete;
    var input = document.getElementById("ricerca-socio");
    var lista = document.getElementById("ricerca-socio-risultati");
    var selezionato = document.getElementById("ricerca-socio-selezionato");
    var hiddenCodiceSocio = document.getElementById("id_codice_socio");
    var selectGruppoServizio = document.getElementById("id_gruppo_servizio");
    if (!url || !input || !lista || !hiddenCodiceSocio) {
      return;
    }

    if (hiddenCodiceSocio.value) {
      input.value = hiddenCodiceSocio.value;
      if (selezionato) {
        selezionato.textContent = "Codice socio selezionato: " + hiddenCodiceSocio.value;
      }
    }

    window.AgesciAutocomplete.avvia({
      url: url,
      input: input,
      lista: lista,
      onInput: function () {
        hiddenCodiceSocio.value = "";
      },
      renderVoce: function (risultato) {
        return risultato.nome + " " + risultato.cognome + " (" + risultato.gruppo + ")";
      },
      onSeleziona: function (risultato) {
        hiddenCodiceSocio.value = risultato.codice_socio;
        input.value = risultato.codice_socio;
        if (selezionato) {
          selezionato.textContent =
            risultato.nome + " " + risultato.cognome + " — " + risultato.gruppo;
        }
        // Default al gruppo di censimento del capo scelto (M7), solo se il
        // campo non ha già un valore: un ?gruppo=<codice> in querystring
        // (arrivo da "Gestione gruppo", M6) ha sempre la precedenza e non va
        // sovrascritto. Resta comunque sempre modificabile manualmente dopo,
        // incarico esterno incluso.
        if (selectGruppoServizio && !selectGruppoServizio.value && risultato.gruppo_codice) {
          selectGruppoServizio.value = risultato.gruppo_codice;
        }
      },
    });
  }

  function attivaBrancaCondizionale() {
    var selectFunzione = document.getElementById("id_funzione");
    var selectBranca = document.getElementById("id_branca");
    var asterisco = document.getElementById("asterisco-branca");
    if (!selectFunzione || !selectBranca) {
      return;
    }

    function aggiorna() {
      var obbligatoria = FUNZIONI_CON_BRANCA_OBBLIGATORIA.indexOf(selectFunzione.value) !== -1;
      selectBranca.required = obbligatoria;
      if (asterisco) {
        asterisco.classList.toggle("d-none", !obbligatoria);
      }
    }

    selectFunzione.addEventListener("change", aggiorna);
    aggiorna();
  }

  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-url-autocomplete]");
    if (script) {
      attivaAutocomplete(script);
    }
    attivaBrancaCondizionale();
  });
})();
