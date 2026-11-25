# Casos de uso · produccion · Transición de etapa

Copia para el repo de los casos PROD-PNF-TRN (versión 0.3) y PROD-CNC-TRN del documento de Drive «CU extendidos», más las partes de PROD-REG-MRM que aplican a la
transición, consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026.

Cambios de formato respecto de Drive: en PROD-CNC-TRN se aplicó la **pendiente 2 de pendientes_CU** (los pasos 4 y 5 se fusionan en un solo paso 4 y los siguientes se renumeran: 6–16 pasan a 5–15; las extensiones ya usaban esa numeración);
se quitaron las marcas ⛔ de los títulos. No cambió ninguna regla. El Drive sigue con la numeración vieja hasta que lo corrijas allá.

Son casos de uso extendidos. **El código va en la app `produccion`**; archivos de pruebas: `produccion/tests/test_prod_pnf_trn.py` y `test_prod_cnc_trn.py`.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-PNF-TRN | Planificar Transición | Agrónomo | `produccion/tests/test_prod_pnf_trn.py` |
| PROD-CNC-TRN | Concretar Transición | Capataz | `produccion/tests/test_prod_cnc_trn.py` |
| PROD-REG-MRM (parte) | Registrar Merma, solo lo que aplica desde la transición | (incluido en CNC-TRN) | `produccion/tests/test_mermas_nucleo.py` |

---

## PROD-PNF-TRN · Planificar Transición

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Órdenes.
Actor principal: Agrónomo.
Versión: 0.3

Personal involucrado e intereses
- Agrónomo: quiere trasladar cada lote a su etapa siguiente en el momento justo, con información confiable sobre:
- cuándo termina la etapa actual del lote;
- qué espacio libre hay en los sectores de la etapa destino;
- qué sectores son compatibles con lo que ya se produce en ellos.
- Así sostiene la producción escalonada sin poner en riesgo los lotes en curso.
- Capataz: quiere recibir una orden clara: qué lote, desde qué sectores, hacia qué sectores, cuántas plantas en cada
   uno y para qué fecha. También quiere tener la certeza de que el espacio de destino va a estar libre cuando la
   ejecute.
- Gerente: quiere trazabilidad completa de quién planificó qué y cuándo, y que la planificación no comprometa espacio
   ya asignado a otras órdenes.
- Vendedor: quiere saber con anticipación cuándo un lote va a entrar en maduración y hasta cuándo podrá cosecharse,
   porque de eso depende el stock maduro que puede comprometer en contratos.
- Organización (Jardín Botánico): quiere reducir la merma biológica por debajo del 15 % por ciclo, evitando que un
   traslado a un sector incompatible por perfil familiar afecte a los lotes que conviven en él, o que un lote se pase
   de punto por trasladarse tarde.

Relaciones con otros casos de uso
- No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
- Lo preceden: PROD-CNC-SMB · Concretar Siembra, que crea el lote en la primera etapa de su ciclo, o la concreción de
   la transición anterior del lote.
- Lo siguen:
- PROD-CNC-TRN · Concretar Transición, del Capataz;
- si la orden se cancela, Cancelar Orden (CU-11), que debe liberar los agujeros comprometidos en los sectores destino.
- Si una merma posterior deja al lote con menos plantas que las planificadas, PROD-REG-MRM · Registrar Merma alerta al
   Agrónomo (regla 15 de 8.8).

Precondiciones
a. El Agrónomo está autenticado en el Sistema.
b. El Agrónomo tiene a su cargo al menos un invernadero en estado "activo" con un Capataz activo asignado.
c. En alguno de esos invernaderos existe al menos un lote "activo", con cantidad actual mayor que cero, que no está en
   la última etapa del ciclo de su variedad y que no tiene una orden de transición "a realizar".

Garantías mínimas
- La operación es atómica. Si el caso de uso se cancela o falla, no queda registrada ninguna orden de trabajo,
   ocupación de sector, cambio en los agujeros comprometidos de los sectores, notificación ni log de auditoría
   parcial.
- No se modifican, cualquiera sea la forma en que termine el caso de uso:
- la etapa actual, la cantidad actual y las ocupaciones vigentes del lote;
- los agujeros disponibles de todos los sectores.
- Ningún sector queda comprometido por encima de su capacidad libre, aun cuando dos Agrónomos planifiquen al mismo
   tiempo sobre el mismo invernadero.
- Un lote tiene como máximo una orden de transición "a realizar".
- La transición no reserva insumos.

Garantías de éxito (Postcondiciones)
a. Se creó una orden de trabajo de transición en estado "a realizar", con:
- fecha de creación igual a la fecha actual;
- la fecha programada;
- la descripción, si se indicó;
- la prioridad, si se indicó (alta, media o baja);
- sin fecha de resolución;
- sin cantidad transferida, que se carga al concretarla.
Está asociada al lote que traslada, a la etapa destino (la etapa siguiente del ciclo de la variedad del lote), al
   Agrónomo que la planificó y al Capataz del invernadero.
b. Se crearon una o más ocupaciones de sector como parte de la orden de transición, una por cada sector destino
   indicado. Cada una tiene:
- la cantidad de agujeros planificados en ese sector;
- la cantidad de agujeros ocupados en cero hasta que la transición se concrete;
- todavía sin lote asociado.
La suma de los agujeros planificados es igual a la cantidad actual del lote al momento de planificar.
c. En cada sector destino, la cantidad de agujeros comprometidos se incrementó en la cantidad de agujeros planificados
   de su ocupación.
d. Se envió al Capataz una notificación de la nueva orden asignada.
e. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la orden de trabajo de transición
   creada.
f. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada ocupación de sector creada.
g. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de cada sector modificado y el cambio en
   su cantidad de agujeros comprometidos.

Escenario principal de éxito (o Flujo Básico)
1.  El Agrónomo inicia la planificación de una nueva transición.
2.  El Sistema presenta los lotes trasladables de los invernaderos activos a cargo del Agrónomo. Para cada lote
   indica:
