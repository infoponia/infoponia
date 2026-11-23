# Modelo de dominio · comercial

Copia para el repo de «Copia de modelo_dominio»: fichas de `Cliente`, `Direccion` (en lo que toca al cliente) y `Vehiculo`, con las
reglas que las tocan (8.18 y 8.22) y la restricción C6. Versión de la ronda 22, consultada el 21/11/2026. Cotejado con pendientes_MD
hasta MD-113, con «MD · Cambios para el modelo de dominio (comercial)» (MD-114 a MD-139, todavía no pegados en pendientes_MD) y con el
glosario del 19/11/2026 más «GLO · Cambios para el Glosario (comercial)». **PROVISORIO.**

Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Si el modelo y un caso de uso no coinciden, **manda el caso de uso**
(D-07); las diferencias que ya detectamos están en «Diferencias con el caso de uso» al final.

Este extracto crece con la ronda: el lote C1 trajo las clases de COM-01 y el lote C2 suma `Contrato`, `CompraVenta`, `DetalleVenta`,
`ReservaStock` y `DetalleReserva` (COM-02, D-59). `Cosecha` y `StockCosechado` viven en `produccion` (D-37, D-59): sus fichas están en
`docs/modelo/produccion.md`. El lote C3 suma `Suministro`, `DetalleSuministro`, sus dos cláusulas y `AlertaComercial` (COM-03, D-63).
El lote C4 suma `EnlaceCliente` (D-65) y `AlertaComercial.partida`, y corrige dos restricciones de C2 (D-64, puntos 6 y 7).
El lote C5a suma `Entrega` y `DetalleEntrega` y `AlertaComercial.entrega` (COM-05a1, D-66); el C5b, los datos de la cancelación de
una compra-venta (COM-05b, MD-130, en «CompraVenta»). El C6 suma lo de la concreción en `Entrega` y `DetalleEntrega`, `PagoCliente`,
`IntentoFallido`, `SolicitudRevision`, `DiscrepanciaEntrega` y `LineaDiscrepancia` (COM-06a) y `Queja` (COM-06b), con `AlertaComercial.solicitud`
y el enlace de confirmación (D-68). El C7 suma `Anulacion` (MD-135), la aplicación de la indemnización y el aviso al cliente en
`SolicitudRevision` y `Suministro.solicitud_resolucion` (COM-07a, D-69). El C8 suma `LineaPago` (R154), lo nuevo de `PagoCliente` y la mora
en `Entrega` (COM-08a) y `Anulacion.pago` con `PagoCliente.anulacion_corregida` (COM-08b, D-94). Con el C8, el extracto está completo para la
ronda. Los nombres COM-03, COM-04, COM-05a, COM-06, COM-07 y COM-08 de abajo se leen con la tabla de la sección 1 del plan (D-67, punto 2;
D-68, punto 1; D-69, punto 1; D-94, punto 1). `Transportista` vive en `core` (D-01) y su
invernadero en `maestros.TransportistaInvernadero` (D-55, `docs/modelo/maestros.md`).

## Convenciones de esta ficha

- Nombres de código según D-05 (snake_case, conservando el sufijo del modelo: `cuitCliente` → `cuit_cliente`). Los atributos que en el
  modelo no tienen sufijo (`marca`, `modelo`, `patente`) lo conservan así.
- **Bajas:** lógicas; nunca se borra una fila de negocio (la única excepción es una dirección que nada usa, regla 4 de COM-MOD-CLT).
  Las claves foráneas son `PROTECT`.
- **Textos:** se guardan recortados; los largos máximos que el modelo y los casos de uso no fijan los fija este extracto (columna
  «Nota»).
- **Auditoría:** `Decimal` y fechas **van como texto** en `cambios` y `datos` (`docs/patrones/auditoria.md`).

---

## Cliente

