# Casos de uso · iot · Orden de mantenimiento automática

Junta las partes de varios casos de uso que le tocan a **IOT-07**: la orden que se crea al agotarse los intentos de un comando, su
cancelación y lo que el Técnico recibe. No es un caso de uso propio. **El texto de cada caso de uso está en su extracto** y acá no se
repite: `resolver_comando.md` (IOT-RSV-CMD), `hardware.md` (IOT-MOD-HDW, IOT-BAJ-HDW e IOT-CNS-HDW), `sistema_iot.md` (IOT-BAJ-SIS) y
`docs/casos_de_uso/produccion/cancelar_orden.md` (PROD-CNL-ORD). Cotejado con `docs/modelo/iot.md` («MantenimientoTecnico») y
`docs/modelo/produccion.md` («OrdenTrabajo»), y con D-53, D-73 y **D-79**. Lote I4 (22/11/2026).

**El código va en la app `iot`** (D-37, nivel 7), con una migración en `produccion` (D-73, punto 3). Si este archivo y Drive no coinciden,
avisá: no elijas en silencio. Planificar y Concretar Mantenimiento técnico (CU-05 y CU-06) **no entran** en esta ronda: son de la etapa 2
(D-73).

## Índice

| Código | Partes | Actor | Archivo de pruebas |
|---|---|---|---|
| IOT-RSV-CMD | Postcondiciones k y l; extensiones 4b.4, 4b.4a y 4b.4b; reglas «Orden de mantenimiento automática» y, de «Alerta «comando fallido»», la asociación con la orden (R048) | Sistema IoT | `iot/tests/test_iot_rsv_cmd_mantenimiento.py` |
| IOT-MOD-HDW | Postcondición b (las órdenes), postcondición e (las órdenes canceladas) y regla 8 | Agrónomo o Gerente (alcance) | `iot/tests/test_iot_mod_hdw_ordenes.py` |
| IOT-CNS-HDW | Regla 6: las órdenes de mantenimiento de la ficha | Agrónomo o Gerente | `iot/tests/test_mantenimiento_vistas.py` |
| IOT-BAJ-HDW, IOT-BAJ-SIS | Precondición d (órdenes a realizar) y su texto (regla 2 de BAJ-HDW, regla 4 de BAJ-SIS) | Agrónomo o Gerente | `iot/tests/test_iot_baj_hdw.py`, `test_iot_baj_sis.py` (casos nuevos) |
| PROD-CNL-ORD | Para un mantenimiento: 4d, 8a, 8e, 9a y las postcondiciones j, k y m, ejecutado desde la ficha del equipo (D-79, puntos 1 y 2) | Agrónomo o Gerente (alcance del IoT) | `iot/tests/test_cancelar_mantenimiento.py` |
| PROD-MOD-INV | Regla 3 y postcondición b para el rol Técnico (traspaso) | Gerente (lo ejecuta `maestros`) | `iot/tests/test_traspaso_tecnico.py` |
| USR-BAJ-USR | Regla 4 para un Técnico (lo que tiene asignado; D-79, punto 9) | Gerente o Administrador (lo ejecuta `core`) | `iot/tests/test_traspaso_tecnico.py` |
| — | Sección «Mantenimientos a realizar» del Inicio del Técnico (D-79, punto 4) | Técnico | `iot/tests/test_inicio_tecnico.py` |

Concurrencia: `iot/tests/test_mantenimiento_concurrencia.py` (`@tag("concurrencia")`). Para nombrar las pruebas, lo de siempre:
`test_post_<letra>_<que_espera>`, `test_ext_<extension>_<que_espera>` y `test_regla_<nombre>_<que_espera>`.

## Cómo se aplica en la ronda «IoT 1» (D-53, D-73, D-79)

### Modelo y migraciones

- **`produccion`** (lo único que se toca, D-73, punto 3):
  - `OrdenTrabajo.Tipo` ya tiene `mantenimiento` → «Mantenimiento técnico» (lo crea PRD-01, D-67 punto 1; IOT-07 no toca los `choices`);
  - `CheckConstraint` `ordentrabajo_prioridad_en_mantenimiento`: `~Q(tipo="mantenimiento") | Q(prioridad_orden__isnull=False)`
    (prioridad obligatoria en mantenimiento, D-53, punto 6). Va aparte del de la cosecha (COM-02): no se reescribe ese;
  - una migración, `00NN_ordentrabajo_prioridad_en_mantenimiento` (solo la restricción).
