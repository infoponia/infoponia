# <ID> · <Título>

Estado: pendiente | App: <app> | Rama: feature/<id>-<nombre> | Ronda: <nombre de la ronda, o —>

Depende de: <ID> (si no está hecha, frená) | —

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9).

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| <CÓDIGO> | <nombre> | docs/casos_de_uso/<app>/<tema>.md | <«Fuera de la ronda (D-45)», o —> |

## Leer

- Casos de uso: lista arriba (extractos completos; leé solo los de la tabla)
- Modelo: docs/modelo/<app>.md — <clases>
- Decisiones: D-NN, D-NN
- Patrones: docs/patrones/<patrón>.md
- Pantallas: docs/prototipos/<carpeta>/ — <funciones> (solo guía visual)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: <lista, con su app> → revisá docs/disparadores.md | ninguno
- Migraciones: <cuáles se crean, con nombre; cuáles cargan datos> | ninguna
- Permitido fuera de la app: <archivos exactos> | nada
- Dependencias nuevas: ninguna | <paquete, con el permiso de quién>
- Fuera de alcance: <lo que queda para otra tarea o para otra ronda>

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. <modelos y migraciones> — pruebas: <archivo>
2. <servicios de un caso de uso, con sus reglas y postcondiciones> — pruebas: <archivo>
3. <vistas, plantillas y entrada del menú> — pruebas: <archivo>
4. <puntos de extensión, alertas, auditoría, datos de migración>

Si el tiempo apremia, lo último que se recorta es: <paso> (se anota como disparador).

## Hecho cuando

- <criterio verificable, uno por caso de uso o por pantalla>
- Pruebas: <app>/tests/test_<codigo_cu>.py (<CodigoCu>ServicioTests y <CodigoCu>VistaTests), una por caso de uso
- Comando de pruebas: python manage.py test <app>.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  (y las de concurrencia y de migración de esta tarea, con sus etiquetas, si las hay)

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
