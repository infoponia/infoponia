# Patrón · Bloqueos de filas y pruebas de concurrencia

Resumen vigente de D-30 y D-32 para cualquier servicio que cuide un invariante entre filas o una cantidad (agujeros
libres de un sector, stock de un insumo, reservas). Si algo de acá contradice una de esas decisiones, manda la decisión:
avisá. `CLAUDE.md` («Convenciones») ya pide `select_for_update()` en reservas de stock y en toda operación concurrente
sobre cantidades.

## Cómo se bloquea

- Siempre `select_for_update(no_key=True)` (`FOR NO KEY UPDATE`), nunca `FOR UPDATE`. Al insertar la auditoría, la FK
  hacia quien actúa toma `FOR KEY SHARE` sobre su fila, y `FOR UPDATE` choca con ese bloqueo: así aparecen los deadlocks
  (D-32).
- Orden fijo, el mismo en todos los servicios (D-30, ampliado por D-32):
  1. el **grupo** de filas que cuida un invariante, en orden de `id`;
  2. los **invariantes**, si corresponde;
  3. verificar que **quien actúa** siga activo (pudo quedar inactivo mientras esperaba);
  4. por último, las **filas** que se modifican, en orden de `id`, y **volver a leerlas**.
- Lo que no cambia (por ejemplo, el rol, D-11) se puede leer antes sin bloquear, para saber qué grupo bloquear.
- Lo lento (calcular un resumen de contraseña, mandar un correo) se hace **antes** de bloquear o **fuera** de la
  transacción. Si una verificación hecha antes puede quedar vieja, se guarda lo leído y se **revalida después de
  bloquear**.
- Si lo bloqueado cambió mientras se esperaba, se **rechaza** con un código («cambio_simultaneo») y un mensaje; no se
  reintenta, porque reintentar toma bloqueos fuera de orden.
- Cuando se pueda, una restricción de la base respalda al bloqueo (por ejemplo, para la primera fila, que no tiene nada
  que bloquear). Su `IntegrityError` se traduce a un código conocido con `raise ... from error`: nunca llega un 500.
- Si se bloquea un conjunto filtrado («los activos»), cuidá el caso en que el filtro no devuelve nada: no se bloquea nada
  y dos operaciones pasan juntas. D-30 bloquea todas las filas del grupo, sin filtrar por estado.

## Cómo se prueba

- Las pruebas de concurrencia van en clases `<CodigoCu>ConcurrenciaTests` (`TransactionTestCase`), con
  `@tag("concurrencia")`, y usan `correr_a_la_vez` de `core/tests/concurrencia.py`.
- `correr_a_la_vez(operacion_a, operacion_b, primera, detener_antes_de=None)`:
  - `primera` («a» o «b») es obligatorio: esa operación se detiene en un punto fijo y la otra arranca recién entonces.
    Así la prueba no depende de la velocidad de la máquina.
  - El punto de parada por defecto es `RegistroAuditoria.objects.registrar` (ya tomó sus bloqueos y escribió, sin
    confirmar).
  - `detener_antes_de=(objeto, "nombre")` la detiene justo antes de llamar a esa función. Hace falta para probar el
    **orden** de los bloqueos.
  - Devuelve `{"a": resultado_o_excepcion, "b": ...}`. `separar` y `codigos` ayudan a leer el resultado.
- En local se corren solo si la tarea toca bloqueos o concurrencia (`CLAUDE.md`, «Tests»).
- Si una tarea toca bloqueos, una prueba de concurrencia debe fallar cuando se quita la protección que cuida (D-32 lo
  verificó así). Esos experimentos solo se hacen si la tarea toca bloqueos o el estudiante lo pide.

## Límite conocido

- Un `UPDATE` que cambia una columna con índice único toma `FOR UPDATE` en esa sentencia, se haya bloqueado antes como
  se haya bloqueado (D-32, «Residual»).

## Invernadero (MAE-01b, D-40)

