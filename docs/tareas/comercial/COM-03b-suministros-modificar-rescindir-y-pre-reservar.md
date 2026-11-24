# COM-03b · Suministros: modificar, rescindir, dejar sin efecto la rescisión y pre-reservar (pasos 35 y 40)

Estado: hecha (24/11/2026, falta su PR) | App: comercial (y los orígenes de alertas en maestros, D-62) | Rama: feature/com-03b-suministros-modificar-rescindir-y-pre-reservar | Ronda: Comercial 1

Depende de: **COM-03a** (el modelo del suministro, `pactar_suministro`, el calendario, la consulta), **DIA-01** (hecha:
`registrar_paso_diario`) y **MAE-02d** (el enlace de cada alerta: `Enlace`, `registrar_enlace_de_alerta`, `enlaces_de_alertas` y la ruta
`alertas:ir`; D-62, tercera enmienda). Si alguna no está mergeada, frená: esta tarea **no** crea el punto del enlace.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda mitad de COM-03 (D-67, punto 2): **modificar** un suministro sin tocar lo ya reservado (detalle sucesor,
MD-131), **rescindirlo por mutuo acuerdo** (COM-RSC-SUM) y **dejar sin efecto** la rescisión (COM-ANL-RSC), con el cierre diario (**paso
35**), y la **pre-reserva diaria** (**paso 40**), que aparta el producto de cada período cuando entra en la ventana y avisa si no alcanza. Trae
la **primera alerta comercial** («período sin cobertura completa», MD-133), con su tabla de vínculo (D-63) y su enlace en la campana (D-62).
También completa la ficha de COM-03a con lo que esto agrega.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-MOD-SUM | Modificar Suministro | docs/casos_de_uso/comercial/suministro.md | Contrato «finalizado» al concretar el último período: COM-06 |
| COM-RSC-SUM | Rescindir Suministro (y el cierre, paso diario 35) | docs/casos_de_uso/comercial/suministro.md | El cierre espera las entregas a realizar: COM-05a1 y COM-06. Resolución durante la rescisión: COM-07 |
| COM-ANL-RSC | Dejar sin Efecto la Rescisión (alto nivel) | docs/casos_de_uso/comercial/suministro.md | — |
| PROD-PRR-SUM | Pre-reservar Período de Suministro (paso diario 40) | docs/casos_de_uso/produccion/pre_reserva.md | Lo sigue el paso 50: COM-05a1 |
| COM-CNS-SUM | Consultar Suministro (lo que completa: la situación por alerta, la rescisión, el historial y los botones de la regla 10) | docs/casos_de_uso/comercial/suministro.md | La base es de COM-03a |

## Leer

- Casos de uso: de docs/casos_de_uso/comercial/suministro.md, **COM-MOD-SUM, COM-RSC-SUM y COM-ANL-RSC completos**, «Cambios ya decididos» y,
  de «Cómo se aplica», las secciones «COM-MOD-SUM», «COM-CNS-SUM» (lo que completa esta tarea) y «COM-RSC-SUM y COM-ANL-RSC»; «Pantallas»
  y «Lo que difiere del prototipo» (las filas de modificar y rescindir). docs/casos_de_uso/produccion/pre_reserva.md **completo**.
- Modelo: docs/modelo/comercial.md (Suministro, DetalleSuministro y sus cláusulas —ya creados por COM-03a—, **AlertaComercial**, «Pendientes
  de MD»).
- Decisiones: **D-62** y **D-63**, D-61, D-59, D-60, D-56, D-14, D-27, D-28, D-29, D-36, D-37, D-41, D-42, D-44, D-54, D-57; **D-67, punto 2**.
- Patrones: docs/patrones/stock_maduro.md, sección 7; docs/patrones/bloqueos.md (sección `comercial`, «Suministros»), docs/patrones/abm.md,
  docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: **docs/api/alertas.md** (secciones 1, 2, 4 y **8**), docs/api/notificaciones.md, `core/procesos.py` (su encabezado).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `INIT.summod`, `VIEWS.summod` (segunda), `contratoErr` (con su
  reemplazo «Incumplimientos tolerados: se admite 0»), `chgDiff`, `rigeDesde`, `periodos`, `precioHoy`, `ACT['summod-ok']`; `MODALS.sumhist`; y
  la rescisión (bloque «Revisión del 21/11/2026 (5)», al final del archivo): `rscConserva`, `MODALS.sumrsc`, `ACT['sumrsc-ok']`,
  `MODALS.sumrscanl`, `ACT['sumrscanl-ok']` y los reemplazos de `VIEWS.sum` y `tabContratos`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-03a): modelos, `servicios/` (`suministros.py`, `calendario.py`, `stock_maduro.py`,
    `comprobantes.py`), vistas, plantillas de suministro, `apps.py`, fábricas, `verificar_invariantes_de_reservas`;
  - `maestros/alertas.py`, `maestros/extensiones.py` (el punto del enlace de MAE-02d), `maestros/servicios/alertas.py`,
    `maestros/servicios/invernaderos.py` (`items_de_campana`), `maestros/tests/fabricas.py` (`tipo_de_alerta_de_prueba`);
  - `core/procesos.py`, `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos en `comercial`: `AlertaComercial` (D-63, con «exactamente un origen»). Los campos de la rescisión y del sucesor ya existen
  (COM-03a). → revisá docs/disparadores.md: nacen «Cuando exista Entrega», puntos 5 y 6, y «Resolución de un contrato con rescisión
  acordada» (paso 8 de «Pasos»).
- Migraciones:
  - `comercial/migrations/00NN_alerta_comercial.py`: la tabla y su restricción;
  - `core/migrations/00NN_comercial_suministros_2`: solo `choices` (acciones `modificacion_suministro`, `pre_reserva_periodo`,
    `rescision_suministro`, `anulacion_rescision`, `cierre_rescision`).
  Con el número libre en `main` al abrir el PR. **Ninguna de datos.** Ninguna en `maestros` (los orígenes nuevos no tocan la base).
- Permitido fuera de la app:
  - `maestros` (D-62, punto 1): en `alertas.py`, solo los cuatro valores nuevos de `Origen` (el punto del enlace es de MAE-02d). **Ninguna
    prueba existente de `maestros` se modifica**;
  - `core/procesos.py`: solo el comentario de la tabla de órdenes (paso 20 en `comercial`, D-59; paso 35 nuevo, «Cerrar rescisiones»);
  - `core/models.py`: solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` (`motivo_rescision`) y `ACCIONES_DE_NEGOCIO`, y su migración;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: entregas y su planificación (COM-05a1, el paso 50); concreción y finalización por entrega (COM-06); solicitudes de
  revisión y resolución del contrato (COM-07; la alerta «suministro resuelto», T-02, D-63 punto 2); cobros y vencimiento de pagos (COM-08,
  paso 30); la rescisión unilateral con preaviso (mejora futura); los asientos (D-57); reintentos automáticos de correos y notificaciones.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Orígenes de las alertas en `maestros` (D-62, punto 1).** El punto de extensión y la campana que pasa por `alertas:ir` **los hizo
   MAE-02d**: acá solo se suman los cuatro valores de `Origen`.
   Pruebas: las de los orígenes nuevos en `maestros/tests/test_alerta.py`. Corré **toda** la suite de `maestros` y de `core`.
