# COM-04c · Faltante y enlace del cliente (paso diario 27)

Estado: pendiente | App: comercial (y piezas de core) | Rama: feature/com-04c-faltante-y-enlace-del-cliente | Ronda: Comercial 1

Depende de: **COM-04b** (y, con ella, COM-04a: el camino de faltante sin enlace, la cámara y su asignación automática; y, desde COM-02,
USR-10: `core.correo.enviar_correo`). Si COM-04b no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La tercera parte de COM-04 (D-67, punto 2): cuando falta producto para una compra-venta, **el cliente decide** por un
**enlace sin cuenta** (D-65), o el Vendedor por él (COM-DCD-FLT), y el **paso diario 27** avisa los enlaces que vencieron sin respuesta.
Completa el camino de faltante de COM-04a con el enlace y el correo, y suma la anulación del enlace donde un detalle deja de esperar la
decisión. El enlace queda listo para que COM-06 lo reutilice en la confirmación de entregas.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-DCD-FLT | Decidir Faltante (y el paso diario 27) | docs/casos_de_uso/comercial/faltante.md | Paso 7 (planificar la entrega): COM-05a1 |
| PROD-CNC-CSC, PROD-CNL-ORD (cosechas), PROD-ASG-CAM, PROD-VNC-CAM, PROD-REG-MRM (cámara) | Lo que completa: el enlace del camino de faltante (crearlo, reemplazarlo o, sin correo, el aviso «registrá vos la decisión») y su anulación al cubrirse el detalle | Los extractos de COM-04a y COM-04b | La base es de COM-04a y COM-04b |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/faltante.md **completo** (con «Cambios ya decididos», «Cómo se aplica», «Pantallas» y «Lo que
  difiere del prototipo»); de cosecha.md (13a), camara.md (PROD-ASG-CAM, el detalle pendiente que se cubre; PROD-VNC-CAM 3a.2a),
  merma.md (10c) y cancelar_orden.md («Comercial 1»: cosechas, 8c y 8d), solo lo que dicen del enlace.
- Modelo: docs/modelo/comercial.md (**EnlaceCliente**, DetalleVenta, CompraVenta, «Pendientes de MD»).
- Decisiones: **D-65** (la de esta parte) y **D-64** (punto 12: el bloqueo del invernadero en COM-DCD-FLT), D-59, D-61, D-56, D-14, D-27,
  D-28, D-29, D-36, D-37, D-42, D-44, D-54, D-57, D-60; **D-67, punto 2**.
- Patrones: **docs/patrones/enlace_del_cliente.md**, docs/patrones/stock_maduro.md (sección 8: el camino de faltante),
  docs/patrones/bloqueos.md (sección `comercial`, «Cosecha y cámara»: el enlace siempre al final), docs/patrones/auditoria.md,
  docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: docs/api/notificaciones.md; `core/procesos.py` (su encabezado).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `VIEWS.portal`, `INIT.dcd`, `VIEWS.dcd`, `ACT['dcd-ok']`; la pantalla del
  Vendedor no está en el prototipo (D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-04b): `servicios/` (`faltantes.py`, `stock_maduro.py`, `cosechas.py`, `camara.py`,
    `merma_camara.py`, `compra_ventas.py`, `comprobantes.py`), vistas, plantillas (la ficha de la compra-venta), `apps.py`, fábricas;
  - `core/views.py` (`recuperacion_enlace`, como modelo de la entrada del enlace), `core/tokens.py`, `core/enlaces.py` (**ya existe**: lo creó IOT-02 el 22/11/2026, con `nuevo_token` y `resumen_de`),
    `core/models.py` (auditoría: `registrar`), `core/correo.py`, `core/procesos.py`;
  - `maestros/servicios/invernaderos.py` (`bloquear_invernadero_para_alertas`).

## Límites

