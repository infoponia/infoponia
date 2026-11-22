# Pruebas de concurrencia de los servicios de transportistas (MAE-05; docs/patrones/bloqueos.md, D-30, D-32, D-40 y D-55):
# dos agregados simultáneos del mismo Transportista, agregar contra la baja del invernadero de destino (en los dos órdenes)
# y agregar contra la baja de la cuenta del Transportista. Dos hilos, dos conexiones, el orden fijado con ``primera``
# (core/tests/concurrencia.py). Son ``TransactionTestCase``: su ``flush`` vacía todas las tablas al terminar, así que el
# invernadero se crea con geografía propia y no con Georef (docs/patrones/datos_de_migracion.md).
#
# Lo que se garantiza (D-55, punto 3): un Transportista nunca queda en dos invernaderos, y el que pierde la carrera recibe un
# rechazo claro (``FaltaConfirmarTraslado`` o un ``ValidationError``), nunca un ``IntegrityError`` sin traducir (un 500).

from django.test import TransactionTestCase, tag

from core.models import Usuario
from core.servicios import baja_usuario
from core.tests.concurrencia import codigos, correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from maestros.models import Invernadero, TransportistaInvernadero
from maestros.servicios import invernaderos
from maestros.tests.fabricas import crear_invernadero_con_geografia_propia, crear_transportista


def servicio():
    """El módulo de servicios de transportistas (se importa acá para que cada prueba falle sola mientras no exista)."""
    from maestros.servicios import transportistas

    return transportistas


@tag("concurrencia")
class TransportistasConcurrenciaTests(TransactionTestCase):
    """Bloqueos de ``agregar_transportista``: la cuenta primero, después los invernaderos en orden de id (D-40)."""

    def setUp(self):
        self.gerente = crear_gerente()
        self.norte = crear_invernadero_con_geografia_propia("Norte")
        self.sur = crear_invernadero_con_geografia_propia("Sur")
        self.diego = crear_transportista("diego@infoponia.com", nombre="Diego", apellido="Ferreyra")

    def agregar(self, invernadero, **extra):
        return lambda: servicio().agregar_transportista(self.gerente, invernadero.pk, self.diego.pk, **extra)

    def test_d55_dos_agregados_del_mismo_transportista_dejan_una_sola_fila(self):
        """D-55 punto 3 y D-40: dos ``agregar_transportista`` simultáneos del mismo Transportista a dos invernaderos. La
        segunda espera el bloqueo de la cuenta, ve la fila de la primera y, sin traslado confirmado, avisa del traslado:
        queda una sola fila y nadie recibe un ``IntegrityError`` (un 500). Sin el bloqueo de la cuenta, la segunda no vería la
        fila todavía sin confirmar y chocaría con la restricción única de la base."""
        resultados = correr_a_la_vez(self.agregar(self.norte), self.agregar(self.sur), primera="a")

        self.assertIsInstance(resultados["a"], TransportistaInvernadero)
        self.assertIsInstance(resultados["b"], servicio().FaltaConfirmarTraslado)
        self.assertEqual(resultados["b"].origen.pk, self.norte.pk)
        fila = TransportistaInvernadero.objects.get()
        self.assertEqual(fila.invernadero_id, self.norte.pk)

    def test_d55_dos_agregados_con_traslado_confirmado_terminan_en_el_ultimo_sin_error(self):
        """D-55 punto 3: si la segunda ya confirmó el traslado, espera, ve la fila de la primera y la traslada: una sola
        fila, en el invernadero de la segunda, y los dos registros del traslado."""
        resultados = correr_a_la_vez(
            self.agregar(self.norte), self.agregar(self.sur, traslado_confirmado=True), primera="a"
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(TransportistaInvernadero.objects.get().invernadero_id, self.sur.pk)

    def test_d55_agregar_espera_a_la_baja_del_invernadero_y_se_rechaza(self):
        """D-40 y PROD-MOD-INV regla 5: la baja del destino va primera y el agregado espera el bloqueo del invernadero; cuando
        sigue, el invernadero está inactivo (``invernadero_inactivo``) y no crea la fila. Sin ``bloquear_invernadero_activo``
        se crearía un transportista activo en un invernadero ya dado de baja."""
        resultados = correr_a_la_vez(
            lambda: invernaderos.baja_invernadero(self.gerente, self.norte.pk), self.agregar(self.norte), primera="a"
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["invernadero_inactivo"])
        self.assertFalse(TransportistaInvernadero.objects.exists())
        self.assertFalse(Invernadero.objects.get(pk=self.norte.pk).activo)

    def test_d55_la_baja_del_invernadero_espera_al_agregado_y_ve_al_transportista(self):
        """D-40, regla 3 de PROD-BAJ-INV: el agregado va primero y la baja espera; cuando sigue, ve al Transportista activo
        y se rechaza (``transportistas_activos``). Sin el bloqueo del invernadero en el agregado, la baja no vería la fila
        sin confirmar y daría de baja un invernadero con un impedimento."""
        resultados = correr_a_la_vez(
            self.agregar(self.norte), lambda: invernaderos.baja_invernadero(self.gerente, self.norte.pk), primera="a"
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["transportistas_activos"])
        self.assertTrue(Invernadero.objects.get(pk=self.norte.pk).activo)
        self.assertEqual(TransportistaInvernadero.objects.get().invernadero_id, self.norte.pk)

    def test_d55_agregar_espera_a_la_baja_de_la_cuenta_y_se_rechaza(self):
        """D-30, D-40 y regla 8 (solo activos): la baja de la cuenta va primera; el agregado espera el bloqueo de la cuenta y,
        cuando sigue, la ve inactiva (``transportista_inactivo``). Sin releer ``is_active`` después de bloquear, se agregaría a
        una cuenta ya dada de baja."""
        resultados = correr_a_la_vez(
            lambda: baja_usuario(self.gerente, self.diego.pk), self.agregar(self.norte), primera="a"
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertEqual(codigos(rechazos[0]), ["transportista_inactivo"])
        self.assertFalse(TransportistaInvernadero.objects.exists())
        self.assertFalse(Usuario.objects.get(pk=self.diego.pk).is_active)

    def test_d55_quitar_y_agregar_a_la_vez_dejan_una_fila_consistente(self):
        """D-40: quitar (primera) y agregar al otro invernadero a la vez. La segunda espera la cuenta, ve que ya no tiene
        invernadero y crea la fila: termina una sola fila, en el destino, sin error."""
        transportistas_agregados = servicio().agregar_transportista(self.gerente, self.norte.pk, self.diego.pk)
        self.assertIsNotNone(transportistas_agregados)

        resultados = correr_a_la_vez(
            lambda: servicio().quitar_transportista(self.gerente, self.norte.pk, self.diego.pk),
            self.agregar(self.sur),
            primera="a",
        )

        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(TransportistaInvernadero.objects.get().invernadero_id, self.sur.pk)
