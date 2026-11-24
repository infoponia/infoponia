# IOT-05 · Comandos: emitir, retirar, resolver con reintentos y cancelar

Estado: hecha | App: iot (y un valor de `Bitacora.TipoEvento` en produccion) | Rama: feature/iot-05-comandos | Ronda: IoT 1

Depende de: **IOT-03** (la API del nodo, sus reglas comunes y `explica_un_comando`) y **PRD-01** (`produccion.Bitacora`, padre de
`RegistroComando`). Si alguna no está mergeada, frená. **No depende de IOT-04**: las dos salen de IOT-03 (`docs/tareas/ronda_iot_1.md`,
sección 2). Si IOT-04 ya está, se completa también el panel (paso 7).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** El Agrónomo (o el Gerente donde no hay Agrónomo activo) **ordena una acción a un actuador** desde InfoPonia. El nodo
central la retira en su próxima consulta, la ejecuta y avisa el resultado. Si el actuador falla, InfoPonia **reintenta**; si agota los
intentos, deja el actuador fuera de servicio y avisa con una alerta crítica. Un comando trabado se **cancela**. Todo queda en la bitácora del
invernadero. Con el flujo de comandos de Node-RED se prueba de punta a punta. La orden de mantenimiento del escalamiento es de IOT-07; las
reglas que emiten solas, de IOT-06.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-EMT-CMD | Emitir comando | docs/casos_de_uso/iot/emitir_comando.md | Reglas activas del actuador (paso 4, 6b): vacías hasta IOT-06 |
| IOT-RSV-CMD | Resolver comando | docs/casos_de_uso/iot/resolver_comando.md | Sin la orden de mantenimiento (4b.4, 4b.4a, 4b.4b; IOT-07) |
| IOT-CNL-CMD | Cancelar comando | docs/casos_de_uso/iot/cancelar_comando.md | — |

## Leer

