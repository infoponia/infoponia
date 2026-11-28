# UI-03 · Accesibilidad: encabezados de acciones, vista activa, etiquetas y títulos (D-109, tanda 2a)

Estado: pendiente | App: core (toca plantillas de todas las apps) | Rama: feature/ui-03-accesibilidad | Ronda: —

Depende de: UI-02 (usa su red de pantallas; si no está mergeada, frená)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Esta tarea no cambia lo que el sistema hace.** Rige la regla de no romper de D-109 (punto 2). Ojo especial: las pruebas y los
scripts buscan elementos por su texto, su `id`, su `name` o sus atributos. Antes de cambiar un atributo (`aria-pressed`, un `<th>`, un
`<h3>`), buscá con Grep si una prueba o un script lo usa, y acomodalo en el mismo PR.

## Hallazgos incluidos

| ID | Qué | Detalle |
|---|---|---|
| UX-09 | Columna de acciones con el encabezado vacío (38 pantallas) | `docs/revision_interfaz_2026-11-27.md`, fila UX-09 |
| UX-10 | `aria-pressed` en enlaces (8 pantallas) | fila UX-10 |
| UX-11 | Campos sin etiqueta asociada | fila UX-11 |
| UX-12 | En el error de Nuevo invernadero, Provincia y Departamento no se marcan | fila UX-12 |
| UX-15 | Títulos que saltan de nivel (27 pantallas) | fila UX-15 |

## Leer

- Decisiones: D-109 (puntos 2, 3 y 8), D-24 (desplegables accesibles), D-29
- Revisión: `docs/revision_interfaz_2026-11-27.md` (las filas de arriba)
- Reglas: .claude/rules/interfaz.md, .claude/rules/pruebas.md; patrón docs/patrones/verificacion_a_mano.md
- Código: `core/static/core/css/infoponia.css` (para la clase de «solo lectores», si no existe), `demo/tests/test_red_de_pantallas.py`,
  `core/static/core/js/desplegable.js` (cómo arma el desplegable a partir del `<select>`: las etiquetas tienen que seguir llegando al
  desplegable propio), y las plantillas que nombra cada paso.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: plantillas y parciales de cualquier app, solo en lo de esta tarea (atributos, `<th>`, `<label>`, niveles
  de título); los formularios de Django solo para sumar `label` o `aria-label` a un widget (nunca su `name`, sus validaciones ni su
  orden); `demo/tests/test_red_de_pantallas.py` para sumar los controles de abajo; las pruebas que afirmen lo que cambia.
- Dependencias nuevas: ninguna (axe-core **no** se agrega: los controles son pruebas del cliente de Django que leen el HTML).
- Fuera de alcance: textos (UI-04), celular (UI-05).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Controles en la red de pantallas, primero** (fallan hoy y muestran el inventario; mostrámelo y frená):
   - toda `<th>` de una tabla tiene texto (visible o en una clase de «solo lectores»);
   - ningún `<a>` tiene `aria-pressed`;
   - todo `input` visible (no `hidden`, no `submit`/`button`), `select` y `textarea` tiene una etiqueta: `<label for>`, una `<label>`
     que lo envuelve, `aria-label` o `aria-labelledby`;
   - después del `h1`, los títulos no saltan niveles (`h1` → `h3` sin `h2` en el medio).
2. **Encabezados de acciones (UX-09).** Si no hay una clase de «solo lectores», sumá `.sr-only` a `infoponia.css` (la forma
   estándar: posición absoluta, 1 px, `clip`). Cada `<th></th>` de acciones pasa a `<th><span class="sr-only">Acciones</span></th>`.
3. **Vista activa (UX-10).** Los enlaces con `aria-pressed` pasan a `aria-current="page"` en el activo (y nada en los demás); si el
   grupo tiene `role="tablist"` y sus enlaces `role="tab"`, `aria-selected`. Grep de `aria-pressed` en el CSS: si algún estilo del
   estado activo depende de ese atributo, cambiá el selector para que el activo se siga viendo igual. Revisá con Grep las pruebas que
   buscan `aria-pressed`.
4. **Etiquetas (UX-11 y UX-12).** Cada campo de la lista del paso 1 recibe su etiqueta. Los conocidos: las duraciones de etapa de
   Variedades, el campo de la cámara de Mi perfil (su `<label>` está oculta: que se asocie bien, aunque no se vea), y las plantas
   perdidas, la causa y la descripción de Concretar cosecha. En Nuevo invernadero, cuando falta la ubicación, se marcan como inválidos
   los tres campos que faltan (Provincia, Departamento y Localidad), con `aria-invalid="true"` y el borde de error; el texto del error
   no cambia.
   Comprobá que el desplegable propio (D-24) sigue mostrando la etiqueta y que los campos dependientes de HTMX siguen funcionando.
5. **Títulos (UX-15).** Los títulos de tarjeta que quedan directamente bajo el `h1` pasan a `h2`. Si el CSS los estiliza por
   etiqueta (`.card-h h3`), sumá el mismo estilo para `h2` para que se vean igual. Grep de pruebas que busquen esos `h3`.
6. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- La red de pantallas pasa con los cuatro controles nuevos, para las diez cuentas.
- Ninguna pantalla cambió de aspecto salvo los bordes de error de Nuevo invernadero.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí: recorrer con Tab una lista con acciones, una pantalla con pestañas en forma de botón (Compras · Órdenes) y Concretar cosecha
en el celular; con un lector de pantalla (Narrador de Windows: Ctrl + Windows + Enter), oír «Acciones» en el encabezado y la etiqueta de
cada campo; enviar Nuevo invernadero sin ubicación y ver los tres campos marcados. -->

## Cierre (la completa Claude Code al cerrar)
