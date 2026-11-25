# CMP-06 · Corrección de recepción y reclamos al proveedor

Estado: hecha (25/11/2026; revisión a mano pendiente) | App: compras (y una función y un tipo en inventario) | Rama: feature/cmp-06-correccion-y-reclamos | Ronda: Compras 1

Depende de: **CMP-05**. Si no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Si una recepción se cargó de más, el Agrónomo la **corrige** (mientras no esté pagada y el lote tenga lo que se corrige): baja el
stock, el valor y genera el **asiento inverso**. El reclamo sin emitir que dejó la recepción (CMP-04) lo **emite** el Gerente al proveedor (sale un correo) y
luego lo **cierra**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-COR-RCP | Corregir Recepción | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |
| CMP-EMT-RCL | Emitir Reclamo a Proveedor | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |
| CMP-CRR-RCL | Cerrar Reclamo a Proveedor | docs/casos_de_uso/compras/correccion_y_reclamos.md | — |

## Leer

- Casos de uso: `correccion_y_reclamos.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`CorreccionRecepcion`, `DetalleCorreccionRecepcion`, `ReclamoProveedor` ya creado en CMP-04), docs/modelo/inventario.md (tipos de
  movimiento).
- Decisiones: D-90 (máximo corregible, tipo nuevo, vínculos), D-89 (corrección inversa), D-91 (no se corrige lo pagado), D-84 a D-86, D-44.
- API: docs/api/stock.md (`registrar_salida_por_correccion_de_recepcion`), docs/api/asientos.md, docs/api/correo.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md, docs/patrones/bloqueos.md.
- Pantallas: `VIEWS.c_cor`, `tabRcl`, `VIEWS.c_rcl`, `panelGer` («reclamos sin emitir»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-04 y CMP-05; `inventario/models.py` (`MovimientoInsumo.Tipo`), `inventario/servicios/stock.py`.

## Límites

- Crea modelos: `CorreccionRecepcion`, `DetalleCorreccionRecepcion` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0006_correcciones_y_reclamos.py`; **una de `inventario`, solo de `choices`**, con
  `salida_por_correccion_de_recepcion`; una de `core` con `correccion_recepcion`, `emision_reclamo`, `cierre_reclamo`.
- Permitido fuera de la app: `inventario/models.py` (el tipo nuevo) y su migración; `inventario/servicios/stock.py` (**solo**
  `registrar_salida_por_correccion_de_recepcion`, con pruebas en `inventario/tests/test_salida_por_correccion.py`); `core/models.py` (acciones) y su
  migración; `docs/modelo/inventario.md` (el tipo nuevo); al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: notas de crédito o devoluciones con dinero (no están en el alcance de la ronda).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** y el tipo nuevo de movimiento. — pruebas: `test_modelos.py` (amplía), `inventario/tests/test_salida_por_correccion.py`.
2. **CMP-COR-RCP** (máximo corregible = recibido − ya corregido, y no más que lo que queda en el lote; asiento inverso). — pruebas:
   `test_cmp_cor_rcp.py`, `test_correcciones_concurrencia.py` (corrección contra consumo del lote; corrección contra pago).
3. **CMP-EMT-RCL** y **CMP-CRR-RCL** (Gerente; emitir resuelve la alerta y manda el correo después del commit). — pruebas: `test_cmp_emt_rcl.py`, `test_cmp_crr_rcl.py`.
4. **Pantallas**, y completar la ficha del proveedor y de la orden (correcciones y reclamos). — pruebas: `test_reclamos_vistas.py`.

## Hecho cuando

- Una recepción se corrige: el lote baja, el valor de la línea baja, el asiento inverso cuadra y el pago pendiente se recalcula; una pagada no se
  corrige.
- El Gerente emite el reclamo con sus inconvenientes, el proveedor recibe el correo y después lo cierra.
- Con esta tarea, la ronda «Compras 1» queda completa: pruebas verdes, sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

