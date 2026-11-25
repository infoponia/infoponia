# Casos de uso · produccion · Siembra

Copia para el repo de los casos PROD-PNF-SMB (versión 0.4) y PROD-CNC-SMB (versión 0.5) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026.

Son casos de uso extendidos. **El código va en la app `produccion`**; los archivos de pruebas son `produccion/tests/test_prod_pnf_smb.py` y `test_prod_cnc_smb.py`.

Cambios de formato respecto de Drive: la numeración de los flujos principales se corrigió (el export de Drive la reinicia después de las líneas en cursiva) y se quitaron las marcas ⛔ del título.
No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-PNF-SMB | Planificar Siembra | Agrónomo | `produccion/tests/test_prod_pnf_smb.py` |
| PROD-CNC-SMB | Concretar Siembra | Capataz | `produccion/tests/test_prod_cnc_smb.py` |

---

## PROD-PNF-SMB · Planificar Siembra

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Órdenes.
Actor principal: Agrónomo.
Versión: 0.4

Personal involucrado e intereses
- Agrónomo: quiere planificar la siembra rápido y con información confiable sobre el stock de semillas, el espacio
   libre en los sectores y la compatibilidad con lo que ya se produce. Así sostiene una producción escalonada sin
   poner en riesgo los lotes en curso.
- Capataz: quiere recibir una orden clara (qué variedad, cuántos plantines, en qué sectores y para qué fecha) y tener
   la certeza de que las semillas e insumos van a estar disponibles cuando la ejecute.
- Gerente: quiere trazabilidad completa de quién planificó qué y cuándo. También quiere que la planificación no
   comprometa insumos ni espacio ya asignados a otras órdenes.
- Vendedor: quiere saber con anticipación cuándo habrá producción madura de cada variedad (la fecha estimada de
   cosecha) para poder comprometer contratos de compra-venta y de suministro.
- Organización (Jardín Botánico): quiere reducir la merma biológica por debajo del 15 % por ciclo, evitando que una
   siembra incompatible, por perfil familiar o por condiciones ambientales, afecte a los lotes que conviven en el
   invernadero. También quiere que el costo de los insumos quede asociado al lote desde su origen.
Relaciones con otros casos de uso: no incluye («include») otros casos de uso. Es extendido («extend») por CMP-HAB-IIN
   · Habilitar Insumo en Invernadero, cuando la semilla de la variedad no está habilitada en el invernadero (extensión
   8b).

Precondiciones
a. El Agrónomo está autenticado en el Sistema.
b. El Agrónomo tiene a su cargo al menos un invernadero en estado "activo".
c. Existe al menos una variedad de cultivo en estado "activo", con su ciclo productivo y sus etapas definidos.
d. Al menos uno de los invernaderos a cargo del Agrónomo tiene un Capataz activo asignado y un sector productivo
   activo, asociado al tipo de etapa "Germinación", con capacidad libre.

Garantías mínimas
- La operación es atómica. Si el caso de uso se cancela o falla, no queda registrada ninguna orden de trabajo,
   ocupación de sector, reserva de insumo, cambio en los agujeros comprometidos de los sectores ni log de auditoría
   parcial.
- El stock actual de los insumos y la cantidad de agujeros disponibles de los sectores no se modifican, cualquiera sea
   la forma en que termine el caso de uso.
- Ningún insumo ni espacio de sector queda comprometido por encima de lo realmente libre, aun cuando dos Agrónomos
   planifiquen al mismo tiempo sobre el mismo invernadero.

Garantías de éxito (Postcondiciones)
a. Se creó una orden de trabajo de siembra en estado "a realizar". Tiene fecha de creación, fecha programada, cantidad
   de plantines, prioridad (si se indicó) y descripción (si se indicó), y está asociada al invernadero, a la variedad
   de cultivo, al Agrónomo que la planificó y al Capataz del invernadero.
b. Se crearon una o más ocupaciones de sector como parte de la orden de siembra, una por cada sector de germinación
   seleccionado, con la cantidad de agujeros planificados en él y con la cantidad de agujeros ocupados en cero hasta
   que la siembra se concrete. La suma de los agujeros planificados es igual a la cantidad de plantines de la orden.
c. En cada sector seleccionado, la cantidad de agujeros comprometidos se incrementó en la cantidad de agujeros
   planificados de su ocupación.
d. Se creó una reserva de insumo en estado "activa" para la semilla de la variedad, con cantidad reservada igual a la
   cantidad de plantines y fecha de reserva igual a la fecha actual. Está asociada a la orden de trabajo de siembra y
   al insumo del invernadero correspondiente.
e. Si el Agrónomo indicó insumos adicionales, se creó una reserva de insumo en estado "activa" por cada uno, con la
   cantidad reservada indicada y fecha de reserva igual a la fecha actual, asociada a la orden de trabajo de siembra y
   al insumo del invernadero correspondiente.
f. Se envió al Capataz una notificación de la nueva orden asignada.
g. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la orden de trabajo de siembra creada.
h. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada ocupación de sector y de cada
   reserva de insumo creadas.
i. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de cada sector modificado y el cambio en
   su cantidad de agujeros comprometidos.

Escenario principal de éxito (o Flujo Básico)
1.  El Agrónomo inicia la planificación de una nueva siembra.
2.  El Sistema presenta los invernaderos activos a cargo del Agrónomo.
3.  El Agrónomo selecciona un invernadero.
4.  El Sistema presenta el Capataz asignado al invernadero y los cultivos con sus variedades activas. Para cada
   variedad indica su perfil familiar, la duración de su ciclo productivo, el stock libre de su semilla en el
   invernadero y si es compatible con el umbral efectivo del invernadero; para las no compatibles indica qué variables
   ambientales entran en conflicto y con qué lotes activos u órdenes de siembra "a realizar".
5.  El Agrónomo selecciona una variedad compatible a sembrar.
6.  El Sistema presenta los rangos ambientales de la variedad seleccionada frente al umbral efectivo del invernadero.
7.  El Agrónomo introduce la cantidad de plantines a sembrar y la fecha programada y, si quiere, la prioridad de la
   orden (alta, media o baja).
8.  El Sistema verifica que la fecha programada sea igual o posterior a la fecha actual y que el stock libre de
   semilla de la variedad cubra la cantidad de plantines. Luego presenta la fecha estimada de cosecha.
9.  El Sistema presenta los sectores de germinación activos del invernadero que son compatibles con el perfil familiar
   de la variedad, con la capacidad libre de cada uno.
