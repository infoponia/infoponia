# COM-04a · Cosechas: núcleo en produccion; planificar, modificar, concretar y cancelar

Estado: pendiente | App: comercial y produccion (núcleo físico, D-64) | Rama: feature/com-04a-cosechas | Ronda: Comercial 1

Depende de: **COM-03b** (y, con ella, COM-03a, COM-02 y toda «Producción 1»: PRD-01 a PRD-04, con `aplicar_merma`, `cancelar_orden_incluida`,
`registrar_pestana_de_invernadero`, la bandeja y la lista de órdenes, la pantalla de merma y el Inicio del Agrónomo). Si COM-03b no está
mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera de las tres partes de COM-04 (D-67, punto 2): **todo lo que COM-04 escribe en `produccion`** (el núcleo físico
de la cosecha y de la cámara, `docs/api/produccion.md`, sección 8, **lo que va a usar la concreción de una entrega en COM-06a**, sección 10,
D-68 punto 3, **y la bitácora de las solicitudes de COM-07a**, sección 11, D-69 punto 3; con una sola migración de esa app) y las **cosechas** de punta a punta:
el Agrónomo las planifica (con contrato o sin él), las modifica y las cancela; el Capataz las concreta desde el celular, con lo que rindió
cada sector y lo que se perdió. Lo cosechado va al contrato y lo que sobra entra a la **cámara** (la partida nace acá). La asignación
automática de la cámara, el vencimiento y la merma en cámara son de **COM-04b**; el enlace del cliente y la decisión del faltante, de
**COM-04c**.

**Estados de paso** (`docs/temas_abiertos.md`, «Abiertos desde el lote C5b»): entre COM-04a y COM-04b, una partida que nace de una cosecha
queda en la cámara sin asignarse sola a quien la espera (el paso 25 de COM-04b la recupera el primer día). Entre COM-04a y COM-04c, una venta
que queda «pendiente de decisión del cliente» no tiene todavía enlace ni pantalla para decidir: espera a COM-04c. Ninguno rompe datos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-PNF-CSC | Planificar Cosecha | docs/casos_de_uso/produccion/cosecha.md | — |
| PROD-MOD-CSC | Modificar Cosecha | docs/casos_de_uso/produccion/cosecha.md | — |
| PROD-CNC-CSC | Concretar Cosecha | docs/casos_de_uso/produccion/cosecha.md | Postcondición f (asientos): fuera, D-57. Postcondición k (asignación de cámara del excedente): COM-04b. 13a con enlace y correo al cliente: COM-04c. Postcondición n (planificar la entrega): COM-05a1 |
| PROD-CNL-ORD | Cancelar Orden (cosechas) | docs/casos_de_uso/produccion/cancelar_orden.md (sección «Comercial 1»: cosechas) | Postcondición h (asignación de cámara): COM-04b. El enlace nuevo de 8c y 8d: COM-04c. Entregas y envasado, postcondición i: COM-05a1. Mantenimiento: IoT |

## Leer

- Casos de uso: docs/casos_de_uso/produccion/cosecha.md **completo** (con «Cambios ya decididos», «Cómo se aplica», «Pantallas» y «Lo que
  difiere del prototipo»); de docs/casos_de_uso/produccion/cancelar_orden.md, la sección «Comercial 1»: cosechas; de
  docs/casos_de_uso/produccion/stock_maduro.md, «Cómo se aplica» (PROD-ASG-STK); de docs/casos_de_uso/comercial/suministro.md y
  pre_reserva.md, «Cómo se aplica» (los períodos y la pre-reserva, que D-64 punto 8 retoca); de faltante.md, solo «El camino de faltante».
- Modelo: docs/modelo/produccion.md (**MovimientoStock**, **Cosecha**, **StockCosechado**, Bitacora, Merma, «Diferencias», filas 18 y 19),
  docs/modelo/comercial.md (**ReservaStock** y **DetalleReserva**, con las dos restricciones que corrige D-64; DetalleVenta; «Diferencias»,
  fila 10), docs/modelo/contabilidad.md.
- Decisiones: **D-64** (puntos 1 a 6, 8, 11, 12 y 13), D-59, D-61, D-63, D-14, D-27, D-28, D-29, D-34, D-36, D-37, D-40, D-42, D-44, D-50,
  D-52, D-53, D-57, D-60; **D-67, puntos 1d, 1e y 2**; **D-68, puntos 2 y 3**; **D-69, punto 3**.
