# COM-07b · Resolución del suministro por incumplimientos (paso diario 33)

Estado: hecha (25/11/2026; revisión a mano pendiente) | App: comercial | Rama: feature/com-07b-resolucion-del-suministro | Ronda: Comercial 1

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

## Verificación a mano (la completó Claude Code al cerrar; la hace el estudiante)

Sin datos cargados (D-95, D-96): el cargador de verificación de la primera versión de esta tarea se retiró; los datos los creás vos a mano con los valores de abajo. Cada paso dice si ya lo cubre una prueba.

**Antes de empezar**

1. En PowerShell, con el entorno virtual activo: `python manage.py migrate` (aplica `core` 0050, solo `choices`; hasta ahí no hay cambios de tablas) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas que necesitás (las de prueba que ya usás): **Gerente**, **Vendedor** (el del invernadero), **Agrónomo** y **Capataz** del invernadero, y un **Transportista** con un vehículo activo (Gerente: «Comercial» → pestaña «Vehículos»; asignalo al invernadero en la ficha del invernadero).
3. Lo que tiene que existir (si ya lo tenés de otras verificaciones, usalo): un invernadero activo con su Agrónomo, Capataz y Vendedor; una variedad con un lote en Maduración de por lo menos 300 plantas; un insumo «envase» con stock habilitado en el invernadero; y un **cliente con un correo que puedas leer**, con una dirección (Comercial → Clientes).
4. **Días de pre-reserva:** en «Configuración» poné «Pre-reserva de suministros» (días) en **21**, para que entren tres períodos semanales en la ventana.
5. **Pactar el suministro** (Vendedor: Comercial → Contratos → Suministros → «Pactar suministro»), con estos valores: cliente, el de arriba; duración **6** meses; incumplimientos tolerados **0**; multa por resolución **50000**; plazo de pago **15** días; indemnización por atraso en el pago **100**; un detalle con la variedad del lote, la dirección del cliente, **50** plantas cada **7** días, primera entrega **dentro de 2 días**, precio fijo **1500**, tolerancia de entrega **0** días, retraso **100** por día, cantidad mínima **30** y faltante **30** por planta. «Ver resumen» y «Confirmar». Tiene que quedar el contrato «SUM-…» en la lista.
6. **Que haya algo que deshacer.** En la terminal: `python manage.py proceso_diario --solo pre_reservar_suministros` (reserva los períodos de la ventana y crea sus cosechas) y después `python manage.py proceso_diario --solo planificar_entregas` (crea las entregas de lo que ya está listo). En el calendario de la ficha del suministro tienen que figurar períodos «Reservado». Entrá como **Agrónomo** a «Producción» → cosechas: tiene que haber cosechas «a realizar» del contrato. Como Agrónomo, si hay una entrega: planificale el envasado con **5** envases (Comercial → Entregas → la entrega → «Envasado»).
7. **La discrepancia que va a resolver el contrato.** Concretá la **primera** entrega con menos plantas que el mínimo: con el Transportista, «Mi ruta» → «Iniciar ruta»; después «Concretar» la entrega del primer período con **20** plantas recibidas (de 50; el mínimo es 30). Eso crea la discrepancia pendiente (Comercial → Solicitudes). Si no hay una entrega del primer período, creá el contrato con la primera entrega «hoy» y corré `planificar_entregas`. Tienen que quedar, además, al menos **otra entrega «a realizar»** y **otra cosecha «a realizar»** de períodos siguientes. Si falta alguna, corré de nuevo los dos pasos del paso 6 o subí los días de pre-reserva.

**Los pasos**

