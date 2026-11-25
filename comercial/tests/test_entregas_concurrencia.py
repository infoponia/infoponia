# Pruebas de concurrencia de las entregas (COM-05a1, paso 7; docs/casos_de_uso/comercial/entregas.md, «Pruebas»; docs/patrones/bloqueos.md, «Entregas y envasado»): dos
# planificaciones por el último lugar de un transportista (el semáforo es el invernadero de origen: una queda sin transportista), una planificación contra una merma en cámara que libera la
# reserva (en los dos órdenes) y dos corridas del paso 50 a la vez. La merma en cámara contra el envasado de la entrega es de COM-05a2 (abajo; el resto del envasado, en `test_envasado_concurrencia.py`); la de la cancelación de la venta llega con COM-05b. Dos hilos, dos
# conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: sin Georef de la migración (el cliente tiene una dirección en la localidad propia que arma
# `geografia_propia`). Todas terminan verificando los invariantes de las reservas y de las entregas. Nunca un error 500: el que pierde espera y relee (8b).

from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import AlertaComercial, Entrega
from comercial.servicios import entregas, envasado, merma_camara
from comercial.servicios.merma_camara import DatosDeMermaEnCamara
from comercial.tests.fabricas import (
    compra_venta,
    envase,
    detalle,
    direccion_de_cliente,
    escenario_comercial,
    partida_cosechada,
    reserva,
    reserva_lista,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.tests.concurrencia import codigos, correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.tests.fabricas import lote_maduro, separar

HOY = timezone.localdate()


@tag("concurrencia")
class EntregasConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, capacidad="20"):
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

    def venta_lista(self, cantidad=100):
        venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        det = detalle(venta, self.e.variedad, cantidad)
        return venta, det, reserva_lista(det, self.lote, cantidad)

    def planificar(self, venta):
        """Una operación que planifica la entrega de la venta."""
        return lambda: entregas.planificar_venta(venta.pk, HOY)

    def test_regla_dos_planificaciones_por_el_ultimo_lugar_de_un_transportista_dejan_una_sin_transportista(self):
        """Requisito especial de COM-PNF-ENT: las planificaciones que involucran al mismo transportista y la misma fecha se ejecutan de a una. Un vehículo de 20 kg y dos ventas de 15 kg: una
        entrega se queda con el transportista y la otra queda sin transportista, con su alerta para el Gerente; nunca las dos (la capacidad no se supera)."""
        self.armar("20")
        v1, _, _ = self.venta_lista(100)
        v2, _, _ = self.venta_lista(100)
        resultados = correr_a_la_vez(self.planificar(v1), self.planificar(v2), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(Entrega.objects.count(), 2)
        self.assertEqual(Entrega.objects.filter(transportista=self.t).count(), 1)
        sin = Entrega.objects.get(transportista__isnull=True)
        self.assertEqual(AlertaComercial.objects.get(entrega=sin).alerta.estado_alerta, "activa")
        self.assertIn("capacidad de carga insuficiente", AlertaComercial.objects.get(entrega=sin).alerta.descripcion_alerta)

    def test_regla_una_planificacion_primero_y_una_merma_que_libera_la_reserva_cancela_la_entrega(self):
        """Planificación contra merma en cámara (primera la planificación): la merma espera el invernadero, recorta la reserva a cero y la entrega vacía se cancela (D-66 puntos 4 y 9); no queda una entrega
        «a realizar» sin producto."""
        self.armar("800")
        venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        det = detalle(venta, self.e.variedad, 30)
        p = partida_cosechada(self.lote, 30)
        reserva(det, [(p, 30)])
        merma = lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, DatosDeMermaEnCamara(p.pk, 30, "dano_en_camara", "", None))
        resultados = correr_a_la_vez(self.planificar(venta), merma, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        (e,) = Entrega.objects.all()
        self.assertEqual((e.estado_orden, e.motivo_cancelacion), ("cancelada", "Se perdió en cámara el producto reservado."))

    def test_regla_una_merma_primero_y_la_planificacion_ve_la_reserva_liberada_y_no_registra_nada(self):
        """Planificación contra merma en cámara (primera la merma): al relear con todo bloqueado (8b) la reserva ya no está «lista para entrega» y la entrega no se registra."""
        self.armar("800")
        venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        det = detalle(venta, self.e.variedad, 30)
        p = partida_cosechada(self.lote, 30)
        reserva(det, [(p, 30)])
        merma = lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, DatosDeMermaEnCamara(p.pk, 30, "dano_en_camara", "", None))
        resultados = correr_a_la_vez(merma, self.planificar(venta), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(Entrega.objects.count(), 0)

    def test_regla_dos_corridas_del_paso_50_a_la_vez_crean_una_sola_entrega(self):
        """Dos corridas del paso 50 a la vez: la que llega segunda espera, relee (8b) y no encuentra nada sin línea; una sola entrega."""
        self.armar("800")
        self.venta_lista(100)
        resultados = correr_a_la_vez(lambda: entregas.planificar_entregas(HOY), lambda: entregas.planificar_entregas(HOY), primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        self.assertEqual(Entrega.objects.count(), 1)
        self.assertEqual(sum(r.creados for r in buenos), 1)

    def merma_que_vacia_la_entrega(self, envasar_primero):
        """Una entrega de 30 plantas con una partida de 30 y un envase de 20: la merma en cámara de las 30 la vacía; el envasado reserva 5 envases."""
        self.armar("800")
        venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        det = detalle(venta, self.e.variedad, 30)
        p = partida_cosechada(self.lote, 30)
        reserva(det, [(p, 30)])
        (resultado,) = entregas.planificar_venta(venta.pk, HOY)
        entrega_ = resultado.entrega
        bandeja = envase(self.e.invernadero, 20)
        carga = envasado.CargaDeEnvasado(entrega_.pk, ((bandeja.pk, "5"),), envasado.huella_de(entrega_.pk))
        envasar = lambda: envasado.planificar_envasado(self.e.agronomo, carga)
        merma = lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, DatosDeMermaEnCamara(p.pk, 30, "dano_en_camara", "", None))
        return entrega_, bandeja, (envasar, merma) if envasar_primero else (merma, envasar)

    def test_regla_una_merma_que_vacia_la_entrega_primero_y_el_envasado_ve_la_entrega_cancelada(self):
        """COM-05a2, 10a: la merma en cámara vacía la entrega (se cancela) y el envasado, que espera al invernadero, la encuentra cancelada: `entrega_no_a_realizar`; sin reservas de envase activas."""
        from comercial.models import Entrega as EntregaModelo
        from produccion.models import ReservaInsumo

        entrega_, bandeja, (primera_op, segunda_op) = self.merma_que_vacia_la_entrega(envasar_primero=False)
        resultados = correr_a_la_vez(primera_op, segunda_op, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], resultados)
        self.assertEqual(codigos(rechazos[0]), ["entrega_no_a_realizar"])
        self.assertEqual(EntregaModelo.objects.get(pk=entrega_.pk).estado_orden, "cancelada")
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=entrega_.pk, estado="activa").exists())

    def test_regla_un_envasado_primero_y_la_merma_que_vacia_la_entrega_cancela_tambien_los_envases(self):
        """COM-05a2: el envasado registra y la merma después cancela la entrega vacía: las reservas de envase pasan a «cancelada» sin consumo y los envases vuelven a estar libres."""
        from inventario.servicios import stock
        from produccion.models import ReservaInsumo

        entrega_, bandeja, (primera_op, segunda_op) = self.merma_que_vacia_la_entrega(envasar_primero=True)
        resultados = correr_a_la_vez(primera_op, segunda_op, primera="a")
        buenos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        (r,) = ReservaInsumo.objects.filter(orden_id=entrega_.pk)
        self.assertEqual((r.estado, r.cantidad_utilizada), ("cancelada", None))
        self.assertEqual(stock.disponible_para_planificar([bandeja.pk], HOY)[bandeja.pk], 20)
