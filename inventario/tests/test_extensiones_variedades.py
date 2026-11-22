# Pruebas de los tres puntos de extensión de variedades de `inventario` (INV-03, paso 1): resultado neutro sin registrantes, los
# de varios registrantes se juntan y no hay consultas por fila (una llamada por registrante para toda la lista).
# Fuente: docs/api/extensiones_de_inventario.md, «Variedades».

from unittest import mock

from django.test import SimpleTestCase

from inventario import extensiones
from inventario.extensiones import UsoDeVariedad
from maestros.extensiones import Impedimento

NEUTRO = UsoDeVariedad(False, 0, 0, frozenset())


class UsoDeVariedadesTests(SimpleTestCase):
    """``registrar_uso_de_variedad`` y ``uso_de_variedades``."""

    def test_sin_registrantes_da_el_neutro_para_cada_id(self):
        """API: lo que no figura es ``UsoDeVariedad(False, 0, 0, frozenset())``."""
        with mock.patch.object(extensiones, "_USOS_DE_VARIEDAD", []):
            self.assertEqual(extensiones.uso_de_variedades([1, 2]), {1: NEUTRO, 2: NEUTRO})

    def test_junta_los_de_varios_registrantes(self):
        """API: con varios registrantes se suman los contadores, se unen los invernaderos y ``con_lotes`` es verdadero si alguno lo dice."""
        uno = lambda ids: {1: UsoDeVariedad(True, 2, 1, frozenset({10}))}
        otro = lambda ids: {1: UsoDeVariedad(False, 1, 3, frozenset({11}))}
        with mock.patch.object(extensiones, "_USOS_DE_VARIEDAD", [uno, otro]):
            resultado = extensiones.uso_de_variedades([1, 2])
        self.assertEqual(resultado[1], UsoDeVariedad(True, 3, 4, frozenset({10, 11})))
        self.assertEqual(resultado[2], NEUTRO)

    def test_una_llamada_por_registrante_para_toda_la_lista(self):
        """API: reciben listas de ids; nunca una llamada por fila."""
        registrante = mock.Mock(return_value={})
        with mock.patch.object(extensiones, "_USOS_DE_VARIEDAD", [registrante]):
            extensiones.uso_de_variedades([1, 2, 3])
        registrante.assert_called_once_with([1, 2, 3])

    def test_ignora_ids_que_no_se_pidieron(self):
        """API: un registrante que devuelve un id de más no lo agrega al resultado."""
        with mock.patch.object(extensiones, "_USOS_DE_VARIEDAD", [lambda ids: {9: UsoDeVariedad(True, 1, 0, frozenset())}]):
            self.assertEqual(set(extensiones.uso_de_variedades([1])), {1})


class VariedadesPresentesTests(SimpleTestCase):
    """``registrar_variedades_presentes`` y ``variedades_presentes``."""

    def test_sin_registrantes_da_un_conjunto_vacio_por_invernadero(self):
        """API: lo que no figura es un conjunto vacío."""
        with mock.patch.object(extensiones, "_VARIEDADES_PRESENTES", []):
            self.assertEqual(extensiones.variedades_presentes([1, 2]), {1: set(), 2: set()})

    def test_une_las_variedades_de_varios_registrantes(self):
        """API: las variedades presentes de todos los registrantes se unen por invernadero."""
        uno = lambda ids: {1: {5}}
        otro = lambda ids: {1: {6}, 2: {7}}
        with mock.patch.object(extensiones, "_VARIEDADES_PRESENTES", [uno, otro]):
            self.assertEqual(extensiones.variedades_presentes([1, 2, 3]), {1: {5, 6}, 2: {7}, 3: set()})

    def test_una_llamada_por_registrante_para_toda_la_lista(self):
        """API: una llamada por registrante con todos los invernaderos, no una por invernadero."""
        registrante = mock.Mock(return_value={})
        with mock.patch.object(extensiones, "_VARIEDADES_PRESENTES", [registrante]):
            extensiones.variedades_presentes([1, 2, 3])
        registrante.assert_called_once_with([1, 2, 3])


class ImpedimentosDeBajaDeVariedadTests(SimpleTestCase):
    """``registrar_impedimento_de_baja_de_variedad`` e ``impedimentos_de_baja_de_variedad``."""

    def test_sin_registrantes_no_hay_impedimentos(self):
        """API: sin registrantes (hasta PRD-01 y `comercial`) la lista es vacía."""
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_BAJA_DE_VARIEDAD", []):
            self.assertEqual(extensiones.impedimentos_de_baja_de_variedad(object()), [])

    def test_regla_baj_var_2_junta_los_de_todos_sin_quedarse_con_el_primero(self):
        """PROD-BAJ-VAR regla 2: los impedimentos de todos los registrantes, juntos."""
        a = Impedimento("lotes_activos", "Tiene 2 lotes activos.", "Terminá los lotes.")
        b = Impedimento("contratos_abiertos", "Tiene 1 contrato.", "Cerralo.")
        with mock.patch.object(extensiones, "_IMPEDIMENTOS_DE_BAJA_DE_VARIEDAD", [lambda v: [a], lambda v: [b]]):
            self.assertEqual(extensiones.impedimentos_de_baja_de_variedad(object()), [a, b])
