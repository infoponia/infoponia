# Casos de uso · iot · Sistema IoT

Copia para el repo de los casos IOT-REG-SIS (v0.2, extendido; Lote 2 v3), IOT-MOD-SIS, IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (v0.2, de alto
nivel; Lote 1 v5.6) de «CU extendidos», pegados el 20/11/2026 y cotejados el 21/11/2026. El 21/11/2026 se corrigió en Drive el tema abierto
«Guía de integración del nodo» de IOT-REG-SIS (decía `docs/api_nodo.md` y «el simulador»; D-70). Reemplazan a CU-90 a CU-93 de la
«Documentación para la IA». Cotejado con pendientes_MD hasta MD-113 (MD-98, MD-99 y MD-100) y con el glosario del 19/11/2026.

**El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: en IOT-REG-SIS (extendido), `test_paso_<n>_…`, `test_ext_<id>_…` (por ejemplo `test_ext_8a_…`) y
`test_post_<letra>_…`; las reglas de negocio de IOT-REG-SIS no están numeradas: se nombran por su título (`test_regla_token_…`). En los casos
breves, `test_regla_<numero>_…` y `test_post_<letra>_…`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-REG-SIS | Registrar Sistema IoT | Agrónomo o Gerente (alcance) | IOT-02 | `iot/tests/test_iot_reg_sis.py` |
| IOT-MOD-SIS | Modificar Sistema IoT (con regenerar el token) | Agrónomo o Gerente | IOT-02 | `iot/tests/test_iot_mod_sis.py` |
| IOT-DSC-SIS | Desactivar Sistema IoT | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_dsc_sis.py` |
| IOT-ACT-SIS | Activar Sistema IoT | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_act_sis.py` |
| IOT-BAJ-SIS | Baja Sistema IoT | Agrónomo o Gerente | IOT-06 | `iot/tests/test_iot_baj_sis.py` |

## IOT-REG-SIS · Registrar Sistema IoT

**Alcance:** Sistema InfoPonia. **Nivel:** Objetivo de usuario. **Módulo:** IoT.

**Actor principal:** Agrónomo (o Gerente, según su alcance; ver regla «Alcance»).

**Versión:** 0.2

**Personal involucrado e intereses:**

  - **Agrónomo:** quiere integrar el sistema IoT de su invernadero en pocos pasos, para monitorear sus condiciones y actuar sobre él sin estar presente.
  - **Técnico:** quiere recibir de una sola vez los datos que necesita para configurar el nodo central (la dirección de la API, el token y la guía de integración del nodo), y quedar a cargo del mantenimiento del hardware del invernadero.
  - **Gerente:** quiere que solo los nodos autorizados puedan enviar datos al Sistema, que ninguna credencial quede expuesta, y poder registrar el IoT de un invernadero que no tiene un Agrónomo activo.
  - **Organización (Jardín Botánico):** quiere integrar la infraestructura IoT que ya tiene, sin reemplazarla, para detectar a tiempo las condiciones ambientales de riesgo.

**Relaciones con otros casos de uso:** no incluye («include») otros casos de uso ni es extendido («extend») por ellos. Al terminar, ofrece iniciar IOT-ALT-HDW para registrar los sensores y actuadores. El token se regenera y el rango de temperatura de la solución se cambia con IOT-MOD-SIS.

**Precondiciones:**

a. El actor está autenticado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. Existe al menos un invernadero activo, dentro del alcance del actor, que no tiene un sistema IoT o cuyo sistema IoT está dado de baja.

c. Existe al menos un insumo activo de la categoría del sistema «Repuestos de hardware».

**Garantías mínimas:**

  - El registro es atómico. Si el caso de uso se cancela o falla, no queda registrado ningún sistema IoT, nodo central, token, alerta ni log de auditoría parcial.
  - El token nunca se guarda en texto plano, ni en la base de datos ni en los logs de auditoría o de errores.
  - Un invernadero nunca queda con dos sistemas IoT que no estén dados de baja, aun cuando dos actores lo registren al mismo tiempo.

**Garantías de éxito (Postcondiciones):**

a. Se creó un sistema IoT en estado «activo», asociado al invernadero (R068), con su rango de temperatura de la solución si se indicó.

b. Se creó su nodo central en estado «activo», con su nombre, su modelo, su número de serie si se indicó y su fecha de instalación, asociado al sistema IoT (R066) y al insumo elegido (R072), y sin sector.

