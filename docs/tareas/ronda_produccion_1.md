# Ronda «Producción 1» — plan completo

Plan de la ronda que construye los datos maestros y el módulo de producción de las pantallas del prototipo
(`docs/prototipos/produccion/datos_maestros_y_produccion.html`). Alcance, exclusiones y asientos fuera de la ronda: **D-45**.
Criterio de documentación y tamaño de las tareas: **D-44**. Este archivo lo lee la persona que planifica; Claude Code lo
abre solo para completar la fila de su tarea al cerrar (regla M3).

## 1. Tareas

Cada tarea es un bloque funcional: una sesión de Claude Code y un PR (D-44). El orden es el de las dependencias; las que
no dependen entre sí pueden hacerse en paralelo.

| ID | Tarea | App | Casos de uso | Depende de | Lote de documentación |
|---|---|---|---|---|---|
| UI-01 | Estilo «Diseño v2» (D-47): hoja de estilos, marco y pantallas ya hechas — **hecha el 20/11/2026** (a la espera de la revisión a mano) | core | — (no es un caso de uso) | — | 1 |

| NOT-01 | Notificaciones y campana (D-42) | core | — (característica del sistema; cierra las postcondiciones de aviso que hoy están sin implementar) | UI-01 | 1 |
| MAE-03 | Sectores y cultivos, con los tipos de etapa | maestros | PROD-ALT-SCT, PROD-MOD-SCT, PROD-BAJ-SCT, PROD-CNS-SCT, PROD-ALT-CLT, PROD-MOD-CLT, PROD-BAJ-CLT, PROD-CNS-CLT | UI-01, NOT-01 | 1 |
| MAE-04 | Configuración operativa y perfil de la organización (sin logo) | maestros | ADM-MOD-CFG, ADM-MOD-ORG | UI-01 | 1 |
| CON-01 | `OrigenDocumento`: el documento de origen común (D-52) | contabilidad | — (estructura del modelo) | — | 5 |
| INV-01 | Tipos de insumo y catálogo de insumos | inventario | CMP-ALT-TIN, CMP-MOD-TIN, CMP-BAJ-TIN, CMP-CNS-TIN, CMP-ALT-INS, CMP-MOD-INS, CMP-BAJ-INS, CMP-CNS-INS | UI-01, NOT-01, CON-01 | 2 |
| INV-02 | Insumos del invernadero, existencias, ajuste de stock y vencimientos | inventario | CMP-HAB-IIN, CMP-MOD-IIN, CMP-DSH-IIN, CMP-CNS-IIN, CMP-AJT-STK, CMP-REV-VNC | INV-01, UI-01 | 2 |
| INV-03 | Variedades, con la creación de su semilla (los modelos `Variedad`, `Ciclo` y `EtapaProductiva` los crea MAE-03 con columnas mínimas; INV-03 completa las columnas; D-49) | inventario (y migración en maestros) | PROD-ALT-VAR, PROD-MOD-VAR, PROD-BAJ-VAR, PROD-CNS-VAR | MAE-03, INV-02 (que incluye a INV-01), UI-01, NOT-01 | 3 |
| PRD-01 | Siembra: planificar, concretar, cancelar orden y bandeja del Capataz | produccion | PROD-PNF-SMB, PROD-CNC-SMB, PROD-CNL-ORD (órdenes de siembra) | MAE-03, MAE-04, INV-02, INV-03, NOT-01, CON-01 | 4 |
| PRD-02 | Transición: planificar, concretar y cancelar | produccion | PROD-PNF-TRN, PROD-CNC-TRN, PROD-CNL-ORD (órdenes de transición) | PRD-01 | 4 |
| PRD-03 | Eventos del lote: merma, aplicación de insumos, otro evento y bitácora | produccion | PROD-REG-MRM, PROD-REG-APL, PROD-REG-EVT, PROD-CNS-BIT | PRD-02 | 5 |
| PRD-04 | Sector fuera de servicio e Inicio del Agrónomo | produccion | PROD-PNR-FDS | PRD-03 | 5 |

Ya hechas o en curso fuera de la ronda: MAE-01 y MAE-01b (invernadero), MAE-02a (alerta, hecha), MAE-02b (baja y
reactivación de cuenta, Inicio del Gerente y `abrir_alerta`, mergeada el 19/11/2026) y MAE-02c (consulta de alertas, CU-46, pendiente).

## 2. Orden y paralelismo