Son 27 pasos. Si tenés poco tiempo, hacé los que no dicen «lo cubre una prueba» y el paso 25 (navegador real). El flujo entero ya lo corre `compras/tests/test_recorrido_correccion_y_reclamos.py`; la concurrencia (corrección contra pago, contra el consumo del lote, dos correcciones de la misma línea, dos emisiones del mismo reclamo y el orden de bloqueo) **no se prueba a mano**: la cubre `compras/tests/test_correcciones_concurrencia.py`.

**Antes de empezar**

- Con `main` integrado en la rama, aplicá las migraciones: `python manage.py migrate`. `compras` 0006 crea las tablas `compras_correccionrecepcion` y `compras_detallecorreccionrecepcion`; `inventario` 0004 agranda la columna del tipo de movimiento (de 30 a 40 caracteres) y reescribe su restricción, sin tocar datos; `contabilidad` 0009 y `core` 0047 solo cambian `choices`. Tu `.env` necesita `DJANGO_DEBUG=1`. Terminal con el entorno virtual activo: `.venv\Scripts\Activate.ps1`, `python manage.py runserver` y entrá a `http://localhost:8000`.
- Para ver los correos sin enviarlos, correo en modo consola (`CORREO_CONSOLA=1` en `.env`): salen en la terminal del `runserver`.
- Cuentas (las contraseñas son las que ya usás; no se escriben acá): un **Gerente**, **Ana** (Agrónoma a cargo de «Invernadero Norte» y «Invernadero Norte 2»), **Beto** (Agrónomo de «Invernadero Sur»), un **Vendedor** y un **Contador** (el Gerente lo da de alta en «Usuarios y seguridad»; uno solo activo). Si ya hiciste las revisiones de CMP-04 y CMP-05, reutilizá su escenario.
- **Crear a mano la orden** (la misma de «Verificación a mano» de CMP-04, «Antes de empezar»): insumos Fertilizante (kg, controla vencimiento), Maceta y Tomate; proveedores **A** «Semillas del Sur S. A.» (CUIT 30-00000013-9) y **B** «Viveros del Este S. R. L.» (CUIT 30-00000026-0), cada uno con un correo propio; pedido de Ana con Fertilizante **10**, Maceta **20** y Tomate **8**; cotizaciones de A (Fertilizante $ 100,00 y Maceta $ 200,00) y de B (Tomate $ 80,00); orden generada por Ana y **aprobada** por el Gerente. La llamamos **OC**.
- **Recibir lo de A** (como Ana, Compras → Por recibir → A en Norte), en **dos recepciones**:
  1. Fertilizante **4** (vencimiento dentro de 3 meses) con un inconveniente «Mercadería dañada», cantidad **2**, descripción «Cajas rotas», y Maceta **20**. Confirmar. Esto deja el reclamo **sin emitir** (la alerta del Gerente y su tarjeta del Inicio; es de CMP-04).
  2. Fertilizante **6** (vencimiento dentro de 3 meses). Confirmar. Con esto A queda recibido por completo y para pagar **$ 300,00**.
- Lo de B (Tomate) **todavía no se recibe**.

**El reclamo: emitir y cerrar** (CMP-EMT-RCL y CMP-CRR-RCL)

