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


## Verificación a mano (la completó Claude Code al cerrar; la hace el estudiante)

Sin datos cargados (D-95, D-96): el cargador de la primera versión de esta tarea (`comercial/verificacion.py`, `registrar_cargador`, cuentas `prueba5`) se retiró y no vuelve; los datos los creás vos a mano con los valores de abajo. La tarea **no tiene migraciones**. Cada paso dice si ya lo cubre una prueba (el recorrido es `comercial/tests/test_recorrido_estadisticas_comerciales.py`).

**Antes de empezar**

1. En PowerShell, con el entorno virtual activo: `python manage.py runserver` (no hay `migrate` que aplicar) y abrí `http://localhost:8000/`.
2. Cuentas: **Gerente**; **Vendedor A** (el de los invernaderos); **Vendedor B** (otro Vendedor, con un contrato propio); y, para el paso 11, un **Agrónomo** o **Capataz**. Las contraseñas de prueba las ponés vos (nunca en un archivo del repo).
3. Lo que tiene que existir: **dos invernaderos activos del Vendedor A**, «Norte» y «Sur», cada uno con su Agrónomo y Capataz, y una variedad «Lechuga Crespa» con un lote en Maduración de por lo menos **300 plantas** en cada uno; un segundo invernadero con otro Vendedor no hace falta. **Dos clientes** con una dirección cada uno (Comercial → Clientes → «Nuevo cliente»): persona jurídica «Verdulería Los Pinos S.R.L.», CUIT **30-71234567-1**, y «Mercado Central S.A.», CUIT **30-70123456-4** (si el sistema rechaza un CUIT, usá cualquiera válido).
4. **Los contratos** (Comercial → Contratos). Con el **Vendedor A**, para «Los Pinos», cuatro compra-ventas y un suministro:
   - **V1**: retiro en **Norte**, **10** plantas de Lechuga Crespa a **100**, fecha pactada **mañana**. Concretala hoy.
   - **V2**: retiro en **Sur**, **30** plantas a **100**, fecha pactada **hoy**. Concretala hoy.
   - **V3**: retiro en **Norte**, **20** plantas a **100**, fecha pactada **hoy**. Concretala hoy.
   - **Tres suministros chicos** (uno por entrega, así cada uno tiene una sola entrega concretada hoy): `SUM-a`, `SUM-b` y `SUM-c`, cada uno con plazo de pago **10** días, indemnización por atraso **300**, un detalle de **10** plantas a precio fijo **100**, período de 30 días, primera entrega «hoy» y, en el de `SUM-a` y el de `SUM-c`, **cantidad mínima 9** (el de `SUM-b`, 1). Con el paso diario (`python manage.py proceso_diario --solo pre_reservar_suministros`, después `--solo planificar_entregas`) y «Concretar» de «Mi ruta» del Transportista, llegá a **una entrega concretada de cada uno**: `S1` (de `SUM-a`) y `S3` (de `SUM-c`) entregando **8** de las 10 plantas (**$ 800,00** cada una: queda debajo del mínimo y el cliente tiene una discrepancia pendiente) y `S2` (de `SUM-b`) entregando las **10** (**$ 1.000,00**).
   - Con el **Vendedor B**, para «Mercado Central»: **V4**: retiro en **Norte**, **50** plantas a **100**, concretada hoy (en total $ 5.000,00).
5. **Mover fechas** (solo en tu base local de desarrollo). Concretar siempre pone la fecha de hoy; para tener un retraso, un mes anterior y una mora hay que mover fechas. En la terminal, `python manage.py shell` y pegá, cambiando los números por los de tus contratos y entregas (`OT-0231` es el 231; `CV-0007` es el 7):

   ```python
   from datetime import timedelta
   from django.utils import timezone
   from comercial.models import CompraVenta, Entrega
   hoy = timezone.localdate()
   # V2 estaba pactada hace 4 días: la entrega de hoy llega con 4 días de retraso (número de la compra-venta)
   CompraVenta.objects.filter(numero=8).update(fecha_pactada_venta=hoy - timedelta(days=4))
   # V3 se concretó el último día del mes anterior (número de la entrega de V3)
   Entrega.objects.filter(numero=233).update(fecha_resolucion_orden=hoy.replace(day=1) - timedelta(days=1))
   # S2 venció hace 5 días (número de la entrega S2): sigue concretada hoy, pero su pago venció hace 5 días
   Entrega.objects.filter(numero=236).update(fecha_vencimiento_pago=hoy - timedelta(days=5))
   ```
