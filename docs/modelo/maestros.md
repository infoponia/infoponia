# Modelo de dominio · maestros

Copia para el repo de «Copia de modelo_dominio»: fichas de `Invernadero`, `Direccion`, `DireccionUrbana`,
`DireccionRural`, la geografía y `Alerta` (lote 0) y, de la ronda «Producción 1», de `TipoEtapa`, `SectorProduccion`, `Cultivo`,
`Variedad`, `Ciclo`, `EtapaProductiva` (columnas de MAE-03), `PerfilOrganizacion` y `ConfiguracionOperativa`, con las reglas que las tocan. Versión de la ronda 22, consultada el
18/11/2026.

Cotejado con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. **PROVISORIO.**

Si este archivo y Drive no coinciden, avisá: no elijas en silencio.

> **Importante.** Hay dos cardinalidades del modelo que los casos de uso ya contradicen y que una decisión del equipo
> resolvió, pero que todavía no se aplicaron al documento del modelo. Están marcadas abajo como «pendiente». **Manda el
> caso de uso**, porque la decisión ya está tomada (D-07: la ronda abierta rige aunque el diagrama no la refleje).

---

## Invernadero

Bloque: Producción, operaciones y trazabilidad. Vive en la app `maestros` (D-37).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idInvernadero` | — | En el código, el `id` automático (D-06) |
| `nombreInverdadero` | texto | **El modelo tiene un error de tipeo.** El nombre correcto es `nombre_invernadero` (D-05, que pide corregirlos y registrarlo) |
| `estadoInvernadero` | activo / inactivo | Baja lógica, regla 4 de 8.4 |

### Asociaciones

| ID | Con | Cardinalidad en el modelo | Estado |
|---|---|---|---|
| R051 | Agrónomo, «abarca» | Invernadero → Agrónomo = 1; Agrónomo → Invernadero = 0..* | **Pendiente (MD-87):** pasa a 0..1 del lado del invernadero. La regla 4 de PROD-ALT-INV ya dice 0..1 |
| R149 | Capataz, «abarca» | Invernadero → Capataz = 1; Capataz → Invernadero = 0..* | Ídem |
| R097 | Vendedor, «abarca» | Invernadero → Vendedor = 1; Vendedor → Invernadero = 0..* | Ídem |
| R134 | Técnico, «abarca» | Invernadero → Técnico = 1; Técnico → Invernadero = 0..* | Ídem |
| R096 | Dirección, «tiene» | Invernadero → Dirección = 1; Dirección → Invernadero = 0..1 | Vigente |
| R155 | Transportista, «pertenece» | Invernadero → Transportista = 0..*; Transportista → Invernadero = 1 | **Cambia (MD-138, D-55, 21/11/2026):** Transportista → Invernadero = **0..1**. Se asigna desde el invernadero (bloque «Logística», reglas 8 a 11 de PROD-MOD-INV), no desde la cuenta. En el código es la tabla `TransportistaInvernadero` (ver abajo) |
| R081 | Bitácora, «se realiza en» | Invernadero → Bitácora = 0..*; Bitácora → Invernadero = 1 | Vigente |
| R133 | DetallePedido, «recibe» | 0..* – 1 | Vigente |
| R136 | Siembra, «corresponde» | 0..* – 1 | Vigente |
| R151 | Compra-venta, «se retira en» | 0..* – 0..1 | Vigente |

**Composiciones** (el invernadero es el todo):

| ID | Con | Cardinalidad en el modelo | Estado |
|---|---|---|---|
| R098 | SectorProduccion, «contiene» | Invernadero → Sector = 1..*; Sector → Invernadero = 1 | **Pendiente (MD-74):** pasa a 0..*. La postcondición a de PROD-ALT-INV ya crea el invernadero sin sectores |
| R068 | SistemaIoT, «tiene» | Invernadero → SistemaIoT = 0..1; SistemaIoT → Invernadero = 1 | **Pendiente (MD-99):** el 0..1 se cuenta entre los sistemas **no dados de baja**: un invernadero puede tener un sistema nuevo después de dar de baja el anterior. La clave la declara `iot` (A2) y la restricción es única condicional |
| R099 | Lote, «tiene» | 0..* – 1 | Vigente |
| R131 | InsumoInvernadero, «tiene» | 0..* – 1 | Vigente |

Sin herencias.

**Eliminadas:** R041 (MovimientoInsumo–Invernadero) y R071 (Hardware–Invernadero): el invernadero se obtiene por otro
camino.

### `TransportistaInvernadero` (R155 en el código, D-55, MAE-05)

No es una clase del modelo de dominio: es cómo se guarda R155 en la base de datos. La declara `maestros` porque es la app de
nivel mayor (regla A2 de D-37).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | automático | D-06 |
| `transportista` | `OneToOneField("core.Transportista", on_delete=PROTECT, related_name="invernadero_asignado")` | El 0..1 lo garantiza la base de datos (único) |
| `invernadero` | `ForeignKey(Invernadero, on_delete=PROTECT, related_name="transportistas_asignados")` | Con índice (la FK lo trae) |
| `desde` | `DateTimeField` | Cuándo empezó a trabajar para este invernadero: se fija al agregar y al trasladar |

- Para agregar, se crea la fila. Para trasladar, se cambian `invernadero` y `desde`. Para quitar, se borra la fila. El
  historial queda en la auditoría.
- La fila **no** se borra cuando se da de baja la cuenta del Transportista: queda como historial (regla 3 de PROD-BAJ-INV). Un
  Transportista inactivo con fila no impide la baja del invernadero.

### Reglas que lo tocan

- **Regla nueva (MD-87):** el nombre del invernadero es único, sin distinguir mayúsculas de minúsculas. Es la regla 1
  de PROD-ALT-INV.
- **Regla 3 de 8.22 (MD-87):** la alerta de personal faltante se genera también cuando el rol nunca se asignó, no solo
  cuando el asignado pasa a inactivo. La del Técnico, solo si el invernadero tiene `SistemaIoT` (R068).
- **Regla 4 de 8.4, reescrita (MD-87):** la baja se bloquea si el invernadero tiene lotes activos, órdenes a realizar,
  partidas de `StockCosechado` con cantidad disponible, algún `InsumoInvernadero` con stock distinto de 0, cantidad en
  tránsito u orden de compra aprobada sin recibir, transportistas vinculados (R155; **solo los activos**, D-39 y regla 3 de PROD-BAJ-INV) o un
  `SistemaIoT` activo. Son las precondiciones c a h de PROD-BAJ-INV.
- **Reglas de 8.22 (MD-60):** cuando el Agrónomo, el Capataz, el Vendedor o el Técnico de un invernadero pasa a
  inactivo, el invernadero lo conserva hasta que el Gerente asigna a otro al modificarlo. Mientras tanto queda para el
  Gerente la alerta «invernadero sin {rol} activo», que se resuelve al asignar al nuevo. Al asignarlo, pasan a él, en
  ese invernadero: las órdenes a realizar del Capataz saliente, los mantenimientos del Técnico saliente, los contratos
  vigentes o abiertos del Vendedor saliente y las alertas activas del Agrónomo saliente. Lo concretado, lo cancelado y
  los registros históricos conservan a quien los hizo.
- **Regla de 8.22 (MD-60), ámbito del Agrónomo:** opera sobre las órdenes de los invernaderos a su cargo (R051),
  cualquiera sea quien las planificó. Un Agrónomo recién asignado las ve y las gestiona como si las hubiera
  planificado él.
- **Regla 4 de 8.22, reescrita (MD-98, «decidido sin aplicar» el 19/11/2026; reemplaza a MD-61):** el IoT se opera por invernadero (R068): cada
  consulta y cada acción es sobre un invernadero elegido, nunca sobre todos a la vez. **El Agrónomo opera el IoT de los invernaderos activos a su
  cargo (R051)**: telemetría, alertas, umbrales, reglas de actuación, comandos y mantenimientos técnicos. **El Gerente lo opera solo en los
  invernaderos sin Agrónomo activo, hasta que se asigne uno, y consulta todos.** Excepción: los tipos de actuador (que son de toda la
  organización) los administra solo el Gerente. Las alertas de un invernadero van a su Agrónomo (R049) y, mientras no tenga un Agrónomo activo, al
  Gerente activo (R007). Un comando emitido por el Gerente no lleva Agrónomo (R050 en 0..1). La regla 3 de 8.22 es la específica de los cuatro
  tipos «invernadero sin {rol} activo», que van al Gerente aunque haya Agrónomo (D11 de MAE-02). **El texto de MD-61 que estaba acá («El Gerente puede
  hacer lo mismo en cualquier invernadero») queda reemplazado por esta versión.**
  Fuente: pendientes_MD, MD-98 (Drive).

---

## Dirección

`Direccion` es abstracta, con dos hijas. Bloque: Gestión comercial. Vive en `maestros` (D-37).

### Direccion (abstracta)

| Atributo | Valores |
|---|---|
| `estadoDireccion` | activo / inactivo |

| ID | Con | Cardinalidad |
|---|---|---|
| R096 | Invernadero, «tiene» | Dirección → Invernadero = 0..1; Invernadero → Dirección = 1 |
| R119 | Cliente, «tiene» | Dirección → Cliente = 0..1; Cliente → Dirección = 1..* |
| R125 | DetalleSuministro, «tiene» | 0..* – 1 |
| R146 | Compra-venta, «se envía a» | 0..* – 0..1 |

Es parte de `Localidad` (R110, composición): Dirección → Localidad = 1; Localidad → Dirección = 1..*.
**Pendiente (MD-88):** R110 deja de ser composición y Localidad → Dirección pasa a 0..*, porque una localidad
precargada puede no tener ninguna dirección.

**Restricción C6:** cada dirección pertenece exactamente a un invernadero (R096) o a un cliente (R119), nunca a las dos
cosas ni a ninguna ({xor}).

**Regla 3 de 8.18:** una dirección que usa una compra-venta o un detalle de suministro no se modifica ni se elimina:
para cambiar el domicilio se registra una dirección nueva y la anterior pasa a inactiva, conservando sus asociaciones.
Para el invernadero esto todavía no aplica, porque esas clases no existen.

### DireccionUrbana

Hereda de `Direccion`. Atributos: `calle`, `numeroCalle`, `piso`, `departamento`, `barrio`, `referencias`.
Obligatorios: calle y número (regla 2 de PROD-ALT-INV).

### DireccionRural

Hereda de `Direccion`. Atributos: `ruta`, `kilometro`, `lote`. Obligatorios: ruta y kilómetro.

---

## Geografía: Provincia, Departamento y Localidad

| ID | Con | Cardinalidad | Tipo |
|---|---|---|---|
| R108 | Provincia → Departamento | 1..* – 1 | Composición |
| R109 | Departamento → Localidad | 1..* – 1 | Composición |
| R110 | Localidad → Dirección | 1..* – 1 | Composición (ver MD-88 arriba) |

**MD-88 (decidido sin aplicar):** las tres se precargan desde el servicio Georef del Estado argentino, a nivel de
localidad y no de asentamiento, y **no tienen ABM**. Es la regla 3 de PROD-ALT-INV: se eligen de listas encadenadas y
no se escriben ni se crean.

---

## Alerta

Bloque: Mantenimiento, alertas y auditoría. Vive en `maestros` (D-38, que corrige a D-37).

Aviso de un hecho que requiere atención y que sigue activo hasta que ese hecho se resuelve. Se distingue de una
notificación, que es solo informativa (glosario, «Alerta»). **Las notificaciones no se modelan** (D-38).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idAlerta` | — | El `id` automático (D-06) |
| `fechaAlerta` y `horaAlerta` | — | En el diagrama son dos; en el código conviene una sola marca de tiempo, como `RegistroAuditoria.fecha_hora` |
| `tipoAlerta` | lista abierta, ver abajo | Indica también el origen y el destinatario |
| `descripcionAlerta` | texto | |
| `nivelSeveridad` | crítica / advertencia / informativa | MD-109 (decidido sin aplicar, 19/11/2026): lo fija el tipo de alerta y se guarda con la alerta. No es la prioridad de una orden de trabajo (`prioridadOrden`) |
| `estadoAlerta` | activa / resuelta | Precisado en la 17ª ronda |
| `fechaResolucion` | — | |
| `estadoLecturaAlerta` | no leída / leída | Precisado en la 17ª ronda. Ver regla 7 de 8.18, más abajo |

