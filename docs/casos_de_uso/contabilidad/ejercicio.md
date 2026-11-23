# Casos de uso · contabilidad · Ejercicio contable

Copia para el repo de CON-ABR-EJE y CON-CRR-EJE, de los archivos fuente de la ronda de Contabilidad (CON-alto-nivel.md). Cotejado con `decisiones_A0.md` y
`pendientes_para_pegar.md` (**esas decisiones ganan** si algo difiere, regla de Ezequiel del 23/11/2026).

**El código va en la app `contabilidad`** (D-37, nivel 2); archivos de pruebas bajo `contabilidad/tests/`. Si este archivo y el
documento de Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>` y `test_post_<letra>_<que_espera>`.

---

## **Caso de uso CON-ABR-EJE: Abrir Ejercicio Contable**

Reemplaza la mitad «abrir» de CON-GST-EJE, que proponía el contexto (sección 3.2, H2). Ahora el ejercicio no lo abre una persona: lo abre el Sistema.

**Actores:** InfoPonia (proceso automático).

**Tipo:** primario, esencial.

**Versión:** 0.1

**Disparador:** la ejecución diaria de InfoPonia (D-56), el día siguiente a la fecha de cierre prevista del ejercicio abierto. También la primera operación contable del día, si el proceso diario no corrió (regla 5, H9).

**Objetivo:** que siempre haya un ejercicio contable abierto donde registrar asientos.

**Precondición:**

a. Ninguna. Si el ejercicio abierto no venció, el paso termina sin cambios.

**Postcondición** (si el ejercicio abierto venció):

a. El ejercicio que estaba «abierto» pasó a «en cierre».

b. Se creó un ejercicio nuevo en estado «abierto», con fecha de inicio el día siguiente a la fecha de cierre del anterior y fecha de cierre prevista 12 meses después, menos un día.

c. Se notificó al Contador que el ejercicio anterior pasó a «en cierre» y que le falta cerrarlo (C7; si no hay un Contador activo, al Gerente).

d. Si al vencer el ejercicio abierto el anterior seguía «en cierre», el Sistema lo cerró solo (el más viejo) antes de abrir el nuevo, sin Contador asociado, y avisó al Contador (C1).

e. Se creó un log de auditoría con origen InfoPonia, el identificador de los ejercicios y los cambios de estado.

**Reglas:**

1.  A lo sumo hay un ejercicio «abierto» y uno «en cierre» (H1). Si el anterior sigue «en cierre» cuando vence el abierto, el Sistema cierra solo el más viejo y avisa al Contador (C1).
2.  El ejercicio abierto vence cuando la fecha actual es posterior a su fecha de cierre prevista (`fechaCierreEjercicio`), que se fija al abrirlo (H1).
3.  Cada ejercicio dura 12 meses desde el día siguiente al cierre del anterior, sin parámetro (H2.1).
4.  El primer ejercicio lo crea la puesta en marcha del Sistema, que empieza ese día; la contabilidad está activa desde ese momento (H3/H4). La puesta en marcha no es un caso de uso (mismo criterio que SEG-17).
5.  Autorrecuperación: si hoy ya pasó la fecha de cierre del abierto y el proceso diario no corrió, el servicio de asientos ejecuta la misma función de apertura antes de registrar (H9). El proceso diario y el servicio comparten la función; ninguno duplica el ejercicio.
6.  El número de asiento se reinicia en cada ejercicio (H8): el nuevo ejercicio parte sin asientos.
7.  Es un paso de la ejecución diaria. Va primero en el proceso, antes de todo paso que pueda generar asientos (orden 5, antes del 10 de inventario).
8.  La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).

---

## **Caso de uso CON-CRR-EJE: Cerrar Ejercicio Contable**

Reemplaza la mitad «cerrar» de CON-GST-EJE.

**Actores:** Contador. Si no hay un Contador activo, el Gerente.

**Tipo:** primario, esencial.

**Versión:** 0.1

**Objetivo:** cerrar definitivamente un ejercicio que está «en cierre», cuando el Contador terminó de cargar los asientos que le faltaban.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Contador o, si no hay un Contador activo, de Gerente.

b. Existe un ejercicio «en cierre».

**Postcondición:**

a. El ejercicio pasó a «cerrado», de forma definitiva.

b. Si lo cerró el Contador, el ejercicio quedó asociado a él (R010, modificada a «Contador cierra EjercicioContable», 0..1). Si lo cerró el Gerente, la asociación quedó vacía y la persona está en el log de auditoría (patrón de R050, MD-61). (H2.2)

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del ejercicio y el cambio de estado.

**Reglas:**

1.  Solo se cierra un ejercicio «en cierre». El ejercicio «abierto» no se cierra a mano: pasa a «en cierre» solo, con CON-ABR-EJE. (H1/H2)
2.  El cierre es definitivo: no hay reapertura. Un ejercicio cerrado no recibe asientos: los que caerían en su rango van al ejercicio abierto (H10).
3.  No hay asientos de cierre ni refundición de resultados. El libro de gestión calcula los saldos: las cuentas de resultado solo del ejercicio elegido y las patrimoniales acumuladas. La refundición es mejora futura. (H2.3)
4.  El cierre no tiene verificaciones que lo bloqueen. Antes de confirmar, el Sistema muestra un resumen del ejercicio (rango, cantidad de asientos, total del Debe y del Haber), avisa que el cierre no se puede deshacer y pide confirmación (C9).
5.  Lo ejecuta el Contador; el Gerente solo si no hay un Contador activo. (X3, H2.1)

---

---

## Cómo se aplica (código)

Decisiones: **D-84** (puntos 2, 3, 4 y 10), **D-85** (punto 5), **D-56** (proceso diario). Modelo: `docs/modelo/contabilidad.md`
(`EjercicioContable`). Contrato: `docs/api/asientos.md` («Escritura» y «Lectura»).

### CON-ABR-EJE (servicio y paso diario)

- Función `contabilidad.servicios.ejercicios.abrir_ejercicio_si_corresponde(hoy=None) -> ResultadoApertura`, con
  `ResultadoApertura = namedtuple("ResultadoApertura", "primero_creado paso_a_en_cierre cerrado_solo nuevo_abierto")` (cada campo, la
  instancia afectada o `None`). Idempotente: si el abierto no venció, devuelve todo `None` y no escribe.
- Pasos, dentro de `transaction.atomic()`: (1) bloquear los ejercicios (abierto y en cierre, en orden de `id`; si no hay ninguno, ver el
  primero); (2) **si no existe ningún ejercicio**, crear el primero con `fecha_inicio_ejercicio = hoy` y cierre previsto doce meses menos
  un día después (la puesta en marcha, D-84 punto 3), auditar `alta_ejercicio_contable` con actor `None` y terminar; (3) si
  `hoy > fecha_cierre_ejercicio` del abierto: si hay uno «en cierre», cerrarlo solo (`estado = cerrado`, `contador = None`, auditar
  `modificacion_ejercicio_contable`, datos `{"origen": "cierre automático"}`) y avisar (postcondición d); pasar el abierto a «en cierre»
  y avisar (postcondición c); crear el nuevo abierto (inicio = día siguiente al cierre previsto del anterior) y auditar.
- **Aviso (C7, pasada general punto 2):** `responsables.notificar_al_responsable_contable("El ejercicio N.º X pasó a «en cierre»", "Terminó el
  dd/mm/aaaa. Revisá el libro de gestión y cerralo cuando estés conforme.")`. Si lo cerró solo el Sistema (C1): «El ejercicio X se cerró
  solo porque venció el siguiente». Sin responsable (ni Contador ni Gerente activos), no se avisa y no falla.
- **Primer ejercicio sin condición de fecha:** si por cualquier razón el abierto no existe pero sí hay ejercicios (todos cerrados o uno en
  cierre), se abre uno nuevo que empieza el día siguiente al cierre del último y dura doce meses; si ese rango ya terminó antes de hoy, el
  paso lo repite hasta alcanzar el actual **dentro de la misma transacción** (tope de seguridad: 10 vueltas; superado, `ErrorContable`
  `ejercicios_atrasados`). Es el caso de un sistema que estuvo apagado más de un año.
- **Paso diario:** `registrar_paso_diario("abrir_ejercicio", "Abrir ejercicio contable", 5, paso_abrir_ejercicio)` en
  `ContabilidadConfig.ready()`; `paso_abrir_ejercicio(hoy)` llama a la función y devuelve
  `ResumenDePaso(procesados=1 si el abierto existía, creados=ejercicios nuevos, resueltos=ejercicios cerrados solos, detalle=...)`. Orden
  **5** (D-56 reserva órdenes de 10 en 10; el 5 es el de contabilidad, anterior al 10 de inventario). Hay que **actualizar la tabla de
  `core/procesos.py`** (comentario) con la fila `5 | Abrir ejercicio contable | contabilidad`.
- **Autorrecuperación (H9):** `registrar_asiento_automatico` y `registrar_asiento_manual` llaman a esta función antes de bloquear el
  ejercicio destino.
- **Comando** `python manage.py poner_en_marcha_contabilidad [--fecha-inicio AAAA-MM-DD]`: llama a `crear_primer_ejercicio(fecha_inicio)`,
  que **no hace nada** si ya existe algún ejercicio (y lo dice); sin `--fecha-inicio`, hoy. La fecha de inicio no puede ser futura.

### CON-CRR-EJE (servicio)

- `ejercicios.cerrar_ejercicio(actor, ejercicio_id) -> EjercicioContable`. Orden: (1) permisos (`responsables.puede_registrar_asientos(actor)`;
  si no, `PermissionDenied`); (2) bloquear el ejercicio (`FOR NO KEY UPDATE`) y verificar que siga «en cierre» (si no, `ErrorContable`
  `ejercicio_no_esta_en_cierre`, «cambio simultáneo»); (3) verificar que el actor siga activo; (4) `estado = cerrado`, `contador = actor`
  si es Contador (si es Gerente, `None`), guardar, auditar `modificacion_ejercicio_contable` (cambios `estado`: en_cierre → cerrado; en
  `datos`, `{"cerrado_por": rol}`).
- **El resumen del paso previo** (rango, cantidad de asientos, total del Debe y del Haber) lo arma `ejercicios.resumen_para_cierre(ejercicio_id)`
  (lectura, una consulta agregada); la pantalla lo muestra, avisa que no se deshace y pide confirmación (C9).
- Un cierre no bloquea los asientos que otro usuario esté registrando a la vez: la numeración toma el ejercicio bloqueado, así que o el
  asiento entra antes del cierre o el servicio de asientos encuentra el ejercicio cerrado y rechaza (7b de CON-REG-ASI).

### Pruebas (archivo `contabilidad/tests/`)

| Qué | Archivo |
|---|---|
| CON-ABR-EJE: cada postcondición y regla, con `hoy` simulado; idempotencia; primer ejercicio; el anterior en cierre se cierra solo; sistema apagado un año | `test_con_abr_eje.py` |
| CON-CRR-EJE: cada postcondición y regla; permisos (Contador, Gerente sin Contador, Gerente con Contador rechazado, Vendedor rechazado) | `test_con_crr_eje.py` |
| Paso diario 5 y comando `poner_en_marcha_contabilidad` | `test_paso_diario_ejercicio.py` |
| Concurrencia: dos aperturas a la vez (una sola crea); cierre contra asiento a la vez | `test_ejercicios_concurrencia.py` |

### Pantallas

Pestaña «Ejercicios» de «Contabilidad» (prototipo: `tabEje`, `VIEWS.k_cierre`, `ACT['cierre-ok']`): lista de ejercicios (número, rango, estado,
cantidad de asientos, quién lo cerró) y, para el «en cierre», el botón «Cerrar ejercicio» con la pantalla del resumen. El número de ejercicio
(«Ejercicio 1») es la posición por fecha de inicio. Textos explicativos siempre (criterio del estudiante).

## Solo prototipo

El interruptor «Hay un Contador activo» y el selector de rol del prototipo no son del sistema.
