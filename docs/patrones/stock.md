# Patrón · Stock de insumos: lotes, FEFO, reservas, faltante y alertas

Resumen de cómo se calcula y se mueve el stock en `inventario` (INV-01 e INV-02) y de lo que `produccion` y `compras` esperan de él.
Sale de las reglas 3 y 8 de 8.4, 5 y 6 de 8.13, 1 a 5 de 8.19 y 3 a 5 de 8.23 del modelo, y de CMP-AJT-STK, CMP-REV-VNC, CMP-HAB-IIN
y CMP-CNS-IIN. Si algo de acá contradice una decisión o un caso de uso, manda la decisión o el caso de uso: avisá.

Modelos: `docs/modelo/inventario.md`. Lo que otras apps llaman: `docs/api/stock.md`. Lo que otras apps registran:
`docs/api/extensiones_de_inventario.md`.

## 1. Las cantidades, con nombre propio

Todo se calcula **para una fecha `hoy`** (la del invernadero: `django.utils.timezone.localdate()`, porque el proyecto ya usa `TIME_ZONE = "America/Argentina/Buenos_Aires"`) y lo hace un solo módulo,
`inventario/servicios/stock.py`. Ninguna pantalla ni otro servicio vuelve a hacer estas cuentas.

| Nombre | Fórmula | Dónde se usa |
|---|---|---|
| **Stock actual** (`/cantActualInsumo`) | Σ `cantidad_disponible` de **todos** los lotes del `InsumoInvernadero`, incluido el faltante sin lote | Total de CNS-IIN; baja y deshabilitación (stock ≠ 0); resumen de los ajustes |
| **Stock vigente** (`hoy`) | Σ `cantidad_disponible` de los lotes **no vencidos hoy** (sin fecha de vencimiento, o con fecha ≥ hoy) **más** el faltante sin lote | La base del stock libre y de «sin cobertura» |
| **Reservado** | Σ `cantidad_reservada` de las `ReservaInsumo` activas del `InsumoInvernadero` (`produccion`, por `registrar_reservas_de_insumo`; sin registrantes, 0) | Stock libre |
| **Stock libre** (`hoy`) | stock vigente − reservado. **Puede ser negativo** (regla 5 de 8.13) | CNS-IIN, bajo el mínimo, planificación |
| **Disponible para planificar** (`f`) | `max(0, stock libre calculado a la fecha f)`: no cuenta los lotes que ya estarán vencidos en la fecha programada `f` de la orden (regla 8 de 8.4) | PRD-01 y PRD-02 |
| **En tránsito** | `cant_transito_insumo` (0 en esta ronda) | Bajo el mínimo y impedimentos |
| **Bajo el mínimo** | `cant_min_insumo > 0` y stock libre(`hoy`) + tránsito < mínimo | Alerta y marca de CNS-IIN |
| **Stock inconsistente** | stock vigente(`hoy`) < reservado (incluye el stock vigente negativo) | Alerta y marca «stock negativo» / «no cubre las reservas» |

Un lote está **vencido** desde el día siguiente a su fecha de vencimiento: el día de la fecha todavía se usa (regla 4 de CMP-REV-VNC).

### Stock inconsistente: qué se mide

El caso de uso (CMP-AJT-STK, postcondiciones h e i; extensión 12b) mide **el stock sin lotes vencidos**; la regla 6 de 8.13 y el
prototipo miden el stock total. **Se usa el del caso de uso** (L7). La consecuencia práctica: un lote que vence puede volver
inconsistente un insumo sin que nadie opere. CMP-REV-VNC no reevalúa esa alerta (no lo pide su caso de uso), así que se
reevalúa en la próxima operación de stock; está anotado en `docs/temas_abiertos.md`. (Dos definiciones conviven sin pisarse: la de la
tabla de la sección 1 es la que usan las alertas y las marcas; la postcondición i y la extensión 12b de CMP-AJT-STK la usan para decidir si
el ajuste deja inconsistente el insumo, y son la misma cuenta: stock vigente(`hoy`) < reservado.)

«Sin cobertura»: las órdenes se cubren por fecha programada, de la más cercana a la más lejana (y por id si empatan), con el stock
vigente que no sea negativo; las que no alcanzan se nombran en la alerta. Lo calcula `ordenes_sin_cobertura(iin, hoy)` con lo que
informa `registrar_ordenes_que_reservan`.

## 2. Lotes y FEFO

- Todo ingreso entra en un `LoteInsumo`. Un lote en 0 se conserva (trazabilidad).
- **FEFO** (`proponer_lotes_fefo(iin, cantidad, fecha)`): ordena por `fecha_vencimiento` ascendente; si el insumo no controla
  vencimiento, por `fecha_ingreso` ascendente y por id; **no propone lotes vencidos a `fecha` ni el faltante sin lote**; devuelve
  `[(lote, cantidad)]` y un `resto` (lo que no entra en lotes). Quien registra puede corregir la propuesta.
