# INV-01 · Tipos de insumo y catálogo de insumos (y los modelos de todo `inventario`)

Estado: pendiente | App: inventario | Rama: feature/inv-01-catalogo-de-insumos | Ronda: Producción 1

Depende de: UI-01 (estilo y marco), NOT-01 (aviso de MOD-INS, postcondición b) y **CON-01** (`contabilidad.OrigenDocumento`, D-52: `MovimientoInsumo` hereda de ella). PRD-00 ya creó la app vacía. Si alguna no está
hecha, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Por qué esta tarea crea también los modelos de existencias, lotes y movimientos.** El catálogo pregunta por stock, lotes y
habilitaciones (la baja de un insumo, el cambio de unidad, el campo «controla vencimiento», «quién lo usa»). Para que INV-01 se pueda
probar sola, crea los cinco modelos y los puntos de extensión; INV-02 agrega el **comportamiento** (habilitar, ajustar, vencimientos)
sin tocar el esquema.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-ALT-TIN | Alta Tipo de Insumo | docs/casos_de_uso/inventario/tipos_de_insumo.md | — |
| CMP-MOD-TIN | Modificar Tipo de Insumo | docs/casos_de_uso/inventario/tipos_de_insumo.md | Las reservas (regla 4) salen de un punto de extensión que registra PRD-01 |
| CMP-BAJ-TIN | Baja Tipo de Insumo | docs/casos_de_uso/inventario/tipos_de_insumo.md | — |
| CMP-CNS-TIN | Consultar Tipo de Insumo | docs/casos_de_uso/inventario/tipos_de_insumo.md | Las cuatro categorías del sistema (el prototipo muestra tres: manda el CU) |
| CMP-ALT-INS | Alta Insumo | docs/casos_de_uso/inventario/insumos.md | El botón «Habilitar en un invernadero» (regla 7) lo agrega INV-02 |
| CMP-MOD-INS | Modificar Insumo | docs/casos_de_uso/inventario/insumos.md | Aviso a los Agrónomos de otros invernaderos por NOT-01; reservas por punto de extensión |
| CMP-BAJ-INS | Baja Insumo | docs/casos_de_uso/inventario/insumos.md | Orden de compra y pedidos en curso por punto de extensión (los registrará `compras`) |
| CMP-CNS-INS | Consultar Insumo | docs/casos_de_uso/inventario/insumos.md | «Habilitar» queda sin acción hasta INV-02; las semillas indican que vienen de su variedad |

## Leer

- Casos de uso: los dos extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno
- Modelo: docs/modelo/inventario.md — las cinco fichas y «Diferencias con el caso de uso»
- Decisiones: D-05, D-06, D-14, D-22, D-27, D-28, D-30, D-32, D-36, D-37, D-39, D-40, D-41, D-42, D-43, D-44, D-45, D-46, D-47
- API: docs/api/extensiones_de_inventario.md (implementalo tal cual), docs/api/alertas.md, docs/api/notificaciones.md, docs/api/stock.md
  (solo «Lectura»)
