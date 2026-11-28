# UI-03 · Accesibilidad: encabezados de acciones, vista activa, etiquetas y títulos (D-109, tanda 2a)

Estado: hecha | App: core (toca plantillas de todas las apps) | Rama: feature/ui-03-accesibilidad | Ronda: —

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

Esta tarea no cambia lo que el sistema hace ni cómo se ve, salvo el borde rojo de Provincia y Departamento en Nuevo invernadero. Lo que
cambia es lo que **oye** quien usa un lector de pantalla. La red de pantallas ya comprobó con las diez cuentas de la demo que ninguna
tabla tiene un encabezado vacío, que ningún enlace usa `aria-pressed`, que todo campo tiene etiqueta y que los títulos no saltan niveles;
el recorrido (`demo/tests/test_recorrido_accesibilidad.py`) recorre las pantallas tocadas por rol. Lo que sigue es lo que una prueba no
puede ver: el aspecto, el teclado y la voz del lector de pantalla.

**Antes de empezar**

- En la terminal: `python manage.py runserver` y abrí `http://localhost:8000/` en Chrome o Edge.
- **Modo celular:** con la página abierta, `F12` y después `Ctrl+Shift+M`. En «Dimensiones», «Responsivo», `360` de ancho y `800` de alto.
  Para volver a computadora, `Ctrl+Shift+M` otra vez y la ventana a pantalla completa (al menos 1366 px de ancho).
- **Narrador de Windows:** se prende y se apaga con `Ctrl + Windows + Enter`. Para recorrer una tabla celda por celda:
  `Ctrl + Alt + flechas`. Para saltar de título en título: con el modo de examen prendido (`Bloq Mayús + Barra espaciadora`), la tecla `H`
  (y `Mayús + H` para volver); el Narrador dice el nivel («encabezado de nivel 2»). Bajá un poco el volumen antes de prenderlo.
- Cuentas: un **Gerente**, un **Agrónomo**, un **Capataz** con una cosecha «a realizar», un **Vendedor** y un **Contador**. Si usás la base
  `infoponia_demo` de `cargar_demo` (DAT-01), ya están todas (`<base>+gerente1@gmail.com`, `+agronomo1`, `+capataz1`, `+vendedor1`,
  `+contador1`, con la contraseña de la variable de la demo) y todos los datos de abajo.
- Datos que hacen falta, si no usás la demo, en este orden:
  1. Una orden de compra en cualquier estado (Agrónomo → Compras → «Pedidos» → un pedido con cotizaciones → «Generar orden»), para que
     «Compras · Órdenes» muestre sus atajos.
  2. Un cobro registrado (Vendedor → Comercial → «Cobranza» → «Por cobrar» → registrar el cobro de una entrega concretada).
  3. Un cultivo, por ejemplo «Lechuga» (Agrónomo → Producción → «Cultivos y variedades» → «Nuevo cultivo»).
  4. Una cosecha planificada para el Capataz, en estado «a realizar» (Agrónomo → Comercial → «Cosechas» → «Planificar cosecha»).

**1. «Acciones» en las tablas (UX-09) — Gerente, 1366 px.** Entrá como Gerente → «Cuentas». La tabla se ve igual que antes: la última
   columna (la de los botones) no tiene título visible. Prendé el Narrador, hacé clic en el nombre de la primera cuenta y movete con
   `Ctrl + Alt + flecha derecha` hasta la última celda: el Narrador dice **«Acciones»** antes del botón. Apagá el Narrador.
   Repetí, sin Narrador, mirando solo el aspecto, en «Comercial» → «Clientes», «Inventario» → «Catálogo» y «Producción» → «Órdenes de
   trabajo»: ninguna tabla muestra la palabra «Acciones» ni cambió de alto. *Lo cubren:* `test_ui03_toda_th_tiene_texto` (red) y el recorrido.

**2. Columnas que no son de acciones — Contador y Agrónomo.** Como Contador → «Contabilidad» (Libro diario, vista «Cronológica»): la
   tabla se ve igual. Con el Narrador, en la fila de un asiento, la celda de la descripción se anuncia con «Cuenta, Descripción».
   Como Vendedor → «Comercial» → «Estadísticas»: la columna de las barras se anuncia como «Proporción del monto» (las barras no se leen).
   *Lo cubre el recorrido* (el texto del Libro).

