# Patrón · Stock maduro, reservas y cosechas automáticas (`comercial`)

Cómo se calcula el stock que se puede vender y cómo se reserva. Lo programa COM-02 (PROD-ASG-STK, `docs/casos_de_uso/produccion/stock_maduro.md`)
y lo usan COM-03 (pactar y pre-reservar; sección 7), COM-04 (cosecha, cámara y merma en cámara; sección 8) y COM-05 (cancelaciones). Decisión: D-59.
Si algo de acá contradice un caso de uso, manda el caso de uso: avisá.

## 1. Definiciones (reglas 9 a 12 de 8.6, 3 de 8.11 y 2 y 3 de 8.20)

| Concepto | Definición |
|---|---|
| **Invernaderos considerados** | Retiro: solo el de retiro. Envío y suministro: los invernaderos **activos** del Vendedor del contrato (regla 7 de 8.6; un inactivo no aparece en asignaciones, regla 4 de PROD-BAJ-INV) |
| **Anticipación efectiva** | `min(parámetro del contrato, postcosecha de la variedad)`. Parámetro: `dias_anticipacion_cosecha_compra_venta` o `dias_anticipacion_cosecha_suministro` (`maestros.servicios.configuracion.obtener()`, leído una vez por operación) |
| **Fecha programada por defecto** de una cosecha automática | `max(hoy, fecha_entrega − anticipación efectiva)` (regla 3 de 8.11) |
| **Partida elegible** | `StockCosechado` «disponible», del lote de la variedad, de un invernadero considerado, con `fecha_limite >= fecha_entrega` y stock libre > 0 |
| **Lote elegible** | `Lote` «activo», de la variedad, cuya etapa actual es de tipo Maduración, en un invernadero considerado **con Capataz activo** (asignado y con la cuenta activa), con stock libre > 0 y con `fecha_maxima_de_cosecha >= fecha programada por defecto` |
| **Stock libre** | Lote: `cantidad_actual − Σ reservado en reservas «activas»`. Partida: `cantidad_disponible − Σ reservado en reservas «activas» o «lista para entrega»` |
| **Stock maduro libre** de una variedad para una fecha | Σ stock libre de los lotes elegibles + Σ stock libre de las partidas elegibles |
| **Orden de asignación** | Primero las partidas, por `fecha_limite` (y `id`); después los lotes, por fecha de entrada a Maduración, después menor stock libre, después `id` |

Hoy siempre se calcula con `stock.hoy()` de `inventario` (`timezone.localdate()`), nunca con `date.today()`.

## 2. Funciones (`comercial/servicios/stock_maduro.py`)

| Función | Qué hace |
|---|---|
| `disponible(variedad_ids, invernadero_ids, fecha_entrega, parametro) -> dict[int, Disponible]` | **Solo lectura, sin bloquear.** Por variedad, `Disponible(total, lotes, partidas)`. Para las pantallas (paso 8 de COM-REG-CVT) y para el resumen. Una consulta por tabla, nunca una por lote |
| `asignar(origen, detalle, cantidad, fecha_entrega, parametro, *, lotes_excluidos=()) -> Asignacion` | **PROD-ASG-STK.** Corre dentro de la transacción del caso de uso base (sin ella, `RuntimeError`), con los bloqueos de la sección 3 ya tomados. `parametro` es `"compra_venta"` o `"suministro"` (anticipación); `lotes_excluidos`, los de una cosecha cancelada (PCU 7, COM-04). Devuelve `Asignacion(cubierta, sin_cubrir, reservas, cosechas)` |
| `cantidad_sin_cubrir(detalle) -> int` | Regla 10 de 8.8 |
| `reservado_de_lotes(lote_ids) -> dict[int, int]` | Lo que registra `comercial` en `produccion.extensiones.registrar_reservado_de_lote` (`docs/api/extensiones_de_produccion.md`) |