2. **`AlertaComercial` y auditoría.** La ficha con su restricción; las acciones nuevas; la fábrica `alerta_de_periodo(...)`; en
   `verificar_invariantes_de_reservas()`, el invariante de `fecha_fin_detalle` con y sin rescisión.
   Pruebas: en `comercial/tests/test_modelos_suministros.py`, métodos nuevos (exactamente un origen: la viola y no la viola).
3. **Modificar**: `modificar_suministro`, `datos_de_modificacion`, `resumen_de_modificacion`, `huella_de`.
   Pruebas: `comercial/tests/test_com_mod_sum.py` (`ComModSumServicioTests`): una por postcondición (a a j) y extensión (1a, 5a a 5g,
   5c.1a, 6a, 7a, 10a con `hoy` movido entre la lectura y la confirmación, 10b con la huella cambiada, 11a); el sucesor (fecha de fin del
   anterior, `reemplaza_a`, precio propuesto, `fecha_base_ajuste`, reservas que siguen con el anterior); el par vigente después de terminar
   un detalle; acortar con un detalle que se queda sin períodos; el contrato que pasa a «finalizado» sin períodos pendientes; tolerados
   iguales a los acumulados (se acepta) y menores (se rechaza); las notificaciones. Concurrencia (`test_suministros_concurrencia.py`,
   métodos nuevos): una modificación contra la pre-reserva del mismo contrato; dos modificaciones del mismo contrato.
4. **Pre-reserva diaria** (`comercial/servicios/pre_reserva.py`) y la alerta: el tipo `comercial_periodo_sin_cobertura`, su enlace
   (`registrar_enlace_de_alerta`) y el paso 40, en `ComercialConfig.ready()`.
   Pruebas: `comercial/tests/test_prod_prr_sum.py` (`ProdPrrSumServicioTests`): una por regla, postcondición y extensión (2a, 3a con y sin
   nada disponible, 3b, \*a con un período que falla y los demás que siguen); idempotencia (dos corridas el mismo día: nada nuevo, ningún
   registro de auditoría nuevo); un día sin corrida se recupera al siguiente (`hoy` + 2); cliente inactivo; detalle finalizado y detalle
   con `fecha_fin_detalle`; la alerta: invernadero de D-63, sin duplicar, cantidad actualizada, resuelta al cubrirse y al pasar su fecha;
   la notificación al Vendedor solo la primera vez; el enlace por rol (Gerente: el suministro; Agrónomo: el invernadero). Concurrencia
   (`test_pre_reserva_concurrencia.py`): las tres del extracto.
5. **Rescindir y dejar sin efecto** (`suministro.md`, «COM-RSC-SUM y COM-ANL-RSC»): `datos_de_rescision`, `rescindir_suministro`,
   `dejar_sin_efecto_rescision`, `cerrar_rescisiones` (paso diario 35) y la constancia en `comprobantes.py`.
   Pruebas: `comercial/tests/test_com_rsc_sum.py` (`ComRscSumServicioTests`): una por regla, postcondición y extensión (2a, 4a, 6a con `hoy`
   movido, 6b con la huella cambiada, 7a, 7b); solo el Gerente; períodos conservados con detalles de distinto período; la fecha de fin de un
   detalle sin períodos en la ventana; sin multa ni incumplimiento; la pre-reserva no toma períodos posteriores; `modificar_suministro`
   rechaza; el cierre (idempotente, `fecha_rescision`, detalles finalizados); la invariante de `fecha_fin_detalle`.
   `test_com_anl_rsc.py` (`ComAnlRscServicioTests`): una por regla y postcondición; rechazada después de la última entrega; la pre-reserva
   del día siguiente toma los períodos que entraron a la ventana. Concurrencia: una rescisión contra la pre-reserva del mismo contrato y
   contra una modificación. `proceso_diario --listar` muestra «35 · cerrar_rescisiones» y «40 · pre_reservar_suministros».
