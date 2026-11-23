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
├── api/                          contratos entre apps: asientos (D-86), alertas, notificaciones, correo (`core/correo.py`, D-54), puntos de extensión de maestros, de inventario y de producción, stock, variedades, producción y direcciones; `nodo/`, el contrato con el nodo central del IoT (v1: guía, mensajes, errores, ejemplos y el flujo de Node-RED; lote I2a)
├── tareas/
│   ├── README.md                 índice de tareas pendientes de todas las apps. Al elegir la próxima
│   ├── ronda_produccion_1.md     plan completo de la ronda: tareas, orden, casos de uso, pantallas y lotes de documentación
│   ├── ronda_comercial_1.md      ídem, ronda «Comercial 1» (con cosecha; en paralelo con el IoT)
│   ├── ronda_iot_1.md            ídem, ronda «IoT 1» (D-70 a D-79; IOT-01 e IOT-02 en paralelo con producción)
│   ├── ronda_contabilidad_1.md   ídem, rondas nuevas: «Contabilidad 1» y «Contabilidad 2» (D-84 a D-86, D-92),
│   ├── ronda_contabilidad_2.md     «Compras 1» (D-87 a D-91) y «Estadísticas 1» (D-93)
│   ├── ronda_compras_1.md
│   ├── ronda_estadisticas_1.md
│   ├── orden_de_implementacion.md  qué tarea sigue, de las tres rondas nuevas
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
│   ├── costo_del_lote.md         costo acumulado y costo por planta sin asientos (lote 4, D-50)
│   ├── stock_maduro.md           stock maduro, reservas, períodos, cosecha, cámara y faltantes (comercial, D-59, D-64)
│   ├── enlace_del_cliente.md     el enlace de un solo uso que recibe un cliente sin cuenta (D-65)
│   ├── enlace_del_proveedor.md   el mismo patrón para el proveedor que cotiza sin cuenta (D-88)
│   └── asientos.md               cómo una operación genera su asiento automático (D-86)
├── casos_de_uso/
│   ├── _plantilla.md             encabezado y secciones de un extracto
│   ├── usuarios.md, auditoria.md (quedan donde están)
│   └── <app>/<tema>.md           extractos de «CU extendidos». Los que cite la tarea
├── modelo/
│   ├── README.md                 encabezado de un extracto del modelo
│   └── <app>.md                  extracto del modelo y del glosario. Los que cite la tarea
└── prototipos/
    ├── cuentas_y_seguridad.html  (queda donde está: D-24 lo nombra con esta ruta)
    ├── produccion/
    │   ├── README.md             qué función arma cada pantalla y qué es «solo prototipo»
    │   ├── datos_maestros_y_produccion.html
    │   └── logistica_transportista.html   (MAE-05, D-55)
    ├── comercial/
    │   ├── README.md             ídem, con la línea de cada sobrescritura (ronda «Comercial 1»)
    │   └── comercial_y_cosecha.html
    ├── iot/
    │   ├── README.md             ídem, con la línea de cada función (ronda «IoT 1»)
    │   └── iot.html              el prototipo del IoT v8.5
    └── compras_contabilidad/
        ├── README.md             ídem, rondas nuevas (contabilidad, compras, estadísticas)
        ├── nota_de_cobertura.md  qué pantalla cumple cada caso de uso
        └── compras_contabilidad_y_estadisticas.html
