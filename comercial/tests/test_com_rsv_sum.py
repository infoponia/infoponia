# Pruebas de COM-RSV-SUM · Resolver Suministro por Incumplimientos (COM-07b; `comercial/servicios/resoluciones.py`; docs/casos_de_uso/comercial/resolucion.md, «Pruebas»). El actor es InfoPonia:
# una prueba por postcondición (a a m, sin h: el asiento de la multa está fuera de la ronda, D-57, y acá se prueba que NO se crea), por extensión (*a, 1a, 2a, 2b, 3a a 3d, 5a, 6a, 6b, 7a, 8a, 9a) y por
# regla («Qué se deshace», «Qué no cambia», «Producto ya cosechado», «Líneas de cámara», «Períodos sin reserva»). Cada prueba arma sus datos con las fábricas, directo en la base.
# Nombres: postcondiciones `test_post_<letra>_…`, extensiones `test_ext_<numero>_…`, disparadores `test_disparador_<numero>_…` (resolucion.md, «Para nombrar las pruebas»).
# Fuente: docs/casos_de_uso/comercial/resolucion.md; D-63 (punto 2), D-64 (puntos 2, 3, 9 y 12), D-66 (puntos 11 y 12), D-69 (puntos 1, 5, 7, 13, 14 y 15), D-36, D-42, D-27.

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from comercial.models import AlertaComercial, DetalleReserva, DetalleSuministro, Entrega, ReservaStock, SolicitudRevision, Suministro
from comercial.servicios import camara, resoluciones
from comercial.tests.fabricas import (
    alerta_de_periodo,
    detalle_suministro,
    entrega,
    escenario_comercial,
    marcar_concretada,
    partida_cosechada,
    queja,
    queja_aceptada,
    reserva,
    reserva_de_periodo,
    reserva_lista,
    segundo_invernadero,
    suministro,
    transportista_con_vehiculo,
    verificar_invariantes_de_entregas,
    verificar_invariantes_de_reservas,
    verificar_invariantes_de_resolucion,
    verificar_invariantes_de_solicitudes,
)
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, ejercicio_abierto, verificar_invariantes_contables
from core.models import Notificacion, RegistroAuditoria, Usuario
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Alerta
from produccion.models import Bitacora, Cosecha, MovimientoStock, StockCosechado
from produccion.tests.fabricas import lote_maduro, reservar

HOY = timezone.localdate()
D = Decimal
MOTIVO = "Resolución del suministro {codigo} por incumplimientos."


class BaseDeResolucion(PlanDeCuentasMixin, ConDatosDeInventario, TestCase):
    """Un invernadero con su Vendedor, su Agrónomo y su Capataz, un lote con 5000 plantas, un Transportista y un Gerente. `armar()` deja un suministro «vigente» con más incumplimientos que los tolerados."""

    @classmethod
    def setUpTestData(cls):
        cls.e = escenario_comercial()
        cls.lote = lote_maduro(cls.e, 5000)
        cls.gerente = crear_gerente()
        cls.t = transportista_con_vehiculo(cls.e.invernadero, "800")

    def setUp(self):
        self.addCleanup(verificar_invariantes_de_reservas)
        self.addCleanup(verificar_invariantes_de_entregas)
        self.addCleanup(verificar_invariantes_de_solicitudes)
        self.addCleanup(verificar_invariantes_de_resolucion)
        self.addCleanup(verificar_invariantes_contables)  # CON-04d: la resolución asienta la multa

    # ---- armado ----

    def incumplimientos(self, contrato, detalle, cuantos):
        """`cuantos` quejas aceptadas de otras tantas entregas concretadas (con sus reservas «entregada»), sin monto: el contador y sus solicitudes quedan iguales (invariante de COM-07a)."""
        quejas = []
        for i in range(cuantos):
            fecha = HOY - timedelta(days=40 - 7 * i)
            r = reserva_lista(None, self.lote, 5, fecha_entrega=fecha, detalle_suministro=detalle)
            concretada = marcar_concretada(entrega(contrato, [r], fecha=fecha), cantidades=[(5, 0, 0)])
            ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
            quejas.append(queja_aceptada(concretada, "otro", monto="0.00"))
        return quejas

    def reserva_cosechada(self, detalle, fecha, *, lote_cantidad=20, cosechada=None, camara_cantidad=10, costo="2.5000", dias_atras=2):
        """Una reserva «lista para entrega» del período `fecha`: una línea de lote ya cosechada (`cosechada` de las `lote_cantidad`, con su cosecha concretada, su bitácora y su salida por cosecha) y, si se
        pide, una línea de cámara de `camara_cantidad` plantas."""
        cosechada = lote_cantidad if cosechada is None else cosechada
        lineas = [(self.lote, lote_cantidad)] + ([(partida_cosechada(self.lote, camara_cantidad), camara_cantidad)] if camara_cantidad else [])
        r = reserva(None, lineas, fecha_entrega=fecha, detalle_suministro=detalle)
        Bitacora.objects.create(
            invernadero=self.lote.invernadero, lote=self.lote, etapa=self.lote.etapa, tipo_evento="cosecha", cosecha=r.cosecha, fecha_bitacora=HOY, hora_bitacora=timezone.localtime().time()
        )
        Cosecha.objects.filter(pk=r.cosecha_id).update(estado_orden="concretada", fecha_resolucion_orden=HOY, fecha_cosecha=HOY - timedelta(days=dias_atras))
        DetalleReserva.objects.filter(reserva=r, lote__isnull=False).update(cantidad_cosechada=cosechada)
        ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="lista_para_entrega")
        MovimientoStock.objects.create(origen_id=r.cosecha_id, lote=self.lote, tipo_movimiento="salida_por_cosecha", cantidad=cosechada, costo_unitario=D(costo))
        r.refresh_from_db()
        return r

    def armar(self, *, tolerados=3, multa="50000.00", con_envasado=True, con_transportista=True, con_entrega=True, con_reserva_activa=True, con_camara=True, en_curso=False, con_solicitudes=True):
        """El escenario del caso de uso: un suministro «vigente» con un solo detalle «vigente» (30 plantas cada 7 días) con `tolerados` + 1 incumplimientos (quejas aceptadas de entregas ya concretadas, con
        sus reservas «entregada»); el período más próximo tiene la entrega «a realizar» (con el Transportista y, si se pide, 5 envases reservados) sobre una reserva «lista para entrega» (20 plantas de lote
        ya cosechadas y 10 de cámara); el período siguiente, una reserva «activa» con su cosecha «a realizar». Devuelve un `SimpleNamespace`."""
        contrato = suministro(self.e, tolerados=tolerados, multa=multa)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=30, periodo=7, primera_en_dias=-40, minima=10)  # períodos: -40, -33, -26, -19, -12, -5, +2, +9, +16…
        quejas = self.incumplimientos(contrato, d, tolerados + 1) if con_solicitudes else []
        if not con_solicitudes:
            Suministro.objects.filter(pk=contrato.pk).update(cantidad_incumplimientos=tolerados + 1)
        x = SimpleNamespace(contrato=contrato, detalle=d, quejas=quejas, entrega=None, reserva_lista=None, reserva_activa=None, envases=None, transportista=self.t if con_transportista else None)
        if con_entrega:
            periodo = HOY - timedelta(days=5) if en_curso else HOY + timedelta(days=2)  # la entrega de un período pasado se programa para hoy (atrasada)
            x.reserva_lista = self.reserva_cosechada(d, periodo, camara_cantidad=10 if con_camara else 0)
            x.entrega = entrega(contrato, [x.reserva_lista], transportista=x.transportista)
            if con_envasado:
                x.envases = reservar(x.entrega, self.e.existencia_semilla, 5)
        if con_reserva_activa:
            x.reserva_activa = reserva_de_periodo(d, HOY + timedelta(days=9), [(self.lote, 30)])
        return x

    def resolver(self, x_o_id, hoy=None):
        """`resolver_suministro` con los callbacks de `on_commit` ejecutados (el correo y PROD-ASG-CAM). Devuelve el resultado."""
        pk = getattr(x_o_id, "contrato", x_o_id)
        pk = getattr(pk, "pk", pk)
        with self.captureOnCommitCallbacks(execute=True):
            return resoluciones.resolver_suministro(pk, hoy or HOY)

    def releer(self, modelo, pk):
        return modelo.objects.get(pk=pk)

    def avisos(self, cuenta, titulo=""):
        return list(Notificacion.objects.filter(destinatario=cuenta, titulo__startswith=titulo).order_by("pk"))

    def registros(self, accion):
        return list(RegistroAuditoria.objects.filter(accion=accion).order_by("pk"))


