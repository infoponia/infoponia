# INV-03 · Variedades, con su ciclo y la creación de su semilla

Estado: pendiente | App: inventario (con una migración en maestros) | Rama: feature/inv-03-variedades-y-semillas | Ronda: Producción 1

Depende de: MAE-03 (cultivos, `TipoEtapa` y las tres tablas de variedad con columnas mínimas), INV-01 (modelos y extensiones de
`inventario`), INV-02 (`habilitar_insumo` y las existencias; el botón «Habilitar la semilla» y la consulta de la semilla las usan),
UI-01 y NOT-01. Si alguna no está hecha, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es la tarea que **cierra el lazo de las semillas**: hasta ahora las
semillas no existían (INV-01 las rechaza) y MAE-03 dejó puntos de extensión sin registrante.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-ALT-VAR | Alta Variedad | docs/casos_de_uso/inventario/variedades.md | Crea variedad, ciclo, etapas y semilla; ofrece habilitar la semilla (CMP-HAB-IIN, INV-02) |
| PROD-MOD-VAR | Modificar Variedad | docs/casos_de_uso/inventario/variedades.md | Lotes y órdenes por `registrar_uso_de_variedad` (los registra PRD-01): sin ellos, nada bloquea |
| PROD-BAJ-VAR | Baja Variedad | docs/casos_de_uso/inventario/variedades.md | Impedimentos de lotes y órdenes por punto de extensión (PRD-01); **la precondición f (contratos) queda sin verificar hasta que `comercial` la registre** |
| PROD-CNS-VAR | Consultar Variedad | docs/casos_de_uso/inventario/variedades.md | Dentro de «Cultivos y variedades» (MAE-03); el formulario es también el detalle |

## Leer

- Casos de uso: el extracto de la tabla, completo, **incluida la sección «Cómo se aplica en la ronda»** (es donde están las decisiones
  de aplicación: dónde va cada cosa, el resumen, la advertencia de rangos, las notificaciones, la auditoría, los bloqueos); y, de
  `docs/casos_de_uso/maestros/cultivos.md`, solo PROD-MOD-CLT (regla 3: el renombre de las semillas) y su sección «Cómo se aplica»
- Modelo: docs/modelo/maestros.md — «Tipo de etapa», «Cultivo» y «Variedad, Ciclo y EtapaProductiva»; docs/modelo/inventario.md — «Insumo»,
  «InsumoInvernadero» y «Semilla»; y la fila 6 de «Diferencias con el caso de uso»
- Decisiones: D-05, D-14, D-22, D-27, D-28, D-30, D-32, D-36, D-37, D-40, D-42, D-43, D-44, D-45, D-46, D-47, D-49
- API: docs/api/variedades.md (lo que vas a implementar para `produccion`), docs/api/extensiones_de_inventario.md (los tres puntos de
  variedades que declarás y lo que registrás en `maestros`), docs/api/extensiones_de_maestros.md («Cultivos»), docs/api/stock.md
  (`habilitar_insumo`, `reevaluar_alertas_del_insumo`) y docs/api/notificaciones.md
