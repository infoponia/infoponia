# Prototipo de compras, contabilidad y estadísticas · nota de cobertura

Archivo: `InfoPonia · Compras, contabilidad y estadísticas.html` (un solo archivo, se abre en el navegador).
Parte del prototipo de comercial y cosecha, que ya integra producción e IoT. No se quitó ni se reemplazó nada de lo anterior: se sumaron menús, secciones en los paneles de control y dos roles nuevos (Contador y Proveedor). El botón «Resaltar lo nuevo» del pie marca en violeta lo agregado en esta ronda.

## Cómo recorrerlo
- Menú de roles (arriba a la derecha, «Solo prototipo · ver como»): Agrónomo (arranca acá), Gerente, Contador, Proveedor, más los roles que ya existían.
- En ese mismo menú, «Hay un Contador activo» enciende o apaga el caso sin Contador: el Gerente pasa a registrar pagos y asientos y el rol Contador desaparece de la lista.
- «Reiniciar datos de ejemplo» (pie) vuelve todo al estado inicial. Hoy es 21/11/2026.
- Proveedor: el selector «enlace de ejemplo» de la parte superior cambia entre enlace vigente, usado, vencido, cancelado, reemplazado y no enviado.

## Qué pantalla cumple cada caso de uso

| Caso de uso | Rol | Dónde |
|---|---|---|
| Realizar pedido de cotización | Agrónomo | Compras › Pedidos › Nuevo pedido (también «Pedir» desde insumos bajo el mínimo en el panel) |
| Cancelar pedido | Agrónomo | Ficha del pedido › Cancelar pedido (motivo obligatorio) |
| Reenviar invitación | Agrónomo | Ficha del pedido › Proveedores invitados (incluye correo que no sale) |
| Cotizar por enlace | Proveedor | Portal del proveedor (precio total o unitario, validez, plazo, observaciones, confirmación) |
| Generar orden de compra | Agrónomo | Ficha del pedido › Comparar cotizaciones (por insumo y por cotización, cobertura con tolerancia) |
| Aprobar o rechazar orden | Gerente | Compras › Órdenes de compra › Revisar |
| Registrar recepción | Agrónomo (Gerente si el destino no tiene Agrónomo) | Compras › Por recibir › Registrar recepción (lotes, vencimientos, inconvenientes) |
| Cerrar faltante | Agrónomo / Gerente | Ficha de la orden › Cerrar con faltante |
| Corregir recepción | Agrónomo / Gerente | Ficha de la orden › Corregir una recepción |
| Emitir y cerrar reclamo | Gerente | Compras › Reclamos |
| Registrar pago a proveedor | Contador (Gerente sin Contador) | Compras › Pagos a proveedores |
| Alta, edición, baja y reactivación de proveedor | Gerente | Compras › Proveedores |
| Registrar asiento | Contador (Gerente sin Contador) | Contabilidad › Registrar asiento |
| Contraasentar | Contador (Gerente sin Contador) | Contabilidad › ficha del asiento › Contraasentar |
| Consultar libro de gestión | Contador, Gerente | Contabilidad › Libro de gestión (cronológica y por cuenta) |
| Cerrar ejercicio | Contador (Gerente sin Contador) | Contabilidad › Ejercicios › Cerrar ejercicio |
| Estadísticas | Agrónomo (producción), Gerente (resumen, producción, comercial, compras, resultados) | Estadísticas, con período elegido y comparación |

Panel de control: el Agrónomo suma insumos bajo el mínimo, pedidos por resolver, mercadería por recibir y órdenes rechazadas; el Gerente suma órdenes por aprobar, reclamos por emitir, pagos y ejercicio en cierre; el Contador tiene su propio panel (pagos pendientes, ejercicio, asientos recientes, resultado del mes). Todo lo que ya tenían producción, IoT y comercial sigue arriba.

## Datos de ejemplo para probar cada excepción
- PED-0030 y PED-0028: venció la fecha límite con cotizaciones (cobertura completa en uno, insuficiente en el otro).
- PED-0030 tiene una cotización con validez vencida (Marcos Benítez) y un enlace vencido (Plásticos Santafesinos).
- PED-0031: enlace vigente para probar el portal; Marcos Benítez tiene el correo mal escrito (el envío falla).
- ODC-0016: pendiente de aprobación (se puede aprobar). ODC-0017: pendiente con cotización vencida (solo se puede rechazar).
- ODC-0014: recibida en parte, con atrasos, un reclamo sin emitir (REC-005) y un pago pendiente.
- ODC-0013: cerrada con faltante, un proveedor pagado y otro por pagar.
- Ejercicio 1 en cierre (terminó el 31/08/2026); el asiento N.º 12 está anulado por el N.º 13 y corregido por el N.º 14.
- CUIT válidos para probar altas: 30-70555123-1 (nuevo), 20-28345671-5 ya existe, 30-68999111-0 es el proveedor dado de baja.

## Decisiones vigentes (confirmadas por el análisis y por Ezequiel)
1. La orden con una cotización vencida o con un proveedor inactivo no se puede aprobar, solo rechazar. El motivo del rechazo ya viene propuesto y se puede editar.
2. Valoración de cada línea: el total cotizado si se recibió todo; si no, lo recibido por el precio unitario (4 decimales). En recepciones parciales se asienta la diferencia en la recepción que completa la línea.
3. El proveedor puede cotizar más que lo pedido; al comparar, el Agrónomo ve la diferencia. El plazo es de al menos 1 día. La elección de cotizaciones es por línea completa.
4. No se puede recibir más de lo que falta (sobreentrega bloqueada). Tipos de inconveniente: mercadería dañada, calidad no conforme, producto distinto al pedido, vencido o próximo a vencer, y otro con descripción obligatoria.
5. Pago: fecha de hoy; transferencia, efectivo o tarjeta; el efectivo sale de Caja y los demás del Banco.
6. Contraasiento: la fecha la elige el Contador, por defecto hoy, dentro de un ejercicio abierto o en cierre. En el prototipo la limité al mismo ejercicio del asiento original (pendiente de confirmar).
7. Proveedor: el correo es obligatorio; el teléfono y los rubros son opcionales; el CUIT se valida con su dígito verificador, sin regla de prefijo.
8. Ejercicio en cierre sin Contador: el aviso va al Gerente.
9. Las estadísticas de producción y comerciales son sintéticas y deterministas; las contables y de compras salen del libro y de las órdenes. Las estadísticas del Vendedor son de otro prototipo y no se tocaron.