1. **Con el contrato vigente.** Gerente: ficha del suministro (Comercial → Contratos → Suministros → «Ver»). **Tiene que ver:** el estado «Vigente», «Incumplimientos 0 de 0» y **ningún** aviso de resolución ni botón «Dar por atendida». *(Lo cubre el recorrido, paso 1.)*
2. **El resumen advierte.** Gerente: Comercial → Solicitudes → la discrepancia → «Hubo incumplimiento (aceptar)» y «Ver resumen». **Tiene que ver:** que se superan los incumplimientos tolerados, que el contrato «se resolverá» y la multa **$ 50.000,00**. *(Lo cubre el recorrido, paso 2.)*
3. **Aceptar y que se resuelva solo.** «Confirmar la decisión». En segundos, abrí la ficha del suministro. **Tiene que ver:** estado **«Resuelto»**; un aviso rojo «Resuelto por incumplimientos el dd/mm/aaaa: 1 de 0 tolerados, por SR-… Multa: $ 50.000,00. Las entregas concretadas se siguen cobrando.» con el código de la solicitud como enlace y las entregas canceladas; sin «Modificar» ni «Rescindir». En «Entregas» las que estaban «a realizar» figuran **canceladas** (con el motivo «Resolución del suministro SUM-… por incumplimientos.»); la entrega concretada sigue **concretada**. En «Producción» (Agrónomo) las cosechas del contrato figuran **canceladas**. En el calendario no queda ningún período «Reservado». *(Lo cubren `test_com_rsv_sum.py` y el recorrido, paso 3.)*
4. **La cámara.** Si alguna cosecha ya estaba concretada antes: ficha del invernadero → pestaña «Cámara»: aparece una partida nueva con el motivo «Resolución del contrato», la fecha límite contada desde la cosecha y el costo de la cosecha. Si no había nada cosechado, no hay partida (es lo normal en este recorrido). *(Lo cubre `test_post_e_…` de `test_com_rsv_sum.py`.)*
5. **Los avisos.** Entrá con cada cuenta y abrí la campana → «Notificaciones»: el **Vendedor** tiene «SUM-… resuelto por incumplimientos» con la multa y las entregas canceladas; el **Transportista** (si tenía una entrega asignada), «Se canceló la entrega OT-…»; el **Capataz**, el aviso de la cosecha cancelada; el **Agrónomo**, **uno solo**: «SUM-… resuelto: cambios en <invernadero>» con las cosechas y los envases que estaban reservados (si había envasado: «Si ya se usaron, ajustá el stock»). El **cliente** recibe en su correo «Resolución de tu suministro SUM-…», con la multa, las entregas canceladas con su fecha y «sin validez fiscal». *(Lo cubre el recorrido, paso 4; el correo real, no: ver el paso 12.)*
6. **La alerta del Gerente.** Gerente: campana → «Alertas»: «SUM-… (cliente) resuelto por incumplimientos: 1 de 0 tolerados, por SR-…. Multa: $ 50.000,00. Se cancelaron …», en rojo (crítica), con el detalle «SUM-… · resuelto · multa $ 50.000,00». Al hacer clic abre la ficha del suministro. *(Lo cubre el recorrido, paso 5.)*
7. **La lista.** Gerente: Comercial → Contratos → Suministros. **Tiene que ver:** el contrato «Resuelto» con la marca roja **«Resolución sin atender»**. *(Lo cubre `test_resolucion_vistas.py`.)*
8. **No se puede anular la aceptación.** Gerente: la solicitud → «Anular resolución». **Tiene que ver:** «No se puede anular. … esta aceptación resolvió el contrato SUM-…» y solo «Volver». *(Lo cubre el recorrido, paso 7.)*
9. **Solo el Gerente la atiende.** Entrá como **Vendedor**: la ficha muestra el aviso de resolución pero **no** «Dar por atendida» y la lista no tiene la marca. Entrá como **Transportista** y escribí a mano `/comercial/contratos/suministros/<id>/`: da «Prohibido (403)». *(Lo cubre el recorrido, pasos 8 y 9.)*
10. **«Dar por atendida».** **Navegador real:** abrí una **ventana privada** (sin sesión), entrá como Gerente, abrí la ficha y apretá «Dar por atendida» (el texto dice «Usalo cuando hayas pagado la multa y avisado al cliente. La alerta deja de figurar entre tus pendientes.»). **Tiene que ver:** vuelve a la ficha con el aviso «La alerta de la resolución quedó atendida.», el botón desaparece, la alerta sale de la campana y la marca de la lista se va. Después volvé a abrir la ficha: sigue el aviso de la resolución. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. En «Auditoría» (Gerente) hay un `atencion_suministro_resuelto` con el contrato y la alerta, y un `resolucion_suministro` **sin usuario** (proceso automático) con todo lo afectado (la ficha del registro muestra los cambios: estado, fecha de resolución y solicitud). *(Lo cubre el recorrido, paso 10.)*
11. **Una entrega en viaje.** Con **otro suministro** (repetí los pasos 5 a 7 de «Antes de empezar» con otro cliente o variedad): como Transportista, «Mi ruta» → «Iniciar ruta» con una entrega del contrato, y como Gerente aceptá una discrepancia que supere lo tolerado. **Tiene que ver:** el Transportista recibe «Se canceló la entrega OT-…» con «**No la entregues:** devolvé el producto y los envases a <invernadero>.» *(Lo cubre `test_ext_3c_…` y la prueba de concurrencia de la ruta.)*
12. **El disparo perdido y el paso 33.** En el shell (`python manage.py shell`): `from comercial.models import Suministro; Suministro.objects.filter(pk=<id de un suministro vigente>).update(cantidad_incumplimientos=5, incumplimientos_tolerados=1)` (cualquier suministro vigente con más incumplimientos que los tolerados). Después `python manage.py proceso_diario --solo resolver_suministros`: **tiene que decir** «Resolver suministros con incumplimientos superados» con «1 suministros resueltos, 0 descartados, 0 con error» y el contrato queda «Resuelto» (sin solicitud: la ficha no muestra el enlace). Corré el mismo comando otra vez: **no hace nada** (0 procesados). `python manage.py proceso_diario --listar` muestra el paso 33 antes del 35, el 40 y el 50. *(Lo cubren `ComRsvSumRecuperacionDiariaTests` y el recorrido, paso 12.)*
13. **Un contrato sin nada pendiente.** Repetí el paso 12 con un suministro que no tenga entregas ni reservas (recién pactado, con la primera entrega dentro de más días que la ventana): se resuelve igual, con su alerta. *(Lo cubre `test_ext_3a_…`.)*
14. **Opcional: el cliente sin correo.** Con un cliente sin correo, la ficha del suministro resuelto dice «Para imprimir» en «Comprobante» y no ofrece «Reenviar comprobante». Con un correo que falle, «Pendiente de envío» y «Reenviar comprobante» manda el aviso de **resolución** (no el de registro). *(Lo cubre `test_ext_8a_reenviar_…`.)*
15. **Opcional: sin JavaScript.** Desactivá JavaScript en el navegador: «Dar por atendida» sigue siendo un botón que envía el formulario (POST) y funciona igual. *(Lo cubre `test_regla_sin_javascript_…`.)*
16. **Opcional: en un celular** la ficha del suministro resuelto y la lista se leen y «Dar por atendida» se aprieta bien.
17. **Después del merge:** en el log de Render, la migración `core.0050_comercial_resolucion` aplicada.

