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

**Antes de empezar**

1. Abrí una terminal con el entorno virtual activo y corré `python manage.py migrate` (aplica `contabilidad` 0003, `produccion` 0008, `comercial` 0005 y `core` 0034) y `python manage.py runserver`. Abrí `http://127.0.0.1:8000/`. No hay datos cargados: los creás vos (los cargadores no existen, D-95).
2. Cuentas (todas con la contraseña de tus cuentas de prueba): un **Gerente**, un **Agrónomo**, un **Capataz** y un **Vendedor**; el Agrónomo, el Capataz y el Vendedor tienen que estar asignados al mismo invernadero (en «Invernaderos» › ficha › personal). Creá además, en otra ventana de navegador, una segunda cuenta de **Capataz** y otra de **Agrónomo** (sin invernadero) para probar permisos.
3. Datos mínimos, en este orden (si venís de COM-03b ya los tenés: invernadero con Agrónomo, Capataz y Vendedor, y un lote de «Lechuga Crespa» en Maduración):
   - un invernadero (por ejemplo «Norte») con **dos sectores de Maduración** de 100 agujeros cada uno y la variedad «Lechuga Crespa» con ciclo hasta Maduración (postcosecha de 7 días);
   - un **lote en Maduración de 300 plantas** (sembrá 300 plantines, concretá la siembra y concretá las transiciones hasta Maduración; repartilo 200 en un sector y 100 en el otro con la pantalla de transición); costo cualquiera;
   - un **cliente** con correo y una dirección activa (por ejemplo CUIT `20-12345678-6` o el que ya tengas).
4. Cada paso dice **quién** lo hace; cambiá de cuenta cerrando sesión (o con una ventana privada por cuenta). «Lo cubre…» indica qué prueba ya verifica ese paso, para que te concentres en lo que se ve y se siente.

**Camino feliz, con contrato**

1. **Vendedor** › «Comercial» › «Contratos» › «Nueva compra-venta»: cliente el de arriba, **envío** a su dirección, fecha pactada **dentro de 10 días**, renglón «Lechuga Crespa», **100** plantas a 100. Confirmá. *Tiene que ver:* la venta «abierta»; el sistema programa la cosecha automática que ves en el paso siguiente. (Lo cubre `test_recorrido_cosechas`.)
2. **Agrónomo** › «Producción» › «Órdenes» › filtro «Tipo: Cosecha»: aparece la cosecha (`OT-…`) con **Origen «Automática»**, el **Contrato** (`CV-…` y la fecha de entrega) y los botones **«Ver», «Modificar» y «Cancelar»**; arriba, **«Planificar cosecha»**. El **Capataz** recibió una notificación «Nueva cosecha OT-…». (Lo cubre `test_cosechas_vistas.ListaYBandejaTests`.)
3. **Agrónomo** › «Modificar» (ficha de la cosecha). *Tiene que ver:* lotes con su **stock libre que incluye lo que ya reserva esta cosecha**, la primera y la última fecha admitida, y **sin** campos para variedad, invernadero, contrato ni cantidad total. (Lo cubre `test_prod_mod_csc` y `test_cosechas_vistas.ModificarTests`.)
   - Poné una **fecha programada posterior a la de entrega** y tocá «Ver resumen»: aviso amarillo «la entrega saldrá con retraso». No lo confirmes todavía.
   - Poné una fecha **anterior a la primera admitida** (entrega − 7 días − 1): error junto a la fecha con «la primera fecha programada admitida es dd/mm/aaaa».
   - Cambiá la cantidad del lote a **90** (el total reservado era 100): «Ver resumen» no deja terminar («no coincide con el reservado»).
   - Dejá todo como estaba y cambiá solo la **prioridad a «Alta»**: «Ver resumen» muestra la tabla **antes → después** (media → alta); «Confirmar cambios». Vuelve a la lista con un aviso. El Capataz tiene la notificación «Cosecha OT-… modificada».
