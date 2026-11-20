# Casos de uso · inventario · Ajustar stock de insumo

Copia para el repo del caso CMP-AJT-STK (versión 0.2) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario.

Es un caso de uso de **nivel de objetivo de usuario** (extendido, con flujo básico y extensiones). **El código va en la app `inventario`** (D-37); el archivo de pruebas es
`inventario/tests/test_cmp_ajt_stk.py` (si crece, se parte en `test_cmp_ajt_stk_recuento.py`, `..._motivos.py` y `..._concurrencia.py`).

Se nombran las pruebas de las extensiones con el número del paso: `test_extension_7b_3a_rotura_supera_lo_disponible`.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

> **Marcas de esta ronda.** Lo marcado «Fuera de la ronda (D-45)» no se implementa; el resto sí. Las decisiones de aplicación están al final, en «Cómo se aplica en la ronda».

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CMP-AJT-STK | Ajustar Stock de Insumo | Agrónomo | `inventario/tests/test_cmp_ajt_stk.py` |

---

## CMP-AJT-STK · Ajustar Stock de Insumo

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Compras e Inventario / Insumos.
Actor principal: Agrónomo.
Versión: 0.2
Personal involucrado e intereses
- Agrónomo: quiere que el stock de cada insumo en el sistema coincida con lo que hay en el depósito, para planificar
   con datos reales. También quiere regularizar rápido un stock negativo o una alerta de vencimiento.
- Capataz: quiere que los insumos que el sistema le reserva en las órdenes existan de verdad en el depósito.
- Gerente: quiere que cada diferencia entre el sistema y la realidad quede valorizada en «Diferencias de Inventario de
   Insumos», con su motivo y su responsable, para medir cuánto se pierde por roturas, vencimientos o errores de
   registro.
- Organización (Jardín Botánico): quiere que el stock y su valor en la contabilidad sean confiables, y que lo vencido
   no se use en la producción.
Relaciones con otros casos de uso
- No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
- **Lo preceden:**
- Concretar Siembra, Concretar Entrega y Registrar Aplicación de Insumos, cuando su consumo deja el stock negativo o
   sin cubrir las reservas activas (regla 6 de 8.13);
- CMP-REV-VNC · Revisar Vencimientos (InfoPonia), cuando alerta un lote de insumo vencido;
- CMP-HAB-IIN · Habilitar Insumo en Invernadero, que el Agrónomo puede ejecutar desde este caso de uso (extensión 4a).
- Lo sigue: la reevaluación de las alertas del insumo (stock inconsistente, vencimiento y stock bajo el mínimo).
Precondiciones
a. El Agrónomo está autenticado en el Sistema.
b. El Agrónomo tiene a su cargo al menos un invernadero en estado «activo».
c. Existe un ejercicio contable vigente. **[Fuera de la ronda (D-45)]**
d. Existen las cuentas contables «Insumos en Stock» y «Diferencias de Inventario de Insumos». **[Fuera de la ronda (D-45)]**
Garantías mínimas
- La operación es atómica. Si el caso de uso se cancela o falla, no se registra ningún cambio en los lotes de insumo,
   ningún movimiento, ningún asiento contable, ningún cambio de estado de una alerta ni ningún log de auditoría
   parcial.
- Todo cambio en la cantidad de un lote de insumo genera exactamente un movimiento de insumo (regla 1 de 8.19).
- Ningún lote de insumo queda con cantidad disponible negativa. Solo el faltante sin lote puede ser negativo, y este
   caso de uso nunca lo hace más negativo.
- Un ajuste nunca registra un consumo: no imputa costo a ningún lote de plantas ni a ninguna orden.
- Lo vencido nunca ingresa al stock.
Garantías de éxito (Postcondiciones)
a. Cada lote de insumo indicado quedó con su cantidad disponible ajustada.
b. Si se ingresó mercadería sin lote, se creó un lote de insumo nuevo por cada ingreso, asociado al insumo del
   invernadero, con:
- cantidad ingresada y cantidad disponible iguales a la indicada;
- fecha de ingreso igual a la fecha actual;
- la fecha de vencimiento indicada, o vacía si el insumo no controla vencimiento.
c. En un recuento físico, el faltante sin lote del insumo quedó en cero.
d. Por cada lote cuya cantidad cambió por un ajuste (incluidos los lotes nuevos y el faltante sin lote), se registró
   un movimiento de insumo con:
- tipo «ajuste positivo» o «ajuste negativo», según el sentido del cambio;
- cantidad positiva igual a la diferencia;
- la fecha y la hora actuales;
- el motivo del ajuste y la descripción, si se indicó.
El movimiento está asociado al insumo del invernadero y al lote, y no tiene documento de origen.
e. **[Fuera de la ronda (D-45)]** Cada movimiento de ajuste originó un asiento contable en el libro diario del ejercicio vigente, valorizado con la
   cantidad × el precio de referencia del insumo en el invernadero:
- ajuste positivo: Debe «Insumos en Stock» / Haber «Diferencias de Inventario de Insumos»;
- ajuste negativo: al revés.
f. En una corrección entre lotes, se registraron dos movimientos de insumo, de tipo «salida por corrección entre
   lotes» en el lote de origen y «entrada por corrección entre lotes» en el de destino, por la misma cantidad. No se
   generó asiento contable, y el stock actual del insumo no cambió.
g. El stock actual del insumo en el invernadero (la suma de lo disponible en sus lotes) quedó actualizado.
h. Si después del ajuste el stock sin lotes vencidos es mayor o igual que cero y que la suma de las reservas activas
   del insumo, la alerta «stock inconsistente» de ese insumo, si estaba activa, pasó a «resuelta», con su fecha de
   resolución.
i. Si después del ajuste el stock sin lotes vencidos es negativo o menor que la suma de las reservas activas, existe
   una alerta «stock inconsistente» activa para el Agrónomo, que identifica el insumo y las órdenes cuyas reservas
   quedaron sin cobertura.
j. Las alertas de vencimiento de los lotes dados de baja por vencimiento pasaron a «resuelta», y se reevaluó la alerta
   de stock bajo el mínimo del insumo.
k. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de valor de cada lote de insumo
   modificado.
l. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada lote de insumo, movimiento de
   insumo y asiento contable creados.
m. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de estado de cada alerta resuelta
   o creada.
Escenario principal de éxito (o Flujo Básico): recuento físico
1.  **El Agrónomo inicia el ajuste de stock de un insumo.**
2.  **El Sistema presenta los invernaderos activos a cargo del Agrónomo.**
3.  **El Agrónomo selecciona un invernadero.**
4.  **El Sistema presenta los insumos habilitados y activos del invernadero, con su stock actual.**
5.  **El Agrónomo selecciona un insumo.**
6.  **El Sistema presenta:**
1.  el stock actual del insumo;
2.  sus lotes de insumo, con la cantidad disponible y la fecha de vencimiento de cada uno;
3.  el faltante sin lote, si existe;
4.  el precio de referencia;
5.  si el insumo controla vencimiento;
6.  los motivos de ajuste.
7.  **El Agrónomo elige el motivo «recuento físico».**
8.  **El Sistema presenta cada lote de insumo con su cantidad registrada, que propone como cantidad contada, e informa
   que el faltante sin lote, si existe, quedará en cero.**
9.  **El Agrónomo indica, para un lote, la cantidad que contó.**
10. El Sistema verifica la cantidad y presenta la diferencia del lote y la diferencia total del recuento.
*El Agrónomo repite los pasos 9-10 por cada lote cuya cantidad contada difiere de la registrada. Si ninguna difiere,
   no los ejecuta.*
11. **El Agrónomo termina el recuento.**
12. **El Sistema verifica que el recuento tenga al menos una diferencia y presenta el resumen:**
1.  por cada lote que cambia, la cantidad registrada, la contada y la diferencia;
2.  los lotes nuevos, con su cantidad y su vencimiento;
3.  el faltante sin lote que queda en cero;
4.  el stock actual antes y después del ajuste;
5.  el valor del ajuste, positivo o negativo.
13. **El Agrónomo confirma el ajuste.**
14. **El Sistema verifica que no cambió la cantidad disponible de los lotes ni el faltante sin lote del insumo. Luego,
   en una única transacción:**
