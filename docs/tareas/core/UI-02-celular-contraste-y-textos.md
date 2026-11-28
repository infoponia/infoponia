# UI-02 · Red de pantallas, celular, contraste, enlaces y textos desactualizados (D-109, tanda 1)

Estado: hecha | App: core (toca plantillas y textos de `produccion`, `comercial`, `inventario`, `maestros`, `compras` y `contabilidad`, y crea una prueba en `demo`) | Rama: feature/ui-02-celular-contraste-y-textos | Ronda: —

Depende de: — (es la primera del lote «Revisión de interfaz»; las demás UI la esperan porque usan su red de pantallas)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Esta tarea no cambia lo que el sistema hace, solo cómo se ve y qué dice.** La regla de no romper de D-109 (punto 2) manda sobre
todo lo demás: si un arreglo de esta lista necesita tocar un modelo, un servicio, una ruta, un nombre de campo o un gancho de
JavaScript, frená y preguntá.

## Hallazgos incluidos

| ID | Qué | Detalle |
|---|---|---|
| UX-01 | El contenido se sale de la pantalla en el celular | `docs/revision_interfaz_2026-11-27.md`, fila UX-01 |
| UX-03 | `--faint` y texto blanco sobre colores de etapa sin contraste | fila UX-03 |
| UX-05 | Enlaces en azul del navegador y pestañas subrayadas | fila UX-05 |
| UX-08 | Flecha de «volver» hacia abajo en 26 plantillas | fila UX-08 |
| UX-21 | «Sistema operativo» en el pie | fila UX-21 |
| UX-23 | Textos con códigos internos o que contradicen al código | fila UX-23 |
| UX-35 | Erratas | fila UX-35 |

## Leer

- Decisiones: D-109 (entera), D-25, D-29, D-47, D-57 (solo «Decisión», punto 2), D-96
- Revisión: `docs/revision_interfaz_2026-11-27.md` (las filas de la tabla de arriba)
- Reglas: .claude/rules/interfaz.md (entera, con la sección nueva de D-109), .claude/rules/pruebas.md
- Patrón: docs/patrones/verificacion_a_mano.md
- Código: `core/static/core/css/infoponia.css`; `core/templates/core/base_con_sesion.html`; `core/templatetags/iconos.py`;
  los CSS de app que repiten `a.tab` (`compras/static/compras/css/compras.css`, `contabilidad/static/contabilidad/css/contabilidad.css`,
  `inventario/static/inventario/css/inventario.css`, `maestros/static/maestros/css/cultivos.css`); `core/tests/test_interfaz.py`
  (cómo prueba hoy el CSS y las plantillas); `demo/carga.py`, `demo/tests/test_recorrido_demo.py` y los mixins que usa
  (`PlanDeCuentasMixin`, `ConDatosDeInventario`); las plantillas y vistas que nombra cada paso.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de `core`: las plantillas de la lista del paso 4; el aviso de cobro en `comercial/views_cobranza.py` y la
  advertencia de `comercial/templates/comercial/solicitudes/ficha.html`; los textos de `DESCRIPCION_DE_CUENTA` en
  `contabilidad/cuentas.py` (solo los textos, no los códigos de cuenta); `produccion/templates/produccion/_seccion_de_inicio.html` y
  `produccion/templates/produccion/concretar.html`; los cuatro CSS de app de «Leer» (solo para quitar `a.tab`); los textos visibles
  que encuentre la red de pantallas (paso 1), con la lista en el plan; `demo/tests/test_red_de_pantallas.py` y
  `demo/tests/datos/pantallas_esperadas.json` (nuevos); las pruebas que afirmen un texto que esta tarea cambia.
