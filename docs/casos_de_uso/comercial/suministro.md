# Casos de uso · comercial · Suministro

Copia para el repo de tres casos de uso de los documentos de Drive (más COM-RSC-SUM y COM-ANL-RSC, nuevos del 21/11/2026, que todavía no están en Drive) de la carpeta «InfoPonia · Comercial · Análisis»: COM-PCT-SUM versión
0.3, COM-MOD-SUM versión 0.1 y COM-CNS-SUM versión 0.1 (alto nivel, de «CU · Consultas comerciales»). Cotejado con pendientes_CU, con «PCU ·
Cambios para pendientes_CU (comercial)» (secciones 1 a 16: las 6, 9 y 16 los cambian), con «MD · Cambios para el modelo de dominio
(comercial)» (MD-116, MD-120, MD-124, MD-126, MD-131 a MD-133, MD-139), con el modelo de dominio (reglas 4 a 8 de 8.11; 7 de 8.6; 10 y 16 de
8.8; 18 de 8.20) y con el glosario.

**El código va en la app `comercial`** (D-37). Archivos de pruebas: `comercial/tests/test_com_pct_sum.py`, `test_com_mod_sum.py`,
`test_com_cns_sum.py` y `test_calendario.py`. COM-PCT-SUM y COM-MOD-SUM incluyen PROD-ASG-STK (`docs/casos_de_uso/produccion/stock_maduro.md`;
cálculo en `docs/patrones/stock_maduro.md`, secciones 1 a 7). La pre-reserva diaria (PROD-PRR-SUM) está en
`docs/casos_de_uso/produccion/pre_reserva.md`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: COM-PCT-SUM y COM-MOD-SUM no numeran sus reglas (`test_fecha_de_fin_…`, `test_detalle_sucesor_…`), sus
postcondiciones son `test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…` (`test_ext_9e_…`). COM-CNS-SUM numera:
`test_regla_<numero>_…`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| COM-PCT-SUM | Pactar Suministro | Vendedor o Gerente | `comercial/tests/test_com_pct_sum.py` |
| COM-MOD-SUM | Modificar Suministro | Vendedor del contrato o Gerente | `comercial/tests/test_com_mod_sum.py` |
| COM-CNS-SUM | Consultar Suministro | Vendedor o Gerente | `comercial/tests/test_com_cns_sum.py` |
| COM-RSC-SUM | Rescindir Suministro | Gerente | `comercial/tests/test_com_rsc_sum.py` |
| COM-ANL-RSC | Dejar sin Efecto la Rescisión (alto nivel) | Gerente | `comercial/tests/test_com_anl_rsc.py` |

## COM-PCT-SUM · Pactar Suministro

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial.

**Versión:** 0.3

**Actor principal:** Vendedor. El Gerente también puede ejecutar este caso de uso; en ese caso elige al Vendedor responsable del contrato.

**Personal involucrado e intereses**

  - **Vendedor:** quiere registrar fielmente el contrato firmado con el cliente (variedades, cantidades, frecuencia de entrega, precios y cláusulas) y saber desde el principio si las entregas que caen dentro de la ventana de pre-reserva se pueden cubrir.
  - **Cliente:** quiere recibir, en cada sucursal y en cada fecha pactada, la cantidad acordada al precio acordado, y contar con un comprobante de lo que firmó.
  - **Agrónomo:** quiere que las entregas futuras queden registradas con anticipación, para planificar siembras que las cubran, y enterarse de las cosechas automáticas que se generen para validarlas.
  - **Capataz:** quiere recibir con anticipación las órdenes de cosecha que surgen de las primeras entregas.
  - **Gerente:** quiere que las cláusulas resolutorias, los incumplimientos tolerados y la multa queden registrados tal como figuran en el contrato, para poder evaluar quejas y discrepancias y, si corresponde, resolver el contrato.
  - **Organización (Jardín Botánico):** quiere asegurar un ingreso recurrente con contratos de suministro sin comprometer entregas que no puede cubrir, porque cada incumplimiento tiene un costo en indemnizaciones.

**Relaciones con otros casos de uso**

  - **«include»** PROD-ASG-STK · Asignar Stock Maduro: se incluye en el paso 14 para cada período de entrega cuya fecha cae dentro de la ventana de pre-reserva.
  - **«include»** Alta Cliente: se incluye en la extensión 4a, cuando el cliente no está registrado o está dado de baja.
  - **«include»** Modificación Cliente: se incluye en la extensión 8a, cuando un detalle se entrega en una dirección distinta de las registradas del cliente, y en la extensión 4b, cuando el cliente no tiene correo.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.

b. Existe al menos un Vendedor activo con invernaderos asignados.

c. Existe al menos una variedad de cultivo en estado “activo”.

**Garantías mínimas**

  - El contrato, sus detalles, sus cláusulas y, si corresponde, las reservas de stock y las órdenes de cosecha de los períodos que caen dentro de la ventana de pre-reserva se registran juntos o no se registra ninguno. Si el caso de uso se cancela o falla, no queda ninguno de ellos ni su log de auditoría.
  - El alta de un cliente y el registro de una dirección nueva, hechos mediante los casos de uso incluidos, no se revierten aunque el contrato no se confirme.
  - Ningún lote ni partida de cámara queda reservado por encima de su stock libre, aun cuando otro Vendedor, el Agrónomo o InfoPonia reserven stock al mismo tiempo.
  - Al pactar el suministro no se genera ningún pago ni asiento contable.

**Garantías de éxito (Postcondiciones)**

a. Se creó un contrato de suministro en estado “vigente”, con fecha de realización igual a la fecha actual, la duración en meses indicada, la fecha de fin calculada, los incumplimientos tolerados y la multa por resolución indicadas, y la cantidad de incumplimientos en cero. Está asociado al cliente y al Vendedor responsable, y tiene una cláusula del suministrado, con plazo de pago e indemnización por retraso en el pago, que rige todas sus entregas.

b. Se crearon uno o más detalles de suministro en estado “vigente”. Cada uno tiene su variedad, su dirección de entrega (una de las direcciones del cliente), la cantidad por período, el período de entrega, la fecha de la primera entrega, el mecanismo de precio y el precio unitario inicial. Si el mecanismo es de ajuste periódico, tiene además el porcentaje de ajuste y cada cuántos meses se aplica. El contrato no repite el par (variedad, dirección).

c. Cada detalle quedó con exactamente una cláusula del suministrante, con plazo de entrega, indemnización por retraso en la entrega, cantidad mínima de mercadería e indemnización por mercadería faltante.

d. Por cada período de entrega cuya fecha cae dentro de la ventana de pre-reserva, se ejecutó PROD-ASG-STK. Este creó una o más reservas de stock asociadas al detalle, con fecha de entrega igual a la fecha del período y cantidad total igual a la cantidad por período.

e. Cada reserva con al menos una línea de lote quedó en estado “activa” y tiene una orden de cosecha en estado “a realizar”, con la fecha programada y la prioridad de la regla “Cosechas automáticas” y el Capataz del invernadero como responsable. Se notificó la orden al Capataz y al Agrónomo del invernadero, a este último para que la valide o la modifique.

f. Cada reserva con todas sus líneas de cámara quedó en estado “lista para entrega”. Si todas las reservas de un período quedaron así, se disparó la planificación automática de la Entrega de ese período, a cargo de InfoPonia.

g. Se envió al cliente un correo con el comprobante del contrato.

h. Se creó un log de auditoría con el usuario que registró el contrato, su rol, fecha, hora e identificador del contrato de suministro creado.

i. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada detalle de suministro, cláusula resolutoria, reserva de stock, línea de reserva y orden de cosecha creados.

**Escenario principal de éxito (o Flujo Básico)**

1.  **El Vendedor inicia el registro de un contrato de suministro.**
2.  **El Sistema solicita identificar al cliente.**
3.  **El Vendedor introduce el CUIT del cliente.**
4.  **El Sistema presenta los datos del cliente y sus direcciones registradas.**
5.  **El Vendedor introduce la duración del contrato en meses, los incumplimientos tolerados, la multa por resolución y la cláusula del suministrado: el plazo de pago y la indemnización por retraso en el pago.**
6.  **El Sistema verifica los datos del contrato y su cláusula del suministrado, y presenta la fecha de fin calculada.**
7.  **El Sistema presenta las variedades activas.**
8.  **El Vendedor selecciona una variedad y una dirección de entrega del cliente, e indica la cantidad por período, el período de entrega, la fecha de la primera entrega, el mecanismo de precio “fijo” y el precio unitario.**
9.  **El Sistema verifica los datos del detalle y presenta el calendario de entregas y la cantidad total a entregar en el contrato para ese detalle.**
10. **El Vendedor introduce la cláusula del suministrante del detalle: plazo de entrega, indemnización por retraso en la entrega, cantidad mínima de mercadería e indemnización por mercadería faltante.**
11. **El Sistema verifica la cláusula y registra el detalle.** \*El Vendedor repite los pasos 7-11 hasta incluir todos los detalles del contrato.\*
12. **El Sistema presenta el resumen del contrato: cliente, Vendedor responsable, duración, fecha de fin, incumplimientos tolerados, multa por resolución, plazo de pago e indemnización por retraso en el pago y, para cada detalle, la variedad, la dirección, la cantidad por período, el calendario de entregas, el precio y su mecanismo, y su cláusula del suministrante.**
13. **El Vendedor confirma el contrato.**
14. **El Sistema registra el contrato de suministro y sus detalles en estado “vigente”, con sus cláusulas. Para cada período de entrega que cae dentro de la ventana de pre-reserva, incluye PROD-ASG-STK · Asignar Stock Maduro. Registra la auditoría correspondiente.**
15. **El Sistema envía al cliente el correo con el comprobante del contrato.**
16. **El Sistema informa al Vendedor que el contrato fue registrado y presenta su identificador.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 13, el actor cancela el registro:**

1.  El Sistema descarta los datos del contrato sin registrarlo. El cliente dado de alta y la dirección agregada durante el caso de uso permanecen registrados.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial del contrato, sus detalles, cláusulas, reservas y cosechas.
2.  Al restablecerse, el Sistema informa al actor que el contrato no fue registrado. El cliente dado de alta y la dirección agregada permanecen registrados.
3.  El actor reinicia el caso de uso desde el paso 1.

**1a. El actor es el Gerente:**

1.  El Sistema presenta los Vendedores activos con sus invernaderos.
2.  El Gerente selecciona el Vendedor responsable del contrato.
3.  El caso de uso continúa en el paso 2. En adelante, los invernaderos habilitados son los del Vendedor seleccionado.

**3a. El Vendedor no conoce el CUIT del cliente:**

1.  El Vendedor busca al cliente por nombre, apellido o razón social.
2.  El Sistema presenta los clientes que coinciden.
3.  El Vendedor selecciona uno. El caso de uso continúa en el paso 4.

**3a.2a. Ningún cliente coincide con la búsqueda:**

