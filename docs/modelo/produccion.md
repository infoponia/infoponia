# Modelo de dominio · produccion

Copia para el repo de «Copia de modelo_dominio»: fichas de `OrdenTrabajo`, `ReservaInsumo`, `Siembra`, `TransicionEtapa`, `OcupacionSector`, `Lote`,
`Bitacora`, `Consumo` y `Merma`, con las reglas que las tocan (8.9, 8.13, 8.20, 8.21 y 8.22), más las tablas de enlace que `produccion` debe declarar por A2.
Versión de la ronda 22, consultada el 19/11/2026. Cotejado con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. **PROVISORIO.**

Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Si el modelo y un caso de uso no coinciden, **manda el caso de uso** (D-07: la ronda abierta
rige aunque el diagrama no la refleje); las diferencias que ya detectamos están en «Diferencias con el modelo y con los casos de uso» al final.

Alcance de la ronda «Producción 1»: **órdenes de siembra y de transición** (D-45). `Cosecha`, `Entrega` y `MantenimientoTecnico` son hijas de `OrdenTrabajo` en el modelo, pero
no se crean ahora. `AplicacionInsumos`, `ImputacionCosto`, `FueraDeServicio` y `Reubicacion` (MD-28, MD-75, MD-76, MD-77) las crean PRD-03 y PRD-04 (lote 5) y están al final de este archivo.
Cómo se guardan los datos de esta ficha: **D-50**.

## Quién crea qué

| Tarea | Crea |
|---|---|
| CON-01 | `contabilidad.OrigenDocumento` (`docs/modelo/contabilidad.md`, D-52): el padre de `OrdenTrabajo`, `Bitacora` y `MovimientoInsumo` |
| PRD-01 | `OrdenTrabajo`, `ReservaInsumo`, `Siembra`, `OcupacionSector`, `Lote`, `Bitacora`, `Consumo`. Una sola migración inicial de `produccion` (depende de `contabilidad.0001_initial` y de `inventario`), que también crea la secuencia `produccion_orden_numero_seq` |
| PRD-02 | `TransicionEtapa`, `Merma`, `AlertaDeMerma` (migración nueva que depende de la de PRD-01) |
| PRD-03 | `AplicacionInsumos`, `ImputacionCosto`; el origen `aplicacion` del consumo (D-51 punto 3); los tipos de evento `aplicacion`, `otro_evento` y el interno `consumo` en `Bitacora.TipoEvento`. Migración `0003` |
| PRD-04 | `FueraDeServicio`, `Reubicacion`; `OcupacionSector.reubicacion` y `orden` nula (D-51 punto 1); los tipos `fuera_de_servicio` y `reubicacion`. Migración `0004` |

## Convenciones de esta ficha

- Nombres de código según D-05 (snake_case, conservando el sufijo del modelo: `fechaProgramadaOrden` → `fecha_programada_orden`).
- **Cantidades de insumo:** `Decimal` con 3 decimales (`DecimalField(max_digits=14, decimal_places=3)`). **Montos:** `DecimalField(14, 2)`, en pesos, redondeo
  `ROUND_HALF_UP`. **Plantas y agujeros:** enteros (`PositiveIntegerField` o `IntegerField` con restricción). Nunca `float`.
- **Fechas:** `DateField`; «hoy» es `django.utils.timezone.localdate()` (`America/Argentina/Buenos_Aires`). La hora de la bitácora es `timezone.localtime().time()`.
- **Bajas:** una orden no se borra: se cancela. Un lote no se borra: se finaliza. Las claves foráneas son `PROTECT`.
- **Auditoría:** `Decimal` y fechas **van como texto** en `cambios` y `datos` (`docs/patrones/auditoria.md`).
- **Herencia:** multitabla de Django (D-50 y D-52): `OrdenTrabajo(OrigenDocumento)`, `Bitacora(OrigenDocumento)` y debajo `class Siembra(OrdenTrabajo)`. La clave de `OrdenTrabajo` y de `Bitacora` es `origendocumento_ptr` (`.id` sigue funcionando); la de `Siembra`, `ordentrabajo_ptr`. Los `id` se comparten con todos los documentos y **no son consecutivos por tipo**. Una consulta de órdenes parte de `OrdenTrabajo` y usa `tipo`.
- **Códigos legibles:** `OrdenTrabajo.codigo` = `f"OT-{numero:04d}"`, con `numero` una columna entera única que asigna el servicio con la secuencia `produccion_orden_numero_seq` (D-52 punto 3; puede haber huecos si una transacción se deshace); `Lote.codigo` = `f"L-{id}"` (`Lote` no hereda, su `id` es propio). Los dos son propiedades; es lo que muestran las pantallas y las notificaciones.

## Listas fijas (`TextChoices`, sin tabla)

| Lista | Valores (clave → texto) |
|---|---|
| `OrdenTrabajo.Estado` | `a_realizar` → «a realizar»; `concretada` → «concretada»; `cancelada` → «cancelada» |
| `OrdenTrabajo.Tipo` | `siembra` → «Siembra»; `transicion` → «Transición de etapa» (después: `cosecha`, `entrega`, `mantenimiento`) |
| `OrdenTrabajo.Prioridad` | `alta`, `media`, `baja` (opcional en siembra y transición, MD-73) |
| `ReservaInsumo.Estado` | `activa`, `consumida`, `cancelada` |
| `Lote.Estado` | `activo`, `finalizado` (MD-51) |
| `Bitacora.TipoEvento` | `siembra`, `transicion`, `merma` (PRD-01 y PRD-02); `aplicacion`, `otro_evento` y `consumo` (interno: el de una aplicación, no se lista; PRD-03); `fuera_de_servicio` y `reubicacion` (PRD-04). Después: `cosecha` e `incumplimiento_de_clausula` |
| `Merma.Causa` (lote en pie) | `plaga`, `enfermedad`, `falla_riego_o_nutrientes`, `condiciones_ambientales`, `dano_mecanico`, `descarte_por_seleccion`, `otra`. La partida en cámara (fuera de la ronda) suma `dano_en_camara`, `dano_en_entrega` y `vencimiento_en_camara` (MD-78) |

