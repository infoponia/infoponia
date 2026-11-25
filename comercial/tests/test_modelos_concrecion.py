# Pruebas de los modelos de COM-06a (paso 1): los campos de la concreción de `Entrega` y `DetalleEntrega`, `PagoCliente`, `IntentoFallido`, `SolicitudRevision`, `DiscrepanciaEntrega`,
# `LineaDiscrepancia` y `AlertaComercial.solicitud`, una por restricción de la base (la viola y no la viola); la función `crear_solicitud`; las fábricas de la concreción y los
# invariantes nuevos de `verificar_invariantes_de_entregas` y `verificar_invariantes_de_solicitudes` (que detectan lo que la base no puede vigilar).
# Fuente: docs/modelo/comercial.md («Entrega», «DetalleEntrega», «PagoCliente», «IntentoFallido», «SolicitudRevision», «DiscrepanciaEntrega y LineaDiscrepancia», «AlertaComercial») y D-68 puntos 4 a 7.

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import (
    AlertaComercial,
    CompraVenta,
    DetalleEntrega,
    DiscrepanciaEntrega,
    Entrega,
    IntentoFallido,
    LineaDiscrepancia,
    PagoCliente,
    SolicitudRevision,
)
from comercial.servicios import solicitudes
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    discrepancia,
    entrega,
    entrega_concretada,
    escenario_comercial,
    marcar_concretada,
    pago_de_compra_venta,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad.models import OrigenDocumento
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_alerta
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    """Una venta con una entrega de 50 plantas y un suministro con un período de 10."""

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

    def entrega_de_venta(self, **extra):
        """Una entrega de la venta de la clase (a realizar, con envío, sin transportista)."""
        return entrega(self.venta, [self.reserva], **extra)

    def entrega_de_suministro(self, **extra):
        return entrega(self.suministro, [self.reserva_sum], **extra)


# ---- Entrega y DetalleEntrega ----


class RestriccionesDeLaConcrecionTests(Base):
    def test_regla_el_monto_total_de_la_entrega_no_es_negativo(self):
        """Modelo, «Entrega»: `monto_total_entrega` nulo o `>= 0`."""
        e = self.entrega_de_venta()
        viola(self, lambda: Entrega.objects.filter(pk=e.pk).update(monto_total_entrega=Decimal("-0.01")))
        Entrega.objects.filter(pk=e.pk).update(monto_total_entrega=Decimal("0.00"))
        self.assertEqual(Entrega.objects.get(pk=e.pk).monto_total_entrega, Decimal("0.00"))

    def test_regla_una_linea_se_concreta_entera_o_no_se_concreta(self):
        """Modelo, «DetalleEntrega»: entregada, perdida, devuelta y monto, las cuatro nulas o las cuatro no nulas."""
        linea = self.entrega_de_venta().lineas.get()
        for parcial in (
            {"cant_entregada": 1},
            {"cant_entregada": 1, "cant_perdida": 0},
            {"cant_entregada": 1, "cant_perdida": 0, "cant_devuelta": 0},
            {"cant_perdida": 0, "cant_devuelta": 0, "monto_pagar": Decimal("1.00")},
        ):
            viola(self, lambda parcial=parcial: DetalleEntrega.objects.filter(pk=linea.pk).update(**parcial))
        DetalleEntrega.objects.filter(pk=linea.pk).update(cant_entregada=50, cant_perdida=0, cant_devuelta=0, monto_pagar=Decimal("5000.00"))
        self.assertEqual(DetalleEntrega.objects.get(pk=linea.pk).cant_perdida, 0)

    def test_regla_las_cantidades_y_el_monto_de_una_linea_no_son_negativos(self):
        """Modelo, «DetalleEntrega»: las tres cantidades y `monto_pagar` son `>= 0`."""
        linea = self.entrega_de_venta().lineas.get()
        completa = dict(cant_entregada=1, cant_perdida=1, cant_devuelta=1, monto_pagar=Decimal("1.00"))
        for campo, valor in (("cant_entregada", -1), ("cant_perdida", -1), ("cant_devuelta", -1), ("monto_pagar", Decimal("-0.01"))):
            viola(self, lambda campo=campo, valor=valor: DetalleEntrega.objects.filter(pk=linea.pk).update(**{**completa, campo: valor}))
        DetalleEntrega.objects.filter(pk=linea.pk).update(**completa)

    def test_la_fabrica_de_una_concretada_deja_los_datos_que_exigen_la_base_y_los_invariantes(self):
        """`entrega(estado="concretada")` y `marcar_concretada` cargan las cuatro columnas de cada línea, el total y, en un suministro, el vencimiento (plazo de la cláusula)."""
        de_venta = self.entrega_de_venta(estado="concretada")
        self.assertEqual((de_venta.monto_total_entrega, de_venta.fecha_vencimiento_pago), (Decimal("5000.00"), None))
        linea = de_venta.lineas.get()
        self.assertEqual((linea.cant_entregada, linea.cant_perdida, linea.cant_devuelta, linea.monto_pagar), (50, 0, 0, Decimal("5000.00")))
        de_suministro = marcar_concretada(self.entrega_de_suministro(), cantidades=[(8, 1, 1)])
        self.assertEqual(de_suministro.estado_orden, "concretada")
        self.assertEqual(de_suministro.fecha_vencimiento_pago, HOY + timedelta(days=15))
        verificar_invariantes_de_entregas()


