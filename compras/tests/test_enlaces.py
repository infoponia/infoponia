# Pruebas de compras/servicios/enlaces.py (CMP-02a, paso 3): el enlace del proveedor. Fuente: D-88, docs/patrones/enlace_del_proveedor.md (secciones 1 a 5)
# y docs/patrones/enlace_del_cliente.md (sección 8, «Pruebas mínimas»). Las pruebas de las vistas públicas (redirección sin el token, encabezados, la
# sesión que no abre otro pedido) van con CMP-ENV-COT (paso 4); la concurrencia, en ``test_pedidos_concurrencia.py``. El módulo se toma dentro de
# cada prueba (``perezoso``).

from datetime import timedelta

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.models import EnlaceProveedor
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, enlace_de, invitar
from compras.tests.fabricas import pedido as armar_pedido
from compras.tests.fabricas import proveedor
from core.enlaces import resumen_de
from core.tests.fabricas import BACKEND_QUE_FALLA, construir_url
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, perezoso
from maestros.tests.fabricas import crear_agronomo_con_invernadero

enlaces = perezoso("compras.servicios.enlaces")


class EnlacesBase(ConDatosDeInventario, TestCase):
    """Un pedido con un detalle, un proveedor invitado y su invitación."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero("Invernadero Norte")
        self.existencia = existencia(insumo("Lechuga", unidad="unidad"), self.invernadero, minimo=20, precio="12.50")
        self.proveedor = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.pedido = armar_pedido(self.agronomo, dias_al_limite=3)
        self.detalle = detalle_de_pedido(self.pedido, self.existencia, cantidad="20")
        self.invitacion = invitar(self.pedido, self.proveedor)

    def crear(self):
        """``crear_enlace`` dentro de una transacción, con los correos ejecutados. Devuelve ``(enlace, token)``."""
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                return enlaces.crear_enlace(self.invitacion, construir_url)


@override_settings(CORREO_CONFIGURADO=True)
class CrearYEnviarTests(EnlacesBase):
    """Crear el enlace (dentro de la transacción del caso de uso) y enviarlo (fuera de ella)."""

    def test_d88_el_token_no_esta_en_la_base_solo_su_resumen(self):
        """D-88 punto 1 y D-65 punto 2: la base guarda el SHA-256 del token; ni el token ni nada que lo contenga está en la fila."""
        enlace, token = self.crear()
        guardado = EnlaceProveedor.objects.filter(pk=enlace.pk).values().get()
        self.assertEqual(guardado["token_resumen"], resumen_de(token))
        self.assertEqual(len(guardado["token_resumen"]), 64)
        self.assertFalse(any(token in str(valor) for valor in guardado.values()))

    def test_d88_dos_enlaces_tienen_tokens_distintos(self):
        """Patrón del enlace del cliente, sección 8: dos tokens seguidos son distintos."""
        otra = invitar(self.pedido, proveedor("Otro", n=2, email="otro@x.com"))
        _, uno = self.crear()
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                _, dos = enlaces.crear_enlace(otra, construir_url)
        self.assertNotEqual(uno, dos)

    def test_d88_nace_vigente_y_sin_estado_de_envio(self):
        """D-88 punto 1: el enlace nace ``vigente``; el estado de envío es nulo hasta el intento."""
        with transaction.atomic():
            enlace, _ = enlaces.crear_enlace(self.invitacion, construir_url)
            self.assertEqual((enlace.estado, enlace.estado_envio), ("vigente", None))

    def test_d88_el_correo_sale_despues_del_commit_con_el_enlace_y_marca_enviado(self):
        """D-88 punto 6: el correo va en ``on_commit`` con la URL absoluta ``/proveedor/<token>/``; el enlace queda ``enviado``."""
        enlace, token = self.crear()
        enlace.refresh_from_db()
        self.assertEqual(enlace.estado_envio, "enviado")
        self.assertEqual([m.to for m in mail.outbox], [["ventas@sur.com"]])
        self.assertIn(f"https://infoponia.test/proveedor/{token}/", mail.outbox[0].body)

    def test_d88_un_rollback_no_envia_el_correo(self):
        """Patrón del enlace del cliente, sección 8: si el caso de uso se revierte, no sale ningún correo (``on_commit``)."""
        with self.captureOnCommitCallbacks(execute=True) as pendientes:
            try:
                with transaction.atomic():
                    enlaces.crear_enlace(self.invitacion, construir_url)
                    raise RuntimeError("se revierte")
            except RuntimeError:
                pass
        self.assertEqual((pendientes, mail.outbox), ([], []))
        self.assertEqual(EnlaceProveedor.objects.count(), 0)

    def test_d88_punto_6_si_el_correo_falla_queda_pendiente_de_envio(self):
        """D-88 punto 6: ``enviar_correo`` devuelve ``False`` → ``pendiente_envio``; sin reintento automático."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            enlace, _ = self.crear()
        enlace.refresh_from_db()
        self.assertEqual((enlace.estado_envio, enlace.estado), ("pendiente_envio", "vigente"))

    def test_d88_con_el_correo_sin_configurar_queda_pendiente_y_no_sale_nada(self):
        """API de correo, regla 5: ``enviar_correo`` no comprueba la configuración; el servicio pregunta antes y deja ``pendiente_envio``."""
        with override_settings(CORREO_CONFIGURADO=False):
            enlace, _ = self.crear()
        enlace.refresh_from_db()
        self.assertEqual((enlace.estado_envio, mail.outbox), ("pendiente_envio", []))

    def test_d88_no_se_envia_un_enlace_que_dejo_de_estar_vigente_entre_el_commit_y_el_envio(self):
        """Patrón, sección 3 (punto 1, adaptado): si otra operación lo anuló, no se envía nada."""
        with self.captureOnCommitCallbacks(execute=False):
            with transaction.atomic():
                enlace, token = enlaces.crear_enlace(self.invitacion, construir_url)
        EnlaceProveedor.objects.filter(pk=enlace.pk).update(estado="anulado")
        enlaces.enviar_invitacion(enlace.pk, construir_url(f"/proveedor/{token}/"))
        self.assertEqual(mail.outbox, [])

    def test_d88_el_correo_trae_el_pedido_el_proveedor_y_nada_del_precio(self):
        """CMP-RLZ-PED 12a: el correo dice a qué proveedor va, el pedido, el detalle (insumo, cantidad, invernadero y su dirección) y la fecha límite; sin precio."""
        self.crear()
        cuerpo = mail.outbox[0].body
        for texto in (str(self.pedido), "Semillas del Sur S. A.", "Lechuga", "20", "Invernadero Norte", "Calle 122 3310",
                      self.pedido.fecha_limite_cotizaciones.strftime("%d/%m/%Y")):
            self.assertIn(texto, cuerpo)
        self.assertNotIn("12,50", cuerpo)
        self.assertNotIn("12.50", cuerpo)

    def test_d88_a_lo_sumo_un_vigente_por_invitacion_crear_otro_es_un_error_de_uso(self):
        """D-88 punto 1: un segundo enlace vigente para la misma invitación no se crea (para reemplazar existe «Reenviar invitación», CMP-02b)."""
        self.crear()
        with self.assertRaises(ValueError):
            with transaction.atomic():
                enlaces.crear_enlace(self.invitacion, construir_url)


