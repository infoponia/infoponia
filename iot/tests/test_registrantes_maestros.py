# Pruebas de los registrantes de `iot` en los puntos de extensión de `maestros` (IOT-02, paso 5; docs/api/extensiones_de_maestros.md, «Estado del IoT del invernadero» y
# «Sectores»; regla A4 de D-37; D-40): el estado del IoT del invernadero, el impedimento de baja del invernadero (``sistema_iot``), el del sector (``hardware_activo``) y el contenido
# del sector. Prueba mínima de cada registrante: devuelve lo esperado con datos, el neutro sin datos y no hace consultas por fila; y, en pantalla, lo que ven la ficha del invernadero
# y las ventanas de baja. Los registrantes los registra ``IotConfig.ready()``: acá se prueban los reales, no los falsos.

from unittest import mock

from django.apps import apps
from django.test import TestCase
from django.urls import reverse

from core.tests.fabricas import crear_gerente
from iot.servicios import hardware
from iot.tests import fabricas
from maestros import extensiones
from maestros.extensiones import Contenido, EstadoIot, Impedimento
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector, crear_tecnico


class RegistrantesBase(fabricas.ConCatalogoIot, TestCase):
    def setUp(self):
        self.gerente = crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero("Norte", agronomo=self.laura, tecnico=crear_tecnico("t@infoponia.com"))


class RegistroEnLasExtensionesTests(RegistrantesBase):
    """``IotConfig.ready()`` conecta `iot` con `maestros` una sola vez."""

    def test_ext_ready_registra_los_cuatro_puntos(self):
        """docs/api/extensiones_de_maestros.md: el estado del IoT, el impedimento de baja del invernadero, el del sector y el contenido del sector."""
        from iot.servicios import hardware, sistemas

        self.assertIn(sistemas.estados_de_sistemas, [par[0] for par in extensiones._ESTADO_IOT])
        self.assertIn(sistemas.impedimentos_de_baja_del_invernadero, extensiones._IMPEDIMENTOS)
        self.assertIn(hardware.impedimentos_de_baja_del_sector, extensiones._IMPEDIMENTOS_DE_SECTOR)
        self.assertIn(hardware.contenido_de_sectores, extensiones._CONTENIDOS)

    def test_ext_ready_corrido_dos_veces_no_duplica_los_registrantes(self):
        """``ready()`` puede correr más de una vez: el estado del IoT admite un solo registrante (``RuntimeError``) y los demás no se repiten."""
        from iot.servicios import hardware, sistemas

        apps.get_app_config("iot").ready()
        self.assertEqual(len(extensiones._ESTADO_IOT), 1)
        self.assertEqual(extensiones._IMPEDIMENTOS.count(sistemas.impedimentos_de_baja_del_invernadero), 1)
        self.assertEqual(extensiones._IMPEDIMENTOS_DE_SECTOR.count(hardware.impedimentos_de_baja_del_sector), 1)
        self.assertEqual(extensiones._CONTENIDOS.count(hardware.contenido_de_sectores), 1)


