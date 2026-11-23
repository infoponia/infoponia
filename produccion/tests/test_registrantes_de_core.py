# Pruebas de lo que `produccion` registra en `core` desde `ProduccionConfig.ready()` (PRD-01, paso 4; docs/api/produccion.md,
# sección 3; core/extensiones.py, D-43): `registrar_asignaciones_de_cuenta` (lo que una cuenta tiene asignado, para la ventana de
# baja, regla 4 de USR-BAJ-USR) y `registrar_seccion_de_inicio` (la bandeja del Capataz como sección del Inicio). Cada registrante
# lleva sus tres pruebas mínimas y una de punta a punta con la función pública de `core` y el registrante REAL. La plantilla de la
# sección la escribe el paso 8: acá se prueba lo que devuelve la función.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core import extensiones
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_agronomo
from produccion.tests.fabricas import invernadero_con_produccion, orden_de_siembra


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()


class AsignacionesDeCuentaTests(Base):
    """`registrar_asignaciones_de_cuenta`: las órdenes «a realizar» del Capataz, por `ordenes_del_capataz` (D-53)."""

    def produccion(self, cuenta):
        return [a for a in extensiones.asignaciones_de_cuenta(cuenta) if a.texto.startswith("Órdenes de trabajo")]

    def test_ext_con_datos_cuenta_las_ordenes_a_realizar_y_dice_que_pasa(self):
        """Regla 4 de USR-BAJ-USR: cuántas órdenes a realizar tiene y qué pasará con ellas (pasan a quien el Gerente asigne al
        modificar el invernadero). Las canceladas no cuentan."""
        orden_de_siembra(self.e, plantines=1)
        orden_de_siembra(self.e, plantines=1, sector="crecimiento")
        orden_de_siembra(self.e, plantines=1, sector="floracion", estado="cancelada")
        asignaciones = self.produccion(self.e.capataz)
        self.assertEqual([(a.texto, a.cantidad) for a in asignaciones], [("Órdenes de trabajo a realizar", 2)])
        self.assertIn("Gerente", asignaciones[0].que_pasa)

    def test_ext_sin_ordenes_o_con_otro_rol_no_hay_asignacion(self):
        """Neutro: un Capataz sin órdenes «a realizar», o una cuenta que no es Capataz, no tiene nada de `produccion`."""
        self.assertEqual(self.produccion(self.e.capataz), [])
        orden_de_siembra(self.e, plantines=1)
        self.assertEqual(self.produccion(self.e.agronomo), [])
        self.assertEqual(self.produccion(crear_gerente()), [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: self.produccion(self.e.capataz))
        for sector in ("crecimiento", "floracion", "fructificacion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        self.assertEqual(con_una, consultas(lambda: self.produccion(self.e.capataz)))


class SeccionDeInicioTests(Base):
    """`registrar_seccion_de_inicio`: la bandeja del Capataz."""

    def seccion(self, usuario):
        secciones = [s for s in extensiones.secciones_de_inicio(usuario) if s.plantilla == "produccion/_seccion_de_inicio.html"]  # la del Agrónomo (PRD-04) se prueba en test_inicio_agronomo.py
        return secciones[0] if secciones else None

    def test_ext_con_datos_el_capataz_recibe_su_bandeja(self):
        """Una `SeccionDeInicio` con la plantilla de `produccion` y la bandeja (vencidas, hoy y próximas) en su contexto."""
        pendiente = orden_de_siembra(self.e, plantines=1)
        seccion = self.seccion(self.e.capataz)
        self.assertEqual(seccion.plantilla, "produccion/_seccion_de_inicio.html")
        self.assertEqual([f.orden_id for f in seccion.contexto["bandeja"].hoy], [pendiente.pk])

    def test_ext_neutro_para_quien_no_es_capataz(self):
        """Neutro: el Agrónomo, el Gerente y los demás no reciben esta sección (`None`; la del Agrónomo es de PRD-04)."""
        self.assertIsNone(self.seccion(self.e.agronomo))
        self.assertIsNone(self.seccion(crear_gerente()))
        self.assertIsNone(self.seccion(crear_agronomo("otro@infoponia.com")))

    def test_ext_el_capataz_sin_ordenes_recibe_la_seccion_vacia(self):
        """Sin órdenes «a realizar», el Capataz igual recibe la sección (para decir «no tenés órdenes»)."""
        seccion = self.seccion(self.e.capataz)
        self.assertEqual(seccion.contexto["bandeja"].hoy, [])

    def test_ext_no_hace_consultas_por_fila(self):
        """La cantidad de consultas no crece con las órdenes."""
        orden_de_siembra(self.e, plantines=1)
        con_una = consultas(lambda: self.seccion(self.e.capataz))
        for sector in ("crecimiento", "floracion", "fructificacion"):
            orden_de_siembra(self.e, plantines=1, sector=sector)
        self.assertEqual(con_una, consultas(lambda: self.seccion(self.e.capataz)))