- **`iot`**: `MantenimientoTecnico(OrdenTrabajo)` (herencia multitabla, **sin** `ConCapataz`; `docs/modelo/iot.md`, «MantenimientoTecnico»):
  - `tipo_mantenimiento`, `TextChoices` `TipoMantenimiento` (`revision` → «Revisión», `reparacion` → «Reparación», `calibracion` →
    «Calibración», `reemplazo` → «Reemplazo», `mantenimiento_general` → «Mantenimiento general»; MD-111);
  - `tecnico`: FK a `core.Tecnico`, `PROTECT`, obligatoria, `related_name="mantenimientos_asignados"` (R047), con índice;
  - `hardware`: `ManyToManyField` a `Hardware`, `related_name="mantenimientos"` (R057, 1..\*: la base no lo garantiza, lo garantiza el
    servicio y lo prueba una prueba de invariante);
  - `alerta`: `OneToOneField` nulo a `maestros.Alerta`, `PROTECT`, `related_name="mantenimiento_tecnico"` (R048);
  - `save()` fija `tipo_orden = mantenimiento`; nunca cambia;
  - una migración, `00NN_mantenimiento_tecnico`, que depende de la de `produccion`;
  - la fábrica `MantenimientoTecnicoFactory` en `iot/tests/fabricas.py`.
- **`core`:** ninguna. Las acciones de auditoría ya existen: `resolucion_comando_iot` (IOT-05), `reactivacion_hardware` (IOT-02) y
  `cancelacion_orden` (PRD-01).

### Lecturas (sin escribir, sin bloquear, sin consultas por fila)

Las dos primeras **ya existen** y devuelven una lista vacía: se quedan donde las dejaron, con su nombre y su firma, y pasan a consultar
`MantenimientoTecnico`. Las otras dos son nuevas, en `iot/servicios/mantenimiento.py`.

| Función | Qué devuelve | Lo usa |
|---|---|---|
| `mantenimientos_a_realizar(equipo)` (`iot/servicios/hardware.py`, IOT-02) | Las órdenes de mantenimiento «a realizar» que incluyen el equipo, por `id` | Volver a activar (regla 8), la baja del equipo (precondición d), la orden al escalar (4b.4b) |
| `ordenes_a_realizar_del_sistema(sistema)` (`iot/servicios/sistemas.py`, IOT-06) | Las «a realizar» que incluyen algún equipo del sistema, sin repetir, por `id` | La baja del sistema (precondición d) |
| `mantenimientos_del_equipo(equipo)` | Todas las órdenes del equipo: primero las «a realizar» (fecha programada, prioridad, `id`), después las demás por fecha de resolución, de la más nueva a la más vieja | La ficha (regla 6 de CNS) |
| `mantenimientos_a_realizar_del_tecnico(tecnico)` | Las «a realizar» asignadas a ese Técnico, en el orden de las órdenes (`docs/modelo/produccion.md`, «Listas fijas»), con el invernadero y los equipos | El Inicio del Técnico, las asignaciones de la cuenta |

Textos de las bajas (regla 2 de IOT-BAJ-HDW y regla 4 de IOT-BAJ-SIS; corrige el «concretala o cancelala» del prototipo, porque en esta
ronda no se concreta, D-61):
- equipo: «Está en la orden de mantenimiento OT-0231, a realizar: cancelala desde «Órdenes de mantenimiento», en la ficha del equipo.»;
- sistema: «Hay {n} orden(es) de mantenimiento a realizar ({códigos}): cancelalas desde la ficha de cada equipo.».

### La orden al escalar (postcondiciones k y l; 4b.4, 4b.4a y 4b.4b) — `crear_orden_automatica(comando, ahora) -> OrdenAutomatica`

La llama **el escalamiento de IOT-05**, en los dos lugares donde un comando agota sus intentos: el resultado `fallo` en el último intento
(4b) y el último intento vencido «sin respuesta» en el retiro (2a, que escala igual que 4b). Si IOT-05 dejó un solo `_escalar`, se llama
desde ahí. Corre en la transacción del mensaje, con invernadero → sistema → nodo → actuador → comando ya bloqueados (D-78, punto 11), y va
**después** de pasar el actuador a «fuera de servicio» y **antes** de asegurar la alerta, porque el texto de la alerta necesita el código
de la orden.

