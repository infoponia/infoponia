# Pruebas de CMP-CNL-PED · Cancelar Pedido (CMP-02b, paso 1): ``cancelar_pedido``, ``resumir_cancelacion`` y ``cancelar_pedido_automaticamente`` de
# ``compras/servicios/pedidos.py``. Fuente: docs/casos_de_uso/compras/pedidos.md (CMP-CNL-PED v0.1: precondiciones a a c, garantías mínimas,
# postcondiciones a a e, flujo básico, extensiones *a, *b, 3a, 6a y 7a, y las reglas «Quién cancela», «Cuándo», «Motivo», «Cotizaciones y enlaces»,
# «Aviso a los proveedores», «Cancelaciones automáticas» y «Pedido y alertas»), D-87 punto 3 (destinatarios, H21) y D-88 (los enlaces).
# Los correos salen en ``on_commit`` (se ejecutan con ``captureOnCommitCallbacks``); las notificaciones, dentro de la transacción (D-42).
# Convenciones de los errores: ``ValidationError`` del campo ``motivo`` (``motivo_obligatorio``, ``motivo_largo``); ``ErrorDeCompras``
# ``pedido_no_en_cotizacion`` (6a, con el estado actual en ``datos``). ``cancelar_pedido_automaticamente`` devuelve el pedido cancelado, o ``None``
# si ya no estaba en cotización. El módulo se toma dentro de cada prueba (``perezoso``).

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.errores import ErrorDeCompras
from compras.models import Cotizacion, EnlaceProveedor, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_administrador, crear_capataz, crear_gerente
from inventario.models import MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, perezoso
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo_con_invernadero, crear_vendedor

pedidos = perezoso("compras.servicios.pedidos")

MOTIVO = "Ya no hace falta, compramos en la feria."


