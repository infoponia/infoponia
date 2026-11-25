# DAT-01 · Comando `cargar_demo`: candado y datos base

Estado: hecha, a verificar a mano | App: demo | Rama: feature/dat-01-cargar-demo-base | Ronda: —

Depende de: D-NN (en `docs/decisiones/`; si no está, frená)

Una tarea es un bloque funcional (D-44): se hace de corrido en una sesión y un PR. Aprobado el plan, no pidas permiso paso por paso. Si algo
que necesitás no está en «Leer», frená (L9).

**Esta tarea es una excepción explícita a «no cargues datos de prueba» (D-NN).** La excepción vale solo para el comando `cargar_demo` y solo
para la base `infoponia_demo`. Vos (Claude Code) **no corrés el comando contra ninguna base real** y no pedís ni usás la cadena de Neon. Lo
corre el estudiante en la Shell del servicio demo de Render. Vos lo probás solo con las pruebas, sobre la base `test_…`.

## Paso 0 (antes del plan): analizar el repo y marcar lo que no existe

Antes de proponer el plan, recorré el repo y armá una tabla con cada sección de `docs/demo/datos_de_la_demo.md` (1 a 11; la 12 a 14 son de
DAT-02):

| Sección | Servicio que la escribe (archivo y función) | Existe | Qué falta, si falta |
|---|---|---|---|

Reglas:

- **Si una sección depende de algo que no está implementado** (un modelo, un campo o un servicio que no encontrás), no la inventes. Se
  saltea, el comando informa «Salteado: <sección> (falta <qué>)», y lo anotás en el cierre.
  - Ejemplo: si `ConfiguracionOperativa` todavía no tiene `porc_margen_pedido_automatico` (CMP-07), no se toca.
- **Si un valor del archivo de datos choca con una regla del código** (un rango, un largo, un CUIT), frená y avisá (L7). No lo cambies en
  silencio.
- **Si un servicio exige un actor**, usá el que corresponde al caso de uso según el archivo de datos (por ejemplo, el Gerente para crear
  cuentas, el Agrónomo del invernadero para habilitar insumos).

## Casos de uso incluidos

Ninguno nuevo. El comando **llama** a los servicios ya hechos de: usuarios (alta de cuentas), maestros (invernaderos, sectores, cultivos,
variedades, transportistas, configuración y perfil), inventario (categorías, insumos, semillas, habilitación, ajuste de carga inicial),
compras (proveedores), comercial (clientes, direcciones, vehículos) y contabilidad (primer ejercicio).

## Leer

- Decisiones: D-NN (esta), D-37 (niveles), D-95 punto 3 y D-96 punto 5 (por qué es excepción), D-101 (no borrar datos), D-103
- Datos: `docs/demo/datos_de_la_demo.md`, secciones 1 a 11
- Servicios: los que encuentres en el paso 0 (`maestros/servicios/*`, `inventario/servicios/*`, `compras/servicios/proveedores.py`,
  `comercial/servicios/clientes.py`, `comercial/servicios/vehiculos.py`, `contabilidad/servicios/ejercicios.py`, el alta de usuarios)
- Comandos de referencia: `contabilidad/management/commands/poner_en_marcha_contabilidad.py` y `core/management/commands/proceso_diario.py`
  (estilo, `_leer_fecha`, errores con `CommandError`)
- Reglas: `.claude/rules/pruebas.md`

## Límites

- Crea modelos: ninguno. La app `demo` no tiene modelos ni migraciones.
- Migraciones: ninguna.
- Permitido fuera de la app:
  - `config/settings.py`: sumar `"demo"` a `INSTALLED_APPS` solo si `os.environ.get("INFOPONIA_DEMO") == "1"` o si se corren pruebas
    (`"test" in sys.argv`). Una línea comentada que cite D-NN.
  - `CLAUDE.md`: una línea en la regla de datos de prueba: «Excepción: `cargar_demo` (D-NN), solo para la base `infoponia_demo`».
  - `docs/decisiones/README.md`: la fila de D-NN, con el número real.
  - `.env.example`: tres líneas comentadas, sin valores: `INFOPONIA_DEMO`, `INFOPONIA_DEMO_CONTRASENA` e `INFOPONIA_DEMO_CORREO`.
