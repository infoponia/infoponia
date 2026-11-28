# UI-05 · Celular, segunda parte: menú desplegable y tablas como tarjetas (D-109, tanda 3a)

Estado: hecha | App: core (toca plantillas de listas de todas las apps) | Rama: feature/ui-05-menu-y-tablas-en-el-celular | Ronda: —

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

Esta tarea no cambia lo que el sistema hace: cambia cómo se ve **en pantallas de menos de 760 px de ancho** (el celular). A 1366 px tiene que
verse igual que antes. La red de pantallas ya comprobó con las diez cuentas de la demo que cada celda de las tablas elegidas tiene su
rótulo, y el recorrido (`demo/tests/test_recorrido_celular.py`) comprobó que «Menú» trae las mismas entradas que el menú lateral y que cada
una abre. Lo que sigue es lo que una prueba no puede ver: el aspecto, el ancho de la ventana, el teclado y el JavaScript.

**Antes de empezar**

- En la terminal: `python manage.py runserver` y abrí `http://localhost:8000/` en Chrome o Edge.
- **Modo celular:** con la página abierta, `F12` y después `Ctrl+Shift+M`. En la barra de arriba elegí «Responsivo» y poné `360` de ancho y
  `800` de alto. **Modo computadora:** `Ctrl+Shift+M` otra vez (se apaga) y la ventana a pantalla completa, de al menos 1366 px de ancho.
- **Sin JavaScript:** con `F12` abierto, `Ctrl+Shift+P`, escribí `javascript`, elegí «Disable JavaScript» (o «Desactivar JavaScript») y
  recargá con `F5`. Para volver, `Ctrl+Shift+P`, «Enable JavaScript» y `F5`.
- Cuentas: un **Gerente**, un **Agrónomo**, un **Vendedor**, un **Contador** y un **Capataz**. Si usás la base `infoponia_demo` de
  `cargar_demo` (DAT-01), ya están (`<base>+gerente1@gmail.com`, `+agronomo1`, `+vendedor1`, `+contador1`, `+capataz1`, con la contraseña
  de la variable de la demo) y tiene clientes, entregas y cobros: saltate la lista de abajo.
- Datos que hacen falta, si no usás la demo, en este orden:
  1. Dos clientes (Vendedor → Comercial → «Clientes» → «Registrar cliente»): «Verónica Paz», CUIT `20-12345678-6`, correo
     `veronica@ejemplo.com`, teléfono `3764 111111` y una dirección cualquiera; y «Huerta Sur S. A.» (tipo empresa), CUIT `30-12345678-1`.
  2. Para ver «Entregas» con datos hace falta una compra-venta con envío ya cargada y su producto listo: es largo de armar a mano
     (Comercial → «Contratos» → «Nueva compra-venta» → modalidad «Envío», y después cosecha y envasado). **Usá la demo para este paso.** Sin la
     demo, la lista de Entregas muestra su aviso «No hay entregas a realizar…» como una sola tarjeta: hacé el paso con eso y anotalo en
     «No pude verificar».
  3. Una orden de compra, un pedido y un proveedor para Compras (Agrónomo → Compras): sin datos esas listas muestran su aviso vacío, que
     también es una tarjeta.

**1. «Menú» en el celular (UX-07) — Gerente, 360 px.** Entrá como Gerente, con el modo celular puesto. En el encabezado, **a la izquierda
   del logo y del nombre de la organización**, hay un botón blanco con borde verde, un ícono de tres rayas y la palabra «Menú». **La fila de
   fichas grises que antes aparecía debajo del encabezado ya no está.** Tocá «Menú»: se despliega un panel blanco debajo del encabezado, a todo
   el ancho de la pantalla (con 8 px de margen a cada lado), con **todas** las entradas del Gerente, una debajo de otra y en el mismo orden que en el menú lateral de computadora (son unas 13:
   por ejemplo «Panel de control», «Contabilidad», «Producción», «Bitácora», «Compras», «Estadísticas», «Usuarios y seguridad», «Auditoría» y
   «Configuración»). La entrada de la pantalla en la que estás («Panel de control») se ve con fondo verde
   claro y letras verdes. Arrastrá la página hacia los costados: **no se mueve de costado** (antes la fila de fichas se desplazaba). Si la
   lista es más alta que la pantalla, el panel se desplaza hacia abajo dentro de sí mismo. *Lo cubren:*
   `test_ui05_el_menu_del_celular_trae_las_mismas_entradas_que_el_lateral_para_cada_rol` y el recorrido (las entradas, no el aspecto).

