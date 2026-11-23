# CMP-06 · Corrección de recepción y reclamos al proveedor

Estado: pendiente | App: compras (y una función y un tipo en inventario) | Rama: feature/cmp-06-correccion-y-reclamos | Ronda: Compras 1

Depende de: **CMP-05**. Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Si una recepción se cargó de más, el Agrónomo la **corrige** (mientras no esté pagada y el lote tenga lo que se corrige): baja el
stock, el valor y genera el **asiento inverso**. El reclamo sin emitir que dejó la recepción (CMP-04) lo **emite** el Gerente al proveedor (sale un correo) y
luego lo **cierra**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-COR-RCP | Corregir Recepción | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |
| CMP-EMT-RCL | Emitir Reclamo a Proveedor | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |
| CMP-CRR-RCL | Cerrar Reclamo a Proveedor | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |

## Leer

- Casos de uso: `correccion_y_reclamos.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`CorreccionRecepcion`, `DetalleCorreccionRecepcion`, `ReclamoProveedor` ya creado en CMP-04), docs/modelo/inventario.md (tipos de
  movimiento).
- Decisiones: D-90 (máximo corregible, tipo nuevo, vínculos), D-89 (corrección inversa), D-91 (no se corrige lo pagado), D-84 a D-86, D-44.
- API: docs/api/stock.md (`registrar_salida_por_correccion_de_recepcion`), docs/api/asientos.md, docs/api/correo.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md, docs/patrones/bloqueos.md.
- Pantallas: `VIEWS.c_cor`, `tabRcl`, `VIEWS.c_rcl`, `panelGer` («reclamos sin emitir»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-04 y CMP-05; `inventario/models.py` (`MovimientoInsumo.Tipo`), `inventario/servicios/stock.py`.

## Límites

- Crea modelos: `CorreccionRecepcion`, `DetalleCorreccionRecepcion` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0006_correcciones_y_reclamos.py`; **una de `inventario`, solo de `choices`**, con
  `salida_por_correccion_de_recepcion`; una de `core` con `correccion_recepcion`, `emision_reclamo`, `cierre_reclamo`.
- Permitido fuera de la app: `inventario/models.py` (el tipo nuevo) y su migración; `inventario/servicios/stock.py` (**solo**
  `registrar_salida_por_correccion_de_recepcion`, con pruebas en `inventario/tests/test_salida_por_correccion.py`); `core/models.py` (acciones) y su
  migración; `docs/modelo/inventario.md` (el tipo nuevo); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: notas de crédito o devoluciones con dinero (no están en el alcance de la ronda).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** y el tipo nuevo de movimiento. — pruebas: `test_modelos.py` (amplía), `inventario/tests/test_salida_por_correccion.py`.
2. **CMP-COR-RCP** (máximo corregible = recibido − ya corregido, y no más que lo que queda en el lote; asiento inverso). — pruebas:
   `test_cmp_cor_rcp.py`, `test_correcciones_concurrencia.py` (corrección contra consumo del lote; corrección contra pago).
3. **CMP-EMT-RCL** y **CMP-CRR-RCL** (Gerente; emitir resuelve la alerta y manda el correo después del commit). — pruebas: `test_cmp_emt_rcl.py`, `test_cmp_crr_rcl.py`.
4. **Pantallas**, y completar la ficha del proveedor y de la orden (correcciones y reclamos). — pruebas: `test_reclamos_vistas.py`.

## Hecho cuando

- Una recepción se corrige: el lote baja, el valor de la línea baja, el asiento inverso cuadra y el pago pendiente se recalcula; una pagada no se
  corrige.
- El Gerente emite el reclamo con sus inconvenientes, el proveedor recibe el correo y después lo cierra.
- Con esta tarea, la ronda «Compras 1» queda completa: pruebas verdes, sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Corregí una recepción en 2 unidades: mirá el movimiento nuevo en el lote y el asiento inverso.
2. Como Gerente, emití el reclamo de la recepción con «mercadería dañada» (mirá el correo de desarrollo) y cerralo.

## Cierre (M3)

README de tareas, plan de la ronda (marcala cerrada), `docs/estado.md`, `docs/disparadores.md` (cerrá lo que quede de compras).
