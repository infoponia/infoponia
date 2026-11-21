# DIA-01 · Proceso diario: pasos registrados y comando `proceso_diario` (sin cron job)

Estado: pendiente | App: core | Rama: feature/dia-01-proceso-diario | Ronda: — (transversal; va antes de INV-02)

Depende de: nada. Es chica y no toca modelos.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por
paso. Si algo que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** InfoPonia va a tener varios procesos que corren una vez por día:
- revisar vencimientos de insumos;
- vencer partidas en cámara;
- vencer pagos;
- pre-reservar suministros;
- planificar entregas.

D-56 decide que **todavía no se crea ningún cron job**. Se arma uno solo al final de la implementación. Mientras tanto, cada
proceso se programa y se prueba igual, con un comando que se corre a mano. Esta tarea deja ese mecanismo en `core`:
- un registro de pasos diarios, al que cada app suma el suyo en su `AppConfig.ready()`;
- el comando `python manage.py proceso_diario`, que los corre en orden.

Es el «cron job sin cron job»: lo mismo que hará el cron, pero lanzado por una persona.

## Casos de uso incluidos

Ninguno: es una característica del sistema. Los casos de uso son los de cada paso (por ejemplo, CMP-REV-VNC, que registra
INV-02).

## Leer

- Decisiones: D-56 (la de esta tarea), D-37 (A1 y A4), D-22 (la auditoría: los pasos auditan lo suyo, el mecanismo no
  audita).
- Reglas: .claude/rules/pruebas.md.
- Código a leer: `core/extensiones.py` (el estilo de los registros: listas de módulo, `_registrar` idempotente) y `core/apps.py`.
  Si existe, `inventario/management/commands/` (no debería: lo crea INV-02).

## Límites

- Crea modelos: ninguno.
- Migraciones: ninguna.
- Permitido fuera de `core`: nada. Al cerrar (M3), los textos de `docs/tareas/README.md` y `docs/estado.md`.
- Dependencias nuevas: ninguna. Nada de Celery ni de `django-crontab` ni de hilos: es un comando de Django y nada más.
- Fuera de alcance:
  - crear el cron job en Render, que se hace al final (disparador «Cuando se arme el cron único»);
  - la lógica de cualquier paso: cada app programa y registra el suyo. El primero lo registra INV-02.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Registro de pasos**, en `core/procesos.py`:
   - **Tipos.** `PasoDiario = namedtuple("PasoDiario", "codigo nombre orden funcion")` y
     `ResumenDePaso = namedtuple("ResumenDePaso", "procesados creados resueltos detalle")`, con `detalle` en texto libre y
     opcional.
   - **`registrar_paso_diario(codigo, nombre, orden, funcion)`:** `funcion(hoy) -> ResumenDePaso`, donde `hoy` es un `date`.
     - Es idempotente: registrar dos veces el mismo `codigo` con la misma función no lo duplica, porque `ready()` puede correr
       más de una vez.
     - Lanza `RuntimeError` si el `codigo` se repite con otra función, o si el `orden` se repite con otro paso.
   - **`pasos_diarios()`:** los pasos, ordenados por `orden`.
   - **`correr_proceso_diario(hoy=None, solo=None)`:** corre los pasos en orden y devuelve una lista de
     `(paso, ResumenDePaso | None, error | None)`.
     - `hoy` vale por defecto `timezone.localdate()`. Se lee **una sola vez** y se pasa a todos los pasos.
     - `solo` es un `codigo`: corre solo ese paso. Si no existe, lanza `ValueError` con la lista de códigos válidos.
     - Si un paso lanza una excepción, se registra con `logging` (`logger = logging.getLogger("infoponia.proceso_diario")`),
       con el código y la excepción, y **los demás siguen**. `correr_proceso_diario` no abre transacciones: cada paso maneja
       las suyas, una por unidad (D-56, punto 4).
   En el encabezado del archivo, la tabla de órdenes reservados de D-56, punto 6.
   Pruebas, en `core/tests/test_proceso_diario.py`, con pasos falsos (`mock.patch.object` sobre la lista de módulo):
   - el orden;
   - `hoy` llega igual a todos;
   - `solo`, y `solo` con un código que no existe;
   - un paso que falla no frena a los siguientes y queda informado;
   - las dos formas de repetir dan `RuntimeError`;
   - registrar dos veces lo mismo es idempotente;
   - sin pasos, devuelve una lista vacía.
