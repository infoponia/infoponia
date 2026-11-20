# PRD-04 · Poner sector fuera de servicio, cierre de registros y Inicio del Agrónomo

Estado: pendiente | App: produccion (con dos piezas chicas en maestros y una sección de inicio en core) | Rama: feature/prd-04-sector-fuera-de-servicio | Ronda: Producción 1

Depende de: PRD-03 (reparto, bitácora, `aplicar_merma` con `por_sector` y `Bitacora.sectores`), PRD-02 (`aplicar_merma`, concretar y cancelar transición) y PRD-01 (`cancelar_orden_incluida`, ocupaciones, bloqueos). Si alguna no está hecha y mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es **la última tarea de la ronda** y la que cierra los registrantes que `maestros` dejó sin respuesta (vuelta a servicio, baja de sector y de invernadero) más el Inicio del Agrónomo.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-PNR-FDS | Poner Sector Fuera de Servicio | docs/casos_de_uso/produccion/sector_fuera_de_servicio.md | **Fuera de la ronda (D-45):** asientos de las mermas (precondiciones c y d), movimiento «salida por merma», condición 1 de plantas comprometidas, extensión 15b (D-42); el hardware del sector no se toca |
| (sin código) | Inicio del Agrónomo | — | No es un caso de uso: sección de inicio con indicadores (D-51 punto 10) |

## Leer

