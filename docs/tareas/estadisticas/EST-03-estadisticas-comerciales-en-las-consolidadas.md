# EST-03 · Estadísticas comerciales dentro de las consolidadas

Estado: pendiente (espera a COM-08c) | App: estadisticas | Rama: feature/est-03-comerciales-en-consolidadas | Ronda: Estadísticas 1

Depende de: **EST-02** y **COM-08c** (COM-CNS-EST; lote C8, D-94). Si COM-08c no está en `main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Qué resuelve.** Suma a las consolidadas del Gerente la pestaña «Comercial», que muestra los indicadores de COM-CNS-EST **llamando a sus
funciones de `comercial`** (H25: no se recalculan acá), con el período y la comparación de D-93.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| EST-CNS-CNS (indicador 8) | Consultar Estadísticas Consolidadas | docs/casos_de_uso/estadisticas/estadisticas.md | — |

## Leer

- Casos de uso: el extracto (EST-CNS-CNS, regla 3.2) y `docs/casos_de_uso/comercial/estadisticas.md` (COM-CNS-EST, su «Servicio»).
- Decisiones: D-93 (puntos 2 y 4), D-94 (las estadísticas comerciales), D-44.
- Pantallas: `stCom` (2908), como referencia de lugar; mandan los indicadores de COM-CNS-EST.
- Código a leer: lo de EST-02; `comercial/servicios/estadisticas.py` (`filtros_de_estadisticas`, `estadisticas`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: nada (si COM-CNS-EST no expone sus cálculos como funciones reutilizables con un período, frená: es un error de
  documentación del lote C8, L9). Si los filtros de COM-CNS-EST no aceptan un rango cualquiera, frená igual.
- Dependencias nuevas: ninguna.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **`consolidadas.comerciales(actor, periodo)`**: arma los filtros de COM-CNS-EST con el período (todos los invernaderos y Vendedores) y
   llama a `estadisticas(actor, filtros, hoy)` dos veces (período y anterior) para la comparación. — pruebas: `test_est_cns_cns.py` (amplía).
2. **Pestaña «Comercial».** — pruebas: `test_est_cns_cns_vistas.py` (amplía).

## Hecho cuando

- El Gerente ve en las consolidadas los mismos números que el Vendedor en COM-CNS-EST para el mismo período.
- Comando de pruebas: `python manage.py test estadisticas comercial --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`.

## Verificación a mano

1. Compará la pestaña «Comercial» del Gerente con la pestaña de estadísticas del Vendedor, mismo período.

## Cierre (M3)

README de tareas, plan de la ronda (marcala cerrada), `docs/estado.md`.
