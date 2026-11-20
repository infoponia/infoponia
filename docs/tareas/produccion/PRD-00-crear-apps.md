# PRD-00 · Crear las apps de los módulos de negocio

Estado: hecha | App: config (sin app propia) | Rama: feature/prd-00-crear-apps

Depende de: — (D-37 vigente desde el 18/11/2026)

## Leer

- Decisiones: D-23, D-37
- Reglas: .claude/rules/pruebas.md

## Límites

- Crea modelos: ninguno
- Permitido fuera de la app: `config/settings.py` (`INSTALLED_APPS`)
- Migraciones: ninguna
- Dependencias nuevas: ninguna
- Fuera de alcance: cualquier modelo, vista o pantalla; los extractos del modelo los arma el equipo en claude.ai

## Hecho cuando

- Existen las apps `contabilidad`, `maestros`, `inventario` y `produccion`, vacías, registradas en `INSTALLED_APPS`
  en el orden de sus niveles (D-37), cada una con su paquete `servicios/` (con `__init__.py` vacío, sin reexportar) y su
  paquete `tests/`.
- Cada archivo nuevo empieza con el comentario que explica su propósito (`CLAUDE.md`, «Convenciones»).
- `python manage.py check` y `python manage.py makemigrations --check --dry-run` pasan sin cambios.
- Comando de pruebas: python manage.py test core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Ninguna. El CI cubre check, las migraciones y las pruebas; la estructura de archivos se revisa en el diff del PR.

## Cierre (la completa Claude Code al cerrar)

- Qué se hizo: se crearon las apps `contabilidad`, `maestros`, `inventario` y `produccion` a mano (sin `startapp`, para
  no generar `models.py`, `views.py`, `admin.py` ni un `tests.py` que chocaría con el paquete `tests/`). Cada una tiene
  `__init__.py`, `apps.py` (AppConfig sin `ready()`), `migrations/__init__.py` (sin migraciones), `servicios/__init__.py`
  vacío y `tests/__init__.py`. Se registraron en `INSTALLED_APPS` después de `core`, en el orden de niveles de D-37.
  Estructura acordada con Fabrizio: mínima, más `migrations/__init__.py`.
- Pruebas: no se escribieron pruebas nuevas (no hay reglas de negocio). `manage.py check`: sin problemas.
  `makemigrations --check --dry-run`: «No changes detected». Comando de pruebas de la tarea: 522 pruebas, OK.
- Decisiones: ninguna nueva. Se aplicó D-37 (D-23 completada). No se crearon modelos: no hay disparadores.
