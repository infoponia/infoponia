# COM-05b · Asignar transportista y cancelar la compra-venta

Estado: pendiente | App: comercial | Rama: feature/com-05b-asignar-transportista-y-cancelar-compra-venta | Ronda: Comercial 1

Depende de: **COM-05a2** (y, con ella, COM-05a1: `Entrega`, `candidatos_para`, `peso_de_entregas`, `en_curso`, la lista de entregas,
`cancelar_entrega_incluida`, la acción `asignacion_transportista`; y todo lo anterior: `cancelar_cosecha_incluida` de COM-04a,
`crear_partida` y `costo_unitario_de_cosecha` del núcleo, PROD-ASG-CAM de COM-04b, `anular_enlaces_de` de COM-04c, los comprobantes de
COM-02). Si COM-05a2 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** Lo que una **persona** hace sobre una entrega que ya existe o sobre la venta (D-66, punto 1): el Vendedor (o el Gerente)
**asigna o cambia el transportista** de una entrega, eligiendo entre los que pueden llevarla ese día (COM-ASG-TRP), y **cancela una
compra-venta** que el cliente ya no quiere: libera todo lo reservado, manda a la cámara lo ya cosechado, cancela las cosechas y las entregas
pendientes, anula el enlace de decisión y le manda al cliente el comprobante (COM-CNL-CVT, que incluye PROD-CNL-ORD). La alerta «entrega sin
transportista» pasa a llevar al Gerente directo a la asignación. **No toca `produccion`.**

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-ASG-TRP | Asignar Transportista a Entrega | docs/casos_de_uso/comercial/entregas.md (sección «COM-ASG-TRP» y su «Cómo se aplica») | 9a: las notificaciones van dentro de la transacción (D-42); el correo, con reintento en el paso 50 (D-66, punto 12) |
| COM-CNL-CVT | Cancelar Compra-venta | docs/casos_de_uso/comercial/compra_venta.md (sección «COM-CNL-CVT» y su «Cómo se aplica») | Extensión 6a y el cobro (postcondición f): COM-06 y COM-08. Asiento del cobro: **Fuera de esta ronda · contabilidad** (D-57). Detalles confirmados sin entregar: se cancelan (D-67, punto 4) |
| PROD-CNL-ORD | Cancelar Orden, incluida por COM-CNL-CVT (cosechas y entregas de la venta) | docs/casos_de_uso/produccion/cancelar_orden.md (sección «Comercial 1»: la compra-venta cancelada) | Sin código nuevo de cancelación: usa `cancelar_cosecha_incluida` y `cancelar_entrega_incluida` |

## Leer

- Casos de uso: de docs/casos_de_uso/comercial/entregas.md, **la sección «COM-ASG-TRP» completa** (el caso de uso, «Cómo se aplica», «Pantallas»,
  «Lo que difiere» y «Pruebas») y, de lo de COM-05a1, «Candidatos, verificaciones y selección», «Avisos y textos», «Alerta…» y «Auditoría»; de
  docs/casos_de_uso/comercial/compra_venta.md, **la sección «COM-CNL-CVT» completa** (con «Cambios ya decididos», «Cómo se aplica» y la
  contradicción de los confirmados) y, de lo de COM-02, «COM-CNS-CVT» (reglas 4 y 5) y el comprobante de «COM-REG-CVT»; de
  docs/casos_de_uso/produccion/cancelar_orden.md, las secciones «Comercial 1»: cosechas (`cancelar_cosecha_incluida`), «entregas y envasado»
  (`cancelar_entrega_incluida`) y «la compra-venta cancelada»; de faltante.md, el paso 6.4 (el rechazo: es el mismo cálculo de la partida).
- Modelo: docs/modelo/comercial.md (**CompraVenta** con los datos de MD-130 y sus restricciones; **DetalleVenta**, el estado «cancelado»;
  ReservaStock, DetalleReserva, Entrega, DetalleEntrega, EnlaceCliente); docs/modelo/produccion.md (StockCosechado: el motivo
  `cancelacion_cliente`).
- Decisiones: **D-67** (la de esta tarea, puntos 3 y 4), D-66 (puntos 9 a 12), D-65, D-64 (puntos 3 y 12), D-59, D-61, D-55, D-14, D-25, D-27,
  D-28, D-29, D-36, D-37, D-40, D-42, D-44, D-54, D-57.
