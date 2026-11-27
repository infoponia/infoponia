# Pruebas de CMP-REG-RCP · Registrar Recepción de Mercadería (CMP-04, paso 3): ``entregas_pendientes``, ``lineas_a_recibir``, ``resumir_recepcion`` y
# ``registrar_recepcion`` de ``compras/servicios/recepciones.py``. Fuente: docs/casos_de_uso/compras/recepcion.md (CMP-REG-RCP v0.3: precondiciones a a c, garantías
# mínimas, postcondiciones a a l, flujo básico, extensiones *a, *b, 1a, 4a, 5a a 5e, 7a a 7f, 8a, 9a, 9b, 10a y 11a, y las reglas de negocio), «Actualizaciones de A0
# que mandan» (P3: sobreentrega bloqueada; P4: tipos de inconveniente; D-89 punto 4: valorización por diferencia de valor acumulado), «Cómo se aplica (código)»,
# D-86 (asiento), D-87, D-89 y D-90, y docs/modelo/compras.md.
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   DatosDeRecepcion(orden_id, proveedor_id, invernadero_id, lineas, observaciones="")
#   LineaRecibida(detalle_orden_id, partes, inconvenientes=())      partes: [(cantidad, vencimiento | None)]; inconvenientes: [(tipo, cantidad, descripcion)]
#   entregas_pendientes(actor) -> list[EntregaPendiente(orden, proveedor, invernadero, lineas, entrega_esperada, atraso_dias, bloqueada)]   la más próxima primero
#   lineas_a_recibir(actor, orden_id, proveedor_id, invernadero_id)
#       -> list[LineaARecibir(detalle, insumo, existencia, pedida, recibida, falta, entrega_esperada, atraso_dias, motivo_bloqueo)]
#   resumir_recepcion(actor, datos) -> ResumenDeRecepcion(orden, proveedor, invernadero, lineas, estado_orden, monto_asiento, alertas_que_se_resuelven,
#                                         inconvenientes, crea_reclamo)       solo lectura; mismas precondiciones que ``registrar_recepcion``
#       lineas: list[LineaResumida(detalle, ingresa, cubre_faltante, lotes, stock_antes, stock_despues, transito_antes, transito_despues, estado_despues,
#                                  inconvenientes)]; lotes: [(cantidad, vencimiento)] de los lotes NUEVOS.
#   registrar_recepcion(actor, datos) -> Recepcion
# Quién: el Agrónomo activo a cargo del invernadero de destino o el Gerente activo (``PermissionDenied`` si no). Una orden que no existe, ``Http404``.
# Errores de negocio (``ErrorDeCompras``): orden_no_recibible (``datos["estado"]``), linea_ajena (``datos["lineas"]``), linea_no_pendiente (9a), supera_lo_pendiente
# (7a y P3; ``datos["linea"]``, ``datos["pendiente"]``), cantidad_invalida (7b), linea_en_cero_sin_inconveniente (7c), sin_lineas (7d), inconveniente_incompleto (7e),
# inconveniente_repetido (5d), vencimiento_obligatorio, vencimiento_no_aplica, vencimiento_pasado (5e) y destino_inactivo (4a y 9b; ``datos["lineas"]``).
# Los correos salen en ``on_commit`` (``captureOnCommitCallbacks``).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase, override_settings

from compras.errores import ErrorDeCompras
from compras.models import (
    AlertaCompras,
    DetalleOrdenCompra,
    DetalleRecepcion,
    DetalleRecepcionMovimiento,
    InconvenienteRecepcion,
    OrdenCompra,
    Recepcion,
    ReclamoProveedor,
)
from compras.tests.base_recepciones import BAJO_MINIMO, DANADA, TIPO_DE_ALERTA, D, RecepcionBase, recepciones
from compras.tests.fabricas import ref
from contabilidad import cuentas
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import PlanDeCuentasMixin, verificar_invariantes_contables
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_cuenta
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import alertas_de_stock, stock
from inventario.servicios.formato import texto_cantidad
from inventario.tests.fabricas import ConDatosDeInventario, faltante, perezoso, verificar_invariantes
from maestros.models import Alerta, Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_alerta, crear_vendedor