### Valores de `tipoAlerta` registrados hasta la ronda 22

- invernadero sin Agrónomo activo / sin Capataz activo / sin Vendedor activo / sin Técnico activo (regla 3 de 8.22);
- stock inconsistente (regla 6 de 8.13; antes «inconsistencia de stock de insumo»);
- insumo por vencer / insumo vencido (regla 5 de 8.23); insumo bajo el mínimo (regla 11 de 8.15);
- entrega no reconocida por el cliente (regla 7 de 8.15);
- recepción con inconvenientes (citado en «CU extendidos», pendiente de registrar en el modelo);
- umbral de merma superado, reservas sin cobertura y merma en cámara con producto reservado (regla 2 de 8.9);
- además de los tipos que definan las demás reglas.

Es una lista que crece con cada módulo: cada tarea que genere una alerta nueva agrega su tipo.

### Asociaciones

**Destinatarios.** Toda alerta tiene al menos uno, según su `tipoAlerta` (regla 1 de 8.9):

| ID | Con | Cardinalidad |
|---|---|---|
| R007 | Gerente, «recibe» | Alerta → Gerente = 0..1; Gerente → Alerta = 0..* |
| R049 | Agrónomo, «recibe» | Alerta → Agrónomo = 0..1; Agrónomo → Alerta = 0..* |