1.  actualiza la cantidad disponible de cada lote que cambia;
2.  crea los lotes nuevos;
3.  deja en cero el faltante sin lote;
4.  registra un movimiento de ajuste por cada lote que cambió, con su asiento **[Fuera de la ronda (D-45)]**;
5.  reevalúa las alertas del insumo;
6.  registra la auditoría correspondiente.
15. **El Sistema informa al Agrónomo lo registrado, el stock actual del insumo y si se resolvió o sigue activa la
   alerta «stock inconsistente».**
Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 13, el Agrónomo cancela el ajuste:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.
*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que el ajuste no se registró.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.
1a. El Agrónomo inicia el ajuste desde un insumo del inventario o desde una alerta:
1.  El Sistema omite los pasos 2 a 5 y presenta el paso 6 con el invernadero y el insumo ya elegidos.
2.  Si lo inició desde un insumo, el Agrónomo puede cambiarlos (vuelve al paso 2). Si lo inició desde una alerta, no
   puede cambiarlos.
3.  Si lo inició desde una alerta, el Sistema propone el motivo que corresponde: «recuento físico» para una alerta
   «stock inconsistente», o «vencimiento» para una de lote vencido. El caso de uso continúa en el paso 7.
4a. El insumo que el Agrónomo busca no está habilitado en el invernadero:
1.  El Agrónomo ejecuta Habilitar Insumo en Invernadero para ese insumo.
2.  El caso de uso vuelve al paso 4 con el insumo habilitado, que tiene stock cero y ningún lote.
7a. El Agrónomo elige el motivo «carga inicial»:
1.  El Sistema pide la cantidad y, si el insumo controla vencimiento, la fecha de vencimiento.
2.  El Agrónomo indica la cantidad y, si corresponde, la fecha de vencimiento.
3.  El Sistema verifica los datos.
4.  El caso de uso continúa en el paso 12, con un lote nuevo.
7a.3a. La cantidad no es válida para la unidad del insumo:
1.  El Sistema señala el error e informa cuántos decimales admite la unidad.
2.  El Agrónomo corrige la cantidad (vuelve a 7a.2).
7a.3b. Falta la fecha de vencimiento, o es anterior a la fecha actual:
1.  El Sistema señala el error e informa que lo vencido no ingresa al stock.
2.  El Agrónomo corrige la fecha (vuelve a 7a.2).
7b. El Agrónomo elige el motivo «rotura o pérdida»:
1.  El Sistema presenta los lotes de insumo con cantidad disponible mayor que cero.
2.  El Agrónomo indica el lote afectado y la cantidad a descontar.
3.  El Sistema verifica los datos.
4.  El caso de uso continúa en el paso 12.
7b.3a. La cantidad no es válida para la unidad del insumo, o supera lo disponible del lote:
1.  El Sistema señala el error e informa la cantidad disponible del lote.
2.  El Agrónomo corrige la cantidad (vuelve a 7b.2).
7c. El Agrónomo elige el motivo «vencimiento»:
1.  El Sistema presenta los lotes de insumo vencidos con cantidad disponible mayor que cero, con su fecha de
   vencimiento.
2.  El Agrónomo indica los lotes que da de baja.
3.  El Sistema verifica que haya indicado al menos uno. Por cada lote se descuenta todo lo que le queda.
4.  El caso de uso continúa en el paso 12.
7c.1a. El insumo no tiene lotes vencidos con cantidad disponible:
1.  El Sistema lo informa.
2.  El Agrónomo elige otro motivo (vuelve al paso 7) o cancela.
7c.3a. El Agrónomo no indicó ningún lote:
1.  El Sistema señala que debe indicar al menos uno.
2.  El Agrónomo indica los lotes (vuelve a 7c.2).
7d. El Agrónomo elige el motivo «corrección entre lotes»:
1.  El Sistema presenta los lotes de insumo de origen posibles (los que tienen cantidad disponible mayor que cero) y
   los de destino posibles (todos los lotes y el faltante sin lote).
