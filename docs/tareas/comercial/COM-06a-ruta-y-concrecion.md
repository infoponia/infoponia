# COM-06a · Ruta y concreción de entregas: iniciar y finalizar la ruta, concretar, intento fallido y discrepancia

Estado: pendiente | App: comercial | Rama: feature/com-06a-ruta-y-concrecion | Ronda: Comercial 1

Depende de: **COM-05b** (y, con ella, toda la cadena COM-02 a COM-05a2, MAE-05 y «Producción 1»). Usa lo que **COM-04a** dejó en
`produccion` para las entregas (`docs/api/produccion.md`, sección 10: `aplicar_merma_de_entrega`, `egresar_de_partida`, `devolver_a_partida`,
`cerrar_reserva`, `registrar_consumo_de_orden`, `Merma.orden` y `Consumo.orden`). Si COM-05b no está mergeada, o si falta alguna de esas
funciones, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La primera de las dos partes de COM-06 (D-68, punto 1): el Transportista **inicia la ruta** del día desde el celular, va
**concretando** cada entrega (lo que llegó, lo que se perdió, lo que el cliente aceptó o recibió, los envases y, en la última de una
compra-venta, el cobro) o registra un **intento fallido**, y **finaliza la ruta**. El Vendedor concreta los **retiros** en el invernadero. La
concreción mueve la cámara, registra las mermas y los consumos de envases, fija los montos y el vencimiento, cierra el contrato cuando
corresponde y, en un suministro por debajo del mínimo, crea la **discrepancia** para el Gerente. La confirmación del cliente por el enlace y
la entrega no reconocida son de **COM-06b**.

**Estado de paso** (`docs/temas_abiertos.md`, «Abiertos desde el lote C6»): entre COM-06a y COM-06b, el correo de una entrega de suministro
concretada lleva el comprobante **sin enlace** y la entrega queda «no confirmado» (COM-06b no les crea enlace a las ya concretadas). No rompe
datos: programá COM-06b enseguida.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-INI-RUT | Iniciar Ruta | docs/casos_de_uso/comercial/rutas.md | — |
| COM-CNC-ENT | Concretar Entrega (con el retiro, 1a, y el intento fallido, 4a) | docs/casos_de_uso/comercial/rutas.md | Precondición d y postcondiciones e, g y h (asientos): fuera, D-57. Postcondición l (el enlace): COM-06b. Resolver la discrepancia: COM-07 |
| COM-FIN-RUT | Finalizar Ruta (alto nivel) | docs/casos_de_uso/comercial/rutas.md | — |
| PROD-VNC-CAM | Vencer Partidas en Cámara (solo la extensión 3b) | docs/casos_de_uso/produccion/camara.md y rutas.md («PROD-VNC-CAM 3b») | — |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/rutas.md **completo**; de docs/casos_de_uso/comercial/entregas.md, «Cómo se aplica» de
  COM-PNF-ENT y de COM-ASG-TRP (candidatos, peso, en curso, el paso 50); de docs/casos_de_uso/produccion/envasado.md, «Cómo se aplica» (las
  reservas de insumo y «Retiro en concreción»); de camara.md, PROD-ASG-CAM, PROD-VNC-CAM y «Para más adelante»; de compra_venta.md, «COM-CNL-CVT»
  y su «Cómo se aplica»; de suministro.md, «Cómo se aplica» (`precio_en`, los períodos, `fecha_fin_detalle`, la ficha); de clientes.md, «Se
  completa en».
- Modelo: docs/modelo/comercial.md (**Entrega**, **DetalleEntrega**, **PagoCliente**, **IntentoFallido**, **SolicitudRevision**,
  **DiscrepanciaEntrega y LineaDiscrepancia**, **AlertaComercial**, Vehiculo, CompraVenta, DetalleVenta, ReservaStock, DetalleReserva,
  DetalleSuministro y las cláusulas); docs/modelo/produccion.md (Merma, Consumo, ReservaInsumo, StockCosechado, MovimientoStock);
  docs/modelo/contabilidad.md (`OrigenDocumento`).
- Decisiones: **D-68** (todos sus puntos), **D-66** (puntos 3, 5, 6, 9, 11 y 12), D-67 (punto 4), D-64 (puntos 1, 3, 9, 10 y 12), D-63, D-62,
  D-60, D-57, D-55, D-52, D-50, D-42, D-40, D-36, D-29, D-28, D-27, D-25.
- Patrones: docs/patrones/bloqueos.md («Entregas y envasado», con «Iniciar y finalizar la ruta» y «Concretar una entrega»), docs/patrones/stock.md
  (sección 5), docs/patrones/stock_maduro.md (secciones 3 y 8), docs/patrones/auditoria.md, docs/patrones/abm.md (sección 1).
