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

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de COM-04b; un cliente con correo y otro sin correo; en
«Configuración», vigencia del enlace de faltante 2 días.

1. Repetí el punto 4 de COM-04a con el lote sin más stock libre: la venta pasa a «Pendiente de decisión del cliente» y el cliente recibe el
   correo con el enlace. La ficha de la venta dice hasta cuándo puede decidir.
2. Abrí el enlace del correo: la URL cambia y no muestra el token. Elegí «No recibir Lechuga Crespa»: el resumen dice que la compra se
   cancela; confirmá. La venta queda «Cancelada» y lo cosechado entra a la cámara con «Rechazo por cantidad reducida». Volvé a abrir el
   enlace: «Este enlace no se puede usar», con el contacto del Vendedor. En «Auditoría», el registro dice «Cliente (mediante enlace)».
3. Repetí con el cliente **sin correo**: el Vendedor recibe la notificación y, desde la ficha de la venta, «Registrar decisión de faltante».
4. `python manage.py proceso_diario --listar`: aparecen 20, 25, 27, 35 y 40. Con un enlace vencido sin respuesta, `proceso_diario --fecha
   <vencimiento + 1>`: el Vendedor recibe el aviso una sola vez.
5. Sin JavaScript: decidir (cliente y Vendedor) funciona con el resumen como página.
6. Después del merge: en Render, desde la «Shell», `python manage.py proceso_diario --listar` y revisar en el log que se aplicaron las
   migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