6. **Lo que completa la consulta de COM-03a** (`suministro.md`, «COM-CNS-SUM»): «Sin cobertura completa · faltan N» también con alerta activa;
   los avisos y la marca de la rescisión en la ficha y en la lista, el filtro «rescindido» y el calendario que corta en la última entrega;
   «Con cambios desde el dd/mm» y «Ver historial de cambios» (`MODALS.sumhist`); los botones de la regla 10 («Modificar suministro»,
   «Rescindir suministro», «Dejar sin efecto la rescisión»).
   Pruebas: en `comercial/tests/test_com_cns_sum.py`, métodos nuevos (una por cada cosa de esta lista).
7. **Vistas y plantillas.** «Modificar suministro» (con el panel «Cambios» y la ventana de resumen), las ventanas de rescindir y de dejar sin
   efecto (con su página sin JavaScript) y la ventana del historial. La campana del Gerente lleva la alerta de período a la ficha del
   suministro. Vistas que solo orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores
   por campo, aviso breve (D-29).
   Pruebas: en `comercial/tests/test_suministros_vistas.py`, `ComModSumVistaTests` y `ComRscSumVistaTests`: permisos (el Vendedor no ve
   «Rescindir»; un Vendedor no modifica un suministro ajeno; ningún botón lleva a un 403); los flujos con HTMX y sin él; `calcular/` no
   escribe nada.
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, agregar los que nacen (COM-06: finalizar detalle y
   contrato al concretar el último período; COM-05a1 y COM-06: el cierre de una rescisión espera las entregas; COM-07: la resolución con
   rescisión acordada); marcar COM-03b en `docs/tareas/README.md` y en el plan (D-62 y D-63 ya están vigentes); lo distinto de lo escrito, a
   `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es la ventana del historial (queda «Con cambios desde el dd/mm» y una línea en
`docs/temas_abiertos.md`). No se recortan las restricciones de la base, la huella (10b), los bloqueos ni las pruebas de concurrencia.

## Hecho cuando

- Modificar un detalle crea su sucesor desde el primer período fuera de la ventana; lo ya reservado no cambia; el historial lo muestra.
  Terminar un detalle o acortar la duración no aplica multa. Una modificación que llega tarde (10a, 10b) no registra nada.
- `python manage.py proceso_diario` pre-reserva los períodos que entran en la ventana, una sola vez aunque se corra dos veces, y avisa con
  la alerta «Período sin cobertura completa» (al Agrónomo, o al Gerente, y al Vendedor por notificación) cuando no alcanza; la alerta se
  resuelve sola al cubrirse o al pasar la fecha, y en la campana lleva a la pantalla correcta según quién la ve.
- El Gerente registra la rescisión de un suministro acordada con el cliente: se entrega lo que ya estaba en la ventana, no se reserva nada
  más, el cliente recibe la constancia y, pasada la última entrega, el contrato queda «rescindido» solo. Hasta entonces la puede dejar sin
  efecto.
- Todas las pruebas de `maestros`, `core` y de las tareas anteriores de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Está en el «Cierre», sección «Verificación a mano» (D-96): los datos se crean a mano, no hay cargador (`comercial/verificacion.py` y `cargar_datos_de_verificacion` se retiraron en D-95 y no vuelven). Hay migraciones nuevas
(`comercial` 0004 y `core` 0031): `python manage.py migrate`.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (rama `feature/com-03b-suministros-modificar-rescindir-y-pre-reservar`, 24/11/2026)

- **Migraciones** (ninguna de datos; `sqlmigrate` leído: solo `CREATE`, ningún `DROP`, `DELETE` ni `UPDATE`):
  - `comercial/0004_alerta_comercial`: `AlertaComercial` (D-63) con `alerta` (`OneToOne`, `PROTECT`), `suministro` y `detalle_suministro` (FK nulas), `fecha_periodo` y `cantidad_sin_cubrir`; dos restricciones
    (`alerta_comercial_un_solo_origen`: exactamente una FK de origen; `alerta_comercial_periodo_completo`: `detalle_suministro` ⇔ fecha y cantidad).
  - `core/0031_comercial_suministros_2`: solo `choices` (`modificacion_suministro`, `pre_reserva_periodo`, `rescision_suministro`, `anulacion_rescision`, `cierre_rescision`; SQL vacío).
  - `core/models.py`: `Accion`, `ETIQUETAS` (las claves nuevas de `datos` y de `cambios`), `VALORES_VISIBLES` (`motivo_rescision`) y `ACCIONES_DE_NEGOCIO`. `core/procesos.py`: solo el comentario de la tabla de órdenes.
- **`maestros`** (D-62, punto 1): los cuatro valores nuevos de `Origen` (`entrega`, `suministro`, `detalle_suministro`, `stock_cosechado`) y 2 pruebas nuevas en `test_alerta.py` (ninguna existente cambió).
- **Servicios de `comercial`:**
  - `suministros.py`: `CambioDeDetalle`, `CambiosDeSuministro`, `huella_de`, `datos_de_modificacion`, `resumen_de_modificacion`, `modificar_suministro` (COM-MOD-SUM); `PedidoDeRescision`, `periodos_conservados`,
    `datos_de_rescision`, `rescindir_suministro`, `dejar_sin_efecto_rescision` y `cerrar_rescisiones` (COM-RSC-SUM, COM-ANL-RSC y el paso diario 35); y en la consulta, `aviso_de_rescision`, `hay_historial`,
    `historial_de_cambios`, la alerta en el calendario y las acciones por rol y estado (regla 10).
  - `pre_reserva.py` (nuevo): `pre_reservar_suministros(hoy)` (PROD-PRR-SUM, paso diario 40), el barrido de las alertas vencidas y `enlaces_de_alertas_de_periodo` (D-62).
  - `comprobantes.py`: `enviar_comprobante(contrato, tipo=None, cambios=None)` (modificación, rescisión y rescisión sin efecto cambian el asunto y la introducción del correo); «Reenviar» deduce la constancia de la
    rescisión del estado del contrato. Plantilla del correo con la introducción por hecho y los datos de la rescisión.
  - `apps.py`: el tipo de alerta `comercial_periodo_sin_cobertura`, su enlace (`registrar_enlace_de_alerta`) y los pasos diarios 35 y 40.
- **Pantallas:** «Modificar suministro» (contrato, detalles vigentes con «Sin cambios / Modificar / Terminar» y «Rige desde», detalles nuevos y panel «Cambios»; recálculo HTMX solo en botones; ventana de resumen y página sin
  JavaScript), «Rescindir suministro» y «Dejar sin efecto la rescisión» (ventanas con su página sin JavaScript), «Ver historial de cambios» (ventana), y la ficha con el aviso de la rescisión, los botones por rol y estado y
  «Sin cobertura completa · faltan N» también con alerta. Vistas en `views_suministros.py`.
- **Disparadores** que se cumplieron (para tachar, M3): «Cuando se programen COM-03b y COM-04» (parte COM-03b: los períodos posteriores a la rescisión y la alerta en el calendario). Los de COM-03 que ya estaban
  planificados («Cuando exista Entrega», puntos 5 y 6, y «Resolución de un contrato con rescisión acordada») **nacen** con esta tarea, como pedía su paso 8. Nace uno: el de la rescisión después de una modificación (ver los desvíos).
- **Estado de paso:** (1) hasta COM-04a, la pre-reserva toma solo detalles «vigentes» (D-64 punto 8): si una modificación ocurre antes de la corrida del día, el período que entra hoy en la ventana del detalle
  finalizado queda sin reservar; la alerta no existe todavía y el calendario lo muestra «Reservado». (2) Hasta COM-05a1 y COM-06 el cierre de una rescisión no espera las entregas a realizar.

**Pruebas** (M1; comandos de «Hecho cuando»)

- `manage.py test comercial maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **2958 pruebas, OK**.
- `manage.py test comercial --keepdb --tag concurrencia`: **43 pruebas, OK** (27 de antes y 16 nuevas).
- `makemigrations --check --dry-run`: sin cambios; `manage.py check`: sin problemas; `proceso_diario --listar`: «10 · revisar_vencimientos», «35 · cerrar_rescisiones» y «40 · pre_reservar_suministros».
- Nuevas: `test_com_mod_sum.py` (82), `test_prod_prr_sum.py` (42), `test_pre_reserva_concurrencia.py` (6), `test_com_rsc_sum.py` (48), `test_com_anl_rsc.py` (19), `test_recorrido_modificacion_y_rescision.py` (1).
  Ampliadas: `test_com_cns_sum.py` (+21), `test_modelos_suministros.py` (+7), `test_suministros_vistas.py` (+27), `test_suministros_concurrencia.py` (+10), `test_alerta.py` de `maestros` (+2).
