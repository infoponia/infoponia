# CMP-04 · Recepción de mercadería y cierre con faltante

Estado: pendiente | App: compras (y funciones en inventario) | Rama: feature/cmp-04-recepcion-y-cierre-con-faltante | Ronda: Compras 1

Depende de: **CMP-03** y **CON-02** (núcleo contable: la recepción genera asiento). Si CON-02 no está mergeada, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Agrónomo **recibe** la mercadería de una orden aprobada (total o parcial, por proveedor y por invernadero), con sus lotes y
vencimientos y los inconvenientes que encuentre (si hay, queda un **reclamo sin emitir** y una alerta para el Gerente); el stock pasa de tránsito a existencia y se registra el **asiento** (Insumos en Stock contra
Proveedores). Si un proveedor no va a entregar lo que falta, el Agrónomo **cierra la línea con faltante**.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| CMP-REG-RCP | Registrar Recepción de Mercadería | docs/casos_de_uso/compras/recepcion.md | Sobreentrega bloqueada (P3); sin tipo «retraso» (P4); el aviso «quedó para pagar» lo agrega CMP-05 |
| CMP-CRR-FLT | Cerrar Detalle con Faltante | docs/casos_de_uso/compras/recepcion.md | Sin asiento (D-90) |

## Leer

- Casos de uso: `recepcion.md` completo, incluida «Cómo se aplica (código)».
- Modelo: docs/modelo/compras.md (`Recepcion`, `DetalleRecepcion`, `InconvenienteRecepcion`, `DetalleRecepcionMovimiento`, `ReclamoProveedor`;
  `DetalleOrdenCompra.fecha_cierre_faltante`), docs/modelo/contabilidad.md (`OrigenDocumento`).
- Decisiones: D-89 (`valor_recibido` y el asiento como diferencia de valor acumulado), D-90 (la de la recepción), D-84 a D-86 (contabilidad), D-87,
  D-36, D-44.
- API: docs/api/stock.md («Escritura de compras»: `registrar_ingreso_por_recepcion`, `restar_transito`, `lotes_de_ingreso`), docs/api/asientos.md
  (`registrar_asiento`, `ejercicio_para`).
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md, docs/patrones/bloqueos.md (orden de compras, `EjercicioContable` al final).
- Pantallas: `tabRec` (pendientes de recibir), `VIEWS.c_rcp`, `VIEWS.c_flt`, la ficha de la orden («Recepciones»), `panelAgr` («Por recibir»).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de CMP-03; `inventario/servicios/stock.py` y `inventario/models.py` (`LoteInsumo`, `MovimientoInsumo`, sus tipos);
  `inventario/unidades.py` (`validar_cantidad`); `contabilidad/servicios/asientos.py` y `contabilidad/models.py`.

## Límites

- Crea modelos: `Recepcion`, `DetalleRecepcion`, `InconvenienteRecepcion`, `DetalleRecepcionMovimiento` y `ReclamoProveedor` (se crea
  abierto y sin emitir; emitirlo y cerrarlo es CMP-06) → revisá docs/disparadores.md.
- Migraciones: `compras/migrations/0004_recepciones.py`; una de `core` con `recepcion_mercaderia` y `cierre_con_faltante`.
- Permitido fuera de la app: `inventario/servicios/stock.py` (**solo** `registrar_ingreso_por_recepcion` y `lotes_de_ingreso`, tal cual
  docs/api/stock.md, con pruebas en `inventario/tests/test_ingreso_por_recepcion.py`); `core/models.py` (acciones) y su migración;
  `compras/apps.py` registra el enlace de origen `Recepcion` en `contabilidad.extensiones.registrar_enlace_de_origen`; al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: pago (CMP-05); corregir una recepción y emitir o cerrar el reclamo (CMP-06).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Modelos** (la recepción hereda `OrigenDocumento`). — pruebas: `test_modelos.py` (amplía).
2. **Ingreso por recepción en inventario** (crea lotes, mueve tránsito a existencia, un movimiento por lote). — pruebas:
   `inventario/tests/test_ingreso_por_recepcion.py`.
3. **CMP-REG-RCP** con el asiento (valor = diferencia del valor acumulado de la línea, D-89), y con inconvenientes: el reclamo sin emitir y la
   alerta al Gerente (tipo registrado en `maestros.alertas`). — pruebas: `test_cmp_reg_rcp.py` (incluye el redondeo:
   tres recepciones parciales suman exactamente el total de la línea).
4. **CMP-CRR-FLT** (baja el tránsito del faltante; sin asiento). — pruebas: `test_cmp_crr_flt.py`.
5. **Concurrencia:** dos recepciones de la misma línea; recepción contra cierre con faltante; recepción contra cierre del ejercicio. — pruebas:
   `test_recepciones_concurrencia.py`.
6. **Pantallas** y el enlace desde el asiento al documento. — pruebas: `test_recepciones_vistas.py`.

## Hecho cuando

- Una orden se recibe en dos partes y en dos invernaderos; el stock de cada uno sube, el tránsito baja, cada recepción tiene su asiento y la suma de
  los asientos es igual al total de las líneas recibidas completas.
- Una sobreentrega se rechaza; un faltante cerrado baja el tránsito y deja la línea «cerrada con faltante».
- Pruebas verdes (incluida concurrencia), sin migraciones pendientes.
- Comando de pruebas: `python manage.py test compras inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test compras --keepdb --tag concurrencia`.

## Verificación a mano

1. Recibí parte de una línea con un inconveniente «mercadería dañada»: mirá el lote creado, el asiento en el libro de gestión y,
   como Gerente, la alerta del reclamo sin emitir.
2. Recibí el resto: el asiento cierra exacto (sin centavos sueltos).
3. En otra línea, cerrá con faltante: el tránsito baja y no aparece asiento.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, `docs/disparadores.md`, `docs/modelo/inventario.md` (si cambiaste algo de los tipos).
