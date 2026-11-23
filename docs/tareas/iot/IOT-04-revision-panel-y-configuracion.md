# IOT-04 · Revisión periódica, panel de monitoreo y configuración IoT

Estado: hecha (a la espera de su PR) | App: iot (y la pantalla de configuración de maestros) | Rama: feature/iot-04-revision-y-panel | Ronda: IoT 1

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

Hay una migración nueva (`core` 0024, solo `choices`): `python manage.py migrate`. Los datos de la base local ya están cargados con `python manage.py cargar_datos_de_verificacion --solo iot` (contraseña por el prompt o por
`INFOPONIA_CONTRASENA_DE_PRUEBA`, nunca como argumento): «Norte» con su sistema IoT, sus siete equipos, el umbral efectivo y **un día entero de lecturas de ayer** (temperatura y luz; de anteayer, la temperatura), y «Sur», sin
Agrónomo y sin sistema. Cuentas: el **Agrónomo de «Norte»** (`agronomo@prueba1.local`: «Norte» ya existía antes de unificar los cargadores; en una base nueva es `agronomo@prueba3.local`) y el **Gerente** que ya tenés (`prueba3@gmail.com`
en la base del autor). Necesitás Node-RED con el flujo de lecturas (`docs/api/nodo/node-red/README.md`) y, para el correo, el servidor de correo configurado en `.env` (como en USR-08) o, si no, revisar que la salida diga
«pendientes sin servidor de correo». Si ya probaste IOT-03 hoy, es normal que haya alertas viejas.

1. Con Node-RED mandando, en otra terminal: `python manage.py revision_iot --cada 60`. Cada minuto, una línea de hora, una por sistema («Norte: … alertas generadas · … resueltas · … resúmenes · … fotoperíodos · … lecturas borradas») y la de
   correos. La primera corrida resume las horas de ayer y de anteayer (decenas de resúmenes) y calcula el fotoperíodo de ayer (1 fotoperíodo); las siguientes dicen 0.
2. Como el Agrónomo, IoT · Monitoreo: el nodo «En línea», los sensores agrupados por variable con su último valor y su gráfico de 24 horas. Esperá 30 segundos sin tocar nada: los valores cambian solos. Abrí «Parámetros IoT» y esperá otros 30 segundos:
   mientras está abierto, no se refresca (cerralo y vuelve a refrescarse). El selector de invernadero y el de período no se cierran solos.
3. Cambiá el período a «Última hora» y a «Últimos 7 días»: el segundo dice que grafica los resúmenes horarios y dibuja la franja de mínimo a máximo. «Actualizar» pide el panel en el momento.
4. En Node-RED, «Nivel de solución bajo»: aparece la alerta crítica en el panel («Informa «bajo» desde las HH:MM» en el sensor) y, en el minuto siguiente, la revisión manda el correo («Notificada por correo» en el panel y «Correos: 1 enviado» en la salida).
   Dejala activa: la revisión siguiente no lo vuelve a mandar.
5. Detené Node-RED: a los 3 minutos (más la vuelta de la revisión), «Nodo sin comunicación», crítica, con su correo; el panel dice «El nodo no se comunica desde hace …» y los sensores, «Desactualizado». Volvé a arrancar Node-RED: la alerta se resuelve con el primer mensaje.
6. «Equipo no registrado (co2)»: aparece «Dispositivo no registrado» con el botón «Registrar este equipo». Después «Volver a lo normal»: a los 5 minutos la revisión la resuelve (la salida dice «1 resuelta»).
7. En la campana, la alerta de un sensor lleva a la ficha del equipo; la de «no registrado», al alta con el identificador cargado (en minúsculas).
8. Con el Gerente, «Configuración» · «Configuración operativa», al final, la sección «Módulo IoT» con sus cinco grupos. Poné el fin del horario de luz igual al inicio: error en el campo («El fin tiene que ser posterior al inicio.») y no guarda nada. Poné «1,55» en una
   histéresis: error; «1,5»: entra. Bajá la retención a 1: guarda con el aviso «Parámetros guardados. Rigen desde el próximo intento y la próxima lectura.» y una advertencia amarilla («La próxima revisión periódica borrará las lecturas anteriores al … »). En el
   panel del Agrónomo, los parámetros muestran el valor nuevo.
9. Con la retención en 1, esperá la revisión siguiente: borra las lecturas de anteayer (21/11, de la temperatura) y la salida dice cuántas. Ya con sus resúmenes: en «Últimos 7 días» siguen los gráficos. Volvé la retención a 7.
10. La tarjeta de la luz dice «Fotoperíodo de ayer: 10 h» con «En rango». (Lo calcula la revisión desde la 01:00 del día siguiente: el día en curso nunca se calcula, D-76 punto 5. `--ahora` sirve para simular otro momento: `python manage.py revision_iot --ahora 2026-11-24T01:30`.)
11. En «Auditoría», `revision_periodica_iot` con las alertas generadas o resueltas y las lecturas borradas; y `modificacion_configuracion` con el antes y el después de lo que cambiaste (las histéresis, como texto).
12. Con el Gerente, Monitoreo de «Sur»: «Sur no tiene Sistema IoT» y «Registrar Sistema IoT» (lo opera el Gerente). Monitoreo de «Norte»: el Gerente solo consulta, sin botones de operación, con el aviso de quién recibe las alertas; «Modificar parámetros» lo lleva a Configuración.
    Entrá como el Agrónomo: no ve «Modificar parámetros» y `/configuracion/` le da 403.