- Crea modelos: en `comercial`, `EnlaceCliente` (D-65).
  → revisá docs/disparadores.md: nace el tipo `confirmacion_entrega` del enlace para COM-06 (paso 7).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_enlace_cliente.py`: `EnlaceCliente` con su índice parcial y sus restricciones;
  - `core/migrations/00NN_comercial_faltantes`: solo `choices` (acciones `decision_faltante`, `vencimiento_enlace`).
- Permitido fuera de `comercial`:
  - `core`: **no** `core/enlaces.py` (ya lo creó IOT-02, D-70 punto 1, tal como lo describe `docs/patrones/enlace_del_cliente.md`, «1.
    Piezas»: se usa sin cambiarlo); en
    `core/models.py`, `ROL_CLIENTE_ENLACE`, el argumento `rol_externo` de `registrar` (D-65 punto 8) y las acciones, `ETIQUETAS`,
    `VALORES_VISIBLES` (`estado` del enlace) y `ACCIONES_DE_NEGOCIO`; en `core/procesos.py`, solo el comentario (fila 27); el texto «Cliente
    (mediante enlace)» en la pantalla de auditoría;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna (`secrets` y `hashlib` son de la biblioteca estándar).
- `core/enlaces.py` ya existe (IOT-02, PR #52): esta tarea no lo crea ni lo cambia.
- Fuera de alcance: COM-CNL-CVT y la anulación de su enlace (COM-05b); la confirmación de entregas por el enlace (COM-06); el reenvío del
  enlace y «esperar otra fecha» (mejoras futuras); reintentos automáticos de correos (no hay cola).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y piezas de `core`** (D-65). `EnlaceCliente`; `core/enlaces.py` ya existe (IOT-02): se usa como está y sus pruebas
   no se duplican; `rol_externo`; las acciones. Fábrica `enlace(...)`.
   Pruebas: en `comercial/tests/test_modelos_cosecha_camara.py`, métodos nuevos (las restricciones del enlace); `core/tests/test_auditoria_rol_externo.py` (el rol
   guardado; `rol_externo` con un usuario lanza `ValueError`).
2. **Enlace del cliente** (`enlace_del_cliente.md`): `comercial/servicios/enlaces.py` (crear, reemplazar, anular, usar, vencer; el correo con
   `on_commit`).
   Pruebas: `test_enlaces.py` (sección 8 del patrón de stock y el patrón del enlace).
3. **El enlace en el camino de faltante y donde se anula**: `seguir_camino_de_faltante` suma `crear_enlace` (reemplaza el vigente; vencimiento
   con `dias_vigencia_enlace_faltante`) y el correo, o, sin correo, el vigente a `reemplazado` y la notificación «registrá vos la decisión»;
   PROD-ASG-CAM anula el enlace del detalle que deja de estar pendiente; el enlace se suma **al final** del orden de bloqueo de los casos de
   uso que tocan un detalle pendiente (`bloquear_enlace`, `docs/patrones/bloqueos.md`).
   Pruebas: en `test_camino_de_faltante.py`, con y sin correo, el enlace reemplazado; en `test_prod_cnc_csc.py` (13a), `test_prod_cnl_ord_cosechas.py`
   (8c y 8d), `test_prod_asg_cam.py` (el enlace anulado, el correo con `captureOnCommitCallbacks`), `test_prod_vnc_cam.py` (3a.2a) y la merma
   en cámara (10c), métodos nuevos con el enlace. Las pruebas existentes no cambian.
4. **Decidir faltante** (`faltante.md`) y el paso 27.
   Pruebas: `test_com_dcd_flt.py` (`ComDcdFltServicioTests`): una por postcondición (a a l) y extensión (\*a, 1a, 1a.2a, 2a con cada motivo,
   2b, 3a, 3b, 4a, 4b, 6a, 6b, 8a); la venta que queda cancelada; el detalle rechazado con cosecha «a realizar» (cancelada) y con líneas
   cosechadas (partidas con la fecha límite de la cosecha); el `on_commit` de PROD-ASG-CAM (l); el cliente dado de baja; el Gerente no ve
   «Registrar decisión»; el paso 27 (idempotente, una notificación). Concurrencia: dos envíos del mismo enlace; la decisión contra
   PROD-ASG-CAM que cubre el mismo detalle; cancelar una cosecha contra la decisión del cliente sobre el mismo detalle
   (`test_cancelar_cosecha_concurrencia.py`, método nuevo).
5. **Vistas, plantillas y lo que completa a COM-02.** Las páginas públicas del cliente (`/cliente/…`, sin menú) y «Registrar decisión de
   faltante» del Vendedor; la ficha de la compra-venta con lo pendiente (`faltante.md`, «Lo que completa a COM-02»). Vistas que solo
   orquestan, `rol_requerido` (las del cliente, sin), `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores por
   campo, aviso breve (D-29).
   Pruebas: `test_faltantes_vistas.py`: permisos (cada rol ve lo suyo y ningún botón lleva a un 403; los encabezados de `/cliente/`); el token
   que no queda en la URL; los flujos con HTMX y sin él.
6. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, lo que nace (el tipo `confirmacion_entrega` del
   enlace, COM-06); marcar COM-04c en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista
   «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, no se recorta nada de esta parte: es chica. No se recortan el enlace de un solo envío, los bloqueos ni las pruebas de
concurrencia.

## Hecho cuando

- El cliente decide un faltante por su enlace (una sola vez, con vencimiento) y, si no tiene correo o el enlace no salió o venció, lo decide el
  Vendedor; rechazar devuelve lo cosechado a la cámara (que lo vuelve a asignar) y cancela lo que no se cosechó.
- Todo caso de uso que deja un detalle «pendiente de decisión del cliente» crea o reemplaza el enlace; el que lo cubre, lo anula.
- Todas las pruebas de `produccion`, `maestros`, `core` y de las tareas anteriores de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial produccion maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la hace el estudiante; la escribió Claude Code al cerrar)

Hay migraciones nuevas (`comercial` 0007 y `core` 0039, solo `choices`) y una **variable de entorno nueva** (`URL_DEL_SITIO`). No hay datos cargados: los creás vos, a mano.

**Antes de empezar**
1. `python manage.py migrate` y `python manage.py runserver`; entrá a `http://localhost:8000`. En local, con `DJANGO_DEBUG=1` en tu `.env`, `URL_DEL_SITIO` vale `http://localhost:8000` sola. Para ver el correo en la terminal, `CORREO_CONSOLA=1` en tu `.env` (sin él, el enlace queda «No se pudo enviar» y el Vendedor recibe el aviso: es el camino del paso 8).
2. Cuentas que necesitás (con la contraseña de prueba que usás siempre): un **Gerente**, un **Agrónomo**, un **Capataz** y un **Vendedor**, y un invernadero activo con ese Agrónomo, ese Capataz y ese Vendedor, un sector en Maduración y una variedad con ciclo completo (los de COM-04b).
3. En «Configuración»: «Vigencia del enlace de decisión ante un faltante» = **2** días.
4. Dos clientes en «Comercial» › «Clientes»: **Verdulería Los Pinos S.R.L.** (CUIT `30712345671`, con correo `lospinos@ejemplo.com`) y **Verdulería Sin Correo S.A.** (CUIT `30000000090`, teléfono `1144445555`, **sin correo**).
5. Un lote en Maduración con **60 plantas** de la variedad, y una partida en cámara de **40 plantas** de esa variedad con fecha límite **hoy** (por ejemplo, concretando una cosecha sin contrato de 40, como en COM-04b). Dos compra-ventas con retiro en el invernadero, una por cliente, de **20 plantas** cada una a $10, que reserven de esa partida (se asignan solas con «Reasignar cámara»: `python manage.py proceso_diario --solo reasignar_camara`).

**Pasos** (lo marcado «lo cubre una prueba» ya lo verifica el recorrido; concentrate en lo que se ve y se siente)

