# IOT-06 · Reglas de actuación y su disparo; desactivar, activar y dar de baja el sistema; baja de equipos

Estado: hecha (falta su PR) | App: iot | Rama: feature/iot-06-reglas-y-ciclo-de-vida | Ronda: IoT 1

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

Pantallas nuevas y formularios que se envían: lleva el paso de «navegador real» (paso 35). Las marcas **[prueba: …]** dicen qué cubre ya una prueba; si tenés poco tiempo, concentrate en lo que se ve y se siente.
Los escenarios 3, 4, 5, 10 y 14 de `docs/api/nodo/escenarios.md` están repetidos acá con sus pasos concretos; no hace falta hacerlos dos veces.

### Antes de empezar

1. **Migración.** `python manage.py migrate`. La de esta tarea es de `core` y solo cambia las opciones del campo «acción» de la auditoría (`sqlmigrate` muestra «no-op»: no toca datos). 
2. **Servidor.** `python manage.py runserver` y abrí `http://127.0.0.1:8000/`. Necesitás cuatro sesiones (ventanas distintas o una ventana privada): **Gerente**, **Agrónomo** (el de «Norte»), **Técnico** y **Capataz**.
   Las contraseñas son las de tus cuentas de prueba; no las escribas en ningún archivo.
3. **Datos que tenés que crear a mano** (no hay cargador), en este orden:
   - Invernadero **«Norte»** con un **Agrónomo** (por ejemplo, Laura) y un **Técnico** asignados, y un sector «Sector A». Otro invernadero **«Libre»**, **sin Agrónomo** (lo opera el Gerente).
   - **Umbral efectivo** en «Norte»: un lote activo (o una siembra a realizar) de una variedad con temperatura 18 a 24 °C. Para comprobarlo: IoT · Monitoreo de «Norte» no debe decir «no tiene umbral efectivo».
   - En Inventario, un insumo de la categoría «Repuestos de hardware» (por ejemplo, «Raspberry Pi 4»).
   - IoT · **Sistema IoT** de «Norte»: «Registrar sistema IoT» (nombre «Nodo del galpón», modelo «Raspberry Pi 4», rango de la solución 18 a 24). **Copiá el token que muestra** (se ve una sola vez): lo vas a usar para
     hablar como el nodo.
   - IoT · **Hardware** de «Norte», con estos identificadores exactos: sensor de **temperatura** `norte/temperatura`; sensor de **humedad** `norte/humedad`; sensor de **nivel de la solución** `norte/nivel`;
     actuador **Ventilador** `norte/ventilador`; actuador **Ventana** `norte/ventana` (los tipos «Ventilador» y «Ventana» ya vienen cargados).
   - Configuración operativa · Módulo IoT: **lecturas de confirmación 2**, **reintentos 1** e **intervalo 10 s** (al terminar, volvé a 3, 3 y 60).
4. **Hablar como el nodo.** O con Node-RED como dice `docs/api/nodo/escenarios.md`, o desde PowerShell (el token en una variable de **tu terminal**, nunca en un archivo):
   ```
   $env:TOKEN_NODO = "<el token que copiaste>"
   function Lectura($valor) { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/iot/v1/lecturas -Headers @{Authorization="Bearer $env:TOKEN_NODO"} -ContentType "application/json" -Body (@{lecturas=@(@{identificador="norte/temperatura"; valor=$valor})} | ConvertTo-Json -Depth 4) }
   function Retiro { Invoke-RestMethod -Uri http://127.0.0.1:8000/api/iot/v1/comandos -Headers @{Authorization="Bearer $env:TOKEN_NODO"} }
   function Resultado($id, $estado) { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/iot/v1/comandos/$id/resultado" -Headers @{Authorization="Bearer $env:TOKEN_NODO"} -ContentType "application/json" -Body (@{resultado="ejecutado"; estado=$estado} | ConvertTo-Json) }
   ```
   `Lectura 35` manda una lectura de 35 °C; `Retiro` pide los comandos pendientes; `Resultado 12 "encendido"` informa que el comando 12 se ejecutó. Esperá **unos segundos entre una lectura y la siguiente** (dos lecturas con la misma hora se descartan).

