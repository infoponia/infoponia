# Contrato del nodo v1 · Mensajes

Parte del contrato entre InfoPonia y el nodo central de un invernadero (D-70, D-74). Este archivo fija **qué manda el nodo y qué le
responde InfoPonia** en cada ruta. Las reglas comunes a todas las rutas (token, límites, códigos HTTP y motivos de rechazo) están en
`respuestas_y_errores.md`; cómo debe comportarse el nodo, en `README.md` (la guía). Ejemplos completos: `ejemplos/`.

El contrato es de InfoPonia: si cambia, se cambia primero este documento y después el código (D-70, punto 1). Un cambio que rompe a los
nodos existentes es una versión nueva (`/api/iot/v2/`).

Versión: **v1**: lecturas, estados, modo y anuncio (lote I2a, 21/11/2026; D-74); retiro y resultado de comandos (lote I3, 22/11/2026; D-77).

## Índice

| Ruta | Mensaje | Caso de uso | Sección |
|---|---|---|---|
| `POST /api/iot/v1/lecturas` | Lecturas de los sensores, en lote (también el latido) | IOT-ENT-INF, pasos 1 a 7 | 1 |
| `POST /api/iot/v1/estados` | Estados de los equipos: conectividad, falla y estado operativo de los actuadores | IOT-ENT-INF, extensión 1a | 2 |
| `POST /api/iot/v1/modo` | Modo del nodo: remoto o local | IOT-ENT-INF, extensión 1b | 3 |
| `POST /api/iot/v1/anuncio` | Anuncio de los equipos del nodo y de los comandos que soporta cada actuador | IOT-ENT-INF, extensión 1c | 4 |
| `GET /api/iot/v1/comandos` | Retiro de los comandos disponibles | IOT-RSV-CMD, pasos 1 y 2, extensiones 2a a 2d | 5 |
| `POST /api/iot/v1/comandos/<id>/resultado` | Resultado de un comando | IOT-RSV-CMD, pasos 4 a 6, extensiones 4a a 4f | 6 |

## 0. Convenciones de todos los mensajes

- **Cuerpo:** un objeto JSON en UTF-8, con `Content-Type: application/json` (salvo el retiro de comandos, que es un `GET` sin cuerpo). Toda ruta lleva el token (`respuestas_y_errores.md`, sección 1).
- **Nombres de los campos:** en español y en snake_case. **Un campo que el contrato no define se rechaza** (D-74, punto 7): en un
  elemento de una lista, rechaza ese elemento (`mal_formada`); en el objeto de arriba, el mensaje entero (400).
- **Identificador de un equipo** (`identificador`): el texto con el que el nodo nombra al sensor o al actuador, el mismo que se cargó al
  registrarlo (regla 2 de IOT-ALT-HDW): hasta 64 caracteres entre letras, números, `-`, `_`, `.` y `/`, sin espacios. Se compara **sin
  distinguir mayúsculas** y sin los espacios del borde. El nodo central no tiene identificador: se identifica con el token.
- **Fechas** (`medida_en`, `informado_en`): texto ISO 8601 **con zona horaria**, por ejemplo `2026-11-21T14:03:00-03:00` o
  `2026-11-21T17:03:00Z`. Se aceptan fracciones de segundo. Son optativas: si el reloj del nodo no está sincronizado, se omiten
  (`README.md`, «Reloj»). Una fecha sin zona o mal escrita rechaza el elemento con `fecha_invalida`; una fecha más de 5 minutos posterior a la
  hora de InfoPonia, con `fecha_futura`.
- **Números:** número JSON (`24.5`), no texto (`"24.5"`). InfoPonia los guarda con dos decimales (redondeo al más cercano; el medio, hacia
  arriba). `NaN` e `Infinity` no son JSON válido.
- **Toda respuesta** trae `version` (`"v1"`) y `servidor_en` (la hora de InfoPonia al recibir el pedido, en UTC, con `Z`). El nodo la usa
  para comprobar su reloj.
