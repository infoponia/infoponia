# Casos de uso · iot · Emitir comando

Copia para el repo del caso IOT-EMT-CMD (v0.2) de «CU extendidos» (sección IoT, copiado el 22/11/2026). Junto con los demás casos IOT-*
reemplaza a los preliminares de la «Documentación para la IA» que lista `docs/tareas/ronda_iot_1.md`, sección 3. Cotejado con
`docs/modelo/iot.md` (MD-98 a MD-113) y con D-70 a D-78.

**El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no elijas en silencio. Para nombrar las pruebas:
`test_post_<letra>_<que_espera>`, `test_ext_<extension>_<que_espera>` y `test_regla_<nombre>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-EMT-CMD | Emitir comando | Agrónomo o Gerente (alcance) | IOT-05 (las reglas activas del actuador en el paso 4 y 6b, IOT-06) | `iot/tests/test_iot_emt_cmd.py` |

## IOT-EMT-CMD · Emitir Comando

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** IoT.

**Actor principal:** Agrónomo (o Gerente, según su alcance; ver regla «Alcance»).

**Versión:** 0.2

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere actuar a distancia sobre un equipo del invernadero (por ejemplo, encender un ventilador) en pocos pasos, saber si la orden llegó y se ejecutó, y no mandar órdenes que se contradigan ni que dañen el equipo.
  - **Gerente:** quiere saber quién ordenó cada acción y poder actuar en un invernadero que no tiene un Agrónomo activo.
  - **Técnico:** quiere que le lleguen como mantenimiento las fallas reales de los actuadores, y no las que causa un nodo sin comunicación o una configuración incompatible.
  - **Organización (Jardín Botánico):** quiere proteger los cultivos ante condiciones de riesgo y conservar la historia de lo que se hizo en cada invernadero.

**Relaciones con otros casos de uso:** no incluye («include») otros casos de uso ni es extendido («extend») por ellos. Se inicia desde IOT-CNS-LEC o desde la ficha de un actuador (IOT-CNS-HDW). Lo sigue IOT-RSV-CMD, cuando el nodo central informa el resultado. Un comando pendiente se cancela con IOT-CNL-CMD. La emisión automática de un comando por una regla de actuación se especifica en IOT-ENT-INF y cumple la regla «Comando válido» de este caso de uso.

**Precondiciones:**

a. El actor está autenticado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. Existe al menos un invernadero, dentro del alcance del actor, con un sistema IoT en estado «activo» y al menos un actuador en estado «activo».

**Garantías mínimas:**

  - El registro es atómico. Si el caso de uso se cancela o falla, no queda registrado ningún comando, registro de bitácora ni log de auditoría parcial, y el nodo no recibe nada.
  - Ningún actuador queda con más de un comando pendiente, aun cuando dos actores, o un actor y una regla de actuación, emitan al mismo tiempo.
  - Emitir un comando no cambia el estado del actuador, del sistema IoT ni de las reglas de actuación.

**Garantías de éxito (Postcondiciones):**

a. Se creó un comando en estado «pendiente», con la fecha y la hora de emisión, el valor (si la acción lo requiere), la descripción (si se indicó) y la cantidad de intentos en cero, sin fecha de recepción ni resultado. Está asociado al actuador y a la acción elegidos, al Agrónomo si lo emitió un Agrónomo, y a ninguna regla de actuación.

b. Se creó un registro de bitácora del invernadero de tipo «comando», sin lote, con el actuador, la acción, el valor y el estado del comando, asociado al Agrónomo si lo emitió un Agrónomo.

c. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del comando y del registro de bitácora creados.

**Escenario principal de éxito (o Flujo Básico):**

1.  El Agrónomo inicia la emisión de un comando en un invernadero a su cargo.
2.  El Sistema presenta la conectividad y el modo del nodo central y los actuadores activos del sistema IoT. De cada actuador indica su tipo, su sector o la marca «general», su estado actual tal como lo informó el nodo, con su fecha y hora (o «desconocido»), la marca «sin confirmar» si corresponde, su compatibilidad con el nodo y si tiene un comando pendiente.
3.  El Agrónomo selecciona un actuador.
4.  El Sistema presenta las acciones activas del tipo del actuador que son compatibles con el nodo, cada una con si requiere un valor y, si lo requiere, su unidad, su mínimo y su máximo, y presenta las reglas de actuación activas del actuador.
5.  El Agrónomo selecciona una acción, ingresa el valor si la acción lo requiere y, si quiere, una descripción.
6.  El Sistema verifica los datos y presenta un resumen: el actuador, la acción, el valor y la descripción.
7.  El Agrónomo confirma el comando.
8.  El Sistema registra el comando en estado «pendiente» y su registro de bitácora.
9.  El Sistema informa que el comando quedó pendiente hasta que el nodo central lo retire en su próxima consulta y lo ejecute, y que el resultado se verá en el panel de monitoreo y en la ficha del actuador.

**Extensiones (o Flujos Alternativos):**

**\*a. En cualquier momento antes del paso 7, el actor cancela:**

1.  El Sistema no registra ningún cambio.
2.  El caso de uso termina.

**1a. El actor es el Gerente:**

1.  El Sistema le permite emitir comandos solo en los invernaderos sin un Agrónomo activo.
2.  El caso de uso continúa en el paso 2.

**1b. El actor inicia el caso de uso desde la ficha de un actuador:**

1.  El invernadero y el actuador ya están elegidos.
2.  El caso de uso continúa en el paso 4.

**3a. El actuador elegido tiene un comando pendiente:**

1.  El Sistema informa el comando pendiente: su acción, quién o qué regla lo emitió y desde cuándo está pendiente. No permite emitir otro. Si el comando se puede cancelar (regla 2 de IOT-CNL-CMD), ofrece cancelarlo.
2.  El actor elige otro actuador (vuelve al paso 3), cancela el comando pendiente con IOT-CNL-CMD y vuelve al paso 3, o cancela.

**4a. Alguna acción del tipo es incompatible con las capacidades que anunció el nodo:**

1.  El Sistema no la ofrece e indica que el actuador tiene la alerta «configuración incompatible» (regla 14 de IOT-ALT-HDW).
2.  Si no queda ninguna acción compatible, el actor elige otro actuador (vuelve al paso 3) o cancela.

**6a. Falta el valor, no es un número entero o está fuera del rango de la acción:**

1.  El Sistema señala el error e informa el rango.
2.  El caso de uso vuelve al paso 5.

**6b. El actuador tiene reglas de actuación activas:**

1.  En el resumen, el Sistema advierte que el comando puede contradecir esas reglas, y que una regla solo vuelve a actuar cuando su condición pasa a cumplirse.
2.  El caso de uso continúa en el paso 7.

**6c. La acción deja al actuador en el estado en que ya está, según el estado informado por el nodo (por ejemplo, encender un ventilador encendido):**

1.  En el resumen, el Sistema advierte que, según el último estado que informó el nodo, el actuador ya está en ese estado.
2.  El caso de uso continúa en el paso 7.

**6d. El actuador está «sin confirmar»:**

1.  En el resumen, el Sistema advierte que del actuador nunca llegó ningún mensaje, y que, si su identificador está mal cargado, el comando no se va a ejecutar.
2.  El caso de uso continúa en el paso 7.

**6e. La conectividad del nodo central es «sin señal»:**

1.  En el resumen, el Sistema advierte que el comando quedará pendiente, sin consumir intentos, hasta que el nodo se comunique.
2.  El caso de uso continúa en el paso 7.

**6f. El último comando ejecutado sobre el actuador es más reciente que el tiempo mínimo entre comandos de su tipo:**

1.  En el resumen, el Sistema advierte hace cuánto cambió de estado el actuador, que cambiarlo tan seguido puede dañar el equipo y cuánto falta para que se cumpla el tiempo mínimo.
2.  El caso de uso continúa en el paso 7.

**6g. El nodo central informa el modo «local»:**

1.  En el resumen, el Sistema advierte que el nodo está operando en forma local y que el comando quedará pendiente, sin consumir intentos, hasta que el nodo vuelva al modo «remoto».
2.  El caso de uso continúa en el paso 7.

**7a. El actor quiere cambiar la acción, el valor o la descripción antes de confirmar:**

1.  El caso de uso vuelve al paso 5.

**7b. El actor quiere elegir otro actuador:**

1.  El caso de uso vuelve al paso 3.

**8a. Al registrar, el actuador ya tiene un comando pendiente (lo emitió otro actor o una regla de actuación):**

1.  El Sistema no registra ningún cambio e informa el comando pendiente.
2.  El caso de uso vuelve al paso 2.

**8b. Al registrar, el sistema IoT ya no está activo, el actuador ya no está activo, la acción ya no está activa o es incompatible, o el invernadero salió del alcance del actor:**

1.  El Sistema no registra ningún cambio e informa el motivo.
2.  El caso de uso vuelve al paso 2 o termina, si ya no queda ningún actuador que pueda recibir comandos.

**Requisitos especiales:**

  - La interfaz se adapta a computadora y a celular.
  - La pantalla responde a cada acción del actor en no más de 1 segundo, y el registro del paso 8 se completa en no más de 5 segundos.
  - El registro se ejecuta como una única transacción. El comando, su registro de bitácora y los logs se registran juntos o no se registra ninguno.
  - El control de concurrencia sobre el actuador impide que quede con dos comandos pendientes, también frente a la emisión automática de IOT-ENT-INF.
  - El comando queda disponible para el nodo central desde que se registra; el nodo lo retira en su próxima consulta, que hace cada pocos segundos (IOT-RSV-CMD).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Lista de tecnología y variaciones de datos:**

  - 5a. El valor es un número entero, en la unidad de la acción. La descripción es texto libre opcional.
  - 2a. El estado actual de cada actuador se muestra con la fecha y hora en que lo informó el nodo (por ejemplo, «encendido desde las 14:32»), y con la marca «cambiado en el invernadero» si el cambio no lo originó un comando de InfoPonia.

**Frecuencia:** Varias veces por día en cada invernadero con sistema IoT. A confirmar con el Jardín Botánico.

**Reglas de negocio:**

  - **Alcance:** el Agrónomo opera el IoT de los invernaderos activos a su cargo. El Gerente lo opera solo en los invernaderos sin un Agrónomo activo (sin asignar, o con el asignado inactivo), hasta que se asigne uno (decisión del 18/11/2026, que reemplaza en este punto a la regla 4 de 8.22). En los demás invernaderos, el Gerente solo consulta. (Pasos 1 y 8, extensiones 1a y 8b)
  - **Actuador elegible:** un actuador en estado «activo» de un sistema IoT en estado «activo». Un actuador fuera de servicio o dado de baja no recibe comandos. (Paso 2, extensión 8b)
  - **Un comando pendiente por actuador:** un actuador no puede tener más de un comando pendiente, lo haya emitido una persona o una regla de actuación. Un comando que quedó trabado, por ejemplo porque el nodo no se comunica, se cancela con IOT-CNL-CMD. (Extensiones 3a y 8a)
  - **Comando válido:** la acción es una de las acciones activas del tipo del actuador y, si el nodo anunció sus capacidades, compatible con ellas (regla 14 de IOT-ALT-HDW). Si la acción requiere un valor, que se deduce de su comando (regla 8 de IOT-ALT-TAC), el valor es obligatorio, es un número entero y está entre el mínimo y el máximo de la acción (regla 4 de IOT-ALT-TAC); si no lo requiere, el comando no lleva valor. Esta regla rige también para los comandos que emite InfoPonia por una regla de actuación. (Pasos 4 a 6, extensiones 4a, 6a y 8b)
  - **Descripción:** en un comando manual es opcional y la escribe el actor. En un comando automático la completa InfoPonia con la regla que lo disparó (IOT-ENT-INF). El resultado que informa el nodo no va en la descripción: se registra aparte (IOT-RSV-CMD). (Paso 5)
  - **Estado inicial e intentos:** el comando nace «pendiente», con cero intentos. La espera y los intentos se cuentan desde que el nodo central retira el comando; mientras no lo retira, el comando sigue pendiente sin consumir intentos. Mientras el nodo informa el modo «local», el Sistema no le entrega comandos (IOT-RSV-CMD). (Paso 8, extensiones 6e y 6g)
  - **Tiempo mínimo entre comandos:** cada tipo de actuador fija los segundos que deben pasar entre dos comandos ejecutados sobre un mismo actuador (regla 9 de IOT-ALT-TAC). En un comando manual, el Sistema advierte y deja continuar, porque decide la persona; en un comando automático, la regla de actuación no emite antes de ese tiempo (IOT-ENT-INF). Se recomienda además que el nodo respete esos tiempos en forma local (guía de integración del nodo). (Extensión 6f)
  - **Advertencias que no bloquean:** el Sistema advierte, y deja continuar, cuando el actuador tiene reglas de actuación activas, cuando la acción lo deja en el estado en que ya está, cuando el actuador está «sin confirmar», cuando el nodo está «sin señal», cuando no pasó el tiempo mínimo entre comandos y cuando el nodo está en modo «local». Una acción que repite el estado actual no tiene efecto en el equipo: el nodo la informa como ejecutada. (Extensiones 6b a 6g)
  - **Estado actual de un actuador:** es el que informa el nodo central, con la fecha y hora en que lo informó (IOT-ENT-INF); ya no se deduce del último comando. Si el nodo nunca informó el estado de un actuador, el estado es «desconocido» y la extensión 6c no se aplica. Un actuador del que nunca llegó ningún mensaje está «sin confirmar». (Paso 2, extensión 6c)
  - **Bitácora:** todo comando, manual o automático, deja un registro de bitácora del invernadero de tipo «comando», sin lote. Los reintentos y el resultado se registran en IOT-RSV-CMD. (Paso 8)
  - **Quién lo emitió:** un comando del Gerente no tiene Agrónomo (R050 en 0..1); la persona real queda en el log de auditoría (regla 4 de 8.22). (Paso 8)
  - **Desconexión del sistema:** si el sistema IoT se desactiva con el comando pendiente, el comando pasa a «cancelado» (IOT-DSC-SIS).

**Temas abiertos:**

  - **Cambios de modelo pendientes de registrar en pendientes_MD:**

      - asociación nueva Comando → Actuador (1), que reemplaza a R067 (Comando → SistemaIoT);
      - asociación nueva Comando → ReglaActuacion (0..1);
      - estado «cancelado» del comando;
      - atributos nuevos del comando: resultado, cantidad de intentos y fecha del último intento, con fechaRecepcionComando y horaRecepcionComando como el momento de la resolución;
      - mínimo y máximo de la Accion, enteros;
      - tipo de evento «comando» de la bitácora;
      - Actuador: estado informado y fecha y hora en que se informó;
      - TipoActuador: tiempo mínimo entre comandos;

Accion: comando del catálogo de capacidades y estado activa / inactiva.

## Cómo se aplica en la ronda «IoT 1» (D-44, D-72, D-78)

Tarea: **IOT-05**. Modelo: `docs/modelo/iot.md` («Comando», «RegistroComando», «Actuador», «Accion», «TipoActuador»). Alcance:
`docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco». El retiro y el resultado: `resolver_comando.md`.