2.  El Agrónomo indica el lote de origen, el lote de destino y la cantidad.
3.  El Sistema verifica los datos.
4.  El caso de uso continúa en el paso 12. El resumen informa que el stock total no cambia y que el ajuste no tiene
   valor contable.
7d.3a. El lote de destino es el mismo que el de origen:
1.  El Sistema señala el error.
2.  El Agrónomo elige otro lote de destino (vuelve a 7d.2).
7d.3b. La cantidad no es válida para la unidad del insumo, o supera lo disponible del lote de origen:
1.  El Sistema señala el error e informa la cantidad disponible del lote de origen.
2.  El Agrónomo corrige la cantidad (vuelve a 7d.2).
7e. El Agrónomo elige el motivo «otro»:
1.  El Agrónomo indica si el ajuste suma o resta stock, y una descripción.
2.  Si suma, el caso de uso sigue los pasos 7a.1 a 7a.3, con su descripción. Si resta, sigue los pasos 7b.1 a 7b.3,
   con su descripción.
3.  El caso de uso continúa en el paso 12.
7e.1a. El Agrónomo no indicó si el ajuste suma o resta, o no indicó la descripción:
1.  El Sistema señala el dato que falta.
2.  El Agrónomo lo indica (vuelve a 7e.1).
10a. La cantidad contada no es válida para la unidad del insumo, o es negativa:
1.  El Sistema señala el error e informa cuántos decimales admite la unidad.
2.  El Agrónomo corrige la cantidad (vuelve al paso 9).
10b. El Agrónomo encontró en el depósito mercadería del insumo que no corresponde a ningún lote registrado:
1.  El Agrónomo indica la cantidad encontrada y, si el insumo controla vencimiento, su fecha de vencimiento.
2.  El Sistema verifica los datos, como en 7a.3a y 7a.3b, y presenta el lote nuevo junto con la diferencia total del
   recuento.
3.  El caso de uso continúa en el paso 9 o en el paso 11. El Agrónomo repite esta extensión por cada fecha de
   vencimiento distinta que encuentre.
10c. El Agrónomo quiere quitar un lote nuevo que agregó en 10b:
1.  El Agrónomo indica el lote nuevo que quiere quitar.
2.  El Sistema lo quita y presenta la diferencia total del recuento.
3.  El caso de uso continúa en el paso 9 o en el paso 11.
12a. El recuento no tiene diferencias: ninguna cantidad contada difiere de la registrada, no hay lotes nuevos y no hay
   faltante sin lote:
1.  El Sistema informa que no hay nada que ajustar.
2.  El Agrónomo corrige el recuento (vuelve al paso 9) o cancela.
12b. Después del ajuste, el stock actual del insumo quedaría negativo o menor que la suma de sus reservas activas:
1.  Junto con el resumen, el Sistema advierte qué órdenes quedarían sin cobertura y que la alerta «stock
   inconsistente» seguirá activa. No bloquea el ajuste.
2.  El caso de uso continúa en el paso 13.
12c. El Agrónomo quiere corregir un dato del resumen:
1.  El Agrónomo indica el dato que quiere corregir, y el caso de uso vuelve al paso donde se ingresó (7, 9, 10b o el
   paso de la extensión del motivo).
2.  El Agrónomo vuelve a terminar la carga, y el Sistema repite las verificaciones del paso 12.
14a. Entre la carga y la confirmación, otra operación cambió la cantidad disponible de un lote indicado o el faltante
   sin lote, y lo indicado ya no es válido:
1.  El Sistema no registra ningún cambio, conserva los datos ingresados e informa qué cambió.
2.  El caso de uso vuelve al paso 8, o al primer paso de la extensión del motivo, con los valores vigentes.
Requisitos especiales
- Tras cada dato ingresado por el Agrónomo (pasos 9, 10b y los de cada motivo), la pantalla se actualiza con las
   verificaciones, las diferencias y el valor del ajuste en no más de 1 segundo.
