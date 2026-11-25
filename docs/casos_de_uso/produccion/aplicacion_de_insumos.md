# Casos de uso · produccion · Aplicación de insumos

Copia para el repo del caso PROD-REG-APL (versión 0.2) del documento de Drive «CU extendidos», consultado el 20/11/2026. El código va en la app `produccion`.
Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. Se quitaron las marcas ⛔ y los `**` sueltos del export de Drive y se corrigió la numeración. No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-REG-APL | Registrar Aplicación de Insumos | Agrónomo, Capataz | `produccion/tests/test_prod_reg_apl.py` |

---

## PROD-REG-APL · Registrar Aplicación de Insumos

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Bitácora.
Actores principales: Agrónomo, Capataz.
Versión: 0.2

Personal involucrado e intereses
- Capataz: quiere registrar rápido lo que usó en una limpieza o en una aplicación de nutrientes, sin hacer cálculos de
   stock ni de costos.
- Agrónomo: quiere que el stock de los insumos que ninguna orden consume (limpieza, nutrientes) baje cuando se usan,
   para que la alerta de stock bajo avise a tiempo. También quiere que el costo de los nutrientes llegue a los lotes
   que los recibieron.
- Gerente: quiere que cada consumo quede valorizado y registrado en la contabilidad, como costo de la producción o
   como gasto, con trazabilidad completa.
- Organización (Jardín Botánico): quiere conocer el costo real por planta de cada lote, incluidos los nutrientes, y el
   gasto en limpieza.

Relaciones con otros casos de uso
- No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
- Lo sigue: CMP-AJT-STK · Ajustar Stock de Insumo, si el consumo deja el stock negativo o sin cubrir las reservas
   activas.

Precondiciones
a. El actor está autenticado en el Sistema.
b. El actor tiene a su cargo (Agrónomo) o asignado (Capataz) al menos un invernadero en estado «activo».
c. Existe un ejercicio contable vigente. *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*
d. Existen las cuentas contables «Insumos en Stock», «Productos en Proceso» y «Gastos de Producción». *(Se cumple sola: no se verifica aparte ni hay extensión «sin ejercicio»; D-92 punto 2, CON-04a.)*

Garantías mínimas
- La operación es atómica. Si el caso de uso se cancela o falla, no se registra ningún registro de bitácora, consumo,
   movimiento de insumo, imputación de costo, asiento contable ni log de auditoría parcial, y no cambia la cantidad de
   ningún lote de insumo ni el costo de ningún lote de plantas.
- Ningún lote de insumo queda con cantidad disponible negativa. Lo que falta queda como faltante sin lote.
- En cada consumo, la suma de las imputaciones a los lotes de plantas es exactamente igual a su monto.
- La aplicación no modifica la cantidad de plantas, la etapa ni las ocupaciones de ningún lote.

Garantías de éxito (Postcondiciones)
a. Se registró en la bitácora una aplicación de insumos con:
- la fecha y la hora actuales;
- la descripción, si se indicó;
- el actor como usuario responsable.
Está asociada al invernadero y, si se indicaron, a los sectores.
b. Por cada insumo, se registró un consumo originado en la aplicación, asociado al insumo del invernadero, con:
- la cantidad usada;
- el monto (la cantidad × el precio de referencia del insumo en el invernadero);
- la fecha actual.
c. La cantidad disponible de cada lote de insumo se redujo según el reparto. Lo que superó lo disponible en los lotes
   redujo el faltante sin lote del insumo.
d. Por cada lote de insumo afectado, y por el faltante sin lote si se usó, se registró un movimiento de insumo de tipo
   «salida por consumo», con la cantidad que salió de él y la fecha y hora actuales. Está asociado al insumo del
   invernadero y a ese lote, y está originado en el consumo.
e. Por cada consumo de un insumo cuya categoría imputa el consumo directo «como costo de los lotes», si en el alcance
   había lotes de plantas:
