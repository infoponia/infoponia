# API · `produccion` (PRD-01 a PRD-04, COM-02, COM-04a y COM-05a2; las secciones 10 y 11, de COM-04a para las entregas y las solicitudes)

Contrato de lo que `produccion` expone y de lo que registra en las otras apps, para quien programa PRD-03, PRD-04 y las rondas futuras (cosecha, entrega, asientos) sin leer todo el código.
Versión del lote 4 (D-50). Si algo de acá contradice una decisión, manda la decisión: avisá.

`produccion` es de nivel 5 (D-37): puede importar `core`, `contabilidad`, `maestros`, `inventario`; **nadie de nivel menor la importa**: se registran en ella, no al revés (regla A4).
Los servicios están en `produccion/servicios/<entidad>.py`; un caso de uso = una función pública dentro de `transaction.atomic()`; los helpers internos llevan guion bajo.

## 1. Servicios de escritura (un CU = una función)

| Función | CU | Quién actúa | Resultado |
|---|---|---|---|
| `siembras.planificar_siembra(actor, datos) -> Siembra` | PROD-PNF-SMB | Agrónomo a cargo | La orden, ya con ocupaciones y reservas |
| `siembras.concretar_siembra(actor, orden_id, datos) -> Lote` | PROD-CNC-SMB | Capataz de la orden | El lote creado |
| `transiciones.planificar_transicion(actor, datos) -> TransicionEtapa` | PROD-PNF-TRN | Agrónomo a cargo | La orden |
| `transiciones.concretar_transicion(actor, orden_id, datos) -> TransicionEtapa` | PROD-CNC-TRN | Capataz de la orden | La orden concretada |
| `ordenes.cancelar_orden(actor, orden_id, motivo) -> OrdenTrabajo` | PROD-CNL-ORD | Agrónomo a cargo | La orden cancelada. Guarda `estado_orden`, `fecha_resolucion_orden` (hoy) y `motivo_cancelacion`; avisa al Capataz con el motivo (texto en `cancelar_orden.md`, «Decisiones de aplicación») |
| `ordenes.cancelar_orden_incluida(actor, orden, motivo, *, avisar=False) -> CancelacionIncluida` | PROD-CNL-ORD como parte de otro CU (PRD-04: PROD-PNR-FDS; COM-05a1: la entrega; IOT-07: el mantenimiento) | `actor` o `None` (InfoPonia) | Ver abajo. **Acepta cualquier tipo de orden** (D-67, punto 1) |

`datos` son `dataclass` (`DatosDeSiembra`, `DatosDeConcrecionDeSiembra`, `DatosDeTransicion`, `DatosDeConcrecionDeTransicion`), no diccionarios, y se construyen desde el formulario con una función `desde_post`.
Cada par `resumen_de_…` / `datos_de_…` **no escribe** y devuelve lo que muestra la pantalla (valores propuestos, advertencias, errores por campo).

Todas: reciben al actor, verifican su rol y que siga activo **después de bloquear**, y lanzan `produccion.errores.ErrorDeProduccion(codigo, mensaje, campo=None)` para cualquier rechazo de negocio. Códigos que usan en común con las otras apps: `cambio_simultaneo`, `sin_permiso`, `invernadero_inactivo`.
Códigos propios: `orden_no_pendiente`, `sin_capataz_activo`, `variedad_incompatible`, `semilla_no_habilitada`, `stock_insuficiente`, `capacidad_insuficiente`, `distribucion_incompleta`, `orden_duplicada`, `fecha_invalida`, `cantidad_invalida`, `causa_obligatoria`, `motivo_obligatorio`, `motivo_largo`, `lote_con_transicion`, `lote_no_trasladable`, `sector_no_elegible`, `orden_no_cancelable` (PRD-01, D-67 punto 1: `cancelar_orden` con un tipo que no cancela `produccion`), `causa_invalida`, `descripcion_larga` y `lote_sin_plantas` (PRD-02, D-83), y los de PRD-03: `lote_no_activo`, `descripcion_obligatoria`, `sin_sectores`, `sin_insumos`, `insumo_no_aplicable`, `insumo_repetido`, `reparto_supera_lote`, `distribucion_incompleta` y `filtro_invalido`. `cantidad_invalida` y `cambio_simultaneo` también llevan `datos` (los valores vigentes: lo ocupado por sector, los lotes y las plantas que cambiaron).).

### `cancelar_orden_incluida`

Para un CU de otra tarea que **incluye** la cancelación de una orden (PROD-PNF-FDS de PRD-04 y, desde la ronda «IoT 1», la cancelación del mantenimiento automático y la regla 8 de IOT-MOD-HDW, en IOT-07; D-73). Corre en la transacción del llamador y **no audita ni notifica por su cuenta**:

- `actor`: quien actúa en el CU que incluye, o `None` si actúa InfoPonia.
- Cancela solo órdenes «a realizar»; si la orden ya no lo está, lanza `orden_no_pendiente` (el llamador decide).
- Acepta **cualquier tipo** (D-67, punto 1): una orden sin Capataz (su hija no hereda de `ConCapataz`: entrega, mantenimiento) deja
  `notificar_a` vacío aunque `avisar=True`; una sin sectores deja `sectores_afectados` vacío; las reservas de insumo, si tiene, se cancelan
  sin consumo, y si no tiene, `reservas` vacío.
