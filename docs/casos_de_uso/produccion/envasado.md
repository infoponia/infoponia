# Casos de uso · produccion · Envasado

Copia para el repo de **PROD-PNF-ENV · Planificar Envasado, versión 0.2** (documento de Drive «CU · PROD-PNF-ENV · Planificar Envasado (v0.2)»,
carpeta «InfoPonia · Comercial · Análisis», 20/11/2026; la versión 0.1 está en «CU extendidos»). Cotejado con pendientes_CU, con «PCU ·
Cambios para pendientes_CU (comercial)» (secciones 1 y 9), con el modelo de dominio (reglas 8 de 8.4; 2 a 4 de 8.22; 18 a 25 de 8.8; 1 y 2 de
8.23; ronda 22) y con MD-87, MD-95 y MD-118.

**El código va en la app `comercial`** (D-59, A3: el caso de uso cambia una entrega, que es de `comercial`): `comercial/servicios/envasado.py`.
Las reservas de insumo se crean y cambian con el núcleo de `produccion` (`produccion/servicios/reservas.py`, `docs/api/produccion.md`,
sección 9) y lo disponible lo da `inventario` (`stock.disponible_para_planificar`, `docs/api/stock.md`). Cómo se guarda: **D-66** (puntos 8 y
13). Tarea: **COM-05a2**. Archivos de pruebas: `comercial/tests/test_prod_pnf_env.py` (`ProdPnfEnvServicioTests`),
`test_envasado_concurrencia.py` y `test_envasado_vistas.py`.

Si este archivo y sus fuentes no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: PROD-PNF-ENV no numera sus reglas (`test_disponible_al_modificar_…`), sus postcondiciones son `test_post_<letra>_…`
y sus extensiones `test_ext_<numero>_…` (`test_ext_10b_…`).

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-PNF-ENV | Planificar Envasado (con la modificación) | Agrónomo del invernadero de origen | `comercial/tests/test_prod_pnf_env.py` |

## PROD-PNF-ENV · Planificar Envasado

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Producción / Comercial.

**Actor principal:** Agrónomo del invernadero de origen de la entrega.

**Versión:** 0.2

**Personal involucrado e intereses**

  - **Agrónomo:** quiere reservar a tiempo los envases que necesita cada entrega, con datos reales del depósito, y poder corregirlos si la entrega cambia o no se pudo realizar.
  - **Transportista:** quiere salir con el producto ya envasado y encontrar, al concretar, los envases planificados con su cantidad, para confirmarlos rápido.
  - **Vendedor:** quiere que el producto de sus contratos llegue al cliente bien presentado y sin demoras por falta de envases.
  - **Gerente:** quiere que ningún envase se comprometa dos veces ni por encima de lo que hay, y que cada reserva quede registrada con su responsable.
  - **Organización (Jardín Botánico):** quiere que el costo de los envases se impute a las entregas que los usan y que no se usen envases vencidos.

**Relaciones con otros casos de uso**

  - No incluye («include») otros casos de uso ni es extendido («extend») por ellos.
  - **Lo precede:** COM-PNF-ENT · Planificar Entrega, que notifica al Agrónomo del invernadero de origen que debe planificar el envasado de cada entrega (postcondición h de COM-PNF-ENT; regla 18 de 8.8).
  - **Lo sigue:** COM-CNC-ENT · Concretar Entrega, donde se confirman las cantidades utilizada y devuelta de cada envase reservado y se registra su consumo.
  - **Relacionados, sin inclusión:**
      - CMP-AJT-STK · Ajustar Stock de Insumo y CMP-RLZ-PED · Realizar Pedido, cuando lo disponible de un envase no alcanza (extensión 6b);
      - CMP-HAB-IIN · Habilitar Insumo en Invernadero, cuando el envase que se necesita no está habilitado en el invernadero de origen (extensión 4a);
      - Cancelar Orden (CU-11), que al cancelar la entrega cancela sus reservas de insumo.

**Precondiciones**

a. El Agrónomo está autenticado en el Sistema.

b. El Agrónomo tiene a su cargo al menos un invernadero en estado «activo».

**Garantías mínimas**

  - La operación es atómica. Si el caso de uso se cancela o falla, no se registra ninguna reserva de insumo nueva, ningún cambio en las reservas existentes ni ningún log de auditoría parcial.
  - El stock actual de los envases, sus lotes de insumo y la contabilidad no se modifican, cualquiera sea la forma en que termine el caso de uso: no se registran consumos, movimientos de insumo ni asientos.
  - Ningún envase queda reservado por encima de lo disponible para planificar, aun cuando se planifiquen al mismo tiempo otras órdenes sobre el mismo invernadero.
  - No cambia el envasado de una entrega concretada, cancelada o en curso.
  - Una entrega tiene, como máximo, una reserva de insumo «activa» por cada envase.