class ComRsvSumServicioTests(BaseDeResolucion):
    # ---- el escenario principal ----

    def test_flujo_principal_resuelve_el_contrato_y_deshace_lo_pendiente(self):
        """Escenario principal (las cifras del caso): el cuarto incumplimiento de un suministro con 3 tolerados y multa resuelve el contrato, cancela la cosecha y la entrega, libera las reservas y
        pasa a la cámara lo cosechado; lo ya entregado no cambia."""
        x = self.armar()
        resultado = self.resolver(x)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.fecha_resolucion_suministro, contrato.cantidad_incumplimientos), ("resuelto", HOY, 4))
        self.assertEqual(self.releer(DetalleSuministro, x.detalle.pk).estado_detalle_suministro, "resuelto")
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "cancelada")
        self.assertEqual(self.releer(Cosecha, x.reserva_activa.cosecha_id).estado_orden, "cancelada")
        self.assertEqual({self.releer(ReservaStock, r.pk).estado_reserva for r in (x.reserva_lista, x.reserva_activa)}, {"liberada"})
        self.assertEqual(resultado.suministro.pk, x.contrato.pk)
        self.assertEqual((len(resultado.cosechas), len(resultado.entregas), len(resultado.partidas), len(resultado.detalles)), (1, 1, 1, 1))
        self.assertIsNotNone(resultado.alerta)

    # ---- contrato ----

    def test_post_a_el_suministro_pasa_a_resuelto_con_la_fecha_y_la_solicitud_que_lo_provoco(self):
        """Postcondición a y D-69 punto 5: «resuelto» con la fecha actual, `solicitud_resolucion` = la solicitud aceptada con la fecha de resolución más reciente (a igual fecha, la de mayor id); los incumplimientos no cambian."""
        x = self.armar()
        self.resolver(x)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.fecha_resolucion_suministro), ("resuelto", HOY))
        self.assertEqual(contrato.solicitud_resolucion_id, x.quejas[-1].pk)
        self.assertEqual(contrato.cantidad_incumplimientos, 4)

    def test_post_b_los_detalles_vigentes_pasan_a_resuelto_y_los_finalizados_conservan_su_estado(self):
        """Postcondición b: cada detalle «vigente» pasa a «resuelto»; uno «finalizado» (reemplazado por una modificación) conserva su estado."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        otro = detalle_suministro(x.contrato, self.e.variedad, cantidad=10, estado="finalizado", fecha_fin_detalle=HOY - timedelta(days=1))
        self.resolver(x)
        self.assertEqual(self.releer(DetalleSuministro, x.detalle.pk).estado_detalle_suministro, "resuelto")
        self.assertEqual(self.releer(DetalleSuministro, otro.pk).estado_detalle_suministro, "finalizado")

    # ---- reservas y cosechas ----

    def test_post_c_la_cosecha_a_realizar_se_cancela_con_su_motivo_y_su_reserva_se_libera_sin_recubrir(self):
        """Postcondición c y PROD-CNL-ORD: la cosecha «a realizar» queda «cancelada» con la fecha actual y el motivo; su reserva, «liberada» sin volver a cubrirse (no se crea otra cosecha ni otra reserva)."""
        x = self.armar()
        reservas_antes = ReservaStock.objects.count()
        self.resolver(x)
        cosecha = self.releer(Cosecha, x.reserva_activa.cosecha_id)
        self.assertEqual((cosecha.estado_orden, cosecha.fecha_resolucion_orden, cosecha.motivo_cancelacion), ("cancelada", HOY, MOTIVO.format(codigo=x.contrato.codigo)))
        self.assertEqual(self.releer(ReservaStock, x.reserva_activa.pk).estado_reserva, "liberada")
        self.assertEqual(ReservaStock.objects.count(), reservas_antes)
        self.assertEqual(Cosecha.objects.filter(estado_orden="a_realizar").count(), 0)

    def test_post_d_la_reserva_lista_para_entrega_pasa_a_liberada(self):
        """Postcondición d: la reserva «lista para entrega» de los detalles del contrato queda «liberada»."""
        x = self.armar()
        self.resolver(x)
        self.assertEqual(self.releer(ReservaStock, x.reserva_lista.pk).estado_reserva, "liberada")

    def test_post_e_regla_producto_ya_cosechado_ingresa_a_la_camara_con_su_fecha_limite_desde_la_cosecha(self):
        """Postcondición e y regla «Producto ya cosechado»: una partida «disponible» con motivo `resolucion_del_contrato`, cantidad = mín(cosechada, reservada) de la línea, costo unitario el de la salida por
        cosecha, fecha de ingreso hoy y fecha límite = fecha de la cosecha + la duración postcosecha de la variedad (no se reinicia la vida útil); y su movimiento «ingreso a cámara» originado en el suministro."""
        x = self.armar()
        # Se cosecharon 15 de las 20 reservadas: la partida lleva 15 (regla 9 de 8.8: mín(cosechada, reservada)).
        DetalleReserva.objects.filter(reserva=x.reserva_lista, lote__isnull=False).update(cantidad_cosechada=15)
        MovimientoStock.objects.filter(origen_id=x.reserva_lista.cosecha_id, tipo_movimiento="salida_por_cosecha").update(cantidad=15)
        resultado = self.resolver(x)
        (partida,) = resultado.partidas
        partida = self.releer(StockCosechado, partida.pk)
        fecha_cosecha = HOY - timedelta(days=2)
        self.assertEqual(
            (partida.estado_stock_cosechado, partida.motivo_cosechado, partida.cantidad_ingreso_cosechado, partida.cantidad_disponible_cosechado, partida.fecha_ingreso),
            ("disponible", "resolucion_del_contrato", 15, 15, HOY),
        )
        self.assertEqual(partida.costo_unitario_cosechado, D("2.5000"))
        self.assertEqual(partida.fecha_limite, fecha_cosecha + timedelta(days=self.e.variedad.duracion_post_cosecha))
        movimiento = MovimientoStock.objects.get(partida=partida, tipo_movimiento="ingreso_a_camara")
        self.assertEqual((movimiento.origen_id, movimiento.cantidad), (x.contrato.pk, 15))

    # ---- entregas ----

    def test_post_f_la_entrega_a_realizar_se_cancela_con_sus_envases_y_deja_de_contar_para_el_transportista(self):
        """Postcondición f: la entrega «a realizar» queda «cancelada» con la fecha y el motivo; su reserva de envases, «cancelada» sin consumo; deja de contar para el límite diario de su Transportista."""
        x = self.armar()
        self.resolver(x)
        actual = self.releer(Entrega, x.entrega.pk)
        self.assertEqual((actual.estado_orden, actual.fecha_resolucion_orden, actual.motivo_cancelacion), ("cancelada", HOY, MOTIVO.format(codigo=x.contrato.codigo)))
        envase = x.envases.__class__.objects.get(pk=x.envases.pk)
        self.assertEqual((envase.estado, envase.cantidad_utilizada), ("cancelada", None))
        candidato = next(c for c in __import__("comercial.servicios.entregas", fromlist=["x"]).candidatos_para(self.e.invernadero, HOY, 1, None, hoy=HOY) if c.transportista.pk == self.t.pk)
        self.assertEqual(candidato.entregas_del_dia, 0)

    def test_post_g_la_alerta_de_entrega_sin_transportista_queda_resuelta(self):
        """Postcondición g y situación 8: la alerta «entrega sin transportista» activa de la entrega cancelada pasa a «resuelta»."""
        from comercial.servicios import entregas as servicio
        from maestros.tests.fabricas import crear_alerta

        x = self.armar(con_transportista=False)
        alerta = crear_alerta(self.e.invernadero, servicio.TIPO_SIN_TRANSPORTISTA, clave_estado=f"entrega:{x.entrega.pk}")
        AlertaComercial.objects.create(alerta=alerta, entrega=x.entrega)
        resultado = self.resolver(x)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIn(alerta, resultado.alertas_resueltas)

    # ---- la multa y la alerta ----

    # `test_post_h_no_se_crea_ningun_asiento_aunque_haya_multa` (COM-07b, D-57) se REEMPLAZÓ por `ComRsvSumAsientoTests` (CON-04d): la regla cambió, la multa ahora asienta (D-92 punto 10).

    def test_post_i_la_alerta_suministro_resuelto_es_para_el_gerente_y_describe_lo_que_se_deshizo(self):
        """Postcondición i y D-69 punto 14: alerta activa de evento, crítica, para el Gerente, con su `AlertaComercial(suministro=…)`; la descripción (hasta 200: el límite de `Alerta.descripcion_alerta`, el caso de uso dice 500) identifica el contrato, el cliente, la solicitud, los incumplimientos, la multa y lo que se deshizo."""
        x = self.armar()
        resultado = self.resolver(x)
        alerta = Alerta.objects.get(tipo_alerta="comercial_suministro_resuelto")
        self.assertEqual((alerta.estado_alerta, alerta.para_gerente, alerta.nivel_severidad, alerta.invernadero_id), ("activa", True, "critica", self.e.invernadero.pk))
        self.assertEqual(AlertaComercial.objects.get(alerta=alerta).suministro_id, x.contrato.pk)
        for texto in (x.contrato.codigo, str(self.e.cliente.nombre_visible), "4 de 3 tolerados", x.quejas[-1].codigo, "$ 50.000,00", "1 cosecha y 1 entrega", "1 partida ingresó a la cámara"):
            self.assertIn(texto, alerta.descripcion_alerta)
        self.assertLessEqual(len(alerta.descripcion_alerta), 200)
        self.assertEqual(resultado.alerta.pk, alerta.pk)

    def test_ext_5a_con_multa_cero_no_hay_asiento_y_la_alerta_dice_que_el_contrato_no_prevé_multa(self):
        """Extensión 5a: sin multa, la alerta y el aviso al cliente informan que el contrato no prevé multa."""
        x = self.armar(multa="0.00")
        self.resolver(x)
        self.assertIn("no prevé multa", Alerta.objects.get(tipo_alerta="comercial_suministro_resuelto").descripcion_alerta)

    # ---- después de confirmar ----

    def test_post_j_asigna_la_camara_con_la_partida_que_ingreso_y_la_linea_de_camara_liberada(self):
        """Postcondición j: PROD-ASG-CAM se dispara DESPUÉS de confirmar, con la partida creada y la partida cuya línea se liberó (3b)."""
        x = self.armar()
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar:
            with self.captureOnCommitCallbacks(execute=False) as despues:
                resultado = resoluciones.resolver_suministro(x.contrato.pk, HOY)
            asignar.assert_not_called()
            for callback in despues:
                callback()
        de_camara = x.reserva_lista.lineas.get(partida__isnull=False).partida_id
        (ids,) = [c.args[0] for c in asignar.call_args_list]
        self.assertEqual(sorted(ids), sorted([resultado.partidas[0].pk, de_camara]))

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_k_el_cliente_recibe_el_aviso_de_resolucion_con_la_multa_y_las_entregas_canceladas(self):
        """Postcondición k y «Lista de tecnología», 8: correo al cliente con el contrato, la fecha, los incumplimientos, la multa, las entregas canceladas con su fecha y que las concretadas se siguen cobrando; pie «sin validez fiscal»."""
        x = self.armar()
        self.resolver(x)
        (correo,) = [m for m in mail.outbox if self.e.cliente.email_cliente in m.to]
        self.assertEqual(correo.subject, f"Resolución de tu suministro {x.contrato.codigo}")
        for texto in ("4 de 3", "$ 50.000,00", x.entrega.codigo, f"{x.entrega.fecha_programada_orden:%d/%m/%Y}", "se siguen cobrando", "sin validez fiscal"):
            self.assertIn(texto, correo.body)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_comprobante, "enviado")

    def test_ext_8a_si_el_correo_no_sale_la_resolucion_queda_y_el_comprobante_pendiente_de_envio(self):
        """Extensión 8a: sin correo del sistema configurado (o con un envío que falla), la resolución permanece y `estado_comprobante` queda «pendiente de envío» (se reenvía con «Reenviar comprobante»)."""
        x = self.armar()
        self.resolver(x)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.estado_comprobante), ("resuelto", "pendiente_envio"))

    def test_post_l_avisos_al_vendedor_al_agronomo_al_capataz_y_al_transportista(self):
        """Postcondición l y «Lista de tecnología», 9: el Vendedor, una notificación con la multa y las entregas canceladas; el Agrónomo, UNA con las cosechas, las partidas y los envases; el Capataz, el aviso de la cosecha
        cancelada; el Transportista, el de la entrega cancelada."""
        x = self.armar()
        self.resolver(x)
        (vendedor,) = self.avisos(self.e.vendedor, f"{x.contrato.codigo} resuelto por incumplimientos")
        self.assertIn("$ 50.000,00", vendedor.detalle)
        self.assertIn(x.entrega.codigo, vendedor.detalle)
        agronomo = self.avisos(self.e.agronomo)
        self.assertEqual(len(agronomo), 1)
        self.assertEqual(agronomo[0].titulo, f"{x.contrato.codigo} resuelto: cambios en {self.e.invernadero}")
        cosecha = self.releer(Cosecha, x.reserva_activa.cosecha_id)
        for texto in (cosecha.codigo, "20 plantas", "Envases que estaban reservados", x.entrega.codigo):
            self.assertIn(texto, agronomo[0].detalle)
        self.assertEqual(len(self.avisos(self.e.capataz)), 1)
        self.assertEqual(len(self.avisos(self.t, f"Se canceló la entrega {x.entrega.codigo}")), 1)

    def test_post_m_un_solo_registro_de_auditoria_de_proceso_automatico_con_todo_lo_afectado(self):
        """Postcondición m y D-36: UN registro `resolucion_suministro`, sin usuario (InfoPonia, D-27), con el cambio de estado y de fecha del suministro y, afectados, el contrato, el detalle, las reservas, la cosecha, la entrega, sus envases, la partida con su movimiento y la alerta."""
        x = self.armar()
        self.resolver(x)
        (registro,) = self.registros("resolucion_suministro")
        self.assertIsNone(registro.usuario_id)
        self.assertEqual(registro.rol, "infoponia")
        self.assertEqual(registro.detalle["cambios"]["estado_suministro"], {"antes": "vigente", "despues": "resuelto"})
        self.assertEqual(registro.detalle["cambios"]["solicitud_resolucion"]["despues"]["id"], x.quejas[-1].pk)
        modelos = {a["modelo"] for a in registro.afectados}
        for modelo in ("comercial.suministro", "comercial.detallesuministro", "comercial.reservastock", "produccion.stockcosechado", "produccion.movimientostock", "maestros.alerta", "produccion.reservainsumo"):
            self.assertIn(modelo, modelos)
        self.assertEqual(registro.afectados[0]["id"], x.contrato.pk)
        self.assertEqual(len(self.registros("resolucion_suministro_descartada")), 0)

    # ---- las reglas ----

    def test_regla_que_no_cambia_lo_ya_ocurrido(self):
        """«Qué no cambia»: la entrega concretada (su monto y su estado), sus reservas «entregada», una solicitud pendiente y la cantidad de incumplimientos quedan como estaban."""
        x = self.armar()
        r = reserva_lista(None, self.lote, 5, fecha_entrega=HOY - timedelta(days=12), detalle_suministro=x.detalle)
        concretada = marcar_concretada(entrega(x.contrato, [r], fecha=HOY - timedelta(days=12)), cantidades=[(5, 0, 0)])
        ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
        pendiente = queja(concretada, "otro")
        antes = (concretada.monto_total_entrega, concretada.estado_orden, concretada.fecha_vencimiento_pago)
        self.resolver(x)
        actual = self.releer(Entrega, concretada.pk)
        self.assertEqual((actual.monto_total_entrega, actual.estado_orden, actual.fecha_vencimiento_pago), antes)
        self.assertEqual(self.releer(ReservaStock, r.pk).estado_reserva, "entregada")
        self.assertEqual(self.releer(SolicitudRevision, pendiente.pk).estado_solicitud, "pendiente")
        self.assertEqual(self.releer(Suministro, x.contrato.pk).cantidad_incumplimientos, 4)

    def test_regla_la_resolucion_prevalece_sobre_una_rescision_acordada(self):
        """Disparador «Resolución de un contrato con rescisión acordada»: los datos de la rescisión quedan como estaban y el contrato queda «resuelto» (el paso 35 ya no lo toma)."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        Suministro.objects.filter(pk=x.contrato.pk).update(
            motivo_rescision="a_pedido_del_cliente", fecha_acuerdo_rescision=HOY, fecha_registro_rescision=HOY, fecha_ultima_entrega_rescision=HOY + timedelta(days=30)
        )
        self.resolver(x)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.motivo_rescision, contrato.fecha_ultima_entrega_rescision), ("resuelto", "a_pedido_del_cliente", HOY + timedelta(days=30)))

    def test_regla_la_alerta_de_periodo_sin_cobertura_del_contrato_queda_resuelta(self):
        """Paso 4.6 (regla 7 de 8.18, va a pendientes_CU): la alerta «período sin cobertura completa» activa de un detalle del contrato se resuelve con el contrato; las de las solicitudes pendientes no cambian."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        fecha = HOY + timedelta(days=16)
        de_periodo = alerta_de_periodo(x.detalle, fecha, invernadero=self.e.invernadero)
        pendiente = queja(marcar_concretada(entrega(x.contrato, [reserva_lista(None, self.lote, 5, fecha_entrega=HOY - timedelta(days=12), detalle_suministro=x.detalle)], fecha=HOY - timedelta(days=12)), cantidades=[(5, 0, 0)]))
        self.resolver(x)
        de_periodo.refresh_from_db()
        self.assertEqual(de_periodo.estado_alerta, "resuelta")
        self.assertEqual(AlertaComercial.objects.get(solicitud=pendiente).alerta.estado_alerta, "activa")

    # ---- extensiones ----

    def test_ext_3a_sin_reservas_ni_entregas_solo_se_resuelven_el_suministro_y_sus_detalles(self):
        """Extensión 3a: nada que deshacer: no se incluye PROD-CNL-ORD ni se crean partidas, no se dispara PROD-ASG-CAM; se resuelven el suministro y el detalle, se genera la alerta y se audita."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar:
            resultado = self.resolver(x)
        asignar.assert_not_called()
        self.assertEqual((resultado.cosechas, resultado.entregas, resultado.partidas), ([], [], []))
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual(len(self.registros("resolucion_suministro")), 1)
        self.assertIsNotNone(resultado.alerta)
        self.assertEqual(StockCosechado.objects.filter(motivo_cosechado="resolucion_del_contrato").count(), 0)

    def test_ext_3b_las_lineas_de_camara_no_crean_partidas_y_su_stock_vuelve_a_estar_libre(self):
        """Extensión 3b: una reserva «lista para entrega» solo con líneas de cámara no crea partidas; al liberarse, el stock que apartaba vuelve a estar libre en la partida (no cambia su cantidad disponible)."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        partida = partida_cosechada(self.lote, 10)
        r = reserva(None, [(partida, 10)], fecha_entrega=HOY + timedelta(days=2), detalle_suministro=x.detalle)
        with mock.patch("comercial.servicios.camara.asignar_camara") as asignar:
            resultado = self.resolver(x)
        self.assertEqual(resultado.partidas, [])
        self.assertEqual(self.releer(ReservaStock, r.pk).estado_reserva, "liberada")
        self.assertEqual(self.releer(StockCosechado, partida.pk).cantidad_disponible_cosechado, 10)
        asignar.assert_called_once_with([partida.pk])

    def test_ext_3c_una_entrega_en_curso_se_cancela_igual_y_el_transportista_recibe_no_la_entregues(self):
        """Extensión 3c: el Transportista ya inició la ruta y la entrega es de hoy: se cancela igual y se le avisa «No la entregues…»; la partida de cámara se crea aunque el producto esté en el vehículo."""
        en_ruta = transportista_con_vehiculo(self.e.invernadero, "800", en_ruta=True)
        x = self.armar(con_transportista=False, en_curso=True)
        Entrega.objects.filter(pk=x.entrega.pk).update(transportista=en_ruta, fecha_programada_orden=HOY)
        resultado = self.resolver(x)
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "cancelada")
        (aviso,) = self.avisos(en_ruta, f"Se canceló la entrega {x.entrega.codigo}")
        self.assertIn("No la entregues", aviso.detalle)
        self.assertEqual(len(resultado.partidas), 1)

    def test_ext_3d_una_entrega_sin_envasado_no_menciona_envases_al_agronomo(self):
        """Extensión 3d: sin envasado planificado no hay reservas de insumo que cancelar y el aviso al Agrónomo no menciona envases."""
        x = self.armar(con_envasado=False)
        self.resolver(x)
        (agronomo,) = self.avisos(self.e.agronomo)
        self.assertNotIn("Envases", agronomo.detalle)

    def test_ext_2a_un_suministro_que_ya_no_esta_vigente_no_cambia_nada_y_no_deja_registro(self):
        """Extensión 2a: «finalizado» (o ya «resuelto»): no se registra ningún cambio ni el registro de disparo descartado."""
        x = self.armar()
        Suministro.objects.filter(pk=x.contrato.pk).update(estado_suministro="finalizado")
        self.assertIsNone(self.resolver(x))
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "a_realizar")
        self.assertEqual(RegistroAuditoria.objects.filter(accion__startswith="resolucion_suministro").count(), 0)
        verificar = self.releer(Suministro, x.contrato.pk)
        self.assertEqual(verificar.estado_suministro, "finalizado")
        Suministro.objects.filter(pk=x.contrato.pk).update(estado_suministro="vigente")  # para que los invariantes de limpieza no vean un contrato finalizado con reservas pendientes

    def test_ext_2b_si_no_supera_los_tolerados_no_cambia_nada_y_deja_el_disparo_descartado(self):
        """Extensión 2b y D-69 punto 15: con 4 incumplimientos de 5 tolerados el disparo no corresponde: nada cambia y queda UN registro `resolucion_suministro_descartada` sin usuario, con el suministro y los dos números."""
        x = self.armar(tolerados=5, con_solicitudes=False)
        Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=4)
        self.assertIsNone(self.resolver(x))
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "vigente")
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "a_realizar")
        (registro,) = self.registros("resolucion_suministro_descartada")
        self.assertIsNone(registro.usuario_id)
        self.assertEqual((registro.detalle["datos"]["cantidad_incumplimientos"], registro.detalle["datos"]["incumplimientos_tolerados"]), (4, 5))
        self.assertEqual(self.registros("resolucion_suministro"), [])

    def test_ext_6b_sin_gerente_activo_la_alerta_se_registra_igual(self):
        """Extensión 6b: sin Gerente activo, la alerta «suministro resuelto» se registra igual (queda esperando al Gerente) y la resolución sigue."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        Usuario.objects.filter(pk=self.gerente.pk).update(is_active=False)
        self.resolver(x)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_suministro_resuelto", estado_alerta="activa", para_gerente=True).count(), 1)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")

    def test_ext_d63_4_sin_invernadero_activo_no_hay_alerta_y_se_avisa_al_vendedor_y_al_gerente(self):
        """D-63 punto 4: si ni el invernadero de la primera reserva ni uno activo del Vendedor admiten la alerta (invernadero inactivo), no se crea la alerta; se avisa al Vendedor y al Gerente con el mismo texto y la resolución sigue."""
        from maestros.models import Invernadero

        x = self.armar(con_entrega=False, con_reserva_activa=False)
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        resultado = self.resolver(x)
        self.assertIsNone(resultado.alerta)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_suministro_resuelto").count(), 0)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        titulo = f"{x.contrato.codigo} resuelto por incumplimientos"
        (al_gerente,) = self.avisos(self.gerente, titulo)
        self.assertIn("resuelto por incumplimientos: 4 de 3 tolerados", al_gerente.detalle)
        self.assertEqual(len(self.avisos(self.e.vendedor, titulo)), 1)

    def test_ext_7a_si_la_asignacion_de_camara_falla_la_resolucion_permanece(self):
        """Extensión 7a: si PROD-ASG-CAM falla, la resolución permanece registrada (el reintento lo maneja PROD-ASG-CAM y el paso 25)."""
        x = self.armar()
        with mock.patch("comercial.servicios.camara.asignar_camara", side_effect=RuntimeError("falló")):
            self.resolver(x)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")

    def test_ext_9a_sin_vendedor_activo_ni_agronomo_activo_no_se_envian_esas_notificaciones(self):
        """Extensión 9a: el Vendedor inactivo o un invernadero sin Agrónomo activo: esa notificación no se envía y la resolución sigue (el Gerente ya tiene la alerta)."""
        x = self.armar()
        Usuario.objects.filter(pk__in=[self.e.vendedor.pk, self.e.agronomo.pk]).update(is_active=False)
        self.resolver(x)
        self.assertEqual(self.avisos(self.e.vendedor, x.contrato.codigo), [])
        self.assertEqual(self.avisos(self.e.agronomo), [])
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")

    def test_ext_a_una_falla_antes_de_confirmar_no_cambia_nada(self):
        """Extensión *a y garantías mínimas: si algo falla a mitad (acá, al cancelar la entrega), se revierte todo: el suministro y el detalle siguen «vigentes», las reservas, la cosecha y la entrega no cambian, no hay partidas
        ni alerta ni registro de auditoría. La excepción sube a quien llama."""
        x = self.armar()
        with mock.patch("comercial.servicios.entregas.cancelar_entrega_incluida", side_effect=RuntimeError("falló")):
            with self.assertRaises(RuntimeError):
                resoluciones.resolver_suministro(x.contrato.pk, HOY)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "vigente")
        self.assertEqual(self.releer(ReservaStock, x.reserva_lista.pk).estado_reserva, "lista_para_entrega")
        self.assertEqual(self.releer(Cosecha, x.reserva_activa.cosecha_id).estado_orden, "a_realizar")
        self.assertEqual(Alerta.objects.filter(tipo_alerta="comercial_suministro_resuelto").count(), 0)
        self.assertEqual(StockCosechado.objects.filter(motivo_cosechado="resolucion_del_contrato").count(), 0)
        self.assertEqual(RegistroAuditoria.objects.filter(accion__startswith="resolucion_suministro").count(), 0)

    # ---- 6a: lo que aparece entre la lectura y el bloqueo ----

    def _con_reserva_nueva_al_bloquear(self, x, invernaderos):
        """Un `_bloquear` que, las primeras veces, deja que otra operación cree una reserva en `invernaderos[i]` (otro invernadero que la lectura previa no vio) justo antes de bloquear."""
        original = resoluciones._bloquear
        llamadas = []

        def con_alta(previo):
            i = len(llamadas)
            llamadas.append(i)
            if i < len(invernaderos):
                lote = lote_maduro(invernaderos[i], 100)
                reserva_de_periodo(x.detalle, HOY + timedelta(days=9 + 7 * i), [(lote, 10)])
            return original(previo)

        return mock.patch.object(resoluciones, "_bloquear", side_effect=con_alta), llamadas

    def test_ext_6a_una_reserva_nueva_de_otro_invernadero_obliga_a_repetir_una_vez(self):
        """Extensión 6a.1: al bloquear aparece una reserva de un invernadero que no se bloqueó: se descarta lo calculado y se repite UNA vez desde el paso 2, dentro de la misma operación, y la reserva nueva también se libera."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        sur = segundo_invernadero(self.e)
        parche, llamadas = self._con_reserva_nueva_al_bloquear(x, [sur])
        with parche:
            resultado = self.resolver(x)
        self.assertEqual(len(llamadas), 2)
        self.assertIsNotNone(resultado)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual(ReservaStock.objects.filter(detalle_suministro=x.detalle, estado_reserva__in=["activa", "lista_para_entrega"]).count(), 0)

    def test_ext_6a_si_al_repetir_vuelve_a_cambiar_no_registra_nada_y_queda_pendiente(self):
        """Extensión 6a.3: si en la segunda lectura vuelve a aparecer algo, no registra ningún cambio y el disparo queda pendiente (lo toma el paso 33)."""
        x = self.armar(con_entrega=False, con_reserva_activa=False)
        sur = segundo_invernadero(self.e, nombre="Invernadero Sur")
        este = segundo_invernadero(self.e, nombre="Invernadero Este")
        parche, llamadas = self._con_reserva_nueva_al_bloquear(x, [sur, este])
        with parche:
            self.assertIsNone(self.resolver(x))
        self.assertEqual(len(llamadas), 2)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual(contrato.estado_suministro, "vigente")
        self.assertEqual(RegistroAuditoria.objects.filter(accion__startswith="resolucion_suministro").count(), 0)
        # Para que los invariantes de limpieza no vean reservas pendientes de un contrato resuelto: el contrato sigue vigente, así que no hay nada que verificar.

    def test_ext_6a_una_cosecha_que_se_concreto_antes_de_bloquear_deja_su_reserva_lista_y_se_trata_como_las_demas(self):
        """Extensión 6a.2: una cosecha que quedó «concretada» deja su reserva «lista para entrega»; se trata en el paso 6 como las demás (su producto cosechado ingresa a la cámara)."""
        x = self.armar(con_entrega=False)
        original = resoluciones._bloquear

        def concretar_antes(previo):
            c = x.reserva_activa.cosecha
            Bitacora.objects.create(
                invernadero=self.lote.invernadero, lote=self.lote, etapa=self.lote.etapa, tipo_evento="cosecha", cosecha=c, fecha_bitacora=HOY, hora_bitacora=timezone.localtime().time()
            )
            Cosecha.objects.filter(pk=c.pk).update(estado_orden="concretada", fecha_resolucion_orden=HOY, fecha_cosecha=HOY)
            DetalleReserva.objects.filter(reserva=x.reserva_activa).update(cantidad_cosechada=30)
            ReservaStock.objects.filter(pk=x.reserva_activa.pk).update(estado_reserva="lista_para_entrega")
            MovimientoStock.objects.create(origen_id=c.pk, lote=self.lote, tipo_movimiento="salida_por_cosecha", cantidad=30, costo_unitario=D("1.0000"))
            return original(previo)

        with mock.patch.object(resoluciones, "_bloquear", side_effect=concretar_antes):
            resultado = self.resolver(x)
        self.assertEqual(self.releer(Cosecha, x.reserva_activa.cosecha_id).estado_orden, "concretada")
        self.assertEqual(self.releer(ReservaStock, x.reserva_activa.pk).estado_reserva, "liberada")
        self.assertEqual([p.cantidad_ingreso_cosechado for p in resultado.partidas], [30])

    # ---- los disparadores ----

    def test_disparador_1_resolver_si_corresponde_resuelve_y_no_deja_pasar_una_falla(self):
        """Disparador 1 y D-69 punto 13: `resolver_si_corresponde` corre el caso de uso en su propia transacción; si algo falla registra la excepción y devuelve `None` (la aceptación ya quedó; el paso 33 lo retoma)."""
        x = self.armar()
        with self.captureOnCommitCallbacks(execute=True):
            resultado = resoluciones.resolver_si_corresponde(x.contrato.pk)
        self.assertEqual(resultado.suministro.estado_suministro, "resuelto")
        y = self.armar()
        with mock.patch("comercial.servicios.resoluciones._resolver", side_effect=RuntimeError("falló")), self.assertLogs("infoponia.resoluciones", "ERROR"):
            self.assertIsNone(resoluciones.resolver_si_corresponde(y.contrato.pk))
        self.assertEqual(self.releer(Suministro, y.contrato.pk).estado_suministro, "vigente")

    def test_disparador_1_una_aceptacion_comun_sin_superar_los_tolerados_no_hace_nada_ni_deja_registro(self):
        """COM-07a llama a `resolver_si_corresponde` con CADA aceptación: sin superar los tolerados no cambia nada ni llena la auditoría con «disparos descartados» (2b queda para el disparo que llega tarde)."""
        x = self.armar(tolerados=5, con_solicitudes=False)
        Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=2)
        self.assertIsNone(resoluciones.resolver_si_corresponde(x.contrato.pk))
        self.assertEqual(RegistroAuditoria.objects.filter(accion__startswith="resolucion_suministro").count(), 0)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "vigente")

    def test_disparador_1_desde_la_aceptacion_de_una_queja_el_contrato_queda_resuelto(self):
        """Disparador 1, de punta a punta: el Gerente acepta la cuarta queja de un suministro con 3 tolerados; después del commit, el contrato queda «resuelto» con esa solicitud (la 2a de COM-ANL-SRV ya se da con datos reales)."""
        from comercial.servicios import solicitudes
        from comercial.servicios.solicitudes import DatosDeResolucion

        x = self.armar(con_solicitudes=False)
        incumplimientos = self.incumplimientos(x.contrato, x.detalle, 3)
        Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=3)
        r = reserva_lista(None, self.lote, 5, fecha_entrega=HOY - timedelta(days=19), detalle_suministro=x.detalle)
        concretada = marcar_concretada(entrega(x.contrato, [r], fecha=HOY - timedelta(days=19)), cantidades=[(5, 0, 0)])
        ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
        pendiente = queja(concretada, "otro")
        datos = DatosDeResolucion("aceptar", "", "10.00", "")
        resumen = solicitudes.resumen_de_resolucion(self.gerente, pendiente.pk, datos)
        with self.captureOnCommitCallbacks(execute=True):
            solicitudes.resolver_queja(self.gerente, pendiente.pk, datos, resumen.huella)
        contrato = self.releer(Suministro, x.contrato.pk)
        self.assertEqual((contrato.estado_suministro, contrato.solicitud_resolucion_id), ("resuelto", pendiente.pk))
        self.assertEqual(len(incumplimientos), 3)

    def test_regla_idempotencia_dos_disparos_seguidos_uno_resuelve_y_el_otro_termina_en_2a(self):
        """Idempotencia: el segundo disparo del mismo contrato ya lo encuentra «resuelto» (2a): no cambia nada ni deja otro registro."""
        x = self.armar()
        self.assertIsNotNone(self.resolver(x))
        antes = RegistroAuditoria.objects.count()
        self.assertIsNone(self.resolver(x))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(len(self.registros("resolucion_suministro")), 1)


class ComRsvSumRecuperacionDiariaTests(BaseDeResolucion):
    """El paso diario 33 (disparador 2 y extensión 1a): `resolver_suministros_pendientes(hoy)`; D-56 (puntos 4, 5 y 6) y D-69 (punto 7)."""

    def pasar(self, hoy=None):
        with self.captureOnCommitCallbacks(execute=True):
            return resoluciones.resolver_suministros_pendientes(hoy or HOY)

    def test_disparador_2_el_paso_resuelve_el_contrato_cuyo_disparo_se_perdio(self):
        """Disparador 2 y situación 6: un suministro «vigente» con más incumplimientos que los tolerados (el disparo falló o no llegó) se resuelve; el resumen cuenta lo revisado y lo resuelto."""
        x = self.armar()
        resumen = self.pasar()
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "cancelada")
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 0, 1))
        self.assertEqual(resumen.detalle, "1 suministros resueltos, 0 descartados, 0 con error")

    def test_ext_1a_con_dos_candidatos_se_procesan_del_que_supero_la_tolerancia_antes_al_que_la_supero_despues(self):
        """Extensión 1a.3: de a uno, del que superó la tolerancia antes (la `fecha_resolucion` de su solicitud aceptada más reciente) al que la superó después; cada uno con su propia transacción."""
        despues = self.armar()
        antes = self.armar()
        SolicitudRevision.objects.filter(pk__in=[q.pk for q in antes.quejas]).update(fecha_resolucion=HOY - timedelta(days=5))
        self.pasar()
        orden = [r.afectados[0]["id"] for r in self.registros("resolucion_suministro")]
        self.assertEqual(orden, [antes.contrato.pk, despues.contrato.pk])

    def test_ext_1a_sin_candidatos_no_registra_nada(self):
        """Extensión 1a.2: sin suministros que superen los tolerados (uno que no los supera y uno ya «finalizado» no cuentan), el caso de uso termina sin registrar nada."""
        no_supera = self.armar(tolerados=5, con_solicitudes=False)
        Suministro.objects.filter(pk=no_supera.contrato.pk).update(cantidad_incumplimientos=2)
        finalizado = self.armar(con_entrega=False, con_reserva_activa=False)
        Suministro.objects.filter(pk=finalizado.contrato.pk).update(estado_suministro="finalizado")
        antes = RegistroAuditoria.objects.count()
        resumen = self.pasar()
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (0, 0, 0))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        Suministro.objects.filter(pk=finalizado.contrato.pk).update(estado_suministro="vigente")

    def test_regla_idempotencia_un_segundo_pase_el_mismo_dia_no_encuentra_nada(self):
        """D-56 punto 4: correr el paso dos veces el mismo día no duplica nada: el segundo no encuentra candidatos y no deja registros."""
        self.armar()
        self.pasar()
        antes = RegistroAuditoria.objects.count()
        resumen = self.pasar()
        self.assertEqual((resumen.procesados, resumen.resueltos), (0, 0))
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_un_contrato_que_falla_queda_en_el_log_y_los_demas_se_resuelven(self):
        """D-56 punto 5: si un contrato falla, se registra y siguen los demás; el que falló sigue «vigente» (su transacción se deshizo) y el resumen lo cuenta."""
        primero = self.armar()
        segundo = self.armar()
        real = resoluciones.resolver_suministro

        def falla_el_primero(suministro_id, hoy, **opciones):
            if suministro_id == primero.contrato.pk:
                raise RuntimeError("falló")
            return real(suministro_id, hoy, **opciones)

        with mock.patch.object(resoluciones, "resolver_suministro", side_effect=falla_el_primero), self.assertLogs("infoponia.resoluciones", "ERROR"):
            resumen = self.pasar()
        self.assertEqual(self.releer(Suministro, primero.contrato.pk).estado_suministro, "vigente")
        self.assertEqual(self.releer(Suministro, segundo.contrato.pk).estado_suministro, "resuelto")
        self.assertEqual((resumen.procesados, resumen.resueltos), (2, 1))
        self.assertEqual(resumen.detalle, "1 suministros resueltos, 0 descartados, 1 con error")
        # El contrato que falló no queda a medias: el invariante de abajo ve su reserva «lista para entrega» y la cosecha «a realizar», pero el contrato sigue vigente.
        self.assertEqual(self.releer(Cosecha, primero.reserva_activa.cosecha_id).estado_orden, "a_realizar")

    def test_regla_el_paso_33_esta_registrado_antes_del_35_el_40_y_el_50(self):
        """D-69 punto 7: el paso «resolver_suministros» está registrado con el orden 33 (después del 30 y antes del 35, el 40 y el 50), y `proceso_diario --listar` lo muestra."""
        from io import StringIO

        from django.core.management import call_command

        from core.procesos import pasos_diarios

        ordenes = {p.codigo: p.orden for p in pasos_diarios()}
        self.assertEqual(ordenes["resolver_suministros"], 33)
        self.assertLess(ordenes["resolver_suministros"], min(ordenes["cerrar_rescisiones"], ordenes["pre_reservar_suministros"], ordenes["planificar_entregas"]))
        salida = StringIO()
        call_command("proceso_diario", "--listar", stdout=salida)
        self.assertIn("resolver_suministros", salida.getvalue())

    def test_regla_proceso_diario_solo_resolver_suministros_resuelve_y_una_segunda_corrida_no_hace_nada(self):
        """`python manage.py proceso_diario --solo resolver_suministros` (el comando del cron): resuelve el contrato; corrido otra vez, no hace nada."""
        from io import StringIO

        from django.core.management import call_command

        x = self.armar()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", solo="resolver_suministros", stdout=StringIO())
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        antes = RegistroAuditoria.objects.count()
        call_command("proceso_diario", solo="resolver_suministros", stdout=StringIO())
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_regla_con_rescision_acordada_el_paso_33_resuelve_antes_de_que_el_35_lo_rescinda(self):
        """Disparador «Resolución de un contrato con rescisión acordada»: un contrato con rescisión acordada ya vencida que supera los tolerados lo resuelve el paso 33 y el 35 ya no lo toma (queda «resuelto», no «rescindido»)."""
        from comercial.servicios import suministros

        x = self.armar(con_entrega=False, con_reserva_activa=False)
        Suministro.objects.filter(pk=x.contrato.pk).update(
            motivo_rescision="a_pedido_del_cliente", fecha_acuerdo_rescision=HOY - timedelta(days=9), fecha_registro_rescision=HOY - timedelta(days=9), fecha_ultima_entrega_rescision=HOY - timedelta(days=1)
        )
        self.pasar()
        suministros.cerrar_rescisiones(HOY)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")


class ComRsvSumAsientoTests(BaseDeResolucion):
    """CON-04d · paso 4: el asiento de la multa por resolución (COM-RSV-SUM postcondición h; D-92 punto 10; D-86). El actor es InfoPonia (sin usuario). Origen: el `Suministro` (R012); fecha: la de la resolución (hoy). Debe «Indemnizaciones
    por Resolución de Contratos» / Haber «Indemnizaciones a Pagar» (2.1.02) por `multa_resolucion`. Multa 0: sin asiento y sin error (H11). Su pago no tiene caso de uso: lo registra el Contador con un asiento manual."""

    def lineas(self, asiento):
        return sorted((m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in asiento.movimientos.select_related("cuenta"))

    def test_post_h_la_multa_asienta_indemnizaciones_por_resolucion_contra_indemnizaciones_a_pagar(self):
        """Postcondición h: con una multa de $ 50.000,00, un asiento Debe Indemnizaciones por Resolución de Contratos / Haber Indemnizaciones a Pagar, originado en el suministro, con la fecha de hoy."""
        x = self.armar(multa="50000.00")
        self.resolver(x)
        asiento = AsientoContable.objects.get(origen_id=x.contrato.pk)
        self.assertEqual(self.lineas(asiento), sorted([(cuentas.INDEMNIZACIONES_POR_RESOLUCION, DEBE, D("50000.00")), (cuentas.INDEMNIZACIONES_A_PAGAR, HABER, D("50000.00"))]))
        self.assertEqual((asiento.fecha_asiento, AsientoContable.objects.count()), (HOY, 1))
        verificar_invariantes_contables()

    def test_post_h_el_asiento_lleva_la_fecha_de_la_resolucion_que_se_le_pasa(self):
        """D-92 punto 4: la fecha del asiento es la de la resolución (el `hoy` del servicio), no la del reloj."""
        ejercicio_abierto(HOY - timedelta(days=60))
        x = self.armar(multa="50000.00")
        self.resolver(x, hoy=HOY - timedelta(days=1))
        self.assertEqual(AsientoContable.objects.get(origen_id=x.contrato.pk).fecha_asiento, HOY - timedelta(days=1))

    def test_ext_5a_con_multa_cero_no_hay_asiento_y_no_falla(self):
        """Extensión 5a y H11: sin multa no se arma ningún asiento; la resolución se hace igual."""
        x = self.armar(multa="0.00")
        self.resolver(x)
        self.assertEqual((self.releer(Suministro, x.contrato.pk).estado_suministro, AsientoContable.objects.count()), ("resuelto", 0))

    def test_post_m_el_registro_de_auditoria_de_proceso_automatico_nombra_el_asiento(self):
        """Postcondición m y D-86 punto 4: el único registro `resolucion_suministro` (sin usuario) nombra el asiento entre sus afectados y en `datos["asientos"]`; el asiento no se audita aparte con el usuario de la resolución."""
        x = self.armar(multa="50000.00")
        self.resolver(x)
        (registro,) = self.registros("resolucion_suministro")
        asiento = AsientoContable.objects.get(origen_id=x.contrato.pk)
        self.assertTrue(any(a["id"] == asiento.pk and a["texto"].startswith("Asiento") for a in registro.afectados))
        self.assertEqual(len(registro.detalle["datos"]["asientos"]), 1)
        self.assertIsNone(registro.usuario_id)

    def test_garantia_si_falla_el_asiento_no_se_resuelve_nada(self):
        """Garantía mínima y extensión *a: si el asiento de la multa falla, el suministro sigue «vigente», no se cancela la entrega ni la cosecha, no hay alerta ni asiento ni registro de auditoría; el disparo queda pendiente."""
        x = self.armar(multa="50000.00")
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                self.resolver(x)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "vigente")
        self.assertEqual(self.releer(Entrega, x.entrega.pk).estado_orden, "a_realizar")
        self.assertEqual((AsientoContable.objects.count(), Alerta.objects.filter(tipo_alerta="comercial_suministro_resuelto").count(), len(self.registros("resolucion_suministro"))), (0, 0, 0))

    def test_disparador_2_el_paso_33_asienta_la_multa_una_sola_vez(self):
        """Disparador 2 (paso diario 33): la recuperación diaria resuelve el contrato cuyo disparo se perdió y asienta su multa; un segundo pase el mismo día no duplica el asiento."""
        x = self.armar(multa="50000.00")
        with self.captureOnCommitCallbacks(execute=True):
            resoluciones.resolver_suministros_pendientes(HOY)
            resoluciones.resolver_suministros_pendientes(HOY)
        self.assertEqual(AsientoContable.objects.filter(origen_id=x.contrato.pk).count(), 1)

    # ---- el actor del asiento de la multa coincide con el del registro de auditoría de la resolución (InfoPonia, sin usuario) en los dos caminos ----

    def _registro_de_alta_del_asiento(self, asiento):
        """El registro `alta_asiento_contable` que hizo `registrar_asiento_automatico` para ese asiento (D-86 punto 4)."""
        return RegistroAuditoria.objects.filter(accion="alta_asiento_contable", afectados__contains=[{"modelo": "contabilidad.asientocontable", "id": asiento.pk}]).get()

    def test_actor_el_paso_diario_33_asienta_la_multa_sin_usuario_igual_que_su_registro_de_auditoria(self):
        """Camino 1 (paso diario 33): el actor es `None` (InfoPonia, D-27). El alta del asiento de la multa y el registro `resolucion_suministro` no tienen usuario."""
        x = self.armar(multa="50000.00")
        with self.captureOnCommitCallbacks(execute=True):
            resoluciones.resolver_suministros_pendientes(HOY)
        asiento = AsientoContable.objects.get(origen_id=x.contrato.pk)
        (resolucion,) = self.registros("resolucion_suministro")
        self.assertEqual((self._registro_de_alta_del_asiento(asiento).usuario_id, resolucion.usuario_id), (None, None))

    def test_actor_la_aceptacion_de_una_queja_por_una_persona_asienta_la_multa_sin_usuario_y_la_indemnizacion_con_el_gerente(self):
        """Camino 2 (la aceptación de la cuarta queja por el Gerente; la resolución corre después del commit, como InfoPonia): el asiento de la INDEMNIZACIÓN lleva al Gerente y el de la MULTA, sin usuario, igual que el
        registro `resolucion_suministro`. Cada asiento tiene su propio origen (la queja y el suministro, R012)."""
        from comercial.servicios import solicitudes
        from comercial.servicios.solicitudes import DatosDeResolucion

        x = self.armar(con_solicitudes=False, multa="50000.00")
        self.incumplimientos(x.contrato, x.detalle, 3)
        Suministro.objects.filter(pk=x.contrato.pk).update(cantidad_incumplimientos=3)
        r = reserva_lista(None, self.lote, 5, fecha_entrega=HOY - timedelta(days=19), detalle_suministro=x.detalle)
        concretada = marcar_concretada(entrega(x.contrato, [r], fecha=HOY - timedelta(days=19)), cantidades=[(5, 0, 0)])
        ReservaStock.objects.filter(pk=r.pk).update(estado_reserva="entregada")
        pendiente = queja(concretada, "otro")
        datos = DatosDeResolucion("aceptar", "", "10.00", "")
        huella = solicitudes.resumen_de_resolucion(self.gerente, pendiente.pk, datos).huella
        with self.captureOnCommitCallbacks(execute=True):
            solicitudes.resolver_solicitud(self.gerente, pendiente.pk, datos, huella)
        self.assertEqual(self.releer(Suministro, x.contrato.pk).estado_suministro, "resuelto")
        indemnizacion, multa = AsientoContable.objects.get(origen_id=pendiente.pk), AsientoContable.objects.get(origen_id=x.contrato.pk)
        (resolucion,) = self.registros("resolucion_suministro")
        self.assertEqual((self._registro_de_alta_del_asiento(indemnizacion).usuario_id, self._registro_de_alta_del_asiento(multa).usuario_id, resolucion.usuario_id), (self.gerente.pk, None, None))
