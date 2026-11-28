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

Esta tarea no tiene migración ni modelos nuevos: no hace falta `migrate`. Lo que se prueba es del navegador (el salto de la página, el foco, el lector de pantalla),
que el cliente de Django no ve. Las pruebas ya cubren lo que sale en el HTML (qué elemento lleva la marca, que los obligatorios salen juntos, que un selector no valida).

### Antes de empezar

- Con el entorno virtual activo: `python manage.py runserver` y abrí `http://localhost:8000/`. Hace falta una cuenta de **Agrónomo** a cargo de un invernadero, la de su **Capataz** y la de un **Gerente**.
  (Las contraseñas no van en ningún archivo del repo: usá las tuyas.)
- Datos a crear a mano para Nueva siembra (si ya tenés un invernadero con producción, usalo y saltá lo que ya exista):
  1. Invernadero **«Norte UI06»**, con tu Agrónomo y un Capataz activo, y un sector de **Germinación** llamado **«Germ 1»** con **100 agujeros**.
  2. Variedad **«Lechuga UI06»** (perfil hoja verde) con su semilla habilitada en «Norte UI06» (Inventario → Variedades → Nueva variedad; después «Habilitar» desde «Qué sigue»).
  3. Stock de la semilla: Inventario → Ajustar stock → «Carga inicial», **500** unidades de la semilla, con vencimiento a un año.
- Para el paso del **navegador real** (portal sin cuenta) hace falta un enlace de portal: el de confirmar una entrega al cliente o el del pedido al proveedor. Si no tenés correo configurado, ponelo en consola
  (`CORREO_CONSOLA=1` en tu `.env`, sin copiar el archivo a ningún lado) y copiá el enlace que aparece en la terminal de `runserver`.
- Probá a **1366 px de ancho** (ventana normal) y a **360 px** (F12 → botón de dispositivo → «Dimensiones: 360 × 800», o un celular real). Entrá como **Agrónomo** salvo que el paso diga otro rol.
- La «ayuda de movimiento» (pasos 8 y 9): Windows → Configuración → Accesibilidad → Efectos visuales → «Efectos de animación».

### Pasos

1. **Nueva siembra, carga inicial (1366 px).** Producción y órdenes → «Nueva siembra». La página abre arriba, sin errores y sin que se mueva sola. *(Lo cubre una prueba: ninguna marca en la carga inicial.)*
2. **Un selector no mueve la vista (INV-02).** Elegí el invernadero «Norte UI06» y después la variedad «Lechuga UI06». Aparecen los campos de plantines y fecha **sin que la página salte**, sin errores y con el foco donde estaba. *(Lo cubre una prueba: el redibujo no trae marca ni error.)*
3. **Formulario vacío: los errores salen juntos y la vista va al primero (UX-24 y UX-27).** Sin escribir nada, tocá «Ver resumen». Tienen que verse **a la vez**: debajo de «Plantines», «La cantidad de plantines tiene que ser un número entero mayor que cero.»,
   y debajo de «Fecha programada», «Indicá la fecha programada.». La página **baja hasta el primero** (Plantines) y queda ahí. *(Lo cubre una prueba: los dos textos, y una sola marca en el primero. El salto lo ves solo vos.)*
4. **Una cosa por vez.** Escribí **30** en «Plantines», dejá la fecha vacía y tocá «Ver resumen»: queda **un solo error**, el de la fecha, y la vista va a él.
5. **Lo que depende de otro valor espera.** Elegí una fecha de mañana, escribí **10** en «Germ 1» y tocá «Ver resumen»: el único error es «La distribución tiene que sumar 30…» (el de siempre, no se adelantan otros). *(Lo cubre una prueba.)*
6. **El resumen a la vista (1366 px).** Cambiá «Germ 1» a **30** y tocá «Ver resumen». La página baja hasta la tarjeta **«Resumen de la orden»** (queda unos 1.200 px más abajo que el botón) y el foco queda en ella. Tocá «Confirmar planificación»: vuelve a la lista con el aviso y sin saltar.
7. **Lo mismo a 360 px.** Repetí los pasos 3 y 6 con el navegador a 360 px de ancho: los errores y el resumen se ven enteros y la página llega a ellos. Fijate que **el encabezado no tape** el error o el resumen al llegar.
8. **«Reducir movimiento».** Con los «Efectos de animación» de Windows **desactivados**, repetí el paso 3: el salto es **inmediato**, sin desplazamiento animado. Con ellos activados, el desplazamiento es suave. Volvé a dejar el ajuste como estaba.
9. **Teclado y Narrador (contrapartida de dejar el foco en el error).** Dejá Nueva siembra vacía con la variedad elegida. **Sin usar el mouse**: llevá el foco a «Ver resumen» con Tab y apretá Enter. Activá Narrador (Win + Ctrl + Enter). Tiene que ocurrir:
   a. el foco cae en el primer error (Plantines) y **Narrador lo lee** («La cantidad de plantines…»);
   b. al apretar **Tab**, el foco pasa al **campo siguiente** (no al campo con error: el error queda debajo del campo);
   c. con **Shift + Tab** llegás al campo «Plantines» para corregirlo.
   Anotá qué te pareció: si molesta, hay una alternativa (llevar el foco al campo) anotada como candidato para UI-08. *(No lo cubre una prueba: es del navegador y de Narrador.)*
