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
- Pantallas: docs/prototipos/compras_contabilidad/ — `VIEWS.e_main` (2866, el selector de período y «Comparar»), `stProd` (2892). Ya sigue los seis
  indicadores del caso de uso y las fórmulas de D-93 (con el selector «Todas / Solo de producción»); sus datos de producción son sintéticos.
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

> Para quien verifica. Es autocontenido: no hace falta haber visto la sesión ni el código. Las bases de prueba (`test_…`) las usa el CI; esto se hace en tu base de
> desarrollo. **No toqué tu base de desarrollo** durante la tarea: no cargué ni borré datos.

### Antes de empezar

1. En la terminal, con el entorno virtual activo: `python manage.py migrate` (esta tarea no tiene migraciones: no debería aplicar nada) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas que necesitás (con la contraseña de tus cuentas de prueba): un **Agrónomo** con al menos un invernadero a cargo, el **Gerente**, un **Capataz**, un **Técnico**, un **Vendedor** y un **Contador**.
3. Datos. Si tu base ya tiene un invernadero con lotes, mermas y consumos de otras verificaciones, podés usarlos: anotá lo que ves y comprobalo contra la lista de cada paso. Si no, creá esto a mano (todo como Agrónomo, con fecha de **hoy** salvo que se diga otra cosa):
   1. Un invernadero activo **«Estadísticas Norte»** con un sector de Germinación de 200 agujeros (Producción → Invernaderos → Nuevo invernadero, y «Agregar sector»), asignado a tu Agrónomo y con un Capataz.
   2. Una variedad con su ciclo y su semilla habilitada con stock de 500 unidades en el invernadero (Inventario).
   3. Una **siembra** de 100 plantines (Producción → Órdenes → Nueva siembra) y **concretala** como el Capataz (celular) con fecha de siembra **5 días atrás**. Eso crea el lote y el consumo de la semilla.
   4. Una **merma** de 5 plantas por «Plaga» (Producción → Bitácora → Registrar merma) con fecha de hoy.
   5. Una **aplicación de insumos** con un insumo de una categoría que admita consumo directo (Producción → Bitácora → Registrar aplicación), por ejemplo 2 kg de nutriente.
   6. Una **orden de siembra** a realizar con fecha programada **hace 3 días** (para que cuente como vencida: planificala con la fecha de hoy y, si el sistema no deja una pasada, usá una orden vieja que ya tengas).
   7. Un **segundo invernadero «Estadísticas Sur»** sin IoT, de otro Agrónomo o del mismo, con otra siembra de 40 plantines concretada hace 4 días.
   8. Para «Alertas del IoT»: un sistema IoT registrado en «Estadísticas Norte» (IoT → Sistema) y alguna alerta de IoT del período (si no tenés, ese bloque solo se verifica «no aparece» en el Sur).
   - La **cosecha** se arma con el flujo de Comercial (cosecha planificada y concretada). Si no tenés ninguna, las tarjetas «Plantas cosechadas» y «Costo por planta» muestran 0 y «—»: es lo correcto.

### Pasos

Marcá con ✔ lo que ya cubre una prueba (así, si tenés poco tiempo, te concentrás en lo que se ve y se siente).

