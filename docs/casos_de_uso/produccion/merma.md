# Casos de uso · produccion · Merma

Copia para el repo del caso PROD-REG-MRM (versión 0.5) del documento de Drive «CU extendidos», consultado el 20/11/2026. El código de la merma de un lote en pie va en la app `produccion`; **la de una partida en cámara (desde COM-04), en `comercial`** (D-59, A3: recorta reservas). Ver «Cómo se aplica en la ronda «Comercial 1»» al final.
Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. Se quitaron las marcas ⛔ y los `**` sueltos del export de Drive y se corrigió la numeración. No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-REG-MRM | Registrar Merma | Capataz, Agrónomo | `produccion/tests/test_prod_reg_mrm.py`; en cámara: `comercial/tests/test_prod_reg_mrm_camara.py` |

---

## PROD-REG-MRM · Registrar Merma

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción.
Actor principal: Capataz. El Agrónomo también puede ejecutar este caso de uso, sobre los invernaderos a su cargo.
Versión: 0.5

Personal involucrado e intereses
- Capataz: quiere dejar constancia rápida de las plantas o el producto que se perdieron, con su causa, sin tener que
   calcular stock ni costos.
- Agrónomo: quiere enterarse a tiempo cuando un lote acumula demasiada merma o cuando una pérdida deja sin cobertura
   una cosecha o una transición planificada, para corregir el manejo del cultivo y replanificar.
- Vendedor: quiere enterarse si una pérdida en cámara afecta producto reservado para sus contratos, y que el sistema
   intente cubrir el faltante.
- Cliente: quiere recibir lo pactado o, si falta producto, poder decidir si acepta una cantidad menor.
- Gerente: quiere que cada pérdida quede valorizada en “Pérdidas por Mermas”, con su causa, para analizar dónde se
   pierde producción.
- Organización (Jardín Botánico): quiere medir la merma por lote y por causa, para cumplir el objetivo de reducirla
   por debajo del 15 % por ciclo, y que el stock de lotes, cámara y sectores refleje la realidad.

Relaciones con otros casos de uso
- «extend» de PROD-CNC-CSC · Concretar Cosecha, en el punto de extensión *Plantas perdidas en la cosecha* (extensión
   10a). Se ejecuta en el paso 13 de ese caso de uso, una vez por cada lote con plantas perdidas.
- «extend» de PROD-CNC-TRN · Concretar Transición, en el punto de extensión *Plantas perdidas en la transición*
   (extensión 10a). Se ejecuta en el paso 13 de ese caso de uso, una sola vez, para el lote de la transición.
- «include» PROD-ASG-STK · Asignar Stock Maduro: se incluye en la extensión 10c para cubrir el faltante que deja una
   merma en cámara sobre producto reservado.
- Nota: la diferencia detectada en una entrega se registra dentro de Concretar Entrega y no usa este caso de uso. La
   merma por vencimiento de una partida en cámara la registra InfoPonia automáticamente, como regla del sistema, y
   tampoco usa este caso de uso.

Precondiciones
a. El actor está autenticado en el Sistema.
b. En al menos uno de los invernaderos del actor existe un lote en estado “activo” o una partida de cámara en estado
   “disponible”.
c. Existe un ejercicio contable vigente. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*
d. Existen las cuentas contables “Pérdidas por Mermas”, “Productos en Proceso” y “Productos Terminados”. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*

Garantías mínimas
- La operación es atómica, incluido el caso de uso incluido. Si el caso de uso se cancela o falla, no se registra
   ninguna merma ni se modifica ningún lote, partida, sector, reserva, contrato, movimiento de stock, asiento contable
   ni log de auditoría.
- Una merma nunca deja a un lote ni a una partida con cantidad negativa.
- Cuando el caso de uso se ejecuta como extensión, sus registros forman parte de la transacción del caso de uso base:
   se confirman o se revierten junto con él.

Garantías de éxito (Postcondiciones)
Si la merma es de un lote en pie:
a. Se registró una merma en la bitácora del lote, con tipo de evento “merma”, la fecha y hora actuales, la cantidad
   perdida, la causa, la descripción (si se indicó) y el usuario responsable (el Capataz o el Agrónomo, según quién la
   registró). Está asociada al lote, a su etapa productiva actual y al invernadero. (desde Concretar Transición, ver
   ‘Ejecución como extensión’)