class EstadoDelIotTests(RegistrantesBase):
    """``registrar_estado_iot``: ``estados_de_sistemas`` y ``url_de_registro``."""

    def test_con_datos_da_el_estado_y_el_enlace_de_cada_invernadero_con_sistema(self):
        """API «Estado del IoT»: solo los invernaderos con un sistema NO dado de baja, con ``activo`` o ``desconectado`` y la URL de su pestaña «Sistema IoT»."""
        sur = crear_invernadero("Sur", agronomo=self.laura)
        este = crear_invernadero("Este", agronomo=self.laura)
        fabricas.sistema(self.norte)
        fabricas.sistema(sur, "desconectado")
        fabricas.sistema(este, "inactivo")
        estados = extensiones.estados_iot([self.norte.pk, sur.pk, este.pk])
        self.assertEqual(sorted(estados), [self.norte.pk, sur.pk])
        self.assertEqual(estados[self.norte.pk], EstadoIot("activo", f"{reverse('iot:sistema')}?invernadero={self.norte.pk}"))
        self.assertEqual(estados[sur.pk].estado, "desconectado")

    def test_sin_datos_es_neutro(self):
        """API «Estado del IoT»: sin sistemas, vacío."""
        self.assertEqual(extensiones.estados_iot([self.norte.pk]), {})

    def test_no_hace_consultas_por_fila(self):
        """API «Estado del IoT»: una sola consulta para toda la lista (tres invernaderos)."""
        otros = [crear_invernadero(nombre, agronomo=self.laura) for nombre in ("Sur", "Este")]
        for invernadero in (self.norte, *otros):
            fabricas.sistema(invernadero)
        with self.assertNumQueries(1):
            extensiones.estados_iot([self.norte.pk, *[i.pk for i in otros]])

    def test_tiene_sistema_iot_sale_del_registrante_real(self):
        """API «Estado del IoT»: ``Invernadero.tiene_sistema_iot()`` es verdadero con un sistema activo o desconectado, falso con ninguno o dado de baja."""
        self.assertFalse(self.norte.tiene_sistema_iot())
        sistema = fabricas.sistema(self.norte, "desconectado")
        self.assertTrue(self.norte.tiene_sistema_iot())
        sistema.estado_sistema = "inactivo"
        sistema.save()
        self.assertFalse(self.norte.tiene_sistema_iot())

    def test_el_enlace_de_registro_es_solo_para_quien_opera_el_iot(self):
        """API «Estado del IoT» y D-30: el Agrónomo del invernadero, sí; el Gerente con Agrónomo activo, no; el Gerente sin Agrónomo, sí."""
        libre = crear_invernadero("Libre")
        esperado = lambda i: f"{reverse('iot:sistema_registrar')}?invernadero={i.pk}"  # noqa: E731
        self.assertEqual(extensiones.url_de_registro_iot(self.laura, self.norte), esperado(self.norte))
        self.assertIsNone(extensiones.url_de_registro_iot(self.gerente, self.norte))
        self.assertEqual(extensiones.url_de_registro_iot(self.gerente, libre), esperado(libre))
        self.assertIsNone(extensiones.url_de_registro_iot(crear_agronomo("otra@infoponia.com"), self.norte))

    def test_la_ficha_del_invernadero_dice_activo_o_sin_registrar_con_el_enlace(self):
        """«Verificación a mano» 1 y 3: «Sin registrar» con «Registrar sistema IoT»; con sistema, «Activo» o «Desconectado» con el enlace a la pestaña; la lista, «Con IoT»."""
        self.client.force_login(self.laura)
        ficha = reverse("maestros:invernadero", args=[self.norte.pk])
        sin = self.client.get(ficha)
        self.assertContains(sin, "Sin registrar")
        self.assertContains(sin, "Registrar sistema IoT")
        self.assertNotContains(self.client.get(reverse("maestros:invernaderos")), "Con IoT")
        sistema = fabricas.sistema(self.norte)
        self.assertContains(self.client.get(ficha), ">Activo</a>")
        sistema.estado_sistema = "desconectado"
        sistema.save()
        self.assertContains(self.client.get(ficha), ">Desconectado</a>")
        self.assertContains(self.client.get(reverse("maestros:invernaderos")), "Con IoT")

    def test_un_gerente_que_no_opera_ve_sin_registrar_sin_enlace(self):
        """D-30: ningún enlace que lleve a un 403: el Gerente con Agrónomo activo ve «Sin registrar» y no «Registrar sistema IoT»."""
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[self.norte.pk]))
        self.assertContains(respuesta, "Sin registrar")
        self.assertNotContains(respuesta, "Registrar sistema IoT")

    def test_la_alerta_del_tecnico_cuenta_con_el_registrante_real(self):
        """Regla 3 de 8.22: con un sistema IoT registrado y sin Técnico activo, ``sincronizar_alertas_de_personal`` crea la alerta del Técnico."""
        from maestros.servicios import alertas

        sin_tecnico = crear_invernadero("Sin tecnico", agronomo=self.laura)
        fabricas.sistema(sin_tecnico)
        self.assertEqual([a.tipo_alerta for a in alertas.sincronizar_alertas_de_personal(sin_tecnico, roles=["tecnico"]).creadas], ["sin_tecnico"])


