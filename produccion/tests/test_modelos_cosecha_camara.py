# Pruebas de los modelos que COM-04a suma a `produccion` (paso 1): `MovimientoStock`, `Bitacora.cosecha`, los tipos de bitácora nuevos,
# las causas nuevas de `Merma`, `Merma.orden`, `Consumo.orden` y `Cosecha.origen_cosecha`. Una prueba por restricción.
# Fuente: docs/modelo/produccion.md («MovimientoStock», «Bitacora», «Merma», «Consumo», «Cosecha»), docs/api/produccion.md (secciones 8, 10 y 11),
# D-64 (puntos 1, 4 y 5), D-68 punto 3 y D-69 punto 3.

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Bitacora, Consumo, Cosecha, Merma, MovimientoStock, StockCosechado
from produccion.tests.fabricas import cosecha, insumo_adicional, invernadero_con_produccion, lote_maduro, orden_suelta


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.lote = lote_maduro(cls.e, 50)
        cls.cosecha = cosecha(cls.e)
        cls.partida = StockCosechado.objects.create(
            lote=cls.lote, cantidad_ingreso_cosechado=10, cantidad_disponible_cosechado=10, fecha_ingreso=timezone.localdate(),
            fecha_limite=timezone.localdate(), motivo_cosechado="excedente_de_cosecha", costo_unitario_cosechado=Decimal("2.0000"),
        )

    def movimiento(self, **campos):
        """Un `MovimientoStock` válido de «salida por cosecha» del lote, con los `campos` que se quieran pisar."""
        valores = dict(
            origen=self.cosecha, lote=self.lote, tipo_movimiento="salida_por_cosecha", cantidad=5, costo_unitario=Decimal("2.0000")
        )
        valores.update(campos)
        return MovimientoStock.objects.create(**valores)

    def bitacora(self, tipo, **campos):
        """Un registro de bitácora con lo mínimo, del invernadero, de `tipo` y con los `campos` pisados."""
        valores = dict(
            invernadero=self.e.invernadero, tipo_evento=tipo, fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(), responsable=self.e.agronomo,
        )
        valores.update(campos)
        return Bitacora.objects.create(**valores)


class MovimientoStockTests(Base):
    """D-64 punto 1 y `docs/modelo/produccion.md`, «MovimientoStock»."""

    def test_regla_movimiento_es_un_documento_de_origen_de_tipo_movimiento_de_stock(self):
        """D-64 punto 1: hija directa de `OrigenDocumento` con `TIPO_DE_ORIGEN = movimiento_de_stock` (como `MovimientoInsumo`, D-52)."""
        m = self.movimiento()
        self.assertEqual(m.tipo, OrigenDocumento.Tipo.MOVIMIENTO_DE_STOCK)
        self.assertEqual(OrigenDocumento.objects.get(pk=m.pk).tipo, "movimiento_de_stock")
        self.assertEqual(self.cosecha.movimientos_de_stock.get().pk, m.pk)  # R017: `origen.movimientos_de_stock`

    def test_regla_c2_exactamente_uno_de_lote_y_partida(self):
        """Restricción C2: ni los dos ni ninguno."""
        viola(self, lambda: self.movimiento(partida=self.partida))
        viola(self, lambda: self.movimiento(lote=None))

    def test_regla_cantidad_positiva(self):
        """`cantidad > 0`."""
        viola(self, lambda: self.movimiento(cantidad=0))

    def test_regla_costo_unitario_no_negativo(self):
        """`costo_unitario >= 0`; con 4 decimales."""
        viola(self, lambda: self.movimiento(costo_unitario=Decimal("-0.0001")))
        self.assertEqual(self.movimiento(costo_unitario=Decimal("0")).costo_unitario, Decimal("0.0000"))

    def test_regla_tipo_dentro_de_la_lista(self):
        """`tipo_movimiento` dentro de los cinco valores."""
        viola(self, lambda: self.movimiento(tipo_movimiento="inventado"))

    def test_regla_salidas_de_lote_exigen_lote_y_los_movimientos_de_camara_exigen_partida(self):
        """`salida_por_cosecha` y `salida_por_merma` ⇒ lote; `ingreso_a_camara`, `egreso_de_camara` y `merma_en_camara` ⇒ partida."""
        for tipo in ("salida_por_cosecha", "salida_por_merma"):
            self.movimiento(tipo_movimiento=tipo)
            viola(self, lambda: self.movimiento(tipo_movimiento=tipo, lote=None, partida=self.partida))
        for tipo in ("ingreso_a_camara", "egreso_de_camara", "merma_en_camara"):
            self.movimiento(tipo_movimiento=tipo, lote=None, partida=self.partida)
            viola(self, lambda: self.movimiento(tipo_movimiento=tipo))