b. La cantidad actual del lote se redujo en la cantidad perdida. Si llegó a cero, el lote quedó en estado
   “finalizado”.
c. En cada sector afectado, la cantidad de agujeros ocupados por la ocupación del lote se redujo en las plantas
   perdidas en ese sector, y la cantidad de agujeros disponibles del sector aumentó en esa misma cantidad.
d. Se registró un movimiento de stock de tipo “salida por merma”, con la cantidad perdida y la fecha actual, asociado
   al lote y originado en la merma. (desde Concretar Transición, ver ‘Ejecución como extensión’)
e. Se generó un asiento contable en el libro diario del ejercicio vigente, originado en la merma, que debita la cuenta
   “Pérdidas por Mermas” y acredita la cuenta “Productos en Proceso” por la cantidad perdida multiplicada por el costo
   por planta del lote. El costo acumulado del lote se redujo en ese monto.
Si la merma es de una partida en cámara:
f. Se registró una merma en la bitácora del lote de origen de la partida, con tipo de evento “merma”, la fecha y hora
   actuales, la cantidad perdida, la causa, la descripción (si se indicó) y el usuario responsable (el Capataz o el
   Agrónomo, según quién la registró). Está asociada a ese lote y al invernadero, sin etapa productiva.
g. La cantidad disponible de la partida se redujo en la cantidad perdida. Si llegó a cero, la partida quedó en estado
   “agotado”.
h. Se registró un movimiento de stock de tipo “merma en cámara”, con la cantidad perdida y la fecha actual, asociado a
   la partida y originado en la merma.
i. Se generó un asiento contable en el libro diario del ejercicio vigente, originado en la merma, que debita la cuenta
   “Pérdidas por Mermas” y acredita la cuenta “Productos Terminados” por la cantidad perdida multiplicada por el costo
   unitario de la partida.
j. Si la cantidad perdida superó el stock libre de la partida:
- se redujo la cantidad reservada de las líneas de cámara afectadas hasta igualar lo que físicamente queda, en el
   orden de la regla “Recorte de reservas de cámara”;
- cada reserva cuya cantidad cubierta quedó en cero pasó a “liberada”;
- se ejecutó PROD-ASG-STK por el faltante de cada detalle de contrato afectado;
- si no hubo stock para cubrirlo, el detalle de compra-venta y su venta quedaron en “pendiente de decisión del
   cliente” y se envió al cliente un correo con un enlace de acceso temporal; en un suministro, la entrega del período
   saldrá con lo disponible;
- se notificó al Agrónomo y al Vendedor de cada contrato afectado.
En ambos casos:
k. Si la merma acumulada del lote superó por primera vez el porcentaje máximo de merma configurado, se generó una
   alerta para el Agrónomo responsable del invernadero y para el Gerente, asociada a la merma.
l. Si después de la merma se cumple alguna de las condiciones de plantas comprometidas del lote, se generó una alerta
   para el Agrónomo responsable del invernadero, asociada a la merma.
m. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la merma, del movimiento de stock y
   del asiento contable creados.
n. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor de cada lote, partida,
   ocupación de sector, sector, línea de reserva, reserva y detalle de contrato modificados.
o. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada alerta generada.

Escenario principal de éxito (o Flujo Básico)
1.  El actor inicia el registro de una merma.
2.  El Sistema presenta los invernaderos del actor.
3.  El actor selecciona un invernadero.
4.  El Sistema presenta los lotes activos del invernadero, indicando para cada uno la variedad, la etapa productiva
   actual y la cantidad actual.
5.  El actor selecciona el lote afectado.
6.  El Sistema presenta la cantidad actual del lote, los sectores donde tiene ocupaciones vigentes con los agujeros
   ocupados en cada uno y la merma acumulada del lote, y propone cero plantas perdidas en cada sector.
7.  El actor indica la cantidad de plantas perdidas en los sectores en los que hubo pérdidas, la causa y,
   opcionalmente, una descripción. En los demás sectores se toman cero plantas perdidas.
8.  El Sistema verifica las cantidades y que se haya indicado la causa, y presenta el resumen de la merma: lote,
   variedad, plantas perdidas por sector y en total, causa, cantidad actual resultante del lote y las advertencias que
   correspondan (umbral de merma superado o plantas comprometidas sin cobertura).
