# Casos de uso · comercial · Faltante

Copia para el repo de COM-DCD-FLT versión 0.1 de «CU extendidos». Cotejado con pendientes_CU, con «PCU · Cambios para pendientes_CU
(comercial)» (la sección 7 lo cambia), con el modelo de dominio (reglas 16, 17, 21 y 29 de 8.6; 9, 10 y 17 de 8.8; 16 de 8.9; 2 de 8.18; 18 de
8.20; 1 a 3 y 8 de 8.15) y con el glosario.

**El código va en la app `comercial`** (`comercial/servicios/faltantes.py` y las páginas públicas de `comercial/views_cliente.py`). El enlace
del cliente: `docs/patrones/enlace_del_cliente.md` (D-65). Archivos de pruebas: `comercial/tests/test_com_dcd_flt.py`,
`test_enlaces.py` (el patrón) y `test_faltantes_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-DCD-FLT no numera sus reglas (`test_enlace_de_decision_…`, `test_rechazo_…`), sus postcondiciones son
`test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…` (`test_ext_6b_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-DCD-FLT | Decidir Faltante | Cliente (por el enlace) o Vendedor del contrato | `comercial/tests/test_com_dcd_flt.py` |

## COM-DCD-FLT · Decidir Faltante
**Alcance:** Sistema InfoPonia.  
 **Nivel:** Objetivo de usuario.  
 **Módulo:** Comercial.  
 **Versión:** 0.1  
 **Actor principal:** Cliente de la compra-venta. Es un actor externo sin usuario en el Sistema: accede mediante el enlace de decisión que recibió por correo. En la extensión 1a, el Vendedor del contrato registra la decisión en su nombre.

**Personal involucrado e intereses**

  - **Cliente:**
      
      - quiere saber cuánto se le puede entregar de cada producto y decidir si lo acepta, sin tener que llamar a nadie;
      - quiere no pagar por lo que no va a recibir;
      - quiere constancia de lo que decidió.
  - **Vendedor:**
      
      - quiere que la venta no quede trabada esperando una respuesta;
      - quiere enterarse de la decisión del cliente;
      - quiere poder registrarla él cuando el cliente no tiene correo o no respondió a tiempo.
  - **Agrónomo:** si el cliente rechaza, quiere enterarse de las cosechas que se cancelan y del producto que vuelve a la cámara.
  - **Capataz:** quiere no cosechar para una reserva que ya no existe.
  - **Organización (Jardín Botánico):**
      
      - quiere no inmovilizar producto perecedero esperando una respuesta;
      - quiere que lo rechazado vuelva a estar disponible para otros contratos;
      - quiere que el acceso de un externo no exponga datos internos ni permita modificar nada más que su propia decisión.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Lo habilitan:** PROD-CNC-CSC · Concretar Cosecha (extensión 13a) y PROD-REG-MRM · Registrar Merma (extensión 10c). Los dos pasan detalles a “pendiente de decisión del cliente” y envían el enlace.
  - **Dispara:**
      
      - COM-PNF-ENT · Planificar Entrega, si la venta queda “abierta” con todas sus reservas listas (disparador 1 de COM-PNF-ENT);
      - la asignación automática de cámara (caso por especificar 9), si ingresa producto a la cámara o se libera una línea de cámara.
  - **Relacionados:**
      
      - las cosechas que cancela este caso de uso tienen el mismo efecto que Cancelar Orden (CU-11), pero se registran aquí, en la misma operación;
      - cancelar la compra completa es Cancelar Compra-venta (caso por especificar 5).

**Precondiciones**

a. El Cliente recibió un enlace de decisión de faltante. En la extensión 1a, el Vendedor está autenticado en el Sistema.

**Garantías mínimas**

  - El registro es atómico. Si el Cliente abandona antes de confirmar, o si el caso de uso falla:
      
      - los detalles siguen en “pendiente de decisión del cliente” y la venta sigue en el mismo estado;
      - no cambia ninguna reserva ni cosecha;
      - no se crea ninguna partida de cámara ni movimiento de stock;
      - no se envía ningún correo ni notificación, ni queda ningún log de auditoría parcial;
      - el enlace puede volver a usarse mientras sirva.
  - El enlace admite un solo envío. Cada detalle se decide una única vez, y la decisión no se modifica después.
  - Una venta nunca vuelve a “abierta” mientras tenga detalles pendientes.
  - El Cliente solo ve su venta. No ve de qué lotes, partidas o invernaderos sale el producto, ni costos, ni datos de otros contratos.
  - Este caso de uso no registra pagos ni asientos contables, no modifica la cantidad solicitada de ningún detalle, la cantidad actual de ningún lote ni la cantidad disponible de ninguna partida existente.

