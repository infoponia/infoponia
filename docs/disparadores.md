# Disparadores — InfoPonia

Obligaciones que nacen cuando aparece algo en el código: «cuando exista X, hay que hacer Y». Claude Code lo lee cuando
la tarea crea modelos («Límites» de la tarea). Al cerrar una tarea que crea modelos, propone tachar los disparadores que
se cumplieron (con la fecha y el ID de la tarea) y agregar los que nacen (regla M3).

Cada obligación cita su fuente. Las de las cuentas vienen de `docs/casos_de_uso/usuarios.md`, sección «Lo que queda para
más adelante», que sigue la regla de D-04: se agregan cuando se programa la tabla destino.

## Cuando exista Invernadero

1. ~~**Roles del invernadero.**~~ Hecho el 19/11/2026 en MAE-01a (FK nulas en `Invernadero`). Las asociaciones del invernadero con su Agrónomo, Capataz, Vendedor y Técnico se agregan
   en la misma tarea que crea `Invernadero` (D-04). Según D-37, son FK declaradas en `Invernadero` (regla
   A2), no campos en los roles de `core`.
2. ~~**Invernadero del Transportista (R155).**~~ Hecho el 21/11/2026 en MAE-05 (D-55): se asigna desde el invernadero (tabla `TransportistaInvernadero` y bloque «Logística»). Texto original: precondición d, postcondición b y reglas 5 y 7 de USR-ALT-USR; postcondición a de
   USR-MOD-USR; regla 3 de USR-CNS-USR; regla 1 de USR-GST-PRF; la precondición g y la regla 3 de PROD-BAJ-INV (solo los transportistas
   activos impiden la baja, D-39). Lo que dependía de que existiera `Invernadero` ya existe; lo que depende de `Entrega` y `Vehiculo`
   pasa a «Cuando exista Entrega» (puntos 2 y 3).
3. **Ámbito por invernadero de SEG-13.** `estado.md` lo ubicaba en `core/acceso.py`, pero `core` no puede importar una
   app de negocio (D-23). Va como un punto de extensión de `core` en el que `maestros` registra el ámbito (D-37, regla
   A4). En MAE-01 el alcance vive en `InvernaderoQuerySet.en_alcance_de`; sigue abierto hasta que una pantalla fuera de
   `maestros` lo necesite.
4. ~~**Efectos de la baja de una cuenta con invernaderos a cargo.**~~ Hecho el 19/11/2026 en MAE-02b, por los puntos de extensión de
   `core/extensiones.py` (D-43). Texto original: postcondición e de USR-BAJ-USR (queda para el Gerente una alerta «invernadero sin
   {rol}») y regla 4 (antes de confirmar, la baja informa lo que la cuenta tiene asignado). Tiene que bloquear en el orden de
   `docs/patrones/bloqueos.md`, sección «Invernadero» (D-40): la cuenta primero y después los invernaderos.

5. ~~**Alerta con su invernadero.**~~ Hecho el 19/11/2026 en MAE-02a (FK `Alerta.invernadero`); la asociación está anotada en `docs/modelo/maestros.md`, pendientes de MD. Texto original: `Alerta` vive en `maestros` y apunta al invernadero con una clave foránea (D-38). La
   crea MAE-02, después de MAE-01. El modelo no tiene esa asociación: anotarlo en pendientes_MD.

## Cuando exista PerfilOrganizacion

1. ~~**Nombre y color configurables (MAE-04, D-48).**~~ Hecho el 21/11/2026 en MAE-04 (maestros/servicios/perfil.py, registrado en MaestrosConfig.ready()). **Sigue abierto: el logo** (fuera de la ronda, D-45). Texto original: El nombre sale del perfil, por el punto de
   extensión de `core` (D-48); `NOMBRE_ORGANIZACION` (D-25) queda como valor por defecto. El logo deja de ser un ícono fijo cuando el almacenamiento esté resuelto (USR-07, D-20); mientras tanto la
   organización queda sin logo. En el prototipo de producción: `VIEWS.config`, `CFG` y `aplicarMarca`.

## Cuando exista la primera notificación o alerta

Los tres puntos los cerró NOT-01 (20/11/2026, D-42). La campana suma las alertas no leídas con
`Alerta.objects.para(usuario).activas().no_leidas()` (ya existe, MAE-02a) por un punto de extensión de `core`
(`registrar_fuente_de_alertas`). Los dos puntos que siguen nacieron al cerrarla.

1. ~~**Campana y notificaciones del marco.**~~ Hecho el 20/11/2026 en NOT-01 (`core/extensiones.py`, `core/notificaciones.py`, `core/views.py`,
   `core/templates/core/_campana*.html` y `campana.html`; el Administrador no la tiene). Texto original: Se agregan al marco de `core` (D-25).
   Diseño: `notifPop` en `docs/prototipos/cuentas_y_seguridad.html`; `shell`, `alertas` y `myNotif` en el prototipo de producción.
2. ~~**Pendientes del Gerente (D-14).**~~ Hecho el 20/11/2026 en NOT-01 (`alta_usuario` avisa al Gerente nuevo; la ventana de baja del
   Gerente muestra el total y el detalle; `registrar_contador_de_pendientes` y `pendientes_del_gerente`). Texto original: Postcondición d de
   USR-ALT-USR (aviso de resumen al Gerente nuevo con la cantidad de pendientes) y postcondición c de USR-BAJ-USR (cantidad de pendientes
   al dar de baja al Gerente). Sin Gerente activo, generar un pendiente no falla y la notificación sin destinatario se omite.
3. ~~**Avisos a las personas asignadas al invernadero.**~~ Hecho el 20/11/2026 en NOT-01 (`alta_invernadero` y `modificar_invernadero` llaman
   a `notificar_a_varios`; en la modificación, solo a quien queda a cargo, con lo que recibe). Texto original: Postcondición e de
   PROD-ALT-INV y postcondición c de PROD-MOD-INV: cada persona asignada recibe una notificación con el invernadero y lo que recibió (la
   cantidad de órdenes, mantenimientos, contratos y alertas, que sale de `maestros.extensiones.contar_traspaso`). D-38 las dejó sin
   modelar. Nació en MAE-01b.
4. ~~**Abrir una alerta desde la campana (MAE-02c).**~~ Hecho el 22/11/2026 en MAE-02c (`items_de_campana` apunta a `/alertas/<id>/`, que llama a `abrir_alerta`). Texto original: El enlace de cada alerta de la campana lleva a la ficha del invernadero y no llama a
   `abrir_alerta`: la alerta sigue «no leída» y el punto rojo del Gerente (o del Agrónomo) no se apaga. Cuando exista la pantalla de
   consulta de alertas (CU-46, MAE-02c), la campana tiene que llevar a ese detalle (que sí llama a `abrir_alerta`), o la
   `ItemDeAlerta.url` de `maestros.servicios.invernaderos.items_de_campana` tiene que apuntar a él. Va junto con el pendiente de
   pendientes_CU de la sección de CU-46 (abrir la alerta la marca «leída», regla 7 de 8.18). Nació en NOT-01.
    ~~**Queda para MAE-02d**~~ Hecho el 22/11/2026 en MAE-02d (`items_de_campana`; D-62, tercera enmienda): la campana pasa por
   `alertas:ir` cuando el enlace es de una app, y lleva directo al detalle con el enlace por omisión (ya lo hacía MAE-02c).
5. **Lo que espera una resolución del Gerente.** Cada app que cree algo que queda esperando al Gerente (órdenes de compra por aprobar,
   solicitudes de revisión; D-14) registra su contador en `AppConfig.ready()` con
   `core.extensiones.registrar_contador_de_pendientes(funcion)`, con `funcion() -> list[tuple[str, int]]` (descripción y cantidad; sin
   nada pendiente, lista vacía). Así el aviso al Gerente nuevo (`alta_usuario`) y la ventana de baja del Gerente los cuentan sin tocar
   `core`. Si además quien genera algo y no hay Gerente activo debe avisarle a quien lo genera que quedará pendiente (D-14), lo hace
   con `core.notificaciones.notificar` y no con `notificar_al_gerente`, que en ese caso no hace nada. Hoy solo `maestros` registra el suyo
   (alertas activas para el Gerente). Nació en NOT-01.


## ~~Cuando exista Pedido~~

**Hecho el 24/11/2026 en CMP-02b** (`compras/servicios/registrantes.py`: `efecto_de_baja_de_cuenta` y `asignaciones_de_cuenta`; D-87). Texto original:

1. ~~**Baja de un Agrónomo.**~~ Postcondición f de USR-BAJ-USR: se cancelan sus pedidos sin orden de compra generada y se avisa. Regla 4:
   la baja lo informa antes de confirmar. Se conecta con `registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta` de
   `core/extensiones.py` (D-43); bloquea sus filas después del invernadero y en orden de id.

## Cuando exista Entrega

1. **Baja de un Transportista.** Postcondición g de USR-BAJ-USR: sus entregas a realizar quedan sin transportista. Regla 4: la baja
   lo informa antes de confirmar. Se conecta con `registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta` de
   `core/extensiones.py` (D-43).
   **Planificado (lote C5a):** COM-05a, con la alerta «entrega sin transportista» y el aviso al Vendedor (`docs/casos_de_uso/comercial/entregas.md`,
   «Lo que completa a otras tareas»). **Hecho el 24/11/2026 en COM-05a1.**
2. **Transportista en ruta o con entregas (D-55, nace en MAE-05).** Reglas 9 y 10 de PROD-MOD-INV y precondición d de USR-BAJ-USR.
   `comercial` registra:
- `maestros.extensiones.registrar_impedimento_de_transportista`, con los códigos `transportista_en_ruta` y
     `transportista_con_entregas`;
- `core.extensiones.registrar_impedimento_de_baja_de_cuenta`, con el código `transportista_en_ruta`.
   Contrato: `docs/api/extensiones_de_maestros.md`, sección «Transportistas». También la regla de COM-ASG-TRP: una entrega del día
   cuyo transportista está en ruta no se reasigna.
   **Planificado (lote C5a):** `transportista_con_entregas`, COM-05a1. `transportista_en_ruta` (los dos puntos), **COM-06a (lote C6)**
   (`docs/casos_de_uso/comercial/rutas.md`, «Lo que completa a otras tareas»). La regla de COM-ASG-TRP, **COM-05b (lote C5b)**: la
   extensión 3a (`entrega_en_curso`; `docs/casos_de_uso/comercial/entregas.md`, «COM-ASG-TRP»).
   **Hecho el 24/11/2026 en COM-05a1:** `transportista_con_entregas`. **Hecho el 25/11/2026 en COM-05b:** la regla de COM-ASG-TRP (`entrega_en_curso`). Sigue abierto `transportista_en_ruta` (COM-06a).
3. **Logística de la ficha del invernadero (D-55, nace en MAE-05).** Regla 3 de PROD-CNS-INV: `comercial` registra
   `maestros.extensiones.registrar_logistica_de_transportista` con el vehículo, la situación (en ruta o no) y las entregas a
   realizar de cada transportista. Con el registrante, «Logística» muestra las tres columnas de `logistica(inv, ger, true)` del
   prototipo `docs/prototipos/produccion/logistica_transportista.html`.
   **Planificado (lote C1):** COM-01 registra el punto con el vehículo y la situación (en ruta) y `entregas_a_realizar = 0`; COM-05a completa
   las entregas a realizar y `url_entregas` (la lista de entregas con `?transportista=<id>`) en el mismo registrante (admite uno solo).    **Hecho el 23/11/2026 en COM-01 (parte de COM-01):** `comercial` registra el punto con el vehículo y la situación (en ruta) y `entregas_a_realizar = 0` y `url_entregas = None`; sigue abierto lo de COM-05a (las entregas a realizar y su URL, en el mismo registrante). **Hecho el 24/11/2026 en COM-05a1.**
4. **Venta que sale toda de cámara (nace en COM-02, lote C2).** Postcondición g de COM-REG-CVT: si todas las reservas de una compra-venta
   quedan «lista para entrega», InfoPonia planifica la entrega (COM-PNF-ENT). COM-05 suma esa llamada al final de `registrar_compra_venta` y
   su paso diario 50 planifica también las ventas que ya estaban así.
   COM-PCT-SUM (postcondición f) y PROD-PRR-SUM hacen lo mismo con un período de suministro (lote C3).
   **Planificado (lote C5a):** COM-05a, con `programar_planificacion_*` y `transaction.on_commit` (D-66, punto 5); el paso 50 recupera lo
   que no se planificó. **Hecho el 24/11/2026 en COM-05a1.**
5. **Fin de un detalle y de un suministro por entrega (nace en COM-03, lote C3).** Un `DetalleSuministro` pasa a «finalizado» al concretarse
   la entrega de su último período, y el `Suministro` cuando todos sus detalles están finalizados (regla 5 de 8.11). COM-06, al concretar,
   lo verifica y cambia los estados. COM-MOD-SUM ya finaliza un contrato que se queda sin detalles vigentes ni períodos pendientes.
   **Planificado (lote C6):** COM-06a, paso 8 de «Concretar» (`rutas.md`).
6. **Cierre de una rescisión (nace en COM-03, lote C3).** El paso diario 35 (`cerrar_rescisiones`) pasa a «rescindido» un suministro con
   rescisión acordada el día siguiente a su última entrega conservada. COM-05 (o COM-06) le suma la condición «sin entregas del contrato
   a realizar», para no cerrar un contrato con una entrega atrasada.
   **Hecho en COM-03b (24/11/2026):** el paso 35 existe y cierra sin esperar entregas. **Planificado (lote C5a):** COM-05a (la condición en `cerrar_rescisiones`). **Hecho el 24/11/2026 en COM-05a1.** Sigue abierto el punto 1 de «Cuando se programen COM-05a1 y COM-06» (`periodos_conservados`).