**Origen.** A lo sumo uno, indicado por `tipoAlerta` (restricción C5). Hay alertas sin ninguno, como la de insumo bajo
el mínimo; por eso no es un {xor}. Todos estos orígenes están en apps de nivel mayor, así que los declara cada una
cuando exista (D-38):

| ID | Con | Cardinalidad | App |
|---|---|---|---|
| R052 | Hardware, «emite» | Alerta → Hardware = 0..1; Hardware → Alerta = 0..* | `iot` |
| R053 | Telemetría, «emite» | 0..1 – 0..1 | `iot` |
| R054 | SolicitudRevisión, «emite» | Alerta → SolicitudRevisión = 0..1; SolicitudRevisión → Alerta = 1 | `comercial` |
| R089 | Merma, «se asocia» | Alerta → Merma = 0..1; Merma → Alerta = 0..* | `produccion` |

**Consecuencia y registro:**

| ID | Con | Cardinalidad | Nota |
|---|---|---|---|
| R048 | MantenimientoTécnico, «genera» | 0..1 – 0..1 | Solo una alerta por comando fallido, agotados los reintentos, genera un mantenimiento |
| R055 | Bitácora, «genera» | 0..1 – 0..1 | No toda alerta genera un registro de bitácora |

Sin herencias ni composiciones. **El modelo no tiene una asociación Alerta–Invernadero**, pero el invernadero aparece
en los cuatro tipos «invernadero sin {rol} activo», en la ficha del invernadero y en su baja (postcondición e de
PROD-BAJ-INV). Es lo que fundamenta D-38 y lo que MAE-02 tiene que resolver; conviene anotarlo en pendientes_MD.

