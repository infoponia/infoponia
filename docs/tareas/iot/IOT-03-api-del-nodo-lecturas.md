# IOT-03 · API del nodo I: token, lecturas, estados, modo y anuncio

Estado: pendiente | App: iot | Rama: feature/iot-03-api-del-nodo | Ronda: IoT 1

Depende de: **IOT-02** (el sistema, el hardware, `core/enlaces.py` y `recalcular_compatibilidad`) e **INV-03** (`umbral_efectivo`,
`docs/api/variedades.md`). Si alguna no está mergeada, frená. **No depende de PRD-01:** sin él, `variedades_presentes` no tiene
registrante, todo invernadero queda «sin umbral efectivo» (extensión 5c) y las pruebas usan `variedades_presentes_de_prueba`
(`docs/api/variedades.md`). Tampoco depende de USR-10: esta tarea no manda correos (D-71).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Es el **primer hito demostrable** del IoT (`docs/tareas/ronda_iot_1.md`, sección 1): el nodo central (Node-RED en las
pruebas a mano) se identifica con su token y manda lecturas, estados, su modo y el anuncio de sus equipos; InfoPonia los valida, guarda las
lecturas, genera y resuelve las alertas que dependen de cada mensaje y responde con el resultado de cada elemento, según el contrato
`docs/api/nodo/` v1 (D-70, D-74). Además completa la lista y la ficha de Hardware con la última lectura y la situación. Todavía no hay
revisión periódica (IOT-04), comandos (IOT-05) ni reglas (IOT-06).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-ENT-INF | Entregar información | docs/casos_de_uso/iot/entregar_informacion.md | Solo las partes de IOT-03 (Índice y «Reparto»): sin \*b (IOT-04) ni el paso 6 y 6a a 6d (IOT-06) |

## Leer

- Caso de uso: el extracto de la tabla: el Índice, **el texto del caso de uso salvo \*b y 6a a 6d**, y la sección «Cómo se aplica en la
  ronda» completa. De `docs/casos_de_uso/iot/hardware.md`, «Cómo se aplica», los puntos «Compatibilidad», «Alerta «dispositivo no
  registrado»» y «Consulta (CNS)». De `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco», «Conectividad».
- Contrato: **todo** `docs/api/nodo/`: `README.md`, `mensajes.md`, `respuestas_y_errores.md` y `ejemplos/` (el `README.md` y los JSON). De
  `node-red/`, solo el `README.md` para la verificación a mano.
- Modelo: docs/modelo/iot.md («SistemaIoT», «Hardware», «NodoCentral», «Sensor», «Actuador», «EquipoAnunciado», «Telemetria», «AlertaIot»,
  «Tipos de alerta del IoT», «Parámetros IoT de ConfiguracionOperativa», «Reglas que tocan al IoT»).
- Decisiones: D-70, D-71 (puntos 3 y 5), D-72, D-74, D-75, D-65 (`core/enlaces.py`), D-05, D-28, D-30, D-36, D-37, D-44, D-56 (auditoría
  con actor `None`).
- API: docs/api/alertas.md (secciones 2 a 4), docs/api/variedades.md («Umbral efectivo» y la fábrica `variedades_presentes_de_prueba`).
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `sensorState`, `actState`, `estInf`, `hwBadge` y la rama de lista
  y de ficha de `hardware` (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md (solo para la lista y la ficha de Hardware).
- Código a leer:
  - todo `iot/` (lo que dejaron IOT-01 e IOT-02), en particular `iot/servicios/compatibilidad.py`, `iot/servicios/hardware.py`,
    `iot/catalogo.py` y `iot/tests/fabricas.py`;
  - `core/enlaces.py` (`resumen_de`), `core/models.py` (acciones de auditoría y cómo registra un proceso con actor `None`);
  - `maestros/servicios/alertas.py` (`asegurar_alerta_de_estado`, `resolver_alerta_de_estado`, `bloquear_invernadero_para_alertas`);
  - `inventario/servicios/variedades.py` (`umbral_efectivo`) e `inventario/tests/fabricas.py` (`variedades_presentes_de_prueba`);
  - `config/urls.py` y, en `config/settings.py`, `MIDDLEWARE` y `CACHES`; `core/middleware.py` (`ContrasenaTemporalMiddleware`) y cómo
    `core/views.py` usa `login_not_required`.

## Límites

- No crea modelos (los creó IOT-01). **El índice único `(sensor, medida_en)` de `Telemetria` (D-74, punto 6) lo crea IOT-01.** Si la
  migración inicial de `iot` ya mergeada no lo tiene, frená y avisá: en ese caso, y solo en ese, se agrega con una migración de `iot`
  `00NN_telemetria_unica` (el permiso lo da el estudiante en ese momento). Cualquier otra columna que falte: frená, es un cambio de D-72.
  → revisá docs/disparadores.md: cierra la parte de IOT-03 del punto 3 de «Cuando existan actuadores, comandos y reglas del IoT» y deja
  abierto su punto 5 (nuevo en el lote I2a).
- Migraciones: una de `core`, solo de `choices`, con la acción `entrega_informacion_iot`:
  `00NN_iot_entrega_de_informacion_accion`. **Ninguna en `iot` ni en `maestros`** (salvo el caso del índice de arriba).
- Permitido fuera de la app:
  - `config/urls.py`: una línea, `path("api/iot/v1/", include("iot.api.urls"))`;
  - `core/models.py`: solo la acción de auditoría y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_iot_1.md`.
