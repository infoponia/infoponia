# PRD-03 · Eventos del lote: registrar merma, aplicación de insumos, otros eventos y consultar la bitácora

Estado: pendiente | App: produccion (con un punto de extensión de maestros y una restricción nueva en `Consumo`) | Rama: feature/prd-03-eventos-del-lote | Ronda: Producción 1

Depende de: PRD-02 (el núcleo `aplicar_merma` con la firma completa, `Merma`, `AlertaDeMerma`, bloqueos de `produccion`), y por ella PRD-01 (modelos, `Bitacora.sectores`, `Consumo`, pestañas de la ficha). Si alguna no está hecha y mergeada, frená. INV-02 debe tener `stock.existencias`, `proponer_lotes_fefo`, `registrar_salida_por_consumo` y `reevaluar_alertas_del_insumo`, y `insumos_invernadero.habilitados`.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). Es la tarea que le da al Agrónomo y al Capataz **todo lo que se registra sobre un lote o un invernadero sin cambiar su etapa**: pérdidas de plantas, aplicaciones de insumos y hechos sueltos, más la consulta que los muestra juntos.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-REG-MRM | Registrar Merma (lote en pie) | docs/casos_de_uso/produccion/merma.md | **Fuera de la ronda (D-45):** partidas de cámara (4a, 10c y postcondiciones f a j), asiento (e) y movimiento «salida por merma» (d), alerta de plantas comprometidas condición 1 |
| PROD-REG-APL | Registrar Aplicación de Insumos | docs/casos_de_uso/produccion/aplicacion_de_insumos.md | **Fuera de la ronda (D-45):** asiento (f) y precondiciones c y d (ejercicio y cuentas) |
| PROD-REG-EVT | Registrar Evento | docs/casos_de_uso/produccion/bitacora.md | — |
| PROD-CNS-BIT | Consultar Bitácora | docs/casos_de_uso/produccion/bitacora.md | Sin cosecha ni incumplimiento de cláusula (no existen todavía); sin auditoría (SEG-14) |

## Leer

- Casos de uso: los tres extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno
- Modelo: docs/modelo/produccion.md — `Bitacora`, `Merma`, `AlertaDeMerma`, `AplicacionInsumos`, `ImputacionCosto`, `Consumo`, `OcupacionSector`, `Lote` y «Cambios a las fichas del lote 4 por el lote 5»; docs/modelo/inventario.md — `InsumoInvernadero`, `LoteInsumo`, `MovimientoInsumo`, categorías de insumo
- Decisiones: D-05, D-24, D-28, D-29, D-30, D-32, D-36, D-37, D-40, D-42, D-43, D-44, D-45, D-47, D-50, **D-51**, **D-52**
- API: docs/api/produccion.md (secciones 3 y 6), docs/api/stock.md, docs/api/alertas.md, docs/api/extensiones_de_maestros.md (`registrar_pestana_de_invernadero`)
- Patrones: docs/patrones/bloqueos.md (sección `produccion`), docs/patrones/costo_del_lote.md (incluido el reparto en centavos), docs/patrones/stock.md, docs/patrones/auditoria.md, docs/patrones/abm.md, docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/datos_maestros_y_produccion.html — `VIEWS.merma`, `mrCalc`, `mermaInfo`, `aplicarMerma` (solo lote en pie), `VIEWS.aplic`, `apCalc`, `reparto`, `fefo`, `bitTab`, `VIEWS['bit-reg']`, `VIEWS.evento`. Solo guía visual: lo que difiera de los CU lo decide el CU (L7)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: todo `produccion/` (en particular `servicios/mermas.py` de PRD-02, `costos.py`, `errores.py`, bloqueos), inventario/servicios/stock.py y alertas_de_stock.py, maestros/alertas.py

## Límites

