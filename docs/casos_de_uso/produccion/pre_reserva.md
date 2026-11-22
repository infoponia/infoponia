# Casos de uso · producción · Pre-reservar Período de Suministro

Copia para el repo de PROD-PRR-SUM, versión 0.1 del documento de Drive «CU · PROD-PRR-SUM · Pre-reservar Período de Suministro» (carpeta
«InfoPonia · Comercial · Análisis»). Reemplaza al caso 31 de PCU (PCU, sección 12). Cotejado con pendientes_CU, con PCU (secciones 7, 9 y
12), con MD-126, MD-127, MD-131 y MD-133, con el modelo de dominio (reglas 7 y 17 de 8.6, 10 y 16 de 8.8, 3 de 8.11, 2 de 8.18, 1 de 8.9) y
con el glosario.

Lo programa COM-03. Archivo de pruebas: `comercial/tests/test_prod_prr_sum.py`. Si este archivo y sus fuentes no coinciden, avisá.

Para nombrar las pruebas: este caso de uso no numera sus reglas (`test_periodo_a_pre_reservar_…`), sus postcondiciones son
`test_post_<letra>_…` y sus extensiones `test_ext_<numero>_…`.

## PROD-PRR-SUM · Pre-reservar Período de Suministro

Caso de uso nuevo del módulo de producción (versión 0.1, 20/11/2026), con el formato de «CU extendidos». Reemplaza al caso 31 de PCU (Planificar Cosecha por Contrato, nombre provisional). Decisiones del 20/11/2026 aplicadas: nombre nuevo (A); ejecución diaria única con orden fijo (B; T-04); con stock insuficiente se reserva lo disponible, se alerta y se reintenta cada día (C; MD-133); entran todos los períodos de la ventana sin reserva (D); avisos al Capataz y al Agrónomo (E).

**Alcance:** Sistema InfoPonia.

**Nivel:** Objetivo de usuario.

**Módulo:** Producción / Reservas.

**Versión:** 0.1

**Actor principal:** InfoPonia (proceso automático).

**Personal involucrado e intereses**

  - **Cliente:** quiere que cada período de su suministro tenga el producto apartado con tiempo.
  - **Vendedor:** quiere enterarse a tiempo si un período no tiene stock suficiente.
  - **Agrónomo y Capataz:** quieren las cosechas programadas con anticipación y con lotes reales.
  - **Gerente:** quiere que nunca se reserve dos veces el mismo stock ni un período dos veces.

**Relaciones con otros casos de uso**

  - **Incluye («include»):** PROD-ASG-STK · Asignar Stock Maduro, una vez por período.
  - **Lo preceden:** COM-PCT-SUM y COM-MOD-SUM, que crean los detalles vigentes.
  - **Lo sigue:** COM-PNF-ENT · Planificar Entrega, en el paso 4 de la misma ejecución diaria, para las reservas que quedan listas para entrega.
  - **Relacionados:** PROD-MOD-CSC y PROD-CNL-ORD, sobre las cosechas que se crean acá.

**Disparador:** la ejecución diaria de InfoPonia, en su paso 3. Orden de la ejecución: (1) vencer partidas en cámara, (2) vencer pagos, (3) pre-reservar suministros, (4) planificar entregas (T-04).

**Precondiciones**

a. Existe la Configuración Operativa con los días de pre-reserva (díasPreReservaSuministro).

**Garantías mínimas**

  - Cada período es atómico: si falla uno, no queda nada parcial de ese período y los demás siguen.
  - Ningún período tiene más reservas que las necesarias para cubrirlo, aunque el proceso se repita.
  - Ningún lote ni partida queda reservado por encima de su stock libre.

**Garantías de éxito (Postcondiciones)**

a. Cada período a pre-reservar tiene su reserva, con fecha de entrega igual a la fecha del período y sus líneas de cámara o de lote según la regla 7 de 8.6.

b. Si la reserva tiene líneas de lote, se creó su cosecha con la fecha de la regla 3 de 8.11 y prioridad «media». Si todas sus líneas son de cámara, quedó «lista para entrega».