- Dependencias nuevas: ninguna.
- Fuera de alcance:
  - Lotes, contratos e IoT (DAT-02).
  - Cualquier comando que borre datos. Para volver a empezar se reinicia la rama de Neon, nunca un borrado desde Django.

## Pasos (en este orden; corré las pruebas del paso antes de seguir)

1. **App y candado.**
   - Crear `demo/` con `apps.py`, `__init__.py`, `management/commands/cargar_demo.py` y `tests/`.
   - Crear `demo/candado.py` con `verificar_que_se_puede_cargar()`. Lanza `CommandError` con un mensaje claro si:
     - `INFOPONIA_DEMO` no es `"1"`;
     - el nombre de la base no es `infoponia_demo`;
     - ya hay alguna cuenta con rol (Gerente, Agrónomo, etc.): la carga es para una base recién migrada;
     - falta `INFOPONIA_DEMO_CONTRASENA` o `INFOPONIA_DEMO_CORREO`.

     El nombre de la base se lee en una función propia (`nombre_de_la_base()`), para que las pruebas puedan sustituirla.
   - Pruebas: `demo/tests/test_candado.py`, un caso por condición. Cada caso verifica que no se escribió nada.
2. **Carga de las secciones 1 a 11.**
   - Una función por sección en `demo/carga.py`, en el orden del archivo de datos. Todas corren dentro de una sola transacción
     (`transaction.atomic`): si una falla, no queda nada a medias.
   - Las fechas se calculan con `HOY = timezone.localdate()`.
   - Correos: `f"{base}+{clave}@gmail.com"`. Contraseña: la de la variable, sin contraseña temporal.
   - Si una sección se saltea (paso 0), la función devuelve el motivo y sigue.
   - Pruebas: `demo/tests/test_carga_base.py`. Con el candado sustituido, se carga y se comprueba:
     - 10 cuentas, cada una con su rol;
     - 2 invernaderos con su personal;
     - 7 sectores;
     - 3 variedades con su ciclo;
     - los insumos con el stock de la tabla, incluida la Solución nutritiva A por debajo del mínimo;
     - 3 proveedores, 3 clientes con su dirección y 2 vehículos;
     - el ejercicio contable;
     - los 4 valores de la configuración operativa.
3. **Salida del comando.** Una línea por sección («Cargado: …» o «Salteado: … (falta …)»). Al final, la lista de cuentas (rol y correo,
   **nunca la contraseña**) y el aviso: «Ahora corré DAT-02 si está, o seguí la guía».

Si el tiempo apremia, lo último que se recorta es: la salida detallada del paso 3 (basta «Carga terminada»).

## Hecho cuando

- `python manage.py cargar_demo` sin `INFOPONIA_DEMO=1`, o con otra base, termina con error y no escribe nada.
- Con el candado sustituido en las pruebas, carga todas las secciones de la 1 a la 11 que existen en el repo, con los valores del archivo de
  datos.
- La app `demo` no aparece en `INSTALLED_APPS` sin `INFOPONIA_DEMO=1` fuera de las pruebas (una prueba lo verifica leyendo la lógica de
  `settings`).
- Pruebas: `demo/tests/test_candado.py`, `demo/tests/test_carga_base.py`.
- Comando de pruebas: `python manage.py test demo.tests --keepdb --parallel --exclude-tag concurrencia --exclude-tag migracion`. También la
  suite completa, una vez al final, para ver que `settings` no rompió nada.

## Verificación a mano (la completa Claude Code al cerrar)

**Qué es esto:** no es crear datos a mano: es correr el comando en la Shell del servicio demo de Render y revisar la salida y las pantallas.
La guía para armar el servicio (`PREPARACION_Render_y_Neon.md`) la tienen ustedes fuera del repo.

**Verifiqué** (Claude Code, solo en la base de pruebas `test_…`; el comando no se corrió contra ninguna base real):
- El recorrido `demo/tests/test_recorrido_demo.py`: con la carga hecha, entran por la pantalla de ingreso gerente1, agronomo1, vendedor1 y
  contador1 con la contraseña de la variable, no los manda a cambiarla y abren su pantalla principal con lo cargado; una contraseña
  equivocada no entra.