- Dependencias nuevas: ninguna (D-70, punto 2: ni Django REST Framework ni otra biblioteca).
- Fuera de alcance: la revisión periódica, el correo y el panel de monitoreo (IOT-04); los comandos y `explica_un_comando` (IOT-05); las
  reglas de actuación, `evaluar_reglas_de_la_lectura` y `al_volver_a_remoto` (IOT-06): quedan escritas, sin hacer nada, con su docstring
  «Se completa en IOT-NN». **Nunca** se guarda, se audita ni se registra el token.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **El contrato en código (`iot/api/`, sin vistas todavía).** `limites.py`, `respuestas.py`, `reloj.py`, `autenticacion.py` y
   `traduccion.py`, tal cual el extracto («La API») y `respuestas_y_errores.md` (orden de verificación, códigos, textos de la sección 4b).
   - `traduccion.py` verifica solo la **forma**: la envoltura de cada mensaje (claves exactas; lista; hasta 500 es aparte), cada elemento
     (objeto, campos conocidos, `identificador` presente y con la forma de la regla 2 de IOT-ALT-HDW, `valor` o `estado` presente) y el
     anuncio entero (clase, comandos del catálogo, sin repetir identificadores ni comandos, un sensor sin `comandos`). Las fechas, los
     valores y el equipo los verifican los servicios, porque dependen del sensor.
   Pruebas, en `iot/tests/test_api_traduccion.py`: una por regla de forma de cada mensaje, incluidos `NaN` (json inválido), un campo
   desconocido arriba (400 con `campo`) y en un elemento (`mal_formada`), un identificador de 65 caracteres y uno con espacios
   (`mal_formada`, D-75 punto 5), un anuncio con un comando fuera del catálogo y con un identificador repetido en mayúsculas distintas
   (400 con `indice` y `campo`). `contar_pedido`: el 120 pasa, el 121 da `Retry-After` con los segundos que faltan del minuto; el minuto
   siguiente vuelve a empezar; dos resúmenes no se mezclan.
2. **Servicios del nodo y de las alertas** (`iot/servicios/nodo.py` y `alertas_iot.py`). `sistema_por_resumen`, `registrar_comunicacion`,
   `registrar_modo`, `al_volver_a_remoto` (vacía) y los dos ayudantes de alertas (reutilizá el de IOT-02 si existe).
   Pruebas (`test_iot_ent_inf_estados.py`, clase `IotEntInfModoServicioTests`, y `test_iot_ent_inf_lecturas.py` para la comunicación): un
   sistema dado de baja no se encuentra por su resumen; la comunicación actualiza `ultima_comunicacion` y resuelve «nodo sin comunicación»
   (postcondición a); el modo se guarda, `cambio` falso si se repite, sin auditoría si no cambió; `asegurar_alerta_iot` no crea un segundo
   `AlertaIot` para una alerta que ya existía.