1. **Gerente, Inicio.** En la sección «Compras», una tarjeta **«Reclamos sin emitir: 1»** («con inconvenientes de recepción») y, abajo, la lista **«Recepciones con reclamo»** con el reclamo (REC-…), la recepción, A y el botón «Emitir». *(lo cubre `test_el_inicio_del_gerente_cuenta_los_reclamos_sin_emitir_y_los_lista`)*
2. **Gerente, Compras → Reclamos.** Aparece la pestaña **«Reclamos»** (Ana no la tiene). La lista trae el reclamo con A, la orden OC, «Mercadería dañada» y las marcas «Abierto» y «Sin emitir». El chip «Sin emitir» muestra **1**; «Emitidos abiertos» y «Cerrados» dicen «No hay reclamos con ese estado». *(lo cubren `test_la_lista_muestra_los_reclamos_…` y `test_los_filtros_separan_…`)*
3. **Ficha del reclamo.** Entrá con «Ver». Datos: proveedor A, la orden, la recepción (con su fecha) y «Norte», «Emisión: Sin emitir». Tabla de inconvenientes: Fertilizante, **Mercadería dañada**, 2 kg, «Cajas rotas». Un cartel explica que al emitir se le envía un correo al proveedor y que no se espera una devolución, con el botón **«Emitir reclamo»**. No hay «Cerrar reclamo». *(lo cubren `test_la_ficha_muestra_los_datos_y_cada_inconveniente` y `test_el_gerente_ve_emitir_…`)*
4. **Emitir.** Apretá «Emitir reclamo». Vuelve a la ficha con el aviso verde **«Emitimos el reclamo REC-…. Le enviamos un correo a Semillas del Sur S. A.»**; ahora figura «Emitido» con la fecha de hoy y tu nombre, y el botón pasó a **«Cerrar reclamo»**. En la terminal del `runserver`, el correo **«Reclamo REC-… · OC-…»** para A con la recepción, la orden y «Fertilizante: Mercadería dañada, 2 … · Cajas rotas»; no menciona a B. *(lo cubren `test_emitir_registra_manda_el_correo_y_vuelve_a_la_ficha` y `test_post_c_…`; el envío real, no)*
5. **Alerta e Inicio.** La alerta «Recepción con inconvenientes» del Gerente pasó a **resuelta** (ya no está entre las activas) y la tarjeta del Inicio dice **0 · «al día»**; la lista «Recepciones con reclamo» desapareció. *(lo cubren `test_post_b_…` y `test_el_inicio_del_gerente_…`)*
6. **Cerrar.** Apretá «Cerrar reclamo». Aviso **«Cerramos el reclamo REC-…»**, badge «Cerrado» y ya **no hay botones**. En la lista, el chip «Cerrados» lo muestra. *(lo cubren `test_cerrar_por_post_cierra_y_vuelve_a_la_ficha` y `CmpCrrRclTests`)*
7. **Auditoría** (Gerente). Dos registros: **«Emisión de reclamo a proveedor»** (con el reclamo, la recepción y A, el cambio de Gerente y fecha y la alerta resuelta) y **«Cierre de reclamo a proveedor»** (estado abierto → cerrado). *(lo cubren `test_post_d_…` y `test_post_b_…`)*

**Corregir la recepción** (CMP-COR-RCP, pasos 1 a 11)

