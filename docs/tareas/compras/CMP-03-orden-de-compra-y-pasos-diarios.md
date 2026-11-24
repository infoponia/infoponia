# CMP-03 · Orden de compra y pasos diarios de compras

Estado: hecha en rama, falta PR | App: compras | Rama: feature/cmp-03-orden-de-compra-y-pasos-diarios | Ronda: Compras 1

Depende de: **CMP-02b**. No depende de la contabilidad (la orden no genera asiento: D-91, D-86).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo **genera** la orden de compra eligiendo, línea por línea, la cotización más conveniente (puede repartir entre
proveedores); el Gerente la **aprueba** o la rechaza; al aprobarse, las cantidades pasan a **tránsito** en el stock. Además, los tres **pasos
diarios** que vencen pedidos, recuerdan la validez y cancelan los que no tienen cotización elegible.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-GNR-ODC | Generar Orden de Compra | docs/casos_de_uso/compras/ordenes_de_compra.md | — |
| CMP-APR-ODC | Aprobar Orden de Compra (y rechazar) | docs/casos_de_uso/compras/ordenes_de_compra.md | — |
| CMP-CNS-ODC | Consultar Orden de Compra | docs/casos_de_uso/compras/ordenes_de_compra.md | Recepciones, pagos y reclamos de la ficha: CMP-04 a CMP-06 |
| (D-87, punto 4) | Pasos diarios 60, 61 y 62 | docs/casos_de_uso/compras/ordenes_de_compra.md («Pasos diarios 60 a 62») | — |
| (H21) | A quién van los avisos si el Agrónomo del pedido ya no está | docs/casos_de_uso/compras/ordenes_de_compra.md («Cambio del punto 6») | Usa `destinatarios_por_destino` de CMP-02a |
| CMP-BAJ-PRV (precondición c) | Orden aprobada sin recibir impide la baja del proveedor | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |

## Leer

- Casos de uso: `ordenes_de_compra.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`OrdenCompra` y `DetalleOrdenCompra`; R026 derivado).
- Decisiones: D-87 (puntos 3 y 4: pasos diarios y sus campos técnicos), D-89, D-90 (solo «tránsito»), D-56 (proceso diario), D-36, D-42, D-44.
- API: docs/api/stock.md («Escritura de compras»: `sumar_transito`), docs/api/notificaciones.md, docs/api/alertas.md; el contrato del
  proceso diario es D-56 y el encabezado de `core/procesos.py`.
- Patrones: docs/patrones/bloqueos.md (orden de compras), docs/patrones/stock.md, docs/patrones/auditoria.md.
- Pantallas: `tabOdc`, `VIEWS.c_gen` (comparar cotizaciones y generar), `VIEWS.c_apr` (revisar y decidir), `VIEWS.c_odc`, `panelAgr` («Pedidos que
  vencieron»), `panelGer` («Órdenes pendientes de aprobación»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-02a/02b; `core/procesos.py` (`registrar_paso_diario`, `ResumenDePaso`) y un paso existente como modelo;
  `inventario/servicios/stock.py`; `maestros/alertas.py` (`registrar_tipo_de_alerta`, `registrar_enlace_de_alerta`); `core/inicio.py`
  (`registrar_seccion_de_inicio`).

## Límites

- Crea modelos: `OrdenCompra` y `DetalleOrdenCompra` (`AlertaCompras` la crea CMP-04 junto con `ReclamoProveedor`, su FK). Los campos técnicos
  `Pedido.aviso_vencimiento_dado` y `Pedido.recordatorio_validez_para` ya existen desde CMP-02a: no hay migración para ellos → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0003_ordenes.py` (o el número que siga); una de `core` con `generacion_orden_compra`, `aprobacion_orden_compra`,
  `rechazo_orden_compra`.
