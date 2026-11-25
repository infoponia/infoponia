# Pruebas de `entregas.estado_de_pago` de COM-08a (paso 2): las cuatro filas de la tabla de «Estado de pago y monto a cobrar», el día del vencimiento y el siguiente, el pago anulado y el vigente de una misma
# entrega, una de compra-venta (la clave está con `None`, como desde COM-06a) y la cantidad de consultas. `EstadoDePago` es un `str` con `.estado`, `.saldada` y `.cobro`.
# Fuente: docs/casos_de_uso/comercial/cobranza.md («Estado de pago y monto a cobrar»), D-94 punto 4, MD-125, MD-136, MD-139.
#
# DIFERENCIA CON LA DOCUMENTACIÓN (decidida por el estudiante, L7): D-94 punto 4 y cobranza.md dicen `EstadoDePago(estado, saldada, cobro)` como tupla y que la clave de una entrega que no es de suministro «no está
# (como hoy)». Se implementa como un `str` con atributos (el texto de siempre, para que `clientes.py`, `solicitudes.py`, las plantillas y `test_extensiones_entregas.py` sigan andando sin tocarse) y la compra-venta
# conserva su `None`, como desde COM-06a. Va al Cierre y a `docs/temas_abiertos.md`.
#
# Contrato de código que fijan estas pruebas (el estudiante lo revisa): `estado_de_pago(entrega_ids, hoy) -> dict[int, EstadoDePago | None]`; `EstadoDePago` es un `str` («pendiente», «en_mora» o «pagada») que se compara,
# se hashea y se muestra como ese texto, con `.estado` (el mismo texto), `.saldada` (bool) y `.cobro` (`None` o un `CobroDeEntrega` con `pago_id`, `codigo`, `fecha` y `quien`).

from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext

from comercial.models import Suministro
from comercial.servicios import entregas
from comercial.tests.base_cobranza import HOY, BaseDeCobranza
from comercial.tests.fabricas import (
    compra_venta,
    cobro,
    detalle,
    discrepancia_aceptada,
    entrega_concretada,
    entrega_de_suministro,
    entrega,
    reserva_lista,
    suministro,
)

D = Decimal