10.  El Agrónomo selecciona un sector e indica la cantidad de plantines a ubicar en él.
11.  El Sistema registra la asignación al sector y presenta la cantidad de plantines que resta distribuir.
*El Agrónomo repite los pasos 10-11 hasta que no quede cantidad por distribuir.*
12.  El Sistema presenta los insumos adicionales activos del invernadero, sin incluir los de las categorías del
   sistema (Semillas, Envases, Repuestos de hardware e Infraestructura), con el stock libre de cada uno.
13.  El Agrónomo indica un insumo adicional a reservar y su cantidad.
14.  El Sistema verifica que la cantidad no supere el stock libre del insumo y presenta el insumo agregado con su
   stock libre.
*El Agrónomo repite los pasos 13-14 por cada insumo adicional que quiera reservar.*
15.  El Agrónomo termina la carga de insumos e indica, opcionalmente, una descripción para la orden.
16.  El Sistema presenta el resumen de la orden: invernadero, cultivo y variedad, cantidad de plantines, fecha
   programada, fecha estimada de cosecha, prioridad (si se indicó), distribución por sector, Capataz responsable e
   insumos a reservar (semilla e insumos adicionales).
17.  El Agrónomo confirma la planificación.
18.  El Sistema registra la orden de trabajo de siembra en estado "a realizar" junto con sus ocupaciones de sector,
   incrementa los agujeros comprometidos de cada sector, registra las reservas de semilla e insumos adicionales y
   registra la auditoría correspondiente.
19.  El Sistema notifica al Capataz la nueva orden asignada.
20.  El Sistema informa al Agrónomo que la orden fue planificada y presenta su identificador.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 17, el Agrónomo cancela la planificación:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
*b. En cualquier momento el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que la orden no fue planificada.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.
3a. El invernadero seleccionado no tiene un Capataz activo asignado:
1.  El Sistema informa que no hay un Capataz que pueda recibir la orden en ese invernadero.
2.  El Agrónomo selecciona otro invernadero (vuelve al paso 3) o cancela.
3b. El invernadero seleccionado no tiene sectores de germinación activos con capacidad libre:
1.  El Sistema informa que no hay espacio de germinación libre en ese invernadero.
2.  El Agrónomo selecciona otro invernadero (vuelve al paso 3) o cancela.
4a. El invernadero no tiene lotes activos ni órdenes de siembra "a realizar":
1.  El Sistema presenta todas las variedades activas como compatibles y el caso de uso continúa en el paso 5.
4b. Ninguna variedad activa es compatible con el umbral efectivo del invernadero:
1.  El Sistema informa que no hay variedades compatibles con las condiciones ambientales del invernadero.
2.  El Agrónomo selecciona otro invernadero (vuelve al paso 3) o cancela.
5a. El Agrónomo intenta seleccionar una variedad no compatible:
1.  El Sistema no permite la selección e informa qué variables ambientales entran en conflicto y con qué lotes activos
   u órdenes de siembra "a realizar".
2.  El Agrónomo selecciona otra variedad (vuelve al paso 5) o cancela.
5b. Ningún sector de germinación activo del invernadero es compatible con el perfil familiar de la variedad o tiene
   capacidad libre:
1.  El Sistema informa que no hay sectores de germinación compatibles con ese perfil familiar.
2.  El Agrónomo selecciona otra variedad (vuelve al paso 5) o cancela.
5c. El invernadero no tiene, para alguna etapa del ciclo de la variedad, un sector de ese tipo de etapa activo o fuera
   de servicio:
1.  El Sistema informa en qué etapas del ciclo faltan sectores y que no se puede planificar una siembra de esa
   variedad en el invernadero.
2.  El Agrónomo selecciona otra variedad (vuelve al paso 5), otro invernadero (vuelve al paso 3) o cancela.
8a. La fecha programada es anterior a la fecha actual:
1.  El Sistema señala el error y rechaza la fecha.
2.  El Agrónomo introduce una nueva fecha (vuelve al paso 7).
8b. La semilla de la variedad no está habilitada en el invernadero:
1.  El Sistema informa que la semilla no está habilitada en ese invernadero y ofrece habilitarla con CMP-HAB-IIN ·
   Habilitar Insumo en Invernadero.
2.  Si el Agrónomo la habilita, el caso de uso continúa en el paso 8. Si no, selecciona otra variedad (vuelve al paso
   5) o cancela.
8c. El stock libre de semilla de la variedad en el invernadero no cubre la cantidad de plantines:
1.  El Sistema informa el stock libre de semilla de la variedad en el invernadero.
2.  El Agrónomo reduce la cantidad de plantines (vuelve al paso 7), selecciona otra variedad (vuelve al paso 5) o
   cancela.
8d. La cantidad de plantines supera, en alguna etapa del ciclo de la variedad, la suma de los agujeros de los sectores
   de ese tipo de etapa del invernadero que están activos o fuera de servicio:
1.  El Sistema informa en qué etapa se supera el tope y cuál es la cantidad máxima de plantines que admite el
   invernadero.
2.  El Agrónomo reduce la cantidad de plantines (vuelve al paso 7), selecciona otra variedad (vuelve al paso 5) o
   cancela.
8e. La cantidad de plantines supera la capacidad libre total de los sectores de germinación compatibles con la
   variedad:
1.  El Sistema informa la capacidad libre total disponible.
2.  El Agrónomo reduce la cantidad de plantines (vuelve al paso 7) o cancela.
10-11a. El Agrónomo quita un sector ya asignado o cambia su cantidad:
1.  El Sistema actualiza la distribución y la cantidad que resta distribuir.
2.  El caso de uso continúa en el paso 10.
11a. La cantidad indicada supera la capacidad libre del sector:
1.  El Sistema señala el error e informa la capacidad libre del sector.
2.  El Agrónomo indica una cantidad menor o elige otro sector (vuelve al paso 10).
11b. La cantidad indicada supera la cantidad de plantines que resta distribuir:
1.  El Sistema señala el error e informa la cantidad que resta distribuir.
2.  El Agrónomo corrige la cantidad (vuelve al paso 10).
13a. El Agrónomo no requiere insumos adicionales:
1.  El caso de uso continúa en el paso 15 y reserva únicamente la semilla.
14a. La cantidad indicada de un insumo adicional supera su stock libre en el invernadero:
1.  El Sistema señala el error e informa el stock libre del insumo.
2.  El Agrónomo corrige la cantidad o quita el insumo (vuelve al paso 13).
17a. El Agrónomo quiere corregir un dato del resumen:
1.  El Agrónomo indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 7, 10, 13 o
   15).
1.  Si cambia la variedad o la cantidad de plantines, el Sistema descarta la distribución por sector y repite las
   verificaciones desde el paso 8.