- Patrones: docs/patrones/stock.md (secciones 1, 4 y 5: bloqueos), docs/patrones/abm.md, docs/patrones/bloqueos.md,
  docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md, docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/ — `cultivosTab` (la tabla de variedades de cada tarjeta), `INIT['var-form']`, `varCalc`, `RANGOS`,
  `ETAPAS`, `PERFILES`, `VIEWS['var-form']` (formulario y resumen y pantalla de «Qué sigue»), `ACT['var-save']`, `difAmb`, `MODALS['var-umbral']`,
  `MODALS['var-baja']` (en el código, la ventana de baja), `ACT['var-react']`, `usosVar`, `puedeVar`, `otrosVar`, `quienesVar`, `semDe`, `habEn`,
  `ciclo` y `et` (el diagrama del ciclo y el chip de cada tipo de etapa). Solo guía visual: lo que difiera de los CU lo decide el CU (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: maestros/models.py (`TipoEtapa`, `Cultivo`, `Variedad`, `Ciclo`, `EtapaProductiva`), maestros/extensiones.py (incluidos los
  puntos de cultivos), maestros/servicios/cultivos.py y su vista de «Cultivos y variedades», maestros/servicios/invernaderos.py
  (`bloquear_invernadero_activo`, `bloquear_invernadero_para_alertas`), inventario/models.py, inventario/extensiones.py,
  inventario/servicios/ (`insumos_invernadero.py`, `stock.py`, `alertas_de_stock.py`, `formato.py`), inventario/categorias.py,
  core/notificaciones.py, `FaltaConfirmarAdvertencia` de MAE-03

## Límites

- Crea modelos: `Semilla` (en `inventario`) → revisá docs/disparadores.md («Cuando exista InsumoInvernadero» y «Cuando exista una ocupación de
  sector, una variedad con semilla o un hardware»)
- Columnas nuevas en `maestros.Variedad` (rangos, postcosecha, peso en gramos) y la restricción única `(cultivo, lower(nombre_variedad))`
- Migraciones: solo nuevas. **En `maestros`**: una de esquema (`variedad_condiciones`) que depende de la última de MAE-03; **en `inventario`**:
  una de esquema (`semilla`) que depende de la de `maestros` y de la última de INV-01/INV-02. Con una de `core` (choices de auditoría). Ninguna de datos
- Permitido fuera de la app: `maestros/models.py` (solo las columnas y restricciones de `Variedad` de la ficha) y su migración; `maestros/views.py` y la
  plantilla de «Cultivos y variedades» **solo** para que usen `variedades_de_cultivos` si MAE-03 no lo dejó hecho (frená si hay que tocar más);
  `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`: `alta_variedad`, `modificacion_variedad`,
  `baja_variedad`, `reactivacion_variedad`, `modificacion_semilla`), su migración, y los textos de cierre de `docs/disparadores.md`,
  `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md`
- Dependencias nuevas: ninguna
- Fuera de alcance: lotes, órdenes, siembra y alertas de rangos (`produccion` e IoT); los contratos (`comercial`); alta de variedades desde la
  pantalla de cultivos que no sea el botón que ya define este plan; `descripcion_etapa` (no la usa ningún caso de uso); un estado propio de la etapa
  (opción A); tope físico de temperatura e intensidad lumínica (no lo tienen); los asientos (D-45)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, migraciones y puntos de extensión.**
   - `maestros`: las diez columnas de la ficha («Variedad»: `temp_ambiente_min/max`, `humedad_min/max`, `intensidad_luz_min/max`,
     `fotoperiodo_min/max`, `duracion_post_cosecha`, `peso_promedio_planta`) con `DecimalField(max_digits=7, decimal_places=2)` para los rangos,
     los `CheckConstraint` (cada mínimo ≤ máximo; humedad entre 0 y 100 y fotoperíodo entre 0 y 24; postcosecha entre 1 y 60; peso > 0; dominios de perfil y estado) y `UniqueConstraint` sobre
     `(cultivo, Lower("nombre_variedad"))`. **Antes de crear la migración** corré `Variedad.objects.count()` en tu base local: si hay filas
     cargadas a mano en `/admin/` (MAE-03 lo pedía en su verificación), la migración las rechaza con un mensaje claro (una operación
     `RunPython` previa que lanza `RuntimeError("Hay N variedades de prueba cargadas a mano: borralas desde /admin/ antes de migrar")`) en vez
     de inventarles rangos; con la tabla vacía, las columnas se agregan con un valor por única vez (`preserve_default=False`). **Avisá al
     estudiante** para que revise lo mismo en la base de Neon antes del merge.
   - `inventario`: `Semilla(Insumo)` con `variedad = OneToOneField("maestros.Variedad", on_delete=PROTECT, related_name="semilla")`, y su
     `__str__` (el nombre). Los tres puntos de extensión de variedades en `inventario/extensiones.py` con su resultado neutro
     (`UsoDeVariedad`, `uso_de_variedades`, `variedades_presentes`, `impedimentos_de_baja_de_variedad`), según
     `docs/api/extensiones_de_inventario.md`.
   - Fábricas: `variedad_con_semilla` y `usos_de_variedad_de_prueba` en `inventario/tests/fabricas.py`.
   - Pruebas: `inventario/tests/test_modelos_variedad.py` (cada restricción: viola y no viola; el nombre repetido con otras mayúsculas y con
     espacios; mismo nombre en otro cultivo sí; la baja no libera el nombre), `test_semilla_modelo.py` (una semilla por variedad; invariante:
     toda `Semilla` está en la categoría `semillas` y ningún otro insumo lo está) y `test_extensiones_variedades.py` (neutros sin registrantes,
     se juntan los de varios registrantes, sin consultas por fila), más la de **migración** (`@tag("migracion")`: tabla vacía y con filas).
