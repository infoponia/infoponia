# CMP-02b · Cancelar pedido, reenviar invitación y lo que cancela solo

Estado: pendiente | App: compras | Rama: feature/cmp-02b-cancelar-reenviar-y-bajas | Ronda: Compras 1

Depende de: **CMP-02a**. No depende de la contabilidad.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo puede **cancelar** un pedido y **reenviar** una invitación; el sistema **cancela solo** los pedidos de un Agrónomo que
se da de baja o deja el invernadero (MD-62); un pedido en curso **impide** deshabilitar el insumo o dar de baja el invernadero (H20), y la baja de
un proveedor **anula** sus enlaces.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-CNL-PED | Cancelar Pedido (manual y la función de las automáticas) | docs/casos_de_uso/compras/pedidos.md | Las automáticas de los pasos 60 y 62 las dispara CMP-03 |
| CMP-CNS-PED (regla 7) | Reenviar invitación | docs/casos_de_uso/compras/pedidos.md | — |
| CMP-BAJ-PRV (regla 3) | Anular los enlaces del proveedor dado de baja | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |
| (MD-62, H17) | Cancelación por baja o traspaso del Agrónomo | docs/casos_de_uso/compras/pedidos.md («Cómo se aplica», CMP-CNL-PED) | — |
| (H20) | Impedimento «pedido en curso» | docs/casos_de_uso/compras/pedidos.md («Impedimentos») | — |

## Leer

- Casos de uso: `pedidos.md` (CMP-CNL-PED, la regla 7 de CMP-CNS-PED y su «Cómo se aplica»), `proveedores.md` (CMP-BAJ-PRV).
- Modelo: docs/modelo/compras.md (`Pedido`: `causa_cancelacion`; `EnlaceProveedor`).
- Decisiones: D-87 (puntos 3 y 5), D-88, D-43 (baja de cuenta), D-60 (traspaso, como ejemplo), D-36, D-42, D-44.
- API: docs/api/extensiones_de_maestros.md (traspaso y baja de cuenta), docs/api/extensiones_de_inventario.md
  (`registrar_impedimento_de_deshabilitacion`), docs/api/notificaciones.md.
- Patrones: docs/patrones/enlace_del_proveedor.md, docs/patrones/bloqueos.md («Invernadero» y el contrato de los puntos de extensión).
- Pantallas: `VIEWS.c_pedcnl`, `VIEWS.c_ped` («Reenviar invitación»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-02a; `maestros/extensiones.py` (`registrar_traspaso`, `contar_traspaso`, `traspasar`), `core/extensiones.py`
  (`registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta`, para que la ventana de baja diga cuántos pedidos se cancelan), `inventario/extensiones.py`; un registrante existente como modelo (`produccion/apps.py`).

## Límites

- Crea modelos: ninguno (los campos `causa_cancelacion`, etc., ya los creó CMP-02a; si faltara alguno, migración `0003`).
- Migraciones: una de `core` con `cancelacion_pedido` y `reenvio_invitacion`.
- Permitido fuera de la app: `core/models.py` (acciones) y su migración; al cerrar, los archivos de M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: los pasos diarios (CMP-03) y el impedimento de órdenes (CMP-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Cancelar** (`_cancelar`, la manual y `cancelar_pedido_automaticamente`). — pruebas: `test_cmp_cnl_ped.py`.
2. **Reenviar invitación.** — pruebas: `test_cmp_cns_ped.py` (amplía).
3. **Registrantes:** baja de cuenta y traspaso del Agrónomo; impedimento `pedido_en_curso`; la baja del proveedor anula sus enlaces. — pruebas:
   `test_registrantes_de_pedidos.py` (las tres pruebas mínimas de cada registrante: con datos, sin datos, sin consultas por fila) y
   `test_cmp_baj_prv.py` (amplía).
4. **Concurrencia:** cancelar contra cotizar; baja del proveedor contra cotizar. — pruebas: `test_pedidos_concurrencia.py` (amplía).
5. **Pantallas:** cancelar con resumen; «Reenviar» en la ficha.

## Hecho cuando

- Un pedido cancelado (a mano o solo) descarta sus cotizaciones, anula los enlaces y avisa a los invitados; el traspaso y la baja del Agrónomo lo
  cancelan y la ventana de confirmación dice cuántos pedidos se cancelarán.
- Deshabilitar un insumo con un pedido en curso se rechaza con un enlace al pedido.
- Pruebas verdes, sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Cancelá un pedido con una cotización: el proveedor ya no puede abrir su enlace.
2. Reenviá una invitación: el enlace viejo dice «reemplazado» y el nuevo funciona.
3. Como Gerente, quitá al Agrónomo de un invernadero con un pedido en curso: la ventana lo avisa y el pedido queda cancelado.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md` (cerrá «Cuando exista Pedido», la parte de los pedidos de «Cuando
exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido», la de «pedido en curso» de «Cuando existan los pedidos de `compras`» y, en «Cuando
exista un caso de uso que planifique, haga pedidos…», los pedidos: un invernadero inactivo no se ofrece al armar un pedido).