- **Pruebas existentes reescritas** (para anotar en el PR; ninguna se borró ni se debilitó: cambió la regla, y las dos las aprobó el estudiante):
  - `test_com_cns_sum.py`: `test_regla_10_las_acciones_de_la_ficha_son_solo_las_que_existen_en_com_03a` → `…_sin_las_de_otras_tareas`: «Modificar» y «Rescindir» ahora existen; se mantienen prohibidos «Registrar cobro» y lo que todavía no corresponde.
  - `test_suministros_vistas.py`: `test_regla_ningun_boton_lleva_a_un_403`: la ficha propia del Vendedor ahora **sí** ofrece «Modificar suministro» (antes afirmaba que no); sigue sin «Rescindir», «Dejar sin efecto», «Ver historial» ni «Registrar cobro», y ningún enlace da 403.

**Decisiones:** ninguna nueva de equipo (`D-NN`). Aplicadas D-14, D-27, D-28, D-29, D-36, D-37, D-41, D-42, D-44, D-54, D-56, D-57, D-59, D-60, D-61, D-62 (con su tercera enmienda), D-63, D-64 (punto 8, **diferido**) y D-67 (punto 2).
Las decisiones de aplicación que aprobaste con el plan y los desvíos (para `docs/temas_abiertos.md`; no los corregí en silencio):

1. **D-64, punto 8 queda para COM-04a** (decisión del estudiante, 24/11/2026): la pre-reserva toma solo detalles «vigentes». `pre_reserva.md` y la sección 7 del patrón de stock ya lo dicen («desde COM-04»).
2. **Enlace del Agrónomo = la ficha del invernadero, explícito** (`maestros:invernadero`). La segunda enmienda de D-62 hace del detalle de la alerta el enlace *por omisión*; `pre_reserva.md` decía «la ficha del invernadero (enlace por omisión)». Se
   devuelve explícito para cumplir la tarea, y la campana pasa por `alertas:ir`. El Gerente va a la ficha del suministro con `#calendario`. Para cualquier otro rol, nada (queda el de omisión).
3. **Un comprobante del estado actual, sin columnas nuevas:** el correo cambia asunto e introducción según el hecho; la página imprimible y «Reenviar» muestran el contrato como está hoy. «Reenviar» deduce la constancia de la
   rescisión de `motivo_rescision`; **después de dejar la rescisión sin efecto no queda ninguna marca**, así que reenvía el comprobante de siempre (la constancia de «rescisión sin efecto» pendiente no se reenvía).