**3. Vista activa en Compras · Órdenes (UX-10) — Gerente, 1366 px.** Compras → «Órdenes». Tocá los atajos «Por aprobar», «Por recibir» y
   «Todas»: el activo se ve **relleno de verde con letras blancas**, igual que antes, y los demás en blanco con borde gris. Con `Tab`
   llegás a cada atajo y se ve el borde de foco. Con el Narrador, sobre el atajo activo dice «**página actual**» (antes decía «botón de
   alternancia presionado»). Repetí en «Compras» → «Reclamos» con «Sin emitir». *Lo cubren:* `test_ui03_ningun_enlace_tiene_aria_pressed`
   (red), `test_ui03_ninguna_plantilla_tiene_un_enlace_con_aria_pressed` (fuentes) y el recorrido.

**4. Pestañas de Cobranza (UX-10) — Vendedor.** «Comercial» → «Cobranza». Tocá «Cobros registrados» y «Por cobrar»: la activa se ve
   **rellena de verde con letras blancas, igual que antes** (este es el único lugar donde el estilo ahora sale de otro atributo; si se ve
   blanca, avisá). Con el Narrador dice «pestaña, seleccionada». *Lo cubre el recorrido* (el HTML; el color, no).

**5. Libro diario — Contador.** «Contabilidad»: «Cronológica» y «Por cuenta» se ven como en el paso 3 y el activo cambia al tocarlos.

**6. Duraciones de etapa (UX-11) — Agrónomo.** Producción → «Cultivos y variedades» → en un cultivo, «Nueva variedad». Elegí un perfil
   familiar. En la lista de etapas, cada fila sigue mostrando el número y «días», sin texto nuevo a la vista. Con el Narrador, hacé clic en
   la casilla de días de Germinación: dice «**Duración estimada de Germinación en días**, editar». Cambiá el perfil: las filas se
   redibujan y la etiqueta se sigue leyendo. *Lo cubren:* `test_ui03_todo_campo_tiene_etiqueta` y el recorrido.

**7. Mi perfil, foto (UX-11) — cualquier cuenta.** Menú de cuenta → «Mi perfil». En computadora se ve «Elegir foto» (o «Cambiar foto»);
   «Tomar foto» no aparece (como antes). Con `Tab` hasta «Elegir foto» y `Enter`: se abre el selector de archivos; cancelalo. En el
   celular de verdad (o a 360 px en la barra de dispositivos con la pantalla táctil simulada) aparece «Tomar foto». *Lo cubre el recorrido*
   (que cada archivo tiene su `aria-label`).

**8. Concretar cosecha en el celular — Capataz, 360 px.** Entrá como Capataz, abrí la cosecha «a realizar» → «Concretar». En el paso 3
   («Plantas perdidas»), abrí «declarar plantas perdidas» de un lote. Recorré con `Tab`: «Perdidas en …», «Causa» (el desplegable propio)
   y «Descripción (opcional)»; cada campo muestra su etiqueta encima. Con el Narrador, cada uno se anuncia con su etiqueta. No cambió
   nada en esta pantalla: ya tenía las etiquetas (ver «Diferencias»). *Lo cubre el recorrido.*

**9. Nuevo invernadero sin ubicación (UX-12) — Gerente, 1366 px.** Producción → «Invernaderos» → «Nuevo invernadero». Escribí el nombre
   «Invernadero de prueba» y tocá «Crear invernadero» sin elegir provincia.
   - Tienen que verse con **borde rojo los tres**: Provincia, Departamento y Localidad.
   - Debajo de Localidad, el error de siempre: «Elegí la localidad de la lista.» (una sola vez; Provincia y Departamento no muestran texto).
   - Elegí una provincia (por ejemplo, Misiones) y volvé a tocar «Crear invernadero»: Provincia ya **no** está en rojo; Departamento y
     Localidad sí. Elegí departamento y localidad: al guardar, si falta otro dato (por ejemplo, la calle), ninguno de los tres está en rojo.
   - Con el Narrador, después del primer envío, al pasar por Provincia dice «**no válido**» (o «entrada no válida»).
   *Lo cubre el recorrido* (atributos y clases); el borde rojo y la voz, no.

**10. Nuevo invernadero sin JavaScript (opcional).** `F12` → `Ctrl+Shift+P` → escribí «Disable JavaScript» → Enter. Recargá Nuevo
   invernadero y repetí el primer envío del paso 9: los tres desplegables (ahora los nativos) se ven con borde rojo. Volvé a activar
   JavaScript («Enable JavaScript») y cerrá las herramientas.

