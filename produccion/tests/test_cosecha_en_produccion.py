# Pruebas de lo que COM-02 suma a `produccion` (D-59): las restricciones de `Cosecha` y `StockCosechado`, la cosecha en la unión
# `ordenes_del_capataz` y en el traspaso del Capataz, lo que la bandeja, la lista y las cancelables todavía NO muestran (hasta COM-04a),
# los impedimentos de baja del invernadero y de la variedad y la condición 1 de las plantas comprometidas (regla 15 de 8.8).
# Fuente: docs/modelo/produccion.md («Cosecha», «StockCosechado», «Diferencias», fila 8), docs/api/extensiones_de_produccion.md y D-59.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventario.tests.fabricas import ConDatosDeInventario
from maestros import extensiones as extensiones_de_maestros
from maestros.models import Alerta
from maestros.tests.fabricas import crear_capataz_activo
from produccion import extensiones
from produccion.models import AlertaDeMerma, Cosecha, OrdenTrabajo, StockCosechado
from produccion.servicios import mermas, ordenes, registrantes
from produccion.tests.fabricas import cosecha, invernadero_con_produccion, lote_maduro, orden_suelta

Tipo = OrdenTrabajo.Tipo


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


def consultas(llamada):
    """Cuántas consultas hace `llamada()`."""
    with CaptureQueriesContext(connection) as capturadas:
        llamada()
    return len(capturadas)


class CosechaEnProduccionBase(ConDatosDeInventario, TestCase):
    """Un invernadero con producción armado una vez."""

    @classmethod
    def setUpTestData(cls):
        cls.e = invernadero_con_produccion()


class RestriccionesTests(CosechaEnProduccionBase):
    """Restricciones de la base de `Cosecha` y de `StockCosechado` (docs/modelo/produccion.md, fichas)."""

    def partida(self, **campos):
        """Una `StockCosechado` válida con los `campos` que se quieran pisar."""
        lote = lote_maduro(self.e, 50)
        valores = dict(
            lote=lote,
            cantidad_ingreso_cosechado=10,
            cantidad_disponible_cosechado=10,
            fecha_ingreso=timezone.localdate(),
            fecha_limite=timezone.localdate() + timedelta(days=5),
            motivo_cosechado="excedente_de_cosecha",
            costo_unitario_cosechado=Decimal("1.5000"),
        )
        valores.update(campos)
        return StockCosechado.objects.create(**valores)

    def test_regla_cosecha_exige_prioridad(self):
        """Modelo de produccion, «Restricciones de la base» de OrdenTrabajo: `tipo_orden = cosecha` ⇒ prioridad no nula (D-59, MD-18)."""
        viola(self, lambda: cosecha(self.e, prioridad=None))
        self.assertEqual(cosecha(self.e, prioridad="alta").prioridad_orden, "alta")

    def test_regla_otros_tipos_siguen_sin_exigir_prioridad(self):
        """La restricción es solo de la cosecha: una entrega sin prioridad se guarda (MD-73)."""
        self.assertIsNone(OrdenTrabajo.objects.create(
            tipo_orden=Tipo.ENTREGA, numero=ordenes.siguiente_numero(), fecha_programada_orden=timezone.localdate(), invernadero=self.e.invernadero
        ).prioridad_orden)

    def test_regla_la_cosecha_guarda_su_variedad_y_su_capataz_y_es_una_orden(self):
        """Ficha de Cosecha: hija de `OrdenTrabajo` y de `ConCapataz`, con `variedad`; el código es `OT-{numero}`."""
        c = cosecha(self.e)
        self.assertEqual((c.variedad, c.capataz, c.tipo_orden), (self.e.variedad, self.e.capataz, "cosecha"))
        self.assertTrue(OrdenTrabajo.objects.filter(pk=c.pk, tipo_orden="cosecha").exists())
        self.assertEqual(c.codigo, f"OT-{c.numero:04d}")

    def test_regla_partida_ingreso_al_menos_uno(self):
        """Ficha de StockCosechado: `cantidad_ingreso_cosechado >= 1`."""
        viola(self, lambda: self.partida(cantidad_ingreso_cosechado=0))
        self.partida(cantidad_ingreso_cosechado=1, cantidad_disponible_cosechado=1)

    def test_regla_partida_disponible_no_negativo_y_puede_superar_al_ingreso(self):
        """Ficha: `cantidad_disponible_cosechado >= 0`; puede superar al ingreso (devolución, regla 29 de 8.6)."""
        self.partida(cantidad_disponible_cosechado=0, estado_stock_cosechado="agotado")
        self.assertEqual(self.partida(cantidad_ingreso_cosechado=10, cantidad_disponible_cosechado=12).cantidad_disponible_cosechado, 12)

    def test_regla_partida_costo_no_negativo(self):
        """Ficha: `costo_unitario_cosechado >= 0`."""
        viola(self, lambda: self.partida(costo_unitario_cosechado=Decimal("-0.0001")))
        self.partida(costo_unitario_cosechado=Decimal("0"))

    def test_regla_partida_agotada_implica_disponible_cero(self):
        """Ficha: `estado = agotado` ⇒ disponible 0."""
        viola(self, lambda: self.partida(estado_stock_cosechado="agotado", cantidad_disponible_cosechado=1))
        self.partida(estado_stock_cosechado="agotado", cantidad_disponible_cosechado=0)

    def test_regla_partida_estado_y_motivo_dentro_de_su_lista(self):
        """Ficha: estado y motivo dentro de sus listas."""
        viola(self, lambda: self.partida(estado_stock_cosechado="roto"))
        viola(self, lambda: self.partida(motivo_cosechado="inventado"))

    def test_regla_partida_se_muestra_como_p_id(self):
        """Ficha: se muestra como `P-{id}`."""
        partida = self.partida()
        self.assertEqual((partida.codigo, str(partida)), (f"P-{partida.pk}", f"P-{partida.pk}"))


