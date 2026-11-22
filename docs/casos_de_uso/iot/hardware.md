# Casos de uso · iot · Hardware

Copia para el repo de los casos IOT-ALT-HDW, IOT-MOD-HDW, IOT-BAJ-HDW e IOT-CNS-HDW (v0.2, de alto nivel) de «CU extendidos» (Lote 1 v5.6
del IoT, pegado el 20/11/2026 y cotejado el 21/11/2026). Reemplazan a CU-82 a CU-85 de la «Documentación para la IA» y al caso por
especificar 21 (Alta Hardware) de pendientes_CU. Cotejado con pendientes_MD hasta MD-113 (MD-100, MD-101 y MD-102) y con el glosario del
19/11/2026.

Son casos de uso breves (de alto nivel). **El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no
elijas en silencio.

Para nombrar las pruebas: `test_regla_<numero>_<que_espera>` y `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-ALT-HDW | Alta Hardware | Agrónomo o Gerente (alcance) | IOT-02 | `iot/tests/test_iot_alt_hdw.py` |
| IOT-MOD-HDW | Modificar Hardware (con volver a activar y reactivar) | Agrónomo o Gerente | IOT-02 (la regla 8, en IOT-07: `mantenimiento_automatico.md`) | `iot/tests/test_iot_mod_hdw.py` (la regla 8, `test_iot_mod_hdw_ordenes.py`) |
| IOT-BAJ-HDW | Baja Hardware | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_baj_hdw.py` |
| IOT-CNS-HDW | Consultar Hardware | Agrónomo y Gerente | IOT-02 | `iot/tests/test_iot_cns_hdw.py` |

## IOT-ALT-HDW · Alta Hardware

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** registrar un sensor o un actuador instalado en un invernadero con sistema IoT, para recibir sus lecturas o enviarle comandos.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El invernadero tiene un sistema IoT en estado «activo» o «desconectado».

c. No existe otro equipo no dado de baja del mismo sistema IoT con el mismo identificador.

**Postcondición:**

a. Se creó un sensor o un actuador en estado «activo», con su identificador, su modelo, su número de serie si se indicó y su fecha de instalación, asociado al nodo central del sistema IoT del invernadero, al insumo que le corresponde y, si se indicó, a un sector.

b. Si es un sensor, quedó con su nombre, su variable, su unidad de medida si la variable la tiene y, salvo que mida el nivel de la solución, su rango de calibración (mínimo y máximo).

c. Si es un actuador, quedó con su descripción y asociado a su tipo de actuador, cuyas acciones son las que puede ejecutar.

d. Si había una alerta activa «dispositivo no registrado» con ese identificador en el sistema IoT, pasó a «resuelta».

e. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del hardware creado, y de la alerta resuelta, si la hubo.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Identificador del equipo: es el código con el que el nodo central nombra al equipo en sus mensajes. Lo define quien configura el nodo (por ejemplo, un número de serie o un tópico MQTT); InfoPonia no lo interpreta, solo lo compara. Es obligatorio, sin espacios, de hasta 64 caracteres entre letras, números, «-», «_», «.» y «/», y se compara sin distinguir mayúsculas ni espacios al principio o al final. Es único entre los equipos no dados de baja del mismo sistema IoT: un equipo de reemplazo puede usar el identificador de uno dado de baja, y dos sistemas IoT pueden usar los mismos identificadores.

3. El sector es opcional: un equipo sin sector es general del invernadero. Si se indica, es un sector activo o fuera de servicio del mismo invernadero (regla 21 de 8.20).

4. La variable del sensor se elige de una lista fija, y su unidad de medida queda fijada por ella: temperatura (°C), humedad (% HR), intensidad lumínica (lux), temperatura de la solución (°C) y nivel de la solución («normal» o «bajo»). La intensidad lumínica se mide en lux porque es la unidad de los sensores accesibles y la que usan los rangos de las variedades; la medición en PPFD queda como mejora futura. Un equipo que mide dos variables se registra como dos sensores.

