# Pruebas de lo que CMP-02b suma a `maestros` (autorizado por el estudiante, 23/11/2026; docs/api/extensiones_de_maestros.md):
#   1. El punto ``registrar_aviso_de_traspaso(funcion)`` con ``funcion(invernadero, rol, saliente, entrante) -> list[str]`` y ``avisos_de_traspaso(...)``: lo que se
#      CANCELA o se pierde al cambiar a una persona del invernadero. A diferencia de ``contar_traspaso`` (lo que RECIBE quien entra), se informa aunque no haya
#      entrante, y no va a la notificación de quien entra. ``_aviso_de_personal`` (la ventana de PROD-MOD-INV, regla 2) lo suma como ``avisos`` de cada cambio.
#   2. ``Impedimento`` suma ``url`` (opcional, por omisión ``None``): la ventana de la baja del invernadero muestra «Ver detalle» si la hay.
# Sin registrantes, el punto da su resultado neutro (lista vacía). Con registrantes falsos (``mock.patch.object``).

from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from maestros import extensiones
from maestros.extensiones import Impedimento
from maestros.models import Departamento, Invernadero, Provincia
from maestros.servicios import invernaderos
from maestros.tests.fabricas import ConGeoref, crear_agronomo, crear_invernadero, localidad
from maestros.tests.test_prod_baj_inv import con_impedimentos
from maestros.tests.test_prod_mod_inv import datos_de


class PuntoDeAvisoDeTraspasoTests(SimpleTestCase):
    """El punto `registrar_aviso_de_traspaso` y `avisos_de_traspaso` (pruebas mínimas del contrato de maestros)."""

    def test_ext_sin_registrantes_no_hay_avisos(self):
        """Prueba mínima (neutro): sin registrantes, lista vacía."""
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", []):
            self.assertEqual(extensiones.avisos_de_traspaso(object(), "agronomo", object(), None), [])

    def test_ext_los_textos_de_todos_los_registrantes_van_juntos_y_en_orden_de_registro(self):
        """Prueba mínima (con datos): cada registrante recibe (invernadero, rol, saliente, entrante); los textos se juntan en orden de registro."""
        primero = mock.Mock(return_value=["Se cancelan 2 pedidos."])
        segundo = mock.Mock(return_value=["Se pierde otra cosa.", "Y otra más."])
        invernadero, saliente, entrante = object(), object(), object()
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", []):
            extensiones.registrar_aviso_de_traspaso(primero)
            extensiones.registrar_aviso_de_traspaso(segundo)
            textos = extensiones.avisos_de_traspaso(invernadero, "agronomo", saliente, entrante)
        self.assertEqual(textos, ["Se cancelan 2 pedidos.", "Se pierde otra cosa.", "Y otra más."])
        primero.assert_called_once_with(invernadero, "agronomo", saliente, entrante)
        segundo.assert_called_once_with(invernadero, "agronomo", saliente, entrante)

    def test_ext_cada_registrante_se_llama_una_sola_vez_por_aviso(self):
        """Prueba mínima (sin consultas por fila): una llamada por registrante y por cambio, no una por elemento."""
        llamada = mock.Mock(return_value=[])
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", []):
            extensiones.registrar_aviso_de_traspaso(llamada)
            extensiones.avisos_de_traspaso(object(), "capataz", None, None)
        self.assertEqual(llamada.call_count, 1)


class ImpedimentoConUrlTests(SimpleTestCase):
    """`Impedimento` suma `url`, opcional: todo lo que ya lo construye con tres valores sigue funcionando."""

    def test_sin_url_es_none(self):
        """Compatibilidad: ``Impedimento(codigo, texto, como_resolver)`` deja ``url`` en ``None``."""
        impedimento = Impedimento("lotes_activos", "Tiene 2 lotes.", "Cosechalos.")
        self.assertIsNone(impedimento.url)
        self.assertEqual(tuple(impedimento)[:3], ("lotes_activos", "Tiene 2 lotes.", "Cosechalos."))

    def test_con_url_la_guarda(self):
        """La ``url`` lleva a lo que impide (por ejemplo, la ficha del pedido)."""
        self.assertEqual(Impedimento("pedido_en_curso", "x", "y", "/compras/pedidos/3/").url, "/compras/pedidos/3/")