### Quién ve qué (D-30)

5. Con el **Capataz**, escribí en la barra `/iot/reglas/`: tiene que dar «Prohibido (403)». **[prueba: `AccesoAReglasVistaTests`]**
6. Con el **Gerente**, entrá a IoT · **Reglas de actuación** de «Norte» (tiene Agrónomo activo): el cartel dice que lo consulta pero lo opera su Agrónomo, la lista dice «No hay reglas en este invernadero.» y **no hay**
   botón «Nueva regla». Probá `/iot/reglas/nueva/?invernadero=<id de Norte>` a mano: vuelve a la lista con un aviso (nunca un error). **[prueba: `AccesoAReglasVistaTests`]**
7. Con el **Gerente**, elegí **«Libre»** en la barra de invernaderos: ahí sí aparece «Nueva regla» (lo opera él). **[prueba: el recorrido, `test_recorrido_del_gerente_en_un_invernadero_sin_agronomo`]**

### Alta de reglas (IOT-ALT-RGL)

8. Con el **Agrónomo**: Reglas de actuación · **Nueva regla**. En «Cuando el sensor…» desplegá la lista: tienen que estar `norte/temperatura` y `norte/humedad`, y **no** `norte/nivel` (la solución se monitorea con alertas).
9. Elegí el sensor `norte/temperatura`, la condición «Supera el máximo del umbral efectivo» y el actuador **Ventilador**. Al elegir el actuador, la lista «Acción» se llena con **Encender, Apagar y Fijar velocidad**
   (sin recargar toda la página). Elegí **Encender**: aparece el recuadro azul **«Vista previa. Cuando Temperatura norte/temperatura supera el máximo del umbral efectivo, Ventilador norte/ventilador: Encender.»**
   **[prueba: `test_regla_4_elegir_el_actuador_ofrece_sus_acciones_y_la_vista_previa`]**
10. Cambiá el actuador a **Ventana**: la acción elegida se borra (no es del tipo). Elegí **Fijar posición**: aparece «Valor (%)» con «Número entero entre 0 y 100 %.». Escribí `40` y apretá **«Actualizar la frase»**:
    la vista previa dice «… Ventana norte/ventana: Fijar posición 40 %». **No** tiene que validar nada mientras escribís. **[prueba: `test_regla_4_una_accion_con_valor_pide_el_valor_y_lo_incluye_en_la_frase`]**
11. Apretá **Crear regla** con Ventana · Fijar posición y el valor vacío, o con `12.5`, o con `101`: el error sale **debajo del campo «Valor»** y el formulario conserva lo escrito. Dejá el sensor sin elegir: «Seleccioná un sensor.»
    **[prueba: `IotAltRglServicioTests` y `test_errores_por_campo_sin_guardar_ni_perder_lo_escrito`]**
12. Volvé a Ventilador · Encender y apretá **Crear regla**: vuelve a la lista con el aviso verde «RGL-n creada: Cuando Temperatura …». La fila dice **Sin evaluar**. Esta es la **regla 1 (R1)**.
13. **Regla igual.** Creá otra vez la **misma** (temperatura · supera el máximo · Ventilador · Encender): **no** se crea y el formulario muestra arriba el error **«Ya hay una regla activa igual: Cuando Temperatura norte/temperatura supera
    el máximo del umbral efectivo, Ventilador norte/ventilador: Encender.»** **[prueba: `test_regla_6_una_regla_igual_a_una_activa_se_rechaza_con_su_texto`]**