5. El rango de calibración es obligatorio para todas las variables salvo el nivel de la solución, que solo informa «normal» o «bajo». El mínimo es menor que el máximo. Son los valores que el sensor puede medir: una lectura fuera de ese rango se toma como lectura inválida, que indica un problema del equipo y no del ambiente.

6. El fotoperíodo no se registra como sensor: InfoPonia lo calcula una vez por día a partir de las lecturas de cada sensor de intensidad lumínica (IOT-ENT-INF). Un invernadero sin sensor de intensidad lumínica no tiene fotoperíodo monitoreado.

7. El tipo de actuador se elige entre los tipos activos. Si falta el que se necesita, el Agrónomo se lo pide al Gerente, que lo registra con IOT-ALT-TAC.

8. El insumo se elige entre los insumos activos de la categoría del sistema «Repuestos de hardware» (R072). No hace falta que esté habilitado en el invernadero ni que tenga stock: dar de alta un equipo no consume stock, porque el equipo ya está instalado. Si el insumo no existe, primero se registra con CMP-ALT-INS.

9. La fecha de instalación es obligatoria y no puede ser posterior a la fecha actual.

10. El nodo central no se da de alta en este caso de uso: se registra junto con el sistema IoT (IOT-REG-SIS).

11. Si el sistema IoT está desconectado, el equipo queda registrado y sus mensajes se aceptan desde que se active el sistema.

12. Desde una alerta «dispositivo no registrado» se inicia este caso de uso con el identificador ya cargado. Al registrar el equipo, la alerta se resuelve y sus mensajes empiezan a aceptarse (IOT-ENT-INF). Si el identificador es el de un equipo dado de baja del mismo sistema IoT, el Sistema lo advierte y ofrece reactivar ese equipo con IOT-MOD-HDW, que conserva su historial; registrar uno nuevo queda para un aparato de reemplazo, que empieza su propio historial.

13. Número de serie: dato físico opcional del aparato, útil para el mantenimiento y la garantía. No identifica al equipo ante el nodo y no es único: un mismo aparato puede generar varios sensores; por ejemplo, uno que mide temperatura y humedad se registra como dos sensores con el mismo número de serie.

14. Si el nodo anunció sus equipos (IOT-ENT-INF), el Sistema ofrece elegir el identificador entre los anunciados que todavía no están registrados, marcando los que eran de un equipo dado de baja (regla 12), y, para un actuador, informa si las capacidades anunciadas cubren los comandos de las acciones del tipo elegido. Una incompatibilidad se advierte y no impide el alta; mientras dure, el actuador tiene la alerta «configuración incompatible» y las acciones incompatibles no se ofrecen en comandos ni en reglas. Si el nodo no anuncia sus equipos, la compatibilidad queda «sin verificar» y no se restringe ninguna acción.

## IOT-MOD-HDW · Modificar Hardware

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** actualizar los datos de un sensor o de un actuador, volver a activar un equipo fuera de servicio, o reactivar uno dado de baja.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El equipo pertenece a un sistema IoT en estado «activo» o «desconectado».

c. El equipo no tiene comandos pendientes.

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron los datos indicados del equipo.

b. Si volvió a activar un equipo fuera de servicio, quedó en estado «activo» y sus alertas activas de falla pasaron a «resuelta». Las órdenes de mantenimiento a realizar que el actor eligió cancelar quedaron canceladas, y el Técnico recibió una notificación de cada una.

c. Si reactivó un equipo dado de baja, quedó en estado «activo», y si había una alerta activa «dispositivo no registrado» con su identificador, pasó a «resuelta».

d. Si reactivó un actuador o cambió su tipo, quedó marcado «compatible», «incompatible» o «sin verificar» según el último anuncio del nodo, con sus acciones incompatibles, y su alerta «configuración incompatible» se generó o se resolvió (regla 14 de IOT-ALT-HDW).

e. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del equipo y los cambios, y otro por cada alerta generada o resuelta y cada orden cancelada.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Se pueden cambiar el modelo, el número de serie, el sector, el nombre del sensor o la descripción del actuador, y el rango de calibración del sensor. El sector y la calibración siguen las reglas 3 y 5 de IOT-ALT-HDW, y el número de serie, la regla 13.