Bloque: Gestión comercial. Vive en `comercial` (D-37). Glosario: «persona física o jurídica externa que adquiere producción mediante un
contrato de Compra-venta o de Suministro; opera sin cuenta de usuario propia, mediante enlaces de acceso temporal enviados por correo,
cuando tiene un correo registrado».

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idCliente` | — | El `id` automático (D-06) |
| — | `tipo_cliente`: `juridica` / `fisica` | **No está en el modelo.** Lo pide la regla 3 de COM-ALT-CLT (persona jurídica o física). `TextChoices` con las etiquetas «Persona jurídica» y «Persona física» |
| `cuitCliente` | 11 dígitos con dígito verificador (módulo 11) | → `cuit_cliente`, `CharField(max_length=11)`, **único entre todos los clientes, activos e inactivos** (MD-48, regla 1 de COM-ALT-CLT). Se guarda sin guiones; se muestra `XX-XXXXXXXX-X`. Restricción de la base: único y `CheckConstraint` de 11 dígitos (`^\d{11}$`) |
| `razonSocialCliente` | texto, hasta 150 | → `razon_social_cliente`. Obligatoria si es persona jurídica; vacía si es física |
| `nombreCliente` | texto, hasta 80 | → `nombre_cliente`. Obligatorio si es persona física; vacío si es jurídica |
| `apellidoCliente` | texto, hasta 80 | → `apellido_cliente`. Ídem |
| `telefonoCliente` | texto, hasta 25, opcional | → `telefono_cliente`. Formato de D-21 (`core.validadores.validar_telefono`) |
| `emailCliente` | correo, opcional | → `email_cliente`, `EmailField` (254). No es único (dos sucursales pueden compartir el correo de compras). Sin correo no se pacta un suministro (regla 18 de 8.20) |
| `estadoCliente` | activo / inactivo | → `estado_cliente`. Baja lógica (regla 1 de 8.18) |

- **Restricción de la base por tipo:** `CheckConstraint` con «jurídica ⇒ razón social no vacía, nombre y apellido vacíos» y «física ⇒
  nombre y apellido no vacíos, razón social vacía». El servicio guarda solo los datos del tipo elegido y descarta los del otro, como
  hace la dirección con urbana y rural (D-39).
- `__str__`: la razón social o «Nombre Apellido» (`cliN` del prototipo). Es el texto de `referencia()` en la auditoría.
- **Alcance** (`ClienteQuerySet.en_alcance_de(actor)`, un único lugar, D-28): el Gerente y el Vendedor activos ven **todos** los
  clientes (regla 3 de COM-CNS-CLT: un cliente puede comprarle a varios Vendedores); cualquier otro rol, ninguno. El alcance de los
  **contratos y las entregas** de un cliente es otro (solo los del Vendedor) y lo trae cada tarea que los crea.

### Asociaciones

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R119 | Dirección, «tiene» | Cliente → Dirección = **0..\*** (MD-128; el modelo decía 1..\*); Dirección → Cliente = 0..1 | Tabla `DireccionCliente` en `comercial` (abajo, D-58) |
| R114 | Contrato, «corresponde» | 0..\* – 1 | La crea COM-02 (`CompraVenta`) y COM-03 (`Suministro`) |
| R116 | PagoCliente, «realiza» | 0..\* – 1 | La crea COM-06a (`PagoCliente.cliente`, D-68 punto 4) |
| R118 | Queja, «emite» | 0..\* – 1 | La crea COM-06 |

Sin herencias.

### Reglas que lo tocan

- **Regla 1 de 8.18 (baja lógica):** nace activo. Inactivo no se ofrece para contratos nuevos, pero conserva sus asociaciones.
- **Regla 2 de 8.18 (cliente inactivo):** lo da de baja **solo el Gerente** (MD-47). Sus suministros vigentes y sus compra-ventas
  abiertas siguen ejecutándose sin reactivarlo. Para contratarle algo nuevo hay que reactivarlo (COM-ALT-CLT, regla 2).
- **MD-48:** el CUIT es único en todo el sistema; un cliente dado de baja que vuelve se reactiva, no se crea otro.
- **Regla 18 de 8.20:** sin correo, el comprobante de una compra-venta se entrega impreso y no se puede pactar un suministro.
- **MD-40:** un cliente puede darse de alta sin contratos.

---

## Direccion (del cliente) y `DireccionCliente`

`Direccion`, `DireccionUrbana` y `DireccionRural` ya existen en `maestros` (MAE-01, D-39; ficha en `docs/modelo/maestros.md`): herencia
multitabla, con `localidad` (Georef, MD-88) y `estado_direccion` (activo / inactivo). Comercial **no** crea otra clase de dirección:
usa esas, con la API pública de `docs/api/direcciones.md` (D-58).

### `DireccionCliente` (R119 en el código, D-58)

No es una clase del modelo de dominio: es cómo se guarda R119 en la base de datos. La declara `comercial` porque es la app de nivel mayor
(regla A2 de D-37), igual que `TransportistaInvernadero` en `maestros` (D-55).

| Columna | Tipo | Nota |
|---|---|---|
| `id` | automático | D-06 |
| `direccion` | `OneToOneField("maestros.Direccion", on_delete=PROTECT, related_name="del_cliente")` | Una dirección es de un solo cliente (Dirección → Cliente = 0..1) |
| `cliente` | `ForeignKey(Cliente, on_delete=PROTECT, related_name="direcciones")` | Con índice (la FK lo trae) |

- **Restricción C6** ({xor} entre R096 y R119: cada dirección es de un invernadero **o** de un cliente, nunca de los dos ni de
  ninguno). La base no puede expresarla (abarca tablas de dos apps). La garantizan los servicios (D-58): `maestros` crea la dirección
  de un invernadero y nunca le agrega `DireccionCliente`; `comercial` crea **siempre** una dirección nueva para el cliente, en la misma
  transacción que su `DireccionCliente`, y nunca reutiliza una existente. Una prueba de `comercial` lo verifica.
- **Dirección usada** (regla 3 de 8.18, MD-19): una dirección que usa una compra-venta (R146) o un detalle de suministro (R125) no se
  modifica ni se borra; se crea otra con los datos corregidos y la anterior pasa a «inactiva». Quién la usa lo sabe `comercial`:
  `direcciones_en_uso(ids) -> set[int]` (en `comercial/servicios/clientes.py`). En COM-01 devuelve siempre un conjunto vacío
  (todavía no hay contratos); COM-02 (compra-ventas) y COM-03 (detalles de suministro) le suman sus consultas.
- **Dirección idéntica** (regla 6 de COM-ALT-CLT: «no dos idénticas»). Decisión de aplicación (D-58): dos direcciones **activas** del
  mismo cliente son idénticas si tienen la misma zona, la misma localidad y los mismos datos de ubicación, comparados sin distinguir
  mayúsculas y con los espacios recortados y unificados: calle, número, piso y departamento (urbana); ruta, kilómetro y lote (rural). El
  barrio y las referencias no cuentan (describen, no ubican). Es la misma clave que arma `dirAdd` del prototipo.

---

## Vehiculo

Bloque: Producción, operaciones y trazabilidad en el modelo; vive en `comercial` (D-37: `Vehiculo` y `Entrega` son de `comercial`).
Glosario: «activo logístico (tipo, marca, modelo, capacidad de carga en kilogramos) asociado a un Transportista, utilizado para
concretar entregas. Puede estar activo o inactivo, y está en ruta desde que el transportista inicia su ruta del día hasta que la
finaliza».

### Atributos

| Atributo | Valores | Nota |
|---|---|---|
| `idVehiculo` | — | El `id` automático |
| `patente` | `AAA123` o `AA123AA` | **Nuevo (MD-129).** `CharField(max_length=7)`, único entre todos los vehículos, activos e inactivos. Se guarda en mayúsculas, sin espacios ni guiones. Restricción de la base: única y `CheckConstraint` con `patente__regex=r"^([A-Z]{3}[0-9]{3}\|[A-Z]{2}[0-9]{3}[A-Z]{2})$"` |
| `tipoVehiculo` | camioneta / furgón / camión / utilitario / moto | → `tipo_vehiculo`, `TextChoices` (`camioneta`, `furgon`, `camion`, `utilitario`, `moto`), lista cerrada (MD-129) |
| `marca` | texto, hasta 50, obligatorio | Regla 2 de COM-ALT-VEH |
| `modelo` | texto, hasta 50, obligatorio | Ídem |
| `capacidadCarga` | kg, mayor que 0, hasta dos decimales | → `capacidad_carga`, `DecimalField(max_digits=8, decimal_places=2)` (hasta 999.999,99 kg). `CheckConstraint` > 0. Regla 3 de COM-ALT-VEH y regla 6 de 8.12 |
| `estadoVehiculo` | activo / inactivo | → `estado_vehiculo` |
| `enRuta` | booleano | → `en_ruta`, falso al crearse. Lo cambian COM-INI-RUT y COM-FIN-RUT (COM-06) |
| `fechaInicioRuta` | fecha | **Nuevo (MD-118).** → `fecha_inicio_ruta`, `DateField(null=True)`. Lo carga COM-INI-RUT |

- **En ruta (MD-118):** un vehículo está en ruta cuando `en_ruta` es verdadero **y** `fecha_inicio_ruta` es la fecha actual. Una ruta que
  no se finalizó deja de estar vigente al terminar el día. Método `esta_en_ruta(hoy)`; nadie lee `en_ruta` solo. `CheckConstraint`:
  `en_ruta` verdadero ⇒ `fecha_inicio_ruta` no nula.
- **Inactivo sin transportista:** `CheckConstraint` «`estado_vehiculo = activo` o `transportista` nulo» (postcondición a de COM-BAJ-VEH y
  c de COM-MOD-VEH).
- `__str__`: «Camioneta AE123CD». El texto de logística para la ficha del invernadero es «Camioneta AE123CD · 800 kg» (contrato de
  `registrar_logistica_de_transportista`, `docs/api/extensiones_de_maestros.md`).
- **Alcance:** solo el Gerente activo (COM-ALT/MOD/BAJ/CNS-VEH). `VehiculoQuerySet.en_alcance_de(actor)`.

### Asociaciones

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R073 | Transportista, «tiene» | Vehículo → Transportista = 0..1; Transportista → Vehículo = 0..1 (21ª ronda) | `transportista = OneToOneField("core.Transportista", null=True, blank=True, on_delete=PROTECT, related_name="vehiculo")`. La base garantiza que un transportista tiene a lo sumo un vehículo. Se asigna **desde el vehículo** (regla 1 de 8.22) |
| R155 (indirecta) | Invernadero | — | El vehículo **trabaja para el invernadero de su transportista** (regla 4 de COM-ALT-VEH): `vehiculo.transportista.invernadero_asignado.invernadero` (`maestros.TransportistaInvernadero`, D-55). No se guarda en el vehículo |

Sin herencias.

### Reglas que lo tocan

- **Regla 1 de 8.22 (MD-59):** el transportista de un vehículo se asigna desde el vehículo, al darlo de alta o al modificarlo.
- **Reglas 5 a 7 y 13 de 8.12:** candidatos de Planificar Entrega (COM-05); un vehículo inactivo no es candidato.
- **Regla 6 de 8.12:** la capacidad es el peso máximo del día, en un solo viaje; la carga es plantas × peso promedio por planta de su
  variedad, sin envases (glosario, «Capacidad de carga»). Con entregas, la usan COM-MOD-VEH (regla 2) y COM-CNS-VEH (regla 2): COM-05.
- **MD-118:** definición de «en ruta» (arriba).

---

## Contrato (COM-02)

Bloque: Gestión comercial. Vive en `comercial`. Clase **concreta** de la que heredan `CompraVenta` (COM-02) y `Suministro` (COM-03), con
herencia multitabla, como `OrdenTrabajo` en `produccion` (D-50). Es **hija directa de `contabilidad.OrigenDocumento`** (D-52), con
`TIPO_DE_ORIGEN = OrigenDocumento.Tipo.CONTRATO`: COM-02 suma el valor `contrato` a `OrigenDocumento.Tipo`, con su migración de `choices` en
`contabilidad`. Las nietas (`CompraVenta`, `Suministro`) heredan el tipo (convención de `docs/modelo/contabilidad.md`).

| Atributo | Valores | Nota |
|---|---|---|
| `idContrato` | — | El `id` de `OrigenDocumento` (compartido con los demás documentos: no es consecutivo) |
| (nuevo) `tipo_contrato` | `compra_venta` / `suministro` | Discriminador de la herencia (`TextChoices`), como `OrdenTrabajo.tipo`. Nunca cambia |
| (nuevo) `numero` | entero único **por tipo** | Lo asigna el servicio con una secuencia de PostgreSQL por tipo (`comercial_compraventa_numero_seq` en COM-02; la de suministros, COM-03), como `OrdenTrabajo.numero` (D-52 punto 3). Código visible: `CV-{numero:04d}` (y `SUM-{numero:04d}`). Puede tener huecos si una transacción se deshace (`docs/temas_abiertos.md`, «Huecos en el número de orden») |
| `fechaRealizacion` | fecha | → `fecha_realizacion`. La de hoy al registrar |
| (nuevo) `estado_comprobante` | enviado / pendiente de envío / para imprimir | → `estado_comprobante` (`enviado`, `pendiente_envio`, `para_imprimir`). **No está en el modelo:** resultado del envío del último comprobante del contrato (paso 16 y extensiones 16a y 16b de COM-REG-CVT; paso 15 y 15a de COM-PCT-SUM; paso 11 y 11a de COM-MOD-SUM); permite «Reenviar comprobante». Está en `Contrato` (no en cada hija) desde el lote C3, porque las dos hijas lo usan |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R114 | Cliente, «corresponde» | Contrato → Cliente = 1 | `cliente`, FK a `Cliente`, `PROTECT`, `related_name="contratos"` |
| R115 | Vendedor, «realiza» | Contrato → Vendedor = 1 | `vendedor`, FK a `core.Vendedor`, `PROTECT`, `related_name="contratos"`. Es el **responsable**; quien lo cargó queda en la auditoría (regla 1 de 8.11). Puede cambiar por un traspaso (D-60) |

- Restricciones de la base: `UniqueConstraint(tipo_contrato, numero)`.
- **Alcance** (`ContratoQuerySet.en_alcance_de(actor)`, un único lugar, D-28): el Gerente activo ve todos; el Vendedor activo, solo aquellos de
  los que es `vendedor`; cualquier otro rol, ninguno.

## CompraVenta (COM-02)

Hija de `Contrato` (`tipo_contrato = compra_venta`). Glosario: venta al contado; al registrarse queda abierta, con el stock reservado y sin
pago ni asiento (regla 19 de 8.6).

| Atributo | Valores | Nota |
|---|---|---|
| `estadoVenta` | abierta / pendiente de decisión del cliente / concretada / cancelada | → `estado_venta` (`abierta`, `pendiente_decision`, `concretada`, `cancelada`). Nace «abierta» (regla 21 de 8.6) |
| `fechaPactadaVenta` | fecha | → `fecha_pactada_venta`. Igual o posterior a la de hoy al registrar |
| `fechaConcrecionVenta` | fecha, nula | → `fecha_concrecion_venta`. La carga COM-06a (postcondición k de COM-CNC-ENT) |
| `modalidadEntrega` | retiro en invernadero / envío a domicilio | → `modalidad_entrega` (`retiro`, `envio`) |
| `montoTotal` | derivado | No se guarda: Σ subtotal de los detalles (sobre la cantidad entregada; mientras no hay entrega, el «monto estimado» usa la solicitada) |
| `motivoCancelacionVenta` (MD-130) | el cliente desistió / el cliente no retiró / otro, nulo | → `motivo_cancelacion_venta` (`cliente_desistio`, `cliente_no_retiro`, `otro`). Lo carga COM-CNL-CVT (**COM-05b**, con su migración). Nulo en toda venta que no se canceló con COM-CNL-CVT (una venta que queda «cancelada» porque el cliente rechazó todo en COM-DCD-FLT no lo tiene) |
| `descripcionCancelacion` (MD-130) | texto, opcional | → `descripcion_cancelacion`. Hasta 300 caracteres, sin espacios al borde; vacío si no se indicó (también con «otro»: el caso de uso la deja opcional) |
| `fechaCancelacionVenta` (MD-130) | fecha, nula | → `fecha_cancelacion_venta`. La de hoy al cancelar con COM-CNL-CVT |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R146 | Dirección, «se envía a» | 0..1 | `direccion_envio`, FK a `maestros.Direccion`, nula, `PROTECT`. Solo con envío, y **tiene que ser una dirección activa del cliente** (regla 23 de 8.6; D-58): la base no puede verificarlo entre dos apps, lo verifica el servicio y una prueba |
| R151 | Invernadero, «se retira en» | 0..1 | `invernadero_retiro`, FK a `maestros.Invernadero`, nula, `PROTECT`. Solo con retiro; uno de los invernaderos activos del Vendedor |
| R113 | DetalleVenta, composición | 1..\* | Por `DetalleVenta.compra_venta` |
| R117 | PagoCliente | 0..1 | La crea COM-06a al concretar la última entrega (`PagoCliente.compra_venta`, D-68 punto 4) |

- Restricción de la base: `CheckConstraint` «envío ⇒ dirección no nula e invernadero nulo; retiro ⇒ invernadero no nulo y dirección nula».
- **(COM-05b, MD-130)** `motivo_cancelacion_venta` no nulo ⇔ `fecha_cancelacion_venta` no nula; motivo no nulo ⇒ `estado_venta` en
  (`cancelada`, `concretada`) (la segunda, cuando COM-08b cobre lo entregado, extensión 6a); `descripcion_cancelacion` no vacía ⇒ motivo no
  nulo.

## DetalleVenta (COM-02)

| Atributo | Valores | Nota |
|---|---|---|
| `idDetalleVenta` | — | El `id` automático |
| `cantSolicitadaVenta` | entero ≥ 1 | → `cant_solicitada_venta`. **No se modifica** (regla 20 de 8.6) |
| `precioUnitarioDeVenta` | pesos > 0, dos decimales | → `precio_unitario_de_venta`, `DecimalField(max_digits=12, decimal_places=2)` |
| `cantEntregadaVenta` | entero ≥ 0, nulo | → `cant_entregada_venta`. Nulo hasta que se fija: al **aceptar un faltante**, la cantidad disponible (regla 16 de 8.6, postcondición g de COM-DCD-FLT, COM-04); en la entrega, lo que llegó (regla 27 de 8.6, COM-06) |
| `estadoDetalleVenta` | abierto / pendiente de decisión del cliente / confirmado / rechazado / cancelado | → `estado_detalle_venta` (`abierto`, `pendiente_decision`, `confirmado`, `rechazado`, `cancelado`; el último por MD-130). Nace «abierto» |
| `fechaPendienteDecision` | fecha, nula | → `fecha_pendiente_decision`. La carga COM-04 cada vez que el detalle pasa a pendiente o suma faltante (13a de PROD-CNC-CSC, 10c de PROD-REG-MRM, 8c y 8d de PROD-CNL-ORD, 3a.2a de PROD-VNC-CAM). Se conserva como historia cuando deja de estar pendiente |
| `subtotal` | derivado | No se guarda: cantidad entregada (o solicitada, para el estimado) × precio |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R113 | Compra-venta, composición | 1 | `compra_venta`, FK a `CompraVenta`, `PROTECT`, `related_name="detalles"` |
| R127 | Variedad, «corresponde» | 1 | `variedad`, FK a `maestros.Variedad`, `PROTECT` |
| R123 | ReservaStock, composición | 1..\* | Por `ReservaStock.detalle_venta` |
| R147 | DetalleEntrega | 0..\* | La crea COM-05a1 (`DetalleEntrega.detalle_venta`, D-66) |

- Restricciones de la base: `UniqueConstraint(compra_venta, variedad)` (una variedad por venta, regla 2 de 8.11); `cant_solicitada_venta >=
  1`; `precio_unitario_de_venta > 0`; `cant_entregada_venta` nula o `>= 0`.

## ReservaStock (COM-02)

Producto apartado para un detalle de contrato (o para una cosecha manual sin contrato, COM-04). Vive en `comercial` (D-37, D-59).

| Atributo | Valores | Nota |
|---|---|---|
| `idReserva` | — | El `id` automático |
| `fecha` | fecha | → `fecha_reserva`. La de hoy al crearla |
| `fechaEntregaReserva` | fecha, nula | → `fecha_entrega_reserva`. En una compra-venta, la pactada; en un suministro, la del período; **nula solo en la reserva de una cosecha sin contrato** (postcondición f de PROD-PNF-CSC; D-64 punto 6, corrige C2). Nunca cambia: conserva la fecha prometida (regla 12 de 8.8) |
| `estado` | activa / lista para entrega / entregada / liberada | → `estado_reserva` (`activa`, `lista_para_entrega`, `entregada`, `liberada`). Estado inicial: regla 12 de 8.6 |
| `totalReservado` | derivado | Σ `cantidad_reservada` de sus líneas |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R123 | DetalleVenta | 0..1 | `detalle_venta`, FK a `DetalleVenta`, nula, `PROTECT`, `related_name="reservas"` |
| R124 | DetalleSuministro | 0..1 | `detalle_suministro`, FK a `DetalleSuministro`, nula, `PROTECT`, `related_name="reservas"` (COM-03). La reserva de un período lleva el detalle y `fecha_entrega_reserva` = la fecha del período |
| R087 | Cosecha, «tiene» | ReservaStock → Cosecha = 0..1; Cosecha → ReservaStock = 1 | `cosecha`, `OneToOneField("produccion.Cosecha")`, nula, `PROTECT`, `related_name="reserva"`. Declarada en `comercial` (A2, D-59). «Toda cosecha tiene una reserva» lo garantiza el servicio que la crea |
| R141 | DetalleReserva, composición | 1..\* | Por `DetalleReserva.reserva` |
| — (nuevo) | Invernadero | 1 | `invernadero`, FK a `maestros.Invernadero`, `PROTECT`. **No está en el modelo como asociación**: es la regla «una reserva toma todo su stock de un único invernadero» (regla 1 de 8.8) guardada, para consultar y bloquear sin recorrer las líneas. Lo verifica una prueba de invariantes (todas las líneas son de lotes o partidas de ese invernadero) |

- **C3** (a lo sumo uno de R123 y R124): `CheckConstraint` «no los dos a la vez» (COM-03, con la migración que agrega
  `detalle_suministro`). Ninguno de los dos: la reserva de una cosecha manual sin contrato (COM-04).
- **Reserva sin contrato** (COM-04, con su migración): `CheckConstraint` «`fecha_entrega_reserva` nula ⇔ `detalle_venta` y
  `detalle_suministro` nulos». Una reserva sin contrato siempre tiene cosecha (la crea PROD-PNF-CSC) y pasa a «liberada» al concretarse
  (regla 18 de 8.6).
- La reserva no tiene «variedad» propia: es la del detalle (o la de su cosecha, en una cosecha sin contrato).

## DetalleReserva (COM-02)

Línea de una reserva: de qué origen físico sale una parte (un lote en pie o una partida de cámara).

| Atributo | Valores | Nota |
|---|---|---|
| `idDetalleReserva` | — | El `id` automático |
| `cantidadReservada` | entero ≥ 1 | → `cantidad_reservada` |
| `cantidadCosechada` | entero ≥ 0, nulo | → `cantidad_cosechada`. Solo en líneas de lote; vacío = todavía no se cosechó; un número, incluido 0, es lo que rindió (lo carga COM-04 al concretar; una cosecha cancelada deja sus líneas vacías) |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R141 | ReservaStock, composición | 1 | `reserva`, FK a `ReservaStock`, `PROTECT`, `related_name="lineas"` |
| R142 | Lote, «aporta a» | 0..1 | `lote`, FK a `produccion.Lote`, nula, `PROTECT`, `related_name="lineas_de_reserva"` |
| R143 | StockCosechado, «aporta a» | 0..1 | `partida`, FK a `produccion.StockCosechado`, nula, `PROTECT`, `related_name="lineas_de_reserva"` |

- Restricciones de la base: **C1** (`CheckConstraint`: exactamente uno de `lote` y `partida`); `cantidad_reservada >= 1`, **salvo en una línea
  de partida, que admite 0** (D-64 punto 7, corrige C2: el recorte de la merma en cámara, regla 6 de 8.9; la línea recortada a 0 se conserva
  y no suma); `cantidad_cosechada` nula o `>= 0`; con `partida`, `cantidad_cosechada` nula. COM-02 crea la restricción ya así.

### Lo que se calcula de las reservas (no se guarda; `docs/patrones/stock_maduro.md`)

| Dato | Cálculo |
|---|---|
| Stock libre de un lote (regla 9 de 8.6) | `cantidad_actual` − Σ `cantidad_reservada` de sus líneas con reserva «activa». Nunca menor que 0 (regla 15 de 8.8) |
| Stock libre de una partida (regla 10 de 8.6) | `cantidad_disponible_cosechado` − Σ `cantidad_reservada` de sus líneas con reserva «activa» o «lista para entrega» |
| Cantidad cubierta de una línea (regla 9 de 8.8) | Lote sin cosechar: la reservada; lote cosechado: `min(cosechada, reservada)`; partida: la reservada |
| Cantidad sin cubrir de un detalle (regla 10 de 8.8) | Cantidad pedida − Σ cantidad cubierta de las líneas de sus reservas no liberadas; un detalle confirmado, rechazado o cancelado no tiene |
| Stock maduro libre de una variedad (regla 11 de 8.6) | Ver el patrón: lotes elegibles + partidas elegibles para una fecha de entrega |

### Reglas que tocan a estas clases (numeración global de cada sección)

El documento de Drive reinicia la numeración en cada subtítulo de 8.6 y 8.8. Los casos de uso citan la numeración global, que es la que se
usa en el código: en 8.6, C1 a C4 son las reglas 1 a 4; «Reserva y asignación de stock» son la 5 a la 12; «Cosecha y faltantes», 13 a 18;
«Compra-venta al contado», 19 a 27; «Stock en cámara», 28 a 31; «Contabilidad», 32 a 34. En 8.8: «Alcance», 1 a 6; «Planificación de cosecha»,
7 a 15; «Planificación automática», 16 y 17; «Envasado», 18 a 23; «Reservas de insumo y retiro», 24 y 25.

- **8.6:** 5 (una o más reservas por detalle), 6 (toda cosecha tiene una reserva), 7 (prioridad de asignación), 9 a 11 (stock libre y stock
  maduro libre), 12 (estado inicial), 19 a 23 (compra-venta al contado, estados, dirección de envío).
- **8.8:** 1 (una reserva, un invernadero), 2 (una cosecha, una variedad y un invernadero), 9 y 10 (cantidad cubierta y sin cubrir), 11
  (validación de vencimiento), 14 (planificar no descuenta), 15 (alerta por merma).
- **8.11:** 1 (Vendedor responsable), 2 (stock suficiente y sin variedades repetidas), 3 (cosechas automáticas).
- **8.20:** 2 y 3 (fecha de entrada a Maduración y fecha máxima de cosecha), 18 (cliente sin correo).

---

## Suministro (COM-03)

Hija de `Contrato` (`tipo_contrato = suministro`). Glosario: contrato de entregas periódicas a un cliente, con cláusulas resolutorias. Se
firma fuera del sistema y el Vendedor lo carga tal como figura (nota de la ficha, 10ª ronda). Código visible: `SUM-{numero:04d}`, con la
secuencia `comercial_suministro_numero_seq`.

| Atributo | Valores | Nota |
|---|---|---|
| `duracion` | entero, meses | → `duracion_meses`, de 1 a 120 (regla «Datos del contrato» de COM-PCT-SUM) |
| `estadoSuministro` | vigente / finalizado / resuelto / **rescindido** | → `estado_suministro` (`vigente`, `finalizado`, `resuelto`, `rescindido`). Nace «vigente» (regla 5 de 8.11). «Rescindido» es nuevo (COM-RSC-SUM; propuesta MD-140 en «Pendientes de MD») |
| `fechaFin` | derivado | → `fecha_fin`, **guardado**: `sumar_meses(fecha_realizacion, duracion_meses)` (regla «Fecha de fin»: mismo día del mes, o el último si no existe). Se guarda porque las consultas y la pre-reserva filtran por él; lo recalcula solo el servicio, al pactar y al cambiar la duración, y lo verifica una prueba de invariantes |
| `cantMaxIncumplimiento` | entero | → `incumplimientos_tolerados`, de **0** a 99 (PCU 16: con 0, el primer incumplimiento aceptado resuelve el contrato) |
| `multaResolucion` | pesos | → `multa_resolucion`, `DecimalField(10, 2)`, de 0 a 99.999.999,99 |
| `cantIncumplimientos` | entero | → `cantidad_incumplimientos`, nace en 0 (regla 6 de 8.11). Suma 1 por cada solicitud aceptada y resta 1 al anular una aceptada (COM-07a; D-69, punto 5). Invariante: igual a la cantidad de solicitudes aceptadas de las entregas del contrato |
| (MD-140) `motivoRescision` | a pedido del cliente / a pedido de la empresa / otro | → `motivo_rescision` (`a_pedido_del_cliente`, `a_pedido_de_la_empresa`, `otro`), nulo |
| (MD-140) `descripcionRescision` | texto, hasta 500 | → `descripcion_rescision`, vacío por defecto; obligatoria con `otro` (la verifica el servicio) |
| (MD-140) `fechaAcuerdoRescision` | fecha, nula | → `fecha_acuerdo_rescision`: el día en que las partes la acordaron (igual o anterior al registro) |
| (MD-140) `fechaRegistroRescision` | fecha, nula | → `fecha_registro_rescision`: el día en que el Gerente la registró |
| (MD-140) `fechaUltimaEntregaRescision` | fecha, nula | → `fecha_ultima_entrega_rescision`: la última entrega conservada (regla «Períodos que se conservan» de COM-RSC-SUM) |
| (MD-140) `fechaRescision` | fecha, nula | → `fecha_rescision`: cuando pasó a «rescindido» (la de la última entrega conservada, o la del registro si no había ninguna) |
| — | `fecha_resolucion_suministro` | **MD-120.** Fecha, nula. La carga COM-07b (COM-RSV-SUM); se crea ya en COM-03 para que la ficha la muestre y no haga falta otra migración |
| (código) | `solicitud_resolucion` | **D-69, punto 5. No está en el modelo.** FK nula a `SolicitudRevision`, `PROTECT`, `related_name="+"`: la solicitud aceptada cuya aceptación provocó la resolución (la de `fecha_resolucion` más reciente del contrato). La crea COM-07a (para la extensión 2a de COM-ANL-SRV) y la carga COM-07b junto con `fecha_resolucion_suministro` |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R112 | DetalleSuministro, composición | 1..\* | Por `DetalleSuministro.suministro` |
| (MD-124) | ClausulaSuministrado, composición | 1 | Por `ClausulaSuministrado.suministro` (`OneToOne`) |
| MD-122 | Alerta, «avisa» | 0..\* | Por `AlertaComercial.suministro` |

- Restricciones de la base: `duracion_meses` entre 1 y 120; `incumplimientos_tolerados` entre 0 y 99; `multa_resolucion >= 0`;
  `cantidad_incumplimientos >= 0`; `estado = resuelto ⇔ fecha_resolucion_suministro no nula`; `solicitud_resolucion` no nula ⇒ `estado = resuelto` (COM-07a); `estado = rescindido ⇔ fecha_rescision no
  nula`; **rescisión acordada** (`motivo_rescision` no nulo) `⇔` `fecha_acuerdo_rescision`, `fecha_registro_rescision` y
  `fecha_ultima_entrega_rescision` no nulas; `fecha_acuerdo_rescision <= fecha_registro_rescision`; `rescindido ⇒ rescisión acordada`.
- **Rescisión acordada** = `motivo_rescision` no nulo con el estado «vigente»: el contrato todavía entrega los períodos conservados
  (COM-RSC-SUM). Dejarla sin efecto (COM-ANL-RSC) vuelve los seis campos a nulo/vacío; la historia queda en la auditoría.
- «Resuelto cuando cantIncumplimientos **supera** cantMaxIncumplimiento» (regla 5 de 8.11): con 3 tolerados, el cuarto lo resuelve.
  Por eso, al modificar, los tolerados nuevos pueden ser **iguales** a los acumulados (PCU 16; «Diferencias», fila 6).
- El correo del cliente es obligatorio para pactar (regla 18 de 8.20): lo verifica el servicio.
- `estado_comprobante` lo hereda de `Contrato` (se mudó ahí en el lote C3: ver la ficha de `Contrato`).

## DetalleSuministro (COM-03)

Una variedad que se entrega periódicamente en una dirección del cliente. El calendario no se guarda: se calcula (regla «Calendario de
entregas»). Un **período** es un par (detalle, fecha del calendario); no es una clase.

| Atributo | Valores | Nota |
|---|---|---|
| `idDetalleSuministro` | — | El `id` automático |
| `periodoEntrega` | entero, días | → `periodo_entrega_dias`, de 1 a 365 |
| `fechaPrimerEntrega` | fecha | → `fecha_primer_entrega`. Entre hoy y la fecha de fin del contrato al pactar (regla 4 de 8.11) |
| `cantEntrega` | entero, plantas | → `cantidad_por_periodo`, de 1 a 500.000 |
| `mecanismoPrecio` | fijo / ajuste periódico | → `mecanismo_precio` (`fijo`, `ajuste_periodico`) |
| `estadoDetalleSuministro` | vigente / finalizado / resuelto | → `estado_detalle_suministro` |
| `precioUnitarioSuministro` | pesos | → `precio_unitario_suministro`, `DecimalField(9, 2)`, de 0,01 a 9.999.999,99. Precio **inicial** |
| `porcAjuste` | porcentaje, nulo | → `porcentaje_ajuste`, `DecimalField(5, 2)`, de 0,01 a 100; solo con ajuste periódico |
| `mesesAjuste` | entero, nulo | → `meses_ajuste`, de 1 a 60; solo con ajuste periódico |
| `fechaFinDetalle` | fecha, nula | **MD-131.** → `fecha_fin_detalle`: la del último período que se entrega; nula mientras rige hasta el fin del contrato |
| (nuevo) `fecha_base_ajuste` | fecha | **No está en el modelo.** Desde cuándo se cuentan los meses del ajuste: la fecha de realización del contrato en un detalle pactado con COM-PCT-SUM; la fecha de primera entrega en uno creado por COM-MOD-SUM (sucesor, regla «Precio con ajuste periódico en el detalle nuevo»; y agregado, decisión de aplicación: ver `suministro.md`). Se guarda para no deducirlo del origen del detalle |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R112 | Suministro, «tiene» | 1 | `suministro`, FK a `Suministro`, `PROTECT`, `related_name="detalles"` |
| R125 | Dirección, «tiene» | 1 | `direccion`, FK a `maestros.Direccion`, `PROTECT`. **Una dirección del cliente del contrato** (activa al pactar o al agregar el detalle): la verifica el servicio (como `CompraVenta.direccion_envio`, D-58) |
| R126 | Variedad, «corresponde» | 1 | `variedad`, FK a `maestros.Variedad`, `PROTECT` |
| MD-131 | DetalleSuministro, «reemplaza a» | 0..1 en los dos sentidos | `reemplaza_a`, `OneToOneField("self")`, nulo, `PROTECT`, `related_name="sucesor"` |
| (MD-124) | ClausulaSuministrante, composición | 1 | Por `ClausulaSuministrante.detalle` (`OneToOne`) |
| R124 | ReservaStock | 0..\* | Por `ReservaStock.detalle_suministro` (lo agrega COM-03) |
| MD-133 | Alerta, «avisa» | 0..\* | Por `AlertaComercial.detalle_suministro` |
| R121 | DetalleEntrega | 0..\* | La crea COM-05a1 (`DetalleEntrega.detalle_suministro` con `fecha_periodo`, D-66) |

- Restricciones de la base:
  - los rangos de la tabla;
  - **mecanismo**: `fijo ⇒ porcentaje_ajuste y meses_ajuste nulos`; `ajuste_periodico ⇒ los dos no nulos`;
  - **par (variedad, dirección)** (regla «Dirección y modalidad»; MD-131): `UniqueConstraint(suministro, variedad, direccion,
    condition=Q(estado_detalle_suministro="vigente"))`. Los finalizados no cuentan;
  - no hay restricción de la base entre el estado y `fecha_fin_detalle` (depende de otra tabla). Invariantes que verifica una prueba: un
    detalle finalizado la tiene; un detalle vigente la tiene **solo** si su suministro tiene una rescisión acordada (COM-RSC-SUM).
- **Período de un detalle** (`calendario(detalle)`): `fecha_primer_entrega + k × periodo_entrega_dias`, k = 0, 1, 2…, mientras no supere
  `fecha_fin_detalle` (si tiene) ni `suministro.fecha_fin`. Una función, en `comercial/servicios/calendario.py`.
- **Precio de un período** (regla 7 de 8.11): `fijo` → el inicial; `ajuste_periodico` → `inicial × (1 + porcentaje / 100) ^ ajustes`,
  `ajustes = meses_transcurridos(fecha_base_ajuste, fecha del período) // meses_ajuste`, redondeado a 2 decimales (`ROUND_HALF_UP`) y
  siempre desde el inicial. Lo guarda COM-05a1 en el `DetalleEntrega` (`precio_unitario`, con la fecha programada).

