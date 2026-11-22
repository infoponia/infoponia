# Casos de uso · iot · Resolver comando

Copia para el repo del caso IOT-RSV-CMD (v0.2) de «CU extendidos» (sección IoT, copiado el 22/11/2026). Cotejado con `docs/modelo/iot.md`
(MD-98 a MD-113) y con D-70 a D-78. **Ya trae las correcciones de D-71** (el correo de la alerta «comando fallido» lo manda la revisión
periódica: postcondición j, extensión 4b.3 y regla «Alerta «comando fallido»»), marcadas «corregido el 22/11/2026, D-71»: hay que pasarlas a
«CU extendidos».

**El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Para nombrar las pruebas:
`test_post_<letra>_<que_espera>`, `test_ext_<extension>_<que_espera>` y `test_regla_<nombre>_<que_espera>`.

## Índice

| Código | Partes | Actor | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-RSV-CMD | Todo, salvo la orden de mantenimiento | Sistema IoT (nodo central) | **IOT-05** | `iot/tests/test_iot_rsv_cmd.py`, `test_api_comandos.py`, `test_api_ejemplos.py` (los de comandos), `test_comandos_concurrencia.py` |
| IOT-RSV-CMD | Postcondiciones k y l, extensiones 4b.4, 4b.4a y 4b.4b (la orden de mantenimiento) | Sistema IoT | **IOT-07** (lote I4; D-73, D-79): cómo se aplica, en `mantenimiento_automatico.md` | `iot/tests/test_iot_rsv_cmd_mantenimiento.py` |

## IOT-RSV-CMD · Resolver Comando

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** IoT.

**Actor principal:** Sistema IoT (nodo central del invernadero).

**Versión:** 0.2

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere saber si cada comando se ejecutó, que los fallos pasajeros se reintenten solos, y que una falla persistente le llegue como alerta, también por correo, con el equipo marcado fuera de servicio.
  - **Técnico:** quiere recibir una orden de mantenimiento solo cuando un actuador falló de verdad, y no cuando el nodo no se comunica o no reconoce el comando, con la información de los intentos para empezar a diagnosticar.
  - **Gerente:** quiere que ninguna falla quede sin responsable y que la historia de cada comando quede registrada.
  - **Organización (Jardín Botánico):** quiere que la infraestructura IoT esté disponible y que una falla no deje sin protección a los cultivos (nota de presentación, «Planteo del problema»).

**Relaciones con otros casos de uso:** no incluye («include») otros casos de uso ni es extendido («extend») por ellos. Resuelve los comandos que emiten IOT-EMT-CMD (manuales) e IOT-ENT-INF (automáticos). Un comando pendiente se puede cancelar con IOT-CNL-CMD. La orden de mantenimiento que crea se planifica y se concreta con Planificar y Concretar Mantenimiento técnico.

**Precondiciones:**

a. El nodo central se identifica con el token vigente de un sistema IoT en estado «activo».

b. Existe al menos un comando pendiente de un actuador de ese sistema.

**Garantías mínimas:**

  - Cada mensaje del nodo se procesa en forma atómica: el resultado de un comando, su registro de bitácora, el cambio de estado del actuador, la alerta, la orden de mantenimiento y los logs se registran juntos o no se registra ninguno.
  - Un comando se resuelve una sola vez: un resultado tardío o repetido no lo cambia.
  - El nodo solo retira y resuelve comandos de los actuadores de su propio sistema IoT.
  - Un comando no consume intentos mientras el nodo no lo retira.
  - Un intento que el nodo puede estar ejecutando no se da por vencido antes de que pase el intervalo de reintento.
  - Un comando que el nodo no reconoce no deja al actuador fuera de servicio ni genera una orden de mantenimiento.

**Garantías de éxito (Postcondiciones):**

**En cada retiro de comandos:** a. Se registró la fecha y la hora de la comunicación del nodo central, que queda «en línea». b. A cada comando entregado se le sumó un intento y se le registró la fecha y la hora del último intento.