18a. Ya existe una orden de trabajo de siembra con los mismos valores en todos sus atributos (sin contar el
   identificador):
1.  El Sistema rechaza el registro e informa el identificador de la orden existente.
2.  El Agrónomo corrige algún dato (vuelve a 17a) o cancela.
18b. Entre las verificaciones y la confirmación, otra operación comprometió semilla, insumos o espacio del
   invernadero, o cambió su compatibilidad:
1.  El Sistema vuelve a verificar la compatibilidad, el stock libre y la capacidad libre al momento de registrar.
2.  Si alguna verificación ya no se cumple, el Sistema no registra nada e informa qué dato cambió.
3.  El caso de uso vuelve al paso afectado (5, 8, 11 o 14).
19a. El Sistema no logra entregar la notificación al Capataz:
1.  La orden permanece registrada y visible entre las órdenes asignadas al Capataz.
2.  El Sistema reintenta el envío y avisa al Agrónomo que la notificación está pendiente.

Requisitos especiales
- Tras cada selección o dato ingresado por el Agrónomo (pasos 3 a 15), la pantalla se actualiza con las verificaciones
   y los valores calculados en no más de 1 segundo.
- El registro del paso 18 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un
   indicador de progreso.
- El paso 18 se ejecuta como una única transacción: la orden, las ocupaciones de sector, los agujeros comprometidos,
   las reservas de insumo y los logs se registran juntos o no se registra ninguno.
- El control de concurrencia sobre el stock libre de insumos y la capacidad libre de los sectores impide la
   sobreasignación entre planificaciones simultáneas.
- Solo el rol Agrónomo accede a este caso de uso, y únicamente sobre los invernaderos que tiene a cargo.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Stock libre: cantidad actual del insumo en el invernadero, sin contar los lotes vencidos a la fecha programada (a la
   fecha actual, mientras no se haya indicado), menos la suma de las cantidades reservadas en sus reservas de insumo
   en estado "activa". (Pasos 4, 8, 12, 13 y 14 )
- Capacidad libre de un sector: agujeros disponibles del sector menos agujeros comprometidos del sector. (Pasos 8, 9 y
   11)
- Capacidad por etapa: no se planifica una siembra si el invernadero no tiene, para cada etapa del ciclo de la
   variedad, al menos un sector de ese tipo de etapa activo o fuera de servicio, ni si la cantidad de plantines
   supera, en alguna etapa, la suma de los agujeros totales de esos sectores. Los sectores fuera de servicio cuentan
   para estas dos verificaciones, pero no se ofrecen para ubicar plantines. Los sectores inactivos no cuentan. Una
   planta ocupa un agujero en todas las etapas. (Extensiones 5c y 8d)
- Compatibilidad por perfil familiar: un sector es compatible si no contiene lotes con ocupaciones vigentes ni
   ocupaciones de órdenes de siembra "a realizar", o si todos ellos pertenecen al mismo perfil familiar que la
   variedad a sembrar. (Paso 9)
- Umbral efectivo: intersección de los rangos mínimo y máximo de temperatura ambiente, humedad, intensidad lumínica y
   fotoperíodo de las variedades de todos los lotes activos y órdenes de siembra "a realizar" del invernadero. La
   variedad nueva es compatible si, al sumarla, ninguna intersección queda vacía. Es una validación bloqueante y se
   aplica aunque el invernadero no posea un sistema IoT. (Pasos 4 y 5)
- Fecha estimada de cosecha: fecha programada más la suma de las duraciones de las etapas anteriores a Maduración, es
   decir, la fecha estimada de entrada a Maduración. No es un atributo. (Pasos 8 y 16)
- Semilla de la variedad: insumo de tipo Semilla asociado a la variedad seleccionada, registrado en el mismo
   invernadero de la orden. (Pasos 4 y 8)
- Insumos adicionales: insumos activos del mismo invernadero que no pertenezcan a las categorías del sistema
   (Semillas, Envases, Repuestos de hardware e Infraestructura). (Pasos 12, 13 y 14)
- Capataz del invernadero: Capataz asignado al invernadero. Cada invernadero tiene un único Capataz. (Pasos 4 y 18)
- Prioridad: opcional (alta, media o baja). Si no se indica, la orden se ordena como si fuera media. (Paso 7)

Lista de tecnología y variaciones de datos
5a. La variedad puede buscarse por nombre de cultivo o por nombre de variedad.
7a. La cantidad de plantines es un número entero positivo expresado en unidades. Una semilla da origen a un plantín,
   por lo que la cantidad de semilla a reservar es igual a la cantidad de plantines.
7b. La fecha programada se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.
10a. La capacidad de los sectores se mide en agujeros; cada plantín ocupa un agujero.
12a. Los insumos adicionales pueden buscarse por nombre.
13a. La cantidad de cada insumo adicional se expresa en la unidad de medida propia del insumo (unidades, gramos,
   litros, etc.).
17a. La notificación al Capataz se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.
Frecuencia: a confirmar con el Jardín Botánico. Por la regla de producción constante y escalonada, se espera que
   ocurra de forma periódica, varias veces por mes en cada invernadero.

Temas abiertos
- ¿Con qué frecuencia real se siembra en cada invernadero?
- ¿Qué pasa con las órdenes "a realizar" de un invernadero si su Capataz se da de baja o es reemplazado? [Resuelto el
   08/11/2026 (MD-60; regla 3 de 8.22): el invernadero conserva al Capataz inactivo hasta que el Gerente asigna a otro
   al modificar el invernadero; al asignarlo, pasan al nuevo las órdenes a realizar del saliente. ]
- ¿Un plantín ocupa siempre un agujero, o la densidad de la variedad modifica esa relación? [Resuelto el 15/11/2026
   (MD-68 y MD-69): sí. Una planta ocupa un agujero en todas las etapas y la densidad de la variedad deja de existir.]
- ¿Debe rechazarse una semilla cuya fecha de vencimiento sea anterior a la fecha programada? [Resuelto el 15/11/2026
   (MD-84): el stock libre no cuenta los lotes que estarán vencidos en la fecha programada, así que una semilla
   vencida a esa fecha no se reserva.]
- ¿Qué variables ambientales forman el umbral efectivo? Este caso de uso considera temperatura ambiente, humedad,
   intensidad lumínica y fotoperíodo.
- "Cancelar Orden" debe pasar a "cancelada" las reservas de insumo de la orden de siembra y reducir los agujeros
   comprometidos de cada sector en la cantidad de agujeros planificados de su ocupación.

---

## PROD-CNC-SMB · Concretar Siembra

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Órdenes.
Actor principal: Capataz.
Versión: 0.5

