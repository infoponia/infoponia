# UI-09 · Los cuatro colores de la organización: papeles, contraste validado y elección sin escribir códigos (D-110)

Estado: pendiente | App: core y maestros (toca el marco y plantillas de `comercial`, `compras` y `estadisticas` donde se ven los colores) | Rama: feature/ui-09-colores-de-la-organizacion | Ronda: —

Depende de: UI-02 (red de pantallas) y UI-04 (el avatar ya muestra iniciales; acá solo cambia su color). Si no están mergeadas,
frená. Va antes de UI-08.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**A diferencia de UI-02 a UI-08, esta tarea sí cambia una regla de negocio**: el servicio del perfil valida el contraste (D-110,
punto 3). Por eso lleva pruebas de servicio primero, como cualquier caso de uso (`.claude/rules/pruebas.md`, «Orden en servicios»).
Todo lo demás sigue la regla de no romper de D-109 (punto 2): sin cambios de modelo ni migraciones, sin cambiar los nombres de los
campos ni los códigos de error que ya existen (`color_formato`, `color_fuera_de_orden`), y con el respaldo sin JavaScript.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| ADM-MOD-ORG | Modificar el perfil de la organización (reglas 2, 5, 6 y 7; regla nueva 5 bis de D-110) | docs/casos_de_uso/maestros/configuracion.md | — |

## Leer

- Decisiones: D-110 (entera), D-48, D-36, D-47, D-109 (puntos 2, 3 y 12)
- Caso de uso: docs/casos_de_uso/maestros/configuracion.md — ADM-MOD-ORG y «Cómo se aplica…», viñeta «Colores»
- Modelo: docs/modelo/maestros.md — `PerfilOrganizacion` (fila de los colores)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md; patrón docs/patrones/verificacion_a_mano.md
- Código: `maestros/servicios/perfil.py` (`_validar`, `modificar_perfil`, `identidad`), `maestros/forms.py` (formulario del perfil),
  `maestros/templates/maestros/configuracion/_organizacion.html` y `pantalla.html`, la vista que guarda la organización
  (`configuracion/organizacion/`) y cómo muestra las «advertencias» de los parámetros (el mismo mecanismo se reutiliza);
  `core/extensiones.py` (`Identidad`), `core/identidad.py`, `core/context_processors.py`, `core/templates/core/base.html` (el `<style>`
  del color), `core/static/core/css/infoponia.css` (`.logo`, `.avatar`, `.sec-num`, `.kpi`, `.auth`); `core/tests/test_identidad.py`,
  `maestros/tests/test_adm_mod_org.py`, `maestros/tests/test_identidad_organizacion.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna (D-110, punto 9).
- Permitido fuera de `core` y `maestros`: los bases de los portales (`comercial/templates/comercial/cliente/base.html`,
  `compras/templates/compras/proveedor/base.html`) si hace falta para el fondo de marca; los comprobantes imprimibles de `comercial`
  (`*/comprobante.html`) para la franja de marca; las pruebas que afirmen lo que cambia.
- Dependencias nuevas: ninguna. El selector de color es el `<input type="color">` del navegador; las cuentas son de `core/colores.py`.
- Fuera de alcance: una segunda serie en los gráficos (no existe hoy); los colores en los correos (D-106: el logo tampoco va).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **`core/colores.py` (D-110, punto 7)**, con pruebas en `core/tests/test_colores.py` primero (mostralas fallando y frená):
   - `luminancia(hex)` y `contraste(a, b)` según WCAG 2.x (canales con 0,03928 de corte y 2,4 de exponente). Valores de control:
     `#FFFFFF` contra `#000000` da 21; `#1A6B3C` contra `#FFFFFF` da 6,54; `#F1C40F` contra `#FFFFFF` da 1,66 (redondeo a dos decimales).
   - `mezclar(a, b, proporcion_de_a)`: igual que `color-mix(in srgb, a p%, b)`, canal por canal, redondeado. `--primary-soft` es
     `mezclar(principal, "#FFFFFF", 0.10)` y `--primary-dark` es `mezclar(principal, "#000000", 0.80)`, como el marco de hoy.
   - `cumple(hex, papel)` con los requisitos de la tabla de D-110 (punto 1), para `"principal"`, `"marca"`, `"acento"` y `"fondo"`.
   - `propuesta(hex, papel)`: el mismo tono y la misma saturación (HSL, con `colorsys`), con la luminosidad más cercana a la original
     que cumple, buscada por bisección; más oscura para principal, marca y acento, más clara para fondo. Valores de control (cálculo del
     27/11/2026, la prueba admite ±1 por canal): principal `#2F6FDB` → `#2668D9`; `#F1C40F` → `#846B08`; `#16A085` → `#117B67`.
   - `parecido_al_error(hex)` (tono entre 345° y 15°, saturación ≥ 40 %) y `casi_iguales(a, b)` (contraste entre ellos < 1,3).
   - `MUESTRAS`: diez colores por papel, en tonos variados (verde, azul, violeta, bordó, marrón, gris azulado…; pasteles para el fondo).
     Prueba: todas cumplen su papel y no hay dos casi iguales en el mismo papel.
