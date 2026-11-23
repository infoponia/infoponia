# Pruebas de los modelos de PRD-03 (paso 1): `AplicacionInsumos`, `ImputacionCosto`, el origen `aplicacion` del `Consumo` con su
# restricción «exactamente uno de siembra y aplicación», los tipos de bitácora nuevos y la migración `0003_aplicaciones`.
# Fuente: docs/modelo/produccion.md («AplicacionInsumos», «ImputacionCosto», «Consumo»), D-51 puntos 3 y 4 y D-52.
# La de la migración lleva la etiqueta «migracion»: desarma y vuelve a armar el esquema (en local se excluye; el CI la corre).

from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, tag
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.models import MovimientoInsumo
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import AplicacionInsumos, Bitacora, Consumo, ImputacionCosto
from produccion.tests.fabricas import insumo_adicional, invernadero_con_produccion, lote_activo


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


def aplicacion_de(escenario, **campos):
    """Una `AplicacionInsumos` con lo mínimo de su bitácora (tipo `aplicacion`, sin lote ni etapa)."""
    valores = dict(
        invernadero=escenario.invernadero,
        tipo_evento="aplicacion",
        fecha_bitacora=timezone.localdate(),
        hora_bitacora=timezone.localtime().time(),
        responsable=escenario.capataz,
    )
    valores.update(campos)
    return AplicacionInsumos.objects.create(**valores)


def consumo_de(escenario, existencia, **campos):
    """Un `Consumo` con lo mínimo de su bitácora; el origen (`siembra` o `aplicacion`) lo ponen los `campos`."""
    valores = dict(
        invernadero=escenario.invernadero,
        tipo_evento="consumo",
        fecha_bitacora=timezone.localdate(),
        hora_bitacora=timezone.localtime().time(),
        monto_consumo=Decimal("10.00"),
        cant_consumo=Decimal("2.500"),
        fecha_consumo=timezone.localdate(),
        insumo_invernadero=existencia,
    )
    valores.update(campos)
    return Consumo.objects.create(**valores)


class ModelosDeAplicacionTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()
        cls.fertilizante = insumo_adicional(cls.e, stock=50)

    def test_regla_aplicacion_es_una_bitacora_hija_con_su_documento_de_origen(self):
        """D-51 punto 3 y D-52: `AplicacionInsumos` es hija de `Bitacora` (multitabla); su documento de origen es una bitácora."""
        aplicacion = aplicacion_de(self.e)
        bitacora = Bitacora.objects.get(pk=aplicacion.pk)
        self.assertEqual(bitacora.tipo_evento, Bitacora.TipoEvento.APLICACION)
        self.assertEqual(bitacora.tipo, OrigenDocumento.Tipo.BITACORA)
        self.assertTrue(issubclass(AplicacionInsumos, Bitacora))
        self.assertEqual(str(aplicacion), f"Aplicación #{aplicacion.pk}")

    def test_regla_tipos_de_bitacora_de_la_ronda_se_aceptan_y_uno_ajeno_se_rechaza(self):
        """docs/modelo/produccion.md («Bitacora.TipoEvento»): `aplicacion`, `otro_evento` y `consumo` valen desde PRD-03; los de PRD-04
        todavía no (`fuera_de_servicio`), y un tipo cualquiera tampoco."""
        for tipo in ("aplicacion", "otro_evento", "consumo", "siembra", "transicion", "merma"):
            Bitacora.objects.create(
                invernadero=self.e.invernadero, tipo_evento=tipo,
                fecha_bitacora=timezone.localdate(), hora_bitacora=timezone.localtime().time(),
            )
        for tipo in ("fuera_de_servicio", "inventado"):
            viola(self, lambda tipo=tipo: Bitacora.objects.create(
                invernadero=self.e.invernadero, tipo_evento=tipo,
                fecha_bitacora=timezone.localdate(), hora_bitacora=timezone.localtime().time(),
            ))

    def test_regla_consumo_con_aplicacion_y_sin_siembra_es_valido(self):
        """D-51 punto 3: el consumo de una aplicación tiene `aplicacion` y no `siembra`."""
        aplicacion = aplicacion_de(self.e)
        consumo = consumo_de(self.e, self.fertilizante, aplicacion=aplicacion)
        self.assertEqual(list(aplicacion.consumos.all()), [consumo])
        self.assertIsNone(consumo.siembra)

    def test_regla_consumo_con_siembra_y_sin_aplicacion_sigue_siendo_valido(self):
        """PRD-01 no cambia: el consumo de una siembra tiene `siembra` y no `aplicacion`."""
        lote = lote_activo(self.e)
        consumo = consumo_de(self.e, self.fertilizante, siembra=lote.siembra, tipo_evento="siembra", lote=lote)
        self.assertIsNone(consumo.aplicacion)

    def test_regla_consumo_con_los_dos_origenes_viola_la_base(self):
        """D-51 punto 3: «exactamente uno de `siembra` y `aplicacion`»: los dos juntos, no."""
        lote = lote_activo(self.e)
        aplicacion = aplicacion_de(self.e)
        viola(self, lambda: consumo_de(self.e, self.fertilizante, siembra=lote.siembra, aplicacion=aplicacion))

    def test_regla_consumo_sin_ningun_origen_viola_la_base(self):
        """D-51 punto 3: tampoco vale un consumo sin origen."""
        viola(self, lambda: consumo_de(self.e, self.fertilizante))

    def test_regla_imputacion_es_unica_por_consumo_y_lote(self):
        """D-51 punto 4: único `(consumo, lote)`: un lote recibe una sola parte de cada consumo."""
        lote = lote_activo(self.e)
        consumo = consumo_de(self.e, self.fertilizante, aplicacion=aplicacion_de(self.e))
        ImputacionCosto.objects.create(consumo=consumo, lote=lote, monto_imputado=Decimal("4.00"))
        viola(self, lambda: ImputacionCosto.objects.create(consumo=consumo, lote=lote, monto_imputado=Decimal("1.00")))

    def test_regla_imputacion_con_monto_negativo_viola_la_base(self):
        """docs/modelo/produccion.md («ImputacionCosto»): `monto_imputado >= 0`."""
        lote = lote_activo(self.e)
        consumo = consumo_de(self.e, self.fertilizante, aplicacion=aplicacion_de(self.e))
        viola(self, lambda: ImputacionCosto.objects.create(consumo=consumo, lote=lote, monto_imputado=Decimal("-0.01")))

    def test_regla_imputaciones_de_un_consumo_van_a_lotes_distintos(self):
        """Un consumo puede imputarse a varios lotes (uno por lote); se leen por `consumo.imputaciones`."""
        uno, otro = lote_activo(self.e), lote_activo(self.e, sector="crecimiento")
        consumo = consumo_de(self.e, self.fertilizante, aplicacion=aplicacion_de(self.e))
        ImputacionCosto.objects.create(consumo=consumo, lote=uno, monto_imputado=Decimal("6.00"))
        ImputacionCosto.objects.create(consumo=consumo, lote=otro, monto_imputado=Decimal("4.00"))
        self.assertEqual(sum(i.monto_imputado for i in consumo.imputaciones.all()), consumo.monto_consumo)

    def test_d52_movimientos_del_consumo_de_una_aplicacion_llevan_el_consumo_como_origen_sin_tabla_de_enlace(self):
        """D-52: la salida de stock del consumo de una aplicación lleva `origen` = el consumo; el consumo la lee por
        `movimientos_de_insumo`, sin tabla de enlace."""
        consumo = consumo_de(self.e, self.fertilizante, aplicacion=aplicacion_de(self.e))
        propuesta = stock.proponer_lotes_fefo(self.fertilizante.pk, Decimal("2.500"), stock.hoy())
        movimientos = stock.registrar_salida_por_consumo(self.fertilizante.pk, propuesta.partes, origen_id=consumo.pk)
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0].origen_id, consumo.pk)
        self.assertEqual(list(consumo.movimientos_de_insumo.all()), movimientos)
        self.assertEqual(movimientos[0].tipo_movimiento, MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO)