Personal involucrado e intereses
- Capataz: quiere registrar rápido y sin errores lo que realmente se sembró, poder informar diferencias con lo
   planificado y devolver lo que no se utilizó, sin que eso le genere trabajo adicional.
- Agrónomo: quiere saber cuándo se concretó cada siembra y con qué diferencias respecto de lo planificado. También
   quiere que el lote quede creado en la etapa de germinación y ubicado en sus sectores, para poder planificar su
   transición.
- Gerente: quiere que el costo de la semilla y de los insumos utilizados quede imputado a la producción en proceso
   desde el origen del lote, con trazabilidad completa en la auditoría y en el libro diario.
- Vendedor: quiere que la cantidad real sembrada quede registrada, porque de ella depende la producción que podrá
   comprometer en contratos futuros.
- Organización (Jardín Botánico): quiere que el stock de insumos y la ocupación de los sectores reflejen la realidad
   del invernadero, y que la semilla y el espacio no utilizados vuelvan a estar disponibles para otras siembras.
Relaciones con otros casos de uso: no incluye («include») otros casos de uso ni es extendido («extend») por ellos.

Precondiciones
a. El Capataz está autenticado en el Sistema.
b. Existe al menos una orden de trabajo de siembra en estado "a realizar" asignada al Capataz.
c. Existe un ejercicio contable vigente. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*
d. Existen las cuentas contables "Productos en Proceso" e "Insumos en Stock". *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*

Garantías mínimas
- La operación es atómica. Si el caso de uso se cancela o falla, la orden permanece en estado "a realizar", sus
   reservas de insumo siguen en estado "activa", y no se registra ningún lote, consumo, movimiento de insumo, asiento
   contable ni log de auditoría parcial.
- Si el caso de uso no termina con éxito, los agujeros comprometidos y disponibles de los sectores y el stock actual
   de los insumos quedan con sus valores anteriores.
- Una orden de siembra se concreta una única vez.

Garantías de éxito (Postcondiciones)
a. La orden de trabajo de siembra pasó de estado "a realizar" a "concretada", con la fecha de resolución igual a la
   fecha actual, la fecha de siembra igual a la fecha efectiva indicada por el Capataz y, si el Capataz lo indicó, el
   motivo de la diferencia.
b. Se creó un lote en estado "activo", con cantidad inicial y cantidad actual iguales al total de plantines sembrados.
   Está asociado a la siembra, al invernadero de la orden y a la etapa productiva de tipo "Germinación" del ciclo de
   la variedad. El costo acumulado del lote es la suma de los montos de consumo de la siembra; su costo por planta es
   ese costo dividido por la cantidad actual del lote.
c. En cada ocupación de sector de la siembra se registró la cantidad de agujeros ocupados, igual a la cantidad de
   plantines realmente sembrados en ese sector; la cantidad de agujeros planificados no se modificó. Cada ocupación de
   sector con al menos un plantín sembrado quedó asociada al lote creado. Las ocupaciones de sector sin plantines
   sembrados se conservan como parte de la siembra, con cero agujeros ocupados, y no se asocian a ningún lote.
d. En cada sector de la siembra, la cantidad de agujeros comprometidos se redujo en la cantidad de agujeros
   planificados de su ocupación, y la cantidad de agujeros disponibles se redujo en la cantidad de agujeros ocupados.
e. La reserva de insumo de la semilla quedó con cantidad utilizada igual al total de plantines sembrados, cantidad
   devuelta igual a la propuesta por el Sistema o a la indicada por el Capataz, y estado "consumida".
f. Cada reserva de insumo adicional quedó con la cantidad utilizada y la cantidad devuelta propuestas por el Sistema o
   indicadas por el Capataz. Pasó a estado "consumida" si la cantidad consumida es mayor a cero, o a "cancelada" si es
   cero.
g. La cantidad disponible de los lotes de cada insumo, en el invernadero de la orden, se redujo en la cantidad
   consumida, tomada de los lotes propuestos por el Sistema con el criterio FEFO o corregidos por el Capataz. Si los
   lotes no cubrían la cantidad consumida, el resto salió del lote «faltante sin lote» del insumo, que quedó con
   cantidad negativa. El stock actual del insumo, que es la suma de sus lotes, bajó en la cantidad consumida.
h. Por cada reserva con cantidad consumida mayor a cero, se registró un consumo en la bitácora del lote, con tipo de
   evento "siembra". El consumo tiene la cantidad consumida (cantidad reservada menos cantidad devuelta), el monto de
   consumo calculado, la fecha de consumo igual a la fecha efectiva de siembra y el Capataz como responsable. Está
   asociado a la siembra, al insumo del invernadero, al lote, a su etapa productiva y al invernadero.
i. Por cada consumo registrado y por cada lote de insumo del que salió cantidad, se registró un movimiento de insumo
   de salida con la cantidad tomada de ese lote y la fecha efectiva de siembra, asociado al insumo del invernadero, al
   lote de insumo, al lote de la siembra, y originado en el consumo.
j. Por cada consumo registrado, se generó un asiento contable en el libro diario del ejercicio vigente, originado en
   el consumo, que debita la cuenta "Productos en Proceso" y acredita la cuenta "Insumos en Stock" por el monto del
   consumo.
k. Se envió al Agrónomo que planificó la orden una notificación de la siembra concretada, indicando las diferencias
   entre lo planificado y lo realmente sembrado y utilizado, y el motivo de la diferencia, si los hubo.
l. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la orden de trabajo de siembra y los
   cambios en su estado, su fecha de resolución, su fecha de siembra y su motivo de la diferencia.
m. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del lote creado.
n. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor de cada ocupación de
   sector, cada sector, cada reserva de insumo y cada insumo del invernadero modificados.
o. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada consumo, cada movimiento de
   insumo y cada asiento contable creados.
p. Si algún insumo quedó con el stock sin lotes vencidos negativo o sin cubrir las reservas activas, hay una alerta
   «stock inconsistente» activa dirigida al Agrónomo responsable del invernadero.

Escenario principal de éxito (o Flujo Básico)
1.  El Capataz inicia la concreción de una siembra.
2.  El Sistema presenta las órdenes de trabajo de siembra en estado "a realizar" asignadas al Capataz, indicando para
   cada una el invernadero, la variedad, la cantidad de plantines y la fecha programada.
3.  El Capataz selecciona una orden.
4.  El Sistema presenta el detalle de la orden: cultivo y variedad, cantidad de plantines planificada, fecha
   programada, distribución planificada por sector e insumos reservados con sus cantidades. Propone como fecha
   efectiva la fecha actual y, para cada sector, la cantidad planificada como cantidad sembrada.