- Permitido fuera de la app: `inventario/servicios/stock.py` (**solo** `sumar_transito` y `restar_transito`, tal cual docs/api/stock.md, con sus
  pruebas en `inventario/tests/test_transito.py`); `core/models.py` (acciones) y su migración; `core/procesos.py` (**solo el comentario** de la tabla de
  órdenes: filas 60, 61 y 62); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: recepción (CMP-04), pago (CMP-05).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** y el derivado R026 (estado de recepción de la línea). — pruebas: `test_modelos.py` (amplía).
2. **Tránsito en inventario.** — pruebas: `inventario/tests/test_transito.py`.
3. **CMP-GNR-ODC** (con la cotización elegible: vigente, con validez, del proveedor activo). — pruebas: `test_cmp_gnr_odc.py`.
4. **CMP-APR-ODC** (aprobar suma tránsito; rechazar vuelve el pedido a «con cotizaciones»); impedimento `orden_de_compra_aprobada` y precondición
   c de la baja del proveedor. — pruebas: `test_cmp_apr_odc.py`, `test_ordenes_concurrencia.py` (las cinco: dos generaciones del mismo
   pedido, generar contra cancelar, dos aprobaciones del mismo insumo y destino, aprobar contra la baja del proveedor y aprobar contra la baja del
   invernadero; la tabla de «Pruebas» de `ordenes_de_compra.md` es la fuente).
5. **Pasos diarios 60, 61, 62** (idempotentes, con `ResumenDePaso`). — pruebas: `test_pasos_diarios_compras.py` (correr dos veces el mismo día no
   repite avisos ni cancelaciones).
6. **CMP-CNS-ODC**, las secciones de inicio y las pantallas. — pruebas: `test_cmp_cns_odc.py`, `test_ordenes_vistas.py`.

Si el tiempo apremia, lo último que se recorta es: la sección de inicio del Gerente (se anota como disparador; la lista de órdenes ya lo cubre).

## Hecho cuando

- Del pedido sale una orden con líneas de dos proveedores; el Gerente la aprueba y el tránsito del insumo sube en ese invernadero; rechazada, el
  pedido vuelve a admitir otra orden.
- Los pasos 60 a 62 corren solos, son idempotentes y aparecen en el resumen del proceso diario.
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

Son 31 pasos. Si tenés poco tiempo, hacé los que no dicen «lo cubre una prueba» y el paso 29 (navegador real). El flujo entero ya lo corre `compras/tests/test_recorrido_ordenes.py`.

**Antes de empezar**

- Con `main` ya integrado en la rama, aplicá las migraciones: `python manage.py migrate` (`compras` 0003 crea las tablas de la orden; `core` 0036 solo cambia los `choices` de la auditoría). Tu `.env` necesita `DJANGO_DEBUG=1` (desde USR-09a). Terminal con el entorno virtual activo: `.venv\Scripts\Activate.ps1`, `python manage.py runserver` y entrá a `http://localhost:8000`.
- Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`): salen en la terminal del `runserver`. Los enlaces del portal del proveedor también.
- Cuentas (las contraseñas son las que ya usás; no se escriben acá): un **Gerente**, **Ana** (Agrónoma a cargo de «Invernadero Norte» y «Invernadero Norte 2»), **Beto** (Agrónomo a cargo de «Invernadero Sur») y un **Capataz**.
- Crear a mano, en este orden:
  1. En «Configuración operativa»: tolerancia de cobertura del pedido **10 %**.
  2. Insumos (Inventario): **Lechuga** (unidad) y **Tomate** (unidad). Habilitar la Lechuga en «Invernadero Norte» (mínimo 20, precio de referencia $ 12,50) y el Tomate en «Invernadero Norte 2» (mínimo 20, referencia $ 10,00). Habilitar la Lechuga también en «Invernadero Sur» (mínimo 10, referencia $ 11,00).
  3. Proveedores (Compras → Proveedores, como Gerente), con correo propio de cada uno: **A**, «Semillas del Sur S. A.», CUIT 30-00000013-9; **B**, «Viveros del Este S. R. L.», CUIT 30-00000026-0; **C**, «Hortalizas del Oeste S. A.», CUIT 30-00000039-2 (personas jurídicas).
  4. **Pedido P1** (como Ana, Compras → Pedidos → Nuevo pedido): Lechuga **20** (Norte) y Tomate **20** (Norte 2), a los tres proveedores, con la fecha límite de mañana. Con los enlaces de la terminal, cotizar desde una ventana privada (portal del proveedor, validez a 10 días): **A** lechuga 20 con total $ 240 (plazo 3 días) y tomate 10 con total $ 90 (plazo 4); **B** tomate 10 con total $ 100 (plazo 5); **C** lechuga 10 con total $ 130 (plazo 2).
  5. **Hacer que el pedido venza** (no hace falta esperar un día): en la terminal, `python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from compras.models import Pedido; h = timezone.localdate(); Pedido.objects.filter(pk=<N>).update(fecha_pedido=h - timedelta(days=5), fecha_limite_cotizaciones=h - timedelta(days=1))"`, con `<N>` el número de P1 (el de «P-00NN», sin ceros). Esto solo mueve las fechas del pedido de prueba.