```
UI-01 ──► (todas las tareas con pantallas)

NOT-01 ──► MAE-03 ──► INV-03 ──────────────┐
CON-01 ──► INV-01 ──► INV-02 ──► INV-03    │   (NOT-01 también llega a INV-01)
                                            │
MAE-04 ────────────────────────────────────►├──► PRD-01 ──► PRD-02 ──► PRD-03 ──► PRD-04
NOT-01, MAE-03, INV-02, CON-01 ────────────►┘
```

Dependencias de PRD-01: MAE-03, MAE-04, INV-02, INV-03 y NOT-01 (tabla de arriba). INV-03 depende de MAE-03, INV-02 (el botón «Habilitar la semilla» y la existencia de la semilla; corregido en el lote 3, antes decía INV-01), UI-01 y NOT-01. INV-01 depende también de NOT-01 (el aviso de CMP-MOD-INS b).

UI-01 va primero porque define el estilo en el que se hacen todas las pantallas (D-47). Los pasos de modelos y servicios de
las demás tareas no dependen de ella, pero sus pantallas sí: no se arma una pantalla con el estilo anterior.

- **Arranca primero:** UI-01. Después arrancan solas NOT-01 y MAE-04; INV-01 arranca cuando NOT-01 está mergeada (sus pasos de modelos y de servicios, antes). MAE-03 arranca cuando NOT-01 está mergeada
  (usa su API para la notificación de PROD-MOD-CLT b); sus pasos de sectores pueden empezar antes.
- **Sugerencia de reparto en dos carriles** (lo deciden ustedes): un carril con UI-01 y NOT-01 (`core`), y otro con INV-01 →
  INV-02 (app nueva, sin choques) y después MAE-03 e INV-03. MAE-02b ya está mergeada con el estilo anterior: UI-01
  la adapta. MAE-02c (consulta de alertas, en `maestros`) usará el estilo que esté vigente cuando se haga; si se hace en paralelo con MAE-03, MAE-04
  o INV-01, seguí `docs/patrones/trabajo_en_paralelo.md` (migraciones y `maestros/apps.py`).
- **Las cuatro de producción son una cadena** (cada una usa lo que crea la anterior): no se pueden repartir en paralelo.
- Cuando se llegue a PRD-01, las tareas de arriba tienen que estar hechas y mergeadas.

## 3. Casos de uso de la ronda → tarea

Los 38 casos de uso. El extracto de cada uno va en `docs/casos_de_uso/<app>/` y se entrega en el lote indicado.

| Caso de uso | Nombre | Tarea | Extracto |
|---|---|---|---|
| PROD-ALT-SCT / MOD / BAJ / CNS | Alta, modificación, baja y consulta de sector | MAE-03 | lote 1 |
| PROD-ALT-CLT / MOD / BAJ / CNS | Alta, modificación, baja y consulta de cultivo | MAE-03 | lote 1 |
| ADM-MOD-CFG | Modificar configuración operativa | MAE-04 | lote 1 |
| ADM-MOD-ORG | Modificar perfil de la organización | MAE-04 | lote 1 |
| CMP-ALT-TIN / MOD / BAJ / CNS | Tipo de insumo (categoría) | INV-01 | lote 2 (`casos_de_uso/inventario/tipos_de_insumo.md`) |
| CMP-ALT-INS / MOD / BAJ / CNS | Insumo del catálogo | INV-01 | lote 2 (`insumos.md`) |
| CMP-HAB-IIN / MOD-IIN / DSH-IIN / CNS-IIN | Insumo en el invernadero y existencias | INV-02 | lote 2 (`insumo_invernadero.md`) |
| CMP-AJT-STK | Ajustar stock de insumo | INV-02 | lote 2 (`ajuste_de_stock.md`) |
| CMP-REV-VNC | Revisar vencimientos de insumos | INV-02 | lote 2 (`vencimientos.md`) |
| PROD-ALT-VAR / MOD / BAJ / CNS | Alta, modificación, baja y consulta de variedad | INV-03 | lote 3 (`casos_de_uso/inventario/variedades.md`) |
| PROD-PNF-SMB, PROD-CNC-SMB | Planificar y concretar siembra | PRD-01 | lote 4 (entregado) |
| PROD-CNL-ORD | Cancelar orden (siembra y transición) | PRD-01 y PRD-02 | lote 4 |
| PROD-PNF-TRN, PROD-CNC-TRN | Planificar y concretar transición | PRD-02 | lote 4 |
| PROD-REG-MRM | Registrar merma | PRD-03 | lote 5 |
| PROD-REG-APL | Registrar aplicación de insumos | PRD-03 | lote 5 |
| PROD-REG-EVT, PROD-CNS-BIT | Registrar evento y consultar bitácora | PRD-03 | lote 5 |
| PROD-PNR-FDS | Poner sector fuera de servicio | PRD-04 | lote 5 |

