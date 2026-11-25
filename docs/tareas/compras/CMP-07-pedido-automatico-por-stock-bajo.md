# CMP-07 · Pedido automático por stock bajo

Estado: pendiente | App: compras | Rama: feature/cmp-07-pedido-automatico-por-stock-bajo | Ronda: —

Depende de: **CMP-03** (paso diario 60 a 62, mergeada) y **CMP-02a** (pedido e invitaciones, mergeada). Si alguna no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Hoy el Agrónomo arma el pedido de cotización a mano. Este paso diario lo arma solo, uno por invernadero, con los insumos bajo el mínimo, y manda las invitaciones a los proveedores. El Agrónomo y el Gerente siguen decidiendo desde la cotización en adelante.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-AUT-PED | Generar Pedidos Automáticos por Stock Bajo | docs/casos_de_uso/compras/pedido_automatico.md | — |

## Leer

- Casos de uso: `pedido_automatico.md` completo y, de `pedidos.md`, CMP-RLZ-PED con sus «Actualizaciones de A0» y «Cómo se aplica».
- Modelo: docs/modelo/compras.md (`Pedido`, `DetallePedido`, `InvitacionPedido`, `EnlaceProveedor`) y docs/modelo/maestros.md (`ConfiguracionOperativa`).
- Decisiones: D-NN (esta tarea), D-56, D-22, D-27, D-42, D-87, D-88, D-100 (pasos 60 a 62).
- API: docs/api/stock.md (`existencias`, `bajo_minimo`), docs/api/notificaciones.md.
- Patrones: docs/patrones/bloqueos.md (orden de compras), docs/patrones/enlace_del_proveedor.md, docs/patrones/auditoria.md.
- Código a leer: `compras/servicios/pedidos.py` (`insumos_bajo_el_minimo`, `ya_pedido`, `proveedores_invitables`, `categorias_del_pedido`, `_validar`, `registrar_pedido`, `cancelar_pedido_automaticamente`), `compras/procesos.py` y `compras/apps.py` (cómo se registran los pasos 60 a 62), `core/procesos.py`, `maestros/servicios/configuracion.py` y la pantalla de configuración operativa.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.

## Límites

- Crea modelos: ninguno.
- Migraciones: **una de `maestros`** que agrega `ConfiguracionOperativa.porc_margen_pedido_automatico` (entero, 0 a 100, por defecto 20, con su validación y su CHECK). **Permiso expreso del estudiante (25/11/2026)** para tocar este modelo ya mergeado. No se toca ninguna otra migración.
- Permitido fuera de la app: `maestros/models.py`, su migración, el formulario y la plantilla de la configuración operativa, el servicio que la audita, y sus pruebas; `core/procesos.py` (**solo el comentario** de la tabla de órdenes: fila 63); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: marcar el pedido como «automático» en un campo propio (queda en la auditoría); calcular cantidades por consumo histórico; cambiar CMP-02a, CMP-02b o CMP-03.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Margen configurable.** Columna, migración, formulario, pantalla y auditoría del cambio, como los demás parámetros de la configuración. — pruebas: `maestros/tests/` (amplía las de configuración).
2. **Servicio.** `compras/servicios/pedidos_automaticos.py`: `calcular_cantidad`, la selección de insumos por invernadero y `generar_pedidos_automaticos(hoy) -> ResumenDePaso`. Reutilizá las validaciones y el alta de `pedidos.py`; si hace falta partir `registrar_pedido` en una función interna que acepte el actor de auditoría, hacelo sin cambiar el comportamiento del pedido manual (sus pruebas tienen que seguir iguales). Una transacción por invernadero, con el orden de bloqueo de `bloqueos.md`. — pruebas: `compras/tests/test_cmp_aut_ped.py`.
3. **Paso diario.** Registrarlo en `compras/apps.py` como `generar_pedidos_automaticos`, orden 63, nombre «Pedidos automáticos por stock bajo»; las URLs de los enlaces salen de `URL_DEL_SITIO`. Notificaciones y avisos de las extensiones 3a y 5a. — pruebas: las mismas, más `proceso_diario --solo generar_pedidos_automaticos --fecha`.
4. **Concurrencia e idempotencia.** Dos corridas seguidas no duplican; un pedido manual que tome el mismo insumo entre la lectura y el bloqueo no genera uno repetido (5b). — pruebas: `test_pedidos_automaticos_concurrencia.py` (etiqueta `concurrencia`).

Si el tiempo apremia, lo último que se recorta es el paso 4 (se anota como disparador).

## Hecho cuando

- El paso 63 aparece en `proceso_diario --listar` y crea un pedido por invernadero con insumos bajo el mínimo, con la cantidad y el margen de la decisión.
- Cada extensión de CMP-AUT-PED (1a, 1b, 3a, 5a, 5b, 8a) tiene su prueba.
- El pedido manual sigue pasando todas sus pruebas sin cambios.
- El Gerente puede cambiar el margen y queda auditado.
- Comando de pruebas: python manage.py test compras.tests maestros.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion (y las de concurrencia y migración de esta tarea, con sus etiquetas).

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
