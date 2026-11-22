# COM-05a1 · Entregas: modelo, planificación automática (paso diario 50) y cancelación incluida

Estado: pendiente | App: comercial | Rama: feature/com-05a1-planificacion-de-entregas | Ronda: Comercial 1

Depende de: **COM-04c** (y, con ella, COM-04a y COM-04b: cosecha, cámara, faltantes, `cancelar_cosecha_incluida`, el núcleo físico y los
puntos 3 y 4 de `produccion/extensiones.py`) y, con ellas, COM-01 a COM-03b, toda «Producción 1» (PRD-01 ya deja el tipo `entrega` y todo lo
de las órdenes de otros tipos: D-67, punto 1), **MAE-05** (`TransportistaInvernadero` y sus puntos), **MAE-02d** (el enlace de las alertas),
**USR-10** (`core.correo.enviar_correo`) y **DIA-01** (`registrar_paso_diario`). Si COM-04c no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera mitad de COM-05a (D-66 punto 1; D-67 punto 2): las **entregas** nacen solas. Cuando todo el producto de una
compra-venta o de un período de suministro queda listo, InfoPonia arma una entrega por invernadero de origen, le busca un transportista que
pueda llevarla (capacidad, entregas y localidades del día) y avisa al transportista, al Vendedor y al cliente. Lo que queda sin transportista
se vuelve a buscar cada día (**paso diario 50**), con un único recordatorio. Deja la **cancelación de una entrega** que usan los casos de
uso de cámara (y después COM-CNL-CVT y COM-RSV-SUM), la lista «Entregas» de Comercial y lo que protege la integridad de las entregas en las
tareas anteriores (la logística y la baja del transportista, los vehículos, el cierre de una rescisión). **No** trae el envasado ni las
pantallas que muestran entregas fuera de la lista (COM-05a2), ni COM-ASG-TRP y COM-CNL-CVT (COM-05b). **No toca `produccion`**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-PNF-ENT | Planificar Entrega (con la ejecución diaria, paso 50, y la postcondición n de PCU 8) | docs/casos_de_uso/comercial/entregas.md | 9-11a: las notificaciones van dentro de la transacción (D-42); el correo, con reintento en el paso 50 (D-66, punto 12). Postcondición h (aviso de envasado al Agrónomo): COM-05a2. COM-ASG-TRP: COM-05b |
| PROD-CNL-ORD | Cancelar Orden: la «Cancelación de una entrega», solo incluida (sin pantalla) | docs/casos_de_uso/produccion/cancelar_orden.md (sección «Comercial 1»: entregas y envasado) | La entrega en curso se cancela igual (situación 11); COM-CNL-CVT y COM-RSV-SUM la usan después |
| (consulta) | Lista de entregas de Comercial (el paso 2 de COM-ASG-TRP, sin asignar) | docs/casos_de_uso/comercial/entregas.md («Pantallas») | «Asignar» y «Cambiar transportista»: COM-05b. «Concretar retiro»: COM-06 |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/entregas.md **completo, salvo** lo de COM-ASG-TRP (sección de COM-05b) y, de «Pantallas», las
  filas del panel, las fichas de contrato y los vehículos (COM-05a2); de cancelar_orden.md, el texto del caso de uso («Cancelación de una
  entrega» y las situaciones 10 a 12) y la sección «Comercial 1: entregas y envasado». De los extractos de las tareas anteriores, **solo
  las partes que esta tarea completa** (las nombra la tabla «Lo que completa a otras tareas» de `entregas.md`, menos las filas de COM-02 y
  COM-03 CNS, que son de COM-05a2):
  - `docs/casos_de_uso/comercial/compra_venta.md`: «Cómo se aplica», postcondición g de COM-REG-CVT;
  - `docs/casos_de_uso/comercial/suministro.md`: «Cómo se aplica», postcondición f de COM-PCT-SUM y el cierre (paso diario 35) de COM-RSC-SUM;
  - `docs/casos_de_uso/produccion/pre_reserva.md`: «Lo sigue el paso 50»;
  - `docs/casos_de_uso/produccion/cosecha.md`: «PROD-CNC-CSC · Concretar Cosecha» de «Cómo se aplica», el punto 9 (postcondición n);
  - `docs/casos_de_uso/produccion/camara.md`: «Cómo se aplica» (candidatos de PROD-ASG-CAM, paso 9; PROD-VNC-CAM, postcondición d y 3a);
  - `docs/casos_de_uso/produccion/merma.md`: «Cómo se aplica en la ronda «Comercial 1»: la partida en cámara», la extensión 10c;
  - `docs/casos_de_uso/comercial/faltante.md`: «Paso 7 y 7a (m)»;
  - `docs/casos_de_uso/produccion/cancelar_orden.md`: la sección «Comercial 1»: cosechas, punto 6 (postcondición i);
  - `docs/casos_de_uso/comercial/vehiculos.md`: lo marcado «Se completa en COM-05» que **no** es pantalla (reglas 2 y 3 de MOD, precondición
    c y regla 1 de BAJ).
