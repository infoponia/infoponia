# Prototipo · Compras, contabilidad y estadísticas

Archivo: `compras_contabilidad_y_estadisticas.html` (esta carpeta), copia del artefacto «InfoPonia · Compras, contabilidad y estadísticas»
(23/11/2026, 2.927 líneas, 473 KB). Es el prototipo de comercial y cosecha, que ya integra producción e IoT, con lo nuevo encima. Es la guía
visual de las tres rondas nuevas: **manda el caso de uso** (D-61): si a una pantalla le falta algo o algo está mal como interfaz, Claude Code la
corrige y lo anota en el «Cierre» (regla L7). `nota_de_cobertura.md` (esta carpeta) dice qué pantalla cumple cada caso de uso y qué datos de ejemplo
usar para probar cada excepción. **No leas el archivo entero (regla L6)**: buscá con Grep el nombre de la función y leé solo esa parte.

> **Solo prototipo, no es del sistema:** el menú «ver como», el interruptor «Hay un Contador activo», «Reiniciar datos de ejemplo», «Resaltar
> lo nuevo» y los datos de ejemplo (`DB`, `CC()`, `KK()`). El rol «Proveedor» es el portal por enlace (no una cuenta).

## Cómo está armado

- Vistas en `VIEWS` (`VIEWS.k_asi`…), ventanas en `MODALS`, `INIT.<vista>` carga un formulario antes de mostrarla y `ACT.<acción>` es lo que hace
  cada botón. Las pestañas se arman con `tabs(...)`; cada pestaña es una función `tab…`.
- `NAV.ger`, `NAV.agr`, `NAV.con` (línea 2275 a 2277): el menú de cada rol. Los datos de contabilidad están en `KK()`, los de compras en `CC()`.
- Algunas definiciones envuelven a otras anteriores: leé **todas** las definiciones de una función, de la primera a la última.

## Contabilidad (lote 1)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Menú y pestañas de «Contabilidad» | `VIEWS.k_main` (2732) | CON-03a | — |
| Libro de gestión, vista cronológica | `tabLibro` (2736), `libroCron` (2740) | CON-03a | CON-CNS-LGS |
| Libro de gestión, vista por cuenta | `libroCta` (2747) | CON-03a | CON-CNS-LGS |
| Ficha del asiento | `VIEWS.k_asi` (2755) | CON-03a / CON-03b | CON-CNS-LGS |
| Registrar asiento | `VIEWS.k_new` (2774), `INIT.k_new`, `ACT.mvadd`, `ACT.mvdel`, `ACT.mvt`, `ACT['asi-ok']` (2784 a 2787) | CON-03b | CON-REG-ASI |
| Contraasentar | `VIEWS.k_contra` (2792), `ACT['contra-ok']` (2800) | CON-03b | CON-CTR-ASI |
| Ejercicios y cierre | `tabEje` (2805), `VIEWS.k_cierre` (2809), `ACT['cierre-ok']` (2817) | CON-03a | CON-CRR-EJE |
| Plan de cuentas | `tabPlan` (2819), `PLAN` (2067), `RUBROS` (2086) | CON-03a | CON-CNS-PCT |
| Panel del Contador | `panelCon` (2917) | CON-03a (alerta del ejercicio en cierre) | — |

**Diferencia ya detectada:** el contraasiento del prototipo limita la fecha al ejercicio del asiento original; el caso de uso (C3) deja elegir
cualquier fecha que caiga en un ejercicio abierto o en cierre. Manda el caso de uso.

