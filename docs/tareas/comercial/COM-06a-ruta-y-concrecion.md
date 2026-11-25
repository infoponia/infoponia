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

Claude Code no cargó datos ni abrió un navegador (D-95, D-96): los datos los creás vos, con los valores de abajo. Esta tarea tiene **formularios que se envían y JavaScript propio** (HTMX): por eso el paso 14 es de «navegador real».

**Antes de empezar**

- `python manage.py migrate` (hay tres migraciones nuevas: `comercial` 0010, `contabilidad` 0007 y `core` 0044) y `python manage.py runserver`; entrá a `http://localhost:8000`. Las cuentas las creás o reutilizás con la contraseña que ya usás en las de prueba (nunca en un archivo del repo).
- Cuentas: un **Gerente**, un **Vendedor**, un **Agrónomo** del invernadero y un **Transportista** (con un vehículo activo de 800 kg, asignado desde «Comercial › Vehículos» por el Gerente, y asignado al invernadero desde su ficha › «Logística»).
- Crear a mano, en este orden (todo con el invernadero de arriba, con un lote en Maduración con 500 plantas de una variedad «Lechuga» y su cliente):
  1. Un **cliente con correo** y una dirección activa en su ficha (por ejemplo «Panadería Sol», CUIT `30-71234567-8`).
  2. **Cámara con stock**: una partida de cámara de 200 plantas de Lechuga (cosechá un lote de 200 con «Cosechas»).
  3. **Envase**: en «Inventario» habilitá «Bandeja PET» en el invernadero con 30 de stock.
  4. **Compra-venta 1** (envío a domicilio, fecha pactada de hoy): 50 plantas de Lechuga a $100. Esperá a que InfoPonia planifique la entrega (aparece en «Comercial › Entregas» a nombre del Transportista, o asignala con «Asignar transportista») y, con el Agrónomo, **planificá su envasado** («Producción › Envasado»: 10 Bandeja PET).
  5. **Suministro** (un detalle de Lechuga, 100 plantas por período, cantidad mínima 100, plazo de pago 15 días, primera entrega hoy) y esperá su entrega para hoy con el mismo Transportista.
  6. **Compra-venta 2** (envío, hoy, 10 plantas): será la del intento fallido.
  7. **Compra-venta 3** con **retiro en invernadero** (fecha de hoy, 20 plantas), para el paso 9.

**Pasos**

1. **Mi ruta (Transportista, en el celular o con la ventana angosta).** «Panel de control» › sección «Ruta de hoy» › «Mi ruta». Tenés que ver las tres entregas de hoy con cliente, destino, contenido y peso, el vehículo («En el invernadero»), la carga de la ruta y la capacidad (800 kg). Las que no tienen envasado dicen «Sin envasado». **No** hay botones «Concretar» ni «Intento fallido» todavía. Abajo, «Iniciar ruta». *(Lo cubre `test_rutas_vistas`.)*
2. **Iniciar ruta.** «Iniciar ruta»: la página con la lista, el peso y las localidades. Tocá «Iniciar ruta». Volvés a «Mi ruta» con el aviso «Ruta iniciada…», el vehículo dice «En ruta» y cada entrega muestra «Concretar» e «Intento fallido»; ahora hay «Finalizar ruta» y ya no «Iniciar ruta». En «Auditoría» (Gerente) hay un registro «Inicio de ruta».
3. **Una entrega en curso no se cambia.** Con el Vendedor o el Gerente: «Comercial › Entregas» › la entrega de la compra-venta 1: la fila dice «En curso» y no ofrece cambiar el transportista; abrir la URL de asignar a mano muestra «ya inició la ruta…».
4. **Concretar la compra-venta 1.** Con el Transportista: «Concretar». Tenés tres pasos en una página. Escribí «Llegaron en buen estado»: **45** (se pierden 5), dejá «Acepta lo que llegó», en «Utilizados» escribí **11** (uno más de lo reservado), tildá «Confirmo la cantidad utilizada», elegí «Efectivo» y tocá «Ver resumen». Tiene que decir: perdidas 5, «1 de más», total **$ 4.500,00** y «efectivo». Tocá «Confirmar entrega»: aparece la pantalla «concretada» con el total cobrado y «Imprimir comprobante».
   - **Efectos para mirar:** la venta queda «Concretada» con su pago en su ficha (Efectivo, hoy, $ 4.500,00); el Agrónomo tiene un aviso del envase de más; el Vendedor, «Se concretó con diferencias»; en «Inventario», el consumo de la bandeja es 11; en «Producción › Mermas», una merma «Daño en la entrega» de 5; el cliente recibe el comprobante de venta por correo (si el correo está configurado) y «Auditoría» tiene un registro «Concreción de entrega». *(Lo cubre el recorrido.)*