- El comando entero (`demo/tests/test_comando.py`): 14 líneas «Cargado:» (con DAT-02), la lista de cuentas y la salida sin la contraseña.
- Migraciones: ninguna en esta tarea (no hay `sqlmigrate`). Las dos de la PR #97 (`comercial` 0014 y `core` 0052) se aplicaron en la base
  de pruebas y pasaron sus 3600 pruebas.

**Lo cubre una prueba:** el candado (una prueba por condición, `test_candado.py`), que `demo` no se instala sin `INFOPONIA_DEMO=1`
(`AppDemoCondicionadaTests`), los valores de las secciones 1 a 11 (`test_carga_base.py`), que el ejercicio empieza el día 1 del mes aunque
la carga de stock asiente, y que una segunda corrida se niega (`test_comando.py`).

**No pude verificar:** la carga real en Neon y en Render (no la corro yo, D-NN); que Render arranque el servicio demo con las variables;
el envío de correos; y cómo se ven las pantallas en un navegador (no abro navegadores, D-96).

### Antes de empezar

1. En Render, el servicio `infoponia-demo` (Starter, con Shell) tiene estas variables de entorno (los valores los eligen ustedes y **no se
   escriben en ningún archivo del repo**): `INFOPONIA_DEMO` = `1`, `INFOPONIA_DEMO_CONTRASENA` (la contraseña de las 10 cuentas) e
   `INFOPONIA_DEMO_CORREO` (la parte de su casilla de Gmail antes de `@gmail.com`).
2. `DATABASE_URL` del servicio apunta a la rama `vivo` del proyecto Neon `infoponia-demo`, base `infoponia_demo`, **recién reiniciada
   desde `main`** (vacía). Nunca a la base de producción.
3. Con ese servicio desplegado, abrí la Shell de Render.

### Pasos

1. **Migrar.** En la Shell: `python manage.py migrate`. Tiene que terminar sin errores (todo en «OK»).
2. **Cargar.** `python manage.py cargar_demo`. Tiene que mostrar:
   - catorce líneas «Cargado: N. <sección> (…)», de la 1 a la 14 (las 12 a 14 son de DAT-02, en el mismo PR), y **ninguna** «Salteado:»;
   - la lista «Cuentas:» con diez filas «Rol: <base>+<clave>@gmail.com» (Gerente, Agrónomo ×2, Capataz ×2, Vendedor, Transportista ×2,
     Técnico y Contador);
   - al final «Carga terminada. Ahora corré estado_demo para ver si las escenas del guion están listas, o seguí la guía.»
   - **La contraseña no tiene que aparecer en ninguna línea.** Si aparece, avisá: es un defecto.
3. **Segunda corrida.** Volvé a correr `python manage.py cargar_demo`. Tiene que negarse con «La base ya tiene cuentas con rol…» y no cambiar
   nada. (Lo cubre `test_comando.py`.)
4. **Entrar con cada cuenta.** En la dirección del servicio demo, con el correo `<base>+<clave>@gmail.com` y la contraseña de la variable.
   Ninguna debe pedir cambiar la contraseña. Qué tiene que ver cada una:
   - **gerente1 (Laura Benítez):** Invernaderos: «Norte» y «Sur» con su personal (Sur sin Técnico). Configuración operativa: pre-reserva
     de suministros 7, reintentos 1, espera 10 s, lecturas 2. Cabecera con «Huerta Hidropónica del Paraná». Vehículos: AE123BC (Toyota
     Hilux, 800 kg) y AF456DE (Renault Kangoo, 500 kg). Proveedores: los tres, con sus especialidades.
   - **agronomo1 (Martín Sosa):** solo Norte. Sectores: Germinación N1 (400), Crecimiento N1 (600), Maduración N1 (600), Maduración N2
     (400). Existencias: «Solución nutritiva A» con 12 l contra un mínimo de 20 y la alerta de stock bajo; «Fungicida biológico» con un
     lote de 3 l que vence en 3 días y otro de 5 l. Cultivos: Lechuga (Criolla, Morada) y Albahaca (Genovesa).
   - **agronomo2 (Paula Giménez):** solo Sur, con sus tres sectores. Existencias: Semilla de Albahaca (1000), Bandeja (100) y Solución
     nutritiva A (40, sin alerta).
   - **vendedor1 (Sofía Acosta):** Clientes: Súper Del Parque S.A., Restaurante El Mensú S.R.L. y Marta Villalba, cada uno con su
     dirección.
   - **contador1 (Valeria Ortiz):** Libro de gestión: un ejercicio que empieza el **primer día del mes de hoy** y los asientos de la carga
     inicial de stock (Debe Insumos en Stock, Haber Capital Inicial), con fecha de hoy.
   - **capataz1, capataz2, tecnico1, transportista1 y transportista2:** entran sin pedir cambio de contraseña y llegan a su inicio. No
     hay pantallas nuevas en esta tarea: lo que ve cada uno lo definen sus tareas.