**2. Ir a un módulo y volver — Gerente, 360 px.** Con «Menú» abierto, tocá «Contabilidad»: se abre su pantalla y el panel está **cerrado**.
   Tocá «Menú» otra vez: «Contabilidad» está resaltada. Tocá «Panel de control»: volvés al inicio. Con el botón «atrás» del navegador:
   volvés a Contabilidad y el panel sigue cerrado (no se queda abierto). *Lo cubre el recorrido* (que cada entrada abre).

**3. Cerrar con Esc — Gerente, 360 px.** Abrí «Menú» y apretá `Esc`: el panel se cierra y el botón «Menú» queda con el borde de foco (verde,
   separado del botón). Apretá `Enter`: se abre de nuevo. `Esc` otra vez: se cierra. *No lo cubre una prueba: es JavaScript.*

**4. Cerrar tocando afuera — Gerente, 360 px.** Abrí «Menú» y hacé clic en una parte vacía del contenido (por ejemplo, sobre el título de la
   pantalla, no sobre un enlace): el panel se cierra. Abrí «Menú» y tocá el botón de la cuenta (el círculo con las iniciales, arriba a la
   derecha): «Menú» se cierra y se abre el menú de la cuenta. *No lo cubre una prueba: es JavaScript.*

**5. Con el teclado — Gerente, 360 px.** Con `Tab` llegá a «Menú» (se ve el borde de foco), abrilo con `Enter` o con la barra espaciadora,
   recorré las entradas con `Tab` (cada una muestra su borde de foco) y entrá a una con `Enter`.

**6. Sin JavaScript — Gerente, 360 px.** Desactivá JavaScript (ver «Antes de empezar») y recargá. Tocá «Menú»: se abre. Tocá «Menú»
   otra vez: se cierra. Abrilo y tocá una entrada: navega. `Esc` y el clic afuera **no** cierran el panel (eso necesita JavaScript; es lo
   esperado). Volvé a activar JavaScript.

**7. Los otros roles — 360 px.** Entrá como **Agrónomo**: «Menú» trae «Panel de control», «Producción» y sus demás módulos. Como **Vendedor**:
   «Panel de control» y «Comercial». Como **Contador**: «Panel de control», «Contabilidad», «Compras» y «Pagos a proveedores». Para cada
   uno, pasá a 1366 px y compará la lista del menú lateral con la de «Menú»: son las mismas, en el mismo orden. *Lo cubre*
   `test_ui05_el_menu_del_celular_trae_las_mismas_entradas_que_el_lateral_para_cada_rol`.

**8. A 1366 px nada cambió — Gerente, 1366 px.** No hay botón «Menú» en el encabezado. El menú lateral está a la izquierda, con las mismas
   entradas, el mismo orden y la entrada activa resaltada, como antes. Achicá de a poco el ancho de la ventana (o escribí el ancho en la
   barra del modo celular): **por encima de 760 px** sigue el menú lateral; **por debajo de 760 px** el lateral desaparece y aparece «Menú».