**Si el comando se ejecutó:** c. El comando pasó a «ejecutado», con el resultado que informó el nodo y la fecha y la hora de recepción. Si el nodo informó el estado en que quedó el actuador, ese pasó a ser su estado informado, con la fecha y la hora. d. Se creó un registro de bitácora del invernadero de tipo «comando», sin lote, con el actuador, la acción, el valor y el resultado. e. Si el actuador tenía activa la alerta «dispositivo sin actividad», pasó a «resuelta». El actuador deja de estar «sin confirmar».

**Por cada intento fallido o sin respuesta con intentos restantes:** f. El comando siguió «pendiente» y se volverá a entregar cuando pase el intervalo de reintento. g. Se creó un registro de bitácora de tipo «comando» con el número de intento y su resultado (la falla informada o «sin respuesta»).

**Si se agotaron los intentos (escalamiento):** h. El comando pasó a «fallido», con el último resultado y la fecha y la hora de recepción. i. El actuador pasó a «fuera de servicio». j. Se generó una alerta activa «comando fallido», con origen en el actuador, para el Agrónomo del invernadero o, si no tiene un Agrónomo activo, para el Gerente; la revisión periódica se lo notifica por correo dentro de los 5 minutos siguientes. *(corregido el 22/11/2026, D-71: antes decía «y se le notificó por correo»)* k. Si el invernadero tiene un Técnico asignado y el actuador no tenía una orden de mantenimiento a realizar, se creó una orden de mantenimiento técnico de tipo «revisión», en estado «a realizar», con prioridad alta, fecha programada igual a la fecha actual y una descripción con el comando, la acción, los intentos y el último resultado. Está asociada al actuador, al Técnico del invernadero y a la alerta, y no tiene Agrónomo. l. Se notificó al Técnico la orden de mantenimiento asignada. m. Se creó un registro de bitácora de tipo «comando» con el fallo definitivo.

**Si el nodo rechazó el comando por no reconocerlo:** n. El comando pasó a «fallido», sin reintentos, con el motivo del rechazo y la fecha y la hora de recepción. El actuador sigue «activo». o. La acción quedó marcada como incompatible para ese actuador, y si el actuador no la tenía, se generó la alerta «configuración incompatible», con origen en el actuador, para el Agrónomo del invernadero o, si no tiene un Agrónomo activo, para el Gerente. p. Se creó un registro de bitácora de tipo «comando» con el rechazo.

**En todos los casos:** q. Se creó un log de auditoría con origen «InfoPonia» (por el nodo central), fecha, hora y el identificador de cada comando, alerta, orden de mantenimiento y registro de bitácora creados o modificados, con los cambios de estado.

**Escenario principal de éxito (o Flujo Básico):**

(El nodo ejecuta el comando en el primer intento.)

1.  El nodo central solicita sus comandos pendientes, identificándose con su token.
2.  El Sistema verifica el token y registra la comunicación del nodo. Entrega de inmediato los comandos pendientes de sus actuadores que están disponibles, cada uno con su identificador, el identificador del actuador, el comando del catálogo de capacidades y el valor. A cada uno le suma un intento y le registra la fecha y la hora del último intento.
3.  El nodo central ejecuta el comando sobre el actuador.
4.  El nodo central informa el resultado del comando: su identificador, que se ejecutó, una descripción y, si lo conoce, el estado en que quedó el actuador.
5.  El Sistema verifica que el comando pertenece a un actuador del nodo y que sigue pendiente, y registra el resultado: pasa el comando a «ejecutado», con el resultado y la fecha y la hora de recepción; actualiza el estado informado del actuador, si vino; crea el registro de bitácora; resuelve la alerta «dispositivo sin actividad» del actuador, si la tenía, y registra la auditoría correspondiente.
6.  El Sistema confirma al nodo la recepción del resultado. *El nodo repite los pasos 3 a 6 por cada comando entregado.*

**Extensiones (o Flujos Alternativos):**

**\*a. El token no es válido o el sistema IoT no está activo:**

1.  El Sistema rechaza el mensaje sin registrar ningún cambio. Si el sistema está desconectado, responde que está desconectado.
2.  El caso de uso termina.

**2a. Algún comando del nodo esperaba la respuesta de un intento y ya pasó el intervalo de reintento:**

