# Historial — InfoPonia

Registro de lo hecho, tarea por tarea. Claude Code no lo lee salvo que el estudiante lo pida (regla L6 de `CLAUDE.md`).
Se agrega una entrada al cerrar cada tarea; las entradas no se reescriben.

Hasta el 17/11/2026 (tarea AUD-CNS-REG) este contenido estaba en `docs/estado.md`, secciones «Hecho», «Registrado el
05/11/2026» y «Registrado el 08/11/2026». Se copió sin cambios, salvo la ruta de las decisiones, que pasaron a
`docs/decisiones/`. Lo que sigue vigente de estas entradas está resumido en `.claude/rules/pruebas.md`,
`.claude/rules/interfaz.md` y `docs/patrones/`.

## Hecho

- Hito 0: proyecto Django mínimo corriendo en local; repositorio `infoponia/infoponia` con main
  protegida (PR obligatoria con una aprobación); despliegue automático en Render desde main;
  base de producción en Neon.
- Decisiones D-01 a D-15 (modelo de usuario, nombres, claves, versión del modelo de dominio,
  «contacto», un solo Gerente activo, Administrador técnico, el rol no se modifica, varios
  Administradores, reemplazo del Gerente en dos operaciones, pendientes por rol, tipo de
  `telefono`). Ver `docs/decisiones/`.
- Política de pruebas fijada en `CLAUDE.md`: acumulación, unidad por regla, integración por flujo
  principal, TDD por lote en servicios con revisión del estudiante y convención de nombres.
- Tarea 01: modelo de usuario propio en la app `core` (D-01 a D-03, D-09 a D-11, D-15).
  `Usuario` con email único y sin username; seis roles con herencia multi-tabla (Gerente,
  Agrónomo, Capataz, Vendedor, Transportista, Técnico); restricciones en la base (rol vacío
  solo para superusuario, un solo Gerente activo) con `Gerente.clean()` como respaldo de
  formulario; admin con nombres visibles por rol, sin alta de `Usuario` genérico y `rol` de
  solo lectura; 10 pruebas en `core/tests/test_usuario.py`; migraciones `0001_initial` y
  `0002_alter_agronomo_options_alter_capataz_options_and_more`. Verificado a mano en el admin
  local. Rama `feature/usuario-base`.
- Neon reiniciado y migrado; Administradores recreados (06/11/2026).
- Despliegue: el servicio de Render está en el plan Starter desde el 11/11/2026, por el acceso a la consola para
  emergencias (el admin de Django quedó apagado en producción con la 05b) y porque el servicio queda siempre
  encendido.
- Tarea chica: renombradas las 10 pruebas de `core/tests/test_usuario.py` con la convención de
  `CLAUDE.md` (prefijo `test_d<numero>_`), ordenadas por decisión; no se cambió lo que verifican.
- Confirmado que los commits de la rama `feature/usuario-base` no llevan línea de coautor.
- Tarea chica: workflow de GitHub Actions (`.github/workflows/pruebas.yml`) que corre `check`,
  `makemigrations --check --dry-run` y `test` contra PostgreSQL 17 en cada PR y push a main.
- Casos de uso del bloque Cuentas y seguridad (08/11/2026): nueve casos de uso de alto nivel
  (USR-INI-SES a USR-VNC-CTA) y la especificación de seguridad SEG-01 a SEG-19, copiados en
  `docs/casos_de_uso/usuarios.md`. Prototipo HTML del bloque en
  `docs/prototipos/cuentas_y_seguridad.html`. Decisiones D-16 a D-24, todas vigentes.
- Tarea 02: plantilla base con los estilos del prototipo y HTMX 2.0.11 servido desde el repo (D-24);
  inicio y cierre de sesión con email sin distinguir mayúsculas (USR-INI-SES, SEG-01 en parte, SEG-05 a
  SEG-08); inicio de cada cuenta según el rol, con marco de celular para Capataz, Técnico y Transportista;
  acceso según el rol con `rol_requerido` y `LoginRequiredMiddleware` (SEG-13, sin el ámbito por
  invernadero). Fuentes Inter y DM Mono en el repo. Nombre de la organización configurable
  (`NOMBRE_ORGANIZACION`). 24 pruebas nuevas en `core/tests/test_usr_ini_ses.py` (34 en total), sin
  migraciones. Carpeta renombrada a `docs/casos_de_uso`. Verificada a mano. Rama
  `feature/plantilla-front`. Decisiones D-25 y D-26.
- Tarea 03: Registro de auditoría `RegistroAuditoria` (D-22), contraseña temporal (D-18, SEG-04) y
  cambio de contraseña (USR-CMB-CTR, SEG-03, SEG-10) con la pantalla «Elegí tu contraseña». Email en
  minúsculas y único sin distinguir mayúsculas (SEG-01), con migración que falla si hay duplicados. 72
  pruebas en total. Migraciones `0003` y `0004`. Rama `feature/password-temporal`. Decisión D-27.
