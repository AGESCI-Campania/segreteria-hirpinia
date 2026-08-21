(function () {
  "use strict";

  function etichettaCheckbox(checkbox) {
    var label = checkbox.closest(".form-check").querySelector(".form-check-label");
    return label ? label.textContent.trim() : "";
  }

  function aggiornaEtichetta(widget) {
    var etichetta = widget.querySelector(".ag-multiselect__label");
    var selezionati = widget.querySelectorAll(".ag-multiselect__checkbox:checked");
    if (selezionati.length === 0) {
      etichetta.textContent = etichetta.dataset.placeholder || "";
    } else if (selezionati.length === 1) {
      etichetta.textContent = etichettaCheckbox(selezionati[0]);
    } else {
      etichetta.textContent = selezionati.length + " selezionati";
    }
  }

  function inizializza(widget) {
    aggiornaEtichetta(widget);
    widget.querySelectorAll(".ag-multiselect__checkbox").forEach(function (checkbox) {
      checkbox.addEventListener("change", function () {
        aggiornaEtichetta(widget);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".ag-multiselect").forEach(inizializza);
  });
})();
