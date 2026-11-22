# Casos de uso · produccion · Cancelar orden

Copia para el repo del caso PROD-CNL-ORD (versión 0.1) del documento de Drive «CU extendidos», consultado el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026.

Es un caso de uso extendido. **El código de siembras y transiciones va en la app `produccion`**; archivo de pruebas: `produccion/tests/test_prod_cnl_ord.py`.
**Las cosechas (desde la ronda «Comercial 1», COM-04) van en `comercial`** (D-59, A3: cancelar una cosecha libera su reserva); archivo de pruebas: `comercial/tests/test_prod_cnl_ord_cosechas.py`. Ver la sección «Cómo se aplica en la ronda «Comercial 1»» al final. **Las entregas** (la «Cancelación de una entrega», sin pantalla) **van en `comercial`** desde COM-05a (D-66, punto 9); archivo de pruebas: `comercial/tests/test_prod_cnl_ord_entregas.py`. Ver «Cómo se aplica en la ronda «Comercial 1»: entregas y envasado» al final.
**Los mantenimientos técnicos (ronda «IoT 1», IOT-07) van en `iot`**, solo la orden automática y solo desde la ficha del equipo (D-73, D-79); archivo de pruebas: `iot/tests/test_cancelar_mantenimiento.py`. Ver «Cómo se aplica en la ronda «IoT 1»» al final.
El texto está **completo**, con las ramas de cosecha, contrato y mantenimiento: en la ronda solo existen siembras y transiciones, y la sección «Cómo se aplica en la ronda» dice qué parte se hace y cuál queda **«Fuera de la ronda (D-45)»**.
Se quitaron los `**` sueltos del export de Drive. No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-CNL-ORD | Cancelar Orden | Agrónomo (o InfoPonia cuando lo incluye otro caso) | `produccion/tests/test_prod_cnl_ord.py`; cosechas: `comercial/tests/test_prod_cnl_ord_cosechas.py` |

---

## PROD-CNL-ORD · Cancelar Orden

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Órdenes.
Actor principal: Agrónomo. Cuando lo incluye otro caso de uso, actúa por cuenta del actor de ese caso de uso (un
   usuario o InfoPonia).
Versión: 0.1

Personal involucrado e intereses
- Agrónomo: quiere dejar sin efecto una orden que ya no corresponde (por un cambio de planes, un problema en el lote o
   en el equipo, o un error de planificación) y que en el mismo acto se libere todo lo que la orden tenía apartado:
   insumos, agujeros de los sectores y stock de los lotes. Antes de confirmar, quiere saber qué consecuencias tiene la
   cancelación sobre los contratos.
- Capataz: quiere que la orden salga de su bandeja y enterarse enseguida, para no trabajar sobre una orden cancelada.
- Técnico: quiere lo mismo con los mantenimientos que tenía asignados.
- Vendedor: quiere que un contrato cuya cosecha se cancela vuelva a quedar cubierto sin intervenir él, y enterarse de
   lo que no se pudo cubrir.
- Cliente: quiere recibir lo que compró en la fecha pactada o, si ya no es posible, decidir él si acepta una cantidad
   menor.
- Transportista: quiere enterarse en el momento si se canceló una entrega suya, sobre todo si ya la lleva en el
   vehículo.
- Gerente: quiere saber quién canceló cada orden, cuándo y por qué, y que ninguna cancelación genere movimientos
   contables sin respaldo.
- Organización (Jardín Botánico): quiere que los insumos, los agujeros y el stock que liberó una orden cancelada
   vuelvan a estar disponibles enseguida, y que ningún contrato quede descubierto sin que nadie lo sepa.

Relaciones con otros casos de uso
- «include» PROD-ASG-STK · Asignar Stock Maduro: se incluye en la extensión 8c, al cancelar una cosecha que cubre un
   contrato, para volver a cubrir la cantidad de la reserva liberada.
- Es incluido por:
- PROD-PNR-FDS · Poner Sector Fuera de Servicio (paso 14), una vez por cada orden de siembra o de transición con
   agujeros comprometidos en el sector;
- previstos: Cancelar Compra-venta (caso por especificar 5), COM-RSV-SUM · Resolver Suministro por Incumplimientos
   (caso por especificar 8) y Modificar Suministro (CU-38), para cancelar las cosechas y las entregas de un contrato.
   Ver «Ejecución desde los casos de uso que lo incluyen».
- Dispara:
- PROD-ASG-CAM · Asignar Stock de Cámara, si al liberar la reserva de una cosecha queda libre stock de líneas de
   cámara (disparador 2 de PROD-ASG-CAM);
- COM-PNF-ENT · Planificar Entrega, si con las reservas creadas por PROD-ASG-STK quedan listas para entrega todas las
   reservas de una venta o de un período de suministro;
- COM-DCD-FLT · Decidir Faltante, que queda habilitado cuando un detalle de venta pasa a «pendiente de decisión del
   cliente» (extensión 8c).
- Lo siguen: PROD-PNF-SMB, PROD-PNF-TRN, PROD-PNF-CSC y Planificar Mantenimiento técnico (CU-05), para volver a
   planificar lo cancelado si hace falta.
- Relacionados, sin inclusión:
- PROD-CNC-SMB, PROD-CNC-TRN, PROD-CNC-CSC, Concretar Mantenimiento técnico (CU-06) y COM-CNC-ENT verifican al
   registrar que la orden siga «a realizar»; si este caso de uso la canceló antes, no la concretan (por ejemplo,
   extensión 13b de PROD-CNC-CSC);
- COM-DCD-FLT · Decidir Faltante cancela por sí mismo las cosechas de un detalle rechazado, con el mismo efecto que
   este caso de uso, en su propia operación;
- Validar o Modificar Cosecha Automática (caso por especificar 3) es la alternativa cuando solo hay que cambiar los
   lotes, la fecha o la prioridad de una cosecha automática, sin cancelarla.

Puntos de extensión
- Ninguno: no es extendido por otros casos de uso.

Precondiciones
a. El Agrónomo está autenticado en el Sistema.
b. El Agrónomo tiene a su cargo al menos un invernadero en estado «activo».

Garantías mínimas
- La operación es atómica, incluido PROD-ASG-STK. Si el caso de uso se cancela o falla:
- la orden sigue «a realizar», con su fecha programada, su prioridad y su responsable;
- sus reservas de insumo siguen «activa» y su reserva de stock conserva su estado y sus líneas;
- no se crea ninguna reserva ni orden de cosecha, y no cambia el estado de ningún detalle de contrato ni de ninguna
   venta;
- no se envía ningún correo ni notificación, ni queda ningún log de auditoría parcial.
- La única excepción es la alerta al Gerente por invernadero sin Capataz activo que puede generar PROD-ASG-STK, que
   permanece registrada (extensión 5a de PROD-ASG-STK).
- Solo se cancelan órdenes «a realizar». Una orden concretada o cancelada nunca cambia de estado, aun cuando se
   cancela y se concreta al mismo tiempo.
- La cancelación no genera asientos contables, consumos de insumo ni movimientos de stock, y no modifica la cantidad
   actual de ningún lote ni la cantidad disponible de ninguna partida.
- No se borra nada: las reservas, las líneas de reserva y las ocupaciones de sector de la orden se conservan como
   historial.
- Ningún detalle de contrato queda con cantidad sin cubrir por la cancelación sin que se intente volver a cubrirla y
   sin que se avise al Vendedor.
- El Agrónomo solo cancela órdenes de los invernaderos a su cargo, y nunca una entrega.

Garantías de éxito (Postcondiciones)
Para toda orden cancelada:
a. La orden pasó del estado «a realizar» a «cancelada», con la fecha actual como fecha de resolución y con el motivo
   de cancelación indicado.
b. Cada reserva de insumo «activa» de la orden pasó a «cancelada», sin cantidad utilizada ni devuelta, y su cantidad
   reservada dejó de restar del stock libre del insumo del invernadero.
c. Si el insumo de una de esas reservas tenía activa la alerta «stock inconsistente» y con la cancelación su stock
   volvió a cubrir las reservas activas, la alerta pasó a «resuelta», con su fecha de resolución.
Si la orden es una siembra o una transición:
d. Sus ocupaciones de sector se conservan, sin lote y con cero agujeros ocupados, y sus agujeros planificados dejaron
   de contar como agujeros comprometidos en cada sector.
e. Si es una transición, el lote conserva su etapa y su fecha de entrada a la etapa, y quedó sin transición «a
   realizar», de modo que puede planificarse otra.
