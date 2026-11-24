# Fábricas compartidas por las pruebas de iot/tests/ (IOT-01, paso 1): arman tipos de actuador, sistemas con su nodo, sensores,
# actuadores, lecturas y comandos DIRECTO en la base, sin pasar por servicios (que crean las tareas siguientes), para que
# IOT-02 en adelante prueben sin depender de ellos. Reutilizan las fábricas de cuentas, invernaderos e insumos de las otras apps.
# Una sola firma por función. Los datos de la migración (catálogo y tipos iniciales) siguen docs/patrones/datos_de_migracion.md.

import importlib
import itertools
from datetime import date, datetime, timedelta, timezone as zona
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.db import connection
from django.utils import timezone

from inventario.categorias import REPUESTOS_DE_HARDWARE
from inventario.models import Insumo
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, categoria_del_sistema
from iot.models import (
    Accion,
    Actuador,
    Capacidad,
    Comando,
    ComandoCatalogo,
    MantenimientoTecnico,
    NodoCentral,
    Sensor,
    SistemaIoT,
    Telemetria,
    TipoActuador,
)

# Un contador por tipo de dato: los nombres de las fábricas no se repiten entre llamadas (el nombre del tipo es único).
_numeros = itertools.count(1)
# La fecha base de las lecturas: cada llamada de ``telemetria`` suma un minuto, así dos lecturas del mismo sensor nunca
# comparten ``medida_en`` (índice único de D-74, punto 6) salvo que la prueba lo pida.
_instantes = itertools.count(0)
INSTANTE_BASE = datetime(2026, 11, 1, 12, 0, tzinfo=zona.utc)


def asegurar_datos_de_iot():
    """Deja cargados y confirmados el catálogo de capacidades y los seis tipos iniciales en la base de pruebas. Las migraciones
    ``0002`` y ``0003`` los cargan al crear la base, pero un ``TransactionTestCase`` vacía todas las tablas al terminar y, con
    ``--keepdb``, la base queda sin ellos. Si faltan, se vuelven a cargar con la misma función de la migración y se corre
    ``ANALYZE`` (docs/patrones/datos_de_migracion.md). Hay que llamarla fuera de la transacción de una clase."""
    asegurar_datos_de_inventario()
    if ComandoCatalogo.objects.count() < 6:
        importlib.import_module("iot.migrations.0002_catalogo_de_capacidades").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE iot_capacidad, iot_comandocatalogo")
    if not TipoActuador.objects.exists():
        importlib.import_module("iot.migrations.0003_tipos_de_actuador_iniciales").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE iot_tipoactuador, iot_accion")


class ConCatalogoIot(ConDatosDeInventario):
    """Mixin: ``class MisTests(ConCatalogoIot, TestCase)``. Asegura el catálogo del IoT, las categorías de inventario y los datos
    de maestros en ``setUpClass``, antes de que ``TestCase`` abra la transacción de la clase. Las clases de concurrencia
    (``TransactionTestCase``) también lo heredan y, dentro de cada prueba, llaman a ``asegurar_datos_de_iot()`` en ``setUp``
    porque el ``flush`` de la prueba anterior vacía las tablas."""

    @classmethod
    def setUpClass(cls):
        asegurar_datos_de_iot()
        super().setUpClass()


def comando_del_catalogo(codigo):
    """Un comando del catálogo (``ENCENDER``, ``APAGAR``, ``FIJAR_NIVEL``, ``ABRIR``, ``CERRAR`` o ``FIJAR_POSICION``)."""
    return ComandoCatalogo.objects.get(codigo=codigo)


def capacidad(codigo):
    """Una capacidad del catálogo (``encendido``, ``nivel`` o ``posicion``)."""
    return Capacidad.objects.get(codigo=codigo)


def tipo_actuador(nombre=None, tiempo_minimo=60, acciones=None, activo=True):
    """Un tipo de actuador creado directo en la base, con sus acciones. ``acciones`` es una lista de tuplas
    ``(nombre, comando)`` o ``(nombre, comando, mínimo, máximo, unidad)``; por defecto, «Encender» y «Apagar». Sin ``nombre``,
    uno único («Tipo de prueba N»)."""
    nombre = nombre or f"Tipo de prueba {next(_numeros)}"
    tipo = TipoActuador.objects.create(
        nombre_actuador=nombre,
        tiempo_minimo_entre_comandos=tiempo_minimo,
        estado="activo" if activo else "inactivo",
    )
    for datos in acciones if acciones is not None else [("Encender", "ENCENDER"), ("Apagar", "APAGAR")]:
        nombre_accion, comando, *rango = datos
        minimo, maximo, unidad = rango if rango else (None, None, None)
        Accion.objects.create(
            tipo_actuador=tipo,
            nombre_accion=nombre_accion,
            comando=comando_del_catalogo(comando),
            valor_minimo=minimo,
            valor_maximo=maximo,
            unidad_valor=unidad,
        )
    return tipo


