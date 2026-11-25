# Pruebas de CMP-AUT-PED · Generar Pedidos Automáticos por Stock Bajo (CMP-07, pasos 2 y 3): el servicio de ``compras/servicios/pedidos_automaticos.py`` y el paso diario 63.
# Fuente: docs/casos_de_uso/compras/pedido_automatico.md (flujo básico, extensiones 1a, 1b, 3a, 5a, 5b y 8a, reglas y postcondiciones), D-104 (cantidad, margen, quién,
# proveedores, plazo y avisos), D-56 (el contrato del proceso diario y el orden 63), D-87 punto 3 (regla única de destinatarios) y D-22/D-27 (auditoría como InfoPonia).
# El módulo se toma dentro de cada prueba (``perezoso``), así que mientras no existe falla cada prueba por separado. Los correos salen en ``on_commit``: las pruebas los
# ejecutan con ``captureOnCommitCallbacks``. Decisiones de esta tarea que el estudiante aprobó el 25/11/2026 (se suman a D-104): los textos de los avisos 3a y 5a, que «una
# vez por día» se resuelve sin columna (no se repite si la cuenta ya tiene una notificación con el mismo título, que lleva la fecha de ``hoy``), que 5a (sin Agrónomo) se
# evalúa antes que 3a, y que con ``URL_DEL_SITIO`` vacía la invitación queda «pendiente de envío» (8a).

from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from compras.models import DetallePedido, EnlaceProveedor, InvitacionPedido, Pedido
from compras.tests.fabricas import cotizacion_de, detalle_de_pedido, orden_de, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core import procesos as procesos_de_core
from core.models import Notificacion, RegistroAuditoria
from core.procesos import ResumenDePaso
from core.tests.fabricas import BACKEND_QUE_FALLA, crear_gerente
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, perezoso, tipo_de_insumo
from maestros.models import Alerta
from maestros.servicios import configuracion
from maestros.tests.fabricas import crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero

automaticos = perezoso("compras.servicios.pedidos_automaticos")

CODIGO = "generar_pedidos_automaticos"
URL_DEL_SITIO = "https://sitio.test"


def con_margen(margen=None, dias_limite=None):
    """Cambia el margen del pedido automático y/o los días límite de la configuración operativa, directo en la fila."""
    fila = configuracion.obtener()
    if margen is not None:
        fila.porc_margen_pedido_automatico = margen
    if dias_limite is not None:
        fila.dias_limite_cotizacion = dias_limite
    fila.save()


class CalcularCantidadTests(SimpleTestCase):
    """Regla «Cantidad» de CMP-AUT-PED y punto 3 de D-104: ``mínimo × (1 + margen/100) − (libre + tránsito)``, hacia arriba a los decimales de la unidad."""

    def calcular(self, minimo, libre, transito, margen, unidad):
        return automaticos.calcular_cantidad(Decimal(minimo), Decimal(libre), Decimal(transito), margen, unidad)

    def test_regla_cantidad_aplica_el_margen_y_resta_lo_libre_y_lo_que_esta_en_transito(self):
        """D-104 punto 3: mínimo 20, margen 20 %, libre 5 y tránsito 3 → 20 × 1,2 − 8 = 16."""
        self.assertEqual(self.calcular("20", "5", "3", 20, "unidad"), Decimal("16"))

    def test_regla_cantidad_con_margen_0_coincide_con_la_sugerida_manual(self):
        """D-104 punto 3: «con 0 coincide con la sugerida manual» (mínimo − (libre + tránsito)) de CMP-RLZ-PED."""
        self.assertEqual(self.calcular("20", "5", "3", 0, "unidad"), Decimal("12"))

    def test_regla_cantidad_se_redondea_hacia_arriba_y_no_a_la_mitad(self):
        """D-104 punto 3: 10 × 1,04 = 10,4 → 11 en «unidad» (la mitad hacia arriba daría 10); 1,234 × 1,01 = 1,24634 → 1,247 en kg (no 1,246)."""
        self.assertEqual(self.calcular("10", "0", "0", 4, "unidad"), Decimal("11"))
        self.assertEqual(self.calcular("1.234", "0", "0", 1, "kg"), Decimal("1.247"))

    def test_regla_cantidad_usa_los_decimales_de_la_unidad(self):
        """D-104 punto 3: los decimales son los que admite la unidad (g: 2): 3,013 → 3,02."""
        self.assertEqual(self.calcular("3.01", "0", "0", 0, "g"), Decimal("3.01"))
        self.assertEqual(self.calcular("2.5", "0", "0", 21, "g"), Decimal("3.03"))

    def test_regla_cantidad_un_libre_negativo_suma(self):
        """Regla «Insumo bajo el mínimo»: lo libre puede ser negativo (reservado mayor que lo vigente); entonces se pide de más: 24 − (−4) = 28."""
        self.assertEqual(self.calcular("20", "-4", "0", 20, "unidad"), Decimal("28"))

    def test_regla_cantidad_un_margen_entero_no_agrega_ruido_decimal(self):
        """D-104 punto 3: mínimo 5 kg con 20 % → 6 kg exactos."""
        self.assertEqual(self.calcular("5", "0", "0", 20, "kg"), Decimal("6"))