1. **Sin Técnico asignado** (`invernadero.tecnico` nulo; 4b.4a): no se crea. Si está asignado pero inactivo, **sí** se crea (regla «Orden
   de mantenimiento automática»).
2. **Orden existente** (4b.4b): la primera «a realizar» del actuador (`mantenimientos_a_realizar(actuador)`), bloqueada (`FOR NO KEY UPDATE`)
   después del comando. No se crea otra (D-73, punto 5). La alerta nueva **no** se asocia a ella: la orden ya tiene la suya (R048 es 0..1)
   y la conserva.
3. **Si no**, se crea:
   - `numero` con `produccion.servicios.ordenes.siguiente_numero()` (PRD-01; nunca a mano);
   - `invernadero` el del sistema, `agronomo` nulo (R046), `tecnico` el del invernadero;
   - `fecha_creacion_orden` y `fecha_programada_orden` = `timezone.localdate()`, `prioridad_orden = alta`;
   - `tipo_mantenimiento = revision`, `hardware = [actuador]`;
   - `descripcion_orden` (D-79, punto 7): «CMD-{id} · {acción}[ {valor} {unidad}] no se ejecutó en {n} intentos. Último resultado:
     {Falló: {detalle} | Sin respuesta}.», hasta 500, recortada con «…».
   El invernadero ya está bloqueado por el mensaje: se cumple el contrato de bloquearlo antes de crear algo que impide su baja
   (`maestros/extensiones.py`, «CONTRATO»).
4. **La alerta** (D-79, puntos 3 y 5): la función de IOT-05 que asegura `iot_comando_fallido` recibe el **sufijo** y lo agrega al texto de
   D-78 (punto 10):
   - creada: « · Orden de mantenimiento OT-0231 asignada a {nombre y apellido}.» (el nombre, hasta 40 con «…»);
   - sin Técnico: « · El invernadero no tiene Técnico: la orden de mantenimiento deberá planificarse cuando se asigne uno.»;
   - existente: « · Ya está en la orden de mantenimiento OT-0231, a realizar.»;
   - si pasa de 200: se recorta con «…» primero el detalle del último resultado y después el texto base; el sufijo va siempre completo.
   Si se creó la orden: `orden.alerta = alerta` (`save(update_fields=["alerta"])`).
5. **El aviso al Técnico** (postcondición l; D-79, puntos 6 y 7), solo si su cuenta está activa, con `core.notificaciones.notificar`:
   título «Orden OT-0231 de mantenimiento asignada»; detalle «Revisión de {identificador} en {invernadero}, prioridad alta, para hoy.
   {descripción de la orden}», recortado a 500 con «…». La cuenta del Técnico **no** se bloquea: la orden se le asigna aunque esté inactivo,
   y una carrera con la baja de su cuenta solo cambia si recibe el aviso.
6. **Auditoría** (postcondición q): la orden es un afectado más del registro `resolucion_comando_iot` del mensaje. En `datos`:
   `orden_mantenimiento` (el código) o `sin_orden` (`sin_tecnico` u `orden_existente`, con el código de la existente).

`OrdenAutomatica(orden, caso, sufijo)`, con `caso` = `creada`, `sin_tecnico` u `orden_existente`, y `orden` nula en `sin_tecnico`.

### Cancelar la orden desde la ficha (PROD-CNL-ORD para un mantenimiento; D-73, puntos 2 a 4; D-79, puntos 1, 2 y 7)

`resumen_de_cancelacion_de_mantenimiento(actor, orden_id)` (no escribe) y `cancelar_mantenimiento(actor, orden_id, motivo) ->
MantenimientoTecnico`, en `iot/servicios/mantenimiento.py`.

- **Quién:** el alcance del IoT (`iot/alcance.py`, regla 1 de IOT-DSC-SIS): el Agrónomo a cargo del invernadero o, sin Agrónomo activo, el
  Gerente. El Gerente con un Agrónomo activo ve la orden sin el botón. Excepción a «el Gerente no cancela» de PROD-CNL-ORD (D-79, punto 2).
- **El resumen** (4d): los equipos, el tipo («Revisión»), el Técnico, los repuestos reservados («Sin repuestos reservados»: en esta ronda
  no hay reservas) y el aviso «La alerta «comando fallido» sigue activa: se resuelve cuando el equipo vuelva a estar activo.» (D-73, punto
  4).
