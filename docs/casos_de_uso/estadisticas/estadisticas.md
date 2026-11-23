# Casos de uso · estadísticas

Copia para el repo de EST-CNS-PRD y EST-CNS-CNS (alto nivel, v0.1, 23/11/2026), del hilo de casos de uso (`EST-alto-nivel.md`). Cotejado con
`decisiones_A0.md` (P3, H25 a H28, pasada general 7): **esas decisiones ganan**. Las fórmulas que el caso de uso deja «[pendiente]» (regla 6 de
cada uno) las fija **D-93**; la «Cómo se aplica (código)», al final. Tareas: EST-01, EST-02 y EST-03.

-----

## # Estadísticas · Casos de uso de alto nivel

Versión 0.1, 23/11/2026, con el formato de «CU extendidos», sección «Casos de uso de alto nivel» (modelo: COM-CNS-EST). Son consultas de solo lectura sobre una app nueva `estadisticas` (nivel 8, H25). Decisiones aplicadas: H25 a H28 (decisiones_A0.md). **Los indicadores son provisorios**: Ezequiel puede ajustarlos después de una entrevista a un productor. COM-CNS-EST (estadísticas comerciales) no se replanifica acá: es de COM-08.

---

## **Caso de uso EST-CNS-PRD: Consultar Estadísticas de Producción**

Reemplaza a CU-59 de «Documentación para la IA» (preliminar). Cambia el actor: ahora también lo consulta el Gerente (H26).

**Actores:** Agrónomo o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver cómo rindió la producción de los invernaderos en un período elegido, para tomar decisiones de siembra, insumos y personal.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta, no modifica datos ni registra auditoría.

**Reglas:**

1.  Alcance: el Agrónomo ve los invernaderos que tiene a cargo; el Gerente ve todos. Se puede ver el consolidado o filtrar por invernadero. (CU-59; H26)
2.  Filtros: período (por defecto, el mes actual hasta hoy; se puede elegir otro mes o un rango) e invernadero. Se compara con el período anterior de igual duración. Cada indicador usa la fecha que indica su regla. (H27)
3.  Es «cómo me fue en un período elegido». No repite ningún indicador del Panel de control (lotes activos, órdenes vencidas, ocupación de sectores, insumos por vencer) sin el filtro de período. (H27)
4.  Indicadores (provisorios, H26):
    1.  **Plantas sembradas y cosechadas:** cantidad de plantas de las siembras concretadas y de las cosechas concretadas en el período, por variedad.
    2.  **Merma:** porcentaje sobre lo sembrado y por causa de merma.
    3.  **Órdenes de trabajo cumplidas a tiempo frente a vencidas:** cantidad y porcentaje de cada grupo en el período.
    4.  **Costo promedio por planta cosechada.**
    5.  **Consumo de insumos:** en cantidad y en monto, por categoría (tipo de insumo).
    6.  **Alertas del IoT del período:** cantidad por tipo; solo si el invernadero tiene un sistema IoT. Si no, no se muestra.
5.  Desde cada indicador se puede ir a la consulta correspondiente con el mismo filtro (lotes, bitácora, órdenes, insumos, IoT).
6.  Las fórmulas exactas y la fecha de cada indicador se definen al planificar la tarea EST-01 (como las reglas de COM-CNS-EST). [pendiente]
7.  El Capataz y el Técnico no tienen acceso.
8.  La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
9.  Menú: entrada «Estadísticas» del Agrónomo y del Gerente (H28). La consulta no se audita (SEG-14).

---

## **Caso de uso EST-CNS-CNS: Consultar Estadísticas Consolidadas**

Reemplaza a CU-61 (preliminar). X9: el «libro de gestión» de CU-61 es el mecanismo contable interno (CON-CNS-LGS). La bandeja de órdenes de compra pendientes de aprobación que mencionaba CU-61 pasa al Panel de control del Gerente (H27), no a este caso de uso.

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver cómo le fue a toda la organización en un período elegido, comparando invernaderos, para decidir a nivel gerencial.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

**Postcondición:**

a. Ninguna: es una consulta.

**Reglas:**

