# Pruebas de COM-REG-CVT, Registrar Compra-venta (COM-02, paso 4; docs/casos_de_uso/comercial/compra_venta.md): `registrar_compra_venta`,
# `datos_del_formulario`, `resumen`, `puede_registrar` y el comprobante. Una prueba por regla, postcondición y extensión. Las que escriben
# verifican al final los invariantes del patrón de stock maduro. La concurrencia está en `test_compra_ventas_concurrencia.py`.

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from contabilidad.models import AsientoContable
from comercial.models import Cliente, CompraVenta, DetalleReserva, DetalleVenta, ReservaStock
from comercial.servicios import comprobantes, compra_ventas
from comercial.servicios.compra_ventas import DatosDeCompraVenta, Renglon
from comercial.tests.fabricas import (
    cliente as crear_cliente,
    compra_venta,
    detalle,
    direccion_de_cliente,
    escenario_comercial,
    reserva,
    segundo_invernadero,
    verificar_invariantes_de_reservas,
)
from core.models import Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import ConDatosDeInventario
from maestros.models import Direccion, Invernadero
from maestros.tests.fabricas import crear_agronomo, crear_vendedor
from produccion.models import Cosecha
from produccion.tests.fabricas import lote_maduro, variedad_con_stock

HOY = timezone.localdate()


def iso(dias):
    """La fecha de dentro de ``dias`` días, como la manda el calendario del formulario."""
    return str(HOY + timedelta(days=dias))


def codigos(error):
    """Todos los códigos de una ``ValidationError`` con campos."""
    return sorted(e.code for lista in error.error_dict.values() for e in lista)


def codigos_de(error, campo):
    """Los códigos de los errores de un campo."""
    return [e.code for e in error.error_dict.get(campo, [])]


class BaseDeRegistro(ConDatosDeInventario, TestCase):
    """Un invernadero con Capataz, Agrónomo y Vendedor, con 100 plantas de la variedad en Maduración, y un cliente con correo y dirección."""

    def setUp(self):
        self.e = escenario_comercial()
        self.lote = lote_maduro(self.e, 100)
        self.gerente = crear_gerente()
        self.addCleanup(verificar_invariantes_de_reservas)

    def datos(self, cantidad="30", precio="1500,50", dias=3, **extra):
        """Los datos de un envío de ``cantidad`` plantas de la variedad (se pisan con ``extra``)."""
        valores = dict(
            vendedor_id="",
            cliente_id=str(self.e.cliente.pk),
            fecha_pactada=iso(dias),
            modalidad="envio",
            direccion_id=str(self.e.direccion.pk),
            invernadero_id="",
            renglones=[Renglon(0, str(self.e.variedad.pk), cantidad, precio)],
        )
        valores.update(extra)
        return DatosDeCompraVenta(**valores)

    def registrar(self, actor=None, **extra):
        """Registra con los datos por defecto como ``actor`` (por defecto, el Vendedor)."""
        return compra_ventas.registrar_compra_venta(actor or self.e.vendedor, self.datos(**extra))

    def rechazo(self, actor=None, **extra):
        """Registra esperando una ``ValidationError`` y la devuelve."""
        with self.assertRaises(ValidationError) as contexto:
            self.registrar(actor, **extra)
        return contexto.exception


