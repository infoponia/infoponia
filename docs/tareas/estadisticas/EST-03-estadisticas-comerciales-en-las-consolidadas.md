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

> Para quien verifica. Es autocontenido: no hace falta haber visto la sesión ni el código. Las bases de prueba (`test_…`) las usa el CI; esto se hace en tu base de desarrollo. **No toqué tu base de
> desarrollo** durante la tarea: no cargué ni borré datos. La tarea no tiene migración. **No abrí un navegador** (D-96): lo que solo se ve ahí (el aspecto) va en el paso 14.

### Antes de empezar

1. En la terminal, con el entorno virtual activo: `python manage.py runserver` (no hay `migrate` que aplicar). Abrí `http://localhost:8000/`.
2. Cuentas: el **Gerente**, el **Vendedor A** y el **Vendedor B** (los de la verificación de COM-08c), un **Agrónomo** y un **Contador** (con la contraseña de tus cuentas de prueba).
3. **Datos: los mismos que armaste para verificar COM-08c**, con los mismos valores (`docs/tareas/comercial/COM-08c-estadisticas.md`, «Verificación a mano», «Antes de empezar» 3 a 6). Si todavía no los tenés, resumidos: dos invernaderos del Vendedor A («Norte» y «Sur») con
   «Lechuga Crespa» a $ 100,00 la planta; compra-ventas V1 (10 plantas, pactada mañana), V2 (30, pactada hace 4 días), V3 (20, concretada el último día del mes anterior) y los suministros `S1`, `S2` y `S3` (8, 10 y 8 plantas) del Vendedor A, todo concretado hoy; V4 (50 plantas) del Vendedor B para otro
   cliente; una discrepancia de `S1` aceptada con descuento de $ 300,00; la de `S3`, aceptada y anulada; y el cobro de `S2` registrado y anulado, con `S2` vencida hace 5 días. Las fechas se mueven desde `python manage.py shell` como dice esa tarea (solo en tu base local).
4. **Lo que tienen que dar los números**, ya con todos los datos. **Vendedor A, mes actual** (lo que ve en «Comercial › Estadísticas»): ventas **$ 6.600,00**, 5 entregas, 66 plantas, a tiempo 80 %, indemnizado $ 300,00, en mora $ 1.000,00 y pendiente $ 1.300,00.
   **Vendedor B, mes actual:** ventas **$ 5.000,00** y 1 entrega. **Gerente en las consolidadas, mes actual:** ventas **$ 11.600,00** (6.600 + 5.000), 6 entregas y 116 plantas; **período anterior** (el último día del mes anterior entra siempre): ventas **$ 2.000,00** y 1 entrega.
   Si tus datos son otros, hacé las sumas vos con los números que ves en cada Vendedor.

### Pasos

Marcá con ✔ lo que ya cubre una prueba (así, si tenés poco tiempo, te concentrás en lo que se ve y se siente).

1. **La pestaña nueva.** Entrá como **Gerente** → menú «Estadísticas». Las pestañas son ahora, en este orden: **Resumen · Producción · Comercial · Compras · Resultados**. Tocá «**Comercial**». **Tiene que ver:** el título «Estadísticas», «Comercial» marcada, el período del mes hasta hoy con
   «se compara con …» (la comparación viene tildada) y el texto «Resultados del período elegido. Las ventas se cuentan cuando se concreta la entrega y no descuentan indemnizaciones. La cobranza es la situación de hoy.» ✔ `test_pestanas_la_pantalla_ofrece_*`, recorrido paso 1.
2. **Las cuatro tarjetas.** **Ventas $ 11.600,00** (6 entregas concretadas) con debajo «▲ 9.600,00 (480,0 %) frente al período anterior» en verde; **Entregas a tiempo** (el % y «N con retraso»); **Indemnizado $ 300,00** (1 solicitud aceptada; la tarjeta con marca de advertencia) y **Cobranza en mora $ 1.000,00**
   con «a la fecha» y **sin** diferencia (la cobranza es una foto de hoy, decisión del estudiante). ✔ `test_regla_3_2_muestra_las_cuatro_tarjetas_*`, `test_d93_punto_2_los_totales_se_comparan_*`.
