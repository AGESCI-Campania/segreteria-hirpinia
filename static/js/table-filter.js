(function () {
  "use strict";

  function aggiungiFiltro(tabella) {
    if (!tabella.tHead || !tabella.tBodies.length) {
      return;
    }
    var corpo = tabella.tBodies[0];
    if (corpo.rows.length <= 1) {
      return;
    }

    var contenitore = document.createElement("div");
    contenitore.className = "mb-2";

    var input = document.createElement("input");
    input.type = "search";
    input.className = "form-control";
    input.placeholder = "Filtra…";
    input.setAttribute("aria-label", "Filtra la tabella");

    contenitore.appendChild(input);
    tabella.parentNode.insertBefore(contenitore, tabella);

    input.addEventListener("input", function () {
      var termine = input.value.trim().toLowerCase();
      Array.prototype.forEach.call(corpo.rows, function (riga) {
        var testo = riga.textContent.toLowerCase();
        riga.style.display = termine === "" || testo.indexOf(termine) !== -1 ? "" : "none";
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table").forEach(aggiungiFiltro);
  });
})();
