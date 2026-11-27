# CON-05 · Iniciar el ejercicio contable con el capital inicial; sin ejercicio no hay asiento

Estado: pendiente | App: contabilidad | Rama: feature/con-05-iniciar-ejercicio | Ronda: — (puesta en marcha contable, 26/11/2026)

Depende de: CON-04d y EST-03 (hechas). Tiene que estar desplegada **antes de operar en producción**.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

**Por qué existe.** Hasta hoy el primer ejercicio lo creaba solo el Sistema, «hoy», en la primera operación contable o en el paso diario 5
(D-84 punto 3). El 26/11/2026 la primera corrida del cron en producción creó así un ejercicio sin capital inicial. El estudiante decidió que
la puesta en marcha sea un caso de uso del Contador (CON-INI-EJE): elige la fecha de inicio y carga el capital inicial en la misma operación,
y mientras no lo haga ninguna operación que genera un asiento se registra. Las dos decisiones de abajo se numeran al cerrar (M3).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CON-INI-EJE | Iniciar Ejercicio Contable (nuevo) | docs/casos_de_uso/contabilidad/ejercicio.md (caso y «Cómo se aplica», sección CON-INI-EJE) | — |
| CON-ABR-EJE | Abrir Ejercicio Contable (cambia la regla 4) | docs/casos_de_uso/contabilidad/ejercicio.md | — |
| CON-REG-ASI | Registrar Asiento Manual (se quita la extensión 3a) | docs/casos_de_uso/contabilidad/asientos_manuales.md («Cómo se aplica», viñetas «Ventas previas» y «Sin ejercicio») | — |

## Leer

- Casos de uso: lista arriba.
- Modelo: docs/modelo/contabilidad.md — `EjercicioContable` (fila `fecha_inicio_ejercicio` y regla 5), plan de cuentas.
- Decisiones: D-84 (puntos 3, 4 y 9), D-86, D-102, D-56, D-71. Las dos decisiones de esta tarea están abajo, en «Decisiones».
- Contratos: docs/api/asientos.md (completo), docs/api/alertas.md (solo para ver cómo se registra una fuente de la campana en `core`).
- Patrones: docs/patrones/asientos.md (sección 2b es nueva), docs/patrones/auditoria.md, docs/patrones/bloqueos.md,
  docs/patrones/datos_de_migracion.md.
- Pantallas: no hay prototipo de CON-INI-EJE; la pantalla está descrita en el extracto. Tomá el estilo de la pantalla de «Registrar asiento»
  (CON-03b) y la ventana de `core/templates/core/_ventana_desvincular.html`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.

## Límites

- Crea modelos: ninguno.
- Migraciones: la de `core` por la acción nueva `baja_ejercicio_contable` en `RegistroAuditoria.Accion` (solo `AlterField` de las opciones,
  como las acciones anteriores). Ninguna otra.
- Permitido fuera de la app:
  - `config/settings.py` (solo agregar el middleware a `MIDDLEWARE`);
  - `core/models.py` (solo la acción `baja_ejercicio_contable`, con su etiqueta y en la clasificación que corresponda según `docs/patrones/auditoria.md`);
  - `core/management/commands/proceso_diario.py` (solo el docstring, paso 7);
  - los servicios de los pasos diarios que generan asientos (solo la guarda del paso 3);
  - las vistas de cualquier app que atrapan `ErrorContable` (solo volver a lanzar `contabilidad_no_iniciada`);
  - `demo/` (solo para que la carga de la demo inicie la contabilidad con `iniciar_ejercicio`);
  - las pruebas de todas las apps (solo para crear el ejercicio antes de la operación, paso 5).
- Dependencias nuevas: ninguna.
- Fuera de alcance: cualquier cambio de reglas de los casos de uso que generan asientos, salvo la regla 9 de CON-INI-EJE. No toques la base de
  producción: el comando del paso 6 lo corre el estudiante (CLAUDE.md, «Seguridad»).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **El núcleo deja de crear el primer ejercicio.** `ejercicios.contabilidad_iniciada()`; `abrir_ejercicio_si_corresponde` sin ningún
   ejercicio no hace nada; `registrar_asiento_automatico`, `registrar_asiento_manual` y `contraasentar` lanzan `contabilidad_no_iniciada`
   antes de bloquear; se retiran `crear_primer_ejercicio` y el comando `poner_en_marcha_contabilidad`. Actualizá las pruebas de
   `contabilidad` que dependían de eso (`test_con_abr_eje.py`, `test_paso_diario_ejercicio.py` y los recorridos que llamaban al comando).
   — pruebas: `contabilidad.tests`
2. **CON-INI-EJE, servicio.** `iniciar_ejercicio`, `resumir_inicio`, `fecha_inicio_minima`, `_crear` con actor y los códigos de error del
   extracto. Texto nuevo de 3.1.01 en `DESCRIPCION_DE_CUENTA` (`contabilidad/cuentas.py`): «Lo que ya existía al poner en marcha InfoPonia.
   La mueven el asiento de apertura (CON-INI-EJE), el ajuste «carga inicial» de insumos y los lotes existentes (Haber).».
   — pruebas: `test_con_ini_eje.py` (`ConIniEjeServicioTests`) y `test_ejercicios_concurrencia.py` (dos inicios a la vez)