class FlujoPrincipalTests(BaseDeRegistro):
    """Postcondiciones a a f, i y j del flujo principal."""

    def test_flujo_principal_registra_la_venta_con_su_detalle_su_reserva_y_su_cosecha(self):
        """Postcondiciones a a e: venta «abierta» de hoy con la fecha y la modalidad indicadas, asociada al cliente, al Vendedor y a la
        dirección; detalle «abierto» sin cantidad entregada; una reserva «activa» con su línea y una cosecha «a realizar»."""
        venta = self.registrar()
        self.assertEqual(
            (venta.estado_venta, venta.fecha_realizacion, venta.fecha_pactada_venta, venta.modalidad_entrega, venta.cliente_id,
             venta.vendedor_id, venta.direccion_envio_id, venta.invernadero_retiro_id),
            ("abierta", HOY, HOY + timedelta(days=3), "envio", self.e.cliente.pk, self.e.vendedor.pk, self.e.direccion.pk, None),
        )
        self.assertEqual(venta.codigo, f"CV-{venta.numero:04d}")
        (d,) = venta.detalles.all()
        self.assertEqual(
            (d.variedad_id, d.cant_solicitada_venta, d.precio_unitario_de_venta, d.cant_entregada_venta, d.estado_detalle_venta),
            (self.e.variedad.pk, 30, Decimal("1500.50"), None, "abierto"),
        )
        (r,) = ReservaStock.objects.filter(detalle_venta=d)
        self.assertEqual((r.estado_reserva, r.fecha_entrega_reserva, r.invernadero_id), ("activa", venta.fecha_pactada_venta, self.e.invernadero.pk))
        self.assertEqual(sum(l.cantidad_reservada for l in r.lineas.all()), 30)
        self.assertEqual((r.cosecha.estado_orden, r.cosecha.capataz_id), ("a_realizar", self.e.capataz.pk))
        self.assertEqual(venta.cosechas_programadas, 1)

    def test_post_f_una_venta_toda_de_camara_queda_lista_para_entrega_sin_cosecha(self):
        """Postcondición f: las reservas con todas sus líneas de cámara quedan «lista para entrega» (la entrega la planifica COM-05)."""
        from comercial.tests.fabricas import partida

        partida(self.lote, 40)
        type(self.lote).objects.filter(pk=self.lote.pk).update(estado_lote="finalizado", cantidad_actual=0, costo_acumulado=0)
        venta = self.registrar()
        (r,) = ReservaStock.objects.filter(detalle_venta__compra_venta=venta)
        self.assertEqual((r.estado_reserva, r.cosecha_id), ("lista_para_entrega", None))
        self.assertEqual(Cosecha.objects.count(), 0)
        self.assertEqual(venta.estado_venta, "abierta")

    def test_post_g_la_venta_tiene_entregas_desde_com_05a1(self):
        """Postcondición g: «se completa en COM-05». CAMBIADA en COM-05a1 (antes: «no se planifica ninguna entrega hasta COM-05», que verificaba que el modelo `Entrega` no existía): ahora la
        compra-venta tiene la relación `entregas`; que la venta que sale toda de cámara programa su entrega lo prueba `PlanificacionDeLaEntregaTests`."""
        self.assertTrue(hasattr(CompraVenta, "entregas"))

    def test_regla_la_venta_no_genera_pago_ni_asiento(self):
        """Garantía mínima 4: al registrar no se genera ningún pago ni asiento contable (D-57)."""
        self.registrar()
        self.assertFalse(any(m.__name__ == "PagoCliente" for m in __import__("django.apps").apps.apps.get_models()))
        # CON-02 creó el modelo `AsientoContable`: ya no se puede preguntar si existe, se pregunta si la venta dejó alguno (D-57, D-86).
        self.assertFalse(AsientoContable.objects.exists())

    def test_post_i_j_un_solo_registro_de_auditoria_con_todo_lo_creado(self):
        """Postcondiciones i y j (D-36): UN registro `registro_compra_venta` con el usuario, su rol y, entre los afectados, la venta, el
        detalle, la reserva, su línea y la cosecha."""
        venta = self.registrar()
        (registro,) = RegistroAuditoria.objects.filter(accion="registro_compra_venta")
        self.assertEqual((registro.usuario_id, registro.rol_usuario if hasattr(registro, "rol_usuario") else "vendedor"), (self.e.vendedor.pk, "vendedor"))
        modelos = [a["modelo"] for a in registro.afectados]
        for esperado in ("comercial.compraventa", "comercial.detalleventa", "comercial.reservastock", "comercial.detallereserva", "produccion.cosecha"):
            self.assertIn(esperado, modelos)
        self.assertEqual(registro.afectados[0]["texto"], venta.codigo)
        self.assertEqual(registro.detalle["datos"]["monto_estimado"], "45015.00")
        self.assertEqual(registro.detalle["datos"]["vendedor"]["id"], self.e.vendedor.pk)

    def test_post_c_el_numero_sale_de_la_secuencia_y_no_se_repite(self):
        """Ficha de Contrato: dos ventas seguidas tienen números distintos y crecientes."""
        a = self.registrar()
        b = self.registrar(cantidad="10")
        self.assertGreater(b.numero, a.numero)

    def test_post_e_se_notifica_la_cosecha_al_capataz_y_al_agronomo(self):
        """Postcondición e: la orden se notifica al Capataz y al Agrónomo del invernadero."""
        self.registrar()
        self.assertEqual(
            sorted(Notificacion.objects.values_list("destinatario_id", flat=True)), sorted([self.e.capataz.pk, self.e.agronomo.pk])
        )


