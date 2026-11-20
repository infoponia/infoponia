# Patrón · Trabajar de a dos en el mismo repo

Para las dos personas del equipo cuando programan tareas distintas al mismo tiempo. Los comandos están para PowerShell con
el entorno virtual activo. Claude Code no hace operaciones de Git (`CLAUDE.md`): los merges y los conflictos los resuelve
una persona; si querés, después de iniciar el merge le podés pedir a Claude Code que te explique un conflicto.

## Reglas

1. **Una tarea, una persona, una rama** (`feature/<id>-<nombre>`), creada desde `main` actualizado. Nunca dos personas en la
   misma tarea.
2. **Mergeá `main` en tu rama seguido**, al menos al empezar cada paso de la tarea y siempre antes de abrir el PR. Un
   conflicto chico de hoy es mejor que uno enorme el día del PR.
3. **Avisá por el chat** cuando tu tarea vaya a tocar `core` o una app que la otra persona también toca, y cuando te falte
   un número de decisión o de migración.
4. **PR al terminar la tarea, no después.** Cuanto más tiempo vive una rama, más choca.

```
git switch main
git pull
git switch -c feature/inv-01-catalogo-de-insumos

# cada tanto, y siempre antes del PR
git fetch origin
git merge origin/main
```

Se usa `merge` y no `rebase`: el `rebase` reescribe el historial y no lo hacemos.

## Qué archivos suelen chocar

| Archivo | Por qué choca | Qué hacer |
|---|---|---|
| `<app>/migrations/00NN_*.py` | Dos personas crean la «próxima» migración de la misma app | Ver «Migraciones» |
| `core/migrations/` por `choices` de `RegistroAuditoria.accion` | Cada acción de auditoría nueva (D-36) cambia los `choices`, y eso genera migración en `core` | Que una sola persona haga la migración de `core` de la semana, o que la segunda regenere la suya después del merge |
| `config/settings.py`, `config/urls.py`, `core/menu.py` | Las dos agregan una línea en la misma lista | Conservar las dos líneas |
| `docs/estado.md`, `docs/tareas/README.md`, `docs/historial.md`, `docs/revisiones_pendientes.md` | Las dos proponen su cierre (M3) | Conservar lo de las dos y verificar que las filas tachadas sean las que se hicieron |
| `docs/decisiones/README.md` y el número `D-NN` | Las dos toman la «próxima libre» | Reservar el número por el chat antes de escribir; si coinciden, la que mergea segunda renumera su archivo, su fila y las citas |
| `docs/disparadores.md` | Las dos tachan o agregan filas | Conservar las dos |

## Cómo se ve un conflicto y cómo se resuelve

Al hacer `git merge origin/main`, Git avisa «CONFLICT» y deja en el archivo marcas como estas:

```
<<<<<<< HEAD
tu versión
=======
la versión de main
>>>>>>> origin/main
```

1. `git status` muestra los archivos en conflicto («both modified»).
2. Abrí cada archivo (en VS Code aparecen los botones «Accept Current», «Accept Incoming» y «Accept Both»). Decidí qué
   queda: tu versión, la de `main` o las dos mezcladas. Borrá las tres líneas de marcas.
3. `git add <archivo>` por cada archivo resuelto.
4. `git commit` (Git ya propone el mensaje del merge).
5. Corré las pruebas de tu tarea y `python manage.py makemigrations --check --dry-run`. Si algo falla, el conflicto se
   resolvió mal: mirá `git diff` contra `origin/main`.
6. Si te perdiste: `git merge --abort` vuelve al estado anterior al merge sin perder nada.

En código, un conflicto casi siempre se resuelve conservando las dos partes. Si las dos partes hacen lo mismo de forma
distinta, hablalo con la otra persona antes de elegir.

## Migraciones (el conflicto más común)

Django exige que las migraciones de una app formen una línea. Si las dos ramas agregaron una migración a la misma app, al
mergear aparece el error «Conflicting migrations detected; multiple leaf nodes». **Nunca se edita una migración que ya
está en `main`** (`CLAUDE.md`). Hay dos salidas:

- **Tu migración todavía no está en `main` (lo normal).** Regenerala sobre la de la otra persona:
  1. Desaplicá la tuya en tu base local, antes de borrarla: `python manage.py migrate <app> <numero_anterior_a_la_tuya>`.
  2. Hacé el merge de `origin/main` y borrá tu archivo de migración (solo el tuyo).
  3. `python manage.py makemigrations <app> -n <nombre_claro>`: Django la numera a continuación de la de `main`.
  4. `python manage.py migrate` y corré las pruebas de la app.
- **Las dos ramas ya están publicadas y las migraciones son independientes.** `python manage.py makemigrations --merge` crea
  una migración de fusión que une las dos líneas. Sirve, pero deja un archivo más; se prefiere la primera salida.

Con `--keepdb` y `--parallel`, después de cambiar migraciones hay que recrear la base de pruebas una vez
(`--keepdb` se omite esa vez).

## Documentos que escribe una sola persona

La documentación de la ronda (`docs/tareas/`, `docs/casos_de_uso/`, `docs/modelo/`, `docs/patrones/`) la escribe una sola
persona o Claude en claude.ai, por lotes, y entra al repo en su propio PR (rama `docs/...`) **antes** de que alguien
programe sobre ella. Nadie edita a mano un extracto mientras el lote está abierto: si algo está mal, se avisa y se corrige
ahí (L9).