1.  El Sistema informa que no hay clientes que coincidan.
2.  El Vendedor busca con otro criterio (vuelve a 3a.1), introduce un CUIT (vuelve al paso 3) o da de alta al cliente (continúa en 4a.2).

**4a. El cliente no está registrado o está dado de baja:**

1.  El Sistema informa que el cliente no está registrado, o que está dado de baja, y ofrece registrarlo o reactivarlo.
2.  Se incluye el caso de uso Alta Cliente, que registra al cliente o lo reactiva.
3.  El caso de uso continúa en el paso 4 con ese cliente.

**4b. El cliente no tiene correo registrado:**

1.  El Sistema informa que no se puede pactar un suministro con un cliente sin correo, porque el correo es necesario para el comprobante y para los enlaces de confirmación de cada entrega, y ofrece cargarlo.
2.  Se incluye Modificación Cliente, que registra el correo.
3.  El caso de uso continúa en el paso 4. Si el Vendedor no lo carga, cancela.

**6a. Algún dato del contrato (duración, incumplimientos tolerados, multa por resolución, plazo de pago o indemnización por retraso en el pago) está fuera de su rango (reglas “Datos del contrato” y “Cláusula del suministrado”):**

1.  El Sistema señala el dato inválido.
2.  El Vendedor lo corrige (vuelve al paso 5).

**8a. El detalle se entrega en una dirección distinta de las registradas del cliente:**

1.  Se incluye el caso de uso Modificación Cliente, que agrega la nueva dirección al cliente.
2.  El Vendedor selecciona la nueva dirección y el caso de uso continúa en el paso 8.

**8b. El mecanismo de precio es de ajuste periódico:**

1.  El Vendedor indica, además del precio unitario inicial, el porcentaje de cada ajuste y cada cuántos meses se aplica.
2.  En el paso 9, el Sistema presenta también el precio que tendrá cada entrega del calendario.

**9a. La fecha de la primera entrega es anterior a la fecha actual o posterior a la fecha de fin del contrato:**

1.  El Sistema señala el error e informa el rango admitido.
2.  El Vendedor corrige la fecha (vuelve al paso 8).

**9b. Algún dato del detalle o del precio (cantidad por período, período de entrega, precio unitario, porcentaje de ajuste o meses de ajuste) está fuera de su rango (reglas “Datos del detalle” y “Datos del precio”):**

1.  El Sistema señala el dato inválido.
2.  El Vendedor lo corrige (vuelve al paso 8).

**9c. El contrato ya tiene un detalle con la misma variedad y la misma dirección:**

1.  El Sistema informa que el contrato no puede repetir ese par y presenta el detalle existente.
2.  El Vendedor cambia la variedad o la dirección (vuelve al paso 8).

**9d. El cliente ya tiene otro contrato de suministro vigente de la misma variedad a la misma dirección:**

1.  El Sistema advierte la superposición, identifica el contrato vigente e indica que, si el cliente quiere cambiar las condiciones de ese contrato, corresponde modificarlo (Modificar Suministro, CU-38).
2.  El Vendedor continúa (sigue en el paso 10), edita el detalle (vuelve al paso 8) o cancela.

**9e. Algún período de entrega dentro de la ventana de pre-reserva no puede cubrirse con el stock maduro libre que queda para su fecha, después de cubrir, en orden de fecha, los períodos anteriores del contrato de la misma variedad:**

1.  El Sistema informa, para cada período afectado, su fecha y la cantidad disponible.
2.  El Vendedor cambia la fecha de la primera entrega, el período de entrega o la cantidad por período (vuelve al paso 8).

**9f. El mecanismo es de ajuste periódico y los meses de ajuste superan la duración del contrato:**

1.  El Sistema advierte que el precio no se ajustará durante el contrato.
2.  El Vendedor mantiene los datos (continúa en el paso 10) o los corrige (vuelve al paso 8).

**11a. La cantidad mínima de mercadería es cero o supera la cantidad por período:**

1.  El Sistema señala el error e informa el rango admitido.
2.  El Vendedor corrige la cláusula (vuelve al paso 10).

**11b. Algún plazo o indemnización de la cláusula del suministrante no es un número válido o está fuera de su rango (regla “Cláusula del suministrante”):**

1.  El Sistema señala el dato inválido.
2.  El Vendedor lo corrige (vuelve al paso 10).

**7-11a. El Vendedor quita un detalle o modifica alguno de sus datos:**

1.  El Sistema actualiza el detalle, su calendario y su cláusula del suministrante.
2.  El caso de uso continúa en el paso 7 o en el paso 12.

**12a. El contrato no tiene ningún detalle:**

1.  El Sistema informa que el contrato debe incluir al menos un detalle.
2.  El Vendedor agrega un detalle (vuelve al paso 7) o cancela.

**13a. El Vendedor quiere corregir un dato del resumen:**

1.  El Vendedor indica el dato a corregir y el caso de uso vuelve al paso donde ese dato se ingresó (1a.2 si el actor es el Gerente, 3 o 3a, 5, 8 o 10).

**13a.1a. Cambió el Vendedor responsable (solo si el actor es el Gerente):**

1.  El Sistema vuelve a verificar el stock de la ventana de pre-reserva con los invernaderos del nuevo Vendedor e informa los detalles que ya no pueden cubrirse.
2.  El Vendedor ajusta esos detalles o los quita (7-11a). Los demás datos se conservan.

**13a.1b. Cambió el cliente:**

1.  El Sistema descarta la dirección de entrega de cada detalle, porque era del cliente anterior.
2.  El Sistema presenta las direcciones del nuevo cliente, y el Vendedor elige una para cada detalle (paso 8).

**13a.1c. Cambió la duración:**

1.  El Sistema recalcula la fecha de fin y vuelve a verificar la fecha de la primera entrega y el calendario de cada detalle.

**14a. El stock maduro libre de algún período dentro de la ventana cambió mientras se cargaba el contrato y ya no alcanza:**

1.  El Sistema no registra el contrato e informa, para cada detalle afectado, la cantidad disponible.
2.  El Vendedor ajusta los detalles (vuelve al paso 8) o cancela.

**15a. El Sistema no logra enviar el correo al cliente:**

1.  El contrato permanece registrado.
2.  El Sistema reintenta el envío y avisa al Vendedor que el comprobante está pendiente de envío.

**Requisitos especiales**

  - Tras cada dato ingresado por el actor (pasos 3 a 11), la pantalla se actualiza con las verificaciones, la fecha de fin, el calendario de entregas y los precios calculados en no más de 1 segundo.
  - El registro del paso 14 se completa típicamente en 5 a 10 segundos. Si supera los 10 segundos, el Sistema muestra un indicador de progreso.
  - El paso 14, incluida la ejecución de PROD-ASG-STK, se ejecuta como una única transacción. El alta de cliente y la dirección nueva quedan fuera de esa transacción.
  - El control de concurrencia sobre el stock libre de lotes y partidas impide la sobreasignación entre contratos, ventas, cosechas manuales y asignaciones automáticas simultáneas.
  - El Vendedor solo puede comprometer stock de sus invernaderos. El Gerente puede registrar contratos para cualquier Vendedor, y el log de auditoría registra al usuario que cargó el contrato.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los precios, indemnizaciones y multas se expresan en pesos argentinos, con dos decimales.
  - El comprobante es interno y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio**

  - **Vendedor responsable e invernaderos habilitados:** el actor, si es un Vendedor; el seleccionado, si el actor es el Gerente. Todo contrato pertenece a un único Vendedor, y el stock de sus entregas sale solo de los invernaderos de ese Vendedor. (Paso 1 y extensión 1a)
  - **Correo del cliente:** es obligatorio para pactar un suministro (regla 18 de 8.20). (Extensión 4b)
  - **Fecha de fin:** atributo derivado. Es el mismo día del mes que la fecha de realización, N meses después (N = duración). Si ese día no existe en el mes de llegada, es el último día de ese mes (por ejemplo, 31/01 + 1 mes = 28/02, o 29/02 en un año bisiesto). La fecha de realización es la de registro y marca el inicio del contrato. (Paso 6)
  - **Datos del contrato:** duración, número entero de al menos un mes y hasta 120 meses; incumplimientos tolerados, número entero de al menos uno y hasta 99; multa por resolución, monto en pesos igual o mayor que cero y hasta $ 99.999.999,99. La cantidad de incumplimientos nace en cero y suma solo los incumplimientos de la empresa; el atraso en el pago del cliente no cuenta. (Pasos 5 y 6)
  - **Calendario de entregas:** las fechas de entrega de un detalle son la fecha de la primera entrega más k veces el período de entrega (k = 0, 1, 2…), mientras no superen la fecha de fin. (Paso 9)
  - **Datos del detalle:** cantidad por período, número entero de al menos una planta y hasta 500.000 plantas; período de entrega, número entero de al menos un día y hasta 365 días (opciones rápidas: 7, 14 y 30); fecha de la primera entrega, igual o posterior a la fecha actual y anterior o igual a la fecha de fin. (Paso 9)
  - **Dirección y modalidad:** la dirección de cada detalle es una de las direcciones del cliente, y el suministro es siempre con envío. Un contrato no repite el par (variedad, dirección). (Pasos 8 y 9)
  - **Precio de cada entrega:** con mecanismo fijo, el precio unitario inicial. Con ajuste periódico, el precio inicial × (1 + porcentaje de ajuste) elevado a la cantidad de ajustes cumplidos. La cantidad de ajustes cumplidos es la parte entera de los meses transcurridos desde la fecha de realización hasta la entrega, dividida por los meses de ajuste. Los meses transcurridos son meses calendario completos desde la fecha de realización: con fecha de realización el 22/10, el 21/12 cuenta 1 mes y el 22/12 cuenta 2. El precio de cada entrega se calcula siempre desde el precio inicial y se redondea a 2 decimales; los redondeos no se acumulan. Por ejemplo, $1.000 con un ajuste del 3 % cada 2 meses vale $1.000 en los meses 0 y 1, $1.030 en los meses 2 y 3, y $1.060,90 en los meses 4 y 5. El precio aplicado se guarda en el detalle de entrega, así que un ajuste posterior no altera las entregas pasadas. (Pasos 8 y 9, extensión 8b)
  - **Datos del precio:** precio unitario entre $ 0,01 y $ 9.999.999,99; porcentaje de ajuste entre 0,01 % y 100 % y meses de ajuste, número entero de al menos uno y hasta 60, solo con ajuste periódico. Con mecanismo fijo, esos dos datos quedan vacíos. (Paso 9 y extensión 8b)
  - **Cláusula del suministrado:** el contrato tiene exactamente una, que rige el pago de todas sus entregas, cualquiera sea su detalle (MD-124). (Pasos 5 y 6)
      - **Plazo de pago:** días desde la entrega para que el cliente pague; entre 0 y 365 días. Define el vencimiento del pago de cada entrega: fecha real de entrega + plazo de pago.
      - **Indemnización por retraso en el pago:** pesos por cada día de atraso en el pago de una entrega, de $ 0,00 a $ 9.999.999,99. Se aplica una vez por entrega, no por detalle.
  - **Cláusula del suministrante:** cada detalle tiene exactamente una. (Pasos 10 y 11)
      - **Plazo de entrega:** días de tolerancia después de la fecha del período antes de considerar la entrega retrasada; entre 0 y 365 días.
      - **Indemnización por retraso en la entrega:** pesos por cada día de retraso, pasada la tolerancia.
      - **Cantidad mínima de mercadería:** plantas mínimas por entrega; entre 1 planta y la cantidad por período.
      - **Indemnización por mercadería faltante:** pesos por cada planta faltante por debajo del mínimo.
      - Las indemnizaciones se expresan en pesos, van de $ 0,00 a $ 9.999.999,99 y no se ajustan con el precio.
  - **Ventana de pre-reserva:** un período cae dentro de la ventana si su fecha es igual o anterior a la fecha actual más los días de pre-reserva de la configuración operativa. Esos períodos se reservan al registrar el contrato, con PROD-ASG-STK; los siguientes los reserva InfoPonia cuando entran en la ventana (regla 16 de 8.8). (Pasos 9 y 14)
  - **Stock maduro libre para la fecha de un período:** stock libre de los lotes y las partidas de los invernaderos del Vendedor que PROD-ASG-STK puede tomar para esa fecha (sus reglas “Lote elegible” y “Partida elegible”). No cuentan los lotes cuya fecha máxima de cosecha es anterior a la fecha programada que tendría su cosecha (regla 11 de 8.6; regla 3 de 8.20), ni los de un invernadero sin Capataz activo. La verificación es acumulada por variedad: los períodos de todos los detalles del contrato que caen dentro de la ventana se cubren en orden de fecha, con el orden de asignación de PROD-ASG-STK (regla 7 de 8.6), y cada uno se verifica contra lo que dejan libre los anteriores. (Extensión 9e y paso 14)
  - **Cosechas automáticas:** las crea PROD-ASG-STK con su regla “Cosechas automáticas” (regla 3 de 8.11), usando el parámetro de anticipación de suministro (diasAnticipacionCosechaSuministro). La fecha programada es la mayor entre la fecha actual y la fecha del período menos la anticipación efectiva, y la prioridad es media. Se notifican al Capataz y al Agrónomo del invernadero, que puede validarlas o modificarlas. (Paso 14)
  - **Suministro superpuesto:** si el cliente ya tiene un contrato de suministro vigente de la misma variedad a la misma dirección, el Sistema advierte y permite continuar. Continuar es una decisión explícita del Vendedor. Es válido, por ejemplo, en una renovación firmada antes de que venza el contrato vigente o en un pedido de temporada con condiciones propias. (Extensión 9d)
  - **Estado inicial:** el contrato y sus detalles quedan “vigentes”, con la cantidad de incumplimientos en cero y la fecha de realización igual a la fecha de registro. (Paso 14)

