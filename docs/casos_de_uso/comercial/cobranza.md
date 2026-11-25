# Casos de uso · comercial · Cobranza

Copia para el repo de **COM-REG-CBR · Registrar Cobro de Suministro, versión 0.2**, de **COM-ANL-CBR · Anular Cobro, versión 0.1** y de
**COM-VNC-PAG · Vencer Pagos de Suministro, versión 0.1** (alto nivel), documentos «CU · COM-REG-CBR · Registrar Cobro de Suministro (v0.2)»,
«CU · COM-ANL-CBR · Anular Cobro (v0.1)» y «CU · COM-VNC-PAG · Vencer Pagos de Suministro (v0.1)» de la carpeta de Drive «InfoPonia ·
Comercial · Análisis», consultados el 22/11/2026. Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU (comercial)» (secciones
4, 12, 13 y 14), con el modelo de dominio (reglas 9 a 11 de 8.11 y 9 y 10 de 8.14; ronda 22) y con «MD · Cambios para el modelo de dominio
(comercial)» (MD-115, MD-122, MD-124, MD-125, MD-132, MD-135, MD-136 y MD-139).

**El código va en la app `comercial`** (`comercial/servicios/cobranza.py`, el cobro, la anulación y la mora; `comercial/servicios/entregas.py`,
que ya tiene `monto_a_cobrar` y `estado_de_pago`; `comercial/servicios/comprobantes.py`, el comprobante de cobro y el aviso de mora; las
vistas en `comercial/views_cobranza.py`; modelo en `docs/modelo/comercial.md`: «PagoCliente», «LineaPago», «Entrega», «Anulacion» y
«AlertaComercial»). Cómo se guarda y cómo corre: **D-94**. Tareas: **COM-08a** (COM-REG-CBR y COM-VNC-PAG) y **COM-08b** (COM-ANL-CBR y la
extensión 6a de COM-CNL-CVT, que está en `compra_venta.md`). Archivos de pruebas: `comercial/tests/test_com_reg_cbr.py`,
`test_com_vnc_pag.py`, `test_estado_de_pago.py`, `test_reevaluar_mora.py`, `test_cobranza_calculos.py`, `test_modelos_cobranza.py`,
`test_cobranza_concurrencia.py` y `test_cobranza_vistas.py` (COM-08a);
`test_com_anl_cbr.py` y `test_anulacion_cobro_concurrencia.py` (COM-08b).

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

**Vocabulario (MD-139).** Las versiones de Drive dicen «vencida» y «pago vencido»; en el sistema se dice **«en mora»** y **«pago en mora»**.
La fecha límite conserva su nombre: «vencimiento del pago» (`fecha_vencimiento_pago`). Este extracto copia los casos de uso con su texto
original y aplica MD-139 en «Cómo se aplica» y en las pantallas.

Para nombrar las pruebas: COM-REG-CBR y COM-ANL-CBR no numeran sus reglas (`test_regla_sin_pagos_parciales_…`); postcondiciones
`test_post_<letra>_…`; extensiones `test_ext_<numero>_…` (`test_ext_1a1_…`). COM-VNC-PAG sí numera sus reglas (`test_regla_5_…`).

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| COM-REG-CBR | Registrar Cobro de Suministro | Vendedor del contrato o Gerente | COM-08a | `comercial/tests/test_com_reg_cbr.py` |
| COM-VNC-PAG | Vencer Pagos de Suministro (alto nivel) | InfoPonia (paso diario 30) | COM-08a | `comercial/tests/test_com_vnc_pag.py` |
| COM-ANL-CBR | Anular Cobro | Gerente | COM-08b | `comercial/tests/test_com_anl_cbr.py` |

## COM-REG-CBR · Registrar Cobro de Suministro

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** Comercial. **Versión:** 0.2

**Actor principal:** Vendedor del contrato. El Gerente también puede registrar el cobro.

**Personal involucrado e intereses**

- **Vendedor:** quiere registrar en un solo acto lo que el cliente pagó por una o varias entregas, sin calcular a mano el monto a cobrar de
  cada una ni la indemnización por atraso, y dejar de recibir avisos de pagos vencidos de entregas que ya cobró.
- **Cliente:** quiere pagar exactamente lo que debe por cada entrega, con las indemnizaciones aceptadas ya descontadas, y recibir una
  constancia de lo que pagó y, si pagó tarde, de cómo se calculó la indemnización por atraso.
- **Gerente:** quiere saber qué entregas están pagadas y cuáles vencidas, que la alerta de pago vencido se resuelva sola al cobrarse la
  entrega, y poder registrar el cobro cuando el Vendedor no está.
- **Organización (Jardín Botánico):** quiere que la caja y el banco reflejen el ingreso en el momento en que ocurre (base devengado); que la
  deuda del cliente en Deudores por Ventas baje solo por lo efectivamente cobrado; cobrar la indemnización por atraso que pactó en la cláusula
  del suministrado, sin que nadie la modifique.

**Relaciones con otros casos de uso**

- No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
- **Lo preceden:** COM-CNC-ENT · Concretar Entrega, que concreta la entrega, calcula su monto total, registra la deuda del cliente en Deudores
  por Ventas y le envía el comprobante de entrega con el vencimiento del pago; COM-EVL-DSC · Evaluar Discrepancia y COM-RSV-QJA · Resolver
  Queja, que bajan el monto a cobrar de una entrega sin pagar cuando aceptan una indemnización.
- **Lo siguen:** COM-EVL-DSC y COM-RSV-QJA, que reintegran la indemnización si la aceptan después del cobro (extensión 6a de cada uno).
- **Relacionados, sin inclusión:** el proceso de InfoPonia que, cuando una entrega de suministro vence sin pago, genera la alerta «pago
  vencido» para el Gerente y notifica al Vendedor del contrato (regla 11 de 8.11). Este caso de uso resuelve esa alerta.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.

b. Existe al menos una entrega de suministro «concretada», sin pago de cliente y con monto a cobrar mayor que cero; si el actor es Vendedor,
de un contrato del que es Vendedor.

c. Existe un ejercicio contable vigente y existen las cuentas contables Caja, Banco c/c, Deudores por Ventas e Indemnizaciones por Atraso en
el Pago.

**Garantías mínimas**

- El registro es atómico. Si el caso de uso se cancela o falla, ninguna entrega elegida queda pagada, no se crea el pago de cliente y no se
  registra ningún cambio en la contabilidad, las alertas, las notificaciones ni el log de auditoría.
- Cada entrega se paga una sola vez y por su total: no hay pagos parciales ni una entrega asociada a dos pagos.
- Un pago corresponde a entregas de suministro de un único cliente, y nunca a una compra-venta.
- Lo que se cobra por cada entrega es su monto a cobrar vigente al registrar, más la indemnización por atraso que calcula el Sistema. El actor
  no modifica ninguno de los dos.
- El cobro origina como máximo un asiento contable, con el Debe igual al Haber.

**Garantías de éxito (Postcondiciones)**

a. Se creó un pago de cliente con la fecha actual como fecha de pago, el medio de pago indicado y un monto pagado igual a la suma de los
montos a cobrar de las entregas elegidas más la indemnización por atraso total. Quedó asociado al cliente (R116) y a cada entrega elegida
(R154), y a ninguna compra-venta (restricción C7).

b. Cada entrega elegida quedó con el estado de pago «pagada». Su monto a cobrar quedó fijo: una indemnización que se acepte después se
reintegra al cliente y ya no se descuenta.

c. Por cada entrega pagada después de su vencimiento quedó calculada la indemnización por atraso, con la cláusula del suministrado del
contrato (regla «Indemnización por atraso en el pago»).

d. Se generó un único asiento compuesto, originado en el pago de cliente (R012), en el libro diario del ejercicio vigente, con la fecha
actual: Debe Caja (efectivo) o Banco c/c (los demás medios), por el monto pagado; Haber Deudores por Ventas, por la suma de los montos a
cobrar de las entregas; Haber Indemnizaciones por Atraso en el Pago, por la indemnización total, solo si es mayor que cero.

e. La alerta «pago vencido» de cada entrega elegida que la tuviera activa pasó a «resuelta», con la fecha de resolución igual a la fecha
actual.

f. Se envió al cliente, por correo, el comprobante de cobro (uso interno). Si el cobro lo registró el Gerente, se notificó al Vendedor de
cada contrato involucrado.

g. Se creó un log de auditoría por el pago de cliente y por el asiento creados, y por cada alerta modificada, con usuario, rol, fecha, hora,
identificador y cambios de valor.

**Escenario principal de éxito** (cobro de una o más entregas de un mismo cliente, sin solicitudes de revisión pendientes sobre ellas)