14. Creá la **regla 2 (R2)**: temperatura · **«Vuelve a quedar dentro del umbral efectivo»** · Ventilador · **Apagar**. Ahora la lista tiene dos filas.
15. (Opcional) En un invernadero **sin lotes ni siembras** (sin umbral efectivo): el formulario muestra, **antes de guardar**, el aviso amarillo «Este invernadero no tiene umbral efectivo: la regla se guarda, pero no se evalúa hasta
    que lo tenga.»; la regla se crea igual y su fila dice «No se evalúa: sin umbral efectivo». **[prueba: `test_el_formulario_ofrece_solo_sensores_que_admiten_reglas_y_actuadores_activos` y `IotCnsRglVistaTests`]**

### La respuesta automática (escenarios 3, 4 y 5)

16. **Escenario 3.** Mandá `Lectura 35`. En la lista de reglas (recargá), R1 dice **«Confirmando 1 de 2»**. Mandá otra `Lectura 35`: R1 dice **«Se cumple»** y en IoT · **Comandos** hay un comando **Pendiente** cuyo origen es
    **«Regla de actuación · RGL-n»** (Encender). Corré `Retiro` (te devuelve ese comando) y `Resultado <id> "encendido"`: el comando pasa a **Ejecutado** y el ventilador, en Hardware, queda «Encendido».
    **[prueba: el recorrido, «Escenario 3»]**
17. **Escenario 4.** Esperá más de 60 s y mandá dos `Lectura 35` más: **no** aparece un segundo comando y R1 sigue en «Se cumple». **[prueba: el recorrido, «Escenario 4»]**
18. **Escenario 5.** Esperá más de 60 s y mandá `Lectura 20` dos veces (más de 1 °C por debajo del máximo): R1 pasa a «No se cumple» y R2 pasa a emitir el comando **Apagar** (Pendiente, origen R2).
    **[prueba: el recorrido, «Escenario 5»]**
19. **Actuador ocupado.** Antes de retirar ese comando, en Comandos emití a mano otro al ventilador: no deja («ya tiene un comando pendiente»). Con una regla que confirme mientras haya un pendiente, la regla **no** emite y vuelve a
    intentar con la lectura siguiente. **[prueba: `test_iot_ent_inf_reglas.py` y `test_regla_8_…` de `test_reglas_concurrencia.py`]**

### Modificar, dar de baja y reactivar una regla (IOT-MOD-RGL, IOT-BAJ-RGL)

20. **Dar de baja con un comando pendiente.** Con el comando de R2 (Apagar) todavía **sin retirar**: en la fila de R2 tocá **Dar de baja**. La ventana dice «La regla deja de evaluarse. Su historial se conserva…» y, **en azul**, que sus
    comandos pendientes (CMD-n) **siguen su curso y se ejecutan igual**. Confirmá: R2 pasa a «Dada de baja» (filtrá por estado «Dadas de baja» para verla). Corré `Retiro` y `Resultado <id> "apagado"`: el comando **sigue y se ejecuta**.
    **[prueba: `test_regla_2_dar_de_baja_deja_seguir_los_comandos_pendientes_y_lo_dice`]**
21. **Reactivar.** En la lista, con el filtro «Dadas de baja», tocá **Reactivar** en R2: vuelve a «Activa» y «Sin evaluar». **[prueba: `test_regla_6_reactivar_deja_la_regla_activa_y_sin_evaluar`]**
    Probalo también así: dá de baja una regla, después dá de baja **su sensor** (Hardware · ficha · Dar de baja: ya se puede, porque la regla está inactiva) y tocá **Reactivar** en la regla: no deja y avisa «El sensor de la regla no
    está activo: volvé a activarlo o reactivalo desde Hardware antes.» **[prueba: `test_regla_6_reactivar_con_el_sensor_dado_de_baja_explica_por_que_no`]**
22. **Modificar.** Mandá `Lectura 35` una vez (R1 dice «Confirmando 1 de 2»). Tocá **Modificar** en R1: el sensor y el actuador aparecen **deshabilitados** con «El sensor y el actuador no se cambian: para otros, se crea una regla nueva.»
    Cambiá la condición a «Baja del mínimo del umbral efectivo» y **Guardar cambios**: la fila de R1 vuelve a **«Sin evaluar»**. Volvé a dejarla en «Supera el máximo». **[prueba: `test_regla_4_modificar_reinicia_la_evaluacion_y_audita`]**
