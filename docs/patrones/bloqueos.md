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
