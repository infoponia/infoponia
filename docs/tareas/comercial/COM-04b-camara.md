# COM-04b · Cámara: asignación automática, vencimiento y merma en cámara (pasos 20 y 25)

Estado: pendiente | App: comercial (y un parámetro en maestros) | Rama: feature/com-04b-camara | Ronda: Comercial 1

Depende de: **COM-04a** (el núcleo de `produccion`, con las funciones de cámara ya hechas y probadas, y las cosechas). Si no está mergeada,
frená. Esta tarea **no** toca `produccion`.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda parte de COM-04 (D-67, punto 2): la **cámara** asigna sola su stock libre a quien lo espera (PROD-ASG-CAM, con
el `on_commit` de cada caso de uso que crea o libera una partida y la recuperación del **paso diario 25**), avisa antes de que una partida
venza y da de baja lo vencido (PROD-VNC-CAM, **paso diario 20**), y el Capataz o el Agrónomo registran la **merma en cámara** (PROD-REG-MRM,
4a y 10c), que recorta las reservas en el orden de la regla. Trae la pestaña «Cámara» de la ficha del invernadero y el parámetro «Aviso de
vencimiento de cámara».

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-ASG-CAM | Asignar Stock de Cámara (y el paso diario 25) | docs/casos_de_uso/produccion/camara.md | Anular el enlace del detalle que se cubre: COM-04c. «Sin entrega» y paso 9: COM-05a1 |
| PROD-VNC-CAM | Vencer Partidas en Cámara (paso diario 20) | docs/casos_de_uso/produccion/camara.md | Asiento: fuera, D-57. El enlace del camino de faltante (3a.2a): COM-04c. Entregas de la 3a: COM-05a1; 3b: COM-06 |
| PROD-REG-MRM | Registrar Merma (partida en cámara: 4a y 10c) | docs/casos_de_uso/produccion/merma.md (sección «Comercial 1») | Asiento (i): fuera, D-57. El enlace de 10c: COM-04c. «Daño en la entrega»: COM-06 |
| PROD-CNC-CSC y PROD-CNL-ORD (cosechas) | Lo que completa: el `on_commit` de PROD-ASG-CAM (postcondiciones k y h) | docs/casos_de_uso/produccion/cosecha.md y cancelar_orden.md | La base es de COM-04a |

## Leer

- Casos de uso: docs/casos_de_uso/produccion/camara.md **completo** (con «Cambios ya decididos», «Cómo se aplica», «Pantallas» y «Lo que
  difiere del prototipo»); de docs/casos_de_uso/produccion/merma.md, la sección «Comercial 1»; de cosecha.md, el punto 8 de «PROD-CNC-CSC» en
  «Cómo se aplica» (la postcondición k); de cancelar_orden.md, «Comercial 1»: cosechas, el punto 6 del registro (postcondición h); de
  faltante.md, solo «El camino de faltante».
- Modelo: docs/modelo/produccion.md (StockCosechado, MovimientoStock, Merma), docs/modelo/comercial.md (ReservaStock, DetalleReserva,
  **AlertaComercial**), docs/modelo/maestros.md (ConfiguracionOperativa, el parámetro nuevo).
- Decisiones: **D-64** (puntos 7, 9 y 10), D-59, D-61, D-62, D-63, D-56, D-14, D-27, D-36, D-37, D-40, D-41, D-42, D-44, D-57; **D-67,
  punto 2**.
- Patrones: docs/patrones/stock_maduro.md, **sección 8** (asignación de cámara y recorte), docs/patrones/bloqueos.md (sección `comercial`,
  «Cosecha y cámara»), docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»: el parámetro choca con los del IoT).
