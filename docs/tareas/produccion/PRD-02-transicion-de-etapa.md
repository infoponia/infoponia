# PRD-02 · Transición de etapa: planificar, concretar y cancelar (con el núcleo de la merma)

Estado: pendiente | App: produccion | Rama: feature/prd-02-transicion-de-etapa | Ronda: Producción 1

Depende de: PRD-01 (modelos, lectura, bloqueos, bandeja, `cancelar_orden` y `cancelar_orden_incluida`; si no está hecha y mergeada, frená), y por ella todas las de PRD-01.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es la tarea que agrega el **segundo tipo de orden** y, como Concretar Transición ejecuta Registrar Merma cuando se pierden plantas, escribe también el **núcleo de la merma** (D-50 punto 6): PRD-03 le agrega la pantalla y el CU completo.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-PNF-TRN | Planificar Transición | docs/casos_de_uso/produccion/transicion.md | — |
| PROD-CNC-TRN | Concretar Transición | docs/casos_de_uso/produccion/transicion.md | **Fuera de la ronda (D-45):** precondiciones c y d (ejercicio y cuentas) |
| PROD-REG-MRM (parte) | Registrar Merma, lo que aplica desde la transición | docs/casos_de_uso/produccion/transicion.md | **Fuera de la ronda (D-45):** asiento (e), movimiento de stock «salida por merma» (d), plantas comprometidas por cosechas (condición 1), partida en cámara |
| PROD-CNL-ORD | Cancelar Orden, ahora también transiciones | docs/casos_de_uso/produccion/cancelar_orden.md | Extensión 4a; el resto igual que en PRD-01 |

## Leer

