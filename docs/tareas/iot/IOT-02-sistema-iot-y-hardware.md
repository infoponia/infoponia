# IOT-02 · Sistema IoT y hardware

Estado: hecha, a la espera de la revisión a mano | App: iot (y un punto de extensión en maestros) | Rama: feature/iot-02-sistema-iot-y-hardware | Ronda: IoT 1

Depende de: **IOT-01** (el esquema, `iot/alcance.py` y las fábricas), **MAE-02b** (`sincronizar_alertas_de_personal` con el Técnico) y
**NOT-01** (avisos). MAE-02b y NOT-01 están hechas. Si IOT-01 no está mergeada, frená. **No depende de ninguna tarea de producción ni de
comercial.**

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** El Agrónomo (o el Gerente donde no hay Agrónomo activo) registra el **sistema IoT** de un invernadero, con su nodo central y
su token, que se muestra una sola vez, y registra, modifica y consulta los **equipos** (sensores y actuadores). Conecta el IoT con `maestros`:
la ficha del invernadero muestra el estado del IoT, un sector con equipos no se da de baja, un invernadero con sistema tampoco, y la alerta
«invernadero sin Técnico activo» aparece al registrar el sistema. Todavía no hay lecturas ni comandos: el sistema queda «sin señal» hasta
IOT-03. La desactivación, la activación y las bajas son de IOT-06.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-REG-SIS | Registrar Sistema IoT | docs/casos_de_uso/iot/sistema_iot.md | La guía del nodo (paso 10) es un enlace: el archivo llega en el lote I2a (`docs/api/nodo/README.md`) |
| IOT-MOD-SIS | Modificar Sistema IoT (con regenerar el token) | docs/casos_de_uso/iot/sistema_iot.md | — |
| IOT-ALT-HDW | Alta Hardware | docs/casos_de_uso/iot/hardware.md | Identificadores anunciados (regla 14): se completan en IOT-03 |
| IOT-MOD-HDW | Modificar Hardware (con volver a activar y reactivar) | docs/casos_de_uso/iot/hardware.md | Regla 3 (lecturas, reglas, comandos): se completa en IOT-03, IOT-05 e IOT-06. Regla 8 (órdenes): se completa en IOT-07 |
| IOT-CNS-HDW | Consultar Hardware | docs/casos_de_uso/iot/hardware.md | Lecturas, comandos, reglas y órdenes de la ficha: se completan en IOT-03 a IOT-07 |

## Leer

- Casos de uso: los dos extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno (de
  `sistema_iot.md`, «Para los cinco», IOT-REG-SIS e IOT-MOD-SIS; las de IOT-06 solo para no cerrarles el camino). De
  `docs/casos_de_uso/iot/tipos_de_actuador.md`, «Cómo se aplica», los puntos «Aviso de equipos afectados», «Compatibilidad» y «Baja», que
  esta tarea completa.
- Modelo: docs/modelo/iot.md («SistemaIoT», «Hardware», «EquipoAnunciado», «AlertaIot», «Tipos de alerta del IoT», «Reglas que tocan al
  IoT»).