## 4. Pantallas del prototipo → tarea

Las funciones son las de `docs/prototipos/produccion/README.md`.

| Pantalla (funciones) | Tarea |
|---|---|
| Marco: barra lateral, encabezado y pie (`shell`) | UI-01 |
| Campana (`alertas`, `myNotif`) | NOT-01 |
| Inicio del Gerente (`VIEWS.inicio`, `personalCard`) | MAE-02b (hecha; UI-01 la pasa al estilo v2) |
| Inicio del Agrónomo (`VIEWS.inicio`, `alertasInv`, `alertasMerma`) | PRD-04 (como sección registrada con `registrar_seccion_de_inicio` de `core/extensiones.py`, D-43) |
| Invernaderos: lista, ficha, alta, modificación, baja (`invCard`, `VIEWS.inv`, `VIEWS['inv-form']`, `MODALS['inv-baja']`) | MAE-01 y MAE-01b (hechas); UI-01 las pasa al estilo nuevo |
| Pestaña de cámara de la ficha (`camaraTab`) | **Fuera de la ronda (D-45)** |
| Sectores (`sectoresTab`, `sectorCard`, `MODALS['sector-*']`) | MAE-03 |
| Sacar un sector de servicio (`VIEWS.fs`, `fsCalc`, `ultimoAviso`) | PRD-04 |
| Cultivos (`cultivosTab`, `MODALS.cultivo`, `MODALS['cult-baja']`) | MAE-03 |
| Variedades (`VIEWS['var-form']`, `varCalc`, `MODALS['var-baja']`, `MODALS['var-umbral']`) | INV-03 |
| Configuración y organización (`VIEWS.config`, `CFG`, `cuitOk`, `aplicarMarca`) | MAE-04 (sin logo) |
| Inventario: existencias, habilitar, baja en el invernadero (`VIEWS.insumos`, `existTab`, `MODALS.habilitar`, `MODALS['ex-form']`, `MODALS['ex-baja']`) | INV-02 |
| Inventario: catálogo y categorías (`catalogoTab`, `tiposTab`, `MODALS['insumo-form']`, `insLocks`, `MODALS['cat-form']`, `MODALS['ins-baja']`) | INV-01 |
| Ajustar stock (`VIEWS.ajuste`, `ajCalc`) | INV-02 |
| Producción y órdenes (`VIEWS.prod`, `ordenesTab`, `MODALS['nueva-orden']`, `MODALS.orden`) | PRD-01 (siembra) y PRD-02 (transición) |
| Planificar siembra (`VIEWS.siembra`, `smbCalc`, `bloqueos`, `incompat`, `ritmo`, `ritmoPanel`, `reqPanel`) | PRD-01 |
| Planificar transición (`VIEWS.transicion`, `trCalc`) | PRD-02 |
| Capataz: bandeja y concretar (`VIEWS.bandeja`, `VIEWS['c-siembra']`, `csCalc`, `VIEWS['c-trans']`, `ctCalc`, `propTrans`) | PRD-01 (bandeja y siembra) y PRD-02 (transición) |
| Lotes (`lotesTab`) | PRD-01 |
| Registrar merma (`VIEWS.merma`, `mrCalc`, `mermaInfo`, `aplicarMerma`) | PRD-03 |
| Aplicación de insumos (`VIEWS.aplic`, `apCalc`, `reparto`, `fefo`) | PRD-03 |
| Bitácora y otro evento (`bitTab`, `VIEWS['bit-reg']`, `VIEWS.evento`) | PRD-03 |

## 5. Fuera de la ronda (D-45)

Cámara de frío (`camaraTab`, PROD-ASG-CAM, extensión 10c de PROD-REG-MRM), logo de la organización, datos de compras (en
tránsito = 0), asientos contables de seis casos de uso, cosecha, envasado, stock maduro y comercial. Cada uno tiene su
disparador en `docs/disparadores.md`.

## 6. Documentación por lotes (D-44)