- Tarea 04a: consultar y alta de usuarios del Gerente (USR-CNS-USR, USR-ALT-USR). Servicios
  `consultar_usuarios`, `obtener_cuenta` y `alta_usuario` en `core/servicios.py`, con auditoría en la misma
  transacción; alcance del Gerente en un único queryset (`UsuarioQuerySet.en_alcance_de`); teléfono de hasta
  25 caracteres con validador (D-21, D-28), migración `0005`. Pantallas de lista (filtros y búsqueda con
  HTMX), ficha y alta con la contraseña temporal mostrada una sola vez; entrada «Usuarios y seguridad» en el
  menú del Gerente. Componentes de D-24: desplegable propio accesible con teclado (el `<select>` nativo si no
  hay JavaScript), ventana, botón «Copiar» y avisos breves. La página 403 ofrece «Volver al inicio». 119
  pruebas en total. Verificada a mano. Rama `feature/CRUD-Usuarios`. Decisión D-28.
- Tarea 04b: modificar, restablecer, reactivar y baja de usuarios del Gerente (USR-MOD-USR, USR-BAJ-USR).
  Servicios `modificar_usuario`, `restablecer_contrasena`, `reactivar_usuario` y `baja_usuario` con bloqueo
  de la cuenta y auditoría en la misma transacción; el alta y la modificación comparten la validación de
  los datos personales (`_limpiar_datos_personales`). Se pueden modificar los datos de una cuenta inactiva
  (D-28). Pantallas de modificar y de confirmación (ventana HTMX, o página sin JavaScript); la contraseña
  temporal de un restablecimiento o una reactivación se muestra una sola vez; el aviso de la regla 8 del
  alta ofrece «Reactivar cuenta». Ajustes de diseño de la revisión a mano (D-29): los avisos breves pasan
  a ser tarjetas arriba a la derecha, con franja, ícono y barra de tiempo del color de su tipo; duran 10
  segundos (éxito y error), tienen una cruz, se anuncian a los lectores de pantalla (`role="status"`) y,
  sin JavaScript, queda el aviso fijo como respaldo. El botón secundario pasa a borde y texto en el verde
  primario sobre blanco (contraste 6,5:1, WCAG AA) en todo el sistema, los botones que son enlaces ya no
  se subrayan y todos los botones muestran el foco con Tab. Los archivos estáticos propios se piden con
  la fecha del archivo en la URL (`static_v`): `runserver` los sirve sin `Cache-Control` y el navegador
  guardaba el JavaScript viejo, por eso los avisos de la 04b parecían no desaparecer. 181 pruebas en
  total, sin migraciones. Verificada a mano. Rama `feature/CRUD-Usuarios-4b`. Decisiones D-28 y D-29.
- Tarea 05a: consultar y alta de Gerente del Administrador (USR-CNS-USR, USR-ALT-USR, D-16). Rama del
  Administrador en `UsuarioQuerySet.en_alcance_de` (Gerentes y Administradores, incluida la suya).
  `acciones_permitidas(actor, cuenta)` decide los botones de la ficha y del aviso de la regla 8: hasta la 05b, el
  Administrador no ve acciones que lo lleven a un 403. Alta solo de Gerente con la regla 2 y SEG-15: se bloquean
  todas las filas de Gerente en orden de id, el Gerente activo se busca en una consulta aparte y la restricción
  `un_solo_gerente_activo` queda de respaldo, traducida sin dar un 500. Pantallas «Cuentas» (con «(vos)» y filtro
  de rol «Gerente» y «Administrador») y «Alta de Gerente», que con un Gerente activo no muestra el formulario:
  solo el aviso con «Ver a <nombre>» y «Volver a Cuentas». Menú «Administración» → «Cuentas»; el Administrador
  entra directo a «Cuentas». Pruebas de operaciones simultáneas con dos hilos (`core/tests/concurrencia.py`).
  204 pruebas en total, sin migraciones. Verificada a mano. Rama `feature/CRUD-Admin`. Decisión D-30.
- Tarea 05b: modificar, restablecer, reactivar y baja del Administrador (USR-MOD-USR, USR-BAJ-USR, D-16) y admin
  de Django apagado en producción (SEG-18). Los servicios aceptan al Administrador con su alcance; regla 4 (no
  restablece su propia contraseña), regla 5 (un solo Gerente activo al reactivar) y precondición c (siempre queda
  un Administrador activo), con SEG-15: se bloquea primero el grupo (todos los Gerentes, o todos los
  Administradores activos, en orden de id), después se verifica que quien actúa siga activo y por último se
  bloquea la cuenta. `acciones_permitidas` ofrece al Administrador sus botones. La ventana de reactivar un Gerente
  con otro activo no pide confirmar: muestra el motivo con «Ver a <nombre>» y «Cerrar». Al darse de baja a sí
  mismo, el Administrador sale del Sistema con un aviso. `ADMIN_DJANGO_HABILITADO = DEBUG`: con `DJANGO_DEBUG=0`,
  `/admin/` responde 404. 237 pruebas en total, sin migraciones. Verificada a mano. Rama
  `feature/CRUD-Admin-5b`. Decisión D-30.
