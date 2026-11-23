# InfoPonia — Instrucciones para Claude Code

Mini-ERP en Django para organizaciones que producen y comercializan hidroponia.
Trabajo universitario (metodología UP). Equipo de dos estudiantes con experiencia
básica en Django: explicá lo que hacés y por qué, en español con voseo.

## Comportamiento

- Una sola vez por tarea, antes de editar: proponé un plan (los pasos de la tarea y los archivos que tocás) y esperá
  aprobación. Aprobado el plan, hacé todos los pasos de la tarea de corrido, corriendo las pruebas de cada paso antes de
  pasar al siguiente. No pidas permiso paso por paso: frená solo en los casos de L7 y L9 y, en los pasos de servicios, para que el
  estudiante revise las pruebas que fallan (`.claude/rules/pruebas.md`, «Orden en servicios»).
- Ante cualquier ambigüedad o contradicción con la documentación: detenete y preguntá. No elijas en silencio.
- Cada regla de negocio implementada cita su fuente en el docstring o en un comentario
  (por ejemplo: `# Regla 9 de 8.13 — modelo de dominio, ronda 20`).
- No agregues dependencias, no modifiques migraciones ya mergeadas en main y no cambies
  modelos ya mergeados sin permiso explícito. Lo que la tarea permite tocar fuera de su app está en
  «Permitido fuera de la app».
- No hagas commits, push ni operaciones de Git que modifiquen el historial. Los commits los hacen los estudiantes.
- **Números de decisión.** Se asignan por orden de creación, no por reserva. Una decisión planificada se nombra por su lote o tarea. El número se toma al final, después de `git fetch`, mirando `docs/decisiones/` en `main`; si dos PR chocan, renumera el que se mergea segundo; una decisión ya mergeada no se renumera nunca; una prueba lleva el número de una decisión en su nombre solo si esa decisión ya está en `main`. Proponé el número recién al cerrar la tarea (M3).
- Antes de borrar datos o tablas, frená y preguntá. Vale también para la base local y para los datos de prueba. Cuenta como borrar: `DROP`, `DELETE` o `TRUNCATE` a mano, `flush`, `migrate <app> zero`, `--fake` seguido de un borrado, borrar el archivo o la base de datos, y descartar la base de `--keepdb`. Contame qué se pierde, por qué hace falta y qué alternativa hay, y esperá mi respuesta. Si una migración no se puede deshacer, no la arregles tocando las tablas: avisame.
- **Verificación (la hace Claude).** El estudiante no verifica a mano ni carga datos de prueba (D-95). Antes de cerrar una tarea, hacé lo que dice `docs/patrones/verificacion_por_claude.md`:
  (1) un **recorrido** de punta a punta con el cliente de Django (`<app>/tests/test_recorrido_<tema>.py`), por rol y estado, con los pasos que antes serían «a mano»;
  (2) si la tarea tiene pantallas, una **verificación visual** con Playwright (`<app>/tests/test_visual_<tema>.py`, `INFOPONIA_VISUAL=1` y `--tag visual`), **mirando vos las capturas**; lo que veas mal se corrige y se anota (D-61);
  (3) si la tarea tiene migración, `sqlmigrate` de la nueva y aplicarla en la base de pruebas.
  Si la tarea trae «Verificación a mano», no prepares datos ni pasos para el estudiante: convertí cada paso en un recorrido. El cargador `cargar_datos_de_verificacion` y los `<app>/verificacion.py` **se retiraron** (D-95): si una tarea los nombra, ignoralo.
  (4) **Pasos para replicar:** al final de una ronda (cuando des el mensaje de commit y la propuesta de M3), dale al estudiante, aunque no vaya a hacerlos, los pasos de verificación a mano **con mucho detalle**, para que pueda replicarlos si se hace tiempo (formato en `docs/patrones/verificacion_por_claude.md`, «Pasos para replicar»). Van también en el «Cierre» de la tarea y en el texto del PR.
  Playwright es la única dependencia nueva permitida, y **solo de desarrollo** (`requirements-dev.txt`; nunca en `requirements.txt`). Las pruebas visuales usan su propia base de pruebas: no toques la base local de desarrollo. Nunca escribas una contraseña en un archivo versionado: el repo es público.
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
      o estilos, `.claude/rules/interfaz.md`; antes de cerrar la tarea, `docs/patrones/verificacion_por_claude.md`.
