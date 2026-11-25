# DAT-02 · `cargar_demo`: lotes, contratos e IoT, y el comando `estado_demo`

Estado: hecha, a verificar a mano | App: demo | Rama: feature/dat-02-lotes-contratos-iot | Ronda: —

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

**Qué es esto:** no es crear datos a mano: es correr los comandos en la Shell del servicio demo de Render y revisar la salida y las pantallas.
Sigue la guía `PREPARACION_Render_y_Neon.md` (la tienen ustedes, fuera del repo). DAT-01 y DAT-02 van en el mismo PR: esta verificación
cubre las dos y reemplaza a la de DAT-01 en lo que se repite.

**Verifiqué** (Claude Code, solo en la base de pruebas `test_…`; los comandos no se corrieron contra ninguna base real, ni se usó Neon):
- La carga de las 14 secciones en una sola transacción (`test_comando.py`, `test_carga_*.py`): 14 líneas «Cargado:», ninguna «Salteado:».
- La escena de la pre-reserva (`test_carga_suministros.py`): con LN-2 pasada a Maduración (planificada por agronomo1, concretada por
  capataz1, con fecha de hoy), `correr_proceso_diario(hoy=HOY+1, solo="pre_reservar_suministros")` reserva las 40 plantas de S-2 para
  HOY+8 y crea la cosecha «a realizar» programada para HOY+5. Sin la transición, el período queda sin cubrir y aparece la alerta
  «Período sin cobertura completa» (el otro resultado válido).
- La escena del ventilador (`test_carga_iot.py`): dos lecturas de 35 °C sobre `norte/sectorA/temperatura` emiten el comando «Encender»
  (pendiente) del ventilador; con una sola no se emite nada, y una lectura de 24 °C no emite nada.
- `estado_demo` (`test_estado_demo.py`): detrás del candado, de solo lectura, sin imprimir la contraseña ni el token.
- Migraciones: ninguna (no hay `sqlmigrate`).

**Lo cubre una prueba:** los valores de las secciones 12 a 14 (lotes, fechas máximas HOY+12 y HOY+6, los 7 identificadores exactos, el
umbral de Norte 16–27 °C y 60–85 %, las reglas), S-1 con HOY y HOY+7 reservados (60 + 60 de LN-1) y su cosecha de HOY «a realizar», S-2
sin reservas, que el token no sale en ninguna línea, y que `estado_demo` no escribe nada.

**No pude verificar:** la carga real en Neon y en Render; que lleguen a la casilla los dos comprobantes por correo de S-1 y S-2 (en las pruebas
el correo no está configurado); el ventilador de punta a punta con Node-RED (las pruebas llegan hasta el comando «pendiente»: que el nodo lo
tome y lo ejecute depende de Node-RED y del token que regeneran ustedes); y cómo se ve todo en un navegador (no abro navegadores, D-96).

### Antes de empezar

Las variables de entorno y la rama de Neon son las de DAT-01 (`INFOPONIA_DEMO=1`, `INFOPONIA_DEMO_CONTRASENA`, `INFOPONIA_DEMO_CORREO`; base
`infoponia_demo` en la rama `vivo` recién reiniciada desde `main`). **Los valores no se escriben en ningún archivo del repo.** Para que salgan
los comprobantes de los contratos, el servicio demo tiene que tener configurado el correo del sistema.

### Pasos

1. **Migrar y cargar.** En la Shell: `python manage.py migrate` y después `python manage.py cargar_demo`. Tiene que mostrar catorce líneas
   «Cargado: N. <sección> (…)», de la 1 a la 14, ninguna «Salteado:» y ningún «Aviso:»; la lista de diez cuentas (rol y correo); y al final
   «Carga terminada. Ahora corré estado_demo…». **Ni la contraseña ni ningún token tienen que aparecer.** Tarda unos segundos más que en DAT-01.
2. **Correos.** En la casilla de Gmail tienen que llegar los comprobantes de S-1 (a `<base>+cliente1@gmail.com`) y de S-2
   (a `<base>+cliente2@gmail.com`). Si el correo no está configurado, no llega nada y los contratos quedan «pendiente de envío»: no es un error.