ANTERIOR = ("produccion", "0002_transicion_y_merma")
ESTA = ("produccion", "0003_aplicaciones")


def restricciones_de(tabla):
    """Los nombres de las restricciones de la tabla, tal como las ve la base."""
    with connection.cursor() as cursor:
        return set(connection.introspection.get_constraints(cursor, tabla))


@tag("migracion")
class MigracionDeAplicacionesTests(ConDatosDeInventario, TransactionTestCase):
    """Migra hacia atrás y hacia adelante con una siembra y su consumo ya cargados. Al terminar deja la base en la última migración."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate([destino])

    def test_regla_la_migracion_reemplaza_la_restriccion_de_origen_y_conserva_el_consumo_de_una_siembra(self):
        """D-51 punto 3: con una siembra existente, la `0003` cambia `consumo_origen_es_siembra` por `consumo_un_solo_origen`, en los dos
        sentidos, sin tocar el consumo ya cargado."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        e = invernadero_con_produccion(geografia_propia=True)
        existencia = insumo_adicional(e, stock=5)
        lote = lote_activo(e)
        consumo = consumo_de(e, existencia, siembra=lote.siembra, tipo_evento="siembra", lote=lote)
        self.assertIn("consumo_un_solo_origen", restricciones_de("produccion_consumo"))
        self.assertNotIn("consumo_origen_es_siembra", restricciones_de("produccion_consumo"))

        self.migrar(ANTERIOR)
        self.assertIn("consumo_origen_es_siembra", restricciones_de("produccion_consumo"))
        self.assertNotIn("consumo_un_solo_origen", restricciones_de("produccion_consumo"))
        self.assertNotIn("produccion_imputacioncosto", connection.introspection.table_names())

        self.migrar(ESTA)
        self.assertIn("consumo_un_solo_origen", restricciones_de("produccion_consumo"))
        self.assertNotIn("consumo_origen_es_siembra", restricciones_de("produccion_consumo"))
        self.assertTrue(Consumo.objects.filter(pk=consumo.pk, siembra_id=lote.siembra_id, aplicacion__isnull=True).exists())
