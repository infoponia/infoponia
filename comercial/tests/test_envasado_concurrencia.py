# Pruebas de concurrencia de PROD-PNF-ENV · Planificar Envasado (COM-05a2; docs/casos_de_uso/produccion/envasado.md, «Pruebas»; docs/patrones/bloqueos.md, «Entregas y envasado»):
# dos envasados de entregas distintas por el último stock de un envase (uno da 10b), un envasado contra una siembra del mismo invernadero (PRD-01, en los dos órdenes: el semáforo) y un
# envasado contra la cancelación de la misma entrega (10a, en los dos órdenes). Dos hilos, dos conexiones, el orden fijado con ``primera``. Son ``TransactionTestCase``: el cliente
# tiene una dirección en la localidad propia que arma `geografia_propia`. Nunca un error 500: el que pierde espera, relee y se rechaza con un error de negocio.

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.test import TransactionTestCase, tag
from django.utils import timezone

from comercial.models import Entrega
from comercial.servicios import entregas, envasado
from comercial.servicios.envasado import CargaDeEnvasado
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    direccion_de_cliente,
    entrega,
    envase,
    escenario_comercial,
    reserva_lista,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
)
from core.models import RegistroAuditoria
from core.tests.concurrencia import codigos, correr_a_la_vez
from inventario.servicios import stock
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario
from maestros.models import Localidad
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import asegurar_datos_de_maestros
from produccion.models import ReservaInsumo
from produccion.servicios import siembras
from produccion.tests.fabricas import codigos_del_rechazo, lote_maduro, separar
from produccion.tests.test_prod_pnf_smb import datos as datos_de_siembra

HOY = timezone.localdate()


