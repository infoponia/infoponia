# CMP-05 · Pago a proveedores

Estado: pendiente | App: compras | Rama: feature/cmp-05-pago-a-proveedores | Ronda: Compras 1

Depende de: **CMP-04**, **USR-11** (rol Contador) y **CON-02**. Si alguna no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Cuando una orden quedó recibida (o cerrada con faltante) para un proveedor, el **responsable contable** ve ese pago pendiente,
lo **registra** (fecha, medio, comprobante) y se genera el **asiento** (Proveedores contra Caja o Banco). La cuenta Proveedores de esa orden queda
en cero.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-REG-PAG | Registrar Pago a Proveedor | docs/casos_de_uso/compras/pagos.md | — |
| CMP-BAJ-PRV (precondición d) | Pago pendiente impide la baja del proveedor | docs/casos_de_uso/compras/proveedores.md | Completa CMP-01 |

## Leer

- Casos de uso: `pagos.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`Pago`), docs/modelo/contabilidad.md.
- Decisiones: D-91 (la del pago), D-89 (monto = suma del valor final), D-87 (menú «Pagos a proveedores»), D-84 a D-86, USR-11 (rol Contador), D-44.
- API: docs/api/asientos.md (`registrar_asiento`, `ejercicio_para`, `puede_registrar_asientos`), docs/api/notificaciones.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/bloqueos.md.
- Pantallas: `tabPag` (pestaña «Pagos» de Compras), `VIEWS.c_pag`, `panelCon` y `panelGer` (pagos pendientes). El medio va sin
  preselección (H23; el prototipo ya lo corrige: sin elegir, «Elija el medio de pago.»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-04; `contabilidad/servicios/asientos.py`, `contabilidad/apps.py` (el menú «Contabilidad»); `core/acceso.py` (cómo se
  verifica el permiso del responsable contable).

## Límites

- Crea modelos: `Pago` → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0005_pagos.py`; una de `core` con `registro_pago_proveedor`.
- Permitido fuera de la app: `core/models.py` (acción) y su migración; `compras/apps.py` registra la entrada de menú «Pagos a proveedores» y el enlace
  de origen `Pago`; al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: corrección de recepción después del pago (CMP-06 la impide); pagos parciales (no existen: un pago por orden y proveedor).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelo** `Pago` (único por orden y proveedor). — pruebas: `test_modelos.py` (amplía).
2. **`pagos_pendientes()`** y **`avisar_si_quedo_para_pagar`** (lo llaman la recepción y el cierre con faltante de CMP-04). — pruebas:
   `test_pagos_pendientes.py`.
3. **CMP-REG-PAG** con el asiento; precondición d de la baja del proveedor. — pruebas: `test_cmp_reg_pag.py`, `test_pagos_concurrencia.py` (dos
   pagos a la vez de la misma orden y proveedor; pago contra cierre del ejercicio).
4. **Pantallas**, menú e inicio del Contador. — pruebas: `test_pagos_vistas.py`.

## Hecho cuando

- Recibida la orden, el Contador (o el Gerente si es el responsable contable) ve el pago pendiente, lo registra y la cuenta Proveedores de esa orden
  da cero en el libro.
- Nadie sin permiso contable registra pagos; un segundo pago se rechaza.
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Con la orden recibida de CMP-04, entrá como Contador: «Pagos a proveedores» la muestra.
2. Registrá el pago por transferencia: el asiento usa Banco y el pendiente desaparece.
3. Intentá dar de baja ese proveedor antes del pago (con otra orden): rechazo con enlace.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`.