1.  El Sistema toma ese intento como «sin respuesta» y lo trata como un intento fallido (extensión 4a o 4b, según le queden intentos).
2.  El caso de uso continúa en el paso 2.

**2a.1a. El intervalo de ese intento venció mientras el nodo estaba «sin señal» (desde el último intento, el nodo pasó más que los minutos sin comunicación de la Configuración Operativa sin comunicarse):**

1.  El Sistema no cuenta el intento como fallido: le descuenta el intento y el comando vuelve a quedar disponible, porque la falta de respuesta se debe a la comunicación del nodo y no al actuador.
2.  El caso de uso continúa en el paso 2.

**2b. No hay comandos disponibles:**

1.  El Sistema responde de inmediato que no hay comandos, sin esperar a que aparezca alguno.
2.  El caso de uso termina.

**2c. Un comando pendiente es de un actuador que ya no está activo:**

1.  El Sistema no lo entrega y lo pasa a «cancelado», con su registro de bitácora.
2.  El caso de uso continúa en el paso 2 con los demás comandos.

**2d. El nodo informa el modo «local»:**

1.  El Sistema registra la comunicación del nodo y no le entrega comandos. Los comandos pendientes no consumen intentos.
2.  El caso de uso termina.

**4a. El nodo informa que el comando falló, y le quedan intentos:**

1.  El Sistema deja el comando «pendiente» y registra el intento fallido en la bitácora, con su número y el motivo informado.
2.  El comando se vuelve a entregar cuando pasa el intervalo de reintento desde el último intento.
3.  El caso de uso continúa en el paso 6.

**4b. El nodo informa que el comando falló, y era el último intento (escalamiento):**

1.  El Sistema pasa el comando a «fallido», con el motivo y la fecha y la hora de recepción.
2.  Pasa el actuador a «fuera de servicio».
3.  Genera la alerta «comando fallido» para el Agrónomo del invernadero o, si no tiene un Agrónomo activo, para el Gerente; la revisión periódica se la notifica por correo dentro de los 5 minutos siguientes. *(corregido el 22/11/2026, D-71: antes decía «y se la notifica por correo»)*
4.  Crea la orden de mantenimiento de tipo «revisión» para el Técnico del invernadero, asociada a la alerta, y le notifica la orden.
5.  Registra el fallo definitivo en la bitácora.
6.  El caso de uso continúa en el paso 6.

**4b.4a. El invernadero no tiene ningún Técnico asignado:**

1.  El Sistema no crea la orden de mantenimiento. La alerta indica que el invernadero no tiene Técnico y que la orden deberá planificarse cuando se asigne uno.
2.  El caso de uso continúa en 4b.5.

**4b.4b. El actuador ya tiene una orden de mantenimiento a realizar:**

1.  El Sistema no crea otra orden. La alerta menciona la orden existente.
2.  El caso de uso continúa en 4b.5.

**4c. El resultado llega después de que venció el intervalo de reintento, pero el comando sigue pendiente:**

1.  El Sistema acepta el resultado como respuesta del último intento.
2.  El caso de uso continúa en el paso 5, o en 4a, 4b o 4f según lo que informe el nodo.

**4d. El comando ya está resuelto (ejecutado, fallido o cancelado), o el resultado es repetido:**

1.  El Sistema no registra ningún cambio, responde que el comando ya estaba resuelto y deja constancia en el registro técnico de errores.
2.  El caso de uso continúa en el paso 6.

**4e. El comando no existe o no pertenece a un actuador del nodo:**

1.  El Sistema rechaza el resultado sin registrar ningún cambio y deja constancia en el registro técnico de errores.
2.  El caso de uso termina.

**4f. El nodo informa que rechazó el comando porque no lo reconoce para ese actuador:**

1.  El Sistema pasa el comando a «fallido», sin reintentos, con el motivo del rechazo y la fecha y la hora de recepción. El actuador sigue «activo».
2.  Marca la acción como incompatible para ese actuador y, si no la tenía, genera la alerta «configuración incompatible» para el Agrónomo del invernadero o, si no tiene un Agrónomo activo, para el Gerente.
3.  Registra el rechazo en la bitácora.
4.  El caso de uso continúa en el paso 6.

