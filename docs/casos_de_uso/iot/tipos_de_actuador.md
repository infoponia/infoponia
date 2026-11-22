# Casos de uso · iot · Tipos de actuador

Copia para el repo de los casos IOT-ALT-TAC (v0.4), IOT-MOD-TAC (v0.4), IOT-BAJ-TAC (v0.2) e IOT-CNS-TAC (v0.3) de «CU extendidos»
(sección de alto nivel; Lote 1 v5.6 del IoT, pegado el 20/11/2026 y cotejado el 21/11/2026). Reemplazan a la parte de tipos de actuador de
CU-82 a CU-85 de la «Documentación para la IA». Cotejado con pendientes_MD hasta MD-113 (MD-98, MD-103 y MD-104) y con el glosario del
19/11/2026.

Son casos de uso breves (de alto nivel). **El código va en la app `iot`** (D-37, nivel 7). Si este archivo y Drive no coinciden, avisá: no
elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las
postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| IOT-ALT-TAC | Alta Tipo de Actuador | Gerente | `iot/tests/test_iot_alt_tac.py` |
| IOT-MOD-TAC | Modificar Tipo de Actuador (con la reactivación) | Gerente | `iot/tests/test_iot_mod_tac.py` |
| IOT-BAJ-TAC | Baja Tipo de Actuador | Gerente | `iot/tests/test_iot_baj_tac.py` |
| IOT-CNS-TAC | Consultar Tipo de Actuador | Gerente y Agrónomo | `iot/tests/test_iot_cns_tac.py` |

## IOT-ALT-TAC · Alta Tipo de Actuador

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.4

**Objetivo:** registrar una clase de actuador con las acciones que admite, cada una asociada a un comando del catálogo de capacidades, para poder dar de alta actuadores de ese tipo.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. No existe otro tipo de actuador con el mismo nombre.

**Postcondición:**

a. Se creó un tipo de actuador en estado «activo», con su nombre, su tiempo mínimo entre comandos y al menos una acción. Cada acción tiene su nombre, el comando del catálogo de capacidades que la ejecuta y, si ese comando lleva un valor, la unidad (de la lista de unidades de ese comando, regla 10), el mínimo y el máximo de ese valor.

b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del tipo de actuador y de cada acción creados.

**Reglas:**

1. Solo el Gerente activo registra tipos de actuador. El catálogo es el mismo para toda la organización y un tipo describe un modelo de equipo, no un invernadero: por eso no tiene el alcance por invernadero de la regla 1 de IOT-DSC-SIS y lo administra un solo actor, para que un cambio no afecte a invernaderos ajenos sin que su Agrónomo lo decida.

2. El nombre es obligatorio y único entre todos los tipos de actuador, activos o inactivos, sin distinguir mayúsculas ni espacios al principio o al final.

3. Un tipo tiene al menos una acción (R059). Los nombres de las acciones son únicos dentro del tipo, y dos acciones del mismo tipo no usan el mismo comando.

4. Si el comando de la acción lleva un valor, su unidad, su mínimo y su máximo son obligatorios; la unidad se elige de la lista cerrada del comando (regla 10), no se escribe; el mínimo y el máximo son números enteros, con el mínimo menor que el máximo; por ejemplo, de 0 a 100 % para fijar una posición. Todo valor que se aplique con esa acción, en una regla de actuación o en un comando, es un número entero dentro de ese rango. Si el comando no lleva valor, la acción no tiene unidad ni rango. El rango depende de la unidad (D-80): con «%», el mínimo y el máximo van de 0 a 100; con «rpm», «L/min» y «cm», el mínimo es 0 o más y no hay tope; con «°» no hay límite fijo.

5. En la puesta en marcha se precarga un catálogo inicial de tipos, todos con un tiempo mínimo entre comandos de 60 segundos: ventilador (encender, apagar y fijar velocidad de 0 a 100 %), bomba (encender y apagar), luminaria (encender y apagar), calefactor (encender y apagar), ventana (abrir, cerrar y fijar posición de 0 a 100 %) y media sombra (abrir, cerrar y fijar posición de 0 a 100 %).

6. El Agrónomo no registra tipos de actuador. Si necesita uno que no existe, se lo pide al Gerente (IOT-ALT-HDW, regla 7). Si dos invernaderos necesitan tiempos mínimos distintos para el mismo equipo, es porque son modelos distintos: se registran dos tipos.

