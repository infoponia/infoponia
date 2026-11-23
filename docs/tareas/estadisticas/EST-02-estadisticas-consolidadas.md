# EST-02 · Estadísticas consolidadas del Gerente

Estado: pendiente | App: estadisticas | Rama: feature/est-02-estadisticas-consolidadas | Ronda: Estadísticas 1

Depende de: **EST-01**, **CON-03a** (el libro: `libro.resultado_del_periodo`) y **CMP-06** (compras con correcciones). Si alguna no está en
`main`, frená.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61).

**Qué resuelve.** El Gerente ve cómo le fue a toda la organización en el período: producción comparando invernaderos, compras por proveedor y por
categoría, y ventas, costos y resultado del libro de gestión. Lo comercial (indicador 8) va en EST-03.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| EST-CNS-CNS | Consultar Estadísticas Consolidadas | docs/casos_de_uso/estadisticas/estadisticas.md | Indicador 8 (comerciales): EST-03. Regla 6: las fórmulas son D-93 punto 4 |

## Leer

- Casos de uso: el extracto, solo EST-CNS-CNS (con «Decididas») y «Cómo se aplica (código)».
- Decisiones: D-93, D-86 (lecturas del libro), D-89 (valor recibido), D-90 (correcciones), D-44, D-61.
- API: docs/api/asientos.md («Lectura»).
- Modelo: docs/modelo/compras.md (`Recepcion`, `DetalleRecepcion`, `CorreccionRecepcion`), docs/modelo/contabilidad.md (tipos de cuenta).
- Pantallas: `statsTabs`, `stRes` (2930), `stCmp` (2914), `stRtd` (2922). `stCmp` ya muestra solo lo del caso de uso (lo recibido por
  proveedor, por rubro y por mes); «pendiente de pago hoy» es del Panel (H27).
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: lo de EST-01; `contabilidad/servicios/libro.py`; `compras/servicios/` (las lecturas de recepciones y correcciones) y `compras/precios.py`.

## Límites

- Crea modelos: ninguno. Migraciones: ninguna.
- Permitido fuera de la app: al cerrar, M3.
- Dependencias nuevas: ninguna.
- Fuera de alcance: indicador 8 (EST-03).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Indicador 7** (reutiliza las funciones de EST-01 por invernadero) y **la merma en cámara**, aparte (D-93 punto 4.7). — pruebas:
   `test_est_cns_cns.py`.
2. **Indicador 9** (compras: recepciones menos correcciones del período). — pruebas: `test_est_cns_cns.py` (una corrección dentro del período y
   una fuera).
3. **Indicador 10** (libro, cruzando dos ejercicios). — pruebas: `test_est_cns_cns.py`.
4. **Pantalla** con pestañas (Resumen, Producción, Compras, Resultados) y sus enlaces. — pruebas: `test_est_cns_cns_vistas.py` (solo Gerente).

## Hecho cuando

- El Gerente compara invernaderos, ve lo comprado por proveedor y por categoría (que coincide con los asientos de recepción y corrección del
  período) y el resultado del período aunque cruce dos ejercicios.
- Comando de pruebas: `python manage.py test estadisticas --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`.

## Verificación a mano

1. Como Gerente, «Estadísticas › Compras» del mes: el total coincide con la suma de los asientos de recepción del libro en esas fechas.
2. Elegí un período que cruce el cambio de ejercicio: el resultado suma los dos.

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`.