**Lista de tecnología y variaciones de datos**

  - **3a.** El cliente se identifica por CUIT, o se busca por nombre, apellido o razón social.
  - **5a.** La duración se expresa en meses, como número entero.
  - **8a.** La fecha de la primera entrega se ingresa con formato dd/mm/aaaa, mediante calendario o teclado.
  - **8b.** El período de entrega se elige entre las opciones rápidas (7, 14 o 30 días) o se ingresa como número entero de días.
  - **8c.** El precio unitario se expresa en pesos argentinos con dos decimales. El porcentaje de ajuste se expresa con hasta dos decimales.
  - **5a.** El plazo de pago se expresa en días, como número entero, y la indemnización por retraso en el pago, en pesos argentinos con dos decimales.
  - **10a.** Los plazos se expresan en días, como números enteros. Las indemnizaciones se expresan en pesos argentinos con dos decimales.
  - **15a.** El correo al cliente contiene el comprobante del contrato: detalles, cantidades, períodos, calendario de entregas, precio y mecanismo de ajuste, la cláusula del suministrante de cada detalle y la cláusula del suministrado del contrato. Aclara que es un comprobante interno sin validez fiscal.

**Frecuencia**

A confirmar con el Jardín Botánico. Se espera que ocurra pocas veces por mes, cada vez que se cierra un contrato con un supermercado u otra organización.

**Temas abiertos**

  - Modificar Suministro (CU-38) tendrá que definir qué pasa con las reservas, cosechas y entregas ya creadas si cambia una cantidad, una fecha o un período, incluido el aumento o la reducción de la cantidad por período por mutuo acuerdo con el cliente.
  - La cancelación del contrato por mutuo acuerdo queda como mejora futura. No existe el estado “cancelado” hasta que haya un caso de uso que lo produzca.
  - Los máximos de los datos son valores provisionales tomados del prototipo; hay que confirmarlos con el Jardín Botánico.

**Cambios respecto de la versión anterior (0.2)** (resumen): la cláusula del suministrado pasa al contrato (MD-124): postcondiciones a y c, pasos 5, 6, 10, 11 y 12, extensiones 6a, 11b y 7-11a, reglas «Cláusula del suministrado» y «Cláusula del suministrante», y 5a y 15a de la lista de tecnología.

## COM-MOD-SUM · Modificar Suministro

