# Pruebas del registro de pasos del proceso diario (DIA-01, D-56): ``core/procesos.py``. Usan pasos falsos y reemplazan la
# lista de módulo ``_PASOS_DIARIOS`` con ``mock.patch.object``, así que no tocan la base de datos. Cada prueba arma sus
# propios datos.

import datetime
from unittest import mock

from django.test import SimpleTestCase

from core import procesos
from core.procesos import PasoDiario, ResumenDePaso


def _vacia(hoy):
    """Función de paso falsa: no hace nada y devuelve un resumen vacío."""
    return ResumenDePaso(0, 0, 0)


def _paso(codigo, orden, funcion=_vacia):
    """Un ``PasoDiario`` falso."""
    return PasoDiario(codigo, f"Paso {codigo}", orden, funcion)


class RegistrarPasoTests(SimpleTestCase):
    """``registrar_paso_diario``: idempotencia y conflictos (D-56 punto 2; DIA-01, paso 1)."""

    def test_d56_registrar_dos_veces_lo_mismo_no_duplica(self):
        """D-56 punto 2 y DIA-01 paso 1: ``ready()`` puede correr más de una vez; un registro idéntico no se duplica."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            self.assertEqual(len(procesos.pasos_diarios()), 1)

    def test_d56_registrar_devuelve_el_paso(self):
        """DIA-01 paso 1: el registro devuelve el ``PasoDiario`` guardado."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            paso = procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            self.assertEqual(paso, PasoDiario("uno", "Paso uno", 10, _vacia))

    def test_d56_mismo_codigo_con_otra_funcion_lanza_runtimeerror(self):
        """DIA-01 paso 1: el ``codigo`` repetido con otra función es un error."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            with self.assertRaises(RuntimeError):
                procesos.registrar_paso_diario("uno", "Paso uno", 10, lambda hoy: ResumenDePaso(1, 1, 1))

    def test_d56_mismo_orden_con_otro_paso_lanza_runtimeerror(self):
        """DIA-01 paso 1: el ``orden`` repetido con otro paso es un error."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            with self.assertRaises(RuntimeError):
                procesos.registrar_paso_diario("dos", "Paso dos", 10, _vacia)

    def test_d56_mismo_codigo_y_funcion_con_otro_nombre_u_orden_lanza_runtimeerror(self):
        """Decidido por el estudiante al aprobar el plan de DIA-01: solo un registro idéntico (código, nombre, orden y
        función) es idempotente; cualquier otra diferencia con el mismo código es un error."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            procesos.registrar_paso_diario("uno", "Paso uno", 10, _vacia)
            with self.assertRaises(RuntimeError):
                procesos.registrar_paso_diario("uno", "Otro nombre", 10, _vacia)
            with self.assertRaises(RuntimeError):
                procesos.registrar_paso_diario("uno", "Paso uno", 20, _vacia)
            self.assertEqual(len(procesos.pasos_diarios()), 1)


class PasosDiariosTests(SimpleTestCase):
    """``pasos_diarios``: orden de los pasos (D-56 punto 6)."""

    def test_d56_devuelve_los_pasos_ordenados_por_orden(self):
        """D-56 punto 6: los pasos salen por ``orden``, sin importar el orden en que se registraron."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("c", 30), _paso("a", 10), _paso("b", 20)]):
            self.assertEqual([p.codigo for p in procesos.pasos_diarios()], ["a", "b", "c"])

    def test_d56_sin_pasos_devuelve_lista_vacia(self):
        """DIA-01 paso 1: sin pasos registrados, la lista es vacía."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            self.assertEqual(procesos.pasos_diarios(), [])


class CorrerProcesoDiarioTests(SimpleTestCase):
    """``correr_proceso_diario``: orden, fecha, ``solo`` y paso que falla (D-56 puntos 2, 4 y 5)."""

    def test_d56_corre_los_pasos_en_orden(self):
        """D-56 punto 6: los pasos corren por ``orden`` y el resultado conserva ese orden."""
        llamados = []

        def uno(codigo):
            def f(hoy):
                llamados.append(codigo)
                return ResumenDePaso(1, 0, 0)
            return f

        pasos = [_paso("c", 30, uno("c")), _paso("a", 10, uno("a")), _paso("b", 20, uno("b"))]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            resultados = procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15))
        self.assertEqual(llamados, ["a", "b", "c"])
        self.assertEqual([paso.codigo for paso, _, _ in resultados], ["a", "b", "c"])

    def test_d56_devuelve_paso_resumen_y_sin_error(self):
        """DIA-01 paso 1: cada elemento es ``(paso, ResumenDePaso, None)`` cuando el paso sale bien."""
        resumen = ResumenDePaso(3, 1, 2, "detalle")
        with mock.patch.object(procesos, "_PASOS_DIARIOS", [_paso("a", 10, lambda hoy: resumen)]):
            [(paso, devuelto, error)] = procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15))
        self.assertEqual(paso.codigo, "a")
        self.assertEqual(devuelto, resumen)
        self.assertIsNone(error)

    def test_d56_hoy_llega_igual_a_todos_los_pasos(self):
        """D-56 punto 4: ``hoy`` se pasa tal cual a cada paso (así ``--fecha`` simula el paso del tiempo)."""
        recibidos = []

        def f(hoy):
            recibidos.append(hoy)
            return ResumenDePaso(0, 0, 0)

        pasos = [_paso("a", 10, f), _paso("b", 20, f)]
        fecha = datetime.date(2026, 12, 15)
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            procesos.correr_proceso_diario(hoy=fecha)
        self.assertEqual(recibidos, [fecha, fecha])

    def test_d56_hoy_por_defecto_es_localdate_leida_una_sola_vez(self):
        """DIA-01 paso 1: sin ``hoy``, vale ``timezone.localdate()``, leído una sola vez para todos los pasos."""
        recibidos = []

        def f(hoy):
            recibidos.append(hoy)
            return ResumenDePaso(0, 0, 0)

        pasos = [_paso("a", 10, f), _paso("b", 20, f)]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos), \
                mock.patch.object(procesos.timezone, "localdate",
                                  side_effect=[datetime.date(2026, 1, 1), datetime.date(2026, 1, 2)]) as localdate:
            procesos.correr_proceso_diario()
        self.assertEqual(localdate.call_count, 1)
        self.assertEqual(recibidos, [datetime.date(2026, 1, 1)] * 2)

    def test_d56_solo_corre_unicamente_ese_paso(self):
        """DIA-01 paso 1: ``solo`` es un código y corre solo ese paso."""
        llamados = []

        def uno(codigo):
            def f(hoy):
                llamados.append(codigo)
                return ResumenDePaso(0, 0, 0)
            return f

        pasos = [_paso("a", 10, uno("a")), _paso("b", 20, uno("b"))]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            resultados = procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15), solo="b")
        self.assertEqual(llamados, ["b"])
        self.assertEqual([paso.codigo for paso, _, _ in resultados], ["b"])

    def test_d56_solo_con_codigo_inexistente_lanza_valueerror_con_los_validos(self):
        """DIA-01 paso 1: un ``solo`` que no existe da ``ValueError`` con la lista de códigos válidos."""
        pasos = [_paso("alfa", 10), _paso("beta", 20)]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            with self.assertRaises(ValueError) as contexto:
                procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15), solo="zzz")
        self.assertIn("alfa", str(contexto.exception))
        self.assertIn("beta", str(contexto.exception))

    def test_d56_un_paso_que_falla_no_frena_a_los_siguientes_y_queda_informado(self):
        """D-56 punto 5: si un paso lanza una excepción, los demás siguen y el error queda en el resultado y en el log."""
        def falla(hoy):
            raise ValueError("se rompió")

        pasos = [_paso("a", 10), _paso("b", 20, falla), _paso("c", 30)]
        with mock.patch.object(procesos, "_PASOS_DIARIOS", pasos):
            with self.assertLogs("infoponia.proceso_diario", level="ERROR") as log:
                resultados = procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15))
        self.assertEqual([paso.codigo for paso, _, _ in resultados], ["a", "b", "c"])
        (_, resumen_a, error_a), (_, resumen_b, error_b), (_, resumen_c, error_c) = resultados
        self.assertIsNotNone(resumen_a)
        self.assertIsNone(error_a)
        self.assertIsNone(resumen_b)
        self.assertIsInstance(error_b, ValueError)
        self.assertIsNotNone(resumen_c)
        self.assertIsNone(error_c)
        salida = "\n".join(log.output)
        self.assertIn("b", salida)
        self.assertIn("se rompió", salida)

    def test_d56_sin_pasos_devuelve_lista_vacia(self):
        """DIA-01 paso 1: sin pasos registrados, correr el proceso devuelve una lista vacía."""
        with mock.patch.object(procesos, "_PASOS_DIARIOS", []):
            self.assertEqual(procesos.correr_proceso_diario(hoy=datetime.date(2026, 12, 15)), [])
