# Casos de uso · comercial · Rutas y concreción de entregas

Copia para el repo de **COM-INI-RUT · Iniciar Ruta, versión 0.1**, y **COM-CNC-ENT · Concretar Entrega, versión 0.4** (documento de Drive «CU
extendidos», consultado el 22/11/2026), y de **COM-FIN-RUT · Finalizar Ruta, versión 0.1** (documento «CU · COM-FIN-RUT · Finalizar Ruta
(v0.1)», carpeta «InfoPonia · Comercial · Análisis», 20/11/2026; caso de uso de alto nivel). Cotejado con pendientes_CU, con «PCU · Cambios
para pendientes_CU (comercial)» (secciones 6, 8, 9 y 16 los cambian), con el modelo de dominio (reglas 18 a 25 de 8.8; 29, 31 y 32 de 8.6;
13 de 8.9; 5 a 15 de 8.12; 1 a 15 de 8.13; ronda 22) y con «MD · Cambios para el modelo de dominio (comercial)» (MD-115, MD-118, MD-124,
MD-125, MD-132, MD-136 y MD-139). No se copian las «Situaciones encontradas y propuestas» de COM-INI-RUT: ya están aplicadas en su texto y en
MD-118.

**El código va en la app `comercial`** (`comercial/servicios/rutas.py` y `comercial/servicios/concrecion.py`; modelo en
`docs/modelo/comercial.md`: «Entrega», «DetalleEntrega», «PagoCliente», «IntentoFallido», «SolicitudRevision» y «DiscrepanciaEntrega»). Lo
físico de `produccion` (merma, consumo y cámara) lo deja hecho **COM-04a** (`docs/api/produccion.md`, sección 10). Cómo se guarda y cómo
corre: **D-68** (y D-66 para lo que ya hacen las entregas). Tarea: **COM-06a**. La confirmación del cliente y la entrega no reconocida
(COM-CNF-ENT y COM-ATN-ENR) están en `docs/casos_de_uso/comercial/confirmacion.md` (COM-06b). Archivos de pruebas:
`comercial/tests/test_com_ini_rut.py`, `test_com_cnc_ent.py`, `test_com_fin_rut.py`, `test_concrecion_concurrencia.py` y
`test_rutas_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de estos casos de uso no están numeradas (`test_regla_entregas_de_la_ruta_…`), las postcondiciones son
`test_post_<letra>_…` y las extensiones `test_ext_<numero>_…` (`test_ext_4a_…`, `test_ext_10b_…`). COM-FIN-RUT numera sus reglas
(`test_regla_1_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-INI-RUT | Iniciar Ruta | Transportista | `comercial/tests/test_com_ini_rut.py` |
| COM-CNC-ENT | Concretar Entrega (con el intento fallido, 4a, y el retiro, 1a) | Transportista; Vendedor en un retiro | `comercial/tests/test_com_cnc_ent.py` |
| COM-FIN-RUT | Finalizar Ruta (alto nivel) | Transportista | `comercial/tests/test_com_fin_rut.py` |

## COM-INI-RUT · Iniciar Ruta

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Órdenes.

**Actor principal:** Transportista.

**Versión:** 0.1

**Personal involucrado e intereses**

  - Transportista: quiere empezar el reparto del día desde el celular con un solo paso, sabiendo exactamente qué entregas lleva, a qué destinos, con qué peso y cuáles van sin envasado planificado, y quedar habilitado para concretarlas.
  - Vendedor: quiere que las entregas con envío de sus contratos salgan en la fecha programada y que, una vez que salieron, no cambien de transportista ni de contenido sin que nadie lo sepa.
  - Agrónomo: quiere que el envasado que planificó para cada entrega sea el que sale en el vehículo, sin cambios a último momento mientras el producto ya está cargado.
  - Gerente: quiere saber qué transportistas están en ruta, que ninguno reciba entregas nuevas para el día una vez que salió, y que cada inicio de ruta quede registrado con su responsable.
  - Cliente: quiere recibir su pedido en la fecha que se le informó.
  - Organización (Jardín Botánico): quiere que el indicador de vehículo en ruta refleje la realidad del día, porque de él dependen la asignación de transportistas, el envasado y la concreción de las entregas.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Lo preceden: COM-PNF-ENT · Planificar Entrega y COM-ASG-TRP · Asignar Transportista a Entrega, que le asignan al Transportista las entregas con envío que lleva en la ruta; y PROD-PNF-ENV · Planificar Envasado, que reserva los envases de esas entregas.
  - Lo sigue: COM-CNC-ENT · Concretar Entrega, que exige la ruta del día iniciada (precondición b de COM-CNC-ENT), y después Finalizar Ruta (CU-48), que exige que no le queden entregas «a realizar» del día (regla 7 de 8.13).
  - Relacionados, sin inclusión:
  - COM-PNF-ENT · Planificar Entrega y COM-ASG-TRP · Asignar Transportista a Entrega, que no le asignan entregas para el día a un transportista en ruta (regla «Transportista candidato» de COM-PNF-ENT);
  - PROD-PNF-ENV · Planificar Envasado, que no permite cambiar el envasado de una entrega en curso (extensión 3b de PROD-PNF-ENV);
  - Modificar Vehículo (CU-07) y Baja Vehículo (CU-30), que exigen que el vehículo no esté en ruta (Documentación para la IA, precondición c de cada uno).

**Precondiciones**

a. El Transportista está autenticado en el Sistema.

b. El Transportista está en estado «activo».

**Garantías mínimas**

  - La operación es atómica. Si el caso de uso se cancela o falla, el vehículo conserva su indicador de ruta y su fecha de inicio de ruta anteriores, y no se registra ningún log de auditoría parcial.
  - Iniciar la ruta no modifica ninguna entrega (estado, fecha programada, transportista ni detalles), ninguna reserva de stock ni de insumo, el stock de cámara ni de insumos, ni la contabilidad, cualquiera sea la forma en que termine el caso de uso.
  - Ningún transportista queda en ruta sin al menos una entrega con envío «a realizar», asignada a él y con fecha programada igual o anterior a la fecha actual en el momento de registrar.
  - Ningún transportista inicia la ruta con entregas distintas de las que el Sistema le presentó, aun cuando al mismo tiempo se planifiquen, reasignen o cancelen entregas suyas.
  - Solo el Transportista inicia la ruta de su propio vehículo.

**Garantías de éxito (Postcondiciones)**

a. El vehículo asociado al Transportista quedó en ruta: su indicador de ruta pasó a verdadero y su fecha de inicio de ruta quedó igual a la fecha actual.

b. Las entregas de la ruta conservaron su estado («a realizar»), su fecha programada, su transportista, sus detalles y sus reservas de stock y de insumo.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del vehículo y cambio de valor de su indicador de ruta y de su fecha de inicio de ruta.

**Escenario principal de éxito (o Flujo Básico)**

(El Transportista tiene un vehículo activo que no está en ruta, y tiene entregas con envío asignadas para la fecha actual, todas con envasado planificado.)
1. El Transportista inicia la ruta del día.
2. El Sistema presenta el vehículo del Transportista (tipo, marca, modelo y capacidad de carga) y las entregas de la ruta, ordenadas por localidad de destino. Para cada entrega indica:
1. el cliente, el destino y su localidad, y la fecha programada;
2. por cada línea, la variedad y la cantidad planificada;
3. los envases planificados con su cantidad reservada.
3. El Sistema presenta además la cantidad de entregas, la cantidad de localidades distintas y el peso total de la ruta, junto con la capacidad de carga del vehículo.
4. El Transportista confirma que inicia la ruta con esas entregas.
5. El Sistema verifica que el vehículo siga activo, asociado al Transportista y sin una ruta del día iniciada, y que las entregas de la ruta sean las mismas que presentó. Luego, en una única transacción, registra el vehículo en ruta con la fecha actual como fecha de inicio de ruta, y la auditoría correspondiente.
6. El Sistema informa al Transportista que la ruta quedó iniciada y le ofrece concretar la primera entrega con COM-CNC-ENT · Concretar Entrega.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 4, el Transportista cancela el inicio de la ruta:**

1. El Sistema descarta la operación sin registrar ningún cambio. El vehículo sigue sin la ruta del día iniciada.

**\*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:**

1. El Sistema revierte cualquier registro parcial de la operación.
2. Al restablecerse, el Sistema informa al Transportista si la ruta quedó iniciada o no.
3. Si no quedó iniciada, el Transportista reinicia el caso de uso desde el paso 1.

**1a. El Transportista no tiene un vehículo asociado, o su vehículo está «inactivo»:**

1. El Sistema informa que no tiene un vehículo activo para iniciar la ruta y que debe comunicarse con el Gerente, que asigna los vehículos (regla 1 de 8.22).
2. El caso de uso termina.

**1b. El vehículo ya tiene la ruta del día iniciada:**

1. El Sistema informa que la ruta ya está iniciada desde la fecha actual y presenta sus entregas «a realizar».
2. El Sistema le ofrece concretar una entrega con COM-CNC-ENT · Concretar Entrega o, si no le quedan entregas «a realizar» del día, finalizar la ruta con Finalizar Ruta (CU-48).
3. El caso de uso termina.

**1c. El vehículo figura en ruta desde un día anterior (la ruta de ese día no se finalizó):**

1. El Sistema informa la fecha de esa ruta y que ya no está vigente, porque una ruta dura como máximo el día en que se inicia.
2. El caso de uso continúa en el paso 2. En el paso 5, el Sistema reemplaza la fecha de inicio de ruta por la fecha actual.

**2a. El Transportista no tiene entregas con envío «a realizar» asignadas con fecha programada igual o anterior a la fecha actual:**

1. El Sistema informa que no tiene entregas para iniciar la ruta y, si las tiene, la próxima fecha programada de sus entregas.
2. El caso de uso termina.

**2b. Una o más entregas de la ruta tienen la fecha programada anterior a la fecha actual:**

1. El Sistema las presenta primero, indica que están demoradas y cuántos días de retraso tienen.
2. El caso de uso continúa en el paso 3.

**2c. Una o más entregas de la ruta no tienen envasado planificado:**

1. El Sistema las señala e informa que salen sin envases reservados y que, al concretarlas, deberá declarar los envases que use (regla 22 de 8.8; extensión 9a de COM-CNC-ENT).
2. El caso de uso continúa en el paso 3. El inicio de la ruta no se bloquea.

