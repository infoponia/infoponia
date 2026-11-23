# Pruebas de CMP-RLZ-PED · Realizar Pedido (CMP-02a, paso 3): el servicio de `compras/servicios/pedidos.py`. Fuente: docs/casos_de_uso/compras/pedidos.md
# (CMP-RLZ-PED v0.2 con las «Actualizaciones de A0»), D-87, D-88 y D-89. El módulo se toma dentro de cada prueba (``perezoso``), así que mientras no
# existe falla cada prueba por separado. Los correos salen en ``on_commit``: las pruebas los ejecutan con ``captureOnCommitCallbacks``.
# Convenciones de los errores del servicio (``ValidationError`` por campo): ``detalles`` (sin_detalles), ``insumo_<iin>`` (insumo_no_pedible,
# detalle_repetido), ``cantidad_<iin>`` (cantidad_invalida, decimales_de_la_unidad), ``fecha_limite`` (fecha_limite_invalida),
# ``proveedores`` (sin_proveedores, proveedor_no_invitable) y, de las condiciones que cambian (11a), el error general.

import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from compras.models import DetallePedido, EnlaceProveedor, InvitacionPedido, Pedido
from compras.tests.fabricas import detalle_de_pedido, proveedor
from compras.tests.fabricas import pedido as armar_pedido
from core.models import RegistroAuditoria
from core.tests.fabricas import BACKEND_QUE_FALLA, construir_url, crear_administrador, crear_capataz, crear_gerente
from inventario.models import MovimientoInsumo
from inventario.tests.fabricas import ConDatosDeInventario, existencia, insumo, lote, perezoso, tipo_de_insumo
from maestros.servicios import configuracion
from maestros.tests.fabricas import codigos_de, crear_agronomo, crear_agronomo_con_invernadero, crear_invernadero, error_de

pedidos = perezoso("compras.servicios.pedidos")


def mañana(dias=1):
    """La fecha de hoy más ``dias`` días (en la zona del sistema)."""
    return timezone.localdate() + timedelta(days=dias)


class PedidoBase(ConDatosDeInventario, TestCase):
    """Un Agrónomo con un invernadero, dos insumos habilitados (lechuga por unidad y nutriente en kg) y dos proveedores activos."""

    def setUp(self):
        self.agronomo, self.invernadero = crear_agronomo_con_invernadero("Invernadero Norte")
        self.lechuga = existencia(insumo("Lechuga", unidad="unidad", descripcion="Plantín"), self.invernadero, minimo=20, precio="12.50")
        self.nutriente = existencia(insumo("Nutriente", unidad="kg"), self.invernadero, minimo=5, precio="100.00")
        self.sur = proveedor("Semillas del Sur S. A.", n=1, email="ventas@sur.com")
        self.este = proveedor("Viveros del Este S. R. L.", n=2, email="info@este.com")

    def datos(self, **cambios):
        """Los datos de un pedido válido: 20 lechugas y 3 kg de nutriente, a los dos proveedores, con la fecha límite pasado mañana."""
        datos = {
            "detalles": [(self.lechuga.pk, "20"), (self.nutriente.pk, "3")],
            "proveedores": [self.sur.pk, self.este.pk],
            "fecha_limite": mañana(2),
        }
        datos.update(cambios)
        return datos

    def registrar(self, actor=None, **cambios):
        """``registrar_pedido`` con los correos ejecutados; devuelve el pedido."""
        with self.captureOnCommitCallbacks(execute=True):
            return pedidos.registrar_pedido(actor or self.agronomo, self.datos(**cambios), construir_url)