7. **Lo que deja COM-04 para las entregas (nace en el lote C4).** COM-05 lo suma al crear `Entrega`:
   - PROD-ASG-CAM: la condición «sin detalle de entrega en una entrega no cancelada» de sus candidatos y el paso 9 (COM-PNF-ENT); lo mismo
     después de PROD-CNC-CSC (postcondición n), de COM-DCD-FLT (paso 7) y de PROD-CNL-ORD (postcondición i);
   - PROD-VNC-CAM, extensión 3a: quitar las líneas recortadas de su entrega «a realizar» y cancelar la entrega que quede vacía (con
     PROD-CNL-ORD); lo mismo en la merma en cámara (10c);
   - COM-CNL-CVT anula el enlace de decisión de la venta que se cancela (`anular_enlaces_de`, D-65).
   Y COM-06: PROD-VNC-CAM 3b (entrega en curso); resolver «partida por vencer» cuando una entrega agota la partida
   (`resolver_aviso_de_partida`); la devolución a una partida vencida (regla 29 de 8.6); el tipo `confirmacion_entrega` del enlace del
   cliente (D-65) para COM-CNF-ENT; la causa «daño en la entrega».
   **Planificado (lote C6):** PROD-VNC-CAM 3b, `resolver_aviso_de_partida` y la devolución a una partida vencida, **COM-06a**; la causa
   «daño en la entrega» la crea **COM-04a** (D-68, punto 3) y la usa COM-06a; el tipo `confirmacion_entrega`, **COM-06b**.
   **Planificado (lote C5a):** COM-05a hace los dos primeros guiones (candidatos «sin entrega» y los disparadores; las líneas quitadas y la
   entrega vacía cancelada, D-66 puntos 4 y 9). El tercero (el enlace de COM-CNL-CVT) es de **COM-05b** (**planificado, lote C5b**:
   postcondición e de COM-CNL-CVT, `anular_enlaces_de(venta)`; `docs/casos_de_uso/comercial/compra_venta.md`, «COM-CNL-CVT»).
   **Hecho el 24/11/2026 en COM-05a1:** los dos primeros guiones (candidatos «sin entrega», los disparadores, las líneas quitadas y la entrega vacía cancelada). **Hecho el 25/11/2026 en COM-05b:** el tercero (`anular_enlaces_de(venta)` en COM-CNL-CVT).

8. **Lo que deja COM-05a (nace en el lote C5a; desde el C5b, COM-05a es COM-05a1 y COM-05a2).**
   - **COM-05b** (**hecho el 25/11/2026**): COM-ASG-TRP reutiliza `candidatos_para`, `peso_de_entregas` y la acción `asignacion_transportista`, resuelve la alerta
     «entrega sin transportista» y le cambia el enlace (a la asignación, extensión 1b); suma «Asignar» y «Cambiar transportista» a la lista de
     entregas. COM-CNL-CVT cancela las entregas «a realizar» de la venta con `cancelar_entrega_incluida`.
   - **COM-06:** COM-INI-RUT usa `peso_de_entregas` («Peso de la ruta») y bloquea el invernadero como semáforo (D-66, punto 11); COM-CNC-ENT
     carga `cant_entregada` y `monto_pagar`, recalcula el precio de suministro y confirma los envases. ~~**El exceso de envases** (regla 21 de 8.8) choca con dos restricciones de
     `ReservaInsumo` de PRD-01: COM-06 las tiene que relajar para las órdenes de tipo `entrega`, con su migración.~~ **Corregido en el lote C6
     (D-68, punto 2):** una restricción de la base no puede mirar el tipo de la orden; las restricciones **no cambian**: la utilizada se
     topea en la reservada y el exceso va en el consumo del envase. «Concretar retiro» en la lista de entregas; `transportista_en_ruta`.
     **Planificado (lote C6):** todo, COM-06a (`rutas.md`, «Cómo se aplica»).

9. **Lo que deja COM-05b (nace en el lote C5b).** **Hecho el 25/11/2026 en COM-05b:** el rechazo `venta_con_entregas_concretadas` (con una prueba de fábrica) y la cancelación de los confirmados sin entregar; siguen abiertos los puntos de abajo para COM-06 y COM-08b.
   - **COM-06:** COM-CNL-CVT con entregas concretadas (extensión 6a) se vuelve posible. Hasta COM-08, el servicio sigue rechazando
     `venta_con_entregas_concretadas` (lo deja COM-05b, con una prueba de fábrica); COM-06 lo confirma con una entrega concretada real.
     COM-CNL-CVT cancela solo los detalles **sin** línea en una entrega concretada (D-67, punto 4): COM-06 suma esa prueba con datos reales.
     COM-INI-RUT toma el invernadero de origen antes de cambiar el vehículo (D-66 punto 11): así COM-ASG-TRP y COM-CNL-CVT ven bien si una
     entrega está en curso.
   - **COM-08:** con `PagoCliente` (MD-136), la extensión 6a de COM-CNL-CVT: el cobro de lo entregado en la misma operación, la venta a
     «concretada» con los datos de la cancelación y el cobro en el comprobante. El asiento del cobro queda fuera de la ronda (D-57).
     Desde el lote C6, `PagoCliente` lo crea **COM-06a** (D-68, punto 4): COM-08 suma R154 y reescribe C7.
     **Planificado (lote C8; D-94, puntos 1 y 14):** la extensión 6a, **COM-08b** (`compra_venta.md`, «La extensión 6a (COM-08b)»).
   **Planificado (lote C6):** lo de COM-06, **COM-06a** (`rutas.md`, «Lo que completa a otras tareas», fila COM-05b).

10. **Lo que deja COM-06 (nace en el lote C6; D-68).**
   - **COM-06b:** el enlace `confirmacion_entrega` en el correo de la concreción de un suministro (postcondición l de COM-CNC-ENT; COM-06a
     manda el comprobante sin enlace). **Planificado (lote C6):** COM-06b (`confirmacion.md`, «El enlace de confirmación»).
   - **COM-07:** COM-EVL-DSC resuelve la `DiscrepanciaEntrega` y COM-RSV-QJA las quejas; las dos cambian el enlace de su alerta (hoy, la
     ficha del suministro) por la pantalla de la solicitud; COM-RSV-QJA usa `intentos_fallidos` (D-68, punto 6); `monto_a_cobrar` ya resta
     las indemnizaciones de las solicitudes aceptadas.
     **Planificado (lote C7; D-69, punto 1):** las solicitudes, **COM-07a** (`solicitudes.md`, «Lo que completa a otras tareas»: el
     registrante del enlace de las dos alertas, `monto_a_cobrar` con lo **descontado**, D-69 punto 9); COM-RSV-SUM, **COM-07b**
     (`resolucion.md`).
   - **COM-08:** `Entrega.pago` (R154) y C7 de `PagoCliente` como {xor}; `estado_de_pago` con «pagada» (MD-125, MD-136) y la alerta «pago en
     mora» (COM-VNC-PAG); el cobro en COM-ATN-ENR (regla 1) y su regla 5.
     **Planificado (lote C8):** todo en **COM-08a** (`cobranza.md`). R154 no es `Entrega.pago`: es la tabla `LineaPago` (D-94, punto 2).
   - **Ronda de contabilidad:** los asientos de la entrega, de sus mermas y de sus consumos (postcondiciones e, g y h de COM-CNC-ENT); el aviso
     a quien registra los asientos manuales (postcondición b de COM-ATN-ENR).

11. **Lo que deja COM-07 (nace en el lote C7; D-69).**
   - **COM-07b:** `resoluciones.resolver_si_corresponde` deja de ser neutra (COM-07a la llama con `on_commit` en cada aceptación) y carga
     `Suministro.solicitud_resolucion`, con lo que la extensión 2a de COM-ANL-SRV se da con datos reales. **Planificado (lote C7):** COM-07b
     (`resolucion.md`, «Lo que completa a otras tareas»).
   - **COM-08:** una entrega de suministro «pagada»: la extensión 6a de COM-EVL-DSC y de COM-RSV-QJA (todo se reintegra), el cobro como cambio
     de la huella (8b) y la extensión 2b de COM-ANL-SRV (`entrega_cobrada`), hoy probados con `mock.patch` de `estado_de_pago`, con datos
     reales; `Anulacion.pago` y `cliente_pago_en_fecha` (COM-ANL-CBR, MD-135) y la restricción «exactamente uno de `solicitud` y `pago`»;
     COM-REG-CBR cobra `monto_a_cobrar`, que ya resta lo descontado; el cobro bloquea la entrega después del suministro
     (`docs/patrones/bloqueos.md`, «Resolver o anular una solicitud»).
     **Planificado (lote C8):** la entrega pagada con datos reales y el cobro en la huella, **COM-08a** (`cobranza.md`, «Lo que completa a
     otras tareas»; el cobro bloquea el invernadero de origen y la entrega, sin el suministro: `bloqueos.md`, «Cobranza»); `Anulacion.pago`,
     `cliente_pago_en_fecha` y las restricciones de `Anulacion`, **COM-08b**.
   - **Ronda de contabilidad:** el asiento de cada indemnización (simple o compuesto, con lo descontado y lo reintegrado que guarda la
     solicitud), el contraasiento de cada `Anulacion` y el asiento de la multa por resolución (MD-123).

## Resolución de un contrato con rescisión acordada (COM-03, lote C3)

COM-07 (COM-RSV-SUM): si un suministro con rescisión acordada supera sus incumplimientos tolerados antes de la última entrega, se resuelve
igual, con su multa (la resolución prevalece, regla «Mientras se entregan…» de COM-RSC-SUM). La resolución deja los datos de la rescisión
como estaban (quedan en la ficha como historia) y el paso 35 ya no lo toma, porque no está «vigente».
**Planificado (lote C7):** COM-07b (`docs/casos_de_uso/comercial/resolucion.md`, paso 4.5; el paso 33 corre antes del 35, D-69 punto 7).

## Cuando se programen COM-05a1 y COM-06 — nace con COM-03b (24/11/2026)

1. **Rescisión después de una modificación.** `periodos_conservados` (`comercial/servicios/suministros.py`) mira solo los detalles «vigentes», como dice `suministro.md`: los períodos de la ventana que quedaron en un detalle finalizado por una modificación y todavía se entregan no cuentan. Un contrato así puede quedar «rescindido» en el acto con entregas pendientes. Con «el cierre espera las entregas a realizar» (punto 6 de «Cuando exista Entrega») la fecha de la última entrega y el cierre tienen que mirar también las entregas de esos detalles.
2. **Reenvío de la constancia de «rescisión sin efecto».** `comprobantes.reenviar_comprobante` deduce la constancia de la rescisión de `motivo_rescision`; después de dejarla sin efecto no queda marca y reenvía el comprobante común. Si hace falta reenviar esa constancia, hay que guardar qué documento quedó pendiente (decisión y migración aparte).

## Cuando exista Cosecha

1. ~~**Pantalla de concretar cosecha.**~~ Resuelto el 21/11/2026 (lote C1 de «Comercial 1»): está en el prototipo comercial,
   `docs/prototipos/comercial/comercial_y_cosecha.html` (`VIEWS.capcsc`, `capcscCalc`). Texto original: El prototipo de producción deriva
   esa pantalla a otro archivo (InfoPonia11), que no está en el repo. Hay que traerlo a `docs/prototipos/produccion/` antes de escribir esa
   tarea (D-24).

## Cuando un módulo de negocio audite por primera vez

1. **Formato y clasificación (D-36).** Detalle con «cambios» y «datos», referencias con `referencia()`, nombres visibles
   en `RegistroAuditoria.ETIQUETAS` y cada acción nueva en `ACCIONES_DE_NEGOCIO`. Cómo hacerlo: `docs/patrones/auditoria.md`.

## Cuando exista SectorProduccion

1. ~~**Sectores del invernadero.**~~ Hecho el 20/11/2026 en MAE-03 (`Invernadero.tiene_sectores` mira los sectores activos o fuera de servicio, pestaña «Sectores» y tarjeta «Capacidad» de la ficha, y la baja del invernadero pasa sus sectores a inactivos con un log por sector, por `registrar_efecto_de_baja`). Texto original: la marca «sin sectores» (`Invernadero.tiene_sectores`, hoy `False`), la capacidad y la pestaña de sectores de la ficha (regla 3 de PROD-CNS-INV) y la postcondición b de PROD-BAJ-INV (los sectores pasan a inactivos). Nació en MAE-01a.


## Cuando exista una ocupación de sector, una variedad con semilla o un hardware (registrantes de los puntos de extensión de MAE-03)

MAE-03 creó los puntos de extensión de sectores y cultivos (`docs/api/extensiones_de_maestros.md`) el 20/11/2026 **sin registrantes** (probados con registrantes falsos). Cada tarea que crea lo que falta se registra en el `AppConfig.ready()` de su app y prueba su registrante:

1. **PRD-01 y PRD-02 (`produccion`) — hecho el 22/11/2026 (PRD-01: los cinco puntos, con lotes y siembras; PRD-02: las transiciones, en los agujeros comprometidos, el contenido, el perfil y los avisos de cambio de tipo):** `registrar_agujeros_de_sector` (ocupados y comprometidos), `registrar_impedimento_de_baja_de_sector`
   (agujeros ocupados y comprometidos, con los lotes y órdenes), `registrar_contenido_de_sector` (lotes y órdenes),
   `registrar_perfil_de_sector` y `registrar_aviso_de_cambio_de_tipo` (lotes que deben pasar por la etapa y siembras a realizar).
   Al reservar agujeros (`PRD-01` y `PRD-02`), llamar a `bloquear_sectores`, que ya bloquea el invernadero activo y después los sectores activos, y rechaza con `sector_no_disponible`.
 2. ~~**PRD-04 (`produccion`):** `registrar_efecto_de_vuelta_a_servicio`~~ (hecho el 23/11/2026, PRD-04: los tres registrantes, `poner_fuera_de_servicio` y el Inicio del Agrónomo; el filtro por invernadero del Inicio no se hizo, ver el disparador nuevo). El texto original sigue igual: [dejar el resto de la línea tal cual y tachar también las tres líneas que le siguen con `~~`].
 (cierra el registro «Fuera de servicio» y escribe la bitácora),
   `registrar_efecto_de_baja_de_sector` (punto nuevo de `maestros`, D-51 punto 7) y `registrar_efecto_de_baja` (cierra los registros abiertos al dar de baja el invernadero; en el lote 4 se había dicho que no registraba nada)
   y el caso de uso PROD-PNR-FDS, que es el que produce el estado «fuera de servicio». También el Inicio del Agrónomo, como sección registrada
   con `registrar_seccion_de_inicio` de `core/extensiones.py` (D-43; la alerta de insumos y de merma del prototipo salen de ahí).
3. ~~**INV-03 (`inventario`):** `registrar_semillas_de_cultivo` y `registrar_uso_de_cultivo`, más las columnas de `Variedad`. Contrato de bloqueo: cultivo → variedad.~~ (hecho el 22/11/2026, INV-03; también registró `registrar_variedades_de_cultivo`, la tabla de cada tarjeta de cultivo)
4. ~~**Módulo IoT (`iot`) — hecho en la documentación el 20/11/2026, se implementa en IOT-02:** `registrar_impedimento_de_baja_de_sector` con `hardware_activo` (códigos y textos de PROD-BAJ-SCT, regla 3)
   y `registrar_contenido_de_sector` con el hardware.~~ (hecho el 22/11/2026, IOT-02: `IotConfig.ready()` registra los dos)

## Cuando existan lotes, órdenes de trabajo y contratos (puntos de extensión de variedades, lote 3)

INV-03 crea los tres puntos de variedades de `docs/api/extensiones_de_inventario.md` («Variedades») **sin registrantes**: sin ellos,
ninguna variedad tiene lotes, órdenes ni contratos, y todas pueden modificarse y darse de baja sin impedimentos. Cada tarea que crea lo
que falta se registra en el `AppConfig.ready()` de su app y prueba su registrante:

1. ~~**PRD-01 (`produccion`):**~~ Hecho el 22/11/2026 en PRD-01 (las órdenes de transición las sumó PRD-02 en `uso_de_variedad`, también el 22/11/2026). Texto original: `registrar_uso_de_variedad` (lotes de la variedad, lotes activos por invernadero, órdenes de siembra y de
   transición a realizar), `registrar_variedades_presentes` (variedades de lotes activos y de órdenes de siembra a realizar por
   invernadero: la misma definición del «umbral efectivo» de PROD-PNF-SMB) y `registrar_impedimento_de_baja_de_variedad` con los códigos
   `lotes_activos` y `ordenes_a_realizar`. PRD-01 también llama a `inventario.servicios.variedades` (`docs/api/variedades.md`) para
   leer la variedad, su ciclo y su semilla; no consulta las tablas a mano.
2. ~~**`comercial` (ronda futura):**~~ **Hecho el 23/11/2026 en COM-02 (compra-ventas) y COM-03a (suministros vigentes; texto «Tiene contratos abiertos: N compra-ventas y M suministros.»).** Texto original: `registrar_impedimento_de_baja_de_variedad` con el código `contratos_abiertos` (contratos vigentes
   o abiertos con un detalle de la variedad; precondición f de PROD-BAJ-VAR). **Hasta entonces la precondición f no se verifica** (no
   hay contratos): se anota en el cierre de INV-03 y en `docs/temas_abiertos.md`.
   **Lo programa COM-02 (lote C2)** para las compra-ventas abiertas o pendientes de decisión; COM-03 suma los suministros vigentes. (COM-03, lote C3: detalles vigentes de la variedad).

## Cuando exista PRD-01 (lotes y órdenes reales de variedades) — nace con INV-03 (22/11/2026)

1. ~~**Prueba de punta a punta con los registrantes reales.**~~ Hecho el 22/11/2026 en PRD-01 (`produccion/tests/test_registrantes_de_inventario.py`: baja, perfil, umbral efectivo y stock libre con lotes y órdenes verdaderos). Texto original: Las pruebas de INV-03 usan registrantes falsos de `registrar_uso_de_variedad`, `registrar_variedades_presentes` y `registrar_impedimento_de_baja_de_variedad`. PRD-01 agrega una prueba de punta a punta con los reales (modificar, dar de baja y advertencia de rangos con lotes verdaderos).
2. Decidir si `reactivar_variedad` debe reevaluar las alertas de las existencias que quedaron activas (hoy solo lo hace la baja).


## Cuando exista SistemaIoT

0. ~~**Traspaso del Técnico y órdenes de mantenimiento** (D-53, D-73): **IOT-07** (antes «IOT-05») agrega el `CheckConstraint` de la prioridad obligatoria en el mantenimiento (el valor `mantenimiento` de `OrdenTrabajo.Tipo` lo crea PRD-01, D-67 punto 1) y su `registrar_traspaso` para el rol Técnico (el punto ya admite varios registrantes y recibe el rol). Si `maestros/extensiones.py` no entrega el rol a quien registra, es una corrección chica dentro de IOT-07 (hoy ya lo entrega: `traspasar(actor, invernadero, rol, saliente, entrante)`). **Planificado: IOT-07** (`docs/tareas/iot/IOT-07-orden-de-mantenimiento.md`; `docs/casos_de_uso/iot/mantenimiento_automatico.md`, «Traspaso del Técnico»; D-79, punto 9).~~ (hecho el 24/11/2026, IOT-07: la restricción `ordentrabajo_prioridad_en_mantenimiento` y `traspasar_mantenimientos` con `contar_traspaso`, registrados en `IotConfig.ready()`)
0. ~~**Envío de correo desde `iot`** (D-54, D-71): usar `core.correo.enviar_correo`, nunca `_enviar_correo`. Lo deja USR-10 y lo usa la revisión periódica de **IOT-04**.~~ (hecho el 23/11/2026, IOT-04: `enviar_correos_pendientes`)
1. ~~**IoT del invernadero.** `Invernadero.tiene_sistema_iot` (hoy `False`), la alerta y el campo del Técnico (regla 5 de
   PROD-ALT-INV) y la precondición h de PROD-BAJ-INV. Nació en MAE-01a. La precondición h se conecta con
   `registrar_impedimento_de_baja`. **Planificado: IOT-02** (`docs/tareas/ronda_iot_1.md`, sección 5): suma en `maestros/extensiones.py` un punto
   de extensión para el estado del IoT del invernadero y lo registra; `tiene_sistema_iot()` lo consulta.~~ (hecho el 22/11/2026, IOT-02: `registrar_estado_iot`; la alerta del Técnico y la precondición h quedan conectadas)

## Cuando existan actuadores, comandos y reglas del IoT (lotes I1 e I2a)

Funciones que IOT-01 e IOT-02 dejan escritas y que hoy devuelven «nada» o no muestran algo porque falta la tabla o el comportamiento que las
alimenta. Cada una tiene su docstring «Se completa en IOT-NN». Fuente: los extractos de `docs/casos_de_uso/iot/`, «Para más adelante».

1. **Tipos de actuador** (`docs/casos_de_uso/iot/tipos_de_actuador.md`).
   - ~~IOT-02: el aviso de equipos afectados (regla 6 de IOT-MOD-TAC), la compatibilidad sobre actuadores reales (regla 9) y el conteo de la
     baja (regla 2 de IOT-BAJ-TAC) con actuadores registrados. Al crear un actuador, llamar antes a `bloquear_tipo_activo(tipo_id)` (`iot/servicios/tipos_actuador.py`; contrato de D-40).~~ (hecho el 22/11/2026, IOT-02: `recalcular_compatibilidad`; el aviso y el conteo ya los tenía IOT-01)
   - ~~IOT-05: `acciones_en_uso(tipo)` (devuelve `dict[int, list[UsoDeAccion]]`: por id de acción, sus usos con código `RGL-n` o `CMD-n` y valor) y `acciones_con_historial(tipo)` por comandos (pendientes y con historial).~~ (hecho el 23/11/2026, IOT-05: una sola consulta para toda la lista de tipos)
   - ~~IOT-06: `acciones_en_uso(tipo)` por reglas de actuación activas.~~ (hecho el 24/11/2026, IOT-06)
2. **Sistema IoT** (`docs/casos_de_uso/iot/sistema_iot.md`). ~~IOT-06: desactivar, activar y dar de baja~~ (hecho el 24/11/2026, IOT-06); ~~IOT-07:
   `ordenes_a_realizar_del_sistema(sistema)` (precondición d de IOT-BAJ-SIS).~~ (hecho el 24/11/2026, IOT-07)
3. **Hardware** (`docs/casos_de_uso/iot/hardware.md`).
   - ~~IOT-03: la última lectura y la situación por lecturas en la lista y la ficha; los identificadores anunciados (`EquipoAnunciado`) y la
     compatibilidad contra anuncios reales; `tiene_lecturas(sensor)` con lecturas reales. **Al anunciar equipos, la API llama a
     `recalcular_compatibilidad`** (`iot/servicios/compatibilidad.py`) con los actuadores del sistema: es la única función que calcula y escribe la compatibilidad (D-82: bloquea
     los invernaderos en orden, después del tipo).~~ (hecho el 23/11/2026, IOT-03: `resumen_de_equipos` y `situacion_de` por alertas, «Último dato» en la lista y la ficha, `anuncios.registrar_anuncio` y `tiene_lecturas`)
   - ~~IOT-05: `tiene_comandos(actuador)`, `tiene_comando_pendiente(actuador)`, «Comando pendiente» y el historial de comandos de la ficha.~~ (hecho el 23/11/2026, IOT-05)
   - ~~IOT-06: `tiene_reglas(equipo)` y las reglas que usan el equipo en la ficha; la baja (IOT-BAJ-HDW), **que se suma a `acciones_permitidas(actor, equipo)`**
     (`iot/servicios/hardware.py`: hoy no ofrece «Dar de baja», para que ningún botón lleve a un 403); y sumar `temp-vieja` (un sensor dado de baja) al cargador de datos de verificación
     de `iot` (`iot/verificacion.py`) con ese servicio.~~ (hecho el 24/11/2026, IOT-06; lo del cargador no se hizo: D-95 retiró los cargadores de datos de verificación)
   - ~~IOT-07: las órdenes de mantenimiento al volver a activar (regla 8 de IOT-MOD-HDW) y en la ficha; la precondición d de la baja.~~ (hecho el 24/11/2026, IOT-07: `ordenes_al_volver_a_activar`, `mantenimientos_del_equipo` y el impedimento de baja)
4. ~~**Enlaces de las alertas del IoT** (D-62): `registrar_enlace_de_alerta` hacia la ficha del equipo, el alta con `?identificador=` o el
   panel. **IOT-04.**~~ (hecho el 23/11/2026, IOT-04: `enlaces_de_alertas_iot`)
5. **API del nodo** (`docs/casos_de_uso/iot/entregar_informacion.md`, «Reparto»; lote I2a). IOT-03 las deja escritas sin hacer nada:
   - ~~IOT-05: `explica_un_comando(actuador, estado)` en `iot/servicios/estados.py` (hoy, falso: D-75 punto 1); en modo `local`, no entregar
     comandos (extensión 1b.2); las rutas de comandos del contrato (`docs/api/nodo/`, lote I3).~~ (hecho el 23/11/2026, IOT-05)
   - ~~IOT-06: `evaluar_reglas_de_la_lectura(contexto, sensor, telemetria)` en `iot/servicios/lecturas.py` (paso 6 y 6a a 6d);
     `al_volver_a_remoto(sistema)` en `iot/servicios/nodo.py` (1b.3); el reinicio de las reglas cuando el invernadero se queda sin umbral
     efectivo (5c).~~ (hecho el 24/11/2026, IOT-06)

6. **Orden de bloqueos con un tipo de actuador (D-82).** ~~IOT-05~~ (hecho el 23/11/2026: `emitir_comando`, con su prueba de concurrencia), ~~IOT-06~~ (hecho el 24/11/2026: alta, modificación y reactivación de reglas, con su prueba de concurrencia) e IOT-07 (hecho el 24/11/2026: ninguno de sus flujos toma el tipo de actuador, así que D-82 no aplica): todo flujo que toque un actuador y su tipo toma primero el tipo
   (`bloquear_tipo_activo`) y después el invernadero, el sistema y el equipo (excepción a D-40 y a `docs/patrones/bloqueos.md`). Nació en IOT-02.
7. **El panel de monitoreo** (`iot/servicios/monitoreo.py` y `iot/templates/iot/monitoreo/_panel.html`). ~~IOT-05~~ (hecho el 23/11/2026): «Comandos pendientes» (indicador y columna de actuadores) y «Emitir comando» desde la fila de cada actuador a quien opera
   (regla 11 de IOT-CNS-LEC); IOT-06: el enlace a las reglas de actuación. Nació en IOT-04.

## ~~Cuando exista InsumoInvernadero~~ (cerrado el 21/11/2026, INV-02)

(INV-01 creó el modelo; INV-02 conectó lo de abajo.)