- **Servicios** en `iot/servicios/comandos.py` (una función por paso con escritura, en `transaction.atomic()`):
  - `datos_para_emitir(actor, invernadero_id, actuador_id=None)` (pasos 2 y 4): el nodo (conectividad y modo); los actuadores activos del
    sistema activo, cada uno con su tipo, su sector o «General», su estado informado con la hora o «Desconocido», «Sin confirmar», su
    compatibilidad y su comando pendiente; del actuador elegido, sus **acciones activas compatibles** (las incompatibles, aparte, con el
    aviso de 4a) y sus reglas activas (**vacías hasta IOT-06**).
  - `validar_comando(actuador, accion, valor)`: la regla «Comando válido», **una sola función**, que también usan las reglas de actuación
    (IOT-06). Devuelve los errores por campo.
  - `resumen_de_comando(actor, actuador_id, datos, ahora)` (paso 6): valida sin escribir y devuelve las **advertencias** 6b a 6g, en ese
    orden, con los textos de la pantalla (abajo).
  - `emitir_comando(actor, actuador_id, datos, ahora) -> Comando` (paso 8): bloquea invernadero → sistema → actuador (D-78, punto 11), vuelve
    a verificar todo (8b, con el motivo) y crea el `Comando` pendiente (0 intentos; `agronomo` si lo emitió un Agrónomo, nulo si lo emitió
    el Gerente) y su `RegistroComando` `emitido` (D-78, punto 3). El índice único de pendiente por actuador respalda 8a: el
    `IntegrityError` se traduce al mismo mensaje, nunca un 500.
  - Auditoría (postcondición c, D-36): acción `emision_comando`, afectados el comando y el registro de bitácora.