def insumo_de_hardware(nombre=None):
    """Un insumo de la categoría del sistema ``repuestos_de_hardware`` (R072), el que exige todo equipo."""
    return Insumo.objects.create(
        nombre_insumo=nombre or f"Repuesto {next(_numeros)}",
        tipo_insumo=categoria_del_sistema(REPUESTOS_DE_HARDWARE),
        unidad_medida_insumo="unidad",
    )


def sistema(invernadero, estado="activo", **extra):
    """Un sistema IoT del ``invernadero`` con su nodo central, creados directo en la base. ``extra`` pisa campos del sistema."""
    sistema_iot = SistemaIoT.objects.create(invernadero=invernadero, estado_sistema=estado, **extra)
    NodoCentral.objects.create(
        sistema=sistema_iot,
        clase="nodo",
        nombre_nodo="Nodo de prueba",
        modelo_hardware="Raspberry Pi 4",
        fecha_instalacion=date(2026, 10, 1),
        insumo=insumo_de_hardware(),
        estado_hardware="inactivo" if estado == "inactivo" else "activo",
    )
    return sistema_iot


def sensor(sistema_iot, identificador=None, variable="temperatura", estado="activo", sector=None, **extra):
    """Un sensor del sistema, con una calibración válida (y sin ella en el nivel de la solución). ``extra`` pisa campos."""
    identificador = identificador or f"SENS-{next(_numeros)}"
    if variable != "nivel_solucion":
        extra.setdefault("valor_calibracion_min", Decimal("-10.00"))
        extra.setdefault("valor_calibracion_max", Decimal("60.00"))
    return Sensor.objects.create(
        sistema=sistema_iot,
        clase="sensor",
        identificador_equipo=identificador,
        tipo_variable_sensor=variable,
        modelo_hardware="DHT22",
        fecha_instalacion=date(2026, 10, 1),
        estado_hardware=estado,
        insumo=insumo_de_hardware(),
        sector=sector,
        **extra,
    )


def actuador(sistema_iot, tipo=None, identificador=None, estado="activo", sector=None, **extra):
    """Un actuador del sistema, de un ``tipo`` (por defecto, uno nuevo con «Encender» y «Apagar»). ``extra`` pisa campos."""
    return Actuador.objects.create(
        sistema=sistema_iot,
        clase="actuador",
        identificador_equipo=identificador or f"ACT-{next(_numeros)}",
        tipo_actuador=tipo or tipo_actuador(),
        modelo_hardware="Relé 4 canales",
        fecha_instalacion=date(2026, 10, 1),
        estado_hardware=estado,
        insumo=insumo_de_hardware(),
        sector=sector,
        **extra,
    )


def telemetria(sensor_medido, valor="25.00", medida_en=None, **extra):
    """Una lectura del sensor. Sin ``medida_en``, usa un instante distinto en cada llamada (un minuto más que la anterior), así
    dos lecturas del mismo sensor nunca chocan con el índice único ``(sensor, medida_en)``. En un sensor de nivel, ``valor`` se
    ignora y la lectura es «normal» salvo que ``extra`` diga otra cosa."""
    medida_en = medida_en or INSTANTE_BASE + timedelta(minutes=next(_instantes))
    if sensor_medido.tipo_variable_sensor == "nivel_solucion":
        datos = {"estado_nivel_medido": "normal", "valor_medido": None, "valida": None, "unidad_medida_telemetria": None}
    else:
        datos = {"valor_medido": Decimal(str(valor)), "valida": True, "unidad_medida_telemetria": sensor_medido.unidad_medida}
    return Telemetria.objects.create(sensor=sensor_medido, medida_en=medida_en, **(datos | extra))


def comando(actuador_destino, accion, estado="pendiente", **extra):
    """Un comando del actuador con su ``accion``. Un comando que no está pendiente lleva su ``resuelto_en`` (la base lo exige);
    ``extra`` pisa cualquier campo."""
    datos = {"estado_comando": estado}
    if estado != "pendiente":
        datos["resuelto_en"] = INSTANTE_BASE
    return Comando.objects.create(actuador=actuador_destino, accion=accion, **(datos | extra))


