# Modelo de dominio · compras (extracto)

Extracto del modelo de dominio (Drive, «MD · Modelo de dominio», bloque «Gestión compras e inventario»: fichas Proveedor, Pedido, DetallePedido,
Cotizacion, DetalleCotizacion, OrdenCompra, DetalleOrdenCompra, Recepcion, DetalleRecepcion, InconvenienteRecepcion, ReclamoProveedor y Pago;
reglas de 8.15 a 8.22) con **los cambios de A0 aplicados** (MD-121 a MD-130 de `pendientes_para_pegar.md`; por regla del estudiante del 23/11/2026
mandan aunque todavía no estén en Drive). Decisiones de implementación: **D-87 a D-91**. Todo vive en la app `compras` (nivel 6, D-37).

Si este archivo y el modelo de Drive no coinciden, avisá: no elijas en silencio. Lo marcado **(técnico)** no está en el modelo de dominio: es cómo
el código cumple una regla.

## Convenciones de este extracto (D-05)

- Nombres en `snake_case` del atributo del modelo (`cuitProveedor` → `cuit_proveedor`). Claves `id` automáticas (D-06).
- Cantidades de insumo: `DecimalField(max_digits=14, decimal_places=3)` validadas con `inventario.unidades.validar_cantidad(valor, unidad)` (los
  decimales dependen de la unidad; D-87 punto 7). Importes: `DecimalField(14, 2)`. Precio unitario derivado: 4 decimales (D-89).
- Fechas de negocio con `timezone.localdate()` (`inventario.servicios.stock.hoy()`); fechas y horas con `timezone.now()`.
- FK con `on_delete=PROTECT` salvo que se diga otra cosa. Nada se borra: hay estados.

---

## Proveedor

Persona u organización externa que cotiza y vende insumos. No tiene cuenta: participa por enlaces enviados por correo (GLO › Proveedor). No tiene
dirección (X7).

| Atributo | Valores | Nota |
|---|---|---|
| — | `tipo_proveedor`: `juridica` / `fisica` **(técnico)** | Igual que `Cliente` (`docs/modelo/comercial.md`): razón social **o** nombre y apellido (regla 1 de CMP-ALT-PRV) |
| `cuitProveedor` | 11 dígitos | → `cuit_proveedor`, `CharField(11)`, **único entre todos, activos e inactivos** (MD-122, H14); `^\d{11}$`; se valida con `maestros.validadores.validar_cuit` y se muestra con `formatear_cuit` (D-58) |
| `razonSocialProveedor` | texto, hasta 150 | Obligatoria si es persona jurídica; vacía si no |
| `nombreProveedor`, `apellidoProveedor` | texto, hasta 80 | Obligatorios si es persona física; vacíos si no |
| `emailProveedor` | correo, **obligatorio** | `EmailField` (254), no único |
| `telefonoProveedor` | texto, hasta 25, **opcional** (P5, MD-130) | `core.validadores.validar_telefono` (D-21) |
| `estadoProveedor` | activo / inactivo | Baja lógica |
| ~~`especialidad`~~ | — | **Reemplazado** por la asociación «se especializa en» (MD-121) |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| nueva (MD-121) | TipoInsumo, «se especializa en» | 0..\* – 0..\* | `especialidades = ManyToManyField("inventario.TipoInsumo", blank=True, related_name="proveedores_especializados")` declarado en `compras` (A2). Una categoría dada de baja conserva el vínculo; los filtros muestran solo las activas |
| R157 | Pedido, «se invita a» | 0..\* – 1..\* | `InvitacionPedido` (abajo) |
| R035 | Cotizacion | 0..\* – 1 | FK en `Cotizacion` |
| R158 | Pago | 0..\* – 1 | FK en `Pago` |
| R028 | ReclamoProveedor (composición) | 0..\* – 1 | FK en `ReclamoProveedor` |

Restricciones de la base: CUIT único y de 11 dígitos; la misma por tipo que `Cliente`. **Alcance:** el Gerente y el Agrónomo activos ven todos; solo
el Gerente modifica (segregación de funciones, decisión del ABM).

## Pedido