5.  El Capataz confirma o modifica la fecha efectiva de siembra.
6.  El Sistema verifica que la fecha efectiva esté comprendida entre la fecha de creación de la orden y la fecha
   actual.
7.  El Capataz indica, para un sector de la distribución planificada, la cantidad de plantines realmente sembrados en
   él.
8.  El Sistema verifica que la cantidad no supere la planificada para ese sector y presenta el total sembrado frente
   al planificado. Si el total es menor al planificado, informa la diferencia y que la semilla no utilizada y los
   agujeros no ocupados quedarán liberados.
*El Capataz repite los pasos 7-8 por cada sector en el que sembró una cantidad distinta de la propuesta. En los demás
   sectores se toma la cantidad propuesta.*
9.  El Capataz indica que terminó de registrar la siembra por sector.
10.  El Sistema verifica que el total sembrado sea de al menos un plantín y establece la cantidad de semilla utilizada
   igual al total sembrado.
11.  El Sistema presenta la semilla y los insumos adicionales reservados para la orden. Para cada reserva presenta la
   cantidad reservada, la cantidad utilizada propuesta (para la semilla, el total sembrado; para cada insumo
   adicional, la cantidad reservada), la cantidad devuelta propuesta (reservada menos utilizada) y la cantidad
   consumida.
12.  El Capataz indica la cantidad realmente utilizada de un insumo adicional.
13.  El Sistema verifica que la cantidad utilizada no supere la reservada, propone la cantidad devuelta igual a la
   reservada menos la utilizada y presenta la cantidad consumida.
*El Capataz repite los pasos 12-13 por cada insumo adicional cuya cantidad utilizada difiere de la propuesta.*
14.  El Capataz reduce la cantidad devuelta de una reserva.
15.  El Sistema verifica que la cantidad devuelta no supere la reservada menos la utilizada y presenta la cantidad
   consumida.
*El Capataz repite los pasos 14-15 por cada reserva en la que parte del sobrante se dañó o se extravió. En las demás
   se toma la cantidad devuelta propuesta.*
16.  El Capataz solicita el resumen de la concreción.
17.  El Sistema presenta el resumen de la concreción: fecha efectiva, total sembrado frente al planificado, motivo de
   la diferencia si lo hay, distribución real frente a la planificada por sector, y cantidades utilizadas, devueltas y
   consumidas de la semilla y de los insumos adicionales, y los lotes de insumo de los que sale cada cantidad
   consumida, propuestos por el Sistema con el criterio FEFO (sale primero lo que vence primero).
18.  El Capataz confirma la concreción.
19.  El Sistema registra la orden como concretada, crea el lote en la etapa de germinación, actualiza las ocupaciones
   de sector y los agujeros de cada sector, resuelve las reservas de insumo, descuenta de los lotes el stock consumido
   (y, si los lotes no alcanzan, del lote «faltante sin lote»), registra los consumos, los movimientos de insumo (uno
   por lote) y los asientos contables, y registra la auditoría correspondiente.
20.  El Sistema notifica al Agrónomo que planificó la orden que la siembra fue concretada.
21.  El Sistema informa al Capataz que la siembra fue concretada y presenta el identificador del lote creado.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 19, el Capataz cancela la concreción:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio y la orden permanece en estado "a realizar".
*b. En cualquier momento el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Capataz que la siembra no fue concretada.
3.  El Capataz reinicia el caso de uso desde el paso 1.
6a. La fecha efectiva es posterior a la fecha actual:
1.  El Sistema señala el error y rechaza la fecha.
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).
6b. La fecha efectiva es anterior a la fecha de creación de la orden:
1.  El Sistema señala el error e informa la fecha de creación de la orden.
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).
8a. La cantidad indicada supera la cantidad planificada para el sector:
1.  El Sistema señala el error e informa la cantidad planificada para ese sector.
2.  El Capataz corrige la cantidad (vuelve al paso 7).
9a. El total sembrado es menor al planificado:
1.  El Capataz indica, opcionalmente, el motivo de la diferencia.
2.  El caso de uso continúa en el paso 10.
10a. El total sembrado es cero:
1.  El Sistema informa que no es posible concretar una siembra sin plantines sembrados.
2.  El Capataz corrige las cantidades (vuelve al paso 7) o cancela el caso de uso. La orden permanece en estado "a
   realizar" hasta que el Agrónomo la cancele.
11a. La orden no tiene insumos adicionales reservados:
1.  El Sistema presenta solo la reserva de la semilla y el caso de uso continúa en el paso 14.
12a. El Capataz no utilizó un insumo adicional:
1.  El Capataz indica cero como cantidad utilizada.
2.  En el paso 13, el Sistema informa además que, si no se registra pérdida, la reserva de ese insumo será cancelada.
13a. La cantidad utilizada de un insumo adicional supera la cantidad reservada:
1.  El Sistema señala el error e informa la cantidad reservada del insumo.
2.  El Capataz corrige la cantidad (vuelve al paso 12).
15a. La cantidad devuelta supera la cantidad reservada menos la utilizada:
1.  El Sistema señala el error e informa la cantidad máxima que se puede devolver.
2.  El Capataz corrige la cantidad (vuelve al paso 14).
17a. El Capataz quiere corregir un dato del resumen:
1.  El Capataz indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 7, 9, 12 o 14).
   El motivo de la diferencia se corrige en el paso 9.
2.  Si corrige una cantidad sembrada, el Capataz vuelve a indicar que terminó el registro (paso 9) y el Sistema repite
   las verificaciones desde el paso 10.
17b. El Capataz quiere cambiar los lotes de los que sale un insumo:
1.  El Capataz indica, para ese insumo, los lotes y las cantidades que toma de cada uno.
2.  El Sistema verifica que la cantidad de cada lote no supere su cantidad disponible y que el total sea igual a la
   cantidad consumida. Lo que los lotes no cubren sale del lote «faltante sin lote».
3.  El caso de uso vuelve al paso 17.
19a. La orden ya no se encuentra en estado "a realizar" al momento de registrar (por ejemplo, el Agrónomo la canceló
   mientras el Capataz ingresaba los datos):
1.  El Sistema no registra ningún cambio e informa al Capataz el estado actual de la orden.
2.  El caso de uso termina.
19b. Los lotes de un insumo en el invernadero no cubren la cantidad consumida:
1.  El Sistema toma de los lotes todo lo que hay disponible y el resto del lote «faltante sin lote» del insumo, que
   queda con cantidad negativa. La concreción no se rechaza.
2.  El Sistema activa la alerta «stock inconsistente», dirigida al Agrónomo responsable del invernadero. La alerta se
   resuelve sola cuando el stock vuelve a cubrir las reservas.