6. **Las solicitudes y el cobro.** Como **Gerente**, Comercial → Solicitudes: **aceptá** la discrepancia de `S1` con **descuento** (no reintegro) de **$ 300,00**; **aceptá** la de `S3` con descuento de **$ 900,00** y después **anulá esa resolución** («Anular resolución», motivo «Error de carga»). Comercial → Cobranza → «Registrar cobro» de «Los Pinos»: marcá **`S2`**, medio Transferencia, «Revisar y registrar» y «Confirmar cobro»; después «Cobros registrados» → «Anular» de ese cobro (motivo «Cargado con el cliente equivocado»).

**Lo que tienen que dar los números** (compará a mano con esto). **Vendedor A, mes actual:** ventas **$ 6.600,00** y **5** entregas concretadas (V1 1.000 + V2 3.000 + `S1` 800 + `S2` 1.000 + `S3` 800; V3 es del mes anterior), **66** plantas, a tiempo **80 %** con **1** con retraso (V2, 4 días: promedio **4,0 días**), indemnizado **$ 300,00** (1 solicitud aceptada: la anulada no cuenta), cobranza: pendiente **$ 1.300,00** (`S1` $ 500,00 con el descuento y `S3` $ 800,00) y en mora **$ 1.000,00** (`S2`, hasta 30 días: el cobro anulado volvió a ser deuda). **Mes anterior:** ventas **$ 2.000,00**, 1 entrega. **Gerente, mes actual:** ventas **$ 11.600,00** (con los $ 5.000,00 de V4).

**Los pasos**