| Atributo | Valores | Nota |
|---|---|---|
| `fechaPedido` | fecha | Hoy al registrar |
| `fechaLimiteCotizaciones` | fecha | ≥ mañana. El enlace vence al terminar ese día |
| `estadoPedido` | `en_cotizacion` / `cerrado` / `cancelado` | |
| `fechaCierrePedido` | fecha, nula | Para «cerrado» **y** «cancelado» (MD-124) |
| `motivoCancelacion` (MD-124) | texto, hasta 500 | Obligatorio en la cancelación manual; las automáticas guardan su texto fijo |
| — | `causa_cancelacion` **(técnico)** | `manual` / `nadie_cotizo` / `sin_cotizaciones_elegibles` / `agronomo_inactivo` / `agronomo_sin_invernadero`; nula si no está cancelado. Responde «si fue automática» (CMP-CNS-PED regla 4) |
| — | `aviso_vencimiento_dado` **(técnico)** | booleano; lo pone el paso 60 (D-87 punto 4) |
| — | `recordatorio_validez_para` **(técnico)** | fecha nula; el paso 61 guarda la fecha de validez que recordó |
| `/montoPedido` | derivado | Σ cantidad × precio de referencia copiado; anotación, no columna |

R038 Agrónomo «realiza» (1): `agronomo = FK("core.Agronomo")`. R025 DetallePedido (composición, 1..\*). R157: `InvitacionPedido`.

Restricciones: `estado ∈ {cerrado, cancelado}` ⇔ `fecha_cierre_pedido` no nula; `estado = cancelado` ⇔ `causa_cancelacion` no nula;
`causa = manual` ⇒ `motivo_cancelacion` no vacío.

## DetallePedido

| Atributo | Valores | Nota |
|---|---|---|
| `cantidadDetalle` | cantidad > 0 | En la unidad del insumo |
| `precioUnitarioDePedido` | importe > 0 | Copia de `InsumoInvernadero.referencia_precio` al registrar. No se muestra a los proveedores |

R037 (Insumo) y R133 (Invernadero) **se guardan juntos** como `insumo_invernadero = FK("inventario.InsumoInvernadero")` **(técnico)**: solo se pide
un insumo habilitado (regla 2 de 8.15), así que el par existe siempre y es una sola FK. Restricción única `(pedido, insumo_invernadero)`
(«detalle único»).

## InvitacionPedido (R157) **(técnico: la tabla de la asociación muchos a muchos)**

`pedido`, `proveedor`, `fecha_invitacion`. Único `(pedido, proveedor)`. Es la «invitación» que audita CMP-RLZ-PED (postcondición g).

## EnlaceProveedor (D-88) **(técnico)**

`invitacion` (FK `InvitacionPedido`, `related_name="enlaces"`), `token_resumen` (64, único), `fecha_creacion`, `estado` (`vigente` / `usado` /
`vencido` / `anulado` / `reemplazado`), `fecha_uso` (nula), `estado_envio` (`enviado` / `pendiente_envio`, nulo hasta el intento). Restricciones:
único parcial «un `vigente` por invitación»; `estado = usado` ⇔ `fecha_uso` no nula. No se audita por su cuenta (lo nombra el caso de uso que lo
crea o lo cambia).

## Cotizacion

| Atributo | Valores | Nota |
|---|---|---|
| `fechaCotizacion` | fecha | Hoy. **(técnico)** `enviada_el` (fecha y hora) para el acuse |
| `fechaValidezCotizacion` | fecha | ≥ fecha límite del pedido; se propone fecha límite + `diasValidezCotizacion` |
| `estadoCotizacion` | `propuesta` / `seleccionada` / `descartada` | Se aplica a la cotización entera |
| `observacionesCotizacion` | texto, opcional, hasta 1000 | |
| `/montoCotizacion` | derivado | Σ `total_linea` |

R035 Proveedor (1). **(técnico)** `pedido = FK(Pedido)`: el modelo lo obtiene por las líneas (R159 → R024 → R025); se guarda para que la base
garantice **C8** con la restricción única `(pedido, proveedor)` («una cotización por proveedor y por pedido»). Que cada línea sea de un detalle de
ese pedido lo garantiza el servicio (prueba).

## DetalleCotizacion

| Atributo | Valores | Nota |
|---|---|---|
| `cantidadCotizada` | cantidad > 0 | **Puede superar la pedida** (P2, MD-130); se propone la pedida |
| `total_linea` (MD-125) | importe > 0 | **Se guarda el total**; el unitario es derivado (`compras.precios.precio_unitario`, 4 decimales; D-89) |
| `plazoEntregaDias` | entero ≥ 1 (P2) | Días corridos desde la aprobación |

R024 DetallePedido (1); R159 Cotizacion (composición); R023 DetalleOrdenCompra (0..1). Único `(cotizacion, detalle_pedido)`.