2. **Auditoría en `core`.** Las acciones de «Límites», con etiquetas (nombres visibles de «perfil familiar», «duración postcosecha», «peso promedio por
   planta», «etapas», «temperatura ambiente», «humedad», «intensidad lumínica» y «fotoperíodo», cada una con su mínimo y su máximo), su clasificación en
   `ACCIONES_DE_NEGOCIO` y su migración de `choices`. Pruebas: la que ya clasifica cada acción
   (`test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio`) y que el Gerente las ve en «Auditoría».
3. **Lectura y bloqueo** en `inventario/servicios/ciclos.py` y `variedades.py`: todo lo de la sección «Lectura» y «Bloqueo» de
   `docs/api/variedades.md` (`etapas_de`, `duracion_del_ciclo`, `dias_hasta_maduracion`, `tipos_de_etapa_de`, `obtener_variedad`, `semilla_de`,
   `rangos_de`, `uso_de_variedades`, `invernaderos_que_usan`, `puede_gestionar`, `acciones_permitidas`, `variedades_activas`, `bloquear_variedad`), más
   `impedimentos_de_baja_de_variedad`, `variedades_presentes` y `incompatibilidades_de_rangos(variedad, rangos_nuevos)` (la regla de la sección
   «Advertencia de rangos» del extracto), y `umbral_efectivo` y `variables_incompatibles` (sección «Umbral efectivo» de `docs/api/variedades.md`;
   agregadas el 21/11/2026: las usan PRD-01 y el módulo IoT). Una consulta por tabla para toda la lista de ids. Pruebas: `test_ciclos_lectura.py` (orden por
   `puesto_global`, suma, días hasta Maduración con y sin etapas intermedias, sin consultas por fila con `assertNumQueries`),
   `test_variedades_lectura.py` (quién usa, `puede_gestionar` en sus tres casos con registrantes falsos, acciones y su motivo, invernadero
   inactivo no cuenta como usuario) y `test_incompatibilidades_de_rangos.py` (rangos que se cruzan, que se tocan en un extremo —no hay
   incompatibilidad—, que no se cruzan; cada variable; ninguna otra variedad presente → ninguna) y `test_umbral_efectivo.py`, con
   `variedades_presentes_de_prueba`: sin registrante, todo `None`; invernadero sin variedades, `None`; una variedad, sus rangos; dos que se
   cruzan, la intersección y qué variedad fija cada límite; empate en un límite, la de menor id; rangos que se tocan en un extremo,
   `minimo == maximo`; una variable sin superposición, esa variable `None` y las demás bien; varios invernaderos en una llamada, sin una
   consulta por invernadero (`assertNumQueries`); `variables_incompatibles` compatible, incompatible por arriba y por abajo con su variedad
   limitante, umbral `None` y variable del umbral ya vacía. La fábrica `variedades_presentes_de_prueba` va en `inventario/tests/fabricas.py`.