- Patrones: docs/patrones/bloqueos.md (sección `comercial`: «Cosecha y cámara» y «Entregas y envasado», con «Asignar un transportista» y
  «Cancelar una compra-venta»), docs/patrones/stock_maduro.md (secciones 1 y 8), docs/patrones/enlace_del_cliente.md (`anular_enlaces_de`),
  docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md («Migraciones»).
- API: docs/api/produccion.md (secciones 1 y 8: `cancelar_orden_incluida`, `crear_partida`, `costo_unitario_de_cosecha`; no se cambian),
  docs/api/alertas.md (secciones 1, 2, 4 y 8), docs/api/notificaciones.md.
- Disparadores: docs/disparadores.md — «Cuando exista Entrega», puntos 2, 7, 8 y 9.
- Pantallas: docs/prototipos/comercial/ (leé primero su `README.md`): `tabEntregas` (las acciones), `INIT.asg`, `VIEWS.asg` y `candidatos` (vale
  la última definición), `ACT['asg-ok']`; `VIEWS.cv` (el botón), `INIT.cvcancel`, `VIEWS.cvcancel`, `ACT['cvcancel-ok']`. Lo que difiere está
  en «Lo que difiere del prototipo» de cada sección.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer:
  - `comercial/` completo (COM-01 a COM-05a2): modelos, `servicios/` (`entregas.py`, `compra_ventas.py`, `cosechas.py`, `camara.py`,
    `faltantes.py`, `enlaces.py`, `comprobantes.py`, `stock_maduro.py`, `vehiculos.py`), vistas y plantillas de entregas y de compra-venta,
    `apps.py` (el registrante del enlace de la alerta), fábricas, `verificar_invariantes_de_reservas` y `verificar_invariantes_de_entregas`;
  - `produccion/servicios/ordenes.py` y `camara.py`, para **usarlos**;
  - `maestros/servicios/invernaderos.py` (`bloquear_invernadero_activo`, `bloquear_invernadero_para_alertas`), `maestros/extensiones.py`
    (`registrar_enlace_de_alerta`), `maestros/servicios/alertas.py`;
  - `core/notificaciones.py`, `core/correo.py`, `core/models.py` (auditoría).

## Límites

- Crea modelos: en `comercial`, los tres campos de MD-130 en `CompraVenta` con sus restricciones (`docs/modelo/comercial.md`) y, **si COM-02
  no lo creó**, el valor `cancelado` de `DetalleVenta.estado_detalle_venta` (la ficha lo lista desde COM-02: miralo en el código).
  → revisá docs/disparadores.md: cierra los de la sección 9 del plan para COM-05b (paso 7).
- Migraciones (con el número libre en `main` al abrir el PR; **ninguna de datos**):
  - `comercial/migrations/00NN_cancelacion_compra_venta.py`: los tres campos, sus restricciones y, si hace falta, los `choices` del detalle;
  - `core/migrations/00NN_comercial_cancelacion_compra_venta.py`: solo `choices` (acción `cancelacion_compra_venta`;
    `asignacion_transportista` ya existe).
  **Ninguna en `produccion`.**
- Permitido fuera de `comercial`:
  - `core`: en `core/models.py`, la acción, `ETIQUETAS` (los campos nuevos), `VALORES_VISIBLES` (`motivo_cancelacion_venta`) y
    `ACCIONES_DE_NEGOCIO`;
  - al cerrar (M3), los textos de `docs/disparadores.md`, `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md`, `docs/temas_abiertos.md`
    y `docs/estado.md`.
  **Nada de `produccion` ni de `maestros`**: lo que se usa de ellas ya existe.
- Dependencias nuevas: ninguna.
- Fuera de alcance: la extensión 6a de COM-CNL-CVT y el cobro de lo entregado (COM-06 deja el rechazo con datos reales y COM-08 el cobro, con
  `PagoCliente`; disparador «Cuando exista Entrega», punto 9); los asientos (D-57); iniciar la ruta, concretar y el intento fallido (COM-06:
  hasta entonces, «en curso» solo se da con un vehículo de fábrica); la cancelación automática de una venta que nunca se retira (el caso de uso
  no la tiene); quitar el transportista de una entrega sin poner otro (decisión D de COM-ASG-TRP); reintentos automáticos de notificaciones.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y auditoría** (MD-130). Los tres campos de `CompraVenta` con sus restricciones; el valor `cancelado` si falta; la acción de
   `core`. Fábricas: `venta_con_todo(...)` (una venta con un detalle abierto con cosecha «a realizar», otro con líneas de lote ya cosechadas y
   de cámara, y su entrega «a realizar» con envases), `vehiculo_en_ruta(...)`.
   Pruebas: en `comercial/tests/test_modelos_compra_venta.py` (o el archivo de modelos de COM-02), métodos nuevos: cada restricción, la viola
   y no la viola (una venta cancelada por COM-DCD-FLT sin motivo no la viola).
