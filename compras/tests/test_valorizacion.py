# Pruebas de la valorización de lo recibido y de lo pagado (CMP-05, paso 3). Fuente: docs/decisiones/D-89.md (punto 4: «la cuenta Proveedores de cada proveedor y orden queda exactamente en cero después del
# pago, sin diferencias de redondeo, aunque la línea se haya recibido en varias partes»), D-91 punto 1, docs/casos_de_uso/compras/pagos.md («Cómo se aplica», tabla de pruebas: «Proveedores en cero
# después del pago (con recepciones parciales) y ``verificar_invariantes_contables``»). El archivo lo crea esta tarea: la documentación decía que ``test_valorizacion.py`` «lo amplía», pero no existía.
#
# «Proveedores de un par» (orden, proveedor) = Haber de los asientos de sus recepciones menos Debe del asiento de su pago, todo sobre la cuenta 2.1.01.


from django.db.models import Sum

from compras.models import Pago, Recepcion
from compras.tests.base_pagos import D, PagosBase
from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import MovimientoContable
from contabilidad.servicios import libro
from contabilidad.tests.fabricas import verificar_invariantes_contables


class ValorizacionTests(PagosBase):
    """La deuda con cada proveedor de una orden nace al recibir y se cancela, por el mismo monto exacto, al pagar."""

    def proveedores_del_par(self, orden, proveedor):
        """Σ Haber (recepciones del par) − Σ Debe (pago del par) sobre Proveedores: lo que todavía se le debe a ese proveedor por esa orden."""
        origenes_de_recepciones = list(Recepcion.objects.filter(orden=orden, proveedor=proveedor).values_list("pk", flat=True))
        origenes_de_pagos = list(Pago.objects.filter(orden=orden, proveedor=proveedor).values_list("pk", flat=True))

        def suma(origenes, tipo):
            return (
                MovimientoContable.objects.filter(
                    cuenta__codigo_cuenta=cuentas.PROVEEDORES, tipo_movimiento=tipo, asiento__origen_id__in=origenes
                ).aggregate(total=Sum("importe_movimiento"))["total"]
                or D("0.00")
            )

        return suma(origenes_de_recepciones, HABER) - suma(origenes_de_pagos, DEBE)

    def test_d89_punto_4_tres_recepciones_parciales_de_una_linea_con_redondeo_dejan_proveedores_en_cero_al_pagar(self):
        """D-89 punto 4: una línea de 3 unidades a $100,00 (unitario $33,3333) recibida de a una: las recepciones asientan $33,33, $33,34 y $33,33 (por diferencia del acumulado), suman $100,00 exactos y el pago de
        $100,00 deja la cuenta en cero, sin el centavo colgado."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, "Sustrato", cantidad=3, total="100.00", n=5)
        proveedor = linea.proveedor
        recepciones_hechas = [self.registrar(self.ana, [self.linea(linea, 1)], orden=orden, proveedor=proveedor) for _ in range(3)]
        importes = [self.movimientos_de(self.asiento_de(r))[0][2] for r in recepciones_hechas]
        self.assertEqual(importes, [D("33.33"), D("33.34"), D("33.33")])
        self.assertEqual(self.proveedores_del_par(orden, proveedor), D("100.00"))
        pago = self.pagar(orden=orden, proveedor=proveedor)
        self.assertEqual(pago.monto_pago, D("100.00"))
        self.assertEqual(self.proveedores_del_par(orden, proveedor), D("0.00"))
        verificar_invariantes_contables()

    def test_d89_punto_4_con_una_recepcion_parcial_y_el_resto_cerrado_con_faltante_el_pago_cancela_lo_recibido(self):
        """D-89 punto 4: 4 de 10 del Fertilizante (cerrado con faltante) y 20 de 20 de la Maceta: se asentó $240,00 al recibir y se paga $240,00: queda en cero."""
        self.recibir_a_con_faltante()
        self.assertEqual(self.proveedores_del_par(self.orden, self.proveedor), D("240.00"))
        self.pagar()
        self.assertEqual(self.proveedores_del_par(self.orden, self.proveedor), D("0.00"))
        verificar_invariantes_contables()

    def test_d89_punto_4_pagar_a_un_proveedor_no_mueve_la_cuenta_del_otro_de_la_misma_orden(self):
        """Cada par se cancela solo: pagado A ($300,00), B ($80,00) sigue debiéndose; y el saldo total de Proveedores en el libro es lo que falta pagar."""
        self.recibir_a()
        self.recibir_b()
        self.pagar()
        self.assertEqual(self.proveedores_del_par(self.orden, self.proveedor), D("0.00"))
        self.assertEqual(self.proveedores_del_par(self.orden, self.proveedor_b), D("80.00"))
        self.assertEqual(libro.saldo_por_cuenta(self.abierto.pk)[cuentas.PROVEEDORES].saldo, D("80.00"))
        self.pagar(proveedor=self.proveedor_b, medio="efectivo")
        self.assertEqual(libro.saldo_por_cuenta(self.abierto.pk)[cuentas.PROVEEDORES].saldo, D("0.00"))
        verificar_invariantes_contables()

    def test_d89_punto_4_el_monto_del_pago_es_el_de_valor_recibido_del_acumulado_final_y_no_la_suma_de_los_asientos_redondeados(self):
        """D-89 punto 4: ``monto_pago`` = Σ ``valor_recibido(acumulado final)``. Con recepciones de 1, 1 y 1 de 3 el pago es el total exacto, que coincide con la suma de los asientos (no al revés)."""
        orden, linea, _ = self.otra_orden(self.ana, self.norte, "Sustrato", cantidad=3, total="100.00", n=5)
        for _ in range(3):
            self.registrar(self.ana, [self.linea(linea, 1)], orden=orden, proveedor=linea.proveedor)
        pago = self.pagar(orden=orden, proveedor=linea.proveedor, medio="efectivo")
        haber_de_recepciones = MovimientoContable.objects.filter(
            cuenta__codigo_cuenta=cuentas.PROVEEDORES, tipo_movimiento=HABER, asiento__origen_id__in=list(Recepcion.objects.filter(orden=orden).values_list("pk", flat=True))
        ).aggregate(total=Sum("importe_movimiento"))["total"]
        self.assertEqual((pago.monto_pago, haber_de_recepciones), (D("100.00"), D("100.00")))
