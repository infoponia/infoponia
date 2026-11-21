# Fábricas compartidas por las pruebas de maestros/tests/: localidades de Georef (ya cargadas por la migración 0002),
# datos de alta de un invernadero y un invernadero ya creado directo en la base (sin pasar por el servicio de alta).
# Reutilizan las fábricas de cuentas de core/tests/fabricas.py. Una sola firma por función.

import importlib
from contextlib import contextmanager
from unittest import mock

from django.apps import apps
from django.db import connection
from django.utils import timezone

from core.models import Agronomo, Capataz, Tecnico, Vendedor
from core.tests.fabricas import crear_cuenta
from maestros import alertas as registro_de_alertas
from maestros.alertas import Clase, Destinatario, TipoAlerta
from maestros.models import (
    Alerta,
    ConfiguracionOperativa,
    Departamento,
    Direccion,
    DireccionRural,
    DireccionUrbana,
    Ciclo,
    Cultivo,
    EtapaProductiva,
    Invernadero,
    Localidad,
    PerfilOrganizacion,
    Provincia,
    SectorProduccion,
    TipoEtapa,
    Variedad,
)


def asegurar_georef():
    """Deja cargada y confirmada la geografía de Georef en la base de pruebas. La migración 0002 la carga al crear la
    base, pero un ``TransactionTestCase`` (de core, por ejemplo) vacía todas las tablas al terminar, y con ``--keepdb``
    la base queda sin Georef para las corridas siguientes. Si está vacía, se vuelve a cargar con la misma función de la
    migración y se corre ``ANALYZE``, para que PostgreSQL conozca el tamaño de las tablas: sin estadísticas elige planes
    muy lentos. Hay que llamarla fuera de la transacción de una clase de pruebas (ver ``ConGeoref``), así los datos
    quedan confirmados y la base de pruebas se arregla sola."""
    if not Localidad.objects.exists():
        importlib.import_module("maestros.migrations.0002_cargar_georef").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE maestros_provincia, maestros_departamento, maestros_localidad")


class ConGeoref:
    """Mixin para las clases de prueba que usan Georef: ``class MisTests(ConGeoref, TestCase)``. Asegura Georef en
    ``setUpClass``, antes de que ``TestCase`` abra la transacción de la clase."""

    @classmethod
    def setUpClass(cls):
        asegurar_georef()
        super().setUpClass()


def localidad(nombre="Garupá", departamento="Capital", provincia="Misiones"):
    """Una localidad de Georef, ya cargada por la migración 0002 (Garupá, Capital, Misiones por defecto)."""
    return Localidad.objects.get(
        nombre_localidad=nombre,
        departamento__nombre_departamento=departamento,
        departamento__provincia__nombre_provincia=provincia,
    )


def crear_agronomo(email="agronomo@infoponia.com", **extra):
    """Un Agrónomo activo."""
    return crear_cuenta(Agronomo, email=email, **extra)


def crear_capataz_activo(email="capataz.inv@infoponia.com", **extra):
    """Un Capataz activo (con otro email que el de ``core.tests.fabricas.crear_capataz``)."""
    return crear_cuenta(Capataz, email=email, **extra)


def crear_vendedor(email="vendedor@infoponia.com", **extra):
    """Un Vendedor activo."""
    return crear_cuenta(Vendedor, email=email, **extra)


def crear_tecnico(email="tecnico@infoponia.com", **extra):
    """Un Técnico activo."""
    return crear_cuenta(Tecnico, email=email, **extra)


def datos_alta(tipo="urbana", **extra):
    """Los argumentos de ``alta_invernadero`` (sin el actor) para una dirección urbana o rural válida. ``extra``
    pisa o agrega cualquiera, por ejemplo ``nombre`` o ``agronomo_id``."""
    datos = {
        "nombre": "Invernadero A",
        "tipo_direccion": tipo,
        "localidad_id": localidad().pk,
    }
    if tipo == "urbana":
        datos |= {"calle": "Av. Uruguay", "numero_calle": "2450"}
    else:
        datos |= {"ruta": "Ruta Provincial 105", "kilometro": "4"}
    return datos | extra


def crear_invernadero(nombre="Invernadero B", activo=True, tipo="urbana", **personal):
    """Crea un invernadero directo en la base. ``personal`` acepta ``agronomo``, ``capataz``, ``vendedor`` y
    ``tecnico`` (instancias de cuenta)."""
    if tipo == "urbana":
        direccion = DireccionUrbana.objects.create(localidad=localidad(), calle="Calle 122", numero_calle="3310")
    else:
        direccion = DireccionRural.objects.create(localidad=localidad(), ruta="Ruta Nacional 14", kilometro="871")
    return Invernadero.objects.create(
        nombre_invernadero=nombre,
        estado_invernadero="activo" if activo else "inactivo",
        direccion=Direccion.objects.get(pk=direccion.pk),
        **personal,
    )


