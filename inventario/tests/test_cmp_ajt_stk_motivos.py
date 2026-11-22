# Pruebas de CMP-AJT-STK · los motivos del ajuste (docs/casos_de_uso/inventario/ajuste_de_stock.md: extensiones 7a, 7b, 7c, 7d y 7e; reglas
# «Motivos», «Lote de insumo nuevo», «Baja por vencimiento», «Corrección entre lotes» y «Faltante sin lote»; postcondiciones a, b, d, f, g y k a m;
# INV-02, paso 6). El recuento físico está en test_cmp_ajt_stk_recuento.py. El contrato del servicio, en ``inventario/tests/ajustes_comunes.py``.
#
# Decisiones de aplicación (L7, «Cómo se aplica en la ronda»):
#   - «otro» que suma crea un lote NUEVO (extensión 7e → 7a), no suma a uno existente (diferencia n.º 1 con el modelo).
#   - Una carga inicial o un «otro» que suma NO tocan el faltante sin lote; solo un recuento o una corrección que lo tiene de destino (n.º 2).
#   - La corrección entre lotes no es un motivo guardado: se guarda con sus dos tipos propios (salida y entrada por corrección), sin motivo,
#     y la entrada se origina en su salida (R016, regla 2 de 8.19).

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase

from core.models import RegistroAuditoria
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.ajustes_comunes import (
    CARGA_INICIAL,
    CORRECCION,
    OTRO,
    RECUENTO,
    ROTURA,
    VENCIMIENTO,
    BaseDeAjustes,
)
from inventario.tests.fabricas import existencia, faltante, insumo, lote

D = Decimal
Mov = MovimientoInsumo.TipoMovimiento
AJUSTE = RegistroAuditoria.Accion.AJUSTE_STOCK