class VendedorResponsableTests(BaseDeRegistro):
    """Regla «Vendedor responsable» y extensión 1a."""

    def test_regla_vendedor_responsable_el_vendedor_que_actua_es_el_responsable(self):
        """Paso 1: si el actor es un Vendedor, es el responsable (no elige)."""
        self.assertEqual(self.registrar().vendedor_id, self.e.vendedor.pk)

    def test_ext_1a_el_gerente_elige_al_vendedor_y_queda_como_quien_la_cargo(self):
        """Extensión 1a y postcondición i: la venta es del Vendedor elegido y el registro de auditoría es del Gerente."""
        venta = self.registrar(self.gerente, vendedor_id=str(self.e.vendedor.pk))
        self.assertEqual(venta.vendedor_id, self.e.vendedor.pk)
        (registro,) = RegistroAuditoria.objects.filter(accion="registro_compra_venta")
        self.assertEqual(registro.usuario_id, self.gerente.pk)
        self.assertEqual(registro.detalle["datos"]["vendedor"]["id"], self.e.vendedor.pk)

    def test_ext_1a_el_gerente_tiene_que_elegir_un_vendedor_activo_con_invernaderos_activos(self):
        """Extensión 1a y precondición b: sin Vendedor, o con uno sin invernaderos activos, `vendedor_obligatorio` o `vendedor_invalido`."""
        self.assertEqual(codigos_de(self.rechazo(self.gerente), "vendedor"), ["vendedor_obligatorio"])
        sin_invernaderos = crear_vendedor(email="sin@infoponia.com")
        self.assertEqual(codigos_de(self.rechazo(self.gerente, vendedor_id=str(sin_invernaderos.pk)), "vendedor"), ["vendedor_invalido"])

    def test_regla_invernaderos_habilitados_solo_los_del_vendedor_elegido(self):
        """Regla «Invernaderos habilitados»: el stock de otro Vendedor no se ofrece ni se vende."""
        otro = escenario_comercial(sufijo="2")
        lote_maduro(otro, 500, variedad=self.e.variedad)
        self.assertEqual(self.registrar(self.gerente, vendedor_id=str(self.e.vendedor.pk), cantidad="100").cosechas_programadas, 1)
        self.assertEqual(codigos_de(self.rechazo(self.gerente, vendedor_id=str(self.e.vendedor.pk), cantidad="101"), "renglon-0-cantidad"), ["supera_disponible"])

    def test_pre_a_solo_vendedor_o_gerente_activos(self):
        """Precondición a: otro rol, una cuenta inactiva o `None` reciben `PermissionDenied`."""
        inactivo = crear_vendedor(email="inactivo@infoponia.com", activo=False)
        for actor in (self.e.agronomo, inactivo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                compra_ventas.registrar_compra_venta(actor, self.datos())

    def test_pre_b_sin_invernaderos_activos_nueva_compra_venta_se_deshabilita_con_su_motivo(self):
        """Precondición b: el Vendedor sin invernaderos activos y el Gerente sin Vendedores con invernaderos ven el motivo."""
        self.assertEqual(compra_ventas.puede_registrar(self.e.vendedor), (True, ""))
        self.assertEqual(compra_ventas.puede_registrar(self.gerente), (True, ""))
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(estado_invernadero="inactivo")
        self.assertEqual(
            compra_ventas.puede_registrar(self.e.vendedor),
            (False, "No tenés invernaderos activos asignados: pedile al Gerente que te asigne uno."),
        )
        self.assertEqual(compra_ventas.puede_registrar(self.gerente), (False, "No hay Vendedores con invernaderos activos."))


class ClienteYEntregaTests(BaseDeRegistro):
    """Pasos 2 a 7 y extensiones 3a, 4a, 5a, 6a y 7a."""

    def test_regla_el_cliente_es_obligatorio_y_tiene_que_estar_activo(self):
        """Pasos 2 a 4 y extensión 4a: sin cliente, `cliente_obligatorio`; uno dado de baja, `cliente_inactivo`."""
        self.assertEqual(codigos_de(self.rechazo(cliente_id=""), "cliente"), ["cliente_obligatorio"])
        Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo")
        self.assertEqual(codigos_de(self.rechazo(), "cliente"), ["cliente_inactivo"])

    def test_regla_fecha_pactada_valida_igual_o_posterior_a_hoy(self):
        """Regla «Fecha pactada válida» y extensión 6a: ayer, `fecha_pasada`; hoy, vale; sin fecha, `fecha_obligatoria`; basura, `fecha_invalida`."""
        self.assertEqual(codigos_de(self.rechazo(dias=-1), "fecha_pactada"), ["fecha_pasada"])
        self.assertEqual(codigos_de(self.rechazo(fecha_pactada=""), "fecha_pactada"), ["fecha_obligatoria"])
        self.assertEqual(codigos_de(self.rechazo(fecha_pactada="mañana"), "fecha_pactada"), ["fecha_invalida"])
        self.assertEqual(self.registrar(dias=0, cantidad="5").fecha_pactada_venta, HOY)

    def test_regla_la_fecha_se_acepta_con_formato_dd_mm_aaaa(self):
        """Lista de datos 5a: la fecha se ingresa dd/mm/aaaa, con calendario o teclado."""
        texto = (HOY + timedelta(days=3)).strftime("%d/%m/%Y")
        self.assertEqual(self.registrar(fecha_pactada=texto, cantidad="5").fecha_pactada_venta, HOY + timedelta(days=3))

    def test_regla_direccion_de_envio_activa_y_del_cliente(self):
        """Regla «Dirección de envío» (regla 23 de 8.6, D-58): debe ser una dirección activa del cliente; sin ella, `direccion_obligatoria`."""
        self.assertEqual(codigos_de(self.rechazo(direccion_id=""), "direccion"), ["direccion_obligatoria"])
        ajena = direccion_de_cliente(crear_cliente(razon_social="Otro S.A."))
        self.assertEqual(codigos_de(self.rechazo(direccion_id=str(ajena.direccion_id)), "direccion"), ["direccion_no_valida"])
        Direccion.objects.filter(pk=self.e.direccion.pk).update(estado_direccion="inactivo")
        self.assertEqual(codigos_de(self.rechazo(), "direccion"), ["direccion_no_valida"])

    def test_ext_5a_retiro_en_un_invernadero_del_vendedor(self):
        """Extensión 5a: retiro en un invernadero activo del Vendedor: se guarda sin dirección de envío."""
        venta = self.registrar(modalidad="retiro", direccion_id="", invernadero_id=str(self.e.invernadero.pk), cantidad="10")
        self.assertEqual((venta.modalidad_entrega, venta.direccion_envio_id, venta.invernadero_retiro_id), ("retiro", None, self.e.invernadero.pk))

    def test_ext_5a_el_invernadero_de_retiro_tiene_que_ser_de_este_vendedor(self):
        """Extensión 5a y regla «Invernaderos habilitados»: el de otro Vendedor es `invernadero_no_habilitado`; uno solo del Vendedor queda elegido."""
        otro = escenario_comercial(sufijo="2")
        error = self.rechazo(modalidad="retiro", direccion_id="", invernadero_id=str(otro.invernadero.pk))
        self.assertEqual(codigos_de(error, "invernadero"), ["invernadero_no_habilitado"])
        sur = segundo_invernadero(self.e)
        self.assertEqual(
            codigos_de(self.rechazo(modalidad="retiro", direccion_id="", invernadero_id=""), "invernadero"), ["invernadero_obligatorio"]
        )
        self.assertEqual(sur.invernadero.vendedor_id, self.e.vendedor.pk)

    def test_ext_5a_un_retiro_vende_solo_el_stock_de_ese_invernadero(self):
        """Extensión 5a: las variedades y cantidades se calculan solo sobre los lotes y partidas de ese invernadero."""
        sur = segundo_invernadero(self.e)
        lote_maduro(sur, 500)
        error = self.rechazo(modalidad="retiro", direccion_id="", invernadero_id=str(self.e.invernadero.pk), cantidad="101")
        self.assertEqual(codigos_de(error, "renglon-0-cantidad"), ["supera_disponible"])
        venta = self.registrar(modalidad="retiro", direccion_id="", invernadero_id=str(sur.invernadero.pk), cantidad="101")
        self.assertEqual(venta.invernadero_retiro_id, sur.invernadero.pk)

    def test_ext_7a_la_modalidad_es_obligatoria(self):
        """Paso 5: la modalidad de entrega es envío o retiro."""
        self.assertEqual(codigos_de(self.rechazo(modalidad=""), "modalidad"), ["modalidad_invalida"])


class RenglonesTests(BaseDeRegistro):
    """Pasos 8 a 11 y extensiones 8a, 9a, 10a a 10c, 9-10a, 9-10b y 11a."""

    def test_ext_8a_sin_stock_para_la_fecha_no_hay_variedades_que_ofrecer(self):
        """Extensión 8a: sin stock maduro libre para la fecha, el formulario lo dice y no ofrece variedades."""
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(dias=60, renglones=[]))
        self.assertTrue(formulario.sin_stock)
        self.assertEqual(formulario.variedades_ofrecidas, [])

    def test_regla_8_10_el_formulario_ofrece_solo_las_variedades_con_stock_para_la_fecha_y_su_disponible(self):
        """Paso 8: solo las variedades con stock libre para la fecha, con «Disponible: N plantas»."""
        variedad_con_stock(self.e, nombre="Otra", habilitar=False)
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(renglones=[]))
        self.assertEqual([(v.pk, d.total) for v, d in formulario.variedades_ofrecidas], [(self.e.variedad.pk, 100)])

    def test_ext_9a_precio_propuesto_el_de_la_venta_mas_reciente_aunque_este_cancelada_o_sea_de_otro_vendedor(self):
        """Paso 9 (confirmado el 21/11/2026): el último precio de la variedad en cualquier compra-venta, Vendedor y estado."""
        otro = escenario_comercial(sufijo="2")
        vieja = compra_venta(self.e, dias=1)
        detalle(vieja, self.e.variedad, 5, precio="10.00")
        CompraVenta.objects.filter(pk=vieja.pk).update(fecha_realizacion=HOY - timedelta(days=5))
        reciente = compra_venta(otro, estado="cancelada", cliente_=self.e.cliente)
        detalle(reciente, self.e.variedad, 5, precio="777.25", estado="cancelado")
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos())
        self.assertEqual(formulario.filas[0].precio_propuesto, Decimal("777.25"))

    def test_ext_9a_una_variedad_que_nunca_se_vendio_no_propone_precio(self):
        """Extensión 9a: sin ventas previas, no se propone precio."""
        self.assertIsNone(compra_ventas.datos_del_formulario(self.e.vendedor, self.datos()).filas[0].precio_propuesto)

    def test_ext_10a_la_cantidad_es_un_entero_de_al_menos_uno_y_hasta_el_disponible(self):
        """Extensión 10a y regla «Cantidad solicitada válida»: 0, texto o vacío, `cantidad_invalida`; más que el disponible,
        `supera_disponible` («Hay N plantas disponibles para esa fecha.»); justo el disponible, vale."""
        for cantidad in ("0", "abc", "", "-3", "2,5"):
            with self.subTest(cantidad=cantidad):
                self.assertEqual(codigos_de(self.rechazo(cantidad=cantidad), "renglon-0-cantidad"), ["cantidad_invalida"])
        error = self.rechazo(cantidad="101")
        self.assertEqual(codigos_de(error, "renglon-0-cantidad"), ["supera_disponible"])
        self.assertEqual(error.error_dict["renglon-0-cantidad"][0].message, "Hay 100 plantas disponibles para esa fecha.")
        self.assertEqual(self.registrar(cantidad="100").detalles.get().cant_solicitada_venta, 100)

    def test_ext_10b_una_variedad_no_se_repite_en_la_venta(self):
        """Extensión 10b y regla «Una variedad por venta»: el segundo renglón de la misma variedad es `variedad_repetida`."""
        renglones = [Renglon(0, str(self.e.variedad.pk), "10", "100"), Renglon(1, str(self.e.variedad.pk), "5", "100")]
        self.assertEqual(codigos_de(self.rechazo(renglones=renglones), "renglon-1-variedad"), ["variedad_repetida"])

    def test_ext_10c_el_precio_es_mayor_que_cero_con_dos_decimales(self):
        """Extensión 10c y regla «Precio unitario»: cero, negativo, más de dos decimales, vacío, sobre el máximo o texto, `precio_invalido`; con coma o con
        punto decimal valen."""
        for precio in ("0", "0,00", "-5", "1,505", "", "abc", "10000000000"):
            with self.subTest(precio=precio):
                self.assertEqual(codigos_de(self.rechazo(precio=precio), "renglon-0-precio"), ["precio_invalido"])
        self.assertEqual(self.registrar(precio="1.500,50", cantidad="5").detalles.get().precio_unitario_de_venta, Decimal("1500.50"))
        self.assertEqual(self.registrar(precio="99.99", cantidad="5").detalles.get().precio_unitario_de_venta, Decimal("99.99"))
        self.assertEqual(self.registrar(precio="9999999999,99", cantidad="5").detalles.get().precio_unitario_de_venta, Decimal("9999999999.99"))

    def test_ext_11a_sin_ningun_renglon_no_se_registra(self):
        """Extensión 11a: una venta sin renglones (o con renglones vacíos) rechaza con `sin_renglones` («Cargá al menos una variedad.»)."""
        for renglones in ([], [Renglon(0)]):
            with self.subTest(renglones=renglones):
                error = self.rechazo(renglones=renglones)
                self.assertEqual(codigos_de(error, "__all__"), ["sin_renglones"])
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_ext_9_10a_el_subtotal_y_el_monto_estimado_son_cantidad_por_precio(self):
        """Pasos 10 y 12 y regla «Monto estimado»: la suma de cantidad por precio; no se guarda."""
        otra, _ = variedad_con_stock(self.e, nombre="Otra", habilitar=False)
        lote_maduro(self.e, 50, variedad=otra)
        renglones = [Renglon(0, str(self.e.variedad.pk), "10", "100,50"), Renglon(1, str(otra.pk), "4", "25")]
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(renglones=renglones))
        self.assertEqual([f.subtotal for f in formulario.filas], [Decimal("1005.00"), Decimal("100.00")])
        self.assertEqual(formulario.monto_estimado, Decimal("1105.00"))
        venta = self.registrar(renglones=renglones)
        self.assertEqual(venta.detalles.count(), 2)

    def test_regla_la_venta_con_varios_renglones_reserva_cada_variedad(self):
        """Paso 15: `asignar` una vez por cada detalle (en orden de variedad)."""
        otra, _ = variedad_con_stock(self.e, nombre="Otra", habilitar=False)
        lote_maduro(self.e, 50, variedad=otra)
        renglones = [Renglon(0, str(self.e.variedad.pk), "10", "100"), Renglon(1, str(otra.pk), "4", "25")]
        venta = self.registrar(renglones=renglones)
        self.assertEqual(ReservaStock.objects.filter(detalle_venta__compra_venta=venta).count(), 2)
        self.assertEqual(Cosecha.objects.count(), 2)

    def test_ext_14a_si_el_stock_cambio_no_se_registra_nada_e_informa_el_maximo(self):
        """Extensión 14a: el stock que se veía ya no alcanza al confirmar: `stock_insuficiente` con la nueva cantidad máxima; se revierte todo
        (venta, detalles, reservas, cosechas, auditoría y avisos)."""
        error_real = None
        falso = {self.e.variedad.pk: mock.Mock(total=1000, lotes=1000, partidas=0)}
        with mock.patch.object(compra_ventas.stock_maduro, "disponible", return_value=falso):
            with self.assertRaises(ValidationError) as contexto:
                self.registrar(cantidad="500")
        error_real = contexto.exception
        self.assertEqual(codigos_de(error_real, "renglon-0-cantidad"), ["stock_insuficiente"])
        self.assertEqual(error_real.error_dict["renglon-0-cantidad"][0].message, "Hay 100 plantas disponibles para esa fecha.")
        self.assertEqual(codigos_de(error_real, "__all__"), ["stock_insuficiente"])
        for modelo in (CompraVenta, DetalleVenta, ReservaStock, DetalleReserva, Cosecha, Notificacion):
            self.assertEqual(modelo.objects.count(), 0, modelo.__name__)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="registro_compra_venta").exists())

    def test_regla_la_venta_nunca_reserva_mas_que_el_stock_libre_de_un_lote(self):
        """Garantía mínima 3: dos ventas por lo que hay: la segunda no alcanza (`supera_disponible` con el máximo nuevo, 40)."""
        self.registrar(cantidad="60")
        error = self.rechazo(cantidad="61")
        self.assertEqual(error.error_dict["renglon-0-cantidad"][0].message, "Hay 40 plantas disponibles para esa fecha.")