9.  El actor confirma el registro.
10. El Sistema registra la merma en la bitácora del lote; reduce la cantidad actual del lote; actualiza las
   ocupaciones de sector y los agujeros de cada sector; registra el movimiento de stock y el asiento contable;
   actualiza el estado del lote si corresponde; y registra la auditoría correspondiente.
11. El Sistema informa al actor que la merma fue registrada.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 9, el actor cancela el registro:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
*b. En cualquier momento el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al actor que la merma no fue registrada.
3.  El actor reinicia el caso de uso desde el paso 1.
4a. La merma es de una partida en cámara:
1.  El actor indica que la pérdida es de producto en cámara.
2.  El Sistema presenta las partidas disponibles del invernadero, indicando para cada una la variedad, el lote de
   origen, la cantidad disponible, la cantidad reservada y la fecha límite.
3.  El actor selecciona la partida afectada e indica la cantidad perdida, la causa y, opcionalmente, una descripción.
4.  El Sistema verifica que la cantidad sea al menos uno y como máximo la cantidad disponible de la partida, y que se
   haya indicado la causa, y presenta el resumen. Si la cantidad supera el stock libre de la partida, el resumen
   indica qué reservas y contratos se verán afectados.
5.  El caso de uso continúa en el paso 9. En el paso 10 se aplican las postcondiciones de la merma en cámara.
4a.4a. La cantidad indicada es menor que uno o supera la cantidad disponible de la partida:
1.  El Sistema señala el error e informa la cantidad disponible de la partida.
2.  El actor corrige la cantidad (vuelve a 4a.3).
4a.4b. El actor no indicó la causa:
1.  El Sistema señala que la causa es obligatoria.
2.  El actor indica la causa (vuelve a 4a.3).
4b. El invernadero no tiene lotes activos:
1.  El Sistema informa que no hay lotes activos en ese invernadero.
2.  El actor registra una merma en cámara (continúa en 4a), selecciona otro invernadero (vuelve al paso 3) o cancela.
8a. La cantidad indicada para un sector supera los agujeros ocupados por el lote en ese sector:
1.  El Sistema señala el error e informa los agujeros ocupados por el lote en ese sector.
2.  El actor corrige la cantidad (vuelve al paso 7).
8b. El total de plantas perdidas es cero:
1.  El Sistema informa que la merma debe ser de al menos una planta.
2.  El actor corrige las cantidades (vuelve al paso 7) o cancela.
8c. El actor no indicó la causa:
1.  El Sistema señala que la causa es obligatoria.
2.  El actor indica la causa (vuelve al paso 7).
9a. El actor quiere corregir un dato del resumen:
1.  El actor indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5 o 7, o 4a.3 en una
   merma en cámara).
10a. Después de la merma, se cumple alguna de las condiciones de plantas comprometidas del lote:
1.  El Sistema genera una alerta para el Agrónomo responsable del invernadero, indicando el lote, qué condición se
   cumple y qué órdenes de cosecha o qué orden de transición quedaron sin cobertura.
10b. La merma hace que la merma acumulada del lote supere por primera vez el porcentaje máximo de merma configurado:
1.  El Sistema genera una alerta para el Agrónomo responsable del invernadero y para el Gerente, indicando el lote, la
   merma acumulada y el porcentaje que representa sobre su cantidad inicial.
10c. En una merma en cámara, la cantidad perdida supera el stock libre de la partida:
1.  El Sistema reduce la cantidad reservada de las líneas de cámara de la partida, en el orden de la regla “Recorte de
   reservas de cámara”, hasta que la suma reservada iguale la cantidad disponible que queda.
2.  El Sistema pasa a “liberada” cada reserva cuya cantidad cubierta quedó en cero.
3.  Por cada detalle de contrato afectado, el Sistema incluye PROD-ASG-STK · Asignar Stock Maduro por el faltante.
4.  Si el stock maduro libre no cubre el faltante de un detalle de compra-venta:
1.  El Sistema pasa el detalle y la venta a “pendiente de decisión del cliente”.
2.  El Sistema envía al cliente un correo con un enlace de acceso temporal para que decida si acepta la cantidad
   disponible.
5.  Si el stock maduro libre no cubre el faltante de un detalle de suministro, el detalle queda con cantidad sin
   cubrir para ese período y la entrega saldrá con lo disponible.
