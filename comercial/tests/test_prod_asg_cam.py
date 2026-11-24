# Pruebas de PROD-ASG-CAM, Asignar Stock de Cámara, y del paso diario 25 (COM-04b; docs/casos_de_uso/produccion/camara.md, «Cómo se aplica»; D-64 puntos 9 y 12).
# Una prueba por regla, postcondición y extensión; cada condición de «Candidato» va en su propia prueba. Las que escriben verifican al final los invariantes de reservas.
# La concurrencia está en `test_camara_concurrencia.py`. Los `on_commit` de PROD-CNC-CSC (k) y de la cancelación (h) están en `test_prod_cnc_csc.py` y
# `test_prod_cnl_ord_cosechas.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/camara.py`:
#   - `asignar_camara(partida_ids, hoy=None) -> list[ResultadoDeAsignacion]` con `ResultadoDeAsignacion(partida, reservas, detalles_reabiertos, ventas_reabiertas, reservado)`.
#     `hoy` es `stock.hoy()` por omisión. Procesa las partidas de a una (de la que vence antes a la que vence después; si empatan, la de menor id), una transacción por partida.
#     Una partida sin nada que asignar no figura en el resultado. Una partida que falla se registra en el log (`logger.exception`) y las demás siguen (1a y *a).
#   - `programar_asignacion_de_camara(partida_ids)`: `transaction.on_commit` con `asignar_camara` (D-64 punto 9). Sin ids, no programa nada.
#   - `reasignar_camara(hoy) -> ResumenDePaso(procesados, creados, resueltos, detalle)` (paso 25): `procesados` = partidas con stock libre intentadas, `creados` = reservas
#     creadas, `resueltos` = 0. Registrado como «reasignar_camara», «Reasignar cámara», orden 25.
#   - Reserva: «lista para entrega», una sola línea de la partida con `min(libre, sin cubrir)`, `fecha_reserva` = hoy, `fecha_entrega_reserva` = la del candidato, sin cosecha.
#   - Avisos (dentro de la transacción, D-42): al Vendedor de cada contrato, título «Stock de cámara para CV-0044»; al Agrónomo del invernadero, uno por partida, título
#     «Partida P-12 asignada». Correo al cliente (11, 11a) solo si un detalle dejó de estar pendiente y tiene correo, con `transaction.on_commit` y `core.correo.enviar_correo`.
#   - Auditoría: acción `asignacion_camara`, sin usuario (InfoPonia), un registro por partida con algo asignado; afectados: la partida, las reservas, sus líneas y los detalles y
#     ventas que cambiaron de estado. Sin asignación: ni auditoría ni avisos (postcondición i).
#   - Fuera de esta tarea (COM-04c y COM-05): anular el enlace del cliente, «sin entrega» de los candidatos y planificar la entrega (paso 9; postcondición e).

import logging
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import camara
from comercial.tests.fabricas import enlace as un_enlace
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    escenario_comercial,
    partida,
    reserva,
    segundo_invernadero,
    suministro,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import ROL_INFOPONIA, Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import crear_variedad
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, su Agrónomo y un lote de 300 plantas en Maduración."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 300)

    def venta(self, cantidad=40, dias=3, estado_detalle="abierto", estado_venta="abierta", **extra):
        """Un detalle de venta de la variedad del escenario (con envío) en una venta del Vendedor del invernadero."""
        return detalle(compra_venta(self.e, dias=dias, estado=estado_venta, **extra), self.e.variedad, cantidad, estado=estado_detalle)

    def pendiente(self, cantidad=40, dias=3):
        """Un detalle «pendiente de decisión del cliente» de una venta «pendiente de decisión del cliente» (el caso del flujo principal)."""
        d = self.venta(cantidad, dias, "pendiente_decision", "pendiente_decision")
        DetalleVenta.objects.filter(pk=d.pk).update(fecha_pendiente_decision=HOY)
        d.refresh_from_db()
        return d

    def asignar(self, *partidas):
        """`asignar_camara` de esas partidas con la fecha de hoy."""
        return camara.asignar_camara([p.pk for p in partidas], HOY)

    def lineas_de(self, p):
        """Las líneas de la partida `p`, por id."""
        return list(DetalleReserva.objects.filter(partida=p).select_related("reserva").order_by("pk"))


