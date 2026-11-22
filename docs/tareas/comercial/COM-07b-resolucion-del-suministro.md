# COM-07b · Resolución del suministro por incumplimientos (paso diario 33)

Estado: pendiente | App: comercial | Rama: feature/com-07b-resolucion-del-suministro | Ronda: Comercial 1

Depende de: **COM-07a** (y, con ella, toda la cadena COM-02 a COM-06b, MAE-05, MAE-02d, DIA-01 y «Producción 1»). Si COM-07a no está
mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La segunda parte de COM-07 (D-69, punto 1): cuando el Gerente acepta una discrepancia o una queja con la que un suministro
**vigente** supera sus incumplimientos tolerados, InfoPonia **resuelve el contrato** sin intervención de nadie: cancela las cosechas y las
entregas que faltaban (también la que está en viaje), libera las reservas, devuelve a la cámara el producto ya cosechado, deja el contrato y
sus detalles «resueltos», avisa al Gerente con una alerta, al cliente con el aviso de resolución (con la multa) y al Vendedor, al Capataz, al
Transportista y al Agrónomo con lo que les toca. Lo ya entregado se conserva y se sigue cobrando. Si el disparo falla, una **recuperación
diaria** (paso 33) lo retoma. El Gerente **da por atendida** la alerta cuando pagó la multa.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-RSV-SUM | Resolver Suministro por Incumplimientos (con el paso diario 33) | docs/casos_de_uso/comercial/resolucion.md | Precondición c, postcondición h y 5b (asiento de la multa): fuera, D-57 |
| PROD-CNL-ORD | Cancelar Orden (cosechas y entregas, incluida; «Desde Cancelar Compra-venta, COM-RSV-SUM y Modificar Suministro») | docs/casos_de_uso/produccion/cancelar_orden.md y resolucion.md («Ejecución de PROD-CNL-ORD») | — |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/resolucion.md **completo**; de solicitudes.md, «Cómo se aplica» (lo que deja COM-07a:
  `resolver_si_corresponde`, `solicitud_resolucion`, 2a de COM-ANL-SRV); de compra_venta.md, «COM-CNL-CVT» y su «Cómo se aplica» (el modelo
  a seguir: la transacción, las partidas, las cancelaciones); de docs/casos_de_uso/produccion/cancelar_orden.md, las secciones «Comercial 1»
  (`cancelar_cosecha_incluida` y `cancelar_entrega_incluida`); de camara.md, PROD-ASG-CAM («Cómo se aplica»: `asignar_camara`); de
  suministro.md, «Cómo se aplica» (COM-CNS-SUM y la rescisión, con el paso 35); de pre_reserva.md, «Cómo se aplica» (el paso 40).
- Modelo: docs/modelo/comercial.md (**Suministro**, **DetalleSuministro**, **AlertaComercial**, SolicitudRevision, ReservaStock,
  DetalleReserva, Entrega, Contrato); docs/modelo/produccion.md (Cosecha, StockCosechado, MovimientoStock, OrdenTrabajo).
- Decisiones: **D-69** (puntos 1, 5, 7, 13, 14 y 15), D-68, D-67 (punto 4), D-66 (puntos 11 y 12), D-64 (puntos 2, 3, 9 y 12), D-63, D-62,
  D-59, D-57, D-56, D-42, D-36, D-27.
- Patrones: docs/patrones/bloqueos.md («Resolver un suministro» y «Cancelar una compra-venta»), docs/patrones/stock_maduro.md (sección 8),
  docs/patrones/auditoria.md.
