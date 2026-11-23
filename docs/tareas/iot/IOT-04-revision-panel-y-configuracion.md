# IOT-04 · Revisión periódica, panel de monitoreo y configuración IoT

Estado: pendiente | App: iot (y la pantalla de configuración de maestros) | Rama: feature/iot-04-revision-y-panel | Ronda: IoT 1

Depende de: **IOT-03** (la API, las lecturas, `AlertaIot.ultimo_mensaje_en` y `alertas_iot.py`), **USR-10** (`core.correo.enviar_correo` y
`correo_configurado`, D-54), **MAE-02d** (`consultar_alertas` con `tipos`, `registrar_enlace_de_alerta`, `enlaces_de_alertas` y la ruta
`alertas:ir`, D-62 con su tercera enmienda; MAE-02c, la pantalla de consulta, ya está mergeada) y **MAE-04**
(la pantalla y el servicio de la configuración operativa). Si alguna no está mergeada, frená. **No depende de PRD-01:** sin él no hay umbral
efectivo y las pruebas usan `variedades_presentes_de_prueba` (`docs/api/variedades.md`). IOT-04 e IOT-05 son independientes entre sí
(`docs/tareas/ronda_iot_1.md`, sección 2).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Tres cosas que completan el primer hito del IoT:
- **La revisión periódica** (IOT-ENT-INF, extensión \*b): `python manage.py revision_iot`, a mano o repetida con `--cada` mientras se prueba
  con Node-RED. Detecta los sensores sin actividad y los nodos sin comunicación, resuelve los «no registrado» sin mensajes, resume las
  lecturas por hora, calcula el fotoperíodo, aplica la retención y manda por correo las alertas críticas (D-71). Sin cron job: el cron se
  arma al final y se enciende solo para presentar.
- **El panel de monitoreo** (IOT-CNS-LEC), que se refresca solo cada 30 segundos, y los enlaces de las alertas del IoT en la campana y en
  «Alertas» (D-62).
- **La sección «Módulo IoT» de la configuración operativa** (ADM-MOD-CFG), donde el Gerente ajusta los 14 parámetros.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-ENT-INF | Entregar información, **extensión \*b** (revisión periódica) | docs/casos_de_uso/iot/entregar_informacion.md | Solo \*b y el correo: lo demás es de IOT-03 e IOT-06 |
| IOT-CNS-LEC | Consultar lecturas (panel de monitoreo) | docs/casos_de_uso/iot/consultar_lecturas.md | Comandos pendientes y acciones de comandos y reglas: IOT-05 e IOT-06 |
| ADM-MOD-CFG | Modificar configuración operativa, **sección «Módulo IoT»** | docs/casos_de_uso/maestros/configuracion.md | Solo la sección del final; el resto lo hizo MAE-04 |

## Leer