**Requisitos especiales:**

  - Cada mensaje del nodo se procesa como una única transacción.
  - El control de concurrencia asegura que un comando se entregue a un solo retiro por intento y se resuelva una sola vez, aun cuando el nodo y un usuario (IOT-CNL-CMD) actúen al mismo tiempo.
  - El retiro de comandos responde de inmediato, sin esperas. El nodo consulta cada pocos segundos; la guía de integración recomienda cada 5 segundos.
  - El token solo autoriza la comunicación de ese nodo con la API: no da acceso a pantallas ni a datos de otros invernaderos.
  - Toda comunicación se hace por HTTPS (SEG-16).
  - La lógica de este caso de uso no depende de la forma de comunicación: la API solo traduce el mensaje del nodo y llama a los servicios del dominio, de modo que otra forma de comunicación, como MQTT, no cambie las reglas.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un proceso automático del Sistema, con el nodo central que lo originó.

**Lista de tecnología y variaciones de datos:**

  - 1a. El nodo se identifica con su token en cada mensaje. Los mensajes van en formato JSON.
  - 2a. El actuador se identifica por su identificador del equipo (regla 2 de IOT-ALT-HDW), y el comando, por su identificador. La acción viaja como un comando del catálogo de capacidades (regla 7 de IOT-ALT-TAC), por ejemplo ENCENDER o FIJAR_POSICION, con su valor si lo lleva.
  - 4a. El resultado es «ejecutado», «falló» o «rechazado», con una descripción de texto libre y, si el nodo lo conoce, el estado en que quedó el actuador.

**Frecuencia:** El retiro de comandos ocurre cada pocos segundos por cada nodo central; los resultados, uno por cada intento de cada comando.