1. **Entrada de menú** (Agrónomo). Entrá como Agrónomo. En el menú lateral tiene que haber «**Estadísticas**» (ícono de barras), después de «Compras». ✔ menú: `test_regla_menu_*`.
2. **Mes actual con comparación** (Agrónomo). Tocá «Estadísticas». Tiene que decir «Período: 01/mm/aaaa al hoy · se compara con …» (los mismos días del período anterior), el chip «Este mes» marcado y la casilla «Comparar con el período anterior» tildada. Cinco tarjetas: Plantas sembradas, Plantas cosechadas, Merma, Órdenes a tiempo y Costo por planta cosechada. Si hay siembras en el período anterior, debajo de cada número aparece, por ejemplo, «▲ 40 (66,7 %) frente al período anterior» en verde, o «▼ …» en rojo (en merma y costo, una suba es mala y se ve roja). ✔ `test_regla_2_por_defecto_*`, recorrido paso 1.
3. **Solo sus invernaderos** (Agrónomo). Con un solo invernadero a cargo **no** hay selector de invernadero. Con dos, aparece «Invernadero» con «Todos los invernaderos» y los tuyos: elegí uno y tocá «Aplicar»; los números tienen que ser solo los de ese. No tiene que aparecer ningún invernadero de otro Agrónomo. ✔ `test_regla_1_*`.
4. **Plantas sembradas y cosechadas.** La tabla lista las variedades con su cantidad sembrada (la del lote, 100 en el ejemplo) y cosechada. **No** cuenta una carga inicial («Registrar lote existente») como sembrada del período. ✔ `EstCnsPrdSembradasYCosechadasServicioTests`.
5. **Merma.** Muestra «5 plantas perdidas sobre X en producción al inicio más Y sembradas» y la barra «Plaga». Comprobá a mano el porcentaje: 5 ÷ (X + Y) × 100 con un decimal. Una merma «en cámara» no suma acá. ✔ `EstCnsPrdMermaServicioTests` (con los cuatro casos de la lectura de D-93 + D-103).
6. **Órdenes a tiempo y vencidas.** Tabla por tipo con a tiempo, vencidas y % a tiempo, y el total «N a tiempo · M vencidas (P %)». La orden «a realizar» con fecha pasada cuenta como vencida; una que vence hoy, no; una cancelada, tampoco.
7. **«Todas» / «Solo de producción».** En la tarjeta de órdenes tocá «Solo de producción»: tienen que desaparecer las filas de Entrega y Mantenimiento (queda siembra, transición, cosecha) y el botón queda marcado. El período y lo demás que elegiste se conservan. Volvé a «Todas». ✔ `test_d93_punto_3_3_*`.
8. **Consumo de insumos.** Total del período arriba y tabla por categoría; dentro de cada una, cada insumo con **su unidad** (kg, L, unidades): las cantidades de insumos distintos no se suman. Entra la semilla de la siembra, la aplicación y los envases de las entregas. ✔ `EstCnsPrdConsumoServicioTests`.
9. **Alertas del IoT.** En «Estadísticas Norte» (con IoT) aparece la tarjeta «Alertas del IoT» con la cantidad por tipo. En «Estadísticas Sur» (sin IoT) la tarjeta **no** aparece. ✔ `test_regla_4_6_*`.
10. **Mes anterior y rango a mano** (Agrónomo). Tocá «Mes anterior»: «Período: 01/mm al fin de mes anterior». Tocá «Personalizado»: aparecen «Desde» y «Hasta» con el mes actual. Escribí dos fechas (por ejemplo, hace 10 días y hoy) y tocá «Aplicar». ✔ `test_regla_2_*`.
11. **Errores del período.** En «Personalizado»: (a) «Desde» posterior a «Hasta» → «La fecha “desde” no puede ser posterior a “hasta”.»; (b) «Hasta» en el futuro (el selector de fecha no deja elegirlo, escribilo en la URL con `&hasta=…`) → «El período no puede terminar después de hoy.»; (c) un rango de **más de un año** (por ejemplo, desde hace 14 meses) → «**El período no puede ser mayor que un año.**»; (d) dejar un campo vacío → «Indicá las dos fechas.». En todos, un aviso rojo, ninguna tarjeta y el formulario sigue para corregir. ✔ `test_regla_2_las_fechas_invalidas_*`, recorrido paso 3.
12. **«Ejercicio actual».** Tocá «Ejercicio actual»: va del inicio del ejercicio contable abierto a hoy. Si el ejercicio abarca más de un año, el mismo aviso del paso 11(c). ✔ `test_regla_2_ejercicio_*`.
13. **Con y sin comparación.** Destildá «Comparar con el período anterior» y tocá «Aplicar»: desaparece «se compara con …» y todas las diferencias. Volvé a tildarla. ✔ recorrido paso 4.
14. **Enlaces de cada bloque** (Agrónomo con un invernadero): «Ver en la bitácora» y «Ver las mermas» (abren la bitácora de ese invernadero con **las mismas fechas** del período; el de mermas con el tipo «Merma»), «Ver las órdenes» (con el invernadero), «Ver los insumos» (existencias del invernadero) y, con IoT, «Ver el monitoreo». Ninguno puede dar «Prohibido (403)». ✔ `test_regla_5_*`.
15. **Período sin actividad.** «Personalizado» con un mes viejo en que no pasó nada: «No hay actividad en este período. Probá con otro rango de fechas.».
16. **Gerente** (cerrá sesión y entrá como Gerente). «Estadísticas» muestra el consolidado de **todos** los invernaderos (la suma de «Norte» y «Sur»). Elegí «Estadísticas Sur» en «Invernadero» y «Aplicar»: solo sus números y sin la tarjeta de IoT. En el consolidado de varios invernaderos **no** aparecen «Ver en la bitácora» ni «Ver los insumos» (esas pantallas se miran de a un invernadero); eligiendo uno sí aparece la bitácora, pero **no** «Ver los insumos» (el inventario es del Agrónomo y le daría 403). ✔ `test_regla_1_el_gerente_*`, `test_regla_5_el_consolidado_*`.
17. **Roles sin acceso.** Entrá como Capataz, como Técnico, como Vendedor y como Contador: ninguno tiene «Estadísticas» en su menú (el Capataz y el Técnico ni menú tienen) y, escribiendo `http://localhost:8000/estadisticas/` en la barra, la pantalla dice «Prohibido (403)» con un mensaje que nombra su rol. ✔ `test_regla_acceso_capataz_tecnico_vendedor_y_contador_reciben_403`.
18. **Invernadero ajeno por URL** (Agrónomo). Con la cuenta del Agrónomo de «Norte», escribí `…/estadisticas/?invernadero=<id de Sur>`: avisa «No tenés acceso a ese invernadero.» y no muestra datos. ✔ `test_regla_1_un_invernadero_ajeno_*`.
19. **No audita.** Como Administrador o Gerente, mirá «Auditoría»: abrir «Estadísticas» no deja ningún registro. ✔ `test_regla_9_la_consulta_no_audita`.
20. **Navegador real** (la pantalla envía un formulario: el filtro del período). Abrí «Estadísticas» en una **ventana privada**, entrá con tu cuenta de Agrónomo y, **sin tocar nada más**, tocá «Mes anterior», «Personalizado» → escribí fechas → «Aplicar», y «Solo de producción». Cada envío tiene que recargar la pantalla con el resultado esperado. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el cliente de Django no ve. Además, copiá la dirección de la barra después de aplicar un período y pegala en otra pestaña: tiene que mostrar el mismo período (la URL se puede compartir). Con Enter dentro de un campo de fecha tiene que aplicar el período escrito (no volver a «Este mes»).
21. **(Opcional) Sin JavaScript.** Desactivá JavaScript en el navegador y repetí los pasos 7, 10 y 13: todo funciona igual (son botones de un formulario GET); el selector de invernadero se ve como lista común. Las barras son de CSS: se ven igual.
22. **(Opcional) En el celular.** El Agrónomo y el Gerente usan el marco de escritorio, pero la pantalla tiene que poder leerse y usarse en ancho angosto: las barras de merma y de alertas pasan a dos líneas y las tarjetas se apilan.

