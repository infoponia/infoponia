# Pruebas mínimas de lo que `comercial` registra en `produccion.extensiones` (COM-02, docs/api/extensiones_de_produccion.md, sección 5):
# con datos, neutro y sin consultas por fila. Se prueba con el registrante REAL, a través de la función pública de `produccion`.
# Las acciones y las entradas de `comercial` (puntos 3 y 4 de la API) las suma COM-04.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from comercial.tests.fabricas import compra_venta, detalle, escenario_comercial, reserva, verificar_invariantes_de_reservas
from inventario.tests.fabricas import ConDatosDeInventario
from produccion import extensiones
from produccion.tests.fabricas import cosecha, lote_maduro


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class ExtensionesDeProduccionTests(ConDatosDeInventario, TestCase):
    """Los dos registrantes de `comercial`: `registrar_reservado_de_lote` y `registrar_detalle_de_cosecha`."""

    def setUp(self):
        self.e = escenario_comercial()
        self.venta = compra_venta(self.e, dias=3)
        self.detalle = detalle(self.venta, self.e.variedad, cantidad=100)
        self.addCleanup(verificar_invariantes_de_reservas)

    def test_ext_reservado_con_datos_suma_las_activas_y_no_las_liberadas(self):
        """Prueba mínima 1 del punto 1: un lote con dos reservas activas y una liberada devuelve la suma de las activas."""
        lote = lote_maduro(self.e, 100)
        reserva(self.detalle, [(lote, 10)])
        reserva(self.detalle, [(lote, 5)])
        reserva(self.detalle, [(lote, 7)], estado="liberada")
        self.assertEqual(extensiones.reservado_de_lotes([lote.pk]), {lote.pk: 15})

    def test_ext_reservado_neutro_un_lote_sin_reservas_da_cero_y_una_lista_vacia_no_consulta(self):
        """Prueba mínima 2 del punto 1: un lote sin reservas da 0; una lista vacía da `{}` sin consultar la base."""
        lote = lote_maduro(self.e, 100)
        self.assertEqual(extensiones.reservado_de_lotes([lote.pk]), {lote.pk: 0})
        with self.assertNumQueries(0):
            self.assertEqual(extensiones.reservado_de_lotes([]), {})

    def test_ext_reservado_sin_consultas_por_fila(self):
        """Prueba mínima 3 del punto 1: con tres lotes, la misma cantidad de consultas que con uno."""
        lotes = [lote_maduro(self.e, 100) for _ in range(3)]
        self.assertEqual(
            consultas(lambda: extensiones.reservado_de_lotes([lotes[0].pk])),
            consultas(lambda: extensiones.reservado_de_lotes([l.pk for l in lotes])),
        )

    def test_ext_detalle_con_datos_devuelve_contrato_fecha_y_lotes_en_orden_de_id(self):
        """Prueba mínima 1 del punto 2: una cosecha devuelve su contrato (`CV-0001`), su fecha de entrega y sus lotes
        `(lote_id, reservada, cosechada)` en orden de id de lote."""
        a, b = lote_maduro(self.e, 100), lote_maduro(self.e, 100)
        r = reserva(self.detalle, [(b, 7), (a, 12)])
        detalle_de_la_cosecha = extensiones.detalle_de_cosechas([r.cosecha_id])[r.cosecha_id]
        self.assertEqual(detalle_de_la_cosecha.contrato, self.venta.codigo)
        self.assertEqual(detalle_de_la_cosecha.fecha_entrega, self.venta.fecha_pactada_venta)
        self.assertEqual(detalle_de_la_cosecha.lotes, [(a.pk, 12, None), (b.pk, 7, None)])

    def test_ext_detalle_neutro_una_cosecha_sin_reserva_no_tiene_contrato_y_una_lista_vacia_no_consulta(self):
        """Prueba mínima 2 del punto 2: una cosecha sin reserva figura sin contrato ni lotes; una lista vacía da `{}` sin consultar."""
        suelta = cosecha(self.e)
        self.assertEqual(tuple(extensiones.detalle_de_cosechas([suelta.pk])[suelta.pk]), (None, None, []))
        with self.assertNumQueries(0):
            self.assertEqual(extensiones.detalle_de_cosechas([]), {})
        suelta.delete()  # una cosecha sin reserva rompe a propósito un invariante del patrón: no la dejamos

    def test_ext_detalle_sin_consultas_por_fila(self):
        """Prueba mínima 3 del punto 2: con tres cosechas, la misma cantidad de consultas que con una."""
        reservas = [reserva(self.detalle, [(lote_maduro(self.e, 100), 5)]) for _ in range(3)]
        con_una = consultas(lambda: extensiones.detalle_de_cosechas([reservas[0].cosecha_id]))
        con_tres = consultas(lambda: extensiones.detalle_de_cosechas([r.cosecha_id for r in reservas]))
        self.assertEqual(con_una, con_tres)

    def test_ext_los_dos_registrantes_son_los_de_comercial(self):
        """`ComercialConfig.ready()` registra los dos puntos (un solo registrante por punto, sin duplicar si `ready()` corre dos veces)."""
        from comercial.servicios import stock_maduro

        self.assertEqual(extensiones._RESERVADO_DE_LOTE, [stock_maduro.reservado_de_lotes])
        self.assertEqual(extensiones._DETALLE_DE_COSECHA, [stock_maduro.detalle_de_cosechas])