**Reglas de negocio:**

  - **Intentos:** un comando se intenta como máximo 1 + la cantidad de reintentos de la Configuración Operativa (valor inicial 3, es decir, 4 intentos). Cada retiro del nodo cuenta como un intento. (Pasos 2, extensiones 4a y 4b)
  - **Intervalo de reintento:** un solo parámetro de la Configuración Operativa (valor inicial 60 segundos) sirve para dos cosas: es el tiempo máximo de espera de la respuesta de un intento, y es el tiempo mínimo entre un intento y el siguiente. (Extensiones 2a y 4a)
  - **Comando disponible:** un comando pendiente se entrega si nunca se retiró, o si pasó el intervalo de reintento desde su último intento. Mientras el nodo no lo retira, no consume intentos. No se entregan comandos a un nodo que informa el modo «local». (Paso 2, extensión 2d)
  - **Intento fallido:** el nodo informa que falló, o no responde dentro del intervalo de reintento («sin respuesta»). Los dos se tratan igual. (Extensiones 2a, 4a y 4b)
  - **Revisión de vencimientos:** los intentos vencidos sin respuesta se detectan en cada retiro del nodo (extensión 2a); abrir el panel no los revisa. Mientras el nodo no se comunica, ningún intento se da por vencido ni se escala, y un intento que venció mientras el nodo estaba «sin señal» no cuenta como fallido: la falta de comunicación la cubre la alerta «nodo sin comunicación» de la revisión periódica (IOT-ENT-INF). Así, una caída del nodo no deja actuadores fuera de servicio ni genera órdenes de mantenimiento. (Extensiones 2a y 2a.1a)
  - **Respuesta tardía o repetida:** si el comando sigue pendiente, una respuesta tardía se acepta; si ya está resuelto, se ignora. (Extensiones 4c y 4d)
  - **Comando repetido en el nodo:** como un comando sin respuesta se vuelve a entregar, el nodo puede recibir un comando que ya ejecutó. La guía de integración del nodo obliga a que el nodo recuerde los identificadores de los comandos ejecutados y, si recibe uno repetido, responda el resultado anterior sin volver a ejecutarlo. Junto con la extensión 4d, evita que una acción se ejecute dos veces. (Paso 3)
  - **Escalamiento:** al agotarse los intentos, el comando pasa a «fallido», el actuador a «fuera de servicio» y se generan la alerta y la orden de mantenimiento (nota de presentación, proceso «Reintento y Escalamiento de Comandos Fallidos»). Un actuador fuera de servicio no recibe comandos y sus reglas de actuación no se evalúan hasta que vuelva a «activo» (IOT-MOD-HDW). (Extensión 4b)
  - **Rechazo:** si el nodo no reconoce el comando para ese actuador, el problema es de configuración y no del equipo: el comando falla sin reintentos, el actuador sigue activo, no se crea orden de mantenimiento y se genera la alerta «configuración incompatible». La acción queda marcada como incompatible para ese actuador y deja de ofrecerse en comandos y reglas (regla 14 de IOT-ALT-HDW) hasta que se corrija la configuración: el Agrónomo cambia el tipo del actuador (IOT-MOD-HDW, solo si todavía no tiene comandos ni reglas; si no, lo da de baja y registra uno nuevo), el Gerente corrige las acciones del tipo (IOT-MOD-TAC) o el nodo anuncia la capacidad. La alerta se resuelve sola cuando no queda ninguna acción incompatible en el actuador; si el equipo nunca va a soportar la acción, no se resuelve con el tiempo y queda abierta hasta que se corrija. (Extensión 4f)
  - **Orden de mantenimiento automática:**

      - es de tipo «revisión», porque la causa de la falla no se conoce: puede ser el actuador, el cableado o el nodo;
      - tiene prioridad alta, fecha programada igual a la fecha actual y no tiene Agrónomo (R046 en 0..1);
      - se asigna al Técnico del invernadero (R134), aunque esté inactivo, porque se reasigna al asignar otro (regla 3 de 8.22). El modelo tiene un único Técnico por invernadero, así que no hay que elegir un «técnico disponible»;
      - en la etapa 1 no reserva repuestos. Cuando exista Planificar Mantenimiento técnico, la orden automática sigue sus reglas;
      - si el invernadero no tiene ningún Técnico asignado, o si el actuador ya tiene una orden a realizar, no se crea. (Extensiones 4b, 4b.4a y 4b.4b)
  - **Alerta «comando fallido»:** con origen en el actuador (R052), asociada a la orden de mantenimiento si se creó (R048). La recibe el Agrónomo del invernadero o, si no tiene un Agrónomo activo, el Gerente. Es de severidad crítica y se notifica por correo una sola vez, dentro de los 5 minutos siguientes, por la revisión periódica. *(corregido el 22/11/2026, D-71: antes decía «al generarse»)* No se resuelve a mano: se resuelve cuando el actuador vuelve a «activo». (Extensión 4b)
  - **Ejecución:** un comando ejecutado confirma que el actuador funciona: el actuador deja de estar «sin confirmar» y se resuelve su alerta «dispositivo sin actividad». Si la acción no cambió nada en el equipo, porque ya estaba en ese estado, el nodo la informa igual como ejecutada. Si el nodo informa el estado en que quedó el actuador, ese pasa a ser su estado informado (IOT-ENT-INF). (Paso 5)
  - **Bitácora:** se registra cada intento fallido o sin respuesta, con su número, y el resultado final (ejecutado, fallido, rechazado o cancelado). El retiro del comando no se registra. (Paso 5, extensiones 2c, 4a, 4b y 4f)
  - **Conectividad:** cada comunicación del nodo actualiza la fecha y la hora de su última comunicación, con la que se calcula si está «en línea» o «sin señal». (Paso 2, extensión 2d)
  - **Sistema desconectado:** al desactivar el sistema IoT, sus comandos pendientes pasan a «cancelado» (IOT-DSC-SIS), y el nodo no puede retirar ni resolver comandos. (Extensión \*a)