- el identificador y el invernadero;
- el cultivo y la variedad, con su perfil familiar;
- la etapa actual, su fecha de entrada y su fecha estimada de fin;
- la etapa siguiente del ciclo;
- la cantidad actual y los sectores que ocupa, con los agujeros ocupados en cada uno.
3.  El Agrónomo selecciona un lote.
4.  El Sistema presenta:
- la etapa destino, con su tipo de etapa y su duración estimada;
- la cantidad del lote a trasladar, igual a su cantidad actual;
- el Capataz asignado al invernadero;
- la fecha programada propuesta, igual a la fecha estimada de fin de la etapa actual del lote.
5.  El Agrónomo indica la fecha programada: acepta la propuesta o ingresa otra.
6.  El Sistema verifica que la fecha programada sea igual o posterior a la fecha actual y que coincida con la fecha
   estimada de fin de la etapa actual.
7.  El Sistema presenta los sectores elegibles del invernadero, con la capacidad libre de cada uno y la cantidad por
   distribuir, que al inicio es igual a la cantidad del lote. Si la etapa destino es de tipo Maduración, presenta
   además la fecha máxima de cosecha estimada del lote.
8.  El Agrónomo selecciona un sector e indica la cantidad de plantas que ubica en él.
9.  El Sistema registra la asignación al sector y presenta la cantidad por distribuir.
*El Agrónomo repite los pasos 8-9 hasta que la cantidad por distribuir sea cero.
*
10. El Agrónomo termina la distribución e indica, opcionalmente, una descripción para la orden y su prioridad (alta,
   media o baja).
11. El Sistema presenta el resumen de la orden:
- el invernadero, el lote, el cultivo y la variedad;
- la etapa actual y la etapa destino;
- la cantidad del lote;
- los sectores de origen, con los agujeros ocupados en cada uno;
- la distribución por sector destino;
- la fecha programada y, si la etapa destino es Maduración, la fecha máxima de cosecha estimada;
- la prioridad, si se indicó;
- el Capataz responsable.
12. El Agrónomo confirma la planificación.
13. El Sistema registra la orden de trabajo de transición en estado "a realizar" junto con sus ocupaciones de sector
   destino, incrementa los agujeros comprometidos de cada sector destino y registra la auditoría correspondiente.
14. El Sistema notifica al Capataz la nueva orden asignada.
15. El Sistema informa al Agrónomo que la orden fue planificada y presenta su identificador.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 12, el Agrónomo cancela la planificación:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
*b. En cualquier momento el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que la orden no fue planificada.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.
3a. El Agrónomo intenta seleccionar un lote que ya tiene una orden de transición "a realizar":
1.  El Sistema no permite la selección e informa el identificador y la fecha programada de esa orden.
2.  El Agrónomo selecciona otro lote (vuelve al paso 3) o cancela.
3b. El invernadero del lote seleccionado no tiene un Capataz activo asignado:
1.  El Sistema informa que no hay un Capataz que pueda recibir la orden en ese invernadero.
2.  El Agrónomo selecciona otro lote (vuelve al paso 3) o cancela.
3c. El invernadero no tiene sectores elegibles para la etapa destino, o su capacidad libre total es menor que la
   cantidad del lote:
1.  El Sistema no permite continuar con ese lote e informa la capacidad libre total de los sectores elegibles frente a
   la cantidad del lote. Indica también qué sectores del tipo de etapa destino no son compatibles por perfil familiar,
   y con qué lotes u órdenes "a realizar".
2.  El Agrónomo selecciona otro lote (vuelve al paso 3) o cancela.
4a. La fecha estimada de fin de la etapa actual del lote es anterior a la fecha actual:
1.  En el paso 4, el Sistema propone la fecha actual como fecha programada e informa los días de atraso respecto del
   fin estimado de la etapa.
2.  El caso de uso continúa en el paso 5.
6a. La fecha programada es anterior a la fecha actual:
1.  El Sistema señala el error y rechaza la fecha.
2.  El Agrónomo ingresa una nueva fecha (vuelve al paso 5).
6b. La fecha programada difiere de la fecha estimada de fin de la etapa actual:
1.  El Sistema informa la diferencia en días, sin bloquear.
2.  El Agrónomo mantiene la fecha programada y el caso de uso continúa en el paso 7, o ingresa otra fecha (vuelve al
   paso 5).
8-9a. El Agrónomo quita un sector ya asignado:
1.  El Sistema elimina esa asignación y presenta la cantidad por distribuir actualizada.
2.  El caso de uso continúa en el paso 8.
8-9b. El Agrónomo quiere cambiar la cantidad de un sector ya asignado:
1.  El Agrónomo vuelve a indicar ese sector con la nueva cantidad (vuelve al paso 8). La nueva cantidad reemplaza a la
   anterior.
9a. La cantidad indicada para el sector supera su capacidad libre:
1.  El Sistema señala el error e informa la capacidad libre del sector.
2.  El Agrónomo indica una cantidad menor o elige otro sector (vuelve al paso 8).
9b. La cantidad indicada para el sector supera la cantidad por distribuir:
1.  El Sistema señala el error e informa la cantidad por distribuir.
2.  El Agrónomo corrige la cantidad (vuelve al paso 8).
10a. El Agrónomo termina la distribución con cantidad por distribuir mayor que cero:
1.  El Sistema señala el error e informa la cantidad por distribuir.
2.  El Agrónomo continúa asignando sectores (vuelve al paso 8).
11a. El Agrónomo quiere corregir un dato del resumen:
1.  El Agrónomo indica el dato a corregir, y el caso de uso vuelve al paso donde ese dato se ingresó (3, 5, 8 o 10).
1.  Si cambia el lote, el Sistema descarta la fecha y la distribución por sector, y el caso de uso continúa en el paso
   4.
13a. Al registrar, el lote ya no puede trasladarse: tiene otra orden de transición "a realizar", cambió de etapa o
   dejó de estar "activo":
1.  El Sistema no registra ningún cambio e informa qué cambió.
2.  El caso de uso vuelve al paso 2.
13b. Al registrar, cambió la cantidad actual del lote (por ejemplo, por una merma registrada mientras tanto):
1.  El Sistema no registra ningún cambio, informa la nueva cantidad actual y descarta la distribución por sector.
2.  El caso de uso vuelve al paso 7.
13c. Entre las verificaciones y la confirmación, otra operación cambió un sector destino: comprometió espacio en él,
   cambió su compatibilidad por perfil familiar o lo pasó a "fuera de servicio" o a "inactivo":
1.  El Sistema vuelve a verificar la capacidad libre y la compatibilidad de cada sector destino al momento de
   registrar.
