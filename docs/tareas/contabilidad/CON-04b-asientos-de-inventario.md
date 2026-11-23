# CON-04b · Asientos de los ajustes de stock (reapertura)

Estado: pendiente | App: inventario | Rama: feature/con-04b-asientos-de-inventario | Ronda: Contabilidad 2

Depende de: **CON-02** (si no está en `main`, frená). INV-02 ya está.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Cada movimiento de ajuste de stock de insumos genera su asiento; la **carga inicial** acredita **Capital Inicial** (H3/H4).
Es chica: va bien justo después de CON-02, antes de que se carguen los insumos reales.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Asiento (origen · Debe / Haber · monto · fecha) |
|---|---|---|---|
| CMP-AJT-STK | Ajustar Stock de Insumo (post. e) | docs/casos_de_uso/inventario/ajuste_de_stock.md | Cada `MovimientoInsumo` de ajuste · positivo: Insumos en Stock / (Capital Inicial si el motivo es «carga inicial»; si no, Diferencias de Inventario de Insumos); negativo: al revés · cantidad × `referencia_precio`, redondeado · fecha del ajuste |

**Cambia el extracto (D-92 punto 7):** la carga inicial va contra Capital Inicial, no contra Diferencias de Inventario. La corrección entre lotes
no asienta (extensión 7d, como ya dice el extracto).

## Leer

- Casos de uso: `ajuste_de_stock.md`, solo lo marcado «Fuera de la ronda (D-45)» y la regla «Asiento de un ajuste».
- Decisiones: D-92 (puntos 2 a 7), D-86, D-52 (el movimiento es el origen), D-45, D-44.
- API: docs/api/asientos.md.
- Patrones: docs/patrones/asientos.md, docs/patrones/stock.md (sección 5).
- Reglas: .claude/rules/pruebas.md.
- Código a leer: `inventario/servicios/ajustes.py`, `inventario/models.py` (`MovimientoInsumo.MotivoAjuste`,
  `InsumoInvernadero.referencia_precio`); `contabilidad/servicios/asientos.py`; las pruebas `test_cmp_ajt_stk_*.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `docs/casos_de_uso/inventario/ajuste_de_stock.md` (la línea del haber de la carga inicial, citando D-92); al cerrar,
  M3 y `docs/disparadores.md`.
- Dependencias nuevas: ninguna.
- Fuera de alcance: el asiento manual de apertura (Caja, Banco, deudas: lo hace el Contador con CON-REG-ASI).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **El asiento de cada movimiento de ajuste**, con la cuenta según el motivo y el sentido. — pruebas: `test_cmp_ajt_stk_motivos.py` (un caso por
   motivo y sentido; un ajuste cuyo valor redondea a $0,00 → sin asiento, H11), `test_cmp_ajt_stk_recuento.py` (un recuento que toca tres lotes: tres asientos).
2. **Concurrencia:** ajuste contra cierre del ejercicio. — pruebas: `test_cmp_ajt_stk_concurrencia.py`.
3. **Resumen del ajuste:** muestra el asiento que se registrará.

## Hecho cuando

- Una carga inicial de 10 kg a $500 de referencia deja Insumos en Stock 5.000 al Debe y Capital Inicial 5.000 al Haber; un recuento con faltante,
  Diferencias de Inventario al Debe.
- Comando de pruebas: `python manage.py test inventario contabilidad --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`, y
  `python manage.py test inventario --keepdb --tag concurrencia`.

## Verificación a mano

1. Hacé una carga inicial y un ajuste por rotura: mirá los dos asientos en el libro, con su enlace al movimiento.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`; en `docs/disparadores.md`, tachá el punto 0 («Inventario») de «Cuando exista contabilidad
con asientos».