5. **Errores del formulario.** En otra entrega: «Llegaron» **99** (más de lo planificado) → «Ver resumen» muestra el error con lo planificado y **no** hay «Confirmar entrega». Dejá «Medio de pago» vacío en una venta → «Elegí el medio de pago…». En una entrega sin envasado, ni declarar envases ni tildar «No se usaron envases» → «Declará los envases usados…».
6. **Concretar el suministro con 80 recibidas.** «Concretar» sobre la entrega del suministro: «Llegaron» 100, «Recibió el cliente» **80**, «No se usaron envases» tildado. El resumen muestra el vencimiento (hoy + 15 días). Confirmá. Resultado: el Gerente ve la alerta «Discrepancia de entrega» (campana) que lleva a la ficha del suministro, con la discrepancia `SR-…` (80 de 100 mínimas); la ficha muestra la entrega con monto, vencimiento y «Pendiente»; el calendario dice «Entregado» en ese período; el Vendedor tiene el aviso; el cliente recibe el comprobante de entrega **sin enlace** (el enlace llega con COM-06b); en la ficha del cliente aparecen «Entregas sin cobrar» y «Discrepancias pendientes».
7. **Finalizar con una pendiente.** «Finalizar ruta» con la compra-venta 2 sin resolver: la pantalla lista la entrega con «Concretar» e «Intento fallido» y no deja finalizar.
8. **Intento fallido.** «Intento fallido» sobre la compra-venta 2: motivo «Cliente ausente» (sin motivo, «Elegí el motivo»). Vuelve a «Mi ruta»: la entrega ya no está, pasó a mañana sin transportista. El Vendedor tiene el aviso «No se pudo entregar…» con la fecha nueva y el cliente, un correo con el motivo. «Comercial › Entregas» la muestra «Sin transportista» para mañana. Ahora «Finalizar ruta» → confirmación → «Ruta finalizada.»; el vehículo vuelve a «En el invernadero».
9. **Concretar retiro (Vendedor).** Con el Vendedor: «Comercial › Entregas»: la compra-venta 3 tiene «Concretar retiro». Escribí 20, «Acepta», «Transferencia» → «Ver resumen» → «Confirmar entrega»: la venta queda «Concretada» con el pago por transferencia. El Gerente **no** ve «Concretar retiro».
10. **Un transportista en ruta no se quita ni se da de baja.** Antes del paso 8, con el Gerente: en la ficha del invernadero quitar al Transportista, o «Usuarios» › dar de baja su cuenta, muestran el impedimento «Está en ruta desde hoy con N entregas. Esperá a que finalice la ruta.» *(Lo cubren las pruebas de `test_extensiones_entregas`.)*
11. **Roles.** El Gerente, el Agrónomo y el Capataz escribiendo a mano `/comercial/ruta/` o `/comercial/entregas/<id>/concretar/` ven un 403 y ninguna pantalla les ofrece el enlace. Un Vendedor tampoco puede concretar una entrega con envío ni el retiro de otro Vendedor.
12. **Una ruta de ayer no vale.** (Opcional, con la base de desarrollo) dejá una ruta iniciada sin finalizar y, al otro día, «Mi ruta» dice que ya no está vigente y se inicia otra.
13. **Sin JavaScript** (opcional, desactivalo en el navegador): iniciar, concretar (con «Ver resumen», que vuelve la misma página con el resumen), intento fallido y finalizar funcionan igual.
14. **Navegador real.** Abrí «Concretar» en una **ventana privada** (entrando con la cuenta del Transportista), completá el formulario, tocá «Ver resumen» y **enviá «Confirmar entrega» hasta el final**; después volvé a abrir «Mi ruta». Tiene que mostrar el resultado esperado. Hacelo también en un celular real o con la ventana angosta (F12 › vista móvil). Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no ve. Con JavaScript, «Ver resumen» redibuja solo el resumen (sin recargar la página ni mover el scroll).
15. **Después del merge:** revisar en el log de Render que se aplicaron las tres migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)