1. **Generar el faltante.** Esperá a que pase la fecha límite de la partida (o corré `python manage.py proceso_diario --solo vencer_partidas_en_camara --fecha <mañana>`), y agotá antes el stock del lote (reservando las 60 con otra venta) para que no se pueda volver a cubrir. Resultado: las dos ventas pasan a «Pendiente de decisión del cliente». Entrá como **Vendedor** › Comercial › Contratos: en la ficha de la venta de Los Pinos tiene que decir «Pendiente de decisión del cliente», el producto y «desde el <hoy>», **«El cliente puede decidir hasta el <hoy + 2 días>»** y **sin** botón. En la de Sin Correo: «El cliente no tiene correo…» **con** el botón «Registrar decisión de faltante». *(Lo cubre el recorrido.)*
2. **El correo.** En la terminal de `runserver` (`CORREO_CONSOLA=1`) aparece el correo a `lospinos@ejemplo.com` con las cantidades pedida y disponible, la fecha pactada, el vencimiento y un enlace `http://localhost:8000/cliente/<código largo>/`. Copiá el enlace. La campana del Vendedor tiene además el aviso «CV-…: el cliente no tiene correo».
3. **Navegador real (obligatorio).** Abrí una **ventana privada** (sin sesión) y pegá el enlace. Tiene que pasar a `/cliente/enlace/` **sin el código en la barra de direcciones**, sin menú ni campana. Elegí «No recibir <variedad>» (con disponible 0 es la única opción); tocá **«Ver resumen»**: dice que la compra quedará cancelada y que la decisión no podrá modificarse. Tocá **«Cambiar»**: vuelve con tu elección marcada. Volvé a «Ver resumen» y **«Confirmar decisión»** hasta el final. Tiene que mostrar «Gracias. Recibimos su decisión.». Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: es un encabezado que el cliente de Django no ve. Con **F12 › Red**, comprobá que las respuestas de `/cliente/…` traen `Cache-Control: no-store`, `Referrer-Policy: same-origin` y `X-Robots-Tag: noindex`.
4. **Reabrir.** En la misma ventana privada, volvé a pegar el enlace: «Este enlace no se puede usar», «ya se usó», con nombre, teléfono y correo del Vendedor y **sin** datos de la venta. Un enlace inventado (cambiá una letra del código): «Este enlace no es válido». *(Lo cubre una prueba, pero conviene ver el texto.)*
5. **Auditoría y efectos.** Como **Gerente** › Auditoría: un registro «Decisión de faltante» con origen **«Cliente (mediante enlace)»**, la venta, el cliente, el detalle y el enlace. La venta de Los Pinos quedó «Cancelada».
6. **Cliente sin correo.** Como **Vendedor** › Contratos: botón «Faltantes para decidir (1)». Abrilo: aparece la venta de Sin Correo con su teléfono, la fecha pactada, el producto y desde cuándo. «Registrar decisión»: pantalla con «Estás registrando la decisión en nombre de…», elegí «No recibir», «Ver resumen», «Confirmar decisión». Vuelve a la ficha con el aviso «Registraste la decisión del cliente sobre el faltante de CV-…» y la venta «Cancelada». Sin ventas pendientes, la lista dice «No hay ventas de tus contratos esperando una decisión que puedas registrar.».
7. **Aceptar parte (opcional, con otra venta).** Repetí los pasos 1 a 3 con una venta de 50 plantas con 30 cubiertas por otra partida: la pantalla ofrece «Recibir las 30 plantas disponibles · $ 300,00» y «No recibir»; aceptá, confirmá: el detalle queda «Confirmado» con 30 entregadas, la venta «Abierta» y el monto de la ficha usa las 30.
8. **Correo que no sale.** Sin `CORREO_CONSOLA` (o con el correo sin configurar), generá otro faltante para Los Pinos: la ficha dice **«El correo no se pudo enviar»**, el Vendedor tiene el aviso «No se pudo enviar el enlace…» y el botón «Registrar decisión de faltante» aparece aunque el plazo siga corriendo.
9. **Paso diario 27.** `python manage.py proceso_diario --listar`: aparecen 20, 25, **27**, 35 y 40. Con un enlace vigente sin responder: `python manage.py proceso_diario --solo avisar_enlaces_vencidos --fecha <vencimiento + 1 día>`. El Vendedor recibe **un** aviso «Venció el plazo del cliente de CV-…»; corrélo de nuevo: no hay otro. La venta sigue «Pendiente de decisión» (no hay decisión tácita) y ahora la ficha ofrece el botón. *(Lo cubre el recorrido.)*
10. **Roles.** El **Gerente** ve la ficha de la venta pendiente con el bloque y **sin** botón; por la dirección `/comercial/faltantes/` o `/comercial/contratos/compra-ventas/<id>/decidir-faltante/` recibe 403. El **Agrónomo** y el **Capataz**: 403 en `/comercial/faltantes/`. Otro **Vendedor** (de otro invernadero): 403 en la decisión de una venta ajena. *(Lo cubre `test_faltantes_vistas.py`.)*
11. **Un faltante que se cubre.** Con un enlace vigente, concretá una cosecha sin contrato (o una partida nueva) de la misma variedad en ese invernadero y corré `proceso_diario --solo reasignar_camara`: el detalle vuelve a «Abierto», la venta a «Abierta» y el enlace deja de servir («Este enlace no se puede usar», «fue anulado»). *(Lo cubre `test_prod_asg_cam.py`.)*
12. **Sin JavaScript (opcional).** Desactivá JavaScript en la ventana privada y repetí el paso 3 y el 6: funciona igual (páginas y un POST).
13. **Celular (opcional).** Abrí el enlace en un celular: la tabla del resumen se apila y los botones se alcanzan con el pulgar.
14. **Después del merge, en Render.** Cargá la variable de entorno **`URL_DEL_SITIO`** (por ejemplo `https://<tu-servicio>.onrender.com`, **sin barra final**) y esperá el despliegue; en el log, que se aplicaron `comercial.0007_enlace_cliente` y `core.0039_comercial_faltantes`. Desde la «Shell»: `python manage.py proceso_diario --listar` muestra el 27. Sin la variable, los enlaces quedan «No se pudo enviar».