4. **Semilla y alta** (PROD-ALT-VAR): `inventario/servicios/semillas.py` (`crear_semilla`, `renombrar_semilla`, `dar_de_baja_semilla`,
   `reactivar_semilla`: la categoría `semillas` se busca por `codigo`, unidad `unidad`, controla vencimiento, estado igual al de la variedad;
   ninguna toca existencias) y, en `variedades.py`, `DatosDeVariedad`, `resumen_de_alta` (valida todo y devuelve el resumen sin escribir) y
   `alta_variedad(actor, cultivo_id, datos)`: bloquea cultivo → verifica activo y que el actor siga activo → valida todo (errores por campo,
   los textos de «Decisiones de aplicación» y del prototipo) → crea variedad, ciclo, etapas y semilla → **un registro de auditoría**
   (`alta_variedad`; variedad, ciclo, etapas y semilla como afectados; rangos como texto) → devuelve la variedad. Todo en una `transaction.atomic()`.
   Pruebas: `test_prod_alt_var.py` (una por regla 1 a 10 y por postcondición a a d: cada perfil con sus etapas permitidas y no permitidas, Germinación y
   Maduración obligatorias, orden de las etapas, duración cero y negativa, rango con mínimo mayor, mínimo igual al máximo, humedad 100,01 y −1, fotoperíodo 24,01, postcosecha 0, 1, 60 y 61,
   peso 0 y con decimales, nombre repetido con otras mayúsculas, con espacios, **con una variedad dada de baja** y en otro cultivo, cultivo inactivo,
   nombre de la semilla, nombre de 51 caracteres, que un error no deja nada creado) y `test_variedades_concurrencia.py` (etiqueta `concurrencia`: dos altas con el
   mismo nombre; el alta contra la baja del cultivo).
5. **Modificar y reactivar** (PROD-MOD-VAR): `resumen_de_modificacion` (sin escribir: cambios con su antes, el nombre nuevo de la semilla, los
   invernaderos que se notificarán y las advertencias de rangos), `modificar_variedad(actor, variedad_id, datos, *, advertencia_confirmada=False)` y
   `reactivar_variedad(actor, variedad_id)`. Cultivo → variedad → insumo bloqueados, luego releer; verificar que el actor puede gestionarla **después de
   bloquear**; las reglas 2 a 9 y las postcondiciones a a e; «sin cambios» no escribe ni notifica (D-28); `FaltaConfirmarAdvertencia` si hay
   incompatibilidades y no se confirmó; notificaciones agrupadas por Agrónomo (`notificar`, una por cuenta, con los invernaderos que le tocan) solo si
   cambió nombre, duraciones, etapas o rangos, sin el actor; el cambio de nombre renombra la semilla dentro de la misma transacción y del mismo registro
   de auditoría (`modificacion_variedad`; etapas antes y después como lista de textos). La reactivación (`reactivacion_variedad`) exige el cultivo activo (lo
   bloquea) y reactiva variedad y semilla sin tocar existencias. Pruebas: `test_prod_mod_var.py` (una por regla y por postcondición; etapas con y
   sin lotes; perfil con lotes activos y con órdenes a realizar, con registrantes falsos; la advertencia y «guardar igual»; notificaciones a Agrónomos
   de otros invernaderos, sin Agrónomo, y que el actor no se notifica; renombre; sin cambios) y `test_prod_mod_var_reactivar.py` (cultivo inactivo, semilla
   reactivada, existencias sin tocar). En `test_variedades_concurrencia.py`: dos modificaciones del mismo nombre a la vez, una modificación contra una baja y
   el renombre del cultivo contra el de la variedad.
6. **Baja** (PROD-BAJ-VAR): `baja_variedad(actor, variedad_id)` y `informe_de_baja(variedad)` (qué impide la baja, dónde está habilitada la semilla y cuánto
   stock queda por invernadero, sin bloquear). Bloquea los invernaderos donde la semilla está habilitada (se leen sin bloquear, se bloquean en orden de id y
   se vuelve a leer), después cultivo, variedad e insumo; verifica las precondiciones b a f **después** de bloquear y las junta todas (regla 2); deja inactivas
   variedad y semilla **sin deshabilitar existencias**; llama a `reevaluar_alertas_del_insumo` por cada existencia (la de «bajo el mínimo» se resuelve);
   audita `baja_variedad` (variedad y semilla). Pruebas: `test_prod_baj_var.py` (una por regla y por precondición con registrantes falsos: lotes activos, órdenes, contratos,
   los tres juntos, sin gestora, ya inactiva; semilla habilitada en otros invernaderos y con stock; existencias intactas; la alerta de bajo mínimo se resuelve; la
   semilla inactiva sigue ofreciéndose en CMP-AJT-STK).