5. **Navegador real (obligatorio).** Abrí la pantalla de ingreso en una **ventana privada** (sin sesión), escribí el correo y la contraseña
   de una cuenta y **enviá el formulario hasta el final**; después cerrá sesión y repetí con otra cuenta. Tiene que entrar. Si aparece
   «Prohibido (403)» o «Verificación CSRF fallida», o un error en la consola (F12), avisá: lo más probable es un encabezado que el
   cliente de Django no puede ver. El cliente de Django no ve el CSRF, el encabezado `Origin` ni el JavaScript.
6. **El candado, en el servicio de producción (opcional).** En la Shell de producción, `python manage.py cargar_demo` tiene que decir
   «Unknown command»: la app `demo` no se instala sin `INFOPONIA_DEMO=1`. **No** lo corras en la Shell de producción con esa variable.
7. **Volver a empezar.** Si hay que repetir el ensayo: en Neon se reinicia la rama `vivo` desde `main` y se vuelve a migrar y cargar.
   Nunca se borra nada desde Django.

## Cierre (la completa Claude Code al cerrar)

**Qué se hizo.** La app `demo` (nivel 9, sin modelos ni migraciones) con el comando `cargar_demo`: `demo/candado.py` (doble candado y
secretos), `demo/carga.py` (una función por sección, una sola transacción) y el comando. En `config/settings.py` la app se instala solo con
`INFOPONIA_DEMO=1` o en las pruebas; `CLAUDE.md` y `.env.example` ya dicen la excepción y las tres variables. Antes de empezar se integró la
PR #97 (COM-08b; avance rápido sin conflictos, 3600 pruebas de `comercial` y `core` en verde).

**Paso 0 (tabla final).** Todas las secciones tenían su servicio; no se salteó ninguna y ningún valor del archivo de datos chocó con una
regla del código.

| Sección | Servicio (archivo y función) | Existe | Estado final |
|---|---|---|---|
| 1 Organización | `maestros/servicios/perfil.py` `modificar_perfil` | Sí | Cargada |
| 2 Configuración | `maestros/servicios/configuracion.py` `modificar_configuracion` | Sí | Cargada (los 4 valores; `porc_margen_pedido_automatico` no se toca) |
| 3 Geografía | lectura de `Localidad` (migración 0002 de maestros) | Sí | Solo lectura |
| 4 Cuentas | `core/servicios.py` `alta_usuario` + ORM | Sí | Cargada (ver «ORM») |
| 5 Invernaderos, sectores, transportistas | `alta_invernadero`, `alta_sector`, `agregar_transportista` | Sí | Cargada |
| 6 Cultivos y variedades | `alta_cultivo`, `alta_variedad` (crea la semilla) | Sí | Cargada |
| 7 Categorías, insumos, existencias | `alta_tipo_insumo`, `alta_insumo`, `habilitar_insumo`, `calcular_ajuste` y `confirmar_ajuste` | Sí | Cargada (un lote por ajuste: el Fungicida lleva dos) |
| 8 Proveedores | `compras/servicios/proveedores.py` `alta_proveedor` | Sí | Cargada |
| 9 Clientes | `comercial/servicios/clientes.py` `alta_cliente` | Sí | Cargada |
| 10 Vehículos | `comercial/servicios/vehiculos.py` `alta_vehiculo` | Sí | Cargada |
| 11 Contabilidad | `contabilidad/servicios/ejercicios.py` `crear_primer_ejercicio` | Sí | Cargada |

