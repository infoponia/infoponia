# Casos de uso · inventario · Variedad y su semilla

Copia para el repo de los casos PROD-ALT-VAR, PROD-MOD-VAR, PROD-BAJ-VAR y PROD-CNS-VAR (versión 0.1) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026.

Son casos de uso breves (de alto nivel). **El código va en la app `inventario`** (D-49), aunque `Variedad`, `Ciclo` y `EtapaProductiva` viven en
`maestros` (los creó MAE-03); los archivos de pruebas son `inventario/tests/test_prod_alt_var.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-ALT-VAR | Alta Variedad | Agrónomo | `inventario/tests/test_prod_alt_var.py` |
| PROD-MOD-VAR | Modificar Variedad | Agrónomo | `inventario/tests/test_prod_mod_var.py` |
| PROD-BAJ-VAR | Baja Variedad | Agrónomo | `inventario/tests/test_prod_baj_var.py` |
| PROD-CNS-VAR | Consultar Variedad | Agrónomo | `inventario/tests/test_prod_cns_var.py` |

---

## PROD-ALT-VAR · Alta Variedad

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: registrar una variedad de un cultivo, con su perfil familiar, su ciclo productivo, sus condiciones ambientales, su postcosecha y su peso, para poder pedir su semilla y sembrarla.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El cultivo está activo.
c. No existe en ese cultivo otra variedad con el mismo nombre.

**Postcondición:**
a. Se creó una variedad en estado «activo», asociada a su cultivo, con su nombre, su perfil familiar, sus rangos de
   temperatura ambiente, humedad, intensidad lumínica y fotoperíodo, su duración postcosecha y su peso promedio por
   planta.
b. Se creó su ciclo, con la duración total en días, y una etapa por cada tipo de etapa incluido, con su duración
   estimada en días y asociada a su tipo de etapa.
c. Se creó su semilla, «Semilla {cultivo} {variedad}», activa, en la categoría Semillas, por unidad, con control de
   vencimiento, asociada a la variedad y sin habilitar en ningún invernadero.
d. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de la variedad, del ciclo, de cada etapa
   y de la semilla creados.

**Reglas:**
1. Cualquier Agrónomo activo registra variedades: la variedad no pertenece a un invernadero.
2. El nombre es obligatorio y único dentro del cultivo, sin distinguir mayúsculas ni espacios al principio o al final.
   Se cuentan también las variedades dadas de baja. Dos cultivos pueden tener variedades con el mismo nombre.
3. El perfil familiar se elige del catálogo fijo: Hoja verde, Pastura, Frutos grandes, Frutos pequeños, Flores y
   Hierbas.
4. Germinación y Maduración son obligatorias. Crecimiento, Floración y Fructificación son optativas, y solo se ofrecen
   las que permite el perfil familiar: Floración, para Frutos grandes, Frutos pequeños y Flores; Fructificación, para
   Frutos grandes y Frutos pequeños. Las etapas siguen el orden del catálogo de tipos de etapa.
5. La duración de cada etapa incluida es un número entero de días mayor que cero. La duración del ciclo es la suma de
   sus etapas, y la cosecha estimada llega al entrar en Maduración, a los días que suman las etapas anteriores.
6. Cada rango ambiental tiene un mínimo y un máximo obligatorios, admite decimales, y el mínimo no puede ser mayor que
   el máximo.
7. La duración postcosecha es un número entero entre 1 y 60 días. El peso promedio por planta es un número entero de
   gramos mayor que cero.
8. Antes de crear la variedad, el Sistema presenta un resumen con todos los datos y el nombre de la semilla que se
   creará. El Agrónomo puede volver a editar, confirmar o cancelar.
9. Al terminar, el Sistema informa que para pedir o sembrar la variedad hay que habilitar su semilla en cada
   invernadero donde se vaya a usar, y ofrece hacerlo.
10. «Semilla» es el material de propagación de la variedad: semilla o plantín.

---

## PROD-MOD-VAR · Modificar Variedad

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: actualizar los datos, el ciclo o las condiciones ambientales de una variedad, o reactivar una dada de baja.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El actor puede gestionar la variedad (regla 1).
c. Si cambia el nombre, no existe en ese cultivo otra variedad con el nombre nuevo.

**Postcondición, según lo que haya hecho el actor:**
a. Se actualizaron los datos indicados de la variedad, de su ciclo y de sus etapas.
b. Si cambió el nombre, su semilla quedó con el nombre nuevo.
c. Si cambió el nombre, las duraciones, las etapas o los rangos, y otros invernaderos usan la variedad, el Agrónomo de
   cada uno de esos invernaderos recibió una notificación dentro del Sistema con lo que cambió.
d. Si reactivó la variedad, ella y su semilla quedaron en estado «activo».
e. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de cada objeto modificado (variedad,
   ciclo, etapas y semilla) y los cambios.

**Reglas:**
1. Un invernadero usa la variedad si está activo y tiene su semilla habilitada o lotes activos de ella. La modifica o
   reactiva el Agrónomo de algún invernadero que la use; si ningún invernadero la usa, cualquier Agrónomo activo. Si
   no puede gestionarla, el Sistema le informa qué invernaderos la usan y quiénes son sus Agrónomos.
2. Los datos se validan con las reglas 2 a 7 de PROD-ALT-VAR.
3. Las etapas (cuáles y en qué orden) no se agregan ni se quitan si la variedad tiene lotes, aunque estén terminados,
   porque el origen de las transiciones registradas se deduce de su orden (regla 5 de 8.20). Las duraciones se cambian
   siempre y rigen para los cálculos desde ese momento, como la fecha máxima de cosecha.
4. El perfil familiar no se cambia mientras la variedad tenga lotes activos u órdenes a realizar.
5. Si la variedad tiene lotes activos y un cambio de rangos la deja incompatible con las otras variedades de un
   invernadero, el Sistema advierte en qué invernadero y en qué variable. El Agrónomo puede volver a revisar o guardar
   igual: los lotes en producción siguen donde están, y las alertas de ese invernadero se calculan con el rango nuevo.
6. Si cambia el nombre, también cambia el nombre de su semilla. El Sistema lo informa antes de confirmar.
7. Si cambian el nombre, las duraciones, las etapas o los rangos, se notifica al Agrónomo de cada otro invernadero que
   usa la variedad, salvo al actor. El Sistema avisa a quiénes notificará antes de confirmar, y la notificación no
   bloquea el cambio.
8. Antes de guardar, el Sistema presenta un resumen con los datos nuevos, los valores anteriores cuando cambian y el
   nuevo nombre de la semilla. El Agrónomo puede volver a editar, confirmar o cancelar.
9. Una variedad inactiva no se modifica: solo se reactiva, y solo si su cultivo está activo. La reactivación reactiva
   también su semilla, pero no la vuelve a habilitar en los invernaderos donde estaba deshabilitada.

---

## PROD-BAJ-VAR · Baja Variedad

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: dar de baja lógica una variedad que deja de producirse, sin perder su historial de siembras y lotes.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El actor puede gestionar la variedad (regla 1 de PROD-MOD-VAR).
c. La variedad está activa.
d. La variedad no tiene lotes activos.
e. La variedad no tiene órdenes de trabajo a realizar.
f. Ningún contrato vigente o abierto tiene un detalle de la variedad.

**Postcondición:**
a. La variedad quedó en estado «inactivo» (baja lógica) y dejó de ofrecerse para sembrar y para incluirse en
   contratos.
b. Su semilla quedó inactiva y dejó de ofrecerse para pedirse.
c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador de la variedad y de su semilla, y el
   cambio de estado.

**Reglas:**
1. La baja es lógica: la variedad conserva su ciclo, sus etapas, sus lotes terminados, sus siembras y todo su
   historial.
2. Si no se cumple alguna de las precondiciones d a f, el Sistema no da de baja la variedad e informa todo lo que lo
   impide, cada cosa con cómo resolverla: los lotes activos terminan con su cosecha o su merma; las órdenes se
   concretan o se cancelan; los contratos se cumplen o se cierran.
3. Si la semilla está habilitada en otros invernaderos, el Sistema lo informa. Si queda stock de semilla, informa
   cuánto y en qué invernaderos, sin bloquear: ese stock sigue registrado y, si se descarta, se registra con un ajuste
   de stock.
4. Se reactiva con PROD-MOD-VAR.

---

## PROD-CNS-VAR · Consultar Variedad

Actores: Agrónomo.
Tipo: secundario, esencial.
Versión: 0.1

Objetivo: consultar las variedades de cada cultivo con su ciclo, sus condiciones y su semilla.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. Las variedades se consultan dentro de su cultivo (PROD-CNS-CLT), activas e inactivas.
2. De cada variedad se ve su nombre, su perfil familiar y su estado; la duración de su ciclo, con sus etapas y la
   duración de cada una; y su semilla, con los invernaderos donde está habilitada (o «sin habilitar»).
3. En el formulario de la variedad se ven además sus rangos ambientales, su postcosecha, su peso y los otros
   invernaderos que la usan.
4. Desde una variedad activa, el Agrónomo que puede gestionarla inicia PROD-MOD-VAR o PROD-BAJ-VAR. Desde una variedad
   inactiva, solo puede reactivarla, y solo si su cultivo está activo. Si no puede gestionarla, las acciones aparecen
   deshabilitadas con el nombre de quién la usa.
5. El Gerente no consulta variedades.
6. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-49)

Tarea: **INV-03** (`docs/tareas/inventario/INV-03-variedades-y-semillas.md`). Los cuatro casos de uso se implementan completos, salvo
las partes que dependen de lo que todavía no existe (marcadas abajo). Las tablas `Variedad`, `Ciclo` y `EtapaProductiva` las creó
MAE-03; los servicios, las pantallas de variedades y `Semilla` son de `inventario` (D-49).

### Qué hace cada parte, y con qué se completa

| Qué depende de otra tarea | Regla | Cómo queda en INV-03 |
|---|---|---|
| Lotes de la variedad (todos, para las etapas) y lotes activos (para el perfil, el uso y la baja) | MOD reglas 1, 3, 4 y 5; BAJ precondición d | Por `registrar_uso_de_variedad` (`docs/api/extensiones_de_inventario.md`). **Sin registrante** (hasta PRD-01): ninguna variedad tiene lotes, así que las etapas y el perfil se cambian siempre, y ningún invernadero «la usa» por lotes |
| Órdenes de trabajo a realizar de la variedad | MOD regla 4; BAJ precondición e | Por `registrar_uso_de_variedad` y `registrar_impedimento_de_baja_de_variedad` (código `ordenes_a_realizar`). Sin registrante: ninguna |
| Variedades presentes en un invernadero (para la advertencia de rangos) | MOD regla 5 | Por `registrar_variedades_presentes`. Sin registrante: nunca hay advertencia |
| Contratos vigentes o abiertos con un detalle de la variedad | BAJ precondición f | Por `registrar_impedimento_de_baja_de_variedad` (código `contratos_abiertos`, lo registra `comercial`). **Hasta entonces la precondición f no se verifica** (no hay contratos): es un hueco conocido de la ronda, anotado en `docs/temas_abiertos.md` |
| Alerta de rangos y umbral efectivo de un invernadero | MOD regla 5, parte final («las alertas de ese invernadero se calculan con el rango nuevo») | No hay nada que hacer en INV-03: las alertas de IoT leen la variedad vigente cuando se calculan (módulo IoT, fuera de la ronda) |
| Habilitar la semilla en un invernadero | ALT regla 9 | La pantalla final ofrece el botón que abre CMP-HAB-IIN (INV-02, `habilitar_insumo`). Por eso INV-03 **depende de INV-02** |

### Decisiones de aplicación (donde el caso de uso no baja al detalle)

- **Dónde está cada cosa (D-49).** Servicios en `inventario/servicios/variedades.py` (los cuatro casos de uso), `ciclos.py` (lectura:
  etapas ordenadas, duración, días hasta Maduración) y `semillas.py` (crear, renombrar, dar de baja y reactivar la semilla). Archivos
  de pruebas: `inventario/tests/test_prod_alt_var.py` y los análogos. `Semilla` es `inventario.Semilla(Insumo)` con la FK uno a uno a
  `maestros.Variedad` (`docs/modelo/inventario.md`, ficha `Semilla`).
- **Largos de los nombres (los CU no los fijan).** Variedad hasta 50 caracteres, cultivo hasta 40 (MAE-03): el nombre de la semilla
  «Semilla {cultivo} {variedad}» llega a 99 y entra en los 100 del insumo. Si un nombre ya guardado pasara (datos viejos), el servicio rechaza
  el alta con un error por campo en vez de truncar.
- **Quién puede gestionar (regla 1 de MOD).** Un invernadero «usa» la variedad si está **activo** y tiene la semilla habilitada
  (`InsumoInvernadero` activo) o lotes activos de ella. `puede_gestionar(actor, variedad)`: verdadero si el Agrónomo tiene a cargo un
  invernadero de los que la usan, o si ninguno la usa (cualquier Agrónomo activo). Si no puede, el mensaje nombra los invernaderos y a
  su Agrónomo, o «sin Agrónomo». Si todos los invernaderos que la usan están sin Agrónomo, **nadie puede gestionarla** hasta que el
  Gerente asigne uno (queda en `docs/temas_abiertos.md`). Se verifica **después de bloquear**, no solo al abrir la pantalla.
- **Las acciones de la consulta (regla 4 de CNS).** Se calculan con la misma función `acciones_permitidas`: variedad activa y gestora →
  Modificar y Dar de baja; inactiva → solo Reactivar, y solo si el cultivo está activo («Primero reactivá el cultivo X») y el actor puede gestionarla;
  sin permiso → deshabilitadas con el texto «Solo la usa …».
- **El formulario también es la consulta de detalle (regla 3 de CNS).** `/produccion/variedades/<id>/` abre el formulario con todos los
  datos. Para quien no puede modificar (variedad inactiva o sin permiso) los campos se ven **deshabilitados** y con el motivo; así se
  ven los rangos, la postcosecha, el peso y los otros invernaderos que la usan sin ofrecer una acción que no puede hacer.
- **Perfil y etapas permitidas (reglas 3 y 4 de ALT).** Al elegir el perfil, la pantalla ofrece solo las etapas de ese perfil
  (`TipoEtapa.perfiles_permitidos`); al cambiar de perfil se desmarcan las que no corresponden. El servicio lo vuelve a validar:
  nunca confía en la pantalla. Germinación y Maduración se marcan siempre y no se pueden sacar. Un cambio de perfil que deje una etapa no
  permitida se rechaza con un error en el campo del perfil.
- **Cálculos derivados.** La duración del ciclo es la suma de las duraciones de sus etapas (nunca se guarda). La «cosecha estimada» es
  la suma de las etapas **anteriores** a Maduración (el día en que entra a Maduración, regla 5 de ALT); se muestra en el formulario y
  en el resumen.
- **Topes (aprobados el 19/11/2026, D-49; los CU no los fijan).** Humedad entre 0 y 100 y fotoperíodo entre 0 y 24; error: «Ingrese un valor entre 0 y 100.» / «Ingrese un valor entre 0 y 24.». Temperatura e intensidad lumínica sin tope.
- **Números.** Los rangos aceptan coma o punto decimal y guardan `Decimal` con 2 decimales (se rechaza más de 2); postcosecha y peso
  son enteros. Mínimo igual al máximo es válido (regla 6). Los textos de error son los del prototipo (`varCalc`).
- **Resumen antes de confirmar (ALT regla 8, MOD regla 8).** Dos pasos en la pantalla: «Revisar resumen» valida todo en el servidor
  (`resumen_de_alta` / `resumen_de_modificacion`, que no escriben) y muestra el resumen; «Crear variedad» / «Guardar cambios»
  **vuelve a validar todo** dentro de la transacción. El resumen de la modificación muestra los datos nuevos, los valores anteriores
  donde cambian, el nombre nuevo de la semilla y a quiénes se notificará. «Volver a editar» regresa al formulario con lo ya escrito.
- **Advertencia de rangos (MOD regla 5).** Solo si el cambio modifica algún rango y la variedad tiene lotes activos en algún invernadero.
  Para cada invernadero donde la variedad tiene lotes activos, se compara el rango **nuevo** con el de cada otra variedad presente
  (lotes activos u órdenes de siembra a realizar, la definición del «umbral efectivo» de PROD-PNF-SMB): hay incompatibilidad en una
  variable si `max(mínimos) > min(máximos)`. Comparar de a pares equivale a mirar la intersección de todas (los rangos son intervalos de
  una dimensión), y permite nombrar con quién choca. El servicio lanza `FaltaConfirmarAdvertencia` con la lista (invernadero, variable,
  variedad con la que choca) si no recibe `advertencia_confirmada=True`; la pantalla ofrece «Volver a revisar» y «Guardar igual».
- **Notificaciones (MOD post c y regla 7).** A cada Agrónomo de otro invernadero que usa la variedad, una vez por cuenta (no por
  invernadero), con los invernaderos que le corresponden, **solo si cambió nombre, duraciones, etapas o rangos** (no perfil, postcosecha ni
  peso), sin el actor (`excluir`), dentro de la transacción y sin bloquear. Un invernadero sin Agrónomo no recibe nada (D-14). Mismo texto
  que el prototipo. No se auditan (D-42).
- **Auditoría (D-36).** **Un registro por caso de uso**, con la variedad, el ciclo, las etapas y la semilla como afectados: acciones
  `alta_variedad`, `modificacion_variedad`, `baja_variedad` y `reactivacion_variedad`. Las duraciones y los rangos, como texto; las
  etapas incluidas y sus duraciones, en `datos` (alta) y en `cambios` (modificación: «etapas» antes y después, con una lista de
  textos «Germinación: 5 días»). Si cambia el nombre de la semilla, va en el mismo registro (`cambios` de la semilla). La consulta no
  se audita (SEG-14). El renombre de la semilla por el **cultivo** (PROD-MOD-CLT) es aparte: lo escribe `renombrar_semillas` con la acción
  `modificacion_semilla`.
- **«Sin cambios» no audita (D-28):** guardar la modificación sin haber cambiado nada no crea registro ni notifica.
- **Reactivación (MOD regla 9).** Una variedad inactiva no se edita: solo se reactiva, con el cultivo activo (se bloquea el cultivo
  antes de verificarlo). Reactiva la variedad y su semilla y **no toca las existencias de la semilla**: no vuelve a habilitar las que estaban
  deshabilitadas, y las que quedaron activas con la baja siguen activas.
- **Baja (BAJ).** Todos los impedimentos juntos, sin quedarse con el primero, cada uno con cómo resolverlo (regla 2): los de `lotes_activos`
  y `ordenes_a_realizar` (PRD-01) y `contratos_abiertos` (`comercial`). Informa sin bloquear dónde está habilitada la semilla y cuánto
  stock queda en cada invernadero (regla 3). Deja inactiva a la semilla **sin deshabilitar sus existencias** (se descarta con un ajuste,
  CMP-AJT-STK, que ofrece las existencias activas aunque la semilla esté inactiva) y reevalúa las alertas de cada existencia
  (`reevaluar_alertas_del_insumo`: la de «bajo el mínimo» se resuelve porque el insumo está inactivo).
- **Bloqueos.** Orden de `docs/patrones/stock.md`, sección 5: si la operación toca existencias de la semilla (baja y reactivación), primero
  los invernaderos donde está habilitada (se leen sin bloquear, se bloquean en orden de id y se vuelve a leer); después el cultivo, la
  variedad y la fila del insumo de la semilla. Alta y modificación no bloquean invernaderos: toman cultivo → variedad → insumo. Dos
  altas del mismo nombre: la segunda ve el nombre ya usado (y la restricción única de la base la respalda). Una baja del cultivo contra un alta
  de variedad: se serializan por la fila del cultivo.
- **Permisos.** Solo el Agrónomo activo. El Gerente no consulta variedades (regla 5 de CNS): ni en la pestaña (404 por URL) ni en el menú.
- **Sin JavaScript** (`.claude/rules/interfaz.md`): el formulario y el resumen funcionan como páginas; la baja es una página con
  confirmación.

### Diferencias con el modelo de dominio

El modelo dice `pesoPromedioPlanta` en kilogramos; el CU, el glosario y MD-69 dicen **gramos**: manda el CU (ya está en
`docs/modelo/maestros.md`). El modelo (regla 3 de 8.4) dice que al pasar un insumo a inactivo se deshabilitan todas sus existencias; el
CU de baja de variedad (regla 3) conserva las de la semilla: manda el CU (`docs/modelo/inventario.md`, «Diferencias», fila 6).
