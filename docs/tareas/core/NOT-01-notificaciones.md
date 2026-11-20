# NOT-01 · Notificaciones y campana (D-42)

Estado: hecha, a la espera de la revisión a mano | App: core (toca servicios de `core` y de `maestros`) | Rama: feature/not-01-notificaciones | Ronda: Producción 1

Depende de: UI-01 (si no está hecha, frená: el marco y la identidad en `core/extensiones.py` los deja ella). MAE-02a y MAE-02b ya están mergeadas

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

No es un caso de uso: es una característica del sistema (D-38, D-42) que cierra postcondiciones de aviso de casos de uso ya
hechos. Los extractos con sus textos exactos:

| Código | Postcondición que se cierra | Extracto | Marcas |
|---|---|---|---|
| USR-ALT-USR | d: al alta de un Gerente, una única notificación al nuevo Gerente con la cantidad de pendientes | docs/casos_de_uso/usuarios.md | — |
| USR-BAJ-USR | c: al dar de baja al Gerente, la pantalla de la baja informa al Administrador cuántos pendientes quedan | docs/casos_de_uso/usuarios.md | No es una notificación: es un texto de la pantalla |
| PROD-ALT-INV | e: cada persona asignada recibe una notificación de que quedó a cargo del invernadero | docs/casos_de_uso/maestros/invernaderos.md | — |
| PROD-MOD-INV | c: cada persona que queda a cargo (nueva) recibe la notificación, con lo que recibe (regla 2) | docs/casos_de_uso/maestros/invernaderos.md | — |

## Leer

- Decisiones: D-14, D-25, D-36, D-38, D-41, D-42, D-47, D-48 (solo la parte de `core/extensiones.py`)
- API: docs/api/notificaciones.md (es el contrato: implementalo tal cual)
- Casos de uso: los de la tabla, solo las postcondiciones indicadas y las reglas que las nombran (USR-ALT-USR regla de rol
  Gerente; USR-BAJ-USR reglas 3 y 4; PROD-MOD-INV regla 2)
- Modelo: docs/modelo/maestros.md — Alerta (solo atributos y reglas; la campana usa `Alerta.objects.para(usuario)`)
- Patrones: docs/patrones/auditoria.md (para no auditar las notificaciones)
- Pantallas: docs/prototipos/produccion/ — `shell`, `alertas`, `myNotif`; docs/prototipos/cuentas_y_seguridad.html — `notifPop`
  (solo guía visual)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código: core/servicios.py (`alta_usuario`, `baja_usuario`), maestros/servicios/invernaderos.py (`alta_invernadero`,
  `modificar_invernadero`, `_aviso_de_personal`), maestros/extensiones.py (`contar_traspaso`)

## Límites

- Crea modelos: `core.Notificacion` → revisá docs/disparadores.md («Cuando exista la primera notificación o alerta»)
- Migraciones: solo nuevas, en `core` (una de esquema para `Notificacion`). Ninguna en `maestros`
- Archivos nuevos: `core/notificaciones.py`, `core/templates/core/_campana.html` (y sus fragmentos), `core/tests/test_notificaciones.py`
- Permitido fuera de `core`: `maestros/apps.py` (registrar la fuente de alertas y el contador de pendientes),
  `maestros/servicios/invernaderos.py` (las llamadas a `notificar_a_varios`), `maestros/tests/test_prod_alt_inv.py` y
  `test_prod_mod_inv.py` (pruebas de las postcondiciones e y c), `core/extensiones.py` (existe desde MAE-02b y UI-01 le sumó la identidad: se le agregan
  `registrar_fuente_de_alertas`, `ItemDeAlerta` y `registrar_contador_de_pendientes`)
