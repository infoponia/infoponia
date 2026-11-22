# Casos de uso · iot · Reglas de actuación

Copia para el repo de los casos IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL e IOT-CNS-RGL (de alto nivel) de «CU extendidos» (sección IoT,
copiados el 22/11/2026). Cotejado con `docs/modelo/iot.md` («ReglaActuacion», MD-106) y con D-70 a D-78. La evaluación y el disparo de una
regla están en IOT-ENT-INF (`entregar_informacion.md`, extensiones 6a a 6d y sección «Reglas de actuación»).

**El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá. Para nombrar las pruebas:
`test_regla_<numero>_<que_espera>` y `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-ALT-RGL | Alta regla de actuación | Agrónomo o Gerente (alcance) | IOT-06 | `iot/tests/test_iot_alt_rgl.py` |
| IOT-MOD-RGL | Modificar regla de actuación (con reactivar) | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_mod_rgl.py` |
| IOT-BAJ-RGL | Baja regla de actuación | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_baj_rgl.py` |
| IOT-CNS-RGL | Consultar regla de actuación | Agrónomo y Gerente | IOT-06 | `iot/tests/test_iot_cns_rgl.py` |

## IOT-ALT-RGL · Alta Regla de Actuación

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** definir que, cuando la lectura de un sensor sale del umbral efectivo del invernadero o vuelve a él, InfoPonia ordene automáticamente una acción a un actuador.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El invernadero tiene un sistema IoT en estado «activo» o «desconectado», con al menos un sensor activo que admite reglas (regla 5) y al menos un actuador activo.

c. No existe otra regla de actuación activa con el mismo sensor, la misma condición y el mismo actuador.

**Postcondición:**

a. Se creó una regla de actuación en estado «activa», con su condición y, si la acción lo requiere, el valor a aplicar, asociada al sensor, al actuador y a la acción elegidos.

b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la regla creada.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. El sensor y el actuador son del mismo invernadero y están activos.

3. La condición es una de tres: la lectura supera el máximo del umbral efectivo; la lectura baja del mínimo del umbral efectivo; la lectura vuelve a quedar dentro del umbral efectivo. No se admiten valores fijos: los límites salen de las variedades de los lotes activos y de las siembras a realizar del invernadero (nota de presentación, «Emisión Automática de Comandos ante Umbral Agronómico Superado»).

4. La acción es una de las acciones activas del tipo del actuador y, si el nodo anunció sus capacidades, compatible con ellas (regla 14 de IOT-ALT-HDW). Si requiere un valor, el valor a aplicar es obligatorio, es un número entero en la unidad de la acción y está entre su mínimo y su máximo.

5. Solo admiten reglas los sensores de temperatura, humedad e intensidad lumínica. La temperatura y el nivel de la solución no admiten reglas: se monitorean con alertas, la temperatura frente al rango del sistema IoT del invernadero (regla 7 de IOT-MOD-SIS) y el nivel cuando informa «bajo». El fotoperíodo tampoco admite reglas, porque es un valor diario que calcula InfoPonia. Las reglas de un sensor de intensidad lumínica se evalúan solo dentro del horario de luz de la Configuración Operativa.

6. No puede haber dos reglas activas con el mismo sensor, la misma condición y el mismo actuador (precondición c).

7. Si el invernadero no tiene lotes activos ni siembras a realizar, no tiene umbral efectivo y la regla no se va a disparar hasta que lo tenga. El Sistema lo advierte y deja continuar.

8. La regla se dispara solo cuando su condición pasa a cumplirse, y no repite el comando mientras siga cumpliéndose. Para no reaccionar al ruido ni encender y apagar el equipo seguido: la condición tiene que cumplirse en la cantidad de lecturas seguidas de confirmación de la Configuración Operativa; deja de cumplirse recién cuando la lectura se aleja del límite más que la histéresis de la variable; y la regla no emite si no pasó el tiempo mínimo entre comandos del tipo del actuador. Para devolver un actuador a su estado anterior se define otra regla con la condición «vuelve a quedar dentro del umbral efectivo». La evaluación y la emisión del comando se detallan en IOT-ENT-INF e IOT-EMT-CMD.

9. Una regla de un sistema IoT desconectado se crea igual y se empieza a evaluar cuando el sistema se activa.

10. Las reglas no se evalúan con lecturas atrasadas, es decir, medidas hace más de la antigüedad máxima de la Configuración Operativa, ni mientras el nodo central informa el modo «local» (IOT-ENT-INF).

## IOT-MOD-RGL · Modificar Regla de Actuación

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** cambiar la condición, la acción o el valor a aplicar de una regla de actuación, o reactivar una dada de baja.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. La regla pertenece a un sistema IoT en estado «activo» o «desconectado».

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron la condición, la acción o el valor a aplicar de la regla.

b. Si reactivó la regla, quedó en estado «activa».

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la regla y los cambios.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. La condición, la acción y el valor siguen las reglas 3 a 5 y 7 de IOT-ALT-RGL.

3. El sensor y el actuador de una regla no se cambian: para otro sensor u otro actuador se da de alta una regla nueva. Así, los comandos que generó la regla conservan su significado.

4. El cambio rige desde la próxima lectura, que se evalúa como si la condición no se cumpliera antes y con la confirmación desde cero. Los comandos ya emitidos no cambian.

5. La regla modificada no puede quedar igual a otra regla activa en sensor, condición y actuador (regla 6 de IOT-ALT-RGL).

6. Una regla inactiva no se modifica: solo se reactiva. Para reactivarla, su sensor y su actuador tienen que estar activos y no puede existir otra regla activa igual.

## IOT-BAJ-RGL · Baja Regla de Actuación

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** dar de baja lógica una regla de actuación, sin afectar el historial de los comandos que generó.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. La regla está en estado «activa».

**Postcondición:**

a. La regla quedó en estado «inactiva» (baja lógica) y dejó de evaluarse, con el historial de los comandos que generó.

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la regla y el cambio de estado.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Los comandos pendientes que generó la regla siguen su curso.

3. Las reglas también pasan a inactivas, sin este caso de uso, cuando se da de baja su sistema IoT (IOT-BAJ-SIS).

4. Se reactiva con IOT-MOD-RGL.

## IOT-CNS-RGL · Consultar Regla de Actuación

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** consultar las reglas de actuación del sistema IoT de un invernadero y los comandos que generó cada una.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. No se producen cambios en el Sistema.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-CNS-HDW.

2. De cada regla se ven su sensor con su variable, su condición, su actuador, su acción con el valor a aplicar, su estado y su último disparo, con la fecha y hora, el comando emitido y su resultado. Si la regla no puede emitir comandos, se indica el motivo: actuador fuera de servicio, acción incompatible con el nodo, invernadero sin umbral efectivo o nodo en modo local.

3. Se filtra por estado, por sensor y por actuador.

4. En la ficha de una regla se ve el historial de los comandos que generó.

5. Quien puede operar el IoT del invernadero inicia desde acá IOT-ALT-RGL, IOT-MOD-RGL e IOT-BAJ-RGL. Quien solo consulta no tiene acciones.

6. La consulta no se audita (SEG-14).

## Cómo se aplica en la ronda «IoT 1» (D-44, D-72, D-75, D-78)

Tarea: **IOT-06**. Modelo: `docs/modelo/iot.md`, «ReglaActuacion» y «Comando». Alcance: `sistema_iot.md`, «Para los cinco».

- **Servicios** en `iot/servicios/reglas.py`:
  - `datos_para_regla(actor, invernadero_id, actuador_id=None)`: los sensores que admiten reglas (temperatura, humedad e intensidad lumínica;
    activos), los actuadores activos y, del elegido, sus acciones activas compatibles.
  - `alta_regla(actor, invernadero_id, datos)`, `modificar_regla(actor, regla_id, datos)`, `reactivar_regla(actor, regla_id)` y
    `baja_regla(actor, regla_id)`, cada una en su transacción, con los bloqueos invernadero → sistema → sensor → actuador → regla.
  - **La acción y el valor los valida `comandos.validar_comando`** (IOT-05), la misma de un comando manual (regla 4 de ALT; regla «Comando
    válido» de IOT-EMT-CMD).
  - Unicidad (regla 6 de ALT, regla 5 de MOD): el índice único parcial `(sensor, condicion, actuador)` con `estado_regla = activa`. El
    `IntegrityError` se traduce a «Ya hay una regla activa igual: {texto de la regla}.», nunca un 500.
  - **Al crear, modificar o reactivar:** `ultima_evaluacion = sin_evaluar` y `contador_confirmacion = 0` (regla 4 de MOD; regla «Disparo de
    una regla»).
  - Auditoría: `alta_regla_actuacion`, `modificacion_regla_actuacion` (con antes y después, y `datos.reactivada` si corresponde) y
    `baja_regla_actuacion`.
  - Lectura: `buscar_reglas(actor, invernadero_id, filtros)` y `ficha_de_regla(actor, regla_id)`, con el historial de comandos de la regla
    (regla 4 de CNS), sin consultas por fila.
- **Regla 7 de ALT.** Sin umbral efectivo, la regla se guarda con la advertencia del prototipo: «Este invernadero no tiene umbral efectivo:
  la regla se guarda, pero no se evalúa hasta que lo tenga.».
- **Regla 9 de ALT.** Con el sistema desconectado se crea igual (estado del sistema activo o desconectado: precondición b).
- **Texto de una regla** (prototipo `rglText`): «Cuando {sensor} {identificador} {condición}, {actuador} {identificador}: {acción}[ {valor}
  {unidad}]». Las condiciones con los textos del modelo: «supera el máximo del umbral efectivo», «baja del mínimo del umbral efectivo» y
  «vuelve a quedar dentro del umbral efectivo».
- **Situación de una regla** (regla 2 de CNS; prototipo `ultB` y `rglTags`):
  - la evaluación: «Se cumple», «Confirmando {n} de {N}», «No se cumple» o «Sin evaluar»;
  - el último disparo: la fecha y hora del último comando de la regla, con su estado;
  - los motivos por los que **no emite**: «actuador fuera de servicio», «acción incompatible con el nodo», «sin umbral efectivo» y «nodo en
    modo local» (los de la regla 2); además, «sensor en un sector fuera de servicio» (extensión 5d de IOT-ENT-INF).
- **MOD (reglas 3 y 6).** El sensor y el actuador no se cambian: el formulario los muestra deshabilitados, con «El sensor y el actuador no se
  cambian: para otros, se crea una regla nueva.». Una regla inactiva solo muestra «Reactivar», que exige el sensor y el actuador activos y
  ninguna regla activa igual.
- **BAJ (regla 2).** Los comandos pendientes de la regla siguen su curso.
- **Lo que completa:** `tiene_reglas(equipo)` (IOT-02); `acciones_en_uso(tipo)` por reglas activas (IOT-01); las reglas activas del
  actuador en Emitir comando (paso 4 y 6b, IOT-05).
- **Pantalla «Reglas de actuación»** (pestaña `reglas/`, con `?invernadero=`; prototipo `reglas`): la lista (código `RGL-{id}`, texto,
  situación, menú «Modificar» y «Dar de baja» para quien opera), los filtros por estado, sensor y actuador (regla 3 de CNS), la ficha de la
  regla con su historial, y el formulario con la frase de vista previa. La baja se confirma en la ventana `rbaj:<id>`.

## Pantallas

| Pantalla | Función en el prototipo | Tarea |
|---|---|---|
| Lista, alta y modificación | `reglas`, `rglText`, `ultB`, `rglTags`, `rglSensors`, `COND`; `case 'rgl-new'`, `'rgl-mod'`, `'r-cond'`, `'r-act'`, `'r-acc'`, `'save-rgl'` | IOT-06 |
| Dar de baja | `modalHtml` (`rbaj:<id>`) | IOT-06 |

**Lo que difiere del prototipo (manda el CU, L7):**
- El prototipo no tiene filtros ni la ficha de la regla con su historial (reglas 3 y 4 de CNS): se agregan.
- La lista del prototipo esconde las reglas dadas de baja: el sistema las muestra con el filtro de estado y ofrece «Reactivar» (MOD).
- `rglSensors` excluye los sensores de un sector fuera de servicio: el CU no lo pide (regla 2 de ALT habla solo del estado del sensor). Se
  ofrecen, y la situación de la regla muestra que no se evalúa mientras el sector siga fuera de servicio (D-75, punto 7).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`. En esta pantalla, los códigos `RGL-NN` de ejemplo.
