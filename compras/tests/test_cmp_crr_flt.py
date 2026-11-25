# Pruebas de CMP-CRR-FLT · Cerrar Detalle con Faltante (CMP-04, paso 4): ``lineas_pendientes_de_cierre``, ``resumir_cierre`` y ``cerrar_con_faltante`` de
# ``compras/servicios/recepciones.py``. Fuente: docs/casos_de_uso/compras/recepcion.md (CMP-CRR-FLT v0.1: precondiciones a y b, garantías mínimas, postcondiciones a a g,
# flujo básico, extensiones *a, *b, 1a, 2a, 4a, 7a y 7b, y las reglas «Cierre con faltante», «Tránsito», «Estado de la orden», «Pago» y «Sin asiento»), «Decisiones derivadas»
# R1 a R6, «Cómo se aplica (código)», D-90 y la regla 22 de 8.16. Lo de la bandeja de pagos (postcondición e: «quedó para pagar», D-91) lo agrega CMP-05: acá solo se calcula
# si el proveedor «queda para pagar» para mostrarlo en el resumen (paso 5).
#
# API que fijan estas pruebas (el módulo se toma dentro de cada prueba con ``perezoso``):
#   lineas_pendientes_de_cierre(actor, orden_id=None, recepcion_id=None)
#       -> list[LineaPorCerrar(orden, detalle, proveedor, invernadero, insumo, pedida, recibida, falta, entrega_esperada, atraso_dias)]   paso 2; con ``orden_id`` solo esa orden;
#          con ``recepcion_id`` (2a) solo las líneas de esa recepción que siguen pendientes
#   resumir_cierre(actor, lineas) -> ResumenDeCierre(lineas, estados_de_ordenes, proveedores, alertas_que_se_activan)    paso 5; solo lectura
#       lineas: list[LineaCerrada(detalle, falta, transito_antes, transito_despues, motivo)]; estados_de_ordenes: {orden_id: estado en que quedará};
#       proveedores: list[(proveedor, queda_para_pagar)]; alertas_que_se_activan: list[InsumoInvernadero] que pasarán a estar bajo el mínimo
#   cerrar_con_faltante(actor, lineas) -> list[DetalleOrdenCompra]     ``lineas = [(detalle_orden_id, motivo)]``; atómico
# Quién: el Agrónomo activo a cargo del invernadero de CADA línea, o el Gerente (``PermissionDenied`` si no). Errores de negocio (``ErrorDeCompras``): sin_lineas (paso 3),
# motivo_obligatorio (4a; ``datos["lineas"]``), linea_repetida y linea_no_pendiente (7a; ``datos["lineas"]``; también una línea que no existe). Los correos salen en ``on_commit`` (``captureOnCommitCallbacks``).

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied
from django.test import override_settings

from compras.errores import ErrorDeCompras
from compras.models import DetalleOrdenCompra, DetalleRecepcion
from compras.tests.base_recepciones import BAJO_MINIMO, D, RecepcionBase, recepciones
from compras.tests.fabricas import ref
from contabilidad.models import AsientoContable
from core.models import Contador, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_cuenta
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.servicios import stock
from inventario.servicios.formato import texto_cantidad
from inventario.tests.fabricas import verificar_invariantes
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_alerta, crear_vendedor

MOTIVO = "El proveedor no consigue reponer."


class CmpCrrFltBase(RecepcionBase):
    """Los auxiliares del cierre sobre el escenario de ``RecepcionBase``."""

    def cerrar(self, actor, *lineas):
        """``cerrar_con_faltante`` con los correos ejecutados. ``lineas`` son ``(detalle, motivo)``."""
        with self.captureOnCommitCallbacks(execute=True):
            return recepciones.cerrar_con_faltante(actor, [(detalle.pk, motivo) for detalle, motivo in lineas])

    def error_de_cierre(self, actor, *lineas):
        with self.assertRaises(ErrorDeCompras) as contexto:
            with self.captureOnCommitCallbacks(execute=True):
                recepciones.cerrar_con_faltante(actor, [(detalle.pk, motivo) for detalle, motivo in lineas])
        return contexto.exception

    def detalle(self, detalle):
        return DetalleOrdenCompra.objects.get(pk=detalle.pk)


