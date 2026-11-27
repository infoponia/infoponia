# CON-05 · Iniciar el ejercicio contable con el capital inicial; sin ejercicio no hay asiento

Estado: hecha en rama (27/11/2026; falta PR y revisión a mano) | App: contabilidad | Rama: feature/con-05-iniciar-ejercicio | Ronda: — (puesta en marcha contable, 26/11/2026)

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
- El paso diario 5 sin ningún ejercicio dice «contabilidad no iniciada» (y con ejercicio y nada que abrir, «sin cambios»); los pasos con asientos dicen «contabilidad no iniciada: queda pendiente para mañana».
- El comando `eliminar_ejercicio_sin_apertura` cumple el paso 6.
- La suite completa pasa.
- Comando de pruebas: python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  y python manage.py test contabilidad.tests.test_ejercicios_concurrencia --keepdb --tag concurrencia

## Decisiones (se numeran al cerrar, M3; aprobadas por el estudiante el 26/11/2026)

### «Puesta en marcha contable» (reemplaza el punto 3 de D-84) — numerada **D-107** el 27/11/2026

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

### «Crons» (completa D-56 punto 1 y D-71 punto 4) — numerada **D-108** el 27/11/2026

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

## Verificación a mano

Escrita por Claude Code al cerrar (27/11/2026) para el estudiante. Sin navegador automatizado y sin datos cargados (D-96). Nunca una contraseña en un archivo del repo.

### Verifiqué (Claude Code)
- **Recorrido por prueba** (`contabilidad/tests/test_recorrido_iniciar_ejercicio.py`, `RecorridoDeIniciarEjercicioTests`, 3 pruebas): el Contador de la alerta a la operación pendiente (campana, libro y «Ejercicios» vacíos, «Registrar asiento» a mano, ventana con y sin HTMX, formulario, «Calcular cierre», errores 5a/5c/5d, resumen, confirmación con «Volver a la operación», asiento N.º 1, ficha, alerta que desaparece, operación pendiente que entra como N.º 2, extensión 2a); el Gerente que inicia porque no hay Contador activo; los demás roles (403 y sin alerta).
- **Migración:** `makemigrations --check` («No changes detected»); `sqlmigrate core 0054` da `BEGIN; -- (no-op) COMMIT;` (solo cambia los `choices` de `accion`: no toca tablas ni datos); aplicada en la base de pruebas al recrearla.
- **Suite completa** (base `test_…` recreada, sin las etiquetas `concurrencia` y `migracion`): en serie **11.241 pruebas, OK**; con `--parallel` **11.241 pruebas, OK**. Concurrencia de `contabilidad`: **19, OK** (incluye «dos inicios a la vez»). `manage.py check`: sin problemas.
- **Alcance de los pasos diarios** (análisis de llamadas del código, no solo `grep`): ver «Llamadores de los servicios de asientos» en el Cierre.

### Lo cubre una prueba (no hace falta mirarlo a mano)
- Permisos de quién inicia (Contador, Gerente sin Contador sí; Gerente con Contador, Vendedor, Agrónomo, sin cuenta no) y su mensaje: `ConIniEjeServicioTests` y `ConIniEjeVistaTests` en `test_con_ini_eje.py`.
- Cada error de datos (fecha futura/antigua, capital, desbalance, importes) y que se marque junto a su campo: `ConIniEjeVistaTests`.
- Atomicidad (si falla el asiento no queda el ejercicio), auditoría con actor, `contabilidad_ya_iniciada` con un ejercicio sin asiento, dos inicios a la vez: `test_con_ini_eje.py` y `test_ejercicios_concurrencia.py`.
- El middleware (login, logout, estáticos y la pantalla de iniciar no se bloquean; encabezados `HX-Retarget` y `HX-Reswap`; roles sin botón; enlace externo con el mensaje genérico; `volver` de otro sitio descartado): `test_contabilidad_no_iniciada.py`.
- Los pasos 20 y 33 sin ejercicio, con los datos reales de cámara y suministros: `comercial/tests/test_pasos_diarios_sin_contabilidad.py`.
- El comando `eliminar_ejercicio_sin_apertura` (simulación, borrado, cada negativa, transacción, auditoría): `contabilidad/tests/test_comando_eliminar_ejercicio.py`.
- «Calcular cierre» muestra el cierre exacto de la fecha escrita: `test_paso_2_calcular_con_htmx_devuelve_solo_el_formulario_con_el_cierre_correcto_de_cada_fecha`.

### No pude verificar
- **Navegador real:** el CSRF, el encabezado `Origin`, el JavaScript (la ventana que se agrega con HTMX, el botón que abre otra pestaña, el foco y el cierre con Escape) y el aspecto. Es el paso 26.
- **Que la confirmación de cada operación con asiento llegue como pedido HTMX o como envío común:** la ventana y la página dicen lo mismo, pero no sé de memoria qué pantallas usan cada camino; el paso 9 las prueba con una operación real.
- **El requisito «el registro del paso 7 se completa en no más de 3 segundos»:** no medí tiempos.
- **El comando contra una base real, el cron de Render y Neon:** nada se corrió fuera de la base de pruebas (CLAUDE.md, «Seguridad»). El comando lo corrés vos después del merge (sección «Después del merge» de la tarea).
- **El celular y el uso sin JavaScript:** están como pasos opcionales (27 y 28).

