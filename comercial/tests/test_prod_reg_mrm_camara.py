# Pruebas de PROD-REG-MRM para una partida en cámara (COM-04b; docs/casos_de_uso/produccion/merma.md, «Cómo se aplica en la ronda «Comercial 1»»: extensiones 4a, 4a.4a,
# 4a.4b, 4b, 10c y 10d; postcondiciones f, g, h y j). Una prueba por postcondición y extensión. Las que escriben verifican al final los invariantes de reservas. La concurrencia
# está en `test_camara_concurrencia.py`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa antes de implementar), en `comercial/servicios/merma_camara.py`:
#   - `DatosDeMermaEnCamara(partida_id, cantidad, causa, descripcion="", visto_disponible=None)` (dataclass). `cantidad` puede llegar como texto (del formulario).
#   - `invernaderos_con_merma_en_camara(actor)`: los invernaderos activos del actor (Capataz asignado o Agrónomo a cargo) con alguna partida «disponible» (extensión 4b: aunque no
#     tengan lotes activos). Cualquier otro rol: lista vacía.
#   - `partidas_con_merma_posible(actor, invernadero_id)`: las partidas «disponibles» del invernadero, por fecha límite, como `FilaDePartidaConMerma(partida_id, codigo, variedad,
#     lote_codigo, fecha_limite, disponible, reservado, libre)`. `PermissionDenied` si el invernadero no es del actor.
#   - `causas_de_camara()`: `[("dano_en_camara", "Daño en cámara")]` (decisión del estudiante: el núcleo de `produccion` solo admite esa y la de vencimiento, que es de InfoPonia).
#   - `resumen_de_merma_en_camara(actor, datos) -> ResumenDeMermaEnCamara(partida, variedad, cantidad, causa, descripcion, disponible_resultante, libre, recortes)`: valida sin
#     bloquear ni escribir; `recortes` = `[(código del contrato, plantas que pierde)]` en el orden del recorte (vacío si la pérdida cabe en el stock libre).
#   - `registrar_merma_en_camara(actor, datos) -> ResultadoDeMermaEnCamara(partida, merma, movimiento, recortes, agotada)`.
#   - Errores (`ValidationError` por campo): `partida_obligatoria`, `partida_no_disponible`, `cantidad_invalida` (4a.4a, el mensaje trae la disponible), `causa_obligatoria` y
#     `causa_invalida` (4a.4b), `descripcion_larga` (más de 300), `cambio_simultaneo` (10d, en el campo `cantidad`, con la disponible vigente). Sin permiso, `PermissionDenied`.
#   - Se baja primero el stock físico y después se vuelve a cubrir (decisión del plan), con la acción de auditoría `registro_merma`.

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from comercial.models import DetalleReserva, DetalleVenta, EnlaceCliente, ReservaStock
from comercial.servicios import camara, merma_camara
from comercial.servicios.merma_camara import DatosDeMermaEnCamara
from comercial.tests.fabricas import (
    compra_venta,
    detalle,
    detalle_suministro,
    escenario_comercial,
    partida,
    reserva,
    reserva_de_periodo,
    segundo_invernadero,
    suministro,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.tests.fabricas import codigos_de, error_de
from produccion.models import AlertaDeMerma, Cosecha, Merma, MovimientoStock
from produccion.tests.fabricas import lote_maduro

HOY = timezone.localdate()


class Base(ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, Agrónomo y Capataz y un lote de 300 plantas en Maduración."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 300)

    def venta(self, cantidad=30, dias=3, estado_detalle="abierto", estado_venta="abierta"):
        """Un detalle de venta (con envío) de la variedad del escenario."""
        return detalle(compra_venta(self.e, dias=dias, estado=estado_venta), self.e.variedad, cantidad, estado=estado_detalle)

    def sin_stock_de_lote(self):
        """Agota el stock libre del lote del escenario con una reserva de otro contrato (así `asignar` no encuentra de dónde cubrir)."""
        reserva(self.venta(300, dias=40), [(self.lote, 300)])

    def datos(self, p, cantidad, causa="dano_en_camara", descripcion="", visto=None):
        """Los `DatosDeMermaEnCamara` de una pérdida de `cantidad` plantas de `p`."""
        return DatosDeMermaEnCamara(p.pk, cantidad, causa, descripcion, visto)

    def registrar(self, p, cantidad, actor=None, **extra):
        """`registrar_merma_en_camara` por el Agrónomo (o `actor`)."""
        return merma_camara.registrar_merma_en_camara(actor or self.e.agronomo, self.datos(p, cantidad, **extra))


class ProdRegMrmCamaraServicioTests(Base):
    """PROD-REG-MRM sobre una partida en cámara."""

    # ---- quién, dónde y qué se ofrece (4a, 4b) ----

    def test_regla_quien_el_capataz_asignado_y_el_agronomo_a_cargo_si_otros_no(self):
        """Precondición b: el Capataz en sus invernaderos y el Agrónomo en los suyos; el Gerente, el Vendedor y un Capataz ajeno, no."""
        p = partida(self.lote, 20)
        otro = segundo_invernadero(self.e)
        for actor in (self.e.capataz, self.e.agronomo):
            self.assertEqual([f.partida_id for f in merma_camara.partidas_con_merma_posible(actor, self.e.invernadero.pk)], [p.pk])
        for actor in (crear_gerente(), self.e.vendedor, otro.capataz):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                merma_camara.partidas_con_merma_posible(actor, self.e.invernadero.pk)
            with self.subTest(actor=actor, registrar=True), self.assertRaises(PermissionDenied):
                self.registrar(p, 1, actor=actor)

    def test_ext_4a_lista_las_partidas_disponibles_con_su_stock_libre(self):
        """Extensión 4a: las partidas disponibles del invernadero con variedad, lote de origen, fecha límite, cantidad disponible y stock libre; las agotadas y vencidas no."""
        p = partida(self.lote, 50, fecha_limite=HOY + timedelta(days=9))
        reserva(self.venta(20), [(p, 20)])
        partida(self.lote, 0, estado="agotado")
        partida(self.lote, 0, estado="vencido")
        (fila,) = merma_camara.partidas_con_merma_posible(self.e.agronomo, self.e.invernadero.pk)
        self.assertEqual((fila.codigo, fila.lote_codigo, fila.disponible, fila.reservado, fila.libre), (p.codigo, self.lote.codigo, 50, 20, 30))
        self.assertEqual(fila.variedad, str(self.e.variedad))

    def test_ext_4b_un_invernadero_sin_lotes_activos_pero_con_partidas_ofrece_la_merma_en_camara(self):
        """Extensión 4b: se ofrece el invernadero que tiene partidas disponibles aunque no tenga lotes activos; el que no tiene ninguna, no."""
        partida(self.lote, 20)
        otro = segundo_invernadero(self.e)
        from produccion.models import Lote

        Lote.objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)  # sin plantas, finalizado: sin lotes activos
        ofrecidos = [i.pk for i in merma_camara.invernaderos_con_merma_en_camara(self.e.agronomo)]
        self.assertEqual(ofrecidos, [self.e.invernadero.pk])
        self.assertNotIn(otro.invernadero.pk, ofrecidos)
        self.assertEqual(merma_camara.invernaderos_con_merma_en_camara(self.e.vendedor), [])

    def test_ext_4a_4b_solo_se_ofrece_danio_en_camara(self):
        """Extensión 4a.4b (decisión del estudiante): la causa es «Daño en cámara»; «Vencimiento en cámara» es de InfoPonia y «Descarte por selección» no se ofrece."""
        self.assertEqual(merma_camara.causas_de_camara(), [("dano_en_camara", "Daño en cámara")])
        p = partida(self.lote, 20)
        for causa in ("vencimiento_en_camara", "descarte_por_seleccion", "plaga"):
            with self.subTest(causa=causa):
                error = error_de(lambda: self.registrar(p, 1, causa=causa))
                self.assertEqual(codigos_de(error, "causa"), ["causa_invalida"])

    # ---- validaciones ----

    def test_ext_4a_4a_la_cantidad_tiene_que_ser_un_entero_entre_1_y_la_disponible(self):
        """Extensión 4a.4a: una cantidad que no es un entero entre 1 y la disponible da `cantidad_invalida` con la disponible en el mensaje; no se escribe nada."""
        p = partida(self.lote, 20)
        for cantidad in (0, -1, "x", "1.5", None, 21):
            with self.subTest(cantidad=cantidad):
                error = error_de(lambda: self.registrar(p, cantidad))
                self.assertEqual(codigos_de(error, "cantidad"), ["cantidad_invalida"])
        self.assertIn("20", str(error_de(lambda: self.registrar(p, 21)).error_dict["cantidad"][0].message))
        self.assertEqual(Merma.objects.count(), 0)

    def test_ext_4a_4b_la_causa_es_obligatoria(self):
        """Extensión 4a.4b: sin causa, `causa_obligatoria`."""
        error = error_de(lambda: self.registrar(partida(self.lote, 20), 5, causa=""))
        self.assertEqual(codigos_de(error, "causa"), ["causa_obligatoria"])

    def test_regla_la_descripcion_pasa_de_300_caracteres(self):
        """Regla del núcleo y del extracto: la descripción es opcional y de hasta 300 caracteres (`descripcion_larga`)."""
        p = partida(self.lote, 20)
        self.assertEqual(codigos_de(error_de(lambda: self.registrar(p, 5, descripcion="x" * 301)), "descripcion"), ["descripcion_larga"])
        self.registrar(p, 5, descripcion="x" * 300)

    def test_regla_una_partida_vencida_o_ajena_no_se_puede_mermar(self):
        """Paso 4a: solo una partida «disponible» del invernadero; una vencida da `partida_no_disponible` y sin partida, `partida_obligatoria`."""
        vencida = partida(self.lote, 0, estado="vencido")
        self.assertEqual(codigos_de(error_de(lambda: self.registrar(vencida, 1)), "partida"), ["partida_no_disponible"])
        datos = DatosDeMermaEnCamara(None, 1, "dano_en_camara")
        error = error_de(lambda: merma_camara.registrar_merma_en_camara(self.e.agronomo, datos))
        self.assertEqual(codigos_de(error, "partida"), ["partida_obligatoria"])

    # ---- postcondiciones f, g, h y j ----

    def test_post_f_registra_una_merma_sin_etapa_con_el_lote_de_origen_y_el_responsable(self):
        """Postcondición f: `Merma` del lote de origen, SIN etapa, con fecha y hora actuales, la causa, la descripción y quien la registró como responsable."""
        p = partida(self.lote, 20)
        resultado = self.registrar(p, 8, actor=self.e.capataz, descripcion="Se golpeó en el traslado")
        merma = Merma.objects.get(pk=resultado.merma.pk)
        self.assertEqual((merma.lote_id, merma.etapa_id, merma.cant_merma, merma.causa), (self.lote.pk, None, 8, "dano_en_camara"))
        self.assertEqual((merma.responsable_id, merma.fecha_bitacora, merma.invernadero_id), (self.e.capataz.pk, HOY, self.e.invernadero.pk))
        self.assertIn("Se golpeó en el traslado", merma.descripcion_evento)

    def test_post_g_baja_la_disponible_y_la_deja_agotada_si_llega_a_cero(self):
        """Postcondición g y regla 30 de 8.6: baja la cantidad disponible; con 0 la partida queda «agotada» (y `agotada` en el resultado)."""
        p = partida(self.lote, 20)
        self.assertFalse(self.registrar(p, 5).agotada)
        p.refresh_from_db()
        self.assertEqual((p.cantidad_disponible_cosechado, p.estado_stock_cosechado), (15, "disponible"))
        self.assertTrue(self.registrar(p, 15).agotada)
        p.refresh_from_db()
        self.assertEqual((p.cantidad_disponible_cosechado, p.estado_stock_cosechado), (0, "agotado"))

    def test_post_h_crea_el_movimiento_merma_en_camara_con_el_costo_de_la_partida(self):
        """Postcondición h: `MovimientoStock` `merma_en_camara` sobre la partida, con la merma como origen y el costo unitario de la partida."""
        p = partida(self.lote, 20, costo="2.5000")
        resultado = self.registrar(p, 4)
        m = MovimientoStock.objects.get(partida=p, tipo_movimiento="merma_en_camara")
        self.assertEqual((m.pk, m.cantidad, str(m.costo_unitario), m.origen_id), (resultado.movimiento.pk, 4, "2.5000", resultado.merma.pk))

    def test_post_j_deja_un_registro_de_auditoria_registro_merma_del_actor(self):
        """Postcondición j (n del extracto): un registro `registro_merma` con quien actuó, la partida, la merma y el movimiento."""
        p = partida(self.lote, 20)
        resultado = self.registrar(p, 4)
        (registro,) = RegistroAuditoria.objects.filter(accion="registro_merma")
        self.assertEqual(registro.usuario_id, self.e.agronomo.pk)
        ids = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertIn(("produccion.stockcosechado", p.pk), ids)
        self.assertIn(("produccion.merma", resultado.merma.pk), ids)

    # ---- 10c: el recorte ----

    def test_ext_10c_dentro_del_stock_libre_no_recorta_ni_avisa(self):
        """Extensión 10c: si la pérdida cabe en el stock libre, no se toca ninguna reserva ni se genera la alerta de merma con producto reservado."""
        p = partida(self.lote, 50)
        d = self.venta(20)
        r = reserva(d, [(p, 20)])
        resultado = self.registrar(p, 30)
        self.assertEqual(resultado.recortes, [])
        self.assertEqual(DetalleReserva.objects.get(reserva=r).cantidad_reservada, 20)
        self.assertFalse(AlertaDeMerma.objects.exists())
        self.assertFalse(Notificacion.objects.filter(destinatario_id=self.e.vendedor.pk).exists())

    def test_ext_10c_recorta_en_el_orden_de_la_regla_y_avisa(self):
        """Extensión 10c y regla 6 de 8.9: la pérdida supera el stock libre: se recorta la entrega más lejana primero; alerta `comercial_merma_camara_reservada` al Agrónomo (enlazada a la merma) y notificación al Vendedor."""
        p = partida(self.lote, 40)
        cerca, lejos = self.venta(20, dias=2), self.venta(20, dias=9)
        r_cerca, r_lejos = reserva(cerca, [(p, 20)]), reserva(lejos, [(p, 20)])
        resultado = self.registrar(p, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r_lejos).cantidad_reservada, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r_cerca).cantidad_reservada, 20)
        self.assertEqual(resultado.recortes, [(lejos.compra_venta.codigo, 10)])
        enlace = AlertaDeMerma.objects.get(merma=resultado.merma)
        self.assertEqual((enlace.alerta.tipo_alerta, enlace.alerta.agronomo_id), (camara.TIPO_MERMA_RESERVADA, self.e.agronomo.pk))
        self.assertIn(lejos.compra_venta.codigo, Notificacion.objects.get(destinatario_id=self.e.vendedor.pk).detalle)
        verificar_invariantes_de_reservas()

    def test_ext_10c_la_compra_venta_pierde_antes_que_el_suministro(self):
        """Regla 6 de 8.9: primero se recortan las compra-ventas y después los suministros, aunque el suministro entregue más lejos."""
        p = partida(self.lote, 40)
        d_cv = self.venta(20, dias=2)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=20, primera_en_dias=10)
        r_cv, r_sum = reserva(d_cv, [(p, 20)]), reserva_de_periodo(d_sum, HOY + timedelta(days=10), [(p, 20)])
        self.registrar(p, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r_cv).cantidad_reservada, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r_sum).cantidad_reservada, 20)

    def test_ext_10c_una_reserva_con_lote_y_partida_sigue_viva_con_la_linea_de_camara_en_cero(self):
        """D-64 punto 7: una reserva con líneas de lote y de cámara sigue viva si la de cámara se recorta a 0 (la línea se conserva)."""
        p = partida(self.lote, 10)
        r = reserva(self.venta(20), [(self.lote, 10), (p, 10)])
        self.registrar(p, 10)
        self.assertEqual(DetalleReserva.objects.get(reserva=r, partida=p).cantidad_reservada, 0)
        self.assertEqual(ReservaStock.objects.get(pk=r.pk).estado_reserva, "activa")

    def test_ext_10c_el_detalle_afectado_se_vuelve_a_cubrir_con_otra_partida(self):
        """Extensión 10c, paso 3: lo recortado de un detalle «abierto» se vuelve a cubrir (`asignar`) con otra partida."""
        p, otra = partida(self.lote, 30), partida(self.lote, 100)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        resultado = self.registrar(p, 30)
        self.assertTrue(resultado.agotada)
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida=otra, reserva__detalle_venta=d)), 30)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "abierto")
        verificar_invariantes_de_reservas()

    def test_ext_10c_el_detalle_afectado_se_vuelve_a_cubrir_con_un_lote_y_programa_una_cosecha(self):
        """Extensión 10c: si no hay otra partida pero sí un lote en Maduración, `asignar` reserva el lote y programa una cosecha nueva."""
        p = partida(self.lote, 30)
        d = self.venta(30)
        reserva(d, [(p, 30)])
        antes = Cosecha.objects.count()
        self.registrar(p, 30)
        self.assertEqual(Cosecha.objects.count(), antes + 1)
        self.assertTrue(DetalleReserva.objects.filter(lote=self.lote, reserva__detalle_venta=d).exists())

    def test_ext_10c_sin_stock_el_detalle_abierto_pasa_a_pendiente_de_decision(self):
        """Extensión 10c y regla 16 de 8.6: lo que no se puede volver a cubrir sigue el camino de faltante (el enlace del cliente es de COM-04c)."""
        p = partida(self.lote, 30)
        self.sin_stock_de_lote()
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.registrar(p, 30)
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.compra_venta.estado_venta), ("pendiente_decision", "pendiente_decision"))

    def test_ext_10c_el_cliente_con_correo_recibe_el_enlace_y_el_confirmado_uno_nuevo(self):
        """Extensión 10c (COM-04c): el detalle que pasa a pendiente deja un enlace vigente; un confirmado que vuelve a pendiente (D-64 punto 13) también recibe uno nuevo, con el viejo reemplazado."""
        p = partida(self.lote, 30)
        self.sin_stock_de_lote()
        d = self.venta(30)
        reserva(d, [(p, 30)])
        self.registrar(p, 30)
        self.assertEqual(EnlaceCliente.objects.filter(compra_venta=d.compra_venta, estado="vigente").count(), 1)
        registro = RegistroAuditoria.objects.get(accion="registro_merma")
        self.assertIn("comercial.enlacecliente", {a["modelo"] for a in registro.afectados})

    def test_ext_10c_un_detalle_confirmado_sin_stock_vuelve_a_pendiente_sin_cantidad_aceptada(self):
        """D-64 punto 13: un detalle «confirmado» que pierde producto y no se cubre vuelve a «pendiente de decisión» con `cant_entregada_venta` vacía."""
        p = partida(self.lote, 30)
        self.sin_stock_de_lote()
        d = self.venta(50, estado_detalle="confirmado")
        DetalleVenta.objects.filter(pk=d.pk).update(cant_entregada_venta=30)
        reserva(d, [(p, 30)])
        self.registrar(p, 30)
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.cant_entregada_venta), ("pendiente_decision", None))

    def test_ext_10c_un_detalle_confirmado_se_cubre_con_la_cantidad_aceptada_si_hay_stock(self):
        """D-64 punto 13: con stock, un detalle «confirmado» se cubre por lo perdido tomando `cant_entregada_venta` como cantidad pedida y sigue «confirmado»."""
        p, otra = partida(self.lote, 30), partida(self.lote, 100)
        d = self.venta(50, estado_detalle="confirmado")
        DetalleVenta.objects.filter(pk=d.pk).update(cant_entregada_venta=30)
        reserva(d, [(p, 30)])
        self.registrar(p, 30)
        d.refresh_from_db()
        self.assertEqual(d.estado_detalle_venta, "confirmado")
        self.assertEqual(sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida=otra, reserva__detalle_venta=d)), 30)

    def test_ext_10c_un_detalle_pendiente_va_directo_al_faltante_sin_volver_a_cubrir(self):
        """Extensión 10c: un detalle «pendiente de decisión» no se vuelve a cubrir (precondición b de PROD-ASG-STK): suma al faltante y su fecha de pendiente queda en hoy."""
        p, otra = partida(self.lote, 30), partida(self.lote, 100)
        d = self.venta(30, estado_detalle="pendiente_decision", estado_venta="pendiente_decision")
        DetalleVenta.objects.filter(pk=d.pk).update(fecha_pendiente_decision=HOY - timedelta(days=2))
        reserva(d, [(p, 10)])
        self.registrar(p, 30)
        d.refresh_from_db()
        self.assertEqual((d.estado_detalle_venta, d.fecha_pendiente_decision), ("pendiente_decision", HOY))
        self.assertFalse(DetalleReserva.objects.filter(partida=otra).exists())

    def test_ext_10c_un_periodo_de_suministro_se_vuelve_a_cubrir(self):
        """Extensión 10c: lo recortado de un período se vuelve a cubrir con otra partida; el suministro no cambia de estado."""
        p, otra = partida(self.lote, 30), partida(self.lote, 100)
        d_sum = detalle_suministro(suministro(self.e), self.e.variedad, cantidad=30, primera_en_dias=3)
        reserva_de_periodo(d_sum, HOY + timedelta(days=3), [(p, 30)])
        self.registrar(p, 30)
        self.assertEqual(
            sum(l.cantidad_reservada for l in DetalleReserva.objects.filter(partida=otra, reserva__detalle_suministro=d_sum)), 30
        )

    # ---- 10d y el aviso «partida por vencer» ----

    def test_ext_10d_si_la_disponible_cambio_desde_el_resumen_rechaza_con_la_vigente(self):
        """Extensión 10d: la disponible que la persona vio ya no es la vigente: `cambio_simultaneo` con la disponible actual; no se escribe nada."""
        p = partida(self.lote, 20)
        error = error_de(lambda: self.registrar(p, 5, visto=25))
        self.assertEqual(codigos_de(error, "cantidad"), ["cambio_simultaneo"])
        self.assertIn("20", str(error.error_dict["cantidad"][0].message))
        self.assertEqual(Merma.objects.count(), 0)
        self.registrar(p, 5, visto=20)

    def test_regla_la_partida_que_se_agota_resuelve_la_alerta_partida_por_vencer(self):
        """`camara.md`, «Resolución de partida por vencer»: una merma que agota la partida resuelve su alerta «partida por vencer»."""
        p = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=2))
        camara.vencer_partidas_en_camara(HOY)
        alerta = camara_alerta(p)
        self.assertEqual(alerta.estado_alerta, "activa")
        self.registrar(p, 20)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")

    def test_regla_una_merma_que_no_agota_deja_activa_la_alerta_partida_por_vencer(self):
        """Control: si la partida conserva producto, el aviso sigue activo."""
        p = partida(self.lote, 20, fecha_limite=HOY + timedelta(days=2))
        camara.vencer_partidas_en_camara(HOY)
        self.registrar(p, 5)
        self.assertEqual(camara_alerta(p).estado_alerta, "activa")

    # ---- el resumen (paso 9) ----

    def test_regla_el_resumen_dice_que_contratos_pierden_producto_y_no_escribe(self):
        """Paso 9: el resumen muestra la partida, la cantidad, la causa, la disponible que queda y, si supera el stock libre, qué contratos pierden producto y cuánto (en el orden del recorte); no escribe ni bloquea."""
        p = partida(self.lote, 40)
        lejos = self.venta(20, dias=9)
        reserva(self.venta(20, dias=2), [(p, 20)])
        reserva(lejos, [(p, 20)])
        resumen = merma_camara.resumen_de_merma_en_camara(self.e.agronomo, self.datos(p, 10))
        self.assertEqual(
            (resumen.partida.pk, resumen.cantidad, resumen.disponible_resultante, resumen.libre, resumen.recortes),
            (p.pk, 10, 30, 0, [(lejos.compra_venta.codigo, 10)]),
        )
        self.assertEqual((Merma.objects.count(), DetalleReserva.objects.filter(cantidad_reservada=10).count()), (0, 0))
        sin_recorte = merma_camara.resumen_de_merma_en_camara(self.e.agronomo, self.datos(partida(self.lote, 20), 5))
        self.assertEqual(sin_recorte.recortes, [])