@override_settings(CORREO_CONFIGURADO=True)
class CancelacionBase(ConDatosDeInventario, TestCase):
    """Ana (invernadero Norte) y Beto (Sur), un Gerente y un pedido de Ana a Norte con dos invitados: Semillas del Sur cotizó (cotización
    «propuesta» y enlace «usado») y Viveros del Este no (enlace «vigente»)."""

    def setUp(self):
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.beto, self.sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        self.gerente = crear_gerente()
        self.lechuga_norte = existencia(insumo("Lechuga", unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.lechuga_sur = existencia(self.lechuga_norte.insumo, self.sur, minimo=10, precio="11.00")
        self.sur_prv = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.este_prv = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")
        self.pedido = armar_pedido(self.ana, dias_al_limite=3)
        self.detalle = detalle_de_pedido(self.pedido, self.lechuga_norte, cantidad="20")
        self.invitacion_sur = invitar(self.pedido, self.sur_prv)
        self.invitacion_este = invitar(self.pedido, self.este_prv)
        self.enlace_sur, _ = enlace_de(self.invitacion_sur, estado="usado")
        self.enlace_este, _ = enlace_de(self.invitacion_este)
        self.cotizacion = cotizacion_de(self.pedido, self.sur_prv, [(self.detalle, 20, "250.00", 3)])

    def cancelar(self, actor=None, motivo=MOTIVO, pedido=None):
        """``cancelar_pedido`` con los correos ejecutados; devuelve el pedido."""
        with self.captureOnCommitCallbacks(execute=True):
            return pedidos.cancelar_pedido(actor or self.ana, (pedido or self.pedido).pk, motivo)

    def automatica(self, causa, actor=None, pedido=None):
        """``cancelar_pedido_automaticamente`` con los correos ejecutados."""
        with self.captureOnCommitCallbacks(execute=True):
            return pedidos.cancelar_pedido_automaticamente(pedido or self.pedido, causa, actor=actor)

    def sin_cambios(self):
        """Afirma que el pedido, sus cotizaciones y sus enlaces siguen como estaban, sin correos ni auditoría ni avisos."""
        self.pedido.refresh_from_db()
        self.assertEqual((self.pedido.estado_pedido, self.pedido.fecha_cierre_pedido, self.pedido.causa_cancelacion), ("en_cotizacion", None, None))
        self.cotizacion.refresh_from_db()
        self.assertEqual(self.cotizacion.estado_cotizacion, "propuesta")
        self.enlace_sur.refresh_from_db()
        self.enlace_este.refresh_from_db()
        self.assertEqual((self.enlace_sur.estado, self.enlace_este.estado), ("usado", "vigente"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 0)
        self.assertEqual((mail.outbox, Notificacion.objects.count()), ([], 0))


class PrecondicionesYReglasDeQuienYCuandoTests(CancelacionBase):
    """Precondiciones a a c y las reglas «Quién cancela» y «Cuándo»."""

    def test_regla_quien_cancela_solo_un_agronomo_activo(self):
        """Precondición a y SEG-13: Gerente, Capataz, Vendedor, Administrador, una cuenta inactiva y ``None`` reciben ``PermissionDenied``."""
        for actor in (self.gerente, crear_capataz(), crear_vendedor(), crear_administrador(), None):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    pedidos.cancelar_pedido(actor, self.pedido.pk, MOTIVO)
        self.sin_cambios()

    def test_regla_quien_cancela_una_cuenta_inactiva_no_cancela(self):
        """Precondición a: el actor tiene que tener la cuenta activa (SEG-13)."""
        self.ana.is_active = False
        self.ana.save()
        with self.assertRaises(PermissionDenied):
            pedidos.cancelar_pedido(self.ana, self.pedido.pk, MOTIVO)
        self.sin_cambios()

    def test_regla_quien_cancela_ni_otro_agronomo_ni_el_gerente_cancelan_a_mano(self):
        """Precondición b y regla «Quién cancela»: solo el Agrónomo que hizo el pedido; otro Agrónomo recibe ``PermissionDenied`` y el Gerente, también."""
        for actor in (self.beto, self.gerente):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    pedidos.cancelar_pedido(actor, self.pedido.pk, MOTIVO)
        self.sin_cambios()

    def test_regla_quien_cancela_un_pedido_que_no_existe_es_404(self):
        """D-28: un pedido inexistente es ``Http404``."""
        with self.assertRaises(Http404):
            pedidos.cancelar_pedido(self.ana, 987654, MOTIVO)

    def test_regla_cuando_solo_un_pedido_en_cotizacion_y_dice_su_estado_actual(self):
        """Precondición c y extensión 6a: un pedido cerrado o cancelado no se cancela; el error trae el estado actual y no cambia nada."""
        for estado, causa in (("cerrado", None), ("cancelado", "manual")):
            with self.subTest(estado=estado):
                otro = armar_pedido(self.ana, estado=estado, causa=causa, motivo="x" if causa else "")
                with self.assertRaises(ErrorDeCompras) as contexto:
                    pedidos.cancelar_pedido(self.ana, otro.pk, MOTIVO)
                self.assertEqual(contexto.exception.codigo, "pedido_no_en_cotizacion")
                self.assertEqual(contexto.exception.datos["estado"], estado)
        self.assertEqual((RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), mail.outbox), (0, []))

    def test_regla_cuando_se_cancela_antes_de_vencer_la_fecha_limite(self):
        """Regla «Cuándo»: con la fecha límite por venir, se cancela."""
        self.assertEqual(self.cancelar().estado_pedido, "cancelado")

    def test_regla_cuando_se_cancela_tambien_despues_de_vencida_la_fecha_limite(self):
        """Regla «Cuándo» (decisión de Ezequiel; resuelve el tema abierto 1): mientras siga «en cotización» se cancela aunque la fecha límite haya pasado."""
        Pedido.objects.filter(pk=self.pedido.pk).update(
            fecha_pedido=timezone.localdate() - timedelta(days=10), fecha_limite_cotizaciones=timezone.localdate() - timedelta(days=2)
        )
        self.assertEqual(self.cancelar().estado_pedido, "cancelado")


class MotivoTests(CancelacionBase):
    """Extensión 3a y regla «Motivo»."""

    def test_ext_3a_el_motivo_es_obligatorio(self):
        """Extensión 3a: sin motivo (vacío o solo espacios) se rechaza en el campo ``motivo`` y no se cancela nada."""
        for motivo in ("", "   ", None):
            with self.subTest(motivo=motivo):
                with self.assertRaises(ValidationError) as contexto:
                    pedidos.cancelar_pedido(self.ana, self.pedido.pk, motivo)
                self.assertEqual([e.code for e in contexto.exception.error_dict["motivo"]], ["motivo_obligatorio"])
        self.sin_cambios()

    def test_regla_motivo_tiene_hasta_500_caracteres(self):
        """Postcondición a: el motivo es un texto de hasta 500 caracteres; 501 se rechaza, 500 se acepta."""
        with self.assertRaises(ValidationError) as contexto:
            pedidos.cancelar_pedido(self.ana, self.pedido.pk, "a" * 501)
        self.assertEqual([e.code for e in contexto.exception.error_dict["motivo"]], ["motivo_largo"])
        self.sin_cambios()
        self.assertEqual(len(self.cancelar(motivo="a" * 500).motivo_cancelacion), 500)

    def test_regla_motivo_se_guarda_recortado(self):
        """Regla «Motivo»: el texto se guarda sin los espacios de los extremos."""
        self.assertEqual(self.cancelar(motivo="  Ya no hace falta.  ").motivo_cancelacion, "Ya no hace falta.")

    def test_ext_3a_y_6a_juntas_no_cambian_nada(self):
        """Extensiones 3a y 6a juntas: un pedido que ya no está en cotización y un motivo vacío tampoco cambian nada."""
        cerrado = armar_pedido(self.ana, estado="cerrado")
        with self.assertRaises((ValidationError, ErrorDeCompras)):
            pedidos.cancelar_pedido(self.ana, cerrado.pk, "")
        cerrado.refresh_from_db()
        self.assertEqual(cerrado.estado_pedido, "cerrado")


class PostcondicionesTests(CancelacionBase):
    """Postcondiciones a a e y las reglas «Cotizaciones y enlaces» y «Aviso a los proveedores»."""

    def test_post_a_el_pedido_pasa_a_cancelado_con_su_fecha_de_cierre_su_motivo_y_su_causa(self):
        """Postcondición a: «cancelado», ``fecha_cierre_pedido`` = hoy, el motivo y la causa ``manual`` (modelo, «Pedido»)."""
        self.cancelar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pedido, "cancelado")
        self.assertEqual(self.pedido.fecha_cierre_pedido, timezone.localdate())
        self.assertEqual((self.pedido.motivo_cancelacion, self.pedido.causa_cancelacion), (MOTIVO, "manual"))

    def test_post_b_las_cotizaciones_propuesta_pasan_a_descartada(self):
        """Postcondición b y regla «Cotizaciones y enlaces»: cada cotización «propuesta» pasa a «descartada»; se conserva (no se borra)."""
        self.cancelar()
        self.cotizacion.refresh_from_db()
        self.assertEqual(self.cotizacion.estado_cotizacion, "descartada")
        self.assertEqual(Cotizacion.objects.filter(pedido=self.pedido).count(), 1)

    def test_post_c_los_enlaces_vigentes_pasan_a_anulado_y_los_usados_se_conservan(self):
        """Postcondición c: cada enlace «vigente» pasa a «anulado» (deja de servir); uno «usado» (el de quien ya cotizó) queda como estaba."""
        self.cancelar()
        self.enlace_sur.refresh_from_db()
        self.enlace_este.refresh_from_db()
        self.assertEqual((self.enlace_este.estado, self.enlace_sur.estado), ("anulado", "usado"))

    def test_post_c_el_enlace_anulado_ya_no_sirve_al_proveedor(self):
        """Postcondición c y D-88 punto 2: con el pedido cancelado, ningún enlace sirve (la situación dice «pedido cancelado»)."""
        from compras.servicios import enlaces

        self.cancelar()
        for enlace in (self.enlace_sur, self.enlace_este):
            enlace = enlaces.enlace_por_id(enlace.pk)
            self.assertEqual(enlaces.situacion_del_enlace(enlace), enlaces.PEDIDO_CANCELADO)

    def test_post_d_se_avisa_por_correo_a_todos_los_invitados_hayan_cotizado_o_no(self):
        """Postcondición d y regla «Aviso a los proveedores»: un correo a cada invitado."""
        self.cancelar()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        for correo in mail.outbox:
            self.assertIn(str(self.pedido), correo.subject)
            self.assertIn("cancel", correo.body.lower())

    def test_post_d_el_correo_no_lleva_el_motivo_ni_a_los_otros_proveedores_ni_precios(self):
        """Lista de tecnología 7: el correo indica el pedido, la fecha y que se canceló; no incluye el motivo ni a los otros proveedores. Tampoco precios."""
        self.cancelar()
        por_destino = {m.to[0]: m.body for m in mail.outbox}
        self.assertIn(str(self.pedido), por_destino["info@este.com"])
        for cuerpo in por_destino.values():
            self.assertNotIn(MOTIVO, cuerpo)
            for prohibido in ("12,50", "250", "Precio", "precio"):
                self.assertNotIn(prohibido, cuerpo)
        self.assertNotIn("Semillas del Sur", por_destino["info@este.com"])
        self.assertNotIn("Viveros del Este", por_destino["ventas@sur.com"])

    def test_ext_7a_si_no_sale_el_correo_la_cancelacion_permanece(self):
        """Extensión 7a: un correo que falla no revierte la cancelación (D-88 punto 6: no hay reintento automático)."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            self.cancelar()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado_pedido, "cancelado")
        self.assertEqual(mail.outbox, [])

    def test_ext_7a_con_el_correo_sin_configurar_la_cancelacion_permanece_y_no_sale_nada(self):
        """Extensión 7a y API de correo, regla 5: sin el correo configurado se cancela igual y no sale nada."""
        with override_settings(CORREO_CONFIGURADO=False):
            self.cancelar()
        self.pedido.refresh_from_db()
        self.assertEqual((self.pedido.estado_pedido, mail.outbox), ("cancelado", []))

    def test_ext_7a_un_correo_que_falla_no_impide_que_salga_el_del_otro_proveedor(self):
        """Extensión 7a: cada proveedor es independiente."""
        original = mail.send_mail

        def a_medias(asunto, cuerpo, remitente, destinatarios, **kwargs):
            if destinatarios == ["info@este.com"]:
                raise OSError("falla")
            return original(asunto, cuerpo, remitente, destinatarios, **kwargs)

        with mock.patch("core.correo.send_mail", a_medias):
            self.cancelar()
        self.assertEqual([m.to for m in mail.outbox], [["ventas@sur.com"]])

    def test_post_e_un_solo_registro_de_auditoria_con_el_cambio_de_estado_el_motivo_y_los_cambios_de_cotizaciones_y_enlaces(self):
        """Postcondición e y D-36: una acción ``cancelacion_pedido`` del Agrónomo con el pedido, la cotización y los enlaces como afectados."""
        self.cancelar()
        registro = RegistroAuditoria.objects.get(accion="cancelacion_pedido")
        self.assertEqual((registro.usuario_id, registro.rol), (self.ana.pk, "agronomo"))
        modelos = [a["modelo"] for a in registro.afectados]
        self.assertEqual((modelos.count("compras.pedido"), modelos.count("compras.cotizacion")), (1, 1))
        self.assertGreaterEqual(modelos.count("compras.enlaceproveedor"), 1)
        cambios = registro.detalle["cambios"]
        self.assertEqual(cambios["estado"], {"antes": "en_cotizacion", "despues": "cancelado"})
        self.assertEqual(cambios["motivo_cancelacion"], {"antes": None, "despues": MOTIVO})
        self.assertEqual(cambios["causa_cancelacion"], {"antes": None, "despues": "manual"})
        self.assertEqual(cambios["fecha_cierre_pedido"], {"antes": None, "despues": timezone.localdate().isoformat()})
        datos = registro.detalle["datos"]
        self.assertEqual(len(datos["cotizaciones_descartadas"]), 1)
        self.assertEqual(len(datos["enlaces_anulados"]), 1)

    def test_post_e_el_registro_no_guarda_ningun_token(self):
        """Patrón del enlace del proveedor, sección 1: la auditoría nunca lleva el token ni su resumen."""
        self.cancelar()
        registro = RegistroAuditoria.objects.get(accion="cancelacion_pedido")
        self.assertNotIn(self.enlace_este.token_resumen, str(registro.detalle) + str(registro.afectados))

    def test_regla_pedido_y_alertas_cancelar_no_toca_stock_transito_minimo_reservas_ni_alertas(self):
        """Garantías «Además» y regla «Pedido y alertas»: ni lotes, ni movimientos, ni tránsito, ni mínimo, ni alertas cambian."""
        lote(self.lechuga_norte, 12)
        movimientos, alertas = MovimientoInsumo.objects.count(), list(Alerta.objects.values_list("pk", "estado_alerta"))
        antes = (self.lechuga_norte.cant_min_insumo, self.lechuga_norte.cant_transito_insumo, self.lechuga_norte.referencia_precio)
        self.cancelar()
        self.lechuga_norte.refresh_from_db()
        self.assertEqual((self.lechuga_norte.cant_min_insumo, self.lechuga_norte.cant_transito_insumo, self.lechuga_norte.referencia_precio), antes)
        self.assertEqual(MovimientoInsumo.objects.count(), movimientos)
        self.assertEqual(list(Alerta.objects.values_list("pk", "estado_alerta")), alertas)

    def test_regla_aviso_la_cancelacion_manual_no_notifica_a_nadie_en_la_campana(self):
        """H21: nunca se notifica a quien hizo la acción, y la cancelación manual la hace el único Agrónomo del pedido: no hay a quién avisar (los proveedores, por correo)."""
        self.cancelar()
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_garantia_si_falla_la_auditoria_no_queda_nada_ni_sale_ningun_correo(self):
        """Garantías mínimas y extensión *b: la cancelación es atómica; si falla, el pedido, las cotizaciones y los enlaces quedan como estaban y los correos (``on_commit``) no salen."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    pedidos.cancelar_pedido(self.ana, self.pedido.pk, MOTIVO)
        self.assertEqual(pendientes, [])
        self.sin_cambios()


class ResumenDeLaCancelacionTests(CancelacionBase):
    """Pasos 2 y 4: qué se cancela. Solo lectura."""

    def test_paso_4_el_resumen_dice_cuantas_cotizaciones_se_descartan_cuantos_enlaces_se_anulan_y_a_quien_se_avisa(self):
        """Paso 4: cotizaciones que se descartan, enlaces que se anulan y a quién se avisará por correo (todos los invitados)."""
        resumen = pedidos.resumir_cancelacion(self.ana, self.pedido.pk, MOTIVO)
        self.assertEqual((resumen.pedido.pk, resumen.motivo), (self.pedido.pk, MOTIVO))
        self.assertEqual((resumen.descartadas, resumen.enlaces), (1, 1))
        self.assertEqual({p.pk for p in resumen.invitados}, {self.sur_prv.pk, self.este_prv.pk})

    def test_paso_2_el_resumen_trae_las_cotizaciones_recibidas_con_su_monto(self):
        """Paso 2: «cuáles ya cotizaron (con su monto)»."""
        resumen = pedidos.resumir_cancelacion(self.ana, self.pedido.pk, MOTIVO)
        self.assertEqual([(p.pk, monto) for p, monto in resumen.cotizaciones], [(self.sur_prv.pk, Decimal("250.00"))])

    def test_el_resumen_no_escribe_nada(self):
        """El resumen no cancela, no audita, no envía correos ni avisa."""
        pedidos.resumir_cancelacion(self.ana, self.pedido.pk, MOTIVO)
        self.sin_cambios()

    def test_el_resumen_valida_lo_mismo_que_cancelar(self):
        """El resumen aplica las mismas precondiciones y el mismo motivo que ``cancelar_pedido``."""
        with self.assertRaises(PermissionDenied):
            pedidos.resumir_cancelacion(self.beto, self.pedido.pk, MOTIVO)
        with self.assertRaises(PermissionDenied):
            pedidos.resumir_cancelacion(self.gerente, self.pedido.pk, MOTIVO)
        with self.assertRaises(Http404):
            pedidos.resumir_cancelacion(self.ana, 987654, MOTIVO)
        with self.assertRaises(ValidationError):
            pedidos.resumir_cancelacion(self.ana, self.pedido.pk, " ")
        cerrado = armar_pedido(self.ana, estado="cerrado")
        with self.assertRaises(ErrorDeCompras):
            pedidos.resumir_cancelacion(self.ana, cerrado.pk, MOTIVO)


class CancelacionesAutomaticasTests(CancelacionBase):
    """Regla «Cancelaciones automáticas» (H16, MD-62, H17, H21): la misma función interna, sin el flujo y sin actor humano."""

    CAUSAS = (
        ("nadie_cotizo", "nadie cotizó"),
        ("sin_cotizaciones_elegibles", "sin cotizaciones elegibles"),
        ("agronomo_inactivo", "Agrónomo inactivo"),
        ("agronomo_sin_invernadero", "Agrónomo sin el invernadero de destino"),
    )

    def test_regla_automaticas_cada_causa_completa_su_texto_fijo(self):
        """Regla «Motivo» y «Cancelaciones automáticas»: el motivo es el literal de la regla 3 de CMP-CNL-PED («Lista de tecnología»), con la causa y la fecha de cierre de hoy."""
        for causa, texto in self.CAUSAS:
            with self.subTest(causa=causa):
                otro = armar_pedido(self.ana)
                detalle_de_pedido(otro, self.lechuga_norte, cantidad="5")
                self.assertEqual(self.automatica(causa, pedido=otro).pk, otro.pk)
                otro.refresh_from_db()
                self.assertEqual(
                    (otro.estado_pedido, otro.causa_cancelacion, otro.motivo_cancelacion, otro.fecha_cierre_pedido),
                    ("cancelado", causa, texto, timezone.localdate()),
                )

    def test_regla_automaticas_descartan_cotizaciones_anulan_enlaces_y_avisan_a_los_proveedores_como_la_manual(self):
        """Regla «Cotizaciones y enlaces» y «Aviso a los proveedores»: lo mismo que la manual, a todos los invitados y sin el motivo."""
        self.automatica("nadie_cotizo")
        self.cotizacion.refresh_from_db()
        self.enlace_este.refresh_from_db()
        self.assertEqual((self.cotizacion.estado_cotizacion, self.enlace_este.estado), ("descartada", "anulado"))
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        for correo in mail.outbox:
            self.assertNotIn("nadie cotizó", correo.body.lower())

    def test_regla_automaticas_la_causa_manual_no_es_una_cancelacion_automatica(self):
        """Solo las cuatro causas automáticas; ``manual`` (o una desconocida) es un error de uso (``ValueError``)."""
        for causa in ("manual", "otra"):
            with self.subTest(causa=causa):
                with self.assertRaises(ValueError):
                    pedidos.cancelar_pedido_automaticamente(self.pedido, causa)
        self.sin_cambios()

    def test_regla_automaticas_se_audita_como_infoponia_sin_cuenta(self):
        """Cómo se aplica (CMP-CNL-PED): ``cancelacion_pedido`` con ``usuario=None`` y el rol ``infoponia``, aunque haya un actor que dio la baja."""
        for actor in (None, self.gerente):
            with self.subTest(actor=actor):
                otro = armar_pedido(self.ana)
                detalle_de_pedido(otro, self.lechuga_norte, cantidad="5")
                self.automatica("agronomo_inactivo", actor=actor, pedido=otro)
                registro = next(r for r in RegistroAuditoria.objects.filter(accion="cancelacion_pedido") if {"modelo": "compras.pedido", "id": otro.pk, "texto": str(otro)} in r.afectados)
                self.assertEqual((registro.usuario_id, registro.rol), (None, "infoponia"))
                self.assertEqual(registro.detalle["cambios"]["causa_cancelacion"]["despues"], "agronomo_inactivo")

    def test_regla_automaticas_un_pedido_que_ya_no_esta_en_cotizacion_devuelve_none_y_no_cambia_nada(self):
        """La función sirve a los pasos diarios (CMP-03): si el pedido ya se cerró o se canceló, no hace nada y no falla."""
        cerrado = armar_pedido(self.ana, estado="cerrado")
        self.assertIsNone(self.automatica("nadie_cotizo", pedido=cerrado))
        cerrado.refresh_from_db()
        self.assertEqual(cerrado.estado_pedido, "cerrado")
        self.assertEqual((RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), mail.outbox), (0, []))

    def test_regla_automaticas_la_decision_se_toma_con_el_pedido_releido(self):
        """La instancia que llega puede estar vieja: si otra operación ya lo canceló, no se cancela dos veces."""
        copia = Pedido.objects.get(pk=self.pedido.pk)
        self.automatica("nadie_cotizo")
        self.assertIsNone(self.automatica("nadie_cotizo", pedido=copia))
        self.assertEqual(RegistroAuditoria.objects.filter(accion="cancelacion_pedido").count(), 1)

    def test_h21_se_avisa_al_agronomo_activo_de_cada_invernadero_de_destino(self):
        """H21 (D-87 punto 3): un pedido a Norte y a Sur avisa a Ana y a Beto, una sola vez cada uno, con el título y el motivo; no al Gerente."""
        detalle_de_pedido(self.pedido, self.lechuga_sur, cantidad="10")
        self.automatica("nadie_cotizo")
        self.assertEqual(sorted(Notificacion.objects.values_list("destinatario_id", flat=True)), sorted([self.ana.pk, self.beto.pk]))
        aviso = Notificacion.objects.get(destinatario=self.ana)
        self.assertIn(str(self.pedido), aviso.titulo)
        self.assertIn(str(self.pedido), aviso.detalle)
        self.assertIn("nadie cotizó", aviso.detalle.lower())

    def test_h21_por_cada_destino_sin_agronomo_activo_se_avisa_al_gerente_una_sola_vez(self):
        """H21: si el Agrónomo de un destino está inactivo, avisa al Gerente (una sola vez aunque sean varios destinos sin Agrónomo)."""
        detalle_de_pedido(self.pedido, self.lechuga_sur, cantidad="10")
        for cuenta in (self.ana, self.beto):
            cuenta.is_active = False
            cuenta.save()
        self.automatica("agronomo_inactivo")
        self.assertEqual(list(Notificacion.objects.values_list("destinatario_id", flat=True)), [self.gerente.pk])

    def test_h21_nunca_se_notifica_a_quien_hizo_la_accion(self):
        """H21 y D-87 punto 3: con ``actor`` (el Gerente que dio de baja la cuenta), no se le avisa a él; sin nadie más a quien avisar, no hay notificaciones."""
        self.ana.is_active = False
        self.ana.save()
        self.automatica("agronomo_inactivo", actor=self.gerente)
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_h21_el_actor_agronomo_no_recibe_el_aviso_de_su_propia_accion(self):
        """H21: ``excluir=actor`` aplica a cualquier cuenta; Beto, que actúa, no se avisa a sí mismo pero Ana sí."""
        detalle_de_pedido(self.pedido, self.lechuga_sur, cantidad="10")
        self.automatica("agronomo_sin_invernadero", actor=self.beto)
        self.assertEqual(list(Notificacion.objects.values_list("destinatario_id", flat=True)), [self.ana.pk])

    def test_garantia_si_falla_la_auditoria_la_cancelacion_automatica_no_deja_nada(self):
        """Garantías mínimas: atómica también la automática; sin correo ni aviso si se revierte."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    pedidos.cancelar_pedido_automaticamente(self.pedido, "nadie_cotizo")
        self.assertEqual(pendientes, [])
        self.sin_cambios()
        self.assertEqual(EnlaceProveedor.objects.filter(estado="anulado").count(), 0)
