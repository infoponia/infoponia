# Pruebas de `transiciones.repartir_proporcional` (PRD-02, paso 2): el reparto del resto mayor de PROD-CNC-TRN (paso 4 y extensión 13c).
# Es una función pura: no toca la base. Fuente: docs/casos_de_uso/produccion/transicion.md («Reparto proporcional»).

import random

from django.test import SimpleTestCase

from produccion.servicios.transiciones import repartir_proporcional


class RepartirProporcionalTests(SimpleTestCase):
    def test_regla_reparto_proporcional_la_cuota_entera_de_cada_sector(self):
        """«Reparto proporcional»: con cuotas exactas no hay resto: 90 de 60/40 son 54 y 36."""
        self.assertEqual(repartir_proporcional(50, [60, 40]), [30, 20])
        self.assertEqual(repartir_proporcional(90, [60, 40, 100]), [27, 18, 45])

    def test_regla_reparto_proporcional_resto_mayor(self):
        """Las unidades restantes van de a una a los de mayor parte decimal: 10 de 1/1/1 da 4,3,3 (empatan; gana el primero);
        7 de 5/3 da 4 y 3 (cuotas 4,375 y 2,625: la parte decimal mayor es la del segundo)."""
        self.assertEqual(repartir_proporcional(7, [5, 3]), [4, 3])
        self.assertEqual(repartir_proporcional(2, [1, 1, 1]), [1, 1, 0])

    def test_regla_reparto_proporcional_empate_gana_el_de_mas_agujeros_planificados(self):
        """Si hay empate de parte decimal, al sector con más agujeros planificados: 1 de 2/4/2... cuotas 0,25/0,5/0,25 → el de 4."""
        self.assertEqual(repartir_proporcional(1, [2, 4, 2]), [0, 1, 0])

    def test_regla_reparto_proporcional_empate_total_gana_el_primero_de_la_lista(self):
        """Si el empate sigue (mismo resto y mismos agujeros planificados), al primero de la lista."""
        self.assertEqual(repartir_proporcional(1, [5, 5]), [1, 0])
        self.assertEqual(repartir_proporcional(1, [5, 5, 5]), [1, 0, 0])

    def test_regla_reparto_proporcional_cantidad_en_cero_y_total_completo(self):
        """Cantidad cero: todo en cero. Cantidad igual o mayor que lo planificado: cada sector conserva lo suyo."""
        self.assertEqual(repartir_proporcional(0, [30, 20]), [0, 0])
        self.assertEqual(repartir_proporcional(50, [30, 20]), [30, 20])
        self.assertEqual(repartir_proporcional(80, [30, 20]), [30, 20])
        self.assertEqual(repartir_proporcional(5, []), [])

    def test_regla_reparto_proporcional_un_solo_sector_recibe_todo(self):
        """Un solo sector: recibe la cantidad (menor que lo planificado)."""
        self.assertEqual(repartir_proporcional(7, [10]), [7])

    def test_regla_reparto_proporcional_no_acepta_negativos(self):
        """Una cantidad o un planificado negativo es un error de uso (`ValueError`)."""
        with self.assertRaises(ValueError):
            repartir_proporcional(-1, [3, 2])
        with self.assertRaises(ValueError):
            repartir_proporcional(1, [3, -2])

    def test_propiedad_la_suma_da_exactamente_la_cantidad_y_nunca_se_pasa_de_lo_planificado(self):
        """Propiedad (semilla fija): para cualquier planificado y cualquier cantidad menor que su suma, el reparto suma exactamente
        la cantidad, no es negativo, no supera lo planificado en cada sector, y se aparta de la cuota exacta en menos de 1."""
        azar = random.Random(20261122)
        for _ in range(500):
            planificado = [azar.randint(1, 120) for _ in range(azar.randint(1, 6))]
            cantidad = azar.randint(0, sum(planificado))
            reparto = repartir_proporcional(cantidad, planificado)
            self.assertEqual(sum(reparto), cantidad, (cantidad, planificado, reparto))
            for parte, p in zip(reparto, planificado):
                self.assertTrue(0 <= parte <= p, (cantidad, planificado, reparto))
                self.assertLess(abs(parte - cantidad * p / sum(planificado)), 1, (cantidad, planificado, reparto))

    def test_propiedad_el_orden_de_los_sectores_solo_decide_los_empates(self):
        """El resultado de cada sector depende de su cuota: permutar la lista permuta el resultado salvo en los empates totales."""
        self.assertEqual(sorted(repartir_proporcional(37, [50, 30, 20])), sorted(repartir_proporcional(37, [20, 50, 30])))