### Reglas

**C5.** A lo sumo una de R052, R053, R054 o R089.

**Regla 1 de 8.9.** Toda alerta tiene al menos un destinatario, el Gerente (R007) o el Agrónomo (R049), según su
`tipoAlerta`. Otros roles, como el Vendedor, reciben notificaciones del módulo de notificaciones, no alertas.

**Regla 2 de 8.9.** Alertas que puede disparar una merma: la de umbral (regla 9 de 8.9), al Agrónomo y al Gerente; la
de reservas sin cobertura o transición planificada (regla 15 de 8.8), al Agrónomo; y la de merma en cámara con producto
reservado (regla 8 de 8.9), al Agrónomo, con notificación al Vendedor. Una misma merma puede disparar más de una.

**Regla 7 de 8.18.** «`estadoAlerta` nace activa y pasa a resuelta cuando se resuelve el hecho que la originó; en ese momento se
carga `fechaResolucion`. No hay otros valores. `estadoLecturaAlerta` nace no leída y pasa a leída cuando uno de sus destinatarios
la abre. Los dos estados son independientes: una alerta puede estar leída y seguir activa». (Texto copiado el 19/11/2026.)

**Resolución automática.** Varias alertas se resuelven solas cuando desaparece el hecho que las originó:
«stock inconsistente» cuando el stock vuelve a cubrir las reservas (MD-85); «insumo vencido» e «insumo por vencer»
cuando la cantidad disponible del lote llega a cero, con a lo sumo una activa por lote y por tipo (MD-96);
«invernadero sin {rol} activo» al asignar a alguien (regla 3 de 8.22).

---

## Tipo de etapa

Bloque: Producción, operaciones y trazabilidad. Vive en `maestros` (D-37). **Catálogo fijo de cinco tipos**, cargado por
migración (MD-52): no tiene alta, modificación ni baja, y sus nombres no se cambian (de ellos dependen reglas del modelo, como
«Maduración» en las reglas 2 y 3 de 8.20).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idTipo` | — | El `id` automático (D-06) |
| `codigo` | texto único: `germinacion`, `crecimiento`, `floracion`, `fructificacion`, `maduracion` | **No está en el modelo.** Identificador estable para el código y las pruebas, para no depender del nombre visible |
| `nombreEtapa` | Germinación, Crecimiento, Floración, Fructificación, Maduración | → `nombre_etapa` |
| `puestoGlobal` | 1 a 5, en ese orden | Orden de las etapas en cualquier ciclo (regla 1 de 8.20). → `puesto_global` |
| `perfilExclusivo` | **reemplazado por `perfilesPermitidos` (MD-52, decidido sin aplicar)**: lista con los valores de `Variedad.perfilFamilia` | → `perfiles_permitidos` (lista JSON). «Permitida» no es «obligatoria» |

Valores cargados por la migración (MD-52):

| `codigo` | `puesto_global` | `perfiles_permitidos` | En el ciclo de una variedad |
|---|---|---|---|
| `germinacion` | 1 | los seis perfiles | obligatoria |
| `crecimiento` | 2 | los seis perfiles | optativa |
| `floracion` | 3 | Frutos grandes, Frutos pequeños, Flores | optativa |
| `fructificacion` | 4 | Frutos grandes, Frutos pequeños | optativa |
| `maduracion` | 5 | los seis perfiles | obligatoria |

Los seis perfiles son: Hoja verde, Pastura, Frutos grandes, Frutos pequeños, Flores, Hierbas (lista fija en código, confirmada
el 19/11/2026). Cada tipo conserva su color fijo en la interfaz (`--e-ger`, `--e-cre`, `--e-flo`, `--e-fru`, `--e-mad` del
prototipo), que se elige por `codigo`.

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R092 | SectorProduccion, «tiene» | TipoEtapa → Sector = 0..*; Sector → TipoEtapa = 1 | Vigente (corregida en la 19ª ronda). Clave foránea en `SectorProduccion` |
| R093 | EtapaProductiva, «tiene», composición | TipoEtapa → Etapa = 1..*; Etapa → TipoEtapa = 1 | Vigente. Clave foránea en `EtapaProductiva` |

La regla «Germinación y Maduración son obligatorias en el ciclo de toda variedad» (MD-52) se valida al guardar el ciclo de una
variedad: es de INV-03.

---

## SectorProduccion

Bloque: Producción, operaciones y trazabilidad. Vive en `maestros` (D-37). Es parte del invernadero (R098, composición).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idSector` | — | El `id` automático |
| `nombreSector` | texto, único por invernadero sin distinguir mayúsculas, ni espacios al borde; se cuentan también los inactivos | → `nombre_sector`. Regla 2 de PROD-ALT-SCT |
| `cantAgujerosTotal` | entero mayor que 0 | → `cant_agujeros_total`. Cada planta ocupa un agujero, en todas las etapas (MD-68) |
| `estadoSector` | **activo / fuera de servicio / inactivo** | → `estado_sector`. MD-74 (decidido sin aplicar) amplía los dos valores del modelo. «Fuera de servicio» conserva su capacidad pero no recibe plantas ni órdenes; «inactivo» es la baja lógica (MD-66). Manda el caso de uso |
| `cantAgujerosComprometidos` | **derivado** (MD-74) | No se guarda: suma de `cantAgujerosPlanificados` de las ocupaciones cuya orden (siembra o transición) está a realizar (regla 4 de 8.13). Lo calcula `produccion` (PRD-01) y `maestros` lo pide con `agujeros_de` |
| `cantAgujerosDisponible` | **derivado** (MD-74) | No se guarda: total − ocupados − comprometidos. El modelo lo lista como atributo y el caso de uso (regla 5 de PROD-ALT-SCT) dice que se calcula: **manda el caso de uso** |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R098 | Invernadero, «contiene», composición | Sector → Invernadero = 1; Invernadero → Sector = **1..*** | **Pendiente (MD-74):** pasa a 0..*. PROD-ALT-INV ya crea el invernadero sin sectores. Clave foránea `invernadero`, protegida, en `SectorProduccion` |
| R092 | TipoEtapa, «tiene» | Sector → TipoEtapa = 1; TipoEtapa → Sector = 0..* | Vigente. Clave foránea `tipo_etapa`, protegida |
| R095 | OcupacionSector, «corresponde» | Sector → Ocupación = 0..*; Ocupación → Sector = 1 | La FK la crea `produccion` (A2). No existe en MAE-03 |
| R070 | Hardware, «funciona» | Sector → Hardware = 0..*; Hardware → Sector = 0..1 | La FK la crea `iot` (A2). No existe en MAE-03 |