- **Motivo** (6a): obligatorio, de 1 a 300 caracteres, sin espacios al borde. Se valida **antes** de llamar a `cancelar_orden_incluida`
  (que recorta sin avisar). Mensajes: «Indicá el motivo de la cancelación.» y «El motivo no puede pasar de 300 caracteres.».
- **Bloqueos** (`docs/patrones/bloqueos.md`, orden de `produccion`, con los niveles del IoT en el medio): las cuentas del actor y del
  Técnico de la orden (leída sin bloquear) en **una** consulta → invernadero → sistema → los equipos de la orden, en orden de `id` → la
  orden y sus reservas (las bloquea `cancelar_orden_incluida`). Se relee la orden:
  - ya no está «a realizar» (8a): «La orden ya no está a realizar: otra operación la canceló.»;
  - cambió su Técnico (un traspaso a la vez): `cambio_simultaneo`.
- **Efecto:** `produccion.servicios.ordenes.cancelar_orden_incluida(actor, orden, motivo, avisar=False)` (D-73, punto 3; regla 4 de
  `docs/api/produccion.md`, sección 5). El hardware conserva su estado (j). La alerta **no** se resuelve.
- **Aviso al Técnico** (k, 9a), solo si su cuenta está activa, con `notificar_a_varios([tecnico], …, excluir=actor)`: título «Orden
  OT-0231 cancelada»; detalle «Motivo: {motivo}. Mantenimiento técnico del {dd/mm/aaaa} en {invernadero}, cancelada por {nombre y
  apellido}.». La regla del largo es la de PROD-CNL-ORD: el motivo va completo y se acortan primero el nombre y después el invernadero. Si
  ya existe `produccion.servicios.ordenes.texto_de_cancelacion(orden, motivo, actor)` (la deja COM-04a, `cancelar_orden.md`, «Cómo se aplica
  en la ronda «Comercial 1»»), se usa esa función, que ya toma «Mantenimiento técnico» de la etiqueta del tipo; si no, se arma igual.
- **Auditoría** (m): un registro `cancelacion_orden`, con la orden y lo que devuelve `CancelacionIncluida` como afectados; en `datos`,
  `desde: "iot"` y los equipos.

### Volver a activar un equipo con órdenes (regla 8 y postcondiciones b y e de IOT-MOD-HDW; D-79, punto 8)

Completa `volver_a_activar(actor, equipo_id)` de IOT-02, que pasa a `volver_a_activar(actor, equipo_id, decisiones=None)`.

- `ordenes_al_volver_a_activar(equipo) -> list[OrdenAlVolver]`: cada orden de `mantenimientos_a_realizar(equipo)` con `cancelable` y
  `otros_fuera_de_servicio` (los demás equipos de la orden que siguen «fuera de servicio»; si hay alguno, no es cancelable).
- `decisiones`: `{orden_id: "cancelar" | "mantener"}`. Con órdenes y sin `decisiones` (o sin una de ellas): «Elegí qué hacer con cada orden
  de mantenimiento.». Pedir cancelar una no cancelable: «La orden OT-0231 incluye otros equipos fuera de servicio: no se puede cancelar.».
- **Bloqueos:** las cuentas del actor y de los Técnicos de las órdenes a cancelar en una consulta → invernadero → sistema → el equipo y los
  demás equipos de esas órdenes, en orden de `id` → las órdenes (por `cancelar_orden_incluida`). Si después de bloquear las órdenes del
  equipo no son las mismas que se mostraron: «Las órdenes del equipo cambiaron mientras confirmabas: revisalas de nuevo.».
- Cada orden a cancelar: `cancelar_orden_incluida(actor, orden, "Se volvió a activar el equipo {identificador}.", avisar=False)` y el aviso
  al Técnico con el texto de la cancelación.
- **Auditoría:** las órdenes canceladas son afectados del registro `reactivacion_hardware`; en `datos`, `ordenes_canceladas` y
  `ordenes_mantenidas` (códigos). Una orden mantenida no cambia.

### Traspaso del Técnico (D-53, punto 5; D-79, punto 9) — `IotConfig.ready()`

`maestros.extensiones.registrar_traspaso(contar_mantenimientos, traspasar_mantenimientos)`:

