# Escenarios del IoT de punta a punta (y guion de la defensa)

Las situaciones que se prueban con InfoPonia y los dos flujos de Node-RED (`node-red/`), de punta a punta: qué preparar, qué tocar y qué
tiene que pasar. Sirven para la **verificación a mano** de IOT-03 a IOT-07 y como **guion de la defensa** del trabajo final. Cada escenario
cita el caso de uso que muestra. Lote I3 (22/11/2026); el lote I4 sumó la orden de mantenimiento al escenario 7 y los escenarios 15 y 16.

## Antes de empezar (una vez)

1. InfoPonia corriendo, con un Agrónomo a cargo del invernadero «Norte», un Técnico asignado y variedades presentes (un lote activo o una
   siembra a realizar), para que haya **umbral efectivo**.
2. El sistema IoT de «Norte» registrado (IoT · Sistema IoT), con el rango de la solución de 18,0 a 24,0 °C, y los equipos del flujo
   registrados con sus identificadores (`node-red/README.md`, sección 4).
3. Node-RED con los dos flujos, arrancado con `INFOPONIA_URL` e `INFOPONIA_TOKEN`.
4. En otra terminal, la revisión periódica: `python manage.py revision_iot --cada 30` (D-71). En la defensa en Render, el cron encendido
   (disparador «Cuando se arme el cron único»).
5. Para que los escenarios de comandos no tarden: Configuración operativa · Módulo IoT, **reintentos 1 e intervalo 10 s**, y **lecturas de
   confirmación 2**. Al terminar, volver a los valores iniciales (3, 60 y 3).
6. Abiertas, en pestañas: IoT · Monitoreo, IoT · Comandos, IoT · Reglas de actuación y la campana. En otra ventana (privada), la sesión
   del Técnico de «Norte», en su Inicio.

## Escenarios

| # | Escenario | Qué hacer | Qué tiene que pasar | Caso de uso |
|---|---|---|---|---|
| 1 | El nodo se conecta | Desplegar los flujos | En menos de un minuto: nodo «En línea», sensores con su última lectura y su gráfico, actuadores con su estado, compatibilidad «Compatible» | IOT-ENT-INF, IOT-CNS-LEC |
| 2 | Condición de riesgo | Lecturas · «Temperatura alta (35 °C)» | La lectura sale del umbral: alerta «Fuera de umbral efectivo» en la campana y en el panel, con el valor y el límite | IOT-ENT-INF (5a) |
| 3 | Respuesta automática | Con una regla «temperatura supera el máximo → Ventilador: Encender» (crearla en Reglas de actuación) y la temperatura alta del escenario 2 | A la segunda lectura fuera (confirmación) InfoPonia emite el comando; Node-RED lo retira, lo ejecuta y el ventilador queda «Encendido». La regla muestra «Se cumple» y el comando, «Ejecutado», con origen en la regla | IOT-ENT-INF (6a), IOT-ALT-RGL, IOT-RSV-CMD |
| 4 | Sin repetir | Dejar la temperatura alta | La regla **no** vuelve a emitir mientras siga cumpliéndose (6b) | IOT-ENT-INF (6b) |
| 5 | Vuelta a la normalidad | Con otra regla «vuelve a quedar dentro → Ventilador: Apagar»; «Volver a lo normal» | Cuando la lectura vuelve a más de la histéresis del límite, se resuelve la alerta y la segunda regla apaga el ventilador | IOT-ENT-INF (5b, 6a) |
| 6 | Comando manual | Comandos · Emitir: Ventana · Fijar posición 40 | «Pendiente»; en unos segundos, «Ejecutado» y la ventana «posicion:40» con su hora | IOT-EMT-CMD, IOT-RSV-CMD |
| 7 | Falla del actuador | Comandos (Node-RED) · «Fallar cada intento»; emitir un comando | Cada intento falla y se reintenta; al último: comando «Fallido», actuador «Fuera de servicio», alerta crítica «Comando fallido» que nombra la orden de mantenimiento (OT-NNNN) y, en la vuelta siguiente de la revisión, el correo. El Técnico recibe el aviso y ve la orden en su Inicio; la ficha del ventilador la muestra «a realizar» | IOT-RSV-CMD (4a, 4b, 4b.4) |
| 8 | El nodo no reconoce el comando | «Rechazar (no reconoce)»; emitir un comando | «Fallido» sin reintentos; la acción pasa a incompatible, alerta «Configuración incompatible»; el actuador sigue activo y la acción deja de ofrecerse | IOT-RSV-CMD (4f) |
| 9 | Caída del nodo | Detener los flujos con un comando pendiente | A los minutos sin comunicación (más la vuelta de la revisión): alerta crítica «Nodo sin comunicación» y su correo; el comando **no** consume intentos. Al volver, se resuelve la alerta y el comando se ejecuta | IOT-ENT-INF (\*b), IOT-RSV-CMD (2a.1a) |
| 10 | Modo local | Lecturas · «Modo local» | El panel avisa el modo local; las reglas no se evalúan y los comandos esperan sin consumir intentos. «Modo remoto»: las reglas empiezan de cero | IOT-ENT-INF (1b, 6d), IOT-RSV-CMD (2d) |
| 11 | Equipo desconocido | Lecturas · «Equipo no registrado (co2)» | Lectura rechazada y alerta «Dispositivo no registrado»; desde la alerta, «Registrar» con el identificador cargado; después, sus lecturas se aceptan | IOT-ENT-INF (3a), IOT-ALT-HDW |
| 12 | Nivel de solución bajo | Lecturas · «Nivel de solución bajo» | Alerta crítica y su correo en la vuelta siguiente de la revisión | IOT-ENT-INF (5g), D-71 |
| 13 | Cancelar un comando trabado | «No responder»; emitir; esperar a que venza el intento; Cancelar | Antes de vencer, «Cancelar» explica cuánto falta; después, el comando queda «Cancelado» y la ventana admite otro | IOT-CNL-CMD |
| 14 | Desconectar el sistema | Sistema IoT · Desactivar | Se cancelan los comandos pendientes, se resuelven las alertas; Node-RED recibe 403 y no reintenta. Activar: vuelve todo, con las reglas desde cero | IOT-DSC-SIS, IOT-ACT-SIS |
| 15 | Cancelar la orden | Después del 7 (para seguir, volver a activar el ventilador): ficha del ventilador · Órdenes de mantenimiento · «Cancelar orden», con un motivo | La orden queda «cancelada»; el Técnico recibe el aviso con el motivo; el ventilador sigue «Fuera de servicio» y la alerta sigue activa | PROD-CNL-ORD (desde el IoT, D-79) |
| 16 | Volver a activar con la orden | Con el ventilador fuera de servicio y su orden a realizar (el 7 sin el 15): en Node-RED, «Ejecutar»; ficha del ventilador · «Volver a activar», con «Cancelarla» marcada | El ventilador vuelve a «Activo», la alerta se resuelve y la orden queda «cancelada», con el aviso al Técnico. Con «Mantenerla», la orden sigue «a realizar» | IOT-MOD-HDW (regla 8) |

## Al terminar

- Configuración operativa · Módulo IoT: volver a 3 reintentos, 60 s de intervalo y 3 lecturas de confirmación.
- En Render, apagar el cron de la revisión y Node-RED (D-71, punto 4).