c. Si un período no se pudo cubrir completo, se reservó lo disponible y se generó la alerta «período sin cobertura completa» al Agrónomo, con notificación al Vendedor del contrato (MD-133). Si ya tenía la alerta, no se generó otra.

d. Si la ejecución completó un período que tenía esa alerta, la alerta quedó resuelta.

e. Se notificó cada cosecha creada al Capataz de su invernadero y al Agrónomo.

f. Se creó un log de auditoría por período, con origen InfoPonia: período, reserva, líneas, cosecha y cantidad sin cubrir.

**Escenario principal de éxito (o Flujo Básico)**

1.  InfoPonia inicia el paso 3 de la ejecución diaria.
2.  InfoPonia busca los períodos a pre-reservar y los recorre ordenados por fecha de entrega y, con la misma fecha, en el orden de registro de sus detalles.
3.  Para cada período, ejecuta PROD-ASG-STK por la cantidad del período, con la fecha del período.
4.  InfoPonia registra la reserva, sus líneas, la cosecha si corresponde, y la auditoría.
5.  InfoPonia notifica la cosecha al Capataz y al Agrónomo.

\*InfoPonia repite los pasos 3 a 5 por cada período.\*

6.  InfoPonia termina el paso 3 y la ejecución continúa con la planificación de entregas.

**Extensiones (o Flujos Alternativos)**

**\*a. En cualquier momento InfoPonia falla:**

1.  InfoPonia revierte el período en curso; los ya registrados se conservan. En la próxima ejecución el período se vuelve a tomar, porque sigue sin reserva.

**2a. No hay períodos a pre-reservar:**

1.  El paso 3 termina sin cambios.

**3a. El stock maduro libre no alcanza para el período:**

1.  InfoPonia reserva lo disponible y genera la alerta «período sin cobertura completa», con la cantidad sin cubrir y la fecha del período.
2.  Si no hay nada disponible, no crea reserva y genera la misma alerta.

**3b. El período ya tiene reserva propia pero quedó con cantidad sin cubrir (alerta activa de una ejecución anterior):**

1.  InfoPonia ejecuta PROD-ASG-STK solo por la cantidad sin cubrir, con una reserva adicional para el mismo período.
2.  Si lo cubre completo, resuelve la alerta; si no, la alerta sigue activa con la cantidad actualizada.

**4a. Otra operación tomó el stock entre la asignación y el registro:**

1.  InfoPonia vuelve a ejecutar la asignación de ese período con el stock actualizado.

**5a. InfoPonia no logra enviar una notificación:**

1.  El registro se conserva y InfoPonia reintenta el envío.

**Requisitos especiales**

  - Cada período se registra en su propia transacción.
  - El proceso se serializa con la asignación de stock, la planificación manual de cosechas y la modificación de contratos sobre los mismos lotes, partidas y detalles.
  - La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
  - Los logs de auditoría son de solo inserción e indican que el origen es InfoPonia.

**Reglas de negocio**

  - **Período a pre-reservar:** de un detalle «vigente» de un suministro «vigente»; con fecha igual o anterior a la fecha actual más los días de pre-reserva y no anterior a la fecha actual; sin superar la fecha de fin del detalle (MD-131) ni la del contrato; y sin reserva propia no liberada, o con cantidad sin cubrir (extensión 3b). Así, un día sin ejecución se recupera al siguiente. (Paso 2)
  - **Cliente inactivo:** su contrato vigente se sigue pre-reservando (regla 2 de 8.18).
  - **Asignación:** la de PROD-ASG-STK: primero cámara, después lotes, solo de los invernaderos del Vendedor del contrato (regla 7 de 8.6). (Paso 3)
  - **Cosecha:** fecha según la regla 3 de 8.11 y prioridad «media»; el Agrónomo la puede cambiar con PROD-MOD-CSC. (Postcondición b)
  - **Cobertura incompleta:** se reserva lo disponible y se reintenta cada día hasta la fecha del período. Lo que siga sin cubrir ese día se entrega con lo disponible y el faltante se trata como discrepancia o queja (regla 17 de 8.6). (Extensiones 3a y 3b)
  - **Alerta «período sin cobertura completa»:** una por período, para el Agrónomo (regla 1 de 8.9), con notificación al Vendedor del contrato. Se resuelve al cubrirse el período o al llegar su fecha. (Postcondiciones c y d)
  - **Orden de la ejecución diaria:** vencer partidas → vencer pagos → pre-reservar → planificar entregas. No se reserva stock que vence ese día, y lo reservado solo de cámara se planifica en la misma ejecución.

