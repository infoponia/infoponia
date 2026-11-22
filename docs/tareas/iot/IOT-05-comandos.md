# IOT-05 · Comandos: emitir, retirar, resolver con reintentos y cancelar

Estado: pendiente | App: iot (y un valor de `Bitacora.TipoEvento` en produccion) | Rama: feature/iot-05-comandos | Ronda: IoT 1

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
