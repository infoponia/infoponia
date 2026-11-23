# COM-08c · Estadísticas comerciales y «Resultados del mes en curso»

Estado: pendiente | App: comercial | Rama: feature/com-08c-estadisticas | Ronda: Comercial 1

Depende de: **COM-08b** (por el orden de la cadena) y, con ella, **COM-08a** (`estado_de_pago` con «pagada», `LineaPago`) y toda la cadena.
Si COM-08a no está mergeada, frená. COM-08c no tiene migraciones ni toca los servicios de COM-08b: si hiciera falta, puede programarse en
paralelo con COM-08b (D-94, punto 1); en ese caso, la prueba del indicador 6 con un cobro anulado se suma cuando las dos estén en `main`.

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9). Las pantallas son una referencia (D-61): lo que les falte para el caso de uso, completalo y
anotalo en el «Cierre».

**Qué resuelve.** La última parte de COM-08 y de la ronda (D-94, punto 1): el Vendedor y el Gerente ven, para un período y un invernadero,
**cómo rinden las ventas, las entregas y la cobranza**: ventas por variedad, entregas a tiempo y con retraso, incumplimientos aceptados con lo
indemnizado, la cobranza de hoy por antigüedad, los faltantes y rechazos de compra-venta y los diez clientes que más compraron. El Vendedor,
además, tiene en su panel los **resultados del mes en curso**. Es una consulta: no escribe nada.

## Casos de uso incluidos

| Código | Caso de uso | Extracto | Marcas |
|---|---|---|---|
| COM-CNS-EST | Consultar Estadísticas Comerciales (alto nivel) | docs/casos_de_uso/comercial/estadisticas.md | Regla 7: fechas del D-94, punto 15 |

## Leer

- Casos de uso: docs/casos_de_uso/comercial/estadisticas.md **completo**; de cobranza.md, «Estado de pago y monto a cobrar»; de
  solicitudes.md, «La lista» (los filtros por estado y fecha, para el enlace de la regla 10); de compra_venta.md, «COM-CNS-CVT» (los filtros
  de la lista de contratos); de entregas.md, la lista de entregas y sus filtros.
- Modelo: docs/modelo/comercial.md (Entrega, DetalleEntrega, CompraVenta, DetalleVenta, Suministro, SolicitudRevision, IntentoFallido,
  PagoCliente, LineaPago, ReservaStock); docs/modelo/produccion.md (`OrdenTrabajo`).
- Decisiones: **D-94** (puntos 1 y 15), D-69 (punto 9), D-68 (punto 7), D-28, D-25.
- Patrones: docs/patrones/abm.md (sección 1: vistas que solo orquestan).
- API: `core/extensiones.py` (`registrar_seccion_de_inicio`).
- Pantallas: docs/prototipos/comercial/ (`README.md`): `VIEWS.est` (línea 1214), `kpi` (línea 1411), `VIEWS.com` (línea 1485), `secMes`
  (línea 1725), `secComercial` (línea 1548), `comTabs`.
- Reglas: .claude/rules/pruebas.md, .claude/rules/interfaz.md.
- Código a leer: `comercial/` (en especial `servicios/entregas.py` —`monto_a_cobrar`, `estado_de_pago`, la lista de entregas—,
  `servicios/cobranza.py`, `servicios/solicitudes.py` —la lista—, `servicios/contratos.py` o donde esté la lista de contratos, las vistas de
  la pestaña «Comercial» y `apps.py` —la sección del panel—, las fábricas).

## Límites

- Crea modelos: ninguno. Migraciones: **ninguna**.
  → revisá docs/disparadores.md: no cierra ninguno (no hay disparadores de las estadísticas).
- Permitido fuera de `comercial`: al cerrar (M3), los textos de `docs/tareas/README.md`, `docs/tareas/ronda_comercial_1.md` y
  `docs/estado.md`. Dentro de `comercial`, la sección «Comercial» del panel suma «Resultados del mes en curso» para el Vendedor. **No agrega
  filtros a otras pantallas**: si el enlace de un indicador no puede llevar un filtro, lleva los que la pantalla admite y se anota en el
  «Cierre».