c. Se generó el token del nodo central. Se guardó solo su resumen criptográfico, y el token se le mostró al actor una sola vez, junto con la dirección de la API y la guía de integración del nodo.

d. La conectividad del nodo central es «sin señal», porque todavía no se comunicó.

e. Si el invernadero no tiene un Técnico activo y no existía la alerta, se generó para el Gerente una alerta activa «invernadero sin Técnico activo».

f. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del sistema IoT y del nodo central creados, y de la alerta, si se generó. No registra el token.

**Escenario principal de éxito (o Flujo Básico):**

1.  El Agrónomo inicia el registro de un sistema IoT.
2.  El Sistema presenta los invernaderos activos a su cargo que no tienen un sistema IoT o cuyo sistema IoT está dado de baja. De cada uno indica su Técnico asignado o la marca «sin Técnico».
3.  El Agrónomo selecciona un invernadero.
4.  El Sistema solicita los datos del nodo central y presenta los insumos activos de la categoría «Repuestos de hardware».
5.  El Agrónomo ingresa el nombre, el modelo y la fecha de instalación del nodo central, selecciona su insumo y, si quiere, ingresa el número de serie del nodo y el rango de temperatura de la solución del invernadero.
6.  El Sistema verifica los datos y presenta un resumen: el invernadero, los datos del nodo central, el rango de temperatura de la solución si se indicó y el aviso de que se generará un token que se mostrará una sola vez.
7.  El Agrónomo confirma el registro.
8.  El Sistema registra el sistema IoT y su nodo central, genera el token y guarda solo su resumen.
9.  El Sistema presenta la dirección de la API, el token y la guía de integración del nodo, advierte que el token no volverá a mostrarse y que la conectividad del nodo quedará «sin señal» hasta su primera comunicación, y ofrece registrar el hardware (IOT-ALT-HDW).
10. El Agrónomo indica que guardó los datos. El Sistema deja de mostrar el token.

**Extensiones (o Flujos Alternativos):**

***a. En cualquier momento antes del paso 7, el actor cancela:**

1.  El Sistema no registra ningún cambio.
2.  El caso de uso termina.

**1a. El actor es el Gerente:**

1.  En el paso 2, el Sistema presenta los invernaderos activos sin un Agrónomo activo que no tienen un sistema IoT o cuyo sistema IoT está dado de baja.
2.  El caso de uso continúa en el paso 3.

**3a. El invernadero tuvo un sistema IoT que fue dado de baja:**

1.  El Sistema informa que el sistema anterior queda como historial y que se registra uno nuevo, con un nodo central nuevo. Los equipos se registran de nuevo y pueden usar los mismos identificadores que los del sistema anterior (regla 3 de IOT-BAJ-SIS).
2.  El caso de uso continúa en el paso 4.

**6a. Falta un dato obligatorio, la fecha de instalación es posterior a la fecha actual o el rango de temperatura de la solución no tiene el mínimo menor que el máximo:**

1.  El Sistema señala los datos con error.
2.  El caso de uso vuelve al paso 5.

**6b. El invernadero no tiene un Técnico activo:**

1.  En el resumen, el Sistema advierte que se generará para el Gerente la alerta «invernadero sin Técnico activo», y que nadie podrá concretar los mantenimientos del hardware hasta que se asigne uno.
2.  El caso de uso continúa en el paso 7.

**7a. El actor quiere cambiar algún dato antes de confirmar:**

1.  El caso de uso vuelve al paso 5.

**8a. Al registrar, el invernadero ya tiene un sistema IoT que no está dado de baja (otro actor lo registró):**

1.  El Sistema no registra ningún cambio e informa que el invernadero ya tiene un sistema IoT.
2.  El caso de uso vuelve al paso 2.

**8b. Al registrar, el invernadero pasó a inactivo o salió del alcance del actor (el Agrónomo dejó de tenerlo a cargo o, si el actor es el Gerente, se asignó un Agrónomo activo):**

1.  El Sistema no registra ningún cambio e informa el motivo.
2.  El caso de uso vuelve al paso 2.

**9a. El actor sale de la pantalla sin guardar el token:**

1.  El sistema IoT queda registrado, pero el token no se puede recuperar.
2.  Para configurar el nodo, se genera un token nuevo con IOT-MOD-SIS.