class AutomaticoBase(ConDatosDeInventario, TestCase):
    """Ana (Norte), un Gerente, una categoría «Fertilizantes» con dos insumos bajo el mínimo en Norte (lechuga por unidad, mínimo 20; nutriente en kg, mínimo 5) y dos
    proveedores activos especializados en esa categoría. Margen 20 %, 3 días límite: la lechuga pide 24 y el nutriente 6."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.config = override_settings(CORREO_CONFIGURADO=True, URL_DEL_SITIO=URL_DEL_SITIO)
        self.config.enable()
        self.addCleanup(self.config.disable)
        self.gerente = crear_gerente()
        self.ana, self.norte = crear_agronomo_con_invernadero("Norte", email="ana@infoponia.com")
        self.tipo = tipo_de_insumo("Fertilizantes")
        self.lechuga = existencia(insumo("Lechuga", self.tipo, unidad="unidad"), self.norte, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", self.tipo, unidad="kg"), self.norte, minimo=5, precio="100.00")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com", especialidades=[self.tipo])
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com", especialidades=[self.tipo])

    def correr(self, hoy=None):
        """El paso con los correos ejecutados; devuelve su ``ResumenDePaso``."""
        with self.captureOnCommitCallbacks(execute=True):
            return automaticos.generar_pedidos_automaticos(hoy or self.hoy)

    def pedido_de(self, invernadero):
        """El único pedido cuyos detalles son de ``invernadero``."""
        return Pedido.objects.filter(detalles__insumo_invernadero__invernadero=invernadero).distinct().get()

    def segundo_invernadero(self):
        """Beto, con el invernadero Sur y un insumo bajo el mínimo (tomate)."""
        beto, sur = crear_agronomo_con_invernadero("Sur", email="beto@infoponia.com")
        tomate = existencia(insumo("Tomate", self.tipo, unidad="unidad"), sur, minimo=10, precio="8.00")
        return beto, sur, tomate

    def avisos(self, cuenta):
        return Notificacion.objects.filter(destinatario=cuenta)


class GeneracionDelPedidoTests(AutomaticoBase):
    """Flujo básico (pasos 1 a 8) y postcondiciones de CMP-AUT-PED."""

    def test_flujo_principal_crea_un_pedido_por_invernadero_a_nombre_de_su_agronomo(self):
        """Flujo básico, paso 5 y D-104 puntos 2 y 4: un pedido por invernadero con sus insumos bajo el mínimo, «en cotización» a nombre de su Agrónomo."""
        beto, sur, tomate = self.segundo_invernadero()
        resumen = self.correr()
        self.assertEqual(Pedido.objects.count(), 2)
        pedido_norte, pedido_sur = self.pedido_de(self.norte), self.pedido_de(sur)
        self.assertEqual((pedido_norte.agronomo_id, pedido_sur.agronomo_id), (self.ana.pk, beto.pk))
        self.assertEqual(set(pedido_norte.detalles.values_list("insumo_invernadero_id", flat=True)), {self.lechuga.pk, self.nutriente.pk})
        self.assertEqual(list(pedido_sur.detalles.values_list("insumo_invernadero_id", flat=True)), [tomate.pk])
        for pedido in (pedido_norte, pedido_sur):
            self.assertEqual(pedido.estado_pedido, Pedido.Estado.EN_COTIZACION)
            self.assertEqual((pedido.fecha_pedido, pedido.fecha_cierre_pedido), (self.hoy, None))
        self.assertEqual(tuple(resumen)[:3], (2, 2, 0))

    def test_flujo_principal_cantidades_con_el_margen_y_precio_de_referencia_copiado_ahora(self):
        """Paso 2 y 5, D-104 punto 3: lechuga 20 × 1,2 = 24 y nutriente 5 × 1,2 = 6; cada detalle copia el precio de referencia del insumo en el invernadero."""
        self.correr()
        por_iin = {d.insumo_invernadero_id: d for d in DetallePedido.objects.all()}
        self.assertEqual(por_iin[self.lechuga.pk].cantidad_detalle, Decimal("24"))
        self.assertEqual(por_iin[self.nutriente.pk].cantidad_detalle, Decimal("6"))
        self.assertEqual(por_iin[self.lechuga.pk].precio_unitario_de_pedido, Decimal("12.50"))
        self.assertEqual(por_iin[self.nutriente.pk].precio_unitario_de_pedido, Decimal("100.00"))

    def test_regla_cantidad_toma_el_margen_vigente_de_la_configuracion(self):
        """D-104 punto 3: el margen es ``porc_margen_pedido_automatico`` de la configuración operativa (se lee en cada corrida): con 50 %, la lechuga pide 30."""
        con_margen(margen=50)
        self.correr()
        self.assertEqual(DetallePedido.objects.get(insumo_invernadero=self.lechuga).cantidad_detalle, Decimal("30"))

    def test_regla_cantidad_con_margen_0_coincide_con_la_sugerida_de_la_pantalla_manual(self):
        """D-104 punto 3: con margen 0 la cantidad es la ``sugerida`` de ``insumos_bajo_el_minimo`` (CMP-RLZ-PED), con lo libre y lo que está en tránsito."""
        from compras.servicios import pedidos as pedidos_manuales

        lote(self.lechuga, 5)
        InsumoInvernadero.objects.filter(pk=self.lechuga.pk).update(cant_transito_insumo=Decimal("3"))
        con_margen(margen=0)
        sugeridas = {f.iin.pk: f.sugerida for f in pedidos_manuales.insumos_bajo_el_minimo(self.ana)}
        self.correr()
        for detalle in DetallePedido.objects.all():
            with self.subTest(insumo=detalle.insumo_invernadero.insumo):
                self.assertEqual(detalle.cantidad_detalle, sugeridas[detalle.insumo_invernadero_id])
        self.assertEqual(DetallePedido.objects.get(insumo_invernadero=self.lechuga).cantidad_detalle, Decimal("12"))

    def test_regla_cantidad_resta_lo_libre_y_lo_que_esta_en_transito(self):
        """D-104 punto 3: la lechuga con 5 libres y 3 en tránsito pide 24 − 8 = 16."""
        lote(self.lechuga, 5)
        InsumoInvernadero.objects.filter(pk=self.lechuga.pk).update(cant_transito_insumo=Decimal("3"))
        self.correr()
        self.assertEqual(DetallePedido.objects.get(insumo_invernadero=self.lechuga).cantidad_detalle, Decimal("16"))

    def test_paso_4_la_fecha_limite_es_hoy_mas_los_dias_limite_de_la_configuracion(self):
        """Flujo básico, paso 4 y D-104 punto 6: ``hoy + dias_limite_cotizacion``, con la ``hoy`` que recibe el paso (no la del reloj)."""
        con_margen(dias_limite=5)
        otro_dia = self.hoy + timedelta(days=10)
        self.correr(hoy=otro_dia)
        pedido = Pedido.objects.get()
        self.assertEqual((pedido.fecha_pedido, pedido.fecha_limite_cotizaciones), (otro_dia, otro_dia + timedelta(days=5)))

    def test_paso_3_invita_solo_a_proveedores_activos_con_correo_especializados_en_el_tipo(self):
        """Flujo básico, paso 3 y D-104 punto 5: activos, con correo y especializados en el tipo de algún insumo del pedido (MD-121); no los de otra categoría, los inactivos ni los sin correo."""
        otro_tipo = tipo_de_insumo("Herramientas")
        proveedor("Ferretería", n=3, email="f@f.com", especialidades=[otro_tipo])
        proveedor("De baja", n=4, email="baja@x.com", activo=False, especialidades=[self.tipo])
        proveedor("Sin correo", n=5, email="", especialidades=[self.tipo])
        proveedor("Sin especialidad", n=6, email="s@s.com")
        self.correr()
        pedido = Pedido.objects.get()
        self.assertEqual(set(pedido.invitaciones.values_list("proveedor_id", flat=True)), {self.sur.pk, self.este.pk})

    def test_paso_5_una_invitacion_y_un_enlace_vigente_por_proveedor(self):
        """Flujo básico, paso 5 y postcondición a: una invitación y un enlace «vigente» por cada proveedor invitado."""
        self.correr()
        self.assertEqual(InvitacionPedido.objects.count(), 2)
        self.assertEqual(EnlaceProveedor.objects.filter(estado=EnlaceProveedor.Estado.VIGENTE).count(), 2)
        for invitacion in InvitacionPedido.objects.all():
            self.assertEqual(invitacion.enlaces.count(), 1)

    def test_paso_6_audita_alta_pedido_como_infoponia_con_el_origen_el_margen_y_los_insumos(self):
        """Flujo básico, paso 6, postcondición b y D-22/D-27: ``alta_pedido`` sin usuario y con el rol ``infoponia``; el detalle dice «automático», el margen y los insumos."""
        self.correr()
        registro = RegistroAuditoria.objects.get(accion="alta_pedido")
        self.assertEqual((registro.usuario_id, registro.rol), (None, "infoponia"))
        pedido = Pedido.objects.get()
        self.assertIn(("compras.pedido", pedido.pk), [(a["modelo"], a["id"]) for a in registro.afectados])
        datos = registro.detalle["datos"]
        self.assertEqual(datos["origen"], "automático")
        self.assertEqual(datos["porc_margen_pedido_automatico"], 20)
        self.assertEqual(len(datos["detalles"]), 2)
        self.assertEqual(len(datos["invitaciones"]), 2)
        self.assertEqual(registro.detalle["cambios"]["estado"], {"antes": None, "despues": "en_cotizacion"})

    def test_post_c_notifica_al_agronomo_del_invernadero_y_a_nadie_mas(self):
        """Flujo básico, paso 7, postcondición c y D-104 punto 7: «Pedido P-… creado automáticamente: N insumos bajo el mínimo en <invernadero>» para el Agrónomo."""
        self.correr()
        pedido = Pedido.objects.get()
        (aviso,) = self.avisos(self.ana)
        self.assertEqual(aviso.titulo, f"Pedido {pedido} creado automáticamente")
        self.assertIn("2 insumos bajo el mínimo en Norte", aviso.detalle)
        self.assertEqual(self.avisos(self.gerente).count(), 0)

    def test_post_c_con_un_solo_insumo_el_aviso_va_en_singular(self):
        """Paso 7: «1 insumo bajo el mínimo»."""
        lote(self.nutriente, 6)
        self.correr()
        (aviso,) = self.avisos(self.ana)
        self.assertIn("1 insumo bajo el mínimo en Norte", aviso.detalle)

    def test_post_d_envia_un_correo_a_cada_proveedor_con_su_enlace_y_sin_precios(self):
        """Flujo básico, paso 8 y postcondición d: un correo por proveedor con su enlace (de ``URL_DEL_SITIO``), el detalle y la fecha límite; sin el precio de referencia (CMP-RLZ-PED, garantía mínima)."""
        self.correr()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        for correo in mail.outbox:
            with self.subTest(para=correo.to):
                self.assertIn(f"{URL_DEL_SITIO}/proveedor/", correo.body)
                self.assertIn("Lechuga", correo.body)
                self.assertNotIn("12,50", correo.body)
                self.assertNotIn("12.50", correo.body)
        self.assertEqual(
            set(EnlaceProveedor.objects.values_list("estado_envio", flat=True)), {EnlaceProveedor.EstadoEnvio.ENVIADO}
        )

    def test_post_e_la_alerta_de_bajo_el_minimo_sigue_activa(self):
        """Postcondición e y D-104 punto 7: pedir no resuelve la alerta de «bajo el mínimo» (se resuelve al recibir)."""
        from inventario.servicios import alertas_de_stock

        lote(self.lechuga, 1)
        alertas_de_stock.reevaluar_alertas_del_insumo(self.lechuga.pk)
        activas = Alerta.objects.activas().count()
        self.assertGreater(activas, 0)
        self.correr()
        self.assertEqual(Alerta.objects.activas().count(), activas)

    def test_regla_no_toca_stock_transito_minimo_reservas_ni_movimientos(self):
        """Reglas de CMP-AUT-PED: «No toca stock, tránsito, mínimo, reservas ni contabilidad»."""
        lote(self.lechuga, 5)
        antes = (
            list(InsumoInvernadero.objects.order_by("id").values()),
            list(LoteInsumo.objects.order_by("id").values()),
            MovimientoInsumo.objects.count(),
        )
        self.correr()
        despues = (
            list(InsumoInvernadero.objects.order_by("id").values()),
            list(LoteInsumo.objects.order_by("id").values()),
            MovimientoInsumo.objects.count(),
        )
        self.assertEqual(antes, despues)

    def test_post_f_el_resumen_cuenta_invernaderos_revisados_y_pedidos_creados(self):
        """Postcondición f: ``ResumenDePaso(procesados=invernaderos revisados, creados=pedidos creados, resueltos=0, detalle)``; un invernadero activo sin nada bajo el mínimo también se revisa."""
        crear_invernadero("Vacío", agronomo=crear_agronomo(email="vacio@infoponia.com"))
        resumen = self.correr()
        self.assertIsInstance(resumen, ResumenDePaso)
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (2, 1, 0))

    def test_regla_un_pedido_cancelado_con_el_insumo_todavia_bajo_el_minimo_permite_otro(self):
        """Regla de CMP-AUT-PED (intencional): si el pedido se cancela (pasos 60 y 62) y el insumo sigue bajo el mínimo, el paso 63 puede crear otro."""
        from compras.servicios import pedidos as pedidos_manuales

        self.correr()
        primero = Pedido.objects.get()
        pedidos_manuales.cancelar_pedido_automaticamente(primero, Pedido.Causa.NADIE_COTIZO, hoy=self.hoy)
        self.correr()
        self.assertEqual(Pedido.objects.count(), 2)
        self.assertEqual(Pedido.objects.filter(estado_pedido=Pedido.Estado.EN_COTIZACION).count(), 1)


class PrecondicionesTests(AutomaticoBase):
    """Precondiciones a y b de CMP-AUT-PED."""

    def test_pre_a_un_invernadero_inactivo_no_genera_pedido(self):
        """Precondición a: solo los invernaderos activos."""
        inactivo = crear_invernadero("Inactivo", activo=False, agronomo=crear_agronomo(email="in@infoponia.com"))
        existencia(insumo("Cal", self.tipo, unidad="kg"), inactivo, minimo=5)
        self.correr()
        self.assertFalse(DetallePedido.objects.filter(insumo_invernadero__invernadero=inactivo).exists())
        self.assertEqual(Pedido.objects.count(), 1)

    def test_pre_b_un_insumo_deshabilitado_o_del_catalogo_inactivo_no_se_pide(self):
        """Precondición b: el insumo tiene que estar habilitado y activo en el invernadero (y activo en el catálogo)."""
        existencia(insumo("Deshabilitado", self.tipo, unidad="kg"), self.norte, minimo=5, activo=False)
        existencia(insumo("De baja", self.tipo, unidad="kg", activo=False), self.norte, minimo=5)
        self.correr()
        nombres = set(DetallePedido.objects.values_list("insumo_invernadero__insumo__nombre_insumo", flat=True))
        self.assertEqual(nombres, {"Lechuga", "Nutriente"})

    def test_pre_b_sin_minimo_o_sobre_el_minimo_no_se_pide(self):
        """Precondición b: ``bajo_minimo`` es la misma condición de la pantalla manual: sin mínimo, o con libre + tránsito igual o mayor, no se pide."""
        existencia(insumo("Sin mínimo", self.tipo, unidad="kg"), self.norte, minimo=0)
        lote(self.nutriente, 5)  # justo en el mínimo: no está bajo
        self.correr()
        nombres = set(DetallePedido.objects.values_list("insumo_invernadero__insumo__nombre_insumo", flat=True))
        self.assertEqual(nombres, {"Lechuga"})

    def test_pre_b_el_stock_vencido_no_cuenta_como_libre(self):
        """Precondición b: el mismo criterio de la alerta: los lotes vencidos no cuentan (``stock.existencias`` con ``hoy``)."""
        lote(self.lechuga, 30, vence=self.hoy - timedelta(days=1))
        self.correr()
        self.assertTrue(DetallePedido.objects.filter(insumo_invernadero=self.lechuga).exists())


class ExtensionesTests(AutomaticoBase):
    """Extensiones 1a, 1b, 3a, 5a y 8a de CMP-AUT-PED."""

    # ---- 1a ----

    def test_ext_1a_sin_insumos_bajo_el_minimo_no_crea_nada_ni_falla(self):
        """Extensión 1a: ningún insumo cumple → no se crea nada, no se audita, no se avisa y el paso termina sin error."""
        lote(self.lechuga, 25)
        lote(self.nutriente, 6)
        resumen = self.correr()
        self.assertEqual((Pedido.objects.count(), RegistroAuditoria.objects.filter(accion="alta_pedido").count(), Notificacion.objects.count()), (0, 0, 0))
        self.assertEqual((resumen.procesados, resumen.creados, resumen.resueltos), (1, 0, 0))
        self.assertEqual(mail.outbox, [])

    def test_ext_1a_dos_corridas_el_mismo_dia_no_duplican(self):
        """Extensión 1a (idempotencia, D-56 punto 4): la segunda corrida ve los insumos ya pedidos y no crea nada."""
        self.correr()
        segunda = self.correr()
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(DetallePedido.objects.count(), 2)
        self.assertEqual(segunda.creados, 0)
        self.assertEqual(self.avisos(self.ana).count(), 1)
        self.assertEqual(len(mail.outbox), 2)

    # ---- 1b ----

    def test_ext_1b_saltea_los_insumos_que_ya_estan_en_otro_pedido_en_cotizacion(self):
        """Extensión 1b: la lechuga ya está en otro pedido «en cotización» → se pide solo el nutriente."""
        previo = armar_pedido(self.ana)
        detalle_de_pedido(previo, self.lechuga, cantidad="24")
        self.correr()
        nuevo = Pedido.objects.exclude(pk=previo.pk).get()
        self.assertEqual(list(nuevo.detalles.values_list("insumo_invernadero_id", flat=True)), [self.nutriente.pk])

    def test_ext_1b_saltea_el_insumo_de_una_orden_pendiente_de_aprobacion(self):
        """Extensión 1b y D-104 punto 2: un pedido «cerrado» cuya orden de compra está «pendiente de aprobación» también cuenta como ya pedido (``ya_pedido``)."""
        previo = armar_pedido(self.ana)
        detalle = detalle_de_pedido(previo, self.lechuga, cantidad="24")
        orden_de(previo, [cotizacion_de(previo, self.sur, [(detalle, 24, "300.00", 3)])])
        self.correr()
        nuevo = Pedido.objects.exclude(pk=previo.pk).get()
        self.assertEqual(list(nuevo.detalles.values_list("insumo_invernadero_id", flat=True)), [self.nutriente.pk])

    def test_ext_1b_si_todos_estan_ya_pedidos_no_crea_nada(self):
        """Extensión 1b y 1a: con todos los insumos ya pedidos no queda ninguno, no se crea nada y no se avisa."""
        previo = armar_pedido(self.ana)
        detalle_de_pedido(previo, self.lechuga)
        detalle_de_pedido(previo, self.nutriente)
        self.correr()
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(Notificacion.objects.count(), 0)

    # ---- 3a ----

    def titulo_sin_proveedores(self, invernadero="Norte", fecha=None):
        return f"Sin proveedores para el pedido automático de {invernadero} ({(fecha or self.hoy):%d/%m/%Y})"

    def test_ext_3a_sin_proveedores_no_crea_el_pedido_y_avisa_al_agronomo_y_al_gerente(self):
        """Extensión 3a: no hay proveedores a invitar → no se crea el pedido y se avisa al Agrónomo y al Gerente (textos aprobados el 25/11/2026)."""
        self.sur.estado_proveedor = self.este.estado_proveedor = "inactivo"
        self.sur.save()
        self.este.save()
        resumen = self.correr()
        self.assertEqual((Pedido.objects.count(), resumen.creados), (0, 0))
        for cuenta in (self.ana, self.gerente):
            with self.subTest(cuenta=cuenta):
                (aviso,) = self.avisos(cuenta)
                self.assertEqual(aviso.titulo, self.titulo_sin_proveedores())
                self.assertEqual(
                    aviso.detalle,
                    "Hay 2 insumos bajo el mínimo en Norte, pero ningún proveedor activo se especializa en sus categorías. "
                    "Pedile al Gerente que revise los proveedores o armá el pedido a mano.",
                )
        self.assertIn("sin proveedores", resumen.detalle)

    def test_ext_3a_un_proveedor_de_otra_categoria_no_cuenta(self):
        """Extensión 3a y MD-121: un proveedor activo que no se especializa en el tipo de ningún insumo del pedido no sirve."""
        otro = tipo_de_insumo("Herramientas")
        self.sur.especialidades.set([otro])
        self.este.especialidades.set([otro])
        self.correr()
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertEqual(self.avisos(self.ana).count(), 1)

    def test_ext_3a_avisa_una_sola_vez_por_dia_y_por_invernadero(self):
        """Extensión 3a y D-56 punto 4: dos corridas el mismo día no repiten el aviso; al día siguiente (otra ``hoy``) se avisa de nuevo."""
        self.sur.estado_proveedor = self.este.estado_proveedor = "inactivo"
        self.sur.save()
        self.este.save()
        self.correr()
        self.correr()
        self.assertEqual((self.avisos(self.ana).count(), self.avisos(self.gerente).count()), (1, 1))
        self.correr(hoy=self.hoy + timedelta(days=1))
        self.assertEqual((self.avisos(self.ana).count(), self.avisos(self.gerente).count()), (2, 2))

    def test_ext_3a_cada_invernadero_avisa_por_separado(self):
        """Extensión 3a: «una vez por día y por invernadero»: dos invernaderos sin proveedores dan dos avisos distintos a su Agrónomo."""
        beto, sur, _ = self.segundo_invernadero()
        self.sur.estado_proveedor = self.este.estado_proveedor = "inactivo"
        self.sur.save()
        self.este.save()
        self.correr()
        self.assertEqual([a.titulo for a in self.avisos(self.ana)], [self.titulo_sin_proveedores("Norte")])
        self.assertEqual([a.titulo for a in self.avisos(beto)], [self.titulo_sin_proveedores("Sur")])
        self.assertEqual(self.avisos(self.gerente).count(), 2)

    def test_ext_3a_un_proveedor_sin_correo_no_cuenta(self):
        """Extensión 3a y D-104 punto 5: solo los proveedores con correo; si el único activo no tiene, es 3a."""
        for p in (self.sur, self.este):
            p.email_proveedor = ""
            p.save()
        self.correr()
        self.assertEqual((Pedido.objects.count(), self.avisos(self.ana).count()), (0, 1))

    # ---- 5a ----

    def titulo_sin_agronomo(self, invernadero, fecha=None):
        return f"Pedido automático sin Agrónomo en {invernadero} ({(fecha or self.hoy):%d/%m/%Y})"

    def huerfano(self, **personal):
        """Un invernadero activo sin Agrónomo, con un insumo bajo el mínimo."""
        invernadero = crear_invernadero("Huérfano", **personal)
        existencia(insumo("Cal", self.tipo, unidad="kg"), invernadero, minimo=5)
        return invernadero

    def test_ext_5a_sin_agronomo_no_crea_el_pedido_y_avisa_al_gerente(self):
        """Extensión 5a y D-104 punto 4: sin Agrónomo activo a cargo no se crea el pedido; se avisa al Gerente (texto aprobado el 25/11/2026)."""
        huerfano = self.huerfano()
        resumen = self.correr()
        self.assertFalse(DetallePedido.objects.filter(insumo_invernadero__invernadero=huerfano).exists())
        titulos = [a.titulo for a in self.avisos(self.gerente)]
        self.assertEqual(titulos, [self.titulo_sin_agronomo("Huérfano")])
        self.assertEqual(
            self.avisos(self.gerente).get().detalle,
            "Hay 1 insumo bajo el mínimo en Huérfano, pero no tiene un Agrónomo activo a cargo: no se creó el pedido. Asignale uno para que el paso lo arme.",
        )
        self.assertIn("sin Agrónomo", resumen.detalle)

    def test_ext_5a_un_agronomo_inactivo_equivale_a_no_tener(self):
        """Extensión 5a: el Agrónomo a cargo está dado de baja → tampoco se crea el pedido (se avisa al Gerente)."""
        baja = crear_agronomo(email="baja@infoponia.com", activo=False)
        huerfano = self.huerfano(agronomo=baja)
        self.correr()
        self.assertFalse(DetallePedido.objects.filter(insumo_invernadero__invernadero=huerfano).exists())
        self.assertEqual([a.titulo for a in self.avisos(self.gerente)], [self.titulo_sin_agronomo("Huérfano")])
        self.assertEqual(self.avisos(baja).count(), 0)

    def test_ext_5a_avisa_una_sola_vez_por_dia(self):
        """Extensión 5a y D-56 punto 4 (idempotencia): dos corridas el mismo día dejan un aviso; otro día, otro."""
        self.huerfano()
        self.correr()
        self.correr()
        self.assertEqual(self.avisos(self.gerente).count(), 1)
        self.correr(hoy=self.hoy + timedelta(days=1))
        self.assertEqual(self.avisos(self.gerente).count(), 2)

    def test_ext_5a_sin_gerente_activo_no_falla(self):
        """Extensión 5a y D-14/D-42: sin Gerente activo ``notificar_al_gerente`` no hace nada y el paso no falla."""
        self.gerente.is_active = False
        self.gerente.save()
        self.huerfano()
        self.correr()
        self.assertEqual(Notificacion.objects.filter(titulo__startswith="Pedido automático sin Agrónomo").count(), 0)

    def test_ext_5a_un_invernadero_sin_agronomo_no_impide_los_demas(self):
        """Regla «un invernadero que no corresponde no frena a los otros»: Norte igual recibe su pedido."""
        self.huerfano()
        resumen = self.correr()
        self.assertEqual(Pedido.objects.get().agronomo_id, self.ana.pk)
        self.assertEqual((resumen.procesados, resumen.creados), (2, 1))

    # ---- 8a ----

    def test_ext_8a_un_correo_que_falla_deja_el_enlace_pendiente_y_no_revierte_el_pedido(self):
        """Extensión 8a (12a de CMP-RLZ-PED): el pedido, la invitación y el enlace quedan; el enlace pasa a «pendiente de envío»."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            self.correr()
        self.assertEqual((Pedido.objects.count(), InvitacionPedido.objects.count()), (1, 2))
        self.assertEqual(
            set(EnlaceProveedor.objects.values_list("estado_envio", flat=True)), {EnlaceProveedor.EstadoEnvio.PENDIENTE_ENVIO}
        )
        self.assertEqual(EnlaceProveedor.objects.filter(estado=EnlaceProveedor.Estado.VIGENTE).count(), 2)

    def test_ext_8a_sin_url_del_sitio_no_se_manda_un_enlace_roto(self):
        """Extensión 8a y respuesta del estudiante (25/11/2026): con ``URL_DEL_SITIO`` vacía el enlace del correo no se puede armar → no se envía y queda «pendiente de envío»."""
        with override_settings(URL_DEL_SITIO=""):
            self.correr()
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual(
            set(EnlaceProveedor.objects.values_list("estado_envio", flat=True)), {EnlaceProveedor.EstadoEnvio.PENDIENTE_ENVIO}
        )

    def test_ext_8a_sin_el_correo_del_sistema_configurado_queda_pendiente(self):
        """Extensión 8a: con el correo del sistema sin configurar no se envía nada y los enlaces quedan «pendiente de envío»; el pedido se crea igual."""
        with override_settings(CORREO_CONFIGURADO=False):
            self.correr()
        self.assertEqual((mail.outbox, Pedido.objects.count()), ([], 1))
        self.assertEqual(
            set(EnlaceProveedor.objects.values_list("estado_envio", flat=True)), {EnlaceProveedor.EstadoEnvio.PENDIENTE_ENVIO}
        )