R079 (Capataz–Sector) se eliminó en la 7ª ronda: el Capataz de un sector es el de su invernadero. R042 (DepósitoNutrientes–Sector)
se elimina por MD-83.

### Reglas que lo tocan

- **MD-66 (baja):** un sector no pasa a inactivo si tiene agujeros comprometidos, ocupaciones con agujeros ocupados o hardware
  activo. Pasar a «fuera de servicio» no lo exige (lo resuelve PROD-PNR-FDS en el mismo acto, MD-75).
- **MD-68 (capacidad, para la siembra):** los sectores fuera de servicio cuentan para los niveles 1 y 2 de la capacidad; los
  inactivos no. No se eligen al planificar.
- **MD-74 (modificación):** el nombre siempre; la cantidad sube siempre y baja hasta ocupados + comprometidos; el tipo solo sin
  ocupados ni comprometidos; el invernadero, nunca. Un sector fuera de servicio se puede modificar y sigue fuera de servicio.
- **Restricciones de la base (D-36 y D-30):** único `(invernadero, lower(nombre_sector))`; `cant_agujeros_total > 0`;
  `estado_sector` en los tres valores.

---

## Cultivo

Bloque: Producción, operaciones y trazabilidad. Vive en `maestros` (D-37). No pertenece a un invernadero: lo comparten todos.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idCultivo` | — | El `id` automático |
| `nombreCultivo` | texto de hasta 40 caracteres (límite de esta ronda), único entre todos los cultivos sin distinguir mayúsculas ni espacios al borde | → `nombre_cultivo`. Regla 2 de PROD-ALT-CLT |
| `estadoCultivo` | activo / inactivo | → `estado_cultivo`. **Nuevo por MD-71 (decidido sin aplicar)**: revierte la parte de MD-20 que lo dejó sin estado |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R074 | Variedad, «tiene», composición | Cultivo → Variedad = 1..*; Variedad → Cultivo = 1 | **Pendiente (MD-71):** Cultivo → Variedad pasa a 0..*, porque se da de alta antes que su primera variedad. Clave foránea `cultivo` en `Variedad` |

### Reglas que lo tocan

- **MD-71:** un cultivo pasa a inactivo solo si no tiene variedades activas; la baja no es en cascada; para reactivar una
  variedad su cultivo tiene que estar activo. Al renombrar un cultivo cambia el nombre de las semillas de sus variedades (MD-72).
- Restricción de la base: único `lower(nombre_cultivo)` (el servicio guarda el nombre recortado).

---

## Variedad, Ciclo y EtapaProductiva

Bloque: Producción, operaciones y trazabilidad. Viven en `maestros` (D-37). **Se crean en dos tiempos:** MAE-03 crea las tres tablas con
las columnas mínimas que sus reglas necesitan (contar variedades activas de un cultivo, calcular qué variedades dejan de poder sembrarse
al cambiar el tipo de un sector); **INV-03 agrega el resto de `Variedad` con una migración propia en `maestros`** y es dueña de sus casos
de uso (los servicios están en `inventario`, D-49). `Variedad` no tiene `densidad` (MD-69).

### Variedad

| Atributo | Valores | Creada por | Nota |
|---|---|---|---|
| `idVariedad` | — | MAE-03 | El `id` automático |
| `nombreVariedad` | texto de hasta **50** caracteres (límite de esta ronda), único dentro de su cultivo sin distinguir mayúsculas ni espacios al borde, **bajas incluidas** | MAE-03 (la restricción única la agrega INV-03) | → `nombre_variedad`. Regla 2 de PROD-ALT-VAR. Dos cultivos pueden repetir un nombre |
| `perfilFamilia` | Hoja verde / Pastura / Frutos grandes / Frutos pequeños / Flores / Hierbas | MAE-03 | → `perfil_familia` (lista fija en código) |
| `estadoVariedad` | activo / inactivo | MAE-03 | → `estado_variedad`. El ciclo sigue el estado de su variedad (19ª ronda: se eliminó `estadoCiclo`) |
| `cultivo` | FK (R074) | MAE-03 | Protegida |
| `tempAmbienteMin`, `tempAmbienteMax` | decimal, °C | INV-03 | → `temp_ambiente_min`, `temp_ambiente_max`. `DecimalField(max_digits=7, decimal_places=2)`. Mínimo ≤ máximo (regla 6 de PROD-ALT-VAR) |
| `humedadMin`, `humedadMax` | decimal, % | INV-03 | → `humedad_min`, `humedad_max`. Igual que arriba |
| `intensidadLuzMin`, `intensidadLuzMax` | decimal, lux | INV-03 | → `intensidad_luz_min`, `intensidad_luz_max`. Igual que arriba |
| `fotoperiodoMin`, `fotoperiodoMax` | decimal, h/día | INV-03 | → `fotoperiodo_min`, `fotoperiodo_max`. Igual que arriba |
| `duracionPostCosecha` | entero de 1 a 60, días | INV-03 | → `duracion_post_cosecha`. Días de aptitud comercial del producto cosechado (regla 7 de PROD-ALT-VAR); la usan `StockCosechado.fechaLimite` y la validación de la cosecha (rondas futuras) |
| `pesoPromedioPlanta` | entero mayor que 0, **gramos** | INV-03 | → `peso_promedio_planta`. **MD-69:** el modelo dice kilogramos; el glosario y el caso de uso dicen gramos y mandan. Verifica la capacidad de carga del vehículo (regla 6 de 8.12, ronda futura) |

Restricciones de la base que agrega INV-03: único `(cultivo, lower(nombre_variedad))`; `*_min <= *_max` en los cuatro rangos;
`duracion_post_cosecha` entre 1 y 60; `peso_promedio_planta > 0`; `perfil_familia` y `estado_variedad` en sus dominios. Además (aprobado el 19/11/2026, D-49; los CU no lo piden): `humedad_min` y `humedad_max` entre 0 y 100, y
`fotoperiodo_min` y `fotoperiodo_max` entre 0 y 24. Temperatura e intensidad lumínica no tienen tope.

Asociaciones: R074 (con `Cultivo`), R091 (con `Ciclo`, uno a uno), R137 (con `Semilla`, uno a uno; la FK está en `Semilla`, `inventario`,
A2) y las de `produccion` y `comercial`: R104 (`Siembra`), R126 y R127 (detalles de suministro y de venta). Las de `produccion` y
`comercial` las declaran esas apps cuando existan.

### Ciclo

| Atributo | Valores | Nota |
|---|---|---|
| `idCiclo` | — | El `id` automático |
| `duracionCicloCompleto` | **derivado** (MD-70, aplicado) | No se guarda: suma de `duracion_estimada_dias` de sus etapas (`inventario.servicios.variedades.duracion_del_ciclo`) |
| `variedad` | FK uno a uno (R091, composición) | Protegida. Cada variedad tiene un único ciclo, exclusivo de ella, que se crea junto con la variedad |

### EtapaProductiva

| Atributo | Valores | Nota |
|---|---|---|
| `idEtapa` | — | El `id` automático |
| `ciclo` | FK (R090, composición) | Protegida |
| `tipo_etapa` | FK (R093) | Protegida. Una variedad no repite un tipo en su ciclo (restricción única `(ciclo, tipo_etapa)`) |
| `duracionEstimadaDias` | entero mayor que 0 | → `duracion_estimada_dias`. Restricción de la base `> 0` |
| `descripcionEtapa` | texto, opcional | → `descripcion_etapa`. **Ningún caso de uso la pide: INV-03 no la muestra ni la escribe** (queda vacía) |
| `estadoEtapa` | **no se crea** (decidido el 19/11/2026, opción A) | El ciclo y sus etapas siguen el estado de su variedad (19ª ronda); la etapa no tiene estado propio |

Reglas del ciclo (las valida el servicio de INV-03, no la base): Germinación y Maduración están siempre; Crecimiento, Floración y
Fructificación son optativas y solo se ofrecen las que permite el perfil de la variedad (`TipoEtapa.perfiles_permitidos`); las etapas
siguen el orden de `puesto_global`; con lotes, las etapas no se agregan ni se quitan (regla 5 de 8.20: el origen de las transiciones se
deduce de su orden). La cosecha estimada llega al entrar en Maduración, a la suma de las etapas anteriores.

El modelo de dominio dice que hereda de `OrigenDocumento`; **no se implementa** (una etapa es configuración, no un documento; D-52 punto 7, posible error del modelo). Las asociaciones con `Lote` (R100),
`Bitacora` (R106) y `TransicionEtapa` (R107) las crea `produccion` (A2).

---

## PerfilOrganizacion

Bloque: Administración general. Estereotipo «Singleton». Vive en `maestros` (D-37, con D-48 para el encabezado). Una sola
fila, creada por migración con el nombre inicial `NOMBRE_ORGANIZACION` (MD-89): no tiene alta ni baja.

| Atributo | Valores | Nota |
|---|---|---|
| `singleton` | siempre 1, único | **No está en el modelo.** Garantiza una sola fila desde la base |
| `nombreOrganizacion` | texto obligatorio, hasta 120 | → `nombre_organizacion` |
| `cuitOrganizacion` | opcional; 11 dígitos con dígito verificador, se guarda sin guiones | → `cuit_organizacion`. Se acepta con o sin guiones (regla 3 de ADM-MOD-ORG) |
| `telefonoOrganizacion` | opcional; formato de D-21 (8 a 15 dígitos, espacios y `+ - ( )`) | → `telefono_organizacion` |
| `emailOrganizacion` | opcional; formato de email | → `email_organizacion` |
| `direccionOrganizacion` | opcional, texto hasta 200 | → `direccion_organizacion`. Es texto libre, no una `Direccion` de Georef |
| `logo` | — | ~~Fuera de la ronda (D-45).~~ **Hecho en USR-07 (27/11/2026, D-106):** imagen opcional, WebP de 512 px de lado mayor como máximo, sin recortar y con transparencia, en `logos/<uuid4>.webp`, en R2 (disco en desarrollo) → `logo` |
| `colorPrimario`, `colorSecundario`, `colorTerciario`, `colorCuaternario` | opcionales; `#RRGGBB` | MD-93. → `color_primario`… `color_cuaternario` (los nombres del 3.º y 4.º, a confirmar en el modelo). Se cargan en orden (regla 5). Formato precisado por D-48 |

