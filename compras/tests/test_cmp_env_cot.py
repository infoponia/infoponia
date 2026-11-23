# Pruebas de CMP-ENV-COT · Enviar Cotización (CMP-02a, paso 4): el servicio (``compras/servicios/cotizaciones.py``) y las vistas públicas del portal del
# proveedor (``compras/views_proveedor.py``). Fuente: docs/casos_de_uso/compras/pedidos.md (CMP-ENV-COT v0.2 con las «Actualizaciones de A0»: cantidad mayor que
# la pedida, total por línea o unitario, plazo ≥ 1), D-88 y D-89. El módulo se toma dentro de cada prueba (``perezoso``).
#
# Contrato del servicio. ``lineas = [(detalle_pedido_id, cantidad, total | None, unitario | None, plazo)]``: exactamente uno de total o unitario.
# Errores de los datos: ``ValidationError`` por campo (``lineas`` sin_lineas; ``detalle_<id>`` detalle_invalido / detalle_repetido; ``cantidad_<id>``
# cantidad_invalida / decimales_de_la_unidad; ``precio_<id>`` precio_invalido / precio_ambiguo; ``plazo_<id>`` plazo_invalido; ``validez``
# validez_invalida; ``observaciones`` observaciones_largas). Del estado: ``ErrorDeCompras`` con ``enlace_no_sirve`` (``datos["situacion"]``, ver
# ``enlaces.situacion_del_enlace``) o ``ya_cotizo`` (extensiones 2b y 11b).
# Contrato del portal. POST a /proveedor/enlace/ con ``accion`` = revisar | enviar, ``modo`` = total | unitario, por detalle ``cantidad_<id>``,
# ``precio_<id>`` y ``plazo_<id>`` (una línea sin ninguno de los tres no se cotiza), ``validez`` (AAAA-MM-DD) y ``observaciones``.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, DetalleCotizacion, EnlaceProveedor, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_gerente
from inventario.models import MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.servicios import configuracion
from maestros.tests.fabricas import codigos_de, crear_agronomo_con_invernadero, crear_invernadero, error_de

cotizaciones = perezoso("compras.servicios.cotizaciones")


def en(dias):
    """La fecha de hoy más ``dias`` días."""
    return timezone.localdate() + timedelta(days=dias)


