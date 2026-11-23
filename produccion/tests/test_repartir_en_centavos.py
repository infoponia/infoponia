# Pruebas de `costos.repartir_en_centavos` (PRD-03, paso 2): el reparto del costo de una aplicación entre los lotes de plantas del alcance,
# en centavos y con el método del resto mayor. Fuente: docs/patrones/costo_del_lote.md («Reparto del costo de una aplicación de insumos
# entre lotes») y D-51 punto 4. Es una función pura: no escribe ni consulta la base.

import random
from decimal import Decimal

from django.test import SimpleTestCase

from produccion.servicios.costos import repartir_en_centavos

D = Decimal


class RepartirEnCentavosTests(SimpleTestCase):
    def test_regla_ejemplo_1_reparto_exacto_60_y_40(self):
        """costo_del_lote.md, ejemplo 1: 100,00 entre 60 y 40 plantas da 60,00 y 40,00."""
        self.assertEqual(repartir_en_centavos(D("100.00"), {1: 60, 2: 40}), {1: D("60.00"), 2: D("40.00")})

    def test_regla_ejemplo_2_el_centavo_sobrante_va_al_de_menor_id_si_empatan_en_resto_y_plantas(self):
        """costo_del_lote.md, ejemplo 2: 100,00 entre tres lotes de 1 planta da 33,34 · 33,33 · 33,33 (el centavo, al lote de menor id)."""
        self.assertEqual(
            repartir_en_centavos(D("100.00"), {1: 1, 2: 1, 3: 1}), {1: D("33.34"), 2: D("33.33"), 3: D("33.33")}
        )

    def test_regla_ejemplo_3_el_centavo_sobrante_va_al_de_mayor_resto(self):
        """costo_del_lote.md, ejemplo 3: 10,00 entre 2 y 1 plantas da 6,67 (resto 0,666…) y 3,33; la suma es 10,00."""
        self.assertEqual(repartir_en_centavos(D("10.00"), {1: 2, 2: 1}), {1: D("6.67"), 2: D("3.33")})

    def test_regla_ejemplo_4_un_centavo_va_al_lote_de_mas_plantas_y_el_otro_recibe_cero(self):
        """costo_del_lote.md, ejemplo 4: 0,01 entre 5 y 3 plantas da 0,01 al de más plantas y 0,00 al otro (el servicio no crea la
        imputación de cero)."""
        self.assertEqual(repartir_en_centavos(D("0.01"), {1: 5, 2: 3}), {1: D("0.01"), 2: D("0.00")})

    def test_regla_ejemplo_5_un_solo_lote_recibe_todo(self):
        """costo_del_lote.md, ejemplo 5: 50,00 con un solo lote de 7 plantas le da los 50,00."""
        self.assertEqual(repartir_en_centavos(D("50.00"), {1: 7}), {1: D("50.00")})

    def test_regla_empate_de_resto_lo_desempata_el_lote_con_mas_plantas_y_despues_el_menor_id(self):
        """Patrón, punto 3: con el mismo resto, el centavo va al lote con más plantas (aunque tenga mayor id) y, si siguen empatados, al de
        menor id. 0,03 entre {1: 1, 2: 2, 3: 3}: restos 3/6 · 0 · 3/6 y sobra 1 centavo, que va al lote 3 (más plantas)."""
        self.assertEqual(repartir_en_centavos(D("0.03"), {1: 1, 2: 2, 3: 3}), {1: D("0.00"), 2: D("0.01"), 3: D("0.02")})
        # Empate total (resto y plantas): el centavo va al menor id aunque las claves lleguen al revés.
        self.assertEqual(repartir_en_centavos(D("0.01"), {7: 2, 3: 2}), {3: D("0.01"), 7: D("0.00")})

    def test_regla_lotes_sin_plantas_no_reciben_ni_figuran(self):
        """Los lotes con 0 plantas en el alcance no reciben nada (no entran en el reparto)."""
        self.assertEqual(repartir_en_centavos(D("9.00"), {1: 0, 2: 3, 3: 6}), {2: D("3.00"), 3: D("6.00")})

    def test_regla_sin_lotes_con_plantas_no_hay_reparto(self):
        """Patrón, punto 5: sin lotes con plantas en el alcance, no hay reparto (el consumo va a gasto)."""
        self.assertEqual(repartir_en_centavos(D("10.00"), {}), {})
        self.assertEqual(repartir_en_centavos(D("10.00"), {1: 0}), {})

    def test_regla_monto_cero_reparte_ceros(self):
        """Un consumo de 0,00 (insumo sin precio de referencia) reparte 0,00 a cada lote con plantas."""
        self.assertEqual(repartir_en_centavos(D("0.00"), {1: 4, 2: 1}), {1: D("0.00"), 2: D("0.00")})

    def test_regla_el_orden_de_entrada_no_cambia_el_resultado(self):
        """El resultado no depende del orden de las claves de entrada."""
        a = repartir_en_centavos(D("100.00"), {1: 1, 2: 1, 3: 1})
        b = repartir_en_centavos(D("100.00"), {3: 1, 1: 1, 2: 1})
        self.assertEqual(a, b)
        self.assertEqual(list(a), sorted(a))

    def test_regla_monto_negativo_o_plantas_negativas_son_un_error_de_uso(self):
        """Un monto o unas plantas negativas no tienen sentido: `ValueError` (error de quien llama, no de la persona)."""
        with self.assertRaises(ValueError):
            repartir_en_centavos(D("-1.00"), {1: 1})
        with self.assertRaises(ValueError):
            repartir_en_centavos(D("1.00"), {1: -1})

    def test_regla_propiedad_la_suma_es_exactamente_el_monto_sin_partes_negativas_ni_mas_de_un_centavo_extra(self):
        """Patrón, pruebas: con montos y plantas aleatorios (semilla fija) la suma da EXACTAMENTE el monto, ninguna parte es negativa y
        ningún lote recibe más de un centavo por encima de su parte entera."""
        azar = random.Random(20261123)
        for _ in range(500):
            monto = D(azar.randint(0, 5_000_000)) / 100
            lotes = {i + 1: azar.randint(0, 400) for i in range(azar.randint(1, 12))}
            reparto = repartir_en_centavos(monto, lotes)
            con_plantas = {i: p for i, p in lotes.items() if p > 0}
            self.assertEqual(set(reparto), set(con_plantas))
            if not con_plantas:
                continue
            self.assertEqual(sum(reparto.values()), monto)
            total = sum(con_plantas.values())
            for i, parte in reparto.items():
                self.assertGreaterEqual(parte, 0)
                entera = (int(monto * 100) * con_plantas[i]) // total
                self.assertIn(int(parte * 100) - entera, (0, 1))