class ImpedimentoDeBajaDelInvernaderoTests(RegistrantesBase):
    """``registrar_impedimento_de_baja``: ``sistema_iot`` (precondición h de PROD-BAJ-INV)."""

    def test_con_sistema_impide_la_baja_con_su_texto_y_como_resolverla(self):
        """API «Estado del IoT», «Los otros dos registrantes»: código ``sistema_iot``; «Tiene el sistema IoT «{nodo}».»; «Dalo de baja desde IoT · Sistema IoT.»"""
        fabricas.sistema(self.norte)
        impedimentos = [i for i in extensiones.impedimentos_de_baja(self.norte) if i.codigo == "sistema_iot"]
        self.assertEqual(impedimentos, [Impedimento("sistema_iot", "Tiene el sistema IoT «Nodo de prueba».", "Dalo de baja desde IoT · Sistema IoT.")])

    def test_un_sistema_desconectado_tambien_impide_la_baja(self):
        """Regla 6 de IOT-BAJ-SIS: un invernadero con un sistema activo o desconectado no se da de baja."""
        fabricas.sistema(self.norte, "desconectado")
        self.assertTrue([i for i in extensiones.impedimentos_de_baja(self.norte) if i.codigo == "sistema_iot"])

    def test_sin_sistema_o_con_el_sistema_dado_de_baja_es_neutro(self):
        """API: sin sistema, o con el sistema dado de baja (historial), no impide nada."""
        self.assertFalse([i for i in extensiones.impedimentos_de_baja(self.norte) if i.codigo == "sistema_iot"])
        fabricas.sistema(self.norte, "inactivo")
        self.assertFalse([i for i in extensiones.impedimentos_de_baja(self.norte) if i.codigo == "sistema_iot"])

    def test_la_baja_del_invernadero_se_rechaza_y_la_ventana_dice_como_resolverlo(self):
        """«Verificación a mano» 7: intentar dar de baja el invernadero con sistema lo impide con «Tiene el sistema IoT…» y «Dalo de baja desde IoT · Sistema IoT.»"""
        fabricas.sistema(self.norte)
        error = None
        try:
            invernaderos.baja_invernadero(self.gerente, self.norte.pk)
        except Exception as e:  # noqa: BLE001
            error = e
        self.assertIsNotNone(error)
        self.norte.refresh_from_db()
        self.assertEqual(self.norte.estado_invernadero, "activo")
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernadero_baja", args=[self.norte.pk]))
        self.assertContains(respuesta, "Tiene el sistema IoT «Nodo de prueba».")
        self.assertContains(respuesta, "Dalo de baja desde IoT · Sistema IoT.")


class ImpedimentoDeBajaDelSectorTests(RegistrantesBase):
    """``registrar_impedimento_de_baja_de_sector``: ``hardware_activo`` (regla 3 de PROD-BAJ-SCT, regla 4 de IOT-BAJ-HDW)."""

    def setUp(self):
        super().setUp()
        self.sistema = fabricas.sistema(self.norte)
        self.sector = crear_sector(self.norte, "Sector A")

    def impedimentos(self, sector=None):
        return [i for i in extensiones.impedimentos_registrados_de_sector(sector or self.sector) if i.codigo == "hardware_activo"]

    def test_con_equipos_impide_la_baja_y_los_nombra(self):
        """API «Sectores»: ``hardware_activo``; «Tiene {n} equipo(s) del sistema IoT: {lista}.»; «Quitales el sector o dalos de baja desde IoT · Hardware.»"""
        fabricas.sensor(self.sistema, "norte/a/temperatura", sector=self.sector)
        fabricas.actuador(self.sistema, fabricas.tipo_actuador("Extractor"), "norte/a/ventilador", sector=self.sector)
        (impedimento,) = self.impedimentos()
        self.assertEqual(
            impedimento,
            Impedimento(
                "hardware_activo",
                "Tiene 2 equipos del sistema IoT: norte/a/temperatura, norte/a/ventilador.",
                "Quitales el sector o dalos de baja desde IoT · Hardware.",
            ),
        )

    def test_un_solo_equipo_va_en_singular(self):
        """«Tiene 1 equipo del sistema IoT: X.»"""
        fabricas.sensor(self.sistema, "norte/a/temperatura", sector=self.sector)
        self.assertTrue(self.impedimentos()[0].texto.startswith("Tiene 1 equipo del sistema IoT"))

    def test_sin_equipos_o_con_los_equipos_dados_de_baja_es_neutro(self):
        """API «Sectores»: los equipos dados de baja no cuentan; un sector sin equipos no tiene impedimento."""
        self.assertEqual(self.impedimentos(), [])
        fabricas.sensor(self.sistema, "norte/a/baja", sector=self.sector, estado="inactivo")
        self.assertEqual(self.impedimentos(), [])

    def test_un_equipo_fuera_de_servicio_si_impide_la_baja(self):
        """Regla 4 de IOT-BAJ-HDW: «Un sector con hardware activo no se puede dar de baja»; un equipo fuera de servicio sigue instalado y cuenta."""
        fabricas.sensor(self.sistema, "norte/a/fuera", sector=self.sector, estado="fuera_de_servicio")
        self.assertEqual(len(self.impedimentos()), 1)

    def test_los_equipos_generales_y_los_de_otro_sector_no_cuentan(self):
        """Un equipo sin sector, o de otro sector, no impide la baja de este."""
        otro = crear_sector(self.norte, "Sector B")
        fabricas.sensor(self.sistema, "norte/general")
        fabricas.sensor(self.sistema, "norte/b/temperatura", sector=otro)
        self.assertEqual(self.impedimentos(), [])
        self.assertEqual(len(self.impedimentos(otro)), 1)

    def test_la_baja_de_un_sector_con_un_equipo_lo_informa_con_quitales_el_sector(self):
        """«Verificación a mano» 6: la baja del sector lo impide y lista el equipo con «Quitales el sector…»."""
        fabricas.sensor(self.sistema, "norte/a/temperatura", sector=self.sector)
        self.client.force_login(self.laura)
        respuesta = self.client.get(reverse("maestros:sector_baja", args=[self.norte.pk, self.sector.pk]))
        self.assertContains(respuesta, "norte/a/temperatura")
        self.assertContains(respuesta, "Quitales el sector o dalos de baja desde IoT · Hardware.")

    def test_no_hace_consultas_por_fila(self):
        """API «Sectores»: el contenido de varios sectores sale de una consulta por clase de equipo, no de una por sector."""
        sectores = [self.sector, crear_sector(self.norte, "Sector B"), crear_sector(self.norte, "Sector C")]
        for i, sector in enumerate(sectores):
            fabricas.sensor(self.sistema, f"norte/s{i}", sector=sector)
            fabricas.actuador(self.sistema, fabricas.tipo_actuador(f"Tipo {i}"), f"norte/a{i}", sector=sector)
        # Solo el registrante de IoT: `produccion` (PRD-01) registra el suyo en la misma lista y suma sus propias consultas.
        with mock.patch.object(extensiones, "_CONTENIDOS", [hardware.contenido_de_sectores]):
            with self.assertNumQueries(2):
                extensiones.contenido_registrado(sectores)


