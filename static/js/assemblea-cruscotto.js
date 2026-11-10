(function () {
  "use strict";

  // Aggiornamento automatico di cruscotto e vista proiettore delle assemblee:
  // chiede al server lo stato della seduta ogni `data-intervallo` ms (polling,
  // nessuna infrastruttura in tempo reale: D-17). Scrive solo con textContent,
  // mai innerHTML: nomi e gruppi arrivano dall'anagrafica.

  var script = document.querySelector("script[data-url-stato]");
  if (!script) {
    return;
  }
  var url = script.dataset.urlStato;
  var intervallo = parseInt(script.dataset.intervallo, 10) || 3000;
  var timer = null;

  function imposta(selettore, valore) {
    document.querySelectorAll(selettore).forEach(function (el) {
      el.textContent = valore;
    });
  }

  function testoQuorum(soglia, raggiunto, mancanti) {
    if (soglia === null) {
      return "Quorum non richiesto";
    }
    return raggiunto ? "Quorum raggiunto" : "Mancano " + mancanti + " presenti";
  }

  function aggiornaElenco(elenco) {
    var corpo = document.querySelector("tbody[data-elenco]");
    if (!corpo || !elenco) {
      return;
    }
    var righe = document.createDocumentFragment();
    elenco.forEach(function (p) {
      var tr = document.createElement("tr");
      [p.ora, p.cognome + " " + p.nome, p.gruppo, p.voto, p.delegato].forEach(function (valore) {
        var td = document.createElement("td");
        td.textContent = valore;
        tr.appendChild(td);
      });
      righe.appendChild(tr);
    });
    corpo.replaceChildren(righe);
  }

  function applica(dati) {
    imposta("[data-campo='aventi_diritto']", dati.aventi_diritto);
    imposta("[data-campo='presenti']", dati.presenti);
    imposta("[data-campo='presenti_app']", dati.presenti_app);
    imposta("[data-campo='presenti_carta']", dati.presenti_carta);
    imposta("[data-campo='soglia']", dati.soglia === null ? "—" : dati.soglia);
    imposta("[data-campo='aggiornato_il']", dati.aggiornato_il);
    imposta("[data-campo='stato_quorum']", testoQuorum(dati.soglia, dati.raggiunto, dati.mancanti));
    document.querySelectorAll("[data-esito-quorum]").forEach(function (el) {
      el.classList.toggle("theme-success", dati.raggiunto);
      el.classList.toggle("theme-warning", !dati.raggiunto);
    });

    var verifica = dati.verifica;
    document.querySelectorAll("[data-verifica]").forEach(function (el) {
      el.classList.toggle("d-none", !verifica);
    });
    if (verifica) {
      imposta("[data-campo='verifica_richiedente']", verifica.richiedente);
      imposta("[data-campo='verifica_presenti']", verifica.presenti);
      imposta("[data-campo='verifica_soglia']", verifica.soglia === null ? "—" : verifica.soglia);
    }
    aggiornaElenco(dati.elenco);
  }

  function segnalaConnessione(ok) {
    document.querySelectorAll("[data-connessione]").forEach(function (el) {
      el.classList.toggle("d-none", ok);
    });
  }

  function aggiorna() {
    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (risposta) {
        if (!risposta.ok) {
          throw new Error("HTTP " + risposta.status);
        }
        return risposta.json();
      })
      .then(function (dati) {
        applica(dati);
        segnalaConnessione(true);
      })
      .catch(function () {
        segnalaConnessione(false);
      });
  }

  function avvia() {
    if (timer === null) {
      aggiorna();
      timer = setInterval(aggiorna, intervallo);
    }
  }

  function ferma() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  // In pausa quando la scheda non è visibile: nessuna richiesta inutile.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      ferma();
    } else {
      avvia();
    }
  });
  avvia();
})();