**Frecuencia:** una vez por día.

**Temas abiertos**

  - La hora de la ejecución diaria, a confirmar con el Jardín Botánico.

## Cómo se aplica en la ronda «Comercial 1» (D-44, D-56, D-57)

Aunque su código empieza con PROD, **el código va en `comercial`** (D-59: toca reservas): `comercial/servicios/pre_reserva.py`.

- **Paso diario 40** (D-56, punto 6; T-04): `ComercialConfig.ready()` registra
  `registrar_paso_diario("pre_reservar_suministros", "Pre-reservar suministros", 40, pre_reservar_suministros)`. El caso de uso lo llama
  «paso 3» de la ejecución diaria: es el mismo, con la numeración de D-56 (10 vencer insumos, 20 vencer partidas, 30 vencer pagos, 40
  pre-reservar, 50 planificar entregas). Se corre a mano con `python manage.py proceso_diario` (o `--solo pre_reservar_suministros`, o
  `--fecha` para simular otro día). Ningún cron job (D-56).
- **Contrato del paso** (D-56, punto 4): `pre_reservar_suministros(hoy) -> ResumenDePaso`; nunca lee la fecha por su cuenta; idempotente;
  un período, una transacción.
- **Paso 2 (qué períodos), regla «Período a pre-reservar»:**
  1. una consulta trae los detalles «vigentes» de suministros «vigentes» con algún período en `[hoy, hoy + días de pre-reserva]` y, **desde
     COM-04 (D-64 punto 8)**, también los detalles «finalizados» de suministros vigentes con `fecha_fin_detalle >= hoy`: sus
     períodos hasta la fecha de fin todavía se deben (un detalle modificado o terminado por COM-MOD-SUM queda «finalizado» en el acto);
  2. por cada uno, `calendario(detalle, desde=hoy, hasta=ventana)` (no genera los anteriores);
  3. `sin_cubrir_de_periodos(...)` (una consulta) y quedan los que tienen cantidad sin cubrir mayor que 0. «Sin reserva propia no liberada, o
     con cantidad sin cubrir» es lo mismo que «cantidad sin cubrir > 0»: un período sin reserva tiene todo sin cubrir;
  4. orden: fecha y, con la misma fecha, `id` del detalle («orden de registro»).
  Un contrato con rescisión acordada (COM-RSC-SUM) no aporta períodos posteriores a la rescisión: su calendario corta en
  `fecha_fin_detalle`. Uno con la rescisión dejada sin efecto (COM-ANL-RSC) vuelve a aportarlos desde la corrida siguiente.
- **Por cada período, en su transacción** (`docs/patrones/stock_maduro.md`, secciones 3 y 7): cuentas (el Vendedor del contrato) →
  invernaderos activos del Vendedor → variedad → lotes y partidas → `Suministro` y `DetalleSuministro`. Se releen: los dos siguen
  «vigentes», la fecha sigue en el calendario y la cantidad sin cubrir sigue siendo mayor que 0 (otra corrida o una modificación pudieron
  cambiarlas); si no, el período se saltea sin cambios. Después, `asignar(None, Periodo(detalle, fecha), sin_cubrir, fecha, "suministro")`
  (origen InfoPonia, D-27). **3b** sale solo: si ya había reservas, la nueva es «una reserva adicional» por lo que falta.