## OrdenCompra

| Atributo | Valores | Nota |
|---|---|---|
| `fechaEmision` | fecha | Hoy |
| `fechaResolucion` | fecha, nula | Al aprobar o rechazar |
| `estadoOrdenCompra` | `pendiente_aprobacion` / `aprobada` / `rechazada` / `parcialmente_recibida` / `recibida` / `recibida_con_faltante` | Regla 24 de 8.16 |
| `observaciones` | texto, opcional | Del Agrónomo |
| `motivoRechazo` | texto | Obligatorio al rechazar; vacío si no |
| `/montoTotalOrdenCompra` | derivado | Σ `total_linea` de sus detalles |

R011 Gerente «resuelve» (0..1): `gerente = FK("core.Gerente", null=True)`. **(técnico)** `pedido = OneToOneField(Pedido, related_name="orden_compra")`:
«un pedido tiene como máximo una orden» (regla 13 de 8.16) garantizado por la base. Restricciones: `estado ≠ pendiente_aprobacion` ⇔ `gerente` y
`fecha_resolucion` no nulos; `estado = rechazada` ⇔ `motivo_rechazo` no vacío.

## DetalleOrdenCompra

| Atributo | Valores | Nota |
|---|---|---|
| `cantidadDetalleOrden` | cantidad > 0 | Copia de la **cotizada** (P2) |
| `total_linea` (MD-125) | importe > 0 | Copia de la línea de cotización; el unitario es derivado |
| `fechaEntregaEsperada` | fecha, nula | Al aprobar: fecha de resolución + plazo |
| `estadoDetalleOrden` | `pendiente` / `completo` / `cerrado_con_faltante` | |
| `motivoCierreFaltante` | texto | Obligatorio al cerrar con faltante |
| — | `fecha_cierre_faltante` **(técnico)** | Fecha nula; para ordenar la bandeja de pagos (D-91) |
| `/cantidadRecibida` | derivado | Σ `cantidad_recibida_detalle` de sus `DetalleRecepcion` (con la línea bloqueada) |

R023 `detalle_cotizacion = OneToOneField(DetalleCotizacion, related_name="detalle_orden")`. **R026 se deriva** (`detalle_cotizacion.detalle_pedido`)
**(técnico)**: guardarla repetiría un dato que no puede ser distinto (regla 5 de 8.17). El proveedor de la línea también se deriva (cotización).
Restricciones: `estado = cerrado_con_faltante` ⇔ `motivo_cierre_faltante` no vacío y `fecha_cierre_faltante` no nula.

## Recepcion (hereda de OrigenDocumento, tipo `recepcion`)

`fecha_recepcion` (hoy, sin fechas retroactivas), `observaciones_recepcion` (opcional), `orden` (R019), `agronomo` (R039, **0..1**: vacío si la
registró el Gerente; quien registró queda en la auditoría). **(técnico)** `proveedor` e `invernadero` (FK): «una recepción es de una orden, un
proveedor y un invernadero» (regla 7 de 8.20); los fija el servicio y una prueba verifica la coherencia con sus líneas.

## DetalleRecepcion

`cantidad_recibida_detalle` (≥ 0: lo que **ingresó** al stock; 0 solo con un inconveniente que no sea «otro»), `recepcion` (composición),
`detalle_orden` (R022). Único `(recepcion, detalle_orden)`. La corrección (CMP-COR-RCP) **baja** esta cantidad.

## DetalleRecepcionMovimiento (R032) **(técnico, D-90)**

`detalle_recepcion` (FK, `related_name="vinculos_de_movimiento"`), `movimiento` (`OneToOneField("inventario.MovimientoInsumo",
related_name="vinculo_de_recepcion")`). Uno por lote tocado (incluido el faltante sin lote).

## InconvenienteRecepcion

| Atributo | Valores | Nota |
|---|---|---|
| `tipoInconveniente` | `mercaderia_danada` / `calidad_no_conforme` / `producto_distinto` / `vencido_o_por_vencer` / `otro` | **P4, MD-130** (reemplaza daño / retraso / vencido / otro). El retraso se calcula y se muestra, no se declara |
| `cantidadAfectada` | cantidad > 0 | |
| `descripcionInconveniente` | texto | Obligatoria en «otro»; opcional en los demás |

R030 DetalleRecepcion (1); R029 ReclamoProveedor (1). Único `(detalle_recepcion, tipo_inconveniente)`.