3. No se puede cambiar si el equipo es un sensor o un actuador. La variable de un sensor no se cambia si ya tiene lecturas, y el tipo de un actuador no se cambia si ya tiene reglas de actuación o comandos.

4. El identificador solo se corrige si el equipo nunca reportó: no tiene lecturas, estados informados ni comandos. Sirve para corregir un identificador mal cargado, que como no coincide con el que usa el nodo nunca va a reportar. El identificador nuevo sigue la regla 2 de IOT-ALT-HDW, y si había una alerta activa «dispositivo no registrado» con el identificador nuevo, pasa a «resuelta». Un equipo que ya reportó conserva su identificador, porque identifica su historial; si el aparato se reemplaza, el equipo se da de baja y el nuevo se registra con el mismo identificador.

5. Un equipo con comandos pendientes no se modifica (precondición c).

6. El cambio del rango de calibración rige desde la próxima lectura: no vuelve a evaluar las lecturas anteriores.

7. Volver a activar un equipo fuera de servicio se hace a mano con este caso de uso, por ejemplo cuando el equipo vuelve a funcionar sin un mantenimiento formal. Cuando exista Concretar Mantenimiento técnico, un mantenimiento exitoso también lo hará, y esta vía manual se mantiene.

8. Al volver a activar un equipo fuera de servicio, el Sistema muestra las órdenes de mantenimiento a realizar que lo incluyen, y por cada una el actor elige cancelarla o mantenerla. Si la orden incluye otros equipos que siguen fuera de servicio, no se ofrece cancelarla. La cancelación sigue a Cancelar Orden: libera las reservas, si las hubiera.

9. Un equipo dado de baja no se modifica: solo se reactiva. No se reactiva si su sistema IoT está dado de baja (regla 2 de IOT-BAJ-SIS) ni si otro equipo no dado de baja del mismo sistema usa su identificador (regla 2 de IOT-ALT-HDW). Tampoco se reactiva un actuador cuyo tipo de actuador está dado de baja (D-82; código `tipo_inactivo`): el Gerente reactiva antes el tipo.

10. Al reactivar un actuador o cambiar su tipo, el Sistema vuelve a comparar los comandos de las acciones activas de su tipo con el último anuncio del nodo, igual que en el alta (regla 14 de IOT-ALT-HDW), e informa el resultado antes de guardar. Una incompatibilidad se advierte y no impide guardar.

## IOT-BAJ-HDW · Baja Hardware

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** dar de baja lógica un sensor o un actuador que se retira del invernadero, sin perder su historial.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El equipo está en estado «activo» o «fuera de servicio».

c. El equipo no tiene comandos pendientes.

d. El equipo no está incluido en una orden de mantenimiento «a realizar».

e. Ninguna regla de actuación activa usa el equipo.

**Postcondición:**

a. El equipo quedó en estado «inactivo» (baja lógica), con su historial de telemetría, comandos y alertas.

b. Las alertas activas originadas en el equipo pasaron a «resuelta».

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del equipo y el cambio de estado, y otro por cada alerta resuelta.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Si no se cumplen las precondiciones c a e, el Sistema no da de baja el equipo e informa lo que lo impide, cada cosa con cómo resolverla: de un comando pendiente se espera su resultado o se cancela con IOT-CNL-CMD; las órdenes de mantenimiento se concretan o se cancelan (Cancelar Orden); las reglas de actuación se dan de baja (IOT-BAJ-RGL).

3. La baja en cascada de todo el hardware de un sistema se hace con IOT-BAJ-SIS, no con este caso de uso.

4. Un sector con hardware activo no se puede dar de baja (pendientes_CU, Ajustes pendientes en la documentación, punto 16).

5. Se reactiva con IOT-MOD-HDW.

6. Al darse de baja, el identificador del equipo queda libre: se puede registrar con él un equipo de reemplazo (regla 2 de IOT-ALT-HDW), que empieza su propio historial.