**11. Navegador real.** Abrí `http://localhost:8000/` en una **ventana privada**, entrá como Gerente, abrí Nuevo invernadero, completá
   todo (nombre «Invernadero de prueba 2», tipo urbana, provincia, departamento, localidad, calle y número) y **envialo hasta el final**:
   tiene que llevarte a la ficha del invernadero con el aviso «Invernadero creado: Invernadero de prueba 2.». Si aparece «Prohibido (403)»,
   «Verificación CSRF fallida» o un error en la consola (`F12` → «Console»), avisá. Después podés darlo de baja desde su ficha.

**12. Títulos (UX-15) — 1366 px y 360 px.** Mirá que se vean **igual que antes** (mismo tamaño y peso, no más grandes) los títulos de
   tarjeta de estas pantallas:
   - Gerente: ficha de un invernadero («Ubicación», «Personal», «Logística», «Capacidad»), Estadísticas → «Producción» y «Consolidadas»,
     Panel de control («Personal por asignar», si aparece), Producción → «Cultivos y variedades» (el nombre de cada cultivo).
   - Vendedor: ficha de un cliente («Contratos»…), ficha de un suministro, Cobranza → «Por cobrar» (el nombre de cada cliente en su
     recuadro) y «Registrar cobro» (el «Resumen»).
   - Técnico (o Gerente) en IoT: «Monitoreo», «Sistema IoT» (el nombre del nodo), «Comandos» («Emitir comando» y «Resumen del comando»),
     la ficha de un equipo, la ficha de una regla y «Tipos de actuador» («Catálogo de capacidades»). En un invernadero **sin** Sistema IoT,
     el mensaje «… no tiene Sistema IoT» del centro se ve chico, con el mismo espacio arriba y abajo que antes.
   - Agrónomo: Compras → registrar una recepción («Qué llegó en buen estado», «Inconvenientes») y resolver una orden («Su decisión»).
   Con el Narrador en una de esas fichas, `H` salta del título de la página (nivel 1) a los de las tarjetas (**nivel 2**), sin un nivel 3
   suelto. *Lo cubre:* `test_ui03_los_titulos_no_saltan_niveles` (el aspecto, no).

**13. El desplegable propio sigue igual (D-24).** En Nuevo invernadero y en Concretar cosecha, abrí cada desplegable con el mouse y con el
   teclado (`Tab` hasta él, flecha abajo, flechas, `Enter`): se abre la lista propia (no la nativa), se elige y, en Nuevo invernadero, al
   elegir provincia se cargan los departamentos y al elegir departamento, las localidades (HTMX). La etiqueta de cada uno sigue arriba.

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

1. **Controles en la red** (`demo/tests/test_red_de_pantallas.py`): un lector aparte, `_LectorDeAccesibilidad`, y cuatro pruebas
   `test_ui03_…` en `RedDePantallasTests` (toda `<th>` con texto, ningún `<a>` con `aria-pressed`, todo campo con etiqueta, títulos sin
   saltos después del `h1`); `ControlesDeAccesibilidadTests` prueba cada control con HTML de ejemplo; en `EscaneoDeFuentesTests`,
   `test_ui03_ninguna_plantilla_tiene_un_enlace_con_aria_pressed` (pedido del estudiante al revisar el paso 1: la red no llega con GET a
   Recepción ni a Corrección). Inventario del paso 1 (con las diez cuentas): 52 filas con un `<th>` vacío, 55 enlaces con `aria-pressed`,
   9 campos sin etiqueta (las duraciones de Variedades) y 48 saltos de título.
2. **Encabezados (UX-09):** 48 `<th>` vacíos en 40 plantillas reciben un texto solo para lectores con la clase `.sr` que ya existía en
   `infoponia.css` (decisión del estudiante: no se suma `.sr-only`). 41 dicen «Acciones»; las columnas que no son de acciones dicen lo que
   son: «Elegir» (la elección de transportista de Asignar entrega), «Proporción del monto» (las barras de Estadísticas comerciales, en
   `comercial` y en `estadisticas`), «Situación» (Alcanza/No alcanza del detalle de suministro y Nuevo/Cambia del resumen de envasado),
   «Descripción» (la columna del medio del Libro diario) y «Sin estado» (la celda del pie de la tabla de la ficha de compra-venta).