- `origen` es la cuenta que actúa (Vendedor o Gerente) o `None` si actúa InfoPonia (D-27).
- `detalle` es un `DetalleVenta` (COM-02) o, desde COM-03, un período de un `DetalleSuministro`.
- `asignar` **no** cambia la cantidad del lote ni la de la partida (regla 14 de 8.8), **no** cambia el estado del detalle ni del contrato y
  **no** audita por su cuenta: devuelve lo creado y el caso de uso base lo pone en **su único registro** de auditoría (D-36), como
  `cancelar_orden_incluida` en `produccion`.

## 3. Bloqueos (orden fijo, `FOR NO KEY UPDATE`)

Se suma al orden de `produccion` (`docs/patrones/bloqueos.md`, sección `produccion`):

1. las cuentas que se van a leer o a notificar (el Vendedor responsable y quien actúa), en una consulta y en orden de id;
2. **los invernaderos considerados**, en orden de id. Con `bloquear_invernadero_activo` (`maestros`), porque una cosecha «a realizar» impide la
   baja del invernadero (contrato de D-40). Se releen el Capataz y su estado **después** de bloquear;
2b. **el cliente** del contrato, si la operación lo tiene (COM-REG-CVT y COM-PCT-SUM): se relee y se verifica que siga activo. La baja del
   cliente (COM-01) bloquea la misma fila, así que una venta y una baja del mismo cliente se ponen en fila;
3. **las variedades** de la operación, en orden de id (`inventario.servicios.variedades.bloquear_variedad`): una baja de la variedad no puede
   pasar a la vez que un contrato nuevo (precondición f de PROD-BAJ-VAR);
4. **los lotes candidatos** (todos los lotes activos de esas variedades en esos invernaderos), en orden de id;
5. **las partidas candidatas**, en orden de id;
6. las filas de la operación (contrato, detalles, reservas, líneas, cosechas), que son nuevas o se releen.

Con los lotes y las partidas bloqueados **antes** de leer sus reservas, dos asignaciones sobre la misma variedad se ponen en fila: la segunda
espera, y al leer ve las reservas que confirmó la primera. Por eso la extensión 8a de PROD-ASG-STK («recalcular una vez») **no hace falta**
con este diseño: el cálculo ya se hace sobre el stock vigente, después de bloquear. Una merma de PRD-03 bloquea invernadero → variedad →
sectores → lote: el mismo sentido, sin interbloqueo.

## 4. Qué crea `asignar`

1. Toma las partidas elegibles en orden hasta cubrir; después los lotes elegibles en orden.
2. Agrupa lo tomado **por invernadero**: una `ReservaStock` por invernadero (regla 1 de 8.8), con una `DetalleReserva` por lote y por partida.
3. Estado de cada reserva: «lista para entrega» si todas sus líneas son de partidas; «activa» si tiene alguna de lote (regla 12 de 8.6).
4. Por cada reserva con líneas de lote, una `produccion.Cosecha` «a realizar» con: el invernadero, la variedad, el Capataz del invernadero,
   `agronomo` nulo, la fecha de creación de hoy, la **fecha programada por defecto**, la prioridad «media» y el número de la secuencia de
   órdenes (`OT-…`, D-52). La reserva apunta a ella (`ReservaStock.cosecha`).
5. Las notificaciones de cada cosecha (al Capataz y al Agrónomo del invernadero; textos en el extracto) van **dentro** de la transacción del
   caso de uso base (D-42): si el base se revierte, no queda ninguna.

## 5. Cosas que el caso de uso decía de otra forma (manda el código del repo, avisado)

| Tema | Caso de uso | Se hace | Por qué |
|---|---|---|---|
| Notificaciones | «Después de que el base confirmó» y reintento (10a) | Dentro de la transacción (D-42); sin reintento | Es la regla de todo el sistema (`docs/temas_abiertos.md`, «Notificaciones», lote 4) |
| Recálculo por concurrencia (8a) | Recalcular una vez | Bloquear antes de calcular | Sección 3 |
| Alerta por invernadero sin Capataz (5a) | Alerta propia, en transacción aparte | La `sin_capataz` de `maestros` (D-41), que ya existe mientras falte un Capataz activo; `asignar` llama a `asegurar_alerta_de_estado(invernadero, "sin_capataz")` por si falta | `maestros` la mantiene sola (alta y modificación del invernadero, baja y reactivación de la cuenta): no hace falta otra, ni otra transacción |