- Casos de uso:
  - de `entregar_informacion.md`: el Índice, la extensión \*b y las reglas «Inactividad», «Fotoperíodo», «Resúmenes horarios»,
    «Retención» y «Alertas» del texto del caso de uso; y de «Cómo se aplica», «Reparto», «Alertas: textos y origen», «Bloqueos y
    concurrencia» y **«La revisión periódica»** completa;
  - `consultar_lecturas.md` completo;
  - de `configuracion.md`, solo la sección «ADM-MOD-CFG · Sección «Módulo IoT»»;
  - de `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco».
- Modelo: docs/modelo/iot.md («SistemaIoT», «Hardware», «NodoCentral», «Sensor», «Actuador», «Telemetria», «ResumenHorario y
  FotoperiodoDiario», «AlertaIot», «Tipos de alerta del IoT», «Parámetros IoT de ConfiguracionOperativa»).
- Decisiones: D-71, **D-76**, D-75 (punto 7), D-54, D-56 (puntos 4 y 6), D-62, D-41, D-24, D-25, D-28, D-29, D-36, D-37, D-44, D-47, D-61.
- API: docs/api/alertas.md (secciones 2 a 4, la sección 5 —la consulta de MAE-02c con el `tipos` de MAE-02d— y la sección 8), docs/api/variedades.md («Umbral efectivo» y
  `variedades_presentes_de_prueba`).
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `monitoreo`, `sensCard`, `sensorState`, `actState`, `estInf`,
  `compatB`, `refRange`, `spark`, `SEV`, `RNG`, `RSUM`, `config` y `CFGP`; en `act`, los casos `range`, `refresh`, `save-cfg` y `cfg-reset`
  (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - todo `iot/` (lo que dejaron IOT-01 a IOT-03), en particular `iot/servicios/alertas_iot.py`, `lecturas.py`, `sistemas.py`
    (`conectividad`), `iot/alcance.py`, `iot/apps.py` e `iot/tests/fabricas.py`;
  - `core/correo.py` (USR-10), `core/management/commands/proceso_diario.py` y `core/procesos.py` (la forma del comando y su salida),
    `core/models.py` (acciones de auditoría);
  - `maestros/servicios/alertas.py` (`consultar_alertas`, `enlaces_de_alertas`), `maestros/extensiones.py` (`Enlace`,
    `registrar_enlace_de_alerta`);
  - `maestros/servicios/configuracion.py`, `maestros/forms.py`, `maestros/views.py` y las plantillas de `maestros/templates/maestros/configuracion/`
    (la pantalla de MAE-04);
  - `inventario/servicios/variedades.py` (`umbral_efectivo`) e `inventario/tests/fabricas.py`.

## Lo que dejó IOT-03 (cambia lo escrito arriba)

- `iot/servicios/alertas_iot.py` (`asegurar_alerta_iot` y `resolver_alerta_iot`, que devuelven `ResultadoDeAlerta(alerta, creada)` y dejan el `AlertaIot`): usalas en la revisión;
  no llames a `maestros.servicios.alertas` directo para las alertas del IoT.
- `iot/servicios/auditoria_nodo.py` (`auditar_entrega`) es el modelo para auditar con `datos` y `cambios` (D-36). `revision_periodica_iot` lleva `sistema` como `referencia(sistema)`.
- `AlertaIot.ultimo_mensaje_en` ya se carga en cada rechazo de «dispositivo no registrado». Las alertas críticas nacen con `correo_enviado_en` nulo y `intentos_correo` en 0.
- Un mensaje que solo resolvió «nodo sin comunicación» se audita con `mensaje: "comunicacion"`.
- La lista y la ficha de Hardware ya muestran la última lectura y la situación por alertas (`resumen_de_equipos`): el panel no tiene que rehacerlo.

## Límites

- No crea modelos (los creó IOT-01, incluido `AlertaIot.ultimo_mensaje_en`, D-76 punto 3). Si falta una columna, frená.
  → revisá docs/disparadores.md: cierra «Cuando exista SistemaIoT», punto 0 del correo (D-54); la parte del panel de «Cuando exista el caso
  de uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)»; y el punto 4 de «Cuando existan actuadores, comandos y reglas del
  IoT» (enlaces). Deja abierto «Cuando se arme el cron único», punto 2 (el cron, al final).
- Migraciones: una de `core`, solo de `choices`, con la acción `revision_periodica_iot`: `00NN_iot_revision_periodica_accion`. **Ninguna en
  `iot` ni en `maestros`.**
- Permitido fuera de la app:
  - `maestros`: la sección «Módulo IoT» en el formulario, la plantilla y la validación de `modificar_configuracion` (reglas 3b, 4b y la
    advertencia 5b), **solo** lo que dice `configuracion.md`, con sus pruebas en `maestros/tests/test_adm_mod_cfg_iot.py`. Las pruebas
    existentes de `maestros` no se modifican y tienen que seguir pasando;
  - `core/models.py`: solo la acción de auditoría y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_iot_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna. Ni bibliotecas de gráficos (los gráficos son SVG del servidor, D-76 punto 8), ni Celery, ni hilos, ni
  `django-crontab`: la revisión es un comando de Django.
- Fuera de alcance: el cron job de Render (disparador «Cuando se arme el cron único»); los comandos y su reintento (IOT-05); las reglas de
  actuación (IOT-06); un enlace en el correo (D-76, punto 7); un historial de alertas resueltas.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Revisión periódica: alertas por tiempo** (`iot/servicios/revision.py`). `revisar(ahora) -> ResumenDeRevision`, con una función por
   paso de «La revisión periódica» del extracto (`entregar_informacion.md`) y cada sistema activo en su transacción. En este paso, los
   pasos 1 a 3 (sin actividad, nodo sin comunicación, «no registrado» sin mensajes).
   Pruebas (`iot/tests/test_revision_iot.py`, `RevisionIotServicioTests`, con `ahora` fijo y fábricas):
   - postcondición u y cada paso con su borde (justo en el plazo no genera; un minuto después sí);
   - los «sin confirmar» y los nodos que nunca se comunicaron no generan;
   - un sensor fuera de servicio no genera «sin actividad»;
   - un sistema desconectado se saltea;
   - un invernadero inactivo no recibe alertas (la API de `maestros` devuelve `None`) y no rompe;
   - «no registrado» se resuelve recién cuando `ultimo_mensaje_en` es más viejo que el plazo;
   - un sistema que falla (simulado con `mock`) no frena a los demás y queda en el resumen;
   - dos corridas seguidas con el mismo `ahora` no duplican nada (idempotencia);
   - la auditoría `revision_periodica_iot` solo cuando cambió algo.
2. **Resúmenes, fotoperíodo y retención** (pasos 4 a 6). Pruebas (`iot/tests/test_revision_resumenes.py`):
   - el resumen de la hora en curso y de las dos anteriores se recalcula; una hora vieja sin resumen se calcula y una con resumen no se
     toca;
   - mínimo, promedio y máximo solo de las válidas; las inválidas se cuentan aparte; una hora solo con inválidas deja los tres nulos;
   - el nivel no tiene resumen;
   - el fotoperíodo con el cálculo de D-76 punto 5 (un día con luz de 8 a 18 h y una lectura por minuto da 10,00 h);
   - un hueco mayor que los minutos sin actividad lo marca incompleto y no compara;
   - el día de hoy nunca se calcula y el de ayer recién a la 01:00;
   - fuera del rango genera la alerta de fotoperíodo, dentro la resuelve, sin umbral no toca nada;
   - la retención borra las viejas, conserva las que tienen `AlertaIot` o están en una regla (crealas con la fábrica) y nunca borra
     resúmenes ni fotoperíodos;
   - con la revisión sin correr durante más días que la retención (simulado con `ahora`), una corrida resume y calcula todo lo que falta
     **antes** de borrar: ninguna hora con lecturas queda sin resumen.
3. **Correos** (`enviar_correos_pendientes(ahora)` en `revision.py`, llamado al final de `revisar`, fuera de las transacciones) y la plantilla
   `iot/templates/iot/correo/alerta_critica.txt`, con el asunto y el cuerpo de D-76, punto 7. Pruebas (`iot/tests/test_revision_correos.py`,
   con `mock` de `core.correo.enviar_correo`):
   - una crítica sin correo se manda una vez y la segunda corrida no la repite;
   - va al Agrónomo o, sin Agrónomo activo, a cada Gerente activo;
   - una falla suma un intento y al quinto deja de intentar con `logger.error`;
   - sin servidor configurado no se intenta;
   - una resuelta antes de mandarse no se manda;
   - las advertencias y las informativas no se mandan;
   - `enviar_correo` se llama fuera de una transacción (`connection.in_atomic_block` falso dentro del `mock`);
   - el correo no tiene el token ni datos de otro invernadero.
4. **Comando** `iot/management/commands/revision_iot.py` (`--ahora`, `--cada`, salida y código de salida como el extracto). Pruebas
   (`iot/tests/test_comando_revision_iot.py`, con `call_command`): con y sin `--ahora`; `--ahora` inválido; `--cada` con un `mock` que corta
   el ciclo a la segunda vuelta; código 1 si un sistema falla; sin sistemas, «No hay sistemas IoT activos».
5. **Enlaces de las alertas del IoT** (`enlaces_de_alertas_iot` en `alertas_iot.py`, registrado en `IotConfig.ready()`), con la tabla de
   `consultar_lecturas.md`. Pruebas (`iot/tests/test_enlaces_alertas_iot.py`): el enlace y el detalle de cada fila de la tabla para el
   Agrónomo y para el Gerente que solo consulta (nunca un 403: seguí el enlace con el cliente de pruebas y verificá 200); sin la alerta en la
   lista, `{}` sin consultar; `assertNumQueries` igual con una y con tres alertas.
6. **Panel** (`iot/servicios/monitoreo.py` e `iot/graficos.py`). Pruebas:
   - `iot/tests/test_graficos.py`: el SVG con y sin franja, resumido y no, vacío, y que escapa el texto;
   - `iot/tests/test_iot_cns_lec.py` (`IotCnsLecServicioTests`): una por regla (1 a 8, 10 y 12); cada fila de la tabla «Situación de un
     sensor», en su orden; el sensor de la solución en un sector fuera de servicio se compara (D-75, punto 7); el umbral con las variedades
     que lo componen y las que fijan cada límite; sin umbral; los 14 parámetros; la misma cantidad de consultas con 1 y con 5 sensores; nada
     se escribe (ninguna fila cambia y no hay auditoría).
7. **Vistas, plantillas y pestaña.** `monitoreo/` en `iot/urls.py`; «Monitoreo» como primera pestaña y `/iot/` redirige a ella; el fragmento
   que se refresca cada 30 s (D-76, punto 8), el selector de período (desplegable propio, D-24) y «Actualizar»; respaldo sin JavaScript.
   Pruebas (`iot/tests/test_monitoreo_vistas.py`, `IotCnsLecVistaTests`): permisos (otros roles, 403; invernadero fuera del alcance, 404);
   el pedido HTMX devuelve solo el fragmento; el período se recuerda; el Gerente sin Agrónomo ve «Registrar Sistema IoT» y el que mira un
   invernadero con Agrónomo, no; el Agrónomo ve los parámetros sin «Modificar parámetros»; ningún botón lleva a un 403.
8. **Configuración: sección «Módulo IoT»** en `maestros`, con lo de `configuracion.md` (etiquetas, ayudas, mensajes, advertencia 5b y aviso al
   guardar). Pruebas (`maestros/tests/test_adm_mod_cfg_iot.py`): cada dominio de la regla 3b (el borde entra, uno más afuera da el error
   del campo); las histéresis de temperatura con un decimal (1,5 entra; 1,55 no); 4b; 5b advierte y guarda; todo o nada con un error en un
   parámetro del IoT y otro de producción; la auditoría con antes y después; el Agrónomo no entra (403). Después corré **toda** la suite de
   `maestros`: tiene que dar lo mismo que antes.
9. **Concurrencia** (`@tag("concurrencia")`, `iot/tests/test_revision_concurrencia.py`): una revisión y una lectura de la API a la vez sobre
   el mismo sensor (una sola alerta, sin deadlock); dos revisiones a la vez (ninguna duplica alertas, resúmenes ni fotoperíodos).
10. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
    - en `docs/disparadores.md`: tachar el punto 0 del correo de «Cuando exista SistemaIoT», la parte del panel de «Cuando exista el caso de
      uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)» y el punto 4 de «Cuando existan actuadores, comandos y reglas del IoT»;
    - marcar IOT-04 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`;
    - en `docs/estado.md`, la línea «Procesos» con `revision_iot` hecha.
    Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el gráfico de 7 y 30 días (paso 6; se anota en `temas_abiertos.md`). No se recortan: la