Caso de uso nuevo del módulo comercial (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza a CU-38 de «Documentacion para la IA» y especifica el caso 24 de pendientes\_CU. Decisiones del 20/11/2026 aplicadas: el cambio rige desde el primer período posterior a la ventana de pre-reserva (G); modificar un detalle lo finaliza y crea un detalle sucesor (H, opción 2; MD-131); lo modificable según la decisión I; el vencimiento de pago se fija en cada entrega (J; MD-132); sin enlace de aceptación del cliente (K); los meses de ajuste del detalle nuevo se cuentan desde su primera entrega (M).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Contratos.

**Versión:** 0.1

**Actor principal:** Vendedor del contrato. El Gerente también puede ejecutarlo.

**Personal involucrado e intereses**

  - **Vendedor:** quiere reflejar lo que acordó con el cliente sin rehacer el contrato.
  - **Gerente:** quiere que ningún cambio deshaga reservas, cosechas o entregas ya en marcha, y que quede el historial de lo pactado.
  - **Cliente:** quiere el comprobante con las nuevas condiciones y saber desde cuándo rigen.
  - **Agrónomo:** quiere que lo ya planificado en el invernadero no cambie de golpe.

**Relaciones con otros casos de uso**

  - **Incluye («include»):** PROD-ASG-STK · Asignar Stock Maduro, solo para un detalle nuevo con períodos dentro de la ventana (extensión 5b).
  - **Lo precede:** COM-PCT-SUM · Pactar Suministro, que lo sugiere en su extensión 9d.
  - **Relacionados:** la pre-reserva diaria de InfoPonia, que reserva los períodos del detalle nuevo cuando entran en la ventana (regla 16 de 8.8); COM-RSV-SUM, que usa los incumplimientos tolerados.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Vendedor o Gerente.

b. Existe al menos un suministro «vigente»; si el actor es Vendedor, de un contrato del que es Vendedor.

**Garantías mínimas**

  - La modificación es atómica. Si falla o se cancela, el contrato queda como estaba.
  - Ningún período que ya cae dentro de la ventana de pre-reserva cambia: sus reservas, cosechas y entregas se conservan.
  - Ningún período pasado cambia su cantidad, su precio ni sus cláusulas.

**Garantías de éxito (Postcondiciones)**, según lo que modificó el actor:

a. **Detalle modificado** (cantidad por período, período de entrega, precio o mecanismo, cláusula del suministrante): el detalle pasó a «finalizado», con su fecha de fin en la de su último período dentro de la ventana, y se creó un detalle «vigente» con las condiciones nuevas, su cláusula del suministrante, la misma variedad y la misma dirección, vinculado al anterior por «reemplaza a» (MD-131).

b. **Detalle agregado:** se creó un detalle «vigente» con su cláusula del suministrante. Si tiene períodos dentro de la ventana, quedaron reservados (PROD-ASG-STK).

c. **Detalle terminado:** pasó a «finalizado», con su fecha de fin en su último período dentro de la ventana, sin multa.

d. **Duración cambiada:** se actualizaron la duración y la fecha de fin del contrato.

e. **Incumplimientos tolerados o multa por resolución cambiados:** se actualizaron.

f. **Cláusula del suministrado cambiada:** se actualizó y rige para las entregas que se concreten desde la confirmación. Las ya concretadas conservan su vencimiento de pago (MD-132).

g. **Vendedor responsable cambiado (solo el Gerente):** el contrato pasó al Vendedor nuevo.

h. Se le envió al cliente por correo el comprobante del contrato modificado, con cada cambio y la fecha desde la que rige.

i. Si el actor fue el Gerente, se notificó al Vendedor. Si cambió el Vendedor responsable, se notificó al anterior y al nuevo.

j. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del contrato, cada cambio con sus valores anterior y nuevo, y los detalles finalizados y creados.

**Escenario principal de éxito (o Flujo Básico)**

(El Vendedor cambia la cantidad por período de un detalle.)

1.  El Vendedor inicia la modificación de un suministro.
2.  El Sistema presenta los suministros «vigentes» de sus contratos, con el cliente, la fecha de fin y la cantidad de detalles vigentes.
3.  El Vendedor selecciona un suministro.
4.  El Sistema presenta el contrato: duración, fecha de fin, incumplimientos tolerados y acumulados, multa por resolución y cláusula del suministrado; cada detalle vigente, con su historial de condiciones (la cadena «reemplaza a»); y, para cada detalle, la fecha desde la que rige un cambio, que es su primer período fuera de la ventana.
5.  El Vendedor elige un detalle e indica las condiciones nuevas.
6.  El Sistema verifica los datos con las reglas «Datos del detalle» y «Datos del precio» de COM-PCT-SUM y presenta el detalle tal como queda: hasta qué fecha rigen las condiciones actuales, desde cuál las nuevas y el calendario de los nuevos períodos.

\*El Vendedor repite los pasos 5 y 6 por cada cambio.\*

7.  El Vendedor termina la carga de cambios.
8.  El Sistema presenta el resumen de todos los cambios, con la fecha desde la que rige cada uno.
9.  El Vendedor confirma.
10. El Sistema vuelve a verificar que el contrato siga «vigente» y que la fecha desde la que rige cada cambio siga fuera de la ventana. Luego, en una única transacción, finaliza y crea los detalles, actualiza el contrato y registra la auditoría.
11. El Sistema envía al cliente el comprobante del contrato modificado.
12. El Sistema informa al Vendedor que el contrato quedó modificado.

> Nota de la copia: en el documento de Drive los pasos 7 a 12 aparecen numerados otra vez desde 1, porque la lista se corta con la línea
> «El Vendedor repite…». Las extensiones los citan como 7 a 12 (7a, 10a, 10b, 11a): acá se numeran así.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 9, el actor cancela:**

1.  El Sistema descarta todos los cambios.

**\*b. En cualquier momento el Sistema falla:**

1.  El Sistema revierte cualquier registro parcial y, al restablecerse, informa que la modificación no se registró.

**1a. El actor es el Gerente:**

1.  En el paso 2, el Sistema presenta todos los suministros vigentes.
2.  En el paso 5 puede además cambiar el Vendedor responsable, que debe estar activo.
3.  En el paso 11, el Sistema notifica al Vendedor o a los Vendedores afectados.

**5a. El actor indica una fecha de inicio posterior a la propuesta:**

1.  El Sistema acepta la fecha de cualquier período posterior a la ventana. Los períodos que quedan entre la ventana y esa fecha siguen con las condiciones actuales.

**5b. El actor agrega un detalle:**

1.  El Vendedor carga la variedad, la dirección, la cantidad, el período, la fecha de primera entrega, el precio y la cláusula del suministrante, con las reglas de COM-PCT-SUM.
2.  Si la variedad y la dirección coinciden con otro detalle vigente del contrato, el Sistema lo rechaza y propone modificar ese detalle. Si coinciden con un detalle vigente de otro contrato del cliente, advierte la superposición sin bloquear, como en COM-PCT-SUM 9d.
3.  Si el detalle tiene períodos dentro de la ventana, el Sistema verifica el stock acumulado de esos períodos, como en COM-PCT-SUM 9e. Si no alcanza, informa los períodos afectados y su cantidad disponible. En el paso 10 los reserva con PROD-ASG-STK.

**5c. El actor termina un detalle:**

1.  El Sistema presenta hasta qué período se entrega e informa que no lleva multa, porque es de mutuo acuerdo.
2.  **5c.1a.** Si no queda ningún otro detalle vigente, el Sistema informa que equivale a terminar el contrato y propone acortar la duración hasta ese período (extensión 5d).

**5d. El actor cambia la duración:**

1.  Si la extiende, el Sistema presenta la nueva fecha de fin y los períodos que se agregan a cada detalle vigente.
2.  Si la acorta, la nueva fecha de fin no puede ser anterior al último período dentro de la ventana; si lo es, el Sistema informa la fecha mínima. Acortar la duración es la forma de terminar el contrato antes de tiempo por mutuo acuerdo, sin multa.

**5e. El actor cambia los incumplimientos tolerados o la multa:**

1.  Si los incumplimientos tolerados nuevos no superan los acumulados, el Sistema informa que el contrato quedaría resuelto y pide un valor mayor.

**5f. El actor cambia la cláusula del suministrado:**

1.  El Sistema informa que rige para las entregas que se concreten desde la confirmación y que las ya concretadas conservan su vencimiento.

**5g. El actor intenta cambiar el cliente o la fecha de realización:**

1.  El Sistema informa que no se pueden cambiar y que corresponde pactar un contrato nuevo.

**6a. Los datos no son válidos:**

1.  El Sistema indica el error, con los mismos límites que COM-PCT-SUM, y el actor lo corrige.

**7a. El actor no indicó ningún cambio:**

1.  El Sistema lo informa y vuelve al paso 4.

**10a. Al registrar, un período entró en la ventana desde el paso 6 (por ejemplo, porque pasó la medianoche o corrió la pre-reserva):**

1.  El Sistema no registra ningún cambio, recalcula la fecha desde la que rige cada cambio y vuelve al paso 8.

**10b. Al registrar, el contrato ya no está vigente (por ejemplo, porque se resolvió por incumplimientos) o lo modificó otra operación:**

1.  El Sistema no registra ningún cambio, informa la situación actual y vuelve al paso 2.

**11a. El Sistema no logra enviar el correo:**

1.  La modificación permanece registrada y el Sistema reintenta el envío.

**Requisitos especiales**

  - La interfaz está pensada para computadora.
  - El paso 10 se ejecuta como una única transacción, que incluye PROD-ASG-STK.
  - La modificación se serializa con la pre-reserva diaria, COM-RSV-SUM y otras modificaciones del mismo contrato.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción.

**Reglas de negocio**

  - **Quién modifica:** el Vendedor del contrato o el Gerente. El Vendedor responsable lo cambia solo el Gerente. (Paso 1 y extensión 1a)
  - **Desde cuándo rige un cambio:** desde el primer período del detalle posterior a la ventana de pre-reserva (fecha actual + díasPreReservaSuministro). Los períodos dentro de la ventana y los pasados conservan sus condiciones. Funciona como el preaviso del contrato. (Paso 4 y extensión 5a)
  - **Detalle sucesor:** modificar un detalle lo finaliza y crea uno nuevo, vinculado por «reemplaza a». La fecha de fin del anterior es la de su último período conservado; la fecha de primera entrega del nuevo es la del primer período con las condiciones nuevas. Las reservas y entregas siguen asociadas al detalle con el que se pactaron. (Postcondición a; MD-131)
  - **Par (variedad, dirección):** en un contrato no puede haber dos detalles vigentes con la misma variedad y la misma dirección; los finalizados no cuentan. (Extensión 5b)
  - **Precio con ajuste periódico en el detalle nuevo:** el precio inicial es el indicado y los meses de ajuste se cuentan desde la fecha de primera entrega del detalle nuevo. (Paso 5)
  - **Terminación por mutuo acuerdo:** terminar un detalle o acortar la duración no aplica multa ni cuenta como incumplimiento. (Extensiones 5c y 5d)
  - **Incumplimientos tolerados:** el valor nuevo debe ser mayor que los acumulados. (Extensión 5e)
  - **Vencimiento de pago:** se fija en cada entrega al concretarse (MD-132); por eso un cambio de la cláusula del suministrado no altera los vencimientos ya fijados. (Extensión 5f)
  - **No modificable:** el cliente y la fecha de realización. (Extensión 5g)
  - **Comprobante:** el cliente recibe el contrato modificado por correo. No hay enlace de aceptación: el acuerdo se hace fuera del Sistema y el Vendedor lo registra.

**Frecuencia:** ocasional.

**Temas abiertos**

  - Confirmar con el Jardín Botánico que un preaviso igual a la ventana de pre-reserva (14 días con la configuración actual) es aceptable comercialmente.

## COM-CNS-SUM · Consultar Suministro

Del documento de Drive «CU · Consultas comerciales · COM-CNS-CVT/SUM/SRV (v0.1)», del 20/11/2026: caso de uso de alto nivel. Reemplaza a
CU-39 de «Documentacion para la IA» (PCU, sección 10).

**Actores:** Vendedor o Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** ver el estado, el cumplimiento y la historia de condiciones de un contrato de suministro.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Vendedor o de Gerente.

**Postcondición:**

a. Ninguna: es una consulta.

**Reglas:**

1.  Alcance: el Vendedor ve los suministros de los que es Vendedor; el Gerente, todos.
2.  Filtros: cliente, estado (vigente, finalizado o resuelto), rango de fechas (de realización o de fin) y, solo para el Gerente, Vendedor.
3.  Listado: cliente, fecha de realización, fecha de fin, cantidad de detalles vigentes, incumplimientos acumulados frente a tolerados y estado.
4.  Ficha · contrato: duración, fecha de fin, multa por resolución, cláusula del suministrado y, si se resolvió, la fecha de resolución (MD-120).
5.  Ficha · detalles: variedad, dirección, cantidad por período, período, precio (con el precio vigente hoy si tiene ajuste periódico), cláusula del suministrante y estado. Un detalle con sucesores se muestra como una sola línea con su historial: qué condiciones rigieron hasta qué fecha (MD-131).
6.  Ficha · calendario: los períodos pasados y futuros de cada detalle, indicando si está fuera de la ventana, reservado, entregado o con faltante.
7.  Ficha · entregas: fecha, estado, confirmación del cliente, monto a cobrar, vencimiento y estado de pago (pendiente, pagada o vencida).
8.  Ficha · solicitudes de revisión: quejas y discrepancias del contrato, con su estado y si cuentan como incumplimiento.
9.  Si al contrato le falta un solo incumplimiento para resolverse, la ficha lo destaca.
10. Desde la ficha se puede ir a Modificar Suministro (COM-MOD-SUM) si está vigente, a Registrar Cobro de Suministro (COM-REG-CBR) si hay entregas sin pagar y a la consulta de una solicitud (COM-CNS-SRV).

## COM-RSC-SUM · Rescindir Suministro

Caso de uso nuevo del módulo comercial (versión 0.1, 21/11/2026), con el formato de «CU extendidos». Lo escribió Claude en el lote C3 con
las decisiones del estudiante del 21/11/2026: rescisión **por mutuo acuerdo** (art. 1076 del Código Civil y Comercial), la registra el
Gerente, se conservan los períodos que ya están en la ventana de pre-reserva, se puede dejar sin efecto hasta la última entrega conservada
(COM-ANL-RSC) y el motivo es una lista cerrada con descripción. Reemplaza la «mejora futura» de cancelación por mutuo acuerdo (1.10 y
observación 2 de 8.11 del modelo; temas abiertos de COM-PCT-SUM y COM-RSV-SUM). **Pendiente de pasar a Drive** (lo pega el estudiante).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Comercial / Contratos.

**Versión:** 0.1

**Actor principal:** Gerente.

**Personal involucrado e intereses**

  - **Gerente:** quiere dejar registrado que la empresa y el cliente acordaron terminar el contrato antes de tiempo, sin multa, y que el
    sistema deje de comprometer stock para ese contrato.
  - **Cliente:** quiere recibir lo que ya estaba en marcha y una constancia de lo acordado, con la fecha de la última entrega.
  - **Vendedor:** quiere enterarse de que su contrato termina y hasta cuándo se entrega.
  - **Agrónomo y Capataz:** quieren que lo ya planificado (cosechas de los períodos reservados) no cambie de golpe.

**Relaciones con otros casos de uso**

  - **Relacionados:** COM-ANL-RSC · Dejar sin Efecto la Rescisión (vuelve atrás la rescisión mientras no llega la última entrega);
    PROD-PRR-SUM, que no pre-reserva los períodos posteriores a la rescisión; COM-MOD-SUM, que no se puede ejecutar sobre un contrato con
    rescisión acordada; COM-RSV-SUM, que puede resolver el contrato igual si mientras tanto se superan los incumplimientos tolerados.

**Precondiciones**

a. El actor está autenticado en el Sistema con rol Gerente.

b. Existe al menos un suministro «vigente» sin rescisión acordada.

c. La empresa y el cliente acordaron la rescisión fuera del Sistema.

**Garantías mínimas**

  - La rescisión se registra completa o no se registra: si falla o se cancela, el contrato queda como estaba.
  - Ningún período que ya cae dentro de la ventana de pre-reserva cambia: sus reservas, cosechas y entregas se conservan.
  - Lo ya entregado, cobrado o reclamado no cambia (la rescisión produce efectos solo para el futuro, art. 1076 del Código Civil y Comercial).

**Garantías de éxito (Postcondiciones)**

a. El suministro quedó con la rescisión acordada: motivo, descripción, fecha del acuerdo con el cliente, fecha del registro y fecha de la
   última entrega conservada. Sigue «vigente» hasta esa fecha.

b. Cada detalle vigente quedó con su fecha de fin en su último período dentro de la ventana de pre-reserva. Los períodos posteriores no se
   entregan ni se pre-reservan.

c. Si no quedó ningún período por entregar, el suministro pasó a «rescindido» y sus detalles vigentes a «finalizado» en la misma operación.

d. No se aplicó multa ni indemnización, y la cantidad de incumplimientos no cambió.

e. Se le envió al cliente por correo la constancia de la rescisión, con el motivo, la fecha del acuerdo y la fecha de la última entrega.

f. Se notificó al Vendedor del contrato.

g. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del contrato, los datos de la rescisión y la fecha de fin
   anterior y nueva de cada detalle.

**Escenario principal de éxito (o Flujo Básico)**

1.  El Gerente inicia la rescisión desde la ficha de un suministro vigente.
2.  El Sistema presenta el contrato y lo que pasará: los períodos que se conservan (los que ya están en la ventana de pre-reserva), con la
    fecha de la última entrega, y que los posteriores no se entregan; que no hay multa ni indemnización y que no cuenta como incumplimiento.
3.  El Gerente indica el motivo, la fecha del acuerdo con el cliente y, si corresponde, una descripción, y confirma que la rescisión se
    acordó con el cliente.
4.  El Sistema verifica los datos.
5.  El Gerente confirma.
6.  El Sistema vuelve a verificar que el contrato siga «vigente», sin rescisión acordada, y que los períodos que se conservan sean los
    mismos que presentó en el paso 2. En una única transacción registra la rescisión, fija la fecha de fin de cada detalle vigente y
    registra la auditoría.
7.  El Sistema envía al cliente la constancia de la rescisión y notifica al Vendedor.
8.  El Sistema informa al Gerente que la rescisión quedó registrada y hasta qué fecha se entrega.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 5, el Gerente cancela:**

1.  El Sistema descarta los datos sin registrar nada.

**\*b. En cualquier momento el Sistema falla:**

1.  El Sistema revierte cualquier registro parcial y, al restablecerse, informa que la rescisión no se registró.

**2a. No hay ningún período dentro de la ventana de pre-reserva:**

1.  El Sistema informa que el contrato queda rescindido en el momento de confirmar.
2.  El caso de uso continúa en el paso 3. En el paso 6 aplica la postcondición c.

**4a. Falta el motivo, el motivo es «otro» sin descripción, la fecha del acuerdo es posterior a la fecha actual o el Gerente no confirmó el
acuerdo con el cliente:**

1.  El Sistema señala el dato inválido y el Gerente lo corrige (vuelve al paso 3).

**6a. Desde el paso 2 un período entró en la ventana (por ejemplo, porque pasó la medianoche o corrió la pre-reserva):**

1.  El Sistema no registra nada, presenta otra vez los períodos que se conservan y vuelve al paso 2.

**6b. El contrato ya no está vigente, ya tiene una rescisión acordada o lo modificó otra operación:**

1.  El Sistema no registra nada, informa la situación actual y vuelve a la ficha del contrato.

**7a. El Sistema no logra enviar el correo al cliente:**

1.  La rescisión permanece registrada y la constancia queda pendiente de envío, para reenviarla desde la ficha.

**7b. El cliente no tiene correo registrado:**

1.  La rescisión permanece registrada y la constancia queda para imprimir desde la ficha.

**Requisitos especiales**

  - El paso 6 se ejecuta como una única transacción y se serializa con la pre-reserva diaria, COM-MOD-SUM, COM-RSV-SUM y otras operaciones
    sobre el mismo contrato.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - La constancia es interna y no tiene validez fiscal.
  - Los logs de auditoría son de solo inserción.

**Reglas de negocio**

  - **Rescisión por mutuo acuerdo:** las dos partes acuerdan dejar sin efecto el contrato. Produce efectos solo hacia el futuro: lo
    cumplido queda firme (art. 1076 del Código Civil y Comercial). El Gerente no puede rescindir un contrato sin el acuerdo del cliente: un
    contrato de suministro con plazo determinado no se rescinde por voluntad de una sola parte salvo que el contrato o la ley lo permitan
    (art. 1077), y el contrato del sistema no tiene esa cláusula. (Precondición c, paso 3)
  - **Quién rescinde:** el Gerente. (Actor principal)
  - **Períodos que se conservan:** los de los detalles vigentes con fecha igual o anterior a la fecha actual más los días de pre-reserva
    (los ya reservados, con cosecha o con entrega planificada). Funciona como el preaviso del contrato, igual que en COM-MOD-SUM («Desde
    cuándo rige un cambio»). La **fecha de la última entrega conservada** es la mayor de esas fechas que no es anterior a la fecha actual.
    (Pasos 2 y 6)
  - **Fecha de fin de cada detalle:** su último período dentro de la ventana; si no tiene ninguno, la fecha de fin de la ventana (el detalle
    queda sin períodos por delante). (Postcondición b)
  - **Motivo:** lista cerrada: «a pedido del cliente», «a pedido de la empresa» u «otro». La descripción es opcional, salvo con «otro», que
    la exige. (Paso 3)
  - **Fecha del acuerdo:** la del día en que la empresa y el cliente acordaron la rescisión; igual o anterior a la fecha actual. (Paso 3)
  - **Sin multa ni incumplimiento:** la rescisión no aplica la multa por resolución, no genera indemnización y no suma a la cantidad de
    incumplimientos. (Postcondición d)
  - **Mientras se entregan los períodos conservados** el contrato sigue «vigente»: se entregan, se confirman, se reclaman y se cobran como
    cualquier otro; no se puede modificar (COM-MOD-SUM) ni volver a rescindir; se puede dejar sin efecto (COM-ANL-RSC). Si en ese tiempo los
    incumplimientos superan los tolerados, COM-RSV-SUM lo resuelve igual, con su multa: la resolución por incumplimiento prevalece sobre la
    rescisión acordada.
  - **Cierre:** el día siguiente a la última entrega conservada, sin entregas del contrato pendientes de concretar, InfoPonia pasa el
    suministro a «rescindido», con fecha de rescisión igual a la de esa última entrega, y sus detalles vigentes a «finalizado». Lo hace la
    ejecución diaria.
  - **Constancia:** el cliente recibe por correo la constancia de la rescisión. No hay enlace de aceptación: el acuerdo se hizo fuera del
    Sistema y el Gerente lo registra (como en COM-MOD-SUM, regla «Comprobante»).

**Frecuencia:** rara.

**Temas abiertos**

  - Confirmar con el Jardín Botánico que conservar los períodos de la ventana de pre-reserva (14 días con la configuración actual) es
    aceptable como plazo de la rescisión.
  - La rescisión unilateral con preaviso, si algún día los contratos la incluyen como cláusula, queda como mejora futura.

## COM-ANL-RSC · Dejar sin Efecto la Rescisión

Caso de uso nuevo de alto nivel (versión 0.1, 21/11/2026), escrito por Claude en el lote C3 con la decisión del estudiante del 21/11/2026.
**Pendiente de pasar a Drive.**

**Actores:** Gerente.

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** volver atrás una rescisión acordada cuando el cliente y la empresa deciden seguir con el contrato.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Gerente.

b. El suministro está «vigente», con una rescisión acordada, y la fecha actual no es posterior a la fecha de la última entrega conservada.

**Postcondición:**

a. El suministro quedó sin rescisión acordada y cada detalle vigente sin fecha de fin: vuelven a regir todos sus períodos hasta la fecha de
   fin del contrato.

b. Los períodos que entraron en la ventana desde la rescisión quedan para la próxima pre-reserva diaria (PROD-PRR-SUM).

c. Se le envió al cliente por correo la constancia y se notificó al Vendedor del contrato.

d. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del contrato, el motivo y los datos de la rescisión que quedó
   sin efecto.

**Reglas:**

1.  Motivo obligatorio, en texto libre.
2.  Se verifica de nuevo, al confirmar, que el contrato siga «vigente» con la rescisión acordada y que no haya pasado la fecha de la última
    entrega conservada; si no, no se registra nada y se informa la situación actual.
3.  Se serializa con la pre-reserva diaria y con el cierre de la rescisión del mismo contrato.
4.  Si la constancia no se puede enviar, queda pendiente de envío o para imprimir, como en COM-RSC-SUM 7a y 7b.

## Cambios ya decididos que se aplican (PCU, secciones 6, 9 y 16; MD-116, MD-124, MD-131, MD-139)

1. **Incumplimientos tolerados de 0 a 99** (PCU 16, 21/11/2026), al pactar y al modificar; al modificar, **nunca menor** que los acumulados
   (igual se admite: el contrato se resuelve cuando los acumulados **superan** los tolerados, regla 5 de 8.11). Reemplaza «al menos uno» de
   la regla «Datos del contrato» de COM-PCT-SUM y «mayor que los acumulados» de COM-MOD-SUM 5e y su regla.
2. **Par (variedad, dirección) nuevo** (PCU 9; MD-131): al pactar y al agregar, los detalles finalizados no cuentan.
3. **9d de COM-PCT-SUM** nombra «Modificar Suministro, CU-38»: es COM-MOD-SUM.
4. **Estado de pago «en mora»** (MD-139): la regla 7 de COM-CNS-SUM dice «vencida»; se muestra «en mora» (cuando exista, COM-08).
5. **Un detalle finalizado no reserva períodos posteriores a su fecha de fin** (PCU 9; MD-131): lo cumple el calendario
   (`fecha_fin_detalle`), para PROD-PRR-SUM y PROD-ASG-STK.

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-57, D-61)

