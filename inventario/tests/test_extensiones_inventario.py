# Pruebas de los puntos de extensión de `inventario` y de la lectura básica del stock (INV-01, paso 2). Fuente:
# docs/api/extensiones_de_inventario.md (contrato y «Prueba mínima de cada registrante»: devuelve lo esperado con datos,
# el neutro sin datos y no hace consultas por fila), docs/patrones/stock.md (sección 1) y docs/api/stock.md («Lectura»).

from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from inventario import extensiones
from inventario.extensiones import OrdenQueReserva
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, existencia, faltante, insumo, lote, reservas_de_prueba
from maestros.extensiones import Impedimento
from maestros.tests.fabricas import crear_invernadero


def orden(orden_id, dia):
    return OrdenQueReserva(orden_id, f"Siembra {orden_id}", Decimal("2"), date(2026, 12, dia), f"/ordenes/{orden_id}/")


class ExtensionesDeInventarioTests(ConDatosDeInventario, TestCase):
    """Los tres puntos de extensión y sus funciones de consulta."""

    def setUp(self):
        self.invernadero = crear_invernadero("Invernadero Uno")
        self.insumo = insumo("Detergente", unidad="l")
        self.existencia = existencia(self.insumo, self.invernadero)
        self.otra = existencia(insumo("Lavandina", unidad="l"), self.invernadero)

    # ---- sin registrantes: el resultado neutro ----

    def test_ext_neutro_reservado_de_sin_registrantes_da_cero_para_cada_id(self):
        """API de extensiones: sin registrantes, `reservado_de` da 0 para cada id."""
        with mock.patch.object(extensiones, "_RESERVAS", []):
            self.assertEqual(
                extensiones.reservado_de([self.existencia.pk, self.otra.pk]),
                {self.existencia.pk: Decimal("0"), self.otra.pk: Decimal("0")},
            )

    def test_ext_neutro_ordenes_que_reservan_sin_registrantes_da_listas_vacias(self):
        """API de extensiones: sin registrantes, `ordenes_que_reservan` da una lista vacía por id."""
        with mock.patch.object(extensiones, "_ORDENES_QUE_RESERVAN", []):
            self.assertEqual(extensiones.ordenes_que_reservan([self.existencia.pk]), {self.existencia.pk: []})

    def test_ext_neutro_impedimentos_sin_stock_ni_registrantes_no_hay(self):
        """API de extensiones: sin stock, reservas, tránsito ni registrantes, no hay impedimentos."""
        with reservas_de_prueba():
            self.assertEqual(extensiones.impedimentos_de_deshabilitacion(self.existencia), [])

    def test_ext_neutro_sin_ids_no_falla(self):
        """Una lista vacía de ids da diccionarios vacíos."""
        self.assertEqual(extensiones.reservado_de([]), {})
        self.assertEqual(extensiones.ordenes_que_reservan([]), {})

    # ---- con registrantes falsos: devuelve lo esperado ----

    def test_ext_reservado_de_devuelve_lo_que_informa_el_registrante(self):
        """API de extensiones: `reservado_de` devuelve lo reservado; lo que no figura es 0."""
        with reservas_de_prueba(reservado={self.existencia.pk: "5.5"}):
            reservado = extensiones.reservado_de([self.existencia.pk, self.otra.pk])
        self.assertEqual(reservado, {self.existencia.pk: Decimal("5.5"), self.otra.pk: Decimal("0")})

    def test_ext_reservado_de_suma_a_todos_los_registrantes_e_ignora_ids_ajenos(self):
        """API de extensiones: con dos registrantes se suman; un id que no se pidió no aparece."""

        def uno(ids):
            return {i: Decimal("2") for i in ids} | {999: Decimal("50")}

        def dos(ids):
            return {i: Decimal("3") for i in ids}

        with mock.patch.object(extensiones, "_RESERVAS", [uno, dos]):
            self.assertEqual(extensiones.reservado_de([self.existencia.pk]), {self.existencia.pk: Decimal("5")})

    def test_ext_ordenes_que_reservan_las_ordena_inventario_por_fecha_y_despues_por_id(self):
        """API de extensiones: las ordena `inventario` (fecha programada, después id de orden), vengan como vengan."""
        desordenadas = [orden(9, 10), orden(3, 20), orden(2, 10)]
        with reservas_de_prueba(ordenes={self.existencia.pk: desordenadas}):
            resultado = extensiones.ordenes_que_reservan([self.existencia.pk, self.otra.pk])
        self.assertEqual([o.orden_id for o in resultado[self.existencia.pk]], [2, 9, 3])
        self.assertEqual(resultado[self.otra.pk], [])

    def test_ext_impedimentos_juntos_stock_reservas_transito_y_registrantes(self):
        """API de extensiones: se juntan TODOS (no se queda con el primero): stock, reservas, tránsito y los de `compras`."""
        lote(self.existencia, 4)
        self.existencia.cant_transito_insumo = Decimal("3")
        self.existencia.save()
        de_compras = [
            Impedimento("orden_de_compra_aprobada", "Hay una orden de compra aprobada.", "Recibila o cerrala."),
            Impedimento("pedido_en_curso", "Hay un pedido en curso.", "Cerralo."),
        ]
        with reservas_de_prueba(reservado={self.existencia.pk: 2}, impedimentos={self.existencia.pk: de_compras}):
            codigos = [i.codigo for i in extensiones.impedimentos_de_deshabilitacion(self.existencia)]
        self.assertEqual(
            codigos,
            [
                "stock_distinto_de_cero",
                "reservas_activas",
                "cantidad_en_transito",
                "orden_de_compra_aprobada",
                "pedido_en_curso",
            ],
        )

    def test_ext_impedimento_de_stock_cuenta_tambien_el_stock_negativo(self):
        """Regla 3 de 8.4: el stock negativo (faltante sin lote) también impide; el texto lo dice y dice cómo resolverlo."""
        faltante(self.existencia, 2)
        impedimentos = extensiones.impedimentos_de_deshabilitacion(self.existencia)
        self.assertEqual([i.codigo for i in impedimentos], ["stock_distinto_de_cero"])
        self.assertIn("stock negativo", impedimentos[0].texto)
        self.assertIn("ajuste", impedimentos[0].como_resolver)

    def test_ext_impedimento_de_stock_nombra_la_cantidad_con_los_decimales_de_la_unidad(self):
        """Regla 5 de CMP-ALT-INS: la cantidad del texto lleva los decimales de la unidad del insumo (litros: 3)."""
        lote(self.existencia, "1.5")
        self.assertIn("1.500", extensiones.impedimentos_de_deshabilitacion(self.existencia)[0].texto)

    def test_ext_stock_cero_con_lote_agotado_no_es_impedimento(self):
        """Un lote en 0 se conserva pero no impide (stock actual 0)."""
        lote(self.existencia, 0, ingresada=3)
        self.assertEqual(extensiones.impedimentos_de_deshabilitacion(self.existencia), [])

    # ---- sin consultas por fila ----

    def test_ext_reservado_y_ordenes_no_hacen_consultas_por_fila(self):
        """API de extensiones: `reservado_de` y `ordenes_que_reservan` llaman una vez al registrante para toda la lista y no
        consultan la base por su cuenta."""
        ids = [existencia(insumo(f"I{n}", unidad="kg"), self.invernadero).pk for n in range(6)]
        llamadas = []

        def registrante(lista):
            llamadas.append(list(lista))
            return {i: Decimal("1") for i in lista}

        with mock.patch.object(extensiones, "_RESERVAS", [registrante]), mock.patch.object(
            extensiones, "_ORDENES_QUE_RESERVAN", [lambda lista: {i: [] for i in lista}]
        ):
            with self.assertNumQueries(0):
                extensiones.reservado_de(ids)
                extensiones.ordenes_que_reservan(ids)
        self.assertEqual(len(llamadas), 1)
        self.assertEqual(llamadas[0], ids)