2.  Si alguna verificación ya no se cumple, el Sistema no registra nada e informa qué sector cambió.
3.  El caso de uso vuelve al paso 7, conservando las asignaciones que siguen siendo válidas.
13d. Al registrar, el Capataz del invernadero ya no está activo:
1.  El Sistema no registra ningún cambio e informa que el invernadero no tiene un Capataz activo que pueda recibir la
   orden.
2.  El caso de uso vuelve al paso 2.
14a. El Sistema no logra entregar la notificación al Capataz:
1.  La orden permanece registrada y visible entre las órdenes asignadas al Capataz.
2.  El Sistema reintenta el envío y, en el paso 15, avisa al Agrónomo que la notificación está pendiente.

Requisitos especiales
- Tras cada selección o dato ingresado por el Agrónomo (pasos 3 a 10), la pantalla se actualiza con las verificaciones
   y los valores calculados en no más de 1 segundo.
- El registro del paso 13 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un
   indicador de progreso.
- El paso 13 se ejecuta como una única transacción: la orden, las ocupaciones de sector, los agujeros comprometidos y
   los logs se registran juntos o no se registra ninguno. La notificación se envía fuera de la transacción.
- El control de concurrencia cumple tres funciones:
- impide la sobreasignación de la capacidad libre de los sectores entre planificaciones simultáneas (de siembra o de
   transición);
- impide que un mismo lote reciba dos órdenes de transición "a realizar";
- impide que se planifique sobre una cantidad del lote que cambió mientras tanto.
- Solo el rol Agrónomo accede a este caso de uso, y únicamente sobre los invernaderos que tiene a cargo.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Lote trasladable (Pasos 2 y 3, y extensiones 3a y 13a): un lote que cumple todas estas condiciones:
- está "activo", en un invernadero activo a cargo del Agrónomo;
- tiene una cantidad actual mayor que cero;
- su etapa actual no es la última del ciclo de su variedad (la de mayor orden global de su tipo de etapa);
- no tiene otra orden de transición "a realizar"(regla 4 de 8.21)
- Etapa destino (Paso 4): es siempre la etapa siguiente a la actual en el ciclo de la variedad del lote, ordenando las
   etapas por el orden global de su tipo de etapa. La determina el Sistema; el Agrónomo no la elige. Una transición no
   saltea etapas ni vuelve a una anterior. (Regla 1 de 8.20)
- Lote completo (Pasos 4 y 13): la transición traslada siempre el lote entero, es decir, su cantidad actual al momento
   de planificar. (Regla 2 de 8.21)
- La cantidad planificada es la suma de los agujeros planificados de sus ocupaciones destino; la orden no guarda otro
   atributo para ella.
- La cantidad realmente transferida se carga al concretar la transición. Las plantas que se pierdan en el traslado se
   registran en ese momento con Registrar Merma.
- Sectores de origen (Pasos 2 y 11): son los sectores donde el lote tiene ocupaciones vigentes, es decir, con agujeros
   ocupados. (Regla 1 de 8.21)
- Sector elegible (Pasos 7 a 9, y extensión 3c): un sector que cumple todas estas condiciones:
- está "activo" (un sector "fuera de servicio" no se ofrece) y es del mismo invernadero que el lote;
- su tipo de etapa es el tipo de la etapa destino (R092 y R093);
- es compatible por perfil familiar;
- tiene capacidad libre mayor que cero.
- Capacidad libre de un sector (Pasos 7 y 9): agujeros disponibles del sector menos agujeros comprometidos del sector.
- Agujeros comprometidos (Paso 13): la suma de los agujeros planificados de las ocupaciones del sector cuya orden de
   siembra o de transición está "a realizar". (Regla 4 de 8.13, modificada por la ronda 20)
- Compatibilidad por perfil familiar (Paso 7 y extensiones 3c y 13c): un sector es compatible si cumple alguna de
   estas condiciones:
- no contiene lotes con ocupaciones vigentes, ni ocupaciones de órdenes de siembra o de transición "a realizar";
- todos ellos pertenecen al mismo perfil familiar que la variedad del lote.
- Es la misma regla que en Planificar Siembra, ampliada a las transiciones "a realizar" hacia ese sector.
- Umbral ambiental (Paso 7): no se valida, porque el lote ya está en el invernadero y su traslado no cambia el umbral
   efectivo.
- Fecha de entrada a la etapa actual (Paso 2): depende de la etapa del lote. (Regla 5 de 8.21)
- si es la primera etapa del ciclo, es la fecha de la siembra del lote (fechaSiembra);
- si no, es la fecha efectiva (fechaTransicion) de la transición concretada del lote cuya etapa destino es la etapa
   actual.
- Fecha programada propuesta (Pasos 4 a 6, y extensiones 4a, 6a y 6b): la mayor entre la fecha actual y la fecha
   estimada de fin de la etapa actual (fecha de entrada a la etapa actual + duración estimada en días de esa etapa).
   El Agrónomo puede elegir otra fecha igual o posterior a la actual. Si difiere de la estimada, el Sistema informa la
   diferencia en días y deja que el Agrónomo decida; no bloquea.
- Ejemplo: L-10, de lechuga Butterhead, entró en Crecimiento el 20/10, y Crecimiento dura 21 días. Su fin estimado es
   el 10/11, y el Sistema propone esa fecha. Si el Agrónomo elige el 12/11, el Sistema informa "2 días después del fin
   estimado de la etapa".
- Fecha máxima de cosecha estimada (Pasos 7 y 11): solo si la etapa destino es de tipo Maduración. Es la fecha
   programada más la duración estimada en días de la etapa Maduración. Es una estimación: la fecha máxima real se
   calcula con la fecha en que la transición se concrete. (Reglas 2 y 3 de 8.20)
- Ejemplo: con la transición programada para el 12/11 y una Maduración de 10 días, la fecha máxima de cosecha estimada
   es el 22/11.
- Distribución (Pasos 8 a 10, y extensiones 9a, 9b y 10a): el Agrónomo reparte la cantidad del lote en uno o varios
   sectores elegibles, hasta que la cantidad por distribuir sea cero.
- Ejemplo: L-10 tiene 180 plantas, y los sectores de maduración M-1 y M-2 tienen 100 y 120 agujeros libres. Se puede
   distribuir 100 en M-1 y 80 en M-2.
