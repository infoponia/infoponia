# Patrón · Altas, modificaciones, bajas y consultas (ABM) de un dato maestro

Resumen de cómo se hicieron MAE-01 y MAE-02a (`maestros/servicios/invernaderos.py`, `maestros/views.py`, `maestros/forms.py`)
y de cómo se hacen las tareas de la ronda «Producción 1» que siguen su forma: MAE-03, MAE-04, INV-01, INV-02 e INV-03. Si algo
de acá contradice una decisión o un caso de uso, manda la decisión o el caso de uso: avisá.

## 1. Capas

| Capa | Hace | No hace |
|---|---|---|
| Servicio (`<app>/servicios/<entidad>.py`) | Un caso de uso = una función en `transaction.atomic()`: permisos, reglas, bloqueos, cambios, auditoría y avisos | Nada de HTTP, plantillas ni mensajes |
| Formulario (`<app>/forms.py`) | Normaliza lo que se escribe y arma listas (D-24); **no valida reglas de negocio** | Reglas |
| Vista (`<app>/views.py`) | Valida la entrada, llama al servicio, pasa los `ValidationError` al formulario y renderiza | Consultas con reglas, auditoría |

## 2. Forma de un servicio

Orden dentro de la función (el de `docs/patrones/bloqueos.md`):

1. Exigir el rol del actor (`PermissionDenied` si no) y que esté activo.
2. Normalizar y validar la entrada **sin tocar la base** (nombre recortado, números, largos). Juntar **todos** los errores y
   lanzar un solo `ValidationError` con un error por campo (`error_dict`), para que la pantalla marque todos a la vez.
3. Tomar los bloqueos en el orden fijo (D-30, D-32, D-40), verificar que el actor siga activo y «a cargo» y **volver a leer**
   lo que se va a cambiar.
4. Validar las reglas que dependen de la base (nombre único, estado, ocupación) contra lo leído **después** de bloquear.
5. Calcular lo que cambió. **Sin cambios no se escribe ni se audita** (D-28).
6. Escribir. Una restricción de la base respalda cada regla de unicidad o de dominio; su `IntegrityError` se traduce al mismo
   `ValidationError` con `raise ... from error`: nunca llega un 500.
7. Auditar en la misma transacción (D-36, `docs/patrones/auditoria.md`): acción, afectados y `cambios` con «antes» y
   «después».
8. Notificar (NOT-01) y registrar alertas, también dentro de la transacción.
9. Devolver el objeto.

Errores: `PermissionDenied` (rol o alcance), `Http404` (id inexistente), `ValidationError` por campo (datos), y una excepción
propia cuando falta una **confirmación** (por ejemplo `FaltaConfirmarPersonal`): lleva el aviso y no cambia nada; la vista lo
muestra y reenvía con `…_confirmado=True`.

## 3. Baja lógica y reactivación

- La baja es lógica: el registro pasa a «inactivo» y conserva su historial. Nunca se borra una fila de negocio.
- Un registro inactivo **no se modifica**: solo se reactiva, y después se modifica como cualquier otro (esa regla está en
  cada CU). La reactivación es parte del caso de uso de **modificación** (código `MOD`) y se audita con su propia acción
  (`reactivacion_<entidad>`).
- La baja **no es en cascada** salvo que el CU lo diga. Si algo impide la baja, el servicio devuelve **todos** los impedimentos
  juntos, con qué pasa y cómo resolverlo (`Impedimento(codigo, texto, como_resolver)`), y no se queda con el primero.
- Los impedimentos que dependen de apps de nivel mayor llegan por un punto de extensión de `maestros/extensiones.py` (regla A4).

## 4. Nombre único

- Sin distinguir mayúsculas ni espacios al principio o al final; se guarda recortado.
- Se cuentan también los inactivos.
- Restricción de la base sobre la expresión (`lower(nombre)`) más validación en el servicio. Dos pedidos a la vez: el segundo
  recibe el mismo error de campo, no un 500.

## 5. Advertencias que no bloquean

Algunas reglas piden advertir «y dejar seguir» (por ejemplo, un cambio de tipo que deja sin sector a una etapa). El servicio
recibe `advertencia_confirmada=False`; si hay algo que advertir y no vino confirmada, lanza la excepción de confirmación con
los avisos y no cambia nada. La pantalla muestra la ventana con «Volver» y «Continuar igual», y reenvía con la confirmación.
La advertencia se calcula de nuevo después de bloquear: lo que se confirmó es lo que se ve en ese momento.

## 6. Alcance y botones

- Cada servicio de consulta recibe al actor y devuelve **solo lo de su alcance**; un id fuera del alcance da 403 y uno
  inexistente, 404 (D-28).
- `acciones_permitidas(actor, objeto)` devuelve qué botones corresponden; **ningún botón lleva a un 403** (D-30). Una acción que
  el actor no puede hacer **no se muestra**, salvo que el CU pida mostrarla deshabilitada con el motivo.
- El Gerente que solo consulta ve las mismas pantallas sin acciones.

## 7. Pantallas

- Lista o pestaña con tarjetas (D-47); lo agrupado se rotula con la cantidad (por ejemplo, «3 sectores · 120 agujeros»).
  Los dados de baja van aparte, con un rótulo, y con «Reactivar» como única acción.
- Acciones de cada fila en un menú «⋯» (el componente propio, D-24).
- Ventanas (alta, modificación, baja, confirmación) con HTMX y **respaldo sin JavaScript**: cada ventana es también una página.
  Las vistas con fragmento llevan `@vary_on_headers("HX-Request")` y `@never_cache`.
- Errores **por campo**, junto al campo y con el texto de la regla; al reenviar, el formulario conserva lo escrito.
- Si la operación sale bien, un aviso breve (D-29) y vuelve a la lista o a la ficha.
- Un formulario de un solo registro (singletons): ver la sección siguiente.

## 8. Pantalla de un registro único (singleton)

- Sin lista, sin alta y sin baja: la pantalla muestra los valores actuales y «Guardar cambios».
- Se guarda **todo o nada**: si un valor es inválido no se guarda ninguno y se marcan los campos con error.
- Una advertencia que no bloquea se muestra junto al formulario y deja guardar.
- Agrupar en tarjetas con título; cada pestaña se guarda por separado cuando sus datos son independientes.
- El servicio relee la fila después de bloquear y compara contra eso (dos personas a la vez: gana la última).

## 9. Pruebas

- Una prueba por regla (`test_regla_<n>_<qué_espera>`) y por postcondición (`test_post_<letra>_<qué_espera>`), en
  `<app>/tests/test_<código_cu>.py` con `<Codigo>ServicioTests` y `<Codigo>VistaTests` (`.claude/rules/pruebas.md`).
- Concurrencia (bloqueos, nombre repetido, cantidad contra reserva) con la etiqueta `concurrencia`; migraciones de datos con la
  etiqueta `migracion` (`docs/patrones/datos_de_migracion.md`).
- Los puntos de extensión se prueban con registrantes falsos (`mock.patch.object` sobre las listas de módulo).
- Las fábricas viven en `<app>/tests/fabricas.py`.