Sin asociaciones. El cálculo del CUIT (módulo 11 con pesos 5,4,3,2,7,6,5,4,3,2) es el de `cuitOk` del prototipo.

---

## ConfiguracionOperativa

Bloque: Administración general. Estereotipo «Singleton». Vive en `maestros` (D-37). Una sola fila, creada por migración con los
valores iniciales (MD-89): no tiene alta ni baja. R001 (Gerente «establece») **no se guarda**: hay un solo Gerente activo y la
auditoría registra quién modificó (D-36).

| Atributo (en código) | Dominio | Inicial | Grupo en la pantalla |
|---|---|---|---|
| `singleton` | siempre 1, único | 1 | — (no está en el modelo) |
| `porc_merma_maxima` | entero de 1 a 100 | 15 | Producción |
| `dias_horizonte_cosecha` | entero ≥ 1 | 30 | Producción |
| `dias_aviso_vencimiento` | entero ≥ 1 | 15 | Insumos |
| `dias_pre_reserva_suministro` | entero ≥ 1 | 14 | Comercial |
| `dias_anticipacion_cosecha_compra_venta` | entero ≥ 0 | 1 | Comercial |
| `dias_anticipacion_cosecha_suministro` | entero ≥ 0 y ≤ `dias_pre_reserva_suministro` | 3 | Comercial |
| `dias_vigencia_enlace_confirmacion` | entero ≥ 1 | 3 | Comercial |
| `dias_vigencia_enlace_faltante` | entero ≥ 1 | 2 | Comercial (**el prototipo no lo muestra**; se agrega) |
| `dias_aviso_vencimiento_camara` (COM-04, MD-134) | entero ≥ 0 (0 desactiva el aviso) | 3 | Comercial («Aviso de vencimiento de cámara», `VIEWS.cfg` del prototipo comercial). Migración propia en `maestros` (COM-04), con el valor inicial para la fila existente |
| `dias_limite_cotizacion` | entero ≥ 1 | 3 | Compras |
| `dias_validez_cotizacion` | entero > 0 | 7 | Compras |
| `porc_tolerancia_cobertura_pedido` | entero de 0 a 100 | 0 | Compras |
| `porc_margen_pedido_automatico` (CMP-07, D-104) | entero de 0 a 100 | 20 | Compras. Migración `maestros` 0013 (`AddField` con su CHECK); con 0 el pedido automático pide justo lo que falta |
| `cant_maxima_entregas_diarias` | entero ≥ 1 | 10 | Entregas |
| `cant_max_ciudades_distintas_diarias` | entero ≥ 1 | 3 | Entregas |