**5a. Al registrar, el vehículo ya tiene la ruta del día iniciada (por ejemplo, el Transportista la inició desde otro dispositivo):**

1. El Sistema no registra ningún cambio e informa que la ruta ya estaba iniciada.
2. El caso de uso termina.

**5b. Al registrar, el vehículo ya no está activo o ya no está asociado al Transportista (por ejemplo, el Gerente lo modificó):**

1. El Sistema no registra ningún cambio e informa la situación del vehículo.
2. El caso de uso termina.

**5c. Al registrar, las entregas de la ruta ya no son las que se presentaron (otra operación le asignó, reasignó o canceló una entrega, o le cambió la fecha), pero le queda al menos una:**

1. El Sistema no registra ningún cambio e informa qué entregas se agregaron y cuáles se quitaron.
2. El caso de uso vuelve al paso 2 con las entregas vigentes.

**5d. Al registrar, el Transportista ya no tiene ninguna entrega de la ruta:**

1. El Sistema no registra ningún cambio e informa que ya no tiene entregas para iniciar la ruta.
2. El caso de uso termina.

**Requisitos especiales**

  - La interfaz del Transportista está pensada para el celular, en «modo campo», como la de COM-CNC-ENT.
  - La presentación de los pasos 2 y 3 y el registro del paso 5 se completan, cada uno, en no más de 2 segundos.
  - El paso 5 se ejecuta como una única transacción: el cambio del vehículo y su log se registran juntos o no se registra ninguno.
  - El control de concurrencia impide iniciar la ruta mientras se registra una planificación o una asignación de transportista que involucra al mismo Transportista en la fecha actual (requisitos especiales de COM-PNF-ENT), mientras se registra el envasado de una de sus entregas (requisitos especiales de PROD-PNF-ENV) o mientras se cancela una de ellas. La operación que llega segunda vuelve a verificar sus condiciones con el resultado de la primera.
  - Solo el Transportista accede al inicio de su propia ruta. El Sistema solo le presenta sus entregas.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio**

  - Quién lo ejecuta: el Transportista, solo sobre el vehículo que tiene asociado (R073). Ni el Gerente ni el Vendedor inician una ruta en su nombre. (Paso 1)
  - Vehículo de la ruta: el vehículo asociado al Transportista, en estado «activo». Un transportista tiene a lo sumo un vehículo, y puede no tener ninguno (R073 en 0..1). (Paso 2 y extensión 1a)
  - Entregas de la ruta: las entregas con envío, en estado «a realizar», asignadas al Transportista (R122) y con fecha programada igual o anterior a la fecha actual. Son las mismas que puede concretar (regla «Entrega concretable» de COM-CNC-ENT; regla 7 de 8.13). Los retiros en invernadero no tienen ruta. (Paso 2 y extensiones 2a y 2b)
  - La ruta lleva todas sus entregas: el Transportista no elige qué entregas lleva. El modelo no registra qué entregas salieron, así que la ruta abarca todas las entregas de la ruta en el momento de iniciarla. Si una entrega no puede salir, el Vendedor o el Gerente la reasignan con COM-ASG-TRP antes del inicio, o el Transportista registra el intento fallido al concretar (extensión 4a de COM-CNC-ENT). (Paso 4)
  - Al menos una entrega: no se inicia una ruta sin entregas, porque el transportista en ruta deja de ser candidato para las entregas del día (regla 5 de 8.12) sin tener nada que repartir. (Extensiones 2a y 5d)
  - Ruta del día: un vehículo está en ruta cuando su indicador de ruta es verdadero y su fecha de inicio de ruta es la fecha actual. Una ruta que no se finalizó deja de estar vigente al terminar el día en que se inició; el día siguiente el Transportista inicia una nueva. Todas las reglas que hablan de un transportista o de un vehículo «en ruta» (COM-PNF-ENT, COM-ASG-TRP, PROD-PNF-ENV, COM-CNC-ENT, Finalizar Ruta, Modificar Vehículo y Baja Vehículo) se leen con esta definición. (Paso 5 y extensiones 1b y 1c)
  - Más de una ruta en el día: después de finalizar la ruta, el Transportista vuelve a ser candidato para las entregas del día (regla 5 de 8.12). Si recibe una, puede iniciar otra ruta ese mismo día. La capacidad de carga y los límites diarios siguen contando todas las entregas no canceladas del día, porque se supone un solo viaje por día (reglas 6 y 7 de 8.12). (Paso 1)
  - Peso de la ruta: suma, por cada línea de cada entrega de la ruta, de la cantidad planificada por el peso promedio por planta de su variedad, en gramos, dividida por 1.000 para expresarla en kilogramos, como la capacidad de carga (regla 6 de 8.12; MD-69). Es informativo: la capacidad ya se controló al asignar cada entrega. (Paso 3)
  - Iniciar no descuenta envases: el inicio de la ruta no es un hito de salida. Los envases ya están apartados del stock libre por sus reservas de insumo, y su consumo se registra al concretar cada entrega, por lo que realmente se usó (decisión de MD-37 en la ronda 18; reglas 20 a 24 de 8.8). (Paso 5)
  - Entregas sin envasado: una entrega sin envasado planificado sale igual; al concretarla se declaran los envases usados y se notifica al Agrónomo (reglas 20 y 22 de 8.8). (Extensión 2c)
  - Entregas en curso: desde el inicio de la ruta, las entregas de la ruta están en curso: no reciben líneas nuevas (regla 2 de 8.12) y su envasado no se modifica (extensión 3b de PROD-PNF-ENV). (Paso 5)
  - Orden de presentación: primero las entregas demoradas y después las demás, agrupadas por localidad de destino. El Sistema no arma un recorrido ni fija horarios, porque la agenda del transportista se controla solo con límites diarios, sin franja horaria (regla 7 de 8.12). (Paso 2 y extensión 2b)

**Lista de tecnología y variaciones de datos**

  - 2. El destino se presenta con su dirección completa: calle y número en una dirección urbana, o ruta, kilómetro y lote en una dirección rural, con su localidad.
  - 3. El peso se expresa en kilogramos con dos decimales, y la capacidad de carga, en kilogramos.

**Frecuencia**

Una vez por día por cada transportista con entregas, y excepcionalmente más de una si recibe entregas para el día después de finalizar su ruta. Depende de la cantidad de transportistas y de entregas con envío; se estima que entre uno y pocos inicios por día en cada invernadero. A confirmar con el Jardín Botánico.

**Temas abiertos**

  - Entrega que no puede salir: si el Transportista ve en el paso 2 una entrega que no puede llevar (por ejemplo, el producto no está listo en la cámara), hoy solo puede pedir que se la reasignen antes de iniciar o registrar después un intento fallido, que la deja sin transportista para el día siguiente. ¿Hace falta que pueda dejarla fuera de la ruta y avisar al Vendedor?
  - Reasignación de una entrega en curso: COM-ASG-TRP permite cambiar el transportista de una entrega «a realizar» aunque el actual esté en ruta con el producto cargado. ¿Debe bloquearse mientras la entrega esté en curso? Hay que resolverlo al especificar COM-ASG-TRP.
  - Cancelación de una entrega en curso: sigue abierto qué pasa con una entrega que se cancela mientras está en el vehículo (temas abiertos de COM-CNC-ENT y de PROD-PNF-ENV). Hay que resolverlo al especificar Cancelar Orden (CU-11).
  - Hora de la ejecución diaria: si el Transportista inicia la ruta antes de la ejecución diaria de COM-PNF-ENT, las entregas del día que esa ejecución consiga asignar ya no pueden ser suyas. Se suma al tema abierto de la hora de esa ejecución (temas abiertos de COM-PNF-ENT y de COM-CNC-ENT).
  - Ruta no finalizada: con la regla «Ruta del día», una ruta que no se finalizó vence sola. ¿Debe avisarse al Gerente cuando un transportista deja una ruta sin finalizar, por ejemplo porque le quedaron entregas sin concretar ni registrar como intento fallido?


## COM-CNC-ENT · Concretar Entrega

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Órdenes.

**Versión:** 0.4

**Actor principal:** Transportista. En un retiro en invernadero, el actor es el Vendedor del contrato.

**Personal involucrado e intereses**

  - Transportista: quiere registrar rápido, desde el celular, lo que entregó, lo que se dañó y lo que el cliente no aceptó, y cobrar el monto correcto sin tener que calcularlo.
  - Vendedor: quiere saber que las entregas de sus contratos se realizaron y enterarse de cualquier pérdida, rechazo, discrepancia o intento fallido. En un retiro, es quien entrega y cobra.
  - Cliente: quiere pagar solo lo que recibió en buen estado y recibir un comprobante. En un suministro, quiere poder confirmar la recepción o presentar una queja.
  - Gerente: quiere que la venta, el costo, las mermas y el cobro queden registrados en el momento en que ocurren (base devengado), y evaluar cada discrepancia de un suministro.
  - Agrónomo: quiere que lo devuelto vuelva a la cámara con su vida útil real y que los envases que no se usaron sigan disponibles en el depósito. También quiere enterarse de todo envase usado de más o sin planificar, y de cualquier inconsistencia que eso deje en el stock de insumos.
  - Organización (Jardín Botánico): quiere cumplir y cerrar sus contratos, y poder rastrear cada planta entregada, perdida o devuelta hasta su lote de origen.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - Lo devuelto a la cámara dispara la asignación automática de cámara.
  - Una entrega que no se pudo realizar queda para la ejecución diaria de COM-PNF-ENT · Planificar Entrega o para COM-ASG-TRP · Asignar Transportista a Entrega.
  - En un suministro, el enlace que envía habilita COM-CNF-ENT · Confirmar Entrega, y la discrepancia que genera se resuelve con COM-EVL-DSC · Evaluar Discrepancia.
  - Confirma el envasado que el Agrónomo planificó con Planificar Envasado (por especificar).
  - La inconsistencia de stock de envases que puede dejar la concreción (extensión 14b) la regulariza el Agrónomo con Ajustar Stock de Insumo (por especificar).
  - Nota: la merma por diferencia en una entrega se registra dentro de este caso de uso y no usa PROD-REG-MRM · Registrar Merma (regla 4 de 8.9).

**Precondiciones**

a. El Transportista está autenticado en el Sistema.

b. El Transportista inició la ruta del día: su vehículo está en ruta.

