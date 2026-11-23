# Ronda «Comercial 1» — plan completo

Plan de la ronda que construye el módulo comercial (clientes, vehículos, compra-venta, suministros, cosecha, cámara, envasado,
entregas, solicitudes de revisión, cobranza y estadísticas) sobre el prototipo `docs/prototipos/comercial/` («InfoPonia · Comercial y
cosecha», lo trae el lote C1). Alcance, exclusiones y asientos fuera de la ronda: **D-57**. Procesos diarios: **D-56** (DIA-01).
Transportista del invernadero: **D-55** (MAE-05). Criterio de documentación y tamaño de las tareas: **D-44**. Este archivo lo lee la
persona que planifica; Claude Code lo abre solo para completar la fila de su tarea al cerrar (regla M3).

La ronda va **en paralelo con la del IoT** (que se documenta aparte, `docs/tareas/ronda_iot_1.md`) y **las dos dependen de la ronda
«Producción 1»**: ninguna tarea se programa antes que las tareas de producción que necesita (sección 2).

## 1. Tareas

Cada tarea es un bloque funcional: una sesión de Claude Code y un PR (D-44). «Por escribir» = su archivo todavía no está en el repo
(llega en el lote indicado).

**Antes de la ronda** (ya documentadas, fuera de este plan): **MAE-05** (`docs/tareas/maestros/MAE-05-transportista-del-invernadero.md`,
D-55), de la que dependen todas las tareas COM, y **DIA-01** (`docs/tareas/core/DIA-01-proceso-diario.md`, D-56), de la que dependen
las que registran un paso diario.

| ID | Tarea | App | Casos de uso | Depende de | Lote |
|---|---|---|---|---|---|
| COM-01 | App `comercial`, clientes y vehículos | comercial | COM-ALT-CLT, COM-MOD-CLT, COM-BAJ-CLT, COM-CNS-CLT, COM-ALT-VEH, COM-MOD-VEH, COM-BAJ-VEH, COM-CNS-VEH | MAE-05 (y UI-01, NOT-01, hechas). **Ninguna de producción** | C1 |
| COM-02 | Stock maduro y compra-venta (crea `Contrato`, `CompraVenta`, las reservas de stock, `Cosecha` y `StockCosechado`) | comercial (y modelos en produccion, D-59) | PROD-ASG-STK, COM-REG-CVT, COM-CNS-CVT | COM-01, USR-10, **PRD-04** (que ya incluye INV-02 e INV-03) | C2 |
| COM-03a | Suministros: pactar y consultar | comercial | COM-PCT-SUM, COM-CNS-SUM | COM-02 | C3 (partida en C5b) |
| COM-03b | Suministros: modificar, rescindir, dejar sin efecto y pre-reservar | comercial (y los orígenes de alertas en maestros, D-62) | COM-MOD-SUM, COM-RSC-SUM y COM-ANL-RSC (con el paso diario 35), PROD-PRR-SUM (paso diario 40, D-56) | COM-03a, DIA-01, MAE-02d | C3 (partida en C5b) |
| COM-04a | Cosechas: núcleo en produccion; planificar, modificar, concretar y cancelar | comercial y produccion (todo el núcleo físico, D-64, también el de la concreción de una entrega, D-68 punto 3) | PROD-PNF-CSC, PROD-MOD-CSC, PROD-CNC-CSC, PROD-CNL-ORD (cosechas) | COM-03b | C4 (partida en C5b) |
| COM-04b | Cámara: asignación, vencimiento y merma en cámara | comercial (y un parámetro en maestros) | PROD-ASG-CAM (con el paso diario 25), PROD-VNC-CAM (paso diario 20), PROD-REG-MRM (partida en cámara: extensiones 4a y 10c) | COM-04a | C4 (partida en C5b) |
| COM-04c | Faltante y enlace del cliente | comercial (y piezas de core) | COM-DCD-FLT (con el paso diario 27) | COM-04b | C4 (partida en C5b) |
| COM-05a1 | Entregas: modelo, planificación automática (paso diario 50) y cancelación incluida (D-66) | comercial | COM-PNF-ENT (paso diario 50), PROD-CNL-ORD (la «Cancelación de una entrega», incluida), la lista de entregas | COM-04c, MAE-02d | C5a (partida en C5b) |
| COM-05a2 | Envasado y las entregas en el panel, las fichas y los vehículos | comercial (y la restricción de `ReservaInsumo` y el núcleo de reservas en produccion) | PROD-PNF-ENV (y la postcondición h de COM-PNF-ENT) | COM-05a1 | C5a (partida en C5b) |
| COM-05b | Asignar transportista y cancelar la compra-venta | comercial | COM-ASG-TRP, COM-CNL-CVT (con la cancelación de sus cosechas y entregas, PROD-CNL-ORD incluida) | COM-05a2 | C5b |
| COM-06a | Ruta y concreción de entregas (crea `PagoCliente`, `IntentoFallido` y la discrepancia, D-68) | comercial | COM-INI-RUT, COM-CNC-ENT (con el retiro y el intento fallido), COM-FIN-RUT, PROD-VNC-CAM (3b) | COM-05b (y la sección 10 de `docs/api/produccion.md`, que hace COM-04a) | C6 |
| COM-06b | Confirmación del cliente: el enlace de confirmación, las quejas y la entrega no reconocida | comercial | COM-CNF-ENT, COM-ATN-ENR (y el enlace de la postcondición l de COM-CNC-ENT) | COM-06a | C6 |
| COM-07a | Solicitudes de revisión: evaluar, resolver, anular y consultar (crea `Anulacion`, D-69) | comercial | COM-EVL-DSC, COM-RSV-QJA, COM-ANL-SRV, COM-CNS-SRV | COM-06b (y la sección 11 de `docs/api/produccion.md`, que hace COM-04a) | C7 |
| COM-07b | Resolución del suministro por incumplimientos | comercial | COM-RSV-SUM (paso diario 33, D-69), PROD-CNL-ORD (cosechas y entregas, incluida) | COM-07a | C7 |
| COM-08a | Cobro de suministros y mora (crea `LineaPago`, D-94) | comercial | COM-REG-CBR, COM-VNC-PAG (paso diario 30) | COM-07b | C8 |
| COM-08b | Anular un cobro y cobrar lo entregado al cancelar una compra-venta | comercial | COM-ANL-CBR, COM-CNL-CVT (extensión 6a) | COM-08a | C8 |
| COM-08c | Estadísticas comerciales y «Resultados del mes en curso» | comercial | COM-CNS-EST | COM-08b (puede ir en paralelo con ella: sin migraciones) | C8 |

Son 43 casos de uso (41 más COM-RSC-SUM y COM-ANL-RSC, del 21/11/2026) (PROD-CNL-ORD se reparte entre COM-04a, COM-05a1 y COM-05b).

**COM-03, COM-04 y COM-05a se partieron (D-67, punto 2, 22/11/2026), sin cambiar ninguna decisión.** Cada parte es una sesión y un PR. En los
documentos escritos antes, los nombres se leen así:

| Nombre viejo | Qué es de cada parte |
|---|---|
| «COM-03» | **COM-03a**: el modelo del suministro (todas sus tablas menos `AlertaComercial`), pactar, el calendario y el precio, la consulta y lo que completa a COM-01 y COM-02 (clientes, baja de variedad, traspaso). **COM-03b**: modificar, rescindir, dejar sin efecto, la pre-reserva y los pasos 35 y 40, `AlertaComercial` y la alerta «período sin cobertura completa», los orígenes de `maestros`, y lo de la consulta que muestra todo eso |
| «COM-04» | **COM-04a**: todo lo que COM-04 escribe en `produccion` (`docs/api/produccion.md`, sección 8, también las funciones de cámara), `MovimientoStock`, el origen de la cosecha, las cosechas (planificar, modificar, concretar, cancelar), el camino de faltante **sin** enlace. **COM-04b**: PROD-ASG-CAM y el paso 25, PROD-VNC-CAM y el paso 20, la merma en cámara, el recorte, `AlertaComercial.partida`, el parámetro de aviso, la pestaña «Cámara». **COM-04c**: `EnlaceCliente`, `core/enlaces.py`, el enlace del camino de faltante y su anulación, COM-DCD-FLT y el paso 27 |
| «COM-05a» | **COM-05a1**: `Entrega` y `DetalleEntrega`, COM-PNF-ENT con el paso 50 (menos el aviso de envasado), la cancelación incluida, los disparadores en las tareas anteriores, la lista de entregas y lo que protege a las entregas (logística, baja del transportista, reglas de los vehículos, cierre de una rescisión). **COM-05a2**: PROD-PNF-ENV, la restricción de `ReservaInsumo` y el núcleo de reservas en `produccion`, el aviso de envasado, el panel, las fichas de los contratos y las pantallas de vehículos |
| «COM-07» (de antes del lote C7; D-69, punto 1) | **COM-07a**: COM-EVL-DSC, COM-RSV-QJA, COM-ANL-SRV, COM-CNS-SRV, `Anulacion`, la aplicación de la indemnización, el contador de incumplimientos, la bitácora, la pestaña, la ficha y el grupo del panel. **COM-07b**: COM-RSV-SUM, el paso 33, la alerta «suministro resuelto» y «Dar por atendida». **Lo de `produccion`** que nombraban «COM-07» (el tipo de bitácora `incumplimiento_de_clausula`) es de **COM-04a** (D-69, punto 3) |
| «COM-05» (de antes del lote C5a) | Primero la tabla de la nota de abajo (COM-05a o COM-05b) y, si es COM-05a, esta |
| «COM-08» (de antes del lote C8; D-94, punto 1) | **COM-08a**: COM-REG-CBR, COM-VNC-PAG y el paso 30, `LineaPago` (R154), lo nuevo de `PagoCliente` y la mora en `Entrega`, «pagada» en `estado_de_pago`, la alerta «pago en mora», la pestaña «Cobranza», el grupo «Cobranza» del panel y lo que dejaron las anteriores sobre una entrega pagada (solicitudes, entrega no reconocida, fichas del cliente y del suministro). **COM-08b**: COM-ANL-CBR (`Anulacion.pago`, el cobro que corrige uno anulado) y la extensión 6a de COM-CNL-CVT. **COM-08c**: COM-CNS-EST y «Resultados del mes en curso» |
| «COM-06» (de antes del lote C6; D-68, punto 1) | **COM-06a**: COM-INI-RUT, COM-CNC-ENT (menos el enlace), COM-FIN-RUT, `transportista_en_ruta`, PROD-VNC-CAM 3b, la cámara y el contrato al concretar, `PagoCliente`, `IntentoFallido`, `SolicitudRevision` y la discrepancia, «Concretar retiro», las entregas sin cobrar en las fichas. **COM-06b**: el enlace de confirmación (tipo `confirmacion_entrega` y el correo de la concreción), COM-CNF-ENT, `Queja`, COM-ATN-ENR y su resultado (MD-137), las quejas en las fichas. **Lo de `produccion`** que nombraban «COM-06» (la causa «daño en la entrega», la merma y el consumo de la entrega, el egreso y la devolución de la cámara) es de **COM-04a** (D-68, punto 3) |

**COM-05 se partió en dos (D-66, punto 1, 22/11/2026).** En los documentos escritos antes, «COM-05» se lee así: lo de `Entrega` y su
planificación, el envasado, la cancelación de una entrega sin pantalla, la logística, la baja del transportista, los vehículos, las fichas, el
panel y lo de cámara es de **COM-05a**; COM-ASG-TRP, COM-CNL-CVT (y el enlace de decisión que anula) y el enlace de la alerta «entrega sin
transportista» a la asignación, de **COM-05b**. El cron job único **no** es una tarea de esta ronda: es el
disparador «Cuando se arme el cron único» (D-56), al final de toda la implementación.

**Por qué este corte** (D-44: casos de uso que comparten modelo, servicios y pantallas):

- **El orden sigue al dinero y al producto:** primero quién compra y con qué se entrega (COM-01); después lo que crea reservas de stock
  (COM-02 y COM-03); después lo que las cumple (cosecha, COM-04); después lo que mueve el producto (COM-05a, COM-05b y COM-06); y al final lo que
  se reclama y se cobra (COM-07 y COM-08). Cada tarea se prueba con lo que dejaron las anteriores.
- **Suministros antes que cosecha:** la asignación de cámara (PROD-ASG-CAM) y la cosecha eligen entre detalles de venta **y** períodos
  de suministro (MD-127). Si el suministro llegara después, COM-04 se programaría a medias y habría que reabrirla.
- **PROD-CNL-ORD se reparte por tipo de orden**, como en «Producción 1» (PRD-01 siembras, PRD-02 transiciones): COM-04a suma las cosechas
  y COM-05a1 las entregas y el envasado (solo incluida: la entrega no tiene pantalla de cancelación). COM-CNL-CVT va en COM-05b porque cancela
  reservas, cosechas **y entregas**, y necesita la cancelación de una entrega de COM-05a1.
- **Las partes de COM-03, COM-04 y COM-05a (D-67, punto 2)** siguen el mismo criterio que el corte de COM-05: cada una crea su modelo y lo
  que lo usa, y deja lo de la siguiente marcado «se completa en …». COM-03a es lo que nace al pactar y se consulta; COM-03b, lo que cambia
  después y lo que corre solo cada día. COM-04a junta **todo lo de `produccion`** (una sola migración y un solo PR en esa app) con las cosechas;
  COM-04b, la cámara, que usa ese núcleo; COM-04c, el enlace, que es lo único que necesita piezas nuevas de `core`. COM-05a1 es la entrega y lo
  que protege su integridad; COM-05a2, el envasado (el único que toca `produccion`) y las pantallas que solo muestran entregas. Los estados de
  paso que quedan entre las partes están en `docs/temas_abiertos.md` («Abiertos desde el lote C5b»): ninguno rompe datos.
- **COM-06 en dos (D-68, punto 1):** COM-06a es lo que pasa en la calle (la ruta y la concreción, con todo lo que la concreción crea, también la
  discrepancia y el pago de la venta); COM-06b, lo que responde el cliente después y lo que atiende el Gerente. El enlace va en COM-06b, que
  tiene la página que lo abre (como COM-04a y COM-04c con el faltante).
- **COM-05 en dos (D-66, punto 1):** COM-05a crea `Entrega` y todo lo que la lee o la cancela sin que decida una persona; COM-05b, lo que una
  persona hace sobre una entrega que ya existe (asignarle transportista) o sobre la venta (cancelarla). La cancelación sin pantalla va en
  COM-05a para que, entre las dos tareas, una entrega no quede vacía «a realizar» después de un vencimiento en cámara.
- **COM-DCD-FLT va con la cosecha (COM-04):** lo habilitan PROD-CNC-CSC (13a), PROD-REG-MRM (10c) y PROD-CNL-ORD (8c); antes no hay
  ningún detalle «pendiente de decisión del cliente».
- **COM-07 en dos (D-69, punto 1):** COM-07a es lo que decide el Gerente (evaluar, resolver, anular y consultar las solicitudes); COM-07b, lo
  que hace InfoPonia cuando una aceptación supera la tolerancia (deshacer lo pendiente del contrato, con su paso diario). Entre las dos, un
  contrato que supera la tolerancia queda «vigente» hasta que el paso 33 de COM-07b lo resuelve: es la falla que el caso de uso ya prevé.
- **COM-08 en tres (D-94, punto 1):** COM-08a es lo que crea el cobro y la mora (y lo que sin un cobro real no se puede probar); COM-08b, lo
  que lo deshace (la anulación) y el único cobro que nace de otro caso de uso (cancelar una venta con entregas concretadas); COM-08c, lo que
  solo lee. Entre COM-08a y COM-08b, un cobro mal registrado no se puede anular: no rompe datos (`docs/temas_abiertos.md`, «Abiertos desde
  el lote C8»).
- **COM-RSV-SUM va con las solicitudes (COM-07b, después de COM-07a):** lo disparan COM-EVL-DSC y COM-RSV-QJA al aceptar el incumplimiento que agota la
  tolerancia.