**Garantías de éxito (Postcondiciones)**

a. Por cada envase nuevo, se creó una reserva de insumo en estado «activa», con:

  - la cantidad reservada indicada;
  - la fecha de reserva igual a la fecha actual;
  - la cantidad utilizada y la cantidad devuelta vacías hasta que la entrega se concrete.

La reserva es parte de la entrega y está asociada al insumo del envase en el invernadero de origen de la entrega.

b. Si la entrega ya tenía envasado planificado, cada reserva cuyo envase cambió de cantidad quedó con la nueva cantidad reservada y conservó su fecha de reserva, y cada reserva de un envase quitado pasó a «cancelada».

c. El stock libre de cada envase en el invernadero de origen bajó en lo que se reservó de más y subió en lo que se liberó. El stock actual y los lotes de insumo no cambiaron.

d. La entrega conservó su estado, su fecha programada, su transportista, sus detalles y su planificador (InfoPonia). Mientras tenga reservas de insumo, COM-PNF-ENT no le agrega líneas de otro período de suministro (regla «Agrupamiento en un suministro» de COM-PNF-ENT).

e. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador de cada reserva de insumo creada.

f. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de valor (cantidad reservada o estado) de cada reserva de insumo modificada.

**Escenario principal de éxito (o Flujo Básico)**

(La entrega todavía no tiene envasado planificado, sale en la fecha programada y el depósito tiene envases suficientes.)

1.  **El Agrónomo inicia la planificación del envasado de una entrega.**
2.  **El Sistema presenta las entregas «a realizar» cuyo invernadero de origen está a su cargo, ordenadas por fecha programada. Para cada una indica el invernadero de origen, el cliente, la modalidad (envío o retiro), la fecha programada y si ya tiene envasado planificado.**
3.  **El Agrónomo selecciona una entrega.**
4.  **El Sistema presenta el detalle de la entrega y los envases del invernadero de origen:**
    1.  **el cliente, el destino, la fecha programada y, si lo tiene, el transportista;**
    2.  **por cada línea, la variedad y la cantidad planificada, y el peso total de la entrega;**
    3.  **los envases habilitados y activos del invernadero, con lo disponible para planificar de cada uno y su unidad de medida.**
5.  **El Agrónomo indica un envase y la cantidad a reservar.**
6.  **El Sistema verifica la cantidad y presenta el envase agregado, con lo disponible que le queda.**

\*El Agrónomo repite los pasos 5-6 por cada envase que quiera reservar.\*

7.  **El Agrónomo termina la carga de envases.**
8.  **El Sistema verifica que haya al menos un envase y presenta el resumen: la entrega (cliente, fecha programada y modalidad) y, por cada envase, la cantidad a reservar y lo disponible que le queda.**
9.  **El Agrónomo confirma el envasado.**
10. **El Sistema verifica que la entrega siga «a realizar» y no esté en curso, que sus reservas de insumo no hayan cambiado y que lo disponible de cada envase siga cubriendo la cantidad indicada. Luego, en una única transacción, registra las reservas de insumo y la auditoría correspondiente.**
11. **El Sistema informa al Agrónomo que el envasado de la entrega quedó planificado.**

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento antes del paso 9, el Agrónomo cancela la planificación:**

1.  El Sistema descarta los datos ingresados sin registrar ningún cambio.

**\*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:**

1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que el envasado no se registró.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.

**1a. El Agrónomo inicia la planificación desde la notificación de COM-PNF-ENT o desde la entrega:**

1.  El Sistema omite los pasos 2 y 3 y presenta el paso 4 con esa entrega elegida.
2.  El caso de uso continúa en el paso 4, con las extensiones 3a y 3b si corresponden.

**2a. No hay entregas «a realizar» con origen en los invernaderos a cargo del Agrónomo:**

1.  El Sistema informa que no hay entregas para envasar.
2.  El caso de uso termina.

**3a. La entrega ya tiene envasado planificado (modificación):**

1.  En el paso 4, el Sistema presenta además los envases ya reservados, con su cantidad reservada. Para cada uno, lo disponible para planificar incluye su propia cantidad reservada.
2.  El Agrónomo cambia la cantidad de un envase reservado, lo quita o agrega un envase nuevo (paso 5).
3.  El caso de uso continúa en el paso 6. En el paso 8, el resumen muestra, por cada envase, la cantidad reservada anterior y la nueva, y los envases que se quitan.