def crear_invernadero_con_geografia_propia(nombre="Invernadero B", activo=True, **personal):
    """Como ``crear_invernadero``, pero con una provincia, un departamento y una localidad propios en vez de Georef.
    Es para los ``TransactionTestCase`` (las pruebas de concurrencia): al terminar cada prueba, su ``flush`` vacía todas
    las tablas, Georef incluida, así que no se puede contar con las localidades de la migración."""
    provincia, _ = Provincia.objects.get_or_create(id_georef="99", defaults={"nombre_provincia": "Provincia de prueba"})
    departamento, _ = Departamento.objects.get_or_create(
        id_georef="99001", defaults={"nombre_departamento": "Departamento de prueba", "provincia": provincia}
    )
    sitio, _ = Localidad.objects.get_or_create(
        id_georef="99001001", defaults={"nombre_localidad": "Localidad de prueba", "departamento": departamento}
    )
    direccion = DireccionUrbana.objects.create(localidad=sitio, calle="Calle 122", numero_calle="3310")
    return Invernadero.objects.create(
        nombre_invernadero=nombre,
        estado_invernadero="activo" if activo else "inactivo",
        direccion=Direccion.objects.get(pk=direccion.pk),
        **personal,
    )


# ---- MAE-02a: alertas ----


class FallaDePrueba(Exception):
    """Falla propia de las pruebas: no es un ``RuntimeError``, para que un ``NotImplementedError`` (que sí lo es) no haga
    pasar por casualidad una prueba que espera que algo falle (los servicios nuevos arrancan con ``NotImplementedError``)."""


def tipo_falso(
    codigo="prueba_evento",
    destinatario=Destinatario.GERENTE,
    clase=Clase.EVENTO,
    severidad=Alerta.Severidad.ADVERTENCIA,
    origen=None,
):
    """Un ``TipoAlerta`` de prueba."""
    return TipoAlerta(
        codigo=codigo,
        nombre=f"Tipo {codigo}",
        destinatario=destinatario,
        severidad=severidad,
        clase=clase,
        origen=origen,
    )


@contextmanager
def tipo_de_alerta_de_prueba(*tipos):
    """Registra ``tipos`` mientras dura el bloque y los quita al terminar, aunque la prueba falle: no contamina el registro
    global (``mock.patch.dict`` restaura el diccionario). Devuelve el primero."""
    with mock.patch.dict(registro_de_alertas._TIPOS, {tipo.codigo: tipo for tipo in tipos}):
        yield tipos[0]


def crear_alerta(invernadero, tipo_alerta="prueba_evento", para_gerente=True, agronomo=None, resuelta=False, **extra):
    """Crea una alerta directo en la base (sin pasar por la API). ``resuelta=True`` la deja resuelta con su fecha."""
    if resuelta:
        extra.setdefault("estado_alerta", Alerta.Estado.RESUELTA)
        extra.setdefault("fecha_resolucion", timezone.now())
    return Alerta.objects.create(
        invernadero=invernadero,
        tipo_alerta=tipo_alerta,
        descripcion_alerta=extra.pop("descripcion_alerta", f"Alerta {tipo_alerta}"),
        nivel_severidad=extra.pop("nivel_severidad", Alerta.Severidad.ADVERTENCIA),
        para_gerente=para_gerente,
        agronomo=agronomo,
        **extra,
    )


# ---- MAE-03: tipos de etapa, sectores, cultivos, variedades y ciclos ----


def asegurar_datos_de_maestros():
    """Deja cargados y confirmados los cinco tipos de etapa (y, desde MAE-04, la configuración y el perfil) en la base de pruebas. La migración ``0005`` los carga al crear
    la base, pero un ``TransactionTestCase`` (de core o de las pruebas de concurrencia) vacía todas las tablas al terminar y,
    con ``--keepdb``, la base queda sin ellos. Si faltan, se vuelven a cargar con la misma función de la migración y se corre
    ``ANALYZE`` (docs/patrones/datos_de_migracion.md). Hay que llamarla fuera de la transacción de una clase."""
    if TipoEtapa.objects.count() < 5:
        importlib.import_module("maestros.migrations.0005_cargar_tipos_de_etapa").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE maestros_tipoetapa")
    # MAE-04: las dos filas únicas (configuración y perfil) también las vacía un ``flush``.
    if not (ConfiguracionOperativa.objects.exists() and PerfilOrganizacion.objects.exists()):
        importlib.import_module("maestros.migrations.0007_cargar_configuracion_y_perfil").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE maestros_configuracionoperativa, maestros_perfilorganizacion")


