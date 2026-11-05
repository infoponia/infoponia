# InfoPonia — Instrucciones para Claude Code

Mini-ERP en Django para organizaciones que producen y comercializan hidroponia.
Trabajo universitario (metodología UP). Equipo de dos estudiantes con experiencia
básica en Django: explicá lo que hacés y por qué, en español con voseo.

## Comportamiento

- Antes de editar, proponé un plan y esperá aprobación.
- Ante cualquier ambigüedad o contradicción con la documentación: detenete y preguntá. No elijas en silencio.
- Cada regla de negocio implementada cita su fuente en el docstring o en un comentario
  (por ejemplo: `# Regla 9 de 8.13 — modelo de dominio, ronda 20`).
- No agregues dependencias, no modifiques migraciones ya mergeadas en main y no cambies
  modelos ya mergeados sin permiso explícito.
- No hagas commits, push ni operaciones de Git que modifiquen el historial. Los commits los hacen los estudiantes.
- No explores el repo por tu cuenta: trabajá sobre los archivos que se te indiquen.
  Nunca listes ni leas `.venv/`.
- Verificá versiones y comandos actuales antes de recomendarlos; no recomiendes de memoria.

## Fuentes de verdad (de mayor a menor peso)

1. `docs/decisiones.md`: bitácora de decisiones tomadas por el equipo.
2. Modelo de dominio (ronda 20) y glosario.
3. Casos de uso extendidos y pendientes.
4. Casos de uso originales (desactualizados; solo orientativos).
5. Prototipo: solo guía visual.

Estado actual y próximos pasos: `docs/estado.md`. Leelo al empezar cada sesión.

## Stack

- Python 3.11.x, Django 5.2 LTS, PostgreSQL 17 (local en el puerto 5433).
- psycopg 3, gunicorn, whitenoise, dj-database-url, python-dotenv.
- Frontend: plantillas de Django con HTMX. CSS propio, sin Tailwind.
- Despliegue: Render (servidor) y Neon (base de producción). Render ejecuta `migrate` en cada despliegue.

## Arquitectura

- Monolito Django (MTV) con capa de servicios.
- Cada caso de uso es una función de servicio en `<app>/servicios.py`, dentro de `transaction.atomic()`.
  Sus pre y postcondiciones salen del caso de uso extendido y de las reglas del modelo de dominio.
- Las vistas solo orquestan: validan la entrada, llaman al servicio y renderizan.
- El alcance por usuario se aplica con un único manager o queryset por modelo.
- Modelo de usuario: ver D-01 a D-04 en `docs/decisiones.md`.

## Convenciones

- Nombres en español según el glosario, en snake_case, conservando el sufijo de la clase
  (`nombre_invernadero`). Las correcciones de errores de tipeo del diagrama se registran en `docs/decisiones.md`.
- Clave primaria: `id` automático de Django, equivalente a `idX` del diagrama.
- Dinero siempre con `Decimal` y `DecimalField`. Nunca `float`.
- `select_for_update()` en reservas de stock y en toda operación concurrente sobre cantidades.
- Cada archivo empieza con un comentario que explica su propósito.
- Docstring en cada clase y función; comentarios en la lógica no evidente.
- Patrones de diseño solo si están identificados y justificados en un comentario.

## Tests

- Obligatorios en reglas con dinero, stock o alcance por usuario.
- Un test por regla numerada, nombrado por la regla (`test_regla_8_13_9_...`).
- TDD en la capa de servicios. Tests posteriores en vistas.
- Las pruebas se acumulan: nunca borres ni debilites una prueba existente para que pase. Si una regla
  cambió, avisá y proponé el cambio de la prueba.
- Un test de integración (vista con el cliente de prueba de Django) por flujo principal de cada caso de
  uso. No escribas pruebas de navegador.
- Cada prueba arma sus propios datos y no depende de otra.
- Mientras trabajás, corré solo las pruebas del tema (`python manage.py test core.tests.test_usuario`).
  La suite completa se corre una vez, al terminar la tarea.

## Comandos (PowerShell, Windows)

```
.venv\Scripts\Activate.ps1
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py test
python manage.py test core.tests.test_usuario
```

## Seguridad

- El repositorio es público: ningún secreto en el código.
- No leas `.env`. Nunca pidas ni uses la cadena de conexión de Neon ni la clave secreta de producción.
- Trabajás solo contra la base local.

## Al terminar cada tarea

1. Corré la suite completa (`python manage.py test`) y mostrá el resultado.
2. Proponé la actualización de `docs/estado.md` y, si hubo decisiones nuevas, la entrada en `docs/decisiones.md`.
3. Proponé un mensaje de commit. El commit lo hace el estudiante.