10. **Concretar siembra, en el celular (Capataz, 360 px).** Entrá como el Capataz de «Norte UI06». Desde su bandeja, abrí la orden que creaste en el paso 6. Escribí **99** en «Sembrado» de «Germ 1» y tocá «Ver resumen»: la página va al error. Corregí a **30** → «Ver resumen»:
    va a la tarjeta «Resumen de la concreción». No confirmes si no querés concretar. *(Lo cubre una prueba, menos el salto.)*
11. **Otras pantallas con selectores: no mueven la vista.** «Registrar merma» (elegí invernadero y lote) y «Registrar aplicación» (elegí el invernadero): ningún salto ni error al elegir.
12. **Los obligatorios juntos en las otras pantallas (UX-27, enviá todo vacío en cada una):**
    - «Registrar lote existente»: marca **Cantidad, Fecha de siembra y Fecha de ingreso**.
    - «Registrar merma» (con un lote elegido): marca **la cantidad perdida y la causa**.
    - «Registrar aplicación» (con «sectores» elegido y sin marcar ninguno, y sin insumos): marca el **alcance** y **«Indicá al menos un insumo.»**.
    - Inventario → «Habilitar insumo» (ventana): marca **insumo, invernadero, stock mínimo y precio**. Es una ventana: el foco lo maneja ella y la página no salta.
    - Compras → «Nuevo pedido» → habilitar un insumo (bloque «Habilitar»): marca los **cuatro** campos.
    - IoT → «Registrar hardware» enviado vacío: marca **tipo de equipo, identificador, modelo e insumo**.
    - Comercial → «Entrega no reconocida» (con una alerta activa; como Gerente) enviada vacía: marca **resultado y descripción**.
    Escribí solo **espacios** en un campo de texto de esas pantallas: cuenta como vacío. *(Lo cubren las pruebas de «obligatorios juntos», con el texto del servicio.)*
13. **Planificar cosecha «cubre un contrato» sin elegir el detalle (defecto corregido).** Producción → Planificar cosecha → «Sí, cubre un contrato» sin elegir un detalle → «Ver resumen»: ahora aparece **«Elegí la variedad de la cosecha.»** debajo del detalle (antes la pantalla volvía sin mostrar nada) y la vista va a él.
14. **Un resumen por ventana y un resumen en otra página.** «Nueva compra-venta» → completá lo mínimo → «Revisar y registrar»: se abre la ventana de resumen (el foco es de la ventana, la página de atrás no salta). «Nuevo pedido» → «Revisar pedido»: va a otra página que abre arriba, sin salto.
15. **Sin JavaScript (opcional).** F12 → Configuración → «Desactivar JavaScript»; recargá Nueva siembra vacía → «Ver resumen»: los errores se ven igual, la página es la de siempre (no salta, y está bien).
16. **Navegador real (obligatorio: hay pantallas públicas y formularios que se envían).** Abrí el **enlace de un portal en una ventana privada** (sin sesión) a **360 px**. Tocá el botón de revisar **sin elegir nada**: aparece el error («Indicá si recibiste la entrega.» en el portal del cliente)
    y la página va a él. Después elegí «Recibí conforme», tocá «Revisar y enviar»: la página va al resumen. **Enviá el formulario hasta el final** y volvé a abrir el enlace: tiene que mostrar el resultado esperado.
    Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no ve.

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

- **Paso 1 · Inventario.** Se relevaron las pantallas con «Ver resumen», «Revisar» o «Calcular» (resumen por recarga, por HTMX, en una ventana o en otra página) y los formularios que enviados vacíos mostraban menos errores que obligatorios.
  Lo aprobó el estudiante antes de editar (obligatorios juntos: Nueva siembra, lote existente, merma de producción, aplicación, habilitar insumo, habilitar en «Nuevo pedido», alta de equipo IoT y entrega no reconocida; quedaron afuera la fecha de «fuera de servicio» y el medio de pago de «cancelar compra-venta»).
