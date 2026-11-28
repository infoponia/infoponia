# UI-06 · Resumen y errores a la vista; errores obligatorios juntos (D-109, tanda 3b)

Estado: pendiente | App: core (toca `infoponia.js` y plantillas y vistas de formularios de todas las apps) | Rama: feature/ui-06-resumen-y-errores-a-la-vista | Ronda: —

Depende de: UI-02 (red de pantallas). Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Es la tarea de este lote con más riesgo, porque toca vistas de formularios.** Rige la regla de no romper de D-109 (punto 2), con
estos límites concretos:

- No se cambia ninguna validación de un **servicio** ni un mensaje de error de negocio. Solo se cambia, en la **vista**, cuándo se
  muestran los errores de los campos obligatorios que no dependen de otros.
- Las validaciones que dependen de otro valor (la distribución que tiene que sumar la cantidad, un precio que depende de la variedad)
  pueden seguir esperando a que ese valor sea válido.
- Los `name` de los campos, los `value` de los botones (`accion=calcular`, `accion=actualizar`…) y el orden de los pasos no cambian.
- `infoponia.js` sigue funcionando en todas las pantallas que lo cargan; el código nuevo es una función aparte y no toca las demás.

## Hallazgos incluidos

| ID | Qué |
|---|---|
| UX-24 | Después de «Ver resumen» o de un error, la página vuelve arriba y el foco queda en el cuerpo |
| UX-27 | Nueva siembra marca de a un error obligatorio por vez |

Detalle en `docs/revision_interfaz_2026-11-27.md`.

## Leer

- Decisiones: D-109 (puntos 2, 3 y 9), D-29 (envíos en curso, errores de HTMX)
- Revisión: `docs/revision_interfaz_2026-11-27.md`, filas UX-24 y UX-27
- Reglas: .claude/rules/interfaz.md (también «Validaciones e interacción HTMX (desde INV-02)»), .claude/rules/pruebas.md;
  patrón docs/patrones/verificacion_a_mano.md
- Código: `core/static/core/js/infoponia.js` (entero: cómo maneja el foco, los avisos, las ventanas y `htmx:afterSwap`),
  `core/templates/core/base.html` (cómo carga los scripts y el manejo de errores de HTMX); las vistas y plantillas de los formularios
  del inventario del paso 1.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: las plantillas de resúmenes y errores (sumar `data-llevar-vista` y `tabindex="-1"`); en las vistas de
  la lista del paso 1, solo la parte que decide qué errores de campo se muestran; las pruebas que afirmen lo que cambia.
- Dependencias nuevas: ninguna.
- Fuera de alcance: cambiar validaciones de servicios; recalcular mientras se escribe (sigue prohibido).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Inventario, antes de tocar nada.** Listá en el plan:
   - las pantallas con «Ver resumen», «Revisar», «Calcular» o equivalentes, y si el resumen llega por recarga completa o por HTMX;
   - los formularios que, enviados vacíos, muestran menos errores de obligatorios de los que tienen (prueba: enviar cada uno vacío con
     el cliente de Django y contar los campos obligatorios sin error). El caso conocido es Nueva siembra (Plantines, Fecha programada y
     la distribución). Mostrame la lista y frená.
2. **Llevar la vista (UX-24).** En `infoponia.js`, una función que, al cargar la página y después de cada `htmx:afterSwap`, busca el
   primer `[data-llevar-vista]` visible, le hace `scrollIntoView({block: "start"})` (sin `behavior: "smooth"` si el usuario pidió
   reducir el movimiento) y le da el foco (`preventScroll: true`). Se marca con `data-llevar-vista` y `tabindex="-1"`:
   - el contenedor del resumen, cuando se muestra;
   - el primer error de campo o el aviso de error del formulario, cuando el envío volvió con errores.
   Los redibujados de HTMX que solo cambian campos dependientes (`data-sin-envio-en-curso`, `hx-swap="… show:none"`) **no** llevan el
   atributo (regla de INV-02). Sin JavaScript no cambia nada.
   Pruebas: cada pantalla del inventario, al devolver el resumen o los errores, trae exactamente un `data-llevar-vista` en ese
   elemento; los fragmentos de redibujado no lo traen; el script existe con su versión (`static_v`, como prueba D-29).
3. **Errores juntos (UX-27).** En las vistas de la lista aprobada, los campos obligatorios independientes se validan todos en la misma
   pasada (el mismo texto de error de hoy en cada uno). Las validaciones dependientes y las del servicio quedan como están.
   Pruebas: enviar vacío marca todos los obligatorios independientes; enviar con la cantidad válida y la distribución mal sigue dando
   el error de la distribución de hoy; las pruebas de servicio no cambian.
4. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- Después de «Ver resumen» o de un error, la vista y el foco están en el resumen o en el primer error, en las pantallas del inventario.
- Nueva siembra, enviada vacía, marca Plantines y Fecha programada a la vez.
- Ninguna prueba de servicio cambió.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí, a 1366 px y a 360 px: Nueva siembra con «Ver resumen» (la vista baja al resumen) y vacía (la vista va al primer error);
Concretar siembra en el celular; el portal del cliente enviado vacío (paso de «navegador real», en ventana privada); un formulario con
selector dependiente (Nueva siembra al elegir invernadero) que NO mueve la vista; con «reducir movimiento» del sistema activado, el
salto es inmediato. Con Narrador de Windows, que al saltar lea el resumen o el error. -->

## Cierre (la completa Claude Code al cerrar)