def mantenimiento_tecnico(invernadero, tecnico, equipos, estado="a_realizar", **extra):
    """Una orden de mantenimiento (``MantenimientoTecnico``) del ``invernadero`` para ``tecnico``, con los ``equipos`` (una lista: «al menos uno», R057), creada directo en la base y
    sin pasar por los servicios. Por defecto, como la automática: «revisión», prioridad alta, programada para hoy y sin Agrónomo. El código sale de ``siguiente_numero``. Una orden
    «cancelada» queda con su motivo y la fecha de hoy; una «concretada», solo con la fecha. ``extra`` pisa cualquier campo. Es una función y no una clase: este archivo usa funciones
    (el extracto de IOT-07 la llama ``MantenimientoTecnicoFactory``)."""
    from produccion.servicios import ordenes

    hoy = timezone.localdate()
    datos = {
        "numero": ordenes.siguiente_numero(),
        "fecha_creacion_orden": hoy,
        "fecha_programada_orden": hoy,
        "prioridad_orden": "alta",
        "estado_orden": estado,
        "agronomo": None,
    }
    if estado != "a_realizar":
        datos["fecha_resolucion_orden"] = hoy
    if estado == "cancelada":
        datos["motivo_cancelacion"] = "Motivo de prueba"
    orden = MantenimientoTecnico.objects.create(invernadero=invernadero, tecnico=tecnico, **(datos | extra))
    orden.hardware.set(equipos)
    return orden


# ---- datos de formulario de los tipos de actuador (IOT-01, paso 3) ----
# Los dos ``dataclass`` y los servicios están en ``iot/servicios/tipos_actuador.py``: se importan dentro de cada función para que,
# mientras el servicio no existe, falle cada prueba y no se caiga la importación de todo el archivo.


def accion_de_formulario(nombre, comando, minimo=None, maximo=None, unidad=None, id=None):
    """Los datos de una fila del formulario de acciones (``DatosDeAccion``): ``comando`` es el código del catálogo e ``id``, el de
    la acción original si la tenía."""
    from iot.servicios.tipos_actuador import DatosDeAccion

    return DatosDeAccion(nombre=nombre, comando=comando, minimo=minimo, maximo=maximo, unidad=unidad, id=id)


def datos_de_tipo(nombre="Extractor", tiempo_minimo=60, acciones=None):
    """Los datos del formulario de un tipo (``DatosDeTipoActuador``). Sin ``acciones``, «Encender» y «Apagar»."""
    from iot.servicios.tipos_actuador import DatosDeTipoActuador

    if acciones is None:
        acciones = [accion_de_formulario("Encender", "ENCENDER"), accion_de_formulario("Apagar", "APAGAR")]
    return DatosDeTipoActuador(nombre=nombre, tiempo_minimo=tiempo_minimo, acciones=list(acciones))


def datos_de(tipo):
    """El formulario de un tipo guardado, sin ningún cambio: cada acción ACTIVA con el id de la original. Las pruebas de
    modificación parten de acá y cambian lo que quieren probar."""
    acciones = [
        accion_de_formulario(a.nombre_accion, a.comando.codigo, a.valor_minimo, a.valor_maximo, a.unidad_valor, id=a.pk)
        for a in tipo.acciones.filter(estado="activa").select_related("comando").order_by("id")
    ]
    return datos_de_tipo(tipo.nombre_actuador, tipo.tiempo_minimo_entre_comandos, acciones)


# ---- sistema IoT (IOT-02, paso 3) ----


def con_iot_registrado():
    """``mock.patch`` que deja, mientras dura, un registrante falso de ``maestros.extensiones.registrar_estado_iot`` que lee los
    sistemas directo de la base (sin URLs): así ``Invernadero.tiene_sistema_iot()`` es verdadero con un sistema activo o desconectado
    y ``sincronizar_alertas_de_personal`` crea la alerta del Técnico. Las pruebas de los servicios lo usan para no depender de los
    registrantes reales de ``iot`` (que prueba ``test_registrantes_maestros.py``). Uso: ``self.enterContext(con_iot_registrado())``."""
    from maestros import extensiones
    from maestros.extensiones import EstadoIot

    def estados(ids):
        sistemas = SistemaIoT.objects.filter(invernadero_id__in=ids).exclude(estado_sistema="inactivo")
        return {s.invernadero_id: EstadoIot(s.estado_sistema, "/iot/sistema/") for s in sistemas}

    return mock.patch.object(extensiones, "_ESTADO_IOT", [(estados, lambda actor, invernadero: None)])


def datos_de_sistema(invernadero, insumo=None, **extra):
    """Los datos del formulario de un sistema (``DatosDeSistema``) del ``invernadero``, válidos: nombre, modelo, fecha de instalación
    de ayer y un insumo de «Repuestos de hardware» (uno nuevo si no se pasa ``insumo``). ``extra`` pisa cualquier campo (por ejemplo
    ``temp_min="10"``)."""
    from iot.servicios.sistemas import DatosDeSistema

    datos = {
        "invernadero_id": invernadero.pk,
        "nombre": "Raspberry del galpón",
        "modelo": "Raspberry Pi 4",
        "numero_serie": "",
        "fecha_instalacion": timezone.localdate() - timedelta(days=1),
        "insumo_id": (insumo or insumo_de_hardware()).pk,
        "temp_min": "",
        "temp_max": "",
    }
    return DatosDeSistema(**(datos | extra))


