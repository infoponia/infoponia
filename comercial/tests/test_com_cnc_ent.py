# Pruebas de COM-CNC-ENT · Concretar Entrega (COM-06a, pasos 3 y 4): `concrecion.entregas_concretables`, `datos_de_concrecion`, `resumen_de_concrecion`, `repartir`, `concretar_entrega`,
# `crear_discrepancia`, `intentos_fallidos` y el intento fallido (extensión 4a, `rutas.registrar_intento_fallido`). Una por postcondición (a a g, i a o, p y q; e, g y h con su asiento: CON-04c) y por
# extensión (1a, 3a, 4a, 5a, 5b, 7a, 8a, 8b, 9a, 10a, 10b, 13a, 14a, 14b, 14c, 15a); el reparto; la devolución a una partida vencida, a una agotada y desde un lote con la fecha límite pasada; el
# exceso de envases; un detalle de venta en dos entregas; el fin del detalle y del suministro (y la rescisión acordada, que no se toca); que todo es atómico y sin consultas por fila.
# Fuente: docs/casos_de_uso/comercial/rutas.md («COM-CNC-ENT» y «Cómo se aplica», «Concretar» e «Intento fallido»), D-66, D-68 y las secciones 8 y 10 de docs/api/produccion.md.

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from comercial.models import (
    AlertaComercial,
    CompraVenta,
    DetalleEntrega,
    DetalleSuministro,
    DetalleVenta,
    DiscrepanciaEntrega,
    EnlaceCliente,
    Entrega,
    IntentoFallido,
    PagoCliente,
    ReservaStock,
    Suministro,
)
from comercial.servicios import calendario, concrecion, entregas, rutas, suministros
from comercial.servicios.concrecion import DatosDeConcrecion, Origen
from comercial.tests.fabricas import (
    compra_venta,
    con_cosecha_concretada,
    detalle,
    detalle_suministro,
    entrega,
    entrega_concretable,
    envase,
    escenario_comercial,
    iniciar_ruta_de,
    partida_cosechada,
    reserva,
    reserva_lista,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_solicitudes,
)
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio_abierto, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.models import LoteInsumo
from inventario.tests.fabricas import ConDatosDeInventario, verificar_invariantes
from maestros.models import Alerta
from produccion.models import Consumo, Merma, MovimientoStock, ReservaInsumo, StockCosechado
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HOY = timezone.localdate()


def codigos(error):
    """Los códigos de un `ValidationError` con o sin `error_dict`."""
    if hasattr(error, "error_dict"):
        return [e.code for lista in error.error_dict.values() for e in lista]
    return [e.code for e in error.error_list]


def campos(error):
    """Los campos con error de un `ValidationError`."""
    return sorted(error.error_dict) if hasattr(error, "error_dict") else []


def origen(clave, aporte, limite_en_dias=30):
    """Un `Origen` mínimo para las pruebas de `repartir` (función pura)."""
    return Origen(clave, "partida", None, None, None, aporte, HOY + timedelta(days=limite_en_dias), Decimal("1.0000"), None)