3.  El caso de uso continúa en el paso 19.
20a. El Sistema no logra entregar la notificación al Agrónomo:
1.  La concreción permanece registrada.
2.  El Sistema reintenta el envío.
3.  En el paso 21, el Sistema avisa además al Capataz que la notificación al Agrónomo quedó pendiente.

Requisitos especiales
- Tras cada dato ingresado por el Capataz (pasos 3 a 15), la pantalla se actualiza con las verificaciones y los
   valores calculados en no más de 1 segundo.
- El registro del paso 19 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un
   indicador de progreso.
- El paso 19 se ejecuta como una única transacción: todos los cambios y registros se confirman juntos o no se confirma
   ninguno.
- El control de concurrencia impide que una misma orden se concrete dos veces, o que se concrete y se cancele al mismo
   tiempo.
- Solo el Capataz asignado a la orden puede concretarla.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos de consumo y de los asientos contables se expresan en pesos argentinos, con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.
- La interfaz del Capataz está diseñada para teléfonos celulares.

Reglas de negocio
- Valores propuestos: el Sistema propone la fecha actual como fecha efectiva, la cantidad planificada como cantidad
   sembrada de cada sector, la cantidad reservada como cantidad utilizada de cada insumo adicional y la reservada
   menos la utilizada como cantidad devuelta. El Capataz solo indica los valores que difieren de lo propuesto; los
   demás se toman tal como los propone el Sistema. (Pasos 4, 5, 7, 11, 12 y 14)
- Fecha efectiva válida: fecha comprendida entre la fecha de creación de la orden y la fecha actual, ambas inclusive.
   (Paso 6)
- Cantidad sembrada válida: en cada sector, un número entero entre cero y la cantidad planificada para ese sector. En
   total, al menos un plantín. No se admiten sectores fuera de la distribución planificada. (Pasos 8 y 10)
- Semilla utilizada: igual al total de plantines sembrados, porque una semilla da origen a un plantín. (Paso 10)
- Cantidad devuelta: la propone el Sistema como cantidad reservada menos cantidad utilizada. El Capataz puede
   reducirla si parte del sobrante se dañó o se extravió. Nunca es negativa ni supera esa diferencia. (Pasos 11, 13,
   14 y 15)
- Cantidad consumida: cantidad reservada menos cantidad devuelta. Incluye lo utilizado y lo dañado o extraviado. La
   regla 13 de 8.9 la define como máx(reservada, utilizada) − devuelta, y la regla 24 de 8.8 propone una devuelta de
   máx(0, reservada − utilizada); acá las dos fórmulas se simplifican porque la cantidad utilizada nunca supera la
   reservada (paso 13 y extensión 13a). (Pasos 11 a 19) f
- Resolución de reservas: una reserva pasa a "consumida" si la cantidad consumida es mayor a cero, y a "cancelada" si
   es cero. Ninguna reserva de una orden concretada permanece "activa". (Paso 19)
- Monto de consumo: cantidad consumida multiplicada por el precio de referencia del insumo en el invernadero de la
   orden. (Paso 19)
- Lotes de salida: el Sistema propone los lotes de los que sale cada insumo con el criterio FEFO y el Capataz puede
   corregirlos. Cada lote aporta como máximo su cantidad disponible; lo que no cubren los lotes sale del lote
   «faltante sin lote». (Pasos 17 y 19, y extensiones 17b y 19b)
- Costo del lote: el costo acumulado del lote nuevo es la suma de los montos de consumo de su siembra, y su costo por
   planta es ese costo dividido por la cantidad actual del lote. (Paso 19)
- Liberación de agujeros: en cada sector, los agujeros comprometidos se reducen en la cantidad de agujeros
   planificados de la ocupación y los agujeros disponibles se reducen en la cantidad de agujeros ocupados. (Paso 19)
- Etapa inicial del lote: etapa productiva de tipo "Germinación" del ciclo de la variedad sembrada. (Paso 19)
- Stock que no cubre el consumo: si los lotes de un insumo no cubren la cantidad consumida, la concreción no se
   rechaza: el resto sale del lote «faltante sin lote» del insumo, que es el único lote que puede tener cantidad
   negativa, y se activa la alerta «stock inconsistente» (reglas 5 y 6 de 8.13, modificadas por MD-85). La alerta es
   dinámica: está activa mientras el stock sin lotes vencidos sea negativo o no cubra las reservas, y se resuelve sola
   cuando vuelve a cubrirlas. La regularización la hace primero la recepción pendiente del insumo, si la hay; si no,
   un ajuste (regla 4 de 8.19). (Extensión 19b)

Lista de tecnología y variaciones de datos
5a. La fecha efectiva se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El Sistema propone por defecto
   la fecha actual.
7a. La cantidad sembrada por sector es un número entero expresado en unidades. El Sistema propone por defecto la
   cantidad planificada para cada sector.
12a. La cantidad utilizada de cada insumo adicional se expresa en la unidad de medida propia del insumo (unidades,
   gramos, litros, etc.). El Sistema propone por defecto la cantidad reservada.
14a. La cantidad devuelta se expresa en la unidad del insumo. El Sistema propone por defecto la cantidad reservada
   menos la utilizada.
20a. La notificación al Agrónomo se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.
Frecuencia: una vez por cada orden de trabajo de siembra planificada. Depende de la frecuencia de siembra de cada
   invernadero, que está a confirmar con el Jardín Botánico.

Temas abiertos
- ¿Qué sucede con las órdenes de siembra "a realizar" cuya fecha programada ya pasó hace varios días sin ser
   concretadas? ¿Se notifica al Agrónomo?

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-46, D-50)

Los dos casos de uso están escritos para el sistema completo. Esta sección dice qué se recorta, qué se cambia y dónde va cada cosa. **Manda el caso de uso** salvo donde se diga lo contrario (D-07).
Las decisiones de modelo (herencia, agujeros derivados, costo guardado) están en D-50 y en `docs/modelo/produccion.md`.

### Qué hace cada parte, y con qué se completa

| Parte | Código | Observaciones |
|---|---|---|
| Planificar siembra | `produccion/servicios/siembras.py`: `datos_de_planificacion`, `resumen_de_planificacion`, `planificar_siembra(actor, datos)` | El resumen valida todo y no escribe; `planificar_siembra` vuelve a verificar bajo bloqueo |
| Concretar siembra | `produccion/servicios/siembras.py`: `datos_de_concrecion`, `resumen_de_concrecion`, `concretar_siembra(actor, orden_id, datos)` | Mismo esquema |
| Bandeja del Capataz y lista de órdenes | `produccion/servicios/ordenes.py`: `bandeja_del_capataz`, `lista_de_ordenes` | Solo lectura. Sección de inicio del Capataz (`registrar_seccion_de_inicio`) |
| Lotes (lectura) | `produccion/servicios/lotes.py`: `lotes_activos_de`, `fecha_de_entrada_a_la_etapa`, `fecha_estimada_de_fin_de_etapa` | Alimenta la pestaña «Lotes activos» de la ficha del invernadero y la bandeja |
| Costo | `produccion/servicios/costos.py` | Ver `docs/patrones/costo_del_lote.md` |
| Conexiones con otras apps | `produccion/apps.py`, `ready()` | Los registrantes de más abajo |