- se registró una imputación de costo por cada uno de esos lotes, asociada al consumo y al lote, con el monto que le
   corresponde;
- el costo acumulado de cada lote aumentó en ese monto.
f. Por cada consumo, se generó un asiento contable en el libro diario del ejercicio vigente, originado en el consumo,
   por su monto:
- si el costo se imputó a los lotes: Debe «Productos en Proceso» / Haber «Insumos en Stock»;
- si va a gasto: Debe «Gastos de Producción» / Haber «Insumos en Stock».
g. Si el stock sin lotes vencidos de un insumo quedó negativo, o menor que la suma de sus reservas activas, existe
   para el Agrónomo del invernadero una alerta «stock inconsistente» en estado «activa», que identifica el insumo y
   las órdenes cuyas reservas quedaron sin cobertura. Se reevaluó la alerta de stock bajo el mínimo de cada insumo.
h. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del registro de bitácora, de cada
   consumo, movimiento de insumo, imputación de costo y asiento contable creados, y de cada alerta creada.
i. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de valor de cada lote de insumo
   modificado.

Escenario principal de éxito (o Flujo Básico)
1.  El actor inicia el registro de una aplicación de insumos.
2.  El Sistema presenta los invernaderos activos a cargo del actor (Agrónomo) o asignados a él (Capataz).
3.  El actor selecciona un invernadero.
4.  El Sistema presenta la fecha y la hora actuales como fecha y hora de la aplicación, y los sectores activos del
   invernadero agrupados por tipo de etapa, para indicar dónde se aplicó.
5.  El actor indica si la aplicación fue en todo el invernadero o en algunos sectores, y en ese caso cuáles.
6.  El Sistema verifica el alcance y presenta los insumos que admiten consumo directo, habilitados y activos en el
   invernadero, con su stock libre, sin contar los lotes vencidos. Al Agrónomo le presenta además el destino del costo
   de cada uno: costo de los lotes o gasto.
7.  El actor indica un insumo y la cantidad usada.
8.  El Sistema verifica la cantidad y presenta el insumo agregado. Si el insumo controla vencimiento, presenta además
   el reparto propuesto entre sus lotes de insumo.
*El actor repite los pasos 7-8 por cada insumo que usó.*
9.  El actor indica, opcionalmente, una descripción y termina la carga.
10. El Sistema verifica que se haya indicado al menos un insumo y presenta el resumen:
1.  el invernadero, el alcance, la fecha y hora actuales y la descripción;
2.  cada insumo, con la cantidad usada y los lotes de insumo de los que sale.
3.  Al Agrónomo le presenta además el valor de cada consumo y su destino; el reparto entre los lotes de plantas, con
   las plantas de cada lote en el alcance, su parte, su monto y su costo por planta antes y después; y el monto que va
   a gasto.
11. El actor confirma la aplicación.
12. El Sistema verifica que los insumos sigan habilitados y activos, que no cambió la cantidad disponible de sus
   lotes de insumo y que no cambiaron los lotes de plantas del alcance ni sus plantas. Luego, en una única
   transacción:
1.  registra la aplicación en la bitácora;
2.  registra un consumo por insumo;
3.  reduce los lotes de insumo según el reparto y, si hace falta, el faltante sin lote;
4.  registra los movimientos de insumo;
5.  registra las imputaciones de costo a los lotes de plantas;
6.  genera los asientos;
7.  reevalúa las alertas de los insumos;
8.  registra la auditoría correspondiente.
13. El Sistema informa al actor que la aplicación quedó registrada, con los consumos registrados. Al Agrónomo le
   informa además los montos, el reparto entre los lotes y, si corresponde, que el stock de un insumo quedó
   negativo.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 11, el actor cancela el registro:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al actor que la aplicación no se registró.