8. **Ana, ficha de OC.** Aparece el botón **«Corregir una recepción»**. En «Recepciones» se ven RCP 1 (con la etiqueta «Reclamo REC-… emitido») y RCP 2. *(lo cubre `test_regla_8_el_boton_corregir_…`)*
9. **Formulario.** Con el botón se abre «Corregir una recepción · OC-…», con un cartel («solo se puede corregir lo que se cargó de más… mientras el proveedor no esté pagado…»). Como hay dos recepciones corregibles de A, arriba hay **dos opciones** (RCP 1 y RCP 2); elegí **RCP 2**. La tabla trae Fertilizante: recibida **6 kg**, «Se puede descontar» **6**, el lote («conserva 6 … vence el …») y un campo; y una **Observación (opcional)**. *(lo cubren `test_paso_2_el_formulario_muestra_…` y `test_paso_2_con_varias_recepciones_…`)*
10. **Errores.** (a) Escribí **7** y «Ver resumen»: vuelve con el mensaje «De Fertilizante se pueden descontar como máximo 6…» y tu 7 conservado. (b) Escribí **abc**: «Escribí un número.» junto al campo. (c) Dejá todo vacío: «La corrección tiene que incluir al menos una línea…». No se registra nada. *(lo cubren `test_ext_5a_…` y `test_ext_5b_…`)*
11. **Resumen.** Escribí **2** y la observación «Se cargó de más»; «Ver resumen». Muestra: Fertilizante se descuenta **2 kg** (Lote N: −2), recibida 6 → 4, stock **10 → 8**, tránsito **0 → 2**, estado «Pendiente de recibir»; «La orden quedará **Parcialmente recibida**»; **«Debe Proveedores / Haber Insumos en Stock por $ 20,00»**; el aviso de que el proveedor recibe un correo. **Todavía no se registró nada.** *(lo cubren `test_paso_7_el_resumen_muestra_…`)*
12. **«Volver».** Reabre el formulario con el 2 y la observación. *(lo cubre `test_la_accion_editar_vuelve_al_formulario_con_lo_escrito`)*
13. **Confirmar.** «Confirmar corrección»: vuelve a la ficha de OC con **«Registramos la corrección COR-… de la recepción RCP-…. La orden quedó parcialmente recibida.»** En la tabla del proveedor A, Fertilizante muestra recibida **8**, falta **2**, estado «Pendiente»; en «Recepciones», RCP 2 dice **«se corrigieron 2»** y la etiqueta «Corregida dd/mm/aaaa (COR-…)». *(lo cubren `test_paso_9_confirmar_registra_…` y `test_flujo_principal_…`)*
14. **Stock.** Inventario → existencias de Fertilizante en Norte: stock actual **8 kg** y en tránsito **2 kg**. El lote de RCP 2 conserva 4 de 6 y, si tu pantalla de existencias muestra los movimientos del lote, ahí figura la **«Salida por corrección de recepción»** de 2 kg. *(lo cubren `test_post_b_…` y `test_salida_por_correccion.py`)*
15. **Libro de gestión** (Contador o Gerente). Un asiento nuevo **Debe Proveedores $ 20,00 / Haber Insumos en Stock $ 20,00**, con la fecha de hoy; su origen dice «COR-… · OC-…» y enlaza a la ficha de la orden. La cuenta Proveedores pasó de $ 300,00 a **$ 280,00**. *(lo cubren `test_post_d_…` y el recorrido)*
16. **Correo.** En la terminal, **«Corrección de recepción · OC-…»** para A con la orden, la fecha de la recepción, «Fertilizante: 2 kg» y «Sigue pendiente: Fertilizante … faltan 2 kg»; no menciona a B ni a la Maceta. *(lo cubre `test_post_g_…`; el envío real, no)*
17. **Auditoría.** Un registro **«Corrección de recepción»** de Ana con la corrección, el detalle de la recepción, la línea y la orden como afectados y, en los datos, el movimiento y el asiento; más una **«Modificación de insumo en un invernadero»** con tránsito 0 → 2 y stock 10 → 8. *(lo cubre `test_post_h_…`)*
18. **El reclamo no cambia.** La ficha del reclamo sigue como la dejaste (emitido y cerrado): corregir no lo toca. *(lo cubre `test_r3_la_correccion_no_toca_…`)*
19. **Bandeja de pagos.** Como Contador, «Pagos a proveedores»: A **ya no figura** (tiene una línea pendiente) y no llegó ningún aviso nuevo. *(lo cubre `test_post_f_…`)*
20. **Volver a recibir y pagar.** Como Ana, Por recibir → A en Norte: Fertilizante **2** (con vencimiento) → confirmar. El Contador recibe el aviso «Proveedor para pagar» y A vuelve a la bandeja por **$ 300,00**. Pagalo (transferencia, hoy). La cuenta Proveedores queda en **cero**. *(lo cubre el recorrido y `test_post_d_tres_recepciones_…`)*
21. **Con el pago hecho ya no se corrige.** En la ficha de OC, Ana **ya no ve** «Corregir una recepción». Si abrís a mano `/compras/ordenes/<id de OC>/corregir-recepcion/`, dice **«No hay recepciones para corregir»**. *(lo cubren `test_ext_2a_…` y `test_regla_8_…`)*

**Por estado y por rol**

