# Casos de uso · producción · Registrar Lote Existente

Copia para el repo de PROD-REG-LTE (v0.1, 23/11/2026), del hilo de casos de uso (`PROD-REG-LTE.md`). Cotejado con `decisiones_A0.md`
(«Lotes previos, opción (a) reducida», «Registrar Lote Existente (modelo)» L1 a L3, H11): **esas decisiones ganan** si algo difiere. Lo técnico
está en D-92 (punto 12) y en «Cómo se aplica (código)», al final. Tarea: PRD-05.

-----

## **Caso de uso PROD-REG-LTE: Registrar Lote Existente**

Caso de uso extendido del módulo Producción (versión 0.1, 23/11/2026), con el formato de «CU extendidos» (modelo: PROD-CNC-SMB v0.5). Caso nuevo de la decisión H3/H4 («Lotes previos, opción (a) reducida», decisiones_A0.md): permite que los lotes de plantas que ya existían al poner en marcha InfoPonia entren al sistema contra la cuenta Capital Inicial. Reemplaza la regla de arranque «los lotes previos se siguen fuera del sistema». 

**Alcance:** Sistema InfoPonia.
**Nivel:** Objetivo de usuario.
**Módulo:** Producción / Lotes.
**Actor principal:** Agrónomo a cargo del invernadero.
**Versión:** 0.1

**Personal involucrado e intereses**

**Agrónomo:**
- quiere cargar de una vez los lotes que ya tiene en los sectores para seguir planificando sus transiciones y cosechas desde el sistema, sin duplicar trabajo;
- quiere que los sectores ocupados por esos lotes reflejen la realidad.

**Gerente y Contador:**
- quieren que el valor de la producción en proceso existente al empezar entre a la contabilidad contra Capital Inicial, sin falsear resultados.

**Capataz y Técnico:**
- quieren que sus órdenes futuras (transiciones, cosechas) puedan planificarse sobre estos lotes.

**Organización (Jardín Botánico):**
- quiere pasar a InfoPonia sin esperar a que terminen los lotes previos.

**Relaciones con otros casos de uso**
- No incluye ni es extendido por otros casos de uso.
- **Lo precede:** la puesta en marcha (no es un caso de uso) y la configuración de invernaderos, sectores, cultivos y variedades.
- **Lo siguen:** PROD-PNF-TRN · Planificar Transición y PROD-PNF-CSC · Planificar Cosecha sobre el lote cargado.
- **Alternativa de:** PROD-PNF-SMB y PROD-CNC-SMB (el flujo normal de siembra).
- **Fuera de alcance:** las partidas en cámara previas (se venden con asiento manual del Contador, CON-REG-ASI) y los lotes cosechados.

**Precondiciones**
a. El actor está autenticado con una cuenta activa de Agrónomo.
b. El actor tiene a su cargo al menos un invernadero «activo» con sectores activos y con una variedad cuyo ciclo tiene etapas productivas.
c. El invernadero no tiene siembras concretadas por el flujo normal (PROD-CNC-SMB). (H3/H4)
d. Existe un ejercicio contable «abierto» y existen las cuentas Productos en Proceso y Capital Inicial.

**Garantías mínimas**
El registro es atómico. Si se cancela o falla:
- no queda registrada ninguna siembra, lote, ocupación de sector, asiento ni log parcial;
- no cambian los agujeros de ningún sector.

**Además:**
- No se crean reservas de insumo ni consumos, ni se descuenta stock de insumos: lo que ya se usó en el lote existe fuera del sistema.
- No se genera ninguna orden de trabajo para el Capataz.
- No se registran mermas ni cosechas previas.
- El caso de uso solo se puede usar en un invernadero que todavía no tuvo siembras por el flujo normal.

**Garantías de éxito (Postcondiciones)**
a. Se creó una siembra ya «concretada» con motivo «carga inicial», con la fecha de siembra indicada (puede ser pasada) y la cantidad de plantines indicada, asociada a la variedad y al invernadero, sin reservas ni consumos.
b. Se creó un lote «activo» asociado a la siembra y al invernadero, con la cantidad inicial igual a la cantidad actual (las plantas indicadas), en la etapa productiva indicada del ciclo de la variedad, con el costo estimado indicado como costo acumulado (puede ser $0) y una entrada de bitácora de tipo «carga inicial» con la etapa actual y la fecha de ingreso a ella.
c. Por cada sector indicado se creó una ocupación de sector asociada a la siembra y al lote, con los agujeros ocupados; los agujeros disponibles del sector bajaron en esa cantidad.
d. Si el costo estimado del lote es mayor que cero, se registró un asiento originado en la siembra: Debe Productos en Proceso / Haber Capital Inicial, por el costo estimado, con la fecha actual. Si es $0, no se registró asiento (H11).
e. Se creó un log de auditoría por la siembra, el lote, cada ocupación de sector, cada sector modificado y el asiento, con usuario, rol, fecha, hora, identificador y valores.

