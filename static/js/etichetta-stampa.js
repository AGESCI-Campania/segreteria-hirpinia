(function () {
  "use strict";

  // «Stampa l'etichetta»: stampa il PDF 50×80 mm già presente nella pagina
  // (data: URI), senza un'altra richiesta al server: il codice in chiaro esiste
  // solo in questa pagina. Il PDF passa da un Blob a un iframe nascosto, che si
  // stampa con il formato dell'etichetta.
  function blobDa(dataUri) {
    var parti = dataUri.split(",");
    var binario = atob(parti[1]);
    var byte = new Uint8Array(binario.length);
    for (var i = 0; i < binario.length; i++) {
      byte[i] = binario.charCodeAt(i);
    }
    return new Blob([byte], { type: "application/pdf" });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-stampa-etichetta]").forEach(function (pulsante) {
      pulsante.addEventListener("click", function () {
        var url = URL.createObjectURL(blobDa(pulsante.dataset.stampaEtichetta));
        var cornice = document.createElement("iframe");
        cornice.style.display = "none";
        cornice.src = url;
        cornice.addEventListener("load", function () {
          cornice.contentWindow.focus();
          cornice.contentWindow.print();
        });
        document.body.appendChild(cornice);
      });
    });
  });
})();