22. **Un lote que ya se usó** *(necesita otra orden recibida)*. Antes de corregir, bajá el stock del lote con un ajuste (Inventario → ajustar stock de Fertilizante, recuento físico, dejando **1 kg** en el lote). En el formulario, «Se puede descontar» dice **1** y avisa «El resto ya se usó o cubrió un faltante: se resuelve con un ajuste de stock»; pedir 2 se rechaza con «como máximo 1 kg». Con el lote en 0, la línea no tiene campo y dice «El lote ya no conserva nada…». *(lo cubren `test_ext_4a_…`)*
23. **Línea cerrada con faltante.** En una orden con Fertilizante recibido en parte y **cerrado con faltante**, esa línea del formulario dice **«Está cerrada con faltante: no se corrige.»** y no tiene campo; las otras líneas sí. *(lo cubren `test_ext_4b_…` y `test_paso_5_una_linea_cerrada_…`)*
24. **Roles.** **Gerente**: ve y corrige las recepciones de todos los invernaderos (la corrección queda sin Agrónomo) y es el único que emite y cierra reclamos. **Ana**: ve el reclamo (por la ficha de la orden → «Ver») **sin** botones y no tiene la pestaña «Reclamos». **Beto**, **Contador**, **Vendedor** y un **Capataz**: por la dirección escrita a mano (`/compras/ordenes/<id>/corregir-recepcion/`, `/compras/reclamos/<id>/`) dan **403**; en la ficha de OC el Contador ve la sección «Reclamos» pero **sin** enlace; sin sesión te lleva al inicio de sesión; un id que no existe da 404. *(lo cubren `test_quien_no_corrige_no_entra`, `test_quien_no_ve_el_reclamo_recibe_403_o_404`, `test_solo_el_gerente_emite_y_cierra_y_solo_por_post` y `test_el_agronomo_no_tiene_la_pestana_…`)*

**Lo que solo ve un navegador**

25. **Navegador real.** Con tu sesión de Ana abierta en el navegador, hacé una corrección de punta a punta (elegir cantidad, **«Ver resumen»**, **«Confirmar corrección»**) y, con la sesión del Gerente, **emití y cerrá un reclamo** apretando cada botón hasta el final; después volvé a abrir la ficha de la orden y la del reclamo. Tienen que mostrar el aviso verde y el nuevo estado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Fijate también que los botones se deshabilitan al enviar («Revisando…», «Corrigiendo…», «Emitiendo…», «Cerrando…») y que no se puede enviar dos veces seguidas.
26. **Sin JavaScript** *(opcional)*. Desactivá JavaScript y repetí la corrección y la emisión: todo son envíos comunes y enlaces; elegir la recepción es un enlace, no un desplegable.
27. **Celular** *(opcional)*. Con la ventana angosta, el formulario, el resumen y las listas se leen sin desplazarse hacia los costados (las tablas pueden desplazarse dentro de su recuadro). El Agrónomo y el Gerente usan la interfaz de escritorio.

## Cierre

**Qué se hizo** (en el orden de los pasos).

1. **Modelos y tipo nuevo.** `CorreccionRecepcion` (hereda de `OrigenDocumento`, tipo nuevo `correccion_de_recepcion`) y `DetalleCorreccionRecepcion` (una fila por lote descontado, con su movimiento `OneToOne`) en `compras` 0006. El tipo de movimiento `salida_por_correccion_de_recepcion` en `inventario` 0004 (la columna pasó de 30 a 40 caracteres; la restricción de tipos lo suma y la de origen no cambia: el tipo nuevo **tiene** origen) y `stock.registrar_salida_por_correccion_de_recepcion`. `contabilidad` 0009 suma el tipo de origen; `core` 0047, las acciones `correccion_recepcion`, `emision_reclamo` y `cierre_reclamo` (`ACCIONES_DE_NEGOCIO`).
2. **CMP-COR-RCP** (`compras/servicios/correcciones.py`): `recepciones_corregibles`, `lineas_corregibles`, `resumir_correccion` y `registrar_correccion` (lee sin bloquear, bloquea en el orden de D-90 punto 5, vuelve a validar con todo bloqueado; descuenta lote por lote del más nuevo al más viejo; asiento inverso **último**; correo en `on_commit`), el enlace del asiento a la ficha de la orden y la plantilla `correo/correccion.txt`.
3. **CMP-EMT-RCL y CMP-CRR-RCL** (`compras/servicios/reclamos.py`): `reclamos`, `ficha_de_reclamo`, `emitir_reclamo` (resuelve la alerta por su `AlertaCompras`, audita, correo en `on_commit`) y `cerrar_reclamo`; plantilla `correo/reclamo.txt`.
4. **Pantallas:** «Corregir una recepción» (formulario, resumen y aviso de «nada para corregir»), «Compras» → «Reclamos» (lista con filtros y ficha con «Emitir reclamo» y «Cerrar reclamo»), el botón y lo corregido en la ficha de la orden, la sección «Reclamos» de la ficha de la orden y de la del proveedor, y la tarjeta y lista «Reclamos sin emitir» del Inicio del Gerente.