# ---- PagoCliente ----


class RestriccionesDePagoClienteTests(Base):
    def pago(self, **campos):
        valores = dict(cliente=self.venta.cliente, compra_venta=self.venta, medio_pago="efectivo", fecha_pago=HOY, monto_pagado=Decimal("5000.00"))
        valores.update(campos)
        return PagoCliente.objects.create(**valores)

    def test_d68_4_un_pago_es_un_documento_de_origen_de_tipo_pago_cliente(self):
        """D-68 punto 4: hija directa de `OrigenDocumento` con `tipo = pago_cliente`; nace «vigente»."""
        p = self.pago()
        self.assertEqual(OrigenDocumento.objects.get(pk=p.pk).tipo, "pago_cliente")
        self.assertEqual(p.estado_pago, "vigente")
        self.assertEqual(self.venta.pagos.get().pk, p.pk)

    def test_regla_el_monto_pagado_es_mayor_que_cero(self):
        """Modelo, «PagoCliente»: `monto_pagado > 0`."""
        viola(self, lambda: self.pago(monto_pagado=Decimal("0.00")))
        viola(self, lambda: self.pago(monto_pagado=Decimal("-1.00")))
        self.assertEqual(self.pago(monto_pagado=Decimal("0.01")).monto_pagado, Decimal("0.01"))

    def test_regla_el_medio_de_pago_es_de_la_lista(self):
        """Regla 15 de 8.13: efectivo, transferencia, tarjeta de débito o tarjeta de crédito."""
        viola(self, lambda: self.pago(medio_pago="cheque"))
        for medio in ("transferencia", "tarjeta_debito", "tarjeta_credito"):
            otra = compra_venta(self.e)
            self.assertEqual(self.pago(compra_venta=otra, medio_pago=medio).medio_pago, medio)

    def test_regla_el_estado_del_pago_es_vigente_o_anulado(self):
        """MD-136: `estado_pago` es `vigente` o `anulado`."""
        viola(self, lambda: self.pago(estado_pago="pendiente"))

    def test_c7_en_com_06a_el_pago_es_de_una_compra_venta(self):
        """C7 (COM-06a): `compra_venta` no nula."""
        viola(self, lambda: self.pago(compra_venta=None))

    def test_regla_una_venta_se_paga_una_vez_pero_conserva_el_pago_anulado(self):
        """Modelo: único `(compra_venta)` con `estado_pago = vigente`; uno anulado no cuenta (COM-08b registra el correcto)."""
        self.pago()
        viola(self, lambda: self.pago())
        self.pago(estado_pago="anulado")
        self.pago(estado_pago="anulado")
        self.assertEqual(self.venta.pagos.count(), 3)


# ---- IntentoFallido ----