6.  El Sistema notifica al Agrónomo y al Vendedor de cada contrato afectado.
10d. Entre las verificaciones y la confirmación, otra operación redujo la cantidad actual del lote, los agujeros
   ocupados de un sector o la cantidad disponible de la partida, de modo que la merma indicada ya no es válida:
1.  El Sistema no registra ningún cambio e informa la cantidad vigente.
2.  El caso de uso vuelve al paso 7 (o a 4a.3 en una merma en cámara).
11a. El Sistema no logra entregar una notificación o una alerta:
1.  La merma permanece registrada.
2.  El Sistema reintenta el envío.

Ejecución como extensión
Desde PROD-CNC-CSC · Concretar Cosecha (punto *Plantas perdidas en la cosecha*):
- El caso de uso recibe el lote, las plantas perdidas en cada sector, la causa y la descripción (si se indicó), ya
   verificadas en la extensión 10a de Concretar Cosecha. Se ejecuta una vez por cada lote con cantidad perdida mayor
   que cero.
- Se omiten los pasos 1 a 9: la carga y las verificaciones se hacen en la extensión 10a del caso de uso base, y la
   confirmación es la de su paso 12.
- El paso 10 y las extensiones 10a y 10b se ejecutan en el paso 13 del caso de uso base y forman parte de su
   transacción.
- Se omite el paso 11: el aviso al actor es el del paso 15 del caso de uso base.
Desde PROD-CNC-TRN · Concretar Transición (punto *Plantas perdidas en la transición*):
El caso de uso recibe el lote, el total de plantas no trasladadas (lo calcula el Sistema), la causa y la descripción
   (si se indicó), ya verificados en la extensión 10a de Concretar Transición. Se comporta igual que desde Concretar
   Cosecha, con estas diferencias:
- la merma se registra en la etapa de origen del lote, antes del traslado;
- en las postcondiciones a y d, la fecha es la fecha efectiva de la transición, que puede ser anterior a la fecha
   actual, y la hora es la actual;
- no se aplica la postcondición c: la merma no tiene cantidades por sector y no libera agujeros, porque Concretar
   Transición libera todos los agujeros de origen del lote, incluidos los de las plantas perdidas;
- la extensión 10a evalúa las plantas comprometidas sin contar la orden de transición que se está concretando.

Requisitos especiales
- Tras cada selección o dato ingresado por el actor (pasos 3 a 7), la pantalla se actualiza con las verificaciones y
   los valores calculados en no más de 1 segundo.
- El registro del paso 10 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un
   indicador de progreso.
- El paso 10, incluida la ejecución de PROD-ASG-STK, se ejecuta como una única transacción.
- El control de concurrencia impide que dos mermas, o una merma y una cosecha simultáneas, dejen a un lote o a una
   partida con cantidad negativa.
- El Capataz solo accede a los lotes y partidas de los invernaderos que tiene asignados; el Agrónomo, a los de los
   invernaderos a su cargo.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos de los asientos contables se expresan en pesos argentinos, con dos decimales.
- El enlace de acceso temporal enviado al cliente es de uso único y tiene una vigencia limitada.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Ámbito del actor: el Capataz registra mermas sobre lotes y partidas de los invernaderos que tiene asignados; el
   Agrónomo, sobre los de los invernaderos a su cargo. (Pasos 2 y 4)
- Valores propuestos: el Sistema propone cero plantas perdidas en cada sector del lote. El actor solo indica los
   sectores en los que hubo pérdidas; en los demás se toman cero plantas perdidas. (Pasos 6 y 7)
- Cantidad válida en un lote: en cada sector donde el lote tiene una ocupación vigente (con agujeros ocupados mayores
   que cero; regla 1 de 8.21 cuando se aplique), un número entero entre cero y los agujeros ocupados por el lote en
   ese sector; en total, al menos una planta. Como la suma de los agujeros ocupados de sus ocupaciones vigentes es
   igual a su cantidad actual, el total nunca supera la cantidad actual del lote. (Paso 8)
- Cantidad válida en una partida: un número entero entre uno y la cantidad disponible de la partida. (Extensión 4a)
- Causa: es obligatoria y depende de dónde ocurre la merma. En un lote en pie: plaga, enfermedad, falla de riego o
   nutrientes, condiciones ambientales, daño mecánico, descarte por selección u otra. El descarte por selección son
   plantas que se descartan a propósito, no por un problema del cultivo. En una partida en cámara: las mismas, salvo
   el descarte por selección, más daño en cámara. “Vencimiento en cámara” la usa solo el Sistema cuando una partida
   vence, y “daño en la entrega” la usa solo Concretar Entrega. (Pasos 7 y 8, y extensiones 4a, 8c y 4a.4b)