## 6. Pruebas (fábricas en `comercial/tests/fabricas.py`)

- `lote_maduro(invernadero, variedad, cantidad, entrada=fecha)`: arma con las fábricas de `produccion` un lote en Maduración (con su
  transición concretada) para no depender de pantallas.
- `partida(lote, disponible, fecha_limite)`.
- `reserva(detalle, lineas=[(lote_o_partida, cantidad)], estado=...)`.
- Invariantes, en `verificar_invariantes_de_reservas()` (después de cada prueba de escritura): ningún lote ni partida con stock libre
  negativo; ninguna reserva con líneas de dos invernaderos; ninguna cosecha sin reserva ni de dos variedades; ningún detalle con más cubierto
  que lo pedido.
- Concurrencia mínima (`@tag("concurrencia")`, `correr_a_la_vez`): dos ventas por el último stock de un lote; una venta contra una merma del
  mismo lote; una venta contra la baja de la variedad; una venta contra la baja del invernadero.

## 7. Suministros: períodos, cobertura y verificación acumulada (COM-03)

Lo suma COM-03 (`docs/casos_de_uso/comercial/suministro.md` y `docs/casos_de_uso/produccion/pre_reserva.md`). Nada de las secciones 1 a 6
cambia.

- **Período** = `Periodo(detalle, fecha)` (`namedtuple`), con `detalle` un `DetalleSuministro` y `fecha` una del calendario del detalle
  (`comercial/servicios/calendario.py`, `docs/modelo/comercial.md`, «DetalleSuministro»). `asignar` acepta un `DetalleVenta` o un
  `Periodo`; con un `Periodo`, cada reserva lleva `detalle_suministro` y `fecha_entrega_reserva = periodo.fecha`, y `parametro` es siempre
  `"suministro"`.
- **Cantidad sin cubrir de un período** (regla 10 de 8.8, MD-126): `cantidad_por_periodo − Σ cantidad_reservada` de las líneas de las
  reservas **no liberadas** de ese detalle con esa `fecha_entrega_reserva`. Tiene cantidad sin cubrir un período de un detalle «vigente» o,
  **desde COM-04 (D-64 punto 8)**, de un detalle «finalizado» si la fecha no supera su `fecha_fin_detalle` (todavía se debe); los demás
  (posteriores a la fecha de fin, detalles resueltos) no tienen.
  `cantidad_sin_cubrir(periodo)` la calcula para uno; `sin_cubrir_de_periodos(periodos)` para muchos, en una consulta.
- **Invernaderos considerados de un suministro**: los activos del Vendedor **actual** del contrato (un cambio de Vendedor, D-60 o COM-MOD-SUM,
  cambia de dónde salen los períodos siguientes; lo ya reservado no se mueve).
- **Ventana de pre-reserva**: `hoy + dias_pre_reserva_suministro` (configuración). Un período cae dentro si `hoy <= fecha <= ventana`.
- **Planificador puro y simulación.** El reparto de la sección 4 (qué partidas y qué lotes, en qué orden y cuánto de cada uno) se escribe
  **una sola vez**, como función pura `repartir(candidatos, libre, cantidad) -> (tomado, sin_cubrir)` que no lee la base. La usan:
  - `asignar`, con los candidatos y el stock libre leídos después de bloquear;
  - `simular(variedad_id, invernadero_ids, pedidos, parametro) -> list[Cobertura]` (**solo lectura, sin bloquear**), con
    `pedidos = [(fecha, cantidad), …]` **en orden de fecha**: reparte el primero, descuenta lo que tomó del stock libre en memoria y sigue con el
    siguiente. Es la «verificación acumulada por variedad» de COM-PCT-SUM (9e) y COM-MOD-SUM (5b.3): cada período se verifica contra lo que
    dejan libre los anteriores **del mismo contrato y de la misma variedad**. Devuelve por pedido `Cobertura(fecha, cantidad, disponible)`.
  Una prueba compara, para los mismos datos, lo que `simular` dice que se cubre con lo que después reserva `asignar` en el mismo orden: tiene
  que coincidir.
