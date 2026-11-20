# Patrón · Datos cargados por migración y pruebas

Para cualquier app que cargue datos con una migración y los use en sus pruebas: la geografía de Georef (`maestros`), el
plan de cuentas (`contabilidad`), las categorías del sistema (`inventario`). Nació en MAE-01 (D-39). Si algo de acá
contradice una decisión, manda la decisión: avisá.

## El problema

Con `--keepdb`, las pruebas de una app que dependen de datos de migración empiezan a fallar, o a tardar minutos, después
de correr las pruebas de otra app. En el CI no pasa, porque arranca de una base nueva. Hay dos causas encadenadas.

**1. Un `TransactionTestCase` vacía la base.** Un `TestCase` corre cada prueba dentro de una transacción que deshace al
terminar, así que no toca los datos de la migración. Un `TransactionTestCase` hace commits de verdad, y para dejar la
base limpia ejecuta un `flush` al terminar: en PostgreSQL, un `TRUNCATE` de **todas** las tablas, también las que cargó
una migración. Con una base nueva no molesta, porque Django corre primero todos los `TestCase` y al final los
`TransactionTestCase`. Pero con `--keepdb` la base se conserva vaciada y la corrida siguiente ya no tiene los datos.
Ejemplo de `core`: `UsrAltUsrInvitacionEnvioTests` (sin la etiqueta `concurrencia`, así que corre en local).

**2. Sin `ANALYZE`, los planes se degradan.** PostgreSQL elige cómo ejecutar una consulta con estadísticas del tamaño de
cada tabla. Después del `TRUNCATE` esas estadísticas dicen «0 filas». Si cada clase de pruebas vuelve a cargar los datos
dentro de su transacción, el autovacuum no los ve (no están confirmados) y las estadísticas siguen en cero: el
planificador arma planes para tablas de cero filas (bucles anidados, sin índices) y una consulta con unos `JOIN` pasa de
milisegundos a decenas de segundos. En MAE-01 una corrida pasó de 11 s a 168 s por esto.

## La solución: cargar una vez, confirmar y analizar

Una función que recarga los datos **solo si faltan**, los **confirma** y corre `ANALYZE`, y un mixin que la llama en
`setUpClass`, antes de que `TestCase` abra la transacción de la clase. Va en `<app>/tests/fabricas.py`:

```python
import importlib

from django.apps import apps
from django.db import connection

from maestros.models import Localidad  # cualquier modelo que cargue la migración


def asegurar_georef():
    """Carga y confirma los datos de la migración si la base de pruebas los perdió, y corre ANALYZE."""
    if not Localidad.objects.exists():
        # La misma función que usa la migración: los datos son siempre los mismos.
        importlib.import_module("maestros.migrations.0002_cargar_georef").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE maestros_provincia, maestros_departamento, maestros_localidad")


class ConGeoref:
    """Mixin: ``class MisTests(ConGeoref, TestCase)``."""

    @classmethod
    def setUpClass(cls):
        asegurar_georef()  # fuera de la transacción de la clase: los datos quedan confirmados
        super().setUpClass()
```

Por qué así y no de otra forma:

- **En `setUpClass`, antes de `super()`.** `TestCase` abre su transacción dentro de `super().setUpClass()`. Lo que se
  inserta antes queda confirmado y sirve a todas las clases y a las corridas siguientes. En `setUpTestData` o en
  `setUp` se inserta dentro de la transacción: se deshace al terminar, se vuelve a cargar en cada clase (o en cada
  prueba) y las estadísticas nunca se enteran.
- **Solo si faltan.** En el CI y en una base recién creada la migración ya cargó todo, y la función no hace nada.
- **Con la función de la migración.** No se copian los datos ni se usa un fixture aparte: la fuente es una sola.
- **El `ANALYZE` solo sobre las tablas cargadas.** Se lista cada tabla; en PostgreSQL se puede correr dentro de una
  transacción.
- **El mixin va primero en la lista de bases**, para que su `setUpClass` corra antes que el de `TestCase`.

## Cómo seguirlo en una app nueva

1. La migración de datos expone una función `cargar(apps, schema_editor)` (y su `descargar`), sin importar código de la
   app (D-36, D-39).
2. En `<app>/tests/fabricas.py`, copiá la función y el mixin con el modelo y las tablas de tu app. Si cargan datos
   varias migraciones, llamá a la función de cada una.
3. Las clases que usan esos datos heredan del mixin: `class XTests(ConDatos, TestCase)`. Las que no los usan no lo
   necesitan.
4. La migración se prueba aparte, sobre tablas vacías y dentro de una prueba (`TestCase`): se borran los datos, se llama
   a `cargar`, se cuentan las filas y se llama a `descargar`. Así la prueba no depende del estado de la base. Ejemplo:
   `test_regla_3_la_migracion_carga_georef` en `maestros/tests/test_prod_alt_inv.py`.

## Cómo reconocer el problema

- Un `DoesNotExist` o un conteo en cero en pruebas que antes pasaban, justo después de correr pruebas de otra app con
  `--keepdb`.
