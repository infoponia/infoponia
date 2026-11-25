# Pruebas de `produccion/extensiones.py` (COM-02, D-59 punto 3; docs/api/extensiones_de_produccion.md, sección 5): sin registrante, cada
# punto da su resultado neutro (sin consultar la base) y un segundo registrante se rechaza. Los registrantes reales de `comercial` están
# instalados en las pruebas, así que cada una parchea la lista del punto que prueba.

from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from contabilidad import extensiones as extensiones_de_contabilidad
from produccion import extensiones
from produccion.servicios import asientos_de_produccion


class ExtensionesDeProduccionTests(TestCase):
    """Los dos puntos de `produccion.extensiones`."""

    def test_ext_reservado_sin_registrante_da_cero_para_cada_lote(self):
        """API de extensiones de `produccion`, punto 1: sin registrante, todas las claves pedidas valen 0."""
        with mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", []):
            self.assertEqual(extensiones.reservado_de_lotes([3, 4]), {3: 0, 4: 0})

    def test_ext_reservado_con_lista_vacia_da_vacio_sin_consultar_la_base(self):
        """API, punto 1: una lista vacía da `{}` sin tocar la base (aun con el registrante real instalado)."""
        with self.assertNumQueries(0):
            self.assertEqual(extensiones.reservado_de_lotes([]), {})

    def test_ext_reservado_completa_con_cero_los_lotes_que_el_registrante_no_nombra(self):
        """API, punto 1: «un lote sin reservas puede faltar en el diccionario»: la función pública lo completa con 0."""
        with mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", [lambda ids: {ids[0]: 7}]):
            self.assertEqual(extensiones.reservado_de_lotes([1, 2]), {1: 7, 2: 0})

    def test_ext_reservado_rechaza_un_segundo_registrante(self):
        """API, punto 1: a lo sumo un registrante (`comercial`); un segundo lanza `ImproperlyConfigured`."""
        with mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", []):
            extensiones.registrar_reservado_de_lote(lambda ids: {})
            with self.assertRaises(ImproperlyConfigured):
                extensiones.registrar_reservado_de_lote(lambda ids: {})

    def test_ext_reservado_registrar_la_misma_funcion_dos_veces_es_idempotente(self):
        """`ready()` puede correr más de una vez: la misma función no cuenta como un segundo registrante."""
        funcion = lambda ids: {}  # noqa: E731
        with mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", []):
            extensiones.registrar_reservado_de_lote(funcion)
            extensiones.registrar_reservado_de_lote(funcion)
            self.assertEqual(extensiones._RESERVADO_DE_LOTE, [funcion])

    def test_ext_detalle_sin_registrante_da_vacio(self):
        """API, punto 2: sin registrante, `{}`."""
        with mock.patch.object(extensiones, "_DETALLE_DE_COSECHA", []):
            self.assertEqual(extensiones.detalle_de_cosechas([1, 2]), {})

    def test_ext_detalle_con_lista_vacia_da_vacio_sin_consultar_la_base(self):
        """API, punto 2: una lista vacía da `{}` sin tocar la base."""
        with self.assertNumQueries(0):
            self.assertEqual(extensiones.detalle_de_cosechas([]), {})

    def test_ext_detalle_rechaza_un_segundo_registrante(self):
        """API, punto 2: a lo sumo un registrante; un segundo lanza `ImproperlyConfigured`."""
        with mock.patch.object(extensiones, "_DETALLE_DE_COSECHA", []):
            extensiones.registrar_detalle_de_cosecha(lambda ids: {})
            with self.assertRaises(ImproperlyConfigured):
                extensiones.registrar_detalle_de_cosecha(lambda ids: {})

    def test_ext_el_detalle_de_cosecha_se_arma_con_contrato_fecha_y_lotes(self):
        """API, punto 2: `DetalleDeCosecha(contrato, fecha_entrega, lotes)` con `lotes` = `(lote_id, reservada, cosechada)`."""
        detalle = extensiones.DetalleDeCosecha("CV-0001", None, [(1, 10, None)])
        self.assertEqual((detalle.contrato, detalle.fecha_entrega, detalle.lotes), ("CV-0001", None, [(1, 10, None)]))