class RelecturaConBloqueoTests(AutomaticoBase):
    """Extensión 5b (determinista): entre la lectura y el bloqueo cambia algo y se relee con todo bloqueado. El cambio se hace justo antes de bloquear el invernadero, con la
    misma conexión (equivale a lo que otra sesión ya confirmó). Las carreras con dos hilos están en ``test_pedidos_automaticos_concurrencia.py``."""

    def antes_de_bloquear(self, cambio):
        """Un parche de ``bloquear_invernadero_activo`` que hace ``cambio()`` la primera vez y sigue con el bloqueo real."""
        real = automaticos.bloquear_invernadero_activo
        hecho = []

        def envoltura(invernadero_id):
            if not hecho:
                hecho.append(True)
                cambio()
            return real(invernadero_id)

        return mock.patch("compras.servicios.pedidos_automaticos.bloquear_invernadero_activo", side_effect=envoltura)

    def test_ext_5b_otro_pedido_que_toma_todos_los_insumos_no_genera_uno_repetido(self):
        """Extensión 5b: entre la lectura y el bloqueo otro pedido «en cotización» toma los dos insumos → con todo releído ya no corresponde y no se crea nada."""
        def pedido_manual():
            previo = armar_pedido(self.ana)
            detalle_de_pedido(previo, self.lechuga)
            detalle_de_pedido(previo, self.nutriente)

        with self.antes_de_bloquear(pedido_manual):
            resumen = self.correr()
        self.assertEqual(Pedido.objects.count(), 1)
        self.assertEqual((resumen.creados, self.avisos(self.ana).count(), len(mail.outbox)), (0, 0, 0))

    def test_ext_5b_si_solo_toma_uno_se_piden_los_demas(self):
        """Extensión 5b y 1b: si el otro pedido toma solo la lechuga, el automático (releído) pide solo el nutriente."""
        def pedido_manual():
            detalle_de_pedido(armar_pedido(self.ana), self.lechuga)

        with self.antes_de_bloquear(pedido_manual):
            self.correr()
        nuevo = Pedido.objects.exclude(detalles__insumo_invernadero=self.lechuga).get()
        self.assertEqual(list(nuevo.detalles.values_list("insumo_invernadero_id", flat=True)), [self.nutriente.pk])

    def test_ext_5b_un_proveedor_dado_de_baja_entre_la_lectura_y_el_bloqueo_no_se_invita(self):
        """Extensión 5b y 11a de CMP-RLZ-PED: el proveedor que se dio de baja no recibe invitación; el otro sí."""
        with self.antes_de_bloquear(lambda: type(self.sur).objects.filter(pk=self.sur.pk).update(estado_proveedor="inactivo")):
            self.correr()
        self.assertEqual(list(Pedido.objects.get().invitaciones.values_list("proveedor_id", flat=True)), [self.este.pk])
        self.assertEqual([m.to[0] for m in mail.outbox], ["info@este.com"])

    def test_ext_5b_si_se_dan_de_baja_todos_los_proveedores_no_se_crea_el_pedido(self):
        """Extensión 5b: sin ningún proveedor activo tras el bloqueo no se crea el pedido (la próxima corrida lo trata como 3a)."""
        with self.antes_de_bloquear(lambda: type(self.sur).objects.update(estado_proveedor="inactivo")):
            self.correr()
        self.assertEqual((Pedido.objects.count(), mail.outbox), (0, []))

    def test_ext_5b_un_invernadero_que_pasa_a_inactivo_no_crea_nada_ni_falla(self):
        """Extensión 5b y precondición a: el invernadero se dio de baja entre la lectura y el bloqueo → no se crea nada y el paso no falla (no es un error del paso)."""
        with self.antes_de_bloquear(lambda: type(self.norte).objects.filter(pk=self.norte.pk).update(estado_invernadero="inactivo")):
            resumen = self.correr()
        self.assertEqual((Pedido.objects.count(), resumen.creados), (0, 0))

    def test_ext_5b_si_cambia_el_agronomo_a_cargo_no_se_crea_a_nombre_del_anterior(self):
        """Extensión 5b: el invernadero cambió de Agrónomo entre la lectura y el bloqueo → no se crea a nombre del que se leyó; la próxima corrida lo trata con el nuevo."""
        nuevo = crear_agronomo(email="nuevo@infoponia.com")
        with self.antes_de_bloquear(lambda: type(self.norte).objects.filter(pk=self.norte.pk).update(agronomo=nuevo)):
            self.correr()
        self.assertEqual(Pedido.objects.count(), 0)
        self.correr()
        self.assertEqual(Pedido.objects.get().agronomo_id, nuevo.pk)

    def test_regla_un_invernadero_que_falla_no_impide_los_demas_y_el_paso_lo_informa(self):
        """Regla de CMP-AUT-PED y D-56 punto 5: si un invernadero falla se registra con ``logger.exception``, se revierte solo ese y los demás se tratan; al terminar el paso
        lanza ``RuntimeError`` para que ``proceso_diario`` lo informe como fallido (como los pasos 60 a 62)."""
        from compras.servicios import pedidos as modulo_de_pedidos

        beto, sur, tomate = self.segundo_invernadero()
        real = modulo_de_pedidos._crear_pedido
        llamadas = []

        def falla_la_primera(*args, **kwargs):
            llamadas.append(True)
            if len(llamadas) == 1:
                raise RuntimeError("falla de prueba")
            return real(*args, **kwargs)

        with mock.patch.object(modulo_de_pedidos, "_crear_pedido", side_effect=falla_la_primera):
            with self.assertLogs("infoponia.proceso_diario", level="ERROR"), self.assertRaises(RuntimeError):
                self.correr()
        self.assertFalse(DetallePedido.objects.filter(insumo_invernadero__invernadero=self.norte).exists())
        self.assertEqual(self.pedido_de(sur).agronomo_id, beto.pk)
        self.assertEqual(self.avisos(self.ana).count(), 0)