class RestriccionesDeIntentoFallidoTests(Base):
    def intento(self, **campos):
        t = transportista_con_vehiculo(self.e.invernadero)
        valores = dict(entrega=self.entrega_de_venta(transportista=t), transportista=t, fecha_programada=HOY, motivo="cliente_ausente")
        valores.update(campos)
        return IntentoFallido.objects.create(**valores)

    def test_regla_el_motivo_es_de_la_lista_de_4a(self):
        """«Lista de tecnología», 4a de COM-CNC-ENT: cliente ausente, domicilio cerrado, dirección incorrecta u otro."""
        viola(self, lambda: self.intento(motivo="llovia"))
        for motivo in ("cliente_ausente", "domicilio_cerrado", "direccion_incorrecta", "otro"):
            self.assertEqual(IntentoFallido.objects.get(pk=self.intento(motivo=motivo).pk).motivo, motivo)

    def test_d68_6_el_intento_guarda_la_entrega_el_transportista_y_la_fecha_que_tenia(self):
        """D-68 punto 6: una entrega tiene varios intentos; la descripción es opcional y la hora es la del registro."""
        i = self.intento(descripcion="Tocamos timbre")
        self.assertEqual((i.fecha_programada, i.descripcion), (HOY, "Tocamos timbre"))
        self.assertIsNotNone(i.fecha_hora)
        self.assertEqual(self.intento().descripcion, "")
        self.assertEqual(i.entrega.intentos_fallidos.count(), 1)


# ---- SolicitudRevision, DiscrepanciaEntrega y LineaDiscrepancia ----


class RestriccionesDeSolicitudTests(Base):
    def solicitud(self, entrega_=None, **campos):
        """Una `SolicitudRevision` cruda (el padre), con lo mínimo y los `campos` pisados."""
        valores = dict(entrega=entrega_ or marcar_concretada(self.entrega_de_suministro()), tipo_solicitud="discrepancia", numero=solicitudes.siguiente_numero())
        valores.update(campos)
        return SolicitudRevision.objects.create(**valores)

    def test_d68_5_la_solicitud_es_un_documento_de_origen_y_nace_pendiente_sin_gerente(self):
        """D-68 punto 5: `tipo = solicitud_revision` en el padre; nace «pendiente», sin fecha de resolución, sin Gerente y sin monto."""
        s = self.solicitud()
        self.assertEqual(OrigenDocumento.objects.get(pk=s.pk).tipo, "solicitud_revision")
        self.assertEqual((s.estado_solicitud, s.fecha_resolucion, s.gerente_id, s.monto_indemnizacion), ("pendiente", None, None, None))
        self.assertEqual(s.codigo, f"SR-{s.numero:04d}")

    def test_regla_3_de_8_14_una_sola_discrepancia_por_entrega(self):
        """Regla 3 de 8.14: único `(entrega)` con `tipo_solicitud = discrepancia`; otra entrega sí puede tener la suya; un tipo `queja` (COM-06b) no cuenta."""
        e1 = marcar_concretada(self.entrega_de_suministro())
        self.solicitud(e1)
        viola(self, lambda: self.solicitud(e1))
        self.solicitud(e1, tipo_solicitud="queja")
        self.solicitud(e1, tipo_solicitud="queja")

    def test_regla_el_numero_de_solicitud_es_unico(self):
        """Modelo, «SolicitudRevision»: `numero` único (el código «SR-0012» que ven el Gerente y el cliente)."""
        s = self.solicitud(marcar_concretada(self.entrega_de_suministro()), tipo_solicitud="queja")
        viola(self, lambda: self.solicitud(s.entrega, tipo_solicitud="queja", numero=s.numero))

    def test_regla_el_tipo_y_el_estado_son_de_su_lista(self):
        """Modelo: `tipo_solicitud` es `discrepancia` o `queja`; `estado_solicitud`, `pendiente`, `aceptada` o `rechazada`."""
        viola(self, lambda: self.solicitud(tipo_solicitud="reclamo"))
        viola(self, lambda: self.solicitud(estado_solicitud="anulada"))

    def test_regla_pendiente_si_y_solo_si_no_hay_fecha_de_resolucion_ni_gerente(self):
        """Modelo: `estado = pendiente` ⇔ `fecha_resolucion` nula ⇔ `gerente` nulo."""
        gerente = crear_gerente()
        viola(self, lambda: self.solicitud(fecha_resolucion=HOY))
        viola(self, lambda: self.solicitud(gerente=gerente))
        viola(self, lambda: self.solicitud(estado_solicitud="rechazada"))
        viola(self, lambda: self.solicitud(estado_solicitud="rechazada", fecha_resolucion=HOY))
        self.assertEqual(self.solicitud(estado_solicitud="rechazada", fecha_resolucion=HOY, gerente=gerente, tipo_solicitud="queja").estado_solicitud, "rechazada")

    def test_regla_aceptada_exige_un_monto_y_un_monto_exige_aceptada(self):
        """Modelo: `estado = aceptada` ⇒ `monto_indemnizacion` no nulo y `>= 0`; `monto_indemnizacion` no nulo ⇒ `estado = aceptada`."""
        gerente = crear_gerente()
        resuelta = dict(fecha_resolucion=HOY, gerente=gerente, tipo_solicitud="queja")
        viola(self, lambda: self.solicitud(estado_solicitud="aceptada", **resuelta))
        viola(self, lambda: self.solicitud(estado_solicitud="aceptada", monto_indemnizacion=Decimal("-1.00"), **resuelta))
        viola(self, lambda: self.solicitud(estado_solicitud="rechazada", monto_indemnizacion=Decimal("10.00"), **resuelta))
        viola(self, lambda: self.solicitud(monto_indemnizacion=Decimal("10.00")))
        # COM-07a (D-69 punto 9): una aceptada también lleva lo descontado y lo reintegrado (antes de COM-07a bastaba el monto).
        aceptada = self.solicitud(estado_solicitud="aceptada", monto_indemnizacion=Decimal("0.00"), monto_descontado=Decimal("0.00"), monto_reintegrado=Decimal("0.00"), **resuelta)
        self.assertEqual(aceptada.monto_indemnizacion, Decimal("0.00"))


