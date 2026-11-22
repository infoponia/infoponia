# IOT-01 · App `iot`, todos sus modelos, catálogo y tipos de actuador

Estado: pendiente | App: iot (y una migración en maestros) | Rama: feature/iot-01-app-modelos-y-tipos-de-actuador | Ronda: IoT 1

Depende de: **MAE-03** (`SectorProduccion`), **MAE-04** (`ConfiguracionOperativa`), **INV-01** (`Insumo` y la categoría
`repuestos_de_hardware`) y UI-01. Si alguna de las tres primeras no está mergeada, frená. **No depende de ninguna tarea de producción ni de
comercial.**

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Crea la app `iot` (nivel 7 de D-37) con **el esquema entero del módulo** (D-72, punto 6), para que las tareas IOT-02 a
IOT-07 no cambien modelos, y el ABM más simple, que no depende de nada: los **tipos de actuador** (comunes a toda la organización, solo los
administra el Gerente). Suma los 14 parámetros IoT a la configuración operativa (sin pantalla: la sección «Módulo IoT» es de IOT-04) y
registra los 11 tipos de alerta del IoT. Las reglas que dependen de equipos, comandos o reglas, que todavía no existen, quedan escritas como
funciones que hoy devuelven «nada» (marcadas «Se completa en IOT-NN» en el extracto).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| IOT-ALT-TAC | Alta Tipo de Actuador | docs/casos_de_uso/iot/tipos_de_actuador.md | — |
| IOT-MOD-TAC | Modificar Tipo de Actuador (con la reactivación) | docs/casos_de_uso/iot/tipos_de_actuador.md | Regla 6 (equipos afectados) y 9 (compatibilidad): se completan en IOT-02. «En uso» y «con historial» (reglas 3 a 8): se completan en IOT-05 e IOT-06 |
| IOT-BAJ-TAC | Baja Tipo de Actuador | docs/casos_de_uso/iot/tipos_de_actuador.md | La cuenta de equipos (regla 2) ya se escribe; tiene datos desde IOT-02 |
| IOT-CNS-TAC | Consultar Tipo de Actuador | docs/casos_de_uso/iot/tipos_de_actuador.md | «En uso» (regla 2): se completa en IOT-05 e IOT-06 |

## Leer

- Casos de uso: el extracto de la tabla, completo, **incluida la sección «Cómo se aplica en la ronda»**.
- Modelo: **docs/modelo/iot.md entero** (esta tarea crea todos sus modelos); de docs/modelo/maestros.md, «ConfiguracionOperativa» y la regla 4
  de 8.22; de docs/modelo/inventario.md, `TipoInsumo.codigo`.
- Decisiones: **D-72** (la de esta tarea), D-70 (solo el punto del token: el campo `token_resumen`), D-71 (solo para saber qué guardan
  `ResumenHorario`, `FotoperiodoDiario` y `AlertaIot.correo_enviado_en`), D-76 (solo el punto 3: la columna `AlertaIot.ultimo_mensaje_en`),
  D-73 (por qué `MantenimientoTecnico` no se crea acá), D-05,
  D-06, D-14, D-21, D-24, D-25, D-28, D-29, D-30, D-36, D-37, D-44, D-47.
- API: docs/api/alertas.md (secciones 1 y 4: registrar tipos y el vínculo de origen).
- Patrones: docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md,
  docs/patrones/trabajo_en_paralelo.md («Migraciones»: la de `maestros` puede chocar con la de COM-04b).
- Pantallas: docs/prototipos/iot/ — leé primero su `README.md` («Cómo está armado»). Funciones: `render`, `NAV`, `ctxBar`, `tipos`,
  `cmdOpts`, `unidOpts`, `enUsoTac`, `histTac`, `act` (casos `tac-new`, `tac-mod`, `acc-add`, `acc-del`, `save-tac`), `modalHtml`
  (ventana `tbaj`). Lo que difiera de los casos de uso lo decide el caso de uso (L7): las diferencias ya detectadas están en el extracto,
  «Lo que difiere del prototipo».
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `maestros/models.py` (`ConfiguracionOperativa`, `SectorProduccion`, `Invernadero`, `Alerta`) y la última migración de `maestros`;
  - `maestros/alertas.py` (`TipoAlerta`, `registrar_tipo_de_alerta`, `Clase`, `Destinatario`, `Origen`);
  - `inventario/models.py` (`Insumo`, `TipoInsumo`) e `inventario/apps.py` (cómo una app registra su menú y sus tipos de alerta);
  - `maestros/servicios/cultivos.py` (el ABM más parecido: nombre único sin distinguir mayúsculas, reactivación);
  - `core/models.py` (auditoría: `Accion`, `ETIQUETAS`, `VALORES_VISIBLES`, `ACCIONES_DE_NEGOCIO`), `core/menu.py`, `core/acceso.py`
    (`rol_requerido`), `core/templatetags/iconos.py`.