- Dependencias nuevas: ninguna (las barras son HTML y CSS).
- Fuera de alcance: comparaciones entre períodos, proyecciones y exportación (regla 9 y PCU 15); un índice nuevo en `OrdenTrabajo` (sería una
  migración de `produccion`; si hace falta, a `docs/temas_abiertos.md`).

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Filtros** (`estadisticas.md`, «Filtros»). Pruebas: en `test_com_cns_est.py`, las de las reglas 1, 2 y 11.
2. **Los indicadores** (`estadisticas.md`, «Indicadores»), uno por uno, con su prueba antes de seguir con el siguiente. Pruebas:
   `test_com_cns_est.py` (reglas 3 a 8, que no escribe, sin consultas por fila).
3. **La pestaña «Estadísticas»** (`estadisticas.md`, «Pantallas»), con los enlaces de la regla 10. Pruebas: `test_estadisticas_vistas.py`.
4. **«Resultados del mes en curso»** en el panel del Vendedor. Pruebas: en `test_estadisticas_vistas.py`.
5. **Cierre de documentación.** Proponé, sin aplicarlos (M3): marcar COM-08c en `docs/tareas/README.md` y en el plan (y, si es la última de
   la ronda, la ronda como hecha en `docs/estado.md`); lo distinto de lo escrito, a `docs/temas_abiertos.md`; y la lista «Pantallas: lo que
   se corrigió del prototipo» (D-61).

Si el tiempo apremia, lo último que se recorta es el filtro por rango de fechas (queda el mes; anotado en `docs/temas_abiertos.md`). No se
recortan el alcance del Vendedor, ningún indicador ni la prueba de que no escribe nada.

## Hecho cuando

- El Vendedor abre Comercial › Estadísticas y ve los ocho indicadores del mes actual solo de sus contratos; cambia el mes, el rango y el
  invernadero y los números cambian; desde cada indicador llega a la consulta con el mismo filtro.
- El Gerente ve todo y filtra por Vendedor.
- El panel del Vendedor muestra «Resultados del mes en curso» (ventas, entregas a tiempo e indemnizado) con el enlace a Estadísticas; el del
  Gerente no.
- Una entrega reprogramada que se concretó en la fecha prometida cuenta «a tiempo»; una resolución anulada no cuenta; un cobro anulado vuelve
  a contar como deuda.
- Todas las pruebas de `comercial` siguen pasando.
- Comando de pruebas:
  python manage.py test comercial --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion

## Verificación a mano (la completa Claude Code al cerrar)

**Datos para verificar** (`CLAUDE.md`, «Datos para la verificación a mano»; `docs/patrones/datos_de_verificacion.md`): antes de pedirle
al estudiante la verificación, Claude Code deja la base local cargada con lo que piden los pasos de abajo, ampliando el cargador de
`comercial` (`comercial/verificacion.py`, registrado en `ComercialConfig.ready()` con `registrar_cargador`, orden 20; lo crea COM-01;
cuentas `<rol>@prueba<N>.local` con el número libre al crearlo: hoy `prueba5`, porque `maestros` usa 1 y 2, `iot` 3 y `produccion` 4),
siempre llamando a los servicios. El estudiante no carga datos a mano. En el «Cierre», qué quedó cargado y con qué cuentas.

No hay migraciones. Datos: los de COM-08b (ventas y suministros concretados en este mes y en el anterior, una entrega reprogramada, una
discrepancia aceptada y otra anulada, cobros vigentes y uno anulado, una venta con faltante rechazado y otra cancelada).

1. Con el Vendedor: las cuatro tarjetas y los seis indicadores del mes; compará a mano dos números (las ventas de una variedad y lo
   indemnizado).
2. Cambiá al mes anterior y a un rango que cruce los dos: los números cambian; un rango de más de un año da error.
3. Filtrá por un invernadero: solo lo de ese invernadero; la cobranza sigue siendo la de hoy.
4. Seguí el enlace de «Incumplimientos aceptados»: la pestaña de solicitudes con el filtro.
5. Con el Gerente: filtrá por Vendedor.
6. El panel del Vendedor: «Resultados del mes en curso»; el del Gerente no lo tiene.
7. Sin JavaScript: los filtros funcionan.

## Cierre (la completa Claude Code al cerrar)

<!-- Al cerrar, Claude Code suma, si corrigió o completó pantallas (D-61):
### Pantallas: lo que se corrigió del prototipo
| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
-->
