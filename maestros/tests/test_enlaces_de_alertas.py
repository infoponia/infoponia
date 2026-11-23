# Pruebas del enlace de cada alerta a la pantalla de su origen (MAE-02d, paso 1; D-62 y sus enmiendas; docs/api/alertas.md,
# sección 8): el punto de extensión ``registrar_enlace_de_alerta`` (maestros/extensiones.py) y ``enlaces_de_alertas``
# (maestros/servicios/alertas.py). Los registrantes son falsos y se reemplazan con ``mock.patch.object`` sobre ``_ENLACES``.

from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from django.urls import reverse

from core.tests.fabricas import crear_gerente
from maestros import extensiones
from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.servicios import alertas as api
from maestros.tests.fabricas import ConGeoref, crear_alerta, crear_invernadero


def con_enlaces_vacios():
    """Un registro de enlaces limpio mientras dura el bloque (no contamina el global)."""
    return mock.patch.object(extensiones, "_ENLACES", [])


class EnlacesDeAlertasServicioTests(ConGeoref, TestCase):
    """``registrar_enlace_de_alerta`` y ``enlaces_de_alertas`` (D-62, puntos 2 y 3 y segunda enmienda)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.invernadero = crear_invernadero("Sur")

    def alertas(self, *tipos):
        """Crea una alerta por cada tipo y las devuelve con el invernadero cargado (como ``consultar_alertas``)."""
        creadas = [crear_alerta(self.invernadero, tipo) for tipo in tipos]
        return list(Alerta.objects.select_related("invernadero").filter(pk__in=[a.pk for a in creadas]).order_by("pk"))

    def por_omision(self, alerta):
        """El enlace por omisión: el detalle de la alerta y el nombre del invernadero (segunda enmienda de D-62)."""
        return Enlace(reverse("alertas:detalle", args=[alerta.pk]), alerta.invernadero.nombre_invernadero)

    # ---- D-62, punto 3 y segunda enmienda: el enlace por omisión ----

    def test_d62_sin_registrante_todas_por_omision(self):
        """D-62, segunda enmienda: sin registrante, el detalle de la alerta y el nombre del invernadero, con todas las claves."""
        a, b = self.alertas("tipo_a", "tipo_b")
        with con_enlaces_vacios():
            enlaces = api.enlaces_de_alertas(self.gerente, [a, b])
        self.assertEqual(set(enlaces), {a.pk, b.pk})
        self.assertEqual(enlaces[a.pk], self.por_omision(a))
        self.assertEqual(enlaces[b.pk], self.por_omision(b))
        self.assertEqual(enlaces[a.pk].url, f"/alertas/{a.pk}/")
        self.assertEqual(enlaces[a.pk].detalle, "Sur")

    # ---- D-62, punto 2: el registrante ----

    def test_d62_un_registrante_da_su_enlace_y_su_texto_y_la_que_no_devuelve_va_por_omision(self):
        """D-62, punto 2: «una alerta que falta en el diccionario usa el enlace por omisión»."""
        a, b = self.alertas("com_a", "com_a")

        def registrante(usuario, alertas):
            return {a.pk: Enlace("/comercial/contratos/7/", "Faltan 120 plantas")}

        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            enlaces = api.enlaces_de_alertas(self.gerente, [a, b])
        self.assertEqual(enlaces[a.pk], Enlace("/comercial/contratos/7/", "Faltan 120 plantas"))
        self.assertEqual(enlaces[b.pk], self.por_omision(b))

    def test_d62_un_registrante_solo_recibe_las_alertas_de_sus_codigos_y_el_usuario(self):
        """D-62, punto 2: ``funcion(usuario, alertas)`` recibe las alertas de sus tipos; las demás no le llegan."""
        propia, ajena = self.alertas("com_a", "otro")
        recibido = []

        def registrante(usuario, alertas):
            recibido.append((usuario, [alerta.pk for alerta in alertas]))
            return {}

        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            enlaces = api.enlaces_de_alertas(self.gerente, [propia, ajena])
        self.assertEqual(recibido, [(self.gerente, [propia.pk])])
        self.assertEqual(enlaces[ajena.pk], self.por_omision(ajena))

    def test_d62_detalle_none_usa_el_texto_de_omision_con_el_url_del_registrante(self):
        """D-62, punto 2: «``detalle`` puede ser ``None``: se usa el de omisión»."""
        (a,) = self.alertas("com_a")
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), lambda usuario, alertas: {a.pk: Enlace("/x/", None)})
            enlaces = api.enlaces_de_alertas(self.gerente, [a])
        self.assertEqual(enlaces[a.pk], Enlace("/x/", "Sur"))

    def test_d62_dos_registrantes_del_mismo_codigo_lanzan_improperly_configured(self):
        """D-62, punto 2: «ningún código puede tener dos registrantes: ``ImproperlyConfigured``»."""
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a", "com_b"), lambda usuario, alertas: {})
            with self.assertRaises(ImproperlyConfigured):
                extensiones.registrar_enlace_de_alerta(("com_b", "com_c"), lambda usuario, alertas: {})
            # Lo que falló no dejó nada a medias: ``com_c`` sigue libre.
            extensiones.registrar_enlace_de_alerta(("com_c",), lambda usuario, alertas: {})

    def test_d62_registrar_dos_veces_la_misma_funcion_no_hace_nada(self):
        """Supuesto aprobado de MAE-02d: ``ready()`` puede correr dos veces; la misma función para el mismo código es idempotente."""

        def registrante(usuario, alertas):
            return {}

        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            self.assertEqual(len(extensiones._ENLACES), 1)

    def test_d62_dos_registrantes_de_codigos_distintos_cada_uno_con_lo_suyo(self):
        """D-62, punto 2: cada registrante resuelve solo sus códigos."""
        a, b, c = self.alertas("com_a", "iot_b", "otro")
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(
                ("com_a",), lambda u, alertas: {x.pk: Enlace("/c/", "Contrato") for x in alertas}
            )
            extensiones.registrar_enlace_de_alerta(
                ("iot_b",), lambda u, alertas: {x.pk: Enlace("/i/", "Equipo") for x in alertas}
            )
            enlaces = api.enlaces_de_alertas(self.gerente, [a, b, c])
        self.assertEqual(enlaces[a.pk], Enlace("/c/", "Contrato"))
        self.assertEqual(enlaces[b.pk], Enlace("/i/", "Equipo"))
        self.assertEqual(enlaces[c.pk], self.por_omision(c))

    def test_d62_una_llamada_por_registrante_y_no_una_por_alerta(self):
        """D-62, punto 2: «una consulta por registrante, nunca una por alerta»."""
        alertas = self.alertas("com_a", "com_a", "com_a")
        registrante = mock.Mock(return_value={})
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            api.enlaces_de_alertas(self.gerente, alertas)
        self.assertEqual(registrante.call_count, 1)
        self.assertEqual([a.pk for a in registrante.call_args.args[1]], [a.pk for a in alertas])

    def test_d62_las_consultas_son_las_mismas_con_una_que_con_tres_alertas(self):
        """D-62, punto 2: sin consultas por alerta (con el invernadero ya cargado, el servicio no consulta la base)."""
        tres = self.alertas("com_a", "com_a", "com_a")
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(
                ("com_a",), lambda u, alertas: {x.pk: Enlace("/c/", "Contrato") for x in alertas}
            )
            with self.assertNumQueries(0):
                api.enlaces_de_alertas(self.gerente, tres[:1])
            with self.assertNumQueries(0):
                api.enlaces_de_alertas(self.gerente, tres)

    def test_d62_una_lista_vacia_da_un_diccionario_vacio_sin_consultar_la_base(self):
        """D-62, punto 2: lista vacía, ``{}`` sin consultar la base y sin llamar a ningún registrante."""
        registrante = mock.Mock(return_value={})
        with con_enlaces_vacios():
            extensiones.registrar_enlace_de_alerta(("com_a",), registrante)
            with self.assertNumQueries(0):
                self.assertEqual(api.enlaces_de_alertas(self.gerente, []), {})
        registrante.assert_not_called()
