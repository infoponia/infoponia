# PRD-05 · Registrar Lote Existente

Estado: pendiente | App: produccion | Rama: feature/prd-05-registrar-lote-existente | Ronda: Contabilidad 2

Depende de: **CON-02** (el asiento) y PRD-03 (la bitácora; hecha). No depende de PRD-04. Si CON-02 no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). La pantalla no está en el prototipo: armala con el patrón de la siembra (D-61) y anotala en el «Cierre».

**Qué resuelve.** Al poner en marcha InfoPonia, el Agrónomo carga los lotes de plantas que ya estaban en los sectores (con su etapa actual y un
costo estimado), para seguir planificando sus transiciones y cosechas desde el sistema. Su valor entra contra **Capital Inicial**. Solo se puede
en un invernadero que todavía no tuvo siembras por el flujo normal.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| PROD-REG-LTE | Registrar Lote Existente | docs/casos_de_uso/produccion/lote_existente.md | Precondición d: no se programa (D-92 punto 2) |

## Leer

- Casos de uso: el extracto completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/produccion.md (`Siembra`, `Lote`, `OcupacionSector`, `Bitacora`).
- Decisiones: D-92 (punto 12), D-86, D-50, D-51, D-53, D-83, D-44, D-61.
- API: docs/api/asientos.md, docs/api/produccion.md (códigos de error).
- Patrones: docs/patrones/bloqueos.md («`produccion`» y «Contabilidad»), docs/patrones/costo_del_lote.md, docs/patrones/auditoria.md.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `produccion/models.py` (`ConCapataz`, `OrdenTrabajo`, `Siembra`, `Lote`, `OcupacionSector`, `Bitacora`); `produccion/servicios/siembras.py`
  (`planificar_siembra`, `_registrar_concrecion`: el modelo de escritura), `transiciones.py` (`_sectores_del_destino`), `lotes.py`, `bitacora.py`;
  las plantillas de la planificación de siembra.

## Límites

- Crea modelos: ninguno; cambia `Siembra` (`tipo_siembra`, `capataz` nulo) y `Bitacora.TipoEvento` → revisá docs/disparadores.md.
- Migraciones: una de `produccion` (los dos campos y los CHECK); una de `core`, solo de `choices`, con `registro_lote_existente`.
- Permitido fuera de la app: `core/models.py` (la acción) y su migración; al cerrar, M3, `docs/modelo/produccion.md` (los cambios de `Siembra` y
  `Bitacora`).
- Dependencias nuevas: ninguna.
- Fuera de alcance: partidas en cámara previas y cosechas previas (asiento manual del Contador); cambiar `TransicionEtapa`.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo y migración.** — pruebas: `test_modelos_produccion.py` (amplía: los CHECK; las siembras existentes quedan `normal` y con Capataz).
2. **Lectura de la fecha de entrada** desde la carga inicial. — pruebas: `test_lotes_lectura.py` (amplía).
3. **Servicio** `lotes_existentes.py` con el asiento. — pruebas: `test_prod_reg_lte.py`, `test_prod_reg_lte_concurrencia.py`.
4. **Pantalla** (formulario, resumen, confirmación) y el filtro «Carga inicial» de la bitácora. — pruebas: `test_prod_reg_lte_vistas.py`,
   `test_prod_cns_bit.py` (amplía).

## Hecho cuando

- En un invernadero sin siembras, el Agrónomo carga un lote en Maduración en dos sectores con costo $12.000: el lote aparece en la lista, los
  agujeros bajan, la bitácora muestra «Carga inicial» y el libro tiene Productos en Proceso / Capital Inicial por $12.000; con costo $0, sin
  asiento. Planificar su cosecha usa la fecha de ingreso a Maduración cargada.
- Concretada una siembra normal, la acción desaparece para ese invernadero.
- Comando de pruebas: `python manage.py test produccion contabilidad core --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test produccion --keepdb --tag concurrencia`.

## Verificación a mano

1. Con un invernadero de verificación sin siembras, registrá un lote existente en una etapa intermedia y mirá el lote, la bitácora y el asiento.
2. Planificá su transición: la fecha mínima sale de la fecha de ingreso cargada.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/modelo/produccion.md`; la pantalla nueva en «Pantallas: lo que se corrigió del prototipo».