4. **2a de COM-RSC-SUM:** sin períodos conservados, `fecha_ultima_entrega_rescision` y `fecha_rescision` valen hoy (la restricción `suministro_rescision_completa` exige la fecha; el modelo dice «la del registro si no había ninguna»).
5. **Rescisión después de una modificación (nace un disparador):** `periodos_conservados` mira solo los detalles **vigentes**, como dice `suministro.md`. Los períodos de la ventana que quedaron en el detalle
   finalizado por una modificación (y que todavía se entregan) no cuentan: un contrato así puede quedar «rescindido» en el acto con entregas pendientes del detalle anterior. Lo resuelve «el cierre espera las entregas a realizar» de COM-05a1 y COM-06.
6. **`huella` y `conservados` en `None` no se comparan** (`rescindir_suministro`, `dejar_sin_efecto_rescision`): lo usan las pruebas de concurrencia para armar un contrato rescindido.
7. **D-63, punto 4 (Vendedor sin invernaderos activos):** el aviso al Vendedor y al Gerente sale **una sola vez** por texto (si ya recibieron ese texto no se repite: la ejecución es diaria).
8. **«Se resuelve al llegar su fecha»:** al empezar la corrida del día siguiente, una consulta resuelve las alertas con `fecha_periodo < hoy`, cada una en su transacción y con su registro `pre_reserva_periodo` (`alertas_resueltas = "1"`).
9. **`asignar` lee `stock.hoy()` por su cuenta:** con `proceso_diario --fecha` la cosecha programada usa la fecha real de hoy, no la simulada (código de COM-02, no se tocó).
10. **Un solo período, una transacción:** en la concurrencia, «pre-reserva primero» solo garantiza el primer período; el segundo puede quedar detrás de una modificación o rescisión que llegue en el medio.
11. **Quién cambia el Vendedor:** un Vendedor que manda `vendedor` distinto del actual recibe `PermissionDenied` (los documentos dicen «solo el Gerente» sin decir cómo se rechaza); mandar el actual no es un cambio.
12. **Detalle que no tiene ningún período hasta la nueva fecha de fin** (acortar la duración): pasa a «finalizado» con `fecha_fin_detalle` = la nueva fecha de fin (el caso de uso solo cubre «su último período»).
13. **Precio propuesto del sucesor:** lo que valdría hoy el detalle actual en la fecha desde la que rige; un precio igual al propuesto no es un cambio, y un detalle «Modificar» sin ningún dato distinto es `detalle_sin_cambios`.
14. **Códigos y campos de error** (los usan COM-04, COM-05 y COM-07): modificar: `contrato_cambio`, `rescision_acordada`, `ventana_cambio`, `sin_cambios`, `detalle_sin_cambios`, `detalle_sin_periodos_posteriores`, `rige_desde_invalido`,
    `tolerados_menores_que_acumulados`, `fin_anterior_a_la_ventana`, `par_vigente`, `accion_invalida` y los de COM-PCT-SUM; campos `modificar-<id>-<campo>` y `detalle-<i>-<campo>`. Rescindir: `motivo_obligatorio|invalido`,
    `descripcion_obligatoria|larga`, `fecha_obligatoria|invalida|futura`, `acuerdo_sin_confirmar`, `ventana_cambio`, `contrato_cambio`, `rescision_acordada`. Dejar sin efecto: `motivo_obligatorio|largo`, `contrato_cambio`,
    `sin_rescision`, `rescision_cerrada`.
15. **Fuera de lo que decía «Permitido fuera de la app»:** nada de `maestros` (salvo `Origen` y su prueba), `produccion` ni `inventario`. En `core/models.py`, además de `Accion`, `ETIQUETAS` y `ACCIONES_DE_NEGOCIO` se tocó `VALORES_VISIBLES` (como pedía el
    «Permitido»); `maestros/extensiones.py` no se tocó.
16. **La tarea nombraba `comercial/verificacion.py` y el cargador** de datos de verificación: se ignoraron (D-95 y D-96).

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `summod`, `ACT['summod-ok']` | Guardaba directo | Ventana de resumen (y página sin JavaScript) con cada cambio y la fecha desde la que rige; «Confirmar cambios» y «Volver a la carga» | Pasos 8 y 9; «Lo que difiere del prototipo», fila 1 |
| `summod` | No dejaba cambiar el mecanismo ni la tolerancia, ni elegir desde qué período rige | Los tres, con «Rige desde» (los períodos posteriores a la ventana) y el precio propuesto | Postcondición a (decisión I) y 5a; fila 8 |
| `summod` | Terminar el último detalle: sin aviso | «Equivale a terminar el contrato» y «Acortar la duración hasta el dd/mm/aaaa» | 5c.1a; fila 9 |
| `summod` | Los datos del cliente editables en apariencia | Cliente y fecha de realización como texto con «No se modifican…» | 5g |
| `summod` | Re-dibujaba al tipear y validaba | Solo «Actualizar» y los botones redibujan, sin validar; el primer botón oculto es «Actualizar» | `.claude/rules/interfaz.md` |
| `summod` | Sin estado de paso entre pantallas | La huella del contrato y la propuesta de «rige desde» viajan ocultas; si cambiaron, vuelve a la ficha (10b) o al formulario con las fechas nuevas (10a) | 10a y 10b |
| `MODALS.sumhist` | (Historial de condiciones en la ficha) | Ventana «Historial de cambios» con los tramos (desde, hasta, cantidad, precio, estado), también como ficha con la ventana abierta sin JavaScript | Regla 5 de COM-CNS-SUM |
| `MODALS.sumrsc`, `ACT['sumrsc-ok']` | Rescindía con un clic y sin acuerdo con el cliente | Motivo de lista cerrada (con descripción obligatoria en «Otro»), fecha del acuerdo y casilla «Confirmo que la rescisión se acordó con el cliente»; presenta los períodos que se conservan y la última entrega | Paso 3 y 4a; regla «Rescisión por mutuo acuerdo» |
| `MODALS.sumrsc` | Sin el caso sin períodos | «El contrato queda rescindido en el momento de confirmar» | 2a |
| `MODALS.sumrscanl` | Sin motivo obligatorio ni límite | Motivo obligatorio (hasta 500), con el error junto al campo | Regla 1 de COM-ANL-RSC |
| `VIEWS.sum` (reemplazo) | Botones sin condición | «Modificar», «Rescindir» y «Dejar sin efecto la rescisión» solo si la persona puede y el estado lo permite (esta última, hasta la última entrega: no lleva a un error); aviso de la rescisión y «Ver historial» solo con cambios | Regla 10; D-30 |
| `tabContratos` (reemplazo) | Marca de la rescisión | La marca «Rescisión acordada» en la lista y el filtro «Rescindido» | Regla 2 y lista de COM-CNS-SUM |
| `VIEWS.sum` (calendario) | Sin alertas | «Sin cobertura completa · faltan N» también con la alerta activa | Regla 6 |