**Requisitos especiales:**

  - La interfaz se adapta a computadora y a celular.
  - La pantalla responde a cada acción del actor en no más de 1 segundo, y el registro del paso 8 se completa en no más de 5 segundos.
  - El registro se ejecuta como una única transacción. El sistema IoT, el nodo central, el resumen del token, la alerta y los logs se registran juntos o no se registra ninguno.
  - El token se genera con una fuente criptográficamente segura. Se guarda solo su resumen criptográfico, como las contraseñas (SEG-02), y no aparece en los logs de auditoría ni en los registros de errores.
  - El token solo autoriza la comunicación de ese nodo central con la API del Sistema: no da acceso a ninguna pantalla ni a datos de otros invernaderos.
  - Toda comunicación con el Sistema, incluida la del nodo, se hace por HTTPS (SEG-16).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Lista de tecnología y variaciones de datos:**

  - 5a. La fecha de instalación se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El insumo se elige de una lista. El rango de temperatura de la solución son dos números en °C, con hasta un decimal.
  - 9a. El token y la dirección de la API se presentan con un botón para copiarlos; la guía de integración del nodo, con un enlace para abrirla o descargarla.

**Frecuencia:** Muy baja: una vez por cada invernadero que incorpora un sistema IoT. A confirmar con el Jardín Botánico.

**Reglas de negocio:**

  - **Alcance:** el Agrónomo opera el IoT de los invernaderos activos a su cargo. El Gerente lo opera solo en los invernaderos sin un Agrónomo activo (sin asignar, o con el asignado inactivo), hasta que se asigne uno (decisión del 18/11/2026, que reemplaza en este punto a la regla 4 de 8.22). (Pasos 2 y 8, extensiones 1a y 8b)
  - **Invernadero elegible:** activo, dentro del alcance del actor, sin un sistema IoT o con su sistema IoT dado de baja. La regla de un único sistema IoT por invernadero (R068) cuenta solo los sistemas que no están dados de baja (regla 3 de IOT-BAJ-SIS). (Paso 2, extensiones 3a y 8a)
  - **Estado inicial, conectividad y modo:** el sistema IoT y su nodo central nacen en estado «activo». La conectividad no es un estado: se calcula con la fecha y hora de la última comunicación del nodo, y es «sin señal» hasta la primera (regla 3 de IOT-ACT-SIS). El modo del nodo («remoto» o «local») lo informa el nodo; informarlo es optativo, y mientras no lo informe se considera «remoto» (IOT-ENT-INF). Este caso de uso no se conecta con el nodo: es el nodo el que se comunica con el Sistema usando su token. (Pasos 8 y 9)
  - **Datos del nodo central:** el nombre, el modelo, la fecha de instalación y el insumo son obligatorios. El número de serie es un dato físico opcional del aparato y no es único: el nodo se identifica ante el Sistema con su token (regla 2 de IOT-MOD-SIS y regla 13 de IOT-ALT-HDW). La fecha sigue la regla 9 de IOT-ALT-HDW, y el insumo, la regla 8. El nodo central no tiene sector (regla 21 de 8.20). (Pasos 5 y 6)
  - **Rango de temperatura de la solución:** opcional al registrar; sigue la regla 7 de IOT-MOD-SIS, donde también se define o se cambia después. (Pasos 5 y 6, extensión 6a)
  - **Token:** se genera al registrar, se muestra una sola vez junto con la dirección de la API, se guarda solo su resumen y solo autoriza la comunicación de ese nodo con la API. Si se pierde o se filtra, se genera uno nuevo con IOT-MOD-SIS y el anterior deja de servir. (Pasos 8 a 10, extensión 9a)
  - **Guía de integración del nodo:** documento con el contrato de la API que debe cumplir el nodo central: los mensajes que envía y recibe, el catálogo de capacidades (regla 7 de IOT-ALT-TAC) y las obligaciones del nodo (actuar en forma local si no logra comunicarse con el Sistema, informar su modo y el estado de los actuadores, no repetir un comando ya ejecutado y sincronizar su reloj). Es la misma para todas las organizaciones; cada una la implementa en su propio nodo. (Paso 9)
  - **Técnico:** un invernadero con sistema IoT necesita un Técnico (PROD-ALT-INV, regla 5). Si no tiene uno activo, se genera la alerta «invernadero sin Técnico activo» para el Gerente, como en PROD-MOD-INV (postcondición d); se resuelve cuando se asigna un Técnico. (Extensión 6b)
  - **Hardware:** este caso de uso no registra sensores ni actuadores: se registran después con IOT-ALT-HDW. Un nodo central puede existir sin sensores (R065 pasa a 0..*, decisión del 18/11/2026). El Sistema solo acepta mensajes de equipos registrados (pre-registro); si el nodo anuncia sus equipos, el alta del hardware ofrece los identificadores anunciados (regla 14 de IOT-ALT-HDW). (Paso 9)

