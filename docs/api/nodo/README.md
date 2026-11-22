# Guía de integración del nodo central con InfoPonia (API v1)

Para quien configura el nodo central de un invernadero (el Técnico de la organización o quien instala el hardware). Explica cómo debe
comportarse el nodo para mandarle a InfoPonia las lecturas de los sensores y el estado de los equipos. Es la misma para todas las
organizaciones: cada una la implementa en su propio nodo (IOT-REG-SIS, regla «Guía de integración del nodo»).

La implementación de referencia es un flujo de **Node-RED**: `node-red/` (D-70, punto 6). Si tu nodo ya usa Node-RED con un broker MQTT,
podés partir de ese flujo y cambiar los equipos simulados por nodos «mqtt in».

| Documento | Para qué |
|---|---|
| Esta guía | Cómo se comporta el nodo: qué manda, cuándo, qué hace con las respuestas |
| `mensajes.md` | Cada ruta: el pedido, la respuesta y sus campos |
| `respuestas_y_errores.md` | El token, los límites, los códigos HTTP y los motivos de rechazo |
| `ejemplos/` | Pedidos y respuestas completos en JSON (las pruebas de InfoPonia los usan) |
| `node-red/` | Los flujos de referencia (lecturas y comandos) y cómo correrlos |
| `escenarios.md` | Las situaciones que se prueban de punta a punta con Node-RED (también, el guion de la defensa) |

Versión **v1**: lecturas, estados, modo y anuncio (21/11/2026, D-74); comandos (22/11/2026, D-77).

## 1. Qué necesitás de InfoPonia

Al registrar el sistema IoT del invernadero (IoT · Sistema IoT · «Registrar sistema IoT»), InfoPonia muestra **una sola vez**:

- la **dirección de la API**, terminada en `/api/iot/v1/` (siempre `https://`);
- el **token** del nodo. Guardalo como un secreto: en Node-RED, en una variable de entorno, nunca en el flujo exportado ni en un registro.
  Si se pierde o se filtra, se regenera desde «Modificar sistema IoT» y el anterior deja de servir;
- y el enlace a esta guía.

Además, cada sensor y cada actuador se registra en InfoPonia (IoT · Hardware) con su **identificador**: el texto con el que el nodo lo
nombra en sus mensajes (un tópico MQTT, un número de serie…). InfoPonia no lo interpreta, solo lo compara sin distinguir mayúsculas. Hasta
64 caracteres entre letras, números, `-`, `_`, `.` y `/`, sin espacios. Si el nodo manda un identificador que no está registrado, InfoPonia
rechaza el mensaje y genera la alerta «dispositivo no registrado», desde la que se puede registrar el equipo.

## 2. El formato unificado

Cada sensor mide **una sola variable, en su unidad fija**. Si un aparato mide dos cosas, se registra como dos sensores con dos
identificadores.

| Variable | Unidad | Valor que manda el nodo |
|---|---|---|
| Temperatura | °C | número |
| Humedad | % HR | número |
| Intensidad lumínica | lux | número |
| Temperatura de la solución | °C | número |
| Nivel de la solución | — | `"normal"` o `"bajo"` |

La conversión desde lo que mande cada equipo (otra unidad, un valor crudo, un 0 o un 1 de un flotante) se hace **en el nodo**, antes de
enviar. InfoPonia no convierte unidades. El fotoperíodo no se manda: InfoPonia lo calcula con las lecturas de intensidad lumínica.

## 3. Qué manda el nodo y cuándo (D-74, puntos 1 y 4)

| Mensaje | Ruta | Cuándo |
|---|---|---|
| Lecturas | `POST lecturas` | **Un lote cada 60 segundos** con la última lectura de cada sensor. Si no hay lecturas, el lote vacío (`{"lecturas": []}`) igual se manda: es el latido que mantiene al nodo «en línea» |
| Estados | `POST estados` | Al arrancar (el estado de todos los equipos que conozca) y cada vez que un equipo cambia: se conecta, se desconecta, falla o un actuador cambia de estado |
| Modo | `POST modo` | Al arrancar y cada vez que pasa de `remoto` a `local` o al revés |
| Anuncio | `POST anuncio` | Al arrancar, cada vez que se agregan o se quitan equipos del nodo y una vez cada 24 horas |
| Retiro de comandos | `GET comandos` | **Cada 5 segundos** (sección 10). También mantiene al nodo «en línea» |
| Resultado de un comando | `POST comandos/<id>/resultado` | Apenas ejecuta, intenta sin éxito o rechaza cada comando entregado |

