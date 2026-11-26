# EST-02 · Estadísticas consolidadas del Gerente

Estado: hecha en rama, a la espera del PR y de la revisión a mano | App: estadisticas | Rama: feature/est-02-estadisticas-consolidadas | Ronda: Estadísticas 1

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

> Para quien verifica. Es autocontenido: no hace falta haber visto la sesión ni el código. Las bases de prueba (`test_…`) las usa el CI; esto se hace en tu base de desarrollo. **No toqué tu base de
> desarrollo** durante la tarea: no cargué ni borré datos. La tarea no tiene migración.

### Antes de empezar

1. En la terminal, con el entorno virtual activo: `python manage.py migrate` (no debería aplicar nada) y `python manage.py runserver`. Abrí `http://localhost:8000/`.
2. Cuentas: el **Gerente**, un **Agrónomo** con un invernadero a cargo, un **Contador**, un **Vendedor**, un **Capataz** y un **Técnico** (con la contraseña de tus cuentas de prueba).
3. Qué crear a mano, con estos valores (si ya tenés datos parecidos de otras verificaciones, usalos y comprobá los pasos contra lo que ves). Las recepciones y las correcciones se registran **siempre con la fecha de hoy** (no hay fechas retroactivas): por eso los
   pasos 6 a 9 eligen el período «con hoy» o «hasta ayer» para dejar un hecho adentro o afuera.
   1. **Dos categorías de insumo** («Limpieza» y «Plantines»), si no existen, y en cada una un insumo habilitado en tu invernadero: **Fertilizante** (kg, categoría «Limpieza», precio de referencia $ 10,00) y **Tomate** (unidad, categoría «Plantines», precio de referencia $ 10,00).
   2. **Dos proveedores:** «Semillas del Sur S. A.» (CUIT `30-71234567-1`) y «Viveros del Este S. R. L.» (CUIT `30-70123456-8`).
   3. Un **pedido** del Agrónomo con 10 kg de Fertilizante y 8 unidades de Tomate, **cotizado** por los dos proveedores (el Sur: Fertilizante, **total $ 100,00**, plazo 3 días; el Este: Tomate, **total $ 80,00**, plazo 2 días), y su **orden de compra generada y aprobada** por el Gerente.
   4. **Recepción 1** (Agrónomo, «Por recibir»): del Sur, **4 kg** de Fertilizante (vencimiento a 90 días) → asiento por **$ 40,00**.
   5. **Recepción 2**: del Sur, **6 kg** más → asiento por $ 60,00 (acumulado 10 kg = el total $ 100,00).
   6. **Recepción 3**: del Este, **8** Tomates → asiento por $ 80,00.
   7. **Corrección:** en la recepción 2 («Corregir recepción» desde la orden) bajá **2 kg** → asiento inverso por **$ 20,00** (el valor de lo recibido pasa de $ 100,00 a $ 80,00).
   8. Para el libro: en **Contabilidad → Libro de gestión → Nuevo asiento** (como Contador o Gerente) cargá un asiento manual de **ventas** con fecha de hoy: Debe Caja $ 1.000,00 / Haber Ventas $ 1.000,00, y otro de **gasto**: Debe Gastos de Producción $ 300,00 / Haber Caja $ 300,00.
   9. **Dos ejercicios:** el cambio de ejercicio lo hace el Sistema por fecha (`proceso_diario`), así que solo sirve si tu base ya tiene dos ejercicios (Contabilidad → Ejercicios) con asientos de resultado en cada uno. Si no los tenés, saltá los pasos 11 y 12: los cubre el recorrido.
   10. Para la merma en cámara: como Agrónomo, «Producción → Registrar merma → Pérdida en cámara» sobre una partida de la cámara (5 plantas, «Daño en cámara»): desde CON-04c deja su asiento (Debe Pérdidas por Mermas / Haber Productos Terminados por cantidad × costo de la partida). Una merma de cámara **anterior** a CON-04c no tiene asiento.