- Dependencias nuevas: ninguna
- Fuera de alcance: marcar una alerta como leída (ya existe: `abrir_alerta`, MAE-02b), pantalla de alertas (MAE-02c), historial completo de
  notificaciones, envío por correo, notificaciones de las apps de producción (las escribe cada tarea con esta API), logo

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** `Notificacion` (D-42) con índice por `(destinatario, fecha_hora)` y `Meta.ordering` de la más
   reciente a la más antigua. Pruebas: `core/tests/test_notificaciones.py` — `NotificacionModeloTests` (valores por defecto,
   orden, `leida` falsa al crear).
2. **API.** `notificar`, `notificar_al_gerente`, `notificar_a_varios`, `de_la_cuenta`, `marcar_vistas` y `pendientes_del_gerente`,
   con las reglas de `docs/api/notificaciones.md`: sin Gerente activo no falla, sin repetir cuentas, sin `None`, sin la cuenta
   excluida, título y detalle con contenido y dentro del largo (`ValueError`), `marcar_vistas` ignora las ajenas. Pruebas:
   `NotificacionApiTests`, incluido que dentro de `transaction.atomic()` que falla no queda nada.
3. **Puntos de extensión.** En `core/extensiones.py`: `registrar_fuente_de_alertas`, `ItemDeAlerta`, `alertas_para(usuario)` (junta
   las fuentes, ordena por severidad crítica, advertencia, informativa, sin perder el orden de cada una) y
   `registrar_contador_de_pendientes`. Pruebas: `ExtensionesCampanaTests` con registrantes falsos.
4. **Campana.** En el marco (el lugar que dejó UI-01): botón con punto rojo (alerta activa no leída o notificación sin leer) y
   el panel de dos pestañas, con el aspecto del prototipo (D-47). Con HTMX: abrir trae el panel (`GET core:campana`) y cerrarlo
   hace `POST core:campana_vista` con los ids de las notificaciones mostradas, que quedan leídas. Sin JavaScript, el botón es un
   enlace a `core:campana` como página completa. Para los roles de campo (celular) el botón mide 44 px. Pruebas:
   `CampanaVistaTests` (solo ve las suyas; el orden; el contador; el punto; que cerrar marca leídas solo las mostradas; que otro
   usuario no puede marcar las ajenas; sin sesión redirige al inicio de sesión).
5. **Avisos de `core`.** USR-ALT-USR d: dentro de `alta_usuario`, si el rol es Gerente, una notificación al nuevo Gerente con el
   total y el detalle de `pendientes_del_gerente()` («No tiene pendientes» si es 0). USR-BAJ-USR c: la pantalla de la baja del
   Gerente muestra el total y el detalle. **La ventana de baja ya existe** (MAE-02b, D-43: `core/templates/core/usuarios/_ventana_confirmar.html`
   y `asignaciones_de_cuenta` de `core/extensiones.py`): leé D-43 y agregá el texto de pendientes ahí, sin duplicar la ventana ni cambiar
   lo que ya lista. Pruebas: se agregan a los archivos existentes de esos casos de uso
   (`test_post_d_…` y `test_post_c_…`); sin Gerente activo la notificación se omite y el alta no falla (D-14).
6. **Fuentes de `maestros`.** En `MaestrosConfig.ready()` registrar la fuente de alertas (las activas de
   `Alerta.objects.para(usuario)`, con severidad desde el tipo registrado, `url` a la ficha del invernadero, `leida` según
   `estado_lectura_alerta`) y el contador de pendientes del Gerente (alertas activas con `para_gerente=True`). Pruebas:
   `maestros/tests/test_campana_alertas.py`.
7. **Avisos de invernadero.** PROD-ALT-INV e y PROD-MOD-INV c: en las transacciones de `alta_invernadero` y
   `modificar_invernadero`, `notificar_a_varios` a cada persona asignada (en la modificación, solo a las que **quedan a cargo**
   en este cambio), con el texto de D-42 y, en la modificación, lo que recibe (`contar_traspaso`, ya armado por
   `_aviso_de_personal`). Nunca al actor. Pruebas: `test_post_e_…` y `test_post_c_…` en los archivos de esos casos de uso;
   incluir que una modificación sin cambios no notifica (D-28) y que la persona saliente no recibe nada.