class InsumosBajoElMinimoTests(PedidoBase):
    """Pasos 2 y 3 y regla «Insumo bajo el mínimo» / «Cantidad sugerida»."""

    def test_regla_bajo_el_minimo_es_libre_mas_transito_menor_que_el_minimo_con_su_sugerida(self):
        """Reglas «Insumo bajo el mínimo» y «Cantidad sugerida»: libre + tránsito < mínimo; sugerida = mínimo − (libre + tránsito)."""
        lote(self.lechuga, 12)
        self.lechuga.cant_transito_insumo = Decimal("3")
        self.lechuga.save()
        lote(self.nutriente, 8)  # sobre el mínimo (5)
        filas = pedidos.insumos_bajo_el_minimo(self.agronomo)
        self.assertEqual([f.iin.pk for f in filas], [self.lechuga.pk])
        self.assertEqual(filas[0].sugerida, Decimal("5"))
        self.assertEqual((filas[0].existencia.libre, filas[0].existencia.transito, filas[0].existencia.minimo), (12, 3, 20))

    def test_regla_el_stock_libre_no_cuenta_lotes_vencidos(self):
        """Regla «Insumo bajo el mínimo»: el stock libre no cuenta los lotes vencidos (mismo criterio que la alerta)."""
        lote(self.lechuga, 30, vence=timezone.localdate() - timedelta(days=1))
        self.assertEqual([f.iin.pk for f in pedidos.insumos_bajo_el_minimo(self.agronomo)], [self.lechuga.pk, self.nutriente.pk])

    def test_regla_insumo_pedible_solo_activo_habilitado_en_invernadero_activo_a_cargo(self):
        """Regla «Insumo pedible»: insumo activo, habilitado en un invernadero activo a cargo del Agrónomo; no los de otro Agrónomo ni los inactivos."""
        otro, ajeno = crear_agronomo_con_invernadero("Ajeno", email="otro@infoponia.com")
        existencia(insumo("Ajeno", unidad="kg"), ajeno, minimo=5)
        existencia(insumo("Deshabilitado", unidad="kg"), self.invernadero, minimo=5, activo=False)
        existencia(insumo("Del catálogo inactivo", unidad="kg", activo=False), self.invernadero, minimo=5)
        inactivo = crear_invernadero("Inactivo", activo=False, agronomo=self.agronomo)
        existencia(insumo("En inactivo", unidad="kg"), inactivo, minimo=5)
        nombres = {f.iin.insumo.nombre_insumo for f in pedidos.insumos_bajo_el_minimo(self.agronomo)}
        self.assertEqual(nombres, {"Lechuga", "Nutriente"})

    def test_regla_sin_minimo_no_esta_bajo_el_minimo(self):
        """Regla «Insumo bajo el mínimo»: con mínimo 0 nunca está bajo el mínimo."""
        existencia(insumo("Sin mínimo", unidad="kg"), self.invernadero, minimo=0)
        self.assertNotIn("Sin mínimo", [f.iin.insumo.nombre_insumo for f in pedidos.insumos_bajo_el_minimo(self.agronomo)])

    def test_ext_2a_sin_insumos_bajo_el_minimo_da_una_lista_vacia(self):
        """Extensión 2a: no hay insumos bajo el mínimo → lista vacía (la pantalla lo informa y sigue en 3a)."""
        lote(self.lechuga, 25)
        lote(self.nutriente, 6)
        self.assertEqual(pedidos.insumos_bajo_el_minimo(self.agronomo), [])

    def test_ext_4c_marca_el_insumo_que_ya_esta_en_otro_pedido_en_cotizacion(self):
        """Paso 2 y extensión 4c: la lista indica si el insumo ya figura en otro pedido «en cotización» (con su id y cantidad)."""
        previo = armar_pedido(self.agronomo)
        detalle_de_pedido(previo, self.lechuga, cantidad="7")
        por_iin = {f.iin.pk: f for f in pedidos.insumos_bajo_el_minimo(self.agronomo)}
        self.assertEqual(por_iin[self.lechuga.pk].ya_pedido.pedido_id, previo.pk)
        self.assertEqual(por_iin[self.lechuga.pk].ya_pedido.cantidad, Decimal("7"))
        self.assertIsNone(por_iin[self.nutriente.pk].ya_pedido)

    def test_ext_4c_un_pedido_cancelado_o_cerrado_no_cuenta_como_ya_pedido(self):
        """Extensión 4c: solo «en cotización» (lo de la orden pendiente de aprobación lo completa CMP-03, que crea la orden)."""
        cancelado = armar_pedido(self.agronomo, estado="cancelado", causa="nadie_cotizo")
        detalle_de_pedido(cancelado, self.lechuga)
        self.assertEqual(pedidos.ya_pedido([self.lechuga.pk]), {})

    def test_post_f_alerta_de_bajo_el_minimo_sigue_sin_resolver(self):
        """Extensión 1a y postcondición f: pedir desde la alerta de bajo el mínimo no la resuelve."""
        from maestros.models import Alerta

        lote(self.lechuga, 1)
        from inventario.servicios import alertas_de_stock

        alertas_de_stock.reevaluar_alertas_del_insumo(self.lechuga.pk)
        activas = Alerta.objects.activas().count()
        self.assertGreater(activas, 0)
        self.registrar(detalles=[(self.lechuga.pk, "19")])
        self.assertEqual(Alerta.objects.activas().count(), activas)

    def test_precondicion_a_solo_un_agronomo_activo(self):
        """Precondición a (SEG-13): el Gerente, otros roles y una cuenta inactiva no usan el caso de uso."""
        for actor in (crear_gerente(), crear_capataz(), crear_administrador(), crear_agronomo(email="baja@infoponia.com", activo=False)):
            with self.subTest(actor=actor):
                with self.assertRaises(PermissionDenied):
                    pedidos.insumos_bajo_el_minimo(actor)
                with self.assertRaises(PermissionDenied):
                    pedidos.resumir_pedido(actor, self.datos())
                with self.assertRaises(PermissionDenied):
                    pedidos.registrar_pedido(actor, self.datos(), construir_url)

    def test_ext_3a_el_catalogo_de_un_invernadero_a_cargo_ofrece_sus_insumos_habilitados_con_su_stock(self):
        """Extensión 3a: el Agrónomo elige uno de sus invernaderos y ve los insumos habilitados con stock libre, tránsito y mínimo."""
        lote(self.nutriente, 9)
        filas = pedidos.insumos_pedibles(self.agronomo, self.invernadero.pk)
        self.assertEqual({f.iin.insumo.nombre_insumo for f in filas}, {"Lechuga", "Nutriente"})
        self.assertEqual({f.iin.insumo.nombre_insumo: f.existencia.libre for f in filas}["Nutriente"], Decimal("9"))

    def test_ext_3a_el_catalogo_de_un_invernadero_ajeno_se_rechaza(self):
        """Regla «Solo el rol Agrónomo accede, únicamente sobre los invernaderos que tiene a cargo»."""
        _, ajeno = crear_agronomo_con_invernadero("Ajeno", email="otro@infoponia.com")
        with self.assertRaises(PermissionDenied):
            pedidos.insumos_pedibles(self.agronomo, ajeno.pk)