Orden global de bloqueos de `maestros` (siempre `select_for_update(no_key=True)`), el mismo en `modificar_invernadero`,
`reactivar_invernadero`, `baja_invernadero` y en todo caso de uso que se registre en `maestros/extensiones.py`:

1. las filas de **`Usuario`** de quien actúa y de las cuentas de personal enviadas, **en una sola consulta** y en orden de
   id (en `modificar_invernadero`; la baja y la reactivación solo verifican que quien actúa siga activo);
2. el **invernadero**, y volver a leerlo (`_bloquear_invernadero`);
3. **recién después**, lo que bloqueen los registrantes de los puntos de extensión (filas de las apps altas), en orden de id.

La baja de una cuenta con invernaderos a cargo (disparador 4 de «Cuando exista Invernadero») tiene que seguir este orden:
primero la cuenta (como ya hace `baja_usuario`) y después los invernaderos. Si bloquea al revés, hay deadlock con
`modificar_invernadero`.

### Contrato de los puntos de extensión

Todo caso de uso futuro que cree algo que impida la baja de un invernadero (un lote activo, una orden a realizar, una
partida disponible, un movimiento de stock o una orden de compra aprobada, un transportista activo, un sistema IoT activo),
o lo vuelva a poner en ese estado, tiene que, **dentro de su transacción y antes de crearlo**:

```python
from maestros.servicios.invernaderos import bloquear_invernadero_activo
invernadero = bloquear_invernadero_activo(invernadero_id)   # FOR NO KEY UPDATE; rechaza uno inactivo
```

**La clave foránea sola no alcanza.** El `INSERT` toma `FOR KEY SHARE` sobre la fila del invernadero, y ese bloqueo no choca con
el `FOR NO KEY UPDATE` de la baja: la baja no esperaría, no vería lo que todavía no se confirmó y daría de baja un
invernadero con un impedimento. Con el bloqueo, o la baja espera al creador (y después ve el impedimento) o el creador espera a la
baja (y la encuentra inactiva). Está en el docstring de `bloquear_invernadero_activo` y de `maestros/extensiones.py`, y lo
prueban `ProdBajInvConcurrenciaTests` (con un creador falso que tiene una FK real).

Los registrantes de los tres puntos corren dentro de la transacción del servicio, **después** de que este tomó los bloqueos
de arriba; el que bloquee filas propias lo hace después del invernadero y en orden de id.

**Excepción de D-82 (IoT).** En los flujos de IoT que crean un actuador, le cambian el tipo o lo reactivan, el **tipo de actuador se bloquea antes que el
invernadero**: IOT-MOD-TAC bloquea el tipo y después los invernaderos de sus actuadores, y con el orden contrario las dos operaciones se cruzan (deadlock). En el
resto del IoT y en las demás apps sigue valiendo el orden de arriba.

### El `UPDATE` del invernadero va antes de los traspasos

Cambiar de urbana a rural cambia `Invernadero.direccion_id`, una columna con índice único común (es un `OneToOneField`): ese
`UPDATE` toma `FOR UPDATE` y espera a cualquier transacción que tenga `FOR KEY SHARE` sobre el invernadero (una que insertó una
fila con FK hacia él). Por eso `modificar_invernadero` hace el `UPDATE` **antes** de llamar a los registrantes de traspaso:
mientras espera ahí, solo tiene bloqueadas cuentas y el invernadero, no filas de las apps altas. Si ya las tuviera, la otra
transacción podría estar esperando justo esas filas y se cerraría un ciclo (deadlock). Quien sigue el contrato bloquea el
invernadero antes de insertar, así que no puede tener `FOR KEY SHARE` sobre él mientras espera las cuentas o el invernadero.

### Unicidad del nombre