2. **Servicio del perfil (D-110, puntos 3 y 4)**, pruebas en `maestros/tests/test_adm_mod_org.py` primero (fallando, y frená):
   - En `_validar`, después del formato y del orden, cada color cargado cumple su papel (1 principal, 2 marca, 3 acento, 4 fondo). Si
     no, error `color_sin_contraste` en su campo con el mensaje de D-110 y la propuesta disponible para la pantalla (en el
     `params` del `ValidationError`, por ejemplo `{"propuesta": "#2668D9"}`). Todo o nada (regla 7): un color sin contraste no deja
     guardar los demás datos.
   - Avisos que no impiden guardar: color 1 parecido al rojo de error; colores 1 y 3 casi iguales. `modificar_perfil` los devuelve
     igual que la configuración devuelve sus advertencias (mirá cómo lo hace y repetilo; si su forma no sirve, frená y preguntá).
   - Los errores y los mensajes de formato y de orden de hoy no cambian. Guardar sin cambios sigue sin auditar (D-28); la auditoría de
     los colores, igual.
   - Prueba de no romper: un perfil con un color guardado antes que no cumple **se puede leer y mostrar** sin error, y modificar otro
     dato sin tocar el color da `color_sin_contraste` en ese color (D-110, punto 5: la validación le pide corregirlo al guardar).
3. **Identidad del marco (D-110, puntos 5 y 6).**
   - `Identidad` suma un campo `colores` (la tupla de los cuatro, `""` si falta) con valor por defecto `None`, **al final**, para que
     las llamadas de hoy con dos o tres valores sigan funcionando (Grep de `Identidad(`; hay pruebas que la arman con dos).
     `color_principal` sigue existiendo y significando lo mismo.
   - `maestros.servicios.perfil.identidad()` la completa. `core/identidad.py` suma `colores_de_la_organizacion(registrada)`: devuelve
     los cuatro ya listos para el CSS, con la propuesta de `core/colores.py` en lugar de cada color guardado que no cumple, y `None` en
     los que faltan. `color_principal()` también devuelve el ajustado si el guardado no cumple.
   - `core/context_processors.py` los pone en el contexto, con la misma consulta única por pedido de hoy.