idempotencia de la revisión, el correo fuera de transacción con su límite de intentos, la retención con sus exclusiones ni la cantidad fija de
consultas del panel.

## Hecho cuando

- `python manage.py revision_iot` genera y resuelve las alertas por tiempo, resume, calcula el fotoperíodo, borra lo vencido y manda una sola
  vez el correo de cada alerta crítica; correrlo dos veces no cambia nada la segunda vez; `--cada 60` sirve para probar con Node-RED.
- El panel muestra, del invernadero elegido, el nodo, las alertas activas con su enlace, los sensores con su situación, su gráfico y el
  fotoperíodo, los actuadores, el umbral efectivo y los parámetros; se refresca solo cada 30 segundos; no escribe nada.
- Las alertas del IoT llevan, en la campana y en «Alertas», a la ficha del equipo, al alta con el identificador o al panel.
- El Gerente modifica los 14 parámetros en «Configuración operativa · Módulo IoT»; el Agrónomo los ve en el panel.
- Todas las pruebas de `maestros` que existían siguen pasando sin cambios.
- Pruebas: `iot/tests/test_revision_iot.py`, `test_revision_resumenes.py`, `test_revision_correos.py`, `test_comando_revision_iot.py`,
  `test_enlaces_alertas_iot.py`, `test_graficos.py`, `test_iot_cns_lec.py`, `test_monitoreo_vistas.py`, `test_revision_concurrencia.py` y
  `maestros/tests/test_adm_mod_cfg_iot.py`.
