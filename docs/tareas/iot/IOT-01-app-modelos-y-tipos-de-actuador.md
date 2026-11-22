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
     parcial `(sistema)` con `clase = nodo` (incluye los dados de baja: el nodo no se reemplaza, D-72); `CheckConstraint` «nodo ⇔ identificador nulo» y «nodo ⇒ sin sector»;
     índice único parcial `(invernadero)` de `SistemaIoT` sin los inactivos; `token_resumen` único y nulo; un solo comando pendiente por
     actuador (índice único parcial); las de `Accion`, `Sensor` (calibración), `Telemetria`, `ReglaActuacion`, `Comando` y `AlertaIot`
     (`num_nonnulls(hardware, telemetria) <= 1`). Todas las FK `PROTECT`, salvo `EquipoAnunciado.sistema`, que es `CASCADE` (dato de diseño, MD-102; ver «Convenciones» de `docs/modelo/iot.md`).
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
   - Las que completan otras tareas, con su docstring «Se completa en IOT-NN»: `acciones_en_uso(tipo) -> dict[int, list[UsoDeAccion]]` y
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

## Verificación a mano

Hay migraciones nuevas (`iot`, `maestros` y `core`): `python manage.py migrate`. Cuentas: Gerente y un Agrónomo. Para el paso 6, además, una cuenta
de Capataz, Vendedor o Técnico.

1. Con el Gerente: el menú muestra «IoT» justo después de «Producción»; abre en «Tipos de actuador» con los seis tipos iniciales (Ventilador, Bomba,
   Luminaria, Calefactor, Ventana y Media sombra, de 60 s) y, debajo, el catálogo de capacidades en solo lectura.
2. «Nuevo tipo»: «Extractor», con «Encender» (`ENCENDER`) y «Fijar velocidad» (`FIJAR_NIVEL`, 0 a 100 %, unidad «%» propuesta). Al elegir el comando
   con valor aparecen el mínimo, el máximo y la unidad. «Crear tipo»: se crea y avisa. Registrar «extractor»: error «Ya existe un tipo de actuador con
   ese nombre.» junto al nombre y lo escrito se conserva.
3. «Modificar» el Extractor: «Agregar acción» (una fila más) con «Apagar» (`APAGAR`); cambiar «Fijar velocidad» a `ENCENDER`: error «Dos acciones
   usan el comando ENCENDER.». Volver a `FIJAR_NIVEL` y quitar «Fijar velocidad»: se guarda; en «Auditoría» hay un `modificacion_tipo_actuador` con
   la acción borrada en «Acciones borradas».
4. Quitar todas las acciones y guardar: «El tipo necesita al menos una acción activa.». Probar también un nombre de acción vacío y un rango con el
   mínimo mayor al máximo.
5. «Dar de baja» el Extractor: la ventana pide confirmar; queda inactivo, con «Reactivar» como único botón. Reactivarlo.
6. Con el Agrónomo: ve la lista y el catálogo, con el aviso de que los administra el Gerente, sin ningún botón de escritura; las URL
   `/iot/tipos/nuevo/`, `/iot/tipos/<id>/modificar/` y `/iot/tipos/<id>/baja/` dan 403. Con un Capataz, un Vendedor o un Técnico, `/iot/tipos/` da 403.
7. Sin JavaScript (desactivalo en el navegador), los pasos 2 a 5 funcionan igual: cada ventana es una página, «Agregar acción» y «Quitar» recargan la
   página con lo escrito, y después de elegir un comando con valor se toca «Actualizar filas» para que aparezcan el rango y la unidad.
8. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas (`core 0017`, `maestros 0010`, `iot 0001` a `0003`).

## Cierre

**Qué se hizo.**
- La app `iot` (nivel 7) con **todos** los modelos de `docs/modelo/iot.md` salvo `RegistroComando` (IOT-05) y `MantenimientoTecnico` (IOT-07), en
  `iot/migrations/0001_initial.py` con las restricciones de D-72; el catálogo (`0002`: 3 capacidades y 6 comandos) y los seis tipos iniciales (`0003`),
  idempotentes y con su inversa. `iot/catalogo.py`, `iot/alcance.py` (con `para` y `operables_por` en los `QuerySet`), las fábricas de `iot/tests/fabricas.py`
  y el admin de solo lectura.
- Los 14 parámetros IoT en `ConfiguracionOperativa` (`maestros/migrations/0010_parametros_iot.py`), en una lista aparte `PARAMETROS_IOT`: la pantalla y
  el formulario de MAE-04 siguen igual.
- Los 11 tipos de alerta del IoT y la entrada «IoT» del menú, en `IotConfig.ready()`.
- Los servicios de tipos de actuador (`iot/servicios/tipos_actuador.py`): alta, modificación, reactivación, baja, consulta, catálogo y
  `acciones_permitidas`; las vistas, las plantillas y el CSS (`iot/static/iot/css/iot.css`).
- `core`: las cuatro acciones de auditoría (`core/migrations/0017_iot_acciones_de_auditoria.py`) y los seis íconos del módulo.