- Capataz del invernadero (Pasos 4 y 13): el Capataz asignado al invernadero del lote. Cada invernadero tiene un único
   Capataz. (R149)
- Sin insumos y con prioridad opcional: la transición no reserva insumos, porque ninguno puede consumirse en una
   transición (un consumo solo nace de una siembra, un mantenimiento o una entrega; regla 7 de 8.4). La prioridad
   (alta, media o baja) es opcional: sin valor, la orden se ordena como si fuera media (MD-73). Es obligatoria solo en
   Cosecha y MantenimientoTecnico. (Paso 10)
- Merma posterior a la planificación: la orden no se ajusta sola. Si una merma deja al lote con menos plantas que las
   planificadas, el Sistema alerta al Agrónomo (regla 15 de 8.8). El Agrónomo decide si cancela y vuelve a planificar,
   o si deja que el Capataz traslade lo que haya.

Lista de tecnología y variaciones de datos
2a. Los lotes pueden filtrarse por invernadero, por variedad o por etapa actual.
5a. La fecha programada se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.
7a. Si la etapa destino no es de tipo Maduración, la presentación del paso 7 no incluye la fecha máxima de cosecha
   estimada.
8a. Las cantidades se expresan en plantas, como números enteros positivos. Cada planta ocupa un agujero del sector.
14a. La notificación al Capataz se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.
Frecuencia: una vez por cada cambio de etapa de cada lote. Un lote cuyo ciclo tiene N etapas tiene N − 1 transiciones.
   Se espera varias veces por semana en cada invernadero, por la producción escalonada. A confirmar con el Jardín
   Botánico.

Temas abiertos
- No existe una forma de modificar una transición planificada. Hoy se cancela y se planifica de nuevo. ¿Hace falta un
   caso de uso propio, por ejemplo para ajustar la orden después de una merma?
- Cancelar Orden (CU-11) debe reducir los agujeros comprometidos de cada sector destino en los agujeros planificados
   de su ocupación, igual que en una siembra.
- Resuelto el 04/11/2026: PROD-CNC-TRN definió cómo el lote deja sus sectores de origen y ocupa los de destino (regla
   3 de 8.21) y su punto de extensión hacia Registrar Merma.
- ¿Una planta ocupa siempre un agujero en todas las etapas, o los sectores de etapas avanzadas necesitan más espacio
   por planta? Es la misma duda que en Planificar Siembra. [Resuelto el 15/11/2026 (MD-68 y MD-69): sí. Una planta
   ocupa un agujero en todas las etapas.]
- ¿Maduración es siempre la última etapa de un ciclo? Si no lo es, un lote con reservas podría tener una transición
   posterior.
- ¿Qué pasa con las órdenes "a realizar" de un invernadero si su Capataz se da de baja o es reemplazado? Es el mismo
   tema abierto que en Planificar Siembra. [Resuelto el 08/11/2026 (MD-60; regla 3 de 8.22): el invernadero conserva
   al Capataz inactivo hasta que el Gerente asigna a otro al modificar el invernadero; al asignarlo, pasan al nuevo
   las órdenes a realizar del saliente. ]

---

## PROD-CNC-TRN · Concretar Transición

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Órdenes.
Actor principal: Capataz.
Versión: 0.3

Personal involucrado e intereses
- Capataz: quiere registrar rápido el traslado de un lote a los sectores de su nueva etapa, indicando solo lo que
   difiere de lo planificado, sin hacer cálculos de stock ni de costos.
- Agrónomo: quiere saber cuándo se concretó cada transición, con qué diferencias respecto de lo planificado y cuántas
   plantas se perdieron, para planificar la etapa siguiente del lote.
- Gerente: quiere que cada pérdida del traslado quede valorizada en “Pérdidas por Mermas”, con su causa y con
   trazabilidad completa en la auditoría y en el libro diario.
- Vendedor: quiere saber cuándo un lote entró en Maduración y hasta cuándo puede cosecharse, porque de eso depende el
   stock maduro que puede comprometer en contratos.
- Organización (Jardín Botánico): quiere que los sectores de origen y de destino reflejen la realidad, que los
   agujeros liberados queden disponibles para nuevas órdenes y que la etapa y la cantidad de cada lote sean
   confiables.

Relaciones con otros casos de uso
- «extend» PROD-REG-MRM · Registrar Merma: extiende este caso de uso en el punto de extensión *Plantas perdidas en la
   transición* (extensión 10a) y se ejecuta una vez, para el lote de la orden.
- No incluye («include») otros casos de uso.
- Lo precede: PROD-PNF-TRN · Planificar Transición.
- Lo interrumpe: Cancelar Orden (CU-11), si el Agrónomo cancela la orden mientras el Capataz la concreta (extensión
   13b).
- Lo sigue: PROD-PNF-TRN, para la transición a la etapa siguiente del lote.

Puntos de extensión
- *Plantas perdidas en la transición* (paso 10): el Capataz ubicó en los sectores destino menos plantas que la
   cantidad actual del lote.

Precondiciones
a. El Capataz está autenticado en el Sistema.
b. Existe al menos una orden de trabajo de transición en estado “a realizar” asignada al Capataz.
c. Existe un ejercicio contable vigente. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*
d. Existen las cuentas contables “Pérdidas por Mermas” y “Productos en Proceso”. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*

Garantías mínimas
- La operación es atómica, incluido el caso de uso que lo extiende. Si el caso de uso se cancela o falla:
- la orden permanece en estado “a realizar”;
- no se registra ningún cambio en el lote, en sus ocupaciones de sector, en los sectores, en la bitácora ni en la
   contabilidad;
- no queda ningún log de auditoría parcial.
- Una orden de transición se concreta una única vez.
- Ningún sector destino recibe más plantas que las planificadas para él, ni toma agujeros comprometidos por otras
   órdenes.
- Un lote nunca queda con más plantas ubicadas que su cantidad actual.
- No se modifica la etapa del lote hasta que la concreción se confirma.
- La transición no consume insumos ni genera asientos por sí misma.

Garantías de éxito (Postcondiciones)
a. La orden de trabajo de transición pasó de “a realizar” a “concretada”, con:
- fecha de resolución igual a la fecha actual;
- fecha efectiva igual a la indicada por el Capataz;
- cantidad transferida igual al total de plantas ubicadas en los sectores destino.
b. El lote quedó en la etapa productiva destino de la orden y sigue en estado “activo”. Si se declararon plantas
   perdidas, su cantidad actual quedó igual al total de plantas ubicadas.