**Temas abiertos:**

  - **Cambios de modelo pendientes de registrar en pendientes_MD:** R065 (NodoCentral → Sensor) pasa de 1..* a 0..*; R068 cuenta solo los sistemas que no están dados de baja; el alcance del Gerente reemplaza a la regla 4 de 8.22; Hardware.numeroSerie pasa a opcional y deja de ser único; SistemaIoT suma el rango de temperatura de la solución (mínimo y máximo, opcionales); NodoCentral suma el modo (remoto / local). El token es un dato de diseño, no del dominio.
  - **Guía de integración del nodo:** documento del repositorio de InfoPonia, en docs/api/nodo/ (D-70), redactado junto con la API. Su implementación de referencia es el flujo de Node-RED de docs/api/nodo/node-red/ (corregido el 21/11/2026: antes decía docs/api_nodo.md y el simulador, que se reemplazó por Node-RED).

## IOT-MOD-SIS · Modificar Sistema IoT

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** corregir los datos del nodo central de un sistema IoT, definir el rango de temperatura de la solución nutritiva del invernadero o regenerar el token del nodo, por ejemplo si el token se perdió o se filtró.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El sistema IoT del invernadero está en estado «activo» o «desconectado».

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron los datos indicados del nodo central o el rango de temperatura de la solución del sistema IoT.

b. Si regeneró el token, se generó un token nuevo, se guardó solo su resumen criptográfico y se le mostró al actor una sola vez. El token anterior dejó de servir en ese momento.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del nodo central o del sistema IoT y los cambios. Si se regeneró el token, se registra que se regeneró, sin registrar ningún token.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Se pueden cambiar el nombre, el modelo y el número de serie del nodo central. El nodo se identifica ante el Sistema con su token, así que su número de serie es un dato físico del aparato y se corrige en cualquier momento.

3. Antes de regenerar el token, el Sistema advierte que el nodo dejará de poder comunicarse hasta que se le cargue el token nuevo, y que mientras tanto su conectividad pasará a «sin señal».

4. El token nuevo sigue las reglas de IOT-REG-SIS: se genera con una fuente criptográficamente segura, se muestra una sola vez junto con la dirección de la API, se guarda solo su resumen y solo autoriza la comunicación de ese nodo con la API del Sistema.

5. El estado del sistema no se cambia acá: se desactiva con IOT-DSC-SIS y se activa con IOT-ACT-SIS.

6. Un sistema IoT dado de baja no se modifica (regla 2 de IOT-BAJ-SIS).

7. Rango de temperatura de la solución: mínimo y máximo en °C, opcional, con el mínimo menor que el máximo. Lo define quien opera el IoT del invernadero según lo que cultiva, porque la temperatura adecuada de la solución depende del cultivo. Con él, InfoPonia compara las lecturas de los sensores de temperatura de la solución del invernadero y genera la alerta «solución fuera de rango» (IOT-ENT-INF). Sin rango, esas lecturas se muestran sin comparar. No se usa en reglas de actuación (regla 5 de IOT-ALT-RGL). El cambio rige desde la próxima lectura.

## IOT-DSC-SIS · Desactivar Sistema IoT

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** suspender por un tiempo la integración del sistema IoT de un invernadero, sin perder su nodo central, su hardware, sus reglas de actuación ni su historial, para volver a activarlo más adelante.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El sistema IoT del invernadero está en estado «activo».

**Postcondición:**

a. El sistema IoT quedó en estado «desconectado», con su nodo central, su hardware y sus reglas de actuación sin cambios.

b. Los comandos pendientes de sus actuadores pasaron a «cancelado».

c. Las alertas activas originadas en el sistema IoT del invernadero pasaron a «resuelta».

d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sistema IoT y el cambio de estado, y otro por cada comando cancelado y cada alerta resuelta.

**Reglas:**

1. Alcance: el Agrónomo opera el IoT de los invernaderos activos a su cargo. El Gerente lo opera solo en los invernaderos sin un Agrónomo activo (sin asignar, o con el asignado inactivo), hasta que se asigne uno; en los demás, solo consulta (decisión del 18/11/2026, que reemplaza en este punto a la regla 4 de 8.22). Los tipos de actuador no dependen de un invernadero: son comunes a toda la organización y los administra solo el Gerente, sin este alcance (IOT-ALT-TAC, IOT-MOD-TAC e IOT-BAJ-TAC); el Agrónomo los consulta (IOT-CNS-TAC).