- Dependencias nuevas: ninguna.
- Fuera de alcance: todo lo de UI-03 a UI-08. El menú desplegable del celular es de UI-05 (acá solo se arregla el desborde).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Red de pantallas, antes de cambiar nada** (D-109, punto 3). Creá `demo/tests/test_red_de_pantallas.py`:
   - Carga UNA vez (`setUpTestData`) los datos de la demo con `carga.cargar`, con los mismos mixins y el mismo `Contexto` que
     `demo/tests/test_recorrido_demo.py`.
   - Para cada una de las diez cuentas: inicia sesión con el cliente de Django y recorre las pantallas **siguiendo los enlaces
     internos** (`href` que empiezan con `/`) desde `/`, hasta 120 por cuenta. Después pide, solo para guardar su código, cada ruta GET
     sin parámetros que resuelve (`get_resolver`) y que el recorrido no visitó. Excluí `/admin/`, `/api/`, `/static/`, `/media/`,
     `cerrar-sesion` y `cambiar-de-cuenta`. Con los datos de la demo son unas 1.300 respuestas y tarda unos 25 segundos (prototipo
     del 27/11/2026).
   - Por cada pantalla: (a) no devuelve 500; (b) su código es el de la línea de base; (c) en las respuestas 200 con HTML, el texto
     visible (sin comentarios HTML, `<script>` ni `<style>`; con `placeholder`, `title`, `alt` y `aria-label`) no tiene códigos
     internos. Patrones prohibidos: `\b(USR|AUD|MAE|INV|PRD|PROD|CMP|COM|IOT|CON|UI|DOC|DIA|EST|SEG|NOT|DAT|ADM)-\d{2}[a-z]?\b`,
     `\b[A-Z]{3,4}-[A-Z]{3}-[A-Z]{3}\b` (códigos de caso de uso), `\bD-\d{2,3}\b` y la palabra «ronda». Los códigos de documento
     de cuatro dígitos («OT-0004», «SUM-0001», «P-0001», «COB-0001») no coinciden con esos patrones y están permitidos.
   - El mensaje de falla lista cuenta, ruta y lo encontrado, para que sirva de inventario.
   - **Escaneo de fuentes**, en la misma prueba o al lado (`core/tests/test_interfaz.py`): la red solo ve lo que la demo muestra, y
     muchos textos salen después de un POST. Por eso, con los mismos patrones, recorré también: las plantillas `.html` y `.txt` de
     todas las apps, sin `{% comment %}…{% endcomment %}`, `{# … #}`, `<!-- … -->` ni las etiquetas `{% … %}`; y las líneas de las
     vistas con `messages.success(`, `messages.info(`, `messages.warning(` o `messages.error(`. El prototipo de este escaneo encontró
     dos casos el 27/11/2026: `comercial/templates/comercial/solicitudes/ficha.html` («COM-07b») y `comercial/views_cobranza.py`
     («ronda»). La red encontró otros ocho en `/contabilidad/plan-de-cuentas/`: las descripciones de `DESCRIPCION_DE_CUENTA` en
     `contabilidad/cuentas.py` nombran casos de uso («CON-INI-EJE», «PROD-REG-APL», «COM-REG-CBR»…).
   - Generá la línea de base `demo/tests/datos/pantallas_esperadas.json` (lista ordenada de `[cuenta, ruta, código]`) con el
     código **de hoy, antes de tocar nada**, con un comando o una función de la misma prueba que la escriba cuando una variable de
     entorno lo pide (`RED_PANTALLAS_ESCRIBIR=1`). Nunca se regenera sin revisar la diferencia: en el «Cierre» va cuántas líneas
     cambiaron y por qué.
   - Corré la prueba. Las partes (a) y (b) tienen que pasar ya. La (c) va a fallar con los textos de UX-23 y los que encuentre: **mostrame
     la lista y frená** (es la revisión de las pruebas que fallan de `.claude/rules/pruebas.md`). Con esa lista armamos el paso 5.
2. **Marco en el celular (UX-01).** En `infoponia.css`:
   - `.shell` (escritorio) usa `var(--sidebar-width) minmax(0,1fr)`;
   - `.shell.field`, `.shell.sin-lateral` y `.shell:not(.field)` dentro de `@media(max-width:760px)` usan `minmax(0,1fr)`;
   - `.mnav .chip{flex-shrink:0;white-space:nowrap}`.
   Antes de cambiar, Grep de `grid-template-columns` en `infoponia.css` y en los CSS de app, y de `.shell` y `.mnav` en todas las
   plantillas; la lista va al plan. Pruebas en `core/tests/test_interfaz.py` (con el estilo de las que ya leen el CSS): las cuatro reglas
   usan `minmax(0,1fr)` y `.mnav .chip` no se encoge.
3. **Contraste (UX-03).** `--faint` pasa a `#5f6b78` (o al gris que elijas, si cumple 4,5:1 sobre `#fff`, `#f9fafb`, `#f5f6f8` y
   `#eaf5ee`; decí cuál en el plan). Grep de `--faint`, `.faint` y `var(--faint)` en todo el repo: revisá que ninguno quede ilegible ni
   igual a otro estado que hoy se distingue (por ejemplo, `.sec.off`). Buscá el texto blanco sobre color de etapa (el gráfico de
   duraciones de Variedades, `span[title^="Germinación:"]` y similares) y pasalo a texto oscuro sobre fondo claro, como `.etapa`.
   Prueba: el contraste de `--faint` contra esos cuatro fondos, con la misma función que usa
   `test_d29_boton_secundario_cumple_contraste_wcag_aa`.