**Garantías de éxito (Postcondiciones)**

**En toda decisión registrada:  
** a. Todos los detalles que estaban pendientes en la venta quedaron decididos, cada uno en “confirmado” o en “rechazado”.  
 b. El enlace quedó usado y ya no admite otro envío.  
 c. La venta pasó a “abierta” si quedó al menos un detalle no rechazado, o a “cancelada” si todos sus detalles quedaron rechazados.  
 d. Se notificó al Vendedor del contrato la decisión de cada detalle.  
 e. Se envió al Cliente por correo un acuse con la decisión de cada detalle, la cantidad que recibirá, el subtotal de cada detalle y el monto total de la venta.  
 f. Se creó un log de auditoría con origen “cliente mediante enlace”, el identificador del cliente y el de la venta, la fecha y la hora. Registra también:

  - los cambios de valor de la venta y de cada detalle, reserva y cosecha modificados;
  - el identificador de cada partida de cámara y de cada movimiento de stock creados.

**Por cada detalle aceptado:  
** g. El detalle pasó a “confirmado”, con la cantidad vendida igual a la cantidad disponible al registrar y el subtotal calculado sobre esa cantidad.  
 h. Sus reservas no cambiaron, y el detalle dejó de tener cantidad sin cubrir.

**Por cada detalle rechazado:  
** i. El detalle pasó a “rechazado” y sus reservas no liberadas pasaron a “liberada”.  
 j. Cada cosecha “a realizar” de esas reservas pasó a “cancelada”, con la fecha de resolución igual a la fecha actual. Se notificó la cancelación al Capataz y al Agrónomo del invernadero de la cosecha.  
 k. Por cada línea de lote ya cosechada de esas reservas, se creó una partida de cámara con:

  - estado “disponible” y motivo “rechazo por cantidad reducida”;
  - cantidad igual a la cantidad cubierta de la línea;
  - costo unitario igual al costo por planta del lote;
  - fecha de ingreso igual a la fecha actual y fecha límite igual a la fecha de la cosecha más la duración postcosecha de la variedad.

Por cada partida se registró un movimiento de stock de tipo “ingreso a cámara”, originado en la compra-venta.  
 l. Si ingresó producto a la cámara o se liberó alguna línea de cámara, se disparó la asignación automática de cámara.

**Si la venta quedó “abierta”:  
** m. Si todas las reservas no liberadas de sus detalles no rechazados están “lista para entrega”, se disparó COM-PNF-ENT · Planificar Entrega.

**Escenario principal de éxito (o Flujo Básico)**

(La venta tiene un solo detalle pendiente, con todas sus reservas “lista para entrega”, y el Cliente acepta la cantidad disponible.)

1.  **El Cliente abre el enlace de decisión.**
2.  **El Sistema verifica el enlace y presenta la venta:**
      
      - la fecha pactada, la modalidad (envío a domicilio o retiro en invernadero) y la fecha hasta la que puede decidir;
      - por cada detalle pendiente: la variedad, la cantidad solicitada, la cantidad disponible, el precio unitario y el subtotal con la cantidad disponible;
      - los demás detalles de la venta, solo para informar.
3.  **El Cliente indica que acepta la cantidad disponible del detalle pendiente.**
4.  **El Sistema presenta el resumen de la decisión: la cantidad que recibirá, el subtotal del detalle y el nuevo monto total de la venta. Advierte que la decisión no podrá modificarse y que el enlace no podrá volver a usarse.**
5.  **El Cliente confirma su decisión.**
6.  **El Sistema verifica que el enlace siga sirviendo, que el detalle siga pendiente y que su cantidad disponible no haya cambiado, y registra la decisión:**
      
      - pasa el detalle a “confirmado”, con la cantidad disponible como cantidad vendida;
      - pasa la venta a “abierta”;
      - marca el enlace como usado;
      - registra la auditoría correspondiente.