class CotizacionBase(ConDatosDeInventario, TestCase):
    """Un pedido de 20 lechugas (por unidad) y 3 kg de nutriente, con la fecha límite dentro de 3 días y dos proveedores invitados."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero("Invernadero Norte")
        self.gerente = crear_gerente()
        self.lechuga = existencia(insumo("Lechuga", unidad="unidad", descripcion="Plantín"), self.invernadero, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.invernadero, minimo=5, precio="100.00")
        self.pedido = armar_pedido(self.agronomo, dias_al_limite=3)
        self.d_lechuga = detalle_de_pedido(self.pedido, self.lechuga, cantidad="20")
        self.d_nutriente = detalle_de_pedido(self.pedido, self.nutriente, cantidad="3")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.enlace_sur, self.token_sur = enlace_de(invitar(self.pedido, self.sur))
        self.enlace_este, self.token_este = enlace_de(invitar(self.pedido, self.este))
        self.validez = en(10)

    def enviar(self, enlace=None, lineas=None, validez=None, observaciones="", ejecutar=True):
        """``registrar_cotizacion`` con los avisos y el acuse ejecutados (``on_commit``). Devuelve la cotización."""
        lineas = lineas if lineas is not None else [(self.d_lechuga.pk, "20", "250.00", None, 3)]
        with self.captureOnCommitCallbacks(execute=ejecutar):
            return cotizaciones.registrar_cotizacion((enlace or self.enlace_sur).pk, lineas, validez or self.validez, observaciones)

    def datos_de_error(self, lineas=None, validez=None, observaciones=""):
        """El ``ValidationError`` que da ``resumir_cotizacion`` con esos datos."""
        lineas = lineas if lineas is not None else [(self.d_lechuga.pk, "20", "250.00", None, 3)]
        return error_de(lambda: cotizaciones.resumir_cotizacion(self.enlace_sur, lineas, validez or self.validez, observaciones))


@override_settings(CORREO_CONFIGURADO=True)
class RegistroDeLaCotizacionTests(CotizacionBase):
    """Paso 11: qué queda registrado (postcondiciones a a f y garantías mínimas)."""

    def test_post_a_la_cotizacion_nace_propuesta_con_su_fecha_validez_observaciones_y_monto(self):
        """Postcondición a: «propuesta», asociada al proveedor, con la fecha de hoy, la validez, las observaciones y el monto = Σ de los subtotales."""
        cotizacion = self.enviar(
            lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3), (self.d_nutriente.pk, "3", None, "40.10", 2)],
            observaciones="Entrega en cajones",
        )
        self.assertEqual((cotizacion.estado_cotizacion, cotizacion.proveedor_id, cotizacion.pedido_id), ("propuesta", self.sur.pk, self.pedido.pk))
        self.assertEqual((cotizacion.fecha_cotizacion, cotizacion.fecha_validez_cotizacion), (timezone.localdate(), self.validez))
        self.assertEqual(cotizacion.observaciones_cotizacion, "Entrega en cajones")
        self.assertEqual(cotizacion.monto_cotizacion, Decimal("370.30"))  # 250,00 + 3 × 40,10 = 120,30

    def test_post_b_una_linea_por_detalle_cotizado_con_cantidad_total_y_plazo(self):
        """Postcondición b y D-89: una línea por detalle cotizado; se guarda el TOTAL (del unitario cargado se calcula: 3 × 40,10 = 120,30)."""
        cotizacion = self.enviar(lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3), (self.d_nutriente.pk, "3", None, "40.10", 2)])
        lineas = {l.detalle_pedido_id: l for l in cotizacion.lineas.all()}
        self.assertEqual((lineas[self.d_lechuga.pk].cantidad_cotizada, lineas[self.d_lechuga.pk].total_linea, lineas[self.d_lechuga.pk].plazo_entrega_dias),
                         (Decimal("20"), Decimal("250.00"), 3))
        self.assertEqual((lineas[self.d_nutriente.pk].total_linea, lineas[self.d_nutriente.pk].plazo_entrega_dias), (Decimal("120.30"), 2))

    def test_regla_cotizar_algunos_detalles_no_todos_es_valido(self):
        """Flujo principal: el proveedor cotiza algunos detalles, no todos; los demás quedan sin cotizar."""
        cotizacion = self.enviar()
        self.assertEqual(cotizacion.lineas.count(), 1)

    def test_post_c_el_enlace_queda_usado_con_su_fecha_de_uso(self):
        """Postcondición c y D-88 punto 3: el enlace queda ``usado`` (sin servir para nuevos envíos) y con su fecha de uso."""
        self.enviar()
        self.enlace_sur.refresh_from_db()
        self.assertEqual(self.enlace_sur.estado, "usado")
        self.assertIsNotNone(self.enlace_sur.fecha_uso)
        self.enlace_este.refresh_from_db()
        self.assertEqual(self.enlace_este.estado, "vigente")  # el de otro proveedor no se toca

    def test_post_d_el_proveedor_recibe_el_acuse_con_el_detalle_de_su_cotizacion(self):
        """Postcondición d y 12a: acuse por correo con el pedido, fecha y hora, cada línea (insumo, destino, cantidad, unitario, subtotal, plazo), el monto, la validez y las observaciones."""
        self.enviar(lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3)], observaciones="Entrega en cajones")
        acuse = next(m for m in mail.outbox if m.to == ["ventas@sur.com"])
        for texto in (str(self.pedido), "Lechuga", "Invernadero Norte", "20", "250,00", "12,50", "3 días", "Entrega en cajones", self.validez.strftime("%d/%m/%Y")):
            self.assertIn(texto, acuse.body)

    def test_post_f_una_auditoria_con_origen_proveedor_mediante_enlace(self):
        """Postcondición f y D-88 punto 5: una acción ``alta_cotizacion`` sin cuenta y con ``rol_externo`` = proveedor; el proveedor, el pedido, la cotización y cada línea van como afectados; ni el token ni su resumen."""
        cotizacion = self.enviar(lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3), (self.d_nutriente.pk, "3", "120.00", None, 2)])
        registro = RegistroAuditoria.objects.get(accion="alta_cotizacion")
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.rol, "proveedor_enlace")
        self.assertEqual(registro.rol_visible(), "Proveedor (mediante enlace)")
        modelos = [a["modelo"] for a in registro.afectados]
        self.assertEqual(sorted(modelos), ["compras.cotizacion", "compras.detallecotizacion", "compras.detallecotizacion", "compras.pedido", "compras.proveedor"])
        self.assertEqual(registro.detalle["cambios"]["monto_cotizacion"], {"antes": None, "despues": "370.00"})
        self.assertEqual(registro.detalle["cambios"]["estado"]["despues"], "propuesta")
        texto = str(registro.detalle) + str(registro.afectados)
        self.assertNotIn(self.token_sur, texto)
        self.assertNotIn(self.enlace_sur.token_resumen, texto)
        self.assertEqual(str(cotizacion), next(a["texto"] for a in registro.afectados if a["modelo"] == "compras.cotizacion"))

    def test_garantia_el_envio_no_modifica_el_pedido_ni_el_stock(self):
        """Garantías mínimas: no cambia el estado del pedido, sus detalles, el stock ni la contabilidad."""
        movimientos = MovimientoInsumo.objects.count()
        self.enviar()
        self.pedido.refresh_from_db()
        self.lechuga.refresh_from_db()
        self.assertEqual((self.pedido.estado_pedido, self.pedido.detalles.count()), ("en_cotizacion", 2))
        self.assertEqual((self.lechuga.cant_transito_insumo, MovimientoInsumo.objects.count()), (0, movimientos))
        self.assertEqual(self.d_lechuga.cantidad_detalle, Decimal("20"))

    def test_garantia_si_falla_el_registro_no_queda_nada_y_el_enlace_sigue_sirviendo(self):
        """Garantías mínimas y extensión *b: atómico; si la auditoría falla, no hay cotización, línea, aviso ni correo, y el enlace sigue vigente."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    cotizaciones.registrar_cotizacion(self.enlace_sur.pk, [(self.d_lechuga.pk, "20", "250.00", None, 3)], self.validez, "")
        self.assertEqual((pendientes, mail.outbox), ([], []))
        self.assertEqual((Cotizacion.objects.count(), DetalleCotizacion.objects.count(), Notificacion.objects.count()), (0, 0, 0))
        self.enlace_sur.refresh_from_db()
        self.assertEqual((self.enlace_sur.estado, self.enlace_sur.fecha_uso), ("vigente", None))

    def test_ext_12a_si_el_acuse_no_sale_la_cotizacion_permanece(self):
        """Extensión 12a: la cotización permanece registrada si no se logra enviar el acuse (no hay reintento automático)."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            cotizacion = self.enviar()
        self.assertTrue(Cotizacion.objects.filter(pk=cotizacion.pk).exists())
        self.enlace_sur.refresh_from_db()
        self.assertEqual(self.enlace_sur.estado, "usado")

    def test_ext_12a_con_el_correo_sin_configurar_la_cotizacion_se_registra_igual(self):
        """Extensión 12a y API de correo (regla 5): sin el correo configurado el acuse no sale y nada falla."""
        with override_settings(CORREO_CONFIGURADO=False):
            self.enviar()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Cotizacion.objects.count(), 1)


class ReglasDeLaLineaTests(CotizacionBase):
    """Pasos 5 y 6: cantidad, precio y plazo (extensiones 6a, 6b y 6c con las actualizaciones de A0)."""

    def test_regla_cantidad_cotizada_puede_superar_la_pedida(self):
        """CMP-ENV-COT regla «Cantidad cotizada» y P2: puede ser mayor que la pedida; se propone la pedida."""
        cotizacion = self.enviar(lineas=[(self.d_lechuga.pk, "30", "300.00", None, 1)])
        self.assertEqual(cotizacion.lineas.get().cantidad_cotizada, Decimal("30"))

    def test_ext_6a_cantidad_no_mayor_que_cero_o_con_mas_decimales_de_los_que_admite_la_unidad(self):
        """Extensión 6a (con A0): se rechaza no mayor que cero o con más decimales que la unidad (la lechuga es por unidad; el kg admite 3)."""
        for cantidad, codigo in (("0", "cantidad_invalida"), ("-1", "cantidad_invalida"), ("", "cantidad_invalida"), ("abc", "cantidad_invalida"), ("2.5", "decimales_de_la_unidad")):
            with self.subTest(cantidad=cantidad):
                error = self.datos_de_error(lineas=[(self.d_lechuga.pk, cantidad, "10.00", None, 1)])
                self.assertEqual(codigos_de(error, f"cantidad_{self.d_lechuga.pk}"), [codigo])
        cotizaciones.resumir_cotizacion(self.enlace_sur, [(self.d_nutriente.pk, "2.125", "10.00", None, 1)], self.validez, "")

    def test_ext_6b_el_precio_tiene_que_ser_mayor_que_cero_y_con_hasta_dos_decimales(self):
        """Extensión 6b: se aplica al que cargó (total o unitario): mayor que cero y con hasta dos decimales."""
        campo = f"precio_{self.d_lechuga.pk}"
        for total, unitario in (("0", None), ("-5", None), ("10.001", None), ("abc", None), (None, "0"), (None, "1.234"), (None, "-1")):
            with self.subTest(total=total, unitario=unitario):
                error = self.datos_de_error(lineas=[(self.d_lechuga.pk, "20", total, unitario, 1)])
                self.assertEqual(codigos_de(error, campo), ["precio_invalido"])

    def test_d89_punto_2_se_carga_el_total_o_el_unitario_pero_no_los_dos_ni_ninguno(self):
        """D-89 punto 2: exactamente uno de total o unitario."""
        campo = f"precio_{self.d_lechuga.pk}"
        self.assertEqual(codigos_de(self.datos_de_error(lineas=[(self.d_lechuga.pk, "20", "250.00", "12.50", 1)]), campo), ["precio_ambiguo"])
        self.assertEqual(codigos_de(self.datos_de_error(lineas=[(self.d_lechuga.pk, "20", None, None, 1)]), campo), ["precio_invalido"])
        self.assertEqual(codigos_de(self.datos_de_error(lineas=[(self.d_lechuga.pk, "20", "", "", 1)]), campo), ["precio_invalido"])

    def test_d89_el_total_calculado_desde_el_unitario_se_redondea_a_dos_decimales(self):
        """D-89 punto 2: del unitario se calcula el total con ``ROUND_HALF_UP`` a dos decimales; lo que se guarda es el total."""
        cotizacion = self.enviar(lineas=[(self.d_nutriente.pk, "2.5", None, "3.33", 1)])
        self.assertEqual(cotizacion.lineas.get().total_linea, Decimal("8.33"))  # 8,325 → 8,33

    def test_ext_6c_el_plazo_es_un_entero_de_uno_o_mas(self):
        """Extensión 6c con A0 (P2, MD-130): falta, cero, negativo, con decimales o texto → ``plazo_invalido``; 1 se acepta."""
        for plazo in (None, "", 0, "0", -2, "1.5", "tres"):
            with self.subTest(plazo=plazo):
                error = self.datos_de_error(lineas=[(self.d_lechuga.pk, "20", "250.00", None, plazo)])
                self.assertEqual(codigos_de(error, f"plazo_{self.d_lechuga.pk}"), ["plazo_invalido"])
        resumen = cotizaciones.resumir_cotizacion(self.enlace_sur, [(self.d_lechuga.pk, "20", "250.00", None, "1")], self.validez, "")
        self.assertEqual(resumen.lineas[0].plazo, 1)

    def test_ext_8a_una_cotizacion_sin_ningun_detalle_se_rechaza(self):
        """Extensión 8a: la cotización incluye al menos un detalle."""
        self.assertEqual(codigos_de(self.datos_de_error(lineas=[]), "lineas"), ["sin_lineas"])

    def test_regla_cada_linea_es_de_un_detalle_de_este_pedido_y_no_se_repite(self):
        """Modelo «Cotizacion» (técnico): que cada línea sea de un detalle de ese pedido lo garantiza el servicio; a lo sumo una línea por detalle."""
        otro = armar_pedido(self.agronomo)
        ajeno = detalle_de_pedido(otro, self.lechuga)
        error = self.datos_de_error(lineas=[(ajeno.pk, "5", "10.00", None, 1)])
        self.assertEqual(codigos_de(error, f"detalle_{ajeno.pk}"), ["detalle_invalido"])
        error = self.datos_de_error(lineas=[(self.d_lechuga.pk, "5", "10.00", None, 1), (self.d_lechuga.pk, "6", "11.00", None, 1)])
        self.assertEqual(codigos_de(error, f"detalle_{self.d_lechuga.pk}"), ["detalle_repetido"])

    def test_ext_9a_la_validez_es_obligatoria_y_no_anterior_a_la_fecha_limite(self):
        """Extensión 9a: falta o es anterior a la fecha límite → ``validez_invalida``; la fecha límite misma se acepta."""
        limite = self.pedido.fecha_limite_cotizaciones
        for validez in (limite - timedelta(days=1), timezone.localdate()):
            with self.subTest(validez=validez):
                error = error_de(lambda: cotizaciones.resumir_cotizacion(self.enlace_sur, [(self.d_lechuga.pk, "20", "250.00", None, 1)], validez, ""))
                self.assertEqual(codigos_de(error, "validez"), ["validez_invalida"])
        error = error_de(lambda: cotizaciones.resumir_cotizacion(self.enlace_sur, [(self.d_lechuga.pk, "20", "250.00", None, 1)], None, ""))
        self.assertEqual(codigos_de(error, "validez"), ["validez_invalida"])
        cotizaciones.resumir_cotizacion(self.enlace_sur, [(self.d_lechuga.pk, "20", "250.00", None, 1)], limite, "")

    def test_regla_validez_propuesta_es_la_fecha_limite_mas_los_dias_de_la_configuracion(self):
        """Regla «Validez de la cotización»: se propone fecha límite + ``dias_validez_cotizacion``, leído de la configuración en cada uso."""
        fila = configuracion.obtener()
        fila.dias_validez_cotizacion = 4
        fila.save(update_fields=["dias_validez_cotizacion"])
        self.assertEqual(cotizaciones.proponer_validez(self.pedido), self.pedido.fecha_limite_cotizaciones + timedelta(days=4))

    def test_regla_observaciones_opcionales_hasta_mil_caracteres(self):
        """Modelo «Cotizacion»: observaciones opcionales de hasta 1000 caracteres."""
        self.assertEqual(codigos_de(self.datos_de_error(observaciones="x" * 1001), "observaciones"), ["observaciones_largas"])
        self.enviar(observaciones="x" * 1000)

    def test_post_el_resumen_muestra_lineas_subtotales_monto_y_no_escribe_nada(self):
        """Paso 9: cada línea con insumo, destino, cantidad, unitario (cuatro decimales internos), subtotal y plazo; el monto; la validez y las observaciones. No escribe."""
        resumen = cotizaciones.resumir_cotizacion(
            self.enlace_sur, [(self.d_lechuga.pk, "20", "250.00", None, 3), (self.d_nutriente.pk, "3", None, "40.10", 2)], self.validez, "Obs"
        )
        self.assertEqual(resumen.monto, Decimal("370.30"))
        self.assertEqual([(l.detalle.pk, l.cantidad, l.total, l.unitario, l.plazo) for l in resumen.lineas],
                         [(self.d_lechuga.pk, Decimal("20"), Decimal("250.00"), Decimal("12.5000"), 3),
                          (self.d_nutriente.pk, Decimal("3.000"), Decimal("120.30"), Decimal("40.1000"), 2)])
        self.assertEqual((resumen.validez, resumen.observaciones), (self.validez, "Obs"))
        self.assertEqual((Cotizacion.objects.count(), RegistroAuditoria.objects.filter(accion="alta_cotizacion").count(), mail.outbox), (0, 0, []))


class EstadoDelEnlaceAlRegistrarTests(CotizacionBase):
    """Extensiones 2a, 2b, 11a y 11b: lo que cambia entre abrir y registrar."""

    def rechazo(self, **kwargs):
        """El ``ErrorDeCompras`` de enviar con el estado actual; falla la prueba si no lo lanza."""
        with self.assertRaises(ErrorDeCompras) as contexto:
            cotizaciones.registrar_cotizacion(self.enlace_sur.pk, [(self.d_lechuga.pk, "20", "250.00", None, 3)], self.validez, "")
        return contexto.exception

    def assert_no_registro(self):
        self.assertEqual((Cotizacion.objects.count(), RegistroAuditoria.objects.filter(accion="alta_cotizacion").count(), Notificacion.objects.count()), (0, 0, 0))
        self.enlace_sur.refresh_from_db()
        self.assertEqual(self.enlace_sur.estado, "vigente")

    def test_ext_11a_vencio_la_fecha_limite(self):
        """Extensión 11a: al registrar venció la fecha límite (el enlace sirve hasta el final de ese día): no se registra nada y se informa el motivo."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-6), fecha_limite_cotizaciones=en(-1))
        error = self.rechazo()
        self.assertEqual((error.codigo, error.datos["situacion"]), ("enlace_no_sirve", "vencido"))
        self.assert_no_registro()

    def test_regla_el_dia_de_la_fecha_limite_todavia_se_puede_enviar(self):
        """D-88 punto 2: vence al terminar el día de la fecha límite; ese día todavía sirve."""
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-6), fecha_limite_cotizaciones=en(0))
        cotizaciones.registrar_cotizacion(self.enlace_sur.pk, [(self.d_lechuga.pk, "20", "250.00", None, 3)], en(10), "")
        self.assertEqual(Cotizacion.objects.count(), 1)

    def test_ext_11a_el_pedido_dejo_de_estar_en_cotizacion(self):
        """Extensión 11a: cerrado o cancelado entre abrir y enviar."""
        for estado, causa, situacion in (("cancelado", "nadie_cotizo", "pedido_cancelado"), ("cerrado", None, "pedido_cerrado")):
            with self.subTest(estado=estado):
                Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido=estado, causa_cancelacion=causa, fecha_cierre_pedido=timezone.localdate())
                self.assertEqual(self.rechazo().datos["situacion"], situacion)
                self.assert_no_registro()

    def test_ext_11a_el_proveedor_paso_a_inactivo(self):
        """Extensión 11a: el proveedor pasó a «inactivo»."""
        self.sur.estado_proveedor = "inactivo"
        self.sur.save()
        self.assertEqual(self.rechazo().datos["situacion"], "proveedor_inactivo")
        self.assert_no_registro()

    def test_ext_2a_un_enlace_reemplazado_o_anulado_no_registra(self):
        """Extensión 2a: un enlace que ya no es el vigente no sirve."""
        for estado in ("reemplazado", "anulado"):
            with self.subTest(estado=estado):
                EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado=estado)
                self.assertEqual(self.rechazo().datos["situacion"], estado)
                EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado="vigente")

    def test_ext_2b_y_11b_si_ya_envio_su_cotizacion_no_registra_otra(self):
        """Extensiones 2b y 11b: con el enlace ``usado`` se informa que ya envió (``ya_cotizo``) y no se registra otra."""
        self.enviar()
        with self.assertRaises(ErrorDeCompras) as contexto:
            cotizaciones.registrar_cotizacion(self.enlace_sur.pk, [(self.d_nutriente.pk, "3", "90.00", None, 2)], self.validez, "")
        self.assertEqual(contexto.exception.codigo, "ya_cotizo")
        self.assertEqual(Cotizacion.objects.filter(proveedor=self.sur).count(), 1)

    def test_ext_11b_si_ya_existe_una_cotizacion_del_proveedor_aunque_el_enlace_siga_vigente(self):
        """Extensión 11b: la restricción única ``(pedido, proveedor)`` respalda a la verificación: una cotización ya existente da ``ya_cotizo`` y no un error de la base."""
        cotizacion_de(self.pedido, self.sur, [(self.d_lechuga, 20, "250.00", 3)])
        with self.assertRaises(ErrorDeCompras) as contexto:
            cotizaciones.registrar_cotizacion(self.enlace_sur.pk, [(self.d_nutriente.pk, "3", "90.00", None, 2)], self.validez, "")
        self.assertEqual(contexto.exception.codigo, "ya_cotizo")
        self.assertEqual(Cotizacion.objects.count(), 1)

    def test_ext_2a_un_enlace_inexistente_no_registra(self):
        """El id de un enlace que no existe no es un 500: ``Http404``."""
        from django.http import Http404

        with self.assertRaises(Http404):
            cotizaciones.registrar_cotizacion(999999, [(self.d_lechuga.pk, "20", "250.00", None, 3)], self.validez, "")