Si la orden es una cosecha:
f. Su reserva de stock pasó a «liberada». Sus líneas de lote quedaron sin cantidad cosechada, y el stock que apartaban
   sus líneas de lote y de cámara volvió a estar libre en los lotes y en las partidas.
g. Si la cosecha cubría un contrato, se ejecutó PROD-ASG-STK para el mismo detalle por la cantidad cubierta por la
   reserva liberada, sin considerar los lotes de la cosecha cancelada. Lo que no se pudo volver a cubrir siguió el
   camino de faltante:
- en una compra-venta, el detalle y la venta quedaron en estado «pendiente de decisión del cliente», con la fecha
   actual como fecha en que el detalle pasó a pendiente, y se envió al cliente un correo con un enlace de acceso
   temporal para que decida (si el cliente no tiene correo, se avisó al Vendedor para que registre la decisión);
- en un suministro, el período quedó con cantidad sin cubrir y su entrega saldrá con lo disponible.
h. Si quedó stock libre en partidas de cámara que la reserva liberada apartaba, se disparó PROD-ASG-CAM · Asignar
   Stock de Cámara.
i. Si con las reservas creadas por PROD-ASG-STK quedaron listas para entrega todas las reservas de una venta o de un
   período de suministro, se disparó COM-PNF-ENT · Planificar Entrega.
Si la orden es un mantenimiento técnico:
j. El hardware del mantenimiento conservó su estado y sus datos.
Avisos y auditoría:
k. Se notificó la cancelación, con el motivo, al Capataz del invernadero (siembra, transición o cosecha) o al Técnico
   asignado (mantenimiento), si está activo.
l. Si la cosecha cubría un contrato, se notificó al Vendedor del contrato la cosecha cancelada, lo que se volvió a
   cubrir y lo que quedó sin cubrir.
m. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la orden y el cambio de su estado, su
   fecha de resolución y su motivo de cancelación.
n. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de valor de cada reserva de
   insumo, reserva de stock, detalle de contrato, venta y alerta modificados. Las reservas y cosechas que crea PROD-
   ASG-STK tienen sus propios logs (postcondición i de PROD-ASG-STK).

Escenario principal de éxito (o Flujo Básico)
(Orden de siembra «a realizar», con una reserva de insumo para la semilla y otra para un nutriente, y agujeros
   comprometidos en dos sectores de germinación.)
1.  El Agrónomo inicia la cancelación de una orden.
2.  El Sistema presenta las órdenes «a realizar» de los invernaderos a su cargo (siembras, transiciones, cosechas y
   mantenimientos), agrupadas por invernadero y por tipo, y ordenadas por fecha programada y prioridad. Para cada una
   indica:
1.  el tipo, la fecha programada, la prioridad y si está demorada;
2.  quién la planificó (un Agrónomo o InfoPonia) y el Capataz o el Técnico asignado;
3.  la variedad o el lote y, si es una cosecha, si cubre un contrato.
3.  El Agrónomo selecciona una orden.
4.  El Sistema presenta el detalle de la orden y lo que libera su cancelación:
1.  las reservas de insumo activas, con el insumo y la cantidad reservada de cada una;
2.  los sectores de germinación con los agujeros comprometidos que se liberan en cada uno.
5.  El Agrónomo indica el motivo de la cancelación.
6.  El Sistema verifica que el motivo esté indicado y presenta el resumen: la orden, el motivo, las reservas de
   insumo que se cancelan y los agujeros que se liberan.
7.  El Agrónomo confirma la cancelación.
8.  El Sistema verifica que la orden siga «a realizar» y que sus reservas no hayan cambiado. Luego, en una única
   transacción:
1.  pasa la orden a «cancelada», con la fecha actual como fecha de resolución y el motivo indicado;
2.  pasa a «cancelada» cada reserva de insumo activa de la orden;
3.  resuelve las alertas «stock inconsistente» que quedaron cubiertas;
4.  registra la auditoría correspondiente.
9.  El Sistema notifica la cancelación al Capataz del invernadero.
10. El Sistema informa al Agrónomo que la orden quedó cancelada, lo que se liberó y que puede volver a planificar la
   siembra con PROD-PNF-SMB.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 7, el Agrónomo cancela la operación:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio. La orden sigue «a realizar».
*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo si la orden quedó cancelada o no.
3.  Si no quedó cancelada, el Agrónomo reinicia el caso de uso desde el paso 1.
2a. No hay órdenes «a realizar» en los invernaderos a cargo del Agrónomo:
1.  El Sistema informa que no hay órdenes para cancelar.
2.  El caso de uso termina.
4a. La orden es una transición:
1.  El Sistema presenta el lote, su etapa actual y la etapa de destino, y los sectores de destino con los agujeros
   comprometidos que se liberan en cada uno. Informa que la transición no tiene reservas de insumo.
2.  El caso de uso continúa en el paso 5.
4b. La orden es una cosecha sin contrato:
1.  El Sistema presenta su reserva de stock, con los lotes y la cantidad reservada de cada uno, e informa que ese
   stock vuelve a estar libre en los lotes.
2.  El caso de uso continúa en el paso 5.
4c. La orden es una cosecha que cubre un contrato:
1.  El Sistema presenta su reserva de stock, con los lotes y las partidas y la cantidad reservada de cada uno, y el
   contrato que cubre: el tipo (compra-venta o suministro), el cliente, la variedad, la fecha de entrega y la cantidad
   cubierta por la reserva.
2.  Si la cosecha la planificó InfoPonia, el Sistema recuerda que, si solo quiere cambiar los lotes, la fecha o la
   prioridad, puede hacerlo con Validar o Modificar Cosecha Automática, sin cancelarla.
3.  El caso de uso continúa en el paso 5. En el paso 6 se aplica la extensión 6b.
4d. La orden es un mantenimiento técnico:
1.  El Sistema presenta el hardware del mantenimiento, el tipo de mantenimiento, el Técnico asignado y los repuestos
   reservados con su cantidad.
2.  El caso de uso continúa en el paso 5.
6a. El motivo no está indicado:
1.  El Sistema señala que el motivo es obligatorio.
2.  El Agrónomo indica el motivo (vuelve al paso 5).
6b. La orden es una cosecha que cubre un contrato:
1.  El Sistema estima, con el stock maduro libre vigente y sin los lotes de la cosecha, cuánto de la cantidad cubierta
   por la reserva podrá volver a cubrirse, con los mismos criterios de PROD-ASG-STK.
2.  Si se cubre toda, el resumen informa que el contrato seguirá cubierto e indica de qué partidas o lotes saldría el
   producto y si hará falta una cosecha nueva.
3.  Si no se cubre toda, el resumen informa la cantidad que quedaría sin cubrir y su consecuencia:
1.  en una compra-venta, que el detalle y la venta pasarán a «pendiente de decisión del cliente» y que el cliente
   recibirá un enlace para decidir (o, si no tiene correo, que el Vendedor registrará la decisión);
2.  en un suministro, que la entrega del período saldrá con menos de lo pactado y que puede haber una discrepancia o
   una queja según la cláusula del contrato.
4.  La estimación es informativa: la asignación definitiva se hace en el paso 8 (extensión 8c). El caso de uso
   continúa en el paso 7.
6c. La orden es una cosecha que cubre un detalle de venta, y el detalle o su venta ya están en «pendiente de decisión
   del cliente»:
1.  El resumen informa que no se intentará volver a cubrir la cantidad, porque el detalle espera la decisión del
   cliente, y que esa cantidad se sumará al faltante sobre el que el cliente decide.
2.  El caso de uso continúa en el paso 7. En el paso 8 se aplica la extensión 8d.
8a. Al registrar, la orden ya no está «a realizar» (el Capataz o el Técnico la concretó, u otra operación la canceló):
1.  El Sistema no registra ningún cambio e informa el estado actual de la orden.
2.  El caso de uso termina.
8b. Al registrar, cambiaron las reservas de la orden o el contrato que cubre (por ejemplo, se modificó la cosecha
   automática, el cliente rechazó el detalle o se canceló la venta):
1.  El Sistema no registra ningún cambio e informa qué cambió.
2.  El caso de uso vuelve al paso 4 con los valores vigentes.
8c. La orden es una cosecha:
1.  Dentro de la misma transacción, el Sistema pasa su reserva de stock a «liberada».
2.  Si la cosecha cubre un contrato, el Sistema incluye PROD-ASG-STK · Asignar Stock Maduro para el mismo detalle, por
   la cantidad cubierta por la reserva liberada, con su fecha de entrega y sin considerar los lotes de la cosecha
   cancelada.
