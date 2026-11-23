# Casos de uso · iot · Entregar información

Copia para el repo del caso IOT-ENT-INF (v0.2) de «CU extendidos» (Lote 1 v5.6 del IoT, pegado el 20/11/2026 y copiado el 21/11/2026).
Junto con los demás casos IOT-* reemplaza a los preliminares de la «Documentación para la IA» que lista `docs/tareas/ronda_iot_1.md`,
sección 3. Cotejado con `docs/modelo/iot.md` (que aplica MD-98 a MD-113) y con D-70 a D-75. **Ya trae las correcciones de D-71** (el correo de las
alertas críticas lo manda la revisión periódica): cada una está marcada «corregido el 21/11/2026, D-71» y hay que pasarlas también a
«CU extendidos».

Es el caso de uso más grande de la ronda y se reparte entre tres tareas: **cada tarea lee solo sus partes** (Índice y «Reparto», abajo).
El código va en la app `iot` (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: `test_post_<letra>_<que_espera>`, `test_ext_<extension>_<que_espera>` (por ejemplo `test_ext_3f_...`) y
`test_regla_<nombre>_<que_espera>` (por ejemplo `test_regla_histeresis_...`).

## Índice

| Código | Partes | Actor | Tarea | Lote | Archivos de pruebas |
|---|---|---|---|---|---|
| IOT-ENT-INF | Flujo principal (pasos 1 a 5 y 7), extensiones \*a, 1a a 1c, 3a a 3f, 4a a 4c y 5a a 5g; postcondiciones a a h, m a t, y y z; la API del nodo | Sistema IoT (nodo central) | **IOT-03** | I2a | `iot/tests/test_iot_ent_inf_lecturas.py`, `test_iot_ent_inf_estados.py`, `test_iot_ent_inf_anuncio.py`, `test_api_nodo.py`, `test_api_ejemplos.py`, `test_api_concurrencia.py` |
| IOT-ENT-INF | Extensión \*b (revisión periódica) y postcondiciones u a x; el correo de las críticas (D-71) | InfoPonia | IOT-04 | I2b | `iot/tests/test_revision_iot.py`, `test_revision_resumenes.py`, `test_revision_correos.py`, `test_comando_revision_iot.py` |
| IOT-ENT-INF | Paso 6, extensiones 6a a 6d, postcondiciones i a l; los reinicios de las reglas de 1b.3 y 5c | Sistema IoT | IOT-06 | I3 | `iot/tests/test_iot_ent_inf_reglas.py` |

## IOT-ENT-INF · Entregar Información

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** IoT.

**Actor principal:** Sistema IoT (nodo central del invernadero).

**Actor secundario:** InfoPonia (tarea programada), que cada 5 minutos detecta los equipos sin actividad y los nodos sin comunicación, actualiza los resúmenes horarios, calcula el fotoperíodo de cada día y borra las lecturas que superan el plazo de retención.

**Versión:** 0.2

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere enterarse a tiempo de las condiciones ambientales de riesgo y de las fallas de los equipos, por correo cuando son graves y aunque no esté usando InfoPonia, sin recibir la misma alerta una y otra vez, y que las reglas de actuación respondan solas mientras él no está, sin encender y apagar los equipos a cada rato.
  - **Gerente:** quiere recibir las alertas de los invernaderos que no tienen un Agrónomo activo, y que solo se acepten datos de los equipos registrados.
  - **Técnico:** quiere saber qué equipos fallan, miden mal, dejaron de reportar o no son compatibles con su tipo, para diagnosticarlos.
  - **Organización (Jardín Botánico):** quiere reducir la merma con la detección temprana de condiciones de riesgo mediante la telemetría (nota de presentación, «Introducción y objetivos»), sin reemplazar su infraestructura IoT, y conservar la historia de las condiciones en que creció cada lote.

**Relaciones con otros casos de uso:** no incluye («include») otros casos de uso ni es extendido («extend») por ellos. Los comandos automáticos que emite cumplen la regla «Comando válido» de IOT-EMT-CMD y los resuelve IOT-RSV-CMD. Sus lecturas y alertas se consultan con IOT-CNS-LEC. Desde la alerta «dispositivo no registrado» se inicia IOT-ALT-HDW con el identificador ya cargado, y los equipos anunciados se ofrecen en ese mismo caso de uso.

**Precondiciones:**

a. El nodo central se identifica con el token vigente de un sistema IoT en estado «activo».

**Garantías mínimas:**

  - Cada lectura, cada estado y cada anuncio se procesan en forma atómica: la lectura, sus alertas, sus comandos automáticos, sus registros de bitácora, la última evaluación de las reglas y los logs se registran juntos o no se registra ninguno. Una lectura rechazada no impide procesar las demás del mismo mensaje.
  - Solo se aceptan mensajes de los equipos registrados del propio sistema IoT del nodo.
  - Nunca hay dos alertas activas del mismo tipo para el mismo sensor o actuador, ni dos alertas activas «dispositivo no registrado» para el mismo identificador en el mismo sistema IoT, aun cuando lleguen mensajes simultáneos.
  - Una regla de actuación no emite un segundo comando mientras su condición sigue cumpliéndose, y ningún actuador queda con dos comandos pendientes.
  - Una lectura atrasada nunca genera ni resuelve alertas de umbral, de rango o de nivel, ni dispara reglas.
  - Una alerta de severidad crítica se notifica por correo una sola vez, aunque la revisión periódica se ejecute varias veces.
  - Las lecturas que originaron una alerta o dispararon una regla no se borran por la retención, y los resúmenes horarios no se borran.

**Garantías de éxito (Postcondiciones):**

**En todo mensaje aceptado:** a. Se registró la fecha y la hora de la comunicación del nodo central, que queda «en línea». Si tenía activa la alerta «nodo sin comunicación», pasó a «resuelta».

**Por cada lectura aceptada:** b. Se creó una telemetría con el valor medido, la unidad del sensor si la tiene, la fecha y la hora de medición y la marca «válida» o «inválida», asociada al sensor. c. Si el sensor tenía activa la alerta «dispositivo sin actividad», pasó a «resuelta».

**Si la lectura es inválida (fuera del rango de calibración) y no está atrasada:** d. Si el sensor no la tenía, se generó una alerta activa «lectura inválida», con origen en el sensor (R052).

**Si la lectura es válida y no está atrasada:** e. Si el sensor tenía activa la alerta «lectura inválida», pasó a «resuelta». f. Si es de temperatura, humedad o intensidad lumínica y quedó fuera del umbral efectivo, y el sensor no tenía la alerta, se generó una alerta activa «fuera de umbral efectivo», con origen en esa telemetría (R053) y con la variable, el valor y el límite superado. Si volvió a quedar dentro del umbral efectivo, a más de la histéresis de la variable de cada límite, y el sensor tenía esa alerta, pasó a «resuelta». g. Si es de temperatura de la solución y el sistema IoT tiene un rango definido, se generó o se resolvió del mismo modo la alerta «solución fuera de rango», con origen en esa telemetría (R053). h. Si es de nivel de la solución, el valor «bajo» generó la alerta «nivel de solución bajo», con origen en esa telemetría (R053), si el sensor no la tenía, y el valor «normal» la resolvió. i. Se actualizó la última evaluación y el contador de confirmación de cada regla de actuación activa del sensor.

**Por cada regla cuya condición pasó a cumplirse y quedó confirmada:** j. Se creó un comando automático en estado «pendiente», con la fecha y la hora de emisión, el valor a aplicar de la regla y la cantidad de intentos en cero. Está asociado al actuador y a la acción de la regla, a la regla misma y a ningún Agrónomo, y su descripción indica la regla que lo disparó. k. La telemetría quedó asociada a la regla (R062). l. Se creó un registro de bitácora del invernadero de tipo «comando», sin lote, con el actuador, la acción, el valor y la regla.

**Por cada estado informado:** m. Si el equipo se informó «en línea», se resolvió su alerta activa «dispositivo sin actividad», si la tenía. n. Si se informó «desconectado», se generó la alerta «dispositivo sin actividad», si no la tenía. o. Si se informó «en falla», el equipo pasó a «fuera de servicio» y se generó la alerta «dispositivo en falla», con origen en el equipo (R052). p. Si se informó el estado operativo de un actuador (por ejemplo, encendido, apagado o una posición), ese pasó a ser su estado informado, con la fecha y la hora, y se marcó «cambiado en el invernadero» si no lo explica un comando de InfoPonia. q. Si el nodo informó su modo, quedó registrado («remoto» o «local»).

**Por cada anuncio de equipos:** r. Quedaron registrados los equipos que el nodo anunció, con sus identificadores y, para los actuadores, sus capacidades. s. Cada actuador registrado quedó marcado «compatible» o «incompatible» según las capacidades anunciadas, con sus acciones incompatibles marcadas, y se generó o se resolvió su alerta «configuración incompatible», con origen en el actuador (R052).

**Por cada identificador desconocido en una lectura o un estado:** t. Si no existía, se generó una alerta activa «dispositivo no registrado», sin origen en el modelo, con el identificador, la variable o el estado que informa y el valor recibido.

**En la revisión periódica (InfoPonia, cada 5 minutos):** u. Se generaron las alertas «dispositivo sin actividad» y «nodo sin comunicación» que correspondían, y se resolvieron las «dispositivo no registrado» sin mensajes recientes. v. Se actualizaron los resúmenes horarios de cada sensor. w. Al cerrar cada día, se calculó el fotoperíodo de cada sensor de intensidad lumínica y se generó o se resolvió su alerta «fuera de umbral efectivo». x. Se borraron las lecturas más antiguas que los días de retención, salvo las que originaron una alerta o dispararon una regla.

**En todos los casos:** y. Cada alerta generada tiene como destinatario al Agrónomo del invernadero o, si no tiene un Agrónomo activo, al Gerente. Las de severidad crítica se le notifican por correo en la revisión periódica siguiente, dentro de los 5 minutos. *(corregido el 21/11/2026, D-71: antes decía «Las de severidad crítica se le notificaron por correo»)* z. Se creó un log de auditoría con origen «InfoPonia» (por el nodo central o por la revisión periódica), fecha, hora y el identificador de cada alerta, comando, registro de bitácora y equipo creados o modificados, con los cambios de estado. Las lecturas y los resúmenes no se auditan uno por uno.

**Escenario principal de éxito (o Flujo Básico):**

(Llega una lectura válida, reciente, dentro del umbral efectivo, y ninguna regla se dispara.)

1.  El nodo central envía una o más lecturas, identificándose con su token. Cada lectura tiene el identificador del sensor, el valor medido y la fecha y la hora de medición.
2.  El Sistema verifica el token y registra la comunicación del nodo.
3.  El Sistema verifica que el identificador corresponde a un sensor activo del sistema IoT, que la fecha y la hora de medición no son futuras y que la lectura no está atrasada.
4.  El Sistema verifica que el valor está dentro del rango de calibración del sensor y registra la lectura como válida.
5.  El Sistema calcula el umbral efectivo del invernadero y verifica que la lectura está dentro de él.
6.  El Sistema evalúa las reglas de actuación activas del sensor. Ninguna condición pasa a cumplirse, y el Sistema registra la última evaluación y el contador de confirmación de cada una. *El Sistema repite los pasos 3 a 6 por cada lectura del mensaje.*
7.  El Sistema responde al nodo con el resultado de cada lectura: aceptada, o rechazada con su motivo.

**Extensiones (o Flujos Alternativos):**

**\*a. El token no es válido o el sistema IoT no está activo:**

1.  El Sistema rechaza el mensaje sin registrar ningún cambio. Si el sistema está desconectado, responde que está desconectado.
2.  El caso de uso termina.

**\*b. Revisión periódica (InfoPonia, tarea programada cada 5 minutos, independiente de los mensajes del nodo y de los usuarios):**

1.  Por cada sistema IoT activo, el Sistema revisa cada sensor activo que ya envió alguna lectura: si no recibió lecturas durante los minutos sin actividad de la Configuración Operativa, genera la alerta «dispositivo sin actividad», si no la tenía. Los sensores «sin confirmar» no generan esta alerta.
2.  Si el nodo central, después de haberse comunicado al menos una vez, no se comunicó durante los minutos sin comunicación de la Configuración Operativa, genera la alerta «nodo sin comunicación», si no la tenía, y la notifica por correo. Un nodo que todavía no se comunicó no genera esta alerta.
3.  Si la última alerta «dispositivo no registrado» de un identificador no recibió mensajes durante los minutos sin actividad, la pasa a «resuelta».
4.  Actualiza el resumen de la hora en curso de cada sensor, salvo los de nivel de la solución, con el mínimo, el promedio y el máximo de sus lecturas válidas, la cantidad de lecturas y la cantidad de inválidas.
5.  Si cerró un día desde la revisión anterior, calcula el fotoperíodo de ese día para cada sensor de intensidad lumínica activo (regla «Fotoperíodo»). Si el invernadero tiene umbral efectivo y el sensor no está en un sector fuera de servicio, lo compara con el rango de fotoperíodo: fuera de él genera la alerta «fuera de umbral efectivo», con origen en el sensor (R052), si no la tenía; dentro, la resuelve.
6.  Borra las lecturas más antiguas que los días de retención de la Configuración Operativa, salvo las que originaron una alerta o dispararon una regla. Los resúmenes horarios y los fotoperíodos calculados se conservan.
7.  La revisión termina.

**1a. El nodo informa el estado de un equipo:**

1.  El Sistema verifica que el identificador corresponde a un equipo registrado y no dado de baja del sistema IoT. Si no, aplica la extensión 3a.
2.  Según lo informado:

      - «en línea»: resuelve la alerta «dispositivo sin actividad» del equipo, si la tenía;
      - «desconectado»: genera la alerta «dispositivo sin actividad», si no la tenía;
      - «en falla»: pasa el equipo a «fuera de servicio» y genera la alerta «dispositivo en falla», si no la tenía; la revisión periódica la notifica por correo dentro de los 5 minutos siguientes; *(corregido el 21/11/2026, D-71: antes decía «y la notifica por correo»)*
      - estado operativo de un actuador (por ejemplo, encendido, apagado o una posición): lo registra como su estado informado, con la fecha y la hora, y lo marca «cambiado en el invernadero» si no lo explica un comando de InfoPonia ejecutado sobre ese actuador.
3.  El caso de uso continúa en el paso 7.

**1b. El nodo informa su modo:**

1.  El Sistema registra el modo informado («remoto» o «local»).
2.  Si pasó a «local», el Sistema deja de evaluar reglas de actuación y de entregar comandos a ese nodo (IOT-RSV-CMD).
3.  Si volvió a «remoto», cada regla de actuación se evalúa desde la próxima lectura como si antes su condición no se cumpliera, con la confirmación desde cero, porque el control local pudo haber cambiado el estado de los actuadores.
4.  El caso de uso continúa en el paso 7.

**1c. El nodo anuncia sus equipos:**

1.  El Sistema registra los equipos anunciados: su identificador, si es sensor o actuador y, para los actuadores, los comandos del catálogo de capacidades que soportan.
2.  Para cada actuador registrado con un identificador anunciado, compara los comandos de las acciones activas de su tipo con los anunciados y marca el actuador «compatible» o «incompatible», con sus acciones incompatibles.
3.  Si un actuador quedó incompatible y no tenía la alerta «configuración incompatible», la genera; si quedó compatible y la tenía, la resuelve.
4.  Los identificadores anunciados que no están registrados no generan alertas: se ofrecen al registrar hardware (regla 14 de IOT-ALT-HDW), marcando los que eran de un equipo dado de baja.
5.  El caso de uso continúa en el paso 7.

**3a. El identificador no corresponde a ningún equipo registrado del sistema IoT, o corresponde a uno dado de baja:**

1.  El Sistema rechaza la lectura o el estado y, si no existía para ese identificador, genera la alerta «dispositivo no registrado». Si el identificador era de un equipo dado de baja del sistema IoT, el motivo que recibe el nodo es «equipo dado de baja» y, al mostrar la alerta, el Sistema indica de qué equipo era y ofrece reactivarlo (regla 12 de IOT-ALT-HDW). Ese vínculo se deduce por el identificador: no se guarda en la alerta.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**3b. El identificador corresponde a un actuador y el mensaje es una lectura:**

1.  El Sistema rechaza la lectura y deja constancia en el registro técnico de errores.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**3c. El sensor está fuera de servicio:**

1.  El Sistema registra la lectura, pero no la compara ni evalúa sus reglas, porque el sensor tiene una falla informada.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**3d. La fecha y la hora de medición son futuras (más de 5 minutos después de la hora actual):**

1.  El Sistema rechaza la lectura y deja constancia en el registro técnico de errores.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**3e. La lectura no trae fecha ni hora de medición:**

1.  El Sistema usa la fecha y la hora de recepción.
2.  El caso de uso continúa en el paso 4.

**3f. La lectura está atrasada (se midió hace más que la antigüedad máxima de la Configuración Operativa):**

1.  El Sistema registra la lectura con su marca «válida» o «inválida» y resuelve la alerta «dispositivo sin actividad» del sensor, si la tenía.
2.  No genera ni resuelve alertas de lectura inválida, de umbral, de rango ni de nivel, y no evalúa reglas: la lectura solo queda en el historial y en los resúmenes.
3.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**4a. El valor está fuera del rango de calibración del sensor:**

1.  El Sistema registra la lectura como inválida y, si el sensor no la tenía, genera la alerta «lectura inválida».
2.  La lectura no se compara ni dispara reglas. El caso de uso continúa con la siguiente lectura o en el paso 7.

**4b. La lectura es válida y el sensor tenía la alerta «lectura inválida»:**

1.  El Sistema resuelve esa alerta.
2.  El caso de uso continúa en el paso 5.

**4c. Es una lectura de nivel de la solución con un valor distinto de «normal» o «bajo»:**

1.  El Sistema rechaza la lectura y deja constancia en el registro técnico de errores.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**5a. La lectura está fuera del umbral efectivo:**

1.  Si el sensor no tenía la alerta «fuera de umbral efectivo», el Sistema la genera, con origen en la telemetría.
2.  El caso de uso continúa en el paso 6.

**5b. La lectura está dentro del umbral efectivo y el sensor tenía la alerta «fuera de umbral efectivo»:**

1.  Si la lectura está a más de la histéresis de la variable de cada límite, el Sistema resuelve esa alerta; si no, la alerta sigue activa.
2.  El caso de uso continúa en el paso 6.

**5c. El invernadero no tiene umbral efectivo (no tiene lotes activos ni siembras a realizar):**

1.  El Sistema no compara la lectura ni evalúa las reglas. La última evaluación de las reglas del sensor pasa a «sin evaluar» y su contador de confirmación, a cero.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**5d. El sensor está en un sector fuera de servicio:**

1.  El Sistema no compara la lectura ni evalúa sus reglas.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**5e. Es una lectura de intensidad lumínica fuera del horario de luz de la Configuración Operativa:**

1.  El Sistema no la compara con el umbral efectivo ni evalúa sus reglas. La lectura sí cuenta para el fotoperíodo.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**5f. Es una lectura de temperatura de la solución:**

1.  Si el sistema IoT tiene un rango de temperatura de la solución (regla 7 de IOT-MOD-SIS), el Sistema la compara con él: fuera del rango genera la alerta «solución fuera de rango», si el sensor no la tenía; dentro del rango, a más de la histéresis de cada límite, la resuelve. Sin rango, no la compara.
2.  No evalúa reglas, porque la temperatura de la solución no las admite. El caso de uso continúa con la siguiente lectura o en el paso 7.

**5g. Es una lectura de nivel de la solución:**

1.  Si el valor es «bajo», el Sistema genera la alerta «nivel de solución bajo», si el sensor no la tenía, y la revisión periódica la notifica por correo dentro de los 5 minutos siguientes; si es «normal», la resuelve. *(corregido el 21/11/2026, D-71: antes decía «y la notifica por correo»)*
2.  No evalúa reglas, porque el nivel de la solución no las admite. El caso de uso continúa con la siguiente lectura o en el paso 7.

**6a. La condición de una regla se cumple y completa la confirmación (antes no se cumplía o no estaba evaluada):**

1.  El Sistema emite un comando automático para el actuador y la acción de la regla, con su valor a aplicar, asociado a la regla y con la descripción de la regla que lo disparó.
2.  Asocia la telemetría a la regla y crea el registro de bitácora del comando.
3.  Registra la última evaluación de la regla como «cumplida».
4.  El caso de uso continúa con la siguiente regla, la siguiente lectura o el paso 7.

**6a.1a. El actuador de la regla tiene un comando pendiente, no está activo, la acción es incompatible con el nodo o no pasó el tiempo mínimo entre comandos de su tipo desde el último comando ejecutado:**

1.  El Sistema no emite el comando y deja la última evaluación de la regla como «no cumplida», para volver a intentarlo con la próxima lectura si la condición sigue.
2.  El caso de uso continúa con la siguiente regla, la siguiente lectura o el paso 7.

**6b. La condición de una regla ya se cumplía:**

1.  El Sistema no emite ningún comando, y la regla sigue «cumplida».
2.  El caso de uso continúa con la siguiente regla, la siguiente lectura o el paso 7.

**6c. La condición de una regla se cumple, pero todavía no completó la confirmación:**

1.  El Sistema suma uno al contador de confirmación de la regla, sin emitir comandos.
2.  El caso de uso continúa con la siguiente regla, la siguiente lectura o el paso 7.

**6d. El nodo central informa el modo «local»:**

1.  El Sistema no evalúa las reglas del sensor; su última evaluación y su contador no cambian.
2.  El caso de uso continúa con la siguiente lectura o en el paso 7.

**Requisitos especiales:**

  - Cada lectura, cada estado y cada anuncio se procesan como una transacción independiente.
  - El control de concurrencia asegura una sola alerta activa por equipo y tipo (y por identificador, en la de dispositivo no registrado) y un solo comando pendiente por actuador, aun con mensajes simultáneos del nodo, emisiones manuales (IOT-EMT-CMD) y la revisión periódica.
  - La revisión periódica corre como una tarea programada cada 5 minutos, independiente de los usuarios y de los mensajes del nodo. Es idempotente: ejecutarla dos veces seguidas no duplica alertas, correos, resúmenes ni fotoperíodos.
  - El correo de una alerta lo envía la revisión periódica, después de confirmada la transacción que la generó y fuera de toda transacción. Si el envío falla, se reintenta en la revisión siguiente, y la alerta queda registrada aunque el correo no salga. *(corregido el 21/11/2026, D-71: antes decía «El correo de una alerta se envía después de confirmar la transacción que la generó. Si el envío falla, se reintenta»)*
  - Una lectura aceptada se ve en el panel de monitoreo en no más de 30 segundos (nota de presentación, «Restricciones tecnológicas y operativas»).
  - La API limita la cantidad de mensajes por minuto y el tamaño de cada mensaje de un nodo, y rechaza los que exceden el límite.
  - El token solo autoriza la comunicación de ese nodo con la API: no da acceso a pantallas ni a datos de otros invernaderos. Toda comunicación se hace por HTTPS (SEG-16).
  - La lógica de este caso de uso no depende de la forma de comunicación: la API solo traduce el mensaje del nodo y llama a los servicios del dominio, de modo que otra forma de comunicación, como MQTT mediante un agente, no cambie las reglas.
  - El cálculo del umbral efectivo es el mismo que usa Planificar Siembra (PROD-PNF-SMB): una sola función del dominio, sin duplicarla.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un proceso automático del Sistema, con el nodo central o la revisión periódica que lo originó.

**Lista de tecnología y variaciones de datos:**

  - 1a. Los mensajes van en formato JSON. Un mensaje puede traer varias lecturas.
  - 1b. Cada lectura trae el identificador del sensor (regla 2 de IOT-ALT-HDW), el valor en la unidad del sensor («normal» o «bajo» para el nivel de la solución) y, si la tiene, la fecha y la hora de medición en formato ISO 8601 con zona horaria. El nodo omite la fecha y la hora si su reloj no está sincronizado (guía de integración del nodo).
  - 1c. Cada estado trae el identificador del equipo y uno de estos valores: en línea, desconectado o en falla; o, para un actuador, su estado operativo (encendido, apagado o el valor de su posición o nivel).
  - 1d. El modo del nodo es «remoto» o «local».
  - 1e. El anuncio trae la lista de equipos del nodo: identificador, sensor o actuador y, para los actuadores, los comandos del catálogo de capacidades que soportan (regla 7 de IOT-ALT-TAC).

**Frecuencia:** Una lectura cada 30 a 60 segundos por sensor; los estados, cuando cambian; el modo, cuando cambia; el anuncio, cuando el nodo se conecta y cuando cambian sus equipos. La revisión periódica, cada 5 minutos. A confirmar con el Jardín Botánico.

**Reglas de negocio:**

  - **Origen de los mensajes:** solo se aceptan mensajes del nodo central con su token vigente, y solo sobre los equipos registrados de su propio sistema IoT (pre-registro). Un sistema desconectado no acepta mensajes. (Paso 2, extensiones \*a y 3a)
  - **Formato unificado:** cada sensor mide una sola variable, con su unidad fija: temperatura en °C, humedad en % HR, intensidad lumínica en lux, temperatura de la solución en °C, y nivel de la solución como «normal» o «bajo» (regla 4 de IOT-ALT-HDW). Un equipo que mide dos variables se registra como dos sensores. Lo que mande cada equipo se traduce a este formato fuera de InfoPonia: en el nodo o en un agente entre el broker y la API. (Paso 1)
  - **Fecha y hora de la lectura:** las de medición que informa el nodo; si faltan, las de recepción. Se rechazan las futuras, con 5 minutos de tolerancia. Las atrasadas se aceptan, porque un nodo con conectividad inestable puede enviarlas acumuladas (nota de presentación, «Restricciones del entorno y de la organización»). (Paso 3, extensiones 3d y 3e)
  - **Lectura atrasada:** una lectura medida hace más que la antigüedad máxima de la Configuración Operativa (valor inicial 5 minutos). Se guarda y alimenta los resúmenes y el fotoperíodo, pero no genera ni resuelve alertas de lectura inválida, de umbral, de rango ni de nivel, y no dispara reglas, porque describe una situación que ya pasó. (Extensión 3f)
  - **Lectura válida:** está dentro del rango de calibración del sensor; el nivel de la solución no tiene calibración y solo admite «normal» o «bajo». La marca «válida» o «inválida» se guarda con la lectura, para que no cambie si después se modifica la calibración (regla 6 de IOT-MOD-HDW). Una lectura inválida no se compara ni dispara reglas. (Paso 4, extensiones 4a y 4c)
  - **Umbral efectivo:** intersección de los rangos mínimo y máximo de temperatura ambiente, humedad, intensidad lumínica y fotoperíodo de las variedades de los lotes activos y de las siembras a realizar del invernadero (PROD-PNF-SMB, regla «Umbral efectivo»). Se calcula por invernadero en cada evaluación; no se guarda. Se compara con las lecturas de temperatura, humedad e intensidad lumínica, y con el fotoperíodo diario. (Paso 5, extensión \*b)
  - **Rango de la solución:** la temperatura de la solución se compara con el rango del sistema IoT (regla 7 de IOT-MOD-SIS), no con el umbral efectivo; el nivel de la solución genera una alerta cuando es «bajo». Ninguno de los dos admite reglas: la solución se monitorea, no se gestiona. (Extensiones 5f y 5g)
  - **Histéresis:** cada variable tiene una histéresis en la Configuración Operativa (valores iniciales: 1 °C para la temperatura y la temperatura de la solución, 3 % HR y 2.000 lux). Una alerta de umbral o de rango se genera apenas la lectura sale del límite, y se resuelve recién cuando vuelve a quedar dentro a más de la histéresis de cada límite. Así, una variable que oscila justo en un límite no abre y cierra la alerta muchas veces. (Extensiones 5b y 5f)
  - **Cuándo no se evalúa una lectura:** no se compara ni se evalúan sus reglas si es inválida, si está atrasada, si el sensor está fuera de servicio o en un sector fuera de servicio, si el invernadero no tiene umbral efectivo (para las variables que se comparan con él) o si es de intensidad lumínica fuera del horario de luz. Las reglas tampoco se evalúan mientras el nodo informa el modo «local». (Extensiones 3c, 3f, 4a, 5c a 5e y 6d)
  - **Alertas:**

      - hay a lo sumo una alerta activa por equipo y por tipo; la de dispositivo no registrado, una por identificador dentro del sistema IoT;
      - se resuelven solas cuando desaparece lo que las originó, y no se resuelven a mano;
      - las recibe el Agrónomo del invernadero o, si no tiene un Agrónomo activo, el Gerente;
      - su severidad (Alerta.nivelSeveridad) la fija el tipo y se guarda con la alerta: crítica para comando fallido, nodo sin comunicación, nivel de solución bajo y dispositivo en falla; advertencia para fuera de umbral efectivo, solución fuera de rango, lectura inválida, dispositivo sin actividad y configuración incompatible; informativa para dispositivo no registrado;
      - las de severidad crítica se notifican además por correo, una sola vez, dentro de los 5 minutos siguientes, por la revisión periódica; *(corregido el 21/11/2026, D-71: antes decía «al generarse»)*
      - su origen sigue la restricción C5: las de umbral efectivo de una lectura, solución fuera de rango y nivel de solución bajo, en la telemetría (R053); la de umbral efectivo del fotoperíodo y las de lectura inválida, sin actividad, en falla y configuración incompatible, en el equipo (R052); la de dispositivo no registrado y la de nodo sin comunicación no tienen origen en el modelo, y el identificador o el nodo van en su descripción;
      - no generan registro de bitácora (R055). (Extensiones \*b, 1a, 1c, 3a, 4a, 5a, 5b, 5f y 5g)
  - **Disparo de una regla:** la regla se dispara solo cuando su condición pasa a cumplirse y se confirma, es decir, cuando su última evaluación era «no cumplida» o «sin evaluar» y la condición se cumple en la cantidad de lecturas válidas seguidas de confirmación de la Configuración Operativa (valor inicial 3). Una lectura que no cumple la condición vuelve el contador a cero. La histéresis se aplica a las condiciones: «supera el máximo» se cumple con una lectura mayor al máximo y sigue cumpliéndose mientras la lectura no baje del máximo menos la histéresis; «baja del mínimo» es simétrica; «vuelve a quedar dentro del umbral efectivo» se cumple con una lectura dentro del umbral a más de la histéresis de cada límite, y sigue cumpliéndose mientras la lectura no salga del umbral. La última evaluación vuelve a «sin evaluar», y el contador a cero, al activar el sistema IoT, al modificar la regla, cuando el invernadero se queda sin umbral efectivo y cuando el nodo vuelve del modo «local». (Paso 6, extensiones 1b, 5c, 6a, 6b y 6c)
  - **Actuador ocupado:** si el actuador de la regla tiene un comando pendiente, no está activo, la acción es incompatible con el nodo o no pasó el tiempo mínimo entre comandos de su tipo desde el último comando ejecutado (regla 9 de IOT-ALT-TAC), la regla no emite y queda «no cumplida», para dispararse con la próxima lectura si la condición sigue. Si dos reglas se disparan sobre el mismo actuador, emite la primera y la otra espera por el mismo mecanismo. (Extensión 6a.1a)
  - **Comando automático:** cumple la regla «Comando válido» de IOT-EMT-CMD, no tiene Agrónomo (R050 en 0..1), está asociado a la regla que lo disparó y deja su registro de bitácora (nota de presentación, proceso «Emisión Automática de Comandos ante Umbral Agronómico Superado»). Lo resuelve IOT-RSV-CMD. (Extensión 6a)
  - **Estados de los equipos:** son optativos para el nodo. «Desconectado» genera la alerta «dispositivo sin actividad»; «en línea», o cualquier mensaje del equipo, la resuelve. «En falla» pasa el equipo a «fuera de servicio», que vuelve a «activo» solo con IOT-MOD-HDW o con un mantenimiento exitoso; no crea una orden de mantenimiento automática. El estado operativo de un actuador que informa el nodo es su estado actual; no se deduce del último comando (IOT-EMT-CMD). (Extensión 1a)
  - **Modo del nodo:** informarlo es optativo; mientras el nodo no lo informe, se considera «remoto». En modo «local» el nodo actúa por su cuenta (guía de integración del nodo), y InfoPonia supervisa: registra lecturas y estados, genera alertas, pero no evalúa reglas ni entrega comandos, para no contradecir el control local. (Extensiones 1b y 6d)
  - **Anuncio de equipos:** es optativo para el nodo. Sin anuncio, la compatibilidad de los actuadores queda «sin verificar» y no se restringe ninguna acción. Con anuncio, una acción cuyo comando el nodo no soporta queda marcada como incompatible para ese actuador y no se ofrece en comandos ni en reglas (regla 14 de IOT-ALT-HDW); la alerta «configuración incompatible» se resuelve sola cuando no queda ninguna acción incompatible en el actuador. No se resuelve con el tiempo: si el equipo nunca va a soportar la acción, queda abierta hasta que se corrija la configuración, ya sea porque el Agrónomo cambia el tipo del actuador (IOT-MOD-HDW, solo si todavía no tiene comandos ni reglas; si no, lo da de baja y registra uno nuevo), el Gerente corrige las acciones del tipo (IOT-MOD-TAC) o el nodo anuncia el comando; la compatibilidad se calcula por actuador contra el anuncio de su propio nodo, de modo que un tipo compartido puede ser compatible en un invernadero e incompatible en otro. La comparación con el último anuncio se repite al recibir un anuncio nuevo, al registrar o reactivar un actuador, al cambiar su tipo (IOT-ALT-HDW e IOT-MOD-HDW) y al cambiar las acciones de su tipo (IOT-MOD-TAC). (Extensión 1c)
  - **Inactividad:** un sensor sin lecturas durante los minutos sin actividad de la Configuración Operativa genera la alerta «dispositivo sin actividad», y un nodo sin comunicación durante los minutos sin comunicación genera la alerta «nodo sin comunicación», que se notifica por correo. Las detecta la revisión periódica cada 5 minutos, aunque nadie esté usando InfoPonia. Un sensor «sin confirmar» o un nodo que todavía no se comunicó no las generan: que nunca haya reportado indica que todavía no se terminó de instalar o configurar, y se muestra como «sin confirmar» o «sin señal» (IOT-CNS-HDW e IOT-REG-SIS), sin alertas ni correos. (Extensión \*b)
  - **Fotoperíodo:** horas del día en que un sensor de intensidad lumínica midió más que el umbral de luz para el fotoperíodo de la Configuración Operativa (a confirmar con el Jardín Botánico). Se calcula al cerrar cada día, en la zona horaria del invernadero, sumando el tiempo entre lecturas válidas consecutivas que superan el umbral. Si al sensor le faltaron lecturas durante más que los minutos sin actividad, el fotoperíodo del día se marca incompleto y no se compara. No admite reglas. (Extensión \*b)
  - **Resúmenes horarios:** por cada sensor y cada hora se guardan el mínimo, el promedio y el máximo de sus lecturas válidas, la cantidad de lecturas y la cantidad de inválidas. Sirven para los gráficos de más de 24 horas (regla 4 de IOT-CNS-LEC) y para conocer las condiciones en que creció un lote. Son un dato de diseño, no del dominio, y no se borran por la retención. (Extensión \*b)
  - **Retención:** las lecturas se guardan durante los días de retención de la Configuración Operativa (valor inicial 7) y después se borran, salvo las que originaron una alerta o dispararon una regla. El borrado lo hace la revisión periódica. (Extensión \*b)
  - **Estado actual de un equipo:** un equipo del que nunca llegó ningún mensaje está «sin confirmar»; deja de estarlo con su primer mensaje. (Postcondiciones b y m)

**Temas abiertos:**

  - *(Registrados en pendientes_MD como MD-98 a MD-113, ronda 23, y aplicados en `docs/modelo/iot.md`.)* **Cambios de modelo pendientes de registrar en pendientes_MD:** atributo nuevo de Telemetria (marca válida / inválida); atributos nuevos de ReglaActuacion (última evaluación: cumplida / no cumplida / sin evaluar, y contador de confirmación); Actuador (estado informado, fecha y hora, y marca de compatibilidad con sus acciones incompatibles); NodoCentral (modo); registro de los equipos anunciados por el nodo (dato de diseño); tipos de alerta «fuera de umbral efectivo», «lectura inválida», «dispositivo en falla», «dispositivo no registrado», «dispositivo sin actividad», «nodo sin comunicación», «solución fuera de rango», «nivel de solución bajo» y «configuración incompatible»; resúmenes horarios y fotoperíodo diario (datos de diseño).
  - **ADM-MOD-CFG** debe sumar los parámetros del IoT: cantidad de reintentos, intervalo de reintento, horario de luz, minutos sin actividad de un dispositivo, minutos sin comunicación del nodo, días de retención de la telemetría, histéresis por variable, lecturas de confirmación, antigüedad máxima de una lectura y umbral de luz para el fotoperíodo.
  - **Notificación por correo:** usa el mecanismo de correo del Sistema; el texto y el formato del correo se definen en el diseño.

**Guía de integración del nodo:** redactada con la API en `docs/api/nodo/README.md` (lote I2a, D-74), con su implementación de referencia en `docs/api/nodo/node-red/` *(actualizado el 21/11/2026: antes decía «documento a redactar junto con la API»)*.

## Cómo se aplica en la ronda «IoT 1» (D-44, D-70, D-71, D-74, D-75, D-76)

Modelo: `docs/modelo/iot.md` («SistemaIoT», «Hardware», «NodoCentral», «Sensor», «Actuador», «EquipoAnunciado», «Telemetria»,
«AlertaIot», «Tipos de alerta del IoT» y «Parámetros IoT de ConfiguracionOperativa»). Contrato: `docs/api/nodo/` (mensajes, respuestas,
errores y ejemplos). Alcance, conectividad y bloqueos generales: `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco».

### Reparto

| Parte del caso de uso | Tarea | Qué hace IOT-03 mientras tanto |
|---|---|---|
| Pasos 1 a 5 y 7; \*a; 1a a 1c; 3a a 3f; 4a a 4c; 5a a 5g | **IOT-03** | — |
| Paso 6 y 6a a 6d (reglas de actuación); postcondiciones i a l | IOT-06 | Deja el punto donde se evalúan: `evaluar_reglas_de_la_lectura(...)`, que no hace nada y dice «Se completa en IOT-06». Cómo lo completa IOT-06: «Reglas de actuación», abajo |
| 1b.2 (en modo local no se entregan comandos) | IOT-05 | Solo guarda el modo: los comandos todavía no existen |
| 1b.3 y 5c (reiniciar la evaluación de las reglas) | IOT-06 | `al_volver_a_remoto(sistema)` y el reinicio de 5c no hacen nada; dicen «Se completa en IOT-06» |
| Postcondición p, «lo explica un comando de InfoPonia» | IOT-05 | `explica_un_comando(actuador, estado)` devuelve falso (D-75, punto 1) |
| \*b (revisión periódica: sin actividad, nodo sin comunicación, «no registrado» sin mensajes, resúmenes, fotoperíodo, retención) | IOT-04 | Carga `AlertaIot.ultimo_mensaje_en` (D-76, punto 3). Hasta IOT-04 esas alertas no se generan ni se resuelven por tiempo, y no se borra nada (D-71, punto 5). Cómo lo hace IOT-04: «La revisión periódica», abajo |
| Postcondición y, el correo de las críticas | IOT-04 | Las alertas críticas se crean con `correo_enviado_en` nulo; la revisión las manda en cuanto existe (D-71, «Consecuencias») |
| Requisito «una lectura se ve en el panel en no más de 30 segundos» | IOT-04 | — |

### La API (D-70, D-74)

- **Dónde.** Un paquete `iot/api/` dentro de la app:
  - `urls.py` (`app_name = "iot_api"`): `lecturas`, `estados`, `modo` y `anuncio` (sin barra final, como el contrato), y una ruta final que
    atrapa cualquier otra y responde 404 `ruta_inexistente` en JSON. Se incluye en `config/urls.py` con
    `path("api/iot/v1/", include("iot.api.urls"))`.
  - `vistas.py`: una vista por ruta, más el código común. Solo traducen y orquestan (D-70, punto 4): **ninguna regla de negocio en la vista**.
  - `traduccion.py`: convierte el JSON en objetos simples (`LecturaRecibida`, `EstadoRecibido`, `EquipoRecibido`), con la verificación de
    **forma** (campos conocidos, tipos de la envoltura, identificador con la forma de la regla 2 de IOT-ALT-HDW). No consulta la base.
  - `autenticacion.py`: `sistema_del_encabezado(valor) -> (resumen, sistema | None)` con `core.enlaces.resumen_de`. Nunca guarda, compara
    ni registra el token.
  - `limites.py`: las tres constantes (`PEDIDOS_POR_MINUTO = 120`, `BYTES_POR_PEDIDO = 262144`, `ELEMENTOS_POR_PEDIDO = 500`) y
    `contar_pedido(resumen, ahora) -> int | None` (devuelve los segundos de `Retry-After` si se pasó). Ventana fija por minuto de reloj; la
    clave de la caché es `iot:pedidos:<16 primeros caracteres del resumen>:<AAAAMMDDHHMM>` con `cache.add` y `cache.incr` (vence a los 120
    segundos). Usa la caché por defecto de Django: sin dependencias (D-70, punto 5).
  - `respuestas.py`: `respuesta_ok(datos, ahora)` y `respuesta_error(codigo_http, error, ahora, detalle, **extra)`, que agregan `version` y
    `servidor_en`; las 401 suman `WWW-Authenticate: Bearer`; la 405, `Allow: POST`; la 429, `Retry-After`.
  - `reloj.py`: `ahora()` (`timezone.now()`). Las vistas la llaman **una vez por pedido** y pasan `ahora` a los servicios, que nunca leen la
    hora por su cuenta. Las pruebas la reemplazan con `unittest.mock.patch`.
- **Sin sesión ni CSRF.** El proyecto exige sesión en toda vista con `LoginRequiredMiddleware` (SEG-13, `config/settings.py`): cada vista de
  la API lleva **`login_not_required`** (`django.contrib.auth.decorators`, como `core/views.py`), además de `csrf_exempt` y `never_cache`.
  No usa `rol_requerido` y no lee ni escribe la sesión; `ContrasenaTemporalMiddleware` no la afecta porque el pedido no tiene usuario. No
  hace falta tocar ningún middleware. El 405 lo arma la vista (no `require_POST`, que responde HTML). *(Corregido el 22/11/2026, lote I2b:
  antes decía «si un middleware exige sesión, se excluye `/api/`»; el proyecto ya tiene el decorador para eso.)*
- **Orden de verificación** de un pedido: exactamente la tabla de `docs/api/nodo/respuestas_y_errores.md`, sección 3. El tamaño se mira con
  `Content-Length` si viene y, si no, con `len(request.body)`; un `RequestDataTooBig` de Django también es 413. El JSON se lee con
  `json.loads(cuerpo, parse_float=Decimal, parse_constant=<función que lanza>)`: así `NaN` e `Infinity` son `json_invalido` y los decimales
  no pasan por `float`.
- **La comunicación (postcondición a).** Superada la verificación (respuesta 200), y antes de procesar los elementos, en **su propia
  transacción**: `registrar_comunicacion(sistema_id, ahora)` bloquea el invernadero (`bloquear_invernadero_para_alertas`), pone
  `NodoCentral.ultima_comunicacion = ahora` y resuelve la alerta `iot_nodo_sin_comunicacion` (clave `nodo:<id del nodo>`) si estaba activa.
  Un lote vacío hace solo esto: es el latido (D-74, punto 2).
- **Un elemento, una transacción** (garantías mínimas y «Requisitos especiales»): cada lectura y cada estado se procesan en su propio
  `transaction.atomic()`. Un error inesperado en uno se registra con `logger.exception` y ese elemento vuelve con `error_interno`; los demás
  se procesan igual. El anuncio es una sola transacción (se procesa entero o nada).
- **Registro técnico de errores.** `logging.getLogger("iot.api")`: un `warning` por elemento rechazado con el sistema, el identificador, el
  motivo y, si sirve, el valor recibido; un `exception` por `error_interno`. **Nunca el token ni el encabezado `Authorization`.** No hay
  tabla de errores: es el registro del servidor.

### Servicios (`iot/servicios/`)

Un archivo por entidad raíz (D-37). Todos reciben `ahora` y los datos ya traducidos; ninguno conoce HTTP.

| Archivo | Funciones |
|---|---|
| `nodo.py` | `sistema_por_resumen(resumen) -> SistemaIoT \| None` (por `token_resumen`, con estado distinto de `inactivo`); `registrar_comunicacion(sistema_id, ahora)`; `registrar_modo(sistema_id, modo, ahora) -> bool` (si cambió); `al_volver_a_remoto(sistema)` («Se completa en IOT-06») |
| `lecturas.py` | `contexto_del_mensaje(sistema, ahora) -> ContextoDeLecturas` (los parámetros de la Configuración Operativa, el umbral efectivo y el rango de la solución, **una vez por pedido**); `registrar_lectura(contexto, lectura, ahora) -> ResultadoDeLectura`; `evaluar_reglas_de_la_lectura(contexto, sensor, telemetria)` («Se completa en IOT-06»); `tiene_lecturas(sensor)` con datos reales |
| `estados.py` | `registrar_estado(sistema_id, estado, ahora) -> ResultadoDeEstado`; `explica_un_comando(actuador, estado) -> bool` («Se completa en IOT-05») |
| `anuncios.py` | `registrar_anuncio(sistema_id, equipos, ahora) -> ResultadoDeAnuncio` |
| `alertas_iot.py` | `asegurar_alerta_iot(invernadero_id, sistema, tipo, clave, descripcion, hardware=None, telemetria=None)` y `resolver_alerta_iot(invernadero_id, tipo, clave)`: llaman a `maestros.servicios.alertas` y crean el `AlertaIot` **solo** cuando la alerta es nueva. Si IOT-02 ya dejó un ayudante así (para la compatibilidad), se reutiliza y no se duplica |

### Una lectura (pasos 3 a 5; extensiones 3a a 5g)

Orden dentro de la transacción de la lectura. Cada paso que termina la lectura lo dice.

1. **Bloqueos:** el invernadero (`bloquear_invernadero_para_alertas`) y después el sistema (`FOR NO KEY UPDATE`), releído. Si ya no está
   activo: `sistema_desconectado` (sin escribir nada).
2. **El equipo** (paso 3, extensiones 3a y 3b): se busca entre los equipos **no dados de baja** del sistema por
   `Lower(identificador_equipo)` igual al identificador recortado y en minúsculas.
   - Ninguno: si hay uno dado de baja con ese identificador, `equipo_dado_de_baja`; si no, `equipo_no_registrado`. En los dos casos,
     `asegurar_alerta_iot(..., "iot_dispositivo_no_registrado", clave="id:<identificador en minúsculas>")`, sin hardware ni telemetría
     (postcondición t), y `AlertaIot.ultimo_mensaje_en = ahora`, tanto si la alerta es nueva como si ya estaba activa (la revisión la
     resuelve cuando deja de recibir mensajes: \*b.3, D-76 punto 3). Termina.
   - Es un actuador: `no_es_sensor`. Termina.
   - Después se bloquea el sensor (`FOR NO KEY UPDATE`).
3. **La fecha** (paso 3, extensiones 3d y 3e; D-74 punto 5): sin `medida_en`, vale `ahora`. Con `medida_en`: `datetime.fromisoformat`; si
   falla o no tiene zona (`tzinfo` nulo), `fecha_invalida`; si es posterior a `ahora + 5 minutos`, `fecha_futura`. Termina en los dos casos.
4. **El valor** (extensión 4c; D-74 punto 7): en el nivel de la solución, solo `"normal"` o `"bajo"`; en las demás variables, un número JSON
   (entero o `Decimal`, **nunca** `bool`) de valor absoluto hasta 9.999.999,99, redondeado a dos decimales con `ROUND_HALF_UP`. Si no:
   `valor_invalido`. Termina.
5. **Repetida** (D-74 punto 6): si ya existe una `Telemetria` de ese sensor con ese `medida_en`, el resultado es `duplicada` y **no se
   escribe nada más** (ni el último mensaje del equipo). El índice único `(sensor, medida_en)` lo respalda: un `IntegrityError` al crear (en
   un `atomic` anidado) también es `duplicada`, nunca un 500.
6. **Guardar** (postcondiciones b y c): la `Telemetria` con `medida_en`, `valor_medido` o `estado_nivel_medido`, `unidad_medida_telemetria`
   (la del sensor; nula en el nivel) y `valida` (nula en el nivel; si no, `valor_calibracion_min <= valor <= valor_calibracion_max`).
   `Hardware.ultimo_mensaje_en = ahora` (deja de estar «sin confirmar»). Se resuelve la alerta `iot_dispositivo_sin_actividad` del sensor
   (clave `hw:<id>`). **Desde acá la lectura es `aceptada`**, con `valida` y `atrasada` en la respuesta.
7. **Atrasada** (extensión 3f): si `medida_en < ahora − minutos_antiguedad_lectura`, termina (no genera ni resuelve otras alertas).
8. **Sensor fuera de servicio** (extensión 3c): `estado_hardware = fuera_de_servicio`: termina.
9. **Calibración** (paso 4, extensiones 4a y 4b): inválida → `asegurar_alerta_iot(..., "iot_lectura_invalida", "hw:<id>", hardware=sensor)`
   y termina. Válida → resolver esa alerta, si estaba.
10. **Según la variable:**
    - **Temperatura, humedad e intensidad lumínica** (paso 5, extensiones 5a a 5e):
      - Intensidad lumínica con la hora local de `medida_en` (zona del proyecto, `settings.TIME_ZONE`) antes de `hora_inicio_luz` o desde
        `hora_fin_luz`: termina (5e).
      - Sensor en un sector `fuera_de_servicio`: termina (5d; D-75, punto 7).
      - Sin umbral efectivo (`contexto.umbral is None`, 5c) o con la variable del umbral vacía (D-75, punto 3): se **resuelve** la alerta
        `iot_fuera_de_umbral` del sensor si estaba (D-75, punto 4) y termina.
      - Con umbral: la variable del sensor usa `temp_ambiente`, `humedad` o `intensidad_luz` del umbral, y la histéresis
        `histeresis_temperatura`, `histeresis_humedad` o `histeresis_luz`. Fuera (`valor > maximo` o `valor < minimo`) →
        `asegurar_alerta_iot(..., "iot_fuera_de_umbral", "sensor:<id>", telemetria=esta)`. Dentro y a más de la histéresis de cada límite
        (`minimo + h <= valor <= maximo − h`, con `h = min(histéresis, (maximo − minimo) / 2)`, D-75 punto 2) → resolver. Entre el límite y
        la histéresis, la alerta queda como está.
      - Si la lectura llegó hasta acá (válida, reciente, sensor activo y comparada), `evaluar_reglas_de_la_lectura(...)` (IOT-06).
    - **Temperatura de la solución** (5f): sin rango en el sistema (`temp_solucion_min` nulo), termina. Con rango, lo mismo que arriba con
      `histeresis_temp_solucion` y la alerta `iot_solucion_fuera_de_rango` (clave `sensor:<id>`, telemetría). El sector fuera de servicio no
      la frena (D-75, punto 7).
    - **Nivel de la solución** (5g): `bajo` → `asegurar_alerta_iot(..., "iot_nivel_solucion_bajo", "sensor:<id>", telemetria=esta)`;
      `normal` → resolver. El sector fuera de servicio no lo frena.
11. **Auditoría** (postcondición z): solo si la lectura generó o resolvió alguna alerta (abajo).

### Un estado (extensión 1a)

1. Bloqueos y búsqueda del equipo como en la lectura (pasos 1 y 2), sin el rechazo `no_es_sensor`: vale para sensores y actuadores. La
   alerta «dispositivo no registrado» lleva el estado informado en su descripción.
2. `informado_en` como `medida_en` (paso 3; D-75, punto 6). Sin fecha, `ahora`.
3. `estado` (D-75, punto 6): `en_linea`, `desconectado`, `en_falla`, o un estado operativo (`encendido`, `apagado`, `abierto`, `cerrado`,
   `nivel:<entero>`, `posicion:<entero>`, con `^(nivel|posicion):-?\d{1,6}$`). Otro valor, o uno operativo para un sensor:
   `estado_invalido`. Termina.
4. Se bloquea el equipo. `ultimo_mensaje_en = ahora`. Según el estado:
   - `en_linea`: resolver `iot_dispositivo_sin_actividad` (`hw:<id>`).
   - `desconectado`: `asegurar_alerta_iot(..., "iot_dispositivo_sin_actividad", "hw:<id>", hardware=equipo)`.
   - `en_falla`: si está `activo`, pasa a `fuera_de_servicio` (si ya lo estaba, no cambia); `asegurar_alerta_iot(...,
     "iot_dispositivo_en_falla", "hw:<id>", hardware=equipo)` (crítica: el correo lo manda la revisión, D-71). No crea una orden de
     mantenimiento (regla «Estados de los equipos»).
   - Estado operativo: resolver `iot_dispositivo_sin_actividad`. Si es distinto del `estado_informado` actual: `estado_informado` = el
     nuevo, `estado_informado_en = informado_en` y `cambiado_en_invernadero` = falso si antes era nulo y, si no, `not
     explica_un_comando(actuador, estado)` (D-75, punto 1). Si es igual, no cambia nada más.
5. Auditoría si cambió el estado del equipo, su estado informado o alguna alerta.

### El modo (extensión 1b)

`registrar_modo`: bloquea el invernadero, el sistema y el nodo (en ese orden) y, si el modo cambió, lo guarda, audita y, si volvió a
`remoto`, llama a `al_volver_a_remoto(sistema)` (IOT-06). Si no cambió, no escribe ni audita (`cambio: false`). Otro valor que `remoto` o
`local` lo rechaza la traducción (400).

### El anuncio (extensión 1c)

`registrar_anuncio`, en una transacción: bloquea el invernadero y el sistema; borra los `EquipoAnunciado` del sistema y crea los nuevos
(identificador, clase, comandos por `ComandoCatalogo.codigo`, `anunciado_en = ahora`); llama a
`compatibilidad.recalcular_compatibilidad(actuadores)` con **todos** los actuadores no dados de baja del sistema (los que no figuran quedan
`sin_verificar`; la función, de IOT-02, genera o resuelve la alerta «configuración incompatible»). La respuesta lista cada actuador con su
compatibilidad y los identificadores anunciados sin registrar (`docs/api/nodo/mensajes.md`, sección 4). El anuncio no cambia
`ultimo_mensaje_en` (no es un mensaje «sobre» un equipo). Auditoría si cambió la compatibilidad de algún actuador.

### Alertas: textos y origen

Todas de clase ESTADO, con los códigos, severidades, orígenes y claves de `docs/modelo/iot.md`, «Tipos de alerta del IoT»; las crea y
resuelve `alertas_iot.py`. Los valores se escriben con coma decimal, sin ceros de más y con punto de miles (`28,4`, `32.000`), con la
unidad del sensor (`°C`, `% HR`, `lux`). Función `iot/textos.py`, `valor_legible(valor, unidad)`.

| Alerta | Descripción | Vínculo `AlertaIot` |
|---|---|---|
| `iot_fuera_de_umbral` | «{identificador} · {valor} (máximo efectivo {límite})» o «(mínimo efectivo {límite})» | `telemetria` = la lectura que la generó |
| `iot_solucion_fuera_de_rango` | «{identificador} · {valor} (máximo de la solución {límite})» o «(mínimo de la solución {límite})» | `telemetria` |
| `iot_nivel_solucion_bajo` | «{identificador} · informa «bajo»» | `telemetria` |
| `iot_lectura_invalida` | «{identificador} · {valor}, fuera de la calibración ({mínimo} a {máximo})» | `hardware` = el sensor |
| `iot_dispositivo_sin_actividad` (por un estado) | «{identificador} · el nodo lo informó desconectado» | `hardware` |
| `iot_dispositivo_en_falla` | «{identificador} · el nodo lo informó en falla» | `hardware` |
| `iot_dispositivo_no_registrado` | Lectura: «El nodo envió una lectura de «{identificador}» ({valor recibido}), que no está registrado.» · Estado: «El nodo envió el estado «{estado}» de «{identificador}», que no está registrado.» | sin hardware ni telemetría; `sistema` siempre |

Ejemplo: «norte/sectorA/temperatura · 28,4 °C (máximo efectivo 26 °C)». La descripción se escribe al crear la alerta y no se actualiza
mientras siga activa. Que un «no registrado» sea de un equipo dado de baja se deduce por el identificador al mostrar la alerta (extensión
3a): no se guarda.

### Auditoría (postcondición z, D-36)

- Acción nueva **`entrega_informacion_iot`** (migración de `core`, solo `choices`), actor `None` (InfoPonia, como los procesos de D-56).
  Un registro **por elemento** (lectura o estado), por modo y por anuncio, **solo si cambió algo** además de la telemetría, la comunicación
  y el último mensaje: una alerta generada o resuelta, el estado de un equipo, su estado informado, el modo o la compatibilidad. Las
  lecturas que no cambian nada no se auditan (postcondición z: «no se auditan una por una»).
- El detalle tiene **solo dos claves** de primer nivel, `datos` y `cambios` (D-36).
  - `datos`: `origen: "nodo_central"`, `sistema: referencia(sistema)`, `mensaje` (`lectura`, `estado`, `modo`, `anuncio` o `comunicacion`, cuando el mensaje
    solo resolvió «nodo sin comunicación»), `identificador` (texto o `null`), `alertas_generadas` y `alertas_resueltas` (listas de `referencia(alerta)`).
  - `cambios`: solo lo que cambió de verdad, cada uno con `antes` y `despues` (D-36 rechaza «antes» igual a «después»). Los decimales y las fechas, como
    texto. En el anuncio, una clave por actuador que cambió: «compatibilidad de <identificador>».
  - Afectados: las alertas, el equipo y, en el anuncio, los actuadores. **Nunca el token.**
- La revisión periódica (IOT-04) tendrá su propia acción.

### Bloqueos y concurrencia

- Orden en toda la API: **invernadero → sistema → equipo** (el de IOT-02 y `docs/api/alertas.md`, sección 3). Ningún bloqueo pasa de un
  elemento al siguiente: cada uno es su transacción.
- Lo garantiza la base, también con mensajes simultáneos (requisito «control de concurrencia»): una alerta de estado activa por invernadero,
  tipo y clave (índice de `maestros`); una lectura por sensor y `medida_en` (índice único, D-74); un nodo por sistema.
- El contador de pedidos vive en la caché por proceso: alcanza para un proceso de gunicorn (D-70, punto 5). Con más procesos, cada uno
  cuenta aparte (se anota si cambia el despliegue).

### Lo que completa en Hardware (IOT-02, disparador «Cuando existan actuadores, comandos y reglas del IoT», punto 3)

- `tiene_lecturas(sensor)` con lecturas reales (la regla 3 de IOT-MOD-HDW ya la usa).
- En la lista y la ficha de equipos (`docs/casos_de_uso/iot/hardware.md`, «Consulta»): la **última lectura** de cada sensor (valor legible
  y hace cuánto; «—» si no tiene) y la **situación** por sus alertas activas: «Sin actividad», «Lectura inválida», «Fuera de umbral», «Fuera
  de rango», «Nivel bajo» (además de las de IOT-02). En los actuadores, el estado informado con su hora y la marca «cambiado en el
  invernadero». Del nodo, el modo y la conectividad reales. Guía visual: `sensorState`, `actState` y `estInf` del prototipo. Sin consultas
  por fila (`assertNumQueries` con tres equipos).
- Los identificadores anunciados del alta (regla 14 de IOT-ALT-HDW) ya leen `EquipoAnunciado`: con IOT-03 tienen datos.

### Reglas de actuación (paso 6, extensiones 6a a 6d) — IOT-06 (D-75, D-78)

IOT-06 completa los tres puntos que IOT-03 dejó vacíos («Reparto»):

- **`evaluar_reglas_de_la_lectura(contexto, sensor, telemetria)`** (`iot/servicios/lecturas.py`). Se llama dentro de la transacción de la
  lectura, en el paso 10 de «Una lectura», solo si la lectura llegó hasta ahí: válida, no atrasada, sensor activo, sector en servicio, con
  umbral y, en la luz, dentro del horario.
  - **6d.** Si el nodo está en modo `local`, vuelve sin tocar nada.
  - Si no, por cada regla **activa** del sensor, en orden de id, aplica la máquina de estados de D-78, punto 8, con la variable y la
    histéresis de la lectura (acotada como en D-75, punto 2), y guarda `ultima_evaluacion` y `contador_confirmacion` (postcondición i).
  - **6a.** Si la regla completa la confirmación, verifica que el actuador no esté ocupado (6a.1a; D-78, punto 8). Si está libre, emite.
- **La emisión** (postcondiciones j a l): un `Comando` pendiente con `regla`, `agronomo` nulo, `valor_comando = aplicar_valor`, la
  descripción de D-78 (punto 9), 0 intentos; el `RegistroComando` `emitido` con responsable nulo; la lectura en `regla.telemetrias`; y
  `ultima_evaluacion = cumplida` con el contador en 0.
  - Antes, `comandos.validar_comando(...)` (IOT-05): si la acción dejó de ser válida, la regla queda ocupada.
  - El bloqueo del actuador sigue al de la lectura (invernadero → sistema → sensor → actuador): las reglas de un sensor que apuntan a
    varios actuadores los bloquean en orden de id.
  - El `IntegrityError` del pendiente único (otra regla o una persona emitieron a la vez) se toma en un `atomic` anidado y deja la regla
    ocupada.
  - La auditoría de la lectura (`entrega_informacion_iot`) suma el comando y el registro de bitácora creados.
- **Reinicios** (`ultima_evaluacion = sin_evaluar`, `contador_confirmacion = 0`), con `reglas.reiniciar_reglas(reglas)`:
  - **5c:** en la lectura de un sensor de un invernadero sin umbral, sus reglas activas;
  - **1b.3:** `al_volver_a_remoto(sistema)`, todas las reglas activas del sistema;
  - **IOT-ACT-SIS** y **IOT-MOD-RGL:** ver `sistema_iot.md` y `reglas_de_actuacion.md`.
- **Pruebas** (IOT-06): `iot/tests/test_iot_ent_inf_reglas.py`, una por extensión (6a, 6a.1a con cada motivo, 6b, 6c y 6d), por condición
  (las tres, con su histéresis y su borde), por reinicio y por las postcondiciones i a l. Además:
  - dos reglas sobre el mismo actuador: emite la primera;
  - una regla ocupada dispara con la lectura siguiente, sin otra confirmación;
  - «vuelve al rango» desde «sin evaluar»;
  - concurrencia: una regla y un comando manual a la vez sobre el mismo actuador, un solo pendiente y sin 500.

### La revisión periódica (extensión \*b) — IOT-04 (D-71, D-76)

**Dónde y cómo se corre (D-71, punto 1).**

- Servicio: `iot/servicios/revision.py`, `revisar(ahora) -> ResumenDeRevision`.
- Comando: `iot/management/commands/revision_iot.py`, sin lógica propia, con las mismas reglas de salida que `proceso_diario` (DIA-01):
  - `--ahora AAAA-MM-DDTHH:MM`: hora local; con un formato inválido, `CommandError`;
  - `--cada N`: repite cada N segundos (N ≥ 10) hasta Ctrl+C, que corta limpio y con código 0;
  - sin opciones, corre una vez.
- Salida: una línea con la hora usada, una por sistema («Norte: 2 alertas generadas · 1 resuelta · 3 resúmenes · 1 fotoperíodo · 120
  lecturas borradas», o «FALLÓ: …») y una de correos («Correos: 1 enviado · 0 fallidos · 0 pendientes sin servidor de correo»).
- Código de salida: 1 si algún sistema falló; 0 si no.
- **No es un paso de `proceso_diario`** (D-56, punto 6): tiene su propio comando y su propio cron (disparador «Cuando se arme el cron
  único», punto 2).

**Reglas comunes (D-71, punto 2):**

- recibe `ahora` y nunca lee la hora por su cuenta;
- **cada sistema IoT activo, en su propia transacción**, en orden de id. Los desconectados y los dados de baja no se revisan;
- si un sistema falla, `logger.exception` (registrador `iot.revision`), se informa y se sigue con los demás;
- es idempotente: dos corridas seguidas con el mismo `ahora` no cambian nada la segunda vez (ni alertas, ni correos, ni resúmenes, ni
  fotoperíodos, ni borrados);
- bloqueos en el orden de la API: invernadero (`bloquear_invernadero_para_alertas`) → sistema → equipos, en orden de id.

**Pasos por sistema**, en el orden de \*b:

1. **Sensores sin actividad** (\*b.1, D-76 punto 1). Cada sensor `activo` con `ultimo_mensaje_en` no nulo y anterior a
   `ahora − minutos_sin_actividad`: `asegurar_alerta_iot(..., "iot_dispositivo_sin_actividad", "hw:<id>", hardware=sensor)`, con la
   descripción «{identificador} · sin lecturas desde las {HH:MM} del {DD/MM}». La resolución la hacen los mensajes (IOT-03), no la
   revisión.
2. **Nodo sin comunicación** (\*b.2, D-76 punto 2). Con `ultima_comunicacion` no nula y anterior a `ahora − minutos_sin_comunicacion`:
   `asegurar_alerta_iot(..., "iot_nodo_sin_comunicacion", "nodo:<id del nodo>")`, sin hardware ni telemetría, con la descripción «{nombre
   del nodo} · sin comunicación desde las {HH:MM} del {DD/MM}». Es crítica: la notifica el paso de correos. La resuelve el próximo mensaje
   aceptado (IOT-03, postcondición a).
3. **«No registrado» sin mensajes** (\*b.3, D-76 punto 3). Cada `AlertaIot` del sistema con alerta activa de tipo
   `iot_dispositivo_no_registrado` y `ultimo_mensaje_en` anterior a `ahora − minutos_sin_actividad`: `resolver_alerta_iot(...)`.
4. **Resúmenes horarios** (\*b.4, D-76 punto 4). Para cada sensor no dado de baja salvo los de nivel, recalcula la hora en curso y las dos
   anteriores, y además toda hora con lecturas que todavía no tenga resumen (así nada se borra sin resumir). Por hora: `minimo`, `promedio` y `maximo` de las
   lecturas **válidas** (nulos si no hubo), `cantidad_lecturas` (todas) y `cantidad_invalidas`. La hora es la local truncada a los minutos
   en 0. Con `update_or_create`. Las consultas son una agregación por sensor y hora (`TruncHour`), nunca una por hora.
5. **Fotoperíodo** (\*b.5, D-76 punto 5). Para cada sensor de intensidad lumínica no dado de baja, los días que faltan, con el cálculo y la
   regla de «incompleto» de D-76. Se guarda `FotoperiodoDiario` (también si es incompleto). Si se puede comparar, contra
   `umbral.fotoperiodo`, en el orden de los días:
   - fuera → `asegurar_alerta_iot(..., "iot_fotoperiodo_fuera_de_umbral", "sensor:<id>", hardware=sensor)`, con la descripción
     «{identificador} · {horas} h de luz el {DD/MM} (mínimo efectivo {mín} h)» o «(máximo efectivo {máx} h)»;
   - dentro → resolverla.
   Un día incompleto o sin umbral no toca la alerta.
6. **Retención** (\*b.6, D-76 punto 6). Un solo `DELETE` por sistema, con las exclusiones (`AlertaIot.telemetria` y
   `ReglaActuacion.telemetrias`). Los resúmenes y los fotoperíodos no se borran nunca.

**Correos** (\*b.2, extensiones 1a y 5g, regla «Alertas»; D-71 punto 3; D-76 punto 7), **después** de todos los sistemas y **fuera de toda
transacción**:

- Cada `AlertaIot` cuya alerta es crítica y activa, con `correo_enviado_en` nulo e `intentos_correo < 5`, en orden de id.
- Se manda con `core.correo.enviar_correo(cuenta, asunto, "iot/correo/alerta_critica.txt", contexto)` a cada destinatario vigente de la
  alerta.
- Después, en una transacción corta por alerta: si salió a alguno, `correo_enviado_en = ahora`; si no, `intentos_correo += 1`. Al quinto
  fallo, `logger.error` con el id de la alerta.
- Sin servidor de correo (`core.correo.correo_configurado()` falso), no se intenta nada y la salida lo dice.
- Una alerta que se resolvió antes de mandarse ya no se manda (solo las activas).

**Auditoría (postcondición z).** Acción nueva `revision_periodica_iot`, actor `None`, **un registro por sistema y por corrida**, solo si
generó o resolvió alertas o borró lecturas:

- `datos`: `{"origen": "revision_periodica", "sistema": referencia(sistema), "ahora": <ISO>, "alertas_generadas": [...], "alertas_resueltas": [...],
  "lecturas_borradas": <n>}`;
- afectados: las alertas.

Los resúmenes, los fotoperíodos y los correos no se auditan uno por uno. La acción la agrega una migración de `core`, solo de `choices`:
`00NN_iot_revision_periodica_accion`.

**Qué cambia en IOT-03 por esto:** solo `AlertaIot.ultimo_mensaje_en` (paso 2 de «Una lectura» y de «Un estado»: se escribe en cada rechazo
por identificador desconocido). El resto ya lo deja IOT-03 listo: las alertas críticas nacen con `correo_enviado_en` nulo.

## Pantallas

IOT-03 no tiene pantallas propias: el nodo no tiene interfaz. Completa la lista y la ficha de Hardware (arriba). El panel de monitoreo es
IOT-04 (`consultar_lecturas.md`, lote I2b).

| Pantalla | Función en el prototipo | Qué agrega IOT-03 | Tarea |
|---|---|---|---|
| IoT · Hardware (lista y ficha) | `hardware`, `sensorState`, `actState`, `estInf` | Última lectura, situación por alertas, estado informado, modo y conectividad | IOT-03 |
| Monitoreo | `monitoreo`, `sensCard` | — | IOT-04 |

**Lo que difiere del prototipo (manda el CU, L7):** las cajas «SOLO PROTOTIPO · simula lo que informa el nodo» y sus botones (`sim-modo`,
`sim-ok`…) no existen: lo informa el nodo por la API.

## Para más adelante

- **IOT-04 (lote I2b):** la extensión \*b con `revision_iot` (sección «La revisión periódica», arriba), el correo de las alertas críticas,
  el panel de monitoreo (`consultar_lecturas.md`), la sección «Módulo IoT» de la configuración (`maestros/configuracion.md`) y los
  enlaces de las alertas del IoT (D-62).
- **IOT-05 (lote I3):** `explica_un_comando`; en modo local no se entregan comandos; el contrato de comandos (retiro y resultado):
  `resolver_comando.md`.
- **IOT-06 (lote I3):** el paso 6 y 6a a 6d en `evaluar_reglas_de_la_lectura`; `al_volver_a_remoto`; el reinicio de las reglas de 5c
  (sección «Reglas de actuación», arriba).
- En `docs/disparadores.md`, «Cuando existan actuadores, comandos y reglas del IoT», punto 5 (nuevo, lote I2a).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`, «Solo prototipo». En particular, para este caso de uso: los recuadros «SOLO PROTOTIPO · simula lo
que informa el nodo» y sus botones (`case 'sim-modo'`, `'sim-ok'`, `'sim-rech'`, `'sim-fail'`), los anuncios fijos `SOP` y la actualización
cada 20 s con valores al azar. En el sistema, todo eso lo manda el nodo (Node-RED en las pruebas a mano, `docs/api/nodo/node-red/`).
