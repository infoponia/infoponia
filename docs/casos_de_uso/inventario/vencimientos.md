# Casos de uso · inventario · Revisar vencimientos de insumos

Copia para el repo del caso CMP-REV-VNC (versión 0.2) del documento de Drive «CU extendidos»,
consultados el 19/11/2026. Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario.

Es un caso de uso breve del propio Sistema. **El código va en la app `inventario`** (D-37); el archivo de pruebas es
`inventario/tests/test_cmp_rev_vnc.py`.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| CMP-REV-VNC | Revisar Vencimientos de Insumos | InfoPonia (el Sistema) | `inventario/tests/test_cmp_rev_vnc.py` |

---

## CMP-REV-VNC · Revisar Vencimientos de Insumos

Actores: InfoPonia.
Tipo: secundario, esencial.
Versión: 0.2

Objetivo: alertar al Agrónomo de los lotes de insumo que están por vencer o ya vencieron, para que los use a tiempo o dé de baja lo vencido.

**Precondición:**
a. Llegó el momento de la revisión diaria.
b. Existe al menos un lote de insumo con fecha de vencimiento y cantidad disponible mayor que cero, de un insumo
   activo en un invernadero activo.

**Postcondición:**
a. Por cada lote por vencer que no tenía alerta activa, se generó una alerta «insumo por vencer» para el Agrónomo del
   invernadero.
b. Por cada lote vencido que no tenía alerta activa de vencido, se generó una alerta «insumo vencido» para ese
   Agrónomo. La alerta «por vencer» del mismo lote pasó a resuelta.
c. Las alertas de vencimiento de lotes cuya cantidad disponible llegó a cero pasaron a resueltas.
d. Por cada alerta generada, se creó un log de auditoría con origen «sistema», fecha, hora e identificador de la
   alerta.
e. Si algún insumo con lotes vencidos quedó bajo el mínimo y no tenía alerta activa de insumo bajo el mínimo, se
   generó esa alerta para el Agrónomo del invernadero.

**Reglas:**
1. La revisión corre una vez por día, de madrugada, con la fecha de la zona horaria del invernadero (UTC−03:00). Si un
   día no corrió, la próxima revisión alerta lo que corresponda a esa fecha, sin repetir lo ya alertado.
2. Se revisan los lotes de insumo con fecha de vencimiento y cantidad disponible mayor que cero. El faltante sin lote
   no se revisa, porque no vence.
3. Un lote está por vencer cuando faltan entre 0 y diasAvisoVencimiento días para su vencimiento (valor inicial 15,
   MD-89). El día del vencimiento el lote todavía puede usarse.
4. Un lote está vencido desde el día siguiente a su fecha de vencimiento.
5. Hay a lo sumo una alerta activa por lote y por tipo.
6. La alerta va solo al Agrónomo del invernadero. Si el invernadero no tiene Agrónomo, no se genera ninguna alerta y
   el lote se revisa de nuevo al día siguiente. Cuando se asigna un Agrónomo, se genera la que corresponda.
7. Una alerta de vencimiento se resuelve sola cuando la cantidad disponible del lote llega a cero, por consumo o por
   un ajuste de stock.
8. Esta revisión no modifica el stock ni descarta lo vencido: el Agrónomo lo da de baja con CMP-AJT-STK, motivo
   «vencimiento».
9. No genera registro de bitácora ni asiento contable.
10. Si el Gerente cambia diasAvisoVencimiento, el nuevo valor rige desde la próxima revisión.
11. Como un lote vencido deja de contar en el stock libre (CMP-RLZ-PED), la revisión también reevalúa la alerta de
   insumo bajo el mínimo de cada insumo que tiene algún lote vencido con cantidad disponible mayor que cero. Si el
   stock mínimo es mayor que cero, el insumo está bajo el mínimo (stock libre + cantidad en tránsito < stock mínimo,
   con la fecha de hoy) y no tiene alerta activa de ese tipo, se genera la alerta para el Agrónomo, con las mismas
   condiciones de la regla 6. Esta revisión no resuelve esa alerta: se resuelve al registrar la recepción (reglas 11 y
   12 de 8.15 del modelo).

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45)

Tarea: **INV-02**. Es un caso de uso del propio Sistema (actor «InfoPonia»): sin pantalla.

