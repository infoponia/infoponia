# Contrato del nodo v1 · Token, límites, códigos HTTP y motivos de rechazo

Parte del contrato entre InfoPonia y el nodo central (D-70, D-74, D-77). Vale para todas las rutas de `mensajes.md`. Versión **v1**: lote I2a
(21/11/2026) y los comandos del lote I3 (22/11/2026).

## 1. Token: el encabezado `Authorization`

- Cada pedido lleva el token del sistema IoT en el encabezado `Authorization: Bearer <token>` (D-70, punto 3). El token se muestra una sola
  vez al registrar el sistema IoT o al regenerarlo (IOT-REG-SIS, IOT-MOD-SIS) y lo carga el Técnico en el nodo.
- InfoPonia guarda solo el resumen SHA-256 del token y busca el sistema por ese resumen: el token **nunca** queda en la base, en la
  auditoría ni en los registros de errores. El nodo tampoco lo escribe en sus registros.
- El token autoriza **solo** a ese nodo a comunicarse con la API: no da acceso a pantallas ni a datos de otros invernaderos. La API no usa
  sesión ni cookies, y no tiene protección CSRF (es para formularios del navegador).
- Regenerar el token (IOT-MOD-SIS) invalida el anterior de inmediato: el nodo recibe 401 hasta que se le cargue el nuevo. Dar de baja el
  sistema IoT borra el resumen: el token deja de servir para siempre.
- Toda comunicación va por **HTTPS** (SEG-16). La dirección de la API es la que muestra InfoPonia junto al token, terminada en
  `/api/iot/v1/`.

## 2. Límites (D-70, punto 5)

| Límite | Valor v1 | Si se excede |
|---|---|---|
| Pedidos por minuto, por nodo | 120 | 429 `demasiados_pedidos`, con `Retry-After` |
| Tamaño del cuerpo | 256 KB (262.144 bytes) | 413 `mensaje_demasiado_grande` |
| Elementos por pedido (lecturas, estados o equipos) | 500 | 413 `demasiados_elementos` |

- El contador es por nodo (por el resumen del token), en ventanas fijas de un minuto de reloj (de `hh:mm:00` a `hh:mm:59`). Cuenta **todo
  pedido que trae un token**, aceptado o no (D-74, punto 8). `Retry-After` dice cuántos segundos faltan para la ventana siguiente.
- Lo que excede un límite se rechaza **sin procesar nada**.
- Los números son del contrato y se pueden ajustar acá (y en la constante del código, `iot/api/limites.py`) sin cambiar de versión.

## 3. Códigos HTTP

Orden en que InfoPonia verifica un pedido. La primera verificación que falla da la respuesta; las siguientes no se hacen.

| Orden | Verificación | Código | `error` |
|---|---|---|---|
| 1 | La ruta existe bajo `/api/iot/v1/` | 404 | `ruta_inexistente` |
| 2 | El método es el de la ruta (`POST`; `GET` en el retiro de comandos) | 405 | `metodo_no_permitido` (con el encabezado `Allow`) |
| 3 | Hay un encabezado `Authorization: Bearer <token>` con algo después de `Bearer` | 401 | `token_ausente` |
| 4 | El nodo no superó los pedidos por minuto | 429 | `demasiados_pedidos` |
| 5 | El token es el de un sistema IoT no dado de baja | 401 | `token_invalido` |
| 6 | El sistema IoT está activo (no «desconectado») | 403 | `sistema_desconectado` |
| 7 | El cuerpo pesa hasta 256 KB | 413 | `mensaje_demasiado_grande` |
| 8 | `Content-Type` es `application/json` (con `charset=utf-8` o sin él) | 415 | `tipo_no_soportado` |
| 9 | El cuerpo es JSON válido en UTF-8 y es un objeto | 400 | `json_invalido` |
| 10 | El objeto tiene exactamente la forma del mensaje (sección 0 de `mensajes.md`); el anuncio, además, cada equipo | 400 | `mensaje_mal_formado` (con `campo` y, si es de un elemento, `indice`) |
| 11 | La lista tiene hasta 500 elementos | 413 | `demasiados_elementos` |
| 12 | En el resultado de un comando: el comando existe, es de un actuador del nodo y ya se le entregó alguna vez | 404 | `comando_inexistente` |
| — | Todo bien: se registra la comunicación y se procesa cada elemento | 200 | — (los rechazos de cada elemento van en `resultados`) |
| — | Falla inesperada de InfoPonia antes de responder | 500 | `error_interno` |