7. **Conexión con `maestros`** (`InventarioConfig.ready()`): `registrar_semillas_de_cultivo` (`contar` y `renombrar`, con un `modificacion_semilla` por
   semilla; bloquea `Insumo` en orden de id), `registrar_uso_de_cultivo` (existencias activas de las semillas del cultivo más lo que informa
   `uso_de_variedades`) y `registrar_variedades_de_cultivo` (se arma en el paso 8). Pruebas: `test_registrantes_de_maestros.py` (las tres pruebas mínimas de cada
   registrante; el renombre de un cultivo con tres variedades deja tres semillas renombradas y tres registros; el nombre de la semilla nunca pasa de 100;
   `modificar_cultivo` de MAE-03 de punta a punta con estos registrantes).
8. **Consulta y pantallas** (PROD-CNS-VAR): la tabla de variedades de cada tarjeta (variedad, perfil, ciclo con su diagrama y los días, semilla con los
   invernaderos donde está habilitada o «Sin habilitar», estado y acciones) y los botones «+ Variedad» y «Reactivar», que entrega
   `registrar_variedades_de_cultivo`; las páginas «Nueva variedad» y «Modificar variedad» con sus dos pasos (formulario y resumen) y la de «Qué sigue» tras el alta
   (con el botón «Habilitar la semilla en un invernadero», que abre la ventana de CMP-HAB-IIN de INV-02 para esa semilla); la página de baja (impedimentos, aviso de la
   semilla habilitada y del stock); la ventana de «Revise antes de guardar» (advertencia de rangos); la reactivación. El formulario de una variedad inactiva o sin
   permiso se ve **deshabilitado con su motivo**. Rutas bajo `/produccion/variedades/…` y `/produccion/cultivos/<id>/variedades/nueva/` (`inventario/urls.py`). HTMX con respaldo
   sin JavaScript (D-24, D-29, D-47). Todas las vistas exigen Agrónomo (el Gerente: 404, igual que «Cultivos»). Pruebas: `inventario/tests/test_variedades_vistas.py` (permisos
   por rol; que el Gerente no las ve; errores por campo; que al elegir el perfil se ofrecen solo sus etapas; el resumen con los valores anteriores; la advertencia; la baja con
   impedimentos falsos; el formulario deshabilitado; que el HTML escapa el nombre; que no hay consultas por fila en la tabla).
9. **Cierre de documentación.** Proponé, sin aplicarlos (M3): cerrar lo que corresponda en `docs/disparadores.md` (en especial «Cuando exista una ocupación de sector, una variedad con
   semilla o un hardware», punto 3, y el apartado «Cuando existan lotes, órdenes de trabajo y contratos»); marcar INV-03 en `docs/tareas/README.md` y en
   `docs/tareas/ronda_produccion_1.md`. Para `docs/temas_abiertos.md`, proponé anotar que la precondición f de PROD-BAJ-VAR (contratos) no se verifica y cualquier cosa que
   hayas implementado distinta de lo escrito: no la corrijas en silencio.

Si el tiempo apremia, lo último que se recorta es la pantalla de modificación con el resumen de valores anteriores (queda el servicio completo y se anota). Las reglas
del servicio, los bloqueos, las notificaciones, la advertencia de rangos y el todo o nada no se recortan.

## Hecho cuando

- Los cuatro casos de uso están implementados con una prueba por regla y por postcondición y con sus pruebas de vista.
- Dar de alta una variedad crea, en una sola transacción, la variedad, su ciclo, sus etapas y su semilla «Semilla {cultivo} {variedad}» (categoría `semillas`, unidad
  `unidad`, controla vencimiento, sin habilitar), y deja **un** registro de auditoría.
