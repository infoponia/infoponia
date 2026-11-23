# CON-04a · Asientos de producción (reapertura)

Estado: pendiente | App: produccion | Rama: feature/con-04a-asientos-de-produccion | Ronda: Contabilidad 2

Depende de: **CON-02** (si no está en `main`, frená). PRD-01 a PRD-04 ya están (PRD-04 se mergeó el 23/11/2026, PR #58, sin CON-02):
la fila de PROD-PNR-FDS la hacés acá (D-92 punto 9).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Los casos de uso de producción que hoy guardan su monto pero no asientan (D-45) pasan a generar su asiento automático. No hay
pantallas nuevas: los resúmenes y las fichas suman «el asiento que se registrará» o «el asiento registrado» donde el caso de uso lo dice.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto · fecha) | Dónde (código actual) |
|---|---|---|---|---|
| PROD-CNC-SMB | Concretar Siembra (post. j) | docs/casos_de_uso/produccion/siembra.md | Cada `Consumo` · Productos en Proceso / Insumos en Stock · `monto_consumo` · fecha efectiva de la siembra | `siembras._registrar_concrecion`, después de crear cada consumo |
| PROD-CNC-TRN | Concretar Transición (merma, post. e) | docs/casos_de_uso/produccion/transicion.md | La `Merma` · Pérdidas por Mermas / Productos en Proceso · `ResultadoMerma.costo` · fecha efectiva | `transiciones._escribir_concrecion`, después de `aplicar_merma` |
| PROD-REG-MRM | Registrar Merma (lote en pie, post. e) | docs/casos_de_uso/produccion/merma.md | La `Merma` · Pérdidas por Mermas / Productos en Proceso · `ResultadoMerma.costo` · fecha de la merma | `mermas._escribir`, después de `aplicar_merma` |
| PROD-REG-APL | Registrar Aplicación de Insumos (post. f) | docs/casos_de_uso/produccion/aplicacion_de_insumos.md | Cada `Consumo` · Productos en Proceso (si se imputó a lotes) o Gastos de Producción (si va a gasto) / Insumos en Stock · `monto_consumo` · fecha de la aplicación | `aplicaciones._escribir`, después de cada consumo y sus imputaciones |
| PROD-PNR-FDS | Poner Sector Fuera de Servicio (mermas) | docs/casos_de_uso/produccion/sector_fuera_de_servicio.md | Cada `Merma` · Pérdidas por Mermas / Productos en Proceso · su costo · fecha del fuera de servicio | `sectores_fuera_de_servicio._escribir`, después de cada `aplicar_merma` (D-92 punto 9) |

Las marcas «Fuera de la ronda (D-45)» de esos extractos, en lo contable, **se programan acá**. Las precondiciones «existe un ejercicio
vigente y existen las cuentas…» y sus extensiones no se programan (D-92 punto 2).

## Leer

- Casos de uso: de cada extracto, **solo** la postcondición del asiento, la regla «Asientos» y la sección «Fuera de la ronda (D-45)».
- Decisiones: D-92 (la de la ronda), D-86 (el contrato), D-84 (puntos 5 y 7), D-50 (punto 5, costo), D-51 (punto 4, reparto), D-45, D-44.
- API: docs/api/asientos.md (`registrar_asiento_automatico`).
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md («Contabilidad: el ejercicio se bloquea último» y «`produccion`»),
  docs/patrones/costo_del_lote.md.
- Reglas: .claude/rules/pruebas.md.
- Código a leer: `produccion/servicios/siembras.py` (`_registrar_concrecion`), `transiciones.py` (`_escribir_concrecion`), `mermas.py`
  (`aplicar_merma`, `_escribir`), `aplicaciones.py` (`_escribir`), `costos.py`; `contabilidad/servicios/asientos.py` y `contabilidad/cuentas.py`;
  las pruebas de cada caso de uso (`test_prod_cnc_smb.py`, `test_prod_cnc_trn.py`, `test_prod_reg_mrm.py`, `test_prod_reg_apl.py`) y las de
  concurrencia (`test_siembras_concurrencia.py`, `test_transiciones_concurrencia.py`, `test_merma_concurrencia.py`, `test_aplicaciones_concurrencia.py`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `contabilidad/cuentas.py` (solo el texto de `DESCRIPCION_DE_CUENTA` de las cuentas que esta tarea mueve, si
  difiere de `docs/casos_de_uso/contabilidad/plan_de_cuentas.md`); al cerrar, los archivos de M3 y `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: inventario (CON-04b), comercial (CON-04c y CON-04d), el lote existente (PRD-05), asientos hacia atrás (D-92 punto 1).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Siembra.** — pruebas: `test_prod_cnc_smb.py` (postcondición j: un asiento por consumo; consumo de $0 sin asiento) y
   `test_siembras_concurrencia.py` (concretar contra cerrar el ejercicio en cierre).
2. **Merma y transición** (las dos llaman a `aplicar_merma`; el asiento va en quien llama, D-92 «alternativas»). — pruebas:
   `test_prod_reg_mrm.py`, `test_prod_cnc_trn.py` (post. e), `test_merma_concurrencia.py`.
3. **Aplicación de insumos** (lote o gasto, según el destino del consumo). — pruebas: `test_prod_reg_apl.py`, `test_aplicaciones_concurrencia.py`.
4. **Fuera de servicio** (`poner_fuera_de_servicio`: un asiento por cada merma; la reubicación no asienta). — pruebas: `test_prod_pnr_fds.py`,
   `test_fds_concurrencia.py` (poner fuera de servicio contra cerrar el ejercicio en cierre).
5. **Resúmenes:** donde el caso de uso muestra el asiento antes de confirmar o después, mostralo (cuentas e importe).

## Hecho cuando

- Cada caso de uso de la tabla genera su asiento con las cuentas, el importe y la fecha de la tabla; el libro de gestión (CON-03a) lo muestra con
  su enlace al origen.
- Ninguna prueba previa se rompe salvo las que verificaban «no hay asiento», que se actualizan.
- Comando de pruebas: `python manage.py test produccion contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test produccion --keepdb --tag concurrencia`.

## Verificación a mano

1. Concretá una siembra con semillas y sustrato: en «Contabilidad › Libro de gestión» hay un asiento por consumo, con fecha de la siembra.
2. Registrá una merma de un lote: asiento Pérdidas por Mermas / Productos en Proceso por el costo de las plantas.
3. Registrá una aplicación a gasto (sin lotes en el alcance): asiento contra Gastos de Producción.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`; en `docs/disparadores.md`, tachá el punto 1 de «Cuando exista contabilidad con asientos».