- Decisiones: D-70 (el token), D-72, D-65 (`core/enlaces.py`), D-05, D-21, D-24, D-25, D-28, D-29, D-30, D-36, D-37, D-40, D-42, D-44, D-47.
- API: docs/api/extensiones_de_maestros.md («Sectores» y **«Estado del IoT del invernadero»**, que esta tarea implementa en `maestros` tal
  cual), docs/api/alertas.md (secciones 2 a 4), docs/api/notificaciones.md.
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/enlace_del_cliente.md (solo la sección «1. Piezas», la fila de `nuevo_token` y `resumen_de`),
  docs/patrones/trabajo_en_paralelo.md.
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md`. Funciones: `sistema`, `sysEstB`, `opBanner`, `canOp`, `visInv`, `newTok`,
  `hardware`, `hwBadge`, `anunciadosLibres`, `sensorState`, `actState`, `estInf`, `compatB`, `tipoCambiable`, `IDRE`, `recompat`,
  `announced`, `announcedBad`, `bajaDe`; en `act`, los casos `open-sys-form`, `save-sys`, `tok-ck`, `copy`, `guia`, `hw-new`, `hw-mod`,
  `hw-ficha`, `hw-back`, `save-hw`, `reg-alert` y `hwf-*`; en `modalHtml`, las ventanas `token`, `regen`, `react:<id>` y `rebaja:<id>`
  (referencia, D-61; lo que difiera lo decide el caso de uso, L7: las diferencias ya detectadas están en cada extracto).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - todo `iot/` (lo que dejó IOT-01);
  - `maestros/extensiones.py` (los puntos de invernadero y de sector), `maestros/models.py` (`Invernadero.tiene_sistema_iot`),
    `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`), `maestros/servicios/alertas.py` (`sincronizar_alertas_de_personal`,
    `asegurar_alerta_de_estado`, `resolver_alerta_de_estado`), y la ficha y la lista del invernadero (`maestros/views.py` y sus plantillas);
  - `inventario/apps.py` (cómo una app registra sus puntos en `maestros`) e `inventario/models.py` (`Insumo` y la categoría por `codigo`);
  - `core/enlaces.py` si existe (D-65; si no, se crea en esta tarea), `core/notificaciones.py`, `core/models.py` (auditoría).

## Límites

- No crea modelos (los creó IOT-01). Si hace falta una columna, frená: es un cambio de D-72.
  → revisá docs/disparadores.md: cierra «Cuando exista una ocupación de sector, una variedad con semilla o un hardware», punto 4; «Cuando
  exista SistemaIoT», punto 1; «Cuando exista SistemaIoT (alertas)», punto 1, **la parte de registrar** (la de dar de baja es de IOT-06); y
  la parte de IOT-02 del punto 1 de «Cuando existan actuadores, comandos y reglas del IoT». Los puntos 2 y 3 de esta última sección siguen
  abiertos (ya escritos en el lote I1).
- Migraciones: una de `core`, solo de `choices`, con las acciones nuevas: `00NN_iot_sistema_y_hardware_acciones` (`alta_sistema_iot`,
  `modificacion_sistema_iot`, `regeneracion_token_iot`, `alta_hardware`, `modificacion_hardware`, `reactivacion_hardware`). **Ninguna en
  `iot` ni en `maestros`.** Si `core/enlaces.py` no existe, no lleva migración.
- Permitido fuera de la app:
  - `maestros/extensiones.py`, el cuerpo de `Invernadero.tiene_sistema_iot()` y la ficha y la lista del invernadero, **solo** lo que dice
    `docs/api/extensiones_de_maestros.md`, «Estado del IoT del invernadero», con su prueba mínima en `maestros/tests/test_estado_iot.py`.
    Ninguna prueba existente de `maestros` se modifica;
  - `core/enlaces.py` (nuevo, solo si no existe: `nuevo_token` y `resumen_de`, como `docs/patrones/enlace_del_cliente.md`, «1. Piezas», D-65),
    con `core/tests/test_enlaces.py`;
  - `core/models.py`: solo las acciones de auditoría de arriba, y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_iot_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: la API del nodo y todo lo que escribe `EquipoAnunciado`, `Telemetria` o `ultimo_mensaje_en` (IOT-03); desactivar,
  activar y dar de baja el sistema, y la baja de equipos (IOT-06); los enlaces de las alertas (IOT-04); las órdenes de mantenimiento
  (IOT-07). **Nunca** se guarda ni se audita el token.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Estado del IoT en `maestros`.** El punto `registrar_estado_iot` y `estados_iot` en `maestros/extensiones.py`, `tiene_sistema_iot()` y la
   ficha y la lista, tal cual el contrato. Primero su prueba mínima con un registrante falso; después corré **toda** la suite de `maestros`:
   tiene que dar lo mismo que antes.
2. **Token.** Si `core/enlaces.py` no existe, crealo (`nuevo_token() -> (token, resumen)` y `resumen_de(token)`), con sus pruebas (el
   resumen es SHA-256 en hexadecimal de 64; dos tokens nunca coinciden; el token no se puede obtener del resumen).
3. **Servicios del sistema**, en `iot/servicios/sistemas.py`. Un caso de uso = una función en `transaction.atomic()`:
   - `resumen_de_registro(actor, datos)` (valida sin escribir), `registrar_sistema_iot(actor, datos) -> (sistema, token)`,
     `modificar_sistema_iot(actor, sistema_id, datos)` y `regenerar_token(actor, sistema_id) -> token`;
   - lectura: `sistema_del_invernadero(actor, invernadero_id)`, `invernaderos_para_registrar(actor)`, `conectividad(nodo, ahora)`,
     `acciones_permitidas(actor, sistema)`;
   - los registrantes de `maestros`: `estados_de_sistemas(invernadero_ids)`, `url_de_registro(actor, invernadero)` e
     `impedimentos_de_baja_del_invernadero(invernadero)` (código `sistema_iot`).
   - Todas las reglas y decisiones de `sistema_iot.md` («Para los cinco», IOT-REG-SIS e IOT-MOD-SIS): alcance verificado después de
     bloquear, precondición c (insumo de `repuestos_de_hardware`), datos del nodo, un sistema no dado de baja por invernadero (con el
     `IntegrityError` traducido), `sincronizar_alertas_de_personal` al registrar, la auditoría sin token.
   Pruebas: `iot/tests/test_iot_reg_sis.py` y `test_iot_mod_sis.py` (las clases `<CodigoCu>ServicioTests`). Una por regla y por
   postcondición; además: el Gerente no registra en un invernadero con Agrónomo activo y sí en uno sin él; un Agrónomo que deja de estar a
   cargo entre el resumen y la confirmación recibe la extensión 8b; el token devuelto coincide con `token_resumen` por `resumen_de` y no
   aparece en ningún `RegistroAuditoria`; regenerar invalida el resumen anterior; sin Técnico activo, se crea la alerta del Técnico y con
   Técnico, no. Concurrencia (`@tag("concurrencia")`, `test_sistemas_concurrencia.py`): dos registros a la vez en el mismo invernadero (uno
   lo logra, el otro recibe 8a, sin 500).
4. **Servicios del hardware**, en `iot/servicios/hardware.py` y `iot/servicios/compatibilidad.py`:
   - `alta_hardware(actor, sistema_id, datos)`, `modificar_hardware(actor, equipo_id, datos)`, `volver_a_activar(actor, equipo_id)` y
     `reactivar_hardware(actor, equipo_id)`. Al crear un **actuador** (y al cambiarle el tipo), antes de insertarlo, llamá en la misma transacción a
     `iot.servicios.tipos_actuador.bloquear_tipo_activo(tipo_id)` (contrato de D-40, como `bloquear_invernadero_activo`): el `INSERT` solo toma
     `FOR KEY SHARE`, que no frena la baja del tipo (IOT-BAJ-TAC); con el bloqueo, la baja espera, ve el equipo y se rechaza;
   - lectura: `buscar_equipos(actor, sistema, filtros)`, `ficha_del_equipo(actor, equipo_id)`, `acciones_permitidas(actor, equipo)`,
     `identificadores_anunciados_libres(sistema)`;
   - `recalcular_compatibilidad(actuadores)` (la única que calcula la compatibilidad; también la llaman `modificar_tipo_actuador`, que deja de
     tener el `TODO` de IOT-01, y la API de anuncios de IOT-03);
   - las que completan otras tareas, con su docstring «Se completa en IOT-NN»: `tiene_lecturas`, `tiene_comandos`,
     `tiene_comando_pendiente`, `tiene_reglas` (consultan sus tablas, vacías hasta IOT-03, IOT-05 e IOT-06) y `mantenimientos_a_realizar(equipo)`
     (lista vacía hasta IOT-07);
   - los registrantes de sector: `impedimentos_de_baja_del_sector(sector)` (`hardware_activo`) y `contenido_de_sectores(sectores)`;
   - en `iot/servicios/tipos_actuador.py`, completar `equipos_afectados(tipo)` y el conteo de la baja con datos reales.
   - Todas las reglas y decisiones de `hardware.md` («Cómo se aplica»): identificador (validador, comparación en minúsculas, índice único
     con su error de campo), sensor, actuador, insumo, sector, fecha, la alerta «dispositivo no registrado» resuelta, el alta desde una alerta
     con `?identificador=`, lo que cambia y lo que no al modificar, volver a activar y reactivar, bloqueos y auditoría.
   Pruebas: `iot/tests/test_iot_alt_hdw.py`, `test_iot_mod_hdw.py`, `test_iot_cns_hdw.py`, `test_compatibilidad.py` (sin anuncio queda
   «sin verificar»; con un `EquipoAnunciado` creado por la fábrica, compatible o incompatible con su alerta, que se resuelve al volver a ser
   compatible). La regla 3 de MOD se prueba con filas creadas por la fábrica (una lectura, un comando, una regla). Concurrencia
   (`test_hardware_concurrencia.py`): dos altas con el mismo identificador en el mismo sistema (una lo logra, la otra recibe el error del
   campo); reactivar un equipo mientras otro toma su identificador (uno de los dos falla con su mensaje, sin 500).
5. **Registrantes en `IotConfig.ready()`:** `registrar_estado_iot`, `registrar_impedimento_de_baja` (invernadero),
   `registrar_impedimento_de_baja_de_sector` y `registrar_contenido_de_sector`. Pruebas mínimas de cada uno
   (`iot/tests/test_registrantes_maestros.py`): con datos, neutro sin datos, sin consultas por fila (`assertNumQueries` con tres invernaderos
   o tres sectores), y en pantalla: la ficha del invernadero dice «Activo» o «Sin registrar» con el enlace; la baja de un sector con un
   equipo lo informa con «Quitales el sector…»; la baja de un invernadero con sistema lo informa con «Dalo de baja desde IoT · Sistema IoT.».
6. **Vistas, plantillas y pestañas.**
   - En `iot/urls.py`: `sistema/` (la pestaña, con `?invernadero=`), `sistema/registrar/` (elegir invernadero, datos, «Revisar» y
     «Registrar y generar token»), `sistema/<id>/modificar/`, `sistema/<id>/regenerar-token/`; `hardware/`, `hardware/nuevo/`
     (con `?identificador=`), `hardware/<id>/`, `hardware/<id>/modificar/`, `hardware/<id>/volver-a-activar/`,
     `hardware/<id>/reactivar/`. `/iot/` pasa a redirigir a «Sistema IoT».
   - La barra de contexto con el invernadero elegido (`?invernadero=` y la sesión `iot_invernadero`; fuera del alcance, 404) y las pestañas
     «Hardware» y «Sistema IoT» (D-25).
   - La pantalla del token se **renderiza** en la respuesta al POST (sin redirigir), con `never_cache` y `Cache-Control: no-store`; recargarla
     no vuelve a mostrar el token. Lo mismo al regenerar.
   - El Gerente que mira un invernadero con Agrónomo activo ve todo en solo lectura con el aviso del prototipo (`opBanner`).
   - Las vistas solo orquestan, con `rol_requerido`, `never_cache` y `vary_on_headers("HX-Request")` donde haya fragmento; ventanas con HTMX
     y respaldo sin JavaScript; errores por campo; aviso breve al terminar (D-29). Textos con voseo y los textos explicativos de cada
     extracto («Pantallas»).
   Pruebas: `iot/tests/test_sistemas_vistas.py` y `test_hardware_vistas.py` (permisos y alcance: los otros roles reciben 403; un invernadero
   fuera del alcance da 404; el Gerente con Agrónomo activo no ve botones de escritura; ningún botón lleva a un 403; la respuesta del token
   lleva `no-store` y un GET posterior no tiene el token; el flujo con HTMX y sin él; los errores por campo).
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`: tachar el punto 4 de «Cuando exista una ocupación de sector…», el punto 1 de «Cuando exista SistemaIoT» y la
     parte de registrar del punto 1 de «Cuando exista SistemaIoT (alertas)»; marcar hecha la parte de IOT-02 de «Cuando existan actuadores,
     comandos y reglas del IoT»;
   - marcar IOT-02 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta son los filtros y la búsqueda de la lista de equipos (se anota en `temas_abiertos.md`). No se