class ContenidoDeSectoresTests(RegistrantesBase):
    """``registrar_contenido_de_sector``: un ``Contenido`` de tipo ``hardware`` por equipo (regla 3 de PROD-CNS-SCT)."""

    def setUp(self):
        super().setUp()
        self.sistema = fabricas.sistema(self.norte)
        self.sector = crear_sector(self.norte, "Sector A")

    def test_con_equipos_da_un_contenido_de_hardware_por_equipo_con_el_enlace_a_su_ficha(self):
        """API «Sectores» y «Cómo se aplica», «Conexión con maestros»: «Sensor de temperatura norte/sectorA/temperatura», con la URL de su ficha."""
        sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura", sector=self.sector)
        actuador = fabricas.actuador(self.sistema, fabricas.tipo_actuador("Extractor"), "norte/sectorA/ventilador", sector=self.sector)
        contenido = extensiones.contenido_registrado([self.sector])[self.sector.pk]
        self.assertEqual(
            contenido,
            [
                Contenido("hardware", "Sensor de temperatura norte/sectorA/temperatura", None, None, reverse("iot:hardware_ficha", args=[sensor.pk])),
                Contenido("hardware", "Actuador Extractor norte/sectorA/ventilador", None, None, reverse("iot:hardware_ficha", args=[actuador.pk])),
            ],
        )

    def test_sin_equipos_o_dados_de_baja_es_neutro(self):
        """API «Sectores»: un sector sin equipos, o solo con equipos dados de baja, no tiene contenido de hardware."""
        self.assertEqual(extensiones.contenido_registrado([self.sector]), {self.sector.pk: []})
        fabricas.sensor(self.sistema, "norte/baja", sector=self.sector, estado="inactivo")
        self.assertEqual(extensiones.contenido_registrado([self.sector]), {self.sector.pk: []})

    def test_la_tarjeta_del_sector_muestra_el_equipo_con_su_enlace(self):
        """PROD-CNS-SCT regla 3: la tarjeta del sector en la ficha del invernadero lista el equipo y lleva a su ficha."""
        sensor = fabricas.sensor(self.sistema, "norte/sectorA/temperatura", sector=self.sector)
        self.client.force_login(self.laura)
        respuesta = self.client.get(reverse("maestros:invernadero", args=[self.norte.pk]))
        self.assertContains(respuesta, "Sensor de temperatura norte/sectorA/temperatura")
        self.assertContains(respuesta, reverse("iot:hardware_ficha", args=[sensor.pk]))
