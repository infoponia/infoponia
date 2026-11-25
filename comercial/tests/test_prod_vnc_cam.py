# Pruebas de PROD-VNC-CAM, Vencer Partidas en Cámara (COM-04b, paso diario 20; docs/casos_de_uso/produccion/camara.md, «Cómo se aplica»; D-64 puntos 10 y 13; MD-134).
# Una prueba por postcondición y por extensión. Las que escriben verifican al final los invariantes de reservas. La concurrencia está en `test_camara_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/camara.py`:
#   - `vencer_partidas_en_camara(hoy) -> ResumenDePaso(procesados, creados, resueltos, detalle)`: `procesados` = partidas vencidas, `creados` = avisos «partida por vencer» nuevos,
#     `resueltos` = alertas «partida por vencer» resueltas, `detalle` = «N partidas con producto reservado». Registrado como «vencer_partidas_en_camara», «Vencer partidas
#     en cámara», orden 20. Una partida por transacción; una que falla se registra con `logger.exception` y las demás siguen (*a).
#   - Una partida vence cuando está «disponible» y su fecha límite es ANTERIOR a hoy: el día de la fecha límite todavía se entrega (regla 17 de 8.8).
#   - Alertas (D-64 punto 10): `comercial_partida_por_vencer` (clave `partida:{id}`, destinatario Agrónomo o Gerente, vínculo `AlertaComercial.partida`) y
#     `comercial_merma_camara_reservada` (evento, vínculo `produccion.AlertaDeMerma`). Constantes `TIPO_POR_VENCER` y `TIPO_MERMA_RESERVADA`.
#   - `resolver_aviso_de_partida(partida) -> Alerta | None`: resuelve la alerta «partida por vencer» activa de la partida.
#   - Auditoría: `vencimiento_partida` por partida vencida y `aviso_partida_por_vencer` por aviso, los dos sin usuario (InfoPonia).
#   - Se vuelve a cubrir DESPUÉS de dar de baja el stock físico (decisión del plan): así lo cubierto nunca sale de la misma partida que se pierde.
#   - Fuera de esta tarea: quitar las líneas de su entrega «a realizar» (COM-05), el enlace del cliente (COM-04c) y el asiento (D-57). La extensión 3b la suma COM-06a (clase `ProdVncCam3bTests`, al final).

import logging
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from comercial.models import AlertaComercial, DetalleReserva, DetalleVenta, EnlaceCliente, Entrega, ReservaStock
from comercial.servicios import camara
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    entrega,
    escenario_comercial,
    iniciar_ruta_de,
    partida,
    reserva,
    reserva_de_periodo,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_suministros,
)
from core.models import ROL_INFOPONIA, Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso, pasos_diarios
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from maestros.servicios import configuracion
from produccion.models import Merma, MovimientoStock, StockCosechado
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()
AYER = HOY - timedelta(days=1)


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor y su Agrónomo y un lote de 300 plantas en Maduración."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 300)

    def venta(self, cantidad=30, dias=3, estado_detalle="abierto", estado_venta="abierta"):
        """Un detalle de venta (con envío) de la variedad del escenario."""
        return detalle(compra_venta(self.e, dias=dias, estado=estado_venta), self.e.variedad, cantidad, estado=estado_detalle)

    def vencida(self, disponible=40):
        """Una partida «disponible» con la fecha límite de ayer."""
        return partida(self.lote, disponible, fecha_limite=AYER)

    def vigente(self, disponible=40):
        """Una partida «disponible» con 30 días por delante."""
        return partida(self.lote, disponible)

    def sin_stock_de_lote(self):
        """Agota el stock libre del lote del escenario con una reserva de otro contrato (así `asignar` no encuentra de dónde cubrir)."""
        reserva(self.venta(300, dias=40), [(self.lote, 300)])

    def correr(self, hoy=HOY):
        """El paso 20."""
        return camara.vencer_partidas_en_camara(hoy)

    def avisos_de(self, p):
        """Las alertas «partida por vencer» de la partida."""
        return Alerta.objects.filter(tipo_alerta=camara.TIPO_POR_VENCER, clave_estado=f"partida:{p.pk}")