## ClausulaSuministrado y ClausulaSuministrante (COM-03)

`ClausulaResolutoria` es la clase padre sin atributos: en el código es una **clase abstracta** de Django (no tiene tabla), porque una tabla
padre vacía no agrega nada y cada hija tiene un solo dueño.

| Clase | Atributo | Valores | En el código |
|---|---|---|---|
| ClausulaSuministrado (una por **contrato**, MD-124) | `plazoPago` | días | → `plazo_pago_dias`, de 0 a 365 |
| | `indemnizacionRetrasoPago` | pesos por día | → `indemnizacion_retraso_pago`, `DecimalField(9, 2)`, de 0 a 9.999.999,99 |
| | (composición) | 1 | `suministro`, `OneToOneField(Suministro)`, `PROTECT`, `related_name="clausula_suministrado"` |
| ClausulaSuministrante (una por **detalle**) | `plazoEntrega` | días de tolerancia | → `plazo_entrega_dias`, de 0 a 365 |
| | `indemnizacionRetrasoEntrega` | pesos por día | → `indemnizacion_retraso_entrega`, `DecimalField(9, 2)`, de 0 a 9.999.999,99 |
| | `cantMinMercaderia` | plantas | → `cantidad_minima`, de 1 a la cantidad por período del detalle (la cota superior la verifica el servicio: está en otra tabla) |
| | `indemnizacionMercaderia` | pesos por planta | → `indemnizacion_faltante`, `DecimalField(9, 2)`, de 0 a 9.999.999,99 |
| | (composición) | 1 | `detalle`, `OneToOneField(DetalleSuministro)`, `PROTECT`, `related_name="clausula_suministrante"` |

