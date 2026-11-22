# Pruebas del umbral efectivo (INV-03, paso 3): `umbral_efectivo` y `variables_incompatibles` de `inventario/servicios/variedades.py`
# (docs/api/variedades.md, «Umbral efectivo», agregada el 21/11/2026). Lo usan PRD-01 (Planificar Siembra) y el módulo IoT. El umbral
# es la intersección de los rangos de las variedades presentes en el invernadero (lotes activos u órdenes de siembra a realizar); las
# variedades presentes se simulan con ``variedades_presentes_de_prueba`` porque `produccion` todavía no existe.

from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from inventario.tests.fabricas import ConDatosDeInventario, perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from maestros.tests.fabricas import crear_cultivo, crear_invernadero

variedades = perezoso("inventario.servicios.variedades")


def d(valor):
    return Decimal(str(valor))


class UmbralEfectivoTests(ConDatosDeInventario, TestCase):
    """``umbral_efectivo(invernadero_ids) -> dict[int, UmbralEfectivo | None]``."""

    def setUp(self):
        self.cultivo = crear_cultivo("Lechuga")
        self.norte = crear_invernadero("Invernadero Norte")
        self.sur = crear_invernadero("Invernadero Sur")

    def variedad(self, nombre, **columnas):
        return variedad_con_semilla(self.cultivo, nombre, **columnas)

    def test_api_sin_registrante_todos_los_invernaderos_valen_none(self):
        """docs/api/variedades.md: todo id pedido figura en el resultado; sin registrante (hasta PRD-01), todos valen ``None``."""
        self.assertEqual(variedades.umbral_efectivo([self.norte.pk, self.sur.pk]), {self.norte.pk: None, self.sur.pk: None})

    def test_api_un_invernadero_sin_variedades_presentes_vale_none(self):
        """docs/api/variedades.md: vale ``None`` si el invernadero no tiene variedades presentes."""
        a = self.variedad("A")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk}}):
            resultado = variedades.umbral_efectivo([self.norte.pk, self.sur.pk])
        self.assertIsNotNone(resultado[self.norte.pk])
        self.assertIsNone(resultado[self.sur.pk])

    def test_api_una_variedad_el_umbral_es_su_rango(self):
        """docs/api/variedades.md: con una sola variedad, el umbral son sus rangos; ella fija los dos límites; ``variedad_ids`` la contiene."""
        a = self.variedad("A", temp_ambiente_min="17.5", temp_ambiente_max="25")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk}}):
            umbral = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk]
        self.assertEqual(umbral.variedad_ids, frozenset({a.pk}))
        self.assertEqual(umbral.temp_ambiente, variedades.LimitesDelUmbral(d("17.50"), d("25.00"), a.pk, a.pk))
        self.assertEqual(umbral.humedad, variedades.LimitesDelUmbral(d(60), d(80), a.pk, a.pk))
        self.assertEqual(umbral.intensidad_luz, variedades.LimitesDelUmbral(d(200), d(400), a.pk, a.pk))
        self.assertEqual(umbral.fotoperiodo, variedades.LimitesDelUmbral(d(12), d(16), a.pk, a.pk))

    def test_api_dos_que_se_cruzan_dan_la_interseccion_y_dicen_que_variedad_fija_cada_limite(self):
        """docs/api/variedades.md: ``minimo`` es el mayor de los mínimos y ``maximo`` el menor de los máximos, con la variedad que lo fija."""
        a = self.variedad("A", temp_ambiente_min="18", temp_ambiente_max="24")
        b = self.variedad("B", temp_ambiente_min="20", temp_ambiente_max="28")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk, b.pk}}):
            umbral = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk]
        self.assertEqual(umbral.variedad_ids, frozenset({a.pk, b.pk}))
        self.assertEqual(umbral.temp_ambiente, variedades.LimitesDelUmbral(d(20), d(24), b.pk, a.pk))

    def test_api_empate_en_un_limite_gana_la_variedad_de_menor_id(self):
        """docs/api/variedades.md: si dos variedades empatan en un límite, se toma la de menor id, para que el resultado sea siempre el mismo."""
        a = self.variedad("A", temp_ambiente_min="18", temp_ambiente_max="24")
        b = self.variedad("B", temp_ambiente_min="18", temp_ambiente_max="24")
        menor = min(a.pk, b.pk)
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk, b.pk}}):
            umbral = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk]
        self.assertEqual((umbral.temp_ambiente.variedad_minimo_id, umbral.temp_ambiente.variedad_maximo_id), (menor, menor))

    def test_api_rangos_que_se_tocan_en_un_extremo_dejan_minimo_igual_al_maximo(self):
        """docs/api/variedades.md: que se toquen en un extremo no es vacío: el umbral queda con ``minimo == maximo``."""
        a = self.variedad("A", temp_ambiente_min="18", temp_ambiente_max="22")
        b = self.variedad("B", temp_ambiente_min="22", temp_ambiente_max="28")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk, b.pk}}):
            umbral = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk]
        self.assertEqual(umbral.temp_ambiente, variedades.LimitesDelUmbral(d(22), d(22), b.pk, a.pk))

    def test_api_una_variable_sin_superposicion_es_none_y_las_demas_siguen_bien(self):
        """docs/api/variedades.md: una variable vale ``None`` si en ella los rangos no se superponen; las otras no se afectan."""
        a = self.variedad("A", temp_ambiente_min="18", temp_ambiente_max="20")
        b = self.variedad("B", temp_ambiente_min="25", temp_ambiente_max="30")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk, b.pk}}):
            umbral = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk]
        self.assertIsNone(umbral.temp_ambiente)
        self.assertEqual(umbral.humedad, variedades.LimitesDelUmbral(d(60), d(80), min(a.pk, b.pk), min(a.pk, b.pk)))
        self.assertIsNotNone(umbral.intensidad_luz)
        self.assertIsNotNone(umbral.fotoperiodo)

    def test_api_varios_invernaderos_en_una_llamada_sin_una_consulta_por_invernadero(self):
        """docs/api/variedades.md: las consultas del registrante más una de ``rangos_de`` para todas las variedades de todos los invernaderos."""
        a, b, c = self.variedad("A"), self.variedad("B", temp_ambiente_min="19"), self.variedad("C")
        otro = crear_invernadero("Invernadero Oeste")
        presentes = {self.norte.pk: {a.pk, b.pk}, self.sur.pk: {c.pk}}
        with variedades_presentes_de_prueba(presentes), self.assertNumQueries(1):
            resultado = variedades.umbral_efectivo([self.norte.pk, self.sur.pk, otro.pk])
        self.assertEqual(resultado[self.norte.pk].variedad_ids, frozenset({a.pk, b.pk}))
        self.assertEqual(resultado[self.sur.pk].variedad_ids, frozenset({c.pk}))
        self.assertIsNone(resultado[otro.pk])

    def test_api_se_calcula_en_cada_llamada_con_los_rangos_vigentes(self):
        """docs/api/variedades.md: no se guarda; un cambio de rangos (PROD-MOD-VAR) rige desde la llamada siguiente."""
        a = self.variedad("A", temp_ambiente_min="18", temp_ambiente_max="24")
        with variedades_presentes_de_prueba({self.norte.pk: {a.pk}}):
            antes = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk].temp_ambiente.maximo
            a.temp_ambiente_max = d(30)
            a.save()
            despues = variedades.umbral_efectivo([self.norte.pk])[self.norte.pk].temp_ambiente.maximo
        self.assertEqual((antes, despues), (d(24), d(30)))