- Comando de pruebas:
  python manage.py test iot maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva (`core`): `python manage.py migrate`. Cuentas: Gerente y un Agrónomo a cargo de un invernadero con sistema IoT y
equipos registrados (IOT-02). Node-RED con el flujo de lecturas (`docs/api/nodo/node-red/README.md`). Para el correo, el servidor de correo
configurado en `.env` (como en USR-08) o, si no, revisar que la salida diga «sin servidor de correo».

1. Con Node-RED mandando, en otra terminal: `python manage.py revision_iot --cada 60`. Cada minuto, una línea por sistema.
2. IoT · Monitoreo (Agrónomo): el nodo «En línea», los sensores agrupados con su último valor y su gráfico de 24 horas; esperá 30 segundos
   sin tocar nada: los valores cambian solos.
3. Cambiá el período a «Última hora» y a «Últimos 7 días»: el segundo dice que grafica los resúmenes horarios.
4. En Node-RED, «Nivel de solución bajo»: aparece la alerta crítica en el panel y, en el minuto siguiente, la revisión manda el correo
   («Notificada por correo» en el panel). Dejala activa: la revisión siguiente no lo vuelve a mandar.
5. Detené Node-RED: a los 3 minutos (más la vuelta de la revisión), «Nodo sin comunicación», crítica, con su correo; el panel dice «El nodo
   no se comunica desde…» y los sensores, «Desactualizado». Volvé a arrancar Node-RED: la alerta se resuelve con el primer mensaje.
6. «Equipo no registrado (co2)» y después «Volver a lo normal»: a los 5 minutos la revisión resuelve «Dispositivo no registrado».
7. En la campana, la alerta de un sensor lleva a la ficha del equipo; la de «no registrado», al alta con el identificador cargado.
8. Con el Gerente, «Configuración» · «Configuración operativa»: la sección «Módulo IoT». Poner el fin del horario de luz igual al inicio: error
   en el campo. Bajar la retención a 1: la advertencia, y guarda. En el panel del Agrónomo, los parámetros muestran el valor nuevo.
9. `python manage.py revision_iot --ahora 2026-11-23T01:30` (o la fecha de mañana a la 01:30): calcula el fotoperíodo de hoy; el panel lo
   muestra como «Fotoperíodo de ayer» al día siguiente.
10. En «Auditoría», `revision_periodica_iot` con las alertas y las lecturas borradas.
11. Sin JavaScript, el panel se ve entero y se actualiza recargando.

## Cierre (la completa Claude Code al cerrar)
