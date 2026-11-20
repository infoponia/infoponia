# Casos de uso · maestros · Cultivo

Copia para el repo de los casos PROD-ALT-CLT, PROD-MOD-CLT, PROD-BAJ-CLT y PROD-CNS-CLT del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96, y con el glosario del 15/11/2026.

Son casos de uso breves (de alto nivel). **El código va en la app `maestros`** (D-37); el archivo de pruebas es
`maestros/tests/test_prod_alt_clt.py` y los análogos.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-ALT-CLT | Alta Cultivo | Agrónomo | `maestros/tests/test_prod_alt_clt.py` |
| PROD-MOD-CLT | Modificar Cultivo | Agrónomo | `maestros/tests/test_prod_mod_clt.py` |
| PROD-BAJ-CLT | Baja Cultivo | Agrónomo | `maestros/tests/test_prod_baj_clt.py` |
| PROD-CNS-CLT | Consultar Cultivo | Agrónomo | `maestros/tests/test_prod_cns_clt.py` |

---

## PROD-ALT-CLT · Alta Cultivo

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** registrar un cultivo nuevo con su nombre, para poder crear después sus variedades.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. No existe otro cultivo con el mismo nombre.

**Postcondición:**
a. Se creó un cultivo en estado «activo», con su nombre y sin variedades.
b. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del cultivo creado.

**Reglas:**
1. Cualquier Agrónomo activo registra cultivos: el cultivo no pertenece a un invernadero y lo comparten todos.
2. El nombre es obligatorio y único entre todos los cultivos, activos o inactivos, sin distinguir mayúsculas ni
   espacios al principio o al final.
3. El cultivo se crea sin variedades. Sus variedades se registran después con Alta Variedad.

---

## PROD-MOD-CLT · Modificar Cultivo

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** cambiar el nombre de un cultivo, o reactivar uno dado de baja.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. Si cambia el nombre, no existe otro cultivo con el nombre nuevo.

**Postcondición, según lo que haya hecho el actor:**
a. Si cambió el nombre, el cultivo quedó con el nombre nuevo y la semilla de cada una de sus variedades quedó con su
   nombre actualizado.
b. Si cambió el nombre y otros invernaderos usan alguna de sus variedades, el Agrónomo de cada uno de esos
   invernaderos recibió una notificación dentro del Sistema con el nombre anterior y el nuevo.
c. Si reactivó el cultivo, quedó en estado «activo».
d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del cultivo y los cambios, y otro por cada
   semilla que cambió de nombre.

**Reglas:**
1. El único dato que se modifica es el nombre, con la regla 2 de PROD-ALT-CLT.
2. Cualquier Agrónomo activo modifica o reactiva cualquier cultivo.
3. La semilla de cada variedad se llama «Semilla {cultivo} {variedad}». Por eso, al renombrar el cultivo se renombran
   sus semillas. Antes de confirmar, el Sistema informa cuántas semillas cambian de nombre.
4. Un invernadero usa una variedad si está activo y tiene su semilla habilitada o lotes activos de ella. Se notifica
   al Agrónomo de cada invernadero que usa alguna variedad del cultivo, salvo al actor. La notificación no bloquea el
   cambio.
5. Un cultivo inactivo no se modifica: solo se reactiva, y después se modifica como cualquier otro.
6. La reactivación no tiene validaciones y no reactiva sus variedades: se reactivan una por una con Modificar
   Variedad.

---

## PROD-BAJ-CLT · Baja Cultivo

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** dar de baja lógica un cultivo que ya no se produce, sin perder su historial.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.
b. El cultivo está activo.
c. El cultivo no tiene variedades activas.

**Postcondición:**
a. El cultivo quedó en estado «inactivo» (baja lógica) y dejó de ofrecerse para registrar variedades.
b. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del cultivo y el cambio de estado.

**Reglas:**
1. La baja es lógica: el cultivo conserva sus variedades inactivas y todo su historial.
2. La baja no es en cascada. Si el cultivo tiene variedades activas, el Sistema no permite darlo de baja y le indica
   al actor cuántas son. Primero se dan de baja con Baja Variedad, que aplica sus propias validaciones.
3. Cualquier Agrónomo activo da de baja un cultivo: como no tiene variedades activas, no lo usa ningún invernadero.
4. Se reactiva con PROD-MOD-CLT.

---

## PROD-CNS-CLT · Consultar Cultivo

**Actores:** Agrónomo. **Tipo:** secundario, esencial. **Versión:** 0.1

