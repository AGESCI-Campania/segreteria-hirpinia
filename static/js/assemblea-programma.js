(function () {
  "use strict";

  // Programma dei lavori della seduta: chiede al server ogni `data-intervallo`
  // ms le righe in corso (polling, D-17) e le evidenzia. Se il programma è
  // cambiato e la pagina è di sola consultazione (`data-ricarica="1"`), la
  // ricarica; ai gestori no, per non perdere un form in compilazione.

  var script = document.querySelector("script[data-url-stato]");
  if (!script) {
    return;
  }
  var url = script.dataset.urlStato;
  var firma = script.dataset.firma;
  var ricarica = script.dataset.ricarica === "1";
  var intervallo = parseInt(script.dataset.intervallo, 10) || 3000;

  function evidenzia(inCorso) {
    var attive = new Set(inCorso.map(String));
    document.querySelectorAll("tr[data-riga]").forEach(function (tr) {
      var attiva = attive.has(tr.dataset.riga);
      tr.classList.toggle("fw-bold", attiva);
      var badge = tr.querySelector("[data-in-corso]");
      if (badge) {
        badge.hidden = !attiva;
      }
    });
  }

  function aggiorna() {
    fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (risposta) {
        return risposta.ok ? risposta.json() : null;
      })
      .then(function (dati) {
        if (!dati) {
          return;
        }
        if (dati.firma !== firma && ricarica) {
          window.location.reload();
          return;
        }
        evidenzia(dati.in_corso || []);
      })
      .catch(function () {});
  }

  window.setInterval(aggiorna, intervallo);
})();
