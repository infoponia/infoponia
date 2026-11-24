# Pruebas de los modelos de COM-05a1 (paso 1): `Entrega`, `DetalleEntrega` y `AlertaComercial.entrega`, una por restricción de la base (la viola y no la viola); el alcance
# por usuario; las fábricas `entrega`, `transportista_con_vehiculo` y `verificar_invariantes_de_entregas` (que detecta lo que la base no puede vigilar); y que una `Entrega`
# real no aparece en las pantallas de `produccion` y `cancelar_orden` la rechaza (confirma lo que PRD-01 ya dejó hecho, D-67 punto 1: no lo reprograma).
# Fuente: docs/modelo/comercial.md («Entrega», «DetalleEntrega», «AlertaComercial»), D-66 puntos 2 y 3 y D-67 punto 1.

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from comercial.models import AlertaComercial, DetalleEntrega, Entrega
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    entrega,
    escenario_comercial,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
)
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_alerta, crear_vendedor
from produccion.errores import ErrorDeProduccion
from produccion.models import OrdenTrabajo
from produccion.servicios import ordenes
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


def viola(prueba, operacion):
    """Ejecuta `operacion` dentro de un savepoint y verifica que la base la rechace con IntegrityError."""
    with prueba.assertRaises(IntegrityError), transaction.atomic():
        operacion()


class Base(ConDatosDeInventario, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 500)
        cls.venta = compra_venta(cls.e)
        cls.detalle = detalle(cls.venta, cls.e.variedad, 50)
        cls.reserva = reserva_lista(cls.detalle, cls.lote, 50)

    def crear(self, **campos):
        """Una `Entrega` cruda de la venta de la clase con lo mínimo y los `campos` pisados."""
        valores = dict(
            tipo_orden="entrega",
            numero=ordenes.siguiente_numero(),
            fecha_programada_orden=HOY,
            invernadero=self.e.invernadero,
            contrato_entrega_id=self.venta.pk,
            modalidad_entrega="envio",
            direccion_destino=self.e.direccion,
        )
        valores.update(campos)
        return Entrega.objects.create(**valores)


class RestriccionesDeEntregaTests(Base):
    def test_regla_destino_segun_modalidad_con_envio_hace_falta_direccion(self):
        """Modelo, «Entrega»: `modalidad_entrega = envio` ⇔ `direccion_destino` no nula."""
        viola(self, lambda: self.crear(direccion_destino=None))
        self.assertEqual(self.crear().modalidad_entrega, "envio")

    def test_regla_destino_segun_modalidad_con_retiro_no_hay_direccion(self):
        """Modelo, «Entrega»: con retiro el destino es el invernadero, así que `direccion_destino` es nula."""
        viola(self, lambda: self.crear(modalidad_entrega="retiro"))
        self.assertTrue(self.crear(modalidad_entrega="retiro", direccion_destino=None).es_retiro)

    def test_regla_destino_segun_modalidad_rechaza_una_modalidad_desconocida(self):
        """La restricción de destino cubre la lista cerrada de modalidades."""
        viola(self, lambda: self.crear(modalidad_entrega="correo"))

    def test_regla_25_de_8_8_un_retiro_no_tiene_transportista(self):
        """Regla 25 de 8.8: `modalidad_entrega = retiro` ⇒ `transportista` nulo; con envío sí puede tenerlo."""
        t = transportista_con_vehiculo(self.e.invernadero)
        viola(self, lambda: self.crear(modalidad_entrega="retiro", direccion_destino=None, transportista=t))
        self.assertEqual(self.crear(transportista=t).transportista_id, t.pk)

    def test_regla_aviso_de_atrasada_exige_transportista(self):
        """Modelo, «Entrega»: `aviso_atrasada_para` no nula ⇒ `transportista` no nulo."""
        t = transportista_con_vehiculo(self.e.invernadero)
        viola(self, lambda: self.crear(aviso_atrasada_para=HOY))
        self.assertEqual(self.crear(transportista=t, aviso_atrasada_para=HOY).aviso_atrasada_para, HOY)
        self.assertIsNone(self.crear().recordatorio_para)  # el recordatorio, en cambio, no lo exige

    def test_regla_la_confirmacion_del_cliente_tiene_dos_valores(self):
        """Modelo, «Entrega»: `estado_confirmacion_cliente` es nulo, `no_confirmado` o `confirmado`."""
        viola(self, lambda: self.crear(estado_confirmacion_cliente="tal_vez"))
        self.assertEqual(self.crear(estado_confirmacion_cliente="confirmado").estado_confirmacion_cliente, "confirmado")

    def test_regla_el_aviso_al_cliente_tiene_tres_valores(self):
        """D-66 punto 12: `estado_aviso_cliente` es nulo, `enviado`, `pendiente_envio` o `sin_correo`."""
        viola(self, lambda: self.crear(estado_aviso_cliente="quizas"))
        self.assertEqual(self.crear(estado_aviso_cliente="sin_correo").estado_aviso_cliente, "sin_correo")

    def test_d66_la_entrega_es_una_orden_de_tipo_entrega_sin_agronomo(self):
        """D-66 punto 2: hija multitabla de `OrdenTrabajo`; la planifica InfoPonia (`agronomo` nulo) y nace «a realizar»."""
        nueva = self.crear()
        orden = OrdenTrabajo.objects.get(pk=nueva.pk)
        self.assertEqual((orden.tipo_orden, orden.estado_orden, orden.agronomo_id), ("entrega", "a_realizar", None))
        self.assertEqual(nueva.codigo, f"OT-{nueva.numero:04d}")
        self.assertEqual(self.venta.entregas.get().pk, nueva.pk)


