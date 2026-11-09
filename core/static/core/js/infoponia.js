// Comportamiento mínimo de las pantallas de InfoPonia: menú de cuenta y mostrar u ocultar la
// contraseña. Sin JavaScript, el inicio y el cierre de sesión siguen funcionando.
(function () {
  "use strict";

  // ---- Menú de cuenta: se abre con el botón de la cabecera, se cierra con Esc o con un clic afuera.
  var boton = document.querySelector("[data-menu-cuenta]");
  var menu = document.getElementById("menu-cuenta");
  var telon = document.querySelector("[data-cerrar-menu]");

  function abrirMenu(abrir) {
    if (!boton || !menu) return;
    menu.hidden = !abrir;
    if (telon) telon.hidden = !abrir;
    boton.setAttribute("aria-expanded", abrir ? "true" : "false");
    if (abrir) {
      var primero = menu.querySelector("button, a");
      if (primero) primero.focus();
    }
  }

  if (boton && menu) {
    boton.addEventListener("click", function () {
      abrirMenu(menu.hidden);
    });
    if (telon) telon.addEventListener("click", function () { abrirMenu(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !menu.hidden) {
        abrirMenu(false);
        boton.focus();
      }
    });
  }

  // ---- Botón del ojo en los campos de contraseña.
  document.querySelectorAll("[data-ver-contrasena]").forEach(function (ojo) {
    ojo.addEventListener("click", function () {
      var campo = document.getElementById(ojo.getAttribute("data-ver-contrasena"));
      if (!campo) return;
      var mostrar = campo.type === "password";
      campo.type = mostrar ? "text" : "password";
      ojo.setAttribute("aria-label", mostrar ? "Ocultar contraseña" : "Mostrar contraseña");
      ojo.querySelector("[data-icono-ver]").hidden = mostrar;
      ojo.querySelector("[data-icono-ocultar]").hidden = !mostrar;
    });
  });
})();
