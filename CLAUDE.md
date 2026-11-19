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
  modelos ya mergeados sin permiso explícito. Lo que la tarea permite tocar fuera de su app está en
  «Permitido fuera de la app».
- No hagas commits, push ni operaciones de Git que modifiquen el historial. Los commits los hacen los estudiantes.
- Nunca listes ni leas `.venv/`.
- Verificá versiones y comandos actuales antes de recomendarlos; no recomiendes de memoria.

## Qué leer

L1. Al empezar: este archivo y `docs/estado.md`.
L2. Leé el archivo de la tarea que te indique el estudiante (`docs/tareas/<app>/<ID>-*.md`).
    Si no te indica ninguna, preguntá cuál.
L3. Leé solo lo que la tarea lista en «Leer», y solo las secciones nombradas.
    - Decisiones: `docs/decisiones/D-NN.md`, solo las listadas.
    - Prototipo: buscá con Grep la función que nombra la tarea y leé solo esa parte.
    - Antes de escribir o correr pruebas, leé `.claude/rules/pruebas.md`; antes de tocar plantillas
      o estilos, `.claude/rules/interfaz.md`.
L4. Código: leé los archivos que vas a modificar y los que importan de forma directa.
    Para cualquier otra cosa, pedila y decí para qué la necesitás.
L5. Si la tarea no cubre un tema, buscalo en `docs/decisiones/README.md` y avisá antes de seguir.
L6. No leas `docs/historial.md`, `docs/revisiones_pendientes.md` ni un prototipo entero,
    salvo que el estudiante lo pida.
L7. Si la tarea contradice un caso de uso, el extracto del modelo, una decisión o el código,
    frená y preguntá. El prototipo es solo una guía visual: si su lógica difiere del caso
    de uso, manda el caso de uso.
L8. Las decisiones se citan por su ID («D-36»), sin ruta: el archivo es `docs/decisiones/D-36.md`.

## Fuentes de verdad (de mayor a menor peso)

1. Decisiones del equipo (`docs/decisiones/`).
2. Modelo de dominio (ronda 20, D-07) y glosario: extractos en `docs/modelo/`.
3. Casos de uso extendidos y pendientes: extractos en `docs/casos_de_uso/`.
4. Casos de uso originales (desactualizados; solo orientativos).
5. Prototipo: solo guía visual (`docs/prototipos/`).

Los documentos de Drive no se leen: el repo tiene sus copias. Si una copia del repo y lo que sabés de Drive no
coinciden, avisá. Los elementos «Solo prototipo» no se implementan (lista en cada caso de uso y en el `README.md`
de cada prototipo).

## Stack

- Python 3.11.x, Django 5.2 LTS, PostgreSQL 17 (local en el puerto 5433).
- psycopg 3, gunicorn, whitenoise, dj-database-url, python-dotenv.
- Frontend: plantillas de Django con HTMX. CSS propio, sin Tailwind.
- Despliegue: Render (servidor) y Neon (base de producción). Render ejecuta `migrate` en cada despliegue.

## Arquitectura

- Monolito Django (MTV) con capa de servicios.
- Cada caso de uso es una función de servicio dentro de `transaction.atomic()`. Sus pre y postcondiciones salen del
  caso de uso extendido y de las reglas del modelo de dominio. En `core`, los servicios están en `core/servicios.py`;
  en las apps nuevas, en el paquete `<app>/servicios/`, un archivo por entidad raíz, importado del módulo y sin
  reexportar en `__init__.py` (D-37).
- Las vistas solo orquestan: validan la entrada, llaman al servicio y renderizan.
- El alcance por usuario se aplica con un único manager o queryset por modelo.
- Modelo de usuario: D-01 a D-04.
- Apps por niveles (D-37): `core` (1), `contabilidad` (2), `maestros` (3), `inventario` (4), `produccion` (5),
  `compras` y `comercial` (6), `iot` (7).
  - A1. Una app solo importa de apps de nivel menor. `compras` y `comercial` no se importan entre sí.
  - A2. Toda FK o M2M se declara en la app de nivel mayor.
  - A3. Un caso de uso que toca varias apps vive en la más alta que toca.
  - A4. Cuando una app baja necesita preguntarle algo a una alta, la alta se registra en un punto de extensión de la
    baja, en `AppConfig.ready()`.
- Antes de crear un modelo, revisá `docs/disparadores.md`. Si el servicio audita, seguí `docs/patrones/auditoria.md`;
  si bloquea filas, `docs/patrones/bloqueos.md` (cuando la tarea los nombre).

## Convenciones

- Nombres en español según el glosario, en snake_case, conservando el sufijo de la clase
  (`nombre_invernadero`). Las correcciones de errores de tipeo del diagrama se registran en una decisión.
- Clave primaria: `id` automático de Django, equivalente a `idX` del diagrama.
- Dinero siempre con `Decimal` y `DecimalField`. Nunca `float`.
- `select_for_update()` en reservas de stock y en toda operación concurrente sobre cantidades.
- Cada archivo empieza con un comentario que explica su propósito.
- Docstring en cada clase y función; comentarios en la lógica no evidente.
- Patrones de diseño solo si están identificados y justificados en un comentario.

## Pruebas

Las reglas de pruebas (tipos, orden, etiquetas, cómo correrlas y nombres) están en `.claude/rules/pruebas.md`.
Cada tarea trae su «Comando de pruebas». La suite completa la corre el CI en el PR.

## Comandos

Los comandos de este archivo están escritos para la terminal PowerShell del estudiante, con el
entorno virtual activo. Cuando los ejecutes vos con la herramienta Bash, que no hereda el entorno
virtual, reemplazá siempre `python` por `.venv/Scripts/python.exe`
(por ejemplo, `.venv/Scripts/python.exe manage.py test`).

```
.venv\Scripts\Activate.ps1
python manage.py runserver
python manage.py makemigrations
python manage.py migrate
python manage.py test
python manage.py test core.tests.test_usuario --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
```

## Seguridad

- El repositorio es público: ningún secreto en el código.
- No leas `.env`. Nunca pidas ni uses la cadena de conexión de Neon ni la clave secreta de producción.
- Trabajás solo contra la base local.

## Al terminar cada tarea

M1. Corré el «Comando de pruebas» de la tarea y mostrá el resultado.
M2. Completá en el archivo de la tarea «Cierre» (qué se hizo, pruebas, decisiones) y «Verificación a mano»
    (los pasos para el estudiante).
M3. Proponé, sin aplicarlos:
    - el `docs/estado.md` nuevo;
    - la fila de la tarea en `docs/tareas/README.md` (si queda hecha, se saca);
    - una línea para `docs/historial.md`;
    - la sección de la tarea en `docs/revisiones_pendientes.md`, si hay pasos a mano;
    - si hubo decisión, `docs/decisiones/D-NN.md` y su fila en `docs/decisiones/README.md`;
    - si creaste modelos, los disparadores que se cumplieron (se tachan) y los que nacen.
M4. Proponé el mensaje de commit. El commit lo hace el estudiante.