4. **Agrónomo** › «Planificar cosecha» › invernadero «Norte» › «¿Cubre un contrato?: No, sin contrato» › variedad «Lechuga Crespa» › fecha de mañana, prioridad «Media» › lote **40** plantas › «Ver resumen» (muestra el total y, si el lote pasa de su fecha máxima de cosecha, la advertencia con los días de exceso) › «Confirmar planificación». *Tiene que ver:* en la lista queda **Origen «Manual»** y **«Sin contrato»**. (Lo cubre `test_cosechas_vistas.PlanificarTests` y el recorrido.)
5. **Capataz** › «Mis órdenes» (en el celular o con la ventana angosta): las dos cosechas, cada una con **«Concretar cosecha»**. Abrí la automática. *Tiene que ver:* la fecha efectiva (hoy) y, por sector, la cantidad **propuesta como texto de ayuda** (100 repartidas según los agujeros que ocupa el lote en cada sector: 67 y 33 si el lote ocupa 200 y 100).
   - Escribí en un sector **10 menos** que lo propuesto y declará **4 perdidas** con causa «Plaga» (desplegá «declarar plantas perdidas»). «Ver resumen»: por lote, reservadas / cosechadas / perdidas, y el destino («Faltan 6…»). «Confirmar concreción». Vuelve a la bandeja con un aviso.
   - *Tiene que ver:* la cosecha desaparece de la bandeja. Si el lote tenía más stock libre, el **Agrónomo** ve en la lista una cosecha **«Encadenada»** para el faltante; si no, la venta pasa a **«Pendiente de decisión del cliente»** (todavía sin enlace: COM-04c). El Agrónomo y el Vendedor reciben su aviso. (Lo cubre `test_prod_cnc_csc` y el recorrido.)
6. **Capataz** › concretá la cosecha sin contrato con los valores propuestos (40). En «Auditoría» (Gerente) queda **«Concreción de cosecha»** con la partida `P-…` de 40 plantas, los movimientos de stock, la bitácora y el lote (la pestaña «Cámara» la trae COM-04b). En «Bitácora» del invernadero (Agrónomo) aparecen los registros de tipo **«Cosecha»**: el filtro «Tipo» ya lo ofrece.
7. **Agrónomo** › «Cancelar» sobre la cosecha «Encadenada» (u otra con contrato): la página muestra **lo que se libera** (lotes y cantidades), el **contrato**, la **estimación de cuánto se vuelve a cubrir sin sus lotes** y el recordatorio de «Modificar cosecha». Con el **motivo vacío**: error «Indicá el motivo de la cancelación». Con un motivo: se cancela, vuelve a la lista y el Capataz recibe «Orden OT-… cancelada» con el motivo.

**Errores y estados**

8. **Planificar** con una fecha anterior a hoy, una cantidad mayor que el stock libre y un lote sin cantidad: cada error sale **debajo de su campo** («Ver resumen»). Con un detalle de otro Vendedor o un período fuera del horizonte no aparece en la lista de contratos. (Lo cubre `test_prod_pnf_csc`.)
9. **Dos pestañas:** abrí «Modificar» de la misma cosecha en dos pestañas; confirmá un cambio en una y después en la otra: la segunda vuelve a abrir la cosecha con un aviso («la cosecha cambió»). Lo mismo con «Cancelar»: abrí la ventana, concretá la cosecha en otra pestaña (con el Capataz) y confirmá la cancelación: aviso de que ya no está «a realizar». (Lo cubre `test_cosechas_concurrencia` y `test_cancelar_cosecha_concurrencia`.)
10. **Concretar** con más plantas que los agujeros del sector, con una fecha futura y con perdidas sin causa: errores por campo, sin resumen. (Lo cubre `test_prod_cnc_csc`.)

**Roles**

