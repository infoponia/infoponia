# Pruebas de CMP-COR-RCP · Corregir Recepción (CMP-06, paso 2): ``recepciones_corregibles``, ``lineas_corregibles``, ``resumir_correccion`` y ``registrar_correccion`` de
# ``compras/servicios/correcciones.py``. Fuente: docs/casos_de_uso/compras/correccion_y_reclamos.md (CMP-COR-RCP v0.1: precondiciones a a d, garantías mínimas, postcondiciones a a h, flujo
# básico, extensiones *a, *b, 1a, 2a, 4a, 4b, 5a, 5b, 9a y 10a, las reglas de negocio y R1 a R3), «Cómo se aplica (código)», D-89 punto 4 (valorización por diferencia de valor acumulado),
# D-90 (puntos 1 a 5: el tipo de movimiento nuevo, los vínculos, «el lote creado por esa recepción» y el orden de bloqueo), D-91 (la bandeja se calcula; la corrección nunca avisa), D-86 y
# docs/modelo/compras.md.
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   recepciones_corregibles(actor, orden_id=None) -> list[RecepcionCorregible(recepcion, orden, proveedor, invernadero, lineas)]       pasos 2 y 3; solo lectura
#       las recepciones de los invernaderos a cargo del Agrónomo (todas, si es el Gerente) cuyo proveedor no tiene ``Pago`` en esa orden y con alguna línea recibida; ``lineas`` son las de
#       ``lineas_corregibles`` de esa recepción; ``orden_id`` filtra por orden (se llega desde la ficha de la orden)
#   lineas_corregibles(actor, recepcion_id) -> list[LineaCorregible(detalle_recepcion, insumo, recibida, lotes, maxima, motivo_bloqueo)]    paso 4; solo lectura
#       las líneas con ``cantidad_recibida_detalle`` > 0; ``recibida`` es lo que esa recepción conserva (ya sin lo corregido); ``lotes`` es ``[(LoteInsumo, corregible)]`` de los lotes que creó
#       (sin el faltante sin lote, D-90 punto 4) con ``corregible = min(disponible, ingresado − ya corregido en ese lote)``; ``maxima`` es la suma de ``corregible``;
#       ``motivo_bloqueo`` es ``None``, ``"cerrada_con_faltante"`` (4b) o ``"sin_stock_en_el_lote"`` (4a con máxima 0)
#   resumir_correccion(actor, recepcion_id, lineas) -> ResumenDeCorreccion(recepcion, lineas, estado_orden, monto_asiento, alertas_que_se_reactivan, avisa_al_proveedor)    paso 7; solo lectura
#       ``lineas`` de entrada: ``[(detalle_recepcion_id, cantidad)]``; ``ResumenDeCorreccion.lineas``: ``[LineaCorregida(detalle_recepcion, cantidad, recibida_antes, recibida_despues,
#       lotes, stock_antes, stock_despues, transito_antes, transito_despues, estado_despues)]`` con ``lotes = [(LoteInsumo, cantidad)]`` en el orden en que se descuenta (del más nuevo al más viejo);
#       ``alertas_que_se_reactivan``: ``[(código de alerta, InsumoInvernadero)]``
#   registrar_correccion(actor, recepcion_id, lineas, observacion="") -> CorreccionRecepcion      paso 9; atómico
# Quién: el Agrónomo activo a cargo del invernadero de la recepción o el Gerente activo (``PermissionDenied`` si no). Una recepción que no existe, ``Http404``. Errores de negocio
# (``ErrorDeCompras``): ``pago_registrado`` (c y 9a; ``datos["pago_id"]``), ``sin_lineas`` (5b), ``linea_repetida``, ``linea_ajena`` (no es de esa recepción), ``linea_cerrada_con_faltante`` (4b),
# ``cantidad_invalida`` (5a: cero, negativa o con más decimales que la unidad) y ``supera_lo_corregible`` (5a, 4a y 9a; ``datos["linea"]``, ``datos["maxima"]``).
# El correo al proveedor sale en ``on_commit``. No toca inconvenientes ni reclamos (R3) y nunca avisa a la bandeja de pagos (D-91 punto 3).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import override_settings

from compras.errores import ErrorDeCompras
from compras.models import (
    AlertaCompras,
    CorreccionRecepcion,
    DetalleCorreccionRecepcion,
    DetalleRecepcion,
    InconvenienteRecepcion,
    Pago,
    Recepcion,
    ReclamoProveedor,
)
from compras.tests.base_correcciones import CorreccionBase, correcciones
from compras.tests.base_recepciones import DANADA, D
from compras.tests.fabricas import ref
from contabilidad import cuentas
from contabilidad.models import AsientoContable, MovimientoContable
from contabilidad.servicios import asientos as servicio_de_asientos
from contabilidad.tests.fabricas import verificar_invariantes_contables
from core.models import Agronomo, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_cuenta, crear_gerente
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad
from inventario.tests.fabricas import faltante, origen_falso, reservas_de_prueba, verificar_invariantes
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_vendedor

CORRECCION = MovimientoInsumo.TipoMovimiento.SALIDA_POR_CORRECCION_DE_RECEPCION
INCONSISTENTE = "inv_stock_inconsistente"


def registro_de_la_correccion():
    """El registro de auditoría de la corrección (la acción se resuelve acá para que un nombre mal escrito falle en la prueba y no al importar)."""
    return RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.CORRECCION_RECEPCION)


