# Pruebas del paso diario de orden 5 «Abrir ejercicio contable» y del comando `poner_en_marcha_contabilidad` (CON-02 paso 3; CON-ABR-EJE,
# «Cómo se aplica»; D-56 y D-84 puntos 2 y 3). Cada prueba arma sus propios datos.
import datetime
import io
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import TestCase

from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import ejercicio, ejercicio_abierto
from core import procesos
from core.models import RegistroAuditoria

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

    def test_post_sin_ningun_ejercicio_crea_el_primero(self):
        """«Paso diario» y D-84 punto 3: si no había abierto, `procesados=0` y el primero cuenta como creado."""
        resumen = ejercicios.paso_abrir_ejercicio(datetime.date(2027, 6, 1))

        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (0, 1, 0))

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


class PonerEnMarchaContabilidadTests(TestCase):
    """CON-ABR-EJE, «Comando»: `poner_en_marcha_contabilidad [--fecha-inicio AAAA-MM-DD]` (D-84 punto 3)."""

    HOY = datetime.date(2027, 5, 20)

    def _correr(self, *argumentos):
        salida = io.StringIO()
        with mock.patch("django.utils.timezone.localdate", return_value=self.HOY):
            call_command("poner_en_marcha_contabilidad", *argumentos, stdout=salida)
        return salida.getvalue()

    def test_d84_sin_fecha_crea_el_primer_ejercicio_que_empieza_hoy(self):
        """D-84 punto 3: sin `--fecha-inicio`, el primer ejercicio empieza hoy."""
        salida = self._correr()

        primero = EjercicioContable.objects.get()
        self.assertEqual((primero.fecha_inicio_ejercicio, primero.fecha_cierre_ejercicio), (self.HOY, datetime.date(2028, 5, 19)))
        self.assertEqual(primero.estado_ejercicio, Estado.ABIERTO)
        self.assertIn("20/05/2027", salida)
        self.assertIn("19/05/2028", salida)

    def test_d84_con_fecha_inicio_empieza_ese_dia(self):
        """D-84 punto 3: `--fecha-inicio` permite que el primer ejercicio empiece antes (para fechar el asiento de apertura)."""
        self._correr("--fecha-inicio", "2027-01-15")

        primero = EjercicioContable.objects.get()
        self.assertEqual((primero.fecha_inicio_ejercicio, primero.fecha_cierre_ejercicio), (datetime.date(2027, 1, 15), datetime.date(2028, 1, 14)))

    def test_d84_es_idempotente_y_lo_dice(self):
        """D-84 punto 3: si ya hay un ejercicio, no hace nada y lo dice."""
        self._correr("--fecha-inicio", "2027-01-15")
        auditoria = RegistroAuditoria.objects.count()

        salida = self._correr("--fecha-inicio", "2026-01-01")

        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertEqual(EjercicioContable.objects.get().fecha_inicio_ejercicio, datetime.date(2027, 1, 15))
        self.assertEqual(RegistroAuditoria.objects.count(), auditoria)
        self.assertIn("Ya existe un ejercicio contable", salida)

    def test_d84_rechaza_una_fecha_futura(self):
        """Cómo se aplica, comando: la fecha de inicio no puede ser futura; no se crea nada."""
        with self.assertRaises(CommandError) as contexto:
            self._correr("--fecha-inicio", "2027-05-21")

        self.assertIn("futura", str(contexto.exception))
        self.assertFalse(EjercicioContable.objects.exists())

    def test_d84_rechaza_una_fecha_con_formato_invalido(self):
        """Mismo criterio que `proceso_diario`: una fecha imposible o sin ceros se rechaza con un mensaje claro."""
        for texto in ("2027-13-01", "2027-1-5", "mañana"):
            with self.assertRaises(CommandError) as contexto:
                self._correr("--fecha-inicio", texto)
            self.assertIn("AAAA-MM-DD", str(contexto.exception))
        self.assertFalse(EjercicioContable.objects.exists())