- **Orden al reservar varios períodos en una operación** (COM-PCT-SUM paso 14, COM-MOD-SUM paso 10): por fecha, después por variedad, después
  por el orden de los detalles en el formulario; uno por uno, cada uno con `asignar`. Si alguno queda con cantidad sin cubrir, el caso de uso
  base lanza `stock_insuficiente` y se revierte todo (14a de COM-PCT-SUM; 10 de COM-MOD-SUM).
- **Orden en la pre-reserva diaria** (PROD-PRR-SUM, paso 2): por fecha y, con la misma fecha, por `id` del detalle. Cada período en su propia
  transacción, con los bloqueos de la sección 3 más, al final, el `Suministro` y el `DetalleSuministro` (`FOR NO KEY UPDATE`), que se releen
  para verificar que siguen vigentes. COM-MOD-SUM bloquea el mismo `Suministro`: una modificación y una pre-reserva del mismo contrato se
  ponen en fila («La modificación se serializa con la pre-reserva diaria», requisito especial de COM-MOD-SUM).
- **Pruebas** (sumar a la sección 6): fábrica `suministro(cliente, vendedor, detalles=[…])` y `periodo(detalle, fecha)`; invariantes nuevos:
  ningún período con más cubierto que su cantidad; ninguna reserva de un período fuera del calendario de su detalle; ninguna reserva con
  `detalle_venta` y `detalle_suministro` a la vez.

## 8. Cosecha, cámara y faltantes (COM-04, D-64)

Lo suma COM-04 (`docs/casos_de_uso/produccion/cosecha.md`, `camara.md`, `merma.md`, `cancelar_orden.md` y
`docs/casos_de_uso/comercial/faltante.md`). Las secciones 1 a 7 no cambian, salvo lo que dice cada punto.

- **`asignar(..., origen_cosecha="automatica")`.** Argumento nuevo con nombre: las cosechas que crea llevan ese origen (D-64 punto 5). Lo
  pasa `encadenada` solo PROD-CNC-CSC (13a). `lotes_excluidos` (ya existe desde COM-02) lo usa PROD-CNL-ORD (8c) con los lotes de la
  cosecha cancelada.
- **`simular(..., lotes_excluidos=(), sin_reservas=())`.** Dos argumentos nuevos con nombre, para la estimación de PROD-CNL-ORD (6b): no
  considera esos lotes y cuenta como libre lo que reservan esas reservas (las de la cosecha que se cancelaría). Una prueba compara la
  estimación con lo que después reserva `asignar` en el paso 8.
- **Períodos de un detalle finalizado** (D-64 punto 8): `asignar` acepta un `Periodo` de un detalle «finalizado» si la fecha no supera su
  `fecha_fin_detalle` (la precondición b de PROD-ASG-STK se lee así); con uno posterior, `ValueError` como hoy.
- **Cosecha manual** (PROD-PNF-CSC): **no** usa `asignar` (el Agrónomo elige los lotes, supuesto 7 de 8.7). Crea una `ReservaStock`
  «activa» con una línea por lote, en el invernadero elegido, y su `Cosecha` `manual`. Con contrato, la reserva lleva el detalle (o el
  período) y su fecha de entrega; sin contrato, ninguno de los dos y `fecha_entrega_reserva` nula (D-64 punto 6). Bloqueos: los de la
  sección 3, con el invernadero elegido como único invernadero y los lotes elegidos (más, con contrato, el contrato y su detalle al final).
- **Cantidad sin cubrir al planificar** (11b de PROD-PNF-CSC): `cantidad_sin_cubrir(detalle o período)`, releída después de bloquear.
- **Faltante después de cosechar** (13a de PROD-CNC-CSC): `faltante = Σ cantidad_reservada de las líneas de lote − Σ min(cosechada,
  reservada)`. Se cubre con `asignar(Capataz, detalle o período, faltante, fecha_entrega_reserva, parametro, origen_cosecha="encadenada")`
  **después** de pasar la reserva a «lista para entrega» (así su cubierto ya es el final) y de liberar sus lotes del stock reservado. Lo que
  `asignar` devuelve sin cubrir sigue el **camino de faltante** (abajo).