**3b. La entrega está en curso: es con envío, su fecha programada es igual o anterior a la fecha actual y el vehículo de su transportista está en ruta:**

1.  El Sistema informa que el transportista ya inició la ruta con la entrega, que su envasado no se puede cambiar y que los envases se confirman al concretarla.
2.  El Agrónomo selecciona otra entrega (vuelve al paso 3) o cancela.

**4a. El invernadero de origen no tiene envases habilitados y activos, o el envase que el Agrónomo necesita no está habilitado:**

1.  El Sistema lo informa y ofrece habilitarlo con CMP-HAB-IIN · Habilitar Insumo en Invernadero, fuera de este caso de uso. Un envase recién habilitado tiene stock cero, así que no se puede reservar hasta que ingrese stock.
2.  El Agrónomo selecciona otra entrega (vuelve al paso 3) o cancela. La entrega puede concretarse igual sin envasado planificado: quien la concreta declara los envases que usó (extensión 9a de COM-CNC-ENT).

**4b. La fecha programada de la entrega es anterior a la fecha actual (por ejemplo, un retiro que el cliente todavía no hizo):**

1.  El Sistema calcula lo disponible para planificar a la fecha actual e indica que la entrega está atrasada.
2.  El caso de uso continúa en el paso 5.

**5-6a. El Agrónomo quita un envase ya agregado o cambia su cantidad:**

1.  El Sistema actualiza la carga y lo disponible de ese envase.
2.  El caso de uso continúa en el paso 5 o en el paso 7.

**6a. La cantidad no es válida: es menor o igual que cero, o tiene más decimales que los que admite la unidad del envase:**

1.  El Sistema señala el error e informa cuántos decimales admite la unidad.
2.  El Agrónomo corrige la cantidad (vuelve al paso 5).

**6b. La cantidad supera lo disponible para planificar del envase:**

1.  El Sistema señala el error e informa lo disponible del envase, sin contar los lotes que estarán vencidos en la fecha de referencia.
2.  El Agrónomo reduce la cantidad, elige otro envase (vuelve al paso 5) o quita el envase. Si necesita más stock, puede pedirlo con CMP-RLZ-PED · Realizar Pedido o, si el depósito tiene más de lo registrado, regularizarlo con CMP-AJT-STK · Ajustar Stock de Insumo, fuera de este caso de uso.

**6c. El envase indicado ya está en la carga:**

1.  El Sistema reemplaza la cantidad anterior por la nueva, porque la entrega tiene una sola reserva por envase, y la verifica como en el paso 6.
2.  El caso de uso continúa en el paso 5 o en el paso 7.

**8a. La carga no tiene ningún envase y la entrega no tenía envasado planificado:**

1.  El Sistema señala que debe indicar al menos un envase.
2.  El Agrónomo indica un envase (vuelve al paso 5) o cancela.

**8b. En una modificación, el Agrónomo quitó todos los envases reservados:**

1.  Junto con el resumen, el Sistema advierte que la entrega quedará sin envasado planificado y que, al concretarla, se declararán los envases usados.
2.  El Agrónomo confirma (continúa en el paso 9) o agrega un envase (vuelve al paso 5).

**8c. En una modificación, ninguna cantidad cambió y no se agregó ni quitó ningún envase:**

1.  El Sistema informa que no hay cambios para registrar.
2.  El Agrónomo modifica la carga (vuelve al paso 5) o cancela.

**8d. El Agrónomo quiere corregir un dato del resumen:**

1.  El Agrónomo indica el envase que quiere corregir y el caso de uso vuelve al paso 5.

**10a. Al registrar, la entrega ya no está «a realizar» (se concretó o se canceló) o está en curso (extensión 3b):**

1.  El Sistema no registra ningún cambio e informa la situación de la entrega.
2.  El caso de uso termina.

**10b. Entre la carga y la confirmación, otra operación redujo lo disponible de un envase y ya no cubre la cantidad indicada:**

1.  El Sistema no registra ningún cambio, conserva los datos ingresados e informa qué envase cambió y lo disponible vigente.
2.  El caso de uso vuelve al paso 5.

**10c. Entre la carga y la confirmación, otra persona cambió el envasado de la misma entrega:**

1.  El Sistema no registra ningún cambio e informa que el envasado cambió.
2.  El caso de uso vuelve al paso 4 con las reservas vigentes, como en la extensión 3a.