23. **Ficha de una regla.** Tocá el código (RGL-n) de R1: la ficha muestra la frase, el estado, la evaluación, el último disparo y el historial **«Comandos que generó»** con el CMD del paso 16. **[prueba: `test_regla_4_la_ficha_muestra_…`]**
24. **Filtros.** En la lista, filtrá por estado, por sensor y por actuador; «Quitar filtros» los saca; sin resultados dice «Ninguna regla coincide con los filtros.» **[prueba: `test_regla_3_los_filtros_…`]**

### Dar de baja un equipo (IOT-BAJ-HDW)

25. **Con una regla activa.** Hardware · ficha del **Ventilador** (la ficha ahora tiene el recuadro **«Reglas activas que lo usan»** con R1): **Dar de baja**. La ventana dice **«No se puede dar de baja todavía»**, lista RGL-n y explica
    **«Dalas de baja primero desde Reglas de actuación»**, y **no** hay botón para confirmar. **[prueba: `test_regla_2_con_una_regla_activa_la_ventana_no_deja_confirmar_y_explica_como_resolverlo`]**
26. **Sin reglas.** Dá de baja R1 (y R2 si está activa) y repetí el paso 25 sobre el Ventilador: ahora la ventana dice que el equipo deja de operar y que su identificador **`norte/ventilador` queda libre**, y trae el aviso amarillo
    **«Último estado informado por el nodo: apagado desde las HH:MM. Después de la baja, InfoPonia no podrá enviarle comandos: si tiene que quedar apagado o cerrado, llevalo a ese estado antes…»**. Confirmá: el equipo queda «Dado de baja».
    **[prueba: `test_post_a_da_de_baja_audita_y_vuelve_a_la_ficha` y `test_iot_baj_hdw.py`]**
27. **Después de la baja.** Mandá una lectura o un estado del equipo dado de baja (por ejemplo, una lectura con identificador `norte/ventilador`): se rechaza y aparece la alerta **«Dispositivo no registrado»** que dice que era de ese
    equipo. **[prueba: `test_iot_baj_hdw.py` y `test_iot_ent_inf_lecturas.py`]** Volvé a registrar un ventilador con ese identificador para seguir (IoT · Hardware · Registrar hardware).

### Modo local (escenario 10) y desconectar el sistema (escenario 14)

28. **Escenario 10.** Con R1 en «Confirmando 1 de 2» (mandá una `Lectura 35`), pasá el nodo a modo local: `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/iot/v1/modo -Headers @{Authorization="Bearer $env:TOKEN_NODO"} -ContentType "application/json" -Body '{"modo":"local"}'`.
    La fila de R1 dice **«No se evalúa: nodo en modo local»** y otra `Lectura 35` **no** la hace avanzar. Volvé a remoto (`{"modo":"remoto"}`): R1 vuelve a **«Sin evaluar»**. **[prueba: el recorrido, «Escenario 10»]**
29. **Escenario 14 · Desconectar.** Con un comando pendiente (emití uno a mano, sin retirarlo), IoT · **Sistema IoT** · **Desconectar**. La ventana dice que mientras esté desconectado no se aceptan mensajes del nodo, no se evalúan reglas,
    no se generan alertas ni se entregan comandos; que los pendientes se cancelan y las alertas del sistema se resuelven. Confirmá: el estado pasa a **Desconectado**, el comando queda **Cancelado**, `Lectura 35` y `Retiro` responden
    **403** y las reglas muestran «No se evalúa: sistema desconectado». **[prueba: `test_post_b_desconectar_abre_la_ventana_sin_cambiar_y_el_post_desconecta_cancelando_los_pendientes` y el recorrido]**
