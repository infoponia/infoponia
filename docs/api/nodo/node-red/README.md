# Nodo de referencia en Node-RED · lecturas, estados, modo, anuncio y comandos

Flujo de Node-RED que hace de nodo central de prueba (D-70, punto 6): simula los equipos de un invernadero, manda lo que pide el contrato v1
(`docs/api/nodo/`) y se comporta como dice la guía (`docs/api/nodo/README.md`): un lote cada 60 segundos, cola de hasta 1 hora, reintentos
con espera creciente, reloj y latido (D-74); y retira los comandos cada 5 segundos, los ejecuta en actuadores simulados y manda su resultado,
con la memoria de 24 horas (D-77). Es el mismo adaptador que usaría el Jardín Botánico, cambiando los equipos simulados por nodos
«mqtt in» de su Mosquitto.

**Node-RED no es una dependencia del repo** (D-70): no se instala con `requirements.txt` ni lo usan las pruebas, que mandan los
`ejemplos/*.json` directamente. Estos flujos son para probar a mano y para la defensa (`docs/api/nodo/escenarios.md`).

Archivos, una pestaña cada uno (se importan los dos, con las mismas variables de entorno):
- `flujo_lecturas.json` («InfoPonia · lecturas (API v1)»): lecturas, estados, modo y anuncio (IOT-03);
- `flujo_comandos.json` («InfoPonia · comandos (API v1)»): retiro y resultado de comandos (IOT-05).

Los dos usan solo nodos que vienen con Node-RED (`inject`, `function`, `http request`, `delay`, `debug`, `comment`): no hay que
instalar nada de la paleta.

## 1. Instalar y abrir Node-RED

Verificado el 21/11/2026 en la documentación de Node-RED («Running on Windows» y «Node.js versions»): **Node-RED 5.x pide Node.js 22 o
posterior** (4.x pedía 18). Instalá la versión LTS de Node.js desde su página oficial y después, en PowerShell:

```
node --version; npm --version
npm install -g node-red
```

## 2. Arrancarlo con la dirección y el token

El flujo lee dos variables de entorno, para que **el token nunca quede en el flujo** (el repo es público):

| Variable | Valor |
|---|---|
| `INFOPONIA_URL` | La dirección de la API que mostró InfoPonia junto al token. En local: `http://127.0.0.1:8000/api/iot/v1/` |
| `INFOPONIA_TOKEN` | El token del sistema IoT (se muestra una sola vez al registrarlo o regenerarlo) |

En la **misma** terminal de PowerShell, antes de arrancar:

```
$env:INFOPONIA_URL = "http://127.0.0.1:8000/api/iot/v1/"
$env:INFOPONIA_TOKEN = "<pegá acá el token>"
node-red
```

Dejá la terminal abierta: cerrarla detiene Node-RED. El editor se abre en el navegador en `http://127.0.0.1:1880`. Contra el servidor de
Render, la dirección empieza con `https://` (nunca `http://`: la guía, sección 7). `http://` solo vale contra tu propia máquina.

## 3. Importar el flujo

En el editor: menú ☰ → **Import** → «select a file to import» → `docs/api/nodo/node-red/flujo_lecturas.json` → **Import**; lo mismo con
`flujo_comandos.json`; y después **Deploy**. El nodo «Configuración de equipos» muestra «configurado» en verde, o «faltan INFOPONIA_URL o INFOPONIA_TOKEN» en rojo si las
variables no llegaron.

## 4. Preparar InfoPonia

Los identificadores del flujo son los del escenario de los ejemplos (`docs/api/nodo/ejemplos/README.md`). En InfoPonia, con el Agrónomo:

1. Registrá el sistema IoT del invernadero (IoT · Sistema IoT) y copiá el token.
2. Registrá los equipos (IoT · Hardware) con estos identificadores: `norte/sectorA/temperatura`, `norte/sectorA/humedad`,
   `norte/sectorA/luz`, `norte/tanque1/temp-solucion`, `norte/tanque1/nivel` (sensores) y `norte/sectorA/ventilador` (Ventilador) y
   `norte/sectorA/ventana` (Ventana) (actuadores). Para usar otros, cambialos en el nodo «Configuración de equipos» (lista `sensores` y
   `actuadores`) y volvé a hacer **Deploy**.
3. Para ver alertas de umbral, el invernadero tiene que tener variedades presentes (lotes activos u órdenes de siembra a realizar): sin
   ellas no hay umbral efectivo y la temperatura, la humedad y la luz no se comparan (IOT-ENT-INF, extensión 5c). La solución y el nivel se
   comparan igual.

## 5. Qué hace el flujo

| Bloque | Qué hace | Regla |
|---|---|---|
| 1 · Al arrancar | Carga la configuración y manda el modo, el estado de los actuadores y el anuncio. Vuelve a anunciar cada 24 horas | D-74, punto 4 |
| 2 · Lecturas cada 60 s | Lee los sensores simulados, encola el lote (hasta 1 hora), manda lo más viejo de la cola (hasta 500 por pedido) y, si la cola queda vacía, el latido. Según la respuesta: saca de la cola, reintenta con espera creciente (10 s → 5 min, o `Retry-After`) o descarta | D-74, puntos 1 a 3 |
| 3 · Estados, modo y anuncio | Un pedido por mensaje, con reintento simple de las fallas pasajeras (hasta 5) | D-74, punto 3 |
| 4 · Panel | Botones para forzar condiciones (ver abajo) | — |