## Límites

- Crea modelos: **todos** los de `docs/modelo/iot.md`, «Quién crea qué», salvo `RegistroComando` (IOT-05, necesita `produccion.Bitacora`)
  y `MantenimientoTecnico` (IOT-07): `Capacidad`, `ComandoCatalogo`, `TipoActuador`, `Accion`, `SistemaIoT`, `Hardware`, `NodoCentral`,
  `Sensor`, `Actuador`, `EquipoAnunciado`, `Telemetria`, `ResumenHorario`, `FotoperiodoDiario`, `Comando`, `ReglaActuacion` y `AlertaIot`.
  → revisá docs/disparadores.md: cierra «Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión», punto 1, para el IoT (el vínculo es
  `AlertaIot`); nace el punto 1 de «Cuando existan actuadores, comandos y reglas del IoT» (ya escrito en el lote I1).
- Migraciones:
  - `iot/migrations/0001_initial.py` (esquema; depende de la última de `maestros`, de `inventario` y de `core`);
  - `iot/migrations/0002_catalogo_de_capacidades.py` (datos: tres capacidades y seis comandos) y `0003_tipos_de_actuador_iniciales.py`
    (datos: los seis tipos con sus acciones), las dos con su función inversa y sin hacer nada si los datos ya están
    (`docs/patrones/datos_de_migracion.md`);
  - `maestros/migrations/00NN_parametros_iot.py`: los 14 campos de `ConfiguracionOperativa` con su valor inicial para la fila existente y sus
    `CheckConstraint`. Número: el libre en `main` al abrir el PR; si COM-04b se mergea antes, ajustá la dependencia (`trabajo_en_paralelo.md`);
  - una de `core`, solo de `choices`, con las cuatro acciones nuevas: `00NN_iot_acciones_de_auditoria`.