7.  **Como todas las reservas de la venta están “lista para entrega”, el Sistema dispara COM-PNF-ENT · Planificar Entrega.**
8.  **El Sistema envía al Cliente el acuse de su decisión y notifica la decisión al Vendedor del contrato.**
9.  **El Sistema informa al Cliente que su decisión quedó registrada.**

**Extensiones (o Flujos Alternativos)**

***a. En cualquier momento antes del paso 5, el Cliente abandona la decisión (por ejemplo, cierra la página):**

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
2.  El enlace puede volver a usarse mientras sirva.

***b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Cliente puede volver a abrir el enlace mientras sirva. Si la decisión ya había quedado registrada, se aplica la extensión 2a.

**1a. El Vendedor registra la decisión en nombre del cliente (el cliente no tiene correo, o el enlace venció sin respuesta):**

1.  El Vendedor inicia el registro de una decisión de faltante.
2.  El Sistema presenta las ventas de sus contratos en “pendiente de decisión del cliente” cuyo cliente no tiene correo o cuyo enlace venció. Para cada una indica el cliente, sus datos de contacto, la fecha pactada, los detalles pendientes y desde qué fecha esperan.
3.  El Vendedor selecciona una venta.
4.  El caso de uso continúa en el paso 2, con el Vendedor como actor y con estas diferencias:
      
      - en el paso 2, el Sistema no verifica el enlace;
      - en el paso 6, el Sistema no verifica el enlace y no lo marca como usado;
      - en el paso 8, el acuse se envía solo si el cliente tiene correo, y no se notifica al Vendedor, porque es quien decidió;
      - el log de auditoría registra como origen al Vendedor, con su usuario y su rol.

**1a.2a. No hay ventas que el Vendedor pueda decidir:**

1.  El Sistema informa que no hay ventas de sus contratos esperando una decisión que él pueda registrar. Las de clientes con correo y enlace vigente las decide el cliente.
2.  El caso de uso termina.

**2a. El enlace no sirve: es inválido, ya fue usado, venció, fue reemplazado por uno más nuevo, la venta fue cancelada o ya no tiene detalles pendientes:**

1.  El Sistema informa que el enlace no puede usarse, y por qué.
2.  El Sistema presenta los datos de contacto del Vendedor del contrato.
3.  El caso de uso termina.

**2b. Un detalle pendiente tiene cantidad disponible cero:**

1.  El Sistema indica que no hay producto disponible para ese detalle y, para ese detalle, solo ofrece rechazarlo.
2.  El caso de uso continúa en el paso 3.

**3a. El Cliente rechaza un detalle:**

1.  El Cliente indica que rechaza el detalle.
2.  El caso de uso continúa en el paso 4. El resumen indica que no recibirá ese producto ni se le cobrará y, si todos los detalles de la venta quedarían rechazados, que la compra quedará cancelada.
3.  En el paso 6, el Sistema:
      
      - pasa el detalle a “rechazado” y libera sus reservas;
      - cancela las cosechas “a realizar” de esas reservas;
      - crea una partida de cámara por cada línea de lote ya cosechada, con su movimiento de stock;
      - pasa la venta a “abierta” o, si todos sus detalles quedaron rechazados, a “cancelada”.
4.  En el paso 7, el Sistema dispara la asignación automática de cámara si ingresó producto a la cámara o se liberó una línea de cámara. Dispara COM-PNF-ENT solo si la venta quedó “abierta” con todas sus reservas “lista para entrega”.
5.  En el paso 8, el Sistema notifica además cada cosecha cancelada al Capataz y al Agrónomo de su invernadero.

**3b. La venta tiene más de un detalle pendiente:**

1.  El Cliente indica, por cada detalle pendiente, si acepta la cantidad disponible o lo rechaza (extensión 3a).
2.  El caso de uso continúa en el paso 4. El resumen presenta la decisión de cada detalle.

**4a. El Cliente quiere pasar al resumen sin haber decidido todos los detalles pendientes:**

1.  El Sistema señala qué detalles faltan decidir.
2.  El Cliente decide los que faltan (vuelve al paso 3).

**4b. El Cliente quiere cambiar la decisión de un detalle antes de confirmar:**

1.  El caso de uso vuelve al paso 3. Las decisiones de los demás detalles se conservan.

