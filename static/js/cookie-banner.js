(function () {
  "use strict";

  var CHIAVE_STORAGE = "catello-cookie-banner-dismissed";

  var banner = document.getElementById("ag-cookie-banner");
  if (!banner) {
    return;
  }

  if (!window.localStorage || !localStorage.getItem(CHIAVE_STORAGE)) {
    banner.classList.remove("d-none");
  }

  var pulsanteChiudi = document.getElementById("ag-cookie-banner-dismiss");
  pulsanteChiudi.addEventListener("click", function () {
    if (window.localStorage) {
      localStorage.setItem(CHIAVE_STORAGE, "1");
    }
    banner.classList.add("d-none");
  });
})();