class OrdenesDelCapatazTests(CosechaEnProduccionBase):
    """`ordenes_del_capataz` suma la cosecha (D-53, D-59); la bandeja, la lista y las cancelables no la muestran hasta COM-04a."""

    def test_regla_ordenes_del_capataz_incluye_la_cosecha(self):
        """Ficha de Cosecha: la unión de `ordenes_del_capataz` la incluye (la usan el traspaso y el aviso de baja de la cuenta)."""
        c = cosecha(self.e)
        filas = ordenes.ordenes_del_capataz(self.e.capataz)
        self.assertEqual([(f.orden_id, f.tipo_orden) for f in filas], [(c.pk, "cosecha")])
        self.assertIn("cosecha", filas[0].resumen)

    def test_regla_ordenes_del_capataz_no_hace_consultas_por_fila(self):
        """`ordenes_del_capataz` hace las mismas consultas con 1 y con 3 cosechas."""
        cosecha(self.e)
        con_una = consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz))
        cosecha(self.e, dias=1)
        cosecha(self.e, dias=2)
        con_tres = consultas(lambda: ordenes.ordenes_del_capataz(self.e.capataz))
        self.assertEqual(con_una, con_tres)

    def test_regla_la_bandeja_del_capataz_no_la_muestra_hasta_com_04a(self):
        """Ficha de Cosecha: la bandeja del Capataz no muestra cosechas hasta COM-04a."""
        cosecha(self.e)
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual((bandeja.vencidas, bandeja.hoy, bandeja.proximas), ([], [], []))

    def test_regla_la_lista_del_agronomo_no_la_muestra_hasta_com_04a(self):
        """Ficha de Cosecha: la lista de órdenes del Agrónomo no muestra cosechas hasta COM-04a (tampoco la del Gerente)."""
        cosecha(self.e)
        self.assertEqual(ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes()), [])

    def test_regla_las_cancelables_no_la_incluyen(self):
        """Ficha de Cosecha: las órdenes cancelables no incluyen cosechas (PRD-01: se cancelan desde `comercial`)."""
        cosecha(self.e)
        self.assertEqual(ordenes.ordenes_cancelables(self.e.agronomo), [])

    def test_regla_la_ventana_de_detalle_de_produccion_no_abre_una_cosecha(self):
        """Hasta COM-04a la cosecha no tiene ventana de detalle en `produccion`: 404 (como cualquier orden que no se muestra)."""
        from django.http import Http404

        c = cosecha(self.e)
        with self.assertRaises(Http404):
            ordenes.detalle_de_orden(self.e.agronomo, c.pk)

    def test_regla_el_aviso_de_baja_de_la_cuenta_del_capataz_la_cuenta(self):
        """Ficha de Cosecha: el aviso de baja de la cuenta del Capataz (`asignaciones_de_cuenta`) cuenta la cosecha «a realizar»."""
        cosecha(self.e)
        cosecha(self.e, estado="cancelada")
        asignaciones = registrantes.asignaciones_de_cuenta(self.e.capataz)
        self.assertEqual([a.cantidad for a in asignaciones], [1])


