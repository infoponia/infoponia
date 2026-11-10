// Marca en vivo los requisitos de la contraseña nueva (policyList del prototipo, SEG-03). Es solo una
// ayuda visual: sin JavaScript el formulario funciona igual y el servidor siempre valida la política.
// «Distinta de la contraseña temporal» no está en la lista: el navegador no la conoce y la controla el servidor.
(function () {
  "use strict";

  var campo = document.querySelector("[data-contrasena-nueva]");
  if (!campo) return;

  // Cada requisito: la marca data-requisito de su <li> y cómo se cumple.
  var requisitos = {
    "largo": function (clave) { return clave.length >= 8; },
    "no-numerica": function (clave) { return clave.length > 0 && !/^\d+$/.test(clave); }
  };

  function actualizar() {
    Object.keys(requisitos).forEach(function (nombre) {
      var item = document.querySelector('[data-requisito="' + nombre + '"]');
      if (!item) return;
      var cumplido = requisitos[nombre](campo.value);
      item.classList.toggle("ok", cumplido);
      var aviso = item.querySelector(".sr");
      if (cumplido && !aviso) {
        aviso = document.createElement("span");
        aviso.className = "sr";
        aviso.textContent = " (cumplido)";
        item.appendChild(aviso);
      } else if (!cumplido && aviso) {
        aviso.remove();
      }
    });
  }

  campo.addEventListener("input", actualizar);
  actualizar();
})();
