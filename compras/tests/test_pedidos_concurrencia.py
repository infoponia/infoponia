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
from core.tests.fabricas import construir_url, crear_gerente
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


# ---------------------------------------------------------------------------------------------------------------------------------
# CMP-02b, paso 4: cancelar contra cotizar, baja del proveedor contra cotizar, reenviar contra cotizar y dos cancelaciones a la vez. Fuente: CMP-CNL-PED
# («Requisitos especiales»: «impide que un proveedor envíe una cotización mientras se lo cancela»), regla 3 de CMP-BAJ-PRV, regla 7 de CMP-CNS-PED, D-88
# puntos 2 y 7 y docs/patrones/bloqueos.md («compras»). Todos bloquean el pedido o el proveedor antes que el enlace, así que quien llega segundo espera, relee y
# ve el estado nuevo. La operación ``primera`` se detiene al auditar, con todo bloqueado y sin confirmar.
# ---------------------------------------------------------------------------------------------------------------------------------

proveedores_de_compras = perezoso("compras.servicios.proveedores")
pedidos_de_compras = perezoso("compras.servicios.pedidos")


@tag("concurrencia")
class CancelarReenviarYDarDeBajaConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Un pedido de 20 lechugas con dos proveedores invitados (enlaces vigentes), su Agrónomo y un Gerente."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        self.gerente = crear_gerente()
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero("Invernadero Norte")
        self.pedido = armar_pedido(self.agronomo, dias_al_limite=3)
        self.detalle = detalle_de_pedido(self.pedido, existencia(insumo("Lechuga", unidad="unidad"), self.invernadero, minimo=20), cantidad="20")
        self.sur, self.este = proveedor("Semillas del Sur S. A.", n=1), proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.invitacion_sur = invitar(self.pedido, self.sur)
        self.enlace_sur, _ = enlace_de(self.invitacion_sur)
        self.enlace_este, _ = enlace_de(invitar(self.pedido, self.este))
        self.validez = timezone.localdate() + timedelta(days=10)

    def cotizar(self, enlace):
        return lambda: cotizaciones.registrar_cotizacion(enlace.pk, [(self.detalle.pk, "20", "100.00", None, 2)], self.validez, "")

    def cancelar(self):
        return lambda: pedidos_de_compras.cancelar_pedido(self.agronomo, self.pedido.pk, "Ya no hace falta.")

    def dar_de_baja(self, proveedor_):
        return lambda: proveedores_de_compras.baja_proveedor(self.gerente, proveedor_.pk)

    def reenviar(self):
        return lambda: pedidos_de_compras.reenviar_invitacion(self.agronomo, self.invitacion_sur.pk, construir_url)

    def estado(self, objeto):
        objeto.refresh_from_db()
        return getattr(objeto, "estado", None) or getattr(objeto, "estado_cotizacion", None)

    # ---- cancelar contra cotizar ----

    def test_cancelar_gana_y_el_envio_ve_el_pedido_cancelado(self):
        """CMP-CNL-PED («Requisitos especiales»): la cancelación va primera y bloquea el pedido; el proveedor que envía espera, relee y recibe ``enlace_no_sirve`` (pedido cancelado). No queda ninguna cotización."""
        resultados = correr_a_la_vez(self.cancelar(), self.cotizar(self.enlace_sur), primera="a")
        self.assertEqual(resultados["a"].estado_pedido, "cancelado")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "enlace_no_sirve")
        self.assertEqual(resultados["b"].datos["situacion"], "pedido_cancelado")
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_el_envio_gana_y_la_cancelacion_descarta_su_cotizacion(self):
        """El envío va primero y confirma; la cancelación espera el pedido, ve la cotización nueva y la descarta; el enlace queda «usado» y el otro, «anulado»."""
        resultados = correr_a_la_vez(self.cotizar(self.enlace_sur), self.cancelar(), primera="a")
        self.assertIsInstance(resultados["a"], Cotizacion)
        self.assertEqual(resultados["b"].estado_pedido, "cancelado")
        self.assertEqual(Cotizacion.objects.get().estado_cotizacion, "descartada")
        self.assertEqual((self.estado(self.enlace_sur), self.estado(self.enlace_este)), ("usado", "anulado"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 1)

    def test_dos_cancelaciones_a_la_vez_cancelan_una_sola_vez(self):
        """Extensión 6a: la segunda espera, ve el pedido cancelado y recibe ``pedido_no_en_cotizacion``; un solo registro, un solo correo por invitado."""
        resultados = correr_a_la_vez(self.cancelar(), self.cancelar(), primera="a")
        self.assertEqual(resultados["a"].estado_pedido, "cancelado")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "pedido_no_en_cotizacion")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 1)

    # ---- baja del proveedor contra cotizar ----

    def test_la_baja_gana_y_el_envio_ve_el_enlace_anulado(self):
        """Regla 3 de CMP-BAJ-PRV: la baja va primera (bloquea al proveedor y anula sus enlaces); el envío espera al proveedor, relee y recibe ``enlace_no_sirve``. No hay cotización."""
        resultados = correr_a_la_vez(self.dar_de_baja(self.sur), self.cotizar(self.enlace_sur), primera="a")
        self.assertEqual(resultados["a"].estado_proveedor, "inactivo")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "enlace_no_sirve")
        self.assertEqual(Cotizacion.objects.count(), 0)
        self.assertEqual(self.estado(self.enlace_sur), "anulado")

    def test_el_envio_gana_y_la_baja_no_anula_el_enlace_usado(self):
        """El envío va primero; la baja espera al proveedor, ve el enlace «usado» y no lo anula: la cotización «propuesta» se conserva y el proveedor queda inactivo."""
        resultados = correr_a_la_vez(self.cotizar(self.enlace_sur), self.dar_de_baja(self.sur), primera="a")
        self.assertIsInstance(resultados["a"], Cotizacion)
        self.assertEqual(resultados["b"].estado_proveedor, "inactivo")
        self.assertEqual(self.estado(self.enlace_sur), "usado")
        self.assertEqual(Cotizacion.objects.get().estado_cotizacion, "propuesta")

    # ---- reenviar contra cotizar ----

    def test_el_reenvio_gana_y_cotizar_con_el_enlace_viejo_da_enlace_no_sirve(self):
        """Regla 7 de CMP-CNS-PED: el reenvío va primero (el enlace viejo pasa a «reemplazado»); el proveedor que cotiza con el viejo espera, relee y recibe ``enlace_no_sirve``."""
        resultados = correr_a_la_vez(self.reenviar(), self.cotizar(self.enlace_sur), primera="a")
        self.assertEqual(resultados["a"].estado, "vigente")
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "enlace_no_sirve")
        self.assertEqual(resultados["b"].datos["situacion"], "reemplazado")
        self.assertEqual((Cotizacion.objects.count(), self.estado(self.enlace_sur)), (0, "reemplazado"))

    def test_la_cotizacion_gana_y_el_reenvio_da_ya_cotizo(self):
        """La cotización va primera (el enlace queda «usado»); el reenvío espera al proveedor, ve la cotización y recibe ``ya_cotizo``: no se crea ningún enlace nuevo."""
        resultados = correr_a_la_vez(self.cotizar(self.enlace_sur), self.reenviar(), primera="a")
        self.assertIsInstance(resultados["a"], Cotizacion)
        self.assertIsInstance(resultados["b"], ErrorDeCompras)
        self.assertEqual(resultados["b"].codigo, "ya_cotizo")
        self.assertEqual(self.invitacion_sur.enlaces.count(), 1)
        self.assertEqual(self.estado(self.enlace_sur), "usado")
