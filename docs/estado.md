# Estado del proyecto — InfoPonia

Última actualización: 14/11/2026. Este archivo se reescribe al final de cada sesión.

## Hecho

- Hito 0: proyecto Django mínimo corriendo en local; repositorio `infoponia/infoponia` con main
  protegida (PR obligatoria con una aprobación); despliegue automático en Render desde main;
  base de producción en Neon.
- Decisiones D-01 a D-15 (modelo de usuario, nombres, claves, versión del modelo de dominio,
  «contacto», un solo Gerente activo, Administrador técnico, el rol no se modifica, varios
  Administradores, reemplazo del Gerente en dos operaciones, pendientes por rol, tipo de
  `telefono`). Ver `docs/decisiones.md`.
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

## En curso

- Nada por ahora.

## Siguiente

1. Después del primer merge con el workflow: en GitHub, Settings → Branches (o Rules), exigir que
   el check de `pruebas.yml` pase para poder mergear a main.
2. Bloque Cuentas y seguridad, una tarea por rama y por PR, en este orden (cada una cita las
   secciones de `docs/casos_de_uso/usuarios.md` que usa):

   | Tarea | Contenido | Necesita |
   |---|---|---|
   | 05 | **05a hecha** (consultar, alta de Gerente, menú «Cuentas», SEG-15 del Gerente); **05b hecha** (modificar, restablecer, reactivar, baja, SEG-15 de los Administradores y SEG-18). Cuentas del Administrador con el mismo flujo y su alcance (D-16, en `en_alcance_de`); invariantes de las cuentas (SEG-15: siempre hay al menos un Administrador activo y nunca hay más de un Gerente activo, verificado bloqueando las filas involucradas durante la operación); admin de Django deshabilitado en producción (SEG-18); entrada «Cuentas» en el menú lateral del Administrador | — |
   | 06 | **06a y 06b hechas** (Mi perfil, «Mi perfil» y «Cambiar de cuenta» en el menú de cuenta, cambio voluntario de contraseña con el servicio de la tarea 03, y cuentas vinculadas: USR-VNC-CTA, SEG-09 y SEG-11) | — |
   | 07 | Foto de perfil (SEG-19) | Proveedor de almacenamiento decidido; permiso para Pillow y `django-storages` (D-20) |
   | 08 | Recuperar contraseña (USR-RCP-CTR, SEG-12) | Proveedor de correo decidido; en desarrollo, backend de consola |
   | 09 | Seguridad de producción: HTTPS, cookies seguras y HSTS (SEG-16); `DEBUG` apagado si falta la variable de entorno; evaluar reemplazar `static_v` por `ManifestStaticFilesStorage` de WhiteNoise en producción (D-29); tope de intentos de identificación para el inicio de sesión y `vincular_cuenta` juntos, que reemplazaría a SEG-05 y D-19 (ver «Temas abiertos» y D-32) | — |

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

## Temas abiertos

- **Prioridad.** Pasar las pruebas de concurrencia existentes al parámetro `primera` de `correr_a_la_vez`. El
  experimento del 14/11/2026 mostró que, con la ventana fija de 1,5 s, en una máquina lenta pueden pasar sin probar
  nada, y eso debilita la evidencia de SEG-15 de D-30 y D-32. Cuándo: la próxima tarea chica, antes de agregar más
  pruebas de concurrencia.
- Reparto final de apps entre los dos integrantes: D-23 fija cuentas en `core` y una app por módulo
  de negocio; faltan los nombres y quién toma cada una.
- Lista cerrada de los casos de uso del 80% y orden de implementación.
- Recuperar contraseña depende del correo, que solo funcionará en Render pago. Falta decidir el
  proveedor de correo (tarea 08).
- Proveedor del almacenamiento de objetos para la foto de perfil (tarea 07).
- Ingreso con Google: trabajo futuro, fuera de este bloque.
- Hacer configurables por `.env` el host, el puerto, el nombre y el usuario de la base local.
- Logo y nombre de la organización configurables: hoy el logo es un ícono fijo y el nombre sale de
  `NOMBRE_ORGANIZACION`; serán una imagen y un nombre configurables, en la configuración de la organización.
  Cuándo: sin fecha todavía.
- Integrar el logo de InfoPonia: favicon y marca en el inicio de sesión. Cuándo: cuando esté el logo definitivo.
- Campana y notificaciones del marco: se agregan cuando exista el primer aviso (por ejemplo, el resumen
  de pendientes del Gerente, D-14). El prototipo ya tiene el diseño (`notifPop`).
- Funciones de pruebas con el mismo nombre y distinto trabajo, que no se unificaron a propósito: `datos_validos`
  (`test_usr_alt_usr.py` arma los datos de un alta; `test_usr_mod_usr.py` toma los datos actuales de una cuenta) y
  `codigos` (`core/tests/concurrencia.py` devuelve todos los códigos de un error; `test_usr_cmb_ctr.py` recibe el
  campo y devuelve solo los de ese campo). Si se renombran, que sea sin cambiar lo que verifica ninguna prueba.
  Cuándo: opcional, sin fecha.
- Tope de intentos de identificación: SEG-05 y D-19 no lo tienen. El inicio de sesión y `vincular_cuenta` son el
  mismo oráculo de contraseñas, así que se evalúan juntos, por ejemplo con una espera creciente y no con el bloqueo
  de la cuenta (bloquearla dejaría sin acceso a quien tenga un email conocido). Necesita una decisión nueva que
  reemplace a D-19 y SEG-05, y un modelo o una caché para contar. Cuándo: tarea 09.
- Búsqueda de la lista de cuentas sin distinguir tildes, con `unaccent` de PostgreSQL. Cuándo: opcional, sin
  fecha.
- Ámbito por invernadero de SEG-13: se agrega en `core/acceso.py` cuando exista `Invernadero`.
- Render tiene `DJANGO_DEBUG=0` (verificado el 12/11/2026); en la tarea 09, `DEBUG` queda apagado por defecto en
  el código.