class CrearSolicitudTests(Base):
    def test_crear_solicitud_asigna_numero_entrega_tipo_y_fecha(self):
        """D-68 punto 5: la única función que escribe `entrega` y `numero`; el tipo lo fija la hija; los números son consecutivos."""
        e1 = marcar_concretada(self.entrega_de_suministro())
        d = solicitudes.crear_solicitud(DiscrepanciaEntrega, e1)
        self.assertEqual((d.entrega_id, d.tipo_solicitud, d.estado_solicitud, d.fecha_solicitud), (e1.pk, "discrepancia", "pendiente", HOY))
        self.assertEqual(solicitudes.siguiente_numero(), d.numero + 1)
        self.assertEqual(SolicitudRevision.objects.get(pk=d.pk).tipo_solicitud, "discrepancia")

    def test_crear_solicitud_sin_transaccion_falla(self):
        """Corre dentro de la transacción del caso de uso: sin ella, `RuntimeError`."""
        with self.assertRaises(RuntimeError), self._sin_transaccion():
            solicitudes.crear_solicitud(DiscrepanciaEntrega, None)

    def test_crear_solicitud_rechaza_una_clase_que_no_es_hija(self):
        with self.assertRaises(TypeError):
            solicitudes.crear_solicitud(PagoCliente, None)

    @staticmethod
    def _sin_transaccion():
        """Un contexto que simula el autocommit (fuera de una transacción) para la verificación de `crear_solicitud`."""
        from unittest import mock

        return mock.patch("comercial.servicios.solicitudes.transaction.get_autocommit", return_value=True)