- **Listas:** hasta 500 elementos por pedido (D-70, punto 5). Los resultados vuelven **en el mismo orden**, con su `indice` (desde 0).

## 1. Lecturas — `POST /api/iot/v1/lecturas`

El nodo manda, una vez por ciclo, las lecturas de todos sus sensores (D-74, punto 1). Un lote vacío es un **latido**: el nodo sigue «en
línea» aunque no tenga lecturas para mandar.

### Pedido

```json
{
  "lecturas": [
    { "identificador": "norte/sectorA/temperatura", "valor": 24.5, "medida_en": "2026-11-21T14:04:30-03:00" },
    { "identificador": "norte/tanque1/nivel", "valor": "normal", "medida_en": "2026-11-21T14:04:30-03:00" }
  ]
}
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `lecturas` | lista de 0 a 500 objetos | sí | Única clave del objeto |
| `lecturas[].identificador` | texto | sí | El de un **sensor** registrado del sistema |
| `lecturas[].valor` | número; o `"normal"` / `"bajo"` | sí | En la unidad del sensor: °C, % HR, lux, °C (solución). El nivel de la solución, solo `"normal"` o `"bajo"`. Hasta 9.999.999,99 en valor absoluto |
| `lecturas[].medida_en` | texto (fecha con zona) | no | La de medición. Si falta, InfoPonia usa la de recepción (extensión 3e) |

**Formato unificado** (regla de IOT-ENT-INF): cada sensor mide una sola variable, en su unidad fija. Lo que mande el equipo físico se
traduce a este formato **en el nodo**, antes de enviarlo. InfoPonia no convierte unidades.

### Respuesta 200

```json
{
  "version": "v1",
  "servidor_en": "2026-11-21T17:05:00Z",
  "aceptadas": 1,
  "duplicadas": 0,
  "rechazadas": 1,
  "resultados": [
    { "indice": 0, "identificador": "norte/sectorA/temperatura", "resultado": "aceptada", "valida": true, "atrasada": false },
    { "indice": 1, "identificador": "norte/sectorB/co2", "resultado": "rechazada", "motivo": "equipo_no_registrado",
      "detalle": "«norte/sectorB/co2» no es un equipo registrado de este sistema IoT." }
  ]
}
```

| Campo | Cuándo | Qué es |
|---|---|---|
| `aceptadas`, `duplicadas`, `rechazadas` | siempre | Cuántas hubo de cada resultado. Suman la cantidad de lecturas del pedido |
| `resultados[].indice` | siempre | La posición de la lectura en el pedido |
| `resultados[].identificador` | siempre | El que mandó el nodo, tal cual; `null` si no vino o no era texto |
| `resultados[].resultado` | siempre | `aceptada` (se guardó), `duplicada` (ya estaba guardada: no se procesó de nuevo) o `rechazada` |
| `resultados[].valida` | en una `aceptada` de un sensor numérico | `false` si el valor está fuera del rango de calibración del sensor (lectura inválida) |
| `resultados[].atrasada` | en una `aceptada` | `true` si se midió hace más que la antigüedad máxima de la Configuración Operativa (inicial, 5 minutos): se guarda pero no genera alertas |
| `resultados[].motivo` y `detalle` | en una `rechazada` | El código del motivo (`respuestas_y_errores.md`, sección 4) y un texto para la persona que configura el nodo |

**Duplicada** (D-74, punto 6): ya hay una lectura de ese sensor con la misma `medida_en` (por ejemplo, el nodo reenvió un lote cuya
respuesta se perdió). Para el nodo es un éxito: la lectura ya está en InfoPonia. Dos lecturas iguales dentro del mismo pedido: la segunda es
`duplicada`.

## 2. Estados — `POST /api/iot/v1/estados`

El nodo informa, cuando cambian y al arrancar, la conectividad de sus equipos, sus fallas y el estado operativo de sus actuadores. Es
optativo (regla «Estados de los equipos»).

### Pedido

```json
{
  "estados": [
    { "identificador": "norte/sectorA/ventilador", "estado": "encendido", "informado_en": "2026-11-21T14:02:10-03:00" },
    { "identificador": "norte/sectorA/ventana", "estado": "posicion:40" },
    { "identificador": "norte/sectorA/humedad", "estado": "en_falla" }
  ]
}
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `estados` | lista de 0 a 500 objetos | sí | Única clave del objeto. Vacía también cuenta como mensaje aceptado |
| `estados[].identificador` | texto | sí | El de un sensor o un actuador registrado del sistema |
| `estados[].estado` | texto | sí | Uno de la tabla de abajo |
| `estados[].informado_en` | texto (fecha con zona) | no | Cuándo cambió. Si falta, la de recepción |

