# EST-01 · App `estadisticas` y estadísticas de producción

Estado: pendiente | App: estadisticas | Rama: feature/est-01-estadisticas-de-produccion | Ronda: Estadísticas 1

Depende de: PRD-03 (hecha). **Mejor después de CON-04a** (los consumos ya con asiento no cambian lo que se mide, pero así se prueba con datos
reales). Los indicadores de cosecha esperan a COM-04a: si no está en `main`, quedan «no disponibles» (D-93 punto 5).

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** Crea la app de nivel 8 y la pantalla «Estadísticas» del Agrónomo (sus invernaderos) y del Gerente (todos): cómo rindió la
producción en un período elegido, comparado con el anterior.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| EST-CNS-PRD | Consultar Estadísticas de Producción | docs/casos_de_uso/estadisticas/estadisticas.md | Regla 6: las fórmulas son D-93 punto 3. Indicadores 1 (cosechadas) y 4: si COM-04a no está, «no disponibles» |

## Leer

- Casos de uso: el extracto, solo EST-CNS-PRD y «Cómo se aplica (código)».
- Decisiones: D-93 (la de la ronda), D-37 (con su enmienda), D-14, D-50, D-51, D-92 (punto 12: la carga inicial no es una siembra del período), D-44, D-61.
- Modelo: docs/modelo/produccion.md (`OrdenTrabajo`, `Siembra`, `Lote`, `Merma`, `Consumo`), docs/modelo/inventario.md (`TipoInsumo`, `Insumo`).
- Pantallas: docs/prototipos/compras_contabilidad/ — `VIEWS.e_main` (2864, el selector de período y «Comparar»), `stProd` (2871). **Cuidado:** el
  prototipo muestra kilos y «pérdida sobre lo cosechado»; mandan los seis indicadores del caso de uso y las fórmulas de D-93.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `produccion/models.py`, `produccion/servicios/lotes.py` y `ordenes.py` (lecturas existentes), `inventario/models.py`
  (`Consumo` está en produccion; `TipoInsumo`, `Insumo`, `InsumoInvernadero`), `iot/alertas.py` (`TIPOS_DE_ALERTA_DE_IOT`), `maestros/models.py`
  (`Alerta`, `Invernadero.tiene_sistema_iot`), `core/menu.py`, `core/acceso.py`, una app con menú como modelo (`inventario/apps.py`).

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: `config/settings.py` (`'estadisticas'` después de `'iot'`, `# nivel 8`), `config/urls.py` y
  `core/tests/urls_prueba_acceso.py` (una línea cada uno); `docs/decisiones/D-37.md` (agregar la enmienda: «Nivel 8: `estadisticas` (D-93)»);
  íconos que falten en `core/templatetags/iconos.py`; al cerrar, M3.
- Dependencias nuevas: **ninguna** (los gráficos son barras con CSS, como en el prototipo; sin bibliotecas de gráficos).
- Fuera de alcance: las consolidadas (EST-02) y lo comercial (EST-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App y período** (`periodos.py`). — pruebas: `test_periodos.py` (por defecto, atajos, anterior, validaciones, años bisiestos).
2. **Indicadores 2, 3, 5 y 6** y el 1 en su parte de sembradas. — pruebas: `test_est_cns_prd.py` (uno por indicador, alcance del Agrónomo,
   período anterior, invernadero sin IoT; órdenes con el selector «Todas» y «Solo de producción»; la merma con plantas en producción al inicio,
   incluido un lote de carga inicial).
3. **Indicadores de cosecha (1 cosechadas y 4)**, con `disponible()`. — pruebas: las mismas, con la cosecha presente o ausente.
4. **Pantalla, menú y enlaces.** — pruebas: `test_est_cns_prd_vistas.py` (403 para Capataz, Técnico, Vendedor y Contador; filtro por GET;
   enlaces con el período).

Si el tiempo apremia, lo último que se recorta es: las barras por variedad (queda la tabla).

## Hecho cuando

- El Agrónomo ve los seis indicadores de sus invernaderos (o «no disponible» donde corresponda) para el mes actual y para otro período, con la
  comparación; el Gerente, los de todos y por invernadero.
- `assertNumQueries` fijo por bloque; ninguna app importa de `estadisticas`.
- Comando de pruebas: `python manage.py test estadisticas --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`.

## Verificación a mano

1. Como Agrónomo, abrí «Estadísticas»: mes actual, con la comparación prendida.
2. Elegí «mes anterior» y un rango a mano; probá un rango de más de un año: mensaje claro.
3. Como Capataz, intentá la URL: 403.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, la enmienda de D-37 y su fila en `docs/decisiones/README.md`.
