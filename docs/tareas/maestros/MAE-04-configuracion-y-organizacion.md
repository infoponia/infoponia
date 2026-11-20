# MAE-04 · Configuración operativa y perfil de la organización (sin logo)

Estado: pendiente | App: maestros | Rama: feature/mae-04-configuracion | Ronda: Producción 1

Depende de: UI-01 (estilo y la identidad de la organización en `core/extensiones.py`). Si no está hecha, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| ADM-MOD-CFG | Modificar Configuración Operativa | docs/casos_de_uso/maestros/configuracion.md | Incluye el parámetro «vigencia del enlace de decisión ante un faltante», que el prototipo no muestra |
| ADM-MOD-ORG | Modificar Perfil de la Organización | docs/casos_de_uso/maestros/configuracion.md | Sin logo (D-45): el campo no se crea |

## Leer

- Casos de uso: el extracto de la tabla, completo, **incluida la sección «Cómo se aplica en la ronda»**
- Modelo: docs/modelo/maestros.md — PerfilOrganizacion y ConfiguracionOperativa
- Decisiones: D-05, D-21, D-25, D-28, D-36, D-37, D-44, D-45, D-47, D-48
- Patrones: docs/patrones/datos_de_migracion.md (incluida «Singletons y catálogos fijos»), docs/patrones/auditoria.md,
  docs/patrones/abm.md (solo «Pantalla de un registro único»), docs/patrones/bloqueos.md
