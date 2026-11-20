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

Hay una migración nueva: `python manage.py migrate`. 1) `migrate` pasa sin errores. 2) En `shell`, `OrigenDocumento()` + `save()` falla con un mensaje claro. 3) Después del merge, verificar en el log de Render que se aplicó la migración.

## Cierre (la completa Claude Code al cerrar)
