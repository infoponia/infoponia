# Pruebas del paso diario de orden 5 «Abrir ejercicio contable» (CON-02 paso 3; CON-ABR-EJE, «Cómo se aplica»; D-56 y D-84 punto 2). Desde CON-05 el
# comando `poner_en_marcha_contabilidad` se retiró (la puesta en marcha es CON-INI-EJE). Cada prueba arma sus propios datos.
import datetime
import io

from django.core.management import call_command
from django.test import TestCase

from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import ejercicio, ejercicio_abierto
from core import procesos

Estado = EjercicioContable.Estado
INICIO = datetime.date(2027, 1, 1)
DIA_SIGUIENTE = datetime.date(2028, 1, 1)


class PasoDiarioEjercicioTests(TestCase):
    """CON-ABR-EJE, «Paso diario»: `registrar_paso_diario("abrir_ejercicio", ..., 5, paso_abrir_ejercicio)` en `ContabilidadConfig.ready()`."""

    def test_regla_7_el_paso_esta_registrado_con_orden_5_antes_del_de_inventario(self):
        """Regla 7 de CON-ABR-EJE y D-56 punto 6: el paso se llama «abrir_ejercicio», es el orden 5 y corre antes del 10 de inventario."""
        pasos = procesos.pasos_diarios()
        paso = next(p for p in pasos if p.codigo == "abrir_ejercicio")

        self.assertEqual((paso.nombre, paso.orden), ("Abrir ejercicio contable", 5))
        self.assertIs(paso.funcion, ejercicios.paso_abrir_ejercicio)
        self.assertLess(pasos.index(paso), next(i for i, p in enumerate(pasos) if p.codigo == "revisar_vencimientos"))

    def test_regla_7_el_paso_es_el_primero_de_todos(self):
        """Regla 7 de CON-ABR-EJE: va primero en el proceso, antes de todo paso que pueda generar asientos."""
        self.assertEqual(procesos.pasos_diarios()[0].codigo, "abrir_ejercicio")

    def test_post_el_paso_abre_el_ejercicio_y_resume(self):
        """«Paso diario»: devuelve `ResumenDePaso(procesados=1 si el abierto existía, creados=nuevos, resueltos=cerrados solos)`."""
        ejercicio_abierto(INICIO)

        resumen = ejercicios.paso_abrir_ejercicio(DIA_SIGUIENTE)

        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 0))
        self.assertTrue(resumen.detalle)
        self.assertEqual(EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO).fecha_inicio_ejercicio, DIA_SIGUIENTE)

    def test_post_el_resumen_cuenta_el_que_se_cerro_solo(self):
        """«Paso diario»: `resueltos` es la cantidad de ejercicios cerrados solos."""
        ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        ejercicio_abierto(INICIO)

        resumen = ejercicios.paso_abrir_ejercicio(DIA_SIGUIENTE)

        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 1, 1))

    def test_post_sin_vencimiento_el_resumen_es_de_un_procesado_sin_cambios(self):
        """«Paso diario»: si el abierto no venció, `procesados=1` y no crea ni resuelve nada."""
        ejercicio_abierto(INICIO)

        resumen = ejercicios.paso_abrir_ejercicio(datetime.date(2027, 6, 1))

        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 0, 0))
        self.assertEqual(EjercicioContable.objects.count(), 1)

    def test_post_sin_ningun_ejercicio_dice_contabilidad_no_iniciada_y_no_crea_nada(self):
        """Regla 4 de CON-ABR-EJE y regla 11 de CON-INI-EJE (CON-05; antes, D-84 punto 3): sin ejercicio el paso 5 no crea el primero:
        `procesados=0`, nada creado ni resuelto y el detalle dice «contabilidad no iniciada» (ajuste del estudiante, 26/11/2026)."""
        resumen = ejercicios.paso_abrir_ejercicio(datetime.date(2027, 6, 1))

        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (0, 0, 0))
        self.assertEqual(resumen.detalle, "contabilidad no iniciada")
        self.assertFalse(EjercicioContable.objects.exists())

    def test_post_con_abierto_y_nada_que_abrir_el_detalle_sigue_siendo_sin_cambios(self):
        """«Paso diario»: con un ejercicio abierto que no venció no hay nada que abrir y el detalle sigue siendo «sin cambios»."""
        ejercicio_abierto(INICIO)

        resumen = ejercicios.paso_abrir_ejercicio(datetime.date(2027, 6, 1))

        self.assertEqual(resumen.detalle, "sin cambios")

    def test_d56_corre_con_el_proceso_diario_y_una_fecha_simulada(self):
        """D-56 punto 3: `correr_proceso_diario(hoy=..., solo="abrir_ejercicio")` lo corre con la fecha simulada."""
        ejercicio_abierto(INICIO)

        (paso, resumen, error), = procesos.correr_proceso_diario(hoy=DIA_SIGUIENTE, solo="abrir_ejercicio")

        self.assertEqual(paso.codigo, "abrir_ejercicio")
        self.assertIsNone(error)
        self.assertEqual(resumen.creados, 1)

    def test_d56_el_comando_proceso_diario_lo_corre_con_fecha(self):
        """D-56 punto 3: `proceso_diario --solo abrir_ejercicio --fecha ...` abre el ejercicio y lo informa."""
        ejercicio_abierto(INICIO)
        salida = io.StringIO()

        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2028-01-01", stdout=salida)

        self.assertIn("Abrir ejercicio contable", salida.getvalue())
        self.assertEqual(EjercicioContable.objects.count(), 2)