## ReclamoProveedor

`fecha_reclamo` (nula: fecha de emisión), `estado_reclamo` (`abierto` / `cerrado`), `gerente` (R008, 0..1: emitido ⇔ tiene Gerente), `proveedor`
(R028). **(técnico)** `recepcion = OneToOneField(Recepcion, related_name="reclamo")`: un reclamo por recepción con inconvenientes (regla 10 de
8.20). Restricciones: `gerente` nulo ⇔ `fecha_reclamo` nula; `cerrado` ⇒ `gerente` no nulo.

## AlertaCompras **(técnico, D-87 punto 5; patrón de `AlertaComercial`, D-63)**

`alerta = OneToOneField("maestros.Alerta")`, `reclamo = FK(ReclamoProveedor)`. La crea CMP-04 con la alerta; la emisión del reclamo la resuelve.

## CorreccionRecepcion (hereda de OrigenDocumento, tipo `correccion_de_recepcion`; MD-126)

`recepcion` (FK), `fecha_correccion`, `observacion` (opcional), `agronomo` (0..1, como la recepción). Líneas: `DetalleCorreccionRecepcion`
**(técnico)** con `correccion`, `detalle_recepcion`, `cantidad_corregida` (> 0), y su vínculo al movimiento de salida
(`movimiento = OneToOneField("inventario.MovimientoInsumo", related_name="vinculo_de_correccion")`; uno por lote descontado: si toca dos lotes,
dos filas).

## Pago (hereda de OrigenDocumento, tipo `pago`)

`fecha_pago` (la elige quien paga), `medio_pago` (`efectivo` / `transferencia` / `tarjeta_debito` / `tarjeta_credito`), `monto_pago` **(guardado,
D-89 punto 6)**, `orden` (R018), `proveedor` (R158). Único `(orden, proveedor)`. El proveedor es uno de los de la orden (servicio y prueba).

---

## Reglas de 8.15 a 8.22 que se aplican en compras (resumen; el texto completo está en los extractos de casos de uso)

| Regla | Dónde se cumple |
|---|---|
| Insumo bajo el mínimo: libre + tránsito < mínimo (8.15) | `inventario.stock.existencias` (ya existe) |
| Pedido: insumo habilitado; par insumo–invernadero único; precio de referencia copiado; fecha límite ≥ mañana (8.15) | CMP-02a |
| Cotización: una por proveedor y pedido (C8), enviada una vez; vigencia del enlace (8.16, 8.17) | CMP-02a |
| Cobertura con tolerancia (`porcToleranciaCoberturaPedido`) (8.16) | CMP-03 (y el aviso de «pedido cubierto» de CMP-02a) |
| Una orden por pedido, decisión total del Gerente, motivo de rechazo (8.16, 8.20 regla 12) | CMP-03 |
| Tránsito: sube al aprobar, baja al recibir y al cerrar con faltante (8.16 regla 22) | CMP-03, CMP-04 |
| Recepción: no supera lo pendiente; un proveedor e invernadero; lo dañado no entra; lotes con faltante primero (8.20 reglas 6 a 11; 8.23) | CMP-04 |
| Pago: uno por proveedor y orden, después de recibir, por lo recibido (8.20 reglas 13 y 14; 8.18 regla 4 con MD-125) | CMP-05 |
| Pedidos de un Agrónomo inactivo o que deja el invernadero se cancelan (8.22 regla 5, MD-62) | CMP-02b |
| Validez de la cotización (8.22 regla 6) | CMP-03 |
| Destinatarios de los avisos (H21, MD-67) | `compras/servicios/avisos.py` (D-87 punto 3) |

## Glosario (términos de la ronda)

- **Pedido (de cotización):** lo que el Agrónomo pide cotizar, para uno o varios de sus invernaderos.
- **Cotización:** la oferta completa de un proveedor para un pedido, con una línea por cada detalle que cotiza.
- **Orden de compra:** una por pedido; puede tener varios proveedores. La aprueba o la rechaza el Gerente.
- **Recepción:** lo que un proveedor entrega en un invernadero para una orden.
- **Cierre con faltante:** dar por terminada una línea que el proveedor no va a completar. No es un reclamo.
- **Reclamo:** el registro de los inconvenientes de una recepción; nace sin emitir y lo emite el Gerente (se le envía por correo al proveedor).
- **Pago pendiente:** proveedor de una orden con todas sus líneas completas o cerradas, algo recibido y sin pago.
