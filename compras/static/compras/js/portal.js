// Portal del proveedor (CMP-ENV-COT): al elegir cómo carga el precio solo cambia el rótulo de los campos («Precio total de la línea» o «Precio unitario»).
// No valida ni recalcula mientras se escribe (.claude/rules/interfaz.md): el otro valor se calcula en el resumen. Sin JavaScript el formulario funciona igual.
(function () {
  "use strict";
  var radios = document.querySelectorAll('input[name="modo"]');
  var etiquetas = document.querySelectorAll("[data-etiqueta-precio]");
  var textos = { total: "Precio total de la línea ($)", unitario: "Precio unitario ($)" };

  function actualizar() {
    var elegido = document.querySelector('input[name="modo"]:checked');
    var texto = textos[elegido ? elegido.value : "total"];
    etiquetas.forEach(function (etiqueta) {
      etiqueta.textContent = texto;
    });
  }

  radios.forEach(function (radio) {
    radio.addEventListener("change", actualizar);
  });
})();