**9. Clientes como tarjetas (UX-02) — Vendedor, 360 px.** Comercial → «Clientes». **Cada cliente es una tarjeta** blanca con borde y esquinas
   redondeadas, una debajo de otra, con un espacio entre ellas. Arriba, el nombre del cliente (más grande) con su tipo debajo; después pares
   «rótulo: valor» con el rótulo gris a la izquierda y el valor a la derecha: «CUIT» (`20-12345678-6`), «Contacto» (el correo y el
   teléfono), «Direcciones», «Contratos vigentes» y «Estado» (la insignia verde «Activo»); y al final, separado por una línea fina, el enlace
   «Ver». **No se ve la fila de encabezados de la tabla y la página no se desplaza de costado.** Tocá «Ver»: abre la ficha. Buscá algo que
   no existe (por ejemplo, `zzz`) y «Filtrar»: aparece **una sola tarjeta** con el aviso «Ningún cliente coincide con la búsqueda.»
   centrado. *Lo cubre el recorrido* (las celdas y sus rótulos, no el aspecto).

**10. Entregas como tarjetas — Vendedor, 360 px (con la demo).** Comercial → «Entregas». Cada entrega es una tarjeta: arriba el código de la
    entrega con el del contrato debajo; después «Cliente y destino», «Fecha» (con «Hoy», «En 2 días» o «Atrasada» debajo), «Peso»,
    «Transportista» y «Estado»; al final, los enlaces «Ver contrato» y, según corresponda, «Asignar transportista», «Cambiar
    transportista» o «Concretar retiro», **en una fila que se parte en dos si no entran**. Una entrega «Sin transportista» conserva la
    franja de color en el borde izquierdo del título, como tenía en la tabla. Los códigos (por ejemplo el de la entrega) **no se cortan en dos
    líneas**.

**11. Contratos, Cobranza, Solicitudes, Faltantes y Vehículos — 360 px.** Como Vendedor: Comercial → «Contratos» (compra-ventas y, con el
    selector, «Suministros»), «Cobranza» (las dos vistas: «Cobros registrados» y «Por cobrar», donde cada cliente es un desplegable con las
    entregas adentro), «Solicitudes de revisión» y, si hay compra-ventas con faltante, el botón «Faltantes para decidir (N)» de «Contratos».
    Como Gerente: la pestaña «Vehículos». Todas se leen como tarjetas, con el rótulo de cada dato y las acciones al final. En «Por cobrar»,
    abrí un cliente: las entregas se ven como tarjetas dentro del desplegable, sin desbordar.

**12. Compras, Cuentas, Contabilidad e Inventario — 360 px.** Como **Gerente**: «Usuarios y seguridad» (cada cuenta es una tarjeta con
    «Rol» y «Estado» y el botón «Ver» al final); Compras → «Pedidos», «Órdenes», «Proveedores» y «Reclamos» (las pestañas de Compras que tu
    rol vea); «Pagos a proveedores» (las dos tablas, «A pagar» y las ya hechas); Contabilidad → pestaña «Ejercicios». Como **Agrónomo**:
    Compras → «Por recibir»; Inventario → pestañas «Catálogo» y «Categorías» (en el Catálogo los botones de lápiz y papelera quedan en una
    fila al final de la tarjeta, y **no hay desplazamiento de costado**, aunque la tabla tenía un ancho mínimo) y las variedades
    (Producción → «Cultivos y variedades»). Las listas sin datos muestran su aviso como una tarjeta. En las variedades, fijate que el texto
    del ciclo no se salga de la tarjeta.

**13. Lo que sigue como tabla — Contador, 360 px.** Contabilidad → «Libro de gestión» (vistas «Cronológica» y «Por cuenta»), «Plan de
    cuentas»; y, como Agrónomo, Inventario → «Existencias de insumos»: **siguen como tabla con desplazamiento de costado dentro de su caja**; la
    página no se ensancha y el resto de la pantalla (título, pestañas, filtros) se ve entero. Es a propósito: las filas de asiento y de
    movimiento, el saldo corrido y las filas de grupo pierden sentido apiladas. *Lo cubre el recorrido* (que el libro no tiene
    `.tabla-apilable`).