1.  Alcance: solo el Gerente. El Contador no la ve (tiene el libro de gestión). El Vendedor ve sus estadísticas comerciales en la pestaña de Comercial (COM-CNS-EST), no acá. (H28)
2.  Filtros y comparación: como en EST-CNS-PRD (período y comparación con el período anterior). (H27)
3.  Indicadores (provisorios, H26):
    1.  **Producción de toda la organización,** comparando invernaderos: los indicadores 1 a 6 de EST-CNS-PRD.
    2.  **Comerciales:** los de COM-CNS-EST, reutilizando sus cálculos (se importan desde `comercial`, H25).
    3.  **Compras del período:** monto comprado por proveedor y por categoría de insumo, a partir de las recepciones del período valorizadas como el asiento de la recepción.
    4.  **Del libro de gestión:** ventas, costos y resultado del período (cuentas de resultado del ejercicio elegido, CON-CNS-LGS regla 4).
4.  Desde cada indicador se puede ir a la consulta correspondiente con el mismo filtro.
5.  No repite indicadores del Panel de control sin el filtro de período. (H27)
6.  Las fórmulas exactas se definen al planificar la tarea EST-02. [pendiente]
7.  Menú: entrada «Estadísticas» del Gerente. La consulta no se audita (SEG-14).

**Decididas (pasada general, 23/11/2026):**

1.  Los indicadores contables se calculan por fecha del asiento dentro del período elegido, aunque cruce dos ejercicios (no hay refundición, H2 2.3). El filtro por ejercicio es solo de la vista por cuenta de CON-CNS-LGS.
2.  Compras del período por fecha de recepción, con el monto por lo recibido según el precio total por línea.
3.  Las fórmulas exactas se definen al planificar EST-01 y EST-02.

-----

## Cómo se aplica (código)

**Las fórmulas:** D-93 puntos 3 y 4 (reemplazan la regla 6 de EST-CNS-PRD y la regla 6 de EST-CNS-CNS).

**App** `estadisticas` (nivel 8, D-93 punto 1): sin modelos. Archivos:

- `estadisticas/periodos.py`: `Periodo(desde, hasta)`, `periodo_por_defecto(hoy)`, `atajo(codigo, hoy)` (`mes`, `mes_anterior`, `tres_meses`, `ejercicio`, `personalizado`), `anterior(periodo)`,
  `validar(desde, hasta, hoy) -> Periodo` (`ValidationError` con los mensajes «La fecha “desde” no puede ser posterior a “hasta”.», «El
  período no puede terminar después de hoy.», «El período no puede ser mayor que un año.»), y `comparar(actual, anterior) -> Comparacion(valor,
  anterior, diferencia, porcentaje)`.
- `estadisticas/servicios/produccion.py`: una función por indicador 1 a 6 (`sembradas_y_cosechadas`, `merma`, `ordenes_a_tiempo`,
  `costo_por_planta_cosechada`, `consumo_de_insumos`, `alertas_iot`), cada una `(invernadero_ids, periodo) -> namedtuple` y su
  `disponible() -> bool` (D-93 punto 5); `estadisticas_de_produccion(actor, invernadero_id, periodo, comparar)` las arma con el alcance (el
  Agrónomo, sus invernaderos; el Gerente, todos).
- `estadisticas/servicios/consolidadas.py` (EST-02): `por_invernadero(periodo)` (indicador 7), `compras(periodo)` (9), `libro(periodo)` (10) y,
  en EST-03, `comerciales(periodo)` (8).
- `estadisticas/views.py`, `urls.py` (`estadisticas/` y `estadisticas/consolidadas/`), plantillas en `estadisticas/templates/estadisticas/`; el
  formulario del período es un GET (la URL se puede compartir y volver a abrir). Acceso: `rol_requerido` (Agrónomo o Gerente; consolidadas, solo
  Gerente); el Capataz, el Técnico, el Vendedor y el Contador reciben 403.
- `estadisticas/apps.py`: el menú «Estadísticas» del Agrónomo y del Gerente (H28).
- No audita (regla 9: es una consulta, SEG-14).

**Pruebas:** `estadisticas/tests/test_periodos.py`, `test_est_cns_prd.py` (`EstCnsPrdServicioTests`: un caso por indicador con datos armados a
mano y resultado esperado calculado en la prueba; alcance; período anterior; indicadores no disponibles), `test_est_cns_prd_vistas.py`,
`test_est_cns_cns.py`, `test_est_cns_cns_vistas.py`, y en cada servicio una prueba con `assertNumQueries` que no crece con la cantidad de filas.
