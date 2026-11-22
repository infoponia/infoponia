# Casos de uso · iot · Consultar lecturas (panel de monitoreo)

Copia para el repo del caso IOT-CNS-LEC (v0.2, de alto nivel) de «CU extendidos» (Lote 1 v5.6 del IoT, copiado el 22/11/2026). Junto con
los demás casos IOT-* reemplaza a los preliminares de la «Documentación para la IA» que lista `docs/tareas/ronda_iot_1.md`, sección 3.
Cotejado con `docs/modelo/iot.md` (que aplica MD-98 a MD-113) y con D-70 a D-76.

Es un caso de uso breve. **El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no elijas en
silencio.

Para nombrar las pruebas: `test_regla_<numero>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-CNS-LEC | Consultar lecturas (panel de monitoreo) | Agrónomo y Gerente (alcance) | IOT-04 (comandos pendientes y acciones de comandos y reglas, IOT-05 e IOT-06) | `iot/tests/test_iot_cns_lec.py` |

## IOT-CNS-LEC · Consultar Lecturas

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** seguir en un panel el estado ambiental y operativo de un invernadero con sistema IoT: las últimas lecturas frente al umbral efectivo, el estado de los sensores, los actuadores y el nodo central, y las alertas activas.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El invernadero tiene un sistema IoT en estado «activo» o «desconectado».

**Postcondición:**

a. La consulta no produce cambios en el Sistema.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-CNS-HDW.

2. Del nodo central se ven el estado del sistema IoT, su conectividad («en línea» o «sin señal»), su modo («remoto» o «local») y la fecha y hora de su última comunicación. Si el sistema está desconectado, el panel lo avisa y muestra los últimos datos recibidos. Si el nodo informa el modo «local», el panel avisa que InfoPonia no evalúa reglas ni entrega comandos hasta que vuelva a «remoto».

3. Los sensores se agrupan por variable. De cada sensor se ven su última lectura, con fecha y hora, y cómo queda: los de temperatura, humedad e intensidad lumínica, frente al umbral efectivo (dentro, sobre el máximo o bajo el mínimo); los de temperatura de la solución, frente al rango del sistema IoT (regla 7 de IOT-MOD-SIS), o sin comparar si no hay rango; los de nivel de la solución, «normal» o «bajo». Una lectura fuera del rango de calibración se muestra como lectura inválida. Un sensor sin lecturas dentro del plazo de la Configuración Operativa, o que el nodo informó desconectado, se marca «sin actividad»; uno del que nunca llegó un mensaje, «sin confirmar». Las lecturas de intensidad lumínica fuera del horario de luz se muestran sin compararlas. De cada sensor de intensidad lumínica se ve además el fotoperíodo del último día completo, frente al rango de fotoperíodo del umbral efectivo.

4. De cada sensor, salvo los de nivel de la solución, se ve un gráfico de sus lecturas con la franja del umbral efectivo o del rango de la solución. El actor elige el período: la última hora o las últimas 6 o 24 horas, que se grafican con las lecturas, o los últimos 7 o 30 días, que se grafican con los resúmenes horarios (mínimo, promedio y máximo de cada hora). Los resúmenes horarios se conservan aunque las lecturas se borren por la retención.

5. De cada actuador se ven su estado actual tal como lo informó el nodo, con su fecha y hora (por ejemplo, «encendido desde las 14:32»), la marca «cambiado en el invernadero» si el cambio no lo originó un comando de InfoPonia, si está fuera de servicio, su compatibilidad con el nodo y sus comandos pendientes. Un actuador del que nunca llegó un mensaje se marca «sin confirmar», y uno que el nodo informó desconectado, «sin actividad».

6. El panel muestra el umbral efectivo del invernadero (panel de parametrización): el mínimo y el máximo de cada variable, con las variedades de los lotes activos y de las siembras a realizar que lo componen y la variedad que fija cada límite. Si no hay lotes ni siembras, informa que el invernadero no tiene umbral efectivo. Muestra también el rango de temperatura de la solución del sistema IoT, si está definido, y, en solo lectura, los parámetros IoT de la Configuración Operativa.

7. El panel muestra las alertas activas del sistema IoT del invernadero, ordenadas por severidad (crítica, advertencia o informativa). La severidad la fija el tipo de alerta (regla «Alertas» de IOT-ENT-INF) y se guarda en la alerta (Alerta.nivelSeveridad). La alerta «dispositivo no registrado» de un identificador que era de un equipo dado de baja lo indica y ofrece reactivarlo (IOT-MOD-HDW) o registrar un reemplazo (IOT-ALT-HDW).

8. Los sensores de un sector fuera de servicio se muestran con esa marca y no generan alertas ambientales.

9. El panel se actualiza solo, como máximo cada 30 segundos (nota de presentación, «Restricciones tecnológicas y operativas»).

10. Abrir el panel no dispara revisiones: los intentos de comando vencidos se detectan en cada consulta del nodo (IOT-RSV-CMD), y la comunicación del nodo central y la inactividad de los equipos, en la revisión periódica de InfoPonia cada 5 minutos (IOT-ENT-INF).

11. Quien puede operar el IoT del invernadero inicia desde acá Emitir Comando, IOT-CNL-CMD, IOT-CNS-RGL e IOT-CNS-HDW. Quien solo consulta no tiene acciones.

12. La consulta no se audita (SEG-14).

## Cómo se aplica en la ronda «IoT 1» (D-44, D-61, D-62, D-76)

Tarea: **IOT-04**. Modelo: `docs/modelo/iot.md` («SistemaIoT», «Hardware», «Sensor», «Actuador», «Telemetria», «ResumenHorario y
FotoperiodoDiario», «AlertaIot», «Parámetros IoT»). Alcance, elección del invernadero y conectividad: `docs/casos_de_uso/iot/sistema_iot.md`,
«Para los cinco». Umbral efectivo: `docs/api/variedades.md`, «Umbral efectivo». Alertas: `docs/api/alertas.md` (consulta de MAE-02c, con
`tipos` de MAE-02d, y sección 8, enlaces, también de MAE-02d).

### Ruta y pestaña

- `iot/urls.py`: `monitoreo/` (nombre `monitoreo`), con `?invernadero=<id>` y `?periodo=<1|6|24|168|720>`. La pestaña «Monitoreo» es la
  **primera** del módulo, como en el prototipo (`NAV`). Desde IOT-04, `/iot/` redirige a «Monitoreo» (IOT-02 la llevaba a «Sistema IoT»).
- El período se recuerda en la sesión (`iot_periodo`). Por omisión, `24`, como el prototipo.
- Vista con `rol_requerido` (Agrónomo y Gerente), `never_cache` y `vary_on_headers("HX-Request")`. Un invernadero fuera de
  `invernaderos_que_consulta` da 404 (regla 1).

### Servicio (`iot/servicios/monitoreo.py`)

`panel(actor, invernadero_id, periodo, ahora) -> PanelDeMonitoreo` arma todo lo que muestra la pantalla. Solo lectura, sin auditoría (regla
12), y **con una cantidad fija de consultas**: la misma con 1 sensor que con 10. La prueba lo verifica con `assertNumQueries`. Lo usan la
vista completa y el fragmento que se refresca.

| Bloque | De dónde sale | Regla |
|---|---|---|
| Sin sistema | Invernadero sin sistema no dado de baja: «{invernadero} no tiene Sistema IoT» y «Registrar Sistema IoT» (solo a quien opera; a los demás, sin botón) | precondición b |
| Nodo | Estado del sistema, `conectividad(nodo, ahora)` (IOT-02), modo y última comunicación | 2 |
| Avisos | Desconectado: «Sistema desconectado. InfoPonia no recibe lecturas ni emite comandos hasta que se active; se muestran los últimos datos recibidos.» · Sin señal, nunca: «El nodo todavía no se comunicó. Cargale la dirección de la API y el token; cuando se comunique pasará a «En línea».» · Sin señal: «El nodo no se comunica desde {hace cuánto}. Los valores son los últimos recibidos.» · Local: el texto del prototipo («El nodo está operando en modo local…») | 2 |
| Indicadores | «Sensores con problema» (de N), «Alertas activas», «Actuadores operativos» (de N). «Comandos pendientes» recién con IOT-05 (D-25: lo que no existe no se muestra) | — |
| Alertas activas | `consultar_alertas(actor, invernadero_id=…, tipos=CODIGOS_DE_ALERTAS_IOT)` (MAE-02c; el argumento `tipos` lo suma MAE-02d), ya ordenadas por severidad, y sus enlaces con una llamada a `enlaces_de_alertas(actor, alertas)` (abajo); «Notificada por correo» si `correo_enviado_en` no es nulo | 7 |
| Sensores | Los no dados de baja del sistema, agrupados por variable (temperatura, humedad, intensidad lumínica, temperatura de la solución, nivel), con su situación, su última lectura, su gráfico y, en la luz, el fotoperíodo de ayer | 3, 4, 8 |
| Actuadores | Los no dados de baja: estado informado con su hora, «cambiado en el invernadero», situación y compatibilidad | 5 |
| Umbral efectivo | `umbral_efectivo([invernadero])`: mínimo y máximo de cada variable, con la variedad que fija cada límite y las variedades que lo componen (sus nombres, en una consulta); o «Este invernadero no tiene umbral efectivo: no tiene lotes activos ni siembras a realizar.». El rango de la solución o «Sin rango definido. Se define en Sistema IoT.» | 6 |
| Parámetros IoT | Los 14 de `maestros.servicios.configuracion.obtener()`, en solo lectura, en un bloque plegable. Al Gerente, «Modificar parámetros» lleva a Configuración operativa (D-76, punto 9) | 6 |

### Situación de un sensor (regla 3, 8; prototipo `sensorState`)

La primera que corresponda, en este orden:

| # | Condición | Insignia |
|---|---|---|
| 1 | `ultimo_mensaje_en` nulo | «Sin confirmar» (gris) |
| 2 | El sensor está fuera de servicio | «Fuera de servicio» (rojo) |
| 3 | El nodo está «sin señal» | «Desactualizado» (amarillo; los valores son los últimos recibidos) |
| 4 | Tiene activa «dispositivo sin actividad» | «Sin actividad · {n} min» (amarillo) |
| 5 | La última lectura es inválida | «Lectura inválida» (amarillo) |
| 6 | Nivel de la solución | «Nivel bajo» (rojo) o «Normal» (verde) |
| 7 | Intensidad lumínica con la última lectura fuera del horario de luz | «Fuera del horario de luz» (gris, sin comparar) |
| 8 | Variable ambiental en un sector fuera de servicio | «Sector fuera de servicio» (gris, sin comparar: D-75 punto 7) |
| 9 | Sin umbral (ambientales) o sin rango (solución) | «Sin umbral efectivo» o «Sin rango definido» (gris) |
| 10 | Fuera | «Supera el máximo» o «Bajo el mínimo» (rojo) |
| 11 | Dentro | «En rango» (verde) |

- La comparación de 10 y 11 es la de la **última** lectura contra el umbral o el rango **actuales**, sin histéresis. Es lo que «queda»
  ahora (regla 3); la alerta, con su histéresis, va aparte, en «Alertas activas».
- Un sensor de la solución en un sector fuera de servicio se compara igual, y además lleva la marca «Sector fuera de servicio» (regla 8;
  D-75, punto 7).
- «Sensores con problema» cuenta los rojos.

### Tarjeta de un sensor

- El identificador y el sector (o «General»).
- La insignia.
- El último valor con su unidad y «hace N min» (con la hora exacta en el `title`); «—» si no tiene.
- El gráfico. Menos en el nivel, que muestra «Informa «bajo» desde las HH:MM» o «Nivel normal».
- En la luz, «Fotoperíodo de ayer: {h} h» con «Incompleto», «Sin umbral», «En rango» o «Fuera de rango» (regla 3). Si no está calculado,
  «Sin calcular (corre en la revisión periódica)».

### Gráficos (regla 4; D-76, punto 8)

- **SVG armado en el servidor**, en `iot/graficos.py`: `grafico_de_sensor(serie, franja, resumido) -> str`. Es una función pura, probada
  sin base, como `spark` del prototipo: 360 × 96, línea de la serie, franja del umbral o del rango con sus dos valores a la derecha, y un
  punto en el último valor. `role="img"` y `aria-label` con la variable y el período.
- **Hasta 24 horas** (1, 6, 24): las lecturas **válidas** del período, en orden.
- **7 y 30 días**: los resúmenes horarios. La línea es el promedio y la franja sombreada, del mínimo al máximo. El texto del prototipo:
  «Más de 24 horas: se grafica el promedio de cada hora (línea) y su mínimo y máximo (franja), con los resúmenes horarios.».
- Una consulta para todas las series del panel (lecturas o resúmenes), no una por sensor.
- La franja es la del umbral o el rango **actual**. Sin umbral, no hay franja. Sin datos en el período, «Sin lecturas en este período».

### Actuadores (regla 5; `actState` y `estInf`)

- Columnas: equipo (tipo e identificador, sector), estado informado («{estado} desde las HH:MM», con «Cambiado en el invernadero»; o
  «Desconocido · El nodo todavía no informó su estado»), situación y compatibilidad.
- Situación, en orden: «Fuera de servicio», «Sin confirmar», «Sin actividad» (con la alerta activa), «Configuración incompatible»,
  «Operativo». «Comando pendiente», con IOT-05.
- Acción: «Ver equipo» (la ficha, IOT-CNS-HDW). «Emitir comando», con IOT-05 (regla 11).

### Refresco (regla 9; D-76, punto 8)

- El cuerpo del panel (`<div id="panel">`) se pide de nuevo con HTMX cada 30 segundos, solo si la pestaña está visible:
  `hx-get` a la misma URL con `hx-trigger="every 30s [document.visibilityState === 'visible']"` y `hx-swap="outerHTML"`.
- «Actualizar» hace lo mismo a mano. El selector de período cambia `?periodo=` y reemplaza el panel.
- Sin JavaScript, la pantalla es la misma página completa: se actualiza recargándola.
- Abrir o refrescar el panel no dispara la revisión periódica ni escribe nada (regla 10).

### Enlaces de las alertas del IoT (D-62; disparador «Cuando existan actuadores, comandos y reglas del IoT», punto 4)

En `IotConfig.ready()`, `registrar_enlace_de_alerta(CODIGOS_DE_ALERTAS_IOT, enlaces_de_alertas_iot)`, en `iot/servicios/alertas_iot.py`,
con **una consulta** para toda la lista (por `AlertaIot`). Nunca un enlace a un 403: Agrónomo y Gerente consultan todo lo del módulo en su
alcance.

| Alerta | Enlace | Detalle (texto debajo del título) |
|---|---|---|
| Con equipo (`hardware`) o con lectura (`telemetria` → su sensor) | La ficha del equipo (`hardware/<id>/` de IOT-02, con `?invernadero=`) | La descripción de la alerta |
| «Nodo sin comunicación» | `iot:monitoreo` del invernadero | La descripción |
| «Dispositivo no registrado» de un identificador que era de un equipo dado de baja del sistema | La ficha de ese equipo (que ofrece «Reactivar», IOT-02) | «{identificador} era de {equipo}, dado de baja el DD/MM» |
| «Dispositivo no registrado», otro | A quien opera, el alta con `?identificador=` (IOT-02, regla 12 de IOT-ALT-HDW); a quien solo consulta, `iot:monitoreo` | La descripción |

En la tabla de alertas del panel, la de un equipo dado de baja suma dos botones para quien opera: «Reactivar» (la ficha) y «Registrar
reemplazo» (el alta con el identificador) (regla 7).

### Datos que lee y no escribe

`umbral_efectivo` sin PRD-01 devuelve `None` (sin registrante): el panel dice que no hay umbral. Las pruebas usan
`variedades_presentes_de_prueba`.

## Pantallas

Guía visual: `docs/prototipos/iot/`. Buscá la función y leé solo esa parte.

| Pantalla | Función en el prototipo | Tarea |
|---|---|---|
| Monitoreo (encabezado del nodo, avisos, indicadores, alertas, sensores, actuadores, umbral) | `monitoreo`, `sensCard`, `sensorState`, `actState`, `estInf`, `compatB`, `refRange`, `SEV`, `RNG`, `RSUM` | IOT-04 |
| Gráfico | `spark` (y `series`, solo para entender la forma: sus datos son al azar) | IOT-04 |

**Lo que difiere del prototipo (manda el CU, L7; D-61):**

- «Ver parámetros IoT» lleva a Configuración también para el Agrónomo, en solo lectura. En el sistema, los parámetros se ven en el panel y
  la pantalla de configuración es del Gerente (D-76, punto 9).
- El selector de período es un `<select>` nativo: se usa el desplegable propio (D-24).
- La situación de los sensores suma «Fuera de servicio» y «Fuera del horario de luz» (reglas 3 y 8), y un sensor de la solución en un sector
  fuera de servicio se sigue comparando (D-75, punto 7).
- El prototipo no muestra las variedades que componen el umbral, solo las que fijan cada límite: se agregan (regla 6).

## Para más adelante

- **IOT-05:** «Comandos pendientes» en los indicadores y en los actuadores; «Emitir comando» desde la fila (regla 11).
- **IOT-06:** el enlace a las reglas de actuación del invernadero (IOT-CNS-RGL, regla 11).

## Solo prototipo

Los de `docs/prototipos/iot/README.md`, «Solo prototipo». En esta pantalla, además: las series de `series` (generadas al azar), el
`case 'refresh'` que mueve los valores al azar, las horas relativas fijas («hace 12 min», «a las 14:10») y los datos de `DB.umb` y
`DB.alertas`.