- Costo por planta de un lote: costo acumulado del lote dividido por su cantidad actual. El costo acumulado es la suma
   de los montos de consumo de su siembra y de sus imputaciones de costo, menos lo que ya salió por cosecha y por
   merma. (Paso 10)
- Valorización de la merma: en un lote, cantidad perdida × costo por planta del lote, con crédito en “Productos en
   Proceso”; la merma baja el costo acumulado del lote en ese monto. En una partida, cantidad perdida × costo unitario
   de la partida, con crédito en “Productos Terminados”. En ambos casos, débito en “Pérdidas por Mermas”. (Paso 10)
- Liberación de agujeros: en cada sector se liberan tantos agujeros como plantas se perdieron en ese sector. (Paso 10)
- Fin del lote y de la partida: un lote cuya cantidad actual llega a cero pasa a “finalizado”; una partida cuya
   cantidad disponible llega a cero pasa a “agotado”. (Paso 10)
- Stock libre de una partida: cantidad disponible menos la suma de las cantidades reservadas en sus líneas cuya
   reserva está “activa” o “lista para entrega”. (Extensión 10c)
- Recorte de reservas de cámara: si la merma supera el stock libre de la partida, se reduce la cantidad reservada de
   sus líneas en este orden: primero las reservas de compra-venta y después las de suministro; dentro de cada grupo,
   primero la de fecha de entrega más lejana y, si empatan, la creada más tarde. Una reserva cuya cantidad cubierta
   queda en cero pasa a “liberada”. (Extensión 10c)
- Merma acumulada de un lote: suma de las cantidades de las mermas registradas sobre el lote en pie, dividida por su
   cantidad inicial. No se cuentan las mermas cuya causa es el descarte por selección. Las mermas en cámara no se
   cuentan: la merma acumulada mide la pérdida antes de la cosecha, y la degradación del producto ya cosechado es
   esperable. (Paso 8 y extensión 10b)
- Umbral de merma: si la merma acumulada supera el porcentaje máximo de merma de la configuración operativa (valor
   inicial: 15 %), se alerta al Agrónomo y al Gerente. La alerta se genera una sola vez por lote, al cruzar el umbral.
   (Extensión 10b)
- Plantas comprometidas de un lote: se evalúan dos condiciones por separado (regla 15 de 8.8), y si se cumple alguna
   se alerta al Agrónomo; la merma no se bloquea. (Extensión 10a)
1.  La suma de las cantidades reservadas en sus líneas cuya reserva está “activa” supera su cantidad actual, y quedan
   cosechas sin cobertura.
2.  La cantidad planificada de su orden de transición “a realizar” (la suma de los agujeros planificados de sus
   ocupaciones destino) supera su cantidad actual, y la transición queda con menos plantas que las planificadas.

Lista de tecnología y variaciones de datos
- 7a. Las cantidades se expresan en plantas (lote) o en unidades de producto (partida), como números enteros.
- 7b. La causa se elige de la lista que corresponde según dónde ocurre la merma (regla “Causa”). La descripción es
   texto libre opcional.
- 10a. Las alertas se presentan dentro del Sistema y pueden, además, enviarse por correo electrónico.
- 10c. El correo al cliente incluye el enlace de acceso temporal, las cantidades solicitada y disponible de cada
   detalle afectado y la fecha de entrega.

Frecuencia
A confirmar con el Jardín Botánico. Se espera que ocurra de forma irregular, cada vez que se detecta una pérdida en
   una recorrida, en una cosecha o en una transición.

Temas abiertos
- Cuando el Agrónomo registra la merma, el modelo no tiene una asociación entre Agrónomo y Bitácora para dejarlo como
   responsable: hoy solo existe Capataz–Bitácora. [Resuelto el 15/11/2026 (MD-77): se crea la asociación
   Agrónomo–Bitácora («registra»), así que el Agrónomo queda como responsable del registro; MD-22 quedó descartado.]

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-50, D-51)

PROD-REG-MRM está escrito para lotes y partidas de cámara. En la ronda **solo se hace la merma de un lote en pie**. Una parte (la que usa Concretar Transición) la entregó PRD-02 como núcleo; PRD-03 agrega la pantalla y el caso de uso por sector.