- Patrones: docs/patrones/stock.md (secciones 1, 4, 5, 6 y 7), docs/patrones/abm.md, docs/patrones/bloqueos.md,
  docs/patrones/auditoria.md, docs/patrones/datos_de_migracion.md (incluida «Singletons y catálogos fijos»),
  docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/ — `VIEWS.insumos`, `catalogoTab`, `tiposTab`, `MODALS['cat-form']`, `ACT['cat-baja']`,
  `MODALS['insumo-form']`, `insLocks`, `insErrs`, `MODALS['ins-baja']`, `ACT['ins-react']`, `UNIDADES`, `quienesIns` y `puedeIns`
  (solo guía visual; lo que difiera de los CU lo decide el CU, L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: maestros/extensiones.py (el `Impedimento` y el estilo de los puntos de extensión), maestros/alertas.py y
  maestros/servicios/alertas.py, maestros/servicios/invernaderos.py (`bloquear_invernadero_activo`, `acciones_permitidas`),
  maestros/servicios/cultivos.py (el ABM más parecido), core/notificaciones.py, core/menu.py, core/models.py (auditoría)

## Límites

- Crea modelos: `TipoInsumo`, `Insumo`, `InsumoInvernadero`, `LoteInsumo`, `MovimientoInsumo` (todos en `inventario`;
  `docs/modelo/inventario.md`; **`MovimientoInsumo` hereda de `contabilidad.OrigenDocumento`** con `TIPO_DE_ORIGEN = movimiento_de_insumo` y tiene la clave `origen` (nula, `PROTECT`) que reemplaza a `movimiento_origen`, D-52 puntos 2 y 4; la restricción de la base «`origen` nulo si y solo si el tipo es ajuste o salida por corrección» va en la migración inicial) → revisá docs/disparadores.md («Cuando exista InsumoInvernadero»)
- Migraciones: solo nuevas, en `inventario`: una de esquema (que depende de `contabilidad.0001_initial`) y una de datos (`cargar_categorias_del_sistema`). Con una de `core` si
  se agregan acciones de auditoría (choices)
- Permitido fuera de la app: `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`:
  `alta_tipo_insumo`, `modificacion_tipo_insumo`, `baja_tipo_insumo`, `reactivacion_tipo_insumo`, `alta_insumo`,
  `modificacion_insumo`, `baja_insumo`, `reactivacion_insumo`, `baja_insumo_invernadero`), su migración, `core/menu.py` (entrada
  «Inventario» del Agrónomo), y los textos de cierre de
  `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md`
- Dependencias nuevas: ninguna
- Fuera de alcance: habilitar, modificar y deshabilitar insumos en un invernadero, existencias, ajustes y vencimientos (INV-02);
  las variedades y su semilla (INV-03); el vínculo con pedidos y órdenes de compra (`compras`, fuera de la ronda); asientos

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, unidades y datos.** Los cinco modelos de `docs/modelo/inventario.md`, con todas sus restricciones de base (únicos por
   `lower(nombre)`, el parcial del faltante, los `CheckConstraint` de cantidades y de dominio de cada ficha), `inventario/unidades.py`
   (la lista fija de ocho unidades con sus decimales, `validar_cantidad` y `cuantizar`; nunca `float`) `inventario/categorias.py` (una constante por categoría del sistema,
   p. ej. `SEMILLAS = "semillas"`, y `es_semilla(insumo)`; las reglas van por `codigo`, nunca por nombre), `inventario/servicios/formato.py`
   (`texto_cantidad` y `texto_precio`, para la auditoría) y la migración de datos
   `cargar_categorias_del_sistema` con las **cuatro** categorías (`codigo` fijo; `cargar`/`descargar` idempotentes). Las fábricas de
   `docs/patrones/stock.md`, sección 7, con el mixin `ConDatosDeInventario`. Pruebas: `inventario/tests/test_modelos_inventario.py`
   (una por restricción de la base: viola y no viola), `test_unidades.py` (cada unidad y sus decimales, el redondeo, los valores
   límite) y `test_datos_de_inventario.py` (la migración sobre tablas vacías, idempotencia y que las categorías del sistema no
   se pueden renombrar ni dar de baja desde la base).
2. **Extensiones, tiempo y lectura básica.** `inventario/extensiones.py` con los tres registros de
   `docs/api/extensiones_de_inventario.md` y sus funciones de consulta (`reservado_de`, `ordenes_que_reservan`,
   `impedimentos_de_deshabilitacion`, todas con resultado neutro sin registrantes), `inventario/servicios/stock.py` con `hoy()` y `stock_actual_de`
   (lo demás de `stock.py` lo escribe INV-02), y el registro de los cuatro tipos de alerta de `docs/patrones/stock.md`, sección 4, en
   `InventarioConfig.ready()` (`maestros.alertas.registrar_tipo_de_alerta`; los usa INV-02, pero BAJ-INS ya resuelve
   «bajo el mínimo»). Pruebas: `test_extensiones_inventario.py` (con registrantes falsos: devuelve lo esperado, el neutro sin datos
   y sin consultas por fila) y `test_tipos_de_alerta_de_inventario.py` (registrados, mismo valor al registrar dos veces).