1. **El actor inicia el registro de un cobro de suministro.**
2. **El Sistema presenta los clientes con entregas de suministro sin pagar (si el actor es Vendedor, solo las de sus contratos). De cada
   cliente indica la cantidad de entregas sin pagar, cuántas están vencidas y el total adeudado.**
3. **El actor selecciona un cliente.**
4. **El Sistema presenta las entregas sin pagar del cliente, de la fecha de vencimiento del pago más antigua a la más reciente. De cada una
   indica el contrato, la fecha en que se concretó, el invernadero de origen, el monto total, las indemnizaciones aceptadas que se le
   descuentan, el monto a cobrar, la fecha de vencimiento del pago, el estado de pago («pendiente» o «vencida») y, si está vencida, los días
   de atraso.**
5. **El actor elige las entregas que el cliente paga.**
6. **El Sistema calcula, para cada entrega elegida, la indemnización por atraso a la fecha actual, y presenta el monto a cobrar de cada una,
   su indemnización por atraso y el total a cobrar.**
7. **El actor indica el medio de pago.**
8. **El Sistema presenta un resumen con el cliente, las entregas con su monto a cobrar y su indemnización por atraso, el total a cobrar, el
   medio de pago, la fecha del pago (la actual) y el asiento que se registrará.**
9. **El actor confirma el cobro.**
10. **El Sistema registra el cobro: verifica que cada entrega siga sin pagar y con el mismo monto a cobrar e indemnización por atraso; crea el
    pago de cliente asociado al cliente y a las entregas; registra el asiento; resuelve las alertas «pago vencido» de esas entregas y
    registra la auditoría correspondiente.**
11. **El Sistema envía al cliente el comprobante de cobro (uso interno) y, si el actor es el Gerente, notifica el cobro al Vendedor de cada
    contrato involucrado.**
12. **El Sistema informa al actor que el cobro fue registrado y presenta su identificador, el total cobrado y el asiento generado.**

**Extensiones (o Flujos Alternativos)**

- **\*a. En cualquier momento antes del paso 9, el actor cancela el registro:** 1. El Sistema descarta los datos ingresados sin registrar
  ningún cambio. Las entregas siguen sin pagar.
- **\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:** 1. El Sistema revierte cualquier registro parcial de la
  operación. 2. Al restablecerse, el Sistema informa al actor que el cobro no fue registrado. 3. El actor reinicia el caso de uso desde el
  paso 1.
- **1a. El actor inicia el cobro desde la alerta o la notificación de pago vencido de una entrega:** 1. El Sistema presenta las entregas sin
  pagar del cliente de esa entrega, con esa entrega ya elegida. 2. El caso de uso continúa en el paso 5.
  - **1a1. La entrega de la alerta o de la notificación ya está pagada (por ejemplo, otro usuario registró el cobro mientras tanto):** 1. El
    Sistema informa el pago, su fecha y quién lo registró. 2. El caso de uso termina.
- **3a. La entrega del cliente tiene una discrepancia o una queja «pendiente de revisión»:** 1. El Sistema la señala en el paso 4, con el
  tipo de solicitud y su fecha, y advierte que, si la entrega se cobra ahora y la solicitud se acepta después, la indemnización se
  reintegrará al cliente en lugar de descontarse. 2. El caso de uso continúa en el paso 4. El actor puede elegir igual esa entrega.
- **5a. El actor no elige ninguna entrega:** 1. El Sistema señala que hay que elegir al menos una entrega. 2. El caso de uso vuelve al paso 5.
- **8a. El actor quiere cambiar las entregas elegidas o el medio de pago:** 1. El caso de uso vuelve al paso 5 (entregas) o al paso 7 (medio
  de pago).
- **10a. Al registrar, una entrega elegida ya está pagada (otro usuario la cobró desde otra sesión):** 1. El Sistema no registra ningún
  cambio e informa qué entrega ya tiene pago, la fecha del pago y quién lo registró. 2. El caso de uso vuelve al paso 4, con los datos
  actualizados.
- **10b. Al registrar, cambió el monto a cobrar o la indemnización por atraso de una entrega elegida (se aceptó una discrepancia o una queja
  mientras tanto, o cambió la fecha actual):** 1. El Sistema no registra ningún cambio e informa, por cada entrega afectada, el monto
  anterior y el nuevo. 2. El caso de uso vuelve al paso 6, con los montos recalculados.
- **11a. El Sistema no logra enviar el correo al cliente o la notificación al Vendedor:** 1. El cobro permanece registrado. 2. El Sistema
  reintenta el envío.

**Requisitos especiales**

- La interfaz del Vendedor y del Gerente está pensada para computadora.
- Las entregas del paso 4 se presentan en no más de 2 segundos desde la selección del cliente.
- El registro del paso 10 se completa en no más de 5 segundos y se ejecuta como una única transacción.
- El control de concurrencia cumple dos funciones: impide que una entrega se cobre dos veces; impide que una entrega se cobre mientras se
  registra la aceptación de una discrepancia o de una queja sobre ella. Es la contraparte de la extensión 8b de COM-EVL-DSC y de COM-RSV-QJA.
- Solo los usuarios con rol Vendedor o Gerente acceden a este caso de uso. El Vendedor solo ve y cobra las entregas de los contratos de los
  que es Vendedor.
- La fecha y la hora actuales se toman en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos se expresan en pesos argentinos, con dos decimales.
- El comprobante de cobro es de uso interno y no tiene validez fiscal.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

- **Quién cobra:** el Vendedor del contrato de la entrega (R115) o el Gerente. Las entregas de un contrato cuyo Vendedor está inactivo las
  cobra el Gerente. (Pasos 2 y 4)
- **Entrega cobrable:** entrega de suministro «concretada», sin pago de cliente (estado de pago «pendiente» o «vencida») y con monto a cobrar
  mayor que cero. Se cobra cualquiera sea el estado del contrato (vigente, finalizado o resuelto) y aunque el cliente esté inactivo, porque un
  cliente inactivo conserva los cobros de sus suministros (nota de la 17ª ronda en Cliente; reglas 1 y 2 de 8.18). (Paso 4)
- **Un cliente por cobro:** todas las entregas de un cobro son del mismo cliente; pueden ser de contratos distintos (R116 y R154). (Pasos 3
  y 5)
- **Sin pagos parciales:** cada entrega se paga una sola vez y por su monto a cobrar (regla 9 de 8.11). Si el cliente paga menos que el total
  adeudado, se cobran solo las entregas que su pago cubre completas. (Paso 5)
- **Monto a cobrar:** monto total de la entrega − Σ montos descontados por las solicitudes aceptadas de sus detalles antes del pago (regla 10
  de 8.14). Nunca es negativo: una indemnización se descuenta como máximo hasta el monto a cobrar y el resto se reintegra (MD-115). Una
  entrega con monto a cobrar cero queda saldada: su estado de pago es «pagada» aunque no tenga pago de cliente, no se ofrece para cobrar y no
  genera alerta «pago vencido» (MD-125). (Paso 4)
- **Vencimiento del pago:** fecha en que se concretó la entrega + plazo de pago de la cláusula del suministrado del contrato (regla 10 de
  8.11; MD-124). Hay un solo vencimiento por entrega, aunque lleve varios detalles. La entrega está vencida desde el día siguiente a su
  vencimiento; el día del vencimiento todavía se paga sin atraso. (Paso 4)
- **Indemnización por atraso en el pago:** días de atraso = fecha del pago − vencimiento de la entrega. Si es mayor que cero, la
  indemnización de la entrega es días de atraso × indemnización por retraso en el pago de la cláusula del suministrado del contrato, una sola
  vez por entrega, aunque lleve varios detalles (MD-124). La del cobro es la suma de las de sus entregas. No se ajusta por el mecanismo de
  precio (regla 7 de 8.11) y el actor no la modifica ni la condona. Por ejemplo, una entrega concretada el 01/11 de un contrato con plazo de
  pago de 10 días y $300 por día de atraso, pagada el 14/11: vence el 11/11, tiene 3 días de atraso y su indemnización es 3 × $300 = $900.
  (Paso 6)
- **Fecha del pago:** es la fecha actual, sin fechas retroactivas, con el mismo criterio que la concreción de una entrega (regla 7 de 8.13).
  (Paso 8)
- **Medio de pago:** uno por cobro: efectivo, transferencia, tarjeta de débito o tarjeta de crédito. El efectivo se imputa a Caja y los
  demás, a Banco c/c, con acreditación inmediata (regla 15 de 8.13). (Paso 7)
- **Asiento del cobro:** uno solo, compuesto, originado en el pago de cliente (R012; reglas 9 y 10 de 8.11): Debe Caja o Banco c/c por el
  total / Haber Deudores por Ventas por la suma de los montos a cobrar / Haber Indemnizaciones por Atraso en el Pago por la indemnización
  total, si es mayor que cero. (Paso 10)