class StockBasicoTests(ConDatosDeInventario, TestCase):
    """`hoy()` y `stock_actual_de` (docs/api/stock.md, «Lectura»; docs/patrones/stock.md, sección 1)."""

    def setUp(self):
        self.invernadero = crear_invernadero("Invernadero Uno")

    def test_regla_stock_1_hoy_es_la_fecha_local_del_sistema(self):
        """Sección 1: `hoy()` es `timezone.localdate()` (America/Argentina/Buenos_Aires), no `date.today()`."""
        self.assertEqual(stock.hoy(), timezone.localdate())

    def test_regla_8_23_stock_actual_suma_todos_los_lotes(self):
        """Regla 3 de 8.23: el stock actual es la suma de los lotes, y lo que no tiene lotes da 0."""
        con_stock = existencia(insumo("A", unidad="kg"), self.invernadero)
        vacia = existencia(insumo("B", unidad="kg"), self.invernadero)
        lote(con_stock, "2.5")
        lote(con_stock, "4")
        self.assertEqual(
            stock.stock_actual_de([con_stock.pk, vacia.pk]), {con_stock.pk: Decimal("6.5"), vacia.pk: Decimal("0")}
        )

    def test_regla_8_23_stock_actual_incluye_el_faltante_y_puede_ser_negativo(self):
        """Regla 3 de 8.23: incluye el faltante sin lote; el resultado puede ser negativo (regla 5 de 8.13)."""
        iin = existencia(insumo("A", unidad="kg"), self.invernadero)
        lote(iin, 1)
        faltante(iin, 3)
        self.assertEqual(stock.stock_actual_de([iin.pk])[iin.pk], Decimal("-2"))

    def test_regla_stock_1_stock_actual_hace_una_sola_consulta_para_toda_la_lista(self):
        """API de extensiones, prueba mínima: no hay consultas por fila."""
        ids = []
        for n in range(5):
            iin = existencia(insumo(f"I{n}", unidad="kg"), self.invernadero)
            lote(iin, n + 1)
            ids.append(iin.pk)
        with self.assertNumQueries(1):
            resultado = stock.stock_actual_de(ids)
        self.assertEqual([resultado[i] for i in ids], [Decimal(n + 1) for n in range(5)])