Nombres en el modelo: `porcMermaMaxima`, `diasHorizonteCosecha`, `diasAvisoVencimiento`, `díasPreReservaSuministro`,
`diasAnticipacionCosechaCompraVenta`, `diasAnticipacionCosechaSuministro`, `diasVigenciaEnlaceConfirmacion`,
`diasVigenciaEnlaceFaltante` (nombre provisional), `diasLimiteCotizacion`, `diasValidezCotizacion` (nombre provisional),
`porcToleranciaCoberturaPedido`, `cantMaximaEntregasDiarias`, `cantMaxCiudadesDistintasDiarias`, `diasAvisoVencimientoCamara` (MD-134, decidido sin aplicar). `idConfiguracion` es el `id`.
Los 14 parámetros de IoT (MD-112) los suma IOT-01 con una migración propia en `maestros`, no MAE-04: dominios, valores iniciales y nombres en `docs/modelo/iot.md`, «Parámetros IoT de ConfiguracionOperativa». Grupo en la pantalla: «Módulo IoT» (IOT-04). Valores iniciales de la ronda 22 (MD-89 y MD-93); dos
están «a confirmar con el Jardín Botánico» (7 días de validez de la cotización y 2 de vigencia del enlace de faltante).

---

## Pendientes de pendientes_MD que tocan a este extracto

