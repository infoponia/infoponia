# Pruebas de las lecturas del libro de gestión (CON-02 paso 4; D-84 punto 8; docs/api/asientos.md, «Lectura»): saldos por cuenta (con arrastre de las
# cuentas patrimoniales), movimientos por cuenta con su saldo acumulado, resultado del período y total por cuenta en un período. Los asientos se
# arman directo en la base con `asiento_de_prueba`, para probar la lectura sin depender del servicio de escritura. Cada prueba arma sus datos.
import datetime
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import EjercicioContable
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import PlanDeCuentasMixin, asiento_de_prueba, ejercicio

Estado = EjercicioContable.Estado


def _d(texto):
    return Decimal(texto)


class LibroTests(PlanDeCuentasMixin, TestCase):
    """Datos comunes: 2026 cerrado con tres asientos y 2027 abierto con dos.

    2026: (1) Caja D 1000 / Capital Inicial H 1000; (2) Caja D 500 / Ventas H 500; (3) Gastos Generales D 200 / Caja H 200.
    2027: (1) Caja D 300 / Ventas H 300; (2) Gastos Generales D 50 / Caja H 50.
    """

    def setUp(self):
        self.e2026 = ejercicio(Estado.CERRADO, datetime.date(2026, 1, 1))
        self.e2027 = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))
        asiento_de_prueba(self.e2026, datetime.date(2026, 3, 1), [(cuentas.CAJA, DEBE, _d("1000.00")), (cuentas.CAPITAL_INICIAL, HABER, _d("1000.00"))])
        asiento_de_prueba(self.e2026, datetime.date(2026, 6, 1), [(cuentas.CAJA, DEBE, _d("500.00")), (cuentas.VENTAS, HABER, _d("500.00"))])
        asiento_de_prueba(self.e2026, datetime.date(2026, 7, 1), [(cuentas.GASTOS_GENERALES, DEBE, _d("200.00")), (cuentas.CAJA, HABER, _d("200.00"))])
        asiento_de_prueba(self.e2027, datetime.date(2027, 2, 1), [(cuentas.CAJA, DEBE, _d("300.00")), (cuentas.VENTAS, HABER, _d("300.00"))])
        asiento_de_prueba(self.e2027, datetime.date(2027, 3, 1), [(cuentas.GASTOS_GENERALES, DEBE, _d("50.00")), (cuentas.CAJA, HABER, _d("50.00"))])

    # saldo_por_cuenta ---------------------------------------------------------------------------------------------------------------------------------

    def test_d84_punto_8_el_saldo_incluye_las_19_cuentas_aunque_no_tengan_movimientos(self):
        """D-84 punto 8 y API: `saldo_por_cuenta` devuelve un `Saldo` por `codigo_cuenta`; una cuenta sin movimientos va en cero."""
        saldos = libro.saldo_por_cuenta(self.e2027.pk)

        self.assertEqual(set(saldos), set(cuentas.TODAS))
        self.assertEqual(saldos[cuentas.BANCO], libro.Saldo(_d("0.00"), _d("0.00"), _d("0.00"), _d("0.00"), False))

    def test_d84_punto_8_la_cuenta_patrimonial_arrastra_el_saldo_de_los_ejercicios_anteriores(self):
        """D-84 punto 8: las cuentas patrimoniales (activo, pasivo, patrimonio neto) arrastran lo acumulado de los ejercicios de inicio menor."""
        caja = libro.saldo_por_cuenta(self.e2027.pk)[cuentas.CAJA]

        self.assertEqual(caja.debe, _d("300.00"))
        self.assertEqual(caja.haber, _d("50.00"))
        self.assertEqual(caja.saldo_inicial, _d("1300.00"))  # 1000 + 500 - 200 del 2026
        self.assertEqual(caja.saldo, _d("1550.00"))  # 1300 + 300 - 50
        self.assertFalse(caja.contrario)

    def test_d84_punto_8_el_patrimonio_neto_acreedor_arrastra_su_saldo(self):
        """D-84 punto 8: Capital Inicial (patrimonio neto, saldo acreedor = Haber − Debe) se arrastra aunque no tenga movimientos en el ejercicio."""
        capital = libro.saldo_por_cuenta(self.e2027.pk)[cuentas.CAPITAL_INICIAL]

        self.assertEqual((capital.debe, capital.haber), (_d("0.00"), _d("0.00")))
        self.assertEqual((capital.saldo_inicial, capital.saldo), (_d("1000.00"), _d("1000.00")))

    def test_d84_punto_8_las_cuentas_de_resultado_empiezan_en_cero_cada_ejercicio(self):
        """D-84 punto 8: las cuentas de resultado no arrastran: solo cuenta el ejercicio elegido (resultado positivo acreedor, negativo deudor)."""
        saldos = libro.saldo_por_cuenta(self.e2027.pk)

        self.assertEqual((saldos[cuentas.VENTAS].saldo_inicial, saldos[cuentas.VENTAS].saldo), (_d("0.00"), _d("300.00")))
        self.assertEqual((saldos[cuentas.GASTOS_GENERALES].saldo_inicial, saldos[cuentas.GASTOS_GENERALES].saldo), (_d("0.00"), _d("50.00")))

    def test_d84_punto_8_el_primer_ejercicio_no_tiene_saldo_inicial(self):
        """D-84 punto 8: el ejercicio de menor fecha de inicio no arrastra nada; su saldo es solo el de sus movimientos."""
        saldos = libro.saldo_por_cuenta(self.e2026.pk)

        self.assertEqual(saldos[cuentas.CAJA], libro.Saldo(_d("1500.00"), _d("200.00"), _d("0.00"), _d("1300.00"), False))
        self.assertEqual(saldos[cuentas.VENTAS].saldo, _d("500.00"))
        self.assertEqual(saldos[cuentas.CAPITAL_INICIAL].saldo, _d("1000.00"))

    def test_d84_punto_8_un_saldo_contrario_a_su_naturaleza_se_marca(self):
        """H7 y D-84 punto 8: 5.1.06 (deudora) con más Haber que Debe queda con saldo negativo y `contrario=True`; no se toma el absoluto."""
        asiento_de_prueba(
            self.e2027,
            datetime.date(2027, 4, 1),
            [(cuentas.INSUMOS_EN_STOCK, DEBE, _d("40.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, _d("40.00"))],
        )

        diferencias = libro.saldo_por_cuenta(self.e2027.pk)[cuentas.DIFERENCIAS_DE_INVENTARIO]

        self.assertEqual(diferencias.saldo, _d("-40.00"))
        self.assertTrue(diferencias.contrario)

    def test_d84_punto_8_los_saldos_se_calculan_con_consultas_agregadas(self):
        """D-84 punto 8: se calcula con una consulta agregada, no una por cuenta; la cantidad de consultas no crece con las cuentas."""
        with CaptureQueriesContext(connection) as consultas:
            libro.saldo_por_cuenta(self.e2027.pk)

        self.assertLessEqual(len(consultas), 4)

    # movimientos_de_cuenta ---------------------------------------------------------------------------------------------------------------------------

    def test_api_movimientos_de_cuenta_trae_el_saldo_acumulado_desde_el_saldo_inicial(self):
        """API, «Lectura»: `movimientos_de_cuenta` devuelve los movimientos con su saldo acumulado; en una cuenta patrimonial parte del saldo inicial."""
        filas = libro.movimientos_de_cuenta(cuentas.CAJA, self.e2027.pk)

        self.assertEqual([(f.movimiento.tipo_movimiento, f.movimiento.importe_movimiento, f.saldo) for f in filas],
                         [("D", _d("300.00"), _d("1600.00")), ("H", _d("50.00"), _d("1550.00"))])

    def test_api_movimientos_de_cuenta_de_resultado_parte_de_cero(self):
        """API y D-84 punto 8: en una cuenta de resultado el saldo acumulado parte de cero en cada ejercicio."""
        filas = libro.movimientos_de_cuenta(cuentas.VENTAS, self.e2027.pk)

        self.assertEqual([f.saldo for f in filas], [_d("300.00")])

    def test_api_movimientos_de_cuenta_de_un_ejercicio_solo_trae_los_de_ese_ejercicio(self):
        """API: solo los movimientos del ejercicio pedido; el saldo acumulado del primero del 2026 parte de cero."""
        filas = libro.movimientos_de_cuenta(cuentas.CAJA, self.e2026.pk)

        self.assertEqual([f.saldo for f in filas], [_d("1000.00"), _d("1500.00"), _d("1300.00")])

    def test_api_movimientos_de_cuenta_se_ordenan_por_fecha_del_asiento_y_despues_por_numero(self):
        """H8 (el número indica orden de registro, no de fecha): la vista por cuenta ordena por fecha del asiento y desempata por número."""
        # El número 3 del 2027 tiene una fecha ANTERIOR a la de los números 1 y 2.
        asiento_de_prueba(self.e2027, datetime.date(2027, 1, 10), [(cuentas.CAJA, DEBE, _d("10.00")), (cuentas.VENTAS, HABER, _d("10.00"))])

        filas = libro.movimientos_de_cuenta(cuentas.CAJA, self.e2027.pk)

        self.assertEqual([f.movimiento.asiento.numero_asiento for f in filas], [3, 1, 2])
        self.assertEqual([f.saldo for f in filas], [_d("1310.00"), _d("1610.00"), _d("1560.00")])

    def test_api_movimientos_de_cuenta_no_hace_una_consulta_por_fila(self):
        """«Sin consultas por fila»: leer el asiento de cada movimiento no suma consultas (se trae junto)."""
        with CaptureQueriesContext(connection) as consultas:
            filas = libro.movimientos_de_cuenta(cuentas.CAJA, self.e2026.pk)
            numeros = [f.movimiento.asiento.numero_asiento for f in filas]

        self.assertEqual(numeros, [1, 2, 3])
        self.assertLessEqual(len(consultas), 4)

    def test_api_movimientos_de_una_cuenta_inexistente_lanza_cuenta_inexistente(self):
        """D-86 punto 3: un código que no existe lanza `ErrorContable` `cuenta_inexistente`."""
        with self.assertRaises(ErrorContable) as contexto:
            libro.movimientos_de_cuenta("9.9.99", self.e2027.pk)

        self.assertEqual(contexto.exception.codigo, "cuenta_inexistente")

    # resultado_del_periodo -----------------------------------------------------------------------------------------------------------------------------

    def test_api_resultado_del_periodo_cruza_dos_ejercicios_por_fecha_del_asiento(self):
        """API: `resultado_del_periodo` suma por FECHA DEL ASIENTO aunque el período cruce dos ejercicios (lo usa Estadísticas, EST-02)."""
        resultado = libro.resultado_del_periodo(datetime.date(2026, 6, 1), datetime.date(2027, 3, 31))

        self.assertEqual(resultado, libro.Resultado(ingresos=_d("800.00"), egresos=_d("250.00"), resultado=_d("550.00")))

    def test_api_resultado_del_periodo_incluye_los_dos_extremos_y_solo_cuentas_de_resultado(self):
        """API: `desde` y `hasta` son inclusivos; las cuentas patrimoniales (Caja, Capital Inicial) no cuentan."""
        un_dia = libro.resultado_del_periodo(datetime.date(2026, 6, 1), datetime.date(2026, 6, 1))
        antes_de_todo = libro.resultado_del_periodo(datetime.date(2026, 1, 1), datetime.date(2026, 2, 28))

        self.assertEqual(un_dia, libro.Resultado(_d("500.00"), _d("0.00"), _d("500.00")))
        self.assertEqual(antes_de_todo, libro.Resultado(_d("0.00"), _d("0.00"), _d("0.00")))

    def test_api_resultado_del_periodo_con_perdida_es_negativo(self):
        """API: `resultado = ingresos − egresos`; un período solo con gastos da un resultado negativo."""
        resultado = libro.resultado_del_periodo(datetime.date(2026, 7, 1), datetime.date(2026, 7, 31))

        self.assertEqual(resultado, libro.Resultado(_d("0.00"), _d("200.00"), _d("-200.00")))

    # total_por_cuenta_en_periodo ---------------------------------------------------------------------------------------------------------------------

    def test_api_total_de_una_cuenta_deudora_sin_tipo_es_debe_menos_haber(self):
        """Decisión de CON-02: con `tipo=None` es el saldo según la naturaleza de la cuenta; Caja (deudora) = Debe − Haber."""
        total = libro.total_por_cuenta_en_periodo(cuentas.CAJA, datetime.date(2026, 1, 1), datetime.date(2027, 12, 31))

        self.assertEqual(total, _d("1550.00"))  # 1800 − 250

    def test_api_total_de_una_cuenta_acreedora_sin_tipo_es_haber_menos_debe(self):
        """Decisión de CON-02: Ventas (acreedora) con `tipo=None` = Haber − Debe."""
        total = libro.total_por_cuenta_en_periodo(cuentas.VENTAS, datetime.date(2026, 1, 1), datetime.date(2027, 12, 31))

        self.assertEqual(total, _d("800.00"))

    def test_api_total_de_una_cuenta_con_saldo_contrario_es_negativo(self):
        """Decisión de CON-02: con saldo contrario a su naturaleza el resultado es negativo, con su signo (no el absoluto)."""
        asiento_de_prueba(
            self.e2027,
            datetime.date(2027, 4, 1),
            [(cuentas.INSUMOS_EN_STOCK, DEBE, _d("40.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, HABER, _d("40.00"))],
        )

        total = libro.total_por_cuenta_en_periodo(cuentas.DIFERENCIAS_DE_INVENTARIO, datetime.date(2027, 1, 1), datetime.date(2027, 12, 31))

        self.assertEqual(total, _d("-40.00"))

    def test_api_total_con_tipo_suma_solo_ese_lado(self):
        """Decisión de CON-02: con «D» o «H» la suma de los importes de ese lado."""
        desde, hasta = datetime.date(2026, 1, 1), datetime.date(2027, 12, 31)

        self.assertEqual(libro.total_por_cuenta_en_periodo(cuentas.CAJA, desde, hasta, tipo=DEBE), _d("1800.00"))
        self.assertEqual(libro.total_por_cuenta_en_periodo(cuentas.CAJA, desde, hasta, tipo=HABER), _d("250.00"))
        self.assertEqual(libro.total_por_cuenta_en_periodo(cuentas.VENTAS, desde, hasta, tipo=DEBE), _d("0.00"))
        self.assertEqual(libro.total_por_cuenta_en_periodo(cuentas.VENTAS, desde, hasta, tipo=HABER), _d("800.00"))

    def test_api_total_filtra_por_fecha_del_asiento_con_extremos_inclusivos(self):
        """API: «por fecha del asiento»; `desde` y `hasta` incluidos."""
        solo_2027 = libro.total_por_cuenta_en_periodo(cuentas.CAJA, datetime.date(2027, 1, 1), datetime.date(2027, 12, 31))
        un_dia = libro.total_por_cuenta_en_periodo(cuentas.CAJA, datetime.date(2027, 2, 1), datetime.date(2027, 2, 1))
        vacio = libro.total_por_cuenta_en_periodo(cuentas.CAJA, datetime.date(2028, 1, 1), datetime.date(2028, 12, 31))

        self.assertEqual((solo_2027, un_dia, vacio), (_d("250.00"), _d("300.00"), _d("0.00")))

    def test_api_total_con_un_tipo_invalido_lanza_tipo_de_movimiento_invalido(self):
        """Decisión de CON-02: cualquier `tipo` que no sea «D» o «H» lanza `ErrorContable` `tipo_de_movimiento_invalido`."""
        for tipo in ("X", "d", "Debe"):
            with self.subTest(tipo=tipo):
                with self.assertRaises(ErrorContable) as contexto:
                    libro.total_por_cuenta_en_periodo(cuentas.CAJA, datetime.date(2026, 1, 1), datetime.date(2027, 12, 31), tipo=tipo)
                self.assertEqual(contexto.exception.codigo, "tipo_de_movimiento_invalido")

    def test_api_total_de_una_cuenta_inexistente_lanza_cuenta_inexistente(self):
        """D-86 punto 3: un código que no existe lanza `ErrorContable` `cuenta_inexistente`."""
        with self.assertRaises(ErrorContable) as contexto:
            libro.total_por_cuenta_en_periodo("9.9.99", datetime.date(2026, 1, 1), datetime.date(2027, 12, 31))

        self.assertEqual(contexto.exception.codigo, "cuenta_inexistente")