def camara_alerta(p):
    """La alerta «partida por vencer» de la partida."""
    from maestros.models import Alerta

    return Alerta.objects.get(tipo_alerta=camara.TIPO_POR_VENCER, clave_estado=f"partida:{p.pk}")


class EntregasTests(Base):
    """COM-05a1: la extensión 10c de PROD-REG-MRM: quitar las líneas recortadas de su entrega «a realizar» y cancelar la que queda vacía."""

    def test_ext_10c_la_entrega_que_queda_vacia_se_cancela_con_el_motivo_de_la_perdida(self):
        """10c: la merma que agota la partida reservada deja la línea en 0; la entrega vacía se cancela («Se perdió en cámara el producto reservado.»), se avisa al transportista y la auditoría la nombra."""
        from comercial.tests.fabricas import entrega, transportista_con_vehiculo
        from core.models import Notificacion, RegistroAuditoria

        p = partida(self.lote, 30)
        d = self.venta(30)
        r = reserva(d, [(p, 30)])
        transportista = transportista_con_vehiculo(self.e.invernadero, "800")
        e = entrega(d.compra_venta, [r], transportista=transportista)
        self.sin_stock_de_lote()
        self.registrar(p, 30)
        e.refresh_from_db()
        self.assertEqual((e.estado_orden, e.motivo_cancelacion), ("cancelada", "Se perdió en cámara el producto reservado."))
        self.assertEqual(Notificacion.objects.filter(destinatario=transportista, titulo=f"Se canceló la entrega {e.codigo}").count(), 1)
        registros = [r_ for r_ in RegistroAuditoria.objects.filter(accion="registro_merma") if "entregas_canceladas" in r_.detalle.get("datos", {})]
        self.assertEqual([r_.detalle["datos"]["entregas_canceladas"] for r_ in registros], [[e.codigo]])

    def test_ext_10c_una_perdida_que_cabe_en_el_stock_libre_no_toca_la_entrega(self):
        """Sin recorte (10c no aplica) no se quita ninguna línea ni se cancela nada."""
        from comercial.tests.fabricas import entrega

        p = partida(self.lote, 50)
        d = self.venta(30)
        r = reserva(d, [(p, 30)])
        e = entrega(d.compra_venta, [r])
        self.registrar(p, 10)
        e.refresh_from_db()
        self.assertEqual(e.estado_orden, "a_realizar")