| ID | Estado | Qué falta |
|---|---|---|
| MD-74 | Decidido sin aplicar (15/11/2026) | R098 pasa a 0..*: un invernadero se da de alta sin sectores |
| MD-52 | Decidido sin aplicar (15/11/2026) | `perfilExclusivo` → `perfilesPermitidos` (lista); catálogo fijo de cinco tipos; Germinación y Maduración obligatorias. **Aplicado en esta ficha** |
| MD-66, MD-68 | Decidido sin aplicar (15/11/2026) | Condiciones de la baja de un sector y capacidad para la siembra. **Aplicadas en la ficha de `SectorProduccion`** |
| MD-69 | Decidido sin aplicar (15/11/2026) | `Variedad.densidad` se elimina; `pesoPromedioPlanta` en gramos. **Aplicado en la ficha** (lote 3) |
| MD-70 | Decidido sin aplicar (15/11/2026) | `Ciclo.duracionCicloCompleto` derivado. **Aplicado** |
| MD-71 | Decidido sin aplicar (15/11/2026) | `Cultivo.estadoCultivo`; R074 a 0..*. **Aplicado en la ficha de `Cultivo`** |
| MD-74 (resto) | Decidido sin aplicar (15/11/2026) | Estados activo / fuera de servicio / inactivo y agujeros comprometidos y disponibles derivados. **Aplicado en la ficha de `SectorProduccion`** |
| MD-89, MD-93 | Decidido sin aplicar / aplicado en parte | Singletons sin alta ni baja; cuatro colores y valores iniciales. **Aplicados en las fichas de `PerfilOrganizacion` y `ConfiguracionOperativa`** |
| MD-85 | Decidido sin aplicar | «Stock inconsistente»: nombre y definición dinámica |
| MD-87 | Decidido sin aplicar (15/11/2026) | Personal opcional del invernadero (R051, R097, R134 y R149 a 0..1); nombre único sin distinguir mayúsculas; regla 4 de 8.4 reescrita |
| MD-88 | Decidido sin aplicar (15/11/2026) | Geografía precargada de Georef, sin ABM; R110 deja de ser composición |
| MD-96 | Aplicado en parte (glosario) | Precisiones de «insumo por vencer» e «insumo vencido» |
| MD-109 | Decidido sin aplicar (19/11/2026) | `nivelSeveridad` se conserva con tres valores, crítica, advertencia e informativa, fijados por el tipo de alerta (los del repo, MAE-02a, D-41); reemplaza a la propuesta de eliminarlo y a la «prioridad» alta / media / baja |
| Sin ID (MAE-02a) | Propuesto | R007 (Gerente «recibe» Alerta) se guarda como el booleano `para_gerente` y no como FK: hay a lo sumo un Gerente activo (D-09) y el Gerente nuevo tiene que ver lo pendiente (D-14). R049 sigue como FK al Agrónomo |
| Sin ID (MAE-02a) | Propuesto | Asociación Alerta–Invernadero (`Alerta.invernadero`, FK): el modelo no la tiene (D-38) |

MD-87 y MD-88 son los que más pesan en MAE-01: sin ellos, el modelo exige personal y sectores que los casos de uso ya
dejan opcionales.