**Camino feliz: el Agrónomo genera la orden** (CMP-GNR-ODC)

1. **Ana, Inicio.** Sección «Compras»: la tarjeta «Pedidos por resolver» dice **1** y la tabla «Pedidos que vencieron» lista P1 con «Resolver». *(lo cubre `test_el_inicio_del_agronomo_lista_los_pedidos_que_vencieron_con_resolver`)*
2. **Ana, ficha de P1** (Compras → Pedidos → P1). Arriba hay «Comparar cotizaciones y generar orden». Como **Gerente** la misma ficha **no** tiene el botón, y como **Beto** da 403. *(lo cubre el recorrido, paso 2)*
3. **Ana, «Comparar cotizaciones y generar orden».** Se ven «Por insumo» (una tabla por insumo, con las líneas del precio unitario más barato al más caro y «el más bajo» marcado; «pidió 20, se acepta desde 18») y «Por cotización» (una tarjeta por proveedor). **Nada viene elegido**; el panel «Lo que va a comprar» dice «Sin elegir» en los dos insumos y el botón «Revisar la orden» está deshabilitado.
4. **Elegir A** («Elegir esta cotización» en la tarjeta de Semillas del Sur). El panel dice Lechuga «Cubierto» y Tomate «Falta 8»; monto $ 330,00; el botón sigue deshabilitado. Es la cotización completa (las dos líneas de A).
5. **Elegir B.** Tomate «Cubierto» y el botón se habilita. Monto de la orden **$ 430,00**, 2 proveedores.
6. **Elegir también C.** Aparece el aviso «Se compra más de lo pedido de Lechuga: 10 de más. Está permitido.» (extensión 6b). Con «Quitar» en C vuelve a $ 430,00. *(lo cubren `test_ext_6b_comprar_de_mas_solo_advierte` y el recorrido)*
7. **Revisar la orden** (con observaciones «Entregar a la mañana.»). El resumen muestra: por proveedor sus líneas; «Lo comprado frente a lo pedido»; monto **$ 430,00** frente al estimado **$ 450,00**, diferencia −$ 20,00 (−4,4 %); las cotizaciones que se descartan (C); las observaciones. Todavía no se generó nada.
8. **Volver a corregir** vuelve a la elección con A y B elegidas y las observaciones escritas.
9. **Confirmar la orden.** Va a la ficha de la orden «OC-…», «Pendiente de aprobación», con el mensaje «Quedó pendiente de aprobación del Gerente». En la terminal sale **un solo correo**, a Hortalizas del Oeste (C): «Su cotización del pedido P-… no fue seleccionada», con el pedido, su fecha y su monto ($ 130,00), sin los otros proveedores. A y B no reciben nada todavía. *(lo cubre `test_post_f_cada_proveedor_descartado_recibe_un_correo_y_los_seleccionados_nada`)*
10. **Ficha de P1.** Ahora está «Cerrado» y dice «Con este pedido se generó la orden de compra OC-…» con el enlace. Escribir a mano `/compras/pedidos/<N>/generar-orden/`: vuelve a la ficha con «ya no está en cotización».