Archivos de servicios: `comercial/servicios/suministros.py` (pactar, modificar, consultar), `calendario.py` (fechas, meses, calendario y
precio por período, funciones puras), `pre_reserva.py` (PROD-PRR-SUM, en `docs/casos_de_uso/produccion/pre_reserva.md`) y
`comprobantes.py` (el mismo de COM-02, con la plantilla del suministro). El stock: `docs/patrones/stock_maduro.md`, sección 7.

### Fechas y precios (`calendario.py`, funciones puras con pruebas de tabla)

- `sumar_meses(fecha, n)`: el mismo día del mes, `n` meses después; si ese día no existe, el último del mes (31/01 + 1 = 28/02 o 29/02).
  Es la regla «Fecha de fin». **No** es `fecha + 30 × n` (el prototipo usa eso: «Lo que difiere», fila 2).
- `meses_transcurridos(desde, hasta)`: el mayor `n` tal que `sumar_meses(desde, n) <= hasta`. Con `desde` el 22/10: el 21/12 da 1 y el 22/12
  da 2 (el ejemplo de la regla «Precio de cada entrega»).
- `calendario(detalle, desde=None, hasta=None)`: las fechas `fecha_primer_entrega + k × periodo` hasta `fecha_fin_detalle` o la fecha de fin
  del contrato (la menor). Con `desde` y `hasta`, solo ese tramo, sin generar los anteriores (para el calendario de la ficha).