Todo es optativo salvo las lecturas: un nodo que solo manda lecturas funciona. Sin estados, InfoPonia no conoce el estado de los
actuadores («desconocido»); sin modo, lo considera `remoto`; sin anuncio, no puede verificar si los actuadores soportan las acciones de su
tipo («sin verificar»).

Si InfoPonia no recibe ningún mensaje del nodo durante los minutos sin comunicación de su Configuración Operativa (inicial, 3 minutos),
genera la alerta crítica «nodo sin comunicación». Con un lote cada 60 segundos hay margen para un par de fallas seguidas.

## 4. Las respuestas, los reintentos y la cola (D-74, punto 3)

InfoPonia responde cada pedido. Lo que hace el nodo depende de la respuesta:

1. **200: el mensaje se aceptó.** Dentro vienen los resultados de cada lectura o estado: `aceptada`, `duplicada` (ya la tenía: también es
   un éxito) o `rechazada` con un `motivo`. **Una lectura rechazada se descarta**: su motivo (equipo no registrado, fecha futura, valor
   inválido…) no cambia por reintentarla. Revisá el motivo y corregí la configuración del nodo o el registro del equipo.
2. **400, 401, 403, 404, 405, 413 o 415: el mensaje entero se rechazó.** No lo reintentes: repetirlo da el mismo error. Dejá constancia en
   el registro del nodo y seguí con los mensajes nuevos. Un 401 es un token incorrecto o regenerado; un 403, un sistema IoT desconectado en
   InfoPonia.
3. **429, 5xx, sin respuesta o error de red: falla pasajera.** Guardá el mensaje y reintentá:
   - con 429, después de los segundos que indica el encabezado `Retry-After`;
   - si no, con espera creciente: 10 s, 20 s, 40 s… hasta 5 minutos entre intentos.

**La cola.** Las lecturas que no se pudieron enviar se guardan en una cola local, **en el orden en que se midieron**, hasta **1 hora** de
lecturas; si se llena, se descarta lo más viejo. Al volver la comunicación, se manda primero lo más viejo, en lotes de hasta 500 lecturas,
sin pasar de 120 pedidos por minuto. Los estados y el modo se mandan también en orden: InfoPonia aplica el último que recibe.

Las lecturas que llegan tarde se guardan y cuentan para el historial, pero InfoPonia no genera alertas con ellas si se midieron hace más
que la antigüedad máxima de su Configuración Operativa (inicial, 5 minutos): describen algo que ya pasó.

**Reenviar es seguro** (D-74, punto 6). Si se perdió una respuesta y el nodo reenvía un lote, InfoPonia reconoce las lecturas que ya tenía
(mismo sensor y misma fecha de medición) y las responde `duplicada`, sin duplicar nada. Por eso **una lectura encolada siempre lleva su
fecha de medición**.

## 5. El reloj (D-74, punto 5)

- Sincronizá el reloj del nodo (NTP). Las fechas van en ISO 8601 **con zona horaria**: `2026-11-21T14:03:00-03:00` o
  `2026-11-21T17:03:00Z`. Una fecha sin zona se rechaza (`fecha_invalida`).
- Cada respuesta de InfoPonia trae `servidor_en`, su hora en UTC. Si la diferencia con el reloj del nodo pasa de **2 minutos**, tratá al
  reloj como no sincronizado hasta corregirlo.
- **Sin reloj sincronizado:** mandá las lecturas **sin** `medida_en` (InfoPonia usa la hora en que las recibe) y **no las guardes en la
  cola**: si el envío falla, descartalas. Una lectura vieja sin fecha se tomaría como recién medida.
- Una fecha más de 5 minutos adelantada respecto de InfoPonia se rechaza (`fecha_futura`).

## 6. Modo local

Si el nodo no logra comunicarse con InfoPonia, **actúa por su cuenta** con su propia lógica de control (por ejemplo, encender el
ventilador si la temperatura sube) y pasa a modo `local`. Cuando InfoPonia vuelve a responder, el nodo informa el modo (`local` mientras
siga controlando él, `remoto` cuando devuelve el control) y el estado actual de sus actuadores.

En modo `local`, InfoPonia supervisa (registra lecturas y estados y genera alertas) pero no evalúa sus reglas de actuación ni entrega
comandos, para no contradecir el control local. Al volver a `remoto`, las reglas empiezan de cero.