```

Fuera de `docs/`, el esquema también cambia `CLAUDE.md`, `.claude/rules/pruebas.md`, `.claude/rules/interfaz.md` y
`.claude/settings.json`.

## Ciclo de una tarea

1. **Documentar la ronda** (una persona, o Claude en claude.ai), por lotes pero con el plan completo desde el primero: el plan
   de la ronda (`tareas/ronda_<nombre>.md`, por ejemplo `ronda_produccion_1.md`), los archivos de tarea en `tareas/<app>/` con la plantilla, los extractos
   que nombran en «Leer» (`casos_de_uso/<app>/`, `modelo/<app>.md`), los patrones y los disparadores. El estudiante aprueba
   cada lote antes de programarlo (**M6**) y las tareas figuran en `tareas/README.md`.
2. **Planificar y programar** (Claude Code): lee `estado.md`, la tarea y solo lo que ella lista. Un plan por tarea, aprobado
   una vez; después hace todos sus pasos de corrido. Frena solo en L7 y L9 y, en los pasos de servicios, para que el
   estudiante revise las pruebas que fallan.
3. **Verificar y cerrar** (Claude Code propone, el estudiante aplica): antes de cerrar, Claude Code verifica la tarea (recorrido con el cliente de Django, verificación visual con
   Playwright si hay pantallas y revisión de la migración: `patrones/verificacion_por_claude.md`) y completa «Cierre» y «Verificación» (con los «Pasos para replicar», opcionales) en la tarea; propone el `estado.md` nuevo, la fila del índice de tareas,
   una línea para `historial.md`, las decisiones nuevas, los disparadores cumplidos o nuevos y lo que quedó distinto de lo escrito (`temas_abiertos.md`). El paso «Cierre de documentación» de
   cada tarea es esa misma propuesta (**M3**).
4. **Revisar antes de mergear** (el estudiante): que el CI esté en verde y leer la lista «No pude verificar» del «Cierre»; si la tarea toca pantallas, mirar una. Claude Code le da, al final de la ronda, los «Pasos para replicar» con mucho detalle:
   son opcionales (D-95). Ya no hay revisiones a mano pendientes (la regla **M5** y `revisiones_pendientes.md` quedaron congeladas; lo anotado ahí es historial).

La regla M6 es de las personas, no de Claude Code: por eso está acá y no en `CLAUDE.md` (que tiene M1 a M4, las del cierre de una tarea).

## Prompt para pedirle una tarea a Claude Code

Es el mismo para cualquier tarea. Reemplazá `<ID>`, `<app>` y `<rama>` (los dos últimos, del encabezado del archivo de la
tarea) y pegalo como primer mensaje de una conversación nueva, con la rama ya creada desde `main` actualizado. Los
comandos de `CLAUDE.md` están escritos para PowerShell en Windows; en macOS o Linux, agregá al final: «Estoy en
macOS/Linux: usá `.venv/bin/python` en lugar de `.venv/Scripts/python.exe`».

```
Implementá la tarea <ID> (docs/tareas/<app>/<ID>-*.md). Ya estoy en la rama
<rama>, creada desde main actualizado.

Antes de editar:
- Leé CLAUDE.md, docs/estado.md y el archivo de la tarea, y después solo lo que
  su sección «Leer» indica, y solo las secciones nombradas (L3).
- Verificá que las tareas de «Depende de» estén hechas y mergeadas en main
  (docs/tareas/README.md y docs/historial.md). Si alguna no lo está, frená y avisame.
- Proponeme el plan: los pasos de la tarea y los archivos que vas a tocar.
  Esperá mi aprobación.

Durante la implementación:
- Seguí los pasos en orden y corré las pruebas de cada paso antes de seguir.
- En los pasos de servicios, escribí primero las pruebas de sus reglas, mostrá que
  fallan y esperá que las revise (.claude/rules/pruebas.md). Fuera de eso, no me
  pidas permiso paso por paso.
- Respetá «Límites»: nada fuera de «Permitido fuera de la app», ningún modelo
  ni migración que no esté listado, ninguna dependencia nueva.
- Si algo no está en «Leer» o dos documentos se contradicen, frená y avisame en
  lugar de inventar (L7, L9). Si sentís que el contexto no alcanza para terminar,
  decimelo antes de empezar el paso siguiente.

Al terminar:
- Corré todos los comandos de pruebas de «Hecho cuando» y mostrá el resultado (M1).
- Completá «Cierre» y «Verificación a mano» en el archivo de la tarea (M2).
- Del paso «Cierre de documentación» y de M3, mostrame los cambios propuestos sin
  aplicarlos; los aplico yo.
- No hagas commits, push ni PR. Proponeme el mensaje de commit (M4) y el texto del
  PR: qué hiciste, qué difiere de la documentación y qué pasos de la
  «Verificación a mano» tengo que hacer yo.
```

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