class AccionesDeCosechaTests(TestCase):
    """Punto 3 (COM-04a, D-64 punto 11): `registrar_acciones_de_cosecha` y `acciones_de_cosechas`; el contenido real lo prueba `comercial`."""

    def test_ext_acciones_sin_registrante_da_vacio(self):
        """API, punto 3: sin registrante, `{}` (la pantalla no muestra botones)."""
        with mock.patch.object(extensiones, "_ACCIONES_DE_COSECHA", []):
            self.assertEqual(extensiones.acciones_de_cosechas(object(), [1, 2]), {})

    def test_ext_acciones_con_lista_vacia_da_vacio_sin_consultar_la_base(self):
        """API, punto 3: una lista vacía da `{}` sin tocar la base."""
        with self.assertNumQueries(0):
            self.assertEqual(extensiones.acciones_de_cosechas(object(), []), {})

    def test_ext_acciones_con_registrante_devuelve_lo_que_este_arma(self):
        """API, punto 3: `AccionesDeCosecha(concretar, modificar, cancelar)`: cada campo es una URL o `None`."""
        acciones = extensiones.AccionesDeCosecha("/c/", None, None)
        with mock.patch.object(extensiones, "_ACCIONES_DE_COSECHA", [lambda usuario, ids: {ids[0]: acciones}]):
            self.assertEqual(extensiones.acciones_de_cosechas(object(), [7]), {7: acciones})
        self.assertEqual((acciones.concretar, acciones.modificar, acciones.cancelar), ("/c/", None, None))

    def test_ext_acciones_rechaza_un_segundo_registrante_y_es_idempotente_con_el_mismo(self):
        """API, punto 3: a lo sumo un registrante (`comercial`); la misma función dos veces no cuenta como un segundo."""
        funcion = lambda usuario, ids: {}  # noqa: E731
        with mock.patch.object(extensiones, "_ACCIONES_DE_COSECHA", []):
            extensiones.registrar_acciones_de_cosecha(funcion)
            extensiones.registrar_acciones_de_cosecha(funcion)
            with self.assertRaises(ImproperlyConfigured):
                extensiones.registrar_acciones_de_cosecha(lambda usuario, ids: {})


class EntradasDeComercialTests(TestCase):
    """Punto 4 (COM-04a, D-64 punto 11): `registrar_entradas_de_comercial` y `entradas_de_comercial`."""

    def test_ext_entradas_sin_registrante_da_las_dos_en_none(self):
        """API, punto 4: sin registrante, `EntradasDeComercial(None, None)`: ningún acceso."""
        with mock.patch.object(extensiones, "_ENTRADAS_DE_COMERCIAL", []):
            entradas = extensiones.entradas_de_comercial(object())
        self.assertEqual((entradas.planificar_cosecha, entradas.merma_en_camara, entradas.envasado), (None, None, None))

    def test_ext_entradas_envasado_tiene_valor_por_defecto(self):
        """API punto 4 (COM-05a2): quien arma la tupla con dos campos sigue funcionando; `envasado` queda en `None`."""
        entradas = extensiones.EntradasDeComercial("/plan/", "/camara/")
        self.assertIsNone(entradas.envasado)
        self.assertEqual(extensiones.EntradasDeComercial("/plan/", "/camara/", "/envasado/").envasado, "/envasado/")

    def test_ext_entradas_con_registrante_devuelve_lo_que_este_arma(self):
        """API, punto 4: URL o `None` en `planificar_cosecha` y `merma_en_camara`."""
        entradas = extensiones.EntradasDeComercial("/plan/", "/camara/")
        with mock.patch.object(extensiones, "_ENTRADAS_DE_COMERCIAL", [lambda usuario: entradas]):
            self.assertEqual(extensiones.entradas_de_comercial(object()), entradas)

    def test_ext_entradas_rechaza_un_segundo_registrante_y_es_idempotente_con_el_mismo(self):
        """API, punto 4: a lo sumo un registrante."""
        funcion = lambda usuario: extensiones.EntradasDeComercial(None, None)  # noqa: E731
        with mock.patch.object(extensiones, "_ENTRADAS_DE_COMERCIAL", []):
            extensiones.registrar_entradas_de_comercial(funcion)
            extensiones.registrar_entradas_de_comercial(funcion)
            with self.assertRaises(ImproperlyConfigured):
                extensiones.registrar_entradas_de_comercial(lambda usuario: None)


class EnlaceDeOrigenDeLosAsientosTests(TestCase):
    """CON-04a: `produccion` registra en `contabilidad` el texto de origen de sus asientos (la bitácora). Los textos de un consumo y de una merma reales
    se prueban junto con cada caso de uso (`test_prod_cnc_smb`, `test_prod_reg_apl`, `test_prod_reg_mrm`)."""

    def test_el_enlace_de_la_bitacora_esta_registrado_en_contabilidad(self):
        """`ready()` registra la función para el tipo «bitacora» (y no la duplica si corre dos veces)."""
        registradas = extensiones_de_contabilidad._ENLACES_DE_ORIGEN["bitacora"]
        self.assertEqual(registradas.count(asientos_de_produccion.enlace_de_origen), 1)

    def test_una_bitacora_que_no_es_consumo_ni_merma_no_tiene_texto_propio(self):
        """Otra bitácora (un evento, una transición…) da `None`: la ficha muestra solo el tipo, sin enlace."""
        self.assertIsNone(asientos_de_produccion.enlace_de_origen(mock.Mock(pk=0)))
