# Pruebas de PROD-CNS-CLT · Consultar Cultivo (docs/casos_de_uso/maestros/cultivos.md). La consulta no se audita (SEG-14).
#
# Servicios que se prueban (maestros/servicios/cultivos.py), tomados del módulo dentro de cada prueba:
#   consultar_cultivos(actor) -> cultivos con ``variedades_activas`` (cantidad); obtener_cultivo(actor, cultivo_id);
#   acciones_permitidas(actor, cultivo); variedades_de_cultivos(actor, cultivos) -> {id: VariedadesDelCultivo}.
# Punto de extensión con registrante falso: ``_VARIEDADES`` (``registrar_variedades_de_cultivo``, un solo registrante).

from django.core.exceptions import PermissionDenied
from django.db import connection
from django.http import Http404
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils.safestring import mark_safe

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_capataz, crear_gerente
from maestros.extensiones import VariedadesDelCultivo
from maestros.servicios import cultivos
from maestros.tests.fabricas import (
    ConDatosDeMaestros,
    con_extension,
    crear_agronomo,
    crear_cultivo,
    crear_variedad,
)


class ProdCnsCltServicioTests(ConDatosDeMaestros, TestCase):
    """Reglas y precondición de PROD-CNS-CLT."""

    def setUp(self):
        self.agronomo = crear_agronomo()

    # ---- precondición y regla 4 ----

    def test_pre_a_un_capataz_no_consulta_cultivos(self):
        """PROD-CNS-CLT precondición a: solo un Agrónomo activo."""
        with self.assertRaises(PermissionDenied):
            cultivos.consultar_cultivos(crear_capataz())

    def test_regla_4_el_gerente_no_consulta_cultivos(self):
        """PROD-CNS-CLT regla 4: el Gerente no consulta cultivos."""
        with self.assertRaises(PermissionDenied):
            cultivos.consultar_cultivos(crear_gerente())

    def test_pre_a_una_cuenta_inactiva_no_consulta(self):
        """PROD-CNS-CLT precondición a: la cuenta tiene que estar activa."""
        self.agronomo.is_active = False
        self.agronomo.save()
        with self.assertRaises(PermissionDenied):
            cultivos.consultar_cultivos(self.agronomo)

    def test_regla_4_el_gerente_tampoco_obtiene_un_cultivo(self):
        """PROD-CNS-CLT regla 4: tampoco por su id."""
        cultivo = crear_cultivo()
        with self.assertRaises(PermissionDenied):
            cultivos.obtener_cultivo(crear_gerente(), cultivo.pk)

    def test_pre_a_un_cultivo_que_no_existe_da_404(self):
        """Un id inexistente da 404."""
        with self.assertRaises(Http404):
            cultivos.obtener_cultivo(self.agronomo, 999999)

    # ---- regla 1: qué cultivos y en qué orden ----

    def test_regla_1_el_agronomo_consulta_todos_los_cultivos_activos_primero_y_por_nombre(self):
        """PROD-CNS-CLT regla 1: todos, activos e inactivos; primero los activos."""
        crear_cultivo("Rúcula", activo=False)
        crear_cultivo("Lechuga")
        crear_cultivo("acelga")
        crear_cultivo("Albahaca", activo=False)
        self.assertEqual(
            [c.nombre_cultivo for c in cultivos.consultar_cultivos(self.agronomo)],
            ["acelga", "Lechuga", "Albahaca", "Rúcula"],
        )

    def test_regla_1_cualquier_agronomo_ve_los_mismos_cultivos(self):
        """PROD-ALT-CLT regla 1: el cultivo lo comparten todos; no hay alcance por invernadero."""
        crear_cultivo("Lechuga")
        otro = crear_agronomo(email="otro@infoponia.com")
        self.assertEqual(
            [c.pk for c in cultivos.consultar_cultivos(self.agronomo)], [c.pk for c in cultivos.consultar_cultivos(otro)]
        )

    # ---- regla 2: variedades activas ----

    def test_regla_2_cada_cultivo_trae_su_cantidad_de_variedades_activas(self):
        """PROD-CNS-CLT regla 2: «su cantidad de variedades activas»; las inactivas no cuentan."""
        lechuga = crear_cultivo("Lechuga")
        acelga = crear_cultivo("Acelga")
        crear_variedad(lechuga, "Crespa")
        crear_variedad(lechuga, "Lisa")
        crear_variedad(lechuga, "Vieja", activa=False)
        por_nombre = {c.nombre_cultivo: c.variedades_activas for c in cultivos.consultar_cultivos(self.agronomo)}
        self.assertEqual(por_nombre, {"Lechuga": 2, "Acelga": 0})
        self.assertEqual(acelga.variedades.count(), 0)

    def test_regla_2_la_consulta_no_hace_una_consulta_por_cultivo(self):
        """La cantidad de variedades viene en la misma consulta para toda la lista: el costo no crece con la cantidad de cultivos."""

        def consultas():
            with CaptureQueriesContext(connection) as capturadas:
                for cultivo in cultivos.consultar_cultivos(self.agronomo):
                    cultivo.variedades_activas
            return len(capturadas)

        crear_variedad(crear_cultivo("Cultivo 0"), "V")
        con_uno = consultas()
        for numero in range(1, 6):
            crear_variedad(crear_cultivo(f"Cultivo {numero}"), "V")
        self.assertEqual(consultas(), con_uno)

    # ---- regla 3: acciones (D-30) ----

    def test_regla_3_un_cultivo_activo_ofrece_modificar_y_baja(self):
        """PROD-CNS-CLT regla 3 y D-30: desde un cultivo activo, modificar y dar de baja (Alta Variedad espera a INV-03)."""
        self.assertEqual(cultivos.acciones_permitidas(self.agronomo, crear_cultivo("Lechuga")), {"modificar", "baja"})

    def test_regla_3_un_cultivo_inactivo_solo_se_reactiva(self):
        """PROD-CNS-CLT regla 3: desde un cultivo inactivo, solo reactivarlo."""
        self.assertEqual(cultivos.acciones_permitidas(self.agronomo, crear_cultivo("Acelga", activo=False)), {"reactivar"})

    def test_regla_4_el_gerente_y_otros_roles_no_tienen_acciones(self):
        """D-30: ningún botón lleva a un 403."""
        cultivo = crear_cultivo()
        for actor in (crear_gerente(), crear_capataz(), None):
            with self.subTest(actor=actor):
                self.assertEqual(cultivos.acciones_permitidas(actor, cultivo), frozenset())

    # ---- regla 5 ----

    def test_regla_5_la_consulta_no_audita(self):
        """PROD-CNS-CLT regla 5 y SEG-14."""
        cultivo = crear_cultivo()
        cultivos.consultar_cultivos(self.agronomo)
        cultivos.obtener_cultivo(self.agronomo, cultivo.pk)
        cultivos.variedades_de_cultivos(self.agronomo, [cultivo])
        self.assertFalse(RegistroAuditoria.objects.exists())


