# API · Puntos de extensión de `inventario` (INV-01, INV-02 e INV-03)

Contrato para las tareas que crean lo que `inventario` no puede importar (regla A4 de D-37): reservas y órdenes (`produccion`),
pedidos, órdenes de compra y tránsito (`compras`). Cada app los registra en su `AppConfig.ready()`. **Sin registrantes, cada punto da un
resultado neutro** (0, lista o diccionario vacío) e `inventario` se prueba con registrantes falsos (`mock.patch.object` sobre las listas
de módulo, o el administrador de contexto `reservas_de_prueba` de `inventario/tests/fabricas.py`).

Están en `inventario/extensiones.py`, con el mismo estilo que `maestros/extensiones.py`.

Contrato común: todo corre **dentro de la transacción** del servicio de `inventario`, **después** de que este tomó el invernadero y
sus propias filas (orden de `docs/patrones/stock.md`, sección 5). Un registrante que bloquee filas propias lo hace después, en orden de id.
Reciben **listas de ids** y devuelven diccionarios por id: una consulta por tabla para toda la lista, nunca una por fila.

| Registro | Firma de la función registrada | Qué calcula `inventario` con ella | Quién se registra |
|---|---|---|---|
| `registrar_reservas_de_insumo(funcion)` | `funcion(ids) -> dict[int, Decimal]`: por `InsumoInvernadero`, lo reservado por las `ReservaInsumo` **activas**; lo que no figura es 0 | `reservado_de(iin_ids)`, y con él el stock libre, «bajo el mínimo», «stock inconsistente», el consumo directo de una categoría (regla 4 de CMP-MOD-TIN y regla 3 de CMP-MOD-INS) y el impedimento `reservas_activas` | `produccion` (PRD-01: reservas de órdenes de siembra y de transición a realizar) |
| `registrar_ordenes_que_reservan(funcion)` | `funcion(ids) -> dict[int, list[OrdenQueReserva]]`, con `OrdenQueReserva = namedtuple("OrdenQueReserva", "orden_id texto cantidad fecha_programada url")` | `ordenes_que_reservan(iin_ids)`: los avisos que nombran órdenes, «sin cobertura» y la descripción de la alerta «stock inconsistente». Las ordena `inventario` (fecha programada, después id) | `produccion` |
| `registrar_impedimento_de_deshabilitacion(funcion)` | `funcion(insumo_invernadero) -> list[Impedimento]` (el `namedtuple` de `maestros.extensiones`: `codigo`, `texto`, `como_resolver` y `url` opcional, D-98). Códigos: `orden_de_compra_aprobada`, `pedido_en_curso` | `impedimentos_de_deshabilitacion(iin)`: los suyos (`stock_distinto_de_cero`, `reservas_activas`, `cantidad_en_transito`) y los de los registrantes, juntos, sin quedarse con el primero. Los usa CMP-DSH-IIN, CMP-BAJ-INS y la baja del invernadero | `compras`: CMP-02b (`pedido_en_curso`) y CMP-03 (`orden_de_compra_aprobada`) |

**Qué cuenta como «en curso» (H20; D-87 punto 5 y D-98):** un pedido **«en cotización»** que pide ese `InsumoInvernadero` (hecho en CMP-02b, con la URL del pedido); una orden aprobada con una línea de ese `InsumoInvernadero` que no está recibida completa ni cerrada con faltante (CMP-03).

## Lo que `inventario` registra en `maestros`

| Punto de `maestros` | Qué registra INV-02 |
|---|---|
| `maestros.extensiones.registrar_impedimento_de_baja` | Por cada `InsumoInvernadero` activo del invernadero: stock distinto de cero (código `stock_distinto_de_cero`), cantidad en tránsito (`cantidad_en_transito`) y los de `registrar_impedimento_de_deshabilitacion` (precondición f de PROD-BAJ-INV) |
| `maestros.extensiones.registrar_efecto_de_baja` | Pasa a inactivos los `InsumoInvernadero` del invernadero y escribe un registro `baja_insumo_invernadero` por cada uno (postcondición c y parte de la f de PROD-BAJ-INV) |
| `maestros.alertas.registrar_tipo_de_alerta` | Los cuatro tipos de `docs/patrones/stock.md`, sección 4 |
| `maestros.extensiones.registrar_uso_de_cultivo`, `registrar_semillas_de_cultivo` y `registrar_variedades_de_cultivo` | **No** son de INV-02: los registra INV-03 (ver abajo) |