### Lo que NO se hace en la ronda (D-45)

- **Todo lo de la partida en cámara:** extensiones 4a, 4a.4a, 4a.4b y 10c; postcondiciones f, g, h, i, j; las causas «daño en cámara», «vencimiento en cámara» y «daño en la entrega»; el recorte de reservas de cámara, PROD-ASG-STK incluido, y el correo al cliente. En la extensión 4b, sin lotes activos el caso informa y ofrece otro invernadero o cancelar (no hay «merma en cámara»).
- ~~**Asiento contable** (postcondición e, y las precondiciones c y d)~~ **Hecho en CON-04a (25/11/2026):** `registrar_merma` asienta Debe «Pérdidas por Mermas» / Haber «Productos en Proceso» por `ResultadoMerma.costo`, con la fecha de la merma (el asiento va en quien llama a `aplicar_merma`, no en ella; D-92). El **movimiento de stock «salida por merma»** (postcondición d) lo hizo COM-04a. El **costo acumulado del lote baja** (`docs/patrones/costo_del_lote.md`).
- **Alerta de plantas comprometidas, condición 1** (reservas de cosecha activas): fuera. La **condición 2** (la transición «a realizar» del lote queda con más plantas planificadas que las actuales) **sí se evalúa**: desde este caso de uso ya puede dispararse.
- Extensión 11a («no logra entregar»): no aplica (D-42; las alertas se crean dentro de la transacción).

### Qué hace cada parte

| Parte | Código |
|---|---|
| Núcleo de la merma (PRD-02) | `produccion/servicios/mermas.py`: `aplicar_merma(...)` (ver `docs/api/produccion.md`); lo llaman Concretar Transición, este caso de uso y Poner Sector Fuera de Servicio |
| Registrar Merma | `produccion/servicios/mermas.py`: `lotes_con_merma_posible(actor, invernadero_id)`, `datos_de_merma`, `resumen_de_merma`, `registrar_merma(actor, datos)` |
| Merma acumulada | `produccion/servicios/mermas.py`: `merma_acumulada(lote)` → porcentaje sobre la cantidad inicial, sin las mermas de «descarte por selección» |

### Decisiones de aplicación

- **Quién y dónde**: el Capataz, en los invernaderos que tiene asignados; el Agrónomo, en los que tiene a su cargo. El responsable del registro es quien actúa (`Bitacora.responsable`, MD-77). Un invernadero sin Capataz activo igual admite que el Agrónomo registre una merma.
- **Cantidad válida**: por sector, entre 0 y los agujeros ocupados por el lote en ese sector (ocupaciones vigentes); en total al menos 1 (extensiones 8a y 8b). El total nunca supera `cantidad_actual` (invariante). **Causa obligatoria** (8c): las causas de un lote en pie, **incluida «descarte por selección»**.
- **Fecha**: la de hoy, hora actual. (Solo Concretar Transición y Poner Sector Fuera de Servicio usan la fecha efectiva.) La merma queda en la **etapa actual** del lote.
- **Efectos** (todo en `aplicar_merma`): `Merma` con su `Bitacora` (tipo `merma`, lote, etapa, invernadero, `sectores` = los sectores con pérdidas, `descripcion_evento` legible, por ejemplo «Merma de 12 plantas por plaga»); baja `Lote.cantidad_actual` y `Lote.costo_acumulado` (patrón de costo); baja `cant_agujeros_ocupados` de cada ocupación afectada (los agujeros se calculan: no hay otro campo para actualizar); si el lote llega a cero, `finalizado`, con todas sus ocupaciones en 0 y costo 0.
- **Alertas** (extensiones 10a y 10b): la de umbral (`produccion_merma_umbral`, Agrónomo a cargo y Gerente) se crea **una sola vez por lote**, cuando la merma acumulada pasa de `<= porc_merma_maxima` a `> porc_merma_maxima` con esta merma; la de plantas comprometidas (`produccion_plantas_comprometidas`, Agrónomo a cargo o Gerente) cuando la transición «a realizar» del lote queda con más plantas planificadas que `cantidad_actual`. Se enlazan con la merma (`AlertaDeMerma`). No hay notificaciones (el caso de uso solo habla de alertas).
- **Resumen** (paso 8): lote, variedad, plantas perdidas por sector y total, causa, `cantidad_actual` resultante y las advertencias («supera el umbral», «deja sin cobertura la transición OT-0007»). No escribe.
- **Concurrencia (10d)**: se bloquea y se relee; si cambió la cantidad actual del lote o los agujeros de un sector, `cambio_simultaneo` con la cantidad vigente y el caso vuelve al paso 7.
- **Bloqueos**: cuentas → invernadero → variedad del lote → sectores con pérdidas (id) → lote → ocupaciones (`docs/patrones/bloqueos.md`, sección `produccion`).
- **Auditoría**: un registro `registro_merma` con la merma, la bitácora, el lote, las ocupaciones, los sectores (texto «agujeros ocupados», antes → después) y las alertas creadas.