- Un lote de un insumo que no controla vencimiento nunca vence: por eso es siempre vigente.

## 3. Salida por consumo y faltante sin lote

`registrar_salida_por_consumo(iin, partes, *, origen_id, fecha=None)` (la llama `produccion`; ver `docs/api/stock.md`):

1. Dentro de la transacción de quien llama, con el invernadero y el `InsumoInvernadero` ya bloqueados (ver «Orden de bloqueo»), vuelve a leer los lotes y
   los bloquea en orden de id.
2. Por cada parte `(lote, cantidad)` descuenta del lote y crea **un** `MovimientoInsumo` de tipo_movimiento «salida por consumo» sobre ese lote, con `origen = origen_id` (el consumo, D-52) y `fecha` = la fecha recibida (la efectiva de la siembra; hoy si no se pasó) y la hora actual de la operación (D-50 punto 7).
3. Si una parte excede lo disponible del lote, o si lo pedido supera lo que hay en lotes, **no se bloquea** (regla 5 de 8.13): lo que falta
   sale del **faltante sin lote**, que se crea con la primera salida que lo necesita (sin cantidad ingresada, ingreso ni
   vencimiento) y baja su `cantidad_disponible` (negativa). Genera su propio movimiento (también con `origen = origen_id`).
4. Llama a `reevaluar_alertas_del_insumo`, que crea la alerta «stock inconsistente» si corresponde.

Regularizar el faltante:

- **Recuento físico** (CMP-AJT-STK): lo deja en cero, con un movimiento «ajuste positivo» sobre ese lote por lo que faltaba. No es físico.
- **Corrección entre lotes** con el faltante como destino: lo acerca a cero. Ni suma ni resta stock total.
- Un ajuste negativo **nunca** sale de él; la carga inicial y el «otro» que suma **no** lo tocan (decisión del CU, ver «Diferencias con el
  caso de uso» en el modelo). La recepción de `compras` (ronda futura) cancelará primero el faltante, como dice la regla 4 de 8.23.

## 4. Alertas

Cuatro tipos de `inventario`, registrados en `InventarioConfig.ready()` con `maestros.alertas.registrar_tipo_de_alerta`
(`docs/api/alertas.md`). Todos de **estado** (`Clase.ESTADO`), con el destinatario `AGRONOMO_O_GERENTE` (D-41) salvo lo dicho de
CMP-REV-VNC. Códigos de hasta 50 caracteres:

| Código | Nombre | Severidad | Clave | Quién la crea / resuelve |
|---|---|---|---|---|
| `inv_stock_inconsistente` | Stock inconsistente | `CRITICA` | `insumo:<id>` | La crea cualquier operación que rompa la condición; la resuelve cualquier operación que la cubra (ajuste, consumo, cierre de reservas) |
| `inv_insumo_bajo_minimo` | Insumo bajo el mínimo | `ADVERTENCIA` | `insumo:<id>` | La crean HAB, MOD, deshabilitar y REV-VNC (regla 11); la resuelven MOD, DSH, BAJ y el ajuste (por ahora, la recepción de `compras`) |
| `inv_insumo_por_vencer` | Insumo por vencer | `ADVERTENCIA` | `lote:<id>` | CMP-REV-VNC; la resuelve REV-VNC al vencer o agotarse el lote, o el consumo o ajuste que lo agota |
| `inv_insumo_vencido` | Insumo vencido | `CRITICA` | `lote:<id>` | CMP-REV-VNC; la resuelve el consumo o ajuste que agota el lote |

Las severidades son las del prototipo (stock inconsistente en rojo, bajo el mínimo en amarillo); el modelo no las define.
La clave es un texto (`"insumo:12"`, `"lote:7"`): la API la guarda tal cual.

**Un solo punto de reevaluación:** `reevaluar_alertas_del_insumo(insumo_invernadero, hoy) -> Reevaluacion`, en
`inventario/servicios/alertas_de_stock.py`. Lo llaman, **dentro de su transacción y con el invernadero ya bloqueado**, todos los
servicios que cambian stock, mínimo, estado o reservas. Hace tres cosas idempotentes:

1. `inv_stock_inconsistente`: la asegura si el stock vigente < reservado y la resuelve si no.
2. `inv_insumo_bajo_minimo`: la asegura si está bajo el mínimo y su estado es activo; la resuelve si no (o si el `InsumoInvernadero` pasó a inactivo, o si su `Insumo` del catálogo está inactivo: solo ocurre con una semilla dada de baja con su variedad, que conserva sus existencias activas).
3. Resuelve las `inv_insumo_por_vencer` e `inv_insumo_vencido` de los lotes cuya cantidad disponible llegó a 0.