**Recorrido y verificación** (D-96: Claude Code hace el recorrido y la revisión de migraciones; el estudiante verifica a mano con los pasos de más abajo)

*Recorrido* (`comercial/tests/test_recorrido_modificacion_y_rescision.py`, `RecorridoDeModificacionYRescisionTests`): (1) `proceso_diario --solo pre_reservar_suministros` pre-reserva los dos períodos de la ventana de dos
contratos; (2) el Vendedor modifica uno (formulario, resumen con la huella y la propuesta en campos ocultos, confirmación sin JavaScript): el detalle pasa a «finalizado», nace su sucesor, lo reservado no cambia;
(3) la ficha muestra «Con cambios desde» y el historial; el Agrónomo recibe 403 en las cuatro pantallas nuevas; (4) el Gerente rescinde el otro (sin la casilla no se registra; con ella, sí) y la ficha cambia de botones; (5) el Vendedor ya
no ve botones y la pantalla de modificar lo devuelve a la ficha con el motivo; (6) el Gerente deja la rescisión sin efecto (motivo obligatorio) y el contrato vuelve a poder modificarse; (7) la rescinde otra vez y
`proceso_diario --fecha <día siguiente> --solo cerrar_rescisiones` lo pasa a «rescindido» (aviso, sin botones, filtro de la lista); (8) un registro de auditoría por hecho.

*Migraciones*: `makemigrations --check` sin cambios; `sqlmigrate comercial 0004` leído (solo `CREATE TABLE` con sus restricciones, claves foráneas e índices) y `core 0031` (sin SQL); aplicadas en la base de pruebas (recreada una vez, con tu autorización); `manage.py check` sin problemas.

**Verifiqué:** el recorrido (con su resultado: OK), las migraciones (arriba) y los dos comandos de pruebas de «Hecho cuando» (2958 y 43, OK), `proceso_diario --listar`. Además, que las pruebas de concurrencia (43) se pueden correr de punta a punta con los bloqueos nuevos.

**Lo cubre una prueba:** modificar (`test_com_mod_sum.py`: una por postcondición, extensión y regla de la tarea; concurrencia en `test_suministros_concurrencia.py`); la pre-reserva, la alerta y su enlace (`test_prod_prr_sum.py`, `test_pre_reserva_concurrencia.py`);
rescindir, dejar sin efecto y el cierre (`test_com_rsc_sum.py`, `test_com_anl_rsc.py`, concurrencia); la consulta, el historial y las acciones (`test_com_cns_sum.py`); las pantallas, los permisos y el flujo con y sin HTMX
(`test_suministros_vistas.py`, clases `ComModSumVistaTests` y `ComRscSumVistaTests`); el modelo (`test_modelos_suministros.py`); el flujo completo (`test_recorrido_modificacion_y_rescision.py`).

**No pude verificar:**
- El envío real de un correo (las pruebas usan `enviar_correo` simulado): con SMTP real, que lleguen el comprobante de la modificación y las constancias de rescisión y de rescisión sin efecto, y que se lean bien.
- Que Render aplicó `comercial/0004` y `core/0031` (log del despliegue) y que las pantallas abren en producción (Neon).
- Lo que solo un navegador real ve (CSRF y `Origin`, JavaScript y HTMX, aspecto, celular): va en el paso «Navegador real» de la «Verificación a mano».
- La campana del **Gerente** con una alerta real: con un Agrónomo activo la alerta va solo al Agrónomo (regla 1 de 8.9); la del Gerente (a la ficha del suministro) la prueba `EnlaceDeAlertaTests`, pero hacerla aparecer a mano exige que el invernadero no tenga Agrónomo activo.
- Criterio de producto: si el formulario de modificar (con varios detalles) se siente cómodo y si un preaviso igual a la ventana de pre-reserva (14 días) es aceptable para el Jardín Botánico (tema abierto de COM-MOD-SUM y COM-RSC-SUM).

**Verificación a mano** (para el estudiante, autocontenida; se copia a `docs/revisiones_pendientes.md`, M5)