- Casos de uso: el extracto de la tabla, completo, **incluida la sección «Cómo se aplica en la ronda»**; en `docs/casos_de_uso/maestros/` (MAE-03): PROD-MOD-SCT (vuelta a servicio) y PROD-BAJ-SCT (baja de sector), solo lo que menciona el extracto
- Modelo: docs/modelo/produccion.md — `FueraDeServicio`, `Reubicacion`, `OcupacionSector`, `Merma`, `Lote`, `OrdenTrabajo`, `ReservaInsumo` y «Cambios a las fichas del lote 4 por el lote 5»; docs/modelo/maestros.md — `SectorProduccion`
- Decisiones: D-05, D-24, D-28, D-29, D-30, D-32, D-36, D-37, D-40, D-42, D-43, D-44, D-45, D-47, D-50, **D-51**, **D-52**
- API: docs/api/produccion.md (secciones 3 y 6), docs/api/extensiones_de_maestros.md, docs/api/alertas.md, docs/api/notificaciones.md
- Patrones: docs/patrones/bloqueos.md (sección `produccion`, orden de la fuera de servicio), docs/patrones/costo_del_lote.md, docs/patrones/auditoria.md, docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/datos_maestros_y_produccion.html — `VIEWS.fs`, `fsCalc`, `ultimoAviso`, `VIEWS.inicio`, `alertasInv`, `alertasMerma`. Solo guía visual (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: todo `produccion/`; maestros/servicios/sectores.py (`avisos_de_cambio_de_tipo`, `bloquear_sectores`, `agujeros_de`), maestros/extensiones.py; core/extensiones.py (`registrar_seccion_de_inicio`) y el Inicio del Gerente de MAE-02b como modelo

## Límites

- Crea modelos: `FueraDeServicio(Bitacora)` y `Reubicacion(Bitacora)` (fichas de `docs/modelo/produccion.md`) → revisá docs/disparadores.md
- Migraciones: solo nuevas. En `produccion`: una de esquema (`0004_fuera_de_servicio`) que depende de `0003_aplicaciones`: las dos tablas; `OcupacionSector.reubicacion` (clave nula) y `OcupacionSector.orden` **pasa a nula** con la restricción «exactamente una de las dos» (D-51 punto 1); el tipo de evento `reubicacion` y `fuera_de_servicio` si faltaban. En `core`: una de `choices`. **Ninguna de datos**
- Permitido fuera de la app, **y nada más**: `maestros/servicios/sectores.py`, solo la función nueva `pasar_a_fuera_de_servicio(sector)` (cambia `estado_sector` y nada más: no audita ni valida el rol); `maestros/extensiones.py`, solo el punto nuevo `registrar_efecto_de_baja_de_sector(funcion)` y su llamada en la baja de sector (postcondición b de PROD-BAJ-SCT), con su prueba en maestros; `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`: `fuera_de_servicio_sector`) y su migración. Documentá los dos cambios de maestros en `docs/api/extensiones_de_maestros.md`
- Dependencias nuevas: ninguna
- Fuera de alcance: cosechas; asientos; hardware (módulo IoT); Inicio del Capataz (ya está en PRD-01) y del Gerente (MAE-02b); un caso de uso nuevo para el Inicio

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, migración y auditoría.** `FueraDeServicio` (único registro abierto por sector: restricción con condición `fecha_fin` nula), `Reubicacion`, el cambio de `OcupacionSector` con la restricción «exactamente una», y la acción `fuera_de_servicio_sector`. Pruebas: `test_modelos_fds.py` (la restricción; que la migración conserva las ocupaciones existentes, todas con `orden`; un solo registro abierto por sector) con `@tag("migracion")` donde corresponda.
2. **Piezas de maestros.** `pasar_a_fuera_de_servicio(sector)` y `registrar_efecto_de_baja_de_sector`, con sus pruebas en `maestros`. Si algo de esto obliga a tocar más de lo permitido, frená.
3. **Lectura.** `sectores_para_fuera_de_servicio(actor)`, `detalle_de_sector`, `fecha_minima_fuera_de_servicio(sector)` (la mayor entre la última activación derivada de la auditoría y del último `fecha_fin`, la llegada de cada lote y su último registro de bitácora), `destinos_elegibles(sector, lotes)`. Pruebas: `test_fds_lectura.py` (fecha mínima en cada caso; destinos por tipo de etapa, perfil familiar y agujeros libres, sin contar los de las órdenes que se cancelan; un lote por destino y varios al mismo destino).
4. **Poner fuera de servicio** (PROD-PNR-FDS): `resumen_de_fuera_de_servicio(actor, datos)` y `poner_fuera_de_servicio(actor, datos)`. Orden dentro de la transacción: verificar → reubicaciones y ocupaciones → mermas con `aplicar_merma(..., sector_ids=[sector], ordenes_excluidas=...)` → puesta en cero de la ocupación de origen → cancelación de órdenes con `cancelar_orden_incluida(..., avisar=False)` → `pasar_a_fuera_de_servicio` → `FueraDeServicio` → **una** notificación al Capataz → **un** registro `fuera_de_servicio_sector`. Bloqueos en el orden de `docs/patrones/bloqueos.md`; el sector de origen se bloquea **antes** de cambiar su estado. Pruebas: `test_prod_pnr_fds.py` y `test_fds_concurrencia.py` (ver el extracto; incluye poner fuera de servicio contra una merma y contra concretar una transición).
5. **Registrantes.** `registrar_efecto_de_vuelta_a_servicio` (cierra el registro y escribe la bitácora `otro_evento`), `registrar_efecto_de_baja_de_sector` y `registrar_efecto_de_baja` (cierra los registros abiertos de los sectores del invernadero). Pruebas: `test_fds_registrantes.py` (cada punto con y sin registro abierto; que el registro del sector es el mismo antes y después; que la baja del invernadero sigue sin lotes ni órdenes como pide PRD-01).
6. **Inicio del Agrónomo.** `inicio.indicadores_del_agronomo(actor, invernadero_ids)` y su registro con `registrar_seccion_de_inicio`: lotes activos, órdenes «a realizar» vencidas, ocupación (agujeros ocupados sobre el total) y **insumos por vencer**, que se cuentan como las alertas activas del tipo `inv_insumo_por_vencer` destinadas al actor (`Alerta.objects.para(actor)`): no hay función nueva en `inventario` y **no hay que crearla**; si te parece que falta, frená y avisá. Una consulta por indicador, no por invernadero. Pruebas: `test_inicio_agronomo.py` (cada indicador; el Agrónomo ve solo los suyos; sin invernaderos, la sección dice cómo empezar; `assertNumQueries`).
7. **Pantallas** (HTMX con respaldo sin JavaScript, D-24, D-29, D-47): el flujo «Poner fuera de servicio» en pasos (sector → detalle, fecha y motivo → por lote, destinos y cantidades → causa de la merma por lote → resumen → confirmar), con entrada desde la ficha del sector y desde el aviso de la baja del sector (MAE-03); formulario deshabilitado con su motivo si no hay sectores activos; la sección de inicio. Pruebas: `test_fds_vistas.py` (solo el Agrónomo a cargo; 404 para el resto; errores por campo; escape de HTML; respaldo sin JavaScript).
8. **Cierre de documentación.** Proponé, sin aplicarlos (M3): cerrar en `docs/disparadores.md` todo lo de PRD-04 (los registrantes, el hueco de la baja de sector y el Inicio del Agrónomo); marcar PRD-04 en `docs/tareas/README.md`, `docs/tareas/ronda_produccion_1.md` y `docs/estado.md`; con esta tarea **la ronda «Producción 1» queda completa**. Para `docs/temas_abiertos.md`, proponé anotar lo que implementaste distinto de lo escrito.

