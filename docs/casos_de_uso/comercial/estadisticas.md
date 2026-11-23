# Casos de uso · comercial · Estadísticas comerciales

Copia para el repo de **COM-CNS-EST · Consultar Estadísticas Comerciales, versión 0.1** (alto nivel), documento «CU · COM-CNS-EST · Consultar
Estadísticas Comerciales (v0.1)» de la carpeta de Drive «InfoPonia · Comercial · Análisis», consultado el 22/11/2026. Cotejado con
«PCU · Cambios para pendientes_CU (comercial)» (secciones 4 y 15) y con «MD · Cambios para el modelo de dominio (comercial)» (MD-115, MD-130,
MD-136 y MD-139).

**El código va en la app `comercial`** (`comercial/servicios/estadisticas.py`, solo lectura; las vistas en `comercial/views_estadisticas.py`).
No crea modelos ni migraciones. Cómo se calcula cada indicador: **D-94, punto 15**. Tarea: **COM-08c**. Archivos de pruebas:
`comercial/tests/test_com_cns_est.py` y `test_estadisticas_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: el caso de uso numera sus reglas (`test_regla_6_…`).

## COM-CNS-EST · Consultar Estadísticas Comerciales

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos», sección «Casos de uso de alto nivel».
Reemplaza a CU-60 de «Documentacion para la IA» y al caso 30 de PCU. Decisiones del 20/11/2026: el Gerente también es actor; las ventas se
cuentan por concreción de la entrega y sin descontar indemnizaciones; sin exportación.

**Actores:** Vendedor o Gerente. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** ver cómo rinden las ventas, las entregas y la cobranza de un período, para tomar decisiones comerciales.

**Precondición:** a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición:** a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas**

1. Alcance: el Vendedor ve solo los datos de sus contratos; el Gerente ve todos y puede filtrar por Vendedor.
2. Filtros: período (por defecto, el mes actual hasta hoy; se puede elegir otro mes o un rango de fechas) e invernadero (el Vendedor, entre
   los suyos; el Gerente, entre todos). Cada indicador usa la fecha que indica su regla.
3. Ventas en pesos por variedad: suma lo vendido en las entregas concretadas en el período, de compra-ventas y suministros (lo que registró
   el asiento de cada entrega, por devengado), por variedad, con cantidad de plantas y monto. No descuenta indemnizaciones: van en el
   indicador 5.
4. Entregas a tiempo y con retraso: de las entregas concretadas en el período, a tiempo son las concretadas en la fecha prometida o antes
   (fecha pactada en una compra-venta, fecha del período en un suministro, no la reprogramada) y con retraso, las demás. Se muestran cantidad
   y porcentaje de cada grupo, el promedio de días de retraso y, aparte, la cantidad de intentos fallidos del período.
5. Incumplimientos aceptados y monto indemnizado: quejas y discrepancias aceptadas en el período (por fecha de resolución) y la suma
   indemnizada, separada en descuentos sobre el monto a cobrar e indemnizaciones pagadas en dinero. Las resoluciones anuladas no cuentan
   (COM-ANL-SRV).
6. Cobranza pendiente y vencida: foto a la fecha actual, no por período. Suma el monto a cobrar de las entregas de suministro sin pagar,
   separando pendientes y vencidas, y las vencidas por antigüedad (hasta 30 días, 31 a 60, más de 60). Los cobros anulados no cuentan como
   pagos (MD-136).
7. Faltantes y rechazos de compra-venta: detalles de compra-venta del período que pasaron a «pendiente de decisión del cliente» (faltante),
   que el cliente rechazó por cantidad reducida, que rechazó al recibir y que se cancelaron (MD-130).
8. Clientes con más compras: los diez clientes con más ventas en pesos del período (mismo cálculo que el indicador 3), con la cantidad de
   entregas y el porcentaje del total.
9. Sin comparaciones entre períodos ni proyecciones.
10. Desde cada indicador se puede ir a la consulta correspondiente con el mismo filtro: ventas, entregas y clientes a COM-CNS-CVT y
    COM-CNS-SUM; incumplimientos a COM-CNS-SRV; cobranza a COM-CNS-SUM.
11. La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).

## Cambios ya decididos que se aplican

| Fuente | Qué cambia | Dónde |
|---|---|---|
| MD-139 | «Vencidas» → «en mora» (la antigüedad se cuenta desde el vencimiento del pago) | Regla 6 |
| PCU, sección 15 | El Gerente es actor, ocho indicadores (PCU sección 4 decía seis), sin exportación | Todo el caso de uso (ya en la v0.1) |
| **D-94, punto 15** | Las fechas que usa cada indicador cuando el modelo no guarda la de la decisión (regla 7), el invernadero de cada dato, el rango máximo | Reglas 2, 4 y 7 |
| Plan de la ronda (sección 4) | Estadísticas es una **pestaña** de Comercial, no una entrada del menú; el Vendedor ve «Resultados del mes en curso» en su panel | Pantallas |

## Cómo se aplica en la ronda «Comercial 1» (COM-08c; D-44, D-94)

### Servicio (`comercial/servicios/estadisticas.py`)

| Función | Regla | Qué devuelve |
|---|---|---|
| `filtros_de_estadisticas(actor, get, hoy) -> FiltrosDeEstadisticas` | 1, 2, 11 | Valida y normaliza el período (mes o rango), el invernadero y el Vendedor. Ver «Filtros» |
| `estadisticas(actor, filtros, hoy) -> Estadisticas` | 3 a 8 | Los ocho indicadores (abajo). Lectura pura: ninguna escritura, ninguna auditoría (postcondición a) |
| `resultados_del_mes(actor, hoy) -> ResultadosDelMes` | 3, 4, 5 | Lo del panel del Vendedor: ventas, entregas a tiempo e indemnizado del mes en curso. Llama a las mismas funciones internas que `estadisticas` |

Errores (`ErrorComercial`): `periodo_invalido` (inicio posterior al fin, fin posterior a hoy, o más de **366 días**), `invernadero_fuera_de_alcance`,
`vendedor_no_admitido` (el Vendedor no filtra por Vendedor); `sin_permiso` (otro rol).

### Filtros (reglas 1, 2 y 11)

- **Alcance:** el Vendedor activo, los contratos de los que es Vendedor (`Contrato.objects.en_alcance_de`, D-28); el Gerente activo, todos, con
  el filtro opcional «Vendedor» (todos los Vendedores, activos o no, que tengan algún contrato). Cualquier otro rol, 403.
- **Período:** por omisión, del 1 del mes actual a hoy. El desplegable ofrece el mes actual («Noviembre de 2026 (hasta hoy)») y los doce
  anteriores; «Otro rango» abre «Desde» y «Hasta» (fechas). Un mes pasado va del 1 al último día. Las fechas se comparan en la zona horaria
  del invernadero (`hoy()` del sistema).
- **Invernadero:** el Vendedor, entre los suyos activos (y los inactivos donde tuvo contratos); el Gerente, entre todos. Qué invernadero tiene
  cada dato: una **entrega**, su invernadero de origen (`OrdenTrabajo.invernadero`); una **solicitud**, el de su entrega; un **detalle de
  venta**, el de sus reservas (`ReservaStock.invernadero`; uno con reservas en dos invernaderos cuenta en los dos filtros y una vez sin
  filtro).
- Los filtros van en la URL (`?periodo=2026-11` o `?desde=…&hasta=…`, `&invernadero=…&vendedor=…`), para que el enlace de cada indicador lleve
  el mismo filtro (regla 10).

### Indicadores (D-94, punto 15)

| N.º | Indicador | Qué entra | Cálculo |
|---|---|---|---|
| 3 | Ventas por variedad | Las líneas (`DetalleEntrega`) de las entregas **concretadas** con `fecha_resolucion_orden` en el período, de compra-ventas y de suministros | Por variedad: Σ `cant_entregada` (plantas) y Σ `monto_pagar` (lo que registró cada entrega). Orden: monto descendente. Total del período. Sin descontar indemnizaciones |
| 4 | Entregas a tiempo y con retraso | Las mismas entregas concretadas | **Fecha prometida:** en una compra-venta, `fecha_pactada_venta`; en un suministro, la **menor** `fecha_periodo` de sus líneas (no la `fecha_programada_orden`, que puede haberse reprogramado). A tiempo: `fecha_resolucion_orden <= prometida`; con retraso: las demás. Cantidad y porcentaje de cada grupo (redondeado a entero; «—» sin entregas); promedio de `(resolución − prometida).days` de las con retraso, con un decimal. **Intentos fallidos:** `IntentoFallido` con `fecha_hora` en el período, de entregas en el alcance y del invernadero |
| 5 | Incumplimientos aceptados | Las solicitudes **hoy** `aceptada` con `fecha_resolucion` en el período | Cantidad (quejas y discrepancias, y cuántas de cada tipo); Σ `monto_descontado` («descuentos sobre el monto a cobrar») y Σ `monto_reintegrado` («pagadas en dinero»); el total. Una resolución anulada dejó la solicitud «pendiente» y no cuenta; si se volvió a aceptar, cuenta con su fecha nueva |
| 6 | Cobranza a la fecha | Foto a **hoy**, sin período: entregas de suministro concretadas **no pagadas** (`estado_de_pago`, COM-08a: sin línea de pago vigente ni saldadas) del alcance y del invernadero | Σ `monto_a_cobrar` de las «pendientes» y de las «en mora»; las en mora por antigüedad, `(hoy − fecha_vencimiento_pago).days`: de 1 a 30, de 31 a 60, más de 60 |
| 7 | Faltantes y rechazos de compra-venta | Detalles de venta del alcance y del invernadero | **Con faltante:** `fecha_pendiente_decision` en el período. **Rechazados por cantidad reducida:** de los anteriores, los que hoy están `rechazado` y no tienen línea en una entrega concretada (lo rechazó el cliente en COM-DCD-FLT). **Rechazados al recibir:** las líneas de venta con `cant_entregada = 0` en entregas concretadas en el período. **Cancelados:** detalles `cancelado` cuya venta tiene `fecha_cancelacion_venta` en el período |
| 8 | Clientes con más compras | Lo del indicador 3 | Por cliente del contrato: Σ `monto_pagar` y la cantidad de entregas; los diez primeros (monto descendente y, a igualdad, nombre); el porcentaje sobre el total del indicador 3 |

- Arriba de todo, cuatro tarjetas (prototipo `VIEWS.est`): «Ventas» (el total del 3 y la cantidad de entregas), «Entregas a tiempo» (el % del
  4 y cuántas con retraso), «Indemnizado» (el total del 5; color de advertencia si hay) y «Cobranza en mora» (el total en mora del 6; en rojo
  si hay).
- **Rendimiento:** una consulta agregada por indicador (`values().annotate()`), con los filtros en la base; sin consultas por fila. El
  indicador 7 son cuatro consultas. Índices: los que ya existen (`(invernadero, estado_orden, fecha_programada_orden)` del padre; las FK); si
  la prueba de rendimiento lo pide, un índice `(estado_orden, fecha_resolucion_orden)` en `OrdenTrabajo` **no** se agrega en esta tarea
  (sería una migración de `produccion`): se anota en `docs/temas_abiertos.md`.
- **Decimales:** todo en `Decimal`; porcentajes y promedios se redondean recién para mostrar.

### Enlaces de cada indicador (regla 10)

| Indicador | Lleva a | Con |
|---|---|---|
| 3 y 8 | La lista de contratos (COM-CNS-CVT y COM-CNS-SUM, pestaña «Contratos») | El Vendedor y el cliente (en el 8) del filtro |
| 4 | La lista de entregas (COM-05a1) | Estado «concretada» y el rango de fechas |
| 5 | La pestaña «Solicitudes de revisión» (COM-CNS-SRV) | Estado «aceptadas» y el rango de fechas |
| 6 | La pestaña «Cobranza», «Por cobrar» (COM-08a) | — (es una foto) |
| 7 | La lista de contratos, compra-ventas | El rango de fechas |

Si la pantalla de destino no admite alguno de esos filtros, el enlace lleva los que admite (no se agregan filtros nuevos a otras pantallas en
esta tarea; lo que falte va al «Cierre»).

## Pantallas

Referencia visual (D-61): `docs/prototipos/comercial/` (`README.md`).

| Pantalla | Funciones del prototipo | Qué tiene |
|---|---|---|
| Comercial · pestaña «Estadísticas» (`/comercial/estadisticas/`) | `VIEWS.est` (línea 1214), `kpi` (línea 1411) y la versión de `VIEWS.com` de la línea 1485 (la agrega como pestaña) | Los filtros, las cuatro tarjetas y las seis tarjetas de los indicadores (ventas por variedad con barras horizontales, entregas, incumplimientos, cobranza, faltantes y rechazos, clientes), cada una con su enlace |
| Panel de control del Vendedor · «Resultados del mes en curso» | `secMes` (línea 1725) | Tres indicadores: «Ventas» (y las entregas concretadas en el mes), «Entregas a tiempo» (y cuántas con retraso) e «Indemnizado»; debajo, «Para otros meses, vea Comercial › Estadísticas.» con el enlace |

- **Panel de control (comparado con lo que va a estar implementado, plan de la ronda, sección 5):** «Resultados del mes en curso» va dentro
  de la sección «Comercial» que registró COM-05a2, **solo para el Vendedor**, entre el grupo «Entregas» y el grupo «Cobranza» (COM-08a). No
  registra otra sección.
- **Menú:** sin cambios (Estadísticas es una pestaña de Comercial, plan de la ronda, sección 4).
- **Gráficos:** las barras de «Ventas por variedad» son HTML y CSS (un `div` con ancho proporcional, como el prototipo), sin bibliotecas
  nuevas; cada barra lleva su monto en texto (no solo el color).
- **Textos explicativos** (criterio «textos explicativos siempre»):
  - arriba: «Resultados del período elegido. Las ventas se cuentan cuando se concreta la entrega y no descuentan indemnizaciones. La cobranza
    es la situación de hoy.»;
  - en «Entregas a tiempo»: «A tiempo es en la fecha prometida al cliente o antes (la pactada o la del período), aunque la entrega se haya
    reprogramado.»;
  - en «Incumplimientos aceptados»: «Quejas y discrepancias que el Gerente aceptó en el período. Las anuladas no cuentan.»;
  - en «Faltantes y rechazos»: «Productos de compra-venta que no se pudieron entregar completos o que el cliente no aceptó.».
- URL `estadisticas/` bajo el espacio `comercial`; vista con `rol_requerido("gerente", "vendedor")`, `never_cache`; los filtros con un
  formulario GET que se aplica con «Ver estadísticas» (funciona sin JavaScript; con HTMX recarga solo el cuerpo). Cambiar un desplegable no
  dispara nada: la validación del período corre al presionar el botón (`.claude/rules/interfaz.md`, «Validaciones e interacción HTMX»).

### Lo que difiere del prototipo (corregir, D-61)

| Pantalla | Prototipo | Caso de uso (manda) |
|---|---|---|
| Estadísticas | El período solo ofrece tres meses fijos | Regla 2: el mes actual, otro mes o un rango |
| Estadísticas | «Intentos de entrega fallidos» y «Con faltante» con valores fijos (`'1'`, `+1`) | Reglas 4 y 7: calculados |
| Estadísticas | Ventas de un suministro con el precio de hoy (`precioHoy(d)`) | Regla 3: lo que registró cada entrega (`monto_pagar`, con el precio al concretar) |
| Estadísticas | A tiempo compara con `fp` (la fecha programada de la entrega) | Regla 4: la fecha **prometida** (pactada o del período), no la reprogramada |
| Estadísticas | «Vencida hasta 30 días» | MD-139: «En mora hasta 30 días» |
| Estadísticas | Sin enlace en «Faltantes y rechazos» ni en «Clientes» | Regla 10: los dos llevan a la lista de contratos |
| Resultados del mes | El título dice el mes fijo y «Ventas» suma `e.monto` (total de la entrega) | El mes actual y el mismo cálculo del indicador 3 (Σ `monto_pagar`, que es lo mismo que el total de la entrega) |

## Pruebas

- `test_com_cns_est.py` (`ComCnsEstServicioTests`): una por regla (1 a 11): el alcance del Vendedor y el filtro del Gerente; cada filtro y su
  validación (366 días, fin futuro, invernadero ajeno); cada indicador con datos que lo distinguen (una venta y un suministro; una entrega
  reprogramada que se concretó en la fecha prometida es «a tiempo»; una solicitud aceptada, anulada y vuelta a aceptar en otro mes; un cobro
  anulado vuelve a contar como deuda; la antigüedad en el día 30, 31, 60 y 61; un detalle con faltante rechazado y otro aceptado; un rechazo
  al recibir; una cancelación con entregas concretadas); el top 10 con empates; que no escribe nada (cuenta de filas y de registros de
  auditoría igual antes y después); sin consultas por fila (`assertNumQueries` igual con 2 y con 20 entregas).
- `test_estadisticas_vistas.py`: permisos (los demás roles, 403); los filtros en la URL; con HTMX y sin JavaScript; los enlaces de la regla 10
  llevan el filtro; el panel del Vendedor muestra «Resultados del mes en curso» y el del Gerente no.

## Para más adelante

- Comparaciones entre períodos, proyecciones y exportación (regla 9 y PCU 15: fuera del caso de uso).
- Un índice para las consultas por fecha de concreción, si hace falta (`docs/temas_abiertos.md`).

## Solo prototipo

- Los datos de ejemplo y la fecha fija; los tres meses del desplegable.