- **Paso 2 · Llevar la vista (UX-24).** `core/static/core/js/infoponia.js`: un bloque nuevo al final (31 líneas, ninguna otra cambió) que, al cargar y después de cada `htmx:afterSwap`, busca el primer `[data-llevar-vista]` visible, le hace `scrollIntoView({block: "start"})`
  (inmediato con «reducir movimiento») y le da el foco con `preventScroll`. No actúa con una ventana abierta (`[data-ventana]`) ni sobre un elemento ya llevado. **45 plantillas de 7 apps** marcan, con `data-llevar-vista tabindex="-1"`, el resumen cuando se muestra y el primer error cuando el envío vuelve con errores;
  la carga inicial, los selectores que redibujan (`accion=actualizar`, `show:none`, `data-sin-envio-en-curso`) y los resúmenes en ventana no llevan la marca.
- **Paso 3 · Errores juntos (UX-27).** `core/obligatorios.py` (`esta_vacio`, `faltantes`, `sumar_faltantes`): en 8 vistas, cuando el envío se rechaza, se suman los obligatorios independientes que vinieron vacíos y que el servicio no llegó a mirar, con el texto del servicio (cada vista cita el archivo y la línea). El error del servicio gana en su campo.
  «Vacío» es `None` o solo espacios, como en los servicios. Solo corre al enviar, nunca al redibujar. **Ningún servicio, mensaje, `name` ni `value` cambió.**

### Etiquetas de plantilla nuevas (`core/templatetags/vista.py`)

Son cuatro y las tres últimas se sumaron por lo que el inventario mostró:

- `primer_error` (devuelve el primer campo con error, en el orden de pantalla; acepta `"sector_*"` para filas) y `llevar_vista` (pone los dos atributos en ese error): para pantallas con un diccionario `errores` de claves fijas (producción).
- `llevar_vista_fila` (`prefijo` + ids): la misma idea para el error de una fila (`sector_12`, `reubicacion_4_9`), con la clave que arma la etiqueta `campo` de producción.
- `llevar_vista_una_vez`: marca el **primer** error o resumen que se dibuja en la respuesta, y solo en una respuesta a un envío (POST). Se sumó porque los portales por enlace, las filas anidadas y los resúmenes por HTMX no tienen un único diccionario con claves fijas. Su estado vive en el contexto de cada respuesta y lo comparten los `include` sin `only` (se revisó que ninguno use `only`).
  Que solo marque en POST lo encontró una prueba: «Concretar entrega» abre diciendo que falta el medio de pago y habría robado el foco al cargar.

### Pantallas: lo que se corrigió del prototipo (D-61)

- **Planificar cosecha, «cubre un contrato» sin elegir el detalle.** Tenía: el servicio rechaza en `variedad` («Elegí la variedad de la cosecha.», `cosechas.py:478`) y la plantilla solo dibujaba `errores.detalle` en ese modo: la pantalla volvía **sin mostrar nada**. Hice: se dibuja el error debajo del detalle (con `aria-invalid` en el selector) y lleva la vista. Lo pide D-109 punto 9 («los errores se ven») y lo aprobó el estudiante. El texto del servicio no cambió.
- **«Emitir comando» (IoT): la marca va en el título «Resumen del comando»**, no en el cuadro `div.resumen`, para que el lector anuncie el título y no arranque en medio de una lista de datos.

### Contrapartida de dejar el foco en el error (decisión del estudiante: A)

El `div.err` queda **después** del campo. Con el foco en el error, el siguiente Tab pasa al campo que sigue y quien navega con teclado necesita **Shift + Tab** para volver al campo con error. Se dejó así a propósito: D-109 punto 9 pide el foco en el primer error.
**Alternativa B (candidato para UI-08, no para esta tarea):** que `infoponia.js` lleve la vista al error y mande el foco al control de su `.fld`. Riesgos: (1) los desplegables propios de D-24 (`desplegable.js`) reemplazan al `<select>` y el foco habría que llevarlo al botón del desplegable, no al `<select>` oculto;
(2) los errores generales (sin campo: el aviso de arriba, «Indicá al menos un insumo.») no tienen un control al que mandar el foco; (3) sin foco en el texto, el lector de pantalla no lee el error: habría que sumar `aria-describedby` en cada campo con error (cambio de las plantillas de todas las apps).

