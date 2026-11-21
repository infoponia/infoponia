# Modelo de dominio · inventario

Copia para el repo de «Copia de modelo_dominio»: fichas de `TipoInsumo`, `Insumo`, `InsumoInvernadero`, `LoteInsumo` y
`MovimientoInsumo`, con las reglas que las tocan (8.4, 8.13, 8.19 y 8.23). Versión de la ronda 22, consultada el 19/11/2026.
Cotejado con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. **PROVISORIO.**

Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Si el modelo y un caso de uso no coinciden, **manda el caso de
uso** (D-07: la ronda abierta rige aunque el diagrama no la refleje); las diferencias que ya detectamos están en «Diferencias con
el caso de uso» al final.

La ficha de `Semilla` (hereda de `Insumo`; la crea INV-03) está al final de las cinco, antes de «Diferencias con el caso de uso». La de
`ReservaInsumo` (vive en `produccion`, D-46) está descripta en `docs/modelo/produccion.md` (lote 4); acá solo figura cómo `inventario` la ve.

## Convenciones de esta ficha

- Nombres de código según D-05 (snake_case, conservando el sufijo del modelo: `nombreInsumo` → `nombre_insumo`).
- **Cantidades:** `Decimal` con 3 decimales en la base (`DecimalField(max_digits=14, decimal_places=3)`) y validadas contra los
  decimales de la unidad del insumo en el servicio (`inventario/unidades.py`). Nunca `float`. **Precios:** `DecimalField(14, 2)`.
- **Fechas de vencimiento e ingreso:** `DateField`; la «fecha actual» es la de `America/Argentina/Buenos_Aires` (UTC−03:00).
- **Bajas:** lógicas (D-36); nunca se borra una fila de negocio. Las claves foráneas son `PROTECT`.
- **Auditoría:** `Decimal` y fechas **van como texto** en `cambios` y `datos` (`docs/patrones/auditoria.md`).

---

## TipoInsumo

Bloque: Compras e inventario. Vive en `inventario` (D-37). Categoría que agrupa insumos del catálogo según su función.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idTipoInsumo` | — | El `id` automático |
| `nombreTipoInsumo` | texto, hasta 100, único entre todas las categorías sin distinguir mayúsculas ni espacios al borde (activas e inactivas) | → `nombre_tipo_insumo`. Regla 2 de CMP-ALT-TIN |
| `estadoTipoInsumo` | activo / inactivo | → `estado_tipo_insumo`. Baja lógica |
| `consumoDirecto` | no admite / como gasto / como costo de los lotes | → `consumo_directo` (`TextChoices`: `no_admite`, `como_gasto`, `como_costo_de_los_lotes`). Regla 1 de 8.23 y regla 3 de CMP-ALT-TIN |
| `esDelSistema` | booleano | → `es_del_sistema`. Verdadero solo en las cuatro categorías del sistema |
| — | `codigo` | **No está en el modelo.** Texto único, nulo si no es del sistema; lo agrega esta ronda para que las reglas busquen la categoría por una clave que no cambia (regla 1 de 8.23: «no por su nombre»). Valores: `semillas`, `envases`, `repuestos_de_hardware`, `infraestructura` |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R153 | Insumo, «pertenece» | TipoInsumo → Insumo = 0..*; Insumo → TipoInsumo = 1 | Vigente. Clave foránea `tipo_insumo` en `Insumo`, protegida. Asociación simple, no composición |

### Reglas que lo tocan

- **Regla 1 de 8.23 (categorías del sistema):** cuatro, con `es_del_sistema` verdadero, creadas en la puesta en marcha (migración de
  datos `cargar_categorias_del_sistema`). No se renombran, no se modifican y no se dan de baja. `consumo_directo` no se cambia
  si algún insumo de la categoría tiene reservas activas.
- **Restricciones de la base (D-36):** único `lower(nombre_tipo_insumo)`; único `codigo` (cuando no es nulo); `es_del_sistema`
  implica `codigo` no nulo y `consumo_directo = no_admite`; los dominios de `estado_tipo_insumo` y `consumo_directo`.

---

## Insumo

Bloque: Compras e inventario. Vive en `inventario`. Es el **catálogo**: nombre, unidad y categoría, compartido por todos los
invernaderos. El stock, el mínimo y el precio son de `InsumoInvernadero`.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idInsumo` | — | El `id` automático |
| `nombreInsumo` | texto, hasta 100, único entre todos los insumos sin distinguir mayúsculas ni espacios al borde (activos e inactivos) | → `nombre_insumo`. Regla 2 de CMP-ALT-INS |
| `descripcionInsumo` | texto libre, opcional, hasta 300 | → `descripcion_insumo`. El tope de 300 es de esta ronda |
| `unidadMedidaInsumo` | unidad / kg / g / L / mL / m³ / m / m² | → `unidad_medida_insumo` (`TextChoices`: `unidad`, `kg`, `g`, `l`, `ml`, `m3`, `m`, `m2`). Regla 2 de 8.23: decimales 0 / 3 / 2 / 3 / 2 / 3 / 2 / 2 |
| `estadoInsumo` | activo / inactivo | → `estado_insumo`. Baja: regla 3 de 8.4 |
| `controlaVencimiento` | booleano | → `controla_vencimiento`. Regla 3 de 8.23: si es verdadero, cada lote lleva fecha de vencimiento |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R130 | InsumoInvernadero, «tiene existencia en» | Insumo → InsumoInvernadero = 0..*; InsumoInvernadero → Insumo = 1 | Vigente (corregida a 0..* en la 19ª ronda) |
| R153 | TipoInsumo, «pertenece» | Insumo → TipoInsumo = 1; TipoInsumo → Insumo = 0..* | Vigente |
| R037 | DetallePedido, «corresponde» | 0..* – 1 | **La declara `compras`** (A2). No existe en esta ronda |
| R072 | Hardware, «corresponde» | 0..* – 1 | **La declara `iot`** (A2). No existe en esta ronda |