4. **Enlaces, pestañas y flecha (UX-05 y UX-08).**
   - Estilo base para los enlaces del contenido (`main a:not(.btn):not(.chip):not(.tab):not(.nav-item):not(.rowlink):not(.gh)` o la
     forma que propongas, que no cambie los enlaces con forma de botón ni el menú): color `--primary` y subrayado. Revisá con Grep
     las clases de enlace existentes (`a.nav-item`, `a.chip`, `a.btn`, `a.gh`, `a.rowlink`, `a.pop-act`, `a.icon-btn`, `.link`,
     `.back`) y listá en el plan cuáles quedan igual.
   - `a.tab{display:inline-block;text-decoration:none}` y `a.tab:focus-visible{…}` pasan a `infoponia.css` y salen de los cuatro CSS
     de app.
   - En estas 26 plantillas, `<a class="back" …>{% icono "chev" 14 %}` pasa a `{% icono "back" 14 %}`:
     comercial/templates/comercial/camara/merma.html, comercial/templates/comercial/cosechas/cancelar.html,
     comercial/templates/comercial/cosechas/concretar.html, comercial/templates/comercial/cosechas/modificar.html,
     comercial/templates/comercial/cosechas/planificar.html, comercial/templates/comercial/envasado/carga.html,
     comercial/templates/comercial/envasado/resumen.html, comercial/templates/comercial/rutas/concretar.html,
     comercial/templates/comercial/rutas/finalizar.html, comercial/templates/comercial/rutas/iniciar.html,
     comercial/templates/comercial/rutas/intento_fallido.html, comercial/templates/comercial/solicitudes/anular.html,
     comercial/templates/comercial/solicitudes/ficha.html, inventario/templates/inventario/ajuste/pantalla.html,
     produccion/templates/produccion/cancelar.html, produccion/templates/produccion/concretar.html,
     produccion/templates/produccion/concretar_transicion.html, produccion/templates/produccion/detalle.html,
     produccion/templates/produccion/fuera_de_servicio.html, produccion/templates/produccion/nueva_siembra.html,
     produccion/templates/produccion/nueva_transicion.html, produccion/templates/produccion/registrar.html,
     produccion/templates/produccion/registrar_aplicacion.html, produccion/templates/produccion/registrar_evento.html,
     produccion/templates/produccion/registrar_lote_existente.html, produccion/templates/produccion/registrar_merma.html
     (confirmá la lista con Grep; si hay más, sumalas).
   Pruebas: ninguna plantilla tiene `class="back"` con `icono "chev"` (recorriendo los archivos, como
   `test_plantillas_los_comentarios_de_una_linea_cierran_en_la_misma_linea`); `a.tab` está en `infoponia.css` y en ningún CSS de app.
5. **Textos (UX-21, UX-23 y UX-35)**, con la lista del paso 1:
   - Pie: «Sistema operativo» pasa a «En línea» (`base_con_sesion.html`), igual que en el modo campo.
   - **Cada texto con un código interno o que contradice al código**: leé el servicio que hay detrás y escribí lo que hace hoy, sin
     códigos. Los dos conocidos:
     - el aviso de `registrar` en `comercial/views_cobranza.py`: el cobro genera su asiento desde CON-04d
       (`asientos_comerciales.asentar_cobro`), así que la frase «El asiento no se genera en esta ronda (contabilidad).» sale; podés
       decir «Se registró su asiento.» si el servicio lo garantiza (mirá qué pasa si el importe es cero: H11);
     - la advertencia de la ficha de la solicitud: COM-07b ya resuelve el contrato, así que «Hasta que se complete COM-07b, el
       contrato queda «vigente».» sale; la advertencia dice lo que pasa al aceptar (el contrato se resuelve y se aplica la multa),
       según `resoluciones.resolver_si_corresponde`.
     - las descripciones de `DESCRIPCION_DE_CUENTA` en `contabilidad/cuentas.py`: el código del caso de uso se cambia por su nombre
       en palabras («el asiento de apertura del ejercicio», «la aplicación de insumos sin lote»). Se muestran desde la constante, no
       se guardan en la base: no hace falta migración. Antes, buscá en `docs/decisiones/` si alguna decisión fija esos textos
       (por ejemplo, D-84); si los fija, frená y preguntá.
     Si en algún texto no está claro qué hace el código, **frená y preguntá** (D-109, punto 7).
   - Erratas: «orden/ordenes próxima(s)» en `produccion/_seccion_de_inicio.html` pasa a «orden próxima» / «órdenes próximas» (con
     `{% if %}`: `pluralize` no pone la tilde); el doble punto del aviso de cobro cuando la razón social termina en punto; «200
     unidad» en `produccion/concretar.html` (la unidad en plural cuando la cantidad no es 1; mirá cómo la muestran las otras pantallas
     de stock antes de inventar).
   - Cada prueba que afirme uno de estos textos se actualiza (no se borra) y va al «Cierre».
   - La red de pantallas pasa entera.
6. **Cierre y verificación.** Comando de pruebas completo (abajo), la red de pantallas y M1 a M4.

Si el tiempo apremia, lo último que se recorta es: el paso 3 en lo que no sea `--faint` (se anota en `docs/temas_abiertos.md`).

## Hecho cuando

- A 360 px, ninguna pantalla con sesión es más ancha que la ventana: lo comprueba la prueba de CSS y la verificación a mano.
- `--faint` cumple 4,5:1 sobre los cuatro fondos.
- Ningún «volver» usa `chev`; `a.tab` vive solo en `infoponia.css`.
- La red de pantallas pasa entera, con su línea de base de antes de los cambios y sin códigos internos.
- No cambió ningún modelo, migración, servicio, ruta ni nombre de campo: `makemigrations --check` sin cambios y `git diff --stat`
  en el «Cierre».
