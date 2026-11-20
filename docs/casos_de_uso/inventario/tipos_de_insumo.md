# Casos de uso · inventario · Tipos de insumo (categorías)

Copia para el repo de los casos CMP-ALT-TIN, CMP-MOD-TIN, CMP-BAJ-TIN y CMP-CNS-TIN del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `inventario`** (D-37); el archivo de pruebas es
`inventario/tests/test_cmp_alt_tin.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CMP-ALT-TIN | Alta Tipo de Insumo | Agrónomo | `inventario/tests/test_cmp_alt_tin.py` |
| CMP-MOD-TIN | Modificar Tipo de Insumo | Agrónomo | `inventario/tests/test_cmp_mod_tin.py` |
| CMP-BAJ-TIN | Baja Tipo de Insumo | Agrónomo | `inventario/tests/test_cmp_baj_tin.py` |
| CMP-CNS-TIN | Consultar Tipo de Insumo | Agrónomo | `inventario/tests/test_cmp_cns_tin.py` |

---

## CMP-ALT-TIN · Alta Tipo de Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: registrar una categoría de insumos, con su nombre y su consumo directo, para clasificar el catálogo de insumos.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. No existe otra categoría con el mismo nombre.

**Postcondición:**
a. Se creó una categoría en estado «activo», con su nombre y su consumo directo, que no es del sistema y no tiene
   insumos.
b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la categoría creada.

**Reglas:**
1. Cualquier Agrónomo activo registra categorías: la categoría es del catálogo y vale para todos los invernaderos.
2. El nombre es obligatorio y único entre todas las categorías, activas o inactivas, sin distinguir mayúsculas ni
   espacios al principio o al final.
3. El consumo directo es obligatorio e indica si los insumos de la categoría pueden registrarse sin una orden de
   trabajo, con Registrar Aplicación de Insumos (PROD-REG-APL), y a dónde va su costo: «no admite» (sus insumos solo
   se consumen con una orden de trabajo: siembra, entrega o mantenimiento); «como gasto» (su costo va a gasto; por
   ejemplo, limpieza); o «como costo de los lotes» (su costo se reparte entre los lotes de plantas de los sectores
   donde se aplicó; por ejemplo, nutrientes).
4. Desde este caso de uso no se crean categorías del sistema. Las categorías del sistema son cuatro y se cargan en la
   puesta en marcha: Semillas, Envases, Repuestos de hardware e Infraestructura. Las reglas de siembra, entrega y
   mantenimiento dependen de ellas, y ninguna admite consumo directo.

---

## CMP-MOD-TIN · Modificar Tipo de Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: cambiar el nombre o el consumo directo de una categoría de insumos, o reactivar una dada de baja.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. La categoría no es del sistema.
c. Si cambia el nombre, no existe otra categoría con el nombre nuevo.

**Postcondición, según lo que haya hecho el actor:**
a. Se actualizaron el nombre o el consumo directo de la categoría.
b. Si reactivó la categoría, quedó en estado «activo».
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la categoría y los cambios.

**Reglas:**
1. Cualquier Agrónomo activo modifica o reactiva una categoría.
2. El nombre y el consumo directo siguen las reglas 2 y 3 de CMP-ALT-TIN.
3. Las categorías del sistema no se modifican ni se dan de baja.
4. El consumo directo no se cambia si algún insumo de la categoría tiene cantidades reservadas por órdenes a realizar:
   el Sistema informa los insumos y las órdenes. El nombre sí se puede cambiar.
5. El cambio de consumo directo rige desde ese momento: las aplicaciones ya registradas conservan su costo, su
   imputación y sus asientos.
6. Una categoría inactiva no se modifica: solo se reactiva, sin validaciones, y después se modifica como cualquier
   otra.

---

## CMP-BAJ-TIN · Baja Tipo de Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: dar de baja lógica una categoría de insumos que ya no se usa.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. La categoría está activa y no es del sistema.
c. La categoría no tiene insumos activos.

**Postcondición:**
a. La categoría quedó en estado «inactivo» (baja lógica) y dejó de ofrecerse al dar de alta o modificar insumos.
b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la categoría y el cambio de estado.

**Reglas:**
1. La baja es lógica: la categoría conserva sus insumos inactivos y su historial.
2. Si la categoría tiene insumos activos, el Sistema no la da de baja e informa cuántos son: primero deben pasarse a
   otra categoría con Modificar Insumo. Los insumos inactivos no impiden la baja.
3. Se reactiva con CMP-MOD-TIN.

---

## CMP-CNS-TIN · Consultar Tipo de Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: consultar las categorías de insumos y su configuración.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. El Agrónomo consulta todas las categorías, activas e inactivas.
2. De cada categoría se ve su nombre, con la marca «del sistema» si corresponde; su consumo directo; la cantidad de
   insumos del catálogo que tiene; y su estado.
3. El Sistema explica por qué las categorías del sistema no se modifican y qué significa el consumo directo.
4. Desde una categoría que no es del sistema, el Agrónomo inicia CMP-MOD-TIN o CMP-BAJ-TIN, o la reactiva si está
   inactiva. Las categorías del sistema no tienen acciones.
5. El Gerente no consulta categorías.
6. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **INV-01**. Todo lo de este archivo se implementa, con estas decisiones de aplicación:

- **Las cuatro categorías del sistema.** El CU y el modelo (regla 1 de 8.23) dicen cuatro: Semillas, Envases, Repuestos de
  hardware e Infraestructura. El prototipo y su texto de ayuda nombran tres (falta Infraestructura). **Manda el CU** (L7). Las
  crea una migración de datos (`cargar_categorias_del_sistema`, `docs/patrones/datos_de_migracion.md`), cada una con un
  `codigo` fijo y único (`semillas`, `envases`, `repuestos_de_hardware`, `infraestructura`), `es_del_sistema` verdadero,
  consumo directo «no admite» y estado activo. **Toda regla que dependa de una categoría la busca por `codigo`, nunca por el
  nombre** (regla 1 de 8.23). Las demás categorías que se ven en el prototipo (limpieza, nutrientes y similares) son datos de
  ejemplo: **no se cargan**; las crea la organización.
- **Quién.** Cualquier Agrónomo activo. El Gerente y los demás roles no ven ni consultan categorías (regla 5 de CNS): la entrada
  del menú «Inventario» es del Agrónomo, y la URL da 403 a los demás.
- **Nombre único** entre activas e inactivas, sin distinguir mayúsculas ni espacios al borde: se recorta al guardar y una
  restricción de la base sobre `lower(nombre_tipo_insumo)` lo respalda (D-36). El nombre de una categoría del sistema también
  cuenta: nadie crea otra «Envases».
- **Reservas en MOD (regla 4).** «Algún insumo de la categoría tiene cantidades reservadas por órdenes a realizar» se pregunta por
  el punto de extensión `registrar_reservas_de_insumo` de `inventario` (`docs/api/extensiones_de_inventario.md`), que registra
  `produccion` (PRD-01). Hasta entonces no hay registrantes y el resultado es «sin reservas». INV-01 escribe la regla y la
  prueba con un registrante falso. Para nombrar las órdenes en el aviso usa `registrar_ordenes_que_reservan`.
- **Bloqueo.** MOD y BAJ toman la categoría con `FOR NO KEY UPDATE`; ALT-INS (en `insumos.md`) la toma antes de crear el insumo,
  para que una baja simultánea no deje un insumo activo en una categoría inactiva. MOD con cambio de consumo directo toma
  además los `InsumoInvernadero` de la categoría, en orden de id, antes de preguntar por las reservas. Orden de `inventario`:
  `docs/patrones/stock.md`, sección «Orden de bloqueo».
- **Auditoría (D-36).** Acciones `alta_tipo_insumo`, `modificacion_tipo_insumo`, `baja_tipo_insumo` y `reactivacion_tipo_insumo`.
  En un cambio de consumo directo, «antes» y «después» llevan el valor visible. Sin cambios no se audita (D-28).
- **Reactivar** (regla 6 de MOD) no valida nada y se hace con la misma función `reactivar_tipo_insumo`; después se modifica como
  cualquier otra.
- **Las categorías del sistema** aparecen en la consulta con la marca «del sistema» y un candado, sin acciones. El servicio
  también las rechaza (`ValidationError` con código `categoria_del_sistema`): no alcanza con esconder el botón.
- **Cantidad de insumos** (regla 2 de CNS): cuenta los del catálogo, activos e inactivos. La baja (regla 2 de BAJ) cuenta solo
  los activos.