class TraspasoDelCapatazTests(CosechaEnProduccionBase):
    """El traspaso del Capataz (regla 3 de 8.22, D-53) actualiza `capataz` también en las cosechas «a realizar»."""

    def test_ext_traspasar_pasa_la_cosecha_a_realizar_al_capataz_nuevo(self):
        """D-59 y D-53: la cosecha «a realizar» pasa al Capataz entrante; la concretada y la cancelada no."""
        nuevo = crear_capataz_activo(email="nuevo@infoponia.com")
        pendiente = cosecha(self.e)
        cancelada = cosecha(self.e, estado="cancelada", dias=1)
        recibe = extensiones_de_maestros.contar_traspaso(self.e.invernadero, "capataz", self.e.capataz, nuevo)
        self.assertEqual(recibe, [("órdenes de trabajo a realizar", 1)])
        afectados = extensiones_de_maestros.traspasar(self.e.agronomo, self.e.invernadero, "capataz", self.e.capataz, nuevo)
        self.assertEqual([a.pk for a in afectados], [pendiente.pk])
        self.assertEqual(Cosecha.objects.get(pk=pendiente.pk).capataz_id, nuevo.pk)
        self.assertEqual(Cosecha.objects.get(pk=cancelada.pk).capataz_id, self.e.capataz.pk)


class ImpedimentosTests(CosechaEnProduccionBase):
    """Una cosecha «a realizar» impide la baja del invernadero y la de la variedad (D-59, punto 5)."""

    def test_ext_la_baja_del_invernadero_se_impide_con_una_cosecha_a_realizar(self):
        """PROD-BAJ-INV, precondición d: `ordenes_a_realizar` cuenta la cosecha (todas las órdenes «a realizar»)."""
        cosecha(self.e)
        self.assertIn("ordenes_a_realizar", [i.codigo for i in registrantes.impedimentos_de_baja_del_invernadero(self.e.invernadero)])

    def test_ext_la_baja_del_invernadero_no_se_impide_con_una_cosecha_cancelada(self):
        """Solo cuentan las «a realizar»."""
        cosecha(self.e, estado="cancelada")
        self.assertEqual(registrantes.impedimentos_de_baja_del_invernadero(self.e.invernadero), [])

    def test_ext_la_baja_de_la_variedad_se_impide_con_una_cosecha_a_realizar(self):
        """PROD-BAJ-VAR, precondición e: `ordenes_a_realizar` suma la cosecha de la variedad."""
        cosecha(self.e)
        impedimentos = registrantes.impedimentos_de_baja_de_variedad(self.e.variedad)
        self.assertEqual([i.codigo for i in impedimentos], ["ordenes_a_realizar"])
        self.assertIn("1 orden de trabajo a realizar", impedimentos[0].texto)

    def test_ext_el_uso_de_la_variedad_cuenta_cosechas_de_otra_variedad_aparte(self):
        """`uso_de_variedad` cuenta cada cosecha en la variedad que corresponde."""
        otra = invernadero_con_produccion(nombre="Otro", sufijo="2")
        cosecha(self.e)
        cosecha(otra)
        usos = registrantes.uso_de_variedad([self.e.variedad.pk, otra.variedad.pk])
        self.assertEqual((usos[self.e.variedad.pk].ordenes_a_realizar, usos[otra.variedad.pk].ordenes_a_realizar), (1, 1))


