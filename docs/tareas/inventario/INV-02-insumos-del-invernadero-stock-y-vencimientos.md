# INV-02 · Insumos del invernadero, existencias, ajuste de stock y vencimientos

Estado: pendiente | App: inventario | Rama: feature/inv-02-existencias-y-stock | Ronda: Producción 1

Depende de: INV-01 (modelos, extensiones y catálogo; y por ella CON-01), UI-01 y NOT-01 (la campana ya muestra alertas). Si alguna no está hecha, frená.
MAE-02a y MAE-02b (alertas y su Inicio) ya están hechas.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso
paso por paso. Si algo que necesitás no está en «Leer», frená (L9). **Es la tarea más larga de `inventario`**: el ajuste de stock tiene
seis motivos y un recuento por lote; si el tiempo apremia, mirá el final de «Pasos».

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-HAB-IIN | Habilitar Insumo en Invernadero | docs/casos_de_uso/inventario/insumo_invernadero.md | La alerta «bajo el mínimo» al habilitar; tránsito = 0 (D-45) |
| CMP-MOD-IIN | Modificar Insumo en Invernadero | docs/casos_de_uso/inventario/insumo_invernadero.md | — |
| CMP-DSH-IIN | Deshabilitar Insumo en Invernadero | docs/casos_de_uso/inventario/insumo_invernadero.md | Orden de compra y pedidos en curso por punto de extensión (`compras`) |
| CMP-CNS-IIN | Consultar Existencias de Insumos | docs/casos_de_uso/inventario/insumo_invernadero.md | Es la pestaña «Existencias de insumos» del prototipo |
| CMP-AJT-STK | Ajustar Stock de Insumo | docs/casos_de_uso/inventario/ajuste_de_stock.md | **Sin asientos contables (D-45)**: las precondiciones c y d, la postcondición e y el asiento del paso 14 no se implementan; el valor del ajuste sí se muestra |
| CMP-REV-VNC | Revisar Vencimientos de Insumos | docs/casos_de_uso/inventario/vencimientos.md | Comando de Django que corre como cron job de Render |

Además crea la **API de stock** que usa `produccion` (`docs/api/stock.md`): `existencias`, `disponible_para_planificar`, `proponer_lotes_fefo`,
`registrar_salida_por_consumo`, `reevaluar_alertas_del_insumo` y `habilitar_insumo`.

## Leer

- Casos de uso: los tres extractos de la tabla, completos, **incluida la sección «Cómo se aplica en la ronda»** de cada uno
- Modelo: docs/modelo/inventario.md — las cinco fichas y «Diferencias con el caso de uso»
- Decisiones: D-05, D-14, D-22, D-27, D-28, D-30, D-32, D-36, D-37, D-40, D-41, D-42, D-44, D-45, D-46, D-47
- API: docs/api/stock.md, docs/api/extensiones_de_inventario.md, docs/api/alertas.md, docs/api/notificaciones.md
- Patrones: docs/patrones/stock.md (todo), docs/patrones/abm.md, docs/patrones/bloqueos.md, docs/patrones/auditoria.md,
  docs/patrones/trabajo_en_paralelo.md
- Pantallas: docs/prototipos/produccion/ — `VIEWS.insumos`, `existTab`, `MODALS.habilitar`, `habErrs`, `MODALS['ex-form']`, `exErrs`,
  `MODALS['ex-baja']`, `MOTIVOS`, `ajCalc`, `VIEWS.ajuste` y las funciones de cálculo de `stock`, `libreAl`, `vencidos`, `porVencer`,
  `bajoMin`, `incons`, `sinCobertura` (solo guía visual; lo que difiera de los CU lo decide el CU, L7: sobre todo el **recuento por lote
  completo** y la definición de «sin cobertura»)
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md
- Código a leer: lo que dejó INV-01 en `inventario/` (modelos, extensiones, fábricas, servicios de insumos), maestros/extensiones.py,
  maestros/servicios/alertas.py, maestros/servicios/invernaderos.py (`bloquear_invernadero_activo`), core/notificaciones.py y
  core/extensiones.py (fuentes de alertas de la campana), core/tests/concurrencia.py

## Límites

- Crea modelos: ninguno (los dejó INV-01) | si falta una columna de las fichas, frená y avisá
- Migraciones: solo nuevas, en `inventario`, **solo si hace falta** (no debería: el esquema ya está). Con una de `core` si se agregan
  acciones de auditoría (choices)