11. **Gerente:** en «Producción» › «Órdenes» › «Cosecha» ve la lista **sin botones** de cosecha ni «Planificar cosecha». Escribiendo a mano `/comercial/cosechas/planificar/`, `/comercial/cosechas/<id>/modificar/`, `/cancelar/` o `/concretar/`: **403**. (Lo cubre `test_cosechas_vistas.PermisosTests`.)
12. **Vendedor:** igual: **403** en las cuatro direcciones. **Capataz:** ve «Concretar cosecha» solo en las suyas; `/comercial/cosechas/planificar/` y `/modificar/` dan 403. **Segundo Capataz y segundo Agrónomo:** no ven la cosecha en su bandeja ni en su lista, y las direcciones escritas a mano dan 403. **Agrónomo:** `/concretar/` da 403.
13. **Inicio del Agrónomo:** después de «Mi producción», el grupo **«Cosechas»** con «A realizar», «Vencidas» y «Sin Capataz» (cada indicador lleva a la lista filtrada). Probá dejando el invernadero sin Capataz activo (desde su ficha): «Sin Capataz» sube y «Planificar cosecha» deshabilita el invernadero con «sin Capataz activo». (Lo cubre `test_extensiones_de_produccion` y `test_cosechas_vistas`.)
14. **Inicio del Capataz:** la cosecha de hoy aparece con su botón «Concretar cosecha».

**Navegador real (obligatorio: hay formularios que se envían)**

15. Abrí **una ventana privada**, iniciá sesión con el **Agrónomo** y enviá **hasta el final** «Planificar cosecha» (sin contrato, 10 plantas); después, con el **Capataz** en otra ventana privada, enviá hasta el final «Concretar cosecha». Tienen que terminar con el aviso verde y la cosecha en su lugar. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: el cliente de Django no ve los encabezados `Origin` ni el JavaScript. Mirá también que los desplegables de invernadero, detalle y variedad **redibujen el formulario sin mover la pantalla** y sin validar nada al elegir.

**Opcionales**

16. **Sin JavaScript** (desactivalo en el navegador): planificar, modificar y concretar funcionan con «Actualizar», «Ver resumen» y «Confirmar»; cancelar es una página.
17. **Celular:** abrí «Concretar cosecha» en un celular (o con la ventana de 360 px): una columna, botones grandes, el resumen al final.

**Después del merge**

18. Revisar en el log de Render que se aplicaron las cuatro migraciones nuevas (`contabilidad` 0003, `produccion` 0008, `comercial` 0005 y `core` 0034) y que «Producción» › «Órdenes» abre.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (rama `feature/com-04a-cosechas`, 24/11/2026)

- **Migraciones** (ninguna de datos; `sqlmigrate` leído: solo `CREATE TABLE`, `ADD COLUMN`, `ADD`/`DROP CONSTRAINT` de restricciones `CHECK` que se recrean con más valores; ningún `DELETE` ni `UPDATE` ni `DROP` de datos):
  - `produccion/0008_cosecha_y_camara`: `MovimientoStock` (hija de `OrigenDocumento`; 6 restricciones, entre ellas C2), `Bitacora.cosecha` (con «tipo `cosecha` ⇔ cosecha») y los tipos `cosecha`, `incumplimiento_de_clausula` y `anulacion_de_resolucion` (con su restricción
    «sin lote, etapa ni cosecha»), `Cosecha.origen_cosecha` (default `automatica`, con su restricción), `Merma.orden` (⇔ `dano_en_entrega`) y las tres causas nuevas, `Consumo.orden` con `consumo_un_solo_origen` ampliada a tres orígenes. Las restricciones `bitacora_tipo_evento_valido` y
    `merma_causa_valida` se reemplazan por la lista completa.
  - `contabilidad/0003_movimiento_de_stock` (solo `choices`; SQL vacío), `comercial/0005_cosechas` (`reserva_stock_fecha_segun_detalle`: fecha de entrega nula ⇔ sin detalle) y `core/0034_comercial_cosechas` (solo `choices`: `planificacion_cosecha`, `modificacion_cosecha`, `concrecion_cosecha`).
  - `core/models.py`: `Accion`, `ACCIONES_DE_NEGOCIO`, `ETIQUETAS` (`origen_cosecha`) y `VALORES_VISIBLES` (`origen_cosecha`).