class BitacoraDeCosechaTests(Base):
    """D-64 punto 4 (R152) y D-69 punto 3."""

    def test_regla_tipo_cosecha_si_y_solo_si_hay_cosecha(self):
        """Restricción: `tipo_evento = cosecha` ⇔ `cosecha` no nula."""
        viola(self, lambda: self.bitacora("cosecha", lote=self.lote))
        viola(self, lambda: self.bitacora("otro_evento", cosecha=self.cosecha))
        registro = self.bitacora("cosecha", lote=self.lote, etapa=self.lote.etapa, cosecha=self.cosecha)
        self.assertEqual(self.cosecha.registros_de_bitacora.get().pk, registro.pk)

    def test_regla_los_dos_tipos_de_contrato_son_validos_sin_lote_etapa_ni_cosecha(self):
        """D-69 punto 3: `incumplimiento_de_clausula` y `anulacion_de_resolucion` valen, con `lote`, `etapa` y `cosecha` nulos."""
        for tipo in ("incumplimiento_de_clausula", "anulacion_de_resolucion"):
            self.bitacora(tipo)

    def test_regla_los_tipos_de_contrato_rechazan_lote_etapa_o_cosecha(self):
        """D-69 punto 3: con cualquiera de los dos tipos, `lote`, `etapa` y `cosecha` son nulos."""
        for tipo in ("incumplimiento_de_clausula", "anulacion_de_resolucion"):
            viola(self, lambda: self.bitacora(tipo, lote=self.lote))
            viola(self, lambda: self.bitacora(tipo, etapa=self.lote.etapa))
            viola(self, lambda: self.bitacora(tipo, cosecha=self.cosecha))

    def test_regla_un_tipo_inventado_se_sigue_rechazando(self):
        """La lista cerrada reemplazada sigue rechazando un tipo desconocido."""
        viola(self, lambda: self.bitacora("inventado"))


class MermaYConsumoTests(Base):
    """Causas nuevas de `Merma`, `Merma.orden` y `Consumo.orden` (D-64, D-68 punto 3)."""

    def merma(self, **campos):
        """Una `Merma` con lo mínimo y los `campos` pisados."""
        valores = dict(
            invernadero=self.e.invernadero, lote=self.lote, tipo_evento="merma", fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(), cant_merma=3, causa="plaga", etapa=self.lote.etapa,
        )
        valores.update(campos)
        return Merma.objects.create(**valores)

    def test_regla_las_causas_nuevas_son_validas_y_las_de_lote_en_pie_siguen_siendo_siete(self):
        """D-64 y D-68: `dano_en_camara`, `vencimiento_en_camara` valen sin orden; `dano_en_entrega`, con ella. `CAUSAS_EN_PIE` conserva las siete."""
        self.merma(causa="dano_en_camara", etapa=None)
        self.merma(causa="vencimiento_en_camara", etapa=None)
        self.merma(causa="dano_en_entrega", etapa=None, orden=orden_suelta(self.e.invernadero, "entrega"))
        self.assertEqual(len(Merma.CAUSAS_EN_PIE), 7)
        self.assertEqual(len(Merma.Causa.values), 10)
        viola(self, lambda: self.merma(causa="inventada"))

    def test_regla_orden_de_la_merma_si_y_solo_si_dano_en_entrega(self):
        """Restricción de `Merma.orden`: no nula ⇔ `causa = dano_en_entrega`."""
        entrega = orden_suelta(self.e.invernadero, "entrega")
        viola(self, lambda: self.merma(causa="dano_en_entrega", etapa=None))
        viola(self, lambda: self.merma(causa="plaga", orden=entrega))
        self.assertEqual(entrega.mermas_de_orden.count(), 0)

    def consumo(self, existencia, **campos):
        """Un `Consumo` con lo mínimo y los `campos` pisados."""
        valores = dict(
            invernadero=self.e.invernadero, tipo_evento="consumo", fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(), monto_consumo=Decimal("10.00"), cant_consumo=Decimal("2.500"),
            fecha_consumo=timezone.localdate(), insumo_invernadero=existencia,
        )
        valores.update(campos)
        return Consumo.objects.create(**valores)

    def test_regla_consumo_con_tres_origenes_exactamente_uno(self):
        """D-68 punto 3: `consumo_un_solo_origen` pasa a exactamente uno de `siembra`, `aplicacion` y `orden`."""
        existencia = insumo_adicional(self.e, stock=5)
        entrega = orden_suelta(self.e.invernadero, "entrega")
        self.assertEqual(self.consumo(existencia, orden=entrega).orden_id, entrega.pk)
        self.assertEqual(entrega.consumos_de_orden.count(), 1)
        viola(self, lambda: self.consumo(existencia))
        viola(self, lambda: self.consumo(existencia, orden=entrega, siembra=self.lote.siembra))


class OrigenDeCosechaTests(Base):
    """D-64 punto 5."""

    def test_regla_origen_de_la_cosecha_por_defecto_automatica_y_dentro_de_la_lista(self):
        """`origen_cosecha` es `automatica` por defecto y solo admite `automatica`, `manual` y `encadenada`."""
        self.assertEqual(Cosecha.objects.get(pk=self.cosecha.pk).origen_cosecha, "automatica")
        self.assertEqual([v for v, _ in Cosecha.OrigenCosecha.choices], ["automatica", "manual", "encadenada"])
        viola(self, lambda: Cosecha.objects.filter(pk=self.cosecha.pk).update(origen_cosecha="inventada"))