- **Indemnización aceptada después del cobro:** ya no se descuenta del monto a cobrar: se reintegra al cliente (regla 9 de 8.14). Por eso el
  Sistema advierte las solicitudes pendientes antes de cobrar. (Extensión 3a)
- **El atraso no es un incumplimiento de la empresa:** no suma a la cantidad de incumplimientos del contrato (regla 6 de 8.11) ni genera un
  registro de bitácora.
- **Alerta «pago vencido»:** una por entrega, para el Gerente, asociada a la entrega (MD-122). La genera InfoPonia cuando la entrega vence sin
  pago (regla 11 de 8.11) y se resuelve en la misma transacción del cobro, o cuando la entrega queda saldada (MD-125). (Paso 10)
- **Avisos:** el cliente recibe el comprobante de cobro; si cobró el Gerente, el Vendedor de cada contrato recibe una notificación. (Paso 11)

**Lista de tecnología y variaciones de datos**

- **4.** Los montos se expresan en pesos, con dos decimales, y los días de atraso, como números enteros. El actor puede filtrar las entregas
  por contrato y por estado de pago («pendiente» o «vencida»).
- **7.** El medio de pago se elige de la lista: efectivo, transferencia, tarjeta de débito o tarjeta de crédito.
- **11.** El comprobante de cobro incluye el cliente, la fecha y el medio de pago; por cada entrega, su fecha, el contrato, el monto total,
  las indemnizaciones descontadas, el monto a cobrar, el vencimiento del pago y, si hubo atraso, los días y la indemnización; y el total
  cobrado. Aclara que es de uso interno, sin validez fiscal.
- **11.** La notificación al Vendedor indica el cliente, las entregas, el total cobrado y quién registró el cobro. Se entrega dentro del
  Sistema y puede, además, enviarse por correo electrónico.

**Frecuencia:** frecuente: una vez por cada pago que hace un cliente de suministro. Con entregas periódicas, varias veces por semana para cada
Vendedor. A confirmar con el Jardín Botánico.

**Temas abiertos**

- **Pago mixto:** un cobro tiene un único medio de pago (PagoCliente.medioPago). Si el cliente paga una misma entrega parte en efectivo y
  parte por transferencia, hoy no se puede registrar. ¿Hace falta admitirlo?
- **Pago anterior a su registro:** la fecha del pago es la actual. Si una transferencia se acreditó antes de que el Vendedor la registre, el
  cliente puede cargar con días de atraso que no tuvo. ¿Debe poder indicarse una fecha anterior, con un límite y bajo control del Gerente?
- **Condonación de la indemnización por atraso:** nadie puede perdonarla, igual que el Gerente no ajusta el monto de una cláusula (regla 2 de
  8.14). ¿Debe poder hacerlo el Gerente, con un motivo?
- **Anulación de un cobro mal registrado** (entrega, cliente o medio equivocados): hoy no hay forma. ¿Se resuelve con un contraasiento
  (CU-17) y desasociando las entregas del pago? **(Resuelto por COM-ANL-CBR, PCU sección 14.)**
- **Pago anticipado o a cuenta:** no se puede registrar un pago antes de concretarse la entrega ni un pago a cuenta, porque no hay saldo a
  favor del cliente (regla 9 de 8.14).

Las «Situaciones encontradas y propuestas» de la versión 0.1 (1 a 7) están en el documento de Drive; las 3, 4 y 5 quedaron resueltas
(MD-124, MD-125, MD-115, MD-122) y ya están aplicadas en las reglas de arriba.

## COM-VNC-PAG · Vencer Pagos de Suministro

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos», sección «Casos de uso de alto nivel».
Reemplaza al caso 32 de PCU. Decisiones del 20/11/2026 aplicadas: vence cuando la fecha de vencimiento es anterior a hoy (A); una alerta por
entrega (B); sin recordatorios repetidos (C); correo al cliente al vencer (D); vence aunque haya una solicitud pendiente (E); exclusiones (F).

**Actores:** InfoPonia (proceso automático). **Tipo:** primario, esencial. **Versión:** 0.1

**Disparador:** la ejecución diaria de InfoPonia, en su paso 2 (T-04).

**Objetivo:** detectar las entregas de suministro que vencieron sin pagarse y avisar al Gerente, al Vendedor y al cliente.

**Precondición:** a. Ninguna. Si no hay entregas vencidas, el paso termina sin cambios.

**Postcondición** (por cada entrega que venció):

a. Se generó una alerta «pago vencido» para el Gerente, asociada a la entrega (MD-122, T-01), con el cliente, el contrato, el monto a cobrar,
la fecha de vencimiento y la indemnización por día de atraso del contrato.

b. Se notificó al Vendedor del contrato.

c. Se le envió al cliente un correo, una sola vez, con la entrega, el monto a cobrar, la fecha de vencimiento y la indemnización por día de
atraso.

d. Si la entrega tiene una queja o una discrepancia pendiente, la alerta y el correo lo aclaran.

e. Se creó un log de auditoría con origen InfoPonia, el identificador de la entrega y el de la alerta.

**Reglas**

1. Entrega vencida: entrega de suministro concretada, sin pagar, con monto a cobrar mayor que cero (MD-125) y con fecha de vencimiento
   (MD-132) anterior a la fecha actual. El día del vencimiento todavía se puede pagar sin atraso.
2. Una sola alerta «pago vencido» por entrega, aunque el proceso se repita. La pantalla del Gerente puede agruparlas por cliente.
3. Ni la alerta, ni la notificación, ni el correo se repiten. La alerta sigue activa hasta el cobro y la pantalla muestra los días de atraso y
   la indemnización acumulada.
4. El correo al cliente se envía una vez, al vencer; si falla, se reintenta; si el cliente no tiene correo, no se envía.
5. La entrega vence aunque tenga una queja o discrepancia sin resolver, porque el plazo es del contrato. Si después la solicitud baja el monto
   a cobrar (MD-115), COM-REG-CBR cobra el monto nuevo.
6. No entran las entregas pagadas, las saldadas ni las de compra-venta. Sí entran las de contratos finalizados o resueltos, porque la deuda
   sigue.
7. COM-REG-CBR resuelve la alerta al registrar el cobro. Si se anula el cobro (caso 29, Anular Cobro), la alerta se reactiva; se define al
   especificar ese caso.
8. Este proceso no calcula ni registra la indemnización: la calcula COM-REG-CBR al cobrar (regla 10 de 8.11).
9. Es el paso 2 de la ejecución diaria, después de vencer las partidas en cámara y antes de pre-reservar.
10. La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).

## COM-ANL-CBR · Anular Cobro

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza al caso 29 de PCU y responde
al tema abierto 4 de COM-REG-CBR. Decisiones del 20/11/2026 aplicadas: la reversión la origina una Anulación (A; MD-135); contraasiento
invertido con fecha actual (B); el cobro queda «anulado» (C; MD-136); se indica si el cliente realmente pagó, para no cobrarle atraso de más
(D); solo cobros de suministro (E).

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** Comercial / Cobros. **Versión:** 0.1

**Actor principal:** Gerente.

**Personal involucrado e intereses**

- **Gerente:** quiere corregir un cobro mal cargado (medio o entrega equivocados, o un pago que no se acreditó) sin borrar la historia.
- **Cliente:** quiere no pagar días de atraso que no tuvo.
- **Vendedor:** quiere saber qué entregas de su contrato vuelven a estar sin pagar.

**Relaciones con otros casos de uso**

- **Lo precede:** COM-REG-CBR · Registrar Cobro de Suministro.
- **Lo sigue:** COM-REG-CBR, para registrar el cobro correcto.
- **Relacionados:** COM-VNC-PAG, por la alerta «pago vencido»; COM-ANL-SRV y COM-ATN-ENR, que pueden pedir anular el cobro primero.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Gerente.

b. Existe un cobro de suministro no anulado.

**Garantías mínimas**

- La anulación es atómica.
- El cobro y su asiento original no se borran ni se modifican.
- Ninguna entrega queda «pagada» por un cobro anulado.

**Garantías de éxito (Postcondiciones)**

a. El cobro pasó a «anulado» y conserva su vínculo con las entregas (MD-136).

b. Se creó una Anulación con la fecha actual, el motivo obligatorio, el usuario, el cobro anulado y la indicación de si el cliente realmente
pagó en esa fecha (MD-135).

c. La Anulación originó el contraasiento del cobro completo, incluida la indemnización por atraso si la hubo.

d. Cada entrega del cobro volvió a «pendiente» o «vencida», según su fecha de vencimiento.