2. **COM-ASG-TRP, servicios** (`entregas.md`, «COM-ASG-TRP», «Servicios» y «Reglas en el código»): `datos_de_asignacion`,
   `resumen_de_asignacion`, `huella_de_entrega`, `asignar_transportista`; el registrante del enlace de la alerta cambia a la asignación (1b).
   Pruebas: `comercial/tests/test_com_asg_trp.py`, `ComAsgTrpServicioTests` (la lista de «Pruebas» de la sección).
3. **COM-CNL-CVT, servicios** (`compra_venta.md`, «COM-CNL-CVT», «Servicios» y «Reglas en el código»): `datos_de_cancelacion`,
   `resumen_de_cancelacion_de_venta`, `huella_de_venta`, `cancelar_compra_venta`; el comprobante de cancelación en `comprobantes.py`.
   Pruebas: `comercial/tests/test_com_cnl_cvt.py`, `ComCnlCvtServicioTests` (la lista de «Pruebas» de la sección) y los métodos nuevos de
   `test_prod_cnl_ord_entregas.py` y `test_cancelar_cosecha_incluida.py` (`cancelar_orden.md`, «la compra-venta cancelada»).
4. **Concurrencia**: los métodos nuevos de `test_entregas_concurrencia.py` (COM-ASG-TRP) y `test_com_cnl_cvt_concurrencia.py` (COM-CNL-CVT);
   en `test_entregas_concurrencia.py`, también la que COM-05a1 dejó para esta tarea («una planificación contra la cancelación de la misma
   venta»).
5. **Vistas y plantillas.** En la lista de entregas, «Asignar transportista» y «Cambiar transportista» (y «En curso» sin acción); la pantalla
   de asignación con su `calcular/` y el respaldo «Ver cómo queda»; en la ficha de la compra-venta, «Cancelar compra-venta» y los datos de una
   venta cancelada; la pantalla de cancelación con su `revisar/` y la ventana de resumen; «Imprimir comprobante» sin correo. Vistas que solo
   orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores por campo y aviso breve
   (D-29): «OT-0231 asignada a Ana Pérez.» (con «Se reprogramó para hoy y se avisó el retraso.» en 4a); «CV-0044 cancelada. Se canceló 1
   cosecha y 1 entrega; 40 plantas entraron a la cámara.» más lo del comprobante.
   Pruebas: `ComAsgTrpVistaTests` y `ComCnlCvtVistaTests` (las de las dos secciones) y los métodos nuevos de `test_entregas_vistas.py`.
6. **Invariantes**: `verificar_invariantes_de_reservas()` y `verificar_invariantes_de_entregas()` después de cada prueba de los pasos 2 y 3
   que escribe (ninguna reserva de un detalle cancelado queda sin liberar; ninguna entrega «a realizar» de una venta cancelada).
7. **Cierre de documentación.** Proponé, sin aplicarlos (M3): en `docs/disparadores.md`, tachar lo de COM-05b (la fila de la sección 9 del
   plan) y confirmar el punto 9 (lo que queda para COM-06 y COM-08); la fila de la tarea en `docs/tareas/README.md` y en el plan; lo distinto
   de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el respaldo «Ver cómo queda» sin JavaScript de la asignación (queda en
`docs/temas_abiertos.md`; la asignación sin JavaScript sigue funcionando, con el resumen después de elegir). No se recortan las restricciones de
la base, los bloqueos, la relectura de 8a y 8b de los dos casos de uso, la cancelación de los confirmados sin entregar ni las pruebas de
concurrencia.

## Hecho cuando

- El Vendedor (o el Gerente) asigna un transportista a una entrega sin transportista, o la cambia de transportista, eligiendo entre los que
  pueden llevarla ese día; la alerta se resuelve, los dos transportistas y (si actuó el Gerente) el Vendedor reciben el aviso, y si la fecha
  ya había pasado, la entrega sale hoy con el aviso de retraso y el correo al cliente. Una entrega en curso no se reasigna.