## Cierre (la completó Claude Code al cerrar, 25/11/2026)

**Qué se hizo** (en el orden de los pasos)

1. **`avisar_agronomo`** (por omisión `True`) en `cancelar_cosecha_incluida` y `cancelar_entrega_incluida`: con `False`, solo se omite el aviso al Agrónomo (la entrega igual devuelve sus reservas de insumo, para el aviso único de la resolución). Las pruebas de COM-04a, COM-05a1 y COM-05b no se modificaron.
2. **Resolver un suministro** (`comercial/servicios/resoluciones.py`): `resolver_si_corresponde` (disparador 1, con `on_commit`; no deja pasar una falla), `resolver_suministro` (lectura sin bloquear → bloqueos de «Resolver un suministro» → relectura con una repetición, 6a → cosechas, partidas, reservas y entregas → contrato y detalles «resueltos» con `solicitud_resolucion` → alertas de período sin cobertura → alerta «suministro resuelto» → avisos → UN registro `resolucion_suministro`; después de confirmar, PROD-ASG-CAM y el aviso al cliente). La liberación de reservas se sacó a `faltantes.liberar_reservas` (la usan también COM-DCD-FLT y COM-CNL-CVT). Aviso de resolución al cliente con `enviar_comprobante(tipo="resolucion")` (plantilla `resolucion_suministro.txt`). En `core`: las acciones `resolucion_suministro`, `resolucion_suministro_descartada` y `atencion_suministro_resuelto` con sus etiquetas, y la migración `0050_comercial_resolucion` (solo `choices`).
3. **Recuperación diaria:** `resolver_suministros_pendientes(hoy)`, registrada en `ComercialConfig.ready()` como el paso 33 (antes del 35, el 40 y el 50); el comentario de `core/procesos.py` suma el 33.
4. **Concurrencia** (`test_resolucion_concurrencia.py`): resolver contra concretar una cosecha, concretar una entrega, planificar una entrega, la pre-reserva, iniciar la ruta, dos resoluciones a la vez y anular la solicitud que la provoca, en los dos órdenes.
5. **Ficha, lista y «Dar por atendida»:** el aviso de la resolución en la ficha (con la solicitud, la multa y las entregas canceladas), la marca «Resolución sin atender» de la lista (Gerente), «Dar por atendida» (POST del Gerente; `resoluciones.dar_por_atendida_la_resolucion`, con auditoría `atencion_suministro_resuelto`) y el enlace de la alerta en la campana.
6. **Cierre:** el recorrido, las migraciones y esta documentación.