class CmpCorRcpPostcondicionesTests(CorreccionBase):
    """Postcondiciones a a h y el flujo básico: Ana corrige 2 kg de Fertilizante que cargó de más."""

    def corregir_fertilizante(self, cantidad=2, actor=None, observacion=""):
        recepcion = self.recibir_a()
        d_fert = self.detalle_de(recepcion, self.l_fert)
        return recepcion, d_fert, self.corregir(actor or self.ana, recepcion, [(d_fert, cantidad)], observacion)

    def test_flujo_principal_corrige_la_recepcion_baja_el_lote_y_registra_el_asiento_inverso(self):
        """Flujo básico (pasos 1 a 11): el lote baja, el tránsito sube, la línea vuelve a «pendiente», la orden queda «parcialmente recibida» y se registra el asiento inverso (Debe Proveedores / Haber
        Insumos en Stock) con la corrección como origen."""
        recepcion, d_fert, correccion = self.corregir_fertilizante()
        self.assertEqual(correccion.recepcion_corregida_id, recepcion.pk)
        self.assertEqual(self.recibido(self.l_fert), D("8"))
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("8"), D("2")))
        self.assertEqual(self.estado_de(self.l_fert), "pendiente")
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        asiento = self.asiento_de_la_correccion(correccion)
        self.assertEqual(self.movimientos_de(asiento), [(cuentas.PROVEEDORES, "D", D("20.00")), (cuentas.INSUMOS_EN_STOCK, "H", D("20.00"))])
        verificar_invariantes(self.fertilizante)
        verificar_invariantes_contables()

    def test_post_a_la_cantidad_recibida_de_la_linea_baja_y_la_corregida_queda_en_la_correccion(self):
        """Postcondición a: ``cantidad_recibida_detalle`` baja en la cantidad corregida; la corrección es un documento de origen de tipo «correccion_de_recepcion» con la fecha de hoy, la observación
        (sin espacios de más), la recepción y el Agrónomo que la hizo. Las demás líneas no cambian."""
        recepcion, d_fert, correccion = self.corregir_fertilizante(observacion="  Se cargó de más.  ")
        self.assertEqual(DetalleRecepcion.objects.get(pk=d_fert.pk).cantidad_recibida_detalle, D("8"))
        self.assertEqual(self.detalle_de(recepcion, self.l_maceta).cantidad_recibida_detalle, D("20"))
        self.assertEqual((correccion.tipo, correccion.fecha_correccion, correccion.observacion, correccion.agronomo_id), ("correccion_de_recepcion", self.hoy, "Se cargó de más.", self.ana.pk))
        self.assertEqual(str(correccion), f"COR-{correccion.pk:04d}")

    def test_post_b_el_lote_baja_con_un_movimiento_del_tipo_nuevo_y_su_vinculo(self):
        """Postcondición b y D-90 puntos 2 y 3: el lote creado por la recepción baja y se crea un movimiento «salida por corrección de recepción» con ``origen`` la corrección, vinculado a su
        línea de corrección (``vinculo_de_correccion``). El stock actual baja y el tránsito sube en lo corregido."""
        recepcion, d_fert, correccion = self.corregir_fertilizante()
        lote = self.lotes_nuevos(self.fertilizante)[0]
        self.assertEqual((lote.cantidad_ingresada, lote.cantidad_disponible), (D("10"), D("8")))
        movimiento = MovimientoInsumo.objects.get(tipo_movimiento=CORRECCION)
        self.assertEqual((movimiento.lote_insumo_id, movimiento.cantidad, movimiento.origen_id), (lote.pk, D("2"), correccion.pk))
        detalle = DetalleCorreccionRecepcion.objects.get()
        self.assertEqual((detalle.correccion_id, detalle.detalle_recepcion_id, detalle.cantidad_corregida, detalle.movimiento_id), (correccion.pk, d_fert.pk, D("2"), movimiento.pk))
        self.assertEqual(movimiento.vinculo_de_correccion, detalle)

    def test_post_c_el_detalle_de_la_orden_vuelve_a_pendiente_y_la_orden_se_recalcula(self):
        """Postcondición c y regla 24 de 8.16: la línea «completo» vuelve a «pendiente» por lo corregido y la orden queda «parcialmente recibida» aunque estuviera «recibida»."""
        a = self.recibir_a()
        self.recibir_b()
        self.assertEqual(self.estado_de_la_orden(), "recibida")
        self.corregir(self.ana, a, [(self.detalle_de(a, self.l_maceta), 5)])
        self.assertEqual((self.estado_de(self.l_maceta), self.estado_de(self.l_fert), self.estado_de(self.l_tomate)), ("pendiente", "completo", "completo"))
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")

    def test_post_c_una_linea_que_ya_estaba_pendiente_sigue_pendiente(self):
        """Postcondición c: si la línea ya estaba «pendiente» (recepción parcial) sigue pendiente; baja lo recibido y sube el tránsito."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 1)])
        self.assertEqual((self.estado_de(self.l_fert), self.recibido(self.l_fert)), ("pendiente", D("3")))
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("3"), D("7")))
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")

    def test_post_d_el_asiento_es_el_inverso_por_la_diferencia_de_valor_acumulado(self):
        """Postcondición d y D-89 punto 4: Debe Proveedores / Haber Insumos en Stock por ``valor_recibido(antes) − valor_recibido(después)`` de cada línea, sumadas: 2 kg de Fertilizante ($100,00 por
        10: $20,00) y 5 u de Maceta ($200,00 por 20: $50,00) hacen un solo asiento de $70,00. La fecha es la de hoy y el ejercicio, el abierto."""
        recepcion = self.recibir_a()
        correccion = self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2), (self.detalle_de(recepcion, self.l_maceta), 5)])
        asiento = self.asiento_de_la_correccion(correccion)
        self.assertEqual(self.movimientos_de(asiento), [(cuentas.PROVEEDORES, "D", D("70.00")), (cuentas.INSUMOS_EN_STOCK, "H", D("70.00"))])
        self.assertEqual((asiento.fecha_asiento, asiento.ejercicio_id, asiento.origen_id), (self.hoy, self.abierto.pk, correccion.pk))
        verificar_invariantes_contables()

    def test_post_d_dos_correcciones_sucesivas_valorizan_cada_una_su_diferencia(self):
        """D-89 punto 4: la segunda corrección usa el acumulado que quedó: de 10 a 8 ($20,00) y de 8 a 5 ($30,00); en total Proveedores se debe $50,00 menos que al recibir."""
        recepcion = self.recibir_a()
        d_fert = self.detalle_de(recepcion, self.l_fert)
        primera = self.corregir(self.ana, recepcion, [(d_fert, 2)])
        segunda = self.corregir(self.ana, recepcion, [(d_fert, 3)])
        self.assertEqual(self.movimientos_de(self.asiento_de_la_correccion(primera))[0], (cuentas.PROVEEDORES, "D", D("20.00")))
        self.assertEqual(self.movimientos_de(self.asiento_de_la_correccion(segunda))[0], (cuentas.PROVEEDORES, "D", D("30.00")))
        self.assertEqual(self.saldo_de_proveedores(), D("250.00"))
        self.assertEqual(self.recibido(self.l_fert), D("5"))

    def test_post_d_tres_recepciones_parciales_una_correccion_y_el_pago_dejan_proveedores_en_cero(self):
        """«Hecho cuando» y D-89 punto 4: una línea de 3 unidades por $100,00 (unitario 33,3333) se recibe de a una (33,33 + 33,34 + 33,33); se corrige la última, se vuelve a recibir y se paga: la cuenta
        Proveedores queda **exactamente** en cero, sin centavos colgados."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, nombre_de_insumo="Sustrato", cantidad=3, total="100.00", n=5)
        recibir = lambda: self.registrar(self.ana, [self.linea(linea, 1)], orden=orden, proveedor=linea.proveedor, invernadero=self.norte)
        recibir()
        recibir()
        tercera = recibir()
        asiento = self.asiento_de(tercera)
        self.assertEqual(self.movimientos_de(asiento)[0], (cuentas.INSUMOS_EN_STOCK, "D", D("33.33")))
        correccion = self.corregir(self.ana, tercera, [(self.detalle_de(tercera, linea), 1)])
        self.assertEqual(self.movimientos_de(self.asiento_de_la_correccion(correccion))[0], (cuentas.PROVEEDORES, "D", D("33.33")))
        recibir()
        self.pagar(orden=orden, proveedor=linea.proveedor)
        origenes = [r.pk for r in Recepcion.objects.filter(orden=orden)] + [correccion.pk] + [p.pk for p in Pago.objects.filter(orden=orden)]
        suyos = MovimientoContable.objects.filter(cuenta__codigo_cuenta=cuentas.PROVEEDORES, asiento__origen_id__in=origenes)
        haber = sum((m.importe_movimiento for m in suyos if m.tipo_movimiento == "H"), D("0.00"))
        debe = sum((m.importe_movimiento for m in suyos if m.tipo_movimiento == "D"), D("0.00"))
        self.assertEqual((haber, debe), (D("133.33"), D("133.33")))
        verificar_invariantes_contables()

    def test_post_e_se_reevaluan_las_alertas_del_insumo_y_se_reactiva_la_de_stock_inconsistente(self):
        """Postcondición e y reglas 11 y 12 de 8.15: la corrección reevalúa las alertas; con 10 de stock y 8 reservados, bajar 4 deja el stock (6) por debajo de lo reservado y se crea la alerta."""
        recepcion = self.recibir_a()
        with reservas_de_prueba(reservado={self.fertilizante.pk: D("8")}):
            self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 4)])
        alerta = Alerta.objects.get(tipo_alerta=INCONSISTENTE, clave_estado=f"insumo:{self.fertilizante.pk}")
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)

    def test_post_f_el_proveedor_sale_de_la_bandeja_de_pagos_pendientes_y_no_hay_aviso_nuevo(self):
        """Postcondición f y D-91 punto 3: A estaba para pagar; al corregir deja de tener todas sus líneas completas y sale de la bandeja (se calcula). La corrección nunca avisa: el Contador no recibe
        un aviso «Proveedor para pagar» más."""
        recepcion = self.recibir_a()
        self.assertEqual([p.proveedor.pk for p in pagos_pendientes()], [self.proveedor.pk])
        avisos = len(self.avisos_de_pago(self.contador))
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2)])
        self.assertEqual(pagos_pendientes(), [])
        self.assertEqual(len(self.avisos_de_pago(self.contador)), avisos)

    def test_post_g_el_proveedor_recibe_un_correo_con_lo_corregido_y_lo_que_sigue_pendiente(self):
        """Postcondición g y lista de tecnología 10: un correo al proveedor (y solo a él) con el identificador de la orden, la fecha de la recepción corregida, por línea el insumo y la cantidad
        corregida, y lo que sigue pendiente. No menciona a otros proveedores."""
        recepcion = self.recibir_a()
        antes = len(mail.outbox)
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2)])
        nuevos = self.correos_nuevos(antes)
        self.assertEqual(len(nuevos), 1)
        correo = nuevos[0]
        self.assertEqual(correo.to, ["ventas@sur.com"])
        self.assertIn(str(self.orden), correo.subject)
        for texto in (str(self.orden), f"{recepcion.fecha_recepcion:%d/%m/%Y}", "Fertilizante", texto_cantidad(D("2"), "kg"), self.proveedor.nombre_para_mostrar, str(recepcion)):
            self.assertIn(texto, correo.body)
        self.assertNotIn("Maceta", correo.body)  # la Maceta no se corrigió y está completa: no aparece ni como corregida ni como pendiente
        self.assertNotIn(self.proveedor_b.nombre_para_mostrar, correo.body)

    def test_post_h_un_registro_de_auditoria_nombra_todo_lo_que_la_correccion_creo_o_modifico(self):
        """Postcondición h y D-36: un registro ``correccion_recepcion`` de quien actuó que nombra entre sus afectados la corrección, su detalle de recepción, la línea de la orden y la orden; en
        ``datos``, el asiento y el movimiento. Más una ``modificacion_insumo_invernadero`` con el tránsito y el stock antes y después. El asiento lo audita la función de asientos."""
        recepcion, d_fert, correccion = self.corregir_fertilizante()
        registro = registro_de_la_correccion()
        self.assertEqual(registro.usuario_id, self.ana.pk)
        afectados = {(a["modelo"], a["id"]) for a in registro.afectados}
        esperados = {
            ("compras.correccionrecepcion", correccion.pk),
            ("compras.detallerecepcion", d_fert.pk),
            ("compras.detalleordencompra", self.l_fert.pk),
            ("compras.ordencompra", self.orden.pk),
        }
        self.assertTrue(esperados <= afectados, esperados - afectados)
        datos = registro.detalle["datos"]
        self.assertEqual(datos["asiento"], ref(self.asiento_de_la_correccion(correccion)))
        self.assertEqual(datos["movimientos"], [ref(MovimientoInsumo.objects.get(tipo_movimiento=CORRECCION))])
        modificacion = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO).order_by("id").last()
        self.assertEqual(modificacion.detalle["datos"]["correccion"], ref(correccion))
        self.assertEqual(
            modificacion.detalle["cambios"],
            {"transito": {"antes": texto_cantidad(D("0"), "kg"), "despues": texto_cantidad(D("2"), "kg")}, "stock": {"antes": texto_cantidad(D("10"), "kg"), "despues": texto_cantidad(D("8"), "kg")}},
        )
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_ASIENTO_CONTABLE).count(), 2)  # el de la recepción y el de la corrección: lo audita la función de asientos

    def test_r3_la_correccion_no_toca_los_inconvenientes_ni_el_reclamo(self):
        """Decisión de modelo R3: una recepción con un inconveniente y un reclamo sin emitir sigue igual después de corregirla: el inconveniente, el reclamo (sin emitir) y su alerta no cambian."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 6, self.vence, inconvenientes=[(DANADA, 2, "Cajas rotas")])])
        alerta = AlertaCompras.objects.get().alerta
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 1)])
        inconveniente = InconvenienteRecepcion.objects.get()
        reclamo = ReclamoProveedor.objects.get()
        self.assertEqual((inconveniente.cantidad_afectada, inconveniente.tipo_inconveniente), (D("2"), DANADA))
        self.assertEqual((reclamo.gerente_id, reclamo.fecha_reclamo, reclamo.estado_reclamo), (None, None, "abierto"))
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, Alerta.Estado.ACTIVA)


def pagos_pendientes():
    from compras.servicios import pagos

    return pagos.pagos_pendientes()


class CmpCorRcpLotesTests(CorreccionBase):
    """«El lote creado por esa recepción» y lo máximo corregible (D-90 punto 4; extensión 4a)."""

    def test_regla_se_descuenta_lote_por_lote_del_mas_nuevo_al_mas_viejo_y_cada_lote_tiene_su_vinculo(self):
        """D-90 punto 4 y R6: una línea recibida en dos lotes (4 con un vencimiento y 6 con otro) y corregida en 7 descuenta primero el lote más nuevo (6) y después 1 del más viejo; son dos
        movimientos y dos filas ``DetalleCorreccionRecepcion`` de la misma línea (uno por lote)."""
        otra = self.hoy + timedelta(days=30)
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, partes=[(D("4"), otra), (D("6"), self.vence)])])
        viejo, nuevo = self.lotes_nuevos(self.fertilizante)
        correccion = self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 7)])
        self.assertEqual((self.disponible(nuevo), self.disponible(viejo)), (D("0"), D("3")))
        filas = list(DetalleCorreccionRecepcion.objects.filter(correccion=correccion).order_by("id"))
        self.assertEqual([(f.movimiento.lote_insumo_id, f.cantidad_corregida) for f in filas], [(nuevo.pk, D("6")), (viejo.pk, D("1"))])
        self.assertEqual({f.detalle_recepcion_id for f in filas}, {self.detalle_de(recepcion, self.l_fert).pk})
        self.assertEqual((self.stock_de(self.fertilizante), self.transito(self.fertilizante)), (D("3"), D("7")))
        verificar_invariantes(self.fertilizante)

    def test_ext_4a_un_lote_parcialmente_consumido_limita_lo_maximo_corregible(self):
        """Extensión 4a y D-90 punto 4: si se consumieron 6 de los 10 que ingresó el lote, la máxima corregible es 4; pedir 5 es ``supera_lo_corregible`` con ``maxima = 4`` y no cambia nada; 4 se corrige
        y deja el lote en 0."""
        recepcion = self.recibir_a()
        lote = self.lotes_nuevos(self.fertilizante)[0]
        stock.registrar_salida_por_consumo(self.fertilizante.pk, [(lote.pk, D("6"))], origen_id=origen_falso().pk)
        linea = [l for l in correcciones.lineas_corregibles(self.ana, recepcion.pk) if l.detalle_recepcion.detalle_orden_id == self.l_fert.pk][0]
        self.assertEqual((linea.recibida, linea.maxima, linea.motivo_bloqueo), (D("10"), D("4"), None))
        self.assertEqual([(l.pk, c) for l, c in linea.lotes], [(lote.pk, D("4"))])
        antes = self.instantanea_de_correcciones()
        error = self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 5)])
        self.assertEqual((error.codigo, error.datos["maxima"]), ("supera_lo_corregible", D("4")))
        self.sin_cambios_de_correcciones(antes)
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 4)])
        self.assertEqual(self.disponible(lote), D("0"))

    def test_ext_4a_si_el_lote_se_consumio_entero_la_linea_no_se_puede_corregir(self):
        """Extensión 4a: con el lote en 0 la máxima corregible es 0 y el Sistema no permite corregir esa línea (``motivo_bloqueo = sin_stock_en_el_lote``); lo restante se resuelve con un ajuste de stock."""
        recepcion = self.recibir_a()
        lote = self.lotes_nuevos(self.fertilizante)[0]
        stock.registrar_salida_por_consumo(self.fertilizante.pk, [(lote.pk, D("10"))], origen_id=origen_falso().pk)
        linea = [l for l in correcciones.lineas_corregibles(self.ana, recepcion.pk) if l.detalle_recepcion.detalle_orden_id == self.l_fert.pk][0]
        self.assertEqual((linea.maxima, linea.motivo_bloqueo), (D("0"), "sin_stock_en_el_lote"))
        antes = self.instantanea_de_correcciones()
        error = self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 1)])
        self.assertEqual((error.codigo, error.datos["maxima"]), ("supera_lo_corregible", D("0")))
        self.sin_cambios_de_correcciones(antes)

    def test_ext_4a_lo_que_cubrio_un_faltante_sin_lote_no_se_puede_corregir(self):
        """D-90 punto 4: si la recepción cubrió primero un faltante sin lote de 3 (ya consumido), lo máximo corregible de los 10 recibidos es 7 (los del lote nuevo), no 10; ``recibida`` sigue siendo 10."""
        faltante(self.fertilizante, 3)
        recepcion = self.recibir_a()
        linea = [l for l in correcciones.lineas_corregibles(self.ana, recepcion.pk) if l.detalle_recepcion.detalle_orden_id == self.l_fert.pk][0]
        self.assertEqual((linea.recibida, linea.maxima), (D("10"), D("7")))
        self.assertEqual(len(linea.lotes), 1)
        error = self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 8)])
        self.assertEqual((error.codigo, error.datos["maxima"]), ("supera_lo_corregible", D("7")))
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 7)])
        verificar_invariantes(self.fertilizante)

    def test_regla_la_maxima_baja_con_lo_ya_corregido_de_esa_recepcion(self):
        """Regla «Solo en menos» y D-90 punto 4: después de corregir 4 de 10, la máxima es 6 (lo que ingresó menos lo ya corregido en el lote) y la línea muestra 6 recibidas; pedir 7 se rechaza."""
        recepcion = self.recibir_a()
        d_fert = self.detalle_de(recepcion, self.l_fert)
        self.corregir(self.ana, recepcion, [(d_fert, 4)])
        linea = [l for l in correcciones.lineas_corregibles(self.ana, recepcion.pk) if l.detalle_recepcion.pk == d_fert.pk][0]
        self.assertEqual((linea.recibida, linea.maxima), (D("6"), D("6")))
        error = self.error_de_correccion(self.ana, recepcion, [(d_fert, 7)])
        self.assertEqual((error.codigo, error.datos["maxima"]), ("supera_lo_corregible", D("6")))

    def test_regla_lo_que_el_lote_conserva_de_mas_por_un_ajuste_no_amplia_lo_maximo(self):
        """D-90 punto 4: la máxima es ``min(disponible, ingresado − ya corregido)``: un ajuste positivo que deja el lote en 12 no permite corregir más de lo que la recepción ingresó."""
        recepcion = self.recibir_a()
        lote = self.lotes_nuevos(self.fertilizante)[0]
        LoteInsumo.objects.filter(pk=lote.pk).update(cantidad_disponible=D("12"))
        linea = [l for l in correcciones.lineas_corregibles(self.ana, recepcion.pk) if l.detalle_recepcion.detalle_orden_id == self.l_fert.pk][0]
        self.assertEqual(linea.maxima, D("10"))


class CmpCorRcpExtensionesTests(CorreccionBase):
    """Extensiones 1a, 2a, 4b, 5a, 5b, 9a y 10a, y la lista de recepciones corregibles."""

    def test_ext_1a_el_gerente_corrige_sin_agronomo_y_queda_en_la_auditoria(self):
        """Extensión 1a: si corrige el Gerente, el Agrónomo de la corrección queda vacío (0..1) y el Gerente figura como quien actuó; ve las recepciones de todos los invernaderos."""
        recepcion = self.recibir_a()
        correccion = self.corregir(self.gerente, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2)])
        self.assertIsNone(correccion.agronomo)
        self.assertEqual(registro_de_la_correccion().usuario_id, self.gerente.pk)
        self.recibir_b()
        self.assertEqual({c.recepcion.proveedor_id for c in correcciones.recepciones_corregibles(self.gerente)}, {self.proveedor.pk, self.proveedor_b.pk})

    def test_ext_2a_no_hay_recepciones_corregibles_si_el_proveedor_ya_tiene_su_pago(self):
        """Extensión 2a y precondición c: una recepción cuyo proveedor tiene su ``Pago`` en esa orden no es corregible; la de otro proveedor sin pago, sí. Sin ninguna, lista vacía."""
        self.assertEqual(correcciones.recepciones_corregibles(self.ana), [])
        a = self.recibir_a()
        b = self.recibir_b()
        self.pagar()
        self.assertEqual([c.recepcion.pk for c in correcciones.recepciones_corregibles(self.ana)], [b.pk])
        self.pagar(proveedor=self.proveedor_b)
        self.assertEqual(correcciones.recepciones_corregibles(self.ana), [])
        self.assertNotIn(a.pk, [c.recepcion.pk for c in correcciones.recepciones_corregibles(self.gerente)])

    def test_pasos_2_y_3_cada_recepcion_trae_su_orden_proveedor_invernadero_y_lineas_y_se_filtra_por_orden(self):
        """Paso 2: para cada recepción corregible, la orden, el proveedor, el invernadero (la fecha va en la recepción) y las líneas con lo recibido; ``orden_id`` filtra por orden."""
        a = self.recibir_a()
        otra, linea, _ = self.otra_orden(self.ana, self.norte, cantidad=6, total="60.00", n=5)
        otra_recepcion = self.registrar(self.ana, [self.linea(linea, 6)], orden=otra, proveedor=linea.proveedor, invernadero=self.norte)
        todas = correcciones.recepciones_corregibles(self.ana)
        self.assertEqual({c.recepcion.pk for c in todas}, {a.pk, otra_recepcion.pk})
        de_la_orden = correcciones.recepciones_corregibles(self.ana, self.orden.pk)
        self.assertEqual([c.recepcion.pk for c in de_la_orden], [a.pk])
        c = de_la_orden[0]
        self.assertEqual((c.orden.pk, c.proveedor.pk, c.invernadero.pk), (self.orden.pk, self.proveedor.pk, self.norte.pk))
        self.assertEqual([(l.insumo.nombre_insumo, l.recibida) for l in c.lineas], [("Fertilizante", D("10")), ("Maceta", D("20"))])

    def test_ext_2a_una_recepcion_sin_nada_recibido_no_es_corregible(self):
        """Precondición b: la recepción tiene que tener alguna línea con cantidad recibida mayor que cero; una cuya única línea llegó en 0 (todo dañado) no figura."""
        self.registrar(self.ana, [self.linea(self.l_fert, 0, inconvenientes=[(DANADA, 3, "")])])
        self.assertEqual(correcciones.recepciones_corregibles(self.ana), [])

    def test_ext_4b_una_linea_cerrada_con_faltante_no_se_puede_corregir(self):
        """Extensión 4b y R2: la línea cerrada con faltante figura con ``motivo_bloqueo = cerrada_con_faltante`` y corregirla es ``linea_cerrada_con_faltante``; la otra línea de la recepción sí se corrige."""
        self.recibir_a_con_faltante()
        a = Recepcion.objects.get(proveedor=self.proveedor)
        lineas = {l.detalle_recepcion.detalle_orden_id: l for l in correcciones.lineas_corregibles(self.ana, a.pk)}
        self.assertEqual((lineas[self.l_fert.pk].motivo_bloqueo, lineas[self.l_maceta.pk].motivo_bloqueo), ("cerrada_con_faltante", None))
        antes = self.instantanea_de_correcciones()
        error = self.error_de_correccion(self.ana, a, [(self.detalle_de(a, self.l_fert), 1)])
        self.assertEqual(error.codigo, "linea_cerrada_con_faltante")
        self.sin_cambios_de_correcciones(antes)
        self.corregir(self.ana, a, [(self.detalle_de(a, self.l_maceta), 1)])

    def test_ext_5a_la_cantidad_cero_negativa_o_con_demasiados_decimales_se_rechaza(self):
        """Extensión 5a y regla 2 de 8.23: cero, negativa o con más decimales de los que admite la unidad (el kg admite tres; la unidad, ninguno) es ``cantidad_invalida`` y no cambia nada."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        for detalle, cantidad in ((self.l_fert, "0"), (self.l_fert, "-1"), (self.l_fert, "0.0005"), (self.l_maceta, "1.5")):
            with self.subTest(cantidad=cantidad, linea=str(detalle)):
                self.assertEqual(self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, detalle), cantidad)]).codigo, "cantidad_invalida")
        self.sin_cambios_de_correcciones(antes)

    def test_ext_5a_no_se_corrige_mas_de_lo_recibido_ni_de_lo_corregible(self):
        """Extensión 5a: una cantidad mayor que la máxima corregible (10 recibidos) es ``supera_lo_corregible`` con la máxima en ``datos``."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        error = self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), D("10.001"))])
        self.assertEqual((error.codigo, error.datos["maxima"], error.datos["linea"]), ("supera_lo_corregible", D("10"), self.detalle_de(recepcion, self.l_fert).pk))
        self.sin_cambios_de_correcciones(antes)

    def test_ext_5b_la_correccion_incluye_al_menos_una_linea(self):
        """Extensión 5b: sin ninguna línea con cantidad, ``sin_lineas``; la misma línea dos veces, ``linea_repetida``; una línea de otra recepción, ``linea_ajena``."""
        a = self.recibir_a()
        b = self.recibir_b()
        antes = self.instantanea_de_correcciones()
        d_fert = self.detalle_de(a, self.l_fert)
        self.assertEqual(self.error_de_correccion(self.ana, a, []).codigo, "sin_lineas")
        self.assertEqual(self.error_de_correccion(self.ana, a, [(d_fert, 1), (d_fert, 1)]).codigo, "linea_repetida")
        self.assertEqual(self.error_de_correccion(self.ana, a, [(self.detalle_de(b, self.l_tomate), 1)]).codigo, "linea_ajena")
        self.sin_cambios_de_correcciones(antes)

    def test_ext_9a_si_el_proveedor_ya_tiene_su_pago_no_se_corrige(self):
        """Precondición c y extensión 9a: con el ``Pago`` del par (orden, proveedor) registrado, ``pago_registrado`` (con el id del pago) y no cambia nada; ni siquiera se lista la recepción."""
        recepcion = self.recibir_a()
        pago = self.pagar()
        antes = self.instantanea_de_correcciones()
        error = self.error_de_correccion(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 1)])
        self.assertEqual((error.codigo, error.datos["pago_id"]), ("pago_registrado", pago.pk))
        self.sin_cambios_de_correcciones(antes)
        with self.assertRaises(ErrorDeCompras):
            correcciones.lineas_corregibles(self.ana, recepcion.pk)

    def test_ext_9a_si_el_lote_se_consume_entre_el_resumen_y_la_confirmacion_no_se_registra_nada(self):
        """Extensión 9a: se verifica de nuevo con todo bloqueado; si entre el resumen y la confirmación se consumió el lote, ``supera_lo_corregible`` con lo que queda y no cambia nada (vuelve al paso 4)."""
        recepcion = self.recibir_a()
        lineas = [(self.detalle_de(recepcion, self.l_fert).pk, D("8"))]
        correcciones.resumir_correccion(self.ana, recepcion.pk, lineas)
        stock.registrar_salida_por_consumo(self.fertilizante.pk, [(self.lotes_nuevos(self.fertilizante)[0].pk, D("5"))], origen_id=origen_falso().pk)
        antes = self.instantanea_de_correcciones()
        with self.assertRaises(ErrorDeCompras) as contexto:
            correcciones.registrar_correccion(self.ana, recepcion.pk, lineas, "")
        self.assertEqual((contexto.exception.codigo, contexto.exception.datos["maxima"]), ("supera_lo_corregible", D("5")))
        self.sin_cambios_de_correcciones(antes)

    @override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_ext_10a_si_el_correo_no_sale_la_correccion_queda_registrada(self):
        """Extensión 10a (D-88 punto 6: no hay cola de reintentos): si no se logra enviar el correo, la corrección permanece registrada con su asiento (el correo sale fuera de la transacción)."""
        recepcion = self.recibir_a()
        correccion = self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2)])
        self.assertTrue(CorreccionRecepcion.objects.filter(pk=correccion.pk).exists())
        self.assertTrue(AsientoContable.objects.filter(origen_id=correccion.pk).exists())

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_10a_sin_el_correo_configurado_no_sale_nada_y_la_correccion_se_registra(self):
        """D-33: sin el correo configurado no sale ningún correo y la corrección se registra igual."""
        recepcion = self.recibir_a()
        antes = len(mail.outbox)
        self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 2)])
        self.assertEqual(len(mail.outbox), antes)
        self.assertEqual(CorreccionRecepcion.objects.count(), 1)


class CmpCorRcpPermisosTests(CorreccionBase):
    """Precondición a: quién corrige, y el alcance del Agrónomo."""

    def test_pre_a_solo_el_agronomo_a_cargo_o_el_gerente_corrigen(self):
        """Precondición a y regla «Quién registra»: ni otro Agrónomo (sin el invernadero a cargo), ni el Vendedor, el Capataz, el Administrador o el Contador, ni un Agrónomo o Gerente inactivo, ni nadie
        (``None``)."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        lineas = [(self.detalle_de(recepcion, self.l_fert).pk, D("1"))]
        inactivo = crear_cuenta(Agronomo, email="viejo@infoponia.com", activo=False)
        gerente_inactivo = crear_gerente(email="otro.gerente@infoponia.com", activo=False)
        otro_agronomo = crear_agronomo()
        for actor in (self.beto, otro_agronomo, crear_vendedor(), crear_capataz(), crear_administrador(), self.contador, inactivo, gerente_inactivo, None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    correcciones.registrar_correccion(actor, recepcion.pk, lineas, "")
                with self.assertRaises(PermissionDenied):
                    correcciones.lineas_corregibles(actor, recepcion.pk)
                with self.assertRaises(PermissionDenied):
                    correcciones.resumir_correccion(actor, recepcion.pk, lineas)
                if actor not in (self.beto, otro_agronomo):  # un Agrónomo activo sin invernaderos a cargo simplemente no tiene nada que corregir (lista vacía)
                    with self.assertRaises(PermissionDenied):
                        correcciones.recepciones_corregibles(actor)
        self.sin_cambios_de_correcciones(antes)

    def test_pre_a_el_agronomo_solo_ve_las_recepciones_de_sus_invernaderos(self):
        """Requisitos especiales: «el Agrónomo accede solo a las órdenes con destino en los invernaderos que tiene a cargo»: Beto (Sur) no ve las recepciones de Norte (lista vacía) ni abre una por id
        (``PermissionDenied``); una recepción que no existe es ``Http404``."""
        recepcion = self.recibir_a()
        self.assertEqual(correcciones.recepciones_corregibles(self.beto), [])
        with self.assertRaises(PermissionDenied):
            correcciones.lineas_corregibles(self.beto, recepcion.pk)
        with self.assertRaises(Http404):
            correcciones.lineas_corregibles(self.ana, recepcion.pk + 9999)
        with self.assertRaises(Http404):
            correcciones.registrar_correccion(self.ana, recepcion.pk + 9999, [(1, D("1"))], "")

    def test_pre_d_sin_ejercicio_la_correccion_se_registra_igual_porque_el_asiento_lo_abre(self):
        """Precondición d y D-84 punto 2 (autorrecuperación): la función de asientos abre un ejercicio si no hay ninguno; la corrección no se rechaza por eso."""
        recepcion = self.recibir_a()
        correccion = self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, self.l_fert), 1)])
        self.assertTrue(AsientoContable.objects.filter(origen_id=correccion.pk).exists())