- Desde la alerta «entrega sin transportista», el Gerente llega directo a la asignación de esa entrega.
- El Vendedor (o el Gerente) cancela una compra-venta abierta o pendiente sin entregas en curso: todo lo reservado se libera, lo cosechado
  entra a la cámara (y se asigna solo a quien lo espera), las cosechas y entregas pendientes se cancelan con aviso a quienes las tenían, el
  enlace de decisión queda anulado y el cliente recibe el comprobante (o se imprime).
- Todas las pruebas de `produccion`, `maestros`, `core`, `inventario` y de las tareas anteriores de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test comercial --keepdb --tag concurrencia

## Verificación a mano (la completa Claude Code al cerrar)

Los datos los creás vos a mano: **no hay cargador** (D-95 lo retiró y no vuelve; D-96). Cada paso dice qué ya cubre una prueba, para que si tenés poco tiempo te concentres en lo que se ve y se siente.

**Antes de empezar**

1. Con el entorno virtual activo: `python manage.py migrate` (aplica `comercial` 0009 y `core` 0043: tres columnas nuevas en `comercial_compraventa` y la acción nueva de auditoría; no tocan datos) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas (usá las de prueba que ya tengas; nada de contraseñas en el repo): un **Gerente**, un **Vendedor** con un invernadero activo «Sur» a su nombre, un **Agrónomo** y un **Capataz** del invernadero, y **tres Transportistas** asignados a «Sur» (en «Logística» de la ficha del invernadero):
   - **Juan Gómez**, con una camioneta de **50 kg**;
   - **Ana Pérez**, con un furgón de **400 kg**;
   - **Luis Soto**, con un furgón de **400 kg**.
3. En «Configuración»: máximo de entregas diarias **2** y de localidades distintas por día **2**.
4. Un cliente **con correo** («Verdulería Los Pinos», CUIT `30-71234567-1`, correo tuyo) con una dirección activa, y otro **sin correo** (CUIT `30-50000001-4`; si ese CUIT no valida en tu base, usá cualquier otro válido) con una dirección activa.
5. Stock: el que ya tengas en Maduración (lotes con plantas listas) y, para el paso 7, una **segunda variedad**. Necesitás lotes de **dos variedades** con al menos 60 plantas libres cada una.
6. Las **entregas** las planifica InfoPonia sola cuando una venta tiene todo su producto listo (COM-05a1). Para tener con qué probar:
   - **Entrega A (sin transportista):** sacá a **Ana y Luis** de «Logística» (o dalos de baja) y registrá una compra-venta de **100 plantas** de una variedad que salga **toda de la cámara** (con una partida en «Cámara»), con envío a la dirección del cliente y fecha pactada dentro de 3 días. Con Juan fuera por capacidad (50 kg), la entrega nace «Sin transportista» y la alerta llega al Gerente. Después volvé a asignar a Ana y Luis a «Sur».
   - **Entrega B (para cambiar de transportista):** otra venta de **20 plantas** de cámara, con envío y fecha pactada mañana; con Ana y Luis de nuevo en «Sur», la entrega nace asignada a uno de los dos (se ve en «Comercial › Entregas»).
   - **Entrega C (fecha pasada):** no se puede registrar una venta con fecha pasada. Si una entrega A queda sin transportista y pasan días, el paso diario la deja «Atrasada»; si no, **saltá el paso 5** (lo cubre el recorrido).
   Para la cancelación (pasos 10 a 18) armás las ventas en cada paso.

**COM-ASG-TRP · Asignar y cambiar el transportista**