| Lote | Contenido | Estado |
|---|---|---|
| 0 | Base: descripciones, errores corregidos, este plan, D-44 a D-47, `trabajo_en_paralelo.md` | validado |
| 1 | UI-01, NOT-01, MAE-03 y MAE-04: sus archivos de tarea, D-42 y D-48, `api/notificaciones.md`, `api/extensiones_de_maestros.md`, extractos de CU (`sectores.md`, `cultivos.md`, `configuracion.md`) y del modelo, `patrones/abm.md`, datos de migración | validado |
| 2 | INV-01 e INV-02: sus archivos de tarea, extractos de CU (`tipos_de_insumo.md`, `insumos.md`, `insumo_invernadero.md`, `ajuste_de_stock.md`, `vencimientos.md`), `modelo/inventario.md`, `patrones/stock.md`, `api/stock.md`, `api/extensiones_de_inventario.md`, corrección de D-46 y datos de migración de las categorías | validado (19/11/2026), con una revisión posterior que corrigió detalles |
| 3 | INV-03: su archivo de tarea, extracto de CU (`variedades.md`), fichas de `Semilla` y de `Variedad`/`Ciclo`/`EtapaProductiva` completas, `api/variedades.md`, los puntos de variedades de `api/extensiones_de_inventario.md`, D-49 (propuesta) y correcciones a MAE-03, INV-02 y a los puntos de `maestros` | validado (19/11/2026) |
| 4 | PRD-01 y PRD-02 (el `capataz` va en cada hija, no en el padre: D-53): sus archivos de tarea, extractos de CU (`produccion/siembra.md`, `transicion.md`, `cancelar_orden.md`), `modelo/produccion.md`, `patrones/costo_del_lote.md`, `api/produccion.md`, D-50, la sección `produccion` de `patrones/bloqueos.md`, el nivel 2c de `patrones/stock.md`, el punto `registrar_pestana_de_invernadero` de `api/extensiones_de_maestros.md` y el parámetro `fecha` de `registrar_salida_por_consumo` (`api/stock.md`, INV-02) | entregado, a validar |
| 5 | PRD-03 y PRD-04: sus archivos de tarea, extractos de CU (`produccion/merma.md`, `aplicacion_de_insumos.md`, `bitacora.md`, `sector_fuera_de_servicio.md`), D-51 (propuesta), las fichas de `AplicacionInsumos`, `ImputacionCosto`, `FueraDeServicio` y `Reubicacion`, el reparto en centavos de `costo_del_lote.md`, la sección 6 de `api/produccion.md`, las piezas de maestros, **D-52 (`OrigenDocumento` en `contabilidad`, tarea CON-01, `MovimientoInsumo.origen` en lugar de `ConsumoMovimiento`) con sus correcciones a los lotes 2 y 4** y correcciones a lotes anteriores (`LEEME_LOTE_5.md`) | entregado, a validar |

Un lote se programa recién cuando está entregado y validado por completo. **Decisión del 19/11/2026: la implementación de PRD-01 y PRD-02 empieza cuando estén los lotes 4 y 5 en el repo** (con el lote 5 entregado, la documentación de la ronda está completa) (los dos juntos). Los lotes 1 y 2 (validados) pueden programarse mientras se valida el 3.

## 7. Decisiones tomadas o por confirmar para los lotes 1 a 5