### Antes de empezar
1. En la terminal de PowerShell con el entorno virtual activo: `python manage.py migrate` (aplica `core 0054`: solo cambia opciones, no toca datos) y `python manage.py runserver`; abrí `http://127.0.0.1:8000/`.
2. Necesitás cuatro cuentas de tu base local: un **Contador** activo, el **Gerente**, un **Vendedor** y un **Agrónomo** (el del invernadero con un insumo para el paso 8). Si no tenés Contador, creálo como Gerente desde «Usuarios». La contraseña es la que ya usás para tus cuentas de prueba: no la escribas en ningún archivo.
3. **Partir sin ningún ejercicio.** Entrá como Gerente → «Contabilidad» → «Ejercicios». Si ya hay uno **sin asientos**: en la terminal `python manage.py eliminar_ejercicio_sin_apertura` (solo simula: lo muestra) y después `python manage.py eliminar_ejercicio_sin_apertura --confirmar` (lo borra; es tu base local). Si ya hay uno **con asientos**, no se puede borrar: usá una base local nueva y vacía (otro nombre en tu `DATABASE_URL` local, `migrate` y las cuatro cuentas). **Nunca con la `DATABASE_URL` de Neon.**

### Pasos
1. **El comando, simulación y negativa (terminal).** Con un ejercicio sin asientos: `python manage.py eliminar_ejercicio_sin_apertura` imprime «Se borraría el ejercicio … (del dd/mm/aaaa al dd/mm/aaaa, sin asientos). Para hacerlo, corré el comando con --confirmar.» y no borra nada (mirá «Ejercicios»: sigue). Con un ejercicio con asientos imprime «No se puede borrar: El ejercicio tiene asientos…» (cubierto por prueba).
2. **El comando, borrado (terminal).** `python manage.py eliminar_ejercicio_sin_apertura --confirmar` imprime «Ejercicio … eliminado. La contabilidad queda sin iniciar: usá «Iniciar ejercicio».». Entrá como **Gerente** → «Auditoría»: aparece «Baja de ejercicio contable», **sin usuario** (InfoPonia), con el ejercicio afectado y el motivo «puesta en marcha automática reemplazada por CON-INI-EJE».
3. **El proceso diario sin ejercicio (terminal).** `python manage.py proceso_diario`: el paso «Abrir ejercicio contable» dice «contabilidad no iniciada»; «Vencer partidas en cámara» y «Resolver suministros con incumplimientos superados» dicen «contabilidad no iniciada: queda pendiente para mañana»; los demás pasos corren normal y el cierre dice «fallidos: 0» (el comando termina bien).
4. **La campana.** Entrá como **Contador** y tocá la campana: una alerta «Falta iniciar la contabilidad» («Iniciá el primer ejercicio y cargá el capital inicial antes de registrar operaciones que generan asientos.») que lleva a «Iniciar ejercicio». Entrá como **Gerente** (hay Contador activo) y como **Vendedor**: no la tienen.
5. **Libro y «Ejercicios» vacíos.** Como **Contador**, «Contabilidad» → «Libro de gestión»: «Todavía no hay ejercicios contables», el botón **«Iniciar ejercicio»** y **no** está «Registrar asiento». Lo mismo en «Ejercicios». Como **Gerente** (con Contador): «La contabilidad todavía no está iniciada» y ningún botón.
6. **«Registrar asiento» a mano.** Como Contador escribí `http://127.0.0.1:8000/contabilidad/asientos/nuevo/`: no muestra el formulario: dice «La contabilidad todavía no está iniciada» y ofrece «Iniciar ejercicio».
7. **La pantalla de iniciar, por rol.** Como **Gerente** (con Contador activo) escribí `http://127.0.0.1:8000/contabilidad/ejercicios/iniciar/`: «Sin acceso» con «Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.». Como **Vendedor**: «Sin acceso» (403). Sin sesión (ventana privada): te lleva a iniciar sesión.
8. **Una operación con asiento sin ejercicio (Agrónomo).** Como **Agrónomo** → «Inventario» → «Ajustar stock» (`/inventario/ajuste/`): elegí un invernadero y un insumo, motivo «Carga inicial», cantidad **10**, un vencimiento futuro, «Ver resumen» y «Confirmar ajuste». Tiene que aparecer el aviso «La contabilidad no está iniciada. Pedile al Contador o al Gerente que la inicie. La operación no se registró.» **sin** botón de iniciar, con solo «Cerrar». Mirá el stock del insumo: **no cambió**.
9. **La operación del responsable.** Como **Contador**, para ver el aviso con botón necesitás una operación suya con asiento sin ejercicio: (a) creá un ejercicio sin asientos con `python manage.py shell -c "import datetime as d; from contabilidad.models import EjercicioContable as E; h=d.date.today(); E.objects.create(fecha_inicio_ejercicio=h.replace(day=1), fecha_cierre_ejercicio=h.replace(day=1, year=h.year+1)-d.timedelta(days=1), estado_ejercicio='abierto')"`; (b) como Contador abrí «Registrar asiento», fecha de hoy, descripción «Pago de la luz», Gastos Generales al **Debe 50,00** y Caja al **Haber 50,00**, «Revisar asiento» (ve el resumen); (c) **sin cerrar esa pestaña**, en la terminal `python manage.py eliminar_ejercicio_sin_apertura --confirmar`; (d) volvé a la pestaña y tocá «Confirmar y registrar». Tiene que aparecer «Lo que estás registrando genera un asiento contable y la contabilidad todavía no está iniciada. La operación no se registró.» con **«Iniciar ejercicio»** y «Cerrar». Si la pantalla se envió como página común, el botón lleva a «Iniciar ejercicio» con `?volver=` en la dirección; si apareció como ventana encima de la pantalla, el botón abre **otra pestaña** y dice «Se abre en otra pestaña. Cuando termines, volvé a esta y confirmá la operación de nuevo.». Las dos son correctas.
10. **El formulario (paso 2 del caso de uso).** Entrá por el botón. Ves: **Fecha de inicio** con la fecha de hoy (el calendario no deja elegir antes de hace casi un año ni después de hoy), el **Cierre previsto** debajo, las cinco cuentas en dos bloques: **Debe** (1.1.01 Caja, 1.1.02 Banco c/c, 1.1.03 Deudores por Ventas) y **Haber** (3.1.01 Capital Inicial con asterisco, 2.1.01 Proveedores), cada una con su campo de importe, y el texto «Los insumos y los lotes que ya existían no van acá…». No aparece Insumos en Stock ni ninguna otra cuenta.
11. **«Calcular cierre».** Escribí la fecha **15/11/2026** (con el teclado, aunque el calendario no la muestre) y tocá **«Calcular cierre»**: el cierre previsto pasa a **14/11/2027** sin recargar la pantalla ni mover el foco, y lo que escribiste en los importes se conserva. Probá **01/03/2026**: **28/02/2027**. Nada se calcula solo al cambiar la fecha: solo con el botón.
12. **Errores.** Dejá los importes en blanco y tocá «Ver resumen»: «El capital inicial es obligatorio para iniciar la contabilidad.» junto al campo de Capital Inicial. Probá: fecha **28/11/2026** (mañana): «La fecha de inicio no puede ser futura.»; fecha **27/11/2025**: «…la más antigua que se puede elegir es el 28/11/2025.»; Caja **1.000,00** y Capital **900,00**: «El Debe ($ 1.000,00) y el Haber ($ 900,00) no coinciden: la diferencia es de $ 100,00.»; Caja **abc** o **-5** o **10,005**: «El importe tiene que ser un número mayor que cero, con hasta dos decimales.» junto a Caja. Con varios errores a la vez, todos aparecen juntos y lo escrito no se pierde.
13. **El resumen (paso 5).** Fecha **15/11/2026**, Caja **800.000,00**, Banco c/c **200.000,00**, Deudores por Ventas **50.000,00**, Capital Inicial **1.000.000,00**, Proveedores **50.000,00**; «Ver resumen». Ves: Ejercicio 1, empieza el 15/11/2026 y cierra el 14/11/2027 (12 meses) · abierto; «Asiento N.º 1 · Asiento de apertura», fecha 15/11/2026; las cinco líneas; Totales **$ 1.050.000,00** y **$ 1.050.000,00**; diferencia **$ 0,00**; y los botones «Confirmar e iniciar», «Volver a editar» y «Cancelar». Todavía no se creó nada (mirá «Ejercicios»).
14. **«Volver a editar».** Vuelve al formulario con la fecha y los importes tal como los escribiste.
15. **Confirmar (pasos 6 a 8).** Ver resumen otra vez y **«Confirmar e iniciar»**: «La contabilidad quedó iniciada. Se creó el Ejercicio 1 (del 15/11/2026 al 14/11/2027) con el asiento N.º 1, el asiento de apertura.», con «Ver el libro de gestión» y el texto de lo que sigue (carga inicial de insumos y lotes existentes, con quién las hace). Como Contador **no** ves «Registrar lote existente» (no lo abre). Si entraste con `?volver=`, ves también «Volver a la operación».
16. **El libro.** «Contabilidad» → «Libro de gestión»: el asiento **N.º 1 «Asiento de apertura»**, fecha **15/11/2026**, tipo manual. Abrilo: cinco movimientos y «registrado por» el Contador. «Por cuenta»: Caja con saldo 800.000,00 y Capital Inicial 1.000.000,00 (a su favor).
17. **Todo vuelve.** La alerta de la campana desapareció; el libro muestra «Registrar asiento»; en «Registrar asiento» el atajo «Asiento de apertura» **ya no está** y «Venta de producción previa» sí; «Ejercicios» lista «Ejercicio 1».
18. **Ya iniciada (extensión 2a).** Escribí otra vez `/contabilidad/ejercicios/iniciar/`: «La contabilidad ya está iniciada» con «Ver los ejercicios», sin formulario. Volvé atrás con el navegador y reenviá la confirmación: tampoco crea otro (misma pantalla).
19. **La operación pendiente entra.** Repetí el paso 8 (Agrónomo, carga inicial de 10): ahora se registra y vuelve a la lista de existencias. En el libro, el asiento **N.º 2** (automático, Debe Insumos en Stock / Haber Capital Inicial) con la fecha de hoy.
20. **Fechas del libro.** Como Contador, «Registrar asiento» con fecha **01/11/2026** (anterior al inicio del 15/11/2026): se rechaza con «La fecha 01/11/2026 no admite un asiento: es anterior al primer ejercicio contable, que empieza el 15/11/2026.».
21. **Auditoría.** Como Gerente, «Auditoría»: «Alta de ejercicio contable» (por el Contador, datos «origen: puesta en marcha»), «Alta de asiento contable» y cinco «Alta de movimiento contable» de la apertura.
22. **Contraasiento de la apertura (decisión pendiente).** Como Contador abrí el asiento N.º 1: ofrece «Contraasentar» como a cualquier asiento. Queda permitido por ahora (`docs/temas_abiertos.md`); no lo hagas si querés conservar los datos.
23. **El Gerente que inicia sin Contador.** Cubierto por el recorrido: da de baja al Contador solo si querés repetirlo en una base nueva (el Gerente pasa a ver la alerta y a poder iniciar, con rol Gerente en el log).
24. **Que nada se bloquea.** Con la contabilidad sin iniciar (antes del paso 15, o en una base nueva), cerrar sesión, volver a entrar y moverse por el menú anda sin errores ni redirecciones en bucle.
25. **Otros roles.** Capataz y Técnico no ven nada de esto.
26. **Navegador real (obligatorio).** Abrí la pantalla en una **ventana privada** (sin sesión), entrá como Contador y **enviá el formulario hasta el final** (pasos 11 a 15 y la confirmación); después volvé a abrirla. Tiene que mostrar el resultado esperado. Probá también el aviso del paso 8 y 9 como **pedido HTMX**: tiene que verse encima de la pantalla con «Cerrar» (y Escape lo cierra). Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver. Con el botón «Iniciar ejercicio» de la ventana HTMX, se abre **otra pestaña**; la operación sigue abierta en la primera.
27. **(Opcional) Sin JavaScript.** Desactivá JavaScript: «Calcular cierre» vuelve a dibujar la página con el cierre calculado; Enter en un importe dispara «Ver resumen»; todos los botones funcionan.
28. **(Opcional) Celular.** Abrí la pantalla en un celular o con el ancho reducido: el formulario, el resumen y la confirmación se ven en una columna y los botones se alcanzan.