- Renombrar la variedad o su cultivo renombra su semilla, y el nombre de la semilla nunca pasa de 100 caracteres.
- La baja de una variedad deja inactivas la variedad y la semilla, conserva las existencias de la semilla y la semilla se puede ajustar en CMP-AJT-STK.
- Los puntos de extensión coinciden con `docs/api/extensiones_de_inventario.md` y `docs/api/variedades.md` y se prueban con registrantes falsos.
- `umbral_efectivo` y `variables_incompatibles` cumplen la sección «Umbral efectivo» de `docs/api/variedades.md` (`test_umbral_efectivo.py`).
- Comando de pruebas:
  python manage.py test inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test inventario --keepdb --tag concurrencia
  python manage.py test inventario maestros --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas: `python manage.py migrate` (en `maestros`, `inventario` y `core`). Cuentas: Gerente, dos Agrónomos (uno con un invernadero a
cargo y otro con otro invernadero), Capataz. Hace falta un cultivo (por ejemplo «Lechuga») y, para los pasos 8 a 10, haber habilitado una semilla en un invernadero.

1. `migrate` pasa sin errores (con la tabla de variedades vacía). Si hubiera variedades cargadas a mano, falla con el mensaje de «Antes de crear la migración». **Antes de `migrate` en tu base local y en Neon, borrá desde `/admin/` las variedades cargadas a mano (las que no tienen ciclo): la migración las rechaza con «Hay N variedades de prueba cargadas a mano».**
2. «Producción» → «Cultivos y variedades» (Agrónomo): la tarjeta de «Lechuga» tiene el botón «+ Variedad». El Gerente no ve la pestaña y la URL le da 404.
3. «Nueva variedad» «Butterhead»: sin completar nada, cada campo marca su error; con perfil «Hoja verde» solo se ofrecen Germinación, Crecimiento y Maduración (no
   Floración ni Fructificación); con «Frutos grandes», las cinco. Las duraciones y el mínimo mayor que el máximo dan error; el nombre repetido con otras mayúsculas también.
4. Con los datos válidos, «Revisar resumen» muestra la duración del ciclo (suma), la cosecha estimada y «Semilla Lechuga Butterhead»; «Volver a editar» conserva lo escrito.
   «Crear variedad» muestra «Qué sigue» con el botón para habilitar la semilla.
5. «Auditoría» (Gerente) tiene **un** registro `alta_variedad` con variedad, ciclo, etapas y semilla. En «Inventario» → «Catálogo» aparece la semilla
   (categoría Semillas, unidad «unidad», con vencimiento, «Viene del alta de la variedad») y no se puede modificar ni dar de baja desde ahí.
6. «Habilitar la semilla en un invernadero» abre la ventana de INV-02 y la habilita. La tabla de la tarjeta muestra «Habilitada en Invernadero …».
7. Con el Agrónomo que **no** tiene a cargo el invernadero donde se habilitó la semilla: los botones de modificar y dar de baja aparecen deshabilitados con «Solo la usa Invernadero … (nombre del Agrónomo)». Con el Agrónomo de ese invernadero, funcionan. (Antes del paso 6, cualquiera de los dos podía, porque nadie la usaba.)
8. Cambiar el nombre y una duración: el resumen muestra los valores anteriores, el nombre nuevo de la semilla y a quiénes se notificará. Guardar sin cambios no crea
   registro. Al guardar con cambios, el otro Agrónomo recibe la notificación (campana) y la semilla cambió de nombre.
9. Renombrar el cultivo «Lechuga» a «Lechuga común»: el aviso dice cuántas semillas se renombran; al guardar, las semillas tienen el nombre nuevo y «Auditoría» muestra un
   `modificacion_semilla` por semilla.
10. Dar de baja la variedad con la semilla habilitada y con stock (cargado con un ajuste): la baja informa dónde está habilitada y cuánto stock queda, y la hace. Variedad y
    semilla quedan inactivas; en «Existencias de insumos» la existencia sigue activa y en CMP-AJT-STK la semilla se puede ajustar a cero. Reactivar con el cultivo inactivo
    da el aviso «Primero reactivá el cultivo»; con el cultivo activo, «Reactivar» abre una página de confirmación y, al confirmar, reactiva variedad y semilla y no vuelve a habilitar nada.
