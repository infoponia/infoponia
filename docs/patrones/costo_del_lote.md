# Patrón · Costo de un lote de plantas

Cómo se calcula, se guarda y se reparte el costo de un lote. Lo usan PRD-01 (lo crea), PRD-02 (la merma de una transición lo baja) y PRD-03 (merma completa,
aplicaciones de insumo). Fundamento: D-50 punto 5, MD-79 («decidido sin aplicar») y los casos PROD-CNC-SMB y PROD-REG-MRM. Si algo de acá contradice una decisión, manda la decisión: avisá.

## Por qué se guarda

El modelo (regla 15 de 8.9) define el costo por planta como la suma de los montos de consumo del lote dividida por la cantidad **inicial**. Pero MD-79 y los dos casos
de uso eligieron otro criterio, el del **promedio ponderado móvil**: cuando se pierden plantas, el costo de esas plantas sale del lote y las que quedan **conservan el costo
unitario que ya tenían**. Con la fórmula de la regla 15 no se puede: el costo por planta bajaría solo por perder plantas. Por eso el lote guarda su **costo acumulado**, que cambia con cada operación.
Manda el caso de uso (D-07). La regla 15 de 8.9 queda desactualizada hasta que se aplique MD-79 en Drive (está en `docs/temas_abiertos.md`).

## Qué se guarda y qué se calcula

| Dato | Dónde | Cálculo |
|---|---|---|
| `Lote.costo_acumulado` | Columna `DecimalField(14, 2)`, ≥ 0 | Se guarda |
| Costo por planta | No se guarda | `costo_acumulado ÷ cantidad_actual`, solo si `cantidad_actual > 0`; se muestra con 2 decimales |
| Costo de las plantas perdidas | No se guarda como columna | Se calcula en la operación (ver abajo) y se informa en el mensaje y en el registro de auditoría |

## Cuándo cambia el costo acumulado

| Operación | Efecto | Quién |
|---|---|---|
| Concretar una siembra | `costo_acumulado` = Σ `monto_consumo` de los consumos de esa siembra | PRD-01 |
| Merma de `n` plantas | Baja en `costo_de_la_merma(lote, n)` (abajo) | PRD-02 (desde la transición) y PRD-03 |
| Aplicación de insumos (PROD-REG-APL) | Suma a cada lote del alcance su parte del monto del consumo (imputación) | PRD-03 |
| Cosecha | Fuera de la ronda (D-45) | — |

Toda operación que lo cambia lo hace **con el lote bloqueado** (`docs/patrones/bloqueos.md`) y dentro de la misma transacción que el resto del caso de uso. Nunca se lo recalcula «desde cero» sumando consumos:
se actualiza solo con el efecto de la operación.

## Costo de las plantas perdidas

Dado un lote con `cantidad_actual = c`, `costo_acumulado = K` y una merma de `n` plantas (`0 < n ≤ c`):

- Si `n = c` (el lote se pierde entero): el costo de la merma es **`K` entero** y el lote queda con `costo_acumulado = 0`. Así no sobran centavos.
- Si `n < c`: `costo_de_la_merma = redondear(K × n ÷ c)` a 2 decimales con `ROUND_HALF_UP`, y `costo_acumulado = K − costo_de_la_merma`.

El costo por planta de las que quedan no cambia (salvo por el redondeo de a lo sumo un centavo por operación). Se calcula con `Decimal` y `quantize`, nunca con `float`.

### Ejemplos

| Lote | Merma | Costo de la merma | Costo acumulado después | Costo por planta después |
|---|---|---|---|---|
| `c = 200`, `K = 1.000,00` (5,00 por planta) | 20 | 100,00 | 900,00 | 5,00 |
| `c = 3`, `K = 10,00` (3,33… por planta) | 1 | 3,33 (10 × 1 ÷ 3 = 3,3333…) | 6,67 | 3,335 → se muestra 3,34 |
| `c = 3`, `K = 10,00` | 3 | 10,00 (el entero) | 0,00 | — (sin plantas) |
| `c = 7`, `K = 0,00` (siembra sin costo) | 2 | 0,00 | 0,00 | 0,00 |

