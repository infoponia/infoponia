// Comportamiento mínimo de las pantallas de InfoPonia: menú de cuenta, mostrar u ocultar la contraseña,
// avisos breves, botón «Copiar» y ventanas. Sin JavaScript, el inicio y el cierre de sesión siguen
// funcionando. El desplegable propio está en desplegable.js.
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

// ---- Avisos breves, botón «Copiar» y ventanas (equivalen a toast, copy y modalHtml del prototipo).
// Sin JavaScript, la ventana queda abierta y su «Entendido» es un enlace; «Copiar» no se muestra.
(function () {
  "use strict";

  var aviso = document.getElementById("aviso");
  var temporizadorAviso = null;

  // Aviso arriba a la izquierda que desaparece solo a los 3,5 segundos.
  function mostrarAviso(texto) {
    if (!aviso) return;
    aviso.textContent = texto;
    var enCampo = document.querySelector(".shell.field");
    aviso.className = "toast " + (enCampo ? "field-t" : "shell-t");
    void aviso.offsetWidth; // reinicia la animación si había otro aviso
    aviso.classList.add("show");
    clearTimeout(temporizadorAviso);
    temporizadorAviso = setTimeout(function () {
      aviso.classList.remove("show");
    }, 3500);
  }
  window.mostrarAviso = mostrarAviso;

  // ---- Botón «Copiar»: copia el texto del elemento que indica data-copiar.
  document.querySelectorAll("[data-copiar]").forEach(function (boton) {
    boton.hidden = false;
    boton.addEventListener("click", function () {
      var origen = document.getElementById(boton.getAttribute("data-copiar"));
      var fallo = "No se pudo copiar: seleccionala y copiala a mano.";
      if (!origen || !navigator.clipboard) {
        mostrarAviso(fallo);
        return;
      }
      navigator.clipboard.writeText(origen.textContent.trim()).then(
        function () {
          mostrarAviso("Contraseña copiada.");
        },
        function () {
          mostrarAviso(fallo);
        }
      );
    });
  });

  // ---- Ventana: bloquea el fondo hasta cerrarla con «Entendido» o Esc, y atrapa el foco.
  var ventana = document.querySelector("[data-ventana]");
  if (ventana) {
    var fondo = document.querySelectorAll(".shell > header, .shell > aside, .shell > main, .shell > footer");
    var enfocables = "a[href], button:not([hidden]):not(:disabled), input, select, textarea";

    var cerrarVentana = function () {
      ventana.remove();
      fondo.forEach(function (parte) {
        parte.removeAttribute("inert");
      });
      document.removeEventListener("keydown", teclado);
      var destino = document.querySelector("[data-foco-al-cerrar]") || document.querySelector("main");
      if (destino) {
        if (!destino.matches(enfocables)) destino.tabIndex = -1;
        destino.focus();
      }
    };

    var teclado = function (e) {
      if (e.key === "Escape") {
        e.preventDefault();
        cerrarVentana();
      } else if (e.key === "Tab") {
        var items = ventana.querySelectorAll(enfocables);
        if (!items.length) return;
        var primero = items[0];
        var ultimo = items[items.length - 1];
        if (e.shiftKey && document.activeElement === primero) {
          e.preventDefault();
          ultimo.focus();
        } else if (!e.shiftKey && document.activeElement === ultimo) {
          e.preventDefault();
          primero.focus();
        }
      }
    };

    fondo.forEach(function (parte) {
      parte.setAttribute("inert", "");
    });
    document.addEventListener("keydown", teclado);
    ventana.querySelectorAll("[data-cerrar-ventana]").forEach(function (cierre) {
      cierre.addEventListener("click", function (e) {
        e.preventDefault(); // con JavaScript se queda en la pantalla; sin él, el enlace va a la lista
        cerrarVentana();
      });
    });
    var inicial = ventana.querySelector("[data-cerrar-ventana]") || ventana.querySelector(enfocables);
    if (inicial) inicial.focus();
  }
})();