El nombre es único con `UniqueConstraint(Lower("nombre_invernadero"))`, un índice de expresión: según la documentación de
PostgreSQL 17 (Explicit Locking, `FOR UPDATE`), un `UPDATE` solo toma `FOR UPDATE` por columnas con un índice único «que se
pueda usar en una clave foránea» (no cuentan los índices parciales ni los de expresión). Renombrar **no** sube a `FOR UPDATE`, y
el «Límite conocido» de arriba no aplica al nombre. Sí aplica a `direccion_id` (ver el apartado anterior). Dos renombres al
mismo nombre a la vez: el segundo espera en el índice y recibe un `IntegrityError`, que el servicio traduce a
`nombre_repetido`.

### Quien actúa

`_exigir_actor_sigue_activo` de `core` no bloquea la fila de quien actúa (es un `EXISTS` posterior a los bloqueos). En
`modificar_invernadero` la fila del Gerente entra en la misma consulta que las cuentas de personal, así que **todas las
modificaciones del mismo Gerente se serializan** (hoy hay un solo Gerente activo, D-09). La baja y la reactivación no la
bloquean: se serializan por el invernadero.

## `produccion` (lote 4, D-50)

Orden global de los servicios de `produccion` (siempre `select_for_update(no_key=True)`; el detalle de `inventario` está en `docs/patrones/stock.md`, sección 5):

1. las cuentas (`Usuario`) de quien actúa y de las que se notifican, en una sola consulta y en orden de id;
2. el **invernadero** (`bloquear_invernadero_activo`) y volver a leerlo;
2b. la **variedad** (`inventario.servicios.variedades.bloquear_variedad`), también al concretar: la variedad no puede darse de baja ni cambiar de perfil a mitad de camino;
2c. los **sectores** (`maestros.servicios.sectores.bloquear_sectores`) que toca la operación, en orden de id y **sin repetir** (en una transición: los destino y los de origen del lote juntos);
3. los insumos que toca (`TipoInsumo` → `Insumo` → `InsumoInvernadero` → `LoteInsumo`, orden de `stock.md`, sección 5);
4. el **lote** (`Lote`) y, por último, las filas de la operación (orden, ocupaciones, reservas), en orden de id, y **volver a leerlas**.

- Las filas que dicen qué bloquear (los sectores de una orden, sus reservas, las ocupaciones de un lote) se leen **sin bloquear**, se bloquean y se releen. Si cambió algo, `cambio_simultaneo`, sin reintentar.
- Un lote con **una sola** transición «a realizar» (regla 4 de 8.21) y una orden que se concreta **una sola vez** no tienen restricción de base: los garantiza el bloqueo del lote y de la orden antes de verificar, y lo prueban las pruebas de concurrencia.
- Toda operación que cree algo que impida la baja de un sector, de una variedad o de un invernadero (un lote, una ocupación, una orden «a realizar») bloquea antes el invernadero, la variedad y los sectores, **antes de crearlo** (contrato de D-40).
- `cancelar_orden_incluida` corre dentro de la transacción de su llamador: el llamador ya tiene los niveles 1 a 2c; la función toma los que siguen, en este mismo orden.
- Las notificaciones y las alertas se crean **dentro** de la transacción (D-42), después de todos los bloqueos de arriba.
- Pruebas de concurrencia mínimas (`@tag("concurrencia")`, `correr_a_la_vez`): dos planificaciones sobre el último agujero y sobre la última unidad de stock; concretar dos veces; concretar contra cancelar; planificar contra la baja del sector o de la variedad; concretar una transición contra una merma que cambia la cantidad del lote.

### Lote 5 (D-51): lo que suman PRD-03 y PRD-04 al orden de `produccion`