Herencia: es padre de `Semilla` (INV-03). **Un insumo es una semilla si su categoría es la del sistema `semillas`**; `inventario`
lo decide por esa categoría y no depende del modelo `Semilla` (INV-01 e INV-02 funcionan sin él).

### Reglas que lo tocan

- **Regla 3 de 8.4 (baja del catálogo):** inactivo solo si en ningún invernadero tiene stock distinto de 0, reservas activas,
  cantidad en tránsito, una orden de compra aprobada sin recibir o un pedido en curso; al pasar a inactivo, pasan a inactivo
  todos sus `InsumoInvernadero`.
- **Restricciones de la base:** único `lower(nombre_insumo)`; los dominios de `unidad_medida_insumo` y `estado_insumo`.

---

## InsumoInvernadero

Bloque: Compras e inventario. Vive en `inventario`. Existencia de un insumo del catálogo en un invernadero: su mínimo, su tránsito
y su precio de referencia propios. Es **parte del invernadero** (R131, composición).

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idInsumoInvernadero` | — | El `id` automático |
| `/cantActualInsumo` | **derivado** | → función `stock_actual`. Suma de `cantidad_disponible` de sus lotes, incluido el faltante sin lote. Puede ser negativo. **No se guarda** (regla 3 de 8.23) |
| `cantMinInsumo` | cantidad ≥ 0, con los decimales de la unidad | → `cant_min_insumo` |
| `cantTransitoInsumo` | cantidad ≥ 0 | → `cant_transito_insumo`. **En esta ronda vale 0 y solo la escribirá `compras`** (D-45). La columna existe |
| `referenciaPrecio` | precio > 0, 2 decimales | → `referencia_precio`. Precio por unidad puesto en el invernadero, con flete; lo mantiene el Agrónomo (regla 6 de 8.18) |
| `estadoInsumoInvernadero` | activo / inactivo | → `estado_insumo_invernadero`. Baja: regla 3 de 8.4 |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R130 | Insumo | InsumoInvernadero → Insumo = 1 | Vigente. Clave foránea `insumo`, protegida |
| R131 | Invernadero, «tiene», composición | InsumoInvernadero → Invernadero = 1; Invernadero → InsumoInvernadero = 0..* | Vigente. Clave foránea `invernadero`, protegida |
| R165 | LoteInsumo, «tiene», composición | InsumoInvernadero → LoteInsumo = 0..*; LoteInsumo → InsumoInvernadero = 1 | Vigente |
| R139 | ReservaInsumo | InsumoInvernadero → ReservaInsumo = 0..*; ReservaInsumo → InsumoInvernadero = 1 | **La declara `produccion`** (A2, D-46). `inventario` pregunta por las reservas con un punto de extensión |
| R045 | Consumo, «corresponde» | 0..* – 1 | **La declara `produccion`** (A2) |

### Reglas que lo tocan

- **Regla 1 de 8.4:** un solo `InsumoInvernadero` por `(insumo, invernadero)`. Habilitar crea el registro activo, sin lotes y con
  stock 0; si el par ya existió y está inactivo, se reactiva el mismo. El stock que ya había entra con una carga inicial.
- **Regla 3 de 8.4:** la deshabilitación se bloquea si tiene stock distinto de 0 (positivo o negativo), reservas activas, cantidad en
  tránsito o una orden de compra aprobada sin recibir.
- **Regla 4 de 8.4 (baja del invernadero):** cascada de baja lógica a sus `InsumoInvernadero`, sujeta a que todos tengan stock 0.
  La conecta INV-02 con `registrar_impedimento_de_baja` y `registrar_efecto_de_baja` de `maestros/extensiones.py`.
- **Regla 8 de 8.4 y fórmulas de stock:** `docs/patrones/stock.md`.
- **Restricciones de la base:** único `(insumo, invernadero)`; `cant_min_insumo >= 0`; `cant_transito_insumo >= 0`;
  `referencia_precio > 0`; el dominio de `estado_insumo_invernadero`.

---

## LoteInsumo

Bloque: Compras e inventario. Vive en `inventario`. Cada partida de un insumo que entró a un invernadero, con su cantidad y su
vencimiento. Permite saber qué está vencido y consumir primero lo que vence antes (FEFO). Incluye el lote especial **«faltante sin
lote»**. **No confundir con `Lote` (el de plantas, que es de `produccion`).**

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idLoteInsumo` | — | El `id` automático |
| `cantidadIngresada` | cantidad > 0 | → `cantidad_ingresada`. Nula en el faltante sin lote |
| `cantidadDisponible` | cantidad | → `cantidad_disponible`. ≥ 0, salvo en el faltante sin lote, que es ≤ 0. Un lote en 0 se conserva (trazabilidad) |
| `fechaIngreso` | fecha | → `fecha_ingreso`. La del movimiento que lo creó. Nula en el faltante |
| `fechaVencimiento` | fecha | → `fecha_vencimiento`. Obligatoria si el insumo controla vencimiento; nula si no. Nula en el faltante |
| `/vencido` | **derivado** | → función `esta_vencido(lote, hoy)`: la fecha de vencimiento es anterior a hoy. El día del vencimiento todavía se puede usar |
| `esFaltanteSinLote` | booleano | → `es_faltante_sin_lote`. A lo sumo uno por `InsumoInvernadero` |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R165 | InsumoInvernadero, composición | LoteInsumo → InsumoInvernadero = 1 | Vigente. Clave foránea `insumo_invernadero`, protegida |
| R166 | MovimientoInsumo, «afecta» | LoteInsumo → MovimientoInsumo = 1..*; MovimientoInsumo → LoteInsumo = 1 | Vigente. «Todo lote nace con el movimiento que lo crea» lo garantiza el servicio, no la base |

