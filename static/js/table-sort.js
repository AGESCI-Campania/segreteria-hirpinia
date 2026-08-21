(function () {
  "use strict";

  function parseValue(raw) {
    var text = raw.trim();
    var dataMatch = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:[ ,]+(\d{1,2}):(\d{2}))?$/);
    if (dataMatch) {
      var giorno = Number(dataMatch[1]);
      var mese = Number(dataMatch[2]);
      var anno = Number(dataMatch[3]);
      var ora = Number(dataMatch[4] || 0);
      var minuti = Number(dataMatch[5] || 0);
      return new Date(anno, mese - 1, giorno, ora, minuti).getTime();
    }
    var isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (isoMatch) {
      var timestamp = Date.parse(text);
      if (!Number.isNaN(timestamp)) {
        return timestamp;
      }
    }
    var numerico = text.replace(/[€%\s]/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".");
    if (numerico !== "" && !Number.isNaN(Number(numerico))) {
      return Number(numerico);
    }
    return text.toLowerCase();
  }

  function cellValue(row, colonna) {
    var cella = row.children[colonna];
    if (!cella) {
      return "";
    }
    return cella.dataset.sortValue !== undefined ? cella.dataset.sortValue : cella.textContent;
  }

  function confronta(colonna, ascendente) {
    return function (a, b) {
      var va = parseValue(cellValue(a, colonna));
      var vb = parseValue(cellValue(b, colonna));
      var risultato;
      if (typeof va === "number" && typeof vb === "number") {
        risultato = va - vb;
      } else {
        risultato = String(va).localeCompare(String(vb), "it", { numeric: true, sensitivity: "base" });
      }
      return ascendente ? risultato : -risultato;
    };
  }

  function ordinaTabella(tabella, colonna, ascendente) {
    var corpo = tabella.tBodies[0];
    if (!corpo) {
      return;
    }
    Array.prototype.slice
      .call(corpo.rows)
      .sort(confronta(colonna, ascendente))
      .forEach(function (riga) {
        corpo.appendChild(riga);
      });
  }

  function ripulisciIndicatori(rigaIntestazione, tranne) {
    Array.prototype.forEach.call(rigaIntestazione.cells, function (cella) {
      if (cella === tranne) {
        return;
      }
      cella.removeAttribute("aria-sort");
      var indicatore = cella.querySelector(".table-sort-indicator");
      if (indicatore) {
        indicatore.remove();
      }
    });
  }

  function rendiOrdinabile(tabella) {
    if (!tabella.tHead || !tabella.tBodies.length) {
      return;
    }
    var rigaIntestazione = tabella.tHead.rows[tabella.tHead.rows.length - 1];
    Array.prototype.forEach.call(rigaIntestazione.cells, function (cella, colonna) {
      cella.style.cursor = "pointer";
      cella.setAttribute("role", "button");
      cella.setAttribute("tabindex", "0");

      function attiva() {
        var ascendente = cella.getAttribute("aria-sort") !== "ascending";
        ripulisciIndicatori(rigaIntestazione, cella);
        cella.setAttribute("aria-sort", ascendente ? "ascending" : "descending");
        var indicatore = cella.querySelector(".table-sort-indicator");
        if (!indicatore) {
          indicatore = document.createElement("span");
          indicatore.className = "table-sort-indicator";
          indicatore.style.marginLeft = "0.25rem";
          cella.appendChild(indicatore);
        }
        indicatore.textContent = ascendente ? "▲" : "▼";
        ordinaTabella(tabella, colonna, ascendente);
      }

      cella.addEventListener("click", attiva);
      cella.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          attiva();
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("table").forEach(rendiOrdinabile);
  });
})();