class ProdAsgCamServicioTests(Base):
    """PROD-ASG-CAM: el caso de uso, con la base."""

    # ---- flujo principal y postcondiciones ----

    def test_flujo_principal_cubre_el_detalle_pendiente_y_lo_pasa_a_abierto(self):
        """Pasos 1 a 7 de PROD-ASG-CAM: un detalle «pendiente de decisión» cubierto del todo pasa a «abierto» y su venta a «abierta» (postcondición d)."""
        p = partida(self.lote, 40)
        d = self.pendiente(40)
        resultado = self.asignar(p)
        self.assertEqual(len(resultado), 1)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "abierto")
        self.assertEqual(d.compra_venta.estado_venta, "abierta")
        self.assertIsNotNone(d.fecha_pendiente_decision)  # la fecha de pendiente se conserva como historial
        self.assertEqual([x.pk for x in resultado[0].detalles_reabiertos], [d.pk])
        verificar_invariantes_de_reservas()

    def test_post_a_crea_una_reserva_lista_para_entrega_con_sus_fechas(self):
        """Postcondición a: una reserva por candidato cubierto, `fecha_reserva` = hoy, `fecha_entrega_reserva` = la pactada, «lista para entrega», del invernadero de la partida, sin cosecha."""
        p = partida(self.lote, 40)
        d = self.venta(40, dias=5)
        self.asignar(p)
        r = ReservaStock.objects.get(detalle_venta=d)
        self.assertEqual(
            (r.estado_reserva, r.fecha_reserva, r.fecha_entrega_reserva, r.invernadero_id, r.cosecha_id),
            ("lista_para_entrega", HOY, d.compra_venta.fecha_pactada_venta, self.e.invernadero.pk, None),
        )

    def test_post_b_una_sola_linea_con_el_minimo_entre_el_stock_libre_y_lo_sin_cubrir(self):
        """Postcondición b: una única línea de la partida con `min(stock libre, sin cubrir)`; no cambia la disponible de la partida (garantía mínima)."""
        p = partida(self.lote, 100)
        d = self.venta(40)
        self.asignar(p)
        (linea,) = self.lineas_de(p)
        self.assertEqual((linea.reserva.detalle_venta_id, linea.cantidad_reservada), (d.pk, 40))
        p.refresh_from_db()
        self.assertEqual(p.cantidad_disponible_cosechado, 100)

    def test_post_c_asigna_en_el_orden_de_prioridad_hasta_agotar_el_stock_libre(self):
        """Postcondición c y regla «Orden de prioridad»: la fecha de entrega más próxima primero; la partida alcanza para una sola."""
        p = partida(self.lote, 40)
        lejos, cerca = self.venta(40, dias=9), self.venta(40, dias=2)
        self.asignar(p)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=cerca).count(), 1)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=lejos).count(), 0)

    def test_ext_4a_con_la_misma_fecha_gana_el_periodo_de_suministro(self):
        """Extensión 4a: con la misma fecha, primero los períodos de suministro y después los detalles de venta."""
        p = partida(self.lote, 20)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=3)
        venta = self.venta(20, dias=3)
        self.asignar(p)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=d_sum).count(), 1)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=venta).count(), 0)
        verificar_invariantes_de_suministros()

    def test_ext_5a_cobertura_parcial_toma_todo_lo_libre_y_deja_el_resto_sin_cubrir(self):
        """Extensión 5a: el stock no alcanza: se reserva todo lo libre y el candidato conserva la diferencia; un pendiente cubierto en parte SIGUE pendiente y no recibe correo."""
        p = partida(self.lote, 30)
        d = self.pendiente(50)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            self.asignar(p)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "pendiente_decision")
        self.assertEqual(self.lineas_de(p)[0].cantidad_reservada, 30)
        self.assertEqual(mail.outbox, [])
        aviso = Notificacion.objects.get(destinatario_id=self.e.vendedor.pk)
        self.assertIn("20", aviso.detalle)  # lo que sigue sin cubrir

    def test_ext_6a_el_stock_que_sobra_queda_libre(self):
        """Extensión 6a: después de cubrir a todos, lo que sobra queda libre en la partida."""
        p = partida(self.lote, 100)
        self.venta(40)
        self.asignar(p)
        p.refresh_from_db()
        reservado = sum(l.cantidad_reservada for l in self.lineas_de(p))
        self.assertEqual(p.cantidad_disponible_cosechado - reservado, 60)

    def test_ext_7a_un_detalle_abierto_no_cambia_de_estado_ni_manda_correo(self):
        """Extensión 7a: un detalle «abierto» cubierto no cambia de estado y no se manda correo al cliente."""
        p = partida(self.lote, 40)
        d = self.venta(40)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            resultado = self.asignar(p)
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, resultado[0].detalles_reabiertos, [m for m in mail.outbox if "faltante" in m.subject]), ("abierto", [], []))

    def test_ext_7b_si_la_venta_conserva_otro_detalle_pendiente_sigue_pendiente(self):
        """Extensión 7b: el detalle cubierto pasa a «abierto» pero la venta sigue en «pendiente de decisión»: le queda otro detalle pendiente."""
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        venta = compra_venta(self.e, estado="pendiente_decision")
        d1 = detalle(venta, self.e.variedad, 40, estado="pendiente_decision")
        d2 = detalle(venta, otra, 10, estado="pendiente_decision")
        p = partida(self.lote, 40)
        self.asignar(p)
        d1.refresh_from_db(), d2.refresh_from_db(), venta.refresh_from_db()
        self.assertEqual((d1.estado_detalle_venta, d2.estado_detalle_venta, venta.estado_venta), ("abierto", "pendiente_decision", "pendiente_decision"))

    # ---- avisos y correo ----

    def test_post_f_avisa_al_vendedor_y_al_agronomo(self):
        """Postcondición f: una notificación al Vendedor del contrato y una al Agrónomo del invernadero de la partida (dentro de la transacción, D-42)."""
        p = partida(self.lote, 40)
        d = self.venta(40)
        self.asignar(p)
        vendedor = Notificacion.objects.get(destinatario_id=self.e.vendedor.pk)
        agronomo = Notificacion.objects.get(destinatario_id=self.e.agronomo.pk)
        self.assertEqual(vendedor.titulo, f"Stock de cámara para {d.compra_venta.codigo}")
        self.assertEqual(agronomo.titulo, f"Partida {p.codigo} asignada")
        self.assertIn(d.compra_venta.codigo, agronomo.detalle)

    def test_ext_10a_varios_contratos_un_aviso_por_vendedor_de_cada_contrato_y_uno_solo_al_agronomo(self):
        """Extensión 10a: una notificación por contrato al Vendedor (solo con lo suyo) y una única por partida al Agrónomo, con todos los contratos."""
        p = partida(self.lote, 60)
        d1, d2 = self.venta(30, dias=2), self.venta(30, dias=4)
        self.asignar(p)
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk).count(), 2)
        (agronomo,) = Notificacion.objects.filter(destinatario_id=self.e.agronomo.pk)
        self.assertIn(d1.compra_venta.codigo, agronomo.detalle)
        self.assertIn(d2.compra_venta.codigo, agronomo.detalle)

    def test_ext_10b_sin_agronomo_se_avisa_solo_a_los_vendedores(self):
        """Extensión 10b: si el invernadero no tiene Agrónomo activo, no se avisa a nadie más."""
        from maestros.models import Invernadero

        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(agronomo=None)
        p = partida(self.lote, 40)
        self.venta(40)
        self.asignar(p)
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk).count(), 1)
        self.assertFalse(Notificacion.objects.filter(destinatario_id=self.e.agronomo.pk).exists())

    def test_post_g_manda_el_correo_al_cliente_cuando_el_detalle_deja_de_estar_pendiente(self):
        """Postcondición g y paso 11: un correo al cliente con correo («el faltante quedó cubierto»), después de confirmar (`on_commit`)."""
        p = partida(self.lote, 40)
        self.pendiente(40)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            self.asignar(p)
        (correo,) = [m for m in mail.outbox if "faltante" in m.subject]  # COM-05a1: cambiada: ahora también se planifica la entrega (aviso y correo propios); se mira solo lo de este caso de uso
        self.assertEqual(correo.to, [self.e.cliente.email_cliente])

    def test_ext_11a_cliente_sin_correo_el_vendedor_recibe_el_aviso_de_que_se_lo_informe(self):
        """Extensión 11a: sin correo del cliente no se envía nada y la notificación al Vendedor dice que el detalle dejó de estar pendiente y que el cliente no tiene correo."""
        from comercial.models import Cliente

        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        p = partida(self.lote, 40)
        self.pendiente(40)
        with override_settings(CORREO_CONFIGURADO=True), self.captureOnCommitCallbacks(execute=True):
            self.asignar(p)
        self.assertEqual(mail.outbox, [])
        aviso = Notificacion.objects.get(destinatario_id=self.e.vendedor.pk, titulo__startswith="Stock de cámara")  # COM-05a1: cambiada: ahora también se planifica la entrega (aviso y correo propios); se mira solo lo de este caso de uso
        self.assertIn("dejó de estar pendiente", aviso.detalle)
        self.assertIn("no tiene correo", aviso.detalle)

    # ---- auditoría ----

    def test_post_h_un_registro_de_auditoria_con_origen_infoponia(self):
        """Postcondición h: un registro `asignacion_camara` por partida, sin usuario (origen InfoPonia), con la partida, la reserva, su línea y el detalle que cambió de estado."""
        p = partida(self.lote, 40)
        d = self.pendiente(40)
        self.asignar(p)
        (registro,) = RegistroAuditoria.objects.filter(accion="asignacion_camara")
        self.assertEqual((registro.usuario_id, registro.rol), (None, ROL_INFOPONIA))
        modelos = {a["modelo"] for a in registro.afectados}
        self.assertTrue({"produccion.stockcosechado", "comercial.reservastock", "comercial.detallereserva", "comercial.detalleventa"} <= modelos)
        self.assertIn(d.pk, [a["id"] for a in registro.afectados if a["modelo"] == "comercial.detalleventa"])

    def test_post_i_sin_candidatos_no_cambia_nada_ni_audita_ni_avisa(self):
        """Postcondición i y extensión 3a: sin candidatos la partida queda igual: sin reservas, sin auditoría y sin avisos."""
        p = partida(self.lote, 40)
        self.assertEqual(self.asignar(p), [])
        self.assertEqual((ReservaStock.objects.count(), Notificacion.objects.count()), (0, 0))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="asignacion_camara").exists())

    # ---- extensiones de la partida ----

    def test_ext_2a_una_partida_vencida_o_agotada_o_sin_stock_libre_no_se_asigna(self):
        """Extensión 2a: no es asignable una partida «vencida», «agotada», con fecha límite anterior a hoy o con el stock libre en cero."""
        self.venta(40)
        vencida = partida(self.lote, 0, estado="vencido")
        agotada = partida(self.lote, 0, estado="agotado")
        pasada = partida(self.lote, 40, fecha_limite=HOY - timedelta(days=1))
        llena = partida(self.lote, 20)
        reserva(self.venta(20, dias=1), [(llena, 20)])
        self.assertEqual(self.asignar(vencida, agotada, pasada, llena), [])
        self.assertEqual(ReservaStock.objects.count(), 1)

    def test_ext_2a_el_dia_de_la_fecha_limite_todavia_es_asignable(self):
        """Regla «Partida asignable»: fecha límite igual o posterior a hoy."""
        p = partida(self.lote, 40, fecha_limite=HOY)
        d = self.venta(40, dias=0)
        self.assertEqual(len(self.asignar(p)), 1)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 1)

    def test_ext_1a_varias_partidas_de_la_que_vence_antes_a_la_que_vence_despues(self):
        """Extensión 1a: de a una, por fecha límite y después por id; cada una en su transacción."""
        tarde = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=20))
        temprano = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=10))
        d = self.venta(30)
        resultado = self.asignar(tarde, temprano)
        self.assertEqual([r.partida.pk for r in resultado], [temprano.pk, tarde.pk])
        self.assertEqual([l.cantidad_reservada for l in self.lineas_de(temprano)], [20])
        self.assertEqual([l.cantidad_reservada for l in self.lineas_de(tarde)], [10])
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(reserva__detalle_venta=d)), 30)

    def test_ext_a_si_una_partida_falla_se_registra_y_las_demas_siguen(self):
        """Extensión *a y 1a: una partida que falla se revierte y se registra en el log (`logger.exception` con su id); las demás se procesan y la recupera el paso 25."""
        mala = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=5))
        buena = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=9))
        self.venta(40)
        original = camara._asignar_partida

        def falla_la_primera(partida_id, hoy):
            if partida_id == mala.pk:
                raise RuntimeError("falla de prueba")
            return original(partida_id, hoy)

        with mock.patch.object(camara, "_asignar_partida", side_effect=falla_la_primera), self.assertLogs("infoponia.camara", level=logging.ERROR) as log:
            resultado = self.asignar(mala, buena)
        self.assertEqual([r.partida.pk for r in resultado], [buena.pk])
        self.assertIn(str(mala.pk), "\n".join(log.output))
        self.assertEqual(self.lineas_de(mala), [])

    # ---- cada condición de «Candidato» ----

    def test_candidato_de_otra_variedad_no_se_considera(self):
        """Regla «Candidato»: es de la variedad de la partida."""
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        detalle(compra_venta(self.e), otra, 40)
        self.assertEqual(self.asignar(partida(self.lote, 40)), [])

    def test_candidato_con_entrega_posterior_a_la_fecha_limite_no_se_considera(self):
        """Regla «Candidato»: su fecha de entrega no es posterior a la fecha límite de la partida (regla 17 de 8.8)."""
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=5))
        self.venta(40, dias=6)
        self.assertEqual(self.asignar(p), [])

    def test_candidato_con_retiro_solo_si_es_el_invernadero_de_retiro(self):
        """Regla «Candidato»: en una compra-venta con retiro, solo si es el invernadero de retiro."""
        otro = segundo_invernadero(self.e)
        propio = detalle(compra_venta(self.e, modalidad="retiro", retiro=self.e.invernadero), self.e.variedad, 20)
        ajeno = detalle(compra_venta(self.e, modalidad="retiro", retiro=otro.invernadero), self.e.variedad, 20)
        self.asignar(partida(self.lote, 100))
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=propio).count(), 1)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=ajeno).count(), 0)

    def test_candidato_con_envio_solo_si_el_vendedor_del_contrato_es_el_del_invernadero(self):
        """Regla «Candidato»: con envío, solo si el invernadero es uno de los del Vendedor (actual) del contrato."""
        from maestros.tests.fabricas import crear_vendedor

        otro_vendedor = crear_vendedor(email="otro.vendedor@infoponia.com")
        ajeno = detalle(compra_venta(self.e, vendedor=otro_vendedor), self.e.variedad, 20)
        self.assertEqual(self.asignar(partida(self.lote, 100)), [])
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=ajeno).count(), 0)

    def test_candidato_un_detalle_confirmado_o_rechazado_no_recibe_reservas(self):
        """Regla «Candidato» y garantía mínima: un detalle «confirmado» o «rechazado» nunca recibe reservas."""
        self.venta(20, estado_detalle="confirmado")
        self.venta(20, estado_detalle="rechazado")
        self.assertEqual(self.asignar(partida(self.lote, 100)), [])

    def test_candidato_de_una_venta_que_no_esta_abierta_no_se_considera(self):
        """Regla «Candidato»: la venta tiene que estar «abierta» o «pendiente de decisión»."""
        self.venta(20, estado_venta="cancelada")
        self.venta(20, estado_venta="concretada")
        self.assertEqual(self.asignar(partida(self.lote, 100)), [])

    def test_candidato_ya_cubierto_no_tiene_cantidad_sin_cubrir(self):
        """Regla «Candidato»: con cantidad sin cubrir mayor que 0; un detalle ya cubierto por otra reserva no recibe más."""
        d = self.venta(20)
        reserva(d, [(partida(self.lote, 20), 20)])
        self.assertEqual(self.asignar(partida(self.lote, 100)), [])

    def test_candidato_periodo_dentro_de_la_ventana_si_y_fuera_de_la_ventana_no(self):
        """Regla «Candidato» (situación 2): el período de un suministro vigente solo si su fecha cae dentro de la ventana de pre-reserva (hoy + días de pre-reserva, 14)."""
        dentro = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=10, primera_en_dias=10)
        fuera = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=10, primera_en_dias=40)
        p = partida(self.lote, 100, fecha_limite=HOY + timedelta(days=90))
        self.asignar(p)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=dentro).count(), 1)
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=fuera).count(), 0)

    def test_candidato_periodo_de_un_detalle_finalizado_dentro_de_su_fecha_de_fin_si_y_despues_no(self):
        """Regla «Candidato» y D-64 punto 8: un período de un detalle «finalizado» todavía se debe hasta su `fecha_fin_detalle`; uno posterior, no."""
        fin = HOY + timedelta(days=4)
        d = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=10, periodo=2, primera_en_dias=2, estado="finalizado", fecha_fin_detalle=fin)
        self.asignar(partida(self.lote, 100))
        fechas = sorted(ReservaStock.objects.filter(detalle_suministro=d).values_list("fecha_entrega_reserva", flat=True))
        self.assertEqual(fechas, [HOY + timedelta(days=2), fin])

    def test_candidato_un_periodo_anterior_a_hoy_sigue_siendo_candidato(self):
        """Regla «Fecha de entrega pasada»: un período cuya fecha ya pasó sigue siendo candidato, porque la entrega se debe."""
        d = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=10, periodo=30, primera_en_dias=-2)
        self.asignar(partida(self.lote, 100))
        self.assertEqual(ReservaStock.objects.get(detalle_suministro=d).fecha_entrega_reserva, HOY - timedelta(days=2))

    def test_candidato_un_suministro_que_no_esta_vigente_no_se_considera(self):
        """Regla «Candidato»: un período de un suministro «vigente»; uno «finalizado» no."""
        detalle_suministro(suministro(self.e, estado="finalizado"), self.e.variedad, cantidad=10, primera_en_dias=2)
        self.assertEqual(self.asignar(partida(self.lote, 100)), [])

    def test_regla_un_pendiente_que_se_cubre_no_anula_el_enlace_todavia(self):
        """El detalle pendiente que se cubre pasa a «abierto»; anular su enlace de decisión es de COM-04c (`EnlaceCliente` todavía no existe): no se rompe sin él."""
        d = self.pendiente(40)
        self.asignar(partida(self.lote, 40))
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "abierto")

    def test_post_d_el_enlace_de_la_venta_que_vuelve_a_abierta_se_anula(self):
        """Postcondición d y D-65 punto 5: al quedar sin detalles pendientes, el enlace de decisión de la venta pasa a `anulado` (y va a la auditoría)."""
        d = self.pendiente(40)
        creado, _ = un_enlace(d.compra_venta)
        self.asignar(partida(self.lote, 40))
        creado.refresh_from_db()
        self.assertEqual(creado.estado, "anulado")
        registro = RegistroAuditoria.objects.get(accion="asignacion_camara")
        self.assertIn("comercial.enlacecliente", {a["modelo"] for a in registro.afectados})

    def test_ext_5a_un_pendiente_cubierto_en_parte_mantiene_el_enlace_vigente(self):
        """Extensión 5a: el detalle cubierto en parte sigue pendiente y su enlace sigue sirviendo (muestra la cantidad nueva, sin correo)."""
        d = self.pendiente(40)
        creado, _ = un_enlace(d.compra_venta)
        self.asignar(partida(self.lote, 10))
        d.refresh_from_db()
        creado.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, creado.estado), ("pendiente_decision", "vigente"))

    def test_post_d_con_otro_detalle_pendiente_la_venta_no_vuelve_a_abierta_y_el_enlace_sigue(self):
        """Extensión 5b: si a la venta le queda otro detalle pendiente, sigue «pendiente de decisión» y su enlace vigente."""
        d = self.pendiente(40)
        otra = crear_variedad(self.e.variedad.cultivo, nombre="Otra")
        detalle(d.compra_venta, otra, 10, estado="pendiente_decision")
        creado, _ = un_enlace(d.compra_venta)
        self.asignar(partida(self.lote, 40))
        d.refresh_from_db()
        creado.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.compra_venta.estado_venta, creado.estado), ("abierto", "pendiente_decision", "vigente"))

    # ---- on_commit y paso 25 ----

    def test_regla_programar_corre_asignar_camara_despues_de_confirmar(self):
        """D-64 punto 9: `programar_asignacion_de_camara` registra un `on_commit`; recién al confirmar se asigna."""
        p = partida(self.lote, 40)
        d = self.venta(40)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            camara.programar_asignacion_de_camara([p.pk])
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 0)
        for callback in callbacks:
            callback()
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 1)

    def test_regla_programar_sin_partidas_no_registra_nada(self):
        """Sin partidas, `programar_asignacion_de_camara` no programa nada."""
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            camara.programar_asignacion_de_camara([])
        self.assertEqual(callbacks, [])

    def test_regla_paso_25_recupera_la_partida_que_dejo_sin_asignar_comercial_4a(self):
        """Paso 25 (D-64 punto 9): una partida «disponible» con stock libre y un candidato esperando se asigna sola (lo que dejó COM-04a sin el `on_commit`)."""
        p = partida(self.lote, 40)
        d = self.venta(40)
        resumen = camara.reasignar_camara(HOY)
        self.assertIsInstance(resumen, ResumenDePaso)
        self.assertEqual((resumen.procesados, resumen.creados), (1, 1))
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 1)
        verificar_invariantes_de_reservas()

    def test_regla_paso_25_es_idempotente(self):
        """Contrato del paso (D-56 punto 4): correrlo dos veces el mismo día no duplica reservas, avisos ni auditoría."""
        partida(self.lote, 100)
        self.venta(40)
        camara.reasignar_camara(HOY)
        reservas, avisos, auditorias = ReservaStock.objects.count(), Notificacion.objects.count(), RegistroAuditoria.objects.count()
        segundo = camara.reasignar_camara(HOY)
        self.assertEqual(
            (ReservaStock.objects.count(), Notificacion.objects.count(), RegistroAuditoria.objects.count(), segundo.creados), (reservas, avisos, auditorias, 0)
        )

    def test_regla_paso_25_ignora_las_partidas_vencidas_y_sin_stock_libre(self):
        """Paso 25: solo toda partida «disponible», con `fecha_limite >= hoy` y stock libre mayor que 0."""
        partida(self.lote, 40, fecha_limite=HOY - timedelta(days=1))
        partida(self.lote, 0, estado="agotado")
        self.venta(40)
        resumen = camara.reasignar_camara(HOY)
        self.assertEqual((resumen.procesados, resumen.creados, ReservaStock.objects.count()), (0, 0, 0))

    def test_regla_los_pasos_diarios_incluyen_el_25_entre_el_20_y_el_35(self):
        """D-56 y D-64 punto 9: el paso 25 «reasignar_camara» queda registrado después de vencer partidas (20) y antes de la pre-reserva."""
        pasos = {p.orden: p.codigo for p in pasos_diarios()}
        self.assertEqual(pasos[25], "reasignar_camara")
        self.assertEqual(sorted(o for o in pasos if o in (20, 25, 35, 40)), [20, 25, 35, 40])


