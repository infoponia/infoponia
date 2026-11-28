# UI-05 · Celular, segunda parte: menú desplegable y tablas como tarjetas (D-109, tanda 3a)

Estado: pendiente | App: core (toca plantillas de listas de todas las apps) | Rama: feature/ui-05-menu-y-tablas-en-el-celular | Ronda: —

Depende de: UI-02 (marco arreglado y red de pantallas). Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Esta tarea no cambia lo que el sistema hace.** Rige la regla de no romper de D-109 (punto 2). El menú del celular es la misma
lista del menú lateral (`core/menu.py`): se reutiliza, no se arma otra, para que una entrada nueva aparezca en los dos lados.

## Hallazgos incluidos

| ID | Qué |
|---|---|
| UX-07 | En el celular, hasta 13 módulos en una fila que se desplaza de costado, sin indicio de que hay más |
| UX-02 | Las tablas no se adaptan al celular |

Detalle en `docs/revision_interfaz_2026-11-27.md`.

## Leer

- Decisiones: D-109 (puntos 2, 3 y 4), D-25 (menú y modo campo), D-29, D-30 (ninguna acción lleva a un 403)
- Revisión: `docs/revision_interfaz_2026-11-27.md`, filas UX-02 y UX-07
- Reglas: .claude/rules/interfaz.md, .claude/rules/pruebas.md; patrón docs/patrones/verificacion_a_mano.md
- Código: `core/templates/core/base_con_sesion.html`, `core/menu.py`, `core/context_processors.py`, `core/static/core/css/infoponia.css`
  (`.mnav`, `.tablewrap`, `.lotlist`), `core/static/core/js/infoponia.js` (menú de cuenta: cómo se cierra con Esc y clic afuera),
  `core/tests/test_menu.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: las plantillas de las listas con tabla (solo para sumar el atributo de rótulo de cada celda); las pruebas
  que afirmen lo que cambia.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el modo campo (Capataz, Técnico y Transportista) no tiene menú lateral y no cambia (D-25, D-109 punto 4).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Menú del celular (UX-07).** Debajo de 760 px, la fila `.mnav` se reemplaza por un botón «Menú» en el encabezado, dentro de un
   `<details>`, que despliega las mismas entradas del menú lateral, con la activa marcada (`aria-current="page"`). Sin JavaScript
   funciona por el `<details>`; con JavaScript, se cierra con Esc y al tocar afuera, como el menú de cuenta. No toca el modo campo.
   Pruebas: en `core/tests/test_menu.py` (o al lado), las entradas del menú del celular son las mismas que las del lateral para cada
   rol, y el modo campo no lo muestra. Grep de `.mnav` en plantillas, CSS y pruebas: si sale, que salga de todos lados.
2. **Tablas en el celular (UX-02).** Debajo de 760 px, cada fila de una tabla de lista se muestra como una tarjeta apilada: la primera
   celda como título y las demás como pares «rótulo: valor», con la acción al final. Hacelo en CSS con un atributo `data-rotulo` en
   cada `<td>` (que repite el texto de su `<th>`) y una clase en la tabla (`.tabla-apilable`), así cada lista elige entrar. Empezá por
   las listas que usan el Vendedor y el Transportista (Clientes, Contratos, Entregas, Cobranza, Solicitudes) y seguí con Compras,
   Usuarios, Contabilidad e Inventario; si alguna tabla no se puede apilar sin perder sentido (por ejemplo, el libro de Contabilidad,
   que tiene filas de asiento y de movimiento), dejala con desplazamiento horizontal y anotalo. **No cambies el orden ni el contenido
   de las columnas en escritorio.**
   Prueba: las tablas con `.tabla-apilable` tienen `data-rotulo` en cada `<td>` que no sea de acciones (sumalo a la red de pantallas).
3. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- A 360 px, el Gerente y el Agrónomo llegan a cualquier módulo desde «Menú»; a 1366 px nada cambió.
- Las listas elegidas se leen como tarjetas a 360 px y como tabla a 1366 px.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí, a 360 px y a 1366 px: como Gerente, abrir «Menú», ir a Contabilidad y volver; cerrar el menú con Esc y tocando afuera; con
JavaScript desactivado, abrir y cerrar el menú; Clientes y Entregas como tarjetas; como Capataz, ver que el modo campo no cambió. -->

## Cierre (la completa Claude Code al cerrar)