### Pantallas

Prototipo: `VIEWS.merma`, `mrCalc`, `mermaInfo`, `aplicarMerma` (solo la parte de lote en pie). Pasos: invernadero → lote (con variedad, etapa y cantidad) → cantidades por sector, causa y descripción → resumen → confirmar. Formulario deshabilitado con su motivo si no hay lotes activos. Entrada de menú: Agrónomo («Registrar merma» dentro de «Producción») y Capataz.
Sin JavaScript funciona igual.

### Pruebas

`produccion/tests/test_prod_reg_mrm.py` (una por regla y por postcondición a, b, c, k, l, m, n, o; un sector, varios sectores, cero total, más que lo ocupado, sin causa, «descarte por selección» no suma, lote que llega a cero queda finalizado con costo 0, umbral cruzado una sola vez, con el porcentaje en 0, condición 2 con una transición ajena «a realizar», actor sin ámbito), `test_merma_concurrencia.py` (`@tag("concurrencia")`: dos mermas simultáneas sobre el mismo lote nunca lo dejan negativo; merma contra concretar transición; merma contra poner el sector fuera de servicio) y las de núcleo ya escritas en PRD-02.

## Cómo se aplica en la ronda «Comercial 1»: la partida en cámara (COM-04; D-57, D-59, D-64)

Lo de «Producción 1» (lote en pie) **no cambia**, salvo dos cosas del núcleo (`docs/api/produccion.md`, sección 8): `aplicar_merma` registra el
movimiento «salida por merma» del lote (postcondición d; disparador «Cuando exista `produccion` completa», punto 5) y `merma_acumulada` cuenta
solo las mermas con etapa (regla «Merma acumulada»: las de cámara no suman). COM-04 programa lo que la sección anterior dejó «Lo que NO se hace
en la ronda (D-45)»: extensiones 4a, 4a.4a, 4a.4b y 10c; postcondiciones f, g, h y j; las causas «daño en cámara» y «vencimiento en cámara»
(esta, solo para InfoPonia: PROD-VNC-CAM); la extensión 4b con «merma en cámara». Sigue **fuera de esta ronda · contabilidad** (D-57): la
postcondición i (asiento) y las precondiciones c y d. «Daño en la entrega» es de COM-06.

### Qué hace cada parte

| Parte | Código |
|---|---|
| Núcleo de la partida | `produccion/servicios/camara.py`: `aplicar_merma_de_partida` (f, g, h) |
| Registrar merma en cámara | `comercial/servicios/merma_camara.py`: `partidas_con_merma_posible(actor, invernadero_id)`, `resumen_de_merma_en_camara(actor, datos)`, `registrar_merma_en_camara(actor, datos)` (10c, j) |
| Recorte y faltante | `docs/patrones/stock_maduro.md`, sección 8 (`orden_de_recorte`, el camino de faltante) |

### Decisiones de aplicación

- **Entrada:** la pantalla «Registrar merma» de PRD-03 ofrece en el paso 4 «Pérdida en cámara» (extensión 4a) con la URL de
  `entradas_de_comercial(usuario).merma_en_camara` (D-64 punto 11), con el invernadero ya elegido; sin registrante, la opción no aparece. La
  pestaña «Cámara» de la ficha del invernadero suma el botón «Registrar merma en cámara» para el Capataz asignado y el Agrónomo a cargo (D-61).
  4b: un invernadero sin lotes activos pero con partidas disponibles ofrece la merma en cámara.
- **Quién y dónde:** los mismos que la merma de un lote (precondición b: el Capataz en sus invernaderos, el Agrónomo en los suyos), sobre
  partidas «disponibles».