7. Catálogo de capacidades: conjunto fijo de capacidades con sus comandos, que forma parte del contrato de la API con el nodo central: «encendido» (ENCENDER y APAGAR, sin valor), «nivel» (FIJAR_NIVEL, con valor) y «posición» (ABRIR y CERRAR, sin valor, y FIJAR_POSICION, con valor). Se carga al poner en marcha el sistema y no tiene alta, baja ni modificación, como el Tipo de Etapa; cambia solo con una nueva versión de la API. El nodo central traduce cada comando al mensaje que entiende su equipo.

8. Si una acción requiere un valor no se elige: se deduce de su comando.

9. Tiempo mínimo entre comandos: segundos que deben pasar entre dos comandos ejecutados sobre un mismo actuador del tipo, para no dañar el equipo con cambios demasiado seguidos. Es obligatorio y es un número entero no negativo (valor inicial 60, a confirmar con el Jardín Botánico). Una regla de actuación no emite antes de ese tiempo; un comando manual se advierte y se permite (IOT-ENT-INF e IOT-EMT-CMD).

10. Unidades de los valores: lista cerrada que fija el Sistema para cada comando con valor, sin alta, baja ni modificación y versionada con la API, como el catálogo de capacidades (regla 7). FIJAR_NIVEL: «%» (porcentaje de la potencia), «rpm» (vueltas por minuto) y «L/min» (litros por minuto). FIJAR_POSICION: «%» (porcentaje de apertura), «°» (grados) y «cm» (centímetros). Se evita el texto libre para que la misma unidad no se escriba de maneras distintas («%», «porcentaje», «pct»), porque la unidad aparece en las reglas, los comandos y las consultas. El nodo recibe solo el número: la unidad es para quien lee, y el rango de la acción es lo que acota los valores válidos.

## IOT-MOD-TAC · Modificar Tipo de Actuador

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.4

**Objetivo:** cambiar el nombre o el tiempo mínimo entre comandos de un tipo de actuador, agregar, modificar o quitar acciones, o reactivar un tipo dado de baja.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. Si cambia el nombre, no existe otro tipo de actuador con el nombre nuevo.

**Postcondición**, según lo que haya hecho el actor:

a. Se actualizaron el nombre del tipo, su tiempo mínimo entre comandos y sus acciones. Una acción quitada que tenía comandos en su historial quedó inactiva; una que no tenía, se eliminó.

b. Si reactivó el tipo, quedó en estado «activo».

c. Si cambiaron las acciones, cada actuador no dado de baja del tipo quedó marcado «compatible», «incompatible» o «sin verificar» según el último anuncio de su nodo, con sus acciones incompatibles, y su alerta «configuración incompatible» se generó o se resolvió.

d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del tipo y sus cambios, con las listas de las acciones creadas, modificadas, desactivadas y borradas, y de las alertas generadas o resueltas.

**Reglas:**

1. Solo el Gerente activo modifica o reactiva un tipo de actuador, sin el alcance por invernadero de la regla 1 de IOT-DSC-SIS (regla 1 de IOT-ALT-TAC).

2. El nombre, las acciones y el tiempo mínimo siguen las reglas 2 a 4, 8, 9 y 10 de IOT-ALT-TAC.

3. Se pueden agregar acciones, cambiar el nombre del tipo y su tiempo mínimo, y ampliar el rango de una acción, sin restricciones.

4. Una acción en uso, es decir, usada por una regla de actuación activa o por un comando pendiente, no se quita, no se renombra y no cambia su comando ni su unidad. Su rango se achica solo si ningún valor de esas reglas o comandos queda afuera. El Sistema informa qué reglas o comandos lo impiden. Una acción con comandos en su historial no cambia su comando ni su unidad, para que esos comandos conserven su significado: para otro comando o para otra unidad se agrega una acción nueva.

5. El tipo conserva siempre al menos una acción activa.

6. Los cambios rigen para todos los actuadores del tipo. Antes de guardar, el Sistema informa cuántos actuadores lo usan y de qué invernaderos, porque el Gerente cambia equipos que operan Agrónomos distintos.

7. Un tipo inactivo no se modifica: solo se reactiva, y después se modifica como cualquier otro.

8. Una acción quitada que tiene comandos en su historial no se elimina: queda inactiva, deja de ofrecerse y conserva el historial.

