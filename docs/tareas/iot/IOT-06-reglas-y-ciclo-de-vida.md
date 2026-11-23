# IOT-06 · Reglas de actuación y su disparo; desactivar, activar y dar de baja el sistema; baja de equipos

Estado: pendiente | App: iot | Rama: feature/iot-06-reglas-y-ciclo-de-vida | Ronda: IoT 1

Depende de: **IOT-05** (comandos, `validar_comando`, `cancelar_comando_incluido` y `RegistroComando`). Si no está mergeada, frená. Con
IOT-05 vienen también IOT-03 y PRD-01. **No depende de IOT-04**, pero si ya está, la situación de las reglas y el panel se completan con ella.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.**
- **Reglas de actuación:** el Agrónomo define que, cuando un sensor sale del umbral efectivo o vuelve a él, InfoPonia ordene sola una acción a
  un actuador. La regla espera la confirmación, no repite y respeta el tiempo mínimo del equipo. Es el segundo hito demostrable: la
  respuesta automática (`docs/api/nodo/escenarios.md`, escenarios 3 a 5).
- **El ciclo de vida que se dejó para después de los comandos y las reglas** (`docs/tareas/ronda_iot_1.md`, sección 1, «Por qué este
  corte»): desactivar, activar y dar de baja el sistema IoT, y dar de baja un equipo.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-ALT-RGL, IOT-MOD-RGL, IOT-BAJ-RGL, IOT-CNS-RGL | ABM de reglas de actuación | docs/casos_de_uso/iot/reglas_de_actuacion.md | — |
| IOT-ENT-INF | Entregar información, **paso 6 y extensiones 6a a 6d** | docs/casos_de_uso/iot/entregar_informacion.md | Solo esas partes y los reinicios de 1b.3 y 5c |
| IOT-DSC-SIS, IOT-ACT-SIS, IOT-BAJ-SIS | Desactivar, activar y dar de baja el sistema IoT | docs/casos_de_uso/iot/sistema_iot.md | Las órdenes de mantenimiento de la baja (precondición d): IOT-07 |
| IOT-BAJ-HDW | Baja de hardware | docs/casos_de_uso/iot/hardware.md | Las órdenes de mantenimiento (precondición d): IOT-07 |

## Leer

- Casos de uso:
  - `reglas_de_actuacion.md` completo;
  - de `entregar_informacion.md`: el paso 6, las extensiones 1b, 5c y 6a a 6d, las reglas «Disparo de una regla», «Actuador ocupado» y
    «Comando automático» del caso de uso, y de «Cómo se aplica», «Reparto», «Una lectura» (paso 10), «Bloqueos y concurrencia» y **«Reglas
    de actuación»**;
  - de `sistema_iot.md`: los casos IOT-DSC-SIS, IOT-ACT-SIS e IOT-BAJ-SIS y, de «Cómo se aplica», «Para los cinco» e «IOT-DSC-SIS,
    IOT-ACT-SIS e IOT-BAJ-SIS (IOT-06)»;
  - de `hardware.md`: IOT-BAJ-HDW y, de «Cómo se aplica», el punto «Baja (BAJ, IOT-06)».
