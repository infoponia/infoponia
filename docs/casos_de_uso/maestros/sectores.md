# Casos de uso · maestros · Sector de producción

Copia para el repo de los casos PROD-ALT-SCT, PROD-MOD-SCT, PROD-BAJ-SCT y PROD-CNS-SCT del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96, y con el glosario del 15/11/2026.

Son casos de uso breves (de alto nivel): precondiciones, postcondiciones y reglas, sin escenario principal paso a paso.
**El código va en la app `maestros`** (D-37): el código del caso de uso (`PROD-...`) no cambia y el archivo de pruebas es
`maestros/tests/test_prod_alt_sct.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-ALT-SCT | Alta Sector | Agrónomo | `maestros/tests/test_prod_alt_sct.py` |
| PROD-MOD-SCT | Modificar Sector | Agrónomo | `maestros/tests/test_prod_mod_sct.py` |
| PROD-BAJ-SCT | Baja Sector | Agrónomo | `maestros/tests/test_prod_baj_sct.py` |
| PROD-CNS-SCT | Consultar Sector | Agrónomo y Gerente | `maestros/tests/test_prod_cns_sct.py` |

---

## PROD-ALT-SCT · Alta Sector

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** registrar un sector de producción en un invernadero, con su nombre, su tipo de etapa y su cantidad de agujeros, para que pueda recibir plantas.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero está activo y a cargo del actor.
c. No existe otro sector con el mismo nombre en ese invernadero.

**Postcondición:**
a. Se creó un sector en estado «activo», con su nombre, su tipo de etapa y su cantidad total de agujeros. Está
   asociado al invernadero y a su tipo de etapa.
b. Si el invernadero tenía la marca «sin sectores», la marca dejó de mostrarse.
c. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del sector creado.

**Reglas:**
1. Solo el Agrónomo a cargo del invernadero registra sus sectores.
2. El nombre es obligatorio y único dentro del invernadero, sin distinguir mayúsculas. Se cuentan también los sectores
   dados de baja. Dos invernaderos pueden tener sectores con el mismo nombre.
3. El tipo de etapa se elige del catálogo fijo de tipos de etapa (Germinación, Crecimiento, Floración, Fructificación,
   Maduración).
4. La cantidad total de agujeros es un número entero mayor que cero. Cada planta ocupa un agujero, en todas las
   etapas.
5. Los agujeros ocupados, comprometidos y libres se calculan, no se cargan. Un sector nuevo tiene todos sus agujeros
   libres.
6. El sector no tiene ubicación ni densidad: es un sector genérico con su cantidad de agujeros.

---

## PROD-MOD-SCT · Modificar Sector

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** actualizar el nombre, el tipo de etapa o la cantidad de agujeros de un sector, volver a activar un sector fuera de servicio, o reactivar uno dado de baja.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero del sector está activo y a cargo del actor.
c. Si cambia el nombre, no existe otro sector con el nombre nuevo en ese invernadero.

**Postcondición, según lo que haya hecho el actor:**
a. Se actualizaron los datos indicados: el nombre, el tipo de etapa o la cantidad total de agujeros.
b. Si volvió a activar un sector fuera de servicio, el sector quedó en estado «activo», el registro «Fuera de
   servicio» abierto del sector quedó con la fecha de fin igual a la fecha actual, y se registró en la bitácora del
   invernadero que el sector vuelve a estar activo, con el período que estuvo fuera de servicio.
c. Si reactivó un sector dado de baja, quedó en estado «activo».
d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sector y los cambios.

**Reglas:**
1. Qué se puede cambiar, campo por campo: el nombre, siempre, respetando la regla 2 de PROD-ALT-SCT; la cantidad total
   de agujeros se puede subir siempre, y bajar como mínimo hasta la suma de sus agujeros ocupados y comprometidos; el
   tipo de etapa, solo si el sector no tiene agujeros ocupados ni comprometidos (si los tiene, el Sistema lo informa y
   el campo queda bloqueado); el invernadero no se cambia nunca.
2. Un sector activo o fuera de servicio se puede modificar. Un sector fuera de servicio sigue fuera de servicio
   después de modificarlo: solo vuelve a «activo» si se lo vuelve a activar.
3. Un sector dado de baja no se modifica: solo se reactiva, y después se modifica como cualquier otro.
4. Si un cambio de tipo deja al invernadero sin sectores activos del tipo anterior, el Sistema advierte, sin bloquear:
   los lotes que todavía deben pasar por esa etapa, con la fecha en que la necesitan; las siembras a realizar
   afectadas; y las variedades que dejan de poder sembrarse en el invernadero. Recomienda registrar otro sector de esa
   etapa o cambiar el tipo de uno existente. El Agrónomo puede volver o continuar igual: los lotes afectados esperan
   en su etapa actual hasta que haya un sector de ese tipo.
5. Volver a activar un sector fuera de servicio y reactivar un sector dado de baja no tienen validaciones: el sector
   está vacío y sin reservas.
6. Para sacar un sector de servicio se usa PROD-PNR-FDS, no este caso de uso.

---

## PROD-BAJ-SCT · Baja Sector

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** dar de baja lógica un sector que deja de existir, sin perder su historial.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El invernadero del sector está activo y a cargo del actor.
c. El sector está activo o fuera de servicio.
d. El sector no tiene agujeros ocupados ni comprometidos.
e. El sector no tiene hardware activo asociado.

**Postcondición:**
a. El sector quedó en estado «inactivo» (baja lógica) y dejó de contar como capacidad del invernadero.
b. Si el sector estaba fuera de servicio, su registro «Fuera de servicio» abierto quedó con la fecha de fin igual a la
   fecha actual.
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sector y el cambio de estado.

**Reglas:**
1. La baja es lógica: el sector conserva sus ocupaciones, su bitácora y su historial.
2. Si el sector tiene agujeros ocupados o comprometidos, el Sistema no lo da de baja. Informa los lotes que lo ocupan
   y las órdenes que lo tienen reservado, y ofrece ponerlo fuera de servicio (PROD-PNR-FDS), donde se reubican o se
   registran como merma las plantas y se cancelan las órdenes (MD-66).
3. Si el sector tiene hardware activo asociado, el Sistema no lo da de baja y presenta cada equipo con un acceso para
   editarlo en el bloque IoT, ya sea para quitarle el sector o para darlo de baja.
4. Si la baja deja al invernadero sin sectores activos de ese tipo de etapa, el Sistema advierte sin bloquear, igual
   que en la regla 4 de PROD-MOD-SCT.
5. Un sector dado de baja no cuenta para los niveles 1 y 2 de la capacidad ni para el ritmo sostenible. Un sector
   fuera de servicio, en cambio, sí cuenta.
6. Se reactiva con PROD-MOD-SCT.

---

## PROD-CNS-SCT · Consultar Sector

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1). **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** consultar los sectores de un invernadero, su capacidad y lo que tienen adentro.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. Alcance: el Agrónomo consulta los sectores de los invernaderos activos a su cargo, y el Gerente los de cualquier
   invernadero, en solo lectura. Se consultan desde la ficha del invernadero (PROD-CNS-INV).
2. Los sectores se agrupan por tipo de etapa, con la cantidad de sectores y de agujeros de cada grupo. Los dados de
   baja van en un grupo aparte.
3. De cada sector se ve su nombre, su estado y su tipo de etapa; su perfil familiar, o «sin plantas: acepta cualquier
   perfil» si está vacío; sus agujeros libres sobre el total, con una barra de los ocupados y los comprometidos; los
   lotes que lo ocupan, con su variedad y sus plantas en el sector; las órdenes a realizar que lo tienen reservado,
   con su fecha y sus agujeros reservados; y su hardware asociado, si tiene.
4. Un sector fuera de servicio muestra desde cuándo y el motivo, y que no recibe plantas ni órdenes pero cuenta como
   capacidad. Un sector dado de baja muestra que no cuenta como capacidad y que conserva su historial.
5. Si el invernadero no tiene sectores, el Sistema lo informa y explica que sin sectores no se puede sembrar. Al
   Agrónomo a cargo le ofrece registrar uno (PROD-ALT-SCT).
6. Desde cada sector, el Agrónomo a cargo inicia PROD-MOD-SCT, PROD-PNR-FDS o PROD-BAJ-SCT, según el estado del
   sector.
7. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **MAE-03**. Todo lo de este archivo se implementa en MAE-03, salvo lo que depende de tablas que crean tareas posteriores
(lotes, órdenes, hardware). Para eso `maestros` ofrece puntos de extensión (regla A4 de D-37; contrato en
`docs/api/extensiones_de_maestros.md`) que, **sin registrantes, dan 0 agujeros ocupados y comprometidos, ningún impedimento y
ningún contenido**. Cada punto se prueba con registrantes falsos. Las tareas que crean lo que falta se registran:

| Qué falta en MAE-03 | Regla afectada | Quién lo completa |
|---|---|---|
| Agujeros ocupados y comprometidos (`OcupacionSector`, órdenes) | MOD regla 1 (piso de la cantidad y bloqueo del tipo); BAJ precondición d y regla 2; CNS regla 3 (barra) | PRD-01 (siembra) y PRD-02 (transición) |
| Perfil familiar del sector (sale de los lotes que lo ocupan) | CNS regla 3 | PRD-01 |
| Lotes, órdenes y hardware que se muestran en cada sector | CNS regla 3 | PRD-01 (lotes y órdenes); el hardware, al módulo IoT (disparador) |
| Lotes y siembras afectados por un cambio de tipo | MOD regla 4 y BAJ regla 4 (solo la parte de lotes y siembras; la de variedades sí la calcula MAE-03) | PRD-01 |
| Hardware activo asociado | BAJ precondición e y regla 3 | módulo IoT (disparador «Cuando exista Hardware») |
| Sector fuera de servicio (registro «Fuera de servicio», bitácora) | MOD postcondición b y regla 5; BAJ postcondición b; CNS regla 4; la acción PROD-PNR-FDS | PRD-04 (`PROD-PNR-FDS`). En MAE-03 el estado «fuera de servicio» existe en el modelo y se muestra, pero ningún caso de uso lo produce |
| Bitácora del invernadero | MOD postcondición b | PRD-03 |

Decisiones de aplicación (no cambian el caso de uso):

- **El estado del sector** tiene tres valores: «activo», «fuera de servicio» y «inactivo». El modelo de dominio nombra dos
  (activo/inactivo) pero los casos de uso y el prototipo usan el tercero (MD-66, PROD-PNR-FDS): **manda el caso de uso**.
- **Auditoría (D-36).** Acciones nuevas en `ACCIONES_DE_NEGOCIO`: `alta_sector`, `modificacion_sector`, `baja_sector`,
  `reactivacion_sector`. La consulta no se audita (SEG-14). La baja del invernadero registra además un log por sector
  (postcondición f de PROD-BAJ-INV), con la misma acción `baja_sector`.
- **Alcance de «a cargo»:** el actor es el Agrónomo activo del invernadero (`Invernadero.agronomo`). El Gerente solo consulta.
- **Bloqueos (D-30, D-32, D-40).** Alta, modificación, baja y reactivación toman el invernadero con
  `bloquear_invernadero_activo` y después la fila del sector, en ese orden; el nombre único por invernadero lo respalda una
  restricción de la base sobre `(invernadero, lower(nombre))`.
- **Reactivación** (regla 3 de MOD): solo con el invernadero activo. Un sector reactivado vuelve «activo» sin validaciones
  (regla 5) y se audita como `reactivacion_sector`.
- **Marca «sin sectores»** (`Invernadero.tiene_sectores()`): pasa a calcularse con los sectores activos o fuera de servicio
  del invernadero, y deja de ser siempre falso (postcondición b de PROD-ALT-SCT; PROD-CNS-INV, regla 3).
- **Etapas que ningún sector atiende:** la advertencia de la regla 4 de PROD-MOD-SCT y de la regla 4 de PROD-BAJ-SCT se
  muestra antes de confirmar y no bloquea; se calcula con lo que haya registrado (hoy: las variedades activas cuyo ciclo
  incluye el tipo anterior).