9. Si cambian las acciones, antes de guardar el Sistema compara los comandos de las acciones activas con el último anuncio del nodo de cada actuador del tipo e informa cuáles quedarían incompatibles, de qué invernadero y con qué acciones. Igual que en el alta (regla 14 de IOT-ALT-HDW), la incompatibilidad se advierte y no impide guardar; los actuadores cuyo nodo no anuncia sus equipos quedan «sin verificar». La comparación se hace en ese momento, sin esperar al próximo anuncio del nodo.

## IOT-BAJ-TAC · Baja Tipo de Actuador

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.2

**Objetivo:** dar de baja lógica un tipo de actuador que ya no se usa.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. El tipo de actuador está activo.

c. Ningún actuador que no esté dado de baja es de ese tipo.

**Postcondición:**

a. El tipo de actuador quedó en estado «inactivo» (baja lógica) y dejó de ofrecerse en IOT-ALT-HDW e IOT-MOD-HDW.

b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del tipo y el cambio de estado.

**Reglas:**

1. La baja es lógica: el tipo conserva sus acciones y el historial de los comandos y las reglas que las usaron.

2. Si algún actuador que no está dado de baja es de ese tipo, el Sistema no lo da de baja e informa cuántos son y de qué invernaderos.

3. Se reactiva con IOT-MOD-TAC.

## IOT-CNS-TAC · Consultar Tipo de Actuador

**Actores:** Gerente y Agrónomo.

**Tipo:** secundario, esencial.

**Versión:** 0.3

**Objetivo:** consultar los tipos de actuador con sus acciones.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

**Postcondición:**

a. No se producen cambios en el Sistema.

**Reglas:**

1. El Gerente y el Agrónomo consultan todos los tipos de actuador, activos e inactivos, sin el alcance por invernadero de la regla 1 de IOT-DSC-SIS: el Agrónomo necesita ver las acciones de un tipo para elegirlo al registrar un equipo y para entender una alerta «configuración incompatible».

2. De cada tipo se ven su nombre; su tiempo mínimo entre comandos; sus acciones activas, cada una con su comando y la capacidad a la que pertenece, si requiere un valor, su unidad, su mínimo y su máximo, y la marca «en uso» si la usa una regla de actuación activa o un comando pendiente; la cantidad de actuadores de ese tipo, y su estado.

3. Solo el Gerente administra los tipos: desde un tipo activo inicia IOT-MOD-TAC o IOT-BAJ-TAC, y desde un tipo inactivo solo puede reactivarlo con IOT-MOD-TAC. El Agrónomo solo consulta.

4. La consulta no se audita (SEG-14).

## Cómo se aplica en la ronda «IoT 1» (D-44, D-72)

Tarea: **IOT-01**. Todo lo de este archivo se implementa, salvo lo marcado «Se completa en IOT-NN», que necesita comandos, reglas o
equipos que todavía no existen (está también en `docs/disparadores.md`). Modelo: `docs/modelo/iot.md`, «Catálogo de capacidades»,
«TipoActuador» y «Accion». Decisiones de aplicación:

- **Quién (regla 1 de ALT, MOD y BAJ; regla 1 de CNS).** Alta, modificación, reactivación y baja: solo el Gerente activo
  (`rol_requerido(GERENTE)`; el Agrónomo recibe 403 y no ve los botones). Consulta: Gerente y Agrónomo. No hay alcance por invernadero.
- **Catálogo (reglas 7, 8 y 10 de ALT).** `Capacidad` y `ComandoCatalogo` se cargan con una migración de datos de `iot` (tres capacidades,
  seis comandos; `docs/modelo/iot.md`). Las unidades son `iot/catalogo.py`, `UNIDADES_POR_COMANDO` (`dict` de código de comando a lista de
  pares valor-texto). Ninguna pantalla los edita. «Requiere valor» se muestra como `comando.lleva_valor`; no se guarda.
- **Tipos iniciales (regla 5 de ALT).** Los seis tipos de la ficha, con sus acciones, en una migración de datos de `iot` que se aplica
  **después** de la del catálogo y que no hace nada si ya existe un tipo con ese nombre (sin distinguir mayúsculas). No se auditan.