- Comando de pruebas: python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion
  (la suite entera: los cambios son compartidos y pueden afectar a cualquier app). Si tarda demasiado en tu máquina, decilo en el
  plan y corré al menos `core`, `demo` y las apps de las plantillas tocadas; el CI corre todo en el PR.

## Verificación a mano (la completa Claude Code al cerrar)

Esta tarea no cambia lo que el sistema hace: lo que hay que mirar es cómo se ve y qué dice. La red de pantallas ya comprobó, con las diez
cuentas de la demo, que ninguna pantalla da error, que todas dan el mismo código que antes y que ninguna muestra códigos internos. Lo que
sigue es lo que una prueba no puede ver: el ancho real en un celular, los colores y los íconos.

**Antes de empezar**

- En la terminal: `python manage.py runserver` y abrí `http://localhost:8000/` en Chrome o Edge.
- **Modo celular:** con la página abierta, `F12` y después `Ctrl+Shift+M` (barra de dispositivos). Arriba, en «Dimensiones», elegí
  «Responsivo» y escribí `360` de ancho y `800` de alto. Para volver a computadora, `Ctrl+Shift+M` otra vez y la ventana a pantalla
  completa (al menos 1366 px de ancho).
- Cuentas: un **Gerente**, un **Agrónomo** a cargo de un invernadero, un **Capataz** de ese invernadero, un **Vendedor** y un **Contador**.
  Sirve cualquier base con datos; si usás la base `infoponia_demo` de `cargar_demo` (D-NN de DAT-01), ya están todas, con el correo
  `<base>+gerente1@gmail.com`, `+agronomo1`, `+capataz1`, `+vendedor1` y `+contador1`, y la contraseña de la variable de la demo.
- Datos que hacen falta, en este orden (si no los tenés):
  1. Una variedad con su ciclo (Agrónomo → Producción → «Cultivos y variedades» → «Nueva variedad», por ejemplo «Lechuga mantecosa» con
     todas sus etapas).
  2. Una siembra planificada para el Capataz **para dentro de 3 días** (Agrónomo → Producción → «Órdenes de trabajo» → «Nueva siembra»:
     30 plantines, fecha de hoy + 3) y, para el paso 9, una segunda para hoy + 4. No tiene que haber ninguna para hoy.
  3. Un cliente cuya razón social termine en punto (Vendedor → Comercial → «Clientes» → «Nuevo cliente», persona jurídica, «Verduras del
     Sur S.A.», CUIT de ejemplo `30-71234560-0` o cualquiera válido) con un suministro y al menos una entrega concretada sin pagar.
     Con la demo, sirve «Súper Del Parque» o el cliente que tenga una entrega por cobrar en «Comercial» → «Cobranza» → «Por cobrar».

**1. El celular no se sale de la pantalla (UX-01) — Gerente a 360 px.**
   Entrá como Gerente con el modo celular a 360 px. En el Panel de control:
   - No tiene que haber barra de desplazamiento horizontal en la página: arrastrá hacia la izquierda; la página no se mueve.
   - El botón de la cuenta (el círculo con la sigla, arriba a la derecha) y la campana se ven enteros. Tocá la campana: el panel se abre
     de borde a borde con 8 px de margen y no se corta. Cerralo. Tocá el botón de la cuenta: se abre el menú de cuenta.
   - Debajo del encabezado está la fila de módulos (Panel de control, Producción, Comercial…). Deslizala de costado: se mueve **dentro de su
     lugar** y la página sigue midiendo 360 px. Ninguna ficha de la fila se parte en dos líneas.
   - Abrí «Comercial» → «Clientes» y «Contabilidad» (si el Gerente la ve): la página sigue en 360 px; una tabla ancha se desplaza dentro de
     su recuadro (que las tablas se vean como tarjetas es de UI-05).
   *Lo cubre una prueba* (las reglas del CSS): `MarcoEnElCelularTests`. El ancho real solo se ve acá.

**2. Capataz a 360 px (modo campo).** Entrá como Capataz con el modo celular a 360 px. El marco es la columna angosta de siempre.
   El botón de la cuenta y la campana se ven y abren (el menú de cuenta sube desde abajo). Abajo, el pie verde dice «En línea».
   Pasá a 1366 px: el marco del Capataz sigue siendo una columna de 430 px en el medio (D-25, no cambia).

**3. Computadora a 1366 px — Gerente.** Sin modo celular. El menú lateral y el contenido se ven como antes. El pie dice
   «**En línea**» a la izquierda y la fecha a la derecha (antes decía «Sistema operativo»). *Lo cubre una prueba:*
   `test_ui02_el_pie_dice_en_linea_en_la_oficina_y_en_el_modo_campo`.

