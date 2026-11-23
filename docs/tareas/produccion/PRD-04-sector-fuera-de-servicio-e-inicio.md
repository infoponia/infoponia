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
4. **Poner fuera de servicio** (PROD-PNR-FDS): `resumen_de_fuera_de_servicio(actor, datos)` y `poner_fuera_de_servicio(actor, datos)`. Orden dentro de la transacción: verificar → reubicaciones y ocupaciones → mermas con `aplicar_merma(..., sector_ids=[sector], ordenes_excluidas=...)` → puesta en cero de la ocupación de origen → cancelación de órdenes con `cancelar_orden_incluida(..., avisar=False)` (el motivo compuesto «Sector fuera de servicio: <sector>. <motivo>» se recorta a 300 con «…»: ver `cancelar_orden.md`) → `pasar_a_fuera_de_servicio` → `FueraDeServicio` → **una** notificación al Capataz → **un** registro `fuera_de_servicio_sector`. Bloqueos en el orden de `docs/patrones/bloqueos.md`; el sector de origen se bloquea **antes** de cambiar su estado. Pruebas: `test_prod_pnr_fds.py` y `test_fds_concurrencia.py` (ver el extracto; incluye poner fuera de servicio contra una merma y contra concretar una transición).
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

Hay dos migraciones nuevas (`core` 0023 y `produccion` 0004): `python manage.py migrate`. Los datos ya están cargados en la base local (`python manage.py cargar_datos_de_verificacion`, idempotente; la contraseña la pide el comando o sale de `INFOPONIA_CONTRASENA_DE_PRUEBA`). Cuentas: `agronomo@prueba4.local`, `capataz@prueba4.local` y tu Gerente. Invernadero «Verificación Fuera de Servicio»: «FDS Germinación 1» (con el lote de 40 plantas y una siembra «a realizar» de 20 plantines con 12 agujeros comprometidos ahí y 8 en «FDS Germinación 2»), «FDS Germinación 2» (con lugar, para reubicar), «FDS Germinación 3» (vacío) y «FDS Maduración» (ya fuera de servicio, con su registro abierto: sirve para los pasos 5 y 6). «Verificación Fuera de Servicio Baja»: sin lotes ni órdenes, con «FDS Baja Germinación» fuera de servicio (para dar de baja el invernadero con la cuenta del Gerente, paso 6). Las pantallas no se vieron en un navegador. Si probás los pasos 3 y 4 sobre «FDS Germinación 1», el estado queda cambiado: para repetirlos hace falta volver a activar el sector y los datos de la siembra no se recrean (la carga solo agrega lo que falta).

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

**Qué se hizo** (23/11/2026, rama `feature/prd-04-sector-fuera-de-servicio-e-inicio`):

- **Modelos y migraciones** (`produccion` 0004, `core` 0023): `FueraDeServicio(Bitacora)` (un solo registro abierto por sector; `fecha_efectiva` es una propiedad de `fecha_bitacora`) y `Reubicacion(Bitacora)`; `OcupacionSector.orden` pasa a nula, se suma `reubicacion` y la restricción «exactamente una de las dos» con los dos únicos condicionales; los tipos `fuera_de_servicio` y `reubicacion`; la acción `fuera_de_servicio_sector`. Ninguna migración de datos.
- **`maestros`**: solo `pasar_a_fuera_de_servicio(sector)` (el punto `registrar_efecto_de_baja_de_sector` y su llamada ya existían desde MAE-03) y dos plantillas con permiso explícito (ver abajo).
- **PROD-PNR-FDS** (`produccion/servicios/sectores_fuera_de_servicio.py`): `sectores_para_fuera_de_servicio`, `detalle_de_sector`, `fecha_minima_fuera_de_servicio`, `destinos_elegibles`, `resumen_de_fuera_de_servicio` y `poner_fuera_de_servicio` (todo o nada, una `Reubicacion` por lote, una sola `FueraDeServicio`, una notificación al Capataz y un registro `fuera_de_servicio_sector`).
- **Registrantes**: vuelta a servicio (cierra el registro y escribe un `otro_evento`), baja de sector y baja de invernadero (cierran el registro abierto); y la sección «Mi producción» del Inicio del Agrónomo (`produccion/servicios/inicio.py`).
- **Pantalla** «Poner fuera de servicio» (`/produccion/sectores/fuera-de-servicio/`), con entrada desde el menú ⋯ de la tarjeta del sector y desde la ventana de la baja con impedimentos; la consulta de bitácora ahora lista y filtra los dos tipos nuevos.
- **Cargador de verificación** ampliado (cuentas `prueba4`), solo con servicios.