## Cierre

Hecha el 27/11/2026 en la rama `feature/con-05-iniciar-ejercicio`. **Falta:** el PR, la revisión a mano y el navegador real; después del merge, los seis pasos de «Después del merge» (los hace el estudiante).

### Qué se hizo
- **Paso 1.** `ejercicios.contabilidad_iniciada()`; `abrir_ejercicio_si_corresponde` ya no crea el primer ejercicio; `registrar_asiento_automatico` (al principio, también con importe cero), `registrar_asiento_manual`, `contraasentar` y los dos resúmenes lanzan `contabilidad_no_iniciada` antes de bloquear; se retiraron `crear_primer_ejercicio` y el comando `poner_en_marcha_contabilidad`.
- **Paso 2.** `iniciar_ejercicio`, `resumir_inicio`, `fecha_inicio_minima`, `_crear` con actor, `exigir_quien_inicia`; texto nuevo de 3.1.01.
- **Paso 3.** `ContabilidadNoIniciadaMiddleware` y sus dos plantillas; las vistas que re-lanzan el error; la guarda en los pasos diarios 20 y 33; la fuente de la campana.
- **Paso 4.** La pantalla «Iniciar ejercicio» (formulario, resumen, confirmación y 2a); el botón en «Ejercicios» y en el libro vacío; «Registrar asiento» oculto o explicado sin ejercicio; se quitó el atajo «Asiento de apertura».
- **Paso 5.** Las pruebas de las demás apps (helper `iniciar_contabilidad_para_pruebas`), la demo y su documento.
- **Paso 6.** El comando `eliminar_ejercicio_sin_apertura`, la acción `baja_ejercicio_contable` y la migración `core/0054_contabilidad_baja_de_ejercicio`.
- **Paso 7.** El docstring de `proceso_diario.py`.