Textos visibles de las causas: «Plaga», «Enfermedad», «Falla de riego o nutrientes», «Condiciones ambientales», «Daño mecánico», «Descarte por selección», «Otra» (los del prototipo, `CAUSAS`).
El orden de **ordenación** de órdenes es: fecha programada (más antigua primero), después prioridad (`alta`, `media`, `baja`; sin prioridad cuenta como `media`), después `id`.

---

## OrdenTrabajo

Bloque: Mantenimiento, alertas y auditoría. Vive en `produccion` (D-46). Orden planificada por el Agrónomo o por InfoPonia para que el Capataz (o el Técnico) la realice.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idOrden` | — | El `id` automático |
| (nuevo) `tipo` | `OrdenTrabajo.Tipo` | Discriminador de la herencia. Obligatorio, nunca cambia |
| `fechaCreacionOrden` | fecha | → `fecha_creacion_orden`. La de hoy al planificar (`auto`, no editable). **Nunca es posterior a hoy** |
| `fechaProgramadaOrden` | fecha | → `fecha_programada_orden`. Obligatoria. Al planificar, ≥ hoy |
| `fechaResolucionOrden` | fecha, nula | → `fecha_resolucion_orden`. Nula mientras está «a realizar»; la de hoy al concretarla o cancelarla (sin fechas retroactivas). Vale para los dos desenlaces (concreción y cancelación), como OrdenCompra.fechaResolucion. Para saber si se concretó hay que mirar `estado_orden`, no esta fecha |
| `descripcionOrden` | texto libre, opcional | → `descripcion_orden`. Hasta 500 caracteres; vacío si no se indicó |
| `estadoOrden` | `OrdenTrabajo.Estado` | → `estado_orden`. Nace «a realizar». Solo cambia a «concretada» o «cancelada» y no vuelve atrás (regla 14 de 8.12) |
| `prioridadOrden` | `OrdenTrabajo.Prioridad`, nula | → `prioridad_orden`. Opcional en siembra y transición (MD-73). **Obligatoria en mantenimiento** (ronda 19): la verifica un `CheckConstraint` por `tipo` que agrega IOT-05 (D-53, punto 6) |
| (nuevo) `motivo_cancelacion` | texto, nulo | Texto libre, obligatorio al cancelar (paso 5 de PROD-CNL-ORD): de 1 a 300 caracteres, sin espacios al borde. Nulo en toda orden que no está «cancelada». Mismo criterio que OrdenCompra.motivoRechazo (texto libre, obligatorio al resolver con rechazo; el modelo no le fija largo): acá 300, como `motivo_diferencia_siembra` y `motivo_fuera_de_servicio`. Ver «Diferencias», n.º 17 |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R046 | Agrónomo, «planifica» | OrdenTrabajo → Agrónomo = 0..1 | Vigente. `agronomo`, FK a `core.Agronomo` (nula = planificó InfoPonia), `PROTECT`. **Sube al padre** (D-50) |
| — | Invernadero | OrdenTrabajo → Invernadero = 1 | El modelo lo pone en `Siembra` (R136) y, para la transición, lo da el lote (R160 + R099). **Sube al padre** como `invernadero`, FK a `maestros.Invernadero`, `PROTECT`; en una transición debe ser el del lote (prueba de invariantes) |
| R075, R077, R078 | Capataz, «realiza» | — | **No está en el padre** (D-53, que enmienda D-50 punto 2): cada hija que tiene Capataz lo declara (`Siembra`, `TransicionEtapa` y, después, `Cosecha`) con la clase abstracta `ConCapataz` (abajo). `Entrega` y `MantenimientoTecnico` no lo tienen; esta última lleva `tecnico` (R047) |
| R138 | ReservaInsumo, composición | OrdenTrabajo → ReservaInsumo = 0..* | Ver `ReservaInsumo` |

Herencias: **hija directa de `OrigenDocumento`** (`contabilidad`, D-52; `TIPO_DE_ORIGEN = orden_de_trabajo`). Es padre de `Siembra` y `TransicionEtapa` (esta ronda) y de `Cosecha`, `Entrega` y `MantenimientoTecnico` (rondas futuras).

### Clase abstracta `ConCapataz` (D-53)

`produccion/models.py` declara `class ConCapataz(models.Model)` con `Meta.abstract = True`: el campo `capataz` (FK a `core.Capataz`, `PROTECT`, obligatoria, `related_name="%(class)s_asignadas"`) y su índice. La heredan `Siembra` y `TransicionEtapa` (junto a `OrdenTrabajo`: `class Siembra(OrdenTrabajo, ConCapataz)`) y, después, `Cosecha`. No crea tabla. Quien necesite «las órdenes de un Capataz» llama a `ordenes.ordenes_del_capataz` (`docs/api/produccion.md`); **nadie arma esa unión por su cuenta**.

Hijas futuras y el IoT: `MantenimientoTecnico` hereda de `OrdenTrabajo` **sin** `ConCapataz` y declara `tecnico` (R047, obligatoria, en `iot`, D-37 A2); `Entrega` tampoco la tiene. IOT-05 agrega el valor `mantenimiento` a `OrdenTrabajo.Tipo` y la restricción de la prioridad obligatoria en ese tipo.

### Restricciones de la base

- `estado_orden` y `tipo` dentro de sus listas; `prioridad_orden` nula o dentro de la lista.
- `numero` único y no nulo (lo asigna la secuencia).
- `fecha_resolucion_orden` nula si y solo si el estado es «a realizar».
- `motivo_cancelacion` no nulo y no vacío si y solo si el estado es «cancelada».
- `fecha_programada_orden >= fecha_creacion_orden` (la programada nunca es anterior a la de creación).
- Índices: `(invernadero, estado_orden, fecha_programada_orden)` (lista). El índice del Capataz está en cada hija con Capataz (`ConCapataz`: `(capataz)`; el estado vive en el padre).

---

## ReservaInsumo

Bloque: Compras e inventario (con composición hacia `OrdenTrabajo`). Vive en `produccion` (D-46). Compromiso temporal de una cantidad de un insumo del invernadero, generado al planificar una orden y resuelto al concretarla o cancelarla.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idReservaInsumo` | — | El `id` automático |
| `cantidadReservada` | cantidad > 0 | → `cantidad_reservada`. La que resta del stock libre mientras la reserva está «activa» |
| `cantidadUtilizada` | cantidad ≥ 0, nula | → `cantidad_utilizada`. Nula mientras está activa; se carga al concretar. **Nunca supera la reservada** (PROD-CNC-SMB, extensión 13a) |
| `cantidadDevuelta` | cantidad ≥ 0, nula | → `cantidad_devuelta`. Nula mientras está activa. Entre 0 y `cantidad_reservada − cantidad_utilizada` |
| `estado` | `ReservaInsumo.Estado` | Nace «activa». Al concretar: «consumida» si lo consumido es mayor que 0, «cancelada» si es 0. Al cancelar la orden: «cancelada», sin cantidad utilizada ni devuelta |
| `fechaReserva` | fecha | → `fecha_reserva`. La de hoy al planificar |