recortan las restricciones del identificador, el token una sola vez, los bloqueos ni los registrantes de `maestros`.

## Hecho cuando

- El Agrónomo registra el sistema IoT de un invernadero a su cargo (el Gerente, de uno sin Agrónomo activo), ve el token una sola vez y lo
  puede regenerar; nunca hay dos sistemas no dados de baja en un invernadero (lo garantiza la base).
- Registra, modifica, vuelve a activar, reactiva y consulta sensores y actuadores; nunca hay dos equipos no dados de baja con el mismo
  identificador en un sistema, sin distinguir mayúsculas (lo garantiza la base).
- La compatibilidad de cada actuador se calcula en un solo lugar y genera o resuelve su alerta.
- La ficha del invernadero muestra el estado del IoT; un sector con equipos y un invernadero con sistema no se dan de baja, con el motivo;
  registrar un sistema sin Técnico activo genera su alerta.
- El token no aparece en la base, en la auditoría ni en ningún log.
- Todas las pruebas de `maestros` que existían siguen pasando sin cambios.
- Pruebas: `iot/tests/test_iot_<cu>.py` (una por caso de uso, con `<CodigoCu>ServicioTests` y `<CodigoCu>VistaTests`),
  `test_compatibilidad.py`, `test_registrantes_maestros.py`, `maestros/tests/test_estado_iot.py` y, si se creó, `core/tests/test_enlaces.py`.