c. Existe al menos una entrega en estado “a realizar”, asignada al Transportista, con fecha programada igual o anterior a la fecha actual.

d. Existe un ejercicio contable vigente y existen las cuentas contables Ventas, Costo de Producción Vendida, Productos Terminados, Deudores por Ventas, Caja, Banco c/c, Pérdidas por Mermas e Insumos en Stock.

**Garantías mínimas**

  - La concreción es atómica. Si el caso de uso se cancela o falla, la entrega sigue “a realizar”, sus reservas de stock siguen “lista para entrega” y sus reservas de insumo siguen “activa”. Tampoco se registra ningún cambio en stock, cámara, contrato, cobro, contabilidad, alertas, notificaciones ni log de auditoría.
  - Una entrega se concreta una única vez. Nunca se entrega más de lo planificado, y ninguna partida de cámara queda con cantidad negativa.
  - Ningún consumo de envases que supere lo reservado, que no tenga reserva o que deje el stock de un envase negativo o sin cubrir las reservas de otras órdenes se registra sin su notificación o su alerta al Agrónomo del invernadero de origen.
  - Solo concreta la entrega el Transportista asignado o, en un retiro, el Vendedor del contrato.

**Garantías de éxito (Postcondiciones)**

**En toda entrega concretada**

a. La entrega pasó de “a realizar” a “concretada”, con la fecha de resolución igual a la fecha actual.

b. Cada detalle de entrega quedó con su cantidad entregada, su precio unitario (en un suministro, recalculado con la fecha real) y su monto a pagar (cantidad entregada × precio unitario). La entrega quedó con su monto total.

c. Cada reserva de stock de la entrega pasó a “entregada”. En una compra-venta, las reservas de un detalle rechazado pasaron a “liberada”.

d. En cada partida de cámara que aportó a la entrega, la cantidad disponible se redujo en lo que salió en el vehículo, y se registró un movimiento de stock de tipo “egreso de cámara por venta/entrega”, originado en la entrega.

e. Por cada lote de origen con plantas perdidas en el traslado, se registró una merma con causa “daño en la entrega”. La merma tiene la fecha y hora actuales, la cantidad perdida, el actor como responsable y la descripción (si se indicó), y está asociada a ese lote, a la entrega y al invernadero de origen, sin etapa productiva. Cada merma generó un asiento: Debe Pérdidas por Mermas / Haber Productos Terminados, valorizado con el costo de cada origen.

f. Lo devuelto en buen estado volvió a la cámara con motivo “rechazo en la entrega”:
  - si venía de una partida, la cantidad disponible de esa partida aumentó y se conservó su fecha límite;
  - si venía de un lote cosechado, se creó una partida nueva, con fecha límite igual a la fecha de la cosecha más la duración postcosecha de la variedad y costo unitario igual al costo por planta del lote.

Por cada ingreso se registró un movimiento de stock de tipo “ingreso a cámara”, originado en la entrega, y se disparó la asignación automática de cámara.

g. Envases:
  - Cada reserva de insumo de la entrega quedó con su cantidad utilizada y su cantidad devuelta. Pasó a “consumida” si su cantidad consumida (la mayor entre la reservada y la utilizada, menos la devuelta) es mayor que cero, o a “cancelada” si es cero.
  - Si no había envasado planificado, cada envase declarado se registró como consumo directo, sin reserva. Si se declaró que no se usaron envases, no se registró ningún consumo.
  - Por cada consumo:
  - se registró un consumo asociado a la entrega y al insumo del invernadero de origen, con su cantidad y su monto;
  - se descontó la cantidad de los lotes de insumo del envase en el invernadero de origen, primero del lote vigente que vence antes (FEFO) y sin usar lotes vencidos; lo que superó lo disponible quedó como faltante sin lote; el stock actual del insumo, que es la suma de sus lotes, se redujo en esa cantidad;
  - se registró un movimiento de insumo de tipo “salida por consumo”, originado en el consumo, por cada lote de insumo afectado y por el faltante sin lote si se usó;
  - se generó un asiento originado en el consumo: Debe Costo de Producción Vendida / Haber Insumos en Stock.
  - Lo devuelto no generó ningún registro de stock: nunca se descontó y volvió a ser stock libre.
  - Si algún envase superó lo reservado, o la entrega no tenía envasado planificado, se notificó al Agrónomo del invernadero de origen lo reservado y lo utilizado o declarado de cada envase.
  - Si el stock sin lotes vencidos de un envase quedó negativo, o menor que la suma de las reservas activas de otras órdenes, se generó para ese Agrónomo una alerta de «stock inconsistente» en estado “activa”. La alerta identifica el insumo, la entrega y las órdenes cuyas reservas quedaron sin cobertura.

h. Se generó un único asiento compuesto, originado en la entrega, en el libro diario del ejercicio vigente. Si en la entrega no hubo ninguna venta ni cobro, no se generó asiento.
  - Suministro: Debe Deudores por Ventas / Haber Ventas, por el monto total de la entrega.
  - Compra-venta: la venta de sus propios detalles según la regla de venta registrada por entrega.
  - Costo de lo entregado, en ambos casos: Debe Costo de Producción Vendida / Haber Productos Terminados.

i. Si hubo pérdidas, devoluciones, rechazos o una discrepancia, se notificó al Vendedor del contrato.

**En una compra-venta**

j. Cada detalle de venta de la entrega quedó “confirmado”, con su cantidad entregada como cantidad vendida, o “rechazado” si el cliente rechazó lo que llegó.

k. Si fue la última entrega de la venta y quedó al menos un detalle confirmado:
  - se registró el pago del cliente por el total de la venta, con el medio de pago indicado;
  - la venta pasó a “concretada”, con la fecha de concreción igual a la fecha actual;
  - se envió al cliente el comprobante de venta (uso interno).

Si todos los detalles de la venta quedaron rechazados, la venta pasó a “cancelada”, sin cobro ni comprobante.

**En un suministro**

l. La confirmación del cliente de la entrega siguió en “no confirmado”. Se generó un enlace de acceso temporal y se envió al cliente un correo con el enlace y el comprobante de entrega (uso interno), que incluye cantidades, precio, monto y vencimiento del pago.

m. Si uno o más detalles de suministro de la entrega quedaron con una cantidad entregada menor que la cantidad mínima de mercadería de su cláusula, se registró una sola discrepancia de entrega en estado “pendiente de revisión”, asociada a la entrega, con una línea por cada uno de esos detalles, que indica la cantidad entregada y la cantidad mínima estipulada. Se generó una sola alerta para el Gerente.

n. Si con esta entrega se concretaron todas las entregas del último período de un detalle de suministro, el detalle pasó a “finalizado”. Si todos los detalles del contrato quedaron finalizados, el contrato pasó a “finalizado”.

**En una entrega que no se pudo realizar**

o. La entrega siguió “a realizar”, con la fecha programada igual al día siguiente y sin transportista. Sus reservas de insumo siguieron “activa” y no se registró ningún consumo de envases. Se notificó al Vendedor y al cliente el motivo y la nueva fecha.

**Auditoría**

p. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor de cada entrega, detalle de entrega, reserva de stock, reserva de insumo, partida de cámara, insumo del invernadero, detalle de venta, compra-venta, detalle de suministro y contrato modificados.

q. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada merma, partida de cámara, movimiento de stock, consumo, movimiento de insumo, pago, discrepancia, alerta y asiento contable creados.

**Escenario principal de éxito (o Flujo Básico)**

(Compra-venta con envío a domicilio, única entrega de la venta, sin pérdidas ni rechazos.)
1. El Transportista inicia la concreción de una entrega.
2. El Sistema presenta las entregas “a realizar” asignadas al Transportista con fecha programada igual o anterior a la fecha actual. Para cada una indica el cliente, el destino, el tipo de contrato y si está demorada.
3. El Transportista selecciona la entrega.
4. El Sistema presenta el detalle de la entrega: cliente, destino y, por cada línea, la variedad, la cantidad planificada y el precio unitario; además, los envases planificados con su cantidad reservada.
5. El Transportista indica, para cada línea, la cantidad de plantas que llegaron en buen estado.
6. El Sistema verifica las cantidades.
7. El Transportista indica que el cliente acepta lo que llegó de cada línea.
8. El Sistema calcula el monto de cada línea y el monto total de la entrega, determina que es la última entrega de la venta y presenta el total a cobrar.
9. El Transportista indica, para cada envase planificado, la cantidad utilizada y la cantidad devuelta.
10. El Sistema verifica las cantidades de envases.
11. El Transportista indica el medio de pago con que el cliente pagó el total.
12. El Sistema presenta el resumen de la concreción: por línea, las cantidades planificada, entregada, perdida y devuelta y el monto; los envases utilizados y devueltos; y el total cobrado con su medio de pago.
13. El Transportista confirma la concreción.
14. El Sistema registra la entrega como concretada:
  - actualiza los detalles de entrega, las reservas y la cámara;
  - registra los consumos de envases, repartidos entre los lotes de insumo, y el asiento de la entrega;
  - confirma los detalles de venta;
  - registra el pago y pasa la venta a “concretada”;
  - registra la auditoría correspondiente.
15. El Sistema envía al cliente el comprobante de venta (uso interno).
16. El Sistema informa al Transportista que la entrega fue concretada y presenta el total cobrado.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 13, el actor cancela la concreción:**

1. El Sistema descarta los datos ingresados sin registrar ningún cambio y la entrega sigue “a realizar”.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1. El Sistema revierte cualquier registro parcial de la operación.
2. Al restablecerse, el Sistema informa al actor que la entrega no fue concretada.
3. El actor reinicia el caso de uso desde el paso 1. Si no tiene señal, puede registrar la entrega más tarde ese mismo día, antes de finalizar la ruta.

**1a. El actor es el Vendedor y la entrega es un retiro en invernadero:**

1. El Vendedor inicia la concreción de un retiro cuando el cliente se presenta. No se exige ruta iniciada.
2. En el paso 2, el Sistema presenta las entregas de retiro “a realizar” de los contratos del Vendedor, con fecha programada igual o anterior a la fecha actual.
3. El caso de uso continúa en el paso 3 con el Vendedor como actor. En el paso 5, la cantidad en buen estado es la que se entrega en el invernadero. Un retiro es siempre la última y única entrega de la venta, así que siempre se cobra. No aplica la extensión 4a.
4. Si el cliente no se presenta, el Vendedor no inicia el caso de uso: la entrega sigue “a realizar”, demorada. El Vendedor la concreta cuando el cliente se presente, o registra la cancelación de la venta (regla 22 de 8.6).