El tercer ejemplo es el de «n = c»: si en cambio se calculara `10 × 3 ÷ 3` y se redondeara, daría lo mismo, pero con otros números (`K = 10,01`, `c = 3`) se puede perder un centavo, y por eso se trata aparte.

## Cálculo del costo de la siembra

`monto_consumo` de cada consumo = `cant_consumo × precio de referencia` del `InsumoInvernadero` **al concretar** (D-50, `docs/modelo/produccion.md`, «Consumo»), redondeado a 2 decimales con `ROUND_HALF_UP`.
El costo acumulado nace con la **suma de los montos ya redondeados** (no se redondea la suma): así coincide con lo que se ve en la bitácora, línea por línea.
Un insumo sin precio de referencia vale 0 y no impide concretar (el precio no es obligatorio en `InsumoInvernadero`); el resumen de la concreción avisa «Sin precio de referencia: no suma costo».

## Funciones (en `produccion/servicios/costos.py`)

| Función | Qué hace |
|---|---|
| `costo_de_la_merma(lote, cantidad) -> Decimal` | Lo de arriba. No escribe |
| `costo_por_planta(lote) -> Decimal \| None` | `None` si la cantidad actual es 0; 2 decimales |
| `redondear_monto(valor) -> Decimal` | `quantize(Decimal("0.01"), ROUND_HALF_UP)` |

Pruebas (en `produccion/tests/test_costos.py`): los cuatro ejemplos; `n = c` con `K = 10,01` y `c = 3`; que la suma de las mermas parciales hasta vaciar el lote da exactamente el costo de la siembra
(propiedad: `Σ costo_de_la_merma = K_inicial` cuando se pierde todo); que el costo nunca es negativo; que `cantidad_actual = 0` implica costo 0 (invariante).

## Reparto del costo de una aplicación de insumos entre lotes (lote 5, D-51 punto 4)

PROD-REG-APL reparte el monto de cada consumo «como costo de los lotes» entre los lotes de plantas del alcance. Entrada: el `monto` del consumo (2 decimales) y, por lote, sus **plantas en el alcance** (suma de `cant_agujeros_ocupados` de sus ocupaciones vigentes en los sectores del alcance; con el alcance «todo el invernadero», en todos sus sectores activos). Función pura: `costos.repartir_en_centavos(monto, plantas_por_lote) -> dict[lote_id, Decimal]`.

1. Se trabaja en **centavos enteros**: `C = monto × 100`.
2. Cuota exacta de cada lote: `C × plantas_i ÷ Σ plantas`. Cada lote recibe la **parte entera** de su cuota.
3. Los centavos que sobran (`C − Σ partes enteras`, siempre menos que la cantidad de lotes) se asignan **de a uno** a los lotes con **mayor resto**. Si hay empate de resto: el lote con más plantas en el alcance; si sigue el empate, el creado antes (menor `id`).
4. La suma de las partes es exactamente el monto. Cada parte se suma a `Lote.costo_acumulado` en su lote (que se bloquea, en orden de `id`).
5. Sin lotes con plantas en el alcance, o si la categoría del insumo es «como gasto», no hay imputaciones: el consumo queda «a gasto».

### Ejemplos

| Monto | Plantas por lote | Partes |
|---|---|---|
| 100,00 | L-1: 60, L-2: 40 | 60,00 y 40,00 |
| 100,00 | L-1: 1, L-2: 1, L-3: 1 | 33,34 · 33,33 · 33,33 (el centavo sobrante va al de menor `id`: empatan en resto y en plantas) |
| 10,00 | L-1: 2, L-2: 1 | 6,67 (resto 0,666…) y 3,33; suma 10,00 |
| 0,01 | L-1: 5, L-2: 3 | 0,01 al lote de más plantas (L-1) y 0,00 al otro: **se registra la imputación de 0,00 solo si el lote recibe más de cero**; si no, no se crea |
| 50,00 | L-1: 7 (un solo lote) | 50,00 |

Pruebas (`produccion/tests/test_costos.py`): los cinco ejemplos; la propiedad «la suma es exactamente el monto» con montos y plantas aleatorios (semilla fija); que el orden de las claves de entrada no cambia el resultado; que no hay partes negativas; que nunca se asigna más de un centavo extra a un lote.
