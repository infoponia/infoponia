# CMP-04 · Recepción de mercadería y cierre con faltante

Estado: hecha (PR #__, 24/11/2026; revisión a mano pendiente) | App: compras (y funciones en inventario) | Rama: feature/cmp-04-recepcion-y-cierre-con-faltante | Ronda: Compras 1

Depende de: **CMP-03** y **CON-02** (núcleo contable: la recepción genera asiento). Si CON-02 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo **recibe** la mercadería de una orden aprobada (total o parcial, por proveedor y por invernadero), con sus lotes y
vencimientos y los inconvenientes que encuentre (si hay, queda un **reclamo sin emitir** y una alerta para el Gerente); el stock pasa de tránsito a existencia y se registra el **asiento** (Insumos en Stock contra
Proveedores). Si un proveedor no va a entregar lo que falta, el Agrónomo **cierra la línea con faltante**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-REG-RCP | Registrar Recepción de Mercadería | docs/casos_de_uso/compras/recepcion.md | Sobreentrega bloqueada (P3); sin tipo «retraso» (P4); el aviso «quedó para pagar» lo agrega CMP-05 |
| CMP-CRR-FLT | Cerrar Detalle con Faltante | docs/casos_de_uso/compras/recepcion.md | Sin asiento (D-90) |

## Leer

- Casos de uso: `recepcion.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`Recepcion`, `DetalleRecepcion`, `InconvenienteRecepcion`, `DetalleRecepcionMovimiento`, `ReclamoProveedor`;
  `DetalleOrdenCompra.fecha_cierre_faltante`), docs/modelo/contabilidad.md (`OrigenDocumento`).
- Decisiones: D-89 (`valor_recibido` y el asiento como diferencia de valor acumulado), D-90 (la de la recepción), D-84 a D-86 (contabilidad), D-87,
  D-36, D-44.
- API: docs/api/stock.md («Escritura de compras»: `registrar_ingreso_por_recepcion`, `restar_transito`, `lotes_de_ingreso`), docs/api/asientos.md
  (`registrar_asiento`, `ejercicio_para`).
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md, docs/patrones/bloqueos.md (orden de compras, `EjercicioContable` al final).
- Pantallas: `tabRec` (pendientes de recibir), `VIEWS.c_rcp`, `VIEWS.c_flt`, la ficha de la orden («Recepciones»), `panelAgr` («Por recibir»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-03; `inventario/servicios/stock.py` y `inventario/models.py` (`LoteInsumo`, `MovimientoInsumo`, sus tipos);
  `inventario/unidades.py` (`validar_cantidad`); `contabilidad/servicios/asientos.py` y `contabilidad/models.py`.

## Límites

- Crea modelos: `Recepcion`, `DetalleRecepcion`, `InconvenienteRecepcion`, `DetalleRecepcionMovimiento`, `ReclamoProveedor` (se crea
  abierto y sin emitir; emitirlo y cerrarlo es CMP-06) y `AlertaCompras` (D-87 punto 5; su FK es el reclamo) → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0004_recepciones.py`; `contabilidad/migrations/0006_tipo_recepcion.py` (solo `choices`: el tipo `recepcion`);
  una de `core` con `recepcion_mercaderia` y `cierre_con_faltante` (solo `choices`; salió como `0041` porque COM-05a1 tomó la `0040`).
- Permitido fuera de la app: `inventario/servicios/stock.py` (**solo** `registrar_ingreso_por_recepcion` y `lotes_de_ingreso`, tal cual
  docs/api/stock.md, con pruebas en `inventario/tests/test_ingreso_por_recepcion.py`); `core/models.py` (acciones) y su migración; `contabilidad/models.py` (**solo** `OrigenDocumento.Tipo.RECEPCION`) y su migración;
  `compras/apps.py` registra el enlace de origen `Recepcion` en `contabilidad.extensiones.registrar_enlace_de_origen`; al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: pago (CMP-05); corregir una recepción y emitir o cerrar el reclamo (CMP-06).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** (la recepción hereda `OrigenDocumento`). — pruebas: `test_modelos.py` (amplía).
2. **Ingreso por recepción en inventario** (crea lotes, mueve tránsito a existencia, un movimiento por lote). — pruebas:
   `inventario/tests/test_ingreso_por_recepcion.py`.
3. **CMP-REG-RCP** con el asiento (valor = diferencia del valor acumulado de la línea, D-89), y con inconvenientes: el reclamo sin emitir y la
   alerta al Gerente (tipo registrado en `maestros.alertas`). — pruebas: `test_cmp_reg_rcp.py` (incluye el redondeo:
   tres recepciones parciales suman exactamente el total de la línea).
4. **CMP-CRR-FLT** (baja el tránsito del faltante; sin asiento). — pruebas: `test_cmp_crr_flt.py`.
5. **Concurrencia:** (1) dos recepciones de la misma línea; (2) recepción contra cierre con faltante; (3) recepción contra `cerrar_ejercicio`, que **no interfieren**
   (`cerrar_ejercicio` bloquea solo el ejercicio «en cierre» y la recepción asienta siempre en el abierto: es una prueba de no interferencia, no del orden de bloqueos);
   (4) recepción contra `abrir_ejercicio_si_corresponde`; (5) recepción contra un consumo del mismo insumo; (6) dos recepciones de órdenes distintas (números de
   asiento correlativos); (7) el ejercicio va último. La 4, la 6 y la 7 fallan si se invierte el orden de bloqueos. — pruebas: `test_recepciones_concurrencia.py`.
6. **Pantallas** y el enlace desde el asiento al documento. — pruebas: `test_recepciones_vistas.py`.

## Hecho cuando

- Una orden se recibe en dos partes y en dos invernaderos; el stock de cada uno sube, el tránsito baja, cada recepción tiene su asiento y la suma de
  los asientos es igual al total de las líneas recibidas completas.
- Una sobreentrega se rechaza; un faltante cerrado baja el tránsito y deja la línea «cerrada con faltante».
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

Son 44 pasos. Si tenés poco tiempo, hacé los que no dicen «lo cubre una prueba», el paso 40 (navegador real) y el 44 (libro de gestión). El flujo entero ya lo corre `compras/tests/test_recorrido_recepcion.py`; la concurrencia (dos recepciones a la vez, recibir contra cerrar, etc.) **no se prueba a mano**: la cubre `compras/tests/test_recepciones_concurrencia.py`.

**Antes de empezar**

- Con `main` integrado en la rama, aplicá las migraciones: `python manage.py migrate` (`compras` 0004 crea las seis tablas de la recepción; `contabilidad` 0006 y `core` 0041 solo cambian `choices`, no tocan datos). Tu `.env` necesita `DJANGO_DEBUG=1`. Terminal con el entorno virtual activo: `.venv\Scripts\Activate.ps1`, `python manage.py runserver` y entrá a `http://localhost:8000`.
- Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`): salen en la terminal del `runserver`, también los enlaces del portal del proveedor.
- Cuentas (las contraseñas son las que ya usás; no se escriben acá): un **Gerente**, **Ana** (Agrónoma a cargo de «Invernadero Norte» y «Invernadero Norte 2»), **Beto** (Agrónomo a cargo de «Invernadero Sur») y un **Contador** (si no hay Contador activo, el Gerente hace lo suyo). Un **Capataz** para el paso de acceso.
- Contabilidad: no hace falta ningún paso manual (el primer ejercicio se abre solo con el primer asiento). Si querés que el ejercicio empiece antes, `python manage.py poner_en_marcha_contabilidad --fecha-inicio 2026-01-01` **antes** del primer paso.
- Crear a mano, en este orden:
  1. Insumos (Inventario): **Fertilizante** (unidad **kg**, **controla vencimiento**), **Maceta** (unidad **unidad**, no vence) y **Tomate** (unidad **unidad**, no vence). Habilitar Fertilizante y Maceta en «Invernadero Norte» (Fertilizante: mínimo **10**, precio de referencia $ 10,00; Maceta: mínimo 0, referencia $ 10,00) y Tomate en «Invernadero Norte 2» (mínimo 0, referencia $ 10,00). Con el mínimo 10 y sin stock, el Fertilizante genera la alerta «bajo el mínimo»: es lo que se va a resolver al recibir.
  2. Proveedores (Compras → Proveedores, como Gerente), con un correo propio cada uno: **A**, «Semillas del Sur S. A.», CUIT 30-00000013-9, y **B**, «Viveros del Este S. R. L.», CUIT 30-00000026-0 (personas jurídicas).
  3. **Pedido P1** (como Ana, Compras → Pedidos → Nuevo pedido): Fertilizante **10** (Norte), Maceta **20** (Norte) y Tomate **8** (Norte 2), a los dos proveedores, con la fecha límite de mañana. Con los enlaces de la terminal, cotizar desde una ventana privada (portal del proveedor, validez a 10 días): **A** fertilizante 10 con total **$ 100,00** (plazo 3 días) y maceta 20 con total **$ 200,00** (plazo 5); **B** tomate 8 con total **$ 80,00** (plazo 2).
  4. **Hacer que el pedido venza** (no hace falta esperar un día): `python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from compras.models import Pedido; h = timezone.localdate(); Pedido.objects.filter(pk=<N>).update(fecha_pedido=h - timedelta(days=5), fecha_limite_cotizaciones=h - timedelta(days=1))"`, con `<N>` el número de P1 (el de «P-00NN», sin ceros).
  5. Como Ana, «Comparar cotizaciones y generar orden»: elegir **A** y **B** (cotizaciones completas), revisar y confirmar. Como **Gerente**, «Revisar y decidir» → aprobar. La orden (la llamamos **OC**) queda «Aprobada» y el tránsito es Fertilizante 10, Maceta 20 y Tomate 8.

**Mercadería por recibir** (CMP-REG-RCP, pasos 2 a 4)

1. **Ana, Inicio.** En «Compras» hay una tarjeta **«Por recibir»** con **2** y una tabla «Por recibir» con las dos entregas: B en Norte 2 (entrega en 2 días) primero y A en Norte (3 días) después, cada una con «Recibir». *(lo cubre `test_panelAgr_el_inicio_del_agronomo_muestra_la_mercaderia_por_recibir`)*
2. **Ana, Compras → «Por recibir».** La pestaña nueva está entre «Órdenes» y «Proveedores». La lista trae las mismas dos entregas con orden, proveedor, invernadero, líneas pendientes (2 y 1), entrega esperada y «En fecha». *(lo cubre `test_paso_2_el_agronomo_ve_sus_entregas_con_el_boton_de_registrar`)*
3. **Hacer que una línea llegue tarde.** `python manage.py shell -c "from datetime import timedelta; from django.utils import timezone; from compras.models import DetalleOrdenCompra; DetalleOrdenCompra.objects.filter(orden_id=<N de OC>, detalle_cotizacion__detalle_pedido__insumo_invernadero__insumo__nombre_insumo='Maceta').update(fecha_entrega_esperada=timezone.localdate() - timedelta(days=3))"`. Recargar «Por recibir»: la entrega de A dice **«3 días de atraso»** en rojo y pasa a ir primera. *(lo cubre `test_paso_2_una_linea_atrasada_marca_los_dias_de_atraso_y_la_entrega_mas_proxima`)*
4. **Gerente.** «Por recibir» y la ficha de la orden le muestran las mismas entregas (el Gerente recibe en cualquier invernadero). **Beto** ve «No hay mercadería pendiente de recibir» y, por la dirección `/compras/ordenes/<id de OC>/`, un 403. *(lo cubre `test_ext_1a_el_gerente_ve_todo_y_un_agronomo_sin_destinos_el_estado_vacio`)*
5. **Ficha de la orden.** Como Ana y como Gerente, arriba a la derecha, **«Registrar recepción»** y **«Cerrar con faltante»**; como Contador, ninguno de los dos (solo consulta). En las líneas, «Recibida» en 0 y «Falta» igual a lo pedido. *(lo cubre `test_regla_8_las_acciones_de_la_ficha_segun_quien_mira`)*

**Camino feliz: recepción parcial con un inconveniente** (pasos 5 a 11, extensiones 5a y 7f)

6. **Ana, «Registrar recepción» de A en Norte** (desde «Por recibir»). Muestra Fertilizante («pedida 10 kg · ya recibida 0 · falta 10 kg») y Maceta; el Fertilizante tiene un campo **de fecha** de vencimiento y la Maceta dice **«No vence»**. El Tomate no aparece (es de B en otro invernadero). *(lo cubre `test_paso_4_el_formulario_muestra_las_lineas_con_lo_pedido_y_lo_que_falta`)*
7. **Cargar:** Fertilizante, cantidad **4**, vencimiento dentro de 3 meses; «Agregar un inconveniente» → tipo **Mercadería dañada**, cantidad afectada **2**, «Qué pasó»: «Dos bolsas rotas». Observaciones: «Llegó por la tarde.» No cargar nada en Maceta. «Agregar un inconveniente» vuelve a dibujar el formulario con una fila más y conserva lo escrito. *(lo cubre `test_paso_5_agregar_otro_lote_suma_una_fila_y_agregar_inconveniente_suma_otra`)*
8. **«Ver resumen».** Dice: Fertilizante ingresa **4 kg**, «Lote nuevo de 4 kg · vence el …», stock **0 → 4**, en tránsito **10 → 6**, «Sigue pendiente»; la orden quedará **Parcialmente recibida**; asiento Debe Insumos en Stock / Haber Proveedores por **$ 40,00**; «se genera un reclamo sin emitir»; en «Alertas que se resuelven», la de **«Fertilizante bajo el mínimo»** (libre 4 + tránsito 6 = 10, igual al mínimo). **No se creó nada todavía.** *(lo cubre `test_paso_7_ver_resumen_muestra_lo_que_pasara_y_no_registra_nada`)*
9. **«Cambiar algún dato»** vuelve al formulario con todo lo que escribiste. Volver a «Ver resumen».
10. **«Confirmar recepción».** Vuelve a la ficha de la orden con «Registramos la recepción RCP-… La orden quedó parcialmente recibida» y un segundo aviso, **«Quedó pendiente Fertilizante (faltan 6)… cerrala con faltante»** (extensión 11a). En la terminal sale **un correo** a Semillas del Sur con la orden, la fecha, el invernadero, «Fertilizante: 4.000 kg recibidas», el inconveniente «Mercadería dañada: 2.000 kg · Dos bolsas rotas» y lo pendiente (Fertilizante y Maceta). No menciona a Viveros del Este. *(lo cubren `test_paso_9_confirmar_registra_la_recepcion_y_lleva_a_la_ficha`, `test_ext_11a_si_quedaron_lineas_pendientes_se_ofrece_cerrarlas_con_faltante` y `test_post_h_el_proveedor_recibe_un_correo_con_lo_recibido_lo_no_aceptado_y_lo_pendiente`)*
11. **Alerta «bajo el mínimo».** Como Ana, «Alertas»: la alerta del Fertilizante («bajo el mínimo») pasó a **resuelta** (con libre 4 + tránsito 6 = 10 ≥ 10). *(lo cubre `test_post_g_recibir_resuelve_la_alerta_de_bajo_el_minimo_si_el_insumo_deja_de_estarlo`)*
12. **Ficha de la orden.** «Recibida 4» y «Falta 6» en el Fertilizante («Pendiente»); la orden «Parcialmente recibida»; la sección **«Recepciones»** nueva: RCP-…, fecha de hoy, Semillas del Sur S. A. · Norte, «la registró» con el nombre de Ana, «Lote …: 4 · vence el …», la insignia **«Mercadería dañada»** con «2 · Dos bolsas rotas», «Reclamo REC-… sin emitir» y las observaciones. *(lo cubre `test_regla_5_la_ficha_muestra_lo_recibido_y_lo_que_falta_de_cada_linea`)*
13. **Inventario.** Como Ana, Inventario → Existencias: Fertilizante en Norte con stock 4 kg (un lote nuevo con su vencimiento) y 6 en camino. (El movimiento «Ingreso por recepción» de 4 y su vínculo con la línea de la recepción no se ven en pantalla.) *(lo cubre `test_flujo_principal_registra_la_recepcion_completa_de_un_proveedor_en_un_invernadero`)*

**Lo que ve el Gerente** (postcondiciones j y k)

14. **Gerente, «Alertas».** Hay una alerta nueva **«Recepción con inconvenientes»** (advertencia, activa, sin leer) que dice «RCP-… de Semillas del Sur S. A. en Invernadero Norte: reclamo REC-… sin emitir. 1 inconveniente (1 mercadería dañada)». Al abrirla, el enlace lleva a la **ficha de la orden**. *(lo cubren `test_post_k_la_alerta_para_el_gerente_es_activa_y_no_leida_e_identifica_la_recepcion` y el recorrido, paso 3)*
15. **Gerente, Compras → Órdenes.** La fila de la orden tiene la insignia **«Reclamo sin emitir»**; el atajo nuevo **«Con reclamo sin emitir»** (con su contador) deja solo esa orden y **«Por recibir»** trae la orden mientras haya líneas pendientes. *(lo cubren `test_post_k_un_inconveniente_genera_el_reclamo_sin_emitir_y_aparece_en_la_ficha_y_en_el_atajo` y `test_regla_2_el_atajo_por_recibir_y_las_marcas_de_la_lista`)*
16. **Emitir el reclamo no se puede todavía** (es CMP-06): no hay botón. El reclamo queda «abierto» y sin emitir.

**Resto de la línea y el asiento exacto** (D-89 punto 4)

17. **Ana, «Registrar recepción» de A en Norte** otra vez: ahora el Fertilizante dice «ya recibida 4 · falta 6». Cargar **6 en dos lotes**: 3 con vencimiento dentro de 3 meses y, con «Agregar otro lote», 3 con vencimiento dentro de 6 meses; «Ver resumen» muestra **dos lotes nuevos** de 3 kg con su fecha cada uno. Confirmar. La línea queda **Completa**; el stock del Fertilizante es **10** y el tránsito **0**; la orden sigue «Parcialmente recibida» (falta la Maceta y el Tomate). *(lo cubre `test_post_d_la_linea_pasa_a_completo_cuando_lo_recibido_acumulado_iguala_lo_pedido`)*
18. **Como Contador (o Gerente), Contabilidad → libro de gestión.** Dos asientos automáticos de la recepción: el primero Insumos en Stock **$ 40,00** / Proveedores **$ 40,00** y el segundo **$ 60,00**; **suman exactamente los $ 100,00** del total de la línea. Cada uno se muestra como «Recepción RCP-… · OC-…» con un enlace a la ficha de la orden. *(lo cubren `test_d89_el_valor_de_dos_recepciones_de_una_linea_es_el_de_lo_acumulado` y el recorrido, pasos 4 y 8)*

**Errores de validación** (extensiones 7a a 7e, 5d y 5e)

19. **Sobreentrega** (P3). En «Registrar recepción» de B en Norte 2: Tomate cantidad **9** (se pidieron 8) → «Confirmar». Vuelve al formulario con «De Tomate faltan recibir 8 …: el excedente no se ingresa (anotalo en las observaciones)» y lo que escribiste; no se registra nada. *(lo cubre `test_ext_7a_un_error_de_negocio_vuelve_al_formulario_con_lo_escrito`)*
20. **Número ilegible.** Cantidad «abc» o «1,2,3»: «Escribí la cantidad recibida como un número, por ejemplo 12 o 12,5.» *(lo cubre `test_ext_7b_un_numero_o_una_fecha_ilegibles_se_senalan_sin_llamar_al_servicio`)*
21. **Decimales que la unidad no admite.** Tomate (unidad) cantidad **1,5**: error de cantidad inválida. *(lo cubre `test_ext_7b_una_cantidad_negativa_o_con_decimales_que_la_unidad_no_admite_se_rechaza`)*
22. **Sin ninguna línea** (dejar todo en blanco, «Ver resumen»): «La recepción tiene que incluir al menos una línea.» *(lo cubre `test_ext_7d_una_recepcion_sin_ninguna_linea_se_rechaza`)*
23. **Falta el vencimiento** (Fertilizante con cantidad y sin fecha): «Fertilizante controla el vencimiento: indicá la fecha de cada lote.» **Vencimiento de ayer:** «Lo de Fertilizante que ya está vencido no ingresa al stock: declaralo como inconveniente.» (para recibir con vencimiento de hoy sí se puede). *(lo cubren `test_regla_el_vencimiento_es_obligatorio_si_el_insumo_lo_controla_y_no_va_si_no_lo_controla` y `test_ext_5e_un_vencimiento_anterior_a_hoy_no_es_un_ingreso`)*
24. **Línea en cero.** Maceta con un inconveniente «Otro» («Llegó otro modelo») y sin cantidad recibida → «Una línea en 0 solo se registra si todo lo que llegó estaba dañado, vencido, no conforme o distinto». Cambiando el tipo a **Producto distinto al pedido** sí se registra: nada ingresa, la línea sigue pendiente, **no hay asiento** y sale un reclamo sin emitir. *(lo cubren `test_ext_7c_una_linea_en_cero_solo_se_registra_con_un_inconveniente_que_no_sea_otro` y `test_post_e_una_recepcion_en_cero_igual_pone_la_orden_parcialmente_recibida_sin_ingresar_nada`)*
25. **Inconveniente incompleto.** Tipo «Otro» sin «Qué pasó», o cantidad afectada vacía o 0 → «Un inconveniente necesita su tipo y una cantidad afectada mayor que cero; el tipo «otro» pide además contar qué pasó.» Dos inconvenientes del mismo tipo en una línea: «a lo sumo un inconveniente de cada tipo». *(lo cubren `test_ext_7e_un_inconveniente_incompleto_se_rechaza` y `test_ext_5d_una_linea_tiene_a_lo_sumo_un_inconveniente_de_cada_tipo`)*
26. **Varios lotes en la ficha.** En la sección «Recepciones» de la ficha, la recepción del paso 17 muestra **dos lotes** del Fertilizante, «Lote …: 3 · vence el …» con las dos fechas. *(lo cubre `test_post_c_cada_fecha_de_vencimiento_distinta_forma_su_lote_con_su_movimiento_y_su_vinculo`)*

27. **Destino inactivo** (extensión 4a/4a1), con la orden todavía con mercadería pendiente. Dar de baja el insumo Tomate en Norte 2 se impide mientras la orden no esté terminada (D-87 punto 5), así que para ver el estado: `python manage.py shell -c "from maestros.models import Invernadero; Invernadero.objects.filter(nombre_invernadero='Invernadero Norte 2').update(estado_invernadero='inactivo')"`. «Por recibir»: la entrega de B dice **«Destino inactivo»** y **sin botón**; la ficha «Registrar recepción» de esa entrega no se puede completar. Volverlo a `'activo'` con el mismo comando. *(lo cubren `test_ext_4a1_una_entrega_con_todo_el_destino_inactivo_no_ofrece_el_boton` y `test_ext_4a_una_linea_de_un_destino_inactivo_se_lista_sin_permitir_recibirla`)*

**Cierre con faltante** (CMP-CRR-FLT)

28. **Ana, ficha de la orden → «Cerrar con faltante».** Lista las líneas pendientes (Maceta y Tomate) con su casilla, lo pedido, lo recibido, lo que falta y **un motivo propio por línea**; avisa «no se puede volver a abrir». *(lo cubre `test_paso_2_la_lista_ofrece_las_lineas_pendientes_con_su_casilla_y_su_motivo`)*
29. **Sin tildar nada** («Ver resumen»): «Elegí al menos una línea para cerrar con faltante.» **Tildar la Maceta sin motivo:** «Contá por qué no va a llegar lo que falta de cada línea.» y la línea queda marcada. *(lo cubre `test_ext_4a_sin_motivo_o_sin_lineas_vuelve_a_la_lista_con_el_error`)*
30. **Maceta con motivo «No las fabrican más.» → «Ver resumen».** Muestra faltante **20**, tránsito **20 → 0**, «La orden quedará: Parcialmente recibida», que el proveedor A **queda listo para pagar** (sus dos líneas quedan completa y cerrada y se le recibió algo; la bandeja y el aviso de pago son de CMP-05) y que el cierre «no se deshace». *(lo cubre `test_paso_5_el_resumen_dice_lo_que_cambia_y_no_cierra_nada`)*
31. **«Confirmar cierre».** Vuelve a la ficha: Maceta **«Cerrado con faltante»** con su motivo; el tránsito de la Maceta en 0; **sin ningún asiento nuevo** en el libro de gestión (la deuda nació al recibir). El correo a Semillas del Sur dice que no se espera el faltante de la Maceta. *(lo cubren `test_paso_7_confirmar_cierra_la_linea_y_la_ficha_la_muestra_con_su_motivo`, `test_regla_sin_asiento_cerrar_no_mueve_dinero_ni_toca_el_stock_ni_las_reservas` y `test_post_f_cada_proveedor_recibe_un_correo_que_avisa_que_no_se_espera_el_resto_de_sus_lineas_cerradas`)*
32. **Cerrar desde la recepción** (extensión 2a). Recibir una parte de B (Tomate 3) y, en el aviso «Quedó pendiente…», tocar «cerrala con faltante»: la lista trae **solo el Tomate**. Cerrarlo: la orden pasa a **«Recibida con faltante»** (todas completas o cerradas y alguna cerrada). *(lo cubren `test_ext_2a_desde_una_recepcion_solo_se_ofrecen_sus_lineas_pendientes` y `test_post_c_la_orden_queda_recibida_con_faltante_si_todas_las_lineas_estan_completas_o_cerradas`)*
33. **Una línea ya cerrada no se vuelve a cerrar.** Con la ficha abierta en otra pestaña antes del cierre, en la que sigue el botón, repetir el cierre de la Maceta: vuelve a la lista con «Alguna de las líneas ya no está pendiente…». El tránsito no cambia. *(lo cubre `test_ext_7a_una_linea_que_ya_no_esta_pendiente_no_se_cierra_y_no_se_cierra_ninguna`)*
34. **Bajo el mínimo por un cierre** (no se repite a mano: pide otra orden aprobada con un insumo de mínimo mayor que su stock). Al cerrar una línea, el tránsito deja de contar y puede aparecer la alerta «bajo el mínimo». *(lo cubre `test_post_d_cerrar_puede_activar_la_alerta_de_insumo_bajo_el_minimo`)*

**Cuando registra el Gerente** (extensión 1a)

35. **Gerente registra una recepción** (otra orden, o la que quede): la ficha dice «la registró **el Gerente**» y, en «Auditoría», el registro «Recepción de mercadería» tiene al Gerente como quien actuó. *(lo cubren `test_regla_la_ficha_dice_quien_registro_la_recepcion_el_gerente_cuando_no_hay_agronomo` y `test_ext_1a_el_gerente_registra_la_recepcion_sin_agronomo_y_queda_en_la_auditoria`)*

**Estados**

36. **Orden recibida.** Con todas las líneas completas o cerradas, «Registrar recepción» y «Cerrar con faltante» desaparecen de la ficha y «Por recibir» ya no la lista. *(lo cubre `test_regla_8_sin_lineas_pendientes_la_ficha_no_ofrece_recibir_ni_cerrar`)*

**Auditoría**

37. **Gerente, «Auditoría».** Registros «Recepción de mercadería» (con la recepción, sus detalles, la orden y el reclamo entre los afectados; «Estado: Aprobada → Parcialmente recibida»; lotes, movimientos, asiento y «Monto del asiento» en el detalle), una «Modificación de insumo en un invernadero» por existencia (stock y tránsito antes y después) y «Cierre de líneas con faltante» con los motivos. *(lo cubren `test_post_l_un_registro_de_auditoria_nombra_todo_lo_que_la_recepcion_creo_o_modifico` y `test_post_g_un_registro_de_cierre_con_faltante_nombra_la_orden_y_las_lineas_cerradas`)*

**Roles, alcance y navegador**

38. **Roles.** El **Capataz** da 403 en `/compras/por-recibir/`; **Beto** da 403 en `/compras/ordenes/<id>/recibir/` y en `/compras/ordenes/<id>/cerrar-con-faltante/` (sin botón en ninguna pantalla); el **Contador** ve la ficha **sin** botones y da 403 en esas dos direcciones. Ningún botón o enlace lleva a un 403. *(lo cubren `test_regla_quien_registra_otro_agronomo_es_403_y_una_orden_inexistente_404` y `test_regla_otros_roles_no_entran_y_el_contador_no_ve_la_pestana`)*
39. **Una orden inexistente.** `/compras/ordenes/999999/recibir/` da 404. *(lo cubre la misma prueba del paso 38)*
40. **Navegador real.** Abrí una **ventana privada**, entrá como Ana, **registrá una recepción hasta el final** (cargar, «Ver resumen», «Confirmar recepción») y **cerrá una línea con faltante hasta el final**; en **otra ventana privada**, entrá como Gerente y abrí la alerta. Después volvé a abrir la ficha de la orden. Tiene que mostrar el resultado esperado. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. *(el cliente de Django comprueba que el formulario exige el token, pero no ve el `Origin` ni el JavaScript)*
41. **Sin JavaScript** (opcional): desactivá JavaScript en el navegador. «Agregar otro lote», «Agregar un inconveniente», «Ver resumen» y «Confirmar» siguen funcionando (son botones de un formulario común). Con JavaScript, los desplegables de tipo de inconveniente son los del sistema; sin él, el desplegable común.
42. **Celular** (opcional): en el ancho de un celular, las tablas de «Por recibir» y de la ficha se desplazan sin romper la página y los campos de cantidad y fecha se pueden tocar bien.
43. **Correo caído** (opcional): con el correo mal configurado (por ejemplo, `EMAIL_HOST` inexistente), registrar una recepción igual funciona: la recepción queda registrada y el error del correo aparece solo en la terminal. *(lo cubre `test_ext_10a_si_el_correo_no_sale_la_recepcion_queda_registrada`)*
44. **Libro de gestión con el Contador.** Entrar como Contador: Contabilidad → libro: los asientos de las recepciones llevan «Recepción RCP-… · OC-…» en la columna de origen y, al abrir el asiento, el enlace «RCP-… · OC-…» lleva a la ficha de la orden (el Contador la ve sin botones). Los saldos: **Insumos en Stock** y **Proveedores** suben lo mismo por cada recepción; el cierre con faltante no los mueve. *(lo cubren `test_enlace_el_asiento_de_la_recepcion_lleva_a_la_ficha_de_la_orden_en_el_libro_de_gestion` y el recorrido, paso 8)*

## Cierre

**Qué se hizo** (en el orden de los pasos).

1. **Modelos** `Recepcion` (hereda de `OrigenDocumento`, tipo nuevo `recepcion`), `DetalleRecepcion`, `DetalleRecepcionMovimiento`, `InconvenienteRecepcion`, `ReclamoProveedor` y `AlertaCompras` (`compras` 0004; `contabilidad` 0006 solo suma el tipo a los `choices`).
2. **Ingreso en `inventario`:** `registrar_ingreso_por_recepcion` (cubre primero el faltante sin lote, un lote por parte, un movimiento por lote, resta el tránsito y reevalúa las alertas) y `lotes_de_ingreso` (`inventario/servicios/stock.py`).
3. **CMP-REG-RCP** (`compras/servicios/recepciones.py`): `entregas_pendientes`, `lineas_a_recibir`, `resumir_recepcion` y `registrar_recepcion` (valida dos veces: sin bloquear y con todo bloqueado; el asiento va **último**), el correo al proveedor, el reclamo sin emitir, la alerta del Gerente (`compras_recepcion_con_inconvenientes`) y los registrantes de `ready()` (tipo de alerta, enlace de la alerta y enlace asiento → ficha de la orden).
4. **CMP-CRR-FLT:** `lineas_pendientes_de_cierre`, `resumir_cierre` y `cerrar_con_faltante` (sin asiento; el correo R1).
5. **Concurrencia:** 11 pruebas (`test_recepciones_concurrencia.py`).
6. **Pantallas:** «Por recibir» (pestaña nueva), «Registrar recepción» y «Cerrar con faltante» (cada una con su resumen), la sección «Recepciones» y las acciones de la ficha de la orden, los atajos «Por recibir» y «Con reclamo sin emitir» y la marca de reclamo en la lista, y la tarjeta «Por recibir» del inicio del Agrónomo. Las acciones `recepcion_mercaderia` y `cierre_con_faltante` en `core` (migración 0041, solo `choices`; en `ACCIONES_DE_NEGOCIO`, `ETIQUETAS` y `VALORES_VISIBLES`).

**Pruebas** (con `main` en `b65c023`, CON-03a incluida, y `DJANGO_DEBUG=1`).

- `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **2444 pruebas, OK**.
- `python manage.py test compras --keepdb --tag concurrencia`: **35 pruebas, OK**.
- Como se tocó `core/models.py`: `python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **1987 pruebas, OK**.
- `makemigrations --check --dry-run`: sin cambios.
- **Integrada con `main` en `2aa95be`** (COM-05a1, #81): la única superposición fue `core/models.py` (se fusionó sin conflicto) y el número de migración de `core` (la `0040` la tomó COM-05a1: la de esta tarea se regeneró como `0041`, que depende de la de COM-05a1). Con todo junto: `compras inventario contabilidad comercial` (4131), `core maestros produccion` (2976), `compras --tag concurrencia` (35) y `comercial --tag concurrencia` (73): **OK**.

**Decisiones.** No creé ninguna.

**Pantallas: lo que se corrigió del prototipo** (D-61).

- `c_rcp` permitía **un solo lote y un solo inconveniente por línea**; el caso de uso pide una cantidad por cada fecha de vencimiento distinta (paso 5) y un inconveniente de cada tipo (extensión 5d): cada línea tiene «Agregar otro lote» y «Agregar un inconveniente» (un botón que vuelve a dibujar el formulario, sin JavaScript).
- `c_rcp` limitaba la cantidad afectada de un inconveniente a lo recibido y exigía recibir algo para declararlo; el caso de uso dice que lo dañado **no cuenta como recibido** y que una línea puede quedar en 0 con un inconveniente que no sea «otro» (7c): la cantidad afectada no tiene tope y la línea en 0 se acepta.
- `c_rcp` registraba con un clic: se agregó el **resumen del paso 7** (lo que ingresa, lotes, stock y tránsito antes y después, estado de la línea y de la orden, monto del asiento, alertas que se resuelven, el reclamo sin emitir y que no se registra ningún pago) y «Cambiar algún dato».
- `c_rcp` marcaba vencido «hoy o antes»; el caso de uso y la regla del lote («vence desde el día siguiente») dicen **anterior a hoy**: un lote que vence hoy ingresa.
- `c_flt` pedía **un único motivo** para todas las líneas; el caso de uso (paso 4) pide **el motivo de cada línea**. Se agregó el **resumen del paso 5** y el aviso «no se deshace».
- `c_odc` (la ficha) ahora muestra lo recibido real, la sección «Recepciones» con los lotes y sus vencimientos, quién la registró y los inconvenientes; los botones «Registrar recepción» y «Cerrar con faltante» solo aparecen si quien mira puede (D-30).
- `tabRec` ganó el estado «Destino inactivo» sin botón (extensión 4a1) y `panelAgr`, la tarjeta «Por recibir» con su KPI. La lista de órdenes suma los atajos «Por recibir» y «Con reclamo sin emitir» y la marca de reclamo.
- Estados que faltaban: orden sin mercadería pendiente (vacío), error de negocio con lo escrito conservado, línea con el destino inactivo, números y fechas ilegibles señalados en la línea. Todo funciona sin JavaScript (formularios comunes).

**Lo que difiere de la documentación.**

- *Ya resuelto por el estudiante (se corrige en su fuente, M3):* `AlertaCompras`, el tipo `recepcion` de `OrigenDocumento` y la migración 0006 de `contabilidad` no estaban en «Límites»; el paso 5 de la tarea tenía tres pruebas de concurrencia y ahora son siete (ver el informe); `lotes_de_ingreso` la escribe CMP-04 (la API decía CMP-06).
- *Pruebas de CMP-03 que se actualizaron* (no se debilitaron: pasan de «se ignora» a «filtra»): en `test_cmp_cns_odc.py`, `test_regla_2_un_atajo_de_otra_tarea_o_desconocido_se_ignora` ya no incluye «por recibir» ni «con reclamo sin emitir» (los suma esta tarea; se agregaron sus dos pruebas) y `test_regla_8_sin_accion_si_la_orden_ya_se_resolvio_o_quien_mira_no_es_el_gerente` espera `{"recibir", "cerrar"}` para el Gerente en una orden aprobada.
- *Para `docs/temas_abiertos.md`:* (a) el resumen del cierre calcula si el proveedor «queda para pagar» con la regla de la postcondición e (todas sus líneas completas o cerradas y algo recibido) **sin** la bandeja ni el aviso, que son de CMP-05 (D-91): CMP-05 tiene que usar la misma regla. (b) El resumen de la recepción calcula las alertas de «bajo el mínimo» que se resolverán desde `compras` (con `stock.existencias`) porque `reevaluar_alertas_del_insumo` no tiene un modo lectura y agregarlo tocaba `inventario` fuera de «Límites». (c) La auditoría de la recepción no lista las alertas resueltas por el stock (`registrar_ingreso_por_recepcion` no devuelve la reevaluación). (d) La extensión 9a («lo que falta cambió») no distingue «cambió» de «te pasaste»: el servicio no recibe lo que la pantalla vio y devuelve `linea_no_pendiente` o `supera_lo_pendiente` con lo que falta ahora. (e) Códigos de error que el caso de uso no nombra: `linea_ajena`, `linea_repetida`, `vencimiento_no_aplica`, `inconveniente_repetido`, `orden_no_recibible`, `cantidad_invalida`, `sin_lineas`, `motivo_obligatorio` y `destino_inactivo`. (f) `cerrar_con_faltante` acepta líneas de varias órdenes en una sola operación (el paso 2 las presenta agrupadas por orden). (g) El caso de uso pedía «recepción contra baja del destino» en los requisitos especiales: no hay prueba de concurrencia propia porque la baja del insumo y del invernadero ya la impide una orden no terminada (D-87 punto 5); el bloqueo del invernadero de la recepción no lo detecta ninguna prueba (ver el experimento). (h) Los archivos de pruebas `test_valorizacion.py` y `test_stock_compras.py` del caso de uso no se crearon: la valorización está en `test_cmp_reg_rcp.py` y las funciones de `inventario` en `test_ingreso_por_recepcion.py`, como dice la tarea. (i) El correo al proveedor de la recepción y del cierre (postcondición h y R1) lo piden el caso de uso y no la lista de la tarea: se agregaron las plantillas `recepcion.txt` y `cierre_faltante.txt`.

**Informe de verificación** (docs/patrones/verificacion_a_mano.md).

*Verifiqué:*

- El **recorrido** `test_recorrido_recepcion.py` (orden aprobada → recepción parcial con inconveniente: lote, stock de tránsito a existencia, asiento, reclamo sin emitir, alerta al Gerente, correo → resto de la línea con el asiento exacto → cierre con faltante sin asiento → sobreentrega rechazada → recepción de B y orden «recibida con faltante» → libro de gestión con el enlace a la ficha → auditoría): **OK**.
- Los **comandos de «Hecho cuando»**: 2444 y 35 pruebas, **OK**; `core` y `maestros` (1987), **OK**; `makemigrations --check`: sin cambios.
- **Migraciones:** `sqlmigrate compras 0004` crea las seis tablas con sus restricciones y claves; no borra ni reescribe nada. `sqlmigrate contabilidad 0006` y `sqlmigrate core 0041` son `no-op` (solo `choices`). Se aplicaron en la base de pruebas.
- **Experimentos de bloqueo** (se editó `recepciones.py`, se corrió la concurrencia y se restauró; `diff` contra la copia original: sin residuos): (A) bloquear el ejercicio abierto **antes** que las filas de `compras` hace fallar exactamente `…la_apertura_del_ejercicio_no_espera_a_la_recepcion…`, `…dos_recepciones_de_ordenes_distintas_toman_numeros_de_asiento_correlativos…` y `…el_ejercicio_va_ultimo_un_rival…`; (E) quitar **todos** los bloqueos de `compras` hace fallar seis (`dos_recepciones_de_la_misma_linea`, `dos_recepciones_que_caben_juntas`, `recibir_mientras_se_cierra`, `cerrar_con_faltante_mientras_se_recibe`, `dos_cierres_de_la_misma_linea` y `el_ejercicio_va_ultimo`); (B) quitar solo el bloqueo de las líneas de la orden, o (C) solo el de la existencia y los lotes, **no** rompe ninguna de las de «misma línea»: las dos capas se respaldan (y `inventario` bloquea la existencia por su cuenta); (F) quitar solo el del invernadero no rompe ninguna. La prueba de `cerrar_ejercicio` queda fuera del experimento a propósito: no comparte ninguna fila con la recepción.

*Lo cubre una prueba:* cada paso de la «Verificación a mano» nombra la suya; para todo lo demás, los encabezados de los archivos de pruebas (las reglas, extensiones y postcondiciones llevan el nombre `test_regla_…`, `test_ext_…`, `test_post_…`).

*No pude verificar:*

- **Navegador real, JavaScript desactivado, celular y aspecto** (no abro navegador, D-96): pasos 40, 41 y 42.
- **Envío real de correo** (las pruebas usan el backend simulado): pasos 10, 31 y 43 con el correo en modo consola o con tu SMTP.
- **Que tu base de desarrollo tenga las migraciones aplicadas:** `showmigrations` marca como pendientes las de `compras` 0004, `contabilidad` 0006 y `core` 0041 (y otras anteriores): no toqué tu base; corré `python manage.py migrate` antes del paso 1.
- **Despliegue en Render y Neon:** que `migrate` aplique `compras` 0004, `contabilidad` 0006 y `core` 0041, y que las pantallas abran en producción.
- **Lo que queda de pago:** la bandeja y el aviso «quedó para pagar» (CMP-05) y emitir y cerrar el reclamo (CMP-06).
- **Criterio de producto:** si el formulario de recepción con varios lotes e inconvenientes «se siente bien» para quien recibe en el invernadero (sobre todo en el celular).

## Cierre de documentación (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md`, `docs/modelo/inventario.md` (si cambiaste algo de los tipos: no cambió nada).