class CmpRegRcpPostcondicionesTests(RecepcionBase):
    """Postcondiciones a a l del caso de uso y el flujo básico."""

    def test_flujo_principal_registra_la_recepcion_completa_de_un_proveedor_en_un_invernadero(self):
        """Flujo básico (pasos 1 a 11): llega completa y en buen estado la mercadería de A en Norte: se crean la recepción y sus detalles, los lotes con sus movimientos, las líneas
        quedan completas, y el asiento. La orden sigue «parcialmente recibida» porque B todavía no entregó."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 20)])
        self.assertEqual(recepcion.orden_id, self.orden.pk)
        self.assertEqual(DetalleRecepcion.objects.filter(recepcion=recepcion).count(), 2)
        self.assertEqual((self.stock_de(self.fertilizante), self.stock_de(self.maceta)), (D("10"), D("20")))
        self.assertEqual((self.transito(self.fertilizante), self.transito(self.maceta)), (D("0"), D("0")))
        self.assertEqual([self.estado_de(self.l_fert), self.estado_de(self.l_maceta), self.estado_de(self.l_tomate)], ["completo", "completo", "pendiente"])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        self.assertEqual(self.movimientos_de(self.asiento_de(recepcion)), [(cuentas.INSUMOS_EN_STOCK, "D", D("300.00")), (cuentas.PROVEEDORES, "H", D("300.00"))])
        verificar_invariantes(self.fertilizante)
        verificar_invariantes(self.maceta)
        verificar_invariantes_contables()

    def test_post_a_la_recepcion_queda_con_la_fecha_de_hoy_las_observaciones_la_orden_y_el_agronomo(self):
        """Postcondición a: la recepción tiene la fecha actual y las observaciones (sin espacios de más), queda asociada a la orden, al proveedor, al invernadero y al Agrónomo
        que la registró, y es un documento de origen de tipo «recepcion»."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)], observaciones="  Llegó en dos cajas.  ")
        self.assertEqual(recepcion.fecha_recepcion, self.hoy)
        self.assertEqual(recepcion.observaciones_recepcion, "Llegó en dos cajas.")
        self.assertEqual((recepcion.orden_id, recepcion.proveedor_id, recepcion.invernadero_id), (self.orden.pk, self.proveedor.pk, self.norte.pk))
        self.assertEqual(recepcion.agronomo_id, self.ana.pk)
        self.assertEqual(recepcion.tipo, "recepcion")
        self.assertEqual(Recepcion.objects.count(), 1)

    def test_ext_1a_el_gerente_registra_la_recepcion_sin_agronomo_y_queda_en_la_auditoria(self):
        """Extensión 1a y regla «Quién registra»: si registra el Gerente, la recepción queda sin Agrónomo (R039 en 0..1) y él figura como quien actuó en el registro de auditoría."""
        recepcion = self.registrar(self.gerente, [self.linea(self.l_fert, 4, self.vence)])
        self.assertIsNone(recepcion.agronomo)
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.RECEPCION_MERCADERIA)
        self.assertEqual(registro.usuario_id, self.gerente.pk)

    def test_post_b_se_crea_un_detalle_de_recepcion_por_cada_linea_recibida_con_su_cantidad(self):
        """Postcondición b: un detalle por cada línea recibida con lo que ingresó, asociado a su línea de la orden; una línea que no llegó no tiene detalle."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        detalle = DetalleRecepcion.objects.get(recepcion=recepcion)
        self.assertEqual((detalle.detalle_orden_id, detalle.cantidad_recibida_detalle), (self.l_fert.pk, D("4")))
        self.assertFalse(DetalleRecepcion.objects.filter(detalle_orden=self.l_maceta).exists())

    def test_post_c_el_stock_sube_y_el_transito_baja_en_lo_recibido(self):
        """Postcondición c: el stock actual sube y la cantidad en tránsito baja en la cantidad recibida; una recepción parcial deja el resto en tránsito."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("4"), D("6")))

    def test_post_c_el_lote_nuevo_lleva_la_cantidad_el_ingreso_de_hoy_y_el_vencimiento(self):
        """Postcondición c: lo recibido forma un lote nuevo, con su fecha de vencimiento si el insumo la controla; un insumo que no vence forma un lote sin fecha."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 5)])
        lote = self.lotes_nuevos(self.fertilizante)[0]
        self.assertEqual((lote.cantidad_ingresada, lote.cantidad_disponible, lote.fecha_ingreso, lote.fecha_vencimiento), (D("4"), D("4"), self.hoy, self.vence))
        self.assertIsNone(self.lotes_nuevos(self.maceta)[0].fecha_vencimiento)

    def test_post_c_cada_fecha_de_vencimiento_distinta_forma_su_lote_con_su_movimiento_y_su_vinculo(self):
        """Postcondición c y regla «Lotes de la recepción»: una cantidad por cada fecha distinta, un lote nuevo por cada una y un movimiento «ingreso por recepción» por lote,
        con ``origen`` la recepción y su ``DetalleRecepcionMovimiento`` (R032, D-90 punto 3)."""
        otra = self.hoy + timedelta(days=30)
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, partes=[(D("4"), otra), (D("6"), self.vence)])])
        lotes = self.lotes_nuevos(self.fertilizante)
        self.assertEqual([(l.cantidad_disponible, l.fecha_vencimiento) for l in lotes], [(D("4"), otra), (D("6"), self.vence)])
        movimientos = list(MovimientoInsumo.objects.filter(origen_id=recepcion.pk).order_by("id"))
        self.assertEqual([(m.tipo_movimiento, m.cantidad, m.lote_insumo_id) for m in movimientos], [("ingreso_por_recepcion", D("4"), lotes[0].pk), ("ingreso_por_recepcion", D("6"), lotes[1].pk)])
        detalle = DetalleRecepcion.objects.get(recepcion=recepcion)
        self.assertEqual([v.movimiento_id for v in DetalleRecepcionMovimiento.objects.filter(detalle_recepcion=detalle).order_by("id")], [m.pk for m in movimientos])
        verificar_invariantes(self.fertilizante)

    def test_post_c_cubre_primero_el_faltante_sin_lote_y_el_resto_forma_el_lote(self):
        """Postcondición c y regla «Lotes de la recepción» (regla 4 de 8.23): lo recibido cubre primero el faltante sin lote (que queda en 0, con su movimiento y su vínculo) y el
        resto forma el lote nuevo."""
        sin_lote = faltante(self.fertilizante, 3)
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        sin_lote.refresh_from_db()
        self.assertEqual(sin_lote.cantidad_disponible, D("0"))
        self.assertEqual([l.cantidad_disponible for l in self.lotes_nuevos(self.fertilizante)], [D("7")])
        movimientos = list(MovimientoInsumo.objects.filter(origen_id=recepcion.pk).order_by("id"))
        self.assertEqual([(m.lote_insumo_id == sin_lote.pk, m.cantidad) for m in movimientos], [(True, D("3")), (False, D("7"))])
        self.assertEqual(DetalleRecepcionMovimiento.objects.filter(detalle_recepcion__recepcion=recepcion).count(), 2)
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("7"), D("0")))
        verificar_invariantes(self.fertilizante)

    def test_post_d_la_linea_pasa_a_completo_cuando_lo_recibido_acumulado_iguala_lo_pedido(self):
        """Postcondición d: la línea sigue «pendiente» mientras lo acumulado sea menor que lo pedido y pasa a «completo» al igualarlo (con dos recepciones)."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual(self.estado_de(self.l_fert), "pendiente")
        self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence)])
        self.assertEqual(self.estado_de(self.l_fert), "completo")
        self.assertEqual(DetalleRecepcion.objects.filter(detalle_orden=self.l_fert).count(), 2)

    def test_post_e_la_primera_recepcion_pone_la_orden_parcialmente_recibida(self):
        """Postcondición e y regla «Estado de la orden» (regla 24 de 8.16): con la primera recepción la orden pasa de «aprobada» a «parcialmente recibida»."""
        self.assertEqual(self.estado_de_la_orden(), "aprobada")
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")

    def test_post_e_la_orden_queda_recibida_si_todas_sus_lineas_estan_completas(self):
        """Postcondición e: con las tres líneas completas (A en Norte y B en Norte 2, dos recepciones en dos invernaderos) la orden queda «recibida»."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 20)])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        self.registrar(self.ana, [self.linea(self.l_tomate, 8)], proveedor=self.proveedor_b, invernadero=self.norte2)
        self.assertEqual(self.estado_de_la_orden(), "recibida")
        self.assertEqual((self.transito(self.fertilizante), self.transito(self.maceta), self.transito(self.tomate)), (D("0"), D("0"), D("0")))

    def test_post_e_la_orden_queda_recibida_con_faltante_si_todas_estan_completas_o_cerradas_y_una_cerrada(self):
        """Postcondición e y regla 24 de 8.16: todas las líneas completas o cerradas con faltante y al menos una cerrada: «recibida con faltante»."""
        DetalleOrdenCompra.objects.filter(pk=self.l_maceta.pk).update(estado_detalle_orden="cerrado_con_faltante", motivo_cierre_faltante="No lo consigue", fecha_cierre_faltante=self.hoy)
        InsumoInvernadero.objects.filter(pk=self.maceta.pk).update(cant_transito_insumo=0)
        DetalleOrdenCompra.objects.filter(pk=self.l_tomate.pk).update(estado_detalle_orden="completo")
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual(self.estado_de_la_orden(), "recibida_con_faltante")

    def test_post_e_una_recepcion_en_cero_igual_pone_la_orden_parcialmente_recibida_sin_ingresar_nada(self):
        """Postcondición e (regla «Estado de la orden»): la orden pasa a «parcialmente recibida» con la primera recepción **aunque no haya ingresado nada** (todo llegó dañado): la línea
        sigue pendiente, no hay lote, movimiento ni asiento (postcondición f) y el tránsito no cambia."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, inconvenientes=[(DANADA, 10, "Llegó mojado")])])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        self.assertEqual(DetalleRecepcion.objects.get(recepcion=recepcion).cantidad_recibida_detalle, D("0"))
        self.assertEqual(self.estado_de(self.l_fert), "pendiente")
        self.assertEqual((LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), self.transito(self.fertilizante)), (0, 0, D("10")))
        self.assertFalse(AsientoContable.objects.filter(origen_id=recepcion.pk).exists())
        self.assertEqual(AsientoContable.objects.count(), 0)

    def test_post_f_el_asiento_es_debe_insumos_en_stock_haber_proveedores_originado_en_la_recepcion(self):
        """Postcondición f y D-90 punto 8: Debe Insumos en Stock / Haber Proveedores por el valor recibido, con origen la recepción y la fecha de la recepción (hoy), en el ejercicio
        abierto (el que deja `iniciar_contabilidad_para_pruebas`; CON-05: ya no se crea solo, H9)."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        asiento = self.asiento_de(recepcion)
        self.assertEqual(asiento.origen_id, recepcion.pk)
        self.assertEqual(asiento.fecha_asiento, self.hoy)
        self.assertEqual(asiento.ejercicio.estado_ejercicio, "abierto")
        self.assertEqual(self.movimientos_de(asiento), [(cuentas.INSUMOS_EN_STOCK, "D", D("40.00")), (cuentas.PROVEEDORES, "H", D("40.00"))])
        verificar_invariantes_contables()

    def test_post_f_el_asiento_suma_el_valor_de_todas_las_lineas_recibidas(self):
        """Postcondición f y D-89 punto 4: un solo asiento con la suma del valor recibido de cada línea (4 kg a $10 + 5 unidades a $10 = $90) y las decimales de la unidad (3,333 kg a
        $10 = $33,33)."""
        primera = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 5)])
        self.assertEqual(self.movimientos_de(self.asiento_de(primera))[0], (cuentas.INSUMOS_EN_STOCK, "D", D("90.00")))
        segunda = self.registrar(self.ana, [self.linea(self.l_fert, D("3.333"), self.vence)])
        self.assertEqual(self.movimientos_de(self.asiento_de(segunda))[0], (cuentas.INSUMOS_EN_STOCK, "D", D("33.33")))
        verificar_invariantes_contables()

    def test_post_g_recibir_resuelve_la_alerta_de_bajo_el_minimo_si_el_insumo_deja_de_estarlo(self):
        """Postcondición g y reglas 11 y 12 de 8.15: la alerta de «bajo el mínimo» (que seguía activa desde antes de aprobar la orden) se resuelve, con su fecha, si después de recibir el
        insumo deja de estar bajo el mínimo (libre + tránsito ≥ mínimo); las demás siguen activas."""
        InsumoInvernadero.objects.filter(pk=self.fertilizante.pk).update(cant_min_insumo=10)
        alerta = crear_alerta(self.norte, BAJO_MINIMO, clave_estado=f"insumo:{self.fertilizante.pk}")
        otra = crear_alerta(self.norte, BAJO_MINIMO, clave_estado=f"insumo:{self.maceta.pk}")
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        alerta.refresh_from_db()
        otra.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(alerta.fecha_resolucion)
        self.assertEqual(otra.estado_alerta, "activa")

    def test_post_h_el_proveedor_recibe_un_correo_con_lo_recibido_lo_no_aceptado_y_lo_pendiente(self):
        """Postcondición h y lista de tecnología 10: un correo al proveedor con la orden, la fecha, el invernadero de destino y, por línea, lo recibido y lo no aceptado por daño; las líneas
        que siguen pendientes, con lo que falta. No menciona al otro proveedor."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "")])])
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, [self.proveedor.email_proveedor])
        self.assertIn(str(self.orden), correo.subject)
        for texto in (str(self.orden), "Norte", f"{self.hoy:%d/%m/%Y}", "Fertilizante", texto_cantidad(D("4"), "kg"), texto_cantidad(D("2"), "kg"), "Maceta"):
            self.assertIn(texto, correo.body)
        self.assertNotIn(self.proveedor_b.nombre_para_mostrar, correo.body)
        self.assertNotIn("Tomate", correo.body)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_ext_10a_si_el_correo_no_sale_la_recepcion_queda_registrada(self):
        """Extensión 10a: si no se logra enviar el correo al proveedor, la recepción permanece registrada (el correo sale fuera de la transacción)."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertTrue(Recepcion.objects.filter(pk=recepcion.pk).exists())
        self.assertEqual(self.stock_de(self.fertilizante), D("4"))

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_10a_sin_el_correo_configurado_no_sale_nada_y_la_recepcion_se_registra(self):
        """Requisito especial («el correo se envía fuera de la transacción») y D-33: sin el correo configurado no sale ningún correo y la recepción se registra igual."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Recepcion.objects.count(), 1)

    # --- inconvenientes (postcondiciones i a k) ---

    def test_post_i_cada_inconveniente_queda_con_su_tipo_cantidad_y_descripcion_en_su_linea(self):
        """Postcondición i y extensiones 5a y 5c: un inconveniente por cada uno declarado, con su tipo, cantidad afectada y descripción, asociado al detalle de su recepción; a lo sumo uno de cada tipo
        por línea. La cantidad afectada no se limita a lo que ingresó (lo dañado no cuenta como recibido)."""
        recepcion = self.registrar(
            self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 6, "Cajas aplastadas"), ("otro", 1, "Falta la ficha técnica")])]
        )
        detalle = DetalleRecepcion.objects.get(recepcion=recepcion)
        self.assertEqual(
            list(InconvenienteRecepcion.objects.filter(detalle_recepcion=detalle).order_by("id").values_list("tipo_inconveniente", "cantidad_afectada", "descripcion_inconveniente")),
            [(DANADA, D("6"), "Cajas aplastadas"), ("otro", D("1"), "Falta la ficha técnica")],
        )

    def test_post_j_el_reclamo_nace_abierto_y_sin_emitir_y_agrupa_todos_los_inconvenientes_de_la_recepcion(self):
        """Postcondición j y regla «Reclamo sin emitir»: un reclamo «abierto», sin Gerente y sin fecha de emisión, del proveedor, que agrupa los inconvenientes de todas las líneas de la recepción."""
        recepcion = self.registrar(
            self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "")]), self.linea(self.l_maceta, 5, inconvenientes=[("calidad_no_conforme", 1, "")])]
        )
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual((reclamo.recepcion_id, reclamo.proveedor_id, reclamo.estado_reclamo), (recepcion.pk, self.proveedor.pk, "abierto"))
        self.assertEqual((reclamo.gerente, reclamo.fecha_reclamo), (None, None))
        self.assertEqual(reclamo.inconvenientes.count(), 2)
        self.assertEqual(InconvenienteRecepcion.objects.filter(reclamo=reclamo).count(), InconvenienteRecepcion.objects.count())

    def test_post_k_la_alerta_para_el_gerente_es_activa_y_no_leida_e_identifica_la_recepcion(self):
        """Postcondición k, 7f y lista de tecnología 7f: una alerta para el Gerente (D-87 punto 5: tipo «recepción con inconvenientes», de evento), activa y no leída, que identifica la
        recepción, el proveedor, el invernadero, el reclamo sin emitir y la cantidad de inconvenientes por tipo, con su ``AlertaCompras`` al reclamo."""
        recepcion = self.registrar(
            self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, ""), ("otro", 1, "Etiqueta equivocada")])]
        )
        alerta = Alerta.objects.get(tipo_alerta=TIPO_DE_ALERTA)
        self.assertEqual((alerta.estado_alerta, alerta.estado_lectura_alerta, alerta.para_gerente, alerta.invernadero_id), ("activa", "no_leida", True, self.norte.pk))
        self.assertEqual(alerta.nivel_severidad, "advertencia")
        self.assertIsNone(alerta.clave_estado)
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual(alerta.vinculo_de_compras.reclamo_id, reclamo.pk)
        descripcion = alerta.descripcion_alerta.lower()
        for texto in (str(recepcion), self.proveedor.nombre_para_mostrar, "Norte", str(reclamo), "mercadería dañada", "otro"):
            self.assertIn(texto.lower(), descripcion)

    def test_post_sin_inconvenientes_no_hay_reclamo_ni_alerta_ni_vinculo(self):
        """Postcondiciones i a k son «si se declararon inconvenientes»: sin ninguno no se crea reclamo, inconveniente, alerta ni ``AlertaCompras``."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence)])
        self.assertEqual((ReclamoProveedor.objects.count(), InconvenienteRecepcion.objects.count(), AlertaCompras.objects.count(), Alerta.objects.filter(tipo_alerta=TIPO_DE_ALERTA).count()), (0, 0, 0, 0))

    # --- auditoría (postcondición l) ---

    def test_post_l_un_registro_de_auditoria_nombra_todo_lo_que_la_recepcion_creo_o_modifico(self):
        """Postcondición l y D-36: un registro ``recepcion_mercaderia`` de quien actuó que nombra entre sus afectados la recepción, su detalle, la línea de la orden, la orden, el inconveniente y el reclamo;
        el cambio de estado de la orden va en ``cambios`` y el asiento, los lotes y los movimientos, en ``datos``."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "")])])
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.RECEPCION_MERCADERIA)
        self.assertEqual(registro.usuario_id, self.ana.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {
            ("compras.recepcion", recepcion.pk),
            ("compras.detallerecepcion", DetalleRecepcion.objects.get().pk),
            ("compras.detalleordencompra", self.l_fert.pk),
            ("compras.ordencompra", self.orden.pk),
            ("compras.inconvenienterecepcion", InconvenienteRecepcion.objects.get().pk),
            ("compras.reclamoproveedor", ReclamoProveedor.objects.get().pk),
        }
        self.assertLessEqual(esperados, afectados)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "aprobada", "despues": "parcialmente_recibida"})
        self.assertEqual(registro.detalle["datos"]["asiento"], ref(self.asiento_de(recepcion)))
        self.assertEqual(registro.detalle["datos"]["movimientos"], [ref(m) for m in MovimientoInsumo.objects.filter(origen_id=recepcion.pk)])

    def test_post_l_cada_insumo_del_invernadero_modificado_tiene_su_registro_con_el_transito_antes_y_despues(self):
        """Postcondición l y D-87 punto 8: una ``modificacion_insumo_invernadero`` por cada existencia recibida, con la cantidad en tránsito antes y después."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 5)])
        registros = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO).order_by("id")
        por_insumo = {r.afectados[0]["id"]: r.detalle["cambios"]["transito"] for r in registros if r.afectados[0]["modelo"] == "inventario.insumoinvernadero"}
        self.assertEqual(por_insumo[self.fertilizante.pk], {"antes": "10.000", "despues": "6.000"})
        self.assertEqual(por_insumo[self.maceta.pk], {"antes": "20", "despues": "15"})

    def test_post_l_el_asiento_lo_audita_la_funcion_de_asientos_y_no_la_recepcion(self):
        """D-86 punto 4: la función de asientos audita el asiento y cada movimiento; la recepción no los vuelve a auditar (un ``alta_asiento_contable`` y dos ``alta_movimiento_contable``)."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        acciones = RegistroAuditoria.Accion
        self.assertEqual(RegistroAuditoria.objects.filter(accion=acciones.ALTA_ASIENTO_CONTABLE).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=acciones.ALTA_MOVIMIENTO_CONTABLE).count(), 2)