- Recibe el motivo ya armado y, si pasa de 300, lo recorta con «…» (el «…» cuenta dentro de los 300; no lanza `motivo_largo`).
- Devuelve `CancelacionIncluida(orden, reservas, sectores_afectados, alertas_resueltas, notificar_a)`: lo que el llamador necesita para **meter en su único registro de auditoría** (D-36) y a quién notificar (el Capataz, si `avisar=True` y está activo).
- El llamador ya tiene bloqueados invernadero, variedad y sectores en el orden de `docs/patrones/bloqueos.md`; esta función bloquea lo que le sigue (insumos de las reservas, orden y reservas).

## 2. Lectura (sin escribir, sin bloquear, sin consultas por fila)

| Función | Qué devuelve |
|---|---|
| `ordenes.ordenes_del_capataz(capataz, *, estado=None)` | **La única unión** de las órdenes de un Capataz (D-53): recorre `Siembra` y `TransicionEtapa` (y `Cosecha` cuando exista), filtrada además por `TIPOS_DE_PRODUCCION`, y devuelve filas ya con lo que necesitan la bandeja, el traspaso y el aviso de baja de cuenta. Sin consultas por fila |
| `ordenes.bandeja_del_capataz(capataz) -> Bandeja` | Con `ordenes_del_capataz`: las órdenes «a realizar» asignadas a ese Capataz, ordenadas por fecha programada, después prioridad (sin valor = media), después `id`; con los grupos «vencidas», «hoy» y «próximas» |
| `ordenes.lista_de_ordenes(actor, filtros)` | Las órdenes visibles para el actor (Agrónomo a cargo; el Gerente en solo lectura), solo de los tipos de `TIPOS_DE_PRODUCCION` |
| `ordenes.ordenes_cancelables(actor)` | Las «a realizar» de sus invernaderos, agrupadas por invernadero y tipo. **En PRD-01** (el código), de los tipos de `TIPOS_DE_PRODUCCION` que además están en `TIPOS_QUE_CANCELA_PRODUCCION` (siembra y transición): no lista cosechas. **Desde COM-04a**, de todos los de `TIPOS_DE_PRODUCCION`; la fila de una cosecha lleva la acción «Cancelar» de `comercial` (`registrar_acciones_de_cosecha`), porque `cancelar_orden` la sigue rechazando (lote C8, corrección a validar) |
| `ordenes.TIPOS_DE_PRODUCCION`, `ordenes.TIPOS_QUE_CANCELA_PRODUCCION` | Constantes (D-67, punto 1): `(SIEMBRA, TRANSICION, COSECHA)`, las órdenes que muestran las pantallas de `produccion` (lista, cancelables, bandeja); `(SIEMBRA, TRANSICION)`, las que acepta `cancelar_orden`. Las listas filtran con `tipo__in`, **nunca** con «todo menos X»: un tipo nuevo no aparece en las pantallas de `produccion` hasta que alguien lo agregue a propósito |
| `lotes.lotes_activos_de(invernadero_ids)` | Lotes activos con variedad, etapa, cantidad, costo por planta, fecha de entrada a la etapa y fecha estimada de fin |
| `lotes.fecha_de_entrada_a_la_etapa(lote)` | Regla 5 de 8.21 |
| `lotes.fecha_estimada_de_fin_de_etapa(lote)` | Entrada + `duracion_dias` de la etapa actual |
| `lotes.fecha_de_entrada_a_maduracion(lote)` | `None` si no entró (regla 2 de 8.20) |
| `lotes.fecha_maxima_de_cosecha(lote)` | `None` si no entró a Maduración (regla 3 de 8.20); la usará la cosecha |
| `lotes.sectores_de_origen(lote)` | Ocupaciones con `cant_agujeros_ocupados > 0` y su sector |
| `lotes.perfil_de_sector(sector_ids)` | `dict[id, perfil o None]` |
| `costos.costo_por_planta(lote)`, `costos.costo_de_la_merma(lote, n)` | `docs/patrones/costo_del_lote.md` |
| `transiciones.fecha_minima_de_transicion(lote)` | La mayor entre la fecha de entrada a la etapa y el último registro de bitácora del lote en esa etapa |
| `transiciones.repartir_proporcional(cantidad, planificado)` | Reparto del resto mayor (función pura) |

Los datos de más de una orden o más de un lote se piden con **listas de ids** y una consulta por tabla.

## 3. Lo que `produccion` registra en las otras apps (`AppConfig.ready()`, regla A4)