Devuelve las alertas creadas y las resueltas, para que el servicio las ponga en los `datos` de su registro de auditoría
(`alertas_creadas`, `alertas_resueltas`; `docs/api/alertas.md`, «Auditoría»). Las alertas de vencimiento (por vencer y vencido) **las crea
solo CMP-REV-VNC**.

**La descripción** de las de vencimiento identifica insumo, lote, cantidad disponible y fecha (regla 5 de 8.23), por ejemplo:
`Nutriente A · lote 7 · 12,5 L disponibles · vence el 02/12/2026`. La de «stock inconsistente» identifica el insumo, la
operación que la generó y las órdenes sin cobertura.

## 5. Orden de bloqueo en `inventario`

Se suma al orden de `docs/patrones/bloqueos.md` (cuentas → invernadero → alertas del invernadero → filas de las apps altas), siempre con
`select_for_update(no_key=True)`:

1. cuentas (`Usuario`), en orden de id;
2. el invernadero (`bloquear_invernadero_activo`, o `bloquear_invernadero_para_alertas` si solo se crean o resuelven alertas);
   si la operación toca varios invernaderos (baja del insumo, baja o reactivación de una variedad), todos, en orden de id;
2b. `Cultivo` y `Variedad` (INV-03; PRD-01 bloquea la variedad antes de crear un lote o una orden de ella), cultivo primero y variedades en orden de id;
2c. `SectorProduccion` (`maestros.servicios.sectores.bloquear_sectores`, en orden de id; lo usan PRD-01 y PRD-02 antes de comprometer o liberar agujeros, y MAE-03 al modificar o dar de baja sectores). Va **después** del invernadero y de la variedad y **antes** de los insumos (D-50 punto 10);
3. `TipoInsumo`;
4. `Insumo`;
5. `InsumoInvernadero`, en orden de id;
6. `LoteInsumo` del `InsumoInvernadero`, en orden de id (los lotes de varios `InsumoInvernadero`, por `InsumoInvernadero` y por id);
7. lo de `produccion` (reservas, órdenes, lotes y ocupaciones), después de todo lo anterior.

Se puede **saltear** un nivel pero **no volver atrás**. Después de bloquear se vuelve a leer lo que se va a cambiar. Cuando hay que
saber qué invernaderos bloquear antes de bloquearlos (baja del insumo), se leen sin bloqueo, se bloquean y se vuelve a leer. Una
operación que deje stock distinto de cero o cree un lote llama a `bloquear_invernadero_activo` **antes** de crearlo (contrato de D-40:
lo que impide la baja del invernadero).

## 6. Auditoría

- Una acción por caso de uso (D-36), con los nombres que fija cada tarea. Los **movimientos** no se auditan uno por uno: van como
  referencias en los `datos` del registro del caso de uso (el kárdex ya los guarda).
- `Decimal` y fechas, como texto (`docs/patrones/auditoria.md`). Para eso `inventario/servicios/formato.py` tiene `texto_cantidad(valor,
  unidad)` (con los decimales de la unidad) y `texto_precio(valor)`.
- La corrida de CMP-REV-VNC audita con `usuario=None` (D-27).

## 7. Pruebas

- Fábricas en `inventario/tests/fabricas.py`: `tipo_de_insumo(...)`, `insumo(...)`, `existencia(insumo, invernadero, minimo=0, precio=...)`,
  `lote(existencia, disponible, vence=None, ingreso=...)` (crea también su movimiento de ingreso, para que se cumpla la regla 1 de 8.19),
  `faltante(existencia, cantidad)` y `asegurar_datos_de_inventario()` con el mixin `ConDatosDeInventario` (mismo esquema que `ConGeoref`, en
  `docs/patrones/datos_de_migracion.md`): vuelve a cargar las cuatro categorías del sistema si un `TransactionTestCase` vació la base.
- Un registrante falso de reservas y de ordenes (`reservas_de_prueba(...)`, administrador de contexto) para probar sin `produccion`.
- **Invariantes que toda prueba de un servicio de stock verifica** (`verificar_invariantes(existencia)` en las fábricas): para cada lote,
  ingresos − salidas = `cantidad_disponible`; ningún lote que no sea el faltante queda negativo; el faltante nunca es positivo; a lo sumo
  un faltante; cada cambio de cantidad tiene exactamente un movimiento.
- La concurrencia se prueba con `correr_a_la_vez` (`@tag("concurrencia")`): un consumo y un ajuste simultáneos sobre el mismo insumo, y
  dos ajustes simultáneos.
