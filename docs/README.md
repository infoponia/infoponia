# Documentación del repo — InfoPonia

Esta carpeta le da contexto a Claude Code para cada tarea, gastando lo menos posible. Tres principios:

1. **Enrutar, no cargar.** Claude Code siempre lee `CLAUDE.md` y `docs/estado.md`. Todo lo demás lo lee solo si el
   archivo de la tarea lo nombra, y solo las secciones nombradas.
2. **Nada pendiente vive en un archivo que no se lee.** Toda tarea, revisión, bloqueo u obligación futura está en el
   índice de tareas, en `estado.md` o en los disparadores.
3. **Lo vigente, resumido; lo histórico, intacto.** Las decisiones y el historial no se reescriben. Lo que sigue
   rigiendo se resume en los patrones y en las reglas de `.claude/rules/`.
4. **Completa por ronda, no justo a tiempo (D-44).** Antes de programar la primera tarea de una ronda, el repo tiene todo lo
   que la ronda necesita: el plan de tareas, un extracto por cada caso de uso, el modelo de todas sus clases, los patrones,
   los datos de migración y los disparadores. Más documentación en el repo no significa más lectura: «Enrutar, no cargar»
   sigue valiendo. Si a una tarea le falta algo, Claude Code frena (L9) y se corrige la documentación, no el código.

## Mapa

```
docs/
├── README.md                     este mapa (para las personas; Claude Code no lo necesita)
├── estado.md                     en curso, siguiente, revisiones y esperas. Siempre. ≤ 2 KB
├── historial.md                  lo hecho, tarea por tarea. Nunca por defecto
├── revisiones_pendientes.md      listas completas de verificación a mano. Solo si el estudiante lo pide
├── temas_abiertos.md             temas sin tarea ni disparador. Al planificar
├── disparadores.md               «cuando exista X, hay que hacer Y». Cuando la tarea crea modelos
├── api/                          contratos entre apps: alertas, notificaciones, puntos de extensión de maestros y de inventario, stock y variedades
├── tareas/
│   ├── README.md                 índice de tareas pendientes de todas las apps. Al elegir la próxima
│   ├── ronda_produccion_1.md     plan completo de la ronda: tareas, orden, casos de uso, pantallas y lotes de documentación
│   ├── _plantilla.md             plantilla de una tarea (un bloque funcional, con pasos)
│   └── <app>/<ID>-<nombre>.md    la orden de trabajo. Primero, al empezar
├── decisiones/
│   ├── README.md                 índice con «qué fija» y «leer si...». Solo para buscar una que la tarea no nombra
│   └── D-NN.md                   una decisión por archivo. Solo las que nombra la tarea
├── patrones/
│   ├── auditoria.md              cómo audita un módulo de negocio (D-22, D-36)
│   ├── bloqueos.md               bloqueos de filas y pruebas de concurrencia (D-30, D-32)
│   ├── datos_de_migracion.md     datos cargados por migración y pruebas: TransactionTestCase, ANALYZE y el mixin (MAE-01)
│   ├── trabajo_en_paralelo.md    dos personas en el mismo repo: ramas, migraciones, conflictos y documentos compartidos
│   ├── abm.md                    cómo se hace un ABM (lote 1; sale de MAE-01 y MAE-02a)
│   ├── stock.md                  stock libre, reservas, FEFO y «faltante sin lote» (lote 2)
│   └── costo_del_lote.md         costo acumulado y costo por planta sin asientos (lote 4, D-50)
├── casos_de_uso/
│   ├── _plantilla.md             encabezado y secciones de un extracto
│   ├── usuarios.md, auditoria.md (quedan donde están)
│   └── <app>/<tema>.md           extractos de «CU extendidos». Los que cite la tarea
├── modelo/
│   ├── README.md                 encabezado de un extracto del modelo
│   └── <app>.md                  extracto del modelo y del glosario. Los que cite la tarea
└── prototipos/
    ├── cuentas_y_seguridad.html  (queda donde está: D-24 lo nombra con esta ruta)
    └── produccion/
        ├── README.md             qué función arma cada pantalla y qué es «solo prototipo»
        └── datos_maestros_y_produccion.html
```

Fuera de `docs/`, el esquema también cambia `CLAUDE.md`, `.claude/rules/pruebas.md`, `.claude/rules/interfaz.md` y
`.claude/settings.json`.

## Ciclo de una tarea

1. **Documentar la ronda** (una persona, o Claude en claude.ai), por lotes pero con el plan completo desde el primero: el plan
   de la ronda (`tareas/ronda_produccion_1.md`), los archivos de tarea en `tareas/<app>/` con la plantilla, los extractos
   que nombran en «Leer» (`casos_de_uso/<app>/`, `modelo/<app>.md`), los patrones y los disparadores. El estudiante aprueba
   cada lote antes de programarlo (**M6**) y las tareas figuran en `tareas/README.md`.
2. **Planificar y programar** (Claude Code): lee `estado.md`, la tarea y solo lo que ella lista. Un plan por tarea, aprobado
   una vez; después hace todos sus pasos de corrido.
3. **Cerrar** (Claude Code propone, el estudiante aplica): completa «Cierre» y «Verificación a mano» en la tarea, y
   propone el `estado.md` nuevo, la fila del índice de tareas, una línea para `historial.md`, la sección de
   `revisiones_pendientes.md`, las decisiones nuevas y los disparadores cumplidos o nuevos.
4. **Revisar a mano**: quien hace un paso lo tacha en `revisiones_pendientes.md` y en `estado.md`, en el mismo commit
   (**M5**).

Las reglas M5 y M6 son de las personas, no de Claude Code: por eso están acá y no en `CLAUDE.md` (que tiene M1 a M4, las
del cierre de una tarea).

## Qué se mudó y adónde (18/11/2026)

| Antes | Ahora |
|---|---|
| `decisiones.md` | `decisiones/D-01.md` a `D-36.md`, sin cambios, más `decisiones/README.md` |
| `estado.md`, «Hecho», «Registrado el 05/11» y «Registrado el 08/11» | `historial.md` |
| `estado.md`, «En curso» (cuatro listas) y «Siguiente», punto 1 | `revisiones_pendientes.md` |
| `estado.md`, «Siguiente», tareas 07 y 09 | `tareas/usuarios/USR-07-foto-perfil.md` y `USR-09-seguridad-produccion.md` |
| `estado.md`, «Siguiente», punto 3 (CSV) | `tareas/auditoria/AUD-02-exportar-csv.md` |
| `estado.md`, «Siguiente», punto 3 (auditoría de negocio) | `patrones/auditoria.md` |
| `estado.md`, «Temas abiertos» | `temas_abiertos.md`, `disparadores.md`, USR-07, USR-09 o D-37 (tabla al pie de `temas_abiertos.md`) |
| `casos_de_uso/usuarios.md`, «Lo que queda para más adelante» | Se queda ahí y además está en `disparadores.md` |