- Patrones: **docs/patrones/stock_maduro.md, secciones 7 y 8** (de la 8, todo menos la asignación de cámara y el recorte, que son de COM-04b),
  docs/patrones/bloqueos.md (secciones `produccion` y `comercial`, con «Cosecha y cámara»), docs/patrones/costo_del_lote.md,
  docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: **docs/api/produccion.md, secciones 8, 10 y 11** (lo que esta tarea escribe en `produccion`; la 10 la usa COM-06a y la 11, COM-07a), docs/api/stock.md
  (`proponer_lotes_fefo`, `registrar_salida_por_consumo`) y las secciones de PRD-01 a PRD-04 (también la 9,
  «Lo que deja hecho PRD-01»: `TIPOS_DE_PRODUCCION`); **docs/api/extensiones_de_produccion.md** (puntos 1 a 4); docs/api/notificaciones.md;
  docs/api/extensiones_de_maestros.md (impedimentos del invernadero).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): las funciones de «Pantallas» de `cosecha.md` (vale la última
  definición; ojo con `VIEWS.caphome`, `INIT.capcsc`, `VIEWS.capcsc`, `VIEWS.cscnew` y `VIEWS.cscmod`, definidas dos veces), `MODALS.cnlcsc`
  y, de `secCosecha`, el grupo de cosechas. docs/prototipos/produccion/ para la lista de órdenes y la bandeja que dejó PRD-01.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-03b): modelos, `servicios/` (`stock_maduro.py`, `compra_ventas.py`, `suministros.py`,
    `pre_reserva.py`, `calendario.py`, `comprobantes.py`), vistas, plantillas, `apps.py`, fábricas, `verificar_invariantes_de_reservas`;
  - `produccion/` completo (PRD-01 a PRD-04 y lo que sumó COM-02): `models.py`, `extensiones.py`, `servicios/` (`ordenes.py`, `mermas.py`,
    `costos.py`, `lotes.py`, `transiciones.py`, `bitacora.py`), las vistas y plantillas de la lista de órdenes y la bandeja;
  - `maestros/extensiones.py`, `maestros/servicios/invernaderos.py`; `core/notificaciones.py`, `core/models.py` (auditoría: `registrar`);
  - `contabilidad/models.py` (`OrigenDocumento`), `inventario/models.py` (`MovimientoInsumo`, el modelo a imitar), `inventario/servicios/stock.py`
    (`hoy`).

## Límites

- Crea modelos:
  - en `produccion` (**todo lo de COM-04 en esta app**, en una sola migración): `MovimientoStock`; `Bitacora.cosecha` y el tipo `cosecha`;
    `Cosecha.origen_cosecha`; las causas `dano_en_camara` y `vencimiento_en_camara` de `Merma` (D-64; las usa COM-04b); **para las entregas
    (D-68, punto 3; las usa COM-06a):** la causa `dano_en_entrega`, `Merma.orden` y `Consumo.orden`, con sus dos restricciones; **para las
    solicitudes (D-69, punto 3; los usa COM-07a):** los tipos `incumplimiento_de_clausula` y `anulacion_de_resolucion` de la bitácora, con su
    restricción;
  - en `comercial`: las restricciones de `ReservaStock` (fecha nula sin contrato) y de `DetalleReserva` (línea de partida en 0; si COM-02 ya
    la creó así, nada).
  → revisá docs/disparadores.md: cierra «Cuando exista `produccion` completa», puntos 3 y 5, y la parte de cosechas de «Cuando exista Lote,
  OrdenTrabajo o StockCosechado» (paso 8).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `produccion/migrations/00NN_cosecha_y_camara.py`: la tabla de `MovimientoStock`, `Bitacora.cosecha` con su restricción, los `choices`
    nuevos (también los dos tipos de bitácora de la sección 11), `Cosecha.origen_cosecha` con `default="automatica"`, `Merma.orden` y
    `Consumo.orden` con sus restricciones (la de origen de `Consumo` se reemplaza) y la restricción de los dos tipos nuevos;
  - `contabilidad/migrations/00NN_movimiento_de_stock.py`: solo `choices` (`movimiento_de_stock`);
  - `comercial/migrations/00NN_cosechas.py`: las restricciones de `ReservaStock` y `DetalleReserva`;
  - `core/migrations/00NN_comercial_cosechas`: solo `choices` (acciones `planificacion_cosecha`, `modificacion_cosecha`,
    `concrecion_cosecha`; `cancelacion_orden` y `registro_merma` ya existen).