**Pruebas** (M1): `produccion maestros inventario core` en paralelo, sin concurrencia ni migración: 3873 pruebas, OK. `produccion --tag concurrencia`: 45, OK (incluye las diez de `test_fds_concurrencia.py` y la que PRD-03 dejó pendiente, «merma contra poner el sector fuera de servicio»). `produccion --tag migracion`: 2, OK (la de `0004` conserva las ocupaciones con su `orden`). `makemigrations --check --dry-run` y `manage.py check`: sin cambios ni problemas. Pruebas nuevas: `test_modelos_fds`, `test_fds_lectura`, `test_prod_pnr_fds`, `test_fds_concurrencia`, `test_fds_registrantes`, `test_inicio_agronomo`, `test_fds_vistas`, `maestros/tests/test_pasar_a_fuera_de_servicio` y tres de `test_verificacion`.

**Contrato que aprobaste** (para quien use el servicio): `DatosDeFueraDeServicio(sector_id, motivo, fecha, reubicaciones=((lote, destino, plantas),…), causas=((lote, causa, descripcion),…), plantas_vistas, libres_vistos, ordenes_vistas)`. Los `*_vistos` en `None` operan sobre lo vigente bloqueado; informados (incluso vacíos), cualquier diferencia da `cambio_simultaneo` con `plantas`, `ordenes` y `libres` en `datos`. Códigos de error: `motivo_obligatorio`, `motivo_largo`, `fecha_invalida` (con `fecha_minima` y `origen`), `cantidad_invalida`, `sector_no_elegible`, `causa_obligatoria`, `causa_invalida`, `descripcion_larga`, `cambio_simultaneo`, `sin_permiso`, `invernadero_inactivo` y el nuevo `sector_no_activo`. Registrantes: `efecto_de_vuelta_a_servicio`, `efecto_de_baja_de_sector`, `efecto_de_baja_del_invernadero` y `seccion_de_inicio_del_agronomo`.

**Decisiones**: ninguna nueva (no hace falta `D-NN`). Interpretaciones y diferencias, todas para `docs/temas_abiertos.md`:

- **Agujeros libres de un destino**: la tarea dice «sin contar los de las órdenes que se cancelan» y el extracto, «no se cuentan como libres». Se tomó la lectura conservadora: lo que comprometen esas órdenes NO se cuenta como libre (el resultado no depende del orden y nunca se pasa de la capacidad).
- **Motivo de las órdenes canceladas**: «Sector fuera de servicio: <sector>. <motivo>» (la tarea y `cancelar_orden.md`); el extracto de PROD-PNR-FDS dice «Sector <nombre> fuera de servicio: <motivo>».
- **Inicio del Agrónomo**: sin el filtro por invernadero del prototipo (el punto de extensión de `core` solo recibe al usuario), con todos sus invernaderos activos juntos; «Insumos por vencer» cuenta solo las alertas activas `inv_insumo_por_vencer` (el prototipo suma también los vencidos).
- **Auditoría de la vuelta a servicio**: `modificacion_sector` (de `maestros`) no incluye el registro «Fuera de servicio» entre sus afectados: hacerlo exigiría tocar `maestros` más de lo permitido.
- **`maestros` fuera de lo listado**: se tocaron `maestros/templates/maestros/sectores/_tarjeta.html` y `_ventana_baja.html` (las entradas pedidas por la tarea y el extracto) con permiso explícito del estudiante.
- **Pruebas existentes que hubo que ajustar** (sin debilitar ninguna regla): `produccion/tests/test_modelos_aplicacion.py` (el tipo `fuera_de_servicio` pasa a ser válido y `reubicacion` también); `maestros/tests/test_extensiones_sectores.py` (las dos pruebas «sin registrantes» parchean la lista vacía: con `produccion` cargada hay un registrante real); `produccion/tests/test_registrantes_de_core.py` (el ayudante mira solo la sección del Capataz); `produccion/tests/test_prod_cns_bit.py` (la lista del filtro suma los dos tipos).
- **Bloqueos**: se siguió «Lote 5» de `bloqueos.md` (insumos de las reservas entre los sectores y los lotes, `Insumo` antes de `InsumoInvernadero`). Lo que se bloquea se decide después de tomar el invernadero, y la extensión 14a se evalúa después de todos los bloqueos.
- **Fecha mínima**: sin ningún registro de auditoría de alta o reactivación del sector (datos cargados a mano) ese componente no cuenta; la fecha mínima puede ser `None`.
- **Descripción de la `Reubicacion`** con las plantas por destino («… a Germinación 2 (25) y Germinación 3 (10).»).
- **Cargador**: el sector ya fuera de servicio del escenario es de Maduración (no de Crecimiento) porque el ciclo de la variedad de prueba es germinación → maduración y la siembra exige un sector de cada etapa; si quien verifica ya volvió a activar un sector, una nueva corrida no lo vuelve a sacar de servicio.
- **Documentación de la API**: `docs/api/produccion.md` debería sumar el código `sector_no_activo` y los nombres de los registrantes de PRD-04; `docs/api/extensiones_de_maestros.md` ya describía los dos cambios de `maestros` (el punto `registrar_efecto_de_baja_de_sector` existe desde MAE-03).

**Pantallas: lo que se corrigió del prototipo** (D-61):

- **Un solo formulario con resumen**: el prototipo recalcula todo al tipear (`data-live`) y arma los pasos con `S.step`. Acá nada se valida ni se calcula al escribir: elegir el sector solo redibuja (HTMX con `show:none`, o «Continuar» sin JavaScript); «Ver resumen» valida y «Confirmar» vuelve a verificar con todo bloqueado. Lo pide `.claude/rules/interfaz.md` y la extensión 14a.
- **Causa de la merma**: el prototipo la pide solo cuando quedan plantas sin reubicar (lo calcula al tipear). Acá se ofrece siempre por lote, con la leyenda «Obligatoria solo si quedan plantas sin reubicar», y el servidor la exige solo si hace falta.
- **Cambio simultáneo**: el prototipo lo simula (`simBox`); acá es real, con lo que la persona vio (`visto_*`) y la «firma» del resumen; si cambió, se muestra de nuevo con lo vigente.
- **Estados que el prototipo no tenía**: sin sectores activos (formulario deshabilitado con su motivo), lote sin destinos elegibles, sector vacío, sector que otra persona ya puso fuera de servicio, errores por campo, fecha mínima con su origen (extensión 6c) y el aviso de las órdenes por replanificar al volver a la ficha del invernadero.
- **Entradas**: el prototipo la tenía en la ficha del sector; se sumó también la ventana de la baja con impedimentos (lo pide el extracto).
- **Inicio**: se tomaron los cuatro indicadores del prototipo como tarjetas que enlazan a su pantalla de origen; sin filtro por invernadero (ver arriba) y con el estado «todavía no tenés invernaderos».

**Datos cargados para la verificación** (base local, con `cargar_datos_de_verificacion`; cuentas `agronomo@prueba4.local` y `capataz@prueba4.local`, y el Gerente de siempre): ver el primer párrafo de «Verificación a mano».