- **3a y la alerta (MD-133, D-63, punto 3):**
  - si queda cantidad sin cubrir: `asegurar_alerta_de_estado(invernadero, "comercial_periodo_sin_cobertura",
    clave=f"periodo:{detalle.id}:{fecha.isoformat()}", descripcion=…)` con el invernadero de D-63; la primera vez, además, su
    `AlertaComercial` (detalle, fecha, cantidad sin cubrir) y la notificación al Vendedor del contrato («SUM-0013: el período del 26/11 de
    Lechuga Crespa quedó sin cobertura completa. Faltan 120 plantas. InfoPonia vuelve a intentar cada día.»). Si ya estaba, solo se
    actualiza `cantidad_sin_cubrir` (postcondición c: «no se generó otra»). Descripción: «Período sin cobertura completa · {variedad} ·
    {cliente} · dd/mm».
  - si queda cubierto y había alerta: `resolver_alerta_de_estado(...)` (postcondición d).
  - **«Se resuelve al llegar su fecha»** (decisión de aplicación): el período del día se intenta por última vez en la corrida de ese día
    y su alerta sigue activa ese día (avisa a quien arma la entrega). Al empezar la corrida del día siguiente, una consulta resuelve las
    alertas de este tipo con `fecha_periodo < hoy`, cada una en su transacción y con su auditoría. Lo que faltó se entregó con lo
    disponible y se trata como faltante (regla 17 de 8.6, COM-06 y COM-07).
  - tipo registrado en `ComercialConfig.ready()`: `TipoAlerta(codigo="comercial_periodo_sin_cobertura", nombre="Período sin cobertura
    completa", destinatario=AGRONOMO_O_GERENTE, severidad=ADVERTENCIA, clase=ESTADO, origen=Origen.DETALLE_SUMINISTRO)` (D-62, D-63).
- **Enlace de la alerta (D-62):** `comercial` registra `registrar_enlace_de_alerta(("comercial_periodo_sin_cobertura",), …)`: para el
  Gerente, la ficha del suministro en su calendario (`#calendario`) con el detalle «Faltan N plantas para el dd/mm»; para el Agrónomo, que no
  abre contratos, la ficha del invernadero (enlace por omisión) con el mismo detalle.
- **Paso 5, 5a (avisos de las cosechas):** los de `asignar`, dentro de la transacción del período (D-42), sin reintento.
- **4a:** no se programa (bloqueos antes de calcular: `docs/patrones/stock_maduro.md`, sección 3).
- **\*a:** cada período en su transacción; si falla uno, se registra en el log y siguen los demás (una excepción por período no corta el
  paso). Al día siguiente el período se vuelve a tomar porque sigue con cantidad sin cubrir.
- **Cliente inactivo** (regla 2 de 8.18): no se mira el estado del cliente.
- **Auditoría (postcondición f):** un registro por período **en el que cambió algo** (reservas creadas, alerta creada o resuelta), acción
  nueva `pre_reserva_periodo`, sin usuario (origen InfoPonia, D-27). Afectados: el detalle (principal), y lo que devolvió `asignar`; en
  `datos`, la fecha del período, la cantidad sin cubrir y `alertas_creadas` / `alertas_resueltas`. Un período que se vuelve a intentar sin
  ningún cambio no audita (si no, cada día dejaría un registro igual).
- **Resumen del paso:** `ResumenDePaso(procesados=períodos intentados, creados=reservas creadas, resueltos=alertas resueltas,
  detalle="N períodos siguen sin cobertura completa")`.
- **Lo sigue el paso 50 (COM-PNF-ENT): se completa en COM-05.**
- **Concurrencia:** una pre-reserva contra una compra-venta por el mismo lote; una pre-reserva contra COM-MOD-SUM del mismo contrato; dos
  corridas del paso a la vez (ningún período queda con más reservas que su cantidad: el segundo, al releer, ve la cantidad sin cubrir en 0).

## Para más adelante

- COM-04: PROD-ASG-CAM puede cubrir con cámara un período de la ventana (MD-127); Cancelar Orden deja un período con cantidad sin cubrir que
  este paso vuelve a tomar al día siguiente. **COM-04 suma al punto 1 del paso 2 los detalles finalizados con fecha de fin pendiente** (D-64
  punto 8) y su prueba (un período de un detalle terminado que pierde su cosecha se vuelve a reservar al día siguiente).
- COM-05: el paso 50 planifica las entregas de los períodos que quedan «lista para entrega».
- Tema abierto del caso de uso: la hora de la ejecución diaria (con el cron único, al final, D-56).