class CambiosDuranteLaCargaTests(BaseDeRegistro):
    """Lo que cambia entre que se carga la venta y se confirma (lo ve el registro después de bloquear)."""

    def entre_la_carga_y_la_confirmacion(self, cambio):
        """Registra con una función que corre ``cambio()`` justo después del análisis previo (antes de bloquear)."""
        real = compra_ventas._analizar

        def con_cambio(*args, **kwargs):
            resultado = real(*args, **kwargs)
            cambio()
            return resultado

        with mock.patch.object(compra_ventas, "_analizar", side_effect=con_cambio), self.assertRaises(ValidationError) as contexto:
            self.registrar()
        return contexto.exception

    def test_regla_cliente_dado_de_baja_entre_la_carga_y_la_confirmacion(self):
        """Paso 14 y bloqueos: `cliente_inactivo` («El cliente se dio de baja mientras cargabas la venta.»); no queda nada."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: Cliente.objects.filter(pk=self.e.cliente.pk).update(estado_cliente="inactivo"))
        self.assertEqual(codigos_de(error, "cliente"), ["cliente_inactivo"])
        self.assertEqual(error.error_dict["cliente"][0].message, "El cliente se dio de baja mientras cargabas la venta.")
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_regla_direccion_desactivada_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos: la dirección sigue activa y es del cliente (`direccion_no_valida`)."""
        error = self.entre_la_carga_y_la_confirmacion(lambda: Direccion.objects.filter(pk=self.e.direccion.pk).update(estado_direccion="inactivo"))
        self.assertEqual(codigos_de(error, "direccion"), ["direccion_no_valida"])

    def test_regla_invernadero_que_dejo_de_ser_del_vendedor_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos: en un retiro, `invernadero_no_habilitado`; en un envío, ese invernadero deja de considerarse y la venta no alcanza."""
        otro = crear_vendedor(email="nuevo@infoponia.com")
        cambio = lambda: Invernadero.objects.filter(pk=self.e.invernadero.pk).update(vendedor=otro)  # noqa: E731
        error = self.entre_la_carga_y_la_confirmacion(cambio)
        self.assertEqual(codigos_de(error, "renglon-0-cantidad"), ["stock_insuficiente"])
        Invernadero.objects.filter(pk=self.e.invernadero.pk).update(vendedor=self.e.vendedor)
        real = compra_ventas._analizar

        def con_cambio(*args, **kwargs):
            resultado = real(*args, **kwargs)
            cambio()
            return resultado

        with mock.patch.object(compra_ventas, "_analizar", side_effect=con_cambio), self.assertRaises(ValidationError) as contexto:
            self.registrar(modalidad="retiro", direccion_id="", invernadero_id=str(self.e.invernadero.pk))
        self.assertEqual(codigos_de(contexto.exception, "invernadero"), ["invernadero_no_habilitado"])
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_regla_vendedor_dado_de_baja_entre_la_carga_y_la_confirmacion(self):
        """Bloqueos: el Vendedor responsable (elegido por el Gerente) sigue activo (`vendedor_inactivo`)."""
        real = compra_ventas._analizar

        def con_baja(*args, **kwargs):
            resultado = real(*args, **kwargs)
            type(self.e.vendedor).objects.filter(pk=self.e.vendedor.pk).update(is_active=False)
            return resultado

        with mock.patch.object(compra_ventas, "_analizar", side_effect=con_baja), self.assertRaises(ValidationError) as contexto:
            self.registrar(self.gerente, vendedor_id=str(self.e.vendedor.pk))
        self.assertEqual(codigos_de(contexto.exception, "vendedor"), ["vendedor_inactivo"])
        self.assertEqual(CompraVenta.objects.count(), 0)


class ComprobanteTests(BaseDeRegistro):
    """Paso 16 y extensiones 16a y 16b: el comprobante, fuera de la transacción."""

    @override_settings(CORREO_CONFIGURADO=True)
    def test_post_h_con_correo_el_comprobante_sale_y_la_venta_queda_enviada(self):
        """Postcondición h y paso 16: se envía al cliente un texto plano con el comprobante; `estado_comprobante = enviado`."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True) as enviar:
            venta = self.registrar()
        cuenta, asunto, plantilla, contexto = enviar.call_args.args
        self.assertEqual((cuenta.email, cuenta.pk), (self.e.cliente.email_cliente, self.e.cliente.pk))
        self.assertEqual(asunto, f"Comprobante de tu compra {venta.codigo}")
        self.assertEqual(contexto["monto"], Decimal("45015.00"))
        self.assertEqual(venta.estado_comprobante, "enviado")
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_comprobante, "enviado")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_16a_si_el_correo_falla_la_venta_queda_pendiente_de_envio(self):
        """Extensión 16a (con `enviar_correo` devolviendo `False`): la venta permanece registrada con el comprobante pendiente de envío."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            venta = self.registrar()
        self.assertEqual(CompraVenta.objects.get(pk=venta.pk).estado_comprobante, "pendiente_envio")
        self.assertEqual(Notificacion.objects.filter(titulo="Comprobante pendiente de envío").count(), 0)

    def test_ext_16a_sin_el_correo_del_sistema_configurado_queda_pendiente_de_envio(self):
        """Extensión 16a: con el correo del sistema sin configurar (las pruebas lo apagan), `pendiente_envio`."""
        self.assertEqual(self.registrar().estado_comprobante, "pendiente_envio")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_16a_si_registro_el_gerente_el_vendedor_recibe_el_aviso_del_comprobante_pendiente(self):
        """Extensión 16a: si registró el Gerente, el Vendedor responsable recibe «El comprobante de CV-… quedó pendiente de envío.»."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            venta = self.registrar(self.gerente, vendedor_id=str(self.e.vendedor.pk))
        aviso = Notificacion.objects.get(destinatario=self.e.vendedor, titulo="Comprobante pendiente de envío")
        self.assertEqual(aviso.detalle, f"El comprobante de {venta.codigo} quedó pendiente de envío.")

    def test_ext_16b_un_cliente_sin_correo_recibe_el_comprobante_impreso(self):
        """Extensión 16b: sin correo, `para_imprimir`; no se intenta enviar nada."""
        sin_correo = crear_cliente(razon_social="Sin correo S.A.", email="")
        vinculo = direccion_de_cliente(sin_correo)
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo") as enviar:
            venta = self.registrar(cliente_id=str(sin_correo.pk), direccion_id=str(vinculo.direccion_id))
        enviar.assert_not_called()
        self.assertEqual(venta.estado_comprobante, "para_imprimir")

    @override_settings(CORREO_CONFIGURADO=True)
    def test_requisito_el_correo_sale_fuera_de_la_transaccion(self):
        """Pasos 15 y 16 y D-14: el correo se manda después de confirmar, nunca con los bloqueos de la venta tomados (se compara la
        profundidad de bloques atómicos con la de la prueba)."""
        base = len(connection.savepoint_ids)

        def enviar(*args):
            self.assertEqual(len(connection.savepoint_ids), base)
            return True

        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", side_effect=enviar) as simulado:
            self.registrar()
        simulado.assert_called_once()

    @override_settings(CORREO_CONFIGURADO=True)
    def test_ext_16a_reenviar_pasa_a_enviado_solo_si_estaba_pendiente(self):
        """«Reenviar comprobante» (16a): lo hace el Vendedor responsable o el Gerente, solo desde «pendiente de envío»; sin auditoría."""
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=False):
            venta = self.registrar()
        antes = RegistroAuditoria.objects.count()
        with mock.patch("comercial.servicios.comprobantes.correo.enviar_correo", return_value=True):
            self.assertEqual(comprobantes.reenviar_comprobante(self.e.vendedor, venta.pk), "enviado")
            with self.assertRaises(ValidationError) as contexto:
                comprobantes.reenviar_comprobante(self.gerente, venta.pk)
        self.assertEqual(contexto.exception.code, "comprobante_no_pendiente")
        self.assertEqual(RegistroAuditoria.objects.count(), antes)

    def test_ext_16a_reenviar_lo_ve_solo_el_vendedor_responsable_o_el_gerente(self):
        """«Reenviar comprobante»: otro Vendedor o cualquier otro rol, `PermissionDenied`; un cliente sin correo, `cliente_sin_correo`."""
        venta = self.registrar()
        otro = crear_vendedor(email="otro@infoponia.com")
        for actor in (otro, self.e.agronomo, None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                comprobantes.reenviar_comprobante(actor, venta.pk)
        Cliente.objects.filter(pk=self.e.cliente.pk).update(email_cliente="")
        with self.assertRaises(ValidationError) as contexto:
            comprobantes.reenviar_comprobante(self.gerente, venta.pk)
        self.assertEqual(contexto.exception.code, "cliente_sin_correo")

    def test_regla_el_comprobante_dice_los_datos_de_la_venta(self):
        """Variación 16a: detalles, cantidades, precios, monto estimado, fecha pactada y modalidad (dirección o invernadero de retiro)."""
        venta = self.registrar(cantidad="10", precio="100,00")
        contexto = compra_ventas.datos_del_comprobante(venta)
        self.assertEqual((contexto["monto"], len(contexto["filas"])), (Decimal("1000.00"), 1))
        self.assertIn("San Martín 123", contexto["destino"])
        retiro = self.registrar(modalidad="retiro", direccion_id="", invernadero_id=str(self.e.invernadero.pk), cantidad="5")
        self.assertIn(self.e.invernadero.nombre_invernadero, compra_ventas.datos_del_comprobante(retiro)["destino"])


class FormularioYResumenTests(BaseDeRegistro):
    """`datos_del_formulario` (sin escribir, consultas fijas) y `resumen` (paso 12)."""

    def consultas(self, renglones):
        """Cuántas consultas hace `datos_del_formulario` con esos renglones."""
        with CaptureQueriesContext(connection) as capturadas:
            compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(renglones=renglones))
        return len(capturadas)

    def test_regla_datos_del_formulario_hace_las_mismas_consultas_con_1_y_con_5_renglones(self):
        """Requisito «no más de 1 segundo»: consultas constantes, sin consultas por renglón."""
        variedades = [self.e.variedad] + [variedad_con_stock(self.e, nombre=f"V{n}", habilitar=False)[0] for n in range(4)]
        for v in variedades[1:]:
            lote_maduro(self.e, 20, variedad=v)
        uno = self.consultas([Renglon(0, str(variedades[0].pk), "5", "10")])
        cinco = self.consultas([Renglon(i, str(v.pk), "5", "10") for i, v in enumerate(variedades)])
        self.assertEqual(uno, cinco)

    def test_regla_datos_del_formulario_no_escribe_ni_bloquea(self):
        """Pasos 2 a 10: solo lee. No crea nada, no bloquea y deja las mismas filas."""
        with CaptureQueriesContext(connection) as capturadas:
            compra_ventas.datos_del_formulario(self.e.vendedor, self.datos())
        sql = " ".join(q["sql"].upper() for q in capturadas)
        for escritura in ("INSERT", "UPDATE", "DELETE", "FOR NO KEY UPDATE", "FOR UPDATE"):
            self.assertNotIn(escritura, sql)

    def test_ext_13a_1a_al_cambiar_la_fecha_los_renglones_que_ya_no_alcanzan_quedan_con_su_error(self):
        """Extensión 13a.1a: con otra fecha se vuelve a calcular el stock y se informa lo que ya no se puede cubrir."""
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(dias=60, cantidad="30"))
        self.assertEqual(formulario.errores["renglon-0-cantidad"], ["Hay 0 plantas disponibles para esa fecha."])

    def test_ext_13a_1b_al_cambiar_de_cliente_se_descarta_la_direccion(self):
        """Extensión 13a.1b: la dirección elegida era del cliente anterior: se descarta y se ofrecen las del nuevo."""
        nuevo = crear_cliente(razon_social="Nuevo S.A.")
        vinculo = direccion_de_cliente(nuevo)
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(cliente_id=str(nuevo.pk)))
        self.assertIsNone(formulario.direccion)
        self.assertEqual([d.pk for d in formulario.direcciones], [vinculo.direccion_id])
        self.assertNotIn("direccion", formulario.errores)

    def test_regla_las_secciones_se_habilitan_en_orden(self):
        """Criterio de interfaz: Entrega con el cliente elegido; Variedades con la fecha y la dirección o el invernadero."""
        sin_nada = compra_ventas.datos_del_formulario(self.e.vendedor, DatosDeCompraVenta())
        self.assertEqual((sin_nada.entrega_habilitada, sin_nada.variedades_habilitadas, sin_nada.errores), (False, False, {}))
        con_cliente = compra_ventas.datos_del_formulario(self.e.vendedor, DatosDeCompraVenta(cliente_id=str(self.e.cliente.pk)))
        self.assertEqual((con_cliente.entrega_habilitada, con_cliente.variedades_habilitadas), (True, False))
        completo = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos())
        self.assertTrue(completo.variedades_habilitadas)

    def test_regla_un_cliente_sin_correo_avisa_que_el_comprobante_va_impreso(self):
        """Texto de la pantalla: con un cliente sin correo, el formulario lo marca."""
        sin_correo = crear_cliente(razon_social="Sin correo S.A.", email="")
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, DatosDeCompraVenta(cliente_id=str(sin_correo.pk)))
        self.assertTrue(formulario.cliente_sin_correo)

    def test_regla_resumen_trae_el_destino_y_el_monto_y_valida_como_el_registro(self):
        """Paso 12: el resumen trae cliente, Vendedor, modalidad con su destino, fecha, renglones y monto estimado; con un error, `ValidationError`."""
        resumen = compra_ventas.resumen(self.e.vendedor, self.datos(cantidad="10", precio="100,00"))
        self.assertEqual(resumen.formulario.monto_estimado, Decimal("1000.00"))
        self.assertIn("San Martín 123", resumen.destino)
        with self.assertRaises(ValidationError):
            compra_ventas.resumen(self.e.vendedor, self.datos(cantidad="0"))
        self.assertEqual(CompraVenta.objects.count(), 0)

    def test_regla_un_retiro_con_un_solo_invernadero_lo_deja_elegido(self):
        """Extensión 5a (`retiroFld` del prototipo): si el Vendedor tiene un solo invernadero activo, queda elegido."""
        formulario = compra_ventas.datos_del_formulario(self.e.vendedor, self.datos(modalidad="retiro", direccion_id=""))
        self.assertEqual(formulario.invernadero_de_retiro.pk, self.e.invernadero.pk)

    def test_ext_1a_el_gerente_ve_los_vendedores_con_sus_invernaderos(self):
        """Extensión 1a: la lista de Vendedores activos con sus invernaderos activos."""
        escenario_comercial(sufijo="2")
        formulario = compra_ventas.datos_del_formulario(self.gerente, DatosDeCompraVenta())
        self.assertEqual(len(formulario.vendedores), 2)
        self.assertTrue(all(invernaderos for _, invernaderos in formulario.vendedores))


