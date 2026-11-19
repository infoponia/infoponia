# <ID> · <Título>

Estado: pendiente | App: <app> | Rama: feature/<id>-<nombre>

Depende de: <ID> (si no está hecha, frená) | —

## Leer

- Casos de uso: docs/casos_de_uso/<app>/<tema>.md — <código>: <secciones>
- Modelo: docs/modelo/<app>.md — <clases>
- Decisiones: D-NN, D-NN
- Patrones: docs/patrones/<patrón>.md
- Pantallas: docs/prototipos/<carpeta>/ — <funciones>
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: <lista> → revisá docs/disparadores.md | ninguno
- Permitido fuera de la app: <archivos exactos> | nada
- Migraciones: solo nuevas, en <app>
- Dependencias nuevas: ninguna | <paquete, con el permiso de quién>
- Fuera de alcance: <lo que queda para otra tarea>

## Hecho cuando

- <criterio verificable>
- Pruebas: <app>/tests/test_<codigo_cu>.py (<CodigoCu>ServicioTests y <CodigoCu>VistaTests)
- Comando de pruebas: python manage.py test <app>.tests.test_<codigo_cu> --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