- **`RegistroComando`** (hija de `produccion.Bitacora`, MD-110) **lo crea IOT-05** con su migración de `iot`. Hace falta sumar el valor
  `comando` a `Bitacora.TipoEvento`: migración de `produccion`, solo de `choices` (permitido fuera de la app).
- **Lo que completa de tareas anteriores** (disparador «Cuando existan actuadores, comandos y reglas del IoT»):
  - de IOT-01, `acciones_en_uso(tipo)` y `acciones_con_historial(tipo)` por comandos;
  - de IOT-02, `tiene_comandos(actuador)`, `tiene_comando_pendiente(actuador)`, «Comando pendiente» en la situación y el historial de comandos
    de la ficha;
  - de IOT-04, «Comandos pendientes» en el panel y «Emitir comando» en su fila.
- **Pantalla «Comandos»** (pestaña del módulo, `comandos/`, con `?invernadero=`; prototipo `comandos` y `cmdForm`). Arriba, el formulario
  de emisión, **solo para quien opera**: actuador, acción (solo las compatibles), valor (si la acción lo lleva, con «Número entero entre {mín}
  y {máx} {unidad}.»), descripción opcional (hasta 300), el resumen con sus advertencias y «Emitir comando». Debajo, la lista de comandos
  del invernadero, del más reciente al más viejo, de a 25, con filtros por estado, actuador y origen (manual o regla), y «Cancelar» en los
  pendientes (`cancelar_comando.md`). Las columnas son las del prototipo: código, actuador y acción, origen, estado, intentos, último intento.
  - **Advertencias** (textos del prototipo, con estos ajustes):
    - 6e: «El nodo está sin señal. El comando queda pendiente, sin consumir intentos, hasta que el nodo se comunique.»;
    - 6g: «El nodo está operando en modo local. El comando queda pendiente, sin consumir intentos, hasta que vuelva a «remoto».»;
    - 6d: «Del actuador nunca llegó ningún mensaje. Si su identificador está mal cargado, el comando no se va a ejecutar.»;
    - 6f: «El actuador cambió de estado hace {tiempo}. Cambiarlo tan seguido puede dañar el equipo: faltan {n} s para cumplir el tiempo
      mínimo entre comandos. Podés emitirlo igual.»;
    - 6c: «Según el último estado que informó el nodo, el actuador ya está {estado}. El nodo lo informará como ejecutado sin cambiar
      nada.»;
    - 6b: «El actuador tiene {n} regla(s) activa(s): este comando puede contradecirlas. Una regla solo vuelve a actuar cuando su condición
      pasa a cumplirse.».
  - Bloqueos que no dejan emitir: sistema desconectado, actuador fuera de servicio, comando pendiente (3a, con «Cancelalo o esperá su
    resultado» y el botón «Cancelar» si se puede).
  - El aviso al terminar (paso 9): «Comando {código} pendiente. El nodo lo retira en su próxima consulta; el resultado se verá en Monitoreo y
    en la ficha del actuador.».
- **Desde la ficha del actuador** (1b), «Emitir comando» abre la misma pantalla con `?actuador=<id>`.
- **Código visible** de un comando: `CMD-{id}`.

## Pantallas

| Pantalla | Función en el prototipo | Tarea |
|---|---|---|
| Comandos: emitir y lista | `comandos`, `cmdForm`, `cmdBadge`, `mismoEstado`; `case 'c-act'`, `'c-acc'`, `'emit'`, `'cf-*'` | IOT-05 |

**Lo que difiere del prototipo (manda el CU, L7):** el prototipo no tiene «Descripción» (paso 5): se agrega, opcional. No muestra el resumen
antes de confirmar (paso 6): las advertencias van en un resumen con «Confirmar», como el resto del sistema. `mismoEstado` solo conoce cuatro
estados: el sistema compara con `ESTADO_QUE_DEJA` (también los de nivel y posición).

## Para más adelante

- **IOT-06:** las reglas activas del actuador en el paso 4 y la advertencia 6b (hasta IOT-06 no hay reglas).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`. En esta pantalla: el recuadro «SOLO PROTOTIPO · simula la respuesta del nodo» (`sim-ok`, `sim-fail`,
`sim-rech`) y los códigos `CMD-NN` de ejemplo.
