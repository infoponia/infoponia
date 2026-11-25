# Pruebas de la sección 13 de ``docs/demo/datos_de_la_demo.md`` (DAT-02, paso 2): S-1 y S-2 pactados con COM-PCT-SUM. La prueba clave es la
# última: con LN-2 pasado a Maduración, el paso diario 40 corrido con HOY+1 reserva el período de S-2 (HOY+8); es la escena en vivo.
# Los secretos de las pruebas se inventan en cada corrida. En las pruebas el correo no está configurado: el comprobante queda «pendiente de envío».

import secrets
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from comercial.models import ReservaStock
from contabilidad.tests.fabricas import PlanDeCuentasMixin
from core.procesos import correr_proceso_diario
from demo import carga
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta, Invernadero, SectorProduccion
from produccion.models import Lote
from produccion.servicios import transiciones

BASE = "ejemplo"


class CargaDeSuministrosTests(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """DAT-02 paso 2: S-1 con sus dos períodos reservados, S-2 sin reservas, y la pre-reserva automática de S-2 en HOY+1."""

    @classmethod
    def setUpTestData(cls):
        cls.hoy = timezone.localdate()
        cls.contexto = carga.Contexto(hoy=cls.hoy, base=BASE, contrasena=secrets.token_urlsafe(12))
        cls.lineas = carga.cargar(cls.contexto)

    def _reservas(self, clave):
        suministro = self.contexto.suministros[clave]
        return list(
            ReservaStock.objects.filter(detalle_suministro__suministro=suministro).order_by("fecha_entrega_reserva").select_related("cosecha")
        )

    def _pasar_ln2_a_maduracion(self):
        """Lo que se hace en vivo: el Agrónomo planifica la transición de LN-2 y el Capataz la concreta con fecha de hoy (le faltaba un día)."""
        norte = Invernadero.objects.get(nombre_invernadero="Norte")
        lote = self.contexto.lotes["LN-2"]
        destino = SectorProduccion.objects.get(invernadero=norte, nombre_sector="Maduración N2")
        orden = transiciones.planificar_transicion(
            norte.agronomo,
            transiciones.DatosDeTransicion(lote_id=lote.pk, fecha_programada=self.hoy, distribucion=((destino.pk, 200),)),
        )
        transiciones.concretar_transicion(norte.capataz, orden.pk, transiciones.DatosDeConcrecionDeTransicion(fecha_efectiva=self.hoy))

    def test_dat_02_la_seccion_13_se_carga_sin_saltearse(self):
        """DAT-02 paso 0: COM-PCT-SUM está en el repo, así que la sección 13 se carga."""
        self.assertTrue(any(l.startswith("Cargado: 13. Suministros") for l in self.lineas), self.lineas)

    def test_dat_02_s1_reserva_los_periodos_hoy_y_hoy_mas_7_con_60_plantas_de_ln1_cada_uno(self):
        """Sección 13: con la pre-reserva de 7 días, S-1 reserva exactamente HOY y HOY+7: 60 + 60 de LN-1."""
        s1 = self.contexto.suministros["S-1"]
        self.assertEqual((s1.periodos_reservados, s1.cosechas_programadas), (2, 2))
        reservas = self._reservas("S-1")
        self.assertEqual([r.fecha_entrega_reserva for r in reservas], [self.hoy, self.hoy + timedelta(days=7)])
        ln1 = self.contexto.lotes["LN-1"]
        for reserva in reservas:
            self.assertEqual(reserva.estado_reserva, "activa")
            self.assertEqual(list(reserva.lineas.values_list("lote_id", "cantidad_reservada")), [(ln1.pk, 60)])

    def test_dat_02_s1_tiene_la_cosecha_de_hoy_a_realizar_programada_para_hoy(self):
        """Sección 13: la cosecha del período HOY queda «a realizar», programada para HOY (máximo entre hoy y HOY−3); la de HOY+7, para HOY+4."""
        primera, segunda = self._reservas("S-1")
        self.assertEqual(primera.cosecha.estado_orden, "a_realizar")
        self.assertEqual(primera.cosecha.fecha_programada_orden, self.hoy)
        self.assertEqual(segunda.cosecha.estado_orden, "a_realizar")
        self.assertEqual(segunda.cosecha.fecha_programada_orden, self.hoy + timedelta(days=4))

    def test_dat_02_s2_se_pacta_sin_ninguna_reserva_porque_su_primera_entrega_cae_fuera_de_la_ventana(self):
        """Sección 13: la primera entrega de S-2 es HOY+8 y la ventana llega a HOY+7: no se reserva nada."""
        s2 = self.contexto.suministros["S-2"]
        self.assertEqual((s2.periodos_reservados, s2.cosechas_programadas), (0, 0))
        self.assertEqual(self._reservas("S-2"), [])

    def test_dat_02_los_contratos_tienen_los_valores_de_la_tabla(self):
        """Sección 13: tolerados, multa y cláusulas de S-1 y S-2."""
        s1, s2 = self.contexto.suministros["S-1"], self.contexto.suministros["S-2"]
        self.assertEqual((s1.cliente.cuit_cliente, s2.cliente.cuit_cliente), ("30714567809", "30711223300"))
        self.assertEqual((s1.incumplimientos_tolerados, s2.incumplimientos_tolerados), (0, 2))
        self.assertEqual((str(s1.multa_resolucion), str(s2.multa_resolucion)), ("50000.00", "30000.00"))
        self.assertEqual((s1.duracion_meses, s2.duracion_meses), (3, 3))

    def test_dat_02_con_ln2_en_maduracion_el_proceso_diario_en_hoy_mas_1_reserva_el_periodo_de_s2(self):
        """PRUEBA CLAVE de la escena en vivo: LN-2 pasa a Maduración y el paso 40 con HOY+1 (ventana hasta HOY+8) reserva las 40 plantas de
        S-2 para HOY+8 y crea la cosecha sola, programada para HOY+5. S-1 no cambia (HOY ya pasó y HOY+7 ya estaba cubierto)."""
        self._pasar_ln2_a_maduracion()
        resultados = correr_proceso_diario(hoy=self.hoy + timedelta(days=1), solo="pre_reservar_suministros")
        paso, resumen, error = resultados[0]
        self.assertIsNone(error)
        self.assertEqual((resumen.procesados, resumen.creados), (1, 1), resumen)
        reservas = self._reservas("S-2")
        self.assertEqual([r.fecha_entrega_reserva for r in reservas], [self.hoy + timedelta(days=8)])
        reserva = reservas[0]
        ln2 = Lote.objects.get(pk=self.contexto.lotes["LN-2"].pk)
        self.assertEqual(list(reserva.lineas.values_list("lote_id", "cantidad_reservada")), [(ln2.pk, 40)])
        self.assertEqual(reserva.cosecha.estado_orden, "a_realizar")
        self.assertEqual(reserva.cosecha.fecha_programada_orden, self.hoy + timedelta(days=5))
        self.assertEqual(len(self._reservas("S-1")), 2)

    def test_dat_02_con_ln2_todavia_en_crecimiento_el_paso_deja_el_periodo_de_s2_sin_cubrir_con_su_alerta(self):
        """El otro resultado válido de la escena: si LN-2 todavía no pasó a Maduración, el período queda sin cobertura y aparece la alerta."""
        resultados = correr_proceso_diario(hoy=self.hoy + timedelta(days=1), solo="pre_reservar_suministros")
        resumen = resultados[0][1]
        self.assertEqual((resumen.procesados, resumen.creados), (1, 0), resumen)
        self.assertEqual(self._reservas("S-2"), [])
        self.assertTrue(Alerta.objects.filter(tipo_alerta="comercial_periodo_sin_cobertura", estado_alerta=Alerta.Estado.ACTIVA).exists())