- Las indemnizaciones no se ajustan con el precio (regla 7 de 8.11).
- Un cambio de la cláusula del suministrado (COM-MOD-SUM) **actualiza** la fila: el vencimiento de cada entrega se fija al concretarla
  (MD-132), así que no hace falta historial. Un cambio de la cláusula del suministrante crea el detalle sucesor con su cláusula nueva.

## AlertaComercial (COM-03, D-63)

Tabla de vínculo entre una alerta de `maestros` y su origen comercial (T-01). No es una clase del modelo: es cómo el código guarda las
asociaciones «avisa» de MD-122, MD-133 y MD-134 (regla A2 de D-37).

| Campo | Valores | Nota |
|---|---|---|
| `alerta` | `OneToOneField("maestros.Alerta")`, `PROTECT`, `related_name="vinculo_comercial"` | |
| `suministro` | FK a `Suministro`, nula, `PROTECT` | MD-122 («suministro resuelto», COM-07b; D-69, punto 14) |
| `detalle_suministro` | FK a `DetalleSuministro`, nula, `PROTECT` | MD-133 («período sin cobertura completa») |
| `fecha_periodo` | fecha, nula | El período de la alerta MD-133 |
| `cantidad_sin_cubrir` | entero, nulo | Lo que falta, actualizado en cada intento de la pre-reserva (D-63, punto 3) |
| `partida` (COM-04) | FK a `produccion.StockCosechado`, nula, `PROTECT` | MD-134 («partida por vencer», D-64 punto 10). COM-06a la usa también para «partida vencida en una entrega en curso» (PROD-VNC-CAM 3b) |
| `entrega` (COM-05a1) | FK a `Entrega`, nula, `PROTECT` | MD-122 y extensión 6a de COM-PNF-ENT («entrega sin transportista», D-66 punto 10). COM-06b la usa para «entrega no reconocida por el cliente»; COM-08a, para «pago en mora» (`comercial_pago_en_mora`, D-94 punto 6) |
| `solicitud` (COM-06a) | FK a `SolicitudRevision`, nula, `PROTECT`, `related_name="alertas"` | R054 (la alerta de una discrepancia, COM-06a, o de una queja, COM-06b). Una sola por solicitud: único `(solicitud)` con `solicitud` no nula |
| `resultado_averiguacion` (COM-06b) | `llego` / `no_llego_perdido` / `no_llego_devuelto`, nulo | **MD-137.** Solo en la alerta «entrega no reconocida»; lo carga COM-ATN-ENR al resolverla (D-68, punto 9) |
| `descripcion_averiguacion` (COM-06b) | texto, vacío | Obligatoria con resultado (de 1 a 500, sin espacios al borde) |

- Restricciones de la base: exactamente una de las FK de origen no nula (en COM-03, `suministro` o `detalle_suministro`);
  `detalle_suministro no nulo ⇔ fecha_periodo y cantidad_sin_cubrir no nulos`. COM-04 suma `partida` y reescribe «exactamente una» con las
  tres; COM-05a1 (`entrega`) la reescribe con cuatro, y COM-06a (`solicitud`) hace lo mismo con cinco. COM-06b suma: `resultado_averiguacion`
  no nulo ⇔ `descripcion_averiguacion` no vacía; resultado no nulo ⇒ `entrega` no nula.
- La alerta de merma en cámara con producto reservado **no** va acá: su origen es la merma (R089), y el vínculo ya existe en
  `produccion.AlertaDeMerma` (D-64 punto 10).

## EnlaceCliente (COM-04, D-65)

Enlace de acceso temporal de un cliente, sin cuenta. **No es una clase del modelo** (el modelo lo describe con `fechaPendienteDecision` y
`diasVigenciaEnlaceFaltante`): es cómo el código cumple «uso único», «vencimiento» y «reemplazo» (`docs/patrones/enlace_del_cliente.md`).