**Pruebas** (con `main` en `f5c59af`, PRD-05 (#87) incluida, y `DJANGO_DEBUG=1`).

- `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: **2702 pruebas, OK**.
- `python manage.py test compras --keepdb --tag concurrencia`: **50 pruebas, OK** (9 nuevas).
- Con los pasos 1 a 3 hechos, `compras inventario contabilidad core` (3445 pruebas, sin las de concurrencia ni de migración): **OK**; el paso 4 no tocó `core`.
- `makemigrations --check --dry-run`: sin cambios.

**Decisiones.** No creé ninguna.

**Pantallas: lo que se corrigió del prototipo** (D-61).

- `c_cor` pedía un **«motivo» obligatorio**; el caso de uso (paso 5) pide una **observación opcional**: se cambió. Registraba **sin resumen**; el caso de uso (paso 7) pide el resumen con el asiento inverso y el aviso al proveedor antes de confirmar: se agregó. No mostraba los **lotes** de cada línea; se agregaron (cuánto conserva cada uno) y por qué una línea no se puede corregir (cerrada con faltante, lote sin stock, extensiones 4a y 4b).
- `c_cor` tenía un **desplegable** para elegir la recepción; D-24 pide desplegables propios y accesibles: acá se eligen con enlaces (sin JavaScript).
- `c_rcl` emitía y cerraba con **ventanas**; acá son botones de un formulario POST en la ficha con la explicación al lado (funciona sin JavaScript). Para el Agrónomo la ficha es solo lectura (la regla 2 la ve el Gerente; la ficha de la orden y la del proveedor llevan a ella).
- `tabRcl` mostraba la pestaña a cualquier Gerente y se completó con los estados vacíos; `panelGer` se completó con la tarjeta de cantidad y el enlace a la lista filtrada.
- La ficha de la orden suma el botón «Corregir una recepción» (regla 8 de CMP-CNS-ODC), lo corregido por línea y la sección «Reclamos» (regla 4 de CMP-EMT-RCL), y la del proveedor, su tarjeta de reclamos (regla 4 de CMP-CNS-PRV).

**Lo que difiere de la documentación** (para `docs/temas_abiertos.md`; no se corrigió en silencio).

- **«Límites» no nombraba tres cambios que hicieron falta:** `OrigenDocumento.Tipo.CORRECCION_DE_RECEPCION` con `contabilidad` 0009 (D-90 punto 3 lo exige); `inventario` 0004 **no es «solo de `choices`»**: el valor tiene 34 caracteres y la columna era de 30, así que sube a 40 y reescribe la restricción de tipos; y `inventario/tests/fabricas.py` suma el tipo nuevo a `SALIDAS`. El estudiante los aprobó antes de empezar.
- **El campo `recepcion` de `CorreccionRecepcion` se llama `recepcion_corregida`:** `recepcion` choca con el accesorio de la herencia multitabla (`OrigenDocumento.recepcion` apunta a la hija `Recepcion`; error E006 de Django, la misma lección de D-83). `Recepcion` accede con `correcciones`. Corregir `docs/modelo/compras.md` («CorreccionRecepcion») y `correccion_y_reclamos.md`.
- **Extensión 10a** de CMP-COR-RCP dice «el Sistema reintenta el envío» del correo: no hay cola de reintentos (D-88 punto 6, como CMP-04 y CMP-05). El correo se manda en `on_commit` y, si falla, no se reintenta. Lo mismo para la emisión del reclamo.
- **Quién ve los reclamos:** el caso de uso solo nombra al Gerente; el servicio deja al Agrónomo ver los reclamos de sus invernaderos (en solo lectura) porque la ficha de la orden y la del proveedor llevan a ellos. El Contador no los ve.
- **La alerta del Gerente** («recepción con inconvenientes») sigue llevando a la ficha de la orden (CMP-04), que ahora tiene la sección «Reclamos» con el enlace: la regla 4 de CMP-EMT-RCL («desde la alerta o desde la ficha de la orden») se cumple; llevarla directo a la ficha del reclamo cambia una prueba de CMP-04 (`test_recorrido_recepcion.py`) y queda como mejora.
- **Códigos de error nuevos** (`ErrorDeCompras`): `pago_registrado`, `sin_lineas`, `linea_repetida`, `linea_ajena`, `linea_cerrada_con_faltante`, `cantidad_invalida`, `supera_lo_corregible` (con `datos["maxima"]`), `reclamo_ya_emitido`, `reclamo_ya_cerrado` y `reclamo_sin_emitir`; lo máximo corregible usa `min(lo que el lote conserva, lo que esa recepción ingresó en él − lo ya corregido)` (D-90 punto 4, con «ya corregido» para correcciones sucesivas).
- **«Alertas que se reactivan»** del resumen: solo «stock inconsistente» puede reactivarse; la de «bajo el mínimo» no cambia porque lo corregido sube el tránsito lo mismo que baja el stock.

**Informe de verificación** (docs/patrones/verificacion_a_mano.md).

*Verifiqué:*

- El **recorrido** `test_recorrido_correccion_y_reclamos.py` (dos recepciones de A con un inconveniente → el Gerente ve el reclamo sin emitir en el Inicio y en «Reclamos», lo emite con su correo y la alerta resuelta → Ana corrige 2 kg por formulario, resumen y confirmación → asiento inverso, stock, tránsito y Proveedores en $ 280,00, correo → A sale de la bandeja → se vuelve a recibir y el Contador paga, Proveedores en cero → sin botón y sin recepciones corregibles → el Gerente cierra el reclamo y no se puede reabrir → Beto, 403): **OK**.
- Los **comandos de «Hecho cuando»**: 2702 y 50 pruebas, **OK**.
- **Migraciones:** `sqlmigrate compras 0006` crea las dos tablas con sus restricciones y claves; no borra ni reescribe nada. `sqlmigrate inventario 0004` quita y vuelve a poner la restricción de tipos y cambia la columna a `varchar(40)` (no toca filas). `sqlmigrate contabilidad 0009` y `sqlmigrate core 0047` son `no-op`. Se aplicaron en la base de pruebas (las pruebas corren sobre ella).
- **No toqué tu base de desarrollo** (no borré ni cargué datos).

*Lo cubre una prueba:* cada paso de la «Verificación a mano» nombra la suya; para todo lo demás, los encabezados de los archivos de pruebas.

*No pude verificar:*

- **Navegador real, JavaScript desactivado, celular y aspecto** (no abro navegador, D-96): pasos 25, 26 y 27.
- **Envío real de correo** (las pruebas usan el backend simulado): pasos 4 y 16 con el correo en modo consola o con tu SMTP.
- **Que tu base de desarrollo tenga las migraciones aplicadas:** corré `python manage.py migrate` antes del paso 1.
- **Despliegue en Render y Neon:** que `migrate` aplique las cuatro migraciones y que las pantallas abran en producción.
- **El experimento de bloqueo quitado** (correr la concurrencia con el ejercicio bloqueado antes de la orden): la tarea toca bloqueos, pero el experimento solo se hace si lo pedís; `test_regla_el_ejercicio_va_ultimo_…` ya cubre el orden.
- **Un lote consumido o ajustado desde la pantalla** (paso 22): hay que preparar el stock a mano; lo cubren las pruebas de lotes.
- **Criterio de producto:** si el formulario y el resumen «se sienten bien» para quien corrige.

## Cierre de documentación (M3)

Propuesto, **sin aplicar**: README de tareas, plan de la ronda («Compras 1» cerrada), `docs/estado.md`, `docs/historial.md`, `docs/disparadores.md` (cerrá lo que quede de compras), `docs/revisiones_pendientes.md`, `docs/temas_abiertos.md` y `docs/modelo/compras.md`. Aplicado en esta tarea: `docs/modelo/inventario.md` (el tipo nuevo, permitido en «Límites»).