- Modelo: docs/modelo/iot.md («SistemaIoT», «Hardware», «Actuador», «ReglaActuacion», «Comando», «RegistroComando», «Parámetros IoT»).
- Decisiones: **D-78** (puntos 8 y 9), D-75 (puntos 2 a 4 y 7), D-71, D-72, D-28, D-30, D-36, D-37, D-44, D-61.
- API: docs/api/alertas.md (secciones 2 a 4), docs/api/variedades.md («Umbral efectivo» y `variedades_presentes_de_prueba`).
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `reglas`, `rglText`, `ultB`, `rglTags`, `rglSensors`, `COND`; en
  `act`, `rgl-new`, `rgl-mod`, `r-cond`, `r-act`, `r-acc`, `save-rgl` y `sys-activar`; en `modalHtml`, `rbaj:<id>`, `desc`, `baj` (del
  sistema) y `baj:<id>` (del equipo) (referencia, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: todo `iot/` (lo que dejaron IOT-01 a IOT-05), en particular `iot/servicios/lecturas.py` (`evaluar_reglas_de_la_lectura`),
  `nodo.py` (`al_volver_a_remoto`), `comandos.py` (`validar_comando`, `cancelar_comando_incluido`), `sistemas.py` y `hardware.py`;
  `maestros/servicios/alertas.py` (`sincronizar_alertas_de_personal`, `resolver_alerta_de_estado`).

## Lo que dejó IOT-03 (cambia lo escrito arriba)

- `evaluar_reglas_de_la_lectura` se llama desde `iot/servicios/lecturas.py` (`_despues_de_guardar`) solo si la lectura llegó hasta la comparación (válida, reciente, sensor activo,
  fuera de horario y sector descartados, con umbral). **El reinicio de la extensión 5c todavía no existe:** la rama «sin umbral» solo resuelve la alerta; sumá ahí `reiniciar_reglas`.
- `al_volver_a_remoto(sistema)` está en `iot/servicios/nodo.py` y no hace nada: completala (extensión 1b.3).
- **Cargador de datos de verificación:** al traer `baja_hardware`, sumá `norte/sectorA/temp-vieja` (un sensor dado de baja) a `iot/verificacion.py`, usando ese servicio y no el ORM, y un paso de
  «Verificación a mano» que pruebe el motivo `equipo_dado_de_baja` (hoy lo cubren solo las pruebas automáticas).

## Límites

- No crea modelos (`ReglaActuacion` es de IOT-01). → revisá docs/disparadores.md: cierra «Cuando exista SistemaIoT (alertas)», punto 1, **la
  parte de dar de baja**; la parte de IOT-06 de los puntos 1, 2, 3 y 5 de «Cuando existan actuadores, comandos y reglas del IoT».
- Migraciones: una de `core`, solo de `choices`, con las acciones `alta_regla_actuacion`, `modificacion_regla_actuacion`,
  `baja_regla_actuacion`, `desactivacion_sistema_iot`, `activacion_sistema_iot`, `baja_sistema_iot` y `baja_hardware`:
  `00NN_iot_reglas_y_bajas_acciones`. **Ninguna en `iot`.**
- Permitido fuera de la app: `core/models.py`, solo esas acciones y su migración; al cerrar (M3), los textos de `docs/disparadores.md`,
  `docs/tareas/README.md`, `docs/tareas/ronda_iot_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: las órdenes de mantenimiento (IOT-07): hasta entonces, `mantenimientos_a_realizar(equipo)` y
  `ordenes_a_realizar_del_sistema(sistema)` devuelven una lista vacía y las precondiciones d de las dos bajas siempre se cumplen.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **ABM de reglas** (`iot/servicios/reglas.py`; `reglas_de_actuacion.md`, «Cómo se aplica»). Pruebas (`test_iot_alt_rgl.py`,
   `test_iot_mod_rgl.py`, `test_iot_baj_rgl.py`, `test_iot_cns_rgl.py`, clases `<CodigoCu>ServicioTests`):
   - una por regla y por postcondición;
   - un sensor de la solución o de nivel no admite reglas;
   - la acción y el valor con `validar_comando`;
   - la regla igual activa (también con el `IntegrityError` de dos altas a la vez, `@tag("concurrencia")`);
   - crear, modificar y reactivar reinician la evaluación;
   - el sensor y el actuador no cambian al modificar;
   - reactivar con el sensor dado de baja no se puede;
   - la baja deja seguir los comandos pendientes;
   - la situación con cada motivo de «no emite».
2. **Disparo** (`evaluar_reglas_de_la_lectura`, `reiniciar_reglas`, `al_volver_a_remoto` y el reinicio de 5c; `entregar_informacion.md`,
   «Reglas de actuación»; D-78, puntos 8 y 9). Pruebas: `iot/tests/test_iot_ent_inf_reglas.py`, con lo que lista esa sección. Corré
   además **todas** las de `test_iot_ent_inf_*.py`: tienen que dar lo mismo que antes.
3. **Desactivar, activar y dar de baja el sistema** (`iot/servicios/sistemas.py`; `sistema_iot.md`, «Cómo se aplica»). Pruebas
   (`test_iot_dsc_sis.py`, `test_iot_act_sis.py`, `test_iot_baj_sis.py`):
   - desactivar cancela los pendientes (con su bitácora, por `cancelar_comando_incluido`) y resuelve las alertas del sistema;
   - mientras está desconectado, la API responde 403 y la revisión lo saltea;
   - activar reinicia las reglas;
   - la baja: todo inactivo, `token_resumen` nulo (el token deja de servir: 401), reglas inactivas, alertas resueltas y la alerta del
     Técnico sincronizada;
   - la baja con un comando pendiente no deja confirmar.
4. **Baja de un equipo** (`iot/servicios/hardware.py`; `hardware.md`, «Baja (BAJ, IOT-06)»). Pruebas (`test_iot_baj_hdw.py`):
   - precondiciones c y e con su explicación;
   - resuelve las alertas del equipo (`hw:<id>` y `sensor:<id>`);
   - la advertencia del último estado del actuador;
   - después, sus mensajes generan «dispositivo no registrado» que dice de qué equipo era (regla 8; ya lo hace IOT-03).
5. **Pantallas.**
   - La pestaña «Reglas de actuación» (`reglas/`): lista, filtros, ficha con historial, formulario con la frase de vista previa y la
     ventana de baja.
   - Las ventanas de desactivar, activar y dar de baja en «Sistema IoT» (`desc`, `sys-activar`, `baj`), y la de dar de baja en la ficha del
     equipo (`baj:<id>`), con los textos de cada extracto.
   - Las reglas activas del actuador en «Emitir comando» (paso 4 y 6b de IOT-EMT-CMD) y en la ficha del equipo.
   Pruebas (`test_reglas_vistas.py`, `test_sistemas_vistas.py`, `test_hardware_vistas.py`): permisos y alcance; el Gerente con Agrónomo
   activo, solo lectura; el flujo con HTMX y sin él; ningún botón lleva a un 403.
6. **Concurrencia** (`@tag("concurrencia")`, `iot/tests/test_reglas_concurrencia.py`):
   - una regla que dispara y un comando manual a la vez sobre el mismo actuador;
   - desactivar el sistema mientras llega una lectura que dispara una regla (o se emite y se cancela, o no se emite; nunca un pendiente en
     un sistema desconectado);
   - dar de baja un equipo mientras una regla lo usa.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`, tachar la parte de dar de baja del punto 1 de «Cuando exista SistemaIoT (alertas)» y marcar hecha la parte de
     IOT-06 de los puntos 1, 2, 3 y 5 de «Cuando existan actuadores, comandos y reglas del IoT»;
   - marcar IOT-06 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta son los filtros y la ficha de la regla (reglas 3 y 4 de CNS; se anota en
`temas_abiertos.md`). No se recortan la máquina de estados de la regla, la confirmación, el «actuador ocupado», los reinicios, la baja en
cascada ni las pruebas de concurrencia.

## Hecho cuando

- Con una regla «supera el máximo → encender» y otra «vuelve al rango → apagar», el ventilador se enciende solo después de la confirmación,
  no se vuelve a encender mientras la condición siga y se apaga cuando la lectura vuelve a más de la histéresis (escenarios 3 a 5 de
  `docs/api/nodo/escenarios.md`).
- Una regla no emite con el actuador ocupado y lo intenta con la lectura siguiente; nunca hay dos pendientes por actuador.
- Las reglas se reinician al modificarlas, al activar el sistema, al volver el nodo de modo local y cuando el invernadero se queda sin umbral.
- Desactivar, activar y dar de baja el sistema, y dar de baja un equipo, hacen lo que dicen sus extractos, con su auditoría.
- Pruebas: `test_iot_alt_rgl.py`, `test_iot_mod_rgl.py`, `test_iot_baj_rgl.py`, `test_iot_cns_rgl.py`, `test_iot_ent_inf_reglas.py`,
  `test_iot_dsc_sis.py`, `test_iot_act_sis.py`, `test_iot_baj_sis.py`, `test_iot_baj_hdw.py`, `test_reglas_vistas.py` y
  `test_reglas_concurrencia.py`.
- Comando de pruebas:
  python manage.py test iot core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva (`core`): `python manage.py migrate`. Lo de «Antes de empezar» de `docs/api/nodo/escenarios.md` (con umbral efectivo
y 2 lecturas de confirmación). Seguí los escenarios 3, 4, 5, 10 y 14, y además:

1. Crear dos reglas iguales: la segunda da el error «Ya hay una regla activa igual…».
2. Modificar una regla: su situación vuelve a «Sin evaluar».
3. Dar de baja una regla con un comando pendiente: el comando sigue y se ejecuta.
4. Dar de baja un actuador con una regla activa: no deja, y explica que hay que dar de baja la regla.
5. Dar de baja el sistema IoT: la ventana muestra todo lo que se da de baja; después, Node-RED recibe 401 y el invernadero ya se puede dar
   de baja en Datos maestros.
6. En «Auditoría», las acciones nuevas.

## Cierre (la completa Claude Code al cerrar)