class CmpAjtStkMotivosTests(BaseDeAjustes, TestCase):
    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.l2 = lote(self.iin, 20, vence=self.vence + timedelta(days=30))

    def movimientos_de(self, un_lote, tipo=None):
        consulta = MovimientoInsumo.objects.filter(lote_insumo=un_lote).order_by("id")
        return list(consulta.filter(tipo_movimiento=tipo) if tipo else consulta)

    # ---- 7a · carga inicial ----

    def test_extension_7a_la_carga_inicial_crea_un_lote_nuevo_con_su_movimiento(self):
        """Extensión 7a y postcondiciones a, b y d: lote nuevo con la cantidad y el vencimiento, y un «ajuste positivo / carga inicial»."""
        resultado = self.confirmar(CARGA_INICIAL, {"cantidad": "30", "vencimiento": self.vence + timedelta(days=5)})
        [nuevo] = resultado.lotes_nuevos
        nuevo.refresh_from_db()
        self.assertEqual(
            (nuevo.cantidad_ingresada, nuevo.cantidad_disponible, nuevo.fecha_ingreso, nuevo.fecha_vencimiento),
            (D("30"), D("30"), self.hoy, self.vence + timedelta(days=5)),
        )
        [movimiento] = self.movimientos_de(nuevo)
        self.assertEqual(
            (movimiento.tipo_movimiento, movimiento.cantidad, movimiento.motivo_ajuste, movimiento.origen_id),
            (Mov.AJUSTE_POSITIVO, D("30"), "carga_inicial", None),
        )
        self.assertEqual(resultado.stock_actual, D("60"))
        self.invariantes()

    def test_extension_7a_el_resumen_muestra_el_valor_de_la_carga(self):
        """Paso 12: el valor del ajuste sigue mostrándose (sin asiento, D-45): cantidad × precio de referencia."""
        r = self.calcular(CARGA_INICIAL, {"cantidad": "30", "vencimiento": self.vence})
        self.assertEqual((r.valor, r.con_valor, r.stock_antes, r.stock_despues), (D("3000.00"), True, D("30"), D("60")))
        self.assertEqual([(n.cantidad, n.vencimiento) for n in r.lotes_nuevos], [(D("30"), self.vence)])

    def test_extension_7a_un_insumo_que_no_controla_vencimiento_se_carga_sin_fecha(self):
        """Postcondición b: lote sin vencimiento si el insumo no lo controla."""
        bolsas = existencia(insumo("Bolsas", tipo=self.tipo, unidad="unidad"), self.invernadero, precio="2")
        resultado = self.confirmar(CARGA_INICIAL, {"cantidad": "40"}, iin=bolsas)
        self.assertIsNone(resultado.lotes_nuevos[0].fecha_vencimiento)
        self.invariantes(bolsas)

    def test_extension_7a_el_vencimiento_de_hoy_es_valido(self):
        """Regla «Lote de insumo nuevo»: la fecha no puede ser anterior a la actual; hoy se puede."""
        resultado = self.confirmar(CARGA_INICIAL, {"cantidad": "1", "vencimiento": self.hoy})
        self.assertEqual(resultado.lotes_nuevos[0].fecha_vencimiento, self.hoy)

    def test_regla_faltante_la_carga_inicial_no_toca_el_faltante_sin_lote(self):
        """Diferencia n.º 2 con el modelo: manda el CU; la carga inicial no cancela el faltante."""
        falta = faltante(self.iin, 3)
        self.confirmar(CARGA_INICIAL, {"cantidad": "10", "vencimiento": self.vence})
        self.assertEqual(self.disponible(falta), D("-3"))
        self.invariantes()

    def test_extension_7a_la_descripcion_opcional_se_guarda_en_el_movimiento(self):
        """Postcondición d: «la descripción, si se indicó»."""
        resultado = self.confirmar(
            CARGA_INICIAL, {"cantidad": "10", "vencimiento": self.vence, "descripcion": "Stock del depósito viejo"}
        )
        self.assertEqual(resultado.movimientos[0].descripcion_ajuste, "Stock del depósito viejo")

    # ---- 7b · rotura o pérdida ----

    def test_extension_7b_la_rotura_descuenta_del_lote_con_un_ajuste_negativo(self):
        """Extensión 7b y postcondiciones a y d: el lote baja la cantidad y se crea un «ajuste negativo / rotura o pérdida»."""
        resultado = self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual(self.disponible(self.l1), D("6"))
        [movimiento] = self.movimientos_de(self.l1, Mov.AJUSTE_NEGATIVO)
        self.assertEqual((movimiento.cantidad, movimiento.motivo_ajuste, movimiento.origen_id), (D("4"), "rotura_o_perdida", None))
        self.assertEqual(resultado.stock_actual, D("26"))
        self.invariantes()

    def test_extension_7b_el_resumen_muestra_el_valor_negativo(self):
        """Paso 12: valor negativo de una resta, sin lotes nuevos."""
        r = self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual((r.valor, r.diferencia, r.lotes_nuevos), (D("-400.00"), D("-4"), []))
        [cambio] = r.lotes
        self.assertEqual((cambio.registrada, cambio.contada, cambio.diferencia), (D("10"), D("6"), D("-4")))

    def test_extension_7b_se_puede_descontar_todo_lo_disponible_y_el_lote_queda_en_cero(self):
        """El tope es lo disponible del lote: igual a lo disponible es válido; el lote se conserva en 0."""
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "10"})
        self.assertEqual(self.disponible(self.l1), D("0"))
        self.invariantes()

    def test_regla_8_23_4_un_ajuste_negativo_nunca_sale_del_faltante_sin_lote(self):
        """Regla 4 de 8.23: la rotura trabaja sobre lotes con stock; el faltante queda como estaba."""
        falta = faltante(self.iin, 3)
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual(self.disponible(falta), D("-3"))

    # ---- 7c · vencimiento ----

    def preparar_vencidos(self):
        self.v1 = lote(self.iin, 5, vence=self.vencido)
        self.v2 = lote(self.iin, 7, vence=self.vencido - timedelta(days=4))

    def test_extension_7c_da_de_baja_todo_lo_que_le_queda_a_cada_lote_vencido_indicado(self):
        """Extensión 7c: por cada lote indicado se descuenta todo lo que le queda, con un «ajuste negativo / vencimiento»."""
        self.preparar_vencidos()
        resultado = self.confirmar(VENCIMIENTO, {"lotes": [self.v1.pk, self.v2.pk]})
        self.assertEqual((self.disponible(self.v1), self.disponible(self.v2)), (D("0"), D("0")))
        self.assertEqual(
            sorted((m.lote_insumo_id, m.cantidad, m.tipo_movimiento, m.motivo_ajuste) for m in resultado.movimientos),
            sorted(
                [
                    (self.v1.pk, D("5"), Mov.AJUSTE_NEGATIVO, "vencimiento"),
                    (self.v2.pk, D("7"), Mov.AJUSTE_NEGATIVO, "vencimiento"),
                ]
            ),
        )
        self.assertEqual(self.disponible(self.l1), D("10"))
        self.invariantes()

    def test_extension_7c_se_pueden_dar_de_baja_solo_algunos(self):
        """Extensión 7c.2: el Agrónomo indica los lotes que da de baja; el otro vencido sigue como estaba."""
        self.preparar_vencidos()
        self.confirmar(VENCIMIENTO, {"lotes": [self.v1.pk]})
        self.assertEqual((self.disponible(self.v1), self.disponible(self.v2)), (D("0"), D("7")))

    def test_extension_7c_el_resumen_muestra_lo_que_baja_con_su_valor(self):
        """Paso 12: el valor de lo dado de baja (12 L × 100)."""
        self.preparar_vencidos()
        r = self.calcular(VENCIMIENTO, {"lotes": [self.v1.pk, self.v2.pk]})
        self.assertEqual((r.valor, r.diferencia, len(r.lotes)), (D("-1200.00"), D("-12"), 2))

    # ---- 7d · corrección entre lotes ----

    def test_extension_7d_la_correccion_mueve_cantidad_de_un_lote_a_otro_sin_cambiar_el_total(self):
        """Extensión 7d y postcondición f: el origen baja, el destino sube por la misma cantidad y el stock actual no cambia."""
        resultado = self.confirmar(CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "4"})
        self.assertEqual((self.disponible(self.l1), self.disponible(self.l2)), (D("6"), D("24")))
        self.assertEqual(resultado.stock_actual, D("30"))
        self.invariantes()

    def test_extension_7d_registra_una_salida_y_una_entrada_por_correccion_la_entrada_se_origina_en_su_salida(self):
        """Postcondición f y R016 (regla 2 de 8.19): dos movimientos por la misma cantidad; la entrada tiene como origen a su salida;
        no son movimientos de ajuste y no llevan motivo."""
        self.confirmar(CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "4"})
        [salida] = self.movimientos_de(self.l1, Mov.SALIDA_POR_CORRECCION)
        [entrada] = self.movimientos_de(self.l2, Mov.ENTRADA_POR_CORRECCION)
        self.assertEqual((salida.cantidad, entrada.cantidad), (D("4"), D("4")))
        self.assertIsNone(salida.origen_id)
        self.assertEqual(entrada.origen_id, salida.pk)
        self.assertEqual((salida.motivo_ajuste, entrada.motivo_ajuste), (None, None))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento__in=[Mov.AJUSTE_POSITIVO, Mov.AJUSTE_NEGATIVO], lote_insumo__in=[self.l1, self.l2]).count(), 2)  # solo los de los ingresos

    def test_extension_7d_el_resumen_dice_que_no_tiene_valor_y_que_el_total_no_cambia(self):
        """Extensión 7d.4: el resumen informa que el stock total no cambia y que el ajuste no tiene valor."""
        r = self.calcular(CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "4"})
        self.assertEqual((r.con_valor, r.valor, r.diferencia, r.stock_antes, r.stock_despues), (False, D("0.00"), D("0"), D("30"), D("30")))
        self.assertEqual({c.lote.pk: c.diferencia for c in r.lotes}, {self.l1.pk: D("-4"), self.l2.pk: D("4")})

    def test_extension_7d_el_faltante_sin_lote_puede_ser_el_destino_y_se_acerca_a_cero(self):
        """Regla «Faltante sin lote»: una corrección que lo tiene de destino lo acerca a cero; el total no cambia."""
        falta = faltante(self.iin, 3)
        self.confirmar(CORRECCION, {"origen_id": self.l1.pk, "destino_id": falta.pk, "cantidad": "2"})
        self.assertEqual((self.disponible(self.l1), self.disponible(falta)), (D("8"), D("-1")))
        self.invariantes()

    def test_extension_7d_la_correccion_audita_sin_cambio_de_stock(self):
        """D-36: el stock no cambia, así que el registro no lleva ``cambios`` (antes igual a después se rechaza) y sí los datos."""
        self.confirmar(CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "4"})
        registro = RegistroAuditoria.objects.get(accion=AJUSTE)
        self.assertNotIn("cambios", registro.detalle)
        self.assertEqual(registro.detalle["datos"]["motivo_ajuste"], "correccion_entre_lotes")

    # ---- 7e · otro ----

    def test_extension_7e_otro_que_suma_crea_un_lote_nuevo_y_no_suma_a_uno_existente(self):
        """Extensión 7e y diferencia n.º 1: manda el CU; «otro» que suma sigue 7a: lote nuevo, «ajuste positivo / otro» con su descripción."""
        resultado = self.confirmar(
            OTRO, {"sentido": "suma", "descripcion": "Donación de otro vivero", "cantidad": "6", "vencimiento": self.vence}
        )
        [nuevo] = resultado.lotes_nuevos
        self.assertEqual((self.disponible(self.l1), self.disponible(self.l2)), (D("10"), D("20")))
        [movimiento] = self.movimientos_de(nuevo)
        self.assertEqual(
            (movimiento.tipo_movimiento, movimiento.cantidad, movimiento.motivo_ajuste, movimiento.descripcion_ajuste),
            (Mov.AJUSTE_POSITIVO, D("6"), "otro", "Donación de otro vivero"),
        )
        self.assertEqual(resultado.stock_actual, D("36"))
        self.invariantes()

    def test_extension_7e_otro_que_suma_no_toca_el_faltante_sin_lote(self):
        """Diferencia n.º 2: un «otro» que suma no cancela el faltante."""
        falta = faltante(self.iin, 3)
        self.confirmar(OTRO, {"sentido": "suma", "descripcion": "x", "cantidad": "6", "vencimiento": self.vence})
        self.assertEqual(self.disponible(falta), D("-3"))

    def test_extension_7e_otro_que_resta_descuenta_de_un_lote_con_su_descripcion(self):
        """Extensión 7e → 7b: «ajuste negativo / otro» con la descripción."""
        self.confirmar(OTRO, {"sentido": "resta", "descripcion": "Derrame en el pasillo", "lote_id": self.l1.pk, "cantidad": "2"})
        self.assertEqual(self.disponible(self.l1), D("8"))
        [movimiento] = self.movimientos_de(self.l1, Mov.AJUSTE_NEGATIVO)
        self.assertEqual((movimiento.motivo_ajuste, movimiento.descripcion_ajuste), ("otro", "Derrame en el pasillo"))
        self.invariantes()

    # ---- postcondiciones k, l y m para cada motivo ----

    def test_post_k_l_y_m_todo_motivo_audita_un_registro_con_su_motivo_y_sus_movimientos(self):
        """Postcondiciones k, l y m: un registro por ajuste, con el motivo (``datos.motivo_ajuste``) y los movimientos creados."""
        self.preparar_vencidos()
        casos = [
            (RECUENTO, {"contados": {self.l1.pk: "8"}}),
            (CARGA_INICIAL, {"cantidad": "3", "vencimiento": self.vence}),
            (ROTURA, {"lote_id": self.l2.pk, "cantidad": "1"}),
            (VENCIMIENTO, {"lotes": [self.v1.pk]}),
            (CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "1"}),
            (OTRO, {"sentido": "resta", "descripcion": "x", "lote_id": self.l2.pk, "cantidad": "1"}),
        ]
        for n, (motivo, entrada) in enumerate(casos, start=1):
            with self.subTest(motivo=motivo):
                resultado = self.confirmar(motivo, entrada)
                self.assertEqual(RegistroAuditoria.objects.filter(accion=AJUSTE).count(), n)
                datos = RegistroAuditoria.objects.filter(accion=AJUSTE).latest("id").detalle["datos"]
                self.assertEqual(datos["motivo_ajuste"], motivo)
                self.assertEqual({r["id"] for r in datos["movimientos"]}, {m.pk for m in resultado.movimientos})
        self.invariantes()

    def test_post_k_el_cambio_de_stock_de_una_suma_y_de_una_resta_va_como_texto(self):
        """D-36: ``cambios.stock`` con antes y después, con los decimales de la unidad."""
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual(
            RegistroAuditoria.objects.get(accion=AJUSTE).detalle["cambios"], {"stock": {"antes": "30.000", "despues": "26.000"}}
        )

    def test_regla_8_19_1_cada_lote_que_cambia_tiene_exactamente_un_movimiento_en_cada_motivo(self):
        """Regla 1 de 8.19: todo cambio de cantidad genera exactamente un movimiento; la suma de los movimientos explica cada lote."""
        self.preparar_vencidos()
        antes = MovimientoInsumo.objects.count()
        self.confirmar(VENCIMIENTO, {"lotes": [self.v1.pk, self.v2.pk]})
        self.assertEqual(MovimientoInsumo.objects.count() - antes, 2)
        antes = MovimientoInsumo.objects.count()
        self.confirmar(CORRECCION, {"origen_id": self.l1.pk, "destino_id": self.l2.pk, "cantidad": "1"})
        self.assertEqual(MovimientoInsumo.objects.count() - antes, 2)
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=self.iin, es_faltante_sin_lote=True).count(), 0)
        self.invariantes()