3. **Estado.** `python manage.py estado_demo`. Tiene que mostrar:
   - las fechas HOY, HOY+1, HOY+3 y HOY+8;
   - seis escenas «[lista]»: LN-1 con **180 plantas libres de 300** (S-1 reserva 120), LN-2 en Crecimiento, S-1 con 2 períodos reservados y su
     primera cosecha «a realizar», S-2 sin reservas, el sistema IoT con «token generado el …» (sin el valor) y la Solución nutritiva A
     «12 contra un mínimo de 20»;
   - las piezas: Lote existente (PRD-05) **está**, Pedido automático (CMP-07) **está**, Cobro de suministro (COM-08a) **está** y
     Asiento de la multa (CON-04d) **no está (la resolución sí)**;
   - las diez cuentas.
4. **Producción.** Entrá como agronomo1: tienen que estar LN-1 (Lechuga Criolla, 300 plantas, Maduración N1) y LN-2 (Lechuga Morada, 200,
   Crecimiento N1); como agronomo2, LS-1 (Albahaca Genovesa, 150, Maduración S1). Las fechas máximas de cosecha: LN-1 HOY+12 y LS-1 HOY+6.
5. **Comercial.** Entrá como vendedor1: S-1 (Súper Del Parque) con sus períodos HOY y HOY+7 reservados y la cosecha de HOY «a realizar»;
   S-2 (Restaurante El Mensú) vigente y **sin reservas**.
6. **IoT.** Entrá como agronomo1: el sistema de Norte con su nodo, 5 sensores y 2 actuadores, todavía sin conexión. **Regenerá el token**
   (IoT · Sistema IoT · Regenerar token), copialo y usalo en Node-RED; no lo pegues en ningún archivo del repo.
7. **Escena en vivo de la pre-reserva (cambia la demo: después hay que reiniciar la rama `vivo` para repetir).**
   a. Como agronomo1, planificá la transición de LN-2 a Maduración N2 (200 plantas) con fecha de hoy; como capataz1, concretala.
   b. En la Shell: `python manage.py proceso_diario --fecha <HOY+1 en AAAA-MM-DD> --solo pre_reservar_suministros`.
   c. Tiene que decir «procesados 1 · creados 1». S-2 pasa a tener un período reservado (HOY+8, 40 plantas de LN-2) y su cosecha, y
      `estado_demo` dice que S-2 «ya tiene 1 reserva(s)». Si no hiciste la transición, el resultado válido es «1 períodos siguen sin
      cobertura completa» y una alerta «Período sin cobertura completa».
8. **Escena en vivo del ventilador.** Con Node-RED conectado, mandá dos lecturas de 35 °C (el botón «Temperatura alta (35 °C)»): después de la
   segunda tiene que aparecer el comando «Encender» del ventilador y la alerta de temperatura fuera de rango. Es lo único que depende de Node-RED.
9. **Navegador real (obligatorio).** Hacé los pasos 4 a 8 en una **ventana privada**, enviando cada formulario hasta el final (ingreso, regenerar
   token, planificar y concretar la transición). Si aparece «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola
   (F12), avisá: lo más probable es un encabezado que el cliente de Django no puede ver.
10. **Volver a empezar.** En Neon, reiniciá la rama `vivo` desde `main` y repetí los pasos 1 y 3. Nunca se borra nada desde Django.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** DAT-02 va en el mismo PR y la misma rama que DAT-01 (decisión del estudiante: no esperar el merge de DAT-01). Se sumaron a
`demo/carga.py` las secciones 12 (lotes existentes), 14 (IoT de Norte) y 13 (suministros), que se ejecutan al final de la carga en ese
orden: 12, 14 y 13. Los suministros van últimos porque reservan el stock de los lotes y porque `pactar_suministro` envía el comprobante por
correo (fuera de su transacción), que así solo sale si todo lo anterior anduvo. Se agregó el comando `estado_demo` (`demo/estado.py`, solo
lectura) y `demo/candado.py` se partió en `verificar_candado()` (variable y base) y `verificar_que_se_puede_cargar()` (esas dos, más «sin
cuentas con rol» y los secretos). Antes de empezar se integró la PR #97, que ya entró a `main`.

**Paso 0 (tabla final de las secciones 12 a 14).**

| Sección | Servicio (archivo y función) | Existe | Estado final |
|---|---|---|---|
| 12 Lotes existentes | `produccion/servicios/lotes_existentes.py` `registrar_lote_existente` | Sí | Cargada (actor: el Agrónomo de cada invernadero) |
| 13 Suministros | `comercial/servicios/suministros.py` `pactar_suministro` | Sí | Cargada (actor: vendedor1) |
| 14 IoT de Norte | `iot/servicios/sistemas.py` `registrar_sistema_iot`, `hardware.py` `alta_hardware`, `reglas.py` `alta_regla` | Sí | Cargada (actor: agronomo1) |

