# Pruebas mínimas del punto de extensión «Estado del IoT del invernadero» (IOT-02, paso 1; docs/api/extensiones_de_maestros.md,
# «Estado del IoT del invernadero»; regla A4 de D-37). `maestros` no puede importar `iot`: pregunta por `estados_iot(ids)` y por
# `url_de_registro_iot(actor, invernadero)`, que `iot` registra en `IotConfig.ready()`. Acá se prueba con un registrante falso
# (`mock.patch.object` sobre la lista de módulo), sin tocar `iot`.
#
# Lo que se prueba, según el contrato: sin registrante, `tiene_sistema_iot()` es falso y la ficha dice «Sin registrar» sin
# enlace; con uno, la ficha muestra el estado y el enlace; la lista hace UNA llamada para todos los invernaderos (no una por
# fila) y marca «Con IoT»; una segunda llamada a `registrar_estado_iot` lanza `RuntimeError`.

from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.tests.fabricas import crear_gerente
from maestros import extensiones
from maestros.extensiones import EstadoIot
from maestros.models import Invernadero
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_invernadero

URL_DEL_SISTEMA = "/iot/sistema/?invernadero={id}"
URL_DE_REGISTRO = "/iot/sistema/registrar/?invernadero={id}"


def registrante_falso(estados_por_id=None, url=URL_DE_REGISTRO, llamadas=None):
    """Un par ``(estados, url_de_registro)`` falso. ``estados_por_id`` es ``{id: "activo" | "desconectado"}``; cada llamada a
    ``estados`` anota sus ids en ``llamadas``. ``url`` es el enlace de registro (``None`` = el actor no opera el IoT)."""
    estados_por_id = estados_por_id or {}

    def estados(ids):
        if llamadas is not None:
            llamadas.append(list(ids))
        return {i: EstadoIot(estados_por_id[i], URL_DEL_SISTEMA.format(id=i)) for i in ids if i in estados_por_id}

    def url_de_registro(actor, invernadero):
        return url.format(id=invernadero.pk) if url else None

    return estados, url_de_registro


class RegistroDelEstadoIotTests(SimpleTestCase):
    """``registrar_estado_iot``, ``estados_iot`` y ``url_de_registro_iot``."""

    def test_ext_estado_iot_sin_registrante_no_hay_estados_ni_enlace(self):
        """API «Estado del IoT»: sin registrante, ``estados_iot`` es vacío y no hay enlace de registro."""
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            self.assertEqual(extensiones.estados_iot([1, 2]), {})
            self.assertIsNone(extensiones.url_de_registro_iot(object(), object()))

    def test_ext_estado_iot_con_registrante_hace_una_sola_llamada_para_toda_la_lista(self):
        """API «Estado del IoT»: una sola llamada para toda la lista de ids (sin consultas por fila)."""
        llamadas = []
        estados, url = registrante_falso({1: "activo", 3: "desconectado"}, llamadas=llamadas)
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            extensiones.registrar_estado_iot(estados, url)
            resultado = extensiones.estados_iot([1, 2, 3])
        self.assertEqual(llamadas, [[1, 2, 3]])
        self.assertEqual(sorted(resultado), [1, 3])
        self.assertEqual(resultado[1].estado, "activo")
        self.assertEqual(resultado[3].estado, "desconectado")

    def test_ext_estado_iot_con_lista_vacia_no_llama_al_registrante(self):
        """API «Estado del IoT»: sin ids no hace falta preguntar."""
        llamadas = []
        estados, url = registrante_falso({1: "activo"}, llamadas=llamadas)
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            extensiones.registrar_estado_iot(estados, url)
            self.assertEqual(extensiones.estados_iot([]), {})
        self.assertEqual(llamadas, [])

    def test_ext_estado_iot_admite_un_solo_registrante(self):
        """API «Estado del IoT»: una segunda llamada a ``registrar_estado_iot`` lanza ``RuntimeError``."""
        estados, url = registrante_falso()
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            extensiones.registrar_estado_iot(estados, url)
            with self.assertRaises(RuntimeError):
                extensiones.registrar_estado_iot(estados, url)

    def test_ext_estado_iot_el_enlace_de_registro_lo_da_el_registrante(self):
        """API «Estado del IoT»: ``url_de_registro_iot`` devuelve lo que informa el registrante (``None`` si no opera)."""
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            estados, url = registrante_falso(url=None)
            extensiones.registrar_estado_iot(estados, url)
            self.assertIsNone(extensiones.url_de_registro_iot(object(), mock.Mock(pk=7)))
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            estados, url = registrante_falso()
            extensiones.registrar_estado_iot(estados, url)
            self.assertEqual(extensiones.url_de_registro_iot(object(), mock.Mock(pk=7)), URL_DE_REGISTRO.format(id=7))