| Campo | Valores | Nota |
|---|---|---|
| `tipo` | `decision_faltante` / `confirmacion_entrega` | El segundo lo suma COM-06b (D-68, punto 1) |
| `cliente` | FK a `Cliente`, `PROTECT`, `related_name="enlaces"` | |
| `compra_venta` | FK a `CompraVenta`, nula, `PROTECT`, `related_name="enlaces"` | Obligatoria en `decision_faltante` (restricción) |
| `entrega` (COM-06b) | FK a `Entrega`, nula, `PROTECT`, `related_name="enlaces"` | Obligatoria en `confirmacion_entrega` (restricción); nula en `decision_faltante` |
| `token_resumen` | texto de 64 caracteres, **único** | SHA-256 del token. El token no se guarda |
| `fecha_creacion` | fecha y hora | |
| `fecha_vencimiento` | fecha, nula (COM-06b) | Sirve hasta el final de ese día. Faltante: la `fecha_pendiente_decision` más reciente de los detalles pendientes + `dias_vigencia_enlace_faltante`. **Confirmación: nula**, la vigencia se calcula al abrir y al registrar con `entrega.fecha_resolucion_orden + dias_vigencia_enlace_confirmacion` (regla «Enlace de confirmación» de COM-CNF-ENT: si cambia el parámetro, cambia la de los ya enviados; D-68, punto 8) |
| `estado` | `vigente` / `usado` / `reemplazado` / `anulado` / `vencido` | Nace `vigente` |
| `fecha_uso` | fecha y hora, nula | Con `usado` |
| `estado_envio` | `enviado` / `pendiente_envio` | Resultado del correo (D-65 punto 6). Nulo hasta el intento. Un cliente sin correo no tiene enlace |

- Restricciones de la base: `UniqueConstraint(token_resumen)`; índice parcial único «a lo sumo un `vigente` por (`compra_venta`, `tipo`)»;
  `estado = usado` ⇔ `fecha_uso` no nula; `tipo = decision_faltante` ⇒ `compra_venta` no nula. **COM-06b suma:** `tipo =
  confirmacion_entrega` ⇔ `entrega` no nula y `compra_venta` nula; `tipo = decision_faltante` ⇔ `fecha_vencimiento` no nula; único
  `(entrega)` con `tipo = confirmacion_entrega` (uno por entrega, sin reemplazo: regla «Enlace de confirmación»).
- Auditoría: el enlace no se audita por su cuenta; el caso de uso que lo crea o lo usa lo pone en su registro (D-36). Al cliente se lo
  registra como origen «cliente mediante enlace» (COM-DCD-FLT, postcondición f).

## Entrega (COM-05a1, D-66)

Bloque: Gestión comercial. Vive en `comercial` (D-37). **Hija multitabla de `produccion.OrdenTrabajo`** (`tipo_orden = entrega`; D-50, D-66
punto 2), sin `ConCapataz` (D-53): la entrega no tiene Capataz. Glosario: la entrega del producto al cliente, con envío (con Transportista) o
con retiro en el invernadero (sin Transportista; la concreta el Vendedor). Sale de un único invernadero (regla 3 de 8.8) y la planifica
siempre InfoPonia (regla 1 de 8.12).

Lo que hereda de `OrdenTrabajo` (`docs/modelo/produccion.md`) y cómo lo usa una entrega:

| Atributo heredado | En una entrega |
|---|---|
| `invernadero` | El **invernadero de origen**: el de las reservas que entrega (regla 3 de 8.8; `ReservaStock.invernadero`) |
| `fecha_creacion_orden` | La de hoy al planificarla |
| `fecha_programada_orden` | La fecha prometida (la pactada de la venta o la del período) o, si ya pasó, hoy (regla 3 de 8.12). Solo cambia si una búsqueda de transportista la pasa a hoy (extensión 1b de COM-PNF-ENT; COM-ASG-TRP) |
| `fecha_resolucion_orden` | Nula «a realizar»; la de hoy al concretarla (COM-06) o cancelarla (MD-119) |
| `estado_orden` | `a_realizar` → `concretada` (COM-06) o `cancelada` (regla 14 de 8.12) |
| `agronomo` | **Siempre nulo**: la planifica InfoPonia (postcondición a de COM-PNF-ENT). Quien planifica el envasado queda en la auditoría (regla «Planificador de la entrega» de PROD-PNF-ENV) |
| `prioridad_orden`, `descripcion_orden` | Nulas / vacía (ningún caso de uso las usa en una entrega) |
| `motivo_cancelacion` | El que pasa el caso de uso que la cancela (punto 9 de D-66) |
| `numero`, `codigo` | Como toda orden: `OT-0231` (D-52, punto 3). Es el código que muestran las pantallas, los avisos y los correos |

| Atributo propio | Valores | Nota |
|---|---|---|
| (código) `contrato` | FK a `Contrato`, `PROTECT`, `related_name="entregas"` | **No está en el modelo** (se deduce de los detalles). Lo guarda D-66 punto 3: una entrega es de un solo contrato (regla «Alcance de una entrega») |
| (código) `modalidad_entrega` | `envio` / `retiro` | La de la compra-venta; un suministro siempre es `envio`. Misma lista que `CompraVenta.modalidad_entrega` |
| (código) `direccion_destino` | FK a `maestros.Direccion`, nula, `PROTECT` | Con envío: la dirección de envío de la venta (R146) o la del detalle de suministro (R125). Con retiro: nula (el destino es el invernadero de origen, R151) |
| R122 `transportista` | FK a `core.Transportista`, nula, `PROTECT`, `related_name="entregas"` | Solo con envío. Nulo mientras no se consigue uno (regla 10 de 8.12) |
| `estadoConfirmacionCliente` | `no_confirmado` / `confirmado`, nulo | → `estado_confirmacion_cliente`. **Solo en una entrega de suministro**, que nace `no_confirmado` (regla 15 de 8.12); nulo en una de compra-venta. Lo cambia COM-CNF-ENT (COM-06) |
| (código) `estado_aviso_cliente` | `enviado` / `pendiente_envio` / `sin_correo` | **No está en el modelo** (como `Contrato.estado_comprobante`): el resultado del último correo al cliente de esta entrega (D-66, punto 12). Nulo hasta el primer intento |
| (código) `recordatorio_para` | fecha, nula | La fecha programada por la que ya salió el recordatorio único «sigue sin transportista» (postcondición k; D-66, punto 6) |
| (código) `aviso_atrasada_para` | fecha, nula | La fecha programada por la que ya salió el aviso único de entrega atrasada con transportista (PCU, sección 8; D-66, punto 6) |
| `montoTotalEntrega` (COM-06a) | pesos ≥ 0, nulo | → `monto_total_entrega`, `DecimalField(14, 2)`. Nulo hasta concretar; Σ `monto_pagar` de las líneas (regla «Precio y montos» de COM-CNC-ENT) |
| `fechaVencimientoPago` (COM-06a) | fecha, nula | → `fecha_vencimiento_pago`. **Se guarda al concretar** (MD-132): `fecha_resolucion_orden + plazo_pago_dias` de la cláusula del suministrado **del contrato** (MD-124). Solo en un suministro; nula en una compra-venta |
| `montoACobrar`, `estadoPagoEntrega` | derivados | No se guardan (`comercial/servicios/entregas.py`, D-68 punto 7). Monto a cobrar = total − Σ **`monto_descontado`** de las solicitudes aceptadas de la entrega, nunca negativo (MD-115; D-69 punto 9, que corrige «Σ indemnizaciones» de D-68 punto 7: con el tope, una parte se reintegra; ninguna hasta COM-07a). Estado de pago (COM-08a, D-94 punto 4): **pagada** si tiene una `LineaPago` vigente o si su monto a cobrar es 0 (saldada, MD-125); si no, **en mora** si `hoy > fecha_vencimiento_pago` y **pendiente** en otro caso (MD-136, MD-139). Hasta COM-08a, nunca «pagada» y sin alerta |
| (código, COM-08a) `fecha_aviso_mora` | fecha, nula | **D-94, punto 5. No está en el modelo.** La fecha en que la entrega entró en mora por primera vez y se avisó (alerta, Vendedor, cliente). La carga `reevaluar_mora`; no vuelve a nula (así el correo de mora sale una sola vez) |
| (código, COM-08a) `estado_aviso_mora` | `enviado` / `pendiente_envio` / `sin_correo`, nulo | Ídem. El resultado del correo de mora al cliente; el paso 30 reintenta los `pendiente_envio` (regla 4 de COM-VNC-PAG). Separado de `estado_aviso_cliente`, que es el del último correo de la entrega |
| (código, COM-08a) `indemnizacion_retraso_dia` | pesos por día ≥ 0, `DecimalField(9, 2)`, nulo | La indemnización por día de la cláusula del suministrado vigente al vencer (D-94, punto 12). La copia `concretar_entrega`; `modificar_suministro` la actualiza solo si `fecha_vencimiento_pago >= hoy`. Nula en una compra-venta |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R120 | DetalleEntrega, composición | 1..\* | Por `DetalleEntrega.entrega` |
| R122 | Transportista, «realiza» | Entrega → Transportista = 0..1 | `transportista` (arriba) |
| R138 | ReservaInsumo (envases), composición | 0..\* | Heredada de `OrdenTrabajo` (`produccion`); las crea PROD-PNF-ENV |
| R084, R148 | Merma, Consumo | 0..\* / 0..\* | `Merma.orden` y `Consumo.orden` en `produccion` (los crea COM-04a; los escribe COM-06a con el núcleo de `docs/api/produccion.md`, sección 10; D-68 punto 3) |
| R154 | PagoCliente, «cancela» | Entrega → PagoCliente = 0..\* (a lo sumo uno vigente) | **`LineaPago`** (COM-08a; D-94, punto 2), no `Entrega.pago`: una entrega conserva el pago anulado y recibe el correcto (MD-136). Solo en un suministro |
| (código) | IntentoFallido | 0..\* | `IntentoFallido.entrega` (COM-06a, D-68 punto 6) |
| MD-122 | Alerta, «avisa» | 0..\* | Por `AlertaComercial.entrega` |

- Restricciones de la base:
  - `modalidad_entrega = envio` ⇔ `direccion_destino` no nula;
  - `modalidad_entrega = retiro` ⇒ `transportista` nulo (regla 25 de 8.8);
  - `aviso_atrasada_para` no nula ⇒ `transportista` no nulo.
  - (COM-08a) `estado_aviso_mora` no nulo ⇒ `fecha_aviso_mora` no nula. Que solo una entrega de suministro concretada tenga `fecha_aviso_mora` lo
    verifica `verificar_invariantes_de_cobros()`.
  - (COM-06a) `monto_total_entrega` nulo o `>= 0`. Que esté no nulo ⇔ «concretada», y `fecha_vencimiento_pago` no nula ⇔ concretada de un
    suministro, no pueden ir en la base (el estado y el tipo de contrato están en otras tablas): los verifica `verificar_invariantes_de_entregas()`.
  - No pueden ir en la base (dependen de otras tablas), y las verifica `verificar_invariantes_de_entregas()` en las pruebas: el contrato, la
    modalidad y el destino coinciden con los de sus detalles; `estado_confirmacion_cliente` no nulo ⇔ el contrato es un suministro; todas las
    reservas de sus líneas son del invernadero de origen; una reserva tiene a lo sumo una línea en una entrega no cancelada (regla 4 de 8.8).
- Índices en la hija: `(transportista)` (parcial, con `transportista` no nulo) y `(contrato)`. La fecha programada y el estado ya tienen el
  índice del padre (`(invernadero, estado_orden, fecha_programada_orden)`).