2. Mientras el sistema está desconectado, el Sistema no acepta telemetría, estados ni anuncios de su nodo central, no le entrega comandos, no evalúa sus reglas de actuación y no genera alertas del sistema IoT. La revisión periódica de InfoPonia (IOT-ENT-INF) no revisa su nodo ni sus equipos.

3. Los comandos cancelados no se reintentan y no generan alertas ni órdenes de mantenimiento.

4. Si al activar el sistema el problema que originó una alerta resuelta sigue, la alerta se vuelve a generar.

5. Desactivar no cambia el estado del hardware ni el de las reglas de actuación, y no cancela las órdenes de mantenimiento a realizar.

6. Para suspender el sistema por un tiempo se desactiva; la baja (IOT-BAJ-SIS) es definitiva. Se vuelve a activar con IOT-ACT-SIS.

## IOT-ACT-SIS · Activar Sistema IoT

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** reanudar la integración de un sistema IoT desconectado, para volver a recibir su telemetría, emitirle comandos y evaluar sus reglas de actuación.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El invernadero está activo.

c. El sistema IoT del invernadero está en estado «desconectado».

**Postcondición:**

a. El sistema IoT quedó en estado «activo», con su nodo central, su hardware y sus reglas de actuación sin cambios.

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sistema IoT y el cambio de estado.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Desde la activación, el Sistema vuelve a aceptar telemetría, estados de dispositivos y anuncios del nodo central, a entregarle comandos, a evaluar las reglas de actuación y a generar alertas.

3. La conectividad del nodo central («en línea» o «sin señal») no es un estado que se active: se calcula con la fecha y hora de su última comunicación. La revisión periódica de InfoPonia, que corre cada 5 minutos, genera la alerta «nodo sin comunicación» si el nodo no se comunica dentro del plazo de la Configuración Operativa, y la notifica por correo (IOT-ENT-INF).

4. Cada regla de actuación se evalúa desde la primera lectura válida y no atrasada (regla 10 de IOT-ALT-RGL) que llega después de la activación, como si antes su condición no se cumpliera y con su confirmación desde cero: si la condición se cumple durante las lecturas de confirmación, la regla se dispara (regla 8 de IOT-ALT-RGL).

## IOT-BAJ-SIS · Baja Sistema IoT

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** dar de baja lógica, en forma definitiva, el sistema IoT de un invernadero junto con su nodo central y todo su hardware, preservando su historial de telemetría, comandos y alertas.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El sistema IoT del invernadero está en estado «activo» o «desconectado».

c. Ningún actuador del sistema tiene comandos pendientes.

d. Ningún hardware del sistema está incluido en una orden de mantenimiento «a realizar».

**Postcondición:**

a. El sistema IoT, su nodo central y todo su hardware, activo o fuera de servicio, quedaron en estado «inactivo» (baja lógica en cascada), con su historial de telemetría, comandos y alertas.

b. Sus reglas de actuación quedaron en estado «inactiva».

c. El token del nodo central dejó de servir para comunicarse con el Sistema.

d. Las alertas activas originadas en el sistema IoT pasaron a «resuelta», y también la alerta «invernadero sin Técnico activo» del invernadero, si existía.

e. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sistema IoT y el cambio de estado, y otro por el nodo central, por cada hardware, por cada regla de actuación y por cada alerta que cambiaron de estado.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. La baja es definitiva: un sistema IoT dado de baja no se reactiva, ni tampoco su nodo central ni su hardware. Para suspender el sistema por un tiempo se usa IOT-DSC-SIS.

3. Si el invernadero vuelve a necesitar IoT, se registra un sistema nuevo con IOT-REG-SIS. La regla de un único sistema IoT por invernadero (R068) cuenta solo los sistemas que no están dados de baja. Los identificadores de los equipos dados de baja quedan libres: el sistema nuevo puede registrar equipos con los mismos identificadores, por ejemplo al reutilizar los mismos sensores físicos (regla 2 de IOT-ALT-HDW).