- Permitido fuera de la app:
  - `config/settings.py`: `'iot'` en `INSTALLED_APPS`, después de `'comercial'` (o de `'produccion'` si `comercial` no existe todavía), con
    el comentario `# nivel 7`;
  - `config/urls.py`: una línea, `path("iot/", include("iot.urls"))`, y la misma en `core/tests/urls_prueba_acceso.py`;
  - `maestros/models.py`: **solo** los 14 campos de `ConfiguracionOperativa` y sus restricciones (ni formulario ni pantalla: IOT-04);
  - `core/models.py`: solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO` (`alta_tipo_actuador`,
    `modificacion_tipo_actuador`, `reactivacion_tipo_actuador`, `baja_tipo_actuador`), y su migración;
  - `core/templatetags/iconos.py`: los íconos `activity`, `wrench`, `router`, `cpu`, `send` y `sliders` si no están, copiados del prototipo
    (objeto `P`, línea 203);
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_iot_1.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: sistema, hardware, lecturas, comandos, reglas y todo lo marcado «Se completa en IOT-NN»; la sección «Módulo IoT» de la
  pantalla de configuración (IOT-04); los enlaces de las alertas (IOT-04); la API del nodo (IOT-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App, modelos y migraciones.**
   - La app: `iot/__init__.py`, `apps.py` (`IotConfig`, con el docstring de nivel como las demás), `models.py`, `catalogo.py`, `servicios/`,
     `tests/`, y su lugar en `INSTALLED_APPS`.
   - Los modelos de `docs/modelo/iot.md`, con **todas** sus restricciones de base, en particular las de D-72: `Hardware` multitabla con
     `clase` y una sola FK `sistema`; índice único parcial `(sistema, Lower(identificador_equipo))` sin los dados de baja; índice único
     parcial `(sistema)` con `clase = nodo` sin los dados de baja; `CheckConstraint` «nodo ⇔ identificador nulo» y «nodo ⇒ sin sector»;
     índice único parcial `(invernadero)` de `SistemaIoT` sin los inactivos; `token_resumen` único y nulo; un solo comando pendiente por
     actuador (índice único parcial); las de `Accion`, `Sensor` (calibración), `Telemetria`, `ReglaActuacion`, `Comando` y `AlertaIot`
     (`num_nonnulls(hardware, telemetria) <= 1`). Todas las FK `PROTECT`.
   - Los `QuerySet` con `para(usuario)` y `operables_por(usuario)` (D-28) donde la ficha los pide; en esta tarea solo los usa `TipoActuador`
     (sin alcance: todos los tipos), pero el resto queda escrito con `iot/alcance.py` (`invernaderos_que_opera`, `invernaderos_que_consulta`,
     `puede_operar`; `docs/casos_de_uso/iot/sistema_iot.md`, «Para los cinco»), con sus pruebas.
   - `iot/catalogo.py`: `UNIDADES_POR_COMANDO`, `ESTADO_QUE_DEJA` (comando → estado del actuador, `docs/modelo/iot.md`) y
     `URL_GUIA_DEL_NODO` (`sistema_iot.md`).
   - Las migraciones del catálogo y de los tipos iniciales.
   - Los 14 parámetros en `ConfiguracionOperativa` y su migración en `maestros`.
   - El admin de solo lectura, como los demás; `__str__` y `verbose_name` en castellano.
   - Las fábricas en `iot/tests/fabricas.py`: `tipo_actuador(...)`, `sistema(invernadero, ...)` (con su nodo), `sensor(sistema, ...)`,
     `actuador(sistema, tipo, ...)`, `telemetria(sensor, ...)` y `comando(actuador, accion, ...)`, para que las tareas siguientes prueben sin
     servicios.
   Pruebas, en `iot/tests/test_modelos_iot.py`: una por restricción de la base (la viola y no la viola), incluidas dos equipos con el mismo
   identificador en mayúsculas distintas (choca), el mismo en dos sistemas (no choca) y uno dado de baja más su reemplazo (no choca), y dos
   telemetrías del mismo sensor con el mismo `medida_en` (choca: índice único de D-74, punto 6; la fábrica `telemetria` usa un `medida_en`
   distinto en cada llamada); las
   migraciones de datos (tres capacidades, seis comandos con su `lleva_valor`, seis tipos con sus acciones; correrlas dos veces no duplica);
   los 14 parámetros con su valor inicial y sus `CheckConstraint`; `iot/tests/test_alcance.py` con los tres casos de MD-98 (Agrónomo,
   Gerente con y sin Agrónomo activo en el invernadero, otro rol).
2. **Tipos de alerta.** En `IotConfig.ready()`, los 11 de `docs/modelo/iot.md`, «Tipos de alerta del IoT», con su código, nombre,
   destinatario, severidad, clase y origen. Prueba (`iot/tests/test_tipos_de_alerta.py`): están los 11 con esos datos y registrar dos veces
   no falla.
3. **Servicios de tipos de actuador**, en `iot/servicios/tipos_actuador.py`. Un caso de uso = una función en `transaction.atomic()`, con el
   orden de `docs/patrones/abm.md`, sección 2:
   - `alta_tipo_actuador(actor, datos)`, `modificar_tipo_actuador(actor, tipo_id, datos)`, `reactivar_tipo_actuador(actor, tipo_id)` y
     `baja_tipo_actuador(actor, tipo_id)`. `datos` es un `dataclass` (`DatosDeTipoActuador`, con la lista de acciones, cada una con el id de la
     original si la tenía) que arma `desde_post`.
   - Lectura: `listar_tipos(actor)`, `catalogo()` (capacidades con sus comandos y unidades), `acciones_permitidas(actor, tipo)`.
   - Las que completan otras tareas, con su docstring «Se completa en IOT-NN»: `acciones_en_uso(tipo) -> set[int]` y
     `acciones_con_historial(tipo) -> set[int]` (IOT-05 e IOT-06), `equipos_afectados(tipo) -> list[tuple[Invernadero, int]]` (IOT-02; ya
     escrita, con datos desde IOT-02) y la llamada a `recalcular_compatibilidad` (la crea IOT-02: en esta tarea, un `TODO` con la lista vacía).
   - Todas las reglas y decisiones de `tipos_de_actuador.md` («Cómo se aplica»): nombre único entre todos, acciones (comando del catálogo,
     rango y unidad según `lleva_valor`), al menos una acción activa, quitar con o sin historial, reactivación, bloqueos y auditoría.
   Pruebas: `iot/tests/test_iot_alt_tac.py`, `test_iot_mod_tac.py`, `test_iot_baj_tac.py`, `test_iot_cns_tac.py` (las clases
   `<CodigoCu>ServicioTests`). Una por regla y por postcondición; además: el Agrónomo no da de alta, no modifica ni da de baja; una acción en
   uso no se quita (con `mock.patch` sobre `acciones_en_uso`); una con historial queda inactiva y una sin historial se borra; la baja con un
   actuador creado por la fábrica se rechaza con su texto; sin cambios no se audita. Concurrencia (`@tag("concurrencia")`,
   `test_tipos_actuador_concurrencia.py`): dos altas con el mismo nombre (una crea, la otra recibe el error del campo); baja y modificación
   a la vez (las dos terminan, sin 500).
4. **Vistas, plantillas y menú.**
   - `iot/urls.py` (`app_name = "iot"`): `/iot/` (nombre `inicio`) redirige a «Tipos de actuador» (hasta IOT-02, que la cambia por «Sistema
     IoT»; IOT-04, por «Monitoreo»); `tipos/`, `tipos/nuevo/`, `tipos/<id>/modificar/`, `tipos/<id>/reactivar/`, `tipos/<id>/baja/`.
   - El marco del módulo: barra de contexto (`ctxBar`, en esta pantalla deshabilitada con «Todos los invernaderos») y pestañas (`NAV`). En
     esta tarea, solo «Tipos de actuador»; cada tarea suma la suya (D-25).
   - El formulario de acciones con HTMX («Agregar acción», «Quitar», el cambio de comando vacía unidad y rango) y respaldo sin JavaScript
     (un botón «Agregar acción» que vuelve a dibujar el formulario con una fila más).
   - Las vistas solo orquestan (`docs/patrones/abm.md`, sección 1), con `rol_requerido`, `never_cache` y `vary_on_headers("HX-Request")`
     donde haya fragmento; ventanas con HTMX y respaldo sin JavaScript; errores por campo; aviso breve al terminar (D-29). Textos con voseo y
     los textos explicativos del extracto («Pantallas»).
   - La entrada del menú, desde `IotConfig.ready()`: `registrar_entrada(("IoT", "iot:inicio", "activity"), (GERENTE, AGRONOMO),
     despues_de="Producción")`.
   Pruebas: `iot/tests/test_tipos_actuador_vistas.py` (permisos: el Agrónomo ve la lista y el catálogo sin botones y recibe 403 en las URL de
   escritura; los demás roles reciben 403 en todo el módulo; ningún botón lleva a un 403; el flujo con HTMX y sin él; los errores por campo)
   y la entrada del menú para los dos roles.
5. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - en `docs/disparadores.md`: tachar el punto 1 de «Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión» para el IoT;
   - marcar IOT-01 en `docs/tareas/README.md` y en `docs/tareas/ronda_iot_1.md`.
   Lo que haya quedado distinto de lo escrito va a `docs/temas_abiertos.md`.

Si el tiempo apremia, lo último que se recorta es el respaldo sin JavaScript del formulario de acciones (se anota en `temas_abiertos.md`). No
se recortan las restricciones de la base, las migraciones de datos ni los tipos de alerta: IOT-02 en adelante los dan por hechos.

## Hecho cuando

- `python manage.py migrate` crea el esquema completo del IoT, el catálogo y los seis tipos iniciales; `ConfiguracionOperativa` tiene los
  14 parámetros con su valor inicial.
- El Gerente registra, modifica, reactiva, da de baja y consulta tipos de actuador; el Agrónomo los consulta sin botones de escritura.
- Nunca hay dos tipos con el mismo nombre (lo garantiza la base) ni un tipo activo sin una acción activa.
- Los 11 tipos de alerta del IoT están registrados.
- Las restricciones de D-72 están en la base y tienen su prueba.
- Pruebas: `iot/tests/test_iot_<cu>.py` (una por caso de uso, con `<CodigoCu>ServicioTests` y `<CodigoCu>VistaTests`),
  `test_modelos_iot.py`, `test_alcance.py`, `test_tipos_de_alerta.py`.
- Comando de pruebas:
  python manage.py test iot maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test iot --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`iot`, `maestros` y `core`): `python manage.py migrate`. Cuentas: Gerente y un Agrónomo.

1. Con el Gerente: el menú muestra «IoT»; abre en «Tipos de actuador» con los seis tipos iniciales y, debajo, el catálogo de capacidades en
   solo lectura.
2. Registrar «Extractor» con «Encender» (`ENCENDER`) y «Fijar velocidad» (`FIJAR_NIVEL`, 0 a 100 %): se crea. Registrar «extractor»: error
   en el nombre.
3. Modificarlo: agregar «Apagar» (`APAGAR`), cambiar «Fijar velocidad» a `ENCENDER`: error «Dos acciones usan el comando ENCENDER.».
   Quitar «Fijar velocidad»: se guarda; en «Auditoría» hay un `modificacion_tipo_actuador` con la acción borrada.
4. Quitar todas las acciones: «El tipo necesita al menos una acción activa.».
5. Darlo de baja: queda inactivo, con «Reactivar»; reactivarlo.
6. Con el Agrónomo: ve la lista y el catálogo, con el aviso de que los administra el Gerente, sin botones; la URL de alta da 403.
7. Sin JavaScript, los pasos 2 a 5 funcionan igual: cada ventana es una página.
8. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