- Una corrida que tarda de golpe diez veces más sin que haya cambiado nada. Para comprobarlo: en `manage.py shell`,
  contá las filas de la tabla en la base `test_<nombre>`; si es cero, la vaciaron.
- Arreglo rápido sin tocar código: correr una vez sin `--keepdb` y con `--noinput`, que recrea la base.

## Lo que no hay que hacer

- No agregar `serialized_rollback = True` ni cambiar los `TransactionTestCase` de otra app para proteger tus datos: es
  de ellos y no de tu app. El mixin hace que tus pruebas se arreglen solas.
- No cargar los datos en cada prueba: es lo que degrada los planes.
- No guardar los datos de prueba en la base de desarrollo ni usar la de Neon (`CLAUDE.md`, «Seguridad»).

## Las categorías del sistema de `inventario` (INV-01, ronda «Producción 1»)

Mismo patrón, con estas particularidades:

1. **Una migración de datos** separada de la de esquema: `cargar_categorias_del_sistema`, con `cargar(apps, schema_editor)` y
   `descargar(apps, schema_editor)`. Los valores van escritos en la migración: cuatro filas de `TipoInsumo`, con su `codigo` fijo
   (`semillas`, `envases`, `repuestos_de_hardware`, `infraestructura`), su nombre (Semillas, Envases, Repuestos de hardware, Infraestructura),
   `es_del_sistema` verdadero, `consumo_directo = no_admite` y estado activo.
2. **Idempotente por `codigo`** (`update_or_create`): correrla dos veces no duplica. **No pisa el nombre** si el estado de la base ya
   tiene la fila (el nombre de una categoría del sistema no se renombra, pero si alguien lo hiciera a mano no lo revierte una migración).
3. **`descargar`** borra las cuatro filas solo si ningún insumo las usa.
4. **Reglas por `codigo`, nunca por nombre** (regla 1 de 8.23): una constante por categoría en `inventario/categorias.py`.
5. **Pruebas:** `inventario/tests/fabricas.py` tiene `asegurar_datos_de_inventario()` y el mixin `ConDatosDeInventario`, con el mismo esquema que
   `ConGeoref` (carga solo si faltan, confirma y corre `ANALYZE` sobre `inventario_tipoinsumo`). Las clases de pruebas de `inventario` heredan
   de él. La migración se prueba aparte, sobre tablas vacías.

## Singletons y catálogos fijos (MAE-03 y MAE-04, ronda «Producción 1»)

El mismo patrón sirve para tres conjuntos chicos de `maestros`: el catálogo de **tipos de etapa** (cinco filas, MD-52), la fila
de **`ConfiguracionOperativa`** y la de **`PerfilOrganizacion`** (MD-89). Lo que cambia respecto de Georef:

1. **Una migración de datos por conjunto**, separada de la de esquema: `cargar_tipos_de_etapa` (MAE-03) y
   `cargar_configuracion_y_perfil` (MAE-04), con el número que corresponda al momento de crearlas (ver
   `docs/patrones/trabajo_en_paralelo.md`). Cada una expone `cargar(apps, schema_editor)` y `descargar(apps, schema_editor)`.
   **Los valores van escritos en la migración**, no importados del modelo (una migración no depende de código que cambia). Una
   prueba compara los valores de la migración con los `default` de los campos del modelo, para que no se separen.
2. **Idempotente.** `cargar` usa `update_or_create` por la clave natural (`codigo` en los tipos de etapa; `singleton=1` en los
   otros dos): correrla dos veces no duplica ni pisa lo que el Gerente ya cambió. Para el perfil, `cargar` toma
   `settings.NOMBRE_ORGANIZACION` solo al crear la fila (D-48) y no vuelve a escribir el nombre.
3. **`descargar` no borra datos del usuario.** La inversa de los tipos de etapa borra las cinco filas solo si ninguna está
   referenciada; la de los singletons no hace nada (la tabla se elimina con la migración de esquema anterior).
4. **Unicidad desde la base.** Los singletons tienen la columna `singleton` (valor fijo 1) con restricción única y un
   `CheckConstraint` `singleton = 1`; los tipos de etapa, `codigo` y `puesto_global` únicos.
5. **Pruebas.** En `maestros/tests/fabricas.py` se agrega `asegurar_datos_de_maestros()` y el mixin `ConDatosDeMaestros`, con el
   mismo esquema que `ConGeoref` (carga solo si faltan, confirma y corre `ANALYZE`): vuelve a cargar los tipos de etapa y las
   dos filas si un `TransactionTestCase` vació la base. Las clases de pruebas de sectores, cultivos, configuración y perfil
   heredan de él. La migración se prueba aparte sobre tablas vacías (`cargar`, contar filas, `descargar`).
6. **Lectura.** `maestros.servicios.configuracion.obtener()` y `maestros.servicios.perfil.obtener()` devuelven la fila; si no
   existiera (por ejemplo, una base vaciada), la **crean con los valores iniciales** de forma segura ante pedidos simultáneos
   (`get_or_create` sobre `singleton=1`) en vez de fallar. Es una red de seguridad, no el camino normal.