**Requisitos especiales**

  - Tras cada dato ingresado por el Agrónomo (pasos 5 y 6), la pantalla se actualiza con las verificaciones y lo disponible en no más de 1 segundo.
  - El paso 10 se ejecuta como una única transacción: las reservas de insumo nuevas, los cambios en las existentes y los logs se registran juntos o no se registra ninguno.
  - El control de concurrencia sobre el stock libre de los envases impide la sobreasignación entre este caso de uso y las siembras, los mantenimientos, los envasados, los ajustes y los consumos simultáneos sobre el mismo insumo del invernadero. También impide registrar un envasado mientras se concreta, se cancela o inicia su ruta la misma entrega.
  - La notificación de COM-PNF-ENT ofrece un acceso directo a este caso de uso con la entrega elegida (extensión 1a).
  - Solo el Agrónomo a cargo del invernadero de origen accede al envasado de sus entregas.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
  - El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

**Reglas de negocio**

  - **Quién lo ejecuta:** el Agrónomo a cargo del invernadero de origen de la entrega, aunque la entrega la haya planificado InfoPonia (regla 2 de 8.22). (Paso 2)
  - **Invernadero de origen:** el de las reservas de stock que entrega la entrega; es único (regla 3 de 8.8). (Pasos 2 y 4)
  - **Envase:** insumo de la categoría del sistema «Envases», con el insumo activo y habilitado en el invernadero de origen (insumo del invernadero «activo»). La categoría se identifica por su marca de categoría del sistema, no por su nombre (regla 1 de 8.23). (Pasos 4 y 5, extensión 4a)
  - **Disponible para planificar:** stock libre del envase en el invernadero de origen menos la cantidad disponible de sus lotes que estarán vencidos en la fecha de referencia, y nunca menos que cero (regla 8 de 8.4). Stock libre = stock actual − Σ cantidad reservada de sus reservas «activa». (Pasos 4, 6 y 10, extensión 6b)
  - **Fecha de referencia:** la fecha programada de la entrega o, si ya pasó, la fecha actual. (Paso 4 y extensión 4b)
  - **Disponible al modificar:** para un envase que la entrega ya tiene reservado, lo disponible suma su propia cantidad reservada, porque mantenerla no compromete stock nuevo. (Extensión 3a)
  - **Cantidad válida:** un número mayor que cero, con los decimales que admite la unidad del envase (unidad: 0; g, mL, m y m²: 2; kg, L y m³: 3) (regla 2 de 8.23). (Paso 6 y extensión 6a)
  - **Una reserva por envase:** cada entrega tiene, como máximo, una reserva «activa» por envase. Indicar otra vez un envase reemplaza su cantidad. (Extensión 6c)
  - **Reservar no descuenta stock:** la reserva solo aparta el envase del stock libre. El consumo, su salida de los lotes y su asiento se registran al concretar la entrega, por lo que realmente se usó (reglas 20, 23 y 24 de 8.8). (Paso 10)
  - **Modificación:** mientras la entrega esté «a realizar» y no esté en curso, el Agrónomo puede cambiar la cantidad de un envase, quitarlo o agregar otro, también después de un intento fallido de entrega (regla 19 de 8.8; regla 8 de 8.13). El cambio de cantidad se registra en la misma reserva, que conserva su fecha de reserva; un envase quitado deja su reserva «cancelada». (Extensión 3a, postcondición b)
  - **Entrega en curso:** una entrega con envío cuya fecha programada es igual o anterior a la fecha actual y cuyo transportista tiene el vehículo en ruta. Incluye las entregas demoradas, que también salen en la ruta (regla «Entregas de la ruta» de COM-INI-RUT). Su envasado no se modifica, porque los envases ya salieron y el Transportista los confirma contra lo reservado (pasos 4, 9 y 10 de COM-CNC-ENT). Después de un intento fallido, la entrega pasa al día siguiente sin transportista y deja de estar en curso. Un retiro no tiene ruta: su envasado se puede modificar hasta que se concrete. (Extensión 3b)
  - **Entrega sin envasado:** el envasado no es obligatorio para concretar. Si una entrega llega a su fecha sin envasado planificado, al concretarla se advierte y se declaran los envases usados (regla 22 de 8.8). (Extensiones 4a y 8b)
  - **Sin cantidad sugerida:** el Sistema no calcula cuántos envases necesita una entrega; presenta sus variedades, cantidades y peso para que el Agrónomo decida. (Paso 4)
  - **Planificador de la entrega:** la entrega sigue sin Agrónomo planificador, porque la planificó InfoPonia (postcondición a de COM-PNF-ENT). Quién planificó el envasado queda en el log de auditoría de cada reserva. (Paso 10)
  - **Invernadero sin Agrónomo:** si el invernadero de origen no tiene un Agrónomo activo, nadie planifica el envasado de sus entregas, que se concretan declarando los envases usados. El Agrónomo que se asigne al invernadero ve y planifica las entregas que sigan «a realizar» (reglas 2 y 3 de 8.22). (Paso 2)