### Pasos

Marcá con ✔ lo que ya cubre una prueba (así, si tenés poco tiempo, te concentrás en lo que se ve y se siente).

1. **Entrada de menú** (Gerente). Entrá como Gerente. En el menú lateral, «**Estadísticas**» (después de «Compras») abre las **consolidadas**: título «Estadísticas», cinco pestañas **Resumen · Producción · Comercial · Compras · Resultados** («Comercial» llegó con EST-03: ver esa tarea) y el período del mes hasta hoy, con la comparación tildada. ✔ `test_regla_7_menu_*`, recorrido paso 1.
2. **Resumen.** Cuatro tarjetas: **Ventas** ($ 1.000,00 con tus datos), **Compras recibidas** (el total neto del mes), **Resultado** (ventas menos costos, en rojo si es negativo) y **Plantas cosechadas**. Cada una enlaza a su pestaña y conserva el período elegido. Con la comparación tildada, debajo aparece «▲/▼ … frente al período anterior» (en verde si mejora; en las compras, subir se ve rojo). ✔ `test_pestana_resumen_*`.
3. **Producción.** Una tabla con una fila por invernadero activo (sembradas, cosechadas, merma %, órdenes a tiempo %, costo por planta, consumo y alertas del IoT; «—» donde no hay base) y la fila **«Total de la organización»**. El nombre de cada invernadero enlaza a la pantalla de producción de EST-01 con **el mismo período** y ese invernadero. ✔ `test_pestana_produccion_*`.
4. **«Todas» / «Solo de producción».** Tocá «Solo de producción» sobre la tabla: cambian los «Órdenes a tiempo» (sin entregas ni mantenimiento) y el botón queda marcado; el período se conserva. ✔ `test_regla_4_7_el_selector_de_ordenes_*`.
5. **Merma en cámara, aparte.** Debajo de la tabla, la tarjeta «Merma en cámara» con las plantas perdidas por causa y «Valor perdido». **No suma** en el % de merma de la tabla. El valor es lo que suman los asientos de esas mermas (con la merma del punto 3.10 de 5 plantas a $ 2,00: $ 10,00). Si en el período hay una merma de cámara con costo mayor que cero **sin** asiento (por ejemplo, una anterior a CON-04c), el valor dice «**—**» y una línea «Todavía no hay asientos para estas mermas.»; sin mermas de cámara en el período: «No hubo mermas en cámara en el período.» y $ 0,00. ✔ `EstCnsCnsMermaEnCamaraServicioTests`.
6. **Compras del mes** (pestaña «Compras»). Con los datos del punto 3: lo recibido en el mes es $ 40,00 + $ 60,00 + $ 80,00 = $ 180,00 y la corrección resta $ 20,00, así que **Compras recibidas = $ 160,00**. «Proveedores con compras»: 2; «Rubros comprados»: 2. Por proveedor: «Semillas del Sur» $ 80,00 (40 + 60 − 20) y «Viveros del Este» $ 80,00; por rubro: «Limpieza» $ 80,00 y «Plantines» $ 80,00 (empatan: van por orden alfabético). «Compras por mes» con una barra por cada mes del período. ✔ `EstCnsCnsComprasServicioTests`.
7. **Coincide con el libro.** En Contabilidad → Libro de gestión, filtrando por origen «Recepción» y «Corrección de recepción» (los enlaces de la pestaña «Compras» ya lo hacen, con las fechas del período): la suma del Haber de «Proveedores» de las recepciones menos el Debe de las correcciones tiene que dar el mismo total de la tarjeta. ✔ `test_d89_punto_4_y_d90_el_total_coincide_con_los_asientos_*`.
8. **Una corrección dentro y otra fuera del período.** «Personalizado» con **«Hasta» = ayer** (y «Desde» hace 10 días): como todo lo registrado es de hoy, la pestaña «Compras» dice «No se recibió mercadería en este período». Volvé a «Este mes»: reaparece todo. ✔ recorrido `test_recorrido_de_una_correccion_dentro_y_otra_fuera_del_periodo`.
9. **Corrección sobre una recepción de un día anterior** (solo si tenés una recepción de días atrás sin pago): corregila hoy y elegí un período que incluya hoy pero **no** el día de esa recepción: el total **resta** la corrección (puede dar menos que cero por proveedor) y no suma la recepción. ✔ `test_d93_punto_4_9_una_correccion_dentro_del_periodo_sobre_una_recepcion_anterior_resta`.
10. **Resultados.** Tres tarjetas: **Ingresos**, **Egresos** y **Resultado**; dos tablas «De dónde vienen los ingresos» y «En qué se gasta», por cuenta, con el importe y el % del total. Cada cuenta enlaza al libro (asientos de esa cuenta, con el período). Con los datos del punto 3: ingresos $ 1.000,00, egresos $ 300,00, resultado $ 700,00. Una cuenta con saldo contrario a su naturaleza (por ejemplo, «Diferencias de inventario») aparece con su signo. ✔ `EstCnsCnsLibroServicioTests`, `test_pestana_resultados_*`.
11. **Un período que cruza dos ejercicios** (si tenés dos). «Personalizado» con un «Desde» del ejercicio anterior y «Hasta» del actual: «Resultados» suma los asientos de los dos por **fecha del asiento** y avisa «El período cruza dos ejercicios…» con un enlace al libro por ejercicio. ✔ `test_regla_4_10_un_periodo_que_cruza_dos_ejercicios_suma_los_dos`, recorrido paso 4.
12. **Comparación contra el período anterior.** Con la casilla tildada, cada tarjeta compara con los mismos días de antes («se compara con dd/mm al dd/mm»); destildala y «Aplicar»: las diferencias desaparecen. ✔ `test_regla_2_*`.
13. **Errores del período.** «Personalizado»: «Desde» posterior a «Hasta», un «Hasta» futuro (escribilo en la URL con `&hasta=…`) o más de un año: aviso rojo con el mensaje de EST-01 y ninguna cifra; el formulario sigue para corregir. ✔ `test_regla_2_un_periodo_invalido_*`.
14. **Estados vacíos.** Un mes viejo sin movimientos: «No se recibió mercadería en este período» (Compras) y «No hay movimientos en este período» (Resultados); en Producción las filas quedan en 0 / «—».
15. **Invernadero dado de baja.** Si dás de baja un invernadero que tuvo actividad en el período, deja de tener fila propia y su actividad aparece en una fila «**Dados de baja**»; el **Total** no cambia y coincide con el consolidado del Gerente en «Estadísticas → Producción» de EST-01 (enlace «Ver el detalle de producción»). Sin actividad en el período, no hay fila «Dados de baja». ✔ `test_regla_4_7_un_invernadero_dado_de_baja_*`.
16. **Roles sin acceso.** Entrá como Agrónomo, Contador, Vendedor, Capataz y Técnico y escribí `http://localhost:8000/estadisticas/consolidadas/`: «Prohibido (403)» con un mensaje que nombra el rol. El Agrónomo sigue entrando por «Estadísticas» a producción (EST-01) y **no** ve el enlace a las consolidadas; el Contador, el Vendedor, el Capataz y el Técnico no tienen «Estadísticas» en el menú. ✔ `test_regla_1_*`, `test_regla_7_menu_*`, recorrido paso 3.
17. **Desde producción al Gerente.** Como Gerente, abrí «Estadísticas → Producción → Ver el detalle de producción»: en la pantalla de EST-01 aparece «← Estadísticas consolidadas». ✔ `test_la_pantalla_de_produccion_ofrece_volver_*`.
18. **No audita.** Como Administrador o Gerente, mirá «Auditoría»: abrir las consolidadas no deja registros. ✔ `test_regla_7_la_consulta_no_audita_*`.
19. **Navegador real** (la pantalla envía un formulario GET: las pestañas, el período y «Solo de producción»). Abrí «Estadísticas» en una **ventana privada**, entrá como Gerente y, **sin tocar nada más**, recorré las cuatro pestañas, tocá «Mes anterior», «Personalizado» → escribí fechas → «Aplicar», y «Solo de producción». Cada envío tiene que recargar con el resultado esperado y **conservar la pestaña y el período**. Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá. Copiá la dirección después de aplicar un período y pegala en otra pestaña: tiene que mostrar lo mismo. Con Enter dentro de un campo de fecha tiene que aplicar el período escrito (no volver a «Este mes»).
20. **(Opcional) Sin JavaScript.** Desactivá JavaScript en el navegador y repetí los pasos 4, 11 y 12 y el cambio de pestaña: todo funciona igual (son botones de un formulario GET; las barras son de CSS).
21. **(Opcional) En el celular.** El Gerente usa el marco de escritorio, pero la pantalla tiene que poder leerse en ancho angosto: las pestañas se desplazan de costado, la tabla de invernaderos tiene desplazamiento horizontal y las barras pasan a dos líneas.