Lo **consumido** no se guarda: es `cantidad_reservada − cantidad_devuelta` (con `cantidad_utilizada ≤ cantidad_reservada`, la fórmula de la regla 13 de 8.9 se simplifica; ver «Diferencias»).

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R138 | OrdenTrabajo, composición | ReservaInsumo → OrdenTrabajo = 1 | Vigente. `orden`, FK a `OrdenTrabajo`, `PROTECT` |
| R139 | InsumoInvernadero | ReservaInsumo → InsumoInvernadero = 1 | Vigente. `insumo_invernadero`, FK a `inventario.InsumoInvernadero`, `PROTECT` (A2: la declara `produccion`, nivel mayor) |

### Restricciones de la base

- Único `(orden, insumo_invernadero)`: una orden reserva un insumo una sola vez.
- `cantidad_reservada > 0`. Estado «activa»: `cantidad_utilizada` y `cantidad_devuelta` nulas. Estado «consumida»: ambas no nulas. Estado «cancelada»: ambas nulas (cancelación de la orden) **o** ambas no nulas (concreción con consumo 0, que cancela la reserva con lo utilizado y devuelto cargados).
- `cantidad_devuelta <= cantidad_reservada - cantidad_utilizada` cuando ambas existen.
- Índice `(insumo_invernadero, estado)` (lo usa `reservado_de`).

---

## Siembra

Hija de `OrdenTrabajo` (`tipo = siembra`). Orden de sembrar una variedad en sectores de Germinación de un invernadero; al concretarla crea el lote.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idSiembra` | — | Es `ordentrabajo_ptr` (y por ella el `id` de `OrigenDocumento`) |
| `cantplantinesSiembra` | entero > 0 | → `cant_plantines_siembra`. **La cantidad planificada**: no cambia al concretar. La real es `Lote.cantidad_inicial` (suma de los agujeros ocupados) |
| `fechaSiembra` | fecha, nula | → `fecha_siembra`. Nula mientras está «a realizar»; la **fecha efectiva** al concretar (entre la creación de la orden y hoy) |
| `motivoDiferenciaSiembra` | texto, opcional | → `motivo_diferencia_siembra`. Hasta 300 caracteres. Solo si el total sembrado fue menor que lo planificado |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R104 | Variedad, «tiene» | Siembra → Variedad = 1 | `variedad`, FK a `maestros.Variedad`, `PROTECT` |
| R075 | Capataz, «realiza» | Siembra → Capataz = 1 | `capataz`, FK a `core.Capataz`, `PROTECT`, obligatoria. Por la clase abstracta `ConCapataz` (D-53): la persona asignada al planificar; se traspasa al nuevo Capataz del invernadero (regla 3 de 8.22). Es la única que puede concretar la siembra |
| R103 | Lote, «corresponde» | Siembra → Lote = 0..1; Lote → Siembra = 1 | La clave está en `Lote.siembra` (uno a uno): la siembra tiene lote si y solo si está concretada (regla 1 de 8.13) |
| R105 | Consumo, «genera» | Siembra → Consumo = 0..* | La clave está en `Consumo.siembra` (nula salvo en consumos de siembra) |
| R136 | Invernadero | 1 | Está en el padre (`invernadero`) |
| R140 | OcupacionSector, composición | Siembra → OcupacionSector = 1..* | Por `OcupacionSector.orden` (D-50) |

### Reglas que la tocan

- Regla 1 de 8.13: tiene lote si y solo si está «concretada». Regla 2 de 8.13: una siembra concretada tiene al menos un consumo (el de la semilla).
- Regla 3 de 8.13 (ocupaciones), regla 4 (agujeros comprometidos), regla 5 y 6 (cobertura y alerta «stock inconsistente», de `inventario`).
- Regla 5 de 8.20: las etapas del ciclo de la variedad no se modifican si la variedad tiene lotes (lo hace cumplir INV-03).
- Reglas de negocio de PROD-PNF-SMB y PROD-CNC-SMB (en `docs/casos_de_uso/produccion/siembra.md`).

---

## TransicionEtapa

Hija de `OrdenTrabajo` (`tipo = transicion`). Traslada **el lote entero** a la etapa siguiente de su ciclo. La crea PRD-02.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idTransicion` | — | Es `ordentrabajo_ptr` (y por ella el `id` de `OrigenDocumento`) |
| `cantTransferido` | entero > 0, nulo | → `cant_transferido`. Nulo mientras está «a realizar»; al concretar, la suma de los `cant_agujeros_ocupados` de sus ocupaciones |
| `fechaTransicion` | fecha, nula | → `fecha_transicion`. La **fecha efectiva** del traslado; nula mientras está «a realizar» (MD-53). Puede ser anterior a la creación de la orden y a la programada |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R160 | Lote, «traslada» | TransicionEtapa → Lote = 1; Lote → TransicionEtapa = 0..* | `lote`, FK a `Lote`, `PROTECT` |
| R107 | EtapaProductiva, «corresponde» | TransicionEtapa → EtapaProductiva = 1 | `etapa_destino`, FK a `maestros.EtapaProductiva`, `PROTECT`. La etapa de origen no se guarda (regla 1 de 8.20) |
| R077 | Capataz, «realiza» | TransicionEtapa → Capataz = 1 | `capataz`, FK a `core.Capataz`, `PROTECT`, obligatoria. Por la clase abstracta `ConCapataz` (D-53): la persona asignada al planificar; se traspasa al nuevo Capataz del invernadero (regla 3 de 8.22) |
| R080 | Bitacora, «genera» | TransicionEtapa → Bitacora = 1 (al concretar) | `bitacora`, `OneToOne` a `Bitacora`, nula hasta concretar |
| R164 | OcupacionSector, composición | TransicionEtapa → OcupacionSector = 1..* | Por `OcupacionSector.orden` |

