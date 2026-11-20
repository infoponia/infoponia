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

## Pruebas de tu app

`inventario/tests/fabricas.py` suma `variedad_con_semilla(cultivo=..., perfil=..., etapas=...)` (extiende la fábrica `variedad` de `maestros`: crea además la semilla, como
el alta) y `usos_de_variedad_de_prueba(...)` (administrador de contexto que registra un `registrar_uso_de_variedad` falso). Usalas: no armes
ciclos a mano.