- API: **docs/api/produccion.md, sección 10**, y las secciones 8 y 9; docs/api/stock.md (`reevaluar_alertas_del_insumo`); docs/api/alertas.md
  (secciones 1, 2, 4 y 8); docs/api/notificaciones.md; docs/api/extensiones_de_maestros.md («Transportistas»); los puntos de
  `core/extensiones.py` (impedimento de baja de cuenta, `registrar_seccion_de_inicio`) y `core/menu.py`.
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): las funciones de «Pantallas» de `rutas.md` (vale la última definición:
  `VIEWS.ruta` y `VIEWS.cncent` están dos veces).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-05b): modelos, `servicios/` (`entregas.py`, `envasado.py`, `camara.py`, `stock_maduro.py`,
    `compra_ventas.py`, `suministros.py`, `calendario.py`, `comprobantes.py`), `apps.py`, vistas, plantillas, fábricas e invariantes;
  - `produccion/servicios/` (`mermas.py`, `camara.py`, `consumos.py`, `ordenes.py`), `produccion/models.py`;
  - `inventario/servicios/stock.py` y `alertas_de_stock.py`; `maestros/extensiones.py`, `maestros/servicios/alertas.py`;
  - `core/menu.py`, `core/extensiones.py`, `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría); el Panel de control y el
    menú del Transportista como están hoy; `contabilidad/models.py`.

## Límites

- Crea modelos (en `comercial`): `PagoCliente`, `IntentoFallido`, `SolicitudRevision`, `DiscrepanciaEntrega`, `LineaDiscrepancia`; los
  campos de la concreción de `Entrega` (`monto_total_entrega`, `fecha_vencimiento_pago`) y de `DetalleEntrega` (`cant_perdida`,
  `cant_devuelta`); `AlertaComercial.solicitud`. **No toca `produccion`** (lo hizo COM-04a, D-68 punto 3).
  → revisá docs/disparadores.md: cierra «Cuando exista Entrega», puntos 2 (`transportista_en_ruta`), 5, la parte de COM-06 de los puntos 7 y
  8 y el punto 9 (lo de COM-06).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_concrecion.py`: las cinco tablas, los campos, la secuencia `comercial_solicitud_numero_seq` (como la de los
    contratos) y todas las restricciones de las fichas (también la de «exactamente una FK de origen» de `AlertaComercial`, con cinco);
  - `contabilidad/migrations/00NN_pago_y_solicitud.py`: solo `choices` (`pago_cliente`, `solicitud_revision`);
  - `core/migrations/00NN_comercial_rutas.py`: solo `choices` (acciones `inicio_ruta`, `fin_ruta`, `concrecion_entrega`,
    `intento_fallido_entrega`).
- Permitido fuera de `comercial`:
  - `core/models.py`: las acciones, `ETIQUETAS`, `VALORES_VISIBLES` (`motivo` del intento, `medio_pago`) y `ACCIONES_DE_NEGOCIO`;
  - `contabilidad/models.py`: los dos valores de `OrigenDocumento.Tipo`;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y `docs/estado.md`.
  Las pruebas existentes de `comercial` no se modifican, salvo las que esperaban «sin datos» donde esta tarea los completa (la ficha del
  cliente, del suministro y de la compra-venta, y las que probaban «en curso» con la fábrica): reemplazalas y anotalas en el PR.
- Dependencias nuevas: ninguna.
- Fuera de alcance: **COM-06b** (el enlace de confirmación y su correo, COM-CNF-ENT, `Queja`, COM-ATN-ENR); resolver la discrepancia
  (COM-07); el cobro de una entrega de suministro, «pagada» y la alerta «pago en mora» (COM-08); la extensión 6a de COM-CNL-CVT (COM-08); los
  asientos (D-57); el cron (D-56); el registro sin conexión (mejora futura del caso de uso).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones** (las fichas de `docs/modelo/comercial.md`; D-68, puntos 4 a 7). Fábricas: `entrega_concretable(...)` (con
   ruta iniciada y envasado opcional), `entrega_concretada(...)`, `discrepancia(...)`, `pago_de_compra_venta(...)`; invariantes nuevos de
   `verificar_invariantes_de_entregas` y `verificar_invariantes_de_solicitudes`.
   Pruebas: `comercial/tests/test_modelos_concrecion.py` (una por restricción de cada ficha; la de una discrepancia por entrega; la de
   `AlertaComercial` con cinco orígenes).
2. **Iniciar la ruta** (`rutas.md`, «Iniciar la ruta»): `ruta_del_dia` e `iniciar_ruta`.
   Pruebas: `test_com_ini_rut.py` y, con la ruta iniciada de verdad, que COM-ASG-TRP, PROD-PNF-ENV, COM-CNL-CVT y COM-PNF-ENT ven las
   entregas «en curso» (reemplazan a las que usaban la fábrica: anotalo).
3. **Intento fallido y finalizar la ruta** (`rutas.md`, «Intento fallido» y «Finalizar la ruta»): `registrar_intento_fallido`,
   `finalizar_ruta`, `intentos_fallidos`.
   Pruebas: `test_com_fin_rut.py` y, en `test_com_cnc_ent.py`, la extensión 4a.