3. **Sin ejercicio no hay asiento.** El middleware `ContabilidadNoIniciadaMiddleware` y sus dos plantillas, las vistas que atrapan
   `ErrorContable`, la guarda en los pasos diarios que generan asientos (nombralos en el «Cierre») y la fuente de la campana.
   — pruebas: `test_contabilidad_no_iniciada.py`
4. **Pantallas.** «Iniciar ejercicio» (pasos 2, 5 y 8, con `volver`), el botón en «Ejercicios» y en el libro vacío, ocultar «Registrar
   asiento» sin ejercicio y quitar el atajo «Asiento de apertura» de la pantalla del asiento manual. — pruebas: `test_con_ini_eje.py`
   (`ConIniEjeVistaTests`) y `test_recorrido_iniciar_ejercicio.py`
5. **Las pruebas de las demás apps.** Corré la suite completa. Cada prueba que registra una operación con asiento sin crear antes un ejercicio
   ahora falla con `contabilidad_no_iniciada`: agregá el ejercicio en su `setUp`/`setUpTestData` con `fabricas.ejercicio(Estado.ABIERTO,
   <inicio que contenga las fechas de la prueba>)`, o con el helper nuevo `fabricas.iniciar_contabilidad_para_pruebas(inicio)` (mismo efecto,
   sin auditoría, para no repetir). No cambies ninguna otra aserción; si una prueba verificaba justamente la creación automática del primer
   ejercicio, reemplazala por la negativa de la regla 9 y anotalo en el «Cierre». Adaptá `demo/` para que inicie la contabilidad con
   `iniciar_ejercicio` (capital inicial de la demo: el importe que ya usaba, o 1.000.000,00 en Caja contra Capital Inicial si no había).
   — pruebas: la suite completa
6. **Comando de uso único `eliminar_ejercicio_sin_apertura`** (en `contabilidad/management/commands/`), para borrar el ejercicio que creó la
   puesta en marcha automática en producción:
   - Sin opciones, **no escribe nada**: muestra qué ejercicio borraría o por qué no puede.
   - Con `--confirmar`, dentro de `transaction.atomic()`: bloquea todos los ejercicios (`select_for_update`) y verifica, con los datos
     bloqueados, que hay **exactamente uno**, en estado «abierto», con `ultimo_numero_asiento == 0` y **sin asientos**. Si algo no se cumple,
     `CommandError` con el motivo y no borra nada.
   - Antes de borrar, audita con actor `None` la acción nueva `baja_ejercicio_contable` (con el ejercicio en `afectados`, los `cambios` de
     sus tres campos a `None` y en `datos` `{"motivo": "puesta en marcha automática reemplazada por CON-INI-EJE"}`); después lo borra e
     imprime «Ejercicio … eliminado. La contabilidad queda sin iniciar: usá «Iniciar ejercicio».».
   - Docstring con el uso y la advertencia de que es de un solo uso; se retira en una tarea posterior.
   — pruebas: `test_comando_eliminar_ejercicio.py` (cada negativa: ninguno, dos, en cierre, con número tomado, con asientos; el borrado con su
   auditoría; sin `--confirmar` no borra)
7. **Documentación en el código.** El docstring de `core/management/commands/proceso_diario.py` dice que se puede correr desde la «Shell» de
   Render: el plan gratuito de Render no tiene shell. Reemplazá esa frase por: «En producción lo corre el cron job `infoponia-proceso-diario`
   de Render (decisión de CON-05, «Crons»); para correrlo a mano, botón «Trigger Run» de ese cron.».

Si el tiempo apremia, lo último que se recorta es: el paso 7 (se anota como disparador).

## Hecho cuando

- Sin ningún ejercicio, una operación con asiento (por ejemplo, un pago a un proveedor) no queda registrada y muestra la ventana correcta según
  quién la hace (Contador/Gerente con botón, otro rol sin botón, enlace externo con el mensaje genérico).
- El Contador inicia la contabilidad desde la alerta, con fecha y capital, y el libro muestra el asiento N.º 1 «Asiento de apertura» con la
  fecha de inicio; la alerta desaparece y la operación pendiente se puede registrar.
- El paso diario 5 sin ejercicio dice «sin cambios»; los pasos con asientos dicen «contabilidad no iniciada: queda pendiente para mañana».
- El comando `eliminar_ejercicio_sin_apertura` cumple el paso 6.
- La suite completa pasa.
- Comando de pruebas: python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  y python manage.py test contabilidad.tests.test_ejercicios_concurrencia --keepdb --tag concurrencia

## Decisiones (se numeran al cerrar, M3; aprobadas por el estudiante el 26/11/2026)

### «Puesta en marcha contable» (reemplaza el punto 3 de D-84)

- Antes: D-84 punto 3 (el primer ejercicio lo crea `abrir_ejercicio_si_corresponde` «hoy», o el comando `poner_en_marcha_contabilidad`);
  regla 4 de CON-ABR-EJE («la puesta en marcha no es un caso de uso»); extensión 3a de CON-REG-ASI (apertura como asiento manual).