- **`produccion` (núcleo físico, `docs/api/produccion.md`, secciones 8, 10 y 11):** `servicios/movimientos.py` (ayudas comunes), `cosechas.py` (`cosechar_lote`, `concretar_orden`, `costo_unitario_de_cosecha`), `camara.py` (`crear_partida`, `aplicar_merma_de_partida`, `vencer_partida`, `partidas_del_invernadero`, `egresar_de_partida`,
  `devolver_a_partida`); `mermas.aplicar_merma` suma el movimiento «salida por merma», `mermas.aplicar_merma_de_entrega`, `consumos.registrar_consumo_de_orden` (`cerrar_reserva` ya existía desde PRD-01) y `bitacora.registrar_evento_de_contrato`. `Merma.CAUSAS_EN_PIE` (las siete de PRD-02): las validaciones y las pantallas de
  merma usan esa lista, no `Merma.Causa`. Puntos 3 y 4 de `extensiones.py` (`registrar_acciones_de_cosecha`, `registrar_entradas_de_comercial`), el impedimento `partidas_en_camara` de la baja del invernadero y el filtro «Cosecha» (y los dos tipos de contrato) de la bitácora. `ordenes.py`: se quitaron los tres `exclude` «hasta COM-04a»
  (bandeja, lista y detalle) y `ordenes_cancelables` lista todos los `TIPOS_DE_PRODUCCION`; `contexto_de_cosechas` arma lo que las pantallas piden a `comercial`.
- **`comercial` (servicios):** `faltantes.py` (`seguir_camino_de_faltante`, sin enlace ni correo: COM-04c), `cosechas.py` (planificar, modificar, concretar, cancelar y `cancelar_cosecha_incluida`, con los bloqueos en el orden del patrón: cuentas → invernaderos → variedad → sectores → lotes y partidas → contrato y detalle → fila de la cosecha → reserva y líneas),
  y en `stock_maduro.py`: `asignar(..., origen_cosecha=)`, el período de un detalle «finalizado» hasta su `fecha_fin_detalle` (D-64 punto 8: `cantidad_sin_cubrir`, `sin_cubrir_de_periodos`, `asignar`), `simular(..., lotes_excluidos, sin_reservas)` y `estimar` (la estimación de 6b); `pre_reserva.py` retoma esos períodos.
  Registrantes en `apps.py`: acciones y entradas de cosecha y el grupo «Cosechas» del Inicio del Agrónomo (`secCosecha`).
- **Pantallas** (`views_cosechas.py`, `templates/comercial/cosechas/`): «Planificar cosecha», «Modificar cosecha», «Concretar cosecha» (celular) y «Cancelar cosecha», cada una con su `calcular/` (redibuja sin validar) y su `revisar/` (el resumen), ninguna escribe; en `produccion`, la lista (columnas «Origen» y «Contrato» con el filtro «Cosecha», botones, aviso de períodos sin cobertura), la bandeja, el detalle y el Inicio del Capataz muestran las cosechas con los botones de `comercial`.
- **Disparadores** que se cumplieron (para tachar, M3): «Cuando exista `produccion` completa», puntos 3 y 5 (filtro «Cosecha» y movimiento «salida por merma»), y la parte de cosechas de «Cuando exista Lote, OrdenTrabajo o StockCosechado» (paso 8). **Nacen:** para COM-04b, el `on_commit` de PROD-ASG-CAM en PROD-CNC-CSC y en la cancelación (hoy las partidas nuevas quedan sin asignarse hasta el paso diario 25), y la entrada «Pérdida en cámara» de `entradas_de_comercial`; para COM-04c, el enlace y el correo del camino de faltante en `seguir_camino_de_faltante`.
- **Estados de paso:** una partida que nace de una cosecha queda en la cámara sin asignarse sola a quien la espera; una venta «pendiente de decisión del cliente» todavía no tiene enlace ni pantalla para decidir (COM-04b y COM-04c; ninguno rompe datos).