class FechaYProveedoresTests(PedidoBase):
    """Pasos 6 a 8: la fecha límite y los proveedores invitables."""

    def test_regla_fecha_limite_propuesta_es_hoy_mas_los_dias_de_la_configuracion(self):
        """Regla «Fecha límite de cotizaciones»: se propone hoy + ``dias_limite_cotizacion``, leído de la configuración en cada uso."""
        fila = configuracion.obtener()
        fila.dias_limite_cotizacion = 5
        fila.save(update_fields=["dias_limite_cotizacion"])
        self.assertEqual(pedidos.proponer_fecha_limite(), mañana(5))
        fila.dias_limite_cotizacion = 2
        fila.save(update_fields=["dias_limite_cotizacion"])
        self.assertEqual(pedidos.proponer_fecha_limite(), mañana(2))

    def test_ext_8a_la_fecha_limite_tiene_que_ser_desde_manana(self):
        """Extensión 8a: una fecha anterior al día siguiente se rechaza (``fecha_limite_invalida``); mañana se acepta."""
        for fecha in (timezone.localdate(), mañana(-3)):
            with self.subTest(fecha=fecha):
                error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(fecha_limite=fecha)))
                self.assertEqual(codigos_de(error, "fecha_limite"), ["fecha_limite_invalida"])
        self.assertEqual(pedidos.resumir_pedido(self.agronomo, self.datos(fecha_limite=mañana(1))).fecha_limite, mañana(1))

    def test_ext_8a_sin_fecha_limite_se_rechaza(self):
        """Extensión 8a: la fecha límite es obligatoria."""
        error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(fecha_limite=None)))
        self.assertEqual(codigos_de(error, "fecha_limite"), ["fecha_limite_invalida"])

    def test_regla_proveedores_invitables_son_los_activos_con_su_especialidad(self):
        """Regla «Proveedores invitables» (6a obsoleta: el correo es obligatorio): los activos; un inactivo no aparece."""
        proveedor("Inactivo", n=3, activo=False)
        self.assertEqual({p.pk for p in pedidos.proveedores_invitables()}, {self.sur.pk, self.este.pk})

    def test_ext_7a_el_filtro_por_especialidad_propuesto_usa_las_categorias_de_los_insumos_del_pedido(self):
        """Paso 6 y 7a con H13/MD-121: se propone filtrar por las categorías de los insumos del pedido; se filtra por los tipos de insumo en que se especializa el proveedor."""
        semillas = self.lechuga.insumo.tipo_insumo
        otra = tipo_de_insumo("Herramientas")
        especialista = proveedor("Especialista", n=3, especialidades=[semillas])
        proveedor("De otra cosa", n=4, especialidades=[otra])
        self.assertEqual(pedidos.categorias_del_pedido([self.lechuga.pk, self.nutriente.pk]), {semillas.pk, self.nutriente.insumo.tipo_insumo.pk})
        self.assertEqual({p.pk for p in pedidos.proveedores_invitables([semillas.pk])}, {especialista.pk})

    def test_ext_8b_sin_proveedores_se_rechaza(self):
        """Extensión 8b: hay que invitar al menos a un proveedor."""
        error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(proveedores=[])))
        self.assertEqual(codigos_de(error, "proveedores"), ["sin_proveedores"])

    def test_regla_un_proveedor_inactivo_o_inexistente_no_se_puede_invitar(self):
        """Regla «Proveedores invitables»: solo activos."""
        inactivo = proveedor("Inactivo", n=3, activo=False)
        for ids in ([inactivo.pk], [self.sur.pk, 999999]):
            with self.subTest(ids=ids):
                error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(proveedores=ids)))
                self.assertEqual(codigos_de(error, "proveedores"), ["proveedor_no_invitable"])