**14. A 1366 px las tablas no cambiaron — 1366 px.** Con la ventana ancha, «Clientes», «Entregas», «Cuentas», «Proveedores» y «Catálogo»
    se ven como siempre: **la misma tabla, con las mismas columnas en el mismo orden** (Clientes: Cliente, CUIT, Contacto, Direcciones,
    Contratos vigentes, Estado y la columna de acciones sin título) y el encabezado gris a la vista. *Lo cubre*
    `test_ui05_en_escritorio_el_bloque_solo_oculta_el_menu_del_celular` (la hoja de estilos), no el aspecto.

**15. El modo campo no cambió — Capataz, 360 px y 1366 px.** Entrá como Capataz: el marco angosto de siempre, **sin botón «Menú»** y sin
    menú lateral, con el pie verde «En línea». A 1366 px sigue en una columna angosta, centrada. Repetilo con un Técnico y con un
    Transportista (con la demo: `+tecnico1`, `+transportista1`). *Lo cubre* `test_ui05_el_modo_campo_no_muestra_el_menu_del_celular` y
    `test_ui05_el_modo_campo_no_cambia`.

**16. Lector de pantalla (opcional) — 360 px, Narrador de Windows (`Ctrl + Windows + Enter`).** Con «Menú» enfocado, el Narrador dice
    «Menú, botón» y si está contraído o expandido. Dentro del panel, cada entrada se lee como enlace, y la actual dice «página actual». En
    una lista apilada (Clientes), recorré una tarjeta: tiene que leer cada dato con su rótulo («CUIT 20-12345678-6»). Fijate si dice «tabla»:
    con CSS que cambia el `display` de una tabla, algunos navegadores dejan de anunciarla como tabla; si pasa, avisá (va a «No pude
    verificar»).

**17. Navegador real.** Esta tarea no tiene pantallas públicas ni formularios nuevos, pero **sí JavaScript** (Esc y clic afuera) y CSS que
    depende del ancho real: hacé los pasos 1 a 6 en el navegador de verdad (no solo en el modo celular de `F12`) con la ventana angosta, y
    abrí la consola (`F12`, pestaña «Console»): no tiene que haber errores rojos. Si tenés un celular a mano, después del despliegue,
    entrá desde ahí a Clientes y probá «Menú» con el dedo (el botón tiene que ser fácil de tocar: 44 px de alto).

## Cierre (la completa Claude Code al cerrar)
### Qué se hizo

1. **Menú del celular (UX-07).** Parcial nuevo `core/templates/core/_menu_entradas.html` con el bucle del menú que antes estaba escrito
   dos veces; lo incluyen el `<aside class="side">` y el nuevo `<details class="menu-celular" data-menu-celular>` del encabezado
   (`base_con_sesion.html`). Las dos listas salen de `menu` (`core/menu.py` → `context_processors.marco`): no se armó otra lista, y una
   entrada nueva aparece en los dos lados. El `<details>` solo se dibuja si `mostrar_menu_lateral`, así que el modo campo no lo recibe. Ícono
   nuevo `menu` (tres rayas) en `iconos.py`. Salió la fila `<nav class="mnav">` de la plantilla y sus cinco reglas del CSS.
2. **JavaScript** (`infoponia.js`, bloque nuevo después del menú de cuenta): con el menú abierto, `Esc` lo cierra y devuelve el foco a
   «Menú»; un clic afuera lo cierra; y `pageshow` lo cierra si el navegador restaura la página con el menú abierto (al volver atrás). Sin
   JavaScript, el `<details>` abre y cierra solo.
3. **Tablas como tarjetas (UX-02).** `class="data-table tabla-apilable"` y `data-rotulo="<texto del th>"` en cada `<td>` de datos de **19
   plantillas y 21 tablas**: Comercial (Clientes, Contratos, Suministros, Entregas, Cobranza —las dos—, Solicitudes, Vehículos, Faltantes), Compras (Órdenes,
   Pedidos, Proveedores, Reclamos, Pagos —las dos—, Por recibir), Cuentas, Contabilidad (Ejercicios) e Inventario (Catálogo, Categorías,
   Variedades). La celda de acciones y la fila de «no hay datos» (`colspan`) no llevan rótulo. Ni el orden ni el contenido de las columnas
   cambió. Un script de una sola vez (no versionado) puso los atributos y avisó si una fila tenía distinta cantidad de `<td>` que de
   `<th>`: ninguna.