| App | Punto | Qué informa | Tarea |
|---|---|---|---|
| `maestros` | `registrar_agujeros_de_sector` | `(ocupados, comprometidos)` por sector (derivados, D-50) | PRD-01 |
| `maestros` | `registrar_impedimento_de_baja_de_sector` | Códigos `agujeros_ocupados` y `agujeros_comprometidos` | PRD-01 |
| `maestros` | `registrar_contenido_de_sector` | Lotes y órdenes que ocupan o comprometen el sector | PRD-01 |
| `maestros` | `registrar_perfil_de_sector` | Perfil familiar | PRD-01 |
| `maestros` | `registrar_aviso_de_cambio_de_tipo` | Lotes que deben pasar por esa etapa y siembras a realizar | PRD-01 |
| `maestros` | `registrar_impedimento_de_baja` (invernadero) | Lotes activos y órdenes «a realizar» (códigos `lotes_activos`, `ordenes_a_realizar`) | PRD-01 |
| `maestros` | `registrar_efecto_de_baja` (invernadero) | PRD-01 **no registra nada** (con lotes u órdenes la baja no se hace); **PRD-04 sí**: cierra con `fecha_fin = hoy` los registros «Fuera de servicio» abiertos de los sectores del invernadero | PRD-04 |
| `maestros` | `registrar_efecto_de_vuelta_a_servicio(actor, sector)` | Cierra el registro «Fuera de servicio» y escribe la bitácora de la vuelta (MAE-03, PROD-MOD-SCT) | PRD-04 |
| `maestros` | `registrar_efecto_de_baja_de_sector` (nuevo, D-51 punto 7) | Cierra el registro «Fuera de servicio» abierto (PROD-BAJ-SCT, postcondición b) | PRD-04 |
| `maestros` | `registrar_traspaso(contar, traspasar)` (rol Capataz) | Al asignar un Capataz nuevo, pasan a él las órdenes «a realizar» del saliente (regla 3 de 8.22), actualizando `capataz` en cada hija (D-53); el punto admite varios registrantes y recibe el rol: IOT-07 registrará el del Técnico (D-73; `docs/casos_de_uso/iot/mantenimiento_automatico.md`, «Traspaso del Técnico»); audita como lo pide el contrato de `maestros/extensiones.py` (MAE-01b) | PRD-01 |
| `maestros` | `registrar_pestana_de_invernadero` (nuevo, ver `extensiones_de_maestros.md`) | «Lotes activos» de la ficha | PRD-01 |
| `maestros.alertas` | `registrar_tipo_de_alerta` | `produccion_merma_umbral` (Agrónomo y Gerente, evento, `Origen.MERMA`) y `produccion_plantas_comprometidas` (Agrónomo o Gerente, evento, `Origen.MERMA`) | PRD-02 |
| `inventario` | `registrar_reservas_de_insumo`, `registrar_ordenes_que_reservan` | Reservas activas por `InsumoInvernadero` y las órdenes que las tienen | PRD-01 |
| `inventario` | `registrar_uso_de_variedad`, `registrar_variedades_presentes`, `registrar_impedimento_de_baja_de_variedad` | Lotes activos y órdenes «a realizar» (códigos `lotes_activos`, `ordenes_a_realizar`); el umbral efectivo | PRD-01 |
| `core` | `registrar_seccion_de_inicio` | La bandeja del Capataz como sección del inicio | PRD-01 |
| `core` | `registrar_asignaciones_de_cuenta` | Lo que una cuenta tiene asignado (órdenes «a realizar», por `ordenes_del_capataz`) para el aviso de baja de la cuenta | PRD-01 |

Cada registrante lleva sus **tres pruebas mínimas** (con datos, neutro sin datos, sin consultas por fila) como las de `docs/api/extensiones_de_maestros.md`, «Prueba mínima de cada registrante».

## 4. Auditoría (`core.models.Accion`, D-36)

Acciones de negocio nuevas (en `ACCIONES_DE_NEGOCIO`, con etiqueta y migración de `choices` de `core`): `planificacion_siembra`, `concrecion_siembra`, `planificacion_transicion`, `concrecion_transicion`, `cancelacion_orden`, `registro_merma` (esta última la usa PRD-02 dentro de `concrecion_transicion` como afectado, y PRD-03 como acción propia).
Un registro por CU, con todo lo tocado como afectado. Decimales y fechas **como texto** en `cambios` y `datos`. «Agujeros comprometidos» y «agujeros ocupados» de cada sector van como cambio de texto antes → después (D-50 punto 4).

## 5. Reglas para quien llama

1. Nunca crees ni cambies `Lote`, `OcupacionSector`, `Consumo` ni `Merma` fuera de los servicios de `produccion`.
2. Bloqueá en el orden de `docs/patrones/bloqueos.md` (nivel 2c: sectores, entre variedad e insumos).
3. Si tu operación cambia un lote, cambiá `costo_acumulado` con las funciones de `costos.py`, nunca a mano.
4. Si cancelás órdenes, usá `cancelar_orden_incluida`; no dupliques su lógica.
5. `Decimal`, nunca `float`; las fechas con `timezone.localdate()`.

## 6. Lote 5: lo que suman PRD-03 y PRD-04

### Escritura

| Función | CU | Quién actúa | Resultado |
|---|---|---|---|
| `mermas.registrar_merma(actor, datos) -> Merma` | PROD-REG-MRM (lote en pie) | Capataz asignado o Agrónomo a cargo | La merma |
| `aplicaciones.registrar_aplicacion(actor, datos) -> ResultadoDeAplicacion(aplicacion, lineas)` | PROD-REG-APL | Agrónomo o Capataz | La aplicación y, por insumo, una `LineaDeResumen` (cantidad, lotes de insumo de los que salió y, **solo si actúa un Agrónomo**, faltante, valor, destino, reparto y aviso; al Capataz, `None`) |
| `bitacora.registrar_evento(actor, datos) -> Bitacora` | PROD-REG-EVT | Agrónomo o Capataz | El registro |
| `sectores_fuera_de_servicio.poner_fuera_de_servicio(actor, datos) -> FueraDeServicio` | PROD-PNR-FDS | Agrónomo a cargo | El registro «Fuera de servicio» |

### El núcleo de la merma (PRD-02), para quien lo llama

`mermas.aplicar_merma(lote, cantidad, causa, descripcion, fecha, responsable, *, por_sector=None, sector_ids=(), ordenes_excluidas=()) -> ResultadoMerma(merma, costo, alertas)`. Corre dentro de la transacción del llamador, con invernadero, variedad, sectores y lote **ya bloqueados** (`docs/patrones/bloqueos.md`, sección `produccion`).