- **Tamaño:** COM-02 tiene tres casos de uso, pero PROD-ASG-STK y COM-REG-CVT son de los más grandes del sistema y crean el núcleo del
  modelo (D-44: «un caso de uso grande con sus pantallas»). Si al escribir su lote resulta demasiado grande, se parte con una decisión.
- **Reglas que se completan después.** Algunas reglas de un caso de uso dependen de clases que crea una tarea posterior (por ejemplo,
  COM-BAJ-CLT informa las entregas sin cobrar, que existen desde COM-05a). La tarea que crea la clase completa la regla y la prueba; el
  extracto marca cada una con «Se completa en COM-NN» y el disparador queda en `docs/disparadores.md`. Es el mismo criterio que la
  precondición f de PROD-BAJ-VAR, que espera a `comercial`.

## 2. Orden, paralelismo y dependencias de producción

### Estado al 21/11/2026 (verificado en `main`, PR #42)

Hechas y mergeadas: UI-01, NOT-01, MAE-03, MAE-04, CON-01 e INV-01. Sin empezar: INV-02, INV-03, PRD-01 a PRD-04 (la app `produccion`
sigue vacía), y también MAE-05, DIA-01, USR-10 y MAE-02c.

### Qué necesita cada tarea de producción

| Tarea | Qué usa de producción (funcional) | Depende de |
|---|---|---|
| COM-01 | Nada. Usa `Direccion`, `Localidad` y Georef (MAE-01), `Transportista` (`core`) y los puntos de MAE-05 | — |
| COM-02 | Lotes en Maduración y su fecha máxima de cosecha (PRD-02: `fecha_de_entrada_a_maduracion`, `fecha_maxima_de_cosecha`), la bandeja del Capataz y `ordenes_del_capataz` (PRD-01, D-53: la cosecha automática tiene Capataz), el peso y la postcosecha de la variedad (INV-03) y la condición 1 de «plantas comprometidas» de `aplicar_merma` (PRD-02, PRD-03) | **PRD-04** (ver abajo) |
| COM-03a | Lo mismo que COM-02 (el stock maduro de los períodos de la ventana) | por COM-02 |
| COM-03b | Lo mismo (pre-reserva sobre stock maduro) y el mecanismo del proceso diario | por COM-03a; DIA-01; MAE-02d (no es de producción: el enlace de las alertas) |
| COM-04a | La merma de PRD-03 (`aplicar_merma`, bitácora), `cancelar_orden_incluida` (PRD-01, PRD-02), la lista de órdenes y la bandeja con `TIPOS_DE_PRODUCCION` (PRD-01, D-67) y el Inicio del Agrónomo (PRD-04) | por COM-02 |
| COM-04b | `registrar_pestana_de_invernadero` (PRD-01, pestaña «Cámara»), la pantalla de merma (PRD-03) y el núcleo de cámara de COM-04a | por COM-04a |
| COM-04c | Nada nuevo de producción | por COM-04b |
| COM-05a1 | `cancelar_orden_incluida` para cualquier tipo, los registrantes de reservas y el impedimento de baja (PRD-01, D-67) | por COM-04c |
| COM-05a2 | Los envases como insumos con stock (INV-02: `disponible_para_planificar`; la categoría «Envases» ya existe desde INV-01), `ReservaInsumo` (PRD-01) | por COM-05a1 |
| COM-05b | Lo que deja COM-05a2 | por COM-05a2 |
| COM-06a | La sección 10 de `docs/api/produccion.md` (la hace COM-04a, D-68 punto 3; usa `registrar_salida_por_consumo` de INV-02 para los envases) | por COM-05b |
| COM-06b | Lo que dejan las anteriores | por COM-06a |
| COM-07a | La sección 11 de `docs/api/produccion.md` (los tipos de bitácora y `registrar_evento_de_contrato`; la hace COM-04a, D-69 punto 3) | por COM-06b |
| COM-07b y COM-08a a COM-08c | Lo que dejan las anteriores (COM-07b usa `cancelar_cosecha_incluida` y `crear_partida` de COM-04a) | por COM-07a |

**Por qué COM-02 espera a PRD-04 y no solo a PRD-02:** funcionalmente alcanzaría con PRD-02, pero COM-02 agrega un modelo y una
migración en `produccion` (`Cosecha`, hija de `OrdenTrabajo` con `ConCapataz`, D-50 y D-53), suma la cosecha a `ordenes_del_capataz` y
toca la condición 1 de la alerta de plantas comprometidas. Hacerlo mientras PRD-03 o PRD-04 están abiertas en la misma app es el choque
de migraciones de `docs/patrones/trabajo_en_paralelo.md` («Migraciones»), sin ninguna ganancia: las cuatro de producción son una cadena
y COM-04 las necesita todas. Regla simple: **desde COM-02, la ronda empieza con `produccion` completa y mergeada.**

### Diagrama

```
MAE-05 ──► COM-01 ──────────────────────────────────────────────┐
                                                                ▼
INV-02 ► INV-03 ► PRD-01 ► PRD-02 ► PRD-03 ► PRD-04 ──────────► COM-02 ► COM-03a ► COM-03b ► COM-04a ► COM-04b ► COM-04c ►
                                                                ► COM-05a1 ► COM-05a2 ► COM-05b ► COM-06a ► COM-06b ► COM-07a ► COM-07b ► COM-08a ► COM-08b ► COM-08c
DIA-01 (antes de INV-02) ─────────────────────────────────────────────────────►┘ (COM-03b, COM-04b, COM-04c, COM-05a1, COM-07b y COM-08a registran pasos)
USR-10 ────────────────────────────────────────────────────────►┘
MAE-02d ──────────────────────────────────────────────────────────────────────►┘ (COM-03b; también IOT-04)
                                     ronda IoT (en paralelo con COM-02 a COM-08c)
```

- **Puede arrancar ya:** MAE-05 (no depende de producción). COM-01 arranca cuando MAE-05 está mergeada; tampoco depende de producción,
  así que puede hacerse mientras se termina «Producción 1» si hay un carril libre (decisión de ustedes).
- **USR-10** (D-54) va antes de COM-02: COM-REG-CVT envía el comprobante por correo (postcondición h); después, COM-PCT-SUM, COM-DCD-FLT,
  COM-CNF-ENT y COM-VNC-PAG envían comprobantes, enlaces y avisos.
- **COM-02 a COM-08 son una cadena** (cada una usa lo que crea la anterior), también sus partes (COM-03a a COM-08b): no se reparten en
  paralelo entre sí. La única excepción es COM-08c, que solo lee y no tiene migraciones: puede ir en paralelo con COM-08b (D-94, punto 1).
- **Reparto en dos carriles** (lo deciden ustedes): un carril con comercial y otro con el IoT, después de «Producción 1». Los puntos donde
  se tocan están en la sección 5.

## 3. Casos de uso de la ronda → tarea

Fuentes (versión vigente de cada uno): «CU extendidos» y los documentos de la carpeta de Drive «InfoPonia · Comercial · Análisis» (un
documento por caso de uso nuevo o reescrito el 20 y el 21/11/2026, con los cambios de PCU, secciones 1 a 16). Para los extractos del
modelo: «MD · Cambios para el modelo de dominio (comercial)» (MD-114 a MD-139), «GLO · Cambios para el Glosario (comercial)», el modelo
de dominio (ronda 22) y «Contratos de operación del sistema». El extracto de cada caso de uso va en `docs/casos_de_uso/comercial/<tema>.md`
(o `produccion/` para los PROD-*) y se entrega con el lote de su tarea.