class EstadoIotEnElInvernaderoTests(ConGeoref, TestCase):
    """``Invernadero.tiene_sistema_iot()`` y lo que muestran la ficha y la lista."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)

    def con_registrante(self, estados_por_id=None, url=URL_DE_REGISTRO, llamadas=None):
        """Registra el registrante falso mientras dura la prueba."""
        parche = mock.patch.object(extensiones, "_ESTADO_IOT", [])
        parche.start()
        self.addCleanup(parche.stop)
        extensiones.registrar_estado_iot(*registrante_falso(estados_por_id, url, llamadas))

    def ficha(self, invernadero=None):
        """La ficha del invernadero, vista por el Gerente."""
        self.client.force_login(self.gerente)
        return self.client.get(reverse("maestros:invernadero", args=[(invernadero or self.invernadero).pk]))

    # ---- tiene_sistema_iot ----

    def test_ext_estado_iot_sin_registrante_tiene_sistema_iot_es_falso(self):
        """API «Estado del IoT»: sin registrante, ``tiene_sistema_iot()`` es ``False`` (como hasta IOT-02)."""
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            self.assertFalse(Invernadero.objects.get(pk=self.invernadero.pk).tiene_sistema_iot())

    def test_ext_estado_iot_con_estado_tiene_sistema_iot_es_verdadero(self):
        """API «Estado del IoT»: ``tiene_sistema_iot()`` es ``self.pk in estados_iot([self.pk])`` (activo o desconectado)."""
        otro = crear_invernadero("Sur")
        self.con_registrante({self.invernadero.pk: "desconectado"})
        self.assertTrue(Invernadero.objects.get(pk=self.invernadero.pk).tiene_sistema_iot())
        self.assertFalse(Invernadero.objects.get(pk=otro.pk).tiene_sistema_iot())

    # ---- ficha ----

    def test_ext_estado_iot_la_ficha_sin_registrante_dice_sin_registrar_sin_enlace(self):
        """API «Estado del IoT»: sin registrante, la ficha dice «Sin registrar» y no hay enlace."""
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            respuesta = self.ficha()
        self.assertContains(respuesta, "Sin registrar")
        self.assertNotContains(respuesta, "Registrar sistema IoT")

    def test_ext_estado_iot_la_ficha_sin_sistema_ofrece_el_enlace_de_registro(self):
        """API «Estado del IoT»: «Sin registrar» con el enlace de ``url_de_registro`` si no es ``None``."""
        self.con_registrante({})
        respuesta = self.ficha()
        self.assertContains(respuesta, "Sin registrar")
        self.assertContains(respuesta, "Registrar sistema IoT")
        self.assertContains(respuesta, URL_DE_REGISTRO.format(id=self.invernadero.pk).replace("&", "&amp;"))

    def test_ext_estado_iot_la_ficha_sin_sistema_no_ofrece_el_enlace_a_quien_no_opera(self):
        """API «Estado del IoT»: si ``url_de_registro`` es ``None``, «Sin registrar» va sin enlace (ningún botón lleva a un 403)."""
        self.con_registrante({}, url=None)
        respuesta = self.ficha()
        self.assertContains(respuesta, "Sin registrar")
        self.assertNotContains(respuesta, "Registrar sistema IoT")

    def test_ext_estado_iot_la_ficha_muestra_activo_o_desconectado_con_su_enlace(self):
        """API «Estado del IoT»: «Activo» o «Desconectado» con el enlace ``url`` a la pestaña «Sistema IoT»."""
        for estado, texto in (("activo", "Activo"), ("desconectado", "Desconectado")):
            with self.subTest(estado=estado):
                self.con_registrante({self.invernadero.pk: estado})
                respuesta = self.ficha()
                self.assertContains(respuesta, URL_DEL_SISTEMA.format(id=self.invernadero.pk))
                self.assertContains(respuesta, f">{texto}</a>")
                self.assertNotContains(respuesta, "Registrar sistema IoT")

    def test_ext_estado_iot_la_ficha_llama_una_sola_vez_al_registrante(self):
        """API «Estado del IoT»: la ficha pregunta una vez, aunque ``equipo()`` y ``roles_faltantes()`` usen ``tiene_sistema_iot()``."""
        llamadas = []
        self.con_registrante({self.invernadero.pk: "activo"}, llamadas=llamadas)
        self.ficha()
        self.assertEqual(llamadas, [[self.invernadero.pk]])

    # ---- lista ----

    def test_ext_estado_iot_la_lista_marca_con_iot_solo_donde_hay_estado(self):
        """API «Estado del IoT»: la lista muestra «Con IoT» donde hay estado y nada en los demás."""
        crear_invernadero("Sur")
        self.con_registrante({self.invernadero.pk: "activo"})
        self.client.force_login(self.gerente)
        respuesta = self.client.get(reverse("maestros:invernaderos"))
        self.assertContains(respuesta, "Con IoT", count=1)

    def test_ext_estado_iot_la_lista_no_hace_una_consulta_por_fila(self):
        """API «Estado del IoT»: una sola llamada para toda la lista, con los ids de todos los invernaderos."""
        for nombre in ("Sur", "Este", "Oeste"):
            crear_invernadero(nombre)
        llamadas = []
        self.con_registrante({}, llamadas=llamadas)
        self.client.force_login(self.gerente)
        self.client.get(reverse("maestros:invernaderos"))
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(len(llamadas[0]), 4)

    def test_ext_estado_iot_la_lista_sin_registrante_no_marca_ninguno(self):
        """API «Estado del IoT»: sin registrante, todo queda como hoy (sin «Con IoT»)."""
        self.client.force_login(self.gerente)
        with mock.patch.object(extensiones, "_ESTADO_IOT", []):
            respuesta = self.client.get(reverse("maestros:invernaderos"))
        self.assertNotContains(respuesta, "Con IoT")