class Base(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero con su Agrónomo y su Vendedor, un lote de 5000 plantas maduras y un Gerente."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)

    # ---- armado ----

    def concretable(self, **opciones):
        """Una entrega lista para concretar (ver `entrega_concretable`)."""
        return entrega_concretable(self.e, self.lote, **opciones)

    def D(self, x, **datos):
        """Los `DatosDeConcrecion` con lo que hace falta por omisión: el medio de pago de una compra-venta y «no usé envases» si la entrega no tiene envasado."""
        datos.setdefault("medio_pago", "efectivo")
        if x.envases is None:
            datos.setdefault("sin_envases", True)
        return DatosDeConcrecion(**datos)

    def actor(self, x):
        return x.transportista or self.e.vendedor

    def resumen(self, x, actor=None, **datos):
        return concrecion.resumen_de_concrecion(actor or self.actor(x), x.entrega.pk, self.D(x, **datos))

    def concretar(self, x, actor=None, **datos):
        """Los dos pasos como la pantalla: el resumen (con su huella) y la confirmación."""
        actor = actor or self.actor(x)
        datos = self.D(x, **datos)
        resumen = concrecion.resumen_de_concrecion(actor, x.entrega.pk, datos)
        return concrecion.concretar_entrega(actor, x.entrega.pk, datos, resumen.huella)

    def linea(self, x):
        return x.entrega.lineas.get()

    def refrescar(self, x):
        return Entrega.objects.get(pk=x.entrega.pk)

    def avisos(self, cuenta):
        return list(Notificacion.objects.filter(destinatario=cuenta).order_by("pk"))

    def mixta(self, *, dias_atras=2, partida_limite=None):
        """Una entrega de 30 plantas de dos orígenes: 20 de un lote ya cosechado y 10 de una partida de cámara. Devuelve un `SimpleNamespace` como el de `entrega_concretable`."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 30)
        de_lote = con_cosecha_concretada(self.e, det, self.lote, reservada=20, cosechada=20, dias_atras=dias_atras)
        p = partida_cosechada(self.lote, 10, fecha_limite=partida_limite)
        de_camara = reserva(det, [(p, 10)])
        e = entrega(venta, [de_lote, de_camara], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        return SimpleNamespace(entrega=e, contrato=venta, detalle=det, transportista=t, envases=None, partida=p)


# ---- el reparto entre orígenes (función pura) ----


class RepartoTests(TestCase):
    def test_regla_con_un_solo_origen_no_hay_reparto(self):
        """Regla «Reparto entre orígenes»: con un solo origen, lo perdido y lo devuelto son los de la línea y lo entregado lo que queda."""
        (r,) = concrecion.repartir([origen("a", 50)], 5, 10)
        self.assertEqual((r.perdida, r.devuelta, r.entregada), (5, 10, 35))

    def test_regla_dos_origenes_en_proporcion_a_lo_que_aporta_cada_uno(self):
        """Lo perdido se reparte en proporción a lo que aporta cada origen (30 y 10: 4 perdidas → 3 y 1)."""
        a, b = concrecion.repartir([origen("a", 30), origen("b", 10)], 4, 0)
        self.assertEqual((a.perdida, b.perdida, a.entregada, b.entregada), (3, 1, 27, 9))

    def test_regla_perdido_y_devuelto_en_la_misma_linea_primero_lo_perdido(self):
        """Primero lo perdido y después lo devuelto, este último en proporción a lo que le queda a cada origen: 30 y 10, 4 perdidas y 6 devueltas → (3, 5) y (1, 1)."""
        a, b = concrecion.repartir([origen("a", 30), origen("b", 10)], 4, 6)
        self.assertEqual((a.perdida, a.devuelta, a.entregada), (3, 5, 22))
        self.assertEqual((b.perdida, b.devuelta, b.entregada), (1, 1, 8))

    def test_regla_las_unidades_que_faltan_van_a_los_de_mayor_parte_decimal(self):
        """Cada origen recibe la parte entera de su cuota (1, 0 y 0); las dos que faltan van de a una a los de mayor parte decimal: 20, 10 y 10 con 3 perdidas → cuotas 1,5; 0,75; 0,75 →
        los de 0,75 (mayor que 0,5) se llevan la suya: 1, 1, 1."""
        a, b, c = concrecion.repartir([origen("a", 20, 30), origen("b", 10, 30), origen("c", 10, 30)], 3, 0)
        self.assertEqual((a.perdida, b.perdida, c.perdida), (1, 1, 1))
        self.assertEqual(a.perdida + b.perdida + c.perdida, 3)

    def test_regla_si_empatan_la_parte_decimal_gana_el_que_mas_aporta(self):
        """Empate de la parte decimal: al que más aporta (3 y 1 con 2 perdidas → cuotas 1,5 y 0,5 → 2 y 0)."""
        a, b = concrecion.repartir([origen("a", 3), origen("b", 1)], 2, 0)
        self.assertEqual((a.perdida, b.perdida), (2, 0))

    def test_regla_si_siguen_empatados_gana_el_de_fecha_limite_mas_proxima(self):
        """Empate también en el aporte: al de fecha límite más próxima (aunque sea el segundo de la lista)."""
        a, b = concrecion.repartir([origen("a", 10, 20), origen("b", 10, 5)], 1, 0)
        self.assertEqual((a.perdida, b.perdida), (0, 1))

    def test_regla_con_tres_origenes_iguales_las_dos_unidades_van_a_las_fechas_mas_proximas(self):
        """Tres orígenes iguales y 2 perdidas: se llevan una cada uno los dos de fecha límite más próxima."""
        a, b, c = concrecion.repartir([origen("a", 10, 30), origen("b", 10, 10), origen("c", 10, 20)], 2, 0)
        self.assertEqual((a.perdida, b.perdida, c.perdida), (0, 1, 1))

    def test_regla_si_todo_empata_gana_la_menor_clave_y_nunca_se_pierde_una_unidad(self):
        """Último desempate (para que sea determinista): la menor clave. Siempre se reparte exactamente lo perdido y lo devuelto."""
        a, b = concrecion.repartir([origen("b", 10), origen("a", 10)], 1, 0)
        self.assertEqual((a.perdida, b.perdida), (0, 1))
        for perdida, devuelta in ((0, 0), (7, 0), (3, 9), (20, 0)):
            partes = concrecion.repartir([origen("a", 13), origen("b", 7)], perdida, devuelta)
            self.assertEqual((sum(p.perdida for p in partes), sum(p.devuelta for p in partes), sum(p.entregada for p in partes)), (perdida, devuelta, 20 - perdida - devuelta))


# ---- la concreción ----


class ComCncEntServicioTests(Base):
    # ---- el escenario principal y las postcondiciones en toda entrega ----

    def test_flujo_principal_compra_venta_unica_entrega_sin_perdidas_ni_rechazos(self):
        """Escenario principal: una compra-venta con envío, única entrega, todo aceptado, pagado en efectivo: la entrega queda concretada, la venta concretada con su pago y el comprobante pendiente."""
        x = self.concretable()
        concretada = self.concretar(x)
        self.assertEqual(concretada.estado_orden, "concretada")
        venta = CompraVenta.objects.get(pk=x.contrato.pk)
        self.assertEqual((venta.estado_venta, venta.fecha_concrecion_venta), ("concretada", HOY))
        pago = PagoCliente.objects.get(compra_venta=venta)
        self.assertEqual((pago.monto_pagado, pago.medio_pago, pago.estado_pago, pago.fecha_pago, pago.cliente_id), (Decimal("5000.00"), "efectivo", "vigente", HOY, venta.cliente_id))

    def test_post_a_la_entrega_pasa_a_concretada_con_la_fecha_de_hoy(self):
        """Postcondición a: «a realizar» → «concretada», con la fecha de resolución igual a la fecha actual (sin fechas retroactivas)."""
        x = self.concretable()
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        e = self.concretar(x)
        self.assertEqual((e.estado_orden, self.refrescar(x).fecha_resolucion_orden), ("concretada", HOY))

    def test_post_b_cada_linea_queda_con_cantidades_precio_y_monto_y_la_entrega_con_su_total(self):
        """Postcondición b: por línea, entregada, perdida, devuelta, precio unitario y monto a pagar (entregada × precio); la entrega, el monto total."""
        x = self.concretable(cantidad=50, precio="12.34")
        self.concretar(x, llego={self.linea(x).pk: "45"})
        linea, e = DetalleEntrega.objects.get(pk=self.linea(x).pk), self.refrescar(x)
        self.assertEqual((linea.cant_entregada, linea.cant_perdida, linea.cant_devuelta, linea.precio_unitario), (45, 5, 0, Decimal("12.34")))
        self.assertEqual((linea.monto_pagar, e.monto_total_entrega, e.fecha_vencimiento_pago), (Decimal("555.30"), Decimal("555.30"), None))

    def test_post_c_las_reservas_de_stock_pasan_a_entregada(self):
        """Postcondición c: cada reserva de stock de la entrega pasa a «entregada»."""
        x = self.concretable()
        self.concretar(x)
        self.assertEqual(ReservaStock.objects.get(pk=x.reserva.pk).estado_reserva, "entregada")

    def test_post_d_la_partida_baja_lo_que_salio_y_se_registra_el_egreso_de_camara(self):
        """Postcondición d: la cantidad disponible de la partida se reduce en lo que salió en el vehículo (queda «agotado» si llega a 0) y se registra un «egreso de cámara» originado en la entrega."""
        x = self.concretable()
        partida = x.reserva.lineas.get().partida
        self.concretar(x)
        partida.refresh_from_db()
        self.assertEqual((partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado), (0, "agotado"))
        egreso = MovimientoStock.objects.get(partida=partida, tipo_movimiento="egreso_de_camara")
        self.assertEqual((egreso.cantidad, egreso.origen_id), (50, x.entrega.pk))

    def test_post_e_la_diferencia_se_registra_como_merma_de_entrega_sin_asiento(self):
        """Postcondición e (sin asiento, D-57) y 5a: una merma «daño en la entrega» por el lote de origen, con la cantidad perdida, el responsable, la descripción, la entrega y el invernadero, sin etapa."""
        x = self.concretable()
        self.concretar(x, llego={self.linea(x).pk: "45"}, descripcion_perdida="Se cayó la bandeja")
        merma = Merma.objects.get()
        self.assertEqual((merma.causa, merma.cant_merma, merma.orden_id, merma.lote_id, merma.etapa_id, merma.responsable_id), ("dano_en_entrega", 5, x.entrega.pk, self.lote.pk, None, x.transportista.pk))
        self.assertIn("Se cayó la bandeja", merma.descripcion_evento)
        self.assertEqual(merma.invernadero_id, self.e.invernadero.pk)

    def test_post_e_una_merma_por_cada_lote_de_origen_sumando_las_de_sus_origenes(self):
        """Regla «Merma de entrega»: una por cada lote de origen afectado (R144), aunque la línea tome de un lote cosechado y de una partida de ese mismo lote."""
        x = self.mixta()
        self.concretar(x, llego={x.entrega.lineas.get().pk: "27"})
        (merma,) = Merma.objects.all()
        self.assertEqual((merma.cant_merma, merma.lote_id), (3, self.lote.pk))

    def test_post_f_lo_devuelto_vuelve_a_la_misma_partida_con_su_fecha_limite(self):
        """Postcondición f: lo devuelto a una partida suma a su disponible (la que estaba «agotada» vuelve a «disponible»), conserva su fecha límite y registra un «ingreso a cámara» originado en la entrega."""
        x = self.concretable()
        partida = x.reserva.lineas.get().partida
        limite = partida.fecha_limite
        self.concretar(x, acepta={self.linea(x).pk: False})
        partida.refresh_from_db()
        self.assertEqual((partida.cantidad_disponible_cosechado, partida.estado_stock_cosechado, partida.fecha_limite), (50, "disponible", limite))
        ingreso = MovimientoStock.objects.filter(partida=partida, tipo_movimiento="ingreso_a_camara", origen_id=x.entrega.pk).get()
        self.assertEqual(ingreso.cantidad, 50)

    def test_post_f_lo_devuelto_de_un_lote_cosechado_crea_una_partida_con_la_vida_util_de_la_cosecha(self):
        """Postcondición f: si venía de un lote cosechado se crea una partida nueva con motivo «rechazo en la entrega», fecha límite = fecha de la cosecha + postcosecha y el costo unitario de la cosecha."""
        x = self.mixta()
        antes = set(StockCosechado.objects.values_list("pk", flat=True))
        self.concretar(x, acepta={x.entrega.lineas.get().pk: False})
        nueva = StockCosechado.objects.exclude(pk__in=antes).get()
        duracion = self.e.variedad.duracion_post_cosecha
        self.assertEqual((nueva.motivo_cosechado, nueva.cantidad_disponible_cosechado, nueva.costo_unitario_cosechado), ("rechazo_en_entrega", 20, Decimal("2.5000")))
        self.assertEqual(nueva.fecha_limite, HOY - timedelta(days=2) + timedelta(days=duracion))
        self.assertEqual(nueva.lote_id, self.lote.pk)
        x.partida.refresh_from_db()
        self.assertEqual(x.partida.cantidad_disponible_cosechado, 10)

    def test_post_f_se_dispara_la_asignacion_automatica_de_camara_despues_de_confirmar(self):
        """Postcondición f: lo devuelto dispara PROD-ASG-CAM, siempre con `on_commit` (D-64 punto 9)."""
        x = self.concretable()
        with mock.patch("comercial.servicios.concrecion.camara_comercial.asignar_camara") as asignar, self.captureOnCommitCallbacks(execute=True):
            self.concretar(x, acepta={self.linea(x).pk: False})
        asignar.assert_called_once()

    def test_regla_la_devolucion_a_una_partida_vencida_se_registra_como_merma_por_vencimiento(self):
        """Regla 29 de 8.6: si la partida ya venció, lo devuelto se registra como merma por vencimiento y la partida no recupera disponible."""
        x = self.concretable()
        partida = x.reserva.lineas.get().partida
        StockCosechado.objects.filter(pk=partida.pk).update(fecha_limite=HOY - timedelta(days=1))
        self.concretar(x, acepta={self.linea(x).pk: False})
        self.assertEqual(Merma.objects.get().causa, "vencimiento_en_camara")
        partida.refresh_from_db()
        self.assertEqual(partida.cantidad_disponible_cosechado, 0)

    def test_regla_lo_devuelto_desde_un_lote_con_la_fecha_limite_pasada_nace_vencido(self):
        """Regla «Lo devuelto a la cámara»: si la fecha límite de la partida nueva ya pasó, la partida vence enseguida (con su merma por vencimiento)."""
        x = self.mixta(dias_atras=400)
        antes = set(StockCosechado.objects.values_list("pk", flat=True))
        self.concretar(x, acepta={x.entrega.lineas.get().pk: False})
        nueva = StockCosechado.objects.exclude(pk__in=antes).get()
        self.assertEqual((nueva.estado_stock_cosechado, nueva.cantidad_disponible_cosechado), ("vencido", 0))
        self.assertTrue(Merma.objects.filter(causa="vencimiento_en_camara", cant_merma=20).exists())

    def test_post_g_con_envasado_cada_reserva_de_insumo_queda_consumida_con_su_consumo_y_su_salida_de_stock(self):
        """Postcondición g: la reserva queda «consumida» con utilizada y devuelta; se registra un consumo de la entrega (sin asiento, D-57) y el stock del envase baja en lo consumido."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, utilizada={x.envases.pk: "10"})
        reserva_ = ReservaInsumo.objects.get(orden_id=x.entrega.pk)
        self.assertEqual((reserva_.estado, reserva_.cantidad_utilizada, reserva_.cantidad_devuelta), ("consumida", Decimal("10"), Decimal("0")))
        consumo = Consumo.objects.get()
        self.assertEqual((consumo.orden_id, consumo.cant_consumo, consumo.insumo_invernadero_id), (x.entrega.pk, Decimal("10"), x.envases.pk))
        self.assertEqual(sum(LoteInsumo.objects.filter(insumo_invernadero=x.envases).values_list("cantidad_disponible", flat=True)), Decimal("20"))
        verificar_invariantes(x.envases)

    def test_post_g_lo_devuelto_no_genera_ningun_registro_de_stock(self):
        """Postcondición g: lo devuelto nunca salió del stock; con 6 utilizadas y 2 devueltas se consumen 8 (la reservada menos la devuelta) y el stock baja 8."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, utilizada={x.envases.pk: "6"}, devuelta={x.envases.pk: "2"})
        reserva_ = ReservaInsumo.objects.get(orden_id=x.entrega.pk)
        self.assertEqual((reserva_.cantidad_utilizada, reserva_.cantidad_devuelta), (Decimal("6"), Decimal("2")))
        self.assertEqual(Consumo.objects.get().cant_consumo, Decimal("8"))
        self.assertEqual(sum(LoteInsumo.objects.filter(insumo_invernadero=x.envases).values_list("cantidad_disponible", flat=True)), Decimal("22"))

    def test_post_g_si_no_se_consumio_nada_la_reserva_se_cancela_y_no_hay_consumo(self):
        """Regla «Cantidad consumida»: con 0 utilizadas y todo devuelto, la reserva queda «cancelada» (con lo utilizado y lo devuelto cargados) y no hay consumo."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, utilizada={x.envases.pk: "0"}, devuelta={x.envases.pk: "10"})
        reserva_ = ReservaInsumo.objects.get(orden_id=x.entrega.pk)
        self.assertEqual((reserva_.estado, reserva_.cantidad_devuelta), ("cancelada", Decimal("10")))
        self.assertFalse(Consumo.objects.exists())

    def test_post_g_por_defecto_la_devuelta_propuesta_es_la_reservada_menos_la_utilizada(self):
        """Regla «Envases»: sin indicar la devuelta, se propone `máx(0, reservada − utilizada)`: con 4 utilizadas, 6 devueltas y se consumen 4."""
        x = self.concretable(con_envasado=True)
        resumen = self.resumen(x, utilizada={x.envases.pk: "4"})
        self.assertEqual((resumen.envases[0].devuelta, resumen.envases[0].consumo), (Decimal("6"), Decimal("4")))

    def test_post_i_se_notifica_al_vendedor_si_hubo_perdidas_o_devoluciones(self):
        """Postcondición i: si hubo pérdidas, devoluciones o rechazos, un aviso al Vendedor del contrato; sin diferencias no se avisa."""
        sin = self.concretable()
        self.concretar(sin)
        self.assertEqual(self.avisos(self.e.vendedor), [])
        con = self.concretable()
        self.concretar(con, llego={self.linea(con).pk: "45"})
        (aviso,) = self.avisos(self.e.vendedor)
        self.assertIn("se concretó con diferencias", aviso.detalle)
        self.assertIn("5 perdidas", aviso.detalle)

    def test_post_p_y_q_un_solo_registro_de_auditoria_con_lo_modificado_y_lo_creado(self):
        """Postcondiciones p y q: un registro `concrecion_entrega` del actor con la entrega, sus líneas, las reservas, la partida, el contrato, la merma, el pago, y las claves de `datos`."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, llego={self.linea(x).pk: "45"}, utilizada={x.envases.pk: "10"})
        (r,) = RegistroAuditoria.objects.filter(accion="concrecion_entrega")
        self.assertEqual(r.usuario_id, x.transportista.pk)
        modelos = {a["modelo"].split(".")[-1].lower() for a in r.afectados}
        self.assertTrue({"entrega", "detalleentrega", "reservastock", "reservainsumo", "stockcosechado", "compraventa", "merma", "pagocliente"} <= modelos, modelos)
        self.assertEqual(r.detalle["cambios"]["estado_orden"], {"antes": "a_realizar", "despues": "concretada"})
        for clave in ("mermas_creadas", "movimientos_creados", "consumos_creados", "pago"):
            self.assertIn(clave, r.detalle["datos"])
        self.assertEqual(len(set((a["modelo"], a["id"]) for a in r.afectados)), len(r.afectados))

    # ---- en una compra-venta ----

    def test_post_j_y_k_el_pago_cierra_la_venta_y_se_programa_el_comprobante(self):
        """Postcondiciones j y k: el detalle queda «confirmado» con lo entregado; en la última entrega, el pago por el total, la venta «concretada» y el comprobante de venta pendiente de envío."""
        x = self.concretable()
        self.concretar(x, medio_pago="transferencia")
        d = DetalleVenta.objects.get(pk=x.detalle.pk)
        self.assertEqual((d.estado_detalle_venta, d.cant_entregada_venta), ("confirmado", 50))
        self.assertEqual(PagoCliente.objects.get().medio_pago, "transferencia")
        self.assertEqual(self.refrescar(x).estado_aviso_cliente, "pendiente_envio")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_k_se_envia_el_comprobante_de_venta_con_lo_cobrado_y_el_medio_de_pago(self):
        """Postcondición k y 15a: después de confirmar sale el comprobante de venta (de uso interno), y la entrega queda «enviado»."""
        x = self.concretable()
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x, medio_pago="tarjeta_debito")
        (correo,) = mail.outbox
        self.assertEqual(correo.to, [self.e.cliente.email_cliente])
        self.assertIn("$5000,00", correo.body)  # el formato de moneda del proyecto usa coma decimal
        self.assertIn("Tarjeta de débito", correo.body)
        self.assertIn("uso interno", correo.body)
        self.assertEqual(self.refrescar(x).estado_aviso_cliente, "enviado")

    def test_ext_15a_si_el_correo_falla_la_concrecion_queda_y_el_paso_50_reintenta(self):
        """Extensión 15a: sin el correo del sistema la entrega queda concretada y el aviso «pendiente de envío»; el paso 50 (parte 4) reenvía el comprobante de las concretadas pendientes."""
        x = self.concretable()
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)
        self.assertEqual((self.refrescar(x).estado_orden, self.refrescar(x).estado_aviso_cliente), ("concretada", "pendiente_envio"))
        self.assertEqual(mail.outbox, [])
        with override_settings(CORREO_CONFIGURADO=True):
            entregas.planificar_entregas(HOY)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.refrescar(x).estado_aviso_cliente, "enviado")
        with override_settings(CORREO_CONFIGURADO=True):
            entregas.planificar_entregas(HOY)
        self.assertEqual(len(mail.outbox), 1)  # idempotente

    def test_regla_un_cliente_sin_correo_queda_sin_correo(self):
        """Un cliente sin correo: el aviso queda «sin correo» y no se envía nada."""
        from comercial.models import Cliente

        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        x = self.concretable()
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)
        self.assertEqual(self.refrescar(x).estado_aviso_cliente, "sin_correo")
        self.assertEqual(mail.outbox, [])

    def test_ext_7a_el_cliente_rechaza_una_linea_no_se_cobra_y_vuelve_a_la_camara(self):
        """Extensión 7a: la línea rechazada no se cobra, lo que llegó vuelve a la cámara, la reserva queda «liberada» y el detalle «rechazado»; el otro detalle se cobra."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        d1 = detalle(venta, self.e.variedad, 20)
        otra_variedad, _ = variedad_con_stock(self.e, "Rúcula 7a")
        d2 = detalle(venta, otra_variedad, 10, precio="50.00")
        lote2 = lote_maduro(self.e, 500, variedad=otra_variedad)
        r1, r2 = reserva_lista(d1, self.lote, 20), reserva_lista(d2, lote2, 10)
        e = entrega(venta, [r1, r2], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        l1, l2 = e.lineas.order_by("pk")
        x = SimpleNamespace(entrega=e, contrato=venta, transportista=t, envases=None)
        self.concretar(x, acepta={l2.pk: False})
        self.assertEqual(ReservaStock.objects.get(pk=r1.pk).estado_reserva, "entregada")
        self.assertEqual(ReservaStock.objects.get(pk=r2.pk).estado_reserva, "liberada")
        self.assertEqual(DetalleVenta.objects.get(pk=d1.pk).estado_detalle_venta, "confirmado")
        self.assertEqual(DetalleVenta.objects.get(pk=d2.pk).estado_detalle_venta, "rechazado")
        self.assertEqual(PagoCliente.objects.get().monto_pagado, Decimal("2000.00"))
        self.assertEqual(DetalleEntrega.objects.get(pk=l2.pk).cant_devuelta, 10)
        self.assertEqual(StockCosechado.objects.get(pk=r2.lineas.get().partida_id).cantidad_disponible_cosechado, 10)

    def test_ext_8a_no_es_la_ultima_entrega_no_se_cobra_y_la_ultima_cobra_el_total(self):
        """Extensiones 8a y regla «Última entrega»: la primera de dos entregas del mismo detalle no cobra; la última cobra el total de la venta y la cierra."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 100)
        e1 = entrega(venta, [reserva_lista(det, self.lote, 50)], transportista=t, fecha=HOY)
        e2 = entrega(venta, [reserva_lista(det, self.lote, 50)], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        x1 = SimpleNamespace(entrega=e1, contrato=venta, transportista=t, envases=None)
        x2 = SimpleNamespace(entrega=e2, contrato=venta, transportista=t, envases=None)
        resumen = self.resumen(x1)
        self.assertFalse(resumen.es_ultima)
        self.assertFalse(resumen.cobra)
        self.concretar(x1, medio_pago="")  # sin medio de pago: no se cobra
        self.assertFalse(PagoCliente.objects.exists())
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_venta, "abierta")
        d = DetalleVenta.objects.get(pk=det.pk)
        self.assertEqual((d.estado_detalle_venta, d.cant_entregada_venta), ("confirmado", 50))
        self.concretar(x2)
        self.assertEqual(PagoCliente.objects.get().monto_pagado, Decimal("10000.00"))
        self.assertEqual(DetalleVenta.objects.get(pk=det.pk).cant_entregada_venta, 100)
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_venta, "concretada")

    def test_ext_8b_si_todos_los_detalles_quedan_rechazados_la_venta_se_cancela_sin_cobro(self):
        """Extensión 8b: sin cobro ni comprobante, la venta pasa a «cancelada» (no es una cancelación de COM-CNL-CVT: sin los datos de MD-130) y las reservas quedan «liberadas»."""
        x = self.concretable()
        self.concretar(x, acepta={self.linea(x).pk: False}, medio_pago="")
        venta = CompraVenta.objects.get(pk=x.contrato.pk)
        self.assertEqual((venta.estado_venta, venta.motivo_cancelacion_venta, venta.fecha_cancelacion_venta), ("cancelada", None, None))
        self.assertEqual(DetalleVenta.objects.get(pk=x.detalle.pk).estado_detalle_venta, "rechazado")
        self.assertEqual(ReservaStock.objects.get(pk=x.reserva.pk).estado_reserva, "liberada")
        self.assertFalse(PagoCliente.objects.exists())
        self.assertIsNone(self.refrescar(x).estado_aviso_cliente)
        self.assertEqual(self.refrescar(x).estado_orden, "concretada")

    def test_regla_en_la_ultima_entrega_con_cobro_hace_falta_el_medio_de_pago(self):
        """Paso 11: sin medio de pago (o con uno desconocido), `medio_de_pago_obligatorio` y no se registra nada."""
        x = self.concretable()
        for medio in ("", "cheque"):
            with self.assertRaises(ValidationError) as c:
                self.concretar(x, medio_pago=medio)
            self.assertEqual(codigos(c.exception), ["medio_de_pago_obligatorio"])
            self.assertEqual(campos(c.exception), ["medio_pago"])
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertFalse(PagoCliente.objects.exists())

    def test_ext_1a_el_vendedor_concreta_un_retiro_sin_ruta_y_siempre_cobra(self):
        """Extensión 1a: el Vendedor del contrato concreta un retiro sin ruta iniciada; es la última y única entrega, así que cobra."""
        x = self.concretable(retiro=True)
        (fila,) = concrecion.entregas_concretables(self.e.vendedor)
        self.assertEqual(fila.entrega.pk, x.entrega.pk)
        self.concretar(x, actor=self.e.vendedor, medio_pago="efectivo")
        self.assertEqual(self.refrescar(x).estado_orden, "concretada")
        self.assertEqual(PagoCliente.objects.get().monto_pagado, Decimal("5000.00"))
        self.assertEqual(self.avisos(self.e.vendedor), [])  # lo concreta él: no se avisa a sí mismo

    # ---- en un suministro ----

    def test_ext_3a_en_un_suministro_se_recibe_una_parte_el_precio_se_recalcula_y_se_fija_el_vencimiento(self):
        """Extensión 3a: el cliente recibe parte de lo que llegó (el resto se devuelve); el precio se recalcula con la fecha real (regla 7 de 8.11); no hay cobro; se fija el vencimiento (hoy + plazo); la confirmación sigue «no confirmado»."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=50, plazo_pago=20)
        d = DetalleSuministro.objects.get(pk=x.detalle.pk)
        DetalleSuministro.objects.filter(pk=d.pk).update(mecanismo_precio="ajuste_periodico", porcentaje_ajuste=Decimal("10.00"), meses_ajuste=1, fecha_base_ajuste=HOY - timedelta(days=65))
        d.refresh_from_db()
        DetalleEntrega.objects.filter(entrega=x.entrega).update(precio_unitario=Decimal("100.00"))
        esperado = calendario.precio_en(d, HOY)
        self.assertNotEqual(esperado, Decimal("100.00"))
        self.concretar(x, recibio={self.linea(x).pk: "80"})
        linea, e = DetalleEntrega.objects.get(pk=self.linea(x).pk), self.refrescar(x)
        self.assertEqual((linea.cant_entregada, linea.cant_devuelta, linea.cant_perdida, linea.precio_unitario), (80, 20, 0, esperado))
        self.assertEqual((e.monto_total_entrega, e.fecha_vencimiento_pago, e.estado_confirmacion_cliente), (esperado * 80, HOY + timedelta(days=20), "no_confirmado"))
        self.assertFalse(PagoCliente.objects.exists())

    @override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test")
    def test_post_l_el_correo_de_un_suministro_es_uno_solo_con_el_comprobante_y_el_enlace_de_confirmacion(self):
        """Postcondición l (COM-06b; D-68 punto 1): un solo correo con las cantidades, el monto y el vencimiento **y** el enlace de confirmación (la URL con el token, hasta cuándo sirve). El enlace nace vigente,
        sin vencimiento guardado (se calcula) y con el envío registrado. (Cambiada en COM-06b: hasta COM-06a el comprobante salía sin enlace.)"""
        x = self.concretable(tipo="suministro", cantidad=100, minima=50)
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)
        (correo,) = mail.outbox
        self.assertIn("Vence el pago", correo.body)
        self.assertRegex(correo.body, r"https://sitio\.test/cliente/[\w-]{20,}/")
        enlace = EnlaceCliente.objects.get(entrega=x.entrega.pk)
        self.assertEqual((enlace.tipo, enlace.estado, enlace.estado_envio, enlace.fecha_vencimiento, enlace.cliente_id), ("confirmacion_entrega", "vigente", "enviado", None, self.e.cliente.pk))
        self.assertEqual(self.refrescar(x).estado_aviso_cliente, "enviado")
        self.assertIn(f"{HOY + timedelta(days=3):%d/%m/%Y}", correo.body)  # la vigencia de fábrica: 3 días desde la fecha de resolución

    def test_post_l_un_cliente_sin_correo_no_tiene_enlace_y_la_entrega_queda_no_confirmada(self):
        """Regla «Enlace de confirmación» y «Sin confirmación tácita»: sin correo no hay enlace; el aviso queda «sin correo» y la confirmación, «no confirmado»."""
        from comercial.models import Cliente

        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        x = self.concretable(tipo="suministro", cantidad=100, minima=50)
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)
        e = self.refrescar(x)
        self.assertEqual((e.estado_aviso_cliente, e.estado_confirmacion_cliente, mail.outbox), ("sin_correo", "no_confirmado", []))
        self.assertFalse(EnlaceCliente.objects.exists())

    def test_post_l_una_compra_venta_no_crea_enlace_de_confirmacion(self):
        """Postcondición l es solo de las entregas de suministro: una compra-venta (confirmación nula) no recibe enlace."""
        x = self.concretable()
        self.concretar(x)
        self.assertFalse(EnlaceCliente.objects.exists())

    def test_post_l_la_concrecion_que_falla_no_deja_enlace(self):
        """Todo en una transacción: si la concreción se revierte, el enlace tampoco queda (y no sale ningún correo)."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=50)
        with mock.patch("comercial.servicios.concrecion.RegistroAuditoria.objects.registrar", side_effect=RuntimeError("falla")), self.assertRaises(RuntimeError):
            self.concretar(x)
        self.assertFalse(EnlaceCliente.objects.exists())
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")

    def test_ext_15a_el_paso_50_reemite_el_enlace_con_un_token_nuevo_si_el_correo_no_salio(self):
        """Extensión 15a (COM-06b): el token no se guarda, así que el reintento le pone un token nuevo a la misma fila (el viejo, que nunca llegó, deja de servir) y manda un solo correo con el enlace."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=50)
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)  # sin el correo del sistema: queda «pendiente de envío»
        enlace = EnlaceCliente.objects.get(entrega=x.entrega.pk)
        viejo = enlace.token_resumen
        self.assertEqual((enlace.estado_envio, self.refrescar(x).estado_aviso_cliente, mail.outbox), ("pendiente_envio", "pendiente_envio", []))
        with override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test"), self.captureOnCommitCallbacks(execute=True):
            entregas.planificar_entregas(HOY)
        comprobantes = [m for m in mail.outbox if m.subject.startswith("Comprobante de tu entrega")]
        self.assertEqual(len(comprobantes), 1)
        self.assertIn("https://sitio.test/cliente/", comprobantes[0].body)
        enlace.refresh_from_db()
        self.assertNotEqual(enlace.token_resumen, viejo)
        self.assertEqual((enlace.estado, enlace.estado_envio, self.refrescar(x).estado_aviso_cliente), ("vigente", "enviado", "enviado"))
        self.assertEqual(EnlaceCliente.objects.filter(entrega=x.entrega.pk).count(), 1)  # la misma fila: no es un reemplazo
        with override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test"), self.captureOnCommitCallbacks(execute=True):
            entregas.planificar_entregas(HOY)
        self.assertEqual(len([m for m in mail.outbox if m.subject.startswith("Comprobante de tu entrega")]), 1)  # idempotente

    def test_ext_15a_un_enlace_usado_o_vencido_no_se_reemite_y_una_concretada_sin_enlace_recibe_el_comprobante_sin_enlace(self):
        """15a: un enlace ya usado o vencido no se reintenta; una entrega concretada antes de COM-06b (sin enlace; estado de paso, D-68 punto 1) sigue recibiendo el comprobante sin enlace."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=50)
        with self.captureOnCommitCallbacks(execute=True):
            self.concretar(x)
        EnlaceCliente.objects.filter(entrega=x.entrega.pk).update(estado="usado", fecha_uso=timezone.now())
        with override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test"), self.captureOnCommitCallbacks(execute=True):
            entregas.planificar_entregas(HOY)
        self.assertEqual(mail.outbox, [])
        EnlaceCliente.objects.filter(entrega=x.entrega.pk).delete()  # una concretada antes de COM-06b
        with override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO="https://sitio.test"), self.captureOnCommitCallbacks(execute=True):
            entregas.planificar_entregas(HOY)
        (correo,) = [m for m in mail.outbox if m.subject.startswith("Comprobante de tu entrega")]
        self.assertNotIn("http", correo.body)

    def test_post_m_y_ext_14c_por_debajo_del_minimo_se_crea_una_sola_discrepancia_con_su_alerta(self):
        """Postcondición m y 14c: una `DiscrepanciaEntrega` «pendiente» con una línea (entregada y mínima copiadas) y una alerta de evento para el Gerente, vinculada por `AlertaComercial.solicitud`; se avisa al Vendedor."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=100)
        self.concretar(x, llego={self.linea(x).pk: "80"})
        d = DiscrepanciaEntrega.objects.get()
        self.assertEqual((d.estado_solicitud, d.entrega_id, d.fecha_solicitud, d.gerente_id, d.monto_indemnizacion), ("pendiente", x.entrega.pk, HOY, None, None))
        (linea,) = d.lineas.all()
        self.assertEqual((linea.cantidad_entregada, linea.cantidad_minima_estipulada, linea.detalle_entrega_id), (80, 100, self.linea(x).pk))
        vinculo = AlertaComercial.objects.get(solicitud=d)
        self.assertEqual((vinculo.alerta.tipo_alerta, vinculo.alerta.para_gerente, vinculo.alerta.estado_alerta), ("comercial_discrepancia_entrega", True, "activa"))
        self.assertIn(d.codigo, vinculo.alerta.descripcion_alerta)
        self.assertIn(d.codigo, self.avisos(self.e.vendedor)[0].detalle)
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos, 0)  # no hay incumplimiento hasta que el Gerente decida (COM-07)

    def test_ext_14c_aunque_la_diferencia_venga_de_un_rechazo_del_cliente_hay_discrepancia(self):
        """Extensión 14c: con 100 llegadas y solo 80 recibidas por el cliente (mínimo 100), igual se crea la discrepancia."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=100)
        self.concretar(x, recibio={self.linea(x).pk: "80"})
        self.assertEqual(DiscrepanciaEntrega.objects.get().lineas.get().cantidad_entregada, 80)

    def test_ext_14c_con_la_cantidad_minima_cubierta_no_hay_discrepancia(self):
        """Regla «Discrepancia de suministro»: con lo entregado igual a la mínima no se crea ni discrepancia ni alerta."""
        x = self.concretable(tipo="suministro", cantidad=100, minima=80)
        self.concretar(x, llego={self.linea(x).pk: "80"})
        self.assertFalse(DiscrepanciaEntrega.objects.exists())
        self.assertFalse(Alerta.objects.filter(tipo_alerta="comercial_discrepancia_entrega").exists())

    def test_regla_una_sola_discrepancia_por_entrega_con_una_linea_por_detalle_bajo_el_minimo(self):
        """Regla 12 de 8.13: dos detalles por debajo de la mínima → una sola discrepancia con dos líneas y una sola alerta."""
        t = transportista_con_vehiculo(self.e.invernadero)
        otra, _ = variedad_con_stock(self.e, "Rúcula 14c")
        lote2 = lote_maduro(self.e, 500, variedad=otra)
        s = suministro(self.e)
        d1 = detalle_suministro(s, self.e.variedad, cantidad=10, minima=10, primera_en_dias=0)
        d2 = detalle_suministro(s, otra, cantidad=10, minima=10, primera_en_dias=0)
        r1 = reserva_lista(None, self.lote, 10, fecha_entrega=d1.fecha_primer_entrega, detalle_suministro=d1)
        r2 = reserva_lista(None, lote2, 10, fecha_entrega=d2.fecha_primer_entrega, detalle_suministro=d2)
        e = entrega(s, [r1, r2], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        x = SimpleNamespace(entrega=e, contrato=s, transportista=t, envases=None)
        self.concretar(x, llego={l.pk: "5" for l in e.lineas.all()})
        d = DiscrepanciaEntrega.objects.get()
        self.assertEqual(d.lineas.count(), 2)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_discrepancia_entrega").count(), 1)

    def test_post_n_el_ultimo_periodo_finaliza_el_detalle_y_el_suministro(self):
        """Postcondición n (disparador «Cuando exista Entrega», punto 5): al concretar las entregas del último período, el detalle pasa a «finalizado» y, con todos finalizados, el suministro también."""
        x = self.concretable(tipo="suministro", cantidad=10, minima=1)
        DetalleSuministro.objects.filter(pk=x.detalle.pk).update(fecha_fin_detalle=HOY)
        self.concretar(x)
        d = DetalleSuministro.objects.get(pk=x.detalle.pk)
        self.assertEqual((d.estado_detalle_suministro, d.fecha_fin_detalle), ("finalizado", HOY))
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_suministro, "finalizado")

    def test_post_n_un_detalle_con_periodos_pendientes_no_se_finaliza(self):
        """Postcondición n: un detalle con períodos todavía por entregar sigue «vigente» y el suministro también."""
        x = self.concretable(tipo="suministro", cantidad=10, minima=1)
        self.concretar(x)
        self.assertEqual(DetalleSuministro.objects.get(pk=x.detalle.pk).estado_detalle_suministro, "vigente")
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_suministro, "vigente")

    def test_d_del_estudiante_con_rescision_acordada_no_se_finaliza_el_contrato(self):
        """Decisión del 25/11/2026 (temas abiertos): con una rescisión acordada, la concreción de la última entrega no toca el detalle ni el contrato; los cierra el paso 35 (detalle «finalizado» y contrato «rescindido»)."""
        x = self.concretable(tipo="suministro", cantidad=10, minima=1)
        DetalleSuministro.objects.filter(pk=x.detalle.pk).update(fecha_fin_detalle=HOY)
        Suministro.objects.filter(pk=x.contrato.pk).update(
            motivo_rescision="a_pedido_del_cliente", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=HOY
        )
        self.concretar(x)
        self.assertEqual(DetalleSuministro.objects.get(pk=x.detalle.pk).estado_detalle_suministro, "vigente")
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_suministro, "vigente")
        suministros.cerrar_rescisiones(HOY + timedelta(days=1))
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).estado_suministro, "rescindido")

    # ---- cantidades (5b) y confirmación del resumen ----

    def test_ext_5b_una_cantidad_que_no_es_un_entero_entre_cero_y_lo_planificado_se_rechaza_por_campo(self):
        """Extensión 5b: `cantidad_invalida` en el campo `llego_<línea>` con lo planificado; el resumen lo trae en `errores` y el registro no escribe nada."""
        x = self.concretable(cantidad=50)
        campo = f"llego_{self.linea(x).pk}"
        for valor in ("51", "-1", "abc", "4,5"):
            resumen = self.resumen(x, llego={self.linea(x).pk: valor})
            self.assertEqual([c for c, _ in resumen.errores[campo]], ["cantidad_invalida"], valor)
            self.assertIn("50", resumen.errores[campo][0][1])
            with self.assertRaises(ValidationError) as c:
                concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x, llego={self.linea(x).pk: valor}), resumen.huella)
            self.assertEqual((codigos(c.exception), campos(c.exception)), (["cantidad_invalida"], [campo]))
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")

    def test_ext_5a_con_menos_plantas_de_las_planificadas_se_informa_que_la_diferencia_es_perdida(self):
        """Extensión 5a: el resumen advierte que la diferencia se registrará como pérdida en el traslado y trae las cantidades perdidas."""
        x = self.concretable(cantidad=50)
        resumen = self.resumen(x, llego={self.linea(x).pk: "40"})
        self.assertTrue(any("pérdida en el traslado" in a for a in resumen.advertencias))
        self.assertEqual((resumen.lineas[0].llego, resumen.lineas[0].perdida, resumen.total), (40, 10, Decimal("4000.00")))

    def test_ext_3a_en_un_suministro_no_se_puede_recibir_mas_de_lo_que_llego(self):
        """Extensión 3a: `recibio <= llegó`; si no, `cantidad_invalida` en `recibio_<línea>`."""
        x = self.concretable(tipo="suministro", cantidad=100)
        campo = f"recibio_{self.linea(x).pk}"
        resumen = self.resumen(x, llego={self.linea(x).pk: "90"}, recibio={self.linea(x).pk: "91"})
        self.assertEqual([c for c, _ in resumen.errores[campo]], ["cantidad_invalida"])

    def test_regla_cantidades_de_una_linea_entregadas_mas_perdidas_mas_devueltas_son_las_planificadas(self):
        """Regla «Cantidades de una línea»: entregadas + perdidas + devueltas = planificada, en una venta aceptada, rechazada y en un suministro."""
        x = self.concretable(cantidad=50)
        for datos in ({"llego": {self.linea(x).pk: "45"}}, {"llego": {self.linea(x).pk: "45"}, "acepta": {self.linea(x).pk: False}}):
            (lr,) = self.resumen(x, **datos).lineas
            self.assertEqual(lr.entregada + lr.perdida + lr.devuelta, 50)

    def test_ext_13a_corregir_un_dato_es_volver_a_pedir_el_resumen_con_el_dato_nuevo(self):
        """Extensión 13a: el resumen es solo lectura; corregir un dato y pedirlo de nuevo da otro resumen sin haber escrito nada."""
        x = self.concretable(cantidad=50)
        primero = self.resumen(x, llego={self.linea(x).pk: "40"})
        segundo = self.resumen(x, llego={self.linea(x).pk: "50"})
        self.assertNotEqual(primero.total, segundo.total)
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertFalse(Merma.objects.exists())

    # ---- envases (9a, 10a, 10b, 14b) ----

    def test_ext_9a_sin_envasado_se_declaran_los_envases_usados_como_consumo_directo_y_se_avisa_al_agronomo(self):
        """Extensión 9a: sin envasado planificado, cada envase declarado es un consumo directo sin reserva y se notifica al Agrónomo con lo declarado."""
        x = self.concretable()
        b = envase(self.e.invernadero, stock=30)
        self.concretar(x, declarado={b.pk: "3"}, sin_envases=False)
        self.assertEqual((Consumo.objects.get().cant_consumo, ReservaInsumo.objects.count()), (Decimal("3"), 0))
        (aviso,) = self.avisos(self.e.agronomo)
        self.assertIn("sin envasado planificado", aviso.detalle)
        self.assertIn("3 Bandeja PET 1 kg", aviso.detalle)

    def test_ext_9a_declarar_que_no_se_usaron_envases_no_registra_consumo_pero_avisa(self):
        """Extensión 9a.2: «no usé envases» no registra consumo; el Agrónomo igual se entera de que se concretó sin envasado."""
        x = self.concretable()
        self.concretar(x)
        self.assertFalse(Consumo.objects.exists())
        self.assertIn("ningún envase", self.avisos(self.e.agronomo)[0].detalle)

    def test_ext_9a_sin_declarar_nada_ni_marcar_que_no_se_usaron_se_rechaza(self):
        """Extensión 9a: hay que declarar los envases o marcar que no se usaron: `envase_invalido` en `envases`; declarar y marcar a la vez también."""
        x = self.concretable()
        b = envase(self.e.invernadero)
        resumen = self.resumen(x, sin_envases=False)
        self.assertEqual([c for c, _ in resumen.errores["envases"]], ["envase_invalido"])
        resumen = self.resumen(x, declarado={b.pk: "2"}, sin_envases=True)
        self.assertIn("envases", resumen.errores)

    def test_ext_10a_una_cantidad_de_envases_invalida_se_rechaza_con_lo_que_se_puede_devolver(self):
        """Extensión 10a: la devuelta no puede superar `reservada − utilizada`; la utilizada no puede ser negativa ni un texto; el mensaje trae la reservada y el máximo."""
        x = self.concretable(con_envasado=True)
        iin = x.envases.pk
        resumen = self.resumen(x, utilizada={iin: "5"}, devuelta={iin: "6"})
        (codigo, mensaje) = resumen.errores[f"devuelta_{iin}"][0]
        self.assertEqual(codigo, "envase_invalido")
        self.assertIn("entre 0 y 5", mensaje)
        self.assertIn("reservadas: 10", mensaje)
        self.assertIn(f"utilizada_{iin}", self.resumen(x, utilizada={iin: "-1"}).errores)
        self.assertIn(f"utilizada_{iin}", self.resumen(x, utilizada={iin: "mucho"}).errores)

    def test_ext_10b_el_exceso_se_confirma_se_consume_y_se_avisa_al_agronomo(self):
        """Extensión 10b y D-68 punto 2: la reserva se cierra topeada (utilizada 10), la devuelta 0, el consumo es de 12 (el exceso incluido) y la utilizada declarada queda en la auditoría y en el aviso al Agrónomo."""
        x = self.concretable(con_envasado=True)
        iin = x.envases.pk
        self.concretar(x, utilizada={iin: "12"}, confirmo_exceso={iin})
        reserva_ = ReservaInsumo.objects.get(orden_id=x.entrega.pk)
        self.assertEqual((reserva_.estado, reserva_.cantidad_utilizada, reserva_.cantidad_devuelta), ("consumida", Decimal("10"), Decimal("0")))
        self.assertEqual(Consumo.objects.get().cant_consumo, Decimal("12"))
        self.assertEqual(sum(LoteInsumo.objects.filter(insumo_invernadero=x.envases).values_list("cantidad_disponible", flat=True)), Decimal("18"))
        (aviso,) = self.avisos(self.e.agronomo)
        self.assertIn("2 de más", aviso.detalle)
        r = RegistroAuditoria.objects.get(accion="concrecion_entrega")
        self.assertTrue(any("12 (reservadas 10)" in texto for texto in r.detalle["datos"]["envases_declarados"]))

    def test_ext_10b_sin_confirmar_el_exceso_no_se_registra(self):
        """Extensión 10b.2: hay que confirmar la cantidad utilizada; sin la confirmación, `envase_invalido` y nada se escribe."""
        x = self.concretable(con_envasado=True)
        iin = x.envases.pk
        with self.assertRaises(ValidationError) as c:
            self.concretar(x, utilizada={iin: "12"})
        self.assertEqual((codigos(c.exception), campos(c.exception)), (["envase_invalido"], [f"utilizada_{iin}"]))
        self.assertEqual(ReservaInsumo.objects.get(orden_id=x.entrega.pk).estado, "activa")

    def test_ext_10b_con_exceso_la_devuelta_es_cero(self):
        """Regla «Exceso de envases»: si se usó más de lo reservado, la devuelta propuesta es 0 y no puede ser mayor."""
        x = self.concretable(con_envasado=True)
        iin = x.envases.pk
        resumen = self.resumen(x, utilizada={iin: "12"}, confirmo_exceso={iin})
        self.assertEqual((resumen.envases[0].devuelta, resumen.envases[0].exceso, resumen.con_exceso), (Decimal("0"), Decimal("2"), True))
        self.assertIn(f"devuelta_{iin}", self.resumen(x, utilizada={iin: "12"}, devuelta={iin: "1"}, confirmo_exceso={iin}).errores)

    def test_ext_14b_un_consumo_que_deja_el_stock_sin_cubrir_se_registra_igual_y_alerta_sin_avisar_al_actor(self):
        """Extensión 14b: con menos stock que lo consumido, la concreción se registra completa (lo que supera los lotes queda como faltante sin lote), se crea la alerta de «stock inconsistente» y no se le dice nada al Transportista."""
        x = self.concretable()
        b = envase(self.e.invernadero, stock=1)
        antes = Alerta.objects.filter(tipo_alerta="inv_stock_inconsistente").count()
        self.concretar(x, declarado={b.pk: "5"}, sin_envases=False)
        self.assertEqual(self.refrescar(x).estado_orden, "concretada")
        self.assertEqual(Consumo.objects.get().cant_consumo, Decimal("5"))
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_stock_inconsistente").count(), antes + 1)
        self.assertEqual(self.avisos(x.transportista), [])
        verificar_invariantes(b)

    # ---- 14a, huella, ruta y permisos ----

    def test_ext_14a_si_se_la_reasignaron_antes_de_registrar_no_se_registra_nada(self):
        """Extensión 14a: la entrega dejó de ser del Transportista entre el resumen y la confirmación: `entrega_no_concretable`, sin cambios ni auditoría."""
        x = self.concretable()
        otro = transportista_con_vehiculo(self.e.invernadero)
        resumen = self.resumen(x)

        def reasignar(invernadero_id):
            Entrega.objects.filter(pk=x.entrega.pk).update(transportista=otro)

        with mock.patch("comercial.servicios.concrecion.bloquear_invernadero_activo", side_effect=reasignar):
            with self.assertRaises(ValidationError) as c:
                concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), resumen.huella)
        self.assertEqual(codigos(c.exception), ["entrega_no_concretable"])
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertFalse(RegistroAuditoria.objects.filter(accion="concrecion_entrega").exists())

    def test_ext_14a_si_ya_no_esta_a_realizar_no_se_registra_nada(self):
        """Extensión 14a: otra operación la canceló: `entrega_no_concretable`."""
        x = self.concretable()
        resumen = self.resumen(x)

        def cancelar(invernadero_id):
            Entrega.objects.filter(pk=x.entrega.pk).update(estado_orden="cancelada", fecha_resolucion_orden=HOY, motivo_cancelacion="x")

        with mock.patch("comercial.servicios.concrecion.bloquear_invernadero_activo", side_effect=cancelar):
            with self.assertRaises(ValidationError) as c:
                concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), resumen.huella)
        self.assertEqual(codigos(c.exception), ["entrega_no_concretable"])
        Entrega.objects.filter(pk=x.entrega.pk).update(estado_orden="a_realizar", fecha_resolucion_orden=None, motivo_cancelacion=None)

    def test_regla_si_cambia_el_envasado_mientras_se_cargan_los_datos_la_huella_lo_detecta(self):
        """«Retiro en concreción» (envasado.md): en un retiro el envasado puede cambiar mientras el Vendedor carga los datos: la huella no coincide, `cambio_simultaneo` y no se registra nada."""
        x = self.concretable(retiro=True, con_envasado=True)
        iin = x.envases.pk
        resumen = self.resumen(x, utilizada={iin: "10"})
        ReservaInsumo.objects.filter(orden_id=x.entrega.pk).update(cantidad_reservada=Decimal("8"))
        with self.assertRaises(ValidationError) as c:
            concrecion.concretar_entrega(self.e.vendedor, x.entrega.pk, self.D(x, utilizada={iin: "10"}), resumen.huella)
        self.assertEqual(codigos(c.exception), ["cambio_simultaneo"])
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertFalse(Consumo.objects.exists())

    def test_regla_si_cambia_el_producto_de_la_linea_la_huella_lo_detecta(self):
        """La huella incluye las reservas no liberadas con sus orígenes: si una se libera, `cambio_simultaneo`."""
        x = self.concretable()
        resumen = self.resumen(x)
        ReservaStock.objects.filter(pk=x.reserva.pk).update(estado_reserva="liberada")
        with self.assertRaises(ValidationError) as c:
            concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), resumen.huella)
        self.assertEqual(codigos(c.exception), ["cambio_simultaneo"])
        ReservaStock.objects.filter(pk=x.reserva.pk).update(estado_reserva="lista_para_entrega")

    def test_regla_sin_la_ruta_iniciada_no_se_concreta(self):
        """Precondición b: sin la ruta del día iniciada, `ruta_no_iniciada` (en el resumen y en el registro)."""
        x = self.concretable(ruta_iniciada=False)
        with self.assertRaises(ValidationError) as c:
            self.resumen(x)
        self.assertEqual(codigos(c.exception), ["ruta_no_iniciada"])
        with self.assertRaises(ValidationError) as c:
            concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), "")
        self.assertEqual(codigos(c.exception), ["ruta_no_iniciada"])

    def test_regla_una_entrega_de_fecha_futura_no_se_concreta(self):
        """Regla «Entrega concretable»: con fecha programada posterior a hoy, `entrega_no_concretable`."""
        x = self.concretable(dias=3, ruta_iniciada=False)  # una entrega de fecha futura no entra en la ruta de hoy: no se puede iniciar con ella
        with self.assertRaises(ValidationError) as c:
            self.resumen(x)
        self.assertEqual(codigos(c.exception), ["entrega_no_concretable"])

    def test_regla_solo_concreta_el_transportista_asignado_o_el_vendedor_de_un_retiro(self):
        """Regla «Entrega concretable» y «Solo concreta la entrega…»: el Gerente, el Agrónomo, otro transportista, el Vendedor (en una entrega con envío) y el Transportista (en un retiro) no concretan (`PermissionDenied`)."""
        envio = self.concretable()
        retiro = self.concretable(retiro=True)
        otro = transportista_con_vehiculo(self.e.invernadero)
        for cuenta in (self.gerente, self.e.agronomo, otro, self.e.vendedor):
            with self.assertRaises(PermissionDenied):
                concrecion.resumen_de_concrecion(cuenta, envio.entrega.pk, self.D(envio))
        for cuenta in (self.gerente, self.e.agronomo, otro, envio.transportista):
            with self.assertRaises(PermissionDenied):
                concrecion.resumen_de_concrecion(cuenta, retiro.entrega.pk, self.D(retiro))
        with self.assertRaises(PermissionDenied):
            concrecion.concretar_entrega(self.gerente, envio.entrega.pk, self.D(envio), "")

    def test_regla_el_vendedor_de_otro_contrato_no_concreta_un_retiro_ajeno(self):
        """El Vendedor solo concreta los retiros de sus contratos."""
        from maestros.tests.fabricas import crear_vendedor

        retiro = self.concretable(retiro=True)
        ajeno = crear_vendedor(email="otro.vendedor@infoponia.com")
        with self.assertRaises(PermissionDenied):
            concrecion.resumen_de_concrecion(ajeno, retiro.entrega.pk, self.D(retiro))

    def test_regla_una_entrega_se_concreta_una_unica_vez(self):
        """Garantía mínima: nunca se concreta dos veces; la segunda se rechaza con `entrega_no_concretable` y no duplica lo registrado."""
        x = self.concretable()
        resumen = self.resumen(x)
        concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), resumen.huella)
        with self.assertRaises(ValidationError) as c:
            concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x), resumen.huella)
        self.assertEqual(codigos(c.exception), ["entrega_no_concretable"])
        self.assertEqual(PagoCliente.objects.count(), 1)
        self.assertEqual(MovimientoStock.objects.filter(tipo_movimiento="egreso_de_camara").count(), 1)

    # ---- atomicidad ----

    def test_garantia_la_concrecion_es_atomica_si_falla_algo_no_se_registra_nada(self):
        """Garantía mínima: si falla un paso del medio (el consumo de un envase), la entrega sigue «a realizar», las reservas «activas» y no se registra ninguna merma, movimiento, pago ni auditoría."""
        x = self.concretable(con_envasado=True)
        partida = x.reserva.lineas.get().partida
        resumen = self.resumen(x, llego={self.linea(x).pk: "45"})
        with mock.patch("comercial.servicios.concrecion.consumos.registrar_consumo_de_orden", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                concrecion.concretar_entrega(x.transportista, x.entrega.pk, self.D(x, llego={self.linea(x).pk: "45"}), resumen.huella)
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertEqual(ReservaStock.objects.get(pk=x.reserva.pk).estado_reserva, "lista_para_entrega")
        self.assertEqual(ReservaInsumo.objects.get(orden_id=x.entrega.pk).estado, "activa")
        partida.refresh_from_db()
        self.assertEqual(partida.cantidad_disponible_cosechado, 50)
        self.assertEqual((Merma.objects.count(), PagoCliente.objects.count(), RegistroAuditoria.objects.filter(accion="concrecion_entrega").count()), (0, 0, 0))

    # ---- lecturas ----

    def test_flujo_principal_las_entregas_concretables_del_transportista_con_las_demoradas_primero(self):
        """Paso 2: las entregas «a realizar» con fecha de hoy o anterior del Transportista, con cliente, destino, tipo de contrato y si están demoradas; no las futuras ni las de otro."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        hoy_ = entrega(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY)
        v2 = compra_venta(self.e, dias=0)
        atrasada = entrega(v2, [reserva_lista(detalle(v2, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY - timedelta(days=2))
        v3 = compra_venta(self.e, dias=5)
        entrega(v3, [reserva_lista(detalle(v3, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY + timedelta(days=5))
        lista = concrecion.entregas_concretables(t)
        self.assertEqual([f.entrega.pk for f in lista], [atrasada.pk, hoy_.pk])
        self.assertEqual([(f.demorada, f.dias_de_retraso, f.es_suministro) for f in lista], [(True, 2, False), (False, 0, False)])
        self.assertEqual(lista[0].cliente, self.e.cliente.nombre_visible)

    def test_regla_entregas_concretables_no_hace_consultas_por_entrega(self):
        """Una consulta por tabla: las mismas consultas con 1 que con 4 entregas."""
        t = transportista_con_vehiculo(self.e.invernadero)

        def nueva():
            venta = compra_venta(self.e, dias=0)
            entrega(venta, [reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)], transportista=t, fecha=HOY)

        nueva()
        with CaptureQueriesContext(connection) as una:
            concrecion.entregas_concretables(t)
        for _ in range(3):
            nueva()
        with CaptureQueriesContext(connection) as varias:
            concrecion.entregas_concretables(t)
        self.assertEqual(len(una), len(varias))

    def test_regla_el_resumen_trae_el_total_a_cobrar_y_es_solo_lectura(self):
        """Paso 12: el resumen trae el total a cobrar y la huella; no escribe nada (las filas de las tablas tocadas no cambian)."""
        x = self.concretable(con_envasado=True)
        antes = (Entrega.objects.count(), MovimientoStock.objects.count(), ReservaInsumo.objects.filter(estado="activa").count(), RegistroAuditoria.objects.count())
        resumen = self.resumen(x, llego={self.linea(x).pk: "40"})
        self.assertEqual((resumen.total_a_cobrar, resumen.cobra, resumen.es_ultima, resumen.huella != ""), (Decimal("4000.00"), True, True, True))
        despues = (Entrega.objects.count(), MovimientoStock.objects.count(), ReservaInsumo.objects.filter(estado="activa").count(), RegistroAuditoria.objects.count())
        self.assertEqual(antes, despues)

    def test_regla_los_datos_del_formulario_se_leen_por_linea_y_por_envase(self):
        """`datos_de_concrecion` arma los datos de un `POST`: `llego_`, `acepta_` («0» rechaza), `recibio_`, `utilizada_`, `devuelta_`, `confirmo_exceso_`, `declarado_`, `sin_envases` y `medio_pago`."""
        datos = concrecion.datos_de_concrecion(
            {"llego_3": "40", "acepta_3": "0", "acepta_4": "1", "recibio_5": "7", "utilizada_9": "2", "devuelta_9": "1", "confirmo_exceso_9": "on", "declarado_8": "4", "sin_envases": "on", "medio_pago": "efectivo", "descripcion_perdida": " hola "}
        )
        self.assertEqual((datos.llego, datos.acepta, datos.recibio), ({3: "40"}, {3: False, 4: True}, {5: "7"}))
        self.assertEqual((datos.utilizada, datos.devuelta, datos.confirmo_exceso, datos.declarado), ({9: "2"}, {9: "1"}, {9}, {8: "4"}))
        self.assertEqual((datos.sin_envases, datos.medio_pago, datos.descripcion_perdida), (True, "efectivo", "hola"))


# ---- extensión 4a: el intento fallido ----


class ComCncEntIntentoFallidoTests(Base):
    def intentar(self, x, motivo="cliente_ausente", descripcion="", actor=None):
        return rutas.registrar_intento_fallido(actor or x.transportista, x.entrega.pk, motivo, descripcion)

    def test_ext_4a_la_entrega_pasa_a_manana_sin_transportista_y_sigue_a_realizar(self):
        """Extensión 4a.2 y postcondición o: sigue «a realizar» con la fecha de mañana, sin transportista y sin avisos viejos; el intento guarda el transportista, la fecha que tenía y el motivo."""
        x = self.concretable()
        Entrega.objects.filter(pk=x.entrega.pk).update(recordatorio_para=HOY, aviso_atrasada_para=HOY)
        intento = self.intentar(x, "domicilio_cerrado", "Portón con candado")
        e = Entrega.objects.get(pk=x.entrega.pk)
        self.assertEqual((e.estado_orden, e.fecha_programada_orden, e.transportista_id, e.recordatorio_para, e.aviso_atrasada_para), ("a_realizar", HOY + timedelta(days=1), None, None, None))
        self.assertEqual((intento.transportista_id, intento.fecha_programada, intento.motivo, intento.descripcion), (x.transportista.pk, HOY, "domicilio_cerrado", "Portón con candado"))
        self.assertEqual(IntentoFallido.objects.filter(entrega=e).count(), 1)

    def test_post_o_las_reservas_de_insumo_siguen_activas_y_no_se_registra_ningun_consumo(self):
        """Postcondición o: los envases vuelven con el producto: sus reservas siguen «activa» y no hay consumo; el stock y la cámara no cambian."""
        x = self.concretable(con_envasado=True)
        partida = x.reserva.lineas.get().partida
        self.intentar(x)
        self.assertEqual(ReservaInsumo.objects.get(orden_id=x.entrega.pk).estado, "activa")
        self.assertFalse(Consumo.objects.exists())
        partida.refresh_from_db()
        self.assertEqual(partida.cantidad_disponible_cosechado, 50)
        self.assertEqual(ReservaStock.objects.get(pk=x.reserva.pk).estado_reserva, "lista_para_entrega")

    def test_post_o_se_notifica_al_vendedor_el_motivo_y_la_nueva_fecha(self):
        """Postcondición o y 4a.3: aviso al Vendedor con el motivo y la nueva fecha."""
        x = self.concretable()
        self.intentar(x, "direccion_incorrecta")
        (aviso,) = self.avisos(self.e.vendedor)
        self.assertIn("no se pudo entregar: dirección incorrecta", aviso.detalle)
        self.assertIn(f"{HOY + timedelta(days=1):%d/%m/%Y}", aviso.detalle)
        self.assertIn("sin transportista", aviso.detalle)

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_o_el_cliente_recibe_un_correo_con_el_motivo_y_la_nueva_fecha(self):
        """Postcondición o: correo al cliente con el motivo y la nueva fecha, después de confirmar; el resultado queda en `estado_aviso_cliente`."""
        x = self.concretable()
        with self.captureOnCommitCallbacks(execute=True):
            self.intentar(x, "cliente_ausente")
        (correo,) = mail.outbox
        self.assertIn("cliente ausente", correo.body)
        self.assertIn(f"{HOY + timedelta(days=1):%d/%m/%Y}", correo.body)
        self.assertEqual(Entrega.objects.get(pk=x.entrega.pk).estado_aviso_cliente, "enviado")

    def test_post_p_se_audita_el_intento_fallido(self):
        """Postcondición p: un registro `intento_fallido_entrega` del Transportista con la entrega y el intento, el cambio de fecha y de transportista y el motivo."""
        x = self.concretable()
        intento = self.intentar(x, "otro", "Lluvia")
        r = RegistroAuditoria.objects.get(accion="intento_fallido_entrega")
        self.assertEqual(r.usuario_id, x.transportista.pk)
        self.assertEqual({(a["modelo"].split(".")[-1].lower(), a["id"]) for a in r.afectados}, {("entrega", x.entrega.pk), ("intentofallido", intento.pk)})
        self.assertEqual(r.detalle["cambios"]["fecha_programada_orden"]["despues"], f"{HOY + timedelta(days=1):%d/%m/%Y}")
        self.assertEqual(r.detalle["datos"]["motivo"], "otro")

    def test_regla_el_intento_fallido_no_es_un_incumplimiento_de_la_empresa(self):
        """Extensión 4a.4: no suma a la cantidad de incumplimientos del contrato."""
        x = self.concretable(tipo="suministro", cantidad=10)
        self.intentar(x)
        self.assertEqual(Suministro.objects.get(pk=x.contrato.pk).cantidad_incumplimientos, 0)

    def test_ext_4a_el_motivo_es_obligatorio_y_de_la_lista_y_la_descripcion_tiene_tope(self):
        """Lista de tecnología 4a: `motivo_obligatorio` sin motivo (o fuera de la lista); `descripcion_larga` con más de 300 caracteres; nada se registra."""
        x = self.concretable()
        for motivo in ("", "llovia"):
            with self.assertRaises(ValidationError) as c:
                self.intentar(x, motivo)
            self.assertEqual(codigos(c.exception), ["motivo_obligatorio"])
        with self.assertRaises(ValidationError) as c:
            self.intentar(x, "otro", "x" * 301)
        self.assertEqual(codigos(c.exception), ["descripcion_larga"])
        self.assertFalse(IntentoFallido.objects.exists())

    def test_regla_sin_la_ruta_iniciada_no_hay_intento_fallido(self):
        """Precondición b: `ruta_no_iniciada`."""
        x = self.concretable(ruta_iniciada=False)
        with self.assertRaises(ValidationError) as c:
            self.intentar(x)
        self.assertEqual(codigos(c.exception), ["ruta_no_iniciada"])

    def test_ext_14a_el_intento_de_una_entrega_que_ya_no_es_suya_o_ya_no_esta_a_realizar_se_rechaza(self):
        """Extensión 14a: una entrega ya pasada a mañana (sin transportista) se informa como `entrega_no_concretable`; la de otro transportista, `PermissionDenied`."""
        x = self.concretable()
        otro = transportista_con_vehiculo(self.e.invernadero)
        with self.assertRaises(PermissionDenied):
            rutas.registrar_intento_fallido(otro, x.entrega.pk, "otro", "")
        self.intentar(x)
        with self.assertRaises(ValidationError) as c:
            self.intentar(x)
        self.assertEqual(codigos(c.exception), ["entrega_no_concretable"])
        self.assertEqual(IntentoFallido.objects.count(), 1)

    def test_regla_un_retiro_no_tiene_intento_fallido_y_otros_roles_no_lo_registran(self):
        """Extensión 1a.3 («No aplica la extensión 4a»): el Vendedor no registra intentos fallidos; tampoco el Gerente."""
        x = self.concretable(retiro=True)
        for cuenta in (self.e.vendedor, self.gerente):
            with self.assertRaises(PermissionDenied):
                rutas.registrar_intento_fallido(cuenta, x.entrega.pk, "otro", "")

    def test_regla_los_intentos_de_una_entrega_se_leen_en_orden(self):
        """`intentos_fallidos(entrega_ids)`: `{id: [intentos]}` del más viejo al más nuevo, con una consulta; sin intentos, lista vacía."""
        x = self.concretable()
        sin = self.concretable()
        self.intentar(x, "cliente_ausente")
        Entrega.objects.filter(pk=x.entrega.pk).update(transportista=x.transportista, fecha_programada_orden=HOY)
        self.intentar(x, "otro")
        with self.assertNumQueries(1):
            lectura = concrecion.intentos_fallidos([x.entrega.pk, sin.entrega.pk])
        self.assertEqual([i.motivo for i in lectura[x.entrega.pk]], ["cliente_ausente", "otro"])
        self.assertEqual(lectura[sin.entrega.pk], [])

    def test_regla_dos_intentos_seguidos_dejan_dos_registros(self):
        """Sin límite automático de intentos: la misma entrega puede fallar más de una vez y cada intento queda registrado."""
        x = self.concretable()
        self.intentar(x)
        Entrega.objects.filter(pk=x.entrega.pk).update(transportista=x.transportista, fecha_programada_orden=HOY)
        self.intentar(x, "domicilio_cerrado")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="intento_fallido_entrega").count(), 2)


class ConcretarEntregaAsientoTests(Base):
    """CON-04c · paso 3: los asientos de la concreción de una entrega (COM-CNC-ENT postcondiciones e, g y h; D-92 puntos 3 a 6; D-86; D-68 punto 2). La fecha es la de la
    resolución (hoy) y el actor, quien concreta. Decisiones del estudiante del 26/11/2026: (2) lo devuelto a una partida vencida asienta como un vencimiento; (3) la compra-venta
    sigue la regla «Venta registrada por entrega» y no la fila (h) de la tarea; (4) lo de las entregas anteriores sin asiento se reconoce en Ventas (transición, D-92 punto 1)."""

    def setUp(self):
        super().setUp()
        self.ejercicio = ejercicio_abierto(HOY - timedelta(days=30))
        self.addCleanup(verificar_invariantes_contables)

    def lineas(self, asiento):
        """`[(cuenta, tipo, importe)]` del asiento, ordenado (el compuesto no fija el orden de sus líneas)."""
        return sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta"))

    def asiento_de(self, origen_):
        return AsientoContable.objects.get(origen_id=origen_.pk)

    def dos_entregas(self, cantidad_cada_una=50):
        """Una compra-venta de 100 plantas a $100 con dos entregas «a realizar» de 50 del mismo transportista. Devuelve `(x1, x2)` como `entrega_concretable`."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 2 * cantidad_cada_una)
        e1 = entrega(venta, [reserva_lista(det, self.lote, cantidad_cada_una)], transportista=t, fecha=HOY)
        e2 = entrega(venta, [reserva_lista(det, self.lote, cantidad_cada_una)], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        return tuple(SimpleNamespace(entrega=e, contrato=venta, detalle=det, transportista=t, envases=None) for e in (e1, e2))

    # ---- h: el asiento compuesto de la entrega ----

    def test_post_h_suministro_debita_deudores_contra_ventas_y_el_costo_contra_productos_terminados(self):
        """h (suministro): Debe Deudores por Ventas / Haber Ventas por el monto total de la entrega y Debe Costo de Producción Vendida / Haber Productos Terminados por el costo
        de lo entregado (50 × 1,0000), en UN asiento compuesto originado en la entrega."""
        x = self.concretable(tipo="suministro")
        self.concretar(x)
        monto = self.refrescar(x).monto_total_entrega
        asiento = self.asiento_de(x.entrega)
        self.assertEqual(
            self.lineas(asiento),
            sorted([
                (cuentas.DEUDORES_POR_VENTAS, DEBE, monto), (cuentas.VENTAS, HABER, monto),
                (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00")),
            ]),
        )
        self.assertEqual((asiento.fecha_asiento, AsientoContable.objects.count()), (HOY, 1))

    def test_regla_venta_registrada_por_entrega_una_sola_entrega_cobra_con_caja_en_efectivo_y_con_banco_en_los_demas_medios(self):
        """Regla «Venta registrada por entrega»: con una sola entrega, Debe Caja (efectivo) o Banco c/c (los demás medios) / Haber Ventas por el total, más el costo."""
        for medio, cuenta in (("efectivo", cuentas.CAJA), ("transferencia", cuentas.BANCO)):
            with self.subTest(medio=medio):
                x = self.concretable()
                self.concretar(x, medio_pago=medio)
                self.assertEqual(
                    self.lineas(self.asiento_de(x.entrega)),
                    sorted([
                        (cuenta, DEBE, Decimal("5000.00")), (cuentas.VENTAS, HABER, Decimal("5000.00")),
                        (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00")),
                    ]),
                )

    def test_regla_venta_registrada_por_entrega_la_no_ultima_debita_deudores_y_la_ultima_cobra_con_caja_o_banco(self):
        """Decisión (3) del 26/11/2026. Dos entregas de 50 a $100: la primera (no última) registra la venta contra Deudores por Ventas; la última cobra el total (10.000,00) con Caja,
        acredita Ventas por lo suyo (5.000,00) y cancela lo acumulado en Deudores (5.000,00). Siempre se suma el costo (CPV / Productos Terminados)."""
        x1, x2 = self.dos_entregas()
        self.concretar(x1)
        self.assertEqual(
            self.lineas(self.asiento_de(x1.entrega)),
            sorted([
                (cuentas.DEUDORES_POR_VENTAS, DEBE, Decimal("5000.00")), (cuentas.VENTAS, HABER, Decimal("5000.00")),
                (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00")),
            ]),
        )
        self.concretar(x2)
        self.assertEqual(
            self.lineas(self.asiento_de(x2.entrega)),
            sorted([
                (cuentas.CAJA, DEBE, Decimal("10000.00")), (cuentas.VENTAS, HABER, Decimal("5000.00")), (cuentas.DEUDORES_POR_VENTAS, HABER, Decimal("5000.00")),
                (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00")),
            ]),
        )

    def test_regla_venta_registrada_por_entrega_transicion_lo_anterior_sin_asiento_va_a_ventas_y_deudores_no_queda_contrario(self):
        """Decisión (4) del 26/11/2026 y D-92 punto 1: la primera entrega se concretó antes de esta tarea (sin asiento). La última no puede acreditar Deudores por lo que nunca se
        debitó: lo de la anterior (5.000,00) se reconoce en Ventas (10.000,00 en total) y Deudores no aparece."""
        x1, x2 = self.dos_entregas()
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", return_value=None):  # la primera, como si fuera anterior a CON-04c: sin asiento
            self.concretar(x1)
        self.assertFalse(AsientoContable.objects.exists())
        self.concretar(x2)
        asiento = self.asiento_de(x2.entrega)
        self.assertEqual(
            self.lineas(asiento),
            sorted([
                (cuentas.CAJA, DEBE, Decimal("10000.00")), (cuentas.VENTAS, HABER, Decimal("10000.00")),
                (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00")),
            ]),
        )
        self.assertNotIn(cuentas.DEUDORES_POR_VENTAS, [c for c, _, _ in self.lineas(asiento)])

    def test_post_h_un_detalle_rechazado_no_suma_a_ventas_ni_al_costo(self):
        """Una compra-venta con dos detalles en una entrega (30 y 20 a $100) y el cliente rechaza el segundo: Caja y Ventas por 3.000,00 y el costo solo de lo aceptado (30 × 1,0000)."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        otra, _ = variedad_con_stock(self.e, "Rúcula de la prueba")
        d1, d2 = detalle(venta, self.e.variedad, 30), detalle(venta, otra, 20)
        lote_b = lote_maduro(self.e, 300, variedad=otra)
        e = entrega(venta, [reserva_lista(d1, self.lote, 30), reserva_lista(d2, lote_b, 20)], transportista=t, fecha=HOY)
        iniciar_ruta_de(t)
        x = SimpleNamespace(entrega=e, contrato=venta, detalle=d1, transportista=t, envases=None)
        self.concretar(x, acepta={DetalleEntrega.objects.get(entrega=e, detalle_venta=d2).pk: False})
        self.assertEqual(
            self.lineas(self.asiento_de(e)),
            sorted([
                (cuentas.CAJA, DEBE, Decimal("3000.00")), (cuentas.VENTAS, HABER, Decimal("3000.00")),
                (cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("30.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("30.00")),
            ]),
        )

    def test_post_h_si_no_hubo_venta_ni_cobro_no_hay_asiento_de_la_entrega(self):
        """h: «si en la entrega no hubo ninguna venta ni cobro, no se generó asiento»: todo rechazado (8b) y sin costo entregado; el asiento de la entrega no existe y no falla
        (lo devuelto a una partida vigente tampoco asienta)."""
        x = self.concretable()
        self.concretar(x, acepta={self.linea(x).pk: False}, medio_pago="")
        self.assertFalse(AsientoContable.objects.exists())

    def test_post_h_una_entrega_no_ultima_sin_cobro_asienta_aunque_no_se_cobre(self):
        """8a: la primera entrega no cobra pero sí registra la venta contra Deudores: el asiento existe con medio de pago vacío."""
        x1, _ = self.dos_entregas()
        self.concretar(x1, medio_pago="")
        self.assertTrue(AsientoContable.objects.filter(origen_id=x1.entrega.pk).exists())

    # ---- e: la merma «daño en la entrega» ----

    def test_post_e_la_merma_de_la_entrega_se_valoriza_con_el_costo_de_cada_origen(self):
        """e: una entrega de dos orígenes (20 de lote a 2,5000 y 10 de cámara a 1,0000); llegan 25 de 30. Las 5 perdidas se reparten 3 y 2: el asiento de la merma es Debe Pérdidas por
        Mermas / Haber Productos Terminados por 3 × 2,5000 + 2 × 1,0000 = 9,50, originado en la merma. El costo entregado (17 × 2,5 + 8 × 1 = 50,50) va al asiento de la entrega."""
        x = self.mixta()
        self.concretar(x, llego={self.linea(x).pk: "25"})
        merma = Merma.objects.get(causa="dano_en_entrega")
        self.assertEqual(
            self.lineas(self.asiento_de(merma)), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, Decimal("9.50")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("9.50"))])
        )
        costo = [l for l in self.lineas(self.asiento_de(x.entrega)) if l[0] == cuentas.COSTO_DE_PRODUCCION_VENDIDA]
        self.assertEqual(costo, [(cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, Decimal("50.50"))])

    def test_regla_8_6_29_lo_devuelto_a_una_partida_vencida_asienta_perdidas_contra_productos_terminados(self):
        """Decisión (2) del 26/11/2026: lo devuelto a una partida que ya venció se registra como merma por vencimiento y se asienta como tal: Debe Pérdidas por Mermas / Haber
        Productos Terminados por 50 × 1,0000 = 50,00, originado en esa merma."""
        x = self.concretable()
        partida = x.reserva.lineas.get().partida
        StockCosechado.objects.filter(pk=partida.pk).update(fecha_limite=HOY - timedelta(days=1))
        self.concretar(x, acepta={self.linea(x).pk: False})
        merma = Merma.objects.get(causa="vencimiento_en_camara")
        self.assertEqual(
            self.lineas(self.asiento_de(merma)), sorted([(cuentas.PERDIDAS_POR_MERMAS, DEBE, Decimal("50.00")), (cuentas.PRODUCTOS_TERMINADOS, HABER, Decimal("50.00"))])
        )

    def test_regla_lo_devuelto_desde_un_lote_con_la_fecha_limite_pasada_asienta_su_vencimiento(self):
        """La partida nueva que nace vencida (regla «Lo devuelto a la cámara»): su merma por vencimiento (20 × 2,5000 = 50,00) también se asienta."""
        x = self.mixta(dias_atras=400)
        self.concretar(x, acepta={x.entrega.lineas.get().pk: False})
        merma = Merma.objects.get(causa="vencimiento_en_camara", cant_merma=20)
        self.assertEqual(self.lineas(self.asiento_de(merma))[0][2], Decimal("50.00"))

    # ---- g: los consumos de envases ----

    def test_post_g_cada_consumo_de_envase_asienta_costo_de_produccion_vendida_contra_insumos_en_stock(self):
        """g: un asiento por consumo, originado en el consumo, por su `monto_consumo` (con el exceso incluido: 12 envases): Debe Costo de Producción Vendida / Haber Insumos en Stock."""
        x = self.concretable(con_envasado=True)
        iin = x.envases.pk
        self.concretar(x, utilizada={iin: "12"}, confirmo_exceso={iin})
        consumo = Consumo.objects.get()
        self.assertGreater(consumo.monto_consumo, 0)
        self.assertEqual(
            self.lineas(self.asiento_de(consumo)),
            sorted([(cuentas.COSTO_DE_PRODUCCION_VENDIDA, DEBE, consumo.monto_consumo), (cuentas.INSUMOS_EN_STOCK, HABER, consumo.monto_consumo)]),
        )
        self.assertEqual(AsientoContable.objects.count(), 2)  # el del consumo y el de la entrega

    def test_post_g_lo_devuelto_de_un_envase_no_asienta(self):
        """g: «lo devuelto no generó ningún registro de stock»: con 10 reservados, 6 usados y 4 devueltos, el consumo es 6 y no hay otro asiento de envases."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, utilizada={x.envases.pk: "6"}, devuelta={x.envases.pk: "4"})
        self.assertEqual(Consumo.objects.get().cant_consumo, Decimal("6"))
        self.assertEqual(AsientoContable.objects.filter(origen__in=Consumo.objects.all()).count(), 1)

    # ---- auditoría y todo o nada ----

    def test_post_q_el_registro_de_auditoria_nombra_los_asientos(self):
        """q y D-86 punto 4: el único registro `concrecion_entrega` nombra cada asiento entre sus afectados y en `datos` (entrega, merma y consumo); no se audita aparte."""
        x = self.concretable(con_envasado=True)
        self.concretar(x, utilizada={x.envases.pk: "10"}, llego={self.linea(x).pk: "45"})
        (r,) = RegistroAuditoria.objects.filter(accion="concrecion_entrega")
        self.assertEqual(sum(1 for a in r.afectados if a["texto"].startswith("Asiento")), 3)
        self.assertEqual(len(r.detalle["datos"]["asientos"]), 3)
        self.assertEqual(AsientoContable.objects.count(), 3)

    def test_garantia_si_falla_un_asiento_no_queda_nada_de_la_concrecion(self):
        """Garantías mínimas: si el asiento falla, la entrega sigue «a realizar», sin pago, sin merma, sin consumo, y la auditoría no tiene el registro."""
        x = self.concretable(con_envasado=True)
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.concretar(x, utilizada={x.envases.pk: "10"}, llego={self.linea(x).pk: "45"})
        self.assertEqual(self.refrescar(x).estado_orden, "a_realizar")
        self.assertFalse(PagoCliente.objects.exists() or Merma.objects.exists() or Consumo.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.filter(accion="concrecion_entrega").exists())

    def test_d92_punto_5_un_costo_cero_omite_las_lineas_del_costo_y_conserva_la_venta(self):
        """H11: si el costo de lo entregado es $0,00 (origen sin costo, p. ej. un lote existente sin costo), las líneas del costo se omiten y no falla; queda el asiento de la venta."""
        x = self.concretable()
        StockCosechado.objects.filter(pk=x.reserva.lineas.get().partida_id).update(costo_unitario_cosechado=Decimal("0.0000"))
        self.concretar(x)
        self.assertEqual(
            self.lineas(self.asiento_de(x.entrega)), sorted([(cuentas.CAJA, DEBE, Decimal("5000.00")), (cuentas.VENTAS, HABER, Decimal("5000.00"))])
        )

    def test_paso_4_el_libro_muestra_el_origen_de_la_entrega_como_texto_sin_direccion(self):
        """CON-04c paso 4 (criterio de CON-04a, D-30): el origen del asiento compuesto se ve como «Entrega OT-… · CV-…, <cliente>», SIN enlace; una orden que no es una entrega
        (una cosecha, una siembra) no tiene texto propio. Y `ready()` lo registra una sola vez."""
        from comercial.servicios import asientos_comerciales
        from contabilidad import extensiones

        x = self.concretable()
        self.concretar(x)
        texto, url = extensiones.enlace_de_origen(self.asiento_de(x.entrega).origen)
        self.assertEqual((texto, url), (f"Entrega {x.entrega.codigo} · {x.contrato.codigo}, {self.e.cliente}", None))
        self.assertEqual(extensiones._ENLACES_DE_ORIGEN["orden_de_trabajo"].count(asientos_comerciales.enlace_de_orden_de_trabajo), 1)
        self.assertIsNone(asientos_comerciales.enlace_de_orden_de_trabajo(mock.Mock(pk=0)))
