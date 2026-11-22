# Pruebas del alcance del IoT por usuario (IOT-01, paso 1; MD-98; docs/casos_de_uso/iot/sistema_iot.md, «Para los cinco»): el
# Agrónomo opera el IoT de los invernaderos activos a su cargo; el Gerente lo opera solo en los invernaderos sin Agrónomo activo
# (sin asignar o con el asignado inactivo) y consulta todos; los demás roles, ninguno. También los ``QuerySet`` ``para`` y
# ``operables_por`` que se apoyan en ese cálculo, y el de los tipos de actuador, que no tienen alcance por invernadero.

from django.test import TestCase

from core.tests.fabricas import crear_administrador, crear_capataz, crear_gerente
from iot.alcance import invernaderos_que_consulta, invernaderos_que_opera, puede_operar
from iot.models import SistemaIoT, Telemetria, TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_tecnico, crear_vendedor


class AlcanceTests(fabricas.ConCatalogoIot, TestCase):
    """MD-98 y regla 4 de 8.22 (reescrita): quién opera y quién consulta el IoT de cada invernadero."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.otro = crear_agronomo("otro@infoponia.com")
        self.suyo = crear_invernadero("Suyo", agronomo=self.laura)
        self.ajeno = crear_invernadero("Ajeno", agronomo=self.otro)
        self.sin_agronomo = crear_invernadero("Sin Agrónomo")
        self.agronomo_inactivo = crear_agronomo("baja@infoponia.com", activo=False)
        self.con_agronomo_inactivo = crear_invernadero("Con Agrónomo inactivo", agronomo=self.agronomo_inactivo)
        self.inactivo = crear_invernadero("Dado de baja", activo=False, agronomo=self.laura)

    def nombres(self, invernaderos):
        """Los nombres, ordenados, para comparar."""
        return sorted(i.nombre_invernadero for i in invernaderos)

    def test_md98_el_agronomo_opera_y_consulta_los_activos_a_su_cargo(self):
        """MD-98, caso 1: el Agrónomo opera y consulta los invernaderos activos a su cargo, no los de otro ni los dados de baja."""
        self.assertEqual(self.nombres(invernaderos_que_opera(self.laura)), ["Suyo"])
        self.assertEqual(self.nombres(invernaderos_que_consulta(self.laura)), ["Suyo"])

    def test_md98_el_gerente_opera_solo_los_invernaderos_sin_agronomo_activo(self):
        """MD-98, caso 2: el Gerente opera los activos sin Agrónomo o con el asignado inactivo; no los que tienen uno activo."""
        self.assertEqual(self.nombres(invernaderos_que_opera(self.gerente)), ["Con Agrónomo inactivo", "Sin Agrónomo"])

    def test_md98_el_gerente_con_agronomo_activo_solo_consulta(self):
        """MD-98, caso 3: en un invernadero con Agrónomo activo, el Gerente no opera pero sí consulta; consulta todos."""
        self.assertFalse(puede_operar(self.gerente, self.suyo))
        self.assertTrue(puede_operar(self.gerente, self.sin_agronomo))
        self.assertTrue(puede_operar(self.gerente, self.con_agronomo_inactivo))
        self.assertEqual(
            self.nombres(invernaderos_que_consulta(self.gerente)),
            ["Ajeno", "Con Agrónomo inactivo", "Dado de baja", "Sin Agrónomo", "Suyo"],
        )

    def test_md98_el_gerente_no_opera_un_invernadero_dado_de_baja(self):
        """MD-98: un invernadero inactivo no se opera (el Agrónomo a cargo tampoco), aunque no tenga Agrónomo activo."""
        sin_nadie = crear_invernadero("Baja sin Agrónomo", activo=False)
        self.assertFalse(puede_operar(self.gerente, sin_nadie))
        self.assertFalse(puede_operar(self.laura, self.inactivo))

    def test_md98_el_agronomo_no_opera_el_invernadero_de_otro(self):
        """MD-98: ``puede_operar`` es falso para un invernadero a cargo de otro Agrónomo."""
        self.assertTrue(puede_operar(self.laura, self.suyo))
        self.assertFalse(puede_operar(self.laura, self.ajeno))
        self.assertFalse(puede_operar(self.laura, self.sin_agronomo))

    def test_md98_los_otros_roles_no_operan_ni_consultan(self):
        """MD-98, caso 4: Capataz, Vendedor, Técnico, el Administrador y quien no inició sesión: ningún invernadero."""
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico(), crear_administrador(), None):
            with self.subTest(cuenta=cuenta):
                self.assertFalse(invernaderos_que_opera(cuenta).exists())
                self.assertFalse(invernaderos_que_consulta(cuenta).exists())

    def test_md98_una_cuenta_inactiva_no_opera_ni_consulta(self):
        """MD-98: un Agrónomo o un Gerente dados de baja no tienen alcance."""
        self.laura.is_active = False
        self.laura.save()
        self.gerente.is_active = False
        self.gerente.save()
        for cuenta in (self.laura, self.gerente):
            with self.subTest(cuenta=cuenta):
                self.assertFalse(invernaderos_que_opera(cuenta).exists())
                self.assertFalse(invernaderos_que_consulta(cuenta).exists())

    def test_md98_si_se_asigna_un_agronomo_el_gerente_deja_de_operar(self):
        """MD-98: «hasta que se asigne uno»: al asignarle un Agrónomo activo, el invernadero sale del alcance del Gerente."""
        self.assertTrue(puede_operar(self.gerente, self.sin_agronomo))
        self.sin_agronomo.agronomo = self.otro
        self.sin_agronomo.save()
        self.assertFalse(puede_operar(self.gerente, self.sin_agronomo))


class QuerySetsConAlcanceTests(fabricas.ConCatalogoIot, TestCase):
    """``para`` y ``operables_por`` de los modelos del IoT, apoyados en ``iot/alcance.py`` (D-28)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.suyo = crear_invernadero("Suyo", agronomo=self.laura)
        self.libre = crear_invernadero("Libre")
        self.del_agronomo = fabricas.sistema(self.suyo)
        self.sin_agronomo = fabricas.sistema(self.libre)
        self.lectura = fabricas.telemetria(fabricas.sensor(self.del_agronomo))

    def test_md98_para_y_operables_por_filtran_los_sistemas(self):
        """MD-98: el Agrónomo ve y opera el sistema de su invernadero; el Gerente ve los dos y opera solo el sin Agrónomo."""
        self.assertEqual(list(SistemaIoT.objects.para(self.laura)), [self.del_agronomo])
        self.assertEqual(list(SistemaIoT.objects.operables_por(self.laura)), [self.del_agronomo])
        self.assertEqual(set(SistemaIoT.objects.para(self.gerente)), {self.del_agronomo, self.sin_agronomo})
        self.assertEqual(list(SistemaIoT.objects.operables_por(self.gerente)), [self.sin_agronomo])
        self.assertFalse(SistemaIoT.objects.para(crear_capataz()).exists())

    def test_md98_el_alcance_llega_a_las_lecturas_por_su_sensor_y_su_sistema(self):
        """MD-98: una lectura es del invernadero de su sensor (regla 20 de 8.20, por el sistema)."""
        self.assertEqual(list(Telemetria.objects.para(self.laura)), [self.lectura])
        self.assertEqual(list(Telemetria.objects.operables_por(self.laura)), [self.lectura])
        self.assertFalse(Telemetria.objects.operables_por(self.gerente).exists())
        self.assertEqual(list(Telemetria.objects.para(self.gerente)), [self.lectura])

    def test_regla_1_de_iot_cns_tac_los_tipos_los_consultan_el_gerente_y_el_agronomo(self):
        """IOT-CNS-TAC regla 1: todos los tipos, sin alcance por invernadero, para el Gerente y el Agrónomo; ninguno para otro rol."""
        todos = set(TipoActuador.objects.all())
        self.assertEqual(set(TipoActuador.objects.para(self.gerente)), todos)
        self.assertEqual(set(TipoActuador.objects.para(self.laura)), todos)
        for cuenta in (crear_capataz(), crear_vendedor(), crear_tecnico(), None):
            self.assertFalse(TipoActuador.objects.para(cuenta).exists())

    def test_regla_1_de_iot_alt_tac_los_tipos_los_administra_solo_el_gerente(self):
        """IOT-ALT-TAC regla 1: ``operables_por`` devuelve todos los tipos solo para el Gerente activo."""
        self.assertEqual(set(TipoActuador.objects.operables_por(self.gerente)), set(TipoActuador.objects.all()))
        self.assertFalse(TipoActuador.objects.operables_por(self.laura).exists())
        self.gerente.is_active = False
        self.gerente.save()
        self.assertFalse(TipoActuador.objects.operables_por(self.gerente).exists())