## Compras (lote 2)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Menú y pestañas de «Compras» | `VIEWS.c_main` (2323), `cmpTabs` (2318) | CMP-01 (menú) y cada tarea su pestaña | — |
| Proveedores: lista, ficha, formulario | `tabPrv` (2638), `VIEWS.c_prv` (2643), `VIEWS.c_prvform` (2661); CUIT en `cuitValido` (1964) | CMP-01 | CMP-ALT/MOD/BAJ/CNS-PRV |
| Pedidos: lista, ficha, nuevo | `tabPed` (2327), `VIEWS.c_ped` (2340), `VIEWS.c_pednew` (2450), `cobertura` (2199) | CMP-02a | CMP-RLZ-PED, CMP-CNS-PED |
| Portal del proveedor (por enlace) | `VIEWS.c_cotz` (2689) | CMP-02a | CMP-ENV-COT |
| Cancelar pedido | `VIEWS.c_pedcnl` (2477) | CMP-02b | CMP-CNL-PED |
| Comparar cotizaciones y generar orden | `VIEWS.c_gen` (2488), `INIT.c_gen` (2484) | CMP-03 | CMP-GNR-ODC |
| Órdenes: lista y ficha | `tabOdc` (2371), `VIEWS.c_odc` (2381), `odcEstado` (2211) | CMP-03 (CMP-04 a 06 suman secciones) | CMP-CNS-ODC |
| Revisar y decidir (Gerente) | `VIEWS.c_apr` (2526), `INIT.c_apr` (2541) | CMP-03 | CMP-APR-ODC |
| Por recibir y registrar recepción | `tabRec` (2409), `VIEWS.c_rcp` (2559), `INIT.c_rcp` (2548), `entregasPend` (2222) | CMP-04 | CMP-REG-RCP |
| Cerrar con faltante | `VIEWS.c_flt` (2588) | CMP-04 | CMP-CRR-FLT |
| Pagos: pendientes, hechos y registrar | `tabPag` (2620), `VIEWS.c_pag` (2625), `pagosPend` (2218) | CMP-05 | CMP-REG-PAG |
| Corregir una recepción | `VIEWS.c_cor` (2605), `INIT.c_cor` (2601) | CMP-06 | CMP-COR-RCP |
| Reclamos: lista y ficha (emitir, cerrar) | `tabRcl` (2415), `VIEWS.c_rcl` (2418) | CMP-06 | CMP-EMT-RCL, CMP-CRR-RCL |
| Inicio del Agrónomo y del Gerente (compras) | `panelAgr` (2907), `panelGer` (2913) | CMP-03 (pedidos vencidos, órdenes por aprobar), CMP-04 (por recibir), CMP-05 (pagos), CMP-06 (reclamos sin emitir) | — |

**Diferencias ya detectadas (manda el caso de uso):** `VIEWS.c_pag` preselecciona «Transferencia» y el caso de uso pide el medio sin
preselección (H23); `VIEWS.c_cotz` tiene un selector «enlace de ejemplo» que es solo del prototipo (el proveedor entra por su enlace y ve solo
su pedido).

## Estadísticas (lote 4)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Selector de período y «Comparar con el período anterior» | `PERS` (2825), `perRango` (2828), `VIEWS.e_main` (2864) | EST-01 | EST-CNS-PRD regla 2 |
| Estadísticas de producción | `stProd` (2871), `prodPer` (2852) | EST-01 | EST-CNS-PRD |
| Pestañas del Gerente | `statsTabs` (2863) | EST-02 | EST-CNS-CNS |
| Resumen, Compras y Resultados | `stRes` (2899), `stCmp` (2883), `comprasEv` (2859), `stRtd` (2891) | EST-02 | EST-CNS-CNS (7, 9 y 10) |
| Comercial | `stCom` (2877) | EST-03 | EST-CNS-CNS (8) |
| Paneles (no son estadísticas) | `panelAgr` (2907), `panelGer` (2913), `panelCon` (2917) | compras y contabilidad | — |

**Diferencias ya detectadas (mandan el caso de uso y D-93):** `stProd` muestra kilos y «pérdida sobre lo cosechado», y le faltan las órdenes a
tiempo, el costo por planta, el consumo de insumos y las alertas del IoT; `stCmp` muestra «pendiente de pago hoy» (es del Panel, H27) y
«entregas a tiempo» (no es un indicador del caso de uso).