c. En cada ocupación de sector de la transición se registró la cantidad de agujeros ocupados, igual a las plantas
   ubicadas en ese sector. La cantidad de agujeros planificados no se modificó. Cada ocupación con al menos una planta
   ubicada quedó asociada al lote. Las que quedaron en cero se conservan como parte de la orden, con cero agujeros
   ocupados y sin lote.
d. Las ocupaciones que el lote tenía en sus sectores de origen quedaron con cero agujeros ocupados y conservan su
   asociación con el lote.
e. En cada sector destino, la cantidad de agujeros comprometidos se redujo en la cantidad de agujeros planificados de
   su ocupación, y la cantidad de agujeros disponibles se redujo en la cantidad de agujeros ocupados.
f. En cada sector de origen, la cantidad de agujeros disponibles aumentó en la cantidad de agujeros que el lote
   ocupaba en él.
g. Se registró en la bitácora del lote un evento de tipo “transición”, con la fecha efectiva, la hora actual, la
   cantidad efectivamente transferida y el Capataz como responsable. El evento está asociado a la orden, al lote, a la
   etapa productiva destino y al invernadero.
h. Si el Capataz ubicó menos plantas que la cantidad actual del lote, se ejecutó PROD-REG-MRM · Registrar Merma por el
   lote, con las plantas sin trasladar como cantidad perdida, la causa y la descripción indicadas. La merma quedó
   registrada en la etapa de origen del lote, con la fecha efectiva.
i. Si la merma superó por primera vez el porcentaje máximo de merma, o dejó plantas comprometidas por otras órdenes
   sin cobertura, se generaron las alertas que corresponden según PROD-REG-MRM.
j. Se envió al Agrónomo responsable del invernadero una notificación de la transición concretada, con lo planificado y
   lo realizado en cada sector, las plantas perdidas y su causa, y la fecha efectiva frente a la fecha programada. La
   notificación avisa además si la fecha efectiva es anterior a la fecha de creación de la orden.
k. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la orden de transición y los cambios en
   su estado, su fecha de resolución, su fecha efectiva y su cantidad transferida.
l. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambios de valor de cada ocupación de
   sector, sector y lote modificados.
m. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del registro de bitácora creado.

Escenario principal de éxito (o Flujo Básico)
1.  El Capataz inicia la concreción de una transición.
2.  El Sistema presenta las órdenes de transición en estado “a realizar” asignadas al Capataz, ordenadas por fecha
   programada, de la más antigua a la más reciente. Para cada una indica el lote, el invernadero, el cultivo y la
   variedad, la etapa destino, la cantidad a trasladar y la fecha programada.
3.  El Capataz selecciona una orden.
4.  El Sistema presenta el detalle de la orden:
- el lote, el cultivo y la variedad;
- la etapa actual y la etapa destino;
- la cantidad actual del lote y los sectores de origen, con los agujeros ocupados por el lote en cada uno;
- la distribución planificada por sector destino.
   El Sistema propone como fecha efectiva la fecha actual y, para cada sector destino, la cantidad planificada como
   cantidad ubicada. También informa la fecha mínima admitida.
5.  El Capataz confirma o modifica la fecha efectiva de la transición.
6.  El Sistema verifica que la fecha efectiva esté comprendida entre la fecha mínima y la fecha actual.
7.  El Capataz indica, para un sector destino, la cantidad de plantas realmente ubicadas en él.
8.  El Sistema verifica que la cantidad no supere la planificada para ese sector, recalcula el total ubicado y
   presenta su diferencia con la cantidad actual del lote. *El Capataz repite los pasos 7-8 por cada sector en el que
   ubicó una cantidad distinta de la propuesta. En los demás sectores se toma la cantidad propuesta.*
9.  El Capataz indica que terminó de registrar el traslado por sector.
10.  El Sistema verifica que el total ubicado sea de al menos una planta y que no supere la cantidad actual del lote.
   Si es menor, se aplica la extensión 10a.
11.  El Sistema presenta el resumen de la concreción:
- la fecha efectiva y su diferencia en días con la fecha programada;
- el lote, el cultivo y la variedad;
- la etapa de origen y la etapa destino;
- la cantidad actual del lote y el total ubicado;
- los sectores de origen, con los agujeros que se liberan en cada uno;
- la distribución real frente a la planificada por sector destino;
- si la etapa destino es Maduración, la fecha máxima de cosecha estimada.
12.  El Capataz confirma la concreción.
13.  El Sistema registra la orden como concretada:
- carga los agujeros ocupados de cada sector destino y los asocia al lote;
- lleva a cero las ocupaciones de origen del lote;
- actualiza los agujeros comprometidos y disponibles de cada sector;
- pasa el lote a la etapa destino;
- registra el evento de bitácora;
- registra la auditoría correspondiente.
14.  El Sistema notifica la transición concretada al Agrónomo responsable del invernadero.
15.  El Sistema informa al Capataz que la transición fue concretada.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 12, el Capataz cancela la concreción:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio y la orden permanece en estado “a realizar”.
*b. En cualquier momento el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Capataz que la transición no fue concretada.
3.  El Capataz reinicia el caso de uso desde el paso 1.
4a. La cantidad actual del lote es cero (una merma lo dejó sin plantas):
1.  El Sistema informa que no es posible concretar la transición y que el Agrónomo debe cancelar la orden.
2.  El caso de uso termina y la orden permanece en estado “a realizar”.
6a. La fecha efectiva es posterior a la fecha actual:
1.  El Sistema señala el error y rechaza la fecha.
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).
6b. La fecha efectiva es anterior a la fecha mínima:
1.  El Sistema señala el error e informa la fecha mínima y de qué fecha proviene (la entrada del lote a su etapa
   actual o su último registro de bitácora en ella).
2.  El Capataz introduce una nueva fecha (vuelve al paso 5).
8a. La cantidad indicada supera la cantidad planificada para el sector:
1.  El Sistema señala el error e informa la cantidad planificada para ese sector.
2.  El Capataz corrige la cantidad (vuelve al paso 7).
10a. El total ubicado es menor que la cantidad actual del lote (punto de extensión *Plantas perdidas en la
   transición*):