Lo que pasa se ve en el estado de cada nodo (el texto bajo el nodo) y en la barra lateral de depuración (🐞): los nodos «Registro…» muestran
las lecturas rechazadas, los mensajes rechazados y las fallas pasajeras.

**Reloj.** Si la hora de InfoPonia (`servidor_en`) difiere más de 2 minutos de la de la computadora, el flujo pasa a mandar sin fecha y sin
cola, como pide la guía. Para volver, «Volver a lo normal».

## 6. El panel: forzar condiciones

Cada botón es un nodo «inject»: se dispara con el cuadrado de su izquierda. Lo forzado rige desde el próximo ciclo de lecturas (hasta 60
segundos) y hasta «Volver a lo normal».

| Botón | Qué debería pasar en InfoPonia |
|---|---|
| Temperatura alta (35 °C) / baja (8 °C) | Con umbral efectivo: la alerta «fuera de umbral efectivo» del sensor. Al volver a lo normal, se resuelve cuando la lectura queda dentro a más de la histéresis |
| Lectura inválida (999 °C) | La alerta «lectura inválida» (fuera de la calibración) |
| Solución caliente (27 °C) | Con el rango de la solución cargado en el sistema IoT: «solución fuera de rango» |
| Nivel de solución bajo | La alerta crítica «nivel de solución bajo» (el correo lo manda la revisión periódica, D-71, desde IOT-04) |
| Equipo no registrado (co2) | La lectura rechazada y la alerta «dispositivo no registrado» |
| Reloj sin sincronizar | Las lecturas van sin `medida_en`: InfoPonia usa la hora de recepción |
| Ventana sin FIJAR_POSICION (anuncio) | Después de «Anunciar ahora»: la ventana queda incompatible, con la alerta «configuración incompatible» |
| Ventilador encendido / apagado, Ventana al 40 % | El estado informado del actuador |
| Humedad en falla / desconectada / en línea | «Dispositivo en falla» (el sensor queda fuera de servicio) / «dispositivo sin actividad» / se resuelve |
| Modo local / remoto | El modo del nodo en IoT · Hardware |
| Anunciar ahora | Los equipos anunciados en el alta de hardware y la compatibilidad de los actuadores |

Para probar los reintentos: detené el servidor de InfoPonia (`runserver`) un par de minutos. El nodo «Según la respuesta» muestra «falla …:
reintento en …» y la cola crece; al volver a arrancarlo, la cola se vacía y las lecturas de esos minutos llegan como atrasadas (sin alertas).

## 6b. El flujo de comandos

| Bloque | Qué hace | Regla |
|---|---|---|
| Al arrancar | Carga los actuadores simulados (qué comandos soporta cada uno y su estado) y vacía la memoria | D-77, punto 3 |
| Cada 5 s | `GET comandos`; un mensaje por comando entregado. Si el retiro anterior no volvió, no manda otro | D-77, puntos 1 y 4 |
| Ejecutar (con memoria de 24 h) | Si el `id` ya está en la memoria, manda el resultado guardado sin ejecutar. Si no, según la simulación elegida: ejecuta y cambia el estado del actuador simulado, falla, no responde o rechaza. Un comando que el actuador no soporta se rechaza siempre | Regla «Comando repetido en el nodo» |
| Resultado | `POST comandos/<id>/resultado`; con 200 (`aceptado` o `ya_resuelto`) termina; ante una falla pasajera reintenta hasta 5 veces, sin pasar la espera del comando; un 4xx se descarta | D-77, punto 4 |

**Panel del flujo de comandos** (rige para los comandos que lleguen después de tocarlo):

| Botón | Qué debería pasar en InfoPonia |
|---|---|
| Ejecutar (normal) | El comando pasa a «Ejecutado» y el actuador muestra su estado nuevo |
| Fallar cada intento | Cada intento falla; después del último, el comando queda «Fallido», el actuador «Fuera de servicio» y aparece la alerta crítica «Comando fallido» (el correo lo manda la revisión periódica) |
| No responder | Cada intento vence sin respuesta (un minuto con la configuración inicial) y se vuelve a entregar; al agotarse, lo mismo que «Fallar» |
| Rechazar (no reconoce) | El comando queda «Fallido» sin reintentos, la acción pasa a incompatible y aparece «Configuración incompatible»; el actuador sigue activo |

Para no esperar 4 minutos en una prueba de escalamiento, bajá en Configuración operativa · Módulo IoT los reintentos a 1 y el intervalo a 10
segundos (y volvelos después a sus valores).

## 7. Del simulador a equipos reales

Para conectar los equipos de un broker MQTT, reemplazá el nodo «Leer sensores simulados» por nodos «mqtt in» (uno por tópico) que armen el
mismo `msg.lecturas` (lista de `{identificador, valor, medida_en}`) en el formato unificado de la guía, sección 2, y dejá el resto del flujo
igual. Los estados de los actuadores y el modo salen de la lógica de control del nodo, que este flujo no tiene.

## 8. Mantener el flujo

Si cambia el contrato, se cambia primero `docs/api/nodo/` y después este flujo (D-70). Para exportarlo: menú ☰ → **Export** → la pestaña →
**Download**, y reemplazá `flujo_lecturas.json`. **Antes de subirlo, verificá que no tenga el token** (no debería: lo lee de la variable
de entorno).