### Lo que NO se hace en la ronda (D-45)

- ~~**Asientos contables** (postcondición j de PROD-CNC-SMB, y las precondiciones de ejercicio vigente y de cuentas «Productos en Proceso» e «Insumos en Stock»): no se verifican ni se crean. El consumo queda con su monto; el asiento lo generará
  `contabilidad` cuando exista. Se anota en `docs/temas_abiertos.md`.~~ **Hecho en CON-04a (25/11/2026):** un asiento por consumo, Debe «Productos en Proceso» / Haber «Insumos en Stock» por `monto_consumo`, con la fecha efectiva de la siembra (`produccion/servicios/asientos_de_produccion.py`). Las precondiciones c y d se cumplen solas (D-92 punto 2).
- (Antes de D-52 el «origen» no se implementaba; ahora sí: `Bitacora` y `OrdenTrabajo` heredan de `contabilidad.OrigenDocumento` y los movimientos de insumo del consumo lo tienen como `origen`.)
- Cosechas, entregas y mantenimiento: no existen. Las únicas órdenes son siembras y transiciones.

### Decisiones de aplicación (donde el caso de uso no baja al detalle)

**Permisos y alcance.**
- Planificar: solo el **Agrónomo**, solo sobre sus invernaderos a cargo (regla de acceso de `maestros`). Concretar: solo el **Capataz asignado a la orden** (el de `Siembra.capataz`, D-53). Cancelar: ver `cancelar_orden.md`.
- El Gerente no ve estas pantallas (404), igual que «Cultivos». Las vistas de lectura de órdenes y lotes sí las ve el Gerente (solo lectura) y el Agrónomo a cargo.
- Todo servicio verifica que quien actúa siga activo **después de bloquear** (D-30/32).

**Bloqueos (D-30, D-32, D-40; `docs/patrones/bloqueos.md`, sección `produccion`).** Orden: cuentas → invernadero (`bloquear_invernadero_activo`) → **variedad** (`bloquear_variedad`, incluso al concretar: la variedad no puede darse de baja ni
cambiar de perfil a mitad de camino) → **sectores** (`bloquear_sectores`, en orden de id; nivel 2c nuevo) → insumos (`TipoInsumo` → `Insumo` → `InsumoInvernadero` → `LoteInsumo`) → filas de `produccion` (orden, lote, ocupaciones, reservas).
Las filas que dicen qué bloquear (los sectores de la orden, sus reservas) se leen **sin bloquear**, se bloquean y se **releen**. Si algo cambió: `cambio_simultaneo`, sin reintentar (extensiones 18b y 19a).

**Planificar (PROD-PNF-SMB).**
- Las verificaciones de los pasos 4 a 14 se hacen en el resumen y se **repiten dentro de `planificar_siembra` después de bloquear** (extensión 18b): compatibilidad por umbral, semilla habilitada, stock libre (`stock.disponible_para_planificar(ids, fecha)`), capacidad por etapa, capacidad libre de cada sector, perfil familiar del sector, insumos adicionales.
- **Stock libre** = lo que da `inventario` (lotes no vencidos a la fecha programada − reservas activas). La suma de reservas activas la informa `produccion` (`registrar_reservas_de_insumo`); ver `docs/api/produccion.md`.
- **Umbral efectivo**: intersección de los rangos de las variedades de los lotes activos y de las órdenes «a realizar» del invernadero. **No se calcula en `produccion`**: lo da `umbral_efectivo([invernadero_id])` de `inventario`, y la compatibilidad de la variedad elegida (paso 4, extensión 4b y verificación bajo bloqueo de la 18b), `variables_incompatibles(umbral, rangos_de([variedad_id])[variedad_id])`. Las dos están en la sección «Umbral efectivo» de `docs/api/variedades.md` (21/11/2026): es la misma función que usa el módulo IoT (IOT-ENT-INF, «Requisitos especiales»). Sin lotes ni órdenes, el umbral es `None` y toda variedad es compatible. Se aplica **aunque el invernadero no tenga IoT**.
- **Capacidad libre** de un sector = `agujeros_de(sector).disponibles` de `maestros`, que ya resta ocupados y comprometidos (`registrar_agujeros_de_sector`). Los sectores **fuera de servicio** cuentan para las extensiones 5c y 8d pero no se ofrecen para ubicar (`maestros` los distingue por estado).
- **Duplicado (18a)**: se rechaza una orden **idéntica** (mismo invernadero, variedad, cantidad, fecha programada, prioridad, descripción, fecha de creación, Agrónomo, Capataz, misma distribución por sector y mismas reservas). Mensaje con el código de la orden existente (`OT-0007`).
- **Sin Capataz activo (extensión 3a)**: se bloquea. El prototipo solo avisaba: manda el caso de uso. En el paso 2 la pantalla ya muestra el invernadero con su motivo.
- **Habilitar la semilla (8b)**: el prototipo la ofrece al elegir la variedad (paso 5), el CU en el paso 8; el efecto es el mismo y se deja como el prototipo. Usa `insumos_invernadero.habilitar_insumo` de INV-02; al volver, el caso continúa.
- **Prioridad** opcional (MD-73): sin valor = media al ordenar.
- **Reservas**: una por insumo (la semilla con `cantidad = plantines` y cada adicional), estado `activa`, `fecha_reserva` = hoy. Un adicional no puede ser de las categorías del sistema.
- **Auditoría (D-36, un registro por CU)**: acción `planificacion_siembra`; afectados: la orden, cada ocupación, cada reserva y cada sector (cambio de texto «agujeros comprometidos» antes → después; D-50 punto 4); `datos` con variedad, cantidad, fecha, Capataz.
  Las tres postcondiciones g, h, i del CU son **un solo registro**.
- **Notificación** (postcondición f): `notificar(capataz, …)` **dentro de la transacción** (D-42). La extensión 19a («no logra entregar») no aplica.