3.  Si PROD-ASG-STK cubre toda la cantidad, el Sistema sigue con el resto del paso 8.
4.  Si la cubre solo en parte o no la cubre, PROD-ASG-STK reserva lo disponible, y lo que queda sin cubrir sigue el
   camino de faltante:
1.  si el detalle es de una compra-venta, el Sistema pasa el detalle y la venta a «pendiente de decisión del cliente»,
   carga la fecha actual como fecha en que el detalle pasó a pendiente y, después de confirmar la transacción, envía
   al cliente el correo con el enlace de decisión y notifica el faltante al Vendedor del contrato; si el cliente no
   tiene correo, solo notifica al Vendedor, que registra la decisión (extensión 1a de COM-DCD-FLT);
2.  si el detalle es de un suministro, el período queda con cantidad sin cubrir y la entrega saldrá con lo disponible;
   el Sistema notifica el faltante al Vendedor del contrato.
5.  Después de confirmar la transacción, el Sistema dispara PROD-ASG-CAM si quedó stock libre en partidas de cámara de
   la reserva liberada, y COM-PNF-ENT si quedaron listas para entrega todas las reservas de una venta o de un período.
6.  El caso de uso continúa en el paso 9 y, en el paso 10, informa además lo que se volvió a cubrir y lo que quedó sin
   cubrir.
8d. La cosecha cubre un detalle de venta que ya está, él o su venta, en «pendiente de decisión del cliente» (extensión
   6c):
1.  El Sistema pasa la reserva de stock a «liberada» y no incluye PROD-ASG-STK.
2.  El detalle pasa a «pendiente de decisión del cliente» si no lo estaba, y en todo caso carga la fecha actual como
   fecha en que pasó a pendiente.
3.  Después de confirmar la transacción, el Sistema envía al cliente un nuevo correo con el enlace y las cantidades
   actualizadas, y notifica al Vendedor. Si el cliente no tiene correo, solo notifica al Vendedor.
4.  El caso de uso continúa en el paso 9.
8e. La orden es un mantenimiento técnico:
1.  El Sistema cancela las reservas de repuestos y no modifica el hardware.
2.  El caso de uso continúa en el paso 9, donde la notificación va al Técnico asignado.
9a. El invernadero no tiene un Capataz activo, o el Técnico del mantenimiento no está activo:
1.  El Sistema no envía la notificación. La alerta «invernadero sin {rol} activo» ya existe (regla 3 de 8.22).
2.  El caso de uso continúa en el paso 10.
9b. El Sistema no logra entregar una notificación o un correo:
1.  La cancelación permanece registrada.
2.  El Sistema reintenta el envío.

Ejecución desde los casos de uso que lo incluyen
Cuando otro caso de uso lo incluye, este caso de uso recibe la orden y el motivo, se ejecuta desde el paso 8 dentro de
   la transacción del caso de uso base y no presenta pantallas. El origen de la auditoría es el del caso de uso base
   (un usuario, con su rol, o un proceso automático). No se aplica la extensión 8b, porque el caso de uso base ya
   verificó la orden. Las diferencias de cada caso de uso base son:
Desde PROD-PNR-FDS · Poner Sector Fuera de Servicio (paso 14):
- Se ejecuta una vez por cada orden de siembra o de transición «a realizar» con agujeros comprometidos en el sector.
- El motivo es «Sector fuera de servicio», seguido del nombre del sector y del motivo indicado en ese caso de uso.
- Los agujeros planificados dejan de contar como comprometidos en todos los sectores de la orden, no solo en el que se
   pone fuera de servicio.
- Se omiten los pasos 9 y 10: el aviso al Capataz es la notificación única del paso 15 de PROD-PNR-FDS, y el aviso al
   Agrónomo es su paso 16.
Desde Cancelar Compra-venta, COM-RSV-SUM y Modificar Suministro (previstos):
- Cosechas: el caso de uso base cancela las cosechas «a realizar» de los detalles que dejan de necesitarse. Como esos
   detalles ya no deben cubrirse, no se aplica la parte de la extensión 8c que incluye PROD-ASG-STK ni el camino de
   faltante: la reserva pasa a «liberada» y nada más.
- Entregas: el caso de uso base cancela las entregas «a realizar» del contrato con la «Cancelación de una entrega» que
   sigue.
Cancelación de una entrega (solo desde otro caso de uso):
- Precondición: el caso de uso base ya liberó, o libera en la misma transacción, todas las reservas de stock de la
   entrega, o canceló o resolvió su contrato (regla 13 de 8.12). Este caso de uso no cambia el estado de las reservas
   de stock: qué pasa con el producto (lotes o cámara) lo decide el caso de uso base.
- La entrega pasa a «cancelada», con la fecha actual como fecha de resolución y el motivo que indica el caso de uso
   base. Conserva sus detalles de entrega como historial (R150 en 0..*).
- Sus reservas de insumo (envases) activas pasan a «cancelada», sin registrar consumo. Si el envasado ya estaba
   planificado, el Sistema notifica al Agrónomo del invernadero de origen los envases que estaban reservados, para
   que, si ya se usaron y no pueden reutilizarse, los regularice con CMP-AJT-STK · Ajustar Stock de Insumo.
- Si la entrega tiene Transportista, se le notifica la cancelación. La entrega deja de contar para su capacidad de
   carga y sus límites diarios, que solo cuentan entregas no canceladas.
- Si la entrega está en curso (el vehículo tiene la ruta del día iniciada y la entrega tiene fecha programada igual o
   anterior a la fecha actual), se cancela igual: la notificación al Transportista es inmediata y le indica que no la
   entregue y que devuelva el producto y los envases al invernadero de origen. Si no le quedan entregas «a realizar»
   del día, puede finalizar la ruta.
- El aviso al cliente lo envía el caso de uso base, que conoce el motivo comercial.
- Si al registrar la entrega ya no está «a realizar» (el Transportista o el Vendedor la concretó), se aplica la
   extensión 8a y el caso de uso base decide cómo sigue.

Requisitos especiales
- La presentación de los pasos 2, 4 y 6, incluida la estimación de la extensión 6b, y el registro del paso 8 se
   completan, cada uno, en no más de 2 segundos.
- El paso 8, incluido PROD-ASG-STK, se ejecuta como una única transacción. Cuando lo incluye otro caso de uso, forma
   parte de la transacción de ese caso de uso.
- El control de concurrencia impide cancelar una orden mientras se registra su concreción (PROD-CNC-SMB, PROD-CNC-TRN,
   PROD-CNC-CSC, Concretar Mantenimiento técnico o COM-CNC-ENT), la modificación de una cosecha automática, el
   envasado de una entrega (PROD-PNF-ENV) o el inicio de la ruta de su Transportista (COM-INI-RUT). La operación que
   llega segunda vuelve a verificar sus condiciones con el resultado de la primera.
- El control de concurrencia sobre el stock libre de lotes y partidas es el de PROD-ASG-STK.
- Solo el Agrónomo a cargo del invernadero accede a sus órdenes.
- Las notificaciones y los correos se envían después de confirmar la transacción. Se presentan dentro del Sistema y
   pueden, además, enviarse por correo electrónico.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción e indican el origen de la operación: un usuario o un proceso automático.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Quién lo ejecuta: el Agrónomo a cargo del invernadero de la orden (R051), cualquiera sea quien la planificó, incluso
   InfoPonia (regla 2 de 8.22). (Paso 2)
- Órdenes que cancela el Agrónomo: siembras, transiciones, cosechas y mantenimientos técnicos en estado «a realizar».
   Las entregas no: una entrega se cancela solo cuando se liberan todas sus reservas o se cancela su contrato (regla
   13 de 8.12), y eso lo hacen los casos de uso del contrato, que incluyen este. (Paso 2)
- Estados: una orden pasa de «a realizar» a «cancelada» y no vuelve atrás (regla 14 de 8.12). Una orden cancelada por
   error no se reactiva: se planifica una nueva. (Paso 8)
- Motivo y fecha: el motivo es obligatorio. La fecha de resolución es la fecha actual, sin fechas retroactivas. (Pasos
   6 y 8)
- Reservas de insumo: pasan a «cancelada» con la orden (composición R138). Reservar no descuenta stock, así que no hay
   nada que devolver: la cantidad reservada solo deja de restar del stock libre (regla 8 de 8.4). (Paso 8)