- `precio_en(detalle, fecha)`: la regla 7 de 8.11 con `fecha_base_ajuste` (`docs/modelo/comercial.md`). `Decimal`, `ROUND_HALF_UP` a 2
  decimales, siempre desde el inicial. Prueba con el ejemplo del caso de uso ($1.000, 3 %, cada 2 meses → 1.000 / 1.030 / 1.060,90).
- **`fecha_base_ajuste`** (decisión de aplicación, validada por el estudiante el 21/11/2026): la fecha de realización en los detalles de COM-PCT-SUM; la fecha de
  primera entrega en los creados por COM-MOD-SUM, tanto el **sucesor** (regla «Precio con ajuste periódico en el detalle nuevo», decisión
  M) como el **agregado** con 5b. El caso de uso dice «el detalle nuevo» sin distinguir; se aplica a los dos porque en los dos el precio
  inicial se pacta el día de la modificación.

### COM-PCT-SUM

- **Servicio.** `pactar_suministro(actor, datos) -> Suministro`, en `transaction.atomic()`. `datos` es `DatosDeSuministro` (vendedor,
  cliente, duración, tolerados, multa, plazo de pago, indemnización por atraso y la lista de `RenglonDeSuministro` con los datos del
  detalle, de su cláusula y `continuar_superpuesto`). Lectura sin escribir: `datos_del_formulario(actor, datos)` (fecha de fin, calendario y
  precios de cada detalle, períodos de la ventana con su disponible, advertencias 9d y 9f, errores por campo) y `resumen(actor, datos)`.
  Errores: `ValidationError` con `code` y campo, como COM-02.
- **La carga no se guarda** (pasos 2 a 13): vive en el formulario, como en COM-02. `datos_del_formulario` no bloquea y usa
  `stock_maduro.simular` para los períodos de la ventana (una consulta por tabla; `assertNumQueries` igual con 1 y con 4 detalles).
- **Paso 1 y 1a, precondición b:** igual que COM-REG-CVT (Vendedores activos con invernaderos activos; botón deshabilitado con su motivo).
  **Precondición c:** sin variedades activas, «Pactar suministro» deshabilitado con «No hay variedades activas.»
- **Pasos 3 y 3a, 4a:** el mismo buscador de clientes activos y el mismo enlace al alta con `volver` que COM-REG-CVT. `volver` lleva los
  datos de las secciones 1 y 2; los detalles no viajan (se avisa antes, como en COM-02).
- **4b (correo obligatorio, regla 18 de 8.20):** con un cliente sin correo, las secciones 2 y 3 quedan bloqueadas con «El cliente no tiene
  correo. Hace falta para el comprobante y para los enlaces de confirmación de cada entrega.» y el botón «Cargar el correo» (COM-MOD-CLT
  con `volver`). El servicio lo verifica de nuevo (`cliente_sin_correo`).
- **Pasos 5, 6 y 6a:** duración de 1 a 120 meses; tolerados de **0** a 99 (PCU 16); multa de 0 a 99.999.999,99; plazo de pago de 0 a 365 días;
  indemnización por atraso de 0 a 9.999.999,99. La fecha de fin se muestra al lado de la duración («Termina el dd/mm/aaaa»).
- **Paso 7:** las variedades **activas** (no solo las que tienen stock: el stock importa solo para los períodos de la ventana).
- **Pasos 8 y 9, 8a, 8b, 9a a 9f:**
  - dirección: solo las **activas** del cliente; «Agregar una dirección al cliente» (8a) abre COM-MOD-CLT con `volver`;
  - período: chips 7, 14 y 30 días más un campo libre (variación 8b);
  - 9a: primera entrega entre hoy y la fecha de fin (`fecha_fuera_de_rango`, «Entre el dd/mm/aaaa y el dd/mm/aaaa.»);
  - 9b: rangos de «Datos del detalle» y «Datos del precio»;
  - 9c: el formulario no ofrece el par repetido y el servicio lo rechaza (`par_repetido`, «El contrato ya tiene Lechuga Crespa para esa
    dirección: es el detalle 2.»);
  - **9d (superposición):** aviso con el código del otro contrato y su enlace, y la casilla «Continuar igual: es una renovación o un pedido
    con condiciones propias». Sin la casilla marcada el servicio rechaza (`superposicion_sin_confirmar`): «continuar es una decisión
    explícita» (regla «Suministro superpuesto»);
  - **9e:** por cada período de la ventana, su fecha, lo pedido y lo disponible después de los anteriores (`simular`). Si alguno no alcanza,
    error en el detalle («El 26/11 hay 120 plantas disponibles de Lechuga Crespa después de los períodos anteriores.») y no se puede seguir;
  - 9f: aviso «El precio no se ajustará durante el contrato: el primer ajuste sería el dd/mm/aaaa, después del fin.», sin bloquear;
  - **paso 9, calendario:** cantidad de entregas, total de plantas del contrato para el detalle y las fechas: las de la ventana marcadas
    «se reserva ahora» y, con ajuste periódico, cada tramo de precio («Desde el dd/mm: $ 1.030,00»). Si hay más de 12 fechas, las primeras
    12 y «y N más hasta el dd/mm/aaaa».
- **Pasos 10, 11, 11a y 11b:** cantidad mínima de 1 a la cantidad por período; tolerancia de 0 a 365 días; indemnizaciones de 0 a
  9.999.999,99. Los cuatro campos son obligatorios (el prototipo deja la tolerancia opcional: «Lo que difiere», fila 6).
- **7-11a y 12a:** quitar un detalle no pide confirmación; con ninguno, «El contrato tiene que tener al menos un detalle.»
- **Pasos 12, 13 y 13a:** ventana de resumen y confirmación, como COM-REG-CVT (el prototipo registra directo). 13a.1a, 13a.1b y 13a.1c los
  resuelve el recálculo: al cambiar el Vendedor se vuelve a simular la ventana; al cambiar el cliente se vacía la dirección de cada detalle;
  al cambiar la duración se recalculan la fecha de fin y el calendario.
- **Paso 14 (la transacción)**, en el orden de `docs/patrones/stock_maduro.md` (secciones 3 y 7):
  1. cuentas del actor y del Vendedor; rol y estado (`sin_permiso`, `vendedor_inactivo`);
  2. invernaderos activos del Vendedor (`bloquear_invernadero_activo`); al menos uno (`vendedor_sin_invernaderos`);
  3. el cliente: activo y con correo (`cliente_inactivo`, `cliente_sin_correo`); cada dirección, activa y suya (`direccion_no_valida`);
  4. las variedades (activas: `variedad_inactiva`) y, si algún período cae en la ventana, los lotes y las partidas candidatos;
  5. crea el `Suministro` («vigente», `fecha_realizacion` = hoy, `fecha_fin`, `numero` de `comercial_suministro_numero_seq`), su
     `ClausulaSuministrado`, cada `DetalleSuministro` («vigente», `fecha_base_ajuste` = hoy) con su `ClausulaSuministrante`;
  6. reserva los períodos de la ventana en el orden de la sección 7 del patrón, con `asignar(actor, Periodo(detalle, fecha), cantidad, fecha,
     "suministro")`;
  7. si alguno queda sin cubrir: `stock_insuficiente` con la cantidad disponible de cada detalle y período (14a); se revierte todo;
  8. audita y devuelve el suministro.
- **Postcondición f (planificar la entrega de un período que salió todo de cámara): se completa en COM-05**, igual que la g de COM-REG-CVT
  (el paso diario 50 la toma; `docs/disparadores.md`, «Cuando exista Entrega», punto 4).
- **Paso 15 y 15a (comprobante):** `enviar_comprobante(suministro)` después de confirmar, fuera de la transacción, con `estado_comprobante`
  y «Reenviar comprobante» en la ficha (como COM-02: sin reintento automático). Contenido (variación 15a): cliente, Vendedor, duración y
  vigencia, tolerados, multa, cláusula del suministrado y, por detalle, variedad, dirección, cantidad, período, **calendario** (primera y
  última fecha, cantidad de entregas y, con ajuste, los tramos de precio; no la lista de todas las fechas, que puede pasar de 500;
  validado por el estudiante el 21/11/2026),
  precio y mecanismo y su cláusula del suministrante. Pie: «Comprobante interno, sin validez fiscal.»
- **Paso 16:** a la ficha con el aviso breve «SUM-0013 pactado. Se reservaron N períodos{ y se programaron M cosechas}.» más lo del
  comprobante.
- **Auditoría (postcondiciones h e i, D-36):** un registro, acción nueva `pacto_suministro`, con el actor y su rol; afectados: el suministro
  (principal), su cláusula, los detalles con sus cláusulas y lo que devolvió cada `asignar` (reservas, líneas y cosechas).
- **Concurrencia** (`@tag("concurrencia")`): un pacto y una compra-venta por el último stock de un lote; un pacto contra la baja del cliente;
  dos pactos del mismo cliente con el mismo par (los dos se registran: la superposición entre contratos no se bloquea).

### COM-MOD-SUM

- **Servicio.** `modificar_suministro(actor, suministro_id, cambios, huella) -> Suministro`. `cambios` es `CambiosDeSuministro` (datos del
  contrato que cambian, Vendedor, y por detalle vigente: `sin_cambios`, `modificar` con las condiciones nuevas y la fecha desde la que rige,
  o `terminar`; y los detalles nuevos). Lectura: `datos_de_modificacion(actor, suministro_id, cambios)` (fecha desde la que rige cada
  cambio, períodos que se conservan y nuevos, simulación de la ventana de los detalles nuevos, errores) y `resumen_de_modificacion`.
- **Precondición nueva (COM-RSC-SUM):** un suministro con rescisión acordada no se modifica (`rescision_acordada`); en la ficha,
  «Modificar suministro» no aparece mientras dure.
- **`huella` (10b).** Un texto que resume el estado del contrato al abrir la pantalla: estado, duración, tolerados, acumulados, multa,
  cláusula del suministrado, Vendedor, los id de los detalles vigentes y los datos de la rescisión (si tiene). La misma `huella` usan
  COM-RSC-SUM (6b) y COM-ANL-RSC. Lo arma `huella_de(suministro)`; el formulario lo lleva oculto. Si al
  confirmar no coincide: `contrato_cambio` («El contrato cambió mientras lo modificabas (por ejemplo, se resolvió o lo modificó otra
  persona). Volvé a abrirlo.») y vuelve a la lista (paso 2). No hace falta una columna de versión.
- **Pasos 2 y 3, 1a:** la lista de suministros vigentes en el alcance (el Vendedor, los suyos; el Gerente, todos). En la pantalla, se entra
  desde la ficha con «Modificar suministro» (el prototipo no tiene una lista aparte: la de Contratos filtrada por «Vigente» es el paso 2).
- **Paso 4, «desde cuándo rige»:** `rige_desde(detalle, hoy)` = el primer período del calendario **posterior** a `hoy + días de
  pre-reserva`. Sin ninguno (el detalle termina dentro de la ventana), «Modificar» y «Terminar» quedan deshabilitados para ese detalle:
  «Todos sus períodos ya están dentro de la ventana de pre-reserva.» El historial de condiciones es el mismo de la ficha (`MODALS.sumhist`).
