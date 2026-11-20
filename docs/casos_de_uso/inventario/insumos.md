# Casos de uso · inventario · Insumos del catálogo

Copia para el repo de los casos CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS y CMP-CNS-INS del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario.

Son casos de uso breves (de alto nivel). **El código va en la app `inventario`** (D-37); el archivo de pruebas es
`inventario/tests/test_cmp_alt_ins.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CMP-ALT-INS | Alta Insumo | Agrónomo | `inventario/tests/test_cmp_alt_ins.py` |
| CMP-MOD-INS | Modificar Insumo | Agrónomo | `inventario/tests/test_cmp_mod_ins.py` |
| CMP-BAJ-INS | Baja Insumo | Agrónomo | `inventario/tests/test_cmp_baj_ins.py` |
| CMP-CNS-INS | Consultar Insumo | Agrónomo | `inventario/tests/test_cmp_cns_ins.py` |

---

## CMP-ALT-INS · Alta Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: registrar un insumo en el catálogo de la organización, con su nombre, su descripción, su categoría, su unidad de medida y si controla vencimiento, para poder habilitarlo en los invernaderos.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. No existe otro insumo con el mismo nombre.

**Postcondición:**
a. Se creó un insumo en estado «activo», con su nombre, su descripción (si se indicó), su unidad de medida y la
   indicación de si controla vencimiento, asociado a su categoría y sin habilitar en ningún invernadero.
b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del insumo creado.

**Reglas:**
1. Cualquier Agrónomo activo registra insumos: el catálogo es el mismo para toda la organización.
2. El nombre es obligatorio y único entre todos los insumos, activos o inactivos, sin distinguir mayúsculas ni
   espacios al principio o al final.
3. La descripción es opcional y de texto libre. Sirve para anotar lo que identifica al insumo y no entra en el nombre,
   como la composición de un nutriente, la marca o la presentación.
4. La categoría se elige entre las categorías activas. La categoría Semillas no se ofrece: las semillas se crean solas
   al registrar su variedad (PROD-ALT-VAR).
5. La unidad de medida es aquella en la que se usa el insumo y se elige de una lista fija, cada una con los decimales
   que admite: unidad (solo enteros); kg, L y m³ (hasta 3 decimales); g, mL, m y m² (hasta 2 decimales). Si se compra
   por presentación (por ejemplo, una tira de 6 m o una bolsa de 100 L), la equivalencia se carga al registrar la
   compra.
6. «Controla vencimiento» indica si cada lote de insumo que ingresa debe llevar su fecha de vencimiento. Si controla,
   el Sistema avisa antes de que venza cada lote; si no, sus lotes no vencen y se consumen por orden de llegada.
   Debería controlarlo todo lo que se degrada (semillas, nutrientes, productos de limpieza), y no hace falta en
   envases, repuestos ni herramientas.
7. Al terminar, el Sistema informa que, para tener stock del insumo en un invernadero, primero hay que habilitarlo
   ahí, y ofrece hacerlo.

---

## CMP-MOD-INS · Modificar Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: actualizar los datos de un insumo del catálogo, o reactivar uno dado de baja.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El actor puede gestionar el insumo (regla 1).
c. El insumo no es una semilla.
d. Si cambia el nombre, no existe otro insumo con el nombre nuevo.

**Postcondición, según lo que haya hecho el actor:**
a. Se actualizaron los datos indicados del insumo.
b. Si otros invernaderos tienen el insumo habilitado, el Agrónomo de cada uno de ellos recibió una notificación dentro
   del Sistema con el cambio.
c. Si reactivó el insumo, quedó en estado «activo» y sin habilitar en ningún invernadero.
d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del insumo y los cambios.

**Reglas:**
1. Un invernadero usa el insumo si está activo y lo tiene habilitado. El insumo lo modifica o reactiva el Agrónomo de
   algún invernadero que lo usa; si ningún invernadero lo usa, cualquier Agrónomo activo. Si no puede gestionarlo, el
   Sistema le informa qué invernaderos lo usan y quiénes son sus Agrónomos.
2. Los datos se validan con las reglas 2 a 6 de CMP-ALT-INS.
3. Qué se puede cambiar, campo por campo: el nombre y la descripción, siempre; la unidad de medida, solo si el insumo
   nunca tuvo stock ni movimientos en ningún invernadero; la categoría no se cambia si es del sistema, ni se puede
   pasar a una del sistema, ni a una con otro consumo directo si el insumo tiene cantidades reservadas por órdenes a
   realizar; «controla vencimiento», solo si el insumo no tiene stock en ningún invernadero. Cada campo bloqueado
   muestra por qué.
4. Las semillas no se modifican desde este caso de uso: su nombre cambia con su cultivo o su variedad (PROD-MOD-CLT y
   PROD-MOD-VAR), y su categoría es fija.
5. Antes de confirmar, el Sistema informa qué otros invernaderos usan el insumo y que sus Agrónomos recibirán el
   aviso, salvo el actor. El aviso no bloquea el cambio.
6. Un insumo inactivo no se modifica: solo se reactiva, y solo si su categoría está activa. La reactivación no lo
   vuelve a habilitar en ningún invernadero: hay que habilitarlo de nuevo en cada uno.

---

## CMP-BAJ-INS · Baja Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: dar de baja lógica un insumo que la organización ya no usa, sin perder su historial.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El actor puede gestionar el insumo (regla 1 de CMP-MOD-INS).
c. El insumo está activo y no es una semilla.
d. En ningún invernadero el insumo tiene stock distinto de cero, cantidades reservadas, cantidad en tránsito ni una
   orden de compra aprobada sin recibir.
e. El insumo no figura en ningún pedido en curso, es decir, en ningún pedido que todavía no tiene orden de compra.

**Postcondición:**
a. El insumo quedó en estado «inactivo» (baja lógica) y dejó de ofrecerse para pedidos, habilitaciones y órdenes de
   trabajo.
b. Todos los invernaderos donde estaba habilitado quedaron con el insumo deshabilitado.
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del insumo y el cambio de estado, y otro
   por cada invernadero donde se deshabilitó.

**Reglas:**
1. La baja es lógica: el insumo conserva sus lotes de insumo, sus movimientos, sus consumos y su historial.
2. Si no se cumple la precondición d o la e, el Sistema no da de baja el insumo e informa, invernadero por
   invernadero, todo lo que lo impide, cada cosa con cómo resolverla: el stock se usa o se lleva a cero con un ajuste
   (CMP-AJT-STK), y el stock negativo también impide la baja; las órdenes que lo reservan se concretan o se cancelan;
   la mercadería en camino se recibe o se cierra la orden de compra; los pedidos en curso se cierran o se les quita el
   insumo.
3. Las semillas se dan de baja junto con su variedad (PROD-BAJ-VAR).
4. Se reactiva con CMP-MOD-INS.

---

## CMP-CNS-INS · Consultar Insumo

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: consultar el catálogo de insumos de la organización y dónde está habilitado cada uno.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. El Agrónomo consulta todo el catálogo, con los insumos activos e inactivos.
2. De cada insumo se ve su nombre y su descripción, si tiene; su categoría, con la marca «del sistema» si corresponde;
   su unidad de medida; si controla vencimiento; los invernaderos donde está habilitado, o «ninguno»; y su estado. Las
   semillas indican que vienen del alta de su variedad y que se gestionan con ella.
3. Desde cada insumo activo, el Agrónomo puede habilitarlo en un invernadero, incluidas las semillas; un insumo
   inactivo no se habilita. Según su estado, inicia CMP-MOD-INS o CMP-BAJ-INS, o lo reactiva; las semillas no tienen
   estas acciones. Si no puede gestionar el insumo, esas acciones aparecen deshabilitadas con el nombre de quién lo
   usa.
4. El Gerente no consulta el catálogo.
5. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **INV-01** (la habilitación en un invernadero, que ofrece el alta, es de INV-02: ver `insumo_invernadero.md`).

- **Las semillas.** Un insumo «es una semilla» si su categoría es la del sistema `semillas` (por `codigo`). INV-01 no depende del
  modelo `Semilla`, que crea INV-03: el alta no ofrece esa categoría, la modificación y la baja rechazan las semillas, y la
  consulta las marca «Viene del alta de la variedad». El texto de la consulta y los avisos de modificar y dar de baja se
  escriben ahora; lo que las enlaza con su variedad llega con INV-03.
- **Unidades.** Lista fija en el código (confirmado el 19/11/2026): `inventario/unidades.py` con `Unidad` (`unidad`, `kg`, `g`,
  `L`, `mL`, `m3`, `m`, `m2`) y su cantidad de decimales (0, 3, 2, 3, 2, 3, 2, 2). Toda cantidad de inventario se guarda como
  `Decimal` con 3 decimales en la base y se valida contra los decimales de **la unidad del insumo** en el servicio; nunca
  `float`. La función `validar_cantidad` de ese módulo es la única que decide si una cantidad es válida (la usan INV-01,
  INV-02 y, después, producción y compras).
- **Qué usa un insumo.** «Un invernadero usa el insumo si está activo y lo tiene habilitado» (regla 1 de MOD): un
  `InsumoInvernadero` activo cuyo invernadero está activo. De ahí salen el Agrónomo que puede gestionarlo, los avisos de
  cambio y la lista de «quién lo usa» de los mensajes. Un Agrónomo gestiona el insumo si es el Agrónomo de alguno de esos
  invernaderos; si ninguno lo usa, cualquier Agrónomo activo.
- **Campos bloqueados de MOD (regla 3).** El servicio los verifica uno por uno y devuelve el error en el campo: unidad (si hubo
  algún `LoteInsumo` o `MovimientoInsumo` del insumo en cualquier invernadero), «controla vencimiento» (si algún `LoteInsumo`
  tiene cantidad disponible distinta de cero, incluido el faltante sin lote), categoría (si es del sistema, si el destino es del
  sistema, o si el destino tiene otro consumo directo y hay reservas, por el punto de extensión de reservas).
- **Avisos de cambio (postcondición b, regla 5).** Una notificación (D-42, `notificar_a_varios`) al Agrónomo de cada otro
  invernadero que usa el insumo, sin el actor y sin repetir cuentas; un invernadero sin Agrónomo no genera aviso. El aviso no
  bloquea. Antes de confirmar, la pantalla informa a quiénes se avisará (la vista pide la lista al servicio
  `invernaderos_que_usan`).
- **Baja (CMP-BAJ-INS).** Se bloquean los invernaderos que lo usan (orden de id, D-40), después el insumo y sus
  `InsumoInvernadero` (orden de id), y se vuelve a leer. Los impedimentos se juntan **todos**, por invernadero:
  stock distinto de cero (incluido el negativo), reservas (punto de extensión), cantidad en tránsito mayor que cero, y orden de
  compra aprobada y pedidos en curso (`registrar_impedimento_de_deshabilitacion`, que registrará `compras`; sin registrantes, no
  hay). Un pedido en curso con el insumo siempre tiene un invernadero de destino donde el insumo está habilitado, así que el
  mismo punto sirve para la baja del catálogo. Si no hay ninguno, el insumo y todos sus `InsumoInvernadero` pasan a
  inactivo, se resuelve la alerta de stock bajo el mínimo de cada uno (API de alertas) y se audita: un registro `baja_insumo`
  y uno `baja_insumo_invernadero` por invernadero.
- **Reactivar** exige la categoría activa y deja el insumo sin habilitar en ningún invernadero (los `InsumoInvernadero` siguen
  inactivos hasta que cada Agrónomo los habilite de nuevo).
- **Descripción:** texto libre, opcional, recortado, hasta 300 caracteres. **Nombre:** hasta 100. Los límites son de esta ronda
  (el CU no los fija); se registran como `max_length` y se prueban.
- **Quién.** Solo el Agrónomo consulta y gestiona el catálogo; el Gerente no lo consulta (regla 4 de CNS).
- **Auditoría (D-36).** Acciones `alta_insumo`, `modificacion_insumo`, `baja_insumo`, `reactivacion_insumo`.
- **Ofrecer la habilitación (regla 7 de ALT).** Hasta que INV-02 exista, el alta termina con el aviso y sin el botón; INV-02
  agrega el botón «Habilitar en un invernadero» en el alta y en el catálogo.