3. **Los mismos números que el Vendedor** (el «Hecho cuando»). Anotá lo que ves en la pestaña «Comercial» del Gerente y comparalo con **«Comercial › Estadísticas»** de cada Vendedor (mismo mes): los números del Gerente son la **suma** de los dos (ventas $ 6.600,00 + $ 5.000,00; cobranza, la de los dos). Los textos, el orden de los bloques
   y el formato (`$ 1.500,50`, `80 %`, `1,5 días`) son los de esa pantalla. ✔ `test_hecho_cuando_el_gerente_ve_los_mismos_numeros_*`, `test_hecho_cuando_con_un_solo_vendedor_*`, recorrido paso 3.
4. **Los seis bloques.** De arriba abajo, en dos columnas: **Ventas por variedad** (Lechuga Crespa, 116 plantas y su barra; botones «Ver compra-ventas» y «Ver suministros») · **Entregas a tiempo y con retraso** (a tiempo, con retraso, promedio de retraso e intentos de entrega fallidos) · **Incumplimientos aceptados**
   · **Cobranza a la fecha** (pendiente, en mora hasta 30 / de 31 a 60 / de más de 60 días, y la aclaración «Es la situación de hoy, no la del período, y por eso no se compara con el período anterior») · **Faltantes y rechazos de compra-venta** · **Clientes con más compras** (el top 10 con su % del total). Cada bloque tiene
   su texto explicativo, el mismo que en Comercial. ✔ `test_regla_3_2_muestra_las_cuatro_tarjetas_*`.
5. **Diferencias frente al período anterior.** Con la comparación tildada, aparecen «▲/▼ … frente al período anterior» debajo de: ventas ($), plantas vendidas, % a tiempo (en «pts»), promedio de retraso (en días), intentos fallidos, incumplimientos aceptados, indemnizado y los cuatro conteos de faltantes y rechazos. **No** aparecen en la
   cobranza, en las filas por variedad ni en las de clientes. Verde = mejora, rojo = empeora: subir las ventas es verde; subir el retraso, los intentos, lo indemnizado o los faltantes es rojo. ✔ `test_d93_punto_2_*`, `test_decision_del_estudiante_la_cobranza_no_se_compara`.
6. **Apagar la comparación.** Destildá «Comparar con el período anterior» y tocá cualquier pestaña o chip de período: las diferencias desaparecen y el aviso «se compara con…» también. ✔ `test_regla_2_con_la_comparacion_apagada_*`, recorrido paso 6.
7. **Otro período.** Tocá «**Mes anterior**»: la pestaña sigue en «Comercial» y muestra lo del mes pasado (con tus datos, ventas **$ 2.000,00**, 1 entrega); la cobranza queda **igual que antes** (es la de hoy). Tocá «**Personalizado**», escribí «Desde» = día 1 del mes anterior y «Hasta» = hoy y «Aplicar»:
   ventas **$ 13.600,00** (2.000 + 11.600). ✔ `test_regla_2_el_periodo_elegido_llega_a_comercial`, recorrido paso 5.
8. **Errores del período.** «Personalizado» con «Desde» posterior a «Hasta»: aviso rojo «La fecha “desde” no puede ser posterior a “hasta”.» y **ningún** número; con más de un año: «El período no puede ser mayor que un año.»; con «Hasta» futuro (escribilo en la URL, `&hasta=2099-01-01`): «El período no puede terminar después de hoy.».
   El formulario sigue ahí para corregir. ✔ `test_regla_2_un_periodo_invalido_*`, recorrido paso 5.
