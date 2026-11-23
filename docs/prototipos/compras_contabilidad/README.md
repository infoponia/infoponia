# Prototipo · Compras, contabilidad y estadísticas

Archivo: `compras_contabilidad_y_estadisticas.html` (esta carpeta), copia del artefacto «InfoPonia · Compras, contabilidad y estadísticas»
(23/11/2026, 2.958 líneas, 478 KB; con las cuatro diferencias con los casos de uso ya corregidas). Es el prototipo de comercial y cosecha, que ya integra producción e IoT, con lo nuevo encima. Es la guía
visual de las tres rondas nuevas: **manda el caso de uso** (D-61): si a una pantalla le falta algo o algo está mal como interfaz, Claude Code la
corrige y lo anota en el «Cierre» (regla L7). `nota_de_cobertura.md` (esta carpeta) dice qué pantalla cumple cada caso de uso y qué datos de ejemplo
usar para probar cada excepción. **No leas el archivo entero (regla L6)**: buscá con Grep el nombre de la función y leé solo esa parte.

> **Solo prototipo, no es del sistema:** el menú «ver como», el interruptor «Hay un Contador activo», «Reiniciar datos de ejemplo», «Resaltar
> lo nuevo» y los datos de ejemplo (`DB`, `CC()`, `KK()`). El rol «Proveedor» es el portal por enlace (no una cuenta).

## Cómo está armado

- Vistas en `VIEWS` (`VIEWS.k_asi`…), ventanas en `MODALS`, `INIT.<vista>` carga un formulario antes de mostrarla y `ACT.<acción>` es lo que hace
  cada botón. Las pestañas se arman con `tabs(...)`; cada pestaña es una función `tab…`.
- `NAV.ger`, `NAV.agr`, `NAV.con` (línea 2277 a 2279): el menú de cada rol. Los datos de contabilidad están en `KK()`, los de compras en `CC()`.
- Algunas definiciones envuelven a otras anteriores: leé **todas** las definiciones de una función, de la primera a la última.

## Contabilidad (lote 1)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Menú y pestañas de «Contabilidad» | `VIEWS.k_main` (2734) | CON-03a | — |
| Libro de gestión, vista cronológica | `tabLibro` (2738), `libroCron` (2742) | CON-03a | CON-CNS-LGS |
| Libro de gestión, vista por cuenta | `libroCta` (2749) | CON-03a | CON-CNS-LGS |
| Ficha del asiento | `VIEWS.k_asi` (2757) | CON-03a / CON-03b | CON-CNS-LGS |
| Registrar asiento | `VIEWS.k_new` (2776), `INIT.k_new`, `ACT.mvadd`, `ACT.mvdel`, `ACT.mvt`, `ACT['asi-ok']` (2786 a 2789) | CON-03b | CON-REG-ASI |
| Contraasentar | `VIEWS.k_contra` (2794), `ACT['contra-ok']` (2802) | CON-03b | CON-CTR-ASI |
| Ejercicios y cierre | `tabEje` (2807), `VIEWS.k_cierre` (2811), `ACT['cierre-ok']` (2819) | CON-03a | CON-CRR-EJE |
| Plan de cuentas | `tabPlan` (2821), `PLAN` (2067), `RUBROS` (2087) | CON-03a | CON-CNS-PCT |
| Panel del Contador | `panelCon` (2948) | CON-03a (alerta del ejercicio en cierre) | — |

## Compras (lote 2)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Menú y pestañas de «Compras» | `VIEWS.c_main` (2325), `cmpTabs` (2320) | CMP-01 (menú) y cada tarea su pestaña | — |
| Proveedores: lista, ficha, formulario | `tabPrv` (2640), `VIEWS.c_prv` (2645), `VIEWS.c_prvform` (2663); CUIT en `cuitValido` (1964) | CMP-01 | CMP-ALT/MOD/BAJ/CNS-PRV |
| Pedidos: lista, ficha, nuevo | `tabPed` (2329), `VIEWS.c_ped` (2342), `VIEWS.c_pednew` (2452), `cobertura` (2201) | CMP-02a | CMP-RLZ-PED, CMP-CNS-PED |
| Portal del proveedor (por enlace) | `VIEWS.c_cotz` (2691) | CMP-02a | CMP-ENV-COT |
| Cancelar pedido | `VIEWS.c_pedcnl` (2479) | CMP-02b | CMP-CNL-PED |
| Comparar cotizaciones y generar orden | `VIEWS.c_gen` (2490), `INIT.c_gen` (2486) | CMP-03 | CMP-GNR-ODC |
| Órdenes: lista y ficha | `tabOdc` (2373), `VIEWS.c_odc` (2383), `odcEstado` (2213) | CMP-03 (CMP-04 a 06 suman secciones) | CMP-CNS-ODC |
| Revisar y decidir (Gerente) | `VIEWS.c_apr` (2528), `INIT.c_apr` (2543) | CMP-03 | CMP-APR-ODC |
| Por recibir y registrar recepción | `tabRec` (2411), `VIEWS.c_rcp` (2561), `INIT.c_rcp` (2550), `entregasPend` (2224) | CMP-04 | CMP-REG-RCP |
| Cerrar con faltante | `VIEWS.c_flt` (2590) | CMP-04 | CMP-CRR-FLT |
| Pagos: pendientes, hechos y registrar | `tabPag` (2622), `VIEWS.c_pag` (2627), `pagosPend` (2220) | CMP-05 | CMP-REG-PAG |
| Corregir una recepción | `VIEWS.c_cor` (2607), `INIT.c_cor` (2603) | CMP-06 | CMP-COR-RCP |
| Reclamos: lista y ficha (emitir, cerrar) | `tabRcl` (2417), `VIEWS.c_rcl` (2420) | CMP-06 | CMP-EMT-RCL, CMP-CRR-RCL |
| Inicio del Agrónomo y del Gerente (compras) | `panelAgr` (2938), `panelGer` (2944) | CMP-03 (pedidos vencidos, órdenes por aprobar), CMP-04 (por recibir), CMP-05 (pagos), CMP-06 (reclamos sin emitir) | — |

## Estadísticas (lote 4)

| Pantalla | Función (línea) | Tarea | Caso de uso |
|---|---|---|---|
| Selector de período y «Comparar con el período anterior» | `PERS` (2827), `perRango` (2830), `VIEWS.e_main` (2866) | EST-01 | EST-CNS-PRD regla 2 |
| Estadísticas de producción | `stProd` (2892), `prodPer` (2854) | EST-01 | EST-CNS-PRD |
| Pestañas del Gerente | `statsTabs` (2865) | EST-02 | EST-CNS-CNS |
| Resumen, Compras y Resultados | `stRes` (2930), `stCmp` (2914), `comprasEv` (2861), `stRtd` (2922) | EST-02 | EST-CNS-CNS (7, 9 y 10) |
| Comercial | `stCom` (2908) | EST-03 | EST-CNS-CNS (8) |
| Paneles (no son estadísticas) | `panelAgr` (2938), `panelGer` (2944), `panelCon` (2948) | compras y contabilidad | — |
