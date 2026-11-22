# Pruebas de los modelos del IoT (IOT-01, paso 1; docs/modelo/iot.md; D-72): UNA prueba por restricción de la base (la viola y no
# la viola), las migraciones de datos (catálogo y seis tipos iniciales, idempotentes y con su inversa) y los 14 parámetros IoT de
# la configuración operativa con su valor inicial y su dominio. Las restricciones se prueban saltándose los servicios, que son de
# las tareas siguientes: la base tiene que garantizarlas sola.

import importlib
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from maestros.models import PARAMETROS_IOT, ConfiguracionOperativa
from maestros.tests.fabricas import crear_alerta, crear_invernadero, crear_sector
from iot.models import (
    Accion,
    Actuador,
    AlertaIot,
    Capacidad,
    Comando,
    ComandoCatalogo,
    EquipoAnunciado,
    FotoperiodoDiario,
    Hardware,
    NodoCentral,
    ReglaActuacion,
    ResumenHorario,
    Sensor,
    SistemaIoT,
    Telemetria,
    TipoActuador,
)
from iot.tests import fabricas

CATALOGO = importlib.import_module("iot.migrations.0002_catalogo_de_capacidades")
INICIALES = importlib.import_module("iot.migrations.0003_tipos_de_actuador_iniciales")


