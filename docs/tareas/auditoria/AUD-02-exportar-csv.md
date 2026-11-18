# AUD-02 · Exportar la auditoría a CSV

Estado: pendiente | App: core | Rama: feature/aud-02-exportar-csv

Depende de: AUD-01 (AUD-CNS-REG, hecha)

Origen: `docs/estado.md`, «Siguiente», punto 3, y D-36 («Consecuencias»): «Trabajo futuro, fuera de esta tarea:
exportar los registros filtrados a CSV». No hay caso de uso escrito: antes de planificar, hay que definir sus reglas.

## Leer

- Casos de uso: docs/casos_de_uso/auditoria.md — AUD-CNS-REG (reglas 1 a 7)
- Decisiones: D-22, D-36
- Patrones: docs/patrones/auditoria.md
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md

## Límites

- Crea modelos: ninguno
- Permitido fuera de la app: nada
- Migraciones: ninguna
- Dependencias nuevas: ninguna (el módulo `csv` de Python alcanza)
- Fuera de alcance: otros formatos de exportación

## Hecho cuando

- Desde la lista de «Auditoría», quien la ve puede bajar en CSV los registros filtrados, con el mismo alcance
  (`visibles_para`) y los mismos filtros.
- Pruebas: core/tests/test_aud_cns_reg.py (o el archivo del caso de uso nuevo, si se escribe uno)
- Comando de pruebas: python manage.py test core.tests.test_aud_cns_reg --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

## Cierre (la completa Claude Code al cerrar)