4. Si no se cumplen las precondiciones c o d, el Sistema no da de baja el sistema IoT e informa lo que lo impide, cada cosa con cómo resolverla: los comandos pendientes se cancelan uno por uno con IOT-CNL-CMD, o todos juntos desactivando el sistema (IOT-DSC-SIS); las órdenes de mantenimiento se concretan o se cancelan (Cancelar Orden).

5. La baja se puede hacer en cualquier momento, también con el invernadero activo, por ejemplo si se retira su infraestructura IoT.

6. Un invernadero con un sistema IoT activo o desconectado no se puede dar de baja: primero se da de baja su sistema IoT (PROD-BAJ-INV, precondición h).

7. Como el invernadero deja de tener sistema IoT, deja de necesitar un Técnico (PROD-ALT-INV, regla 5).

8. Antes de confirmar, el Sistema presenta lo que se dará de baja: el nodo central, cada equipo con su estado («activo» o «fuera de servicio»), de cada actuador su último estado informado por el nodo (regla 7 de IOT-BAJ-HDW) y cada regla de actuación activa, y advierte que la baja es definitiva. El actor confirma o cancela.

## Cómo se aplica en la ronda «IoT 1» (D-44, D-70, D-72)

Tareas: **IOT-02** (IOT-REG-SIS e IOT-MOD-SIS) e **IOT-06** (IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS). Modelo: `docs/modelo/iot.md`,
«SistemaIoT», «Hardware» y «NodoCentral». Decisiones de aplicación:

### Para los cinco

- **Alcance (regla 1 de IOT-DSC-SIS, regla «Alcance» de IOT-REG-SIS; MD-98).** Un único lugar, `iot/alcance.py` (D-28):
  - `invernaderos_que_opera(usuario)`: para un Agrónomo activo, los invernaderos activos a su cargo; para el Gerente activo, los
    invernaderos activos **sin Agrónomo activo** (sin asignar o con el asignado inactivo); para los demás, ninguno.
  - `invernaderos_que_consulta(usuario)`: el Agrónomo, los activos a su cargo; el Gerente, todos.
  - `puede_operar(usuario, invernadero) -> bool`, que los servicios vuelven a verificar **después de bloquear** el invernadero (si salió del
    alcance: extensión 8b de REG-SIS, con el motivo «Ya no operás el IoT de este invernadero: …»).
  Los otros roles reciben 403 en todo el módulo; un Gerente que mira un invernadero con Agrónomo activo ve todo en solo lectura, con el aviso
  del prototipo (`opBanner`).
- **Elección del invernadero.** Toda pantalla del módulo (salvo «Tipos de actuador») trabaja sobre un invernadero elegido en la barra de
  contexto (`ctxBar`): parámetro `?invernadero=<id>` en la URL, recordado en la sesión (`iot_invernadero`). Si no hay ninguno elegido, se toma
  el primero de `invernaderos_que_consulta` por nombre. Con un invernadero fuera del alcance, 404.
- **Conectividad (regla «Estado inicial, conectividad y modo» de REG-SIS; regla 3 de IOT-ACT-SIS).** No se guarda:
  `conectividad(nodo, ahora)` devuelve `en_linea` si `nodo.ultima_comunicacion` es más reciente que `minutos_sin_comunicacion`, y
  `sin_senal` si no; con `ultima_comunicacion` nula, `sin_senal` con el texto «Todavía no se comunicó». La actualiza la API (IOT-03).
- **Estado del IoT en la ficha del invernadero.** Punto de extensión nuevo en `maestros` (`docs/api/extensiones_de_maestros.md`, «Estado del
  IoT del invernadero»): `iot` registra `estados_de_sistemas(invernadero_ids)` y `url_de_registro(actor, invernadero)` con
  `registrar_estado_iot` (en `iot/servicios/sistemas.py`); `maestros` los consulta con `estados_iot(ids)`. Con él, `Invernadero.tiene_sistema_iot()` devuelve verdadero si hay un
  sistema activo o desconectado; la ficha muestra «Activo», «Desconectado» o «Sin registrar» con el enlace «Registrar sistema IoT» (solo a
  quien lo opera), y la lista, la marca «Con IoT».

### IOT-REG-SIS (IOT-02)

- **Flujo en tres pantallas, como el prototipo:** elegir invernadero (paso 2: los de `invernaderos_que_opera` sin sistema o con el sistema
  dado de baja, cada uno con su Técnico o «sin Técnico»), datos del nodo con el **resumen** (`resumen_de_registro(actor, datos)` valida todo
  sin escribir: pasos 5 y 6) y confirmación (`registrar_sistema_iot(actor, datos) -> (sistema, token)`: paso 8).
