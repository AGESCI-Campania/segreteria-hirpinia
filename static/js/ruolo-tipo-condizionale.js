(function () {
  "use strict";

  // Deve combaciare con Ruolo.clean() in apps/accounts/models.py: solo un
  // aiuto visivo, la validazione reale resta lì, mai fidarsi solo di questo
  // script.
  var TIPI_CON_BRANCA_OBBLIGATORIA = ["IABZ"];
  var TIPI_CON_SETTORE_OBBLIGATORIA = ["ISZ"];

  document.addEventListener("DOMContentLoaded", function () {
    var selectTipo = document.getElementById("id_tipo");
    var selectBranca = document.getElementById("id_branca");
    var inputSettore = document.getElementById("id_settore");
    var asteriscoBranca = document.getElementById("asterisco-branca");
    var asteriscoSettore = document.getElementById("asterisco-settore");
    if (!selectTipo || !selectBranca || !inputSettore) {
      return;
    }

    function aggiorna() {
      var brancaObbligatoria = TIPI_CON_BRANCA_OBBLIGATORIA.indexOf(selectTipo.value) !== -1;
      var settoreObbligatorio = TIPI_CON_SETTORE_OBBLIGATORIA.indexOf(selectTipo.value) !== -1;
      selectBranca.required = brancaObbligatoria;
      inputSettore.required = settoreObbligatorio;
      if (asteriscoBranca) {
        asteriscoBranca.classList.toggle("d-none", !brancaObbligatoria);
      }
      if (asteriscoSettore) {
        asteriscoSettore.classList.toggle("d-none", !settoreObbligatorio);
      }
    }

    selectTipo.addEventListener("change", aggiorna);
    aggiorna();
  });
})();