e. Cada entrega que vuelve a «vencida» tiene activa su alerta «pago vencido», reactivada o generada, y se notificó al Vendedor. El correo al
cliente no se repite.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del cobro y de la Anulación, el motivo y las entregas afectadas.

**Escenario principal de éxito**

1. El Gerente busca un cobro de suministro e inicia la anulación.
2. El Sistema presenta el cobro (fecha, medio, monto, indemnización por atraso y entregas) y qué va a pasar: el contraasiento y el estado en
   que queda cada entrega.
3. El Gerente escribe el motivo e indica si el cliente realmente pagó en la fecha del cobro (por ejemplo, si solo se cargó mal el medio o la
   entrega).
4. El Gerente confirma.
5. El Sistema vuelve a verificar que el cobro siga sin anular. Luego, en una única transacción, registra la Anulación, el contraasiento, los
   estados, las alertas y la auditoría.
6. El Sistema notifica al Vendedor.
7. El Sistema informa que el cobro quedó anulado y ofrece registrar el cobro correcto (COM-REG-CBR).

**Extensiones**

- **\*a. Antes del paso 4, el Gerente cancela:** 1. No se registra nada.
- **\*b. El Sistema falla:** 1. El Sistema revierte cualquier registro parcial.
- **1a. El cobro es de una compra-venta:** 1. El Sistema informa que no se anula desde acá, porque va dentro del asiento de la entrega, y que
  la corrección se hace con CU-17.
- **3a. El motivo está vacío:** 1. El Sistema lo pide.
- **5a. Al registrar, el cobro ya fue anulado en otra operación:** 1. El Sistema no registra ningún cambio, informa la situación y el caso de
  uso termina.
- **7a. El Gerente registra enseguida el cobro correcto y había indicado que el cliente sí pagó:** 1. COM-REG-CBR propone la fecha del cobro
  anulado como fecha de cobro, para que la indemnización por atraso sea la que correspondía.

**Requisitos especiales**

- El paso 5 es una única transacción, serializada con COM-REG-CBR, COM-ANL-SRV y COM-VNC-PAG sobre las mismas entregas.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**

- **Quién anula:** solo el Gerente, con motivo obligatorio.
- **Alcance:** solo cobros de suministro.
- **Cobro anulado:** queda «anulado» con su historia; una entrega está «pagada» solo si tiene un cobro no anulado (MD-136).
- **Contraasiento:** lo origina la Anulación, con las mismas cuentas e importes, Debe y Haber invertidos y fecha actual, incluida la
  indemnización.
- **Estado de las entregas:** se recalcula con su fecha de vencimiento guardada (MD-132).
- **Alerta y avisos:** la alerta «pago vencido» se reactiva o se genera y se notifica al Vendedor; el correo al cliente no se repite.
- **Volver a cobrar:** si el cliente sí pagó en esa fecha, COM-REG-CBR propone la fecha del cobro anulado, para no cobrarle atraso que no tuvo.

**Frecuencia:** rara.

## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| MD-139 | «Vencida» → «en mora»; «pago vencido» → «pago en mora». El vencimiento del pago conserva su nombre | Los tres casos de uso (textos, filtros, alerta) |
| MD-136; **D-94, punto 2** | Un cobro anulado conserva su vínculo con las entregas y una entrega puede volver a cobrarse: R154 se guarda en `LineaPago` (una entrega puede tener un pago anulado y uno vigente). El caso de uso dice «una entrega asociada a dos pagos» no (garantía mínima 2): se lee «a dos pagos **vigentes**» | COM-REG-CBR, postcondición a; COM-ANL-CBR, postcondición a |
| PCU, sección 14; **D-94, punto 10** | Si el cobro anulado indicaba que el cliente sí pagó, COM-REG-CBR propone la fecha del cobro anulado (7a de COM-ANL-CBR). La regla «Fecha del pago» de COM-REG-CBR v0.2 todavía dice «sin fechas retroactivas»: vale fuera de ese camino. Va a pendientes_CU (COM-REG-CBR v0.3) | COM-REG-CBR, paso 8 y regla «Fecha del pago»; COM-ANL-CBR 7a |
| PCU, sección 14 | El tema abierto 4 de COM-REG-CBR (anular un cobro mal registrado) queda cerrado por COM-ANL-CBR | COM-REG-CBR, «Temas abiertos» |
| PCU, sección 12 (T-04); D-56, punto 6 | «Paso 2 de la ejecución diaria» es el **orden 30** de `core/procesos.py` (después del 20, el 25 y el 27; antes del 33, el 35, el 40 y el 50) | COM-VNC-PAG, disparador y regla 9 |
| COM-ANL-CBR (postcondición e); **D-94, punto 5** | La regla 7 de COM-VNC-PAG («se define al especificar ese caso») queda definida: se asegura una alerta nueva del mismo tipo y clave (la API no reabre una resuelta, D-69 punto 4) | COM-VNC-PAG, regla 7 |
| MD-125 | Una entrega saldada (monto a cobrar 0) es «pagada» sin pago; su alerta se resuelve | COM-REG-CBR, regla «Monto a cobrar»; COM-VNC-PAG, regla 6 |
| D-57; **D-94, punto 16** | Fuera de esta ronda · contabilidad: la precondición c y la postcondición d de COM-REG-CBR (y lo que los pasos 8 y 12 muestran del asiento); la postcondición c de COM-ANL-CBR (el contraasiento) y lo que su paso 2 muestra de él | COM-REG-CBR y COM-ANL-CBR |

## Cómo se aplica en la ronda «Comercial 1» (COM-08a y COM-08b; D-44, D-57, D-68, D-69, D-94)

### Qué entra y qué no

- **COM-08a:** COM-REG-CBR y COM-VNC-PAG completos, sin el asiento; `LineaPago`, lo nuevo de `PagoCliente` y de `Entrega`; `estado_de_pago`
  con «pagada»; `reevaluar_mora` y la alerta «pago en mora»; el paso 30; la pestaña «Cobranza» («Por cobrar» y «Cobros registrados», sin
  «Anular»); el grupo «Cobranza» del panel de control; lo que completa a otras tareas (abajo).
- **COM-08b:** COM-ANL-CBR completo, sin el contraasiento; `Anulacion.pago_cliente`, `cliente_pago_en_fecha` y `PagoCliente.anulacion_corregida`; la
  fecha propuesta de 7a en la pantalla de COM-REG-CBR; «Anular» en «Cobros registrados»; la extensión 6a de COM-CNL-CVT (`compra_venta.md`).
- **Fuera de esta ronda · contabilidad** (D-57): la precondición c y el asiento de COM-REG-CBR; el contraasiento de COM-ANL-CBR. El código
  guarda todo lo que necesitan (medio, lo cobrado y el atraso por entrega) y no crea asientos.

### Servicios (`comercial/servicios/cobranza.py`)

| Función | Caso de uso | Tarea | Qué hace |
|---|---|---|---|
| `clientes_con_deuda(actor, hoy) -> list[ClienteConDeuda]` | COM-REG-CBR, paso 2 | 08a | Lectura: por cliente, la cantidad de entregas sin pagar, cuántas en mora, el total a cobrar y el total en mora. Ver «Por cobrar» |
| `entregas_cobrables(actor, cliente_id, hoy, filtros, fecha_pago=None) -> list[EntregaCobrable]` | Pasos 4 y 6 (y 3a) | 08a | Lectura. Ver «Entregas cobrables» |
| `resumen_de_cobro(actor, datos) -> ResumenDeCobro` | Paso 8 (y 5a, 8a) | 08a | No escribe. Valida, calcula y arma la **huella** (D-94, punto 9) |
| `registrar_cobro(actor, datos, huella) -> PagoCliente` | Paso 10 (y 10a, 10b) | 08a | Ver «Registrar el cobro» |
| `reenviar_comprobante_de_cobro(actor, pago_id) -> bool` | 11a | 08a | Vuelve a mandar el comprobante; devuelve si salió |
| `cobros_registrados(actor, filtros, pagina)` y `ficha_de_cobro(actor, pago_id)` | (lectura) | 08a | La lista y la ficha de los cobros (prototipo, «Cobros registrados») |
| `reevaluar_mora(entrega, hoy, avisar_vendedor) -> Alerta \| None` | COM-VNC-PAG; postcondición e de COM-REG-CBR; e de COM-ANL-CBR; MD-125 | 08a | Ver «La mora». **No bloquea**: la llama quien ya bloqueó el invernadero y la entrega |
| `vencer_pagos(hoy) -> ResumenDePaso` | COM-VNC-PAG (paso 30) | 08a | Ver «Paso diario 30» |
| `datos_de_anulacion_de_cobro(actor, pago_id) -> DatosDeAnulacionDeCobro` | COM-ANL-CBR, paso 2 (y 1a) | 08b | Lectura: el cobro, cada entrega con su estado después (pendiente o en mora), qué alertas se van a asegurar y la huella |
| `anular_cobro(actor, pago_id, motivo, cliente_pago_en_fecha, huella) -> Anulacion` | COM-ANL-CBR, paso 5 | 08b | Ver «Anular un cobro» |