3. **Auditoría en `core`.** Las acciones de «Límites», con sus etiquetas y su clasificación en `ACCIONES_DE_NEGOCIO`, y los valores visibles
   de `consumo_directo` (patrón de auditoría, sección «Lo que hay que tocar en `core`»), con su migración de `choices`. Pruebas: que
   `test_d36_cada_accion_esta_clasificada_en_cuentas_o_en_negocio` siga pasando y que el Gerente vea cada acción nueva en «Auditoría».
4. **Servicios de tipo de insumo** en `inventario/servicios/tipos_de_insumo.py`: `alta_tipo_insumo`, `modificar_tipo_insumo`,
   `reactivar_tipo_insumo`, `baja_tipo_insumo`, `consultar_tipos_de_insumo`, `acciones_permitidas`. Cada CU es una función en
   `transaction.atomic()` con el orden de `docs/patrones/abm.md`: Agrónomo activo (`PermissionDenied` si no), validación de todo
   junto con un error por campo, bloqueo de la categoría (y, si cambia el consumo directo, de sus `InsumoInvernadero` en orden de
   id), relectura, reglas, sin cambios no se escribe ni audita (D-28), restricción de la base traducida a `ValidationError` y
   auditoría (D-36). Las categorías del sistema se rechazan con el código `categoria_del_sistema` aunque la vista no ofrezca la
   acción. Pruebas: `test_cmp_alt_tin.py`, `test_cmp_mod_tin.py`, `test_cmp_baj_tin.py`, `test_cmp_cns_tin.py` (una por regla y por
   postcondición; nombrar con el número de regla), incluida la concurrencia: una baja y un alta de insumo simultáneas sobre la
   misma categoría, y dos modificaciones del mismo nombre, con la etiqueta `concurrencia`.
5. **Servicios de insumo** en `inventario/servicios/insumos.py`: `alta_insumo`, `modificar_insumo`, `reactivar_insumo`,
   `baja_insumo`, `consultar_insumos`, `invernaderos_que_usan`, `puede_gestionar`, `acciones_permitidas`. `modificar_insumo` bloquea campo
   por campo (regla 3), avisa a los Agrónomos de los otros invernaderos con `notificar_a_varios` (excluye al actor) y devuelve, antes de confirmar,
   a quiénes avisará. `baja_insumo` junta **todos** los impedimentos por invernadero (stock distinto de cero —también el negativo—, reservas,
   tránsito y los de los registrantes de deshabilitación), cada uno con su texto y cómo resolverlo; si no hay, pasa el insumo y sus
   `InsumoInvernadero` a inactivos, resuelve «bajo el mínimo» de cada uno y audita un `baja_insumo` y un `baja_insumo_invernadero` por
   invernadero. Las semillas (categoría `semillas`) se rechazan en alta, modificación y baja. Pruebas: `test_cmp_alt_ins.py`,
   `test_cmp_mod_ins.py`, `test_cmp_baj_ins.py`, `test_cmp_cns_ins.py`, con concurrencia (baja del insumo contra un consumo o un ajuste
   simulado, y contra la baja del invernadero) con la etiqueta `concurrencia`.
6. **Pantallas.** Entrada «Inventario» en el menú del Agrónomo (ícono del prototipo; sumalo a `iconos.py` si falta), con la página del
   prototipo (`VIEWS.insumos`) y sus pestañas «Catálogo» y «Categorías» (la de «Existencias de insumos» la suma INV-02 como primera):
   tablas, filtros, modal de alta y modificación con campos bloqueados y su motivo, modal de baja (con la lista de impedimentos),
   avisos en los lugares del prototipo, acciones deshabilitadas con el nombre de quién usa el insumo (regla 3 de CNS-INS), todo con HTMX
   y respaldo sin JavaScript (D-24, D-29, D-47). Las vistas exigen Agrónomo (otros roles: 403; sin sesión: inicio de sesión). Las vistas
   de lectura no se auditan. Pruebas: `inventario/tests/test_inventario_catalogo_vistas.py` (permisos, errores por campo, la baja
   que informa, los campos bloqueados, la entrada del menú solo para el Agrónomo y no para el Gerente ni el Administrador).