### Pruebas
Suite completa en serie: 11.241 OK; `--parallel`: 11.241 OK; concurrencia de `contabilidad`: 19 OK (todo con la base de pruebas recreada). Comando de la tarea: `python manage.py test --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` y `python manage.py test contabilidad.tests.test_ejercicios_concurrencia --keepdb --tag concurrencia`.

### Decisiones
Dos: «Puesta en marcha contable» (**D-107**) y «Crons» (**D-108**), numeradas con `git fetch` el 27/11/2026 (los últimos de `main` eran D-105) y escritas en `docs/decisiones/`. Texto en la sección «Decisiones» de esta tarea.

### Llamadores de los servicios de asientos (`grep` del 27/11/2026, sin pruebas)
**`registrar_asiento_automatico`** (todos dentro de una operación con su propia transacción):
- `comercial/servicios/asientos_comerciales.py`: 10 llamadas (`asentar_salida_por_cosecha`, `asentar_merma_de_partida`, `asentar_merma_de_entrega`, `asentar_consumo_de_envase`, `asentar_entrega`, `asentar_cobro`, `asentar_cobro_de_compra_venta`, `asentar_anulacion`, `asentar_indemnizacion`, `asentar_multa_de_resolucion`).
- `compras/servicios/recepciones.py:568`, `compras/servicios/pagos.py:240`, `compras/servicios/correcciones.py:341`.
- `inventario/servicios/ajustes.py:635`.
- `produccion/servicios/asientos_de_produccion.py` (2: `asentar_consumo`, `asentar_merma`) y `produccion/servicios/lotes_existentes.py:402`.