class ResumenDelPedidoTests(PedidoBase):
    """Pasos 4 y 9: las validaciones y el resumen, sin escribir nada."""

    def test_post_resumen_agrupa_por_invernadero_con_subtotales_y_monto_estimado(self):
        """Paso 9 y regla «Precio y monto estimado»: los detalles agrupados por invernadero con insumo, cantidad, unidad, precio de referencia y subtotal; el monto, su suma."""
        resumen = pedidos.resumir_pedido(self.agronomo, self.datos())
        self.assertEqual(resumen.monto, Decimal("550.00"))  # 20 × 12,50 + 3 × 100,00
        self.assertEqual(len(resumen.grupos), 1)
        invernadero, lineas = resumen.grupos[0]
        self.assertEqual(invernadero.pk, self.invernadero.pk)
        self.assertEqual([(l.iin.pk, l.cantidad, l.precio, l.subtotal) for l in lineas],
                         [(self.lechuga.pk, Decimal("20"), Decimal("12.50"), Decimal("250.00")),
                          (self.nutriente.pk, Decimal("3.000"), Decimal("100.00"), Decimal("300.00"))])
        self.assertEqual({p.pk for p in resumen.proveedores}, {self.sur.pk, self.este.pk})

    def test_post_el_resumen_no_escribe_nada(self):
        """Garantías mínimas: resumir no crea pedido, detalle, invitación, enlace, auditoría ni correo."""
        antes = (Pedido.objects.count(), DetallePedido.objects.count(), InvitacionPedido.objects.count(), RegistroAuditoria.objects.count())
        with self.captureOnCommitCallbacks(execute=True):
            pedidos.resumir_pedido(self.agronomo, self.datos())
        self.assertEqual(
            (Pedido.objects.count(), DetallePedido.objects.count(), InvitacionPedido.objects.count(), RegistroAuditoria.objects.count()), antes
        )
        self.assertEqual(EnlaceProveedor.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_ext_5a_un_pedido_sin_detalles_se_rechaza(self):
        """Extensión 5a: el pedido debe incluir al menos un insumo."""
        error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[])))
        self.assertEqual(codigos_de(error, "detalles"), ["sin_detalles"])

    def test_ext_4a_la_cantidad_tiene_que_ser_mayor_que_cero_y_con_los_decimales_de_la_unidad(self):
        """Extensión 4a, regla «Cantidad pedida» y regla 2 de 8.23: > 0 y con los decimales de la unidad (la lechuga es por unidad: entera)."""
        campo = f"cantidad_{self.lechuga.pk}"
        for valor, codigo in (("0", "cantidad_invalida"), ("-2", "cantidad_invalida"), ("", "cantidad_invalida"), ("abc", "cantidad_invalida"),
                              ("2.5", "decimales_de_la_unidad")):
            with self.subTest(valor=valor):
                error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(self.lechuga.pk, valor)])))
                self.assertEqual(codigos_de(error, campo), [codigo])
        pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(self.nutriente.pk, "2.5")]))  # el kg admite decimales

    def test_ext_4b_el_mismo_par_insumo_invernadero_no_se_repite(self):
        """Extensión 4b y regla «Detalle único»: un pedido no repite el par insumo–invernadero."""
        error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(self.lechuga.pk, "5"), (self.lechuga.pk, "6")])))
        self.assertEqual(codigos_de(error, f"insumo_{self.lechuga.pk}"), ["detalle_repetido"])

    def test_regla_el_mismo_insumo_puede_ir_a_invernaderos_distintos(self):
        """Regla «Detalle único»: el mismo insumo puede aparecer más de una vez si va a invernaderos distintos."""
        segundo = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        en_sur = existencia(self.lechuga.insumo, segundo, minimo=10, precio="11.00")
        resumen = pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(self.lechuga.pk, "5"), (en_sur.pk, "6")]))
        self.assertEqual(len(resumen.grupos), 2)

    def test_regla_insumo_no_pedible_se_rechaza(self):
        """Regla «Insumo pedible»: deshabilitado, de un insumo inactivo, de un invernadero inactivo o inexistente."""
        deshabilitado = existencia(insumo("Deshabilitado", unidad="kg"), self.invernadero, minimo=5, activo=False)
        de_baja = existencia(insumo("De baja", unidad="kg", activo=False), self.invernadero, minimo=5)
        for iin_id in (deshabilitado.pk, de_baja.pk, 999999):
            with self.subTest(iin=iin_id):
                error = error_de(lambda: pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(iin_id, "1")])))
                self.assertEqual(codigos_de(error, f"insumo_{iin_id}"), ["insumo_no_pedible"])

    def test_regla_un_insumo_de_un_invernadero_ajeno_se_rechaza(self):
        """Regla «Solo el rol Agrónomo accede... únicamente sobre los invernaderos que tiene a cargo»."""
        _, ajeno = crear_agronomo_con_invernadero("Ajeno", email="otro@infoponia.com")
        de_otro = existencia(insumo("Ajeno", unidad="kg"), ajeno, minimo=5)
        with self.assertRaises(PermissionDenied):
            pedidos.resumir_pedido(self.agronomo, self.datos(detalles=[(de_otro.pk, "1")]))

    def test_ext_4c_el_resumen_advierte_del_insumo_ya_pedido_y_deja_continuar(self):
        """Extensión 4c y regla «Insumo ya pedido»: advierte (id del otro pedido, su cantidad y su fecha límite) y no impide registrar."""
        previo = armar_pedido(self.agronomo)
        detalle_de_pedido(previo, self.lechuga, cantidad="7")
        resumen = pedidos.resumir_pedido(self.agronomo, self.datos())
        linea = next(l for g in resumen.grupos for l in g[1] if l.iin.pk == self.lechuga.pk)
        self.assertEqual((linea.ya_pedido.pedido_id, linea.ya_pedido.cantidad), (previo.pk, Decimal("7")))
        self.assertEqual(self.registrar().invitaciones.count(), 2)  # deja continuar