Todas las de escritura reciben al actor, verifican su rol y que siga activo **después de bloquear** y lanzan `ErrorComercial(codigo, mensaje,
campo=None)`. Códigos nuevos: `sin_entregas_elegidas` (5a), `entregas_de_otro_cliente`, `entrega_no_cobrable` (no es de suministro, no está
concretada, está saldada o es de otro alcance), `entrega_ya_pagada` (1a1, 10a: con el cobro, su fecha y quién lo registró),
`cobro_cambio` (10b: con el monto anterior y el nuevo de cada entrega), `medio_de_pago_obligatorio` (ya existe, COM-06a), `fecha_no_admitida`
(una fecha anterior sin la anulación que la justifica), `cobro_de_compra_venta` (1a de COM-ANL-CBR), `cobro_ya_anulado` (5a),
`anulacion_ya_usada` (el cobro correcto de esa anulación ya se registró), `motivo_obligatorio`, `motivo_largo`; y los comunes
`cambio_simultaneo` y `sin_permiso`.

### Estado de pago y monto a cobrar (COM-08a; D-94, punto 4)

`entregas.estado_de_pago(entrega_ids, hoy) -> dict[int, EstadoDePago]` (COM-06a) se completa. `EstadoDePago(estado, saldada, cobro)`:

| Estado | Cuándo | `saldada` | `cobro` |
|---|---|---|---|
| `pagada` | Tiene una `LineaPago` vigente | `False` | El código, la fecha y quién lo registró |
| `pagada` | Monto a cobrar = 0 (MD-125) | `True` | `None` |
| `en_mora` | No pagada y `hoy > fecha_vencimiento_pago` | `False` | `None` |
| `pendiente` | No pagada y `hoy <= fecha_vencimiento_pago` | `False` | `None` |

Solo para entregas de suministro concretadas; para cualquier otra, la clave no está (como hoy). Una consulta por tabla (entregas, líneas de
pago vigentes, solicitudes aceptadas). `monto_a_cobrar` (COM-06a, con lo descontado desde COM-07a) **no cambia**: después del cobro sigue
siendo el total menos lo descontado antes del pago, porque una aceptación posterior reintegra y no descuenta (`indemnizaciones.aplicacion`,
COM-07a, con `pagada=True`). Lo que se cobró queda en `LineaPago.monto_cobrado`: invariante, `monto_cobrado = monto_a_cobrar` de su entrega
mientras la línea esté vigente.

### Cálculos (funciones puras con pruebas de tabla, en `comercial/servicios/cobranza.py`)

- `dias_de_atraso(fecha_vencimiento, fecha_pago) -> int`: `max(0, (fecha_pago − fecha_vencimiento).days)`. El día del vencimiento da 0.
- `indemnizacion_por_atraso(dias, por_dia) -> Decimal`: `dias × por_dia`, `ROUND_HALF_UP` a dos decimales; 0 si `dias = 0`. `por_dia` =
  `entrega.indemnizacion_retraso_dia`, la de la cláusula vigente al vencer (D-94, punto 12; si es nula, la de
  `contrato.clausula_suministrado` de hoy). Ejemplo de la regla: vence el 11/11, se
  paga el 14/11, $300 por día → 3 días, $900,00.
- `total_del_cobro(lineas) -> Decimal`: Σ (`monto_a_cobrar` + indemnización). Siempre `Decimal`, nunca `float`.

### Por cobrar (paso 2 de COM-REG-CBR; prototipo `tabCobranza` y `cobGroups`)

- **Alcance:** el Gerente, todas las entregas; el Vendedor, las de los contratos de los que es Vendedor (`Contrato.objects.en_alcance_de`,
  D-28). Los demás roles, 403 con mensaje.
- **Qué entra:** entregas de suministro concretadas, **no pagadas** (ni con línea vigente ni saldadas) y con monto a cobrar > 0, de cualquier
  estado del contrato y de clientes activos o no (regla «Entrega cobrable»).
- **Por cliente** (paso 2), de la A a la Z por nombre visible: la cantidad de entregas, cuántas en mora, el total a cobrar y el total en mora
  (en rojo si hay), con «Registrar cobro» (lleva a la pantalla con el cliente elegido). Cada grupo se despliega con sus entregas, de la que
  vence primero a la última: entrega (`OT-0231`), contrato, fecha de concreción, vencimiento (con «hace 3 días» o «en 5 días»), monto a cobrar
  (con «con descuento de $ …» si lo hubo), estado de pago y, si está «no reconocida», esa marca (COM-06b).
- Una consulta para los grupos y otra para las entregas de los grupos abiertos; sin consultas por fila.

### Entregas cobrables (pasos 4 y 6; 3a)

`EntregaCobrable` por cada entrega del cliente que el actor puede cobrar: el código, el contrato, la fecha de concreción, el invernadero de
origen, el monto total, lo descontado (Σ `monto_descontado` de las aceptadas), el monto a cobrar, el vencimiento, el estado (`pendiente` o
`en_mora`), los días de atraso y la indemnización **a la fecha del pago** (hoy o, en 7a, la del cobro anulado) y las solicitudes pendientes
de la entrega (tipo, número y fecha: 3a). Orden: vencimiento ascendente y, a igualdad, código. Filtros (Lista de tecnología, 4): contrato y
estado de pago («Pendientes», «En mora» o los dos). **Tiempo:** dos consultas para toda la lista (requisito especial: 2 segundos).

### Registrar el cobro (paso 10; D-94, puntos 3, 8, 9 y 12)

- **`datos`** (`DatosDeCobro`): `cliente_id`, `entrega_ids` (al menos una: `sin_entregas_elegidas`), `medio_pago` (de la lista de
  `PagoCliente.medio_pago`: `medio_de_pago_obligatorio`) y, solo en COM-08b, `anulacion_id` y `usar_fecha_anulada` (7a).
- **Bloqueos** (`docs/patrones/bloqueos.md`, «Cobranza»): las cuentas (el actor y los Vendedores de los contratos de las entregas, en una
  consulta y en orden de id) → los **invernaderos de origen** de las entregas (`bloquear_invernadero_para_alertas`, en orden de id: activos o
  no) → las **entregas** (`OrdenTrabajo` de cada una, en orden de id). Después, la relectura:
  - el actor sigue activo y con su rol, y cada entrega está en su alcance (`sin_permiso`);
  - todas son del mismo cliente (`entregas_de_otro_cliente`), de suministro, concretadas y con monto a cobrar > 0 (`entrega_no_cobrable`);
  - ninguna tiene línea de pago vigente (10a: `entrega_ya_pagada` con el cobro; la pantalla vuelve al paso 4);
  - la **huella** coincide: por cada entrega, el estado de pago, el monto a cobrar y la indemnización por atraso, y la fecha de hoy (10b:
    `cobro_cambio` con lo anterior y lo nuevo; la pantalla vuelve al paso 6 con los montos recalculados).
- **Con todo verificado:**
  1. el `PagoCliente`: `tipo_pago = suministro`, `numero` de la secuencia (`COB-0032`), `cliente`, `medio_pago`, `fecha_pago` (hoy, o la del
     cobro anulado en 7a), `monto_pagado` (el total), `estado_pago = vigente`, `usuario = actor` y, en 7a, `anulacion_corregida`;
  2. una `LineaPago` por entrega: `monto_cobrado` (el monto a cobrar releído bajo bloqueo), `dias_atraso`, `indemnizacion_atraso`, `vigente
     = True` (postcondiciones a, b y c);
  3. por cada entrega, `reevaluar_mora(entrega, hoy, avisar_vendedor=False)`: resuelve su alerta «pago en mora» si estaba activa (e);
  4. si el actor es el Gerente, un aviso a cada Vendedor activo de los contratos involucrados (f; D-42, dentro de la transacción): «COB-0032
     registrado», «El Gerente registró el cobro de Pérez SA: OT-0231 y OT-0240 (SUM-0013), $ 47.200,00 por transferencia, con $ 1.200,00 de
     atraso.»;
  5. el registro de auditoría (g; abajo);
  6. `on_commit`: el comprobante de cobro al cliente (f, 11a).
- **Fecha del pago:** hoy (`hoy()` de la zona del invernadero, requisito especial). Una fecha anterior solo con 7a (COM-08b, D-94 punto 10;
  si no, `fecha_no_admitida`). Nunca posterior.
