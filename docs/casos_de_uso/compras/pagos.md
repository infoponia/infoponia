# Casos de uso · compras · Pago a proveedores

Copia para el repo de CMP-REG-PAG (A0, extendido v0.1). Fuentes: `CMP-REG-PAG.md`. Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-REG-PAG: Registrar Pago a Proveedor**

Caso de uso extendido del módulo Compras e Inventario (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Reemplaza a PCU › caso 20 (por especificar). Decisiones aplicadas: MD-03, MD-26, MD-36, MD-43 (pago diferido y asiento), H23 (actor, aviso, bandeja, medio sin preselección), precio total por línea, fecha elegida, correo al proveedor y sin anulación de pagos (decisiones_A0.md), X3 (Contador), H21 (regla de notificaciones) y H10/H11 (asientos). Fuentes: MD › regla 13 y 14 de 8.20, regla 4 de 8.18, regla 15 de 8.13; ficha Pago.

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Compras e Inventario.
**Actor principal:** Contador. Si no hay un Contador activo, el Gerente (extensión 1a).
**Versión:** 0.1

**Personal involucrado e intereses**

**Contador:**
- quiere ver qué proveedores hay que pagar y cuánto, sin armar las cuentas a mano;
- quiere registrar el pago con su medio y que el asiento quede correcto.

**Gerente:**
- quiere que se pague a los proveedores por lo que entregaron, y solo por eso;
- quiere poder registrar el pago cuando no hay un Contador activo.

**Proveedor:**
- quiere que se le pague por lo recibido.

**Organización (Jardín Botánico):**
- quiere que la deuda con cada proveedor (cuenta Proveedores) se cancele por el monto exacto recibido;
- quiere un solo pago por proveedor y orden, sin duplicados.

**Relaciones con otros casos de uso**
- No incluye ni es extendido por otros casos de uso.
- **Lo precede:** CMP-REG-RCP · Registrar Recepción de Mercadería y CMP-CRR-FLT · Cerrar Detalle con Faltante (a especificar): cuando con alguno de ellos todos los detalles de un proveedor en una orden quedan completos o cerrados, ese proveedor pasa a la bandeja de pagos pendientes.
- **Disparador:** la notificación «proveedor para pagar» y la bandeja «Pagos a proveedores pendientes» del panel (H23).
- **Lo sigue:** CON-CNS-LGS · Consultar Libro de Gestión, donde se ve el asiento del pago.

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Contador o, si no hay un Contador activo, de Gerente.
b. Existe al menos un proveedor con pago pendiente: en una orden de compra, todos sus detalles están «completos» o «cerrados con faltante», se recibió algo de al menos un detalle y todavía no tiene pago.
c. Existe un ejercicio contable «abierto» y existen las cuentas Proveedores, Caja y Banco c/c.

**Garantías mínimas**
El registro es atómico. Si se cancela o falla:
- no queda registrado ningún pago ni asiento;
- el proveedor sigue en la bandeja de pagos pendientes;
- no se registra ningún log de auditoría parcial.

**Además:**
- Hay a lo sumo un pago por proveedor y por orden (R158; regla 13 de 8.20).
- El monto no lo escribe el actor: lo calcula el Sistema sobre lo recibido (regla 4 de 8.18).
- Este caso de uso no modifica el stock, las recepciones, los reclamos ni los estados de la orden o de sus detalles.

**Garantías de éxito (Postcondiciones)**
a. Se creó un pago asociado a la orden y al proveedor, con la fecha indicada, el medio de pago indicado y el monto igual a la suma, por línea del proveedor en la orden, del total de la línea si se recibió todo, o de lo recibido × el precio unitario calculado (con 4 decimales) si se recibió una parte o se cerró con faltante.
b. Se registró un asiento, con la fecha del pago, originado en el pago: Debe Proveedores / Haber Caja (si el medio es efectivo) o Banco c/c (transferencia, tarjeta de débito o tarjeta de crédito), por el monto del pago.
c. El proveedor dejó de figurar en la bandeja «Pagos a proveedores pendientes» y la notificación asociada quedó resuelta.
d. Se envió al proveedor un correo con el monto, el medio de pago, la fecha y la orden.
e. Se creó un log de auditoría por el pago y el asiento, con usuario, rol, fecha, hora, identificador y valores.

**Escenario principal de éxito (Flujo Básico)**
(El Contador paga a un proveedor, en efectivo o por otro medio, por lo recibido.)

1. **El Contador inicia el registro de un pago a proveedor, desde la bandeja «Pagos a proveedores pendientes» de su panel o desde el menú «Contabilidad».**
2. **El Sistema presenta los pagos pendientes, ordenados del más antiguo al más reciente (por la fecha en que quedó todo completo o cerrado). Para cada uno indica: el proveedor, la orden, la fecha de la última recepción o cierre, la cantidad de líneas y el monto a pagar.**
3. **El Contador selecciona el proveedor y la orden.**
4. **El Sistema presenta el detalle del pago: por cada línea, el insumo, la cantidad pedida, la recibida, el total de la línea, el precio unitario calculado y el subtotal a pagar; las líneas cerradas con faltante y lo no aceptado por daño (que no se pagan); el monto total.**
5. **El Contador indica el medio de pago (efectivo, transferencia, tarjeta de débito o tarjeta de crédito) y, si quiere, cambia la fecha del pago (por defecto, hoy).**
6. **El Sistema verifica los datos y presenta el resumen: el monto, el medio, y el asiento que se registrará (Debe Proveedores / Haber Caja o Banco c/c).**
7. **El Contador confirma el pago.**
8. **El Sistema registra el pago:**
   - bloquea la orden y verifica que el proveedor siga con el pago pendiente;
   - crea el pago con su monto calculado;
   - registra el asiento;
   - registra la auditoría correspondiente.
9. **El Sistema envía al proveedor el correo con el pago.**
10. **El Sistema informa al Contador que el pago fue registrado, con el asiento generado.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 7), el actor cancela:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa que el pago no fue registrado.
3. El actor reinicia desde el paso 1.