class PlantasComprometidasPorReservasTests(CosechaEnProduccionBase):
    """Condición 1 de la regla 15 de 8.8 (COM-02, D-59; «Diferencias», fila 8): lo reservado supera la cantidad actual del lote."""

    def merma(self, lote, cantidad, reservado, detalle=None):
        """Aplica una merma con `reservado` plantas reservadas en el lote (registrante falso) y devuelve su resultado."""
        with (
            mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", [lambda ids: {lote.pk: reservado}]),
            mock.patch.object(extensiones, "_DETALLE_DE_COSECHA", [lambda ids: detalle(ids) if detalle else {}]),
            transaction.atomic(),
        ):
            return mermas.aplicar_merma(
                lote, cantidad, "plaga", "", timezone.localdate(), self.e.agronomo
            )

    def test_regla_8_8_15_reservado_por_encima_de_lo_que_queda_genera_la_alerta(self):
        """Regla 15 de 8.8, condición 1: lo reservado (40) supera la cantidad actual que queda (30): alerta `produccion_plantas_comprometidas`
        con la cosecha afectada nombrada (extensión 10a: «qué órdenes de cosecha quedaron sin cobertura»), enlazada con la merma."""
        lote = lote_maduro(self.e, 50)
        c = cosecha(self.e)
        detalle = lambda ids: {c.pk: extensiones.DetalleDeCosecha("CV-0001", None, [(lote.pk, 40, None)])}  # noqa: E731
        resultado = self.merma(lote, 20, 40, detalle)
        alertas = [a for a in resultado.alertas if a.tipo_alerta == "produccion_plantas_comprometidas"]
        self.assertEqual(len(alertas), 1)
        self.assertIn(c.codigo, alertas[0].descripcion_alerta)
        self.assertIn("30 plantas", alertas[0].descripcion_alerta)
        self.assertTrue(AlertaDeMerma.objects.filter(merma=resultado.merma, alerta=alertas[0]).exists())

    def test_regla_8_8_15_reservado_que_entra_en_lo_que_queda_no_alerta(self):
        """Regla 15 de 8.8: si lo reservado (30) no supera lo que queda (30), no hay alerta de plantas comprometidas."""
        lote = lote_maduro(self.e, 50)
        resultado = self.merma(lote, 20, 30)
        self.assertEqual([a for a in resultado.alertas if a.tipo_alerta == "produccion_plantas_comprometidas"], [])
        self.assertFalse(Alerta.objects.filter(tipo_alerta="produccion_plantas_comprometidas").exists())

    def test_regla_8_8_15_sin_registrante_no_hay_alerta(self):
        """Sin registrante (nada reservado), la merma se comporta como antes de COM-02."""
        lote = lote_maduro(self.e, 50)
        with mock.patch.object(extensiones, "_RESERVADO_DE_LOTE", []), transaction.atomic():
            resultado = mermas.aplicar_merma(lote, 20, "plaga", "", timezone.localdate(), self.e.agronomo)
        self.assertEqual([a for a in resultado.alertas if a.tipo_alerta == "produccion_plantas_comprometidas"], [])

    def test_regla_8_8_15_una_orden_suelta_de_otro_tipo_no_cuenta_como_cosecha(self):
        """Solo las cosechas «a realizar» de la variedad y el invernadero se nombran; una entrega suelta no."""
        lote = lote_maduro(self.e, 50)
        orden_suelta(self.e.invernadero, "entrega")
        resultado = self.merma(lote, 20, 40)
        alertas = [a for a in resultado.alertas if a.tipo_alerta == "produccion_plantas_comprometidas"]
        self.assertEqual(len(alertas), 1)
        self.assertNotIn("OT-", alertas[0].descripcion_alerta)