7. Antes de confirmar la baja de un actuador, el Sistema muestra su último estado informado por el nodo (por ejemplo, «encendido desde las 14:09») y advierte que, después de la baja, InfoPonia no podrá enviarle comandos: si tiene que quedar apagado o cerrado, se lo lleva a ese estado antes, con Emitir Comando, o en el invernadero. La advertencia no impide la baja. Si el nodo nunca informó su estado, se advierte que es «desconocido».

8. Si el aparato sigue conectado y el nodo sigue enviando mensajes con su identificador, se rechazan y generan la alerta «dispositivo no registrado», que indica que el identificador era de este equipo dado de baja (IOT-ENT-INF, extensión 3a). La alerta se resuelve sola cuando el nodo deja de enviarlos, por ejemplo al quitar el equipo de la configuración del nodo.

## IOT-CNS-HDW · Consultar Hardware

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** consultar el nodo central y los sensores y actuadores del sistema IoT de un invernadero, con su estado, y acceder a la ficha de cada equipo.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. No se producen cambios en el Sistema.

**Reglas:**

1. Alcance: la consulta es siempre sobre un invernadero elegido (regla 4 de 8.22). El Agrónomo consulta los invernaderos activos a su cargo; el Gerente consulta todos. Operar sigue la regla 1 de IOT-DSC-SIS.

2. Del nodo central se ven su estado, su conectividad («en línea» o «sin señal»), su modo («remoto» o «local», según lo informe el nodo) y la fecha y hora de su última comunicación.

3. De cada equipo se ven su identificador, su modelo, su número de serie si lo tiene, su sector o la marca «general», y su estado. De cada sensor, además, su variable, su unidad, su rango de calibración (salvo el nivel de la solución) y su última lectura. De cada actuador, su tipo, su compatibilidad con las capacidades anunciadas por el nodo («compatible», «incompatible» o «sin verificar») y su estado actual tal como lo informó el nodo (por ejemplo, «encendido»), con la fecha y hora en que lo informó. Si el cambio de estado no lo originó un comando de InfoPonia, se marca «cambiado en el invernadero».

4. Un equipo del que todavía no llegó ningún mensaje (lectura, estado informado por el nodo o resultado de un comando) se marca «sin confirmar». Un equipo que el nodo informó desconectado, o un sensor sin lecturas dentro del plazo de la Configuración Operativa, se marca «sin actividad» y tiene la alerta «dispositivo sin actividad». Un actuador del que el nodo nunca informó su estado operativo muestra el estado «desconocido».

5. Se filtra por tipo de equipo (sensor o actuador), por sector y por estado, y se busca por identificador o por nombre.

6. En la ficha de un equipo se ven además su insumo y su fecha de instalación, sus alertas, sus órdenes de mantenimiento y, si es un actuador, su historial de comandos.

7. Quien puede operar el IoT del invernadero inicia desde acá IOT-ALT-HDW, IOT-MOD-HDW e IOT-BAJ-HDW, y, en un actuador, Emitir Comando e IOT-CNL-CMD. Quien solo consulta no tiene acciones.

8. La consulta no se audita (SEG-14).

## Cómo se aplica en la ronda «IoT 1» (D-44, D-72)