- **Merma de un lote** (PRD-03): cuentas → invernadero → variedad del lote → sectores con pérdidas (id) → lote → ocupaciones.
- **Aplicación de insumos** (PRD-03): cuentas → invernadero → **sectores del alcance** (id; fijan qué lotes tienen plantas ahí) → insumos (`TipoInsumo` → `Insumo` → `InsumoInvernadero` → `LoteInsumo`, id) → **lotes de plantas del alcance** (id; cambia su `costo_acumulado`). No toca ocupaciones, etapas ni plantas.
- **Poner un sector fuera de servicio** (PRD-04): cuentas → invernadero → **variedades** de los lotes y órdenes afectados (id) → sectores (el de origen, los destino y los de las órdenes a cancelar, id, sin repetir) → insumos de las reservas de esas órdenes → lotes (id) → órdenes, ocupaciones y reservas. El sector de origen se bloquea **antes** de pasarlo a «fuera de servicio».
- **Registrar evento** (PRD-03): cuentas → invernadero → fila del lote si se eligió.
- **Efectos de maestros** (vuelta a servicio, baja de sector, baja de invernadero): corren con el invernadero y los sectores ya tomados; sus filas de `FueraDeServicio` se bloquean después, en orden de id.
- Pruebas de concurrencia que suma el lote 5: dos mermas sobre el mismo lote; merma contra concretar una transición; merma contra poner el sector fuera de servicio; dos aplicaciones sobre el mismo lote de insumo; aplicación contra un ajuste de stock; poner fuera de servicio dos veces el mismo sector.

## `comercial` (COM-02, D-59)

Orden de las operaciones que reservan stock (compra-venta, suministro, cosecha, cámara). El detalle, con el porqué, está en
`docs/patrones/stock_maduro.md`, sección 3:

1. las cuentas (quien actúa, el Vendedor responsable y las que se notifican), en una consulta y en orden de id;
2. los **invernaderos considerados** (`bloquear_invernadero_activo`), en orden de id, y releer su Vendedor y su Capataz;
2b. el **cliente** (si la operación tiene uno), y releer su estado y, en un envío, su dirección;
3. las **variedades** (`bloquear_variedad`), en orden de id;
4. los **lotes candidatos** y después las **partidas candidatas**, cada grupo en orden de id;
5. las filas de la operación (contrato, detalles, reservas, líneas, cosechas), nuevas o releídas.

- Es compatible con el de `produccion`: una merma (invernadero → variedad → sectores → lote) y una venta (invernadero → variedad → lote) toman
  lo común en el mismo sentido.
- El traspaso de contratos al Vendedor nuevo (D-60) corre dentro de `modificar_invernadero`: bloquea los contratos **después** del invernadero
  (contrato de `maestros/extensiones.py`). Una venta nueva de ese invernadero espera al invernadero, así que no queda una venta del Vendedor
  anterior creada en medio del traspaso.
- ABM de clientes y vehículos (COM-01): cuentas → la fila del cliente o del vehículo. No toman invernaderos.

- Suministros (COM-03): la pre-reserva de un período y una modificación con detalles nuevos siguen el orden de arriba y bloquean el
  `Suministro` en el paso 5, antes que sus detalles. Una modificación sin detalles nuevos (sin asignación) bloquea solo las cuentas y el
  `Suministro`: no toma invernaderos ni lotes, así que no puede cruzarse con una pre-reserva.

- Cosecha y cámara (COM-04, D-64): el mismo orden, con los **sectores** entre las variedades y los lotes (como la merma de `produccion`):
  cuentas → invernaderos → cliente → variedades → **sectores** (los de las ocupaciones de los lotes, en orden de id) → lotes → partidas →
  contrato → detalles → **cosecha** (`OrdenTrabajo`) → reservas → líneas → **enlace del cliente** (`EnlaceCliente`, D-65), siempre al final. Así se ordenan PROD-PNF-CSC,
  PROD-MOD-CSC, PROD-CNC-CSC (con su merma y su encadenamiento), la cancelación de una cosecha, la merma en cámara, PROD-VNC-CAM, PROD-ASG-CAM y
  COM-DCD-FLT. Cada uno lee sin bloquear qué filas va a tocar, las bloquea en este orden, las **relee** y verifica que no cambiaron (las
  extensiones 13b y 13c de PROD-CNC-CSC, 10a y 10b de PROD-MOD-CSC, 8a y 8b de PROD-CNL-ORD, 6a y 6b de COM-DCD-FLT).