- `por_sector`: `dict[sector_id, int]` con las plantas perdidas por sector. Solo Registrar Merma lo pasa; baja los agujeros ocupados de esas ocupaciones.
- `sector_ids`: sectores que quedan en `Bitacora.sectores`. `ordenes_excluidas`: órdenes que no cuentan para la condición 2 de plantas comprometidas.
- Baja `cantidad_actual` y `costo_acumulado`; deja el lote `finalizado` si llega a cero; evalúa y crea alertas. **No audita ni notifica**: el CU que llama arma su único registro.

### Lectura

| Función | Qué devuelve |
|---|---|
| `bitacora.consultar_bitacora(actor, invernadero_id, filtros, pagina)` | Página de 50 registros, del más reciente al más antiguo; una consulta por tabla |
| `bitacora.invernaderos_de_bitacora(actor)` | Agrónomo, los suyos; Gerente, todos (también de baja) |
| `alcance.invernaderos_del_actor(actor)`, `alcance.invernadero_del_actor(actor, id)` | Los invernaderos activos donde el Capataz está asignado o el Agrónomo está a cargo; `sin_permiso`, `invernadero_inactivo` o 404 |
| `mermas.lotes_con_merma_posible(actor, invernadero_id)`, `datos_de_merma(actor, lote_id)`, `resumen_de_merma(actor, datos)` | Los lotes activos (lista vacía = extensión 4b), la propuesta del paso 6 y el resumen del paso 8 (sin escribir) |
| `aplicaciones.sectores_de_aplicacion`, `insumos_aplicables(actor, invernadero_id)` (`precio` y `destino`, `None` para el Capataz), `resumen_de_aplicacion(actor, datos)`, `plantas_del_alcance(actor, datos)` | Lo de los pasos 4, 6 y 10, y las plantas por lote del alcance para la extensión 12a |
| `bitacora.datos_de_evento(actor, invernadero_id=None)`, `bitacora.TIPOS_DE_FILTRO`, `FiltrosDeBitacora` | La propuesta de «Otro evento» y los tipos que ofrece el filtro; `PaginaDeBitacora` trae `lotes` y `sectores` para los filtros |
| `aplicaciones.insumos_aplicables(actor, invernadero_id)` | Insumos con consumo directo, habilitados, activos y con stock libre; sin valores si actúa un Capataz |
| `mermas.merma_acumulada(lote)` | Porcentaje sobre la cantidad inicial, sin «descarte por selección» |
| `costos.repartir_en_centavos(monto, plantas_por_lote)` | Parte de cada lote (`docs/patrones/costo_del_lote.md`) |
| `sectores_fuera_de_servicio.fecha_minima_fuera_de_servicio(sector)`, `destinos_elegibles(sector, lotes)` | Para la pantalla y las verificaciones |
| `inicio.indicadores_del_agronomo(actor, invernadero_ids)` | Indicadores del Inicio del Agrónomo |

### Registrantes que suman

| App | Punto | Qué informa | Tarea |
|---|---|---|---|
| `maestros` | `registrar_pestana_de_invernadero` | Pestaña «Bitácora» | PRD-03 |
| `core` | `registrar_seccion_de_inicio` | Sección del Agrónomo | PRD-04 |
| `maestros` | vuelta a servicio, baja de sector, baja de invernadero | Cierre del registro «Fuera de servicio» | PRD-04 |

### Auditoría (D-36 y D-51 punto 9)

Acciones nuevas: `registro_aplicacion` y `registro_evento` (PRD-03; `registro_merma` la crea PRD-02) y `fuera_de_servicio_sector` (PRD-04), con etiquetas y migración de `choices` de `core`.

## 7. COM-02: los puntos de extensión de `produccion` (D-59)

`produccion/extensiones.py` (nuevo en COM-02) declara `registrar_reservado_de_lote` y `registrar_detalle_de_cosecha`, que registra
`comercial`. Contrato: `docs/api/extensiones_de_produccion.md`. Con ellos, `aplicar_merma` evalúa la condición 1 de plantas comprometidas
y, desde COM-04a, la bandeja y la lista muestran las cosechas con sus lotes. COM-02 también suma `Cosecha` a `ordenes_del_capataz` y al
traspaso del Capataz.

## 8. COM-04a: el núcleo físico de la cosecha y la cámara (D-64)

Funciones de **núcleo** (como `aplicar_merma`): corren dentro de la transacción de quien llama (sin ella, `RuntimeError`), con lo suyo ya
bloqueado (`docs/patrones/bloqueos.md`), **no auditan ni notifican** y devuelven lo que crearon para que el caso de uso lo ponga en su único
registro (D-36). Los casos de uso que las llaman viven en `comercial` (D-59, D-64 punto 2): `produccion` no lee reservas por su cuenta.