1. ~~**Insumos del invernadero.** Postcondición c y precondición f de PROD-BAJ-INV. Nació en MAE-01a. La c (y el log por insumo
   de la f) se conecta con `registrar_efecto_de_baja`; la f, con `registrar_impedimento_de_baja`.~~ Hecho en INV-02: `InventarioConfig.ready()` registra los dos ganchos.

## ~~Cuando se programe INV-02 (catálogo)~~ (cerrado el 21/11/2026, INV-02)

1. ~~**Botón y pestaña.** El catálogo agrega «Habilitar en un invernadero» (regla 7 de CMP-ALT-INS y regla 4 de CMP-CNS-INS) y la pestaña «Existencias de insumos» como primera; `/inventario/` pasa a redirigir a ella (hoy va al catálogo). Nació en INV-01.~~ Hecho en INV-02.

## ~~Cuando exista Variedad y Semilla (INV-03)~~ (cerrado el 22/11/2026, INV-03)

1. **Semillas en el catálogo.** `es_semilla` ya marca las filas «Viene del alta de la variedad»; INV-03 las enlaza con su variedad y mantiene su alta, modificación y baja. Nació en INV-01.

## Cuando exista Lote, OrdenTrabajo o StockCosechado

1. **Baja del invernadero y ficha.** Precondiciones c, d y e de PROD-BAJ-INV y las pestañas de lotes y de cámara de la
   ficha (la pestaña de lotes la registra PRD-01 con `registrar_pestana_de_invernadero`, ver `docs/api/extensiones_de_maestros.md`; la de cámara queda fuera, D-45). Se conectan por el punto de extensión `maestros/extensiones.py` (D-37, regla A4), creado en MAE-01b. Se registra con
   `registrar_impedimento_de_baja` en `AppConfig.ready()`. Todo caso de uso que cree algo que impide la baja llama a
   `bloquear_invernadero_activo` antes de crearlo (contrato de D-40 y de `docs/patrones/bloqueos.md`). Nació en MAE-01a.
   **Hecho el 22/11/2026 en PRD-01:** los impedimentos `lotes_activos` y `ordenes_a_realizar` (de todos los tipos de orden, D-64 punto 12) y la
   pestaña «Lotes activos». ~~Sigue abierto lo de la cámara (`partidas_en_camara`, COM-04)~~ Hecho el 24/11/2026 en COM-04a: el impedimento `partidas_en_camara` de la baja del invernadero y las cosechas en la bandeja y la lista; ~~la pestaña «Cámara» sigue siendo de COM-04b~~ Hecho el 24/11/2026 en COM-04b: la pestaña «Cámara» (`registrar_pestana_de_invernadero("camara", …)`; la ven en la práctica el Gerente y el Agrónomo, porque la ficha del invernadero no abre para el Capataz ni el Vendedor: `docs/temas_abiertos.md`).
   **COM-02 (lote C2):** las cosechas «a realizar» impiden la baja (las cuenta el registrante de PRD-01 si cuenta por `OrdenTrabajo`; si no,
   COM-02 las suma) y PROD-ASG-STK bloquea los invernaderos antes de crearlas. Las partidas en cámara y su pestaña: COM-04.
   **Planificado (lote C4):** COM-04 registra la pestaña «Cámara» (desde `comercial`, porque muestra lo reservado) y el impedimento
   `partidas_en_camara` (desde `produccion`, en el registrante de PRD-01); todo caso de uso que crea una partida bloquea antes el
   invernadero (D-64 punto 12).

## Cuando exista Alerta (MAE-02)

1. ~~**Alertas de personal faltante del invernadero.**~~ Hecho el 19/11/2026 en MAE-02a (las `test_d38_…` se reemplazaron). Texto original: Postcondición d de PROD-ALT-INV (una alerta «invernadero sin {rol} activo»
   por cada rol sin asignar); de PROD-MOD-INV, la b (la alerta del rol que se asigna pasa a «resuelta»), la d (alerta si deja
   un rol sin asignar; la del Técnico solo con sistema IoT) y la e (alertas al reactivar); y la e de PROD-BAJ-INV (las alertas
   activas pasan a «resuelta»). Se conectan en `alta_invernadero`, `modificar_invernadero`, `reactivar_invernadero` y
   `baja_invernadero`; sus pruebas `test_d38_…` hay que cambiarlas. Nació en MAE-01b.

## Cuando exista SistemaIoT (alertas)

1. **Alerta del Técnico.** Al registrar o dar de baja el `SistemaIoT` de un invernadero, el caso de uso llama a
   `maestros.servicios.alertas.sincronizar_alertas_de_personal` (la alerta «invernadero sin Técnico activo» solo cuenta con sistema
   IoT, regla 3 de 8.22). `Invernadero.tiene_sistema_iot()` es verdadero desde IOT-02. Nació en MAE-02a. Al registrar: hecho en IOT-02 (22/11/2026). Al dar de baja: hecho en IOT-06 (24/11/2026).

## Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión

1. **Origen de la alerta (restricción C5).** Cada app declara el enlace desde su propia app (`OneToOneField` a `Alerta`, o una tabla de
   enlace para Hardware, R052), en la misma transacción que la alerta; el `origen` de su `TipoAlerta` dice cuál. Contrato en
   `docs/api/alertas.md`, sección 4. Mostrar el origen en una pantalla va por un punto de extensión. Nació en MAE-02a.
   **IoT:** una sola tabla `AlertaIot` para R052 y R053 (D-72). ~~Hecho el 22/11/2026 en IOT-01 (la tabla `AlertaIot` y sus restricciones).~~ Falta que cada alerta del IoT cree su vínculo en la misma transacción: IOT-03 en adelante.

## Cuando exista el caso de uso de consulta de alertas (CU-46) o el panel de IoT (CU-41)

1. ~~**Consulta de alertas (CU-46).**~~ Hecho el 22/11/2026 en MAE-02c (`consultar_alertas`, `filtros_de_alertas` y `detalle_de_alerta` en `docs/api/alertas.md`, sección 5). Texto original: MAE-02b dejó afuera la pantalla (paso 4): pasa a MAE-02c (`docs/tareas/maestros/MAE-02c-alerta-consulta.md`; extracto en `docs/casos_de_uso/maestros/alertas.md`). Incluye la entrada «Alertas» del menú
   (desde `MaestrosConfig.ready()`), el alcance `Alerta.objects.para(usuario)`, solo las activas, filtros por invernadero y tipo, el
   detalle que llama a `abrir_alerta` (ya existe), que funcione sin JavaScript (HTMX solo reemplaza la tabla) y que viva en `maestros`.
   **Pendiente para pendientes_CU:** abrir la alerta la marca «leída» (regla 7 de 8.18) y choca con la postcondición de CU-46 («no se
   produjeron cambios en el sistema»). CU-41 reutiliza la consulta: `consultar_alertas` (`docs/api/alertas.md`, sección 5). **CU-41 (el panel de monitoreo) hecho el 23/11/2026 en IOT-04:** usa `consultar_alertas(…, tipos=)` y `enlaces_de_alertas`. Nació en
   MAE-02a.
2. **Contador de no leídas en la entrada «Alertas» del menú.** MAE-02c dejó la entrada sin contador: `core.menu.registrar_entrada` solo
   admite `(texto, url, ícono)`. Para sumarlo hay que ampliarla (por ejemplo, con `contador=funcion(usuario)`), calcularlo en
   `core/context_processors.py` y mostrarlo en `core/templates/core/base_con_sesion.html`; el valor lo da
   `Alerta.objects.para(usuario).activas().no_leidas().count()`. Hoy lo avisa el punto rojo de la campana. Nació en MAE-02c.

## Cuando una app necesite sumar algo al Inicio, a la ventana de baja o a la reactivación de una cuenta

1. **Puntos de extensión de `core` (D-43).** Se registran en `AppConfig.ready()` con `registrar_seccion_de_inicio`,
   `registrar_asignaciones_de_cuenta`, `registrar_efecto_de_baja_de_cuenta` y `registrar_efecto_de_reactivacion_de_cuenta`. Un efecto
   corre con la cuenta ya bloqueada y bloquea sus filas después del invernadero y en orden de id (`core/extensiones.py`). Nació en
   MAE-02b.

## Cuando el invernadero ya exista en Neon con datos (D9)

1. **Invernaderos anteriores a MAE-02a.** No tienen alertas de personal hasta su primera modificación con cambios o su
   reactivación; guardar sin cambios no las crea (D-28). Decidir antes de desplegar si hace falta una migración de datos (sería una
   tarea nueva, con D-39 y `docs/patrones/datos_de_migracion.md`). Nació en MAE-02a.

## Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido

1. **Traspaso por cambio de personal.** Postcondición b de PROD-MOD-INV (MD-60 y MD-62). Cada app registra
   `registrar_traspaso(contar, traspasar)` de `maestros/extensiones.py`: al Capataz, las órdenes a realizar del invernadero;
   al Técnico, los mantenimientos a realizar; al Vendedor, los contratos vigentes o abiertos (regla 8 de 8.21); al Agrónomo,
   las alertas activas (hecho en MAE-02a, directo en `modificar_invernadero`, no por registrante) y, si el saliente sigue activo, se cancelan sus pedidos sin orden de compra con destino a ese
   invernadero y se avisa a los proveedores invitados. `contar` alimenta el aviso de la regla 2 y la notificación de la
   postcondición c. Bloquean sus filas después del invernadero y en orden de id. Nació en MAE-01b.
   **Hecho el 22/11/2026 en PRD-01 (el Capataz):** `produccion` registra el suyo, filtra por `TIPOS_DE_PRODUCCION` y devuelve las instancias tocadas,
   que quedan entre los afectados de `modificacion_invernadero` (D-81: `traspasar` ahora devuelve lo que tocó). Siguen los de COM-02 y COM-03; el de IOT-07, abajo.
   **COM-02 (lote C2)** suma las cosechas al traspaso del Capataz (por `ordenes_del_capataz`, D-53) y registra el del Vendedor con la regla de
   D-60 (compra-ventas); **Hecho el 23/11/2026 en COM-03a:** los suministros vigentes, con la misma regla. Los pedidos son de `compras` (fuera de «Comercial 1», D-57).
   **Hecho el 24/11/2026 en CMP-02b (los pedidos):** `compras` registra su `traspasar` (cancela los pedidos «en cotización» del Agrónomo saliente con algún detalle a ese invernadero, aunque siga activo: MD-62 no lo condiciona) y su aviso (`registrar_aviso_de_traspaso`, D-98); su `contar` devuelve vacío.
   **Hecho el 24/11/2026 en IOT-07:** `iot` registra el del Técnico (`traspasar_mantenimientos` y `contar_traspaso`): pasan al entrante todas las órdenes de mantenimiento a realizar del invernadero (D-79, punto 9).

## Cuando exista un caso de uso que planifique, haga pedidos, asigne stock o reintente entregas

1. **Invernaderos inactivos (regla 4 de PROD-BAJ-INV).** «Un invernadero inactivo no aparece en las planificaciones, en los
   pedidos, en la asignación de stock ni en el reintento diario de las entregas»: cada app que lo programe excluye los
invernaderos inactivos. Hoy lo cumple PRD-01 (planificar y concretar rechazan un invernadero inactivo y la bandeja lo excluye; hecho el 22/11/2026). Nació en MAE-01b.
   **Asignación de stock: COM-02 (lote C2)**, en `stock_maduro` (invernaderos considerados = solo activos). Planificaciones y reintento de
   entregas: COM-03 y COM-05 (**planificado en el lote C5a:** COM-05a, en la planificación inmediata y en el paso 50).
   **Pedidos: hecho el 24/11/2026 en CMP-02b.** Un invernadero inactivo no se ofrece al armar un pedido (CMP-RLZ-PED lo rechaza con `invernadero_inactivo` vía `bloquear_invernadero_activo`) y la baja del invernadero se impide con un pedido en curso. Quedan las planificaciones, la asignación de stock y el reintento de entregas. **Hecho el 24/11/2026 en COM-05a1:** la planificación de entregas y el paso 50 no toman un invernadero inactivo.

## Cuando exista Cliente o CompraVenta

1. ~~**Dirección usada.**~~ Hecho el 23/11/2026 en COM-01 (D-58, con la nota de C6). Texto original: Regla 3 de 8.18: una dirección que usa una compra-venta o un detalle de suministro no se modifica
   ni se elimina; se registra una nueva y la anterior pasa a inactiva. `modificar_invernadero` (MAE-01b) crea la dirección nueva al cambiar de
   urbana a rural y borra la anterior con `Direccion.objects.filter(pk=...).delete()`: cuando existan esas clases hay que
   cambiarlo por «pasa a inactiva», o el borrado falla por PROTECT. Nació en MAE-01a.
   **Se cierra en COM-01 (D-58):** por la restricción C6 una dirección de invernadero nunca es de un cliente, así que ningún contrato la usa y
   `modificar_invernadero` puede seguir borrando la anterior. Lo que sí queda: COM-02 valida que la dirección de envío de una compra-venta sea
   una dirección **activa del cliente** (y COM-03, la de cada detalle de suministro). Lo que queda para COM-02 y COM-03 (la dirección de envío y la de cada detalle son direcciones activas del cliente) sigue en «Completan el ABM de cliente».

## Cuando se actualicen los datos de Georef

1. **Carpeta y migración nuevas.** Los CSV de `maestros/datos/georef_2026-11-18/` no se editan: una actualización va en una
   carpeta nueva y una migración nueva (D-39).

## Cuando una migración cargue datos que las pruebas usen

1. **Plan de cuentas de `contabilidad`, categorías de `inventario`, Georef de `maestros`.** Las clases de pruebas que los
   usan heredan del mixin que los carga una vez, los confirma y corre `ANALYZE`. Cómo hacerlo:
   `docs/patrones/datos_de_migracion.md`.

