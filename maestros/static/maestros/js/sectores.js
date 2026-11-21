// Menú «⋯» de los sectores (MAE-03): cada menú es un <details>, que abre y cierra solo sin JavaScript. Con JavaScript, además,
// se cierra al hacer clic afuera, al elegir una acción (la ventana que abre HTMX lo tapa) y con Esc. Sin dependencias.
(function () {
  "use strict";

  function cerrar(menu) {
    menu.removeAttribute("open");
  }

  document.addEventListener("click", function (e) {
    document.querySelectorAll("details.sec-kb[open]").forEach(function (menu) {
      // Clic en una acción del propio menú: se cierra; clic dentro del menú pero fuera de ellas, no; clic afuera, se cierra.
      var accion = e.target.closest && e.target.closest(".menu a");
      if (!menu.contains(e.target) || (accion && menu.contains(accion))) cerrar(menu);
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.sec-kb[open]").forEach(function (menu) {
      cerrar(menu);
      var resumen = menu.querySelector("summary");
      if (resumen) resumen.focus();
    });
  });
})();