- Agujeros comprometidos: se calculan, no se guardan. Son la suma de los agujeros planificados de las ocupaciones cuya
   orden está «a realizar» (regla 4 de 8.13), así que dejan de contar al cancelarse la orden. Las ocupaciones se
   conservan sin lote (regla 3 de 8.13). (Paso 8)
- Transición cancelada: el lote no cambia de etapa ni de fecha de entrada a la etapa, y puede recibir otra transición,
   porque solo admite una «a realizar» (regla 4 de 8.21). (Extensión 4a)
- Cosecha cancelada: su reserva de stock pasa entera a «liberada», también sus líneas de cámara (regla 13 de 8.8). No
   cambia la cantidad de ningún lote, que solo baja al concretar una cosecha (regla 14 de 8.8). Una cosecha sin
   contrato no requiere nada más. (Extensiones 4b y 8c)
- Recobertura del contrato: la cantidad a volver a cubrir es la cantidad cubierta por la reserva liberada: lo
   reservado en sus líneas de lote, que no se cosecharon, más lo reservado en sus líneas de cámara (regla 9 de 8.8).
   Se cubre con PROD-ASG-STK, que toma primero la cámara y después los lotes (regla 7 de 8.6). (Extensión 8c)
- Lotes excluidos: en esa ejecución de PROD-ASG-STK no se consideran los lotes de la cosecha cancelada. Si el motivo
   de la cancelación es un problema del lote, volver a elegirlo repetiría la cosecha cancelada; si el Agrónomo solo
   quería cambiar lotes o fechas, la herramienta es Validar o Modificar Cosecha Automática. (Extensión 8c)
- Camino de faltante: lo que PROD-ASG-STK no cubre sigue el mismo camino que en la extensión 13a de PROD-CNC-CSC: en
   una compra-venta, el detalle y la venta pasan a «pendiente de decisión del cliente» (regla 16 de 8.6); en un
   suministro, se entrega lo disponible y el faltante se trata con una discrepancia o una queja (regla 17 de 8.6). Si
   el cliente no tiene correo, la decisión la registra el Vendedor (regla 18 de 8.20). (Extensión 8c)
- Detalle que espera la decisión del cliente: no se puede cubrir con PROD-ASG-STK (precondición b de PROD-ASG-STK;
   regla 8 de 8.8). La cantidad liberada se suma a su faltante, el detalle carga la fecha actual como fecha de
   pendiente y el cliente recibe un enlace nuevo con las cantidades actualizadas, cuyo plazo se cuenta desde esa
   fecha. (Extensiones 6c y 8d)
- Sin contabilidad ni bitácora: cancelar una orden no genera asientos (regla 22 de 8.6), consumos ni movimientos de
   stock. Tampoco genera un registro de bitácora: queda en el estado de la orden, en su motivo, en las notificaciones
   y en el log de auditoría, con el mismo criterio que la resolución de un contrato (regla 13 de 8.14). (Paso 8)
- Alerta «stock inconsistente»: es dinámica. Si al cancelar las reservas el stock del insumo vuelve a cubrir sus
   reservas activas, la alerta se resuelve en la misma transacción (regla 6 de 8.13). (Paso 8)
- Mantenimiento cancelado: los repuestos reservados vuelven a estar libres; el hardware no cambia de estado.
   (Extensión 8e)
- Orden de presentación: por fecha programada, de la más antigua a la más reciente, y después por prioridad (alta,
   media, baja). Una siembra o una transición sin prioridad se ordena como media (MD-73). (Paso 2)
- Avisos: al Capataz del invernadero (siembra, transición o cosecha) o al Técnico (mantenimiento), con el motivo; al
   Vendedor, si la cosecha cubría un contrato; al cliente, solo por el camino de faltante. (Pasos 9 y 10, extensión
   8c)

Lista de tecnología y variaciones de datos
- 2. El Agrónomo puede filtrar las órdenes por invernadero, por tipo y por rango de fechas programadas.
- 5. El motivo es texto libre, de hasta 500 caracteres. (En la ronda son 300: ver «Decisiones de aplicación». Con 300 el aviso al Capataz puede llevar el motivo entero dentro de los 500 del detalle de una notificación, D-42.)
- 6b. Las cantidades se expresan en plantas, como números enteros.
- 9. La notificación indica la orden, su tipo, su fecha programada, el motivo y quién la canceló. Se entrega dentro
   del Sistema y puede, además, enviarse por correo electrónico.
- 8c. El correo al cliente incluye el enlace de acceso temporal, las cantidades solicitada y disponible de cada
   detalle afectado y la fecha pactada, igual que en PROD-CNC-CSC.

Frecuencia
Baja: algunas cancelaciones por mes en cada invernadero, más las que se ejecutan incluidas en otros casos de uso
   (sectores fuera de servicio, cancelaciones o resoluciones de contratos). A confirmar con el Jardín Botánico.

Temas abiertos
- Estado del hardware en mantenimiento: si Planificar Mantenimiento técnico (CU-05) cambia el estado del hardware (por
   ejemplo, a «en mantenimiento»), este caso de uso debe devolverlo a su estado anterior. Hoy el modelo no define los
   valores de estadoHardware. Hay que resolverlo al especificar CU-05.
- Alerta que originó un mantenimiento: un mantenimiento puede originarse en una alerta por comando fallido (R048).
   ¿Esa alerta sigue activa al cancelarse el mantenimiento? Hay que resolverlo con CU-05 y CU-06.
- Período de suministro sin reservas: si la cosecha cancelada era la única reserva de un período y PROD-ASG-STK no
   cubre nada, el período queda sin reservas y COM-PNF-ENT nunca planifica su entrega. ¿Debe Planificar Cosecha por
   Contrato volver a intentar cubrirlo en su ejecución diaria? Es el mismo caso que deja PROD-CNC-CSC (extensión 13a).
- Cancelar varias órdenes a la vez: hoy se cancela de a una. Queda como mejora futura.
Situaciones encontradas y propuestas (versión 0.1)
- 1. Clave y módulo del caso de uso.
- Situación: el caso de uso existe solo como CU-11 en «Documentación para la IA», sin clave ni módulo.
- Propuesta: PROD-CNL-ORD, en el módulo Producción / Órdenes.
- Por qué: las órdenes que cancela el Agrónomo son de producción (y el mantenimiento), como las de PROD-CNC-SMB y
   PROD-CNC-CSC. «CNL» lo distingue de «CNC» (Concretar).
- 2. Las entregas en Cancelar Orden.
- Situación: CU-11 permite cancelar una entrega «a realizar» (precondición d y postcondición d). Pero la regla 13 de
   8.12 dice que una entrega se cancela solo cuando se liberan todas sus reservas o se cancela su contrato, y no para
   volver a planificarla. Además, varios casos de uso dejaron para CU-11 qué pasa con una entrega cancelada (temas
   abiertos de COM-CNC-ENT, PROD-PNF-ENV, COM-INI-RUT y COM-PNF-ENT).
- Propuesta: el Agrónomo no cancela entregas. Este caso de uso define la «Cancelación de una entrega», que solo se
   ejecuta incluida en los casos de uso del contrato (Cancelar Compra-venta, COM-RSV-SUM y Modificar Suministro).
- Por qué: cumple la regla 13 de 8.12. La entrega la planifica InfoPonia a partir del contrato, y el Agrónomo no es el
   responsable comercial: si pudiera cancelarla sin tocar el contrato, sus reservas quedarían listas para entrega y la
   recuperación diaria la volvería a planificar (tema abierto de COM-PNF-ENT). Así, las reglas de la entrega cancelada
   quedan escritas en un solo lugar.
- 3. Hardware «reservado» en el mantenimiento.
- Situación: la postcondición c de CU-11 dice que el hardware de reemplazo pasa de «reservado» a «libre». En el
   modelo, los repuestos son insumos que se reservan con ReservaInsumo (R138), y Hardware no tiene esos estados (la
   ficha no define valores de estadoHardware).
- Propuesta: al cancelar un mantenimiento se cancelan sus reservas de insumo y el hardware no cambia (extensión 8e).
   Lo que haga falta sobre el estado del hardware se decide al especificar CU-05 (temas abiertos).
- Por qué: sigue el modelo vigente. La postcondición de CU-11 viene del diseño anterior a la ronda en que se creó
   ReservaInsumo.
