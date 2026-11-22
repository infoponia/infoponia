# API · Variedades y su ciclo (`inventario/servicios/variedades.py` y `ciclos.py`)

Lo que `produccion` (PRD-01 a PRD-04) y las rondas siguientes llaman para leer variedades, ciclos y semillas, sin leer el código de
`inventario` ni consultar las tablas a mano. Lo implementa INV-03. Si algo de acá no alcanza, frená (L9). Los puntos de extensión que
**registra** `produccion` están en `docs/api/extensiones_de_inventario.md`, sección «Variedades».

Las tablas `Variedad`, `Ciclo` y `EtapaProductiva` están en `maestros` (`docs/modelo/maestros.md`); `Semilla`, en `inventario`
(`docs/modelo/inventario.md`). Estas funciones son de solo lectura salvo `bloquear_variedad`.

## Lectura (`inventario/servicios/ciclos.py`)

| Función | Qué devuelve |
|---|---|
| `etapas_de(variedad_ids) -> dict[int, list[EtapaDelCiclo]]` | Las etapas de cada variedad **en el orden del catálogo** (`TipoEtapa.puesto_global`). `EtapaDelCiclo = namedtuple("EtapaDelCiclo", "etapa_id tipo_id codigo nombre puesto_global duracion_dias")`. Una consulta para toda la lista |
| `duracion_del_ciclo(variedad_ids) -> dict[int, int]` | La suma de las duraciones de sus etapas (derivada, MD-70) |
| `dias_hasta_maduracion(variedad_ids) -> dict[int, int]` | La suma de las etapas **anteriores** a Maduración. La cosecha estimada de una siembra es `fecha_siembra + dias_hasta_maduracion` (regla de «fecha estimada de cosecha» de PROD-PNF-SMB) |
| `tipos_de_etapa_de(variedad) -> list[TipoEtapa]` | Solo los tipos incluidos, en orden. Lo usa PRD-01 para exigir un sector por cada etapa |

## Lectura (`inventario/servicios/variedades.py`)

| Función | Qué devuelve |
|---|---|
| `obtener_variedad(variedad_id) -> Variedad` | La variedad con su cultivo (`select_related`). `Http404` si no existe |
| `semilla_de(variedad_ids) -> dict[int, Semilla]` | La semilla de cada variedad (siempre existe: se crea con ella) |
| `rangos_de(variedad_ids) -> dict[int, Rangos]` | `Rangos = namedtuple("Rangos", "temp_ambiente humedad intensidad_luz fotoperiodo")`, cada uno un `RangoAmbiental(minimo, maximo)` con `Decimal`. Es lo que cruza el «umbral efectivo» (PROD-PNF-SMB) |
| `uso_de_variedades(variedad_ids) -> dict[int, UsoDeVariedad]` | Lo que informan los registrantes de `registrar_uso_de_variedad` (neutro sin ellos) |
| `invernaderos_que_usan(variedad_ids) -> dict[int, set[int]]` | Ids de invernaderos **activos** que usan la variedad: semilla habilitada (`InsumoInvernadero` activo) o lotes activos |
| `puede_gestionar(actor, variedad) -> ResultadoGestion` | `ResultadoGestion(puede: bool, quienes: list[str])` (regla 1 de PROD-MOD-VAR); `quienes` es «Invernadero Norte (Ana Pérez)» o «Invernadero Sur (sin Agrónomo)» |
| `acciones_permitidas(actor, variedad) -> AccionesDeVariedad` | `modificar`, `dar_de_baja`, `reactivar` (bool) y `motivo` (texto del botón deshabilitado) |
| `variedades_activas(cultivo_id=None)` | Las variedades activas de cultivos activos con su ciclo; **PRD-01 la usa para ofrecer qué sembrar** (la regla «cultivos con sus variedades activas» del paso 4 de PROD-PNF-SMB) |
| `umbral_efectivo(invernadero_ids) -> dict[int, UmbralEfectivo \| None]` | El umbral efectivo de cada invernadero. Ver la sección «Umbral efectivo» |
| `variables_incompatibles(umbral, rangos) -> list[VariableIncompatible]` | Las variables en las que una variedad con esos `rangos` dejaría vacío el umbral. Ver la sección «Umbral efectivo» |

## Umbral efectivo (`inventario/servicios/variedades.py`)

Decidido el 21/11/2026: el umbral efectivo se calcula en **una sola función**, en `inventario`, porque lo necesitan Planificar Siembra
(`produccion`, PRD-01) y el módulo IoT (`iot`: lecturas, fotoperíodo y panel). Así lo pide IOT-ENT-INF («Requisitos especiales»: «una sola
función del dominio, sin duplicarla»). Ninguna otra app calcula la intersección de rangos por su cuenta.

**`umbral_efectivo(invernadero_ids) -> dict[int, UmbralEfectivo | None]`**