Si el tiempo apremia, lo último que se recorta es: el indicador de ocupación del Inicio. Las reglas de la fuera de servicio, los bloqueos, los registrantes y el todo o nada **no se recortan**. Si la tarea no entra en una sesión, el corte limpio es entre el paso 5 y el 6 (el Inicio es independiente); avisá antes de partirla.

## Hecho cuando

- PROD-PNR-FDS está implementado con una prueba por regla y por postcondición a a k, con sus pruebas de vista y de concurrencia.
- Poner un sector fuera de servicio lo deja sin agujeros ocupados ni comprometidos, con cada lote reubicado o dado de baja como merma, las órdenes afectadas canceladas y **un** registro de auditoría `fuera_de_servicio_sector`; la etapa y la fecha de entrada de los lotes no cambian.
- Volver a servicio, dar de baja el sector o el invernadero cierra el registro «Fuera de servicio» abierto.
- El Inicio del Agrónomo muestra sus indicadores con consultas constantes.
- Comando de pruebas:
  python manage.py test produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test produccion --keepdb --tag concurrencia
  python manage.py test produccion --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate` (en `produccion` y `core`). Hace falta un invernadero con tres sectores de Germinación, un lote con plantas en uno de ellos, otro sector con lugar, una siembra «a realizar» con agujeros comprometidos en el sector, el Agrónomo a cargo y el Capataz.

1. `migrate` pasa sin errores, con ocupaciones existentes.
2. «Poner fuera de servicio»: solo se ofrecen sectores activos del invernadero del Agrónomo. La fecha mínima se explica si la fecha elegida es anterior.
3. Reubicar las plantas del lote a otro sector: se ofrecen solo destinos del mismo tipo de etapa, con perfil compatible y lugar. Dejar plantas sin reubicar pide la causa por lote (sin «descarte por selección»); el resumen muestra la merma, las órdenes que se cancelan y el aviso si es el último sector de su tipo.
4. Confirmar: el sector queda «fuera de servicio» sin ocupados ni comprometidos; el lote conserva su etapa y su fecha de entrada y tiene una ocupación nueva en el destino; la merma (si hubo) está en la bitácora; la siembra quedó cancelada con su motivo y sus reservas liberadas; el Capataz recibe **una** notificación. «Auditoría» tiene **un** registro `fuera_de_servicio_sector`.
5. Volver a poner el sector en servicio (MAE-03): el registro «Fuera de servicio» se cierra con la fecha de hoy y la bitácora lo cuenta con los días que estuvo fuera.
6. Dar de baja un sector que está fuera de servicio y la baja de un invernadero sin lotes con sectores en ese estado: se cierran los registros.
7. Sector sin plantas ni órdenes: solo cambia de estado, sin reubicaciones ni mermas.
8. Dos Agrónomos (o dos pestañas) ponen fuera de servicio el mismo sector, o uno lo pone mientras el Capataz concreta una transición sobre él: una sola gana y la otra ve el estado actual, sin 500.
9. Inicio del Agrónomo: lotes activos, órdenes vencidas, ocupación e insumos por vencer coinciden con las pantallas de origen.
10. Sin JavaScript, los pasos 2, 3, 4 y 5 funcionan igual.
11. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