## Cierre

**Qué se hizo**
- `EnlaceCliente` (D-65): modelo, restricciones y migración `comercial` 0007; en `core`, las acciones `decision_faltante` y `vencimiento_enlace`, sus etiquetas y los estados del enlace (migración 0039, solo `choices`). `ROL_CLIENTE_ENLACE` y `rol_externo` ya existían (CMP-02a).
- `comercial/servicios/enlaces.py`: crear (reemplaza al vigente, correo con `on_commit`), reemplazar, anular, buscar por token, `situacion_del_enlace`, `bloquear_enlace`, `enviar_enlace` y el paso diario 27 (`avisar_enlaces_vencidos`).
- `seguir_camino_de_faltante` crea o reemplaza el enlace (con correo) o avisa «registrá vos la decisión» (sin correo); PROD-ASG-CAM anula el enlace de la venta que vuelve a «abierta»; el enlace va a la auditoría de la concreción, la cancelación de cosecha, el vencimiento y la merma en cámara.
- COM-DCD-FLT (`faltantes.py`): `datos_de_decision`, `resumen_de_decision`, `registrar_decision`, `ventas_para_decidir`, `puede_decidir_el_vendedor`, `estado_del_faltante`; bloqueos en el orden de `bloqueos.md` con el enlace al final; auditoría `decision_faltante` con origen «cliente mediante enlace» o el Vendedor; acuse y asignación de cámara con `on_commit`.
- Portal público (`/cliente/…`), «Faltantes para decidir» y «Registrar decisión de faltante» del Vendedor, la ficha de la compra-venta con lo pendiente y el enlace en la lista de Contratos.

