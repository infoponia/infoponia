// Editor de encuadre de la foto de perfil (USR-07; precisión de D-106). Al elegir un archivo en Mi perfil («Elegir foto» o «Tomar
// foto») se abre una ventana donde la persona arrastra, pellizca o hace zoom hasta que lo que quiere queda dentro del círculo
// (el avatar). «Guardar foto» completa tres campos ocultos del formulario, recorte_x, recorte_y y recorte_lado, y lo envía:
// son enteros en píxeles de la imagen ya con la orientación EXIF aplicada (la que ve el navegador, ``naturalWidth`` y
// ``naturalHeight``). Sin JavaScript, el formulario envía sin ellos y el servidor recorta desde el centro. El servidor vuelve a
// validar todo (core/imagenes.py): esto es solo comodidad. Se maneja con el mouse, con el dedo (arrastrar y pellizcar), con la
// rueda y con el teclado (flechas para mover; «+» y «−», y los botones, para el zoom).

(function () {
  "use strict";

  var TOPE = 5 * 1024 * 1024; // SEG-19: 5 MB
  var LADO_MINIMO = 64; // precisión de D-106: lado mínimo de la foto y del recorte
  var PASO_DEL_ZOOM = 1.1;
  var PASO_DE_LAS_FLECHAS = 10; // px de pantalla; con Shift, 50

  var MENSAJE_PESADA = "La imagen pesa más de 5 MB. Elegí una más liviana.";
  var MENSAJE_NO_SE_ABRE = "No se pudo abrir esa imagen. Probá con una foto en formato JPG, PNG o WebP.";
  var MENSAJE_CHICA = "La foto es demasiado chica: tiene que medir al menos " + LADO_MINIMO + " px de lado.";

  var form = document.querySelector("[data-foto-form]");
  var plantilla = document.querySelector("template[data-encuadre]");
  var contenedor = document.getElementById("ventana-perfil");
  if (!form || !plantilla || !contenedor || !window.InfoPonia || !window.InfoPonia.abrirVentana) return;

  var estado = form.querySelector("[data-foto-estado]");
  var campos = {
    x: form.querySelector('input[name="recorte_x"]'),
    y: form.querySelector('input[name="recorte_y"]'),
    lado: form.querySelector('input[name="recorte_lado"]'),
  };

  function escribir(texto, esError) {
    if (!estado) return;
    estado.textContent = texto;
    estado.classList.toggle("err", !!esError);
  }

  function vaciar(entrada) {
    entrada.value = "";
    campos.x.value = campos.y.value = campos.lado.value = "";
  }

  function acotar(valor, minimo, maximo) {
    return Math.min(Math.max(valor, minimo), maximo);
  }

  // Abre el editor para ``archivo`` (ya aceptado en tamaño). ``entrada`` es el campo de archivo que lo trajo.
  function abrirEditor(archivo, entrada, url) {
    var imagen0 = new Image();
    imagen0.onerror = function () {
      URL.revokeObjectURL(url);
      vaciar(entrada);
      escribir(MENSAJE_NO_SE_ABRE, true);
    };
    imagen0.onload = function () {
      var W = imagen0.naturalWidth;
      var H = imagen0.naturalHeight;
      if (!W || !H) {
        imagen0.onerror();
        return;
      }
      if (Math.min(W, H) < LADO_MINIMO) {
        URL.revokeObjectURL(url);
        vaciar(entrada);
        escribir(MENSAJE_CHICA, true);
        return;
      }
      montar(entrada, url, W, H);
    };
    imagen0.src = url;
  }

  function montar(entrada, url, W, H) {
    contenedor.appendChild(plantilla.content.cloneNode(true));
    var ventana = contenedor.querySelector("[data-ventana]");
    var escenario = ventana.querySelector("[data-encuadre-escenario]");
    var imagen = ventana.querySelector("[data-encuadre-imagen]");
    var guardando = false;

    // Estado: ``escala`` = píxeles de pantalla por píxel de la imagen; (ox, oy) = esquina de la imagen dentro del cuadro.
    var S = 0; // lado del cuadro en pantalla
    var escala = 1;
    var ox = 0;
    var oy = 0;
    var escalaMinima = 1; // el cuadro cubre el lado corto: la foto entera sin huecos
    var escalaMaxima = 1; // el recorte nunca baja de LADO_MINIMO px de la imagen

    function dibujar() {
      imagen.style.width = W * escala + "px";
      imagen.style.height = H * escala + "px";
      imagen.style.transform = "translate(" + ox + "px," + oy + "px)";
    }

    // El recorte queda siempre adentro de la imagen.
    function acomodar() {
      ox = acotar(ox, S - W * escala, 0);
      oy = acotar(oy, S - H * escala, 0);
    }

    function zoomHacia(nueva, cx, cy) {
      nueva = acotar(nueva, escalaMinima, escalaMaxima);
      ox = cx - ((cx - ox) * nueva) / escala;
      oy = cy - ((cy - oy) * nueva) / escala;
      escala = nueva;
      acomodar();
      dibujar();
    }

    function mover(dx, dy) {
      ox += dx;
      oy += dy;
      acomodar();
      dibujar();
    }

    function medir() {
      S = escenario.clientWidth;
      escalaMinima = S / Math.min(W, H);
      escalaMaxima = Math.max(escalaMinima, S / LADO_MINIMO);
      escala = escalaMinima;
      ox = (S - W * escala) / 2; // centrada
      oy = (S - H * escala) / 2;
      imagen.src = url;
      dibujar();
    }

    // ---- Puntero: un dedo o el mouse arrastran; dos dedos pellizcan.
    var punteros = new Map();
    var distanciaAnterior = 0;

    function distanciaYCentro() {
      var puntos = Array.from(punteros.values());
      var dx = puntos[0].x - puntos[1].x;
      var dy = puntos[0].y - puntos[1].y;
      return { d: Math.hypot(dx, dy), cx: (puntos[0].x + puntos[1].x) / 2, cy: (puntos[0].y + puntos[1].y) / 2 };
    }

    escenario.addEventListener("pointerdown", function (e) {
      escenario.setPointerCapture(e.pointerId);
      punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });
      escenario.classList.add("moviendo");
      if (punteros.size === 2) distanciaAnterior = distanciaYCentro().d;
      e.preventDefault();
    });
    escenario.addEventListener("pointermove", function (e) {
      var anterior = punteros.get(e.pointerId);
      if (!anterior) return;
      var caja = escenario.getBoundingClientRect();
      if (punteros.size === 1) {
        mover(e.clientX - anterior.x, e.clientY - anterior.y);
        punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });
      } else if (punteros.size === 2) {
        var antes = distanciaYCentro();
        punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });
        var ahora = distanciaYCentro();
        if (antes.d > 0 && ahora.d > 0) zoomHacia((escala * ahora.d) / antes.d, ahora.cx - caja.left, ahora.cy - caja.top);
        mover(ahora.cx - antes.cx, ahora.cy - antes.cy);
      }
    });
    function soltar(e) {
      punteros.delete(e.pointerId);
      if (!punteros.size) escenario.classList.remove("moviendo");
    }
    escenario.addEventListener("pointerup", soltar);
    escenario.addEventListener("pointercancel", soltar);

    escenario.addEventListener(
      "wheel",
      function (e) {
        e.preventDefault();
        var caja = escenario.getBoundingClientRect();
        zoomHacia(escala * (e.deltaY < 0 ? PASO_DEL_ZOOM : 1 / PASO_DEL_ZOOM), e.clientX - caja.left, e.clientY - caja.top);
      },
      { passive: false }
    );

    // ---- Teclado: flechas mueven la foto en esa dirección; «+» y «−» acercan y alejan.
    escenario.addEventListener("keydown", function (e) {
      var paso = e.shiftKey ? PASO_DE_LAS_FLECHAS * 5 : PASO_DE_LAS_FLECHAS;
      var movimientos = { ArrowLeft: [-paso, 0], ArrowRight: [paso, 0], ArrowUp: [0, -paso], ArrowDown: [0, paso] };
      if (movimientos[e.key]) {
        e.preventDefault();
        mover(movimientos[e.key][0], movimientos[e.key][1]);
      } else if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        zoomHacia(escala * PASO_DEL_ZOOM, S / 2, S / 2);
      } else if (e.key === "-" || e.key === "_") {
        e.preventDefault();
        zoomHacia(escala / PASO_DEL_ZOOM, S / 2, S / 2);
      }
    });
    ventana.querySelector("[data-encuadre-mas]").addEventListener("click", function () {
      zoomHacia(escala * PASO_DEL_ZOOM, S / 2, S / 2);
    });
    ventana.querySelector("[data-encuadre-menos]").addEventListener("click", function () {
      zoomHacia(escala / PASO_DEL_ZOOM, S / 2, S / 2);
    });

    // ---- Guardar: pasa el encuadre a enteros en píxeles de la imagen, siempre adentro de sus límites, y envía el formulario.
    var cerrar = window.InfoPonia.abrirVentana(ventana, function () {
      URL.revokeObjectURL(url);
      if (!guardando) {
        vaciar(entrada); // Cancelar o Esc: no queda ningún archivo ni encuadre
        escribir("", false);
        var elegir = form.querySelector('label[for="f-file"]');
        if (elegir) elegir.focus();
      }
    });

    ventana.querySelector("[data-encuadre-guardar]").addEventListener("click", function () {
      var lado = acotar(Math.round(S / escala), LADO_MINIMO, Math.min(W, H));
      campos.lado.value = String(lado);
      campos.x.value = String(acotar(Math.round(-ox / escala), 0, W - lado));
      campos.y.value = String(acotar(Math.round(-oy / escala), 0, H - lado));
      guardando = true;
      escribir("Subiendo la foto…", false);
      cerrar();
      form.requestSubmit();
    });

    medir();
  }

  // ---- Al elegir el archivo (desde el disco o la cámara): primero el tope de 5 MB y recién después el editor.
  document.addEventListener("change", function (e) {
    var entrada = e.target;
    if (!entrada.matches || !entrada.matches("input[data-foto]") || entrada.form !== form) return;
    var archivo = entrada.files && entrada.files[0];
    if (!archivo) return;
    // Un solo archivo por envío: se vacía el otro campo (archivo o cámara).
    form.querySelectorAll("input[data-foto]").forEach(function (otro) {
      if (otro !== entrada) otro.value = "";
    });
    campos.x.value = campos.y.value = campos.lado.value = "";
    if (archivo.size > TOPE) {
      entrada.value = "";
      escribir(MENSAJE_PESADA, true);
      return;
    }
    escribir("", false);
    abrirEditor(archivo, entrada, URL.createObjectURL(archivo));
  });

  // Al volver con «Atrás» desde el caché del navegador no debe quedar el «Subiendo…» de antes ni un encuadre viejo.
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    escribir("", false);
    campos.x.value = campos.y.value = campos.lado.value = "";
  });
})();