- Permitido fuera de la app: `core/models.py` (solo `Accion`, `ETIQUETAS`, `VALORES_VISIBLES` y `ACCIONES_DE_NEGOCIO`:
  `habilitacion_insumo_invernadero`, `modificacion_insumo_invernadero`, `ajuste_stock`, `alerta_de_vencimiento`), su migración,
  `core/menu.py` (si hace falta), `inventario/apps.py` (para registrar en `maestros`), y los textos de cierre de
  `docs/disparadores.md`, `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md`
- Dependencias nuevas: ninguna
- Fuera de alcance: asientos contables y sus precondiciones (D-45); pedidos, órdenes de compra y recepciones; el consumo de insumos por
  órdenes y aplicaciones (`produccion` llama a `registrar_salida_por_consumo`); las pantallas de alertas y la campana (NOT-01 y MAE-02c);
  las variedades y su semilla (INV-03); crear el cron job en Render (es manual, ver «Verificación a mano»)

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Lectura de stock y alertas.** Completar `inventario/servicios/stock.py` con `existencias`, `disponible_para_planificar`,
   `proponer_lotes_fefo` y `ordenes_sin_cobertura` según `docs/patrones/stock.md` (sección 1 y 2), y `inventario/servicios/alertas_de_stock.py`
   con `reevaluar_alertas_del_insumo` y las descripciones. Una consulta por tabla para toda la lista de ids. Pruebas:
   `test_stock_lectura.py` (cada fórmula de la sección 1, con lotes vencidos, por vencer, sin vencimiento, faltante sin lote, reservas
   falsas y fechas futuras; el borde del día de vencimiento; sin consultas por fila con `assertNumQueries`) y `test_alertas_de_stock.py`
   (crea, no duplica, resuelve; mínimo 0 no alerta; inactivo resuelve (el `InsumoInvernadero` o el insumo del catálogo); invernadero inactivo no crea; sin Agrónomo va al Gerente).
2. **Auditoría en `core`.** Las acciones de «Límites», con sus etiquetas y clasificación, y su migración de `choices`. Pruebas: la de
   clasificación (D-36) sigue pasando.
3. **Servicios de `InsumoInvernadero`** en `inventario/servicios/insumos_invernadero.py`: `habilitar_insumo`, `modificar_insumo_invernadero`,
   `deshabilitar_insumo`, `consultar_existencias`, `habilitados`, `acciones_permitidas`. Bloquean el invernadero (`bloquear_invernadero_activo`) antes
   de tocar nada, verifican que esté **a cargo del actor** y vuelven a leer. HAB reactiva el registro anterior (postcondición b) o crea uno
   nuevo (a), y reevalúa «bajo el mínimo» (c). DSH junta **todos** los impedimentos (`impedimentos_de_deshabilitacion`), cada uno con su
   texto y cómo resolverlo. Auditoría con `Decimal` como texto. Pruebas: `test_cmp_hab_iin.py`, `test_cmp_mod_iin.py`,
   `test_cmp_dsh_iin.py`, `test_cmp_cns_iin.py` (una por regla y por postcondición), con concurrencia (dos habilitaciones simultáneas del mismo par:
   queda un solo registro; una habilitación contra la baja del invernadero) con la etiqueta `concurrencia`.
4. **Conexión con `maestros`.** En `InventarioConfig.ready()`: `registrar_impedimento_de_baja` (stock distinto de cero, tránsito y los
   impedimentos de deshabilitación de los insumos del invernadero) y `registrar_efecto_de_baja` (pasa a inactivos los
   `InsumoInvernadero` y escribe un `baja_insumo_invernadero` por cada uno), según `docs/api/extensiones_de_inventario.md`. Cierra el
   disparador «Cuando exista InsumoInvernadero». Pruebas: `test_baja_de_invernadero_con_insumos.py` (precondición f y postcondición c de
   PROD-BAJ-INV con `baja_invernadero` real; la reactivación no reactiva los insumos).
5. **Salida por consumo** (`registrar_salida_por_consumo(iin_id, partes, *, origen_id, fecha=None)`, API de `produccion`; `origen_id` es obligatorio (D-52 punto 5) y cada movimiento lo lleva en `origen`; prueba: sin él falla; el parámetro opcional `fecha` lo pide D-50 punto 7: la fecha del movimiento es esa, con la hora actual, y sin ella la de hoy; prueba: con `fecha` pasada, el movimiento la lleva). Según `docs/patrones/stock.md`, sección 3: un movimiento por lote, el
   faltante sin lote cuando falta, sin bloquear, y `reevaluar_alertas_del_insumo` al final. Pruebas: `test_salida_por_consumo.py` (cubre
   exacto, de varios lotes, con faltante nuevo y con faltante existente que crece; deja la alerta; los invariantes de las fábricas en
   cada caso) y la de concurrencia (dos consumos simultáneos sobre el mismo lote: no deja negativo ni descuenta dos veces) con etiqueta
   `concurrencia`.