class CmpRegRcpReglasTests(RecepcionBase):
    """Reglas de negocio, precondiciones y extensiones de error. Cada una verifica que, al rechazar, no cambió nada."""

    def test_regla_quien_registra_es_el_agronomo_a_cargo_del_invernadero_de_destino_o_el_gerente(self):
        """Regla «Quién registra» y precondición a: solo el Agrónomo activo a cargo del destino y el Gerente activo; otro Agrónomo, otros roles, una cuenta inactiva o sin cuenta: ``PermissionDenied``."""
        antes = self.instantanea()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        inactiva = crear_agronomo(email="baja@infoponia.com", activo=False)
        for actor in (self.beto, crear_capataz(), crear_vendedor(), crear_administrador(), contador, inactiva, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    recepciones.registrar_recepcion(actor, self.datos([self.linea(self.l_fert, 4, self.vence)]))
        self.sin_cambios(antes)

    def test_regla_el_agronomo_de_otro_invernadero_de_la_misma_orden_no_registra_la_recepcion(self):
        """Regla «Quién registra»: el Agrónomo es el del invernadero de DESTINO de la recepción: Ana, a cargo de Norte y Norte 2, registra las dos entregas; Beto (Sur) ninguna."""
        self.registrar(self.ana, [self.linea(self.l_tomate, 8)], proveedor=self.proveedor_b, invernadero=self.norte2)
        with self.assertRaises(PermissionDenied):
            recepciones.registrar_recepcion(self.beto, self.datos([self.linea(self.l_fert, 4, self.vence)]))

    def test_regla_una_recepcion_que_apunta_a_una_orden_que_no_existe_es_404(self):
        """Una orden que no existe: ``Http404`` (D-28)."""
        datos = recepciones.DatosDeRecepcion(999999, self.proveedor.pk, self.norte.pk, [self.linea(self.l_fert, 4, self.vence)])
        with self.assertRaises(Http404):
            recepciones.registrar_recepcion(self.ana, datos)

    def test_regla_7_de_8_20_una_recepcion_es_de_una_orden_un_proveedor_y_un_invernadero(self):
        """Regla 7 de 8.20 (R019): todas las líneas son de esa orden, de ese proveedor y de ese invernadero; una de otro proveedor, de otro invernadero o de otra orden es ``linea_ajena`` y no cambia nada.
        Una prueba verifica que lo registrado es coherente con sus líneas."""
        orden_b, linea_b, _ = self.otra_orden(self.ana, self.norte2, "Sustrato")
        antes = self.instantanea()
        for lineas, kwargs in (
            ([self.linea(self.l_tomate, 4)], {}),  # el proveedor B en Norte 2, declarado como A en Norte
            ([self.linea(self.l_fert, 4, self.vence), self.linea(self.l_tomate, 4)], {}),  # una línea de B mezclada con las de A
            ([self.linea(self.l_fert, 4, self.vence)], {"invernadero": self.norte2}),  # el invernadero declarado no es el de la línea
            ([self.linea(linea_b, 2)], {}),  # una línea de otra orden
        ):
            with self.subTest(lineas=lineas, kwargs=kwargs):
                self.assertEqual(self.error(self.ana, lineas, **kwargs).codigo, "linea_ajena")
        self.sin_cambios(antes)
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 5)])
        for detalle in DetalleRecepcion.objects.filter(recepcion=recepcion).select_related("detalle_orden__detalle_cotizacion__cotizacion", "detalle_orden__detalle_cotizacion__detalle_pedido__insumo_invernadero"):
            self.assertEqual(detalle.detalle_orden.orden_id, recepcion.orden_id)
            self.assertEqual(detalle.detalle_orden.proveedor.pk, recepcion.proveedor_id)
            self.assertEqual(detalle.detalle_orden.detalle_pedido.insumo_invernadero.invernadero_id, recepcion.invernadero_id)

    def test_regla_8_de_8_20_la_orden_debe_estar_aprobada_o_parcialmente_recibida(self):
        """Regla 8 de 8.20 y precondición b: una orden pendiente de aprobación, rechazada, recibida o recibida con faltante no se recibe (``orden_no_recibible``, con su estado)."""
        antes = self.instantanea()
        for estado in ("recibida", "recibida_con_faltante"):
            OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra=estado)
            with self.subTest(estado=estado):
                error = self.error(self.ana, [self.linea(self.l_fert, 4, self.vence)])
                self.assertEqual((error.codigo, error.datos["estado"]), ("orden_no_recibible", estado))
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="pendiente_aprobacion", gerente=None, fecha_resolucion=None)
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4, self.vence)]).codigo, "orden_no_recibible")
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="aprobada", gerente=self.gerente, fecha_resolucion=self.hoy)
        self.assertEqual(self.estado_de_la_orden(), "aprobada")
        self.assertEqual(antes[:11], self.instantanea()[:11])

    def test_ext_9a_una_linea_que_ya_no_esta_pendiente_no_se_recibe(self):
        """Extensión 9a y regla «Línea recibible»: una línea ya completa o cerrada con faltante (otro usuario la recibió o la cerró) no se recibe: ``linea_no_pendiente``, sin cambios."""
        antes = self.instantanea()
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(estado_detalle_orden="completo")
        error = self.error(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual((error.codigo, error.datos["linea"]), ("linea_no_pendiente", self.l_fert.pk))
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(estado_detalle_orden="cerrado_con_faltante", motivo_cierre_faltante="No llega", fecha_cierre_faltante=self.hoy)
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4, self.vence)]).codigo, "linea_no_pendiente")
        self.assertEqual(antes[:11], self.instantanea()[:11])

    def test_ext_7a_la_cantidad_recibida_no_supera_lo_que_falta_recibir(self):
        """Extensión 7a y P3 (D-90 punto 6): una cantidad que supera lo que falta recibir se rechaza (``supera_lo_pendiente``, con la línea y lo que falta); el excedente no se ingresa. Con lo ya
        recibido de otra recepción (9a: «lo que falta cambió») se calcula contra lo que falta ahora. Recibir exactamente lo que falta sí se puede."""
        antes = self.instantanea()
        error = self.error(self.ana, [self.linea(self.l_fert, 11, self.vence)])
        self.assertEqual((error.codigo, error.datos["linea"], error.datos["pendiente"]), ("supera_lo_pendiente", self.l_fert.pk, D("10")))
        self.sin_cambios(antes)
        self.registrar(self.ana, [self.linea(self.l_fert, 8, self.vence)])
        error = self.error(self.ana, [self.linea(self.l_fert, 3, self.vence)])
        self.assertEqual((error.codigo, error.datos["pendiente"]), ("supera_lo_pendiente", D("2")))
        self.registrar(self.ana, [self.linea(self.l_fert, 2, self.vence)])
        self.assertEqual(self.estado_de(self.l_fert), "completo")

    def test_ext_7b_una_cantidad_negativa_o_con_decimales_que_la_unidad_no_admite_se_rechaza(self):
        """Extensión 7b y regla 2 de 8.23 (D-87 punto 7): la cantidad es mayor que cero y con los decimales de la unidad (el kg admite tres; la unidad, ninguno); ``cantidad_invalida``."""
        antes = self.instantanea()
        for detalle, cantidad, vence in ((self.l_fert, "-1", self.vence), (self.l_fert, "0.0005", self.vence), (self.l_fert, "0", self.vence), (self.l_maceta, "1.5", None)):
            with self.subTest(cantidad=cantidad):
                linea = recepciones.LineaRecibida(detalle.pk, [(D(cantidad), vence)], [])
                with self.assertRaises(ErrorDeCompras) as contexto:
                    recepciones.registrar_recepcion(self.ana, self.datos([linea]))
                self.assertEqual(contexto.exception.codigo, "cantidad_invalida")
        self.sin_cambios(antes)

    def test_ext_7c_una_linea_en_cero_solo_se_registra_con_un_inconveniente_que_no_sea_otro(self):
        """Extensión 7c y regla «Cantidad recibida» (P4: la 7c acepta 0 con cualquier inconveniente que no sea «otro»): una línea en 0 sin inconveniente, o solo con «otro», se rechaza
        (``linea_en_cero_sin_inconveniente``); con un daño se registra."""
        antes = self.instantanea()
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert)]).codigo, "linea_en_cero_sin_inconveniente")
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, inconvenientes=[("otro", 3, "No era lo pedido")])]).codigo, "linea_en_cero_sin_inconveniente")
        self.sin_cambios(antes)
        self.registrar(self.ana, [self.linea(self.l_fert, inconvenientes=[("producto_distinto", 3, "")])])
        self.assertEqual(DetalleRecepcion.objects.get().cantidad_recibida_detalle, D("0"))

    def test_ext_7d_la_recepcion_incluye_al_menos_una_linea(self):
        """Extensión 7d: una recepción sin ninguna línea se rechaza (``sin_lineas``)."""
        antes = self.instantanea()
        self.assertEqual(self.error(self.ana, []).codigo, "sin_lineas")
        self.sin_cambios(antes)

    def test_ext_7e_un_inconveniente_incompleto_se_rechaza(self):
        """Extensión 7e: un inconveniente con cantidad afectada no mayor que cero, o de tipo «otro» sin descripción, está incompleto (``inconveniente_incompleto``)."""
        antes = self.instantanea()
        for inconveniente in ((DANADA, 0, ""), (DANADA, -1, ""), ("otro", 2, ""), ("otro", 2, "   ")):
            with self.subTest(inconveniente=inconveniente):
                self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[inconveniente])]).codigo, "inconveniente_incompleto")
        self.sin_cambios(antes)

    def test_ext_5d_una_linea_tiene_a_lo_sumo_un_inconveniente_de_cada_tipo(self):
        """Extensión 5d: declarar dos inconvenientes del mismo tipo en una línea se rechaza (``inconveniente_repetido``); de tipos distintos, sí."""
        antes = self.instantanea()
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 1, ""), (DANADA, 2, "")])]).codigo, "inconveniente_repetido")
        self.sin_cambios(antes)
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 1, ""), ("calidad_no_conforme", 2, "")])])
        self.assertEqual(InconvenienteRecepcion.objects.count(), 2)

    def test_ext_5a_lo_danado_no_cuenta_como_recibido_y_la_linea_sigue_pendiente_por_esa_cantidad(self):
        """Extensión 5a y regla «Inconvenientes»: lo dañado no ingresa al stock ni al asiento y la línea sigue pendiente por esa cantidad (el proveedor puede reponerlo): llegaron 6, 4 dañados:
        ingresan 6 y faltan 4; la reposición de 4 la completa."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence, inconvenientes=[(DANADA, 4, "")])])
        self.assertEqual((self.stock_de(self.fertilizante), self.estado_de(self.l_fert), self.transito(self.fertilizante)), (D("6"), "pendiente", D("4")))
        self.assertEqual(self.movimientos_de(self.asiento_de(recepcion))[0][2], D("60.00"))
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual(self.estado_de(self.l_fert), "completo")

    def test_ext_5e_un_vencimiento_anterior_a_hoy_no_es_un_ingreso(self):
        """Extensión 5e y «Cómo se aplica»: la pantalla convierte lo vencido en un inconveniente; el servicio rechaza un ingreso con vencimiento pasado (``vencimiento_pasado``). El día del
        vencimiento todavía se usa: un lote que vence hoy ingresa."""
        antes = self.instantanea()
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4, self.hoy - timedelta(days=1))]).codigo, "vencimiento_pasado")
        self.sin_cambios(antes)
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.hoy)])
        self.assertEqual(self.lotes_nuevos(self.fertilizante)[0].fecha_vencimiento, self.hoy)

    def test_regla_el_vencimiento_es_obligatorio_si_el_insumo_lo_controla_y_no_va_si_no_lo_controla(self):
        """Paso 5 y regla «Lotes de la recepción»: un insumo que controla el vencimiento necesita la fecha de cada parte (``vencimiento_obligatorio``); uno que no lo controla no lleva fecha
        (``vencimiento_no_aplica``)."""
        antes = self.instantanea()
        self.assertEqual(self.error(self.ana, [self.linea(self.l_fert, 4)]).codigo, "vencimiento_obligatorio")
        self.assertEqual(self.error(self.ana, [self.linea(self.l_maceta, 4, self.vence)]).codigo, "vencimiento_no_aplica")
        self.sin_cambios(antes)

    def test_ext_4a_y_9b_una_linea_de_un_invernadero_o_un_insumo_inactivo_no_se_recibe(self):
        """Extensiones 4a y 9b y regla «Destino inactivo»: una línea de un invernadero inactivo (``invernadero_inactivo``) o de un insumo inactivo en él (``insumo_inactivo``) no se recibe; el error
        trae ``datos["lineas"]`` con cada línea afectada y su motivo, y no cambia nada."""
        antes = self.instantanea()
        InsumoInvernadero.objects.filter(pk=self.maceta.pk).update(estado_insumo_invernadero="inactivo")
        error = self.error(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 5)])
        self.assertEqual((error.codigo, error.datos["lineas"]), ("destino_inactivo", [(self.l_maceta.pk, "insumo_inactivo")]))
        Invernadero.objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")
        error = self.error(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.assertEqual((error.codigo, error.datos["lineas"]), ("destino_inactivo", [(self.l_fert.pk, "invernadero_inactivo")]))
        self.sin_cambios(antes)

    def test_regla_la_recepcion_no_cambia_lo_pedido_ni_el_precio_ni_la_fecha_esperada_ni_el_precio_de_referencia(self):
        """«Además»: no se modifica la cantidad pedida, el total (precio) ni la fecha de entrega esperada de ningún detalle de la orden, ni el precio de referencia del insumo (regla 6 de 8.18)."""
        antes = list(DetalleOrdenCompra.objects.order_by("id").values_list("cantidad_detalle_orden", "total_linea", "fecha_entrega_esperada"))
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 5)])
        self.assertEqual(list(DetalleOrdenCompra.objects.order_by("id").values_list("cantidad_detalle_orden", "total_linea", "fecha_entrega_esperada")), antes)
        self.assertEqual(InsumoInvernadero.objects.get(pk=self.fertilizante.pk).referencia_precio, D("10.00"))


class CmpRegRcpValorizacionYTodoONadaTests(RecepcionBase):
    """D-89 punto 4 (el asiento como diferencia de valor acumulado) y la garantía mínima «atómico»."""

    def test_d89_tres_recepciones_parciales_suman_exactamente_el_total_de_la_linea(self):
        """D-89 punto 4 («Proveedores en cero»): tres recepciones de 1 sobre una línea de 3 por $100,00 ($33,3333 la unidad) asientan $33,33, $33,34 y $33,33: la suma es exactamente el total
        de la línea, sin un centavo colgado en Proveedores."""
        orden, linea, iin = self.otra_orden(self.ana, self.norte, "Abono", cantidad=3, total="100.00", n=3)
        asientos = []
        for _ in range(3):
            with self.captureOnCommitCallbacks(execute=True):
                datos = recepciones.DatosDeRecepcion(orden.pk, linea.proveedor.pk, self.norte.pk, [self.linea(linea, 1)])
                asientos.append(self.asiento_de(recepciones.registrar_recepcion(self.ana, datos)))
        importes = [self.movimientos_de(a)[0][2] for a in asientos]
        self.assertEqual(importes, [D("33.33"), D("33.34"), D("33.33")])
        self.assertEqual(sum(importes), D("100.00"))
        haber = sum(m[2] for a in asientos for m in self.movimientos_de(a) if m[:2] == (cuentas.PROVEEDORES, "H"))
        self.assertEqual(haber, linea.total_linea)
        verificar_invariantes_contables()

    def test_d89_el_valor_de_dos_recepciones_de_una_linea_es_el_de_lo_acumulado(self):
        """D-89 punto 4: el valor de cada recepción es ``valor_recibido(acumulado después) − valor_recibido(acumulado antes)``; si se recibe todo, el total guardado de la línea."""
        primera = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        segunda = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence)])
        self.assertEqual([self.movimientos_de(a)[0][2] for a in (self.asiento_de(primera), self.asiento_de(segunda))], [D("40.00"), D("60.00")])
        self.assertEqual(sum(self.movimientos_de(self.asiento_de(r))[0][2] for r in (primera, segunda)), self.l_fert.total_linea)

    def test_regla_todo_o_nada_si_falla_el_asiento_no_queda_ningun_registro_de_la_recepcion(self):
        """Garantías mínimas y «el registro es atómico»: si el asiento (lo último que se hace) falla, no queda recepción, detalle, lote, movimiento, vínculo, inconveniente, reclamo, alerta,
        asiento ni registro de auditoría; no cambian el stock, el tránsito ni los estados, y no sale ningún correo."""
        antes = self.instantanea()
        lineas = [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "")]), self.linea(self.l_maceta, 5)]
        with mock.patch("contabilidad.servicios.asientos.registrar_asiento_automatico", side_effect=RuntimeError("falla del asiento")):
            with self.assertRaises(RuntimeError):
                with self.captureOnCommitCallbacks(execute=True):
                    recepciones.registrar_recepcion(self.ana, self.datos(lineas))
        self.sin_cambios(antes)

    def test_regla_todo_o_nada_el_asiento_se_pide_una_sola_vez_y_despues_de_todo_lo_demas(self):
        """D-86 punto 2 y «Cómo se aplica»: el asiento va **por último**: cuando se lo pide, la recepción, sus lotes, el reclamo y la alerta ya están creados (y el ejercicio se bloquea después de todo)."""
        vistos = {}
        real = servicio_de_asientos.registrar_asiento_automatico

        def espiar(*args, **kwargs):
            vistos.update(
                recepciones=Recepcion.objects.count(), lotes=LoteInsumo.objects.count(), reclamos=ReclamoProveedor.objects.count(),
                alertas=Alerta.objects.filter(tipo_alerta=TIPO_DE_ALERTA).count(), estado=self.estado_de_la_orden(),
            )
            return real(*args, **kwargs)

        with mock.patch("contabilidad.servicios.asientos.registrar_asiento_automatico", side_effect=espiar) as llamadas:
            self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence, inconvenientes=[(DANADA, 2, "")])])
        self.assertEqual(llamadas.call_count, 1)
        self.assertEqual(vistos, {"recepciones": 1, "lotes": 1, "reclamos": 1, "alertas": 1, "estado": "parcialmente_recibida"})


class CmpRegRcpConsultasTests(RecepcionBase):
    """Pasos 2 a 4 y 7 del flujo: las entregas pendientes, las líneas de una entrega y el resumen. Ninguna escribe."""

    def test_paso_2_el_agronomo_ve_las_entregas_de_sus_invernaderos_agrupadas_por_proveedor_e_invernadero(self):
        """Paso 2: las entregas pendientes de los invernaderos a cargo del Agrónomo, agrupadas por proveedor e invernadero, de la fecha de entrega esperada más próxima a la más lejana:
        con la orden, la cantidad de líneas pendientes, la entrega más próxima y los días de atraso. B en Norte 2 (2 días) va antes que A en Norte (3 y 5 días)."""
        entregas = recepciones.entregas_pendientes(self.ana)
        self.assertEqual([(e.proveedor.pk, e.invernadero.pk, len(e.lineas)) for e in entregas], [(self.proveedor_b.pk, self.norte2.pk, 1), (self.proveedor.pk, self.norte.pk, 2)])
        self.assertEqual([(e.orden.pk, e.entrega_esperada, e.atraso_dias, e.bloqueada) for e in entregas], [(self.orden.pk, self.hoy + timedelta(days=d), 0, False) for d in (2, 3)])

    def test_ext_1a_el_gerente_ve_las_entregas_de_todos_los_invernaderos_y_un_agronomo_sin_destinos_ninguna(self):
        """Extensión 1a (paso 2): el Gerente ve las de todos los invernaderos; Beto, a cargo de Sur, no ve ninguna de esta orden."""
        self.otra_orden(self.beto, self.sur, "Sustrato")
        self.assertEqual(len(recepciones.entregas_pendientes(self.gerente)), 3)
        self.assertEqual([e.invernadero.pk for e in recepciones.entregas_pendientes(self.beto)], [self.sur.pk])

    def test_paso_2_una_linea_atrasada_marca_los_dias_de_atraso_y_la_entrega_mas_proxima(self):
        """Paso 2 y regla «Retraso» (regla 23 de 8.16): una línea atrasada si hoy es posterior a su fecha de entrega esperada; los días de atraso son la diferencia (el mayor del grupo)."""
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(fecha_entrega_esperada=self.hoy - timedelta(days=4))
        entrega = next(e for e in recepciones.entregas_pendientes(self.ana) if e.proveedor.pk == self.proveedor.pk)
        self.assertEqual((entrega.atraso_dias, entrega.entrega_esperada), (4, self.hoy - timedelta(days=4)))

    def test_paso_2_solo_las_ordenes_aprobadas_o_parcialmente_recibidas_con_lineas_pendientes(self):
        """Regla «Línea recibible»: las líneas completas o cerradas con faltante y las órdenes en otros estados no aparecen; un grupo sin líneas pendientes desaparece."""
        DetalleOrdenCompra.objects.filter(pk__in=[self.l_fert.pk, self.l_maceta.pk]).update(estado_detalle_orden="completo")
        self.assertEqual([e.proveedor.pk for e in recepciones.entregas_pendientes(self.ana)], [self.proveedor_b.pk])
        OrdenCompra.objects.filter(pk=self.orden.pk).update(estado_orden_compra="recibida")
        self.assertEqual(recepciones.entregas_pendientes(self.ana), [])

    def test_ext_4a1_una_entrega_con_todo_el_destino_inactivo_se_marca_bloqueada(self):
        """Extensión 4a1: si todas las líneas pendientes de la entrega tienen el destino inactivo, la entrega se muestra bloqueada (la pantalla informa que primero hay que reactivarlo)."""
        Invernadero.objects.filter(pk=self.norte2.pk).update(estado_invernadero="inactivo")
        por_proveedor = {e.proveedor.pk: e for e in recepciones.entregas_pendientes(self.ana)}
        self.assertTrue(por_proveedor[self.proveedor_b.pk].bloqueada)
        self.assertFalse(por_proveedor[self.proveedor.pk].bloqueada)

    def test_regla_solo_el_agronomo_y_el_gerente_ven_las_entregas(self):
        """Precondición a: otros roles, una cuenta inactiva o sin cuenta: ``PermissionDenied``."""
        for actor in (crear_capataz(), crear_vendedor(), crear_cuenta(Contador, email="contador@infoponia.com"), crear_agronomo(email="baja@infoponia.com", activo=False), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    recepciones.entregas_pendientes(actor)

    def test_paso_4_las_lineas_pendientes_de_la_entrega_traen_lo_pedido_lo_recibido_y_lo_que_falta(self):
        """Paso 4: por cada línea pendiente de esa orden, proveedor e invernadero: el insumo y su unidad, lo pedido, lo ya recibido y lo que falta, la entrega esperada y los días de atraso."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        DetalleOrdenCompra.objects.filter(pk=self.l_maceta.pk).update(fecha_entrega_esperada=self.hoy - timedelta(days=2))
        lineas = recepciones.lineas_a_recibir(self.ana, self.orden.pk, self.proveedor.pk, self.norte.pk)
        self.assertEqual([l.detalle.pk for l in lineas], [self.l_fert.pk, self.l_maceta.pk])
        fert, maceta = lineas
        self.assertEqual((fert.insumo.nombre_insumo, fert.pedida, fert.recibida, fert.falta, fert.atraso_dias, fert.motivo_bloqueo), ("Fertilizante", D("10"), D("4"), D("6"), 0, None))
        self.assertEqual((maceta.pedida, maceta.recibida, maceta.falta, maceta.atraso_dias, maceta.entrega_esperada), (D("20"), D("0"), D("20"), 2, self.hoy - timedelta(days=2)))

    def test_ext_4a_una_linea_de_un_destino_inactivo_se_lista_sin_permitir_recibirla(self):
        """Extensión 4a: la línea de un insumo inactivo (o de un invernadero inactivo) aparece con su motivo, sin que se le pueda indicar cantidad (la pantalla la bloquea con ``motivo_bloqueo``)."""
        InsumoInvernadero.objects.filter(pk=self.maceta.pk).update(estado_insumo_invernadero="inactivo")
        fert, maceta = recepciones.lineas_a_recibir(self.ana, self.orden.pk, self.proveedor.pk, self.norte.pk)
        self.assertEqual((fert.motivo_bloqueo, maceta.motivo_bloqueo), (None, "insumo_inactivo"))

    def test_paso_4_las_lineas_de_una_entrega_respetan_el_alcance_y_la_existencia(self):
        """Regla «Quién registra»: Beto no ve las líneas de Norte (``PermissionDenied``); una orden inexistente, ``Http404``."""
        with self.assertRaises(PermissionDenied):
            recepciones.lineas_a_recibir(self.beto, self.orden.pk, self.proveedor.pk, self.norte.pk)
        with self.assertRaises(Http404):
            recepciones.lineas_a_recibir(self.ana, 999999, self.proveedor.pk, self.norte.pk)

    def test_paso_7_el_resumen_dice_lo_que_ingresa_los_lotes_el_asiento_el_estado_de_la_linea_y_de_la_orden(self):
        """Paso 7: por línea, lo que ingresa al stock, los lotes en que ingresa (primero el faltante sin lote) y cómo cambian el stock y el tránsito; el estado en que quedará cada línea y la
        orden; el monto del asiento; las alertas de bajo el mínimo que se resolverán y los inconvenientes, con el reclamo sin emitir. No escribe nada."""
        faltante(self.fertilizante, 3)
        InsumoInvernadero.objects.filter(pk=self.fertilizante.pk).update(cant_min_insumo=7)  # libre −3 + tránsito 10 = 7: ya no está bajo el mínimo
        alerta = crear_alerta(self.norte, BAJO_MINIMO, clave_estado=f"insumo:{self.fertilizante.pk}")
        antes = self.instantanea()
        resumen = recepciones.resumir_recepcion(self.ana, self.datos([self.linea(self.l_fert, 10, self.vence, inconvenientes=[(DANADA, 2, "")])]))
        self.assertEqual(self.instantanea(), antes)
        (linea,) = resumen.lineas
        self.assertEqual((linea.detalle.pk, linea.ingresa, linea.cubre_faltante, linea.lotes), (self.l_fert.pk, D("10"), D("3"), [(D("7"), self.vence)]))
        self.assertEqual((linea.stock_antes, linea.stock_despues, linea.transito_antes, linea.transito_despues), (D("-3"), D("7"), D("10"), D("0")))
        self.assertEqual((linea.estado_despues, resumen.estado_orden, resumen.monto_asiento, resumen.crea_reclamo), ("completo", "parcialmente_recibida", D("100.00"), True))
        self.assertEqual([i[0] for i in linea.inconvenientes], [DANADA])
        self.assertEqual([a.pk for a in resumen.alertas_que_se_resuelven], [alerta.pk])

    def test_paso_7_el_resumen_aplica_las_mismas_validaciones_que_el_registro(self):
        """Paso 7: el resumen verifica los datos como el registro (``supera_lo_pendiente``, ``vencimiento_obligatorio``, permisos) y no escribe; sin inconvenientes, ``crea_reclamo`` es falso."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            recepciones.resumir_recepcion(self.ana, self.datos([self.linea(self.l_fert, 11, self.vence)]))
        self.assertEqual(contexto.exception.codigo, "supera_lo_pendiente")
        with self.assertRaises(PermissionDenied):
            recepciones.resumir_recepcion(self.beto, self.datos([self.linea(self.l_fert, 4, self.vence)]))
        resumen = recepciones.resumir_recepcion(self.ana, self.datos([self.linea(self.l_fert, 4, self.vence)]))
        self.assertFalse(resumen.crea_reclamo)
        self.assertEqual((resumen.lineas[0].estado_despues, resumen.monto_asiento), ("pendiente", D("40.00")))
        self.assertEqual(Recepcion.objects.count(), 0)