**Camino feliz: el Gerente aprueba** (CMP-APR-ODC)

11. **Gerente, Inicio.** «Órdenes por aprobar» dice 1; la tabla «Órdenes pendientes de aprobación» tiene «Revisar». En la campana hay una notificación «Orden OC-… pendiente de aprobación» con el total, la diferencia y «2 proveedores». *(lo cubre el recorrido, pasos 4 y 6)*
12. **Gerente, Compras → Órdenes.** El atajo «Por aprobar 1» filtra la orden; la fila tiene «Revisar» y «Ver». Como **Ana**, la misma lista **no** tiene «Revisar».
13. **Gerente, «Revisar y decidir».** Muestra el pedido, a Ana, las observaciones, los dos proveedores con sus líneas (insumo, destino, cantidad, total, precio unitario con la referencia, plazo), «Lo comprado frente a lo pedido» (lechuga 20 de 20, tomate 20 de 20) y el monto frente al estimado.
14. **Aprobar orden → resumen.** Dice las fechas de entrega esperadas (hoy + 3, hoy + 4 y hoy + 5 días), cómo sube la cantidad en tránsito (Lechuga 0 → 20 y Tomate 0 → 20), a quién le llega el correo y que **no registra ningún pago**. «Volver» no cambia nada (la orden sigue pendiente).
15. **Confirmar aprobación.** La ficha dice «Aprobada» y «Aprobada por …». En Inventario → Existencias, la cantidad en tránsito de Lechuga en Norte y de Tomate en Norte 2 es **20**. En la terminal salen **dos correos**: a Semillas del Sur con sus 2 líneas, el invernadero con su dirección y las fechas de entrega; a Viveros del Este con su 1 línea. Ninguno nombra al otro proveedor. *(lo cubren `test_post_h_cada_proveedor_recibe_un_correo_con_solo_sus_lineas` y `test_post_f_el_transito_suma_las_lineas_de_distintos_proveedores_que_cubren_un_mismo_detalle`)*
16. **Avisos.** Ana tiene en la campana «Orden OC-… aprobada» con el total y las fechas. El Gerente **no** recibe aviso de su propia acción. *(lo cubre `test_post_c_se_notifica_al_agronomo_la_aprobacion_y_no_al_gerente_que_la_resolvio`)*
17. **Auditoría** (como Gerente): «Aprobación de orden de compra» con los detalles y el cambio de estado, y dos «Modificación de insumo en un invernadero» con la cantidad en tránsito antes y después. *(lo cubre `test_post_m_un_registro_por_la_orden_y_uno_por_cada_insumo_invernadero_modificado`)*
18. **La orden impide.** Como Ana, deshabilitar la Lechuga en Norte (Inventario): se rechaza con «Tiene mercadería en la orden de compra OC-… (aprobada)» y un enlace a la orden. Como Gerente, dar de baja al proveedor A (Compras → Proveedores): se rechaza «Tiene la orden de compra OC-… sin terminar». *(lo cubre el recorrido, paso 9)*
19. **Ficha del proveedor A.** La tarjeta «Órdenes de compra» lista OC-… con su estado y **$ 330,00** (solo las líneas de A). La ficha del proveedor C dice «Todavía no se le compró». Como Beto, la tarjeta de A **no** muestra esa orden.

**Rechazo, errores y estados**