class RestriccionesDeLineaDeEntregaTests(Base):
    def setUp(self):
        self.entrega = self.crear()

    def linea(self, **campos):
        valores = dict(entrega=self.entrega, detalle_venta=self.detalle, precio_unitario="100.00")
        valores.update(campos)
        return DetalleEntrega.objects.create(**valores)

    def test_c4_exactamente_uno_de_venta_y_suministro(self):
        """C4: exactamente una de `detalle_venta` y `detalle_suministro`: ninguna, o las dos, se rechaza."""
        s = suministro(self.e)
        d = detalle_suministro(s, self.e.variedad)
        viola(self, lambda: self.linea(detalle_venta=None))
        viola(self, lambda: self.linea(detalle_suministro=d, fecha_periodo=HOY))
        self.assertEqual(self.linea().detalle_venta_id, self.detalle.pk)

    def test_regla_el_periodo_va_con_el_detalle_de_suministro(self):
        """Modelo, «DetalleEntrega»: `detalle_suministro` no nulo ⇔ `fecha_periodo` no nula."""
        d = detalle_suministro(suministro(self.e), self.e.variedad)
        viola(self, lambda: self.linea(detalle_venta=None, detalle_suministro=d))
        viola(self, lambda: self.linea(fecha_periodo=HOY))
        linea = self.linea(detalle_venta=None, detalle_suministro=d, fecha_periodo=d.fecha_primer_entrega)
        self.assertEqual(linea.fecha_periodo, d.fecha_primer_entrega)

    def test_regla_una_linea_por_detalle_de_venta_en_cada_entrega(self):
        """Modelo: único `(entrega, detalle_venta)`; el mismo detalle en otra entrega sí se puede (por ejemplo, una cancelada)."""
        self.linea()
        viola(self, lambda: self.linea())
        otra = self.crear()
        self.assertEqual(DetalleEntrega.objects.create(entrega=otra, detalle_venta=self.detalle, precio_unitario="100.00").entrega_id, otra.pk)

    def test_regla_una_linea_por_periodo_en_cada_entrega(self):
        """Modelo: único `(entrega, detalle_suministro, fecha_periodo)`; otro período del mismo detalle sí se puede."""
        d = detalle_suministro(suministro(self.e), self.e.variedad)
        f = d.fecha_primer_entrega
        self.linea(detalle_venta=None, detalle_suministro=d, fecha_periodo=f)
        viola(self, lambda: self.linea(detalle_venta=None, detalle_suministro=d, fecha_periodo=f))
        self.assertIsNotNone(self.linea(detalle_venta=None, detalle_suministro=d, fecha_periodo=f + timedelta(days=7)).pk)

    def test_regla_el_precio_unitario_es_mayor_que_cero(self):
        """Modelo: `precio_unitario > 0`."""
        viola(self, lambda: self.linea(precio_unitario="0.00"))
        self.assertEqual(str(self.linea(precio_unitario="0.01").precio_unitario), "0.01")

    def test_regla_la_cantidad_entregada_es_nula_o_no_negativa(self):
        """Modelo: `cant_entregada` nula (hasta concretar) o `>= 0`; el monto a pagar también nace vacío."""
        linea = self.linea()
        self.assertIsNone(linea.cant_entregada)
        self.assertIsNone(linea.monto_pagar)
        viola(self, lambda: DetalleEntrega.objects.filter(pk=linea.pk).update(cant_entregada=-1))
        DetalleEntrega.objects.filter(pk=linea.pk).update(cant_entregada=0)

    def test_r150_una_linea_se_asocia_a_varias_reservas_y_una_reserva_a_varias_lineas(self):
        """R150: `reservas` es una M2M; una reserva puede estar en las líneas de entregas canceladas (historial, regla 4 de 8.8)."""
        linea = self.linea()
        otra = reserva_lista(self.detalle, self.lote, 5)
        linea.reservas.set([self.reserva, otra])
        self.assertEqual(self.reserva.lineas_de_entrega.count(), 1)
        self.assertEqual(linea.reservas.count(), 2)