## Cuando exista contabilidad con asientos (D-45)

- **Ronda Contabilidad 1 (CON-02, D-84 a D-86):** el servicio `registrar_asiento_automatico` existe desde CON-02.
  **Planificado (Contabilidad 2, D-92):** punto 0 (inventario) → **CON-04b**; punto 1 (producción) → **CON-04a** (también la fila de
  PROD-PNR-FDS: PRD-04 se mergeó sin CON-02); «Comercial 1 (COM-04)» → **CON-04c**; «Comercial 1 (COM-07)» y «Comercial 1 (COM-08)» →
  **CON-04d**. Toda tarea de Producción o Comercial que empiece con CON-02 ya en `main` programa su asiento con la tabla de su tarea de
  reapertura (D-92 punto 9). Las precondiciones «existe un ejercicio y existen las cuentas» no se programan (D-92 punto 2).
  **Decidido el haber de la carga inicial (MD-90):** Capital Inicial (H3/H4, D-92 punto 7).

- **Comercial 1 (COM-04, D-64):** los asientos de la cosecha (uno por movimiento «salida por cosecha», con su `costo_unitario`), de la
  merma en cámara y del vencimiento se originan en `MovimientoStock` y en `Merma`, que ya guardan el costo: no hay que migrar nada.
- **Comercial 1 (COM-07, D-69):** el asiento de cada indemnización se origina en su `SolicitudRevision` (hija de `OrigenDocumento`), con lo
  descontado contra Deudores por Ventas y lo reintegrado contra Caja o Banco según `medio_reintegro`; el contraasiento, en su `Anulacion`; la
  multa, en el `Suministro` (R012, MD-123). Todo lo que hace falta ya está guardado: no hay que migrar nada.
- **Comercial 1 (COM-08, D-94):** el asiento del cobro de un suministro se origina en su `PagoCliente` (Debe Caja o Banco c/c por
  `monto_pagado` / Haber Deudores por Ventas por Σ `LineaPago.monto_cobrado` / Haber Indemnizaciones por Atraso en el Pago por Σ
  `indemnizacion_atraso`, si es mayor que cero); el contraasiento de un cobro anulado, en su `Anulacion`; el del cobro de 6a de COM-CNL-CVT, en
  su `PagoCliente` de compra-venta (MD-130). La precondición c de COM-REG-CBR (ejercicio y cuentas) se suma al reabrirlo. Todo lo que hace
  falta ya está guardado.

0. ~~**Inventario.** `MovimientoInsumo` **ya hereda** de `OrigenDocumento` (D-52: CON-01 crea el padre e INV-01 la hija): no hay nada que migrar. CMP-AJT-STK (INV-02) vuelve a verificar el
   ejercicio y las cuentas y crea el asiento de cada ajuste (`docs/casos_de_uso/inventario/ajuste_de_stock.md`: lo marcado «Fuera de la
   ronda (D-45)»; el asiento de cada ajuste referencia al movimiento como su `OrigenDocumento`). Decidir antes la cuenta del haber de la carga inicial (MD-90, tema abierto del CU).~~
   Hecho en CON-04b (24/11/2026): `confirmar_ajuste` crea el asiento de cada movimiento de ajuste; la carga inicial va contra Capital Inicial (D-92 punto 7). Las precondiciones c y d se cumplen solas (D-92 punto 2).

1. **Reabrir seis casos de uso de la ronda «Producción 1».** Hasta entonces no verifican el ejercicio vigente ni las
   cuentas, ni crean `AsientoContable`: PROD-CNC-SMB y PROD-CNC-TRN (precondiciones c y d y su asiento), PROD-REG-MRM,
   PROD-PNR-FDS, CMP-AJT-STK y PROD-REG-APL (el asiento y las precondiciones contables que cada uno tenga en «CU
   extendidos»; el extracto de cada caso de uso las marca «Fuera de la ronda (D-45)»). Hay que reabrir sus servicios (PRD-01,
   PRD-02, PRD-03, PRD-04 e INV-02; en PRD-02, `concretar_transicion` y `aplicar_merma`, que suman el ejercicio, las cuentas «Pérdidas por Mermas» y «Productos en Proceso» y el asiento de la merma) y sus pruebas, incluidas las de concurrencia, y respetar el orden de bloqueos del
   patrón. Anotar lo mismo en pendientes_CU (Drive).

   **PRD-03 ya existe:** el asiento de la merma va dentro de `mermas.registrar_merma` (después de `aplicar_merma`) y el de cada consumo, dentro de `aplicaciones.registrar_aplicacion` (después de cada `Consumo`); ninguno de los dos devuelve hoy lo que hace falta para el asiento más que `Merma.cant_merma`, el costo de `ResultadoMerma` y `Consumo.monto_consumo`.

## ~~Cuando se retome la cámara de frío (D-45)~~ (cerrado el 24/11/2026, COM-04b)

1. ~~**Cámara.**~~ Hecho el 24/11/2026 en COM-04b (`comercial/servicios/camara.py` y `merma_camara.py`: la pestaña «Cámara», PROD-ASG-CAM con el paso 25, PROD-VNC-CAM con el paso 20 y la extensión 10c de PROD-REG-MRM). Texto original: Pestaña `camaraTab` de la ficha del invernadero, `PROD-ASG-CAM` y la extensión 10c de `PROD-REG-MRM` (recorta las
   reservas de `comercial`). Va con la ronda de cosecha y comercial: necesita `StockCosechado` y `ReservaStock`.
   **Planificado (21/11/2026, D-57):** entra en la ronda «Comercial 1», tarea COM-04 (`docs/tareas/ronda_comercial_1.md`).
   **Lote C4:** COM-04 lo programa (`docs/casos_de_uso/produccion/camara.md` y la sección «Comercial 1» de `merma.md`).

## Cuando existan los pedidos de `compras` (D-45)

**Planificado (Compras 1, D-87):** el punto 1 lo programan CMP-02b (`pedido_en_curso`), CMP-03 (`orden_de_compra_aprobada` y el tránsito al
aprobar) y CMP-04 (el tránsito al recibir o cerrar con faltante); el punto 2, CMP-04 con `registrar_ingreso_por_recepcion` (`docs/api/stock.md`,
«Escritura de compras», D-90): el vínculo `OneToOne` es `compras.DetalleRecepcionMovimiento`, además del `origen` de D-52.

1. **Insumo en tránsito y compras.** En la ronda «Producción 1» el stock en tránsito es 0: la columna `cant_transito_insumo` existe y
   solo la escribirá `compras`. `compras` se enchufa a `inventario` por dos vías ya documentadas (`docs/api/extensiones_de_inventario.md`):
   el punto `registrar_impedimento_de_deshabilitacion` (orden de compra aprobada sin recibir, pedido en curso: los usan CMP-DSH-IIN, CMP-BAJ-INS y
   la baja del invernadero) y los servicios de stock (`docs/api/stock.md`) para la **recepción**.
   **Hecho el 24/11/2026 en CMP-02b:** el código `pedido_en_curso` (un pedido «en cotización» con ese insumo en ese invernadero, con enlace al pedido). **Hecho el 24/11/2026 en CMP-03:** `orden_de_compra_aprobada` (una orden no terminada con una línea a ese insumo en ese invernadero, con enlace a su ficha) y el tránsito al aprobar (`stock.sumar_transito`). Falta el tránsito al recibir o cerrar con faltante (CMP-04; `stock.restar_transito` ya existe).
   INV-02 ya dejó conectado el punto: CMP-DSH-IIN, CMP-BAJ-INS y la baja del invernadero llaman a `registrar_impedimento_de_deshabilitacion` (`compras` solo registra su función). Su `cant_transito_insumo` ya cuenta en «bajo el mínimo» y se muestra en las existencias.
2. **Recepción y faltante sin lote.** Por la regla 4 de 8.23 la recepción cancela primero el faltante sin lote y crea un lote nuevo por partida
   (y por fecha de vencimiento); hoy solo lo regulariza un recuento físico (`docs/modelo/inventario.md`, «Diferencias con el caso de uso»). Al
   escribir la recepción hay que verificar que resuelva la alerta «stock inconsistente» y la de «bajo el mínimo» (tema abierto de CMP-AJT-STK), y
   que agregue el vínculo `OneToOne` desde su tabla a `MovimientoInsumo` (A2).
   La recepción debe llamar a `alertas_de_stock.reevaluar_alertas_del_insumo(iin_id)` (INV-02 no crea ninguna función de entrada por recepción).

## Cuando exista `produccion` completa (lote 5)

1. ~~**Pestaña «Bitácora» de la ficha del invernadero**~~ Hecho el 23/11/2026 en PRD-03 (`registrantes.pestana_de_bitacora`; la ven el Agrónomo a cargo y el Gerente).
2. **Contabilidad** (ronda futura): los asientos de merma, aplicación de insumos (cuenta «Gastos de Producción», MD-90) y fuera de servicio salen de los registros de `produccion` (`Merma`, `AplicacionInsumos` e `ImputacionCosto`); hoy llevan su monto y no hay asiento (D-45).
3. **Cosecha** (ronda futura): suma a la bitácora los tipos `cosecha` e `incumplimiento de cláusula suministrante` (hoy no se ofrecen en el filtro de PROD-CNS-BIT) y la condición 1 de la alerta de plantas comprometidas (`aplicar_merma`).
   **Planificado:** la condición 1, COM-02 (lote C2); el tipo `cosecha` con su vínculo a la cosecha (R152), ~~COM-04 (lote C4, D-64 punto 4)~~ Hecho el 24/11/2026 en COM-04a (D-64 punto 4); los dos tipos de contrato también, en COM-04a (D-69 punto 3).; el
   tipo `incumplimiento_de_clausula`, COM-07 (lo crean las solicitudes de revisión aceptadas). **Desde el lote C7** (D-69, punto 3): el tipo
   lo crea **COM-04a**, junto con `anulacion_de_resolucion` y el filtro (`docs/api/produccion.md`, sección 11); COM-07a los usa.
4. ~~**Módulo IoT** (en paralelo): decide qué pasa con el hardware de un sector que sale de servicio.~~ **Resuelto el 20/11/2026:** no se toca; sus sensores no generan alertas ambientales mientras el sector esté fuera de servicio (`temas_abiertos.md`). PROD-PNR-FDS no cambia.
5. **Cámara de producto** (ronda futura): las partidas de cámara de PROD-REG-MRM (extensiones 4a y 10c, causas de cámara) y el movimiento «salida por merma».
   **Planificado (lote C4):** COM-04 (sección «Comercial 1» de `merma.md`; `MovimientoStock`, D-64 punto 1). Hecho el 24/11/2026 en COM-04a: `MovimientoStock`, «salida por merma» en `aplicar_merma`, las causas `dano_en_camara`, `vencimiento_en_camara` y `dano_en_entrega`. Hecho el 24/11/2026 en COM-04b: las extensiones 4a, 4b, 10c y 10d de PROD-REG-MRM sobre una partida (`merma_camara.py`; solo «Daño en cámara», `docs/temas_abiertos.md`).


## ~~Cuando exista el modelo completo de Variedad (INV-03)~~ (cerrado el 22/11/2026, INV-03)

1. **Restricciones de `Variedad`.** MAE-03 la creó con columnas mínimas. INV-03 agrega la restricción única `(cultivo, lower(nombre_variedad))`, los rangos y el resto, con una migración propia en `maestros` (`docs/modelo/maestros.md`, «Variedad»).

## ~~Cuando exista TransicionEtapa (PRD-02)~~ (cerrado el 22/11/2026, PRD-02)

1. ~~**Fechas de etapas posteriores a la primera.**~~ Hecho el 22/11/2026 en PRD-02 (`lotes.entradas_a_la_etapa`, `fecha_de_entrada_a_maduracion` y `fecha_maxima_de_cosecha` salen de la transición concretada; `lotes_activos_de` y `fecha_estimada_de_fin_de_etapa` ya no dan `None`). Texto original: `lotes.fecha_de_entrada_a_la_etapa` devuelve `None` fuera de la primera etapa, y
   `fecha_de_entrada_a_maduracion` y `fecha_maxima_de_cosecha` siempre `None` (reglas 2, 3 y 5 de 8.20 y 8.21): PRD-02 las completa con la
   transición concretada. Con ellas se completan `lotes_activos_de` y `fecha_estimada_de_fin_de_etapa`.
2. ~~**Dónde suma `TransicionEtapa`.**~~ Hecho el 22/11/2026 en PRD-02 (`_HIJAS_CON_CAPATAZ` con sus relaciones por clase, `uso_de_variedad`, `perfil_de_sector`, los avisos de cambio de tipo y la cancelación, que bloquea la variedad y el lote). Texto original: PRD-02 la agrega a `_HIJAS_CON_CAPATAZ` de `produccion/servicios/ordenes.py` (bandeja, `ordenes_del_capataz`,
   traspaso del Capataz, asignaciones de cuenta y cancelación), al conteo de órdenes de `registrantes.uso_de_variedad` y a los registrantes de
   sectores (ocupaciones y avisos de cambio de tipo). `cancelar_orden` ya acepta `transicion` (`TIPOS_QUE_CANCELA_PRODUCCION`).
3. ~~**Prueba pendiente.**~~ Hecho el 22/11/2026 en PRD-02 (`CancelarTransicionConcurrenciaTests` de `test_cancelar_concurrencia.py`). Texto original: «Cancelar contra planificar otra transición del mismo lote» (`test_cancelar_concurrencia.py`).

## Cuando exista PRD-03 o PRD-04 (merma, bitácora y sector fuera de servicio) — nace con PRD-02 (22/11/2026)

