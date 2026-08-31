(function () {
  "use strict";

  // Variante di ricerca-socio-autocomplete.js (M7) per "Inserisci
  // partecipazione" (M14): stesso meccanismo di ricerca, ma senza la
  // precompilazione di un gruppo di servizio (qui il gruppo è sempre
  // risolto dal censimento nel service layer, mai un input) e con
  // l'etichetta "[Nome] [Cognome] ([Codice Socio])" richiesta dal TODO,
  // diversa da quella usata in M7.

  function attivaAutocomplete(script) {
    var url = script.dataset.urlAutocomplete;
    var input = document.getElementById("ricerca-socio");
    var lista = document.getElementById("ricerca-socio-risultati");
    var selezionato = document.getElementById("ricerca-socio-selezionato");
    var hiddenCodiceSocio = document.getElementById("id_codice_socio");
    if (!url || !input || !lista || !hiddenCodiceSocio) {
      return;
    }

    if (hiddenCodiceSocio.value) {
      input.value = hiddenCodiceSocio.value;
      if (selezionato) {
        selezionato.textContent = "Codice socio selezionato: " + hiddenCodiceSocio.value;
      }
    }

    var timeoutId = null;
    var controllerCorrente = null;

    function nascondiLista() {
      lista.style.display = "none";
      lista.innerHTML = "";
    }

    function etichetta(risultato) {
      return risultato.nome + " " + risultato.cognome + " (" + risultato.codice_socio + ")";
    }

    function selezionaRisultato(risultato) {
      hiddenCodiceSocio.value = risultato.codice_socio;
      input.value = etichetta(risultato);
      if (selezionato) {
        selezionato.textContent = etichetta(risultato) + " — " + risultato.gruppo;
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
        // Gruppo di censimento in coda (M18 #1): non è dato riservato
        // (a differenza dei recapiti, stesso principio già applicato in
        // M7), utile qui perché il perimetro può includere più gruppi
        // per SEGRETERIA/ADMIN/RDZ. L'etichetta dopo la selezione resta
        // invece quella richiesta dal TODO M14, senza gruppo.
        voce.textContent = etichetta(risultato) + " — " + risultato.gruppo;
        voce.addEventListener("click", function () {
          selezionaRisultato(risultato);
        });
        lista.appendChild(voce);
      });
      lista.style.display = "block";
    }

    input.addEventListener("input", function () {
      hiddenCodiceSocio.value = "";
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

  function attivaDescrizioneAltroCondizionale(script) {
    // M15: il campo "Specificare Altro" compare, e diventa obbligatorio
    // solo lato UI, quando la tipologia selezionata è "Altro" — la
    // validazione reale resta in Partecipazione.clean() (mai fidarsi solo
    // del client, stesso principio di attivaBrancaCondizionale in M7).
    var tipologiaAltroPk = script.dataset.tipologiaAltroPk;
    var selectTipologia = document.getElementById("id_tipologia");
    var campo = document.getElementById("campo-descrizione-altro");
    var input = document.getElementById("id_descrizione_altro");
    if (!tipologiaAltroPk || !selectTipologia || !campo || !input) {
      return;
    }

    function aggiorna() {
      var mostra = selectTipologia.value === tipologiaAltroPk;
      campo.classList.toggle("d-none", !mostra);
      input.required = mostra;
    }

    selectTipologia.addEventListener("change", aggiorna);
    aggiorna();
  }

  function attivaPrecompilazioneQuota(script) {
    // M17: precompila quota_versata con la quota_default della tipologia
    // scelta, quando esiste. Solo un aiuto lato client sul cambio
    // tipologia (mai al caricamento pagina, per non sovrascrivere un
    // valore già digitato in un ripresentazione del form dopo un errore
    // di validazione): il campo resta comunque obbligatorio e modificabile,
    // il fallback reale è server-side in inserimento.py.
    var quoteDefaultId = script.dataset.quoteDefaultId;
    var selectTipologia = document.getElementById("id_tipologia");
    var inputQuota = document.getElementById("id_quota_versata");
    var badge = document.getElementById("quota-badge-precompilato");
    if (!quoteDefaultId || !selectTipologia || !inputQuota) {
      return;
    }
    var elementoDati = document.getElementById(quoteDefaultId);
    if (!elementoDati) {
      return;
    }
    var quoteDefault;
    try {
      quoteDefault = JSON.parse(elementoDati.textContent);
    } catch (e) {
      return;
    }

    selectTipologia.addEventListener("change", function () {
      var quota = quoteDefault[selectTipologia.value];
      if (quota !== undefined) {
        inputQuota.value = quota;
        if (badge) {
          badge.classList.remove("d-none");
        }
      }
    });

    // M18 #3: il badge sparisce non appena l'utente modifica manualmente
    // il valore precompilato, per non farlo sembrare ancora "automatico".
    if (badge) {
      inputQuota.addEventListener("input", function () {
        badge.classList.add("d-none");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var script = document.querySelector("script[data-url-autocomplete]");
    if (script) {
      attivaAutocomplete(script);
      attivaDescrizioneAltroCondizionale(script);
      attivaPrecompilazioneQuota(script);
    }
  });
})();
