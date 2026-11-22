# Pruebas de IOT-CNS-HDW · Consultar Hardware (docs/casos_de_uso/iot/hardware.md, v0.2, con «Cómo se aplica en la ronda IoT 1») y de lo que cita:
# D-28 (alcance en un único lugar; 404 fuera del alcance) y SEG-14 (la consulta no se audita). Se escribieron ANTES que el servicio.
#
# Servicios que se prueban (iot/servicios/hardware.py), tomados del módulo dentro de cada prueba:
#   buscar_equipos(actor, sistema, filtros: dict) -> [Sensor | Actuador]     (sensores y después actuadores, por identificador; sin el nodo)
#       filtros: ``q`` (identificador, nombre del sensor, tipo, variable o serie), ``tipo`` (sensor | actuador), ``estado``, ``sector`` (id o «_» = general)
#   ficha_del_equipo(actor, equipo_id) -> Sensor | Actuador
#   situacion_de(equipo) -> Situacion(clave, texto)
#   alertas_activas_del_equipo(equipo) -> [Alerta]
#   acciones_permitidas(actor, equipo) -> frozenset de {"modificar", "volver_a_activar", "reactivar"}
# Errores: ``PermissionDenied`` (rol) y ``Http404`` (sistema o equipo fuera del alcance de consulta o inexistente).

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from inventario.tests.fabricas import perezoso
from iot.tests import fabricas
from maestros.servicios import alertas as api_alertas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico

hardware = perezoso("iot.servicios.hardware")


class IotCnsHdwServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Reglas 1 a 7 de IOT-CNS-HDW."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.sector_a = crear_sector(self.norte, "Sector A")
        self.temperatura = fabricas.sensor(self.sistema, "norte/b/temperatura", sector=self.sector_a, numero_serie="DHT-77")
        self.humedad = fabricas.sensor(self.sistema, "norte/a/humedad", variable="humedad", nombre_sensor="Del fondo")
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.ventilador = fabricas.actuador(self.sistema, self.tipo, "norte/ventilador", sector=self.sector_a)
        self.viejo = fabricas.sensor(self.sistema, "norte/viejo", estado="inactivo")

    def buscar(self, actor=None, **filtros):
        return hardware.buscar_equipos(actor or self.laura, self.sistema, filtros)

    def identificadores(self, **filtros):
        return [e.identificador_equipo for e in self.buscar(**filtros)]

    # ---- regla 1: alcance ----

    def test_regla_1_el_agronomo_consulta_los_invernaderos_a_su_cargo_y_el_gerente_todos(self):
        """IOT-CNS-HDW regla 1 y precondición a: el Agrónomo consulta los suyos; el Gerente, todos; un invernadero ajeno, 404; otros roles, 403."""
        self.assertTrue(self.buscar())
        self.assertTrue(self.buscar(self.gerente))
        with self.assertRaises(Http404):
            hardware.buscar_equipos(crear_agronomo("otra@infoponia.com"), self.sistema, {})
        with self.assertRaises(PermissionDenied):
            hardware.buscar_equipos(crear_capataz(), self.sistema, {})

    def test_regla_1_la_ficha_fuera_del_alcance_da_404(self):
        """IOT-CNS-HDW regla 1 (D-28): la ficha de un equipo de otro invernadero, o que no existe, da 404."""
        otra = crear_agronomo("otra@infoponia.com")
        with self.assertRaises(Http404):
            hardware.ficha_del_equipo(otra, self.temperatura.pk)
        with self.assertRaises(Http404):
            hardware.ficha_del_equipo(self.laura, 999999)
        with self.assertRaises(PermissionDenied):
            hardware.ficha_del_equipo(crear_capataz(), self.temperatura.pk)
        self.assertEqual(hardware.ficha_del_equipo(self.gerente, self.temperatura.pk), self.temperatura)

    def test_ficha_del_equipo_es_el_sensor_o_el_actuador_con_sus_datos(self):
        """IOT-CNS-HDW regla 6: la ficha trae el equipo con los datos de su clase (variable y calibración; tipo y compatibilidad)."""
        sensor = hardware.ficha_del_equipo(self.laura, self.temperatura.pk)
        actuador = hardware.ficha_del_equipo(self.laura, self.ventilador.pk)
        self.assertEqual((sensor.tipo_variable_sensor, actuador.tipo_actuador, actuador.compatibilidad), ("temperatura", self.tipo, "sin_verificar"))

    # ---- regla 3 y la lista ----

    def test_la_lista_trae_sensores_y_despues_actuadores_por_identificador_sin_el_nodo(self):
        """«Cómo se aplica», «Consulta»: orden sensores y después actuadores, por identificador; también los dados de baja; sin el nodo central."""
        self.assertEqual(self.identificadores(), ["norte/a/humedad", "norte/b/temperatura", "norte/viejo", "norte/ventilador"])

    def test_la_lista_es_solo_del_sistema_elegido(self):
        """IOT-CNS-HDW regla 1: la consulta es siempre sobre un invernadero elegido."""
        otro = fabricas.sistema(crear_invernadero("Sur", agronomo=self.laura))
        fabricas.sensor(otro, "sur/1")
        self.assertNotIn("sur/1", self.identificadores())

    # ---- regla 5: filtros y búsqueda ----

    def test_regla_5_filtra_por_tipo_de_equipo(self):
        """IOT-CNS-HDW regla 5: por tipo de equipo (sensor o actuador)."""
        self.assertEqual(self.identificadores(tipo="actuador"), ["norte/ventilador"])
        self.assertEqual(self.identificadores(tipo="sensor"), ["norte/a/humedad", "norte/b/temperatura", "norte/viejo"])

    def test_regla_5_filtra_por_estado(self):
        """IOT-CNS-HDW regla 5: por estado (activo, fuera de servicio, dado de baja)."""
        self.humedad.estado_hardware = "fuera_de_servicio"
        self.humedad.save()
        self.assertEqual(self.identificadores(estado="fuera_de_servicio"), ["norte/a/humedad"])
        self.assertEqual(self.identificadores(estado="inactivo"), ["norte/viejo"])
        self.assertEqual(self.identificadores(estado="activo"), ["norte/b/temperatura", "norte/ventilador"])

    def test_regla_5_filtra_por_sector_y_por_general(self):
        """IOT-CNS-HDW regla 5: por sector, con «General» incluido (sin sector)."""
        self.assertEqual(self.identificadores(sector=str(self.sector_a.pk)), ["norte/b/temperatura", "norte/ventilador"])
        self.assertEqual(self.identificadores(sector="_"), ["norte/a/humedad", "norte/viejo"])

    def test_regla_5_busca_por_identificador_nombre_tipo_variable_y_serie(self):
        """IOT-CNS-HDW regla 5 y «Consulta»: por identificador, nombre del sensor, tipo o variable y número de serie, sin distinguir mayúsculas."""
        self.assertEqual(self.identificadores(q="B/TEMP"), ["norte/b/temperatura"])
        self.assertEqual(self.identificadores(q="del fondo"), ["norte/a/humedad"])
        self.assertEqual(self.identificadores(q="extractor"), ["norte/ventilador"])  # el tipo del actuador
        self.assertEqual(self.identificadores(q="Humedad"), ["norte/a/humedad"])  # la variable
        self.assertEqual(self.identificadores(q="dht-77"), ["norte/b/temperatura"])  # la serie
        self.assertEqual(self.identificadores(q="no existe"), [])

    def test_regla_5_los_filtros_se_combinan(self):
        """IOT-CNS-HDW regla 5: los filtros se combinan (y); un valor vacío o «todos» no filtra."""
        self.assertEqual(self.identificadores(tipo="sensor", sector=str(self.sector_a.pk)), ["norte/b/temperatura"])
        self.assertEqual(len(self.buscar(tipo="todos", estado="", sector="", q="  ")), 4)

    # ---- regla 4: situación ----

    def test_regla_4_un_equipo_sin_mensajes_esta_sin_confirmar(self):
        """IOT-CNS-HDW regla 4 y «Cómo se aplica»: «Sin confirmar» si ``ultimo_mensaje_en`` es nulo."""
        self.assertEqual(hardware.situacion_de(self.temperatura).clave, "sin_confirmar")
        self.assertEqual(hardware.situacion_de(self.temperatura).texto, "Sin confirmar")

    def test_regla_4_la_situacion_de_un_equipo_que_ya_reporto_y_no_tiene_problemas(self):
        """«Cómo se aplica»: con mensajes y sin problemas, el actuador está «Operativo»; lo de las lecturas se completa en IOT-03 e IOT-04."""
        self.ventilador.ultimo_mensaje_en = timezone.now()
        self.ventilador.save()
        self.assertEqual(hardware.situacion_de(self.ventilador).texto, "Operativo")

    def test_regla_4_fuera_de_servicio_configuracion_incompatible_y_comando_pendiente(self):
        """«Cómo se aplica», «Situación»: «Fuera de servicio», «Configuración incompatible» y, en los actuadores, «Comando pendiente»."""
        self.ventilador.ultimo_mensaje_en = timezone.now()
        self.ventilador.compatibilidad = "incompatible"
        self.ventilador.save()
        self.assertEqual(hardware.situacion_de(self.ventilador).texto, "Configuración incompatible")
        fabricas.comando(self.ventilador, self.tipo.acciones.first(), "pendiente")
        self.assertEqual(hardware.situacion_de(self.ventilador).texto, "Comando pendiente")
        self.ventilador.estado_hardware = "fuera_de_servicio"
        self.assertEqual(hardware.situacion_de(self.ventilador).texto, "Fuera de servicio")
        self.assertEqual(hardware.situacion_de(self.viejo).texto, "Dado de baja")

    def test_regla_6_la_ficha_muestra_las_alertas_activas_del_equipo(self):
        """IOT-CNS-HDW regla 6: sus alertas activas (las de clave ``hw:<id>`` vinculadas al equipo); las resueltas y las de otros equipos no."""
        from iot.models import AlertaIot

        propia = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.ventilador.pk}")
        resuelta = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_comando_fallido", f"hw:{self.ventilador.pk}")
        ajena = api_alertas.asegurar_alerta_de_estado(self.norte.pk, "iot_dispositivo_en_falla", f"hw:{self.humedad.pk}")
        for alerta, equipo in ((propia, self.ventilador), (resuelta, self.ventilador), (ajena, self.humedad)):
            AlertaIot.objects.create(alerta=alerta, sistema=self.sistema, hardware=equipo)
        api_alertas.resolver_alerta_de_estado(self.norte.pk, "iot_comando_fallido", f"hw:{self.ventilador.pk}")
        self.assertEqual(hardware.alertas_activas_del_equipo(self.ventilador), [propia])

    # ---- regla 7: botones ----

    def test_regla_7_quien_opera_ve_las_acciones_de_cada_estado_y_quien_consulta_no_ve_ninguna(self):
        """IOT-CNS-HDW regla 7 y D-30: quien opera el IoT modifica un equipo activo, vuelve a activar uno fuera de servicio y reactiva uno dado de
        baja; quien solo consulta no tiene acciones; ningún botón lleva a un 403."""
        self.humedad.estado_hardware = "fuera_de_servicio"
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.temperatura), frozenset({"modificar"}))
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.humedad), frozenset({"modificar", "volver_a_activar"}))
        self.assertEqual(hardware.acciones_permitidas(self.laura, self.viejo), frozenset({"reactivar"}))
        self.assertEqual(hardware.acciones_permitidas(self.gerente, self.temperatura), frozenset())
        self.assertEqual(hardware.acciones_permitidas(crear_capataz(), self.temperatura), frozenset())

    def test_regla_7_un_sistema_dado_de_baja_no_tiene_acciones_sobre_sus_equipos(self):
        """IOT-MOD-HDW regla 9: un equipo de un sistema dado de baja no se modifica ni se reactiva: sin botones."""
        baja = fabricas.sistema(crear_invernadero("Viejo", agronomo=self.laura), "inactivo")
        equipo = fabricas.sensor(baja, "v/1", estado="inactivo")
        self.assertEqual(hardware.acciones_permitidas(self.laura, equipo), frozenset())

    def test_regla_7_un_gerente_sin_agronomo_activo_opera(self):
        """IOT-CNS-HDW regla 7: el Gerente opera donde no hay Agrónomo activo."""
        libre = fabricas.sensor(fabricas.sistema(crear_invernadero("Libre")), "l/1")
        self.assertEqual(hardware.acciones_permitidas(self.gerente, libre), frozenset({"modificar"}))

    # ---- regla 8 y anuncios ----

    def test_regla_8_la_consulta_no_se_audita(self):
        """IOT-CNS-HDW regla 8 y SEG-14: la consulta no audita."""
        self.buscar()
        hardware.ficha_del_equipo(self.laura, self.temperatura.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_la_lista_no_hace_una_consulta_por_fila(self):
        """La lista trae las filas con una cantidad de consultas que no crece con la cantidad de equipos."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def cantidad():
            with CaptureQueriesContext(connection) as capturadas:
                for equipo in self.buscar():
                    str(equipo.sector), equipo.insumo_id, getattr(equipo, "tipo_actuador", None)
            return len(capturadas)

        antes = cantidad()
        for i in range(5):
            fabricas.sensor(self.sistema, f"extra/{i}", sector=self.sector_a)
            fabricas.actuador(self.sistema, self.tipo, f"extra/a{i}", sector=self.sector_a)
        self.assertEqual(cantidad(), antes)