**Pruebas (M1)**
- `python manage.py test comercial produccion maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **4444 pruebas, OK**.
- `python manage.py test comercial --keepdb --tag concurrencia`: **69 pruebas, OK** (dos envíos del mismo enlace, la decisión contra PROD-ASG-CAM, contra la merma en cámara y contra cancelar una cosecha).
- `makemigrations --check --dry-run`: sin cambios. `check`: sin problemas. `sqlmigrate comercial 0007`: crea la tabla, sus restricciones y el índice parcial único, sin tocar datos; `sqlmigrate core 0038`: no-op.
- Pruebas nuevas: `test_enlaces.py`, `test_com_dcd_flt.py` (con `ComDcdFltConcurrenciaTests`), `test_faltantes_vistas.py`, `test_recorrido_faltantes.py` y métodos nuevos en `test_modelos_cosecha_camara.py`, `test_camino_de_faltante.py`, `test_prod_asg_cam.py`, `test_prod_vnc_cam.py`, `test_prod_reg_mrm_camara.py`, `test_prod_cnc_csc.py`, `test_prod_cnl_ord_cosechas.py` y `test_cancelar_cosecha_concurrencia.py`.
- **Pruebas existentes cambiadas** (con tu autorización): `test_prod_cnl_ord_cosechas.py`, `test_post_h_las_lineas_de_camara_que_se_liberan_programan_la_asignacion_de_camara` (se quitó `len(callbacks) == 1`: ahora hay además el `on_commit` del correo del enlace) y `test_post_h_una_cosecha_sin_lineas_de_camara_no_programa_nada` (verifica que no corra `asignar_camara` en vez de que no haya callbacks).

**Verifiqué:** el recorrido `RecorridoDeFaltantesTests` (correo con el enlace, portal sin token en la URL, «No recibir», resumen, confirmar, reabrir, auditoría «Cliente (mediante enlace)», decisión del Vendedor, roles, paso 27 idempotente); las migraciones (SQL leído, sin pérdida de datos; aplicadas en la base de pruebas).
**Lo cubre una prueba:** cada postcondición (a a l) y extensión (`test_com_dcd_flt.py`); el token que no está en la base y los tres encabezados (`test_enlaces.py`, `test_faltantes_vistas.py`); permisos por rol (`test_faltantes_vistas.py`); concurrencia (`ComDcdFltConcurrenciaTests`, `test_cancelar_cosecha_concurrencia.py`).
**No pude verificar:** el CSRF real, el encabezado `Origin` y el aspecto en navegador (pasos 3 y 12 a 13 de arriba); el envío real de correo; el despliegue en Render con `URL_DEL_SITIO` (paso 14).

**Desvíos respecto de la documentación** (para `docs/temas_abiertos.md`, M3)
1. `ROL_CLIENTE_ENLACE`, `rol_externo` y su texto visible ya existían (CMP-02a): no se tocaron y no hay `core/tests/test_auditoria_rol_externo.py` (lo cubre `test_registro_auditoria.py::test_d88_*`).
2. **`URL_DEL_SITIO`** (nuevo ajuste en `config/settings.py`, de la variable de entorno; en local con DEBUG vale `http://localhost:8000`) y la ruta `/cliente/` en `config/urls.py`: ninguna estaba en «Permitido fuera de la app» (autorizado por el estudiante). Hay que cargar la variable en Render.
3. `cancelar_cosecha_incluida` recibe como actor al Vendedor en 1a (la doc dice siempre `None`); así el aviso dice «cancelada por <Vendedor>».
4. El aviso «registrá vos la decisión» no lleva URL (`notificar` no tiene ese campo): el botón está en la ficha y en la lista.
5. COM-DCD-FLT bloquea además las partidas de las líneas de **todos** los detalles pendientes (para que 6b sea confiable frente a una merma o una asignación sobre un detalle aceptado). El orden no cambia.
6. Si un caso de uso deja dos detalles de la misma venta sin cubrir, el enlace se crea dos veces en la transacción (el primero queda `reemplazado` y su correo no sale); sin correo del cliente, el Vendedor puede recibir dos avisos iguales.
7. Sin HTMX en el flujo del cliente y del Vendedor: son páginas completas y un POST (`Vary: HX-Request`); el respaldo sin JavaScript es el único camino.
8. La prueba «merma en cámara contra la decisión del cliente» está en `test_com_dcd_flt.py` (comparte su escenario) y no en `test_camara_concurrencia.py`.
9. El paso 7 / postcondición m (planificar la entrega) no se hace: es de COM-05a1, como dice la doc.
10. La contraseña de las cuentas de prueba no se escribió en ningún archivo versionado; los datos de «Datos para verificar» (cargador) no se cargaron (D-95).

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Portal del cliente · Decidir Faltante (`VIEWS.dcd`) | Un solo detalle pendiente (`c.det.find`), sin resumen y registro directo | Una elección por detalle pendiente, resumen con cantidad, subtotal, monto total nuevo y advertencia, y «Cambiar» | Extensiones 3b, 4a y 4b; paso 4 |
| `VIEWS.dcd` | No mostraba los demás detalles, la modalidad ni el monto total; no contemplaba disponible 0 | Muestra la modalidad y el destino, hasta cuándo puede decidir, «el resto de la compra no cambia» y, con disponible 0, solo «No recibir» | Paso 2; extensión 2b |
| (no existe) | Sin pantalla de enlace que no sirve ni de enlace no válido | «Este enlace no se puede usar» con motivo y contacto del Vendedor; «Este enlace no es válido» (404) | Extensiones 2a y 6a |
| (no existe) | Sin pantalla para el Vendedor | «Faltantes para decidir» (con 1a.2a) y «Registrar decisión de faltante»; el botón y el enlace en la ficha y en Contratos, solo cuando puede | Extensión 1a; D-30 (ningún botón lleva a un 403) |
| `ACT['dcd-ok']` | Registraba al elegir | Dos páginas y un POST (sin JavaScript) con un campo oculto con la cantidad disponible vista | Extensión 6b; D-29 |
| Ficha de la compra-venta (COM-02) | Sin lo pendiente ni el plazo | Bloque «Pendiente de decisión del cliente» con desde cuándo, vencimiento y estado del envío | «Lo que completa a COM-02» |