El retiro de comandos (`GET`, sin cuerpo) salta las verificaciones 7 a 11. Las respuestas 401 llevan además `WWW-Authenticate: Bearer`. Un token mal formado (por ejemplo, con espacios) es `token_invalido`, no
`token_ausente`.

**Cuerpo de un error** (todas las respuestas que no son 200):

```json
{
  "version": "v1",
  "servidor_en": "2026-11-21T17:05:00Z",
  "error": "mensaje_mal_formado",
  "detalle": "equipos[1].comandos: «GIRAR» no está en el catálogo de comandos.",
  "campo": "equipos[1].comandos",
  "indice": 1
}
```

`campo` e `indice` van solo en `mensaje_mal_formado`. `detalle` es para la persona que configura el nodo; el nodo decide por `error` y por
el código HTTP, nunca por el texto. Un 502, 503 o 504 puede venir del proveedor (Render, por ejemplo mientras el servicio arranca), sin este
cuerpo: el nodo lo trata como cualquier falla pasajera.

### Qué hace el nodo con cada código (D-74, punto 3)

| Código | Tipo | El nodo |
|---|---|---|
| 200 | aceptado | Saca el mensaje de la cola. Descarta las lecturas o estados `rechazada`/`rechazado` (su motivo es permanente) y da por recibidas las `duplicada` |
| 200 con `ya_resuelto` (resultado de un comando) | aceptado | Saca el resultado de su cola: InfoPonia ya lo tenía (D-77, punto 2) |
| 400, 401, 403, 404, 405, 413, 415 | mensaje rechazado | **No lo reintenta.** Lo saca de la cola y lo informa en su registro. 401 y 403 piden que alguien revise el token o el estado del sistema IoT en InfoPonia; 404 `comando_inexistente`, que el `id` no es de este nodo |
| 429 | falla pasajera | Lo deja en la cola y reintenta después de `Retry-After` |
| 500, 502, 503, 504, sin respuesta o error de red | falla pasajera | Lo deja en la cola y reintenta con espera creciente: 10 s, 20 s, 40 s… hasta 5 minutos |

Un 413 `demasiados_elementos` no debería pasar nunca si el nodo arma lotes de hasta 500; si pasa, el nodo parte el lote.

## 4. Motivos de rechazo de una lectura o un estado

Van en `resultados[].motivo` dentro de una respuesta 200. Ninguno se arregla reintentando: el nodo descarta el elemento.

| `motivo` | En | Cuándo | Qué hace InfoPonia además | Caso de uso |
|---|---|---|---|---|
| `mal_formada` | lectura, estado | No es un objeto; falta `identificador`, `valor` o `estado`; el identificador no tiene la forma de la regla 2 de IOT-ALT-HDW; trae un campo desconocido | Lo deja en el registro técnico de errores | D-74 punto 7; D-75 punto 5 |
| `equipo_no_registrado` | lectura, estado | El identificador no es de ningún equipo del sistema IoT | Genera la alerta «dispositivo no registrado» si no la había para ese identificador | Extensión 3a |
| `equipo_dado_de_baja` | lectura, estado | El identificador es de un equipo dado de baja del sistema (y de ninguno vigente) | Ídem; la alerta indica de qué equipo era | Extensión 3a |
| `no_es_sensor` | lectura | El identificador es de un actuador | Registro técnico de errores | Extensión 3b |
| `fecha_invalida` | lectura, estado | `medida_en` o `informado_en` no es una fecha ISO 8601 o no tiene zona horaria | Registro técnico de errores | D-74 punto 5 |
| `fecha_futura` | lectura, estado | La fecha es más de 5 minutos posterior a `servidor_en` | Registro técnico de errores | Extensión 3d |
| `valor_invalido` | lectura | En el nivel de la solución, un valor que no es `"normal"` ni `"bajo"`; en otra variable, un valor que no es un número JSON o pasa de 9.999.999,99 | Registro técnico de errores | Extensión 4c; D-74 punto 7 |
| `estado_invalido` | estado | Un `estado` que no está en la tabla de `mensajes.md`, sección 2, o un estado operativo informado para un sensor | Registro técnico de errores | D-75 punto 6 |
| `sistema_desconectado` | lectura, estado | El sistema IoT se desconectó mientras se procesaba el pedido (los elementos ya procesados quedan) | — | Extensión \*a |
| `error_interno` | lectura, estado | Falla inesperada al procesar ese elemento; los demás se procesan igual | Lo deja en el registro técnico de errores con el detalle | Garantías mínimas |

