# Pruebas mínimas de lo que `comercial` registra en `produccion.extensiones` (COM-02, docs/api/extensiones_de_produccion.md, sección 5):
# con datos, neutro y sin consultas por fila. Se prueba con el registrante REAL, a través de la función pública de `produccion`.
# Las acciones y las entradas de `comercial` (puntos 3 y 4 de la API) las suma COM-04.

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    escenario_comercial,
    reserva,
    reserva_de_periodo,
    suministro,
    verificar_invariantes_de_reservas,
)
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

    def test_ext_detalle_con_un_periodo_de_suministro_devuelve_el_codigo_sum_y_la_fecha_del_periodo(self):
        """COM-03a: la cosecha de la reserva de un período devuelve el código visible del suministro (`SUM-0001`) y la fecha del período."""
        from datetime import timedelta

        from django.utils import timezone

        s = suministro(self.e)
        d = detalle_suministro(s, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=3)
        fecha = timezone.localdate() + timedelta(days=3)
        r = reserva_de_periodo(d, fecha, [(lote_maduro(self.e, 100), 30)])
        detalle_de_la_cosecha = extensiones.detalle_de_cosechas([r.cosecha_id])[r.cosecha_id]
        self.assertEqual(detalle_de_la_cosecha.contrato, s.codigo)
        self.assertEqual(detalle_de_la_cosecha.fecha_entrega, fecha)

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


class AccionesYEntradasDeComercialTests(ConDatosDeInventario, TestCase):
    """COM-04a (puntos 3 y 4 de la API, D-64 punto 11): `registrar_acciones_de_cosecha` y `registrar_entradas_de_comercial`, con el registrante REAL, y el
    grupo «Cosechas» del Inicio del Agrónomo: por rol, para una cosecha ya concretada, sin consultas por cosecha y nunca una URL a un 403."""

    def setUp(self):
        from comercial.tests.fabricas import cosecha_manual

        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 10)], dias=1)
        self.addCleanup(verificar_invariantes_de_reservas)

    def acciones(self, usuario, ids=None):
        return extensiones.acciones_de_cosechas(usuario, ids or [self.cosecha.pk])[self.cosecha.pk]

    def test_ext_acciones_por_rol(self):
        """Prueba mínima 1 del punto 3: el Capataz asignado concreta; el Agrónomo a cargo modifica y cancela; otro Capataz, otro Agrónomo, el Gerente y el
        Vendedor, nada."""
        from core.tests.fabricas import crear_gerente
        from maestros.tests.fabricas import crear_agronomo, crear_capataz_activo

        capataz = self.acciones(self.e.capataz)
        self.assertEqual((capataz.modificar, capataz.cancelar), (None, None))
        self.assertTrue(capataz.concretar.endswith(f"/comercial/cosechas/{self.cosecha.pk}/concretar/"))
        agronomo = self.acciones(self.e.agronomo)
        self.assertEqual(agronomo.concretar, None)
        self.assertTrue(agronomo.modificar.endswith("/modificar/") and agronomo.cancelar.endswith("/cancelar/"))
        for otro in (crear_capataz_activo(email="otro.capataz@infoponia.com"), crear_agronomo(email="otro.agro@infoponia.com"), crear_gerente(), self.e.vendedor):
            self.assertEqual(tuple(self.acciones(otro)), (None, None, None), otro.email)

    def test_ext_acciones_de_una_cosecha_resuelta_son_todas_none(self):
        """Prueba mínima 1: una cosecha concretada o cancelada no ofrece nada."""
        from produccion.models import OrdenTrabajo

        OrdenTrabajo.objects.filter(pk=self.cosecha.pk).update(estado_orden="cancelada", fecha_resolucion_orden=self.cosecha.fecha_creacion_orden, motivo_cancelacion="x")
        self.assertEqual(tuple(self.acciones(self.e.agronomo)), (None, None, None))
        self.assertEqual(tuple(self.acciones(self.e.capataz)), (None, None, None))

    def test_ext_acciones_neutro_y_sin_consultas_por_cosecha(self):
        """Pruebas mínimas 2 y 3: una lista vacía da `{}` sin consultar; con tres cosechas, las mismas consultas que con una."""
        from comercial.tests.fabricas import cosecha_manual

        with self.assertNumQueries(0):
            self.assertEqual(extensiones.acciones_de_cosechas(self.e.agronomo, []), {})
        una = consultas(lambda: extensiones.acciones_de_cosechas(self.e.agronomo, [self.cosecha.pk]))
        otras = [cosecha_manual(self.e, [(self.lote, 5)], dias=1).pk for _ in range(2)]
        self.assertEqual(una, consultas(lambda: extensiones.acciones_de_cosechas(self.e.agronomo, [self.cosecha.pk, *otras])))

    def test_ext_entradas_por_rol(self):
        """Punto 4: «Planificar cosecha» solo para el Agrónomo con un invernadero activo a su cargo; la merma en cámara es de COM-04b (`None`)."""
        from core.tests.fabricas import crear_gerente

        self.assertTrue(extensiones.entradas_de_comercial(self.e.agronomo).planificar_cosecha.endswith("/comercial/cosechas/planificar/"))
        for otro in (self.e.capataz, self.e.vendedor, crear_gerente()):
            self.assertEqual(tuple(extensiones.entradas_de_comercial(otro)), (None, None))
        self.assertIsNone(extensiones.entradas_de_comercial(self.e.agronomo).merma_en_camara)

    def test_regla_la_seccion_de_cosechas_del_inicio_cuenta_hoy_vencidas_y_sin_capataz(self):
        """`secCosecha`: solo para el Agrónomo; a realizar, de hoy, vencidas y de invernaderos sin Capataz activo."""
        from comercial.servicios.registrantes import seccion_de_cosechas
        from comercial.tests.fabricas import cosecha_manual
        from maestros.models import Invernadero
        from produccion.models import OrdenTrabajo

        hoy = cosecha_manual(self.e, [(self.lote, 5)], dias=0)
        vencida = cosecha_manual(self.e, [(self.lote, 5)], dias=-2)
        self.assertEqual(seccion_de_cosechas(self.e.capataz), None)
        datos = seccion_de_cosechas(self.e.agronomo).contexto["cosechas"]
        self.assertEqual((datos["a_realizar"], datos["hoy"], datos["vencidas"], datos["sin_capataz"]), (3, 1, 1, 0))
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(capataz=None)
        self.assertEqual(seccion_de_cosechas(self.e.agronomo).contexto["cosechas"]["sin_capataz"], 3)
        self.assertTrue(hoy and vencida and OrdenTrabajo)