13. Sin JavaScript (o con el botón «Ver» del período): el panel se ve entero y se actualiza recargando.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Los 11 pasos. La revisión periódica (`iot/servicios/revision.py`: `revisar(ahora)` con sus seis pasos de \*b, el correo de las críticas y la auditoría `revision_periodica_iot`) y el comando `revision_iot` (`--ahora`, `--cada`). El panel de monitoreo
(`iot/servicios/monitoreo.py`, `iot/graficos.py`, `iot/views_monitoreo.py` y las plantillas `iot/monitoreo/`), la pestaña «Monitoreo» (primera del módulo; `/iot/` redirige a ella) y `enlaces_de_alertas_iot` (registrado en `IotConfig.ready()`). La sección
«Módulo IoT» de Configuración (`maestros/servicios/configuracion.py`, `forms.py`, `views.py` y `_parametros.html`). Concurrencia, datos de verificación (`iot/verificacion.py`: «Sur» y las lecturas de ayer y anteayer) y esta documentación.

**Pruebas.** `iot/tests/`: `test_revision_iot` (22), `test_revision_resumenes` (44), `test_revision_correos` (28, 2 de ellas `@tag("concurrencia")`), `test_comando_revision_iot` (12), `test_enlaces_alertas_iot` (11), `test_graficos` (10), `test_iot_cns_lec` (52), `test_monitoreo_vistas` (36),
`test_revision_concurrencia` (4, `@tag("concurrencia")`) y lo sumado a `test_verificacion` (5); `maestros/tests/test_adm_mod_cfg_iot.py` (40, 3 de concurrencia). Comandos de «Hecho cuando»:
- `python manage.py test iot maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **2948 pruebas, OK**.
- `python manage.py test iot --keepdb --tag concurrencia` → **28 pruebas, OK**.
- Además: `python manage.py test maestros --keepdb --tag concurrencia` → 41, OK; `python manage.py makemigrations --check --dry-run`: sin cambios.
- **Maestros no cambió:** antes del paso 8, la suite de `maestros` daba 1134 (y 38 de concurrencia), todas en verde; después, 1169 (y 41): la diferencia son las pruebas nuevas, y ninguna prueba existente se modificó.
- **Concurrencia verificada con el orden invertido:** con la revisión tomando el nodo y los sensores antes que el invernadero, fallan las tres pruebas con barrera de bloqueo (un deadlock y dos aserciones: `0 != 1` y `0 != 2`); la del correo no depende del orden de bloqueos: con la marca de «enviado» cargada después de enviar (D-76 punto 7),
  falla (los dos mandan). Se volvió al orden correcto.
`test_infoponia` se recreó una vez con `--noinput` por la migración de `core`.

**Migración.** `core/migrations/0025_iot_revision_periodica_accion.py` (solo `choices`). Ninguna en `iot` ni en `maestros`; ningún modelo nuevo; ninguna dependencia.

**Fuera de «Permitido» (avisado en el control previo y aprobado):** en `core/models.py`, además de la acción, `ACCIONES_DE_NEGOCIO` (lo exige `test_d36_cada_accion_esta_clasificada_…`) y las `ETIQUETAS` de las claves de la revisión y de los 14 parámetros del IoT (las de IOT-03 que faltaban: `origen`,
`sistema`, `mensaje`, `identificador`, `alertas_generadas`); en `maestros/forms.py`, `GRUPOS_IOT` (las etiquetas y ayudas de los 14, una sola fuente para la pantalla de configuración y el panel); los cambios de `assertRedirects` de dos pruebas de `iot` (destino de `/iot/`; en la de sistema también el nombre y el docstring,
que decían «Sistema IoT»).

**Lo que se implementó distinto de lo escrito (para `docs/temas_abiertos.md`).**
- **Paso 9 de la «Verificación a mano» vs D-76, punto 5:** el paso decía que `--ahora` calculaba «el fotoperíodo de hoy»; D-76 dice que el día en curso nunca se calcula (un día D, desde D+1 a la 01:00). Manda D-76 y el paso quedó corregido (paso 10).
- **El correo se reserva antes de enviar** (D-76 punto 7 carga `correo_enviado_en` después): con un `UPDATE` condicional fuera del envío, así dos revisiones simultáneas no mandan el mismo correo. Costo: si el proceso muere entre reservar y enviar, ese correo se pierde (nunca hay duplicados), y mientras dura el envío el panel muestra
  «Notificada por correo». Si el envío falla (o lanza una excepción) se libera y se suma un intento; al quinto, `logger.error` con el id de la alerta. `intentos_correo` cuenta fallos.
- **Alertas del Gerente en el panel (regla 7 de IOT-CNS-LEC vs reparto de MAE-02, R007):** el panel usa `consultar_alertas(actor, …)` (opción a, como dice el documento) y el Gerente que no opera solo recibe las `para_gerente`: con un Agrónomo activo, su panel dice «0 alertas». Para que no engañe, el bloque de alertas muestra «Las alertas de este invernadero las recibe
  {Agrónomo}; vos las recibís si no tiene un Agrónomo activo.». La alternativa (opción b: una consulta propia del panel para que el Gerente vea todas) queda a decidir con el análisis.
- **Advertencia 5b:** se muestra tras guardar con el estilo de advertencia de la regla 5 (`alert-warn`) y una sola vez; viaja por la sesión y no por `django.contrib.messages`, porque `core` dibuja todo mensaje que no es de error con el estilo de éxito y esta tarea no toca `core`.
- **Guardados simultáneos desde la pantalla (límite conocido, igual que MAE-04):** el formulario manda todos los campos, así que un formulario viejo puede pisar con su valor un campo que otra persona acaba de cambiar (gana el último). El servicio, que solo toca lo que recibe, no pierde cambios (prueba de concurrencia).
- **Alta desde la alerta:** el enlace «Registrar este equipo» lleva el identificador **en minúsculas** (el de la clave de la alerta), no como lo escribió el nodo.
- **Fila nueva «Sin lecturas»** en la tabla «Situación de un sensor» de `consultar_lecturas.md`: un sensor con último mensaje pero sin lecturas (la retención ya las borró). A sumar a la tabla del extracto.
- **Un agrónomo inactivo no recibe el correo** (se pide cuenta activa y con email); si la alerta no tiene a quién mandarse, suma un intento y deja un `logger.warning` con el id de la alerta. D-76 no lo dice.
- **Auditoría de la revisión:** los afectados son solo las alertas (como dice el extracto): una corrida que solo borra lecturas deja `afectados` vacío; el sistema va en `datos`. `ahora` va como texto ISO.
- **Retención:** el «solo un `DELETE` por sistema» es un `queryset.delete()` del ORM, que lee los ids y borra por lotes (las claves foráneas `PROTECT` impiden el borrado rápido).
- **Fotoperíodo:** una lectura inválida no suma luz y tampoco corta la serie (D-76: «se toman las lecturas válidas»).
- **Sin sesión con HTMX:** el proyecto no tiene patrón (solo para la contraseña temporal, con `HX-Redirect`): manda el `LoginRequiredMiddleware` y HTMX meterá la pantalla de inicio de sesión dentro del panel. No se inventó uno.
- **El menú lateral** sigue apuntando a `/iot/` (que redirige a «Monitoreo»): mejora menor.
- **El identificador de cada sensor del panel** no es un enlace a su ficha (solo los actuadores tienen «Ver equipo»).

**Pantallas: lo que se corrigió del prototipo (D-61).**
- `sensorState` compara la última lectura con el umbral y no tiene «Fuera de servicio», «Fuera del horario de luz» ni «Sector fuera de servicio»: manda `consultar_lecturas.md` (tabla de 11 filas, en su orden).
- El botón de plegar cada grupo de sensores (`grp`) no se implementa: los grupos van siempre abiertos (si fueran `<details>` abiertos, el refresco automático no correría nunca); el único plegable es el bloque de parámetros, y el refresco espera mientras esté abierto.
- El `<select>` nativo del período y del invernadero pasa al desplegable propio de D-24 (con el nativo de respaldo y un botón «Ver» sin JavaScript); el `setInterval` y el «refrescar» al azar del prototipo pasan a HTMX cada 30 s, con la pestaña visible.
- «Ver parámetros IoT» (un enlace a Configuración) pasa a un bloque plegable de solo lectura en el panel, con «Modificar parámetros» solo para el Gerente (D-76 punto 9). Se suman las variedades que componen el umbral, el aviso de quién recibe las alertas y el escape de todo texto.
- Configuración: las histéresis de temperatura admiten un decimal (el prototipo pedía enteros; manda el modelo); «Descartar cambios» (`cfg-reset`) no se implementa (recargar la pantalla vuelve a lo guardado) y el Agrónomo no entra a la pantalla (la ve en el panel).

**Datos que quedaron cargados en la base local** (`cargar_datos_de_verificacion --solo iot`; idempotente; no se tocó al Administrador ni la auditoría): el invernadero **«Sur»** (sin Agrónomo y sin sistema IoT: lo opera el Gerente); las lecturas de **ayer** (22/11) de `norte/sectorA/temperatura` y `norte/sectorA/luz` y las de **anteayer** (21/11) de la
temperatura, una cada 5 minutos y de día entero (288 por día y sensor). Cuentas: el Agrónomo de «Norte» (`agronomo@prueba1.local`) y el Gerente existente; no se creó ninguna cuenta. **Se borraron 75 lecturas de ayer** (temperatura y luz de «Norte», de las pruebas con Node-RED de IOT-03; no eran origen de ninguna alerta ni
regla; una de la temperatura quedó) para poder dejar el día entero (CLAUDE.md, «Datos para la verificación a mano»). El nodo sigue sin comunicación registrada y los sensores quedan «sin actividad» hasta que Node-RED mande.