Archivos tocados fuera de `comercial/`: `core/models.py` (las acciones, `ETIQUETAS` y `ACCIONES_DE_NEGOCIO`), `core/migrations/0050_comercial_resolucion.py` y `core/procesos.py` (solo el comentario). No se tocó `produccion`, `maestros`, `contabilidad` ni ningún modelo; ninguna dependencia nueva.

**Pruebas**

- Nuevas (79): `test_com_rsv_sum.py` (45; `ComRsvSumServicioTests` y `ComRsvSumRecuperacionDiariaTests`), `test_resolucion_concurrencia.py` (13), `test_resolucion_vistas.py` (16), `test_recorrido_resolucion_del_suministro.py` (1) y cuatro métodos en `test_cancelar_cosecha_incluida.py` y `test_prod_cnl_ord_entregas.py` (el argumento `avisar_agronomo`).
- **M1** (el «Comando de pruebas» de la tarea, acotado a `comercial` y `core` por pedido del estudiante; `produccion` no se tocó y lo corre el CI): `python manage.py test comercial core --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion` → **3297 pruebas, OK** (antes de sumar `test_ext_d63_4_…`, que corrió aparte con el resto de las nuevas: 62 pruebas, OK). `python manage.py test comercial --keepdb --tag concurrencia` → **124 pruebas, OK** (todas las de concurrencia de `comercial`, 13 propias de esta tarea). `--tag migracion` (`core`): **1 prueba, OK** (la de `core`) (la migración no es de datos: no hay prueba de migración propia).
- **Prueba existente reemplazada** (se anota en el PR): `test_recorrido_solicitudes_de_revision.py`, que esperaba el contrato «vigente» tras superar los tolerados («estado de paso»): ahora verifica que la aceptación lo resuelve, con la solicitud que lo provocó. Ninguna se borró ni se debilitó.

**Decisiones y desvíos** (también en `docs/temas_abiertos.md`, «COM-07b»): descripción de la alerta de 200 caracteres (el límite de `maestros.Alerta`; el caso de uso dice 500); `resolver_si_corresponde` no deja el registro 2b en una aceptación común (el registro lo deja `resolver_suministro`); `faltantes.liberar_reservas` extraída; invariante `verificar_invariantes_de_resolucion` aparte; `dar_por_atendida_la_resolucion` en `resoluciones.py` con un delegado en `suministros.py`. **No hubo decisión nueva** (no se propone `D-NN`).