- Comando de pruebas:
  python manage.py test iot maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva (`core`): `python manage.py migrate`. Cuentas: Gerente, un Agrónomo a cargo de un invernadero sin Técnico y otro
invernadero sin Agrónomo. Un insumo activo de «Repuestos de hardware».

1. Con el Agrónomo: «IoT» abre en «Sistema IoT», con «Este invernadero no tiene Sistema IoT» y «Registrar sistema IoT». La ficha del
   invernadero (Datos maestros) dice «Sin registrar» con el mismo enlace.
2. Registrar el sistema con un rango de la solución de un solo valor: error en el rango. Completarlo, «Revisar»: el resumen avisa de la
   alerta del Técnico. Confirmar: aparece el token con «Copiar», la dirección de la API y la guía; «Cerrar» se habilita al marcar «Ya guardé
   el token». Recargar la página: el token no aparece.
3. La campana del Gerente tiene «Invernadero sin Técnico activo». La ficha del invernadero dice «Activo»; la lista, «Con IoT».
4. Regenerar el token: confirma y muestra el nuevo una sola vez. En «Auditoría» están `alta_sistema_iot` y `regeneracion_token_iot`, sin
   token.
5. «Hardware» · «Registrar hardware»: un sensor de temperatura `norte/sectorA/temperatura` en un sector, con calibración 0 a 50. Otro con
   `NORTE/sectorA/temperatura`: error en el identificador. Un actuador «Ventilador» `norte/sectorA/ventilador`: queda «Sin verificar».