1.  El Sistema informa cuántas plantas quedaron sin trasladar, que se registrarán como merma del lote, y solicita la
   causa.
2.  El Capataz indica la causa y, opcionalmente, una descripción.
3.  El Sistema verifica que se indicó la causa y el caso de uso continúa en el paso 11, con las plantas perdidas y su
   causa en el resumen. En el paso 13 se ejecuta PROD-REG-MRM.
10a.3a. El Capataz no indicó la causa:
1.  El Sistema señala que la causa es obligatoria.
2.  El Capataz indica la causa (vuelve a 10a.2).
10b. El total ubicado es cero:
1.  El Sistema informa que no es posible concretar una transición sin plantas trasladadas.
2.  El Capataz corrige las cantidades (vuelve al paso 7) o cancela el caso de uso. La orden permanece en estado “a
   realizar” hasta que el Agrónomo la cancele.
10c. El total ubicado supera la cantidad actual del lote:
1.  El Sistema señala el error e informa la cantidad actual del lote.
2.  El Capataz corrige las cantidades (vuelve al paso 7).
11a. La etapa destino es Maduración y la fecha máxima de cosecha estimada es anterior a la fecha actual:
1.  En el resumen del paso 11, el Sistema advierte además que el lote ya superó su fecha máxima y que no contará como
   stock maduro libre para ninguna fecha de entrega.
2.  La advertencia no bloquea y el caso de uso continúa en el paso 12.
12a. El Capataz quiere corregir un dato del resumen:
1.  El Capataz indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (5, 7 o 10a.2).
2.  Si corrige una cantidad ubicada, el Capataz vuelve a indicar que terminó el registro (paso 9) y el Sistema repite
   las verificaciones desde el paso 10.
13a. El Sistema no logra registrar la concreción porque el lote ya no cumple las condiciones de la orden (otra
   operación cambió su etapa actual o su estado):
1.  El Sistema no registra ningún cambio e informa qué cambió.
2.  El caso de uso termina.
13b. La orden ya no se encuentra en estado “a realizar” al momento de registrar (por ejemplo, el Agrónomo la canceló
   mientras el Capataz ingresaba los datos):
1.  El Sistema no registra ningún cambio e informa al Capataz el estado actual de la orden.
2.  El caso de uso termina.
13c. Entre las verificaciones y la confirmación cambió la cantidad actual del lote o las ocupaciones de origen (por
   ejemplo, por una merma registrada mientras tanto):
1.  El Sistema no registra ningún cambio, informa la nueva cantidad actual y presenta la distribución propuesta con
   esa cantidad.
2.  El caso de uso vuelve al paso 7.
14a. El Sistema no logra entregar la notificación al Agrónomo:
1.  La concreción permanece registrada.
2.  El Sistema reintenta el envío.
3.  En el paso 15, el Sistema avisa además al Capataz que la notificación al Agrónomo quedó pendiente.

Requisitos especiales
- La interfaz del Capataz está pensada para pantallas de celular, con la carga dividida en pasos.
- Tras cada dato ingresado por el Capataz (pasos 3 a 10), la pantalla se actualiza con las verificaciones y los
   valores calculados en no más de 1 segundo.
- El registro del paso 13 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un
   indicador de progreso.
- El paso 13, incluida la ejecución de PROD-REG-MRM, se ejecuta como una única transacción: todos los cambios y
   registros se confirman juntos o no se confirma ninguno. La notificación se envía fuera de la transacción.
- El control de concurrencia impide:
- que una misma orden se concrete dos veces;
- que una orden se concrete y se cancele al mismo tiempo;
- que se concrete sobre una cantidad del lote que cambió mientras tanto.
- Solo el Capataz asignado a la orden puede concretarla.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos de los asientos contables de la merma se expresan en pesos argentinos, con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Valores propuestos: el Sistema propone la fecha actual como fecha efectiva y, en cada sector destino, la cantidad
   planificada como cantidad ubicada. El Capataz solo indica los valores que difieren de lo propuesto; los demás se
   toman tal como los propone el Sistema. (Pasos 4, 5 y 7)
- Reparto proporcional: si la cantidad actual del lote es menor que la suma de las cantidades planificadas, el Sistema
   propone la cantidad actual repartida en proporción a lo planificado en cada sector, así: (Paso 4, y extensión 13c)
- cada sector recibe la parte entera de su cuota;
- las unidades restantes se asignan de a una a los sectores con mayor parte decimal (método del resto mayor);
- si hay empate, se asignan al sector con más agujeros planificados y, si el empate sigue, al primero de la lista.
- Fecha mínima: la mayor entre la fecha de entrada del lote a su etapa actual y la fecha de su último registro de
   bitácora asociado a esa etapa, si lo tiene. (Pasos 4 y 6, y extensión 6b)
- Fecha efectiva válida: fecha comprendida entre la fecha mínima y la fecha actual, ambas inclusive. Puede ser
   anterior a la fecha de creación de la orden y a la fecha programada. (Paso 6) Motivo: el traslado físico puede
   haberse hecho antes de que se registre, y la fecha de entrada a la nueva etapa, y con ella la fecha máxima de
   cosecha, tiene que ser la real.
- Fecha de entrada a la etapa actual: la calcula el Sistema según la regla 5 de 8.21. En la primera etapa del ciclo es
   la fecha de siembra del lote; en las demás, la fecha efectiva de la transición concretada cuya etapa destino es la
   etapa actual. (Pasos 4 y 6)
- Cantidad ubicada válida: en cada sector destino, un número entero entre cero y la cantidad planificada para ese
   sector. No se admiten sectores fuera de la distribución planificada. (Pasos 8 y 10)
- Total ubicado válido: al menos una planta y como máximo la cantidad actual del lote. (Paso 10)
- Plantas sin trasladar: cantidad actual del lote menos el total ubicado. Siempre se registran como merma, con causa
   obligatoria, porque un lote tiene una única etapa y no puede quedar plantas en la etapa de origen. (Paso 10, y
   extensión 10a)
- Merma de la transición: se registra con PROD-REG-MRM, una sola vez, con una única causa y una descripción opcional.
   La causa se elige de la lista de causas de merma que aplican a un lote en pie, que incluye el descarte por
   selección (MD-78): plantas que se descartan a propósito al elegir cuáles trasladar, y que no suman a la merma
   acumulada del lote. (Extensión 10a)