| Caso de uso | Nombre | Versión (fuente) | Tarea | Extracto |
|---|---|---|---|---|
| COM-ALT/MOD/BAJ/CNS-CLT | ABM de Cliente (alto nivel) | v0.1 (Drive) | COM-01 | C1 (`comercial/clientes.md`) |
| COM-ALT/MOD/BAJ/CNS-VEH | ABM de Vehículo (alto nivel) | v0.1 (Drive) | COM-01 | C1 (`comercial/vehiculos.md`) |
| PROD-ASG-STK | Asignar Stock Maduro | 0.3 (CU extendidos) más PCU 7 y 9 | COM-02 | C2 (`produccion/stock_maduro.md`) |
| COM-REG-CVT | Registrar Compra-venta | 0.3 (CU extendidos) | COM-02 | C2 (`comercial/compra_venta.md`) |
| COM-CNS-CVT | Consultar Compra-venta (alto nivel) | v0.1 (Drive, consultas comerciales) | COM-02 | C2 (`comercial/compra_venta.md`) |
| COM-PCT-SUM | Pactar Suministro | 0.3 (Drive) más PCU 9 y 16 | COM-03a | C3 (`comercial/suministro.md`) |
| COM-MOD-SUM | Modificar Suministro | 0.1 (Drive) más PCU 16 | COM-03b | C3 (`comercial/suministro.md`) |
| COM-CNS-SUM | Consultar Suministro (alto nivel) | v0.1 (Drive) | COM-03a (y lo que completa COM-03b) | C3 (`comercial/suministro.md`) |
| COM-RSC-SUM | Rescindir Suministro | 0.1 (nuevo, en el repo; falta pasarlo a Drive) | COM-03b | C3 (`comercial/suministro.md`) |
| COM-ANL-RSC | Dejar sin Efecto la Rescisión (alto nivel) | 0.1 (nuevo, ídem) | COM-03b | C3 (`comercial/suministro.md`) |
| PROD-PRR-SUM | Pre-reservar Período de Suministro | 0.1 (Drive) | COM-03b | C3 (`produccion/pre_reserva.md`) |
| PROD-PNF-CSC | Planificar Cosecha | 0.4 (CU extendidos) | COM-04a | C4 (`produccion/cosecha.md`) |
| PROD-MOD-CSC | Modificar Cosecha | 0.1 (Drive) | COM-04a | C4 |
| PROD-CNC-CSC | Concretar Cosecha | 0.4 (CU extendidos) | COM-04a | C4 |
| PROD-CNL-ORD | Cancelar Orden (cosechas) | 0.1 (CU extendidos) más PCU 7 | COM-04a | C4 (completa `produccion/cancelar_orden.md`) |
| PROD-ASG-CAM | Asignar Stock de Cámara | 0.1 (CU extendidos) más PCU 6 y 7 | COM-04b | C4 (`produccion/camara.md`) |
| PROD-VNC-CAM | Vencer Partidas en Cámara | 0.1 (Drive) | COM-04b | C4 (`produccion/camara.md`) |
| PROD-REG-MRM | Registrar Merma (partida en cámara) | 0.5 (CU extendidos) | COM-04b | C4 (completa `produccion/merma.md`) |
| COM-DCD-FLT | Decidir Faltante | 0.1 (CU extendidos) más PCU 7 | COM-04c | C4 (`comercial/faltante.md`) |
| PROD-PNF-ENV | Planificar Envasado | 0.2 (Drive) | COM-05a2 | C5a (`produccion/envasado.md`) |
| COM-PNF-ENT | Planificar Entrega | 0.3 (Drive) más PCU 8 y 12 | COM-05a1 (la postcondición h, COM-05a2) | C5a (`comercial/entregas.md`) |
| COM-ASG-TRP | Asignar Transportista a Entrega | 0.1 (Drive) más «Transportista en el invernadero» v0.1 | COM-05b | C5b (`comercial/entregas.md`) |
| PROD-CNL-ORD | Cancelar Orden (la «Cancelación de una entrega», incluida) | 0.1 más PCU 7 | COM-05a1 | C5a (completa `cancelar_orden.md`) |
| COM-CNL-CVT | Cancelar Compra-venta | 0.1 (Drive) | COM-05b | C5b (`comercial/compra_venta.md`) |
| COM-INI-RUT | Iniciar Ruta | 0.1 (CU extendidos) más PCU 8 | COM-06a | C6 (`comercial/rutas.md`) |
| COM-CNC-ENT | Concretar Entrega (con el intento fallido, extensión 4a) | 0.4 (CU extendidos) más PCU 6 y 9 | COM-06a (el enlace de la postcondición l, COM-06b) | C6 (`comercial/rutas.md`) |
| COM-FIN-RUT | Finalizar Ruta (alto nivel) | 0.1 (Drive) | COM-06a | C6 (`comercial/rutas.md`) |
| COM-CNF-ENT | Confirmar Entrega | 0.2 (CU extendidos) más PCU 16 | COM-06b | C6 (`comercial/confirmacion.md`) |
| COM-ATN-ENR | Atender Entrega No Reconocida (alto nivel) | 0.1 (Drive) | COM-06b | C6 (`comercial/confirmacion.md`) |
| COM-EVL-DSC | Evaluar Discrepancia | 0.2 (CU extendidos) más MD-115 (D-69, punto 2) | COM-07a | C7 (`comercial/solicitudes.md`) |
| COM-RSV-QJA | Resolver Queja | 0.2 (Drive) | COM-07a | C7 (`comercial/solicitudes.md`) |
| COM-RSV-SUM | Resolver Suministro por Incumplimientos | 0.1 (CU extendidos) | COM-07b | C7 (`comercial/resolucion.md`; el plan decía `suministro.md`, ver `docs/temas_abiertos.md`) |
| COM-ANL-SRV | Anular Resolución de Solicitud | 0.1 (Drive) | COM-07a | C7 (`comercial/solicitudes.md`) |
| COM-CNS-SRV | Consultar Solicitudes de Revisión (alto nivel) | 0.1 (Drive) | COM-07a | C7 (`comercial/solicitudes.md`) |
| COM-REG-CBR | Registrar Cobro de Suministro | 0.2 (Drive) más PCU 9 y 14 y MD-139 | COM-08a (la fecha de 7a de COM-ANL-CBR, COM-08b) | C8 (`comercial/cobranza.md`) |
| COM-ANL-CBR | Anular Cobro | 0.1 (Drive) | COM-08b | C8 (`comercial/cobranza.md`) |
| COM-VNC-PAG | Vencer Pagos de Suministro (alto nivel) | 0.1 (Drive) más MD-139 | COM-08a | C8 (`comercial/cobranza.md`) |
| COM-CNS-EST | Consultar Estadísticas Comerciales (alto nivel) | 0.1 (Drive) | COM-08c | C8 (`comercial/estadisticas.md`) |

**Casos de uso sin extender (L9):** ninguno del alcance. Los de «CUs que faltan extender» que son de este módulo (PROD-ASG-STK,
asignación de cámara, envasado, Iniciar y Finalizar Ruta, Decidir Faltante, Cancelar Orden, Registrar Cobro, Resolver Suministro,
Cancelar Compra-venta, Asignar Transportista, Modificar Suministro y Validar o Modificar Cosecha) ya están especificados: los
extendidos, en «CU extendidos» o en su documento de Drive; los de alto nivel (ABM de Cliente y de Vehículo, COM-FIN-RUT, COM-ATN-ENR,
COM-VNC-PAG y las consultas), como decidió PCU, secciones 5, 8, 10, 13, 14 y 15. Quedan fuera, por ser de otro módulo: CU-17 Registrar
Asiento (contabilidad), los de compras y los del IoT.

**Datos de migración (D-44):** no se prevé ninguno. Las listas cerradas (tipo de vehículo, motivos de cancelación, estados) van como
`TextChoices`, como decidió «Producción 1» para sus catálogos fijos. Los tipos de alerta se registran en `ready()` (D-41), sin migración.

## 4. Pantallas del prototipo → tarea

Las funciones son las del prototipo «InfoPonia · Comercial y cosecha» (`docs/prototipos/comercial/README.md`, lote C1). Para cada
pantalla vale la **versión final**: las sobrescrituras del final del archivo mandan sobre la primera definición (el `README.md` dice la
línea de cada una).

