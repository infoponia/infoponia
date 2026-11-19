# PRD-00 · Crear las apps de los módulos de negocio

Estado: pendiente | App: config (sin app propia) | Rama: feature/prd-00-crear-apps

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

## Cierre (la completa Claude Code al cerrar)