**6a. Al registrar, el enlace dejó de servir o algún detalle ya no está pendiente (por ejemplo, venció mientras el Cliente decidía, llegó un enlace más nuevo, la venta fue cancelada o la cámara cubrió un detalle):**

1.  El Sistema no registra ningún cambio e informa qué cambió.
2.  Si el enlace sigue sirviendo y la venta conserva detalles pendientes, el caso de uso vuelve al paso 2. Si no, el Sistema presenta los datos de contacto del Vendedor y el caso de uso termina.

**6b. Al registrar, la cantidad disponible de algún detalle cambió (por ejemplo, por una merma en cámara):**

1.  El Sistema no registra ningún cambio y presenta la nueva cantidad disponible de cada detalle afectado. Si alguna quedó en cero, para ese detalle solo ofrece rechazar.
2.  El Cliente vuelve a decidir los detalles afectados (vuelve al paso 3). Las decisiones de los demás detalles se conservan.

**7a. Alguna reserva de la venta todavía no está “lista para entrega” (por ejemplo, tiene una cosecha “a realizar”):**

1.  El Sistema no dispara COM-PNF-ENT. Se dispara cuando la última reserva quede lista (disparador 1 de COM-PNF-ENT).
2.  El caso de uso continúa en el paso 8.

**8a. El Sistema no logra enviar el acuse o una notificación:**

1.  La decisión permanece registrada.
2.  El Sistema reintenta el envío.
3.  Si lo que falló fue el acuse, en el paso 9 el Sistema informa además al Cliente que el acuse le llegará más tarde.

**Requisitos especiales**

  - La página del enlace se usa desde navegadores web modernos (Chrome, Firefox, Edge), en computadora y en celular, sin instalación ni registro.
  - La información del paso 2 se presenta en no más de 2 segundos.
  - El registro del paso 6 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El registro del paso 6 es una única transacción: detalles, venta, reservas, cosechas, partidas, movimientos de stock, enlace y logs se registran juntos o no se registra ninguno. El acuse, las notificaciones y los disparos (COM-PNF-ENT y la asignación de cámara) se ejecutan después de confirmar la transacción.
  - El control de concurrencia impide dos cosas:
      
      - que dos decisiones sobre la misma venta se registren a la vez;
      - que una decisión se registre mientras otra operación cambia las reservas del detalle (asignación de cámara, merma en cámara, Cancelar Compra-venta).
  - El enlace no se puede adivinar ni reutilizar, y no da acceso a nada fuera de la venta.
  - En la extensión 1a, solo el Vendedor del contrato registra la decisión.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales.
  - Los logs de auditoría son de solo inserción. Indican como origen “cliente mediante enlace” o, en la extensión 1a, el usuario.