### Reglas que lo tocan

- **Regla 3 de 8.23 (lotes):** todo ingreso entra en un lote. FEFO: primero el que vence antes; sin vencimiento, del ingresado antes al más
  nuevo. FEFO no propone lotes vencidos ni el faltante sin lote.
- **Regla 4 de 8.23 (faltante sin lote):** a lo sumo uno por `InsumoInvernadero`; se crea con la primera salida que lo necesita;
  es el único lote que puede ser negativo y nunca es positivo. Un ajuste negativo nunca sale de él.
- **Restricciones de la base:** único parcial `insumo_invernadero` donde `es_faltante_sin_lote`; si `es_faltante_sin_lote`:
  `cantidad_disponible <= 0` y ingresada, ingreso y vencimiento nulos; si no: `cantidad_disponible >= 0`, `cantidad_ingresada > 0` y
  `fecha_ingreso` no nula. Que `fecha_vencimiento` sea obligatoria según el insumo no se puede expresar como restricción de una
  tabla (depende de otra): lo verifica el servicio.

---

## MovimientoInsumo

Bloque: Compras e inventario. Vive en `inventario`. El kárdex: todo cambio de `cantidad_disponible` de un lote genera **exactamente un**
movimiento de ese lote (regla 1 de 8.19). Una operación que toca varios lotes genera un movimiento por lote.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idMovimientoInsumo` | — | El `id` automático |
| `fecha` | fecha y hora | → `fecha`. La fecha de la operación con la hora actual. En una salida por consumo de siembra, la fecha es la **efectiva** de la siembra (que puede ser anterior a hoy; D-50 punto 7) |
| `cantidad` | cantidad > 0 | → `cantidad`. Siempre positiva: el sentido lo da el tipo |
| `tipo_movimiento` | ingreso por recepción / salida por consumo / ajuste positivo / ajuste negativo / salida por corrección entre lotes / entrada por corrección entre lotes | `tipo_movimiento` (`TextChoices`; no se llama `tipo` porque choca con `OrigenDocumento.tipo`, D-52). En esta ronda se crean los cuatro últimos y «salida por consumo»; el ingreso por recepción lo crea `compras` |
| `motivoAjuste` | recuento físico / rotura o pérdida / carga inicial / vencimiento / otro | → `motivo_ajuste`. Solo en ajustes. **La corrección entre lotes no es un motivo guardado**: se guarda con sus dos tipos propios, aunque la pantalla la ofrece como un motivo más |
| `descripcionAjuste` | texto libre | → `descripcion_ajuste`. Solo en ajustes; obligatoria si el motivo es «otro» |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R166 | LoteInsumo, «afecta» | MovimientoInsumo → LoteInsumo = 1 | Vigente. Clave foránea `lote_insumo`, protegida |
| R016 | OrigenDocumento, «se origina» | MovimientoInsumo → OrigenDocumento = 0..1; OrigenDocumento → MovimientoInsumo = 0..* | **Vigente desde D-52.** `origen`: clave foránea nula a `contabilidad.OrigenDocumento`, `PROTECT`, `related_name="movimientos_de_insumo"`. **Reemplaza a `movimiento_origen`**: la entrada por corrección entre lotes apunta a su salida (que es un documento, porque `MovimientoInsumo` hereda de `OrigenDocumento`); la salida por consumo apunta al `Consumo` (lo recibe de `produccion` como `origen_id`); el ingreso por recepción apuntará a la recepción (`compras`, ronda futura) |
| R016 / R032 | Consumo / DetalleRecepcion | | **Ya no hay tabla de enlace (D-52):** el consumo (`produccion`) y la recepción (`compras`) son documentos de origen y sus movimientos los apuntan con `origen`. Se leen con `consumo.movimientos_de_insumo` |
| R040 | Lote (de plantas), «asocia» | 0..1 – 0..* | **Se deriva, no se guarda (D-52 punto 6):** en una siembra, por `consumo.siembra.lote`; en una aplicación, por las imputaciones del consumo |

Herencias: **hereda de `OrigenDocumento`** (`contabilidad`, D-52): se implementa como herencia multitabla de Django, con clave primaria `origendocumento_ptr` y `tipo = movimiento_de_insumo`. Cada movimiento de ajuste es su propio documento de origen (regla 3 de 8.19); el asiento que origina está fuera de la ronda (D-45).

### Reglas que lo tocan

- **Regla 1 de 8.19:** para todo lote, ingresos − salidas = `cantidad_disponible`; para todo `InsumoInvernadero`, la suma de los lotes es
  la existencia. Los cambios de `cant_transito_insumo` no generan movimientos.
- **Regla 2 de 8.19:** salida y entrada por corrección entre lotes van de a pares y por la misma cantidad; la entrada se origina en su salida;
  ninguna cambia la existencia ni afecta al faltante sin lote como origen.
- **Regla 3 de 8.19:** sin origen si y solo si es de ajuste o salida por corrección. (Con asientos, además: origina asiento si y solo si es de ajuste.)
- **Regla 4 de 8.19:** los ajustes se registran sobre un lote.
- **Restricciones de la base:** `cantidad > 0`; el dominio de `tipo_movimiento`; `motivo_ajuste` no nulo si y solo si `tipo_movimiento` es ajuste positivo o negativo;
  `descripcion_ajuste` no vacía si `motivo_ajuste = otro`; `origen` nulo si y solo si `tipo_movimiento` es ajuste positivo , ajuste negativo o salida por corrección entre lotes (regla 3 de 8.19).
  Que el origen de una entrada por corrección sea la salida de la misma cantidad lo verifica el servicio; que el de una salida por consumo sea un consumo, lo garantiza `produccion` (no lo puede nombrar `inventario`, A1).

---

## Semilla

Bloque: Compras e inventario. Vive en `inventario` (D-37). **La crea INV-03.** Es el material de propagación de una variedad (semilla o
plantín) y hereda de `Insumo`: se implementa como herencia multitabla de Django (`class Semilla(Insumo)`, con la clave primaria
`insumo_ptr`), de modo que toda la lógica de insumos, existencias y lotes la sigue tratando como un `Insumo` más.

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| (los de `Insumo`) | — | Nombre «Semilla {cultivo} {variedad}», categoría `semillas`, unidad `unidad`, `controla_vencimiento` verdadero, estado igual al de su variedad (postcondición c de PROD-ALT-VAR) |
| `variedad` | FK uno a uno, `PROTECT` (R137) | → `variedad`. La FK se declara acá, en la app de nivel mayor (A2 de D-37), apuntando a `maestros.Variedad`. `related_name="semilla"`. Único. Atributos propios: ninguno (`esPeletizada` se eliminó en la 22ª ronda) |

### Asociaciones

| ID | Con | Cardinalidad | Estado |
|---|---|---|---|
| R137 | Variedad, «corresponde» | Semilla → Variedad = 1; Variedad → Semilla = 1 | Vigente (rediseño de la 22ª ronda) |

### Reglas que la tocan

- **Se crea, se renombra, se da de baja y se reactiva solo con su variedad** (PROD-ALT-VAR, PROD-MOD-VAR, PROD-BAJ-VAR) y se renombra
  también con su cultivo (PROD-MOD-CLT). Ni el alta, ni la modificación, ni la baja de insumos (CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS)
  las tocan.
- **La categoría la fija el servicio, no la base:** una semilla siempre está en la categoría `semillas`, y ningún otro insumo lo está.
  Lo garantizan los servicios (el alta de insumos no ofrece esa categoría, regla 4 de CMP-ALT-INS) y una prueba de invariante
  (`Semilla` ⇔ categoría `semillas`).
- Se habilita en cada invernadero con CMP-HAB-IIN, como cualquier insumo (regla 3 de CMP-CNS-INS); sin habilitar no se pide ni se siembra.
- La baja de la variedad deja inactiva a la semilla pero **no deshabilita sus `InsumoInvernadero`**: el stock que queda sigue registrado
  (regla 3 de PROD-BAJ-VAR). Es la única excepción a «el insumo inactivo no tiene existencias activas» (regla 3 de 8.4); la reactivación
  de la variedad no vuelve a habilitar las existencias que ya estaban deshabilitadas.
- Restricciones de la base: único `variedad_id` (la FK uno a uno).

---

## Diferencias con el caso de uso

Las siguientes diferencias entre este documento (copia del modelo) y los casos de uso **ya están resueltas a favor del caso de uso**
(L7). Se anotan en `docs/temas_abiertos.md` para actualizar el modelo en Drive (pendientes_MD).

| # | Modelo | Caso de uso | Se implementa |
|---|---|---|---|
| 1 | Regla 3 de 8.23: un ajuste positivo de otro motivo suma a un lote existente que elige quien lo registra | CMP-AJT-STK, extensión 7e: «otro» que suma sigue 7a y crea un lote nuevo | **El caso de uso** |
| 2 | Regla 4 de 8.23 y ejemplo de la regla 5 de 8.19: todo ingreso (recepción o ajuste positivo) cancela primero el faltante sin lote | CMP-AJT-STK, paso 14.3 y reglas: el faltante queda en cero solo con un recuento físico, o se acerca a cero con una corrección entre lotes | **El caso de uso.** Una carga inicial o un «otro» que suma no lo tocan; la recepción (`compras`) sí lo hará |
| 3 | Regla 6 de 8.13: «stock inconsistente» mide el stock actual (`/cantActualInsumo`) | CMP-AJT-STK, postcondiciones h e i y 12b: mide el stock **sin lotes vencidos** | **El caso de uso** (ver `docs/patrones/stock.md`, «Stock inconsistente») |
| 4 | R139: `ReservaInsumo` pertenece a `InsumoInvernadero` | D-46 decía que apunta a `LoteInsumo` | **El modelo** (R139); D-46 se corrigió (consecuencias y nombre del punto de extensión) |
| 5 | Alertas de vencimiento: «van al Agrónomo del invernadero (R049)»; toda alerta tiene al menos un destinatario (MD-61, D-41) | CMP-REV-VNC, regla 6: sin Agrónomo no se genera alerta | **El caso de uso**, solo para las alertas de vencimiento (`docs/casos_de_uso/inventario/vencimientos.md`) |
| 6 | Regla 3 de 8.4: cuando un insumo pasa a inactivo, todos sus `InsumoInvernadero` pasan a inactivos | PROD-BAJ-VAR, regla 3: la semilla queda inactiva pero su stock sigue registrado y se descarta con un ajuste | **El caso de uso**, solo para las semillas dadas de baja con su variedad (lote 3) |
