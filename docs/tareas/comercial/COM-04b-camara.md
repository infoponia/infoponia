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

Hay migraciones nuevas (`comercial`, `maestros`, `core`): `python manage.py migrate`. Datos: los de COM-04a (con la partida de 40 plantas de
la cosecha sin contrato); en «Configuración», aviso de vencimiento de cámara 3 días.

1. Ficha del invernadero, pestaña «Cámara»: aparece `P-…` con 40 plantas, motivo «Cosecha planificada por el Agrónomo» y su fecha límite.
2. Con una venta que espera esa variedad: `python manage.py proceso_diario` (el paso 25): la partida queda
   reservada y el Vendedor tiene la notificación.
3. «Registrar merma» › «Pérdida en cámara»: más que el stock libre de una partida reservada: el resumen dice qué contratos pierden producto;
   confirmá y mirá cómo quedaron las reservas.
4. `python manage.py proceso_diario --listar`: aparecen 20, 25, 35 y 40. `python manage.py proceso_diario --fecha <fecha límite − 2>`: la
   campana del Agrónomo muestra «Partida por vencer» (y el Vendedor la notificación). `--fecha <fecha límite + 1>`: la partida queda
   «Vencida» con su merma. Corré la misma fecha otra vez: nada nuevo.
5. Sin JavaScript: la merma en cámara funciona con «Actualizar» y el resumen como página.
6. Después del merge: en Render, desde la «Shell», `python manage.py proceso_diario --listar` y revisar en el log que se aplicaron las
   migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