6. Modificar el sensor: cambiar la variable (todavía no tiene lecturas) y el sector. Intentar dar de baja ese sector desde Datos maestros:
   lo impide y lista el equipo con «Quitales el sector…».
7. Intentar dar de baja el invernadero: lo impide con «Tiene el sistema IoT…».
8. Con el Gerente, en el invernadero del Agrónomo: ve todo en solo lectura con el aviso; en el invernadero sin Agrónomo, puede registrar.
9. Sin JavaScript, los pasos 2, 4, 5 y 6 funcionan igual: cada ventana es una página.
10. Hardware · «Ver ficha» del sensor: identificador, tipo, sector, «Sin confirmar», modelo, insumo y calibración; «Última lectura» dice «—». Con el Agrónomo, «Modificar»; con el
    Gerente en el invernadero con Agrónomo, ningún botón.
11. Un equipo que todavía no reportó: «Modificar» deja corregir el identificador. Si hay lecturas (se pueden crear a mano en la base), el campo sale deshabilitado con «Ya reportó…».
12. Dar de baja un equipo a mano en la base (`estado_hardware = inactivo`): su ficha ofrece «Reactivar». Si hay otro equipo con su identificador, la ventana dice «No se puede reactivar…».
    Con uno `fuera_de_servicio`, la ficha ofrece «Volver a activar».