3. **Lecturas** (`iot/servicios/lecturas.py`). Los 11 pasos de «Una lectura» del extracto, en ese orden, con `contexto_del_mensaje`
   calculado una vez por pedido.
   Pruebas (`test_iot_ent_inf_lecturas.py`, `IotEntInfLecturasServicioTests`), una por postcondición (b a h, t, z) y por extensión (3a a 3f,
   4a a 4c, 5a a 5g), con los nombres del extracto. Además: la histéresis (sale apenas pasa el máximo; entre el máximo y máximo − h sigue
   activa; a más de h se resuelve) y la histéresis con un umbral angosto y con un umbral de un solo valor (D-75, punto 2); la variable del
   umbral vacía no compara (punto 3); sin umbral se resuelve la alerta activa (punto 4); el sector fuera de servicio no compara la
   temperatura pero sí genera «nivel de solución bajo» (punto 7); una lectura atrasada resuelve «sin actividad» y no genera «lectura
   inválida»; una repetida (mismo sensor y `medida_en`) es `duplicada` y no toca nada; una de un sensor dado de baja es
   `equipo_dado_de_baja` con la alerta «no registrado» de clave `id:<minúsculas>`; dos rechazos del mismo identificador no crean dos
   alertas y el segundo actualiza `AlertaIot.ultimo_mensaje_en` (D-76, punto 3); la descripción de cada alerta con el texto del extracto («Alertas: textos y origen»); `AlertaIot` con `telemetria` o
   `hardware` según la tabla. Usá `variedades_presentes_de_prueba` para tener umbral.
4. **Estados** (`iot/servicios/estados.py`). Los 5 pasos de «Un estado» y `explica_un_comando` (devuelve falso).
   Pruebas (`test_iot_ent_inf_estados.py`, `IotEntInfEstadosServicioTests`): postcondiciones m a p y t; «en falla» pasa a fuera de servicio
   y no crea orden de mantenimiento; el primer estado operativo no marca «cambiado en el invernadero», el segundo distinto sí, el mismo
   repetido no cambia nada (D-75, punto 1); `nivel:60` y `posicion:-15` se aceptan, `nivel:alto` y `encendido` para un sensor son
   `estado_invalido`; un estado de un equipo no registrado lleva el estado en la descripción de la alerta.
5. **Anuncio** (`iot/servicios/anuncios.py`).
   Pruebas (`test_iot_ent_inf_anuncio.py`, `IotEntInfAnuncioServicioTests`): postcondiciones r y s; el anuncio reemplaza al anterior; un
   actuador que deja de anunciarse queda `sin_verificar` y se resuelve su alerta; los identificadores sin registrar no generan alertas y
   se ofrecen en el alta (la consulta de IOT-02 los lista); el anuncio vacío deja todo `sin_verificar`.
6. **Vistas y rutas** (`iot/api/vistas.py`, `iot/api/urls.py`, la línea de `config/urls.py`). Las cuatro rutas y la de 404, con el orden de
   verificación de `respuestas_y_errores.md`, sección 3.
   Pruebas:
   - `iot/tests/test_api_nodo.py` (`ApiNodoVistaTests`): cada fila de la tabla de códigos (incluido `WWW-Authenticate`, `Allow` y
     `Retry-After`); que no hace falta sesión ni token CSRF; que un sistema desconectado responde 403 y no registra la comunicación; que un
     400 tampoco la registra y un lote vacío sí; que un error inesperado en una lectura (simulado con `mock`) da `error_interno` en esa y
     procesa las demás; que un pedido sin sesión no redirige a «Iniciar sesión» (`LoginRequiredMiddleware`); **que el token no aparece en
     ningún registro** (`assertLogs("iot.api")` sobre un pedido con rechazos y comparar
     que el texto del token no está), ni en `RegistroAuditoria`.
   - `iot/tests/test_api_ejemplos.py` (`ApiEjemplosTests`): arma el escenario de `docs/api/nodo/ejemplos/README.md`, manda cada
     `*.pedido.json` y compara con su `*.respuesta.json` campo por campo salvo `servidor_en`; arma los que solo tienen respuesta (sin token,
     token inválido, desconectado, el pedido 121, 262.145 bytes, 501 lecturas, `text/plain`, `GET`, ruta inexistente). Lee los archivos
     desde `settings.BASE_DIR / "docs/api/nodo/ejemplos"`: si cambia un ejemplo, la prueba lo sigue.
