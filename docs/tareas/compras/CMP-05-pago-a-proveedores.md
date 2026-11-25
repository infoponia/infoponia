# CMP-05 · Pago a proveedores

Estado: hecha (25/11/2026; revisión a mano pendiente) | App: compras | Rama: feature/cmp-05-pago-a-proveedores | Ronda: Compras 1

Depende de: **CMP-04**, **USR-11** (rol Contador) y **CON-02**. Si alguna no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Cuando una orden quedó recibida (o cerrada con faltante) para un proveedor, el **responsable contable** ve ese pago pendiente,
lo **registra** (fecha y medio; el modelo no tiene comprobante) y se genera el **asiento** (Proveedores contra Caja o Banco). La cuenta Proveedores de esa orden queda
en cero.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-REG-PAG | Registrar Pago a Proveedor | docs/casos_de_uso/compras/pagos.md | — |
| CMP-BAJ-PRV (precondición d) | Pago pendiente impide la baja del proveedor | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |

## Leer

- Casos de uso: `pagos.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`Pago`), docs/modelo/contabilidad.md.
- Decisiones: D-91 (la del pago), D-89 (monto = suma del valor final), D-87 (menú «Pagos a proveedores»), D-84 a D-86, USR-11 (rol Contador), D-44.
- API: docs/api/asientos.md (`registrar_asiento`, `ejercicio_para`, `puede_registrar_asientos`), docs/api/notificaciones.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md.
- Pantallas: `tabPag` (pestaña «Pagos» de Compras), `VIEWS.c_pag`, `panelCon` y `panelGer` (pagos pendientes). El medio va sin
  preselección (H23; el prototipo ya lo corrige: sin elegir, «Elija el medio de pago.»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-04; `contabilidad/servicios/asientos.py`, `contabilidad/apps.py` (el menú «Contabilidad»); `core/acceso.py` (cómo se
  verifica el permiso del responsable contable).

## Límites

- Crea modelos: `Pago` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0005_pagos.py`; `contabilidad/0007_tipo_pago` (solo `choices`); una de `core` con `registro_pago_proveedor` (`core/0044_acciones_de_pagos`).
- Permitido fuera de la app: `core/models.py` (acción) y su migración; `contabilidad/models.py` (el tipo `pago` de `OrigenDocumento`, D-91 punto 1) y su migración (`contabilidad/0007_tipo_pago`); `compras/apps.py` registra la entrada de menú «Pagos a proveedores» y el enlace
  de origen `Pago`; al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: corrección de recepción después del pago (CMP-06 la impide); pagos parciales (no existen: un pago por orden y proveedor).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo** `Pago` (único por orden y proveedor). — pruebas: `test_modelos.py` (amplía).
2. **`pagos_pendientes()`** y **`avisar_si_quedo_para_pagar`** (lo llaman la recepción y el cierre con faltante de CMP-04). — pruebas:
   `test_pagos_pendientes.py`.
3. **CMP-REG-PAG** con el asiento; precondición d de la baja del proveedor. — pruebas: `test_cmp_reg_pag.py`, `test_pagos_concurrencia.py` (dos
   pagos a la vez de la misma orden y proveedor; pago contra cierre del ejercicio).
4. **Pantallas**, menú e inicio del Contador. — pruebas: `test_pagos_vistas.py`.

## Hecho cuando

- Recibida la orden, el Contador (o el Gerente si es el responsable contable) ve el pago pendiente, lo registra y la cuenta Proveedores de esa orden
  da cero en el libro.
- Nadie sin permiso contable registra pagos; un segundo pago se rechaza.
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

Son 24 pasos. Si tenés poco tiempo, hacé los que no dicen «lo cubre una prueba» y el paso 22 (navegador real). El flujo entero ya lo corre `compras/tests/test_recorrido_pagos.py`; la concurrencia (dos pagos a la vez del mismo proveedor, pago contra recepción, pago contra el cierre del ejercicio, el orden de bloqueo) **no se prueba a mano**: la cubre `compras/tests/test_pagos_concurrencia.py`.