@tag("concurrencia")
class ProdPnfEnvConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    def armar(self, stock_del_envase=10):
        """Un invernadero con un lote, un envase con `stock_del_envase` unidades y un cliente con dirección en la localidad propia."""
        asegurar_datos_de_maestros()
        asegurar_datos_de_inventario()
        self.e = escenario_comercial(geografia_propia=True)
        self.lote = lote_maduro(self.e, 5000)
        self.agronomo = self.e.agronomo
        self.direccion = direccion_de_cliente(self.e.cliente, localidad_id=Localidad.objects.get(id_georef="99001001").pk).direccion
        self.envase = envase(self.e.invernadero, stock_del_envase)
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)

    def entrega_nueva(self, cantidad=50):
        venta = compra_venta(self.e, dias=3, direccion=self.direccion)
        det = detalle(venta, self.e.variedad, cantidad)
        return entrega(venta, [reserva_lista(det, self.lote, cantidad)])

    def envasar(self, entrega_, cantidad):
        """Una operación que envasa `cantidad` del envase en la entrega, con la carga armada antes (como la pantalla)."""
        carga = CargaDeEnvasado(entrega_.pk, ((self.envase.pk, str(cantidad)),), envasado.huella_de(entrega_.pk))
        return lambda: envasado.planificar_envasado(self.agronomo, carga)

    def test_regla_dos_envasados_de_entregas_distintas_por_el_ultimo_stock_uno_da_10b(self):
        """Requisito especial: el control de concurrencia sobre el stock libre impide la sobreasignación. Con 10 envases, dos envasados de 10 de entregas distintas: el primero registra y el
        segundo espera el insumo del invernadero, ve la reserva del primero y se rechaza con `disponible_cambio` (10b)."""
        self.armar(10)
        uno, otro = self.entrega_nueva(), self.entrega_nueva()
        resultados = correr_a_la_vez(self.envasar(uno, 10), self.envasar(otro, 10), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (1, 1, []), resultados)
        self.assertEqual(codigos(rechazos[0]), ["disponible_cambio"])
        self.assertEqual(ReservaInsumo.objects.filter(estado="activa").count(), 1)
        self.assertEqual(stock.disponible_para_planificar([self.envase.pk], HOY)[self.envase.pk], 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="planificacion_envasado").count(), 1)

    def siembra(self):
        """Una operación que planifica una siembra (PRD-01): reserva semilla, no envases (`planificar_siembra` rechaza un envase como insumo adicional: `insumo_no_elegible`)."""
        return lambda: siembras.planificar_siembra(self.agronomo, datos_de_siembra(self.e, cantidad=10))

    def test_regla_un_envasado_primero_y_una_siembra_del_mismo_invernadero_se_serializan_sin_errores(self):
        """Envasado contra siembra (primero el envasado): las dos toman el invernadero como semáforo (D-66 punto 11) y la siembra espera sin deadlock; las dos registran. Una siembra
        no puede reservar envases (`insumo_no_elegible`), así que no compiten por el mismo stock: lo que se prueba es el orden de bloqueos."""
        self.armar(10)
        e = self.entrega_nueva()
        resultados = correr_a_la_vez(self.envasar(e, 10), self.siembra(), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []), resultados)
        self.assertEqual(ReservaInsumo.objects.filter(insumo_invernadero=self.envase, estado="activa").count(), 1)

    def test_regla_una_siembra_primero_y_un_envasado_del_mismo_invernadero_se_serializan_sin_errores(self):
        """Envasado contra siembra (primero la siembra): el envasado espera el invernadero y registra después; sin deadlock ni error 500."""
        self.armar(10)
        e = self.entrega_nueva()
        resultados = correr_a_la_vez(self.siembra(), self.envasar(e, 10), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), rechazos, otros), (2, [], []), resultados)
        self.assertEqual(ReservaInsumo.objects.filter(orden_id=e.pk, estado="activa").count(), 1)

    def cancelar(self, entrega_):
        """Una operación que cancela la entrega como lo hace un caso de uso base (COM-CNL-CVT, la merma): invernadero → cancelación incluida → su registro de auditoría."""

        def operacion():
            with transaction.atomic():
                bloquear_invernadero_activo(entrega_.invernadero_id)
                cancelacion = entregas.cancelar_entrega_incluida(None, entrega_, "Cancelada por la prueba")
                RegistroAuditoria.objects.registrar(None, RegistroAuditoria.Accion.CANCELACION_ORDEN, [cancelacion.entrega], {"datos": {"motivo": "Cancelada por la prueba"}})

        return operacion

    def test_ext_10a_una_cancelacion_primero_y_el_envasado_ve_la_entrega_cancelada(self):
        """Extensión 10a: el envasado espera al invernadero que tomó la cancelación, relee y encuentra la entrega cancelada: `entrega_no_a_realizar`; no queda ninguna reserva de insumo activa."""
        self.armar(10)
        e = self.entrega_nueva()
        resultados = correr_a_la_vez(self.cancelar(e), self.envasar(e, 5), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual(otros, [], resultados)
        self.assertEqual(codigos(rechazos[0]), ["entrega_no_a_realizar"])
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "cancelada")
        self.assertFalse(ReservaInsumo.objects.filter(orden_id=e.pk, estado="activa").exists())

    def test_ext_10a_un_envasado_primero_y_la_cancelacion_cancela_las_reservas_de_los_envases(self):
        """Envasado primero: la cancelación (que espera al invernadero) cancela la entrega y, con ella, las reservas de insumo recién creadas, sin consumo."""
        self.armar(10)
        e = self.entrega_nueva()
        resultados = correr_a_la_vez(self.envasar(e, 5), self.cancelar(e), primera="a")
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((rechazos, otros), ([], []), resultados)
        (reserva,) = ReservaInsumo.objects.filter(orden_id=e.pk)
        self.assertEqual((reserva.estado, reserva.cantidad_utilizada, reserva.cantidad_devuelta), ("cancelada", None, None))
        self.assertEqual(stock.disponible_para_planificar([self.envase.pk], HOY)[self.envase.pk], 10)