**4. Contraste del gris claro (UX-03).** En el menú lateral, el rótulo «Módulos» y, en la campana, la fecha de cada aviso, ahora se leen
   en un gris más oscuro (el mismo de los textos secundarios). Siguen siendo más claros que el texto negro. En un formulario por pasos
   (por ejemplo «Nueva siembra»), las secciones todavía no habilitadas siguen viéndose apagadas: el número en un círculo gris y el título
   en gris, distintos de la sección activa (número verde). *Lo cubre una prueba* (el cálculo del contraste):
   `test_ui02_faint_cumple_contraste_sobre_los_cuatro_fondos`.

**5. El ciclo de una variedad (UX-03).** Agrónomo → Producción → «Cultivos y variedades» → abrí la variedad del paso 1 de «Antes de
   empezar» («Modificar»). La franja del ciclo muestra cada etapa con su **nombre en texto oscuro sobre un fondo claro del color de la
   etapa** y una raya del color lleno abajo (antes, texto blanco sobre el color lleno). Las etapas se siguen distinguiendo por color. En la
   lista de variedades, la franja fina de la columna del ciclo sigue con los colores llenos, como antes. *Lo cubre una prueba* (el contraste
   de cada etapa): `test_ui02_el_texto_del_ciclo_no_es_blanco_y_cumple_contraste_en_cada_etapa`.

**6. La flecha de «volver» (UX-08).** Agrónomo → Producción → «Órdenes de trabajo» → «Nueva siembra»: arriba, el enlace de «volver» tiene
   la **flecha hacia la izquierda** (antes, hacia abajo). Lo mismo como Capataz en «Concretar siembra» de una orden, y como Gerente en
   Comercial → «Entregas» → «Asignar transportista» de una entrega (antes, el carácter «‹»). *Lo cubre una prueba* (todas las plantillas):
   `test_ui02_todo_volver_usa_el_icono_back_y_nunca_chev`.

**7. Pestañas sin subrayado (UX-05).** Como Gerente, a 1366 px: las pestañas de «IoT», de «Comercial» (Contratos, Entregas, Cobranza,
   Solicitudes de revisión), de «Configuración» y de la ficha de un invernadero (Producción → «Invernaderos» → uno) **no están
   subrayadas**; la activa tiene la raya verde abajo. Navegá con `Tab` hasta una pestaña: se ve el borde verde de foco.
   *Lo cubre una prueba* (la regla vive solo en la hoja común): `test_ui02_la_regla_de_las_pestanas_enlace_vive_solo_en_infoponia_css`.

**8. Enlaces del contenido en verde (UX-05).** Como Gerente, en la ficha de un invernadero con sistema IoT, el dato «Sistema IoT» dice
   «Activo» (o «Desconectado») **en verde y subrayado** (antes, azul del navegador). Pasá el mouse: se oscurece. Los botones, las fichas
   de filtro y los enlaces de las filas de las tablas («Ver», «Abrir») se ven como antes. En el inicio del Capataz, «Ver todas» también va
   en verde. En el inicio de Comercial (Gerente o Vendedor), las tarjetas de indicadores que son enlaces ya no tienen el número en azul ni
   subrayado.

**9. «órdenes próximas» (UX-35).** Como Capataz, con la siembra del paso 2 de «Antes de empezar» (solo la de hoy + 3), el Inicio dice
   «Nada para hoy · Tenés **1 orden próxima**.». Con la segunda (hoy + 4): «Tenés **2 órdenes próximas**.», con tilde. *Lo cubre una
   prueba:* `test_ui02_sin_ordenes_para_hoy_cuenta_las_proximas_con_el_plural_con_tilde`.

**10. La unidad en «Concretar siembra» (UX-35).** Como Capataz, en «Mis órdenes», abrí «Concretar» de una siembra de 30 plantines. En
    «3 · Insumos», la semilla dice «reservado: 30 **unidades**» (antes «30 unidad»). Si la siembra reservó un insumo en litros, dice «L»
    (antes «l»). *Lo cubre una prueba:* `test_ui02_lo_reservado_lleva_la_unidad_en_plural_y_con_su_etiqueta`.

**11. Registrar un cobro y leer el aviso (UX-23 y UX-35).** Como Vendedor (o Gerente): Comercial → «Cobranza» → «Por cobrar» →
    «Registrar cobro» del cliente que termina en «S.A.». Marcá la entrega, elegí «Transferencia», «Calcular total», «Revisar» y
    «Confirmar cobro». El aviso dice **«Se registró el cobro COB-0001 de Verduras del Sur S.A.: $ 1.600,00.»** (con el número y el monto
    que correspondan): un solo punto al final, y nada de «El asiento no se genera en esta ronda». Después, como Contador, Contabilidad →
    libro de gestión: está el asiento «Cobro COB-0001». *Lo cubren pruebas:* `test_confirmar_registra_el_cobro_y_lleva_a_su_ficha_con_el_aviso`
    y el recorrido de cobranza.