9. **Sin datos.** Elegí un mes viejo sin movimientos: «Sin ventas en el período.» en los dos bloques que lo dicen, los contadores en 0 y los promedios en «—» (no «0»). ✔ `test_sin_datos_muestra_los_estados_vacios_de_comercial`, recorrido paso 1.
10. **Los enlaces.** Tocá cada botón («Ver compra-ventas», «Ver suministros», «Ver entregas», «Ver solicitudes», «Ver cobranza», «Ver compra-ventas» de faltantes), los enlaces de cada cliente («compra-ventas» y «suministros») y «Verlos en Comercial, con filtros» (arriba): todos abren una pantalla de Comercial,
    **ninguno da «Prohibido (403)»**. El último abre «Comercial › Estadísticas» con el mismo rango. Algunas pantallas de destino no admiten el rango de fechas y muestran el resto de los filtros (lo dice «Cierre» de COM-08c). ✔ `test_regla_4_los_enlaces_de_cada_indicador_los_abre_el_gerente`, recorrido paso 6.
11. **Las otras pestañas no cambiaron.** «Resumen» (ventas del libro, compras, resultado, plantas cosechadas), «Producción», «Compras» y «Resultados» muestran lo de siempre (EST-02): el «Ventas» del Resumen sigue saliendo del libro de gestión y puede diferir del de «Comercial» (el libro suma asientos; Comercial, entregas).
12. **Roles sin acceso.** Entrá como **Vendedor A**, **Agrónomo** y **Contador** y escribí `http://localhost:8000/estadisticas/consolidadas/?pestana=comercial`: «Prohibido (403)». El Vendedor ve lo suyo en «Comercial › Estadísticas», no acá. Sin sesión, te lleva a iniciar sesión. ✔ `test_regla_1_solo_el_gerente_ve_la_pestana`, recorrido paso 7.
13. **No audita.** Como Administrador o Gerente, mirá «Auditoría»: abrir la pestaña «Comercial» no deja registros. ✔ `test_regla_7_la_consulta_no_audita`, recorrido (cierre).
14. **Aspecto en un navegador real.** El cliente de Django no ve el aspecto, las barras ni los colores. Abrí la pestaña «Comercial» en una **ventana privada**, entrá como Gerente y comprobá a ojo: las tarjetas alineadas como las de las otras pestañas; la barra de «Ventas por variedad» proporcional y con el monto escrito al lado;
    las diferencias en verde y rojo; los bloques en dos columnas, sin que nada se corte; «Cobranza en mora» en rojo cuando hay mora. Recorré las cinco pestañas, «Mes anterior» y «Personalizado → Aplicar» y comprobá que cada envío **conserva la pestaña y el período**. No hay formularios que guarden datos (es un GET):
    si aparece «Prohibido (403)» o un error en la consola del navegador (F12), avisá.
15. **(Opcional) Sin JavaScript.** Desactivá JavaScript y repetí los pasos 1, 6 y 7: todo funciona igual (son botones de un formulario GET; las barras son de CSS).
16. **(Opcional) En el celular.** El Gerente usa el marco de escritorio, pero la pestaña tiene que poder leerse en ancho angosto: los bloques pasan a una columna y las tablas se desplazan de costado.

## Cierre

**Qué se hizo.** La pestaña «**Comercial**» de las estadísticas consolidadas del Gerente (indicador 8 de EST-CNS-CNS) en la app `estadisticas`, sin modelos ni migraciones, sin dependencias nuevas y **sin tocar ningún archivo de otra app**:

- `estadisticas/servicios/consolidadas.py`: `comerciales(actor, periodo, hoy)`, que arma los filtros con `filtros_de_estadisticas` (el rango del período; todos los invernaderos y Vendedores) y devuelve lo que da `estadisticas` de `comercial`: **no recalcula nada** (H25). `PESTANAS` suma `"comercial"` (entre Producción y
  Compras, como el prototipo); `Bloques` suma `comerciales` (solo se calcula en esa pestaña); `_bloques` recibe el `actor`; `_comparaciones` compara los totales (decisión 2). `_exigir_gerente` es la regla 1 que ya estaba en `estadisticas_consolidadas`, ahora compartida.