**3a. La entrega es de un suministro:**

1. En el paso 7, el Transportista indica, para cada línea, cuántas de las plantas que llegaron en buen estado recibió el cliente; el resto son devueltas.
2. En el paso 8, el Sistema recalcula el precio unitario de cada línea con la fecha actual (regla 7 de 8.11) y calcula sus montos. No hay cobro: se omite el paso 11.
3. En el paso 12, el resumen indica el monto total de la entrega y el vencimiento del pago.
4. En el paso 14, el Sistema registra la venta contra Deudores por Ventas, deja la confirmación del cliente en “no confirmado” y genera el enlace de acceso temporal.
5. En el paso 15, el Sistema envía al cliente el correo con el enlace de confirmación y el comprobante de entrega (uso interno).

**4a. El Transportista no puede realizar la entrega (por ejemplo, el cliente está ausente, el domicilio está cerrado o la dirección es incorrecta):**

1. El Transportista indica que no se pudo entregar y el motivo.
2. El Sistema pasa la fecha programada de la entrega al día siguiente y la deja sin transportista, para que la ejecución diaria de COM-PNF-ENT le busque uno. Las reservas de insumo de la entrega siguen “activa”: los envases vuelven con el producto y la misma entrega se reintenta con ellos.
3. El Sistema notifica al Vendedor y al cliente el motivo y la nueva fecha, y registra la auditoría.
4. El caso de uso termina. El intento fallido no es un incumplimiento de la empresa y no suma a la cantidad de incumplimientos del contrato.

**5a. En una línea llegaron en buen estado menos plantas que las planificadas:**

1. El Sistema informa que la diferencia se registrará como pérdida en el traslado.
2. El Transportista confirma la causa “daño en la entrega” y, opcionalmente, una descripción.
3. El caso de uso continúa en el paso 5 o en el paso 7.

**5b. La cantidad indicada no es un número entero entre cero y la cantidad planificada de la línea:**

1. El Sistema señala el error e informa la cantidad planificada.
2. El Transportista corrige la cantidad (vuelve al paso 5).

**7a. En una compra-venta, el cliente rechaza lo que llegó de un detalle:**

1. El Transportista indica que el cliente rechaza esa línea.
2. El Sistema informa que la línea no se cobra, que lo que llegó en buen estado vuelve a la cámara y que el detalle quedará rechazado.
3. El caso de uso continúa en el paso 7 o en el paso 8.

**8a. En una compra-venta, no es la última entrega de la venta (quedan otras entregas “a realizar”):**

1. El Sistema informa que en esta entrega no se cobra y que la venta de sus detalles se registra contra Deudores por Ventas.
2. El caso de uso continúa en el paso 9 y omite el paso 11.

**8b. En una compra-venta, es la última entrega y todos los detalles de la venta quedaron rechazados:**

1. El Sistema informa que la venta quedará cancelada, sin cobro.
2. El caso de uso continúa en el paso 9 y omite el paso 11. En el paso 14, la venta pasa a “cancelada” y en el paso 15 no se envía comprobante.

**9a. La entrega no tiene envasado planificado:**

1. El Sistema advierte que no hay envasado planificado.
2. El actor declara los envases utilizados, con su cantidad, o declara que no utilizó envases.
3. El caso de uso continúa en el paso 10. En el paso 14, el Sistema registra un consumo directo, sin reserva, por cada envase declarado, y notifica al Agrónomo del invernadero de origen que la entrega se concretó sin envasado planificado, con los envases y las cantidades declarados.

**10a. Una cantidad de envases no es válida: la utilizada o la declarada es negativa, o la devuelta es negativa o supera la cantidad máxima a devolver (la reservada menos la utilizada, o cero si se usó más de lo reservado):**

1. El Sistema señala el error e informa, para ese envase, la cantidad reservada y la cantidad máxima que se puede devolver.
2. El actor corrige las cantidades (vuelve al paso 9).

**10b. La cantidad utilizada de un envase supera su cantidad reservada:**

1. El Sistema informa la cantidad reservada, la utilizada y el exceso, y advierte que el exceso se registrará como consumo y se notificará al Agrónomo.
2. El actor confirma la cantidad (el caso de uso continúa en el paso 11, o en el 12 si no hay cobro) o la corrige (vuelve al paso 9).
3. En el paso 14, el Sistema notifica al Agrónomo del invernadero de origen el exceso, con la cantidad reservada y la utilizada de cada envase.

**13a. El actor quiere corregir un dato del resumen:**

1. El actor indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 7, 9 u 11).

**14a. Al registrar, la entrega ya no está “a realizar” o el Transportista ya no es el asignado (por ejemplo, se la reasignaron con COM-ASG-TRP):**

1. El Sistema no registra ningún cambio e informa la situación de la entrega.
2. El caso de uso termina.

**14b. Al registrar, el consumo de un envase deja su stock sin lotes vencidos en el invernadero de origen negativo, o menor que la suma de las reservas activas de otras órdenes:**

1. El Sistema registra la concreción completa, sin bloquearla. Lo que supera lo disponible en los lotes de insumo queda como faltante sin lote.
2. El Sistema genera una alerta de «stock inconsistente» para el Agrónomo del invernadero de origen. La alerta identifica el insumo, la entrega y las órdenes cuyas reservas quedaron sin cobertura, y queda activa hasta que el stock sin lotes vencidos vuelva a cubrirlas.
3. El caso de uso continúa en el paso 15. No se informa al actor, porque no puede corregir la situación.

**14c. En un suministro, la cantidad entregada de uno o más detalles es menor que la cantidad mínima de mercadería de su cláusula, aunque la diferencia venga de un rechazo del cliente:**

1. El Sistema registra una sola discrepancia de entrega en estado “pendiente de revisión”, con una línea por cada detalle por debajo del mínimo, y genera una alerta para el Gerente.
2. El Sistema notifica la discrepancia al Vendedor del contrato.

**15a. El Sistema no logra enviar el correo al cliente o una notificación:**

1. La concreción permanece registrada.
2. El Sistema reintenta el envío.

**Requisitos especiales**

  - La interfaz del Transportista está pensada para el celular, en “modo campo”.
  - Tras cada dato ingresado por el actor (pasos 3 a 11), la pantalla se actualiza con las verificaciones y los montos calculados en no más de 1 segundo.
  - El registro del paso 14 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El paso 14 se ejecuta como una única transacción.
  - El control de concurrencia impide que una entrega se concrete dos veces, o que se concrete mientras se le reasigna el transportista.
  - El Transportista solo ve y concreta sus entregas. El Vendedor solo concreta los retiros de sus contratos.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios y montos se expresan en pesos argentinos, con dos decimales.
  - Los comprobantes de entrega y de venta son de uso interno y no tienen validez fiscal.
  - El enlace de acceso temporal enviado al cliente es de uso único, y su vigencia son los días que fija la configuración operativa (diasVigenciaEnlaceConfirmacion), la misma que controla COM-CNF-ENT · Confirmar Entrega.
  - El PMV supone conexión al registrar. El registro sin conexión queda como mejora futura.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**

  - Entrega concretable: en estado “a realizar”, con fecha programada igual o anterior a la fecha actual. Con envío, la concreta el Transportista asignado, con la ruta del día iniciada; sin transportista no se puede concretar. En un retiro, la concreta el Vendedor del contrato. (Pasos 2 y 3)
  - Fecha real: la fecha de resolución de la entrega es la fecha del registro, sin fechas retroactivas. (Paso 14)
  - Cantidades de una línea: enteros iguales o mayores que cero, que cumplen entregadas + perdidas + devueltas = cantidad planificada. Lo que no llegó en buen estado es pérdida. (Pasos 5 a 7)
  - Aceptación en una compra-venta: el cliente acepta todo lo que llegó en buen estado de una línea, o lo rechaza todo; no hay rechazo parcial. Si acepta, lo vendido es lo que llegó. Si rechaza, lo que llegó vuelve a la cámara. (Paso 7 y extensión 7a)
  - Recepción en un suministro: el cliente puede recibir una parte de lo que llegó; el resto se devuelve. (Extensión 3a)
  - Reparto entre orígenes: si una línea toma stock de varios orígenes (lotes cosechados o partidas de cámara), lo perdido y lo devuelto se reparten en proporción a lo que aporta cada origen. (Paso 14)
  - Primero se reparte lo perdido y después lo devuelto, este último en proporción a lo que le queda a cada origen.
  - Cada origen recibe la parte entera de su cuota. Las unidades que faltan se asignan de a una a los orígenes con mayor parte decimal. Si empatan, al que más aporta; si siguen empatados, al de fecha límite más próxima.
  - Lo entregado de cada origen es lo que le queda.
  - Si la línea tiene un solo origen, no hay reparto.
  - Costo de lo entregado, perdido o devuelto: cada parte se valoriza con el costo de su origen, sin costos promedio: plantas × costo por planta del lote, si es un lote cosechado, o plantas × costo unitario de la partida, si es de cámara. (Paso 14)
  - Merma de entrega: una por cada lote de origen afectado, con causa “daño en la entrega”, sin etapa productiva y asociada a la entrega. No libera agujeros, porque el producto ya fue cosechado. (Paso 14 y extensión 5a)
  - Lo devuelto a la cámara: conserva su vida útil. Si viene de una partida, vuelve a esa misma partida. Si viene de un lote cosechado, se crea una partida por cada cosecha de origen, con fecha límite igual a la fecha de la cosecha más la duración postcosecha de la variedad. Si esa fecha ya pasó, la partida vence (regla 31 de 8.6). (Paso 14)
  - Precio y montos: el precio unitario de compra-venta es el del detalle de venta. El de suministro se recalcula con la fecha real (regla 7 de 8.11). El monto a pagar de una línea es la cantidad entregada por el precio unitario, y el monto total es la suma de las líneas. (Paso 8)
  - Venta registrada por entrega (compra-venta): cada entrega registra la venta de sus propios detalles confirmados. Si no es la última, la registra contra Deudores por Ventas. La última cobra el total de la venta, con Caja o Banco por todo, y cancela lo acumulado en Deudores por Ventas. Con una sola entrega, el asiento es Caja o Banco contra Ventas. (Paso 14 y extensión 8a)
  - Última entrega de una venta: la que se concreta cuando ya no quedan otras entregas “a realizar” de esa venta. (Paso 8)
  - Medio de pago: efectivo, transferencia, tarjeta de débito o tarjeta de crédito. El efectivo se registra en Caja; los demás, en Banco c/c. Se supone que todo lo que no es efectivo se acredita en el momento, sin tarjetas a cobrar ni comisiones. (Paso 11)
  - Asiento de la entrega: uno solo por entrega, compuesto: venta (o cobro) más costo de lo entregado. Las mermas y los consumos de envases originan sus propios asientos. (Paso 14)
  - Estado del detalle de venta: queda “confirmado” si el cliente aceptó al menos una de sus líneas, y su cantidad vendida es la suma de lo aceptado. Queda “rechazado” si se rechazaron todas sus líneas. Si todos los detalles de la venta quedan rechazados, la venta pasa a “cancelada” al concretarse su última entrega. (Paso 14 y extensión 8b)
  - Discrepancia de suministro: si la cantidad entregada de uno o más detalles es menor que la cantidad mínima de mercadería de su cláusula, se genera una sola discrepancia por entrega, con una línea por cada uno de esos detalles, y una sola alerta para el Gerente, aunque la diferencia venga de un rechazo del cliente. El Gerente decide si hubo incumplimiento. (Extensión 14c)
  - Retraso en un suministro: no dispara nada automático; se trata con una queja del cliente. (Paso 14)
  - Cierre del suministro: un detalle pasa a “finalizado” cuando se concretan todas las entregas de su último período; el contrato, cuando todos sus detalles están finalizados. Una queja posterior sigue siendo posible y puede generar una indemnización, pero no cambia el estado del contrato. (Paso 14)
  - Envases: confirmarlos es obligatorio (regla 20 de 8.8). Con envasado planificado, el actor indica, para cada envase, la cantidad utilizada y la devuelta. El Sistema propone como devuelta la reservada menos la utilizada (o cero, si se usó más de lo reservado), y el actor solo puede bajarla: lo que baja se dañó o se perdió. Sin envasado planificado, el actor declara los envases usados o declara que no usó ninguno. Las cantidades no se contrastan con el stock del invernadero, porque el hecho ya ocurrió. (Pasos 9 y 10, extensiones 9a, 10a y 10b)
  - Entrega no realizada : pasa al día siguiente, sin transportista, y se avisa al Vendedor y al cliente. Sus reservas de insumo siguen activas (regla 8 de 8.13). No hay límite automático de intentos, y el intento fallido no es incumplimiento de la empresa. (Extensión 4a)
  - Cantidad consumida de un envase : la mayor entre la cantidad reservada y la utilizada, menos la devuelta (regla 24 de 8.8 y regla 13 de 8.9). Es lo que sale del stock y lo que se valoriza en el consumo. Sale de los lotes de insumo del envase: primero el lote vigente que vence antes (FEFO), sin usar lotes vencidos, y lo que supera lo disponible queda como faltante sin lote (MD-84 y MD-85). Lo devuelto nunca salió del stock: vuelve a estar libre sin generar registros. Si la cantidad consumida es cero, la reserva se cancela. (Paso 14)
  - Exceso de envases: si se usó más de lo reservado, la devuelta es cero, el actor confirma la cantidad y se notifica al Agrónomo (regla 21 de 8.8). (Extensión 10b)
  - Envases sin envasado planificado : se registran como consumo directo, sin reserva (R148), y se notifica al Agrónomo (reglas 20 y 22 de 8.8). (Extensión 9a)
  - Stock de envases inconsistente : si el consumo deja el stock sin lotes vencidos negativo o sin cubrir las reservas activas de otras órdenes, la concreción se registra igual y se alerta al Agrónomo. La alerta queda activa hasta que el stock sin lotes vencidos vuelva a cubrirlas (regla 6 de 8.13), y el Agrónomo lo regulariza con Ajustar Stock de Insumo. No se le avisa al actor. (Extensión 14b)