## Cierre

**Qué se hizo.** La pantalla «Estadísticas» consolidadas del Gerente (EST-CNS-CNS, sin lo comercial) en la app `estadisticas` (sin modelos ni migraciones):

- `estadisticas/servicios/consolidadas.py`: `por_invernadero` (indicador 7, 9 consultas fijas), `merma_en_camara` (2), `compras` (indicador 9, 2), `libro` (indicador 10: 2 más 2 por cuenta de resultado del plan) y `estadisticas_consolidadas`, que arma solo la pestaña elegida
  (y la del período anterior si se compara) y exige un Gerente activo.
- `estadisticas/servicios/produccion.py`: refactor sin cambiar resultados ni consultas: los filtros de cada indicador (`_lotes_sembrados_en`, `_mermas_de_lotes`, `_ordenes_del_periodo`, `_condiciones_de_ordenes`, `_consumos_del_periodo`, `_alertas_del_periodo`, `_costo_de_la_cosecha`) y
  `_plantas_al_inicio(…, por_invernadero=True)` se comparten con el indicador 7: no hay lógica duplicada. Las pruebas de EST-01 pasan sin tocarlas (salvo la del menú, abajo).
- `estadisticas/views.py` (`consolidadas`), `urls.py` (`consolidadas/`), `templates/estadisticas/consolidadas.html` y `_celdas_de_invernadero.html`, `estadisticas.css`, y en `produccion.html` el enlace «← Estadísticas consolidadas» para el Gerente.
- `estadisticas/apps.py`: el Gerente entra por «Estadísticas» a las consolidadas; el Agrónomo, a producción.
- Ningún archivo fuera de `estadisticas` (salvo este archivo de la tarea y `docs/temas_abiertos.md`, ver abajo).