| Tema | Propuesta de trabajo (se usa hasta que se decida otra cosa) | Lote que la necesita |
|---|---|---|
| Catálogos fijos del prototipo (**confirmado el 19/11/2026**): unidades de medida, perfiles de sector y causas de merma | Listas fijas en el código (`TextChoices`), sin tabla ni migración de datos. Los tipos de etapa sí son una tabla (D-37), **con los cinco tipos del catálogo (Germinación, Crecimiento, Floración, Fructificación y Maduración) cargados por migración**, con su orden global y sus perfiles permitidos (MD-52). Solo Germinación y Maduración son obligatorias en el ciclo de toda variedad. *(Corrección del 19/11/2026: este texto decía solo dos.)* | 1, 3 y 5 |
| Notificaciones | D-42 (vigente, validada el 19/11/2026) y la API `docs/api/notificaciones.md`; NOT-01 la implementa | 1 |
| Nombre y color de la organización en `core` | D-48 (vigente, validada el 19/11/2026): punto de extensión de `core`; sin perfil, `NOMBRE_ORGANIZACION` | 1 |
| Parámetro «vigencia del enlace de decisión ante un faltante» | Se agrega a la pantalla de configuración aunque el prototipo no lo muestre: lo piden el CU y el modelo (L7) | 1 |
| Revisión diaria de vencimientos (CMP-REV-VNC, **decidido el 19/11/2026**) | Un comando de Django (`manage.py revisar_vencimientos`, nombre propuesto) que se ejecuta una vez por día como tarea programada de Render (cron job); el diseño va en el lote 2 | 2 |
| Categorías del sistema | **Cuatro** (Semillas, Envases, Repuestos de hardware e Infraestructura), como dicen el CU y el modelo; el prototipo muestra tres. `codigo` fijo para buscarlas (regla 1 de 8.23) | 2 |
| Modelos de `inventario` | Los cinco (`TipoInsumo`, `Insumo`, `InsumoInvernadero`, `LoteInsumo`, `MovimientoInsumo`) los crea INV-01, para que el catálogo se pruebe solo; INV-02 agrega comportamiento sin cambiar el esquema | 2 |
| Reservas de insumo | Punto de extensión de `inventario` por `InsumoInvernadero` (R139): `registrar_reservas_de_insumo` y `registrar_ordenes_que_reservan`. Corrige a D-46 (decía `LoteInsumo` y `registrar_reservas_de_lote`) | 2 |
| Dónde manda el CU sobre el modelo en inventario | Ajuste «otro» que suma crea lote nuevo; el faltante sin lote solo lo regulariza un recuento (o una corrección entre lotes); «sin cobertura» se mide sin lotes vencidos; sin Agrónomo las alertas de vencimiento no se generan (ver `modelo/inventario.md`, «Diferencias con el caso de uso») | 2 |
| Recuento del ajuste de stock | Por lote y de todo el insumo, como dice el CU (el prototipo cuenta un lote por vez) | 2 |
| Stock en tránsito | Columna `cant_transito_insumo` en 0; la escribirá `compras`. Sin punto de extensión propio | 2 |
| Dónde van los servicios de variedades | **D-49 (vigente, validada el 19/11/2026)**: servicios y pantallas en `inventario`, tablas en `maestros`, `Semilla(Insumo)` con FK uno a uno; las variedades de cada tarjeta de cultivo por el punto `registrar_variedades_de_cultivo` | 3 |
| Puntos de extensión de variedades | `registrar_uso_de_variedad`, `registrar_variedades_presentes` y `registrar_impedimento_de_baja_de_variedad`, declarados por INV-03 y registrados por PRD-01 y `comercial` (`docs/api/extensiones_de_inventario.md`). `registrar_uso_de_cultivo` queda solo en `inventario` | 3 |
| Largos de nombre | Cultivo hasta 40 y variedad hasta 50 caracteres (los CU no los fijan), para que el nombre de la semilla entre en los 100 del insumo | 3 |
| Semilla de una variedad dada de baja | La baja deja inactiva la semilla pero conserva sus existencias activas (regla 3 de PROD-BAJ-VAR), para poder descartar el stock con un ajuste; el CU manda sobre la regla 3 de 8.4 (`modelo/inventario.md`, «Diferencias», fila 6) | 3 |
| Precondición f de PROD-BAJ-VAR (contratos) | No se verifica hasta que `comercial` registre su impedimento; anotado en `docs/temas_abiertos.md` | 3 |
| Contraste del color principal | No se valida; queda en `docs/temas_abiertos.md` | 1 |
| Estilo del sistema (**decidido el 19/11/2026**) | El del prototipo, D-47; lo aplicó UI-01 | todos |

## 8. Disparadores existentes que cierra cada tarea

Cada archivo de tarea los trae en «Límites». Salen de `docs/disparadores.md`.

| Tarea | Disparadores que cierra |
|---|---|
| NOT-01 | «Cuando exista la primera notificación o alerta» (campana, pendientes del Gerente, avisos al personal del invernadero) |
| MAE-03 | «Cuando exista SectorProduccion» (`Invernadero.tiene_sectores`, pestaña de sectores, postcondición b de PROD-BAJ-INV) |
| MAE-04 | «Cuando exista PerfilOrganizacion» (el nombre configurable; el logo queda afuera, D-45) |
| INV-02 | «Cuando exista InsumoInvernadero» (postcondición c y precondición f de PROD-BAJ-INV, por `maestros/extensiones.py`) |
| PRD-01 | «Cuando exista Lote, OrdenTrabajo…» (precondiciones c, d y e de PROD-BAJ-INV y traspaso de órdenes del Capataz) y «Cuando exista un caso de uso que planifique…» (excluir invernaderos inactivos) |
| PRD-02 | el segundo de esos dos, para las transiciones |

No entra en la ronda: cómo se asigna el Transportista a un invernadero (R155, disparador «Cuando exista Invernadero», punto 2):
el prototipo no lo muestra y sigue pendiente de decidir.