- Permitido fuera de `comercial`:
  - `produccion`: las funciones de núcleo y los cambios de `docs/api/produccion.md`, sección 8 (incluidos `marcar_cancelada` y
    `texto_de_cancelacion` sacados de `cancelar_orden`, sin cambiar sus pruebas; **también las de cámara**: `crear_partida`,
    `aplicar_merma_de_partida`, `vencer_partida`, `partidas_del_invernadero`, aunque sus casos de uso sean de COM-04b; **y las de la sección 10**,
    `aplicar_merma_de_entrega`, `egresar_de_partida`, `devolver_a_partida`, `cerrar_reserva` y `registrar_consumo_de_orden`, aunque las use
    COM-06a; **y la de la sección 11**, `bitacora.registrar_evento_de_contrato`, aunque la use COM-07a); los puntos 3 y 4 de
    `extensiones.py`; el impedimento `partidas_en_camara`; **quitar los dos `exclude(tipo_orden=COSECHA)` «hasta COM-04a»** que dejó COM-02 en la
    bandeja y la lista, y **cambiar `ordenes_cancelables`** para que liste todos los `TIPOS_DE_PRODUCCION` (el código de PRD-01 la cruza con
    `TIPOS_QUE_CANCELA_PRODUCCION` y deja afuera las cosechas; `cancelar_orden` las sigue rechazando: la fila de una cosecha lleva la acción
    «Cancelar» de `comercial`) (D-67, punto 1e; lote C8, corrección a validar), para que muestren las cosechas con las acciones de
    `comercial` por los puntos nuevos; **reemplazar las restricciones `merma_causa_valida` y `bitacora_tipo_evento_valido`** con la lista
    completa de valores (las de PRD-01 a PRD-03 enumeran los valores: sumarlos a los `choices` no alcanza; `docs/api/produccion.md`, sección
    10); el filtro «Cosecha» de la bitácora (y los de los dos tipos de la sección 11). **Las pruebas existentes de `produccion` no se modifican** salvo las que esperaban que la
    bandeja y la lista excluyeran las cosechas (las de COM-02), la de PRD-01 que espera que `ordenes_cancelables` no liste cosechas y las
    de las dos restricciones reemplazadas (suman los valores nuevos): anotalas en el PR;
  - `core/models.py`: las acciones, `ETIQUETAS`, `VALORES_VISIBLES` (`origen_cosecha`) y `ACCIONES_DE_NEGOCIO`;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: **COM-04b** (PROD-ASG-CAM y el paso 25, PROD-VNC-CAM y el paso 20, la merma en cámara, la pestaña «Cámara», el parámetro
  `dias_aviso_vencimiento_camara`, `AlertaComercial.partida`, `orden_de_recorte`); **COM-04c** (`EnlaceCliente`, `core/enlaces.py`, COM-DCD-FLT,
  el paso 27, el enlace y el correo del camino de faltante); las entregas (COM-05a1); los asientos (D-57); reemplazar una cosecha pendiente
  por stock de cámara (tema abierto de PROD-ASG-CAM).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Núcleo en `produccion`** (D-64 puntos 1 a 5 y 12; `docs/api/produccion.md`, sección 8, **completa**). Modelos y migraciones de
   `produccion` y `contabilidad`; `cosechas.cosechar_lote`, `concretar_orden`, `costo_unitario_de_cosecha`; `camara.crear_partida`,
   `aplicar_merma_de_partida`, `vencer_partida`, `partidas_del_invernadero`; el movimiento de `aplicar_merma` y el cambio de
   `merma_acumulada`; `ordenes.marcar_cancelada` y `texto_de_cancelacion`; el impedimento `partidas_en_camara`; los puntos 3 y 4 de
   `extensiones.py`; **la sección 10 completa** (D-68, punto 3), con órdenes sueltas de tipo `entrega` (`orden_suelta`, D-67 punto 1d); **la
   sección 11 completa** (D-69, punto 3).
   Pruebas: `produccion/tests/test_modelos_cosecha_camara.py` (una por restricción: C2 de `MovimientoStock`, tipo según lote o partida,
   bitácora de cosecha con y sin cosecha), `test_cosechas_nucleo.py`, `test_camara_nucleo.py` (los de la sección 8, también los de las
   funciones de cámara: así COM-04b ya no toca `produccion`), `test_extensiones.py` (puntos 3 y 4 sin registrante y con dos), `test_entregas_nucleo.py` (los de la sección 10, con sus dos
   restricciones; la prueba de origen de `Consumo` de PRD-03 se amplía con el tercer origen: anotalo en el PR), `test_bitacora_de_contrato.py`
   (los de la sección 11), y en
   `test_prod_reg_mrm.py`, el movimiento «salida por merma» y la merma acumulada sin las de cámara. Corré **toda** la suite de `produccion`:
   tiene que dar lo mismo que antes, salvo lo anotado.