- **Camino de faltante** (una sola función, `comercial/servicios/faltantes.py`: `seguir_camino_de_faltante(detalle_o_periodo, sin_cubrir,
  *, origen)`), la usan PROD-CNC-CSC (13a), PROD-REG-MRM (10c), PROD-CNL-ORD (8c y 8d) y PROD-VNC-CAM (3a.2a):
  - **detalle de compra-venta**: pasa a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy` (si ya lo estaba, solo
    actualiza la fecha: 8d de PROD-CNL-ORD); la venta pasa a «pendiente de decisión del cliente»; se crea o se reemplaza el enlace de la venta
    (`docs/patrones/enlace_del_cliente.md`); notificación al Vendedor con el faltante. Sin correo del cliente: la notificación le dice que
    registre él la decisión;
  - **período de suministro**: no cambia de estado; queda con cantidad sin cubrir, la pre-reserva diaria lo vuelve a intentar mientras su
    fecha esté en la ventana (sección 7) y se notifica al Vendedor.
  - **quién llama a `asignar` antes:** el caso de uso, y solo para un detalle que se puede cubrir (precondición b de PROD-ASG-STK): un detalle
    «abierto» de una venta «abierta» o un período. Un detalle (o una venta) que ya espera la decisión del cliente va **directo** al camino,
    con la cantidad perdida sumada a su faltante (8d de PROD-CNL-ORD); un detalle «confirmado» que pierde producto (recorte de cámara) se intenta
    cubrir con `asignar` por lo perdido (con `cant_entregada_venta` como cantidad pedida) y, si no alcanza, vuelve a «pendiente de decisión
    del cliente» con `cant_entregada_venta` vacía y enlace nuevo (D-64 punto 13).
- **Asignación automática de cámara** (PROD-ASG-CAM, `comercial/servicios/camara.py`, `asignar_camara(partida_ids)`): **no** usa `repartir`
  (cubre candidatos con una partida, al revés que `asignar`, que cubre un detalle con varias fuentes). Candidatos y orden: los del extracto
  (`camara.md`). Por partida, una transacción con los bloqueos de la sección 3: el invernadero de la partida, las cuentas de los Vendedores
  y del Agrónomo, la variedad, **la partida**, y al final los contratos, detalles y enlaces de los candidatos, releídos; después de releer,
  el cálculo es el definitivo (la 8a del caso de uso no hace falta, como en la sección 3). Se dispara con `transaction.on_commit` y lo
  recupera el paso diario 25 (D-64 punto 9).
- **Recorte de reservas de cámara** (regla 6 de 8.9; 10c de PROD-REG-MRM y 3a de PROD-VNC-CAM), función pura `orden_de_recorte(lineas)`:
  primero las líneas cuya reserva es de compra-venta y después las de suministro; dentro de cada grupo, la de `fecha_entrega_reserva` más
  lejana primero y, si empatan, la reserva creada más tarde (mayor `id`). Se recorta hasta que lo reservado de la partida en reservas
  «activas» o «lista para entrega» iguale su nueva disponible. Una reserva cuya cantidad cubierta queda en 0 pasa a «liberada»; la línea
  queda en 0 (D-64 punto 7).
- **Invariantes nuevos** (sumar a `verificar_invariantes_de_reservas()`): ninguna reserva sin detalle con fecha de entrega, ni con detalle sin
  ella; ninguna reserva sin detalle que no sea de una cosecha `manual`; ninguna partida con lo reservado por encima de su disponible; toda
  partida tiene su «ingreso a cámara»; toda cosecha concretada tiene un registro de bitácora por lote y sus líneas de lote con cantidad
  cosechada; ninguna reserva «lista para entrega» con una línea de lote sin cosechar.