### Restricciones de la base

- Un lote tiene a lo sumo **una** transición «a realizar» (regla 4 de 8.21). Como el estado está en el padre, no se expresa con una restricción de la base: lo garantiza el servicio con el bloqueo del lote y lo prueba la concurrencia (`docs/patrones/bloqueos.md`).
- `cant_transferido` y `fecha_transicion` nulos si y solo si la orden está «a realizar» o «cancelada».

### Reglas que la tocan

Regla 1 de 8.20 (origen y destino), regla 2 de 8.20 (fecha de entrada a Maduración), regla 3 de 8.20 (fecha máxima de cosecha), reglas 1 a 5 de 8.21 y reglas de negocio de PROD-PNF-TRN y PROD-CNC-TRN (`docs/casos_de_uso/produccion/transicion.md`).

---

## OcupacionSector

Parte de una orden de siembra o de transición. Lo que la orden planifica ocupar en un sector y, una vez concretada, lo que el lote ocupa de verdad.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idOcupacion` | — | El `id` automático |
| `cantAgujerosPlanificados` | entero > 0 | → `cant_agujeros_planificados`. Se fija al planificar y no cambia |
| `cantAgujerosOcupados` | entero ≥ 0 | → `cant_agujeros_ocupados`. Cero mientras la orden está «a realizar»; al concretar, lo realmente ocupado. **Baja** con cada merma por sector (PRD-03) y se pone en cero en el origen de una transición |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R095 | SectorProduccion, «corresponde» | OcupacionSector → SectorProduccion = 1 | `sector`, FK a `maestros.SectorProduccion`, `PROTECT` |
| R094 | Lote, «son de» | OcupacionSector → Lote = 0..1 | `lote`, FK nula a `Lote`, `PROTECT`. Tiene lote si y solo si su orden está concretada **y** ocupó al menos un agujero al concretar; lo conserva aunque después los libere (regla 3 de 8.13) |
| R140 / R164 | OrdenTrabajo (Siembra o TransicionEtapa), composición | OcupacionSector → orden = 1 | `orden`, FK a `OrdenTrabajo`, `PROTECT` (D-50: una sola clave, sin restricción C9) |

### Restricciones de la base

- `cant_agujeros_planificados > 0`; `cant_agujeros_ocupados >= 0`; `cant_agujeros_ocupados <= cant_agujeros_planificados`.
- Único `(orden, sector)`: una orden usa un sector una sola vez.
- `lote` nulo si `cant_agujeros_ocupados = 0` y la orden está «a realizar» o «cancelada» (lo verifica el servicio y la prueba de invariantes).

### Lo que se calcula de las ocupaciones (no se guarda)

- **Agujeros ocupados de un sector** = Σ `cant_agujeros_ocupados` de sus ocupaciones.
- **Agujeros comprometidos de un sector** = Σ `cant_agujeros_planificados` de sus ocupaciones cuya orden (siembra o transición) está «a realizar» (regla 4 de 8.13).
- **Capacidad libre** = `cant_agujeros_total − ocupados − comprometidos` (la da `maestros.servicios.sectores.agujeros_de`, que suma lo que informa `produccion`; ver `docs/api/produccion.md`).
- **Ocupaciones vigentes de un lote** = sus ocupaciones con `cant_agujeros_ocupados > 0`. La suma de sus ocupados es `Lote.cantidad_actual` (regla 1 de 8.21). Invariante probado.
- **Perfil familiar de un sector** = el de la variedad de los lotes con ocupaciones vigentes en él y de las órdenes de siembra o transición «a realizar» que lo usan; `None` si no tiene ninguno (regla de compatibilidad de PROD-PNF-SMB).

---

## Lote

Plantas de una misma siembra que atraviesan juntas las etapas del ciclo. Lo crea Concretar Siembra.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idLote` | — | El `id` automático; se muestra como `L-{id}` |
| `cantidadInicial` | entero > 0 | → `cantidad_inicial`. El total sembrado; no cambia |
| `cantidadActual` | entero ≥ 0 | → `cantidad_actual`. Baja con las mermas (y con la cosecha, fuera de la ronda). **Nunca negativa ni mayor que la inicial** |
| `estadoLote` | `Lote.Estado` | → `estado_lote`. Nace «activo»; pasa a «finalizado» cuando la cantidad actual llega a cero |
| (nuevo) `costo_acumulado` | monto ≥ 0 | Ver `docs/patrones/costo_del_lote.md`. Nace con la suma de los montos de consumo de la siembra; baja con cada merma; vale 0 con la cantidad actual en 0 |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R099 | Invernadero, composición | Lote → Invernadero = 1 | `invernadero`, FK a `maestros.Invernadero`, `PROTECT` |
| R100 | EtapaProductiva, «atraviesa» | Lote → EtapaProductiva = 1 | `etapa`, FK a `maestros.EtapaProductiva`, `PROTECT`. La etapa **actual**; nace en la de tipo Germinación del ciclo de la variedad y cambia en cada transición |
| R103 | Siembra | Lote → Siembra = 1 | `siembra`, `OneToOne` a `Siembra`, `PROTECT` (de ahí sale la variedad: `lote.siembra.variedad`) |
| R094 | OcupacionSector | Lote → OcupacionSector = 1..* | Por `OcupacionSector.lote` |
| R160 | TransicionEtapa | Lote → TransicionEtapa = 0..* | Por `TransicionEtapa.lote` |
| R082 | Bitacora | Lote → Bitacora = 1..* | Por `Bitacora.lote` |
| R040 | MovimientoInsumo | Lote → MovimientoInsumo = 0..* | **Se deriva, no se guarda (D-52 punto 6):** en una siembra, los movimientos de los consumos de su siembra (`consumo.movimientos_de_insumo`); en una aplicación, los de los consumos con `ImputacionCosto` al lote |

