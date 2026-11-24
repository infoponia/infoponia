# Pruebas de la sección «Mantenimientos a realizar» del Inicio del Técnico (IOT-07, paso 6; D-79 punto 4; docs/casos_de_uso/iot/mantenimiento_automatico.md, «El Inicio del Técnico»).
# Se escribieron ANTES que el servicio (.claude/rules/pruebas.md, «Orden en servicios»).
#
# Servicio que se prueba (iot/servicios/mantenimiento.py), registrado con ``core.extensiones.registrar_seccion_de_inicio`` en ``IotConfig.ready()``:
#   seccion_de_mantenimientos(usuario) -> SeccionDeInicio("iot/_inicio_mantenimientos.html", {"ordenes": [...], "hoy": fecha}) | None
#       ``None`` si ``usuario`` no es un Técnico activo. ``ordenes`` es ``mantenimientos_a_realizar_del_tecnico`` (con el invernadero y los equipos cargados). Solo lectura: sin botones ni enlaces
#       a pantallas del IoT (el Técnico no las tiene, IOT-CNS-HDW).

from datetime import timedelta

from django.db import connection
from django.template.loader import render_to_string
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core import extensiones
from core.tests.fabricas import crear_capataz
from inventario.tests.fabricas import perezoso
from iot.models import MantenimientoTecnico
from iot.tests import fabricas
from iot.tests.test_iot_rsv_cmd_mantenimiento import Escena
from maestros.tests.fabricas import crear_tecnico

mantenimiento = perezoso("iot.servicios.mantenimiento")
PLANTILLA = "iot/_inicio_mantenimientos.html"


def consultas(llamada):
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class InicioDelTecnicoBase(Escena, TestCase):
    def setUp(self):
        super().setUp()
        self.hoy = timezone.localdate()

    def orden(self, dias=0, **extra):
        """Una orden «a realizar» del Técnico programada ``dias`` días desde hoy (negativo: vencida; la de creación va tres días antes de la programada o hoy)."""
        programada = self.hoy + timedelta(days=dias)
        return fabricas.mantenimiento_tecnico(
            self.norte, self.tecnico, [self.actuador], fecha_programada_orden=programada, fecha_creacion_orden=min(self.hoy, programada), **extra
        )

    def seccion(self, usuario=None):
        secciones = [s for s in extensiones.secciones_de_inicio(usuario or self.tecnico) if s.plantilla == PLANTILLA]
        return secciones[0] if secciones else None

    def html(self, usuario=None):
        return render_to_string(PLANTILLA, {"datos": self.seccion(usuario).contexto})


class SeccionRegistradaTests(InicioDelTecnicoBase):
    def test_ext_con_datos_el_tecnico_recibe_sus_ordenes_en_el_orden_de_las_ordenes(self):
        """Con órdenes: una `SeccionDeInicio` con la plantilla de `iot` y sus órdenes «a realizar», por fecha programada, prioridad e id."""
        tarde, vencida, hoy = self.orden(5), self.orden(-2), self.orden(0)
        seccion = self.seccion()
        self.assertEqual(seccion.plantilla, PLANTILLA)
        self.assertEqual([o.pk for o in seccion.contexto["ordenes"]], [vencida.pk, hoy.pk, tarde.pk])
        self.assertEqual(seccion.contexto["hoy"], self.hoy)

    def test_ext_solo_las_a_realizar_del_propio_tecnico(self):
        propia = self.orden()
        self.orden(estado="cancelada")
        fabricas.mantenimiento_tecnico(self.norte, crear_tecnico("otro@infoponia.com"), [self.actuador])
        self.assertEqual([o.pk for o in self.seccion().contexto["ordenes"]], [propia.pk])

    def test_ext_neutro_para_quien_no_es_un_tecnico_activo(self):
        """Neutro: el Agrónomo, el Gerente, el Capataz y un Técnico inactivo no reciben esta sección (`None`)."""
        self.orden()
        for usuario in (self.laura, self.gerente, crear_capataz()):
            with self.subTest(rol=type(usuario).__name__):
                self.assertIsNone(self.seccion(usuario))
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(is_active=False)
        self.tecnico.refresh_from_db()
        self.assertIsNone(self.seccion())

    def test_ext_el_tecnico_sin_ordenes_recibe_la_seccion_vacia(self):
        """Sin órdenes, el Técnico igual recibe la sección (para decir «No tenés mantenimientos a realizar.»)."""
        self.assertEqual(self.seccion().contexto["ordenes"], [])

    def test_ext_no_hace_consultas_por_fila(self):
        def leer():
            for o in self.seccion().contexto["ordenes"]:
                o.invernadero.nombre_invernadero, [e.identificador_equipo for e in o.hardware.all()]  # noqa: B018

        self.orden()
        con_una = consultas(leer)
        for dias in (1, 2, 3, 4):
            self.orden(dias)
        self.assertEqual(con_una, consultas(leer))

    def test_ext_esta_registrada_una_sola_vez(self):
        self.assertEqual(extensiones._SECCIONES_DE_INICIO.count(mantenimiento.seccion_de_mantenimientos), 1)