**Antes de empezar**

- Con `main` integrado en la rama, aplicá las migraciones: `python manage.py migrate` (`compras` 0005 crea la tabla `compras_pago`; `contabilidad` 0007 y `core` 0044 solo cambian `choices`, no tocan datos). Tu `.env` necesita `DJANGO_DEBUG=1`. Terminal con el entorno virtual activo: `.venv\Scripts\Activate.ps1`, `python manage.py runserver` y entrá a `http://localhost:8000`.
- Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`): salen en la terminal del `runserver`.
- Cuentas (las contraseñas son las que ya usás; no se escriben acá): un **Gerente**, **Ana** (Agrónoma a cargo de «Invernadero Norte» y «Invernadero Norte 2»), **Beto** (Agrónomo de «Invernadero Sur»), un **Vendedor** y un **Contador** (el Gerente lo da de alta en «Usuarios y seguridad» con el rol Contador; uno solo activo). Si ya hiciste la revisión de CMP-04, reutilizá su escenario.
- **Crear a mano la orden recibida** (la misma de la «Verificación a mano» de CMP-04, «Antes de empezar», ítems 1 a 5): insumos Fertilizante (kg, controla vencimiento), Maceta y Tomate; proveedores **A** «Semillas del Sur S. A.» (CUIT 30-00000013-9) y **B** «Viveros del Este S. R. L.» (CUIT 30-00000026-0), cada uno con un correo propio; pedido de Ana con Fertilizante **10**, Maceta **20** y Tomate **8**; cotizaciones de A (Fertilizante $ 100,00 y Maceta $ 200,00) y de B (Tomate $ 80,00); orden generada por Ana y **aprobada** por el Gerente. La llamamos **OC**.
- **Recibir lo de A** (como Ana, Compras → Por recibir → A en Norte): Fertilizante **4** con vencimiento dentro de 3 meses y Maceta **20**; confirmar. Después, ficha de la orden → «Cerrar con faltante»: tildar el Fertilizante, motivo «El proveedor no repone.», confirmar. Lo de B (Tomate) **todavía no se recibe**.
- Contabilidad: no hace falta ningún paso manual (el primer ejercicio se abre solo con el primer asiento).
- Con estos datos, A queda para pagar **$ 240,00** (Fertilizante 4 × $ 10,00 = $ 40,00 y Maceta $ 200,00) y B todavía no.

**El aviso y la bandeja** (CMP-REG-PAG, pasos 1 y 2; H23)

1. **Contador, campana.** Hay una notificación **«Proveedor para pagar»**: «Semillas del Sur S. A. · OC-… : todo lo suyo quedó recibido o cerrado. Monto a pagar: $240.00.». El Gerente (con el Contador activo) y Ana **no** reciben nada. *(lo cubre `test_regla_aviso_al_quedar_el_proveedor_listo_lo_recibe_el_contador` y `test_regla_aviso_el_cierre_con_faltante_que_deja_listo_al_proveedor_avisa`)*
2. **Contador, Inicio.** Una sección **«Pagos a proveedores pendientes»** con una tarjeta «Proveedores para pagar: 1 · $ 240,00 en total» y una tabla con A, la orden, «Listo desde» (hoy), el monto y «Pagar». *(lo cubre `test_la_seccion_del_inicio_la_ve_el_contador_con_un_boton_para_pagar`)*
3. **Menú.** Como Contador y como Gerente, **«Pagos a proveedores»** aparece justo después de «Contabilidad». Ana y el Vendedor no la tienen. *(lo cubre `test_d87_la_entrada_del_menu_es_del_contador_y_del_gerente_y_va_despues_de_contabilidad`)*
4. **Contador, «Pagos a proveedores».** La bandeja trae solo A (B no figura: tiene todo por recibir): orden, «Listo desde» hoy, **2** líneas, **$ 240,00**, botón «Registrar pago». Abajo, «Pagos registrados»: «Todavía no se registró ningún pago». *(lo cubre `test_paso_2_el_contador_ve_el_pago_pendiente_con_su_monto_y_el_boton_para_registrarlo`)*
5. **Ficha de la orden y lista de órdenes** (Contador). En la ficha, la sección **«Pagos»**: A «Pendiente de pago» con **$ 240,00** y «Registrar pago»; B «Todavía no está para pagar». En Compras → Órdenes, la fila de OC tiene la marca **«Pago pendiente»** y el atajo **«Con pago pendiente 1»** deja solo esa orden. *(lo cubren `test_regla_7_de_cmp_cns_odc_la_ficha_muestra_el_pago_pendiente_el_pagado_y_el_que_no_esta_listo` y `test_regla_3_la_lista_marca_las_ordenes_con_pago_pendiente_y_ofrece_el_atajo`)*

**Registrar el pago** (pasos 3 a 10 y extensiones 5a, 5b y 8a)

6. **Contador, «Registrar pago» de A.** Muestra «Qué se paga»: Fertilizante (pedida 10 kg, recibida 4, total $ 100,00, unitario $ 10,00, a pagar **$ 40,00**, con «Cerrada con faltante: El proveedor no repone. Lo que faltó no se paga.») y Maceta (20 de 20, a pagar $ 200,00); abajo **«Monto a pagar $ 240,00»**. En «Cómo se paga» hay cuatro medios (Efectivo, Transferencia, Tarjeta de débito, Tarjeta de crédito) **ninguno elegido**, la fecha de hoy y **no hay campo de comprobante**. *(lo cubre `test_paso_4_el_formulario_muestra_el_detalle_el_medio_sin_preseleccion_y_la_fecha_de_hoy`)*
7. **Sin medio.** Sin elegir nada, «Ver resumen»: vuelve al formulario con **«Elegí el medio de pago.»** junto al medio; no se registra nada. *(lo cubre `test_ext_5a_sin_elegir_el_medio_se_pide_y_no_se_registra_nada`)*
8. **Fecha de mañana.** Escribí la fecha de mañana (el calendario ya no deja pasar de hoy; si lo escribís a mano) y elegí Transferencia: «Ver resumen» vuelve con «La fecha … no admite un asiento: posterior a la fecha de hoy». *(lo cubre `test_ext_5b_una_fecha_futura_vuelve_al_formulario_con_el_motivo`; la fecha anterior al primer ejercicio y la de un ejercicio cerrado, `test_ext_5b_…` en `test_cmp_reg_pag.py`)*
9. **Resumen.** Con **Transferencia** y la fecha de hoy, «Ver resumen»: monto $ 240,00, medio «Transferencia», fecha de hoy, **«Debe Proveedores $240.00 · Haber Banco c/c $240.00»**, el ejercicio donde cae, el correo al proveedor y el aviso «El pago no se anula…». Todavía no se registró nada: «Pagos a proveedores» sigue mostrando a A. *(lo cubre `test_paso_6_el_resumen_dice_el_monto_el_medio_y_el_asiento_sin_registrar_nada`)*
10. **«Cambiar el medio o la fecha».** Vuelve al formulario con Transferencia ya tildada y la fecha. *(lo cubre `test_el_boton_cambiar_vuelve_al_formulario_con_lo_elegido`)*
11. **«Confirmar pago».** Vuelve a «Pagos a proveedores» con el aviso verde **«Registramos el pago PAG-… de $240.00 a Semillas del Sur S. A. Asiento N.º … del libro de gestión.»**; A ya **no** figura entre los pendientes y «Pagos registrados» lo lista (fecha, PAG, proveedor, orden, Transferencia, $ 240,00). El Inicio ya no muestra a A. *(lo cubre `test_paso_7_a_10_confirmar_registra_el_pago_y_vuelve_a_la_bandeja_con_el_aviso_del_asiento`)*
12. **Libro de gestión** (Contabilidad). El asiento del pago: **Debe Proveedores $ 240,00 / Haber Banco c/c $ 240,00**, con la fecha de hoy, y su origen enlaza a la ficha de la orden. En la vista por cuenta de **Proveedores**, el Haber de la recepción de A ($ 240,00) y el Debe del pago dejan **cero** para A. *(lo cubren `test_post_b_…` y `test_d89_punto_4_…` de `test_valorizacion.py`)*
13. **Correo.** En la terminal del `runserver`, «Pago registrado · OC-…» para A con el monto $ 240.00, el medio Transferencia, la fecha y la orden; no menciona a B. *(lo cubre `test_post_d_el_proveedor_recibe_un_correo_con_el_monto_el_medio_la_fecha_y_la_orden`; el envío real, no)*
14. **Auditoría** (Gerente). Un registro **«Registro de pago a proveedor»** hecho por el Contador, con el pago, la orden y A como afectados y, en los datos, el asiento, el medio, la fecha y el monto; el asiento y sus movimientos tienen sus propios registros. La notificación no se audita. *(lo cubre `test_post_e_se_audita_el_pago_con_el_actor_los_afectados_y_el_asiento`)*
15. **Un segundo pago.** Volvé con la flecha del navegador al formulario de A y confirmá otra vez (o escribí a mano `/compras/pagos/orden/<id de OC>/proveedor/<id de A>/`): te lleva a la ficha de la orden con el aviso «Ya se registró el pago PAG-…», que figura como «Pagado». No hay un segundo pago ni un segundo asiento. *(lo cubre `test_ext_8a_un_par_ya_pagado_lleva_a_la_ficha_de_la_orden_con_el_aviso`)*

**Por estado y por rol**

16. **B para pagar.** Como Ana, Compras → Por recibir → B en Norte 2: Tomate **8**, confirmar. La orden pasa a «Recibida con faltante». El Contador recibe otro aviso «Proveedor para pagar» ($ 80.00) y la bandeja trae a B con **$ 80,00**. *(lo cubren las pruebas de los pasos 1 y 4)*
17. **Gerente con el Contador activo: solo lectura.** «Pagos a proveedores» le muestra a B con el cartel «Los pagos los registra el Contador» y **sin** botón; en la ficha de la orden, «Pendiente de pago» sin botón; en el Inicio **no** hay sección de pagos. Si escribís a mano la dirección del formulario de B, da **403**. *(lo cubren `test_ext_1a_el_gerente_con_contador_activo_ve_la_bandeja_sin_botones` y `…_no_abre_el_formulario`)*
18. **Baja del proveedor bloqueada.** Gerente, Compras → Proveedores → B → «Dar de baja»: la ventana dice **«No se puede dar de baja a Viveros del Este S. R. L.»** con «Tiene un pago pendiente de la orden de compra OC-… ($80.00)», cómo resolverlo y un enlace **«Ver la orden»**; no ofrece confirmar. La ficha de B muestra, en «Órdenes de compra», la columna **«Pago»: «Pendiente de pago»**. *(lo cubren `test_pre_d_la_ventana_de_baja_del_proveedor_explica_el_pago_pendiente_y_enlaza_la_orden` y `test_regla_4_de_cmp_cns_prv_la_ficha_del_proveedor_muestra_el_pago_de_cada_orden`)*
19. **Sin Contador activo, el Gerente paga.** El Gerente da de baja al Contador (Usuarios y seguridad). Ahora el Gerente ve en el Inicio la sección de pagos y la bandeja con «Registrar pago». Paga a B en **Efectivo** (resumen: **«Haber Caja $80.00»**), confirma. En el libro, el asiento es Debe Proveedores / Haber **Caja** $ 80,00; en «Auditoría» el autor es el Gerente. Con A y B pagados, Proveedores da cero. *(lo cubren `test_ext_1a_sin_contador_activo_el_gerente_registra_y_queda_como_autor_en_la_auditoria` y el recorrido)*
20. **Ficha de la orden y del proveedor, ya pagados.** La sección «Pagos» muestra a A y a B «Pagado» con su PAG, fecha y medio (sin botones). En la ficha de A, la columna «Pago» dice «Pagado», la fecha, «Transferencia» y $ 240,00. *(lo cubren las pruebas del paso 5 y `test_regla_4_de_cmp_cns_prv_…`)*
21. **Roles sin acceso.** Ana, Beto, el Vendedor y un Capataz **no** ven «Pagos a proveedores» en el menú; por la dirección escrita a mano (`/compras/pagos/`) da **403**, y sin sesión te lleva al inicio de sesión. Una orden o un proveedor que no existen dan 404. *(lo cubren `test_pre_a_los_demas_roles_no_entran` y `test_un_proveedor_ajeno_o_una_orden_inexistente_dan_404`)*

**Lo que solo ve un navegador**

22. **Navegador real.** Con tu sesión de Contador (o de Gerente sin Contador) abierta en el navegador, hacé un pago de punta a punta con un proveedor que quede para pagar (por ejemplo, repetí el escenario con otra orden): elegí el medio, **«Ver resumen»**, **«Confirmar pago»** y **enviálo hasta el final**; después volvé a abrir «Pagos a proveedores». Tiene que mostrar el aviso verde y el pago registrado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate también que el campo de fecha abre el calendario y no deja elegir un día posterior a hoy, y que el botón «Confirmar pago» se deshabilita y dice «Registrando…» al enviarlo (para no pagar dos veces con un doble clic).
23. **Sin JavaScript** *(opcional)*. Desactivá JavaScript y repetí el formulario: el medio se elige, «Ver resumen» y «Confirmar pago» funcionan igual (son envíos comunes).
24. **Celular** *(opcional)*. Con la ventana angosta (o en el celular), la bandeja y el formulario se leen sin desplazarse hacia los costados; las tablas pueden desplazarse dentro de su recuadro. El Contador y el Gerente usan la interfaz de escritorio (D-85 punto 6): no es una pantalla de campo.

## Cierre

**Qué se hizo** (en el orden de los pasos).

1. **Modelo** `Pago` (hereda de `OrigenDocumento`, tipo nuevo `pago`; único por `(orden, proveedor)`, monto positivo y medio válido en la base) en `compras` 0005; `contabilidad` 0007 solo suma el tipo a los `choices`.
2. **`pagos_pendientes()` y `avisar_si_quedo_para_pagar`** (`compras/servicios/pagos.py`): la consulta única de D-91 punto 2 (una consulta por tabla) y el aviso «Proveedor para pagar» al responsable contable, sin quien hizo la acción. La llaman, dentro de la transacción, `registrar_recepcion` y `cerrar_con_faltante` (`recepciones.py`).
3. **CMP-REG-PAG:** `detalle_del_pago`, `resumir_pago` y `registrar_pago` (valida sin bloquear y otra vez con la orden bloqueada; el asiento va **último**; audita `registro_pago_proveedor`; el correo sale en `on_commit`), `enlace_de_origen` del asiento, y el impedimento `pago_pendiente` de la baja del proveedor con enlace a la orden. `core`: la acción, `ACCIONES_DE_NEGOCIO`, `ETIQUETAS` y `VALORES_VISIBLES["medio_pago"]` (`core` 0044, solo `choices`).
4. **Concurrencia:** 6 pruebas (`test_pagos_concurrencia.py`).
5. **Pantallas:** «Pagos a proveedores» (bandeja y registrados), «Registrar pago» con su resumen, la entrada del menú (Contador y Gerente), la sección del Inicio del responsable contable, la sección «Pagos» y el botón «Registrar pago» de la ficha de la orden, el atajo «Con pago pendiente» y la marca de la lista, y la columna «Pago» de la ficha del proveedor.

**Pruebas** (con `main` en `cbfa01e`, COM-05b (#85) incluida, y `DJANGO_DEBUG=1`).

- `python manage.py test compras contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **1414 pruebas, OK**.
- `python manage.py test compras --keepdb --tag concurrencia`: **41 pruebas, OK**.
- Como se tocó `core/models.py`: `python manage.py test core.tests.test_aud_cns_reg core.tests.test_auditoria_produccion --keepdb --parallel`: **54 pruebas, OK**.
- **Integrada con `main` en `cbfa01e`** (COM-05b, #85): la única superposición de código fue `core/models.py` (se fusionó sin conflicto) y el número de migración de `core` (la `0043` la tomó COM-05b: la de esta tarea se regeneró como `0044`, que depende de la de COM-05b). Con todo junto: `compras contabilidad comercial` y la auditoría de `core` (3379 pruebas) y la concurrencia de `compras` y `comercial` (137), **OK**; `makemigrations --check`: sin cambios.
- `makemigrations --check --dry-run`: sin cambios.

**Decisiones.** No creé ninguna.

**Pantallas: lo que se corrigió del prototipo** (D-61).

- `c_pag` ofrecía **tres** medios («Transferencia», «Efectivo», «Tarjeta»); el caso de uso y D-91 piden cuatro: efectivo, transferencia, tarjeta de débito y tarjeta de crédito.
- `c_pag` tenía la fecha **fija en hoy** (solo lectura) y un **número de comprobante** opcional; el caso de uso (paso 5) deja elegir la fecha y el modelo **no tiene comprobante** (decisión del estudiante). Se agregó la fecha elegible (con tope en hoy) y se quitó el comprobante.
- `c_pag` registraba con un clic; el caso de uso pide el **resumen del paso 6** (monto, medio y asiento) antes de confirmar y el aviso de que el pago no se anula: se agregaron.
- `c_pag` no mostraba lo **no aceptado por daño**, ni el precio unitario ni el total por línea (paso 4): se agregaron.
- El prototipo ponía «Pagos a proveedores» como una **pestaña de Compras** y la ocultaba al Gerente con Contador activo; D-87 punto 6 pide una **entrada del menú** junto a «Contabilidad» para el Contador y el Gerente, y D-91 punto 6 que el Gerente con Contador la **vea en solo lectura**: se hizo así.
- `tabPag` suma la lista de **pagos registrados**; `panelCon` y `panelGer`, la sección «Pagos a proveedores pendientes» (el Gerente solo sin Contador activo); la ficha de la orden, la sección «Pagos» (regla 7 de CMP-CNS-ODC) y la lista de órdenes, el atajo y la marca «Pago pendiente».
- Estados que faltaban: bandeja vacía, error de negocio con lo escrito conservado (medio, fecha), par ya pagado o no listo (lleva a la ficha con el aviso) y proveedor ajeno (404). Todo funciona sin JavaScript (formularios comunes).

**Lo que difiere de la documentación.**

- *Ya resuelto por el estudiante en el control previo (se corrige en su fuente, M3):* `OrigenDocumento.Tipo.PAGO` y la migración `contabilidad/0007_tipo_pago` no estaban en «Límites»; `pagos.md` dice `alta_pago` y la tarea `registro_pago_proveedor` (se usó la segunda); «Qué resuelve» menciona un comprobante que el modelo no tiene; `pagos.md` dice que `test_valorizacion.py` «lo amplía» pero no existía (se creó).
- *Prueba de CMP-03 que se actualizó* (no se debilitó: pasa de «se ignora» a «filtra»): en `test_cmp_cns_odc.py`, `test_regla_2_un_atajo_de_otra_tarea_o_desconocido_se_ignora` ya no incluye «con pago pendiente» (lo suma esta tarea; su prueba está en `test_pagos_vistas.py`).
- *Para `docs/temas_abiertos.md`:* (a) los errores de la fecha del pago (5b) y de las cuentas (8b) los lanza `ErrorContable` (con `campo="fecha"`) y no `ErrorDeCompras`: la pantalla los muestra junto al campo; (b) el texto de 5a es «Elegí el medio de pago.» (voseo) y no «Elija…» del prototipo; (c) `LineaDePago.no_aceptada` suma los inconvenientes que no son «otro» (el caso de uso solo dice «lo no aceptado por daño»); (d) como en CMP-04, el correo no se reintenta (9a): `enviar_correo` registra la falla y el pago queda; (e) el ícono de la entrada del menú es `cart` (no hay uno de dinero en `core/templatetags/iconos.py`); (f) `detalle_del_pago` y `resumir_pago` exigen ser el responsable contable, así que el Gerente con Contador activo mira la bandeja y la ficha pero no el formulario; (g) «comprobante del pago» queda como mejora futura (columna y decisión nueva).

**Informe de verificación** (docs/patrones/verificacion_a_mano.md).

*Verifiqué:*

- El **recorrido** `test_recorrido_pagos.py` (recepción de A → aviso y Inicio del Contador → bandeja → formulario, resumen y confirmación por transferencia → asiento Debe Proveedores / Haber Banco, correo y Proveedores en cero → segundo pago rechazado → B para pagar, Gerente en solo lectura y 403 → baja de B bloqueada con enlace → sin Contador, el Gerente paga en efectivo (Caja) → baja de B posible → Agrónomo y Vendedor sin acceso; y una orden cerrada con faltante pagada por lo recibido con tarjeta de crédito): **OK**.
- Los **comandos de «Hecho cuando»**: 1414 y 41 pruebas, **OK**; auditoría de `core` (54), **OK**; `makemigrations --check`: sin cambios.
- **Migraciones:** `sqlmigrate compras 0005` crea la tabla `compras_pago` con sus restricciones y claves; no borra ni reescribe nada. `sqlmigrate contabilidad 0007` y `sqlmigrate core 0044` son `no-op` (solo `choices`). Se aplicaron en la base de pruebas.
- **Experimento de bloqueo** (se editó `pagos.py` para bloquear el ejercicio abierto **antes** que la orden, se corrió la concurrencia y se restauró; `diff` contra la copia original: sin residuos): hizo fallar exactamente `test_regla_el_ejercicio_va_ultimo_un_rival_que_lo_bloquea_antes_de_la_orden_forma_un_deadlock_con_el_pago` (0 *deadlocks* en lugar de 1); las otras cinco siguieron en verde.

*Lo cubre una prueba:* cada paso de la «Verificación a mano» nombra la suya; para todo lo demás, los encabezados de los archivos de pruebas (las reglas, extensiones y postcondiciones llevan el nombre `test_regla_…`, `test_ext_…`, `test_post_…`).

*No pude verificar:*

- **Navegador real, JavaScript desactivado, celular y aspecto** (no abro navegador, D-96): pasos 22, 23 y 24.
- **Envío real de correo** (las pruebas usan el backend simulado): paso 13 con el correo en modo consola o con tu SMTP.
- **Que tu base de desarrollo tenga las migraciones aplicadas:** no toqué tu base; corré `python manage.py migrate` antes del paso 1 (`compras` 0005, `contabilidad` 0007 y `core` 0044).
- **Despliegue en Render y Neon:** que `migrate` aplique las tres y que las pantallas abran en producción.
- **Pago con la fecha en un ejercicio «en cierre» o cerrado desde la pantalla:** necesita preparar un ejercicio vencido a mano; lo cubren `test_ext_5b_…` y la concurrencia (D-102).
- **Criterio de producto:** si el formulario y el resumen «se sienten bien» para quien paga.

## Cierre de documentación (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md`, `docs/revisiones_pendientes.md`, `docs/temas_abiertos.md` y `docs/pendientes_prototipo.md` (nuevo), `docs/casos_de_uso/compras/pagos.md` y esta tarea. Aplicado el 25/11/2026 (estado, README, ronda, historial, revisiones, disparadores, temas abiertos, `pendientes_prototipo.md` nuevo y `pagos.md`).