7. **Concurrencia** (`@tag("concurrencia")`, `iot/tests/test_api_concurrencia.py`): dos pedidos a la vez con la misma lectura (una
   `aceptada` y la otra `duplicada`, una sola telemetría); dos lecturas a la vez fuera de umbral del mismo sensor (una sola alerta); dos
   rechazos a la vez del mismo identificador desconocido (una sola alerta «no registrado»); una lectura mientras se modifica el sensor con
   IOT-MOD-HDW (sin deadlock ni 500).
8. **Hardware** (lo que completa IOT-03, sección final de «Cómo se aplica»): `tiene_lecturas` real; la última lectura y la situación por
   alertas en la lista y la ficha; el estado informado, el modo y la conectividad reales. Pruebas en `test_iot_cns_hdw.py` (las que ya
   existen siguen pasando): con lecturas y alertas creadas por la API, la lista muestra la última lectura y la situación; sin consultas por
   fila (`assertNumQueries` con tres equipos).
9. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - el patrón `docs/patrones/api_de_dispositivos.md` (D-70, «Consecuencias»): cómo se escribe una ruta de la API del nodo (traducción,
     orden de verificación, una transacción por elemento, respuestas, registro sin token, pruebas con los ejemplos), para que IOT-05 lo siga;
   - en `docs/disparadores.md`: marcar hecha la parte de IOT-03 del punto 3 de «Cuando existan actuadores, comandos y reglas del IoT»;
   - marcar IOT-03 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`.
   Lo que haya quedado distinto de lo escrito va a
   `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el paso 8 (la última lectura y la situación en Hardware; se anota en `temas_abiertos.md`).
No se recortan: el token sin guardar ni registrar, el orden de verificación, una transacción por elemento, la unicidad de la lectura, las
pruebas con los ejemplos ni las de concurrencia.

## Hecho cuando

- Un nodo con el token de un sistema activo manda lecturas, estados, modo y anuncio, y recibe las respuestas de `docs/api/nodo/` v1, que
  coinciden con todos los ejemplos.
- Cada lectura se guarda con su marca de validez, y genera o resuelve las alertas de lectura inválida, umbral efectivo (con histéresis),
  solución y nivel según el extracto; las atrasadas, las de un sensor fuera de servicio y las que no se comparan (5c a 5e) no generan
  alertas.
- Un identificador desconocido o de un equipo dado de baja genera una sola alerta «dispositivo no registrado» por identificador.
- Reenviar un lote no duplica lecturas (lo garantiza la base); dos mensajes simultáneos no duplican alertas.
- Los estados cambian el estado del equipo, su estado informado y sus alertas; el modo y el anuncio quedan registrados y la compatibilidad
  de los actuadores se recalcula.
- Un token inválido, un sistema desconectado o un pedido fuera de los límites se rechaza sin procesar nada; el token no aparece en la base,
  la auditoría ni los registros.
- Pruebas: `iot/tests/test_api_traduccion.py`, `test_iot_ent_inf_lecturas.py`, `test_iot_ent_inf_estados.py`,
  `test_iot_ent_inf_anuncio.py`, `test_api_nodo.py`, `test_api_ejemplos.py`, `test_api_concurrencia.py` y lo que se suma a
  `test_iot_cns_hdw.py`.
- Comando de pruebas:
  python manage.py test iot core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva (`core`, solo de `choices`): `python manage.py migrate`. Cuentas y datos: **ya están cargados en la base local** por
`python manage.py cargar_datos_de_verificacion --contrasena <la de tu CLAUDE.local.md>` (`docs/patrones/datos_de_verificacion.md`): el invernadero «Norte» con
`agronomo@prueba1.local` y `capataz@prueba1.local` (sin Técnico), «Sector A» y «Sector B», un insumo de «Repuestos de hardware», la variedad «Lechuga Crespa» con
stock y una siembra «a realizar» (umbral efectivo: temperatura 18 a 26 °C, humedad 60 a 80 % HR, luz 10.000 a 30.000 lux). Node-RED instalado y los dos flujos
importados (`docs/api/nodo/node-red/README.md`, secciones 1 a 3).

