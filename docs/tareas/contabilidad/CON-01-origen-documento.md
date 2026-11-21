# CON-01 · `OrigenDocumento`: el documento de origen común (D-52)

Estado: pendiente | App: contabilidad | Rama: feature/con-01-origen-documento | Ronda: Producción 1

Depende de: PRD-00 (las apps, ya hecha). **La necesitan INV-01 (que crea `MovimientoInsumo`) y PRD-01**: no empieces ninguna de las dos sin ella mergeada.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es una tarea **chica** (una clase y su migración) y la base sobre la que heredan órdenes, bitácora y movimientos de insumo.

## Casos de uso incluidos

Ninguno. Es una estructura del modelo (D-52), no un caso de uso.

## Leer

- Modelo: docs/modelo/contabilidad.md (completo)
- Decisiones: D-37, D-45, D-50, D-52
- Reglas: CLAUDE.md («Convenciones»), .claude/rules/pruebas.md
- Código a leer: `contabilidad/` (apps.py, paquetes vacíos de PRD-00) y `config/settings` (orden de `INSTALLED_APPS`)

## Límites

- Crea el modelo `OrigenDocumento` en `contabilidad/models.py` (ficha de `docs/modelo/contabilidad.md`): `tipo` con `OrigenDocumento.Tipo` (`orden_de_trabajo`, `bitacora`, `movimiento_de_insumo`), obligatorio y dentro de la lista.
- Migración: solo nueva, `contabilidad/migrations/0001_initial.py`. **Sin migración de datos y sin plan de cuentas** (eso viene con la contabilidad).
- `save()` de `OrigenDocumento` lanza `TypeError` (o la excepción que se defina) si se lo llama sobre una instancia pura sin `tipo` de hija directa. Dejá documentada, en un comentario del modelo, **cómo fija el `tipo` una hija directa** (`TIPO_DE_ORIGEN` como atributo de clase que `save()` copia), para que `MovimientoInsumo` (INV-01), `OrdenTrabajo` y `Bitacora` (PRD-01) la usen sin repetir lógica.
- Permitido fuera de la app: nada. No toques `produccion` ni `inventario`.
- Dependencias nuevas: ninguna
- Fuera de alcance: asientos, ejercicio, cuentas y movimientos contables (D-45); cualquier hija (las crean INV-01 y PRD-01).

## Pasos

1. **Modelo y migración.** `OrigenDocumento` con su `Tipo`, `save()` protegido y la convención de la hija. `python manage.py makemigrations contabilidad` y revisar que la migración es solo esa tabla.
2. **Pruebas** (`contabilidad/tests/test_origen_documento.py`): no se puede crear uno puro; una hija de prueba (declarada dentro de la prueba, sin migración, con `isolate_apps` o un modelo de prueba) fija su `tipo` y queda creada con su `id`; el `tipo` fuera de la lista no es válido; dos hijas de prueba comparten la secuencia de `id`; `makemigrations --check` no deja cambios.
3. **Cierre de documentación.** Proponé, sin aplicarlos (M3): cerrar en `docs/disparadores.md` el apartado «Cuando exista contabilidad con asientos» punto 0 que corresponda a esta tarea; marcar CON-01 en `docs/tareas/README.md`, `docs/tareas/ronda_produccion_1.md` y `docs/estado.md`.

## Hecho cuando

- Existe `contabilidad.OrigenDocumento` con su migración inicial y sus pruebas; `makemigrations --check` y `check` pasan.
- Ninguna hija existe todavía: INV-01 y PRD-01 la usan.
- Comando de pruebas:
  python manage.py test contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate`. Cuenta: no hace falta ninguna (no hay pantallas).

1. `python manage.py migrate` pasa sin errores y aplica `contabilidad.0001_initial`.
2. `python manage.py makemigrations --check --dry-run` responde «No changes detected».
3. En `python manage.py shell`: `from contabilidad.models import OrigenDocumento` y `OrigenDocumento(tipo="bitacora").save()` falla con `TypeError` y un mensaje que dice que solo se guardan las hijas directas con `TIPO_DE_ORIGEN`.
4. En el mismo `shell`: `OrigenDocumento.objects.count()` da 0 (el intento anterior no dejó ninguna fila).
5. En `/admin/` (solo con `DJANGO_DEBUG=1`) no aparece «Documentos de origen»: el modelo no se registra en el admin, es esperado.
6. Después del merge: verificar en el log de Render que se aplicó la migración `contabilidad.0001_initial`.

## Cierre (la completa Claude Code al cerrar)

- **Qué se hizo:** `contabilidad.OrigenDocumento` (`contabilidad/models.py`) con `Tipo` (`orden_de_trabajo`, `bitacora`, `movimiento_de_insumo`) y `tipo` obligatorio y dentro de la lista (`choices`, `max_length=30`). `save()` lanza `TypeError` si la clase no tiene un `TIPO_DE_ORIGEN` válido y, si lo tiene, lo copia en `tipo` (la hija fija el tipo y no cambia). La convención de las hijas directas quedó documentada en un comentario del modelo. Migración `contabilidad/migrations/0001_initial.py`: solo esa tabla, sin datos y sin plan de cuentas. Se actualizó el docstring de `contabilidad/apps.py`. No se tocó `produccion`, `inventario` ni nada fuera de `contabilidad`.
- **Pruebas:** `contabilidad/tests/test_origen_documento.py`, 9 pruebas: no se guarda uno puro; la hija fija su tipo; la hija no cambia su tipo; la nieta hereda el tipo; tipo fuera de la lista y tipo obligatorio inválidos en `full_clean`; hija con tipo inválido o ausente no se guarda; los `id` se comparten entre hijas; `makemigrations` no deja cambios. Las pruebas de las reglas se mostraron fallando antes de implementar `save()` (6 de 9). Comando de la tarea: 667 pruebas, OK. `check` y `makemigrations --check --dry-run` sin cambios.
- **Decisiones:** ninguna nueva. Aplica D-52 (puntos 1 y 2), D-37 y D-45. Criterios acordados con el estudiante: `save()` sobrescribe `tipo` con `TIPO_DE_ORIGEN`; una subclase de segundo nivel hereda el atributo y puede guardarse.
- **Diferencias con la documentación:** (1) `max_length=30` y los nombres visibles de `Tipo` no estaban fijados en la ficha. (2) No hay `CheckConstraint` en la base para `tipo`: la lista se controla con `choices` y con `save()`; cada ronda que sume un tipo ya genera su migración por el cambio de `choices`. (3) `docs/disparadores.md` («Cuando exista contabilidad con asientos», punto 0) dice «CON-01 e INV-02», pero `MovimientoInsumo` lo crea INV-01.