**Lista de tecnología y variaciones de datos**

  - **2.** Las entregas pueden filtrarse por invernadero de origen y por fecha programada.
  - **5.** Los envases pueden buscarse por nombre. La cantidad se expresa en la unidad de medida del envase.

**Frecuencia**

Una vez por cada entrega planificada, más las modificaciones por cambios en la entrega o por intentos fallidos. Depende de la cantidad de ventas y de contratos de suministro vigentes; se estima que varias veces por día en cada invernadero. A confirmar con el Jardín Botánico.

**Temas abiertos**

  - **Quién envasa:** el modelo no dice quién arma físicamente el envasado (el Agrónomo, el Capataz u otra persona del invernadero). Si es el Capataz, ¿hay que notificarle el envasado planificado?
  - **Recordatorio de entregas sin envasado:** queda como mejora futura un aviso al Agrónomo, antes del inicio de las rutas, de las entregas del día sin envasado planificado (observación 3 de 8.19; «Ajustes pendientes en la documentación», punto 5, de pendientes\_CU).
  - **Entrega cancelada después de envasarse:** sigue abierto qué pasa con los envases que ya se usaron (observación 2 de 8.19; temas abiertos de COM-CNC-ENT). Hay que resolverlo al especificar Cancelar Orden (CU-11).
  - **Entrega que se achica después del envasado:** si una merma en la cámara recorta una reserva de stock de la entrega (regla 8 de 8.9), su cantidad planificada baja y el envasado puede quedar de más. Hoy nadie se lo avisa al Agrónomo. ¿Hace falta una notificación?
  - **Retiro en concreción:** en un retiro, el Vendedor puede estar concretando mientras el Agrónomo modifica el envasado. La extensión 14a de COM-CNC-ENT no verifica si cambiaron las reservas de insumo entre el paso 4 y el registro. Hay que verificarlo en COM-CNC-ENT.
  - **Cantidad sugerida:** sugerir los envases a partir de las variedades y cantidades de la entrega exigiría un dato nuevo en el modelo (envases por planta de cada variedad). Queda como mejora futura.

**Situaciones encontradas y propuestas (versión 0.1)**

Las ocho situaciones (clave del caso de uso; qué insumos son envases; lo disponible al modificar; la fecha de referencia de una entrega atrasada;
hasta cuándo se modifica; cómo se modifica una reserva; una reserva por envase y por entrega; el planificador de la entrega) ya están
aplicadas en el texto de arriba (su porqué queda en el documento de Drive; no hace falta para programar). Cambios pendientes aplicados:
MD-87 (regla «Invernadero sin Agrónomo») y MD-95 (regla «Disponible para planificar», con la fecha de referencia).

## Cambios ya decididos que se aplican

1. **PCU, sección 9:** el tema abierto de los envases de una compra-venta cancelada está cerrado: los envases solo se reservan hasta concretar,
   y la cancelación de la entrega cancela esas reservas sin consumo (`docs/casos_de_uso/produccion/cancelar_orden.md`, «entregas»).
2. **PROD-CNL-ORD, situación 10** (cerrada en ese caso de uso): «Entrega cancelada después de envasarse» de los temas abiertos queda
   respondida: las reservas pasan a «cancelada» sin consumo y se avisa al Agrónomo, que regulariza con CMP-AJT-STK si los envases ya se usaron.
3. **MD-118:** «en ruta» = `Vehiculo.esta_en_ruta(hoy)` (la extensión 3b y la regla «Entrega en curso» se leen así).

## Cómo se aplica en la ronda «Comercial 1» (COM-05a2; D-44, D-57, D-66)

### Qué entra y qué no