def datos_de_sistema_guardado(sistema_iot, **extra):
    """El formulario de modificación de un sistema guardado, sin ningún cambio (nombre, modelo, serie y rango del nodo). Las pruebas de
    modificación parten de acá y cambian lo que quieren probar."""
    nodo = NodoCentral.objects.get(sistema=sistema_iot)
    datos = {
        "nombre": nodo.nombre_nodo,
        "modelo": nodo.modelo_hardware,
        "numero_serie": nodo.numero_serie,
        "temp_min": "" if sistema_iot.temp_solucion_min is None else str(sistema_iot.temp_solucion_min),
        "temp_max": "" if sistema_iot.temp_solucion_max is None else str(sistema_iot.temp_solucion_max),
    }
    return datos_de_sistema(sistema_iot.invernadero, **(datos | extra))


# ---- hardware (IOT-02, paso 4) ----


def datos_de_equipo(clase="sensor", **extra):
    """Los datos del formulario de un equipo (``DatosDeEquipo``), válidos: un sensor de temperatura con calibración 0 a 50 o un actuador
    de un tipo nuevo (con «Encender» y «Apagar»), con fecha de ayer y un insumo de «Repuestos de hardware» nuevo. ``extra`` pisa cualquier campo."""
    from iot.servicios.hardware import DatosDeEquipo

    datos = {
        "clase": clase,
        "identificador": "norte/sectorA/temperatura" if clase == "sensor" else "norte/sectorA/ventilador",
        "modelo": "DHT22" if clase == "sensor" else "Relé 4 canales",
        "numero_serie": "",
        "fecha_instalacion": timezone.localdate() - timedelta(days=1),
        "insumo_id": insumo_de_hardware().pk,
        "sector_id": None,
    }
    if clase == "sensor":
        datos |= {"variable": "temperatura", "nombre_sensor": "", "calibracion_min": "0", "calibracion_max": "50"}
    else:
        datos |= {"tipo_actuador_id": tipo_actuador().pk, "descripcion": ""}
    return DatosDeEquipo(**(datos | extra))


def datos_de_equipo_guardado(equipo, **extra):
    """El formulario de un sensor o actuador guardado, sin ningún cambio. Las pruebas de modificación parten de acá y cambian lo que
    quieren probar. La fecha y el insumo no se editan (se ignoran al modificar)."""
    datos = {
        "identificador": equipo.identificador_equipo,
        "modelo": equipo.modelo_hardware,
        "numero_serie": equipo.numero_serie,
        "fecha_instalacion": equipo.fecha_instalacion,
        "insumo_id": equipo.insumo_id,
        "sector_id": equipo.sector_id,
    }
    if equipo.clase == "sensor":
        datos |= {
            "variable": equipo.tipo_variable_sensor,
            "nombre_sensor": equipo.nombre_sensor,
            "calibracion_min": "" if equipo.valor_calibracion_min is None else str(equipo.valor_calibracion_min),
            "calibracion_max": "" if equipo.valor_calibracion_max is None else str(equipo.valor_calibracion_max),
        }
    else:
        datos |= {"tipo_actuador_id": equipo.tipo_actuador_id, "descripcion": equipo.descripcion_actuador}
    clase_del_formulario = extra.pop("clase", equipo.clase)  # el formulario puede mandar otra clase: el servicio la ignora
    formulario = datos_de_equipo(equipo.clase, **(datos | extra))
    formulario.clase = clase_del_formulario
    return formulario


def equipo_anunciado(sistema_iot, identificador, comandos=("ENCENDER", "APAGAR"), clase="actuador"):
    """Un ``EquipoAnunciado`` del sistema: lo que el nodo anunció (IOT-ENT-INF, extensión 1c), con los códigos de ``comandos`` del catálogo
    (vacío en un sensor). Lo escribe la API de IOT-03; hasta entonces lo crean las pruebas con esta fábrica."""
    from iot.models import EquipoAnunciado

    anunciado = EquipoAnunciado.objects.create(sistema=sistema_iot, identificador_equipo=identificador, clase=clase)
    anunciado.comandos.set(ComandoCatalogo.objects.filter(codigo__in=comandos if clase == "actuador" else ()))
    return anunciado


def regla(sensor_que_mide, actuador_que_actua, accion=None, condicion="supera_maximo", **extra):
    """Una regla de actuación activa del sensor sobre el actuador, con una acción del tipo del actuador (la primera activa por defecto)."""
    from iot.models import ReglaActuacion

    accion = accion or actuador_que_actua.tipo_actuador.acciones.filter(estado="activa").order_by("id").first()
    return ReglaActuacion.objects.create(
        sensor=sensor_que_mide, actuador=actuador_que_actua, accion=accion, condicion=condicion, **extra
    )