- Casos de uso: los tres extractos de la tabla, completos, **incluida su sección «Cómo se aplica»**. De
  `docs/casos_de_uso/iot/entregar_informacion.md`, «La API», «Alertas: textos y origen», «Auditoría» y «Bloqueos y concurrencia» (las reglas
  comunes de la API que dejó IOT-03). De `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco».
- Contrato: `docs/api/nodo/mensajes.md` (secciones 0, 5 y 6), `docs/api/nodo/respuestas_y_errores.md` completo, `docs/api/nodo/README.md`
  (sección 10) y, de `docs/api/nodo/ejemplos/`, el `README.md` y los JSON `comando*` y `error_metodo_no_permitido_comandos`. De
  `node-red/`, el `README.md` (sección 6b) para la verificación a mano; de `docs/api/nodo/escenarios.md`, los escenarios 6 a 9 y 13.
- Modelo: docs/modelo/iot.md («Catálogo de capacidades», «TipoActuador», «Accion», «Actuador», «Comando», «RegistroComando», «AlertaIot»,
  «Tipos de alerta del IoT», «Parámetros IoT»); docs/modelo/produccion.md («Bitacora» y la fila `Bitacora.TipoEvento` de los valores).
- Decisiones: **D-77**, **D-78**, D-70, D-71 (punto 3), D-72, D-74, D-75, D-50 (herencia de `Bitacora`), D-52, D-28, D-30, D-36, D-37, D-44,
  D-61.
- API: docs/api/alertas.md (secciones 2 a 4), docs/api/produccion.md (lo que exponga `Bitacora`).
- Patrones: docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md y, si IOT-03 lo dejó,
  docs/patrones/api_de_dispositivos.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `comandos`, `cmdForm`, `cmdBadge`, `mismoEstado`, `CMDV`,
  `CMDST`; en `act`, los casos `cmd-for`, `c-act`, `c-acc`, `emit` y `cf-*`; en `modalHtml`, la ventana `ccan:<id>` (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: todo `iot/` (lo que dejaron IOT-01 a IOT-03, y IOT-04 si está); `produccion/models.py` (`Bitacora` y su herencia) y sus
  fábricas; `core/models.py` (acciones de auditoría).

## Lo que dejó IOT-03 (cambia lo escrito arriba)

- `explica_un_comando(actuador, estado)` está en `iot/servicios/estados.py` y devuelve falso: completala (D-75, punto 1).
- Las rutas `comandos` y `comandos/<id>/resultado` hoy caen en la ruta que atrapa todo (`iot/api/urls.py`) y responden 404 `ruta_inexistente`: agregalas **antes** de ella.
- Seguí el patrón `docs/patrones/api_de_dispositivos.md` (`_atender`, `_recibir`, el orden de `docs/api/nodo/respuestas_y_errores.md`, sección 3) y la auditoría de `iot/servicios/auditoria_nodo.py`.
- El modo del nodo está en `NodoCentral.modo` (`remoto` o `local`): en `local` no se entregan comandos.

## Límites

- Crea modelos: **`RegistroComando`** (hija de `produccion.Bitacora`, `docs/modelo/iot.md`), con su migración de `iot`
  (`00NN_registro_comando`). Los demás ya existen (IOT-01). → revisá docs/disparadores.md: cierra la parte de IOT-05 de los puntos 1, 3 y 5
  de «Cuando existan actuadores, comandos y reglas del IoT».
- Migraciones:
  - `iot`: `00NN_registro_comando`;
  - `produccion`: una de `choices`, `00NN_bitacora_tipo_comando` (el valor `comando` de `Bitacora.TipoEvento`);
  - `core`: una de `choices`, `00NN_iot_comandos_acciones` (`emision_comando`, `cancelacion_comando`, `resolucion_comando_iot`).
- Permitido fuera de la app:
  - `produccion/models.py`: solo el valor `comando` de `Bitacora.TipoEvento` («Comando»), y su migración. Si el filtro de la bitácora
    (PROD-CNS-BIT) lista los tipos desde los `choices`, el nuevo aparece solo; no se toca su pantalla;
  - `core/models.py`: solo las tres acciones de auditoría y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_iot_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: la orden de mantenimiento automática y su aviso al Técnico (IOT-07); las reglas de actuación y la emisión automática
  (IOT-06); cancelar comandos al desactivar o dar de baja el sistema o el hardware (IOT-06, con `cancelar_comando_incluido`, que deja esta
  tarea).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migraciones.** `RegistroComando` (hija de `Bitacora`, `tipo_evento = comando`), con `comando`, `numero_intento` y
   `resultado`, y las tres migraciones de «Límites». Pruebas (`iot/tests/test_modelos_comandos.py`): crear un registro le pone el tipo
   `comando` y el invernadero del sistema; `lote` nulo; las restricciones de `Comando` que ya existían siguen (un pendiente por actuador).
2. **Emitir** (`iot/servicios/comandos.py`: `datos_para_emitir`, `validar_comando`, `resumen_de_comando`, `emitir_comando`; `emitir_comando.md`,
   «Cómo se aplica»). Pruebas (`iot/tests/test_iot_emt_cmd.py`, `IotEmtCmdServicioTests`):
   - una por postcondición (a a c), por extensión (1a, 3a, 4a, 6a a 6g, 8a, 8b) y por regla;
   - el Gerente no emite en un invernadero con Agrónomo activo y sí en uno sin él;
   - el comando del Gerente queda sin Agrónomo y la persona va en la auditoría;
   - el valor fuera del rango, no entero o de más (acción sin valor);
   - una acción incompatible no se ofrece;
   - el tiempo mínimo se mide desde el último ejecutado (D-78, punto 7).
3. **Cancelar** (`cancelar_comando`, `cancelar_comando_incluido`; `cancelar_comando.md`). Pruebas (`iot/tests/test_iot_cnl_cmd.py`):
   - reglas 1 a 5 y postcondiciones;
   - cancelable sin retirar y con el intento vencido; no cancelable dentro de la espera, con cuánto falta;
   - un resultado posterior es `ya_resuelto`.
4. **Retiro y resultado** (`retirar_comandos`, `registrar_resultado`; `resolver_comando.md`). Pruebas (`iot/tests/test_iot_rsv_cmd.py`,
   `IotRsvCmdServicioTests`):
   - una por postcondición (a a j, m a q) y por extensión (\*a, 2a, 2a.1a, 2b, 2c, 2d, 4a, 4b sin 4b.4, 4c, 4d, 4e, 4f);
   - un comando dentro de su espera no se vuelve a entregar;
   - el intento que vence con el nodo «sin señal» se descuenta (D-78, punto 2);
   - el último intento «sin respuesta» escala;
   - el rechazo marca la acción incompatible y un anuncio que la cubre la quita (D-78, punto 5);
   - `explica_un_comando` (D-78, punto 4) y el estado que llega con el resultado no queda «cambiado en el invernadero»;
   - la bitácora de cada hecho, con su número de intento (D-78, punto 3);
   - la alerta «comando fallido» crítica con `correo_enviado_en` nulo (la manda la revisión, D-71).
5. **Rutas de la API** (`comandos` y `comandos/<id>/resultado` en `iot/api/`). Pruebas:
   - `iot/tests/test_api_comandos.py`: 405 con `Allow: GET` y con `Allow: POST`; sin cuerpo en el `GET`; el retiro cuenta como
     comunicación; 404 `comando_inexistente` para el comando de otro sistema y para uno nunca entregado; 400 por cada campo del resultado;
   - en `iot/tests/test_api_ejemplos.py`, el escenario de comandos de `docs/api/nodo/ejemplos/README.md` y todos los ejemplos `comando*`.
6. **Concurrencia** (`@tag("concurrencia")`, `iot/tests/test_comandos_concurrencia.py`):
   - dos emisiones a la vez sobre el mismo actuador: una gana, la otra recibe 8a, sin 500;
   - dos retiros a la vez: cada comando se entrega una vez;
   - un retiro y una cancelación a la vez;
   - dos resultados iguales a la vez: uno `aceptado`, el otro `ya_resuelto`.
7. **Pantallas.**
   - Pestaña «Comandos» (`comandos/`), con la emisión, la lista, sus filtros y la ventana de cancelar, para quien opera; el resto, solo la
     lista.
   - «Emitir comando» desde la ficha del actuador (`?actuador=`).
   - El historial de comandos y «Comando pendiente» en Hardware (IOT-02); «Cancelar» en la ficha.
   - Si IOT-04 está mergeada: «Comandos pendientes» y «Emitir comando» en el panel.
   - Los textos de `emitir_comando.md` y `cancelar_comando.md`.
   Pruebas (`iot/tests/test_comandos_vistas.py`): permisos y alcance (otros roles, 403; fuera del alcance, 404; el Gerente con Agrónomo
   activo, solo lectura); el resumen con sus advertencias; el flujo con HTMX y sin él; ningún botón lleva a un 403.
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`, marcar hecha la parte de IOT-05 de los puntos 1, 3 y 5 de «Cuando existan actuadores, comandos y reglas
     del IoT»;
   - marcar IOT-05 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`;
   - completar `docs/patrones/api_de_dispositivos.md` con las rutas de comandos (un `GET`, una ruta con id), si IOT-03 lo dejó.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta son los filtros de la lista de comandos (se anota en `temas_abiertos.md`). No se recortan la
entrega una sola vez por intento, el descuento por «sin señal», la idempotencia del resultado, el escalamiento ni las pruebas de
concurrencia.

## Hecho cuando

- El Agrónomo emite un comando con su resumen y sus advertencias; nunca hay dos pendientes por actuador (lo garantiza la base).
- Un nodo con el flujo de comandos de Node-RED lo retira, lo ejecuta y el comando queda «Ejecutado», con el estado nuevo del actuador; las
  respuestas coinciden con los ejemplos.
- Los fallos se reintentan hasta agotar los intentos y entonces el actuador queda fuera de servicio con la alerta crítica; un rechazo marca
  la acción incompatible; una caída del nodo no consume intentos.
- Un comando trabado se cancela; uno en curso no, con el tiempo que falta.
- Cada hecho queda en la bitácora del invernadero y en la auditoría.
- Pruebas: `iot/tests/test_modelos_comandos.py`, `test_iot_emt_cmd.py`, `test_iot_cnl_cmd.py`, `test_iot_rsv_cmd.py`, `test_api_comandos.py`,
  los de comandos de `test_api_ejemplos.py`, `test_comandos_concurrencia.py` y `test_comandos_vistas.py`.
- Comando de pruebas:
  python manage.py test iot produccion core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`iot`, `produccion`, `core`): `python manage.py migrate`. Cuentas: un Agrónomo a cargo de un invernadero con sistema
IoT y los actuadores del flujo. Node-RED con los dos flujos (`docs/api/nodo/node-red/README.md`). Para no esperar, en Configuración
operativa · Módulo IoT: 1 reintento y 10 s de intervalo (al final, volver a 3 y 60).

Seguí `docs/api/nodo/escenarios.md`, escenarios 6, 7, 8, 9 y 13, y además:

1. Emitir «Ventilador · Encender» con el ventilador ya encendido: el resumen avisa que ya está en ese estado; confirmalo y queda
   «Ejecutado».
2. Emitir con el nodo en modo local (Node-RED de lecturas, «Modo local»): el resumen lo avisa; el comando queda pendiente con 0 intentos
   hasta «Modo remoto».
3. En la bitácora del invernadero (Producción · Bitácora), los registros de tipo «Comando» con cada intento.
4. En «Auditoría», `emision_comando`, `cancelacion_comando` y `resolucion_comando_iot`.
5. Después del merge, verificar en el log de Render que se aplicaron las tres migraciones.

## Cierre (la completa Claude Code al cerrar)


### Qué se hizo

- **Modelo y migraciones.** `RegistroComando` (hija de `produccion.Bitacora`, `iot` 0004); el valor `comando` de `Bitacora.TipoEvento` y su restricción (`produccion` 0005, solo `choices` y `CHECK`); las acciones `emision_comando`, `cancelacion_comando` y `resolucion_comando_iot` (`core` 0029, solo `choices`) con sus etiquetas.
- **Servicios** (`iot/servicios/comandos.py`): emitir (`datos_para_emitir`, `validar_comando`, `resumen_de_comando`, `emitir_comando`), cancelar (`cancelar_comando`, `cancelar_comando_incluido`, `segundos_para_cancelar`), el retiro (`retirar_comandos`) y el resultado (`registrar_resultado`), más la consulta de la pantalla (`listar_comandos`, `historial_del_actuador`, `comando_para_cancelar`). `explica_un_comando` (`estados.py`), `acciones_en_uso` y `acciones_con_historial` (`tipos_actuador.py`) y `tiene_comandos`/`tiene_comando_pendiente` (`hardware.py`) ya consultan comandos reales.
- **API del nodo:** `GET comandos` y `POST comandos/<id>/resultado` (`iot/api/`), con `traducir_resultado`.
- **Pantallas:** la pestaña «Comandos» (`iot/views_comandos.py`, `iot/templates/iot/comandos/`), «Emitir comando», el historial de comandos y «Cancelar» en la ficha del actuador, y «Comandos pendientes», la situación «Comando pendiente» y los botones de la fila en el panel de monitoreo.

### Pruebas

- Comando 1 (`iot produccion core`, sin concurrencia ni migración), **con `main` ya fusionado**: **2927 pruebas OK**.
- Comando 2 (`iot`, concurrencia): **37 OK**. `--tag migracion` de `iot produccion core`: 3 OK. `makemigrations --check`: sin cambios.
- Archivos nuevos: `test_modelos_comandos.py`, `test_iot_emt_cmd.py` (73), `test_iot_cnl_cmd.py` (22), `test_iot_rsv_cmd.py` (74), `test_api_comandos.py`, `test_comandos_concurrencia.py` (9), `test_comandos_vistas.py` (53), `test_recorrido_comandos.py`; además, los ejemplos y el escenario de comandos en `test_api_ejemplos.py`.
- **Prueba de concurrencia que protege el orden de bloqueo (D-82):** invertí temporalmente `emitir_comando` (invernadero antes que el tipo) y `test_d82_emitir_a_la_vez_que_se_modifica_el_tipo_de_ese_actuador_no_se_cruzan` falló con `deadlock detectado`; volví al orden correcto.
- **Un primer intento del comando paralelo (`--parallel`) terminó con `TypeError: cannot pickle 'traceback' object`** (el runner no puede mostrar un fallo). No se reprodujo: tres corridas paralelas y una en serie dieron todo OK. Queda anotado por si reaparece (¿una prueba que depende de la hora?).

### Cambios de pruebas existentes (la regla cambió con esta tarea; no se debilitó nada)

- `test_iot_cns_tac.py`, `test_regla_2_el_listado_hace_pocas_consultas`: `assertNumQueries(2)` pasa a **3**, porque `acciones_en_uso` ahora consulta comandos reales (una sola consulta para toda la lista de tipos, no una por tipo). Aprobado por el estudiante.
- `test_api_nodo.py`, `test_regla_404_las_rutas_de_comandos_...`: antes afirmaba que `comandos` era `ruta_inexistente` («por ahora, son de IOT-05»); ahora afirma que las dos rutas existen y que una ruta parecida sigue siendo 404.
- `test_monitoreo_vistas.py`, `test_monitoreo_es_la_primera_pestana_y_esta_activa`: la lista de pestañas suma «Comandos» (segunda).
- `test_iot_cns_lec.py`, `test_regla_5_los_indicadores_...`: «Comandos pendientes» ya existe (vale 0 sin comandos); antes se afirmaba que no existía.

### Decisiones

Propuesta de **D-97** al cerrar (M3, sin aplicar): el orden de bloqueo de emitir (tipo → invernadero → sistema → actuador, agregado a D-78 punto 11), qué audita el retiro (cada hecho que crea bitácora), el texto de «configuración incompatible» por un rechazo, y que un intento que el nodo respondió con «falló» no se vuelve a dar por «sin respuesta» (aclara D-78 punto 1).

### Lo que difiere de la documentación (para `temas_abiertos.md`)

1. `ahora` es un parámetro más en `datos_para_emitir`, `cancelar_comando_incluido` y `segundos_para_cancelar` (la firma del extracto no lo trae: los servicios no leen la hora).
2. La regla 2 y la regla 5 de IOT-CNL-CMD usan el mismo código (`comando_en_curso`) y el mismo mensaje: el servicio no distingue «se retiró hace un rato» de «se retiró entre la pantalla y la confirmación».
3. Los códigos de error de `validar_comando` los comparte IOT-06 (`accion_no_disponible`, `accion_incompatible`, `valor_requerido`, `valor_invalido`, `valor_de_mas`); están nombrados en su docstring.
4. Texto de la alerta «configuración incompatible» por un rechazo (no estaba escrito): «{tipo} {identificador} · el nodo rechazó {COMANDO} (acción «{acción}»)[: {detalle}]». Falta en `entregar_informacion.md`, «Alertas: textos y origen».
5. El contrato no define las razones de un `informado_en` inválido o futuro en el resultado: se usó «tiene que ser una fecha ISO 8601 con zona horaria» y «es más de 5 minutos posterior a la hora de InfoPonia». Falta en `respuestas_y_errores.md`, sección 4b.
6. La emisión usa una sola URL (`comandos/`, con `paso` = `refrescar`, `resumen` o `emitir`) en lugar de las tres rutas del plan; la ventana de cancelar es `comandos/<id>/cancelar/`.
7. La emisión bloquea el tipo antes que el invernadero (D-82): el extracto y D-78 punto 11 no nombran el tipo.
8. El filtro «Tipo» de la bitácora (`TIPOS_DE_FILTRO`, PROD-CNS-BIT) **no** ofrece «Comando» (no se tocó, por «Límites»): los registros se listan igual. Hay que sumarlo en otra tarea.
9. «Actuadores operativos» del panel no resta a un actuador que espera un comando (cuenta su situación sin el comando pendiente).
10. El retiro audita una vez por retiro, con los hechos juntos (`datos.hechos`), y no un registro por comando.

### Pantallas: lo que se corrigió del prototipo (D-61)

- **Sin «Descripción» ni resumen:** el prototipo no tenía la descripción (paso 5) ni el resumen antes de confirmar (paso 6). Se agregaron, con «Confirmar y emitir» y «Cambiar» (7a y 7b).
- **Las advertencias salían de inmediato** en el formulario; el caso de uso las pone en el resumen. Se muestran ahí, con sus textos de «Cómo se aplica», en el orden 6b a 6g (las 6b y 6c, informativas; el resto, de cuidado).
- **`mismoEstado` solo conocía cuatro estados:** se compara con `ESTADO_QUE_DEJA` (también nivel y posición).
- **«Solo prototipo»:** no se implementó el recuadro que simula la respuesta del nodo ni `sim-ok`, `sim-fail` y `sim-rech`.
- **Faltaban los estados vacíos, de error y de bloqueo** (sistema desconectado, actuador fuera de servicio, comando pendiente con «Cancelar»), la paginación de a 25, el celular y el respaldo sin JavaScript.
- **Al mirar las capturas (antes de que D-96 retirara la verificación visual; esa prueba y Playwright ya no están en la rama):** (1) el desplegable «Acción» deshabilitado usaba el `<select>` nativo (flecha y fondo distintos): ahora es el propio; (2) con un comando pendiente, «Acción» quedaba habilitada aunque «Ver resumen» no: ahora dice «No se puede emitir ahora»; (3) la opción del actuador «— con comando pendiente» partía el desplegable en dos líneas: ahora «· pendiente»; (4) «Limpiar filtros» no aparecía al filtrar con HTMX (solo se reemplaza la tabla): ahora se actualiza junto con ella (`hx-swap-oob`); (5) «Regla de actuación · RGL-11» se partía en tres líneas y «Podés cancelarlo en 59 s» dejaba una «s» huérfana; (6) en el panel, las acciones de una fila iban en dos líneas y las de otra en una.
- **Un hallazgo del recorrido, de servicio y no de pantalla:** un intento que el nodo respondió con «falló» se daba por «sin respuesta» en el retiro siguiente (segundo registro `intento_fallido` con el mismo número y, con el nodo sin señal, un descuento indebido). Se corrigió en `retirar_comandos` (el intento respondido se reconoce por su registro) y se sumaron 3 pruebas.
- **Migración corregida antes de aplicarla:** `sqlmigrate` mostró dos índices iguales sobre `comando_id` (el de la clave foránea y uno del modelo); se quitó el del modelo.

### Base local (CLAUDE.local.md)

No se tocó la base de desarrollo (ni datos ni usuario administrador). Las pruebas usan su propia base de pruebas, que se recreó una vez sin `--keepdb` y con `--noinput` para aplicar las tres migraciones nuevas. Las capturas visuales están en la carpeta temporal de la sesión.

### Merge con `main` (23/11/2026)

- Se trajo `main` (COM-02 #65 y CMP-02a #66, con D-96) y se resolvió un conflicto en `core/models.py` (etiquetas de auditoría): conviven las de comandos y las de pedidos.
- **Migraciones regeneradas** sobre las de `main` (`docs/patrones/trabajo_en_paralelo.md`; las mías no estaban aplicadas en ninguna base): `produccion` 0005 → **0006** (`main` ya tenía una 0005), `core` 0027 → **0029** (`main` trae 0027 y 0028) e `iot` 0004 (ahora depende de `produccion` 0006). Corrida sin `--keepdb`, con `--noinput`: se aplican y no hay cambios pendientes.
- **D-96 retira la verificación visual:** se borró `iot/tests/test_visual_comandos.py` (su base, `core/tests/visual.py`, ya no existe). Se conserva el recorrido, y la «Verificación a mano» pasa al estudiante.
- Mi propuesta de decisión pasó de D-96 a **D-97**.

## Verificación a mano

Hay tres migraciones nuevas (`iot` 0004, `produccion` 0006 y `core` 0029): `python manage.py migrate`; después `python manage.py runserver` y abrí `http://localhost:8000`. No hay datos cargados: creá a mano, en este orden, (a) un **Agrónomo** (Laura) a cargo del invernadero «Norte», un **Gerente** y un **Técnico**; un segundo invernadero «Libre» **sin Agrónomo**; (b) en «IoT · Sistema IoT» de «Norte», el sistema (anotá el token); (c) en «IoT · Hardware» de «Norte», dos actuadores con un insumo de «Repuestos de hardware» cada uno: `norte/sectorA/ventilador` (tipo «Ventilador», con un sector) y `norte/sectorA/ventana` (tipo «Ventana»); (d) en «Libre», un sistema y `libre/ventilador` (tipo «Ventilador»). Con el Gerente, «Configuración · Módulo IoT»: **1 reintento y 10 s de intervalo** (al final, volver a 3 y 60). Node-RED con los dos flujos (`docs/api/nodo/node-red/README.md`, secciones 1 a 4) y, en otra terminal, `python manage.py revision_iot --cada 30`. Si no tenés Node-RED, los pasos 5 a 12 se pueden cubrir con la API (`GET comandos` y `POST comandos/<id>/resultado`, con `Authorization: Bearer <token>`).