| Pantalla (funciones) | Tarea |
|---|---|
| Ficha del invernadero: bloque «Logística» (`VIEWS.invfic`, `logistica`, `MODALS.tragregar`, `MODALS.trquitar`) | MAE-05 (con su propio prototipo, `docs/prototipos/produccion/logistica_transportista.html`); COM-01 registra el vehículo y la situación; COM-05, las entregas a realizar |
| Panel de control del Gerente: «Personal por asignar» (`secPersonal`) | MAE-05 |
| Menú: entrada «Comercial» para el Gerente y el Vendedor (`NAV.ger`, `NAV.ven` de «Integración») | COM-01 |
| Comercial · Clientes: lista, ficha, alta, modificación, baja y reactivación (`tabClientes`, `VIEWS.cli`, `VIEWS.cliform`, `dirForm`, `dirAdd`, `MODALS.bajacli`, `ACT.reactcli`) | COM-01 |
| Comercial · Vehículos (solo el Gerente) (`tabVehiculos`, `VIEWS.vehform`, `MODALS.bajaveh`, `ACT.reactveh`) | COM-01 |
| Comercial · Contratos · Compra-venta: lista, ficha y alta (`tabContratos` con `cv`, `VIEWS.cv`, `VIEWS.cvnew`, `cliPick`, `retiroFld`) | COM-02 |
| Comercial · Contratos · Suministro: lista, ficha, pactar, modificar e historial (`tabContratos` con `sum`, `VIEWS.sum`, `VIEWS.sumnew`, `VIEWS.summod`, `MODALS.sumhist`) | COM-03a (lista, ficha, pactar) y COM-03b (modificar, historial, rescindir) |
| Producción del Agrónomo · Órdenes de trabajo con las cosechas; planificar, modificar y cancelar cosecha (`VIEWS.prod`, `ordenesTab`, `tabCosechas`, `MODALS['nueva-orden']`, `VIEWS.cscnew`, `VIEWS.cscmod`, `MODALS.cnlcsc`) | COM-04a (comparar con lo que deje PRD-01 en la misma pantalla, sección 5) |
| Capataz (celular): bandeja con cosechas y Concretar Cosecha (`VIEWS.caphome`, `VIEWS.capcsc`, `capcscCalc`) | COM-04a |
| Ficha del invernadero · pestaña «Cámara» (`camaraTab`, `tabCamara`) | COM-04b (con `registrar_pestana_de_invernadero`) |
| Portal del cliente · Decidir Faltante (`VIEWS.dcd`) | COM-04c |
| Configuración: «Aviso de vencimiento de cámara» (`VIEWS.cfg`, MD-134) | COM-04b |
| Registrar merma: opción «Pérdida en cámara» (la pantalla de PRD-03, `VIEWS.merma` del prototipo de producción) y la página de la merma en cámara (no está en el prototipo comercial, D-61) | COM-04b |
| Producción · Envasado (`tabEnvasado`, `VIEWS.env`) | COM-05a2 |
| Comercial · Entregas (`tabEntregas`, la lista, sin asignar) | COM-05a1 |
| Asignar transportista (`VIEWS.asg`, `candidatos`) y las acciones de la lista; cancelar compra-venta (`VIEWS.cvcancel`) | COM-05b |
| Transportista (celular): hoja de ruta, Iniciar Ruta, Concretar Entrega, intento fallido y Finalizar Ruta (`VIEWS.ruta`, `MODALS.inirut`, `VIEWS.cncent`, `cncentCalc`, `MODALS.fallo`, `MODALS.finrut`) | COM-06a (y «Concretar retiro» del Vendedor) |
| Portal del cliente · Confirmar Entrega (`VIEWS.cnf`) | COM-06b |
| Atender entrega no reconocida (`VIEWS.atnenr`) | COM-06b |
| Comercial · Solicitudes de revisión: ficha, evaluar, resolver y anular (`tabSolicitudes`, `VIEWS.srv`, `srvCalc`, `MODALS.anlsrv`) | COM-07a |
| Ficha del suministro: la sección «Solicitudes de revisión» (`VIEWS.sum`, `ccard('sol', …)`) | COM-07a |
| Ficha y lista del suministro: la resolución por incumplimientos y «Dar por atendida» (`VIEWS.sum`, `tabContratos`; el prototipo no la tiene completa) | COM-07b |
| Comercial · Cobranza: por cobrar, registrar cobro y cobros registrados (`tabCobranza`, `cobGroups`, `VIEWS.cobro`) | COM-08a |
| Comercial · Cobranza: anular cobro (`MODALS.anlcbr`) y la fecha del cobro anulado en el registro | COM-08b |
| Comercial · Estadísticas (pestaña, no entrada del menú) (`VIEWS.est`, la versión de `VIEWS.com` que la agrega como pestaña) | COM-08c |
| Panel de control del Gerente y del Vendedor: Entregas, Solicitudes (solo el Gerente), Cobranza y «Resultados del mes en curso» (solo el Vendedor) (`secComercial`, `secMes`) | Cada grupo lo agrega su tarea: Entregas en COM-05a2, Solicitudes en COM-07a, Cobranza en COM-08a y Resultados en COM-08c |
| Panel de control del Agrónomo: cosechas y envasado (`secCosecha`) | COM-04a (cosechas), COM-04b (cámara) y COM-05a2 (envasado) |

Lo marcado «Ya existe» (`mk-ext`) o «IoT» (`mk-iot`) en el prototipo no lo hace esta ronda: está para mostrar dónde va lo nuevo.

## 5. Pantallas y puntos compartidos (con lo existente y con el IoT)

**Criterio (decisión del 21/11/2026):** antes de documentar las pantallas de cada tarea, se compara lo implementado **en ese momento** en el
panel de control, la ficha del invernadero, el menú y la campana con lo que la tarea agrega, para no chocar contenido. Lo hace quien
escribe el lote de la tarea (no Claude Code al programar) y lo deja escrito en la sección «Pantallas» de la tarea. El IoT hace lo mismo con
las suyas. Todo se resuelve con los puntos de extensión que ya existen (regla A4 de D-37); si hiciera falta uno nuevo, lo declara la
tarea con su contrato en `docs/api/`.

| Punto compartido | Cómo se resuelve hoy (código mergeado o tarea documentada) | Qué agrega comercial | Qué cuidar con el IoT |
|---|---|---|---|
| **Panel de control** (`core/templates/core/inicio.html`, título «Panel de control») | Cada app suma secciones con `core.extensiones.registrar_seccion_de_inicio` (D-43); `core` las muestra **en orden de registro**, que es el de `INSTALLED_APPS`. Hoy: «Personal por asignar» (`maestros`, Gerente), que MAE-05 amplía con los transportistas sin invernadero | Una sección por rol y grupo: Entregas, Solicitudes (Gerente), Cobranza y «Resultados del mes en curso» (Vendedor); cosechas y envasado (Agrónomo); hoja de ruta (Transportista) | Las de `iot` (nivel 7) aparecen después de las de `comercial` (nivel 6), porque `INSTALLED_APPS` sigue el orden de los niveles (D-37). Si hiciera falta otro orden, lo decide la tarea que agregue la segunda sección al mismo rol |
| **Ficha del invernadero** | Pestañas por `maestros.extensiones.registrar_pestana_de_invernadero` (lo crea PRD-01; hoy no existe en el código), en orden de registro. «Equipo» y «Logística» (MAE-05) son de `maestros` | El vehículo, la situación y las entregas de cada transportista en «Logística» (`registrar_logistica_de_transportista`, un solo registrante: COM-01 lo crea y COM-05a1 lo completa); pestaña «Cámara» (COM-04b) | El estado del sistema IoT va en «Ubicación» (PROD-CNS-INV, regla 3) y sus pestañas por el mismo punto |
| **Menú** | `core.menu.registrar_entrada(entrada, roles, despues_de)` desde `ready()` | «Comercial» (Gerente y Vendedor), después de «Producción»; Estadísticas es una pestaña de Comercial, no una entrada | «IoT» con su propio `despues_de`; si los dos usan el mismo, queda primero el que se registra primero |
| **Campana** | Las alertas de `maestros.Alerta` salen solas (`items_de_campana`, NOT-01); las notificaciones, con `core.notificaciones` (D-42) | Sus tipos de alerta con `registrar_tipo_de_alerta`, el vínculo con su origen en `AlertaComercial` (D-63) y el enlace a su pantalla con `registrar_enlace_de_alerta` (D-62). La primera alerta comercial es «período sin cobertura completa» (MD-133, COM-03b) | **Resuelto en C3 (D-62):** el enlace de cada alerta lo da un punto de extensión de `maestros` por código de tipo y según el usuario; los orígenes de C5 suman `entrega`, `suministro`, `detalle_suministro` y `stock_cosechado`. El IoT usa el mismo punto para sus alertas. **El punto lo crea MAE-02d** (MAE-02c se programó sin él: D-62, tercera enmienda); COM-03b e IOT-04 dependen de ella |
| **Proceso diario** | `core/procesos.py` y el comando `proceso_diario` (DIA-01, D-56). Cada app registra sus pasos en `ready()` con `registrar_paso_diario` | Pasos 20 (vencer partidas en cámara, COM-04b), 25 (reasignar cámara, COM-04b, D-64), 27 (avisar enlaces vencidos, COM-04c, D-65), 30 (vencer pagos, COM-08a), 33 (resolver suministros con incumplimientos superados, COM-07b, D-69), 35 (cerrar rescisiones, COM-03b), 40 (pre-reservar, COM-03b) y 50 (planificar entregas, COM-05a1). Ninguna tarea crea un cron job | El IoT no usa este proceso (D-56, punto 6): su revisión es cada 5 minutos |
| **Configuración operativa** (`maestros`, MAE-04) | Trece parámetros con migración propia | `dias_aviso_vencimiento_camara` (MD-134), con migración en `maestros` (COM-04b) | El IoT también agrega parámetros: son dos migraciones en `maestros` desde dos ramas. Seguir `docs/patrones/trabajo_en_paralelo.md`, «Migraciones» |
| **Íconos** (`core/templatetags/iconos.py`) | Los que trajo UI-01 | `cart` (menú «Comercial») y `truck` (vehículos), si MAE-05 no agregó este último | Cada ronda suma los suyos; dos ramas que tocan el mismo diccionario chocan en el merge (ver «Qué archivos suelen chocar») |