**Temas abiertos:**

  - **Cambios de modelo pendientes de registrar en pendientes_MD:**

      - MantenimientoTecnico.tipoMantenimiento pasa a lista de valores: revisión / reparación / calibración / reemplazo / mantenimiento general. Una orden de calibración solo incluye sensores, y una de reemplazo reserva una unidad del insumo del equipo (R072). El detalle se especifica en Planificar Mantenimiento técnico;
      - Alerta.nivelSeveridad toma los valores crítica, advertencia e informativa, que fija el tipo de alerta (se conserva el atributo que ya existe en el modelo). La severidad indica la importancia de la alerta; la urgencia de lo que hay que hacer la expresa la prioridad de la orden de trabajo, que es otro concepto;
      - Alerta.tipoAlerta suma «configuración incompatible»;
      - marca de acción incompatible por actuador (asociación entre Actuador y Accion);
      - parámetros de la Configuración Operativa: cantidad de reintentos e intervalo de reintento.
  - **Diferencia con la nota de presentación:** el proceso «Reintento y Escalamiento de Comandos Fallidos» asigna la orden «a un técnico disponible» y audita «el cambio de estado del actuador y del técnico», y el módulo de gestión de usuarios habla de consultar la disponibilidad de los empleados. Responde a un diseño anterior, con varios técnicos y un estado de disponibilidad. Desde la ronda 21, cada invernadero tiene un único Técnico (R134; MD-59 y MD-60) y su único estado es el de su cuenta (activo o inactivo), así que la orden va al Técnico del invernadero y ningún estado cambia. No se modifica el modelo; queda como diferencia documentada con la nota.

## Cómo se aplica en la ronda «IoT 1» (D-44, D-71, D-72, D-77, D-78)

Tarea: **IOT-05**. Contrato: `docs/api/nodo/mensajes.md`, secciones 5 y 6, y `respuestas_y_errores.md` (las reglas comunes de la API son
las de IOT-03: `docs/casos_de_uso/iot/entregar_informacion.md`, «La API»). Modelo: `docs/modelo/iot.md` («Comando», «RegistroComando»,
«Actuador», «AlertaIot», «Parámetros IoT»).

### Rutas (en `iot/api/`, con lo que dejó IOT-03)

- `comandos` (solo `GET`; con otro método, 405 con `Allow: GET`) y `comandos/<int:id>/resultado` (solo `POST`). Mismo orden de verificación,
  token, contador de pedidos, `login_not_required`, `csrf_exempt`, `never_cache` y registro técnico de errores que el resto de la API. El
  retiro salta las verificaciones del cuerpo (7 a 11).
- **Una transacción por mensaje** («Requisitos especiales»), con los bloqueos de D-78, punto 11.

### El retiro (pasos 1 y 2, extensiones 2a a 2d) — `retirar_comandos(sistema_id, ahora) -> Retiro`

En este orden, en una sola transacción:

1. Se bloquean invernadero, sistema y nodo, y se lee la **comunicación anterior** del nodo. Después se registra la comunicación
   (postcondición a; resuelve «nodo sin comunicación», como en IOT-03).
2. Si el nodo está en modo `local` (2d), la respuesta es la lista vacía. No se toca ningún comando.
3. Se bloquean los actuadores del sistema y sus comandos pendientes, en orden de id.
4. **2c.** El comando pendiente de un actuador que no está `activo` pasa a `cancelado` (`resuelto_en = ahora`), con su `RegistroComando`
   `cancelado` («Actuador fuera de servicio» o «dado de baja»). No se entrega.
5. **2a y 2a.1a** (D-78, puntos 1 y 2). Cada intento vencido:
   - si el nodo estuvo «sin señal», se descuenta;
   - si no, es un intento fallido «sin respuesta». Si le quedan intentos, deja un `RegistroComando` `intento_fallido`. Si era el último,
     escala igual que 4b, con `resultado_comando = sin_respuesta`.
6. **Disponibles** (regla «Comando disponible»): los pendientes con `cantidad_intentos = 0`, o con el último intento vencido y que todavía
   tienen intentos. A cada uno: `cantidad_intentos + 1` y `ultimo_intento_en = ahora` (postcondición b). No se registra en la bitácora
   (regla «Bitácora»).
7. Respuesta: `modo` y `comandos` (`id`, `identificador`, `comando` del catálogo, `valor`, `intento`, `espera_segundos` =
   `segundos_intervalo_reintento`).

### El resultado (pasos 4 a 6, extensiones 4a a 4f) — `registrar_resultado(sistema_id, comando_id, resultado, ahora)`