0. Entrá como `agronomo@prueba1.local`, en IoT · Sistema IoT registrá el sistema de «Norte» y **copiá el token** (se muestra una sola vez). Volvé a correr
   `cargar_datos_de_verificacion`: carga el rango de la solución (18,0 a 24,0 °C) y los siete equipos del flujo (los identificadores de
   `docs/api/nodo/node-red/README.md`, sección 4). El token no pasa por el comando.
1. Arrancá Node-RED con `INFOPONIA_URL` e `INFOPONIA_TOKEN` e importá el flujo: «Configuración de equipos» queda en verde. En IoT · Hardware están los siete equipos,
   «Sin confirmar».
2. En menos de un minuto, IoT · Hardware: el nodo está «En línea» y los sensores dejan de estar «Sin confirmar»: cada uno muestra su última lectura y hace cuánto.
3. «Anunciar ahora» y después «Ventana sin FIJAR_POSICION (anuncio)» + «Anunciar ahora»: la ventana pasa a incompatible y aparece la alerta
   «Configuración incompatible». «Volver a lo normal» + «Anunciar ahora»: se resuelve.
4. «Temperatura alta (35 °C)»: la situación del sensor pasa a «Fuera de umbral» y aparece «Fuera de umbral efectivo» en la campana, con el valor y el máximo efectivo
   (26 °C). «Volver a lo normal»: se resuelve cuando la lectura queda a más de 1 °C dentro del umbral.
5. «Lectura inválida (999 °C)»: aparece «Lectura inválida» en la campana. «Volver a lo normal»: se resuelve con la lectura siguiente.
6. «Nivel de solución bajo»: aparece la alerta crítica (sin correo hasta IOT-04) y el sensor muestra «Nivel bajo». «Solución caliente (27 °C)»: «Solución fuera de rango».
7. «Equipo no registrado (co2)»: la lectura vuelve rechazada (barra de depuración de Node-RED) y aparece «Dispositivo no registrado»; desde la alerta se puede
   registrar el equipo (IOT-02).
8. «Humedad en falla»: el sensor queda «Fuera de servicio» con «Dispositivo en falla». «Ventilador encendido»: la ficha del actuador muestra «Encendido» con la hora;
   después «Ventilador apagado»: aparece «Cambiado en el invernadero».
9. Detené `runserver` dos minutos y volvé a arrancarlo: Node-RED reintenta (estado «falla …: reintento en …»), vacía la cola y las lecturas de esos minutos llegan
   atrasadas, sin alertas.
10. Regenerá el token en InfoPonia: Node-RED recibe 401 y no reintenta. Cargá el nuevo y reiniciá Node-RED: vuelve a «En línea».
11. En «Auditoría» están los registros `entrega_informacion_iot` (sin token) y los registros del servidor no muestran el token.
12. Después del merge, en Render: la dirección de la API que muestra el registro del sistema empieza con `https://` (si no, es la configuración del proxy de USR-09:
    anotalo en `temas_abiertos.md`) y Node-RED, apuntado a esa dirección, recibe 200.

No se prueba a mano el motivo `equipo_dado_de_baja` (necesita un equipo dado de baja y la baja es de IOT-06): se prueba con IOT-06; por ahora lo cubren las pruebas
automáticas (`test_api_ejemplos.py`, `test_iot_ent_inf_lecturas.py`).

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** La API del nodo v1 (`iot/api/`: límites, respuestas, reloj, autenticación, traducción de la forma y las cuatro vistas con su ruta 404), los servicios
(`nodo.py`, `alertas_iot.py`, `lecturas.py`, `estados.py`, `anuncios.py` y la auditoría común `auditoria_nodo.py`), `iot/textos.py` y la acción de auditoría
`entrega_informacion_iot`. La lista y la ficha de Hardware muestran la última lectura, la situación por alertas y el estado informado, sin consultas por fila
(`resumen_de_equipos`: dos consultas). `evaluar_reglas_de_la_lectura`, `al_volver_a_remoto` y `explica_un_comando` quedan escritas sin hacer nada («Se completa en IOT-05 / IOT-06»).