20. **Segundo pedido P2** (como Ana): Lechuga 20 en Norte, solo a A; A cotiza 20 con total $ 200 (plazo 2). Hacerlo vencer con el comando del paso 5. Ana genera la orden de P2 (elige A, revisa, confirma).
21. **Gerente rechaza P2 sin motivo.** En «Revisar y decidir» apretar «Rechazar orden» con el motivo vacío: el error «Contá por qué se rechaza la orden.» sale bajo el campo y nada cambia.
22. **Con motivo** («No hay presupuesto este mes.»): el resumen dice el motivo, que la cotización pasa a «descartada», a quién se avisa y que **la cantidad en tránsito no cambia**. «Volver a corregir» conserva el motivo. «Confirmar rechazo»: la orden queda «Rechazada» con el motivo; el correo a Semillas del Sur dice que su cotización no fue seleccionada **sin el motivo**; Ana ve en su Inicio «Órdenes rechazadas». La cantidad en tránsito de Lechuga en Norte sigue en **20** (solo las de P1). *(lo cubre `test_post_k_cada_proveedor_de_la_orden_recibe_el_aviso_de_que_no_fue_seleccionada`)*
23. **Una orden ya resuelta.** Con la ficha de P2 abierta, escribir a mano `/compras/ordenes/<id de P2>/resolver/`: vuelve a la ficha con «ya no está pendiente: está rechazada, resuelta por …». *(lo cubre `test_ext_1a1_y_8a_una_orden_ya_resuelta_informa_la_decision_y_vuelve_a_la_ficha`)*
24. **Cotización vencida.** Pedido **P3** (Tomate 20 en Norte 2, solo a B; B cotiza 20 con total $ 190) y hacerlo vencer. Luego, en la terminal, `python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from compras.models import Cotizacion; Cotizacion.objects.filter(pedido_id=<N de P3>).update(fecha_validez_cotizacion=timezone.localdate() - timedelta(days=1))"`. Ana abre «Comparar cotizaciones…»: la cotización de B dice «Validez vencida», **no tiene botón «Elegir»**, el tomate dice «Ofertas insuficientes» y aparece «el pedido no podrá generar una orden» con «Cancelar pedido». *(lo cubre `test_ext_4b_y_4c_una_cotizacion_no_elegible_se_muestra_marcada_y_sin_boton`)*
25. **Orden con cotización vencida** (opcional, si tenés tiempo): con A y B elegidas en una orden pendiente, mover a mano la validez de B a ayer (mismo comando, con el pedido de esa orden). El Gerente abre «Revisar y decidir»: no hay botón «Aprobar orden», el aviso rojo dice «La cotización de Viveros del Este S. R. L. venció el …» y el motivo del rechazo viene propuesto (editable). *(lo cubre `test_p1_con_una_cotizacion_vencida_se_propone_el_motivo_del_rechazo_y_no_se_ofrece_aprobar`)*

**Pasos diarios 60 a 62**

26. `python manage.py proceso_diario --listar` muestra «60 · pedidos_vencidos», «61 · recordatorio_de_validez» y «62 · pedidos_sin_cotizacion_elegible». *(lo cubre `test_d56_listar_muestra_los_pasos_60_a_62`)*
27. **Pedido P4** (Tomate 20 en Norte 2, a B; sin que nadie cotice) y hacerlo vencer. `python manage.py proceso_diario --solo pedidos_vencidos`: P4 queda «Cancelado» («Nadie cotizó»), Ana recibe un aviso y la salida cuenta al menos 1 «resueltos». (Si en tu base hay otros pedidos vencidos sin avisar, como P3, la línea también los cuenta y Ana recibe su aviso de vencimiento.) **Correrlo de nuevo** el mismo día: «procesados 0 · creados 0 · resueltos 0» y ningún aviso nuevo.
28. **Pedido P5** (Tomate 20 en Norte 2, a B; B cotiza 20 con total $ 190 y **validez hasta mañana**, la misma fecha que la fecha límite) y hacerlo vencer con el comando del paso 5. `python manage.py proceso_diario --solo pedidos_vencidos` avisa «Venció la fecha límite del pedido P-…; hay 1 cotización para revisar» con «1 línea, alcanza la cantidad mínima». `--solo recordatorio_de_validez` avisa «Mañana vence la cotización de … si querés elegirla, generá la orden hoy» (una sola vez). Por último, `python manage.py proceso_diario --fecha <pasado mañana, AAAA-MM-DD> --solo pedidos_sin_cotizacion_elegible` cancela P5 («Sin cotizaciones elegibles») con ese día como fecha de cierre.