- Modelo: docs/modelo/comercial.md (**Entrega**, **DetalleEntrega**, **AlertaComercial** con `entrega`; ReservaStock y DetalleReserva;
  DetalleVenta; DetalleSuministro, «Período» y «Precio de un período»; Vehiculo; «Pendientes de MD»; «Diferencias», fila 11),
  docs/modelo/produccion.md (OrdenTrabajo y «Tipos que ven las pantallas de `produccion`»), docs/modelo/maestros.md (ConfiguracionOperativa:
  `cant_maxima_entregas_diarias`, `cant_max_ciudades_distintas_diarias`; Variedad: `peso_promedio_planta`, en gramos;
  `TransportistaInvernadero`).
- Decisiones: **D-66** (la de esta tarea, salvo el punto 8, que es de COM-05a2), D-62 (con sus tres enmiendas), D-63, D-64, D-65, D-59, D-61,
  D-55, D-56, D-14, D-25, D-27, D-28, D-29, D-36, D-37, D-40, D-41, D-42, D-44, D-50, D-52, D-53, D-54, D-57; **D-67, puntos 1 y 2**.
- Patrones: docs/patrones/bloqueos.md (secciones `produccion` y `comercial`, con «Entregas y envasado»), docs/patrones/stock_maduro.md
  (secciones 1, 7 y 8: cantidad cubierta, períodos, recorte), docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md
  («Migraciones»).
- API: docs/api/produccion.md, **sección 9, «Lo que deja hecho PRD-01»**, y la sección 1 (`cancelar_orden_incluida`); docs/api/alertas.md
  (secciones 1, 2, 4 y 8); docs/api/notificaciones.md; docs/api/extensiones_de_maestros.md («Transportistas»); `core/procesos.py` (su
  encabezado).
- Disparadores: docs/disparadores.md — «Cuando exista Entrega» (puntos 1 a 7), «Completan el ABM de vehículo», «Cuando exista un caso de uso
  que planifique, haga pedidos, asigne stock o reintente entregas».
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `tabEntregas`, `logistica`. Vale la última definición; lo que difiere
  está en «Lo que difiere del prototipo» de `entregas.md`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-04c): modelos, `servicios/` (`stock_maduro.py`, `compra_ventas.py`, `suministros.py`,
    `pre_reserva.py`, `calendario.py`, `cosechas.py`, `camara.py`, `merma_camara.py`, `faltantes.py`, `vehiculos.py`, `clientes.py`,
    `comprobantes.py`, `enlaces.py`), vistas, plantillas, `apps.py`, fábricas y `verificar_invariantes_de_reservas`;
  - `produccion/`: `models.py` (`OrdenTrabajo`, `ReservaInsumo`), `servicios/ordenes.py` (`cancelar_orden_incluida`, `siguiente_numero`,
    `TIPOS_DE_PRODUCCION`), para **usarlos**: no se cambian;
  - `maestros/extensiones.py` (`Enlace`, `registrar_enlace_de_alerta`, `registrar_logistica_de_transportista`,
    `registrar_impedimento_de_transportista`), `maestros/models.py` (`TransportistaInvernadero`, `ConfiguracionOperativa`, `Direccion`),
    `maestros/servicios/alertas.py`, `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`);
  - `core/extensiones.py` (`registrar_asignaciones_de_cuenta`, `registrar_efecto_de_baja_de_cuenta`), `core/procesos.py`,
    `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos en `comercial`: `Entrega` (hija de `produccion.OrdenTrabajo`; el valor `entrega` del tipo ya existe desde PRD-01) y
  `DetalleEntrega` con su M2M a `ReservaStock`; `AlertaComercial.entrega` con la restricción «exactamente un origen» reescrita (D-63).
  → revisá docs/disparadores.md: cierra los de la sección 9 del plan para COM-05a1 (paso 9).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_entregas.py`: `Entrega`, `DetalleEntrega`, la M2M, `AlertaComercial.entrega` y su restricción (depende de la
    migración inicial de `produccion`);
  - `core/migrations/00NN_comercial_entregas.py`: solo `choices` (acciones `planificacion_entrega`, `modificacion_entrega`,
    `asignacion_transportista`; `cancelacion_orden` ya existe).
  **Ninguna en `produccion`.**