**Escenario principal de éxito (Flujo Básico)**
(El Agrónomo carga un lote en maduración que ocupa un sector de su invernadero.)

1. **El Agrónomo inicia el registro de un lote existente.**
2. **El Sistema verifica que el invernadero no tenga siembras concretadas por el flujo normal y presenta los invernaderos activos a cargo del Agrónomo que cumplen la precondición.**
3. **El Agrónomo selecciona el invernadero.**
4. **El Sistema presenta el formulario: cultivo y variedad (activos), etapa productiva actual del ciclo de la variedad, fecha de siembra, fecha de ingreso a la etapa actual, cantidad de plantas (inicial = actual), costo estimado del lote (por defecto $0) y la distribución por sector.**
5. **El Agrónomo indica la variedad, la etapa actual, las fechas, las cantidades y el costo estimado.**
6. **El Sistema presenta los sectores activos del invernadero compatibles con el tipo de la etapa actual, con sus agujeros disponibles.**
7. **El Agrónomo indica, por cada sector, la cantidad de plantas que ocupa.**
8. **El Sistema verifica los datos y presenta el resumen: la variedad, la etapa, las fechas, las cantidades, el costo estimado y por planta, la ocupación por sector con los agujeros que quedan libres y el asiento que se registrará (Debe Productos en Proceso / Haber Capital Inicial).**
9. **El Agrónomo confirma el registro.**
10. **El Sistema registra el lote existente:**
    - crea la siembra «concretada» con motivo «carga inicial»;
    - crea el lote en la etapa indicada;
    - crea las ocupaciones de sector y reduce los agujeros disponibles;
    - registra el asiento, si el costo es mayor que cero;
    - registra la auditoría correspondiente.
11. **El Sistema informa al Agrónomo que el lote fue registrado y presenta su identificador, con acceso a planificar su transición o su cosecha.**

**Extensiones (Flujos Alternativos)**

**\*a. En cualquier momento antes de la confirmación (paso 9), el actor cancela el registro:**
1. El Sistema descarta los datos sin registrar ningún cambio.

**\*b. En cualquier momento el Sistema falla o se interrumpe la conexión:**
1. El Sistema revierte cualquier registro parcial.
2. Al restablecerse, informa que el lote no fue registrado.
3. El actor reinicia desde el paso 1.

**2a. Ningún invernadero del actor cumple la precondición (todos tienen siembras concretadas):**
1. El Sistema informa que este caso de uso solo se usa en invernaderos sin siembras por el flujo normal.
2. El caso de uso termina.

**5a. La fecha de siembra es posterior a la fecha actual, o la fecha de ingreso a la etapa es anterior a la de siembra o posterior a hoy:**
1. El Sistema señala el error.
2. El actor corrige (vuelve al paso 5).

**5b. La cantidad de plantas es cero, negativa o no entera:**
1. El Sistema señala el error.
2. El actor corrige (vuelve al paso 5).

**5c. El costo estimado es negativo o tiene más de dos decimales:**
1. El Sistema señala el error.
2. El actor corrige (vuelve al paso 5).

**7a. La cantidad en un sector supera sus agujeros disponibles:**
1. El Sistema informa los agujeros disponibles de ese sector.
2. El actor corrige (vuelve al paso 7).

**7b. La suma de la distribución por sector no es igual a la cantidad actual del lote:**
1. El Sistema señala la diferencia.
2. El actor corrige (vuelve al paso 7).

**7c. El actor quiere repartir el lote en más de un sector:**
1. El actor repite el paso 7 por cada sector.

**7d. No hay sectores activos compatibles con la etapa elegida:**
1. El Sistema informa que no hay dónde ubicar el lote y que hay que crear o activar un sector.
2. El actor elige otra etapa o cancela.

**10a. Al registrar, el invernadero o un sector dejó de estar activo, los agujeros disponibles cambiaron, o se concretó una siembra por el flujo normal:**
1. El Sistema no registra ningún cambio e informa qué cambió.
2. El caso de uso vuelve al paso 4.

**Requisitos especiales**
- La interfaz se adapta a computadora y a celular.
- El registro del paso 10 se completa en no más de 5 segundos.
- El registro es una única transacción: siembra, lote, ocupaciones, agujeros, asiento y logs juntos o ninguno.
- El control de concurrencia impide que dos usuarios ocupen los mismos agujeros, o que se registre un lote existente mientras se concreta una siembra normal en el mismo invernadero, y respeta el orden de bloqueos de `docs/patrones/bloqueos.md` (el ejercicio al final).
- El Agrónomo accede solo a los invernaderos que tiene a cargo.
- Los montos se expresan en pesos argentinos con dos decimales.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los logs de auditoría son de solo inserción.

