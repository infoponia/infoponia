# Pruebas de concurrencia de CMP-ENV-COT (CMP-02a, paso 4): dos envíos del mismo proveedor y dos proveedores que cubren el pedido a la vez. Fuente:
# CMP-ENV-COT («Requisitos especiales»: «El control de concurrencia cumple dos funciones»), D-88 punto 7 y docs/patrones/bloqueos.md («compras»:
# ``Proveedor`` → ``Pedido`` → ``EnlaceProveedor``). Son ``TransactionTestCase`` con dos hilos y dos conexiones (``core/tests/concurrencia.py``); la primera
# operación se detiene al auditar, con todos sus bloqueos tomados y sin confirmar, y recién entonces arranca la otra. CMP-02b amplía este archivo.

from decimal import Decimal

from django.test import TransactionTestCase, tag

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion
from compras.tests.fabricas import detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, existencia, insumo, perezoso
from maestros.servicios import configuracion
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef, crear_agronomo_con_invernadero
from django.utils import timezone
from datetime import timedelta

cotizaciones = perezoso("compras.servicios.cotizaciones")


@tag("concurrencia")
class PedidosConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Un pedido de 20 lechugas con tolerancia 0 y dos proveedores invitados. ``TransactionTestCase``: su ``flush`` vacía los datos de las migraciones,
    así que se aseguran de nuevo en cada prueba."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()  # el ``flush`` de cada prueba también vacía Georef, que usan los invernaderos
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 0
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.gerente = crear_gerente()
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero("Invernadero Norte")
        self.pedido = armar_pedido(self.agronomo, dias_al_limite=3)
        self.detalle = detalle_de_pedido(self.pedido, existencia(insumo("Lechuga", unidad="unidad"), self.invernadero, minimo=20), cantidad="20")
        self.sur, self.este = proveedor("Semillas del Sur S. A.", n=1), proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.enlace_sur, _ = enlace_de(invitar(self.pedido, self.sur))
        self.enlace_este, _ = enlace_de(invitar(self.pedido, self.este))
        self.validez = timezone.localdate() + timedelta(days=10)

    def enviar(self, enlace, cantidad):
        """Un envío de ``cantidad`` lechugas por ``enlace`` (en el hilo que lo llama)."""
        return lambda: cotizaciones.registrar_cotizacion(enlace.pk, [(self.detalle.pk, cantidad, "100.00", None, 2)], self.validez, "")

    def avisos(self):
        return Notificacion.objects.filter(titulo__contains=str(self.pedido))

    def test_ext_11b_dos_envios_del_mismo_proveedor_registran_una_sola_cotizacion(self):
        """Requisitos especiales de CMP-ENV-COT (primera función): dos pestañas del mismo proveedor; la segunda espera al proveedor bloqueado, ve el enlace ``usado`` y recibe ``ya_cotizo``; nunca un 500."""
        resultados = correr_a_la_vez(self.enviar(self.enlace_sur, "20"), self.enviar(self.enlace_sur, "20"), primera="a")
        exitos = [r for r in resultados.values() if isinstance(r, Cotizacion)]
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual((len(exitos), len(errores)), (1, 1))
        self.assertIsInstance(errores[0], ErrorDeCompras)
        self.assertEqual(errores[0].codigo, "ya_cotizo")
        self.assertEqual(Cotizacion.objects.filter(proveedor=self.sur).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_cotizacion").count(), 1)

    def test_ext_11c_dos_proveedores_que_juntos_cubren_el_pedido_avisan_una_sola_vez(self):
        """Requisitos especiales de CMP-ENV-COT (segunda función): ninguno cubre solo (12 y 12 de 20), pero juntos sí; con el pedido bloqueado el segundo ve la cotización del primero y es quien lo cubre: un solo aviso (sin el bloqueo no habría ninguno)."""
        resultados = correr_a_la_vez(self.enviar(self.enlace_sur, "12"), self.enviar(self.enlace_este, "12"), primera="a")
        self.assertEqual([type(r).__name__ for r in resultados.values()], ["Cotizacion", "Cotizacion"])
        self.assertEqual(Cotizacion.objects.count(), 2)
        self.assertEqual(self.avisos().count(), 1)

    def test_ext_11c_dos_proveedores_que_cubren_cada_uno_por_su_cuenta_avisan_una_sola_vez(self):
        """Requisitos especiales de CMP-ENV-COT: cada uno cubre solo (20 y 20); sin el bloqueo los dos verían «no cubierto → cubierto» y habría dos avisos; con él, el segundo ve el pedido ya cubierto."""
        resultados = correr_a_la_vez(self.enviar(self.enlace_sur, "20"), self.enviar(self.enlace_este, "20"), primera="b")
        self.assertEqual([type(r).__name__ for r in resultados.values()], ["Cotizacion", "Cotizacion"])
        self.assertEqual(self.avisos().count(), 1)
        self.assertEqual(self.avisos().get().destinatario_id, self.agronomo.pk)
