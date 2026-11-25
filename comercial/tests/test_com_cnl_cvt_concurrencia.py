# Pruebas de concurrencia de COM-CNL-CVT · Cancelar Compra-venta (COM-05b; docs/casos_de_uso/comercial/compra_venta.md, «Pruebas»; docs/patrones/bloqueos.md, «Cancelar una compra-venta»):
# cancelar contra concretar una cosecha de la venta (8b), contra la planificación de su entrega (la del `on_commit` y la del paso 50: la que llega segunda no encuentra nada que hacer),
# contra la decisión del cliente por el enlace (la segunda ve el enlace anulado o la venta cancelada), contra PROD-ASG-CAM sobre una partida de la venta y contra asignar un transportista a su
# entrega. Dos hilos, dos conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma
# `geografia_propia`). Todas terminan verificando los invariantes de las reservas y de las entregas. Nunca un error 500: el que pierde espera, relee y recibe un código de negocio.

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import CompraVenta, DetalleVenta, EnlaceCliente, Entrega, PagoCliente, ReservaStock
from comercial.servicios import camara, compra_ventas, concrecion, cosechas, entregas, faltantes
from comercial.servicios.compra_ventas import DatosDeCancelacionDeVenta
from comercial.servicios.cosechas import DatosDeConcrecion
from comercial.tests.fabricas import (
    compra_venta,
    cosecha_manual,
    detalle,
    direccion_de_cliente,
    enlace as un_enlace,
    entrega,
    escenario_comercial,
    partida_cosechada,
    reserva,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_cobros,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import Cosecha
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar, variedad_con_stock

HOY = timezone.localdate()


@tag("concurrencia")
class ComCnlCvtConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, capacidad="800"):
        """Un invernadero con un transportista de ``capacidad`` kg, un lote de 500 y un cliente con una dirección en la localidad propia."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 500)
        self.gerente = crear_gerente()
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.t = transportista_con_vehiculo(self.e.invernadero, capacidad)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def venta_con_cosecha(self):
        """Una venta con envío con una cosecha «a realizar» que reserva 30 de 50."""
        self.armar()
        self.venta = compra_venta(self.e, dias=10, direccion=self.direccion)
        self.detalle = detalle(self.venta, self.e.variedad, 50)
        self.cosecha = cosecha_manual(self.e, [(self.lote, 30)], detalle_=self.detalle, dias=5)

    def venta_con_entrega(self, transportista=None):
        """Una venta lista con su entrega «a realizar» (sin transportista, por omisión)."""
        self.armar()
        self.venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        self.detalle = detalle(self.venta, self.e.variedad, 100)
        self.reserva = reserva_lista(self.detalle, self.lote, 100)
        self.entrega = entrega(self.venta, [self.reserva], transportista=transportista)

    def cancelar(self, actor=None):
        """La cancelación de la venta, con la huella que vio la pantalla antes de que arrancara la otra operación."""
        actor = actor or self.e.vendedor
        huella = compra_ventas.datos_de_cancelacion(actor, self.venta.pk).huella
        return lambda: compra_ventas.cancelar_compra_venta(actor, self.venta.pk, DatosDeCancelacionDeVenta("cliente_desistio"), huella)

    def estado_de_la_venta(self):
        return CompraVenta.objects.get(pk=self.venta.pk).estado_venta

    # ---- contra concretar una cosecha de la venta (8b) ----

    def concretar(self):
        datos = DatosDeConcrecion(cantidades=((self.lote.pk, self.e.sectores["maduracion"].pk, 30),))
        return lambda: cosechas.concretar_cosecha(self.e.capataz, self.cosecha.pk, datos)

    def test_regla_cancelar_primero_y_la_concrecion_de_la_cosecha_recibe_orden_no_a_realizar(self):
        """8b: con la cancelación primero, la cosecha queda cancelada y la concreción, que espera la fila de la cosecha, recibe `orden_no_a_realizar`; el lote no se toca."""
        self.venta_con_cosecha()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.concretar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("orden_no_a_realizar", codigos_del_rechazo(rechazos[0]))
        self.assertEqual((self.estado_de_la_venta(), Cosecha.objects.get(pk=self.cosecha.pk).estado_orden), ("cancelada", "cancelada"))
        self.assertEqual(ReservaStock.objects.get(cosecha=self.cosecha).estado_reserva, "liberada")

    def test_regla_concretar_primero_y_la_cancelacion_ve_que_la_venta_cambio_y_vuelve_al_paso_4(self):
        """8b: con la concreción primero, la cancelación relee, ve la huella cambiada y recibe `venta_cambio`: no registra nada y, al volver a mirar, lo cosechado figura como ingreso a la cámara."""
        self.venta_con_cosecha()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar(), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("venta_cambio", codigos(rechazos[0]))
        self.assertEqual((self.estado_de_la_venta(), Cosecha.objects.get(pk=self.cosecha.pk).estado_orden), ("abierta", "concretada"))
        datos = compra_ventas.datos_de_cancelacion(self.e.vendedor, self.venta.pk)
        self.assertEqual([g.cantidad for g in datos.a_camara], [30])

    # ---- contra la planificación de su entrega ----

    def test_regla_cancelar_primero_y_la_planificacion_no_encuentra_nada_que_hacer(self):
        """La planificación (la del `on_commit` y la del paso 50 son la misma función) espera el invernadero y relee: la venta ya no está «abierta», así que no crea ninguna entrega."""
        self.armar()
        self.venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        self.detalle = detalle(self.venta, self.e.variedad, 100)
        reserva_lista(self.detalle, self.lote, 100)
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), lambda: entregas.planificar_venta(self.venta.pk, HOY), primera="a"))
        self.assertEqual((rechazos, otros), ([], []), (rechazos, otros))
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.count()), ("cancelada", 0))

    def test_regla_la_planificacion_primero_y_la_cancelacion_no_deja_entregas_a_realizar(self):
        """Con la planificación primero, la entrega nace antes de que la cancelación relea: la cancelación ve la huella cambiada (`venta_cambio`) y, al repetirla, cancela también la entrega nueva."""
        self.armar()
        self.venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        self.detalle = detalle(self.venta, self.e.variedad, 100)
        reserva_lista(self.detalle, self.lote, 100)
        exitos, rechazos, otros = separar(correr_a_la_vez(lambda: entregas.planificar_venta(self.venta.pk, HOY), self.cancelar(), primera="a"))
        self.assertEqual(otros, [], (rechazos, otros))
        self.assertEqual(Entrega.objects.filter(estado_orden="a_realizar").count(), 1 if self.estado_de_la_venta() != "cancelada" else 0)
        if rechazos:
            self.assertIn("venta_cambio", codigos(rechazos[0]))
            compra_ventas.cancelar_compra_venta(
                self.e.vendedor, self.venta.pk, DatosDeCancelacionDeVenta("cliente_desistio"), compra_ventas.datos_de_cancelacion(self.e.vendedor, self.venta.pk).huella
            )
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.filter(estado_orden="a_realizar").count()), ("cancelada", 0))

    # ---- contra la decisión del cliente por el enlace ----

    def pendiente_con_enlace(self):
        """El detalle de la cosecha pasa a «pendiente de decisión» (la cosecha reserva 30 de 50) con el enlace vigente del cliente."""
        self.venta_con_cosecha()
        DetalleVenta.objects.filter(pk=self.detalle.pk).update(estado_detalle_venta="pendiente_decision", fecha_pendiente_decision=HOY)
        CompraVenta.objects.filter(pk=self.venta.pk).update(estado_venta="pendiente_decision")
        self.enlace, _ = un_enlace(self.venta)

    def rechazar(self):
        return lambda: faltantes.registrar_decision(self.enlace.pk, {self.detalle.pk: "rechazar"}, {self.detalle.pk: 30})

    def test_regla_cancelar_primero_y_la_decision_del_cliente_ve_el_enlace_anulado(self):
        """Con la cancelación primero, el enlace queda «anulado» y la decisión del cliente recibe `enlace_no_sirve`; la venta queda «cancelada» con su motivo."""
        self.pendiente_con_enlace()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.rechazar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("enlace_no_sirve", codigos_del_rechazo(rechazos[0]))
        self.assertEqual(EnlaceCliente.objects.get(pk=self.enlace.pk).estado, "anulado")
        self.assertEqual(CompraVenta.objects.get(pk=self.venta.pk).motivo_cancelacion_venta, "cliente_desistio")

    def test_regla_la_decision_primero_y_la_cancelacion_ve_la_venta_cerrada(self):
        """Con la decisión primero (rechaza el único detalle), la venta queda «cancelada» sin motivo de MD-130; la cancelación, que esperaba, recibe `venta_no_cancelable` y no la toca."""
        self.pendiente_con_enlace()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.rechazar(), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertTrue({"venta_no_cancelable", "venta_cambio"} & set(codigos(rechazos[0])))
        venta = CompraVenta.objects.get(pk=self.venta.pk)
        self.assertEqual((venta.estado_venta, venta.motivo_cancelacion_venta), ("cancelada", None))

    # ---- contra PROD-ASG-CAM ----

    def test_regla_cancelar_contra_la_asignacion_de_camara_de_una_partida_de_la_venta_no_da_errores(self):
        """La asignación de cámara de la partida de una línea de la venta (que la cancelación libera) corre a la vez: ninguna falla con un error sin traducir y la venta queda coherente."""
        self.armar()
        self.venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        self.detalle = detalle(self.venta, self.e.variedad, 30)
        p = partida_cosechada(self.lote, 30)
        reserva(self.detalle, [(p, 30)])
        resultados = correr_a_la_vez(self.cancelar(), lambda: camara.asignar_camara([p.pk]), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], resultados)
        self.assertEqual(self.estado_de_la_venta(), "cancelada")
        self.assertEqual(ReservaStock.objects.get(detalle_venta=self.detalle).estado_reserva, "liberada")

    # ---- contra asignar un transportista a su entrega ----

    def asignar(self, transportista):
        from comercial.servicios import entregas as api

        huella = api.datos_de_asignacion(self.e.vendedor, self.entrega.pk).huella
        return lambda: api.asignar_transportista(self.e.vendedor, self.entrega.pk, transportista.pk, huella)

    def test_regla_cancelar_primero_y_la_asignacion_recibe_la_entrega_cancelada(self):
        """Con la cancelación primero, la entrega queda cancelada y la asignación, que espera el invernadero, recibe `entrega_no_a_realizar` (8a)."""
        self.venta_con_entrega()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar(), self.asignar(self.t), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("entrega_no_a_realizar", codigos(rechazos[0]))
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.get(pk=self.entrega.pk).estado_orden), ("cancelada", "cancelada"))

    def test_regla_la_asignacion_primero_y_la_cancelacion_ve_la_entrega_cambiada(self):
        """Con la asignación primero, la cancelación relee, ve la huella cambiada (el transportista) y recibe `venta_cambio`: la venta sigue abierta y la entrega, con su transportista."""
        self.venta_con_entrega()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.asignar(self.t), self.cancelar(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("venta_cambio", codigos(rechazos[0]))
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.get(pk=self.entrega.pk).transportista_id), ("abierta", self.t.pk))

    # ---- contra concretar la otra entrega de una venta con una entrega concretada (6a; COM-08b) ----

    def venta_de_retiro_con_una_entrega_concretada(self):
        """Una venta de **retiro** con dos detalles (dos variedades) y dos entregas «a realizar» de hoy, sin transportista: la primera se concreta de verdad (no es la última de la venta: no se cobra); la segunda
        queda para concretar. El retiro no necesita ruta (COM-06a). Deja `self.venta`, `self.e1`, `self.e2`."""
        self.armar()
        otra, _ = variedad_con_stock(self.e, "Otra variedad")
        lote_b = lote_maduro(self.e, 500, variedad=otra)
        self.venta = compra_venta(self.e, dias=0, modalidad="retiro", retiro=self.e.invernadero)
        d1, d2 = detalle(self.venta, self.e.variedad, 50), detalle(self.venta, otra, 30)
        self.e1 = entrega(self.venta, [reserva_lista(d1, self.lote, 50)], fecha=HOY)
        self.e2 = entrega(self.venta, [reserva_lista(d2, lote_b, 30)], fecha=HOY)
        self.addCleanup(verificar_invariantes_de_cobros)
        datos = concrecion.DatosDeConcrecion(sin_envases=True, medio_pago="efectivo")
        concrecion.concretar_entrega(self.e.vendedor, self.e1.pk, datos, concrecion.resumen_de_concrecion(self.e.vendedor, self.e1.pk, datos).huella)

    def cancelar_con_cobro(self):
        """La cancelación con el cobro de lo entregado, con la huella que vio la pantalla antes de que arrancara la otra operación."""
        huella = compra_ventas.datos_de_cancelacion(self.e.vendedor, self.venta.pk).huella
        return lambda: compra_ventas.cancelar_compra_venta(self.e.vendedor, self.venta.pk, DatosDeCancelacionDeVenta("cliente_desistio", "", "efectivo"), huella)

    def concretar_la_segunda(self):
        datos = concrecion.DatosDeConcrecion(sin_envases=True, medio_pago="efectivo")
        huella = concrecion.resumen_de_concrecion(self.e.vendedor, self.e2.pk, datos).huella
        return lambda: concrecion.concretar_entrega(self.e.vendedor, self.e2.pk, datos, huella)

    def pagos_vigentes(self):
        return PagoCliente.objects.filter(compra_venta=self.venta, estado_pago="vigente").count()

    def test_regla_6a_cancelar_primero_y_la_concrecion_de_la_otra_entrega_recibe_entrega_no_concretable(self):
        """6a y 8a: con la cancelación primero, cobra lo entregado y cancela la entrega pendiente; la concreción, que espera el invernadero, relee y recibe `entrega_no_concretable`: un solo pago y la venta «concretada»."""
        self.venta_de_retiro_con_una_entrega_concretada()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.cancelar_con_cobro(), self.concretar_la_segunda(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn("entrega_no_concretable", codigos(rechazos[0]))
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.get(pk=self.e2.pk).estado_orden, self.pagos_vigentes()), ("concretada", "cancelada", 1))

    def test_regla_6a_concretar_primero_y_la_cancelacion_no_cobra_dos_veces(self):
        """6a y 8a: con la concreción primero (la última entrega: la venta queda «concretada» con su pago, postcondición k de COM-CNC-ENT), la cancelación relee y recibe `venta_cambio` o `venta_no_cancelable`:
        no cobra lo entregado por segunda vez (un solo pago vigente)."""
        self.venta_de_retiro_con_una_entrega_concretada()
        exitos, rechazos, otros = separar(correr_a_la_vez(self.concretar_la_segunda(), self.cancelar_con_cobro(), primera="a"))
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []))
        self.assertIn(codigos(rechazos[0])[0], ("venta_cambio", "venta_no_cancelable"))
        self.assertEqual((self.estado_de_la_venta(), Entrega.objects.get(pk=self.e2.pk).estado_orden, self.pagos_vigentes()), ("concretada", "concretada", 1))