- **El comprobante de cobro** (Lista de tecnología, 11; tipo `cobro` de `comprobantes.py`, como el de COM-02): el cliente, el código, la fecha
  y el medio; por cada entrega, su fecha, el contrato, el monto total, lo descontado, el monto a cobrar, el vencimiento y, si hubo atraso, los
  días y la indemnización; el total. Pie: «Comprobante interno, sin validez fiscal.». Resultado en `PagoCliente.estado_aviso_cliente`
  (`enviado` / `pendiente_envio` / `sin_correo`; el cliente de un suministro tiene correo mientras tenga un contrato vigente, regla 18 de
  8.20: uno de un contrato terminado puede no tenerlo). Con `pendiente_envio`: «Reenviar comprobante» en la ficha del cobro y el reintento de
  la parte 4 del paso 50 («Correos pendientes», `entregas.md`), que suma los pagos con `pendiente_envio`. Sin correo: «Imprimir comprobante».
- **Auditoría** (D-36): un registro `registro_cobro`, con el actor y su rol; afectados: el pago (principal, con sus datos), sus líneas y las
  alertas resueltas; en `datos`, por cada entrega, el monto a cobrar, los días y la indemnización (como texto). El asiento no existe en esta
  ronda.
- **Lo que no hace:** no crea el asiento (D-57); no toca la entrega, el contrato, el contador de incumplimientos ni la bitácora (regla «El
  atraso no es un incumplimiento»).

### La mora (COM-VNC-PAG; D-94, puntos 5 a 7)

- **`reevaluar_mora(entrega, hoy, avisar_vendedor)`** (la llaman con el invernadero de origen y la entrega ya bloqueados):
  - si la entrega **está en mora** (`estado_de_pago` = `en_mora`): `alertas.asegurar_alerta_de_estado(entrega.invernadero_id,
    "comercial_pago_en_mora", clave=f"entrega:{entrega.pk}", descripcion=…)` (la API recibe el **id** del invernadero); si la alerta es nueva (sin `AlertaComercial`), crea su
    `AlertaComercial(entrega=…)`. Si `fecha_aviso_mora` es nula: la carga con `hoy` y programa el aviso de mora al cliente (`on_commit`). Si
    `avisar_vendedor`: el aviso al Vendedor del contrato, si está activo;
  - si **no está en mora** (pagada, saldada o pendiente): `alertas.resolver_alerta_de_estado(entrega.invernadero_id,
    "comercial_pago_en_mora", clave=f"entrega:{entrega.pk}")` (nada si no había);
  - devuelve la alerta activa o `None`. No audita: lo hace quien la llama.
- **El tipo** (en `comercial/apps.py`, `ready()`): `comercial_pago_en_mora`, «Pago en mora», `GERENTE`, `CRITICA`, `Clase.ESTADO`, origen
  `ENTREGA`. **Descripción** (hasta 500): «OT-0231 · Pérez SA · SUM-0013 · $ 46.000,00 · venció el 18/11 · $ 300,00 por día de atraso» y, si
  tiene una solicitud pendiente (d), « · Tiene una queja pendiente (SR-0013)». Invernadero dado de baja: la API no crea la alerta; el aviso y
  el correo salen igual (D-94, punto 6).
- **El enlace** (`registrar_enlace_de_alerta`, `docs/api/alertas.md`, sección 8): solo para el Gerente (es su único destinatario): «Registrar
  cobro» con la entrega ya elegida (`/comercial/cobranza/registrar/?entrega=<id>`, 1a), con el detalle «En mora desde el 19/11 · 4 días ·
  $ 1.200,00 por atraso» calculado al mostrarlo (regla 3). Si la entrega ya está pagada (1a1), la pantalla lo informa con el cobro, su
  fecha y quién lo registró, y termina.
- **El aviso al Vendedor** (b): «OT-0231 en mora», «Pérez SA no pagó OT-0231 (SUM-0013): $ 46.000,00, venció el 18/11. Desde hoy suma
  $ 300,00 por día de atraso.» (con « Tiene una queja pendiente.» si corresponde). Sin enlace (D-42).
- **El aviso de mora al cliente** (c, d; tipo `aviso_mora` de `comprobantes.py`): la entrega y su fecha, el contrato, el monto a cobrar, la
  fecha de vencimiento, la indemnización por día de atraso y, si tiene una solicitud pendiente, que la está revisando la empresa y que, si se
  acepta, el monto puede bajar (regla 5). Resultado en `Entrega.estado_aviso_mora`. Sin correo: `sin_correo`, no se intenta (regla 4).
- **Quién la llama:**

  | Quién | Con `avisar_vendedor` | Qué provoca |
  |---|---|---|
  | `vencer_pagos` (paso 30) | `True` | La alerta, el aviso y el correo de una entrega que entra en mora |
  | `registrar_cobro` (COM-08a) | `False` | Resuelve la alerta |
  | `anular_cobro` (COM-08b) | `False` (su aviso al Vendedor ya nombra las entregas en mora) | Asegura una alerta nueva si la entrega está en mora; el correo solo si nunca había salido |
  | `resolver_solicitud` (COM-07a, completado por COM-08a) | `False` | Resuelve la alerta si la aceptación dejó la entrega saldada (MD-125) |
  | `anular_resolucion` (COM-07a, completado por COM-08a) | `False` | Asegura la alerta si la entrega deja de estar saldada y ya está en mora |

### Paso diario 30 (COM-VNC-PAG; D-94, punto 7)

`vencer_pagos(hoy) -> ResumenDePaso`, registrado en `comercial/apps.py` con `registrar_paso_diario("vencer_pagos", "Vencer pagos de suministro",
30, vencer_pagos)`. Cada entrega en su transacción; si una falla, `logger.exception` y sigue (D-56, punto 4).

1. **Entregas que entran en mora** (reglas 1 y 6): de suministro, concretadas, sin línea de pago vigente, con monto a cobrar > 0,
   `fecha_vencimiento_pago < hoy` y `fecha_aviso_mora` nula. Por cada una: el invernadero de origen (`bloquear_invernadero_para_alertas`) →
   la entrega; la relectura (sigue sin pagar, con monto > 0 y con `fecha_aviso_mora` nula; si no, nada); `reevaluar_mora(entrega, hoy,
   avisar_vendedor=True)`; la auditoría `vencimiento_pago` **sin usuario** (origen InfoPonia, e), con la entrega y la alerta.
2. **Correos de mora pendientes** (regla 4): las entregas todavía en mora con `estado_aviso_mora = pendiente_envio`: se reintenta el aviso
   (fuera de transacción; el resultado vuelve a `estado_aviso_mora`).

Regla 2 y 3 (no se repite): la parte 1 solo toma entregas con `fecha_aviso_mora` nula, y la alerta es de estado (una activa por clave).
Resumen: `ResumenDePaso(procesados=entregas revisadas, creados=alertas creadas, resueltos=0, detalle="N correos de mora pendientes")`.

### Anular un cobro (COM-ANL-CBR; COM-08b; D-94, puntos 5, 10 y 11)

- **Quién y desde dónde:** el Gerente, desde «Cobros registrados» o la ficha del cobro («Anular», ventana `MODALS.anlcbr`; sin JavaScript,
  una página). Un cobro de compra-venta (1a): no tiene «Anular»; por URL, `cobro_de_compra_venta` («Este cobro es de una compra-venta: va
  dentro del asiento de la entrega y se corrige con un asiento manual.»).
- **Paso 2:** el cobro (código, fecha, medio, monto, la indemnización por atraso total y cada entrega con lo cobrado); qué va a pasar: cada
  entrega «vuelve a pendiente» o «vuelve a en mora» (con `estado_de_pago` sin esa línea), las alertas que se van a asegurar y el
  contraasiento como «Fuera de esta ronda · contabilidad» (`fueraRonda`).
- **Paso 3:** `motivo` obligatorio (`motivo_obligatorio`, 3a), de 1 a 500 caracteres, sin espacios al borde (`motivo_largo`);
  `cliente_pago_en_fecha` (casilla, por omisión desmarcada: «El cliente pagó en esa fecha (se corrige un error de carga)»).
