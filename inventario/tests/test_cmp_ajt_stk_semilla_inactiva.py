# Pruebas de CMP-AJT-STK con una semilla dada de baja con su variedad (docs/casos_de_uso/inventario/ajuste_de_stock.md, «Cómo se aplica en la ronda»:
# «Semilla de una variedad dada de baja (lote 3)»; docs/modelo/inventario.md, «Diferencias con el caso de uso», n.º 6; docs/patrones/stock.md, sección 4;
# INV-02, paso 6).
#
# PROD-BAJ-VAR (regla 3) deja INACTIVA a la semilla pero NO deshabilita sus existencias: el stock que queda sigue registrado y se descarta con un ajuste.
# Por eso el paso 4 del CU ofrece las existencias ACTIVAS del invernadero aunque su insumo del catálogo esté inactivo. Es la única excepción a «el insumo
# inactivo no tiene existencias activas» y solo les pasa a las semillas. Con el insumo inactivo no se crea la alerta «bajo el mínimo» y se resuelve la
# que hubiera. Una existencia inactiva (ya deshabilitada) no se ajusta.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase

from inventario.models import Insumo, InsumoInvernadero
from inventario.tests.ajustes_comunes import RECUENTO, ROTURA, VENCIMIENTO, BaseDeAjustes, ajustes
from inventario.tests.fabricas import categoria_del_sistema, existencia, insumo, lote, perezoso
from maestros.models import Alerta
from maestros.tests.fabricas import codigos_de, error_de

iin_servicio = perezoso("inventario.servicios.insumos_invernadero")
D = Decimal
BAJO_MINIMO = "inv_insumo_bajo_minimo"