- `estadisticas/views.py`: el texto de la pestaña, los deltas de las cifras comparadas (sube es bueno en ventas y puntualidad; es malo en retraso, intentos, incumplimientos, indemnizado y faltantes) y el enlace «Verlos en Comercial».
- `estadisticas/templates/estadisticas/_comercial.html` (nuevo) y `consolidadas.html` (la rama de la pestaña); `estadisticas.css` (las barras `.hbar`, `.est-grupo`, `.acts-fila` y `.facts .dta`).
- Pruebas ampliadas: `test_est_cns_cns.py`, `test_est_cns_cns_vistas.py` y `test_recorrido_estadisticas_consolidadas.py`.

**Decisiones del estudiante (26/11/2026)** — anotadas para `temas_abiertos.md`:
1. **Qué se leyó:** la sección «Pantallas» del extracto de COM-CNS-EST y la plantilla `comercial/templates/comercial/estadisticas/`, para mostrar los mismos textos, el mismo orden y el mismo formato. La estructura se **copió** dentro de `estadisticas`; solo se cargan los filtros de plantilla de `comercial` (`pesos`,
   `porcentaje`, `miles`, `un_decimal`, `ancho_de_barra`) con `{% load comercial %}`: es una dependencia de `estadisticas` (nivel 8) hacia `comercial` (nivel 6), permitida (A1).
2. **Qué se compara con el período anterior** (hueco del extracto de EST-CNS-CNS, que no dice qué pasa con la cobranza): los **totales**, sin cobranza. Se comparan ventas ($, entregas y plantas), % a tiempo (en puntos), promedio de retraso, intentos fallidos, incumplimientos (cantidad y total indemnizado) y los cuatro
   conteos de faltantes y rechazos. La **cobranza** (indicador 6) es una foto a hoy (regla 6 de COM-CNS-EST): se muestra «a la fecha», sin comparación ni variación. Las filas por variedad y por cliente no se comparan.

**Lo que difiere de la documentación** (para `docs/temas_abiertos.md`; no lo apliqué):
1. La decisión 2 de arriba (qué se compara).
2. **Firma:** `comerciales(actor, periodo, hoy)`. El extracto («Cómo se aplica») dice `comerciales(periodo)` y la tarea `consolidadas.comerciales(actor, periodo)`; hacen falta el `actor` (`estadisticas` de `comercial` verifica el alcance) y `hoy` (la cobranza es una foto a hoy). Va con `hoy` como el resto de EST-02.
3. **Regla 9 de COM-CNS-EST** («sin comparaciones entre períodos»): es de la pantalla de Comercial. En las consolidadas manda EST-CNS-CNS regla 2 (comparar con el período anterior, D-93 punto 2); no hay contradicción, pero conviene que el extracto de COM-CNS-EST lo aclare.
4. **El período de «Comercial»** es el de las consolidadas (los atajos, hasta 366 días): se pasa como `periodo=rango&desde=…&hasta=…`, que `filtros_de_estadisticas` valida con la misma convención que `periodos.validar` (la comprueba `test_convencion_de_periodo.py`). No hace falta que `comercial` acepte otra cosa.
5. **El nombre de la pestaña** en el prototipo es «Comercial» y su contenido (`stCom`: «Cobrado», «Venta promedio por entrega», «Ventas por mes», todo desde el libro) no coincide con COM-CNS-EST: mandan los indicadores de COM-CNS-EST (L7).

**Pantallas: lo que se corrigió del prototipo** (D-61):
- Tenía (`stCom`): ventas por entrega calculadas del libro de gestión («Ventas», «Entregas», «Venta promedio por entrega», «Cobrado», «Ventas por mes» y una tabla «Entregas del período») → hice los indicadores de COM-CNS-EST (ocho, con sus textos y enlaces), como pide la tarea: «mandan los indicadores de COM-CNS-EST».
- Tenía: sin enlaces a la consulta de cada indicador → hice los de la regla 10 de COM-CNS-EST (los calcula `comercial`) y sumé «Verlos en Comercial, con filtros» (regla 4 de EST-CNS-CNS). Solo los ve el Gerente, que puede abrir todas esas pantallas (D-30).
- Tenía: «Estado vacío» únicamente para «No hubo entregas en este período» → conservé los de Comercial («Sin ventas en el período.», promedios en «—»).
- Agregué: las diferencias frente al período anterior en los totales y el aviso de que la cobranza no se compara.