6. **Ajuste de stock** en `inventario/servicios/ajustes.py`: `calcular_ajuste` (no escribe) y `confirmar_ajuste` (bloquea, recalcula, compara la
   «huella» y escribe en una sola transacción), con los seis motivos y el recuento por lote completo con lotes nuevos (10b) y quitados (10c).
   Todo según el extracto, incluida su sección «Cómo se aplica» (sin asientos; los dos desvíos del modelo; dos pasos; el paso 4 ofrece las existencias activas aunque el insumo sea una semilla dada de baja con su variedad). Prueba extra: `test_cmp_ajt_stk_semilla_inactiva.py`. El resumen del paso 12
   lleva las cinco partes (lotes que cambian, lotes nuevos, faltante que queda en cero, stock antes y después, valor). `AjusteDesactualizado`
   (extensión 14a) no cambia nada y devuelve lo vigente. Pruebas: `test_cmp_ajt_stk_recuento.py`, `test_cmp_ajt_stk_motivos.py`,
   `test_cmp_ajt_stk_validaciones.py` (una por regla, por postcondición y **por extensión**, nombrando con el número del paso:
   `test_extension_7b_3a_…`), `test_cmp_ajt_stk_alertas.py` (h, i, j y 12b) y `test_cmp_ajt_stk_concurrencia.py` (ajuste contra consumo y
   ajuste contra ajuste, con la etiqueta `concurrencia`; la 14a). Cada una verifica los invariantes de las fábricas.
7. **Revisión de vencimientos** en `inventario/servicios/vencimientos.py` (`revisar_vencimientos(hoy=None)`) y
   `inventario/management/commands/revisar_vencimientos.py` (sin lógica; `--fecha` opcional). Según el extracto y su sección «Cómo se
   aplica»: una transacción por invernadero, idempotente, sin Agrónomo no alerta, el lote que vence resuelve la alerta de «por vencer»,
   regla 11 (bajo el mínimo), un registro de auditoría por alerta creada con `usuario=None`, código de salida distinto de cero si hubo
   una falla. Pruebas: `test_cmp_rev_vnc.py` (una por regla y por postcondición; el borde del día del vencimiento y de los 15 días; correr
   dos veces; un día salteado; cambio de `dias_aviso_vencimiento`; invernadero sin Agrónomo; lote agotado) y `test_comando_revisar_vencimientos.py`
   (`call_command` con y sin `--fecha`; el código de salida con una falla simulada).
8. **Pantallas.** La pestaña «Existencias de insumos» (primera de «Inventario»; filas desplegables con lotes y sus estados; filtros del
   CU), los modales «Habilitar insumo», «Mínimo y precio» y «Deshabilitar» (con los impedimentos), el botón «Habilitar en un invernadero» en
   el catálogo y en el alta (que INV-01 dejó sin él), el aviso «Cargar stock inicial» y la pantalla «Ajustar stock» (invernadero, insumo,
   motivo; recuento por lote; resumen; confirmar; aviso de datos desactualizados), con HTMX (la pantalla se actualiza tras cada dato) y
   respaldo sin JavaScript. «Dar de baja» en los lotes vencidos abre el ajuste con el motivo «vencimiento». Las vistas exigen Agrónomo
   a cargo (403 al resto y a un Agrónomo ajeno). Pruebas: `inventario/tests/test_existencias_vistas.py`, `test_ajuste_vistas.py`
   (permisos, errores por campo, resumen, la advertencia 12b, el aviso 14a, el valor sin asiento) y la entrada del menú.
9. **Cierre de documentación.** Cerrar «Cuando exista InsumoInvernadero» en `docs/disparadores.md`; completar «Cuando existan los pedidos de
   `compras`» (los tres puntos ya existen) y agregar la nota de que el cron job de Render se crea a mano; marcar INV-02 en
   `docs/tareas/README.md` y `docs/tareas/ronda_produccion_1.md`. Lo que dice la documentación distinto de lo implementado va a
   `docs/temas_abiertos.md`.

Si el tiempo apremia: no se recortan los bloqueos, el todo o nada ni los invariantes. Se puede dejar para una tarea chica aparte, anotada
como disparador, **la pantalla del ajuste sin JavaScript** (el servicio y su prueba sí van) y el filtro «Bajo el mínimo» de las existencias.
Si la tarea no entra en una sesión, el corte limpio es entre el paso 5 (todo lo que usa `produccion`) y el 6 (ajustes y vencimientos): avisá
antes de partirla.

## Hecho cuando