class CmpAjtStkSemillaInactivaTests(BaseDeAjustes, TestCase):
    def setUp(self):
        self.preparar()
        self.semilla = insumo(
            "Semilla de lechuga", tipo=categoria_del_sistema("semillas"), unidad="unidad", controla_vencimiento=True
        )
        self.iin_semilla = existencia(self.semilla, self.invernadero, minimo=5, precio="3")
        self.stock = lote(self.iin_semilla, 20, vence=self.vence)
        # La variedad se da de baja: la semilla queda inactiva y su existencia, activa (regla 3 de PROD-BAJ-VAR).
        Insumo.objects.filter(pk=self.semilla.pk).update(estado_insumo="inactivo")

    def ajustar(self, motivo, entrada, huella=None):
        return self.confirmar(motivo, entrada, huella=huella, iin=self.iin_semilla)

    def test_paso_4_las_existencias_activas_de_una_semilla_inactiva_se_ofrecen_para_ajustar(self):
        """Paso 4: el Sistema ofrece las existencias activas del invernadero aunque el insumo del catálogo esté inactivo."""
        self.assertIn(self.iin_semilla.pk, [i.pk for i in iin_servicio.habilitados(self.invernadero.pk)])
        situacion = ajustes.situacion_del_insumo(self.agronomo, self.invernadero.pk, self.semilla.pk)
        self.assertEqual((situacion.stock_actual, situacion.iin.pk), (D("20"), self.iin_semilla.pk))

    def test_paso_4_el_ajuste_se_calcula_sobre_una_semilla_inactiva(self):
        """El cálculo no exige que el insumo del catálogo esté activo."""
        r = self.calcular(ROTURA, {"lote_id": self.stock.pk, "cantidad": "20"}, iin=self.iin_semilla)
        self.assertEqual((r.stock_antes, r.stock_despues, r.valor), (D("20"), D("0"), D("-60.00")))

    def test_regla_3_de_baj_var_el_stock_que_queda_se_descarta_con_un_ajuste(self):
        """Regla 3 de PROD-BAJ-VAR: «su stock, si queda, se descarta con un ajuste»: una rotura o pérdida lo lleva a cero."""
        resultado = self.ajustar(ROTURA, {"lote_id": self.stock.pk, "cantidad": "20", "descripcion": "Descarte por baja de la variedad"})
        self.assertEqual((resultado.stock_actual, self.disponible(self.stock)), (D("0"), D("0")))
        self.invariantes(self.iin_semilla)

    def test_regla_3_de_baj_var_se_descartan_tambien_con_un_recuento_a_cero(self):
        """Un recuento físico en cero también regulariza."""
        self.ajustar(RECUENTO, {"contados": {self.stock.pk: "0"}})
        self.assertEqual(self.disponible(self.stock), D("0"))

    def test_regla_3_de_baj_var_se_dan_de_baja_los_lotes_vencidos_de_una_semilla_inactiva(self):
        """La baja por vencimiento también funciona con la existencia de una semilla inactiva."""
        viejo = lote(self.iin_semilla, 4, vence=self.vencido)
        self.ajustar(VENCIMIENTO, {"lotes": [viejo.pk]})
        self.assertEqual(self.disponible(viejo), D("0"))

    def test_post_j_con_el_insumo_inactivo_no_se_crea_la_alerta_bajo_el_minimo(self):
        """Sección 4 de docs/patrones/stock.md: la alerta «bajo el mínimo» solo se crea si el insumo del catálogo está activo; descartar casi
        todo el stock (quedan 2 < mínimo 5) no la crea."""
        resultado = self.ajustar(ROTURA, {"lote_id": self.stock.pk, "cantidad": "18"})
        self.assertEqual(Alerta.objects.filter(tipo_alerta=BAJO_MINIMO).count(), 0)
        self.assertEqual([a for a in resultado.alertas_creadas if a.tipo_alerta == BAJO_MINIMO], [])

    def test_post_j_con_el_insumo_inactivo_se_resuelve_la_alerta_bajo_el_minimo_que_hubiera(self):
        """Una alerta «bajo el mínimo» previa se resuelve al ajustar: el insumo ya no se repone."""
        Alerta.objects.create(
            invernadero=self.invernadero, tipo_alerta=BAJO_MINIMO, descripcion_alerta="x", nivel_severidad="advertencia",
            agronomo=self.agronomo, clave_estado=f"insumo:{self.iin_semilla.pk}",
        )
        resultado = self.ajustar(ROTURA, {"lote_id": self.stock.pk, "cantidad": "1"})
        self.assertEqual([a.tipo_alerta for a in resultado.alertas_resueltas], [BAJO_MINIMO])

    def test_extension_4a_una_existencia_inactiva_de_una_semilla_inactiva_no_se_ajusta(self):
        """Solo las existencias ACTIVAS: si ya se deshabilitó, no se ofrece (extensión 4a: habría que habilitarla, y el insumo está inactivo)."""
        InsumoInvernadero.objects.filter(pk=self.iin_semilla.pk).update(estado_insumo_invernadero="inactivo")
        self.assertNotIn(self.iin_semilla.pk, [i.pk for i in iin_servicio.habilitados(self.invernadero.pk)])
        error = error_de(lambda: self.calcular(ROTURA, {"lote_id": self.stock.pk, "cantidad": "1"}, iin=self.iin_semilla))
        self.assertEqual(codigos_de(error), ["insumo_no_habilitado"])

    def test_la_semilla_inactiva_figura_en_las_existencias_mientras_su_existencia_siga_activa(self):
        """CMP-CNS-IIN: los insumos habilitados (existencia activa) del invernadero; el estado del insumo del catálogo no la oculta."""
        filas = iin_servicio.consultar_existencias(self.agronomo)
        self.assertIn(self.iin_semilla.pk, [f.iin.pk for f in filas])

    def test_el_ajuste_de_una_semilla_inactiva_audita_como_cualquier_otro(self):
        """Postcondiciones k a m: el mismo registro ``ajuste_stock``, con la semilla como insumo."""
        from core.models import RegistroAuditoria

        self.ajustar(ROTURA, {"lote_id": self.stock.pk, "cantidad": "20"})
        registro = RegistroAuditoria.objects.get(accion=RegistroAuditoria.Accion.AJUSTE_STOCK)
        self.assertEqual(registro.detalle["datos"]["insumo"]["texto"], "Semilla de lechuga")
        self.assertEqual(registro.detalle["cambios"], {"stock": {"antes": "20", "despues": "0"}})