7. **Cierre de documentación.** Cerrar lo que corresponda en `docs/disparadores.md` y marcar INV-01 en `docs/tareas/README.md` y en
   `docs/tareas/ronda_produccion_1.md`. Si algún texto de la documentación dice algo distinto de lo que implementaste, anotalo en
   `docs/temas_abiertos.md`: no lo corrijas en silencio.

Si el tiempo apremia, lo último que se recorta es la pantalla de modificación con todos los campos bloqueados mostrados con su
motivo (queda el error en el servicio y se anota); las reglas del servicio, los bloqueos y el todo o nada no se recortan.

## Hecho cuando

- Los ocho casos de uso están implementados con una prueba por regla y por postcondición y con sus pruebas de vista.
- Las cuatro categorías del sistema existen tras `migrate`, no se modifican ni se dan de baja, y las reglas las buscan por `codigo`.
- Ningún servicio usa `float`; toda cantidad se valida contra la unidad del insumo con `validar_cantidad`.
- Un insumo con stock distinto de cero (incluido el negativo) no se da de baja y el mensaje dice dónde y cómo resolverlo.
- Comando de pruebas:
  python manage.py test inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test inventario --keepdb --tag concurrencia
  python manage.py test inventario --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas: `python manage.py migrate`. Cuentas: Agrónomo (con un invernadero a cargo), otro Agrónomo (con otro invernadero),
Gerente, Capataz y Administrador.

1. `migrate` aplica esquema y datos de `inventario`. En «Categorías» están **cuatro** categorías del sistema (Semillas, Envases,
   Repuestos de hardware e Infraestructura), con el candado y sin acciones.
2. El Agrónomo ve «Inventario» en el menú; el Gerente, el Capataz y el Administrador no; la URL les da 403.
3. Crear la categoría «Limpieza» con consumo directo «Como gasto»; «limpieza » (minúscula, con espacio) da error de nombre duplicado;
   dejar el consumo directo sin elegir da error en su campo.
4. Modificarla a «Como costo de los lotes» y renombrarla; luego darla de baja (sin insumos): pasa a inactiva; reactivarla.
5. Crear el insumo «Detergente» en «Limpieza», unidad «L», sin vencimiento: aparece en el catálogo como activo y «ninguno» en habilitado
   en; la pantalla avisa que hay que habilitarlo (sin botón hasta INV-02). Con el nombre repetido en otras mayúsculas da error.
6. La categoría «Semillas» no se ofrece al crear un insumo. Con unidad «unidad» una cantidad con decimales se rechaza (prueba en INV-02);
   acá se verifica que las ocho unidades se ofrecen con el texto de sus decimales.
7. Dar de baja la categoría «Limpieza» teniendo «Detergente» activo: no se puede e informa cuántos insumos tiene. Pasarlo a otra
   categoría (modificar) y volver a probar.
8. Con otro Agrónomo que use un insumo (desde la consola, hasta que INV-02 permita habilitarlo), el primero no puede modificarlo ni darlo
   de baja: los botones aparecen deshabilitados con el nombre de quien lo usa. Si lo modifica quien lo usa, el otro Agrónomo recibe la
   notificación (campana).
9. Dar de baja un insumo con stock (cargado desde la consola, también uno con stock negativo): informa por invernadero qué lo impide.
10. En «Auditoría» (Gerente) figuran las altas, modificaciones y bajas con el antes y el después. Guardar sin cambios no deja registro.
11. Dos Agrónomos modifican a la vez el nombre de la misma categoría a valores distintos: gana el último y no hay error 500.
12. Sin JavaScript, los pasos 3 a 5 funcionan igual.
13. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
