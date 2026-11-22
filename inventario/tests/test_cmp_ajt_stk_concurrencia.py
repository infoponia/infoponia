# Pruebas de CMP-AJT-STK · concurrencia y la extensión 14a (docs/casos_de_uso/inventario/ajuste_de_stock.md: «Requisitos especiales» y extensión 14a;
# docs/patrones/stock.md, sección 5; INV-02, paso 6). El contrato del servicio, en ``inventario/tests/ajustes_comunes.py``.
#
# Dos pasos y una confirmación: ``calcular_ajuste`` devuelve la «huella» del estado que usó (las cantidades disponibles de los lotes que usó, el
# faltante si lo usó, y las RESERVAS activas del insumo: cambian el stock libre y la cobertura); ``confirmar_ajuste`` bloquea (invernadero → existencia →
# lotes), recalcula y, si la huella ya no coincide, lanza ``AjusteDesactualizado`` (extensión 14a): no cambia nada y trae lo vigente en ``.vigente``
# (``{"lotes": {lote_id: disponible}, "reservado": Decimal}``) para que la pantalla vuelva al paso con los valores de ahora. Los bloqueos impiden que
# un ajuste y un consumo simultáneos dejen un lote común negativo o descuenten dos veces lo mismo.

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, TransactionTestCase, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.ajustes_comunes import RECUENTO, ROTURA, BaseDeAjustes, ajustes
from inventario.tests.fabricas import (
    asegurar_datos_de_inventario,
    lote,
    origen_falso,
    perezoso,
    reservas_de_prueba,
)
from inventario.tests.test_salida_por_consumo import consumo_simulado
from maestros.tests.fabricas import asegurar_datos_de_maestros

stock = perezoso("inventario.servicios.stock")
D = Decimal
AJUSTE = RegistroAuditoria.Accion.AJUSTE_STOCK
CONSUMO = MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO


class CmpAjtStkDesactualizadoTests(BaseDeAjustes, TestCase):
    """Extensión 14a: entre la carga y la confirmación otra operación cambió lo que el ajuste usó."""

    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.l2 = lote(self.iin, 20, vence=self.vence + timedelta(days=30))
        self.origen = origen_falso()

    def consumir(self, un_lote, cantidad):
        stock.registrar_salida_por_consumo(self.iin.pk, [(un_lote.pk, D(cantidad))], origen_id=self.origen.pk)

    def estado(self):
        return (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count())

    def test_extension_14a_un_consumo_que_cambia_un_lote_indicado_desactualiza_el_ajuste_y_no_cambia_nada(self):
        """Extensión 14a: otra operación cambió la cantidad disponible de un lote indicado: el Sistema no registra ningún cambio."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "4"}
        huella = self.calcular(ROTURA, entrada).huella
        self.consumir(self.l1, "7")
        antes = self.estado()
        with self.assertRaises(ajustes.AjusteDesactualizado) as contexto:
            self.confirmar(ROTURA, entrada, huella=huella)
        self.assertEqual(self.estado(), antes)
        self.assertEqual(self.disponible(self.l1), D("3"))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento="ajuste_negativo", motivo_ajuste="rotura_o_perdida").count(), 0)
        self.assertEqual(contexto.exception.vigente["lotes"][self.l1.pk], D("3"))

    def test_extension_14a_trae_lo_vigente_para_volver_al_paso_con_los_valores_de_ahora(self):
        """Extensión 14a.2: la pantalla vuelve al paso con los valores vigentes: se vuelve a calcular y se confirma con la huella nueva."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "2"}
        huella = self.calcular(ROTURA, entrada).huella
        self.consumir(self.l1, "7")
        with self.assertRaises(ajustes.AjusteDesactualizado):
            self.confirmar(ROTURA, entrada, huella=huella)
        nuevo = self.calcular(ROTURA, entrada)
        self.assertEqual(nuevo.lotes[0].registrada, D("3"))
        self.confirmar(ROTURA, entrada, huella=nuevo.huella)
        self.assertEqual(self.disponible(self.l1), D("1"))
        self.invariantes()

    def test_extension_14a_el_recuento_se_desactualiza_si_aparece_un_faltante_sin_lote(self):
        """Extensión 14a: «o el faltante sin lote»: un consumo que crea el faltante después de cargar el recuento lo invalida (el recuento
        usa todos los lotes y el faltante)."""
        huella = self.calcular(RECUENTO, {"contados": {self.l1.pk: "8"}}).huella
        self.consumir(self.l2, "25")  # 20 disponibles: faltan 5
        with self.assertRaises(ajustes.AjusteDesactualizado):
            self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}}, huella=huella)
        self.assertEqual(self.disponible(self.l1), D("10"))

    def test_extension_14a_un_faltante_que_crece_desactualiza_un_recuento_que_ya_lo_contemplaba(self):
        """El faltante que ya existía cambia de cantidad: la huella no coincide."""
        self.consumir(self.l2, "25")
        huella = self.calcular(RECUENTO, {}).huella
        self.consumir(self.l1, "12")
        with self.assertRaises(ajustes.AjusteDesactualizado):
            self.confirmar(RECUENTO, {}, huella=huella)

    def test_extension_14a_un_cambio_en_las_reservas_activas_desactualiza_el_ajuste(self):
        """La huella incluye las reservas activas (cambian el stock libre y la cobertura): si cambian entre calcular y confirmar, 14a."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "4"}
        with reservas_de_prueba(reservado={self.iin.pk: "2"}):
            huella = self.calcular(ROTURA, entrada).huella
        with reservas_de_prueba(reservado={self.iin.pk: "5"}):
            antes = self.estado()
            with self.assertRaises(ajustes.AjusteDesactualizado) as contexto:
                self.confirmar(ROTURA, entrada, huella=huella)
        self.assertEqual(contexto.exception.vigente["reservado"], D("5"))
        self.assertEqual(self.estado(), antes)

    def test_extension_14a_con_las_mismas_reservas_el_ajuste_se_confirma(self):
        """Si las reservas no cambiaron, no hay nada que avisar."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "4"}
        with reservas_de_prueba(reservado={self.iin.pk: "2"}):
            huella = self.calcular(ROTURA, entrada).huella
            self.confirmar(ROTURA, entrada, huella=huella)
        self.assertEqual(self.disponible(self.l1), D("6"))

    def test_extension_14a_las_reservas_que_aparecen_o_desaparecen_tambien_desactualizan(self):
        """De 0 a algo (o de algo a 0) es un cambio."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "4"}
        huella = self.calcular(ROTURA, entrada).huella
        with reservas_de_prueba(reservado={self.iin.pk: "1"}), self.assertRaises(ajustes.AjusteDesactualizado):
            self.confirmar(ROTURA, entrada, huella=huella)

    def test_extension_14a_un_cambio_en_un_lote_que_el_ajuste_no_uso_no_lo_desactualiza(self):
        """La huella lleva «los lotes que usó»: una rotura en el lote 1 no se invalida porque otro consumo toque el lote 2."""
        entrada = {"lote_id": self.l1.pk, "cantidad": "4"}
        huella = self.calcular(ROTURA, entrada).huella
        self.consumir(self.l2, "5")
        self.confirmar(ROTURA, entrada, huella=huella)
        self.assertEqual((self.disponible(self.l1), self.disponible(self.l2)), (D("6"), D("15")))
        self.invariantes()

    def test_extension_14a_la_huella_de_un_ajuste_sin_cambios_confirma_normalmente(self):
        """Sin operaciones en el medio, la huella coincide."""
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual(self.disponible(self.l1), D("6"))


@tag("concurrencia")
class CmpAjtStkConcurrenciaTests(BaseDeAjustes, TransactionTestCase):
    """Requisito especial: «El control de concurrencia impide que un ajuste y un consumo simultáneos sobre el mismo insumo dejen un lote con
    cantidad negativa o descuenten dos veces lo mismo». Bloqueos: invernadero → existencia → lotes (docs/patrones/stock.md, sección 5)."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.preparar(geografia_propia=True)
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.origen = origen_falso()

    def ajuste(self, huella, cantidad="4"):
        return lambda: self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": cantidad}, huella=huella)

    def huella(self, cantidad="4"):
        return self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": cantidad}).huella

    def test_requisito_especial_ajuste_primero_y_consumo_despues_no_dejan_un_lote_negativo(self):
        """El ajuste va primero; el consumo espera el invernadero, relee el lote ya descontado (6), toma lo que queda y manda el resto
        al faltante: nunca un lote común negativo ni lo mismo descontado dos veces."""
        resultados = correr_a_la_vez(
            self.ajuste(self.huella()),
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.l1.pk, D("7"))], self.origen),
            primera="a",
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(self.disponible(self.l1), D("0"))
        falta = LoteInsumo.objects.get(insumo_invernadero=self.iin, es_faltante_sin_lote=True)
        self.assertEqual(falta.cantidad_disponible, D("-1"))
        self.invariantes()

    def test_extension_14a_consumo_primero_y_ajuste_despues_el_ajuste_se_rechaza_como_desactualizado(self):
        """El consumo va primero y confirma; el ajuste espera, recalcula, ve el lote en 3 y lanza ``AjusteDesactualizado`` sin cambiar nada
        (nunca un 500 ni un lote negativo)."""
        resultados = correr_a_la_vez(
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.l1.pk, D("7"))], self.origen),
            self.ajuste(self.huella()),
            primera="a",
        )
        self.assertIsInstance(resultados["b"], ajustes.AjusteDesactualizado)
        self.assertNotIsInstance(resultados["a"], Exception)
        self.assertEqual(self.disponible(self.l1), D("3"))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento="ajuste_negativo", motivo_ajuste="rotura_o_perdida").count(), 0)
        self.invariantes()

    def test_requisito_especial_dos_ajustes_iguales_a_la_vez_solo_uno_se_aplica(self):
        """Dos ajustes calculados sobre el mismo estado: el primero se aplica; el segundo espera, ve la huella vieja y se rechaza como
        desactualizado. El lote queda en 3 (no −4, ni descontado dos veces) y hay un solo registro de auditoría."""
        huella = self.huella("7")
        resultados = correr_a_la_vez(self.ajuste(huella, "7"), self.ajuste(huella, "7"), primera="a")
        self.assertNotIsInstance(resultados["a"], Exception)
        self.assertIsInstance(resultados["b"], ajustes.AjusteDesactualizado)
        self.assertEqual(self.disponible(self.l1), D("3"))
        self.assertEqual(RegistroAuditoria.objects.filter(accion=AJUSTE).count(), 1)
        self.invariantes()

    def test_extension_14a_el_ajuste_rechazado_trae_lo_vigente_con_lo_que_dejo_el_primero(self):
        """``AjusteDesactualizado.vigente`` trae lo que hay ahora, para que la pantalla vuelva al paso con esos valores."""
        huella = self.huella("7")
        resultados = correr_a_la_vez(self.ajuste(huella, "7"), self.ajuste(huella, "7"), primera="a")
        self.assertEqual(resultados["b"].vigente["lotes"][self.l1.pk], D("3"))