- Permitido fuera de `comercial`:
  - **`produccion`: nada.** Lo que una entrega necesita de PRD-01 (listas y bandeja filtradas por tipo, `cancelar_orden` que la rechaza,
    `cancelar_orden_incluida` que la acepta, los registrantes de reservas de insumo y el impedimento de baja) **ya lo dejó hecho y probado
    PRD-01** (D-67, punto 1). Verificalo leyendo el código; si falta algo, frená y avisá (es un error de PRD-01);
  - `core`: en `core/models.py`, las tres acciones, `ETIQUETAS`, `VALORES_VISIBLES` (`modalidad_entrega`, `estado_confirmacion_cliente`,
    `estado_aviso_cliente`) y `ACCIONES_DE_NEGOCIO`; en `core/procesos.py`, solo el comentario (fila 50);
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md`, `docs/temas_abiertos.md`
    y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: **COM-05a2** (PROD-PNF-ENV y la restricción de `ReservaInsumo`; el aviso de envasado al Agrónomo, postcondición h; el panel
  de control; las secciones de entregas de las fichas de compra-venta y de suministro; la columna y la carga de los vehículos en sus
  pantallas); COM-ASG-TRP y COM-CNL-CVT (COM-05b); rutas, concreción, intento fallido y confirmación (COM-06: `transportista_en_ruta`,
  PROD-VNC-CAM 3b, el exceso de envases); montos, vencimiento y pago de una entrega (COM-06 y COM-08); el cron (D-56); reintentos automáticos
  de notificaciones (no hay cola; el del correo es el paso 50); los temas abiertos del caso de uso.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (D-66 puntos 2 y 3). `Entrega`, `DetalleEntrega` y `AlertaComercial.entrega` con **todas** sus restricciones;
   las acciones de `core`. Fábricas en `comercial/tests/fabricas.py`: `entrega(...)` (con sus líneas y sus reservas «lista para entrega»),
   `transportista_con_vehiculo(invernadero, capacidad, ...)`; y `verificar_invariantes_de_entregas()`.
   Los datos copiados de `Entrega` (`contrato`, `modalidad_entrega`, `direccion_destino`) los escribe **una sola función**, al crearla, y
   el servicio rechaza `detalle_fuera_de_alcance` (D-66, punto 3, refuerzos).
   Pruebas: `comercial/tests/test_modelos_entregas.py` (una por restricción: la viola y no la viola; un detalle de otro contrato, otra
   modalidad u otra dirección rechazado, también al agrupar; `verificar_invariantes_de_entregas()` después de cada prueba que escribe); una prueba de punta a punta de que una
   `Entrega` **real** no aparece en la lista de órdenes, en las cancelables ni en la bandeja de `produccion`, y que `cancelar_orden` la
   rechaza (confirma lo de PRD-01; no lo reprograma). Corré **toda** la suite de `produccion`: tiene que dar lo mismo que antes.
2. **Cálculos de una entrega** (`comercial/servicios/entregas.py`; `entregas.md`, «Candidatos…» y «Agrupamiento»; `docs/modelo/comercial.md`,
   «Lo que se calcula»): `cantidades_planificadas`, `peso_de_entregas`, `en_curso`, `atrasada`; `candidatos_para` (con su motivo),
   `seleccionar` (pura), `motivo_de_alerta`, `entrega_para_agrupar`.
   Pruebas: `comercial/tests/test_entregas_calculos.py`: de tabla para `seleccionar` y `motivo_de_alerta`; el peso con redondeo; cada motivo
   de `candidatos_para`, una prueba por motivo y en su orden; el día que cuenta concretadas y no canceladas; cada condición del agrupamiento,
   una por prueba (la de «sin envasado», con una `ReservaInsumo` activa de fábrica); sin consultas por fila.
3. **COM-PNF-ENT inmediato** (`entregas.md`, «Cuándo corre», «“Lista para entrega”», «El registro de una entrega», «Avisos y textos»,
   «Alerta…», «Auditoría»): `programar_planificacion_de_venta`, `programar_planificacion_de_periodo`, `planificar_venta`,
   `planificar_periodo`; el tipo de alerta y su enlace (`registrar_enlace_de_alerta`, a la lista de entregas) en `ComercialConfig.ready()`; el
   correo al cliente. **Sin** el aviso de envasado al Agrónomo (postcondición h: su texto nombra una pantalla que llega con COM-05a2; D-25).
   Pruebas: `comercial/tests/test_com_pnf_ent.py`, `ComPnfEntServicioTests` (la lista de «Pruebas» de `entregas.md`, menos «aviso de
   envasado» y la postcondición h).
4. **Los disparadores y lo de cámara en las tareas anteriores** (`entregas.md`, la tabla de «Cuándo corre» y «Lo que completa a otras tareas»,
   filas de COM-04; `cancelar_orden.md`, sección de entregas): las llamadas a `programar_planificacion_*` en `registrar_compra_venta`,
   `pactar_suministro`, la pre-reserva, `concretar_cosecha`, `asignar_camara`, la decisión del faltante, la cancelación de una cosecha y los
   recortes de cámara; la condición «sin línea en una entrega no cancelada» de los candidatos de PROD-ASG-CAM; `quitar_lineas_liberadas` en
   PROD-VNC-CAM 3a y la merma en cámara 10c; `cancelar_entrega_incluida` (completa: también el aviso al Agrónomo si la entrega tenía envases
   reservados, que se prueba con una `ReservaInsumo` de fábrica).
   Pruebas: `comercial/tests/test_prod_cnl_ord_entregas.py` y **métodos nuevos** en los archivos de pruebas de cada caso de uso tocado
   (`test_com_reg_cvt.py`, `test_com_pct_sum.py`, `test_prod_prr_sum.py`, `test_prod_cnc_csc.py`, `test_prod_asg_cam.py`, `test_prod_vnc_cam.py`,
   `test_prod_reg_mrm_camara.py`, `test_com_dcd_flt.py`, `test_prod_cnl_ord_cosechas.py`): que programan la planificación (con
   `captureOnCommitCallbacks`), que el candidato con entrega ya no lo es, que la entrega vacía se cancela y la que conserva líneas no. Las pruebas
   existentes no cambian; si una esperaba «sin entrega», anotala en el PR.
5. **El paso diario 50** (`entregas.md`, «Ejecución diaria: el paso 50»): `planificar_entregas(hoy)` y su registro.
   Pruebas: `ComPnfEntDiariaTests` en `test_com_pnf_ent.py`.
6. **Lo que protege a las entregas en MAE-05, en la baja de cuentas, en los vehículos y en la rescisión** (`entregas.md`, «Lo que completa a
   otras tareas»): el registrante de logística (completado: `entregas_a_realizar` y `url_entregas`), `transportista_con_entregas`,
   `registrar_asignaciones_de_cuenta` y `registrar_efecto_de_baja_de_cuenta` del Transportista, `entregas_a_realizar_del_transportista` y
   `carga_maxima_asignada` de `vehiculos.py` con las reglas de COM-MOD-VEH y COM-BAJ-VEH que las usan (y el bloqueo de las cuentas del
   transportista), la condición del paso 35. La columna y la tarjeta de los vehículos en sus pantallas son de COM-05a2.
   Pruebas: las de logística, en `comercial/tests/test_logistica.py` (donde COM-01 dejó las del registrante; métodos nuevos); las demás, en
   `comercial/tests/test_extensiones_entregas.py` (las tres mínimas de cada registrante: con datos, neutro sin datos, sin consultas por
   fila; la baja de un Transportista con entregas, que quedan sin transportista con su alerta); en `test_com_mod_veh.py` y `test_com_baj_veh.py`,
   las pruebas que usaban `mock.patch` sobre las dos funciones pasan a datos reales (anotalo en el PR); en `test_com_rsc_sum.py`, el cierre que
   espera una entrega atrasada.
7. **Concurrencia de las entregas**: `test_entregas_concurrencia.py` (la de `entregas.md`, salvo la de la cancelación de la venta, que es de
   COM-05b, y la del envasado, de COM-05a2).
8. **Vistas y plantillas**: la pestaña «Entregas» de Comercial (lista con filtros, orden, `?entrega=` y `?transportista=`, texto explicativo,
   solo «Ver contrato»). Vistas que solo orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript.
   Pruebas: `test_entregas_vistas.py` (permisos: Gerente todas, Vendedor solo las suyas, Agrónomo y Capataz 403; filtros, orden, los dos
   parámetros; la columna de Logística).
9. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-05a1 (la fila de la sección 9 del
   plan) y dejar lo que nace (para COM-05a2, COM-05b y COM-06); la fila de la tarea en `docs/tareas/README.md` y en el plan; lo distinto de lo
   escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el filtro por invernadero de la lista (queda en `docs/temas_abiertos.md`). No se recortan
las restricciones de la base, los bloqueos, la relectura de 8b, el paso 50, la cancelación incluida ni las pruebas de concurrencia.

## Hecho cuando

- Una compra-venta o un período de suministro con todo su producto listo tiene, sin que nadie haga nada, una entrega por invernadero de
  origen, con un transportista que puede llevarla o, si no hay ninguno, con la alerta al Gerente; el transportista, el Vendedor y el cliente
  fueron avisados.
- `python manage.py proceso_diario` planifica lo que haya quedado listo sin entrega, busca transportista para las entregas que no lo tienen
  (con un único recordatorio la víspera), avisa una vez por cada entrega atrasada con transportista y reintenta los correos que no salieron.
- Cuando un vencimiento o una merma en cámara deja vacía una entrega «a realizar», la entrega se cancela y se avisa.
- La ficha del invernadero («Logística»), la baja de un transportista, las reglas de los vehículos y el cierre de una rescisión tienen en
  cuenta las entregas.
- Todas las pruebas de `produccion`, `maestros`, `core`, `inventario` y de las tareas anteriores de `comercial` siguen pasando (las que
  cambian, anotadas).
- Comando de pruebas:
  python manage.py test comercial produccion maestros inventario core contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial produccion --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de COM-04c (un invernadero «Sur» con Agrónomo, Capataz
y Vendedor y un lote de «Lechuga Crespa» en Maduración); en «Configuración», máximo de entregas diarias 2 y de localidades 2; dos
transportistas de «Sur» (Juan, con una camioneta de 50 kg; Ana, con un furgón de 400 kg); un cliente con correo y dirección en Paraná.

1. Con el Vendedor, una compra-venta con envío de 100 plantas para dentro de 3 días. Con el Capataz, concretá su cosecha (COM-04a): en
   «Comercial › Entregas» aparece `OT-…` con el peso calculado (100 × el peso por planta / 1.000) y el transportista que tenga más capacidad
   libre (con 0 entregas los dos, gana el de más capacidad libre: Ana). Ana tiene la notificación y el cliente, el correo.
2. Una segunda venta para el mismo día y destino en otra localidad, y una tercera en una tercera localidad: con el máximo de 2 localidades, la
   tercera queda **sin transportista** (si nadie más cumple). En la campana del Gerente, «Entrega sin transportista» con el motivo; abrila:
   lleva a la lista, a esa entrega. El Vendedor tiene la notificación.
3. Subí el máximo de localidades a 3 y corré `python manage.py proceso_diario --fecha <mañana> --solo planificar_entregas` (o sin `--solo`,
   todos los pasos): la entrega recibe transportista, la alerta queda resuelta, el transportista y el Vendedor tienen el aviso. Corrélo de
   nuevo: nada nuevo.
4. Con una entrega sin transportista para pasado mañana: `proceso_diario --fecha <mañana>` envía «Mañana sale … sin transportista» al Gerente
   y al Vendedor; repetilo: no sale otro.
5. En la ficha del invernadero › «Logística»: la columna «Entregas a realizar» de cada transportista. Como Gerente, intentá quitar a Ana: lo
   impide con sus entregas y «Ver sus entregas» lleva a la lista filtrada.
6. Dá de baja la cuenta de Juan con una entrega a realizar: la ventana lo informa; después, su entrega queda sin transportista con la alerta.
7. Vencé en cámara (`proceso_diario --fecha <fecha límite + 1>`) una partida reservada para una entrega «a realizar» que sale toda de esa
   partida: la entrega queda «Cancelada» y el transportista tiene el aviso.
8. Sin JavaScript: la lista de entregas y sus filtros funcionan con «Filtrar».
9. Después del merge: en Render, desde la «Shell», `python manage.py proceso_diario --listar` (aparece el 50) y revisar en el log que se
   aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
