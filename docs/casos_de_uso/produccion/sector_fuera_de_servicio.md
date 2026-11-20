# Casos de uso · produccion · Sector fuera de servicio

Copia para el repo del caso PROD-PNR-FDS (versión 0.1) del documento de Drive «CU extendidos», consultado el 20/11/2026. El código va en la app `produccion`.
Cotejado con pendientes_CU y con pendientes_MD hasta MD-96 y con el glosario del 15/11/2026. Se quitaron las marcas ⛔ y los `**` sueltos del export de Drive y se corrigió la numeración. No cambió ninguna regla.

Si este archivo y el documento de Drive no coinciden, avisá: no elijas en silencio.

Para nombrar las pruebas: las reglas de cada caso de uso están numeradas, así que se usa `test_regla_<numero>_<que_espera>`, y para las postcondiciones, `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Archivo de pruebas |
|---|---|---|---|
| PROD-PNR-FDS | Poner Sector Fuera de Servicio | Agrónomo | `produccion/tests/test_prod_pnr_fds.py` |

---

## PROD-PNR-FDS · Poner Sector Fuera de Servicio

Alcance: Sistema InfoPonia.
Nivel: Objetivo de usuario.
Módulo: Producción / Sectores.
Actor principal: Agrónomo.
Versión: 0.1

Personal involucrado e intereses
- Agrónomo: quiere registrar en una sola operación que un sector no puede alojar plantas (por una rotura, una plaga o
   una reparación prolongada) y resolver en ese momento qué pasa con las plantas y las órdenes que lo usaban. Quiere
   salvar todas las plantas sanas que se puedan reubicar.
- Capataz: quiere enterarse enseguida de que el sector no recibe plantas y de qué órdenes se cancelaron, para no
   trabajar sobre ellas.
- Gerente: quiere que las plantas perdidas queden valorizadas en «Pérdidas por Mermas», con su causa, y que haya
   trazabilidad completa en la auditoría y en el libro diario.
- Vendedor: quiere que la cantidad de cada lote refleje las pérdidas, porque de ella depende el stock que puede
   comprometer en contratos.
- Organización (Jardín Botánico): quiere que la capacidad de cada etapa refleje los sectores que realmente pueden
   usarse, y que ninguna orden quede planificada sobre un sector que no puede recibirla.

Relaciones con otros casos de uso
- «include» Cancelar Orden (CU-11): se ejecuta en el paso 14, una vez por cada orden a realizar con agujeros
   comprometidos en el sector.
- «extend» PROD-REG-MRM · Registrar Merma: extiende este caso de uso en el punto de extensión *Plantas sin reubicar*
   (paso 14). Se ejecuta una vez por cada lote con plantas sin reubicar.
- Lo siguen:
- Modificar Sector, para volver a poner el sector en estado «activo»;
- PROD-PNF-SMB y PROD-PNF-TRN, para volver a planificar las órdenes canceladas;
- Baja Sector, si el sector no se va a reparar. La baja exige que el sector no tenga agujeros ocupados ni
   comprometidos, y este caso de uso lo deja así.

Puntos de extensión
- *Plantas sin reubicar* (paso 14): un lote del sector tiene plantas que el Agrónomo no reubicó.

Precondiciones
a. El Agrónomo está autenticado en el Sistema.
b. El Agrónomo tiene a su cargo al menos un invernadero en estado «activo» con al menos un sector en estado «activo».
c. Existe un ejercicio contable vigente.
d. Existen las cuentas contables «Pérdidas por Mermas» y «Productos en Proceso».

Garantías mínimas
- La operación es atómica, incluidos el caso de uso que la extiende y el que incluye. Si el caso de uso se cancela o
   falla:
- el sector permanece en estado «activo»;
- no se registra ningún registro «Fuera de servicio», reubicación, ocupación, merma, cancelación de orden, asiento
   contable ni notificación;
- no queda ningún log de auditoría parcial.
- Ningún sector de destino recibe más plantas que sus agujeros libres, aun con operaciones simultáneas.
- Ningún sector de destino queda con lotes de perfiles familiares distintos.
- Un sector nunca queda fuera de servicio con agujeros ocupados ni comprometidos.
- La reubicación no cambia la etapa del lote, su fecha de entrada a la etapa ni su cantidad actual.

Garantías de éxito (Postcondiciones)
a. El sector pasó del estado «activo» a «fuera de servicio».
b. Se registró en la bitácora un registro «Fuera de servicio» con:
- la fecha efectiva indicada por el Agrónomo, la hora actual y el motivo;
- el Agrónomo como usuario responsable;
- la fecha de reactivación vacía.
Está asociado al sector y al invernadero.
c. Por cada lote con plantas reubicadas, se registró en la bitácora una reubicación con:
- la fecha efectiva, la hora actual y el Agrónomo como usuario responsable;
- una asociación al lote, al invernadero y al sector de origen.
La reubicación se compone de una ocupación de sector nueva por cada sector de destino, asociada al lote, con la
   cantidad de agujeros ocupados igual a las plantas reubicadas en ese sector.
d. La ocupación de cada lote en el sector pasó a cero agujeros ocupados y conserva su lote.
e. Por cada lote con plantas sin reubicar, se ejecutó PROD-REG-MRM · Registrar Merma, con la cantidad de plantas sin
   reubicar, la causa y la descripción, si se indicó.
f. Por cada orden de siembra o de transición en estado «a realizar» con agujeros comprometidos en el sector, se
   ejecutó Cancelar Orden (CU-11). La orden quedó en estado «cancelada», dejaron de contar como comprometidos los
   agujeros planificados en todos sus sectores, y sus reservas de insumo quedaron en estado «cancelada».
g. Como consecuencia de d, e y f, el sector quedó sin agujeros ocupados ni comprometidos.
h. Si el invernadero tiene un Capataz activo, se le envió una única notificación con el sector, la fecha efectiva, el
   motivo y las órdenes canceladas.
i. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del sector y el cambio de su estado.
j. Se creó un log de auditoría con usuario, rol, fecha, hora e identificador del registro «Fuera de servicio», de cada
   reubicación y de cada ocupación de sector creados.
k. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador y cambio de valor de cada ocupación de
   sector modificada.

Escenario principal de éxito (o Flujo Básico)
1.  El Agrónomo inicia la puesta fuera de servicio de un sector.
2.  El Sistema presenta los invernaderos activos a cargo del Agrónomo y, para cada uno, sus sectores activos
   agrupados por tipo de etapa.
3.  El Agrónomo selecciona un sector.
4.  El Sistema presenta el detalle del sector:
1.  su invernadero, su tipo de etapa y su cantidad total de agujeros;
2.  los lotes que lo ocupan, con la variedad y las plantas de cada uno en el sector;
3.  las órdenes en estado «a realizar» con agujeros comprometidos en él, con su tipo, su variedad o su lote, los
   agujeros comprometidos en el sector y su fecha programada.
4.  Propone la fecha actual como fecha efectiva.
5.  El Agrónomo indica el motivo y confirma o modifica la fecha efectiva.
6.  El Sistema verifica que el motivo esté indicado y que la fecha efectiva sea válida. Después presenta, para cada
   lote del sector, los sectores de destino elegibles con sus agujeros libres y su perfil familiar, y las plantas del
   lote que quedan sin reubicar (al comienzo, todas).
7.  El Agrónomo indica, para un lote y un sector de destino, la cantidad de plantas a reubicar en ese sector.
8.  El Sistema verifica la cantidad y presenta, para ese lote, las plantas reubicadas en cada sector de destino y las
   que quedan sin reubicar.
*El Agrónomo repite los pasos 7-8 por cada lote y sector de destino en el que reubica plantas. Si no reubica ninguna,
   no los ejecuta.*
9.  El Agrónomo indica, para un lote con plantas sin reubicar, la causa de la merma y, opcionalmente, una
   descripción.
10. El Sistema registra la causa y presenta los lotes con plantas sin reubicar que todavía no tienen causa.
*El Agrónomo repite los pasos 9-10 por cada lote con plantas sin reubicar.*
11. El Agrónomo termina la carga.
12. El Sistema verifica que todo lote con plantas sin reubicar tenga causa y presenta el resumen:
1.  el sector, el motivo y la fecha efectiva;
2.  para cada lote, las plantas que se reubican y dónde, y las que se registran como merma, con su causa y su valor;
3.  las órdenes que se cancelan.
13. El Agrónomo confirma la puesta fuera de servicio.
14. El Sistema verifica que los sectores de destino conserven los agujeros libres indicados y que no cambiaron las
   plantas de los lotes en el sector ni las órdenes con agujeros comprometidos en él. Luego, en una única
   transacción:
1.  pasa el sector a «fuera de servicio» y registra el registro «Fuera de servicio»;
2.  registra una reubicación por cada lote con plantas reubicadas, con sus ocupaciones de destino;
3.  deja en cero la ocupación de cada lote en el sector;
4.  ejecuta PROD-REG-MRM por cada lote con plantas sin reubicar;
5.  incluye Cancelar Orden (CU-11) por cada orden con agujeros comprometidos en el sector;
6.  registra la auditoría correspondiente.
15. El Sistema notifica al Capataz del invernadero que el sector quedó fuera de servicio.
16. El Sistema informa al Agrónomo lo registrado y las órdenes canceladas que deberá volver a planificar.

Extensiones (o Flujos Alternativos)
*a. En cualquier momento antes del paso 13, el Agrónomo cancela la operación:
1.  El Sistema descarta los datos ingresados sin registrar ningún cambio, y el sector permanece en estado «activo».
*b. En cualquier momento, el Sistema falla o se interrumpe la conexión:
1.  El Sistema revierte cualquier registro parcial de la operación.
2.  Al restablecerse, el Sistema informa al Agrónomo que el sector no se puso fuera de servicio.
3.  El Agrónomo reinicia el caso de uso desde el paso 1.
4a. El sector es el último sector activo de su tipo de etapa en el invernadero:
1.  Junto con el detalle del paso 4, el Sistema advierte:
1.  que el invernadero se queda sin sectores activos de esa etapa;
2.  los lotes que todavía deben pasar por ella, con la fecha en que la necesitan;
3.  las siembras a realizar de variedades que la usan.
4.  Recomienda registrar otro sector de esa etapa o cambiar el tipo de uno existente. No bloquea la operación.
2.  El caso de uso continúa en el paso 5.
6a. El motivo no está indicado:
1.  El Sistema señala que el motivo es obligatorio.
2.  El Agrónomo indica el motivo (vuelve al paso 5).
6b. La fecha efectiva es posterior a la fecha actual:
1.  El Sistema señala el error y rechaza la fecha.
2.  El Agrónomo indica otra fecha (vuelve al paso 5).
6c. La fecha efectiva es anterior a la fecha mínima:
1.  El Sistema señala el error e informa la fecha mínima y qué la determina (la última activación del sector, la
   llegada de un lote o el último registro de bitácora de un lote).
2.  El Agrónomo indica otra fecha (vuelve al paso 5).
6d. El sector no tiene plantas:
1.  El Sistema informa que no hay plantas que reubicar y que el sector solo cambiará de estado.
2.  El caso de uso continúa en el paso 11.
6e. Un lote no tiene sectores de destino elegibles:
1.  Al presentar ese lote, el Sistema informa que sus plantas no pueden reubicarse y que se registrarán como merma.
2.  El caso de uso continúa para los demás lotes. Si ninguno tiene destinos elegibles, continúa en el paso 9.
8a. La cantidad no es un número entero mayor o igual que cero:
1.  El Sistema señala el error.
2.  El Agrónomo corrige la cantidad (vuelve al paso 7).
8b. La cantidad supera los agujeros libres del sector de destino, contando las plantas que en esta misma operación ya
   se asignaron a él desde otros lotes:
1.  El Sistema señala el error e informa los agujeros libres que quedan en ese sector.
2.  El Agrónomo corrige la cantidad (vuelve al paso 7).
8c. El total reubicado del lote supera sus plantas en el sector:
1.  El Sistema señala el error e informa las plantas del lote en el sector.
2.  El Agrónomo corrige la cantidad (vuelve al paso 7).
8d. El Agrónomo reubicó todas las plantas de todos los lotes:
1.  El Sistema informa que no se registrará ninguna merma.
2.  El caso de uso continúa en el paso 11.
12a. Un lote con plantas sin reubicar no tiene causa:
1.  El Sistema señala los lotes sin causa.
2.  El Agrónomo indica la causa (vuelve al paso 9).
12b. El Agrónomo quiere corregir un dato del resumen:
1.  El Agrónomo indica el dato que quiere corregir, y el caso de uso vuelve al paso donde se ingresó (5, 7 o 9).
2.  El Agrónomo vuelve a terminar la carga (paso 11), y el Sistema repite las verificaciones del paso 12.
14a. Entre la carga y la confirmación, otra operación cambió los agujeros libres de un sector de destino, las plantas
   de un lote en el sector o las órdenes con agujeros comprometidos en él, y lo indicado ya no es válido:
1.  El Sistema no registra ningún cambio, conserva los datos ingresados e informa qué cambió.
2.  El caso de uso vuelve al paso 6 con los valores vigentes.
15a. El invernadero no tiene un Capataz activo:
1.  El Sistema no envía la notificación. La alerta «invernadero sin Capataz activo» ya existe (regla 3 de 8.22).
2.  El caso de uso continúa en el paso 16.
15b. El Sistema no logra entregar la notificación:
1.  La puesta fuera de servicio permanece registrada.
2.  El Sistema reintenta el envío.
Ejecución del caso de uso que lo extiende
PROD-REG-MRM · Registrar Merma, en el punto *Plantas sin reubicar*:
El caso de uso recibe el lote, las plantas sin reubicar (las calcula el Sistema), la causa y la descripción, si se
   indicó, ya verificadas en los pasos 6 a 12 de este caso de uso. Se comporta igual que desde Concretar Transición,
   con estas diferencias:
- la merma se registra en la etapa actual del lote, asociada al sector que se pone fuera de servicio;
- en sus postcondiciones a y d, la fecha es la fecha efectiva, que puede ser anterior a la fecha actual, y la hora es
   la actual;
- no se aplica su postcondición c: los agujeros del sector los libera este caso de uso al dejar en cero las
   ocupaciones (postcondición d);
- su extensión 10a evalúa las plantas comprometidas sin contar las órdenes que se cancelan en esta operación, y su
   extensión 10b (umbral de merma) se aplica normalmente;
- se omite su paso 11: el aviso al actor es el del paso 16 de este caso de uso.

Requisitos especiales
- Tras cada dato ingresado por el Agrónomo (pasos 5, 7 y 9), la pantalla se actualiza con las verificaciones y los
   valores calculados en no más de 1 segundo.
- El paso 14, incluidos los casos de uso incluidos y extensores, se ejecuta como una única transacción.
- El control de concurrencia impide que dos operaciones simultáneas superen los agujeros libres de un sector de
   destino o dejen a un lote con cantidad negativa.
- Solo el Agrónomo a cargo del invernadero accede a sus sectores.
- La fecha actual se toma en la zona horaria del invernadero (Argentina, UTC−03:00).
- Los montos de los asientos contables se expresan en pesos argentinos, con dos decimales.
- Los logs de auditoría son de solo inserción e indican que el origen de la operación es un usuario.
- El caso de uso es accesible desde navegadores web modernos (Chrome, Firefox, Edge) sin instalación adicional.

Reglas de negocio
- Quién lo ejecuta: solo el Agrónomo a cargo del invernadero del sector. (Paso 2)
- Sector que se puede poner fuera de servicio: un sector en estado «activo». Un sector fuera de servicio solo puede
   volver a «activo» (con Modificar Sector) o darse de baja. (Pasos 2 y 3)
- Fecha efectiva válida: no puede ser posterior a la fecha actual ni anterior a la fecha mínima. La hora es siempre la
   actual. (Paso 6)
- Fecha mínima: la más tardía entre:
- la fecha en que el sector quedó activo por última vez (su alta o su última reactivación);
- la fecha en que llegó al sector cada lote que lo ocupa (por su siembra, su transición o una reubicación);
- el último registro de bitácora de esos lotes.
- Así la merma y la reubicación nunca quedan con una fecha en la que el lote no estaba en el sector. (Paso 6,
   extensión 6c)
- Sector de destino elegible: un sector del mismo invernadero y del mismo tipo de etapa, en estado «activo»,
   compatible por perfil familiar y con agujeros libres. Todos los lotes de un sector comparten perfil familiar, así
   que reubicar varios lotes en un mismo destino no mezcla perfiles. (Paso 6)
- Agujeros libres de un sector: su total de agujeros menos los ocupados y los comprometidos. Se calculan, no se
   guardan. (Pasos 6 y 8)
- Cantidad a reubicar válida: un número entero mayor o igual que cero. No supera los agujeros libres del destino
   (contando lo asignado en la misma operación), y el total del lote no supera sus plantas en el sector. Cada planta
   ocupa un agujero. (Paso 8)
- Plantas sin reubicar: las plantas del lote en el sector menos las reubicadas. Se registran como merma: el sector no
   puede quedar con plantas. (Pasos 8 y 14)
- Causa de la merma: una por lote, elegida de las causas de un lote en pie, sin «descarte por selección» (que solo
   corresponde a la selección de plantines). Suma a la merma acumulada para el umbral. (Paso 9)
- Valor de la merma: plantas perdidas × costo por planta del lote en ese momento (saldo del lote ÷ plantas actuales).
   (Paso 12)
- Reubicación:
- un registro de bitácora por lote;
- se compone de una ocupación de sector nueva por cada destino;
- la ocupación de origen pasa a cero y conserva su lote;
- la etapa del lote y su fecha de entrada a la etapa no cambian.
- Toda ocupación de sector pertenece exactamente a una siembra, una transición o una reubicación (restricción C9).
   (Paso 14)
- Órdenes afectadas: las de siembra y transición en estado «a realizar» con agujeros planificados en el sector. Se
   cancelan todas automáticamente con Cancelar Orden. Se libera todo lo que reservaban, también en sus otros sectores,
   y deben volver a planificarse. (Pasos 4 y 14)
- Último sector de su tipo: se advierte pero no se bloquea. (Extensión 4a)
- Notificación al Capataz: una sola, con el sector y todas las órdenes canceladas, y no una por orden. (Paso 15)
- Un sector fuera de servicio:
- no recibe plantas;
- no puede elegirse al planificar una siembra o una transición;
- sigue contando para los niveles 1 y 2 de la capacidad y para el ritmo sostenible. (Consecuencia del estado)
- Fin del período fuera de servicio: al volver el sector a «activo» con Modificar Sector, se carga la fecha de
   reactivación del registro «Fuera de servicio». (Fuera de este caso de uso)
- Hardware: poner un sector fuera de servicio no cambia el estado del hardware asociado. (Ver temas abiertos)

Lista de tecnología y variaciones de datos
- 5a. La fecha efectiva se ingresa con formato dd/mm/aaaa, mediante calendario o teclado. El motivo es texto libre.
- 7a. Las cantidades se expresan en plantas, como números enteros.
- 9a. La causa se elige de una lista. La descripción es texto libre opcional.
- 15a. La notificación al Capataz se entrega dentro del Sistema y puede, además, enviarse por correo electrónico.

Frecuencia
Baja e irregular, ante una rotura, una plaga o una reparación prolongada. A confirmar con el Jardín Botánico.

Temas abiertos
- Hardware del sector (bloque IoT): los sensores de un sector fuera de servicio pueden seguir generando alertas de
   telemetría sobre un sector sin plantas. Hay que decidir si esas alertas se suspenden mientras el sector está fuera
   de servicio.
- Reacomodar lotes en cualquier momento: la reubicación solo existe dentro de este caso de uso. Moverlos libremente
   queda como mejora futura.

---

## Cómo se aplica en la ronda «Producción 1» (D-44, D-45, D-50, D-51)

### Lo que NO se hace en la ronda (D-45)

- **Asientos contables** de las mermas (precondiciones c y d: ejercicio y cuentas «Pérdidas por Mermas» y «Productos en Proceso»): no se verifican ni se crean. El costo de las plantas perdidas **sí baja** del costo del lote.
- **Movimiento de stock «salida por merma»** de PROD-REG-MRM: no existe en la ronda.
- Cancelar Orden se ejecuta **solo para siembras y transiciones** (no hay otras órdenes). Sin cosechas, no hay condición 1 de plantas comprometidas.
- El **hardware** del sector no se toca (tema abierto del CU; lo decide el módulo IoT).
- Extensión 15b («no logra entregar»): no aplica (D-42).

### Qué hace cada parte

| Parte | Código |
|---|---|
| Poner fuera de servicio | `produccion/servicios/sectores_fuera_de_servicio.py`: `sectores_para_fuera_de_servicio(actor)`, `detalle_de_sector(actor, sector_id)`, `fecha_minima_fuera_de_servicio(sector)`, `destinos_elegibles(sector, lotes)`, `resumen_de_fuera_de_servicio(actor, datos)`, `poner_fuera_de_servicio(actor, datos)` |
| Cambio de estado del sector | `maestros/servicios/sectores.py`: `pasar_a_fuera_de_servicio(sector)` (nueva en PRD-04, D-51 punto 7) |
| Cierre del registro «Fuera de servicio» | `produccion`: se registra en `registrar_efecto_de_vuelta_a_servicio` (MOD-SCT), en el nuevo `registrar_efecto_de_baja_de_sector` (BAJ-SCT) y en `registrar_efecto_de_baja` (baja del invernadero) |
| Merma por lote sin reubicar | `mermas.aplicar_merma` (PRD-02), con la **etapa actual** y los sectores = el sector que sale de servicio |
| Cancelación de órdenes | `ordenes.cancelar_orden_incluida(actor, orden, motivo, avisar=False)` (PRD-01) |

### Decisiones de aplicación

- **Quién**: el Agrónomo a cargo del invernadero del sector (el Capataz y el Gerente no). El sector debe estar «activo». Sin sectores activos el caso informa (precondición b).
- **Fecha efectiva**: entre la **fecha mínima** y hoy. Fecha mínima = la mayor entre: (a) la última activación del sector, que `SectorProduccion` no guarda y se **deriva** de la fecha del último registro de auditoría `alta_sector` o `reactivacion_sector` que lo nombra y del `fecha_fin` del último registro «Fuera de servicio» (D-51 punto 6); (b) la fecha en que llegó cada lote que lo ocupa (`siembra.fecha_siembra`, `transicion.fecha_transicion` o `fecha_bitacora` de la reubicación de la ocupación vigente); (c) el último registro de bitácora de esos lotes. Extensión 6c: informa de dónde sale.
- **Motivo** obligatorio, hasta 300 caracteres.
- **Destinos elegibles** de un lote (`destinos_elegibles`): sector del mismo invernadero, del **mismo tipo de etapa**, «activo», distinto del origen, con **perfil familiar compatible** (el del lote; o sin plantas ni órdenes) y con agujeros libres (`agujeros_de`: total − ocupados − comprometidos; **no se cuentan como libres los comprometidos por las órdenes que esta misma operación cancela**, para no depender del orden). Al asignar varios lotes al mismo destino se descuenta lo ya asignado en la operación (8b).
- **Reubicación**: por lote con plantas reubicadas, una `Reubicacion` (bitácora tipo `reubicacion`, lote, invernadero, sector de origen, fecha efectiva, hora actual, `descripcion_evento` «Reubicación de 40 plantas del lote L-3 desde Germinación 2 a Germinación 1 y 3») con una `OcupacionSector` nueva por destino (`reubicacion`, `lote`, `cant_agujeros_planificados = cant_agujeros_ocupados`). La ocupación de origen queda en 0 y conserva el lote. **No cambia la etapa del lote ni su fecha de entrada.** `Lote.cantidad_actual` no cambia.
- **Plantas sin reubicar**: se registran como merma con `aplicar_merma(lote, n, causa, descripcion, fecha_efectiva, actor, sector_ids=[sector])`. La causa es una por lote, de las de un lote en pie **sin «descarte por selección»**. La merma **suma** a la acumulada (umbral normal). No se evalúan como comprometidas las órdenes que se cancelan en esta misma operación (`ordenes_excluidas`). **No** libera agujeros por su cuenta: los libera la puesta de la ocupación en cero.
- **Órdenes**: las siembras y transiciones «a realizar» con agujeros comprometidos en el sector se cancelan **todas** con `cancelar_orden_incluida`, con el motivo «Sector {nombre} fuera de servicio: {motivo}». Se libera todo lo que reservaban, también en otros sectores. Las notificaciones por orden **se omiten** (`avisar=False`): el Capataz recibe **una sola** notificación con el sector, la fecha efectiva, el motivo y las órdenes canceladas (paso 15; extensión 15a: sin Capataz activo no se envía).
- **Sector**: `maestros.servicios.sectores.pasar_a_fuera_de_servicio(sector)` cambia `estado_sector` a «fuera de servicio». Después, el sector queda sin agujeros ocupados ni comprometidos (postcondición g, prueba de invariantes). Sigue contando para la capacidad (niveles 1 y 2 y ritmo sostenible) pero ya no lo ofrece `bloquear_sectores`.
- **Registro «Fuera de servicio»** (`FueraDeServicio`): motivo, fecha efectiva, `fecha_fin` nula, sector, responsable el Agrónomo. Uno abierto por sector como máximo.
- **Último sector de su tipo (4a)**: advertencia que no bloquea; reutiliza `maestros.servicios.sectores.avisos_de_cambio_de_tipo` (el mismo cálculo de PROD-MOD-SCT).
- **Sector sin plantas (6d)**: solo cambia de estado; si además no tiene órdenes, no hay reubicaciones ni mermas ni cancelaciones.
- **Concurrencia (14a)**: se bloquea y se relee; si cambiaron los agujeros libres de un destino, las plantas de un lote en el sector o las órdenes con agujeros comprometidos en él → `cambio_simultaneo` con qué cambió, y el caso vuelve al paso 6 con los valores vigentes.
- **Bloqueos**: cuentas → invernadero → **variedades** de los lotes y órdenes afectados (id) → **sectores** (el de origen, los destinos y los de las órdenes a cancelar, id, sin repetir) → insumos de las reservas de las órdenes → lotes afectados (id) → órdenes, ocupaciones y reservas. El sector de origen se bloquea **antes** de pasarlo a «fuera de servicio» (`bloquear_sectores` solo acepta activos).
- **Auditoría**: un registro `fuera_de_servicio_sector` con el sector (estado antes → después), el registro «Fuera de servicio», cada reubicación y ocupación creada, cada ocupación modificada, las mermas con sus bitácoras y alertas, las órdenes canceladas con sus reservas, y los lotes (cantidad y costo, antes → después).
- **Notificación**: una al Capataz, dentro de la transacción.

### Vuelta a servicio y baja (MAE-03)

- `registrar_efecto_de_vuelta_a_servicio(actor, sector)` (ya declarado en MAE-03): cierra el registro abierto con `fecha_fin = hoy` y escribe una bitácora `otro_evento` con el sector («El sector X vuelve a estar activo. Estuvo fuera de servicio desde dd/mm/aaaa hasta dd/mm/aaaa, N días»), responsable el actor. Es una decisión de aplicación: el CU de MAE-03 dice «se registró en la bitácora» y la lista de tipos de PROD-CNS-BIT no tiene uno propio.
- `registrar_efecto_de_baja_de_sector(funcion)` (**punto nuevo de `maestros`**, PRD-04): en PROD-BAJ-SCT, postcondición b, cierra el registro abierto con `fecha_fin = hoy`. La baja del invernadero (`registrar_efecto_de_baja`) hace lo mismo con los sectores del invernadero (PRD-04 lo registra; en el lote 4 se había dicho que `produccion` no registraba nada ahí).

### Pantallas

Prototipo: `VIEWS.fs`, `fsCalc`, `ultimoAviso`. Es la pantalla más larga del bloque: sector → detalle y fecha/motivo → por lote, destinos y cantidades → causa de la merma por lote → resumen → confirmar. Se entra desde la ficha del sector y desde el aviso de la baja del sector (MAE-03). Formulario deshabilitado con su motivo si no hay sectores activos. Sin JavaScript funciona igual.

### Pruebas

`produccion/tests/test_prod_pnr_fds.py` (una por regla y por postcondición a a k; sector vacío; con un lote y destinos; con lote sin destinos elegibles; con varios lotes en el mismo destino y que no se pasa de los libres; reubicación parcial con merma y causa; todas reubicadas sin merma; con órdenes a cancelar y que se liberan sus reservas y agujeros; fecha mínima en cada caso; último sector de su tipo; sin Capataz activo; la etapa y la fecha de entrada del lote no cambian; el sector queda sin ocupados ni comprometidos; un error no deja nada creado), `test_fds_registrantes.py` (vuelta a servicio, baja del sector y baja del invernadero cierran el registro) y `test_fds_concurrencia.py` (`@tag("concurrencia")`: dos puestas fuera de servicio del mismo sector; contra una planificación sobre el sector; contra una merma en el sector; dos reubicaciones sobre el último agujero del mismo destino).