### Restricciones de la base

- `cantidad_actual >= 0` y `cantidad_actual <= cantidad_inicial`; `costo_acumulado >= 0`.
- `estado_lote = 'finalizado'` si y solo si `cantidad_actual = 0` (en esta ronda; la cosecha, fuera, también lo lleva a cero).
- `costo_acumulado = 0` si `cantidad_actual = 0`.

### Lo que se calcula de un lote (no se guarda)

| Dato | Cálculo |
|---|---|
| **Costo por planta** | `costo_acumulado ÷ cantidad_actual` (`cantidad_actual > 0`), a 2 decimales, solo para mostrar; las cuentas se hacen con la fracción exacta (ver `costo_del_lote.md`) |
| **Fecha de entrada a la etapa actual** (regla 5 de 8.21) | En la primera etapa del ciclo: `siembra.fecha_siembra`. En las demás: `fecha_transicion` de la transición concretada del lote cuya etapa destino es la etapa actual |
| **Fecha estimada de fin de la etapa actual** | fecha de entrada + `duracion_dias` de la etapa actual (`inventario.servicios.ciclos.etapas_de`) |
| **Fecha de entrada a Maduración** (regla 2 de 8.20) | La `fecha_transicion` de la transición concretada con destino de tipo Maduración |
| **Fecha máxima de cosecha** (regla 3 de 8.20) | Fecha de entrada a Maduración + `duracion_dias` de la etapa Maduración |
| **Fecha estimada de cosecha de una siembra** | `fecha_siembra` (o la programada) + `dias_hasta_maduracion` de la variedad |
| **Merma acumulada** (regla de PROD-REG-MRM) | Σ `cantidad_merma` de sus mermas con causa distinta de «descarte por selección», ÷ `cantidad_inicial` |
| **Última etapa del ciclo** | La de mayor `puesto_global` del tipo de etapa entre las etapas de la variedad |
| **Etapa siguiente** | La inmediata posterior en `puesto_global` entre las etapas de la variedad (regla 1 de 8.20) |

---

## Bitacora