- 4. Quién cancela.
- Situación: CU-11 habla de «Agrónomo o superior», mientras que la regla 2 de 8.22 (MD-60) dice que el Agrónomo opera
   las órdenes de los invernaderos a su cargo.
- Propuesta: solo el Agrónomo a cargo del invernadero. El Gerente no cancela órdenes de trabajo desde este caso de
   uso.
- Por qué: es el mismo actor que planifica siembras, transiciones, cosechas y envasados. Si un invernadero se queda
   sin Agrónomo activo, el Gerente ya recibe la alerta «invernadero sin Agrónomo activo» y lo resuelve asignando otro
   (regla 3 de 8.22), que hereda las órdenes y puede cancelarlas.
- 5. Motivo y fecha de la cancelación.
- Situación: el modelo no tiene dónde guardar por qué se canceló una orden. Además, la ficha de OrdenTrabajo y la de
   Entrega solo definen fechaResolucionOrden para la concreción.
- Propuesta: agregar el atributo OrdenTrabajo.motivoCancelacion (texto, obligatorio al cancelar) y precisar que
   fechaResolucionOrden es también la fecha de la cancelación. Hay que registrarlo como un ítem nuevo de
   pendientes_MD.
- Por qué: hay un antecedente en el modelo, OrdenCompra.motivoRechazo (MD-33), y una fecha de resolución que vale para
   los dos desenlaces (OrdenCompra.fechaResolucion, MD-34). El Capataz y el Vendedor necesitan el motivo en el aviso,
   y el log de auditoría no es un dato del dominio que se pueda consultar desde la orden.
- 6. PROD-ASG-STK vuelve a elegir el mismo lote.
- Situación: PROD-ASG-STK prevé su inclusión desde CU-11, pero su primer tema abierto advierte que, sin cambios,
   volvería a elegir el mismo lote (regla 7 de 8.6).
- Propuesta: en la ejecución desde este caso de uso, PROD-ASG-STK no considera los lotes de la cosecha cancelada
   (regla «Lotes excluidos»). Hay que agregarlo en «Ejecución desde cada caso de uso base» de PROD-ASG-STK («Desde
   Cancelar Orden»), como un dato más que recibe del caso de uso base, y anotarlo en pendientes_CU.
- Por qué: si el lote está bien, cancelar no tiene sentido: el cambio de lote o de fecha corresponde a Validar o
   Modificar Cosecha Automática. Si se cancela, es porque el lote no sirve para ese contrato. Excluirlo solo en esa
   ejecución no lo bloquea para otros contratos.
- 7. Qué se hace con lo que queda sin cubrir.
- Situación: PROD-ASG-STK y PROD-ASG-CAM dejan a CU-11 decidir qué pasa con la cantidad que no se puede volver a
   cubrir (temas abiertos de los dos).
- Propuesta: el mismo camino de faltante que la extensión 13a de PROD-CNC-CSC (extensión 8c). Con eso, este caso de
   uso también habilita COM-DCD-FLT, cuyo apartado «Lo habilitan» hoy solo cita a PROD-CNC-CSC y PROD-REG-MRM: hay que
   anotarlo en pendientes_CU.
- Por qué: el faltante es el mismo hecho, venga de una cosecha que rindió menos o de una cosecha que se canceló, y el
   cliente y el Vendedor reciben el mismo tratamiento. Además, PROD-ASG-CAM ya pide que lo cubra el caso de uso que
   genera el faltante, con PROD-ASG-STK, que toma primero la cámara.
- 8. Detalle que ya espera la decisión del cliente.
- Situación: la precondición b de PROD-ASG-STK exige un detalle «abierto» de una venta «abierta». Si la cosecha cubre
   un detalle que ya está «pendiente de decisión del cliente», no se puede incluir.
- Propuesta: no se incluye PROD-ASG-STK. La cantidad liberada se suma al faltante, la fecha de pendiente pasa a la
   fecha actual y el cliente recibe un enlace nuevo con las cantidades actualizadas (extensiones 6c y 8d).
- Por qué: el cliente tiene que decidir sobre el faltante real, no sobre uno desactualizado. Reiniciar el plazo es
   coherente con MD-92, que cuenta la vigencia del enlace desde la fecha de pendiente más reciente.
- 9. Inclusión desde PROD-PNR-FDS.
- Situación: PROD-PNR-FDS (versión 0.1, paso 14 y postcondición f) incluye a Cancelar Orden. Pero la nota del
   15/11/2026 en el punto 10 de «Ajustes pendientes en la documentación» de pendientes_CU dice que PROD-PNR-FDS
   cancela las órdenes «sin pasar por Cancelar Orden». MD-75 solo dice que se cancelan automáticamente.
- Propuesta: se mantiene la inclusión, como está escrita en PROD-PNR-FDS, y se define cómo se ejecuta desde ahí
   («Ejecución desde los casos de uso que lo incluyen»). Hay que corregir la nota de pendientes_CU.
- Por qué: los efectos de cancelar una orden (reservas, agujeros, auditoría) quedan escritos en un solo lugar. Si
   PROD-PNR-FDS los repitiera, cualquier cambio futuro habría que hacerlo en dos casos de uso. MD-75 no lo impide.
- 10. Envases de una entrega cancelada después de envasarse.
- Situación: está abierto qué pasa con los envases de una entrega que se cancela cuando el producto ya se envasó
   (observación 2 de 8.19; temas abiertos de COM-CNC-ENT y de PROD-PNF-ENV).
- Propuesta: las reservas de envases pasan a «cancelada» sin registrar consumo, y se avisa al Agrónomo del invernadero
   de origen con los envases que estaban reservados, para que los regularice con CMP-AJT-STK si se usaron y no pueden
   reutilizarse.
- Por qué: la cancelación la ejecuta otro caso de uso, a veces sin un usuario (COM-RSV-SUM), así que no hay a quién
   pedirle que confirme los envases en ese momento. El Sistema no sabe si el envasado ya se hizo físicamente, y muchas
   veces los envases siguen con el producto y se reutilizan. El ajuste existe justamente para corregir el stock a
   partir de un recuento (regla 4 de 8.19).
- 11. Entrega en curso.
- Situación: está abierto qué pasa con una entrega que se cancela mientras está en el vehículo (temas abiertos de COM-
   CNC-ENT, PROD-PNF-ENV y COM-INI-RUT).
- Propuesta: se cancela igual y se avisa de inmediato al Transportista para que no la entregue y devuelva el producto
   y los envases al invernadero.
- Por qué: bloquearla haría depender la cancelación de un contrato, o su resolución automática, de que el vehículo
   vuelva. Si se cancela sin aviso, el Transportista entregaría algo que ya no corresponde. Si el Transportista la
   concreta antes, el control de concurrencia lo resuelve (extensión 8a de este caso de uso y extensión 14a de COM-
   CNC-ENT).
- 12. Reservas de una entrega cancelada.
- Situación: COM-PNF-ENT pregunta si, al cancelar una entrega cuyas reservas siguen «lista para entrega», CU-11 debe
   cambiar su estado, porque si no la recuperación diaria la vuelve a planificar.
- Propuesta: este caso de uso no cambia las reservas de stock. Exige que el caso de uso base las haya liberado o haya
   cancelado el contrato (precondición de «Cancelación de una entrega»).
- Por qué: es lo que dice la regla 13 de 8.12, y el destino del producto (volver al lote o ingresar a la cámara)
   depende del motivo comercial, que solo conoce el caso de uso base. Con las reservas liberadas, la recuperación
   diaria no la vuelve a planificar.
Cambios pendientes aplicados en este caso de uso
- MD-74 (pendientes_MD, «Decidido sin aplicar»): los agujeros comprometidos de un sector pasan a ser derivados. Por
   eso este caso de uso no modifica los sectores ni registra un log de su cambio: los agujeros dejan de contar al
   cancelarse la orden (regla «Agujeros comprometidos», postcondición d). PROD-PNF-SMB (postcondiciones c e i) y PROD-
   PNF-TRN (postcondiciones c y g) todavía los tratan como un valor guardado.
- MD-73 (pendientes_MD, «Decidido sin aplicar»): la prioridad de la siembra y de la transición es opcional, y sin
   valor se ordena como media. Se aplica en la regla «Orden de presentación» (paso 2).
- Puntos 10 y 13 de «Ajustes pendientes en la documentación» (pendientes_CU): al cancelar una transición se liberan
   los agujeros de cada sector destino (postcondición d), y el Agrónomo cancela las órdenes de sus invernaderos aunque
   no las haya planificado (regla «Quién lo ejecuta»).