**Lista de tecnología y variaciones de datos**

**5a. Las cantidades se expresan en plantas, como números enteros. El Sistema propone por defecto la cantidad planificada de cada línea.**

**4a. El motivo de una entrega no realizada se elige de una lista (cliente ausente, domicilio cerrado, dirección incorrecta, otro), con una descripción opcional.**

**9a. La cantidad de cada envase se expresa en la unidad de medida del insumo.**

**11a. El medio de pago se elige de la lista: efectivo, transferencia, tarjeta de débito o tarjeta de crédito.**

**15a. El comprobante de venta incluye las cantidades vendidas por variedad, los precios, el total cobrado y el medio de pago. El comprobante de entrega de un suministro incluye cantidades, precio, monto y vencimiento del pago. Ambos aclaran que son de uso interno, sin validez fiscal.**

**Frecuencia:** una vez por cada entrega planificada, varias veces por día y por transportista. Depende de la cantidad de ventas y de contratos de suministro vigentes.

**Temas abiertos**

  - ¿Qué pasa si el cliente de una compra-venta no puede pagar el total en el momento de la entrega?
  - La ejecución diaria de COM-PNF-ENT debería ejecutarse antes del inicio de las rutas, para que una entrega pasada al día siguiente reciba transportista a tiempo. Esto se suma al tema abierto de la hora de esa ejecución.
  - Una compra-venta con retiro que el cliente no viene a buscar sigue “a realizar” y su producto puede vencer mientras tanto. ¿Debería avisarse al Vendedor cuando se acerca la fecha límite del producto reservado?
  - Este caso de uso asume que la merma de entrega no suma a la merma acumulada del lote para el umbral de merma, porque ese umbral mide la pérdida durante la producción. ¿Es correcto?
  - Si se cancela una entrega cuyo producto ya se envasó (Cancelar Orden, CU-11), sus reservas de insumo se cancelan y los envases usados no se registran como consumo. ¿Debe la cancelación pedir que se confirmen los envases usados?


## COM-FIN-RUT · Finalizar Ruta

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos», sección «Casos de uso de alto nivel».
Decisión E del 20/11/2026 aplicada: si la ruta no se finaliza, vence sola al terminar el día y la ejecución diaria de COM-PNF-ENT avisa al
Vendedor y al Gerente por las entregas que quedaron con la fecha vencida.

**Actores:** Transportista.

**Tipo:** primario, esencial.

**Versión:** 0.1

**Objetivo:** marcar como terminada la ruta del día, después de concretar las entregas o de registrar las que no pudieron hacerse.

**Precondición**

a. El actor está identificado en el Sistema con una cuenta activa de Transportista.

b. Su vehículo está en ruta: inició la ruta hoy y no la finalizó (MD-118).

**Postcondición**

a. El vehículo dejó de estar en ruta.

b. Si el Transportista registró intentos fallidos desde este caso de uso, cada una de esas entregas siguió «a realizar», con la fecha
programada en el día siguiente y sin transportista. Además, se notificó el motivo y la nueva fecha al Vendedor y al cliente, igual que en
COM-CNC-ENT, extensión 4a.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del vehículo, el cambio de su indicador de ruta y cada intento
fallido registrado.

**Reglas**

1. No se finaliza la ruta con entregas «a realizar» de la ruta (regla 7 de 8.13). El Sistema las muestra y ofrece, para cada una, registrar
   el intento fallido desde acá, con el motivo de la lista de COM-CNC-ENT (cliente ausente, domicilio cerrado, dirección incorrecta u otro) y
   una descripción opcional. También puede volver a Concretar Entrega.
2. El intento fallido registrado desde acá tiene el mismo efecto que en COM-CNC-ENT, extensión 4a. No es un incumplimiento de la empresa y
   sus reservas de envases siguen activas.
3. Al finalizar, el Transportista vuelve a ser candidato para las entregas del día. Si recibe una, puede iniciar otra ruta ese mismo día
   (COM-INI-RUT, regla «Más de una ruta en el día»). La capacidad y los límites diarios siguen contando todas las entregas del día.
4. Si el Transportista no finaliza, la ruta vence sola al terminar el día (MD-118). Las entregas que dejó sin concretar ni registrar siguen
   asignadas a él, con la fecha vencida, y la ejecución diaria de COM-PNF-ENT avisa una vez al Vendedor del contrato y al Gerente para que
   las reasignen con COM-ASG-TRP.
5. Lo ejecuta solo el Transportista, sobre su propio vehículo. Ni el Gerente ni el Vendedor finalizan una ruta en su nombre.

## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| PCU, sección 6 (MD-124) | La postcondición l y la regla del vencimiento citan la cláusula del suministrado **del contrato** (una por contrato) | COM-CNC-ENT, postcondición l; «Cómo se aplica», «Montos» |
| PCU, sección 8 | COM-INI-RUT cierra dos temas abiertos: una entrega en curso no se reasigna (la salida es el intento fallido, ya en COM-ASG-TRP 3a, COM-05b) y la ruta no finalizada vence sola, con el aviso de COM-PNF-ENT (paso 50, ya en COM-05a1). COM-CNC-ENT no cambia: COM-FIN-RUT reutiliza su extensión 4a | COM-INI-RUT, «Temas abiertos»; COM-FIN-RUT |
| PCU, sección 9 (MD-132) | Al concretar una entrega de suministro se **fija** su fecha de vencimiento de pago, con el plazo vigente en ese momento | COM-CNC-ENT, paso 14 |
| MD-118 | `Vehiculo.fechaInicioRuta` y la definición de «en ruta» (ya en COM-01) | COM-INI-RUT y COM-FIN-RUT |
| MD-139 | «En mora» en lugar de «vencida» para el pago; «atrasada» para una entrega con la fecha pasada | Los textos de las pantallas |
| MD-85 | Concretar Siembra adopta el criterio de la entrega: el consumo de envases no se bloquea por el stock | Ya es el criterio de COM-CNC-ENT (regla «Stock de envases inconsistente») |
| D-68 | Corte de COM-06, exceso de envases (opción A), núcleo de `produccion` en COM-04a, `PagoCliente` en esta tarea, `IntentoFallido`, montos de la entrega | Toda la sección siguiente |

## Cómo se aplica en la ronda «Comercial 1» (COM-06a; D-44, D-57, D-66, D-68)

### Qué entra y qué no