**`registrar_asiento_manual`:** solo `contabilidad/views.py:443` (la pantalla «Registrar asiento»). `contraasentar`: solo `contabilidad/views.py` (pantalla del contraasiento).

**Pasos diarios que los alcanzan** (análisis de llamadas resueltas por módulo importado, `scratchpad/alcance2.py`, sobre los 14 pasos registrados):
| Orden | Paso | ¿Alcanza un asiento? |
|---|---|---|
| 5 | `abrir_ejercicio` | no (informa «contabilidad no iniciada» sin ejercicio) |
| 10 | `revisar_vencimientos` | no |
| **20** | `vencer_partidas_en_camara` | **sí**: `_vencer_partida` → `_vencer_en_transaccion` → `asentar_merma_de_partida` (**con guarda**) |
| 25 | `reasignar_camara` | no |
| 27 | `avisar_enlaces_vencidos` | no |
| 30 | `vencer_pagos` | no |
| **33** | `resolver_suministros` | **sí**: `resolver_suministro` → `_resolver` → `asentar_multa_de_resolucion` (**con guarda**) |
| 35 | `cerrar_rescisiones` | no |
| 40 | `pre_reservar_suministros` | no |
| 50 | `planificar_entregas` | no |
| 60 a 63 | compras (pedidos vencidos, recordatorio, sin elegible, automáticos) | no |
Límite del análisis: sigue las llamadas a funciones de módulos importados, funciones del mismo archivo y `self.método()`; **no sigue las llamadas sobre objetos que no puede resolver** (por ejemplo un servicio que llega por una instancia). Un primer análisis solo por nombre marcó de más todos los pasos (por nombres genéricos como `_resolver` o `registrar`) y se descartó; el 20 y el 33 además los confirma una prueba con datos reales.

### Vistas en las que se volvió a lanzar `contabilidad_no_iniciada` (`relanzar_si_no_iniciada`)
`compras/views_pagos.py` (el pago a proveedor, que ya mostraba el resumen y el registro) y en `contabilidad/views.py`: el cierre del ejercicio, el asiento manual (las dos ramas: fecha inválida y registro) y el contraasiento. `demo/management/commands/cargar_demo.py` es un comando y no aplica.

### Pantallas: lo que se corrigió del prototipo (D-61)
No hay prototipo de CON-INI-EJE: se armó con el estilo de «Registrar asiento» (CON-03b). Correcciones y agregados: el cierre previsto se recalcula con el botón «Calcular cierre» y no con `change` (interfaz.md); resumen propio (paso 5) y confirmación del paso 8 por redirección (`?listo=1`); «Registrar asiento» sin ejercicio explica en lugar de mostrar el formulario; el libro vacío no ofrece «Registrar asiento»; «Ejercicios» y el libro vacío ofrecen «Iniciar ejercicio» solo a quien puede (D-30); la confirmación no enlaza la carga inicial de insumos (es del Agrónomo) sino que dice quién la hace.

### Fuera de lo previsto (todo anotado también en `docs/temas_abiertos.md`, sección «CON-05»)
- Se agregó el código de error `fecha_invalida` (a `docs/casos_de_uso/contabilidad/ejercicio.md`) y `resumir_contraasiento` también chequea la contabilidad iniciada.
- El paso diario 5 sin ejercicio dice «contabilidad no iniciada» (la tarea decía «sin cambios»; ajuste del estudiante; «Hecho cuando» ya corregido).
- Convención de fábricas: `ejercicio(ABIERTO, …)` reemplaza al del helper si no tiene asientos (solo en pruebas; probada en `test_fabricas.py`).
- Tres pruebas de `produccion` que exigían cero ejercicios después de un rechazo (`test_prod_cnc_smb.py`: `ConcretarSiembraAsientoTests.test_garantia_un_rechazo_no_crea_asientos_ni_abre_el_ejercicio`; `test_prod_reg_apl.py`: `RegistrarAsientoTests.test_garantia_un_rechazo_no_crea_asientos_ni_abre_el_ejercicio`; `test_prod_reg_mrm.py`: `RegistrarMermaAsientoTests.test_garantia_un_rechazo_no_crea_asientos`): la clase ahora trae el ejercicio del helper, así que comparan el conteo de ejercicios **antes y después** del rechazo en lugar de esperar 0 (misma garantía: un rechazo no crea ejercicios). Cambio aprobado por el estudiante el 27/11/2026; reemplaza a una versión que borraba el ejercicio del helper al empezar.
- Pruebas del grupo 2 reemplazadas por la negativa de la regla 9 (aprobadas el 27/11/2026): `test_d92_punto_2_sin_ejercicio_el_primero_se_abre_solo` → `test_regla_9_sin_ejercicio_la_cosecha_no_se_registra` (`comercial/tests/test_prod_cnc_csc.py`); `test_d92_el_cobro_asienta_aunque_no_haya_ejercicio_abierto_y_se_recupera_solo` → `test_regla_9_el_cobro_sin_ejercicio_no_se_registra` (`test_com_reg_cbr.py`); `test_d92_sin_ejercicio_el_ajuste_se_registra_abre_el_primero_y_muestra_el_valor` → `test_regla_9_sin_ejercicio_el_ajuste_no_se_registra_y_el_resumen_sigue_mostrando_el_valor` (`inventario/tests/test_cmp_ajt_stk_recuento.py`); `test_post_f_el_asiento_es_debe_insumos…` (`compras/tests/test_cmp_reg_rcp.py`: sin la aserción inicial y con el docstring ajustado); `test_post_j_ninguna_otra_accion_de_auditoria…` (`produccion/tests/test_prod_pnr_fds.py`: sin `alta_ejercicio_contable`); y los tres recorridos (`comercial/tests/test_recorrido_asientos_comerciales.py`, `inventario/tests/test_recorrido_ajuste_con_asiento.py`, `produccion/tests/test_recorrido_asientos_de_produccion.py`: agregan el paso «sin ejercicio, no se registra» y después `iniciar_contabilidad_para_pruebas()`).
- **Grupo 1** (697 pruebas en 43 archivos de comercial, compras, inventario y producción): solo líneas agregadas del helper (92), sin cambiar ninguna aserción (`git diff` sin líneas borradas en esos archivos fuera del grupo 2).
- **Demo:** `cargar_contabilidad` inicia la contabilidad con `iniciar_ejercicio` (Contador de la demo, primer día del mes de HOY, Caja y Capital Inicial de $ 1.000.000,00); `docs/demo/datos_de_la_demo.md` dice que un asiento manual o contraasiento de un mes anterior al inicio se rechaza.
- **`iot`, fuera del alcance de CON-05, autorizado por el usuario:** en `iot/tests/test_modelos_mantenimiento.py` la expresión `^OT-\d{4}$` pasó a `^OT-\d{4,}$` (el código de la orden usa el id). Solo la prueba. Queda una igual en `comercial/tests/test_prod_asg_stk.py` (en `temas_abiertos`).
- **Base de datos:** no se borró ningún dato de la base de desarrollo; las bases `test_…` se recrearon sin permiso (D-101).