class PasoDiarioTests(AutomaticoBase):
    """Paso 3 de la tarea (D-104 punto 1 y D-56): el paso 63 registrado, listado y corrido con ``--solo`` y ``--fecha``."""

    def paso(self):
        return next(p for p in procesos_de_core.pasos_diarios() if p.codigo == CODIGO)

    def test_d104_el_paso_esta_registrado_como_63_con_su_nombre_y_su_funcion(self):
        """D-104 punto 1: ``generar_pedidos_automaticos``, orden 63, «Pedidos automáticos por stock bajo», con ``generar_pedidos_automaticos``."""
        paso = self.paso()
        self.assertEqual((paso.nombre, paso.orden), ("Pedidos automáticos por stock bajo", 63))
        self.assertIs(paso.funcion, automaticos.generar_pedidos_automaticos)

    def test_d104_corre_despues_de_los_pasos_60_a_62(self):
        """D-104 punto 1: el 63 va después de los pasos de CMP-03 (60, 61 y 62) y es el último de compras."""
        ordenes = [p.orden for p in procesos_de_core.pasos_diarios()]
        self.assertEqual([o for o in ordenes if o >= 60], [60, 61, 62, 63])

    def test_d104_proceso_diario_listar_muestra_el_paso(self):
        """D-56 punto 3: ``proceso_diario --listar`` muestra el paso con su nombre."""
        salida = StringIO()
        call_command("proceso_diario", "--listar", stdout=salida)
        self.assertIn(f"63 · {CODIGO} · Pedidos automáticos por stock bajo", salida.getvalue())

    def test_d104_proceso_diario_solo_con_fecha_corre_el_paso_con_esa_fecha(self):
        """D-56 puntos 3 y 4: ``--solo generar_pedidos_automaticos --fecha`` corre solo ese paso y simula el día (``hoy`` nunca se lee del reloj)."""
        otro_dia = self.hoy + timedelta(days=30)
        salida = StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command("proceso_diario", "--solo", CODIGO, "--fecha", otro_dia.isoformat(), stdout=salida)
        self.assertIn("Pedidos automáticos por stock bajo: procesados 1 · creados 1 · resueltos 0", salida.getvalue())
        self.assertIn("Pasos correctos: 1 · fallidos: 0.", salida.getvalue())
        pedido = Pedido.objects.get()
        self.assertEqual(pedido.fecha_pedido, otro_dia)
        self.assertEqual(pedido.fecha_limite_cotizaciones, otro_dia + timedelta(days=3))

    def test_d104_el_paso_63_no_crea_un_pedido_que_el_paso_60_cancela_el_mismo_dia(self):
        """D-104 punto 1: el 63 corre después de los pasos 60 a 62: un pedido vencido sin cotizaciones se cancela («nadie cotizó») y, como el insumo sigue bajo el mínimo,
        el 63 crea uno nuevo; no queda un pedido «en cotización» ya vencido."""
        vencido = armar_pedido(self.ana)
        detalle_de_pedido(vencido, self.lechuga)
        detalle_de_pedido(vencido, self.nutriente)
        Pedido.objects.filter(pk=vencido.pk).update(
            fecha_pedido=self.hoy - timedelta(days=7), fecha_limite_cotizaciones=self.hoy - timedelta(days=1)
        )
        with self.captureOnCommitCallbacks(execute=True):
            for paso in procesos_de_core.pasos_diarios():
                if paso.orden in (60, 61, 62, 63):
                    paso.funcion(self.hoy)
        vencido.refresh_from_db()
        self.assertEqual(vencido.estado_pedido, Pedido.Estado.CANCELADO)
        (nuevo,) = Pedido.objects.filter(estado_pedido=Pedido.Estado.EN_COTIZACION)
        self.assertGreater(nuevo.fecha_limite_cotizaciones, self.hoy)