3.  El actor reinicia el caso de uso desde el paso 1.
1a. El actor inicia el registro desde la bitácora de un invernadero:
1.  El Sistema omite los pasos 2 y 3 y continúa en el paso 4, con ese invernadero.
4a. El invernadero no tiene sectores activos:
1.  En el paso 4, el Sistema informa que solo puede indicarse todo el invernadero.
2.  El caso de uso continúa en el paso 5.
6a. El actor indicó algunos sectores, pero no marcó ninguno:
1.  El Sistema señala que debe marcar al menos un sector.
2.  El actor indica los sectores (vuelve al paso 5).
6b. El invernadero no tiene insumos que admitan consumo directo, habilitados y activos:
1.  El Sistema lo informa.
2.  El caso de uso termina sin registrar ningún cambio.
8a. La cantidad no es un número mayor que cero, o no es válida para la unidad del insumo:
1.  El Sistema señala el error e informa cuántos decimales admite la unidad.
2.  El actor corrige la cantidad (vuelve al paso 7).
8b. La cantidad supera lo disponible en los lotes de insumo vigentes:
1.  El Sistema registra el insumo igual. Lo que no tiene lote se registrará como faltante sin lote.
2.  Si el actor es el Agrónomo, en el paso 8 el Sistema informa la cantidad que no tiene lote. Al Capataz no se le
   informa.
3.  El caso de uso continúa en el paso 9 o en el paso 7.
8c. El actor corrige el reparto entre los lotes de insumo propuesto:
1.  El actor indica, para un lote de insumo, la cantidad que salió de él.
2.  El Sistema verifica que no supere lo disponible del lote y presenta el reparto con la suma de los lotes.
3.  El actor repite los puntos 1 y 2 por cada lote que corrige.
8c.2a. La cantidad supera lo disponible del lote de insumo:
1.  El Sistema señala el error e informa la cantidad disponible del lote.
2.  El actor corrige la cantidad (vuelve a 8c.1).
8d. El actor quiere quitar un insumo agregado:
1.  El actor indica el insumo que quiere quitar.
2.  El Sistema lo quita y presenta los insumos que quedan.
3.  El caso de uso continúa en el paso 7 o en el paso 9.
10a. No se indicó ningún insumo:
1.  El Sistema señala que debe indicar al menos uno.
2.  El actor indica un insumo (vuelve al paso 7).
10b. El reparto entre los lotes de insumo de un insumo no suma la cantidad usada (o lo disponible en sus lotes, si es
   menor):
1.  El Sistema señala el error e informa cuánto deberían sumar.
2.  El actor corrige el reparto (vuelve a 8c.1).
10c. Un insumo imputa su costo a los lotes, pero en el alcance no hay lotes de plantas:
1.  En el resumen, el Sistema informa al Agrónomo que el costo de ese insumo va a gasto porque no hay entre qué lotes
   repartirlo.
2.  El caso de uso continúa en el paso 11.
10d. El actor quiere corregir un dato del resumen:
1.  El actor indica el dato que quiere corregir, y el caso de uso vuelve al paso donde se ingresó (5, 7, 8c o 9).
2.  El actor vuelve a terminar la carga (paso 9), y el Sistema repite las verificaciones del paso 10.
12a. Entre la carga y la confirmación, otra operación cambió la cantidad disponible de un lote de insumo indicado, la
   habilitación o el estado de un insumo, o las plantas de los lotes del alcance, y lo indicado ya no es válido:
1.  El Sistema no registra ningún cambio, conserva los datos ingresados e informa qué cambió.
2.  El caso de uso vuelve al paso 6 con los valores vigentes.

Requisitos especiales
- La interfaz del Capataz está pensada para pantallas de celular.
- Tras cada dato ingresado por el actor (pasos 5, 7 y 8c), la pantalla se actualiza con las verificaciones y los
   valores calculados en no más de 1 segundo.
- El paso 12 se ejecuta como una única transacción.
- El control de concurrencia impide que dos consumos simultáneos descuenten dos veces lo mismo de un lote de insumo, o
   que un consumo y un ajuste dejen un lote con cantidad negativa.
