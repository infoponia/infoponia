# CMP-02a · Pedido de cotización y portal del proveedor

Estado: pendiente | App: compras (y una constante en core) | Rama: feature/cmp-02a-pedido-y-portal-del-proveedor | Ronda: Compras 1

Depende de: **CMP-01**, USR-10 (correo público, hecha), INV-02 (hecha). **No depende de la contabilidad.** Si CMP-01 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo arma un **pedido** de cotización (con los insumos bajo el mínimo, para uno o varios invernaderos) e invita
proveedores; cada proveedor recibe un **enlace** y cotiza **sin cuenta**, una sola vez. El Agrónomo y el Gerente consultan los pedidos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-RLZ-PED | Realizar Pedido | docs/casos_de_uso/compras/pedidos.md | 6a obsoleta (P5); 12a: el aviso al Agrónomo sale, el reintento es «Reenviar invitación» de CMP-02b |
| CMP-ENV-COT | Enviar Cotización (portal del proveedor) | docs/casos_de_uso/compras/pedidos.md | Con las actualizaciones de A0 (cantidad mayor que la pedida, total por línea, plazo ≥ 1) |
| CMP-CNS-PED | Consultar Pedido | docs/casos_de_uso/compras/pedidos.md | Regla 7 («Reenviar invitación») y la acción «Cancelar»: CMP-02b; «Generar orden»: CMP-03 |

## Leer

- Casos de uso: el extracto `pedidos.md`, **solo** CMP-RLZ-PED, CMP-ENV-COT y CMP-CNS-PED, sus actualizaciones de A0 y su «Cómo se aplica».
- Modelo: docs/modelo/compras.md (`Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`, `Cotizacion`, `DetalleCotizacion`).
- Decisiones: D-87, D-88 (la del enlace), D-89 (precios), D-65 (enlace del cliente, del que se copia), D-54, D-36, D-37, D-42, D-44.
- API: docs/api/stock.md («Lectura»), docs/api/notificaciones.md, docs/api/correo.md.
- Patrones: docs/patrones/enlace_del_proveedor.md **y** docs/patrones/enlace_del_cliente.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md,
  docs/patrones/stock.md (sección 5).
- Pantallas: docs/prototipos/compras_contabilidad/ — `VIEWS.c_main`, `tabPed`, `VIEWS.c_pednew`, `VIEWS.c_ped`, `VIEWS.c_cotz` (sin el selector «enlace
  de ejemplo», que es solo del prototipo), `panelAgr` (la sección «pedidos que vencieron» va en CMP-03).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `core/enlaces.py`, `core/correo.py`, `core/notificaciones.py`; `core/models.py` (`RegistroAuditoria.objects.registrar` y, si ya
  existe, `rol_externo` y `ROL_CLIENTE_ENLACE`); `inventario/servicios/stock.py` (`existencias`), `inventario/servicios/insumos_invernadero.py`
  (`habilitados`, `habilitar_insumo`); `maestros/servicios/configuracion.py` (`obtener`); `maestros/servicios/invernaderos.py`
  (`bloquear_invernadero_activo`); si ya existe, `comercial/servicios/enlaces.py` y `comercial/views_cliente.py` como modelo.

## Límites

- Crea modelos: `Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`, `Cotizacion`, `DetalleCotizacion` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0002_pedidos_y_cotizaciones.py`; una de `core` con las acciones (`alta_pedido`, `alta_cotizacion` y las que
  uses) y, si no existe, `rol_externo` + `ROL_CLIENTE_ENLACE` + `ROL_PROVEEDOR_ENLACE` (D-88 punto 5; D-65 punto 8).
- Permitido fuera de la app: `core/models.py` (acciones, `ROL_PROVEEDOR_ENLACE` y, si falta, `rol_externo` con su prueba en `core/tests/`);
  `config/urls.py` (la URL pública `proveedor/`); al cerrar, los archivos de M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: cancelar, reenviar, impedimentos y lo que cancela solo (CMP-02b); la orden de compra y los pasos diarios (CMP-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migración** con todas sus restricciones (C8 por la única `(pedido, proveedor)`). — pruebas: `test_modelos.py` (amplía).
2. **`compras/precios.py`** (`precio_unitario`, `valor_recibido`, D-89) y **`compras/servicios/cobertura.py`**. — pruebas: `test_precios.py`,
   `test_cobertura.py` (los cuatro ejemplos de la regla de cobertura).
3. **CMP-RLZ-PED** (servicio y resumen) y `compras/servicios/enlaces.py` (crear y enviar). — pruebas: `test_cmp_rlz_ped.py`, `test_enlaces.py`.
4. **CMP-ENV-COT** (vistas públicas, servicio y aviso de pedido cubierto) y `compras/servicios/avisos.py` (`destinatarios_por_destino`, D-87 punto
   3). — pruebas: `test_cmp_env_cot.py`, `test_avisos.py`, `test_pedidos_concurrencia.py` (dos envíos del mismo proveedor; dos que cubren a la vez).
5. **CMP-CNS-PED** y las pantallas del Agrónomo y del Gerente. — pruebas: `test_cmp_cns_ped.py`, `test_pedidos_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: el filtro propuesto por especialidad en el paso 6 (se anota como disparador).

## Hecho cuando

- Un Agrónomo arma un pedido para dos invernaderos, invita proveedores y cada uno recibe su enlace; un proveedor cotiza una vez (total o unitario
  por línea), recibe el acuse y ve su cotización en solo lectura; el aviso de pedido cubierto sale una sola vez.
- El token no está en la base; la auditoría muestra «Proveedor (mediante enlace)».
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Como Agrónomo, pedí un insumo bajo el mínimo y otro del catálogo; invitá dos proveedores (con el correo de desarrollo).
2. Abrí el enlace en una ventana privada, cotizá una línea con total y otra con unitario y enviá. Volvé a abrirlo: solo lectura.
3. Como Gerente, abrí el pedido: lo ves y no podés cambiar nada.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`; si creaste `rol_externo`, anotalo en `docs/disparadores.md` para COM-04c.