1. *(Gerente)* En la campana, «Entrega sin transportista»: tocala. **Tiene que verse** «Asignar transportista · OT-…», con el punto de partida, el destino, la fecha, el peso y «Sin asignar». **Juan** aparece con el rótulo «Capacidad de carga insuficiente» y **no se puede elegir**. *(Lo cubre el recorrido.)*
2. Elegí a **Ana**. **Tiene que aparecer** debajo la tarjeta «Cómo queda» (Carga del día «X + Y = Z de 400,00 kg», Entregas del día «1 de 2», Localidades «1 de 2», la fecha), sin que la página salte ni pierda el foco. Todavía no se guardó nada: entrá a «Comercial › Entregas» en otra pestaña y la entrega sigue «Sin transportista».
3. Tocá «Asignar transportista». **Tiene que** volver a «Entregas» con el aviso «OT-… asignada a Ana Pérez.»; la entrega muestra a Ana; la alerta ya no está en la campana. Entrá con Ana: **«Nueva entrega para el dd/mm»**; con el Vendedor: **«OT-… ya tiene transportista»**; en «Auditoría», un `asignacion_transportista` con el Gerente como actor. *(Lo cubre el recorrido.)*
4. *(Vendedor)* En «Comercial › Entregas», la entrega B muestra «Cambiar transportista». Tocala: **Ana no aparece** entre los candidatos. Elegí a **Luis** y «Asignar transportista». **Tiene que** decir «OT-… asignada a Luis Soto.»; Ana recibe **«Ya no tenés la entrega OT-…»**.
5. Con la entrega C (si la tenés): la pantalla dice **«La fecha ya pasó: la entrega se reprogramará para hoy…»**; al asignarla, el aviso termina con «Se reprogramó para hoy y se avisó el retraso.», la fecha pasa a hoy, el Vendedor tiene «Entrega con retraso» y tu correo (el del cliente) recibe «Cambió la fecha de tu entrega…». *(Recorrido y pruebas.)*
6. **Dos pestañas:** abrí la asignación de una misma entrega sin transportista en dos pestañas; asigná en una y después en la otra. **Tiene que** volver a la lista con **«La entrega cambió mientras la mirabas…»** y quedar el transportista de la primera. *(Lo cubre el recorrido.)*
7. **Sin candidatos:** con la entrega A y sin transportistas disponibles, la pantalla dice el motivo de cada uno y, para el **Gerente**, «Podés dar de alta un transportista en la ficha del invernadero («Logística»), un vehículo, o ajustar los límites en «Configuración».»; para el **Vendedor**, «Avisale al Gerente…»; el botón «Asignar transportista» está deshabilitado. *(Lo cubre `ComAsgTrpVistaTests`.)*
8. **Por rol:** con el Agrónomo y el Capataz, escribí a mano `/comercial/entregas/<id>/asignar/`: **403**. Con un Vendedor de otro contrato, también 403. *(Lo cubre `ComAsgTrpVistaTests`.)*
9. **Una entrega en curso no se reasigna** *(no se puede probar a mano: la ruta la inicia COM-06)*: la lista dice «En curso» sin acción y la pantalla avisa que el producto está cargado. *(Solo la cubre una prueba.)*

**COM-CNL-CVT · Cancelar la compra-venta**