**Reglas de negocio**

  - **Detalle pendiente de decisión:** detalle de compra-venta con faltante que el stock maduro libre no pudo cubrir (regla 16 de 8.6). Lo pasan a ese estado PROD-CNC-CSC (extensión 13a) y PROD-REG-MRM (extensión 10c), que cargan la fecha en que pasó a pendiente (fechaPendienteDecision, ronda 21). Mientras espera, no se cubre con una cosecha manual (regla 8 de 8.8). Si la asignación automática de cámara llega a cubrirlo, vuelve a “abierto” y se le informa al cliente (regla 17 de 8.8). (Pasos 2 y 6)
  - **Cantidad disponible:** cantidad cubierta del detalle, es decir, la suma de la cantidad cubierta de las líneas de sus reservas no liberadas (reglas 9 y 10 de 8.8). Se calcula al presentar la venta y otra vez al registrar. (Pasos 2 y 6; extensiones 2b y 6b)
  - **Enlace de decisión:** (Pasos 2 y 6; extensiones 2a y 6a)
      
      - hay uno por venta, con todos sus detalles pendientes;
      - es de uso único: puede abrirse muchas veces, pero se envía una sola;
      - si aparece otro detalle pendiente antes de decidir, se envía un enlace nuevo con todos los detalles pendientes y el anterior deja de servir;
      - vence en la fecha de pendiente de decisión más reciente de sus detalles pendientes más diasVigenciaEnlaceFaltante (ronda 21);
      - deja de servir si venció, ya se usó, fue reemplazado, la venta se canceló o la venta ya no tiene detalles pendientes;
      - la vigencia se controla al abrirlo y también al registrar.
  - **Opciones del cliente:** (Pasos 3 y 4; extensiones 2b, 3a, 3b y 4a)
      
      - por cada detalle pendiente, aceptar la cantidad disponible o rechazar el detalle;
      - con cantidad disponible cero, solo puede rechazar;
      - todos los detalles pendientes se deciden en un solo envío;
      - cancelar la compra completa es Cancelar Compra-venta, y esperar otra fecha para recibir la cantidad completa queda como mejora futura.
  - **Aceptación:** el detalle queda “confirmado”, con la cantidad disponible como cantidad vendida, y sus reservas no cambian. La cantidad solicitada no se modifica. Un detalle confirmado no tiene cantidad sin cubrir, así que la asignación de cámara no le reserva más. El subtotal se calcula sobre la cantidad vendida. (Reglas 16 y 20 de 8.6; reglas 10 y 17 de 8.8, precisadas en la ronda 21; paso 6)
  - **Rechazo:** el detalle queda “rechazado” y sus reservas no liberadas pasan a “liberada”. En la misma operación se cancelan las cosechas “a realizar” de esas reservas. Cada cosecha tiene una sola reserva (R087), de un solo detalle (R123), así que la cancelación no afecta a otros contratos. Lo ya cosechado ingresa a la cámara, las líneas de cámara dejan de apartar stock y se dispara la asignación automática de cámara. (Regla 16 de 8.6; regla 17 de 8.8; extensión 3a)
  - **Partida de cámara por rechazo:** (Regla 29 de 8.6; regla 16 de 8.9; extensión 3a)
      
      - se crea una por cada línea de lote ya cosechada de una reserva liberada;
      - su cantidad es la cantidad cubierta de la línea: el menor valor entre la cosechada y la reservada;
      - su costo unitario es el costo por planta del lote;
      - la fecha de ingreso es la fecha actual;
      - la fecha límite es la fecha de la cosecha más la duración postcosecha de la variedad, así que no se reinicia su vida útil;
      - genera un movimiento de stock “ingreso a cámara”, originado en la compra-venta.
  - **Estado de la venta:** vuelve a “abierta” cuando ya no quedan detalles pendientes y al menos uno no está rechazado. Pasa a “cancelada” si todos sus detalles quedaron rechazados. (Regla 21 de 8.6, precisada en la ronda 21; paso 6 y extensión 3a)
  - **Entrega:** si la venta queda “abierta” y todas las reservas no liberadas de sus detalles no rechazados están “lista para entrega”, se dispara COM-PNF-ENT. Si la fecha pactada ya pasó, la entrega se planifica con retraso, según ese caso de uso. (Paso 7 y extensión 7a)
  - **Quién decide:** el Cliente, mediante el enlace. El Vendedor del contrato registra la decisión solo si el cliente no tiene correo (regla 18 de 8.20) o si el enlace venció sin respuesta. Así la decisión es, en lo posible, del propio cliente. (Extensión 1a)
  - **Vencimiento sin respuesta:** es un evento de tiempo. Cuando el enlace vence sin decisión, los detalles siguen pendientes y su stock sigue reservado. InfoPonia notifica al Vendedor del contrato, con una notificación y no con una alerta (las alertas van al Gerente o al Agrónomo, R007 y R049), para que hable con el cliente y registre la decisión. No hay decisión tácita, con el mismo criterio que la regla 3 de 8.15. (Extensión 1a)
  - **Avisos:** (Pasos 8 y 1a.4; extensión 3a)
      
      - el Cliente recibe un acuse por correo, salvo que no tenga correo;
      - el Vendedor del contrato recibe una notificación, salvo que haya decidido él;
      - el Capataz y el Agrónomo del invernadero reciben un aviso por cada cosecha cancelada.
  - **Sin contabilidad:** este caso de uso no registra pagos ni asientos. La compra-venta los genera recién en la entrega. (Reglas 19 y 22 de 8.6)
  - **Cliente dado de baja:** su venta, aunque esté “pendiente de decisión del cliente”, sigue su curso, y el cliente puede decidir igual. (Regla 2 de 8.18)

