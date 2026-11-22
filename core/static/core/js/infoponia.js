// Comportamiento mínimo de las pantallas de InfoPonia: menú de cuenta, mostrar u ocultar la contraseña,
// avisos breves (10 s y con cruz), botón «Copiar», ventanas, envíos en curso y errores de HTMX. Sin JavaScript, el inicio y el cierre de sesión siguen
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

// ---- Envíos en curso y errores de HTMX (D-29). Sin JavaScript, los formularios envían como siempre.
(function () {
  "use strict";

  var TEXTO_POR_DEFECTO = "Guardando…";
  // Dos mensajes de error de HTMX (D-29): sin conexión o sin respuesta a tiempo, se sugiere revisar la conexión;
  // con un error del servidor (4xx o 5xx) la conexión funcionó, así que no se la menciona.
  var MENSAJE_SIN_CONEXION = "No pudimos completar la acción. Revisá tu conexión y volvé a intentarlo.";
  var MENSAJE_ERROR_DEL_SERVIDOR = "No pudimos completar la acción. Volvé a intentarlo.";
  // El mismo límite que tiene HTMX para cortar un pedido (<meta name="htmx-config"> de base.html): pasado ese
  // tiempo sin respuesta, el botón vuelve a su estado normal. No es menor a propósito: con la base de datos
  // despertando, devolver el botón antes de la respuesta reabriría la posibilidad del doble envío.
  // Se lee al usarlo y no al cargar: HTMX junta su configuración (la del <meta>) recién cuando la página termina de cargar.
  function esperaMaxima() {
    return (window.htmx && window.htmx.config && window.htmx.config.timeout) || 30000;
  }
  var BOTONES_DE_ENVIO = 'button[type="submit"], button:not([type]), input[type="submit"]';

  // Formularios con un envío en curso: form -> lo necesario para devolver el botón a su estado normal.
  var enCurso = new Map();

  // Marca el formulario como «enviando». Cambia el botón (indicador y verbo) y lo deshabilita. Devuelve el
  // estado, o null si ya había un envío en curso. ``botonClicado`` es el botón que disparó el envío.
  function empezar(form, botonClicado) {
    if (enCurso.has(form)) return null;
    var boton = botonClicado && botonClicado.form === form ? botonClicado : form.querySelector(BOTONES_DE_ENVIO);
    var estado = { boton: boton, contenido: null, anchoMinimo: null, desactivados: [], temporizador: null };
    enCurso.set(form, estado);
    form.setAttribute("aria-busy", "true");

    if (boton && boton.tagName === "BUTTON") {
      estado.contenido = boton.innerHTML;
      estado.anchoMinimo = boton.style.minWidth;
      // Se fija el ancho actual para que el botón no cambie de tamaño al cambiar el texto.
      boton.style.minWidth = boton.getBoundingClientRect().width + "px";
      var giro = document.createElement("span");
      giro.className = "giro";
      giro.setAttribute("aria-hidden", "true");
      boton.textContent = "";
      boton.appendChild(giro);
      // El verbo puede estar en el botón o, si no, en su formulario (data-enviando).
      var verbo = boton.getAttribute("data-enviando") || form.getAttribute("data-enviando") || TEXTO_POR_DEFECTO;
      boton.appendChild(document.createTextNode(verbo));
      boton.classList.add("enviando");
    }
    estado.temporizador = setTimeout(function () {
      terminar(form);
    }, esperaMaxima());
    return estado;
  }

  // Deshabilita los botones de envío del formulario. En un envío común se hace un instante después del evento
  // ``submit``: un botón deshabilitado antes de que el navegador arme los datos no manda su nombre ni su valor.
  function deshabilitar(form, estado) {
    if (enCurso.get(form) !== estado) return; // ya terminó
    form.querySelectorAll(BOTONES_DE_ENVIO).forEach(function (b) {
      if (!b.disabled) {
        b.disabled = true;
        estado.desactivados.push(b);
      }
    });
  }

  // Devuelve el formulario a su estado normal: texto original, botones habilitados.
  function terminar(form) {
    var estado = enCurso.get(form);
    if (!estado) return;
    clearTimeout(estado.temporizador);
    enCurso.delete(form);
    form.removeAttribute("aria-busy");
    estado.desactivados.forEach(function (b) {
      b.disabled = false;
    });
    if (estado.boton && estado.contenido !== null) {
      estado.boton.innerHTML = estado.contenido;
      estado.boton.style.minWidth = estado.anchoMinimo;
      estado.boton.classList.remove("enviando");
    }
  }

  function terminarTodos() {
    enCurso.forEach(function (estado, form) {
      terminar(form);
    });
  }

  // ---- Formulario común (POST). Se engancha en el documento para cubrir también las ventanas que inserta HTMX.
  // Los GET (el filtro de la lista) quedan afuera: no duplican nada y se reenvían a cada tecla.
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (e.defaultPrevented || !form.matches || !form.matches("form") || form.method.toLowerCase() !== "post") return;
    if (enCurso.has(form)) {
      e.preventDefault(); // segundo envío (otro clic o Enter): se descarta
      return;
    }
    var estado = empezar(form, e.submitter);
    setTimeout(function () {
      deshabilitar(form, estado);
    }, 0);
  });

  // ---- Formulario enviado por HTMX (hx-post, hx-put, hx-patch, hx-delete). HTMX cancela el envío nativo, por eso
  // se usan sus eventos. ``htmx:afterRequest`` se dispara con éxito y con error.
  function formularioDelPedido(e) {
    var elt = e.detail && e.detail.elt;
    var verbo = e.detail && e.detail.requestConfig && e.detail.requestConfig.verb;
    var form = elt && (elt.tagName === "FORM" ? elt : elt.form);
    return form && verbo && verbo !== "get" ? form : null;
  }

  document.addEventListener("htmx:beforeRequest", function (e) {
    var form = formularioDelPedido(e);
    if (!form) return;
    // Un pedido que solo vuelve a dibujar el formulario sin guardarlo («Agregar acción», «Quitar», el cambio de un combo) lleva
    // ``data-sin-envio-en-curso`` en su elemento: no cuenta como envío y no deshabilita el botón de guardar (D-29).
    var elemento = e.detail.elt;
    if (elemento.closest && elemento.closest("[data-sin-envio-en-curso]")) return;
    var estado = empezar(form, elemento);
    if (!estado) return;
    deshabilitar(form, estado);
    // El fin del pedido se escucha TAMBIÉN en el propio elemento: si la respuesta reemplaza el bloque donde estaba (por ejemplo, el
    // botón «Guardar» dentro de lo que se vuelve a dibujar), el elemento queda fuera del documento y ``htmx:afterRequest`` ya no
    // burbujea hasta ``document``: el botón seguiría deshabilitado hasta el límite de espera. En el elemento el evento sí llega.
    elemento.addEventListener("htmx:afterRequest", function () {
      terminar(form);
    }, { once: true });
  });
  document.addEventListener("htmx:afterRequest", function (e) {
    var form = formularioDelPedido(e);
    if (form) terminar(form);
  });

  // Volver atrás desde la memoria del navegador (o desde la copia de HTMX) no debe dejar un botón trabado.
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) terminarTodos();
  });
  document.addEventListener("htmx:beforeHistorySave", terminarTodos);

  // ---- Errores de HTMX: error del servidor (4xx o 5xx), sin conexión o sin respuesta a tiempo. La pantalla queda
  // como estaba (HTMX no cambia nada en esos casos) y se muestra el aviso de error de D-29. Si ya hay uno igual a
  // la vista, no se apila otro.
  function avisarError(mensaje) {
    var region = document.getElementById("avisos");
    var yaEsta =
      region &&
      Array.prototype.some.call(region.querySelectorAll(".toast:not(.toast-saliendo) .toast-texto"), function (t) {
        return t.textContent === mensaje;
      });
    if (!yaEsta) window.mostrarAviso(mensaje, "error");
  }
  document.addEventListener("htmx:sendError", function () {
    avisarError(MENSAJE_SIN_CONEXION);
  });
  document.addEventListener("htmx:timeout", function () {
    avisarError(MENSAJE_SIN_CONEXION);
  });
  document.addEventListener("htmx:responseError", function () {
    avisarError(MENSAJE_ERROR_DEL_SERVIDOR);
  });
})();

