# API · `produccion` (PRD-01 y PRD-02)

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
| `ordenes.cancelar_orden_incluida(actor, orden, motivo, *, avisar=False) -> CancelacionIncluida` | PROD-CNL-ORD como parte de otro CU (PRD-04: PROD-PNR-FDS) | `actor` o `None` (InfoPonia) | Ver abajo |

`datos` son `dataclass` (`DatosDeSiembra`, `DatosDeConcrecionDeSiembra`, `DatosDeTransicion`, `DatosDeConcrecionDeTransicion`), no diccionarios, y se construyen desde el formulario con una función `desde_post`.
Cada par `resumen_de_…` / `datos_de_…` **no escribe** y devuelve lo que muestra la pantalla (valores propuestos, advertencias, errores por campo).

Todas: reciben al actor, verifican su rol y que siga activo **después de bloquear**, y lanzan `produccion.errores.ErrorDeProduccion(codigo, mensaje, campo=None)` para cualquier rechazo de negocio. Códigos que usan en común con las otras apps: `cambio_simultaneo`, `sin_permiso`, `invernadero_inactivo`.
Códigos propios: `orden_no_pendiente`, `sin_capataz_activo`, `variedad_incompatible`, `semilla_no_habilitada`, `stock_insuficiente`, `capacidad_insuficiente`, `distribucion_incompleta`, `orden_duplicada`, `fecha_invalida`, `cantidad_invalida`, `causa_obligatoria`, `motivo_obligatorio`, `motivo_largo`, `lote_con_transicion`, `lote_no_trasladable`, `sector_no_elegible`.

### `cancelar_orden_incluida`

Para un CU de otra tarea que **incluye** la cancelación de una orden (hoy solo PROD-PNF-FDS de PRD-04). Corre en la transacción del llamador y **no audita ni notifica por su cuenta**:

- `actor`: quien actúa en el CU que incluye, o `None` si actúa InfoPonia.
- Cancela solo órdenes «a realizar»; si la orden ya no lo está, lanza `orden_no_pendiente` (el llamador decide).
- Recibe el motivo ya armado y, si pasa de 300, lo recorta con «…» (el «…» cuenta dentro de los 300; no lanza `motivo_largo`).
- Devuelve `CancelacionIncluida(orden, reservas, sectores_afectados, alertas_resueltas, notificar_a)`: lo que el llamador necesita para **meter en su único registro de auditoría** (D-36) y a quién notificar (el Capataz, si `avisar=True` y está activo).
- El llamador ya tiene bloqueados invernadero, variedad y sectores en el orden de `docs/patrones/bloqueos.md`; esta función bloquea lo que le sigue (insumos de las reservas, orden y reservas).

## 2. Lectura (sin escribir, sin bloquear, sin consultas por fila)

| Función | Qué devuelve |
|---|---|
| `ordenes.ordenes_del_capataz(capataz, *, estado=None)` | **La única unión** de las órdenes de un Capataz (D-53): recorre `Siembra` y `TransicionEtapa` (y `Cosecha` cuando exista) y devuelve filas ya con lo que necesitan la bandeja, el traspaso y el aviso de baja de cuenta. Sin consultas por fila |
| `ordenes.bandeja_del_capataz(capataz) -> Bandeja` | Con `ordenes_del_capataz`: las órdenes «a realizar» asignadas a ese Capataz, ordenadas por fecha programada, después prioridad (sin valor = media), después `id`; con los grupos «vencidas», «hoy» y «próximas» |
| `ordenes.lista_de_ordenes(actor, filtros)` | Las órdenes visibles para el actor (Agrónomo a cargo; el Gerente en solo lectura) |
| `ordenes.ordenes_cancelables(actor)` | Las «a realizar» de sus invernaderos, agrupadas por invernadero y tipo |
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
| `maestros` | `registrar_traspaso(contar, traspasar)` (rol Capataz) | Al asignar un Capataz nuevo, pasan a él las órdenes «a realizar» del saliente (regla 3 de 8.22), actualizando `capataz` en cada hija (D-53); el punto admite varios registrantes y recibe el rol: IOT-05 registrará el del Técnico; audita como lo pide el contrato de `maestros/extensiones.py` (MAE-01b) | PRD-01 |
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
| `aplicaciones.registrar_aplicacion(actor, datos) -> AplicacionInsumos` | PROD-REG-APL | Agrónomo o Capataz | La aplicación, con sus consumos |
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