- El Sistema calcula la cantidad perdida; el Capataz no la escribe.
- Se ejecuta antes del traslado, de modo que queda registrada en la etapa de origen, con la fecha efectiva.
- La alerta por plantas comprometidas se evalúa sin contar la propia transición, que se concreta en la misma
   operación.
- Liberación de agujeros de origen: en cada sector de origen se liberan todos los agujeros que el lote ocupaba,
   incluidos los de las plantas perdidas. Por eso la merma de esta transición no libera agujeros por su cuenta. (Paso
   13)
- Agujeros de destino: en cada sector destino, los agujeros comprometidos se reducen en los planificados de la
   ocupación y los disponibles se reducen en los ocupados. Lo planificado que no se ubicó vuelve a estar libre. (Paso
   13)
- Ocupaciones sin plantas: una ocupación destino que quedó en cero se conserva como parte de la orden, sin lote. (Paso
   13)
- Etapa del lote: pasa a ser la etapa destino de la orden. (Paso 13)
- Fecha máxima de cosecha estimada: solo si la etapa destino es de tipo Maduración. Es la fecha efectiva más la
   duración estimada en días de esa etapa. (Pasos 11 y 13, y extensión 11a)
- Sin insumos ni asientos, y con prioridad opcional: la transición no consume insumos ni genera asientos; el costo del
   lote sigue en “Productos en Proceso”. Su prioridad, que se indica al planificarla, es opcional y no cambia la
   concreción (MD-73). Solo la merma, si la hay, genera su asiento.

Lista de tecnología y variaciones de datos
- 5a. La fecha efectiva se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El Sistema propone por
   defecto la fecha actual.
- 7a. Las cantidades ubicadas se expresan en plantas, como números enteros. El Sistema propone por defecto la cantidad
   planificada para cada sector (o su parte proporcional, según la regla “Reparto proporcional”).
- 10a. La causa de las plantas perdidas se elige de la lista de causas de merma que aplican a un lote en pie: plaga,
   enfermedad, falla de riego o nutrientes, condiciones ambientales, daño mecánico, descarte por selección u otra.
   Opcionalmente puede agregarse una descripción.
- 14a. La notificación al Agrónomo se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.

Frecuencia
Una vez por cada orden de transición planificada. Un lote cuyo ciclo tiene N etapas tiene N − 1 transiciones. La
   frecuencia real está a confirmar con el Jardín Botánico.

Temas abiertos
- Si un sector planificado no puede usarse o el Capataz tuvo que usar un sector no planificado, el Sistema no lo
   permite registrar. El procedimiento es: el Capataz avisa al Agrónomo fuera del Sistema, y el Agrónomo cancela la
   orden original y las órdenes que reservaban el sector usado. Después planifica una nueva transición con los
   sectores reales, que el Capataz concreta con la fecha real del traslado. Hay que evaluar si el Jardín Botánico
   necesita que el Sistema lo contemple.
- ¿Qué pasa con las órdenes de transición “a realizar” cuya fecha programada ya pasó sin concretarse?
- ¿Maduración es siempre la última etapa de un ciclo? Si no lo es, un lote con reservas podría tener una transición
   posterior.
- Una transición admite una sola causa de merma. Si las plantas se perdieron por causas distintas, el Capataz elige la
   principal.

---

## PROD-REG-MRM · Registrar Merma (solo lo que aplica desde la transición)

Extracto de las secciones del caso de Drive que se usan en la ronda (el caso completo lo hace PRD-03).

Postcondiciones que aplican (lote en pie):
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

Extensiones que aplican:
10a. Después de la merma, se cumple alguna de las condiciones de plantas comprometidas del lote:
1.  El Sistema genera una alerta para el Agrónomo responsable del invernadero, indicando el lote, qué condición se
   cumple y qué órdenes de cosecha o qué orden de transición quedaron sin cobertura.
10b. La merma hace que la merma acumulada del lote supere por primera vez el porcentaje máximo de merma configurado:
1.  El Sistema genera una alerta para el Agrónomo responsable del invernadero y para el Gerente, indicando el lote, la
   merma acumulada y el porcentaje que representa sobre su cantidad inicial.

Ejecución como extensión desde PROD-CNC-TRN:
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

Reglas de negocio que aplican:
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
- Fin del lote y de la partida: un lote cuya cantidad actual llega a cero pasa a “finalizado”; una partida cuya
   cantidad disponible llega a cero pasa a “agotado”. (Paso 10)
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

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-50)

### Qué hace cada parte, y con qué se completa

| Parte | Código | Observaciones |
|---|---|---|
| Planificar transición | `produccion/servicios/transiciones.py`: `lotes_trasladables`, `datos_de_planificacion`, `resumen_de_planificacion`, `planificar_transicion(actor, datos)` | Lotes trasladables solo de invernaderos activos a cargo del Agrónomo |
| Concretar transición | `produccion/servicios/transiciones.py`: `datos_de_concrecion`, `resumen_de_concrecion`, `concretar_transicion(actor, orden_id, datos)` | Incluye, como paso interno, el núcleo de la merma |
| Núcleo de la merma | `produccion/servicios/mermas.py`: `aplicar_merma(...)` (función interna, no un CU; firma completa en PRD-02, D-51 punto 5) | **Lo escribe PRD-02** porque CNC-TRN lo necesita. PRD-03 agrega la pantalla y el CU completo (PROD-REG-MRM) sobre el mismo módulo |
| Reparto proporcional y fecha mínima | `produccion/servicios/transiciones.py`: `repartir_proporcional`, `fecha_minima_de_transicion` | Funciones puras, con sus propias pruebas |

### Lo que NO se hace en la ronda (D-45)