Tareas: **IOT-02** (ALT, MOD y CNS) e **IOT-06** (BAJ). Modelo: `docs/modelo/iot.md`, «Hardware», «Sensor», «Actuador» y «EquipoAnunciado».
El alcance, la elección del invernadero y la conectividad son los de `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco». Decisiones
de aplicación:

- **Identificador (regla 2 de ALT).** Validador `iot/validadores.py`, `validar_identificador_equipo`: se recorta, hasta 64 caracteres,
  `^[A-Za-z0-9._/-]{1,64}$` («Hasta 64 caracteres sin espacios: letras, números, - _ . /»). Se guarda como se escribió y se compara en
  minúsculas. La unicidad la respalda el índice único parcial `(sistema, Lower(identificador_equipo))` sin los dados de baja: dos altas
  simultáneas con el mismo identificador dan a la segunda el error del campo («Ya lo usa {equipo} en este sistema IoT.»), nunca un 500.
- **El equipo pertenece al sistema** (`Hardware.sistema`, D-72): el del invernadero elegido, activo o desconectado (precondición b de ALT).
  Con el sistema desconectado se registra igual (regla 11).
- **Sensor (reglas 4 a 6 de ALT).** Variable de la lista (`Sensor.Variable`, con su unidad fija en el código: `°C`, `% HR`, `lux`, `°C` y sin
  unidad para el nivel). Calibración: dos decimales, obligatoria salvo en el nivel, mínimo < máximo. El nombre del sensor es opcional (hasta
  60; `docs/modelo/iot.md`, «Sensor»). El texto bajo «Variable» del prototipo: «El fotoperíodo no es un sensor: InfoPonia lo calcula con los
  sensores de intensidad lumínica.».
- **Actuador (regla 7 de ALT).** Tipo de la lista de tipos **activos**. Descripción opcional (hasta 300). Para el Agrónomo, bajo el campo:
  «Si falta el tipo que necesitás, pedíselo al Gerente: los tipos son comunes a toda la organización.».
- **Insumo (regla 8 de ALT).** Lista de insumos activos de la categoría `repuestos_de_hardware` (por `codigo`, regla 1 de 8.23), sin mirar
  habilitación ni stock. No mueve stock.
- **Sector (regla 3 de ALT).** «General (todo el invernadero)» o un sector **activo o fuera de servicio** del mismo invernadero. Si es un
  sensor en un sector fuera de servicio, el aviso al terminar del prototipo: «El {sector} está fuera de servicio: este sensor no generará
  alertas ni activará reglas.».
- **Fecha de instalación (regla 9 de ALT):** obligatoria, no posterior a hoy.
- **Identificadores anunciados (regla 14 de ALT).** El campo ofrece (lista `datalist`) los identificadores de `EquipoAnunciado` del sistema
  que no están registrados, marcando los que eran de un equipo dado de baja. Para un actuador anunciado, antes de guardar se muestra si el
  nodo soporta todas las acciones del tipo (el aviso «Compatible» o la lista de las que no). Los anuncios los escribe la API (**IOT-03**):
  hasta entonces no hay ninguno, todo actuador queda «sin verificar» y la lista está vacía.
- **Compatibilidad (regla 14 de ALT, postcondición d y regla 10 de MOD).** `iot/servicios/compatibilidad.py`,
  `recalcular_compatibilidad(actuadores)`: compara los comandos de las acciones **activas** del tipo de cada actuador con los anunciados para
  su identificador en su sistema; sin anuncio, `sin_verificar` y sin acciones incompatibles; con anuncio, `compatible` o `incompatible` y
  `acciones_incompatibles`. Genera o resuelve la alerta `iot_configuracion_incompatible` (clave `hw:<id>`) y crea su `AlertaIot`. La usan el
  alta, la modificación, la reactivación, IOT-MOD-TAC y la API de anuncios (IOT-03). Una sola función: nadie más calcula la compatibilidad.
- **Alerta «dispositivo no registrado» (postcondición d de ALT, c de MOD, regla 4 de MOD).** Al registrar un equipo, reactivarlo o corregir
  su identificador, se resuelve la alerta activa `iot_dispositivo_no_registrado` con la clave `id:<identificador en minúsculas>` del
  invernadero (`resolver_alerta_de_estado`). La crea la API (IOT-03).
- **Desde una alerta (regla 12 de ALT).** El alta acepta `?identificador=<…>` y carga el campo con el texto «Tomado de la alerta «Dispositivo
  no registrado».». Si el identificador es el de un equipo dado de baja del sistema, el formulario lo advierte y ofrece «Reactivar {equipo}»
  (conserva su historial) además de seguir con el alta (un reemplazo). El enlace desde la alerta lo registra IOT-04 (D-62).
- **Modificar (MOD).**
  - Cambian el modelo, el número de serie, el sector, el nombre del sensor, la descripción del actuador y la calibración (regla 2).
  - El tipo de equipo nunca cambia. La variable de un sensor cambia solo si no tiene lecturas; el tipo de un actuador, solo si no tiene
    reglas ni comandos (regla 3). El identificador, solo si el equipo nunca reportó (regla 4): `ultimo_mensaje_en` nulo y sin lecturas ni
    comandos. Funciones: `tiene_lecturas(sensor)`, `tiene_comandos(actuador)`, `tiene_reglas(equipo)`. **Se completan en IOT-03 (lecturas,
    ya existe la tabla), IOT-05 (comandos) e IOT-06 (reglas):** en IOT-02 las tres consultan sus tablas, que todavía están vacías, y se
    prueban con filas creadas por la fábrica.
  - Precondición c (sin comandos pendientes): la verifica `tiene_comando_pendiente(actuador)`; los comandos existen desde IOT-05, pero la
    tabla ya existe y la consulta se escribe y se prueba en IOT-02.
  - **Volver a activar un equipo fuera de servicio** (postcondición b, reglas 7 y 8): botón aparte con su confirmación. Pasa a `activo` y
    resuelve sus alertas activas `iot_dispositivo_en_falla` e `iot_comando_fallido`. **Las órdenes de mantenimiento de la regla 8 se completan
    en IOT-07** (la ventana lista las órdenes a realizar del equipo y, por cada una, «Cancelarla» o «Mantenerla»; D-73, D-79 punto 8;
    `mantenimiento_automatico.md`, «Volver a activar un equipo con órdenes»).
  - **Reactivar un equipo dado de baja** (postcondición c, regla 9): pasa a `activo` y `fecha_baja` a nulo; no se puede si el sistema está
    dado de baja ni si otro equipo no dado de baja del sistema usa su identificador («No se puede reactivar: el identificador X ya lo usa
    {equipo} (registrado como reemplazo).»). Si es un actuador, se recalcula su compatibilidad.
  - Un equipo dado de baja no se modifica: solo muestra «Reactivar».
- **Baja (BAJ, IOT-06).** Precondiciones c a e (comandos pendientes, órdenes a realizar —**se completan en IOT-07**—, reglas activas que lo
  usan): si hay, la ventana no deja confirmar y explica cómo resolverlo (regla 2, textos del prototipo, ventana `baj:<id>`). En una
  transacción: `inactivo`, `fecha_baja` = hoy, y se resuelven las alertas activas del equipo (las de clave `hw:<id>` y `sensor:<id>`). La
  advertencia del último estado de un actuador (regla 7) va en la ventana y no bloquea.
- **Consulta (CNS).**
  - Arriba, el nodo central: estado del sistema, conectividad, modo y última comunicación (regla 2).
  - Lista de los equipos del sistema (también los dados de baja, con su marca), con filtros por tipo, estado y sector («General» incluido) y
    búsqueda por identificador, nombre del sensor, tipo o variable y número de serie (regla 5). Orden: sensores y después actuadores, por
    identificador.
  - «Situación» de cada equipo: «Sin confirmar» (`ultimo_mensaje_en` nulo), «Fuera de servicio», «Configuración incompatible» y, en los
    actuadores, «Comando pendiente». Lo que depende de lecturas y alertas («En rango», «Sin actividad», la última lectura) **se completa en
    IOT-03 e IOT-04**: hasta entonces la última lectura se muestra «—».
  - Ficha (regla 6): insumo, fecha de instalación, calibración o estado informado y compatibilidad, sus alertas activas y las reglas activas
    que lo usan (**IOT-06**), sus órdenes de mantenimiento (**IOT-07**) y el historial de comandos (**IOT-05**). D-25: lo que todavía no existe
    no se muestra.
- **Conexión con `maestros` (IOT-02).** `IotConfig.ready()` registra:
  - `registrar_impedimento_de_baja_de_sector`: código `hardware_activo` si el sector tiene equipos no dados de baja; texto «Tiene {n}
    equipo(s) del sistema IoT: {lista}.», `como_resolver` «Quitales el sector o dalos de baja desde IoT · Hardware.» (regla 3 de
    PROD-BAJ-SCT);
  - `registrar_contenido_de_sector`: un `Contenido` de tipo `hardware` por equipo no dado de baja del sector («Sensor de temperatura
    norte/sectorA/temperatura», con la URL de su ficha).
- **Bloqueos (D-82, excepción a D-40).** Alta: el invernadero (`bloquear_invernadero_activo`), después el sistema (`FOR NO KEY UPDATE`), releído. MOD, reactivación y
  baja: invernadero, sistema y el equipo, releídos. **Cuando interviene un tipo de actuador** (el alta de un actuador, el cambio del tipo de un actuador y la
  reactivación de un actuador), el tipo se bloquea primero (`bloquear_tipo_activo`) y recién después el invernadero, el sistema y el equipo. El tipo va antes
  porque IOT-MOD-TAC lo bloquea y después bloquea los invernaderos de sus actuadores al recalcular la compatibilidad; si el alta o el cambio de tipo bloquearan primero el
  invernadero, las dos operaciones se cruzarían y la base abortaría una. Sin cambios no se escribe ni se audita.
- **Auditoría (D-36).** Un registro por caso de uso: `alta_hardware`, `modificacion_hardware`, `reactivacion_hardware` (con `datos.desde`:
  `fuera_de_servicio` o `inactivo`) y `baja_hardware`. Afectados: el equipo, las alertas generadas o resueltas y, en IOT-07, las órdenes
  canceladas.

## Pantallas

Guía visual: `docs/prototipos/iot/`. Buscá la función y leé solo esa parte.

| Pantalla | Función en el prototipo | Casos de uso | Tarea |
|---|---|---|---|
| IoT · pestaña «Hardware» (lista, filtros y anunciados sin registrar) | `hardware` (rama final), `hwBadge`, `sensorState`, `actState`, `anunciadosLibres` | IOT-CNS-HDW | IOT-02 |
| Ficha del equipo | `hardware` (rama `hw-ficha`), `estInf`, `compatB` | IOT-CNS-HDW, botones de MOD y BAJ | IOT-02 |
| Registrar y modificar | `hardware` (rama `hw-form`), `act` (`hw-new`, `hw-mod`, `save-hw`, `reg-alert`), `recompat`, `announcedBad`, `bajaDe`, `tipoCambiable` | IOT-ALT-HDW, IOT-MOD-HDW | IOT-02 |
| Volver a activar y reactivar | `modalHtml` (`react:<id>`, `rebaja:<id>`) | IOT-MOD-HDW | IOT-02 (las órdenes, IOT-07) |
| Dar de baja | `modalHtml` (`baj:<id>`) | IOT-BAJ-HDW | IOT-06 |

**Lo que difiere del prototipo (manda el CU, L7):**

- Volver a activar: el prototipo cancela la orden de mantenimiento sin preguntar; el CU (regla 8) deja elegir por cada orden (D-73, IOT-07).
- El prototipo no deja cambiar la variable de un sensor en ningún caso: el CU lo permite si no tiene lecturas (regla 3).
- El prototipo no tiene «Nombre» del sensor: se agrega, opcional.
- La ficha del prototipo no muestra las alertas ni las órdenes del equipo: se agregan (regla 6 de CNS) cuando existan.

## Para más adelante

En `docs/disparadores.md`, «Cuando existan actuadores, comandos y reglas del IoT»:

- IOT-03: la última lectura y la situación por lecturas; los identificadores anunciados y la compatibilidad contra anuncios reales.
- IOT-05: el historial de comandos en la ficha; «Comando pendiente».
- IOT-06: las reglas que usan el equipo; la baja (BAJ).
- IOT-07: las órdenes de mantenimiento al volver a activar (regla 8) y en la ficha; la precondición d de la baja. Escrito en
  `docs/casos_de_uso/iot/mantenimiento_automatico.md` (lote I4).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`, «Solo prototipo». En estas pantallas, además: los identificadores `HW-NN` (en el sistema, el id) y los
anuncios fijos del objeto `SOP`.