**Concretar (PROD-CNC-SMB).**
- **Fecha efectiva**: entre `fecha_creacion_orden` y hoy, ambas inclusive. Es la fecha de la siembra, del consumo y de los movimientos.
- **Cantidades por sector**: entre 0 y lo planificado; total ≥ 1 (10a). Las ocupaciones con 0 se conservan, sin lote.
- **Reservas**: `cantidad_utilizada` de la semilla = total sembrado; la de un adicional la indica el Capataz (≤ reservada, 13a); `cantidad_devuelta` ≤ `reservada − utilizada` (15a). Consumido = `reservada − devuelta`. Estado `consumida` si consumido > 0, si no `cancelada`.
- **Lotes de insumo**: `inventario.stock.proponer_lotes_fefo(iin_id, cantidad, fecha)` propone; el Capataz puede cambiarlos (17b) y el servicio valida que cada parte no supere el disponible y que la suma sea la consumida. Lo que no cubren los lotes sale del lote
  «faltante sin lote» (extensión 19b): **no se rechaza**. Después de salir, `reevaluar_alertas_del_insumo` (alerta «stock inconsistente», de `inventario`).
- **Salida**: `stock.registrar_salida_por_consumo(iin_id, partes, fecha=fecha_efectiva)` (D-50 punto 7; INV-02 lo prepara con `fecha` opcional). Se llama con `origen_id` = el `Consumo` (D-52 punto 5), **que se crea antes** (su monto no depende de los movimientos). Devuelve los `MovimientoInsumo`, ya con `origen = consumo`; no hay tabla de enlace.
- **Consumo y bitácora** (se crean **antes** de la salida de stock: el movimiento los apunta): por cada reserva con consumido > 0, una `Bitacora` de tipo `siembra` (con el hijo `Consumo`): `monto_consumo` = consumido × precio de referencia del `InsumoInvernadero` (2 decimales, `ROUND_HALF_UP`), fecha = fecha efectiva, hora = ahora, responsable = el Capataz.
- **Lote**: `Lote(invernadero, siembra, etapa = la de tipo Germinación del ciclo, cantidad_inicial = cantidad_actual = total sembrado, estado activo, costo_acumulado = Σ montos)`. Código `L-{id}`. Las ocupaciones con ≥ 1 sembrado quedan enlazadas al lote.
- **La cantidad planificada no se toca** (`cant_plantines_siembra`); el prototipo la pisaba (diferencia 6 de `modelo/produccion.md`). `motivo_diferencia_siembra` solo si total < planificado.
- **Agujeros**: no se escribe «disponibles» ni «comprometidos» (son derivados, D-50 punto 4). Sí se audita el cambio de texto «agujeros comprometidos» y «agujeros ocupados» de cada sector, antes y después, en el mismo registro.
- **Auditoría**: un registro `concrecion_siembra` con afectados orden, lote, ocupaciones, sectores, reservas, insumos del invernadero, lotes de insumo, consumos, movimientos y bitácoras.
- **Notificación** al Agrónomo que planificó la orden (si lo hubo y no es quien actúa), con las diferencias, dentro de la transacción (D-42). Si planificó InfoPonia, no se notifica a nadie.
- **Concurrencia (19a)**: si la orden ya no está «a realizar» al registrar → `orden_no_pendiente` con el estado actual; no se escribe nada.
- ~~Las precondiciones de ejercicio y cuentas contables **no se verifican** (D-45).~~ Siguen sin verificarse, pero ya no por estar fuera de la ronda: se cumplen solas (D-92 punto 2).

### Pantallas

- Planificar siembra: `docs/prototipos/produccion/datos_maestros_y_produccion.html` — `INIT['siembra-form']`, `VIEWS['siembra-form']` y las acciones asociadas; el panel «Ritmo sostenible» **no está en ningún caso de uso**: se hace al final, informativo y recortable (el estudiante decide).
- Concretar siembra: `INIT['siembra-concretar']` y sus vistas (diseñada para celular, como pide el CU).
- Bandeja del Capataz: agrupa «vencidas / hoy / próximas»; el CU las ordena por fecha y luego prioridad. Son compatibles: el grupo es una forma de mostrar el mismo orden.
- La pestaña «Lotes activos» de la ficha del invernadero necesita un punto de extensión de `maestros` que MAE-03 no definió: se agrega `registrar_pestana_de_invernadero` (ver `docs/api/extensiones_de_maestros.md`). Si hiciera falta algo más, frená.
- Estilo: Diseño v2 (D-47); sin JavaScript todo debe funcionar igual (cada ventana es una página).

### Registrantes que PRD-01 declara en `ready()` (A4)

| App | Punto | Qué informa |
|---|---|---|
| `maestros` | `registrar_agujeros_de_sector` | Ocupados y comprometidos por sector |
| `maestros` | `registrar_impedimento_de_baja_de_sector` | Ocupaciones vigentes y órdenes «a realizar» |
| `maestros` | `registrar_contenido_de_sector`, `registrar_perfil_de_sector` | Lotes y órdenes que lo usan; perfil familiar |
| `maestros` | `registrar_aviso_de_cambio_de_tipo` | Aviso si el sector tiene lotes u órdenes |
| `maestros` | `registrar_impedimento_de_baja`, `registrar_efecto_de_baja`, `registrar_traspaso` | Invernadero con lotes activos u órdenes; el Capataz saliente pasa sus órdenes «a realizar» al entrante |
| `maestros` | `registrar_pestana_de_invernadero` (nuevo) | «Lotes activos» |
| `inventario` | `registrar_reservas_de_insumo`, `registrar_ordenes_que_reservan` | Reservas activas por insumo; órdenes que las tienen |
| `inventario` | `registrar_uso_de_variedad`, `registrar_variedades_presentes`, `registrar_impedimento_de_baja_de_variedad` | Lotes activos y órdenes «a realizar» (códigos `lotes_activos`, `ordenes_a_realizar`) |
| `core` | `registrar_seccion_de_inicio`, `registrar_asignaciones_de_cuenta` | Bandeja del Capataz; las órdenes que tiene una cuenta |

### Diferencias con el modelo de dominio

Ver «Diferencias con el modelo y con los casos de uso» en `docs/modelo/produccion.md` (costo por planta, cantidad consumida, dónde está el invernadero, cantidad planificada, fecha del movimiento).

### Pruebas

Una prueba por regla y por postcondición con `test_regla_<n>_…` y `test_post_<letra>_…`. Para estos casos: `produccion/tests/test_prod_pnf_smb.py`, `test_prod_cnc_smb.py` y `test_siembras_concurrencia.py` (`@tag("concurrencia")`: dos planificaciones sobre la última semilla o el último agujero;
concretar contra cancelar; concretar dos veces). Pruebas de invariantes en `test_invariantes_produccion.py`.
