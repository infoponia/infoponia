// Comportamiento mínimo de las pantallas de InfoPonia: menú de cuenta, mostrar u ocultar la contraseña,
// avisos breves (10 s y con cruz), botón «Copiar» y ventanas. Sin JavaScript, el inicio y el cierre de sesión siguen
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
      var primero = menu.querySelector("button:not(:disabled), a[href]");
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

  // ---- Botón del ojo en los campos de contraseña. Se engancha en el documento (no en cada botón) para que
  // también funcione en una ventana que inserta HTMX después de cargar la página (vincular cuenta).
  document.addEventListener("click", function (e) {
    var ojo = e.target.closest("[data-ver-contrasena]");
    if (!ojo) return;
    var campo = document.getElementById(ojo.getAttribute("data-ver-contrasena"));
    if (!campo) return;
    var mostrar = campo.type === "password";
    campo.type = mostrar ? "text" : "password";
    ojo.setAttribute("aria-label", mostrar ? "Ocultar contraseña" : "Mostrar contraseña");
    ojo.querySelector("[data-icono-ver]").hidden = mostrar;
    ojo.querySelector("[data-icono-ocultar]").hidden = !mostrar;
  });
})();

// ---- Avisos breves, botón «Copiar» y ventanas (equivalen a toast, copy y modalHtml del prototipo).
// Sin JavaScript, la ventana queda abierta y su «Entendido» es un enlace; «Copiar» no se muestra.
(function () {
  "use strict";

  var DURACION_AVISO = 10000; // 10 s, para todos los avisos (de éxito y de error)
  var DURACION_SALIDA = 200; // ms; igual a la animación .toast-saliendo de la hoja de estilos
  var svg = function (trazos, tamano) {
    return (
      '<svg width="' + tamano + '" height="' + tamano + '" viewBox="0 0 24 24" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
      'aria-hidden="true">' + trazos + "</svg>"
    );
  };
  // Trazos de los íconos «check», «warn» (los de core/templatetags/iconos.py) y de la cruz.
  var ICONO_EXITO = svg('<polyline points="20 6 9 17 4 12"/>', 16);
  var ICONO_ERROR = svg(
    '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
    16
  );
  var CRUZ = svg('<path d="M18 6 6 18M6 6l12 12"/>', 14);
  var reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)");

  // La región «status» (role="status") está en la página desde el principio y vacía: al agregarle un aviso,
  // los lectores de pantalla lo anuncian.
  var regionDeAvisos = document.getElementById("avisos");

  // Aviso breve arriba a la derecha, debajo del encabezado: tarjeta con el color de su tipo, ícono, texto,
  // cruz y una barra que se achica durante los 10 segundos. ``tipo`` es "error" para los de error; cualquier
  // otro valor es un aviso de éxito. Se quita a los 10 segundos o al cerrarlo con la cruz, con una salida
  // animada (sin animación si la persona pidió reducir el movimiento). Los errores que se muestran debajo
  // de los campos de un formulario no son avisos y no pasan por acá.
  function mostrarAviso(texto, tipo) {
    if (!regionDeAvisos) return;
    var esError = tipo === "error";
    var aviso = document.createElement("div");
    aviso.className = "toast" + (esError ? " toast-error" : "");
    aviso.style.setProperty("--duracion-aviso", DURACION_AVISO + "ms");

    var icono = document.createElement("span");
    icono.className = "toast-icono";
    icono.innerHTML = esError ? ICONO_ERROR : ICONO_EXITO;

    var contenido = document.createElement("span");
    contenido.className = "toast-texto";
    contenido.textContent = texto;

    var cerrar = document.createElement("button");
    cerrar.type = "button";
    cerrar.className = "toast-cerrar";
    cerrar.setAttribute("aria-label", "Cerrar aviso");
    cerrar.innerHTML = CRUZ;

    var barra = document.createElement("span");
    barra.className = "toast-barra";
    barra.setAttribute("aria-hidden", "true");

    var temporizador = setTimeout(quitar, DURACION_AVISO);
    var saliendo = false;
    function quitar() {
      if (saliendo) return;
      saliendo = true;
      clearTimeout(temporizador);
      if (reducirMovimiento.matches) {
        aviso.remove();
        return;
      }
      // Primero se desvanece hacia la derecha y recién después sale del DOM.
      aviso.classList.add("toast-saliendo");
      setTimeout(function () {
        aviso.remove();
      }, DURACION_SALIDA);
    }
    cerrar.addEventListener("click", quitar);

    aviso.appendChild(icono);
    aviso.appendChild(contenido);
    aviso.appendChild(cerrar);
    aviso.appendChild(barra);
    regionDeAvisos.appendChild(aviso);
  }
  window.mostrarAviso = mostrarAviso;

  // ---- Botón «Copiar»: copia el texto del elemento que indica data-copiar.
  document.querySelectorAll("[data-copiar]").forEach(function (boton) {
    boton.hidden = false;
    boton.addEventListener("click", function () {
      var origen = document.getElementById(boton.getAttribute("data-copiar"));
      var fallo = "No se pudo copiar: seleccionala y copiala a mano.";
      if (!origen || !navigator.clipboard) {
        mostrarAviso(fallo, "error");
        return;
      }
      navigator.clipboard.writeText(origen.textContent.trim()).then(
        function () {
          mostrarAviso("Contraseña copiada.");
        },
        function () {
          mostrarAviso(fallo, "error");
        }
      );
    });
  });

  // ---- Ventana: bloquea el fondo hasta cerrarla con «Entendido», «Cancelar» o Esc, y atrapa el foco.
  // La ventana puede venir en la página (la contraseña temporal) o insertarla HTMX (las confirmaciones
  // de restablecer, reactivar y baja): en los dos casos se llama a abrirVentana.
  var enfocables = "a[href], button:not([hidden]):not(:disabled), input, select, textarea";

  function abrirVentana(ventana) {
    var fondo = document.querySelectorAll(".shell > header, .shell > aside, .shell > main, .shell > footer");
    var disparador = document.activeElement; // a quien se le devuelve el foco al cerrar

    function cerrar() {
      ventana.remove();
      fondo.forEach(function (parte) {
        parte.removeAttribute("inert");
      });
      document.removeEventListener("keydown", teclado);
      var destino =
        disparador && disparador !== document.body && document.body.contains(disparador)
          ? disparador
          : document.querySelector("[data-foco-al-cerrar]") || document.querySelector("main");
      if (destino) {
        if (!destino.matches(enfocables)) destino.tabIndex = -1;
        destino.focus();
      }
    }

    function teclado(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        cerrar();
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
    }

    fondo.forEach(function (parte) {
      parte.setAttribute("inert", "");
    });
    document.addEventListener("keydown", teclado);
    ventana.querySelectorAll("[data-cerrar-ventana]").forEach(function (cierre) {
      cierre.addEventListener("click", function (e) {
        e.preventDefault(); // con JavaScript se queda en la pantalla; sin él, el enlace sigue su destino
        cerrar();
      });
    });
    var inicial = ventana.querySelector("[data-foco-inicial]") || ventana.querySelector(enfocables);
    if (inicial) inicial.focus();
  }

  var ventanaEnLaPagina = document.querySelector("[data-ventana]");
  if (ventanaEnLaPagina) abrirVentana(ventanaEnLaPagina);

  // Ventana insertada por HTMX (confirmaciones).
  document.addEventListener("htmx:afterSwap", function (e) {
    var ventana = e.target.querySelector("[data-ventana]");
    if (ventana) abrirVentana(ventana);
  });

  // ---- Mensajes de Django (por ejemplo «Cambios guardados.»): sin JavaScript se ven como un aviso fijo
  // en la página (el respaldo); con JavaScript pasan a ser un aviso breve, de éxito o de error según su
  // data-tipo, que dura 10 segundos y se puede cerrar.
  document.querySelectorAll("[data-aviso]").forEach(function (mensaje) {
    var contenedor = mensaje.parentElement;
    mostrarAviso(mensaje.textContent.trim(), mensaje.getAttribute("data-tipo"));
    mensaje.remove();
    if (contenedor && contenedor.hasAttribute("data-avisos") && !contenedor.children.length) {
      contenedor.remove();
    }
  });
})();