- **Definición** (regla «Umbral efectivo» de PROD-PNF-SMB y de IOT-ENT-INF): la intersección de los rangos de temperatura ambiente, humedad,
  intensidad lumínica y fotoperíodo de las variedades con lotes activos o con órdenes de siembra a realizar en el invernadero. Las variedades
  salen de `variedades_presentes(invernadero_ids)` (el punto `registrar_variedades_presentes`, que registra `produccion`) y sus rangos, de
  `rangos_de`.
- **Todo id pedido figura en el resultado.** Vale `None` si el invernadero no tiene variedades presentes. Sin registrante (hasta PRD-01),
  todos valen `None`.
- **Si tiene variedades**, vale `UmbralEfectivo = namedtuple("UmbralEfectivo", "temp_ambiente humedad intensidad_luz fotoperiodo variedad_ids")`:
  - `variedad_ids`: `frozenset` con las variedades que lo componen.
  - Cada variable es `LimitesDelUmbral = namedtuple("LimitesDelUmbral", "minimo maximo variedad_minimo_id variedad_maximo_id")`, con
    `Decimal`. `minimo` es el mayor de los mínimos, y `variedad_minimo_id`, la variedad que lo fija; `maximo` es el menor de los máximos, y
    `variedad_maximo_id`, la que lo fija. Si dos variedades empatan, se toma la de menor id, para que el resultado sea siempre el mismo.
  - Una variable vale `None` si en ella los rangos no se superponen (`max(mínimos) > min(máximos)`). Que se toquen en un extremo no es
    vacío: el umbral queda con `minimo == maximo`, como en `incompatibilidades_de_rangos`.
- **No se guarda:** se calcula en cada llamada, así un cambio de rangos (PROD-MOD-VAR) rige desde la llamada siguiente.
- **Consultas:** las del registrante más una de `rangos_de` para todas las variedades de todos los invernaderos pedidos. Nunca una por
  invernadero.

**`variables_incompatibles(umbral, rangos) -> list[VariableIncompatible]`**

- Función pura, sin consultas. `VariableIncompatible = namedtuple("VariableIncompatible", "variable variedad_limitante_id")`, con `variable`
  igual al nombre del campo de `Rangos` (`temp_ambiente`, `humedad`, `intensidad_luz` o `fotoperiodo`).
- Es la regla de compatibilidad de PROD-PNF-SMB: una variedad es compatible si, al sumarla, ninguna intersección queda vacía.
  - Con `umbral` en `None` (invernadero sin variedades), la lista es vacía: toda variedad es compatible.
  - Una variable es incompatible si su intersección con el umbral queda vacía. `variedad_limitante_id` es la variedad que fija el límite que
    choca: la de `variedad_maximo_id` si el mínimo de `rangos` supera el máximo del umbral, o la de `variedad_minimo_id` en el caso contrario.
  - Si esa variable del umbral ya es `None` (variedades presentes incompatibles entre sí, por ejemplo tras «Guardar igual» en
    PROD-MOD-VAR), es incompatible, con `variedad_limitante_id` en `None`.
- La usa PRD-01 para el paso 4, la extensión 4b y la verificación bajo bloqueo (extensión 18b) de PROD-PNF-SMB.

## Bloqueo

`bloquear_variedad(variedad_id) -> Variedad`: `FOR NO KEY UPDATE`, ya releída, **solo si está activa** (si no, `ValidationError` de código
`variedad_inactiva`). **Quien crea un lote o una orden de siembra o de transición de una variedad la llama antes de crear** (después de
bloquear el invernadero; orden de `docs/patrones/stock.md`, sección 5). Motivo: la clave foránea sola no alcanza (toma `FOR KEY SHARE`, que no
choca con `FOR NO KEY UPDATE`), y sin este bloqueo una baja de la variedad, un cambio de perfil o un cambio de etapas pasarían a la vez que la
creación del primer lote (reglas 3 y 4 de PROD-MOD-VAR y precondiciones d y e de PROD-BAJ-VAR).

## Lo que no hace `produccion`

1. No cambia el nombre, el estado ni los datos de una variedad ni de su semilla: son de INV-03.
2. No crea `Semilla`: la crea el alta de la variedad.
3. No calcula la duración del ciclo ni los días hasta Maduración por su cuenta: usa `ciclos.py`.
4. No calcula el umbral efectivo ni la compatibilidad de una variedad con él: usa `umbral_efectivo` y `variables_incompatibles`.

## Pruebas de tu app

`inventario/tests/fabricas.py` suma `variedad_con_semilla(cultivo=..., perfil=..., etapas=...)` (extiende la fábrica `variedad` de `maestros`: crea además la semilla, como
el alta), `usos_de_variedad_de_prueba(...)` (administrador de contexto que registra un `registrar_uso_de_variedad` falso) y
`variedades_presentes_de_prueba({invernadero_id: {variedad_id, ...}})` (lo mismo con `registrar_variedades_presentes`, para probar
`umbral_efectivo` sin lotes reales). Usalas: no armes ciclos a mano.