**Roles, alcance y navegador**

29. **Navegador real.** Abrí una **ventana privada**, entrá como Ana y **generá una orden hasta el final** (elegir, revisar, confirmar); en **otra ventana privada**, entrá como Gerente y **aprobá** una orden y **rechazá** otra hasta el final. Después volvé a abrir cada ficha. Tiene que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. *(el cliente de Django comprueba que el formulario exige el token, pero no ve el `Origin` ni el JavaScript)*
30. **Roles.** El **Capataz** da 403 en `/compras/ordenes/`; **Beto** ve la lista vacía y 403 en `/compras/ordenes/<id>/`; el **Gerente** da 403 en `/compras/pedidos/<N>/generar-orden/`; **Ana** da 403 en `/compras/ordenes/<id>/resolver/`. Ningún botón o enlace de las pantallas lleva a un 403. *(lo cubre el recorrido, paso 6)*
31. **Opcionales: sin JavaScript y en un celular.** Con JavaScript desactivado, «Generar» y «Revisar y decidir» siguen funcionando (son formularios comunes con un botón por acción). En el ancho de un celular, las tablas se desplazan sin romper la página.

## Cierre

**Qué se hizo** (en el orden de los pasos).

1. **Modelos** `OrdenCompra` y `DetalleOrdenCompra` (`compras` 0003; R026, el proveedor y el monto derivados; estados, restricciones y el alcance `en_alcance_de`). **`AlertaCompras` no se creó:** la crea CMP-04 junto con `ReclamoProveedor` (su FK).
2. **Tránsito:** `sumar_transito` y `restar_transito` en `inventario/servicios/stock.py` (docs/api/stock.md).
3. **CMP-GNR-ODC:** `pedidos_resolubles`, `comparacion`, `resumir_orden`, `generar_orden` y `cobertura_de_la_eleccion` (`compras/servicios/ordenes.py`) y el correo de descarte.
4. **CMP-APR-ODC:** `ordenes_por_aprobar`, `detalle_para_resolver`, `resumir_aprobacion`, `aprobar_orden`, `resumir_rechazo`, `rechazar_orden` y `motivo_propuesto`; los impedimentos `orden_de_compra_aprobada` (del insumo; con enlace a la ficha) y `orden_no_terminada` (del proveedor); la parte «orden pendiente de aprobación» de la extensión 4c; el contador de pendientes del Gerente; las tres acciones de auditoría en `core` (migración 0036, solo `choices`).
5. **Pasos diarios 60, 61 y 62** (`compras/procesos.py`, registrados en `ComprasConfig.ready()`) y `cancelar_pedido_automaticamente(pedido, causa, hoy=…, aviso=…)`.
6. **CMP-CNS-ODC** (`consultar_ordenes`, `ficha_de_orden`), las pantallas «Órdenes» (lista, ficha, «Comparar cotizaciones y generar orden» y «Revisar y decidir», cada una con su resumen), las secciones del inicio del Agrónomo y del Gerente, el botón y el aviso de la ficha del pedido, y la tarjeta de órdenes de la ficha del proveedor.

