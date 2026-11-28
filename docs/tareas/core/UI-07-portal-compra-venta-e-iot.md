# UI-07 · Portal del cliente por partes, monto de la compra-venta y Monitoreo de IoT (D-109, tanda 3c)

Estado: pendiente | App: core (toca plantillas de `comercial` e `iot`) | Rama: feature/ui-07-portal-compra-venta-e-iot | Ronda: —

Depende de: UI-02 (red de pantallas) y UI-06 (si se cruza con sus marcas `data-llevar-vista` en el portal). Si no están mergeadas,
frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Esta tarea no cambia lo que el sistema hace.** Rige la regla de no romper de D-109 (punto 2). El portal del cliente es una
pantalla pública con token de un solo uso (D-65): no se cambia el token, la sesión del enlace, los nombres de campos ni las
validaciones del servidor. Mostrar u ocultar partes es solo de presentación; sin JavaScript el formulario queda exactamente como hoy.

## Hallazgos incluidos

| ID | Qué |
|---|---|
| UX-26 | Portal del cliente: las quejas y «Si no recibió…» se ven siempre, con «*» |
| UX-28 | Nueva compra-venta: «$ 0,00» y «—» mientras la ventana de confirmación dice el monto real |
| UX-13 | Monitoreo de IoT: una caja de ancho completo por variable con una tarjeta de un tercio; «Sin lecturas» repetido |

Detalle en `docs/revision_interfaz_2026-11-27.md`.

## Leer

- Decisiones: D-109 (puntos 2, 3, 9 y 10), D-65, D-29; las decisiones de IoT que cite la plantilla de Monitoreo para el panel
  (búscalas en `docs/decisiones/README.md` antes de tocarla, L5)
- Revisión: `docs/revision_interfaz_2026-11-27.md`, filas UX-13, UX-26 y UX-28
- Reglas: .claude/rules/interfaz.md (también «Validaciones e interacción HTMX (desde INV-02)»), .claude/rules/pruebas.md;
  patrones docs/patrones/verificacion_a_mano.md y docs/patrones/enlace_del_cliente.md
- Código: portal del cliente en `comercial/templates/comercial/cliente/` (`confirmacion.html`, `_confirmacion_bloques.html`, `base.html`)
  y su vista; Nueva compra-venta en `comercial/templates/comercial/contratos/` (`formulario.html`, `_cuerpo.html`, `_resumen.html`) y su
  vista; Monitoreo en `iot/templates/iot/monitoreo/_panel.html` (y la plantilla que lo incluye) con `iot/static/iot/css/iot.css`.
  Confirmá los nombres con Grep: pueden haber cambiado.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: esas plantillas y CSS; un script propio chico para el portal, si hace falta, cargado con `static_v`; las
  pruebas que afirmen lo que cambia.
- Dependencias nuevas: ninguna.
- Fuera de alcance: recalcular la compra-venta mientras se escribe (prohibido por la regla de INV-02).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Portal del cliente (UX-26).** Con JavaScript: «Quejas» se muestra solo con «Sí, la recibí pero tengo quejas», y «Si no recibió
   la entrega…» solo con «No recibí la entrega»; las partes ocultas no se envían como obligatorias (si el servidor ya las ignora según
   la opción, solo se ocultan; **no** se cambia la validación del servidor). Sin JavaScript, todo visible como hoy. Las partes ocultas
   usan `hidden`, para que los lectores de pantalla tampoco las lean.
   Pruebas: el HTML del servidor trae las tres partes (respaldo sin JavaScript); los envíos de hoy (conforme, con quejas y no recibida)
   siguen dando el mismo resultado.
2. **Monto de la compra-venta (UX-28, D-109 punto 10).** Mientras el monto no se calculó (el formulario cambió desde el último
   «Actualizar»), el resumen lateral y el subtotal de cada línea muestran «—» con la ayuda «Se calcula al tocar «Actualizar»», en vez
   de «$ 0,00». Cuando la vista calculó el monto, se ve el monto como hoy. **No se agrega ningún recálculo por escritura.**
   Pruebas: la pantalla sin calcular no dice «$ 0,00» en el monto estimado; después de «Actualizar», dice el monto.
3. **Monitoreo de IoT (UX-13).** Las tarjetas de sensor van en una grilla (`repeat(auto-fill, minmax(280px, 1fr))` o similar), agrupadas
   por variable con un rótulo, en lugar de una caja de ancho completo por variable. Si ningún sensor tiene lecturas, un solo estado vacío
   («Todavía no llegaron lecturas del nodo») en lugar de uno por sensor. No cambian los datos, los estados, los umbrales ni los
   gráficos. Grep de las clases y los `id` que usan el refresco automático cada 30 s y las pruebas de IoT: no se renombran.
   Pruebas: la pantalla sin lecturas trae un solo estado vacío; con lecturas trae una tarjeta por sensor con su estado.
4. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- El portal muestra solo lo que corresponde a la opción elegida, y sin JavaScript sigue como hoy.
- La compra-venta nunca muestra «$ 0,00» como monto sin calcular.
- Monitoreo usa el ancho de la pantalla y tiene un solo estado vacío.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí el paso de «navegador real» del portal (ventana privada, enlace tomado de la consola con `CORREO_CONSOLA=1`, responder «con
quejas» hasta el final) y otra vez con JavaScript desactivado. Compra-venta: escribir cantidad y precio, ver «—», tocar «Actualizar» y ver
el monto. Monitoreo: con el nodo sin comunicarse y con lecturas (siguiendo `docs/api/nodo/escenarios.md`, escenario 1), a 1366 px y a 360 px. -->

## Cierre (la completa Claude Code al cerrar)