def umbral(**por_variable):
    """Un ``UmbralEfectivo`` armado a mano: ``(minimo, maximo, variedad_minimo_id, variedad_maximo_id)`` por variable o ``None``."""
    base = {variable: (20, 24, 1, 2) for variable in ("temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo")}
    base.update(por_variable)
    limites = {
        variable: None if datos is None else variedades.LimitesDelUmbral(d(datos[0]), d(datos[1]), datos[2], datos[3])
        for variable, datos in base.items()
    }
    return variedades.UmbralEfectivo(**limites, variedad_ids=frozenset({1, 2}))


def rangos(**por_variable):
    """``Rangos`` de una variedad candidata: por defecto 20-24 (cabe justo en el umbral de ``umbral()``)."""
    base = {variable: (20, 24) for variable in ("temp_ambiente", "humedad", "intensidad_luz", "fotoperiodo")}
    base.update(por_variable)
    return variedades.Rangos(**{v: variedades.RangoAmbiental(d(m), d(x)) for v, (m, x) in base.items()})


class VariablesIncompatiblesTests(SimpleTestCase):
    """``variables_incompatibles(umbral, rangos)``: función pura, sin consultas (regla de compatibilidad de PROD-PNF-SMB)."""

    def test_api_una_variedad_que_cabe_en_el_umbral_es_compatible(self):
        """docs/api/variedades.md: compatible si, al sumarla, ninguna intersección queda vacía."""
        self.assertEqual(variedades.variables_incompatibles(umbral(), rangos()), [])

    def test_api_un_umbral_none_acepta_cualquier_variedad(self):
        """docs/api/variedades.md: con ``umbral`` en ``None`` (invernadero sin variedades), la lista es vacía."""
        self.assertEqual(variedades.variables_incompatibles(None, rangos(temp_ambiente=(100, 200))), [])

    def test_api_incompatible_por_arriba_la_limitante_es_la_variedad_del_maximo(self):
        """docs/api/variedades.md: si el mínimo de ``rangos`` supera el máximo del umbral, la limitante es ``variedad_maximo_id``."""
        resultado = variedades.variables_incompatibles(umbral(), rangos(temp_ambiente=(25, 30)))
        self.assertEqual(resultado, [variedades.VariableIncompatible("temp_ambiente", 2)])

    def test_api_incompatible_por_abajo_la_limitante_es_la_variedad_del_minimo(self):
        """docs/api/variedades.md: en el caso contrario (el máximo de ``rangos`` queda bajo el mínimo del umbral), ``variedad_minimo_id``."""
        resultado = variedades.variables_incompatibles(umbral(), rangos(humedad=(5, 19)))
        self.assertEqual(resultado, [variedades.VariableIncompatible("humedad", 1)])

    def test_api_rangos_que_solo_se_tocan_con_el_umbral_son_compatibles(self):
        """docs/api/variedades.md y regla 5 de PROD-MOD-VAR: tocarse en un extremo no es vacío."""
        self.assertEqual(variedades.variables_incompatibles(umbral(), rangos(temp_ambiente=(24, 30), humedad=(10, 20))), [])

    def test_api_una_variable_del_umbral_ya_vacia_es_incompatible_sin_limitante(self):
        """docs/api/variedades.md: si esa variable del umbral ya es ``None`` (variedades incompatibles entre sí, por ejemplo tras
        «Guardar igual»), es incompatible, con ``variedad_limitante_id`` en ``None``."""
        resultado = variedades.variables_incompatibles(umbral(fotoperiodo=None), rangos())
        self.assertEqual(resultado, [variedades.VariableIncompatible("fotoperiodo", None)])

    def test_api_varias_variables_salen_en_el_orden_de_rangos(self):
        """docs/api/variedades.md: ``variable`` es el nombre del campo de ``Rangos``; las incompatibles salen en su orden."""
        resultado = variedades.variables_incompatibles(
            umbral(humedad=None), rangos(fotoperiodo=(30, 40), temp_ambiente=(30, 40))
        )
        self.assertEqual(
            [(r.variable, r.variedad_limitante_id) for r in resultado],
            [("temp_ambiente", 2), ("humedad", None), ("fotoperiodo", 2)],
        )