**12. Advertencia de una solicitud de revisión (UX-23) — opcional, necesita un contrato al límite.** Si tenés un suministro que ya usó
    todos sus incumplimientos tolerados y una solicitud de revisión pendiente sobre una de sus entregas: como Gerente, Comercial →
    «Solicitudes de revisión» → abrila y elegí aceptarla. Antes de confirmar, la advertencia roja dice «Con esta aceptación se superan los N
    incumplimientos tolerados: SUM-000X se resolverá y se aplicará la multa de $ …». Ya **no** dice «Hasta que se complete COM-07b, el
    contrato queda «vigente»». *Lo cubre una prueba:* el escaneo de plantillas (`test_ui02_las_plantillas_no_tienen_codigos_internos`).

**13. Plan de cuentas sin códigos (UX-23).** Como Contador: Contabilidad → «Plan de cuentas». Las descripciones nombran las operaciones en
    palabras («el asiento de apertura del ejercicio», «la aplicación de insumos sin lote», «la resolución de un suministro») y ninguna dice
    «CON-INI-EJE», «PROD-REG-APL», «COM-RSV-SUM» ni otro código. «Productos en Proceso» ya no dice que la mueven las transiciones (solo
    sus mermas). *Lo cubre la red de pantallas.*

**14. Ventana de baja de una cuenta (UX-23).** Como Gerente: Usuarios → un Agrónomo que tenga alertas activas → «Dar de baja». La
    ventana lista «Alertas activas … Pasan al Gerente hasta que asignes otro Agrónomo.» sin «(regla 4 de 8.22)». Cancelá sin confirmar.
    *Lo cubre la red de pantallas.*

**15. Navegador real.** En una **ventana privada**, iniciá sesión como Vendedor y repetí el paso 11 **hasta confirmar el cobro**. Tiene que
    llegar a la ficha del cobro con el aviso. Si aparece «Prohibido (403)», «Verificación CSRF fallida» o un error en la consola (`F12` →
    «Consola»), avisá: el cliente de Django no ve esos encabezados.

**16. Opcional, sin JavaScript.** Con JavaScript desactivado (F12 → `Ctrl+Shift+P` → «Disable JavaScript»), a 360 px como Gerente: la página
    no se sale de la pantalla, la fila de módulos se desplaza y los «volver» y las pestañas se ven igual (son CSS, no dependen de JavaScript).

Después del merge, Claude en claude.ai repite el relevamiento del 27/11/2026 sobre `main` (D-109, punto 13).

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

1. **Red de pantallas** (`demo/tests/test_red_de_pantallas.py`, nuevo). Carga la demo una vez, entra con las diez cuentas, recorre los
   enlaces internos desde `/` y después pide las rutas GET sin parámetros que no visitó. Cada pedido corre en un `atomic` que se deshace (las
   pantallas no se afectan entre sí) y con la misma sesión. Comprueba (a) ningún 500, (b) el código de la línea de base
   `demo/tests/datos/pantallas_esperadas.json` y (c) ningún código interno en el texto visible. Al lado, el escaneo de fuentes: plantillas,
   `messages.*` y (pedido en la revisión del paso 1) las cadenas de servicios y vistas.
2. **Marco en el celular (UX-01):** `.shell`, `.shell.field`, `.shell.sin-lateral` y `.shell:not(.field)` (celular) con `minmax(0,1fr)`;
   `.mnav .chip{flex-shrink:0;white-space:nowrap}`.
3. **Contraste (UX-03):** `--faint` pasa de `#8a94a0` a `#5f6b78` (5,44 sobre `#fff`; 5,20 `#f9fafb`; 5,03 `#f5f6f8`; 4,87 `#eaf5ee`). Los
   tramos del ciclo de una variedad (`.ciclo span`, el único texto blanco sobre color de etapa del repo) pasan a texto oscuro sobre el color
   de la etapa al 22 % (de 6,3 a 7,1:1 según la etapa), con una raya de 3 px del color lleno; la versión `mini` (sin texto) queda igual.
4. **Enlaces, pestañas y flecha (UX-05, UX-08):** estilo base de los enlaces del contenido (`:where(main) a:where(:not(...))`, pesa como un
   `a` suelto: las reglas con clase siguen mandando); `a.kpi,a.opt` sin azul ni subrayado; `a.tab` y su foco pasan a `infoponia.css` y
   salen de `compras.css`, `contabilidad.css`, `inventario.css` y `cultivos.css`; las 26 plantillas de la lista con `{% icono "back" 14 %}`.
5. **Textos (UX-21, UX-23, UX-35):** pie «En línea»; aviso del cobro; advertencia de la solicitud; `DESCRIPCION_DE_CUENTA`; cinco textos en
   servicios; «orden próxima / órdenes próximas»; la unidad de lo reservado en «Concretar siembra».

### Diferencias con la tarea (para `docs/temas_abiertos.md`)

- **Tope del recorrido: 1.000, no 120**, y la red falla si una cuenta lo alcanza (decisión del estudiante al revisar el paso 1). Con 120,
  las diez cuentas llegaban al tope y el 64 % del recorrido eran `/campana/?next=<página>` (la misma campana con otro «volver»). Ahora los
  valores de consulta que son una ruta cuentan como uno solo (`clave_de_recorrido`), y en la línea de base van como `*`. Con eso, el
  recorrido completo son 2.015 pedidos (1.289 pantallas distintas) en unos 65 s; la cuenta más grande, el Gerente, usa 623.