class ProdVncCamServicioTests(Base):
    """PROD-VNC-CAM: el paso 20 con la base."""

    # ---- sin producto reservado: postcondiciones a y c ----

    def test_flujo_principal_vence_la_partida_sin_producto_reservado(self):
        """Flujo básico, pasos 2 y 3 (postcondiciones a y c): la partida vencida queda «vencida» con disponible 0 y su merma por vencimiento."""
        p = self.vencida(40)
        resumen = self.correr()
        p.refresh_from_db()
        self.assertEqual((p.estado_stock_cosechado, p.cantidad_disponible_cosechado), ("vencido", 0))
        self.assertIsInstance(resumen, ResumenDePaso)
        self.assertEqual((resumen.procesados, resumen.detalle), (1, "0 partidas con producto reservado"))
        verificar_invariantes_de_reservas()

    def test_post_a_la_merma_es_por_vencimiento_sin_responsable_y_con_su_movimiento(self):
        """Postcondición a y regla «Merma por vencimiento»: una merma «vencimiento en cámara» por toda la disponible, del lote de origen, sin responsable (InfoPonia), con su movimiento `merma_en_camara`."""
        p = self.vencida(40)
        self.correr()
        merma = Merma.objects.get(lote=self.lote, causa="vencimiento_en_camara")
        self.assertEqual((merma.cant_merma, merma.responsable_id, merma.etapa_id), (40, None, None))
        movimiento = MovimientoStock.objects.get(partida=p, tipo_movimiento="merma_en_camara")
        self.assertEqual((movimiento.cantidad, movimiento.origen_id), (40, merma.pk))

    def test_regla_el_dia_de_la_fecha_limite_no_vence(self):
        """Regla «Partida vencida»: su fecha límite es ANTERIOR a hoy; el día de la fecha límite todavía se puede entregar."""
        p = partida(self.lote, 40, fecha_limite=HOY)
        resumen = self.correr()
        p.refresh_from_db()
        self.assertEqual((p.estado_stock_cosechado, resumen.procesados), ("disponible", 0))

    def test_ext_2a_sin_partidas_vencidas_no_hace_nada(self):
        """Extensión 2a: sin partidas vencidas el paso sigue con los avisos y no crea mermas ni auditoría de vencimiento."""
        self.vigente()
        resumen = self.correr()
        self.assertEqual((resumen.procesados, Merma.objects.count()), (0, 0))
        self.assertFalse(RegistroAuditoria.objects.filter(accion="vencimiento_partida").exists())

    def test_regla_dos_corridas_el_mismo_dia_no_duplican_nada(self):
        """Contrato del paso (D-56 punto 4) y garantía mínima: ninguna partida genera más de una merma por vencimiento ni más de un aviso."""
        self.vencida(40)
        con_aviso = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=2))
        self.correr()
        merma, avisos, auditorias, notificaciones = Merma.objects.count(), Alerta.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()
        segundo = self.correr()
        self.assertEqual((Merma.objects.count(), Alerta.objects.count(), RegistroAuditoria.objects.count(), Notificacion.objects.count()), (merma, avisos, auditorias, notificaciones))
        self.assertEqual((segundo.procesados, segundo.creados), (0, 0))
        self.assertEqual(self.avisos_de(con_aviso).count(), 1)

    def test_post_g_un_registro_de_auditoria_por_partida_con_origen_infoponia(self):
        """Postcondición g: un registro `vencimiento_partida` por partida vencida, sin usuario, con la partida, la merma y su movimiento."""
        p = self.vencida(40)
        self.correr()
        (registro,) = RegistroAuditoria.objects.filter(accion="vencimiento_partida")
        self.assertEqual((registro.usuario_id, registro.rol), (None, ROL_INFOPONIA))
        modelos = {a["modelo"] for a in registro.afectados}
        self.assertTrue({"produccion.stockcosechado", "produccion.merma", "produccion.movimientostock"} <= modelos)
        self.assertIn(p.pk, [a["id"] for a in registro.afectados if a["modelo"] == "produccion.stockcosechado"])

    def test_ext_a_si_una_partida_falla_se_registra_y_las_demas_siguen(self):
        """Extensión *a: cada partida en su transacción; la que falla se registra con `logger.exception` y las demás se procesan; al día siguiente se retoma."""
        mala, buena = self.vencida(10), self.vencida(20)
        original = camara._vencer_partida

        def falla_la_primera(partida_id, hoy):
            if partida_id == mala.pk:
                raise RuntimeError("falla de prueba")
            return original(partida_id, hoy)

        with mock.patch.object(camara, "_vencer_partida", side_effect=falla_la_primera), self.assertLogs("infoponia.camara", level=logging.ERROR) as log:
            resumen = self.correr()
        mala.refresh_from_db(), buena.refresh_from_db()
        self.assertEqual((mala.estado_stock_cosechado, buena.estado_stock_cosechado, resumen.procesados), ("disponible", "vencido", 1))
        self.assertIn(str(mala.pk), "\n".join(log.output))
        self.assertEqual(self.correr().procesados, 1)  # al día siguiente (la próxima corrida) se retoma

    # ---- con producto reservado: postcondición d y extensión 3a ----

    def test_ext_3a_una_reserva_de_la_partida_vencida_se_recorta_a_cero_y_se_libera(self):
        """Extensión 3a, paso 1: las líneas reservadas se recortan a 0 y la reserva sin cobertura pasa a «liberada»."""
        p = self.vencida(40)
        d = self.venta(30)
        r = reserva(d, [(p, 30)])
        self.correr()
        self.assertEqual(DetalleReserva.objects.get(reserva=r).cantidad_reservada, 0)
        self.assertEqual(ReservaStock.objects.get(pk=r.pk).estado_reserva, "liberada")
        verificar_invariantes_de_reservas()

    def test_ext_3a_un_detalle_abierto_se_vuelve_a_cubrir_con_otra_partida(self):
        """Extensión 3a, paso 2 (`asignar`): el detalle «abierto» afectado vuelve a cubrirse con otra partida vigente."""
        p = self.vencida(40)
        otra = self.vigente(100)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.correr()
        nuevas = DetalleReserva.objects.filter(partida=otra, reserva__detalle_venta=d)
        self.assertEqual(sum(l.cantidad_reservada for l in nuevas), 30)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "abierto")
        verificar_invariantes_de_reservas()

    def test_ext_3a_2a_sin_stock_el_detalle_abierto_pasa_a_pendiente_de_decision_sin_enlace(self):
        """Extensión 3a.2a y regla 16 de 8.6: lo que no se cubre sigue el camino de faltante: el detalle y su venta pasan a «pendiente de decisión del cliente» con la fecha de hoy. El enlace del cliente es de COM-04c."""
        p = self.vencida(40)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.sin_stock_de_lote()
        self.correr()
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.compra_venta.estado_venta, d.fecha_pendiente_decision), ("pendiente_decision", "pendiente_decision", HOY))

    def test_ext_3a_2a_el_cliente_con_correo_recibe_el_enlace_nuevo_y_va_a_la_auditoria(self):
        """Extensión 3a.2a (COM-04c): lo que no se cubre sigue el camino de faltante completo: enlace vigente para el cliente y el enlace en la auditoría del vencimiento."""
        p = self.vencida(40)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.sin_stock_de_lote()
        self.correr()
        creado = EnlaceCliente.objects.get(compra_venta=d.compra_venta)
        self.assertEqual((creado.estado, creado.fecha_vencimiento), ("vigente", HOY + timedelta(days=2)))
        registro = RegistroAuditoria.objects.get(accion="vencimiento_partida")
        self.assertIn("comercial.enlacecliente", {a["modelo"] for a in registro.afectados})

    def test_ext_3a_un_detalle_pendiente_no_se_vuelve_a_cubrir_y_suma_al_faltante(self):
        """Extensión 3a: un detalle «pendiente de decisión» no llama a `asignar` (precondición b de PROD-ASG-STK): va directo al camino de faltante con la fecha de pendiente nueva, aunque haya otra partida."""
        p = self.vencida(40)
        otra = self.vigente(100)
        d = self.venta(30, estado_detalle="pendiente_decision", estado_venta="pendiente_decision")
        DetalleVenta.objects.filter(pk=d.pk).update(fecha_pendiente_decision=HOY - timedelta(days=1))
        reserva(d, [(p, 10)])
        self.correr()
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.fecha_pendiente_decision), ("pendiente_decision", HOY))
        self.assertFalse(DetalleReserva.objects.filter(partida=otra).exists())

    def test_ext_3a_un_detalle_confirmado_se_cubre_con_la_cantidad_aceptada(self):
        """Extensión 3a y D-64 punto 13: un detalle «confirmado» que pierde producto se intenta cubrir con la cantidad aceptada (`cant_entregada_venta`) como pedida."""
        p = self.vencida(40)
        otra = self.vigente(100)
        d = self.venta(50, estado_detalle="confirmado")
        DetalleVenta.objects.filter(pk=d.pk).update(cant_entregada_venta=30)
        reserva(d, [(p, 30)])
        self.correr()
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "confirmado")
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida=otra, reserva__detalle_venta=d)), 30)

    def test_ext_3a_un_detalle_confirmado_sin_stock_vuelve_a_pendiente_y_pierde_la_cantidad_aceptada(self):
        """D-64 punto 13: lo que no se cubre vuelve a «pendiente de decisión del cliente» con `cant_entregada_venta` vacía."""
        p = self.vencida(40)
        d = self.venta(50, estado_detalle="confirmado")
        DetalleVenta.objects.filter(pk=d.pk).update(cant_entregada_venta=30)
        reserva(d, [(p, 30)])
        self.sin_stock_de_lote()
        self.correr()
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.cant_entregada_venta, d.fecha_pendiente_decision), ("pendiente_decision", None, HOY))

    def test_ext_3a_un_periodo_de_suministro_se_vuelve_a_cubrir_o_queda_sin_cubrir_sin_cambiar_de_estado(self):
        """Extensión 3a.2a y regla 17 de 8.6: un período se vuelve a cubrir con otra partida; si no hay, queda con cantidad sin cubrir y el contrato no cambia de estado."""
        p = self.vencida(40)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=3)
        fecha = HOY + timedelta(days=3)
        reserva_de_periodo(d_sum, fecha, [(p, 30)])
        self.correr()
        d_sum.refresh_from_db()
        self.assertEqual(d_sum.estado_detalle_suministro, "vigente")
        self.assertFalse(ReservaStock.objects.filter(detalle_suministro=d_sum, estado_reserva="lista_para_entrega").exists())
        verificar_invariantes_de_suministros()

    def test_post_d_alerta_de_merma_con_producto_reservado_y_aviso_al_vendedor(self):
        """Postcondición d, regla 8 de 8.9 y D-64 punto 10: la alerta `comercial_merma_camara_reservada` (enlazada a la merma por `AlertaDeMerma`) para el Agrónomo y una notificación al Vendedor del contrato afectado."""
        from produccion.models import AlertaDeMerma

        p = self.vencida(40)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.correr()
        merma = Merma.objects.get(causa="vencimiento_en_camara")
        enlace = AlertaDeMerma.objects.get(merma=merma)
        self.assertEqual((enlace.alerta.tipo_alerta, enlace.alerta.agronomo_id), (camara.TIPO_MERMA_RESERVADA, self.e.agronomo.pk))
        self.assertIn(p.codigo, enlace.alerta.descripcion_alerta)
        self.assertIn(d.compra_venta.codigo, enlace.alerta.descripcion_alerta)
        self.assertTrue(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk, detalle__contains=d.compra_venta.codigo).exists())

    def test_post_d_sin_producto_reservado_no_hay_alerta_de_merma(self):
        """Postcondición d: la alerta de merma con producto reservado solo existe si la partida tenía líneas reservadas."""
        from produccion.models import AlertaDeMerma

        self.vencida(40)
        self.correr()
        self.assertFalse(AlertaDeMerma.objects.exists())

    def test_resumen_cuenta_las_partidas_con_producto_reservado(self):
        """Resumen del paso: «N partidas con producto reservado»."""
        p = self.vencida(40)
        reserva(self.venta(30), [(p, 30)])
        self.vencida(10)
        resumen = self.correr()
        self.assertEqual((resumen.procesados, resumen.detalle), (2, "1 partidas con producto reservado"))

    # ---- aviso previo: postcondiciones e y f, extensión 4a ----

    def test_post_f_avisa_una_sola_vez_una_partida_que_entra_en_el_plazo(self):
        """Postcondición f y pasos 4 y 5: una partida «disponible» con stock libre que vence dentro de los días de aviso (3) genera la alerta «partida por vencer» al Agrónomo con su vínculo y una notificación al Vendedor del invernadero."""
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=2))
        resumen = self.correr()
        alerta = self.avisos_de(p).get()
        self.assertEqual((resumen.creados, alerta.agronomo_id, alerta.estado_alerta), (1, self.e.agronomo.pk, "activa"))
        self.assertEqual(AlertaComercial.objects.get(alerta=alerta).partida_id, p.pk)
        self.assertIn("40 plantas libres", alerta.descripcion_alerta)
        self.assertIn("en 2 días", alerta.descripcion_alerta)
        self.assertEqual(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk, titulo="Partida por vencer").count(), 1)
        self.assertTrue(RegistroAuditoria.objects.filter(accion="aviso_partida_por_vencer").exists())

    def test_post_f_el_ultimo_dia_de_la_fecha_limite_tambien_entra_en_el_plazo(self):
        """Regla «Aviso previo»: `hoy <= fecha_limite <= hoy + días`."""
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=3))
        self.correr()
        self.assertEqual(self.avisos_de(p).count(), 1)
        lejos = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=4))
        self.correr()
        self.assertEqual(self.avisos_de(lejos).count(), 0)

    def test_post_f_una_partida_sin_stock_libre_no_se_avisa(self):
        """Paso 4: solo partidas con stock libre mayor que 0 (todo reservado = sin aviso)."""
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=2))
        reserva(self.venta(40), [(p, 40)])
        self.correr()
        self.assertEqual(self.avisos_de(p).count(), 0)

    def test_ext_4a_con_cero_dias_de_aviso_no_se_generan_avisos(self):
        """Extensión 4a: con `dias_aviso_vencimiento_camara` en 0 no se genera ningún aviso previo."""
        from core.tests.fabricas import crear_gerente

        configuracion.modificar_configuracion(crear_gerente(), dias_aviso_vencimiento_camara=0)
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=1))
        resumen = self.correr()
        self.assertEqual((self.avisos_de(p).count(), resumen.creados), (0, 0))

    def test_post_e_al_vencer_la_alerta_de_partida_por_vencer_queda_resuelta(self):
        """Postcondición e: si la partida tenía activa la alerta «partida por vencer», queda resuelta al vencer."""
        p = partida(self.lote, 40, fecha_limite=HOY)
        self.correr()  # el día de la fecha límite: aviso
        self.assertEqual(self.avisos_de(p).get().estado_alerta, "activa")
        siguiente = HOY + timedelta(days=1)
        resumen = self.correr(siguiente)
        self.assertEqual((self.avisos_de(p).get().estado_alerta, resumen.resueltos), ("resuelta", 1))

    def test_regla_resolver_aviso_de_partida_la_resuelve_y_no_falla_sin_alerta(self):
        """`resolver_aviso_de_partida`: pasa a «resuelta» la alerta activa (cuando la partida se agota); sin alerta devuelve `None`."""
        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=2))
        self.assertIsNone(camara.resolver_aviso_de_partida(p))
        self.correr()
        from django.db import transaction

        with transaction.atomic():
            resuelta = camara.resolver_aviso_de_partida(p)
        self.assertEqual(resuelta.estado_alerta, "resuelta")

    def test_regla_los_pasos_diarios_listan_20_25_35_y_40(self):
        """`proceso_diario --listar` muestra 20, 25, 35 y 40 (D-56)."""
        pasos = {p.orden: p.codigo for p in pasos_diarios()}
        self.assertEqual(pasos[20], "vencer_partidas_en_camara")
        self.assertEqual([pasos[o] for o in (20, 25, 35, 40)], ["vencer_partidas_en_camara", "reasignar_camara", "cerrar_rescisiones", "pre_reservar_suministros"])

    def test_regla_el_aviso_lleva_a_la_pestana_de_camara_para_el_agronomo_y_el_gerente(self):
        """D-62 y `camara.md`: la campana lleva «partida por vencer» a la pestaña «Cámara» del invernadero (Agrónomo y Gerente); para otro rol, nada. Una consulta para toda la lista."""
        from core.tests.fabricas import crear_gerente
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        p = partida(self.lote, 40, fecha_limite=HOY + timedelta(days=2))
        self.correr()
        alerta = self.avisos_de(p).get()
        url = reverse("maestros:invernadero", args=[self.e.invernadero.pk]) + "?pestana=camara"
        with CaptureQueriesContext(connection) as consultas:
            enlaces = camara.enlaces_de_alertas_de_camara(self.e.agronomo, [alerta])
        self.assertEqual(enlaces[alerta.pk].url, url)
        self.assertIn(p.codigo, enlaces[alerta.pk].detalle)
        self.assertLessEqual(len(consultas), 2)
        self.assertEqual(camara.enlaces_de_alertas_de_camara(crear_gerente(), [alerta])[alerta.pk].url, url)
        self.assertEqual(camara.enlaces_de_alertas_de_camara(self.e.vendedor, [alerta]), {})
        self.assertEqual(camara.enlaces_de_alertas_de_camara(self.e.agronomo, []), {})