2. **Comando** `core/management/commands/proceso_diario.py`, sin lógica propia: llama a `correr_proceso_diario`.
   - **Opciones:**
     - `--fecha AAAA-MM-DD`: simula ese día; con un formato inválido, `CommandError`;
     - `--solo <codigo>`;
     - `--listar`: muestra los pasos en orden, con código, orden y nombre, y no corre nada.
   - **Salida.** Una línea al empezar, con la fecha usada. Una línea por paso, con su nombre y su resumen: «procesados N ·
     creados N · resueltos N», más el detalle si hay. Si un paso falla, «FALLÓ: …». Una línea final con la cantidad de pasos
     correctos y fallidos. Sin pasos registrados: «No hay pasos registrados» y código 0.
   - **Código de salida:** 0 si todos salieron bien; 1 si alguno falló (`sys.exit(1)` o `CommandError`). Así el cron del futuro
     marca la corrida como fallida.
   Pruebas, en `core/tests/test_comando_proceso_diario.py`, con `call_command`:
   - con `--fecha` y sin ella;
   - con `--fecha` inválida;
   - `--listar`;
   - `--solo`;
   - el código de salida con un paso que falla;
   - sin pasos.
3. **Documentación del uso**, en el docstring del comando y en el «Cierre». Cómo se usa en la máquina local (PowerShell, con el
   entorno virtual activo):

   ```
   python manage.py proceso_diario --listar
   python manage.py proceso_diario
   python manage.py proceso_diario --fecha 2026-12-15
   python manage.py proceso_diario --solo revisar_vencimientos
   ```

   En Render también se puede correr a mano, desde la «Shell» del web service, sin crear ningún cron job.
4. **Cierre de documentación.** Proponé, sin aplicarlos (M3):
   - marcar DIA-01 en `docs/tareas/README.md`;
   - en `docs/estado.md`, que siga la línea «Proceso diario: se corre a mano con `python manage.py proceso_diario`; el cron job,
     al final (D-56)», y sacar DIA-01 de «Siguiente»;
   - pasar D-56 a «vigente» si el estudiante la validó.

## Hecho cuando

- `python manage.py proceso_diario --listar` funciona sin pasos registrados y muestra «No hay pasos registrados».
- Con pasos falsos en las pruebas: se respeta el orden; un paso que falla no frena a los demás; el código de salida es 1.
- No hay ningún cron job, ningún hilo ni ninguna dependencia nueva.
- Comando de pruebas:
  python manage.py test core.tests.test_proceso_diario core.tests.test_comando_proceso_diario --keepdb --parallel

## Verificación a mano (la completa Claude Code al cerrar)

Sin migraciones.

1. `python manage.py proceso_diario --listar`: «No hay pasos registrados» (hasta que INV-02 registre el primero).
2. `python manage.py proceso_diario --fecha 2026-13-01`: error claro por la fecha inválida, sin traza de Python. Lo mismo
   con `--fecha 2026-1-5` (sin ceros): se rechaza a propósito. En los dos casos `echo $LASTEXITCODE` da 1.
3. Cuando INV-02 esté mergeada: `--listar` muestra «10 · revisar_vencimientos · Revisar vencimientos de insumos». Correrlo dos
   veces seguidas no duplica alertas. `--fecha` con un día de dentro de un mes genera las alertas «por vencer» que
   correspondan.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo** (21/11/2026). Sin modelos, sin migraciones, sin dependencias nuevas y sin tocar nada fuera de `core`.