- Pantallas: docs/prototipos/produccion/ — `VIEWS.config`, `CFG`, `cuitOk`, `orgErr`, `cfgErr`, `aplicarMarca` (solo guía visual;
  lo que difiera de los CU lo decide el CU, L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: core/extensiones.py (existe desde MAE-02b; UI-01 le sumó la identidad) y core/identidad.py (lo creó UI-01), core/context_processors.py,
  maestros/validadores.py (reutilizá el validador de teléfono de D-21 si existe en `core/validadores.py`), core/menu.py

## Límites

- Crea modelos: `ConfiguracionOperativa`, `PerfilOrganizacion` → revisá docs/disparadores.md («Cuando exista PerfilOrganizacion»)
- Migraciones: solo nuevas, en `maestros`: una de esquema y una de datos (`cargar_configuracion_y_perfil`). Con una de `core` si
  se agregan acciones de auditoría (choices)
- Permitido fuera de la app: `core/models.py` (solo `Accion`, `ETIQUETAS` y `ACCIONES_DE_NEGOCIO`: `modificacion_configuracion`
  y `modificacion_perfil`), su migración, `core/menu.py` (entrada «Configuración» del Gerente) y los textos de cierre de
  `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md` (M3)
- Dependencias nuevas: ninguna
- Fuera de alcance: logo; los parámetros de IoT (MD-112); usar los parámetros en otras tareas (cada tarea los lee con
  `maestros.servicios.configuracion.obtener()`); validación de contraste del color; asientos o documentos que muestren el perfil

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos y migraciones.** Los dos singletons de la ficha, con `singleton` único y `CheckConstraint`, los dominios como
   restricciones de la base (por ejemplo `porc_merma_maxima` entre 1 y 100) y los valores iniciales como `default` del modelo. La
   migración de datos crea cada fila (el nombre del perfil sale de `settings.NOMBRE_ORGANIZACION`, solo al crear). En
   `fabricas.py`, `asegurar_datos_de_maestros()` ya la sirve (la dejó MAE-03; si MAE-03 no está mergeada, creala con el mismo
   esquema). Pruebas: `maestros/tests/test_singletons_modelo.py` (una sola fila, valores iniciales, la migración sobre tablas
   vacías, y que los valores de la migración coinciden con los `default` del modelo).
2. **Servicios.** `maestros/servicios/configuracion.py` (`obtener`, `modificar_configuracion`) y `maestros/servicios/perfil.py`
   (`obtener`, `modificar_perfil`, `identidad`). `obtener` crea la fila con los valores iniciales si faltara (red de seguridad,
   ver el patrón). Cada `modificar_*` es una función en `transaction.atomic()`: exige Gerente activo (`PermissionDenied` si no),
   bloquea la fila (`FOR NO KEY UPDATE`), la relee, valida **todo o nada** y devuelve los errores por campo (`ValidationError`
   con un error por campo, todos juntos), calcula lo que cambió contra lo leído después de bloquear, no escribe ni audita si
   nada cambió (D-28) y audita con antes y después de cada parámetro (D-36). Reglas de la configuración: dominios, regla 4
   (la anticipación de cosecha del suministro no supera la pre-reserva) como error del campo de la anticipación, y la regla 5
   (horizonte menor que la pre-reserva) como **advertencia** que se devuelve sin bloquear. Reglas del perfil: nombre
   obligatorio y recortado, CUIT por formato y dígito verificador (con o sin guiones; se guarda sin guiones), teléfono con el
   formato de D-21, email por formato, colores `#RRGGBB` cargados en orden (el 2.º no sin el 1.º, etc.; se guardan en
   mayúsculas o como vinieron, uniforme). Pruebas: `test_adm_mod_cfg.py` y `test_adm_mod_org.py` (una por regla y por
   postcondición; nombrar con el número de regla), incluida la concurrencia de dos Gerentes con etiqueta `concurrencia`.
3. **Identidad de la organización (D-48).** En `MaestrosConfig.ready()`, registrar con
   `core.extensiones.registrar_identidad_de_la_organizacion` una función que devuelve `Identidad(nombre, color_principal)`
   desde el perfil (`None` si no hay fila o si el nombre está vacío). Pruebas: `maestros/tests/test_identidad_organizacion.py`
   (cambiar el nombre cambia `nombre_organizacion` del contexto y el nombre en un correo de `core`; un color válido escribe
   las tres variables; sin colores, no escribe nada; con `NOMBRE_ORGANIZACION` distinto, el perfil gana).
4. **Pantalla.** «Configuración» en el menú del Gerente (entrada nueva, ícono `gear`: sumalo a `iconos.py` si falta), con las
   dos pestañas del prototipo: «Parámetros operativos» (cinco grupos, uno por tarjeta, con el parámetro de faltante agregado a
   «Comercial») y «Organización» (datos y colores; **sin el campo del logo**). Cada pestaña se guarda por separado, con su
   botón «Guardar cambios» y los errores por campo (HTMX con respaldo sin JavaScript); la advertencia del horizonte se muestra
   junto al formulario; las vistas exigen Gerente (otros roles: 403; sin sesión: inicio de sesión). Las vistas de lectura no
   se auditan. Pruebas: `maestros/tests/test_configuracion_vistas.py` (permisos, errores por campo, todo o nada, mensaje de
   guardado, la entrada del menú solo para el Gerente y el Administrador no la ve).
5. **Cierre de documentación.** Cerrar «Cuando exista PerfilOrganizacion» en `docs/disparadores.md` (menos el logo, que queda
   como disparador), agregar a `docs/temas_abiertos.md` el contraste del color principal, y marcar MAE-04 en
   `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md`.

Si el tiempo apremia, lo último que se recorta es la validación de colores en orden (se anota); los dominios y el todo o nada
no se recortan.

## Hecho cuando

- Los dos casos de uso están implementados con una prueba por regla y por postcondición y con sus pruebas de vista.
- El nombre del perfil aparece en el encabezado, en los correos y en las pantallas sin sesión; sin perfil se usa
  `NOMBRE_ORGANIZACION`.
- La pantalla tiene los trece parámetros de la ficha, incluido el de faltante, y ninguno del logo.
- Comando de pruebas:
  python manage.py test maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test maestros --keepdb --tag concurrencia
  python manage.py test maestros --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay migraciones nuevas: `python manage.py migrate`. Cuentas: Gerente, Agrónomo, Administrador.

1. `migrate` aplica esquema y datos de `maestros`. En `/admin/` hay una sola fila de cada singleton con los valores iniciales
   de la ficha.
2. El Gerente ve «Configuración» en el menú; el Agrónomo, el Capataz y el Administrador no; la URL les da 403.
3. «Parámetros operativos»: vaciar un campo, poner 0 en merma (mínimo 1), 101 (máximo 100), una anticipación del suministro mayor
   que la pre-reserva: cada error sale en su campo y no se guarda ninguno (todo o nada). Poner el horizonte en 10 con la
   pre-reserva en 14: advertencia, y se puede guardar.
4. Guardar sin cambiar nada: no hay registro nuevo en «Auditoría». Cambiar dos valores: un registro con el antes y el después
   de cada uno.
5. «Organización»: nombre vacío da error; CUIT inválido (cambiando un dígito) da error y uno válido con guiones se acepta;
   email sin arroba da error; colores en formato `rojo` dan error; cargar el color 2 sin el 1 da error.
6. Cargar color 1 `#2E7D32`: botones, enlaces y selecciones cambian en todo el sistema desde la página siguiente. Borrarlo: vuelve
   la paleta del sistema.
7. Cambiar el nombre a «Vivero Los Álamos»: lo muestran el encabezado, la pantalla de inicio de sesión (en otra ventana) y un
   correo de invitación o de recuperación (en la consola o en el cuerpo del correo, según el entorno).
8. Dos Gerentes (dos sesiones; si no hay dos, la prueba de concurrencia lo cubre): gana el último y no hay error 500.
9. Sin JavaScript, los pasos 3 a 5 funcionan igual.
10. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