*Antes de empezar.* Con el entorno virtual activo: `python manage.py migrate` (aplica `comercial` 0004 y `core` 0031) y `python manage.py runserver`; abrí `http://127.0.0.1:8000/`. No hay datos cargados: hay que crearlos a mano, en este orden.
(1) Con el Gerente, en «Usuarios y seguridad», creá un Agrónomo, un Capataz y dos Vendedores (el segundo, para el paso 11); la contraseña es la que definas. (2) En «Producción», creá un invernadero con ese Agrónomo, ese Capataz y el
primer Vendedor, sus sectores y una variedad («Lechuga Crespa») con su ciclo; sembrá y avanzá un lote hasta «Maduración» con **300 plantas** (como en las rondas de producción). (3) En «Comercial» › «Clientes», creá «Verdulería Los Pinos
S.R.L.» (CUIT de ejemplo 30-71234567-1) con correo (`compras@lospinos.com`) y dos direcciones («San Martín 123, Garupá» y «Belgrano 45, Garupá»), y «Verdulería El Sol S.R.L.» (CUIT 30-71234568-9) con correo y una dirección. (4) En «Configuración», la
pre-reserva de suministros en 14 días (viene así). (5) Con el primer Vendedor, en «Comercial» › «Contratos» › «Suministros» › «Pactar suministro», pactá **dos suministros**: **SUM-A** para «Los Pinos»: duración 6, tolerados 3, multa 50000, plazo de pago 15,
indemnización por atraso 100; detalle 1: Lechuga Crespa, San Martín, 30 plantas cada 7 días, primera entrega dentro de 3 días, precio fijo 1500, tolerancia 1, retraso 100, mínima 10, faltante 50; detalle 2: Lechuga Crespa, Belgrano, 20 plantas cada 14 días, primera entrega
dentro de 5 días, ajuste periódico de 1000 con 3 % cada 2 meses, tolerancia 1, retraso 100, mínima 5, faltante 50. **SUM-B** para «El Sol»: mismos datos del contrato, un detalle de 10 plantas cada 7 días, primera entrega dentro de 3 días, precio fijo 1500
(cláusula igual a la del detalle 1). Los dos reservan sus períodos de la ventana al pactarse. Entrá con el primer Vendedor.

1. **Los pasos diarios.** En una terminal: `python manage.py proceso_diario --listar`: tienen que verse «35 · cerrar_rescisiones · Cerrar rescisiones de suministros» y «40 · pre_reservar_suministros · Pre-reservar suministros». Después
   `python manage.py proceso_diario --solo pre_reservar_suministros --fecha <hoy + 7 días, aaaa-mm-dd>`: dice «procesados 3 · creados …» (los períodos que entran en la ventana con esa fecha: el día 17 de cada detalle de 7 días y el 19 del de 14). Cada uno queda reservado o, si el lote todavía no llega a cosechar para esa fecha, con su alerta (paso 8).
   Corrélo otra vez con la misma fecha: no crea reservas, alertas ni avisos nuevos. *(lo cubre `ProdPrrSumServicioTests`)*
2. **Modificar (camino feliz).** En la ficha de SUM-A: botón verde «Modificar suministro». En el detalle 1, marcá «Modificar», dejá «Rige desde» en la primera fecha que ofrece (el primer período posterior a la ventana) y poné **cantidad 40**. A la derecha, «Cambios»
   dice «Lechuga Crespa: cantidad por período: de 30 a 40. Rige desde el dd/mm/aaaa». «Guardar cambios»: la ventana con el resumen. «Confirmar cambios»: vuelve a la ficha con «SUM-… modificado.» y el calendario: los períodos hasta la ventana siguen con 30 («Reservado») y
   los siguientes con 40; el detalle muestra «Con cambios desde el dd/mm» y aparece «Ver historial de cambios» (tramos: «Rigió desde … hasta …» y el nuevo, «fin del contrato»). Con el Gerente, «Auditoría»: un registro «Modificación de suministro». *(lo cubre el recorrido)*
3. **Elegir desde cuándo rige.** Modificá otra vez el detalle 1 (cantidad 45) y en «Rige desde» elegí una fecha **posterior** a la primera: los períodos intermedios siguen con 40. *(prueba: `test_ext_5a_…`)*
4. **Errores.** En «Modificar»: cantidad 0 → «Ingresá un número entero de plantas, de 1 a 500.000.» junto al campo; tolerados 100 → «Ingresá un número entero, de 0 a 99.» (con incumplimientos acumulados, un valor menor que ellos da «No puede ser menor que…»; con 0 acumulados no se
   puede probar: anotalo); duración 0 o 121 → «Ingresá un número entero de meses, de 1 a 120.» (acortar por debajo del último período reservado, «La fecha de fin más cercana posible es el dd/mm/aaaa.», necesita un contrato pactado hace más de un mes: lo cubre la prueba). «Guardar cambios» sin tocar nada: «No indicaste ningún cambio.» *(lo cubre la prueba de cada regla)*
5. **Terminar y acortar.** Marcá «Terminar» en el detalle 2: el panel dice «Se termina … Sin multa: es de mutuo acuerdo.». Marcá «Terminar» también en el 1: aparece «Equivale a terminar el contrato…» y el botón «Acortar la duración hasta el dd/mm/aaaa»; tocalo: la duración baja
   a 1 mes. No confirmes. *(prueba: `test_ext_5c_1a_…`)*
6. **Detalle nuevo.** «Agregar detalle»: variedad Lechuga Crespa, dirección **Belgrano**, 20 plantas cada 30 días, primera entrega dentro de 5 días, precio 1500, cláusula cualquiera válida. Como Belgrano ya la usa el detalle 2: «Guardar cambios» da «El contrato ya tiene Lechuga Crespa para esa dirección: modificá ese detalle.».
   Cambiá a San Martín: lo mismo con el detalle 1. Quitá el detalle nuevo con «Quitar».