class RestriccionesDeLineaDeDiscrepanciaTests(Base):
    def setUp(self):
        self.entrega_ = marcar_concretada(self.entrega_de_suministro(), cantidades=[(5, 5, 0)])
        self.disc = solicitudes.crear_solicitud(DiscrepanciaEntrega, self.entrega_)
        self.linea_entrega = self.entrega_.lineas.get()

    def linea(self, **campos):
        valores = dict(discrepancia=self.disc, detalle_entrega=self.linea_entrega, cantidad_entregada=5, cantidad_minima_estipulada=8)
        valores.update(campos)
        return LineaDiscrepancia.objects.create(**valores)

    def test_regla_la_linea_existe_porque_queda_por_debajo_del_minimo(self):
        """Modelo: `cantidad_entregada < cantidad_minima_estipulada`."""
        viola(self, lambda: self.linea(cantidad_entregada=8))
        viola(self, lambda: self.linea(cantidad_entregada=9))
        self.assertEqual(self.linea(cantidad_entregada=7).cantidad_entregada, 7)

    def test_regla_la_minima_estipulada_es_al_menos_uno(self):
        """Modelo: `cantidad_minima_estipulada >= 1`."""
        viola(self, lambda: self.linea(cantidad_entregada=0, cantidad_minima_estipulada=0))
        self.assertEqual(self.linea(cantidad_entregada=0, cantidad_minima_estipulada=1).cantidad_minima_estipulada, 1)

    def test_regla_el_monto_de_la_linea_es_nulo_o_no_negativo(self):
        """Modelo: `monto_indemnizacion_linea` nulo o `>= 0` (lo carga COM-07a)."""
        viola(self, lambda: self.linea(monto_indemnizacion_linea=Decimal("-1.00")))
        self.assertIsNone(self.linea().monto_indemnizacion_linea)

    def test_r163_una_linea_de_entrega_se_evalua_en_a_lo_sumo_una_linea_de_discrepancia(self):
        """R163: `detalle_entrega` es único (`OneToOne`)."""
        self.linea()
        viola(self, lambda: self.linea())
        self.assertEqual(self.linea_entrega.linea_de_discrepancia.discrepancia_id, self.disc.pk)


# ---- AlertaComercial.solicitud ----


class AlertaDeSolicitudTests(Base):
    def alerta(self, **origen):
        return AlertaComercial.objects.create(alerta=crear_alerta(self.e.invernadero, "comercial_discrepancia_entrega"), **origen)

    def setUp(self):
        self.entrega_ = marcar_concretada(self.entrega_de_suministro())
        self.disc = solicitudes.crear_solicitud(DiscrepanciaEntrega, self.entrega_)

    def test_d63_la_alerta_de_una_solicitud_tiene_ese_unico_origen(self):
        """D-63 punto 1 con cinco orígenes: `solicitud` sola vale; `solicitud` con otro origen, o ninguno, se rechazan."""
        self.assertEqual(self.alerta(solicitud=self.disc).solicitud_id, self.disc.pk)
        viola(self, lambda: self.alerta(solicitud=self.disc, entrega=self.entrega_))
        viola(self, lambda: self.alerta(solicitud=self.disc, suministro=self.suministro))
        viola(self, lambda: self.alerta())

    def test_los_otros_cuatro_origenes_siguen_valiendo_solos(self):
        """La restricción reescrita con cinco orígenes no rompe los de COM-03 a COM-05a1."""
        self.assertIsNotNone(self.alerta(entrega=self.entrega_).pk)
        self.assertIsNotNone(self.alerta(suministro=self.suministro).pk)

    def test_d68_5_una_sola_alerta_por_solicitud(self):
        """D-68 punto 5: único `(solicitud)` con `solicitud` no nula; otra solicitud sí puede tener la suya."""
        self.alerta(solicitud=self.disc)
        viola(self, lambda: self.alerta(solicitud=self.disc))
        siguiente = self.detalle_sum.fecha_primer_entrega + timedelta(days=7)
        reserva_siguiente = reserva_lista(None, self.lote, 10, fecha_entrega=siguiente, detalle_suministro=self.detalle_sum)
        otra = solicitudes.crear_solicitud(DiscrepanciaEntrega, marcar_concretada(entrega(self.suministro, [reserva_siguiente])))
        self.assertIsNotNone(self.alerta(solicitud=otra).pk)


# ---- los invariantes nuevos ----