### Propuestas M3 (**aplicadas el 27/11/2026** a pedido del estudiante; el texto de abajo es lo que se propuso)
1. **`docs/estado.md`** (≤ 2 KB), reemplazar «En curso» y «Siguiente»: «Actualizado: 27/11/2026 (CON-05 en rama).» **En curso:** «CON-05 (iniciar el ejercicio con el capital inicial; sin ejercicio no hay asiento): hecha en rama `feature/con-05-iniciar-ejercicio`; falta PR, revisión a mano (28 pasos) y navegador real. **Antes de operar en producción:** después del merge, el estudiante corre `eliminar_ejercicio_sin_apertura` (Neon, con respaldo) e inicia la contabilidad desde la alerta (pasos de «Después del merge» de la tarea). Hasta entonces: cron diario suspendido y nada que genere asientos en producción.» **Siguiente:** quitar la línea de CON-05 y dejar «Procesos: `proceso_diario` en el cron `infoponia-proceso-diario` (6:00) y `revision_iot` en `infoponia-revision-iot` (cada 5 min, suspendido salvo presentaciones; decisión D-108)». En «Revisiones a mano pendientes»: sumar «CON-05: 28».
2. **`docs/tareas/README.md`:** sacar la fila de CON-05 (queda hecha).
3. **`docs/historial.md`** (una línea): `- 27/11/2026 · CON-05 · iniciar el ejercicio contable con el capital inicial; sin ejercicio no hay asiento (CON-INI-EJE; D-107, D-108; reemplaza D-84 punto 3): ejercicios.iniciar_ejercicio / resumir_inicio / fecha_inicio_minima / contabilidad_iniciada; ContabilidadNoIniciadaMiddleware (ventana HTMX o página según quién opera); campana «Falta iniciar la contabilidad»; guarda «contabilidad no iniciada» en los pasos 20 y 33 (y el paso 5); pantalla «Iniciar ejercicio» (formulario, resumen y confirmación); se retiran crear_primer_ejercicio, el comando poner_en_marcha_contabilidad y el atajo «Asiento de apertura»; comando de uso único eliminar_ejercicio_sin_apertura con la acción baja_ejercicio_contable (core 0054, solo choices); demo y ~700 pruebas de otras apps con iniciar_contabilidad_para_pruebas; 11.241 pruebas OK.`
4. **`docs/revisiones_pendientes.md`:** sección nueva «## CON-05 · Tarea CON-05 (iniciar el ejercicio contable con el capital inicial)» con los 28 pasos de «Verificación a mano» tal cual (una línea por paso, con casilla `- [ ]`), precedida de «Antes de empezar» y de la nota «los pasos 1 a 3 son de terminal; el 26 es el navegador real».
5. **Decisiones** (`docs/decisiones/D-107.md` y `D-108.md`, texto de la sección «Decisiones» de esta tarea, «Estado: aprobada (estudiante, 26/11/2026)», con «Fecha: 26/11/2026» y «Fuentes»; y dos filas en `docs/decisiones/README.md`):
   - `| D-107 | Puesta en marcha contable: el Contador inicia el ejercicio con el capital inicial; sin ejercicio no hay asiento | contabilidad | aprobada | CON-INI-EJE; regla 9 y middleware; se retiran crear_primer_ejercicio, poner_en_marcha_contabilidad y la extensión 3a; baja del ejercicio de producción con eliminar_ejercicio_sin_apertura (reemplaza el punto 3 de D-84) |`
   - `| D-108 | Crons: dos cron jobs de Render contra producción, sin migrate | despliegue | aprobada | infoponia-proceso-diario (0 9 * * *) e infoponia-revision-iot (*/5 * * * *, suspendido salvo presentaciones); grupo de variables infoponia-produccion; sin shell: comandos a mano desde la máquina del estudiante (completa el punto 1 de D-56 y el punto 4 de D-71) |`
   - **Estado de D-84:** «Estado: aprobada por el estudiante el 23/11/2026; **el punto 3 lo reemplaza D-107** (27/11/2026): el primer ejercicio lo crea CON-INI-EJE y ya no se crea solo ni con el comando `poner_en_marcha_contabilidad`».
   - **Estado de D-56:** «…; enmendada por D-69 (…); **el punto 1 (cron único al final) lo completa D-108**: dos cron jobs (`infoponia-proceso-diario` e `infoponia-revision-iot`)».
   - **Estado de D-71:** «vigente (validada por el estudiante el 21/11/2026); **el punto 4 (un solo cron o dos) lo resuelve D-108**: dos cron jobs, el del IoT cada 5 minutos y suspendido salvo en las presentaciones».