4. **Marco y pantallas (D-110, puntos 1, 2 y 6).** En el `<style>` de `core/templates/core/base.html`, además de las tres variables
   de hoy: `--marca` (color 2 o, si falta, `var(--primary-dark)`), `--acento` (color 3 o `var(--primary)`), `--acento-soft`
   (`color-mix` del acento con blanco al 10 %) y `--fondo-marca` (color 4 o `var(--primary-soft)`). Los valores por defecto también van en
   `:root` de `infoponia.css`, para que sin color cargado todo se vea como hoy. Después:
   - `.logo` y `.avatar` (sin foto) usan `--marca`; `.sec-num` usa `--acento` sobre `--acento-soft`; el punto del rótulo de `.kpi` usa
     `--acento` (Grep de la clase que lo pinta hoy);
   - `.auth` (pantallas sin sesión) y los bases de los dos portales usan `--fondo-marca` como fondo de la página;
   - los comprobantes imprimibles de `comercial` suman una franja superior en `--marca` con el nombre de la organización (con
     `print-color-adjust: exact` para que salga al imprimir).
   **Nada de esto toca `--status-*`, los colores de etapa ni los del texto** (D-110, punto 2): agregá una prueba que lo controle en el
   `<style>` del marco.
   Pruebas: con los cuatro colores, el marco escribe las cuatro variables; sin colores, no escribe el `<style>`; con un color guardado
   que no cumple, escribe la propuesta; ninguna variable llega al HTML si no cumple `#RRGGBB`.
5. **Pestaña «Organización» (D-110, punto 8).** Por cada color: las muestras de `MUESTRAS` como botones de opción con el color de
   fondo y su nombre accesible («Verde bosque, #1A6B3C»), «Personalizado» con `<input type="color">` y el campo del código (que es el
   que se envía: **el `name` del campo no cambia**), y «Sin color» para los colores 2 a 4. Una vista previa (botón principal, enlace,
   cuadro de marca, número de paso y fondo de ingreso) que se actualiza en el navegador al elegir, sin pedidos al servidor. Con el error
   `color_sin_contraste`, el campo muestra el mensaje y un botón «Usar este color» que pone la propuesta en el campo (con JavaScript) o
   un enlace que vuelve a cargar el formulario con la propuesta (sin JavaScript; si eso complica, alcanza con el código escrito en el
   mensaje). Los avisos del punto 4 de D-110 se muestran junto al formulario. Sin JavaScript queda el campo del código, como hoy.
   Pruebas de vista: guardar una muestra; guardar un personalizado que cumple; guardar uno que no cumple (error y propuesta en el
   HTML); el aviso del rojo; la pantalla sin JavaScript trae los cuatro campos de código.
6. **Cierre de documentación (propuesto en M3, sin aplicarlo):** la viñeta «Colores» de `docs/casos_de_uso/maestros/configuracion.md`
   (sale «el sistema no valida el contraste»; entra la regla 5 bis de D-110); las dos filas de `docs/temas_abiertos.md`; el «Estado» de
   D-48; la fila de los colores en `docs/modelo/maestros.md` (los papeles, sin cambio de campos).
7. Red de pantallas entera, comando de pruebas y M1 a M4.

## Hecho cuando

- Ningún color que no cumpla su papel se puede guardar, y el Gerente recibe una propuesta del mismo tono.
- Un color guardado antes que no cumple se muestra ajustado y no rompe ninguna pantalla.
- Los cuatro colores se ven en sus lugares; sin colores, el sistema se ve exactamente como hoy.
- Los estados y las etapas no cambian de color con ninguna combinación.
- Pruebas: `core/tests/test_colores.py`, `maestros/tests/test_adm_mod_org.py` (servicio y vistas), `core/tests/test_identidad.py`,
  `maestros/tests/test_identidad_organizacion.py`, `maestros/tests/test_configuracion_vistas.py`, la red de pantallas.
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Incluí: como Gerente, elegir una muestra de cada papel y guardar; ver los colores en el encabezado (cuadro de marca), el avatar sin
foto, los números de paso de Nueva compra-venta, los indicadores del panel, la pantalla de ingreso en ventana privada (paso de
«navegador real»), un portal del cliente y un comprobante impreso a PDF. Probar un personalizado amarillo (#F1C40F): error, propuesta y
«Usar este color». Probar un rojo (#C0392B): guarda con el aviso. Quitar todos los colores y ver el sistema como antes. A 360 px y a 1366 px. -->

## Cierre (la completa Claude Code al cerrar)
