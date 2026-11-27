# Casos de uso · contabilidad · Ejercicio contable

Copia para el repo de CON-INI-EJE (nuevo, 26/11/2026, tarea CON-05), CON-ABR-EJE y CON-CRR-EJE. CON-ABR-EJE y CON-CRR-EJE salen de los archivos fuente de la ronda de Contabilidad (CON-alto-nivel.md). Cotejado con `decisiones_A0.md` y
`pendientes_para_pegar.md` (**esas decisiones ganan** si algo difiere, regla de Ezequiel del 23/11/2026).

**El código va en la app `contabilidad`** (D-37, nivel 2); archivos de pruebas bajo `contabilidad/tests/`. Si este archivo y el
documento de Drive no coinciden, avisá: no elijas en silencio. Pruebas: `test_regla_<n>_<que_espera>` y `test_post_<letra>_<que_espera>`.

---

## **Caso de uso CON-INI-EJE: Iniciar Ejercicio Contable**

Caso de uso extendido del módulo Contabilidad (versión 0.1, 26/11/2026), con el formato de «CU extendidos». Sale de la decisión del estudiante del 26/11/2026 (tarea CON-05): la puesta en marcha de la contabilidad deja de ser técnica (D-84, punto 3; regla 4 de CON-ABR-EJE) y pasa a ser un objetivo del Contador, que inicia el primer ejercicio y carga el capital inicial en una sola operación.

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Contabilidad.
**Actor principal:** Contador. Si no hay un Contador activo, el Gerente (extensión 1a).
**Versión:** 0.1

**Personal involucrado e intereses**

**Contador:**
- quiere elegir la fecha en que empieza la contabilidad de la organización, en lugar de que la defina el Sistema;
- quiere que el primer asiento del libro sea la apertura, con lo que la organización ya tenía, para que los saldos tengan sentido desde el primer día.

**Gerente:**
- quiere poner en marcha la organización en un orden claro y que el Sistema le avise si intenta operar antes de iniciar la contabilidad;
- quiere poder iniciarla cuando no hay un Contador activo.

**Capataz, Agrónomo, Vendedor y demás roles que generan asientos:**
- quieren saber por qué no pueden registrar una operación y a quién recurrir.

**Organización (Jardín Botánico):**
- quiere que nunca exista un ejercicio sin su asiento de apertura ni un asiento fuera de un ejercicio;
- quiere que lo anterior a la puesta en marcha entre a la contabilidad por una vía controlada (Capital Inicial).

**Relaciones con otros casos de uso**
- No incluye otros casos de uso.
- No es extendido por otros casos de uso.
- **Disparador:** la alerta «Falta iniciar la contabilidad» de la campana del Contador o del Gerente, el botón «Iniciar ejercicio» de la pestaña «Ejercicios» o del libro de gestión vacío, o el aviso de cualquier caso de uso que genera un asiento automático cuando todavía no hay ejercicio (regla «Sin ejercicio no hay asiento»; extensión 1b).
- **Lo siguen:** CMP-AJT-STK · Ajustar Stock (motivo «carga inicial») y PROD-REG-LTE · Registrar Lote Existente, que cargan los insumos y los lotes que ya existían; y CON-ABR-EJE · Abrir Ejercicio Contable, que desde ahora abre los ejercicios siguientes.
- **Relacionado:** CON-CNS-LGS · Consultar Libro de Gestión, donde se ve el asiento de apertura como asiento N.º 1.

**Precondiciones**
a. El actor está autenticado en el Sistema con una cuenta activa de Contador o, si no hay un Contador activo, de Gerente.
b. No existe ningún ejercicio contable (en ningún estado).
c. Existen las cuentas contables del plan de cuentas (se cargan por migración, D-37).

**Garantías mínimas**
El registro es atómico. Si el caso de uso se cancela o falla:
- no queda creado ningún ejercicio, asiento ni movimiento contable;
- no se registra ningún log de auditoría parcial;
- la operación que disparó el caso de uso (extensión 1b) sigue sin registrarse.

**Además:**
- Nunca queda un ejercicio sin su asiento de apertura ni un asiento de apertura sin su ejercicio.
- No se modifica ninguna otra entidad del Sistema (stock, lotes, contratos, entregas, etc.): este caso de uso solo toca la contabilidad.

