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

  // Affluenza delle urne aperte: stesso markup di templates/assemblee/_affluenza_urne.html.
  function paragrafo(classi, parti) {
    var p = document.createElement("p");
    p.className = classi;
    parti.forEach(function (parte) {
      if (typeof parte === "string") {
        p.appendChild(document.createTextNode(parte));
      } else {
        var strong = document.createElement("strong");
        strong.textContent = String(parte.forte);
        p.appendChild(strong);
      }
    });
    return p;
  }

  function aggiornaUrne(urne) {
    document.querySelectorAll("[data-urne]").forEach(function (contenitore) {
      var solo = contenitore.dataset.urneVotazione;
      var proiettore = contenitore.dataset.urneStile === "proiettore";
      var blocchi = document.createDocumentFragment();
      (urne || []).forEach(function (u) {
        if (solo && String(u.votazione) !== solo) {
          return;
        }
        var div = document.createElement("div");
        div.className = "mb-5";
        if (proiettore) {
          div.appendChild(paragrafo("fs-4xl fw-bold mb-0", [u.votanti + " / " + u.attesi]));
          div.appendChild(paragrafo("fs-lg mb-0", ["hanno votato in app — " + u.oggetto]));
        } else {
          if (!solo) {
            var h3 = document.createElement("h3");
            h3.className = "fs-lg mb-1";
            h3.textContent = u.oggetto;
            div.appendChild(h3);
          }
          div.appendChild(
            paragrafo(
              "mb-1",
              ["Hanno votato in app ", { forte: u.votanti }, " su " + u.attesi + ": "].concat(
                u.mancano ? ["mancano ", { forte: u.mancano }, "."] : ["hanno votato tutti."]
              )
            )
          );
          if (u.da_votare && u.da_votare.length) {
            div.appendChild(
              paragrafo("fs-sm fg-2 mb-0", ["Devono ancora votare: " + u.da_votare.join(", ") + "."])
            );
          }
        }
        blocchi.appendChild(div);
      });
      contenitore.replaceChildren(blocchi);
    });
    document.querySelectorAll("[data-se-urne]").forEach(function (el) {
      el.classList.toggle("d-none", !(urne && urne.length));
    });
  }

  function applica(dati) {
    imposta("[data-campo='aventi_diritto']", dati.aventi_diritto);
    imposta("[data-campo='presenti']", dati.presenti);
    imposta("[data-campo='presenti_app']", dati.presenti_app);
    imposta("[data-campo='presenti_carta']", dati.presenti_carta);
    imposta("[data-campo='soglia']", dati.soglia === null ? "—" : dati.soglia);
    imposta("[data-campo='aggiornato_il']", dati.aggiornato_il);
    imposta("[data-campo='stato_quorum']", testoQuorum(dati.soglia, dati.raggiunto, dati.mancanti));
    // Vista proiettore: sfondo tenue rosso senza quorum, verde con il quorum.
    document.querySelectorAll("[data-sfondo-quorum]").forEach(function (el) {
      el.classList.toggle("bg-subtle-success", dati.raggiunto);
      el.classList.toggle("bg-subtle-danger", !dati.raggiunto);
    });
    // Azioni della seduta che seguono il quorum: «Dichiara validamente
    // costituita» con il quorum, «Chiudi: quorum non raggiunto» senza.
    document.querySelectorAll("[data-se-quorum-raggiunto]").forEach(function (el) {
      el.classList.toggle("d-none", !dati.raggiunto);
    });
    document.querySelectorAll("[data-se-quorum-mancante]").forEach(function (el) {
      el.classList.toggle("d-none", dati.raggiunto);
      el.classList.toggle("d-flex", !dati.raggiunto);
    });
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
    if (dati.soglie) {
      imposta("[data-campo='soglia_deliberazioni']", dati.soglie.deliberazioni);
      imposta("[data-campo='soglia_elezioni']", dati.soglie.elezioni);
      imposta("[data-campo='soglia_revoca']", dati.soglie.revoca);
    }
    aggiornaElenco(dati.elenco);
    aggiornaUrne(dati.urne);
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