- El paso 14 se ejecuta como una única transacción.
- El control de concurrencia impide que un ajuste y un consumo simultáneos sobre el mismo insumo dejen un lote con
   cantidad negativa o descuenten dos veces lo mismo.
- Solo el Agrónomo a cargo del invernadero accede a sus insumos.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos de los asientos contables se expresan en pesos argentinos, con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio:**
- Quién lo ejecuta: solo el Agrónomo a cargo del invernadero (regla 5 de 8.19). (Paso 2)
- Qué es un ajuste: la corrección del stock registrado de un insumo para que coincida con lo que hay en el depósito.
   No representa un uso del insumo, que siempre es un consumo, ni una compra, que es una recepción (regla 4 de 8.19).
   (Todo el caso de uso)
- Motivos: (Paso 7)
- Recuento físico: alinear el sistema con lo contado, incluida la regularización de un stock negativo. Suma o resta,
   por lote.
- Carga inicial: cargar el stock que el invernadero tenía al empezar a usar el sistema. Suma, con un lote nuevo.
- Rotura o pérdida: mercadería rota, perdida o descartada en el depósito, sin orden de trabajo. Resta.
- Vencimiento: dar de baja lo que les queda a los lotes vencidos. Resta.
- Corrección entre lotes: corregir de qué lote salió lo usado, sin cambiar el stock total. Ni suma ni resta.
- Otro: cualquier otro caso, con descripción obligatoria. Suma, con un lote nuevo, o resta.
- Fecha y hora: las actuales. Si la diferencia se originó antes, se aclara en la descripción. (Paso 14)
- Cantidad válida: un número mayor que cero, con los decimales que admite la unidad del insumo (unidad: 0; g, mL, m y
   m²: 2; kg, L y m³: 3). En el recuento, la cantidad contada puede ser cero. (Pasos 10, 7a.3, 7b.3 y 7d.3)
- Recuento físico: (Pasos 8 a 12, extensiones 10b y 10c)
- se cuenta el insumo entero, lote por lote;
- el Sistema propone la cantidad registrada de cada lote, y el Agrónomo solo indica las que difieren;
- lo que se encuentra sin lote registrado se carga como lote nuevo, con su vencimiento;
- el faltante sin lote siempre queda en cero, porque no es algo físico.
- Faltante sin lote: cuando un consumo supera lo disponible en los lotes de insumo, lo que falta se registra como un
   faltante sin lote del insumo, con cantidad negativa (stock negativo, regla 5 de 8.13). Solo puede volver a cero con
   un recuento físico, o acercarse a cero con una corrección entre lotes que lo tenga como destino. (Pasos 6, 8 y 14,
   extensión 7d)
- Lote de insumo nuevo: se crea con la carga inicial, con un «otro» que suma o con mercadería encontrada en el
   recuento. Si el insumo controla vencimiento, la fecha es obligatoria y no puede ser anterior a la fecha actual: lo
   vencido no ingresa al stock. Si hay existencias con fechas distintas, se carga un lote por cada fecha. (Extensiones
   7a, 7e y 10b)
- Baja por vencimiento: solo de lotes vencidos, y por todo lo que les queda. (Extensión 7c)
- Rotura o pérdida: no puede superar lo disponible del lote. (Extensión 7b)
- Valor del ajuste: la cantidad × el precio de referencia del insumo en el invernadero, en el momento del ajuste.
   (Paso 12)
- Asiento de un ajuste **[Fuera de la ronda (D-45)]**: cada movimiento de ajuste es su propio documento de origen y origina su asiento (regla 2 de
   8.19). Ajuste positivo: Debe «Insumos en Stock» / Haber «Diferencias de Inventario de Insumos». Ajuste negativo: al
   revés. (Paso 14)
- Corrección entre lotes: genera un movimiento «salida por corrección entre lotes» en el origen y uno «entrada por
   corrección entre lotes» en el destino. No son movimientos de ajuste y no originan asiento, porque el stock total y
   su valor no cambian. (Extensión 7d)