**Pruebas** (M1; comandos de «Hecho cuando», 24/11/2026)

- `manage.py test comercial produccion maestros core contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **4176 pruebas, OK**.
- `manage.py test comercial produccion --keepdb --tag concurrencia`: **100 pruebas, OK** (las de COM-04a: 12). `manage.py test produccion --keepdb --tag migracion`: 2 pruebas, OK. `makemigrations --check --dry-run`: sin cambios; `manage.py check`: sin problemas.
- Nuevas en `produccion`: `test_modelos_cosecha_camara` (14), `test_cosechas_nucleo` (15), `test_camara_nucleo` (23), `test_entregas_nucleo` (13), `test_bitacora_de_contrato` (7). En `comercial`: `test_modelos_cosecha_camara` (6), `test_camino_de_faltante` (8), `test_prod_pnf_csc` (47), `test_prod_mod_csc` (27), `test_prod_cnc_csc` (41), `test_prod_cnl_ord_cosechas` (26),
  `test_cancelar_cosecha_incluida` (7), `test_cosechas_vistas` (26), `test_recorrido_cosechas` (1), `test_cosechas_concurrencia` (9), `test_cancelar_cosecha_concurrencia` (3). Ampliadas: `test_prod_asg_stk`, `test_prod_prr_sum`, `test_simular`, `test_extensiones_de_produccion` (5) y, en `produccion`, `test_extensiones` (7) y `test_prod_reg_mrm` (2).
- **Pruebas existentes cambiadas** (para anotar en el PR; ninguna se borró ni se debilitó: cambió la regla, y el estudiante aprobó los ajustes en las pausas A y B):
  - `produccion/test_cosecha_en_produccion.py`: las 4 pruebas «hasta COM-04a» (bandeja, lista, cancelables y ventana de detalle) se invirtieron.
  - `produccion/test_modelos_transicion.py`, `test_mermas_nucleo.py` y `test_prod_reg_mrm.py`: usan `Merma.CAUSAS_EN_PIE` (las siete) donde usaban `Merma.Causa`; `vencimiento_en_camara` ya no viola la restricción. `test_prod_cns_bit.py` (2): el filtro de la bitácora ofrece `cosecha` y los dos tipos de contrato.
  - `comercial/test_modelos_suministros.py` (C3): el cambio de contrato de una reserva se hace en un solo `update` (la restricción de la fecha de entrega). `test_prod_asg_stk.py` (precondición b) y `test_prod_prr_sum.py` (el detalle finalizado se pre-reserva hasta su fecha de fin): D-64 punto 8.
  - `comercial/test_com_cns_sum.py` (3 pruebas con alerta): el detalle «finalizado» de la fábrica ahora tiene sus períodos reservados para que «el cálculo dé 0»; sin reservas, desde D-64 punto 8, el período se debe y el cálculo da lo que falta. `test_stock_maduro_concurrencia.py` (baja del invernadero): la partida de la prueba está agotada, porque desde D-64 punto 12 una partida «disponible» impide la baja.
  - Fábricas: `partida()` también crea su `ingreso_a_camara`; los invariantes cuentan lo cubierto de un lote cosechado como `min(cosechada, reservada)` (regla 9 de 8.8) y suman los de la sección 8 del patrón de stock.

**Verifiqué** (con el cliente de Django y la base de pruebas)

- El recorrido `test_recorrido_cosechas` (pasos 1 a 7 de la verificación a mano, por rol y por estado): OK.
- Las cuatro migraciones: `makemigrations --check`, `sqlmigrate` leído y aplicadas en la base de pruebas (`produccion` con su prueba `@tag("migracion")`): OK.
- La concurrencia: planificar contra planificar y contra una venta, modificar contra concretar, concretar contra cancelar, dos concreciones, concretar contra una venta, cancelar contra modificar: OK, siempre con los invariantes de reservas y sin un error 500.

**Lo cubre una prueba**

- Reglas de cada caso de uso: `test_prod_pnf_csc`, `test_prod_mod_csc`, `test_prod_cnc_csc`, `test_prod_cnl_ord_cosechas`; permisos, botones y flujos con y sin HTMX: `test_cosechas_vistas`; el núcleo de `produccion`: `test_cosechas_nucleo`, `test_camara_nucleo`, `test_entregas_nucleo`, `test_bitacora_de_contrato`; los registrantes y el Inicio: `test_extensiones_de_produccion`.

**No pude verificar**

- El aspecto, el celular, el CSRF y el encabezado `Origin` en un navegador real, el JavaScript (los desplegables que redibujan sin mover la pantalla) y el funcionamiento con JavaScript desactivado: pasos 15 a 17 de la verificación a mano.
- La aplicación de las migraciones en Render/Neon (paso 18). El correo al cliente del camino de faltante no existe todavía (COM-04c).

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Planificar cosecha (`VIEWS.cscnew`) | No mostraba la primera fecha admitida ni el aviso de retraso con el texto de suministro; sin búsqueda por cliente o variedad; sin el error de cantidad mayor que lo sin cubrir; sin resumen antes de confirmar | Mensaje de 8b con la primera fecha admitida; advertencia `retraso` (con la posible indemnización en un suministro) y `fecha_maxima` con los días de exceso; búsqueda; error 11b por campo; resumen con firma y «Confirmar planificación» como página (y botones «Actualizar» y «Ver resumen» sin JavaScript) | Pasos 8, 11 y 13; extensiones 5a, 8b, 8c, 11b y 11c |
| Modificar cosecha (`VIEWS.cscmod`) | Sin resumen con valor anterior y nuevo; sin el aviso 5b.4c con el enlace a cancelar | Tabla «antes → después» (paso 8); advertencia `lotes_no_alcanzan` con el enlace a «Cancelar cosecha»; el stock libre de cada lote incluye lo ya reservado por esta cosecha | Paso 8; extensiones 5b.4a a 5b.4c |
| Cancelar cosecha (`MODALS.cnlcsc`) | Sin el resumen de lo que se libera ni la estimación de recobertura | Página (cada ventana es una página, D-47) con las líneas, el contrato, la estimación de cuánto se vuelve a cubrir sin sus lotes, el caso «ya espera la decisión del cliente» y el recordatorio de «Modificar cosecha»; motivo obligatorio | Pasos 4 y 6; extensiones 4b, 4c, 6b y 6c de PROD-CNL-ORD |
| Concretar cosecha (`VIEWS.capcsc`, `capcscCalc`) | La fecha efectiva no validaba la fecha de creación; faltaban el error del máximo del lote y el de perdidas por sector; sin resumen con el destino de lo cosechado | Validaciones 6a, 6b, 8a, 8b y 10a.3a/3b por campo; resumen por lote con el destino (cámara, contrato, faltante) antes de confirmar; la propuesta por sector como texto de ayuda | Pasos 5 a 11; extensiones 6a, 6b, 8a, 8b, 10a |
| Lista de órdenes (`ordenesTab`, `tabCosechas`) | Dos listas separadas | Una sola con el filtro «Tipo» (la de PRD-01): con «Cosecha» suma «Origen» y «Contrato» y el aviso de períodos sin cobertura completa; los botones salen de `registrar_acciones_de_cosecha` y nunca llevan a un 403 | D-64 punto 11; «Lo que difiere del prototipo» |
| Panel del Agrónomo (`secCosecha`) | — | Grupo «Cosechas» (a realizar, vencidas, sin Capataz) con `registrar_seccion_de_inicio` | D-43; `cosecha.md`, «Pantallas» |

**Decisiones:** ninguna nueva de equipo (`D-NN`). Aplicadas D-14, D-27, D-28, D-29, D-34, D-36, D-37, D-40, D-42, D-44, D-50, D-52, D-53, D-57, D-59, D-60, D-61, D-63, **D-64** (puntos 1 a 6, 8, 11 a 13; el 9 queda para COM-04b), D-67 (1d, 1e y 2), D-68 (2 y 3) y D-69 (3).

**Desvíos y temas abiertos** (para `docs/temas_abiertos.md`; no los corregí en silencio):

1. **Máximo al concretar (8b):** el caso de uso dice «cantidad reservada + stock libre del lote sin contar esta reserva». Leído literalmente cuenta dos veces las plantas de la propia reserva (se podrían tomar plantas reservadas por otra orden). Se implementó: reservada + (cantidad actual − todo lo reservado, esta reserva incluida) = **cantidad actual menos lo que reservan las demás órdenes**. Hay que corregir el texto del extracto y de Drive.
2. **Plantas no cosechadas ni perdidas:** quedan en el lote como stock libre y **pueden volver a reservarse** al cubrir el faltante (`asignar` no excluye los lotes de la cosecha en la 13a, a diferencia de la cancelación); una cosecha con todo en 0 y sin perdidas se vuelve a cubrir con su propio lote.
3. **Un lote en cero** (`cosechar_lote`) deja `costo_acumulado` en 0 y el costo de lo cosechado se calcula con `costo_de_la_merma` (si se cosecha todo, el costo entero); el costo por planta del movimiento y de la partida es `costo_acumulado ÷ cantidad` con 4 decimales.
4. **Bitácora `cosecha`:** sus `sectores` son todos los sectores que ocupa el lote (también los de 0 plantas); la merma de las plantas perdidas lleva la fecha de **hoy** y no la efectiva.
5. **Contratos de código que fijaron las pruebas y aprobó el estudiante:** claves de detalle `cv:<id>` y `sum:<id>:<fecha>`, `ultima_fecha` = fecha de entrega, errores por campo `lote_<id>`, `cantidad_<lote>_<sector>`, `perdidas_<lote>[_<sector>]` y `causa_<lote>`, y los códigos `sin_stock_maduro`, `detalle_no_cubrible`, `supera_stock_libre`, `supera_sin_cubrir`, `supera_maximo`, `supera_no_cosechadas`, `cosecha_cambio`, `cosecha_resuelta`, `orden_no_a_realizar`, `no_modificable`, `total_distinto`, `sin_cambios`, `lotes_no_alcanzan` (advertencia) y `cosecha_duplicada` (la 15a se verifica **antes** que lo demás: una cosecha repetida también supera lo sin cubrir). Los usan COM-04b y COM-04c.
6. **Sectores:** se bloquean directo (`SectorProduccion`), no con `bloquear_sectores` (que rechaza un sector «fuera de servicio»: un lote reubicado ya no está ahí, pero la cosecha de un lote con ocupaciones de sectores ya fuera de servicio no debe fallar).
7. **Baja del invernadero:** `partidas_en_camara` (D-64 punto 12) la impide mientras haya una partida «disponible», aunque su lote esté finalizado (por eso se ajustó la prueba de concurrencia de la baja).
8. **`detalle_de_orden`:** quitó el tercer `exclude` (API, sección 9; el plan lo aprobó el estudiante). Una cosecha no tiene `puede_cancelar` ni `puede_concretar` desde `produccion`: los botones son los de `comercial`.
9. **Cancelar como página**, no como ventana: sin JavaScript todo funciona y con HTMX no hay ventana propia (D-47: «cada ventana es una página»). El correo y el enlace del faltante (COM-04c) y la asignación de cámara (COM-04b) quedan para sus tareas.