1. **4e.** El comando no existe o su actuador no es del sistema: 404 `comando_inexistente`, sin cambios, al registro técnico de errores.
2. Se bloquean invernadero → sistema → nodo → actuador → comando. Se registra la comunicación.
3. **4d.** Si no está `pendiente`: 200 `ya_resuelto` con su estado, sin cambios, al registro técnico de errores (D-77, punto 2). Un resultado
   para un comando pendiente que **nunca se entregó** (`cantidad_intentos = 0`) se trata como 4e: 404 `comando_inexistente`, porque el nodo
   no pudo haberlo recibido (D-78, punto 12).
4. **4c.** Si llega después de que venció su espera, pero sigue pendiente, se acepta como respuesta del último intento.
5. Según `resultado`:
   - **`ejecutado`** (paso 5, postcondiciones c a e): `estado_comando = ejecutado`, `resultado_comando = ejecutado`, `detalle_resultado`,
     `resuelto_en = ahora`. Si trae `estado`, pasa a ser el estado informado, con `informado_en` y `cambiado_en_invernadero` falso (D-78,
     punto 4). `ultimo_mensaje_en = ahora`. Se resuelve «dispositivo sin actividad» y se crea el `RegistroComando` `ejecutado`.
   - **`fallo` con intentos restantes** (4a): sigue `pendiente`, con `resultado_comando = fallo` y su detalle, y un `RegistroComando`
     `intento_fallido` con el número de intento. **No vuelve a entregarse antes de que pase la espera** desde el último intento.
   - **`fallo` en el último intento** (4b, salvo 4b.4): `fallido`, `resultado_comando = fallo`, `resuelto_en`. El actuador pasa a
     `fuera_de_servicio`. Se asegura la alerta `iot_comando_fallido` (D-78, punto 10) y se crea el `RegistroComando` `fallido`. **La orden
     de mantenimiento la suma IOT-07**: hasta entonces no se crea, y la alerta no menciona ninguna orden. IOT-07 llama a
     `crear_orden_automatica` desde este mismo escalamiento y le agrega a la alerta un sufijo (`mantenimiento_automatico.md`, «La orden al
     escalar»; D-79, punto 3).
   - **`rechazado`** (4f): `fallido`, `resultado_comando = rechazado`, sin reintentos. El actuador sigue activo. La acción se suma a
     `acciones_incompatibles`, el actuador queda `incompatible` y se asegura «configuración incompatible» (D-78, punto 5). Se crea el
     `RegistroComando` `rechazado`.
6. Auditoría (postcondición q): acción `resolucion_comando_iot`, actor `None`, origen «nodo_central», con los cambios del comando, del
   actuador, de la alerta y del registro de bitácora. El retiro audita **solo** si canceló (2c) o escaló algo (2a); la entrega sola no se
   audita.

### Lo que esto completa

- `explica_un_comando(actuador, estado)` de IOT-03 (D-78, punto 4).
- `ultimo_mensaje_en` del actuador: también lo carga un resultado (IOT-CNS-HDW, regla 4).

### Concurrencia (`@tag("concurrencia")`)

- Dos retiros a la vez entregan cada comando una sola vez.
- Un retiro y una cancelación a la vez: una de las dos gana; la cancelación se niega con el mensaje de la regla 5 de IOT-CNL-CMD.
- Dos resultados iguales a la vez: uno `aceptado`, el otro `ya_resuelto`.

## Pantallas

No tiene pantallas propias: lo que resuelve se ve en «Comandos» (`emitir_comando.md`), en el panel y en la ficha del actuador. La alerta
«comando fallido» lleva a la ficha del actuador (enlace de IOT-04).

## Para más adelante

- **IOT-07 (lote I4):** la orden de mantenimiento de 4b.4, 4b.4a y 4b.4b, y su aviso al Técnico. Escrito en
  `docs/casos_de_uso/iot/mantenimiento_automatico.md` y `docs/tareas/iot/IOT-07-orden-de-mantenimiento.md`.

## Solo prototipo

`failCmd` y los botones `sim-ok`, `sim-fail` y `sim-rech` del prototipo: en el sistema, lo informa el nodo por la API (Node-RED,
`docs/api/nodo/node-red/flujo_comandos.json`).