| Función | Qué hace |
|---|---|
| `cosechas.cosechar_lote(cosecha, lote, por_sector, fecha, responsable) -> ResultadoCosechaDeLote(cantidad, costo_unitario, costo, bitacora, movimiento)` | `por_sector`: `dict[sector_id, int]` con las plantas cosechadas en cada sector (0 vale). Calcula el costo por planta **antes** (`costos.costo_por_planta`); baja `cantidad_actual` y `costo_acumulado` (cantidad × costo por planta, `docs/patrones/costo_del_lote.md`) y los agujeros ocupados de cada ocupación vigente; deja el lote `finalizado` si llega a 0 (ocupaciones en 0, costo 0); crea la `Bitacora` tipo `cosecha` (con `cosecha`, lote, etapa actual, invernadero, `sectores` = los de la cosecha, responsable y la fecha efectiva) y, si la cantidad es mayor que 0, el `MovimientoStock` `salida_por_cosecha` (origen: la cosecha; `costo_unitario` = el costo por planta de antes). `ErrorDeProduccion('cosecha_supera_sector', sector=…)` si un sector pasa de sus agujeros ocupados |
| `cosechas.concretar_orden(cosecha, fecha)` | Pasa la cosecha a «concretada» con `fecha_resolucion_orden` = hoy y `fecha_cosecha` = la efectiva. `ErrorDeProduccion('orden_no_a_realizar')` si ya no lo estaba |
| `cosechas.costo_unitario_de_cosecha(cosecha_ids, lote_ids) -> dict[(cosecha_id, lote_id), Decimal]` | El `costo_unitario` de cada «salida por cosecha» (lo usa la partida que nace después, D-64 punto 3). Una consulta |
| `camara.crear_partida(lote, cantidad, motivo, *, fecha_cosecha, fecha_ingreso, costo_unitario, origen) -> StockCosechado` | Partida «disponible» con ingreso = disponible = `cantidad`, `fecha_limite = fecha_cosecha + lote.variedad.duracion_post_cosecha`, y su `MovimientoStock` `ingreso_a_camara` (origen: el documento que lo origina). Quien llama ya bloqueó el invernadero con `bloquear_invernadero_activo` (D-40) |
| `camara.aplicar_merma_de_partida(partida, cantidad, causa, descripcion, responsable) -> ResultadoMermaDePartida(merma, movimiento)` | `Merma` (hija de `Bitacora`, tipo `merma`) con el lote de origen, **sin etapa**, el invernadero, fecha y hora actuales (regla 8 de 8.9) y `responsable` (`None` = InfoPonia); baja la disponible de la partida; `agotado` si llega a 0; `MovimientoStock` `merma_en_camara` (origen: la merma, `costo_unitario` = el de la partida). No toca el lote ni su costo. `ErrorDeProduccion('merma_supera_partida')` si pasa de la disponible. **No recorta reservas**: eso lo hace `comercial` antes de llamarla |
| `camara.vencer_partida(partida, hoy) -> ResultadoMermaDePartida \| None` | Si la disponible es mayor que 0, `aplicar_merma_de_partida` con causa `vencimiento_en_camara` y `responsable=None`; la partida queda `vencido` con disponible 0 en todos los casos. `None` si no había nada |
| `camara.partidas_del_invernadero(invernadero_ids)` | Lectura: partidas con variedad, lote, ingreso, fecha límite, disponible y estado, para la pestaña «Cámara» (lo reservado lo suma `comercial`) |
| `ordenes.marcar_cancelada(orden, motivo)` y `ordenes.texto_de_cancelacion(orden, motivo, actor) -> (titulo, detalle)` | Lo común de cancelar cualquier orden (estado, fecha de resolución, motivo con su validación y recorte; el texto del aviso con su regla de largo), **Ya existen desde PRD-01** (`produccion/servicios/ordenes.py`, código mergeado): COM-04a las **usa** para que la cancelación de una cosecha (`comercial`) no duplique la lógica; no las escribe ni las cambia |
| `mermas.aplicar_merma(...)` (cambia) | Suma el `MovimientoStock` `salida_por_merma` del lote (origen: la merma; `costo_unitario` = el costo por planta de antes). Nada más cambia |
| `mermas.merma_acumulada(lote)` (cambia) | Cuenta solo las mermas **con etapa** (lote en pie, regla 7 de 8.9): las de cámara no suman |

- **Orden dentro de PROD-CNC-CSC** (lo arma `comercial`): `cosechar_lote` de cada lote → `aplicar_merma` de los que declararon plantas
  perdidas (extensión 10a; las cantidades por sector se validan contra lo que queda **después** de la cosecha) → `concretar_orden`.
- **Registrantes que suma COM-04a en `produccion`:** el impedimento de baja del invernadero `partidas_en_camara` (precondición e de
  PROD-BAJ-INV) en el registrante de PRD-01; la bitácora (PROD-CNS-BIT) ofrece el tipo `cosecha` en su filtro.
- **Puntos nuevos de `produccion/extensiones.py`:** `registrar_acciones_de_cosecha` y `registrar_entradas_de_comercial`
  (`docs/api/extensiones_de_produccion.md`, secciones 3 y 4). Los usan la bandeja del Capataz, la lista de órdenes del Agrónomo y la
  pantalla de merma.
- Pruebas en `produccion/tests/test_camara_nucleo.py` y `test_cosechas_nucleo.py`: una por efecto (cantidad, costo, agujeros, bitácora,
  movimiento, partida, estados), el lote que llega a 0, el sector que se pasa, sin transacción (`RuntimeError`), y que ninguna audita ni
  notifica.

## 9. Entregas y mantenimientos frente a `produccion`: lo que deja hecho PRD-01 y lo que suma COM-05a2 (D-66, D-67)

`Entrega` vive en `comercial` y es hija de `OrdenTrabajo` (D-66, punto 2). `produccion` no la conoce por su clase: la ve como una orden de
`tipo_orden = entrega` (lo mismo que un mantenimiento de IOT-07, hijo de `OrdenTrabajo` en `iot`). Hay dos partes: lo que **deja hecho PRD-01**
(D-67, punto 1), que ninguna tarea posterior toca, y lo que **suma COM-05a2** para el envasado (permitido en su tarea).

### Lo que deja hecho PRD-01 (D-67, punto 1)

`OrdenTrabajo.Tipo` ya tiene los cinco valores desde `produccion/0001_initial` (COM-02, COM-05a1 e IOT-07 no tocan los `choices`). Con una
orden de tipo `entrega` o `mantenimiento`:

| Función o punto (PRD-01) | Qué hace |
|---|---|
| `ordenes.lista_de_ordenes`, `ordenes.ordenes_cancelables`, `ordenes.ordenes_del_capataz` (y con ella la bandeja) | **No la muestran**: filtran con `TIPOS_DE_PRODUCCION` (`tipo__in`). Las entregas tienen su pantalla «Envasado» (`comercial`); el mantenimiento, la ficha del equipo (`iot`) |
| `ordenes.cancelar_orden` (la del Agrónomo) | **La rechaza** con `ErrorDeProduccion('orden_no_cancelable')`, sin bloquear ni cambiar nada: acepta solo `TIPOS_QUE_CANCELA_PRODUCCION` (siembra y transición). Una entrega o un mantenimiento solo se cancelan desde otro caso de uso (PROD-CNL-ORD, regla «Órdenes que cancela el Agrónomo»); una cosecha, con `comercial.cancelar_cosecha` (D-64) |
| `ordenes.cancelar_orden_incluida(actor, orden, motivo, *, avisar=False)` | **Sí la acepta**, de cualquier tipo, sin dar por hecho Capataz ni sectores y con o sin reservas de insumo. La usan `comercial.servicios.entregas.cancelar_entrega_incluida` (D-66, punto 9) e `iot` (D-73, punto 3) |
| El impedimento `ordenes_a_realizar` de la baja del invernadero | **La cuenta**: cuenta las órdenes «a realizar» de todos los tipos (precondición de PROD-BAJ-INV; D-64, punto 12) |
| `registrar_reservas_de_insumo` (en `inventario`) | **Cuenta sus reservas activas** (las de todas las órdenes): los envases reservados restan del stock libre |
| `registrar_ordenes_que_reservan` (en `inventario`) | Una orden de un tipo que no está en `TIPOS_DE_PRODUCCION` se nombra «`OT-0231` · <texto del tipo>» («`OT-0231` · Entrega») con `url=None` (`produccion` no conoce la pantalla de `comercial`, y la de envasado es solo del Agrónomo: D-30) |
| `ReservaInsumo` | «Único `(orden, insumo_invernadero)`» sin condición y «`cantidad_utilizada ≤ cantidad_reservada`», como dice el modelo. La primera la cambia después COM-05a2 (abajo); la segunda **no la cambia nadie**: el exceso de envases de una entrega va en el consumo (D-68, punto 2; sección 10) |

Las pruebas son de PRD-01, con órdenes sueltas (`orden_suelta(invernadero, tipo, ...)`, sin hija). Cuando existen las hijas, siguen
valiendo: COM-05a1, COM-05a2 e IOT-07 no las modifican ni suman filtros.

**COM-02 y COM-04a** (D-67, punto 1e): `cosecha` está en `TIPOS_DE_PRODUCCION` desde PRD-01, pero COM-02 la oculta de la bandeja y de la
lista hasta COM-04a (las dos con un `exclude(tipo_orden=COSECHA)` y el comentario «hasta COM-04a»), porque antes no hay acciones de
cosecha; COM-04a quita esas dos líneas. `ordenes_cancelables` no necesita el `exclude`: el código de PRD-01 ya deja afuera las cosechas
(las cruza con `TIPOS_QUE_CANCELA_PRODUCCION`); COM-04a la cambia para que liste todos los `TIPOS_DE_PRODUCCION` (sección 2).
`detalle_de_orden` (`ordenes.py`) también excluye `cosecha` con el mismo comentario «hasta COM-04a» y devuelve `Http404` (su ventana de detalle todavía no existe): COM-04a quita esa línea junto con las otras dos.

### Lo que suma COM-05a2

**Funciones de núcleo nuevas, `produccion/servicios/reservas.py`.** Como las de la sección 8: corren dentro de la transacción de quien llama
(sin ella, `RuntimeError`), con el invernadero y el `InsumoInvernadero` ya bloqueados por quien llama (`docs/patrones/stock.md`, sección 5),
**no auditan ni notifican** y devuelven lo que crearon o cambiaron para el registro del caso de uso. No validan contra el stock: eso lo hace
el caso de uso, después de bloquear, con `stock.disponible_para_planificar` (`docs/api/stock.md`).

| Función | Qué hace |
|---|---|
| `reservas.reservar(orden, insumo_invernadero, cantidad, fecha) -> ReservaInsumo` | Una reserva «activa» con `cantidad_reservada = cantidad` y `fecha_reserva = fecha`, utilizada y devuelta nulas. `ErrorDeProduccion('reserva_duplicada')` si la orden ya tiene una activa de ese insumo (la base también lo impide, D-66 punto 8). `ErrorDeProduccion('orden_no_pendiente')` si la orden no está «a realizar» |
| `reservas.cambiar_cantidad(reserva, cantidad) -> ReservaInsumo` | Cambia `cantidad_reservada` de una reserva «activa»; conserva `fecha_reserva` (postcondición b de PROD-PNF-ENV). `ErrorDeProduccion('reserva_no_activa')` si no lo está |
| `reservas.cancelar(reserva) -> ReservaInsumo` | Pasa una reserva «activa» a «cancelada», con utilizada y devuelta nulas (lo mismo que hace `cancelar_orden_incluida` con cada reserva de la orden) |

**Restricción de `ReservaInsumo`** (D-66, punto 8): la migración de COM-05a2 reemplaza «Único `(orden, insumo_invernadero)`» por
`UniqueConstraint(orden, insumo_invernadero, condition=Q(estado="activa"))`. Las pruebas de PRD-01 no cambian.