**Lista de tecnología y variaciones de datos**

  - **1.** El enlace llega en el correo que envían PROD-CNC-CSC y PROD-REG-MRM. El correo incluye las cantidades solicitada y disponible de cada detalle pendiente, la fecha pactada y la fecha de vencimiento del enlace.
  - **2.** Las cantidades se expresan en plantas, como números enteros. Los precios y montos se expresan en pesos.
  - **3.** Cada detalle pendiente ofrece dos opciones, aceptar o rechazar, sin ninguna elegida de antemano.
  - **8.** El acuse indica el identificador de la venta, la decisión de cada detalle, la cantidad que recibirá, el subtotal de cada detalle, el monto total y la fecha pactada. Las notificaciones al Vendedor, al Capataz y al Agrónomo se entregan dentro del Sistema y pueden, además, enviarse por correo electrónico.

**Frecuencia**

Una vez por cada venta con detalles pendientes de decisión. Depende de los faltantes de cosecha y de las mermas en cámara sobre producto reservado. Se espera que sea poco frecuente. A confirmar con el Jardín Botánico.

**Temas abiertos**

  - El valor inicial de diasVigenciaEnlaceFaltante (2 días) hay que confirmarlo con el Jardín Botánico.
  - Esperar a otra fecha para recibir la cantidad completa queda como mejora futura.
  - Si el producto ya cosechado supera su fecha límite mientras el detalle espera, la partida que crea el rechazo nace vencida. ¿Se registra en ese momento la merma por vencimiento que InfoPonia hace en forma automática?
  - El reenvío del enlace a un cliente que lo perdió queda como mejora futura. Mientras tanto, el cliente se comunica con el Vendedor y, al vencer el enlace, decide el Vendedor (extensión 1a).

## Cambios ya decididos que se aplican (PCU, sección 7)

1. **«Lo habilitan» suma PROD-CNL-ORD · Cancelar Orden (extensiones 8c y 8d)**, que también deja detalles «pendiente de decisión del cliente»
   (PCU 7; PROD-CNL-ORD, situación 7). En el código también lo habilitan PROD-VNC-CAM (3a.2a) y la rama de cámara de PROD-REG-MRM (10c): todos
   usan el mismo camino de faltante (`docs/patrones/stock_maduro.md`, sección 8).
2. **Nombres vigentes:** «la asignación automática de cámara (caso por especificar 9)» es **PROD-ASG-CAM**; «Cancelar Orden (CU-11)» es
   **PROD-CNL-ORD**; «Cancelar Compra-venta (caso por especificar 5)» es **COM-CNL-CVT** (COM-05).

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57, D-64, D-65)

**El código va en `comercial`**: `comercial/servicios/faltantes.py` (el caso de uso y el camino de faltante) y `comercial/views_cliente.py`
(las páginas del enlace, sin cuenta). El enlace: `docs/patrones/enlace_del_cliente.md` y D-65. Sin contabilidad: el caso de uso no tiene
asientos («Sin contabilidad»), así que no hay nada fuera de la ronda por D-57.

### El camino de faltante (lo que deja una venta «pendiente de decisión del cliente»)

`seguir_camino_de_faltante` (sección 8 del patrón de stock), dentro de la transacción del caso de uso que lo produce:

- el detalle pasa a «pendiente de decisión del cliente» con `fecha_pendiente_decision = hoy`; si ya lo estaba, solo cambia la fecha
  (8d de PROD-CNL-ORD: el plazo se cuenta desde la fecha más reciente);
- la venta pasa a «pendiente de decisión del cliente» (si ya lo estaba, no cambia);
- con correo del cliente: `crear_enlace` (reemplaza el vigente; vence en la `fecha_pendiente_decision` más reciente de los detalles pendientes
  + `dias_vigencia_enlace_faltante`) y el correo con `on_commit` (D-65). Sin correo: no hay enlace (el vigente, si lo había, pasa a
  `reemplazado`) y la notificación al Vendedor dice «registrá vos la decisión»;
- la notificación del faltante al Vendedor del contrato la arma el caso de uso que lo produce (cada uno tiene su texto).

### COM-DCD-FLT · Decidir Faltante