- `core/procesos.py`: `PasoDiario`, `ResumenDePaso` (`detalle` opcional, por defecto `""`), `registrar_paso_diario`,
  `pasos_diarios` y `correr_proceso_diario(hoy=None, solo=None)`. En el encabezado, la tabla de órdenes de D-56, punto 6.
  Sigue el estilo de `core/extensiones.py`: lista de módulo (`_PASOS_DIARIOS`) y registro idempotente.
- `core/management/commands/proceso_diario.py` (con los dos `__init__.py` de `core/management/`): sin lógica propia.
  Opciones `--fecha`, `--solo` y `--listar`. Código de salida 1 si algún paso falla (lanza `CommandError` al final).
- Pruebas: `core/tests/test_proceso_diario.py` (15) y `core/tests/test_comando_proceso_diario.py` (10), todas
  `SimpleTestCase` con pasos falsos: no usan la base. Se escribieron primero las del servicio, se mostró que fallaban contra
  un esqueleto y el estudiante las revisó antes de implementar.

**Cómo se usa** (PowerShell, con el entorno virtual activo; también está en el docstring del comando):

```
python manage.py proceso_diario --listar
python manage.py proceso_diario
python manage.py proceso_diario --fecha 2026-12-15
python manage.py proceso_diario --solo revisar_vencimientos
```

En Render se puede correr a mano desde la «Shell» del web service, sin crear ningún cron job. Todavía no hay pasos
registrados: el primero (`revisar_vencimientos`, orden 10) lo registra INV-02.

**Pruebas** (M1). Comando de la tarea: 25 pruebas, OK. `test core --keepdb --parallel --exclude-tag concurrencia
--exclude-tag migracion`: 683 pruebas, OK (sin regresiones). `--listar` sin pasos: «No hay pasos registrados.», código 0.
`--fecha 2026-13-01` y `--fecha 2026-1-5`: mensaje claro sin traza, código 1. `makemigrations --check --dry-run`: sin
cambios. `manage.py check`: sin problemas.

**Lo implementado distinto de lo escrito, o que la tarea no decía** (a `docs/temas_abiertos.md`):

1. **Registro idéntico.** La tarea pide `RuntimeError` si el `codigo` se repite con otra función. Se decidió (el estudiante,
   al aprobar el plan) que solo un registro idéntico (código, nombre, orden y función) es idempotente: el mismo código y la
   misma función con otro nombre u otro orden también lanzan `RuntimeError`.
2. **`--fecha` estricta.** `strptime("%Y-%m-%d")` acepta `2026-1-5`; el comando además compara con `fecha.isoformat()`
   y rechaza todo lo que no sea `AAAA-MM-DD` con ceros.
3. **Textos de la salida** que la tarea no fija (aprobados con el plan): «Proceso diario del AAAA-MM-DD.» al empezar,
   «Pasos correctos: N · fallidos: N.» al terminar, «No hay pasos registrados.» (con punto) y las líneas de error de
   `--fecha` y `--solo`.
4. **`--listar` y `--fecha`.** La fecha se valida antes que nada: `--listar --fecha 2026-13-01` da error. Sin pasos
   registrados, `--solo` con cualquier código también dice «No hay pasos registrados.» y termina en 0.
5. **Una sola lectura de la fecha.** El comando lee `timezone.localdate()` una vez y se la pasa a `correr_proceso_diario`, así
   el encabezado y los pasos ven el mismo día. `correr_proceso_diario` igual la lee solo si se la llama sin `hoy`.
6. **`ResumenDePaso`** tiene `detalle=""` por defecto (`defaults=("",)`), para que un paso pueda devolver
   `ResumenDePaso(procesados, creados, resueltos)`.

**Decisiones:** ninguna nueva. D-56 pasa a «vigente» (validada por el estudiante el 21/11/2026).