**Punto de extensión que cambia** (`docs/api/extensiones_de_produccion.md`, sección 4): `EntradasDeComercial` suma el campo `envasado`
(con valor por defecto `None`, así no cambia quien ya lo construye): la lista de órdenes del Agrónomo muestra el acceso «Envasado» cuando
viene.

Pruebas en `produccion/tests/test_reservas_nucleo.py` (las tres funciones: cada efecto, cada error, sin transacción, que no auditan). Los
filtros por tipo y lo demás de la tabla de PRD-01 **no** se vuelven a probar: ya tienen sus pruebas en PRD-01.

## 10. Lo que COM-04a deja hecho para la concreción de una entrega (D-68, punto 3)

Lo escribe **COM-04a**, en su única migración de `produccion`, aunque lo use **COM-06a** (COM-CNC-ENT): así `produccion` recibe todos sus
cambios de la ronda en una tarea (D-67, punto 2; elección del estudiante del 22/11/2026). Las funciones no conocen `Entrega`: reciben una
`OrdenTrabajo` (la entrega la ve como `tipo_orden = entrega`, sección 9). Son de **núcleo**, como las de la sección 8: corren dentro de la
transacción de quien llama (sin ella, `RuntimeError`), con lo suyo ya bloqueado por quien llama (`docs/patrones/bloqueos.md`, «Concretar
una entrega»), **no auditan ni notifican** y devuelven lo que crearon o cambiaron para el único registro del caso de uso (D-36).

### Modelos (en la migración de COM-04a)

| Cambio | Qué |
|---|---|
| `Merma.Causa` | Suma `dano_en_entrega` («Daño en la entrega», MD-78; postcondición e de COM-CNC-ENT). No se ofrece en PROD-REG-MRM |
| Restricciones de PRD-01 a PRD-03 | `Merma.Causa` y `Bitacora.TipoEvento` tienen en el código una restricción con la **lista cerrada** de valores (`merma_causa_valida` y `bitacora_tipo_evento_valido`): sumar un valor a los `choices` no alcanza; la migración de COM-04a **reemplaza** las dos restricciones con la lista completa (las causas de cámara y de entrega; los tipos `cosecha`, `incumplimiento_de_clausula` y `anulacion_de_resolucion`) y suma los tipos a `bitacora.TIPOS_DE_FILTRO` (disparador «Cuando exista PRD-03 o PRD-04», punto 2) |
| `Merma.orden` | FK nula a `OrdenTrabajo`, `PROTECT`, `related_name="mermas_de_orden"` (R084, Merma «presenta» Entrega). Restricción: `orden` no nula ⇔ `causa = dano_en_entrega` |
| `Consumo.orden` | FK nula a `OrdenTrabajo`, `PROTECT`, `related_name="consumos_de_orden"` (R148, Entrega «genera» Consumo). La restricción de origen de PRD-03 pasa a **exactamente uno de `siembra`, `aplicacion` y `orden`** |

### Funciones de núcleo

| Función | Qué hace |
|---|---|
| `mermas.aplicar_merma_de_entrega(orden, lote, cantidad, descripcion, responsable) -> Merma` | `Merma` (hija de `Bitacora`, tipo `merma`) con causa `dano_en_entrega`, `orden`, el **lote de origen** (el de la línea de reserva, o el de la partida: R144), el invernadero de la orden, **sin etapa ni sectores**, fecha y hora actuales y `responsable` (regla «Merma de entrega» de COM-CNC-ENT). **No toca el lote** (ni cantidad, ni costo, ni agujeros: «no libera agujeros, porque el producto ya fue cosechado») ni crea `MovimientoStock`: lo perdido ya salió del stock con la «salida por cosecha» o con el egreso de la partida. Como no tiene etapa, no suma a la merma acumulada del umbral (`merma_acumulada`, sección 8). `ErrorDeProduccion('cantidad_invalida')` si `cantidad <= 0` |
| `camara.egresar_de_partida(partida, cantidad, origen) -> MovimientoStock` | Baja `cantidad_disponible_cosechado` en `cantidad`; `agotado` si llega a 0; `MovimientoStock` `egreso_de_camara` (origen: la orden; `costo_unitario` = el de la partida). `ErrorDeProduccion('egreso_supera_partida')` si pasa de la disponible o si la partida está `vencido` |
| `camara.devolver_a_partida(partida, cantidad, origen, hoy) -> ResultadoDevolucion(movimiento, merma)` | Regla 29 de 8.6. Si `partida.fecha_limite >= hoy` y no está `vencido`: sube la disponible, `agotado` → `disponible`, `MovimientoStock` `ingreso_a_camara` (origen: la orden) y `merma = None`. Si ya venció: el mismo ingreso y enseguida `aplicar_merma_de_partida(partida, cantidad, "vencimiento_en_camara", "", None)` (la merma por vencimiento directa); la partida conserva su estado (`vencido` sigue `vencido`, con disponible 0) |
| `consumos.cerrar_reserva(reserva, utilizada, devuelta) -> ReservaInsumo` | Cierra una reserva «activa»: `0 <= utilizada <= cantidad_reservada` y `0 <= devuelta <= cantidad_reservada − utilizada` (las restricciones de PRD-01, que no cambian); «consumida» si `reservada − devuelta > 0`, si no «cancelada». `ErrorDeProduccion('reserva_no_activa')` o `('cantidad_invalida')`. Quien llama ya **topeó** la utilizada en la reservada cuando hubo exceso (D-68, punto 2). Si PRD-01 tiene esta lógica dentro de `concretar_siembra`, sacala a esta función sin cambiar sus pruebas (como `marcar_cancelada`, sección 8) |
| `consumos.registrar_consumo_de_orden(orden, insumo_invernadero, cantidad, fecha, responsable) -> ResultadoConsumo(consumo, movimientos)` | `Consumo` (hijo de `Bitacora`, tipo interno `consumo`, como el de una aplicación: la consulta de la bitácora no lo lista) con `orden`, el invernadero de la orden, sin lote, etapa ni sectores, `cant_consumo = cantidad`, `monto_consumo = cantidad × referencia_precio` del insumo en el invernadero **al concretar** (`ROUND_HALF_UP`, 2 decimales) y `fecha_consumo = fecha`. Después, los movimientos: FEFO con `stock.proponer_lotes_fefo` y `stock.registrar_salida_por_consumo(..., origen_id=consumo.id, fecha=fecha)`, con lo que no cubren los lotes al faltante sin lote (como la siembra de PRD-01). **No valida contra el stock** (regla «Envases» de COM-CNC-ENT: el hecho ya ocurrió) ni reevalúa alertas: quien llama llama a `reevaluar_alertas_del_insumo` (`docs/api/stock.md`, regla 3) |