6. **Modelos y disparadores:** no se crearon modelos. Disparadores: «Cuando se arme el cron único» ya figura como resuelto el 26/11/2026 (línea 570 de `docs/disparadores.md`: sin cambios). **Nacen** dos: «**Cuando se retire el comando `eliminar_ejercicio_sin_apertura`** (uso único; una tarea posterior, después de correrlo en producción)» y «**Cuando se decida el contraasiento de la apertura**» (hoy permitido; ver `temas_abiertos`, punto 1).
7. **Plan de la ronda:** CON-05 figura con «Ronda: —»: no hay fila en ningún `docs/tareas/ronda_<nombre>.md`.
8. **Lo implementado distinto de lo escrito** (para `docs/temas_abiertos.md`): ya está escrito en la sección «CON-05» (puntos 1 a 9); se sumó el punto 10 (`fecha_invalida` y el mensaje de `exigir_quien_inicia`). No se corrigió ningún documento de las fuentes de más peso en silencio: `ejercicio.md` tiene la lista de códigos con `fecha_invalida` (único cambio en `docs/casos_de_uso/`), pedido por el estudiante.

### Detalle por paso (notas tomadas durante la tarea)

- **Agregado fuera del plan (paso 1):** `asientos.resumir_contraasiento` también lanza `contabilidad_no_iniciada` (tras los permisos, antes de leer el asiento), para que la pantalla del contraasiento sin ejercicio no dé 404 antes que el motivo real. El plan nombraba `registrar_asiento_automatico`, `registrar_asiento_manual` y `contraasentar`; `resumir_asiento_manual` entra por el chequeo del manual.
- **Cambio de texto (paso 1):** el paso diario 5 sin ningún ejercicio dice «contabilidad no iniciada» (la tarea decía «sin cambios»; ajuste del estudiante, 26/11/2026). «Hecho cuando» ya está corregido. Anotar en `temas_abiertos` para actualizar el caso de uso en el Drive.
- **Pruebas reemplazadas por la regla 9 (paso 1):** `test_asientos_automaticos.py` (la creación automática del primer ejercicio por la primera operación), `test_con_abr_eje.py` (clase del primer ejercicio y `crear_primer_ejercicio`), `test_paso_diario_ejercicio.py` (paso 5 sin ejercicio y el comando retirado). Quitada: la concurrencia de «dos aperturas sin ejercicio» (sin ejercicio no hay nada que auditar ni disputar; la cubre «dos inicios a la vez» del paso 2). Los recorridos `test_recorrido_libro_y_cierre.py` y `test_recorrido_nucleo_contable.py` crean el ejercicio con `ejercicio_abierto(...)` en lugar de llamar al comando retirado.
- `ResultadoApertura.primero_creado` se conserva y queda siempre en `None`.
- **Códigos de error de CON-INI-EJE (paso 2):** se agregó `fecha_invalida` (la fecha de inicio no es una fecha) a la lista de «Cómo se aplica» de `docs/casos_de_uso/contabilidad/ejercicio.md` (con él son seis los de fecha e importes; `cuenta_no_permitida_en_apertura` ya estaba nombrado). El mensaje del Gerente con un Contador activo se ajusta en el paso 4, con la pantalla.
- **Contraasiento de la apertura:** queda permitido por ahora (decisión pendiente en `temas_abiertos`, sin cambios de código).
- **Vista y plantilla de «Iniciar ejercicio» PROVISORIAS hasta el paso 4:** en el paso 3 se agregó la ruta `contabilidad:iniciar` (`contabilidad/ejercicios/iniciar/`), la vista `views.iniciar_ejercicio` (permisos de la regla 1 y 403, y el mensaje de la extensión 2a) y la plantilla `contabilidad/iniciar.html`, solo para que la campana, la ventana del middleware y sus pruebas tengan adónde llevar. El paso 4 las reemplaza por la pantalla completa (formulario, resumen y confirmación).
- **Archivos de pruebas nuevos que no estaban en el plan (paso 3):** `comercial/tests/test_pasos_diarios_sin_contabilidad.py` (los pasos 20 y 33 con los fixtures reales de cámara y de suministros; vive en `comercial` porque ahí están sus fixtures y `contabilidad` no importa de apps altas, ni siquiera en pruebas) y `contabilidad/tests/urls_de_prueba.py` (una URLconf SOLO de pruebas con tres vistas mínimas para probar el middleware de punta a punta). `urls_de_prueba.py` no está incluida en `config/urls.py` ni en ninguna URL real: solo se activa con `@override_settings(ROOT_URLCONF=...)` en `VentanaDeContabilidadNoIniciadaTests` (verificado con `grep`: lo nombran únicamente esa prueba y el propio archivo).
- **Pruebas de otras apps que fallaban por la campana (regla 10), arregladas en el paso 3 con autorización del estudiante (26/11/2026):** en `maestros/tests/test_campana_alertas.py`, la campana del Gerente sin Contador ni ejercicio suma «Falta iniciar la contabilidad», lo que cambia el orden y la cantidad de alertas que esperan. Se agregó `iniciar_contabilidad_para_pruebas()` (helper nuevo de `contabilidad/tests/fabricas.py`: crea el ejercicio abierto directo, sin auditoría ni `iniciar_ejercicio`) en el `setUp` de `CampanaAlertasFuenteTests` y de `CampanaConAlertasDeMaestrosTests`, sin cambiar ninguna aserción (3 líneas: el import y los dos `setUp`). Las 5 pruebas:
  1. `test_d42_core_ordena_por_severidad_las_alertas_de_maestros_y_conserva_el_orden_dentro_de_cada_nivel`
  2. `test_d42_el_gerente_ve_en_alertas_la_de_sin_capataz_con_su_severidad_y_el_enlace_al_detalle`
  3. `test_d42_el_punto_sigue_a_la_lectura_de_la_alerta`
  4. `test_r10_de_punta_a_punta_la_campana_pasa_por_alertas_ir_marca_leida_y_llega_a_la_pantalla_del_registrante`
  5. `test_regla_r7_abrir_una_alerta_desde_la_campana_la_marca_leida_y_apaga_el_punto_rojo`
  En el paso 5 se aplica el mismo criterio a cualquier otra prueba que falle por esto, y se listan acá.