- Una cosecha que se concreta y otra operación sobre su reserva (cancelarla, modificarla, rechazar el detalle) se ponen en fila en la
  **fila de la cosecha** (`OrdenTrabajo`), que todas bloquean antes que su reserva.

- Entregas y envasado (COM-05a1 y COM-05a2, D-66 punto 11; COM-05b, D-67). **El semáforo es el invernadero de origen**: toda operación que crea, cambia o cancela una
  entrega o su envasado lo toma antes (`bloquear_invernadero_activo`), y como un transportista es de un solo invernadero (MD-138), quedan
  en fila las planificaciones, las asignaciones y el inicio de ruta del mismo transportista.
  - **Planificar una entrega** (COM-PNF-ENT, un invernadero de origen por transacción): cuentas (el Vendedor del contrato, el Agrónomo del
    invernadero y **todos los transportistas del invernadero**, en una consulta y en orden de id; se releen su estado y su invernadero) →
    el invernadero → el cliente → el **contrato** → sus detalles → sus **reservas** (releer que sigan «lista para entrega» y sin línea en una
    entrega no cancelada: 8b) → las **entregas** del contrato con las que podría agruparse (en orden de id) y sus reservas de insumo (para
    ver si tienen envasado). Con todo releído, se eligen el transportista y el agrupamiento (8a ya no puede pasar: nadie más cambia ese día
    del transportista sin el invernadero).
  - **Planificar el envasado** (PROD-PNF-ENV): la cuenta del Agrónomo → el invernadero → los `InsumoInvernadero` de los envases (en orden
    de id) y sus lotes (`docs/patrones/stock.md`, sección 5) → la **entrega** (`OrdenTrabajo`) → sus reservas de insumo, releídas (10a, 10c).
  - **Cancelar una entrega** (dentro de PROD-VNC-CAM, la merma en cámara, COM-CNL-CVT o COM-RSV-SUM): el caso de uso base ya tomó el
    invernadero y sus filas; después de las reservas de stock toma la **entrega**, y `cancelar_orden_incluida` sus insumos y sus reservas de
    insumo. Ese orden interno (reservas de stock → entrega → insumos) es distinto del del envasado (insumos → entrega), pero no se cruzan:
    los dos tomaron antes el mismo invernadero.
  - **Baja de la cuenta de un Transportista** (`registrar_efecto_de_baja_de_cuenta`): la cuenta ya está bloqueada por `baja_usuario`; el
    efecto toma los invernaderos de sus entregas «a realizar» (en orden de id) y después las entregas.
  - **Asignar un transportista** (COM-ASG-TRP, COM-05b): cuentas (el actor, el Vendedor del contrato, el transportista nuevo y el actual, en
    una consulta y en orden de id; se releen su estado y el invernadero del nuevo) → el **invernadero de origen** → la **entrega**
    (`OrdenTrabajo`). Con el invernadero tomado se vuelven a calcular los candidatos (8b): nadie más puede cambiar ese día del transportista.
    No toma reservas ni insumos (el contenido de la entrega no cambia).
  - **Cancelar una compra-venta** (COM-CNL-CVT, COM-05b): el orden de «Cosecha y cámara» con las entregas después de las reservas: cuentas (el
    actor, el Vendedor, los Capataces y Agrónomos de las cosechas, los transportistas de las entregas) → los **invernaderos** de las reservas y
    de las entregas (`bloquear_invernadero_para_alertas`, en orden de id: activo o no, como COM-DCD-FLT, D-64 punto 12) → el cliente → las
    variedades → los sectores → los lotes → las partidas → la venta → sus detalles → las **cosechas** → las reservas y sus líneas → las
    **entregas** (y, por `cancelar_orden_incluida`, sus insumos y reservas de insumo) → el **enlace**. Se cruza bien con la concreción de una
    cosecha (la fila de la cosecha), con la planificación y el inicio de ruta (el invernadero) y con la decisión del cliente (la venta y el
    enlace).
  - **Iniciar y finalizar la ruta, y el intento fallido** (COM-INI-RUT, COM-FIN-RUT y 4a de COM-CNC-ENT; COM-06a, D-66 punto 11): la cuenta
    del Transportista (y, en el intento fallido, la del Vendedor) → el **invernadero** de su `TransportistaInvernadero` (el de origen de sus
    entregas) → el **vehículo** (inicio y fin) → las **entregas** de la ruta, releídas (o la entrega del intento). El inicio toma el invernadero
    **antes** de cambiar el vehículo: así COM-ASG-TRP, PROD-PNF-ENV, COM-CNL-CVT y COM-PNF-ENT, que toman el mismo invernadero, ven bien si una
    entrega está en curso.
  - **Concretar una entrega** (COM-CNC-ENT, COM-06a): cuentas (el actor, el Vendedor del contrato, el Agrónomo del invernadero de origen) →
    el **invernadero de origen** → las **variedades** → los **lotes** de origen → las **partidas** de origen → el **contrato** → sus
    **detalles** → la **entrega** (`OrdenTrabajo`) → sus líneas y sus **reservas de stock** con sus `DetalleReserva` → los
    `InsumoInvernadero` de los envases (reservados y declarados, en orden de id) y sus lotes → las **reservas de insumo**; desde COM-06b, al
    final, el **enlace** que crea. Es el orden de «Cosecha y cámara» con la entrega y los envases al final, como «Cancelar una compra-venta».
    Las funciones de núcleo de `produccion` (`docs/api/produccion.md`, sección 10) no bloquean nada más. Se cruza bien con COM-ASG-TRP y con
    el envasado (el invernadero), con PROD-VNC-CAM y la merma en cámara (el invernadero y la partida) y con COM-CNL-CVT (el invernadero y el
    contrato).
  - **Confirmar una entrega** (COM-CNF-ENT, COM-06b): la cuenta del Vendedor → el **invernadero de origen** (`bloquear_invernadero_para_alertas`)
    → la **entrega** → el **enlace** (`docs/patrones/enlace_del_cliente.md`, sección 5). **Atender una entrega no reconocida** (COM-ATN-ENR):
    las cuentas → el invernadero (`bloquear_invernadero_para_alertas`) → la entrega → la `AlertaComercial`.