- `contar(invernadero, rol, saliente, entrante)`: si `rol != "tecnico"` o no hay entrante, `[]`. Si no, las órdenes de mantenimiento «a
  realizar» del invernadero con otro Técnico: `[("mantenimientos técnicos a realizar", n)]` si `n > 0`. Lo usan el aviso de la regla 2 y la
  notificación de la postcondición c de PROD-MOD-INV («Recibe: mantenimientos técnicos a realizar: 2.»).
- `traspasar(actor, invernadero, rol, saliente, entrante)`: las mismas órdenes, bloqueadas en orden de `id` después del invernadero, pasan
  a `tecnico = entrante` con **una** consulta. Sin entrante, nada (el campo es obligatorio).
- No audita por su cuenta: el contrato de `maestros/extensiones.py` no devuelve afectados, y el cambio de personal ya queda en
  `modificacion_invernadero`. Si PRD-01, al programarse, cambió el contrato para devolver afectados, seguí lo mismo que su registrante del
  Capataz.

### Asignaciones de la cuenta (regla 4 de USR-BAJ-USR; D-79, punto 9)

`core.extensiones.registrar_asignaciones_de_cuenta(asignaciones_del_tecnico)`: para la cuenta de un Técnico con órdenes a realizar,
`Asignacion("Mantenimientos técnicos a realizar", n, "Pasan a quien el Gerente asigne al modificar el invernadero.")`; para cualquier otra
cuenta, `[]`. Solo lectura.

### El Inicio del Técnico (D-79, punto 4)

`core.extensiones.registrar_seccion_de_inicio(seccion_de_mantenimientos)`: `None` si el usuario no es un Técnico; si lo es, la sección
«Mantenimientos a realizar» (`iot/_inicio_mantenimientos.html`) con `mantenimientos_a_realizar_del_tecnico`:
- por orden: código, invernadero, equipos (identificador y descripción), «Revisión», prioridad, fecha programada (con «Vencida» si es
  anterior a hoy) y la descripción;
- sin órdenes: «No tenés mantenimientos a realizar.»;
- debajo, una línea: «Las órdenes las cierra el Agrónomo: cancelándolas o volviendo a activar el equipo.»;
- **sin botones ni enlaces** a pantallas del IoT: el Técnico no las tiene (IOT-CNS-HDW).

### Lo que no tiene que cambiar en `produccion`

La bandeja del Capataz, la lista de órdenes y la de cancelables (`docs/api/produccion.md`, sección 2) **no** muestran mantenimientos (D-79,
punto 1). Una prueba de `iot` lo verifica. Si alguna los muestra, frená y avisá: corregirlo toca `produccion` más allá de D-73 (punto 3).

## Pantallas

El prototipo (`docs/prototipos/iot/`) no tiene estas pantallas o las tiene a medias: son una referencia (D-61).

| Pantalla | En el prototipo | Qué se hace |
|---|---|---|
| Ficha del equipo, sección «Órdenes de mantenimiento» | No está (la ficha no muestra órdenes) | Tabla con código, tipo, estado, prioridad, fecha programada, Técnico y descripción; «Cancelar orden» en las «a realizar», si el actor puede operar |
| Ventana «Cancelar orden» | No está | El resumen de 4d, el motivo y «Cancelar orden» (botón de peligro); sin JavaScript funciona igual |
| Ventana «Volver a activar» (`modalHtml`, `react:<id>`) | Avisa «se cancelará» sin preguntar | Una fila por orden con «Cancelarla» (marcada) y «Mantenerla», o solo «Mantenerla» con su explicación |
| Ventanas de baja (`baj:<id>`, `baj` del sistema) | «Concretala o cancelala» | Los textos de «Lecturas», arriba |
| Inicio del Técnico | No está | La sección «Mantenimientos a realizar» |
| Comando fallido (`failCmd`) | Crea la orden y escribe la nota | Lo hace el servidor (arriba); el prototipo es solo una referencia del texto |

## Para más adelante

- Planificar y Concretar Mantenimiento técnico (CU-05 y CU-06, etapa 2): la orden automática seguirá sus reglas (regla «Orden de
  mantenimiento automática»), con la bitácora y el consumo (R056, R135) y la vuelta del equipo a «activo» al concretar (regla 7 de
  IOT-MOD-HDW).
- Repuestos reservados: en esta ronda ninguna orden los tiene; la ventana de cancelación ya muestra la línea.

## Solo prototipo

La cancelación automática al volver a activar (manda la regla 8, D-73) y los códigos `OT-NNNN` fijos de `DB.ordenes`.