- **Funciones:** `datos_de_decision(enlace)` (paso 2), `resumen_de_decision(enlace, decisiones)` (paso 4) y `registrar_decision(enlace_id,
  decisiones, disponibles_vistos, *, vendedor=None) -> ResultadoDecision` (paso 6; con `vendedor`, la extensión 1a). Las páginas del cliente
  llaman a las mismas funciones que la del Vendedor.
- **Paso 2 (lo que ve el cliente):** la venta (`CV-0044`), la fecha pactada, la modalidad (la dirección de envío, o el invernadero de retiro con
  su dirección), **hasta cuándo puede decidir** (`fecha_vencimiento` del enlace); por detalle pendiente: variedad, cantidad solicitada,
  **cantidad disponible** (cantidad cubierta, regla «Cantidad disponible»), precio unitario y subtotal con la disponible; los demás detalles,
  solo para informar. Nada de lotes, partidas, invernaderos de origen ni costos (garantía mínima 4). En 2 segundos (requisito especial):
  una consulta por tabla.
- **2a:** la pantalla de enlace no válido con el motivo y el contacto del Vendedor (nombre, teléfono y correo de su cuenta).
- **2b:** con disponible 0, solo «No recibir <variedad>».
- **Pasos 3 a 5 (3a, 3b, 4a, 4b):** un formulario con una elección por detalle pendiente (aceptar la cantidad disponible o no recibir ese
  producto), todos obligatorios (4a: `faltan_decisiones` con los detalles que faltan); el resumen (paso 4) en otra página, con la cantidad
  que recibirá, el subtotal de cada detalle y el **monto total nuevo** de la venta (suma de los subtotales con la cantidad que recibirá de los
  detalles no rechazados; los no pendientes, con la solicitada), la advertencia «la decisión no podrá modificarse y el enlace no podrá volver
  a usarse» y, si todos quedarían rechazados, «la compra quedará cancelada». «Cambiar» vuelve al formulario con lo elegido (4b). Sin
  JavaScript funciona igual (dos páginas y un POST).
- **Paso 6, registro (una transacción):**
  1. bloqueos: cuentas (el Vendedor; el Capataz y el Agrónomo de las cosechas que se cancelan) → los invernaderos de las reservas de los
     detalles rechazados (`bloquear_invernadero_para_alertas`: activo o no, porque el producto existe aunque el invernadero se haya dado de
     baja) → las variedades → los sectores y los lotes de esas reservas → sus partidas → la venta → sus detalles → las cosechas «a realizar»
     → las reservas y sus líneas → **el enlace** (`bloquear_enlace`, D-65);
  2. relectura: 6a (`enlace_no_sirve` o `detalle_ya_no_pendiente`, con qué cambió) y 6b (`disponible_cambio`, con la cantidad nueva de cada
     detalle afectado: la pantalla manda en un campo oculto la disponible que mostró, `disponibles_vistos`);
  3. **aceptado** (g, h): «confirmado», `cant_entregada_venta` = la disponible, reservas sin cambios;
  4. **rechazado** (i, j, k): «rechazado»; sus reservas no liberadas, a «liberada»; cada cosecha «a realizar» de esas reservas, cancelada con
     `cancelar_cosecha_incluida(None, cosecha, motivo="El cliente rechazó el faltante de CV-0044", recubrir=False)` (`cancelar_orden.md`;
     fecha de resolución hoy; aviso al Capataz y al Agrónomo); por cada línea de lote **ya cosechada** con cubierto > 0, una partida
     `rechazo_cantidad_reducida` con `camara.crear_partida`: cantidad = `min(cosechada, reservada)`, `fecha_cosecha` = la de su cosecha,
     `fecha_ingreso` = hoy, costo = `costo_unitario_de_cosecha` (D-64 punto 3) y origen del movimiento = **la compra-venta**;
  5. la venta (c): «abierta» si queda algún detalle no rechazado; «cancelada» si todos quedaron rechazados (sin los datos de MD-130, que son de
     COM-CNL-CVT: quedan vacíos);
  6. el enlace, `usado` (b; con `vendedor`, no se marca: 1a);
  7. `on_commit`: PROD-ASG-CAM con las partidas creadas y las de las líneas de cámara liberadas (l); el acuse al cliente (e).