8. **Cierre de documentación.** Actualizá los comentarios y docstrings que dicen «las notificaciones no existen todavía» o
   «tarea aparte en core, D-42» (en `core/servicios.py` y `maestros/servicios/invernaderos.py`). Proponé, sin aplicarlos (M3), el cierre de la sección
   «Cuando exista la primera notificación o alerta» de `docs/disparadores.md` y los cambios de las filas de `docs/tareas/README.md` y de
   `docs/tareas/ronda_produccion_1.md`.

Si el tiempo apremia, lo último que se recorta es el paso 7 (se anota como disparador); los pasos 1 a 6 no se recortan porque
MAE-03 y PRD-01 usan la API.

## Hecho cuando

- La campana funciona para todos los roles, con y sin JavaScript, y marca como leídas solo las notificaciones mostradas al cerrar.
- Las cuatro postcondiciones de la tabla están implementadas y probadas; ninguna se audita.
- `docs/api/notificaciones.md` coincide con el código (si hubo que cambiar algo, se cambió el documento y se avisó).
- Pruebas: `core/tests/test_notificaciones.py` y `maestros/tests/test_campana_alertas.py`, más las de las postcondiciones.
- Comando de pruebas (suites completas de core y maestros, porque se tocan servicios de ambos):
  python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test core maestros --keepdb --tag concurrencia

## Verificación a mano

Hay una migración nueva: `python manage.py migrate`. Después, con el entorno virtual activo: `python manage.py runserver`. Cuentas:
Gerente, Administrador, Agrónomo y Capataz. No hay navegador en la sesión de Claude Code: **el JavaScript de la campana (abrir,
cerrar, pestañas, marcar como leídas) se probó solo con pruebas de las vistas y con `node --check`; lo recorrés vos.**

1. Con el Gerente, dar de alta un invernadero con Agrónomo y Capataz. Con cada una de esas cuentas: la campana tiene punto rojo y la
   pestaña dice «Notificaciones (1 sin leer)»; el título es «Quedó a cargo de <invernadero>» y el detalle, «El Gerente le asignó el rol
   de Agrónomo.» (o Capataz). Abrir la pestaña «Notificaciones» y cerrar el panel (clic en la campana, clic afuera o Esc): la
   notificación queda leída y, al volver a mirar, el punto desapareció.
2. Abrir el panel con la pestaña «Alertas» a la vista y cerrarlo: las notificaciones **no** quedan leídas (solo se marcan si se vio
   su pestaña). Cambiar de pestaña no recarga la página.
3. «Modificar» ese invernadero y cambiar el Agrónomo: el nuevo recibe el aviso con lo que recibe («Recibe: alertas activas: N.» si
   tenía alertas, o «No recibe nada pendiente.»); el anterior no recibe nada. Guardar sin cambiar nada, o cambiando solo el nombre,
   no genera avisos.
4. Con el Administrador, abrir la baja del Gerente: la ventana muestra «Pendientes del Gerente: N (Alertas activas para el Gerente:
   N)…» o «No tiene pendientes.». Dar de baja al Gerente y dar de alta uno nuevo: el nuevo tiene una notificación «Pendientes que
   esperan al Gerente» con el mismo total.
5. Con un invernadero sin Capataz, el Gerente ve en la pestaña «Alertas» la de «Invernadero sin Capataz activo», con el nombre del
   invernadero, su severidad (advertencia) y un enlace a la ficha. Mientras la alerta siga sin leer, el punto rojo del Gerente
   sigue prendido: abrir la ficha no la marca como leída (eso lo hace `abrir_alerta` desde la pantalla de alertas, MAE-02c). El
   Administrador no tiene campana.