| Pieza | Qué se buscó | Estado |
|---|---|---|
| CMP-07, pedido automático | paso `generar_pedidos_automaticos` (orden 63) registrado | **Está** |
| COM-08a, cobro y mora | paso `vencer_pagos` (orden 30) registrado | **Está** |
| CON-04d, asiento de la multa | `registrar_asiento_automatico` en `comercial/servicios/resoluciones.py` | **No está** (la resolución sí): `estado_demo` dice «no está (la resolución sí)» |
| PRD-05, lote existente | `registrar_lote_existente` | **Está**: no hubo que frenar |

**Salteado:** nada. La carga completa tiene 14 líneas «Cargado:».

**Lo que chocó con el archivo de datos y el estudiante aprobó corregir (el archivo se corrigió en este PR, porque el guion lo lee):**
- **Token:** el archivo decía «el token no se genera en la carga», pero `registrar_sistema_iot` lo genera siempre y lo devuelve en claro. La
  carga lo descarta sin guardarlo ni imprimirlo y el estudiante lo regenera en la pantalla. `estado_demo` dice si fue generado y cuándo.
- **Nodo:** no es una fila de `alta_hardware`: lo crea el registro del sistema. Se sacó de la tabla de equipos.
- **Modelo:** es obligatorio en el sistema y en cada equipo, y el archivo no lo traía. Se agregó la columna, tomada del insumo (ESP32, DHT22, …).
- **Actuadores:** no tienen campo de nombre; «Ventilador sector A» y «Ventana sector A» van en la descripción.
- **Semillas:** el sistema las nombra «Semilla {cultivo} {variedad}», sin «de». Se corrigieron las tablas.
- **Luz:** el aviso de «µmol» quedó viejo (D-105 ya corrigió la unidad a lux).
- **Secretos:** el archivo decía que la base de los correos no va en ningún mensaje de salida; la salida lista el correo completo de cada cuenta
  (paso 3 de DAT-01).

**Escrito con ORM en vez de servicio:** nada nuevo respecto de DAT-01 (el Gerente y la contraseña de las cuentas). Las secciones 12 a 14 van
enteras por servicio.

**Para `docs/temas_abiertos.md` (no corregido en silencio):**
- `pactar_suministro` no recibe `hoy`: usa la fecha real. La carga tiene que correr el mismo día que se calcula HOY (no cruza la medianoche
  en la práctica, pero las pruebas lo suponen).
- `estado_demo` reconoce CON-04d buscando `registrar_asiento_automatico` en el código de `resoluciones.py`: es una heurística. Cuando se haga
  CON-04d hay que revisar que siga detectándolo (hay una prueba que lo simula).
- `registrar_lectura` no necesita que el nodo se haya comunicado: el comando queda «pendiente» hasta que lo haga.
- Cada lote existente deja un asiento (Productos en Proceso / Capital Inicial) con fecha de hoy.

**Pantallas: lo que se corrigió del prototipo (D-61):** no hay pantallas nuevas.

**Pruebas (M1).** `.venv/Scripts/python.exe manage.py test demo.tests --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion`:
78 pruebas, OK (DAT-01: 42; DAT-02: `test_carga_lotes.py` 8, `test_carga_iot.py` 9, `test_carga_suministros.py` 7 y `test_estado_demo.py` 12).
**La suite completa no se corrió al cerrar DAT-02** (pedido del estudiante: la corre el CI en el PR). La de DAT-01 sí había corrido antes
(11 102 pruebas, OK); DAT-02 solo suma archivos dentro de `demo/` y un cambio en `docs/demo/datos_de_la_demo.md`.

**Pendiente de proponer (M3, sin aplicar):** número de la decisión (con `git fetch`, el primero libre en `main` es **D-106**; renombrar
`D-01-demo.md`); `docs/estado.md`; filas de DAT-01 y DAT-02 en `docs/tareas/README.md`; una línea de `docs/historial.md`; la sección de
`docs/revisiones_pendientes.md` con los pasos de arriba; la fila de la decisión en `docs/decisiones/README.md`; y los temas abiertos de arriba.
No se crearon modelos ni migraciones.