2. **Modelos de `comercial` y `core`** (D-64 puntos 6 y 7). Las dos restricciones; las acciones. Fábricas: `partida_cosechada(...)` (con su
   movimiento), `cosecha_manual(...)`; invariantes nuevos (sección 8 del patrón de stock: los de reservas, partidas y cosechas).
   Pruebas: `comercial/tests/test_modelos_cosecha_camara.py` (una por restricción).
3. **Stock maduro y camino de faltante** (patrón de stock, sección 8): `asignar(..., origen_cosecha=…)`; los períodos de un detalle finalizado
   (D-64 punto 8) en `cantidad_sin_cubrir`, `sin_cubrir_de_periodos`, `asignar` y la pre-reserva; `simular(..., lotes_excluidos,
   sin_reservas)`; `seguir_camino_de_faltante` **sin el enlace**: los estados del detalle y de la venta, `fecha_pendiente_decision`, el período
   que queda con cantidad sin cubrir, el detalle confirmado que vuelve a pendiente (D-64 punto 13) y la notificación al Vendedor que arma cada
   caso de uso. El enlace y el correo (o el aviso «registrá vos la decisión» sin correo) los suma COM-04c en esta misma función.
   Pruebas: en `test_prod_asg_stk.py`, el origen y el período finalizado; en `test_prod_prr_sum.py`, el período de un detalle terminado que
   pierde su reserva se vuelve a tomar; `test_simular.py`, los dos argumentos; `test_camino_de_faltante.py` (detalle abierto, ya pendiente,
   confirmado, período; sin enlace: lo prueba COM-04c).
4. **Planificar y modificar cosecha** (`cosecha.md`): `comercial/servicios/cosechas.py`.
   Pruebas: `test_prod_pnf_csc.py` (`ProdPnfCscServicioTests`): una por regla, postcondición y extensión (3a, 3b, 4a, 4b, 6a, 8a, 8b, 8c,
   10-11a, 11a a 11c, 12a, 12b, 14a, 15a, 15b); período fuera del horizonte; retiro desde otro invernadero; Vendedor distinto; la reserva sin
   contrato sin fecha. `test_prod_mod_csc.py` (`ProdModCscServicioTests`): una por postcondición (a a f) y extensión (2a, 5a, 5b.4a a 5b.4c,
   5c, 6a a 6d, 7a, 10a, 10b); el stock libre que suma lo propio; la fecha de entrega que no cambia. Concurrencia (`test_cosechas_concurrencia.py`):
   dos planificaciones por el último stock de un lote; una planificación contra una compra-venta; modificar contra concretar.
5. **Concretar cosecha** (`cosecha.md`, PROD-CNC-CSC), **sin** el `on_commit` de PROD-ASG-CAM (postcondición k: COM-04b) ni el enlace de 13a
   (COM-04c).
   Pruebas: `test_prod_cnc_csc.py` (`ProdCncCscServicioTests`): una por postcondición (a a e, g a j, l, m, o a r) y extensión (4a, 6a, 6b, 8a,
   8b, 10a con sus 3a y 3b, 10b, 12a, 13a con cobertura total, parcial y nula, en compra-venta y en suministro, 13b, 13c); la propuesta por
   sector (de tabla, con empates); el lote que llega a 0; el excedente y el faltante en la misma cosecha (el excedente cubre el faltante); la
   reserva con todo en 0 («liberada» y faltante total); solo el Capataz asignado; el costo de la partida es el de antes de la cosecha.
   Concurrencia: concretar contra cancelar; dos concreciones de la misma orden; concretar contra una venta que toma el stock libre del lote.
6. **Cancelar cosecha** (`cancelar_orden.md`, sección «Comercial 1»: cosechas): `resumen_de_cancelacion_de_cosecha`, `cancelar_cosecha`,
   `cancelar_cosecha_incluida`, **sin** el `on_commit` de PROD-ASG-CAM (postcondición h: COM-04b).
   Pruebas: las de esa sección (`test_prod_cnl_ord_cosechas.py`, `test_cancelar_cosecha_incluida.py`, `test_cancelar_cosecha_concurrencia.py`),
   salvo la concurrencia «cancelar contra la decisión del cliente» (COM-04c) y lo de la postcondición h (COM-04b).