- Tarea chica de limpieza de pruebas (sin cambiar lo que verifica ninguna): las fábricas `crear_gerente`,
  `crear_administrador`, `crear_capataz` y `crear_cuenta` y los auxiliares `administrador_inactivo` y `dar_temporal_vencida` pasan a
  `core/tests/fabricas.py`, con una sola firma (nombre y apellido opcionales). Los archivos que verifican un nombre
  concreto lo pasan explícito (`LAURA` en `test_usr_mod_usr.py` y `test_usr_baj_usr.py`). Las pruebas `test_d29_`
  (`MarcoVistaTests` y `AvisosYFocoEstilosTests`) se mudaron a `core/tests/test_interfaz.py`. `requirements.txt` ya
  estaba en ASCII (UTF-8 válido, sin BOM), no en UTF-16: no hizo falta convertirlo. 237 pruebas antes y después,
  sin migraciones.
- Tarea 06a: Mi perfil (USR-GST-PRF) y cambio voluntario de contraseña (USR-CMB-CTR con la contraseña actual). Mi
  perfil muestra los datos de la cuenta con la que se opera; el Administrador modifica los suyos desde «Cuentas» y
  los demás ven a quién pedir la corrección (`quien_gestiona`). El cambio de contraseña está dentro de Mi perfil,
  reutiliza `cambiar_contrasena` y se envía a `mi-perfil/contrasena/`, solo por POST; el Administrador ya no la
  cambia solo por consola. La lista de requisitos suma «distinta de la contraseña actual» solo en Mi perfil. «Mi
  perfil» entra al menú de cuenta de todas las cuentas, con el mismo nombre para el Administrador (D-31). El lugar
  de la foto queda preparado para la 07. 259 pruebas en total, sin migraciones. Verificada a mano. Rama
  `feature/mi-perfil`. Decisión D-31.
- Tarea 06b: cuentas vinculadas (USR-VNC-CTA, SEG-09 y SEG-11). Modelo `GrupoCuentas`, `Usuario.grupo` y la
  restricción `administrador_sin_grupo` (migración `0006`). Servicios `vincular_cuenta`, `desvincular_cuenta` y
  `cuenta_para_cambiar`, y las consultas `cuentas_vinculadas` y `obtener_cuenta_del_grupo`; restablecer y reactivar
  sacan la cuenta de su grupo. Bloqueos en el orden de D-30 ampliado (grupo, invariantes, cuenta) y
  «cambio_simultaneo» cuando el grupo cambió mientras se esperaba. Mi perfil con la tarjeta «Cuentas vinculadas»
  (vincular, desvincular, «Salir del grupo» y «Cambiar»), «Cambiar de cuenta» en el menú de cuenta y los vínculos en
  solo lectura en la ficha. Pruebas de concurrencia con dos hilos, verificadas contra bloqueos desactivados. 337
  pruebas en total. Verificada a mano. Rama `feature/vinculo-cuentas`. Decisión D-32.
- Tarea chica de pendientes, punto 1 (diseño): los avisos breves de D-29 van abajo, sobre el pie, en pantallas de
  menos de 760px (apilados hacia arriba; entran y salen por abajo; sin movimiento con `prefers-reduced-motion`), y al
  cambiar de cuenta ya no se muestra el aviso «Operás como …», porque el inicio lo indica (SEG-09). Solo hoja de
  estilos y una línea de la vista, sin migraciones. 340 pruebas en total: 3 nuevas de pantallas angostas, y una
  aserción de `test_seg09_cambiar_de_cuenta_genera_sesion_nueva_y_llega_al_inicio` que pasa a exigir que no haya aviso.
  Verificada a mano. Rama `chore/pendientes`. Actualiza D-29 y D-32.
- Tarea chica de pendientes, punto 2 (limpieza de pruebas, sin cambiar lo que verifica ninguna): `contenido_de_auditoria`
  (estaba en `test_usr_mod_usr.py` y en `test_usr_vnc_cta.py`), `poner_temporal` y `dar_contrasena_temporal` (estaba en
  `test_usr_ini_ses.py` y en `test_usr_cmb_ctr.py`; queda con la firma de la primera, `(usuario, generada_hace=None)`,
  que con un solo argumento hace lo mismo que la segunda) pasan a `core/tests/fabricas.py`, y `dar_temporal_vencida`
  delega en la última. Se sacaron los imports que quedaron sin uso. 340 pruebas antes y después, con la misma lista de
  nombres y ninguna aserción cambiada; sin migraciones. Rama `chore/pendientes`.
- Tarea chica de pendientes, punto 3 (bloqueos): los cuatro bloqueos que todavía usaban `FOR UPDATE`
  (`_bloquear_gerentes`, `_bloquear_administradores_activos`, el de la cuenta en `_bloquear_cuenta_en_alcance` y el de
  `cambiar_contrasena`) pasan a `select_for_update(no_key=True)`. Resuelve el límite conocido de D-32 (restablecer
  al Gerente mientras modifica su cuenta vinculada) y el mismo ciclo entre dos Administradores que se modifican
  entre sí; queda el residual del cambio simultáneo de email. `correr_a_la_vez` suma el parámetro `primera`, que
  fija el orden de las dos operaciones sin depender de la velocidad de la máquina. 2 pruebas de concurrencia nuevas
  (`test_d32_…`), que fallaban con deadlock antes del cambio; las 10 de concurrencia, corridas con los bloqueos
  devueltos a `FOR UPDATE`, sin bloqueos y sin los de los invariantes, fallan donde corresponde. 342 pruebas en
  total, sin migraciones. Rama `chore/pendientes`. Actualiza D-30 y D-32.