1. 1. ~~**El núcleo de la merma ya existe, no se reescribe.**~~ Hecho el 23/11/2026 en PRD-03 (`mermas.registrar_merma` llama a `aplicar_merma` con `por_sector` y `sector_ids`). PRD-03 (Registrar Merma) llama a `produccion/servicios/mermas.aplicar_merma(lote, cantidad, causa, descripcion, fecha, responsable, *, por_sector=…, sector_ids=…, ordenes_excluidas=…)` dentro de su transacción y con el lote ya bloqueado; con `por_sector` baja los agujeros ocupados de cada ocupación y deja las ocupaciones en cero conservando el lote. PRD-04 usa `sector_ids` y `ordenes_excluidas`. Códigos de error: `cantidad_invalida`, `causa_obligatoria`, `causa_invalida`, `descripcion_larga` y `fecha_invalida`.
2. ~~**La condición 2 de plantas comprometidas solo está probada llamando a la función.**~~ Hecho el 23/11/2026 en PRD-03 (`test_post_l_una_transicion_a_realizar_ajena_...` y el aviso del resumen de la merma). Desde Concretar Transición no puede dispararse (se excluye la orden que se concreta): PRD-03 agrega la prueba de punta a punta desde la pantalla de merma, con una transición «a realizar» ajena (`test_mermas_nucleo.py` ya tiene la de función).
3. **Nombres que PRD-03 y PRD-04 tienen que respetar (D-83):** `TransicionEtapa.bitacora_de_transicion` (no `bitacora`) y los códigos `causa_invalida`, `descripcion_larga` y `lote_sin_plantas`. La bitácora de una transición es una `Bitacora` de tipo `transicion` con la etapa destino; la de una merma, una `Merma` de tipo `merma` en la etapa de origen: PRD-03 las lista en PROD-CNS-BIT.
4. ~~**`registro_merma`**~~ Hecho el 23/11/2026 en PRD-03 (`registrar_merma` la usa como acción propia). (acción de auditoría ya creada por PRD-02) la usa PRD-03 como acción propia; en una transición la merma va dentro de `concrecion_transicion`.
5. ~~**PRD-04 y `cancelar_orden_incluida`:**~~ Hecho el 23/11/2026 en PRD-04: `poner_fuera_de_servicio` toma cuentas, invernadero, variedades, sectores, insumos, lotes y órdenes en ese orden.~~ ahora, con una transición, toma el lote (nivel 4 de `bloqueos.md`) antes de la orden: quien la llama ya tiene que haber bloqueado cuentas, invernadero, variedad, sectores y lotes en ese orden. `notificar_a` trae al Capataz de la hija `TransicionEtapa`.~~

## Cuando exista PRD-05 (registrar lote existente) — nace con PRD-05 (25/11/2026)

1. **`Siembra.capataz` puede ser nulo** (D-92 punto 12; solo en una siembra de carga inicial, concretada). Toda tarea que lea `siembra.capataz` o `capataz_id` tiene que contemplar `None`: hoy lo hacen `ordenes._fila`, `ordenes.detalle_de_orden` y `detalle.html` («Sin Capataz (carga inicial)»); `ordenes_del_capataz`, el traspaso y la cancelación solo ven órdenes «a realizar», que siempre tienen Capataz. Las estadísticas de producción (EST-01) y cualquier pantalla nueva con el Capataz de una siembra deben comprobarlo.
2. **CON-04a no asienta la carga inicial.** `siembras._registrar_concrecion` es de las siembras normales; el asiento de un lote existente lo crea `lotes_existentes.registrar_lote_existente` (Debe Productos en Proceso / Haber Capital Inicial, fecha actual). CON-04a no lo reabre ni lo duplica.
3. ~~**`carga_inicial` en el filtro de la bitácora.**~~ Hecho el 25/11/2026 en PRD-05 (`bitacora.TIPOS_DE_FILTRO`).
4. **Lo que lee «la entrada a la etapa»** (`lotes.entradas_a_la_etapa` y `fecha_de_entrada_a_maduracion`) ahora también mira la entrada de bitácora `carga_inicial`: una tarea que sume otra forma de entrar a una etapa (una reubicación que cambie la etapa, por ejemplo) tiene que respetar el orden «transición concretada → carga inicial → fecha de siembra».

## Cuando exista PROD-PNR-FDS (PRD-04)

1. ~~**Estado «fuera de servicio».**~~ Hecho el 23/11/2026 en PRD-04. ~~ Ningún caso de uso de MAE-03 lo produce; `maestros` ya lo muestra y ya ofrece «Volver a activar» y «Dar de baja». PRD-04 agrega `maestros/servicios/sectores.py::pasar_a_fuera_de_servicio` (lote 5 de `docs/api/extensiones_de_maestros.md`) y registra `registrar_efecto_de_vuelta_a_servicio` y `registrar_efecto_de_baja_de_sector`. La clave `fuera_de_servicio` ya está en `VALORES_VISIBLES["estado"]`.~~
2. ~~**Tipos de bitácora y filtro de la consulta.**~~ Hecho el 23/11/2026 en PRD-04 para `fuera_de_servicio` y `reubicacion` (`bitacora.TIPOS_DE_FILTRO` los incluye). Quedan `cosecha`, `incumplimiento_de_clausula`, `anulacion_de_resolucion` (COM-04a) y `comando`: IOT-05 (23/11/2026) lo sumó a `Bitacora.TipoEvento` y a su restricción (`produccion` 0006), pero **no** a `bitacora.TIPOS_DE_FILTRO` (estaba fuera de su «Límites»): falta sumarlo para que el filtro «Tipo» de la consulta lo ofrezca. [no tachar este renglón entero: sigue vigente para esas tareas]* PRD-04 suma `fuera_de_servicio` y `reubicacion` a `Bitacora.TipoEvento`, reemplaza la restricción `bitacora_tipo_evento_valido` (hoy: siembra, transicion, merma, aplicacion, otro_evento y consumo) y los suma a `bitacora.TIPOS_DE_FILTRO` (el filtro de PROD-CNS-BIT). Lo mismo harán COM-04a (`cosecha`, `incumplimiento_de_clausula`, `anulacion_de_resolucion`) e IOT-05 (`comando`). Nace en PRD-03. Hecho el 24/11/2026 en COM-04a: `TIPOS_DE_FILTRO` ofrece `cosecha`, `incumplimiento_de_clausula` y `anulacion_de_resolucion`.
3.3. ~~**Prueba de concurrencia que PRD-03 no pudo escribir:**~~ Hecho el 23/11/2026 en PRD-04 (`produccion/tests/test_fds_concurrencia.py`, en los dos órdenes).~~ «merma contra poner el sector fuera de servicio» (`produccion/tests/test_merma_concurrencia.py`; `docs/patrones/bloqueos.md`, «Lote 5»). La merma toma cuentas → invernadero → variedad → sectores con pérdidas → lote → ocupaciones. Nace en PRD-03.~~
4. **Inicio del Agrónomo con filtro por invernadero.** `registrar_seccion_de_inicio` solo recibe al usuario; la sección de PRD-04 muestra todos sus invernaderos activos juntos. Cuando `core` permita a una sección recibir un parámetro (por ejemplo `?invernadero=`), sumar los chips «Todos / <invernadero>» del prototipo. También suma COM-04a el grupo «Cosechas» después de esta sección (`cosecha.md`).



## Cuando se arme el cron único

1. **Un solo cron job de Render para todo el proceso diario (D-56).** Se crea **al final de la implementación**, cuando estén
   registrados todos los pasos de `core/procesos.py`. Ejecuta `python manage.py proceso_diario`, con:
   - el mismo repositorio, la misma rama y las mismas variables de entorno que el web service, incluida la base de Neon;
   - el mismo comando de compilación;
   - una agenda antes del inicio de las rutas. La hora se confirma con el Jardín Botánico; Render usa UTC.
   Antes, revisar el costo (`docs/temas_abiertos.md`). Después, anotar su nombre en `docs/estado.md`. Nace en DIA-01.
2. **La revisión periódica del IoT (D-71).** `python manage.py revision_iot` cada 5 minutos, **encendido solo para las presentaciones** (un
   rato antes y hasta un rato después; el resto del tiempo, suspendido, por Neon Free). Decidir entonces si es un cron propio o uno solo
   cada 5 minutos que también corra el proceso diario (idempotente por día). Nace en el lote IoT 0. **`revision_iot` ya existe (IOT-04, hecha el 23/11/2026); falta solo el cron.**

## Completan el ABM de cliente (COM-01, lote C1)

COM-01 deja escritas, con un resultado neutro, las funciones de `comercial/servicios/clientes.py` que dependen de clases que todavía no
existen. Cada tarea que crea la clase les pone la consulta real y la prueba (`docs/casos_de_uso/comercial/clientes.md`, «Para más adelante»).

COM-01 está hecha (23/11/2026): las funciones neutras ya existen. En clientes, `direcciones_en_uso` ya trae escrita (y probada con `mock.patch`) la rama «crear otra y dejar inactiva la anterior»: la tarea que cuente usos solo reescribe esa función.

1. **COM-02 (compra-venta; escrito en el lote C2, paso 6 de la tarea):** `direcciones_en_uso` cuenta las compra-ventas con envío (en cualquier estado); `pendientes_del_cliente`, las compra-ventas
   abiertas o pendientes de decisión; la ficha y la lista muestran sus contratos (el Vendedor, solo los suyos); el formulario usa
   `volver` para regresar a COM-REG-CVT (regla 7 de COM-ALT-CLT, regla 5 de COM-MOD-CLT).
2. ~~**COM-03 (suministro; escrito en el lote C3, paso 8 de la tarea):**~~ **Hecho el 23/11/2026 en COM-03a.** Texto original: `direcciones_en_uso` cuenta los detalles de suministro (en cualquier estado); `impide_quitar_el_correo` mira los suministros
   vigentes (regla 3 de COM-MOD-CLT); `pendientes_del_cliente` y la ficha suman los suministros; `volver` regresa a COM-PCT-SUM.
3. **COM-06 (entregas concretadas, quejas y discrepancias):** la ficha y la baja muestran las entregas sin cobrar, con el monto a cobrar y
   el vencimiento, y las quejas o discrepancias pendientes. **Planificado (lote C6):** las entregas sin cobrar y las discrepancias, COM-06a;
   las quejas, COM-06b (`rutas.md` y `confirmacion.md`, «Lo que completa a otras tareas»).
4. **COM-08 (cobranza):** el estado de pago de cada entrega (pagada o en mora, MD-139) en la ficha. **Planificado (lote C8):** COM-08a
   (`cobranza.md`, «Lo que completa a otras tareas», fila COM-01).

## Completan el ABM de vehículo (COM-01, lote C1)

1. **COM-05a (entregas; planificado en el lote C5a):** `entregas_a_realizar_del_transportista` y `carga_maxima_asignada` de `comercial/servicios/vehiculos.py` reciben su
   consulta (reglas 2 y 3 de COM-MOD-VEH, precondición c y regla 1 de COM-BAJ-VEH); la lista suma «Entregas a realizar» y la ficha, la carga
   de los próximos días frente a la capacidad (regla 2 de COM-CNS-VEH).

   COM-01 está hecha (23/11/2026): `entregas_a_realizar_del_transportista` (lista vacía) y `carga_maxima_asignada` (`(0, None)`) ya existen y sus llamadores están probados con `mock.patch`: COM-05a solo les pone la consulta. **Hecho el 24/11/2026 en COM-05a1** (las pruebas con `mock.patch` siguen; las de datos reales están en `test_extensiones_entregas.py`). La columna «Entregas a realizar» y la tarjeta de carga de las pantallas de vehículos son de COM-05a2. **Hecho el 24/11/2026 en COM-05a2** (la columna en la lista y «Carga de los próximos días» en la ficha del vehículo).

## Cuando exista el rol Contador (USR-11) — nace con el lote 1 de Contabilidad

USR-11 está hecha (24/11/2026): el rol, `core.Contador` y `contabilidad/servicios/responsables.py` existen. El punto 1 sigue vigente para CON-04d; el punto 2 nace con el modelo.

1. El aviso de «registrar asiento manual» de COM-ATN-ENR (postcondición b) pasa del Vendedor a `responsable_contable()` (H12). Lo programa
   **CON-04d**, o COM-06b si llega después de CON-02. Toda pantalla que diga «Gerente y Vendedor registran asientos» se corrige.
2. ~~`EjercicioContable.contador` (R010, MD-116) es una FK nula a `core.Contador` (`PROTECT`, `related_name="ejercicios_cerrados"`), declarada en `contabilidad` (regla A2 de D-37). La crea CON-02. El modelo `Contador` ya existe en `core` (USR-11).~~ **Cumplido en CON-02 (24/11/2026).**

## Cuando se programe CON-03a — nace con el lote 1 de Contabilidad

1. ~~La entrada del menú «Contabilidad» y la alerta del «ejercicio en cierre» en el Panel del Contador y del Gerente (sin Contador, al Gerente).~~ **Cumplido en CON-03a (24/11/2026):** la entrada se registra desde `contabilidad/apps.py` (`registrar_entrada`) y la alerta es una sección del Inicio (`registrar_seccion_de_inicio`). **La alerta la ve el responsable contable: el Contador activo y, solo si no hay Contador activo, el Gerente** (el Gerente con un Contador activo no la ve).

## Cuando se programe CON-03b — nace con CON-03a

1. Las acciones de la ficha («Contraasentar», solo si el asiento puede anularse y su ejercicio no está cerrado) y de la lista («Registrar asiento») se agregan a `contabilidad/templates/contabilidad/asiento.html` y `libro.html` con `responsables.puede_registrar_asientos`; hoy están ocultas para todos (D-30). La validación de la fecha de un asiento manual o de un contraasiento usa `ejercicios.ejercicio_para(..., automatico=False)` (D-102 punto 3).

