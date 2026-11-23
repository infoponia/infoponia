# COM-03b · Suministros: modificar, rescindir, dejar sin efecto la rescisión y pre-reservar (pasos 35 y 40)

Estado: pendiente | App: comercial (y los orígenes de alertas en maestros, D-62) | Rama: feature/com-03b-suministros-modificar-rescindir-y-pre-reservar | Ronda: Comercial 1

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

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

Hay migraciones nuevas (`comercial`, `core`): `python manage.py migrate`. Datos: los de la verificación de COM-03a, con `SUM-0001` pactado
(dos detalles, uno con ajuste periódico).

1. `python manage.py proceso_diario --listar`: aparecen los pasos 35 y 40. `python manage.py proceso_diario --fecha <hoy + 7>`: se reservan
   los períodos que entran en la ventana; si no alcanza, el Agrónomo ve «Período sin cobertura completa» en la campana y el Vendedor la
   notificación. Corrélo otra vez con la misma fecha: nada nuevo.
2. Con el Gerente, la campana: la alerta lleva a la ficha de `SUM-0001`, al calendario. Con el Agrónomo: lleva a la ficha del invernadero.
3. «Modificar suministro»: en el detalle 1, «Modificar», 180 plantas. Dice desde qué fecha rige (el primer período después de la ventana);
   elegí uno posterior en «Rige desde». «Guardar cambios», resumen, confirmá. La ficha muestra «Con cambios desde el …» y «Ver historial».
4. Intentá bajar los tolerados por debajo de los acumulados (con 0 acumulados no se puede probar: anotalo); terminá el detalle 2: «Se entrega
   por última vez el …». Terminá el 1 también: aparece «Equivale a terminar el contrato» y «Acortar la duración».
5. Abrí «Modificar» en dos pestañas; guardá en una y después en la otra: «El contrato cambió mientras lo modificabas».
6. Con el Gerente, en `SUM-0001`: «Rescindir suministro». La ventana dice cuántos períodos se entregan y la fecha de la última. Elegí
   «Otro» sin descripción: error; sin la casilla de confirmación: error. Registrá: la ficha muestra «Rescisión acordada…», no aparece
   «Modificar», el calendario termina en la última entrega y el cliente recibió la constancia. «Dejar sin efecto la rescisión»: vuelve todo.
   Rescindí otra vez y corré `python manage.py proceso_diario --fecha <día siguiente a la última entrega>`: el contrato queda «Rescindido».
7. Sin JavaScript, la modificación y la rescisión funcionan con «Actualizar» y el resumen como página.
8. Después del merge: en Render, desde la «Shell», `python manage.py proceso_diario --listar` y revisar en el log que se aplicaron las
   migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
