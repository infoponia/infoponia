# Pruebas de los modelos de PRD-02 (paso 1): `TransicionEtapa`, `Merma` y `AlertaDeMerma`: cada restricción de la base (viola y no
# viola), la herencia multitabla y las fábricas `lote_con_ciclo` y `orden_de_transicion`. Fuente: docs/modelo/produccion.md
# («TransicionEtapa», «Merma», «Restricciones de la base»), D-50 y D-53.

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_alerta
from produccion.models import AlertaDeMerma, Bitacora, ConCapataz, Merma, OrdenTrabajo, TransicionEtapa
from produccion.tests.fabricas import invernadero_con_produccion, lote_con_ciclo, orden_de_transicion


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class ModelosDeTransicionTests(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()

    def merma_de(self, lote, **campos):
        """Una `Merma` con lo mínimo de su bitácora y los `campos` que se quieran pisar."""
        valores = dict(
            invernadero=lote.invernadero, lote=lote, etapa=lote.etapa, tipo_evento="merma",
            fecha_bitacora=timezone.localdate(), hora_bitacora=timezone.localtime().time(), cant_merma=3, causa="plaga",
        )
        valores.update(campos)
        return Merma.objects.create(**valores)

    # ---- TransicionEtapa ----

    def test_regla_transicion_es_una_orden_de_trabajo_con_capataz_y_su_tipo(self):
        """docs/modelo/produccion.md, «TransicionEtapa» y D-50/D-53: es una `OrdenTrabajo` (multitabla) de tipo transición, con su
        Capataz por `ConCapataz`; su documento de origen es una orden de trabajo (D-52)."""
        lote = lote_con_ciclo(self.e)
        transicion = orden_de_transicion(self.e, lote)
        orden = OrdenTrabajo.objects.get(pk=transicion.pk)
        self.assertEqual(orden.tipo_orden, OrdenTrabajo.Tipo.TRANSICION)
        self.assertEqual(orden.tipo, OrigenDocumento.Tipo.ORDEN_DE_TRABAJO)
        self.assertEqual(TransicionEtapa.objects.get(pk=orden.pk).capataz, self.e.capataz)
        self.assertTrue(issubclass(TransicionEtapa, ConCapataz))
        self.assertEqual(transicion.codigo, f"OT-{transicion.numero:04d}")

    def test_regla_transicion_la_etapa_destino_es_la_siguiente_del_ciclo(self):
        """Regla 1 de 8.20: la fábrica arma la orden hacia la etapa siguiente; la de origen no se guarda (es la del lote)."""
        lote = lote_con_ciclo(self.e, etapa="crecimiento")
        transicion = orden_de_transicion(self.e, lote)
        self.assertEqual(transicion.etapa_destino.tipo_etapa.codigo, "floracion")
        self.assertEqual(lote.etapa.tipo_etapa.codigo, "crecimiento")

    def test_regla_transicion_cantidad_y_fecha_nulas_si_esta_a_realizar_o_cancelada(self):
        """«Restricciones de la base»: `cant_transferido` y `fecha_transicion` están nulos mientras la orden está «a realizar» o
        «cancelada»."""
        lote = lote_con_ciclo(self.e)
        for estado in ("a_realizar", "cancelada"):
            with self.subTest(estado=estado):
                orden = orden_de_transicion(self.e, lote, estado=estado)
                self.assertIsNone(orden.cant_transferido)
                self.assertIsNone(orden.fecha_transicion)

    def test_regla_transicion_concretada_tiene_cantidad_y_fecha(self):
        """«Restricciones de la base»: concretada, la cantidad (suma de los ocupados) y la fecha efectiva están cargadas."""
        lote = lote_con_ciclo(self.e, cantidad=40)
        orden = orden_de_transicion(self.e, lote, estado="concretada")
        self.assertEqual(orden.cant_transferido, 40)
        self.assertEqual(orden.fecha_transicion, timezone.localdate())

    def test_regla_transicion_cantidad_y_fecha_se_cargan_juntas(self):
        """«Restricciones de la base»: una sola de las dos cargada viola; las dos, o ninguna, no. El vínculo con el estado de la
        orden (que vive en el padre) lo garantiza el servicio."""
        lote = lote_con_ciclo(self.e)
        orden = orden_de_transicion(self.e, lote)
        hoy = timezone.localdate()
        viola(self, lambda: TransicionEtapa.objects.filter(pk=orden.pk).update(cant_transferido=5))
        viola(self, lambda: TransicionEtapa.objects.filter(pk=orden.pk).update(fecha_transicion=hoy))
        TransicionEtapa.objects.filter(pk=orden.pk).update(cant_transferido=5, fecha_transicion=hoy)
        TransicionEtapa.objects.filter(pk=orden.pk).update(cant_transferido=None, fecha_transicion=None)

    def test_regla_transicion_cantidad_transferida_positiva(self):
        """«TransicionEtapa»: `cant_transferido` es mayor que cero cuando existe (cero viola)."""
        lote = lote_con_ciclo(self.e)
        orden = orden_de_transicion(self.e, lote)
        viola(
            self,
            lambda: TransicionEtapa.objects.filter(pk=orden.pk).update(
                cant_transferido=0, fecha_transicion=timezone.localdate()
            ),
        )

    def test_regla_transicion_un_lote_con_dos_a_realizar_lo_impide_el_servicio_no_la_base(self):
        """Regla 4 de 8.21: no hay restricción de base (el estado vive en el padre): la base admite dos transiciones «a realizar»
        del mismo lote. Que no se creen lo garantiza `planificar_transicion` con el bloqueo del lote (paso 4)."""
        lote = lote_con_ciclo(self.e)
        orden_de_transicion(self.e, lote)
        orden_de_transicion(self.e, lote)
        self.assertEqual(TransicionEtapa.objects.filter(lote=lote, estado_orden="a_realizar").count(), 2)

    def test_regla_transicion_la_bitacora_es_uno_a_uno_y_nula_hasta_concretar(self):
        """R080: `bitacora_de_transicion` es nula hasta concretar y un registro de bitácora no es de dos transiciones."""
        lote = lote_con_ciclo(self.e)
        primera, segunda = orden_de_transicion(self.e, lote), orden_de_transicion(self.e, lote)
        self.assertIsNone(primera.bitacora_de_transicion)
        registro = Bitacora.objects.create(
            invernadero=lote.invernadero, lote=lote, tipo_evento="transicion", fecha_bitacora=timezone.localdate(),
            hora_bitacora=timezone.localtime().time(),
        )
        TransicionEtapa.objects.filter(pk=primera.pk).update(bitacora_de_transicion=registro)
        viola(self, lambda: TransicionEtapa.objects.filter(pk=segunda.pk).update(bitacora_de_transicion=registro))

    # ---- Merma ----

    def test_regla_merma_es_una_bitacora_de_tipo_merma_con_su_lote_y_etapa(self):
        """«Merma»: hija de `Bitacora` (multitabla); su documento de origen es una bitácora (D-52)."""
        lote = lote_con_ciclo(self.e)
        merma = self.merma_de(lote)
        registro = Bitacora.objects.get(pk=merma.pk)
        self.assertEqual(registro.tipo_evento, Bitacora.TipoEvento.MERMA)
        self.assertEqual(registro.tipo, OrigenDocumento.Tipo.BITACORA)
        self.assertEqual((registro.lote, registro.etapa), (lote, lote.etapa))
        self.assertEqual(str(merma), f"Merma #{merma.pk}")

    def test_regla_merma_cantidad_positiva_y_causa_dentro_de_la_lista(self):
        """«Merma»: `cant_merma > 0` y la causa es una de la lista; COM-04a suma tres (cámara y entrega), así que las del lote en pie son
        `Merma.CAUSAS_EN_PIE` (se ajustó esta prueba: antes la lista era de siete y rechazaba `vencimiento_en_camara`)."""
        lote = lote_con_ciclo(self.e)
        viola(self, lambda: self.merma_de(lote, cant_merma=0))
        viola(self, lambda: self.merma_de(lote, causa="inventada"))
        for causa in Merma.CAUSAS_EN_PIE:
            self.merma_de(lote, causa=causa)
        self.assertEqual(len(Merma.CAUSAS_EN_PIE), 7)

    # ---- AlertaDeMerma ----

    def test_regla_alerta_de_merma_una_alerta_pertenece_a_una_sola_merma(self):
        """R089 y restricción C5 (`docs/api/alertas.md`, sección 4): el enlace es `OneToOne` con la alerta; una merma puede tener
        las dos (umbral y plantas comprometidas)."""
        lote = lote_con_ciclo(self.e)
        merma, otra = self.merma_de(lote), self.merma_de(lote)
        alerta = crear_alerta(lote.invernadero, nivel_severidad="critica")
        AlertaDeMerma.objects.create(merma=merma, alerta=alerta)
        AlertaDeMerma.objects.create(merma=merma, alerta=crear_alerta(lote.invernadero))
        viola(self, lambda: AlertaDeMerma.objects.create(merma=otra, alerta=alerta))
        self.assertEqual(merma.alertas_de_merma.count(), 2)

    # ---- Fábricas ----

    def test_fabrica_lote_con_ciclo_deja_al_lote_en_su_etapa_con_su_fecha_de_entrada(self):
        """La fábrica pasa por una transición «concretada» por etapa anterior: la entrada a la etapa actual sale de la última
        (regla 5 de 8.21) y las ocupaciones vigentes suman la cantidad actual."""
        lote = lote_con_ciclo(self.e, cantidad=30, etapa="crecimiento", dias_en_etapa=4)
        self.assertEqual(lote.etapa.tipo_etapa.codigo, "crecimiento")
        self.assertEqual(lote.cantidad_actual, 30)
        vigentes = lote.ocupaciones.filter(cant_agujeros_ocupados__gt=0)
        self.assertEqual([o.sector.tipo_etapa.codigo for o in vigentes], ["crecimiento"])
        self.assertEqual(sum(o.cant_agujeros_ocupados for o in vigentes), 30)
        # La fecha de entrada (la transición concretada más reciente) la prueba `test_transiciones_lectura.py`.
        ultima = lote.transiciones.get(estado_orden="concretada", etapa_destino=lote.etapa)
        self.assertEqual(ultima.fecha_transicion, timezone.localdate() - timedelta(days=4))