| Parte | En COM-05a2 |
|---|---|
| Escenario, extensiones \*a, \*b, 2a, 3a, 3b, 4a, 4b, 5-6a, 6a a 6c, 8a a 8d, 10a a 10c | **Sí** |
| 1a «desde la entrega» | **Sí**: desde la fila de la lista de envasado y desde el panel del Agrónomo (con el id de la entrega) |
| 1a «desde la notificación» (y el requisito especial del acceso directo) | **No se puede:** las notificaciones no tienen enlace (D-42). El texto del aviso de COM-PNF-ENT dice dónde está («Producción › Envasado»). Va a pendientes_CU (D-66, consecuencias) |
| Temas abiertos «Quién envasa», «Recordatorio», «Entrega que se achica», «Cantidad sugerida» | Fuera: siguen abiertos (mejoras futuras) |
| «Retiro en concreción» (14a de COM-CNC-ENT) | COM-06a: esta tarea ya bloquea la entrega al registrar, que es lo que necesita COM-CNC-ENT para detectarlo |

### Servicios (`comercial/servicios/envasado.py`)

- `entregas_para_envasar(actor, *, invernadero_id=None, fecha=None) -> list[FilaDeEnvasado]` (pasos 2 y 2a): las entregas «a realizar» de
  los invernaderos **activos** a cargo del Agrónomo, ordenadas por fecha programada y después id. Cada fila: la entrega, su invernadero, el
  cliente, la modalidad, el transportista, el contenido (variedad y cantidad planificada por línea, sin las quitadas), el peso, la fecha
  (con «atrasada»), `tiene_envasado` y `en_curso`. `fecha` filtra por la fecha programada exacta. Una consulta por tabla.
- `datos_de_envasado(actor, entrega_id, carga=None) -> DatosDeEnvasado` (pasos 4 a 6, sin escribir): el detalle de la entrega; los envases
  ofrecidos; las filas de la carga con lo disponible de cada envase y su error; la **huella** de las reservas de insumo de la entrega (para
  10c); y los avisos (3b, 4a, 4b). Sin `carga`, la carga inicial es la de las reservas activas (3a) o vacía.
- `resumen_de_envasado(actor, carga) -> ResumenDeEnvasado` (pasos 7 y 8, sin escribir): por envase, la cantidad anterior (si la había) y la
  nueva, lo disponible que le queda, los quitados; 8a (error), 8b (aviso), 8c (error).
- `planificar_envasado(actor, carga) -> Entrega` (pasos 9 a 11), en `transaction.atomic()`.
- `carga` es un `dataclass` `CargaDeEnvasado(entrega_id, filas, huella)`, con `filas` = lista de `(insumo_invernadero_id, cantidad)`; lo arma
  `desde_post`. Indicar un envase que ya está en la carga reemplaza su cantidad (6c): la carga es, en el fondo, un diccionario por envase.
- Errores de negocio: `ValidationError` con `code` y el campo (la fila), como el resto de `comercial`.

### Reglas en el código

- **Quién** (regla «Quién lo ejecuta»; requisito «Solo el Agrónomo a cargo»): Agrónomo activo, a cargo del invernadero de origen **en el
  momento** (se relee después de bloquear). Cualquier otro rol: 403 en las rutas y `PermissionDenied` en los servicios. El Gerente no ve esta
  pantalla (como «Cultivos», PRD-01: no planifica producción).
- **Envases ofrecidos** (regla «Envase»; 4a): los `InsumoInvernadero` **activos** del invernadero de origen cuyo insumo está activo y su
  categoría es la del sistema `envases` (`inventario.categorias.ENVASES`, por código, nunca por nombre). Ordenados por nombre. Sin ninguno:
  «Este invernadero no tiene envases habilitados.» y el acceso a la pantalla de insumos del invernadero de INV-02 (donde se habilita,
  CMP-HAB-IIN), si el Agrónomo puede abrirla.
- **Fecha de referencia** (4b): `max(fecha_programada_orden, hoy)`.
- **Disponible** (reglas «Disponible para planificar» y «Disponible al modificar»): `stock.disponible_para_planificar(ids, fecha_ref)` más,
  para un envase que la entrega ya tiene reservado, su propia `cantidad_reservada` activa.
- **Cantidad válida** (6a): `Decimal` > 0 con a lo sumo `inventario.unidades.decimales_de(unidad)` decimales; se lee como en los formularios de
  `inventario` (coma o punto decimal, como ya lo hace INV-02). Texto: «Ingresá una cantidad mayor que 0, con hasta 2 decimales (g).»; para
  unidad, «… un número entero (unidad).».
- **Supera lo disponible** (6b): «Supera lo disponible: quedan 40 unidades (sin contar los lotes que estarán vencidos el 26/11).». Junto al
  error, la ayuda: «Si necesitás más, pedilo con un pedido de compra o, si el depósito tiene más de lo registrado, ajustá el stock.»
