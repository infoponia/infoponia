# DAT-01 · Comando `cargar_demo`: candado y datos base

Estado: pendiente | App: demo | Rama: feature/dat-01-cargar-demo-base | Ronda: —

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

<!-- Al cerrar, Claude Code escribe los pasos para el estudiante. Acá NO es crear a mano: es correr el comando en la Shell del servicio demo
siguiendo `PREPARACION_Render_y_Neon.md` (la guía que tiene el estudiante, fuera del repo) y qué tiene que ver en la salida y en pantalla. Tres
listas antes: Verifiqué, Lo cubre una prueba, No pude verificar (la carga real en Neon: no la corrés vos). -->

## Cierre (la completa Claude Code al cerrar)

<!-- La tabla del paso 0 con su estado final; lo salteado y por qué; lo escrito con ORM en vez de servicio, y por qué. Número real de D-NN
(git fetch, mirar docs/decisiones/ en main) y renombrar el archivo. -->
