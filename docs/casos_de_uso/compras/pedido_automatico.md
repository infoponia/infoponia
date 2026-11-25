# Casos de uso · compras · Pedido automático por stock bajo

Proceso automatizado de la nota de presentación. Decisión: D-NN. Se apoya en CMP-RLZ-PED (`pedidos.md`).

## **Caso de uso CMP-AUT-PED: Generar Pedidos Automáticos por Stock Bajo**

- **Actor:** InfoPonia (paso 63 del proceso diario). Es un proceso, no una pantalla.
- **Disparador:** el proceso diario corre con la fecha `hoy`.
- **Grado de automatización:** semiautomático. El pedido y las invitaciones salen solos; el Agrónomo y el Gerente siguen decidiendo (cotizaciones, orden de compra y aprobación).

**Precondiciones**

- a. Invernadero activo.
- b. El insumo está habilitado y activo en ese invernadero, y su existencia está bajo el mínimo (`Existencia.bajo_minimo`, la misma condición que la pantalla manual).

**Flujo básico (por cada invernadero, en orden de id, cada uno en su transacción)**

1. El Sistema reúne los insumos del invernadero que cumplen la precondición b y que no están ya en otro pedido en cotización ni en una orden pendiente de aprobación (`ya_pedido`).
2. Calcula la cantidad de cada uno: `mínimo × (1 + porc_margen_pedido_automatico/100) − (libre + tránsito)`, redondeada hacia arriba a los decimales de la unidad.
3. Busca los proveedores a invitar: activos, con correo, y especializados en el tipo de algún insumo del pedido (MD-121).
4. Fija la fecha límite en `hoy + dias_limite_cotizacion`.
5. Registra el pedido «en cotización» a nombre del Agrónomo activo del invernadero, con sus detalles (precio de referencia copiado ahora), una invitación y un enlace por proveedor.
6. Audita `alta_pedido` como InfoPonia (usuario nulo, rol `infoponia`), con el origen «automático», el margen aplicado y los insumos.
7. Notifica al Agrónomo: «Pedido P-… creado automáticamente: N insumos bajo el mínimo en <invernadero>».
8. Tras confirmar, envía por correo la invitación a cada proveedor (`on_commit`, `enlaces.enviar_invitacion`).

**Extensiones**

- 1a. Ningún insumo cumple: no se crea nada y el paso termina sin error (idempotencia: dos corridas el mismo día no duplican).
- 1b. Algunos insumos ya están en otro pedido: se piden los demás; los ya pedidos se saltean.
- 3a. No hay proveedores a invitar: no se crea el pedido; se notifica al Agrónomo y al Gerente, una vez por día y por invernadero.
- 5a. El invernadero no tiene Agrónomo activo: no se crea el pedido; se notifica al Gerente.
- 5b. Entre la lectura y el bloqueo cambió algo (otro pedido, un proveedor dado de baja, el invernadero inactivo): se relee con todo bloqueado y se repite la validación; si ya no corresponde, no se crea nada (extensión 11a de CMP-RLZ-PED).
- 8a. Falla un correo: el enlace queda en «pendiente de envío» (12a de CMP-RLZ-PED); no se revierte el pedido.

**Reglas**

- No toca stock, tránsito, mínimo, reservas ni contabilidad.
- Un invernadero que falla no impide los demás (D-56, punto 5): se registra con `logger.exception` y el paso sigue.
- Si el pedido queda sin cotizaciones y se cancela (pasos 60 y 62), y el insumo sigue bajo el mínimo, el paso 63 puede crear otro. Es intencional.

**Postcondiciones**

- a. El pedido, sus detalles, invitaciones y enlaces.
- b. Un registro de auditoría `alta_pedido` por pedido creado.
- c. La notificación al Agrónomo (o al Gerente en 3a y 5a).
- d. Los correos en `on_commit`.
- e. La alerta de «bajo el mínimo» sigue activa.
- f. `ResumenDePaso(procesados=invernaderos revisados, creados=pedidos creados, resueltos=0, detalle)`.

## Cómo se aplica (código)

Decisión: **D-104**. Tarea: CMP-07. Fuentes: `docs/casos_de_uso/compras/pedidos.md` (CMP-RLZ-PED), D-56, D-22, D-27, D-42, D-87 y D-88.

- `compras/servicios/pedidos_automaticos.py`:
  - `calcular_cantidad(minimo, libre, transito, margen, unidad)`: `mínimo × (1 + margen/100) − (libre + tránsito)`, `ROUND_CEILING` a los decimales de la unidad.
  - `generar_pedidos_automaticos(hoy) -> ResumenDePaso`: por invernadero activo, en orden de id, una transacción. `procesados` = invernaderos revisados, `creados` = pedidos, `resueltos` = 0, `detalle` = cuántos quedaron sin proveedores o sin Agrónomo. Un invernadero que falla se registra y los demás siguen; al final lanza `RuntimeError` (D-56 punto 5).
- **Lectura sin bloquear:** insumos habilitados y activos, bajo el mínimo (`stock.existencias`) y sin `ya_pedido`. Sin ninguno: nada (1a). Sin Agrónomo activo: aviso al Gerente (5a). Sin proveedores: aviso al Agrónomo y al Gerente (3a). Los avisos no se repiten el mismo día (el título lleva la fecha).
- **Bloqueos** (el orden de `registrar_pedido`): cuenta del Agrónomo → invernadero (`bloquear_invernadero_activo`) → `InsumoInvernadero` en orden de id → proveedores en orden de id. Con todo bloqueado se releen los candidatos, los proveedores y el Agrónomo; si ya no corresponde, no se crea nada (5b).
- **Alta:** `pedidos._crear_pedido(agronomo_id, lineas, invitados, fecha, hoy, construir_url, *, usuario_de_auditoria, datos_extra)`, que comparten `registrar_pedido` (con el actor) y el paso (con `None`: InfoPonia). `datos_extra` suma `origen` y `porc_margen_pedido_automatico` a la auditoría.
- **Enlaces:** las URLs salen de `settings.URL_DEL_SITIO`; `enlaces.enviar_invitacion` no envía si la URL no es absoluta y deja el enlace «pendiente de envío» (8a).
- **Paso diario:** `ComprasConfig.ready()` registra `generar_pedidos_automaticos`, orden 63, «Pedidos automáticos por stock bajo».
- **Margen:** `ConfiguracionOperativa.porc_margen_pedido_automatico` (`maestros` 0013), en la tarjeta «Compras» de la configuración.

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| Cantidad, flujo, postcondiciones, precondiciones, extensiones 1a, 1b, 3a, 5a y 8a, 5b determinista y paso 63 | `test_cmp_aut_ped.py` |
| 5b con dos hilos y dos corridas a la vez (`concurrencia`) | `test_pedidos_automaticos_concurrencia.py` |
| Recorrido por rol y estado | `test_recorrido_pedido_automatico.py` |
| El margen en la configuración | `maestros/tests/test_adm_mod_cfg.py`, `test_configuracion_vistas.py`, `test_singletons_modelo.py` |