- **Pruebas viejas reemplazadas en el paso 4 por la extensión 3a quitada (el atajo «Asiento de apertura» ya no existe; la apertura es CON-INI-EJE):**
  1. `contabilidad/tests/test_asientos_vistas.py`: `test_ext_3a_el_atajo_de_apertura_precarga_la_descripcion_y_las_cuentas_sin_importes` → `test_ext_3a_quitada_el_atajo_de_apertura_ya_no_precarga_nada` (aprobada por el estudiante).
  2. `contabilidad/tests/test_recorrido_asientos_manuales.py`: `test_recorrido_del_contador_del_formulario_al_contraasiento_y_el_cierre`, el paso 3 («Extensión 3a: el atajo precarga…») pasa a verificar que el atajo no se ofrece y que escribirlo a mano no precarga ni registra (aprobada).
  3. **No estaba en la lista aprobada, apareció al implementar:** `contabilidad/tests/test_asientos_vistas.py`: `test_flujo_principal_el_formulario_trae_hoy_dos_filas_el_buscador_de_cuenta_y_los_atajos` exigía `assertIn("Asiento de apertura", contenido)` (el botón del atajo): ahora es `assertNotIn` y el docstring dice «el atajo de venta previa» en lugar de «los dos atajos». Misma regla, mismo criterio; se avisa para que el estudiante lo revise.
- **Prueba de «Calcular cierre» reforzada (pedido del estudiante):** `test_paso_2_calcular_con_htmx_devuelve_solo_el_formulario_con_el_cierre_correcto_de_cada_fecha` verifica, dentro de `id="cierre-previsto"`, la fecha de cierre exacta de cinco fechas escritas (1/1, 15/11, 1/3 antes de un bisiesto, 29/2 y hoy) y que no aparece la de otra; con una fecha ilegible el elemento muestra «—».
- **Mensaje del Gerente con un Contador activo (ajustado en el paso 4):** `ejercicios.exigir_quien_inicia(actor)` (función nueva, la usan `iniciar_ejercicio`, `resumir_inicio` y la pantalla): «Lo inicia el Contador: mientras haya un Contador activo, el Gerente no inicia la contabilidad.»; para los demás, «Solo el Contador, o el Gerente si no hay un Contador activo, inicia la contabilidad.». Antes reutilizaba el de «registrar asientos».
- **Pantallas: lo que se corrigió del prototipo (D-61)** (no hay prototipo de CON-INI-EJE; se armó con el estilo de «Registrar asiento»): el botón «Calcular cierre» en lugar de recalcular con `change` (interfaz.md); un resumen propio (paso 5) y la confirmación del paso 8 por redirección (`?listo=1`), que el extracto no detalla; «Registrar asiento» abierto a mano sin ejercicio muestra «La contabilidad todavía no está iniciada» con el acceso a iniciar en lugar del formulario; el libro vacío no muestra «Registrar asiento»; la pestaña «Ejercicios» y el libro vacío ofrecen «Iniciar ejercicio» solo a quien puede (D-30); la carga inicial de insumos (del Agrónomo) no se enlaza desde la confirmación: se explica quién la hace.
- **Fuera del alcance de CON-05, autorizado por el usuario (27/11/2026):** `iot/tests/test_modelos_mantenimiento.py::test_md111_crear_una_orden_le_pone_tipo_mantenimiento_y_su_codigo_es_ot_nnnn`: la expresión `^OT-\d{4}$` pasó a `^OT-\d{4,}$` (el código de la orden usa el id y en la corrida completa en serie pasa de 9999). Solo la prueba; el código no se tocó.