## Cierre

**Qué se hizo.** App `estadisticas` (nivel 8, D-93 punto 1; sin modelos ni migraciones) y la pantalla «Estadísticas» de producción (EST-CNS-PRD) del Agrónomo y del Gerente:

- `estadisticas/periodos.py`: período por defecto, atajos (mes, mes anterior, últimos 3 meses, ejercicio, personalizado), período anterior, validaciones y `comparar`.
- `estadisticas/servicios/produccion.py`: un servicio por indicador (1 sembradas y cosechadas, 2 merma, 3 órdenes a tiempo, 4 costo por planta cosechada, 5 consumo de insumos, 6 alertas del IoT) y `estadisticas_de_produccion`, con las consultas fijas por bloque (2, 3, 1, 1, 1 y 2; el armado completo, 11 y 21 con comparación).
- `estadisticas/views.py`, `urls.py`, `presentacion.py`, la plantilla `estadisticas/produccion.html` y `static/estadisticas/css/estadisticas.css` (barras de CSS, sin bibliotecas).
- Menú «Estadísticas» del Agrónomo y del Gerente (`apps.py`, `ready()`); `config/settings.py`, `config/urls.py`, `core/tests/urls_prueba_acceso.py` y el ícono `chart` en `core/templatetags/iconos.py`. Ninguna app importa de `estadisticas` (lo verifica una prueba).

