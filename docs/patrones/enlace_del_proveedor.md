# Patrón · Enlace del proveedor (cotizar sin cuenta)

Cómo se programa el enlace que recibe un proveedor invitado para cotizar un pedido (CMP-RLZ-PED crea, CMP-ENV-COT usa, CMP-CNL-PED y la baja del
proveedor anulan, «Reenviar invitación» reemplaza). Decisión: **D-88**. Es el **mismo mecanismo** que el enlace del cliente
(`docs/patrones/enlace_del_cliente.md`, D-65): leelo primero; acá van solo las diferencias. Si algo de acá contradice un caso de uso, manda el
caso de uso: avisá.

## 1. Piezas

| Pieza | Dónde |
|---|---|
| `nuevo_token()` y `resumen_de(token)` | `core/enlaces.py` (ya existe) |
| `InvitacionPedido` y `EnlaceProveedor` | `compras/models.py` (`docs/modelo/compras.md`) |
| `compras/servicios/enlaces.py` | `crear_enlace(invitacion) -> (enlace, token)`, `enlace_vigente(token)`, `bloquear_enlace(id)`, `anular_enlaces_de_pedido(pedido)`, `anular_enlaces_de_proveedor(proveedor)`, `reemplazar_enlace(invitacion)`, `enviar_invitacion(enlace_id, token)` |
| Vistas públicas | `compras/views_proveedor.py`, URL `proveedor/` (sin `login_required`), plantilla base `compras/proveedor/base.html` sin menú ni campana |

## 2. Diferencias con el enlace del cliente

| Tema | Cliente (D-65) | Proveedor (D-88) |
|---|---|---|
| Uno por | venta y tipo | **invitación** (pedido + proveedor); a lo sumo un `vigente` |
| Vencimiento | campo `fecha_vencimiento` | **sin campo**: el final del día de `pedido.fecha_limite_cotizaciones`, leído al abrir y al registrar |
| Después de usarlo | no muestra nada | muestra **la cotización enviada en solo lectura** hasta el final del día de la fecha límite (H15.2) |
| Anulación | al cancelar la venta | al cancelar el pedido (manual o automática) y al pasar el proveedor a inactivo (H22) |
| Reemplazo | nuevo enlace de decisión | «Reenviar invitación» (H15.1): el anterior pasa a `reemplazado` y se envía uno nuevo |
| Correo que falla | avisa al Vendedor | avisa al Agrónomo del pedido: «pedile al Gerente que revise el correo y reenviá la invitación» |
| Auditoría | `rol_externo = ROL_CLIENTE_ENLACE` | `rol_externo = ROL_PROVEEDOR_ENLACE` («Proveedor (mediante enlace)»), con el proveedor y el pedido en `afectados` |

## 3. Abrir (`/proveedor/<token>/`)

1. `enlace_vigente(token)` busca por el resumen. Con `vigente` y la fecha límite no pasada → sesión `request.session["enlace_proveedor"] =
   enlace.id` y redirección a `/proveedor/enlace/`. Con `usado` y la fecha límite no pasada → la misma sesión, pero la vista muestra la
   cotización en solo lectura (extensión 2b). En cualquier otro caso, «Este enlace no se puede usar» con el motivo que el caso de uso permite
   (venció, el pedido ya no está en cotización, ya no podés cotizar, el enlace fue reemplazado por uno más nuevo) **sin datos del pedido**. Un token
   inexistente: «Este enlace no es válido».
2. Cada vista vuelve a leer el enlace por la sesión y verifica que siga sirviendo. Solo se muestra el pedido del enlace, **sin** el precio de
   referencia, sin otras cotizaciones y sin los otros invitados (regla 6 de 8.16).
3. Las páginas de `/proveedor/…` responden con `Cache-Control: no-store`, `Referrer-Policy: same-origin` y `X-Robots-Tag: noindex` (D-88, corregida el
   23/11/2026: con `no-referrer` el navegador manda `Origin: null` en los POST y el CSRF de Django los rechaza).

## 4. Registrar la cotización (CMP-ENV-COT, paso 11)

Dentro de `transaction.atomic()`: bloquear `Proveedor` → `Pedido` → `EnlaceProveedor` (`FOR NO KEY UPDATE`); verificar con las filas
bloqueadas: proveedor activo, pedido `en_cotizacion`, hoy ≤ fecha límite, enlace `vigente`; calcular «cubierto» **antes**; crear la cotización y
sus líneas (la restricción única `(pedido, proveedor)` respalda la 11b); enlace → `usado`; calcular «cubierto» **después**; auditar con
`rol_externo`; `on_commit`: acuse al proveedor y, si pasó de no cubierto a cubierto, el aviso al Agrónomo del pedido
(`avisos.destinatarios_por_destino`, D-87 punto 3).

## 5. Pruebas mínimas (`compras/tests/test_enlaces.py`)

Las del enlace del cliente (token no guardado, redirección sin token, encabezados, sesión que no abre otro pedido, rollback sin correo, correo que
falla), más: el enlace `usado` muestra la cotización en solo lectura hasta el último segundo del día de la fecha límite y nada después; un
`reemplazado` no muestra nada; anular por baja del proveedor; concurrencia (`@tag("concurrencia")`): dos envíos del mismo proveedor a la vez (uno
solo) y dos proveedores distintos que completan la cobertura a la vez (un solo aviso).