- **Paso 5, la transacción** (`bloqueos.md`, «Cobranza»): las cuentas (el Gerente y los Vendedores) → los invernaderos de origen de las
  entregas del cobro → las entregas → el **pago** y sus líneas. La relectura: el pago sigue vigente (5a: `cobro_ya_anulado`, termina) y la
  huella coincide (`cambio_simultaneo`). Con todo verificado:
  1. la `Anulacion`: `fecha_anulacion = hoy`, `motivo_anulacion`, `usuario`, `pago_cliente`, `cliente_pago_en_fecha` (b);
  2. el pago a `anulado` y sus líneas a `vigente = False` (a; las líneas no se borran: MD-136);
  3. por cada entrega, `reevaluar_mora(entrega, hoy, avisar_vendedor=False)` (d, e);
  4. el aviso a cada Vendedor activo de los contratos (paso 6): «COB-0032 anulado», «El Gerente anuló el cobro de Pérez SA ($ 47.200,00).
     Vuelven a estar sin pagar: OT-0231 (en mora) y OT-0240 (pendiente). Motivo: …»;
  5. la auditoría `anulacion_cobro` (f): afectados el pago (principal), la anulación, las líneas y las alertas creadas; en `datos`, el motivo,
     `cliente_pago_en_fecha` y cada entrega con su estado nuevo.
- **No escribe al cliente** (el caso de uso no lo pide; e: «el correo al cliente no se repite»). No crea el contraasiento (D-57).
- **Paso 7:** «COB-0032 anulado.» con el botón «Registrar el cobro correcto» (COM-REG-CBR con `?anulacion=<id>`: el cliente y las entregas
  del cobro anulado ya elegidas). **7a** (D-94, punto 10): si `cliente_pago_en_fecha`, la pantalla muestra la casilla marcada «Usar la fecha
  del cobro anulado (dd/mm): el cliente pagó ese día» y calcula la indemnización a esa fecha. Con la casilla, solo se pueden elegir entregas
  del cobro anulado y `registrar_cobro` carga `anulacion_corregida` (una vez por anulación: `anulacion_ya_usada`). Sin la casilla, o sin
  `cliente_pago_en_fecha`, es un cobro común con la fecha de hoy.
- **Lo que libera:** una entrega cuyo cobro se anuló vuelve a ser cobrable; la extensión 2b de COM-ANL-SRV deja de bloquear la anulación de
  sus solicitudes (`solicitudes.md`) y la regla 5 de COM-ATN-ENR deja de rechazar (`confirmacion.md`).
- **Una indemnización reintegrada después del cobro** (6a de COM-EVL-DSC o COM-RSV-QJA): no cambia nada al anular el cobro. El monto a cobrar
  de la entrega sigue siendo el que se cobró (lo reintegrado se pagó en dinero y no se descontó), así que el cliente vuelve a deberlo entero.

### Lo que completa a otras tareas

| Tarea | Qué | Parte |
|---|---|---|
| COM-06a | `estado_de_pago` con «pagada» (arriba); el pago de compra-venta de `concretar_entrega` carga `tipo_pago = compra_venta` y `usuario` | 08a |
| COM-07a | Las extensiones 6a de COM-EVL-DSC y COM-RSV-QJA y el cobro como cambio de la huella (8b), y 2b de COM-ANL-SRV, **con datos reales**: las pruebas que usaban `mock.patch` de `estado_de_pago` se reemplazan por otras con un cobro registrado (anotalas en el PR). `resolver_solicitud` y `anular_resolucion` llaman a `reevaluar_mora` (MD-125). La ficha de la solicitud muestra el cobro de la entrega | 08a |
| COM-06b | COM-ATN-ENR, regla 1 (el cobro: código, fecha, medio y monto, o «Sin cobro registrado») y regla 5 (`entrega_cobrada` con una línea de pago vigente) con datos reales | 08a |
| COM-03a | La ficha del suministro, regla 7 de COM-CNS-SUM: el estado de pago de cada entrega con «pagada» (y el código del cobro, o «saldada») y «en mora» con los días; **«Registrar cobro»** si hay entregas cobrables y el actor es su Vendedor o el Gerente (lleva a la pantalla con el cliente elegido). Regla 10 de COM-CNS-SUM | 08a |
| COM-01 | La ficha del cliente: la tarjeta de entregas sin cobrar suma el estado de pago (pendiente o en mora, con los días) y «Registrar cobro»; la baja del cliente ya informa las entregas sin cobrar (COM-06a) y suma cuántas en mora («Completan el ABM de cliente», punto 4) | 08a |
| COM-05a1 | La parte 4 del paso 50 («Correos pendientes») suma los pagos con `estado_aviso_cliente = pendiente_envio` | 08a |
| COM-05a2 | El grupo «Cobranza» de la sección «Comercial» del panel (abajo, «Pantallas») | 08a |
| COM-05b | La extensión 6a de COM-CNL-CVT (`compra_venta.md`) | 08b |

## Pantallas

Referencia visual (D-61): `docs/prototipos/comercial/` (`README.md`). Vale la **última** definición de cada función.

| Pantalla | Funciones del prototipo | Qué tiene | Parte |
|---|---|---|---|
| Comercial · pestaña «Cobranza» (`/comercial/cobranza/`) | `tabCobranza` (línea 951), `cobGroups` (línea 1543), `ACT.cobtog`, `comTabs` | Dos subpestañas: «Por cobrar» (los grupos por cliente) y «Cobros registrados» (lista: cobro con su fecha, cliente, entregas, medio, monto con «incluye $ … por atraso», estado «Vigente» o «Anulado»). Contador rojo de la pestaña: las entregas en mora | 08a («Anular», 08b) |
| Registrar cobro de suministro (`/comercial/cobranza/registrar/`) | `INIT.cobro` y `VIEWS.cobro` (líneas 1787 y 1788, las finales), `atrasoDe` (línea 1184), `ACT['cobro-ok']`, `cliPick` | En tres secciones: «Cliente» (el buscador de clientes de COM-02, limitado a los que tienen deuda; o el cliente fijo), «Entregas que paga» (filtros, la tabla con casillas, la advertencia de 3a), «Pago» (el medio); el resumen a la derecha; «Revisar y registrar» → resumen → «Confirmar cobro» | 08a (la fecha de 7a, 08b) |
| Ficha del cobro (`/comercial/cobranza/cobros/<id>/`) | (no está en el prototipo) | El cobro, sus entregas con lo cobrado y el atraso, el estado del comprobante con «Reenviar» o «Imprimir» y, si está anulado, la anulación (fecha, Gerente, motivo, si el cliente pagó) y el cobro que la corrigió | 08a (la anulación, 08b) |
| Anular cobro (ventana) | `MODALS.anlcbr` (línea 1198), `ACT['anlcbr-ok']` (línea 1199) | Paso 2, el motivo, la casilla y «Anular cobro»; la pantalla final con «Registrar el cobro correcto» | 08b |
| Panel de control del Gerente y del Vendedor · grupo «Cobranza» | `secComercial` (línea 1548) | Tres indicadores: «Por cobrar» (total y cantidad de entregas de suministro), «En mora» (total y cantidad; en rojo si hay) y «Sin confirmar por el cliente» («no afecta el cobro»), que llevan a la pestaña | 08a |

- **Panel de control (comparado con lo que va a estar implementado, plan de la ronda, sección 5):** el grupo «Cobranza» va dentro de la
  sección «Comercial» que registró COM-05a2 (grupo «Entregas») y amplió COM-07a (grupo «Solicitudes», solo el Gerente), **después** de ellos;
  COM-08a suma sus indicadores en la **misma** sección (no registra otra). «Resultados del mes en curso» (Vendedor) es de COM-08c y va
  **entre** «Entregas» y «Cobranza» (prototipo: `${isG()?'':secMes()}` antes del grupo «Cobranza»).
- **Campana:** la alerta «pago en mora» sale sola (`items_de_campana`); COM-08a registra su enlace.
- **Menú:** sin cambios (la pestaña es de «Comercial»).
- **Pasos bloqueados** (criterio de la ronda): «Entregas que paga» aparece después de elegir el cliente; «Pago», después de elegir al menos
  una entrega; «Revisar y registrar» queda deshabilitado mientras falte el medio. Sin JavaScript, el resumen es una página
  (`/comercial/cobranza/registrar/revisar/`).
- **HTMX** (`.claude/rules/interfaz.md`, «Validaciones e interacción HTMX», desde INV-02): marcar o desmarcar una entrega y cambiar los
  filtros son selectores: redibujan el panel del total y la tabla **sin validar** (`hx-swap="innerHTML show:none"`, con
  `data-sin-envio-en-curso`); las validaciones (5a, el medio) y el resumen corren recién con «Revisar y registrar». Sin JavaScript, «Calcular
  total» vuelve a dibujar la página con el total.