- **En curso** (3b, 10a; regla «Entrega en curso»): con envío, `fecha_programada_orden <= hoy` y `transportista.vehiculo.esta_en_ruta(hoy)`.
  La fila de la lista dice «En curso» sin botón; si se entra por la URL: «Juan Gómez ya inició la ruta con esta entrega: su envasado no se puede
  cambiar. Los envases se confirman al concretarla.» Un retiro nunca está en curso.
- **Registro** (paso 10), en este orden:
  1. bloqueos (`docs/patrones/bloqueos.md`, «Entregas y envasado»): la cuenta del Agrónomo → el invernadero (`bloquear_invernadero_activo`)
     → los `InsumoInvernadero` de la carga **y** de las reservas activas, en orden de id, y sus lotes → la entrega → sus reservas de insumo;
  2. relecturas: el Agrónomo sigue a cargo y activo; la entrega sigue «a realizar» y no está en curso (10a: `entrega_no_a_realizar` o
     `entrega_en_curso`, con el estado actual); la huella de sus reservas es la misma (10c: `envasado_cambio`, con la carga vigente); cada
     cantidad nueva o aumentada sigue cubierta por lo disponible (10b: `disponible_cambio`, con el envase y lo vigente; se conserva la carga);
  3. por cada envase nuevo, `reservas.reservar(entrega, iin, cantidad, hoy)` (a); por cada cambio de cantidad, `reservas.cambiar_cantidad`
     (b); por cada quitado, `reservas.cancelar` (b);
  4. la auditoría (e, f).
  La validación de lo disponible solo mira las cantidades **que suben** (nuevas o aumentadas): bajar o quitar nunca falla (regla «Disponible
  al modificar»).
- **Huella** (10c): una tupla ordenada de `(id, insumo_invernadero_id, cantidad_reservada, estado)` de las reservas de insumo de la entrega,
  tomada al abrir la pantalla y enviada con el formulario (como la huella de PROD-MOD-CSC, COM-04).
- **Sin cambios** (8c): la carga es igual a las reservas activas: `sin_cambios`, «No hay cambios para registrar.».
- **Sin envases** (8a): «Indicá al menos un envase.». **Todos quitados** (8b): el resumen avisa «La entrega va a quedar sin envasado
  planificado: al concretarla se declaran los envases usados.» y deja confirmar.
- **Nada más cambia** (d): ni la entrega, ni sus líneas, ni su fecha, ni su transportista, ni `agronomo` (sigue nulo). No se notifica a nadie
  (el caso de uso no lo pide).
- **Auditoría** (e, f; D-36): un registro `planificacion_envasado` (acción nueva de `core`) con usuario y rol; la entrega como principal; cada
  reserva creada como afectada (con `datos`: envase, cantidad, fecha) y cada reserva cambiada con `cambios` (`cantidad_reservada` o `estado`,
  antes → después). Decimales y fechas como texto.

## Pantallas

Guía visual: `docs/prototipos/comercial/comercial_y_cosecha.html`. Vale la **última** definición de cada función.

| Pantalla | Funciones del prototipo | En el sistema |
|---|---|---|
| Producción › **Envasado** (lista de entregas, pasos 2 y 2a) | `tabEnvasado` (línea 1248) | Para el Agrónomo. Se llega por el acceso «Envasado» de la pantalla de órdenes de PRD-01 (campo `envasado` de `registrar_entradas_de_comercial`, `docs/api/extensiones_de_produccion.md`, sección 4) y por el indicador «Entregas sin envasado» del panel. Filtros: invernadero (si tiene más de uno a cargo) y fecha programada. Columnas: entrega (`OT-0231`, contrato), cliente (debajo, «Retiro» o el transportista o «Sin transportista»), contenido (y el peso), fecha programada (con «Atrasada» si corresponde), envasado («Planificado» o «Sin planificar» en ámbar) y la acción «Planificar envasado» / «Modificar envasado», o «En curso» sin botón. Texto explicativo: «Las entregas las planifica InfoPonia. Reservá los envases de cada una: se descuentan del stock recién al concretarla.» Vacía (2a): «No hay entregas para envasar.» |
| Planificar / modificar envasado (pasos 4 a 11) | `INIT.env`, `VIEWS.env` (líneas 1289, 1290 y 1704), `envDisp`, `envErr`, `dupOf` (1702 y 1703) | Arriba, los datos de la entrega (contenido, peso, fecha, modalidad y transportista; «Atrasada» si 4b). «Envases a reservar»: filas con un **buscador de envases** (por nombre, con lo disponible y la unidad de cada uno; no un `<select>`), la cantidad con su unidad, lo disponible debajo y el error de la fila; «Agregar envase» y «Quitar». Con HTMX, cada cambio actualiza la carga en menos de 1 segundo; sin JavaScript, «Actualizar». «Revisar» (bloqueado mientras haya errores) lleva al **resumen** (paso 8, como página: anterior → nueva, quitados, el aviso de 8b); «Confirmar envasado» registra; «Volver a la carga» (8d) y «Cancelar» (\*a). Al terminar, aviso breve «Envasado de OT-0231 planificado.» y vuelta a la lista |
| Panel del Agrónomo: «Entregas sin envasado» | `secCosecha` (1422) | En `entregas.md`, «Pantallas» |