- **Paso 4a:** las partidas disponibles del invernadero, con variedad, lote de origen (`L-12`), fecha límite, cantidad disponible y **stock
  libre**. Cantidad válida: entero entre 1 y la disponible (4a.4a: `cantidad_invalida` con la disponible). **Causa obligatoria** (4a.4b):
  «Daño en cámara» y las de lote en pie **sin** «Descarte por selección»; nunca «Vencimiento en cámara». Descripción opcional (hasta 500).
- **Resumen (paso 9):** partida, variedad, cantidad perdida, causa, la disponible que queda y, si la pérdida supera el stock libre, la
  advertencia con **qué contratos pierden producto** y cuánto (en el orden del recorte) y que se intentará volver a cubrir.
- **Registro (paso 10), en una transacción:**
  1. bloqueos (se leen antes, sin bloquear, los contratos con líneas en la partida): las cuentas (quien actúa, el Agrónomo, los Vendedores de
     esos contratos) → el invernadero de la partida y los considerados de esos contratos, en orden de id → la variedad → lotes y partidas
     candidatos (con esta) → los contratos, detalles, reservas y líneas, y sus enlaces;
  2. relectura: 10d (`cambio_simultaneo` con la disponible vigente; vuelve a 4a.3);
  3. **10c, si la cantidad supera el stock libre:** el recorte (`orden_de_recorte`) hasta que lo reservado en reservas «activas» o «lista para
     entrega» iguale la disponible nueva; reservas con cubierto 0, «liberada»; por cada detalle o período afectado, lo recortado de ese
     detalle por el camino de la sección 8 del patrón (`asignar` si se puede cubrir; si no, directo al camino de faltante; un detalle
     confirmado, D-64 punto 13);
  4. `camara.aplicar_merma_de_partida` (f, g, h), con el actor como responsable;
  5. si la partida quedó «agotada», `resolver_aviso_de_partida` (la alerta «partida por vencer», `camara.md`);
  6. con recorte (10c.6, regla 2 de 8.9): la alerta `comercial_merma_camara_reservada` para el Agrónomo (enlazada a la merma por
     `AlertaDeMerma`) y la notificación al Vendedor de cada contrato afectado. El caso de uso dice «notifica al Agrónomo y al Vendedor»; la
     regla 2 de 8.9 dice que al Agrónomo le llega una **alerta**: se aplica la regla (las alertas van al Gerente o al Agrónomo, regla 1 de 8.9);
  7. `on_commit`: los correos del camino de faltante.
- **Postcondiciones k y l** no se dan en una merma en cámara: la merma acumulada no cuenta las de cámara (k) y las plantas comprometidas son del
  lote en pie (l).
- **Auditoría (n):** el mismo `registro_merma`, con la partida, el movimiento, la merma, las líneas recortadas, las reservas liberadas, lo de
  `asignar`, el camino de faltante y las alertas.

### Pantallas

La de PRD-03 (`VIEWS.merma` del prototipo de producción) con la opción nueva, y la página de `comercial` para la cámara (no está en el
prototipo comercial: se arma con el mismo esquema de la merma, D-61): invernadero → partida → cantidad, causa y descripción → resumen →
confirmar. Sin JavaScript funciona igual.

### Pruebas

`comercial/tests/test_prod_reg_mrm_camara.py` (una por postcondición f, g, h, j y por extensión 4a, 4a.4a, 4a.4b, 4b, 10c, 10d; dentro del stock
libre no recorta; recorte en el orden de la regla con compra-venta y suministro, fechas distintas y empate por la más reciente; reserva con
líneas de lote y de cámara que sigue viva con la línea en 0; detalle pendiente, confirmado (cubierto con otra partida, y sin stock: vuelve a pendiente con enlace) y período; vuelve a cubrir con otra partida y con un
lote (cosecha nueva); la partida que se agota resuelve «partida por vencer»; «Vencimiento en cámara» y «Descarte por selección» no se
ofrecen), las de núcleo en `produccion/tests/test_camara_nucleo.py`, y en `produccion/tests/test_prod_reg_mrm.py` las nuevas del movimiento
«salida por merma» y de `merma_acumulada` sin las de cámara. Concurrencia (`@tag("concurrencia")`): una merma en cámara contra PROD-ASG-CAM de la
misma partida; contra la decisión del cliente que usa esas reservas; dos mermas de la misma partida nunca la dejan negativa.