10. *(Vendedor)* Armá una venta con **dos variedades**: un detalle que **no tenga todo el stock en lotes aún no cosechados** (que genere una cosecha «a realizar» en la lista de órdenes del Agrónomo) y otro **de cámara** o ya cosechado con su entrega planificada. En el Agrónomo, planificá el **envasado** de esa entrega con 5 envases. En la ficha de la venta tocá **«Cancelar compra-venta»**. **Tiene que verse:** el texto «Cancelar libera todo lo reservado para esta venta…»; «Qué se cancela» (cada detalle con su efecto); «Qué pasa con el producto» (lo que vuelve a los lotes y a las partidas, lo que entra a la cámara **con su fecha límite**, la cosecha y la entrega que se cancelan, y que se cancelan sus envases); el resumen a la derecha y «Se enviará el comprobante a …».
11. Tocá «Revisar y cancelar» **sin motivo**: **error** «Elegí el motivo de la cancelación.» junto a los botones; no pasó nada. Escribí 301 caracteres en «Descripción»: error «La descripción pasa de 300 caracteres.».
12. Elegí «El cliente desistió», una descripción corta, y «Revisar y cancelar». **Tiene que abrirse** la ventana con el resumen y «La cancelación no se puede deshacer.»; «Volver» la cierra sin cancelar. Confirmá con **«Confirmar cancelación»**. **Tiene que** volver a la ficha con el aviso «CV-… cancelada. Se canceló 1 cosecha y 1 entrega; N plantas entraron a la cámara.» más lo del comprobante. *(El flujo lo cubre el recorrido.)*
13. **Efectos a comprobar** (cada uno en su pantalla): la venta «Cancelada» con «Cancelada el dd/mm/aaaa. Motivo: el cliente desistió.»; en «Comercial › Cámara», una partida **«Cancelación del cliente»** con la fecha límite de la cosecha; la cosecha y la entrega **canceladas** (lista de órdenes y «Entregas»); el Capataz y el Agrónomo con **«Orden OT-… cancelada»** y el transportista con **«Se canceló la entrega OT-…»**; el Agrónomo, además, con el aviso de los envases; los envases vuelven a estar libres en «Existencias»; las plantas de lote reservadas vuelven a estar libres; en «Auditoría», un `cancelacion_compra_venta` con tu usuario. El correo del cliente: **«Cancelación de tu compra CV-…»** *(si tenés el correo del sistema configurado; si no, el aviso dice que no se pudo enviar y la ficha ofrece «Reenviar comprobante»)*.
14. **Venta «pendiente de decisión del cliente»:** si tenés una (una partida que venció y dejó sin cubrir a la venta), cancelala; después, abrí el **enlace del correo del faltante**: **«Este enlace no se puede usar»**. *(Lo cubre el recorrido.)*
15. **Cliente sin correo:** cancelá una venta de «Verdulería sin correo». **Tiene que** decir «El cliente no tiene correo: imprimí el comprobante.» y la ficha ofrece el botón **«Imprimir comprobante»**, que abre la página imprimible con «Cancelación de la compra CV-…», el motivo y lo que se canceló. *(Lo cubre el recorrido.)*
16. **El Gerente cancela** otra venta: el Vendedor recibe **«CV-… cancelada»** («El Gerente canceló la venta de …»). *(Lo cubre el recorrido.)*
17. **Una venta cancelada** no ofrece «Cancelar compra-venta»; si escribís `/comercial/contratos/compra-ventas/<id>/cancelar/` a mano, la pantalla dice que ya está cancelada. Con el **Agrónomo**: **403**. *(Lo cubre `ComCnlCvtVistaTests`.)*
18. **Una entrega en curso impide cancelar** *(no se puede probar a mano: la ruta la inicia COM-06)*: el aviso «No se puede cancelar mientras el producto está en viaje…». *(Solo la cubre una prueba.)*
19. **Navegador real (obligatorio: hay formularios que se envían).** Abrí la asignación y la cancelación en una **ventana privada** con la sesión iniciada (para estas pantallas hace falta cuenta) y **enviá cada formulario hasta el final**: asignar un transportista y confirmar una cancelación. Tienen que mostrar el aviso y el resultado esperado. Si aparece «Prohibido (403)», «Verificación CSRF fallida» o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Comprobá también con HTMX: al elegir un transportista **solo se redibuja «Cómo queda»**; «Revisar y cancelar» abre la **ventana** sobre la pantalla.
20. *(Opcional)* **Sin JavaScript** (desactivalo en el navegador): en la asignación, elegí un transportista y tocá **«Ver cómo queda»** (devuelve la página con la tarjeta) y después «Asignar transportista»; en la cancelación, «Revisar y cancelar» muestra el resumen **como una página** con «Volver» y «Confirmar cancelación». *(Lo cubren `ComAsgTrpVistaTests` y `ComCnlCvtVistaTests`.)*
21. *(Opcional)* **En un celular:** estas pantallas son para computadora (requisito especial de los dos casos de uso); verificá solo que se pueden leer.
22. **Después del merge:** revisá en el log de Render que se aplicaron `comercial` 0009 y `core` 0043.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Bloque 1 (modelo): los tres datos de MD-130 en `CompraVenta` (`motivo_cancelacion_venta`, `descripcion_cancelacion`, `fecha_cancelacion_venta`) con cuatro restricciones de la base (`comercial` 0009; `DetalleVenta.cancelado` ya existía desde COM-02) y la acción `cancelacion_compra_venta` con sus etiquetas (`core` 0043, solo `choices`). Bloque 2 (servicios): COM-ASG-TRP en `entregas.py` (`datos_de_asignacion`, `resumen_de_asignacion`, `huella_de_entrega`, `asignar_transportista`, con los bloqueos cuentas → invernadero de origen → entrega y la relectura de 8a y 8b) y COM-CNL-CVT en `compra_ventas.py` (`datos_de_cancelacion`, `resumen_de_cancelacion_de_venta`, `huella_de_venta`, `cancelar_compra_venta`, con los bloqueos de «Cancelar una compra-venta» y la partida `cancelacion_cliente`), con el comprobante de cancelación en `comprobantes.py`. Bloque 3 (pantallas): «Asignar / Cambiar transportista» (con `calcular/` y «Ver cómo queda» sin JavaScript), las acciones de la lista de entregas, «Cancelar compra-venta» (con `revisar/` y la ventana de resumen), la ficha con los datos de la cancelación y el comprobante imprimible; el enlace de la alerta «entrega sin transportista» lleva a la asignación.