**Garantías de éxito (Postcondiciones)**
a. Se creó un ejercicio contable en estado «abierto», con la fecha de inicio indicada, fecha de cierre prevista 12 meses después menos un día y último número de asiento igual a 1.
b. Se creó el asiento de apertura: asiento N.º 1 del ejercicio, sin documento de origen, con fecha igual a la fecha de inicio y descripción «Asiento de apertura».
c. Se creó un movimiento contable por cada línea con importe mayor que cero. Hay al menos un movimiento al Haber de Capital Inicial y la suma del Debe es igual a la suma del Haber.
d. Se creó un log de auditoría por el ejercicio, por el asiento y por cada movimiento, con usuario, rol (Contador o Gerente), fecha, hora, identificador y valores.
e. Dejó de mostrarse la alerta «Falta iniciar la contabilidad» y, desde ese momento, los casos de uso que generan asientos automáticos pueden registrar.

**Escenario principal de éxito (Flujo Básico)**
(El Contador inicia la contabilidad desde la alerta, con una fecha de inicio válida y un asiento de apertura balanceado.)

1. **El Contador inicia la puesta en marcha de la contabilidad desde la alerta «Falta iniciar la contabilidad».**
2. **El Sistema verifica que no existe ningún ejercicio y presenta el formulario:**
   - fecha de inicio del ejercicio (por defecto, la fecha actual) y la fecha de cierre prevista que resulta de ella;
   - las líneas del asiento de apertura, con las cuentas ya puestas y los importes vacíos: al Debe, Caja, Banco c/c y Deudores por Ventas; al Haber, Capital Inicial y Proveedores;
   - un texto que explica que los insumos y los lotes que ya existían se cargan después, con sus propios casos de uso, y que también acreditan Capital Inicial.
3. **El Contador indica la fecha de inicio y el importe de cada línea que corresponda.**
4. **El Contador indica que terminó de cargar los datos.**
5. **El Sistema verifica los datos y presenta el resumen: el ejercicio (fecha de inicio y de cierre prevista), el asiento de apertura como asiento N.º 1 con su fecha, el total del Debe, el total del Haber y la diferencia (debe ser 0).**
6. **El Contador confirma.**
7. **El Sistema registra la puesta en marcha:**
   - verifica de nuevo, con bloqueo, que no existe ningún ejercicio;
   - crea el ejercicio «abierto»;
   - crea el asiento de apertura N.º 1 y sus movimientos;
   - registra la auditoría correspondiente.
8. **El Sistema informa que la contabilidad quedó iniciada, con el ejercicio y el asiento N.º 1, y ofrece seguir con la carga inicial de insumos y de lotes existentes.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 6), el actor cancela:**
1. El Sistema descarta los datos ingresados sin registrar ningún cambio.
2. Si el actor había llegado desde otra operación (extensión 1b), esa operación sigue sin registrarse.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa al actor que la contabilidad no fue iniciada.
3. El actor reinicia desde el paso 1.

**1a. No hay un Contador activo y el Gerente inicia la contabilidad:**
1. El caso de uso continúa en el paso 2 con el Gerente como actor.
2. En el paso 7, el log de auditoría deja al Gerente como autor (rol Gerente).
3. Si hay un Contador activo, el Sistema no permite iniciarla al Gerente e indica que la inicia el Contador (regla «Quién inicia»).

**1b. El actor llega desde una operación que genera un asiento automático:**
1. Al confirmar esa operación, el Sistema le muestra una ventana: lo que está haciendo genera un asiento contable y la contabilidad todavía no está iniciada; la operación no se registró.
2. La ventana ofrece el botón «Iniciar ejercicio», que lleva al paso 2 de este caso de uso.
3. Si el actor cierra la ventana sin iniciar el ejercicio, la operación no se registra (regla «Sin ejercicio no hay asiento»).
4. Al terminar (paso 8), el Sistema ofrece volver a la pantalla de la operación que quedó pendiente; los datos de esa operación se cargan de nuevo.

**2a. Ya existe un ejercicio contable:**
1. El Sistema informa que la contabilidad ya está iniciada, con el ejercicio vigente.
2. El caso de uso termina.

**5a. La fecha de inicio es posterior a la fecha actual:**
1. El Sistema señala que la fecha de inicio no puede ser futura.
2. El actor la corrige (vuelve al paso 3) o cancela.

**5b. La fecha de inicio es tan antigua que el ejercicio ya habría terminado (la fecha de cierre prevista es anterior a la fecha actual):**
1. El Sistema señala la fecha más antigua que se puede elegir.
2. El actor la corrige (vuelve al paso 3) o cancela.