7. **Dos pestañas.** Abrí «Modificar» en dos pestañas del mismo contrato; en la primera cambiá los tolerados a 5 y confirmá; en la segunda cambiá la multa y confirmá: vuelve a la ficha con «El contrato cambió mientras lo modificabas (por ejemplo, se resolvió o lo modificó otra persona). Volvé a abrirlo.» y no se registra nada.
8. **Alerta de período sin cobertura.** Con el Gerente, «Comercial» › «Contratos» › «Compra-ventas» › «Registrar compra-venta» con retiro en ese invernadero que reserve **todo el stock libre** de Lechuga Crespa (el formulario muestra lo disponible). Después, en la terminal:
   `python manage.py proceso_diario --solo pre_reservar_suministros --fecha <hoy + 14 días>`: dice «N períodos siguen sin cobertura completa». Con el **Agrónomo**: la campana tiene «Período sin cobertura completa · Lechuga Crespa · Verdulería… · dd/mm» y, debajo, «Faltan N plantas para el dd/mm»; al tocarla
   se abre la ficha del invernadero y la alerta pasa a «leída». Con el **Vendedor**: la campana de notificaciones trae «SUM-…: el período del dd/mm de Lechuga Crespa quedó sin cobertura completa. Faltan N plantas. InfoPonia vuelve a intentar cada día.». En la ficha del suministro, el período dice
   «Sin cobertura completa · faltan N». Corré el mismo comando otra vez: no hay alertas ni avisos repetidos. Con `--fecha <hoy + 25 días>` las alertas de los períodos que ya pasaron se resuelven solas. *(lo cubren `SinStockTests` y `EnlaceDeAlertaTests`)*
9. **Rescindir (Gerente).** En la ficha de SUM-B, «Rescindir suministro»: la ventana dice los períodos que se conservan, «la última entrega es el dd/mm/aaaa», «no lleva multa ni indemnización». Probá: «Registrar rescisión» sin elegir motivo (error), con motivo «Otro» sin descripción («Con el motivo «Otro», contá cuál fue.»), con fecha de
   acuerdo de mañana («No puede ser posterior al…») y sin la casilla («Confirmá que la rescisión se acordó con el cliente…»). Después motivo «A pedido del cliente», fecha de ayer, con la casilla: vuelve a la ficha con «rescisión registrada. Se entrega hasta el dd/mm/aaaa.»; la ficha dice «Rescisión acordada el … Se entrega hasta el …», no ofrece
   «Modificar» ni «Rescindir», sí «Dejar sin efecto la rescisión»; el calendario termina en la última entrega; la lista marca «Rescisión acordada»; la campana del Vendedor trae «El Gerente registró la rescisión de SUM-… por mutuo acuerdo…». *(lo cubre el recorrido)*
10. **Dejar sin efecto y cerrar.** «Dejar sin efecto la rescisión»: sin motivo, error; con motivo, vuelve a la ficha con «la rescisión quedó sin efecto», el calendario completo y el botón «Modificar suministro». Rescindí de nuevo y corré `python manage.py proceso_diario --solo cerrar_rescisiones --fecha <el día siguiente a la última entrega>`:
    el suministro queda «Rescindido» («Rescindido por mutuo acuerdo (acordado el …). La última entrega fue el …»), sin botones, y aparece en la lista con el filtro «Rescindido». Con el correo del sistema sin configurar, el aviso dice que la constancia quedó pendiente: «Reenviar comprobante» en la ficha. *(lo cubre el recorrido)*
11. **Roles.** Entrá con el segundo Vendedor y escribí en la barra `/comercial/contratos/suministros/<id de SUM-A>/modificar/` y `/historial/`: 403; con el primer Vendedor, `/comercial/contratos/suministros/<id>/rescindir/` y `/dejar-sin-efecto-rescision/`: 403 (solo el Gerente); con el Agrónomo, las cuatro: 403.
    La ficha del primer Vendedor no muestra «Rescindir suministro». *(lo cubre `ComModSumVistaTests` y `ComRscSumVistaTests`)*
12. **Navegador real (D-96).** Abrí el sistema en una **ventana privada**, entrá con el Vendedor y modificá un suministro **hasta el final**: «Modificar suministro», «Guardar cambios» y «Confirmar cambios»; después, con el Gerente, «Rescindir suministro» hasta «Registrar rescisión» y «Dejar sin efecto la rescisión». Cada paso tiene que mostrar la
    ficha o la ventana esperada, sin «Prohibido (403)», sin «Verificación CSRF fallida» y sin errores en la consola del navegador (F12). Si aparece alguno, avisá: lo más probable es un encabezado que el cliente de Django no ve. Probá también que las ventanas se cierran con «Volver» y con Escape.
13. *(opcional)* **Sin JavaScript** (desactivalo en el navegador): modificar funciona con «Actualizar», el resumen es una página y las ventanas de rescindir, dejar sin efecto e historial son la ficha con la ventana abierta. **En un celular** (ancho de 390 px): el formulario de modificar, las ventanas y la ficha no se desbordan.
14. *(después del merge)* En el log de Render, que se aplicaron `comercial/0004_alerta_comercial` y `core/0031_comercial_suministros_2`, y en la «Shell»: `python manage.py proceso_diario --listar` muestra los pasos 35 y 40.

*Lo que ya cubre el recorrido*: los pasos 1, 2, 9 y 10 (con el cliente de Django); si tenés poco tiempo, concentrate en el 8 (alerta y campana), el 4 (errores), el 7 (dos pestañas) y el 12 (navegador real).