1. **Escenario 6 · Emitir un comando manual.** Con Laura, IoT → «Comandos»: elegí «Ventana · norte/sectorA/ventana» y la acción «Fijar posición»; aparece el campo «Valor (%)» con «Número entero entre 0 y 100 %.». Escribí 40, tocá «Ver resumen» y después «Confirmar y emitir». Tiene que verse el aviso «Comando CMD-n pendiente. El nodo lo retira en su próxima consulta…» y la fila «Pendiente», «0 de 2». En unos segundos, «Ejecutado»; en la ficha de la ventana (Hardware), «Posición 40» y el historial con el comando. *(Lo cubre: `test_recorrido_de_comandos_de_punta_a_punta` y `test_flujo_principal_…` de `test_comandos_vistas.py`.)*
2. **Advertencia «ya está en ese estado» (paso 1 de la tarea).** Con el ventilador ya «Encendido» (por el flujo de Node-RED), elegí «Encender» y «Ver resumen»: «Según el último estado que informó el nodo, el actuador ya está encendido…». Confirmá: queda «Ejecutado». *(Lo cubre: `test_ext_6c_…` y el recorrido.)*
3. **Errores de validación.** «Fijar posición» con 150, con 12.5 y con el campo vacío, y «Ver resumen»: el error junto al campo («Ingresá un número entero entre 0 y 100 %, sin decimales.» o «Ingresá el valor…») y ningún comando creado. Sin elegir actuador: «Seleccioná un actuador.». *(Lo cubre: `test_ext_6a_…` y `test_los_errores_van_junto_al_campo_y_no_se_escribe`.)*
4. **Tiempo mínimo entre comandos (6f).** Justo después de un comando ejecutado, emití otro al mismo actuador: el resumen advierte «El actuador cambió de estado hace… faltan n s… Podés emitirlo igual.» y deja confirmar. *(Lo cubre: `test_ext_6f_…` y el recorrido.)*
5. **Escenario 7 · Falla del actuador.** En Node-RED, flujo de comandos → «Fallar cada intento»; emití «Apagar» al ventilador. El primer intento falla (la fila sigue «Pendiente», «1 de 2»); al segundo queda «Fallido» con «El actuador falló en 2 intentos…», el ventilador pasa a «Fuera de servicio» y aparece la alerta crítica «Comando fallido» en Monitoreo. En la vuelta siguiente de `revision_iot` llega el correo. «Emitir comando» ya no se ofrece para ese actuador: la pantalla dice «Volvé a activarlo desde Hardware antes de emitir comandos.». Después, en su ficha, «Volver a activar». *(Lo cubre: `test_ext_4a_…`, `test_ext_4b_…` y el recorrido; el correo real no (usa el servicio simulado).)*
6. **Escenario 8 · El nodo no reconoce el comando.** «Rechazar (no reconoce)» y emití «Cerrar» a la ventana: queda «Rechazado por el nodo», sin reintentos y con la nota; aparece «Configuración incompatible», el actuador sigue activo y «Cerrar» ya no se ofrece al emitir (el formulario avisa «El nodo no soporta: Cerrar»). *(Lo cubre: `test_ext_4f_…` y el recorrido.)*
7. **Escenario 9 · Caída del nodo.** Emití un comando, esperá a que el nodo lo retire y detené los flujos unos 4 minutos. En la vuelta de la revisión: alerta crítica «Nodo sin comunicación» (y su correo). El comando sigue «Pendiente» y no consumió intentos. Volvé a arrancar los flujos: se resuelve la alerta y el comando se ejecuta. *(Lo cubre: `test_ext_2a_1a_…` y el recorrido.)*
8. **Escenario 13 · Cancelar un comando trabado.** «No responder»; emití un comando. Mientras el nodo lo tiene, «Cancelar» está deshabilitado con «Cancelable en n s» y la ventana (si la abrís a mano) lo explica. Cuando vence el intento, «Cancelar» → «Cancelar comando»: «Cancelado», aviso «CMD-n cancelado…», y se puede emitir otro al mismo actuador. *(Lo cubre: `test_regla_2_…`, `test_regla_5_…` y el recorrido.)*
9. **Modo local (paso 2 de la tarea).** En el flujo de lecturas, «Modo local». Emití un comando: el resumen avisa «El nodo está operando en modo local…» y queda «Pendiente» con «0 de 2» aunque pase el tiempo. «Modo remoto»: el nodo lo retira y se ejecuta. *(Lo cubre: `test_ext_2d_…`, `test_ext_6g_…` y el recorrido.)*
10. **Bitácora y auditoría (pasos 3 y 4 de la tarea).** Producción → «Bitácora» (invernadero «Norte»): los registros de tipo «Comando» con cada hecho («Falló: …», «Sin respuesta», «cancelado», «ejecutado»). Con el Gerente, «Auditoría»: «Emisión de comando», «Cancelación de comando» y «Resolución de comando (IoT)». (El filtro «Tipo» de la bitácora todavía no ofrece «Comando»: queda para otra tarea.) *(Lo cubre: `test_regla_bitacora_…`, `test_post_c_…` y el recorrido.)*
11. **Panel y ficha.** Monitoreo: el indicador «Comandos pendientes», la situación «Comando pendiente» del actuador y, en su fila, «Cancelar» (o «Emitir comando» si no hay pendiente). Ficha del actuador (Hardware → «Ver ficha»): «Emitir comando», la tarjeta «Comandos» con los últimos 10 y «Ver todos (n)» filtrado por ese actuador. *(Lo cubre: `ComandosEnLaFichaYElPanelVistaTests`.)*
12. **Lista y filtros.** «Comandos»: filtrá por estado, actuador y origen (el filtro no recarga la página con JavaScript y aparece «Limpiar filtros»); con más de 25 comandos, «Siguiente» y «Anterior» conservan los filtros. *(Lo cubre: `ListaDeComandosVistaTests`.)*
13. **Gerente.** En «Norte» (tiene Agrónomo activo): ve la lista y el aviso «Norte tiene Agrónomo activo…», pero **sin** formulario ni «Cancelar». En «Libre» (sin Agrónomo): «Operás este invernadero como Gerente…», emite, y su comando sale «Manual · … (Gerente)»; en Auditoría figura su nombre. *(Lo cubre: `test_el_gerente_con_agronomo_activo_solo_consulta_…` y el recorrido.)*
14. **Rol sin acceso y alcance.** El Técnico o un Capataz escriben `/iot/comandos/` a mano: 403. Un Agrónomo de otro invernadero, con `?invernadero=<id de Norte>`: 404. Sin sesión: lleva al ingreso. (Los botones nunca llevan a un 403.) *(Lo cubre: `AccesoAComandosVistaTests` y el recorrido.)*
15. **Navegador real (D-96).** En una ventana privada, entrá con Laura y hacé **de punta a punta** el formulario de «Comandos» (elegir actuador y acción, «Ver resumen», «Confirmar y emitir») y la cancelación («Cancelar» → «Cancelar comando»): sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola (F12). Mirá además que la lista, la ficha y el panel se vean bien (la tabla no se corta, «Cancelar» no se parte). *(Lo cubre: ninguna: el cliente de Django no ve el CSRF, el JavaScript ni el aspecto.)*
16. (Opcional) **Sin JavaScript y en un celular.** Desactivá JavaScript: elegí el actuador y tocá «Actualizar el formulario», elegí la acción y volvé a tocarlo; «Ver resumen» y «Confirmar y emitir» funcionan; «Cancelar» abre la misma página con la ventana. En un ancho de 390 px no hay desborde horizontal. *(Lo cubre: `test_con_htmx_…` (el respaldo); el aspecto, no.)*
17. (Opcional) **Después del despliegue:** en el log de Render, que se aplicaron las tres migraciones. *(Lo cubre: ninguna.)*