class ViolaLaBase:
    """Auxiliar de las pruebas de restricciones: ``self.viola(lambda: ...)`` pasa si la base rechaza la operación con un
    ``IntegrityError``. El ``atomic`` interno deja usable la transacción de la prueba."""

    def viola(self, operacion):
        """Verifica que ``operacion()`` lance ``IntegrityError`` (la restricción de la base)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            operacion()


# ---- Tipos de actuador y acciones ----


class TipoActuadorYAccionTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """IOT-ALT-TAC, reglas 2, 3 y 4 (docs/modelo/iot.md, «TipoActuador» y «Accion»)."""

    def test_regla_2_el_nombre_del_tipo_es_unico_sin_distinguir_mayusculas(self):
        """IOT-ALT-TAC regla 2: dos tipos con el mismo nombre en distinta capitalización chocan; con otro nombre, no."""
        fabricas.tipo_actuador("Extractor")
        self.viola(lambda: TipoActuador.objects.create(nombre_actuador="EXTRACTOR"))
        TipoActuador.objects.create(nombre_actuador="Extractor de aire")

    def test_regla_2_el_nombre_es_unico_tambien_entre_los_inactivos(self):
        """IOT-ALT-TAC regla 2: la unicidad cuenta activos e inactivos."""
        fabricas.tipo_actuador("Extractor", activo=False)
        self.viola(lambda: TipoActuador.objects.create(nombre_actuador="extractor"))

    def test_regla_9_el_tiempo_minimo_no_es_negativo(self):
        """IOT-ALT-TAC regla 9: el tiempo mínimo entre comandos es un entero de 0 en adelante."""
        self.viola(lambda: TipoActuador.objects.create(nombre_actuador="Negativo", tiempo_minimo_entre_comandos=-1))
        TipoActuador.objects.create(nombre_actuador="Cero", tiempo_minimo_entre_comandos=0)

    def test_regla_4_la_unidad_y_el_rango_van_juntos(self):
        """IOT-ALT-TAC regla 4: unidad, mínimo y máximo, los tres nulos o los tres cargados."""
        tipo = fabricas.tipo_actuador(acciones=[("Encender", "ENCENDER")])
        nivel = fabricas.comando_del_catalogo("FIJAR_NIVEL")
        for datos in ({"unidad_valor": "%"}, {"valor_minimo": 0}, {"valor_minimo": 0, "valor_maximo": 100}, {"unidad_valor": "%", "valor_maximo": 100}):
            with self.subTest(datos=datos):
                self.viola(lambda: Accion.objects.create(tipo_actuador=tipo, nombre_accion="Nivel", comando=nivel, **datos))
        Accion.objects.create(tipo_actuador=tipo, nombre_accion="Nivel", comando=nivel, unidad_valor="%", valor_minimo=0, valor_maximo=100)

    def test_regla_4_el_minimo_es_menor_que_el_maximo(self):
        """IOT-ALT-TAC regla 4: con rango, el mínimo es menor que el máximo (iguales o al revés, no)."""
        tipo = fabricas.tipo_actuador(acciones=[])
        nivel = fabricas.comando_del_catalogo("FIJAR_NIVEL")
        for minimo, maximo in ((50, 50), (60, 10)):
            with self.subTest(minimo=minimo, maximo=maximo):
                self.viola(
                    lambda: Accion.objects.create(
                        tipo_actuador=tipo, nombre_accion="Nivel", comando=nivel, unidad_valor="%", valor_minimo=minimo, valor_maximo=maximo
                    )
                )

    def test_regla_3_el_nombre_de_la_accion_es_unico_en_el_tipo_entre_las_activas(self):
        """IOT-ALT-TAC regla 3: dos acciones activas del mismo tipo no tienen el mismo nombre (sin distinguir mayúsculas); una
        inactiva no cuenta, y el mismo nombre en otro tipo vale."""
        tipo = fabricas.tipo_actuador(acciones=[("Encender", "ENCENDER")])
        apagar = fabricas.comando_del_catalogo("APAGAR")
        self.viola(lambda: Accion.objects.create(tipo_actuador=tipo, nombre_accion="ENCENDER", comando=apagar))
        Accion.objects.create(tipo_actuador=fabricas.tipo_actuador(acciones=[]), nombre_accion="Encender", comando=apagar)
        Accion.objects.filter(tipo_actuador=tipo).update(estado="inactiva")
        Accion.objects.create(tipo_actuador=tipo, nombre_accion="Encender", comando=apagar)

    def test_regla_3_el_comando_de_la_accion_es_unico_en_el_tipo_entre_las_activas(self):
        """IOT-ALT-TAC regla 3: dos acciones activas del mismo tipo no usan el mismo comando; una inactiva no cuenta."""
        tipo = fabricas.tipo_actuador(acciones=[("Encender", "ENCENDER")])
        encender = fabricas.comando_del_catalogo("ENCENDER")
        self.viola(lambda: Accion.objects.create(tipo_actuador=tipo, nombre_accion="Prender", comando=encender))
        Accion.objects.filter(tipo_actuador=tipo).update(estado="inactiva")
        Accion.objects.create(tipo_actuador=tipo, nombre_accion="Prender", comando=encender)

    def test_r059_un_tipo_con_acciones_no_se_borra(self):
        """R059: la clave foránea de la acción es PROTECT."""
        tipo = fabricas.tipo_actuador()
        with self.assertRaises(ProtectedError):
            tipo.delete()


# ---- Sistema IoT y hardware ----


class SistemaIoTTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """R068 y MD-99: un sistema no inactivo por invernadero, token y rango de la solución."""

    def test_r068_un_solo_sistema_no_inactivo_por_invernadero(self):
        """MD-99: un segundo sistema activo (o desconectado) en el mismo invernadero choca; en otro invernadero, no."""
        invernadero = crear_invernadero("Norte")
        SistemaIoT.objects.create(invernadero=invernadero)
        for estado in ("activo", "desconectado"):
            with self.subTest(estado=estado):
                self.viola(lambda: SistemaIoT.objects.create(invernadero=invernadero, estado_sistema=estado))
        SistemaIoT.objects.create(invernadero=crear_invernadero("Sur"))

    def test_r068_un_sistema_inactivo_no_impide_registrar_otro(self):
        """MD-99: el sistema dado de baja no cuenta; después de la baja se registra otro, y puede haber varios inactivos."""
        invernadero = crear_invernadero("Norte")
        SistemaIoT.objects.create(invernadero=invernadero, estado_sistema="inactivo")
        SistemaIoT.objects.create(invernadero=invernadero, estado_sistema="inactivo")
        SistemaIoT.objects.create(invernadero=invernadero)

    def test_d70_el_resumen_del_token_es_unico_y_puede_faltar(self):
        """D-70 punto 3: dos sistemas no comparten el resumen del token; los nulos (después de la baja) no chocan."""
        SistemaIoT.objects.create(invernadero=crear_invernadero("A"), token_resumen="a" * 64)
        self.viola(lambda: SistemaIoT.objects.create(invernadero=crear_invernadero("B"), token_resumen="a" * 64))
        SistemaIoT.objects.create(invernadero=crear_invernadero("C"), token_resumen=None)
        SistemaIoT.objects.create(invernadero=crear_invernadero("D"), token_resumen=None)

    def test_regla_7_el_rango_de_la_solucion_son_los_dos_o_ninguno_con_minimo_menor(self):
        """IOT-MOD-SIS regla 7: los dos valores o ninguno, con el mínimo menor que el máximo."""
        sin_rango = SistemaIoT.objects.create(invernadero=crear_invernadero("A"))
        SistemaIoT.objects.create(invernadero=crear_invernadero("B"), temp_solucion_min=Decimal("18.0"), temp_solucion_max=Decimal("24.0"))
        for datos in ({"temp_solucion_min": Decimal("18.0")}, {"temp_solucion_max": Decimal("24.0")}, {"temp_solucion_min": Decimal("24.0"), "temp_solucion_max": Decimal("24.0")}):
            with self.subTest(datos=datos):
                self.viola(lambda: SistemaIoT.objects.filter(pk=sin_rango.pk).update(**datos))


class HardwareTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """MD-100 y D-72: las restricciones de la tabla base de los equipos."""

    def setUp(self):
        self.invernadero = crear_invernadero("Norte")
        self.sistema = fabricas.sistema(self.invernadero)

    def test_md100_un_identificador_no_se_repite_en_el_sistema_aunque_cambien_las_mayusculas(self):
        """MD-100: dos equipos con el mismo identificador en mayúsculas distintas chocan."""
        fabricas.sensor(self.sistema, "Temp-1")
        self.viola(lambda: fabricas.sensor(self.sistema, "TEMP-1"))

    def test_md100_el_identificador_puede_repetirse_en_otro_sistema(self):
        """MD-100: el mismo identificador en dos sistemas no choca."""
        fabricas.sensor(self.sistema, "TEMP-1")
        fabricas.sensor(fabricas.sistema(crear_invernadero("Sur")), "TEMP-1")

    def test_md100_un_equipo_dado_de_baja_no_impide_el_reemplazo(self):
        """MD-100: el reemplazo de un equipo dado de baja puede reusar su identificador (y al revés)."""
        fabricas.sensor(self.sistema, "TEMP-1", estado="inactivo")
        fabricas.sensor(self.sistema, "TEMP-1")
        fabricas.sensor(self.sistema, "TEMP-2")
        fabricas.sensor(self.sistema, "TEMP-2", estado="inactivo")

    def test_md100_un_equipo_fuera_de_servicio_si_cuenta_para_la_unicidad(self):
        """MD-100: solo los dados de baja quedan afuera; uno fuera de servicio sigue ocupando el identificador."""
        fabricas.sensor(self.sistema, "TEMP-1", estado="fuera_de_servicio")
        self.viola(lambda: fabricas.sensor(self.sistema, "temp-1"))

    def test_md100_el_nodo_no_tiene_identificador_y_los_demas_si(self):
        """MD-100: ``clase = nodo`` ⇔ identificador nulo."""
        nodo = Hardware.objects.get(sistema=self.sistema, clase="nodo")
        self.assertIsNone(nodo.identificador_equipo)
        self.viola(lambda: Hardware.objects.filter(pk=nodo.pk).update(identificador_equipo="NODO-1"))
        sensor = fabricas.sensor(self.sistema)
        self.viola(lambda: Hardware.objects.filter(pk=sensor.pk).update(identificador_equipo=None))

    def test_regla_21_de_8_20_el_nodo_no_tiene_sector(self):
        """Regla 21 de 8.20: ``clase = nodo`` ⇒ sector nulo; un sensor sí puede tenerlo."""
        sector = crear_sector(self.invernadero)
        nodo = Hardware.objects.get(sistema=self.sistema, clase="nodo")
        self.viola(lambda: Hardware.objects.filter(pk=nodo.pk).update(sector=sector))
        fabricas.sensor(self.sistema, sector=sector)

    def test_r066_un_sistema_tiene_un_solo_nodo(self):
        """R066 (1–1): un segundo nodo en el mismo sistema choca; en otro sistema, no."""
        def otro_nodo(sistema):
            return NodoCentral.objects.create(
                sistema=sistema, clase="nodo", nombre_nodo="Otro", modelo_hardware="RPi", fecha_instalacion=date(2026, 10, 1),
                insumo=fabricas.insumo_de_hardware(),
            )

        self.viola(lambda: otro_nodo(self.sistema))
        otro_nodo(SistemaIoT.objects.create(invernadero=crear_invernadero("Este")))

    def test_d72_el_segundo_nodo_choca_aunque_el_primero_este_dado_de_baja(self):
        """D-72 punto 2: el índice del nodo NO excluye las bajas, porque el nodo no se reemplaza (R066 = 1 – 1)."""
        Hardware.objects.filter(sistema=self.sistema, clase="nodo").update(estado_hardware="inactivo")
        self.viola(
            lambda: NodoCentral.objects.create(
                sistema=self.sistema, clase="nodo", nombre_nodo="Reemplazo", modelo_hardware="RPi",
                fecha_instalacion=date(2026, 10, 1), insumo=fabricas.insumo_de_hardware(),
            )
        )

    def test_r064_un_sistema_con_equipos_no_se_borra(self):
        """R064: la clave foránea del equipo al sistema es PROTECT."""
        with self.assertRaises(ProtectedError):
            self.sistema.delete()

    def test_md101_la_calibracion_del_sensor(self):
        """MD-101: en el nivel de la solución es nula; en las demás variables está completa y con mínimo < máximo."""
        fabricas.sensor(self.sistema, variable="nivel_solucion")
        self.viola(lambda: fabricas.sensor(self.sistema, variable="nivel_solucion", valor_calibracion_min=Decimal("0"), valor_calibracion_max=Decimal("10")))
        self.viola(lambda: fabricas.sensor(self.sistema, variable="temperatura", valor_calibracion_min=None, valor_calibracion_max=None))
        self.viola(lambda: fabricas.sensor(self.sistema, variable="temperatura", valor_calibracion_min=Decimal("30"), valor_calibracion_max=Decimal("30")))
        self.viola(lambda: fabricas.sensor(self.sistema, variable="humedad", valor_calibracion_min=Decimal("80"), valor_calibracion_max=Decimal("20")))
        fabricas.sensor(self.sistema, variable="humedad", valor_calibracion_min=Decimal("0"), valor_calibracion_max=Decimal("100"))

    def test_md101_la_unidad_del_sensor_la_fija_la_variable(self):
        """MD-101: la unidad no se guarda; sale de la variable (°C, % HR, lux, °C y sin unidad en el nivel)."""
        esperadas = {"temperatura": "°C", "humedad": "% HR", "intensidad_luz": "lux", "temperatura_solucion": "°C", "nivel_solucion": ""}
        for variable, unidad in esperadas.items():
            with self.subTest(variable=variable):
                self.assertEqual(fabricas.sensor(self.sistema, variable=variable).unidad_medida, unidad)

    def test_md102_un_actuador_es_de_un_tipo_y_puede_marcar_acciones_incompatibles(self):
        """MD-102 y R060: el actuador nace «sin verificar» y puede relacionarse con acciones de su tipo."""
        tipo = fabricas.tipo_actuador()
        equipo = fabricas.actuador(self.sistema, tipo)
        self.assertEqual(equipo.compatibilidad, Actuador.Compatibilidad.SIN_VERIFICAR)
        self.assertFalse(equipo.cambiado_en_invernadero)
        equipo.acciones_incompatibles.add(tipo.acciones.first())
        self.assertEqual(equipo.acciones_incompatibles.count(), 1)
        with self.assertRaises(ProtectedError):
            tipo.delete()


class EquipoAnunciadoTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """MD-102: lo que el nodo anunció es un dato de diseño."""

    def test_md102_el_identificador_anunciado_es_unico_por_sistema_sin_distinguir_mayusculas(self):
        """MD-102: dos anunciados con el mismo identificador en el mismo sistema chocan; en otro, no."""
        uno = SistemaIoT.objects.create(invernadero=crear_invernadero("A"))
        otro = SistemaIoT.objects.create(invernadero=crear_invernadero("B"))
        EquipoAnunciado.objects.create(sistema=uno, identificador_equipo="Ventilador-1", clase="actuador")
        self.viola(lambda: EquipoAnunciado.objects.create(sistema=uno, identificador_equipo="VENTILADOR-1", clase="actuador"))
        EquipoAnunciado.objects.create(sistema=otro, identificador_equipo="Ventilador-1", clase="actuador")

    def test_md102_al_borrar_un_sistema_se_borran_sus_equipos_anunciados(self):
        """MD-102 y «Convenciones» de docs/modelo/iot.md: ``EquipoAnunciado.sistema`` es CASCADE (dato de diseño), la excepción a
        «todas las claves foráneas son PROTECT». Sus comandos (la tabla intermedia) se van con él."""
        sistema = SistemaIoT.objects.create(invernadero=crear_invernadero("A"))
        anunciado = EquipoAnunciado.objects.create(sistema=sistema, identificador_equipo="V-1", clase="actuador")
        anunciado.comandos.add(fabricas.comando_del_catalogo("ENCENDER"))

        sistema.delete()

        self.assertFalse(EquipoAnunciado.objects.exists())
        self.assertTrue(ComandoCatalogo.objects.filter(codigo="ENCENDER").exists())


# ---- Lecturas ----


class TelemetriaTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """MD-107 y D-74 (punto 6): la lectura, su unicidad y sus resúmenes."""

    def setUp(self):
        self.sistema = fabricas.sistema(crear_invernadero("Norte"))
        self.sensor = fabricas.sensor(self.sistema)
        self.nivel = fabricas.sensor(self.sistema, variable="nivel_solucion")

    def test_d74_dos_lecturas_del_mismo_sensor_en_el_mismo_instante_chocan(self):
        """D-74 punto 6: no hay dos lecturas del mismo sensor con el mismo ``medida_en``; el mismo instante en otro sensor, sí."""
        primera = fabricas.telemetria(self.sensor)
        self.viola(lambda: fabricas.telemetria(self.sensor, medida_en=primera.medida_en))
        fabricas.telemetria(fabricas.sensor(self.sistema), medida_en=primera.medida_en)

    def test_d74_la_fabrica_usa_un_instante_distinto_en_cada_llamada(self):
        """La fábrica ``telemetria`` nunca repite ``medida_en``: dos llamadas seguidas no chocan."""
        fabricas.telemetria(self.sensor)
        fabricas.telemetria(self.sensor)
        self.assertEqual(Telemetria.objects.filter(sensor=self.sensor).count(), 2)

    def test_md107_la_lectura_tiene_valor_o_estado_de_nivel_pero_no_los_dos_ni_ninguno(self):
        """MD-107: ``num_nonnulls(valor_medido, estado_nivel_medido) = 1``."""
        ahora = fabricas.INSTANTE_BASE
        self.viola(lambda: Telemetria.objects.create(sensor=self.sensor, medida_en=ahora, valor_medido=Decimal("20"), estado_nivel_medido="bajo", valida=None))
        self.viola(lambda: Telemetria.objects.create(sensor=self.sensor, medida_en=ahora, valor_medido=None, estado_nivel_medido=None, valida=True))

    def test_md107_la_validez_es_nula_si_y_solo_si_es_un_nivel(self):
        """MD-107: ``valida`` nula ⇔ ``estado_nivel_medido`` no nulo."""
        ahora = fabricas.INSTANTE_BASE
        self.viola(lambda: Telemetria.objects.create(sensor=self.nivel, medida_en=ahora, estado_nivel_medido="bajo", valida=True))
        self.viola(lambda: Telemetria.objects.create(sensor=self.sensor, medida_en=ahora, valor_medido=Decimal("20"), valida=None))
        fabricas.telemetria(self.nivel, estado_nivel_medido="bajo")
        fabricas.telemetria(self.sensor, valida=False)

    def test_md107_el_estado_del_nivel_es_normal_o_bajo(self):
        """MD-107: el nivel de la solución es «normal» o «bajo»."""
        self.viola(lambda: fabricas.telemetria(self.nivel, estado_nivel_medido="alto"))

    def test_md107_el_resumen_horario_es_unico_por_sensor_y_hora(self):
        """MD-107: un solo resumen por ``(sensor, hora)``; la misma hora de otro sensor, no choca."""
        ResumenHorario.objects.create(sensor=self.sensor, hora=fabricas.INSTANTE_BASE)
        self.viola(lambda: ResumenHorario.objects.create(sensor=self.sensor, hora=fabricas.INSTANTE_BASE))
        ResumenHorario.objects.create(sensor=fabricas.sensor(self.sistema), hora=fabricas.INSTANTE_BASE)

    def test_md107_el_fotoperiodo_es_unico_por_sensor_y_dia_y_de_0_a_24_horas(self):
        """MD-107: un solo fotoperíodo por ``(sensor, fecha)``, de 0 a 24 horas."""
        luz = fabricas.sensor(self.sistema, variable="intensidad_luz")
        FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 1), horas=Decimal("12.50"))
        self.viola(lambda: FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 1), horas=Decimal("10")))
        self.viola(lambda: FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 2), horas=Decimal("24.01")))
        self.viola(lambda: FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 3), horas=Decimal("-0.01")))
        FotoperiodoDiario.objects.create(sensor=luz, fecha=date(2026, 11, 4), horas=Decimal("24"))

    def test_r063_un_sensor_con_lecturas_no_se_borra(self):
        """R063: la clave foránea de la lectura al sensor es PROTECT."""
        fabricas.telemetria(self.sensor)
        with self.assertRaises(ProtectedError):
            Sensor.objects.get(pk=self.sensor.pk).delete()


# ---- Reglas de actuación y comandos ----


class ReglaYComandoTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """MD-105 y MD-106: las reglas activas únicas y el comando pendiente único por actuador."""

    def setUp(self):
        self.sistema = fabricas.sistema(crear_invernadero("Norte"))
        self.sensor = fabricas.sensor(self.sistema)
        self.tipo = fabricas.tipo_actuador()
        self.actuador = fabricas.actuador(self.sistema, self.tipo)
        self.encender, self.apagar = self.tipo.acciones.order_by("id")

    def regla(self, condicion="supera_maximo", estado="activa", actuador=None, **extra):
        """Una regla del sensor y el actuador de la prueba."""
        return ReglaActuacion.objects.create(
            sensor=self.sensor, actuador=actuador or self.actuador, accion=self.encender, condicion=condicion, estado_regla=estado, **extra
        )

    def test_md106_a_lo_sumo_una_regla_activa_por_sensor_condicion_y_actuador(self):
        """MD-106: dos reglas activas iguales chocan; con otra condición, otro actuador o una inactiva, no."""
        self.regla()
        self.viola(lambda: self.regla())
        self.regla("baja_del_minimo")
        self.regla(actuador=fabricas.actuador(self.sistema, self.tipo))
        self.regla(estado="inactiva")
        self.regla(estado="inactiva")

    def test_md106_el_contador_de_confirmacion_no_es_negativo(self):
        """MD-106: ``contador_confirmacion >= 0``."""
        regla = self.regla()
        self.viola(lambda: ReglaActuacion.objects.filter(pk=regla.pk).update(contador_confirmacion=-1))

    def test_md106_la_regla_nace_sin_evaluar_con_el_contador_en_cero(self):
        """MD-106: ``ultima_evaluacion`` inicial «sin evaluar» y ``contador_confirmacion`` inicial 0."""
        regla = self.regla()
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("sin_evaluar", 0))

    def test_md105_un_solo_comando_pendiente_por_actuador(self):
        """MD-105: dos pendientes sobre el mismo actuador chocan, aunque uno venga de una regla; en otro actuador, no."""
        fabricas.comando(self.actuador, self.encender)
        self.viola(lambda: fabricas.comando(self.actuador, self.apagar, regla=self.regla()))
        fabricas.comando(fabricas.actuador(self.sistema, self.tipo), self.encender)

    def test_md105_los_comandos_resueltos_no_cuentan_como_pendientes(self):
        """MD-105: puede haber muchos comandos resueltos y uno pendiente sobre el mismo actuador."""
        for estado in ("ejecutado", "fallido", "cancelado", "ejecutado"):
            fabricas.comando(self.actuador, self.encender, estado=estado)
        fabricas.comando(self.actuador, self.apagar)

    def test_md105_la_resolucion_es_nula_si_y_solo_si_esta_pendiente(self):
        """MD-105: ``resuelto_en`` nula ⇔ pendiente."""
        self.viola(lambda: Comando.objects.create(actuador=self.actuador, accion=self.encender, estado_comando="ejecutado"))
        self.viola(lambda: Comando.objects.create(actuador=self.actuador, accion=self.encender, resuelto_en=fabricas.INSTANTE_BASE))

    def test_md105_los_intentos_no_son_negativos(self):
        """MD-105: ``cantidad_intentos >= 0``."""
        comando = fabricas.comando(self.actuador, self.encender)
        self.viola(lambda: Comando.objects.filter(pk=comando.pk).update(cantidad_intentos=-1))

    def test_md105_un_actuador_con_comandos_no_se_borra(self):
        """MD-105: la clave foránea del comando al actuador es PROTECT."""
        fabricas.comando(self.actuador, self.encender)
        with self.assertRaises(ProtectedError):
            Actuador.objects.get(pk=self.actuador.pk).delete()


# ---- Alertas ----


class AlertaIotTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """D-72 punto 4: el vínculo de la alerta con su origen."""

    def setUp(self):
        self.invernadero = crear_invernadero("Norte")
        self.sistema = fabricas.sistema(self.invernadero)
        self.sensor = fabricas.sensor(self.sistema)

    def test_c5_la_alerta_tiene_a_lo_sumo_un_origen(self):
        """Restricción C5: ``num_nonnulls(hardware, telemetria) <= 1``; con hardware solo, telemetría sola o ninguno, vale."""
        lectura = fabricas.telemetria(self.sensor)
        self.viola(lambda: AlertaIot.objects.create(alerta=crear_alerta(self.invernadero), sistema=self.sistema, hardware=self.sensor.hardware_ptr, telemetria=lectura))
        AlertaIot.objects.create(alerta=crear_alerta(self.invernadero), sistema=self.sistema, hardware=self.sensor.hardware_ptr)
        AlertaIot.objects.create(alerta=crear_alerta(self.invernadero), sistema=self.sistema, telemetria=lectura)
        AlertaIot.objects.create(alerta=crear_alerta(self.invernadero), sistema=self.sistema)

    def test_d72_una_alerta_tiene_un_solo_vinculo(self):
        """D-72 punto 4: ``alerta`` es un ``OneToOneField``: no hay dos vínculos para la misma alerta."""
        alerta = crear_alerta(self.invernadero)
        AlertaIot.objects.create(alerta=alerta, sistema=self.sistema)
        self.viola(lambda: AlertaIot.objects.create(alerta=alerta, sistema=self.sistema))

    def test_d71_d76_el_estado_del_correo_y_el_ultimo_mensaje_nacen_vacios(self):
        """D-71 y D-76 punto 3: ``correo_enviado_en`` y ``ultimo_mensaje_en`` nulos, ``intentos_correo`` en 0."""
        vinculo = AlertaIot.objects.create(alerta=crear_alerta(self.invernadero), sistema=self.sistema)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.ultimo_mensaje_en, vinculo.intentos_correo), (None, None, 0))


# ---- Migraciones de datos ----


def _vaciar_catalogo_y_tipos():
    """Borra los datos de las migraciones 0002 y 0003 (la prueba corre en una transacción: se deshace sola)."""
    Accion.objects.all().delete()
    TipoActuador.objects.all().delete()
    ComandoCatalogo.objects.all().delete()
    Capacidad.objects.all().delete()


class MigracionesDeDatosTests(fabricas.ConCatalogoIot, TestCase):
    """IOT-ALT-TAC reglas 5 y 7; docs/patrones/datos_de_migracion.md: el catálogo y los seis tipos iniciales."""

    def test_regla_7_el_catalogo_tiene_tres_capacidades_y_seis_comandos(self):
        """IOT-ALT-TAC regla 7: «encendido» (ENCENDER y APAGAR), «nivel» (FIJAR_NIVEL) y «posición» (ABRIR, CERRAR y FIJAR_POSICION)."""
        esperadas = {
            "encendido": {"ENCENDER", "APAGAR"},
            "nivel": {"FIJAR_NIVEL"},
            "posicion": {"ABRIR", "CERRAR", "FIJAR_POSICION"},
        }
        self.assertEqual(Capacidad.objects.count(), 3)
        self.assertEqual(ComandoCatalogo.objects.count(), 6)
        for codigo, comandos in esperadas.items():
            with self.subTest(capacidad=codigo):
                self.assertEqual({c.codigo for c in Capacidad.objects.get(codigo=codigo).comandos.all()}, comandos)

    def test_regla_8_solo_los_comandos_de_nivel_y_posicion_llevan_valor(self):
        """IOT-ALT-TAC regla 8: ``lleva_valor`` es verdadero solo en FIJAR_NIVEL y FIJAR_POSICION."""
        con_valor = set(ComandoCatalogo.objects.filter(lleva_valor=True).values_list("codigo", flat=True))
        self.assertEqual(con_valor, {"FIJAR_NIVEL", "FIJAR_POSICION"})

    def test_regla_5_los_seis_tipos_iniciales_con_sus_acciones(self):
        """IOT-ALT-TAC regla 5: seis tipos activos de 60 segundos, cada uno con sus acciones, comandos y rangos."""
        esperados = {
            "Ventilador": [("Encender", "ENCENDER", None), ("Apagar", "APAGAR", None), ("Fijar velocidad", "FIJAR_NIVEL", (0, 100, "%"))],
            "Bomba": [("Encender", "ENCENDER", None), ("Apagar", "APAGAR", None)],
            "Luminaria": [("Encender", "ENCENDER", None), ("Apagar", "APAGAR", None)],
            "Calefactor": [("Encender", "ENCENDER", None), ("Apagar", "APAGAR", None)],
            "Ventana": [("Abrir", "ABRIR", None), ("Cerrar", "CERRAR", None), ("Fijar posición", "FIJAR_POSICION", (0, 100, "%"))],
            "Media sombra": [("Abrir", "ABRIR", None), ("Cerrar", "CERRAR", None), ("Fijar posición", "FIJAR_POSICION", (0, 100, "%"))],
        }
        self.assertEqual(TipoActuador.objects.count(), 6)
        for nombre, acciones in esperados.items():
            with self.subTest(tipo=nombre):
                tipo = TipoActuador.objects.get(nombre_actuador=nombre)
                self.assertEqual((tipo.tiempo_minimo_entre_comandos, tipo.estado), (60, "activo"))
                obtenidas = [
                    (a.nombre_accion, a.comando.codigo, (a.valor_minimo, a.valor_maximo, a.unidad_valor) if a.comando.lleva_valor else None)
                    for a in tipo.acciones.order_by("id")
                ]
                self.assertEqual(obtenidas, acciones)
                self.assertTrue(all(a.estado == "activa" for a in tipo.acciones.all()))
                if any(a.comando.lleva_valor for a in tipo.acciones.all()):
                    continue
                self.assertTrue(all((a.unidad_valor, a.valor_minimo, a.valor_maximo) == (None, None, None) for a in tipo.acciones.all()))

    def test_las_migraciones_sobre_tablas_vacias_cargan_todo(self):
        """Con las tablas vacías, ``cargar`` de la 0002 y de la 0003 (en ese orden) deja el catálogo y los seis tipos."""
        _vaciar_catalogo_y_tipos()
        CATALOGO.cargar(apps, None)
        INICIALES.cargar(apps, None)
        self.assertEqual((Capacidad.objects.count(), ComandoCatalogo.objects.count(), TipoActuador.objects.count()), (3, 6, 6))
        self.assertEqual(Accion.objects.count(), 3 + 2 + 2 + 2 + 3 + 3)

    def test_correr_las_migraciones_dos_veces_no_duplica(self):
        """Idempotentes (docs/patrones/datos_de_migracion.md): una segunda ejecución no duplica nada."""
        for _ in range(2):
            CATALOGO.cargar(apps, None)
            INICIALES.cargar(apps, None)
        self.assertEqual((Capacidad.objects.count(), ComandoCatalogo.objects.count(), TipoActuador.objects.count()), (3, 6, 6))
        self.assertEqual(Accion.objects.count(), 15)

    def test_los_tipos_iniciales_no_pisan_un_tipo_con_el_mismo_nombre(self):
        """Regla 5 de IOT-ALT-TAC: si ya existe un tipo con ese nombre (sin distinguir mayúsculas), no se toca ni se le agregan acciones."""
        _vaciar_catalogo_y_tipos()
        CATALOGO.cargar(apps, None)
        propio = fabricas.tipo_actuador("VENTILADOR", tiempo_minimo=5, acciones=[("Girar", "ENCENDER")])

        INICIALES.cargar(apps, None)

        self.assertEqual(TipoActuador.objects.count(), 6)
        propio.refresh_from_db()
        self.assertEqual((propio.nombre_actuador, propio.tiempo_minimo_entre_comandos), ("VENTILADOR", 5))
        self.assertEqual([a.nombre_accion for a in propio.acciones.all()], ["Girar"])

    def test_el_catalogo_no_pisa_el_nombre_de_una_capacidad_existente(self):
        """Idempotente por código: ``cargar`` no revierte el nombre de una capacidad que ya existe."""
        Capacidad.objects.filter(codigo="nivel").update(nombre="Potencia")
        CATALOGO.cargar(apps, None)
        self.assertEqual(Capacidad.objects.get(codigo="nivel").nombre, "Potencia")

    def test_descargar_borra_los_datos_iniciales_si_nadie_los_usa(self):
        """La inversa de la 0003 y la de la 0002 borran los tipos y el catálogo si nada los usa."""
        INICIALES.descargar(apps, None)
        self.assertFalse(TipoActuador.objects.exists())
        CATALOGO.descargar(apps, None)
        self.assertFalse(ComandoCatalogo.objects.exists() or Capacidad.objects.exists())

    def test_descargar_conserva_un_tipo_que_tiene_un_actuador(self):
        """La inversa de la 0003 no borra un tipo inicial con un actuador (no destruye datos de la organización)."""
        sistema = fabricas.sistema(crear_invernadero("Norte"))
        ventilador = TipoActuador.objects.get(nombre_actuador="Ventilador")
        fabricas.actuador(sistema, ventilador)

        INICIALES.descargar(apps, None)

        self.assertEqual(list(TipoActuador.objects.values_list("nombre_actuador", flat=True)), ["Ventilador"])
        CATALOGO.descargar(apps, None)
        self.assertEqual(ComandoCatalogo.objects.count(), 6)


# ---- Parámetros IoT de la configuración operativa ----

INICIALES_IOT = {
    "cant_reintentos_comando": 3,
    "segundos_intervalo_reintento": 60,
    "hora_inicio_luz": 8,
    "hora_fin_luz": 18,
    "lux_umbral_fotoperiodo": 1000,
    "minutos_sin_actividad": 5,
    "minutos_sin_comunicacion": 3,
    "minutos_antiguedad_lectura": 5,
    "cant_lecturas_confirmacion": 3,
    "histeresis_temperatura": Decimal("1.0"),
    "histeresis_humedad": 3,
    "histeresis_luz": 2000,
    "histeresis_temp_solucion": Decimal("1.0"),
    "dias_retencion_telemetria": 7,
}
# Los dominios de docs/modelo/iot.md, «Parámetros IoT de ConfiguracionOperativa», escritos acá aparte del modelo.
DOMINIOS_IOT = {
    "cant_reintentos_comando": (0, 10),
    "segundos_intervalo_reintento": (10, 3600),
    "hora_inicio_luz": (0, 23),
    "hora_fin_luz": (1, 24),
    "lux_umbral_fotoperiodo": (1, 100000),
    "minutos_sin_actividad": (1, 1440),
    "minutos_sin_comunicacion": (1, 1440),
    "minutos_antiguedad_lectura": (1, 1440),
    "cant_lecturas_confirmacion": (1, 10),
    "histeresis_temperatura": (0, 10),
    "histeresis_humedad": (0, 30),
    "histeresis_luz": (0, 20000),
    "histeresis_temp_solucion": (0, 10),
    "dias_retencion_telemetria": (1, 365),
}


class ParametrosIotTests(fabricas.ConCatalogoIot, ViolaLaBase, TestCase):
    """MD-112: los 14 parámetros IoT de ``ConfiguracionOperativa``, con su valor inicial y su dominio en la base."""

    def test_md112_son_catorce(self):
        """MD-112: la lista del modelo tiene los 14 parámetros de la ficha, y ningún otro."""
        self.assertEqual(len(PARAMETROS_IOT), 14)
        self.assertEqual({campo for campo, *_ in PARAMETROS_IOT}, set(INICIALES_IOT))

    def test_md112_la_fila_existente_tiene_los_valores_iniciales(self):
        """MD-112: la fila de configuración que ya existía queda con el valor inicial de cada parámetro."""
        configuracion = ConfiguracionOperativa.objects.get()
        for campo, valor in INICIALES_IOT.items():
            with self.subTest(campo=campo):
                self.assertEqual(getattr(configuracion, campo), valor)

    def test_md112_el_modelo_y_la_lista_coinciden_con_la_ficha(self):
        """Los ``default`` de los campos y los dominios de ``PARAMETROS_IOT`` son los de la ficha (no se separan)."""
        for campo, _, inicial, minimo, maximo in PARAMETROS_IOT:
            with self.subTest(campo=campo):
                self.assertEqual(ConfiguracionOperativa._meta.get_field(campo).default, inicial)
                self.assertEqual((minimo, maximo), DOMINIOS_IOT[campo])

    def test_md112_las_histeresis_de_temperatura_son_decimales_de_un_lugar(self):
        """MD-112: las dos histéresis de temperatura son ``Decimal(3,1)``; las demás, enteros."""
        for campo in ("histeresis_temperatura", "histeresis_temp_solucion"):
            campo_del_modelo = ConfiguracionOperativa._meta.get_field(campo)
            self.assertEqual((campo_del_modelo.max_digits, campo_del_modelo.decimal_places), (3, 1))
        self.assertEqual(ConfiguracionOperativa._meta.get_field("histeresis_humedad").get_internal_type(), "IntegerField")

    def test_md112_un_valor_fuera_de_dominio_se_rechaza_en_la_base(self):
        """MD-112: un valor por debajo del mínimo o por encima del máximo viola el ``CheckConstraint`` del parámetro."""
        for campo, (minimo, maximo) in DOMINIOS_IOT.items():
            for fuera in (minimo - 1, maximo + 1):
                with self.subTest(campo=campo, valor=fuera):
                    self.viola(lambda: ConfiguracionOperativa.objects.filter(singleton=1).update(**{campo: fuera}))

    def test_md112_los_extremos_del_dominio_valen(self):
        """MD-112: el mínimo y el máximo de cada parámetro se aceptan (las horas de luz, en un par coherente)."""
        for campo, (minimo, maximo) in DOMINIOS_IOT.items():
            if campo.startswith("hora_"):
                continue
            for extremo in (minimo, maximo):
                with self.subTest(campo=campo, valor=extremo):
                    ConfiguracionOperativa.objects.filter(singleton=1).update(**{campo: extremo})
        for inicio, fin in ((0, 1), (23, 24)):
            ConfiguracionOperativa.objects.filter(singleton=1).update(hora_inicio_luz=inicio, hora_fin_luz=fin)

    def test_md112_el_fin_del_horario_de_luz_es_posterior_al_inicio(self):
        """MD-112: ``hora_fin_luz > hora_inicio_luz`` (iguales o al revés se rechazan)."""
        for inicio, fin in ((10, 10), (18, 8)):
            with self.subTest(inicio=inicio, fin=fin):
                self.viola(lambda: ConfiguracionOperativa.objects.filter(singleton=1).update(hora_inicio_luz=inicio, hora_fin_luz=fin))