- **Textos explicativos** (criterio «textos explicativos siempre»):
  - arriba de «Por cobrar»: «Las entregas de suministro se cobran después de entregarlas, dentro del plazo pactado. Una entrega en mora suma
    cada día la indemnización por atraso del contrato.»; en los grupos: «Por cliente. Dentro de cada uno, las entregas van de la que vence
    primero a la última.» (prototipo);
  - bajo «Entregas que paga»: «Cada entrega se paga completa. Si el cliente paga menos que el total, elegí solo las que su pago cubre.»;
  - bajo la indemnización por atraso del resumen: «Días de atraso × lo pactado por día. Se calcula sola y no se puede cambiar ni perdonar.»;
  - bajo «Medio de pago»: «Uno por cobro. El efectivo va a Caja; los demás, a Banco.» (prototipo);
  - bajo «Fecha del pago»: «Es la fecha de hoy: no se registran cobros con fecha anterior.» o, en 7a, «Es la fecha del cobro anulado: el
    cliente pagó ese día.» (prototipo);
  - en la ventana de anulación: «El cobro queda anulado con su historia y sus entregas vuelven a estar sin pagar. Después podés registrar el
    cobro correcto.».
- URLs (espacio `comercial`): `cobranza/`, `cobranza/registrar/`, `cobranza/registrar/revisar/`, `cobranza/cobros/<id>/`,
  `cobranza/cobros/<id>/comprobante/` (imprimible), `cobranza/cobros/<id>/reenviar-comprobante/` (08a); `cobranza/cobros/<id>/anular/`
  (08b). Vistas que solo orquestan, `never_cache`, con `rol_requerido("gerente", "vendedor")` (y `rol_requerido("gerente")` para anular).

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Registrar cobro | `ACT['cobro-ok']` registra directo, sin resumen ni relectura | Pasos 8 y 9 (resumen y confirmación) y 10a, 10b |
| Registrar cobro | La fecha es un campo que se valida contra hoy (`fv('fc') > HOY`) | Regla «Fecha del pago»: no se elige; hoy o, en 7a, la del cobro anulado (D-94, punto 10) |
| Registrar cobro | Muestra «Total … − … de indemnizaciones» como descuento | Paso 4: lo **descontado** (`monto_descontado`), no la indemnización entera (D-69, punto 9) |
| Registrar cobro | Sin resumen, el texto final dice «Se envió el comprobante» siempre | 11a: el estado real del correo, con «Reenviar» o «Imprimir» |
| Por cobrar | La primera definición de `tabCobranza` incluye entregas con monto a cobrar 0 | Regla «Entrega cobrable»: las saldadas no se ofrecen (la versión final de `VIEWS.cobro` ya filtra `aCobrar(e) > 0`) |
| Anular cobro | `ACT['anlcbr-ok']` no relee ni bloquea; la ventana no muestra el estado en que queda cada entrega | Pasos 2 y 5, 5a |
| Anular cobro | Al anular, borra la alerta solo en el cobro (`DB.alertas.filter`) y no la vuelve a crear | Postcondición e: se asegura una alerta nueva para cada entrega en mora (D-94, punto 5) |
| Cobros registrados | Sin ficha del cobro | La ficha (estado del comprobante, la anulación y el cobro que la corrigió) |

## Pruebas

- `test_modelos_cobranza.py` (08a; COM-08b suma lo suyo): una por restricción de la base (`LineaPago`, `PagoCliente`, `Entrega`; en 08b,
  `Anulacion`). `test_cobranza_calculos.py` (08a): las tres funciones de «Cálculos», de tabla (el día del vencimiento, un día, el ejemplo de
  la regla, montos con centavos).
- `test_estado_de_pago.py` (08a): las cuatro filas de la tabla de «Estado de pago»; el día del vencimiento (pendiente) y el siguiente (en
  mora); una entrega con un pago anulado y uno vigente; una de compra-venta (sin clave); sin consultas por entrega (`assertNumQueries` igual
  con una y con cinco).
- `test_com_reg_cbr.py` (`ComRegCbrServicioTests`, 08a): una por regla (quién cobra, con el Vendedor de otro contrato y con un Vendedor
  inactivo; entrega cobrable, con contrato finalizado y resuelto y con cliente inactivo; un cliente por cobro; sin pagos parciales; monto a
  cobrar, con descuento y saldada; vencimiento; indemnización por atraso, con el ejemplo de la regla y con una cláusula cambiada después del
  cobro; fecha del pago; medio; indemnización aceptada después del cobro —se reintegra, con un cobro real—; el atraso no es un
  incumplimiento; alerta; avisos), por postcondición (a, b, c, e, f, g; d sin asiento) y por extensión (1a, 1a1, 3a, 5a, 8a en la vista,
  10a, 10b por monto y por fecha, 11a); el `on_commit` del comprobante (`captureOnCommitCallbacks`); el reintento de la parte 4 del paso 50;
  `verificar_invariantes_de_cobros()` después de cada una.
- `test_com_vnc_pag.py` (`ComVncPagServicioTests`, 08a): una por regla (1 a 10; la 7 y la 8, como no-hace) y postcondición (a a e); dos
  ejecuciones el mismo día y al día siguiente (nada se repite); una entrega pagada, una saldada, una de compra-venta y una con vencimiento hoy
  (no entran); un contrato resuelto (entra); el invernadero dado de baja (sin alerta, con aviso y correo); el cliente sin correo; el
  reintento del correo; el paso 30 en `pasos_diarios()` entre el 27 y el 33.
- `test_reevaluar_mora.py` (08a): cada fila de «Quién la llama» con su efecto; una aceptación que salda la entrega (resuelve) y su anulación
  con la entrega ya vencida (asegura otra, sin correo ni aviso).
- `test_com_anl_cbr.py` (`ComAnlCbrServicioTests`, 08b): una por regla y postcondición (a, b, d, e, f; c sin contraasiento) y extensión (1a,
  3a, 5a, 7a con y sin `cliente_pago_en_fecha`, con la casilla desmarcada, con una entrega que no era del cobro y con la anulación ya usada);
  una entrega que nunca había estado en mora y queda en mora al anular (la alerta y el **primer** correo); una que ya estuvo (la alerta, sin
  correo); después de anular, 2b de COM-ANL-SRV y la regla 5 de COM-ATN-ENR dejan de rechazar; `verificar_invariantes_de_cobros()`.
- Concurrencia (`@tag("concurrencia")`): `test_cobranza_concurrencia.py` (08a): dos cobros de la misma entrega (uno gana; el otro,
  `entrega_ya_pagada`); un cobro contra la aceptación de una solicitud de la misma entrega (el segundo ve la huella cambiada: `cobro_cambio` o
  `solicitud_cambio`); un cobro contra el paso 30 sobre la misma entrega. `test_anulacion_cobro_concurrencia.py` (08b): dos anulaciones del
  mismo cobro; anular contra registrar el cobro correcto de la misma anulación; anular contra el paso 30.
- `test_cobranza_vistas.py` (08a; COM-08b suma lo suyo): permisos (el Vendedor solo sus contratos; los demás roles, 403; ningún botón lleva a
  un 403; «Anular» solo para el Gerente); el flujo completo con HTMX y sin JavaScript; `revisar/` no escribe nada; el enlace de la alerta
  (prueba mínima del registrante, `docs/api/alertas.md`, sección 8).
- Invariantes (`verificar_invariantes_de_cobros()`, en `comercial/tests/invariantes.py`): cada pago de suministro tiene al menos una línea y uno
  de compra-venta ninguna; `monto_pagado` = Σ (`monto_cobrado` + `indemnizacion_atraso`) de sus líneas; `vigente` de cada línea = el pago
  está vigente; todas las entregas de un pago son de suministro, concretadas y del cliente del pago; a lo sumo una línea vigente por entrega
  (también lo garantiza la base); una entrega con línea vigente tiene `monto_cobrado = monto_a_cobrar`; una entrega en mora sin pagar con
  `fecha_aviso_mora` no nula tiene su alerta activa si su invernadero está activo; un pago anulado tiene exactamente una `Anulacion` (08b).

## Para más adelante

- **COM-08c:** las estadísticas (`estadisticas.md`) leen `estado_de_pago`, `LineaPago` y las solicitudes; «Resultados del mes en curso».
- **Ronda de contabilidad** (D-57): el asiento del cobro (postcondición d de COM-REG-CBR) y el contraasiento de su `Anulacion` (c de
  COM-ANL-CBR), con lo que guardan `PagoCliente` y `LineaPago`.
- Temas abiertos de COM-REG-CBR: el pago mixto; el pago anterior a su registro (fuera del camino de 7a); la condonación del atraso; el pago a
  cuenta.

## Solo prototipo

- Los datos de ejemplo (`DB.cobros`, `DB.ent`), el cambio de rol y la fecha fija (`HOY`).
- El asiento que muestra el resumen del cobro y el contraasiento de la anulación: «Fuera de esta ronda · contabilidad» (D-57).
- El toast «Se envió el comprobante» sin mirar el resultado del correo.