## Cuando una app tenga un origen de asiento con pantalla propia — nace con el lote 1 de Contabilidad

1. Registrar su `registrar_enlace_de_origen(tipo, funcion)` en `ready()` (punto de extensión de `contabilidad/extensiones.py`, creado por CON-03a el 24/11/2026; solo falta registrar los enlaces),
   para que el libro de gestión enlace el asiento con su documento. Compras: CMP-04 (recepción), CMP-05 (pago), CMP-06 (corrección). **Hecho el 25/11/2026 el del pago, en CMP-05** (`pagos.enlace_de_origen`) **y el de la corrección, en CMP-06** (`correcciones.enlace_de_origen`, registrado en `ComprasConfig.ready()`).

## Cuando se programe COM-04c o CMP-02a (lo que llegue primero) — nace con el lote 2 de Compras

1. ~~Crear `rol_externo` en `core` con `ROL_CLIENTE_ENLACE` y `ROL_PROVEEDOR_ENLACE` (D-65 punto 8; D-88 punto 5). La segunda tarea solo suma su constante.~~ Hecho el 23/11/2026 en CMP-02a: las dos constantes, `RegistroAuditoria.objects.registrar(..., rol_externo=)` y su texto visible («Cliente (mediante enlace)» ya está en `VALORES_VISIBLES["rol"]`). **COM-04c solo lo usa** con `ROL_CLIENTE_ENLACE`, y tiene que responder con `Referrer-Policy: same-origin` y no `no-referrer` (D-65 y D-88, corregidas: con `no-referrer` el navegador manda `Origin: null` y el CSRF rechaza los POST del portal; `compras/views_proveedor.py` es el modelo, y la «Verificación a mano» de la tarea lleva el paso de «navegador real», D-96). Para las etiquetas de la auditoría, no repetir claves de `ETIQUETAS` que ya existen (`detalles`, `lineas`, `monto_estimado`): la última pisa a la primera.

## Cuando se programe COM-01 o CMP-01 (lo que llegue primero) — nace con el lote 2 de Compras

1. ~~`validar_cuit` y `formatear_cuit` en `maestros/validadores.py` (D-58).~~ Hecho el 23/11/2026 en COM-01 (`perfil.py` delega en ellas); CMP-01 las usa.

## Cuando se programen CMP-02a, CMP-02b, CMP-03 y CMP-05 (completan lo que CMP-01 dejó vacío)

1. **Hecho el 23/11/2026 en CMP-02a** (`tiene_pedidos_u_ordenes` y la tarjeta de pedidos de la ficha, `proveedores.pedidos_del_proveedor`); las órdenes, pagos y reclamos de la ficha se suman de CMP-03 a CMP-06. Texto original: **CMP-02a:** completar `tiene_pedidos_u_ordenes(proveedor)` en `compras/servicios/proveedores.py` (hoy da `False`) con `proveedor.invitaciones.exists() or proveedor.cotizaciones.exists()`; desde entonces el CUIT del proveedor con pedidos no se modifica (regla 2 de CMP-MOD-PRV; la pantalla y las pruebas ya lo esperan). Sumar la tarjeta de pedidos de la ficha (regla 4 de CMP-CNS-PRV).
2. **CMP-02b:** al dar de baja, anular los enlaces vigentes del proveedor con `enlaces.anular_enlaces_de_proveedor` (regla 3 de CMP-BAJ-PRV), dentro de `baja_proveedor`.
3. **Hecho el 24/11/2026 en CMP-03** (`impedimentos_de_baja` con `orden_no_terminada` y la tarjeta «Órdenes de compra» de la ficha, `proveedores.ordenes_del_proveedor`). Texto original: **CMP-03:** sumar a `impedimentos_de_baja` el impedimento `orden_no_terminada` (órdenes pendientes de aprobación, aprobadas o parcialmente recibidas; precondición c de CMP-BAJ-PRV) y la tarjeta de órdenes de la ficha.
4. **Hecho el 25/11/2026 en CMP-05** (el impedimento `pago_pendiente`, con enlace a la orden, y la columna «Pago» de la tarjeta de órdenes de la ficha del proveedor; los reclamos de la ficha quedan para CMP-06). Texto original: **CMP-05:** sumar a `impedimentos_de_baja` el impedimento `pago_pendiente` (precondición d de CMP-BAJ-PRV) y los pagos de la ficha (CMP-06, los reclamos).


## Cuando se programen COM-03b y COM-04 — nace con COM-03a (23/11/2026)
1. **Calendario de la ficha con detalles finalizados.** Un período de un detalle finalizado que cae dentro de la ventana se muestra «Reservado» (los finalizados no tienen cantidad sin cubrir hasta D-64, punto 8). ~~COM-03b, los períodos posteriores a la rescisión~~ **Hecho en COM-03b (24/11/2026):** el calendario corta en `fecha_fin_detalle` y un período con la alerta «sin cobertura completa» activa dice «Sin cobertura completa · faltan N». **Queda para COM-04a:** la cantidad sin cubrir de un período de un detalle finalizado y que la pre-reserva (`comercial/servicios/pre_reserva.py`, `_periodos_a_pre_reservar` y `_pre_reservar_periodo`) retome esos períodos; revisar también `comercial/servicios/suministros.py`, `_filas_de_calendario`.

## ~~Cuando se programe CMP-03 (completa lo que CMP-02a dejó a medias)~~ (cerrado el 24/11/2026, CMP-03)

1. **Hecho en CMP-03** (`ya_pedido` cuenta también los pedidos «cerrados» con la orden «pendiente de aprobación» y trae su `orden_id`; las pantallas dicen «su orden de compra está pendiente de aprobación»). Texto original: **Regla 4c de CMP-RLZ-PED:** `pedidos.ya_pedido` cuenta hoy solo los pedidos «en cotización»; sumar los pedidos «cerrados» cuya orden de compra está «pendiente de aprobación» (regla 14 de 8.15), con el texto de la advertencia («su orden de compra está pendiente de aprobación»).
2. **Hecho en CMP-03** («Pedidos por resolver» con «Resolver», «Órdenes rechazadas» de los últimos 7 días y, para el Gerente, «Órdenes por aprobar»; «Por recibir» sigue siendo de CMP-04). Texto original: **Inicio del Agrónomo:** `compras/servicios/inicio.py` trae «Insumos bajo el mínimo» y «Esperando cotizaciones»; CMP-03 suma «Pedidos por resolver» (con su lista y el botón «Resolver») y «Órdenes rechazadas»; CMP-04, «Por recibir».
3. **Hecho en CMP-03** («Comparar cotizaciones y generar orden» y el aviso con el enlace a la orden que generó el pedido, solo si quien mira puede abrirla). Texto original: **Ficha del pedido** (`compras/templates/compras/pedidos/ficha.html`): hoy sin acciones. CMP-02b suma «Cancelar pedido» y «Reenviar invitación»; CMP-03, «Comparar cotizaciones y generar orden» y la orden que generó un pedido «cerrado» (regla 4 de CMP-CNS-PED).
4. **Hecho en CMP-03** (el paso 60 pone «vencido» a los enlaces vigentes de un pedido con cotizaciones). Texto original: **El paso diario 60** pone «vencido» a los enlaces vigentes: la ficha ya muestra «vencido» un enlace vigente con la fecha límite pasada, así que el paso no cambia lo que se ve (`pedidos._estado_del_enlace`).

## Nacidos en CMP-02b

1. **Hecho el 24/11/2026 en CMP-03** (el impedimento `orden_de_compra_aprobada` con su enlace y la parte «orden pendiente» de 4c; los pasos 60 y 62 usan `cancelar_pedido_automaticamente`, que ahora acepta `hoy` y `aviso`). Texto original: **Cuando CMP-03 genere la orden.** `cancelar_pedido_automaticamente(pedido, causa)` ya existe para los pasos 60 y 62 (causas `nadie_cotizo` y `sin_cotizaciones_elegibles`); devuelve `None` si el pedido ya no estaba en cotización, así que los pasos son idempotentes. Hay que completar el impedimento `orden_de_compra_aprobada` (puede usar `Impedimento.url`) y la parte «orden pendiente de aprobación» de la extensión 4c de CMP-RLZ-PED.
2. **Cuando se toque la ventana de baja de cuentas de `core`.** Mostrar `Asignacion.cantidad` (hoy solo `texto` y `que_pasa`); CMP-02b y PRD-01 meten el número en el texto.


## Cuando se programen COM-04b y COM-04c — nace con COM-04a (24/11/2026)
1. ~~**`on_commit` de PROD-ASG-CAM (COM-04b).**~~ Hecho el 24/11/2026 en COM-04b (`camara.programar_asignacion_de_camara` en `concretar_cosecha` y en `_cancelar_en_transaccion`). Texto original: `concretar_cosecha` y `cancelar_cosecha` (y `cancelar_cosecha_incluida`) no disparan la asignación automática de cámara de las partidas que crean o liberan (postcondiciones k y h): COM-04b registra el `transaction.on_commit` en `comercial/servicios/cosechas.py`. Hasta entonces las recupera el paso diario 25.
2. ~~**«Pérdida en cámara» y pestaña «Cámara» (COM-04b).**~~ Hecho el 24/11/2026 en COM-04b (`entradas_de_comercial` devuelve la URL de `comercial:merma_camara`). Texto original: `entradas_de_comercial` devuelve`merma_en_camara = None`: COM-04b lo completa junto con la pantalla.
3. ~~**Enlace y correo del camino de faltante (COM-04c).**~~ Hecho el 24/11/2026 en COM-04c (`faltantes._enlace_del_camino`; la prueba de concurrencia «cancelar contra la decisión del cliente» está en `test_cancelar_cosecha_concurrencia.py`). Texto original: **Enlace y correo del camino de faltante (COM-04c).** `faltantes.seguir_camino_de_faltante` no crea el enlace del cliente ni manda el correo (ni el aviso «registrá vos la decisión» sin correo): COM-04c los suma en la misma función; también la prueba de concurrencia «cancelar contra la decisión del cliente».
4. **Planificar la entrega (COM-05a1)** cuando una cosecha deja lista una venta o un período (postcondición n de PROD-CNC-CSC) y los **asientos** (D-57, CON-04c) originados en cada `salida_por_cosecha`. **Planificar la entrega: hecho el 24/11/2026 en COM-05a1;** los asientos siguen abiertos (CON-04c).

## Lo que deja COM-04b (nace el 24/11/2026)
1. ~~**COM-04c.**~~ Hecho el 24/11/2026 en COM-04c (`camara._asignar_partida` anula el enlace con `enlaces.anular_enlaces_de`; la prueba de la merma contra la decisión está en `test_com_dcd_flt.py`). Texto original: **COM-04c.** `camara._asignar_partida` (paso 7 de PROD-ASG-CAM) no anula el enlace de decisión del cliente de la venta que vuelve a «abierta»; `camara._recubrir` usa `faltantes.seguir_camino_de_faltante`, así que el enlace nuevo y el correo del camino de faltante (3a.2a de PROD-VNC-CAM, 10c de PROD-REG-MRM) se suman en esa misma función. También la prueba de concurrencia «merma en cámara contra la decisión del cliente» (`test_camara_concurrencia.py`).
2. ~~**COM-05a1.**~~ Hecho el 24/11/2026 en COM-05a1. Texto original: La condición «sin detalle de entrega en una entrega no cancelada» de `camara._candidatos`; el paso 9 y la postcondición e de PROD-ASG-CAM (planificar la entrega); y, en `camara._vencer_en_transaccion` y `merma_camara._registrar`, quitar las líneas recortadas de su entrega «a realizar» y cancelar la que queda vacía (postcondición d y extensión 3a de PROD-VNC-CAM; 10c).
3. **COM-06a.** La extensión 3b de PROD-VNC-CAM (partida con líneas en una entrega en curso); llamar a `camara.resolver_aviso_de_partida` cuando una entrega agota una partida.
4. **CON-04c.** Los asientos de `vencimiento_partida` y de `registro_merma` sobre una partida (se originan en la `Merma` y su `MovimientoStock`, que ya guardan el costo).
5. **Decisión pendiente (ficha del invernadero).** Si el Capataz y el Vendedor tienen que ver la pestaña «Cámara», `maestros.views.invernadero` (hoy `rol_requerido(GERENTE, AGRONOMO)`) tiene que abrirse a esos roles, con sus pruebas.

## Antes de las presentaciones — nace con USR-09a (24/11/2026)
1. **Subir el HSTS de un día a un año.** `HSTS_SEGUNDOS` de `config/seguridad.py` vale 86400 (D-99). Si Render lleva días en https sin problemas, pasarlo a 31536000. Sin subdominios ni preload, salvo decisión nueva.

## Nacidos en CMP-03 (24/11/2026)