- API: docs/api/produccion.md, sección 8 (las funciones de cámara que usás; no las cambies); docs/api/alertas.md (secciones 1, 2, 4 y 8);
  docs/api/notificaciones.md; docs/api/extensiones_de_maestros.md (pestaña del invernadero); `core/procesos.py` (su encabezado).
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `camaraTab`, `tabCamara`, `VIEWS.cfg` (el parámetro), el grupo de
  cámara de `secCosecha`; la merma: `VIEWS.merma` de docs/prototipos/produccion/ (la opción «Pérdida en cámara» no está en el prototipo
  comercial, D-61).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-04a): `servicios/` (`stock_maduro.py`, `cosechas.py`, `faltantes.py`, `pre_reserva.py`), vistas,
    plantillas, `apps.py`, fábricas, `verificar_invariantes_de_reservas`;
  - `produccion/servicios/camara.py` y `mermas.py`, la pantalla de merma de PRD-03 y su vista;
  - `maestros/models.py` (`ConfiguracionOperativa`), `maestros/servicios/configuracion.py` y la pantalla de configuración,
    `maestros/servicios/alertas.py`, `maestros/extensiones.py`;
  - `core/procesos.py`, `core/notificaciones.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos: en `comercial`, `AlertaComercial.partida` con la restricción «exactamente un origen» reescrita (D-63); en `maestros`, el
  campo `dias_aviso_vencimiento_camara` (MD-134).
  → revisá docs/disparadores.md: cierra «Cuando se retome la cámara de frío (D-45)» y la parte de la cámara de «Cuando exista Lote,
  OrdenTrabajo o StockCosechado» (la pestaña) (paso 7).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_camara.py`: `AlertaComercial.partida` y su restricción reescrita;
  - `maestros/migrations/00NN_dias_aviso_vencimiento_camara.py`: el parámetro, con el valor inicial 3 para la fila existente (es un
    `AddField` con `default`, no una migración de datos);
  - `core/migrations/00NN_comercial_camara`: solo `choices` (acciones `asignacion_camara`, `vencimiento_partida`,
    `aviso_partida_por_vencer`; `registro_merma` ya existe).
- Permitido fuera de `comercial`:
  - `maestros`: el campo `dias_aviso_vencimiento_camara`, su formulario y su texto en la pantalla de configuración;
  - la pantalla de merma de `produccion` (PRD-03): la opción «Pérdida en cámara» que muestra la de `comercial` por el punto 4 de
    `produccion/extensiones.py` (que creó COM-04a). **Nada más de `produccion`**;
  - `core`: en `core/models.py`, las acciones, `ETIQUETAS`, `VALORES_VISIBLES` (las causas nuevas de `Merma`) y `ACCIONES_DE_NEGOCIO`; en
    `core/procesos.py`, solo el comentario (fila 25);
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: **COM-04c** (el enlace del cliente, COM-DCD-FLT y el paso 27: el camino de faltante sigue sin enlace); las entregas
  (COM-05a1: «sin entrega» de los candidatos, el paso 9 de PROD-ASG-CAM, las entregas de PROD-VNC-CAM y de la merma en cámara); rutas y
  «daño en la entrega» (COM-06); los asientos (D-57).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, parámetro y auditoría.** `AlertaComercial.partida` y la restricción; el parámetro de `maestros`; las acciones.
   Pruebas: en `comercial/tests/test_modelos_cosecha_camara.py`, métodos nuevos (la restricción); la de `maestros` del parámetro (rango y
   valor inicial).
2. **Recorte** (patrón de stock, sección 8): `orden_de_recorte` (pura) y la función que recorta las líneas de una partida hasta su nueva
   disponible.
   Pruebas: `test_recorte.py` (de tabla).
3. **Asignación de cámara** (`camara.md`): `asignar_camara` y el paso 25; los `on_commit` que la disparan desde PROD-CNC-CSC (k) y desde la
   cancelación de una cosecha (h).
   Pruebas: `test_prod_asg_cam.py` (`ProdAsgCamServicioTests`): una por regla, postcondición y extensión (1a, 1b, 2a, 3a, 4a, 5a, 6a, 7a, 7b,
   9a, 10a, 10b, 11a); cada condición de «Candidato», una por prueba (incluido el período fuera de la ventana y el del detalle finalizado);
   el detalle pendiente que se cubre (sin el enlace: su anulación la prueba COM-04c); el paso 25 idempotente y que recupera las partidas que
   dejó COM-04a sin asignar. En `test_prod_cnc_csc.py` y `test_prod_cnl_ord_cosechas.py`, métodos nuevos: la postcondición k y la h con
   `captureOnCommitCallbacks`. Concurrencia: PROD-ASG-CAM contra una compra-venta que toma la misma partida.
4. **Vencimiento** (`camara.md`, PROD-VNC-CAM): `vencer_partidas_en_camara` (paso 20), los dos tipos de alerta, sus enlaces
   (`registrar_enlace_de_alerta`) y `resolver_aviso_de_partida`.
   Pruebas: `test_prod_vnc_cam.py` (`ProdVncCamServicioTests`): una por postcondición (a, c, d, e, f, g) y extensión (\*a, 2a, 3a con abierto,
   pendiente, confirmado y período, 3a.2a sin enlace, 4a); el día de la fecha límite no vence; dos corridas el mismo día no duplican nada; el
   aviso una sola vez y su resolución al agotarse por una merma; `proceso_diario --listar` muestra 20, 25, 35 y 40. Concurrencia:
   PROD-VNC-CAM contra una merma en cámara.