class EntregasTests(Base):
    """COM-05a1: la postcondición d y la extensión 3a de PROD-VNC-CAM: quitar las líneas recortadas de su entrega «a realizar» y cancelar la que queda vacía."""

    def entrega_con(self, *reservas, detalle_=None):
        from comercial.tests.fabricas import entrega, transportista_con_vehiculo

        transportista = transportista_con_vehiculo(self.e.invernadero, "800")
        return transportista, entrega(detalle_.compra_venta, list(reservas), transportista=transportista)

    def test_post_d_3a_la_entrega_que_queda_vacia_se_cancela_y_se_avisa_al_transportista(self):
        """3a: la reserva recortada a cero deja la línea en 0; la entrega «a realizar» vacía se cancela con el motivo «Se venció en cámara el producto reservado.», se avisa al transportista y la auditoría la nombra."""
        p = self.vencida(30)
        d = self.venta(30)
        r = reserva(d, [(p, 30)])
        transportista, e = self.entrega_con(r, detalle_=d)
        self.sin_stock_de_lote()
        self.correr()
        e.refresh_from_db()
        self.assertEqual((e.estado_orden, e.motivo_cancelacion), ("cancelada", "Se venció en cámara el producto reservado."))
        self.assertEqual(e.lineas.count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=transportista, titulo=f"Se canceló la entrega {e.codigo}").count(), 1)
        datos = RegistroAuditoria.objects.get(accion="vencimiento_partida").detalle["datos"]
        self.assertEqual(datos["entregas_canceladas"], [e.codigo])
        verificar_invariantes_de_reservas()

    def test_post_d_3a_la_entrega_que_conserva_otra_reserva_no_se_cancela(self):
        """3a: si la entrega conserva producto de otra partida vigente, sigue «a realizar» (solo se recortó una parte) y su peso baja a lo que queda."""
        from decimal import Decimal

        from comercial.servicios import entregas

        vencida, vigente = self.vencida(30), self.vigente(20)
        d = self.venta(50)
        transportista, e = self.entrega_con(reserva(d, [(vencida, 30)]), reserva(d, [(vigente, 20)]), detalle_=d)
        self.sin_stock_de_lote()
        self.correr()
        e.refresh_from_db()
        self.assertEqual(e.estado_orden, "a_realizar")
        self.assertEqual(entregas.peso_de_entregas([e.pk])[e.pk], Decimal("3.00"))