- Solicitudes y resolución del suministro (COM-07a y COM-07b, D-69 punto 11).
  - **Resolver o anular una solicitud** (COM-EVL-DSC, COM-RSV-QJA y COM-ANL-SRV, COM-07a): las cuentas (el Gerente y el Vendedor del contrato)
    → el **invernadero de origen** de la entrega (`bloquear_invernadero_para_alertas`: activo o no; escribe la bitácora y resuelve la alerta)
    → el **suministro** (el contador de incumplimientos: dos aceptaciones del mismo contrato quedan en fila) → la **entrega** (el cobro de
    COM-08a la bloquea también, así no se cobra mientras se registra la aceptación; «Cobranza», abajo) → la **solicitud** (y su hija) → su `AlertaComercial`. Va
    en el mismo sentido que la concreción (invernadero → contrato → entrega): no se cruzan. Dos solicitudes de entregas de invernaderos
    distintos del mismo contrato toman cada una su invernadero y después el mismo suministro: tampoco se cruzan.
  - **Resolver un suministro** (COM-RSV-SUM, COM-07b): el orden de «Cancelar una compra-venta» con el **suministro** en lugar de la venta:
    cuentas (el Vendedor, los Capataces y los Agrónomos, los transportistas de las entregas) → los **invernaderos** de las reservas y de las
    entregas (`bloquear_invernadero_para_alertas`, en orden de id) → el cliente → las variedades → los sectores → los lotes → las partidas →
    el **suministro** → sus detalles → las **cosechas** → las reservas y sus líneas → las **entregas** (y, por `cancelar_orden_incluida`, sus
    insumos y reservas de insumo). Sin enlaces. Se cruza bien con la concreción de una cosecha (la fila de la cosecha), con la planificación,
    el inicio de ruta y la concreción de una entrega (el invernadero), con la pre-reserva (el invernadero y el suministro) y con una
    aceptación o una anulación del mismo contrato (el invernadero y el suministro). Lo que la lectura previa no vio y aparece al bloquear
    (una fila de otro invernadero) obliga a repetir una vez (6a de COM-RSV-SUM; `docs/casos_de_uso/comercial/resolucion.md`).