class RestriccionDeLaAlertaTests(Base):
    def alerta(self, **origen):
        a = crear_alerta(self.e.invernadero, "comercial_entrega_sin_transportista")
        return AlertaComercial.objects.create(alerta=a, **origen)

    def test_d63_la_entrega_es_un_origen_valido_de_la_alerta(self):
        """D-63 y D-66 punto 10: `AlertaComercial.entrega` es uno de los orígenes posibles (exactamente uno cargado)."""
        entrega_ = self.crear()
        self.assertEqual(self.alerta(entrega=entrega_).entrega_id, entrega_.pk)

    def test_d63_sin_ningun_origen_se_rechaza(self):
        """D-63 punto 1: ninguna FK de origen cargada se rechaza."""
        viola(self, lambda: self.alerta())

    def test_d63_la_entrega_y_otro_origen_a_la_vez_se_rechazan(self):
        """D-63 punto 1: dos orígenes a la vez se rechazan, también la entrega junto con un suministro."""
        s = suministro(self.e)
        viola(self, lambda: self.alerta(entrega=self.crear(), suministro=s))


class AlcanceDeEntregasTests(Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.t = transportista_con_vehiculo(cls.e.invernadero)
        cls.entrega = entrega(cls.venta, [cls.reserva], transportista=cls.t)

    def ids(self, actor):
        return list(Entrega.objects.en_alcance_de(actor).values_list("pk", flat=True))

    def test_regla_alcance_el_gerente_ve_todas(self):
        """D-28 y modelo, «Alcance»: el Gerente activo, todas."""
        self.assertEqual(self.ids(crear_gerente()), [self.entrega.pk])

    def test_regla_alcance_el_vendedor_ve_solo_las_de_sus_contratos(self):
        """D-28: el Vendedor activo, las de sus contratos; otro Vendedor, ninguna."""
        self.assertEqual(self.ids(self.e.vendedor), [self.entrega.pk])
        self.assertEqual(self.ids(crear_vendedor(email="otro.vendedor@infoponia.com")), [])

    def test_regla_alcance_el_agronomo_ve_las_de_sus_invernaderos(self):
        """Modelo, «Alcance»: el Agrónomo activo, las de sus invernaderos a cargo."""
        self.assertEqual(self.ids(self.e.agronomo), [self.entrega.pk])

    def test_regla_alcance_el_transportista_ve_las_suyas(self):
        """Modelo, «Alcance»: el Transportista activo, las suyas; otro, ninguna."""
        self.assertEqual(self.ids(self.t), [self.entrega.pk])
        self.assertEqual(self.ids(transportista_con_vehiculo(self.e.invernadero)), [])

    def test_regla_alcance_el_capataz_y_una_cuenta_inactiva_no_ven_ninguna(self):
        """D-28: cualquier otro rol, o una cuenta inactiva, ninguna."""
        self.assertEqual(self.ids(self.e.capataz), [])
        self.assertEqual(self.ids(None), [])
        inactivo = crear_vendedor(email="inactivo.vendedor@infoponia.com", activo=False)
        self.assertEqual(self.ids(inactivo), [])


class FabricasDeEntregasTests(Base):
    def test_la_fabrica_arma_una_entrega_valida_de_una_venta(self):
        """La fábrica `entrega` escribe los datos copiados como `_crear_entrega` y no rompe ningún invariante."""
        e = entrega(self.venta, [self.reserva])
        self.assertEqual((e.contrato_entrega_id, e.modalidad_entrega, e.direccion_destino_id), (self.venta.pk, "envio", self.venta.direccion_envio_id))
        self.assertIsNone(e.estado_confirmacion_cliente)
        self.assertEqual(e.lineas.get().reservas.get(), self.reserva)
        verificar_invariantes_de_entregas()

    def test_la_fabrica_arma_una_entrega_de_retiro_y_otra_de_suministro(self):
        """Un retiro no tiene dirección ni transportista; un suministro nace `no_confirmado` con la dirección de su detalle."""
        retiro = compra_venta(self.e, modalidad="retiro")
        d = detalle(retiro, self.e.variedad, 5)
        e1 = entrega(retiro, [reserva_lista(d, self.lote, 5)])
        self.assertEqual((e1.modalidad_entrega, e1.direccion_destino_id, e1.transportista_id), ("retiro", None, None))
        s = suministro(self.e)
        ds = detalle_suministro(s, self.e.variedad, cantidad=10)
        r = reserva_lista(None, self.lote, 10, fecha_entrega=ds.fecha_primer_entrega, detalle_suministro=ds)
        e2 = entrega(s, [r])
        self.assertEqual((e2.estado_confirmacion_cliente, e2.direccion_destino_id), ("no_confirmado", ds.direccion_id))
        self.assertEqual(e2.lineas.get().fecha_periodo, ds.fecha_primer_entrega)
        verificar_invariantes_de_entregas()

    def test_la_fabrica_acepta_una_fecha_pasada_y_los_estados_cerrados(self):
        """Una entrega atrasada baja su fecha de creación; una cancelada lleva fecha de resolución y motivo (restricciones de la orden)."""
        atrasada = entrega(self.venta, [self.reserva], fecha=HOY - timedelta(days=2))
        self.assertEqual(atrasada.fecha_programada_orden, HOY - timedelta(days=2))
        cancelada = entrega(self.venta, [self.reserva], estado="cancelada")
        self.assertEqual((cancelada.estado_orden, cancelada.motivo_cancelacion), ("cancelada", "Motivo de prueba"))
        verificar_invariantes_de_entregas()  # la atrasada y la cancelada comparten reserva: solo una está viva

    def test_transportista_con_vehiculo_arma_la_logistica_del_invernadero(self):
        """El transportista queda en su invernadero con un vehículo activo de la capacidad pedida, en ruta si se pide."""
        t = transportista_con_vehiculo(self.e.invernadero, "400", en_ruta=True)
        self.assertEqual(t.invernadero_asignado.invernadero_id, self.e.invernadero.pk)
        t.vehiculo.refresh_from_db()
        self.assertEqual(t.vehiculo.capacidad_carga, Decimal("400.00"))
        self.assertTrue(t.vehiculo.esta_en_ruta(HOY))

    def test_invariantes_detecta_una_linea_de_otro_contrato(self):
        """Modelo, «Entrega»: el contrato de la entrega coincide con el de sus líneas (D-66 punto 3, refuerzos)."""
        otra_venta = compra_venta(self.e)
        otro_detalle = detalle(otra_venta, self.e.variedad, 5)
        e = entrega(self.venta, [self.reserva])
        DetalleEntrega.objects.filter(entrega=e).update(detalle_venta=otro_detalle)
        with self.assertRaisesRegex(AssertionError, "de otro contrato"):
            verificar_invariantes_de_entregas()

    def test_invariantes_detecta_otra_modalidad_y_otro_destino(self):
        """Modelo, «Entrega»: la modalidad y el destino coinciden con los de la venta."""
        e = entrega(self.venta, [self.reserva])
        Entrega.objects.filter(pk=e.pk).update(modalidad_entrega="retiro", direccion_destino=None)
        with self.assertRaisesRegex(AssertionError, "modalidad distinta"):
            verificar_invariantes_de_entregas()

    def test_invariantes_detecta_una_reserva_en_dos_entregas_no_canceladas(self):
        """Regla 4 de 8.8: una reserva tiene a lo sumo una línea en una entrega no cancelada; en una cancelada, sí (historial)."""
        entrega(self.venta, [self.reserva], estado="cancelada")
        entrega(self.venta, [self.reserva])
        verificar_invariantes_de_entregas()
        entrega(self.venta, [self.reserva])
        with self.assertRaisesRegex(AssertionError, "2 entregas no canceladas"):
            verificar_invariantes_de_entregas()

    def test_invariantes_detecta_una_reserva_de_otro_invernadero(self):
        """Regla 3 de 8.8: todas las reservas de la entrega son del invernadero de origen."""
        e = entrega(self.venta, [self.reserva])
        from comercial.tests.fabricas import segundo_invernadero

        sur = segundo_invernadero(self.e)
        Entrega.objects.filter(pk=e.pk).update(invernadero=sur.invernadero)
        with self.assertRaisesRegex(AssertionError, "de otro invernadero"):
            verificar_invariantes_de_entregas()

    def test_invariantes_detecta_una_confirmacion_en_una_venta(self):
        """Modelo, «Entrega»: `estado_confirmacion_cliente` no nulo ⇔ el contrato es un suministro."""
        e = entrega(self.venta, [self.reserva])
        Entrega.objects.filter(pk=e.pk).update(estado_confirmacion_cliente="no_confirmado")
        with self.assertRaisesRegex(AssertionError, "confirmación del cliente"):
            verificar_invariantes_de_entregas()


class LaEntregaNoEsDeProduccionTests(Base):
    """D-67 punto 1 (lo dejó hecho PRD-01): una `Entrega` real no aparece en las pantallas de `produccion` y `cancelar_orden` la rechaza."""

    def setUp(self):
        self.entrega = entrega(self.venta, [self.reserva])

    def test_d67_la_entrega_no_esta_en_la_lista_de_ordenes(self):
        """`lista_de_ordenes` filtra por `TIPOS_DE_PRODUCCION`: la entrega no aparece, ni siquiera pidiendo su tipo."""
        self.assertNotIn(self.entrega.pk, [f.orden_id for f in ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes())])
        self.assertNotIn(self.entrega.pk, [f.orden_id for f in ordenes.lista_de_ordenes(self.e.agronomo, ordenes.FiltrosDeOrdenes(tipo="entrega"))])

    def test_d67_la_entrega_no_esta_entre_las_cancelables(self):
        """`ordenes_cancelables` no la lista."""
        self.assertEqual(ordenes.ordenes_cancelables(self.e.agronomo), [])

    def test_d67_la_entrega_no_esta_en_la_bandeja_del_capataz(self):
        """La bandeja del Capataz une solo las hijas con Capataz: la entrega no tiene."""
        bandeja = ordenes.bandeja_del_capataz(self.e.capataz)
        self.assertEqual([*bandeja.vencidas, *bandeja.hoy, *bandeja.proximas], [])

    def test_d67_cancelar_orden_rechaza_una_entrega_y_no_la_cambia(self):
        """`cancelar_orden` solo acepta `TIPOS_QUE_CANCELA_PRODUCCION`: con una entrega, `orden_no_cancelable`, sin cambiarla (D-66 punto 13)."""
        with self.assertRaises(ErrorDeProduccion) as contexto:
            ordenes.cancelar_orden(self.e.agronomo, self.entrega.pk, "No va")
        self.assertEqual(contexto.exception.codigo, "orden_no_cancelable")
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.estado_orden, "a_realizar")