**Pruebas** (con `main` ya integrado, USR-11 y USR-09a incluidos; hace falta `DJANGO_DEBUG=1`). `python manage.py test compras inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` (el comando de «Hecho cuando», después de recrear la base de pruebas y sus clones): **2705 pruebas, OK**; con `contabilidad` y sin `--parallel`: 2726, OK. `python manage.py test compras --keepdb --tag concurrencia`: **24 pruebas, OK**. `makemigrations --check`: sin cambios. Archivos nuevos: `test_cmp_gnr_odc.py` (68), `test_cmp_apr_odc.py` (53), `test_cmp_cns_odc.py` (33), `test_pasos_diarios_compras.py` (41), `test_ordenes_concurrencia.py` (10), `test_ordenes_vistas.py` (65), `test_recorrido_ordenes.py` (1) e `inventario/tests/test_transito.py` (16); amplían `test_modelos.py` (+14 pruebas del modelo de la orden), `test_registrantes_de_pedidos.py`, `test_cmp_baj_prv.py` y `test_cmp_rlz_ped.py`.

**Decisiones.** No creé ninguna. Propongo **una**, a validar (**D-100**: `main` llega a D-99; si otro PR se mergea antes, se renumera el segundo), con las interpretaciones de esta tarea: lo que fija el paso 61 («vence mañana» = `fecha_validez == hoy + 1` y solo la primera cotización elegible), que aprobar y rechazar no bloquean la cuenta del Gerente, las cinco pruebas de concurrencia que son invariantes y no carreras, y las dos extensiones opcionales de `cancelar_pedido_automaticamente`.

**Pantallas: lo que se corrigió del prototipo** (D-61).

- `c_gen` elegía **líneas sueltas**, una casilla por línea; el caso de uso y la regla 14 de 8.16 piden elegir la **cotización completa**: cada tarjeta y cada fila de la tabla de un insumo tiene un botón «Elegir esta cotización» / «Quitar» que agrega la cotización con todas sus líneas.
- `c_gen` tenía un selector «Por insumo / Por cotización»; el caso de uso (paso 4) pide **las dos vistas**: se muestran las dos en la misma pantalla. Se quitó «Elegir el precio más bajo de cada insumo» (con cotizaciones completas elegir lo más barato de cada insumo no está definido): se resalta «el más bajo» en cada tabla.
- `c_gen` generaba la orden con un solo clic: se agregaron el **resumen del paso 9** (monto frente al estimado, lo que se descarta, los excesos) y la confirmación, con «Volver a corregir» (10a).
- `c_apr` aprobaba con un clic: se agregó el **resumen del paso 6** (entregas esperadas, tránsito por insumo, «no registra ningún pago») y, para el rechazo, el resumen de la extensión 5a.3; cuando la orden no se puede aprobar (4a, 4b y P1) **no se ofrece «Aprobar orden»** (D-30) en lugar de un botón deshabilitado, y el motivo propuesto de P1 se carga en el campo del rechazo.
- Estados que faltaban: lista vacía con y sin filtros, pedido sin cotizaciones elegibles («el pedido no podrá generar una orden» con «Cancelar pedido»), orden ya resuelta (se informa la decisión y se vuelve a la ficha), error del motivo bajo el campo.
- Íconos: `scale` no existe en el conjunto del sistema; se usa `sliders`. Los botones llevan texto solo para lectores de pantalla que nombra el proveedor o la orden; todo funciona sin JavaScript (formularios comunes).
- Se muestran solo los bloques que existen: la ficha de la orden **no** tiene todavía recepciones, pagos ni reclamos (CMP-04 a CMP-06), y el inicio del Gerente solo «Órdenes por aprobar».

**Lo que difiere de la documentación.**

