# Pruebas de la advertencia de rangos (INV-03, paso 3): `incompatibilidades_de_rangos(variedad, rangos_nuevos)` de
# `inventario/servicios/variedades.py` (regla 5 de PROD-MOD-VAR y «Advertencia de rangos» de docs/casos_de_uso/inventario/variedades.md).
# Para cada invernadero donde la variedad tiene lotes activos se compara el rango NUEVO con el de cada OTRA variedad presente (lotes
# activos u órdenes de siembra a realizar): hay incompatibilidad en una variable si ``max(mínimos) > min(máximos)``. Cada una es
# ``Incompatibilidad(invernadero_id, variable, variedad_id)``: el invernadero, la variable y la variedad con la que choca. Sin
# registrantes de `produccion` (los lotes y las variedades presentes se simulan), nunca hay advertencia.

from decimal import Decimal

from django.test import TestCase

from inventario.extensiones import UsoDeVariedad
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    perezoso,
    usos_de_variedad_de_prueba,
    variedad_con_semilla,
    variedades_presentes_de_prueba,
)
from maestros.tests.fabricas import crear_cultivo, crear_invernadero

variedades = perezoso("inventario.servicios.variedades")

VARIABLES = ("temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo")


def rangos(**por_variable):
    """``Rangos`` nuevos: los de la variedad base (18-24, 60-80, 200-400, 12-16) salvo los que se pasen como ``(minimo, maximo)``."""
    base = {
        "temp_ambiente": ("18", "24"),
        "humedad": ("60", "80"),
        "intensidad_luz": ("200", "400"),
        "fotoperiodo": ("12", "16"),
    }
    base.update(por_variable)
    return variedades.Rangos(
        **{variable: variedades.RangoAmbiental(Decimal(minimo), Decimal(maximo)) for variable, (minimo, maximo) in base.items()}
    )