- Tarea chica de pruebas de concurrencia: las 8 pruebas de SEG-15 y de las cuentas vinculadas que esperaban una ventana
  fija de 1,5 s pasan al parámetro `primera` de `correr_a_la_vez`, que ahora es obligatorio; la ventana fija se
  elimina. Con ella, en una máquina lenta seis de las ocho podían pasar sin probar nada y dos fallaban aunque todo
  estuviera bien; ahora detectan lo mismo a velocidad normal y con la segunda operación 3 s tarde. `correr_a_la_vez`
  suma `detener_antes_de` y hay 3 pruebas nuevas (`test_d32_…`): el orden de bloqueos de `restablecer_contrasena`
  (única que detecta que falte el bloqueo del grupo) y `cuida_grupo` en restablecer y en reactivar. La prueba de
  restablecer y vincular corre los dos órdenes. Matriz de 11 modos de bloqueos desactivados, a velocidad normal y
  lenta: cada prueba falla cuando falta su protección. 13 pruebas de concurrencia, 5 corridas seguidas sin fallas.
  345 pruebas en total, ninguna aserción cambiada, sin migraciones. Rama `chore/pendientes`. Actualiza D-32.
- Tarea chica de experiencia de uso (Neon Free se suspende a los 5 minutos y el primer pedido tarda): (1) envíos en
  curso: `infoponia.js` deshabilita el botón de envío de todo formulario POST con un indicador y el verbo de la acción
  (`data-enviando`, por defecto «Guardando…») y descarta un segundo envío; (2) errores de HTMX: dos avisos de error de
  D-29 («Revisá tu conexión…» sin conexión o sin respuesta en 30 s; «Volvé a intentarlo.» con un error del servidor),
  con el límite en `base.html`; Render usa el `--timeout` por defecto de gunicorn (30 s); (3) al iniciar sesión, si la
  pantalla pedida (`next`) no es accesible por rol para la cuenta que entra, va a su inicio y no al 403
  (`pantalla_accesible_para`, `core/acceso.py`). 359 pruebas en total (14 nuevas: 9 en `test_usr_ini_ses.py` y 5 en
  `test_interfaz.py`), sin migraciones, ninguna existente cambió. Rama `chore/pendientes`. Actualiza D-29.
- Forma de trabajo con las pruebas (`CLAUDE.md`, sección Tests): en local solo las de los módulos tocados, con
  `--keepdb --parallel`; la suite completa la corre el CI en el PR; las 4 clases de concurrencia (13 pruebas) llevan
  `@tag("concurrencia")` y se excluyen con `--exclude-tag concurrencia` salvo que la tarea toque bloqueos; sin
  experimentos ni matrices de bloqueos salvo que la tarea lo pida. Con `manage.py test`, `config/settings.py` usa
  `MD5PasswordHasher` (detectado con `sys.argv`) para que crear cuentas en las pruebas no cueste 1.000.000 de
  iteraciones de PBKDF2; `test_usr_cns_usr.py` ya no busca el texto «pbkdf2» sino el prefijo del hash real. Si se
  cambia el algoritmo de producción, hay que probarlo a mano. Sin otros cambios de comportamiento.
- Tarea 08: recuperar contraseña por correo (USR-RCP-CTR, SEG-12) y configuración del envío de correo (D-33 y D-34).
  Gmail por SMTP con la cuenta exclusiva de notificaciones, contraseña de aplicación solo en Render, `EMAIL_TIMEOUT = 10`
  y `CORREO_CONFIGURADO` como única fuente de verdad (`config/correo.py`); con `DEBUG` y `CORREO_CONSOLA=1`, el correo va
  a la consola. Servicios `pedir_recuperacion`, `cuenta_del_enlace` y `confirmar_recuperacion`: el pedido no escribe ni
  audita y da la misma respuesta exista o no la cuenta; la confirmación bloquea la cuenta (`FOR NO KEY UPDATE`) y vuelve a
  validar el token después de bloquear, así que el enlace es de un solo uso aun con dos pedidos simultáneos (verificado:
  con la validación antes del bloqueo, la prueba de concurrencia falla con `2 != 1`). Recuperan las cuentas activas de
  cualquier rol y también las de los Administradores. Pantallas de pedido, «Revisá tu correo», contraseña nueva y «Enlace
  no válido», con el token fuera de la URL; al terminar se lleva al inicio de sesión sin iniciar sesión. El inicio de
  sesión ofrece «¿Olvidaste tu contraseña?» solo con el correo configurado. `test_usr_rcp_ctr.py`: 48 pruebas (47 más 1 de
  concurrencia) y dos pantallas sumadas a `EnviosEnCursoTests`; corridos con los de `test_interfaz`, `test_usr_ini_ses` y
  `test_usr_cmb_ctr`: 146 pruebas, OK. Sin migraciones ni dependencias nuevas. Falta la revisión a mano (ver «En curso»)
  y cargar las variables de correo en Render. Decisiones D-33 y D-34.