- **Lo que se calcula** (no se guarda; funciones de `comercial/servicios/entregas.py`, una consulta por tabla para toda la lista):
  - **Cantidad planificada de una línea:** Σ la cantidad cubierta de sus reservas **no liberadas** (regla 9 de 8.12; regla 9 de 8.8).
  - **Línea quitada:** su cantidad planificada es 0 (todas sus reservas quedaron liberadas por un recorte; D-66, punto 4). No se muestra.
  - **Entrega vacía:** «a realizar» y con todas sus líneas quitadas: se cancela (D-66, punto 9).
  - **Peso** (`peso_de_entregas(ids) -> dict[int, Decimal]`): `redondear(Σ cantidad planificada × variedad.peso_promedio_planta / 1000, 2)`,
    en kilogramos, `ROUND_HALF_UP` (regla «Peso de una entrega»; MD-69: el peso por planta está en gramos).
  - **Atrasada** (MD-139): «a realizar» y `fecha_programada_orden < hoy`. Es el texto de las pantallas («vencida» es otra cosa).
  - **En curso** (regla «Entrega en curso» de PROD-PNF-ENV; MD-118): con envío, `fecha_programada_orden <= hoy` y el vehículo de su
    transportista `esta_en_ruta(hoy)`.
  - **Tiene envasado:** alguna `ReservaInsumo` «activa».
- **Alcance** (`EntregaQuerySet.en_alcance_de(actor)`, D-28): el Gerente activo, todas; el Vendedor activo, las de sus contratos; el Agrónomo
  activo, las de sus invernaderos a cargo (solo para el envasado); el Transportista activo, las suyas (COM-06a); cualquier otro, ninguna.

## DetalleEntrega (COM-05a1, D-66)

Una línea de la entrega: satisface un detalle de venta o un período de un detalle de suministro (restricción C4) y dice qué reservas entrega.

| Atributo | Valores | Nota |
|---|---|---|
| `idDetalleEntrega` | — | El `id` automático |
| `precioUnitario` | pesos > 0, dos decimales | → `precio_unitario`, `DecimalField(12, 2)`. Se guarda **al planificar**: el del detalle de venta, o el del período con la fecha programada (regla 7 de 8.11, `precio_en(detalle, fecha)` de COM-03). COM-06a lo recalcula con la fecha real en un suministro (regla 9 de 8.12) |
| `cantEntregada` | entero ≥ 0, nulo | → `cant_entregada`. Nulo hasta concretar (COM-06a). En una compra-venta, lo que el cliente aceptó (0 si rechazó la línea); en un suministro, lo que recibió |
| (código, COM-06a) `cant_perdida` | entero ≥ 0, nulo | Lo que no llegó en buen estado (la merma «daño en la entrega»). **No está en el modelo** (D-68, punto 7) |
| (código, COM-06a) `cant_devuelta` | entero ≥ 0, nulo | Lo que llegó y volvió a la cámara (rechazo en una compra-venta, lo no recibido en un suministro). **No está en el modelo** |
| `montoPagar` | pesos, nulo | → `monto_pagar`, `DecimalField(14, 2)`. Nulo hasta concretar (COM-06a): `cant_entregada × precio_unitario` |
| (código) `fecha_periodo` | fecha, nula | La fecha del período del detalle de suministro (un período es un par detalle-fecha, `docs/modelo/comercial.md`, «DetalleSuministro»). Nula en una línea de venta |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R120 | Entrega, composición | 1 | `entrega`, FK a `Entrega`, `PROTECT`, `related_name="lineas"` |
| R147 | DetalleVenta, «satisface» | 0..1 | `detalle_venta`, FK nula, `PROTECT`, `related_name="lineas_de_entrega"` |
| R121 | DetalleSuministro, «satisface» | 0..1 | `detalle_suministro`, FK nula, `PROTECT`, `related_name="lineas_de_entrega"` |
| R150 | ReservaStock, «se entrega en» | DetalleEntrega → ReservaStock = 1..\*; ReservaStock → DetalleEntrega = 0..\* | `reservas = ManyToManyField(ReservaStock, related_name="lineas_de_entrega")` (tabla automática). R150 en 0..\* conserva el historial de las entregas canceladas (regla 4 de 8.8) |
| R156 | Queja, «se refiere a» | 0..\* | `Queja.detalles` (COM-06b) |
| R163 | LineaDiscrepancia, «evalúa» | 0..1 | `LineaDiscrepancia.detalle_entrega`, único (COM-06a) |

- Restricciones de la base:
  - **C4:** exactamente una de `detalle_venta` y `detalle_suministro` no nula;
  - `detalle_suministro` no nulo ⇔ `fecha_periodo` no nula;
  - `UniqueConstraint(entrega, detalle_venta)` y `UniqueConstraint(entrega, detalle_suministro, fecha_periodo)`: una línea por detalle (o
    período) en cada entrega;
  - `precio_unitario > 0`; `cant_entregada` nula o `>= 0`.
  - (COM-06a) `cant_entregada`, `cant_perdida`, `cant_devuelta` y `monto_pagar`: las cuatro nulas o las cuatro no nulas; las tres cantidades
    `>= 0`; `monto_pagar >= 0`. Que `entregada + perdida + devuelta` sea la planificada lo verifica el servicio (la planificada sale de las
    reservas) y el invariante.
  - Invariante (prueba): cada línea tiene al menos una reserva (R150 1..\*), y sus reservas son del mismo detalle y, en un suministro, de la
    misma fecha (`fecha_entrega_reserva = fecha_periodo`).

## PagoCliente (COM-06a, D-68 punto 4; COM-08a y COM-08b, D-94)

Bloque: Gestión comercial. Vive en `comercial`. **Hija directa de `contabilidad.OrigenDocumento`** (`TIPO_DE_ORIGEN = pago_cliente`, valor
nuevo de `OrigenDocumento.Tipo` con su migración de `choices` en `contabilidad`), como `MovimientoStock` (D-52). Glosario: el pago que hace el
cliente. COM-06a crea el de una **compra-venta** (lo registra la concreción de su última entrega, postcondición k de COM-CNC-ENT); **COM-08a**
suma el de las entregas de suministro (COM-REG-CBR, con `LineaPago`); **COM-08b**, la anulación (COM-ANL-CBR, MD-136) y el de una compra-venta
cancelada con entregas concretadas (6a de COM-CNL-CVT).

| Atributo | Valores | Nota |
|---|---|---|
| `idPago` | — | El `id` de `OrigenDocumento` |
| (código, COM-08a) `tipo_pago` | `compra_venta` / `suministro` | **D-94, punto 3.** El {xor} de C7. Nunca cambia. La migración lo agrega con el valor por omisión `compra_venta` (los pagos que existan son de COM-06a): no es una migración de datos |
| (código, COM-08a) `numero` y `codigo` | entero, nulo; `COB-0032` | Secuencia propia `comercial_cobro_numero_seq` (como `SolicitudRevision.numero`). **Solo en un pago de suministro** (el que tiene pantalla propia); nulo en uno de compra-venta, que se ve en la ficha de la venta |
| `medioPago` | efectivo / transferencia / tarjeta de débito / tarjeta de crédito | → `medio_pago` (`efectivo`, `transferencia`, `tarjeta_debito`, `tarjeta_credito`; regla 15 de 8.13). El efectivo va a Caja y los demás a Banco c/c, en el asiento (fuera de la ronda, D-57) |
| `fechaPago` | fecha | → `fecha_pago`. La de hoy al registrarlo (en COM-06a, la fecha de resolución de la entrega). En un cobro que corrige uno anulado con `cliente_pago_en_fecha` (7a de COM-ANL-CBR), la del cobro anulado (COM-08b, D-94 punto 10) |
| `montoPagado` | pesos > 0, dos decimales | → `monto_pagado`, `DecimalField(14, 2)`. En una compra-venta, el total de la venta: Σ `cant_entregada_venta × precio_unitario_de_venta` de sus detalles confirmados (regla «Venta registrada por entrega» de COM-CNC-ENT; en 6a de COM-CNL-CVT, Σ `monto_pagar` de las entregas concretadas). En un suministro, Σ (`monto_cobrado` + `indemnizacion_atraso`) de sus líneas |
| `estadoPago` (MD-136) | vigente / anulado | → `estado_pago`. Nace `vigente`. Lo pasa a `anulado` COM-ANL-CBR (COM-08b), que también pone sus líneas en `vigente = False` |
| (código, COM-08a) `usuario` | FK nula a `core.Usuario`, `PROTECT` | Quien lo registró (1a1 y 10a de COM-REG-CBR lo muestran). COM-08a lo carga también en el pago de compra-venta de la concreción; nulo en los anteriores |
| (código, COM-08a) `estado_aviso_cliente` | `enviado` / `pendiente_envio` / `sin_correo`, nulo | El resultado del correo del comprobante de cobro (D-94, punto 13), como `SolicitudRevision.estado_aviso_cliente`. Nulo en un pago de compra-venta (su comprobante es el de la venta, `Contrato.estado_comprobante`) |
| (código, COM-08b) `anulacion_corregida` | `OneToOneField` nulo a `Anulacion`, `PROTECT`, `related_name="cobro_correcto"` | **D-94, punto 10.** El cobro que se registró desde la anulación de otro (7a). Una anulación se usa una sola vez |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R116 | Cliente, «realiza» | PagoCliente → Cliente = 1 | `cliente`, FK a `Cliente`, `PROTECT`, `related_name="pagos"` |
| R117 | Compra-venta, «corresponde» | 0..1 / 0..1 | `compra_venta`, FK nula a `CompraVenta`, `PROTECT`, `related_name="pagos"` |
| R154 | Entrega, «cancela» | PagoCliente → Entrega = 0..\* (1..\* en un suministro) | Por `LineaPago` (COM-08a) |
| MD-135 | Anulacion | 0..1 | `Anulacion.pago` (COM-08b) |

- Restricciones de la base: `monto_pagado > 0`; único `(compra_venta)` con `estado_pago = vigente` (una venta se paga una vez). **C7 (COM-06a:
  `compra_venta` no nula; COM-08a la reescribe como el {xor} del modelo, D-94 punto 3):** `tipo_pago = compra_venta` ⇔ `compra_venta` no nula;
  `tipo_pago = suministro` ⇔ `numero` no nulo; `UniqueConstraint(numero)`; `tipo_pago = compra_venta` ⇒ `estado_aviso_cliente` nulo.
- Invariantes (prueba; `verificar_invariantes_de_cobros()` desde COM-08a): `cliente` es el de la venta; una venta «concretada» tiene
  exactamente un pago vigente y una «cancelada» sin entregas concretadas, ninguno; un pago de suministro tiene al menos una línea y uno de
  compra-venta ninguna; `monto_pagado` = Σ de sus líneas; todas sus entregas son del `cliente`; un pago anulado tiene exactamente una
  `Anulacion` (COM-08b); un cobro con `anulacion_corregida` tiene solo entregas del cobro anulado (COM-08b).
- Asiento: no origina asiento propio en una compra-venta (regla 32 de 8.6: el cobro va en el asiento de la última entrega), **salvo** el de 6a
  de COM-CNL-CVT (MD-130); el de un suministro sí (postcondición d de COM-REG-CBR). Todos fuera de la ronda (D-57).

## LineaPago (COM-08a, R154, D-94 punto 2)

**No es una clase del modelo**: es cómo el código guarda R154 (PagoCliente «cancela» Entrega) con lo que se cobró por cada entrega, como
`LineaDiscrepancia` guarda lo de cada detalle. Una fila por entrega cobrada en un pago de suministro.

| Campo | Valores | Nota |
|---|---|---|
| `pago` | FK a `PagoCliente`, `PROTECT`, `related_name="lineas"` | |
| `entrega` | FK a `Entrega`, `PROTECT`, `related_name="lineas_de_pago"` | Una entrega de suministro concretada |
| `monto_cobrado` | pesos > 0, `DecimalField(14, 2)` | El monto a cobrar de la entrega al cobrar (MD-115: total − Σ descontado) |
| `dias_atraso` | entero ≥ 0 | `fecha_pago − fecha_vencimiento_pago`, 0 si no es positivo (regla «Indemnización por atraso en el pago») |
| `indemnizacion_atraso` | pesos ≥ 0, `DecimalField(14, 2)` | `dias_atraso × Entrega.indemnizacion_retraso_dia`, la de la cláusula vigente al vencer (MD-124; D-94, punto 12). Fija: no cambia si después cambia la cláusula |
| `vigente` | booleano | Copia de `pago.estado_pago = vigente` (la base no puede mirar otra tabla en un índice). La escriben juntos `registrar_cobro` (`True`) y `anular_cobro` (`False`) |