- *Ya resuelto por el estudiante (se corrige en su fuente, M3):* `AlertaCompras` no es de esta tarea; las notificaciones van dentro del `atomic()` y los correos en `on_commit`; la tarea lista cinco pruebas de concurrencia; y los campos técnicos `aviso_vencimiento_dado` y `recordatorio_validez_para` son de `Pedido` (no de `Cotizacion`) y ya existían desde CMP-02a.
- *Para `docs/temas_abiertos.md`:* (a) «aprobar contra la baja del proveedor» y «contra la baja del invernadero» son invariantes, no carreras: una orden pendiente ya impide las dos bajas (H20 y H22); lo que sí es una carrera es generar contra la baja del proveedor. (b) Las postcondiciones g y h piden dos registros de auditoría al generar; se hace **uno** (D-36: una acción, un registro) con el pedido, las cotizaciones, la orden y los detalles. (c) «Mañana vence la cotización» no dice si la fecha de validez es el último día válido; se tomó `fecha_validez == hoy + 1` y se recuerda solo la **primera** elegible (la de validez más próxima). (d) «Órdenes rechazadas» del inicio del Agrónomo: sin documento, se tomó el criterio del prototipo (últimos 7 días). (e) `cancelar_pedido_automaticamente` aceptó dos parámetros opcionales (`hoy` y `aviso`) para que `--fecha` simule la fecha de cierre y el paso 62 use el texto de D-87. (f) Los textos de los correos de descarte y de aprobación y de las notificaciones de la orden se redactaron acá (los documentos fijan su contenido, no sus palabras). (g) El Contador (USR-11) consulta las órdenes en solo lectura desde «Compras» → «Órdenes»; sus pagos son de CMP-05.

**Informe de verificación** (docs/patrones/verificacion_a_mano.md).

*Verifiqué:*

- El **recorrido** `test_recorrido_ordenes.py` (un solo flujo: Ana compara, elige, revisa y genera; el Gerente aprueba; tránsito 20 y 20; correos por proveedor; deshabilitar el insumo y dar de baja al proveedor impedidos; rechazo con motivo; pasos 60 a 62 con `--fecha`; roles y alcance): **OK**.
- Los **comandos de «Hecho cuando»** (con `main` integrado y `DJANGO_DEBUG=1`): 2705 y 24 pruebas, **OK**; `makemigrations --check`: sin cambios.
- **Migraciones:** `sqlmigrate compras 0003` crea `compras_ordencompra` y `compras_detalleordencompra` con sus restricciones y claves; no borra ni reescribe nada. `sqlmigrate core 0036` es un `no-op` (solo `choices`). Se aplicaron en la base de pruebas (que se recreó una vez con tu permiso).
- **Experimentos de bloqueo:** quitar el bloqueo de proveedores en `generar_orden` hace fallar las dos pruebas de «generar contra la baja del proveedor»; quitar el del pedido hace fallar «cancelar mientras se genera»; quitar a la vez las cuatro capas que protegen el tránsito (invernadero, existencia y proveedores en `aprobar_orden`, y la existencia en `sumar_transito`) hace fallar «dos aprobaciones del mismo insumo» (10 en vez de 30). Los archivos quedaron restaurados.

*Lo cubre una prueba:* la lista con el nombre de la prueba va en cada paso de la «Verificación a mano» y, para todo lo demás, en el encabezado de cada archivo de pruebas (las reglas, extensiones y postcondiciones llevan el nombre `test_regla_…`, `test_ext_…`, `test_post_…`).

*No pude verificar:*

- **Navegador real, JavaScript desactivado, celular y aspecto** (no abro navegador, D-96): paso 29 y 31.
- **Envío real de correo** (las pruebas usan el backend simulado): paso 9, 15 y 22 con el correo en modo consola o con tu SMTP.
- **Despliegue en Render y Neon:** que `migrate` aplique `compras` 0003 y la de `core`, y que las pantallas abran en producción.
- **Lo que queda del Contador:** su entrada «Pagos a proveedores» y las marcas de pago pendiente (CMP-05).
- **Que tu `.env` tenga `DJANGO_DEBUG=1`** (USR-09a): sin esa variable `DEBUG` queda apagado y ni las pruebas ni el `runserver` arrancan con la clave de desarrollo.
- **Criterio de producto:** si la pantalla de elegir cotizaciones «se siente bien» (por ejemplo, el panel de cobertura y los dos botones por cotización).

## Cierre de documentación (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md` (cerrá «orden aprobada» de «Cuando existan los pedidos de `compras`»), la tabla de pasos de docs/core (60 a 62).