- Los seis casos de uso están implementados con una prueba por regla, por postcondición y, en CMP-AJT-STK, por extensión, y con sus
  pruebas de vista.
- Ninguna operación deja un lote (que no sea el faltante) negativo ni cambia una cantidad sin su movimiento; las fábricas lo verifican en cada
  prueba de servicio.
- El ajuste no genera asiento ni lo verifica (D-45) y muestra el valor.
- `revisar_vencimientos` es idempotente y corre con `python manage.py revisar_vencimientos`.
- La baja de un invernadero con stock de insumos distinto de cero se rechaza, y la de uno en 0 pasa sus insumos a inactivos.
- `docs/api/stock.md` coincide con lo implementado (nombres y firmas); si cambió algo, se corrige el documento en la misma tarea.
- Comando de pruebas:
  python manage.py test inventario maestros core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion
  python manage.py test inventario --keepdb --tag concurrencia
  python manage.py test inventario --keepdb --tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

Hay posibles migraciones de `core`: `python manage.py migrate`. Cuentas: Agrónomo con un invernadero a cargo (con lotes y alertas visibles),
otro Agrónomo, Gerente. Datos: un insumo con vencimiento (por ejemplo, «Nutriente A», L), otro sin vencimiento (por ejemplo, «Bolsas», unidad).

1. En «Inventario» → «Existencias de insumos» no hay nada. Habilitar «Nutriente A» en tu invernadero con mínimo 20 y precio 1500: la alerta
   «bajo el mínimo» aparece (campana) y el aviso ofrece «Cargar stock inicial».
2. «Cargar stock inicial» 30 L con vencimiento dentro de 40 días; otro lote de 10 L con vencimiento en 5 días; uno de 5 L con una fecha pasada: el
   último da error («lo vencido no ingresa al stock»). Cantidad con 4 decimales: error con los decimales que admite la unidad.
3. Las existencias muestran 40 L, el lote de 5 días con «vence en 5 días» y la alerta «bajo el mínimo» resuelta.
4. Recuento físico: contar 8 L en el lote de 10 y agregar un lote nuevo de 2 L con otro vencimiento; el resumen muestra diferencias, el lote nuevo y el
   stock antes y después; confirmar. Ver los movimientos en el administrador de Django (solo lectura).
5. Rotura con más cantidad de la disponible: error con lo disponible. Corrección entre lotes: el stock total no cambia y el resumen dice que no
   tiene valor.
6. «Vencimiento» solo lista lotes vencidos. Para probarlo: en `manage.py shell`, cambiar la fecha de un lote al pasado y volver a mirar; dar de baja
   el lote y ver que su alerta de vencido se resuelve.
7. Simular un consumo mayor al stock con `registrar_salida_por_consumo` desde `manage.py shell`: aparece «Sin lote» negativo y la alerta «stock
   inconsistente»; un recuento físico lo deja en cero y resuelve la alerta.
8. Con otro Agrónomo (ajeno): la URL de ajuste del invernadero de otro da 403. El Gerente no ve «Inventario».
9. Modificar mínimo y precio: sin cambios no hay registro en «Auditoría»; con cambios, un registro con antes y después (como texto).
10. Deshabilitar con stock: lista lo que lo impide. Con stock en 0: se deshabilita; volver a habilitar reactiva el mismo registro.
11. Dar de baja el invernadero con stock de insumos distinto de cero: se rechaza e informa. Con todo en 0: los insumos quedan inactivos.
12. `python manage.py revisar_vencimientos` en el servidor de desarrollo: genera las alertas «por vencer» (15 días) y «vencido» que correspondan;
    correrlo de nuevo no duplica nada; `--fecha` con un día futuro simula el paso del tiempo.
13. Dos ajustes simultáneos sobre el mismo insumo (dos sesiones; si no, la prueba de concurrencia lo cubre): uno lo aplica y el otro ve «los datos
    cambiaron» sin error 500.
14. Sin JavaScript, los pasos 1 a 5 funcionan igual.
15. **Render (a mano, una sola vez):** crear un *Cron Job* con el mismo repositorio y rama, las mismas variables de entorno que el web service
    (incluida la base de Neon), comando de compilación igual al del web service, comando de ejecución `python manage.py revisar_vencimientos` y
    agenda `0 6 * * *` (03:00 de Argentina, porque Render usa UTC). Costo: Render cobra un mínimo de 1 dólar por mes por cron job; revisarlo antes
    de crearlo. Después de una corrida, ver en el log el resumen del comando. Anotar el nombre del cron job en `docs/estado.md`.
16. Después del merge: verificar en el log de Render que se aplicaron las migraciones nuevas.

## Cierre (la completa Claude Code al cerrar)