- MD-75 (pendientes_MD, «Decidido sin aplicar»): las órdenes con agujeros comprometidos en un sector que pasa a fuera
   de servicio se cancelan automáticamente. Se aplica con la inclusión desde PROD-PNR-FDS (ver la situación 9).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-46, D-50)

PROD-CNL-ORD está escrito para los cuatro tipos de orden. En la ronda **solo existen siembras y transiciones**; el resto del texto se conserva (es el caso de uso completo) pero queda **«Fuera de la ronda (D-45)»**: no se implementa ni se prueba.

### Qué entra y qué no

| Parte del caso de uso | En la ronda |
|---|---|
| Flujo básico, pasos 1 a 10, con siembra y transición (extensión 4a) | **Sí** |
| Extensiones *a, *b, 2a, 6a, 8a | **Sí** |
| Extensión 8b (cambió la orden o sus reservas mientras tanto) | **Sí**, sin la parte de contrato |
| Extensión 9a (el invernadero no tiene Capataz activo) | **Sí**: no se notifica a nadie, la cancelación se registra igual |
| Extensión 9b («no logra entregar la notificación o el correo») | **No aplica** (D-42: la notificación va dentro de la transacción) |
| Extensiones 4b, 4c, 4d, 6b, 6c, 8c, 8d, 8e (cosecha, contrato y mantenimiento) | **Fuera de la ronda (D-45)** |
| Postcondiciones f, g, h, i, j, l | **Fuera de la ronda (D-45)** |
| PROD-ASG-STK, PROD-ASG-CAM, COM-PNF-ENT, COM-DCD-FLT | **Fuera de la ronda (D-45)** |

Aviso con el motivo: en la ronda solo al Capataz (postcondición k). El aviso al Vendedor (postcondición l) es de cosecha, Fuera de la ronda (D-45); cuando exista Cosecha también llevará el motivo, con el mismo texto de la decisión anterior. La postcondición l de la versión 0.1 no menciona el motivo: falta ajustarla en Drive (ver `docs/temas_abiertos.md`).

### Qué hace cada parte

| Parte | Código |
|---|---|
| Lista de órdenes canceladas posibles y resumen | `produccion/servicios/ordenes.py`: `ordenes_cancelables(actor)`, `resumen_de_cancelacion(actor, orden_id)` |
| Cancelar | `produccion/servicios/ordenes.py`: `cancelar_orden(actor, orden_id, motivo)` |
| Cancelar desde otro caso de uso | `produccion/servicios/ordenes.py`: `cancelar_orden_incluida(actor, orden, motivo, *, avisar=False)` |

`cancelar_orden_incluida` existe **para PRD-04** (PROD-PNF-FDS, sector fuera de servicio, cancela las órdenes que usaban el sector). Se escribe en PRD-01 y se prueba con un llamador falso. Reglas:
`actor` puede ser `None` (cancela InfoPonia); no abre transacción propia (usa la del llamador); no notifica al Agrónomo (lo hace quien lo incluye), y notifica al Capataz solo si `avisar=True`; el audit lo escribe el llamador **dentro de su único registro**
(devuelve los afectados y los cambios en vez de auditar).

### Decisiones de aplicación

- **Permisos**: el Agrónomo a cargo del invernadero de la orden, aunque la haya planificado InfoPonia (regla 2 de 8.22). El Gerente no cancela (como en el resto de Producción: no tiene estas pantallas).
- **Bloqueos**: cuentas → invernadero → (variedad, si es siembra) → **sectores** de las ocupaciones (nivel 2c) → insumos de las reservas (`InsumoInvernadero` en orden de id) → fila de la orden y sus reservas. Se leen sin bloquear, se bloquean, se **releen** y se verifica que la orden siga «a realizar» y que las reservas no hayan cambiado (extensión 8a y 8b).
- **Motivo obligatorio**, de 1 a 300 caracteres, sin espacios al borde; vacío o solo espacios → `ErrorDeProduccion('motivo_obligatorio')`; más de 300 → `ErrorDeProduccion('motivo_largo', campo='motivo')`. El prototipo no lo pedía (`orden-cancelar` no tenía motivo ni resumen): manda el CU, hay que agregar ambos.
- **Efectos**: orden → `cancelada`, `fecha_resolucion_orden` = hoy, `motivo_cancelacion`; cada reserva activa → `cancelada` (sin utilizada ni devuelta); las ocupaciones se **conservan** sin lote y con 0 ocupados (la cantidad planificada no cambia, deja de comprometer porque la orden ya no está «a realizar»). No se tocan lotes, cantidades ni etapa (en la transición el lote queda sin transición «a realizar»).
- **Alertas «stock inconsistente»**: se llama a `reevaluar_alertas_del_insumo` de cada insumo de las reservas canceladas (postcondición c).
- **Auditoría**: un registro `cancelacion_orden` con la orden, sus reservas, sus sectores (texto «agujeros comprometidos» antes → después) y las alertas resueltas.
- **Notificación**: se arma así y va dentro de la transacción, con `notificar_a_varios([capataz], titulo, detalle, excluir=actor)` (`docs/api/notificaciones.md`); sin Capataz activo no se avisa y la cancelación se registra igual (extensión 9a).
  - `titulo`: «Orden OT-0007 cancelada» (el código de la orden).
  - `detalle`: «Motivo: <motivo>. <Siembra | Transición de etapa> del <dd/mm/aaaa> en <invernadero>, cancelada por <nombre y apellido>.»
  - Regla del largo: el motivo va completo y primero (310 caracteres con «Motivo: » y el punto). Si el detalle pasa de 500, se acorta con «…» primero el nombre de quien cancela y después el del invernadero (peor caso: invernadero de 80 → quedan unos 55 caracteres para el nombre). El motivo no se recorta nunca, y el aviso no puede hacer fallar la cancelación.
- **Desde otro caso de uso**: `cancelar_orden_incluida` recibe el motivo ya armado por el llamador. PROD-PNR-FDS lo compone («Sector fuera de servicio: <sector>. <motivo>») y puede pasar de 300: la función lo recorta a 300 con «…» (el «…» cuenta dentro de los 300) y no lanza error. El texto completo queda en `FueraDeServicio.motivo_fuera_de_servicio`.
- **Pantalla**: lista de órdenes «a realizar» agrupadas por invernadero y tipo (solo siembra y transición), el resumen de lo que se libera (reservas y agujeros por sector), el campo de motivo y la confirmación. Prototipo: `ACT['orden-cancelar']` y su vista; sin JavaScript funciona igual.
- **Interfaces con las otras tareas**: PRD-04 usa `cancelar_orden_incluida`; la cosecha futura agregará sus ramas. Cualquier función nueva que cancele órdenes debe llamar a esta, no duplicar la lógica.
- **Tipos de orden** (D-67, punto 1): `cancelar_orden` acepta solo siembra y transición (`TIPOS_QUE_CANCELA_PRODUCCION`); con una entrega, un
  mantenimiento o una cosecha lanza `orden_no_cancelable` antes de bloquear. `ordenes_cancelables` lista solo `TIPOS_DE_PRODUCCION` (siembra,
  transición y cosecha; la cosecha, desde COM-04a, con la acción de `comercial`). `cancelar_orden_incluida` acepta **cualquier tipo**, sin
  dar por hecho que la orden tenga Capataz o sectores, con o sin reservas. Las tres cosas las hace y las prueba PRD-01, con órdenes sueltas de
  tipo `entrega` y `mantenimiento`.

### Pruebas

`produccion/tests/test_prod_cnl_ord.py` (una por regla y por postcondición a, b, c, d, e, k, m, n; siembra con reservas, transición, sin Capataz activo, orden ya concretada, motivo vacío y de 301 caracteres, invernadero inactivo, reservas que cambiaron mientras tanto, que el lote queda con la posibilidad de planificar otra transición),
`test_cancelar_orden_incluida.py` (con `actor=None`, sin notificar, sin transacción propia, devuelve afectados) y `test_cancelar_concurrencia.py` (`@tag("concurrencia")`: cancelar contra concretar; cancelar dos veces; cancelar contra planificar otra transición del mismo lote).

## Cómo se aplica en la ronda «Comercial 1»: cosechas (COM-04; D-57, D-59, D-64)