Las rutas van con el mismo prefijo que usaron las pantallas de cosecha del Agrónomo de COM-04 (el que deja marcada «Producción» en el
menú). Vistas que solo orquestan, `rol_requerido`, `never_cache`, `vary_on_headers("HX-Request")`, respaldo sin JavaScript, errores por
campo y aviso breve (D-29).

### Lo que difiere del prototipo (corregir, D-61)

- `VIEWS.env` usa un `<select>` nativo para el envase: el caso de uso pide buscarlo por nombre (variación 5) y D-24 descartó el `<select>`.
- `dupOf` muestra el error «Ese envase ya está en otra fila»: manda la extensión 6c (indicarlo otra vez **reemplaza** su cantidad, con el
  aviso «Ya estaba en la lista: se reemplazó la cantidad.»).
- `envErr` solo acepta enteros (`entR(r.c,1)`): la cantidad admite los decimales de la unidad del envase (regla «Cantidad válida»).
- `ACT['env-ok']` registra sin resumen: falta el paso 8 (resumen y confirmación), con 8a a 8d.
- `tabEnvasado` muestra solo el invernadero «A»: en el sistema, los invernaderos a cargo, con el filtro.
- El prototipo propone «Bandeja PET 1 kg» con la cantidad del peso: el caso de uso dice «Sin cantidad sugerida».
- Falta 4a (sin envases habilitados) y 4b (atrasada).

### Solo prototipo

Lo de la lista general de `docs/prototipos/comercial/README.md`, más: `DB.envases` (datos de ejemplo) y la cantidad propuesta de `INIT.env`.

## Pruebas

- `comercial/tests/test_prod_pnf_env.py` (`ProdPnfEnvServicioTests`): una por regla (quién —Agrónomo a cargo, otro Agrónomo, Gerente,
  Capataz, cuenta inactiva—; envase —uno de otra categoría, uno inactivo, uno no habilitado—; disponible con lotes que vencen antes y después
  de la fecha de referencia; fecha de referencia de una entrega atrasada; disponible al modificar; cantidad válida por cada unidad; una
  reserva por envase; modificación; entrega en curso; invernadero sin Agrónomo; invernadero inactivo), por postcondición (a a f) y por
  extensión (2a, 3a, 3b, 4a, 4b, 6a, 6b, 6c, 8a, 8b, 8c, 10a con concretada, cancelada y en curso, 10b, 10c); quitar un envase y volver a
  agregarlo (dos reservas, una cancelada y una activa: D-66, punto 8); que nada cambia en la entrega ni en el stock actual ni en los lotes;
  sin consultas por fila en la lista (`assertNumQueries` igual con una y con tres entregas).
- `comercial/tests/test_envasado_concurrencia.py` (`@tag("concurrencia")`): dos envasados de entregas distintas por el último stock de un
  envase (uno da 10b); un envasado contra una siembra que reserva el mismo insumo (PRD-01); un envasado contra la cancelación de la misma
  entrega (10a).
- `comercial/tests/test_envasado_vistas.py`: permisos por rol; la lista con sus filtros y su orden; la carga con HTMX (solo el bloque) y sin
  JavaScript; el resumen como página; la confirmación; los mensajes de cada extensión; que `calcular/` (si existe) no escribe nada.

## Para más adelante

- **COM-06a:** COM-CNC-ENT confirma la cantidad utilizada y devuelta de cada reserva (pasos 4, 9 y 10) y admite el exceso de envases (regla 21
  de 8.8) **sin tocar la restricción** de `ReservaInsumo`: la utilizada se topea en la reservada y el exceso va en el consumo del envase
  (D-68, punto 2; `docs/casos_de_uso/comercial/rutas.md`, «Cómo se aplica»).
- Mejoras futuras de los temas abiertos del caso de uso.