- Crea modelos: `AplicacionInsumos(Bitacora)` e `ImputacionCosto` (fichas de `docs/modelo/produccion.md`) → revisá docs/disparadores.md («Cuando exista Lote, OrdenTrabajo o StockCosechado»)
- Migraciones: solo nuevas. En `produccion`: una de esquema (`0003_aplicaciones`) que depende de `0002_transicion_y_merma`: las dos tablas; el campo `Consumo.aplicacion` (clave nula); el **reemplazo** de la restricción «`siembra` no nula» por «exactamente una de `siembra` y `aplicacion`» (D-51 punto 3); y los tipos de evento `aplicacion`, `otro_evento` y `consumo` si aún no estaban en las `choices`. En `core`: una de `choices` (acciones nuevas). **Ninguna de datos**
- Permitido fuera de la app: `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`: `registro_aplicacion`, `registro_evento`; `registro_merma` ya existe) y su migración; `maestros/alertas.py` **no se toca** (los tipos de alerta ya los registró PRD-02); la pestaña «Bitácora» se registra con `registrar_pestana_de_invernadero` (ya existe, lote 4)
- Dependencias nuevas: ninguna
- Fuera de alcance: poner un sector fuera de servicio y su Inicio (PRD-04); cosecha, incumplimiento de cláusula, partidas en cámara, asientos y movimiento «salida por merma» (D-45); la cuenta «Gastos de Producción» (MD-90); el aviso de insumos vencidos usados (queda como está)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos, migración y auditoría.** `AplicacionInsumos`, `ImputacionCosto` (único `(consumo, lote)`; la suma por consumo es el monto del consumo), `Consumo.aplicacion` con la restricción nueva; las dos acciones de auditoría con etiquetas y migración de `choices`. Pruebas: `test_modelos_aplicacion.py` (la restricción «exactamente una»; que la migración reemplaza a la de PRD-01 con una siembra existente; unicidad de la imputación; los movimientos del consumo de una aplicación llevan `origen` = el consumo, sin tabla de enlace, D-52).
2. **Reparto del costo.** `costos.repartir_en_centavos(monto, plantas_por_lote)` según `docs/patrones/costo_del_lote.md` (centavos, resto mayor, empates por id). Pruebas: `test_repartir_en_centavos.py` con los cinco ejemplos del patrón y la propiedad (la suma da **exactamente** el monto; ninguna parte negativa; lotes con 0 plantas no reciben).
3. **Registrar Merma** (PROD-REG-MRM): `lotes_con_merma_posible(actor, invernadero_id)`, `datos_de_merma`, `resumen_de_merma` y `registrar_merma(actor, datos)` sobre `aplicar_merma` con `por_sector`; `merma_acumulada(lote)`. Bloqueos: cuentas → invernadero → variedad → sectores con pérdidas → lote → ocupaciones. Cantidades por sector entre 0 y los agujeros ocupados, total ≥ 1; causa obligatoria (incluye «descarte por selección»); fecha de hoy; 10d con `cambio_simultaneo`. Un registro `registro_merma`. Pruebas: `test_prod_reg_mrm.py` y `test_merma_concurrencia.py` (ver el extracto; incluye merma contra concretar transición).
4. **Registrar Aplicación de Insumos** (PROD-REG-APL): `insumos_aplicables`, `resumen_de_aplicacion` y `registrar_aplicacion`. Alcance (todo o sectores activos), FEFO y su corrección, faltante sin lote, valor, destino del costo y reparto, `AplicacionInsumos` con un `Consumo` interno por insumo, movimientos de insumo con `origen` = el consumo (el `Consumo` se crea **antes** de la salida de stock, `registrar_salida_por_consumo(..., origen_id=...)`), imputaciones, `reevaluar_alertas_del_insumo`. **El Capataz no recibe valores, destinos ni avisos de stock: los servicios no los devuelven.** Bloqueos y concurrencia (12a) como el extracto. Un registro `registro_aplicacion`. Pruebas: `test_prod_reg_apl.py`, `test_aplicaciones_concurrencia.py`.
5. **Registrar Evento** (PROD-REG-EVT): `datos_de_evento` y `registrar_evento(actor, datos)`. Pruebas: `test_prod_reg_evt.py` (incluida la que verifica que no existen vistas de edición ni de baja de un registro de bitácora).
6. **Consultar Bitácora** (PROD-CNS-BIT): `invernaderos_de_bitacora(actor)` y `consultar_bitacora(actor, invernadero_id, filtros, pagina)`: sin el tipo interno `consumo`, filtros combinables, de a 50, **sin consultas por fila**. Pruebas: `test_prod_cns_bit.py` con `assertNumQueries` constante.
7. **Pantallas** (HTMX con respaldo sin JavaScript, D-24, D-29, D-47): «Registrar merma» y «Registrar aplicación» en pasos para celular, «Registrar evento», la pestaña «Bitácora» de la ficha del invernadero (con los botones «Registrar evento» y «Registrar aplicación» ya con el invernadero elegido, extensión 1a) y las entradas de menú según el rol (Agrónomo: dentro de «Producción»; Capataz: merma, aplicación y evento; Gerente: solo la consulta de bitácora). Formularios deshabilitados con su motivo si no hay lotes activos o insumos aplicables. Pruebas: `test_eventos_vistas.py` (permisos por rol, 404 donde corresponde, errores por campo, escape de HTML, **que la respuesta del Capataz no contiene valores en dinero** y el respaldo sin JavaScript).
8. **Cierre de documentación.** Cerrar lo que corresponda en `docs/disparadores.md`; marcar PRD-03 en `docs/tareas/README.md`, `docs/tareas/ronda_produccion_1.md` y `docs/estado.md`. Anotá en `docs/temas_abiertos.md` lo que implementaste distinto de lo escrito.

