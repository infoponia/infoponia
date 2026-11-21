# Pruebas del comando ``proceso_diario`` (DIA-01, D-56): ``core/management/commands/proceso_diario.py``. Usan
# ``call_command`` con pasos falsos (``mock.patch.object`` sobre ``_PASOS_DIARIOS``) y no tocan la base de datos. El código
# de salida 1 se verifica con ``CommandError``: Django la convierte en ``exit(1)`` al correr ``manage.py``. Cada prueba arma
# sus propios datos.

import datetime
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from core import procesos
from core.procesos import PasoDiario, ResumenDePaso


def _correr(*args):
    """Corre el comando y devuelve lo que imprimió."""
    salida = StringIO()
    call_command("proceso_diario", *args, stdout=salida)
    return salida.getvalue()


def _paso(codigo, orden, funcion=None, nombre=None):
    """Un ``PasoDiario`` falso; por defecto su función devuelve ``ResumenDePaso(0, 0, 0)``."""
    return PasoDiario(codigo, nombre or f"Paso {codigo}", orden, funcion or (lambda hoy: ResumenDePaso(0, 0, 0)))


class ComandoProcesoDiarioTests(SimpleTestCase):
    """DIA-01 paso 2: opciones, salida y código de salida."""

    def test_d56_con_fecha_la_pasa_a_los_pasos_y_la_informa(self):
        """DIA-01 paso 2: ``--fecha`` simula ese día: llega a los pasos y se informa en la primera línea."""
        recibidas = []

        def f(hoy):
            recibidas.append(hoy)
            return ResumenDePaso(3, 1, 2)

        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("a", 10, f, "Paso A")]):
            salida = _correr("--fecha", "2026-12-15")
        self.assertEqual(recibidas, [datetime.date(2026, 12, 15)])
        lineas = salida.splitlines()
        self.assertEqual(lineas[0], "Proceso diario del 2026-12-15.")
        self.assertEqual(lineas[1], "Paso A: procesados 3 · creados 1 · resueltos 2")
        self.assertEqual(lineas[2], "Pasos correctos: 1 · fallidos: 0.")

    def test_d56_sin_fecha_usa_hoy_leido_una_sola_vez(self):
        """DIA-01 paso 2: sin ``--fecha``, usa ``timezone.localdate()``, una sola vez, y la informa."""
        recibidas = []

        def f(hoy):
            recibidas.append(hoy)
            return ResumenDePaso(0, 0, 0)

        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("a", 10, f)]), \
                mock.patch("core.management.commands.proceso_diario.timezone.localdate",
                           side_effect=[datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)]) as localdate:
            salida = _correr()
        self.assertEqual(localdate.call_count, 1)
        self.assertEqual(recibidas, [datetime.date(2026, 1, 1)])
        self.assertIn("Proceso diario del 2026-01-01.", salida)

    def test_d56_el_detalle_del_resumen_se_muestra_si_existe(self):
        """DIA-01 paso 2: el detalle opcional del resumen se agrega a la línea del paso."""
        paso = _paso("a", 10, lambda hoy: ResumenDePaso(1, 0, 0, "3 lotes vencen en 7 días"), "Paso A")
        with mock.patch.object(procesos, "_PASOS_DIARIOS", [paso]):
            salida = _correr("--fecha", "2026-12-15")
        self.assertIn("Paso A: procesados 1 · creados 0 · resueltos 0 · 3 lotes vencen en 7 días", salida)

    def test_d56_fecha_invalida_lanza_commanderror_sin_correr_nada(self):
        """DIA-01 paso 2: una fecha imposible o sin ceros da ``CommandError`` y no corre ningún paso."""
        llamados = []

        def f(hoy):
            llamados.append(hoy)
            return ResumenDePaso(0, 0, 0)

        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("a", 10, f)]):
            for texto in ("2026-13-01", "2026-1-5", "15/12/2026", "mañana", "2026-02-30"):
                with self.subTest(fecha=texto):
                    with self.assertRaises(CommandError) as contexto:
                        _correr("--fecha", texto)
                    self.assertIn(texto, str(contexto.exception))
        self.assertEqual(llamados, [])

    def test_d56_listar_muestra_los_pasos_en_orden_y_no_corre_nada(self):
        """DIA-01 paso 2: ``--listar`` muestra orden, código y nombre, en orden, y no corre ningún paso."""
        llamados = []

        def f(hoy):
            llamados.append(hoy)
            return ResumenDePaso(0, 0, 0)

        pasos = [_paso("b", 20, f, "Segundo"), _paso("a", 10, f, "Primero")]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            salida = _correr("--listar")
        self.assertEqual(salida.splitlines(), ["10 · a · Primero", "20 · b · Segundo"])
        self.assertEqual(llamados, [])

    def test_d56_listar_sin_pasos_dice_que_no_hay(self):
        """DIA-01 «Hecho cuando»: ``--listar`` sin pasos muestra «No hay pasos registrados.»"""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            self.assertEqual(_correr("--listar").strip(), "No hay pasos registrados.")

    def test_d56_solo_corre_unicamente_ese_paso(self):
        """DIA-01 paso 2: ``--solo`` corre un paso y deja los demás sin correr."""
        llamados = []

        def uno(codigo):
            def f(hoy):
                llamados.append(codigo)
                return ResumenDePaso(0, 0, 0)
            return f

        pasos = [_paso("a", 10, uno("a"), "Paso A"), _paso("b", 20, uno("b"), "Paso B")]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            salida = _correr("--solo", "b", "--fecha", "2026-12-15")
        self.assertEqual(llamados, ["b"])
        self.assertIn("Paso B:", salida)
        self.assertNotIn("Paso A:", salida)

    def test_d56_solo_con_codigo_inexistente_lanza_commanderror_con_los_validos(self):
        """DIA-01 paso 2: ``--solo`` con un código que no existe da ``CommandError`` con los códigos válidos."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("alfa", 10), _paso("beta", 20)]):
            with self.assertRaises(CommandError) as contexto:
                _correr("--solo", "zzz")
        self.assertIn("alfa", str(contexto.exception))
        self.assertIn("beta", str(contexto.exception))

    def test_d56_un_paso_que_falla_informa_y_sale_con_error_pero_los_demas_corren(self):
        """D-56 punto 5: el paso fallido se informa con «FALLÓ: …», los demás corren y el comando termina con
        ``CommandError`` (código de salida 1)."""
        def falla(hoy):
            raise ValueError("se rompió")

        pasos = [_paso("a", 10, nombre="Paso A"), _paso("b", 20, falla, "Paso B"), _paso("c", 30, nombre="Paso C")]
        salida = StringIO()
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos), \
                self.assertLogs("infoponia.proceso_diario", level="ERROR"):
            with self.assertRaises(CommandError) as contexto:
                call_command("proceso_diario", "--fecha", "2026-12-15", stdout=salida)
        texto = salida.getvalue()
        self.assertIn("Paso A: procesados 0", texto)
        self.assertIn("Paso B: FALLÓ: ValueError: se rompió", texto)
        self.assertIn("Paso C: procesados 0", texto)
        self.assertIn("Pasos correctos: 2 · fallidos: 1.", texto)
        self.assertIn("b", str(contexto.exception))

    def test_d56_sin_pasos_dice_que_no_hay_y_no_falla(self):
        """DIA-01 paso 2: sin pasos registrados, imprime «No hay pasos registrados.» y termina bien (código 0)."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            self.assertEqual(_correr().strip(), "No hay pasos registrados.")