class InvariantesDeLaConcrecionTests(Base):
    def test_una_entrega_concretada_bien_armada_cumple_los_invariantes(self):
        """La compra-venta con su pago y el suministro con su discrepancia, armados por las fábricas, cumplen los dos verificadores."""
        entrega_concretada(self.venta, [self.reserva], con_pago=True)
        d = discrepancia(entrega_concretada(self.suministro, [self.reserva_sum], cantidades=[(5, 5, 0)]))
        self.assertEqual(d.lineas.count(), 1)
        pago_otra = compra_venta(self.e)
        self.assertEqual(pago_de_compra_venta(pago_otra).monto_pagado, Decimal("100.00"))
        verificar_invariantes_de_entregas()
        verificar_invariantes_de_solicitudes()

    def rompe(self, texto, verificador=verificar_invariantes_de_entregas):
        with self.assertRaises(AssertionError) as c:
            verificador()
        self.assertIn(texto, str(c.exception))

    def test_invariante_el_monto_total_y_el_vencimiento_solo_en_una_concretada(self):
        """Una «a realizar» con monto total, o un suministro concretado sin vencimiento, rompen el invariante."""
        e1 = self.entrega_de_venta()
        Entrega.objects.filter(pk=e1.pk).update(monto_total_entrega=Decimal("1.00"))
        self.rompe("monto total")
        Entrega.objects.filter(pk=e1.pk).update(monto_total_entrega=None)
        e2 = marcar_concretada(self.entrega_de_suministro())
        verificar_invariantes_de_entregas()
        Entrega.objects.filter(pk=e2.pk).update(fecha_vencimiento_pago=None)
        self.rompe("vencimiento del pago")

    def test_invariante_el_total_es_la_suma_de_las_lineas_y_el_monto_es_entregada_por_precio(self):
        e1 = marcar_concretada(self.entrega_de_venta())
        Entrega.objects.filter(pk=e1.pk).update(monto_total_entrega=Decimal("1.00"))
        self.rompe("suma de los montos")
        Entrega.objects.filter(pk=e1.pk).update(monto_total_entrega=Decimal("5000.00"))
        DetalleEntrega.objects.filter(entrega=e1).update(monto_pagar=Decimal("5000.00"), cant_entregada=49, cant_devuelta=0, cant_perdida=1)
        self.rompe("entregada × precio")

    def test_invariante_una_linea_aceptada_de_una_venta_no_tiene_devueltas(self):
        """El cliente acepta todo lo que llegó o lo rechaza todo (7a): entregada > 0 con devuelta > 0 rompe."""
        e1 = marcar_concretada(self.entrega_de_venta(), cantidades=[(30, 0, 20)])
        self.rompe("devueltas")
        self.assertEqual(e1.monto_total_entrega, Decimal("3000.00"))

    def test_invariante_una_venta_concretada_tiene_un_pago_vigente_por_el_total(self):
        entrega_concretada(self.venta, [self.reserva], con_pago=True)
        verificar_invariantes_de_entregas()
        PagoCliente.objects.filter(compra_venta=self.venta).update(monto_pagado=Decimal("1.00"))
        self.rompe("no es el total")
        PagoCliente.objects.filter(compra_venta=self.venta).update(estado_pago="anulado")
        self.rompe("0 pagos vigentes")

    def test_invariante_una_venta_cancelada_sin_entregas_concretadas_no_tiene_pago(self):
        otra = compra_venta(self.e, estado="cancelada")
        pago_de_compra_venta(otra)
        self.rompe("cancelada sin entregas concretadas")

    def test_invariante_de_solicitudes_la_entrega_es_de_un_suministro_concretado_con_una_alerta(self):
        d = discrepancia(marcar_concretada(self.entrega_de_suministro(), cantidades=[(5, 5, 0)]))
        verificar_invariantes_de_solicitudes()
        AlertaComercial.objects.filter(solicitud=d).delete()
        self.rompe("0 alertas", verificar_invariantes_de_solicitudes)

    def test_invariante_de_solicitudes_una_discrepancia_sin_lineas_o_de_una_entrega_no_concretada_rompe(self):
        e1 = self.entrega_de_suministro()
        with transaction.atomic():
            d = solicitudes.crear_solicitud(DiscrepanciaEntrega, e1)
        AlertaComercial.objects.create(alerta=crear_alerta(self.e.invernadero, "comercial_discrepancia_entrega"), solicitud=d)
        self.rompe("no está concretada", verificar_invariantes_de_solicitudes)
        self.rompe("sin líneas", verificar_invariantes_de_solicitudes)

    def test_invariante_de_solicitudes_una_solicitud_de_una_compra_venta_rompe(self):
        e1 = marcar_concretada(self.entrega_de_venta())
        s = solicitudes.crear_solicitud(DiscrepanciaEntrega, e1)
        AlertaComercial.objects.create(alerta=crear_alerta(self.e.invernadero, "comercial_discrepancia_entrega"), solicitud=s)
        self.rompe("compra-venta", verificar_invariantes_de_solicitudes)
        self.assertEqual(CompraVenta.objects.filter(pk=e1.contrato_entrega_id).count(), 1)