### Qué se hizo

- **Modelos y migraciones** (`comercial/0010_concrecion`, `contabilidad/0008_pago_y_solicitud`, `core/0046_comercial_rutas`, ninguna de datos): `PagoCliente`, `IntentoFallido`, `SolicitudRevision`, `DiscrepanciaEntrega` y `LineaDiscrepancia`; `Entrega.monto_total_entrega` y `fecha_vencimiento_pago`; `DetalleEntrega.cant_perdida` y `cant_devuelta`; `AlertaComercial.solicitud` (restricción de un solo origen con cinco); la secuencia `comercial_solicitud_numero_seq`; las cuatro acciones de auditoría (`inicio_ruta`, `fin_ruta`, `concrecion_entrega`, `intento_fallido_entrega`) con sus etiquetas; los dos tipos de `OrigenDocumento`.
- **Servicios**: `rutas.py` (`ruta_del_dia`, `iniciar_ruta`, `finalizar_ruta`, `registrar_intento_fallido`, `pendientes_de_la_ruta`, `entrega_de_la_ruta`), `concrecion.py` (`entregas_concretables`, `datos_de_concrecion`, `resumen_de_concrecion`, `repartir`, `concretar_entrega`, `crear_discrepancia`, `intentos_fallidos`, el comprobante y su correo) y `solicitudes.py` (`crear_solicitud`); `entregas.py` suma `monto_a_cobrar`, `estado_de_pago`, `periodos_entregados`, los impedimentos `transportista_en_ruta` (de `maestros` y de la baja de cuenta de `core`) y la parte 4 del paso 50 con las concretadas; `camara.py`, PROD-VNC-CAM 3b.
- **Pantallas** (`views_rutas.py`, `templates/comercial/rutas/`): «Mi ruta», iniciar, finalizar, intento fallido, concretar (con `calcular/`), comprobante, «Concretar retiro» en la lista de entregas, la sección «Ruta de hoy» y la entrada «Mi ruta»; las fichas de la compra-venta (pago), del suministro (entregas con monto, vencimiento y estado de pago, «Entregado» y discrepancias) y del cliente (entregas sin cobrar y discrepancias, también en la baja).
- **Códigos de error** (todos `ValidationError` con `code`): `sin_vehiculo`, `vehiculo_inactivo`, `ruta_ya_iniciada`, `sin_entregas_de_ruta`, `ruta_cambio` (con `agregadas` y `quitadas` en `params`), `ruta_no_iniciada`, `ruta_con_entregas_pendientes` (con `pendientes`), `entrega_no_concretable`, `cantidad_invalida`, `envase_invalido`, `medio_de_pago_obligatorio`, `motivo_obligatorio`, `descripcion_larga` y `cambio_simultaneo`; `PermissionDenied` para `sin_permiso`.

### Pruebas (M1)

- `python manage.py test comercial produccion maestros core inventario contabilidad --keepdb --exclude-tag concurrencia --exclude-tag migracion` (serie): **6618 pruebas**, 1 falla (`test_com_reg_cvt…test_regla_la_venta_no_genera_pago_ni_asiento`, ver «Pruebas existentes cambiadas»), corregida y vuelta a correr: 57 de `test_com_reg_cvt` en verde.
- `python manage.py test comercial --keepdb --tag concurrencia`: **102 pruebas, OK** (incluye las 6 nuevas de `test_concrecion_concurrencia`).
- `makemigrations --check --dry-run`: sin cambios. `manage.py check`: sin problemas.
- Migraciones: `sqlmigrate comercial 0010` crea las cinco tablas, la secuencia y las restricciones (solo `CREATE`/`ALTER`, ningún `DROP` ni reescritura de filas); `contabilidad 0007` y `core 0044` son `no-op` en SQL (solo `choices`). Se aplicaron en las bases de prueba.