- **Precondición c.** Si no hay ningún insumo activo de la categoría `repuestos_de_hardware`, la pantalla no ofrece registrar y dice «Primero
  registrá en Compras e Inventario el insumo del nodo, en la categoría «Repuestos de hardware».», con el enlace al alta de insumo si el actor
  puede hacerla.
- **Datos (paso 5, regla «Datos del nodo central»).** Nombre y modelo obligatorios (hasta 60), número de serie opcional (hasta 60), fecha de
  instalación obligatoria y no posterior a hoy, insumo de `repuestos_de_hardware` activo (no hace falta que esté habilitado ni que tenga
  stock), rango de la solución opcional: los dos valores o ninguno, con un decimal y el mínimo menor que el máximo (6a). Mensajes por campo.
- **Registro (paso 8) en una transacción:** bloquear el invernadero con `bloquear_invernadero_activo` (si pasó a inactivo: 8b); verificar el
  alcance; verificar que no tiene un sistema no dado de baja (8a; además lo respalda el índice único parcial: un `IntegrityError` se traduce
  al mismo mensaje, nunca un 500); crear `SistemaIoT` (activo) y su `NodoCentral` (activo, modo `remoto`, sin sector); generar el token con
  `core.enlaces.nuevo_token()` y guardar solo `token_resumen` (D-70; si `core/enlaces.py` no existe todavía, lo crea esta tarea tal como lo
  describe `docs/patrones/enlace_del_cliente.md`, sección «Token»); llamar a `maestros.servicios.alertas.sincronizar_alertas_de_personal` (crea
  la alerta «invernadero sin Técnico activo» si corresponde: postcondición e) y auditar.
- **Mostrar el token una sola vez (pasos 9 y 10, extensión 9a).** La respuesta al POST que registra **renderiza** la pantalla del token (no
  redirige: el token no se guarda en ningún lado para mostrarlo después), con `never_cache` y `Cache-Control: no-store`. Muestra la dirección
  de la API (`request.build_absolute_uri("/api/iot/v1/")`), el token con «Copiar», el enlace a la guía de integración y la casilla «Ya
  guardé el token», que habilita «Cerrar» (como el prototipo, ventana `token`). Recargar la página no lo vuelve a mostrar.
- **La guía de integración del nodo.** Es el `README.md` de `docs/api/nodo/` (escrito en el lote I2a, D-74). El enlace apunta a su copia pública en GitHub:
  constante `URL_GUIA_DEL_NODO` en `iot/catalogo.py`
  (`https://github.com/infoponia/infoponia/blob/main/docs/api/nodo/README.md`). Hasta que exista el archivo, el enlace lleva a una página
  vacía: es esperado.
- **Después de registrar,** el sistema queda «sin señal» (todavía no se comunicó) y la pantalla ofrece «Registrar hardware» (IOT-ALT-HDW).
- **Auditoría (D-36).** `alta_sistema_iot`: afectados el sistema, el nodo y la alerta del Técnico si se creó. En `datos`, el invernadero, el
  nodo y el rango. **Nunca el token ni su resumen.**

### IOT-MOD-SIS (IOT-02)

- Se pueden cambiar el nombre, el modelo y el número de serie del nodo y el rango de la solución (regla 2 y 7), con las mismas validaciones
  del registro. Un sistema dado de baja no se modifica (404 desde la URL; sin botón).
- **Regenerar el token (postcondición b, reglas 3 y 4)** es una acción aparte, con su confirmación (ventana `regen` del prototipo: «El token
  actual deja de funcionar de inmediato…»). `regenerar_token(actor, sistema_id) -> token`: bloquea el sistema, reemplaza `token_resumen` y
  `token_generado_en`, y muestra el token nuevo una sola vez, igual que el registro.
- Bloqueos: el invernadero y después el sistema (`FOR NO KEY UPDATE`), releídos. Sin cambios no se escribe ni se audita.
- Auditoría: `modificacion_sistema_iot` (con «antes» y «después» del nodo y del rango) y `regeneracion_token_iot` (sin token).

### IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06)

- **Desactivar.** Estado `desconectado`; cancela los comandos pendientes de sus actuadores con la función de cancelación de IOT-05
  (`cancelar_comando_incluido`, sin el aviso al actor) y resuelve todas las alertas activas con `AlertaIot.sistema` = ese sistema
  (`resolver_alerta_de_estado`). No toca el hardware, las reglas ni las órdenes de mantenimiento (regla 5). Mientras está desconectado, la
  API responde «sistema desconectado» (IOT-ENT-INF, \*a) y la revisión periódica lo saltea.