class CmpCorRcpResumenTests(CorreccionBase):
    """Paso 7: el resumen no escribe y muestra lo que pasaría."""

    def test_paso_7_el_resumen_muestra_por_linea_el_nuevo_recibido_el_stock_el_transito_y_el_estado(self):
        """Paso 7: por línea, la nueva cantidad recibida, cómo cambian el stock y el tránsito, el estado en que queda la línea y la orden, el monto del asiento inverso y que se avisará al proveedor."""
        recepcion = self.recibir_a()
        resumen = correcciones.resumir_correccion(self.ana, recepcion.pk, [(self.detalle_de(recepcion, self.l_fert).pk, D("2"))])
        linea = resumen.lineas[0]
        self.assertEqual((linea.cantidad, linea.recibida_antes, linea.recibida_despues), (D("2"), D("10"), D("8")))
        self.assertEqual((linea.stock_antes, linea.stock_despues, linea.transito_antes, linea.transito_despues), (D("10"), D("8"), D("0"), D("2")))
        self.assertEqual(linea.estado_despues, "pendiente")
        self.assertEqual([(l.pk, c) for l, c in linea.lotes], [(self.lotes_nuevos(self.fertilizante)[0].pk, D("2"))])
        self.assertEqual((resumen.estado_orden, resumen.monto_asiento, resumen.avisa_al_proveedor), ("parcialmente_recibida", D("20.00"), True))

    def test_paso_7_el_resumen_avisa_de_las_alertas_que_se_reactivaran(self):
        """Paso 7: con 8 reservados de 10 en stock, corregir 4 reactivará «stock inconsistente»; sin reservas, el resumen no reactiva ninguna."""
        recepcion = self.recibir_a()
        lineas = [(self.detalle_de(recepcion, self.l_fert).pk, D("4"))]
        self.assertEqual(correcciones.resumir_correccion(self.ana, recepcion.pk, lineas).alertas_que_se_reactivan, [])
        with reservas_de_prueba(reservado={self.fertilizante.pk: D("8")}):
            resumen = correcciones.resumir_correccion(self.ana, recepcion.pk, lineas)
        self.assertEqual([(codigo, iin.pk) for codigo, iin in resumen.alertas_que_se_reactivan], [(INCONSISTENTE, self.fertilizante.pk)])

    def test_paso_7_el_resumen_no_escribe_ni_bloquea_nada_y_valida_lo_mismo_que_el_registro(self):
        """El resumen no cambia nada y rechaza con los mismos errores que ``registrar_correccion`` (5a, 5b, 4b, pago)."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        correcciones.resumir_correccion(self.ana, recepcion.pk, [(self.detalle_de(recepcion, self.l_fert).pk, D("2"))])
        with self.assertRaises(ErrorDeCompras) as contexto:
            correcciones.resumir_correccion(self.ana, recepcion.pk, [])
        self.assertEqual(contexto.exception.codigo, "sin_lineas")
        with self.assertRaises(ErrorDeCompras) as contexto:
            correcciones.resumir_correccion(self.ana, recepcion.pk, [(self.detalle_de(recepcion, self.l_fert).pk, D("11"))])
        self.assertEqual(contexto.exception.codigo, "supera_lo_corregible")
        self.sin_cambios_de_correcciones(antes)


class CmpCorRcpAtomicidadTests(CorreccionBase):
    """Garantías mínimas: la corrección es atómica."""

    def test_garantia_minima_si_el_asiento_falla_no_queda_nada_a_medias(self):
        """Garantías mínimas y docs/patrones/asientos.md, sección 4: si el asiento falla (el último paso), no cambia el stock, el tránsito, los lotes, los estados ni las alertas, y no queda ningún
        movimiento, corrección, log ni correo."""
        recepcion = self.recibir_a()
        antes = self.instantanea_de_correcciones()
        with mock.patch.object(servicio_de_asientos, "registrar_asiento_automatico", side_effect=RuntimeError("falla forzada")):
            with self.assertRaises(RuntimeError), self.captureOnCommitCallbacks(execute=True):
                correcciones.registrar_correccion(self.ana, recepcion.pk, [(self.detalle_de(recepcion, self.l_fert).pk, D("2"))], "")
        self.sin_cambios_de_correcciones(antes)

    def test_regla_un_asiento_de_importe_cero_no_es_un_error_y_no_deja_asiento(self):
        """D-84 punto 6 (H11) y docs/api/asientos.md: si la diferencia de valor se redondea a cero (una línea de 3 unidades por $0,01: ``valor(3) − valor(2)`` = 0,01 − 0,01), la función de asientos devuelve
        ``None``: la corrección se registra igual, sin asiento."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, nombre_de_insumo="Sustrato", cantidad=3, total="0.01", n=5)
        recepcion = self.registrar(self.ana, [self.linea(linea, 3)], orden=orden, proveedor=linea.proveedor, invernadero=self.norte)
        correccion = self.corregir(self.ana, recepcion, [(self.detalle_de(recepcion, linea), 1)])
        self.assertFalse(AsientoContable.objects.filter(origen_id=correccion.pk).exists())
        self.assertEqual(self.recibido(linea), D("2"))
        verificar_invariantes_contables()