Si el tiempo apremia, lo último que se recorta es: el filtro por texto y por rango de fechas de la bitácora (los de tipo, lote y sector quedan). Las reglas de los servicios, el reparto en centavos, los bloqueos, que el Capataz no reciba valores y el todo o nada **no se recortan**. Si la tarea no entra en una sesión, el corte limpio es entre el paso 4 y el 5; avisá antes de partirla.

## Hecho cuando

- Los cuatro casos de uso están implementados con una prueba por regla y por postcondición (menos las contables), con sus pruebas de vista y de concurrencia.
- Una merma de lote en pie baja la cantidad, el costo total (no el unitario) y los agujeros ocupados, y deja el lote `finalizado` con costo 0 si llega a cero; las alertas se crean una sola vez; hay **un** registro `registro_merma`.
- Una aplicación descuenta el stock por lote de insumo, imputa el costo a los lotes con plantas en el alcance con una suma exacta o lo manda a gasto, y deja **un** registro `registro_aplicacion`; nada de esto se le muestra al Capataz.
- La bitácora lista todo lo que escribieron PRD-01 a PRD-03 con descripciones legibles, sin consultas por fila y sin escribir auditoría.
- Comando de pruebas:
  python manage.py test produccion maestros inventario core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test produccion --keepdb --tag concurrencia
  python manage.py test produccion --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay una migración nueva: `python manage.py migrate` (en `produccion` y `core`). Hace falta lo de PRD-02 más un lote activo con plantas en dos sectores, insumos habilitados en el invernadero (uno con vencimiento, uno como «costo de los lotes» y uno como «gasto»), el Agrónomo a cargo y el Capataz.

1. `migrate` pasa sin errores, también con una siembra ya creada.
2. «Registrar merma» (Capataz): solo ofrece lotes activos; cantidades por sector que no pasan de lo ocupado; sin causa, error; con total 0, error. Confirmar: el lote baja su cantidad, el **costo por planta queda igual**, aparece en la bitácora («Merma de N plantas por …»). «Auditoría» tiene **un** `registro_merma`.
3. Una merma que lleve la acumulada sobre el 15 % crea la alerta de umbral una sola vez; «descarte por selección» no suma. Una merma que deje a una transición «a realizar» con más plantas que las del lote crea la alerta de plantas comprometidas.
4. Una merma que deje el lote en cero lo pasa a «finalizado», con costo 0.
5. «Registrar aplicación» (Capataz): elegir sectores o todo el invernadero; se ofrecen solo insumos habilitados y con consumo directo; el reparto FEFO se propone y solo se corrige en insumos con vencimiento. **No se ve ningún valor en dinero.** Confirmar descuenta el stock y aparece en la bitácora.
6. La misma aplicación como Agrónomo: el resumen muestra el valor, el destino y el reparto entre lotes; el insumo «como costo de los lotes» sube el costo de los lotes del alcance (la suma de las partes es exacta al centavo); «como gasto» no imputa; sin lotes en el alcance va a gasto y avisa.
7. Aplicar más que el stock: se registra, sale del faltante sin lote y el Agrónomo (no el Capataz) recibe la alerta «stock inconsistente».
8. «Registrar evento»: sin descripción, error; con 501 caracteres, error; con lote y sector opcionales. No hay forma de editarlo ni borrarlo.
9. Pestaña «Bitácora» del invernadero (Agrónomo y Gerente): orden del más reciente al más antiguo, agrupado por día; las aplicaciones muestran sus insumos adentro y los consumos internos no aparecen; los filtros se combinan; «Quitar filtros» funciona. El Capataz no ve la pestaña.
10. Dos personas registran mermas a la vez sobre el mismo lote: el lote nunca queda negativo y la otra ve el error, sin 500. Dos aplicaciones a la vez sobre el último lote de insumo: una gana.
11. Sin JavaScript, los pasos 2, 5, 6 y 8 funcionan igual.
12. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