### Pruebas

- **Comando de «Hecho cuando»:** `python manage.py test --parallel --exclude-tag concurrencia --exclude-tag migracion` → **11.592 pruebas, OK** (con `main` ya integrado: UI-03 y UI-05; base de pruebas recreada con `--noinput`). Ninguna prueba de servicio cambió y no se borró ninguna prueba.
  **Tres pruebas existentes se modificaron, a pedido del estudiante:** `comercial/tests/test_com_reg_cbr.py:88`, `comercial/tests/test_modelos_cobranza.py:179` (`^COB-\d{4}$`) y `comercial/tests/test_prod_asg_stk.py:367` (`^OT-\d{4}$`) pasan a `\d{4,5}`.
  Motivo: con `--keepdb` la numeración de la base de pruebas se acumula entre corridas completas y, pasadas unas diez, un código llega a 5 dígitos (`OT-14657`) y esas pruebas fallaban por el formato y no por una regla. La intención (el formato `OT-NNNN` o `COB-NNNN`) no cambia.
  El resto de las pruebas son archivos nuevos. Las comparaciones con `{numero:04d}` ya aceptan 5 dígitos y no se tocaron.
- **Pruebas nuevas (unas 150), en 13 archivos:** `test_ui06_llevar_vista.py` en `core` (el script y las etiquetas), `produccion`, `comercial`, `inventario`, `iot`, `compras` y `contabilidad` (por pantalla: carga inicial sin marca, resumen y primer error con exactamente una marca, selectores sin marca);
  `test_ui06_obligatorios_juntos.py` en `produccion`, `inventario`, `compras`, `iot` y `comercial` (obligatorios juntos con el texto del servicio comparado, campo de solo espacios, selector sin errores, una sola marca en el primer error);
  y el recorrido `produccion/tests/test_recorrido_resumen_y_errores.py` (`RecorridoDeResumenYErroresTests`).
- **Red de pantallas** (`demo/tests/test_red_de_pantallas.py`): pasa sin tocar `pantallas_esperadas.json`.

### Verifiqué (recorrido y migraciones)

- **Recorrido** `RecorridoDeResumenYErroresTests`: Nueva siembra de punta a punta por rol (Gerente 404 y Capataz 403 en la pantalla del Agrónomo) y estado (carga inicial, selectores, vacía, solo la fecha, distribución mal, resumen, confirmar, y la concreción del Capataz con error y resumen). **OK.**
- **Migraciones:** no hay (la tarea no crea modelos ni migraciones; `git status` no muestra archivos en `migrations/`). No hizo falta `sqlmigrate`.

### Lo cubre una prueba

- Una sola marca en el resumen o en el primer error, y ninguna en la carga ni en el redibujo de un selector: `test_ui06_*` de cada app (`test_ui06_llevar_vista.py`).
- Los obligatorios independientes salen juntos con el texto del servicio, y los dependientes esperan: `test_ui06_enviada_vacia_*`, `test_ui06_con_la_cantidad_valida_y_la_distribucion_mal_*` (`test_ui06_obligatorios_juntos.py`).
- El script y su versión (`static_v`): `core/tests/test_ui06_llevar_vista.py` (`LlevarLaVistaScriptTests`); el orden de `primer_error` y las etiquetas: `PrimerErrorTests` y `LlevarVistaEtiquetaTests`.

### No pude verificar

- **El salto, el foco y el lector de pantalla:** son del navegador (Narrador, Tab y Shift + Tab, «reducir movimiento», 360 y 1366 px). Van en la «Verificación a mano» (pasos 3, 6 a 10).
- **El navegador real en un portal sin cuenta** (CSRF, `Origin`, JavaScript): paso 16 de la «Verificación a mano».
- **Las 8 pantallas de «Habilitar» y compañía en un celular real** y **sin JavaScript:** pasos 12 y 15, opcionales.

### Para otras tareas (no se corrigió en silencio)

Está en el texto que se propone para `docs/temas_abiertos.md` (ver el informe de cierre de la sesión): la repetición de los textos del servicio en las vistas (deuda de mantenimiento protegida por las pruebas de comparación), las altas largas con errores abajo en el celular (UI-08),
los errores en voseo del portal del cliente (UI-04), `required` sin `novalidate` en la ventana de cancelar orden de IoT, los selectores sin `data-sin-envio-en-curso`, el `data-sin-envio-en-curso` de «Ver resumen» de pago, y que en «Concretar entrega» con HTMX los errores de cada campo no se redibujan.
