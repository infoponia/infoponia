# Ejemplos del contrato del nodo v1

Pedidos y respuestas completos de `mensajes.md` y `respuestas_y_errores.md` (D-74; los de comandos, D-77). Sirven a dos públicos:

- **A quien configura un nodo:** para ver exactamente qué mandar y qué va a recibir.
- **A las pruebas de InfoPonia** (D-70, «Consecuencias»): `iot/tests/test_api_ejemplos.py` manda cada `*.pedido.json` con el escenario de
  abajo y compara la respuesta con su `*.respuesta.json` **campo por campo, salvo `servidor_en`**. Si un texto de `detalle` cambia, se
  cambia acá y en `respuestas_y_errores.md`, sección 4b, en el mismo PR.

Un archivo `X.pedido.json` va con su `X.respuesta.json`. Los que solo tienen respuesta se arman en la prueba (por ejemplo, el pedido sin
token).

## Escenario

Todos los ejemplos suponen este estado, que la prueba arma con las fábricas de `iot/tests/fabricas.py`:

- **Hora de InfoPonia:** `2026-11-21T17:05:00Z` (14:05 en Argentina). La prueba la fija con `iot.api.reloj.ahora`.
- **Configuración Operativa:** los valores iniciales (`docs/modelo/iot.md`, «Parámetros IoT»): antigüedad máxima de una lectura, 5 minutos.
- **Sistema IoT** del invernadero «Norte», **activo**, rango de la temperatura de la solución 18,0 a 24,0 °C, nodo en modo `remoto`. Su
  `token_resumen` es `resumen_de("token-de-ejemplo-no-es-secreto")`: ese es el token que mandan los pedidos (no es un token real).
- **Equipos** del sistema (todos activos salvo el último):

| Identificador | Clase | Variable o tipo | Calibración | Sector |
|---|---|---|---|---|
| `norte/sectorA/temperatura` | sensor | temperatura | −10 a 60 | Sector A |
| `norte/sectorA/humedad` | sensor | humedad | 0 a 100 | Sector A |
| `norte/sectorA/luz` | sensor | intensidad lumínica | 0 a 100000 | Sector A |
| `norte/tanque1/temp-solucion` | sensor | temperatura de la solución | 0 a 50 | general |
| `norte/tanque1/nivel` | sensor | nivel de la solución | — | general |
| `norte/sectorA/ventilador` | actuador | Ventilador (Encender, Apagar, Fijar velocidad) | — | Sector A |
| `norte/sectorA/ventana` | actuador | Ventana (Abrir, Cerrar, Fijar posición) | — | Sector A |
| `norte/sectorA/temp-vieja` | sensor | temperatura, **dado de baja** | −10 a 60 | Sector A |

- Sin telemetrías previas (salvo en el reenvío) y sin anuncio previo.
- **Para los ejemplos de comandos** (IOT-05), además:
  - Configuración Operativa inicial: 3 reintentos (4 intentos) e intervalo de 60 segundos.
  - El nodo se comunicó por última vez a las `17:04:55Z` (está «en línea»: el intento vencido de 102 cuenta como «sin respuesta»).
  - **Comando 101**: ventilador, acción «Fijar velocidad» (`FIJAR_NIVEL`), valor 60, pendiente, **nunca retirado**, emitido por el
    Agrónomo.
  - **Comando 102**: ventana, acción «Cerrar» (`CERRAR`), pendiente, **1 intento**, retirado a las `17:03:30Z`: su espera venció a las
    `17:04:30Z` sin respuesta.
  - Para los resultados, 101 está **retirado** (intento 1, a las `17:04:50Z`), salvo en `comando_resultado_fallo_ultimo`, donde está en su
    **cuarto** intento.

## Archivos