**Reglas de negocio**
- **Quién registra:** el Agrónomo a cargo del invernadero. (Decisión H3/H4)
- **Cuándo:** solo en un invernadero sin siembras concretadas por el flujo normal. En cuanto se concreta una, el caso de uso deja de estar disponible para ese invernadero. (H3/H4; precondición c)
- **Siembra de carga inicial:** una siembra ya concretada, con motivo «carga inicial» (valor nuevo del motivo; ítem MD nuevo), sin reservas ni consumos, con fecha de siembra pasada permitida (nunca futura). No tiene orden de trabajo planificada ni Capataz asignado. (H3/H4; extensión 5a)
- **Etapa actual:** cualquier etapa productiva del ciclo de la variedad, no solo Germinación. Los sectores se eligen según el tipo de esa etapa. (Regla de «Etapa inicial del lote» de PROD-CNC-SMB, aquí sin restricción)
- **Costo estimado:** lo indica el Agrónomo (puede ser $0). El costo por planta es el costo estimado dividido por la cantidad actual. (H3/H4)
- **Asiento:** Debe Productos en Proceso / Haber Capital Inicial por el costo estimado, originado en la siembra, con la fecha actual y en el ejercicio abierto; con costo $0 no hay asiento. (H3/H4, H11; regla de asientos de la regla 14 de 8.20)
- **Sectores:** la ocupación toma agujeros disponibles; los agujeros planificados son iguales a los ocupados, porque no hubo planificación. (Reglas 3 y 4 de 8.13, por analogía)
- **Sin otras cargas previas:** las partidas previas en cámara y las cosechas anteriores no se cargan; la venta de esa producción se registra con un asiento manual del Contador (Debe Caja o Banco c/c / Haber Ventas). (H3/H4)
- **Después de cargado:** el lote se comporta como cualquier lote: se puede transicionar, cosechar, registrar mermas y aplicaciones de insumo.
- **Aplicación de Insumos sobre lotes previos:** ya no hace falta como regla especial. (H3/H4)

**Lista de tecnología y variaciones de datos**
- **5.** Fechas: dd/mm/aaaa. Cantidades: enteros en unidades. Costo estimado: pesos con dos decimales.
- **7.** Cantidad por sector: entero hasta los agujeros disponibles.

**Frecuencia**
Muy baja: una vez por cada lote existente, durante la puesta en marcha.

**Decisiones derivadas del hilo de análisis**
- Cantidad inicial = cantidad actual: el lote empieza su vida en el sistema con lo que hay, por eso no se registran mermas previas.
- El costo estimado se guarda en el costo acumulado del lote (MD-79, `Lote.costo_acumulado`); la regla 15 de 8.9, que lo derivaba de los consumos, queda desactualizada.

**Decisiones de modelo (L1 a L3, aprobadas)**
- R078 (Siembra–Capataz) pasa a 0..1, nulo solo en una siembra de carga inicial. Entra al ítem MD-120.
- Una entrada de bitácora de tipo nuevo «carga inicial» (cumple R082, 1..*) registra la etapa actual (R106) y la fecha de ingreso a esa etapa; la planificación de transición y la fecha máxima de cosecha (MD-09) la leen como la última transición.

-----

## Cómo se aplica (código)

**Precondición d y extensión «sin ejercicio»:** no se programan (D-92 punto 2). El asiento lo crea `registrar_asiento_automatico` (D-86), que
elige el ejercicio por la fecha (la actual) y se recupera solo.

**Modelo (D-92 punto 12; migración de `produccion`):**

- `Siembra.tipo_siembra`: `TextChoices` `normal` («Normal») y `carga_inicial` («Carga inicial»), por defecto `normal` (las filas existentes
  quedan `normal`). CHECK `siembra_tipo_valido`.
- `Siembra.capataz` redeclarado nulo (L1, R078 0..1) y CHECK `siembra_capataz_segun_tipo`: nulo si y solo si `carga_inicial`.
- `Bitacora.TipoEvento.CARGA_INICIAL = "carga_inicial", "Carga inicial"`; el CHECK `bitacora_tipo_evento_valido` suma el valor.
- Nada más cambia: `Lote`, `OcupacionSector` y `OrdenTrabajo` ya tienen todo.

**Servicio** `produccion/servicios/lotes_existentes.py`:

- `invernaderos_disponibles(actor)`: los activos a cargo del Agrónomo sin una `Siembra` concretada con `tipo_siembra = normal` (precondición c,
  paso 2, extensión 2a).