- **Nombre del tipo (regla 2 de ALT).** Obligatorio, hasta 60 caracteres, recortado. Único entre activos e inactivos: `UniqueConstraint(Lower("nombre_actuador"))`. Dos altas simultáneas con el mismo nombre dan a la segunda el error del campo, nunca un 500 (`docs/patrones/abm.md`, sección 2, paso 6). Mensaje: «Ya existe un tipo de actuador con ese nombre.».
- **Tiempo mínimo (regla 9 de ALT).** Entero de 0 en adelante, en segundos; el formulario propone 60. Mensaje: «Ingresá un número entero de
  segundos (0 o más).».
- **Acciones (reglas 3, 4 y 8 de ALT).** Se cargan en el mismo formulario del tipo («Agregar acción»). Cada una: nombre (obligatorio, hasta
  40), comando del catálogo (lista agrupada por capacidad) y, si el comando lleva valor, mínimo, máximo (enteros, mínimo < máximo) y unidad
  (lista del comando; el formulario propone `%`). Al cambiar a un comando sin valor se vacían unidad y rango. Textos de error del prototipo
  (`save-tac`): «El tipo necesita al menos una acción activa.», «Cada acción necesita un nombre.», «Elegí el comando de «X».», «La acción «X» está repetida.», «Dos acciones usan el comando Y.», «“X” necesita un mínimo y un máximo enteros, con el mínimo menor al máximo.», «“X” necesita una unidad.».
- **Modificar (reglas 3 a 9 de MOD).** El servicio recibe la lista completa de acciones del formulario, cada una con el id de la acción
  original si la tenía, y la compara con las guardadas:
  - **En uso** = usada por una regla de actuación activa o un comando pendiente (`acciones_en_uso(tipo) -> dict[int, list[UsoDeAccion]]`: por id de acción, sus usos, cada uno con su código `RGL-n` o `CMD-n` y el valor que aplica; así el Sistema informa qué los impide y controla el achique del rango); **con historial** = algún comando
    la usó. **Se completan en IOT-05 (comandos) e IOT-06 (reglas):** en IOT-01 las dos funciones devuelven «ninguna», con su prueba de que se
    llaman; las tareas de comandos y reglas les suman la consulta y la prueba.
  - Una acción en uso no se quita, no se renombra y no cambia su comando ni su unidad; su rango se achica solo si ningún valor de esas reglas o comandos queda afuera (los mensajes del prototipo: «No se puede quitar «X»: la usan …», etc.).
  - Una acción con historial no cambia su comando ni su unidad (la pantalla deshabilita los dos campos con la explicación).
  - Quitar: con historial, queda `inactiva`; sin historial, **se borra** (postcondición a).
  - El tipo conserva al menos una acción activa (regla 5).
- **Aviso de equipos afectados (regla 6 de MOD).** Antes de guardar, el formulario dice «Los cambios afectan a N equipo(s) de este tipo:
  Invernadero Norte (3), Invernadero Sur (1).». **Se completa en IOT-02**: en IOT-01 todavía no hay actuadores y el aviso no se muestra.
- **Compatibilidad (regla 9 de MOD, postcondición c).** Si cambian las acciones, antes de guardar se compara con el último anuncio del nodo
  de cada actuador del tipo y se pide «Guardar igual» si alguno quedaría incompatible. Al guardar se recalcula la compatibilidad y se genera
  o resuelve la alerta `iot_configuracion_incompatible`. La función que recalcula es `iot/servicios/compatibilidad.py`,
  `recalcular_compatibilidad(actuadores)`, **que crea IOT-02** (la usan el alta y la modificación del hardware). **Se completa en IOT-02:** en
  IOT-01 no hay actuadores; `modificar_tipo_actuador` ya la llama sobre la lista vacía.
- **Reactivar (postcondición b de MOD, regla 7 de MOD, regla 3 de BAJ).** Un tipo inactivo solo muestra «Reactivar» (no se edita).
  `reactivar_tipo_actuador(actor, tipo_id)`: pasa a activo; si otro tipo **activo o inactivo** tiene el mismo nombre, no puede pasar (la
  unicidad es entre todos). Auditoría aparte.
- **Baja (BAJ).** `baja_tipo_actuador(actor, tipo_id)`: bloquea el tipo, cuenta los actuadores no dados de baja del tipo y, si hay, rechaza
  con «Hay N equipo(s) de este tipo en Invernadero Norte e Invernadero Sur. Dalos de baja antes de dar de baja el tipo.» (regla 2). **Se
  completa en IOT-02**, cuando existen actuadores: en IOT-01 la cuenta es siempre 0, pero la consulta ya se escribe y se prueba con un
  actuador creado por la fábrica.