| `estado` | Para | Qué hace InfoPonia (extensión 1a) |
|---|---|---|
| `en_linea` | sensor o actuador | Resuelve la alerta «dispositivo sin actividad» del equipo |
| `desconectado` | sensor o actuador | Genera la alerta «dispositivo sin actividad» |
| `en_falla` | sensor o actuador | Pasa el equipo a «fuera de servicio» y genera la alerta «dispositivo en falla» (crítica) |
| `encendido`, `apagado` | actuador | Pasa a ser su estado informado |
| `abierto`, `cerrado` | actuador | Ídem |
| `nivel:<n>`, `posicion:<n>` | actuador | Ídem; `<n>` es un entero (por ejemplo `nivel:60`, `posicion:-15`) |

Son los mismos textos que deja cada comando (`docs/modelo/iot.md`, «Catálogo de capacidades»: `ENCENDER` → `encendido`, `FIJAR_NIVEL` →
`nivel:<n>`…). Cualquier mensaje sobre un equipo, no solo `en_linea`, resuelve su alerta «dispositivo sin actividad».

### Respuesta 200

```json
{
  "version": "v1",
  "servidor_en": "2026-11-21T17:05:00Z",
  "aceptados": 2,
  "rechazados": 1,
  "resultados": [
    { "indice": 0, "identificador": "norte/sectorA/ventilador", "resultado": "aceptado" },
    { "indice": 1, "identificador": "norte/sectorA/ventana", "resultado": "aceptado" },
    { "indice": 2, "identificador": "norte/sectorA/temp-vieja", "resultado": "rechazado", "motivo": "equipo_dado_de_baja",
      "detalle": "«norte/sectorA/temp-vieja» era de un equipo dado de baja de este sistema IoT." }
  ]
}
```

`resultado` es `aceptado` o `rechazado`; los demás campos, como en las lecturas.

## 3. Modo — `POST /api/iot/v1/modo`

El nodo informa si InfoPonia lo controla (`remoto`) o si actúa por su cuenta (`local`). Es optativo: mientras no lo informe, vale `remoto`
(regla «Modo del nodo»). Lo manda al arrancar y cada vez que cambia.

### Pedido

