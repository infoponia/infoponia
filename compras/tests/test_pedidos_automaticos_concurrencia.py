# Pruebas de concurrencia de CMP-AUT-PED (CMP-07, paso 4): la extensión 5b («entre la lectura y el bloqueo cambió algo: se relee con todo bloqueado y, si ya no corresponde, no se
# crea nada») y la idempotencia del paso (D-56 punto 4) con dos hilos. Fuente: docs/casos_de_uso/compras/pedido_automatico.md, D-104 punto 2, docs/patrones/bloqueos.md («compras»:
# cuenta del Agrónomo → invernadero → ``InsumoInvernadero`` → proveedores) y la extensión 11a de CMP-RLZ-PED. Son ``TransactionTestCase`` con dos hilos y dos conexiones
# (``core/tests/concurrencia.py``): la primera operación se detiene al auditar, con todos sus bloqueos tomados y sin confirmar, y recién entonces arranca la otra.

from datetime import timedelta
from decimal import Decimal

from django.test import TransactionTestCase, override_settings, tag
from django.utils import timezone

from compras.models import DetallePedido, Pedido
from compras.tests.fabricas import proveedor
from core.models import Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import construir_url, crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario, asegurar_datos_de_inventario, existencia, insumo, perezoso, tipo_de_insumo
from maestros.tests.fabricas import asegurar_datos_de_maestros, asegurar_georef, crear_agronomo_con_invernadero

automaticos = perezoso("compras.servicios.pedidos_automaticos")
pedidos = perezoso("compras.servicios.pedidos")


@tag("concurrencia")
@override_settings(CORREO_CONFIGURADO=False, URL_DEL_SITIO="https://sitio.test")
class PedidosAutomaticosConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Ana con Norte, una lechuga (mínimo 20) y un nutriente (mínimo 5) bajo el mínimo y dos proveedores especializados. ``TransactionTestCase``: su ``flush`` vacía los datos de las
    migraciones, así que se aseguran de nuevo en cada prueba."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_georef()
        self.hoy = timezone.localdate()
        self.gerente = crear_gerente()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        tipo = tipo_de_insumo("Fertilizantes")
        self.lechuga = existencia(insumo("Lechuga", tipo, unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", tipo, unidad="kg"), self.norte, minimo=5, precio="100.00")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[tipo])
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com", especialidades=[tipo])

    def generar(self):
        """El paso, en el hilo que lo llama."""
        return lambda: automaticos.generar_pedidos_automaticos(self.hoy)

    def pedido_manual(self, detalles):
        """El pedido manual de Ana (CMP-RLZ-PED) con ``detalles = [(existencia, cantidad)]`` para los dos proveedores, en el hilo que lo llama."""
        datos = {
            "detalles": [(iin.pk, cantidad) for iin, cantidad in detalles],
            "proveedores": [self.sur.pk, self.este.pk],
            "fecha_limite": self.hoy + timedelta(days=3),
        }
        return lambda: pedidos.registrar_pedido(self.ana, datos, construir_url)

    def test_ext_5b_un_pedido_manual_que_toma_los_mismos_insumos_no_genera_uno_repetido(self):
        """Extensión 5b: Ana confirma un pedido manual con la lechuga y el nutriente (sin confirmar todavía: tiene todo bloqueado) mientras el paso lee, ve los dos insumos sin pedir y
        espera; al confirmarse el manual, el paso relee con todo bloqueado, ve ``ya_pedido`` y no crea nada. Sin el bloqueo común (cuenta de Ana e invernadero) habría dos pedidos."""
        resultados = correr_a_la_vez(
            self.pedido_manual([(self.lechuga, "24"), (self.nutriente, "6")]), self.generar(), primera="a"
        )
        self.assertIsInstance(resultados["a"], Pedido)
        self.assertIsInstance(resultados["b"], ResumenDePaso)
        self.assertEqual((resultados["b"].procesados, resultados["b"].creados), (1, 0))
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(DetallePedido.objects.count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_pedido").count(), 1)
        self.assertEqual(Notificacion.objects.filter(titulo__contains="creado automáticamente").count(), 0)

    def test_ext_5b_si_el_manual_toma_solo_uno_el_paso_pide_el_otro(self):
        """Extensión 5b y 1b: el manual toma solo la lechuga; el paso (releído con todo bloqueado) pide el nutriente y nada más: ningún par insumo–invernadero queda en dos pedidos."""
        resultados = correr_a_la_vez(self.pedido_manual([(self.lechuga, "24")]), self.generar(), primera="a")
        self.assertEqual(resultados["b"].creados, 1)
        self.assertEqual(Pedido.objects.count(), 2)
        pares = list(DetallePedido.objects.values_list("insumo_invernadero_id", flat=True))
        self.assertCountEqual(pares, [self.lechuga.pk, self.nutriente.pk])
        self.assertEqual(DetallePedido.objects.get(insumo_invernadero=self.nutriente).cantidad_detalle, Decimal("6"))

    def test_regla_dos_corridas_a_la_vez_crean_un_solo_pedido(self):
        """D-56 punto 4 y extensión 1a (idempotencia): dos corridas del paso a la vez (dos procesos, o el cron y una a mano) crean un solo pedido: la segunda espera la cuenta de Ana, relee
        y ve los insumos ya pedidos."""
        resultados = correr_a_la_vez(self.generar(), self.generar(), primera="a")
        self.assertEqual(sorted(r.creados for r in resultados.values()), [0, 1])
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(DetallePedido.objects.count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_pedido").count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=self.ana).count(), 1)

    def test_regla_dos_corridas_seguidas_no_duplican(self):
        """D-56 punto 4: la misma fecha dos veces seguidas, sin concurrencia, deja un solo pedido y un solo aviso."""
        self.generar()()
        self.generar()()
        self.assertEqual((Pedido.objects.count(), Notificacion.objects.filter(destinatario=self.ana).count()), (1, 1))