class PedidoCubiertoTests(CotizacionBase):
    """Extensión 11c: el aviso de «pedido cubierto» sale una sola vez, cuando se cubre por primera vez (regla 14 de 8.16)."""

    def setUp(self):
        super().setUp()
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 0
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])

    def completa(self, enlace, cantidad_l="20", cantidad_n="3"):
        """Un envío que cotiza los dos detalles con esas cantidades."""
        return self.enviar(enlace, lineas=[(self.d_lechuga.pk, cantidad_l, "250.00", None, 3), (self.d_nutriente.pk, cantidad_n, "100.00", None, 2)])

    def avisos(self):
        return Notificacion.objects.filter(titulo__contains=str(self.pedido))

    def test_ext_11c_al_cubrirse_por_primera_vez_se_avisa_y_el_pedido_sigue_en_cotizacion(self):
        """Extensión 11c: cubierto por primera vez → una notificación para el Agrónomo del destino; el pedido sigue «en cotización» hasta la fecha límite."""
        self.completa(self.enlace_sur)
        self.assertEqual([n.destinatario_id for n in self.avisos()], [self.agronomo.pk])
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pedido, "en_cotizacion")

    def test_lista_11c_el_aviso_indica_el_pedido_la_fecha_limite_y_las_lineas_por_detalle(self):
        """«Lista de tecnología» 11c: el aviso dice el pedido, la fecha límite y la cantidad de líneas de cotización recibidas por detalle."""
        self.completa(self.enlace_sur)
        aviso = self.avisos().get()
        self.assertIn(self.pedido.fecha_limite_cotizaciones.strftime("%d/%m/%Y"), aviso.detalle)
        self.assertIn("Lechuga", aviso.detalle)
        self.assertIn("1 línea", aviso.detalle)

    def test_ext_11c_un_pedido_ya_cubierto_no_vuelve_a_avisar(self):
        """Extensión 11c: «cubierto por primera vez»: la segunda cotización, con el pedido ya cubierto, no avisa."""
        self.completa(self.enlace_sur)
        self.completa(self.enlace_este)
        self.assertEqual(self.avisos().count(), 1)

    def test_ext_11c_una_cotizacion_que_no_alcanza_no_avisa_hasta_que_la_suma_cubre(self):
        """Regla «Pedido cubierto»: la cobertura suma las cotizaciones recibidas; avisa recién cuando la suma alcanza (12 + 12 ≥ 20)."""
        self.completa(self.enlace_sur, cantidad_l="12")
        self.assertEqual(self.avisos().count(), 0)
        self.completa(self.enlace_este, cantidad_l="12")
        self.assertEqual(self.avisos().count(), 1)

    def test_ext_11c_con_un_detalle_sin_cubrir_no_avisa(self):
        """Regla «Pedido cubierto»: tienen que estar cubiertos todos los detalles."""
        self.enviar(self.enlace_sur, lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3)])
        self.assertEqual(self.avisos().count(), 0)

    def test_ext_11c_la_tolerancia_de_la_configuracion_cuenta(self):
        """Regla «Pedido cubierto» (porcToleranciaCoberturaPedido): con 10 % alcanzan 18 lechugas y 2,7 kg."""
        fila = configuracion.obtener()
        fila.porc_tolerancia_cobertura_pedido = 10
        fila.save(update_fields=["porc_tolerancia_cobertura_pedido"])
        self.completa(self.enlace_sur, cantidad_l="18", cantidad_n="2.7")
        self.assertEqual(self.avisos().count(), 1)

    def test_h21_el_aviso_va_al_gerente_si_el_destino_no_tiene_agronomo_activo(self):
        """CMP-ENV-COT «Destinatario del aviso» y H21: si el Agrónomo del destino no está activo, al Gerente."""
        self.agronomo.is_active = False
        self.agronomo.save()
        self.completa(self.enlace_sur)
        self.assertEqual([n.destinatario_id for n in self.avisos()], [self.gerente.pk])

    def test_h21_un_pedido_para_dos_invernaderos_avisa_a_cada_agronomo_una_vez(self):
        """D-87 punto 3: el aviso va a cada Agrónomo activo de los invernaderos de destino, sin repetir."""
        otro, sur = crear_agronomo_con_invernadero("Invernadero Sur", email="otro@infoponia.com")
        en_sur = existencia(self.lechuga.insumo, sur, minimo=10)
        detalle = detalle_de_pedido(self.pedido, en_sur, cantidad="5")
        self.enviar(self.enlace_sur, lineas=[(self.d_lechuga.pk, "20", "250.00", None, 3), (self.d_nutriente.pk, "3", "100.00", None, 2), (detalle.pk, "5", "50.00", None, 2)])
        self.assertEqual(sorted(n.destinatario_id for n in self.avisos()), sorted([self.agronomo.pk, otro.pk]))

    def test_ext_11c_si_el_registro_se_revierte_no_queda_aviso(self):
        """Garantías mínimas: el aviso es parte de la transacción (D-42); sin registro no hay aviso."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                self.completa(self.enlace_sur)
        self.assertEqual(self.avisos().count(), 0)


class PortalDelProveedorTests(CotizacionBase):
    """Las vistas públicas (D-88 punto 4): ``/proveedor/<token>/`` valida y redirige a ``/proveedor/enlace/``, sin el token en la barra."""

    # D-88 punto 4 pedía ``Referrer-Policy: no-referrer``; con esa política Chromium manda ``Origin: null`` en los POST del mismo sitio y el CSRF de Django los rechaza (lo
    # encontró ``test_visual_pedidos``). Se usa ``same-origin``: a otro sitio no se manda ningún ``Referer`` y el token no queda en ninguna página (la entrada solo redirige).
    ENCABEZADOS = {"Referrer-Policy": "same-origin", "X-Robots-Tag": "noindex"}

    def setUp(self):
        super().setUp()
        self.config_correo = override_settings(CORREO_CONFIGURADO=True)
        self.config_correo.enable()
        self.addCleanup(self.config_correo.disable)

    def abrir(self, token=None):
        """Abre ``/proveedor/<token>/`` y sigue la redirección a ``/proveedor/enlace/``; devuelve la respuesta final."""
        return self.client.get(f"/proveedor/{token or self.token_sur}/", follow=True)

    def formulario(self, **cambios):
        """Los datos del formulario del portal: 20 lechugas a 250,00 en total (plazo 3 días), con validez y sin observaciones."""
        datos = {
            "accion": "enviar",
            "modo": "total",
            f"cantidad_{self.d_lechuga.pk}": "20",
            f"precio_{self.d_lechuga.pk}": "250.00",
            f"plazo_{self.d_lechuga.pk}": "3",
            "validez": self.validez.isoformat(),
            "observaciones": "",
        }
        datos.update(cambios)
        return datos

    def enviar_por_el_portal(self, **cambios):
        self.abrir()
        with self.captureOnCommitCallbacks(execute=True):  # el acuse sale en ``on_commit``; en un ``TestCase`` no corre solo
            return self.client.post("/proveedor/enlace/", self.formulario(**cambios), follow=True)

    def test_d88_abrir_redirige_a_una_url_sin_el_token_y_guarda_solo_el_id_en_la_sesion(self):
        """D-88 punto 4 y patrón, sección 3: guarda el id del enlace en la sesión y redirige a ``/proveedor/enlace/``; el token no queda en la barra ni en el historial."""
        respuesta = self.client.get(f"/proveedor/{self.token_sur}/")
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta["Location"], "/proveedor/enlace/")
        self.assertNotIn(self.token_sur, respuesta["Location"])
        self.assertEqual(self.client.session["enlace_proveedor"], self.enlace_sur.pk)
        self.assertNotIn(self.token_sur, str(dict(self.client.session)))

    def test_d88_las_paginas_del_portal_llevan_los_encabezados_de_seguridad(self):
        """D-88 punto 4: ``Cache-Control: no-store``, ``Referrer-Policy: no-referrer`` y ``X-Robots-Tag: noindex`` en cada respuesta, también en la de un enlace que no sirve y en la de un token inválido."""
        respuestas = [
            self.client.get(f"/proveedor/{self.token_sur}/"),
            self.client.get("/proveedor/enlace/"),
            self.client.get("/proveedor/token-que-no-existe/"),
        ]
        EnlaceProveedor.objects.filter(pk=self.enlace_este.pk).update(estado="anulado")
        respuestas.append(self.client.get(f"/proveedor/{self.token_este}/", follow=True))
        for respuesta in respuestas:
            with self.subTest(url=respuesta.request["PATH_INFO"]):
                self.assertIn("no-store", respuesta["Cache-Control"])
                for encabezado, valor in self.ENCABEZADOS.items():
                    self.assertEqual(respuesta[encabezado], valor)

    def test_ext_2a_un_token_inexistente_da_enlace_no_valido_sin_datos(self):
        """Patrón, sección 3: un token que no existe → «Este enlace no es válido», sin más."""
        respuesta = self.client.get("/proveedor/no-existe/", follow=True)
        self.assertEqual(respuesta.status_code, 404)
        self.assertContains(respuesta, "Este enlace no es válido", status_code=404)
        self.assertNotContains(respuesta, "Lechuga", status_code=404)

    def test_ext_2a_cada_motivo_por_el_que_el_enlace_no_sirve_se_informa_sin_datos_del_pedido(self):
        """Extensión 2a: «el enlace no puede usarse y el motivo»; nunca muestra datos del pedido."""
        casos = [
            ("vencido", dict(estado="vencido"), "El plazo para cotizar terminó."),
            ("reemplazado", dict(estado="reemplazado"), "Este enlace fue reemplazado por uno más nuevo."),
            ("anulado", dict(estado="anulado"), "Este enlace fue anulado."),
        ]
        for nombre, cambios, texto in casos:
            with self.subTest(nombre):
                EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(**cambios)
                respuesta = self.abrir()
                self.assertContains(respuesta, "Este enlace no se puede usar")
                self.assertContains(respuesta, texto)
                self.assertNotContains(respuesta, "Lechuga")
                self.assertNotContains(respuesta, "Invernadero Norte")
        EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado="vigente")
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-6), fecha_limite_cotizaciones=en(-1))
        self.assertContains(self.abrir(), "El plazo para cotizar terminó.")
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=timezone.localdate(), fecha_limite_cotizaciones=en(3))
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cancelado", causa_cancelacion="nadie_cotizo", fecha_cierre_pedido=timezone.localdate())
        self.assertContains(self.abrir(), "El pedido fue cancelado.")
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="cerrado", causa_cancelacion=None)
        self.assertContains(self.abrir(), "El pedido ya no está recibiendo cotizaciones.")
        Pedido.objects.filter(pk=self.pedido.pk).update(estado_pedido="en_cotizacion", fecha_cierre_pedido=None)
        self.sur.estado_proveedor = "inactivo"
        self.sur.save()
        self.assertContains(self.abrir(), "El proveedor no está activo.")

    def test_ext_2_el_portal_muestra_el_pedido_con_su_destino_y_la_validez_propuesta(self):
        """Paso 2: la fecha límite; por cada detalle el insumo (nombre, descripción y unidad), la cantidad pedida y el invernadero de destino con su dirección; la fecha de validez propuesta."""
        respuesta = self.abrir()
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("Lechuga", "Plantín", "20", "Nutriente", "Invernadero Norte", "Calle 122 3310",
                      self.pedido.fecha_limite_cotizaciones.strftime("%d/%m/%Y"), cotizaciones.proponer_validez(self.pedido).isoformat()):
            self.assertContains(respuesta, texto)

    def test_regla_el_proveedor_no_ve_el_precio_de_referencia_ni_a_los_otros_invitados_ni_otras_cotizaciones(self):
        """Regla «Información visible» y garantía mínima: ni el precio de referencia ni el monto estimado, ni a quién más se invitó, ni las cotizaciones de otros."""
        cotizacion_de(self.pedido, self.este, [(self.d_lechuga, 20, "777.77", 3)])
        respuesta = self.abrir()
        for prohibido in ("12,50", "12.50", "100,00", "550,00", "Viveros del Este", "777,77"):
            self.assertNotContains(respuesta, prohibido)

    def test_d88_el_portal_no_depende_de_la_sesion_de_un_usuario_ni_muestra_menu(self):
        """Patrón, sección 4 (punto 3): las páginas del portal no leen ``request.user``; una sesión de usuario abierta en el mismo navegador no cambia nada ni muestra menú."""
        self.client.force_login(self.gerente)
        respuesta = self.abrir()
        self.assertNotContains(respuesta, self.gerente.email)
        self.assertNotContains(respuesta, "Cerrar sesión")
        self.assertContains(respuesta, "Semillas del Sur S. A.")

    def test_d88_la_sesion_de_un_enlace_no_abre_otro_pedido(self):
        """Patrón, sección 4 (punto 4): cambiar el id de la sesión a mano da la pantalla de enlace no válido (cada vista relee el enlace por el id)."""
        self.abrir()
        sesion = self.client.session
        sesion["enlace_proveedor"] = 999999
        sesion.save()
        respuesta = self.client.get("/proveedor/enlace/")
        self.assertContains(respuesta, "Este enlace no es válido", status_code=404)
        self.assertNotContains(respuesta, "Lechuga", status_code=404)

    def test_d88_sin_sesion_de_enlace_no_hay_portal(self):
        """``/proveedor/enlace/`` sin haber abierto un enlace da la pantalla de enlace no válido."""
        self.assertContains(self.client.get("/proveedor/enlace/"), "Este enlace no es válido", status_code=404)

    def test_d88_si_el_enlace_deja_de_servir_con_la_sesion_abierta_se_vuelve_a_verificar(self):
        """Patrón, sección 3 (punto 2): cada vista vuelve a leer el enlace y verifica que siga sirviendo."""
        self.abrir()
        EnlaceProveedor.objects.filter(pk=self.enlace_sur.pk).update(estado="anulado")
        self.assertContains(self.client.get("/proveedor/enlace/"), "Este enlace no se puede usar")

    def test_paso_9_revisar_muestra_el_resumen_con_la_advertencia_y_no_registra_nada(self):
        """Paso 9: el resumen (líneas, monto, validez, observaciones) y la advertencia de que se envía una sola vez; revisar no registra nada."""
        self.abrir()
        respuesta = self.client.post("/proveedor/enlace/", self.formulario(accion="revisar", observaciones="Cajones"))
        self.assertEqual(respuesta.status_code, 200)
        for texto in ("250,00", "Cajones", self.validez.strftime("%d/%m/%Y"), "una sola vez"):
            self.assertContains(respuesta, texto)
        self.assertEqual((Cotizacion.objects.count(), mail.outbox), (0, []))

    def test_paso_9_revisar_con_errores_los_muestra_junto_a_cada_campo_y_conserva_lo_escrito(self):
        """Extensiones 6a a 6c y 9a: los errores se muestran en la misma pantalla, sin perder lo escrito."""
        self.abrir()
        respuesta = self.client.post(
            "/proveedor/enlace/", self.formulario(accion="revisar", **{f"cantidad_{self.d_lechuga.pk}": "0", f"plazo_{self.d_lechuga.pk}": "0", "observaciones": "Cajones"})
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cajones")
        self.assertContains(respuesta, 'class="err"')
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_flujo_principal_el_proveedor_cotiza_una_vez_recibe_el_acuse_y_ve_su_cotizacion_en_solo_lectura(self):
        """Flujo principal y 2b: envía, se registra, llega el acuse; al volver a abrir el enlace ve su cotización en solo lectura y no puede enviar otra."""
        respuesta = self.enviar_por_el_portal(observaciones="Cajones")
        self.assertContains(respuesta, "Recibimos su cotización")
        self.assertEqual(Cotizacion.objects.get().monto_cotizacion, Decimal("250.00"))
        self.assertEqual([m.to for m in mail.outbox], [["ventas@sur.com"]])
        otra_vez = self.abrir()
        for texto in ("Ya envió su cotización", "250,00", "Cajones", self.validez.strftime("%d/%m/%Y")):
            self.assertContains(otra_vez, texto)
        self.assertNotContains(otra_vez, "Enviar cotización")
        repetido = self.client.post("/proveedor/enlace/", self.formulario(), follow=True)
        self.assertContains(repetido, "Ya envió su cotización")
        self.assertEqual(Cotizacion.objects.count(), 1)

    def test_d89_el_proveedor_puede_cargar_el_precio_unitario(self):
        """D-89 punto 2: con ``modo = unitario`` el campo de precio es el unitario y el total se calcula (20 × 12,50 = 250,00)."""
        self.enviar_por_el_portal(modo="unitario", **{f"precio_{self.d_lechuga.pk}": "12.50"})
        self.assertEqual(Cotizacion.objects.get().lineas.get().total_linea, Decimal("250.00"))

    def test_regla_una_linea_sin_cantidad_precio_ni_plazo_no_se_cotiza_y_sin_ninguna_se_rechaza(self):
        """Pasos 3 a 6 y 8a: los detalles que no elige quedan sin cotizar; terminar sin cotizar ninguno se rechaza."""
        self.abrir()
        sin_nada = self.formulario()
        for clave in (f"cantidad_{self.d_lechuga.pk}", f"precio_{self.d_lechuga.pk}", f"plazo_{self.d_lechuga.pk}"):
            sin_nada[clave] = ""
        respuesta = self.client.post("/proveedor/enlace/", sin_nada)
        self.assertContains(respuesta, "al menos un detalle")
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_ext_11a_enviar_despues_de_la_fecha_limite_no_registra_y_lo_informa(self):
        """Extensión 11a: el proveedor armó la cotización durante varias horas y venció la fecha límite: no se registra nada y se informa que el enlace ya no puede usarse."""
        self.abrir()
        Pedido.objects.filter(pk=self.pedido.pk).update(fecha_pedido=en(-6), fecha_limite_cotizaciones=en(-1))
        respuesta = self.client.post("/proveedor/enlace/", self.formulario(), follow=True)
        self.assertContains(respuesta, "Este enlace no se puede usar")
        self.assertContains(respuesta, "El plazo para cotizar terminó.")
        self.assertEqual(Cotizacion.objects.count(), 0)

    def test_ext_11b_enviar_desde_dos_pestanas_registra_una_sola_y_informa_la_segunda(self):
        """Extensión 11b: la segunda pestaña recibe «ya había enviado una cotización» y ve la suya en solo lectura."""
        self.abrir()
        self.client.post("/proveedor/enlace/", self.formulario())
        respuesta = self.client.post("/proveedor/enlace/", self.formulario(**{f"precio_{self.d_lechuga.pk}": "1.00"}), follow=True)
        self.assertContains(respuesta, "Ya envió su cotización")
        self.assertEqual(Cotizacion.objects.get().monto_cotizacion, Decimal("250.00"))

    def test_regla_los_metodos_que_no_son_get_o_post_dan_405(self):
        """Las pantallas del portal solo aceptan GET y POST."""
        self.abrir()
        self.assertEqual(self.client.put("/proveedor/enlace/").status_code, 405)
        self.assertEqual(self.client.delete("/proveedor/enlace/").status_code, 405)