### Los puntos de MAE-05 que registra `comercial`

| Punto (contrato: `docs/api/extensiones_de_maestros.md`, «Transportistas») | Qué informa | Tarea |
|---|---|---|
| `maestros.extensiones.registrar_logistica_de_transportista` | Vehículo («Camioneta AE123CD · 800 kg») y situación (en ruta, MD-118) | COM-01 |
| ídem (el mismo registrante, completado) | Entregas a realizar y `url_entregas` | COM-05a1 |
| `maestros.extensiones.registrar_impedimento_de_transportista` | `transportista_con_entregas` | COM-05a1 |
| ídem | `transportista_en_ruta` | COM-06a |
| `core.extensiones.registrar_impedimento_de_baja_de_cuenta` | `transportista_en_ruta` | COM-06a |
| `core.extensiones.registrar_efecto_de_baja_de_cuenta` y `registrar_asignaciones_de_cuenta` (D-43) | Las entregas a realizar de un Transportista dado de baja quedan sin transportista, con su alerta (disparador «Cuando exista Entrega», punto 1) | COM-05a1 |

`core.extensiones.registrar_datos_de_cuenta`: lo registra `maestros` (MAE-05) con el invernadero del Transportista y, **además**, `comercial`
(COM-01) con su vehículo (decisión del estudiante del 21/11/2026).

## 6. Fuera de la ronda (D-57)

- **Contabilidad:** los asientos y las precondiciones contables (ejercicio vigente, cuentas) de cada caso de uso quedan marcados «Fuera
  de esta ronda · contabilidad» en su extracto, como hizo D-45. Los casos de uso con asiento, al menos: PROD-CNC-CSC, PROD-REG-MRM
  (partida en cámara), PROD-VNC-CAM, COM-CNC-ENT, COM-CNL-CVT, COM-EVL-DSC, COM-RSV-QJA, COM-RSV-SUM, COM-ANL-SRV, COM-REG-CBR y
  COM-ANL-CBR; COM-ATN-ENR deriva al asiento manual (CU-17), que es de contabilidad. La lista exacta la cierra el extracto de cada uno.
- **Mejoras futuras de los casos de uso:** la anulación automática de una concreción y el reingreso a la cámara del producto devuelto
  (PCU 14), las rutas de más de un día (MD-118), la queja registrada por el Vendedor y el reenvío del enlace (pendientes_CU, «Ajustes
  pendientes», punto 5).
- **El cron job:** es el disparador «Cuando se arme el cron único» (D-56), después de esta ronda y de la del IoT.
- **Todo lo «Solo prototipo»** (lista en `docs/prototipos/comercial/README.md`).

## 7. Documentación por lotes (D-44)

