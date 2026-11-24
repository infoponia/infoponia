# Pruebas del NÚCLEO de la cosecha (COM-04a, paso 1): `produccion/servicios/cosechas.py`: `cosechar_lote`, `concretar_orden` y
# `costo_unitario_de_cosecha`. No son casos de uso: los llama PROD-CNC-CSC (en `comercial`) con el lote ya bloqueado.
# Fuente: docs/api/produccion.md (sección 8), D-64 (puntos 2, 3 y 4), docs/patrones/costo_del_lote.md y PROD-CNC-CSC (postcondiciones a a e y g).
# `cosechas` se toma del módulo dentro de cada prueba: mientras no exista, falla cada prueba por separado.

from decimal import Decimal
from unittest import mock

from django.db import connections
from django.test import TestCase
from django.utils import timezone

from core.models import Notificacion, RegistroAuditoria
from inventario.tests.fabricas import ConDatosDeInventario, perezoso
from produccion.errores import ErrorDeProduccion
from produccion.models import Bitacora, Cosecha, Lote, MovimientoStock, OcupacionSector
from produccion.tests.fabricas import cosecha, invernadero_con_produccion, lote_maduro

cosechas = perezoso("produccion.servicios.cosechas")
HOY = timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def lote(self, cantidad=100, costo="100.00"):
        """Un lote en Maduración de `cantidad` plantas, todas ocupando agujeros del sector de Maduración."""
        return lote_maduro(self.e, cantidad, costo=costo)

    def sector(self):
        """El sector de Maduración del escenario."""
        return self.e.sectores["maduracion"]

    def cosechar(self, lote, plantas, orden=None, fecha=None, responsable=None):
        """Llama al núcleo con `plantas` cosechadas en el único sector del lote."""
        return cosechas.cosechar_lote(
            orden or cosecha(self.e), lote, {self.sector().pk: plantas}, fecha or HOY, responsable or self.e.capataz
        )


class CosecharLoteTests(Base):
    def test_post_c_baja_la_cantidad_y_el_costo_del_lote_y_devuelve_lo_cosechado(self):
        """PROD-CNC-CSC, postcondición c y D-64 punto 3: el costo por planta es el de ANTES de cosechar (100,00 ÷ 100 = 1,0000); el lote
        baja 60 plantas y 60,00 de costo."""
        lote = self.lote()
        r = self.cosechar(lote, 60)
        self.assertEqual((r.cantidad, r.costo_unitario, r.costo), (60, Decimal("1.0000"), Decimal("60.00")))
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.estado_lote), (40, Decimal("40.00"), "activo"))

    def test_post_c_el_costo_de_lo_cosechado_no_pierde_centavos(self):
        """Costo del lote (`costo_de_la_merma`): con 3 plantas y 10,00, una planta cuesta 3,33 (costo unitario 3,3333) y las tres, los 10,00
        enteros."""
        lote = self.lote(cantidad=3, costo="10.00")
        r = self.cosechar(lote, 1)
        self.assertEqual((r.costo_unitario, r.costo), (Decimal("3.3333"), Decimal("3.33")))
        self.assertEqual(Lote.objects.get(pk=lote.pk).costo_acumulado, Decimal("6.67"))
        r = self.cosechar(lote, 2, orden=cosecha(self.e, dias=1))
        self.assertEqual(r.costo, Decimal("6.67"))

    def test_post_d_baja_los_agujeros_ocupados_de_cada_ocupacion_vigente(self):
        """Postcondición d: en cada sector se liberan tantos agujeros como plantas se cosecharon ahí."""
        lote = self.lote()
        self.cosechar(lote, 60)
        self.assertEqual(OcupacionSector.objects.get(lote=lote, sector=self.sector()).cant_agujeros_ocupados, 40)

    def test_post_c_un_lote_que_llega_a_cero_queda_finalizado_con_costo_cero_y_conserva_sus_ocupaciones(self):
        """Postcondición c y «Fin del lote»: sin plantas, `finalizado` y costo 0; la ocupación queda en 0 y conserva su lote."""
        lote = self.lote()
        self.cosechar(lote, 100)
        lote.refresh_from_db()
        self.assertEqual((lote.cantidad_actual, lote.costo_acumulado, lote.estado_lote), (0, Decimal("0.00"), "finalizado"))
        ocupacion = OcupacionSector.objects.get(lote=lote, sector=self.sector())
        self.assertEqual(ocupacion.cant_agujeros_ocupados, 0)

    def test_post_g_crea_la_bitacora_de_cosecha_con_la_fecha_efectiva_y_el_responsable(self):
        """Postcondición g y D-64 punto 4: un registro `cosecha` con la cosecha, el lote, su etapa actual, el invernadero, los sectores, el
        responsable y la fecha efectiva (la hora es la actual)."""
        lote, orden = self.lote(), cosecha(self.e)
        ayer = HOY - timezone.timedelta(days=1)
        r = self.cosechar(lote, 60, orden=orden, fecha=ayer)
        registro = Bitacora.objects.get(pk=r.bitacora.pk)
        self.assertEqual(
            (registro.tipo_evento, registro.cosecha_id, registro.lote_id, registro.etapa_id, registro.invernadero_id, registro.responsable_id),
            ("cosecha", orden.pk, lote.pk, lote.etapa_id, self.e.invernadero.pk, self.e.capataz.pk),
        )
        self.assertEqual(registro.fecha_bitacora, ayer)
        self.assertEqual(list(registro.sectores.all()), [self.sector()])

    def test_post_e_crea_el_movimiento_salida_por_cosecha_con_el_costo_de_antes(self):
        """Postcondición e: `salida_por_cosecha` con la cantidad, el lote, la cosecha como origen y el costo por planta de antes; su fecha
        es la efectiva."""
        lote, orden = self.lote(), cosecha(self.e)
        ayer = HOY - timezone.timedelta(days=1)
        r = self.cosechar(lote, 60, orden=orden, fecha=ayer)
        m = MovimientoStock.objects.get(pk=r.movimiento.pk)
        self.assertEqual(
            (m.tipo_movimiento, m.cantidad, m.lote_id, m.partida_id, m.origen_id, m.costo_unitario),
            ("salida_por_cosecha", 60, lote.pk, None, orden.pk, Decimal("1.0000")),
        )
        self.assertEqual(timezone.localtime(m.fecha).date(), ayer)

    def test_regla_un_lote_que_rinde_cero_deja_su_bitacora_y_ningun_movimiento(self):
        """D-64 punto 4 (R152): un registro por cada lote de la orden, también el que rindió 0; sin plantas no hay movimiento de stock."""
        lote = self.lote()
        r = self.cosechar(lote, 0)
        self.assertEqual((r.cantidad, r.costo, r.movimiento), (0, Decimal("0.00"), None))
        self.assertTrue(Bitacora.objects.filter(pk=r.bitacora.pk, tipo_evento="cosecha").exists())
        self.assertFalse(MovimientoStock.objects.exists())
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 100)

    def test_ext_8a_un_sector_que_se_pasa_de_sus_agujeros_ocupados_se_rechaza(self):
        """Extensión 8a: `cosecha_supera_sector` con el sector, sin cambiar nada."""
        lote = self.lote()
        with self.assertRaises(ErrorDeProduccion) as rechazo:
            self.cosechar(lote, 101)
        self.assertEqual(rechazo.exception.codigo, "cosecha_supera_sector")
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 100)
        self.assertFalse(Bitacora.objects.filter(tipo_evento="cosecha").exists())

    def test_ext_8a_un_sector_donde_el_lote_no_ocupa_nada_se_rechaza(self):
        """Extensión 8a: un sector sin agujeros ocupados por el lote vale como 0 ocupados."""
        lote = self.lote()
        with self.assertRaises(ErrorDeProduccion) as rechazo:
            cosechas.cosechar_lote(cosecha(self.e), lote, {self.e.sectores["germinacion"].pk: 1}, HOY, self.e.capataz)
        self.assertEqual(rechazo.exception.codigo, "cosecha_supera_sector")

    def test_regla_sin_transaccion_lanza_runtime_error_y_no_cambia_nada(self):
        """Docs de la API, sección 8: corre en la transacción de quien llama; sin ella, `RuntimeError`."""
        lote, orden = self.lote(), cosecha(self.e)
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            self.cosechar(lote, 10, orden=orden)
        self.assertEqual(Lote.objects.get(pk=lote.pk).cantidad_actual, 100)

    def test_regla_no_audita_ni_notifica(self):
        """«No audita ni notifica: el caso de uso arma su único registro» (D-36, D-42)."""
        lote = self.lote()
        auditoria, avisos = RegistroAuditoria.objects.count(), Notificacion.objects.count()
        self.cosechar(lote, 10)
        self.assertEqual((RegistroAuditoria.objects.count(), Notificacion.objects.count()), (auditoria, avisos))


