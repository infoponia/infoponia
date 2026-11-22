# Casos de uso · iot · Cancelar comando

Copia para el repo del caso IOT-CNL-CMD (v0.1, de alto nivel) de «CU extendidos» (sección IoT, copiado el 22/11/2026). Cotejado con
`docs/modelo/iot.md` y con D-70 a D-78. **El código va en la app `iot`.** Si este archivo y Drive no coinciden, avisá. Para nombrar las
pruebas: `test_regla_<numero>_<que_espera>` y `test_post_<letra>_<que_espera>`.

## Índice

| Código | Caso de uso | Actores | Tarea | Archivo de pruebas |
|---|---|---|---|---|
| IOT-CNL-CMD | Cancelar comando | Agrónomo o Gerente (alcance) | IOT-05 | `iot/tests/test_iot_cnl_cmd.py` |

## IOT-CNL-CMD · Cancelar Comando

**Actores:** Agrónomo y Gerente, cada uno con su alcance (regla 1).

**Tipo:** secundario, esencial.

**Versión:** 0.1

**Objetivo:** cancelar un comando pendiente que ya no se quiere ejecutar o que quedó trabado, por ejemplo porque el nodo central no se comunica, para liberar al actuador y poder enviarle otro comando.

**Precondición:**

a. El actor está identificado en el Sistema con una cuenta activa de Agrónomo o de Gerente.

b. El comando está en estado «pendiente».

c. El comando no está esperando la respuesta de un intento en curso (regla 2).

**Postcondición:**

a. El comando quedó en estado «cancelado».

b. Se creó un registro de bitácora del invernadero de tipo «comando», sin lote, con el actuador, la acción y la cancelación, asociado al Agrónomo si lo canceló un Agrónomo.

c. Se creó un log de auditoría con usuario, rol, fecha, hora, identificador del comando y el cambio de estado.

**Reglas:**

1. Alcance: el mismo que en la regla 1 de IOT-DSC-SIS.

2. Un comando pendiente se puede cancelar mientras el nodo central no lo retiró, o cuando su último intento ya venció sin respuesta. No se cancela mientras el nodo puede estar ejecutándolo, es decir, desde que lo retira hasta que pasa el intervalo de reintento de la Configuración Operativa: el Sistema informa cuánto falta para poder cancelarlo.

3. Se cancelan tanto los comandos manuales como los que emitió InfoPonia por una regla de actuación.

4. Un comando cancelado no se reintenta y no genera alertas ni órdenes de mantenimiento. Si después llega un resultado del nodo para ese comando, se ignora (IOT-RSV-CMD).

5. Si al cancelar, el nodo acaba de retirar el comando, no se cancela y el Sistema lo informa.

6. Se inicia desde la ficha del actuador (IOT-CNS-HDW), desde el panel de monitoreo (IOT-CNS-LEC) o desde Emitir Comando, cuando el actuador elegido tiene un comando pendiente.

## Cómo se aplica en la ronda «IoT 1» (D-78, punto 6)

Tarea: **IOT-05**.

- `cancelar_comando(actor, comando_id, ahora)` en `iot/servicios/comandos.py`: bloquea invernadero → sistema → actuador → comando, vuelve a
  verificar el alcance (regla 1), que siga `pendiente` (precondición b) y que sea **cancelable** (regla 2; D-78, punto 6). Pasa a
  `cancelado` con `resuelto_en = ahora` y crea el `RegistroComando` `cancelado` con el responsable (postcondición b). Auditoría:
  `cancelacion_comando`.
- **Regla 2 en pantalla.** Si no se puede cancelar todavía, el botón «Cancelar» está deshabilitado con «El nodo puede estar ejecutándolo:
  podés cancelarlo en {n} s.».
- **Regla 5.** Si el retiro tomó el comando entre la pantalla y la confirmación, el servicio lo ve bajo el bloqueo y responde «El nodo acaba
  de retirar el comando: no se canceló. Podés cancelarlo cuando venza el intento (en {n} s).».
- **Ventana de confirmación** (`ccan:<id>` del prototipo): «Cancelar {CMD-id}: {acción} sobre {actuador}. El nodo no lo va a recibir y no se
  reintenta.».
- **`cancelar_comando_incluido(comando, motivo, responsable=None)`**: la misma cancelación sin la verificación de alcance ni la auditoría
  propia. Es para quien cancela como parte de otro caso de uso: 2c de IOT-RSV-CMD (IOT-05) y la desactivación y la baja del sistema y del
  hardware (IOT-06), que auditan lo suyo.
- **Regla 4.** Un cancelado no se reintenta. Su resultado tardío es `ya_resuelto` (`resolver_comando.md`).
- **Regla 6.** «Cancelar» está en la lista de «Comandos», en el panel (la fila del actuador con comando pendiente) y en la ficha del actuador.

## Pantallas

| Pantalla | Función en el prototipo | Tarea |
|---|---|---|
| Confirmar la cancelación | `modalHtml` (`ccan:<id>`) | IOT-05 |

## Solo prototipo

Los de `docs/prototipos/iot/README.md`.