- Restricciones de la base: `UniqueConstraint(pago, entrega)`; **`UniqueConstraint(entrega, condition=Q(vigente=True))`** (a lo sumo un pago
  vigente por entrega: garantía mínima 2 de COM-REG-CBR); `monto_cobrado > 0`; `dias_atraso >= 0`; `indemnizacion_atraso >= 0`; `dias_atraso =
  0` ⇒ `indemnizacion_atraso = 0`.
- Invariantes (prueba, `verificar_invariantes_de_cobros()`): `vigente` = el pago está vigente; la entrega es de suministro, está concretada y es
  del cliente del pago; con la línea vigente, `monto_cobrado = monto_a_cobrar(entrega)`.
- No se borra nunca (MD-136: el cobro anulado conserva su vínculo con las entregas). Se audita como parte del registro de COM-REG-CBR y de
  COM-ANL-CBR (D-36). Índice: el de la FK `entrega` y el único parcial.

## IntentoFallido (COM-06a, D-68 punto 6)

**No es una clase del modelo**: el registro de una entrega que no se pudo realizar (COM-CNC-ENT, extensión 4a, y COM-FIN-RUT, regla 1). Lo
leen COM-RSV-QJA (los intentos dentro del plazo, COM-07), la ficha de la entrega y COM-ATN-ENR (regla 1: «motivos registrados»).

| Campo | Valores | Nota |
|---|---|---|
| `entrega` | FK a `Entrega`, `PROTECT`, `related_name="intentos_fallidos"` | |
| `transportista` | FK a `core.Transportista`, `PROTECT` | El que la tenía asignada al intentar |
| `fecha_hora` | fecha y hora | La del registro |
| `fecha_programada` | fecha | La que tenía la entrega al intentar (la nueva es el día siguiente) |
| `motivo` | `cliente_ausente` / `domicilio_cerrado` / `direccion_incorrecta` / `otro` | La lista de 4a («Lista de tecnología», 4a) |
| `descripcion` | texto, vacío | Opcional, hasta 300 caracteres, sin espacios al borde |

- Se audita como parte del registro del caso de uso (D-36), no por su cuenta. Índice `(entrega, fecha_hora)`.

## SolicitudRevision (COM-06a, D-68 punto 5)

Bloque: Gestión comercial. **Abstracta en el modelo; en el código, padre multitabla concreto** (como `OrdenTrabajo`, D-50): hija directa de
`contabilidad.OrigenDocumento` (`TIPO_DE_ORIGEN = solicitud_revision`, con su migración de `choices`), porque una solicitud aceptada origina
el asiento de su indemnización (fuera de la ronda, D-57). Hijas: `DiscrepanciaEntrega` (COM-06a) y `Queja` (COM-06b).

| Atributo | Valores | Nota |
|---|---|---|
| `idSolicitud` | — | El `id` de `OrigenDocumento` |
| (código) `tipo_solicitud` | `discrepancia` / `queja` | Lo fija la hija al crearse; las listas parten del padre y usan el tipo |
| (código) `numero` y `codigo` | entero; `SR-0012` | Secuencia propia `comercial_solicitud_numero_seq` (como `Contrato.numero`): el número que ven el Gerente y el cliente (acuse de COM-CNF-ENT, postcondición h) |
| `fechaSolicitud` | fecha | → `fecha_solicitud`. La de hoy al crearse |
| `estadoSolicitud` | pendiente de revisión / aceptada / rechazada | → `estado_solicitud` (`pendiente`, `aceptada`, `rechazada`). Nace `pendiente`. Lo cambia COM-07 |
| `fechaResolucion` | fecha, nula | → `fecha_resolucion`. COM-07 |
| `observacionesResolucion` | texto, vacío | → `observaciones_resolucion`. COM-07 (obligatoria al rechazar) |
| `montoIndemnizacion` | pesos ≥ 0, nulo | → `monto_indemnizacion`, `DecimalField(14, 2)`. COM-07a, al aceptar (en una discrepancia, Σ de sus líneas; en una queja sin cláusula, el que carga el Gerente, de 0 al tope de MD-114) |
| (código) `monto_descontado` | pesos ≥ 0, nulo | **D-69, punto 9. No está en el modelo.** `DecimalField(14, 2)`. Lo que la aceptación descontó del monto a cobrar de la entrega (MD-115: hasta dejarlo en 0; 0 si ya estaba pagada) |
| (código) `monto_reintegrado` | pesos ≥ 0, nulo | Ídem. Lo que se reintegró al cliente (6a o 6d de los dos casos de uso) |
| (código) `medio_reintegro` | `efectivo` / `transferencia`, nulo | Ídem. Con qué se reintegró («Lista de tecnología», 6a) |
| (código) `estado_aviso_cliente` | `enviado` / `pendiente_envio` / `sin_correo`, nulo | **D-69, punto 17.** El resultado del correo al cliente de la resolución (comprobante o aviso). Nulo mientras está pendiente |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| R009 | Gerente, «revisa» | 0..1 | `gerente`, FK nula a `core.Usuario`, `PROTECT`. COM-07a |
| R054 | Alerta, «emite» | SolicitudRevision → Alerta = 1 | Por `AlertaComercial.solicitud` (D-63) |
| (código) | Entrega | 1 | `entrega`, FK a `Entrega`, `PROTECT`, `related_name="solicitudes"`. **No está en el modelo** (R129 se eliminó: se deduce de los detalles). Lo guarda D-68 punto 5 para la única discrepancia por entrega; lo escribe una sola función (`crear_solicitud`) |

- Restricciones de la base: `UniqueConstraint(entrega, condition=Q(tipo_solicitud="discrepancia"))` (regla 3 de 8.14); `estado = pendiente`
  ⇔ `fecha_resolucion` nula ⇔ `gerente` nulo; `estado = aceptada` ⇒ `monto_indemnizacion` no nulo y `>= 0`; `monto_indemnizacion` no nulo
  ⇒ `estado = aceptada`. **COM-07a suma** (D-69, puntos 9 y 17): `estado = aceptada` ⇔ `monto_descontado` y `monto_reintegrado` no nulos;
  los dos `>= 0`; aceptada ⇒ `monto_descontado + monto_reintegrado = monto_indemnizacion`; `medio_reintegro` no nulo ⇔ `monto_reintegrado >
  0`; `estado = pendiente` ⇒ `estado_aviso_cliente` nulo.
- Invariantes (prueba, `verificar_invariantes_de_solicitudes()`): la entrega es de un suministro y está «concretada»; los detalles de la
  solicitud (líneas o detalles de la queja) son todos de esa entrega; cada solicitud tiene exactamente una `AlertaComercial`. **COM-07a
  suma:** el monto a cobrar de cada entrega nunca es negativo; `Suministro.cantidad_incumplimientos` = las aceptadas del contrato; en una
  discrepancia aceptada, `monto_indemnizacion` = Σ `monto_indemnizacion_linea`; una pendiente o rechazada no tiene montos en sus líneas.
- La alerta de una solicitud **anulada** no se reabre ni se crea otra (D-69, punto 4): queda resuelta y la solicitud vuelve a «pendiente».

## DiscrepanciaEntrega y LineaDiscrepancia (COM-06a)

`DiscrepanciaEntrega(SolicitudRevision)`, `tipo_solicitud = discrepancia`, **sin atributos propios** (ronda 19). La crea la concreción de una
entrega de suministro cuando uno o más detalles quedan por debajo de la cantidad mínima de su cláusula (extensión 14c de COM-CNC-ENT; regla 12
de 8.13). Una por entrega, con una línea por detalle.

| `LineaDiscrepancia` | Valores | Nota |
|---|---|---|
| `idLineaDiscrepancia` | — | El `id` automático |
| `cantidadEntregada` | entero ≥ 0 | → `cantidad_entregada`. Copia fija de la `cant_entregada` de la línea |
| `cantidadMinimaEstipulada` | entero ≥ 1 | → `cantidad_minima_estipulada`. Copia fija de la mínima de la cláusula del suministrante del detalle, por si después cambia |
| `montoIndemnizacionLinea` | pesos ≥ 0, nulo | → `monto_indemnizacion_linea`. COM-07a, al aceptar: `(cantidad_minima_estipulada − cantidad_entregada) × indemnizacion_faltante` de la cláusula del detalle; vuelve a nulo al anular |
| R162 | DiscrepanciaEntrega, composición | `discrepancia`, FK, `PROTECT`, `related_name="lineas"` |
| R163 | DetalleEntrega, «evalúa» | `detalle_entrega`, `OneToOneField` a `DetalleEntrega`, `PROTECT` (0..1 del lado de la línea de entrega) |

- Restricciones de la base: `cantidad_entregada < cantidad_minima_estipulada` (por eso existe la línea); `cantidad_entregada >= 0`.

## Queja (COM-06b)

`Queja(SolicitudRevision)`, `tipo_solicitud = queja`. La registra el cliente con el enlace (COM-CNF-ENT, extensión 3a).

| Atributo | Valores | Nota |
|---|---|---|
| `tipoQueja` | estado de la mercadería / retraso / otro | → `tipo_queja` (`estado_mercaderia`, `retraso`, `otro`) |
| `motivoQueja` | texto, vacío | → `motivo_queja`. Hasta 500 caracteres, sin espacios al borde. Obligatorio en `estado_mercaderia` y `otro` (restricción); opcional en `retraso` |
| R118 | Cliente, «emite» | `cliente`, FK a `Cliente`, `PROTECT`, `related_name="quejas"` |
| R156 | DetalleEntrega, «se refiere a» | `detalles`, `ManyToManyField(DetalleEntrega, related_name="quejas")`, 1..\* (lo verifica el servicio y el invariante) |

- Restricciones de la base: `tipo_queja` en la lista; `tipo_queja <> retraso` ⇒ `motivo_queja` no vacío.
- Invariantes (prueba): a lo sumo una queja de cada tipo por entrega en la misma respuesta (regla «Tipos de queja»; dos respuestas no puede
  haber: el enlace es de un solo envío); en una de retraso, todos sus detalles tienen días de retraso mayores que cero; `cliente` es el del
  contrato.

## Anulacion (COM-07a, MD-135, D-69 punto 10)

Bloque: Gestión comercial. **Clase nueva** (MD-135): hija de `contabilidad.OrigenDocumento` (`TIPO_DE_ORIGEN = anulacion`, con su migración de
`choices`), porque origina el contraasiento del documento que anula (R012; fuera de la ronda, D-57). En la ronda anula la resolución de una
solicitud (COM-ANL-SRV, COM-07a) y un cobro de suministro (COM-ANL-CBR, **COM-08b**; D-94, punto 11).

| Atributo | Valores | Nota |
|---|---|---|
| `idAnulacion` | — | El `id` de `OrigenDocumento` |
| `fechaAnulacion` | fecha | → `fecha_anulacion`. La de hoy |
| `motivoAnulacion` | texto, obligatorio | → `motivo_anulacion`, de 1 a 500 caracteres, sin espacios al borde |
| `clientePagoEnFecha` | booleano, nulo | → `cliente_pago_en_fecha` (**COM-08b**). Solo en la anulación de un cobro: si el cliente realmente pagó en la fecha del cobro anulado (paso 3 de COM-ANL-CBR); con `True`, el cobro correcto puede usar esa fecha (7a; D-94, punto 10) |
| (código) copia de la resolución anulada | `estado_anulado` (`aceptada` / `rechazada`), `fecha_resolucion_anulada`, `gerente_anulado` (FK a `core.Usuario`, `PROTECT`), `observaciones_anuladas`, `monto_indemnizacion_anulado`, `monto_descontado_anulado`, `monto_reintegrado_anulado`, `medio_reintegro_anulado` | **D-69, punto 10. No está en el modelo.** Lo que tenía la solicitud antes de volver a «pendiente», para el historial de la ficha (COM-CNS-SRV) sin leer la auditoría. Los montos y el medio, nulos si estaba rechazada |