El «registro técnico de errores» es el registro de Python (`logging`, registrador `iot.api`) que ve quien administra el servidor. Guarda el
sistema, el identificador, el motivo y, si sirve, el valor recibido; **nunca el token**.

## 4b. Textos de `detalle`

Son los textos del sistema; los ejemplos los usan tal cual y las pruebas los comparan (`ejemplos/README.md`). Entre llaves, lo que se
completa; `{id}` es el identificador tal como lo mandó el nodo.

**De un elemento** (`resultados[].detalle`):

| `motivo` | Texto |
|---|---|
| `mal_formada` | «No tiene la forma del contrato: {razón}.» Razones: «no es un objeto», «falta «identificador»», «falta «valor»», «falta «estado»», «el campo «{campo}» no existe», «el identificador tiene más de 64 caracteres o caracteres no permitidos» |
| `equipo_no_registrado` | ««{id}» no es un equipo registrado de este sistema IoT.» |
| `equipo_dado_de_baja` | ««{id}» era de un equipo dado de baja de este sistema IoT.» |
| `no_es_sensor` | ««{id}» es un actuador: las lecturas son solo de sensores.» |
| `fecha_invalida` | ««{texto}» no es una fecha ISO 8601 con zona horaria.» (si no es texto: «La fecha tiene que ser un texto ISO 8601 con zona horaria.») |
| `fecha_futura` | «La fecha {texto} es más de 5 minutos posterior a la hora de InfoPonia.» |
| `valor_invalido` | Nivel: «El nivel de la solución solo admite «normal» o «bajo».» · Otra variable, no numérico: «El valor tiene que ser un número.» · Muy grande: «El valor pasa del máximo admitido (9.999.999,99).» |
| `estado_invalido` | ««{estado}» no es un estado del contrato.» · Operativo en un sensor: ««{estado}» es un estado de actuador y «{id}» es un sensor.» |
| `sistema_desconectado` | «El sistema IoT se desconectó mientras se procesaba el pedido.» |
| `error_interno` | «InfoPonia no pudo procesar este elemento; los demás se procesaron.» |

**Del mensaje** (`detalle` de una respuesta que no es 200):

| `error` | Texto |
|---|---|
| `ruta_inexistente` | «La ruta no existe en la API v1.» |
| `metodo_no_permitido` | «Esta ruta solo acepta POST.» (en el retiro de comandos: «Esta ruta solo acepta GET.») |
| `token_ausente` | «Falta el encabezado «Authorization: Bearer <token>».» |
| `token_invalido` | «El token no corresponde a ningún sistema IoT vigente.» |
| `demasiados_pedidos` | «Se superaron los 120 pedidos por minuto. Reintentá en {n} segundos.» |
| `sistema_desconectado` | «El sistema IoT de este nodo está desconectado en InfoPonia.» |
| `mensaje_demasiado_grande` | «El cuerpo pesa más de 256 KB.» |
| `tipo_no_soportado` | «El cuerpo tiene que ser JSON (Content-Type: application/json).» |
| `json_invalido` | «El cuerpo no es un objeto JSON válido en UTF-8.» |
| `mensaje_mal_formado` | «{campo}: {razón}.» Razones: «falta», «no existe en este mensaje», «tiene que ser una lista», «tiene que ser un objeto», «tiene que ser «remoto» o «local»», «tiene que ser «sensor» o «actuador»», ««{código}» no está en el catálogo de comandos», «un sensor no lleva comandos», «el comando «{código}» se repite», «el identificador «{id}» se repite en el anuncio», «el identificador tiene más de 64 caracteres o caracteres no permitidos», «tiene que ser «ejecutado», «fallo» o «rechazado»», «tiene más de 300 caracteres», «no es un estado operativo de un actuador» |
| `demasiados_elementos` | «El pedido trae {n} elementos; el máximo es 500.» |
| `comando_inexistente` | «El comando {id} no existe o no es de un actuador de este nodo.» |
| `error_interno` | «InfoPonia no pudo procesar el pedido. Reintentá más tarde.» |

## 5. Versiones

- `v1` está en la ruta. Agregar una ruta, un campo optativo **en las respuestas** o un motivo nuevo no cambia de versión: el nodo ignora lo
  que no conoce en una respuesta.
- Agregar o cambiar un campo de un **pedido**, cambiar un código o el significado de un motivo es una versión nueva (`/api/iot/v2/`), y la
  anterior sigue funcionando mientras haya nodos que la usen.
