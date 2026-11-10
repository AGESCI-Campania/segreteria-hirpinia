(function () {
  "use strict";

  // Pagine pubbliche del voto (apps/voto/views_urna.py).
  //
  // 1. Accesso: il codice arriva nel fragment del link (#c=CODICE), che il
  //    browser non manda mai al server. Lo si copia nel campo, si toglie dalla
  //    barra degli indirizzi e si invia il modulo in POST.
  // 2. Attesa: polling dello stato ogni `data-intervallo` ms (D-17, nessuna
  //    infrastruttura in tempo reale); quando cambia la votazione aperta la
  //    pagina si ricarica e mostra la scheda.

  var accesso = document.querySelector("form[data-voto-accesso]");
  if (accesso) {
    var corrispondenza = window.location.hash.match(/[#&]c=([A-Za-z0-9-]+)/);
    if (corrispondenza) {
      accesso.querySelector("input[name=codice]").value = corrispondenza[1];
      window.history.replaceState(null, "", window.location.pathname);
      accesso.submit();
    }
  }

  // Attivazione del seggio: il segreto arriva nel fragment (#s=…), come il
  // codice; si copia nel modulo e si toglie dalla barra degli indirizzi.
  var seggio = document.querySelector("form[data-voto-seggio]");
  if (seggio) {
    var segreto = window.location.hash.match(/[#&]s=([A-Za-z0-9_-]+)/);
    if (segreto) {
      seggio.querySelector("input[name=segreto]").value = segreto[1];
      window.history.replaceState(null, "", window.location.pathname);
    }
  }

  var attesa = document.querySelector("[data-voto-stato]");
  if (attesa) {
    var url = attesa.dataset.votoStato;
    var attuale = attesa.dataset.votazione || null;
    var intervallo = Number.parseInt(attesa.dataset.intervallo, 10) || 3000;

    var controlla = function () {
      fetch(url, { credentials: "same-origin", cache: "no-store" })
        .then(function (risposta) {
          return risposta.ok ? risposta.json() : null;
        })
        .then(function (stato) {
          if (!stato) {
            return;
          }
          if (!stato.accesso) {
            window.location.reload();
            return;
          }
          var nuova = stato.votazione === null ? null : String(stato.votazione);
          if (nuova !== attuale) {
            window.location.reload();
          }
        })
        .catch(function () {
          // Rete della sala instabile: si riprova al giro successivo.
        });
    };
    window.setInterval(controlla, intervallo);
  }
})();