- Casos de uso: el extracto de la tabla, completo, **incluida la sección «Cómo se aplica en la ronda»** de `transicion.md` y la de `cancelar_orden.md`
- Modelo: docs/modelo/produccion.md — `TransicionEtapa`, `Merma`, `AlertaDeMerma`, `OcupacionSector`, `Lote`, `Bitacora` y los cálculos de lote; docs/modelo/maestros.md — «Variedad, Ciclo y EtapaProductiva»
- Decisiones: D-05, D-07, D-24, D-28, D-29, D-30, D-32, D-36, D-37, D-40, D-42, D-43, D-44, D-45, D-47, D-49, **D-50**, **D-52**, **D-53**
- API: docs/api/produccion.md, docs/api/variedades.md (`etapas_de`, `duracion_del_ciclo`), docs/api/alertas.md, docs/api/notificaciones.md
- Patrones: docs/patrones/bloqueos.md (sección `produccion`), docs/patrones/costo_del_lote.md, docs/patrones/auditoria.md, docs/patrones/abm.md, docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/datos_maestros_y_produccion.html — `VIEWS.transicion`, `trCalc`, `VIEWS['c-trans']`, `ctCalc`, `propTrans`, `mermaInfo` (solo el aviso de merma de la transición), `MODALS.orden` (la rama de transición), `ACT['orden-cancelar']`. Solo guía visual: lo que difiera de los CU lo decide el CU (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: todo `produccion/` (hecho en PRD-01: modelos, servicios, `errores.py`, bandeja, `registrar_…` de `ready()`), maestros/alertas.py y maestros/servicios/alertas.py, core/notificaciones.py

## Límites

- Crea modelos: `TransicionEtapa(OrdenTrabajo)`, `Merma(Bitacora)` y `AlertaDeMerma` (fichas de `docs/modelo/produccion.md`) → revisá docs/disparadores.md («Cuando exista Lote, OrdenTrabajo o StockCosechado» y «Cuando exista un caso de uso que planifique…»)
- Migraciones: solo nuevas. En `produccion`: una de esquema (`0002_transicion_y_merma`) que depende de `0001_initial` (PRD-01): las tres tablas y sus restricciones. En `core`: una de `choices` (acciones nuevas). **Ninguna de datos**
- Permitido fuera de la app: `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`: `planificacion_transicion`, `concrecion_transicion`, `registro_merma`) y su migración; `maestros/alertas.py` **no se toca** (los tipos se registran desde `produccion`); los textos de cierre de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_produccion_1.md` y `docs/estado.md`
- Dependencias nuevas: ninguna
- Fuera de alcance: la pantalla y el CU completo de registrar merma, con mermas por sector, el movimiento de stock y el asiento (PRD-03); aplicación de insumos y otros eventos (PRD-03); sector fuera de servicio (PRD-04); cosechas y la condición 1 de plantas comprometidas (D-45); modificar una transición (se cancela y se planifica otra)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, migración y auditoría.** `TransicionEtapa` (con `capataz` por `ConCapataz`, D-53), `Merma` y `AlertaDeMerma` con sus restricciones; las tres acciones de auditoría con etiquetas y su migración de `choices`. Fábricas: `lote_con_ciclo` (lote activo en Crecimiento con sectores destino de Maduración), `orden_de_transicion`. Pruebas: `test_modelos_transicion.py` (restricciones: viola y no viola; la herencia; `cant_transferido` y `fecha_transicion` nulos si la orden no está concretada;
   la prueba de que **un lote con dos transiciones «a realizar»** lo impide el servicio, no la base).
2. **Lectura.** `lotes_trasladables(actor)`, `lotes.fecha_de_entrada_a_maduracion`, `fecha_maxima_de_cosecha`, `transiciones.fecha_minima_de_transicion`, `repartir_proporcional` y la parte de transición de `ordenes.py` (bandeja y lista; **`ordenes_del_capataz` suma `TransicionEtapa` y el registrante del traspaso suma su tabla**, D-53; prueba: el traspaso pasa también las transiciones «a realizar»). Pruebas: `test_transiciones_lectura.py` (lote en la última etapa no es trasladable; con otra transición «a realizar»; invernadero inactivo; etapa destino por `puesto_global`; la regla 5 de 8.21 para etapas intermedias;
   fecha mínima con y sin bitácora), `test_repartir_proporcional.py` (la propiedad: la suma da exactamente la cantidad; resto mayor; empates por agujeros planificados y por orden; cantidades en cero) y la de **sin consultas por fila**.
3. **Núcleo de la merma** (`produccion/servicios/mermas.py`, `aplicar_merma(lote, cantidad, causa, descripcion, fecha, responsable, *, por_sector=None, sector_ids=(), ordenes_excluidas=())`, función interna que corre en la transacción del llamador y devuelve `ResultadoMerma(merma, costo, alertas)`; **con la firma completa**, porque PRD-03 (Registrar Merma, con `por_sector`) y PRD-04 (con `sector_ids` y `ordenes_excluidas`) la llaman sin reescribirla, D-51 punto 5. Desde la transición se llama con `por_sector=None` y `sector_ids=()`: no toca ocupaciones ni sectores): crea `Bitacora` tipo `merma` (con `descripcion_evento` legible, por ejemplo «Merma de 12 plantas por plaga», y `sectores` = `sector_ids`; en la etapa de origen, con la fecha efectiva y la hora actual) y su `Merma`;
   baja `cantidad_actual` y `costo_acumulado` con `costo_de_la_merma`; calcula la **merma acumulada** (sin las de «descarte por selección») y, si cruza por primera vez `porc_merma_maxima`, crea la alerta `produccion_merma_umbral` (`crear_alerta_de_evento`) enlazada por `AlertaDeMerma`; **evalúa la condición 2 de plantas comprometidas** (sin contar la orden que se concreta) y crea la `produccion_plantas_comprometidas`
   si corresponde, **sin contar** las órdenes de `ordenes_excluidas` (desde la transición no puede dispararse porque la orden que se concreta se excluye; PRD-03 y PRD-04 sí la disparan). Si `por_sector` viene (PRD-03), baja `cant_agujeros_ocupados` de cada ocupación afectada y deja el lote `finalizado` con costo 0 si llega a cero. Registra en `ready()` los dos tipos de alerta de `docs/api/produccion.md`. Pruebas: `test_mermas_nucleo.py` (una por regla y por postcondición a, b, d (sin el movimiento: no existe), k, l, m, n; el lote nunca queda con cantidad negativa; causa obligatoria; «descarte por selección» no suma a la merma acumulada;
   el umbral se cruza una sola vez por lote; con el porcentaje en 0; el costo baja como en el patrón; la condición 2 **llamando a la función** con una transición ajena «a realizar»; los registrantes con sus tres pruebas mínimas).
4. **Planificar transición** (PROD-PNF-TRN): `DatosDeTransicion`, `datos_de_planificacion`, `resumen_de_planificacion` y `planificar_transicion(actor, datos)`. Bloqueos: cuentas → invernadero → variedad → sectores (destino, ordenados por id) → lote → filas propias; verificación del actor después de bloquear; repetición de todas las verificaciones bajo bloqueo (extensión 13a del CU: el lote cambió; cantidad actual; transición «a realizar»).
   Sin reservas. Notificación al Capataz dentro de la transacción y un registro `planificacion_transicion`. Pruebas: `test_prod_pnf_trn.py` (una por regla y por postcondición a a g: lote ya con transición; sin Capataz; sin sectores elegibles o con capacidad libre menor que la cantidad; sector fuera de servicio no se ofrece; perfil familiar; fecha pasada; fecha distinta de la estimada informa los días sin bloquear;
   fecha estimada vencida propone hoy; distribución incompleta, mayor que la capacidad y mayor que lo que resta; quitar y cambiar un sector; destino Maduración con su fecha máxima; **un error no deja nada creado**) y `test_transiciones_concurrencia.py` (etiqueta `concurrencia`: dos planificaciones sobre el mismo lote, una gana; dos sobre el último agujero; planificar contra la baja del sector).
5. **Concretar transición** (PROD-CNC-TRN): `datos_de_concrecion`, `resumen_de_concrecion` y `concretar_transicion(actor, orden_id, datos)`. Orden de efectos dentro de la transacción: verificar → merma (con la etapa de origen y la fecha efectiva) → ocupaciones de destino → ocupaciones de origen en cero → etapa y cantidad del lote → orden → bitácora de transición (tipo `transicion`, `sectores` = los destino con ≥ 1 planta, `descripcion_evento` legible, por ejemplo «Transición del lote L-3 a Maduración: 180 plantas») → notificación → **un** registro `concrecion_transicion` con todo como afectado.
   Fecha mínima y efectiva; reparto proporcional al cambiar la cantidad del lote (13c, con `cambio_simultaneo` y la nueva propuesta); 4a (lote en cero), 10a (causa obligatoria), 10b, 10c, 11a (advertencia de Maduración vencida) y 13a/13b. Sin asientos ni movimiento de stock (D-45). Pruebas: `test_prod_cnc_trn.py` (una por regla y por postcondición a a m, **menos las contables**: total completo sin merma; con merma y causa; sin causa; cero ubicado; más que la cantidad del lote;
   fecha efectiva anterior a la creación y a la programada, en la fecha mínima y fuera de ella; sectores con 0 conservan la ocupación sin lote; el origen queda en cero y conserva el lote; el lote cambia de etapa y de cantidad; la bitácora; la notificación avisa si la efectiva es anterior a la creación;
   la merma acumulada que cruza el umbral crea la alerta; **la transición no puede dejar el lote en cero**) y en `test_transiciones_concurrencia.py` (concretar dos veces; concretar contra cancelar; concretar contra una merma que cambia la cantidad, 13c; concretar contra la baja de un sector destino).
6. **Cancelar transición** (PROD-CNL-ORD, extensión 4a): `cancelar_orden` y `cancelar_orden_incluida` ya existen (PRD-01); acá se completan para `TransicionEtapa` (sin reservas; el lote queda sin transición «a realizar»). Pruebas: ampliar `test_prod_cnl_ord.py` (transición con su lote, que se puede planificar otra después; el lote conserva etapa y fecha de entrada; las ocupaciones se conservan sin lote)
   y `test_cancelar_orden_incluida.py` con una transición.
7. **Pantallas** (HTMX con respaldo sin JavaScript, D-24, D-29, D-47): «Nueva transición» con sus pasos (lote trasladable → fecha → distribución por sector destino → resumen), «Concretar transición» en pasos para celular (fecha efectiva, cantidad por sector con la propuesta proporcional, causa de la merma cuando falten plantas, resumen), la rama de transición de la ventana de detalle de la orden, y la inclusión de las transiciones en la lista, la bandeja y la cancelación.
   El resumen del Capataz muestra la merma con su causa. Pruebas: `test_transicion_vistas.py` (permisos por rol y 404 del Gerente donde corresponde; errores por campo; que el HTML escapa; que sin lotes trasladables el formulario está deshabilitado con su motivo; que no hay consultas por fila; la causa aparece solo cuando faltan plantas; sin JavaScript funciona).
8. **Cierre de documentación.** Cerrar lo que corresponda en `docs/disparadores.md`; marcar PRD-02 en `docs/tareas/README.md`, `docs/tareas/ronda_produccion_1.md` y `docs/estado.md`. Anotá en `docs/temas_abiertos.md` lo que implementaste distinto de lo escrito (no lo corrijas en silencio) y que la condición 2 de plantas comprometidas queda probada solo por función hasta PRD-03.

Si el tiempo apremia, lo último que se recorta es: la rama de transición de la ventana de detalle de la orden (queda en la lista). Las reglas de los servicios, el núcleo de la merma, los bloqueos, las notificaciones y el todo o nada **no se recortan**.

## Hecho cuando

- PROD-PNF-TRN y PROD-CNC-TRN están implementados con una prueba por regla y por postcondición (menos las contables), con sus pruebas de vista y de concurrencia; la parte de PROD-REG-MRM que aplica, con las suyas.
- Planificar una transición crea la orden y sus ocupaciones y compromete agujeros en una sola transacción; concretarla pasa el lote a la etapa destino, mueve sus ocupaciones, registra la bitácora y, si faltaban plantas, la merma con su costo y sus alertas, con **un** registro de auditoría `concrecion_transicion`.
- Un lote nunca queda con más plantas ubicadas que su cantidad actual ni con dos transiciones «a realizar»; el costo acumulado cumple el patrón.
- Cancelar una transición libera los agujeros comprometidos y deja al lote sin transición «a realizar».
- Comando de pruebas:
  python manage.py test produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test produccion --keepdb --tag concurrencia
  python manage.py test produccion --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate` (en `produccion` y `core`). Hace falta lo de PRD-01 más un lote activo en Germinación (concretá una siembra), sectores de Crecimiento con lugar (o los de la etapa que siga en el ciclo), un Agrónomo a cargo y el Capataz del invernadero.