6. Sin JavaScript (desactivalo en las herramientas del navegador): el botón de la campana abre la página completa «Alertas y
   notificaciones» con las dos pestañas (son enlaces); «Cerrar» marca las notificaciones solo si se estaba viendo esa pestaña y
   vuelve a la pantalla de donde se vino.
7. A 375 px el panel entra en la pantalla (con el Gerente) y, con el Capataz (marco de celular), se abre como hoja inferior y el
   botón de la campana mide al menos 44 px.

## Cierre

**Qué se hizo.**
- **Modelo y API.** `core.Notificacion` (migración `0011_notificacion`, solo esquema) y `core/notificaciones.py` con `notificar`,
  `notificar_al_gerente`, `notificar_a_varios`, `de_la_cuenta`, `marcar_vistas`, `pendientes_del_gerente` y `estado_de_la_campana`.
  Ninguna se audita.
- **Puntos de extensión.** `ItemDeAlerta`, `registrar_fuente_de_alertas`, `alertas_para`, `registrar_contador_de_pendientes` y
  `contadores_de_pendientes` en `core/extensiones.py`.
- **Campana.** Botón en el marco (todos los roles menos el Administrador) con el punto rojo, panel con dos pestañas
  (`GET core:campana`) y `POST core:campana_vista` al cerrar. Sin JavaScript, el botón lleva a la página completa. Vistas, rutas,
  procesador de contexto, cuatro plantillas (`_campana`, `_campana_panel`, `_campana_contenido`, `campana`), CSS y JS.
- **Avisos de `core`.** `alta_usuario` avisa al Gerente nuevo (USR-ALT-USR d); la ventana de baja del Gerente muestra el total y el
  detalle de pendientes (USR-BAJ-USR c), sin duplicar la ventana ni cambiar lo que lista.
- **`maestros`.** `items_de_campana` y `pendientes_de_alertas` (registradas en `MaestrosConfig.ready()`), y los avisos de
  `alta_invernadero` (PROD-ALT-INV e) y `modificar_invernadero` (PROD-MOD-INV c).
- **Paso 8.** Se actualizaron los comentarios y docstrings que decían que las notificaciones no existían.

**Pruebas.**
- `python manage.py test core maestros --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`: 1100 pruebas, OK
  (antes de la tarea, 1030).
- `python manage.py test core maestros --keepdb --tag concurrencia`: 34 pruebas, OK.
- `python manage.py test core maestros --keepdb --tag migracion`: 1 prueba, OK.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- Nuevas: 79 en `core/tests/test_notificaciones.py` (modelo, API, extensiones y campana), 26 en
  `maestros/tests/test_campana_alertas.py`, 20 de las postcondiciones de `core` (11 `test_post_d_…` y 9 de
  `UsrBajUsrPendientesTests`) y 24 de las de invernadero (9 `test_post_e_…` y 15 `test_post_c_…`/`test_d28_…`). Se escribieron antes y
  fallaron en los pasos 2, 5 y 7 (con pausa para tu revisión). Ninguna prueba existente se modificó.
- La prueba de «dentro de `transaction.atomic()` que falla no queda nada» usa `TestCase` (punto de guardado), no
  `TransactionTestCase`: no hizo falta el mixin de `datos_de_migracion.md`.

**Decisiones y diferencias con la documentación.**
- **Textos (L9).** D-42 dice «con el texto de D-42» pero no trae ninguno. Se usaron los que aprobaste: título «Quedó a cargo de
  <invernadero>»; detalle «El Gerente le asignó el rol de <rol>.» (en la modificación, más «Recibe: <descripción>: <cantidad>, …» o
  «No recibe nada pendiente.»); «Pendientes que esperan al Gerente» / «Tiene N pendiente(s). <descripción>: <cantidad>.» o «No tiene
  pendientes.»; en la ventana de baja, «Pendientes del Gerente: N (…). Quedan esperando hasta el alta de otro Gerente; la baja no se
  bloquea por ellos.». Difiere del ejemplo de `docs/api/notificaciones.md` («lo asignó como Agrónomo») y conviene escribirlos en D-42 y
  en la API.