class ProdVncCam3bTests(Base):
    """PROD-VNC-CAM, extensión 3b (COM-06a; `rutas.md`, «PROD-VNC-CAM 3b»): una partida vencida con producto en una entrega **en curso** no se vence ese día."""

    def entrega_con(self, p, *, en_ruta):
        """Una entrega de hoy con 30 plantas de la partida ``p``, de un transportista con la ruta iniciada (o sin iniciar)."""
        t = transportista_con_vehiculo(self.e.invernadero)
        venta = compra_venta(self.e, dias=0)
        det = detalle(venta, self.e.variedad, 30)
        e = entrega(venta, [reserva(det, [(p, 30)])], transportista=t, fecha=HOY)
        if en_ruta:
            iniciar_ruta_de(t)
        return t, e

    def test_ext_3b_con_producto_en_una_entrega_en_curso_no_se_vence_y_se_alerta_al_gerente(self):
        """Extensión 3b: la partida vencida sigue «disponible» con su stock; se deja para la próxima ejecución y se asegura la alerta de estado `comercial_partida_en_entrega_en_curso` (Gerente, crítica, clave `partida:<id>`) con su `AlertaComercial(partida=…)`."""
        p = self.vencida(40)
        _, e = self.entrega_con(p, en_ruta=True)
        resumen = self.correr()
        p.refresh_from_db()
        self.assertEqual((p.estado_stock_cosechado, p.cantidad_disponible_cosechado), ("disponible", 40))
        self.assertEqual(resumen.procesados, 0)
        alerta = Alerta.objects.get(tipo_alerta=camara.TIPO_EN_ENTREGA_EN_CURSO, clave_estado=f"partida:{p.pk}")
        self.assertEqual((alerta.para_gerente, alerta.nivel_severidad, alerta.estado_alerta), (True, Alerta.Severidad.CRITICA, "activa"))
        self.assertIn(p.codigo, alerta.descripcion_alerta)
        self.assertIn(e.codigo, alerta.descripcion_alerta)
        self.assertEqual(AlertaComercial.objects.get(alerta=alerta).partida_id, p.pk)
        self.assertFalse(Merma.objects.filter(causa="vencimiento_en_camara").exists())
        self.assertEqual(ReservaStock.objects.get(lineas__partida=p).estado_reserva, "lista_para_entrega")
        verificar_invariantes_de_reservas()

    def test_ext_3b_la_alerta_no_se_repite_entre_ejecuciones(self):
        """La alerta de estado es una por partida: una segunda ejecución con la entrega todavía en curso no crea otra."""
        p = self.vencida(40)
        self.entrega_con(p, en_ruta=True)
        self.correr()
        self.correr()
        self.assertEqual(Alerta.objects.filter(tipo_alerta=camara.TIPO_EN_ENTREGA_EN_CURSO).count(), 1)

    def test_ext_3b_cuando_la_entrega_deja_de_estar_en_curso_la_partida_se_vence_y_la_alerta_se_resuelve(self):
        """La alerta se resuelve cuando la partida se vence: con la entrega ya fuera de la ruta (intento fallido, a mañana y sin transportista) la ejecución siguiente aplica la 3a y resuelve la alerta de 3b."""
        from comercial.servicios import rutas

        p = self.vencida(40)
        t, e = self.entrega_con(p, en_ruta=True)
        self.correr()
        rutas.registrar_intento_fallido(t, e.pk, "cliente_ausente", "")
        self.correr()
        p.refresh_from_db()
        self.assertEqual(p.estado_stock_cosechado, "vencido")
        alerta = Alerta.objects.get(tipo_alerta=camara.TIPO_EN_ENTREGA_EN_CURSO)
        self.assertEqual(alerta.estado_alerta, "resuelta")

    def test_ext_3b_una_entrega_asignada_pero_con_la_ruta_sin_iniciar_no_esta_en_curso_y_se_aplica_la_3a(self):
        """«En curso» es con la ruta iniciada: una entrega «a realizar» de un transportista sin ruta no frena el vencimiento (3a: se recorta la reserva y la entrega vacía se cancela)."""
        p = self.vencida(40)
        _, e = self.entrega_con(p, en_ruta=False)
        self.correr()
        p.refresh_from_db()
        self.assertEqual(p.estado_stock_cosechado, "vencido")
        self.assertFalse(Alerta.objects.filter(tipo_alerta=camara.TIPO_EN_ENTREGA_EN_CURSO).exists())
        self.assertEqual(Entrega.objects.get(pk=e.pk).estado_orden, "cancelada")

    def test_ext_3b_una_entrega_en_curso_de_otra_partida_no_frena_a_esta(self):
        """Solo frena el producto de la misma partida: otra partida vencida sin entregas en curso se vence igual."""
        con = self.vencida(40)
        sin = self.vencida(10)
        self.entrega_con(con, en_ruta=True)
        self.correr()
        con.refresh_from_db()
        sin.refresh_from_db()
        self.assertEqual((con.estado_stock_cosechado, sin.estado_stock_cosechado), ("disponible", "vencido"))

    def test_ext_3b_el_enlace_de_la_alerta_lleva_a_la_pestana_camara_para_el_gerente(self):
        """D-62: la alerta usa el enlace de la cámara (pestaña «Cámara» del invernadero) para el Gerente."""
        from core.tests.fabricas import crear_gerente

        p = self.vencida(40)
        self.entrega_con(p, en_ruta=True)
        self.correr()
        gerente = crear_gerente()
        alerta = Alerta.objects.get(tipo_alerta=camara.TIPO_EN_ENTREGA_EN_CURSO)
        enlaces = camara.enlaces_de_alertas_de_camara(gerente, [alerta])
        self.assertIn("?pestana=camara", enlaces[alerta.pk].url)