**Salteado:** nada. La lógica de salteo existe (`Salteada`, «Salteado: … (falta …)»), pero no se dispara con el repo actual.

**Escrito con ORM en vez de servicio, y por qué (punto 3 de la decisión de la demo):**
- El **Gerente** (`gerente1`): en una base recién migrada no hay un actor que lo dé de alta (lo da de alta un Administrador y ese no existe).
- La **contraseña** de las diez cuentas (`set_password`) y dejar `fecha_contrasena_temporal` vacía: `alta_usuario` no recibe contraseña (regla 4
  de USR-ALT-USR, SEG-04). Los otros nueve usan `alta_usuario(actor=gerente1)`, así que quedan auditados; el Gerente no.
- Lo demás va por servicio. La contraseña temporal que devuelve `alta_usuario` se descarta sin usarla ni imprimirla.

**Decisiones del estudiante durante la tarea (25/11/2026):**
1. **Orden de ejecución 4, 1, 2, 3, 11, 5 a 10** (la salida se informa en el orden del archivo): las secciones 1 y 2 necesitan un Gerente, y
   la carga inicial de stock asienta; sin ejercicio previo el sistema abriría uno desde HOY y la sección 11 (desde el día 1 del mes) no
   haría nada. La tarea decía «en el orden del archivo».
2. **Cuentas:** gerente1 por ORM y las otras nueve por `alta_usuario`.
3. **Salida con el correo completo** (manda el paso 3 de la tarea). El archivo de datos dice que la base de los correos no va en ningún
   mensaje de salida: se anota abajo.

**Para `docs/temas_abiertos.md` (no corregido en silencio):**
- El orden de ejecución difiere del escrito en la tarea («en el orden del archivo»).
- `docs/demo/datos_de_la_demo.md` («Secretos fuera del repo») dice que la base de los correos no se escribe en ningún mensaje de salida; el
  paso 3 de la tarea pide el correo completo, que la contiene. Hay que corregir una de las dos fuentes.
- El aviso de la sección 6 del archivo de datos sobre «µmol» quedó viejo: D-105 ya corrigió la unidad a lux. No cambia ningún valor.
- La tarea nombra la decisión `D-NN-demo.md`; el archivo en el repo es `docs/decisiones/D-01-demo.md`. Al cerrar se renombra con el número real.
- Los nombres de las semillas los arma el sistema («Semilla {cultivo} {variedad}»); el comando avisa si difieren de la tabla del archivo.
- Al habilitar un insumo con mínimo mayor que 0 y stock 0 nace la alerta de stock bajo y la carga inicial la resuelve: quedan alertas
  resueltas en el historial. Es lo que hacen los servicios.
- Con `INFOPONIA_DEMO` distinto de `1`, el comando no existe (`Unknown command`), no «se niega»: es el punto 5 de la decisión.

**Pantallas: lo que se corrigió del prototipo (D-61):** no hay pantallas nuevas.

**Pruebas (M1).** `.venv/Scripts/python.exe manage.py test demo.tests --parallel --noinput --exclude-tag concurrencia --exclude-tag migracion`:
42 pruebas, OK (`test_candado.py` 14, `test_carga_base.py` 24, `test_comando.py` 2, `test_recorrido_demo.py` 2). Suite completa, una vez
al final, para ver que `settings` no rompió nada: 11102 pruebas, OK (1206 s, con DJANGO_DEBUG=0 y una clave falsa, incluidas concurrencia y migración);
corrió con DAT-01 sola, antes de sumar DAT-02 (que solo agrega archivos dentro de `demo/`). La suite completa de DAT-02 la corre el CI en el PR.

**Pendiente de proponer (M3, sin aplicar):** número de la decisión (con `git fetch`, el primero libre en `main` era **D-106**) y renombrar
`D-01-demo.md`; `docs/estado.md`; fila en `docs/tareas/README.md`; línea de `docs/historial.md`; sección de `docs/revisiones_pendientes.md` con
los pasos de arriba; fila de la decisión en `docs/decisiones/README.md`; los temas abiertos de arriba. No se crearon modelos.