- `datos_de_registro(actor, invernadero_id, variedad_id=None, etapa_id=None)`: variedades activas con ciclo, etapas productivas de su ciclo y, con
  la etapa elegida, los sectores **elegibles** con sus agujeros libres. Elegible = la regla «Sector elegible» de PROD-PNF-TRN (activo, del tipo de
  la etapa, perfil familiar compatible, con lugar): se reutiliza la lógica de `transiciones._sectores_del_destino` (si hace falta, moverla a un
  módulo común de `produccion` sin cambiar su comportamiento). **Sobre el perfil familiar:** el caso de uso dice «compatibles con el tipo de la
  etapa»; la compatibilidad de perfil es la regla de todos los sectores del sistema y se aplica igual (anotado para el hilo de análisis).
- `resumen_de_registro(actor, datos)` (paso 8) y `registrar_lote_existente(actor, datos) -> Lote` (paso 10), con `datos` = invernadero,
  variedad, etapa, `fecha_siembra`, `fecha_ingreso_etapa`, `cantidad`, `costo_estimado`, `distribucion = {sector_id: plantas}`.
- Validaciones: 5a (fechas: siembra ≤ hoy; siembra ≤ ingreso a la etapa ≤ hoy), 5b (entero > 0), 5c (`Decimal` ≥ 0 con dos decimales como
  mucho), 7a, 7b, 7d. Códigos de `ErrorDeProduccion`: `fecha_invalida`, `cantidad_invalida`, `costo_invalido`, `supera_agujeros`,
  `distribucion_incompleta`, `sin_sectores`, `invernadero_con_siembras` (2a y 10a).
- Orden de bloqueo (docs/patrones/bloqueos.md, «`produccion`»): cuentas → invernadero (`bloquear_invernadero_activo`) → variedad → sectores (en
  orden de id) → filas nuevas → ejercicio (lo toma el servicio de asientos, al final). Releer después de bloquear: el invernadero sigue sin
  siembras normales concretadas, los sectores siguen activos y con lugar (10a). Concretar una siembra normal toma el mismo invernadero primero,
  así que las dos no se cruzan.
- Escritura, en una transacción: la `Siembra` (`tipo_orden = siembra`, `estado_orden = concretada`, `tipo_siembra = carga_inicial`,
  `capataz = None`, `agronomo = actor`, `numero` de la secuencia, `fecha_creacion_orden = fecha_resolucion_orden = hoy`,
  `fecha_programada_orden = fecha_siembra = la indicada`, `cant_plantines_siembra = cantidad`); el `Lote` (`etapa` = la elegida,
  `cantidad_inicial = cantidad_actual = cantidad`, `costo_acumulado = costo_estimado`); una `OcupacionSector` por sector
  (`cant_agujeros_planificados = cant_agujeros_ocupados` = sus plantas, `lote` = el nuevo); una `Bitacora` `carga_inicial` (lote, etapa,
  `fecha_bitacora` = ingreso a la etapa, hora actual, `responsable = actor`, sectores); el asiento si el costo es mayor que 0 (Debe
  `PRODUCTOS_EN_PROCESO` / Haber `CAPITAL_INICIAL`, origen la `Siembra`, fecha actual); la auditoría `registro_lote_existente` con todo lo
  anterior en `afectados` (acción nueva de `core`).
- **Lectura** (`produccion/servicios/lotes.py`): `entradas_a_la_etapa` y `fecha_de_entrada_a_maduracion` toman la `fecha_bitacora` de la
  entrada `carga_inicial` del lote cuando no hay una transición concretada hacia la etapa actual (L3). `fecha_maxima_de_cosecha` hereda el
  cambio. La consulta de la bitácora (PROD-CNS-BIT) suma «Carga inicial» al filtro y a la lista.

**Pantalla:** no está en el prototipo. Va en «Producción», como acción «Registrar lote existente» de la lista de lotes del Agrónomo, visible solo
si `invernaderos_disponibles` no está vacío; el formulario copia el de PROD-PNF-SMB (variedad y distribución por sector) más la etapa, las dos
fechas y el costo estimado, y el resumen muestra el asiento (paso 8). Anotá en el «Cierre» cómo quedó (D-61).

**Pruebas:** `produccion/tests/test_prod_reg_lte.py` (`ProdRegLteServicioTests`, una por postcondición y por extensión; sin asiento con costo
0), `test_lotes_lectura.py` (amplía: fecha de entrada desde la carga inicial), `test_prod_reg_lte_concurrencia.py` (`@tag("concurrencia")`: contra
concretar una siembra normal en el mismo invernadero; dos cargas que ocupan el mismo sector), `test_modelos_produccion.py` (los dos CHECK nuevos) y
`test_prod_reg_lte_vistas.py`.