// ---- Campana de alertas y notificaciones (NOT-01, D-42). Con HTMX, un clic en el botón trae el panel a #campana-panel
// (hx-get, ver _campana.html); sin JavaScript el botón es un enlace a la página completa. Acá se hace lo que HTMX no:
// cambiar de pestaña sin recargar, cerrar (clic en el botón, clic afuera o Esc) y, al cerrar, marcar como leídas las
// notificaciones mostradas: se dispara el evento «cerrar» del formulario oculto #campana-formulario, un POST a
// core:campana_vista con los ids del panel (solo si se vio la pestaña de notificaciones). Las ajenas las ignora el servidor.
(function () {
  "use strict";

  var contenedor = document.getElementById("campana-panel");
  var formulario = document.getElementById("campana-formulario");
  if (!contenedor || !formulario) return;

  function boton() {
    return document.getElementById("campana-boton");
  }

  function panel() {
    return contenedor.querySelector("[data-campana-panel]");
  }

  function mostrarPestana(ventana, nombre) {
    ventana.setAttribute("data-pestana", nombre);
    if (nombre === "notificaciones") ventana.setAttribute("data-vistas", "1");
    ventana.querySelectorAll("[data-campana-tab]").forEach(function (pestana) {
      var activa = pestana.getAttribute("data-campana-tab") === nombre;
      if (activa) pestana.setAttribute("aria-current", "true");
      else pestana.removeAttribute("aria-current");
      pestana.setAttribute("aria-selected", activa ? "true" : "false");
    });
    ventana.querySelectorAll("[data-campana-lista]").forEach(function (lista) {
      lista.hidden = lista.getAttribute("data-campana-lista") !== nombre;
    });
  }

  function cerrar(devolverFoco) {
    var ventana = panel();
    if (!ventana) return;
    var ids = (ventana.getAttribute("data-ids") || "").split(",").filter(Boolean);
    if (ventana.getAttribute("data-vistas") === "1" && ids.length && window.htmx) {
      formulario.querySelectorAll("input[name=ids]").forEach(function (campo) { campo.remove(); });
      ids.forEach(function (id) {
        var campo = document.createElement("input");
        campo.type = "hidden";
        campo.name = "ids";
        campo.value = id;
        formulario.appendChild(campo);
      });
      window.htmx.trigger(formulario, "cerrar");
    }
    contenedor.innerHTML = "";
    var b = boton();
    if (b) {
      b.setAttribute("aria-expanded", "false");
      if (devolverFoco) b.focus();
    }
  }

  // En la fase de captura, antes que HTMX: con el panel abierto, el clic en el botón lo cierra y no pide otro.
  document.addEventListener(
    "click",
    function (e) {
      var b = e.target.closest("[data-campana-boton]");
      if (!b || !panel()) return;
      e.preventDefault();
      e.stopPropagation();
      cerrar(true);
    },
    true
  );

  document.addEventListener("click", function (e) {
    var ventana = panel();
    if (!ventana) return;
    if (e.target.closest("[data-campana-cerrar]")) {
      cerrar(false);
      return;
    }
    var pestana = e.target.closest("[data-campana-tab]");
    if (pestana && ventana.contains(pestana)) {
      e.preventDefault();
      mostrarPestana(ventana, pestana.getAttribute("data-campana-tab"));
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && panel()) cerrar(true);
  });

  // El panel llegó: se marca abierto y el foco va a la primera pestaña.
  document.addEventListener("htmx:afterSwap", function (e) {
    if (e.target !== contenedor) return;
    var ventana = panel();
    if (!ventana) return;
    var b = boton();
    if (b) b.setAttribute("aria-expanded", "true");
    var primera = ventana.querySelector("[data-campana-tab]");
    if (primera) primera.focus();
  });
})();