- Tarea 08b: invitación por correo en el alta, el restablecimiento y la reactivación (USR-ALT-USR 0.4, USR-MOD-USR 0.5,
  USR-CNS-USR 0.4, SEG-04 y SEG-20; D-35). Quien gestiona la cuenta elige cómo obtiene la persona su primer acceso: una
  invitación por correo (por defecto, solo con el correo configurado) o una contraseña temporal. La invitación deja la
  cuenta con contraseña no utilizable y `Usuario.fecha_invitacion` (migración `0007`, con la restricción
  `invitacion_o_temporal` y la acción de auditoría `aceptacion_invitacion`); el enlace vence a los 7 días
  (`core/tokens.py`, un generador propio que no sirve para la recuperación ni al revés). Elegir la contraseña con un enlace
  es un solo servicio, compartido con la recuperación de la 08 (`_elegir_contrasena_con_enlace`: bloquea y revalida después
  de bloquear); `confirmar_invitacion` no exige el correo configurado. Los servicios devuelven un `ResultadoAcceso`; el
  envío va fuera de la transacción y, si falla, la cuenta queda con la invitación pendiente y la pantalla avisa y ofrece
  «Restablecer acceso». Pantallas: el radio de la forma de acceso en el alta y en las ventanas de restablecer y reactivar,
  los resultados, el enlace de la invitación (`invitacion/…`, con el token fuera de la URL), las insignias «Invitación
  pendiente» y «Invitación vencida», y la pista de Spam también en «Revisá tu correo». «Restablecer contraseña» pasa a
  «Restablecer acceso». Una cuenta con invitación pendiente no se puede vincular (ya ocurría; ahora tiene prueba). 64
  pruebas nuevas (62 sin concurrencia y 2 de concurrencia); los módulos tocados dan 437 pruebas sin concurrencia y 16 de
  concurrencia, OK; el experimento de mover la revalidación antes del bloqueo hace fallar las tres de enlaces de un solo uso
  (invitación, restablecer mientras se acepta y recuperación). Con `manage.py test`, `CORREO_CONFIGURADO` arranca en
  `False`. Decisión D-35. Sin dependencias nuevas.

- Tarea AUD-CNS-REG: consultar el registro de auditoría (AUD-CNS-REG 0.1, `docs/casos_de_uso/auditoria.md`) y formato
  obligatorio del detalle (D-36). `RegistroAuditoria.objects.registrar` valida que el detalle tenga solo «cambios»
  (`{campo: {antes, despues}}`, el valor anterior es obligatorio) y «datos» (contexto), con las referencias como
  `{id, texto}`; los afectados se guardan con texto y rol. Todos los servicios que auditan pasan al formato nuevo (las
  pruebas de detalle exacto cambian de forma, no de rigor). Migración de datos `0008` (única excepción deliberada a D-22:
  convierte los registros existentes, idempotente, con vuelta, sin llamar a código de la app) e índices `0009` (GIN
  `jsonb_path_ops` en los afectados y btree en la fecha). Alcance: `visibles_para(actor)`, con las acciones clasificadas
  en `ACCIONES_DE_CUENTAS` y `ACCIONES_DE_NEGOCIO` (una prueba obliga a clasificar cada acción nueva); servicios
  `consultar_auditoria`, `obtener_registro` y `puede_ver_auditoria_de`. Pantallas «Auditoría» (lista paginada de 25 con
  filtros, y detalle con Campo / Antes / Después, solo GET), entrada en el menú del Gerente y del Administrador, y «Ver
  auditoría» en la ficha de una cuenta. Los módulos tocados dan 509 pruebas sin concurrencia ni migración, 16 de
  concurrencia y 1 de migración (`@tag("migracion")`, nueva en `CLAUDE.md`), OK; `makemigrations --check` sin cambios. Sin
  dependencias nuevas (`GinIndex` no necesita `django.contrib.postgres` en `INSTALLED_APPS`). Decisión D-36.

## Registrado el 05/11/2026

- Administrador técnico, un solo Gerente activo y R002 a R006 calculadas: ya están en pendientes_MD
  (MD-55), pendientes_DER (DER-10), pendientes_CU (caso 23 y ajustes en COM-EVL-DSC y CMP-APR-ODC),
  el glosario y pendientes_prototipo (pendiente 45). Pendientes por rol (D-14) registrado el mismo
  día en pendientes_CU, pendientes_MD y pendientes_prototipo. Los CU extendidos y el diagrama del
  modelo de dominio no se tocaron: se ajustan en la próxima ronda.

## Registrado el 08/11/2026

- Resueltos: la pantalla propia del Administrador (D-16); los plazos sin Gerente activo (ninguno de
  sus pendientes tiene plazo: regla 3 de USR-BAJ-USR); los casos de uso de iniciar sesión, cerrar
  sesión y recuperar contraseña (`docs/casos_de_uso/usuarios.md`).
- Las decisiones del bloque también están en los documentos de Drive: pendientes_MD (MD-58 a MD-64),
  pendientes_DER (DER-10, DER-12 y DER-13), pendientes_CU y CU extendidos. El DER se actualiza
  después, a partir del código.

## Entradas nuevas

Una línea por tarea cerrada, con este formato:

- dd/mm/aaaa · <ID> · <qué se hizo, en una línea> · <cantidad de pruebas> · <migraciones> · <decisiones> · rama `<rama>`

- 18/11/2026 · PRD-00 · creadas las apps contabilidad, maestros, inventario y produccion (vacías, con servicios/ y tests/) y registradas en INSTALLED_APPS por niveles · 522 pruebas, sin cambios · sin migraciones · aplica D-37 · rama `feature/prd-00-crear-apps`
- 19/11/2026 · MAE-01a · invernadero: modelos de maestros (geografía, dirección multi-tabla, invernadero), Georef cargado por migración, alta (PROD-ALT-INV) y consulta (PROD-CNS-INV), menú «Producción», primeras acciones de auditoría de negocio y validadores de formato y de contenido · 99 pruebas nuevas en maestros · core 0010, maestros 0001 y 0002 · D-39 · rama `feature/mae-01-invernadero`
- 19/11/2026 · MAE-01b · invernadero: modificar con aviso del cambio de personal, reactivar y dar de baja (PROD-MOD-INV y PROD-BAJ-INV); tres puntos de extensión de maestros (impedimentos y efectos de la baja, traspaso de personal) y uno del menú de core · maestros pasa de 99 a 234 pruebas sin concurrencia (136 nuevas, una de MAE-01a reemplazada) y suma 10 de concurrencia; core suma 6 · sin migraciones · D-40 · rama `feature/mae-01-invernadero`
- 19/11/2026 · MAE-02a · alerta: modelo `Alerta` en maestros, registro de tipos (A4), API de servicios (`maestros/servicios/alertas.py`, documentada en `docs/api/alertas.md`) y alertas «invernadero sin {rol} activo» conectadas en alta, modificar, reactivar y baja, con traspaso al Agrónomo entrante (D4) y las alertas en `datos` de la auditoría · maestros sin concurrencia pasa de 234 a 322 pruebas y las de concurrencia, de 10 a 14 (336 en total); core sin cambios, 545 (el aumento frente a las 522 de PRD-00 viene de main, no de esta tarea) · migración maestros 0003 · D-41 · rama `feature/mae-02-alerta`
- 19/11/2026 · MAE-02b · alerta: la baja y la reactivación de una cuenta crean, resuelven y traspasan las alertas de los invernaderos a cargo (post e y regla 4 de USR-BAJ-USR, MD-61, D8) por los puntos de extensión nuevos de `core/extensiones.py` (efectos de la baja y de la reactivación, asignaciones de la ventana de baja y secciones del Inicio); «Personal por asignar» en el Inicio del Gerente (regla 5 de PROD-CNS-INV); `abrir_alerta` (regla 7 de 8.18); `roles` en `sincronizar_alertas_de_personal` · las pruebas de concurrencia pasan de 30 a 34 y el resto de maestros y core, de 855 a 941 (ninguna existente modificada) · sin migraciones · D-43 · la pantalla de CU-46 pasa a MAE-02c · rama `feature/mae-02-alerta`
- 20/11/2026 · documentación · corrección previa al IoT (sin código): `capataz` pasa del padre `OrdenTrabajo` a cada hija (D-53, enmienda D-50 punto 2); `core` expone el envío de correo (D-54, tarea USR-10); regla 4 de 8.22 y R068 de `modelo/maestros.md` según MD-98 y MD-99; cerrados los temas «Infraestructura» y «hardware de un sector fuera de servicio»; sección «Abiertos desde la preparación del IoT» en `temas_abiertos.md`.


- 20/11/2026 · UI-01 · estilo «Diseño v2» (D-47): hoja de estilos del prototipo de producción en `infoponia.css` (mismas variables y clases; `.btn-ghost` y los avisos conservan lo de D-29), marco con `mnav` y lugar vacío de la campana, 20 íconos más, pantallas de `maestros` y botones «Volver» de `core` al estilo nuevo; identidad de la organización (D-48: `Identidad` y `registrar_identidad_de_la_organizacion` en `core/extensiones.py`, `core/identidad.py`, color con `color-mix()` en `base.html`, correos con el nombre registrado); DM Mono quitado del repo · 951 pruebas de `core` y `maestros` en verde, 10 nuevas en `test_identidad.py` (ninguna existente modificada) · sin migraciones · rama `feature/ui-01-estilo-v2`

- 20/11/2026 · NOT-01 · notificaciones y campana (D-42): `core.Notificacion` (migración 0011) y `core/notificaciones.py`; puntos de extensión `registrar_fuente_de_alertas` y `registrar_contador_de_pendientes`; campana en el marco (panel con HTMX, página completa sin JavaScript; el Administrador no la tiene); avisos de USR-ALT-USR d, USR-BAJ-USR c (texto de la ventana), PROD-ALT-INV e y PROD-MOD-INV c; fuentes de `maestros` (`items_de_campana`, `pendientes_de_alertas`). 1100 + 34 + 1 pruebas.