13. «Hardware · Registrar hardware» con `?identificador=norte/algo` en la URL: el campo trae el identificador con «Tomado de la alerta «Dispositivo no registrado».».
14. Como Gerente, en «Tipos de actuador», modificar las acciones de un tipo con un actuador: si el nodo anunció equipos, la compatibilidad y la alerta «Configuración incompatible» se actualizan.
15. Después del merge: verificar en el log de Render que se aplicó la migración nueva.

## Cierre

**Qué se hizo.** Los siete pasos, en orden:
1. `maestros`: punto de extensión `registrar_estado_iot` / `estados_iot` / `url_de_registro_iot` (`maestros/extensiones.py`); `Invernadero.estado_iot()` y `tiene_sistema_iot()`; la ficha y la lista
   del invernadero muestran «Activo», «Desconectado» o «Sin registrar» con el enlace, y «Con IoT» (una sola llamada para toda la lista).
2. `core/enlaces.py` (`nuevo_token`, `resumen_de`) con sus pruebas. Migración `core/0019_iot_sistema_y_hardware_acciones` (solo `choices`); ninguna en `iot` ni en `maestros`.
3. `iot/servicios/sistemas.py` (registrar con resumen, modificar, regenerar el token, lectura, conectividad y acciones) y `iot/validadores.py`.
4. `iot/servicios/hardware.py` (alta, modificación, volver a activar, reactivar y consulta) y `iot/servicios/compatibilidad.py` (la única que calcula la compatibilidad); `modificar_tipo_actuador` ya
   la llama (se sacó el `TODO` de IOT-01).
5. `IotConfig.ready()` registra los cuatro puntos de `maestros` (con guarda contra el doble registro).
6. Vistas (`views_sistema.py`, `views_hardware.py`, `contexto.py`), plantillas, pestañas «Hardware», «Sistema IoT» y «Tipos de actuador»; `/iot/` redirige a «Sistema IoT».
7. Documentación propuesta (M3), sin aplicar.

**Pruebas.** `python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` (todas las apps, tras el merge de PRD-01): 3791 pruebas, todas en verde.
`python manage.py test iot produccion --keepdb --tag concurrencia`: 30 en verde, 17 de ellas de `iot` (dos altas con el mismo identificador, dos registros en el mismo invernadero, reactivar contra un alta, la baja de un tipo contra el alta de un actuador,
dos regeneraciones, y dos `test_d82_…` de la modificación de un tipo a la vez que el alta o el cambio de tipo de un actuador). `makemigrations --check`: sin cambios pendientes. Las de servicios se escribieron antes y se revisaron en rojo.
Las dos `test_d82_…` de `test_hardware_concurrencia.py` fuerzan el cruce con `detener_antes_de=(api_alertas, "bloquear_invernadero_para_alertas")`; con el orden invertido fallan con `DeadlockDetected` (comprobado).

**Decisiones.** D-82 (propuesta): el orden de bloqueos del hardware es tipo, invernadero, sistema y equipo (ver «Diferencias»). Se usó D-80 sin cambios.

**Diferencias con lo escrito (se corrigen en `hardware.md`, `sistema_iot.md` y D-82, M3; no se corrigieron en silencio).**
- **Orden de bloqueos del hardware** (`hardware.md`, «Bloqueos»: el invernadero, el sistema y, si cambia el tipo, el tipo): se bloquea el tipo ANTES que el invernadero. Si no, el alta de un actuador (invernadero y
  después tipo) e IOT-MOD-TAC (tipo y después los invernaderos de sus actuadores, al recalcular la compatibilidad) se cruzan y la base aborta una (500). Prueba: `test_hardware_concurrencia.py`, `test_d82_…` (con barrera; fallan con el orden inverso).
- **Reactivar un actuador cuyo tipo está dado de baja** (la regla 9 de IOT-MOD-HDW no lo contempla): se rechaza con `tipo_inactivo`; si no, quedaría un actuador activo de un tipo inactivo y se rompería la
  precondición c de IOT-BAJ-TAC.