- **Pasos 5 y 6, 5a, 6a (modificar un detalle):**
  - se puede cambiar la cantidad, el período, el precio inicial, **el mecanismo con su porcentaje y sus meses** y los cuatro datos de la
    cláusula del suministrante (decisión I; el prototipo no deja cambiar el mecanismo ni la tolerancia: «Lo que difiere», fila 8). Variedad y
    dirección no: para cambiarlas se termina el detalle y se agrega otro;
  - **5a:** «Rige desde» es un desplegable con los períodos posteriores a la ventana (por defecto, el primero);
  - el precio inicial del sucesor viene propuesto con el precio que tendría el detalle actual en la fecha desde la que rige (con ajuste,
    el ajustado), para no bajarlo sin querer;
  - un detalle marcado «Modificar» sin ningún dato distinto: «Cambiá al menos un dato o elegí "Sin cambios".» (7a para ese detalle);
  - al confirmar: el detalle pasa a «finalizado» con `fecha_fin_detalle` = su último período **anterior** a la fecha desde la que rige (la
    regla «Detalle sucesor» dice «el último período conservado»; la postcondición a dice «el último dentro de la ventana», que es lo mismo
    salvo con 5a: manda la regla). Si no tiene ninguno, `fecha_fin_detalle` = el día anterior a la fecha desde la que rige. El sucesor:
    «vigente», misma variedad y dirección, `reemplaza_a` = el anterior, `fecha_primer_entrega` = la fecha desde la que rige,
    `fecha_base_ajuste` = esa misma fecha, y su cláusula nueva. Las reservas siguen con el detalle anterior.
- **5b (agregar un detalle):** el mismo formulario de detalle de COM-PCT-SUM (`detForm`), con sus reglas, 9c contra los detalles vigentes
  (rechaza y propone «Modificar» ese detalle) y 9d contra otros contratos (advierte, con la casilla). Si tiene períodos en la ventana: se
  simulan (acumulado por variedad con los demás detalles nuevos) y se reservan en el paso 10 con `asignar` (el único caso en que COM-MOD-SUM
  toma stock).
- **5c (terminar un detalle):** pasa a «finalizado» con `fecha_fin_detalle` = su último período dentro de la ventana (o el día de hoy más los
  días de pre-reserva, si no tiene ninguno). El aviso: «Se entrega por última vez el dd/mm/aaaa. Sin multa: es de mutuo acuerdo.»
  **5c.1a:** si no queda ningún otro detalle vigente (ni nuevo), aviso «Equivale a terminar el contrato. Si es por acuerdo con el
  cliente, el Gerente puede rescindirlo desde la ficha (sin multa).» con el botón «Acortar la duración hasta el dd/mm/aaaa», que pone la
  duración mínima en meses que todavía incluye ese período. El Vendedor puede no acortarla.
- **5d (duración):** extender recalcula `fecha_fin` y muestra cuántos períodos suma cada detalle vigente. Acortar: la nueva fecha de fin no
  puede ser anterior al último período dentro de la ventana de **cualquier** detalle (vigente o finalizado), porque esos ya están
  reservados (`fin_anterior_a_la_ventana`, «La fecha de fin más cercana posible es el dd/mm/aaaa.»). Un detalle vigente que con la nueva
  fecha de fin se queda sin períodos posteriores a la ventana **pasa a «finalizado»** con `fecha_fin_detalle` = su último período (decisión
  de aplicación, validada por el estudiante el 21/11/2026: si no, quedaría «vigente» sin nada que entregar); el resumen lo muestra.
- **Estado del contrato al terminar todo:** si después de confirmar ningún detalle queda vigente y ninguno tiene períodos desde hoy, el
  contrato pasa a «finalizado» en la misma transacción (regla 5 de 8.11: «el Suministro, cuando todos sus detalles están finalizados»). Si
  todavía tiene períodos por entregar, sigue «vigente» y **se completa en COM-06**, que finaliza el detalle y el contrato al concretar la
  entrega del último período (disparador nuevo).
- **5e:** tolerados de 0 a 99 y nunca menores que los acumulados (PCU 16): `tolerados_menores_que_acumulados`, «No puede ser menor que los
  2 incumplimientos ya acumulados.»
- **5f:** se actualiza la `ClausulaSuministrado`; aviso «Rige para las entregas que se concreten desde hoy. Las ya concretadas conservan su
  vencimiento.»
- **5g:** cliente y fecha de realización se muestran como texto, con «No se modifican: para otro cliente o desde otra fecha, pactá un
  suministro nuevo.»
- **1a.2 (Vendedor):** solo el Gerente; un Vendedor activo con al menos un invernadero activo (como en el alta: si no, los períodos siguientes
  no tendrían de dónde salir). Lo ya reservado no se mueve (D-60, punto 3).
- **Pasos 7 a 9:** el panel «Cambios» a la derecha (como el prototipo) y, al guardar, la ventana de resumen con cada cambio y la fecha desde la
  que rige, y «Confirmar cambios» (el prototipo guarda directo).
- **Paso 10, 10a y 10b (la transacción):** cuentas → si hay detalles nuevos con períodos en la ventana, invernaderos, cliente, variedades,
  lotes y partidas → el `Suministro` y sus detalles vigentes (`FOR NO KEY UPDATE`). Después: `huella` (10b); el contrato sigue «vigente»
  (10b); cada «rige desde» del formulario es igual al que se calcula con `hoy` (10a: `ventana_cambio`, «Desde que abriste la pantalla, un
  período entró en la ventana. Revisá las fechas nuevas.», y vuelve al resumen con las fechas recalculadas). Luego aplica los cambios y,
  para los detalles nuevos, reserva; si no alcanza, `stock_insuficiente` y se revierte todo.
- **Paso 11, 11a:** comprobante del contrato modificado, con cada cambio y desde cuándo rige; `estado_comprobante` y «Reenviar», como al
  pactar.
- **Postcondición i (notificaciones):** si actuó el Gerente, al Vendedor («El Gerente modificó SUM-0013: …»); si cambió el Vendedor, al
  anterior («SUM-0013 pasó a {nuevo}.») y al nuevo («Quedó a cargo de SUM-0013, de {cliente}.»). Dentro de la transacción (D-42).
- **Auditoría (postcondición j):** un registro, acción nueva `modificacion_suministro`, con `cambios` (campo: anterior y nuevo) y entre los
  afectados el suministro, los detalles finalizados y creados, sus cláusulas y lo que reservó `asignar`.
- **Concurrencia:** una modificación contra la pre-reserva del mismo contrato (se ponen en fila por el `Suministro`); dos modificaciones del
  mismo contrato (la segunda recibe `contrato_cambio`).

### COM-CNS-SUM

- **Lectura:** `buscar_suministros(actor, filtros, pagina)` y `ficha_de_suministro(actor, id)`, sin consultas por fila. Alcance con
  `en_alcance_de` (D-28); fuera del alcance, 403 con mensaje.
- **Reglas 2 y 3 (lista):** filtros cliente, estado (con «rescindido», COM-RSC-SUM), rango de fechas («de realización» o «de fin») y Vendedor (solo el Gerente), en la URL.
  Columnas del prototipo (`tabContratos`, rama `sum`): suministro (código y, para el Gerente, el Vendedor), cliente, vigencia (realización
  al fin, y la duración), detalles vigentes, incumplimientos «N de M» con la marca «Al límite» (regla 9) y estado. Orden: fecha de
  realización descendente. Desde COM-03, la pestaña «Contratos» tiene el selector «Compra-ventas / Suministros» (`ctrSel`).
- **Regla 4 (contrato):** duración y vigencia, tolerados y acumulados, multa, cláusula del suministrado, fecha de resolución si la tiene, y el
  estado del comprobante con «Ver comprobante» y «Reenviar».
- **Regla 5 (detalles):** una línea por cadena «reemplaza a» (el último detalle de cada una), con el precio vigente hoy (`precio_en(detalle,
  hoy)`), la cláusula del suministrante, el estado y «Con cambios desde el dd/mm» si tiene anteriores; «Ver historial de cambios» abre la
  ventana con cada tramo (`MODALS.sumhist`).
- **Regla 6 (calendario):** por defecto, los períodos de los últimos 30 días hasta 28 días después del fin de la ventana, con «Ver todo el
  calendario» (todos, de a 100). Situación de cada período en COM-03: «Fuera de la ventana», «Reservado» (sin cantidad sin cubrir),
  «Sin cobertura completa · faltan N» (con alerta activa o con cantidad sin cubrir), «Pasado» (todavía no hay entregas). **Se completan
  después:** «Entrega planificada» (COM-05), «Entregado» y «Con faltante» (COM-06 y COM-07).
- **Reglas 7 y 8 (entregas y solicitudes): se completan en** COM-05/COM-06 y COM-07a (la sección «Solicitudes de revisión»:
  `docs/casos_de_uso/comercial/solicitudes.md`, «Lo que completa a otras tareas»). Hasta entonces esas secciones no se muestran (D-25).
- **Regla 9:** con un incumplimiento restante, «Al contrato le queda un incumplimiento tolerado.»; con los tolerados ya usados, «El contrato
  ya usó sus N incumplimientos tolerados: el próximo lo resuelve y se aplica la multa.» (textos del prototipo).
- **Rescisión en la ficha y en la lista:** con rescisión acordada, el aviso «Rescisión acordada el dd/mm (motivo). Se entrega hasta el
  dd/mm…» y, en la lista, la marca «Rescisión acordada»; rescindido, el aviso «Rescindido por mutuo acuerdo el dd/mm…». Los períodos
  posteriores a la rescisión no aparecen en el calendario.
- **Regla 10:** «Modificar suministro» si está vigente, sin rescisión acordada, y el actor es su Vendedor o el Gerente. «Rescindir
  suministro» (Gerente, vigente sin rescisión) y «Dejar sin efecto la rescisión» (Gerente, con rescisión acordada). «Registrar cobro» (COM-08) y la consulta de
  una solicitud (COM-07a): **se completan en** esas tareas. La resolución en la ficha y «Dar por atendida»: COM-07b (`resolucion.md`).

### COM-RSC-SUM y COM-ANL-RSC (rescisión por mutuo acuerdo)

- **Servicios** (`comercial/servicios/suministros.py`): `datos_de_rescision(actor, suministro_id)` (lectura: períodos que se conservan,
  fecha de la última entrega, `huella`), `rescindir_suministro(actor, suministro_id, datos, huella, conservados)`,
  `dejar_sin_efecto_rescision(actor, suministro_id, motivo)` y `cerrar_rescisiones(hoy)` (paso diario).
- **Solo el Gerente** (`rol_requerido("gerente")` en las vistas y `sin_permiso` en el servicio).
- **Paso 2:** `periodos_conservados(suministro, hoy)` = los del calendario de cada detalle vigente con `fecha <= ventana(hoy)` y no anteriores a
  hoy; la última entrega es la mayor. Se muestran agrupados por detalle, con su fecha y su situación («Reservado», «Sin cobertura completa»).