Lo de «Producción 1» (siembra y transición) **no cambia**. COM-04 programa la rama de cosecha: extensiones 4b, 4c, 6b, 6c, 8c y 8d;
postcondiciones f, g, h y l; el aviso al Capataz con el motivo (k) también para la cosecha. Sigue fuera: lo de entregas y envasado (COM-05:
la «Cancelación de una entrega», PCU 7, y la postcondición i, COM-PNF-ENT) y el mantenimiento (4d, 8e, j: ronda del IoT).

### Cambios ya decididos que se aplican (PCU 7 y 11)

- **4c, punto 2:** «Validar o Modificar Cosecha Automática» es **PROD-MOD-CSC · Modificar Cosecha**, y vale para **toda** cosecha pendiente, no
  solo las que planificó InfoPonia (PCU 11): la ventana lo recuerda siempre. Igual en la regla «Lotes excluidos».
- **Lotes excluidos** (PCU 7; PROD-CNL-ORD, situación 6): PROD-ASG-STK recibe los lotes de la cosecha cancelada y no los considera
  (`stock_maduro.asignar(..., lotes_excluidos=…)`, que COM-02 ya dejó con su prueba).
- **Tema abierto «Período de suministro sin reservas»:** resuelto por PROD-PRR-SUM (COM-03): la pre-reserva diaria vuelve a tomar todo período
  con cantidad sin cubrir mientras esté en la ventana, también el de un detalle finalizado con fecha pendiente (D-64 punto 8).

### Qué hace cada parte

| Parte | Código |
|---|---|
| Resumen (4b, 4c, 6b, 6c) | `comercial/servicios/cosechas.py`: `resumen_de_cancelacion_de_cosecha(actor, cosecha_id)` |
| Cancelar una cosecha | `cancelar_cosecha(actor, cosecha_id, motivo, huella)` |
| Cancelar desde otro caso de uso | `cancelar_cosecha_incluida(actor, cosecha, motivo, *, recubrir=True, avisar=True) -> CancelacionDeCosecha` |

Lo comparten con `produccion` (PRD-01): el texto del motivo (1 a 300, mismos códigos `motivo_obligatorio` y `motivo_largo`), el formato del
aviso al Capataz («Orden OT-0051 cancelada», «Motivo: <motivo>. Cosecha del <dd/mm/aaaa> en <invernadero>, cancelada por <nombre>.», con la
misma regla de largo), la acción de auditoría `cancelacion_orden` y los estados de la orden (`cancelada`, `fecha_resolucion_orden` = hoy,
`motivo_cancelacion`). Para no duplicar, `produccion` expone `ordenes.marcar_cancelada(orden, motivo)` y `ordenes.texto_de_cancelacion(orden,
motivo, actor)` (los usa PRD-01 por dentro desde ahora; las pruebas de PRD-01 no cambian).

### Decisiones de aplicación

- **Permisos:** el Agrónomo a cargo del invernadero de la cosecha, de cualquier origen (regla 2 de 8.22). Desde la lista de órdenes y desde
  «Modificar cosecha» (botón `cancelar` de `registrar_acciones_de_cosecha`, D-64 punto 11).
- **Resumen (pasos 4 y 6):**
  - 4b (sin contrato): la reserva con sus lotes y cantidades; «ese stock vuelve a estar libre en los lotes»;
  - 4c (con contrato): la reserva con sus lotes **y sus partidas**, el contrato (tipo, cliente, variedad, fecha de entrega) y la cantidad
    cubierta por la reserva; siempre, el recordatorio de PROD-MOD-CSC con su enlace;
  - 6b (estimación, solo lectura): `stock_maduro.simular(variedad, invernaderos considerados, [(fecha_entrega, cubierto)], parametro,
    lotes_excluidos=lotes de la cosecha, sin_reservas=(la reserva de la cosecha,))`, con los dos argumentos nuevos de `simular` (sección 8
    del patrón: la reserva que se libera cuenta como libre, y sus partidas pueden volver a usarse). Si se cubre todo: de qué partidas o lotes
    saldría y si hace falta una cosecha nueva; si no: cuánto queda sin cubrir y la consecuencia (compra-venta: el cliente recibirá un enlace,
    o, sin correo, el Vendedor registrará la decisión; suministro: el período saldrá con menos y puede haber discrepancia o queja);
  - 6c: el detalle o su venta ya esperan la decisión del cliente: «no se intentará volver a cubrir; la cantidad se suma al faltante».
- **Registro (paso 8), en una transacción:**
  1. bloqueos (orden del patrón): las cuentas (el Capataz; con contrato, el Vendedor) → el invernadero de la cosecha y, con contrato, los
     considerados del contrato, en orden de id → la variedad → los lotes y las partidas candidatos (los de la reserva incluidos) → el contrato
     y su detalle → **la cosecha** → su reserva y sus líneas (y, con faltante, el enlace de la venta);
  2. relectura: 8a (`orden_no_a_realizar`: se concretó o se canceló) y 8b (`cosecha_cambio`, con la huella de la cosecha y de su reserva, y
     el estado del detalle y de la venta, leídos al abrir el resumen);
  3. la cosecha, cancelada (`ordenes.marcar_cancelada`); su reserva, «liberada» (f): las líneas de lote quedan sin cantidad cosechada y las de
     partida sin cambios (la reserva liberada ya no cuenta para el stock libre);
  4. 8c, con contrato y si el detalle se puede cubrir (venta «abierta» con el detalle «abierto», o un período con cantidad pedida): `asignar(actor,
     detalle o período, cubierto de la reserva liberada, fecha_entrega_reserva, parametro, lotes_excluidos=…)` (g); lo no cubierto, por el
     camino de faltante (`docs/patrones/stock_maduro.md`, sección 8);
  5. 8d (6c): sin `asignar`; el camino de faltante con la cantidad liberada (fecha de pendiente nueva, enlace nuevo);
  6. `on_commit`: PROD-ASG-CAM con las partidas de las líneas de cámara liberadas (h). COM-PNF-ENT (i): **se completa en COM-05**.
- **Avisos (9, k y l), dentro de la transacción:** al Capataz con el motivo (sin Capataz activo, nada: 9a); con contrato, al Vendedor: «Cosecha
  OT-0051 de CV-0044 cancelada», con lo que se volvió a cubrir y lo que quedó sin cubrir (l). 9b no aplica (D-42).
- **Auditoría (m, n):** un registro `cancelacion_orden` con la orden, la reserva y sus líneas, el detalle y la venta, y lo de `asignar` y el
  camino de faltante. «Sin bitácora» (regla del CU): no hay registro de bitácora ni movimiento de stock.
- **`cancelar_cosecha_incluida`** (como `cancelar_orden_incluida` de PRD-01): `actor` puede ser `None`; no abre transacción (usa la del
  llamador, con sus bloqueos ya tomados); no audita (devuelve la cosecha, la reserva y lo creado para el registro del llamador). Con
  `recubrir=False` no llama a `asignar` ni al camino de faltante (COM-DCD-FLT: el detalle se rechazó). Con `avisar=True`, el aviso al Capataz
  y al Agrónomo del invernadero (postcondición j de COM-DCD-FLT). La usan COM-DCD-FLT (COM-04) y, desde COM-05, COM-CNL-CVT y la cancelación
  de entregas. **Ninguna función nueva que cancele cosechas duplica esta lógica.**

### Pruebas

`comercial/tests/test_prod_cnl_ord_cosechas.py` (una por postcondición f, g, h, k, l, m, n y por extensión 4b, 4c, 6b, 6c, 8a, 8b, 8c, 8d;
cosecha sin contrato; con contrato que se vuelve a cubrir del todo con cámara, del todo con otro lote (cosecha nueva, sin los lotes
excluidos), en parte y nada; período de un suministro; período de un detalle finalizado con fecha pendiente; la estimación 6b coincide con
lo que después hace el paso 8; motivo vacío y de 301), `test_cancelar_cosecha_incluida.py` (con `actor=None`, `recubrir=False`, sin
transacción propia, devuelve lo afectado) y `test_cancelar_cosecha_concurrencia.py` (`@tag("concurrencia")`: cancelar contra concretar la
misma cosecha; cancelar contra modificarla; cancelar contra la decisión del cliente sobre el mismo detalle).

## Cómo se aplica en la ronda «IoT 1»: el mantenimiento automático (IOT-07; D-73, D-79)

Lo de «Producción 1» y de «Comercial 1» **no cambia**. IOT-07 programa la rama de mantenimiento (4d, 8e, 9a y las postcondiciones j, k y m)
**solo para la orden que crea IOT-RSV-CMD** al agotarse los intentos de un comando. El detalle está en
`docs/casos_de_uso/iot/mantenimiento_automatico.md`, «Cancelar la orden desde la ficha»; acá van solo las diferencias con lo de arriba:

- **Dónde:** en la ficha del equipo del IoT, no en la lista de órdenes de `produccion`, que sigue mostrando solo siembras, transiciones y
  cosechas (D-79, punto 1).
- **Quién:** el alcance del IoT, es decir, el Agrónomo a cargo o, sin Agrónomo activo, el Gerente. **Es una excepción** a «Quién lo
  ejecuta» y a «el Gerente no cancela» (D-79, punto 2). Falta pasarla a «CU extendidos» (`docs/temas_abiertos.md`).
- **Cómo:** `iot` llama a `cancelar_orden_incluida(actor, orden, motivo, avisar=False)` y avisa al Técnico (D-73, punto 3), con el mismo
  formato del aviso al Capataz y «Mantenimiento técnico» como tipo. Si al programar IOT-07 ya existe `ordenes.texto_de_cancelacion` (COM-04a),
  se usa esa función.
- **Repuestos (8e):** en esta ronda ningún mantenimiento los reserva; el resumen dice «Sin repuestos reservados».
- **La alerta que originó la orden** (tema abierto «Alerta que originó un mantenimiento»): para la orden automática lo responde D-73
  (punto 4). Cancelar no la resuelve: se resuelve cuando el actuador vuelve a «activo».
- También cancela, incluida, **IOT-MOD-HDW** (regla 8, al volver a activar un equipo), con el motivo «Se volvió a activar el equipo
  {identificador}.».

## Cómo se aplica en la ronda «Comercial 1»: entregas y envasado (COM-05a1; D-57, D-59, D-66)

Lo de «Producción 1», de las cosechas (COM-04) y del IoT **no cambia**. COM-05a1 programa la **«Cancelación de una entrega (solo desde otro
caso de uso)»** de arriba, con lo que le suma la PCU (sección 7: resuelve la alerta «entrega sin transportista»), y las situaciones 10 a 12.
No hay pantalla: **el Agrónomo no cancela entregas** (regla «Órdenes que cancela el Agrónomo»; D-66, punto 13). Archivo de pruebas:
`comercial/tests/test_prod_cnl_ord_entregas.py`.

### Qué hace cada parte

- **`cancelar_entrega_incluida(actor, entrega, motivo) -> CancelacionDeEntrega`** en `comercial/servicios/entregas.py` (D-59, A3: la entrega es
  de `comercial`). Como `cancelar_cosecha_incluida` (COM-04): `actor` puede ser `None` (InfoPonia); **no abre transacción** (usa la del caso
  de uso base, con sus bloqueos ya tomados y la entrega bloqueada después de sus reservas de stock: `docs/patrones/bloqueos.md`, «Entregas y
  envasado»); **no audita** (devuelve la entrega, las reservas de insumo canceladas y la alerta resuelta, para el registro del caso de uso
  base, D-36). Lanza `entrega_no_a_realizar` si la entrega ya no está «a realizar» (8a: el caso de uso base decide cómo sigue).
- Hace, en este orden:
  1. `ordenes.cancelar_orden_incluida(actor, entrega, motivo, avisar=False)` de PRD-01: la orden a «cancelada», con la fecha de hoy y el
     motivo (recortado a 300 si hace falta), y **sus reservas de insumo** (envases) a «cancelada» sin consumo (situación 10). PRD-01 ya acepta
     una orden de tipo `entrega` (sin sectores ni Capataz) y lo prueba (D-67, punto 1): acá no se toca `produccion`;
  2. **no toca las reservas de stock** ni sus líneas (precondición; situación 12): el destino del producto lo decide el caso de uso base. La
     entrega conserva sus líneas como historial (R150 en 0..\*);
  3. `resolver_alerta_de_estado(invernadero, "comercial_entrega_sin_transportista", clave=f"entrega:{id}")` si estaba activa (PCU 7);
  4. los avisos (dentro de la transacción, D-42):
     - al **Transportista**, si lo tiene: título «Se canceló la entrega OT-0231», detalle «{motivo}.»; si está **en curso** (su vehículo
       `esta_en_ruta(hoy)` y la fecha programada es hoy o anterior; situación 11), además: «No la entregues: devolvé el producto y los envases
       a Invernadero Sur.». La entrega deja de contar para su carga y sus límites (solo cuentan las no canceladas);
     - al **Agrónomo** del invernadero (si está activo), solo si tenía envasado: «Se canceló OT-0231, que tenía envases reservados»,
       detalle «Reservados: 20 Bandeja PET 1 kg, 5 Cajón plástico. Si ya se usaron y no se pueden volver a usar, ajustá el stock.»
       (situación 10);
     - **el aviso al cliente lo manda el caso de uso base**, que conoce el motivo comercial.
- **Quién la llama en COM-05a1:** `quitar_lineas_liberadas(entrega_ids)` (`docs/casos_de_uso/comercial/entregas.md`, «Lo que completa a otras
  tareas»), que usan **PROD-VNC-CAM 3a** (motivo «Se venció en cámara el producto reservado.») y la **merma en cámara 10c** (motivo «Se perdió en
  cámara el producto reservado.»), cuando la entrega queda vacía. Después: **COM-CNL-CVT** (COM-05b) y **COM-RSV-SUM** (COM-07).

### Pruebas

`comercial/tests/test_prod_cnl_ord_entregas.py` (`ProdCnlOrdEntregasServicioTests`): la entrega cancelada con su fecha y su motivo; las
reservas de insumo canceladas sin consumo y el stock libre que sube; las reservas de stock sin cambios; la alerta resuelta; el aviso al
Transportista (con y sin «en curso») y al Agrónomo (con y sin envasado, sin Agrónomo activo); que no audita; `entrega_no_a_realizar`; sin
transacción, `RuntimeError` (o lo que lance `cancelar_orden_incluida`); y, desde PROD-VNC-CAM y la merma en cámara, la entrega vacía cancelada y
la que conserva otra línea, sin cancelar. Concurrencia (`test_entregas_concurrencia.py`): una merma en cámara que vacía la entrega contra un
envasado de esa entrega (el que llega segundo ve la entrega cancelada: 10a de PROD-PNF-ENV).

## Cómo se aplica en la ronda «Comercial 1»: la compra-venta cancelada (COM-05b; D-65, D-66, D-67)

Lo anterior **no cambia**. COM-CNL-CVT (`docs/casos_de_uso/comercial/compra_venta.md`, al final) **incluye** PROD-CNL-ORD para dos tipos de
orden, y para los dos usa las funciones que ya existen; no hay código nuevo de cancelación:

- **Cosechas «a realizar»** de las reservas de los detalles que se cancelan: `cancelar_cosecha_incluida(actor, cosecha, motivo,
  recubrir=False, avisar=True)` (COM-04a). `recubrir=False` porque el detalle se cancela (no hay nada que volver a cubrir); `avisar=True`: el
  Capataz y el Agrónomo reciben el aviso con el motivo.
- **Entregas «a realizar»** de la venta, con envío o de retiro (6b de COM-CNL-CVT): `cancelar_entrega_incluida(actor, entrega, motivo)`
  (COM-05a1): la orden y sus reservas de envases canceladas (situación 10), la alerta «entrega sin transportista» resuelta (PCU 7), el aviso al
  Transportista y, con envases, al Agrónomo. **El aviso al cliente lo da el caso de uso base**: es el comprobante de cancelación de la venta.
- **Una entrega en curso no se cancela** (situación 11 vale solo para quien la cancela desde otro caso de uso que lo admita): COM-CNL-CVT la
  detecta antes (4a) y no sigue.
- El **motivo** que reciben las dos funciones lo arma COM-CNL-CVT: «Se canceló la compra-venta CV-0044: el cliente desistió.» (de 1 a 300; si
  pasa, lo recorta `cancelar_orden_incluida`).
- Actúa una persona (el Vendedor o el Gerente), no un proceso automático: la regla de PCU 7 («cuando lo incluye un proceso automático se
  omite el paso 10») no aplica; el Agrónomo recibe el aviso de cada cosecha y de cada entrega con envases que se cancelan.

Pruebas: en `comercial/tests/test_com_cnl_cvt.py` (postcondición d) y métodos nuevos en `test_prod_cnl_ord_entregas.py` y
`test_cancelar_cosecha_incluida.py` (desde COM-CNL-CVT).