- Cobertura de reservas: un ajuste que deja el stock sin lotes vencidos negativo o por debajo de las reservas activas
   no se bloquea: se registra y deja activa la alerta «stock inconsistente», que identifica las órdenes sin cobertura.
   Las órdenes se cubren en orden de fecha programada, de la más cercana a la más lejana. (Extensión 12b,
   postcondición i)
- Resolución de la alerta «stock inconsistente»: se resuelve cuando el stock sin lotes vencidos vuelve a ser mayor o
   igual que cero y que la suma de las reservas activas del insumo (regla 6 de 8.13). (Postcondición h)
- Regularización de un stock negativo: si el faltante se debe a una recepción sin cargar, se regulariza cargando esa
   recepción, y no con un ajuste. Un ajuste dejaría la compra sin registrar y el costo mal valorizado. El ajuste por
   recuento es para cuando no hay recepción pendiente que lo explique. (Todo el caso de uso)
Lista de tecnología y variaciones de datos
- 7a. La fecha de vencimiento se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.
- 9a. Las cantidades se expresan en la unidad de medida del insumo.
- 7e. La descripción es texto libre.
Frecuencia
El recuento, cada vez que el Agrónomo cuenta el depósito o regulariza una alerta. La carga inicial, una vez por insumo
   e invernadero al empezar a usar el sistema. La baja por vencimiento, cada vez que InfoPonia alerta un lote vencido.
   A confirmar con el Jardín Botánico.
Temas abiertos
- Cuenta de la carga inicial: hoy va contra «Diferencias de Inventario de Insumos», como cualquier ajuste positivo. En
   contabilidad, el stock con el que empieza la operación no es una ganancia: debería ir a una cuenta de capital o de
   apertura. A definir con el bloque contable.
- Recepción pendiente: cuando el stock negativo se debe a una compra sin cargar, la regularización es Registrar
   Recepción. Hay que verificar que ese caso de uso resuelva la alerta «stock inconsistente» igual que este.

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **INV-02**. Es el caso de uso más largo de la ronda. Todo se implementa, con estas decisiones de aplicación:

- **Semilla de una variedad dada de baja (lote 3).** El paso 4 ofrece las existencias **activas** del invernadero, aunque su insumo del
  catálogo esté inactivo: PROD-BAJ-VAR (regla 3) deja activa la existencia de la semilla para que su stock, si queda, se descarte con un
  ajuste. Solo las semillas pueden estar en esa situación (la baja de cualquier otro insumo deshabilita sus existencias).
- **Asientos contables: fuera de la ronda (D-45).** Se omiten las precondiciones c y d (ejercicio vigente y cuentas), la
  postcondición e y el asiento del paso 14, la regla «Asiento de un ajuste» y la mención del asiento en el resumen. Se
  implementa todo lo demás, incluido el **valor del ajuste** (cantidad × precio de referencia, en pesos con dos decimales), que
  el resumen del paso 12 sigue mostrando. Lo recupera el disparador «Cuando exista contabilidad con asientos»
  (`docs/disparadores.md`). El tema abierto «Cuenta de la carga inicial» (MD-90) queda para entonces.
- **Dos puntos donde el CU y el modelo no coinciden. Manda el CU (L7)**, y la diferencia está en `docs/temas_abiertos.md`:
  1. *Ajuste «otro» que suma.* El modelo (regla 3 de 8.23) dice que suma a un lote existente que elige quien lo registra. El CU
     (extensión 7e) lo manda por 7a: **crea un lote nuevo**. Se hace lo del CU.
  2. *Faltante sin lote.* El modelo (regla 4 de 8.23 y el ejemplo de la regla 5 de 8.19) dice que todo ingreso, incluido un
     ajuste positivo, cancela primero el faltante. El CU lo deja en cero **solo con un recuento físico** (paso 14.3) y
     lo reduce con una corrección entre lotes que lo tiene como destino. Una carga inicial o un «otro» que suma **no** lo
     tocan. Se hace lo del CU. La recepción (compras, fuera de la ronda) es la que cancela el faltante, y la define
     `compras` cuando exista.
