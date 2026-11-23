// Formulario de proveedores (CMP-01). Dos mejoras que sin JavaScript no hacen falta (el formulario funciona igual):
// 1) en el alta, muestra solo los campos del tipo elegido (razón social para una persona jurídica; nombre y apellido para una física);
// 2) un buscador para las categorías de insumos: oculta las que no coinciden, sin tocar las que están marcadas ni lo que se envía.
// No valida nada: las reglas las aplica el servicio.
(function () {
  "use strict";

  function mostrarSegunTipo() {
    var elegido = document.querySelector("input[data-tipo]:checked");
    if (!elegido) return;
    document.querySelectorAll("[data-grupo-tipo]").forEach(function (grupo) {
      grupo.hidden = grupo.getAttribute("data-grupo-tipo") !== elegido.value;
    });
  }

  function normalizar(texto) {
    return (texto || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
  }

  function iniciarBuscador(bloque) {
    var campo = bloque.querySelector("[data-buscar-categoria]");
    var opciones = bloque.querySelectorAll(".prv-categoria");
    var vacio = bloque.querySelector("[data-sin-resultados]");
    if (!campo) return;
    campo.hidden = false; // con JavaScript el buscador se ve; sin él, todas las categorías quedan a la vista
    campo.addEventListener("input", function () {
      var buscado = normalizar(campo.value);
      var visibles = 0;
      opciones.forEach(function (opcion) {
        var coincide = !buscado || normalizar(opcion.getAttribute("data-nombre")).indexOf(buscado) !== -1;
        opcion.hidden = !coincide;
        if (coincide) visibles += 1;
      });
      if (vacio) vacio.hidden = visibles > 0;
    });
    // Enter en el buscador no envía el formulario.
    campo.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter") evento.preventDefault();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[data-tipo]").forEach(function (radio) {
      radio.addEventListener("change", mostrarSegunTipo);
    });
    mostrarSegunTipo();
    document.querySelectorAll("[data-buscador-categorias]").forEach(iniciarBuscador);
  });
})();