**Pruebas.** `python manage.py test estadisticas --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **194 pruebas, OK** (134 de EST-01 y 60 de EST-02: 33 de servicios, 24 de vistas y 3 del recorrido). `makemigrations --check --dry-run`: «No changes detected».
**Una prueba existente cambió:** `test_regla_menu_la_entrada_es_del_agronomo_y_del_gerente` (EST-01) afirmaba que el Gerente tiene la entrada hacia `estadisticas:produccion`; ahora debe tener la de `estadisticas:consolidadas` (y el Agrónomo, la de producción). Es el cambio de una regla (adónde entra el Gerente), no un debilitamiento: la prueba sigue exigiendo una sola entrada
«Estadísticas» por rol y ninguna para los demás roles.

**Decisiones.** Aplica D-93 (puntos 4, 6 y 7), D-86 y D-102 (lecturas del libro y `tipo=None`: no cambia nada de lo que decía la tarea), D-89 y D-90 (valorización), D-61 y D-30. No crea una decisión nueva; se propone una nota en D-93 (ver abajo).

**Lo que difiere de la documentación** (para `docs/temas_abiertos.md`, anotado ahí):
1. **Indicador 7, «Dados de baja»** (decidido por el estudiante, 26/11/2026): D-93 punto 4.7 dice «una fila por invernadero activo… y la fila del total». Hay además una fila agrupada «Dados de baja» (solo con actividad en el período) y el total es el de **toda la organización**, igual al de
   EST-01 para el Gerente, que cuenta todos los invernaderos del alcance. Motivo: coherencia con EST-01 y no perder la historia de un invernadero dado de baja en el período. Se propone enmendar el texto de D-93 punto 4.7.
2. **Valor de la merma en cámara** (D-93 punto 4.7: «el importe de sus asientos»): esos asientos los crea CON-04c (ya en `main`; se verificó que redondea igual y que su origen es la merma). El valor es «—» si **alguna merma que debería tener asiento** no lo tiene; «debería tener asiento» = su costo (cantidad × costo por planta de la partida, redondeado a centavos
   con `ROUND_HALF_UP`) es mayor que cero (H11: un importe cero no genera asiento). Una merma de cámara de costo cero aporta $ 0,00 y no fuerza el «—». Lo descubierto: el costo de una merma de cámara está en su `MovimientoStock` `merma_en_camara` (origen: la merma); la propia `Merma` no guarda el costo.
   Las mermas de cámara anteriores a CON-04c no tienen asiento (sin asientos hacia atrás, D-92 punto 1): mientras haya alguna en el período, el valor dice «—».
3. **Indicador 9, cómo se reparte:** el asiento de una recepción es uno solo por el total, así que no sirve para repartir por proveedor y por categoría. Se reconstruye la historia de cada línea de orden (recepciones y correcciones por orden de id) y cada hecho vale `valor_recibido(después) − valor_recibido(antes)`, el mismo importe de su
   asiento (D-89 punto 4); una prueba lo compara con los asientos reales. Un proveedor o una categoría pueden quedar en negativo si la corrección del período es sobre una recepción anterior (se muestra con su signo).
4. **Firmas con `hoy`** (como EST-01): `por_invernadero(periodo, hoy, solo_produccion)` y `estadisticas_consolidadas(actor, pestana, periodo, comparar, hoy, solo_produccion)`; «Cómo se aplica» las nombra sin `hoy` ni `pestana`.
5. **Sin gráficos «por mes» del libro** (decidido por el estudiante): ni «Ingresos y egresos por mes» (Resultados) ni «Ventas y compras por mes» (Resumen); D-93 punto 4.10 no los nombra y el punto 7 pide consultas fijas por bloque. Sí va «Compras por mes», que sale de las mismas filas del indicador 9.
6. **Una merma de cámara sin costo y un invernadero sin IoT** no fuerzan nada: lo primero, por el punto 2; lo segundo, `alertas_iot` es `None` («—») en su fila.
7. **Menú:** el Gerente entra por «Estadísticas» a las consolidadas y no a producción (el prototipo abre en «Resumen»); su pestaña «Producción» enlaza a la pantalla de EST-01.

**Pantallas: lo que se corrigió del prototipo** (D-61):
- Tenía: pestañas Resumen, Producción, **Comercial**, Compras y Resultados → hice: sin «Comercial» (indicador 8, EST-03).
- Tenía: las pestañas y los filtros cambiaban al instante con JavaScript → hice un formulario GET con botones: funciona sin JavaScript, la pestaña y el período viajan en la URL y se pueden compartir.
- Tenía: «Ventas y compras por mes» (Resumen) e «Ingresos y egresos por mes» (Resultados), sintéticos → no los hice (punto 5 de arriba); en Resumen, cada tarjeta enlaza a su pestaña.
- Tenía: «Merma en cámara» con un valor sintético → hice el valor real de los asientos, con «—» y la línea «Todavía no hay asientos para estas mermas.» mientras falten.
- Tenía: «Compras por mes» como columnas verticales → hice barras horizontales de CSS (como el resto de EST-01); un mes sin compras aparece en cero.
- Tenía: sin estados vacíos de producción ni de error → agregué «No hay invernaderos activos para comparar», «No se recibió mercadería en este período», «No hay movimientos en este período» y los avisos del período.
- Tenía: sin enlaces a la consulta de cada indicador → agregué (regla 4 de EST-CNS-CNS): el invernadero lleva a EST-01 con el mismo período; la compra y las cuentas, al libro de gestión con el período, **un enlace por ejercicio** si el período cruza dos (el libro filtra de a un ejercicio). Solo los ve el Gerente, que puede abrir ambas pantallas (D-30).
- Agregué: el aviso «El período cruza dos ejercicios…», la fila «Dados de baja», las diferencias contra el período anterior en cada tarjeta y el selector «Todas / Solo de producción» en la tabla por invernadero.

**Verifiqué** (con pruebas, sin navegador):
- El recorrido `RecorridoDeEstadisticasConsolidadasTests` (3 pruebas): el Gerente en las cuatro pestañas con dos ejercicios, recepciones parciales y correcciones; una corrección dentro y otra fuera del período; los demás roles reciben 403; un período inválido. OK.
- `makemigrations --check --dry-run`: «No changes detected» (la tarea no tiene migración: no hay `sqlmigrate` que leer ni migración que aplicar en la base de pruebas).
- Que las pruebas de EST-01 (134) siguen verdes tras el refactor, con sus `assertNumQueries` intactos.
- `git fetch`: sin cambios nuevos en `main` (`HEAD..origin/main` vacío): sin conflicto con `config/` ni `estadisticas/`; no hizo falta `trabajo_en_paralelo.md`.

**Lo cubre una prueba:** el alcance y los 403 (`test_regla_1_*`), el menú (`test_regla_7_menu_*`), cada indicador (`EstCnsCns…ServicioTests`), el total igual al de EST-01 con un invernadero dado de baja (`test_regla_4_7_un_invernadero_dado_de_baja_con_actividad_*`), la merma en cámara con costo cero y con costo mayor que cero
(`test_regla_4_7_solo_costo_cero_*`, `test_regla_4_7_con_costo_mayor_que_cero_*`), las compras contra los asientos (`test_d89_punto_4_y_d90_*`), un período que cruza dos ejercicios (`test_regla_4_10_*`, `test_pestana_resultados_un_periodo_que_cruza_*`), el período y la comparación (`test_regla_2_*`) y las consultas fijas (`test_d93_punto_7_*`).

**No pude verificar:**
- El aspecto, el JavaScript (el desplegable propio ni se usa acá) y el CSRF/`Origin` en un navegador: paso 19 de la verificación a mano.
- El cruce de dos ejercicios con datos reales de tu base (depende de que tengas dos ejercicios): lo cubre el recorrido, pero conviene verlo.
- El rendimiento con muchos datos reales: las pruebas fijan el número de consultas, no mido tiempos. El indicador 9 trae a memoria las líneas de orden tocadas en el período (acotado: una orden tiene pocas líneas).
- Que el valor de la merma en cámara coincida a mano con el asiento que deja CON-04c: lo comprobé leyendo su código (mismo redondeo y mismo origen) y con asientos armados en las pruebas, no registrando una merma real.
- Que las cifras «se sientan bien» para quien decide (criterio de producto) y las fórmulas, que se vuelven a revisar tras la entrevista al productor (H26).

**Base de desarrollo:** no la toqué; no borré ni cargué datos.