7. **Vistas, plantillas y pantallas compartidas.** La lista de órdenes del Agrónomo y la bandeja del Capataz con las cosechas (con los puntos
   3 y 4; sin los `exclude` de COM-02); «Planificar cosecha», «Modificar cosecha», la ventana de cancelar (con su página sin JavaScript),
   «Concretar cosecha» en pasos para celular; los indicadores de cosechas del panel del Agrónomo (`secCosecha`; los de cámara los suma
   COM-04b). Vistas que solo orquestan (`abm.md`, sección 1), `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin
   JavaScript, errores por campo, aviso breve (D-29).
   Pruebas: `test_cosechas_vistas.py`: permisos (cada rol ve lo suyo y ningún botón lleva a un 403; el Capataz no concreta una cosecha ajena);
   los flujos con HTMX y sin él; las páginas de `calcular/` no escriben nada.
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de «Límites» y agregar lo que nace (para
   COM-04b: el `on_commit` de PROD-ASG-CAM en PROD-CNC-CSC y en la cancelación; para COM-04c: el enlace del camino de faltante); marcar
   COM-04a en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se
   corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el grupo «Cosechas» del panel del Agrónomo (queda en `docs/temas_abiertos.md`). No se
recortan las restricciones de la base, los bloqueos, la huella de PROD-MOD-CSC ni las pruebas de concurrencia.

## Hecho cuando

- El Agrónomo planifica una cosecha para un detalle de compra-venta o un período de suministro, o sin contrato, eligiendo los lotes; el
  Capataz la ve en su bandeja. La modifica (fecha, prioridad, lotes) sin cancelarla, y la cancela con motivo: el contrato se vuelve a cubrir
  sin los lotes de la cosecha cancelada, o pasa al camino de faltante.
- El Capataz concreta una cosecha desde el celular: baja el lote, sus agujeros y su costo; queda la bitácora y el movimiento de stock; lo que
  sobra entra a la cámara y lo que falta se vuelve a reservar o va al camino de faltante; las plantas perdidas son merma.
- Todas las funciones de `docs/api/produccion.md`, secciones 8, 10 y 11, existen con sus pruebas (también las de cámara, las de la entrega,
  probadas con órdenes sueltas, y la de la bitácora de las solicitudes).
- Todas las pruebas de `produccion`, `core` y de las tareas anteriores de `comercial` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial produccion maestros core contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial produccion --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`produccion`, `contabilidad`, `comercial`, `core`): `python manage.py migrate`. Datos: los de COM-03b (un invernadero
con Agrónomo, Capataz y Vendedor y un lote de «Lechuga Crespa» en Maduración con 300 plantas libres en dos sectores); un cliente con correo.

1. Con el Vendedor, una compra-venta con envío de 100 plantas para dentro de 3 días (COM-02): se programa una cosecha automática.
2. Con el Agrónomo: «Producción» › órdenes: la cosecha aparece con su contrato, origen «Automática» y los botones «Modificar» y «Cancelar».
   «Modificar»: fecha programada posterior a la entrega: aviso de retraso; más allá de la postcosecha: error con la primera fecha admitida.
   Cambiá el reparto entre lotes con un total distinto: no deja terminar. Dejalo como estaba y cambiá la prioridad: el resumen muestra antes y
   después. El Capataz tiene la notificación.
3. «Planificar cosecha» sin contrato: 40 plantas del lote. Queda «Manual», «Sin contrato».
4. Con el Capataz (en el celular o con el navegador angosto): la bandeja muestra las dos cosechas. Concretá la automática: la propuesta por
   sector suma 100; poné 90 (10 menos en un sector) y declará 4 perdidas por «Plaga». El resumen dice 6 que quedan en el lote, 4 de merma y
   el faltante de 10. Confirmá. Si el lote no tenía más stock libre, la venta pasa a «Pendiente de decisión del cliente» (sin enlace todavía:
   COM-04c); si tenía, se programó una cosecha «Encadenada».
5. Concretá la sin contrato con 40: en «Auditoría» queda la concreción con su partida `P-…` de 40 plantas (la pestaña «Cámara» la trae
   COM-04b).
6. Cancelá una cosecha con contrato: la ventana estima cuánto se vuelve a cubrir sin sus lotes; con motivo vacío, error.
7. Sin JavaScript: planificar, modificar, cancelar y concretar funcionan con «Actualizar» y el resumen como página.
8. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
