// Comportamiento de las pantallas de `iot` (IOT-02). Todo es una mejora: sin JavaScript, cada pantalla funciona igual (D-29).
//  - La barra de contexto envía el invernadero elegido al cambiar el desplegable (sin JavaScript, el botón «Ver»).
//  - La pantalla del token (IOT-REG-SIS, pasos 9 y 10): «Copiar» copia el token; «Cerrar» se habilita al marcar «Ya guardé el token».
(function () {
  "use strict";

  document.addEventListener("change", function (e) {
    var desplegable = e.target.closest ? e.target.closest("select[data-enviar-al-cambiar]") : null;
    if (desplegable && desplegable.form) desplegable.form.submit();
  });

  function iniciarElToken() {
    var caja = document.querySelector("[data-token]");
    if (!caja) return;
    var cerrar = document.querySelector("[data-token-cerrar]");
    var guardado = document.querySelector("[data-token-guardado]");

    document.querySelectorAll("[data-copiar]").forEach(function (boton) {
      boton.hidden = false;
      boton.addEventListener("click", function () {
        var texto = document.querySelector(boton.getAttribute("data-copiar")).textContent.trim();
        var avisar = function (mensaje) { boton.textContent = mensaje; };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(texto).then(function () { avisar("Copiado"); }, function () { avisar("No se pudo copiar: seleccionalo y copialo a mano"); });
        } else {
          avisar("No se pudo copiar: seleccionalo y copialo a mano");
        }
      });
    });

    if (cerrar && guardado) {
      var actualizar = function () {
        var habilitado = guardado.checked;
        cerrar.setAttribute("aria-disabled", habilitado ? "false" : "true");
        cerrar.classList.toggle("disabled", !habilitado);
      };
      cerrar.addEventListener("click", function (e) { if (!guardado.checked) e.preventDefault(); });
      guardado.addEventListener("change", actualizar);
      actualizar();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciarElToken);
  else iniciarElToken();
})();