## 7. Seguridad

- Siempre `https://`. Nunca mandes el token por `http://`.
- El token va solo en el encabezado `Authorization: Bearer <token>` de cada pedido. No lo pongas en la dirección, en el cuerpo, en el flujo
  exportado ni en los registros del nodo.
- Si sospechás que el token se filtró, regeneralo en InfoPonia y cargá el nuevo en el nodo.

## 8. Obligaciones del nodo (resumen)

1. Identificarse con el token en cada pedido, por HTTPS.
2. Mandar cada sensor con su identificador registrado, en el formato unificado.
3. Mandar lecturas al menos una vez por minuto (o el latido).
4. Sincronizar el reloj y mandar las fechas con zona; sin reloj, omitirlas y no encolar.
5. Reintentar solo las fallas pasajeras, con espera creciente y una cola en orden de hasta 1 hora.
6. Informar el modo y el estado de los actuadores al arrancar y cuando cambian.
7. Anunciar sus equipos y los comandos que soporta cada actuador.
8. Actuar en forma local si no logra comunicarse con InfoPonia.
9. Consultar sus comandos cada 5 segundos, ejecutarlos, informar cada resultado y **no repetir un comando ya ejecutado**: recordar
   durante 24 horas cada comando ejecutado o rechazado, con su resultado (sección 10).
10. Respetar en forma local el tiempo mínimo entre comandos de cada tipo de actuador (lo informa el Técnico al configurarlo).

## 9. Catálogo de comandos (para el anuncio)

Es parte del contrato (IOT-ALT-TAC, regla 7): solo cambia con una versión nueva de la API.

| Comando | Capacidad | Lleva valor | Estado que deja |
|---|---|---|---|
| `ENCENDER` | encendido | no | `encendido` |
| `APAGAR` | encendido | no | `apagado` |
| `FIJAR_NIVEL` | nivel | sí (entero) | `nivel:<n>` |
| `ABRIR` | posición | no | `abierto` |
| `CERRAR` | posición | no | `cerrado` |
| `FIJAR_POSICION` | posición | sí (entero) | `posicion:<n>` |

## 10. Comandos (D-77)

InfoPonia no se conecta al nodo: el nodo **pide** sus comandos. El ciclo:

1. **Cada 5 segundos**, `GET comandos`. La respuesta trae los comandos disponibles (puede venir vacía) y el `modo` que InfoPonia tiene
   registrado (`mensajes.md`, sección 5).
2. **Por cada comando:**
   - si su `id` está en la memoria del nodo (ya lo ejecutó o lo rechazó en las últimas 24 horas), **no lo ejecuta otra vez**: manda de
     nuevo el resultado guardado;
   - si el comando no es del catálogo o el actuador no lo soporta, lo **rechaza** (`resultado: "rechazado"`): InfoPonia no lo reintenta y
     marca la acción como incompatible;
   - si no, lo ejecuta y manda `ejecutado` (con el `estado` en que quedó el actuador, si lo sabe) o `fallo` (con el error en `detalle`).
     **Una acción que no cambia nada** (encender lo que ya estaba encendido) se informa igual como `ejecutado`.
3. **Guarda en su memoria** el `id` y el resultado durante 24 horas.
4. **El resultado** se manda apenas se tiene, dentro de los `espera_segundos` del comando. Si el envío falla por una falla pasajera, se
   reintenta como las lecturas (sección 4). Pasada la espera, InfoPonia cuenta el intento como «sin respuesta» y vuelve a entregar el
   comando en un retiro siguiente, pero sigue aceptando el resultado mientras el comando esté pendiente.
5. Una respuesta `ya_resuelto` es un éxito: InfoPonia ya tenía ese resultado (o el comando se canceló). Un 404 `comando_inexistente` se
   descarta.

**Intentos.** InfoPonia intenta cada comando hasta 1 + los reintentos de su Configuración Operativa (inicial, 4 intentos), con el intervalo
de reintento entre uno y otro (inicial, 60 s). Si se agotan, el actuador pasa a «fuera de servicio» y se genera la alerta crítica «comando
fallido». **Un intento que vence mientras el nodo no se comunica no cuenta**: una caída del nodo no deja actuadores fuera de servicio.

**Modo local.** En modo `local`, el retiro viene siempre vacío y los comandos esperan sin consumir intentos hasta que el nodo vuelva a
`remoto` (sección 6). El nodo sigue consultando cada 5 segundos: así sigue «en línea».
