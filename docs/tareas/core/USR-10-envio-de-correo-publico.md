# USR-10 · Envío de correo público de `core` (D-54)

Estado: hecha y verificada a mano (23/11/2026) | App: core | Rama: feature/usr-10-envio-de-correo-publico | Ronda: IoT (se hace después de «Producción 1»)

Depende de: — (no necesita nada de la ronda de producción; se puede hacer en cualquier momento antes de COM-02 y de IOT-04, que manda los correos del IoT; D-71)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es una tarea **chica**: una refactorización sin cambio de comportamiento.

## Casos de uso incluidos

No es un caso de uso: es una pieza de infraestructura (D-54) que dejan lista `core` para que otras apps envíen correo.

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| USR-RCP-CTR, USR-ALT-USR | Siguen funcionando igual (recuperación de contraseña e invitación usan el envío) | docs/casos_de_uso/usuarios.md | Solo para no romperlos |

## Leer

- Código: `core/servicios.py` (`_enviar_correo` y quienes la llaman), `core/tests/` (las pruebas de recuperación e invitación)
- Decisiones: D-14, D-33, D-35, D-54
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: ninguno
- Migraciones: ninguna
- Permitido fuera de la app: nada (toda la tarea es en `core`)
- Dependencias nuevas: ninguna
- Fuera de alcance: cambiar plantillas existentes; enviar correos en HTML; cola de envíos (si hiciera falta, es otra decisión)

## Pasos

1. **`core/correo.py`** con `enviar_correo(cuenta, asunto, plantilla, contexto) -> bool` y `correo_configurado() -> bool` (D-54, punto 1). El cuerpo es el de `_enviar_correo` actual, movido sin cambiarlo. Docstring: se llama **siempre fuera de una transacción** (D-14) y no registra el contenido. Pruebas: `test_correo.py` (sale y devuelve `True`; falla del servidor → `False` y un registro de error con el id de la cuenta y sin el cuerpo; `correo_configurado` sigue a `settings.CORREO_CONFIGURADO` en cada llamada).
2. **`_enviar_correo` delega** en la pública, sin cambiar su firma. Las pruebas de recuperación e invitación pasan sin tocarlas, salvo el nombre del logger en sus `assertLogs` (ver «Hecho cuando»).
3. **Documentar** en `docs/api/` (un párrafo en `notificaciones.md` o un archivo `correo.md`, el que corresponda) la función y la regla de uso.

## Hecho cuando

- Ninguna prueba existente de `core` cambió, salvo el nombre del logger en seis `assertLogs` (de `core.servicios` a `core.correo`, porque el error de envío sale ahora por el logger de `core/correo.py`), y todas pasan.
- Un llamador de otra app puede importar `core.correo.enviar_correo` (la prueba lo importa desde otra ruta).
- Comando de pruebas: python manage.py test core.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

No hace falta cargar datos con `cargar_datos_de_verificacion`: la base local ya tiene Administradores activos (la
recuperación funciona con ellos, D-34) y el alta crea la cuenta como parte de la prueba.

1. En `.env` local, con `DJANGO_DEBUG` encendido, poné `CORREO_CONSOLA=1` (D-33) y reiniciá `runserver`.
2. Sin sesión, en el inicio de sesión, abrí «¿Olvidaste tu contraseña?», escribí el email de un Administrador activo y
   enviá. Esperado: la pantalla «Revisá tu correo» y, en la terminal de `runserver`, el correo en texto plano que
   saluda por el nombre, nombra a la organización, trae el enlace `.../recuperar-contrasena/<uid>/<token>/` y dice
   que vence en una hora.
3. Iniciá sesión como Administrador o Gerente y dá de alta una cuenta nueva con la forma de acceso «Invitación» (la
   marcada por defecto), con un email inventado. Esperado: «Le enviamos una invitación a <email>. Vence en 7 días…» y,
   en la terminal, el correo con el enlace `.../invitacion/<uid>/<token>/` y el vencimiento en 7 días.
4. Abrí cada enlace impreso y comprobá que lleva a su pantalla (elegir contraseña).
5. Dejá `CORREO_CONSOLA` como lo tenías.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** Refactorización sin cambio de comportamiento (D-54):
- `core/correo.py` nuevo, con `enviar_correo(cuenta, asunto, plantilla, contexto) -> bool` (el cuerpo de la antigua
  `_enviar_correo`, movido sin cambiarlo) y `correo_configurado() -> bool` (lee `settings.CORREO_CONFIGURADO` en cada
  llamada, D-33).
- `_enviar_correo` de `core/servicios.py` conserva nombre y firma y delega en `correo.enviar_correo`. Salieron de
  `servicios.py` los imports que quedaron sin uso (`logging`, `send_mail`, `render_to_string`,
  `nombre_de_la_organizacion`) y su `logger`. Los tres usos directos de `settings.CORREO_CONFIGURADO` de
  `servicios.py` no se tocaron.
- Paso 3 (documentar la API en `docs/api/notificaciones.md`): propuesto como cambio de documentación, no aplicado.

**Lo que difiere de la documentación.** Los errores de envío ahora salen por el logger `core.correo` y no por
`core.servicios`. Por eso cambia el nombre del logger en seis `assertLogs` de pruebas existentes (`test_usr_mod_usr.py`,
`test_usr_rcp_ctr.py` y `test_usr_alt_usr.py`, dos en cada una): es lo único que se tocó de ellas. Aprobado por el
estudiante al encargar la tarea; el «Hecho cuando» y el paso 2 de esta tarea se corrigieron para decirlo.

**Pruebas.** `core/tests/test_correo.py`, 5 pruebas (envío y `True`, `nombre_organizacion` en el contexto, falla →
`False` y registro con el id sin el cuerpo ni el token, `correo_configurado` en cada llamada, y la delegación de
`_enviar_correo`). Escritas primero y vistas en rojo (`ModuleNotFoundError`), revisadas por el estudiante.
Comando de la tarea: `python manage.py test core.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`
→ 742 pruebas, OK. Concurrencia: `python manage.py test core --keepdb --tag concurrencia` → 16 pruebas, OK. Control: `maestros.tests.test_identidad_organizacion` (llama a `_enviar_correo`), 7 pruebas, OK.

**Decisiones.** Ninguna nueva. Sin modelos, migraciones ni dependencias; nada fuera de `core`.

**Datos cargados para la verificación.** Ninguno: no hizo falta (ver «Verificación a mano»).