| Ejemplo | Ruta | Código | Qué muestra |
|---|---|---|---|
| `lecturas_aceptadas` | `lecturas` | 200 | Una lectura de cada sensor, todas aceptadas; el nivel sin `valida` |
| `lecturas_reenviadas` (solo respuesta) | `lecturas` | 200 | El mismo pedido de `lecturas_aceptadas`, mandado **dos veces**: la segunda respuesta, todas `duplicada` |
| `lecturas_latido` | `lecturas` | 200 | El lote vacío |
| `lecturas_con_rechazos` | `lecturas` | 200 | Una inválida (999 °C), una atrasada (15 minutos), una sin fecha, una repetida en el mismo pedido y un rechazo por cada motivo de lectura salvo `sistema_desconectado` y `error_interno` |
| `estados` | `estados` | 200 | Estado operativo de dos actuadores (uno con fecha), falla de un sensor, «en línea», un equipo dado de baja y dos estados inválidos |
| `modo_local` | `modo` | 200 | Pasa a `local` (`cambio: true`) |
| `modo_remoto` | `modo` | 200 | Ya estaba en `remoto` (`cambio: false`) |
| `anuncio` | `anuncio` | 200 | El ventilador queda compatible, la ventana incompatible (no anuncia `FIJAR_POSICION`) y `co2` queda sin registrar |
| `anuncio_mal_formado` | `anuncio` | 400 | Un comando fuera del catálogo: no cambia nada |
| `error_mensaje_mal_formado` | `lecturas` | 400 | Un campo de más arriba (`nodo`) |
| `error_json_invalido` (pedido `.txt`) | `lecturas` | 400 | `NaN` no es JSON válido |
| `error_token_ausente` (solo respuesta) | cualquiera | 401 | Sin encabezado `Authorization` |
| `error_token_invalido` (solo respuesta) | cualquiera | 401 | Con un token que no es de ningún sistema |
| `error_sistema_desconectado` (solo respuesta) | cualquiera | 403 | El sistema del escenario, desconectado |
| `error_demasiados_pedidos` (solo respuesta) | cualquiera | 429 | El pedido 121 del minuto que empieza a las 17:05:00 (`Retry-After: 60`) |
| `error_mensaje_demasiado_grande` (solo respuesta) | cualquiera | 413 | Un cuerpo de 262.145 bytes |
| `error_demasiados_elementos` (solo respuesta) | `lecturas` | 413 | 501 lecturas |
| `error_tipo_no_soportado` (solo respuesta) | cualquiera | 415 | `Content-Type: text/plain` |
| `error_metodo_no_permitido` (solo respuesta) | `lecturas` | 405 | Un `GET` |
| `error_ruta_inexistente` (solo respuesta) | `/api/iot/v1/telemetria` | 404 | Una ruta que no existe |
| `comandos_retiro` (solo respuesta) | `GET comandos` | 200 | 101 por primera vez; 102 en su segundo intento (el primero venció) |
| `comandos_retiro_vacio` (solo respuesta) | `GET comandos` | 200 | El mismo retiro, repetido enseguida: los dos están dentro de su espera |
| `comandos_retiro_local` (solo respuesta) | `GET comandos` | 200 | Con el nodo en modo `local`: lista vacía, sin consumir intentos |
| `comando_resultado_ejecutado` | `POST comandos/101/resultado` | 200 | Ejecutado, con el estado en que quedó el ventilador |
| `comando_resultado_ya_resuelto` (solo respuesta) | `POST comandos/101/resultado` | 200 | El pedido de `comando_resultado_ejecutado`, mandado **dos veces**: la segunda respuesta |
| `comando_resultado_fallo` | `POST comandos/101/resultado` | 200 | Falló en el primer intento: sigue pendiente |
| `comando_resultado_fallo_ultimo` (solo respuesta) | `POST comandos/101/resultado` | 200 | El pedido de `comando_resultado_fallo`, en el cuarto intento: fallido (escalamiento) |
| `comando_resultado_rechazado` | `POST comandos/102/resultado` | 200 | Rechazado: fallido sin reintentos |
| `comando_resultado_inexistente` (solo respuesta) | `POST comandos/999/resultado` | 404 | Un comando que no existe |
| `comando_resultado_mal_formado` | `POST comandos/101/resultado` | 400 | `«falló»` no es un resultado del contrato |
| `error_metodo_no_permitido_comandos` (solo respuesta) | `POST comandos` | 405 | El retiro solo acepta `GET` |

Los ejemplos no muestran las alertas: las alertas no viajan en la respuesta. Las pruebas de los servicios las verifican aparte.
