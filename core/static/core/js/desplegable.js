// Desplegable propio y accesible con teclado (D-24): reemplaza cada <select data-desplegable> por un
// botón con una lista, siguiendo el patrón «select-only combobox» de WAI-ARIA. El <select> nativo sigue
// dentro del formulario, oculto y sincronizado: el envío del formulario y los eventos «change» (por
// ejemplo, los filtros de HTMX) funcionan igual. Sin JavaScript no se ejecuta nada y se ve el <select>
// nativo.
//
// Teclado (botón cerrado): flecha abajo, flecha arriba, Enter o espacio abren la lista; una letra elige
// la primera opción que empieza con ella. Teclado (lista abierta): flechas, Inicio y Fin mueven;
// Enter o espacio eligen; Esc cierra sin cambiar; Tab elige y sigue; una letra salta a la opción.
(function () {
  "use strict";

  var contador = 0;
  var CHEVRON =
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<polyline points="6 9 12 15 18 9"/></svg>';

  function crear(select) {
    if (select.getAttribute("data-dd-listo")) return;
    select.setAttribute("data-dd-listo", "1");
    contador += 1;
    var base = select.id || "dd-" + contador;

    var contenedor = document.createElement("div");
    contenedor.className = "dd";

    var boton = document.createElement("button");
    boton.type = "button";
    boton.className = "field-input dd-boton";
    boton.id = base + "-boton";
    boton.setAttribute("role", "combobox");
    boton.setAttribute("aria-haspopup", "listbox");
    boton.setAttribute("aria-expanded", "false");
    boton.setAttribute("aria-controls", base + "-lista");

    // La etiqueta pasa a apuntar al botón (el <select> queda oculto); sin etiqueta, aria-label.
    var etiqueta = select.id ? document.querySelector('label[for="' + select.id + '"]') : null;
    if (etiqueta) {
      if (!etiqueta.id) etiqueta.id = base + "-etiqueta";
      etiqueta.setAttribute("for", boton.id);
      boton.setAttribute("aria-labelledby", etiqueta.id + " " + boton.id);
    } else if (select.getAttribute("aria-label")) {
      boton.setAttribute("aria-label", select.getAttribute("aria-label"));
    }

    var texto = document.createElement("span");
    texto.className = "dd-texto";
    boton.appendChild(texto);
    boton.insertAdjacentHTML("beforeend", CHEVRON);

    var lista = document.createElement("ul");
    lista.className = "dd-lista";
    lista.id = base + "-lista";
    lista.setAttribute("role", "listbox");
    lista.tabIndex = -1;
    lista.hidden = true;
    if (etiqueta) lista.setAttribute("aria-labelledby", etiqueta.id);
    else if (select.getAttribute("aria-label")) {
      lista.setAttribute("aria-label", select.getAttribute("aria-label"));
    }

    var opciones = [];
    Array.prototype.forEach.call(select.options, function (opcion, i) {
      var li = document.createElement("li");
      li.className = "dd-opcion";
      li.id = base + "-opcion-" + i;
      li.setAttribute("role", "option");
      li.textContent = opcion.textContent;
      li.addEventListener("mousedown", function (e) {
        e.preventDefault(); // el foco se queda en el botón
      });
      li.addEventListener("click", function () {
        elegir(i);
        cerrar();
        boton.focus();
      });
      lista.appendChild(li);
      opciones.push(li);
    });

    select.parentNode.insertBefore(contenedor, select);
    contenedor.appendChild(boton);
    contenedor.appendChild(lista);
    contenedor.appendChild(select);
    select.classList.add("dd-oculto");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");

    var activo = select.selectedIndex;
    var buffer = "";
    var temporizador = null;

    function pintar() {
      var elegido = select.selectedIndex;
      texto.textContent = elegido >= 0 ? select.options[elegido].textContent : "";
      boton.classList.toggle("dd-vacio", elegido >= 0 && select.options[elegido].value === "");
      opciones.forEach(function (li, i) {
        li.setAttribute("aria-selected", i === elegido ? "true" : "false");
        li.classList.toggle("dd-activa", i === activo && !lista.hidden);
      });
      if (!lista.hidden && opciones[activo]) {
        boton.setAttribute("aria-activedescendant", opciones[activo].id);
        opciones[activo].scrollIntoView({ block: "nearest" });
      } else {
        boton.removeAttribute("aria-activedescendant");
      }
    }

    function abierta() {
      return !lista.hidden;
    }

    function abrir() {
      activo = Math.max(select.selectedIndex, 0);
      lista.hidden = false;
      boton.setAttribute("aria-expanded", "true");
      pintar();
    }

    function cerrar() {
      lista.hidden = true;
      boton.setAttribute("aria-expanded", "false");
      pintar();
    }

    function elegir(i) {
      if (i < 0 || i >= select.options.length) return;
      var cambio = select.selectedIndex !== i;
      select.selectedIndex = i;
      activo = i;
      pintar();
      // Avisa al formulario y a HTMX, igual que si se hubiera usado el <select> nativo.
      if (cambio) select.dispatchEvent(new Event("change", { bubbles: true }));
    }

    function mover(i) {
      activo = Math.min(Math.max(i, 0), opciones.length - 1);
      pintar();
    }

    // Busca por la primera letra (o las letras seguidas): salta a la próxima opción que coincide.
    function buscar(letra) {
      clearTimeout(temporizador);
      buffer += letra.toLowerCase();
      temporizador = setTimeout(function () {
        buffer = "";
      }, 600);
      var desde = abierta() ? activo : select.selectedIndex;
      var orden = [];
      for (var k = 1; k <= opciones.length; k += 1) orden.push((desde + k) % opciones.length);
      if (buffer.length > 1) orden.unshift(desde); // letras seguidas: puede seguir en la actual
      for (var n = 0; n < orden.length; n += 1) {
        var texto_opcion = opciones[orden[n]].textContent.toLowerCase();
        if (texto_opcion.indexOf(buffer) === 0) {
          if (abierta()) mover(orden[n]);
          else elegir(orden[n]);
          return;
        }
      }
    }

    boton.addEventListener("click", function () {
      if (abierta()) cerrar();
      else abrir();
    });

    boton.addEventListener("keydown", function (e) {
      var tecla = e.key;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (!abierta()) {
        if (tecla === "ArrowDown" || tecla === "ArrowUp" || tecla === "Enter" || tecla === " ") {
          e.preventDefault();
          abrir();
        } else if (tecla.length === 1) {
          e.preventDefault();
          buscar(tecla);
        }
        return;
      }
      if (tecla === "ArrowDown") {
        e.preventDefault();
        mover(activo + 1);
      } else if (tecla === "ArrowUp") {
        e.preventDefault();
        mover(activo - 1);
      } else if (tecla === "Home") {
        e.preventDefault();
        mover(0);
      } else if (tecla === "End") {
        e.preventDefault();
        mover(opciones.length - 1);
      } else if (tecla === "Enter" || tecla === " ") {
        e.preventDefault();
        elegir(activo);
        cerrar();
      } else if (tecla === "Escape") {
        // Solo cierra la lista: no debe cerrar también una ventana o el menú de cuenta.
        e.preventDefault();
        e.stopPropagation();
        cerrar();
      } else if (tecla === "Tab") {
        elegir(activo); // el foco sigue su camino
        cerrar();
      } else if (tecla.length === 1) {
        e.preventDefault();
        buscar(tecla);
      }
    });

    // Si el foco sale del desplegable (clic afuera, por ejemplo), la lista se cierra.
    contenedor.addEventListener("focusout", function (e) {
      if (abierta() && !contenedor.contains(e.relatedTarget)) cerrar();
    });
    document.addEventListener("click", function (e) {
      if (abierta() && !contenedor.contains(e.target)) cerrar();
    });

    // Si algo cambia el <select> desde afuera (por ejemplo, reiniciar el formulario), se refleja.
    select.addEventListener("change", pintar);
    pintar();
  }

  function iniciarTodos(raiz) {
    (raiz || document).querySelectorAll("select[data-desplegable]").forEach(crear);
  }

  iniciarTodos();
  // Pantallas que HTMX agrega después de la carga.
  document.addEventListener("htmx:afterSwap", function (e) {
    iniciarTodos(e.target);
  });
})();
