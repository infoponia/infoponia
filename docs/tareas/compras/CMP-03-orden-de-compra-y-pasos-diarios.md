# CMP-03 · Orden de compra y pasos diarios de compras

Estado: pendiente | App: compras | Rama: feature/cmp-03-orden-de-compra-y-pasos-diarios | Ronda: Compras 1

Depende de: **CMP-02b**. No depende de la contabilidad (la orden no genera asiento: D-91, D-86).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo **genera** la orden de compra eligiendo, línea por línea, la cotización más conveniente (puede repartir entre
proveedores); el Gerente la **aprueba** o la rechaza; al aprobarse, las cantidades pasan a **tránsito** en el stock. Además, los tres **pasos
diarios** que vencen pedidos, recuerdan la validez y cancelan los que no tienen cotización elegible.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-GNR-ODC | Generar Orden de Compra | docs/casos_de_uso/compras/ordenes_de_compra.md | — |
| CMP-APR-ODC | Aprobar Orden de Compra (y rechazar) | docs/casos_de_uso/compras/ordenes_de_compra.md | — |
| CMP-CNS-ODC | Consultar Orden de Compra | docs/casos_de_uso/compras/ordenes_de_compra.md | Recepciones, pagos y reclamos de la ficha: CMP-04 a CMP-06 |
| (D-87, punto 4) | Pasos diarios 60, 61 y 62 | docs/casos_de_uso/compras/ordenes_de_compra.md («Pasos diarios 60 a 62») | — |
| (H21) | A quién van los avisos si el Agrónomo del pedido ya no está | docs/casos_de_uso/compras/ordenes_de_compra.md («Cambio del punto 6») | Usa `destinatarios_por_destino` de CMP-02a |
| CMP-BAJ-PRV (precondición c) | Orden aprobada sin recibir impide la baja del proveedor | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |

## Leer

- Casos de uso: `ordenes_de_compra.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`OrdenCompra`, `DetalleOrdenCompra`, `AlertaCompras`; R026 derivado).
- Decisiones: D-87 (puntos 3 y 4: pasos diarios y sus campos técnicos), D-89, D-90 (solo «tránsito»), D-56 (proceso diario), D-36, D-42, D-44.
- API: docs/api/stock.md («Escritura de compras»: `sumar_transito`), docs/api/notificaciones.md, docs/api/alertas.md; el contrato del
  proceso diario es D-56 y el encabezado de `core/procesos.py`.
- Patrones: docs/patrones/bloqueos.md (orden de compras), docs/patrones/stock.md, docs/patrones/auditoria.md.
- Pantallas: `tabOdc`, `VIEWS.c_gen` (comparar cotizaciones y generar), `VIEWS.c_apr` (revisar y decidir), `VIEWS.c_odc`, `panelAgr` («Pedidos que
  vencieron»), `panelGer` («Órdenes pendientes de aprobación»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-02a/02b; `core/procesos.py` (`registrar_paso_diario`, `ResumenDePaso`) y un paso existente como modelo;
  `inventario/servicios/stock.py`; `maestros/alertas.py` (`registrar_tipo_de_alerta`, `registrar_enlace_de_alerta`); `core/inicio.py`
  (`registrar_seccion_de_inicio`).

## Límites

- Crea modelos: `OrdenCompra`, `DetalleOrdenCompra`, `AlertaCompras`; campos técnicos `Pedido.aviso_vencimiento_dado` y
  `Cotizacion.recordatorio_validez_para` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0003_ordenes.py` (o el número que siga); una de `core` con `generacion_orden_compra`, `aprobacion_orden_compra`,
  `rechazo_orden_compra`.
- Permitido fuera de la app: `inventario/servicios/stock.py` (**solo** `sumar_transito` y `restar_transito`, tal cual docs/api/stock.md, con sus
  pruebas en `inventario/tests/test_transito.py`); `core/models.py` (acciones) y su migración; `core/procesos.py` (**solo el comentario** de la tabla de
  órdenes: filas 60, 61 y 62); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: recepción (CMP-04), pago (CMP-05).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** y el derivado R026 (estado de recepción de la línea). — pruebas: `test_modelos.py` (amplía).
2. **Tránsito en inventario.** — pruebas: `inventario/tests/test_transito.py`.
3. **CMP-GNR-ODC** (con la cotización elegible: vigente, con validez, del proveedor activo). — pruebas: `test_cmp_gnr_odc.py`.
4. **CMP-APR-ODC** (aprobar suma tránsito; rechazar vuelve el pedido a «con cotizaciones»); impedimento `orden_de_compra_aprobada` y precondición
   c de la baja del proveedor. — pruebas: `test_cmp_apr_odc.py`, `test_ordenes_concurrencia.py` (aprobar contra la baja del proveedor; dos
   aprobaciones a la vez).
5. **Pasos diarios 60, 61, 62** (idempotentes, con `ResumenDePaso`). — pruebas: `test_pasos_diarios_compras.py` (correr dos veces el mismo día no
   repite avisos ni cancelaciones).
6. **CMP-CNS-ODC**, las secciones de inicio y las pantallas. — pruebas: `test_cmp_cns_odc.py`, `test_ordenes_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: la sección de inicio del Gerente (se anota como disparador; la lista de órdenes ya lo cubre).

## Hecho cuando

- Del pedido sale una orden con líneas de dos proveedores; el Gerente la aprueba y el tránsito del insumo sube en ese invernadero; rechazada, el
  pedido vuelve a admitir otra orden.
- Los pasos 60 a 62 corren solos, son idempotentes y aparecen en el resumen del proceso diario.
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Con el pedido de CMP-02a cotizado por dos proveedores, generá la orden repartiendo líneas.
2. Como Gerente, aprobala: el stock del invernadero muestra la cantidad en tránsito.
3. Corré `python manage.py proceso_diario --fecha <un día después de la fecha límite>` con la fecha límite vencida de otro pedido: queda vencido y el Agrónomo recibe el
   aviso una sola vez.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md` (cerrá «orden aprobada» de «Cuando existan los pedidos de
`compras`»), la tabla de pasos de docs/core (60 a 62).