**Pruebas** (todas en verde).
- `python manage.py test iot maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 2016 pruebas, OK (`iot`: 249).
- `python manage.py test iot --keepdb --tag concurrencia`: 6 pruebas, OK.
- `python manage.py test iot maestros core inventario --keepdb --tag migracion`: 8 pruebas, OK.
- `makemigrations --check --dry-run`: sin cambios pendientes. `inventario` también se corrió completa (OK).
- Las pruebas de servicios se escribieron primero y se mostraron en rojo (118 pruebas, módulo inexistente); el estudiante las aprobó antes de implementar.

**Decisiones y diferencias con la documentación.**
- `acciones_en_uso(tipo)` devuelve `dict[int, list[UsoDeAccion]]` (`UsoDeAccion(codigo, valor)`) y no `set[int]`: la regla 4 de IOT-MOD-TAC pide informar
  qué reglas o comandos lo impiden y dejar achicar el rango solo si ningún valor queda afuera. En IOT-01 devuelve `{}`; IOT-05 e IOT-06 le suman la consulta.
- `EquipoAnunciado.sistema` es `CASCADE` (MD-102, «Convenciones» de `docs/modelo/iot.md`) y el índice «un nodo por sistema» incluye los dados de baja (D-72, punto 2):
  el texto de este archivo, en «Límites» y en el paso 1, decía otra cosa en los dos puntos.
- La auditoría escribe **un registro por caso de uso** con las listas `acciones_creadas`, `acciones_modificadas`, `acciones_desactivadas` y `acciones_borradas`
  (así lo fija «Cómo se aplica»), no uno por acción como dice la postcondición d.
- `num_nonnulls(...)` de las restricciones se escribió con `Q` equivalentes. Largos que la ficha no fija: `Actuador.estado_informado` 30,
  `Telemetria.unidad_medida_telemetria` 10, `Accion.unidad_valor` 5.
- Se sumó `bloquear_tipo_activo(tipo_id)`, que no pedía la tarea: es el contrato de D-40 para quien cree un actuador (IOT-02), porque el `INSERT` solo toma
  `FOR KEY SHARE` y no frena la baja del tipo. Tiene su prueba de concurrencia.
- Una acción que cambia de nombre o de comando sale un momento de los índices únicos parciales (queda inactiva) para que dos acciones puedan
  intercambiar nombres o comandos sin chocar a mitad de camino.
- Las inversas de las migraciones `0002` y `0003` borran con `_raw_delete` una vez verificado que nada las usa: el `.delete()` normal fallaba de forma
  intermitente en la prueba de `core` que baja y vuelve a subir todas las migraciones.
- **Cambio a una prueba existente** (decidido por el estudiante): `maestros/tests/test_cns_alr.py`, `test_registrar_la_entrada_dos_veces_no_la_duplica`
  fijaba que «Alertas» fuera la tercera entrada del Gerente. Como la tarea pide registrar «IoT» con `despues_de="Producción"`, que lo deja antes, el assert
  pasó a un orden relativo («Panel de control» primero y «Producción» antes que «Alertas»). Se mantiene el `count("Alertas") == 1` por rol. Justificación:
  esa línea sobre-especificaba el orden completo y se rompe con cualquier módulo que se registre después de «Producción».
- Dos pruebas propias se corrigieron al implementar (no eran reglas): un nombre de tipo que chocaba con el inicial «Ventana» y el intercambio de acciones,
  que buscaba la fila por un nombre que acababa de cambiar.

**Pantallas: lo que se corrigió del prototipo** (D-61).
- Baja: el prototipo borra el tipo; acá es lógica y el tipo queda inactivo, visible, con «Reactivar» (ya anotado en el extracto).
- Se agregaron «Reactivar», los tipos inactivos y la marca «En uso» (regla 7 de MOD, reglas 1 y 2 de CNS).
- El formulario del prototipo cambia de comando con JavaScript: acá cada cambio (y «Agregar acción» y «Quitar») manda el formulario al servidor,
  que lo vuelve a dibujar sin guardar; con HTMX solo cambia el bloque de acciones y, sin JavaScript, hay un botón «Actualizar filas».
- Las filas de una acción en uso o con historial muestran el nombre, el comando y la unidad deshabilitados con el motivo (el prototipo solo bloquea el comando
  y la unidad, y solo para el historial); su valor viaja en un campo oculto.
- Textos agregados (no están en el extracto): el nombre de una acción de más de 40 caracteres, la unidad que no es de la lista del comando, «No se puede achicar
  el rango de «X»: quedarían afuera los valores de …» y «Las acciones del tipo cambiaron mientras lo editabas…» (`cambio_simultaneo`).
- «Quitar» se ofrece en toda fila, también en una acción en uso: el servicio la rechaza con el motivo, para no duplicar la regla en la plantilla.

**Para IOT-02 en adelante.** `bloquear_tipo_activo` antes de crear un actuador; `equipos_afectados` ya tiene datos reales; `recalcular_compatibilidad` se llama desde
`modificar_tipo_actuador` (hoy un `TODO` con la lista vacía). La pestaña «Tipos de actuador» queda como única del marco: cada tarea suma la suya, y `/iot/` redirige a
ella hasta IOT-02.