1. **Hecho en CMP-03:** el Contador (USR-11) consulta las órdenes en solo lectura (`en_alcance_de`, `_exigir_consulta`, menú «Compras» → «Órdenes», una sola pestaña, sin enlaces a pedidos ni proveedores). **Hecho en CMP-05 (25/11/2026):** su entrada «Pagos a proveedores» (junto a «Contabilidad») y las marcas de pago pendiente.
2. **Hecho en CMP-04 lo de recepciones, en CMP-05 lo de pagos (sección «Pagos») y en CMP-06 lo de reclamos (sección «Reclamos» de la ficha de la orden y tarjeta de la ficha del proveedor, y lo corregido por línea).** Texto original: **Secciones de la ficha de la orden:** recepciones (CMP-04), pagos (CMP-05) y reclamos (CMP-06). Lo «recibido» hoy es 0 y lo «pendiente» es toda la cantidad (`LineaDeOrden`).
3. **Hecho en CMP-04 «Por recibir» y «Con reclamo sin emitir» (y la marca de reclamo) y en CMP-05 «Con pago pendiente» (y su marca).** Texto original: **Atajos de la lista de órdenes y marcas de la fila:** «Por recibir» y «Con reclamo sin emitir» (CMP-04), «Con pago pendiente» (CMP-05). Los atajos que hoy no existen se ignoran como un filtro mal formado.
4. **Hecho en CMP-04 «Por recibir» del Agrónomo y en CMP-05 «Pagos a proveedores pendientes» (Contador y, sin Contador activo, Gerente); **Hecho el 25/11/2026 en CMP-06 «Reclamos sin emitir» (tarjeta y lista del Inicio del Gerente).** Texto original: **Inicio:** «Por recibir» del Agrónomo (CMP-04), y «Reclamos sin emitir» y «Pagos a proveedores pendientes» (Gerente y Contador, CMP-05 y CMP-06).
5. **Hecho en CMP-04.** Texto original: **Estados posteriores a la aprobación** de la orden («parcialmente recibida», «recibida», «recibida con faltante») y del detalle («completo», «cerrado con faltante») los aplica CMP-04; `OrdenCompra.NO_TERMINADAS` ya los incluye para los impedimentos.
6. **Hecho en CMP-04** (la crea `registrar_recepcion`, junto con `ReclamoProveedor`). Texto original: **`AlertaCompras`:** la crea CMP-04 junto con `ReclamoProveedor` (su FK); el archivo de la tarea CMP-04 debe listarla.

## Lo que deja COM-04c (nace el 24/11/2026)
1. **Render: cargar `URL_DEL_SITIO`** (sin barra final) antes de usar el enlace del cliente; sin ella el correo no sale y el enlace queda «No se pudo enviar». Pasada manual en navegador real al cerrar la tanda de «Comercial 1» (pasos 3 y 14 de la «Verificación a mano» de COM-04c).
2. **COM-05a1:** planificar la entrega después de decidir (paso 7 y postcondición m de COM-DCD-FLT: si la venta queda «abierta» con todas sus reservas «lista para entrega»); el punto de enganche es el final de `faltantes._registrar`, con `on_commit`, junto a la asignación de cámara. **Hecho el 24/11/2026 en COM-05a1.**
3. ~~**COM-05b.**~~ **Hecho el 25/11/2026 en COM-05b** (COM-CNL-CVT anula el enlace de la venta cancelada). Texto original: COM-CNL-CVT llama a `enlaces.anular_enlaces_de(venta)` (ya existe; es el tercer llamador). **COM-06b:** suma el tipo `confirmacion_entrega` y su FK a `Entrega` al mismo `EnlaceCliente`, con `crear_enlace(…, entrega=)` sin reemplazo y vigencia calculada (`enlace_del_cliente.md`, sección 9); el paso 27 no lo toma.
4. **Documentar `URL_DEL_SITIO`** en `docs/patrones/enlace_del_cliente.md` (sección 3) y los bloqueos de COM-DCD-FLT en `docs/patrones/bloqueos.md` (ver `docs/temas_abiertos.md`, «COM-04c»).

## Cuando se programen CON-03b, CON-04a a CON-04d, CMP-04 y Estadísticas — nacen con CON-02 (24/11/2026)

El servicio `registrar_asiento_automatico`, los ejercicios y el libro existen desde CON-02 (`docs/api/asientos.md`, D-102).

1. **Hecho el 24/11/2026 en CMP-04** (tipo `recepcion` en `contabilidad` 0006 y asiento con `registrar_asiento_automatico`). Texto original: **Cuando exista la recepción de compras (asiento de compras):** CMP-04 suma el tipo `recepcion` a `OrigenDocumento.Tipo` (una migración de `contabilidad` con solo ese cambio) y llama a `registrar_asiento_automatico` con Debe Insumos en Stock / Haber Proveedores (regla 14 de 8.20, valorizada con el precio total por línea, MD-125). Sin ingreso al stock, no hay asiento.
2. **Cuando se reabra COM-CNC-ENT (CON-04c):** los asientos de la entrega, de sus mermas y de sus consumos (postcondiciones e, g y h) usan el mismo servicio, cada uno con su documento de origen; ya está listado arriba, en «Cuando exista contabilidad con asientos».
3. **Cuando se reabra cada caso de uso con asiento (CON-04a a CON-04d):** completar el texto de `DESCRIPCION_DE_CUENTA` (`contabilidad/cuentas.py`) con lo que ese asiento mueve (regla 3 de CON-CNS-PCT). No necesita migración.
4. **Cuando se programe CON-03b (asiento manual y contraasiento):** validar la fecha con `ejercicios.ejercicio_para(fecha, automatico=False)`, que lanza `fecha_en_ejercicio_cerrado`, `fecha_anterior_al_primer_ejercicio` y `fecha_futura` (D-102). El automático nunca las lanza.
5. **Cuando se programe Estadísticas (EST-02):** usar `libro.resultado_del_periodo(desde, hasta)` y `libro.total_por_cuenta_en_periodo(...)`; con `tipo=None` el total es el saldo según la naturaleza de la cuenta y puede ser negativo (D-102).
6. **Cuando se arme el cron único:** el paso 5 `abrir_ejercicio` ya está registrado y va primero (D-56); no hace falta programarlo aparte.

## Lo que deja COM-05a1 (nace el 24/11/2026)

1. ~~**COM-05a2.**~~ **Hecho el 24/11/2026 en COM-05a2** (el aviso, la columna y la carga de los vehículos, las secciones de las fichas, el panel y la restricción de `ReservaInsumo`). Texto original: el aviso de envasado al Agrónomo (postcondición h de COM-PNF-ENT) en `_planificar_en_invernadero`, junto al aviso al transportista; la columna «Entregas a realizar» y la tarjeta de carga de los próximos días en las pantallas de vehículos (`carga_maxima_asignada` y `entregas_a_realizar_del_transportista` ya existen); «Ver sus entregas» en la ventana de baja de un vehículo; las secciones de entregas de las fichas de contrato y el panel. La restricción de `ReservaInsumo` («a lo sumo una activa», D-66 punto 8) y las funciones de envasado: `entrega_para_agrupar` ya lee las reservas de insumo «activas».
2. ~~**COM-05b.**~~ **Hecho el 25/11/2026 en COM-05b.** Texto original: COM-ASG-TRP reutiliza `candidatos_para(..., excluir=)`, `seleccionar`, `motivo_de_alerta`, `peso_de_entregas` y la acción `asignacion_transportista` (ya declarada); cambia el enlace de la alerta (`entregas.enlaces_de_alertas`) a la pantalla de asignación. COM-CNL-CVT usa `cancelar_entrega_incluida` (que ya resuelve la alerta y avisa).
3. **COM-06:** `transportista_en_ruta` (impedimento del invernadero y de la baja de cuenta) y PROD-VNC-CAM 3b: `quitar_lineas_liberadas` solo toca las «a realizar»; una entrega en curso con producto vencido se trata en 3b. COM-INI-RUT usa `peso_de_entregas` y bloquea el invernadero antes de cambiar el vehículo.
4. **Documentación a corregir** (`docs/temas_abiertos.md`, «COM-05a1»): el nombre `contrato_entrega`; las varias `AlertaComercial` por entrega; el «último correo» del paso 50. Agregar en `docs/patrones/bloqueos.md`, «Entregas y envasado», el orden de la baja de cuenta tal como quedó (invernaderos de las entregas y después las entregas).
5. **Pasada manual en navegador real** (paso 9 de la «Verificación a mano» de COM-05a1) para el cierre de la tanda de «Comercial 1».

## Nacidos en CMP-04 (24/11/2026)

1. **Hecho el 25/11/2026 en CMP-05** (`pagos.avisar_si_quedo_para_pagar`, llamada desde `registrar_recepcion` y `cerrar_con_faltante`; usa la misma regla que la bandeja). Texto original: **Aviso «quedó para pagar» (CMP-05, D-91).** `avisar_si_quedo_para_pagar(...)` se llama desde `registrar_recepcion` y `cerrar_con_faltante` y tiene que usar la misma regla que ya calcula `resumir_cierre` (todas las líneas del proveedor en la orden completas o cerradas y algo recibido). Hoy ninguna de las dos avisa nada ni arma la bandeja.
2. **Hecho el 25/11/2026 en CMP-06: emitir el reclamo** (`reclamos.emitir_reclamo`: resuelve la alerta por su `AlertaCompras`, completa la sección «Reclamos» y la tarjeta del Inicio del Gerente). Texto original: **Emitir el reclamo (CMP-06).** Resuelve la alerta del Gerente (`AlertaCompras.alerta`), completa la sección «Reclamos» de la ficha y la tarjeta «Reclamos sin emitir» del inicio del Gerente. Hoy `ReclamoProveedor` solo se crea «abierto» y sin emitir.
3. **Hecho el 25/11/2026 en CMP-06: la corrección de una recepción** (`correcciones.py`, con `stock.lotes_de_ingreso` y los `DetalleRecepcionMovimiento`). Texto original: **Corrección de una recepción (CMP-06).** Usa `stock.lotes_de_ingreso` (ya escrita) y los `DetalleRecepcionMovimiento`; hoy una recepción no se puede corregir.
4. **Auditoría de las alertas que resuelve `inventario`.** `registrar_ingreso_por_recepcion` no devuelve la reevaluación, así que el registro de la recepción no lista `alertas_resueltas`; si se quiere, la función tiene que devolverla.

## Lo que deja COM-05a2 (nace el 24/11/2026)

1. **COM-06a:** COM-CNC-ENT confirma la cantidad utilizada y devuelta de cada `ReservaInsumo` «activa» de la entrega (pasos 4, 9 y 10) y el exceso de envases va en el consumo, **sin tocar la restricción** (D-68, punto 2). La extensión 14a (retiro en concreción) tiene que verificar que las reservas de insumo no cambiaron entre el paso 4 y el registro: `envasado.huella_de(entrega_id)` y el bloqueo de la entrega al registrar el envasado son lo que necesita. PROD-VNC-CAM 3b trata la entrega **en curso** (`entregas.en_curso`), que el envasado ya respeta (3b, 10a).
2. ~~**COM-05b.**~~ **Hecho el 25/11/2026 en COM-05b.** Texto original: la cancelación de la compra-venta usa `cancelar_entrega_incluida`, que ya cancela las reservas de insumo de la entrega («cancelada», sin consumo) y avisa al Agrónomo; el envasado deja de abrirse en una entrega cancelada (10a).
3. **Documentación a corregir** (`docs/temas_abiertos.md`, «COM-05a2»): la migración de `core` es la 0042; «Entregas de hoy» sin filtro de fecha; las notificaciones sin enlace al envasado van a `pendientes_CU` (D-42, D-66).
4. **Pasada manual en navegador real** (paso 12 de la «Verificación a mano» de COM-05a2) para el cierre de la tanda de «Comercial 1».


## Lo que deja COM-05b (nace el 25/11/2026)

1. **COM-06a:** una entrega «en curso» se arma hoy solo con un vehículo de fábrica (`vehiculo_en_ruta`): COM-INI-RUT toma el invernadero de origen antes de cambiar el vehículo (D-66, punto 11), y con la ruta real COM-06 confirma a mano la asignación (3a) y la cancelación (4a) que hoy cubren solo las pruebas. Con una entrega concretada real, el rechazo `venta_con_entregas_concretadas` y la prueba de la venta con detalles entregados (D-67, punto 4) se completan con datos reales.
2. **COM-08b:** la extensión 6a de COM-CNL-CVT reemplaza el rechazo `venta_con_entregas_concretadas` (la prueba de COM-05b que lo espera se reemplaza; anotarlo en el PR) y suma `medio_pago` a `DatosDeCancelacionDeVenta`, el cobro y la venta «concretada» con los datos de la cancelación (la restricción de MD-130 ya lo admite).
3. **Documentación a corregir** (`docs/temas_abiertos.md`, «COM-05b»): `sin_permiso` por `PermissionDenied`; «Ver cómo queda» como `POST`; el comprobante de cancelación después de la transacción; la restricción `compra_venta_motivo_cancelacion_valido` en `docs/modelo/comercial.md`.
4. **Pasada manual en navegador real** (paso 19 de la «Verificación a mano» de COM-05b) para el cierre de la tanda de «Comercial 1».

## Lo que deja CMP-05 (nace el 25/11/2026)

1. **Hecho el 25/11/2026 en CMP-06** (`pago_registrado`, con la prueba «corrección contra pago» en `test_correcciones_concurrencia.py`). Texto original: **CMP-06 (corrección de una recepción):** tiene que impedirla si el par (orden, proveedor) ya tiene `Pago` (`Pago.objects.filter(orden=…, proveedor=…)`; D-89 punto 6: «la corrección exige que no haya pago») y, al corregir, sacar al proveedor de la bandeja si deja de estar listo: la bandeja se calcula, así que no hay nada que reasignar. La corrección **nunca avisa** (D-91 punto 3). La prueba «pago contra corrección de recepción» de `test_pagos_concurrencia.py` se escribe con CMP-06.
2. **Hecho el 25/11/2026 en CMP-06** (la tarjeta de reclamos de la ficha del proveedor y «Reclamos sin emitir» del Inicio). Texto original: **CMP-06 (reclamos):** la columna «Pago» de la ficha del proveedor ya existe; falta la de reclamos. «Reclamos sin emitir» del Inicio del Gerente sigue pendiente.
3. **Mejora futura:** «comprobante del pago» (número de operación o de recibo): necesita una columna en `Pago` y una decisión nueva.