class CmpCrrFltPostcondicionesTests(CmpCrrFltBase):
    """Postcondiciones a a g y el flujo básico."""

    def test_flujo_principal_cierra_la_linea_con_su_motivo_y_baja_el_transito_de_lo_que_falta(self):
        """Flujo básico (pasos 1 a 8) y postcondiciones a y b: el Agrónomo cierra la línea de las macetas de la que ya recibió 5 de 20: pasa a «cerrada con faltante» con su motivo y la fecha de cierre,
        y el tránsito baja en lo que faltaba (15); el stock actual no cambia."""
        self.registrar(self.ana, [self.linea(self.l_maceta, 5)])
        self.assertEqual(self.transito(self.maceta), D("15"))
        cerradas = self.cerrar(self.ana, (self.l_maceta, MOTIVO))
        self.assertEqual([d.pk for d in cerradas], [self.l_maceta.pk])
        linea = self.detalle(self.l_maceta)
        self.assertEqual((linea.estado_detalle_orden, linea.motivo_cierre_faltante, linea.fecha_cierre_faltante), ("cerrado_con_faltante", MOTIVO, self.hoy))
        self.assertEqual((self.transito(self.maceta), self.stock_de(self.maceta)), (D("0"), D("5")))
        verificar_invariantes(self.maceta)

    def test_post_a_se_puede_cerrar_una_linea_de_la_que_no_llego_nada(self):
        """Regla «Cierre con faltante»: se cierra aunque no haya llegado nada; la cantidad faltante es toda la pedida y el tránsito baja en eso."""
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual((self.transito(self.fertilizante), self.stock_de(self.fertilizante), self.detalle(self.l_fert).estado_detalle_orden), (D("0"), D("0"), "cerrado_con_faltante"))

    def test_post_a_el_motivo_se_guarda_sin_espacios_de_mas_y_cada_linea_tiene_el_suyo(self):
        """Regla «Cierre con faltante» (paso 4): cada línea lleva su propio motivo (texto libre); se guarda sin espacios en los extremos."""
        self.cerrar(self.ana, (self.l_fert, "  Se quemó el depósito.  "), (self.l_maceta, "No lo fabrican más."))
        self.assertEqual([self.detalle(d).motivo_cierre_faltante for d in (self.l_fert, self.l_maceta)], ["Se quemó el depósito.", "No lo fabrican más."])
        self.assertEqual((self.transito(self.fertilizante), self.transito(self.maceta)), (D("0"), D("0")))

    def test_post_c_la_orden_queda_recibida_con_faltante_si_todas_las_lineas_estan_completas_o_cerradas(self):
        """Postcondición c y regla «Estado de la orden» (regla 24 de 8.16): todas las líneas completas o cerradas y al menos una cerrada: «recibida con faltante»."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 20)])
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")
        self.cerrar(self.ana, (self.l_tomate, MOTIVO))
        self.assertEqual(self.estado_de_la_orden(), "recibida_con_faltante")

    def test_post_c_si_todo_se_cierra_sin_haber_recibido_nada_la_orden_queda_recibida_con_faltante(self):
        """Postcondición c: «todas completas o cerradas y al menos una cerrada» también vale si no se recibió nada de nada."""
        self.cerrar(self.gerente, (self.l_fert, MOTIVO), (self.l_maceta, MOTIVO), (self.l_tomate, MOTIVO))
        self.assertEqual(self.estado_de_la_orden(), "recibida_con_faltante")

    def test_post_c_si_quedan_lineas_pendientes_la_orden_sigue_como_estaba(self):
        """Postcondición c: «en otro caso siguió «parcialmente recibida» o «aprobada»»: sin recepciones sigue «aprobada»; con una recepción, «parcialmente recibida»."""
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual(self.estado_de_la_orden(), "aprobada")
        self.registrar(self.ana, [self.linea(self.l_maceta, 5)])
        self.cerrar(self.ana, (self.l_tomate, MOTIVO))
        self.assertEqual(self.estado_de_la_orden(), "parcialmente_recibida")

    def test_post_d_cerrar_puede_activar_la_alerta_de_insumo_bajo_el_minimo(self):
        """Postcondición d y regla «Tránsito»: al bajar el tránsito se reevalúan las alertas de bajo el mínimo (libre + tránsito < mínimo); puede activarse una nueva. Con mínimo 15, con 20 en tránsito
        no estaba bajo; sin él, sí."""
        InsumoInvernadero.objects.filter(pk=self.maceta.pk).update(cant_min_insumo=15)
        self.assertFalse(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).exists())
        self.cerrar(self.ana, (self.l_maceta, MOTIVO))
        alerta = Alerta.objects.get(tipo_alerta=BAJO_MINIMO, clave_estado=f"insumo:{self.maceta.pk}")
        self.assertEqual(alerta.estado_alerta, "activa")

    def test_regla_sin_asiento_cerrar_no_mueve_dinero_ni_toca_el_stock_ni_las_reservas(self):
        """Regla «Sin asiento» (D-90 punto 8, regla 14 de 8.20) y «Además»: no registra asiento ni pagos y no modifica el stock actual, la cantidad pedida, el precio ni los lotes y movimientos."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        asientos = AsientoContable.objects.count()
        lotes, movimientos = LoteInsumo.objects.count(), MovimientoInsumo.objects.count()
        pedida = list(DetalleOrdenCompra.objects.order_by("id").values_list("cantidad_detalle_orden", "total_linea"))
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual((AsientoContable.objects.count(), LoteInsumo.objects.count(), MovimientoInsumo.objects.count()), (asientos, lotes, movimientos))
        self.assertEqual(list(DetalleOrdenCompra.objects.order_by("id").values_list("cantidad_detalle_orden", "total_linea")), pedida)
        self.assertEqual(self.stock_de(self.fertilizante), D("4"))

    def test_post_se_pueden_cerrar_lineas_de_varios_invernaderos_proveedores_y_ordenes_a_la_vez(self):
        """Paso 2 (líneas «agrupadas por orden, proveedor e invernadero»): una sola operación cierra líneas de A en Norte, de B en Norte 2 y de otra orden de Ana; cada una baja el tránsito de su existencia."""
        otra, linea_otra, iin_otra = self.otra_orden(self.ana, self.norte2, "Sustrato")
        self.cerrar(self.ana, (self.l_fert, MOTIVO), (self.l_tomate, MOTIVO), (linea_otra, "No llegó el camión."))
        self.assertEqual((self.transito(self.fertilizante), self.transito(self.tomate), self.transito(iin_otra)), (D("0"), D("0"), D("0")))
        self.assertEqual(self.detalle(linea_otra).estado_detalle_orden, "cerrado_con_faltante")
        self.assertEqual(self.estado_de_la_orden(), "aprobada")  # a esta orden todavía le queda la maceta

    # --- avisos (postcondición f) ---

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_f_cada_proveedor_recibe_un_correo_que_avisa_que_no_se_espera_el_resto_de_sus_lineas_cerradas(self):
        """Postcondición f y decisión R1: se le avisa por correo al proveedor que no se espera el resto de las líneas cerradas: uno por proveedor, solo con sus líneas y sin mencionar a los otros."""
        self.registrar(self.ana, [self.linea(self.l_maceta, 5)])
        mail.outbox.clear()
        self.cerrar(self.ana, (self.l_maceta, MOTIVO), (self.l_tomate, MOTIVO))
        por_destino = {m.to[0]: m for m in mail.outbox}
        self.assertEqual(set(por_destino), {self.proveedor.email_proveedor, self.proveedor_b.email_proveedor})
        correo_a, correo_b = por_destino[self.proveedor.email_proveedor], por_destino[self.proveedor_b.email_proveedor]
        for correo in (correo_a, correo_b):
            self.assertIn(str(self.orden), correo.subject)
        self.assertIn("Maceta", correo_a.body)
        self.assertIn(texto_cantidad(D("15"), "unidad"), correo_a.body)  # lo que no se espera: 20 − 5
        self.assertNotIn("Tomate", correo_a.body)
        self.assertNotIn(self.proveedor_b.nombre_para_mostrar, correo_a.body)
        self.assertIn("Tomate", correo_b.body)
        self.assertNotIn("Maceta", correo_b.body)

    @override_settings(CORREO_CONFIGURADO=True, EMAIL_BACKEND=BACKEND_QUE_FALLA)
    def test_ext_7b_si_el_correo_no_sale_el_cierre_queda_registrado(self):
        """Extensión 7b: si no se logra enviar el correo al proveedor, el cierre permanece registrado."""
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual(self.detalle(self.l_fert).estado_detalle_orden, "cerrado_con_faltante")

    @override_settings(CORREO_CONFIGURADO=False)
    def test_ext_7b_sin_el_correo_configurado_no_sale_nada_y_el_cierre_se_registra(self):
        """D-33: sin el correo configurado no sale ningún correo y el cierre se registra igual."""
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual((len(mail.outbox), self.detalle(self.l_fert).estado_detalle_orden), (0, "cerrado_con_faltante"))

    # --- auditoría (postcondición g) ---

    def test_post_g_un_registro_de_cierre_con_faltante_nombra_la_orden_y_las_lineas_cerradas(self):
        """Postcondición g y D-36: un registro ``cierre_con_faltante`` de quien actuó, con la orden y cada línea cerrada entre los afectados, el cambio de estado de la orden en ``cambios`` y las líneas
        y sus motivos en ``datos``."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 20)])
        self.cerrar(self.ana, (self.l_tomate, MOTIVO))
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.CIERRE_CON_FALTANTE)
        self.assertEqual(registro.usuario_id, self.ana.pk)
        self.assertLessEqual({("compras.ordencompra", self.orden.pk), ("compras.detalleordencompra", self.l_tomate.pk)}, {(a["modelo"], a["id"]) for a in registro.afectados})
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": "parcialmente_recibida", "despues": "recibida_con_faltante"})
        self.assertEqual(registro.detalle["datos"]["lineas_cerradas"], [ref(self.l_tomate)])
        self.assertEqual(registro.detalle["datos"]["motivos_de_cierre"], [f"{self.l_tomate}: {MOTIVO}"])

    def test_post_g_cada_insumo_del_invernadero_modificado_tiene_su_registro_con_el_transito_antes_y_despues(self):
        """Postcondición g y D-87 punto 8: una ``modificacion_insumo_invernadero`` por existencia, con la cantidad en tránsito antes y después."""
        self.cerrar(self.ana, (self.l_maceta, MOTIVO))
        registro = RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO, afectados__0__id=self.maceta.pk).order_by("-id").first()
        self.assertEqual(registro.detalle["cambios"]["transito"], {"antes": "20", "despues": "0"})

    def test_post_g_el_gerente_queda_en_la_auditoria_como_quien_cerro(self):
        """Extensión 1a: si cierra el Gerente porque el Agrónomo no está, él queda en el registro de auditoría."""
        self.cerrar(self.gerente, (self.l_fert, MOTIVO))
        self.assertEqual(RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.CIERRE_CON_FALTANTE).usuario_id, self.gerente.pk)


class CmpCrrFltReglasTests(CmpCrrFltBase):
    """Permisos, extensiones de error y atomicidad. Cada rechazo verifica que no cambió nada."""

    def test_regla_quien_cierra_es_el_agronomo_a_cargo_de_cada_linea_o_el_gerente(self):
        """Precondición a y extensión 1a: el Agrónomo activo a cargo del invernadero de cada línea o el Gerente activo; otro Agrónomo, otros roles, una cuenta inactiva o sin cuenta: ``PermissionDenied``,
        sin cambios."""
        antes = self.instantanea()
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        for actor in (self.beto, crear_capataz(), crear_vendedor(), crear_administrador(), contador, crear_agronomo(email="baja@infoponia.com", activo=False), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    recepciones.cerrar_con_faltante(actor, [(self.l_fert.pk, MOTIVO)])
        self.sin_cambios(antes)

    def test_regla_una_sola_linea_ajena_rechaza_todo_el_cierre(self):
        """Regla «Quién cierra»: si una de las líneas es de un invernadero que el Agrónomo no tiene a cargo, no se cierra ninguna (``PermissionDenied``)."""
        otra, linea_sur, _ = self.otra_orden(self.beto, self.sur, "Sustrato")
        antes = self.instantanea()
        with self.assertRaises(PermissionDenied):
            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, MOTIVO), (linea_sur.pk, MOTIVO)])
        self.sin_cambios(antes)

    def test_ext_3_el_cierre_necesita_al_menos_una_linea(self):
        """Paso 3: sin líneas elegidas no hay cierre (``sin_lineas``)."""
        antes = self.instantanea()
        with self.assertRaises(ErrorDeCompras) as contexto:
            recepciones.cerrar_con_faltante(self.ana, [])
        self.assertEqual(contexto.exception.codigo, "sin_lineas")
        self.sin_cambios(antes)

    def test_ext_4a_el_motivo_de_cada_linea_es_obligatorio(self):
        """Extensión 4a y regla «Cierre con faltante»: falta el motivo de alguna línea (vacío o solo espacios): ``motivo_obligatorio`` con las líneas afectadas; no se cierra ninguna."""
        antes = self.instantanea()
        error = self.error_de_cierre(self.ana, (self.l_fert, MOTIVO), (self.l_maceta, "   "))
        self.assertEqual((error.codigo, error.datos["lineas"]), ("motivo_obligatorio", [self.l_maceta.pk]))
        self.assertEqual(self.error_de_cierre(self.ana, (self.l_fert, "")).codigo, "motivo_obligatorio")
        self.sin_cambios(antes)

    def test_ext_7a_una_linea_que_ya_no_esta_pendiente_no_se_cierra_y_no_se_cierra_ninguna(self):
        """Extensión 7a y «Los cierres no se deshacen» (decisión R2): una línea ya completa o ya cerrada (otra sesión la recibió o la cerró) no se cierra otra vez: ``linea_no_pendiente`` con las
        afectadas, y no se cierra ninguna de las demás ni se resta dos veces el tránsito."""
        DetalleOrdenCompra.objects.filter(pk=self.l_maceta.pk).update(estado_detalle_orden="completo")
        antes = self.instantanea()
        error = self.error_de_cierre(self.ana, (self.l_fert, MOTIVO), (self.l_maceta, MOTIVO))
        self.assertEqual((error.codigo, error.datos["lineas"]), ("linea_no_pendiente", [self.l_maceta.pk]))
        self.sin_cambios(antes)
        self.cerrar(self.ana, (self.l_fert, MOTIVO))
        self.assertEqual(self.error_de_cierre(self.ana, (self.l_fert, MOTIVO)).codigo, "linea_no_pendiente")
        self.assertEqual(self.transito(self.fertilizante), D("0"))  # no se restó dos veces

    def test_regla_una_linea_repetida_en_el_mismo_pedido_se_rechaza_y_no_resta_el_transito_dos_veces(self):
        """Regla «Los cierres no se restan dos veces» (requisito de concurrencia): la misma línea dos veces en un mismo cierre es ``linea_repetida`` y no cambia nada."""
        antes = self.instantanea()
        self.assertEqual(self.error_de_cierre(self.ana, (self.l_fert, MOTIVO), (self.l_fert, MOTIVO)).codigo, "linea_repetida")
        self.sin_cambios(antes)

    def test_regla_una_linea_que_no_existe_es_un_error_de_negocio_y_no_cierra_nada(self):
        """Una línea que no existe no se cierra (``linea_no_pendiente``): el resto del pedido tampoco."""
        antes = self.instantanea()
        with self.assertRaises(ErrorDeCompras) as contexto:
            recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, MOTIVO), (999999, MOTIVO)])
        self.assertEqual(contexto.exception.codigo, "linea_no_pendiente")
        self.sin_cambios(antes)

    def test_regla_todo_o_nada_si_falla_a_mitad_no_queda_ningun_cierre(self):
        """Garantías mínimas y «el registro es una única transacción»: si algo falla después de cerrar la primera línea, no cambia el estado de ninguna línea ni de la orden, ni el tránsito, las alertas
        ni los logs; no sale ningún correo."""
        antes = self.instantanea()
        real, llamadas = stock.restar_transito, []

        def falla_la_segunda(*args, **kwargs):
            llamadas.append(args)
            if len(llamadas) == 2:
                raise RuntimeError("falla del segundo tránsito")
            return real(*args, **kwargs)

        with mock.patch.object(stock, "restar_transito", side_effect=falla_la_segunda):
            with self.assertRaises(RuntimeError):
                with self.captureOnCommitCallbacks(execute=True):
                    recepciones.cerrar_con_faltante(self.ana, [(self.l_fert.pk, MOTIVO), (self.l_maceta.pk, MOTIVO)])
        self.assertEqual(len(llamadas), 2)
        self.sin_cambios(antes)


class CmpCrrFltConsultasTests(CmpCrrFltBase):
    """Paso 2 (las líneas pendientes) y paso 5 (el resumen). Solo leen."""

    def test_paso_2_las_lineas_pendientes_de_los_invernaderos_del_agronomo_con_lo_que_falta(self):
        """Paso 2: las líneas pendientes de las órdenes de los invernaderos del Agrónomo, agrupadas por orden, proveedor e invernadero: insumo, pedida, recibida, lo que falta, la entrega esperada y su atraso."""
        self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence)])
        lineas = recepciones.lineas_pendientes_de_cierre(self.ana)
        self.assertEqual([(l.proveedor.pk, l.invernadero.pk, l.detalle.pk) for l in lineas], [(self.proveedor.pk, self.norte.pk, self.l_fert.pk), (self.proveedor.pk, self.norte.pk, self.l_maceta.pk), (self.proveedor_b.pk, self.norte2.pk, self.l_tomate.pk)])
        fert = lineas[0]
        self.assertEqual((fert.orden.pk, fert.insumo.nombre_insumo, fert.pedida, fert.recibida, fert.falta, fert.atraso_dias), (self.orden.pk, "Fertilizante", D("10"), D("4"), D("6"), 0))

    def test_ext_1a_el_gerente_ve_las_lineas_de_todos_los_invernaderos(self):
        """Extensión 1a (paso 2): el Gerente ve las líneas pendientes de todos los invernaderos; Beto, a cargo de Sur, no ve ninguna de esta orden."""
        self.otra_orden(self.beto, self.sur, "Sustrato")
        self.assertEqual(len(recepciones.lineas_pendientes_de_cierre(self.gerente)), 4)
        self.assertEqual(len(recepciones.lineas_pendientes_de_cierre(self.beto)), 1)

    def test_paso_2_con_la_orden_solo_se_ven_las_lineas_de_esa_orden(self):
        """Paso 1: se llega desde la ficha de la orden: se muestran solo las líneas pendientes de esa orden."""
        otra, linea_otra, _ = self.otra_orden(self.ana, self.norte2, "Sustrato")
        self.assertEqual({l.orden.pk for l in recepciones.lineas_pendientes_de_cierre(self.ana, orden_id=otra.pk)}, {otra.pk})
        self.assertEqual(len(recepciones.lineas_pendientes_de_cierre(self.ana, orden_id=self.orden.pk)), 3)

    def test_ext_2a_desde_una_recepcion_solo_se_ven_sus_lineas_que_siguen_pendientes(self):
        """Extensión 2a (11a de la recepción): «presenta solo las líneas pendientes de esa recepción»: las que recibió esa recepción y todavía no están completas."""
        recepcion = self.registrar(self.ana, [self.linea(self.l_fert, 4, self.vence), self.linea(self.l_maceta, 20)])
        self.assertEqual([l.detalle.pk for l in recepciones.lineas_pendientes_de_cierre(self.ana, recepcion_id=recepcion.pk)], [self.l_fert.pk])

    def test_regla_solo_el_agronomo_y_el_gerente_ven_las_lineas_a_cerrar(self):
        """Precondición a: otros roles, una cuenta inactiva o sin cuenta: ``PermissionDenied``."""
        for actor in (crear_capataz(), crear_vendedor(), crear_cuenta(Contador, email="contador@infoponia.com"), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    recepciones.lineas_pendientes_de_cierre(actor)

    def test_paso_5_el_resumen_dice_la_cantidad_faltante_el_transito_el_estado_de_la_orden_y_los_pagos(self):
        """Paso 5: por línea, la cantidad faltante y cómo cambia el tránsito; el estado en que quedará la orden; si cada proveedor queda para pagar (todas sus líneas completas o cerradas y algo recibido) o
        sin pago; y las existencias que pasarán a estar bajo el mínimo. No escribe nada."""
        self.registrar(self.ana, [self.linea(self.l_fert, 10, self.vence), self.linea(self.l_maceta, 5)])
        InsumoInvernadero.objects.filter(pk=self.maceta.pk).update(cant_min_insumo=15)
        antes = self.instantanea()
        resumen = recepciones.resumir_cierre(self.ana, [(self.l_maceta.pk, MOTIVO), (self.l_tomate.pk, MOTIVO)])
        self.assertEqual(self.instantanea(), antes)
        maceta, tomate = resumen.lineas
        self.assertEqual((maceta.detalle.pk, maceta.falta, maceta.transito_antes, maceta.transito_despues, maceta.motivo), (self.l_maceta.pk, D("15"), D("15"), D("0"), MOTIVO))
        self.assertEqual((tomate.falta, tomate.transito_antes, tomate.transito_despues), (D("8"), D("8"), D("0")))
        self.assertEqual(resumen.estados_de_ordenes, {self.orden.pk: "recibida_con_faltante"})
        self.assertEqual({p.pk: queda for p, queda in resumen.proveedores}, {self.proveedor.pk: True, self.proveedor_b.pk: False})  # B no recibió nada: sin pago
        self.assertEqual([i.pk for i in resumen.alertas_que_se_activan], [self.maceta.pk])

    def test_paso_5_el_resumen_aplica_las_mismas_validaciones_que_el_cierre(self):
        """Paso 5: mismas precondiciones que el cierre (permisos, motivo, línea pendiente); no escribe."""
        with self.assertRaises(PermissionDenied):
            recepciones.resumir_cierre(self.beto, [(self.l_fert.pk, MOTIVO)])
        with self.assertRaises(ErrorDeCompras) as contexto:
            recepciones.resumir_cierre(self.ana, [(self.l_fert.pk, "")])
        self.assertEqual(contexto.exception.codigo, "motivo_obligatorio")
        DetalleOrdenCompra.objects.filter(pk=self.l_fert.pk).update(estado_detalle_orden="completo")
        with self.assertRaises(ErrorDeCompras) as contexto:
            recepciones.resumir_cierre(self.ana, [(self.l_fert.pk, MOTIVO)])
        self.assertEqual(contexto.exception.codigo, "linea_no_pendiente")
