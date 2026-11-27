# Pruebas de CON-05 (paso 3), regla 9 de CON-INI-EJE, «Sin ejercicio no hay asiento», para los dos pasos diarios que generan asientos: el 20 «Vencer partidas en cámara» (la merma por
# vencimiento, CON-04c) y el 33 «Resolver suministros con incumplimientos superados» (la multa, CON-04d). Con los fixtures reales de cámara y de suministros: sin ejercicio, el paso no procesa
# nada, no genera asientos ni errores, informa «contabilidad no iniciada: queda pendiente para mañana» y, cuando se inicia la contabilidad, el mismo paso del día siguiente lo recupera.
# El contrato del paso (sin fixtures) está en `contabilidad/tests/test_contabilidad_no_iniciada.py`. Cada prueba arma sus propios datos.
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from comercial.models import Suministro
from comercial.servicios import camara, resoluciones
from comercial.tests.fabricas import escenario_comercial, partida
from comercial.tests.test_com_rsv_sum import BaseDeResolucion
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio_abierto
from core.models import RegistroAuditoria
from core.procesos import correr_proceso_diario
from inventario.tests.fabricas import ConDatosDeInventario
from produccion.models import Merma, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
TEXTO = "contabilidad no iniciada: queda pendiente para mañana"


class PasoVencerPartidasSinContabilidadTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Paso 20 (CON-04c): una partida de cámara vencida, sin ejercicio."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.partida = partida(self.lote, 40, fecha_limite=HOY - timedelta(days=1), costo="2.5000")
        EjercicioContable.objects.all().delete()  # la contabilidad sin iniciar

    def test_regla_9_sin_ejercicio_el_paso_20_no_vence_la_partida_ni_asienta_y_dice_el_motivo(self):
        """Regla 9: sin ejercicio el paso 20 devuelve `ResumenDePaso(0, 0, 0, «contabilidad no iniciada…»)`: la partida sigue «disponible», no hay merma ni asiento ni ejercicio ni registro de auditoría de la merma."""
        resumen = camara.vencer_partidas_en_camara(HOY)

        self.assertEqual(tuple(resumen), (0, 0, 0, TEXTO))
        self.partida.refresh_from_db()
        self.assertEqual(self.partida.estado_stock_cosechado, StockCosechado.Estado.DISPONIBLE)
        self.assertFalse(Merma.objects.filter(causa="vencimiento_en_camara").exists())
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(EjercicioContable.objects.exists())

    def test_regla_9_el_paso_20_corrido_por_el_proceso_diario_no_da_error(self):
        """Regla 9 y D-56 punto 5: corrido por el proceso diario (`--solo vencer_partidas_en_camara`) el paso termina sin error y con el texto en su resumen."""
        (paso, resumen, error), = correr_proceso_diario(hoy=HOY, solo="vencer_partidas_en_camara")

        self.assertIsNone(error)
        self.assertEqual(resumen.detalle, TEXTO)

    def test_regla_9_al_iniciar_la_contabilidad_el_paso_del_dia_siguiente_vence_la_partida_y_asienta(self):
        """Regla 9 («queda pendiente para mañana»): corrido de nuevo con el ejercicio ya creado, el mismo paso vence la partida y genera su asiento una sola vez (idempotente)."""
        camara.vencer_partidas_en_camara(HOY)
        ejercicio_abierto(HOY)

        camara.vencer_partidas_en_camara(HOY)
        camara.vencer_partidas_en_camara(HOY)

        self.partida.refresh_from_db()
        self.assertEqual(self.partida.estado_stock_cosechado, StockCosechado.Estado.VENCIDO)
        merma = Merma.objects.get(causa="vencimiento_en_camara")
        self.assertEqual(AsientoContable.objects.filter(origen_id=merma.pk).count(), 1)


class PasoResolverSuministrosSinContabilidadTests(BaseDeResolucion):
    """Paso 33 (CON-04d): un suministro con más incumplimientos que los tolerados y con multa, sin ejercicio."""

    def test_regla_9_sin_ejercicio_el_paso_33_no_resuelve_el_contrato_ni_asienta_la_multa(self):
        """Regla 9: sin ejercicio el paso 33 devuelve `ResumenDePaso(0, 0, 0, «contabilidad no iniciada…»)`: el suministro sigue «vigente» (no se resuelve a medias: la multa no se asienta y por eso
        tampoco se cancela nada), sin asiento ni ejercicio."""
        x = self.armar(multa="50000.00")
        EjercicioContable.objects.all().delete()

        with self.captureOnCommitCallbacks(execute=True):
            resumen = resoluciones.resolver_suministros_pendientes(HOY)

        self.assertEqual(tuple(resumen), (0, 0, 0, TEXTO))
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "vigente")
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(EjercicioContable.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="resolucion_suministro").exists())

    def test_regla_9_el_paso_33_corrido_por_el_proceso_diario_no_da_error(self):
        """Regla 9 y D-56 punto 5: por el proceso diario (`--solo resolver_suministros`) termina sin error y con el texto en su resumen."""
        self.armar(multa="50000.00")
        EjercicioContable.objects.all().delete()

        with self.captureOnCommitCallbacks(execute=True):
            (paso, resumen, error), = correr_proceso_diario(hoy=HOY, solo="resolver_suministros")

        self.assertIsNone(error)
        self.assertEqual(resumen.detalle, TEXTO)

    def test_regla_9_al_iniciar_la_contabilidad_el_paso_del_dia_siguiente_resuelve_y_asienta_la_multa(self):
        """Regla 9 («queda pendiente para mañana»): con el ejercicio creado el mismo paso resuelve el contrato y asienta la multa una sola vez."""
        x = self.armar(multa="50000.00")
        EjercicioContable.objects.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            resoluciones.resolver_suministros_pendientes(HOY)
        ejercicio_abierto(HOY)

        with self.captureOnCommitCallbacks(execute=True):
            resoluciones.resolver_suministros_pendientes(HOY)
            resoluciones.resolver_suministros_pendientes(HOY)

        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual(AsientoContable.objects.filter(origen_id=x.contrato.pk).count(), 1)