3. **Vista activa (UX-10):** 13 enlaces de Compras · Órdenes y Reclamos, Recepción, Corrección y el Libro diario pasan de `aria-pressed` a
   `aria-current="page"` solo en el activo. En Cobranza (que ya tenía `role="tab"` y `aria-selected`) se quita `aria-pressed`, y
   `.chip[aria-selected="true"]` se suma a la regla del chip activo de `infoponia.css` para que se vea igual. Los `<button>` de Estadísticas
   con `aria-pressed` no cambian (es válido en un botón).
4. **Etiquetas (UX-11 y UX-12):** `<label class="sr">` con el texto del campo («Duración estimada de … en días») en las duraciones de
   Variedades; `aria-label` en los dos campos de archivo de Mi perfil. Nuevo invernadero: filtro nuevo `marcado_invalido`
   (`core/templatetags/formularios.py`) y parámetro opcional `invalido` en `core/usuarios/_campo.html` (clase `fld-invalido` y
   `aria-invalid="true"`); Provincia y Departamento lo pasan cuando Localidad tiene error y ellos están vacíos; regla
   `.fld.fld-invalido .field-input` (el mismo borde de `.fld:has(.err)`). `desplegable.js` copia el `aria-invalid` del `<select>` al botón
   del desplegable propio.
5. **Títulos (UX-15):** 74 `h3` pasan a `h2` en 35 plantillas y 2 `h4` (`.sec-h` de IoT) a `h3`. CSS: `.card-h h2` y `.panel h2` con las
   reglas de sus `h3`, y `.card-h h2,.panel h2,.vacio h2` con el peso 600 y sin el espaciado y el equilibrado del `h2` de página;
   `.vacio h2{margin:10px 0 4px;font-size:14px}` (decisión del estudiante, opción (b): no se toca `iot.css`).
6. **Recorrido:** `demo/tests/test_recorrido_accesibilidad.py` (`RecorridoDeAccesibilidadTests`), con los datos de la demo.

### Cosas compartidas que se tocaron (D-109 punto 2)

| Qué | Usos revisados | Efecto |
|---|---|---|
| `infoponia.css`: `.chip[aria-selected="true"]` | solo los dos chips de Cobranza tienen `aria-selected` | Cobranza se ve como antes |
| `infoponia.css`: `.fld.fld-invalido .field-input` | solo Provincia y Departamento de Nuevo invernadero pasan `invalido` | borde rojo nuevo, el pedido por la tarea |
| `infoponia.css`: `.card-h h2`, `.panel h2`, `.vacio h2` | en `main` no había ningún `h2` dentro de `.card-h`, `.panel` ni `.vacio` (`git grep`) | solo alcanzan a los títulos convertidos |
| `core/usuarios/_campo.html` (parámetro `invalido`) | 23 plantillas lo incluyen: clientes (formulario y cuatro parciales de dirección), vehículos, proveedores, alta y modificación de cuentas, vincular, catálogo, categorías, habilitar existencia, mínimo, variedades, configuración (organización y parámetros), cultivos, sectores, invernaderos (formulario, dirección, departamento y localidad, localidad) | sin el parámetro, el HTML es el mismo |
| `desplegable.js` (copia `aria-invalid`) | todo `select[data-desplegable]` | un atributo más en el botón cuando el `<select>` tiene error; no cambia el aspecto (el borde lo pone `.fld`) |
| `core/templatetags/formularios.py` (nuevo) | `_campo.html` | — |

### Diferencias con la tarea y con la revisión (para `docs/temas_abiertos.md`)

- **`.sr` en lugar de `.sr-only`** (decisión del estudiante): `infoponia.css` ya tenía `.sr` con la regla estándar (71 usos). Los `<th>` de
  IoT e Inventario que ya usaban `.sr-only` (con su CSS de app) quedan como estaban.
- **El control de etiquetas saltea los campos con `aria-hidden="true"`** (aprobado): el `username` oculto para el administrador de
  contraseñas (Mi perfil, Vincular, elegir contraseña) no llega al lector de pantalla.
- **Concretar cosecha ya tenía las etiquetas** en `main` (`<label for>` de plantas perdidas, causa y descripción); la red no la marcó con
  `capataz1`. No se cambió; el recorrido lo deja asegurado. La revisión probablemente la midió con la sección «declarar plantas perdidas»
  cerrada o antes de que el desplegable propio moviera la etiqueta al botón.
- **Mi perfil:** la `<label for="f-cam">` existía, pero en computadora está oculta (`.btn.cam{display:none}`), así que no da nombre al
  campo; se sumó `aria-label` a los dos campos de archivo.
- **Columnas que no son de acciones:** la columna del medio del Libro diario no es de acciones; se nombró «Descripción». Lo mismo con las
  otras cinco del punto 2 de «Qué se hizo».