L4. Código: leé los archivos que vas a modificar y los que importan de forma directa.
    Para cualquier otra cosa, pedila y decí para qué la necesitás.
L5. Si la tarea no cubre un tema, buscalo en `docs/decisiones/README.md` y avisá antes de seguir.
L6. No leas `docs/historial.md`, `docs/revisiones_pendientes.md` ni un prototipo entero,
    salvo que el estudiante lo pida.
L7. Si la tarea contradice un caso de uso, el extracto del modelo, una decisión o el código,
    frená y preguntá. El prototipo es una referencia, no una especificación (D-61): si su lógica difiere
    del caso de uso, manda el caso de uso; si a una pantalla le falta algo que el caso de uso necesita o
    algo está mal como interfaz, corregila y completala vos, sin frenar, y anotalo en el «Cierre». Frená
    solo si la corrección necesita una regla, un permiso, un cálculo o una columna que no están en las
    fuentes de más peso.
L8. Las decisiones se citan por su ID («D-36»), sin ruta: el archivo es `docs/decisiones/D-36.md`.
L9. La documentación de cada tarea está completa por diseño (D-44): trae las reglas, los campos, los textos, las pantallas
    y los datos de migración que hacen falta. Si te falta algo que la tarea necesita, no lo inventes ni lo deduzcas del
    código: frená, decí qué falta y en qué archivo tendría que estar. Es un error de documentación y se corrige ahí.

## Fuentes de verdad (de mayor a menor peso)

1. Decisiones del equipo (`docs/decisiones/`).
2. Modelo de dominio (ronda 20, D-07) y glosario: extractos en `docs/modelo/`.
3. Casos de uso extendidos y pendientes: extractos en `docs/casos_de_uso/`.
4. Casos de uso originales (desactualizados; solo orientativos).
5. Prototipo: referencia de estructura, contenido y estilo, que puede tener errores o faltantes (`docs/prototipos/`, D-61).

Los documentos de Drive no se leen: el repo tiene sus copias, completas para cada ronda (D-44). Una tarea que nombra un
caso de uso o una clase sin extracto en el repo es un error de documentación (L9). Si una copia del repo y lo que sabés de Drive no
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
  `compras` y `comercial` (6), `iot` (7), `estadisticas` (8).
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
M2. Completá en el archivo de la tarea «Cierre» (qué se hizo, pruebas, decisiones y, si hubo, «Pantallas: lo que
    se corrigió del prototipo», D-61) y «Verificación» (tres listas: «Verifiqué», «Lo cubre una prueba» y «No pude verificar», más «Pasos para replicar», opcionales para el estudiante; `docs/patrones/verificacion_por_claude.md`).
M3. Proponé, sin aplicarlos (una sola vez, al cerrar la tarea entera, no por paso):
    - el `docs/estado.md` nuevo;
    - la fila de la tarea en `docs/tareas/README.md` (si queda hecha, se saca);
    - una línea para `docs/historial.md`;
    - si hubo decisión, `docs/decisiones/D-NN.md` y su fila en `docs/decisiones/README.md`;
    - si creaste modelos, los disparadores que se cumplieron (se tachan) y los que nacen;
    - la fila de la tarea en el plan de su ronda (`docs/tareas/ronda_<nombre>.md`), si pertenece a una;
    - lo que implementaste distinto de lo escrito, para `docs/temas_abiertos.md` (no lo corrijas en silencio).
M4. Proponé el mensaje de commit y el texto del PR (con los «Pasos para replicar»). El commit lo hace el estudiante.

La regla M6 (el estudiante aprueba cada lote de documentación antes de programar) es de las personas; está en `docs/README.md`,
«Ciclo de una tarea». La M5 (tachar las revisiones a mano) quedó en desuso: ya no se agregan revisiones a mano.
