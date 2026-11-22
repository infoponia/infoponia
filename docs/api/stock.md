# API · Stock de insumos (`inventario.servicios.stock` y `inventario.servicios.insumos_invernadero`)

Para quien programa `produccion` (planificar, concretar, aplicar insumos), `compras` o la pantalla de inicio sin leer el código de
`inventario`. Versión de INV-02. Las reglas están en `docs/patrones/stock.md`. Si algo de acá contradice una decisión o un caso de uso,
manda la decisión o el caso de uso: avisá.

`inventario` es de nivel 4: `produccion` (nivel 5) puede importarlo. **No** al revés (regla A1 de D-37).

## Lectura (no escribe, no bloquea)

```python
from inventario.servicios import stock
```

| Función | Devuelve |
|---|---|
| `stock.hoy()` | La fecha de hoy: `django.utils.timezone.localdate()` (el proyecto ya tiene `TIME_ZONE = "America/Argentina/Buenos_Aires"` y `USE_TZ = True`). Usala siempre que necesites «hoy»: nada de `date.today()` |
| `stock.existencias(ids, hoy=None) -> dict[int, Existencia]` | Por `InsumoInvernadero`: `Existencia(actual, vigente, reservado, libre, transito, minimo, bajo_minimo, inconsistente)`. Una consulta por tabla |
| `stock.disponible_para_planificar(ids, fecha) -> dict[int, Decimal]` | `max(0, libre a la fecha)`: sin los lotes que estarán vencidos en `fecha` (regla 8 de 8.4) |
| `stock.proponer_lotes_fefo(iin_id, cantidad, fecha) -> Propuesta` | `Propuesta(partes=[(lote_id, cantidad)], resto)`: FEFO, sin vencidos ni faltante; `resto` es lo que ningún lote cubre |
| `stock.ordenes_sin_cobertura(iin_id, hoy=None, vigente=None)` | Las `OrdenQueReserva` que el stock vigente no cubre, de la más cercana a la más lejana. Con `vigente` calcula contra ese stock en lugar del actual (lo usa el resumen 12b del ajuste: el stock que quedaría) |
| `stock.validar_cantidad(valor, unidad)` (`inventario/unidades.py`) | `Decimal` cuantizado o `ValidationError` con el mensaje de «decimales que admite la unidad» |
| `insumos_invernadero.habilitados(invernadero_id)` | Los `InsumoInvernadero` activos de un invernadero activo, con su insumo y categoría (para listas de elección) |

## Escritura

Todas corren **dentro de la transacción de quien llama**, con el invernadero **ya bloqueado** por quien llama (`bloquear_invernadero_activo`) y
vuelven a leer y a bloquear lo suyo (`InsumoInvernadero` y lotes, en orden de id). No auditan: lo hace el caso de uso que llama.

| Función | Qué hace |
|---|---|
| `stock.registrar_salida_por_consumo(iin_id, partes, *, origen_id, fecha=None) -> list[MovimientoInsumo]` | `partes = [(lote_id, cantidad)]`; **`origen_id` obligatorio (D-52 punto 5): el id del `OrigenDocumento` que origina el movimiento (el `Consumo`, que `produccion` crea antes de llamar)**; `fecha` opcional (D-50 punto 7): la fecha del movimiento es esa con la hora actual; sin `fecha`, la de hoy. La usa PRD-01 con la fecha efectiva de la siembra. Descuenta de cada lote, crea **un** movimiento «salida por consumo» por lote y manda lo que falta al **faltante sin lote** (regla 4 de 8.23); no bloquea (regla 5 de 8.13). Cada movimiento queda con `origen = origen_id`: no hace falta ninguna tabla de enlace en tu app (D-52); el consumo lee sus movimientos con `consumo.movimientos_de_insumo`. Después llama a `reevaluar_alertas_del_insumo`. `ValueError` si los datos o las cantidades son inválidos; si `partes` repite un lote, lo consolida en un solo movimiento; si el consumo supera lo disponible, crea o incrementa el faltante sin lote (y no lo toca si los lotes alcanzan) |
| `alertas_de_stock.reevaluar_alertas_del_insumo(iin_id, hoy=None) -> Reevaluacion` | `Reevaluacion(creadas, resueltas)` (listas de `Alerta`) para los `datos` de tu registro de auditoría |
| `insumos_invernadero.habilitar_insumo(actor, insumo_id, invernadero_id, cant_min, referencia_precio)` | CMP-HAB-IIN completo (con sus permisos y su auditoría). Lo llama la pantalla de INV-02 y, cuando una semilla no está habilitada, PRD-01 (PROD-PNF-SMB, extensión del caso de uso) |

Todo lo demás (ajustes, mínimos, deshabilitar, vencimientos) lo hacen los servicios de `inventario`; `produccion` no lo llama.

## Reglas para quien llama

1. Nunca cambies `cantidad_disponible` de un lote ni cree un `LoteInsumo`/`MovimientoInsumo` por tu cuenta: es de `inventario` (regla 1 de 8.19).
2. Si tu operación crea reservas, bloqueá antes el invernadero y el `InsumoInvernadero` (orden de `docs/patrones/stock.md`, sección 5) y
   leé `disponible_para_planificar` **después** de bloquear.
3. Si tu operación cierra o cancela reservas, llamá a `reevaluar_alertas_del_insumo` de cada `InsumoInvernadero` afectado, en la misma
   transacción (la alerta «stock inconsistente» se resuelve «cualquiera sea la operación que lo logre»; regla 6 de 8.13).
4. `Decimal`, nunca `float`; y en la auditoría, como texto.

## Pruebas de tu app

`inventario/tests/fabricas.py` tiene `tipo_de_insumo`, `insumo`, `existencia`, `lote`, `faltante`, `reservas_de_prueba` y
`verificar_invariantes` (ver `docs/patrones/stock.md`, sección 7). Usalas: no armes lotes a mano.
