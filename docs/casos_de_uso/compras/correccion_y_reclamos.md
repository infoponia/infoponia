# Casos de uso · compras · Corrección de recepción y reclamos

Copia para el repo de CMP-COR-RCP (extendido v0.1), CMP-EMT-RCL y CMP-CRR-RCL (alto nivel v0.1), de A0. Fuentes: `CMP-COR-RCP.md` y `CMP-alto-nivel.md`. Cotejado con `decisiones_A0.md` y `pendientes_para_pegar.md`: **esas decisiones ganan** si algo
difiere (regla del estudiante del 23/11/2026); lo que cambian está en «Actualizaciones de A0 que mandan», al final de cada caso de uso o del
archivo.

**El código va en la app `compras`** (D-37, nivel 6; D-87). Archivos de pruebas bajo `compras/tests/`. Si este archivo y el documento de
Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>`, `test_post_<letra>_<que_espera>` y
`test_ext_<codigo>_<que_espera>`.

---

## **Caso de uso CMP-COR-RCP: Corregir Recepción**

Caso de uso extendido del módulo Compras e Inventario (versión 0.1, 23/11/2026), con el formato de «CU extendidos». Caso nuevo que resuelve H24 (decisiones_A0.md, opción c) y el tema abierto «Corrección de una recepción registrada con error» de CMP-REG-RCP. Cierra la mejora futura que el contexto (sección 4.2, H24) planteaba resolver con CMP-AJT-STK y un asiento manual.

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Compras e Inventario.
**Actor principal:** Agrónomo a cargo del invernadero de destino. Si no está, el Gerente (extensión 1a), como en CMP-REG-RCP.
**Versión:** 0.1

**Personal involucrado e intereses**

**Agrónomo:**
- quiere corregir una cantidad que cargó de más al recibir, sin tener que recurrir a un ajuste de stock ni a un asiento manual.

**Proveedor:**
- quiere que se le informe lo que se le dejó de reconocer como recibido y que no se le pague por eso.

**Gerente y Contador:**
- quieren que el stock, la deuda con el proveedor y el libro de gestión reflejen lo que realmente entró.

**Organización (Jardín Botánico):**
- quiere corregir un error de carga sin perder trazabilidad ni cambiar nada que ya se pagó.

**Relaciones con otros casos de uso**
- No incluye ni es extendido por otros casos de uso.
- **Lo precede:** CMP-REG-RCP · Registrar Recepción de Mercadería (la recepción que se corrige).
- **Alternativas:** CMP-AJT-STK · Ajustar Stock de Insumo, cuando el lote ya no conserva la cantidad a corregir (diferencia de inventario).
- **Lo que se corrige de menos:** un registro de menos se corrige con otra recepción parcial, no con este caso de uso.

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Agrónomo.
b. Existe una recepción registrada con una línea cuya cantidad recibida es mayor que cero.
c. El proveedor de la recepción no tiene pago registrado en esa orden.
d. Existe un ejercicio contable «abierto» y las cuentas Proveedores e Insumos en Stock.

**Garantías mínimas**
La corrección es atómica. Si se cancela o falla:
- no cambia el stock, el tránsito, los lotes, los estados de la línea o de la orden, ni las alertas;
- no queda registrado ningún asiento, movimiento ni log parcial, y no se envía ningún correo.

**Además:**
- Solo se corrige en menos: la cantidad recibida de una línea nunca sube con este caso de uso.
- No se corrige una línea si el lote creado por esa recepción ya no conserva la cantidad a descontar (porque se consumió o se movió).
- No se modifica la cantidad pedida, el precio ni el precio de referencia.

**Garantías de éxito (Postcondiciones)**
a. La cantidad recibida de la línea de la recepción bajó en la cantidad corregida.
b. El lote de insumo creado por esa recepción bajó su stock en esa cantidad, con un movimiento de insumo que la registra (movimiento nuevo «salida por corrección de recepción»). El stock actual del InsumoInvernadero bajó en la misma cantidad y su cantidad en tránsito subió en la misma cantidad.
c. El detalle de la orden volvió a «pendiente» por la cantidad corregida (si estaba «completo») y el estado de la orden se recalculó («parcialmente recibida» si corresponde).
d. Se registró un asiento inverso al de la recepción: Debe Proveedores / Haber Insumos en Stock, por la cantidad corregida × el precio unitario calculado de la línea (misma valorización que el asiento de CMP-REG-RCP, con el ítem MD de precio total por línea).
e. Las alertas de insumo bajo el mínimo y de «stock inconsistente» del InsumoInvernadero se reevaluaron: se reactivan las que correspondan.
f. Si el detalle había dejado al proveedor listo para pagar, el proveedor salió de la bandeja de pagos pendientes (porque ya no tiene todos sus detalles completos o cerrados).
g. Se envió al proveedor un correo informándole la corrección.
h. Se creó un log de auditoría por cada elemento creado o modificado, con usuario, rol, fecha, hora, identificador y valores.

**Escenario principal de éxito (Flujo Básico)**
(El Agrónomo descubre que cargó de más una línea de una recepción y la corrige antes de que se pague.)

1. **El Agrónomo inicia la corrección de una recepción, desde la ficha de la orden (CMP-CNS-ODC).**
2. **El Sistema presenta las recepciones corregibles de los invernaderos a cargo del Agrónomo (aquellas cuyo proveedor todavía no tiene pago). Para cada una: la orden, el proveedor, la fecha y las líneas.**
3. **El Agrónomo selecciona la recepción.**
4. **El Sistema presenta las líneas con cantidad recibida mayor que cero. Para cada una: el insumo, la cantidad recibida, el lote creado, la cantidad que conserva ese lote y la máxima corregible.**
5. **El Agrónomo indica, por cada línea a corregir, la cantidad a descontar (menor o igual que la máxima) y, si quiere, una observación.**
6. **El Agrónomo indica que terminó.**
7. **El Sistema verifica los datos y presenta el resumen: por línea, la nueva cantidad recibida y cómo cambian el stock, el tránsito y el estado de la línea y de la orden; el asiento inverso y su monto; las alertas que se reactivarán; y que se avisará al proveedor.**
8. **El Agrónomo confirma.**
9. **El Sistema registra la corrección:**
   - bloquea la orden, las líneas y los lotes y verifica de nuevo las condiciones;
   - baja la cantidad recibida y el stock del lote, sube el tránsito, con su movimiento de insumo;
   - actualiza los estados de la línea y de la orden;
   - registra el asiento inverso;
   - reevalúa las alertas;
   - registra la auditoría correspondiente.
10. **El Sistema envía al proveedor el correo con la corrección.**
11. **El Sistema informa al Agrónomo que la corrección fue registrada y el estado en que quedó la orden.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 8), el actor cancela:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa que la corrección no fue registrada.
3. El actor reinicia desde el paso 1.

**1a. El Gerente corrige porque el Agrónomo no está:**
1. En el paso 2, el Sistema presenta las recepciones corregibles de todos los invernaderos.
2. El caso de uso continúa con el Gerente como actor; el Agrónomo de la corrección queda vacío y el Gerente en el log de auditoría.

**2a. No hay recepciones corregibles (todas tienen su pago registrado):**
1. El Sistema informa que no hay recepciones para corregir.
2. El caso de uso termina.

**4a. El lote creado ya no conserva la cantidad recibida (se consumió o se movió):**
1. El Sistema indica la cantidad máxima corregible (lo que conserva el lote) y, si es cero, no permite corregir esa línea.
2. El Sistema informa que lo restante se resuelve con un ajuste de stock y la diferencia de inventario (CMP-AJT-STK).
3. El actor continúa con las demás líneas o cancela.

**4b. La línea está «cerrada con faltante»:**
1. El Sistema no permite corregirla.

**5a. La cantidad a descontar es cero, negativa, tiene más de dos decimales o supera la máxima corregible:**
1. El Sistema señala el error.
2. El actor corrige (vuelve al paso 5).

**5b. Ninguna línea tiene cantidad a descontar:**
1. El Sistema informa que la corrección debe incluir al menos una línea.
2. El actor indica una cantidad (vuelve al paso 5) o cancela.

**9a. Al registrar, el proveedor ya tiene su pago registrado, o el lote ya no conserva la cantidad:**
1. El Sistema no registra ningún cambio e informa qué cambió.
2. El caso de uso vuelve al paso 4.

**10a. No se logra enviar el correo al proveedor:**
1. La corrección permanece registrada.
2. El Sistema reintenta el envío.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 9 se completa en no más de 5 segundos.
- El registro es una única transacción: línea, lote, movimiento, stock, tránsito, estados, asiento, alertas y logs juntos o ninguno. El correo se envía fuera de la transacción.
- El control de concurrencia impide corregir una línea mientras se la recibe, se la cierra con faltante, se la paga o se consume el lote, y respeta el orden de bloqueos de `docs/patrones/bloqueos.md` (el ejercicio al final).
- El Agrónomo accede solo a las órdenes con destino en los invernaderos que tiene a cargo.
- Las cantidades tienen hasta dos decimales; los montos, en pesos con dos decimales.
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**
- **Solo en menos:** la corrección baja lo recibido; lo registrado de menos se corrige con otra recepción parcial. (H24)
- **Antes del pago:** una recepción solo se corrige mientras su proveedor no tenga pago en esa orden, porque el pago se calcula sobre lo recibido (regla 13 y regla 4 de 8.18/8.20). (H24)
- **Solo si el lote conserva la cantidad:** si no, se usa un ajuste y una diferencia de inventario (CMP-AJT-STK). (H24)
- **Asiento:** inverso al de la recepción, Debe Proveedores / Haber Insumos en Stock, por cantidad corregida × precio unitario de la orden. No es un contraasiento de R161: es un asiento automático originado en la corrección. Su documento de origen es la corrección (clase nueva CorreccionRecepcion, que hereda de OrigenDocumento). (H24, R1; regla 14 de 8.20)
- **Estado de la línea y de la orden:** lo corregido vuelve a pendiente; el estado de la orden se recalcula con la regla 24 de 8.16.
- **Tránsito:** sube en lo corregido, porque esa mercadería vuelve a estar pendiente. (Regla 22 de 8.16)
- **Aviso al proveedor:** por correo, con lo corregido por línea. (H24)
- **Alertas:** el stock baja, así que pueden reactivarse las de insumo bajo el mínimo y de «stock inconsistente». (Reglas 11 y 12 de 8.15)

**Lista de tecnología y variaciones de datos**
- **5.** Observación: texto libre opcional.
- **10.** El correo indica el identificador de la orden, la fecha de la recepción corregida, por línea el insumo y la cantidad corregida, y lo que sigue pendiente. No menciona a otros proveedores.

**Frecuencia**
Muy baja.

**Decisiones de modelo derivadas (R1 a R6)**
1. Clase nueva CorreccionRecepcion, hija de OrigenDocumento, origen del movimiento de salida y del asiento inverso; valor nuevo del tipo de movimiento de insumo (ítem MD nuevo).
2. No se corrige una línea cerrada con faltante.
3. La corrección no toca los inconvenientes ni el reclamo: el sin emitir sigue sin emitir y el emitido sigue emitido.


---

## **Caso de uso CMP-EMT-RCL: Emitir Reclamo a Proveedor**

Reemplaza a CU-98 (preliminar). X4: manda el MD (regla 10 de 8.20; MD-56): los inconvenientes los declara quien registra la recepción y el reclamo nace «sin emitir»; el Gerente solo lo emite. Por eso es de alto nivel (una sola clase afectada).

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** dejar formalmente emitido un reclamo ya generado por una recepción con inconvenientes.

**Precondición:**

a. El actor está identificado con una cuenta activa de Gerente.

b. Existe un reclamo «abierto» sin emitir.

**Postcondición:**

a. El reclamo quedó emitido: con el Gerente que lo emitió (R008) y la fecha de emisión igual a la fecha actual. Sigue «abierto».

b. La alerta «recepción con inconvenientes» del Gerente asociada al reclamo quedó resuelta.

c. Se envió al proveedor un correo con el reclamo: la recepción, la orden y cada inconveniente (el proveedor no tiene cuenta: emitir es eso).

d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del reclamo y el cambio.

**Reglas:**

1.  Un reclamo está emitido si y solo si tiene Gerente, y solo entonces tiene fecha de emisión. (R008 en 0..1)
2.  El Gerente ve el reclamo con la recepción, el proveedor, el invernadero y cada inconveniente (tipo, cantidad afectada y descripción). No los modifica ni agrega: los declaró quien registró la recepción.
3.  Reclamar significa dejar registrado lo que pasó, no esperar una devolución. (Regla 10 de 8.20)
4.  Se llega desde la alerta del Gerente o desde la ficha de la orden (CMP-CNS-ODC).

**Decisiones derivadas (R1 a R6):**

1.  Emitir el reclamo envía el correo al proveedor.
2.  Una corrección de recepción (CMP-COR-RCP) no toca los inconvenientes ni el reclamo.

---

## **Caso de uso CMP-CRR-RCL: Cerrar Reclamo a Proveedor**

Reemplaza a CU-99 (preliminar).

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** registrar que el reclamo quedó resuelto, una vez tratada la situación con el proveedor por fuera del Sistema.

**Precondición:**

a. El actor está identificado con una cuenta activa de Gerente.

b. Existe un reclamo «abierto» y emitido.

**Postcondición:**

a. El reclamo pasó a «cerrado».

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del reclamo y el cambio de estado.

**Reglas:**

1.  Solo se cierra un reclamo emitido. (Regla 10 de 8.20)
2.  Un reclamo cerrado no se reabre.
3.  El cierre no cambia el stock, las líneas de la orden ni el pago.

---

## Cómo se aplica (código)

Decisiones: **D-90** (corrección: tipo de movimiento nuevo, vínculos, «lo máximo corregible»), **D-89** (asiento inverso), **D-91** (sale de la
bandeja), **D-86**. Modelo: `docs/modelo/compras.md` (`CorreccionRecepcion`, `DetalleCorreccionRecepcion`, `ReclamoProveedor`, `AlertaCompras`).

### CMP-COR-RCP (CMP-06)

- `compras/servicios/correcciones.py`: `recepciones_corregibles(actor)`, `lineas_corregibles(actor, recepcion_id)` (por línea: lo recibido, los
  lotes creados con lo que conserva cada uno y lo máximo corregible: D-90 punto 4, con `stock.lotes_de_ingreso`), `resumir_correccion` y
  `registrar_correccion(actor, recepcion_id, lineas=[(detalle_recepcion_id, cantidad)], observacion) -> CorreccionRecepcion`.
- **Registrar:** bloquear cuentas → invernadero → `InsumoInvernadero` → lotes → orden → líneas de la orden → detalles de recepción; volver a
  verificar (9a: el proveedor sin pago en esa orden, `Pago` incluido; el lote conserva la cantidad; la línea no está cerrada con faltante, 4b).
  Crear la corrección (es un `OrigenDocumento`); por cada línea, descontar lote por lote del más nuevo al más viejo con
  `stock.registrar_salida_por_correccion_de_recepcion(lote_id, cantidad, origen_id=correccion.id)` y su `DetalleCorreccionRecepcion`; bajar
  `cantidad_recibida_detalle`; la línea de la orden vuelve a `pendiente` y se recalcula la orden; `avisar_si_quedo_para_pagar` (solo saca);
  **por último** el asiento inverso `[(PROVEEDORES, DEBE, importe), (INSUMOS_EN_STOCK, HABER, importe)]` con el importe de D-89 punto 4. Auditar
  todo. `on_commit`: correo al proveedor.
- **Migración de `inventario`** (la hace esta tarea, D-90 punto 2): el tipo `salida_por_correccion_de_recepcion` y la restricción de origen
  reescrita; con su prueba de que un movimiento de ese tipo sin origen se rechaza.
- **No toca** inconvenientes ni reclamos (R5).

### CMP-EMT-RCL y CMP-CRR-RCL (CMP-06)

- `compras/servicios/reclamos.py`: `reclamos(actor, filtros)`, `emitir_reclamo(actor, reclamo_id)` (Gerente; bloquear el invernadero para la
  alerta y el reclamo; verificar abierto y sin emitir; `gerente = actor`, `fecha_reclamo = hoy`; resolver la alerta por su `AlertaCompras`; auditar
  `emision_reclamo`; `on_commit` correo al proveedor con cada inconveniente) y `cerrar_reclamo(actor, reclamo_id)` (Gerente; verificar emitido y
  abierto; `cerrado`; auditar `cierre_reclamo`). Un reclamo cerrado no se reabre.
- La pestaña «Reclamos» de «Compras» y la sección de la ficha de la orden; panel del Gerente «reclamos sin emitir».

### Pruebas (`compras/tests/`)

| Qué | Archivo |
|---|---|
| CMP-COR-RCP: cada regla, extensión y postcondición (incluido: lote parcialmente consumido, faltante sin lote no corregible, corrección en dos lotes) | `test_cmp_cor_rcp.py` |
| CMP-EMT-RCL y CMP-CRR-RCL | `test_cmp_emt_rcl.py`, `test_cmp_crr_rcl.py` |
| Concurrencia: corrección contra pago; corrección contra consumo del lote; dos emisiones del mismo reclamo | `test_correcciones_concurrencia.py` |

### Pantallas (prototipo: `VIEWS.c_cor` 2605, `tabRcl` 2415, `VIEWS.c_rcl` 2418)