- El Agrónomo solo accede a los invernaderos a su cargo, y el Capataz a los que tiene asignados.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos se expresan en pesos argentinos, con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Qué es una aplicación de insumos: el uso de insumos sin una orden de trabajo, como la limpieza o los nutrientes. Es
   un registro de bitácora que origina consumos: el cuarto origen de un consumo, junto con la siembra, el
   mantenimiento técnico y la entrega. No es un ajuste ni una merma. (Todo el caso de uso)
- Quién lo registra: el Agrónomo, en los invernaderos a su cargo, y el Capataz, en los que tiene asignados. El Sistema
   nunca elige el invernadero solo, aunque haya uno. (Paso 2)
- Fecha y hora: las actuales. Si la aplicación fue antes, se aclara en la descripción. (Paso 4)
- Alcance: todo el invernadero (todos sus sectores activos) o los sectores activos que se elijan. Un sector fuera de
   servicio no se puede elegir. Define entre qué lotes de plantas se reparte el costo. (Paso 5)
- Insumos que se ofrecen: los de categorías cuyo consumo directo es «como gasto» o «como costo de los lotes», activos
   y habilitados en el invernadero. Cada insumo una sola vez por aplicación. (Paso 6)
- Cantidad válida: un número mayor que cero, con los decimales que admite la unidad del insumo (unidad: 0; g, mL, m y
   m²: 2; kg, L y m³: 3). No se limita al stock: el hecho ya ocurrió. (Paso 8)
- Reparto entre los lotes de insumo: (Pasos 8 y 10, extensiones 8c y 10b)
- el Sistema propone sacar primero del lote vigente que vence antes (FEFO), y deja al final los lotes sin fecha, por
   orden de ingreso;
- los lotes vencidos no se proponen;
- la propuesta se muestra y se puede corregir solo en los insumos que controlan vencimiento; en los demás se aplica
   tal cual;
- el reparto suma la cantidad usada o, si es menor, lo disponible en los lotes.
- Stock insuficiente: lo que supera lo disponible en los lotes de insumo se registra como faltante sin lote (stock
   negativo). No se bloquea, y se alerta al Agrónomo. Al Capataz no se le informa. (Extensión 8b, postcondición g)
- Valor del consumo: la cantidad × el precio de referencia del insumo en el invernadero, en el momento del registro.
   (Paso 10)
- Destino del costo: lo decide la categoría del insumo, no quien registra. (Pasos 6 y 10, extensión 10c)
- «como gasto»: va a «Gastos de Producción»;
- «como costo de los lotes»: se reparte entre los lotes de plantas del alcance. Si no hay lotes, va a gasto.
- Lotes de plantas del alcance: los que tienen ocupaciones vigentes en los sectores del alcance. Las plantas de cada
   uno son las que tiene en esos sectores. (Paso 10)
- Reparto del costo entre los lotes de plantas: (Paso 10)
- cada lote recibe el monto del consumo × sus plantas en el alcance ÷ el total de plantas en el alcance;
- se trabaja en centavos: cada lote recibe la parte entera de su cuota, y los centavos que sobran se asignan de a uno
   a los lotes con mayor resto;
- si hay empate, el centavo va al lote con más plantas y, si sigue el empate, al creado antes.
- Imputación de costo: cada parte del reparto se registra como una imputación del consumo al lote, con su monto. Así
   queda trazable de qué consumos sale el costo de cada lote. (Paso 12)
- Costo por planta de un lote (promedio ponderado móvil): el costo acumulado del lote ÷ sus plantas actuales. Una
   imputación aumenta el costo acumulado. Una cosecha o una merma lo reduce en sus plantas × el costo por planta del
   momento. (Paso 10)
- Asientos: uno por consumo, originado en el consumo. Costo de los lotes: Debe «Productos en Proceso» / Haber «Insumos
   en Stock». Gasto: Debe «Gastos de Producción» / Haber «Insumos en Stock». (Paso 12)