- **IoT, estado vacío:** «… no tiene Sistema IoT» de `monitoreo/_panel.html:9` y `sistema/pagina.html:19` sí están dentro de
  `.card-b.vacio` (el `<div>` abre en la línea anterior), así que los cubre `.vacio h2`.
- **Diferencia mínima de aspecto, a mirar en el paso 12:** los `h3.ped-sub` de Registrar recepción y los `h3.sec-h` del formulario de
  Sistema IoT pasan a `h2` y toman el `letter-spacing:-.01em` y el `text-wrap:balance` del `h2` de página (0,14 px menos entre letras a
  14 px), igual que los `h2.ped-sub` que ya existían en Generar orden, Pedido nuevo y Pagos, y el `h2.sec-h` de Configuración. No se les
  sacó para no cambiar esos otros.
- **`desplegable.js`** ahora anuncia como inválido todo desplegable con error (Django ya ponía `aria-invalid` en el `<select>`, pero el
  `<select>` queda oculto para los lectores): alcanza a más pantallas que Nuevo invernadero.
- **Para UI-06 (pendiente, no se tocó):** Django 5.2 pone `aria-describedby="id_<campo>_error"` en los campos con error, pero el
  `<div class="err">` de `_campo.html` no tiene ese `id`, así que la referencia queda colgando. Conviene resolverlo junto con los
  contenedores de error de UI-06.
- **Pruebas en local:** sin `tblib`, con `--parallel` una prueba que falla tumba la corrida entera («cannot pickle 'traceback' object») en
  vez de informar el fallo. Para ver los fallos de la red se corrió sin `--parallel`.

### Línea de base

`demo/tests/datos/pantallas_esperadas.json` no cambió: ninguna ruta ni código cambió.

### Pruebas

- Nuevas: las cuatro `test_ui03_…` de `RedDePantallasTests`, las cuatro de `ControlesDeAccesibilidadTests`,
  `test_ui03_ninguna_plantilla_tiene_un_enlace_con_aria_pressed` y `RecorridoDeAccesibilidadTests`.
- Actualizadas: ninguna. Grep de pruebas antes de cambiar: solo `iot/tests/test_comandos_vistas.py:267` afirma `<th>…</th>` (no la
  columna de acciones); las de `aria-pressed` de Estadísticas son de `<button>` y no cambian; ninguna prueba buscaba `<h3>`.

### Comandos

- `python manage.py test --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` (el de «Hecho cuando», con `--noinput`
  para recrear las bases `test_…` sin preguntar, D-101): **11.426 pruebas, OK** (671 s).
- `python manage.py test demo.tests.test_red_de_pantallas --keepdb` (sin `--parallel`): 16 pruebas, OK (70 s).
- `python manage.py test demo.tests.test_recorrido_accesibilidad --keepdb`: 1 prueba, OK.

### Verifiqué

- Paso 1: los cuatro controles fallaban con el inventario de arriba; los 11 de UI-02 pasaban.
- Paso 2 a 5: la red (16 pruebas, 70 s, sin `--parallel`) pasa entera; las pruebas de `core`, `comercial`, `compras`, `contabilidad`,
  `inventario`, `iot`, `maestros`, `produccion` y `estadisticas` pasan (11.331 pruebas, con `--parallel`, después del paso 2).
- El recorrido pasa; `node --check` de `desplegable.js` sin errores. Sin migraciones (no hay nada que `sqlmigrate`).
- En la base de desarrollo no se tocó nada.

### Lo cubre una prueba

- Encabezados, enlaces, etiquetas y títulos en todas las pantallas de la demo: las cuatro `test_ui03_…` de la red.
- Enlaces con `aria-pressed` en todas las plantillas: `test_ui03_ninguna_plantilla_tiene_un_enlace_con_aria_pressed`.
- Atajos activos, pestañas de Cobranza, Libro, Variedades, Mi perfil, Concretar cosecha y los tres estados de Nuevo invernadero:
  `test_ui03_recorrido_de_las_pantallas_tocadas_por_rol`.

### No pude verificar

- El aspecto (que los `h2` y los chips se vean igual, el borde rojo), la voz del lector de pantalla, el teclado y el desplegable propio:
  son CSS, JavaScript y lectores de pantalla (D-96); van en la «Verificación a mano».

### Pantallas: lo que se corrigió del prototipo

No aplica: la tarea no parte de un prototipo.