**Prueba existente que cambió** (aviso, no es un debilitamiento): `test_pestanas_la_pantalla_ofrece_resumen_produccion_compras_y_resultados` (EST-02) exigía que **no** estuviera la pestaña «Comercial» (decía «llega con EST-03»); ahora exige las cinco pestañas en orden (`test_pestanas_la_pantalla_ofrece_resumen_produccion_comercial_compras_y_resultados`).
El recorrido de EST-02 también suma «comercial» a las pestañas que los demás roles no pueden abrir.

**Pruebas.** `python manage.py test estadisticas comercial --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion` → **3176 pruebas, OK** (288 s). Las nuevas son 10 de servicio (`EstCnsCnsComercialesServicioTests`), 10 de vista (`EstCnsCnsComercialVistaTests`) y 1 recorrido
(`RecorridoDeEstadisticasComercialesTests`); la prueba que cambió se cuenta aparte. `makemigrations --check --dry-run`: «No changes detected».

**Verifiqué** (con pruebas, sin navegador):
- El recorrido `RecorridoDeEstadisticasComercialesTests`: el Gerente abre la pestaña sin datos; con los datos de dos Vendedores el total es la **suma** de lo que ve cada uno en «Comercial › Estadísticas» (ventas, entregas, cobranza) y el filtro de Vendedor de Comercial coincide; «Mes anterior», «Personalizado» válido e inválido; la
  comparación apagada; cada enlace abre (200); el Vendedor, el Agrónomo y otro Vendedor reciben 403 y sin sesión redirige; no hay huellas en la auditoría. OK.
- Que las demás pestañas no calculan lo comercial (`test_regla_3_2_las_otras_pestanas_no_piden_lo_comercial`) y que la consulta usa un número fijo de consultas con 2 o con 12 ventas.
- `makemigrations --check --dry-run`: la tarea no tiene migración (no hay `sqlmigrate` ni nada que aplicar en la base de pruebas).
- La arquitectura (`test_arquitectura`): `estadisticas` (nivel 8) importa de `comercial` (nivel 6) y nadie importa de `estadisticas`.

**Lo cubre una prueba:** el alcance y los 403 (`test_regla_1_*`), que sean los números de COM-CNS-EST (`test_regla_3_2_comerciales_son_los_de_com_cns_est_*`, `test_hecho_cuando_*`), la suma de todos los Vendedores (`test_regla_3_2_suma_*`), el período anterior y las doce cifras comparadas
(`test_d93_punto_2_*`), que la cobranza no se compara (`test_decision_del_estudiante_la_cobranza_no_se_compara`), que no escribe ni audita (`test_regla_7_*`), las consultas fijas (`test_d93_punto_7_*`), los textos y los bloques de la vista, los enlaces (D-30) y el período inválido.

**No pude verificar:**
- El **aspecto** en un navegador real (alineación de las tarjetas, las barras, los colores de las diferencias, el ancho angosto): paso 14. Copié solo cinco reglas de CSS (`.hbar`, `.hbar i`, `.est-grupo`, `.acts-fila`, `.facts .dta`) y reutilicé las clases de Diseño v2 que ya existían; no vi el resultado.
- El **rendimiento con muchos datos reales**: las pruebas fijan el número de consultas, no los tiempos. La pestaña llama dos veces a `estadisticas` de `comercial` (ocho indicadores, una consulta agregada cada uno) cuando se compara.
- Que las cifras «se sientan bien» para quien decide (criterio de producto) y las fórmulas, que se vuelven a revisar tras la entrevista al productor (H26).

**Base de desarrollo:** no la toqué; no borré ni cargué datos.