- **Entra:** los tres casos de uso completos, con el retiro (1a) y el intento fallido (4a); la discrepancia de entrega (14c) con su alerta;
  el pago de una compra-venta (`PagoCliente`, D-68 punto 4); el fin del detalle y del suministro por entrega (postcondición n); la cámara
  (egreso, devolución, partida vencida, PROD-VNC-CAM 3b, «partida por vencer» resuelta); los registrantes de `transportista_en_ruta`.
- **Fuera de esta ronda · contabilidad** (D-57): la precondición d de COM-CNC-ENT (ejercicio y cuentas), el asiento de la entrega
  (postcondición h), el de cada merma (e) y el de cada consumo (g). El código deja todo lo que esos asientos necesitan (montos, costos de cada
  origen en los movimientos) y no crea asientos.
- **COM-06b:** el enlace de confirmación (postcondición l, 3a.4 y 3a.5: el correo de la concreción sale **sin enlace** hasta COM-06b; D-68,
  punto 1), COM-CNF-ENT y COM-ATN-ENR.
- **COM-07:** resolver la discrepancia (COM-EVL-DSC). **COM-08:** el cobro de una entrega de suministro, el estado de pago con «pagada» y la
  alerta «pago en mora» (COM-VNC-PAG).

### Servicios

| Función | Caso de uso | Qué hace |
|---|---|---|
| `rutas.ruta_del_dia(actor) -> RutaDelDia` | COM-INI-RUT, pasos 1 a 3 (y 1a, 1b, 1c, 2a, 2b, 2c) | Lectura: el vehículo, la situación (`sin_vehiculo`, `en_ruta`, `ruta_vencida`, `lista`), las entregas de la ruta ordenadas (regla «Orden de presentación»), con días de retraso y si tienen envasado, la cantidad, las localidades distintas, el peso (`peso_de_entregas`, COM-05a1) y la capacidad, la próxima fecha si no hay entregas (2a) y la **huella** (ids y fechas programadas de las entregas, ordenados) |
| `rutas.iniciar_ruta(actor, huella) -> Vehiculo` | COM-INI-RUT, paso 5 | Ver «Iniciar la ruta» |
| `rutas.finalizar_ruta(actor) -> Vehiculo` | COM-FIN-RUT | Ver «Finalizar la ruta» |
| `rutas.registrar_intento_fallido(actor, entrega_id, motivo, descripcion) -> IntentoFallido` | COM-CNC-ENT 4a y COM-FIN-RUT, regla 1 | Ver «Intento fallido». Una función para los dos casos de uso (regla 2 de COM-FIN-RUT) |
| `concrecion.entregas_concretables(actor) -> list` | COM-CNC-ENT, paso 2 y 1a.2 | Las del Transportista (con envío) o las de retiro de los contratos del Vendedor, con fecha programada `<= hoy`, «a realizar»; cliente, destino, tipo de contrato, demorada |
| `concrecion.datos_de_concrecion(post) -> DatosDeConcrecion` y `concrecion.resumen_de_concrecion(actor, entrega_id, datos) -> ResumenDeConcrecion` | Pasos 4 a 12 | No escriben. El resumen trae lo propuesto (cantidades planificadas, devuelta propuesta de cada envase), los errores por campo (5b, 10a), las advertencias (5a, 7a, 8a, 8b, 9a, 10b), los montos, si es la última de la venta, el vencimiento (suministro) y la **huella** de la concreción |
| `concrecion.concretar_entrega(actor, entrega_id, datos, huella) -> Entrega` | Paso 14 | Ver «Concretar». Una transacción |
| `entregas.monto_a_cobrar(entrega_ids)` y `entregas.estado_de_pago(entrega_ids, hoy)` | (lectura) | D-68, punto 7. Una consulta por tabla |
| `concrecion.intentos_fallidos(entrega_ids) -> dict[int, list[IntentoFallido]]` | (lectura) | Para la ficha de la entrega, COM-ATN-ENR (COM-06b) y COM-RSV-QJA (COM-07) |

Todas reciben al actor, verifican su rol y que siga activo **después de bloquear**, y lanzan `ErrorComercial(codigo, mensaje, campo=None)`.
Códigos nuevos: `sin_vehiculo`, `vehiculo_inactivo`, `ruta_ya_iniciada`, `sin_entregas_de_ruta`, `ruta_cambio` (5c, con lo agregado y lo
quitado), `ruta_no_iniciada`, `ruta_con_entregas_pendientes`, `entrega_no_concretable` (14a), `cantidad_invalida`, `envase_invalido`,
`medio_de_pago_obligatorio`, `motivo_obligatorio`; y los comunes `cambio_simultaneo` y `sin_permiso`.

### Iniciar la ruta (COM-INI-RUT)

- **Entregas de la ruta** (regla del caso de uso): con envío, «a realizar», `transportista = actor`, `fecha_programada_orden <= hoy`. Son las
  mismas que `entregas_concretables` le muestra al Transportista. **Peso de la ruta:** `peso_de_entregas` (COM-05a1) de esas entregas,
  sumado, informativo.
- **Paso 5, en este orden** (`docs/patrones/bloqueos.md`, «Entregas y envasado», «Iniciar y finalizar la ruta»): la cuenta del
  Transportista → **el invernadero de su `TransportistaInvernadero`** (`bloquear_invernadero_activo`, D-66 punto 11: es el semáforo de las
  planificaciones, asignaciones, envasados y cancelaciones de sus entregas) → **el vehículo** → las entregas de la ruta, releídas. Con todo
  tomado: 5b (vehículo inactivo o de otro: `vehiculo_inactivo`), 5a (`esta_en_ruta(hoy)`: `ruta_ya_iniciada`), 5d (ninguna:
  `sin_entregas_de_ruta`), 5c (la huella no coincide: `ruta_cambio` con lo agregado y lo quitado; la pantalla vuelve al paso 2).
- Efecto: `en_ruta = True`, `fecha_inicio_ruta = hoy` (1c reemplaza una fecha vieja). **No toca ninguna entrega ni reserva** (garantía
  mínima). Un registro de auditoría `inicio_ruta` con el vehículo como afectado, `cambios` de `en_ruta` y `fecha_inicio_ruta`, y en `datos`
  los códigos de las entregas de la ruta.
- Un transportista sin invernadero no tiene entregas (MD-138): 2a.
- **Desde que la ruta se inicia, sus entregas están «en curso»** (`en_curso`, COM-05a1): COM-ASG-TRP las rechaza (3a, COM-05b), el envasado
  no cambia (3b de PROD-PNF-ENV, COM-05a2), COM-CNL-CVT no cancela la venta (COM-05b) y COM-PNF-ENT no le agrega líneas ni le asigna
  entregas del día (COM-05a1). Esta tarea **prueba esos cuatro con una ruta iniciada de verdad** (antes se probaban con la fábrica).

### Concretar (COM-CNC-ENT)

- **Quién:** con envío, el Transportista asignado con la ruta del día iniciada (`esta_en_ruta(hoy)`, precondición b; si no,
  `ruta_no_iniciada`); con retiro (1a), el Vendedor del contrato, sin ruta. El Gerente no concreta (regla «Entrega concretable»).
- **Orígenes de una línea:** las `DetalleReserva` de sus reservas no liberadas: líneas de **lote** (producto cosechado por su cosecha: la
  cantidad que aporta es la cosechada que le quedó a la línea) y de **partida** (la cantidad de la línea). La planificada de la línea es la
  suma (COM-05a1).
- **Verificación de cantidades** (pasos 5 a 7, 5b): enteros `>= 0` con `llegó <= planificada`. En una compra-venta, la línea se acepta o se
  rechaza entera (7a): aceptada, `entregada = llegó` y `devuelta = 0`; rechazada, `entregada = 0` y `devuelta = llegó`. En un suministro
  (3a), `recibió <= llegó`: `entregada = recibió` y `devuelta = llegó − recibió`. Siempre `perdida = planificada − llegó` (5a: la causa es
  `dano_en_entrega`, con descripción opcional; una por entrega, la misma para todas las mermas).
- **Reparto entre orígenes** (regla «Reparto entre orígenes»; una función pura, `concrecion.repartir(orígenes, perdida, devuelta)`): primero
  lo perdido, en proporción a lo que aporta cada origen; después lo devuelto, en proporción a lo que le queda a cada uno. Cada origen recibe
  la parte entera de su cuota; las unidades que faltan, de a una, a los de mayor parte decimal; si empatan, al que más aporta; si siguen
  empatados, al de fecha límite más próxima (la de la partida, o la de la cosecha más la postcosecha en una línea de lote) y, por último,
  al de menor id (para que sea determinista). Lo entregado de cada origen es lo que le queda. Con un solo origen no hay reparto.
- **Paso 14, en este orden de bloqueos** (`docs/patrones/bloqueos.md`, «Concretar una entrega»): cuentas (el actor, el Vendedor del
  contrato y el Agrónomo del invernadero de origen) → el **invernadero de origen** (`bloquear_invernadero_activo`) → las variedades → los
  **lotes** de origen → las **partidas** de origen → el **contrato** → sus detalles (de venta o de suministro) → la **entrega**
  (`OrdenTrabajo`) → sus líneas y sus **reservas de stock** con sus `DetalleReserva` → los `InsumoInvernadero` de los envases (reservados y
  declarados, en orden de id) y sus lotes (`docs/patrones/stock.md`, sección 5) → las **reservas de insumo** de la entrega. Con todo tomado
  se relee y se verifica: 14a (`entrega_no_concretable`: ya no está «a realizar» o el actor ya no es su Transportista o el Vendedor del
  contrato) y la **huella** (líneas, reservas no liberadas con sus orígenes y cantidades, y reservas de insumo activas con sus cantidades: si
  cambió algo, `cambio_simultaneo` y la pantalla vuelve al paso 4). En un retiro, el envasado puede cambiar mientras el Vendedor carga los
  datos (no está «en curso»): lo detecta la huella (`envasado.md`, «Retiro en concreción»).