**Pruebas.** `iot/tests/`: `test_api_traduccion` (40), `test_iot_ent_inf_lecturas` (76 con comunicación y alertas), `test_iot_ent_inf_estados` (25), `test_iot_ent_inf_anuncio` (15),
`test_api_nodo` (24), `test_api_ejemplos` (20, con todos los ejemplos del contrato), `test_api_concurrencia` (5, `@tag("concurrencia")`) y lo sumado a `test_iot_cns_hdw`.
Comandos de «Hecho cuando»: `test iot core … --exclude-tag concurrencia --exclude-tag migracion` → 1548 pruebas, OK; `test iot --tag concurrencia` → 22, OK.
`makemigrations --check --dry-run`: sin cambios.

**Migración.** `core/migrations/0020_iot_entrega_de_informacion_accion.py` (solo `choices`). **`main` ya trajo otra `0020` (PRD-02) y D-83:** al mergear hay que regenerar la mía (ver el texto del PR).

**Fuera de «Permitido» (con autorización expresa, en un commit aparte, el primero):** `core/verificacion.py`, `core/management/commands/cargar_datos_de_verificacion.py`,
`core/tests/test_verificacion.py`, `iot/verificacion.py` (+ su prueba y el registro en `IotConfig.ready()`), `docs/patrones/datos_de_verificacion.md` y la regla de `CLAUDE.md`
que dice dónde vive el comando.

**Cambio sobre código de IOT-02 ya mergeado.** `iot/servicios/compatibilidad.py` usa `alertas_iot.asegurar_alerta_iot` / `resolver_alerta_iot`: una sola forma de crear un `AlertaIot`.
Mismo comportamiento y mismo orden de bloqueos (D-82); las pruebas de IOT-02, incluidas las dos `test_d82_…`, pasan sin cambios. También cambian docstrings de `hardware.py` y
`sistemas.py`, y `situacion_de` (con un parámetro opcional) y `alertas_activas_del_equipo` (suma las alertas de las lecturas del sensor).

**Lo que se implementó distinto de lo escrito (para `docs/temas_abiertos.md`).**
- La auditoría: el extracto pone `cambios` dentro de `datos`, y D-36 solo admite `datos` y `cambios` arriba: manda D-36 (decisión del estudiante). `sistema` va como `referencia(sistema)`.
- Resolver «nodo sin comunicación» al recibir un mensaje se audita con `mensaje: "comunicacion"` (el extracto no lo prevé: solo lista lectura, estado, modo y anuncio).
- `ETIQUETAS` de `RegistroAuditoria` no se amplió: la pantalla de Auditoría muestra las claves de `datos` y `cambios` tal cual (como IOT-02).
- La frase de «Depende de» («sin PRD-01, todo invernadero queda sin umbral») quedó vieja: PRD-01 ya registra `variedades_presentes`.
- La descripción de «lectura inválida» no tenía formato exacto: «{id} · {valor} {unidad}, fuera de la calibración ({mín} a {máx})».
- `temp-vieja` (un sensor dado de baja) no se carga con el cargador hasta que IOT-06 traiga `baja_hardware`.

**Pantallas: lo que se corrigió del prototipo (D-61).** `sensorState` calcula la situación comparando la última lectura con el umbral («Supera el máximo», «En rango»,
«Desactualizado»): manda el caso de uso, que la saca de las alertas activas («Sin actividad», «Lectura inválida», «Fuera de umbral», «Fuera de rango», «Nivel bajo»). Se agregó
una columna «Último dato» a la lista (el prototipo no la tiene): la última lectura y hace cuánto, o el estado informado con su hora y la marca «cambiado en el invernadero».
Las cajas «Solo prototipo» no existen (`sim-modo`, `sim-ok`…).

**Datos que quedaron cargados en la base local** (`cargar_datos_de_verificacion`): cuentas `agronomo@prueba1.local` y `capataz@prueba1.local` (contraseña de tu `CLAUDE.local.md`); invernadero
«Norte» (sin Técnico) con «Sector A» y «Sector B»; insumo «Repuesto de sensor»; cultivo «Lechuga», variedad «Crespa» con su semilla habilitada y 1.000 de stock; una siembra «a realizar».
Falta, a mano: registrar el sistema IoT de «Norte» (paso 0) y volver a correr el comando. No se tocó al Administrador ni se borró nada.