class ConcretarOrdenTests(Base):
    def test_post_a_pasa_la_cosecha_a_concretada_con_las_dos_fechas(self):
        """Postcondición a: `concretada`, `fecha_resolucion_orden` = hoy y `fecha_cosecha` = la efectiva."""
        orden = cosecha(self.e)
        ayer = HOY - timezone.timedelta(days=1)
        cosechas.concretar_orden(orden, ayer)
        orden = Cosecha.objects.get(pk=orden.pk)
        self.assertEqual((orden.estado_orden, orden.fecha_resolucion_orden, orden.fecha_cosecha), ("concretada", HOY, ayer))

    def test_ext_13b_una_orden_que_ya_no_esta_a_realizar_se_rechaza(self):
        """Extensión 13b: `orden_no_a_realizar` si ya se concretó o se canceló."""
        for estado in ("concretada", "cancelada"):
            with self.subTest(estado=estado), self.assertRaises(ErrorDeProduccion) as rechazo:
                cosechas.concretar_orden(cosecha(self.e, estado=estado), HOY)
            self.assertEqual(rechazo.exception.codigo, "orden_no_a_realizar")

    def test_regla_sin_transaccion_lanza_runtime_error(self):
        """Contrato de núcleo: sin transacción, `RuntimeError`."""
        orden = cosecha(self.e)
        with mock.patch.object(connections["default"], "in_atomic_block", False), self.assertRaises(RuntimeError):
            cosechas.concretar_orden(orden, HOY)
        self.assertEqual(Cosecha.objects.get(pk=orden.pk).estado_orden, "a_realizar")


class CostoUnitarioDeCosechaTests(Base):
    def test_regla_devuelve_el_costo_de_cada_salida_por_cosecha_en_una_consulta(self):
        """D-64 punto 3: el `costo_unitario` de cada «salida por cosecha» por `(cosecha, lote)`, en una sola consulta; un lote que rindió 0
        no tiene salida y no figura."""
        a, b, vacio = self.lote(100, "100.00"), self.lote(50, "150.00"), self.lote(10, "10.00")
        orden = cosecha(self.e)
        for lote, plantas in ((a, 10), (b, 5), (vacio, 0)):
            cosechas.cosechar_lote(orden, lote, {self.sector().pk: plantas}, HOY, self.e.capataz)
        with self.assertNumQueries(1):
            costos = cosechas.costo_unitario_de_cosecha([orden.pk], [a.pk, b.pk, vacio.pk])
        self.assertEqual(costos, {(orden.pk, a.pk): Decimal("1.0000"), (orden.pk, b.pk): Decimal("3.0000")})