class AvisosEnLaVentanaDeCambioDePersonalTests(ConGeoref, TestCase):
    """`modificar_invernadero` (regla 2 de PROD-MOD-INV): el aviso de cada cambio trae ``avisos``, con o sin persona entrante."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)

    def avisar(self, **cambios):
        datos = datos_de(self.invernadero) | cambios
        with self.assertRaises(invernaderos.FaltaConfirmarPersonal) as contexto:
            invernaderos.modificar_invernadero(self.gerente, self.invernadero.pk, **datos)
        return contexto.exception.aviso

    def test_regla_2_el_aviso_trae_los_textos_de_los_registrantes_aunque_no_haya_entrante(self):
        """Los textos llegan con persona entrante y también cuando el rol queda vacío; ``recibe`` no los incluye."""
        nuevo = crear_agronomo("nuevo@infoponia.com")
        textos = mock.Mock(return_value=["Se cancelan 2 pedidos de cotización."])
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", [textos]):
            con_entrante = self.avisar(agronomo_id=nuevo.pk)
            sin_entrante = self.avisar(agronomo_id=None)
        for aviso in (con_entrante[0], sin_entrante[0]):
            self.assertEqual(aviso["avisos"], ["Se cancelan 2 pedidos de cotización."])
            self.assertEqual(aviso["recibe"], [])
        self.assertTrue(sin_entrante[0]["queda_vacio"])

    def test_regla_2_sin_registrantes_los_avisos_son_una_lista_vacia(self):
        """Sin registrantes, ``avisos`` es ``[]`` y la ventana queda como antes."""
        nuevo = crear_agronomo("nuevo@infoponia.com")
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", []):
            self.assertEqual(self.avisar(agronomo_id=nuevo.pk)[0]["avisos"], [])

    def test_regla_2_el_aviso_no_llega_a_la_notificacion_de_quien_entra(self):
        """Postcondición c (NOT-01): la notificación de quien queda a cargo dice lo que recibe; lo que se cancela no va ahí."""
        from core.models import Notificacion

        nuevo = crear_agronomo("nuevo@infoponia.com")
        datos = datos_de(self.invernadero) | {"agronomo_id": nuevo.pk}
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", [lambda *args: ["Se cancelan 2 pedidos de cotización."]]):
            invernaderos.modificar_invernadero(self.gerente, self.invernadero.pk, **datos, personal_confirmado=True)
        for notificacion in Notificacion.objects.filter(destinatario=nuevo):
            self.assertNotIn("cancelan", notificacion.detalle)


class VentanasConAvisosYEnlacesTests(ConGeoref, TestCase):
    """Las ventanas de maestros: «Confirmá el cambio de personal» muestra los avisos y la de la baja del invernadero, el enlace de un impedimento."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.client.force_login(self.gerente)
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Invernadero A", agronomo=self.agronomo)
        self.misiones = Provincia.objects.get(nombre_provincia="Misiones")
        self.capital = Departamento.objects.get(nombre_departamento="Capital", provincia=self.misiones)

    def datos(self, **extra):
        return {
            "nombre": "Invernadero A",
            "tipo_direccion": "urbana",
            "provincia": self.misiones.pk,
            "departamento": self.capital.pk,
            "localidad": localidad().pk,
            "calle": "Calle 122",
            "numero_calle": "3310",
            "agronomo": self.agronomo.pk,
        } | extra

    def test_regla_2_la_ventana_muestra_los_avisos_con_un_agronomo_entrante(self):
        """La ventana de confirmación del cambio de personal lista lo que se cancela y no guarda hasta confirmar."""
        nuevo = crear_agronomo("nuevo@infoponia.com")
        url = reverse("maestros:invernadero_modificar", args=[self.invernadero.pk])
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", [lambda *args: ["Se cancelan 2 pedidos de cotización en curso."]]):
            respuesta = self.client.post(url, self.datos(agronomo=nuevo.pk))
        self.assertContains(respuesta, "Confirmá el cambio de personal")
        self.assertContains(respuesta, "Se cancelan 2 pedidos de cotización en curso.")
        self.assertEqual(Invernadero.objects.get(pk=self.invernadero.pk).agronomo_id, self.agronomo.pk)
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_regla_2_la_ventana_muestra_los_avisos_tambien_cuando_el_rol_queda_vacio(self):
        """Sin Agrónomo entrante la ventana dice que el invernadero queda sin Agrónomo y, además, lo que se cancela."""
        url = reverse("maestros:invernadero_modificar", args=[self.invernadero.pk])
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", [lambda *args: ["Se cancelan 2 pedidos de cotización en curso."]]):
            respuesta = self.client.post(url, self.datos(agronomo=""))
        self.assertContains(respuesta, "queda <b>sin Agrónomo</b>")
        self.assertContains(respuesta, "Se cancelan 2 pedidos de cotización en curso.")

    def test_regla_2_sin_avisos_la_ventana_no_agrega_nada(self):
        """Sin registrantes la ventana es la de siempre."""
        nuevo = crear_agronomo("nuevo@infoponia.com")
        url = reverse("maestros:invernadero_modificar", args=[self.invernadero.pk])
        with mock.patch.object(extensiones, "_AVISOS_DE_TRASPASO", []):
            respuesta = self.client.post(url, self.datos(agronomo=nuevo.pk))
        self.assertNotContains(respuesta, "cancelan")

    def test_regla_2_de_baj_inv_la_ventana_de_baja_muestra_el_enlace_de_un_impedimento_con_url(self):
        """Un impedimento con ``url`` se muestra con su enlace «Ver detalle» (el pedido en curso); uno sin ``url`` sigue como texto."""
        con_url = Impedimento("pedido_en_curso", "Está en el pedido P-0031.", "Esperá a que se cierre.", "/compras/pedidos/31/")
        sin_url = Impedimento("registro_falso", "Hay un registro falso.", "Borralo.")
        with con_impedimentos(lambda invernadero: [con_url, sin_url]):
            respuesta = self.client.get(reverse("maestros:invernadero_baja", args=[self.invernadero.pk]), HTTP_HX_REQUEST="true")
        self.assertContains(respuesta, "Está en el pedido P-0031. Esperá a que se cierre.")
        self.assertContains(respuesta, 'href="/compras/pedidos/31/"')
        self.assertContains(respuesta, "Ver detalle")
        self.assertContains(respuesta, "Hay un registro falso. Borralo.")
        self.assertEqual(respuesta.content.decode().count("Ver detalle"), 1)