30. **Activar.** Tocá **Activar** (es un botón directo, sin ventana): el sistema vuelve a «Activo», las reglas vuelven a «Sin evaluar» y `Lectura 20` responde 200. **[prueba: `test_post_a_activar_es_un_post_directo_y_deja_el_sistema_activo` y el recorrido]**

### Dar de baja el sistema (IOT-BAJ-SIS)

31. **Con un comando pendiente.** Emití un comando a mano y abrí **Dar de baja** en Sistema IoT: la ventana dice **«No se puede dar de baja todavía»**, lista el CMD pendiente y cómo resolverlo («Cancelalo… o todos juntos
    desactivando el sistema»), y **no** hay botón de confirmar. **[prueba: `test_regla_4_con_comandos_pendientes_la_ventana_no_deja_confirmar_y_explica_como_resolverlo`]**
32. **Sin pendientes.** Cancelá el comando y abrí **Dar de baja** otra vez: la ventana muestra «La baja es **definitiva**», el nodo (su token deja de servir), **cada equipo** con «Activo» o «Fuera de servicio» y, de cada actuador, su
    **último estado informado**, **cada regla activa**, y el aviso de que InfoPonia no podrá enviar comandos a los actuadores. Confirmá con **Dar de baja definitivamente**. **[prueba: `test_regla_8_la_ventana_de_baja_lista_lo_que_se_da_de_baja_y_advierte`]**
33. **Después.** La ficha dice «Norte no tiene Sistema IoT» (y Hardware, Comandos y Reglas de actuación también: el sistema dado de baja queda como historial, ya no se opera). `Lectura 35` responde **401** (el token dejó de
    servir). En **Datos maestros · Invernaderos**,
    «Norte» ya se puede dar de baja (antes decía que tiene un sistema IoT). La alerta «invernadero sin Técnico activo», si existía, se resolvió. **[prueba: `test_post_a_la_baja_deja_todo_inactivo_sin_token_y_vuelve_a_la_ficha` y el recorrido]**

### Auditoría

34. Con el Gerente, **Auditoría**: tienen que estar las acciones nuevas, cada una con el usuario, la fecha y lo que cambió: **alta de regla de actuación**, **modificación de regla de actuación** (también la reactivación),
    **baja de regla de actuación**, **desactivación del sistema IoT**, **activación del sistema IoT**, **baja del sistema IoT** y **baja de hardware**. **[prueba: el recorrido, «Auditoría»]**

### Navegador real (obligatorio: hay formularios que se envían)

35. **Navegador real.** Abrí IoT · Reglas de actuación en una **ventana privada**, iniciá sesión con el Agrónomo, y **enviá hasta el final** estos formularios: Nueva regla (con «Actualizar la frase» antes), Modificar, la ventana
    **Dar de baja** de una regla, **Reactivar**, y las ventanas **Desconectar** y **Dar de baja** del equipo. Cada uno tiene que mostrar el resultado esperado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error
    en la consola del navegador (F12), avisá: el cliente de Django no ve el CSRF, el encabezado `Origin` ni el JavaScript.
36. **Con JavaScript desactivado** (opcional): cada ventana (Dar de baja, Desconectar, Dar de baja el sistema) se abre como **una página completa** con la ventana encima, y «Actualizar la frase» recarga el formulario.
    **[prueba: las que piden «sin JavaScript» en `test_reglas_vistas.py` y `test_sistemas_vistas.py`]**
37. **En un celular** (opcional): la tabla de reglas se desplaza hacia el costado y las ventanas entran en pantalla.

Al terminar: Configuración operativa · Módulo IoT, volver a 3 lecturas de confirmación, 3 reintentos y 60 s de intervalo.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (rama `feature/iot-06-reglas-y-ciclo-de-vida`):
- **Migración `core` 0032** (`iot_reglas_y_bajas_acciones`, renumerada de 0031 al traer `main` con CMP-02b; incluye las acciones de las dos tareas): solo `choices`; agrega las acciones `alta_regla_actuacion`, `modificacion_regla_actuacion`, `baja_regla_actuacion`, `desactivacion_sistema_iot`, `activacion_sistema_iot`,
  `baja_sistema_iot` y `baja_hardware`. `sqlmigrate` dice «no-op»: no toca datos. Ninguna migración en `iot`.