5. **Merma en cámara** (`merma.md`, sección «Comercial 1»): las pruebas de esa sección (con el camino de faltante sin enlace).
6. **Vistas, plantillas y pantallas compartidas.** La pestaña «Cámara» (`registrar_pestana_de_invernadero`); «Registrar merma en cámara» (la
   opción en la pantalla de merma y su página); el parámetro en «Configuración»; los indicadores de cámara del panel del Agrónomo
   (`secCosecha`). Vistas que solo orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript,
   errores por campo, aviso breve (D-29). Antes de tocar la ficha del invernadero y el panel, mirá qué dejaron PRD-01 a PRD-04 y COM-04a
   (criterio de la sección 5 del plan).
   Pruebas: `test_camara_vistas.py`: permisos (cada rol ve lo suyo y ningún botón lleva a un 403); los flujos con HTMX y sin él.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de «Límites» y agregar lo que nace (COM-05a1
   y COM-06: «sin entrega» de los candidatos, entregas de PROD-VNC-CAM, la devolución a una partida vencida, resolver «partida por vencer» al
   entregar); marcar COM-04b en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista
   «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el grupo de cámara del panel del Agrónomo y las partidas cerradas de la pestaña «Cámara»
(quedan en `docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, el recorte de cámara ni las pruebas de
concurrencia.

## Hecho cuando

- La cámara asigna sola su stock libre a quien lo espera (también al día siguiente si algo falló), avisa con «Partida por vencer» y
  `python manage.py proceso_diario` da de baja lo vencido, con su merma y recortando lo reservado.
- Una merma en cámara recorta las reservas en el orden de la regla y vuelve a cubrir lo que puede.
- Todas las pruebas de `produccion`, `maestros`, `core` y de las tareas anteriores de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial produccion maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`maestros` 0011, `comercial` 0006, `core` 0037): `python manage.py migrate`. **No hay datos cargados** (D-95: los cargadores se retiraron): los creás vos, con los valores de abajo. Nunca escribas una contraseña en un archivo del repo.

**Antes de empezar**

1. `.venv\Scripts\Activate.ps1`, `python manage.py migrate` y `python manage.py runserver` (http://127.0.0.1:8000/). Necesitás cuatro cuentas de prueba (las que ya usaste en las verificaciones anteriores): un **Gerente**, un **Agrónomo**, un **Capataz** y un **Vendedor**, los tres últimos asignados al **mismo invernadero activo** (por ejemplo «Invernadero Norte»).
2. Lo que hay que crear a mano, **en este orden** (todo con pantallas que ya existen):
   1. Variedad «Lechuga Crespa» con postcosecha de **7 días** (la que ya usaste en COM-04a sirve) y un sector de Maduración con al menos 200 agujeros en el invernadero.
   2. **Lote A**: 100 plantas en Maduración. **Lote B**: 60 plantas en Maduración (misma variedad). Sembralos y pasalos por las transiciones como en PRD-02, o reutilizá los de la verificación de COM-04a.
   3. Un cliente **con correo** y con una dirección activa (CUIT de ejemplo válido: `20-12345678-6`).
   4. **Agrónomo** › Producción › Órdenes › «Planificar cosecha»: **sin contrato**, invernadero «Norte», fecha de **hoy**, **60 plantas del Lote B**. (Así el Lote B queda reservado y no cubre ventas.)
   5. **Vendedor** › Comercial › Contratos › «Nueva compra-venta»: con **envío**, 100 plantas de Lechuga Crespa, fecha pactada **dentro de 5 días** (la llamamos **V1**). Se programa una cosecha automática del Lote A.
   6. **Capataz** › su bandeja › concretá la cosecha de V1: **cosechá 60** y declará **40 perdidas** (causa «Plaga»). Faltan 40 y no hay stock: V1 queda «pendiente de decisión del cliente» (el enlace del cliente es de COM-04c: todavía no existe).

**Pasos**

1. **Configuración** (Gerente) › Configuración › «Parámetros operativos» › grupo «Comercial». Tiene que aparecer **«Aviso de vencimiento de cámara (días antes)»** con **3** y la ayuda «Con esta anticipación se avisa al Agrónomo y al Vendedor de una partida con stock libre. 0 desactiva el aviso.». Probá `-1` y «Guardar»: error junto al campo «El mínimo es 0.» y no guarda nada. Probá `0` (guarda) y volvé a `3`. En «Auditoría» queda «Modificación de la configuración operativa» con el antes y el después. *Lo cubre una prueba:* `test_adm_mod_cfg`, `test_configuracion_vistas`.
2. **Asignación automática (k)** (Capataz) › bandeja › concretá la **cosecha sin contrato** del paso 4 del apartado anterior (60 plantas del Lote B). Al confirmar nace la partida «P-…» de 60 plantas y, **sin que hagas nada más**, InfoPonia la asigna a V1 (que esperaba 40). Tiene que verse:
   - **Vendedor**: en la campana (Notificaciones) «**Stock de cámara para CV-…**» con «40 plantas de la cámara (P-…)… El detalle dejó de estar pendiente…».
   - **Agrónomo**: «**Partida P-… asignada**» con el contrato y «Stock libre que le queda: 20 plantas».
   - **Gerente** › Auditoría: «Asignación de stock de cámara» (sin usuario: lo hizo InfoPonia).
   - Vendedor › Comercial › V1: el detalle ya no está «pendiente de decisión» (vuelve a «abierto») y la venta a «abierta». Si tenés el correo del sistema configurado, el cliente recibe «el faltante quedó cubierto». *Lo cubre una prueba:* `test_prod_asg_cam` y `test_post_k_*` de `test_prod_cnc_csc`.
3. **Pestaña «Cámara»** (Agrónomo) › Producción › «Invernadero Norte» › pestaña **«Cámara»**. Tres indicadores (Partidas disponibles **1** · 60 plantas; Plantas libres **20**; Por vencer **0** en 3 días o menos) y la tabla: **P-…**, «Lechuga Crespa», lote y motivo «Cosecha planificada por el Agrónomo», ingreso de hoy, fecha límite (hoy + 7), disponible **60**, reservado **40**, libre **20**, estado «Disponible». Aparece el botón «Registrar merma en cámara». Con el **Gerente** la pestaña se ve igual pero **sin** ese botón. El Capataz y el Vendedor no llegan a la ficha del invernadero (403 al escribir la dirección: es la pantalla de Gerente y Agrónomo; queda en `docs/temas_abiertos.md`). *Lo cubre una prueba:* `PestanaDeCamaraTests`.
4. **Paso 25 idempotente.** En una terminal: `python manage.py proceso_diario --listar`: tienen que aparecer, en este orden, **20** «Vencer partidas en cámara», **25** «Reasignar cámara», **35** y **40**. Corré `python manage.py proceso_diario --solo reasignar_camara` dos veces: no se crea ninguna reserva, aviso ni auditoría nuevos (la partida ya cubrió a V1). *Lo cubre una prueba:* `test_regla_paso_25_*`.
5. **Merma en cámara sin recorte** (Capataz) › «Registrar merma». Elegí el invernadero «Norte»: debajo aparece «¿Se perdió producto de la cámara? **Pérdida en cámara**». Entrá. Elegí el invernadero y la partida (el desplegable dice «P-… · Lechuga Crespa · lote … · vence el … · 60 disponibles (20 libres)»; al elegir **no** se mueve la pantalla ni aparecen errores). Escribí **5** plantas, causa «Daño en cámara» (es la única), descripción «Se golpeó la bandeja» y «**Ver resumen**»: partida, 5 plantas, «60 → 55» y **ningún** aviso de contratos. «**Confirmar merma**»: vuelve a tu bandeja con el aviso «La merma quedó registrada…». Agrónomo: la pestaña «Cámara» muestra disponible **55**, reservado 40, libre **15**; en la campana no aparece ninguna alerta. Auditoría: «Registro de merma». *Lo cubre una prueba:* `test_prod_reg_mrm_camara`, `MermaEnCamaraVistaTests`.
6. **Errores por campo** (misma pantalla): cantidad `0` o `99` → debajo del campo «Ingresá un número entero entre 1 y 55 (las plantas disponibles de la partida).»; sin causa → «Elegí la causa de la pérdida.»; descripción de más de 300 caracteres → «La descripción pasa de 300 caracteres.». No se escribe nada. Cambiá un dato **después** de «Ver resumen» y confirmá: avisa «Cambiaste un dato después de ver el resumen» y no registra. *Lo cubre una prueba:* `test_ext_4a_4a_*`, `test_regla_confirmar_con_un_dato_cambiado_*`.
7. **Aviso previo** (terminal). Mirá la fecha límite de la partida en la pestaña (hoy + 7). Corré `python manage.py proceso_diario --fecha AAAA-MM-DD` con **la fecha límite menos 2 días** (hoy + 5). **Agrónomo**: en la campana (Alertas) «**Partida por vencer**»: «Lechuga Crespa · P-…: 15 plantas libres vencen el … (en 2 días)»; al abrirla lleva a la pestaña «Cámara». **Vendedor**: la notificación «Partida por vencer». Corré **el mismo comando** otra vez: no aparece nada nuevo (un solo aviso por partida). *Lo cubre una prueba:* `test_post_f_*` de `test_prod_vnc_cam`.
8. **Merma en cámara con recorte (10c)** (Capataz) › «Pérdida en cámara», la misma partida (55 disponibles, 15 libres), **30** plantas, «Daño en cámara», «Ver resumen». Tiene que decir: «55 → **25**» y, en un cuadro de advertencia, «La pérdida supera el stock libre de la partida (15 plantas): estos contratos pierden producto. **CV-…**: 15 plantas. Se intentará volver a cubrirlos con otro stock…». «Confirmar merma». Después:
   - **Vendedor**: notificación «**Cámara: CV-… perdió producto**» («CV-…: merma en la partida P-… y se perdieron 15 plantas reservadas. Se volvió a cubrir 0 plantas; quedan 15 plantas sin cubrir.»). V1 vuelve a «pendiente de decisión del cliente» (no hay otro stock).
   - **Agrónomo**: alerta «**Merma en cámara con producto reservado**» («Merma en la partida P-… (Lechuga Crespa) con 15 plantas reservadas para CV-…»), que lleva a la pestaña «Cámara».
   - Pestaña «Cámara»: disponible **25**, reservado **25**, libre **0**.
   *Lo cubre una prueba:* `test_ext_10c_*`, `test_ext_9_*`.
9. **El día de la fecha límite no vence** (terminal): `python manage.py proceso_diario --fecha AAAA-MM-DD` con **la fecha límite exacta** (hoy + 7). La partida sigue «**Disponible**» en la pestaña «Cámara» (el día de la fecha límite todavía se entrega) y el aviso sigue activo. *Lo cubre una prueba:* `test_regla_el_dia_de_la_fecha_limite_no_vence`.
10. **Vencimiento (paso 20)** (terminal): `python manage.py proceso_diario --fecha AAAA-MM-DD` con **la fecha límite más 1 día** (hoy + 8). **Pestaña «Cámara»**: la partida queda «**Vencida**» con «Merma por vencimiento: 25 plantas» y disponible 0. **Agrónomo**: la alerta «Partida por vencer» pasa a resuelta y llega una nueva, «Merma en cámara con producto reservado» («Venció la partida P-… (Lechuga Crespa) con 25 plantas reservadas para CV-…»). **Vendedor**: «Cámara: CV-… perdió producto». V1 sigue «pendiente de decisión» con la fecha de hoy. **Gerente** › Auditoría: «Vencimiento de partida en cámara» (sin usuario). Corré el mismo comando **otra vez**: nada nuevo (ninguna merma ni aviso duplicado). *Lo cubre una prueba:* `ProdVncCamServicioTests` y `test_recorrido_camara`.

> Con `--fecha`, el proceso diario corre **todos** los pasos para esa fecha: cualquier otra partida que tengas de verificaciones anteriores (por ejemplo la de 40 plantas de COM-04a) también va a avisar o vencer. Es lo esperado.

11. **Roles y permisos** (opcional pero recomendado). **Gerente**: escribí a mano `/comercial/camara/merma/` → «403». **Vendedor**: lo mismo → 403, y en «Registrar merma» (si entra) no aparece «Pérdida en cámara». Un **Agrónomo ajeno** al invernadero: la pestaña «Cámara» de «Norte» da 403. **Capataz sin partidas** en su invernadero: «Registrar merma» no ofrece «Pérdida en cámara». *Lo cubre una prueba:* `MermaEnCamaraVistaTests.test_regla_solo_el_agronomo_y_el_capataz_asignados_entran`, `EntradaEnLaMermaDeProduccionTests`.
12. **Panel del Agrónomo.** Inicio del Agrónomo: el grupo se llama «**Cosechas y cámara**» y suma «Partidas por vencer» y «Plantas libres en cámara» (las cifras coinciden con las de la pestaña «Cámara»). *Lo cubre una prueba:* `PanelDelAgronomoTests`.
13. **Sin JavaScript** (opcional): desactivá JavaScript en el navegador y repetí el paso 5: cada desplegable queda con «Continuar» (dentro del formulario) que redibuja sin validar; «Ver resumen» y «Confirmar merma» funcionan como páginas.
14. **Celular** (opcional): abrí «Registrar merma en cámara» con el Capataz en un celular o con el ancho de ventana reducido: una columna, botones de ancho completo, sin scroll horizontal.
15. **Navegador real** (obligatorio: hay formularios que se envían). Hacé el paso 5 y el paso 8 **en el navegador, con JavaScript** y enviando el formulario hasta el final. Tiene que mostrar el resultado esperado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Los desplegables tienen que redibujar la pantalla sin saltar de lugar y el botón de enviar tiene que deshabilitarse con «Calculando…» / «Registrando…».
16. **Después del merge, en Render:** en la «Shell», `python manage.py proceso_diario --listar` (tienen que verse 20, 25, 35 y 40) y revisá en el log del despliegue que se aplicaron `maestros.0011`, `comercial.0006` y `core.0037`.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (COM-04b, 24/11/2026)

- **Modelos y migraciones:**
  - `maestros/0011_dias_aviso_vencimiento_camara`: el campo `dias_aviso_vencimiento_camara` (valor inicial 3 para la fila existente, `AddField` con `default`) y su restricción `>= 0`.
  - `comercial/0006_camara`: `AlertaComercial.partida` (FK a `produccion.StockCosechado`, `PROTECT`) y la restricción `alerta_comercial_un_solo_origen` reescrita con tres FK (`suministro`, `detalle_suministro`, `partida`).
  - `core/0037_comercial_camara`: solo `choices` (`asignacion_camara`, `vencimiento_partida`, `aviso_partida_por_vencer`; el SQL es vacío). `core/models.py`: las tres acciones en `ACCIONES_DE_NEGOCIO`, las etiquetas nuevas (`partida`, `lineas_recortadas`, `reservas_liberadas`, `recubierto`, `sin_cubrir_tras_recorte`, `detalles_reabiertos`, `ventas_reabiertas`, `fecha_limite`, `dias_para_vencer`, `alerta_de_merma`, `plantas_perdidas`, `dias_aviso_vencimiento_camara`) y `estado_stock_cosechado` en `VALORES_VISIBLES`. `core/procesos.py`: solo el comentario (fila 25).
- **`maestros`:** el parámetro en `PARAMETROS_DE_CONFIGURACION` y en el grupo «Comercial» de la pantalla («Aviso de vencimiento de cámara (días antes)», ayuda «0 desactiva el aviso»). El servicio no cambió: valida por la tabla.
- **`comercial/servicios/camara.py` (nuevo):** `orden_de_recorte` y `orden_de_candidatos` (puras), `recortar_partida`, `asignar_camara` (PROD-ASG-CAM), `programar_asignacion_de_camara` (`transaction.on_commit`), `reasignar_camara` (paso 25), `vencer_partidas_en_camara` (paso 20, con el aviso previo), `resolver_aviso_de_partida`, `enlaces_de_alertas_de_camara`, `indicadores_de_camara` y `pestana_de_camara`.
- **`comercial/servicios/merma_camara.py` (nuevo):** `invernaderos_con_merma_en_camara`, `partidas_con_merma_posible`, `causas_de_camara`, `resumen_de_merma_en_camara` y `registrar_merma_en_camara`, con `DatosDeMermaEnCamara`.
- **Ganchos (`comercial/servicios/cosechas.py`):** `concretar_cosecha` programa PROD-ASG-CAM con las partidas que crea (postcondición k) y `_cancelar_en_transaccion` con las de las líneas de cámara que libera (postcondición h; sirve a `cancelar_cosecha` y a `cancelar_cosecha_incluida`).
- **`stock_maduro.asignar(..., confirmado=False)`:** argumento nuevo con nombre para el detalle «confirmado» que pierde producto (D-64 punto 13: la cantidad aceptada, `cant_entregada_venta`, hace de cantidad pedida; `cantidad_sin_cubrir(..., pedida=)`). Los dos caminos de antes no cambian.
- **Registros en `ComercialConfig.ready()`:** los tipos de alerta `comercial_partida_por_vencer` y `comercial_merma_camara_reservada` con su enlace, los pasos 20 y 25, y la pestaña «Cámara». `registrantes.entradas_de_comercial` devuelve la URL de la merma en cámara y `seccion_de_cosechas` suma los indicadores de la cámara.
- **Pantallas:** pestaña «Cámara» (`comercial/camara/_pestana.html`), «Registrar merma en cámara» (`views_camara.py`, `merma.html` y `_merma_formulario.html`, con su respaldo sin JavaScript), el enlace «Pérdida en cámara» en la merma de PRD-03 (`produccion/views_bitacora.py` y `_merma_formulario.html`: lo único de `produccion` que se tocó) y el grupo «Cosechas y cámara» del Inicio del Agrónomo. Correo `faltante_cubierto.txt`.
- **Bloqueos** (`FOR NO KEY UPDATE`, el orden de `docs/patrones/bloqueos.md`, «Cosecha y cámara»): cuentas → invernaderos (el de la partida y los considerados de los contratos, por id) → variedad → lotes y partidas candidatos → contratos y detalles → reservas y líneas. Con la partida bloqueada antes de leer sus reservas no hace falta la extensión 8a. El vencimiento y la merma leen sin bloquear qué contratos tienen líneas, bloquean, releen y, si aparecieron contratos nuevos, repiten una vez.

**Pruebas** (M1; 24/11/2026)

- `manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` (la suite completa): **7711 pruebas, OK** (390 s).
- `manage.py test comercial produccion --keepdb --tag concurrencia`: **107 pruebas, OK** (las de COM-04b: 7). `makemigrations --check --dry-run`: sin cambios; `manage.py check`: sin problemas. No hay migración de datos: no hay prueba `@tag("migracion")` nueva.
- Nuevas en `comercial`: `test_recorte` (13), `test_prod_asg_cam` (38), `test_prod_vnc_cam` (25), `test_prod_reg_mrm_camara` (27), `test_camara_vistas` (19), `test_camara_concurrencia` (7), `test_recorrido_camara` (1); métodos nuevos en `test_modelos_cosecha_camara` (3), `test_prod_cnc_csc` (3: postcondición k) y `test_prod_cnl_ord_cosechas` (3: postcondición h). En `maestros`: 2 en `test_adm_mod_cfg`.
- **Pruebas existentes cambiadas** (ninguna se borró ni se debilitó: cambió la cantidad de parámetros de 13 a 14, como pidió el plan aprobado):
  - `maestros/test_configuracion_vistas.py`: `test_flujo_principal_muestra_los_trece_parametros…` pasó a `…catorce…` (14 campos, más el aviso de cámara y su ayuda).
  - `maestros/test_adm_mod_cfg_iot.py`: `…formulario_de_produccion_sigue_con_trece_campos…` pasó a `…catorce…`; `maestros/test_singletons_modelo.py`: el diccionario de valores iniciales suma el campo nuevo; los docstrings que decían «13».
  - Sin cambios y vigentes: `comercial/test_extensiones_de_produccion.py::test_ext_entradas_por_rol` (su último renglón sigue pasando porque el escenario no tiene partidas; su docstring dice «es de COM-04b (`None`)» y queda viejo: lo cubre `EntradaEnLaMermaDeProduccionTests`).

**Verifiqué** (con el cliente de Django y la base de pruebas)

- El recorrido `test_recorrido_camara` (pasos 1 a 10 de la verificación a mano, por rol y por estado): el Capataz concreta una cosecha sin contrato; el Agrónomo ve la partida; el paso 25 la asigna y avisa, y repetirlo no duplica; el Capataz registra una merma en cámara con recorte (el resumen nombra el contrato, lo recortado se vuelve a cubrir con el lote en pie); el aviso previo con `proceso_diario --fecha`; el vencimiento con su merma y el aviso resuelto; la misma fecha otra vez no duplica nada: OK.
- Las tres migraciones: `makemigrations --check`, `sqlmigrate` leído (agregan dos columnas (una con valor inicial), un índice y dos restricciones de la base (una de ellas reescrita); no borran ni reescriben datos; `core.0037` es un no-op) y aplicadas en la base de pruebas: OK.
- La concurrencia (`test_camara_concurrencia`): PROD-ASG-CAM contra una compra-venta que toma la misma partida (en los dos órdenes), el vencimiento contra una merma (en los dos órdenes), una merma contra la asignación (en los dos órdenes) y dos mermas de la misma partida: OK, siempre con los invariantes de reservas y sin un error 500.

**Lo cubre una prueba**

- Reglas de cada caso de uso: `test_prod_asg_cam`, `test_prod_vnc_cam`, `test_prod_reg_mrm_camara` y `test_recorte` (orden y recorte); las postcondiciones k y h: `test_post_k_*` de `test_prod_cnc_csc` y `test_post_h_*` de `test_prod_cnl_ord_cosechas`; permisos, botones y flujos con y sin HTMX: `test_camara_vistas`; el parámetro: `test_adm_mod_cfg` y `test_configuracion_vistas`; la restricción de `AlertaComercial`: `test_modelos_cosecha_camara`.

**No pude verificar**

- El aspecto, el celular, el CSRF y el encabezado `Origin` en un navegador real, y el JavaScript (los desplegables que redibujan sin mover la pantalla y el botón que se deshabilita al enviar) con y sin JavaScript: pasos 13 a 15 de la verificación a mano.
- El correo «el faltante quedó cubierto» con un servidor de correo real (la prueba usa el correo de prueba de Django) y la aplicación de las migraciones en Render/Neon (paso 16).

**Pantallas: lo que se corrigió del prototipo** (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Ficha del invernadero › «Cámara» (`camaraTab`, `tabCamara`) | Todas las partidas, sin orden ni corte; datos solo del invernadero «A» | Disponibles primero por fecha límite; después las agotadas y vencidas de los últimos 30 días (por fecha límite); los datos son los del invernadero de la ficha; la «Merma por vencimiento» de las vencidas; estado vacío; botón «Registrar merma en cámara» solo para el Agrónomo a cargo | `camara.md`, «Pestaña «Cámara»» y «Lo que difiere del prototipo» |
| Configuración (`VIEWS.cfg`) | «Aviso previo al vencimiento de partidas en cámara» con la ayuda y sin validación | «Aviso de vencimiento de cámara (días antes)» con su validación (entero ≥ 0, error «El mínimo es 0.») y la ayuda «0 desactiva el aviso» | MD-134; `camara.md`, «Configuración» |
| Registrar merma (`VIEWS.merma` de PRD-03) | Sin la opción de la cámara | «¿Se perdió producto de la cámara? Pérdida en cámara», con el invernadero ya elegido, solo si hay partidas | Extensión 4a/4b de PROD-REG-MRM; D-64 punto 11 |
| Registrar merma en cámara (no está en el prototipo comercial) | — | Página nueva con el mismo esquema que la merma de PRD-03: invernadero → partida → cantidad, causa y descripción → resumen (qué contratos pierden producto) → confirmar; errores por campo; firma y comparación de la disponible vista (10d); respaldo sin JavaScript | `merma.md`, «Pantallas»; D-61 |
| Panel del Agrónomo (`secCosecha`) | Grupo «Cosecha y cámara» con partidas por vencer y plantas libres | El grupo «Cosechas y cámara» (el de COM-04a) suma «Partidas por vencer» y «Plantas libres en cámara» | `camara.md`, «Pantallas»; COM-04a |

**Decisiones:** ninguna nueva de equipo (`D-NN`). Aplicadas D-14, D-27, D-36, D-37, D-40, D-41, D-42, D-44, D-56, D-57, D-59, D-61, D-62, D-63, **D-64** (puntos 7, 9, 10, 12 y 13) y **D-67** (punto 2).

**Desvíos y temas abiertos** (para `docs/temas_abiertos.md`; no los corregí en silencio):

1. **Causa de la merma en cámara (decisión del estudiante en el plan):** `merma.md` dice «Daño en cámara» más las causas de lote en pie (sin «Descarte por selección»), pero `camara.aplicar_merma_de_partida` (mergeado en COM-04a) solo admite `dano_en_camara` y `vencimiento_en_camara`. Se ofrece solo «Daño en cámara». Hay que corregir el extracto y Drive o ampliar el núcleo en otra tarea. La descripción llega a 300 caracteres (el límite del núcleo), no a 500.
2. **Quién ve la pestaña «Cámara» (decisión del estudiante en el plan):** `camara.md` dice Gerente, Agrónomo a cargo, Capataz asignado y Vendedor, pero la ficha del invernadero es solo de Gerente y Agrónomo (`maestros.views.invernadero`, `rol_requerido`). `pestana_de_camara` decide por los cuatro roles, pero en la práctica solo la ven el Gerente y el Agrónomo. El Capataz llega a la merma en cámara desde «Registrar merma» y el Vendedor se entera por las notificaciones.
3. **Orden físico antes de volver a cubrir:** los extractos ponen `asignar` antes de `aplicar_merma_de_partida` y de `vencer_partida`. Se baja primero el stock físico y después se vuelve a cubrir: así lo recortado no vuelve a salir de la partida que se pierde. El resultado de negocio es el mismo.
4. **Enlace de la alerta «merma en cámara con producto reservado»:** el extracto lleva al Gerente a la ficha del contrato y al Agrónomo a la pestaña «Cámara». Se llevan los dos a la pestaña «Cámara» (la alerta no guarda el contrato; la descripción lo nombra).
5. **La pestaña va después de «Bitácora»:** las pestañas salen en el orden de registro (`maestros` no se tocó); el prototipo la pone antes.
6. **Cerradas de la pestaña:** «los últimos 30 días» se mide con la fecha límite de la partida (no se guarda cuándo se agotó o venció).
7. **El aviso «partida por vencer» sale una sola vez por partida (para siempre):** si una partida se agota y una devolución la vuelve a llenar (COM-06), no se vuelve a avisar.
8. **Sin hacer (de otras tareas):** el enlace del cliente (anularlo al cubrir un detalle pendiente, crearlo en el camino de faltante) y la concurrencia «merma en cámara contra la decisión del cliente» (COM-04c); «sin entrega» de los candidatos, planificar la entrega (paso 9, postcondición e) y quitar las líneas de su entrega «a realizar» (COM-05); la extensión 3b y la devolución a una partida vencida (COM-06); los asientos (CON-04c).
9. **Datos de verificación:** el apartado «Datos para verificar» de la tarea pedía ampliar `comercial/verificacion.py`; D-95 retiró los cargadores y no se hizo (CLAUDE.md).
10. **Cambios al disparador:** el `on_commit` de PROD-ASG-CAM ya corre en PROD-CNC-CSC y en la cancelación (el estado de paso de COM-04a deja de existir).
