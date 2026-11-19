---
paths:
  - "**/tests/**"
---

# Pruebas

Copiado sin cambios de la sección «Tests» de `CLAUDE.md` (versión del 17/11/2026, PR #26). Se carga sola al abrir un
archivo de `tests/`; igual leela antes de escribir o de correr pruebas (regla L3 de `CLAUDE.md`), porque al crear el
primer archivo de pruebas de una app nueva todavía no abriste ninguno.

Cada tarea trae su «Comando de pruebas» en «Hecho cuando»: usá ese.

Las pruebas se escriben en `<app>/tests/` y se acumulan: el CI corre todas en cada PR.

- Unidad: una prueba por regla de negocio, extensión y postcondición relevante del caso de uso.
  Son obligatorias, como mínimo, en reglas con dinero, stock o alcance por usuario.
- Integración: una prueba por flujo principal de cada caso de uso (vista con el cliente de
  prueba de Django). No escribas pruebas de navegador.
- Orden en servicios: primero escribí todas las pruebas de las reglas del caso de uso, corrélas y
  mostrá que fallan; esperá que el estudiante las revise; después implementá el servicio.
  En vistas y en pantallas sin reglas de negocio, las pruebas van después.
- Nunca borres ni debilites una prueba existente para que pase. Si una regla cambió, avisá y
  proponé el cambio de la prueba.
- Cada prueba arma sus propios datos y no depende de otra.
- Forma de correr las pruebas en local: solo las de los módulos que tocás, siempre con `--keepdb` y
  `--parallel` (`python manage.py test core.tests.test_usuario --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`).
  No corras la suite completa local al terminar la tarea: la corre el CI en el PR.
- Las clases de pruebas de concurrencia (dos hilos, `TransactionTestCase`) llevan `@tag("concurrencia")`
  (`from django.test import tag`). En local se excluyen con `--exclude-tag concurrencia`, salvo que la tarea
  toque servicios con bloqueos (`select_for_update`) o concurrencia: ahí se corren las del módulo tocado.
- Las pruebas de migraciones que desarman y vuelven a armar el esquema de la base de pruebas (`TransactionTestCase` con
  `MigrationExecutor`) llevan `@tag("migracion")`. En local se excluyen junto con las de concurrencia
  (`--exclude-tag concurrencia --exclude-tag migracion`), salvo que la tarea toque una migración de datos: ahí se
  corren aparte, una vez al final (`--tag migracion`, sin `--parallel`), y se muestra el resultado.
- Con `manage.py test`, `config/settings.py` usa `MD5PasswordHasher` como único algoritmo de contraseñas (se
  detecta con `sys.argv`; `runserver`, gunicorn y los demás comandos no lo cambian), porque el PBKDF2 por defecto
  hace lento cada `create_user`. Las pruebas no deben depender del algoritmo (no busques «pbkdf2»: compará con el
  prefijo del hash real). Si se cambia el algoritmo de producción, hay que probarlo a mano: las pruebas no lo ejercitan.
- Con `manage.py test`, `CORREO_CONFIGURADO` arranca en `False` (aunque el `.env` tenga `CORREO_CONSOLA=1` o
  credenciales), para que las pruebas den lo mismo en cada máquina y en el CI. Las pruebas que necesitan el correo lo
  encienden con `@override_settings(CORREO_CONFIGURADO=True)`.
- Después de una migración nueva, con `--keepdb --parallel` los clones de la base de pruebas no la reciben y falla con un
  error de columna inexistente. Si aparece, corré una vez sin `--keepdb` y con `--noinput` para recrear la base
  (`python manage.py test core.tests.test_usuario --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion`) y después volvé a
  `--keepdb`.
- Si tus pruebas usan datos cargados por una migración (Georef, plan de cuentas, categorías del sistema), leé
  `docs/patrones/datos_de_migracion.md`: con `--keepdb`, un `TransactionTestCase` de otra app los vacía, y sin `ANALYZE`
  las consultas se vuelven muy lentas. Las clases que los usan heredan del mixin de ese patrón.
- Nada de experimentos ni de matrices de bloqueos desactivados (correr las pruebas de concurrencia con los
  bloqueos quitados o cambiados) salvo que la tarea toque bloqueos o concurrencia, o que el estudiante lo pida.
- Para reproducir en local un fallo del CI (producción, con `DEBUG` apagado), o si el estudiante pide la
  suite completa: poné `DJANGO_DEBUG=0` y una
  `DJANGO_SECRET_KEY` inventada en la misma línea. Sin la clave, con `DEBUG` apagado la configuración queda sin
  `SECRET_KEY` y fallan casi todas las pruebas. No leas `.env` ni uses la clave real.
  En PowerShell: `$env:DJANGO_DEBUG="0"; $env:DJANGO_SECRET_KEY="clave-falsa-solo-para-pruebas"; python manage.py test`
  (después, `Remove-Item Env:DJANGO_DEBUG, Env:DJANGO_SECRET_KEY` para volver al modo normal).
  Con la herramienta Bash: `DJANGO_DEBUG=0 DJANGO_SECRET_KEY=clave-falsa-solo-para-pruebas .venv/Scripts/python.exe manage.py test`.
  Si la base `test_infoponia` quedó de una corrida interrumpida, agregá `--noinput` para recrearla.

## Nombres

Los nombres concretos de esta sección son ejemplos del formato, no archivos ni pruebas que haya
que crear.

- Archivo por caso de uso: `<app>/tests/test_<codigo_cu>.py`.
  Ejemplo: `compras/tests/test_cmp_apr_odc.py`.
- Clases: `<CodigoCu>ServicioTests` (unidad) y `<CodigoCu>VistaTests` (integración).
  Ejemplo: `CmpAprOdcServicioTests`.
- Prueba: `test_<origen>_<que_espera>`, en snake_case, sin tildes ni ñ, con el resultado en presente.
  Formatos según el origen, con un ejemplo cada uno:
  - Regla del CU, `test_regla_<nombre_regla>_<que_espera>`.
    Ejemplo: `test_regla_orden_resoluble_rechaza_orden_ya_aprobada`
  - Regla del modelo, `test_regla_<seccion>_<numero>_<que_espera>`.
    Ejemplo: `test_regla_8_16_24_orden_resuelta_no_vuelve_a_resolverse`
  - Extensión, `test_ext_<id>_<que_espera>`.
    Ejemplo: `test_ext_8b_destino_inactivo_no_registra_cambios`
  - Postcondición, `test_post_<letra>_<que_espera>`.
    Ejemplo: `test_post_d_sube_cantidad_en_transito`
  - Flujo principal, `test_flujo_principal_<que_espera>`.
    Ejemplo: `test_flujo_principal_aprueba_orden`
  - Decisión sin caso de uso, `test_d<numero>_<que_espera>`.
    Ejemplo: `test_d09_un_solo_gerente_activo`
- Cada prueba tiene un docstring con la fuente exacta (caso de uso y regla, o decisión).