4. **CSS** (`infoponia.css`): **un bloque propio**, `/* ---- UI-05 … */`, después del bloque «marco con sesión: menú de cuenta y celular»
   y antes de `.grid2`. Fuera del `@media`, solo oculta `.menu-celular` y le saca el marcador al botón; dentro de `@media(max-width:760px)`,
   el botón, el panel y las tarjetas. Las tarjetas usan el patrón de `position:relative` + `td::before{content:attr(data-rotulo)}` (y no
   `display:flex` en la celda) porque en una celda con varios elementos (`<b>` y un `<span class="sub2">`) un contenedor flex los separaría.
5. **Quedan con desplazamiento horizontal (a propósito, D-109 y la tarea):**
   - `contabilidad/libro.html` (las tres tablas): las filas de asiento (`colspan`) y de movimiento (con una celda vacía y sangría) y el mayor
     con saldo corrido se leen comparando columnas; apiladas pierden el sentido.
   - `contabilidad/plan.html`: el árbol de rubros y subrubros (filas de grupo con `colspan`).
   - `inventario/existencias/lista.html`: su primera columna es el botón que despliega los lotes, y las filas de lote (`.lotlist`, que ya
     tiene su versión angosta) son filas de `colspan`.
6. **Pruebas:** ver «Pruebas». **Recorrido:** `demo/tests/test_recorrido_celular.py`.

### Cosas compartidas que se tocaron (D-109 punto 2)

| Qué | Usos revisados | Efecto |
|---|---|---|
| `base_con_sesion.html` (marco) | lo extienden todas las pantallas con sesión | el `<aside>` queda con el mismo HTML de salida (ahora por el parcial); sale la fila `.mnav`; entra el `<details>` solo para los roles con menú lateral |
| `infoponia.css`: `.mnav` (5 reglas) | `git grep mnav`: solo `base_con_sesion.html`, `infoponia.css` y `core/tests/test_interfaz.py`; el resto son documentos y prototipos (no se tocan) | salen de todos lados; la prueba que las afirmaba se actualizó |
| `infoponia.css`: bloque UI-05 | `.menu-celular*` y `.tabla-apilable*` son clases nuevas; `.tablewrap:has(.tabla-apilable)` solo alcanza a las tablas marcadas | en escritorio, solo `.menu-celular{display:none}` |
| `infoponia.js` | bloque nuevo, después de la línea 34; UI-06 agrega desde la 503 en su rama | no toca el menú de cuenta ni nada existente |
| `iconos.py` | clave nueva `menu`; ninguna existente cambió | — |
| `.tablewrap` (CSS de escritorio) | no se tocó | — |
| `td[data-rotulo]` | `comercial.css` y `compras.css` ya usan `data-etiqueta` en `.portal-resumen` (otra tabla, del portal) | no se cruzan: otro nombre y otra clase |

### Diferencias con la tarea y con la revisión (para `docs/temas_abiertos.md`)

- **Vehículos y Faltantes (de Comercial) se sumaron a pedido del estudiante**, al cerrar: la tarea no los nombra, pero la revisión (UX-02)
  habla de «listas de Comercial». Misma receta (la clase y los rótulos, sin CSS nuevo).
- **Listas que la tarea no nombra y quedaron como estaban:** Auditoría, IoT (hardware, reglas, tipos, comandos, monitoreo), Producción
  (órdenes de trabajo, detalle), Estadísticas, y las tablas de ficha y de resumen.