11. Con lotes u órdenes simulados desde la consola (registrante falso en `ready()`, solo para probar) la baja no se hace y lista todo junto; el perfil no se puede cambiar.
12. Dos Agrónomos crean «Butterhead» a la vez: una sola gana; la otra ve el error de nombre repetido y no hay error 500.
13. Sin JavaScript, los pasos 3, 4, 8 y 10 funcionan igual (cada ventana es una página).
14. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo (22/11/2026).** Los nueve pasos, de corrido y con las pruebas de cada uno en verde:

1. **Modelos y migraciones.** `maestros.Variedad` con sus diez columnas, los `CheckConstraint` y la única `(cultivo, lower(nombre_variedad))` (`maestros/0009_variedad_condiciones`, con guarda `RuntimeError` si hay variedades cargadas a mano); `inventario.Semilla(Insumo)` (`inventario/0003_semilla`); los tres puntos de extensión de variedades; fábricas `variedad_con_semilla`, `usos_de_variedad_de_prueba` y `variedades_presentes_de_prueba`.
2. **Auditoría.** Cinco acciones nuevas en `core` (`core/0016_variedades_acciones_de_auditoria`), con etiquetas y clasificadas como de negocio.
3. **Lectura y bloqueo.** `inventario/servicios/ciclos.py` y `variedades.py`: lectura, `bloquear_variedad`, `incompatibilidades_de_rangos`, `umbral_efectivo` y `variables_incompatibles`.
4. **Alta.** `semillas.py` y `resumen_de_alta` / `alta_variedad`.
5. **Modificar y reactivar.** `resumen_de_modificacion`, `modificar_variedad` y `reactivar_variedad`.
6. **Baja.** `informe_de_baja` y `baja_variedad`.
7. **Conexión con `maestros`.** `registrar_semillas_de_cultivo`, `registrar_uso_de_cultivo` y, en el paso 8, `registrar_variedades_de_cultivo`, los tres con guarda de idempotencia en `InventarioConfig.ready()`.
8. **Pantallas.** `inventario/forms.py` (`FormularioVariedad`), `views_variedades.py`, `urls_variedades.py` (una línea en `config/urls.py` y otra en `core/tests/urls_prueba_acceso.py`, que las pruebas de interfaz de `core` necesitan para resolver los enlaces), plantillas en `inventario/templates/inventario/variedades/` y `variedades.css`. `views_existencias.habilitar` acepta una semilla activa que llega con `?insumo=` (la lista general sigue sin semillas). En `variedades.py` se agregaron `gestion_de` y `acciones_de` (la misma regla de `puede_gestionar` y `acciones_permitidas`, para toda la tabla sin consultas por fila; las dos funciones de antes delegan en ellas y dan el mismo resultado).
9. **Cierre.**