- **Cómo las usa COM-06a** (`docs/casos_de_uso/comercial/rutas.md`, «Cómo se aplica»): por cada origen de cada línea, `egresar_de_partida`
  (si es una partida) → `aplicar_merma_de_entrega` (lo perdido) → `devolver_a_partida` o `camara.crear_partida(..., "rechazo_en_entrega",
  ...)` (lo devuelto, según el origen); y por cada envase, `cerrar_reserva` (si tenía reserva) y `registrar_consumo_de_orden` (si lo
  consumido es mayor que 0). `produccion` no lee reservas de stock ni líneas de entrega: el reparto entre orígenes lo hace `comercial`.
- Pruebas en `produccion/tests/test_entregas_nucleo.py`, con **órdenes sueltas de tipo `entrega`** (`orden_suelta`, D-67 punto 1d): una
  por efecto y por error de cada función; la merma sin etapa no suma a `merma_acumulada`; la devolución a una partida vencida (ingreso más
  merma, estado `vencido`) y a una agotada (vuelve a `disponible`); el consumo con faltante sin lote; las dos restricciones nuevas (merma
  con orden y otra causa, consumo con dos orígenes); sin transacción (`RuntimeError`); que ninguna audita ni notifica. Las pruebas de
  PRD-01 a PRD-03 no cambian (la de la restricción de origen de `Consumo` se amplía con el tercer origen: anotala en el PR).

## 11. Lo que COM-04a deja hecho para las solicitudes de revisión (D-69, punto 3)

Lo escribe **COM-04a**, en su única migración de `produccion`, aunque lo use **COM-07a** (COM-EVL-DSC, COM-RSV-QJA y COM-ANL-SRV): como la
sección 10, así `produccion` recibe todos sus cambios de la ronda en una tarea (enmienda D-68 punto 3 y D-64 punto 4). La función no conoce
las solicitudes ni los contratos: recibe el invernadero, el tipo y el texto. Es de **núcleo**: corre dentro de la transacción de quien llama
(sin ella, `RuntimeError`), con el invernadero ya bloqueado por quien llama (`docs/patrones/bloqueos.md`, «Resolver o anular una
solicitud»), **no audita ni notifica** y devuelve el registro creado para el registro del caso de uso (D-36).

### Modelos (en la migración de COM-04a)

| Cambio | Qué |
|---|---|
| `Bitacora.TipoEvento` | Suma `incumplimiento_de_clausula` («Incumplimiento de cláusula suministrante»: postcondición f de COM-EVL-DSC y de COM-RSV-QJA) y `anulacion_de_resolucion` («Anulación de una resolución»: postcondición d de COM-ANL-SRV, D-69 punto 6) |
| Restricción | Con cualquiera de los dos tipos: `lote`, `etapa` y `cosecha` nulos (reglas «Bitácora» de los casos de uso: «sin lote, etapa productiva ni Capataz») |

### Función de núcleo

| Función | Qué hace |
|---|---|
| `bitacora.registrar_evento_de_contrato(invernadero, tipo, descripcion, responsable) -> Bitacora` | `Bitacora` del invernadero, con `tipo` (solo los dos de arriba: con otro, `ValueError`), `descripcion_evento = descripcion` (de 1 a 500, recortada; `ErrorDeProduccion('descripcion_invalida')` si queda vacía o pasa de 500), fecha y hora actuales (`inventario.servicios.stock.hoy` y la hora local), `responsable` (el Gerente que resuelve o anula), **sin lote, etapa, sectores ni cosecha**. No verifica que el invernadero esté activo (un contrato puede tener entregas de un invernadero dado de baja) |

- **La consulta de la bitácora** (PROD-CNS-BIT, PRD-03): los dos tipos se listan y se ofrecen en el filtro «Tipo» (disparador «Cuando exista
  `produccion` completa», punto 3). Sin lote, la columna del lote muestra «—».
- Pruebas en `produccion/tests/test_bitacora_de_contrato.py`: los dos tipos; otro tipo (`ValueError`); la descripción vacía, de 500 y de 501;
  sin transacción (`RuntimeError`); que no audita ni notifica; la restricción (un registro de esos tipos con lote no se guarda); la consulta
  y el filtro con un registro de cada tipo. Las pruebas de PRD-01 a PRD-04 no cambian.
