# Pruebas de los modelos de COM-06b (paso 1): el tipo `confirmacion_entrega` del `EnlaceCliente` (con su `entrega` y sin vencimiento guardado), el resultado de la averiguación de
# `AlertaComercial`, `Queja`, las fábricas nuevas y los invariantes de las quejas de `verificar_invariantes_de_solicitudes`. Una prueba por restricción de la base (la viola y no la viola).
# Fuente: docs/modelo/comercial.md («EnlaceCliente», «AlertaComercial», «Queja»), D-65, D-68 puntos 1, 5, 8 y 9 y docs/casos_de_uso/comercial/confirmacion.md.

import itertools
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial, ClausulaSuministrante, DetalleEntrega, EnlaceCliente, Queja, SolicitudRevision
from comercial.servicios import solicitudes
from comercial.tests.fabricas import (
    alerta_no_reconocida,
    cliente,
    compra_venta,
    detalle,
    detalle_suministro,
    enlace,
    enlace_de_confirmacion,
    entrega,
    escenario_comercial,
    marcar_concretada,
    queja,
    reserva_lista,
    suministro,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import OrigenDocumento
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_alerta
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
Tipo = EnlaceCliente.Tipo


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    """Un suministro con un período de 10 plantas (mínimo 8) y una compra-venta, cada uno con su reserva lista."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 500)
        cls.venta = compra_venta(cls.e)
        cls.detalle = detalle(cls.venta, cls.e.variedad, 50)
        cls.reserva = reserva_lista(cls.detalle, cls.lote, 50)
        cls.suministro = suministro(cls.e)
        cls.detalle_sum = detalle_suministro(cls.suministro, cls.e.variedad, cantidad=10, minima=8)
        cls.reserva_sum = reserva_lista(None, cls.lote, 10, fecha_entrega=cls.detalle_sum.fecha_primer_entrega, detalle_suministro=cls.detalle_sum)

    def entrega_de_suministro(self):
        """Una entrega de suministro del período de la clase, ya concretada (directo en la base)."""
        return marcar_concretada(entrega(self.suministro, [self.reserva_sum]))

    def otra_entrega_de_suministro(self):
        """Otra entrega concretada del mismo suministro, con el período siguiente (la reserva se crea una vez por prueba)."""
        if not hasattr(self, "_reserva_siguiente"):
            siguiente = self.detalle_sum.fecha_primer_entrega + timedelta(days=7)
            self._reserva_siguiente = reserva_lista(None, self.lote, 10, fecha_entrega=siguiente, detalle_suministro=self.detalle_sum)
        return marcar_concretada(entrega(self.suministro, [self._reserva_siguiente]))

    def rompe(self, texto, verificador=verificar_invariantes_de_solicitudes):
        with self.assertRaises(AssertionError) as c:
            verificador()
        self.assertIn(texto, str(c.exception))


# ---- EnlaceCliente: el tipo `confirmacion_entrega` ----


class EnlaceDeConfirmacionModeloTests(Base):
    def crear(self, **campos):
        """Un `EnlaceCliente` de confirmación crudo (token distinto en cada llamada) con los `campos` pisados."""
        valores = dict(tipo=Tipo.CONFIRMACION_ENTREGA, cliente=self.suministro.cliente, token_resumen=f"{next(self._serie):064d}")
        valores.update(campos)
        if "entrega" not in campos:
            valores["entrega"] = self.entrega_de_suministro()
        return EnlaceCliente.objects.create(**valores)

    def setUp(self):
        self._serie = itertools.count(1)

    def test_d68_1_el_tipo_confirmacion_entrega_es_valido_y_otro_no(self):
        """D-68 punto 1: `tipo` es `decision_faltante` o `confirmacion_entrega`; cualquier otro lo rechaza la base."""
        self.assertEqual(self.crear().tipo, "confirmacion_entrega")
        viola(self, lambda: self.crear(tipo="aviso", entrega=self.otra_entrega_de_suministro()))

    def test_regla_la_confirmacion_exige_la_entrega_y_ninguna_venta(self):
        """Modelo, «EnlaceCliente»: `tipo = confirmacion_entrega` ⇔ `entrega` no nula y `compra_venta` nula."""
        viola(self, lambda: self.crear(entrega=None))
        viola(self, lambda: self.crear(compra_venta=self.venta))

    def test_regla_la_decision_de_faltante_no_lleva_entrega(self):
        """Modelo, «EnlaceCliente»: `entrega` no nula solo en `confirmacion_entrega`: un faltante con entrega se rechaza."""
        viola(self, lambda: self.crear(tipo=Tipo.DECISION_FALTANTE, compra_venta=self.venta, fecha_vencimiento=HOY))

    def test_regla_el_vencimiento_se_guarda_solo_en_el_faltante(self):
        """D-68 punto 8: `decision_faltante` ⇔ `fecha_vencimiento` no nula; la confirmación la calcula y la deja nula."""
        viola(self, lambda: self.crear(fecha_vencimiento=HOY))
        viola(self, lambda: self.crear(tipo=Tipo.DECISION_FALTANTE, entrega=None, compra_venta=self.venta, fecha_vencimiento=None))
        self.assertEqual(enlace(self.venta)[0].tipo, "decision_faltante")  # la fábrica del faltante sigue guardando su vencimiento
        self.assertIsNone(self.crear().fecha_vencimiento)

    def test_regla_uno_por_entrega_y_sin_reemplazo(self):
        """Regla «Enlace de confirmación»: único `(entrega)` en este tipo, en cualquier estado (no hay reemplazo: la base lo impide); otra entrega sí puede tener el suyo."""
        entrega_ = self.entrega_de_suministro()
        self.crear(entrega=entrega_)
        viola(self, lambda: self.crear(entrega=entrega_))
        viola(self, lambda: self.crear(entrega=entrega_, estado="reemplazado"))
        self.assertIsNotNone(self.crear(entrega=self.otra_entrega_de_suministro()).pk)

    def test_regla_la_fabrica_guarda_el_resumen_y_nunca_el_token_y_usado_exige_fecha_de_uso(self):
        """D-65 punto 2 y modelo: la fábrica guarda solo el SHA-256 (64 caracteres); `usado` ⇔ `fecha_uso`."""
        entrega_ = self.entrega_de_suministro()
        creado, token = enlace_de_confirmacion(entrega_)
        self.assertEqual((len(creado.token_resumen), creado.estado, creado.entrega_id, creado.compra_venta_id), (64, "vigente", entrega_.pk, None))
        self.assertNotEqual(creado.token_resumen, token)
        usado, _ = enlace_de_confirmacion(self.otra_entrega_de_suministro(), estado="usado")
        self.assertIsNotNone(usado.fecha_uso)
        viola(self, lambda: self.crear(entrega=self.otra_entrega_de_suministro(), estado="usado"))

    def test_str_nombra_la_entrega(self):
        """El texto del enlace de confirmación lleva el código de la entrega (el del faltante, el de la venta)."""
        entrega_ = self.entrega_de_suministro()
        self.assertEqual(str(enlace_de_confirmacion(entrega_)[0]), f"Enlace de {entrega_.codigo} (vigente)")
        self.assertEqual(str(enlace(self.venta)[0]), f"Enlace de {self.venta.codigo} (vigente)")


# ---- AlertaComercial: el resultado de la averiguación ----


class ResultadoDeLaAveriguacionModeloTests(Base):
    def vinculo(self, entrega_=None, **campos):
        """Una `AlertaComercial` de la entrega (o la que pida `campos`) con una alerta nueva de `maestros`."""
        valores = dict(alerta=crear_alerta(self.e.invernadero, "comercial_entrega_no_reconocida"))
        valores.update(campos)
        if "entrega" not in campos:
            valores["entrega"] = entrega_ or self.entrega_de_suministro()
        return AlertaComercial.objects.create(**valores)

    def test_d68_9_el_resultado_es_de_su_lista(self):
        """MD-137: `resultado_averiguacion` es `llego`, `no_llego_perdido`, `no_llego_devuelto` o nulo; otro valor lo rechaza la base."""
        for resultado in ("llego", "no_llego_perdido", "no_llego_devuelto"):
            self.assertEqual(self.vinculo(resultado_averiguacion=resultado, descripcion_averiguacion="Habló con el cliente.").resultado_averiguacion, resultado)
        viola(self, lambda: self.vinculo(resultado_averiguacion="perdido", descripcion_averiguacion="x"))

    def test_d68_9_resultado_si_y_solo_si_hay_descripcion(self):
        """MD-137: `resultado_averiguacion` no nulo ⇔ `descripcion_averiguacion` no vacía."""
        viola(self, lambda: self.vinculo(resultado_averiguacion="llego"))
        viola(self, lambda: self.vinculo(descripcion_averiguacion="Sin resultado no hay descripción."))
        sin_resultado = self.vinculo()
        self.assertEqual((sin_resultado.resultado_averiguacion, sin_resultado.descripcion_averiguacion), (None, ""))

    def test_d68_9_el_resultado_solo_va_en_la_alerta_de_una_entrega(self):
        """MD-137: `resultado_averiguacion` no nulo ⇒ `entrega` no nula (el vínculo de una solicitud no lo lleva)."""
        entrega_ = self.entrega_de_suministro()
        queja_ = queja(entrega_, con_alerta=False)
        viola(self, lambda: self.vinculo(entrega=None, solicitud=queja_, resultado_averiguacion="llego", descripcion_averiguacion="x"))
        self.assertIsNotNone(self.vinculo(entrega=None, solicitud=queja_).pk)

    def test_fabrica_la_alerta_no_reconocida_es_critica_y_tiene_un_solo_origen(self):
        """La fábrica deja la alerta crítica del Gerente con su `AlertaComercial(entrega=…)`; la restricción de «exactamente un origen» sigue valiendo."""
        entrega_ = self.entrega_de_suministro()
        alerta = alerta_no_reconocida(entrega_, "No llegó nada a la sucursal.")
        self.assertEqual((alerta.nivel_severidad, alerta.para_gerente, alerta.estado_alerta), ("critica", True, "activa"))
        self.assertEqual(alerta.vinculo_comercial.entrega_id, entrega_.pk)
        self.assertIn("No llegó nada a la sucursal.", alerta.descripcion_alerta)
        self.assertEqual(alerta_no_reconocida(self.otra_entrega_de_suministro(), resuelta=True).estado_alerta, "resuelta")


# ---- Queja ----


class QuejaModeloTests(Base):
    def crear(self, entrega_=None, **campos):
        """Una `Queja` cruda creada con `crear_solicitud` (el número y la entrega las escribe una sola función) con los `campos` pisados."""
        entrega_ = entrega_ or self.entrega_de_suministro()
        valores = dict(tipo_queja="estado_mercaderia", motivo_queja="Llegó golpeado.", cliente=entrega_.contrato_entrega.cliente)
        valores.update(campos)
        return solicitudes.crear_solicitud(Queja, entrega_, **valores)

    def test_d68_5_la_queja_es_una_solicitud_pendiente_con_su_tipo_fijado_por_la_hija(self):
        """D-68 punto 5: la hija fija `tipo_solicitud = queja`; es un documento de origen `solicitud_revision`; nace «pendiente», sin Gerente ni monto."""
        q = self.crear()
        self.assertEqual(SolicitudRevision.objects.get(pk=q.pk).tipo_solicitud, "queja")
        self.assertEqual(OrigenDocumento.objects.get(pk=q.pk).tipo, "solicitud_revision")
        self.assertEqual((q.estado_solicitud, q.gerente_id, q.monto_indemnizacion, q.fecha_solicitud, q.codigo), ("pendiente", None, None, HOY, f"SR-{q.numero:04d}"))

    def test_regla_el_tipo_de_queja_es_de_su_lista(self):
        """Modelo, «Queja»: `tipo_queja` es `estado_mercaderia`, `retraso` u `otro`."""
        viola(self, lambda: self.crear(tipo_queja="faltante"))
        for tipo in ("estado_mercaderia", "retraso", "otro"):
            self.assertEqual(self.crear(self.otra_entrega_de_suministro(), tipo_queja=tipo).tipo_queja, tipo)

    def test_regla_el_motivo_es_obligatorio_salvo_en_retraso(self):
        """Modelo, «Queja»: `tipo_queja <> retraso` ⇒ `motivo_queja` no vacío (regla «Motivo de la queja»); en «retraso» es opcional."""
        viola(self, lambda: self.crear(motivo_queja=""))
        viola(self, lambda: self.crear(tipo_queja="otro", motivo_queja=""))
        self.assertEqual(self.crear(tipo_queja="retraso", motivo_queja="").motivo_queja, "")

    def test_r118_y_r156_el_cliente_y_los_detalles_con_sus_nombres_inversos(self):
        """R118 (`Cliente.quejas`) y R156 (`DetalleEntrega.quejas`)."""
        entrega_ = self.entrega_de_suministro()
        q = queja(entrega_)
        linea = entrega_.lineas.get()
        self.assertEqual(list(q.detalles.all()), [linea])
        self.assertEqual(list(linea.quejas.all()), [q])
        self.assertEqual(list(entrega_.contrato_entrega.cliente.quejas.all()), [q])

    def test_la_discrepancia_y_varias_quejas_conviven_en_una_entrega(self):
        """Regla 3 de 8.14 es solo de la discrepancia: una entrega admite una queja de cada tipo (el límite «una por tipo» es de la respuesta y del invariante, no de la base)."""
        entrega_ = self.entrega_de_suministro()
        for tipo in ("estado_mercaderia", "retraso", "otro"):
            queja(entrega_, tipo)
        self.assertEqual(Queja.objects.filter(entrega=entrega_).count(), 3)

    def test_fabrica_queja_deja_su_alerta_y_su_vinculo(self):
        """La fábrica deja la alerta `comercial_queja` con su `AlertaComercial(solicitud=…)`, y los invariantes de solicitudes no encuentran nada roto."""
        q = queja(self.entrega_de_suministro())
        self.assertEqual(AlertaComercial.objects.filter(solicitud=q).count(), 1)
        verificar_invariantes_de_solicitudes()


# ---- los invariantes de las quejas ----


class InvariantesDeQuejasTests(Base):
    def test_invariante_una_queja_sin_detalles_rompe(self):
        entrega_ = self.entrega_de_suministro()
        q = queja(entrega_)
        verificar_invariantes_de_solicitudes()
        q.detalles.clear()
        self.rompe(f"{q.codigo}: sin detalles")

    def test_invariante_un_detalle_de_otra_entrega_rompe(self):
        q = queja(self.entrega_de_suministro())
        q.detalles.set(self.otra_entrega_de_suministro().lineas.all())
        self.rompe("es de otra entrega")

    def test_invariante_el_cliente_es_el_del_contrato(self):
        entrega_ = self.entrega_de_suministro()
        q = queja(entrega_)
        otro = cliente()
        Queja.objects.filter(pk=q.pk).update(cliente=otro)
        self.rompe("de un cliente que no es el del contrato")

    def test_invariante_a_lo_sumo_una_queja_por_tipo_en_cada_entrega(self):
        entrega_ = self.entrega_de_suministro()
        queja(entrega_, "otro")
        verificar_invariantes_de_solicitudes()
        queja(entrega_, "otro")
        self.rompe("2 quejas de tipo otro")

    def test_invariante_la_queja_por_retraso_solo_con_detalles_con_retraso(self):
        entrega_ = self.entrega_de_suministro()  # el período es dentro de 3 días: llegó antes de tiempo
        queja(entrega_, "retraso")
        self.rompe("no llegó con retraso")
        DetalleEntrega.objects.filter(entrega=entrega_).update(fecha_periodo=HOY - timedelta(days=5))
        ClausulaSuministrante.objects.filter(detalle=self.detalle_sum).update(plazo_entrega_dias=1)
        verificar_invariantes_de_solicitudes()  # 5 días − 1 de plazo: 4 de retraso
        ClausulaSuministrante.objects.filter(detalle=self.detalle_sum).update(plazo_entrega_dias=5)  # el límite: sin retraso
        self.rompe("no llegó con retraso")

    def test_invariante_la_queja_sin_su_alerta_rompe(self):
        queja(self.entrega_de_suministro(), con_alerta=False)
        self.rompe("0 alertas")