- **`data-rotulo` también en la primera celda**, aunque el CSS no la muestra (es el título de la tarjeta): así la prueba de la red es una
  sola regla («toda celda de datos») y el atributo sirve si un día el título se muestra con rótulo.
- **La prueba de escritorio compara la hoja de estilos, no el aspecto:** que a 1366 px «nada cambió» es lo que afirma
  `test_ui05_en_escritorio_el_bloque_solo_oculta_el_menu_del_celular` (el bloque no tiene reglas de escritorio salvo ocultar el menú) y lo que
  el paso 14 mira a mano.
- **Entrada activa por prefijo (ya existía, no se cambió):** `core.context_processors.marco` marca una entrada como activa también en sus
  pantallas internas, por prefijo de la URL; en «Bitácora» están activas «Producción» y «Bitácora» a la vez, en el menú lateral y ahora en
  «Menú». El recorrido exige que las dos listas marquen lo mismo.
- **`.mnav` del prototipo** (`docs/temas_abiertos.md`, fila «`.mnav` del prototipo»): la fila del prototipo ya no tiene equivalente en el
  sistema; el menú del celular es un botón «Menú». La fila de temas abiertos queda vieja: proponerla para corregir.
- **Tablas de los portales** (`.portal-resumen`): ya se apilaban en el celular con `data-etiqueta` y su propio CSS en `comercial.css` y
  `compras.css`. Es el mismo patrón con otro nombre; unificarlo es de UI-08 (sistema de diseño).
- **Lector de pantalla y `display:block` en tablas:** cambiar el `display` de una tabla puede hacer que algunos navegadores dejen de anunciarla
  como tabla. Quedó anotado en «No pude verificar» y en el paso 16.
- **Pruebas en local:** sin `tblib`, con `--parallel` una prueba que falla tumba la corrida entera («cannot pickle 'traceback' object») en vez
  de informar el fallo; así apareció el primer fallo de `test_usr_cns_usr` (el esperado, por el rótulo).

### Línea de base

`demo/tests/datos/pantallas_esperadas.json` no cambió: ninguna ruta ni código de respuesta cambió.

### Pruebas

- **Nuevas:** `MenuDelCelularTests` (5 pruebas, `core/tests/test_menu.py`); `TablasEnElCelularTests` (2, `core/tests/test_interfaz.py`);
  `test_ui05_las_tablas_apilables_tienen_rotulo_en_cada_celda` (red) y `ControlDeRotulosTests` (2, el control con HTML de ejemplo);
  `RecorridoDelCelularTests` (2, `demo/tests/test_recorrido_celular.py`).
- **Actualizadas, con el motivo (D-109 punto 2):**
  - `core/tests/test_interfaz.py`: `test_ui02_las_fichas_del_menu_del_celular_no_se_encogen` afirmaba la regla de `.mnav .chip`; la fila
    desaparece. Pasó a `test_ui05_el_menu_del_celular_no_ensancha_la_pagina`, que afirma lo mismo que UX-01 cuidaba (el panel va pegado a los
    dos bordes y se desplaza hacia abajo dentro de su lugar, así que no estira la página).
  - `core/tests/test_usr_cns_usr.py:476`: `<td>Administrador</td>` pasó a `<td data-rotulo="Rol">Administrador</td>` (el texto de la celda no
    cambió; ahora la celda trae su rótulo).
  - `demo/tests/test_recorrido_accesibilidad.py`: solo un comentario que nombraba el «chip» del menú del celular.
  - `iot/tests/test_monitoreo_vistas.py:474` (`test_regla_6_el_agronomo_ve_los_parametros…`): contaba los `<details>` de la página completa y
    esperaba 1 (el bloque de parámetros); el marco ahora suma el del botón «Menú». La cuenta excluye el que lleva `data-menu-celular`;
    lo que afirma (un solo plegable del panel) no cambió. La del fragmento del panel (línea 315) no se toca.
  - `demo/tests/test_red_de_pantallas.py`: `CONTROLES_DE_ACCESIBILIDAD` suma `CELDA_SIN_ROTULO`, así que el recorrido de UI-03 también lo mira.