**1a. No hay un Contador activo y el Gerente registra el pago:**
1. El caso de uso continúa en el paso 2 con el Gerente como actor.
2. En el paso 8 el Gerente queda como autor en el log de auditoría.
3. Si hay un Contador activo, el Sistema no permite el registro al Gerente.

**2a. No hay pagos pendientes:**
1. El Sistema informa que no hay proveedores para pagar.
2. El caso de uso termina.

**5a. El actor no indica el medio de pago:**
1. El Sistema señala que el medio es obligatorio; no preselecciona ninguno (H23).
2. El actor lo indica (vuelve al paso 5).

**5b. La fecha es posterior a hoy, o cae fuera de un ejercicio «abierto» o «en cierre»:**
1. El Sistema rechaza la fecha con un mensaje que explica el motivo.
2. El actor la corrige (vuelve al paso 5).

**9a. No se logra enviar el correo al proveedor:**
1. El pago permanece registrado.
2. El Sistema reintenta el envío.

**8a. Al registrar, el proveedor ya tiene su pago (otro usuario lo registró):**
1. El Sistema no registra ningún cambio, informa que el pago ya fue registrado y muestra cuál.
2. El caso de uso termina.

**8b. Al registrar, falta el ejercicio abierto o alguna cuenta:**
1. El Sistema no registra ningún cambio e informa qué falta.
2. El caso de uso termina.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 8 se completa en no más de 3 segundos.
- El registro es una única transacción: pago, asiento y logs juntos o ninguno.
- El control de concurrencia impide dos pagos al mismo proveedor en la misma orden y respeta el orden de bloqueos (la orden antes que el ejercicio, que se bloquea al final para la numeración, `docs/patrones/bloqueos.md`).
- Los montos se expresan en pesos argentinos con dos decimales.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**
- **Quién registra:** el Contador; si no hay uno activo, el Gerente. (H23, X3)
- **Pago diferido:** se paga después de recibir, solo por lo recibido, con un solo pago por proveedor y por orden, cuando todos sus detalles en la orden están completos o cerrados con faltante. No se paga lo dañado o vencido que no ingresó al stock. (MD-03, MD-26; regla 13 de 8.20)
- **Sin recepción, sin pago:** si de ningún detalle del proveedor se recibió algo, no hay pago ni asiento. (Regla 13 de 8.20; H11)
- **Monto:** por línea, el total de la línea si se recibió todo; si se recibió una parte o se cerró con faltante, lo recibido × el precio unitario calculado (4 decimales). No hay prorrateo de un precio de toda la cotización (mejora futura). No es editable. (Regla 4 de 8.18, a modificar con el ítem MD nuevo)
- **Medio de pago:** efectivo, transferencia, tarjeta de débito o tarjeta de crédito, sin preselección. El efectivo se imputa a Caja y los demás medios a Banco c/c. (Regla 15 de 8.13, MD-36; H23)
- **Asiento:** Debe Proveedores / Haber Caja o Banco c/c, originado en el pago. (MD-43; regla 14 de 8.20)
- **Fecha:** la elige el Contador, por defecto hoy; no puede ser futura y debe caer en un ejercicio abierto o en cierre (como en CON-REG-ASI).
- **Sin anulación:** no existe Anular Pago (mejora futura). Un error de medio o de fecha se corrige con contraasiento y asiento manual (CON-CTR-ASI, CON-REG-ASI); el pago sigue registrado.
- **Aviso y bandeja:** cuando todos los detalles de un proveedor en una orden quedan completos o cerrados (con algo recibido), InfoPonia notifica al Contador (o al Gerente si no hay Contador activo) y suma el pago a la bandeja «Pagos a proveedores pendientes» de su panel. Si la persona que provocó el estado (por ejemplo, el Gerente al registrar una recepción) es quien recibiría la notificación, no se la envía, aunque el pago igual figura en la bandeja (H21: nunca se notifica a quien hizo la acción). (H23)
- **Baja del proveedor:** un pago pendiente bloquea la baja del proveedor. (H22)