- 20/11/2026 · MAE-03 · sectores y cultivos con los tipos de etapa (PROD-ALT/MOD/BAJ/CNS-SCT y -CLT): modelos `TipoEtapa` (catálogo de 5 por migración), `SectorProduccion`, `Cultivo` y, con columnas mínimas, `Variedad`, `Ciclo` y `EtapaProductiva` (migraciones `maestros` 0004 y 0005, `core` 0012); diez puntos de extensión en `maestros/extensiones.py` sin registrantes; servicios `sectores.py` y `cultivos.py` con auditoría, bloqueos invernadero → sector y cultivo, y notificación del renombre (NOT-01); la baja del invernadero pasa sus sectores a inactivos con un log por sector; pestaña «Sectores» y tarjeta «Capacidad» en la ficha, y «Cultivos y variedades» en «Producción», con HTMX y respaldo sin JavaScript. 368 pruebas nuevas; `maestros core` pasa de 1283 a 1459 sin concurrencia.

- 20/11/2026 · documentación · H2 (sin código): `motivo_cancelacion` y `fecha_resolucion_orden` también al cancelar, alineados en modelo, CU PROD-CNL-ORD, API, PRD-01 y PRD-04; texto del aviso al Capataz con el motivo (NOT-01); diferencia n.º 17 y temas abiertos.


- 21/11/2026 · MAE-04 · configuración operativa y perfil de la organización (ADM-MOD-CFG, ADM-MOD-ORG): singletons `ConfiguracionOperativa` (13 parámetros, con la vigencia del enlace de faltante) y `PerfilOrganizacion` (sin logo, D-45), con `singleton` único y `CheckConstraint` por dominio (migraciones `maestros` 0006 y 0007, `core` 0013); servicios `configuracion.py` y `perfil.py` con bloqueo `FOR NO KEY UPDATE`, todo o nada, sin cambios no audita y auditoría con antes y después; identidad de la organización registrada en `ready()` (D-48); pantalla «Configuración» en `/configuracion/` con dos pestañas, HTMX con respaldo sin JavaScript, y entrada del menú del Gerente. 1537 + 48 + 5 pruebas; dos pruebas de `core` ajustadas con permiso (`test_d24…` y el urlconf de prueba).


- 21/11/2026 · CON-01 · `contabilidad.OrigenDocumento` (D-52): tabla concreta con `tipo` (`orden_de_trabajo`, `bitacora`, `movimiento_de_insumo`); `save()` lanza `TypeError` si la clase no tiene un `TIPO_DE_ORIGEN` válido y, si lo tiene, lo copia (la hija directa fija el tipo; la nieta lo hereda); convención de las hijas documentada en el modelo · 9 pruebas nuevas en contabilidad (core sin cambios; 667 en el comando de la tarea) · `contabilidad` 0001 · aplica D-52 · rama `feature/con-01-origen-documento`


- 21/11/2026 · INV-01 · tipos de insumo y catálogo (CMP-ALT/MOD/BAJ/CNS-TIN y -INS): los cinco modelos de `inventario` con sus restricciones de base (`TipoInsumo`, `Insumo`, `InsumoInvernadero`, `LoteInsumo`, `MovimientoInsumo`, esta última hija de `OrigenDocumento`), unidades fijas, cuatro categorías del sistema por migración de datos, puntos de extensión y cuatro tipos de alerta de stock, nueve acciones de auditoría (`core` 0014), servicios con bloqueos y aviso MOD-INS, y las pantallas «Inventario» → «Catálogo» y «Categorías» (HTMX con respaldo sin JavaScript) con entrada de menú del Agrónomo · 1848 pruebas en inventario, maestros y core (63 de concurrencia y 6 de migración aparte).

- 21/11/2026 · DIA-01 · proceso diario sin cron job (D-56): `core/procesos.py` con `PasoDiario`, `ResumenDePaso`, `registrar_paso_diario` (idempotente solo si el registro es idéntico; `RuntimeError` si se repite el código con otra cosa o el orden con otro paso), `pasos_diarios` y `correr_proceso_diario(hoy, solo)` (un paso que falla se registra en el log `infoponia.proceso_diario` y los demás siguen); comando `manage.py proceso_diario` con `--fecha` (estricta: rechaza `2026-1-5`), `--solo` y `--listar`, que sale con código 1 si algún paso falla · 25 pruebas nuevas en core (15 + 10, sin base de datos; 683 en `core` completo) · sin modelos ni migraciones · aplica D-56 · rama `feature/dia-01-proceso-diario`

- 21/11/2026 · INV-02 · insumos del invernadero, existencias, ajuste de stock y vencimientos (CMP-HAB/MOD/DSH/CNS-IIN, CMP-AJT-STK y CMP-REV-VNC): API de stock de `produccion` (`existencias`, `disponible_para_planificar`, `proponer_lotes_fefo`, `ordenes_sin_cobertura`, `registrar_salida_por_consumo`, `reevaluar_alertas_del_insumo`, `habilitar_insumo`); ganchos de la baja del invernadero; ajuste con seis motivos, recuento por lote, huella y aviso de datos desactualizados; revisión de vencimientos como comando y como paso 10 del proceso diario (una transacción por invernadero); pantallas «Existencias de insumos» y «Ajustar stock» (HTMX con respaldo sin JavaScript) y botón «Habilitar en un invernadero» en el catálogo · 2329 pruebas en inventario, maestros y core (37 de concurrencia y 2 de migración aparte) · `core` 0015 (cuatro acciones de auditoría) · rama `feature/inv-02-insumos-del-invernadero-stock-y-vencimientos`