- Qué ve cada rol: el Capataz ve los insumos, las cantidades y los lotes de insumo. No ve valores, destinos del costo,
   el reparto entre lotes de plantas ni los avisos de stock. El Agrónomo ve todo. (Pasos 6, 8, 10 y 13)
- Sin notificación: la aplicación queda en la bitácora del invernadero, y no se notifica al Agrónomo cuando la
   registra el Capataz. La alerta «stock inconsistente» sí se genera. (Paso 13)

Lista de tecnología y variaciones de datos
- 5a. Los sectores se eligen de una lista con casillas, agrupados por tipo de etapa.
- 7a. Las cantidades se expresan en la unidad de medida del insumo.
- 9a. La descripción es texto libre opcional.

Frecuencia
Varias veces por semana en cada invernadero (limpieza en cada rotación, aplicación de nutrientes). A confirmar con el
   Jardín Botánico.

Temas abiertos
- Cuenta de gasto: «Gastos de Producción» es una propuesta, a confirmar con el bloque contable.
- Insumo vencido usado igual: si el Capataz usó un producto vencido, el reparto no lo ofrece. Hoy se registra como si
   saliera de otro lote, y después se corrige con un ajuste. Hay que ver si hace falta permitirlo con un aviso.

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-50, D-51)

### Lo que NO se hace en la ronda (D-45)

- ~~**Asientos contables** (postcondición f y las precondiciones c y d: ejercicio vigente y cuentas «Insumos en Stock», «Productos en Proceso» y «Gastos de Producción»): no se verifican ni se crean. El consumo queda con su monto y, si se imputó a lotes, con sus imputaciones; el asiento lo generará `contabilidad`.~~ **Hecho en CON-04a (25/11/2026):** un asiento por consumo (no por imputación), con la fecha de la aplicación: Debe «Productos en Proceso» si el consumo quedó con imputaciones, o «Gastos de Producción» si quedó sin ellas (también cuando la categoría es «como costo de los lotes» pero no hay lotes de plantas en el alcance, extensión 10c) / Haber «Insumos en Stock».
- ~~La cuenta «Gastos de Producción» sigue siendo una propuesta (MD-90): no hace falta en la ronda.~~ «Gastos de Producción» (5.1.03) ya está en el plan de cuentas aprobado y la usa este caso de uso.

### Qué hace cada parte

| Parte | Código |
|---|---|
| Registrar aplicación | `produccion/servicios/aplicaciones.py`: `insumos_aplicables(actor, invernadero_id)`, `resumen_de_aplicacion(actor, datos)`, `registrar_aplicacion(actor, datos)` |
| Reparto del costo | `produccion/servicios/costos.py`: `repartir_en_centavos` (`docs/patrones/costo_del_lote.md`) |

### Decisiones de aplicación