**Pruebas.** `python manage.py test estadisticas --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **134 pruebas, OK** (37 de período, 58 de servicios, 4 de arquitectura, 34 de vistas, 1 recorrido). También verdes: `core.tests.test_menu`, `test_interfaz` y `test_usr_ini_ses` (78) y las 297 de otras apps que leen el menú. `makemigrations --check`: sin cambios.

**Decisiones.** Aplica D-93 (con la enmienda a D-37, ya escrita en `D-37.md`), D-92 punto 12, D-103, D-61, D-30, D-14. No crea una decisión nueva.

**Lo que difiere de la documentación** (para `docs/temas_abiertos.md`, sin corregirlo en silencio):
1. **Merma, «en producción al inicio»**: D-93 punto 3.2 dice «siembra concretada (`fecha_resolucion_orden`) antes de `desde`»; con D-103 (la orden de una carga inicial se resuelve el día del registro) eso dejaba fuera del denominador un lote existente sembrado antes y registrado dentro del período, y el porcentaje podía pasar de 100 %. Por decisión del estudiante (26/11/2026) se usa **`Siembra.fecha_siembra`**: cuentan «al inicio» los lotes con `fecha_siembra < desde` (también los de carga inicial); el denominador suma además lo sembrado en el período, incluidas las cargas iniciales con `fecha_siembra` en él (que **no** suman al indicador «Sembradas»). Se propone enmendar el texto de D-93 punto 3.2.
2. **Firmas**: `ordenes_a_tiempo` y `estadisticas_de_produccion` reciben `hoy` y `solo_produccion` (el selector «Todas / Solo de producción»); la segunda devuelve además el período anterior, los invernaderos del alcance y las comparaciones.
3. **`disponible()`**: hay una sola función, `cosecha_disponible()`, para los indicadores 1 (cosechadas) y 4 (D-93 punto 5 pedía una por indicador); como la cosecha (COM-04a) ya está en `main`, es solo un respaldo.
4. **«Mes anterior» y «Últimos 3 meses»** siguen D-93 (el prototipo toma «el 1 de dos meses atrás»); el prototipo admite 732 días, D-93, 366.
5. La merma de «daño en la entrega» cuenta en lo perdido (D-93 punto 3.2 la nombra) y las de cámara no cuentan ni en lo perdido ni al descontar lo que había al inicio.

**Pantallas: lo que se corrigió del prototipo** (D-61):
- Tenía: período de hasta dos años → hice: 366 días con «El período no puede ser mayor que un año.» (D-93 punto 2).
- Tenía: «Últimos 3 meses» desde el 1 de dos meses atrás → hice: el mismo día de tres meses atrás, con el último día del mes si ese día no existe (D-93 punto 2).
- Tenía: pestañas Resumen/Comercial/Compras/Resultados y «Merma en cámara» del Gerente → no las hice: son EST-02 y EST-03.
- Tenía: filtros que se aplicaban al instante (JavaScript) → hice un formulario GET con botones: funciona sin JavaScript, la URL se comparte y Enter en una fecha aplica el período escrito.
- Tenía: `<select>` nativo → hice el desplegable propio (`data-desplegable`) con el nativo como respaldo (`interfaz.md`).
- Tenía: sin estados vacíos ni de error → agregué «No tenés invernaderos para consultar», «No hay actividad en este período», los avisos del período y del invernadero ajeno, y «Disponible cuando exista la cosecha» (D-93 punto 5).
- Tenía: resaltado «warn» con umbrales fijos (merma > 8 %, órdenes < 85 %) → no lo hice: son reglas que no están en las fuentes.
- Tenía: diferencia por variedad en la tabla de cosechadas → solo en los totales de las tarjetas (lo que pide D-93 punto 2: «cada indicador se compara con su valor en el anterior»).
- Agregué: los enlaces de la regla 5 (solo los que la cuenta puede abrir, D-30), el mensaje «sin datos antes», las barras de merma y de alertas en CSS y el «Aplicar» explícito.

**Verifiqué** (con pruebas, sin navegador):
- El recorrido `RecorridoDeEstadisticasDeProduccionTests` (por rol y por estado): OK.
- `makemigrations --check`: sin cambios (la tarea no tiene migración, no hay `sqlmigrate` que leer).
- Las pruebas de `core` y de otras apps que leen el menú: OK (la entrada nueva no las rompe).
- `git fetch`: sin cambios nuevos en `main`; no hubo conflicto con `config/settings.py` ni `config/urls.py` (no hizo falta `trabajo_en_paralelo.md`).

**Lo cubre una prueba:** el alcance por rol (`test_regla_1_*`), los 403 (`test_regla_acceso_*`), el menú (`test_regla_menu_*`), los atajos y errores del período (`test_regla_2_*`, `test_periodos.py`), la comparación (`test_regla_2_*comparacion*`), el selector de órdenes (`test_d93_punto_3_3_*`), los enlaces (`test_regla_5_*`), el bloque de IoT (`test_regla_4_6_*`), cada indicador (`EstCnsPrd…ServicioTests`), las consultas fijas (`test_d93_punto_7_*`) y la arquitectura (`test_arquitectura.py`).

**No pude verificar:**
- El aspecto, el JavaScript (desplegable propio) y el CSRF/`Origin` en un navegador: está en el paso 20 de la verificación a mano.
- Que las barras, las tarjetas y las diferencias «se vean bien» en pantalla y en el celular (criterio de producto).
- El rendimiento con muchos datos reales: las pruebas fijan el número de consultas, pero no medí tiempos.
- La cosecha con datos reales de Comercial: las pruebas arman las salidas por cosecha directo en la base.

**Base de desarrollo:** no la toqué (no borré ni cargué datos).

## Cierre (M3)

README de tareas, plan de la ronda, `docs/estado.md`, la enmienda de D-37 y su fila en `docs/decisiones/README.md`.