### Verifiqué

- **Recorrido** con el cliente de Django (`test_recorrido_comandos.py`): los pasos 1 a 4 de la «Verificación a mano» original y los escenarios 6, 7, 8, 9 y 13 de `docs/api/nodo/escenarios.md`, con el nodo simulado por la API real y el reloj adelantado a mano: ejecutado con estado `posicion:40`; falla en cada intento hasta «fallido», actuador fuera de servicio, alerta crítica y correo por la revisión; rechazo y acción incompatible; caída del nodo sin consumir intentos; cancelar con cuánto falta; modo local; bitácora y auditoría. Por rol: Agrónomo, Gerente con y sin Agrónomo activo, Técnico y Capataz (403), Agrónomo ajeno (404).
- **Migraciones:** `makemigrations --check` sin cambios; `sqlmigrate` de las tres (la de `iot` crea una tabla; la de `produccion` reemplaza un `CHECK`; la de `core` es un no-op) y aplicadas en la base de pruebas (recreada sin `--keepdb`). Antes del merge, `sqlmigrate` mostró un índice duplicado sobre `comando_id` y se corrigió.
- **Concurrencia:** dos emisiones, dos retiros, retiro contra cancelación (en los dos órdenes), dos resultados iguales, resultado contra cancelación y emitir contra IOT-MOD-TAC (D-82). Esta última falla con `DeadlockDetected` si se invierte el orden de bloqueo (lo probé a propósito y volví al orden correcto).

### Lo cubre una prueba

- Reglas, postcondiciones y extensiones de los tres casos de uso: `test_iot_emt_cmd.py`, `test_iot_cnl_cmd.py` y `test_iot_rsv_cmd.py`. Contrato de la API y ejemplos: `test_api_comandos.py` y `test_api_ejemplos.py`. Permisos, alcance, HTMX y sin él: `test_comandos_vistas.py`.

### No pude verificar

- **Node-RED real** con sus dos flujos (se simularon con la API real); **el correo real** de «comando fallido»; **Render** (que apliquen las tres migraciones); **el aspecto y el JavaScript en un navegador** (D-96: no abro navegador ni miro capturas; las pantallas se miraron con capturas **antes** de D-96, y esa prueba se retiró); **el criterio de producto** (si el formulario con resumen «se siente bien»).