**5c. Capital Inicial no tiene importe:**
1. El Sistema señala que el capital inicial es obligatorio para iniciar la contabilidad.
2. El actor lo completa (vuelve al paso 3) o cancela.

**5d. El Debe y el Haber no suman lo mismo:**
1. El Sistema señala la diferencia y no permite confirmar.
2. El actor corrige (vuelve al paso 3).

**5e. Una línea tiene importe negativo o con más de dos decimales:**
1. El Sistema señala el error. Las líneas sin importe o con importe cero se omiten.
2. El actor corrige (vuelve al paso 3) o cancela.

**7a. Al registrar, otro usuario ya inició la contabilidad:**
1. El Sistema no registra ningún cambio e informa el ejercicio que ya existe.
2. El caso de uso termina.

**7b. Al registrar, una cuenta del asiento ya no existe o dejó de estar disponible:**
1. El Sistema no registra ningún cambio e informa las líneas afectadas.
2. El caso de uso vuelve al paso 3.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 7 se completa en no más de 3 segundos.
- El registro es una única transacción: el ejercicio, el asiento, sus movimientos y los logs se registran juntos o ninguno.
- El control de concurrencia impide que dos usuarios inicien la contabilidad a la vez: solo uno crea el ejercicio (extensión 7a).
- Los montos se expresan en pesos argentinos con dos decimales.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.

**Reglas de negocio**
1. **Quién inicia:** el Contador. Si no hay un Contador activo, el Gerente; si hay uno activo, el Gerente no la inicia. Es el mismo criterio que CON-REG-ASI y CON-CRR-EJE. (Precondición a, extensión 1a)
2. **Una sola vez:** la contabilidad se inicia solo si no existe ningún ejercicio. No hay reinicio. (Precondición b, extensión 2a)
3. **Puesta en marcha indivisible:** el primer ejercicio y el asiento de apertura se crean juntos. No existe un ejercicio sin capital inicial. (Postcondiciones a y b)
4. **Fecha de inicio:** no posterior a hoy y no tan antigua que la fecha de cierre prevista sea anterior a hoy. (Extensiones 5a y 5b)
5. **Duración:** el ejercicio dura 12 meses desde la fecha de inicio, menos un día, igual que los siguientes. (Regla 3 de CON-ABR-EJE)
6. **Cuentas del asiento de apertura:** al Debe, Caja (1.1.01), Banco c/c (1.1.02) y Deudores por Ventas (1.1.03); al Haber, Capital Inicial (3.1.01, obligatoria, importe mayor que cero) y Proveedores (2.1.01, deudas previas). No se pueden agregar otras cuentas.
7. **Sin insumos ni productos en la apertura:** Insumos en Stock, Productos en Proceso y Productos Terminados no van en el asiento de apertura. Entran con la carga inicial de insumos (CMP-AJT-STK) y con los lotes existentes (PROD-REG-LTE), que acreditan Capital Inicial. Si fueran también en la apertura, se contarían dos veces.
8. **Balance:** Debe = Haber, con importes mayores que cero; las líneas sin importe se omiten. (Extensiones 5c, 5d y 5e)
9. **Sin ejercicio no hay asiento:** mientras no exista ningún ejercicio, ninguna operación que genera un asiento automático se registra:
   - el Contador o el Gerente que puede iniciarla (regla 1) ve la ventana con el botón «Iniciar ejercicio» (extensión 1b);
   - cualquier otro usuario con cuenta ve la ventana «La contabilidad no está iniciada. Pedile al Contador o al Gerente que la inicie.», sin botón; el Contador o el Gerente ya tiene la alerta de la regla 10;
   - un paso del proceso diario que genera asientos no procesa nada, deja todo pendiente para el día siguiente e informa el motivo en su resumen;
   - un actor externo que opera desde un enlace (proveedor, cliente o transportista) ve un mensaje que indica que la operación no se pudo registrar y que lo intente más tarde.
10. **Alerta de puesta en marcha:** mientras no exista ningún ejercicio, la campana del Contador (o del Gerente, si no hay Contador activo) muestra la alerta «Falta iniciar la contabilidad», con el acceso a este caso de uso. (Disparador)
11. **El proceso diario ya no crea el primer ejercicio:** CON-ABR-EJE solo abre el ejercicio siguiente a uno que existe. (Reemplaza la regla 4 de CON-ABR-EJE y el punto 3 de D-84.)
12. **Auditoría:** el usuario real queda en el log, con su rol.