class RegistroDelPedidoTests(PedidoBase):
    """Pasos 10 a 13: registrar el pedido con sus detalles, invitaciones, enlaces, auditoría y correos."""

    def setUp(self):
        super().setUp()
        self.config = override_settings(CORREO_CONFIGURADO=True)
        self.config.enable()
        self.addCleanup(self.config.disable)

    def test_post_a_el_pedido_nace_en_cotizacion_con_sus_fechas_y_su_agronomo(self):
        """Postcondición a: «en cotización», fecha de pedido = hoy, fecha límite indicada, sin cierre, del Agrónomo que lo realizó."""
        pedido = self.registrar()
        self.assertEqual(pedido.estado_pedido, "en_cotizacion")
        self.assertEqual((pedido.fecha_pedido, pedido.fecha_limite_cotizaciones), (timezone.localdate(), mañana(2)))
        self.assertIsNone(pedido.fecha_cierre_pedido)
        self.assertEqual(pedido.agronomo_id, self.agronomo.pk)
        self.assertEqual(Pedido.objects.con_monto().get(pk=pedido.pk).monto_estimado, Decimal("550.00"))

    def test_post_b_un_detalle_por_par_con_el_precio_de_referencia_copiado_ahora(self):
        """Postcondición b y regla «Precio y monto estimado»: el precio es una copia del de referencia al registrar; cambiarlo después no cambia el detalle."""
        pedido = self.registrar()
        self.lechuga.referencia_precio = Decimal("99.00")
        self.lechuga.save()
        detalles = {d.insumo_invernadero_id: d for d in pedido.detalles.all()}
        self.assertEqual(detalles[self.lechuga.pk].precio_unitario_de_pedido, Decimal("12.50"))
        self.assertEqual(detalles[self.nutriente.pk].cantidad_detalle, Decimal("3.000"))
        self.assertEqual(len(detalles), 2)

    def test_post_c_y_d_una_invitacion_y_un_enlace_vigente_por_proveedor_sin_guardar_el_token(self):
        """Postcondiciones c y d y D-88 punto 1: una invitación y un enlace vigente por proveedor; la base guarda solo el resumen del token."""
        pedido = self.registrar()
        self.assertEqual({i.proveedor_id for i in pedido.invitaciones.all()}, {self.sur.pk, self.este.pk})
        enlaces = list(EnlaceProveedor.objects.filter(invitacion__pedido=pedido))
        self.assertEqual({e.estado for e in enlaces}, {"vigente"})
        tokens = set(re.findall(r"/proveedor/([\w-]+)/", " ".join(m.body for m in mail.outbox)))
        self.assertEqual(len(tokens), 2)
        for token in tokens:
            for enlace in enlaces:
                self.assertNotIn(token, " ".join(str(v) for v in EnlaceProveedor.objects.filter(pk=enlace.pk).values().get().values()))
            self.assertFalse(RegistroAuditoria.objects.filter(detalle__icontains=token).exists())

    def test_post_e_cada_proveedor_recibe_su_correo_con_su_enlace_el_detalle_y_la_fecha_limite(self):
        """Postcondición e y 12a: un correo por proveedor, con su enlace, por cada detalle el insumo (nombre, descripción, unidad), la cantidad y el invernadero con su dirección, y la fecha límite."""
        self.registrar()
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["info@este.com", "ventas@sur.com"])
        cuerpo = next(m.body for m in mail.outbox if m.to == ["ventas@sur.com"])
        for texto in ("https://infoponia.test/proveedor/", "Lechuga", "Plantín", "20", "Nutriente", "Invernadero Norte", "Calle 122 3310",
                      mañana(2).strftime("%d/%m/%Y")):
            self.assertIn(texto, cuerpo)
        tokens = [re.search(r"/proveedor/([\w-]+)/", m.body).group(1) for m in mail.outbox]
        self.assertEqual(len(set(tokens)), 2)

    def test_garantia_ningun_proveedor_recibe_el_precio_de_referencia_ni_el_monto(self):
        """Garantías mínimas y 12a: el correo no incluye el precio de referencia ni el monto estimado."""
        self.registrar()
        for correo in mail.outbox:
            for prohibido in ("12,50", "12.50", "100,00", "100.00", "550", "Precio", "precio", "Monto", "monto"):
                self.assertNotIn(prohibido, correo.body)

    def test_post_g_un_registro_de_auditoria_con_el_pedido_los_detalles_y_las_invitaciones(self):
        """Postcondición g y D-36: una sola acción ``alta_pedido`` del Agrónomo, con el pedido, cada detalle y cada invitación como afectados."""
        pedido = self.registrar()
        registro = RegistroAuditoria.objects.get(accion="alta_pedido")
        self.assertEqual((registro.usuario_id, registro.rol), (self.agronomo.pk, "agronomo"))
        modelos = [a["modelo"] for a in registro.afectados]
        self.assertEqual(modelos.count("compras.pedido"), 1)
        self.assertEqual(modelos.count("compras.detallepedido"), 2)
        self.assertEqual(modelos.count("compras.invitacionpedido"), 2)
        self.assertEqual(registro.detalle["cambios"]["fecha_limite_cotizaciones"], {"antes": None, "despues": mañana(2).isoformat()})
        self.assertEqual(registro.detalle["cambios"]["monto_estimado"], {"antes": None, "despues": "550.00"})
        self.assertEqual(registro.detalle["cambios"]["estado"]["despues"], "en_cotizacion")
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_pedido").count(), 1)
        self.assertEqual(str(pedido), next(a["texto"] for a in registro.afectados if a["modelo"] == "compras.pedido"))

    def test_garantia_el_pedido_no_modifica_stock_transito_minimo_ni_reservas(self):
        """Garantías mínimas y regla «Efectos sobre el inventario»: ni lotes, ni movimientos, ni tránsito, ni mínimo cambian."""
        lote(self.lechuga, 12)
        movimientos = MovimientoInsumo.objects.count()
        antes = [(e.cant_min_insumo, e.cant_transito_insumo, e.referencia_precio) for e in (self.lechuga, self.nutriente)]
        self.registrar()
        self.lechuga.refresh_from_db()
        self.nutriente.refresh_from_db()
        self.assertEqual([(e.cant_min_insumo, e.cant_transito_insumo, e.referencia_precio) for e in (self.lechuga, self.nutriente)], antes)
        self.assertEqual(MovimientoInsumo.objects.count(), movimientos)

    def test_ext_b_si_falla_el_registro_no_queda_nada_ni_sale_ningun_correo(self):
        """Garantías mínimas y extensión *b: el registro es atómico; si la auditoría falla se revierte todo y los correos (``on_commit``) no salen."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.captureOnCommitCallbacks(execute=True) as pendientes:
                with self.assertRaises(RuntimeError):
                    pedidos.registrar_pedido(self.agronomo, self.datos(), construir_url)
        self.assertEqual(pendientes, [])
        self.assertEqual((Pedido.objects.count(), DetallePedido.objects.count(), InvitacionPedido.objects.count(), EnlaceProveedor.objects.count()), (0, 0, 0, 0))
        self.assertEqual(mail.outbox, [])

    def test_ext_11a_un_insumo_que_dejo_de_estar_habilitado_no_registra_nada(self):
        """Extensión 11a: entre el resumen y la confirmación un insumo se deshabilitó; no se registra nada y se informa qué cambió."""
        pedidos.resumir_pedido(self.agronomo, self.datos())
        self.nutriente.estado_insumo_invernadero = "inactivo"
        self.nutriente.save()
        error = error_de(lambda: pedidos.registrar_pedido(self.agronomo, self.datos(), construir_url))
        self.assertEqual(codigos_de(error, f"insumo_{self.nutriente.pk}"), ["insumo_no_pedible"])
        self.assertEqual((Pedido.objects.count(), RegistroAuditoria.objects.filter(accion="alta_pedido").count()), (0, 0))

    def test_ext_11a_un_invernadero_que_dejo_de_estar_activo_no_registra_nada(self):
        """Extensión 11a: el invernadero de destino pasó a inactivo (``bloquear_invernadero_activo`` lo rechaza)."""
        self.invernadero.estado_invernadero = "inactivo"
        self.invernadero.save()
        error = error_de(lambda: pedidos.registrar_pedido(self.agronomo, self.datos(), construir_url))
        self.assertIn("invernadero_inactivo", codigos_de(error, NON_FIELD_ERRORS))
        self.assertEqual(Pedido.objects.count(), 0)

    def test_ext_11a_un_invernadero_que_ya_no_esta_a_cargo_no_registra_nada(self):
        """Extensión 11a: el invernadero dejó de estar a cargo del Agrónomo."""
        otro = crear_agronomo(email="nuevo@infoponia.com")
        self.invernadero.agronomo = otro
        self.invernadero.save()
        with self.assertRaises(PermissionDenied):
            pedidos.registrar_pedido(self.agronomo, self.datos(), construir_url)
        self.assertEqual(Pedido.objects.count(), 0)

    def test_ext_11a_un_proveedor_que_paso_a_inactivo_no_registra_nada(self):
        """Extensión 11a: un proveedor invitado pasó a inactivo."""
        self.sur.estado_proveedor = "inactivo"
        self.sur.save()
        error = error_de(lambda: pedidos.registrar_pedido(self.agronomo, self.datos(), construir_url))
        self.assertEqual(codigos_de(error, "proveedores"), ["proveedor_no_invitable"])
        self.assertEqual((Pedido.objects.count(), mail.outbox), (0, []))

    def test_ext_12a_si_un_correo_falla_el_pedido_y_la_invitacion_quedan_y_el_enlace_queda_pendiente(self):
        """Extensión 12a y D-88 punto 6: el pedido y la invitación permanecen; el enlace queda ``pendiente_envio`` (sin reintento automático; el reintento es «Reenviar invitación», CMP-02b)."""
        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            pedido = self.registrar()
        self.assertEqual(pedido.invitaciones.count(), 2)
        self.assertEqual({e.estado_envio for e in EnlaceProveedor.objects.filter(invitacion__pedido=pedido)}, {"pendiente_envio"})
        self.assertEqual({e.estado for e in EnlaceProveedor.objects.filter(invitacion__pedido=pedido)}, {"vigente"})

    def test_ext_12a_un_envio_correcto_deja_el_enlace_enviado(self):
        """D-88 punto 6: ``enviado`` cuando el correo sale."""
        pedido = self.registrar()
        self.assertEqual({e.estado_envio for e in EnlaceProveedor.objects.filter(invitacion__pedido=pedido)}, {"enviado"})

    def test_ext_12a_solo_falla_el_de_un_proveedor_y_el_otro_sale(self):
        """Extensión 12a: se marca cuál falló; los demás correos salen igual."""
        original = mail.send_mail
        enviados = []

        def a_medias(asunto, cuerpo, remitente, destinatarios, **kwargs):
            if destinatarios == ["info@este.com"]:
                raise OSError("falla")
            enviados.append(destinatarios)
            return original(asunto, cuerpo, remitente, destinatarios, **kwargs)

        with mock.patch("core.correo.send_mail", a_medias):
            pedido = self.registrar()
        estados = {e.invitacion.proveedor_id: e.estado_envio for e in EnlaceProveedor.objects.filter(invitacion__pedido=pedido)}
        self.assertEqual(estados, {self.sur.pk: "enviado", self.este.pk: "pendiente_envio"})
        self.assertEqual(enviados, [["ventas@sur.com"]])

    def test_d87_punto_3_no_se_notifica_en_la_campana_a_quien_hizo_la_accion(self):
        """H21 (D-87 punto 3): nunca se notifica a quien hizo la acción; el aviso del correo que falla va en la pantalla del paso 13, no en la campana."""
        from core.models import Notificacion

        with override_settings(EMAIL_BACKEND=BACKEND_QUE_FALLA):
            self.registrar()
        self.assertEqual(Notificacion.objects.count(), 0)

    def test_post_a_el_pedido_de_dos_invernaderos_agrupa_los_detalles(self):
        """Postcondición b y paso 9: un pedido puede ser para varios invernaderos del Agrónomo."""
        segundo = crear_invernadero("Invernadero Sur", agronomo=self.agronomo)
        en_sur = existencia(self.lechuga.insumo, segundo, minimo=10, precio="11.00")
        pedido = self.registrar(detalles=[(self.lechuga.pk, "5"), (en_sur.pk, "6")])
        self.assertEqual({d.insumo_invernadero.invernadero_id for d in pedido.detalles.all()}, {self.invernadero.pk, segundo.pk})