- **Cómo corre (decidido el 19/11/2026).** Un comando de Django, `python manage.py revisar_vencimientos` (el nombre es propuesta
  de esta tarea), que se ejecuta una vez por día como **cron job de Render** (servicio aparte, con el mismo repositorio, las mismas
  variables de entorno y el comando de arranque `python manage.py revisar_vencimientos`). Render evalúa la agenda en **UTC**: para
  «de madrugada» en Argentina (UTC−03:00), `0 6 * * *` corre a las 03:00 locales. El comando tiene que terminar solo, porque
  Render cobra por el tiempo que corre y tiene un mínimo mensual de 1 dólar por cada cron job (verificado en la documentación
  de Render el 19/11/2026; revisalo antes de crearlo). Crear el cron job en Render es un paso manual, fuera del código, que está
  en la verificación a mano de INV-02.
- **El comando no tiene lógica.** Llama a `inventario.servicios.vencimientos.revisar_vencimientos(hoy=None)`. Sin `hoy`, usa la
  fecha de `America/Argentina/Buenos_Aires` (regla 1). Con `hoy`, las pruebas simulan cualquier día; el comando acepta
  `--fecha AAAA-MM-DD` solo para correrlo a mano en el servidor.
- **Idempotente y con recuperación.** Correrlo dos veces el mismo día no duplica nada (regla 5: a lo sumo una alerta activa por
  lote y tipo). Si un día no corrió, el siguiente alerta lo que corresponda a esa fecha, sin repetir (regla 1): la lógica
  mira el estado de cada lote contra `hoy`, no el día anterior.
- **Qué revisa** (reglas 2 a 4): lotes con fecha de vencimiento y cantidad disponible mayor que cero, de un `InsumoInvernadero`
  activo cuyo invernadero está activo. El faltante sin lote no. Por vencer: faltan entre 0 y `dias_aviso_vencimiento` días
  (`ConfiguracionOperativa`, leída una sola vez al empezar la corrida: el cambio rige desde la próxima, regla 10). Vencido:
  desde el día siguiente a su fecha.
- **Alertas.** Tipos de estado de `inventario`, `inv_insumo_por_vencer` y `inv_insumo_vencido`, con clave `lote:<id>`, la
  descripción pedida por el modelo (insumo, lote, cantidad disponible y fecha de vencimiento: `descripcion_alerta`) y la
  severidad que define `docs/api/extensiones_de_inventario.md`. El lote que pasa de «por vencer» a «vencido» resuelve la primera
  y crea la segunda en la misma transacción. Un lote que llegó a cero ya no se revisa: la corrida resuelve las alertas de
  vencimiento de los lotes agotados que quedaran activas (postcondición c; normalmente ya las resolvió el consumo o el ajuste).
- **Sin Agrónomo (regla 6).** Si el invernadero no tiene Agrónomo activo, **no se genera la alerta** y el lote se revisa de nuevo
  al día siguiente; al asignar un Agrónomo, la próxima corrida la genera. Esto difiere de la API de alertas (D-41: sin Agrónomo,
  va al Gerente): para estos dos tipos, la revisión se salta el lote antes de llamar a la API. Manda el CU. Para
  «stock inconsistente» y «bajo el mínimo» creados por una operación de usuario, vale la API de alertas. Registrado en
  `docs/temas_abiertos.md`.
- **Bajo el mínimo (regla 11).** Para cada `InsumoInvernadero` con algún lote vencido con cantidad mayor que cero, mínimo mayor
  que cero y sin alerta activa del tipo: si libre + tránsito < mínimo con la fecha de hoy, se crea (con las condiciones de la
  regla 6). **Esta corrida no la resuelve.**
- **Qué no hace.** No modifica stock ni descarta lo vencido (regla 8); no escribe bitácora ni asiento (regla 9). No reevalúa la
  alerta «stock inconsistente» cuando un lote vence (el CU no lo pide): queda en `docs/temas_abiertos.md`.
- **Auditoría (postcondición d).** Un registro por alerta creada, acción `alerta_de_vencimiento`, usuario `None` (origen «sistema», D-27),
  con el invernadero y el insumo como afectados y la alerta en `datos` (`alertas_creadas`).
- **Bloqueos y concurrencia.** Por cada invernadero con lotes a revisar (en orden de id): una transacción propia que toma el
  invernadero (`bloquear_invernadero_para_alertas`) y vuelve a leer sus lotes antes de decidir. Una falla en un invernadero se
  registra en el log y no impide revisar los demás; el comando termina con código distinto de cero si hubo fallas, para que
  Render lo marque. Es seguro correrlo mientras alguien consume o ajusta: el consumo y el ajuste toman el mismo invernadero.