**Pruebas (M1).** 
- `python manage.py test comercial produccion maestros inventario core --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion`: **6074 pruebas en 342 s, OK** (base de pruebas recreada por las migraciones nuevas).
- `python manage.py test comercial --keepdb --tag concurrencia`: **96 pruebas en 415 s, OK**.
- `python manage.py check`: sin problemas; `makemigrations --check --dry-run`: sin cambios.
- Pruebas nuevas de la tarea: `test_com_asg_trp.py`, `test_com_cnl_cvt.py`, `test_com_cnl_cvt_concurrencia.py`, `test_recorrido_asignar_transportista_y_cancelar_compra_venta.py`, `CompraVentaCancelacionModeloTests` (en `test_modelos_contratos.py`) y métodos nuevos en `test_prod_cnl_ord_entregas.py`, `test_cancelar_cosecha_incluida.py` y `test_entregas_concurrencia.py`. En el desarrollo, tres corridas parciales las hizo el estudiante en su terminal (los fallos que salieron se corrigieron antes de esta corrida final).

**Verifiqué** (recorrido y migraciones): el recorrido `RecorridoDeAsignarTransportistaYCancelarCompraVentaTests` (la alerta desde la campana → asignar con «Cómo queda» → cambiar transportista con el aviso al anterior → entrega atrasada con el correo → dos pestañas → permisos y entrega en curso; y la cancelación completa de una venta con cosecha, entrega con envases, lo cosechado y la cámara → una venta pendiente con su enlace → cliente sin correo → cancela el Gerente → venta ya cancelada y 403); `makemigrations --check` sin cambios; `sqlmigrate comercial 0009` (tres columnas nuevas, dos nulas y una con `DEFAULT ''` que se quita enseguida, y cuatro `CHECK`: no borra ni reescribe filas, y las ventas ya canceladas por COM-DCD-FLT cumplen las restricciones porque no tienen motivo) y `sqlmigrate core 0043` (no-op, solo `choices`); las dos migraciones aplicadas en la base de pruebas.

**Lo cubre una prueba**: COM-ASG-TRP, reglas, postcondiciones a a f y extensiones 1a, 1b, 3a, 4a, 4b, 5a, 8a, 8b y 9a (`test_com_asg_trp.py`, `ComAsgTrpServicioTests` y `ComAsgTrpVistaTests`; las acciones de la lista en `AccionesDeLaListaTests`, del mismo archivo); COM-CNL-CVT, reglas, postcondiciones a a i y extensiones 1a, 4a, 6a, 6b, 8a, 8b y 9a (`test_com_cnl_cvt.py`, `ComCnlCvtServicioTests` y `ComCnlCvtVistaTests`); PROD-CNL-ORD desde la venta (`test_prod_cnl_ord_entregas.py`, `test_cancelar_cosecha_incluida.py`); modelo (`CompraVentaCancelacionModeloTests`); concurrencia (`test_entregas_concurrencia.py`: asignación contra planificación, dos asignaciones, baja del transportista y cancelación; `test_com_cnl_cvt_concurrencia.py`: cancelar contra concretar, planificación, decisión del cliente, PROD-ASG-CAM y asignación); sin consultas por transportista en `datos_de_asignacion`.