- **La comprobación (c) también corre sobre las rutas sueltas**, no solo sobre las pantallas del recorrido.
- **Patrones ampliados** (pedido del estudiante): además de los cuatro de la tarea, `MD-NN`, `UX-NN`, `CU-NN` y «regla N de».
- **Escaneo de cadenas de servicios y vistas** con `ast` (pedido del estudiante; la tarea pedía solo plantillas y `messages.*`). Sin
  docstrings; excluye las cadenas de `raise ValueError/RuntimeError/TypeError` (errores de programación: ninguna vista muestra su texto;
  las dos que atrapan `ValueError`, en `compras/views_recepciones.py`, responden 404).
- **Variables de entorno para revisar la red:** `RED_PANTALLAS_DIAS` (corre con otro «hoy»), `RED_PANTALLAS_TOPE` y `RED_PANTALLAS_INFORME`.
- **Dos «volver» fuera de la lista** pasaron al ícono `back`: `comercial/entregas/asignar.html` (sumó `iconos` a su `{% load %}`) y
  `comercial/entregas/no_reconocida.html`, que usaban el carácter «‹».
- **Textos en servicios, sin cambio de lógica** (permiso explícito del estudiante; la cita de la regla quedó en un comentario encima):
  - `maestros/servicios/invernaderos.py`: «Quedan sin Técnico; sin sistema IoT no generan alerta (regla 3 de 8.22). Lo asigna el Gerente
    al modificarlos.» → «Quedan sin Técnico; sin sistema IoT no generan alerta. Lo asigna el Gerente al modificarlos.»
  - `maestros/servicios/invernaderos.py`: «Pasa(n) al Gerente hasta que asignes otro Agrónomo (regla 4 de 8.22).» → «Pasa(n) al Gerente
    hasta que asignes otro Agrónomo.»
  - `produccion/servicios/registrantes.py`: «Pasan a quien el Gerente asigne como Capataz al modificar el invernadero (regla 3 de 8.22).» →
    sin el paréntesis.
  - `comercial/servicios/cosechas.py` (error `no_modificable`): «No se puede cambiar {…}: cancelá la orden y planificá otra
    (PROD-CNL-ORD).» → sin el paréntesis.
  - `comercial/servicios/cosechas.py` (advertencia `lotes_no_alcanzan`): «…hay que cancelar la orden (PROD-CNL-ORD); lo que quede…» → sin
    el paréntesis.
- **`a.kpi,a.opt{color:inherit;text-decoration:none}`** en la hoja común: las tarjetas de indicadores del inicio de Comercial y las opciones
  de «Registrar» de producción que son enlaces se veían en azul y subrayadas. `estadisticas.css` ya tenía `.est a.kpi` (la repetición es de UI-08).
- **«Productos en Proceso»** (decisión del estudiante): decía que la mueven las transiciones; la transición no asienta por sí misma, solo su
  merma (`produccion/servicios/asientos_de_produccion.py`).
- **Textos de `DESCRIPCION_DE_CUENTA`**, antes → después (solo texto; las pruebas leen el diccionario):
  - Capital Inicial: «el asiento de apertura (CON-INI-EJE)» → «el asiento de apertura del ejercicio».
  - Indemnizaciones a Pagar: «resolución del suministro (Haber, COM-RSV-SUM)» → «la resolución de un suministro (Haber)».
  - Indemnizaciones por Atraso en el Pago: «el pago en mora (COM-VNC-PAG, COM-REG-CBR)» → «el cobro de una entrega pagada con atraso» (el
    paso diario de mora solo alerta; `docs/temas_abiertos.md`, punto 9 de CON-04d).
  - Gastos de Producción: «(PROD-REG-APL)» sale.
  - Indemnizaciones por Incumplimiento: «la evaluación de discrepancias y de quejas (COM-EVL-DSC, COM-RSV-QJA)» → «la evaluación de
    discrepancias de una entrega y la resolución de quejas».
  - Indemnizaciones por Resolución: «La mueve: COM-RSV-SUM.» → «La mueve: la resolución de un suministro.»
  - Diferencias de Inventario: «(CMP-AJT-STK)» sale.
  - Productos en Proceso: «siembra, transiciones, aplicaciones sobre lotes y lotes existentes (Debe); cosechas y mermas (Haber)» → «siembra,
    aplicaciones sobre lotes y lotes existentes (Debe); cosechas y mermas, también las de una transición, una cosecha o un sector fuera de
    servicio (Haber)».
- **Aviso del cobro:** «COB-… registrado: $ … cobrados a {cliente}. El asiento no se genera en esta ronda (contabilidad).» → «Se registró el
  cobro COB-… de {cliente}: $ ….». No dice «se registró su asiento» porque con importe cero no hay asiento (H11); terminar en el monto
  arregla el punto doble de «S.A.».

### Línea de base