| Lote | Contenido | Estado |
|---|---|---|
| C0 | Este plan; D-57 (alcance); las filas de la ronda en `docs/tareas/README.md`; ajustes del IoT en paralelo y temas abiertos; correcciones menores de `estado.md`, `ronda_produccion_1.md`, `CLAUDE.md` (M3) y `docs/README.md` | validado (21/11/2026) |
| C1 | **El prototipo en `docs/prototipos/comercial/` con su `README.md`**; COM-01: su archivo de tarea, `modelo/comercial.md` (Cliente, sus direcciones y Vehículo), los extractos `clientes.md` y `vehiculos.md`, D-58 (direcciones del cliente y API pública de direcciones y CUIT de `maestros`), `api/direcciones.md`, los disparadores que nacen | validado (21/11/2026); revisado con el lote C2 (cambio de zona de una dirección, vehículo en la ficha de la cuenta) |
| C2 | COM-02: archivo de tarea; modelo de `Contrato`, `CompraVenta`, `DetalleVenta`, `ReservaStock`, `DetalleReserva`, `Cosecha` y `StockCosechado`; extractos `produccion/stock_maduro.md` y `comercial/compra_venta.md`; **D-59** (servicios de cosecha y cámara en `comercial`; corrige el paso 20 de D-56); **D-60** (cambio de Vendedor); `patrones/stock_maduro.md` (y la sección `comercial` de `patrones/bloqueos.md`); `api/extensiones_de_produccion.md`; temas abiertos y disparadores de COM-02 | validado (21/11/2026); revisado con el lote C3 (`estado_comprobante` pasa a `Contrato`) |
| C3 | COM-03: archivo de tarea; modelo de `Suministro`, `DetalleSuministro`, las dos cláusulas (MD-124, MD-131) y `AlertaComercial`; extractos `comercial/suministro.md` y `produccion/pre_reserva.md`; patrón de stock, sección 7 (períodos y simulación); **D-61** (las pantallas son una referencia, pedido del estudiante), **D-62** (enlace de las alertas y orígenes nuevos de C5), **D-63** (T-01 y T-02 al repo, y la alerta «período sin cobertura completa»); `api/alertas.md`, sección 8. Revisión de C2. **Agregado:** COM-RSC-SUM y COM-ANL-RSC (rescisión por mutuo acuerdo, pedido del estudiante), con el cambio en el prototipo (versión `1795306795-c806`) | validado (21/11/2026), con la rescisión |
| C4 | COM-04: archivo de tarea; `MovimientoStock`, la bitácora de la cosecha, el origen de la cosecha y las causas de cámara (`produccion`); `EnlaceCliente` y `AlertaComercial.partida` (`comercial`); extractos `produccion/cosecha.md`, `produccion/camara.md`, `comercial/faltante.md` y las secciones «Comercial 1» de `cancelar_orden.md` y `merma.md`; **D-64** (cosecha y cámara en el código; corrige dos restricciones de C2 y una regla de C3) y **D-65** (enlace del cliente); `patrones/enlace_del_cliente.md`; patrón de stock, sección 8; `api/produccion.md`, sección 8; puntos 3 y 4 de `api/extensiones_de_produccion.md`; la pantalla de órdenes compartida con PRD-01 por esos puntos. Revisión de C3 | validado (21/11/2026); falta el lote C5 en adelante |
| C5a | **MAE-02d** (lo que faltaba de D-62, con su tercera enmienda) y las dependencias de COM-03 e IOT-04 en ella; `core/enlaces.py` «solo si no existe» en COM-04; COM-05a: archivo de tarea; `Entrega` y `DetalleEntrega` (`comercial`), el tipo `entrega` y la restricción de `ReservaInsumo` (`produccion`); extractos `comercial/entregas.md`, `produccion/envasado.md` y la sección «entregas» de `cancelar_orden.md`; **D-66**; `api/produccion.md`, sección 9; el campo `envasado` de `extensiones_de_produccion.md`; `patrones/bloqueos.md` («Entregas y envasado»); disparadores de «Cuando exista Entrega» | validado (COM-05a partida en COM-05a1 y COM-05a2 en el lote C5b) |
| C5b | **PRD-01 con los tipos de orden futuros** (D-67, punto 1: los cinco valores del tipo, las listas por tipos permitidos, `cancelar_orden` y `cancelar_orden_incluida`, los registrantes; ajustes en `modelo/produccion.md`, `api/produccion.md` sección 9, COM-02, IOT-07 y sus extractos); **el corte** de COM-03 (03a y 03b), COM-04 (04a, 04b y 04c) y COM-05a (05a1 y 05a2) (D-67, punto 2); COM-05b: archivo de tarea; COM-ASG-TRP y COM-CNL-CVT (extractos en `entregas.md` y `compra_venta.md`; sección nueva de `cancelar_orden.md`); los datos de la cancelación (MD-130); **D-67** | validado (22/11/2026) |
| C6 | **COM-06 partida en COM-06a y COM-06b** (D-68, punto 1): sus dos archivos de tarea; `PagoCliente`, `IntentoFallido`, `SolicitudRevision`, `DiscrepanciaEntrega`, `LineaDiscrepancia` y `Queja`, los campos de la concreción en `Entrega` y `DetalleEntrega`, `AlertaComercial.solicitud` y el enlace de confirmación (`modelo/comercial.md`); extractos `comercial/rutas.md` y `comercial/confirmacion.md`; **la sección 10 de `api/produccion.md` en COM-04a** (D-68, punto 3) y el exceso de envases sin tocar `ReservaInsumo` (punto 2); bloqueos y el patrón del enlace; **D-68** | validado (22/11/2026) |
| C7 | **COM-07 partida en COM-07a y COM-07b** (D-69, punto 1): sus dos archivos de tarea; `Anulacion` (MD-135), la aplicación de la indemnización y el aviso en `SolicitudRevision`, `Suministro.solicitud_resolucion` (`modelo/comercial.md`); extractos `comercial/solicitudes.md` y `comercial/resolucion.md`; **la sección 11 de `api/produccion.md` en COM-04a** (D-69, punto 3); MD-115 en COM-EVL-DSC (punto 2); el paso 33 (enmienda D-56); bloqueos; **D-69** | a validar (puntos 1 a 8 validados antes de escribir) |
| C8 | **COM-08 partida en COM-08a, COM-08b y COM-08c** (D-94, punto 1): sus tres archivos de tarea; R154 como `LineaPago` (no `Entrega.pago`, D-94 punto 2), C7 de `PagoCliente` como {xor}, `estado_pago` anulado (MD-136), la mora en `Entrega`, `Anulacion.pago` y `cliente_pago_en_fecha` (MD-135), `PagoCliente.anulacion_corregida` (`modelo/comercial.md`); extractos `comercial/cobranza.md` y `comercial/estadisticas.md`; la extensión 6a en `compra_venta.md`; lo que completa a COM-01 a COM-07a; bloqueos de la cobranza; **D-94**. Además, las correcciones por lo mergeado hasta la PR #57 (D-81, D-83, la regla de interfaz de INV-02, los datos de verificación, `core/enlaces.py`) | validado (23/11/2026; D-94, punto 12 cambiado) |

Un lote se programa recién cuando él y los anteriores están entregados y validados. COM-01 (C1) puede programarse mientras se escriben
los demás; **COM-02 en adelante, cuando la documentación de la ronda esté completa** (como se decidió para PRD-01 el 19/11/2026), porque
el modelo de COM-02 condiciona a todas las que siguen.

## 8. Decisiones tomadas o por confirmar

Las decisiones de comercial tomadas van de D-57 a D-69 (D-55 y D-56 ya se usaron para MAE-05 y DIA-01). Las de abajo con número son de los
lotes C0 a C7; la del lote C8 tomó su número al escribirse (`docs/decisiones/README.md`, «Numeración»): **D-94** (D-80 a D-83 ya eran de IoT y
producción). Si al abrir el PR ya está tomada, se renumera.