**No pude verificar**: el CSRF, el encabezado `Origin`, el JavaScript de HTMX y el aspecto (paso «navegador real»); una entrega «en curso» a mano (la ruta la inicia COM-06, solo está cubierta por prueba); el envío real del correo al cliente; el log de Render después del merge.

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| `candidatos` / `VIEWS.asg` | Filtraba por nombre y no mostraba todos los motivos | Por id, con todos los motivos de `candidatos_para` y los que no cumplen, deshabilitados con su motivo | «Lo que difiere del prototipo» de COM-ASG-TRP |
| `ACT['asg-ok']` | Asignaba sin volver a verificar, sin auditoría ni avisos, y borraba la alerta | La transacción de 8a y 8b, la auditoría, los avisos y la alerta resuelta (queda en el historial) | Pasos 8 y 9, postcondiciones c a f |
| `VIEWS.asg` («Cómo queda») | Solo aparecía al elegir, sin respaldo | Con HTMX se redibuja al elegir; sin JavaScript, «Ver cómo queda» (POST a `calcular/`, que devuelve la página con la tarjeta) | Paso 6; criterio de interfaz (respaldo sin JavaScript) |
| `VIEWS.asg` (4b) | «Registre un vehículo» | Voseo y distinto para el Gerente y el Vendedor; el botón queda deshabilitado | Extensión 4b |
| `tabEntregas` | Sin acciones | «Asignar transportista», «Cambiar transportista» o «En curso» sin acción, según la entrega | Paso 2, extensión 3a |
| `VIEWS.cvcancel` | Registraba directo, sin resumen ni relectura | «Revisar y cancelar» → resumen (ventana con HTMX, página sin él) → «Confirmar cancelación», con 8a y 8b | Pasos 6 a 8 |
| `VIEWS.cvcancel` | `curso=false`: no impedía cancelar con una entrega en viaje | El aviso de 4a y sin botón de revisar | Extensión 4a |
| `VIEWS.cvcancel` | Cancelaba solo los detalles «abierto» y «pendiente» | También el «confirmado» sin entregar | D-67, punto 4 |
| `VIEWS.cvcancel` | Motivo como desplegable | Tres botones de opción; la descripción opcional también con «Otro» | Criterio de interfaz (menos clics); MD-130 |
| `VIEWS.cvcancel` | Sección 3 «Cobro de lo entregado» y «Asientos» | No van en esta tarea | Extensión 6a (COM-06 y COM-08b), D-57 |
| `VIEWS.cv` | «Se imprimirá el comprobante» | Con un cliente sin correo, el botón «Imprimir comprobante» en la ficha; el comprobante imprimible dice la cancelación | Regla 18 de 8.20 |

**Desvíos respecto de la documentación (para `docs/temas_abiertos.md`, M3):**
- La sección «Datos para verificar» de la tarea nombraba el cargador `comercial/verificacion.py`, retirado por D-95: no se creó; la «Verificación a mano» pide crear los datos a mano.
- Permisos: un actor sin acceso (rol, alcance o cuenta inactiva) recibe `PermissionDenied` (403 con mensaje), como el resto de `comercial`; el extracto decía un código `sin_permiso`. Las cuentas se vuelven a leer de la base, porque el objeto del pedido puede estar viejo.
- «Ver cómo queda» sin JavaScript es un `POST` a `calcular/` (el extracto lo describía como la misma página): así el token de CSRF no queda en la URL.
- El comprobante de cancelación sale **después de la transacción** (como el paso 16 de COM-REG-CVT) y no con `on_commit`: así la pantalla sabe si salió y puede decirlo en el aviso. PROD-ASG-CAM sí va en `on_commit`. Sin el correo del sistema, queda «pendiente de envío» y la ficha ofrece «Reenviar comprobante», que reenvía el de cancelación.
- Se agregó una restricción de la base que no estaba en `docs/modelo/comercial.md`: `compra_venta_motivo_cancelacion_valido` (motivo dentro de su lista cerrada), siguiendo la convención de los `*_estado_valido`.
- `faltantes._rechazar_detalle` se renombró a `liberar_reservas_de_detalle` y recibe el motivo de la partida y el de la cosecha, para que la usen COM-DCD-FLT y COM-CNL-CVT sin duplicar la liberación de reservas (sin cambio de conducta en COM-DCD-FLT: sus pruebas pasan sin cambios).
- `huella_de_venta` incluye los enlaces vigentes y el estado de la cosecha de cada reserva: una cosecha concretada o una entrega asignada mientras se mira el resumen dan `venta_cambio` (8a y 8b se resuelven con el mismo código; el caso de uso las distingue por el mensaje de la pantalla).
- En el aviso al Vendedor cuando cancela el Gerente, y en el motivo que reciben las órdenes, el texto del motivo va en minúscula («el cliente desistió»).

**Pruebas existentes que cambiaron** (la regla cambió; ninguna se debilitó): `test_extensiones_entregas.py`, `test_entregas_vistas.py` y `test_recorrido_entregas.py` (el enlace de la alerta lleva a la asignación; «Cambiar transportista» ya existe), `test_compra_ventas_vistas.py` (la ficha ofrece «Cancelar compra-venta») y `test_com_cns_cvt.py` (regla 5: la acción `cancelar`).
