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

(La completa Claude Code al cerrar.)