- Ninguna prueba se borró ni se debilitó. Grep de pruebas antes de cambiar: `<td …>` en `comercial/tests/test_camara_vistas.py`,
  `contabilidad/tests/test_asientos_vistas.py`, `estadisticas/tests/…` e `iot/tests/…` son de plantillas que no se tocaron.

### Comandos

- `python manage.py test --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` (el de «Hecho cuando», con `--noinput`
  para recrear las bases `test_…` sin preguntar, D-101): **11.438 pruebas, OK** (1.159 s, la corrida final, con Vehículos y Faltantes ya apilados). La primera corrida cortó en una prueba de IoT (ver «Pruebas»); con el arreglo, pasa entera (665 s antes de sumar esas dos listas).
- `python manage.py test core.tests.test_interfaz core.tests.test_menu core.tests.test_usr_cns_usr demo.tests.test_recorrido_accesibilidad
  --keepdb --parallel`: 75 pruebas de `core` más el recorrido de UI-03, OK.
- `python manage.py test demo.tests.test_red_de_pantallas --keepdb --parallel`: 19 pruebas, OK (93 s).
- `python manage.py test demo.tests.test_recorrido_celular --keepdb --parallel`: 2 pruebas, OK.

### Verifiqué

- Paso 1: el menú del celular tiene las mismas entradas, en el mismo orden y con la misma activa que el lateral, para el Gerente, el
  Agrónomo, el Vendedor, el Contador y el Administrador; el modo campo no lo tiene; `grep mnav` solo queda en mis docstrings y en la prueba
  que afirma su ausencia.
- Paso 2: la red entera pasa con el control nuevo, con **más de 30 pantallas** con una `.tabla-apilable` y ninguna celda sin su rótulo
  (con las diez cuentas de la demo).
- Paso 3: el recorrido por rol (Gerente y Agrónomo abren cada entrada de «Menú»; el Vendedor, las cinco listas; el Contador, el libro sin
  tarjetas; el modo campo sin «Menú»).
- `node --check core/static/core/js/infoponia.js` sin errores. Sin migraciones: no hay nada que `sqlmigrate`.
- **Base de desarrollo:** no se tocó nada ni se borró ningún dato; las pruebas usan sus bases `test_…`.

### Lo cubre una prueba

- Las entradas de «Menú» = las del lateral, por rol; el modo campo sin «Menú»; la entrada activa: `MenuDelCelularTests` y el recorrido.
- Cada celda de las listas elegidas con su rótulo: `test_ui05_las_tablas_apilables_tienen_rotulo_en_cada_celda` (con las diez cuentas).
- A 1366 px el bloque no tiene reglas de escritorio salvo ocultar el menú: `test_ui05_en_escritorio_el_bloque_solo_oculta_el_menu_del_celular`.
- Las reglas de tarjeta (bloque, rótulo, encabezados solo para lectores, caja sin desplazamiento): `test_ui05_en_el_celular_cada_fila_es_una_tarjeta_con_su_rotulo`.

### No pude verificar

- **El aspecto** de «Menú» y de las tarjetas a 360 px, el ancho real de la ventana, `Esc`, el clic afuera, el foco y el comportamiento sin
  JavaScript: son CSS y JavaScript, y Claude Code no abre un navegador (D-96). Van en la «Verificación a mano» (pasos 1 a 15).
- **El lector de pantalla** con las tarjetas (si siguen anunciándose como tabla): paso 16.
- **Entregas con datos** en una base sin la demo (hace falta una compra-venta con envío y su producto listo); la red y el recorrido sí la
  recorren con la demo.

### Decisiones

Ninguna nueva: la tarea aplica D-109 (puntos 2 a 4). No hace falta `D-NN`.

### Pantallas: lo que se corrigió del prototipo

No aplica: la tarea no parte de un prototipo (el `.mnav` del prototipo queda como tema abierto, arriba).
