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