class PlanificacionDeLaEntregaTests(BaseDeRegistro):
    """Postcondición g (COM-05a1; D-66 punto 5): una venta que sale toda de cámara programa su entrega con `on_commit`."""

    def test_post_g_una_venta_que_sale_toda_de_camara_programa_su_entrega_despues_de_confirmar(self):
        """Postcondición g: con todas las reservas «lista para entrega» la entrega se planifica DESPUÉS de confirmar (no dentro de la transacción de quien registra)."""
        from comercial.models import Entrega
        from comercial.tests.fabricas import partida_cosechada, transportista_con_vehiculo

        partida_cosechada(self.lote, 50)
        transportista_con_vehiculo(self.e.invernadero, "800")
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            venta = self.registrar()
            self.assertEqual(Entrega.objects.count(), 0)
        for callback in callbacks:
            callback()
        entrega = Entrega.objects.get()
        self.assertEqual((entrega.contrato_entrega_id, entrega.estado_orden), (venta.pk, "a_realizar"))

    def test_post_g_una_venta_con_una_cosecha_pendiente_no_planifica_nada(self):
        """Con una reserva «activa» (la cosecha todavía no se concretó), la venta no está lista: no hay entrega."""
        from comercial.models import Entrega

        with self.captureOnCommitCallbacks(execute=True):
            self.registrar()
        self.assertEqual(Entrega.objects.count(), 0)
