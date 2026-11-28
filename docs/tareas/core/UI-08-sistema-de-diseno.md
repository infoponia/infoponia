# UI-08 · Sistema de diseño: escala tipográfica, colores de `:root` y menos estilos sueltos, app por app (D-109, tanda 4)

Estado: pendiente | App: core y, en cada subtarea, una sola app | Rama: feature/ui-08<letra>-<app> (una por subtarea) | Ronda: —

Depende de: UI-02 a UI-07 y UI-09 mergeadas (esta tarea reordena estilos que aquellas tocan). Si alguna no está, frená.

**Esta tarea se hace en subtareas, una por app, cada una en su propia sesión y su propio PR.** No se hacen dos a la vez
(tocan `infoponia.css`). Aprobado el plan de la subtarea, no pidas permiso paso por paso. Si algo que necesitás no está en «Leer»,
frená (L9).

**El objetivo es que nada se vea distinto**, salvo lo que la escala corrige (por ejemplo, 13,5 px pasa a 14 px). Rige la regla de no
romper de D-109 (punto 2). Es la tarea donde más fácil es romper algo sin darse cuenta, por eso:

- Antes de quitar un `style="…"`, buscá si un script o una prueba lo lee (`style`, `getComputedStyle`, `.style.`).
- Antes de quitar una regla de un CSS de app, comprobá que la regla común que la reemplaza da el mismo resultado en esa pantalla
  (mismas propiedades y misma especificidad, o una que gane).
- Un `style` con un valor que calcula la plantilla (`style="width:{{ p }}%"`, el color de una etapa) **se queda**.
- No cambies clases ni `id` que usen los scripts o las pruebas.

## Subtareas (en este orden)

| Subtarea | Qué cubre | Rama |
|---|---|---|
| UI-08a | `core`: escala tipográfica y colores en `:root`, `infoponia.css` ordenado (sin reglas repetidas, como `.grid2` que hoy aparece dos veces) y las plantillas de `core` | feature/ui-08a-core |
| UI-08b | `maestros` (plantillas y `maestros/static/maestros/css/*.css`) | feature/ui-08b-maestros |
| UI-08c | `inventario` | feature/ui-08c-inventario |
| UI-08d | `produccion` | feature/ui-08d-produccion |
| UI-08e | `compras` | feature/ui-08e-compras |
| UI-08f | `comercial` | feature/ui-08f-comercial |
| UI-08g | `contabilidad` y `estadisticas` | feature/ui-08g-contabilidad-estadisticas |
| UI-08h | `iot` | feature/ui-08h-iot |

## Hallazgo incluido

UX-04 (`docs/revision_interfaz_2026-11-27.md`): 831 atributos `style="…"`, 19 tamaños de letra, 68 colores escritos a mano, 11 CSS de
app con reglas repetidas y 5 funciones distintas para formatear pesos.

## Leer

- Decisiones: D-109 (puntos 2, 3 y 11), D-47, D-29
- Revisión: `docs/revision_interfaz_2026-11-27.md`, fila UX-04
- Reglas: .claude/rules/interfaz.md, .claude/rules/pruebas.md; patrón docs/patrones/verificacion_a_mano.md
- Código: `core/static/core/css/infoponia.css` (en todas las subtareas) y, en cada subtarea, las plantillas y el CSS de su app;
  `core/tests/test_interfaz.py` (pruebas que leen el CSS: no se debilitan).

## Límites (en cada subtarea)

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido: `infoponia.css`, las plantillas y el CSS de la app de la subtarea; las pruebas que afirmen un estilo que cambia a
  propósito.
- Dependencias nuevas: ninguna.
- Fuera de alcance: los cinco formateadores de pesos se **anotan** en `docs/temas_abiertos.md` con dónde está cada uno y qué
  diferencia tienen; unificarlos toca servicios de varias apps y respeta A1, así que queda para una tarea propia si el equipo lo decide.

## Pasos de UI-08a (`core`; las demás subtareas repiten los pasos 3 a 5 en su app)

1. **Escala y colores.** En `:root`: `--texto-xs:12px`, `--texto-sm:14px`, `--texto-md:16px`, `--texto-lg:20px`, `--texto-xl:24px` y
   `--texto-2xl:28px` (o los nombres que propongas, en el plan). Tabla en el plan: cada `font-size` en uso hoy y a qué paso de la
   escala va. Colores: cada hex escrito fuera de `:root` y a qué variable va; si no hay una equivalente, se agrega a `:root` con
   nombre, no se deja suelto.
2. **Prueba de la escala** en `core/tests/test_interfaz.py`: en `infoponia.css` (y, en cada subtarea, en el CSS de su app) no hay
   `font-size` en px fuera de `:root` ni colores hex fuera de `:root`, salvo una lista explícita de excepciones con su motivo.
3. **Plantillas.** Cada `style="…"` fijo (que no calcula la plantilla) pasa a una clase existente o a una nueva en el CSS común (si
   la usan varias apps) o en el de la app. Contalos antes y después, con Grep, en el «Cierre».
4. **CSS de la app.** Sale toda regla que repite una de `infoponia.css`. Sus tamaños y colores pasan a las variables.
5. Red de pantallas entera, comando de pruebas y M1 a M4. En el «Cierre», la tabla «antes y después»: `style=`, tamaños y colores.

## Hecho cuando (en cada subtarea)

- La prueba de la escala pasa para el CSS de la app.
- No quedan `style="…"` fijos en las plantillas de la app (los calculados se quedan, con su lista).
- La red de pantallas pasa con la misma línea de base.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar cada subtarea)

<!-- Incluí la lista de pantallas de la app para comparar antes y después, a 1366 px y a 360 px, con el «main» anterior abierto en otra
ventana (o con las capturas del relevamiento de D-109). Después de cada merge, Claude en claude.ai repite el relevamiento sobre esa app. -->

## Cierre (la completa Claude Code al cerrar cada subtarea)
