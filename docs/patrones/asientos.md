# Patrón · Cómo crea un asiento un servicio de otra app

Resumen vigente de D-84, D-85 y D-86. Si algo de acá contradice una de esas decisiones, manda la decisión: avisá. El contrato de las
funciones está en `docs/api/asientos.md`; el modelo, en `docs/modelo/contabilidad.md`.

## 1. La receta (cuatro pasos)

Un caso de uso con asiento (por ejemplo, registrar una recepción) hace, **dentro de su `transaction.atomic()`**:

1. Toma sus bloqueos en el orden de su patrón (cuentas, invernadero, sectores, insumos, lotes…, `docs/patrones/bloqueos.md`).
2. Hace su trabajo y **crea el documento de origen** (la recepción, el pago, la entrega…). Ese documento hereda de `OrigenDocumento`.
3. Arma los movimientos con las constantes de `contabilidad/cuentas.py` y llama **una vez** a
   `asientos.registrar_asiento_automatico(actor, origen, fecha_del_hecho, movimientos)`. Si devuelve `None`, no corresponde asiento
   (importe cero): seguí sin error.
4. Registra su propia auditoría (nombrando el asiento si lo hubo). **No** audites el asiento: lo hace la función.

## 2. El orden de bloqueos: el ejercicio va último

`registrar_asiento_automatico` bloquea el `EjercicioContable` destino (`select_for_update(no_key=True)`) para tomar el número siguiente.
Es **lo último que cualquier servicio bloquea**. Por eso:

- Todo caso de uso con asiento termina sus bloqueos de negocio **antes** de llamar a la función, y no bloquea nada después.
- Los servicios de contabilidad que bloquean más de una cosa (el contraasiento) toman primero el asiento a anular y **después** el ejercicio.
- La apertura de un ejercicio (`abrir_ejercicio_si_corresponde`) bloquea la fila del ejercicio abierto y la del en cierre, en orden de `id`, y
  nada más. Si un servicio ya tiene el ejercicio bloqueado, no la llama (la autorrecuperación corre al empezar la función, **antes** de
  bloquear el ejercicio, en una transacción corta propia con `atomic()` anidado).
- El primer ejercicio ya no lo crea un asiento: lo crea CON-INI-EJE (`iniciar_ejercicio`), respaldado por la restricción única (el segundo
  inicio simultáneo recibe `contabilidad_ya_iniciada`).

## 2b. Sin ejercicio no hay asiento (CON-INI-EJE, regla 9; tarea CON-05)

Si la contabilidad no está iniciada, `registrar_asiento_automatico` lanza `ErrorContable` `contabilidad_no_iniciada` **antes** de bloquear
nada. **No lo atrapes**: tu transacción se deshace entera (la operación no queda registrada) y la ventana para el usuario la muestra el
middleware de `contabilidad` (`ContabilidadNoIniciadaMiddleware`). Si tu vista atrapa `ErrorContable` para mostrar un mensaje, volvé a lanzar
el de ese código. Un **paso diario** que genera asientos empieza con `if not ejercicios.contabilidad_iniciada(): return ResumenDePaso(0, 0, 0,
"contabilidad no iniciada: queda pendiente para mañana")`. En las pruebas, creá el ejercicio antes de la operación (`fabricas.ejercicio(...)`
o `iniciar_ejercicio`); hay una prueba por caso de uso con asiento que verifica la negativa sin ejercicio solo en `test_contabilidad_no_iniciada.py`.

## 3. Qué fecha se pasa

La **fecha del hecho**: la de la recepción, la del pago elegido, la de concreción de una entrega (puede ser anterior a hoy). No la de registro.
La función decide en qué ejercicio cae (D-84 punto 5). Si el hecho cae en un ejercicio ya cerrado, es anterior al primer ejercicio o es posterior a hoy, el asiento
**no falla**: va al abierto con la fecha de hoy y su descripción lo aclara («Fecha del hecho: dd/mm/aaaa (<motivo>); se registra con la fecha de
hoy.», D-102).

## 4. Cómo se prueba

Las pruebas de un caso de uso con asiento incluyen, además de las suyas:

- **El asiento:** que se creó con el origen correcto, los movimientos exactos (cuenta, Debe o Haber, importe) y el ejercicio esperado.
- **El importe cero:** que no hay asiento y no hay error.
- **Todo o nada:** si el caso de uso falla después de crear el asiento (o el asiento falla), no queda ninguno de los dos (una prueba con un
  fallo forzado con `mock.patch`).
- **Concurrencia (obligatoria):** `<CodigoCu>ConcurrenciaTests` (`TransactionTestCase`, `@tag("concurrencia")`, `correr_a_la_vez`): dos
  operaciones a la vez con asiento toman números distintos y sin hueco; y una prueba que rompe el orden de bloqueos (el ejercicio antes que
  tus filas) falla por *deadlock*, para demostrar que la tuya lo respeta (`detener_antes_de=(registrar, ...)`, patrón de bloqueos).
- Al final de cada prueba que crea asientos: `verificar_invariantes_contables()`.
- Las clases de pruebas que usan cuentas heredan de `PlanDeCuentasMixin` (`docs/patrones/datos_de_migracion.md`).