class VariedadesDeCultivosTests(ConDatosDeMaestros, TestCase):
    """``variedades_de_cultivos``: el cuerpo y los botones de cada tarjeta (docs/api/extensiones_de_maestros.md, «Cultivos»)."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.cultivo = crear_cultivo("Lechuga")

    def test_ext_sin_registrante_dice_no_tiene_variedades_y_no_hay_botones(self):
        """PROD-CNS-CLT regla 2 y API: sin registrante (hasta INV-03), «No tiene variedades» y sin botones."""
        with con_extension("_VARIEDADES"):
            tarjeta = cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo])[self.cultivo.pk]
        self.assertIn("No tiene variedades", tarjeta.cabecera + tarjeta.cuerpo)
        self.assertEqual(tarjeta.cabecera, "")

    def test_ext_sin_registrante_lista_los_nombres_de_las_variedades_cargadas_a_mano(self):
        """API: la lista simple de nombres si las hay, cargadas a mano; los datos se escapan."""
        crear_variedad(self.cultivo, "Crespa")
        crear_variedad(self.cultivo, "<b>Rara</b>", activa=False)
        with con_extension("_VARIEDADES"):
            cuerpo = cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo])[self.cultivo.pk].cuerpo
        self.assertIn("Crespa", cuerpo)
        self.assertIn("&lt;b&gt;Rara&lt;/b&gt;", cuerpo)
        self.assertNotIn("<b>Rara</b>", cuerpo)
        self.assertNotIn("No tiene variedades", cuerpo)

    def test_ext_sin_registrante_cada_cultivo_trae_lo_suyo(self):
        """Una entrada por cultivo, con sus propias variedades."""
        acelga = crear_cultivo("Acelga")
        crear_variedad(self.cultivo, "Crespa")
        with con_extension("_VARIEDADES"):
            tarjetas = cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo, acelga])
        self.assertIn("Crespa", tarjetas[self.cultivo.pk].cuerpo)
        self.assertIn("No tiene variedades", tarjetas[acelga.pk].cuerpo)

    def test_ext_con_registrante_usa_su_cabecera_y_su_cuerpo(self):
        """API: la página pone ``cabecera`` y ``cuerpo`` del registrante (INV-03) en cada tarjeta."""
        propias = {self.cultivo.pk: VariedadesDelCultivo(mark_safe("<b>+ Variedad</b>"), mark_safe("<table></table>"))}
        with con_extension("_VARIEDADES", lambda actor, cultivos_: propias):
            tarjeta = cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo])[self.cultivo.pk]
        self.assertEqual((tarjeta.cabecera, tarjeta.cuerpo), ("<b>+ Variedad</b>", "<table></table>"))

    def test_ext_con_registrante_se_le_pasa_el_actor_y_los_cultivos(self):
        """API: ``funcion(actor, cultivos)``."""
        llamadas = []

        def registrante(actor, cultivos_):
            llamadas.append((actor, [c.pk for c in cultivos_]))
            return {c.pk: VariedadesDelCultivo(mark_safe(""), mark_safe("x")) for c in cultivos_}

        with con_extension("_VARIEDADES", registrante):
            cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo])
        self.assertEqual(llamadas, [(self.agronomo, [self.cultivo.pk])])

    def test_ext_con_registrante_un_cultivo_que_no_devuelve_cae_a_lo_propio(self):
        """Un cultivo que el registrante no trae se muestra con lo propio de `maestros`: ninguna tarjeta queda sin cuerpo."""
        with con_extension("_VARIEDADES", lambda actor, cultivos_: {}):
            tarjeta = cultivos.variedades_de_cultivos(self.agronomo, [self.cultivo])[self.cultivo.pk]
        self.assertIn("No tiene variedades", tarjeta.cuerpo)