- **Paso 3 y 4a:** `motivo_rescision` (`a_pedido_del_cliente`, `a_pedido_de_la_empresa`, `otro`), `descripcion_rescision` (obligatoria con
  `otro`: `descripcion_obligatoria`), `fecha_acuerdo_rescision` (`<= hoy`: `fecha_futura`) y la casilla «Confirmo que la rescisión se
  acordó con el cliente» (`acuerdo_sin_confirmar`). Es la regla «Rescisión por mutuo acuerdo» hecha pantalla: el sistema no deja registrar
  una rescisión unilateral.
- **Paso 6, 6a y 6b (la transacción):** cuentas → el `Suministro` y sus detalles (`FOR NO KEY UPDATE`; no toma stock: no bloquea
  invernaderos ni lotes, `docs/patrones/bloqueos.md`, sección `comercial`). Verifica `huella` (6b: `contrato_cambio`), estado «vigente» y sin
  rescisión (6b), y que `conservados` (las fechas que vio el Gerente) sea igual a `periodos_conservados(suministro, hoy)` (6a:
  `ventana_cambio`). Luego carga los datos de la rescisión y `fecha_fin_detalle` de cada detalle vigente (regla «Fecha de fin de cada
  detalle»). **2a:** sin períodos conservados, en la misma transacción pasa a «rescindido» (`fecha_rescision` = hoy) y los detalles a
  «finalizado».
- **Invariante** (prueba en `verificar_invariantes_de_reservas`): un detalle vigente de un suministro **sin** rescisión acordada no tiene
  `fecha_fin_detalle`; con rescisión, sí. Así `dejar_sin_efecto_rescision` vuelve a poner `fecha_fin_detalle = None` sin guardar el valor
  anterior.
- **Paso 7, 7a y 7b:** `enviar_comprobante(suministro, tipo="rescision")` fuera de la transacción, con `estado_comprobante` y «Reenviar»
  (como al pactar). Notificación al Vendedor: «El Gerente registró la rescisión de SUM-0013 ({cliente}) por mutuo acuerdo. Se entrega hasta
  el dd/mm/aaaa.»
- **Auditoría:** acciones nuevas `rescision_suministro` y `anulacion_rescision`, con el actor; `cierre_rescision`, sin usuario (InfoPonia,
  D-27). Afectados: el suministro (principal) y sus detalles, con la fecha de fin anterior y nueva.
- **Mientras dura** (regla «Mientras se entregan…»): `modificar_suministro` rechaza un contrato con rescisión acordada
  (`rescision_acordada`, «Tiene una rescisión acordada: dejala sin efecto para modificarlo.»); la pre-reserva no toma los períodos
  posteriores porque el calendario corta en `fecha_fin_detalle`. **Se completa en COM-07b:** COM-RSV-SUM puede resolver el contrato igual
  (`docs/casos_de_uso/comercial/resolucion.md`, paso 4.5).
- **COM-ANL-RSC:** regla 2 con el mismo bloqueo y `fecha_ultima_entrega_rescision >= hoy` (`rescision_cerrada`). Limpia los datos de la
  rescisión (quedan en la auditoría) y `fecha_fin_detalle` de los detalles vigentes. No pre-reserva en el momento: lo hace la próxima
  ejecución diaria (postcondición b); el aviso de la ventana lo dice. Constancia y notificación como en COM-RSC-SUM.
- **Cierre (paso diario 35, `cerrar_rescisiones`)**, registrado en `ComercialConfig.ready()` con
  `registrar_paso_diario("cerrar_rescisiones", "Cerrar rescisiones de suministros", 35, cerrar_rescisiones)` (D-56, punto 6: los órdenes van
  de 10 en 10 para poder intercalar). Toma los suministros «vigentes» con rescisión acordada y `fecha_ultima_entrega_rescision < hoy`; cada
  uno, en su transacción: «rescindido», `fecha_rescision` = la última entrega conservada, detalles vigentes a «finalizado», auditoría
  `cierre_rescision`. Idempotente. **Se completa en COM-05 y COM-06:** el cierre espera que no queden entregas del contrato a realizar.
  `core/procesos.py`: COM-03 actualiza la tabla de órdenes del comentario (35 en `comercial`; 20 también en `comercial`, D-59).

### Lo que completa a COM-01, COM-02 y otras apps

- Clientes (`docs/disparadores.md`, «Completan el ABM de cliente», punto 2): `direcciones_en_uso` cuenta los detalles de suministro (en
  cualquier estado); `impide_quitar_el_correo` mira los suministros vigentes; `pendientes_del_cliente` y la ficha suman los suministros
  vigentes; `volver` regresa a «Pactar suministro» y a «Modificar suministro».
- Baja de variedad: `contratos_abiertos` suma los detalles de suministro vigentes de esa variedad («Tiene contratos abiertos: N compra-ventas
  y M suministros.»).
- Traspaso de Vendedor (D-60): `contar` y `traspasar` suman los suministros vigentes con la regla de D-60, punto 2 («atado a este
  invernadero» = todas sus reservas no liberadas son de este invernadero, con al menos una).

## Pantallas

Prototipo `docs/prototipos/comercial/`: `tabContratos` (rama `sum`) y `ctrSel`; `INIT.sumnew`, `VIEWS.sumnew`, `detForm` y `detErr` (la
**segunda** definición, desde la línea 1561, reemplaza a la primera), `ACT['sumnew-ok']`; `VIEWS.sum` (segunda definición),
`MODALS.sumhist`, `versiones`, `ultimas`; `INIT.summod`, `VIEWS.summod` (segunda), `contratoErr` (con su reemplazo «Incumplimientos
tolerados: se admite 0»), `chgDiff`, `rigeDesde`, `periodos`, `precioHoy`, `ACT['summod-ok']`; y la rescisión (bloque «Revisión del 21/11/2026 (5)», al
final del archivo): `rscConserva`, `MODALS.sumrsc`, `ACT['sumrsc-ok']`, `MODALS.sumrscanl`, `ACT['sumrscanl-ok']` y los reemplazos de
`VIEWS.sum` y `tabContratos`. Referencia (L7, D-61): manda el caso de
uso, y lo que falte o esté mal como interfaz se corrige.

URLs: `contratos/?tipo=suministro`, `contratos/suministros/nuevo/` (con `calcular/` y `revisar/`), `contratos/suministros/<id>/`,
`contratos/suministros/<id>/modificar/` (con `calcular/` y `revisar/`), `contratos/suministros/<id>/comprobante/`,
`contratos/suministros/<id>/reenviar-comprobante/`, `contratos/suministros/<id>/calendario/` (el calendario completo),
`contratos/suministros/<id>/rescindir/` y `contratos/suministros/<id>/dejar-sin-efecto-rescision/` (ventanas, con su página sin JavaScript).

Textos explicativos:

- bajo «Incumplimientos tolerados»: «Cuántos incumplimientos acepta el contrato. Al superarlos, se resuelve. Con 0, el primero lo resuelve.»;
- bajo «Primera entrega»: «Desde hoy y hasta el fin del contrato. Las entregas que caen en los próximos N días se reservan al pactar.»;
- en la sección Detalles: «Cada variedad va una vez por dirección. El calendario y el precio de cada entrega se calculan solos.»;
- en Modificar, sección Detalles: «Los cambios rigen desde el primer período posterior al dd/mm/aaaa. Lo ya reservado, cosechado o entregado
  no cambia.» (del prototipo).

### Lo que difiere del prototipo

| N.º | Prototipo | Se hace | Por qué |
|---|---|---|---|
| 1 | Registra y modifica sin resumen | Ventana de resumen y confirmación | Pasos 12 y 13 de PCT; 8 y 9 de MOD |
| 2 | Fecha de fin = hoy + 30 × meses | `sumar_meses` | Regla «Fecha de fin» |
| 3 | Duración «De 1 a 36 meses» en la ayuda | De 1 a 120 | Regla «Datos del contrato» (el reemplazo del prototipo ya dice 120) |
| 4 | Precio vigente con meses = días / 30 desde la primera entrega | `meses_transcurridos` desde `fecha_base_ajuste` | Regla «Precio de cada entrega»; decisión M |
| 5 | Sin verificación de stock de la ventana, sin aviso de superposición ni de ajuste sin efecto | 9d, 9e y 9f | COM-PCT-SUM |
| 6 | Tolerancia de entrega opcional; plazo de pago desde 1 | Obligatoria, de 0 a 365; plazo de pago desde 0 | Reglas «Cláusula del suministrante» y «Cláusula del suministrado» |
| 7 | Calendario: solo la cantidad de entregas | Fechas, tramos de precio y períodos de la ventana | Paso 9 y 8b |
| 8 | Modificar: no cambia el mecanismo ni la tolerancia, ni elige desde qué período rige | Los tres | Postcondición a (decisión I) y 5a |
| 9 | Terminar el último detalle: sin aviso | 5c.1a con «Acortar la duración» | COM-MOD-SUM |
| 10 | Correo del cliente: aviso, pero deja seguir | Bloquea hasta cargarlo, con el enlace | 4b |
| 11 | Calendario de la ficha con un tramo fijo | El mismo tramo por defecto y «Ver todo el calendario» | Regla 6 de COM-CNS-SUM («pasados y futuros») |
| 12 | «Registrar cobro» y solicitudes en la ficha | Llegan con COM-08 y COM-07a | D-25 |
| 13 | Rescindir: la rescisión se cierra en el momento si no hay períodos; el cierre posterior no se ve | El paso diario 35 la cierra | Regla «Cierre» de COM-RSC-SUM |

## Para más adelante

- COM-04: los lotes excluidos al cancelar una cosecha de un período; la reserva de cámara de períodos (PROD-ASG-CAM, MD-127: solo los de
  la ventana); «Con faltante».
- COM-05: postcondición f de COM-PCT-SUM; «Entrega planificada» en el calendario; la sección de entregas.
- COM-06: el detalle y el contrato pasan a «finalizado» al concretarse la entrega del último período; «Entregado»; el vencimiento del pago
  (MD-132).
- COM-05 y COM-06: el cierre de una rescisión espera las entregas del contrato a realizar.
- COM-07a: solicitudes de revisión e incumplimientos (`solicitudes.md`). COM-07b: la resolución (`fecha_resolucion_suministro`, alerta
  «suministro resuelto» con T-02, «Dar por atendida»); la resolución de un contrato con rescisión acordada (prevalece la resolución;
  `resolucion.md`).
- COM-08: «Registrar cobro» y el estado de pago («en mora», MD-139).

## Solo prototipo

Los de `docs/prototipos/comercial/README.md`, «Elementos del prototipo que no van en el sistema». En estas pantallas, además: los datos de
ejemplo (`DB.sum`, `SUM-0010` a `SUM-0012`), los identificadores armados a mano (`'SUM-0013'`, `nid()`), el caso fijo de la situación
«Sin cobertura completa» (`DS-22` del 24/11) y el aviso «se envió el comprobante» sin verificar el envío.