| R | Con | Multiplicidad | En el código |
|---|---|---|---|
| MD-135 | Usuario, «anula» | 1 | `usuario`, FK a `core.Usuario`, `PROTECT` |
| MD-135 | SolicitudRevision, «anula» | 0..1 | `solicitud`, FK nula a `SolicitudRevision`, `PROTECT`, `related_name="anulaciones"` (una solicitud puede anularse más de una vez, una por cada resolución) |
| MD-135 | PagoCliente, «anula» | 0..1 | `pago`, `OneToOneField` nulo a `PagoCliente`, `PROTECT`, `related_name="anulacion"` (**COM-08b**): un pago se anula una sola vez. **Sin copia** de los datos del pago: el pago anulado los conserva, con `estado_pago = anulado` (D-94, punto 11) |

- Restricciones de la base: `motivo_anulacion <> ''`; en COM-07a, `solicitud` no nula (**COM-08b** la reescribe como «exactamente uno de
  `solicitud` y `pago`» y suma `pago` no nulo ⇔ `cliente_pago_en_fecha` no nulo); `estado_anulado` no nulo si `solicitud` no nula (COM-08b:
  «si y solo si»); `estado_anulado = aceptada` ⇔ `monto_indemnizacion_anulado` no
  nulo.
- Se audita como parte del registro de COM-ANL-SRV (`anulacion_resolucion_solicitud`) o de COM-ANL-CBR (`anulacion_cobro`, COM-08b; D-36), no
  por su cuenta. Índice `(solicitud,
  fecha_anulacion)`.

---

## Pendientes de MD

Lo que estas fichas ya aplican y todavía no está en el modelo de Drive (pendientes_MD lo pega el estudiante; Claude no tiene permiso de
escritura).

| Ítem | Qué | Estado en Drive |
|---|---|---|
| MD-128 | R119 en 0..\* (dirección opcional) | Decidido sin aplicar («MD · Cambios… (comercial)») |
| MD-129 | `Vehiculo.patente` y lista cerrada de `tipoVehiculo` | Ídem |
| MD-118 | `Vehiculo.fechaInicioRuta` y la definición de «en ruta» | Ídem |
| MD-138 | R155 en 0..1 (ya aplicado por D-55 en `maestros`) | Ídem |
| Nuevo | `Cliente.tipoCliente` (jurídica / física): la regla 3 de COM-ALT-CLT lo usa y el modelo no lo tiene | **Sin ítem**: proponerlo en pendientes_MD |
| Nuevo | Largos de los textos de `Cliente` y `Vehiculo` y capacidad hasta 999.999,99 kg | **Sin ítem**: son del sistema, no del dominio; no hace falta en el modelo |
| MD-130 | `estadoDetalleVenta` «cancelado» y los datos de la cancelación (los aplica COM-05b; ficha de CompraVenta) | Decidido sin aplicar («MD · Cambios… (comercial)») |
| Nuevo | `ReservaStock.invernadero` guardado (regla 1 de 8.8) y `Cosecha.variedad` guardada (regla 2 de 8.8): desnormalizaciones del código, D-59 | **Sin ítem**: son del código, no del dominio |
| Nuevo | `Contrato.numero` por tipo (código `CV-0001`) | **Sin ítem**: del código |
| Nuevo | `Contrato.estado_comprobante` (16a y 16b de COM-REG-CVT, 15a de COM-PCT-SUM, 11a de COM-MOD-SUM) | **Sin ítem**: del código (el modelo no guarda el envío del comprobante) |
| MD-120, MD-124, MD-131, MD-133 | `fechaResolucionSuministro`; cláusula del suministrado por contrato; `fechaFinDetalle` y «reemplaza a»; alerta «período sin cobertura completa» | Decidido sin aplicar («MD · Cambios… (comercial)») |
| PCU 16 | Incumplimientos tolerados de 0 a 99 | Decidido (pendientes_CU) |
| **MD-140 (proponer)** | Rescisión por mutuo acuerdo de un Suministro: estado «rescindido» y los seis atributos de la rescisión; reemplaza la mejora futura de 1.10 y de la observación 2 de 8.11; glosario «Rescisión» (texto en `LEEME_LOTE_C3.md`) | **Sin ítem todavía**: proponerlo en pendientes_MD |
| Nuevo | `Suministro.fecha_fin` guardado; `DetalleSuministro.fecha_base_ajuste`; `AlertaComercial` (D-63) | **Sin ítem**: del código |
| D-60 | Regla 8 de 8.21: qué contratos pasan al Vendedor nuevo | **Proponer en pendientes_MD** (D-60 vigente desde el 21/11/2026) |
| D-64, punto 8 | Un período de un detalle finalizado con fecha ≤ `fechaFinDetalle` todavía tiene cantidad sin cubrir (lectura de MD-126) | **Proponer en pendientes_MD** (D-64 vigente desde el 21/11/2026) |
| Nuevo | `EnlaceCliente` (D-65); `fecha_entrega_reserva` nula sin contrato y línea de cámara en 0 (D-64, puntos 6 y 7) | **Sin ítem**: del código (la reserva sin fecha ya la dice PROD-PNF-CSC, y el recorte, la regla 6 de 8.9) |
| MD-135 | `Anulacion` (aplicada por COM-07a con la solicitud; COM-08b suma `clientePagoEnFecha` y el pago) | Decidido sin aplicar («MD · Cambios… (comercial)») |
| MD-136 | `PagoCliente.estadoPago` (vigente / anulado) | Decidido sin aplicar («MD · Cambios… (comercial)») |
| **Nuevo (D-94, punto 2)** | **R154 en 0..\***: Entrega → PagoCliente = 0..\*, con a lo sumo un pago vigente. MD-136 dice que el cobro anulado conserva su vínculo con las entregas, y la entrega se vuelve a cobrar: con 0..1 no se puede | **Proponer en pendientes_MD** |
| Nuevo (D-94) | `LineaPago` (lo cobrado y el atraso por entrega); `PagoCliente.tipo_pago`, `numero`, `usuario`, `estado_aviso_cliente` y `anulacion_corregida`; `Entrega.fecha_aviso_mora` y `estado_aviso_mora` | **Sin ítem**: del código |
| Nuevo (D-69) | `SolicitudRevision.monto_descontado`, `monto_reintegrado`, `medio_reintegro` y `estado_aviso_cliente`; `Suministro.solicitud_resolucion`; la copia de la resolución en `Anulacion` | **Sin ítem**: del código. Pero conviene que MD-115 diga que el descuento y el reintegro se registran en la solicitud (para el asiento compuesto) |
| Nuevo (D-69, punto 6) | Tipo de evento de bitácora «anulación de una resolución» (junto con «incumplimiento de cláusula suministrante») | **Proponer en pendientes_MD** |
| Nuevo | `Entrega.contrato`, `modalidad_entrega`, `direccion_destino`, `estado_aviso_cliente`, `recordatorio_para`, `aviso_atrasada_para` y `DetalleEntrega.fecha_periodo` (D-66) | **Sin ítem**: del código |
| MD-119, MD-122, MD-139 | Motivo y fecha de la cancelación de una orden; la alerta asociada a la entrega; «atrasada» para una entrega con la fecha pasada | Decidido sin aplicar («MD · Cambios… (comercial)») |
| D-66, punto 7 | Agrupamiento en una compra-venta de las reservas que quedan listas después de su entrega | **Proponer en pendientes_CU** (COM-PNF-ENT) |
| Nuevo | `Entrega.monto_total_entrega` y `fecha_vencimiento_pago` guardados (MD-132 ya lo pide para el vencimiento); `DetalleEntrega.cant_perdida` y `cant_devuelta`; `SolicitudRevision.entrega`, `tipo_solicitud` y `numero`; `EnlaceCliente.entrega`; `AlertaComercial.solicitud` (D-68) | **Sin ítem**: del código |
| D-68, punto 6 | Intentos fallidos guardados (`IntentoFallido`): el modelo no los tiene y COM-RSV-QJA pregunta si conviene modelarlos | **Proponer en pendientes_MD** |
| MD-136, MD-137 | `PagoCliente.estadoPago`; `Alerta.resultadoAveriguacion` (en el código, en `AlertaComercial`, D-68 punto 9) | Decidido sin aplicar («MD · Cambios… (comercial)») |

## Diferencias con el caso de uso

| N.º | Tema | Modelo | Caso de uso | Se aplica |
|---|---|---|---|---|
| 1 | Dirección del cliente | R119 1..\* | Opcional (MD-128, regla 6 de COM-ALT-CLT) | El caso de uso |
| 2 | Tipo de cliente | No existe | Persona jurídica o física (regla 3 de COM-ALT-CLT) | El caso de uso (`tipo_cliente`) |
| 3 | Reactivar un cliente | La regla 2 de 8.18 dice «reactivarlo (Alta Cliente)» | Lo mismo: COM-ALT-CLT, regla 2, y la puede hacer el Vendedor | El caso de uso. Ojo: `docs/patrones/abm.md` (sección 3) dice que la reactivación es parte de MOD; acá es parte del alta |
| 4 | Patente | No existe | Obligatoria y única (MD-129) | El caso de uso |
| 5 | Cláusulas del suministro | R111: dos cláusulas por detalle | Una del suministrado por contrato y una del suministrante por detalle (MD-124; COM-PCT-SUM v0.3) | El caso de uso |
| 6 | Incumplimientos tolerados | «Resuelto cuando cantIncumplimientos supera cantMaxIncumplimiento» | COM-PCT-SUM v0.3: de 1 a 99; COM-MOD-SUM v0.1: el nuevo valor «mayor que los acumulados». PCU 16 (21/11/2026): de 0 a 99 y nunca menor que los acumulados | **PCU 16**, que es la decisión más nueva y coincide con «supera» del modelo |
| 7 | Validación de stock al pactar | Regla 8 de 8.11: solo la primera entrega | Todos los períodos de la ventana, acumulados por variedad (MD-116; COM-PCT-SUM 9e) | El caso de uso |
| 8 | Fecha de fin | `fechaRealizacion + duracion` | Mismo día del mes N meses después, o el último día del mes (COM-PCT-SUM, «Fecha de fin») | El caso de uso |
| 9 | Terminación por mutuo acuerdo | 1.10 y Observación 2 de 8.11: mejora futura, con estado «cancelado» | COM-RSC-SUM (nuevo, 21/11/2026): rescisión por mutuo acuerdo, estado «rescindido» (MD-140, a proponer). COM-MOD-SUM sigue permitiendo terminar un detalle o acortar la duración (MD-131) | El caso de uso |
| 10 | Cantidad sin cubrir de un detalle de suministro finalizado | MD-126: «un detalle finalizado o resuelto no tiene cantidad sin cubrir» | COM-MOD-SUM finaliza el detalle **en el acto**, con períodos de la ventana todavía por entregar | D-64, punto 8: el período con fecha ≤ `fecha_fin_detalle` de un detalle finalizado se debe; MD-126 rige para los posteriores y para los resueltos |
| 11 | Reservas de una venta que quedan listas después de su entrega | Regla 2 de 8.12: el agrupamiento es solo de suministro | COM-PNF-ENT no lo dice (solo pasa tras un recorte de cámara y una nueva cobertura) | D-66, punto 7 (a validar): se agregan a la entrega «a realizar» de esa venta y ese invernadero, con las condiciones de la regla 2 |