class ConDatosDeMaestros(ConGeoref):
    """Mixin para las clases que usan los tipos de etapa (y Georef): ``class MisTests(ConDatosDeMaestros, TestCase)``. Asegura
    los datos en ``setUpClass``, antes de que ``TestCase`` abra la transacción de la clase. Las clases de concurrencia
    (``TransactionTestCase``) también lo heredan, y dentro de cada prueba llaman a ``asegurar_datos_de_maestros()`` porque
    el ``flush`` de la prueba anterior vacía las tablas."""

    @classmethod
    def setUpClass(cls):
        asegurar_datos_de_maestros()
        super().setUpClass()


def tipo_etapa(codigo="germinacion"):
    """Un tipo de etapa del catálogo cargado por la migración (por su ``codigo``)."""
    return TipoEtapa.objects.get(codigo=codigo)


def crear_sector(invernadero, nombre="Sector 1", tipo="germinacion", agujeros=100, estado="activo"):
    """Crea un sector directo en la base (sin pasar por el servicio de alta)."""
    return SectorProduccion.objects.create(
        invernadero=invernadero,
        tipo_etapa=tipo_etapa(tipo),
        nombre_sector=nombre,
        cant_agujeros_total=agujeros,
        estado_sector=estado,
    )


def crear_cultivo(nombre="Lechuga", activo=True):
    """Crea un cultivo directo en la base."""
    return Cultivo.objects.create(nombre_cultivo=nombre, estado_cultivo="activo" if activo else "inactivo")


def crear_variedad(cultivo, nombre="Crespa", perfil="hoja_verde", activa=True):
    """Crea una variedad (columnas mínimas de MAE-03) directo en la base."""
    return Variedad.objects.create(
        cultivo=cultivo, nombre_variedad=nombre, perfil_familia=perfil, estado_variedad="activo" if activa else "inactivo"
    )


def crear_ciclo(variedad, *codigos):
    """Crea el ciclo de ``variedad`` con una etapa de 10 días por cada ``codigo`` de tipo de etapa (por defecto, solo
    germinación y maduración, las dos obligatorias)."""
    ciclo = Ciclo.objects.create(variedad=variedad)
    for codigo in codigos or ("germinacion", "maduracion"):
        EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo_etapa(codigo), duracion_estimada_dias=10)
    return ciclo


# ---- MAE-03: auxiliares de las pruebas de sectores y cultivos ----


def error_de(llamada):
    """Ejecuta ``llamada`` y devuelve la ``ValidationError`` que lanza; si no la lanza, la prueba falla."""
    from django.core.exceptions import ValidationError

    try:
        llamada()
    except ValidationError as error:
        return error
    raise AssertionError("Se esperaba una ValidationError y no se lanzó ninguna.")


def codigos_de(error, campo=None):
    """Los códigos de una ``ValidationError``; con ``campo``, solo los de ese campo (``NON_FIELD_ERRORS`` para los
    generales)."""
    if campo is None:
        return [e.code for errores in error.error_dict.values() for e in errores]
    return [e.code for e in error.error_dict.get(campo, [])]


def crear_agronomo_con_invernadero(nombre="Invernadero Uno", email="agronomo@infoponia.com"):
    """Un Agrónomo activo y un invernadero activo a su cargo: ``(agronomo, invernadero)``."""
    agronomo = crear_agronomo(email=email)
    return agronomo, crear_invernadero(nombre, agronomo=agronomo)


def con_agujeros(ocupados=0, comprometidos=0, **por_sector):
    """Reemplaza los registrantes de agujeros por uno falso que da ``(ocupados, comprometidos)`` a todos los sectores, salvo
    los de ``por_sector`` (``s<id>=(ocupados, comprometidos)``)."""
    from maestros import extensiones

    def falso(ids):
        return {i: por_sector.get(f"s{i}", (ocupados, comprometidos)) for i in ids}

    return mock.patch.object(extensiones, "_AGUJEROS", [falso])


def con_extension(nombre_de_lista, *funciones):
    """Reemplaza la lista de registrantes ``nombre_de_lista`` de ``maestros.extensiones`` por ``funciones``."""
    from maestros import extensiones

    return mock.patch.object(extensiones, nombre_de_lista, list(funciones))