| Tema | Decisión o propuesta de trabajo | Lote |
|---|---|---|
| Transportista del invernadero | **D-55** (propuesta): MAE-05. Además, el vehículo del Transportista en la ficha de su cuenta (COM-01, decisión del 21/11/2026) | — |
| Proceso diario | **D-56** (vigente; implementada): DIA-01; cada tarea registra su paso con `registrar_paso_diario` y no crea ningún cron job | — |
| Alcance de la ronda | **D-57** (vigente): sin contabilidad; entran cosecha, cámara y envasado | C0 |
| Direcciones del cliente (R119, restricción C6) | **D-58** (vigente, validada el 21/11/2026): tabla `DireccionCliente` en `comercial`; C6 la garantiza el servicio; `maestros` expone su API de direcciones y de CUIT | C1 |
| **Dónde viven los modelos y los servicios de cosecha y cámara (P5 de TEC)** | **D-59** (vigente): modelos según D-37 (`Cosecha` y `StockCosechado` en `produccion`; `Contrato`, sus detalles y las reservas en `comercial`); todo caso de uso que toca reservas vive en `comercial` (A3); `produccion` declara dos puntos de extensión para leer reservas y detalle de cosechas; el paso diario 20 lo registra `comercial` (corrige D-56, punto 6) | C2 |
| Vínculo de las alertas comerciales con su origen | **D-63** (vigente; T-01): tabla `AlertaComercial` en `comercial`; la alerta «período sin cobertura completa», con su invernadero y sus destinatarios | C3 |
| Invernadero de la alerta «suministro resuelto» | **D-63**, punto 2 (T-02): solo al Gerente; invernadero del primer detalle con reservas | C3 (se programa en COM-07b; D-69, punto 14) |
| `motivoCancelacion` (T-03) | **Cerrado:** ya está en `docs/modelo/produccion.md` (H2, PR #38) | — |
| Enlace de cada alerta en la campana y orígenes nuevos de C5 | **D-62** (vigente): `registrar_enlace_de_alerta` en `maestros`, por código de tipo y según el usuario | C3 |
| Cosecha y cámara en el código (movimientos de stock, núcleo físico, reserva sin contrato, recorte, períodos de un detalle finalizado, cuándo corre la asignación de cámara, alertas de cámara, acciones en pantallas de `produccion`) | **D-64** (vigente) | C4 |
| Enlace del cliente (acceso temporal sin cuenta) | **D-65** (vigente): tabla `EnlaceCliente`, token aleatorio con su resumen, un vigente por venta, correo con `on_commit`, el Vendedor decide si el correo no sale, paso 27, auditoría «cliente mediante enlace» | C4 |
| Las pantallas del prototipo | **D-61** (vigente, pedida por el estudiante): referencia, no especificación; Claude Code las corrige y completa y lo anota en el «Cierre» | C3 |
| Cambio de Vendedor de un invernadero (pendientes_CU, caso 22; MD-46 y MD-60) | **D-60** (vigente): el traspaso es automático, con una regla en lugar de «el Gerente decide contrato por contrato» | C2 |
| Pago «en mora» | MD-139: `pendiente` / `en_mora` / `pagada`; alerta «pago en mora»; «atrasada» para una entrega con la fecha pasada | C5a a C8 (textos; «atrasada» ya en C5a) |
| Corte de COM-08; R154 como `LineaPago`; C7 como {xor}; estado de pago y mora; la alerta «pago en mora» y el paso 30; bloqueos y huella del cobro; el cobro que corrige uno anulado; `Anulacion.pago`; la indemnización por atraso; correos; el cobro al cancelar una venta; las fechas de las estadísticas | **D-94** (aprobada el 23/11/2026; punto 12 cambiado: la cláusula vigente al vencer) | C8 |
| Entregas y envasado en el código (corte de COM-05, modelo, `on_commit`, paso 50, agrupamiento de una venta, reserva de insumo, cancelación de una entrega, alerta, semáforo) | **D-66** (propuesta, a validar) | C5a |
| Enlace de las alertas sobre la MAE-02c de `main` | **D-62, tercera enmienda** (vigente): MAE-02d, ruta `alertas:ir`, `tipos` | C5a |
| Tipos de orden futuros en PRD-01; corte de COM-03, COM-04 y COM-05a; COM-ASG-TRP y COM-CNL-CVT en el código | **D-67** (vigente) | C5b |
| Corte de COM-06; exceso de envases sin cambiar `ReservaInsumo`; lo de `produccion` de las entregas en COM-04a; `PagoCliente` en COM-06a; solicitudes, intentos, montos, vigencia del enlace y resultado de la averiguación en el código | **D-68** (vigente) | C6 |
| Corte de COM-07; MD-115 en COM-EVL-DSC; la bitácora de las solicitudes en COM-04a; la alerta de una solicitud anulada; los bloqueos de COM-ANL-SRV; el paso 33; lo descontado y lo reintegrado; `Anulacion` con la copia; el disparo y la alerta de la resolución | **D-69** (puntos 1 a 8 validados; 9 a 17, a validar) | C7 |
| Terminación anticipada de un suministro por mutuo acuerdo | **COM-RSC-SUM** (decisión del estudiante del 21/11/2026): rescisión bilateral (art. 1076 CCyC) que registra el Gerente; se conservan los períodos de la ventana; sin multa; se puede dejar sin efecto hasta la última entrega (COM-ANL-RSC); motivo en lista cerrada con descripción. Propuesta MD-140 para el modelo | C3 |
| Incumplimientos tolerados | 0..99 al pactar y al modificar; al modificar, nunca menos que los acumulados (PCU 16). Aplicado en `suministro.md` («Cambios ya decididos», punto 1) | C3 |
| Confirmación del cliente | Monto por línea y total de la entrega; precio unitario como dato secundario (PCU 16) | C6 |
| Criterios de interfaz | Buscadores en lugar de desplegables para datos que crecen (clientes, contratos); pasos siguientes bloqueados hasta completar el actual; contadores en rojo; tablas siempre ordenadas; **textos explicativos siempre** («alguien nuevo debe entender el sistema rápidamente»). Van en «Pantallas» de cada tarea | todos **Desde INV-02** (`.claude/rules/interfaz.md`, «Validaciones e interacción HTMX»): nada se valida ni se recalcula mientras se tipea; los `calcular/` de las pantallas de comercial (compra-venta, suministro, asignación, concreción, cobro) corren con un botón («Actualizar», «Ver resumen», «Revisar y registrar») o cuando cambia un **selector**, que redibuja sin validar (`hx-swap="innerHTML show:none"`, `data-sin-envio-en-curso`). Donde un documento anterior diga otra cosa (COM-02 decía un retardo de 350 ms), manda la regla |

## 9. Disparadores existentes que cierra cada tarea

Salen de `docs/disparadores.md`; cada archivo de tarea los trae en «Límites».

| Tarea | Disparadores que cierra |
|---|---|
| COM-01 | «Cuando exista Cliente o CompraVenta» (la dirección de un invernadero nunca la usa un contrato: C6); «Cuando exista Entrega», punto 3, en parte (vehículo y situación). «Cuando exista Cosecha» ya quedó resuelto en el lote C1 (la pantalla de concretar cosecha está en el prototipo comercial): COM-01 no tiene que hacer nada con él |
| COM-02 | «Cuando existan lotes, órdenes de trabajo y contratos», punto 2 (`contratos_abiertos` en la baja de variedad); «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido» (traspaso de contratos al Vendedor y de cosechas al Capataz; termina en COM-03 con los suministros); «Cuando exista Lote, OrdenTrabajo o StockCosechado» (impedimentos de baja del invernadero por cosechas a realizar, si PRD-01 no los cuenta ya); condición 1 de «plantas comprometidas» (`docs/modelo/produccion.md`, «Diferencias», fila 8); «Completan el ABM de cliente» (nace en C1) para compra-ventas; «Cuando exista un caso de uso que planifique… asigne stock», en la parte de la asignación. Nace: «Cuando exista Entrega», punto 4 (para COM-05) |
| COM-03a | «Completan el ABM de cliente», punto 2 (suministros); «Cuando existan lotes, órdenes de trabajo y contratos», punto 2, para suministros; «Cuando exista OrdenTrabajo, MantenimientoIoT, Contrato o Pedido» (traspaso de suministros al Vendedor, D-60). (COM-03b) Nace: «Cuando exista Entrega», punto 5 (finalizar detalle y contrato al concretar el último período, para COM-06) y punto 6 (el cierre de una rescisión espera las entregas a realizar, para COM-05 y COM-06); «Resolución de un contrato con rescisión acordada» (para COM-07) |
| COM-04a | «Cuando exista `produccion` completa», puntos 3 y 5; «Cuando exista Lote, OrdenTrabajo o StockCosechado» (las partidas en la baja del invernadero) |
| COM-04b | «Cuando se retome la cámara de frío (D-45)»; «Cuando exista Lote, OrdenTrabajo o StockCosechado» (la pestaña «Cámara») |
| COM-05a1 | «Cuando exista Entrega», puntos 1, 2 (`transportista_con_entregas`), 3 (entregas a realizar), 4 (venta y período que salen todos de cámara), 6 (el cierre de una rescisión espera las entregas) y 7 (lo que dejó COM-04, salvo el enlace de COM-CNL-CVT y lo de COM-06); «Cuando exista un caso de uso que planifique… o reintente entregas» (excluir invernaderos inactivos); «Completan el ABM de vehículo» (nace en C1; las reglas de MOD y BAJ) |
| COM-05a2 | «Completan el ABM de vehículo» (la columna y la carga de los próximos días en sus pantallas); «Cuando exista Entrega», punto 8 (lo del envasado) |
| COM-05b | «Cuando exista Entrega», punto 7 (COM-CNL-CVT anula el enlace de decisión de la venta, D-65); la regla de COM-ASG-TRP del punto 2 (una entrega del día de un transportista en ruta no se reasigna); punto 8 (lo de COM-05b). Nace: «Cuando exista Entrega», punto 9 (COM-CNL-CVT con entregas concretadas, para COM-06 y COM-08) |
| COM-06a | «Cuando exista Entrega», puntos 2 (en ruta), 5, 7 y 8 (lo de COM-06) y 9 (lo de COM-06); «Cuando exista Hardware, Telemetría, Merma o SolicitudRevisión» (origen de la alerta, para la solicitud); «Completan el ABM de cliente» para discrepancias y entregas sin cobrar. Nace: «Cuando exista Entrega», punto 10 |
| COM-06b | «Cuando exista Entrega», punto 10 (el enlace); «Completan el ABM de cliente» para quejas |
| COM-07a | «Cuando exista Entrega», punto 10 (lo de COM-07: las solicitudes, el enlace de sus alertas, `intentos_fallidos`, `monto_a_cobrar`); «Cuando exista `produccion` completa», punto 3 (usa el tipo `incumplimiento_de_clausula` que crea COM-04a). Nace: «Cuando exista Entrega», punto 11 (para COM-07b, COM-08 y contabilidad) |
| COM-07b | «Resolución de un contrato con rescisión acordada»; «Cuando exista Entrega», punto 11 (lo de COM-07b) |
| COM-08a | «Cuando exista Entrega», puntos 10 (`estado_de_pago` con «pagada», `PagoCliente` de suministro, C7 como {xor}) y 11 (lo de COM-08a: la entrega pagada en las solicitudes y en COM-ATN-ENR); «Completan el ABM de cliente», punto 4 (el estado de pago de cada entrega) |
| COM-08b | «Cuando exista Entrega», punto 9 (la extensión 6a de COM-CNL-CVT) y lo de COM-08b del 11 (`Anulacion.pago`) |
| COM-08c | Ninguno |
