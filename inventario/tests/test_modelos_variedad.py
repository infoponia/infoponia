# Pruebas de las restricciones de la base de `Variedad` (INV-03, paso 1): una por restricción, con el caso que la viola y el que no.
# Fuente: docs/modelo/maestros.md («Variedad», «Restricciones de la base que agrega INV-03»), reglas 2, 6 y 7 de PROD-ALT-VAR y D-49.
# Las restricciones de dominio del estado y del perfil ya las creó MAE-03; acá se prueban junto con las nuevas.

from django.db import IntegrityError, transaction
from django.test import TestCase

from maestros.models import Variedad
from maestros.tests.fabricas import ConDatosDeMaestros, crear_cultivo, crear_variedad


class VariedadRestriccionesTests(ConDatosDeMaestros, TestCase):
    """Cada restricción de la base de ``Variedad``. ``viola`` exige que la base rechace sin romper la transacción de la prueba."""

    def viola(self, operacion):
        with self.assertRaises(IntegrityError), transaction.atomic():
            operacion()

    def setUp(self):
        self.cultivo = crear_cultivo("Lechuga")

    # ---- regla 2 de PROD-ALT-VAR: nombre único por cultivo ----

    def test_regla_alt_var_2_nombre_repetido_con_otras_mayusculas_viola(self):
        """PROD-ALT-VAR regla 2: el mismo nombre con otras mayúsculas, en el mismo cultivo, lo rechaza la base."""
        crear_variedad(self.cultivo, "Crespa")
        self.viola(lambda: crear_variedad(self.cultivo, "cRESPA"))

    def test_regla_alt_var_2_espacios_al_borde_los_recorta_el_servicio_no_la_base(self):
        """PROD-ALT-VAR regla 2: «sin espacios al principio o al final» lo hace el servicio al recortar (la restricción de la base
        solo mira ``lower(nombre)``): la base no recorta, por eso el alta guarda siempre el nombre ya recortado."""
        crear_variedad(self.cultivo, "Crespa")
        self.assertIsNotNone(crear_variedad(self.cultivo, "Crespa ").pk)

    def test_regla_alt_var_2_mismo_nombre_en_otro_cultivo_no_viola(self):
        """PROD-ALT-VAR regla 2: dos cultivos pueden tener variedades con el mismo nombre."""
        crear_variedad(self.cultivo, "Crespa")
        self.assertIsNotNone(crear_variedad(crear_cultivo("Acelga"), "Crespa").pk)

    def test_regla_alt_var_2_la_baja_no_libera_el_nombre(self):
        """PROD-ALT-VAR regla 2: «se cuentan también las variedades dadas de baja»: una inactiva sigue ocupando su nombre."""
        crear_variedad(self.cultivo, "Crespa", activa=False)
        self.viola(lambda: crear_variedad(self.cultivo, "crespa"))

    # ---- regla 6: mínimo <= máximo en los cuatro rangos ----

    def test_regla_alt_var_6_minimo_mayor_que_maximo_viola_en_cada_rango(self):
        """PROD-ALT-VAR regla 6: el mínimo no puede ser mayor que el máximo, en ninguno de los cuatro rangos."""
        rangos = {
            "temp_ambiente": ("30", "20"),
            "humedad": ("90", "80"),
            "intensidad_luz": ("500", "400"),
            "fotoperiodo": ("18", "16"),
        }
        for numero, (nombre, (minimo, maximo)) in enumerate(rangos.items()):
            with self.subTest(rango=nombre):
                columnas = {f"{nombre}_min": minimo, f"{nombre}_max": maximo}
                self.viola(lambda c=columnas, n=numero: crear_variedad(self.cultivo, f"V{n}", **c))

    def test_regla_alt_var_6_minimo_igual_al_maximo_no_viola(self):
        """PROD-ALT-VAR regla 6: mínimo igual al máximo es válido."""
        variedad = crear_variedad(self.cultivo, temp_ambiente_min="20", temp_ambiente_max="20")
        self.assertEqual(variedad.temp_ambiente_min, variedad.temp_ambiente_max)

    # ---- topes aprobados el 19/11/2026 (D-49) ----

    def test_d49_humedad_fuera_de_0_a_100_viola(self):
        """D-49: la humedad va de 0 a 100: −1 en el mínimo y 100,01 en el máximo violan."""
        self.viola(lambda: crear_variedad(self.cultivo, "A", humedad_min="-1", humedad_max="50"))
        self.viola(lambda: crear_variedad(self.cultivo, "B", humedad_min="50", humedad_max="100.01"))

    def test_d49_humedad_de_0_a_100_no_viola(self):
        """D-49: 0 y 100 son valores válidos de humedad."""
        self.assertIsNotNone(crear_variedad(self.cultivo, humedad_min="0", humedad_max="100").pk)

    def test_d49_fotoperiodo_fuera_de_0_a_24_viola(self):
        """D-49: el fotoperíodo va de 0 a 24: −1 en el mínimo y 24,01 en el máximo violan."""
        self.viola(lambda: crear_variedad(self.cultivo, "A", fotoperiodo_min="-1", fotoperiodo_max="10"))
        self.viola(lambda: crear_variedad(self.cultivo, "B", fotoperiodo_min="10", fotoperiodo_max="24.01"))

    def test_d49_fotoperiodo_de_0_a_24_no_viola(self):
        """D-49: 0 y 24 son valores válidos de fotoperíodo."""
        self.assertIsNotNone(crear_variedad(self.cultivo, fotoperiodo_min="0", fotoperiodo_max="24").pk)

    def test_d49_temperatura_e_intensidad_no_tienen_tope(self):
        """D-49: temperatura e intensidad lumínica no tienen tope (admiten negativos y valores grandes)."""
        variedad = crear_variedad(
            self.cultivo, temp_ambiente_min="-10", temp_ambiente_max="999", intensidad_luz_min="0", intensidad_luz_max="9999"
        )
        self.assertIsNotNone(variedad.pk)

    # ---- regla 7: postcosecha y peso ----

    def test_regla_alt_var_7_postcosecha_fuera_de_1_a_60_viola(self):
        """PROD-ALT-VAR regla 7: la postcosecha es un entero de 1 a 60: 0 y 61 violan."""
        self.viola(lambda: crear_variedad(self.cultivo, "A", duracion_post_cosecha=0))
        self.viola(lambda: crear_variedad(self.cultivo, "B", duracion_post_cosecha=61))

    def test_regla_alt_var_7_postcosecha_1_y_60_no_viola(self):
        """PROD-ALT-VAR regla 7: 1 y 60 son valores válidos."""
        self.assertIsNotNone(crear_variedad(self.cultivo, "A", duracion_post_cosecha=1).pk)
        self.assertIsNotNone(crear_variedad(self.cultivo, "B", duracion_post_cosecha=60).pk)

    def test_regla_alt_var_7_peso_cero_viola_y_uno_no(self):
        """PROD-ALT-VAR regla 7: el peso en gramos es mayor que cero: 0 viola, 1 no."""
        self.viola(lambda: crear_variedad(self.cultivo, "A", peso_promedio_planta=0))
        self.assertIsNotNone(crear_variedad(self.cultivo, "B", peso_promedio_planta=1).pk)

    # ---- dominios (MAE-03) ----

    def test_dominio_del_estado_y_del_perfil_viola(self):
        """docs/modelo/maestros.md: ``estado_variedad`` y ``perfil_familia`` solo admiten sus valores."""
        self.viola(lambda: Variedad.objects.filter(pk=crear_variedad(self.cultivo, "A").pk).update(estado_variedad="otro"))
        self.viola(lambda: crear_variedad(self.cultivo, "B", perfil="verdura"))