```json
{ "modo": "local" }
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `modo` | texto | sí | `remoto` o `local`. Otro valor: 400 `mensaje_mal_formado` |

### Respuesta 200

```json
{ "version": "v1", "servidor_en": "2026-11-21T17:05:00Z", "resultado": "aceptado", "modo": "local", "cambio": true }
```

`cambio` es `false` si el nodo ya estaba en ese modo (repetirlo no hace nada). En modo `local`, InfoPonia sigue registrando lecturas,
estados y alertas, pero no evalúa reglas ni entrega comandos (extensiones 1b y 6d; eso llega con IOT-05 e IOT-06).

## 4. Anuncio — `POST /api/iot/v1/anuncio`

El nodo anuncia la lista completa de sus equipos y, de cada actuador, los comandos del catálogo que soporta. Es optativo: sin anuncio, la
compatibilidad de los actuadores queda «sin verificar» y no se restringe ninguna acción (regla «Anuncio de equipos»). **Cada anuncio
reemplaza al anterior**: un equipo que deja de anunciarse deja de figurar como anunciado.

### Pedido

```json
{
  "equipos": [
    { "identificador": "norte/sectorA/temperatura", "clase": "sensor" },
    { "identificador": "norte/sectorA/ventilador", "clase": "actuador", "comandos": ["ENCENDER", "APAGAR", "FIJAR_NIVEL"] },
    { "identificador": "norte/sectorA/ventana", "clase": "actuador", "comandos": ["ABRIR", "CERRAR"] }
  ]
}
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `equipos` | lista de 0 a 500 objetos | sí | Única clave del objeto. Una lista vacía es válida: el nodo no tiene equipos |
| `equipos[].identificador` | texto | sí | Con la forma de un identificador. **No se repite** en el anuncio (sin distinguir mayúsculas). No hace falta que esté registrado |
| `equipos[].clase` | texto | sí | `sensor` o `actuador` |
| `equipos[].comandos` | lista de textos | en un actuador, sí; en un sensor, no va | Códigos del catálogo: `ENCENDER`, `APAGAR`, `FIJAR_NIVEL`, `ABRIR`, `CERRAR`, `FIJAR_POSICION`. Sin repetir. Puede ser vacía |

El anuncio se procesa **entero o nada**: si un elemento está mal (clase desconocida, comando fuera del catálogo, identificador repetido o mal
formado, un sensor con `comandos`), se rechaza el mensaje con 400 `mensaje_mal_formado`, con el `indice` y el `campo` del primer error, y no
cambia nada.

### Respuesta 200

```json
{
  "version": "v1",
  "servidor_en": "2026-11-21T17:05:00Z",
  "resultado": "aceptado",
  "equipos": 3,
  "actuadores": [
    { "identificador": "norte/sectorA/ventana", "compatibilidad": "incompatible", "acciones_incompatibles": ["Fijar posición"] },
    { "identificador": "norte/sectorA/ventilador", "compatibilidad": "compatible", "acciones_incompatibles": [] }
  ],
  "sin_registrar": ["norte/sectorB/co2"]
}
```

| Campo | Qué es |
|---|---|
| `equipos` | Cuántos equipos anunció el nodo |
| `actuadores` | Cada actuador **registrado** (no dado de baja) del sistema, por identificador, con la compatibilidad que quedó después del anuncio: `compatible`, `incompatible` (con los nombres de sus acciones incompatibles) o `sin_verificar` (no figura en el anuncio) |
| `sin_registrar` | Los identificadores anunciados que no son de ningún equipo registrado. No generan alertas: InfoPonia los ofrece al registrar hardware (regla 14 de IOT-ALT-HDW) |

La compatibilidad compara los comandos de las acciones activas del tipo de cada actuador con los anunciados para su identificador
(`recalcular_compatibilidad`, `docs/casos_de_uso/iot/hardware.md`).

## 5. Retiro de comandos — `GET /api/iot/v1/comandos`

El nodo pide, **cada 5 segundos**, los comandos que InfoPonia tiene para sus actuadores (D-77, punto 4). La respuesta es inmediata: si no
hay, la lista viene vacía (extensión 2b). Cada retiro cuenta como comunicación del nodo (postcondición a).

### Pedido

Sin cuerpo. Solo el encabezado `Authorization`.

### Respuesta 200

```json
{
  "version": "v1",
  "servidor_en": "2026-11-21T17:05:00Z",
  "modo": "remoto",
  "comandos": [
    { "id": 101, "identificador": "norte/sectorA/ventilador", "comando": "FIJAR_NIVEL", "valor": 60, "intento": 1, "espera_segundos": 60 },
    { "id": 102, "identificador": "norte/sectorA/ventana", "comando": "CERRAR", "valor": null, "intento": 2, "espera_segundos": 60 }
  ]
}
```