**Lista de tecnología y variaciones de datos**
- **5.** Medio de pago: efectivo, transferencia, tarjeta de débito, tarjeta de crédito. No hay comprobante ni número de operación en el modelo.
- **Notificación «proveedor para pagar»:** indica el proveedor, la orden y el monto.

**Frecuencia**
Una vez por cada proveedor de cada orden de compra aprobada con mercadería recibida.

**Temas abiertos**
1. Pagos parciales o un pago por cada recepción: mejora futura (PCU › Ajustes pendientes, punto 5). Hoy un solo pago al final.
2. Caja o Banco c/c con saldo insuficiente: el Sistema no lo controla; un saldo negativo se muestra en rojo en el libro de gestión.

---

## Cómo se aplica (código)

Decisiones: **D-91**, **D-89** (monto), **D-85** (quién paga), **D-86** (asiento). Modelo: `docs/modelo/compras.md` (`Pago`). API:
`docs/api/asientos.md`. Patrón: `docs/patrones/asientos.md`.

- `compras/servicios/pagos.py`:
  - `pagos_pendientes(*, proveedor=None, orden=None)`: la consulta única de D-91 punto 2 (bandeja, filtro de órdenes, baja del proveedor);
  - `detalle_del_pago(actor, orden_id, proveedor_id)`: el paso 4 (por línea: pedido, recibido, total, unitario calculado, a pagar; lo no aceptado
    y lo cerrado con faltante);
  - `resumir_pago(actor, orden_id, proveedor_id, medio, fecha)` y `registrar_pago(actor, orden_id, proveedor_id, medio, fecha) -> Pago`;
  - `avisar_si_quedo_para_pagar(orden, proveedor, *, actor)` (la llaman CMP-04 y CMP-06).
- **Registrar:** permisos con `responsables.puede_registrar_asientos(actor)` (1a: el Gerente con un Contador activo recibe `PermissionDenied` con
  «Lo registra el Contador»); medio obligatorio sin preselección (5a); fecha con `ejercicio_para(fecha, automatico=False)` (5b); bloquear la orden y
  las líneas del proveedor; verificar que el par siga pendiente (8a: si ya hay pago, informarlo); calcular `monto_pago` con
  `precios.valor_recibido` (D-89); crear el `Pago`; **por último** `registrar_asiento_automatico(actor, pago, fecha, [(PROVEEDORES, DEBE, monto),
  (CAJA si efectivo / BANCO, HABER, monto)])`; auditar `alta_pago` (con el asiento en `datos`). `on_commit`: correo al proveedor (d).
- **La baja del proveedor** (`proveedores.impedimentos_de_baja`) suma `pago_pendiente` con `pagos_pendientes(proveedor=...)`.
- **Bandeja y panel:** sección «Pagos a proveedores pendientes» del panel del Contador y, sin Contador activo, del Gerente
  (`core.registrar_seccion_de_inicio`, con `puede_registrar_asientos`); la entrada del menú «Pagos a proveedores» (D-87 punto 6); el atajo «con
  pago pendiente» y la sección «Pagos» de la ficha de la orden (CMP-CNS-ODC regla 7).
- `contabilidad.registrar_enlace_de_origen("pago", ...)` → la ficha de la orden.

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-REG-PAG: cada regla, extensión y postcondición; los tres casos de monto (todo recibido, parte, cerrado con faltante); efectivo → Caja y los demás → Banco c/c | `test_cmp_reg_pag.py` |
| `pagos_pendientes` y `avisar_si_quedo_para_pagar` (el aviso sale una vez; no a quien hizo la acción; sin responsable no falla) | `test_pagos_pendientes.py` |
| Proveedores en cero después del pago (con recepciones parciales) y `verificar_invariantes_contables` | `test_valorizacion.py` (lo amplía) |
| Concurrencia: dos pagos del mismo par (uno solo); pago contra corrección de recepción (cuando exista, CMP-06) | `test_pagos_concurrencia.py` |

### Pantallas (prototipo: `tabPag` línea 2620, `VIEWS.c_pag` 2625, `panelCon` 2917)

En el prototipo los pagos están en «Compras › Pagos a proveedores»; por la pasada general (punto 1) el Contador entra desde «Contabilidad» y su
panel: la pantalla es la misma, cambia solo dónde está la entrada del menú (D-87 punto 6).