class EstadoDePagoTests(BaseDeCobranza):
    def estado(self, e, hoy=HOY):
        return entregas.estado_de_pago([e.pk], hoy)[e.pk]

    # ---- las cuatro filas de la tabla ----

    def test_regla_fila_1_pagada_con_una_linea_vigente_trae_el_cobro(self):
        """`pagada` con una `LineaPago` vigente: no saldada, y `cobro` con el código, la fecha y quién lo registró."""
        e = self.concretada()
        pago = cobro([e], usuario=self.gerente)
        resultado = self.estado(e)
        self.assertEqual(resultado, "pagada")
        self.assertEqual((resultado.estado, resultado.saldada), ("pagada", False))
        self.assertEqual((resultado.cobro.pago_id, resultado.cobro.codigo, resultado.cobro.fecha), (pago.pk, pago.codigo, pago.fecha_pago))
        self.assertIn(self.gerente.email, resultado.cobro.quien)

    def test_regla_fila_1_el_cobro_sin_usuario_no_rompe_el_texto(self):
        """Un pago sin usuario (los que no registró una persona) devuelve `quien` vacío, no un error."""
        e = self.concretada()
        cobro([e])
        self.assertEqual(self.estado(e).cobro.quien, "")

    def test_regla_fila_2_saldada_si_el_monto_a_cobrar_es_cero(self):
        """MD-125: con el monto a cobrar en 0 (las indemnizaciones cubrieron todo) la entrega es `pagada` y `saldada`, sin cobro."""
        e = self.concretada()
        discrepancia_aceptada(e, monto="1000.00", descontado="1000.00")
        resultado = self.estado(e)
        self.assertEqual(resultado, "pagada")
        self.assertEqual((resultado.estado, resultado.saldada, resultado.cobro), ("pagada", True, None))

    def test_regla_fila_3_en_mora_si_hoy_pasa_el_vencimiento(self):
        """`en_mora`: no pagada y `hoy > fecha_vencimiento_pago`."""
        e = self.en_mora()
        resultado = self.estado(e)
        self.assertEqual(resultado, "en_mora")
        self.assertEqual((resultado.estado, resultado.saldada, resultado.cobro), ("en_mora", False, None))

    def test_regla_fila_4_pendiente_si_hoy_no_pasa_el_vencimiento(self):
        """`pendiente`: no pagada y `hoy <= fecha_vencimiento_pago`."""
        e = self.concretada()
        resultado = self.estado(e)
        self.assertEqual(resultado, "pendiente")
        self.assertEqual((resultado.estado, resultado.saldada, resultado.cobro), ("pendiente", False, None))

    # ---- el día del vencimiento ----

    def test_regla_el_dia_del_vencimiento_es_pendiente_y_el_siguiente_en_mora(self):
        """MD-139 y regla «Vencimiento del pago»: hasta el día del vencimiento todavía se paga sin atraso; la mora empieza al día siguiente."""
        e = self.concretada(plazo_pago=10)
        vencimiento = e.fecha_vencimiento_pago
        self.assertEqual(self.estado(e, vencimiento), "pendiente")
        self.assertEqual(self.estado(e, vencimiento + timedelta(days=1)), "en_mora")
        self.assertEqual(self.estado(e, vencimiento - timedelta(days=1)), "pendiente")

    # ---- el pago anulado y el vigente ----

    def test_regla_una_entrega_con_un_pago_anulado_y_uno_vigente_esta_pagada_con_el_vigente(self):
        """MD-136: el pago anulado conserva su vínculo; la entrega está pagada solo si tiene un cobro no anulado, y el `cobro` es el vigente."""
        e = self.concretada()
        anulado = cobro([e], estado="anulado")
        vigente = cobro([e])
        resultado = self.estado(e)
        self.assertEqual(resultado, "pagada")
        self.assertEqual(resultado.cobro.pago_id, vigente.pk)
        self.assertNotEqual(resultado.cobro.pago_id, anulado.pk)

    def test_regla_con_solo_un_pago_anulado_la_entrega_vuelve_a_pendiente_o_en_mora(self):
        """MD-136 (lo que usará COM-08b): sin cobro vigente, el estado se recalcula con el vencimiento guardado."""
        pendiente, en_mora = self.concretada(), self.en_mora()
        cobro([pendiente], estado="anulado")
        cobro([en_mora], estado="anulado")
        self.assertEqual((self.estado(pendiente), self.estado(en_mora)), ("pendiente", "en_mora"))
        self.assertIsNone(self.estado(pendiente).cobro)

    # ---- lo que no es una entrega de suministro concretada ----

    def test_regla_una_compra_venta_tiene_la_clave_con_none(self):
        """Como desde COM-06a: una entrega de compra-venta no tiene estado de pago de entrega (la clave está, con `None`). Su pago es el de la venta."""
        venta = compra_venta(self.e, dias=0)
        reserva = reserva_lista(detalle(venta, self.e.variedad, 10), self.lote, 10)
        de_venta = entrega_concretada(venta, [reserva], con_pago=True)
        self.assertEqual(entregas.estado_de_pago([de_venta.pk], HOY), {de_venta.pk: None})

    def test_regla_una_entrega_sin_concretar_no_tiene_estado_de_pago(self):
        """Una entrega «a realizar» de un suministro todavía no tiene vencimiento: `None`."""
        from comercial.tests.fabricas import detalle_suministro

        contrato = suministro(self.e)
        d = detalle_suministro(contrato, self.e.variedad, cantidad=10, primera_en_dias=0)
        a_realizar = entrega(contrato, [reserva_lista(None, self.lote, 10, fecha_entrega=d.fecha_primer_entrega, detalle_suministro=d)])
        self.assertEqual(entregas.estado_de_pago([a_realizar.pk], HOY), {a_realizar.pk: None})

    def test_regla_un_id_inexistente_devuelve_none_sin_fallar(self):
        """Como `monto_a_cobrar`: la clave de cada id pedido está siempre."""
        self.assertEqual(entregas.estado_de_pago([999999], HOY), {999999: None})

    def test_regla_una_lista_vacia_no_consulta_la_base_de_mas(self):
        """Sin ids, `{}`."""
        self.assertEqual(entregas.estado_de_pago([], HOY), {})

    # ---- el tipo EstadoDePago ----

    def test_regla_estado_de_pago_es_un_str_con_atributos(self):
        """Se compara, se hashea y se muestra como el texto de siempre (para que lo ya escrito siga andando) y trae `.estado`, `.saldada` y `.cobro`."""
        e = self.concretada()
        for resultado, texto in ((self.estado(e), "pendiente"), (self.estado(self.en_mora()), "en_mora")):
            with self.subTest(texto=texto):
                self.assertIsInstance(resultado, str)
                self.assertIsInstance(resultado, entregas.EstadoDePago)
                self.assertEqual(resultado, texto)
                self.assertEqual(hash(resultado), hash(texto))
                self.assertEqual(str(resultado), texto)
                self.assertEqual(f"{resultado}", texto)
                self.assertIn(resultado, (texto, "otro"))
                self.assertEqual({texto: 1}[resultado], 1)
                self.assertEqual(resultado.estado, texto)
                self.assertFalse(resultado.saldada)
                self.assertIsNone(resultado.cobro)

    def test_regla_el_dict_compara_igual_que_con_textos(self):
        """`test_extensiones_entregas.py` compara el dict entero contra textos: tiene que seguir siendo igual."""
        a, b = self.concretada(), self.en_mora()
        self.assertEqual(entregas.estado_de_pago([a.pk, b.pk], HOY), {a.pk: "pendiente", b.pk: "en_mora"})

    # ---- consultas ----

    def test_regla_una_consulta_por_tabla_igual_con_una_y_con_cinco_entregas(self):
        """Sin consultas por entrega: la misma cantidad con una entrega que con cinco (entregas, líneas de pago vigentes y solicitudes aceptadas)."""
        primera = self.concretada()
        with CaptureQueriesContext(connection) as pocas:
            entregas.estado_de_pago([primera.pk], HOY)
        contrato = Suministro.objects.get(pk=primera.contrato_entrega_id)
        mas = [primera]
        for _ in range(4):
            mas.append(entrega_de_suministro(self.e, self.lote, contrato=contrato))
        cobro(mas[1:3], usuario=self.gerente)
        with CaptureQueriesContext(connection) as muchas:
            entregas.estado_de_pago([e.pk for e in mas], HOY)
        self.assertEqual(len(pocas), len(muchas))
        self.assertLessEqual(len(muchas), 3)