### Verifiqué

- El recorrido `test_recorrido_ruta_y_concrecion` (pasos 1 a 9 y 11 de la «Verificación a mano», por rol y estado, con correos y avisos reales): verde.
- Las tres migraciones: SQL leído, sin pérdida de datos, aplicadas en la base de pruebas.
- La suite completa de las apps tocadas y la concurrencia de `comercial`.

### Lo cubre una prueba

- Cada postcondición y extensión de COM-INI-RUT, COM-CNC-ENT y COM-FIN-RUT: `test_com_ini_rut`, `test_com_cnc_ent`, `test_com_fin_rut`.
- El reparto entre orígenes (desempates): `RepartoTests`.
- Los cinco cruces de concurrencia: `test_concrecion_concurrencia`.
- Permisos, botones sin 403, HTMX y sin JavaScript, `calcular/` sin escrituras y las fichas: `test_rutas_vistas`.
- PROD-VNC-CAM 3b: `ProdVncCam3bTests`; `transportista_en_ruta`: `TransportistaEnRutaTests`; COM-CNL-CVT con una entrega concretada real: `ComCnlCvtConEntregaConcretadaRealTests`.

### No pude verificar

- Lo que ve un navegador: CSRF y `Origin`, JavaScript de HTMX, el aspecto en un celular (paso 14).
- El envío real de correo (las pruebas usan el servicio simulado) y el despliegue en Render (paso 15).
- La suite en paralelo (`--parallel`) corrió en mi entorno con `TypeError: cannot pickle 'traceback' object` aun con los clones recreados; en serie corre completa y en verde. No pude aislar la causa (no es una prueba concreta: ninguna falló), y vos la corriste en paralelo sin problema.

### Pruebas existentes cambiadas (anotar en el PR)

- Reemplazadas por `iniciar_ruta_de` (la ruta se inicia de verdad, en vez de la fábrica `vehiculo_en_ruta` o `en_ruta=True`; mismos nombres y mismas verificaciones): `test_com_asg_trp::test_ext_3a_una_entrega_en_curso_no_se_reasigna`, `test_prod_pnf_env::test_ext_3b_una_entrega_en_curso_no_se_modifica`, `test_com_cnl_cvt::test_ext_4a_con_una_entrega_en_curso_no_se_puede_cancelar` y `test_entregas_calculos::test_motivo_3_en_ruta_solo_si_la_fecha_es_hoy`.
- Una entrega «concretada» armada solo con el estado rompía los invariantes nuevos: ahora usan `marcar_concretada` `test_com_cnl_cvt::test_ext_6a_…`, `test_envasado_vistas` (extensión 10a) y `test_prod_pnf_env::test_ext_10a_la_entrega_concretada_o_cancelada_…`.
- `test_modelos_entregas::test_regla_la_cantidad_entregada_es_nula_o_no_negativa`: la concreción de una línea se carga entera (`linea_entrega_concrecion_completa`), así que prueba los cuatro campos juntos.
- `test_com_reg_cvt::test_regla_la_venta_no_genera_pago_ni_asiento`: preguntaba si existía el modelo `PagoCliente`; ahora pregunta que registrar la venta no deja ningún pago.
- Se agregaron al conjunto de invariantes de `verificar_invariantes_de_entregas` (concretadas con monto, pago de la venta) y `verificar_invariantes_de_solicitudes` (nuevo).

### Decisiones tomadas dentro de la tarea (a revisar; van a `docs/temas_abiertos.md`)