class PlantillaTests(InicioDelTecnicoBase):
    """Lo que dibuja la sección: por orden, código, invernadero, equipos, tipo, prioridad, fecha y descripción; sin botones ni enlaces."""

    def test_regla_cada_orden_muestra_sus_datos(self):
        orden = self.orden(2, descripcion_orden="CMD-7 · Encender no se ejecutó en 4 intentos.")
        html = self.html()
        for texto in (orden.codigo, "Norte", "norte/extractor", "Revisión", "Alta", (self.hoy + timedelta(days=2)).strftime("%d/%m/%Y"), "CMD-7 · Encender no se ejecutó en 4 intentos."):
            self.assertIn(texto, html)
        self.assertNotIn("Vencida", html)

    def test_regla_una_orden_anterior_a_hoy_se_marca_vencida_y_una_de_hoy_no(self):
        vencida = self.orden(-1)
        self.assertIn("Vencida", self.html())
        MantenimientoTecnico.objects.filter(pk=vencida.pk).update(fecha_programada_orden=self.hoy)  # ahora es de hoy
        self.assertNotIn("Vencida", self.html())

    def test_regla_sin_ordenes_dice_que_no_tiene(self):
        self.assertIn("No tenés mantenimientos a realizar.", self.html())

    def test_regla_la_linea_de_quien_las_cierra(self):
        self.assertIn("Las órdenes las cierra el Agrónomo: cancelándolas o volviendo a activar el equipo.", self.html())

    def test_regla_sin_botones_ni_enlaces(self):
        """El Técnico no tiene pantallas del IoT: la sección no lleva `<a`, `<button` ni `<form`, y no nombra una URL del módulo."""
        self.orden(-1)
        html = self.html()
        for etiqueta in ("<a ", "<button", "<form", "/iot/"):
            self.assertNotIn(etiqueta, html)

    def test_regla_la_descripcion_se_escapa(self):
        self.orden(descripcion_orden="<script>alert(1)</script>")
        html = self.html()
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


class InicioDeLaCuentaTests(InicioDelTecnicoBase):
    """La pantalla de Inicio completa, con el cliente de Django."""

    def abrir(self, usuario):
        cliente = Client()
        cliente.force_login(usuario)
        return cliente.get("/")

    def test_el_inicio_del_tecnico_muestra_la_seccion_con_su_orden(self):
        orden = self.orden(-1)
        respuesta = self.abrir(self.tecnico)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Mantenimientos a realizar")
        self.assertContains(respuesta, orden.codigo)
        self.assertContains(respuesta, "Vencida")

    def test_el_inicio_de_otros_roles_no_tiene_la_seccion(self):
        self.orden()
        for usuario in (self.laura, self.gerente):
            with self.subTest(rol=type(usuario).__name__):
                self.assertNotContains(self.abrir(usuario), "Mantenimientos a realizar")