- **D-14 en `alta_usuario`.** El destinatario del aviso es el Gerente recién creado, que ya es el Gerente activo (D-09). El caso «sin
  Gerente activo, la notificación se omite» que menciona el paso 5 no puede darse ahí: solo se da en `notificar_al_gerente`
  (probado en la API). `alta_usuario` usa `notificar`, no `notificar_al_gerente`.
- **Sin campana para el Administrador.** D-42 dice «todos los roles», pero `docs/casos_de_uso/usuarios.md` define «todos los roles»
  como los seis operativos y dice que el Administrador no tiene campana. Se siguió el caso de uso: sin botón y `core:campana` da 403.
- **Severidad (MD-109) con respaldo en `items_de_campana`.** La severidad sale del tipo registrado; si el código ya no está registrado,
  se usa la que se guardó con la alerta (MD-109), en vez de lanzar `ValueError` y romper la campana de todas las pantallas.
- **Punto rojo y «vistas».** El punto rojo sigue a D-42 (alerta activa no leída o notificación sin leer), no al prototipo (que lo
  muestra con cualquier alerta). Las notificaciones se marcan al cerrar solo si se vio la pestaña «Notificaciones» durante la
  apertura (el prototipo, solo si esa pestaña estaba a la vista al cerrar); y solo las 30 mostradas.
- **Lo que recibe la persona (paso 7).** `_aviso_de_personal` se calcula antes del traspaso (después ya no queda nada en la
  saliente) y solo si hay un rol entrante no nulo. Cambió el comportamiento: con el cambio confirmado, `contar_traspaso` ahora se
  llama también, una vez por rol entrante. Un cambio de nombre o de dirección, o quitar a alguien sin reemplazo, no lo llama.
- **Una notificación por rol.** `notificar_a_varios` se llama una vez por persona entrante, porque cada rol lleva su texto.
- **Validación del texto.** `notificar_al_gerente` y `notificar_a_varios` validan el título y el detalle aunque no haya destinatarios:
  un texto vacío es un error de uso. `notificar` y las demás rechazan también el texto en blanco (solo espacios) y guardan el texto
  recortado.
- **Estilo de la campana.** Se sumaron a la hoja las clases `.ptabs a`, `.sev-critica|advertencia|informativa` (el azul de la
  informativa es el de `.status-info`, el v2 no define `--status-info`) y `.plist .acc-item .t span` con `white-space: normal` para
  que el detalle de una notificación pueda tener varias líneas (en los menús sigue cortándose). Las alertas no leídas llevan
  `.unread`, que el prototipo no usa para las alertas.
- **Alertas y lectura.** El enlace de una alerta en la campana lleva a la ficha del invernadero y no llama a `abrir_alerta`: el punto
  rojo por alertas no leídas se apaga recién cuando MAE-02c las abra por su pantalla. Marcar una alerta como leída es de MAE-02b y
  está fuera del alcance de NOT-01.
- **Archivo de pruebas no listado.** `maestros/tests/test_campana_alertas.py` no figura en «Límites», pero lo piden el paso 6 y
  «Hecho cuando».
- **Fuera de lo permitido.** El docstring de `AlertaQuerySet.no_leidas` en `maestros/models.py` todavía dice «tarea de
  notificaciones»; no se tocó porque `maestros/models.py` no está en «Permitido fuera de la app» (queda para `temas_abiertos.md`).
- **JavaScript sin probar en navegador.** Solo se verificó la sintaxis con `node --check` y el comportamiento servidor con pruebas.
- **Base de pruebas.** Después de la migración nueva, con `--keepdb --parallel` los clones no la tenían: se recreó la base una vez
  con `--noinput` (`pruebas.md`).