- **Quién y dónde**: el Agrónomo (invernaderos a su cargo) y el Capataz (los que tiene asignados). El invernadero nunca se elige solo, aunque haya uno. Fecha y hora: **las actuales**, sin fechas retroactivas.
- **Alcance**: «todo el invernadero» (sin sectores en `Bitacora.sectores`; los sectores **activos** del invernadero) o sectores elegidos entre los activos (los fuera de servicio no se ofrecen; extensión 6a: «algunos sectores» sin ninguno marcado es error).
- **Insumos que se ofrecen** (`insumos_invernadero.habilitados` de `inventario`, filtrados por `TipoInsumo.consumo_directo != no_admite`), con su stock libre sin lotes vencidos (`stock.existencias`). Un insumo una sola vez.
- **Cantidad**: mayor que cero, con los decimales de la unidad (`stock.validar_cantidad`). **No se limita al stock** (el hecho ya ocurrió): lo que supera los lotes sale del faltante sin lote (extensión 8b) y se alerta al Agrónomo; **al Capataz no se le informa**.
- **Reparto entre lotes de insumo**: FEFO (`proponer_lotes_fefo(iin_id, cantidad, hoy)`); solo se puede corregir en insumos que controlan vencimiento (8c); debe sumar la cantidad o, si es menor, lo disponible (10b). Se aplica con `registrar_salida_por_consumo(iin_id, partes, origen_id=consumo.pk)` (un movimiento por lote, hoy).
- **Valor**: `cantidad × precio de referencia` del insumo en el invernadero, 2 decimales, `ROUND_HALF_UP`, al registrar.
- **Destino del costo**: lo decide la categoría. «Como costo de los lotes» → se reparte entre los lotes con plantas en los sectores del alcance (`repartir_en_centavos`; una `ImputacionCosto` por lote que recibe más de cero y suma a su `costo_acumulado`); si no hay lotes → va a gasto (10c, aviso solo al Agrónomo). «Como gasto» → sin imputaciones.
- **Qué ve cada rol**: el Capataz ve insumos, cantidades y lotes de insumo; **no** ve valores, destinos, reparto ni avisos de stock. Los servicios **no devuelven esos datos** si actúa un Capataz (`resumen_de_aplicacion` los entrega vacíos), no solo la plantilla.
- **Registros**: una `AplicacionInsumos` (bitácora tipo `aplicacion`, `descripcion_evento` = la descripción del actor o, si no hay, «Aplicación de insumos: {lista}»); por insumo, un `Consumo` (fila de bitácora interna tipo `consumo`, `aplicacion` = la aplicación, `siembra` nula), con sus movimientos de insumo (`origen` = el consumo, creado **antes** de la salida de stock; D-52); las imputaciones; y `reevaluar_alertas_del_insumo` por insumo (alerta «stock inconsistente» y «bajo el mínimo»).
- **Concurrencia (12a)**: si cambió el stock de un lote de insumo, la habilitación o el estado de un insumo, o las plantas de los lotes del alcance → `cambio_simultaneo` con qué cambió y el caso vuelve al paso 6 con los valores vigentes.
- **Bloqueos**: cuentas → invernadero → **sectores del alcance** (id; para fijar las plantas de los lotes) → insumos (`TipoInsumo` → `Insumo` → `InsumoInvernadero` → `LoteInsumo`) → lotes de plantas del alcance (id; sus `costo_acumulado` cambian). La aplicación no cambia plantas, etapa ni ocupaciones.
- **Sin notificación** cuando registra el Capataz (regla del caso de uso). **Auditoría**: un registro `registro_aplicacion` con la bitácora, los consumos, los movimientos, las imputaciones, los lotes de insumo y de plantas modificados y las alertas creadas.
- **Insumo vencido usado igual** (tema abierto del CU): no se ofrece; se corrige con un ajuste. Queda como está.

### Pantallas

Prototipo: `VIEWS.aplic`, `apCalc`, `reparto`, `fefo`. Diseñada para celular (el Capataz); desde la bitácora de un invernadero se inicia ya con ese invernadero (extensión 1a). Pasos: invernadero → alcance (todo o sectores) → insumos y cantidades (con el reparto FEFO) → descripción → resumen (según el rol) → confirmar.

### Pruebas

`produccion/tests/test_prod_reg_apl.py` (una por regla y por postcondición a a e y g a i; todo el invernadero y sectores; insumo con y sin vencimiento; reparto corregido y que no suma; faltante sin lote y alerta solo al Agrónomo; sin lotes en el alcance → gasto; imputaciones que suman exactamente el monto; el Capataz no recibe valores; un insumo repetido; sectores fuera de servicio; cantidad con decimales no válidos; que un error no deja nada creado) y `test_aplicaciones_concurrencia.py` (`@tag("concurrencia")`: dos aplicaciones sobre el mismo lote de insumo; aplicación contra un ajuste; aplicación contra una merma que cambia las plantas del alcance).