class AbrirEnlaceTests(EnlacesBase):
    """``enlace_por_token`` y ``situacion_del_enlace``: qué hace cada estado al abrirlo (D-88 puntos 2 y 3, extensiones 2a y 2b de CMP-ENV-COT)."""

    def situacion(self, enlace, **kwargs):
        return enlaces.situacion_del_enlace(enlace, **kwargs)

    def test_regla_un_token_inexistente_no_se_encuentra(self):
        """Patrón, sección 3: un token que no existe → «Este enlace no es válido»."""
        self.assertIsNone(enlaces.enlace_por_token("no-existe"))

    def test_regla_se_busca_por_el_resumen_del_token(self):
        """Patrón del enlace del cliente, sección 4 (punto 1): se compara el resumen, no el token."""
        enlace, token = enlace_de(self.invitacion)
        self.assertEqual(enlaces.enlace_por_token(token).pk, enlace.pk)

    def test_ext_2a_un_enlace_vigente_dentro_del_plazo_sirve(self):
        """CMP-ENV-COT paso 2: vigente, pedido en cotización, proveedor activo y hoy ≤ fecha límite."""
        enlace, _ = enlace_de(self.invitacion)
        self.assertEqual(self.situacion(enlace), "sirve")

    def test_regla_el_dia_de_la_fecha_limite_todavia_sirve_y_el_siguiente_no(self):
        """D-88 punto 2 y regla «Enlace del proveedor»: vence al terminar el día de la fecha límite; se lee del pedido (sin fecha de vencimiento propia)."""
        enlace, _ = enlace_de(self.invitacion)
        limite = self.pedido.fecha_limite_cotizaciones
        self.assertEqual(self.situacion(enlace, hoy=limite), "sirve")
        self.assertEqual(self.situacion(enlace, hoy=limite + timedelta(days=1)), "vencido")

    def test_ext_2a_el_pedido_que_ya_no_esta_en_cotizacion_no_deja_cotizar(self):
        """Extensión 2a: «el pedido ya no está en cotización» (cerrado o cancelado), con el motivo que corresponde."""
        enlace, _ = enlace_de(self.invitacion)
        self.pedido.estado_pedido = "cerrado"
        self.pedido.fecha_cierre_pedido = timezone.localdate()
        self.pedido.save()
        self.assertEqual(self.situacion(enlace), "pedido_cerrado")
        self.pedido.estado_pedido = "cancelado"
        self.pedido.causa_cancelacion = "nadie_cotizo"
        self.pedido.save()
        self.assertEqual(self.situacion(enlace), "pedido_cancelado")

    def test_ext_2a_un_proveedor_inactivo_no_puede_cotizar(self):
        """Extensión 2a y regla «Enlace del proveedor»: deja de servir cuando el proveedor pasa a inactivo."""
        enlace, _ = enlace_de(self.invitacion)
        self.proveedor.estado_proveedor = "inactivo"
        self.proveedor.save()
        self.assertEqual(self.situacion(enlace), "proveedor_inactivo")

    def test_ext_2a_un_enlace_reemplazado_o_anulado_nunca_muestra_nada_del_pedido(self):
        """D-88 punto 3: reemplazado, anulado o vencido nunca muestran nada del pedido."""
        for estado, esperado in (("reemplazado", "reemplazado"), ("anulado", "anulado"), ("vencido", "vencido")):
            with self.subTest(estado=estado):
                enlace, _ = enlace_de(invitar(armar_pedido(self.agronomo), self.proveedor), estado=estado)
                self.assertEqual(self.situacion(enlace), esperado)

    def test_ext_2b_un_enlace_usado_muestra_la_cotizacion_en_solo_lectura_hasta_el_ultimo_segundo_del_dia_limite(self):
        """Extensión 2b y H15.2 (D-88 punto 3): con el enlace ``usado`` el proveedor ve su cotización en solo lectura hasta el final del día de la fecha límite; después, nada."""
        enlace, _ = enlace_de(self.invitacion, estado="usado")
        cotizacion_de(self.pedido, self.proveedor, [(self.detalle, 20, "250.00", 2)])
        limite = self.pedido.fecha_limite_cotizaciones
        self.assertEqual(self.situacion(enlace, hoy=limite), "solo_lectura")
        self.assertEqual(self.situacion(enlace, hoy=limite + timedelta(days=1)), "vencido")

    def test_regla_la_cotizacion_enviada_de_un_proveedor_que_paso_a_inactivo_se_mantiene(self):
        """CMP-ENV-COT regla «Proveedor que pasa a inactivo»: la cotización que ya envió se mantiene (el enlace usado sigue en solo lectura)."""
        enlace, _ = enlace_de(self.invitacion, estado="usado")
        self.proveedor.estado_proveedor = "inactivo"
        self.proveedor.save()
        self.assertEqual(self.situacion(enlace), "solo_lectura")

    def test_regla_un_enlace_usado_con_el_pedido_cancelado_no_muestra_nada(self):
        """D-88 punto 2: al cancelarse el pedido el enlace deja de servir, también para ver la cotización."""
        enlace, _ = enlace_de(self.invitacion, estado="usado")
        self.pedido.estado_pedido = "cancelado"
        self.pedido.causa_cancelacion = "manual"
        self.pedido.motivo_cancelacion = "Ya no hace falta"
        self.pedido.fecha_cierre_pedido = timezone.localdate()
        self.pedido.save()
        self.assertEqual(self.situacion(enlace), "pedido_cancelado")

    def test_regla_bloquear_enlace_devuelve_la_fila_releida(self):
        """Patrón, sección 4: ``bloquear_enlace`` toma ``FOR NO KEY UPDATE`` dentro de una transacción y devuelve el enlace con su estado real."""
        enlace, _ = enlace_de(self.invitacion)
        EnlaceProveedor.objects.filter(pk=enlace.pk).update(estado="anulado")
        with transaction.atomic():
            releido = enlaces.bloquear_enlace(enlace.pk)
        self.assertEqual(releido.estado, "anulado")