1. `migrate` pasa sin errores.
2. «Nueva transición»: se ofrecen solo los lotes trasladables; la etapa destino la fija el sistema; la fecha propuesta es el fin estimado de la etapa actual (o hoy si ya pasó, con los días de atraso). Con otra fecha, se informa la diferencia sin bloquear.
3. La distribución por sector no deja pasar más que la capacidad libre; con sectores de otro perfil familiar o fuera de servicio, no se ofrecen. Confirmar crea la orden; el Capataz recibe la notificación; «Auditoría» tiene **un** registro `planificacion_transicion`. El lote ya no se puede elegir para otra transición.
4. Como Capataz: «Concretar transición» propone la fecha de hoy y las cantidades planificadas. Poner una fecha anterior a la fecha mínima da el error con su explicación; una anterior a la creación de la orden se acepta y la notificación lo avisa.
5. Ubicar menos plantas que las del lote: pide la causa (obligatoria) y el resumen muestra las plantas perdidas. Con 0, error. Confirmar: el lote pasa a la etapa nueva con la cantidad ubicada, el origen queda libre, y el Agrónomo recibe la notificación. «Auditoría» tiene **un** registro `concrecion_transicion`.
6. En «Lotes activos» de la ficha, el lote tiene la etapa nueva y el costo por planta **igual** que antes de la merma (cambió el costo total, no el unitario). Si la merma superó el 15 % de la cantidad inicial, el Agrónomo y el Gerente tienen la alerta de umbral (una sola vez); con la causa «descarte por selección» no suma.
7. Cancelar una transición «a realizar» (como Agrónomo): pide el motivo, libera los agujeros y deja al lote disponible para planificar otra.
8. Dos Agrónomos planifican a la vez la misma transición: uno gana; el otro ve el error, sin 500. Concretar y cancelar a la vez: una sola gana y la otra ve el estado actual.
9. Sin JavaScript, los pasos 2, 3, 4, 5 y 7 funcionan igual.
10. Después del merge: verificar en el log de Render que se aplicó la migración nueva.

## Cierre (la completa Claude Code al cerrar)
