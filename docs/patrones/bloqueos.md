# Patrón · Bloqueos de filas y pruebas de concurrencia

Resumen vigente de D-30 y D-32 para cualquier servicio que cuide un invariante entre filas o una cantidad (agujeros
libres de un sector, stock de un insumo, reservas). Si algo de acá contradice una de esas decisiones, manda la decisión:
avisá. `CLAUDE.md` («Convenciones») ya pide `select_for_update()` en reservas de stock y en toda operación concurrente
sobre cantidades.

## Cómo se bloquea

- Siempre `select_for_update(no_key=True)` (`FOR NO KEY UPDATE`), nunca `FOR UPDATE`. Al insertar la auditoría, la FK
  hacia quien actúa toma `FOR KEY SHARE` sobre su fila, y `FOR UPDATE` choca con ese bloqueo: así aparecen los deadlocks
  (D-32).
- Orden fijo, el mismo en todos los servicios (D-30, ampliado por D-32):
  1. el **grupo** de filas que cuida un invariante, en orden de `id`;
  2. los **invariantes**, si corresponde;
  3. verificar que **quien actúa** siga activo (pudo quedar inactivo mientras esperaba);
  4. por último, las **filas** que se modifican, en orden de `id`, y **volver a leerlas**.
- Lo que no cambia (por ejemplo, el rol, D-11) se puede leer antes sin bloquear, para saber qué grupo bloquear.
- Lo lento (calcular un resumen de contraseña, mandar un correo) se hace **antes** de bloquear o **fuera** de la
  transacción. Si una verificación hecha antes puede quedar vieja, se guarda lo leído y se **revalida después de
  bloquear**.
- Si lo bloqueado cambió mientras se esperaba, se **rechaza** con un código («cambio_simultaneo») y un mensaje; no se
  reintenta, porque reintentar toma bloqueos fuera de orden.
- Cuando se pueda, una restricción de la base respalda al bloqueo (por ejemplo, para la primera fila, que no tiene nada
  que bloquear). Su `IntegrityError` se traduce a un código conocido con `raise ... from error`: nunca llega un 500.
- Si se bloquea un conjunto filtrado («los activos»), cuidá el caso en que el filtro no devuelve nada: no se bloquea nada
  y dos operaciones pasan juntas. D-30 bloquea todas las filas del grupo, sin filtrar por estado.

## Cómo se prueba

- Las pruebas de concurrencia van en clases `<CodigoCu>ConcurrenciaTests` (`TransactionTestCase`), con
  `@tag("concurrencia")`, y usan `correr_a_la_vez` de `core/tests/concurrencia.py`.
- `correr_a_la_vez(operacion_a, operacion_b, primera, detener_antes_de=None)`:
  - `primera` («a» o «b») es obligatorio: esa operación se detiene en un punto fijo y la otra arranca recién entonces.
    Así la prueba no depende de la velocidad de la máquina.
  - El punto de parada por defecto es `RegistroAuditoria.objects.registrar` (ya tomó sus bloqueos y escribió, sin
    confirmar).
  - `detener_antes_de=(objeto, "nombre")` la detiene justo antes de llamar a esa función. Hace falta para probar el
    **orden** de los bloqueos.
  - Devuelve `{"a": resultado_o_excepcion, "b": ...}`. `separar` y `codigos` ayudan a leer el resultado.
- En local se corren solo si la tarea toca bloqueos o concurrencia (`CLAUDE.md`, «Tests»).
- Si una tarea toca bloqueos, una prueba de concurrencia debe fallar cuando se quita la protección que cuida (D-32 lo
  verificó así). Esos experimentos solo se hacen si la tarea toca bloqueos o el estudiante lo pide.

## Límite conocido

- Un `UPDATE` que cambia una columna con índice único toma `FOR UPDATE` en esa sentencia, se haya bloqueado antes como
  se haya bloqueado (D-32, «Residual»).

## Invernadero (MAE-01b, D-40)

Orden global de bloqueos de `maestros` (siempre `select_for_update(no_key=True)`), el mismo en `modificar_invernadero`,
`reactivar_invernadero`, `baja_invernadero` y en todo caso de uso que se registre en `maestros/extensiones.py`:

1. las filas de **`Usuario`** de quien actúa y de las cuentas de personal enviadas, **en una sola consulta** y en orden de
   id (en `modificar_invernadero`; la baja y la reactivación solo verifican que quien actúa siga activo);
2. el **invernadero**, y volver a leerlo (`_bloquear_invernadero`);
3. **recién después**, lo que bloqueen los registrantes de los puntos de extensión (filas de las apps altas), en orden de id.

La baja de una cuenta con invernaderos a cargo (disparador 4 de «Cuando exista Invernadero») tiene que seguir este orden:
primero la cuenta (como ya hace `baja_usuario`) y después los invernaderos. Si bloquea al revés, hay deadlock con
`modificar_invernadero`.

### Contrato de los puntos de extensión

Todo caso de uso futuro que cree algo que impida la baja de un invernadero (un lote activo, una orden a realizar, una
partida disponible, un movimiento de stock o una orden de compra aprobada, un transportista activo, un sistema IoT activo),
o lo vuelva a poner en ese estado, tiene que, **dentro de su transacción y antes de crearlo**:

```python
from maestros.servicios.invernaderos import bloquear_invernadero_activo
invernadero = bloquear_invernadero_activo(invernadero_id)   # FOR NO KEY UPDATE; rechaza uno inactivo
```

**La clave foránea sola no alcanza.** El `INSERT` toma `FOR KEY SHARE` sobre la fila del invernadero, y ese bloqueo no choca con
el `FOR NO KEY UPDATE` de la baja: la baja no esperaría, no vería lo que todavía no se confirmó y daría de baja un
invernadero con un impedimento. Con el bloqueo, o la baja espera al creador (y después ve el impedimento) o el creador espera a la
baja (y la encuentra inactiva). Está en el docstring de `bloquear_invernadero_activo` y de `maestros/extensiones.py`, y lo
prueban `ProdBajInvConcurrenciaTests` (con un creador falso que tiene una FK real).

Los registrantes de los tres puntos corren dentro de la transacción del servicio, **después** de que este tomó los bloqueos
de arriba; el que bloquee filas propias lo hace después del invernadero y en orden de id.

### El `UPDATE` del invernadero va antes de los traspasos

Cambiar de urbana a rural cambia `Invernadero.direccion_id`, una columna con índice único común (es un `OneToOneField`): ese
`UPDATE` toma `FOR UPDATE` y espera a cualquier transacción que tenga `FOR KEY SHARE` sobre el invernadero (una que insertó una
fila con FK hacia él). Por eso `modificar_invernadero` hace el `UPDATE` **antes** de llamar a los registrantes de traspaso:
mientras espera ahí, solo tiene bloqueadas cuentas y el invernadero, no filas de las apps altas. Si ya las tuviera, la otra
transacción podría estar esperando justo esas filas y se cerraría un ciclo (deadlock). Quien sigue el contrato bloquea el
invernadero antes de insertar, así que no puede tener `FOR KEY SHARE` sobre él mientras espera las cuentas o el invernadero.

### Unicidad del nombre

El nombre es único con `UniqueConstraint(Lower("nombre_invernadero"))`, un índice de expresión: según la documentación de
PostgreSQL 17 (Explicit Locking, `FOR UPDATE`), un `UPDATE` solo toma `FOR UPDATE` por columnas con un índice único «que se
pueda usar en una clave foránea» (no cuentan los índices parciales ni los de expresión). Renombrar **no** sube a `FOR UPDATE`, y
el «Límite conocido» de arriba no aplica al nombre. Sí aplica a `direccion_id` (ver el apartado anterior). Dos renombres al
mismo nombre a la vez: el segundo espera en el índice y recibe un `IntegrityError`, que el servicio traduce a
`nombre_repetido`.

### Quien actúa

`_exigir_actor_sigue_activo` de `core` no bloquea la fila de quien actúa (es un `EXISTS` posterior a los bloqueos). En
`modificar_invernadero` la fila del Gerente entra en la misma consulta que las cuentas de personal, así que **todas las
modificaciones del mismo Gerente se serializan** (hoy hay un solo Gerente activo, D-09). La baja y la reactivación no la
bloquean: se serializan por el invernadero.