**Lista de tecnología y variaciones de datos**
- **3.** Fecha de inicio: fecha (dd/mm/aaaa). Importes: hasta dos decimales, en pesos argentinos.

**Frecuencia**
Una sola vez en la vida del Sistema, al ponerlo en marcha.

---

## **Caso de uso CON-ABR-EJE: Abrir Ejercicio Contable**

Reemplaza la mitad «abrir» de CON-GST-EJE, que proponía el contexto (sección 3.2, H2). Ahora el ejercicio no lo abre una persona: lo abre el Sistema.

**Actores:** InfoPonia (proceso automático).

**Tipo:** primario, esencial.

**Versión:** 0.1

**Disparador:** la ejecución diaria de InfoPonia (D-56), el día siguiente a la fecha de cierre prevista del ejercicio abierto. También la primera operación contable del día, si el proceso diario no corrió (regla 5, H9).

**Objetivo:** que siempre haya un ejercicio contable abierto donde registrar asientos.

**Precondición:**

a. Ninguna. Si el ejercicio abierto no venció, o si todavía no existe ningún ejercicio (la contabilidad no está iniciada, regla 4), el paso termina sin cambios.

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
4.  El primer ejercicio lo crea CON-INI-EJE, con la fecha de inicio y el capital inicial que indica el Contador; la contabilidad está activa desde ese momento. CON-ABR-EJE nunca crea el primero: si no existe ningún ejercicio, no hace nada (cambió el 26/11/2026, tarea CON-05; antes, la puesta en marcha técnica de D-84 punto 3).
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

Decisiones: **D-84** (puntos 2, 4 y 10; el punto 3 lo reemplaza la decisión de CON-05), **D-85** (punto 5), **D-56** (proceso diario).
Modelo: `docs/modelo/contabilidad.md` (`EjercicioContable`). Contrato: `docs/api/asientos.md` («Escritura» y «Lectura»). Tarea: CON-05.

### CON-INI-EJE (servicio, pantalla, alerta y la regla «Sin ejercicio no hay asiento»)

- **Servicio** `contabilidad.servicios.ejercicios.iniciar_ejercicio(actor, fecha_inicio, importes, *, hoy=None) -> AsientoContable` (el
  asiento de apertura; su ejercicio es `asiento.ejercicio`). `importes` es un `dict` de código de cuenta a `Decimal` con las cinco cuentas
  de la regla 6 (`CAJA`, `BANCO`, `DEUDORES_POR_VENTAS` al Debe; `CAPITAL_INICIAL`, `PROVEEDORES` al Haber, de `contabilidad/cuentas.py`);
  una clave que no es de esas cinco es `ErrorContable` `cuenta_no_permitida_en_apertura`. Orden, dentro de `transaction.atomic()`:
  (1) permisos con `responsables.puede_registrar_asientos(actor)` (si no, `PermissionDenied`); (2) validar fecha (reglas 4: `fecha_invalida`,
  `fecha_futura`, `fecha_inicio_demasiado_antigua`) e importes (reglas 6 y 8: `capital_inicial_obligatorio`, `importe_invalido`, `asiento_desbalanceado`);
  si hay varios errores de campo, `ErroresContables`, como el asiento manual; (3) verificar que el actor siga activo; (4) crear el ejercicio con
  `_crear(fecha_inicio, "puesta en marcha")` pero **auditado con el actor** (agregale un parámetro `actor=None` a `_crear`) y respaldado por la
  restricción única: si ya existe algún ejercicio o el alta choca (`IntegrityError` en un `atomic()` anidado), `ErrorContable`
  `contabilidad_ya_iniciada` (extensiones 2a y 7a); (5) bloquear el ejercicio nuevo (`select_for_update(no_key=True)`), numerar el asiento
  N.º 1, crear el asiento (sin origen, `fecha_asiento = fecha_inicio`, descripción «Asiento de apertura») y sus movimientos, y auditar
  igual que `registrar_asiento_manual` (reusá sus funciones internas; no llames a `registrar_asiento_manual`, que exige un ejercicio).
- **Resumen** `ejercicios.resumir_inicio(actor, fecha_inicio, importes, *, hoy=None) -> ResumenDeInicio` (paso 5): las mismas validaciones,
  sin escribir ni bloquear: `inicio`, `cierre`, `lineas` (cuenta, tipo, importe; las de importe cero omitidas), `total_debe`, `total_haber`,
  `diferencia`. `ejercicios.fecha_inicio_minima(hoy)`: la fecha más antigua permitida (extensión 5b; el día siguiente a «hoy menos 12 meses»).