- Cobranza (COM-08a y COM-08b, D-94 punto 8).
  - **Registrar un cobro** (COM-REG-CBR, COM-08a): las cuentas (el actor y los Vendedores de los contratos de las entregas, en orden de id) →
    los **invernaderos de origen** de las entregas (`bloquear_invernadero_para_alertas`, en orden de id: activos o no; resuelve la alerta
    «pago en mora») → las **entregas** (en orden de id). Sin el suministro: el cobro no lo cambia. Es una parte del orden de «Resolver o anular
    una solicitud» (invernadero → suministro → entrega): una aceptación y un cobro de la misma entrega quedan en fila en la entrega y el
    segundo ve la huella cambiada. Dos cobros de la misma entrega: el segundo ve la línea vigente (10a).
  - **Anular un cobro** (COM-ANL-CBR, COM-08b): el orden de «Registrar un cobro» → el **pago** y sus líneas. Se cruza bien con el registro del
    cobro correcto (el pago nuevo nace después) y con la anulación de una solicitud de la misma entrega (la entrega).
  - **Vencer pagos** (paso 30, COM-08a): por entrega, en su transacción, el invernadero de origen → la entrega.
  - **Cobrar al cancelar una compra-venta** (6a de COM-CNL-CVT, COM-08b): el orden de «Cancelar una compra-venta», sin cambios; el pago nace
    al final.

## Contabilidad: el ejercicio se bloquea último (D-86)

Quien crea un asiento (propio o desde otra app) bloquea **todo lo suyo primero** (la operación, las cuentas, los lotes, los orígenes) y el
`EjercicioContable` destino **al final**, con `select_for_update(no_key=True)`: así dos operaciones distintas que asientan a la vez no se
cruzan (una espera a la otra solo en el último paso, el de más corta duración). El contraasiento bloquea primero el asiento a anular y
después el ejercicio. Detalle y receta: `docs/patrones/asientos.md`.

## `compras` (CMP-01 a CMP-06, D-88 y D-90)

Toda operación de compras sigue el orden de `docs/patrones/stock.md`, sección 5, punto 8. Lo particular:

- ABM de proveedores (CMP-01): cuentas → la fila del proveedor. La unicidad del CUIT la asegura la restricción `UNIQUE` (no un bloqueo): la
  segunda alta concurrente recibe `IntegrityError` y se traduce al mensaje del caso de uso.
- Enviar una cotización por el enlace (CMP-ENV-COT): `Proveedor` → `Pedido` → `EnlaceProveedor`, y releer los tres (el pedido pudo cancelarse
  o vencer; el proveedor pudo darse de baja; el enlace pudo usarse en otra pestaña). La única `(pedido, proveedor)` de `Cotizacion` es la red.
- Cancelar un pedido, aprobar o rechazar una orden: el invernadero de destino primero (si toca tránsito o alertas), después el orden del punto 8.
- Recepción, cierre con faltante y corrección (CMP-04, CMP-06): leen la orden sin bloquear para saber qué invernaderos e insumos tomar,
  bloquean en el orden completo (cuentas → invernadero → insumo → `InsumoInvernadero` → lotes → … → ejercicio) y vuelven a leer.
- El pago (CMP-05): cuentas → `OrdenCompra` → `Pago` → ejercicio. La única `(orden, proveedor)` de `Pago` es la red.