- **Consulta (CNS).** Lista de todos los tipos (activos primero, después por nombre), con: código `TAC-NN` (el id con dos dígitos), nombre,
  acciones activas (nombre, comando, rango y unidad, y la marca «en uso»), tiempo mínimo, cantidad de equipos no dados de baja y estado. El
  catálogo de capacidades se muestra debajo, en solo lectura («Forma parte del contrato de la API con el nodo · no se edita»). Para el
  Agrónomo, el aviso «Los tipos de actuador los administra el Gerente…» del prototipo.
- **Bloqueos.** Alta: nada que bloquear (la base respalda el nombre). MOD, reactivación y baja: el tipo con `FOR NO KEY UPDATE` y releído,
  después sus acciones en orden de id. Sin cambios no se escribe ni se audita (D-28). Dos modificaciones a la vez: gana la última, salvo el
  nombre, que respalda la base.
- **Auditoría (D-36).** Un registro por caso de uso: `alta_tipo_actuador`, `modificacion_tipo_actuador`, `reactivacion_tipo_actuador` y
  `baja_tipo_actuador`. Afectados: el tipo y cada acción creada, modificada, desactivada o borrada (la borrada, como `referencia()` tomada
  antes de borrar). En `cambios`, el nombre y el tiempo mínimo con «antes» y «después» y, de cada acción modificada, un cambio por cada dato que cambió
  (nombre, comando, unidad, mínimo y máximo; la clave dice qué cambió y de qué acción, con su nombre anterior: «Comando de la acción «Apagar»»); en `datos`, las listas `acciones_creadas`,
  `acciones_modificadas`, `acciones_desactivadas` y `acciones_borradas`.

## Pantallas

Guía visual: `docs/prototipos/iot/`. Buscá la función y leé solo esa parte (`docs/prototipos/iot/README.md`).

| Pantalla | Función en el prototipo | Casos de uso |
|---|---|---|
| IoT · pestaña «Tipos de actuador» (lista y catálogo) | `tipos` (rama final), `ctxBar` (con el invernadero deshabilitado) | IOT-CNS-TAC |
| Nuevo y modificar tipo | `tipos` (rama `tac-form`), `cmdOpts`, `unidOpts`, `act` (casos `tac-new`, `tac-mod`, `acc-add`, `acc-del`, `save-tac`) | IOT-ALT-TAC, IOT-MOD-TAC |
| Dar de baja | `modalHtml` (`tbaj`) | IOT-BAJ-TAC |

**Lo que difiere del prototipo (manda el CU, L7):**

- El prototipo **borra** el tipo al darlo de baja (`DB.tipos.splice`): la baja es lógica y el tipo queda inactivo, visible en la lista con
  su marca y con «Reactivar».
- El prototipo no tiene «Reactivar» ni muestra los tipos inactivos: se agregan (regla 7 de MOD y regla 1 de CNS).
- El prototipo no marca «en uso» en la lista (regla 2 de CNS): se agrega.
- Los nombres de los tipos iniciales y sus acciones son los de la regla 5 de ALT (coinciden con el prototipo).

**Textos explicativos** (además de los del prototipo):

- Bajo el título: «Definen qué acciones admite cada clase de equipo y con qué comando del catálogo se ejecutan. Son de toda la organización:
  un cambio afecta a los equipos de todos los invernaderos.»
- En el formulario, bajo «Tiempo mínimo entre comandos»: «Protege el equipo de cambios demasiado seguidos. Las reglas de actuación no emiten
  antes de este tiempo; un comando manual lo advierte.»

## Para más adelante

Cada punto está también en `docs/disparadores.md`, «Cuando existan actuadores, comandos y reglas del IoT».

- IOT-02: el aviso de equipos afectados de la regla 6 de MOD; la compatibilidad de la regla 9 de MOD sobre actuadores reales; el conteo de
  la baja con actuadores registrados.
- IOT-05: «con historial» y «en uso» por comandos.
- IOT-06: «en uso» por reglas de actuación activas.

## Solo prototipo

Los de `docs/prototipos/iot/README.md`, «Solo prototipo». En estas pantallas, además: el borrado físico del tipo y los códigos `TAC-01` a
`TAC-06` fijos (en el sistema salen del id).