- 21/11/2026 · MAE-05 · transportista del invernadero (D-55): `maestros.TransportistaInvernadero` (OneToOne a `core.Transportista`, `PROTECT`) e `Invernadero.transportistas()`; bloque «Logística» de la ficha con agregar, trasladar (con confirmación) y quitar, con bloqueos cuenta → invernaderos en orden de id, notificación al Transportista y un `modificacion_invernadero` por invernadero que cambió; impedimento propio `transportistas_activos` en la baja del invernadero (solo activos, D-39); transportistas sin invernadero en «Personal por asignar» (contador «N pendientes»); «Invernadero» en la ficha de la cuenta y en «Mi perfil»; puntos de extensión de `maestros` (impedimentos y logística de transportistas) y de `core` (impedimentos de baja de cuenta y datos de cuenta) que registrará `comercial` · 151 pruebas nuevas (145 más 6 de concurrencia; `maestros core` sin concurrencia, 1707) · `maestros` 0008 · aplica D-55 · rama `feature/mae-05-transportista-del-invernadero`

- 22/11/2026 · MAE-02c · consulta de alertas (CU-46): servicios `consultar_alertas`, `filtros_de_alertas` y `detalle_de_alerta` (alcance con `Alerta.objects.para`, solo activas, filtros por invernadero y tipo, orden por severidad y fecha, MD-109); pantallas `/alertas/` (filtros GET con HTMX y respaldo sin JavaScript) y `/alertas/<id>/` (el detalle marca «leída», propuesta A); entrada «Alertas» del Gerente y del Agrónomo (sin contador); la campana lleva al detalle y apaga el punto rojo · 60 pruebas nuevas (`maestros core` sin concurrencia, 1767; concurrencia, 54) · sin migraciones · rama `feature/mae-02c-alerta-consulta`

- 22/11/2026 · INV-03 · variedades con su ciclo y su semilla (PROD-ALT-VAR, PROD-MOD-VAR, PROD-BAJ-VAR y PROD-CNS-VAR): `maestros.Variedad` completa (rangos, postcosecha, peso en gramos y nombre único por cultivo) e `inventario.Semilla`; servicios de lectura, bloqueo, alta, modificación, reactivación y baja, `incompatibilidades_de_rangos`, `umbral_efectivo` y `variables_incompatibles`; los tres registrantes de `maestros` (semillas, uso y tabla de variedades de cada cultivo); pantallas bajo `/produccion/` (formulario en dos pasos con resumen, advertencia de rangos, «Qué sigue», baja y reactivación) · 353 pruebas nuevas (`inventario maestros core` sin concurrencia ni migración, 2879; concurrencia, 86; migración, 8) · migraciones `maestros` 0009, `inventario` 0003 y `core` 0016 · rama `feature/inv-03-variedades-y-semillas`

- 22/11/2026 · IOT-01 · app `iot` con todo su esquema (D-72), catálogo de capacidades y seis tipos de actuador por migración, 14 parámetros IoT en `ConfiguracionOperativa` (`maestros` 0010), 11 tipos de alerta del IoT y ABM de tipos de actuador (IOT-ALT/MOD/BAJ/CNS-TAC) con HTMX y respaldo sin JavaScript; entrada «IoT» del menú; `acciones_en_uso` devuelve usos (`dict`) y `bloquear_tipo_activo` queda como contrato para IOT-02; D-80 (rango según la unidad); `infoponia.js` rehabilita el botón cuando el fragmento reemplaza al elemento del pedido y `desplegable.js` arma el combo en `afterSettle`


- 22/11/2026 · PRD-01 · siembra, bandeja y cancelación de órdenes (PROD-PNF-SMB, PROD-CNC-SMB y PROD-CNL-ORD para siembras): `produccion` con sus siete modelos (`OrdenTrabajo`, `ReservaInsumo`, `Siembra`, `OcupacionSector`, `Lote`, `Bitacora` y `Consumo`) y la secuencia de números de orden; `planificar_siembra`, `concretar_siembra` (consumos con su bitácora antes de los movimientos de insumo, FEFO a la fecha efectiva, faltante sin lote y costo del lote), `cancelar_orden` y `cancelar_orden_incluida` (de cualquier tipo de orden); lista, detalle y bandeja solo con los tipos de producción (D-67 punto 1); todos los registrantes de `maestros`, `inventario` y `core` (agujeros, impedimentos de baja, contenido y perfil de sectores, aviso de cambio de tipo, traspaso de las órdenes del Capataz, pestaña «Lotes activos», reservas de insumo, uso de variedades y asignaciones de cuenta); pantallas bajo `/produccion/` con HTMX y respaldo sin JavaScript (lista, detalle, «Nueva siembra», bandeja, «Concretar siembra» para celular y «Cancelar orden»); `traspasar` devuelve lo que tocó para la auditoría y `OrigenDocumento.save()` ya no depende del `Tipo` de la hija (D-81) · 3177 pruebas más 13 de concurrencia · `core` 0018 y `produccion` 0001 · el panel «Ritmo sostenible» queda recortado · rama `feature/prd-01-siembra-ordenes-y-bandeja`