| Campo | Qué es |
|---|---|
| `modo` | El modo del nodo que tiene registrado InfoPonia. Con `local`, `comandos` siempre viene vacía (extensión 2d) |
| `comandos[].id` | El identificador del comando. Es el que va en la ruta del resultado y el que el nodo recuerda 24 horas (D-77, punto 3) |
| `comandos[].identificador` | El identificador del actuador, tal como se registró |
| `comandos[].comando` | Un código del catálogo (`README.md`, sección 9) |
| `comandos[].valor` | Entero, en `FIJAR_NIVEL` y `FIJAR_POSICION`; `null` en los demás |
| `comandos[].intento` | El número de este intento (1 la primera vez). Un comando sin respuesta se vuelve a entregar con el número siguiente |
| `comandos[].espera_segundos` | Cuánto espera InfoPonia el resultado de este intento (el intervalo de reintento de la Configuración Operativa). Después lo cuenta como «sin respuesta» |

**Qué se entrega** (regla «Comando disponible»): cada comando pendiente de un actuador activo del nodo que **nunca se retiró** o cuyo
**último intento venció** sin respuesta. Un comando que el nodo retiró y todavía está dentro de su espera **no** se vuelve a entregar.
Antes de entregar, InfoPonia resuelve los intentos vencidos (extensiones 2a y 2a.1a) y cancela los comandos de actuadores que ya no están
activos (2c).

**Un comando repetido.** Si el nodo recibe un `id` que ya ejecutó o rechazó (está en su memoria de 24 horas), **no lo ejecuta de nuevo**:
manda otra vez el resultado que guardó (regla «Comando repetido en el nodo»).

## 6. Resultado de un comando — `POST /api/iot/v1/comandos/<id>/resultado`

Uno por cada comando entregado, apenas el nodo lo ejecuta, lo intenta sin éxito o lo rechaza.

### Pedido

```json
{ "resultado": "ejecutado", "detalle": "Velocidad al 60 %.", "estado": "nivel:60", "informado_en": "2026-11-21T14:05:08-03:00" }
```

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `resultado` | texto | sí | `ejecutado`; `fallo` (lo intentó y no pudo: se reintenta si quedan intentos); `rechazado` (no reconoce ese comando para ese actuador: falla sin reintentos y marca la acción como incompatible) |
| `detalle` | texto | no | Hasta 300 caracteres. Lo que pasó, para la persona que mira el comando (por ejemplo, el error del equipo) |
| `estado` | texto | no | El estado en que quedó el actuador, con los valores operativos de la sección 2 (`encendido`, `nivel:60`…). Si viene, pasa a ser su estado informado |
| `informado_en` | texto (fecha con zona) | no | Cuándo quedó en ese estado. Si falta, la de recepción |

Un `resultado` fuera de la lista, un `detalle` de más de 300 caracteres, un `estado` que no es operativo o una fecha inválida o futura
rechazan el mensaje con 400 `mensaje_mal_formado`, con el `campo`.

### Respuesta 200

```json
{ "version": "v1", "servidor_en": "2026-11-21T17:05:10Z", "resultado": "aceptado", "comando": 101, "estado_comando": "ejecutado" }
```

| `resultado` | Cuándo | `estado_comando` |
|---|---|---|
| `aceptado` | El comando estaba pendiente y se registró el resultado (también si llegó tarde, extensión 4c) | `ejecutado`; `pendiente` (falló y le quedan intentos: se vuelve a entregar cuando pase la espera); o `fallido` (falló el último intento, o fue rechazado) |
| `ya_resuelto` | El comando ya estaba ejecutado, fallido o cancelado, o el resultado es repetido (4d): no cambia nada (D-77, punto 2) | El estado final que ya tenía |

Un `id` que no existe o que es de un actuador de otro sistema: 404 `comando_inexistente` (4e).