- Decisión:
  1. La puesta en marcha es el caso de uso CON-INI-EJE, del Contador (el Gerente si no hay Contador activo): elige la fecha de inicio (no
     futura, con el cierre previsto no anterior a hoy) y carga el asiento de apertura en la misma transacción. El asiento de apertura es el
     N.º 1, con la fecha de inicio, y solo usa Caja, Banco c/c y Deudores por Ventas al Debe y Capital Inicial (obligatoria) y Proveedores al
     Haber; insumos y lotes entran por la carga inicial y los lotes existentes.
  2. Sin ejercicio no hay asiento: toda operación con asiento se rechaza (`contabilidad_no_iniciada`) y no queda registrada. La ventana la
     muestra un middleware: con botón «Iniciar ejercicio» para el responsable contable, sin botón para otros roles, mensaje genérico para
     los enlaces externos. Los pasos diarios con asientos no procesan y reintentan al día siguiente. La campana del responsable muestra
     «Falta iniciar la contabilidad».
  3. Se retiran `crear_primer_ejercicio` y el comando `poner_en_marcha_contabilidad`; se quita la extensión 3a de CON-REG-ASI.
  4. El ejercicio que creó la puesta en marcha automática en producción el 26/11/2026 (sin asientos) se elimina con el comando de uso único
     `eliminar_ejercicio_sin_apertura`, auditado con la acción nueva `baja_ejercicio_contable`, después de una branch de respaldo en Neon.
- Por qué: la fecha de inicio y el capital son decisiones del negocio, no técnicas; un ejercicio sin capital deja saldos sin sentido y la
  apertura fuera del N.º 1; la regla 9 impide que una operación cree la contabilidad por accidente.
- Consecuencias: D-84 (estado: «reemplazada en el punto 3 por D-NN»); `docs/casos_de_uso/contabilidad/ejercicio.md` y `asientos_manuales.md`;
  `docs/api/asientos.md`; `docs/patrones/asientos.md` (2b); `docs/modelo/contabilidad.md`.
- Estado: aprobada (estudiante, 26/11/2026).

### «Crons» (completa D-56 punto 1 y D-71 punto 4)

- Antes: D-56 dejó un único cron al final; D-71 dejó abierto si el IoT iba en el mismo cron o en otro.
- Decisión:
  1. Dos cron jobs de Render, **contra producción** (la demo ya no se usa): `infoponia-proceso-diario` (`python manage.py proceso_diario`,
     `0 9 * * *`, es decir 6:00 de Argentina; la hora se confirma con el Jardín Botánico) e `infoponia-revision-iot`
     (`python manage.py revision_iot`, `*/5 * * * *`, suspendido salvo en las presentaciones, D-71).
  2. Los dos usan el grupo de variables de entorno `infoponia-produccion` (las del web service, incluido `PYTHON_VERSION` igual al del web
     service), el mismo repositorio y rama, y `pip install -r requirements.txt` como compilación, **sin `migrate`** (lo corre el web service).
  3. Se prueban con «Trigger Run». El plan gratuito de Render no tiene shell: los comandos a mano contra producción se corren desde la máquina
     del estudiante con `DATABASE_URL` solo en esa ventana.
- Por qué: cada cron hace una sola cosa, con logs separados, y el del IoT se puede suspender solo (Neon Free); el costo es de 1 dólar por mes
  por cron como mínimo (verificado en la documentación de Render el 26/11/2026).
- Consecuencias: disparador «Cuando se arme el cron único» resuelto; `docs/estado.md` nombra los crons; docstring de `proceso_diario` (paso 7).
- Estado: aprobada (estudiante, 26/11/2026).

## Después del merge (lo hace el estudiante, no Claude Code)

1. Antes del merge: cron `infoponia-proceso-diario` suspendido y nada que genere asientos en producción.
2. En Neon: branch de respaldo `respaldo-antes-de-con-05` de la principal.
3. Merge a `main` → esperar «Deploy live» del web service (aplica la migración de `core`).
4. En la máquina del estudiante, con `$env:DATABASE_URL` de Neon solo en esa ventana: `python manage.py eliminar_ejercicio_sin_apertura`;
   revisar; `python manage.py eliminar_ejercicio_sin_apertura --confirmar`; `Remove-Item Env:DATABASE_URL` y cerrar la ventana.
5. Iniciar la contabilidad en producción desde la alerta (Contador o Gerente), con la fecha y el capital reales.
6. Reanudar el cron y hacer «Trigger Run»: el paso 5 dice «sin cambios». Borrar la branch de respaldo.

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code escribe los pasos para el estudiante, con mucho detalle (`docs/patrones/verificacion_a_mano.md`, D-96). Incluye el
paso de «navegador real» (la ventana sale en un formulario HTMX que se envía). Antes de los pasos van tres listas: **Verifiqué**, **Lo cubre
una prueba** y **No pude verificar**. -->

## Cierre (la completa Claude Code al cerrar)