class IncompatibilidadesDeRangosTests(ConDatosDeInventario, TestCase):
    """La regla se prueba con la variedad ``a`` (con lotes activos en el invernadero) y otras presentes en él."""

    def setUp(self):
        self.cultivo = crear_cultivo("Lechuga")
        self.invernadero = crear_invernadero("Invernadero Norte")
        self.a = variedad_con_semilla(self.cultivo, "A")  # 18-24, 60-80, 200-400, 12-16
        self.b = variedad_con_semilla(self.cultivo, "B")  # igual: compatible

    def incompatibilidades(self, nuevos, presentes=None, invernaderos=None):
        """Corre la regla con ``a`` con lotes activos en ``invernaderos`` (por omisión, el de la prueba) y ``presentes`` allí."""
        invernaderos = self.invernadero.pk if invernaderos is None else invernaderos
        ids = {invernaderos} if isinstance(invernaderos, int) else set(invernaderos)
        uso = UsoDeVariedad(True, 1, 0, frozenset(ids))
        presentes = {i: presentes if presentes is not None else {self.a.pk, self.b.pk} for i in ids}
        with usos_de_variedad_de_prueba({self.a.pk: uso}), variedades_presentes_de_prueba(presentes):
            return variedades.incompatibilidades_de_rangos(self.a, nuevos)

    def test_regla_mod_var_5_rangos_que_se_cruzan_no_son_incompatibles(self):
        """PROD-MOD-VAR regla 5: dos rangos que se cruzan comparten valores: no hay incompatibilidad."""
        self.assertEqual(self.incompatibilidades(rangos(temp_ambiente=("20", "30"))), [])

    def test_regla_mod_var_5_rangos_que_se_tocan_en_un_extremo_no_son_incompatibles(self):
        """Advertencia de rangos: incompatible solo si ``max(mínimos) > min(máximos)``: tocarse en un extremo (24 = 24) es válido."""
        self.assertEqual(self.incompatibilidades(rangos(temp_ambiente=("24", "30"))), [])
        self.assertEqual(self.incompatibilidades(rangos(temp_ambiente=("10", "18"))), [])

    def test_regla_mod_var_5_rangos_que_no_se_cruzan_son_incompatibles_y_dicen_con_quien_chocan(self):
        """PROD-MOD-VAR regla 5: el Sistema advierte en qué invernadero y en qué variable (y con qué variedad)."""
        resultado = self.incompatibilidades(rangos(temp_ambiente=("25", "30")))
        self.assertEqual(resultado, [variedades.Incompatibilidad(self.invernadero.pk, "temp_ambiente", self.b.pk)])

    def test_regla_mod_var_5_rango_nuevo_por_debajo_tambien_es_incompatible(self):
        """Advertencia de rangos: el rango nuevo que queda enteramente por debajo del de la otra variedad también choca."""
        resultado = self.incompatibilidades(rangos(temp_ambiente=("5", "17")))
        self.assertEqual(resultado, [variedades.Incompatibilidad(self.invernadero.pk, "temp_ambiente", self.b.pk)])

    def test_regla_mod_var_5_cada_variable_se_compara_por_separado(self):
        """PROD-MOD-VAR regla 5: la incompatibilidad se informa por variable; probamos las cuatro."""
        nuevos = {
            "temp_ambiente": ("30", "35"),
            "humedad": ("85", "95"),
            "intensidad_luz": ("500", "600"),
            "fotoperiodo": ("18", "20"),
        }
        for variable in VARIABLES:
            with self.subTest(variable=variable):
                resultado = self.incompatibilidades(rangos(**{variable: nuevos[variable]}))
                self.assertEqual(resultado, [variedades.Incompatibilidad(self.invernadero.pk, variable, self.b.pk)])

    def test_regla_mod_var_5_varias_variables_a_la_vez_salen_juntas_en_el_orden_de_los_rangos(self):
        """PROD-MOD-VAR regla 5: se informan todas las variables incompatibles, en el orden de ``Rangos``."""
        resultado = self.incompatibilidades(rangos(fotoperiodo=("18", "20"), temp_ambiente=("30", "35")))
        self.assertEqual(
            [(i.variable, i.variedad_id) for i in resultado], [("temp_ambiente", self.b.pk), ("fotoperiodo", self.b.pk)]
        )

    def test_regla_mod_var_5_choca_con_cada_variedad_presente_por_separado(self):
        """Advertencia de rangos: se compara de a pares para poder nombrar con quién choca; una entrada por variedad."""
        c = variedad_con_semilla(self.cultivo, "C", temp_ambiente_min="19", temp_ambiente_max="22")
        resultado = self.incompatibilidades(
            rangos(temp_ambiente=("25", "30")), presentes={self.a.pk, self.b.pk, c.pk}
        )
        self.assertEqual(
            sorted((i.variable, i.variedad_id) for i in resultado),
            sorted([("temp_ambiente", self.b.pk), ("temp_ambiente", c.pk)]),
        )

    def test_regla_mod_var_5_la_propia_variedad_no_cuenta_como_otra(self):
        """PROD-MOD-VAR regla 5: se compara con las OTRAS variedades; la variedad no choca consigo misma con su rango anterior."""
        self.assertEqual(self.incompatibilidades(rangos(temp_ambiente=("30", "35")), presentes={self.a.pk}), [])

    def test_regla_mod_var_5_sin_otras_variedades_presentes_no_hay_incompatibilidad(self):
        """PROD-MOD-VAR regla 5: ninguna otra variedad presente en el invernadero, ninguna incompatibilidad."""
        self.assertEqual(self.incompatibilidades(rangos(temp_ambiente=("30", "35")), presentes=set()), [])

    def test_regla_mod_var_5_solo_se_miran_los_invernaderos_donde_tiene_lotes_activos(self):
        """PROD-MOD-VAR regla 5: la advertencia es para los invernaderos donde la variedad tiene lotes ACTIVOS."""
        otro = crear_invernadero("Invernadero Sur")
        with usos_de_variedad_de_prueba({self.a.pk: UsoDeVariedad(True, 0, 0, frozenset())}), variedades_presentes_de_prueba(
            {otro.pk: {self.a.pk, self.b.pk}}
        ):
            self.assertEqual(variedades.incompatibilidades_de_rangos(self.a, rangos(temp_ambiente=("30", "35"))), [])

    def test_regla_mod_var_5_informa_cada_invernadero_afectado_en_orden_de_id(self):
        """PROD-MOD-VAR regla 5: «en qué invernadero»: uno por cada invernadero con lotes activos donde hay incompatibilidad."""
        otro = crear_invernadero("Invernadero Sur")
        resultado = self.incompatibilidades(
            rangos(temp_ambiente=("30", "35")), invernaderos={self.invernadero.pk, otro.pk}
        )
        self.assertEqual([i.invernadero_id for i in resultado], sorted([self.invernadero.pk, otro.pk]))

    def test_regla_mod_var_5_sin_registrantes_de_produccion_nunca_hay_advertencia(self):
        """docs/casos_de_uso/inventario/variedades.md: sin registrante de variedades presentes (hasta PRD-01), nunca hay advertencia."""
        self.assertEqual(variedades.incompatibilidades_de_rangos(self.a, rangos(temp_ambiente=("30", "35"))), [])

    def test_regla_mod_var_5_sin_lotes_activos_en_ningun_invernadero_no_hay_advertencia(self):
        """PROD-MOD-VAR regla 5: solo si la variedad tiene lotes activos (si no, no hay lotes en producción que proteger)."""
        with variedades_presentes_de_prueba({self.invernadero.pk: {self.a.pk, self.b.pk}}):
            self.assertEqual(variedades.incompatibilidades_de_rangos(self.a, rangos(temp_ambiente=("30", "35"))), [])
