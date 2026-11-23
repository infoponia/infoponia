# Patrón · Datos para la verificación a mano

Cómo se deja la base local lista para que el estudiante verifique una tarea (regla «Datos para la verificación a mano» de `CLAUDE.md`).
Lo creó IOT-03, que unificó el comando que MAE-02d había creado en `maestros`. Si algo de acá contradice a `CLAUDE.md`, manda `CLAUDE.md`: avisá.

## Qué es

**Un solo comando** para todo el proyecto, `python manage.py cargar_datos_de_verificacion --contrasena <contraseña>` (MAE-02d lo había creado con `--clave`, dentro de `maestros`: ya no existe ese comando propio), que deja la base **local** con los datos que pide la
«Verificación a mano» de cada tarea, en cada estado que haya que probar. El estudiante no carga datos a mano. La contraseña es la de
quien trabaja y está en su `CLAUDE.local.md` (no se versiona; nunca se escribe en un archivo del repo). También se puede pasar en la variable
de entorno `INFOPONIA_CONTRASENA_DE_PRUEBA`. `--listar` muestra los cargadores sin cargar nada; `--solo <código>` corre uno.

## Dónde vive

| Pieza | Archivo |
|---|---|
| Registro de cargadores y guarda de «solo la base local» | `core/verificacion.py` |
| El comando (sin lógica propia) | `core/management/commands/cargar_datos_de_verificacion.py` |
| El cargador de cada app | `<app>/verificacion.py`, registrado en `AppConfig.ready()` con `core.verificacion.registrar_cargador(codigo, nombre, orden, funcion)` (regla A4 de D-37: `core` no conoce a ninguna app) |
| Pruebas | `core/tests/test_verificacion.py` y `<app>/tests/test_verificacion.py` |

Mismo patrón que el proceso diario (D-56, `core/procesos.py`). **Cada app tiene su propia función** y no se mezclan: así una tarea nueva agrega lo suyo sin
tocar el código de otra app ni el comando. Hoy: `maestros` (orden 5, MAE-02d) e `iot` (orden 10, IOT-03).

### Cómo agrego los datos de mi tarea
1. Si mi app ya tiene `<app>/verificacion.py`, amplío su función `cargar(contrasena)`. Si no, lo creo con esa función y la registro en mi `AppConfig.ready()`:
   `verificacion.registrar_cargador("<app>", "<nombre>", <orden>, <app>.verificacion.cargar)` (`from core import verificacion`). El orden es de 5 en 5: un cargador que
   necesita lo de otro va después (el de `iot` usa lo que arma `maestros`).
2. La función devuelve `ResumenDeCarga(creado=(…), cuentas=(…), pendiente=(…))` y, si no puede seguir, lanza `core.verificacion.ErrorDeCarga("…")` con un mensaje claro.
3. **Cuentas con un número propio** para no pisar a otra app: `maestros` usa `prueba1` y `prueba2`; `iot`, `prueba3`. La siguiente app usa el número que siga (`prueba4`, …).
   Antes de crear datos, reutilizá lo que ya exista por su nombre (idempotente).
4. Pruebas en `<app>/tests/test_verificacion.py` (la guarda ya la prueba `core`).

## La guarda

`core.verificacion.exigir_base_local()` se llama **antes de leer o escribir nada** y se niega si:

1. `DEBUG` está apagado;
2. el `HOST` de la base no es `localhost`, `127.0.0.1` ni `::1` (una base sin host tampoco se toma por local);
3. hay variables de Render en el entorno: `RENDER`, cualquiera que empiece con `RENDER_` o `IS_PULL_REQUEST` (verificado el 22/11/2026 en la
   documentación de Render, «Default environment variables»: `RENDER` vale siempre `true` y `IS_PULL_REQUEST` es la única que no lleva el prefijo).

Los mensajes de rechazo no incluyen el host ni ningún secreto.

## Reglas de un cargador

- Firma `funcion(contrasena) -> ResumenDeCarga(creado, cuentas, pendiente)`. Es **idempotente**: lo que ya existe se reutiliza.
- Carga **llamando a los servicios de las apps**, nunca con inserciones directas, para que queden la auditoría y las reglas como en una pantalla.
  Si falta un servicio para algún estado que hay que probar, **frená y avisá**: no lo resuelvas con el ORM.
- **No borra nada** (D-22: la auditoría es inmutable). La primera versión no tiene `--limpiar`; si hace falta, se frena y se pregunta.
- **No toca al Administrador** (ni su usuario ni su contraseña).
- Cuentas `<rol>@prueba<N>.local` (un N propio por cargador, ver arriba), con la contraseña recibida. Se dan de alta con `alta_usuario` y
  se les pone la contraseña con `cambiar_contrasena`; la temporal se descarta.
- **Nunca** imprime ni devuelve la contraseña ni un token. Lo que no se puede cargar sin un secreto (el sistema IoT: su token se ve una sola vez)
  se pide como `pendiente` y se hace por la pantalla.
- Un cargador que falla (`ErrorDeCarga` o cualquier excepción) no frena a los demás; el comando informa cuál falló y termina con código 1.
- En el «Cierre» de la tarea se listan los datos que quedaron cargados y con qué cuentas.

## El cargador de `iot` (IOT-03)

Primera corrida: cuentas `agronomo@prueba3.local` y `capataz@prueba3.local` (si «Norte» ya existe, se sigue con su Agrónomo y no se crean cuentas); el invernadero «Norte» con ese Agrónomo y ese Capataz y **sin
Técnico**; «Sector A» (germinación) y «Sector B» (maduración); un insumo de «Repuestos de hardware»; la variedad «Lechuga Crespa» con su semilla
habilitada y con stock, y una siembra «a realizar» (da variedades presentes y, con ellas, **umbral efectivo**: temperatura 18 a 26 °C, humedad
60 a 80 % HR, luz 10.000 a 30.000 lux, fotoperíodo 8 a 14 h).

Segunda corrida, **después de registrar a mano el sistema IoT de «Norte»** por la pantalla: el rango de la solución (18,0 a 24,0 °C) y los siete
equipos de `docs/api/nodo/node-red/README.md`, sección 4, punto 2.

**Pendiente para IOT-06:** el sensor `norte/sectorA/temp-vieja` (dado de baja, para probar a mano el motivo `equipo_dado_de_baja`). No se carga
hasta que IOT-06 traiga el servicio de baja de hardware (`baja_hardware`): hoy no existe y la regla es no cargarlo con el ORM. Mientras tanto
el motivo lo cubren las pruebas automáticas (`iot/tests/test_api_ejemplos.py`).