- ~~**Asientos** (precondiciones c y d de CNC-TRN y la postcondición e de PROD-REG-MRM): no se verifica el ejercicio ni las cuentas, y no se crea asiento.~~ **Hecho en CON-04a (25/11/2026):** la merma de las plantas sin trasladar asienta Debe «Pérdidas por Mermas» / Haber «Productos en Proceso» por su costo, con la fecha efectiva de la transición; la transición en sí no asienta. El **costo acumulado del lote baja** (`docs/patrones/costo_del_lote.md`).
- **Movimiento de stock «salida por merma»** (postcondición d de PROD-REG-MRM): no existe `MovimientoStock` ni stock de plantas en la ronda; no se crea.
- **Alerta de plantas comprometidas, condición 1** (reservas de cosecha): no hay cosechas. La **condición 2** (la transición «a realizar» queda con menos plantas) está programada y probada, pero **desde CNC-TRN no puede dispararse** (se evalúa «sin contar la orden que se concreta»); la ejerce PRD-03 con la merma desde la pantalla.
- Partida en cámara y causas de cámara: fuera.

### Decisiones de aplicación

**Permisos.** Planificar: Agrónomo a cargo del invernadero del lote. Concretar: el Capataz asignado a la orden. Todo servicio verifica que quien actúa siga activo después de bloquear.

**Bloqueos.** Cuentas → invernadero → variedad (`bloquear_variedad`) → **sectores** (`bloquear_sectores`: los destino de la orden y los de origen del lote, en orden de id, sin repetir) → fila del **lote** → ocupaciones y orden. Se lee sin bloquear qué sectores hay, se bloquea y se relee. Si cambió algo (la cantidad actual, la etapa, el estado de la orden): `cambio_simultaneo`
con el dato que cambió y, en 13c, se vuelve a proponer el reparto con la cantidad nueva. Un lote con una sola transición «a realizar» (regla 4 de 8.21) se garantiza bloqueando el lote antes de verificar.

**Planificar.**
- **Etapa destino**: la determina el sistema (`inventario.servicios.ciclos.etapas_de`); no se elige. Un lote en la última etapa del ciclo no es trasladable.
- **Cantidad**: siempre la cantidad actual del lote. La suma de agujeros planificados debe igualarla.
- **Sector elegible**: activo (no «fuera de servicio»), del mismo invernadero, tipo de etapa igual al de la etapa destino, perfil familiar compatible (`perfil_de_sector` de `produccion`) y capacidad libre > 0. **No se valida el umbral ambiental**.
- **Fecha programada propuesta**: la mayor entre hoy y la fecha estimada de fin de la etapa actual (`fecha_de_entrada_a_la_etapa` + `duracion_dias`). Informar la diferencia en días sin bloquear (6b). Con fecha estimada vencida: proponer hoy e informar los días de atraso (4a).
- **Fecha máxima de cosecha estimada**: solo si el destino es Maduración: programada + duración de Maduración.
- Sin reservas de insumo. Prioridad opcional (MD-73).
- **Auditoría**: un registro `planificacion_transicion` con la orden, las ocupaciones y los sectores (texto «agujeros comprometidos» antes → después). Notificación al Capataz dentro de la transacción (D-42); la extensión 14a «no logra entregar» no aplica.

**Concretar.**
- **Fecha mínima** = la mayor entre la fecha de entrada del lote a su etapa actual y la fecha del último registro de bitácora del lote en esa etapa. La fecha efectiva puede ser anterior a la fecha de creación y a la programada (regla de CNC-TRN).
- **Cantidades**: por sector entre 0 y lo planificado; total ≥ 1 y ≤ cantidad actual. **Reparto proporcional** (método del resto mayor; empate: más agujeros planificados, después el primero de la lista) cuando la cantidad actual es menor que la planificada (13c).
- **Plantas sin trasladar** = cantidad actual − total ubicado: **siempre se registran como merma**, con causa obligatoria (10a), antes del traslado y en la etapa de origen, con la fecha efectiva.
- **Efectos al confirmar**: ocupaciones destino con `cant_agujeros_ocupados` y `lote` (si ≥ 1); ocupaciones de origen del lote en cero (conservan el lote); `Lote.etapa` = destino y `cantidad_actual` = total ubicado; `TransicionEtapa.cant_transferido` y `fecha_transicion`; `Bitacora` tipo `transicion` (fecha efectiva, hora actual, responsable el Capataz, etapa destino) enlazada a la orden; orden «concretada» con fecha de resolución = hoy.
- **Núcleo de la merma desde la transición** (ver el extracto de PROD-REG-MRM más abajo): crea la `Merma` (con su `Bitacora` tipo `merma`); baja `cantidad_actual` y `costo_acumulado` del lote (si llega a cero: `finalizado`; **en una transición no puede llegar a cero**, porque el total ubicado es ≥ 1); **no** baja agujeros por sector (los libera la transición); evalúa el umbral de merma y, si se cruzó por primera vez,
  crea la alerta `produccion_merma_umbral` (Agrónomo a cargo y Gerente) enlazada por `AlertaDeMerma`.
- **Notificación** al Agrónomo a cargo del invernadero (`notificar`, dentro de la transacción, D-42) con lo planificado y lo realizado por sector, las plantas perdidas y su causa, y la fecha efectiva frente a la programada; avisa si la efectiva es anterior a la fecha de creación. Con Agrónomo = quien actúa no aplica porque actúa el Capataz.
- **Auditoría**: un registro `concrecion_transicion` con orden, lote, ocupaciones, sectores, bitácora y, si hubo, merma y alerta. Además `registro_merma` solo cuando se registre una merma sola (PRD-03); en la transición la merma va **dentro** del único registro (D-36: un registro por CU).
- **Advertencia 11a** (Maduración vencida): se muestra en el resumen y no bloquea.

### Registrantes

Los mismos de `siembra.md`; PRD-02 solo agrega el tipo de alerta `produccion_merma_umbral` (`registrar_tipo_de_alerta`, destinatario Agrónomo y Gerente, evento, origen `Origen.MERMA`) y el tipo `produccion_plantas_comprometidas` (Agrónomo o Gerente, evento) que queda sin emitirse hasta PRD-03.

### Pruebas

`produccion/tests/test_prod_pnf_trn.py`, `test_prod_cnc_trn.py`, `test_mermas_nucleo.py`, `test_transiciones_concurrencia.py` (`@tag("concurrencia")`: dos planificaciones sobre el mismo lote; concretar contra cancelar; concretar contra una merma que cambia la cantidad, 13c; concretar dos veces). Una por regla y por postcondición, `test_regla_<n>…` / `test_post_<letra>…`.
La condición 2 de plantas comprometidas se prueba **llamando a la función directamente** (con una orden ajena «a realizar»), porque desde CNC-TRN no se dispara.