**Pruebas (M1).**
- `python manage.py test inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 2879 pruebas, OK.
- `python manage.py test inventario maestros --keepdb --tag concurrencia`: 86 pruebas, OK.
- `python manage.py test inventario maestros core --keepdb --tag migracion`: 8 pruebas, OK (se incluye `core`: el comando de la tarea no lo traía y la migración `core/0016` también se prueba).
- `makemigrations --check --dry-run`: «No changes detected». `manage.py check`: sin problemas.
- Los archivos de INV-03 suman 353 pruebas (47 de pantallas).

**Decisiones de la tarea (para la revisión).**
1. Rutas bajo `/produccion/` en `inventario/urls_variedades.py` (`app_name = "variedades"`), con una línea en `config/urls.py`.
2. `crear_variedad` (fábrica de `maestros`) agrega valores válidos por defecto para las diez columnas; `test_cultivos_concurrencia.py` ahora usa `crear_variedad(cultivo, "Crespa")`.
3. Los textos de error son los del prototipo (`varCalc`) y del caso de uso, en voseo («Ingresá el mínimo.», «Ingresá un valor entre 0 y 100.»).
4. Un nombre de semilla repetido (choca con `insumo_nombre_unico`) da `semilla_repetida` en el campo `nombre`, en el alta, la modificación y el renombre del cultivo; también se traduce el `IntegrityError`.
5. Códigos de error nuevos: `variedad_en_uso_por_otros`, `variedad_inactiva`, `variedad_no_inactiva`, `cultivo_inactivo`, `cambio_simultaneo`, `etapas_con_lotes` (en `etapas`), `perfil_con_lotes_u_ordenes` y `etapa_no_permitida` (en `perfil_familia`, cuando el cambio de perfil deja una etapa sin permiso).
6. Contratos de datos: `Incompatibilidad(invernadero_id, variable, variedad_id)`, `InformeDeBaja`, `StockDeSemilla`, `ResumenDeAlta` y `ResumenDeModificacion`.
7. Auditoría: el alta lleva `datos.cultivo` (referencia), `datos.etapas` y `datos.nombre_semilla`; la modificación, `cambios` solo con lo que cambió; rangos y postcosecha como texto; afectados de la modificación: la variedad, más el ciclo y las etapas tocadas, más la semilla si se renombró.
8. Notificaciones: una por cuenta Agrónomo, con el título «Cambió la variedad {cultivo} {nombre anterior}»; solo avisan nombre, duraciones, etapas y rangos.
9. Baja: bloquea primero los invernaderos de la semilla, después cultivo, variedad e insumo; si al releer aparece otro invernadero, rechaza con `cambio_simultaneo` sin reintentar; no deshabilita existencias; reevalúa cada existencia activa llamando por módulo a `alertas_de_stock.reevaluar_alertas_del_insumo`.
10. Pantallas: sin validación en vivo (solo al revisar y al confirmar); HTMX solo redibuja las etapas del perfil (`hx-get` al cambiar el desplegable, `hx-swap="innerHTML show:none"`); respaldo completo sin JavaScript con el botón «Actualizar etapas» (dentro de `<noscript>`); la duración del ciclo y la cosecha estimada se ven en el resumen y, en una variedad guardada, como valores guardados (no en vivo como el prototipo); «Habilitar la semilla» abre la ventana de INV-02 con la semilla ya elegida.
11. **Reactivar es una página de confirmación** (`/produccion/variedades/<id>/reactivar/`: GET confirma, POST reactiva), no un botón directo como en el prototipo: la tabla de variedades la arma `inventario` para `maestros` sin recibir el pedido y no puede llevar un formulario con CSRF.
12. La advertencia de rangos («Revise antes de guardar») es una ventana dentro del formulario del resumen, con «Volver a revisar» y «Guardar igual».

**Pendientes y límites que quedan anotados** (propuestos para `docs/temas_abiertos.md` y `docs/disparadores.md`):
- La precondición f de PROD-BAJ-VAR (contratos) no se verifica hasta que `comercial` registre `contratos_abiertos`.
- `reactivar_variedad` no reevalúa las alertas de stock de las existencias que quedaron activas (la baja sí).
- `habilitar_insumo` (INV-02) no mira la variedad de una semilla: la ventana entre habilitar y dar de baja la variedad la cubre la baja con `cambio_simultaneo`.
- Una variedad cuyos invernaderos usuarios no tienen Agrónomo no la gestiona nadie hasta que el Gerente asigne uno.
- Tres pruebas existentes adaptadas: `maestros/tests/test_cultivos_concurrencia.py` y dos de `maestros/tests/test_extensiones_sectores.py` (`test_ext_semillas_sin_registrantes_son_cero` y `test_ext_uso_de_cultivo_sin_registrantes_no_hay_invernaderos`, que ahora aíslan el punto con `mock.patch.object`, como ya hacía la de variedades): con `inventario` instalado, esos puntos ya tienen registrante.
- `renombrar_semillas(actor, cultivo, nombre_anterior)`: `nombre_anterior` no se usa (el nombre de cada semilla se arma con el cultivo y la variedad).
- La prueba de espacios al borde documenta la frontera entre la base (no recorta) y el servicio (recorta antes de comparar).
- Cruce extra de concurrencia: alta de una variedad contra el renombre del cultivo.
- El comando de pruebas de migración de la tarea incluye ahora `core`.
- Sin verificar: HTMX en vivo y el aspecto de las pantallas en un navegador real (no hay pruebas de navegador, por regla).