- Generada con el código **antes de cambiar el sistema**: 1.289 pantallas (`[cuenta, ruta, código]`). Una primera versión, con el
  recorrido sin corregir (tope 120 y la campana repetida), tenía 1.896 líneas y se reemplazó antes del paso 2; el sistema no había cambiado.
- **Estable por fecha:** corrida con «hoy» +10 días (7/12/2026) y +40 días (6/1/2027, otro año y otro ejercicio) sin regenerar: 0 diferencias.
- **403 y 404 por origen:** ninguno sale de un enlace seguido. Los 777 (687 de 403, 54 de 404 y 36 de 405) salen de la fase de rutas
  sueltas: rutas de otros roles, enlaces de los portales sin token y rutas que solo aceptan POST. Nada que anotar por D-30 ni enlaces rotos.
- **Después de todos los cambios: 0 líneas cambiadas** (no se regeneró).

### Pruebas

Nuevas:
- `demo/tests/test_red_de_pantallas.py`: `RedDePantallasTests` (4: cada cuenta entra y ninguna llega al tope; ningún 500; el código de la
  línea de base; ningún código interno a la vista) y `EscaneoDeFuentesTests` (3: plantillas, `messages.*`, cadenas de servicios y vistas).
- `core/tests/test_interfaz.py`: `MarcoEnElCelularTests` (2), `ContrasteTests` (2), `EnlacesPestanasYVolverTests` (3) y
  `MarcoVistaTests.test_ui02_el_pie_dice_en_linea_en_la_oficina_y_en_el_modo_campo`.
- `produccion/tests/test_produccion_vistas.py`: `test_ui02_lo_reservado_lleva_la_unidad_en_plural_y_con_su_etiqueta` y
  `test_ui02_sin_ordenes_para_hoy_cuenta_las_proximas_con_el_plural_con_tilde`.

Cambiadas (ninguna se borró ni se debilitó):
- `comercial/tests/test_cobranza_vistas.py::RegistrarTests::test_confirmar_registra_el_cobro_y_lleva_a_su_ficha_con_el_aviso`: afirmaba
  «COB-… registrado» (del aviso viejo); ahora el aviso nuevo completo, con el monto, y que no dice «ronda».
- `comercial/tests/test_recorrido_cobranza.py` (paso del cobro confirmado): lo mismo.
- `iot/tests/test_sistemas_vistas.py::test_la_ficha_muestra_en_linea_si_el_nodo_se_comunico_hace_poco`: afirmaba el texto «En línea»
  suelto, que con el pie nuevo pasaría siempre; ahora afirma la insignia `status-ok` y que no dice «Sin señal» (queda más estricta).

### Comandos

- M1: `python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` (la suite entera): **11.416 pruebas en
  740 s, OK**. La red de pantallas y los escaneos, aparte: 7 pruebas en 66 s, OK.
- `python manage.py makemigrations --check --dry-run`: «No changes detected».
- `git diff --stat` (sin `docs/` ni `.claude/`): 45 archivos, 267 inserciones y 79 borrados, más los dos archivos nuevos de `demo/tests/`.
  Ningún modelo, migración, ruta, nombre de URL, `name`, `id`, `data-*`, `hx-*` ni JavaScript cambió (comprobado sobre el diff: los 28
  atributos y rutas de las líneas tocadas son los mismos antes y después). En servicios cambiaron solo los cinco textos de arriba.
- No se tocó la base de desarrollo: todo corrió en `test_infoponia`.

### Verifiqué

- La red de pantallas: 10 cuentas, 2.015 pedidos, ningún 500, los códigos de la línea de base, ningún código interno; estable con «hoy» +10 y +40 días.
- El escaneo de plantillas, avisos y cadenas de servicios y vistas: 0 hallazgos.
- `makemigrations --check`: sin cambios (la tarea no tiene migración: no hay `sqlmigrate`).

### Lo cubre una prueba

- Las reglas de CSS del marco, del contraste, de `a.tab` y de los enlaces: `core/tests/test_interfaz.py` (`MarcoEnElCelularTests`,
  `ContrasteTests`, `EnlacesPestanasYVolverTests`).
- La flecha de todos los «volver»: `test_ui02_todo_volver_usa_el_icono_back_y_nunca_chev`.
- Los textos: el pie (`test_ui02_el_pie_dice_en_linea…`), el aviso del cobro, la unidad y el plural (las de `produccion`), y la ausencia de
  códigos internos (la red y los tres escaneos).

### No pude verificar

- El ancho real a 360 px, los colores, la flecha y el subrayado: son del navegador (D-96). Pasos 1 a 10 de la «Verificación a mano».
- La advertencia de la solicitud con un contrato al límite (paso 12): la demo no tiene ese estado; la cubre el escaneo de plantillas.
- El envío real del cobro en un navegador (CSRF, `Origin`): paso 15.

### Pantallas: lo que se corrigió del prototipo

- Ninguna corrección de prototipo: la tarea partió de la revisión de interfaz, no del prototipo.