- **¿Está iniciada?** `ejercicios.contabilidad_iniciada() -> bool` (lectura: existe algún ejercicio). La usan la alerta, las pantallas y los
  pasos diarios.
- **«Sin ejercicio no hay asiento» (regla 9).** `registrar_asiento_automatico`, `registrar_asiento_manual` y `contraasentar` lanzan
  `ErrorContable("contabilidad_no_iniciada", "La contabilidad no está iniciada.")` si no existe ningún ejercicio, **antes** de bloquear nada.
  La transacción de quien llama se deshace entera: la operación no queda registrada. La ventana la arma, en un solo lugar, el middleware
  `contabilidad.middleware.ContabilidadNoIniciadaMiddleware` (en `MIDDLEWARE` de `config/settings.py`, después de los de sesión y
  autenticación), con `process_exception`: solo atiende ese código y deja pasar cualquier otra excepción. Responde:
  - pedido HTMX (`HX-Request`): la ventana `contabilidad/_ventana_contabilidad_no_iniciada.html` con estado 200 y los encabezados
    `HX-Retarget: body` y `HX-Reswap: beforeend` (así se agrega encima de la pantalla actual), con el mismo marco de ventana que
    `core/_ventana_desvincular.html`;
  - pedido común: la página `contabilidad/contabilidad_no_iniciada.html` con el mismo texto;
  - texto según quién: si `responsables.puede_registrar_asientos(usuario)`, «Lo que estás registrando genera un asiento contable y la
    contabilidad todavía no está iniciada. La operación no se registró.» con los botones «Iniciar ejercicio» (lleva a la pantalla de inicio con
    `?volver=<la URL de la pantalla de la operación>`; usá `Referer` si es del mismo sitio, si no, nada) y «Cerrar»; si es otro usuario con
    cuenta, «La contabilidad no está iniciada. Pedile al Contador o al Gerente que la inicie. La operación no se registró.» y solo «Cerrar»;
    si no hay usuario (pantallas de enlace de proveedor, cliente o transportista), «No pudimos registrar la operación. Probá de nuevo más
    tarde.», sin mencionar la contabilidad.
  - Las vistas que hoy atrapan `ErrorContable` de forma general (por ejemplo `compras/views_pagos.py`) tienen que volver a lanzar el de código
    `contabilidad_no_iniciada` para que lo atienda el middleware; buscá todas con `grep -rn "except ErrorContable"`.
- **Pasos diarios con asientos (regla 9).** Todo paso registrado en `core/procesos.py` cuyo servicio llama, directa o indirectamente, a
  `registrar_asiento_automatico` empieza con `if not ejercicios.contabilidad_iniciada(): return ResumenDePaso(0, 0, 0, "contabilidad no
  iniciada: queda pendiente para mañana")`. Hoy son, como mínimo, `vencer_partidas_en_camara` (20) y `resolver_suministros` (33); revisá todos
  y nombralos en el «Cierre».
- **Alerta (regla 10):** `contabilidad` registra en `ContabilidadConfig.ready()` una fuente con `core.extensiones.registrar_fuente_de_alertas`:
  si no está iniciada y `responsables.puede_registrar_asientos(usuario)`, devuelve un `ItemDeAlerta("advertencia", "Falta iniciar la
  contabilidad", "Iniciá el primer ejercicio y cargá el capital inicial antes de registrar operaciones que generan asientos.", <URL de la
  pantalla de inicio>, False)`; si no, `[]`. Es una consulta liviana (`exists()`); no crea alertas en la base.
- **Pantalla «Iniciar ejercicio»** (no hay prototipo: armala con `.claude/rules/interfaz.md` y el estilo de la pantalla de «Registrar
  asiento» de CON-03b). URL `contabilidad/ejercicios/iniciar/`. Solo para quien cumple la regla 1 (si no, 403). Si ya está iniciada, muestra
  el mensaje de 2a con un enlace a «Ejercicios». Paso 2: fecha de inicio (por defecto hoy; el calendario no deja elegir fuera del rango de la
  regla 4), la fecha de cierre prevista calculada al cambiar la fecha (HTMX), las cinco líneas fijas en dos bloques («Debe» y «Haber», con el
  código y el nombre de cada cuenta y un campo de importe) y el texto de la regla 7. Paso 5: el resumen, con el botón «Confirmar e iniciar»
  y «Volver a editar». Paso 8: mensaje de éxito con enlaces a «Libro de gestión», a la carga inicial de insumos y a «Registrar lote
  existente» (los de las pantallas que ya existen) y, si llegó `volver`, «Volver a la operación».