- **Dos definiciones de «sin cobertura» que difieren.** El CU (postcondiciones h e i, extensión 12b) mide con el stock **sin lotes
  vencidos**; la regla 6 de 8.13 del modelo y el prototipo usan el stock total. Manda el CU. Está en `docs/patrones/stock.md`,
  «Stock inconsistente».
- **El recuento es de todo el insumo y por lote** (a diferencia del prototipo, que cuenta un lote por vez): la pantalla muestra
  todos los lotes con la cantidad registrada ya cargada, el Agrónomo cambia solo los que difieren, puede agregar lotes
  nuevos (10b) y quitarlos (10c), y el resumen (paso 12) lleva las cuatro cosas del CU. **Es el CU el que manda**, no el
  prototipo (regla L7). El resto de los motivos sigue al prototipo.
- **Dos pasos y una confirmación.** El servicio tiene dos funciones: `calcular_ajuste(actor, invernadero_id, insumo_id, motivo,
  entrada)` — **no escribe nada**: valida, calcula diferencias, valor, advertencias (12b) y devuelve el resumen con la «huella» del
  estado (las cantidades disponibles de los lotes y del faltante que usó) — y `confirmar_ajuste(actor, …, entrada, huella)`, que
  bloquea, **recalcula** y, si la huella ya no coincide, lanza `AjusteDesactualizado` (extensión 14a: no cambia nada y la
  pantalla vuelve al paso con los valores vigentes). La pantalla se actualiza tras cada dato con HTMX llamando a
  `calcular_ajuste` (requisito de 1 segundo); sin JavaScript, cada envío del formulario hace lo mismo con una página nueva.
- **Todo cambio de un lote = un movimiento** (regla 1 de 8.19), con `fecha` y hora actuales (zona horaria del invernadero:
  `America/Argentina/Buenos_Aires`, UTC−03:00). Cantidad siempre positiva; el tipo da el sentido. Sin documento de origen en
  ajustes. En la corrección entre lotes, la entrada se origina en su salida (R016, regla 2 de 8.19): `origen` de la entrada es la salida
  (`MovimientoInsumo.origen`, FK a `OrigenDocumento`, D-52; antes `movimiento_origen`).
- **Bloqueos.** Invernadero (`bloquear_invernadero_activo`) → `InsumoInvernadero` → todos los `LoteInsumo` del insumo en el
  invernadero (orden de id): evita que un consumo y un ajuste simultáneos dejen un lote negativo o descuenten dos veces
  (requisito especial). Etiqueta `concurrencia` en las pruebas.
- **Fecha de vencimiento válida:** hoy o posterior (la «fecha actual» es la del invernadero). Un lote nuevo del recuento con
  fecha pasada se rechaza.
- **Resultado sobre las alertas** (`reevaluar_alertas_del_insumo`, patrón de stock): resuelve o mantiene «stock inconsistente»
  (postcondiciones h e i), resuelve las alertas de vencimiento de los lotes agotados (j) y reevalúa «bajo el mínimo». El
  resumen final informa si «stock inconsistente» se resolvió o sigue activa (paso 15).
- **Salidas desde una alerta (extensión 1a).** La pantalla de alertas llega con MAE-02c y la campana con NOT-01: la acción
  «Ajustar» de una alerta de insumo abre CMP-AJT-STK con el invernadero y el insumo ya elegidos y el motivo propuesto (`recuento`
  para «stock inconsistente», `vencimiento` para «insumo vencido»).
- **Regularización con recepción pendiente.** `compras` no existe en esta ronda: la advertencia sobre la recepción pendiente se
  muestra como texto fijo en el aviso del recuento y no verifica nada.
- **Auditoría (D-36).** Una acción `ajuste_stock` **por ajuste**: afectados el invernadero y el insumo; `cambios` con el stock
  antes y después (texto); `datos` con la lista de lotes tocados (referencias), los movimientos creados (referencias), el
  motivo, la descripción y las alertas creadas y resueltas (`alertas_creadas`, `alertas_resueltas`). Los tres logs de las
  postcondiciones k, l y m son un solo registro con esos datos. Las referencias llevan texto, no `Decimal`.