- **Paso 7 y 7a (m):** planificar la entrega: **se completa en COM-05**.
- **Paso 8 (d, e):** la notificación al Vendedor (dentro de la transacción; salvo en 1a, que decidió él): «El cliente decidió el faltante de
  CV-0044», con la decisión de cada detalle. El acuse al cliente (con `on_commit`): la decisión de cada detalle, la cantidad que recibirá, el
  subtotal y el monto total. 8a: si el acuse falla, la página final igual dice que la decisión quedó registrada (el reintento no aplica: no hay
  cola), y se anota en el log.
- **Paso 9:** «Gracias. Recibimos su decisión.» con lo que recibirá (prototipo `VIEWS.dcd`, `S.p.done`).
- **Extensión 1a (el Vendedor decide en nombre del cliente):** «Comercial» › la ficha de la venta › «Registrar decisión de faltante», o la lista
  de ventas a decidir (1a.2). Ventas de sus contratos en «pendiente de decisión del cliente» cuyo cliente no tiene correo, **cuyo enlace no se
  pudo enviar** (`pendiente_envio`, D-65 punto 6) o cuyo enlace venció; el Gerente también puede (regla «Quién decide» dice «el Vendedor del
  contrato»: **solo el Vendedor**; el Gerente ve la venta pero no el botón). 1a.2a: «No hay ventas de tus contratos esperando una decisión que
  puedas registrar.» Las demás diferencias, las del caso de uso (acuse solo si hay correo, sin notificación al Vendedor, auditoría con su
  usuario).
- **Cliente dado de baja** (regla 2 de 8.18): decide igual. **Venta de un Vendedor que cambió** (D-60): el Vendedor actual del contrato.
- **Auditoría (f):** un registro, acción nueva `decision_faltante`, con `rol_externo="cliente_enlace"` (D-65 punto 8) o, en 1a, el Vendedor; la
  venta y el cliente en `afectados`; los cambios de la venta, los detalles, las reservas y las cosechas; los ids de las partidas y los
  movimientos creados; el enlace usado.
- **Requisitos especiales:** el registro en 5 a 10 segundos (indicador de progreso con HTMX si pasa de 10); dos decisiones de la misma venta se
  ponen en fila en la venta y en el enlace; una asignación de cámara o una merma en cámara sobre las mismas reservas, en la partida o en la
  venta (orden del patrón).

### Lo que completa a COM-02

- **Ficha de la compra-venta** (COM-CNS-CVT, regla 4): muestra «Pendiente de decisión del cliente» con el detalle pendiente, desde qué fecha, el
  plazo del enlace (vence el …) y el estado del envío («El correo no se pudo enviar» o, sin enlace, «El cliente no tiene correo»), y el botón «Registrar
  decisión de faltante» para el Vendedor cuando corresponde (1a). Disparador de COM-02: «vencimiento del enlace (COM-04)».
- **Paso diario 27** (`avisar_enlaces_vencidos`, D-65 punto 7): regla «Vencimiento sin respuesta».

## Pantallas

| Pantalla | Funciones | Notas |
|---|---|---|
| Portal del cliente · Decidir Faltante | `VIEWS.portal`, `INIT.dcd`, `VIEWS.dcd`, `ACT['dcd-ok']` | Página pública, sin menú (`comercial/cliente/base.html`) |
| Registrar decisión (Vendedor) | — (no está en el prototipo) | Misma plantilla que la del cliente dentro del diseño de la aplicación, desde la ficha de la venta |

### Lo que difiere del prototipo (corregir, D-61)

- `VIEWS.dcd` toma **un** detalle pendiente (`c.det.find`): la venta puede tener varios (3b); hace falta una elección por detalle.
- No hay **resumen antes de confirmar** (paso 4) con la advertencia de que no se puede modificar: `dcd-ok` registra directo.
- No muestra los demás detalles de la venta (paso 2), la modalidad ni el monto total nuevo; no contempla la disponible 0 (2b).
- No existe la pantalla de enlace no válido (2a) ni la del Vendedor (1a).
- El texto «responda antes del …» usa `venceEnlace`: en el sistema, la `fecha_vencimiento` del enlace.

## Para más adelante

- COM-05: COM-PNF-ENT después de decidir (paso 7, postcondición m); COM-CNL-CVT anula el enlace de la venta que se cancela.
- Mejoras futuras del caso de uso: esperar otra fecha para recibir la cantidad completa; reenviar el enlace (D-57, sección 6 del plan).