1. **El Vendedor A abre Estadísticas.** Entrá como **Vendedor A** → «Comercial» → última pestaña, **«Estadísticas»**. **Tiene que ver:** el título «Comercial», la pestaña «Estadísticas» marcada, el texto «Resultados del período elegido. Las ventas se cuentan cuando se concreta la entrega y no descuentan indemnizaciones. La cobranza es la situación de hoy.», el período «Noviembre de 2026 (hasta hoy)» (el del mes en que estés) elegido, los desplegables de período e invernadero (**sin** «Vendedor») y el botón «Ver estadísticas». Cuatro tarjetas: **Ventas $ 6.600,00** (5 entregas concretadas), **Entregas a tiempo 80 %** (1 con retraso), **Indemnizado $ 300,00** (1 solicitud aceptada, en color de advertencia), **Cobranza en mora $ 1.000,00** (en rojo). Debajo, seis tarjetas: en «Ventas por variedad», «Lechuga Crespa» con **66** plantas, su barra a lo ancho y el monto escrito **$ 6.600,00**; «Entregas a tiempo y con retraso» con **A tiempo 4 (80 %)**, **Con retraso 1 (20 %)**, **Promedio de retraso 4,0 días** e **Intentos de entrega fallidos 0**; «Incumplimientos aceptados» **1** (0 quejas y 1 discrepancia), **Descuentos $ 300,00**, **Pagadas en dinero $ 0,00**; «Cobranza a la fecha» **Pendiente $ 1.300,00 (2 entregas)** y **En mora hasta 30 días $ 1.000,00**; «Faltantes y rechazos» en 0; «Clientes con más compras»: «Verdulería Los Pinos S.R.L.», 5 entregas, $ 6.600,00, 100 % del total. **No** tiene que aparecer «Mercado Central S.A.» ni los $ 5.000,00 de V4. *(Lo cubre el recorrido, paso 1, y `test_el_vendedor_ve_los_indicadores_del_mes_solo_de_sus_contratos`.)*
2. **Compará dos números a mano.** Las plantas de «Lechuga Crespa»: V1 10 + V2 30 + `S1` 8 + `S2` 10 + `S3` 8 = **66** (si entregaste otras cantidades, la suma de las tuyas) y su monto a $ 100 cada una (**$ 6.600,00**). Lo indemnizado: lo que aceptaste con descuento en `S1` ($ 300,00); la de `S3` anulada no cuenta. **Tiene que ver** que coincidan con la pantalla. *(Lo cubren `test_regla_3_…`, `test_regla_5_una_resolucion_anulada_no_cuenta`.)*
3. **Otro mes.** En «Período» elegí **el mes anterior** (por ejemplo «Octubre de 2026») y tocá «Ver estadísticas». **Tiene que ver:** la dirección con `?periodo=2026-10`, el mes elegido, **Ventas $ 2.000,00** (1 entrega: V3), **Entregas a tiempo 100 %**, indemnizado $ 0,00 y la **cobranza igual que antes** (es la de hoy). *(Lo cubre el recorrido, paso 2.)*
4. **Un rango que cruza los dos meses.** Elegí «Otro rango», **Desde** el primer día del mes anterior y **Hasta** hoy, «Ver estadísticas». **Tiene que ver:** **Ventas $ 8.600,00** (6.600 + 2.000), y la pantalla dice «Del …/… al …/…» con tus fechas. *(Lo cubre el recorrido, paso 3.)*
5. **Un rango de más de un año.** «Otro rango» con **Desde** hace dos años y **Hasta** hoy. **Tiene que ver:** ningún número; el aviso «Corregí el filtro para ver las estadísticas.» y debajo «El período no puede ser mayor que un año.»; los filtros siguen ahí para corregirlos. Probá también un **Hasta** de mañana («El período no puede terminar después de hoy.»), un **Desde** posterior al **Hasta** y un rango sin una de las dos fechas («Indicá las dos fechas.»). *(Lo cubren el recorrido, paso 4, y `test_regla_2_…`.)*
6. **Un invernadero.** Con el período del mes actual, elegí «Sur» y «Ver estadísticas». **Tiene que ver:** solo lo de Sur: **Ventas $ 3.000,00** (1 entrega: V2), **Entregas a tiempo 0 %** (1 con retraso, promedio 4,0 días) y **Cobranza en mora $ 0,00** (la mora de `S2` salió de Norte); «Cobranza a la fecha» en cero para Sur, porque también se filtra por invernadero. Un invernadero ajeno no se ofrece en el desplegable; escribir `?invernadero=<id de uno de otro Vendedor>` a mano muestra el aviso «Elegí uno de tus invernaderos.» *(Lo cubre el recorrido, paso 5.)*
7. **Los enlaces de cada indicador.** Con el Vendedor A, en la pantalla del mes actual: «Ver compra-ventas» (lista de compra-ventas), «Ver suministros» (la lista con «Suministros»), «Ver entregas» (la lista de entregas con el estado **«Concretadas»** ya elegido y, si elegiste un invernadero, ese invernadero), «Ver solicitudes» (la pestaña de solicitudes con **«Aceptadas»** elegido), «Ver cobranza» (la pestaña «Cobranza», «Por cobrar») y, en «Clientes con más compras», los enlaces «compra-ventas» y «suministros» de la fila (con ese cliente en el filtro del buscador). **Tiene que ver:** que ninguno lleve a «Prohibido (403)». **Lo que los enlaces NO llevan:** el período (esas listas filtran por otra fecha: la de la solicitud o la pactada) ni, en «Ver entregas», el Vendedor. Es lo que dice el «Cierre». *(Lo cubren `test_regla_10_…` y `test_ningun_enlace_lleva_a_un_403`.)*
8. **El Gerente: todo y por Vendedor.** Entrá como **Gerente** → Comercial → «Estadísticas». **Tiene que ver:** el desplegable **«Vendedor»** («Todos los Vendedores», el A y el B) y **Ventas $ 11.600,00**; «Clientes con más compras»: «Verdulería Los Pinos S.R.L.» primero ($ 6.600,00, 57 %) y «Mercado Central S.A.» ($ 5.000,00, 43 %). Elegí al **Vendedor B** y «Ver estadísticas»: **Ventas $ 5.000,00** y solo «Mercado Central S.A.»; el enlace «Ver solicitudes» lleva `?estado=aceptada&vendedor=<id>`. Escribir `?vendedor=<id de un Vendedor sin contratos>` a mano: «Elegí uno de los Vendedores de la lista.» *(Lo cubre el recorrido, paso 6.)*
9. **«Resultados del mes en curso».** Entrá como **Vendedor A** → «Panel de control». **Tiene que ver:** entre «Entregas» y «Cobranza», el título **«Resultados de noviembre de 2026 (mes en curso)»** (el mes en que estés), tres tarjetas: **Ventas $ 6.600,00** (5 entregas concretadas en el mes), **Entregas a tiempo 80 %** (1 con retraso respecto de la fecha prometida) e **Indemnizado $ 300,00** (por quejas y discrepancias aceptadas en el mes), y la línea «Para otros meses, vea Comercial › Estadísticas.» con el enlace. Cada tarjeta lleva a «Estadísticas». Como **Gerente**: el panel **no** tiene «Resultados del mes en curso». Como **Vendedor B**: el grupo en sus propios números ($ 5.000,00). *(Lo cubren el recorrido, paso 8, y `PanelDeResultadosTests`.)*
10. **Los tres casos de la tarea.** (a) Una entrega **reprogramada** (la que movió una búsqueda de transportista o un intento fallido) que se concretó el día prometido **cuenta «a tiempo»**: con V1 lo ves (pactada mañana, concretada hoy: a tiempo aunque la programada fuera otra). (b) La **resolución anulada** de `S3` no suma a «Indemnizado» (paso 1). (c) El **cobro anulado** de `S2` vuelve a contar en la cobranza en mora (paso 1); si querés verlo al revés, **registrá otra vez el cobro** de `S2` y «Estadísticas» muestra la mora en $ 0,00 y pendiente $ 1.300,00. *(Lo cubren `test_regla_4_una_entrega_reprogramada_…`, `test_regla_5_una_resolucion_anulada_no_cuenta` y `test_regla_6_…_un_cobro_anulado_vuelve_a_contar_como_deuda`.)*
11. **Otros roles y sin sesión.** Como **Agrónomo** o **Capataz**, escribí a mano `/comercial/estadisticas/`: **«Prohibido (403)»**; sin sesión te lleva a ingresar. «Estadísticas» no es una entrada del menú lateral. *(Lo cubre `test_los_demas_roles_y_los_anonimos_no_entran`.)*
12. **Un Vendedor sin contratos.** Con una cuenta de Vendedor sin contratos, «Estadísticas» muestra todo en cero y «Sin ventas en el período.» en las variedades y en los clientes, y el panel muestra «Resultados…» en $ 0,00. *(Lo cubre `test_un_vendedor_sin_datos_ve_ceros_y_sin_errores`.)*
13. **Navegador real.** Los filtros son un formulario que se envía. Abrí «Estadísticas» en una **ventana privada** (sin otra sesión), entrá como Vendedor A, elegí «Otro rango» con fechas, un invernadero y **tocá «Ver estadísticas» hasta el final**; después usá el botón «Atrás» y volvé a «Adelante». Tiene que mostrar el resultado esperado, con la dirección con los filtros y los números que cambian **sin recargar toda la página** (HTMX redibuja solo el cuerpo y deja el formulario donde está). Cambiar un desplegable **no** tiene que disparar nada: la validación corre recién al tocar el botón. Si aparece una página «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola del navegador (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
14. **Sin JavaScript.** Desactivá JavaScript y repetí los pasos 3 a 6 y 8: los desplegables vuelven a ser los nativos, «Desde» y «Hasta» siempre están a la vista, y «Ver estadísticas» recarga la **página entera** con los filtros elegidos y los números nuevos; los enlaces de cada indicador funcionan igual. Con un filtro inválido (paso 5) también se ve el motivo. *(Lo cubre `test_con_htmx_devuelve_solo_el_cuerpo_y_sin_javascript_la_pagina_entera`.)*
15. **Opcional: en un celular.** La pantalla se lee: tarjetas apiladas, tablas sin cortar los montos y los botones tocables.

## Cierre (lo completó Claude Code al cerrar, 26/11/2026)

**Qué se hizo** (en el orden de los pasos)

1. **Filtros** (`comercial/servicios/estadisticas.py`): `FiltrosDeEstadisticas` y `filtros_de_estadisticas(actor, get, hoy)` (reglas 1, 2 y 11): el mes actual hasta hoy por omisión, un mes (`?periodo=2026-10`) o un rango (`?periodo=rango&desde=…&hasta=…`), el invernadero y, solo para el Gerente, el Vendedor; los desplegables ofrecen el mes actual y los doce anteriores. Errores con código estable: `periodo_invalido`, `invernadero_fuera_de_alcance`, `vendedor_no_admitido`; `PermissionDenied` para otro rol o una cuenta inactiva. Pura: lee, no escribe ni audita; `hoy` es siempre un parámetro.
2. **Los seis indicadores** (`estadisticas(actor, filtros, hoy)` y `resultados_del_mes(actor, hoy)`), una función interna por indicador, cada una con una consulta agregada (`values().annotate()`) y nunca una por fila: ventas por variedad (3 consultas), entregas a tiempo y con retraso con la fecha prometida (2), incumplimientos aceptados (1), cobranza a hoy (1), faltantes y rechazos (4) y los diez clientes con más compras (2). Todo en `Decimal`; los porcentajes y el promedio de retraso se devuelven sin redondear y se redondean recién al mostrar (filtros de plantilla `porcentaje`, `un_decimal`).
3. **La pestaña «Estadísticas»** (`/comercial/estadisticas/`, `views_estadisticas.py`, `estadisticas/lista.html` y `_cuerpo.html`): filtros con «Ver estadísticas», las cuatro tarjetas, las seis tarjetas de indicadores con las barras en HTML y CSS (`.hbar`), los textos explicativos y los enlaces de la regla 10.
4. **«Resultados del mes en curso»** en el panel del Vendedor (`registrantes.seccion_de_entregas` y `entregas/_seccion_de_inicio.html`), entre «Solicitudes» y «Cobranza». El Gerente no lo tiene.
5. **Cierre de documentación** (propuestas en el informe de la tarea; no se aplicaron).

**Para EST-03:** `filtros_de_estadisticas(actor, get, hoy)` y `estadisticas(actor, filtros, hoy)` son públicas y puras. Los límites de la pantalla (fin ≤ hoy, 366 días) son de `filtros_de_estadisticas`; `estadisticas` acepta cualquier `desde`/`hasta` de un `FiltrosDeEstadisticas` (puede armarse con solo esas dos fechas) y vuelve a verificar el alcance (rol, invernadero, Vendedor).

**Pruebas**

- `test_com_cns_est.py` (70 pruebas): `Regla1AlcanceTests`, `Regla2FiltrosTests`, `Regla3VentasTests`, `Regla4PuntualidadTests` (con la regla 11), `Regla5IncumplimientosTests`, `Regla6CobranzaTests`, `Regla7FaltantesTests`, `Regla8ClientesTests`, `Regla10EnlacesTests`, `PostcondicionYRendimientoTests` (consulta pura: todas las sentencias son `SELECT`; mismas consultas con 2 y con 20 entregas, por indicador), `FuncionesPublicasRendimientoTests` (lo mismo para las tres funciones públicas) y `ResultadosDelMesTests`.
- `test_estadisticas_vistas.py` (16): permisos, filtros en la URL, errores sin números, HTMX y sin JavaScript, textos, enlaces con su filtro, panel con y sin «Resultados del mes en curso».
- `test_recorrido_estadisticas_comerciales.py` (2, `RecorridoDeEstadisticasComercialesTests`).
- Las pruebas en rojo se revisaron y aprobaron antes de implementar. Después de aprobadas, **corregí seis expectativas de mis propias pruebas que estaban mal armadas** (no cambié ninguna regla): el orden de dos variedades en la prueba de la regla 3 (el monto de la «otra» era menor), que el Gerente solo filtra por un Vendedor con contratos (faltaba crear la venta en la prueba de enlaces), la cantidad de entregas de la prueba de rendimiento (`poblar` crea más de 20) el armado de una venta con todo rechazado al recibir (un pago no puede ser de $ 0) y, en las pruebas de vistas, que el texto comparado ya viene sin escapar (`&`) y que `/comercial/` redirige (302).
- Resultado de M1: **`python manage.py test comercial --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **Ran 2960 tests … OK** (la primera corrida falló con «cannot pickle 'traceback' object»: eran dos corridas mías a la vez sobre las mismas bases clonadas; sola y sin `--parallel`, 2.962 pruebas OK, y de nuevo con `--parallel`, OK)**

**Decisiones de aplicación** (lo implementado distinto o lo que la documentación no dice; va a `docs/temas_abiertos.md`)

1. **El rango máximo (366 días) cuenta los dos extremos**, la misma convención que `estadisticas/periodos.py` (EST-01 y EST-02): `hasta − desde + 1 ≤ 366`, `hasta ≤ hoy`, `desde ≤ hasta`. `comercial` (nivel 6) no puede importar de `estadisticas` (nivel 8, A1), así que la convención se repite en `estadisticas.py` y una prueba de la app `estadisticas` (`estadisticas/tests/test_convencion_de_periodo.py`; ni las pruebas de `comercial` pueden importar de `estadisticas`) compara los límites con `periodos.validar`. Si cambia uno, esa prueba avisa.
2. **Filtros inválidos del Gerente** (punto 3 de la revisión): un Vendedor sin contratos o con un id que no existe da `vendedor_no_admitido`, y un invernadero que no existe, `invernadero_fuera_de_alcance`. D-94 solo nombra esos códigos para el Vendedor; se extendieron en vez de ignorar el filtro (un filtro mal escrito no debe mostrar «todo» en silencio).
3. **Las variedades sin plantas vendidas no figuran en «Ventas por variedad» ni en «Clientes con más compras»** (punto 4 de la revisión): una línea entregada en 0 es un rechazo al recibir y va al indicador 7. Sí cuenta en «entregas concretadas» de la tarjeta. D-94 punto 15 dice «Σ cant_entregada por variedad» sin aclarar este borde.
4. **Los enlaces no llevan el rango** (decisión del estudiante): los destinos filtran por otra fecha (la solicitud; la pactada o la de realización), así que el 5 lleva `estado=aceptada` (y `vendedor`) y el 7 solo el Vendedor. El 4 («Ver entregas») lleva `estado=concretada` y el invernadero, pero no el rango ni el Vendedor: la lista de entregas no los admite. Los 3 y 8 llevan el Vendedor y, en el 8, el cliente; el invernadero no (la lista de contratos no lo tiene). Y el 6 («Cobranza») no lleva nada: es una foto. Lo que no se pudo llevar no agrega filtros a otras pantallas (Límites).
5. **Un filtro inválido se muestra en el cuerpo, no bajo cada campo:** así con HTMX (que solo redibuja el cuerpo) el motivo siempre se ve. El formulario no se vuelve a pedir.
6. **El período por omisión del panel y de la pantalla es el de `hoy` pasado por parámetro** (la vista usa `stock.hoy()`, Argentina, regla 11).
7. **Índice en `OrdenTrabajo`:** no se agregó (sería una migración de `produccion`). La prueba de rendimiento solo mide la cantidad de consultas, no el tiempo; si una base grande lo pide, se anota ahí (`docs/temas_abiertos.md`).

### Pantallas: lo que se corrigió del prototipo

| Pantalla (función del prototipo) | Qué tenía | Qué se hizo | Por qué (paso o regla) |
|---|---|---|---|
| Estadísticas (`VIEWS.est`) | El período solo ofrecía tres meses fijos | El mes actual, los doce anteriores, y «Otro rango» con «Desde» y «Hasta» | Regla 2 |
| Estadísticas (`VIEWS.est`) | «Intentos de entrega fallidos» y «Con faltante» con valores fijos | Calculados | Reglas 4 y 7 |
| Estadísticas (`VIEWS.est`) | Ventas de un suministro con el precio de hoy | El `monto_pagar` de cada línea (el precio al concretar) | Regla 3 |
| Estadísticas (`VIEWS.est`) | «A tiempo» comparaba con la fecha programada | Con la fecha prometida (la pactada; la menor del período) | Regla 4 |
| Estadísticas (`VIEWS.est`) | «Vencida hasta 30 días» | «En mora hasta 30 días» (y «de 31 a 60», «más de 60») | MD-139, regla 6 |
| Estadísticas (`VIEWS.est`) | Sin enlace en «Faltantes y rechazos» ni en «Clientes» | Los dos llevan a la lista de contratos (y cada cliente, con su filtro) | Regla 10 |
| Resultados del mes (`secMes`) | El título decía un mes fijo y «Ventas» sumaba `e.monto` | El mes en curso, con el cálculo del indicador 3 | «Lo que difiere del prototipo» |
| Estadísticas (`VIEWS.est`) | Sin estados vacío ni de error | «Sin ventas en el período.», y, con un filtro inválido, «Corregí el filtro para ver las estadísticas.» con el motivo y los filtros a la vista | `.claude/rules/interfaz.md`, «Prototipos» |
| Estadísticas (`VIEWS.est`) | Los desplegables cambiaban los números al elegir | Un formulario GET con «Ver estadísticas»: sin JavaScript funciona igual y nada se valida al cambiar un desplegable | `.claude/rules/interfaz.md`, «Validaciones e interacción HTMX» |
| Estadísticas (`VIEWS.est`) | Cada tarjeta con su solo color | El monto escrito junto a cada barra; los porcentajes y promedios con «—» sin datos | Accesibilidad (no solo el color) |

**Informe de verificación (D-96)**

*Verifiqué:*
- **El recorrido** `RecorridoDeEstadisticasComercialesTests` (cliente de Django) pasa: el Vendedor ve solo lo suyo (ventas, a tiempo, indemnizado, cobranza), el mes anterior, un rango, un rango de más de un año (error, sin números) y un invernadero; el Gerente ve todo y filtra por Vendedor; los enlaces responden con su filtro; el panel del Vendedor tiene «Resultados del mes en curso» y el del Gerente no; y los tres casos de «Hecho cuando».
- **Sin migraciones:** `makemigrations --check --dry-run` → «No changes detected».
- **`git fetch`:** `main` no avanzó desde la rama (`HEAD..origin/main` vacío): ninguna otra tarea tocó `comercial/`.
- **Consulta pura:** una prueba captura las sentencias de las tres funciones públicas y comprueba que todas son `SELECT`.

*Lo cubre una prueba:* cada regla del 1 al 11 (`test_com_cns_est.py`), los permisos, los filtros en la URL, HTMX y sin JavaScript (`test_estadisticas_vistas.py`), el panel del Vendedor y el del Gerente (`PanelDeResultadosTests`) y el rendimiento (`test_rendimiento_…`).

*No pude verificar* (y por qué):
- **El navegador real:** el CSRF y el encabezado `Origin` del formulario de filtros, el comportamiento real de HTMX (el cuerpo que se redibuja, el botón «Atrás», `hx-push-url`), el aspecto de las barras y de las tarjetas y el teclado: lo ve un navegador (D-96, paso 13 de la «Verificación a mano»).
- **El rendimiento con datos reales:** la prueba mide la cantidad de consultas, no el tiempo; con una base grande, el filtro por `fecha_resolucion_orden` de `OrdenTrabajo` podría pedir un índice (sería una migración de `produccion`; `docs/temas_abiertos.md`).
- **El mes que cambia de día:** las pruebas toman `hoy` por parámetro, pero armaron sus datos con la fecha real del reloj: si corren el primer día del mes, algunas fechas relativas caen en el mes anterior (las pruebas lo evitan con rangos explícitos).
- **El despliegue en Render:** no hay migraciones; solo que la pestaña abra en producción.

**Base local de desarrollo:** no se tocó ni se borró ningún dato; no se corrió `cargar_demo`. Las bases `test_…` se reutilizaron con `--keepdb`.