**Informe (D-96)**

*Verifiqué*
- El recorrido de punta a punta con el cliente de Django (`RecorridoDeResolucionDelSuministroTests`): la aceptación que supera lo tolerado, el resumen que lo advierte, la resolución, los avisos y el correo, la campana y su enlace, la ficha y la lista del Gerente y del Vendedor, el 403 del Transportista, la anulación rechazada, «Dar por atendida», el paso 33 y su segunda corrida. **OK.**
- `makemigrations --check --dry-run`: «No changes detected». `manage.py check`: sin problemas. `sqlmigrate core 0050`: un no-op (solo cambian los `choices` de `RegistroAuditoria.accion`: no toca tablas ni datos). Aplicada en la base de pruebas (`--keepdb`) sin errores.
- Claves duplicadas en `ETIQUETAS` y `VALORES_VISIBLES` de `core/models.py` (D-36): ninguna (revisado con el AST del archivo).
- `docs/estado.md` pesa 1887 bytes (menos de 2048).

*Lo cubre una prueba*
- Cada postcondición (a a g, i a m; la h, que no se implementa, con `test_post_h_no_se_crea_ningun_asiento…`) y extensión (*a, 1a, 2a, 2b, 3a a 3d, 5a, 6a con una y con dos repeticiones, 6b, 7a, 8a, 9a, D-63 punto 4) en `test_com_rsv_sum.py`.
- El paso 33 (orden, idempotencia, un contrato que falla, `proceso_diario --solo`), la rescisión acordada que se resuelve: `ComRsvSumRecuperacionDiariaTests`.
- Los choques de concurrencia: `test_resolucion_concurrencia.py`. Las pantallas, los permisos, el POST sin JavaScript y el enlace de la campana: `test_resolucion_vistas.py`.

*No pude verificar*
- El **navegador real** (el CSRF y el encabezado `Origin` de «Dar por atendida», el aspecto de la ficha y de la lista, el aviso breve, el foco con Tab y el celular): paso 10 de la «Verificación a mano». No abro navegadores (D-96).
- El **correo real** al cliente y a los demás (las pruebas usan el correo simulado de Django).
- La suite de `produccion` y la completa del proyecto: las corre el CI en el PR (esta tarea no cambia código de `produccion`).
- El rendimiento con 10 detalles en menos de 5 segundos (prueba opcional `@tag("rendimiento")`, no escrita).
- El despliegue: que Render aplique `core.0050_comercial_resolucion` (paso 17).

### Pantallas: lo que se corrigió del prototipo (D-61)

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Ficha del suministro (`VIEWS.sum`) | Mostraba «resuelto» y la fecha; sin aviso ni forma de atender la alerta; el contrato pasaba a «resuelto» en la misma operación de la aceptación | Aviso rojo con la fecha, los incumplimientos, el enlace a la solicitud, la multa («asiento: fuera de esta ronda»), las entregas canceladas y «Las entregas concretadas se siguen cobrando»; para el Gerente, la tarjeta «Resolución sin atender» con «Dar por atendida» (formulario POST, sin JavaScript también) | Postcondición i, regla «Alerta “suministro resuelto”», D-69 punto 14 |
| Lista de contratos (`tabContratos`, rama `sum`) | Sin marca de resolución | Marca «Resolución sin atender» (solo Gerente, mientras la alerta esté activa) | Regla «Lista» de «La resolución en la ficha y en la lista» |
| Ficha, estado de error | Sin caso | «Dar por atendida» repetida (o con la alerta ya atendida) vuelve a la ficha con «Esta alerta ya fue atendida.»; no es un error 500 | Código `alerta_resuelta` |
| Ficha, sin permiso | Sin caso | El botón no se muestra al Vendedor ni a otros roles; el POST a mano da 403 | D-30 |