1. **Con una rescisión acordada, la concreción no finaliza el detalle ni el contrato** (decisión tuya del 25/11/2026): `rutas.md` (postcondición n) los finalizaba y `suministro.md` / D-64 dicen que terminan «rescindido» por el paso 35.
2. **Errores**: `rutas.md` habla de `ErrorComercial`, que no existe; se usó `ValidationError` con código estable (patrón de COM-05b) y `PermissionDenied` para `sin_permiso`.
3. **Una línea de compra-venta donde no llegó nada** cuenta como **rechazada** (evita una venta «confirmada» con total 0 y un pago de 0).
4. **Exceso de envases**: se confirma con una casilla («Confirmo la cantidad utilizada»); sin ella, `envase_invalido`.
5. **Correos**: el comprobante de venta y el de entrega van en `Entrega.estado_aviso_cliente` (no en `Contrato.estado_comprobante`); el correo del intento fallido reutiliza el del cambio de fecha con el motivo; el paso 50 reintenta también las concretadas pendientes. Una entrega de compra-venta que no es la última no manda correo.
6. **La devolución de la concreción dispara PROD-ASG-CAM** (`on_commit`) y eso puede planificar una entrega del período siguiente de un suministro (con su propio correo): es el encadenamiento de la postcondición f, no un correo duplicado.
7. **Precios**: el Transportista ve el precio y el total (cobra; paso 4 de COM-CNC-ENT). No se ocultan.
8. **Desempate del reparto**: mayor parte decimal, después el que más aporta, la fecha límite más próxima y la menor clave. Con 20, 10 y 10 y 3 perdidas el resultado es 1, 1, 1 (mi prueba inicial esperaba 2, 1, 0 y estaba mal).
9. **`fin_ruta.datos.intentos_fallidos`** son los intentos de ese transportista de hoy: el modelo no guarda desde qué pantalla se registró cada uno y no se agregó una columna.
10. **La entrada «Mi ruta»** se registró en el menú, pero el Transportista es de campo (sin menú lateral): su acceso real es la sección «Ruta de hoy» del Panel de control.

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Concretar entrega (`VIEWS.cncent`, `cncentCalc`) | Recalculaba y deshabilitaba el botón mientras se tipeaba | «Ver resumen» (botón) calcula; el resumen es un bloque aparte con «Confirmar entrega»; sin JavaScript, la misma página | `.claude/rules/interfaz.md` (nada de validar al tipear) y paso 12 |
| Concretar: envases | Un número «usa» por entrega | Por cada envase reservado: utilizados, devueltos (con propuesta) y casilla para confirmar el exceso; sin envasado, una fila por envase habilitado y «No se usaron envases» (sin filas que aparecen solas) | Pasos 9 y 10, extensiones 9a, 10a y 10b |
| Concretar: suministro | Monto con el precio de la venta; sin vencimiento | Precio recalculado con la fecha real y el vencimiento del pago en el resumen | Extensión 3a.2 y 3a.3 |
| Intento fallido (`MODALS.fallo`) | Dejaba la entrega en la lista del día | Pasa a mañana sin transportista y sale de la ruta; el motivo es obligatorio (error bajo el campo) | Extensión 4a.2 |
| Finalizar ruta (`MODALS.finrut`) | Bloqueaba solo con las no marcadas con fallo | Bloquea con toda entrega «a realizar» de la ruta, con «Concretar» e «Intento fallido» de cada una | Regla 1 de COM-FIN-RUT |
| Iniciar ruta (`MODALS.inirut`) | Solo la lista y el peso | Vehículo con capacidad, demoradas primero con sus días, sin envasado señaladas, cantidad de entregas y localidades, y la huella (5c con lo agregado y lo quitado) | Pasos 2 y 3, extensiones 2b, 2c y 5c |
| Mi ruta (`VIEWS.ruta`) | Sin estados vacíos ni de «sin vehículo» o «ruta vencida» | Los tres estados con su aviso; «Concretar» e «Intento fallido» solo con la ruta iniciada (ningún botón lleva a un rechazo) | Extensiones 1a, 1c y 2a; D-30 |
| Pantalla final | Solo un aviso | Total cobrado, estado del correo y «Imprimir comprobante» para el cliente sin correo | Paso 16 y variación 15a |