- **Lo que registra, con el núcleo de `produccion`** (sección 10 de `docs/api/produccion.md`; ninguna función de núcleo audita):
  1. por cada origen de **partida**: `egresar_de_partida(partida, aporte, entrega)` (postcondición d; «lo que salió en el vehículo» es lo que
     aportó, también lo que después vuelve);
  2. por cada **lote** de origen con plantas perdidas (sumando las de sus líneas de lote y las de las partidas de ese lote, R144):
     `aplicar_merma_de_entrega(entrega, lote, perdidas, descripcion, actor)` (postcondición e);
  3. lo **devuelto** (postcondición f): de una partida, `devolver_a_partida(partida, devuelta, entrega, hoy)` (si la partida ya venció, el
     núcleo lo registra como merma por vencimiento: regla 29 de 8.6); de una línea de lote, una partida nueva por cada (cosecha, lote) con
     `camara.crear_partida(lote, devuelta, "rechazo_en_entrega", fecha_cosecha=<la de la cosecha de la reserva>, fecha_ingreso=hoy,
     costo_unitario=<costo_unitario_de_cosecha>, origen=entrega)`, y si su fecha límite ya pasó, enseguida `camara.vencer_partida(partida,
     hoy)` (regla «Lo devuelto a la cámara»: «la partida vence»);
  4. las **reservas de stock**: `entregada`; en una compra-venta, las de un detalle **rechazado** (todas sus líneas de esta entrega rechazadas
     y ninguna aceptada en otra), `liberada` (postcondición c);
  5. las **líneas**: `cant_entregada`, `cant_perdida`, `cant_devuelta`, `precio_unitario` (en un suministro, `precio_en(detalle, hoy)` de
     COM-03: regla 7 de 8.11) y `monto_pagar`; la **entrega**: `monto_total_entrega`, `estado_orden = concretada`, `fecha_resolucion_orden =
     hoy` (la escribe `comercial`: la entrega es su hija, como al crearla) y, en un suministro, `fecha_vencimiento_pago = hoy +
     contrato.clausula_suministrado.plazo_pago_dias` (MD-124, MD-132);
  6. los **envases** (D-68, punto 2): por cada reserva de insumo activa, `cerrar_reserva(reserva, mín(utilizada, reservada), devuelta)` y, si
     `máx(reservada, utilizada) − devuelta > 0`, `registrar_consumo_de_orden(entrega, insumo, esa cantidad, hoy, actor)`; sin envasado (9a),
     un `registrar_consumo_de_orden` por envase declarado con cantidad mayor que 0 (ninguno si declaró que no usó); después,
     `reevaluar_alertas_del_insumo` de cada insumo tocado (14b: la alerta «stock inconsistente» la crea `inventario`; no se le avisa al
     actor). La devuelta propuesta es `máx(0, reservada − utilizada)` y el actor solo puede bajarla (regla «Envases»); los envases declarados
     en 9a son los de la categoría del sistema `envases` habilitados en el invernadero de origen (la misma lista de PROD-PNF-ENV);
  7. **compra-venta:** cada detalle de venta de la entrega pasa a `confirmado` con `cant_entregada_venta` = la suma de lo aceptado en todas
     sus entregas concretadas, o a `rechazado` si se rechazaron todas sus líneas (regla «Estado del detalle de venta»). Si es la **última**
     entrega de la venta (no quedan otras «a realizar» de esa venta, regla «Última entrega») y quedó al menos un detalle confirmado: un
     `PagoCliente` (medio del paso 11, `fecha_pago = hoy`, `monto_pagado` = el total de la venta), la venta a `concretada` con
     `fecha_concrecion_venta = hoy` y el comprobante de venta con `on_commit`. Si todos quedaron rechazados (8b), la venta a `cancelada`, sin
     pago ni comprobante (**no** es una cancelación de COM-CNL-CVT: no carga los datos de MD-130). Un retiro es siempre la última y única
     entrega (1a.3): siempre cobra, salvo 8b;
  8. **suministro:** la discrepancia (14c, abajo); el **fin del detalle y del contrato** (postcondición n; disparador «Cuando exista
     Entrega», punto 5): si con esta entrega quedaron concretadas todas las entregas del **último período** de un detalle (el de
     `fecha_fin_detalle`, o el último del contrato si no tiene), el detalle pasa a `finalizado`; si todos los detalles del suministro quedaron
     `finalizado`, el suministro también. La confirmación del cliente sigue `no_confirmado` (la entrega nace así, COM-05a1);
  9. **cámara:** `asignar_camara(partida_ids)` con `transaction.on_commit` (D-64 punto 9) con las partidas que crecieron o nacieron y no
     vencieron; `resolver_aviso_de_partida(partida)` (COM-04b) de cada partida que quedó `agotado`.
- **Auditoría:** un registro `concrecion_entrega` (D-36) con todo lo modificado y lo creado (postcondiciones p y q): la entrega, sus líneas,
  las reservas de stock y de insumo, las partidas, los detalles y el contrato tocados, y en `datos` las mermas, los movimientos, los
  consumos, el pago, la discrepancia y su alerta, y la utilizada **declarada** de cada envase (la real, aunque la reserva guarde la topeada).
- **Avisos** (D-42: dentro de la transacción, `core.notificaciones`): al Vendedor del contrato si hubo pérdidas, devoluciones, rechazos o
  discrepancia (postcondición i; un aviso con todo); al Agrónomo del invernadero de origen si algún envase superó lo reservado (10b.3) o no
  había envasado (9a.3), con lo reservado y lo utilizado o declarado de cada uno. Textos: «OT-0231 · se concretó con diferencias: 5 perdidas,
  10 devueltas (Lechuga Crespa)», «OT-0231 · se usaron 12 Bandejas, reservadas 10 (2 de más)».
- **Correos al cliente** (con `core.correo.enviar_correo` y el `Destinatario` de COM-02, siempre con `transaction.on_commit`; el resultado en
  `Entrega.estado_aviso_cliente`, D-66 punto 12; un cliente sin correo queda `sin_correo` y la pantalla final ofrece el comprobante para
  imprimir): el **comprobante de venta** (uso interno: cantidades vendidas por variedad, precios, total cobrado y medio; 15a) con
  `comercial/servicios/comprobantes.py` (COM-02), y en un suministro el **comprobante de entrega** (cantidades, precio, monto y vencimiento
  del pago; **sin enlace** hasta COM-06b). 15a: si el correo falla, la concreción queda y el paso 50 lo reintenta: su parte 4 («Correos
  pendientes», `entregas.md`) hoy mira solo las entregas «a realizar»; COM-06a le suma las **concretadas** con `pendiente_envio` (vuelve a
  mandar el comprobante de venta o de entrega).
- **Discrepancia (14c; regla 12 de 8.13; D-68 punto 5):** con `concrecion.crear_discrepancia(entrega, lineas)` dentro de la transacción,
  que usa `solicitudes.crear_solicitud` (`comercial/servicios/solicitudes.py`: la única función que crea una `SolicitudRevision` y escribe su
  `entrega` y su número; la usa también COM-06b para las quejas):
  una `DiscrepanciaEntrega` «pendiente» con `fecha_solicitud = hoy` y una `LineaDiscrepancia` por cada detalle con `cant_entregada <
  clausula_suministrante.cantidad_minima` (con la entregada y la mínima copiadas), **aunque la diferencia venga de un rechazo del cliente**;
  la alerta `comercial_discrepancia_entrega` (destinatario `GERENTE`, `ADVERTENCIA`, `Clase.EVENTO`, origen `SOLICITUD_REVISION`;
  `crear_alerta_de_evento` del invernadero de origen) con su `AlertaComercial(solicitud=…)`; el aviso al Vendedor (14c.2, dentro del de la
  postcondición i). Descripción: «OT-0231 · SR-0012: 80 plantas de Lechuga Crespa, mínimo 100». Enlace de la alerta (MAE-02d): la ficha
  del suministro (COM-03a, donde están sus entregas; no hay ficha de una entrega sola) hasta COM-07, que lo cambia por la pantalla de la
  solicitud.
- **Montos (regla «Precio y montos»):** `monto_pagar = cant_entregada × precio_unitario`, `ROUND_HALF_UP` a 2 decimales;
  `monto_total_entrega` = Σ de las líneas. En una compra-venta que **no** es la última (8a), no se cobra en esta entrega: el total de la
  venta se cobra en la última (regla «Venta registrada por entrega»; el asiento de cada entrega, fuera de la ronda).
- **Medio de pago** (11a): efectivo, transferencia, tarjeta de débito o tarjeta de crédito; obligatorio cuando se cobra
  (`medio_de_pago_obligatorio`).

### Intento fallido (COM-CNC-ENT 4a y COM-FIN-RUT, regla 1)

- `registrar_intento_fallido(actor, entrega_id, motivo, descripcion)`: con envío, el Transportista asignado con la ruta iniciada. Bloqueos:
  la cuenta (y las del Vendedor) → el invernadero de origen → la entrega. Relee 14a.
- Efecto: un `IntentoFallido` (D-68, punto 6) con la fecha programada que tenía; la entrega sigue «a realizar» con `fecha_programada_orden =
  hoy + 1` y `transportista = None`, y `recordatorio_para` y `aviso_atrasada_para` en nulo (para que los avisos de COM-05a1 vuelvan a
  correr por la fecha nueva); **sus reservas de insumo siguen activas** (regla 8 de 8.13) y no se registra ningún consumo. El paso 50 de
  COM-PNF-ENT le busca transportista (COM-05a1); hasta entonces, la alerta «entrega sin transportista» la crea ese paso como a cualquier
  otra (no esta función). No suma a los incumplimientos del contrato.
- Avisos: al Vendedor («OT-0231 · no se pudo entregar: cliente ausente. Pasa al 24/11/2026, sin transportista.») y correo al cliente con el
  motivo y la nueva fecha (`estado_aviso_cliente`). Auditoría: `intento_fallido_entrega` con la entrega y el intento.
- Motivo: de la lista de 4a, obligatorio (`motivo_obligatorio`); descripción opcional (hasta 300).

### Finalizar la ruta (COM-FIN-RUT)

- Precondición b: `esta_en_ruta(hoy)`; si no, `ruta_no_iniciada` (la de ayer ya venció sola, regla 4: no hay nada que finalizar).
- Bloqueos: la cuenta → el invernadero → el vehículo → las entregas de la ruta, releídas. Con entregas «a realizar» de la ruta:
  `ruta_con_entregas_pendientes` con la lista (regla 1): la pantalla ofrece, por cada una, «Concretar» o «Intento fallido»
  (`registrar_intento_fallido`, la misma función). Sin ninguna: `en_ruta = False` (`fecha_inicio_ruta` queda: regla 3, puede iniciar otra
  ruta hoy). Auditoría `fin_ruta` con el vehículo y, en `datos`, los intentos fallidos registrados desde la pantalla de finalizar en esta
  ruta (postcondición c).