## Variedades (los declara INV-03)

Misma convención que los de arriba (en `inventario/extensiones.py`, sin registrantes dan el neutro, se prueban con registrantes falsos,
reciben listas de ids y devuelven diccionarios por id). Los registra `produccion` (PRD-01) y, el de contratos, `comercial` (ronda futura).

| Registro | Firma de la función registrada | Qué calcula `inventario` con ella | Quién se registra |
|---|---|---|---|
| `registrar_uso_de_variedad(funcion)` | `funcion(variedad_ids) -> dict[int, UsoDeVariedad]`, con `UsoDeVariedad = namedtuple("UsoDeVariedad", "con_lotes lotes_activos ordenes_a_realizar invernaderos_con_lotes_activos")`: `con_lotes` (bool: tiene algún lote, aunque esté terminado), `lotes_activos` (int), `ordenes_a_realizar` (int: órdenes de siembra de la variedad y de transición de sus lotes que están «a realizar») e `invernaderos_con_lotes_activos` (`frozenset` de ids). Lo que no figura es `UsoDeVariedad(False, 0, 0, frozenset())` | `uso_de_variedades(ids)`. Con él: los invernaderos que usan la variedad (regla 1 de PROD-MOD-VAR), si se pueden tocar las etapas (regla 3), si se puede cambiar el perfil (regla 4: `lotes_activos` o `ordenes_a_realizar` mayores que 0) y los invernaderos donde mirar los rangos (regla 5) | `produccion` (PRD-01) |
| `registrar_variedades_presentes(funcion)` | `funcion(invernadero_ids) -> dict[int, set[int]]`: por invernadero, los ids de las variedades con lotes activos u órdenes de siembra a realizar (la misma definición del «umbral efectivo» de PROD-PNF-SMB). Lo que no figura es un conjunto vacío | `variedades_presentes(invernadero_ids)`, para la advertencia de rangos (regla 5 de PROD-MOD-VAR) y para `umbral_efectivo(invernadero_ids)` (`docs/api/variedades.md`, «Umbral efectivo»; lo usan PRD-01 y el IoT) | `produccion` (PRD-01) |
| `registrar_impedimento_de_baja_de_variedad(funcion)` | `funcion(variedad) -> list[Impedimento]` (el `namedtuple` de `maestros.extensiones`: `codigo`, `texto`, `como_resolver`). Códigos: `lotes_activos`, `ordenes_a_realizar`, `contratos_abiertos` | `impedimentos_de_baja_de_variedad(variedad)`: los registrados, juntos (regla 2 de PROD-BAJ-VAR). Los textos dicen cuántos y cuáles | `produccion` (los dos primeros); `comercial` (`contratos_abiertos`) |

**Cuándo se leen:** dentro de la transacción del servicio, **después** de que este tomó los bloqueos de la sección 5 de `docs/patrones/stock.md`.
Un registrante que bloquee filas propias lo hace después de la variedad.

## Lo que `inventario` registra en `maestros` (INV-03)

| Punto de `maestros` | Qué registra INV-03 |
|---|---|
| `registrar_semillas_de_cultivo(contar, renombrar)` | `contar`: las semillas de las variedades del cultivo; `renombrar`: las renombra a «Semilla {cultivo nuevo} {variedad}» y escribe **un registro `modificacion_semilla` por semilla** (afectados: semilla, variedad y cultivo; `cambios`: el nombre antes y después). Bloquea las filas de `Insumo` en orden de id |
| `registrar_uso_de_cultivo(funcion)` | Invernaderos activos que usan alguna variedad del cultivo: los de la semilla habilitada (`InsumoInvernadero` activo) más los de `uso_de_variedades(...).invernaderos_con_lotes_activos` |
| `registrar_variedades_de_cultivo(funcion)` | El cuerpo (tabla) y la cabecera (botones) de variedades de cada tarjeta de cultivo |

## Prueba mínima de cada registrante (para quien se registra)

Tres pruebas: devuelve lo esperado con datos; devuelve el neutro sin datos; no hace consultas por fila.