**Objetivo:** consultar los cultivos registrados con sus variedades.

**Precondición:**
a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo.

**Postcondición:**
a. No se producen cambios en el Sistema.

**Reglas:**
1. El Agrónomo consulta todos los cultivos, activos e inactivos. Primero se listan los activos, y los inactivos se
   distinguen como tales.
2. De cada cultivo se ve su nombre; su cantidad de variedades activas, o «inactivo» si está dado de baja; y sus
   variedades, cada una con su perfil familiar, la duración de su ciclo con sus etapas, su semilla con los
   invernaderos donde está habilitada (o «sin habilitar») y su estado. Si no tiene variedades, el Sistema lo informa.
3. Desde un cultivo activo, el Agrónomo inicia PROD-MOD-CLT, PROD-BAJ-CLT y Alta Variedad, y en cada variedad,
   Modificar Variedad y Baja Variedad. Desde un cultivo inactivo, solo puede reactivarlo con PROD-MOD-CLT.
4. El Gerente no consulta cultivos.
5. La consulta no se audita (SEG-14).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **MAE-03** (los cultivos) e **INV-03** (las variedades y las semillas). Lo que cada CU de este archivo toca de
variedades y semillas funciona desde MAE-03 con los modelos ya creados y vacíos, y con puntos de extensión
(`docs/api/extensiones_de_maestros.md`) que registra INV-03:

| Qué depende de variedades o semillas | Regla | Cómo queda en MAE-03 |
|---|---|---|
| Renombrar la semilla de cada variedad | MOD post a y d; regla 3 | `contar_semillas_a_renombrar` y `renombrar_semillas`, sin registrantes (0 semillas) hasta INV-03 |
| Invernaderos que usan una variedad (para notificar) | MOD post b; regla 4 | `invernaderos_que_usan_el_cultivo`, sin registrantes (ninguno) hasta INV-03 |
| Variedades activas del cultivo | BAJ precondición c y regla 2; CNS reglas 2 y 3 | Se leen de `Variedad` (modelo creado en MAE-03, tabla vacía); desde el Agrónomo, «Alta Variedad» y las acciones de variedad **no se ofrecen** hasta INV-03 |
| Perfil, ciclo, semilla y habilitación de cada variedad en la consulta | CNS regla 2 | El cuerpo y los botones de variedades de cada tarjeta salen de `registrar_variedades_de_cultivo` (lo registra INV-03); sin registrante, «No tiene variedades» y sin botones |

Decisiones de aplicación:

- **Auditoría (D-36).** Acciones nuevas: `alta_cultivo`, `modificacion_cultivo`, `baja_cultivo`, `reactivacion_cultivo`. La
  postcondición d de MOD pide un log más por cada semilla renombrada: lo escribe `renombrar_semillas` (INV-03), con la
  acción `modificacion_semilla`. La consulta no se audita (SEG-14).
- **Cualquier Agrónomo activo** hace altas, modificaciones y bajas (reglas 1 y 2 de ALT y MOD, regla 3 de BAJ): no hay «a
  cargo». El Gerente no ve cultivos (regla 4 de CNS) y la entrada del menú es solo del Agrónomo.
- **Largo del nombre: hasta 40 caracteres** (lo agrega el lote 3; los CU no fijan largo). Con el nombre de la variedad de hasta 50, el nombre
  de la semilla («Semilla » + cultivo + espacio + variedad) llega a 99 y entra en los 100 del insumo.
- **Variedades en la consulta.** El cuerpo y los botones de variedades de cada tarjeta los arma INV-03 y los entrega por
  `registrar_variedades_de_cultivo` (`docs/api/extensiones_de_maestros.md`).
- **Nombre único** entre todos los cultivos, sin distinguir mayúsculas ni espacios al borde: restricción de la base sobre
  `lower(nombre)` más validación en el servicio.
- **Bloqueos.** Modificar y dar de baja bloquean la fila del cultivo (`FOR NO KEY UPDATE`) y, recién después, lo que bloqueen los
  registrantes (semillas, en orden de id). Dos Agrónomos que renombran a la vez: gana el último, calculado contra lo leído
  después de bloquear (misma convención que `modificar_invernadero`).
- **Notificación de MOD post b** (NOT-01): `notificar_a_varios` al Agrónomo de cada invernadero que usa alguna variedad,
  excluyendo al actor, con el nombre anterior y el nuevo; dentro de la transacción; no bloquea el cambio.