- **Entradas:** el botón «Iniciar ejercicio» en la pestaña «Ejercicios» y en el estado vacío del libro de gestión cuando no está iniciada
  (solo para quien cumple la regla 1; para los demás, el texto «La contabilidad todavía no está iniciada»). El botón «Registrar asiento» no
  se muestra mientras no esté iniciada.
- **Auditoría:** `alta_ejercicio_contable` (con el actor), `alta_asiento_contable` y `alta_movimiento_contable`, como CON-REG-ASI.
- **Eliminación del ejercicio de producción (una sola vez):** comando `eliminar_ejercicio_sin_apertura`, descrito en la tarea CON-05, paso 6.

### CON-ABR-EJE (servicio y paso diario)

- Función `contabilidad.servicios.ejercicios.abrir_ejercicio_si_corresponde(hoy=None) -> ResultadoApertura`, con
  `ResultadoApertura = namedtuple("ResultadoApertura", "primero_creado paso_a_en_cierre cerrado_solo nuevo_abierto")` (cada campo, la
  instancia afectada o `None`). Idempotente: si el abierto no venció, devuelve todo `None` y no escribe.
- Pasos, dentro de `transaction.atomic()`: (1) bloquear los ejercicios (abierto y en cierre, en orden de `id`; si no hay ninguno, ver el
  primero); (2) **si no existe ningún ejercicio**, no hacer nada y devolver todo `None` (regla 4: el primero lo crea CON-INI-EJE; ya no se
  crea «hoy» como en D-84 punto 3); (3) si
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
  ejercicio destino. Solo recupera ejercicios **siguientes**: si no existe ninguno, lanzan `contabilidad_no_iniciada` (CON-INI-EJE, regla 9).
- **Se retiran** el comando `poner_en_marcha_contabilidad` y la función `crear_primer_ejercicio` (CON-05): la puesta en marcha es
  CON-INI-EJE. Las pruebas que los usaban pasan a `iniciar_ejercicio` o a `fabricas.ejercicio(...)` (tarea CON-05, paso 5).

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
| Paso diario 5 (sin ejercicio, no hace nada) | `test_paso_diario_ejercicio.py` |
| CON-INI-EJE: cada postcondición, regla y extensión; permisos (Contador, Gerente sin Contador, Gerente con Contador rechazado, Vendedor rechazado); resumen; fecha mínima | `test_con_ini_eje.py` |
| Regla 9: el asiento automático, el manual y el contraasiento sin ejercicio lanzan `contabilidad_no_iniciada` y no queda nada; el middleware (HTMX y común; responsable, otro rol y sin usuario); los pasos diarios con asientos no procesan; la alerta | `test_contabilidad_no_iniciada.py` |
| Concurrencia: dos inicios a la vez (uno solo crea; el otro, `contabilidad_ya_iniciada`) | `test_ejercicios_concurrencia.py` |
| Comando `eliminar_ejercicio_sin_apertura` (todas las negativas y el borrado) | `test_comando_eliminar_ejercicio.py` |
| Recorrido: iniciar desde la alerta, ver el asiento N.º 1 en el libro; una operación con asiento sin ejercicio muestra la ventana | `test_recorrido_iniciar_ejercicio.py` |
| Concurrencia: dos aperturas a la vez (una sola crea); cierre contra asiento a la vez | `test_ejercicios_concurrencia.py` |

### Pantallas

Pestaña «Ejercicios» de «Contabilidad» (prototipo: `tabEje`, `VIEWS.k_cierre`, `ACT['cierre-ok']`): lista de ejercicios (número, rango, estado,
cantidad de asientos, quién lo cerró) y, para el «en cierre», el botón «Cerrar ejercicio» con la pantalla del resumen. Sin ningún ejercicio,
la pestaña muestra el estado vacío con el botón «Iniciar ejercicio» (CON-INI-EJE; la pantalla está descrita arriba). El número de ejercicio
(«Ejercicio 1») es la posición por fecha de inicio. Textos explicativos siempre (criterio del estudiante).

## Solo prototipo

El interruptor «Hay un Contador activo» y el selector de rol del prototipo no son del sistema.