class PlanificacionDeLaEntregaTests(Base):
    """COM-05a1: el paso 9 y la postcondición e de PROD-ASG-CAM (planificar la entrega) y la condición «sin línea en una entrega no cancelada» de los candidatos."""

    def test_post_e_paso_9_la_venta_que_queda_lista_programa_su_entrega_despues_de_confirmar(self):
        """Paso 9: la asignación que deja lista una venta dispara COM-PNF-ENT con `on_commit`."""
        from comercial.models import Entrega

        p = partida(self.lote, 40)
        self.venta(40)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.asignar(p)
            self.assertEqual(Entrega.objects.count(), 0)
        for callback in callbacks:
            callback()
        self.assertEqual(Entrega.objects.count(), 1)

    def test_regla_candidato_un_detalle_con_linea_en_una_entrega_a_realizar_ya_no_es_candidato(self):
        """Regla «Candidato»: un detalle de venta con alguna línea en una entrega «a realizar» o «concretada» no es candidato (la cámara no le agrega más)."""
        from comercial.tests.fabricas import entrega, reserva_lista

        d = self.venta(40)
        entrega(d.compra_venta, [reserva_lista(d, self.lote, 10)])
        self.asignar(partida(self.lote, 100))
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 1)

    def test_regla_candidato_un_detalle_con_su_entrega_cancelada_si_es_candidato(self):
        """Regla «Candidato»: una entrega cancelada no cuenta (la línea queda de historial): el detalle vuelve a ser candidato."""
        from comercial.tests.fabricas import entrega, reserva_lista

        d = self.venta(40)
        entrega(d.compra_venta, [reserva_lista(d, self.lote, 10)], estado="cancelada")
        self.asignar(partida(self.lote, 100))
        self.assertEqual(ReservaStock.objects.filter(detalle_venta=d).count(), 2)

    def test_regla_candidato_un_periodo_con_linea_en_una_entrega_ya_no_es_candidato(self):
        """Lo mismo para un período de suministro: con una línea en una entrega «a realizar» no es candidato."""
        from comercial.tests.fabricas import detalle_suministro, entrega, reserva_lista, suministro

        s = suministro(self.e)
        ds = detalle_suministro(s, self.e.variedad, cantidad=40, primera_en_dias=3)
        fecha = ds.fecha_primer_entrega
        entrega(s, [reserva_lista(None, self.lote, 10, fecha_entrega=fecha, detalle_suministro=ds)])
        self.asignar(partida(self.lote, 100))
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=ds, fecha_entrega_reserva=fecha).count(), 1)