Registro de un evento con fecha, hora y responsable. Aquí solo lo que escriben las siembras (consumo), las transiciones y las mermas.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idBitacora` | — | El `id` automático |
| `fechaBitacora` | fecha | → `fecha_bitacora`. Para la siembra, la efectiva; para la transición, la efectiva; para la merma de una transición, la efectiva; para las demás, hoy |
| `horaBitacora` | hora | → `hora_bitacora`. La hora actual del registro |
| `tipoEvento` | `Bitacora.TipoEvento` | → `tipo_evento` |
| `descripcionEvento` | texto, opcional | → `descripcion_evento`. Hasta 500 caracteres |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R081 | Invernadero | Bitacora → Invernadero = 1 | `invernadero`, FK a `maestros.Invernadero`, `PROTECT` |
| R082 | Lote | Bitacora → Lote = 0..1 | `lote`, FK nula a `Lote`, `PROTECT` |
| R106 | EtapaProductiva | Bitacora → EtapaProductiva = 0..1 | `etapa`, FK nula a `maestros.EtapaProductiva`, `PROTECT`. La etapa del lote en ese momento: en la merma de una transición, la de **origen** |
| MD-77 + MD-28 | SectorProduccion, «se realiza en» | Bitacora → SectorProduccion = 0..* | `sectores`, `ManyToManyField` a `maestros.SectorProduccion` (D-51 punto 2): sustituye la asociación de un sector (MD-77) y la de varios de la aplicación (MD-28). Reglas por tipo en D-51 |
| R076 + MD-77 | Capataz o Agrónomo, «registra» | Bitacora → responsable = 0..1 | `responsable`, FK nula a `core.Usuario`, `PROTECT` (una sola clave en lugar de las dos asociaciones; nulo = lo registró InfoPonia). Es la persona que hizo la operación |

Herencias: **hija directa de `OrigenDocumento`** (`contabilidad`, D-52; `TIPO_DE_ORIGEN = bitacora`). Es padre de `Consumo` y `Merma` (esta ronda) y de `AplicacionInsumos` y `FueraDeServicio` (PRD-03 y PRD-04).

### Restricciones de la base

- `tipo_evento` dentro de la lista. Índices `(invernadero, fecha_bitacora)` y `(lote, fecha_bitacora, hora_bitacora)`.
- La fecha de la bitácora **no puede ser posterior a hoy**.

---

## Consumo

Hijo de `Bitacora` (`tipo_evento = siembra` en esta ronda). Un consumo por cada reserva de insumo de la siembra que se consumió (cantidad consumida mayor que cero).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `MontoConsumo` | monto ≥ 0 | → `monto_consumo`. `cant_consumo × precio de referencia` del insumo en el invernadero **al concretar**; queda fijo aunque el precio cambie (regla 14 de 8.9). Redondeo `ROUND_HALF_UP` a 2 decimales |
| `cantConsumo` | cantidad > 0 | → `cant_consumo`. La cantidad consumida (reservada menos devuelta) |
| `fechaConsumo` | fecha | → `fecha_consumo`. La fecha efectiva de la siembra |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R045 | InsumoInvernadero, «corresponde» | Consumo → InsumoInvernadero = 1 | `insumo_invernadero`, FK a `inventario.InsumoInvernadero`, `PROTECT` |
| R105 | Siembra, «genera» | Consumo → Siembra = 0..1 | `siembra`, FK nula a `Siembra`, `PROTECT`. Esta ronda es siempre una siembra; los otros orígenes (mantenimiento, entrega y aplicación) los suman sus rondas con sus propias claves |
| R016 | MovimientoInsumo | Consumo → MovimientoInsumo = 1..* | Por `MovimientoInsumo.origen` (D-52): `consumo.movimientos_de_insumo`. El consumo **se crea antes** que sus movimientos |

Un consumo tiene **exactamente un origen** (regla 7 de 8.4): hoy, la siembra. Restricción `siembra_id IS NOT NULL` en PRD-01; **PRD-03 la reemplaza por «exactamente uno de `siembra` y `aplicacion`»** (D-51 punto 3). Un consumo de aplicación es una fila de bitácora de tipo interno `consumo`, que la consulta no lista.

### Sin tabla de enlace con el stock (D-52)

En el lote 4 existía `ConsumoMovimiento` (consumo, movimiento y lote). **Ya no existe**: `inventario.MovimientoInsumo` es un documento de origen y lleva `origen = consumo`; `inventario` no nombra al consumo, solo recibe su `origen_id` (`docs/api/stock.md`). El lote de plantas asociado (R040) se deriva. Un consumo se descuenta de uno o más lotes de insumo y cada uno genera su movimiento.

---|---|
| `consumo` | FK a `Consumo`, `PROTECT` |
| `movimiento` | `OneToOne` a `inventario.MovimientoInsumo`, `PROTECT` |
| `lote` | FK **nula** a `Lote` (de plantas), `PROTECT`: el lote de la siembra al que se asocia el movimiento (R040). Nula en los consumos de una aplicación (D-51 punto 3). En la siembra se crea el lote primero y después los movimientos |

Única `(consumo, movimiento)` (lo garantiza el `OneToOne` de `movimiento`).

---

## Merma

Hija de `Bitacora` (`tipo_evento = merma`). Plantas de un lote que se perdieron o se descartaron. La crea PRD-02 (de una transición) y la completa PRD-03.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `cantMerma` | entero > 0 | → `cant_merma` |
| `causa` | `Merma.Causa` | → `causa`. Obligatoria. La descripción libre va en `descripcion_evento` |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R082 (heredada) | Lote | 1 (en la merma de lote en pie) | La merma de un lote **siempre** tiene lote y etapa; la de una partida en cámara (fuera de la ronda) tiene el lote de origen |
| R089 | Alerta | Merma → Alerta = 0..* | Por `AlertaDeMerma` (A2) |

### `AlertaDeMerma` (tabla de enlace, A2)

Una alerta de las dos que puede disparar una merma (umbral y plantas comprometidas) se enlaza con su merma (`docs/api/alertas.md`, «Origen»): `merma` FK a `Merma`, `alerta` `OneToOne` a `maestros.Alerta`.

### Restricciones de la base

- `cant_merma > 0`. Una merma no deja a un lote con cantidad negativa: lo garantiza el servicio con el bloqueo del lote.

---

## AplicacionInsumos (lote 5, PRD-03)

Hija de `Bitacora` (`tipo_evento = aplicacion`). Uso de insumos sin una orden de trabajo (limpieza, nutrientes). Se registra cuando ocurre: no se planifica. MD-28 (decidido sin aplicar).

### Atributos y asociaciones

No tiene atributos propios: usa los de `Bitacora` (fecha y hora **actuales**, `descripcion_evento` opcional, `invernadero`, `responsable` el actor; sin lote ni etapa).

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| MD-28 | SectorProduccion, «se aplica en» | AplicacionInsumos → Sector = 0..* | Por `Bitacora.sectores`. Vacío = todo el invernadero (todos sus sectores activos). Los sectores son del invernadero y no están inactivos ni fuera de servicio (no se pueden elegir) |
| MD-28 | Consumo, «genera» | AplicacionInsumos → Consumo = 1..* | Por `Consumo.aplicacion` (cuarto origen, D-51 punto 3) |

### Lo que se calcula

- **Insumos que admite**: los de categorías con `consumo_directo` distinto de `no_admite`, activos y habilitados en el invernadero; cada insumo una vez por aplicación.
- **Destino del costo** (no se guarda): hay `ImputacionCosto` → «costo de los lotes»; no hay → «gasto». Si la categoría es «como costo de los lotes» pero en el alcance no hay lotes de plantas, va a gasto.

## ImputacionCosto

Clase de asociación entre `Consumo` y `Lote`. MD-28. Parte del costo de un consumo que recibe un lote de plantas.

| Campo | Valores | Nota |
|---|---|---|
| `consumo` | FK a `Consumo`, `PROTECT` | |
| `lote` | FK a `Lote`, `PROTECT` | |
| `monto_imputado` | monto ≥ 0, `DecimalField(14, 2)` | |

- Único `(consumo, lote)`. **La suma de las imputaciones de un consumo es exactamente su `monto_consumo`** (la verifica el servicio y la prueba de invariantes).
- Cada imputación suma su monto a `Lote.costo_acumulado`. Reparto y ejemplos: `docs/patrones/costo_del_lote.md`.

## FueraDeServicio (lote 5, PRD-04)

Hija de `Bitacora` (`tipo_evento = fuera_de_servicio`). Constancia de que un sector pasó a «fuera de servicio». MD-75.

| Atributo | Valores | Nota |
|---|---|---|
| `motivoFueraServicio` | texto obligatorio, hasta 300 caracteres | → `motivo_fuera_de_servicio` |
| `fechaEfectiva` | fecha | → `fecha_efectiva`. Desde cuándo; puede ser anterior a hoy. Es la `fecha_bitacora` del registro (la hora es la actual) |
| `fechaFin` | fecha, nula | → `fecha_fin`. Nula mientras el sector sigue fuera de servicio; se carga al volver a activarlo (`registrar_efecto_de_vuelta_a_servicio`) o al darlo de baja (`registrar_efecto_de_baja_de_sector`) |

El sector es **uno obligatorio** en `Bitacora.sectores`; el responsable es el Agrónomo. **A lo sumo un registro abierto** (`fecha_fin` nula) por sector: restricción de la base sobre una columna `sector` propia, ver abajo.

- Columna `sector`: FK a `maestros.SectorProduccion`, `PROTECT`, además de `Bitacora.sectores` (que lo contiene), para respaldar con `UniqueConstraint(fields=["sector"], condition=Q(fecha_fin__isnull=True))` que un sector no tenga dos registros abiertos.
- Restricción: `fecha_fin >= fecha_efectiva` cuando existe.

## Reubicacion (lote 5, PRD-04)

Hija de `Bitacora` (`tipo_evento = reubicacion`). Traslado de las plantas de un lote desde un sector que pasa a fuera de servicio hacia otros sectores del mismo tipo de etapa y del mismo invernadero. MD-76. Solo se origina en PROD-PNR-FDS.

Sin atributos propios. El lote es `Bitacora.lote` (obligatorio), el sector de origen es el único de `Bitacora.sectores`, la fecha es la efectiva y la hora la actual.

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| MD-76 | OcupacionSector, «genera», composición | Reubicacion → OcupacionSector = 1..* | Por `OcupacionSector.reubicacion` (D-51 punto 1). Las ocupaciones de destino nacen con `cant_agujeros_planificados = cant_agujeros_ocupados` y con el lote |

La ocupación de origen queda con 0 ocupados y conserva su lote. **No cambia la etapa del lote ni su fecha de entrada a la etapa.** La fecha de entrada se sigue calculando con la siembra o con la transición (regla 5 de 8.21), nunca con la reubicación.

## Cambios a las fichas del lote 4 por el lote 5

- `OcupacionSector`: `orden` pasa a **nula** y se suma `reubicacion` (clave nula a `Reubicacion`), con la restricción «exactamente una de las dos» (C9, MD-76). Único `(orden, sector)` pasa a `condition=Q(orden__isnull=False)` y se suma único `(reubicacion, sector)` con la condición contraria. «Agujeros comprometidos» sigue sumando solo ocupaciones de órdenes «a realizar». «Fecha en que el lote llegó al sector» = `fecha_siembra` de su siembra, `fecha_transicion` de su transición o `fecha_bitacora` de su reubicación.
- `Consumo`: cuarto origen (arriba). `ConsumoMovimiento` no existe (D-52).
- `Bitacora`: `sectores` y los tipos nuevos (arriba y D-51).
- `Merma`: sin cambios de columnas. Sus **sectores afectados** van en `Bitacora.sectores`; la cantidad perdida **por sector** va en la auditoría y en la descripción, y se refleja en las ocupaciones.

## Reglas del modelo que las tocan (resumen, con su número)

- **8.9, regla 13:** consumo de una reserva (consumido = máx(reservada, utilizada) − devuelta), monto = consumido × precio de referencia, fijo al concretar. **Regla 14:** el monto queda fijo. **Regla 15:** costo por planta (ver «Diferencias»).
- **8.13, 1 a 6:** lote de una siembra concretada; consumos; ocupaciones; agujeros comprometidos; cobertura de reservas; alerta «stock inconsistente».
- **8.20, 1 a 5:** origen y destino de una transición; fecha de entrada y máxima de cosecha; elección manual de la fecha; etapas del ciclo congeladas con lotes.
- **8.21, 1 a 5:** ocupaciones vigentes; ocupaciones de una transición; concreción de una transición; una transición «a realizar» por lote; fecha de entrada a la etapa actual.
- **8.22, 2 y 3:** el Agrónomo opera las órdenes de sus invernaderos; traspaso de las órdenes del Capataz saliente.

## Diferencias con el modelo y con los casos de uso

Manda el caso de uso (L7) salvo donde se diga otra cosa. Todas están también en `docs/temas_abiertos.md`.

| N.º | Tema | Modelo / CU | Se hace así |
|---|---|---|---|
| 1 | Costo por planta | Regla 15 de 8.9: Σ montos de consumo ÷ `cantidadInicial`. PROD-CNC-SMB y PROD-REG-MRM: costo acumulado ÷ cantidad actual, y la merma baja el costo acumulado (MD-79, «decidido sin aplicar») | Costo acumulado ÷ cantidad actual, con el costo acumulado guardado en el lote. La regla 15 queda desactualizada hasta aplicar MD-79 |
| 2 | Cantidad consumida | Regla 13 de 8.9: máx(reservada, utilizada) − devuelta; regla 24 de 8.8: devuelta propuesta máx(0, reservada − utilizada) | PROD-CNC-SMB: la utilizada nunca supera la reservada (13a), así que consumido = reservada − devuelta. Es el mismo valor |
| 3 | Dónde está el invernadero de una orden | R136 en `Siembra` (y R160 + R099 en la transición) | En el padre (D-50). **El Capataz no**: queda en cada hija (D-53) |
| 4 | Ocupación de una orden | Dos composiciones excluyentes (R140, R164) | Una clave `orden` (D-50) |
| 5 | Responsable de la bitácora | R076 (Capataz) y MD-77 (Agrónomo) | Una clave `responsable` a `core.Usuario` |
| 6 | Cantidad de plantines de la siembra | El prototipo sobrescribe la cantidad con lo sembrado | `cant_plantines_siembra` no cambia; la real es `Lote.cantidad_inicial` |
| 7 | Fecha del movimiento de insumo | MovimientoInsumo.fecha: «hora actual de la operación» | La fecha efectiva de la siembra con la hora actual (D-50, punto 7) |
| 8 | Alerta de plantas comprometidas, condición 1 | Reservas de cosecha activas que superan la cantidad actual | **Fuera de la ronda (D-45)**: no hay cosechas ni reservas de stock. Solo se evalúa la condición 2 |
| 9 | Prioridad | La sección 1.19 dice que siembra y transición no tienen prioridad | MD-73 («decidido sin aplicar»): es opcional; sin valor cuenta como media |
| 10 | Reparto del costo de una aplicación entre lotes | MD-28: proporcional a la `cantidadActual` de cada lote activo del alcance. PROD-REG-APL: proporcional a las plantas que cada lote tiene **en los sectores del alcance** | El caso de uso (D-51 punto 4) |
| 11 | Sectores de un registro de bitácora | MD-77: uno (0..1); MD-28: varios solo en la aplicación | Una relación muchos a muchos (D-51 punto 2) |
| 12 | Dónde queda el consumo de una aplicación | El consumo hereda de la bitácora, pero la consulta (PROD-CNS-BIT) no lista «consumos» | Fila de bitácora de tipo interno `consumo`, no listada (D-51 punto 3) |
| 13 | Fecha de la última activación de un sector | PROD-PNR-FDS la usa; `SectorProduccion` no la guarda | Se deriva de la auditoría y del `fecha_fin` del último «Fuera de servicio» (D-51 punto 6) |
| 14 | `OrigenDocumento` | D-45 y D-50 (lote 4): no se crea y el asiento usaría una referencia genérica | **Se crea en `contabilidad` y las hijas directas heredan** (D-52). Sin asientos |
| 15 | Código de la orden | D-50: `OT-{id}` | `OT-{numero}`, con una secuencia propia (D-52 punto 3): los `id` ahora se comparten entre documentos |
| 16 | Movimientos de un consumo | Tabla de enlace `ConsumoMovimiento` (lote 4) | `MovimientoInsumo.origen`; R040 derivado (D-52 puntos 5 y 6) |
| 17 | Motivo y fecha de una cancelación | El modelo (ronda 22) no tiene motivo de cancelación y define `fechaResolucionOrden` solo para la concreción; PROD-CNL-ORD (Propuesta 5) pide el atributo y que la fecha valga para los dos desenlaces | Como pide el CU: `motivo_cancelacion` (1 a 300, obligatorio al cancelar) y `fecha_resolucion_orden` también al cancelar. Pendiente de registrar en pendientes_MD (Drive) |

## Pendientes de MD que la afectan

| MD | Qué | Estado | Cómo se aplica acá |
|---|---|---|---|
| MD-73 | Prioridad opcional de siembra y transición | Decidido sin aplicar | Columna nula `prioridad_orden` |
| MD-77 | Agrónomo–Bitácora «registra» y sector en la bitácora | Decidido sin aplicar | `Bitacora.responsable` a `core.Usuario`; el sector lo suma PRD-03 |
| MD-78 | Causa «descarte por selección» | Decidido sin aplicar | En `Merma.Causa`; no suma a la merma acumulada |
| MD-79 | Costo del lote con promedio ponderado móvil | Decidido sin aplicar | `Lote.costo_acumulado` (`costo_del_lote.md`) |
| MD-28, MD-75, MD-76 | Decidido sin aplicar | `AplicacionInsumos`, `ImputacionCosto`, `FueraDeServicio` y `Reubicacion` (lote 5) |
| MD-49, 50, 53, 54 | Ocupaciones y fecha efectiva de la transición | Implementado (ronda 20) | Ya están en las fichas de arriba |
| MD-84, 85 | Lotes de insumo y faltante sin lote | Implementado (ronda 22) | `registrar_salida_por_consumo` y `proponer_lotes_fefo` de `inventario` |
| (sin número) | `OrdenTrabajo.motivoCancelacion` y fecha de resolución también al cancelar | Aprobado el 20/11/2026, sin ítem en pendientes_MD | Columna nula `motivo_cancelacion` con su restricción de la base (ver la ficha) |
