# DAT-02 · `cargar_demo`: lotes, contratos e IoT, y el comando `estado_demo`

Estado: pendiente | App: demo | Rama: feature/dat-02-lotes-contratos-iot | Ronda: —

Depende de: DAT-01 (si no está mergeada, frená)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

Rige la misma excepción y las mismas prohibiciones de DAT-01 (D-NN):

- No corrés el comando contra ninguna base real.
- No pedís ni usás la cadena de Neon.
- No imprimís la contraseña.

## Paso 0 (antes del plan): analizar el repo y marcar lo que no existe

Armá la misma tabla de DAT-01 para las secciones 12, 13 y 14 de `docs/demo/datos_de_la_demo.md`. Sumale estas filas, que son las que el
guion de la defensa necesita saber:

| Pieza | Qué buscar | Si no está |
|---|---|---|
| CMP-07, pedido automático | El paso `generar_pedidos_automaticos` registrado en `core/procesos.py` (orden 63) | `estado_demo` dice «Pedido automático: no está». No se toca nada. |
| COM-08a, cobro de suministro y mora | `comercial/servicios/cobranza.py` (o como se llame) y el paso de orden 30 | `estado_demo` dice «Cobro de suministro: no está». |
| CON-04d, asiento de la multa | El asiento en `resolver_si_corresponde` | `estado_demo` dice «Asiento de la multa: no está (la resolución sí)». |
| PRD-05, lote existente | `produccion/servicios/lotes_existentes.registrar_lote_existente` | **Frená**: sin esto no hay demo. |

## Casos de uso incluidos

Ninguno nuevo. El comando llama a:

- PRD-05 `registrar_lote_existente`;
- COM-PCT-SUM `pactar_suministro`;
- IOT-REG-SIS `registrar_sistema_iot`, `alta_hardware` y `alta_regla`.

## Leer

- Decisiones: D-NN, D-92 punto 12, D-103 (fechas de la carga inicial), D-63 (pre-reserva), D-71 (revisión IoT)
- Datos: `docs/demo/datos_de_la_demo.md`, secciones 12 a 15
- Casos de uso:
  - `docs/casos_de_uso/produccion/lote_existente.md` («Cómo se aplica»)
  - `docs/casos_de_uso/comercial/suministro.md` (COM-PCT-SUM, reglas de la ventana y 9e)
  - los de alta de sistema, hardware y reglas en `docs/casos_de_uso/iot/`
- Patrones: `docs/patrones/stock_maduro.md` (orden de asignación, fecha programada, elegibilidad)
- Servicios: `produccion/servicios/lotes_existentes.py`, `comercial/servicios/suministros.py`, `iot/servicios/sistemas.py`,
  `iot/servicios/hardware.py`, `iot/servicios/reglas.py`, `core/procesos.py`
- Referencia IoT: `docs/api/nodo/node-red/README.md` (sección 4) y `docs/api/nodo/escenarios.md`

## Límites

- Crea modelos: ninguno.
- Migraciones: ninguna.
- Permitido fuera de la app: nada.
- Dependencias nuevas: ninguna.
- Fuera de alcance:
  - El token del sistema IoT. Se registra el sistema **sin mostrar ni guardar en la salida** el token que devuelva el servicio. El estudiante
    lo regenera en la pantalla.
  - Cualquier operación en vivo de la sección 15 del archivo de datos.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **Sección 12, lotes existentes.**
   - LN-1, LN-2 y LS-1, con `DatosDeLoteExistente`. El actor es el Agrónomo de cada invernadero.
   - Tienen que cargarse **antes** de cualquier siembra normal y antes de los suministros.
   - Pruebas: `demo/tests/test_carga_lotes.py`. Se comprueba:
     - cada lote en su etapa y su sector;
     - la entrada a la etapa en su fecha;
     - la fecha máxima de cosecha de LN-1 (HOY+12) y de LS-1 (HOY+6).
2. **Sección 13, suministros.**
   - S-1 y S-2 con `pactar_suministro`. El actor es vendedor1.
   - Pruebas: `demo/tests/test_carga_suministros.py`. Se comprueba:
     - S-1 tiene reservados los períodos HOY y HOY+7 (60 + 60 de LN-1), con su cosecha «a realizar», programada para HOY la primera;
     - S-2 no tiene ninguna reserva;
     - al correr `correr_proceso_diario(hoy=HOY+1, solo="pre_reservar_suministros")`, con LN-2 pasado a Maduración en la prueba, S-2
       queda con su período HOY+8 reservado. **Esta es la prueba de que la escena en vivo va a funcionar.**
3. **Sección 14, IoT de Norte.**
   - Sistema, nodo, 5 sensores, 2 actuadores y 2 reglas, con los servicios del IoT y agronomo1 como actor.
   - Pruebas: `demo/tests/test_carga_iot.py`. Se comprueba:
     - los 7 identificadores, exactos;
     - el umbral efectivo de Norte da 16–27 °C y 60–85 %;
     - una lectura de 35 °C, pasada por `registrar_lectura` dos veces (confirmación 2), emite el comando «Encender» del ventilador.
4. **Comando `estado_demo`** (solo lectura, también detrás del candado de DAT-01, salvo la condición de «no hay cuentas»).
   Imprime, en castellano y en este orden:
   - la fecha HOY y cada fecha que el guion usa: HOY+1 para el paso 40, HOY+3 para el vencimiento del fungicida, HOY+8 para la primera
     entrega de S-2;
   - por escena del guion (`datos_de_la_demo.md`, secciones 12 a 15), si está lista:
     - LN-1 con su stock libre;
     - LN-2 en Crecimiento;
     - S-1 con la cosecha de HOY «a realizar»;
     - S-2 sin reservas;
     - el sistema IoT con su token generado o no;
     - la Solución nutritiva A por debajo del mínimo;
   - las piezas de la tabla del paso 0, con «está» o «no está»;
   - las cuentas (rol y correo; nunca la contraseña).

   Pruebas: `demo/tests/test_estado_demo.py`.

Si el tiempo apremia, lo último que se recorta es: el detalle por escena de `estado_demo` (basta con las fechas y las piezas).

## Hecho cuando

- Con el candado sustituido en las pruebas, `cargar_demo` carga las secciones 1 a 14 que existen, en una sola transacción.
- La prueba del paso 2 (pre-reserva de S-2 con `--fecha` HOY+1) pasa.
- La prueba del paso 3 (regla que enciende el ventilador) pasa.
- `estado_demo` dice qué piezas faltan sin fallar.
- Pruebas: `demo/tests/test_carga_lotes.py`, `test_carga_suministros.py`, `test_carga_iot.py`, `test_estado_demo.py`.
- Comando de pruebas: `python manage.py test demo.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`.

## Verificación a mano (la completa Claude Code al cerrar)

<!-- Pasos para el estudiante en la Shell del servicio demo:
- reiniciar la rama `vivo`;
- `migrate`;
- `cargar_demo`;
- `estado_demo`;
- qué ver en cada pantalla (Producción: los tres lotes; Comercial: S-1 con su cosecha y S-2 sin reservas; IoT: los equipos sin
  conexión todavía).

Tres listas antes: Verifiqué, Lo cubre una prueba, No pude verificar (la carga real en Neon). -->

## Cierre (la completa Claude Code al cerrar)

<!-- La tabla del paso 0 con su estado final. Si un dato del archivo chocó con una regla y el estudiante aprobó cambiarlo, el archivo de
datos se corrige en este mismo PR y se dice qué cambió, porque el guion de la defensa lo lee. -->