- **`maestros` más allá del cuerpo de `tiene_sistema_iot()`:** se agregó `Invernadero.estado_iot()`, `precargar_estado_iot` en `maestros/servicios/invernaderos.py` y un cambio en `maestros/views.py` para que la lista
  y la ficha hagan UNA llamada al registrante (el contrato pide que no haya consultas por fila).
- **Pruebas existentes que cambiaron** (la tarea decía que ninguna de `maestros`): `iot/tests/test_tipos_actuador_vistas.py` (el destino de `/iot/`, que la tarea manda cambiar) y, con la aprobación del estudiante,
  `test_ext_impedimentos_de_sector_sin_registrantes_no_hay_ninguno` y `test_ext_contenido_sin_registrantes_esta_vacio` de `maestros/tests/test_extensiones_sectores.py`: asumían que ninguna app registraba los puntos de sector
  y `iot` ya los registra. Siguen probando el neutro «sin registrantes». Tras el merge, el `setUp` de PRD-01 en el mismo archivo aísla las mismas listas.
- `docs/casos_de_uso/iot/sistema_iot.md` cita una sección «Token» de `enlace_del_cliente.md` que no existe: la correcta es «1. Piezas».
- El texto «Ya lo usa {equipo} en este sistema IoT.» usa el nombre del prototipo (`hwName`: «Temperatura», o el tipo del actuador), que el caso de uso no define.

**Pantallas: lo que se corrigió del prototipo (D-61).**
- *Registrar el sistema:* el prototipo registraba en una sola pantalla; se hizo en tres (elegir invernadero, datos con «Revisar», confirmación) como pide el caso de uso (pasos 2 y 6). El aviso de la extensión 6b va
  completo en el resumen.
- *Token:* el prototipo lo muestra en una ventana sobre la ficha; acá es una página que es la respuesta al POST (sin redirigir, con `no-store`), con «Copiar» y la casilla «Ya guardé el token» como mejora de JavaScript
  (sin él, «Cerrar» siempre funciona). Además ofrece «Registrar hardware» después de registrar (paso 9).
- *Guía del nodo:* el botón del prototipo solo mostraba un aviso; es un enlace a `URL_GUIA_DEL_NODO`. *Fecha máxima:* la de hoy, no la fija del prototipo.
- *Barra de contexto:* el prototipo usa un `<select>` nativo; se usa el desplegable propio (D-24), que envía el formulario GET al cambiar, con el botón «Ver» como respaldo sin JavaScript.
- *Hardware, formulario:* se agregó el «Nombre» del sensor (opcional); la variable se puede cambiar si no hay lecturas; lo que no se puede cambiar se ve deshabilitado con su motivo. El cambio del tipo de equipo, de la
  variable o del tipo de actuador vuelve a dibujar el formulario sin guardar (con HTMX solo el bloque; sin JavaScript, la página).
- *Hardware, avisos de «antes de guardar»* (identificador de un equipo dado de baja con «Reactivar»; compatibilidad con lo que anunció el nodo): con HTMX llegan al cambiar el identificador; sin JavaScript aparecen al
  volver a dibujar el formulario y, si el actuador queda incompatible, en el aviso de después de guardar.
- *Volver a activar y reactivar:* ventanas con HTMX y respaldo sin JavaScript (la ficha con la ventana). Las órdenes de mantenimiento de la regla 8 las completa IOT-07.
- *Lista de equipos:* se agregaron el nodo central arriba (regla 2 de CNS), los estados vacíos, la búsqueda por serie y variable y el aviso de los anunciados sin registrar, solo para quien opera.
- *Ficha:* se agregaron las alertas activas del equipo (regla 6 de CNS); las lecturas, las reglas, los comandos y las órdenes no se muestran todavía (D-25).

**Lo que queda para otras tareas (ya está en `docs/disparadores.md`).** Lecturas y anuncios reales (IOT-03), comandos (IOT-05), reglas y la baja de equipos y del sistema (IOT-06), órdenes de mantenimiento (IOT-07).