- **Reglas** (`iot/servicios/reglas.py`): ABM, reactivar, consulta con situación y motivos, y `acciones_ofrecidas` y `texto_previo` (nuevas en esta sesión, para el formulario).
- **Disparo** (`iot/servicios/lecturas.py`, `nodo.py`): `evaluar_reglas_de_la_lectura`, `reiniciar_reglas`, el reinicio de 5c y `al_volver_a_remoto` (1b.3).
- **Ciclo de vida** (`sistemas.py`, `hardware.py`): desactivar, activar, dar de baja el sistema y dar de baja un equipo, con `datos_de_baja_del_*` para las ventanas.
- **Pantallas** (paso 5): `iot/views_reglas.py` y `iot/templates/iot/reglas/` (lista, tabla, ficha, formulario y ventana de baja), la pestaña «Reglas de actuación», las ventanas de **Desconectar**, **Activar** (botón directo) y
  **Dar de baja** del sistema, la ventana de **Dar de baja** del equipo y «Reglas activas que lo usan» en su ficha, y las reglas activas del actuador en «Emitir comando» (paso 4; la advertencia 6b ya la daba IOT-05).
- Además, `comandos.filas_de_comandos` (nombre público de `_filas_de`, para la ficha de la regla).

**Pruebas.**
- `python manage.py test iot core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **2253 pruebas, OK**.
- `python manage.py test iot --keepdb --tag concurrencia`: **44 pruebas, OK** (7 nuevas en `test_reglas_concurrencia.py`: regla contra comando manual en los dos órdenes; desactivar contra una lectura que dispara, en los dos órdenes;
  baja de un actuador o de un sensor contra el alta de una regla que lo usa).
- Nuevas en esta sesión: `test_reglas_vistas.py` (28), `IotCicloSisVistaTests` (11, en `test_sistemas_vistas.py`), `IotBajHdwVistaTests` (8, en `test_hardware_vistas.py`), `ReglasEnEmitirComandoVistaTests` (3, en
  `test_comandos_vistas.py`), `test_reglas_concurrencia.py` (7) y `test_recorrido_reglas.py` (2: `RecorridoDeReglasTests`).
- **Pruebas existentes que cambiaron** (se avisa: no se debilitó ninguna): `test_comandos_vistas.test_la_pestana_comandos_esta_en_el_modulo_y_activa` y `test_monitoreo_vistas` (la lista de pestañas ahora trae «Reglas de actuación»);
  en pasos anteriores, `test_iot_cns_hdw` (2) y `test_iot_reg_sis` (el conjunto de acciones permitidas suma `baja` y `desactivar`), `test_iot_cns_tac` (una consulta más, por las reglas activas), `test_iot_ent_inf_estados` y
  `test_iot_ent_inf_lecturas` (las que fijaban el vacío de IOT-03: `al_volver_a_remoto` ya reinicia y 5c ya reinicia las reglas).

**Verifiqué** (con el recorrido y las migraciones):
- `RecorridoDeReglasTests`: los escenarios 3, 4, 5, 10 y 14, los pasos 1 a 6 de la verificación original (regla repetida, modificar, baja con pendiente, baja del actuador con regla, baja del sistema con 401 y baja del invernadero
  posible, auditoría) y el Gerente en un invernadero sin Agrónomo; por rol (Capataz 403, Gerente con Agrónomo solo lectura, Agrónomo, Gerente operando) y por estado (activa, dada de baja, sistema desconectado, modo local).
- `makemigrations --check`: «No changes detected». `sqlmigrate core 0032`: `-- (no-op)`. La migración se aplica en la base de pruebas (todas las pruebas corren sobre ella).

**Lo cubre una prueba:** cada paso de la «Verificación a mano» marca la suya.

**No pude verificar:**
- Lo que solo ve un navegador (paso 35): el aspecto, el CSRF y el encabezado `Origin`, la consola, el desplegable propio de cada filtro y de «Acción», y que «Actualizar la frase» y las ventanas con HTMX se vean como corresponde.
- El paso del sistema sin JavaScript y en celular (36 y 37).
- El «último estado informado: …» con el nodo real, y el envío de correos de las alertas (los hace `revision_iot`, de IOT-04).
- Que Render aplique la migración (log de Render, tras el despliegue).

**Decisiones:** ninguna nueva en esta sesión (el número se propone al cerrar, tras `git fetch`: ver M3).

**Pantallas: lo que se corrigió del prototipo (D-61):**
- *Filtros y ficha de la regla.* El prototipo no los tiene; se agregaron (reglas 3 y 4 de IOT-CNS-RGL), con «Ver ficha» como enlace.
- *Reglas dadas de baja.* El prototipo las esconde; la lista las muestra (con «Dada de baja» y «Reactivar») y se filtran por estado (regla 3 de CNS, regla 6 de MOD).
- *Sensores de un sector fuera de servicio.* El prototipo los excluye del formulario; se ofrecen (la regla 2 de ALT no los excluye) y la situación de la regla dice que no se evalúa (D-75, punto 7).
- *Condición de la regla.* El prototipo usa botones de opción de aspecto «chip»; se usaron botones de opción comunes (con teclado y sin JavaScript) agrupados en un `fieldset` con leyenda.
- *Vista previa.* El prototipo la recalcula al escribir; acá no se valida ni se recalcula mientras se tipea (`.claude/rules/interfaz.md`): se actualiza al elegir el actuador o la acción y con el botón «Actualizar la frase».
- *Aviso de «sin umbral efectivo».* Se muestra **antes** de guardar (como el prototipo) y de nuevo en el aviso de la regla creada.
- *Aviso de sistema desconectado* en el formulario (regla 9 de ALT): «El sistema IoT está desconectado: la regla se guarda y empieza a evaluarse cuando lo actives.» (no está en el prototipo).
- *Ventana de baja de la regla.* Suma el aviso de los comandos pendientes que siguen su curso (regla 2 de BAJ).
- *Ventana de baja del sistema.* Suma el estado de cada equipo y el aviso de los actuadores en un solo recuadro, y el texto de «no se puede dar de baja todavía» con las precondiciones c y d (regla 4 de BAJ-SIS).
- *Ventana de baja del equipo.* Con impedimentos no ofrece confirmar (regla 2 de BAJ-HDW) y, sin ellos, la advertencia del último estado del actuador (regla 7).
- *«Activar».* Es un botón directo (un POST), como `sys-activar` del prototipo, sin ventana: no se pierde nada.
- *«Reglas activas que lo usan»* en la ficha del equipo (prototipo) y en «Emitir comando» (paso 4 de IOT-EMT-CMD).

**Para `docs/temas_abiertos.md` (implementado distinto de lo escrito):**
- La tarea nombra `iot/verificacion.py` y el cargador de datos de verificación (`baja_hardware`, `norte/sectorA/temp-vieja`): no se hizo, porque D-95 los retiró (los datos de prueba los crea el estudiante).
- `comandos.filas_de_comandos` es un nombre público nuevo sobre `_filas_de` (IOT-05), para reusar el aspecto de la lista en la ficha de la regla.
- El historial de la ficha de una regla muestra los últimos 25 comandos y enlaza a «Comandos» con el origen «Regla de actuación» para ver el resto.
- **Migración:** al traer `main` (CMP-02b trajo su `0031`), la de esta tarea se renumeró a `0032` y se regeneró con `makemigrations`, así que trae las acciones de las dos tareas. Pruebas tras el merge: `iot`, `core` y `compras`, 2758, OK.