4. **Concretar** (`rutas.md`, «Concretar»): `entregas_concretables`, `datos_de_concrecion`, `resumen_de_concrecion`, `repartir`,
   `concretar_entrega`, `crear_discrepancia`, `monto_a_cobrar`, `estado_de_pago`; los avisos, los correos (comprobante de venta y de entrega,
   sin enlace) y el reintento en el paso 50 (su parte 4 suma las entregas concretadas con `pendiente_envio`).
   Pruebas: `test_com_cnc_ent.py` (todo lo de «Pruebas» de `rutas.md`), `test_concrecion_concurrencia.py`.
5. **Lo que completa a otras tareas** (`rutas.md`, «Lo que completa a otras tareas» y «PROD-VNC-CAM 3b»): `transportista_en_ruta` en los dos
   registrantes; PROD-VNC-CAM 3b en el paso 20; la prueba de COM-CNL-CVT con una entrega concretada real (sigue rechazando
   `venta_con_entregas_concretadas`) y la de los detalles «sin línea en una entrega concretada» (D-67, punto 4); las fichas del cliente, del
   suministro y de la compra-venta.
   Pruebas: en `test_extensiones_entregas.py` (COM-05a1), las tres mínimas de cada registrante; en
   `test_prod_vnc_cam.py`, la 3b; en `test_com_cnl_cvt.py`, las dos con datos reales; en las de las fichas, las secciones nuevas.
6. **Vistas, plantillas y pantallas compartidas** (`rutas.md`, «Pantallas»): «Mi ruta», iniciar, concretar en pasos para celular (con
   `calcular/`), intento fallido, finalizar; «Concretar retiro» en la lista de entregas; la entrada «Mi ruta» y la sección «Ruta de hoy» del
   Transportista (antes, mirá qué tiene hoy su Panel de control y su menú: no dupliques).
   Pruebas: `test_rutas_vistas.py`.
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de «Límites» y dejar lo que nace (COM-06b:
   el enlace en la concreción; COM-07: la discrepancia, `intentos_fallidos`; COM-08: R154 y C7, «pagada», 6a de COM-CNL-CVT); marcar COM-06a
   en `docs/tareas/README.md` y en el plan; lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió
   del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es la sección «Ruta de hoy» del Panel de control (queda la entrada del menú; anotalo en
`docs/temas_abiertos.md`). No se recortan las restricciones de la base, los bloqueos, la huella, el reparto entre orígenes ni las pruebas de
concurrencia.

## Hecho cuando

- El Transportista ve su ruta del día con el peso y las demoradas primero, la inicia y desde ese momento sus entregas están en curso para las
  demás operaciones; la finaliza cuando no le queda nada, y puede iniciar otra el mismo día si le asignan una entrega.
- Concreta una entrega de compra-venta y una de suministro desde el celular: la cámara, las mermas, los consumos de envases (con exceso y
  sin envasado), los montos, el vencimiento del pago, el pago de la venta, el fin del detalle y del contrato y la discrepancia quedan como
  dice `rutas.md`, en una transacción y con un registro de auditoría.
- Registra un intento fallido: la entrega pasa a mañana, sin transportista, con sus envases reservados; el Vendedor y el cliente se enteran.
- El Vendedor concreta un retiro y cobra.
- Un transportista en ruta no se quita, no se traslada y su cuenta no se da de baja.
- Todas las pruebas de `comercial`, `produccion`, `maestros`, `core` e `inventario` siguen pasando (las reemplazadas, anotadas).
- Comando de pruebas:
  python manage.py test comercial produccion maestros core inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas (`comercial`, `contabilidad`, `core`): `python manage.py migrate`. Datos: los de COM-05b (un invernadero con Agrónomo,
Capataz, Vendedor y un Transportista con vehículo; un cliente con correo); una compra-venta con envío lista para entregar, con su envasado; un
suministro con una entrega planificada para hoy y cantidad mínima 100.

1. Con el Transportista (en el celular o con el navegador angosto): «Mi ruta» muestra las dos entregas, el peso y la capacidad. «Iniciar
   ruta». Con el Vendedor, intentá cambiarle el transportista a una: no deja («en curso»).
2. Concretá la compra-venta: 5 perdidas, el resto aceptado, un envase de más. El resumen muestra la merma, el exceso y el total a cobrar; elegí
   «Efectivo» y confirmá. La venta queda «concretada» con su pago; el Agrónomo tiene el aviso del exceso; en «Inventario», el consumo del
   envase incluye el exceso.
3. Concretá el suministro con 80 recibidas: queda la discrepancia `SR-…` y la alerta para el Gerente; la ficha del suministro muestra la
   entrega con su monto y su vencimiento. El correo al cliente trae el comprobante (sin enlace todavía).
4. Con otra entrega: «Intento fallido» por «Cliente ausente»: pasa a mañana sin transportista; el Vendedor tiene el aviso.
5. «Finalizar ruta» con una pendiente: no deja y ofrece concretar o registrar el intento; sin pendientes, finaliza.
6. Con el Vendedor, un retiro: «Concretar retiro» desde «Comercial» › «Entregas», con cobro por transferencia.
7. Con el Gerente, con el Transportista en ruta: quitarlo del invernadero y darle de baja la cuenta muestran el impedimento.
8. Sin JavaScript: iniciar, concretar (con «Actualizar»), intento fallido y finalizar funcionan.
9. Después del merge: revisar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