- **Activar.** Precondición b: el invernadero activo. Estado `activo`; todas las reglas activas del sistema vuelven a `ultima_evaluacion =
  sin_evaluar` y `contador_confirmacion = 0` (regla 4; regla «Disparo de una regla» de IOT-ENT-INF).
- **Baja.**
  - Antes de confirmar, la ventana muestra lo que se da de baja (regla 8: el nodo, cada equipo con su estado, el último estado informado de
    cada actuador y cada regla activa) y advierte que es definitiva.
  - Precondiciones c y d: comandos pendientes y órdenes de mantenimiento a realizar. Si hay, no deja confirmar e informa cómo resolverlo
    (regla 4). **Las órdenes se completan en IOT-07:** hasta entonces, la función `ordenes_a_realizar_del_sistema(sistema)` devuelve una
    lista vacía. El texto del impedimento, en `mantenimiento_automatico.md`, «Lecturas».
  - En una transacción, con el invernadero, el sistema y su hardware bloqueados: el sistema, el nodo y todo el hardware pasan a `inactivo`
    con `fecha_baja` = hoy; `token_resumen` pasa a nulo (el token deja de servir: postcondición c); las reglas activas pasan a `inactiva`; se
    resuelven las alertas activas del sistema; y se llama a `sincronizar_alertas_de_personal` (sin sistema IoT, el invernadero deja de
    necesitar Técnico: postcondición d y regla 7).
- **Auditoría:** `desactivacion_sistema_iot`, `activacion_sistema_iot` y `baja_sistema_iot`; cada uno con los comandos, las alertas, los
  equipos y las reglas afectados (un registro por caso de uso, D-36).

## Pantallas

Guía visual: `docs/prototipos/iot/`. Buscá la función y leé solo esa parte.

| Pantalla | Función en el prototipo | Casos de uso | Tarea |
|---|---|---|---|
| IoT · pestaña «Sistema IoT» (ficha del nodo, o «no tiene Sistema IoT») | `sistema` (rama final), `sysEstB`, `opBanner` | Consulta, botones de MOD, DSC, ACT y BAJ | IOT-02 (los botones de IOT-06, en IOT-06) |
| Registrar y modificar | `sistema` (rama `sys-form`), `act` (`open-sys-form`, `save-sys`) | IOT-REG-SIS, IOT-MOD-SIS | IOT-02 |
| El token, una sola vez | `modalHtml` (`token`), `newTok` | IOT-REG-SIS, IOT-MOD-SIS | IOT-02 |
| Regenerar el token | `modalHtml` (`regen`) | IOT-MOD-SIS | IOT-02 |
| Desconectar | `modalHtml` (`desc`) | IOT-DSC-SIS | IOT-06 |
| Activar | botón «Activar» de `sistema`, `act` (`sys-activar`) | IOT-ACT-SIS | IOT-06 |
| Dar de baja | `modalHtml` (`baj` sin id) | IOT-BAJ-SIS | IOT-06 |

**Lo que difiere del prototipo (manda el CU, L7):**

- El prototipo registra en una sola pantalla: el CU pide elegir el invernadero (paso 2) y un **resumen** antes de confirmar (paso 6). La
  elección del invernadero se hace con la barra de contexto; el resumen va como un paso «Revisar» antes de «Registrar y generar token».
- El prototipo no muestra el aviso de la extensión 6b en el resumen con el texto completo: «Se generará para el Gerente la alerta
  «invernadero sin Técnico activo». Nadie podrá concretar los mantenimientos del hardware hasta que se asigne uno.».
- El botón «Guía de integración del nodo» del prototipo muestra un aviso con `docs/api_nodo.md`: es un enlace a `docs/api/nodo/README.md`.
- La fecha máxima fija (`max="2026-11-19"`) del prototipo es la de hoy.

## Para más adelante

En `docs/disparadores.md`, «Cuando existan actuadores, comandos y reglas del IoT»: las órdenes de mantenimiento que impiden la baja
(IOT-07).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`, «Solo prototipo». En estas pantallas, además: la caja «SOLO PROTOTIPO · simula lo que informa el
nodo» (`sim-modo`); el modo lo informa el nodo por la API (IOT-03).