- API: docs/api/produccion.md (secciones 8 y 9); docs/api/alertas.md (secciones 1, 2, 4 y 8); docs/api/notificaciones.md.
- Pantallas: docs/prototipos/comercial/ (`README.md`): `VIEWS.sum` (todas sus definiciones, también el reemplazo de la rescisión) y
  `tabContratos` (rama `sum`).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/` completo (COM-01 a COM-07a), en especial `servicios/resoluciones.py` (la función neutra), `servicios/compra_ventas.py`
  (`cancelar_compra_venta`), `servicios/cosechas.py` (`cancelar_cosecha_incluida`), `servicios/entregas.py` (`cancelar_entrega_incluida`),
  `servicios/camara.py` (`asignar_camara`), `servicios/suministros.py` (la ficha, `cerrar_rescisiones`), `servicios/comprobantes.py`,
  `servicios/solicitudes.py`, `apps.py` (los pasos registrados), las fábricas e invariantes; `produccion/servicios/camara.py`
  (`crear_partida`), `produccion/servicios/ordenes.py`; `core/procesos.py`, `core/models.py`, `core/notificaciones.py`;
  `maestros/servicios/alertas.py`, `maestros/extensiones.py`.

## Límites

- Crea modelos: ninguno (los campos que usa ya existen: `fecha_resolucion_suministro` desde COM-03a, `solicitud_resolucion` desde COM-07a,
  `AlertaComercial.suministro` desde COM-03b).
  → revisá docs/disparadores.md: cierra «Resolución de un contrato con rescisión acordada» y lo de COM-07b del punto 10 de «Cuando exista
  Entrega».
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `core/migrations/00NN_comercial_resolucion.py`: solo `choices` (acciones `resolucion_suministro`, `resolucion_suministro_descartada`,
    `atencion_suministro_resuelto`).
- Permitido fuera de `comercial`: `core/models.py` (las acciones, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`); `core/procesos.py`
  (solo el comentario con la tabla de órdenes: suma el 33); al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`,
  `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`. Dentro de `comercial`, el argumento nuevo `avisar_agronomo` de
  `cancelar_cosecha_incluida` y de `cancelar_entrega_incluida` (por omisión `True`): **las pruebas de COM-04a, COM-05a1 y COM-05b no se
  modifican**. Las de COM-07a que esperaban que `resolver_si_corresponde` no hiciera nada se reemplazan: anotalas en el PR.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el asiento de la multa y su pago (ronda de contabilidad, D-57; CU-17); volver un contrato resuelto a «vigente»; registrar
  la devolución física del producto que estaba en el vehículo; compensar la multa con lo que el cliente debe (temas abiertos del caso de uso).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **El argumento `avisar_agronomo`** en las dos funciones incluidas (`resolucion.md`, paso 4.1 y 4.4). Pruebas: métodos nuevos en
   `test_cancelar_cosecha_incluida.py` y `test_prod_cnl_ord_entregas.py` (sin aviso al Agrónomo con `False`; el resto igual).
2. **Resolver un suministro** (`resolucion.md`, «Resolver un suministro»), con `resolver_si_corresponde` completa. Pruebas: `test_com_rsv_sum.py`.
3. **Recuperación diaria** (`resolucion.md`, «Recuperación diaria»), con el paso 33 registrado. Pruebas: en `test_com_rsv_sum.py`, las del
   disparador 2 y 1a; en la prueba de `core/procesos.py` que lista los pasos (si existe), el orden 33.
4. **Concurrencia.** Pruebas: `test_resolucion_concurrencia.py`.
5. **La ficha, la lista y «Dar por atendida»** (`resolucion.md`, «La resolución en la ficha y en la lista del suministro»), con el enlace de la
   alerta. Pruebas: `test_resolucion_vistas.py`.
6. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar «Resolución de un contrato con rescisión
   acordada» y lo de COM-07b del punto 10; marcar COM-07b en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a
   `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es la marca «Resolución sin atender» de la lista (queda en `docs/temas_abiertos.md`). No se
recortan los bloqueos, la relectura (6a), la recuperación diaria, el aviso a quien tiene la entrega en viaje ni las pruebas de concurrencia.

## Hecho cuando

- Al aceptar la solicitud que supera los tolerados de un suministro vigente, en menos de un minuto el contrato y sus detalles quedan
  «resueltos», con la fecha y la solicitud que lo provocó; no queda ninguna reserva activa ni lista para entrega ni ninguna orden a realizar
  del contrato; lo cosechado está en la cámara con su fecha límite desde la cosecha; lo entregado no cambió.
- El Gerente tiene la alerta «suministro resuelto» (y la da por atendida desde la ficha); el cliente, el aviso con la multa y las entregas
  canceladas; el Vendedor, su aviso; el Capataz y el Transportista, los de las cancelaciones (el que estaba en viaje, «No la entregues»); el
  Agrónomo de cada invernadero, una sola notificación.
- Si el disparo falla, `python manage.py proceso_diario` lo resuelve (paso 33, antes del 35, del 40 y del 50).
- Una aceptación en un contrato no vigente, o un disparo que ya no corresponde, no cambia nada (el segundo deja su registro).
- La anulación de la solicitud que resolvió el contrato se rechaza (2a de COM-ANL-SRV).
- Todas las pruebas de `comercial`, `produccion` y `core` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial produccion core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva (`core`, solo `choices`): `python manage.py migrate`. Datos: los de COM-07a, con un suministro vigente con 0
incumplimientos tolerados y multa, que tenga una entrega a realizar con envasado, otra reserva activa con su cosecha a realizar y una
discrepancia pendiente; un cliente **con un correo que puedas leer**.

1. Con el Gerente, aceptá la discrepancia: el resumen advierte la resolución. Confirmá: en la ficha del suministro, «Resuelto por
   incumplimientos» con la solicitud; la cosecha y la entrega canceladas con el motivo; la partida nueva en la pestaña «Cámara».
2. La campana del Gerente tiene «suministro resuelto»; llega el aviso al cliente; el Capataz, el Transportista, el Vendedor y el Agrónomo tienen
   sus avisos (el Agrónomo, uno solo).
3. Intentá anular la discrepancia: «esta aceptación resolvió el contrato».
4. «Dar por atendida»: la alerta se resuelve y la marca de la lista desaparece.
5. Con otro suministro, iniciá la ruta del Transportista con una entrega del contrato y después provocá la resolución: el Transportista recibe
   «No la entregues…».
6. Simulá el disparo perdido (en el shell: un suministro vigente con más incumplimientos que los tolerados) y corré `python manage.py
   proceso_diario --solo resolver_suministros`: queda resuelto; corré otra vez: no hace nada.
7. Sin JavaScript: «Dar por atendida» funciona.
8. Después del merge: revisar en el log de Render que se aplicó la migración nueva.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