- Regla 4 (la ruta que no se finaliza): no hay nada que programar. La definición de MD-118 la vence sola y el aviso por entregas asignadas
  con fecha vencida ya lo hace el paso 50 (COM-05a1, `aviso_atrasada_para`).

### PROD-VNC-CAM 3b y lo demás de la cámara (disparador «Cuando exista Entrega», punto 7)

- **3b** (paso 20, COM-04b): si una partida vencida tiene líneas en una entrega **en curso**, no se vence ese día: se deja para la próxima
  ejecución y se asegura la alerta de estado `comercial_partida_en_entrega_en_curso` (`GERENTE`, `CRITICA`, clave `partida:<id>`, con su
  `AlertaComercial(partida=…)`), que se resuelve cuando la partida se vence o se agota. «No debería ocurrir» (el paso corre antes de las
  rutas), pero el paso 20 lo verifica y la prueba lo fuerza.
- La devolución a una partida vencida y el aviso «partida por vencer» resuelto al agotarse: arriba, pasos 3 y 9 de «Concretar».

### Lo que completa a otras tareas

| Tarea | Qué |
|---|---|
| MAE-05 y COM-05a1 | `transportista_en_ruta` en `registrar_impedimento_de_transportista` (el mismo registrante de `transportista_con_entregas`, D-55; reglas 9 y 10 de PROD-MOD-INV): «Está en ruta desde hoy con N entregas.», como resolver «Esperá a que finalice la ruta.» |
| MAE-05 (core) | `transportista_en_ruta` en `core.extensiones.registrar_impedimento_de_baja_de_cuenta` (precondición d de USR-BAJ-USR) |
| COM-05b | COM-CNL-CVT con entregas concretadas (6a): el servicio **sigue rechazando** `venta_con_entregas_concretadas` hasta COM-08; esta tarea lo prueba con una entrega concretada real y prueba que los detalles cancelados son los **sin** línea en una entrega concretada (D-67, punto 4) |
| COM-05a1 | «Concretar retiro» en la lista de entregas (Vendedor responsable, entregas de retiro «a realizar» con fecha `<= hoy`) |
| COM-03a y COM-03b | La ficha del suministro: «Entregado» en el calendario (regla 6 de COM-CNS-SUM), las entregas concretadas con monto, vencimiento y estado de pago (regla 7; «pagada» llega con COM-08) y las discrepancias pendientes |
| COM-01 | La ficha del cliente: entregas sin cobrar (suministro, con monto a cobrar y vencimiento) y discrepancias pendientes; la baja del cliente las informa (regla 1 de COM-BAJ-CLT; `clientes.md`, «Se completa en») |
| COM-02 | La ficha de la compra-venta: fecha de concreción, el pago (medio, fecha, monto) y, por detalle, lo entregado |

## Pantallas

Referencia visual (D-61): `docs/prototipos/comercial/comercial_y_cosecha.html` (leé primero su `README.md`). Vale la **última** definición
de cada función. El Transportista trabaja **desde el celular, en «modo campo»** (requisitos especiales de los tres casos de uso):
`.claude/rules/interfaz.md`, botones grandes, un paso por pantalla, sin tablas anchas.

| Pantalla | Funciones del prototipo | Qué tiene |
|---|---|---|
| «Mi ruta» del Transportista (`/comercial/ruta/`) | `VIEWS.ruta` (la de la línea 1732), `loc`, `entR` | Vehículo, entregas de hoy ordenadas (demoradas primero, después por localidad), peso, localidades y capacidad; «Iniciar ruta», «Concretar», «Intento fallido» y «Finalizar ruta» según el estado |
| Iniciar ruta | `MODALS.inirut` | La confirmación del paso 4, con la lista. Sin JavaScript, una página |
| Concretar entrega (`/comercial/entregas/<id>/concretar/`) | `INIT.cncent`, `VIEWS.cncent` (línea 1682), `cncentCalc` | En pasos: llegó por línea (y perdidas), aceptación o recepción, envases, medio de pago, resumen. HTMX recalcula (`calcular/`, que no escribe) |
| Intento fallido | `MODALS.fallo` | Motivo de la lista y descripción. Sin JavaScript, una página |
| Finalizar ruta | `MODALS.finrut` | Con pendientes: cada una con «Concretar» e «Intento fallido»; sin pendientes: la confirmación |
| Concretar retiro (Vendedor) | `VIEWS.cncent` con `S.role !== 'tra'` | La misma pantalla, desde la lista de entregas de Comercial (botón «Concretar retiro») |

- **Dónde entra el Transportista:** la entrada «Mi ruta» del menú (`core/menu.py`, `registrar_entrada`, solo para el Transportista activo) y
  una sección «Ruta de hoy» en su Panel de control (`registrar_seccion_de_inicio`). Antes de escribirlas, mirá qué tiene hoy el Panel de
  control del Transportista y el menú (plan de la ronda, punto 2.3 del método): no dupliques una sección que ya exista.
- Vistas que solo orquestan (`abm.md`, sección 1), `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`; respaldo completo sin
  JavaScript (cada ventana es una página); errores por campo; aviso breve al terminar (D-29).

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Iniciar ruta | La ventana solo lista las entregas y el peso | Pasos 2 y 3: vehículo con capacidad, demoradas primero con sus días de retraso (2b), las sin envasado señaladas (2c), cantidad de entregas y de localidades |
| Intento fallido | `ACT['fallo-ok']` marca la entrega con `fallo` y la deja en la lista del día | 4a.2: pasa al día siguiente **sin transportista**: sale de la ruta |
| Concretar: envases | Un solo número «usa» por entrega (`S.f.usa`) | Paso 9 y 9a: por **cada** envase reservado, utilizada y devuelta (la devuelta propuesta, que solo se puede bajar); sin envasado, una lista de envases declarados o «no usé envases» |
| Concretar: suministro | El monto se calcula con el precio de la venta | 3a.2: el precio se recalcula con la fecha real (`precio_en`) |
| Concretar: resumen | No muestra el vencimiento del pago | 3a.3: monto total y vencimiento del pago |
| Finalizar ruta | Bloquea solo con las `!e.fallo` | Regla 1: bloquea con toda entrega «a realizar» de la ruta (las de intento fallido ya no son de la ruta) |

### Solo prototipo

- Los datos de ejemplo (`DB`), el cambio de rol y la fecha fija. El asiento que muestra el resumen (fuera de la ronda: «Fuera de esta ronda ·
  contabilidad», D-57).

## Pruebas

- `test_com_ini_rut.py` (`ComIniRutServicioTests`): una por postcondición (a a c), extensión (1a, 1b, 1c, 2a, 2b, 2c, 5a, 5b, 5c, 5d) y regla
  (las entregas de la ruta: con retiro, de otro, cancelada, con fecha futura, demorada; más de una ruta en el día; el peso; el orden); que no
  toca entregas ni reservas (comparar antes y después); y con la ruta iniciada, que COM-ASG-TRP, PROD-PNF-ENV, COM-CNL-CVT y COM-PNF-ENT ven
  las entregas «en curso».
- `test_com_cnc_ent.py` (`ComCncEntServicioTests`): una por postcondición (a a g, i a o, p y q; e y h, sin asiento) y extensión (1a, 3a, 4a,
  5a, 5b, 7a, 8a, 8b, 9a, 10a, 10b, 13a, 14a, 14b, 14c, 15a); el reparto (dos y tres orígenes, empates por aporte y por fecha límite, perdido
  y devuelto en la misma línea); la devolución a una partida vencida, a una agotada y desde un lote con la fecha límite pasada; el exceso de
  envases (la reserva topeada, el consumo con el exceso, la utilizada declarada en la auditoría); un detalle de venta en dos entregas (el
  último cobra el total); el fin del detalle y del suministro, y el detalle con períodos pendientes que no se finaliza; sin transacción
  propia del núcleo; sin consultas por fila en `entregas_concretables` y `resumen_de_concrecion`.
- `test_com_fin_rut.py` (`ComFinRutServicioTests`): una por regla (1 a 5) y postcondición (a a c); la ruta de ayer (vencida) no se
  finaliza; finalizar y volver a iniciar el mismo día.
- `test_concrecion_concurrencia.py` (`@tag("concurrencia")`): dos concreciones de la misma entrega (una gana; la otra, `entrega_no_concretable`);
  concretar contra reasignar (COM-ASG-TRP); concretar un retiro contra cambiar su envasado (huella); iniciar la ruta contra planificar una
  entrega para el mismo transportista (5c); intento fallido contra concretar.
- `test_rutas_vistas.py`: permisos (el Transportista solo lo suyo; el Vendedor solo los retiros de sus contratos; el Gerente, el Agrónomo y el
  Capataz no concretan: 403 y ningún botón lleva a un 403); el flujo completo con HTMX y sin JavaScript en un ancho de celular (la
  plantilla, no un navegador); `calcular/` no escribe nada (cuenta de filas igual antes y después).
- Invariantes: `verificar_invariantes_de_entregas()` (con los de COM-06a), `verificar_invariantes_de_solicitudes()`, los de reservas y de
  stock (`docs/patrones/stock_maduro.md`, sección 8; `docs/patrones/stock.md`, sección 7) después de cada prueba que concreta.

## Para más adelante

- **COM-06b:** el enlace de confirmación en el correo de la concreción (postcondición l); COM-CNF-ENT; COM-ATN-ENR (lee `intentos_fallidos`
  y lo que registró la concreción).
- **COM-07:** COM-EVL-DSC resuelve la discrepancia; COM-RSV-QJA lee `intentos_fallidos`; el monto a cobrar resta lo indemnizado.
- **COM-08:** el cobro de las entregas de suministro (`Entrega.pago`, R154), «pagada» y la alerta «pago en mora»; la extensión 6a de
  COM-CNL-CVT.
- **Contabilidad** (D-57): los asientos de la entrega, de las mermas y de los consumos (postcondiciones e, g y h).
- Temas abiertos de los casos de uso: el cliente de una compra-venta que no puede pagar el total; la hora de la ejecución diaria (con el cron
  único, D-56); el retiro que nadie viene a buscar; si la merma de entrega suma al umbral (hoy no: no tiene etapa, D-64); la cancelación de
  una entrega ya envasada; la entrega que no puede salir (COM-INI-RUT).
