# Modelo de dominio · maestros

Copia para el repo de «Copia de modelo_dominio»: fichas de `Invernadero`, `Direccion`, `DireccionUrbana`,
`DireccionRural`, la geografía y `Alerta`, con las reglas que las tocan. Versión de la ronda 22, consultada el
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
| R155 | Transportista, «pertenece» | Invernadero → Transportista = 0..*; Transportista → Invernadero = 1 | Vigente. Se asigna desde la cuenta del Transportista (regla 6 de PROD-ALT-INV) |
| R081 | Bitácora, «se realiza en» | Invernadero → Bitácora = 0..*; Bitácora → Invernadero = 1 | Vigente |
| R133 | DetallePedido, «recibe» | 0..* – 1 | Vigente |
| R136 | Siembra, «corresponde» | 0..* – 1 | Vigente |
| R151 | Compra-venta, «se retira en» | 0..* – 0..1 | Vigente |

**Composiciones** (el invernadero es el todo):

| ID | Con | Cardinalidad en el modelo | Estado |
|---|---|---|---|
| R098 | SectorProduccion, «contiene» | Invernadero → Sector = 1..*; Sector → Invernadero = 1 | **Pendiente (MD-74):** pasa a 0..*. La postcondición a de PROD-ALT-INV ya crea el invernadero sin sectores |
| R068 | SistemaIoT, «tiene» | Invernadero → SistemaIoT = 0..1; SistemaIoT → Invernadero = 1 | Vigente |
| R099 | Lote, «tiene» | 0..* – 1 | Vigente |
| R131 | InsumoInvernadero, «tiene» | 0..* – 1 | Vigente |

Sin herencias.

**Eliminadas:** R041 (MovimientoInsumo–Invernadero) y R071 (Hardware–Invernadero): el invernadero se obtiene por otro
camino.

### Reglas que lo tocan

- **Regla nueva (MD-87):** el nombre del invernadero es único, sin distinguir mayúsculas de minúsculas. Es la regla 1
  de PROD-ALT-INV.
- **Regla 3 de 8.22 (MD-87):** la alerta de personal faltante se genera también cuando el rol nunca se asignó, no solo
  cuando el asignado pasa a inactivo. La del Técnico, solo si el invernadero tiene `SistemaIoT` (R068).
- **Regla 4 de 8.4, reescrita (MD-87):** la baja se bloquea si el invernadero tiene lotes activos, órdenes a realizar,
  partidas de `StockCosechado` con cantidad disponible, algún `InsumoInvernadero` con stock distinto de 0, cantidad en
  tránsito u orden de compra aprobada sin recibir, transportistas vinculados (R155, sin importar su estado) o un
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
| `nivelSeveridad` | — | El modelo no precisa sus valores. El prototipo usa tres: crítica, advertencia e informativa |
| `estadoAlerta` | activa / resuelta | Precisado en la 17ª ronda |
| `fechaResolucion` | — | |
| `estadoLecturaAlerta` | no leída / leída | Precisado en la 17ª ronda. Ver regla 7 de 8.18, cuyo texto no está en este extracto |

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

**Resolución automática.** Varias alertas se resuelven solas cuando desaparece el hecho que las originó:
«stock inconsistente» cuando el stock vuelve a cubrir las reservas (MD-85); «insumo vencido» e «insumo por vencer»
cuando la cantidad disponible del lote llega a cero, con a lo sumo una activa por lote y por tipo (MD-96);
«invernadero sin {rol} activo» al asignar a alguien (regla 3 de 8.22).

---

## Pendientes de pendientes_MD que tocan a este extracto

| ID | Estado | Qué falta |
|---|---|---|
| MD-74 | Decidido sin aplicar (15/11/2026) | R098 pasa a 0..*: un invernadero se da de alta sin sectores |
| MD-85 | Decidido sin aplicar | «Stock inconsistente»: nombre y definición dinámica |
| MD-87 | Decidido sin aplicar (15/11/2026) | Personal opcional del invernadero (R051, R097, R134 y R149 a 0..1); nombre único sin distinguir mayúsculas; regla 4 de 8.4 reescrita |
| MD-88 | Decidido sin aplicar (15/11/2026) | Geografía precargada de Georef, sin ABM; R110 deja de ser composición |
| MD-96 | Aplicado en parte (glosario) | Precisiones de «insumo por vencer» e «insumo vencido» |

MD-87 y MD-88 son los que más pesan en MAE-01: sin ellos, el modelo exige personal y sectores que los casos de uso ya
dejan opcionales.
