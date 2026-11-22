# Pruebas de CMP-AJT-STK · las alertas (docs/casos_de_uso/inventario/ajuste_de_stock.md: postcondiciones h, i, j y m; extensión 12b; paso 15;
# docs/patrones/stock.md, secciones 1 y 4; INV-02, paso 6). El contrato del servicio, en ``inventario/tests/ajustes_comunes.py``.
#
# «Stock inconsistente» mide el stock SIN lotes vencidos (manda el CU, L7): vigente(hoy) < reservado. Un ajuste que lo deja así no se bloquea: se
# registra y deja la alerta activa (12b y post i); uno que vuelve a cubrir las reservas la resuelve (post h). El resultado informa, en el paso 15,
# si «stock inconsistente» se resolvió (``"resuelta"``), sigue activa (``"activa"``) o nunca estuvo (``None``). Las reservas las informa
# `produccion` por el punto de extensión (aquí, ``reservas_de_prueba``).

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.test import TestCase

from core.models import RegistroAuditoria
from inventario.extensiones import OrdenQueReserva
from inventario.models import InsumoInvernadero, MovimientoInsumo
from inventario.tests.ajustes_comunes import CARGA_INICIAL, RECUENTO, ROTURA, VENCIMIENTO, BaseDeAjustes
from inventario.tests.fabricas import faltante, lote, perezoso, reservas_de_prueba
from maestros.models import Alerta
from maestros.tests.fabricas import crear_alerta

alertas_de_stock = perezoso("inventario.servicios.alertas_de_stock")
D = Decimal
AJUSTE = RegistroAuditoria.Accion.AJUSTE_STOCK
INCONSISTENTE = "inv_stock_inconsistente"
BAJO_MINIMO = "inv_insumo_bajo_minimo"
VENCIDO = "inv_insumo_vencido"


class CmpAjtStkAlertasTests(BaseDeAjustes, TestCase):
    def setUp(self):
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)

    def reevaluar(self):
        with transaction.atomic():
            return alertas_de_stock.reevaluar_alertas_del_insumo(self.iin.pk)

    def activas(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo, clave_estado=f"insumo:{self.iin.pk}", estado_alerta="activa")

    def orden(self, numero, cantidad, dias=1):
        return OrdenQueReserva(numero, f"Siembra {numero}", D(cantidad), self.hoy + timedelta(days=dias), f"/o/{numero}")

    # ---- postcondición h: se resuelve ----

    def test_post_h_un_recuento_que_regulariza_el_faltante_resuelve_la_alerta_stock_inconsistente(self):
        """Postcondición h: si después del ajuste el stock sin lotes vencidos es >= 0 y >= las reservas, la alerta activa pasa a «resuelta»
        con su fecha de resolución."""
        faltante(self.iin, 15)
        self.reevaluar()
        self.assertEqual(self.activas(INCONSISTENTE).count(), 1)
        resultado = self.confirmar(RECUENTO, {})
        alerta = Alerta.objects.get(tipo_alerta=INCONSISTENTE)
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIsNotNone(alerta.fecha_resolucion)
        self.assertEqual(resultado.inconsistente, "resuelta")
        self.assertIn(alerta.pk, [a.pk for a in resultado.alertas_resueltas])

    def test_post_h_cargar_stock_que_vuelve_a_cubrir_las_reservas_resuelve_la_alerta(self):
        """Postcondición h con reservas: el stock vigente vuelve a ser mayor o igual que la suma de las reservas activas."""
        with reservas_de_prueba(reservado={self.iin.pk: "15"}, ordenes={self.iin.pk: [self.orden(1, "15")]}):
            self.reevaluar()
            self.assertEqual(self.activas(INCONSISTENTE).count(), 1)
            resultado = self.confirmar(CARGA_INICIAL, {"cantidad": "10", "vencimiento": self.vence})
        self.assertEqual(resultado.inconsistente, "resuelta")
        self.assertEqual(self.activas(INCONSISTENTE).count(), 0)

    # ---- postcondición i y extensión 12b: queda o se crea ----

    def test_post_i_un_ajuste_que_deja_el_stock_sin_cubrir_las_reservas_deja_la_alerta_activa(self):
        """Postcondición i: si queda menor que la suma de las reservas activas, existe una alerta activa que identifica el insumo y las
        órdenes sin cobertura; el ajuste NO se bloquea."""
        ordenes = [self.orden(1, "4"), self.orden(2, "4", dias=5)]
        with reservas_de_prueba(reservado={self.iin.pk: "8"}, ordenes={self.iin.pk: ordenes}):
            resultado = self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"})
        self.assertEqual(self.disponible(self.l1), D("5"))
        alerta = self.activas(INCONSISTENTE).get()
        self.assertEqual(resultado.inconsistente, "activa")
        self.assertIn("Nutriente A", alerta.descripcion_alerta)
        self.assertIn("Siembra 2", alerta.descripcion_alerta)  # la 1 (4) queda cubierta con 5; la 2 no
        self.assertNotIn("Siembra 1", alerta.descripcion_alerta)
        self.assertEqual([a.pk for a in resultado.alertas_creadas if a.tipo_alerta == INCONSISTENTE], [alerta.pk])

    def test_post_i_si_la_alerta_ya_estaba_activa_sigue_activa_sin_duplicarse(self):
        """Postcondición i: sigue activa mientras el stock no cubra; no se crea otra."""
        faltante(self.iin, 15)
        self.reevaluar()
        resultado = self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"})
        self.assertEqual(self.activas(INCONSISTENTE).count(), 1)
        self.assertEqual(resultado.inconsistente, "activa")
        self.assertEqual([a for a in resultado.alertas_creadas if a.tipo_alerta == INCONSISTENTE], [])

    def test_extension_12b_el_resumen_advierte_las_ordenes_sin_cobertura_sin_bloquear(self):
        """Extensión 12b: junto con el resumen, advierte qué órdenes quedarían sin cobertura y que la alerta seguirá activa; no bloquea."""
        ordenes = [self.orden(1, "4"), self.orden(2, "4", dias=5)]
        with reservas_de_prueba(reservado={self.iin.pk: "8"}, ordenes={self.iin.pk: ordenes}):
            r = self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"})
        self.assertEqual([o.orden_id for o in r.advertencia.ordenes], [2])
        self.assertEqual((r.advertencia.stock_vigente, r.advertencia.reservado), (D("5"), D("8")))

    def test_extension_12b_un_ajuste_que_cubre_las_reservas_no_advierte_nada(self):
        """Sin la condición de 12b, ``advertencia`` es ``None``."""
        with reservas_de_prueba(reservado={self.iin.pk: "4"}, ordenes={self.iin.pk: [self.orden(1, "4")]}):
            self.assertIsNone(self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"}).advertencia)

    def test_extension_12b_el_stock_que_quedaria_negativo_tambien_advierte(self):
        """Extensión 12b: «negativo o menor que la suma de sus reservas activas»: un faltante que sigue ahí deja el stock vigente negativo."""
        faltante(self.iin, 20)
        r = self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"})
        self.assertIsNotNone(r.advertencia)
        self.assertLess(r.advertencia.stock_vigente, D("0"))

    def test_extension_12b_se_mide_sin_los_lotes_vencidos(self):
        """Manda el CU (L7): un lote vencido no cubre reservas; con 10 vigentes y 8 reservados, descontar 5 deja 5 < 8 aunque haya un
        vencido grande."""
        lote(self.iin, 100, vence=self.vencido)
        with reservas_de_prueba(reservado={self.iin.pk: "8"}, ordenes={self.iin.pk: [self.orden(1, "8")]}):
            r = self.calcular(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"})
        self.assertEqual(r.advertencia.stock_vigente, D("5"))

    # ---- postcondición j: vencimiento y bajo el mínimo ----

    def test_post_j_dar_de_baja_un_lote_vencido_resuelve_su_alerta_de_vencido(self):
        """Postcondición j: las alertas de vencimiento de los lotes dados de baja pasan a «resuelta» y van en los datos de la auditoría."""
        vencido = lote(self.iin, 5, vence=self.vencido)
        alerta = crear_alerta(
            self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{vencido.pk}"
        )
        resultado = self.confirmar(VENCIMIENTO, {"lotes": [vencido.pk]})
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertIn(alerta.pk, [a.pk for a in resultado.alertas_resueltas])
        datos = RegistroAuditoria.objects.get(accion=AJUSTE).detalle["datos"]
        self.assertIn(alerta.pk, [r["id"] for r in datos["alertas_resueltas"]])

    def test_post_j_la_baja_de_un_lote_no_resuelve_las_alertas_de_otros_lotes(self):
        """Solo las de los lotes que quedaron en cero."""
        uno = lote(self.iin, 5, vence=self.vencido)
        otro = lote(self.iin, 6, vence=self.vencido - timedelta(days=2))
        a_uno = crear_alerta(self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{uno.pk}")
        a_otro = crear_alerta(self.invernadero, VENCIDO, para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{otro.pk}")
        self.confirmar(VENCIMIENTO, {"lotes": [uno.pk]})
        a_uno.refresh_from_db()
        a_otro.refresh_from_db()
        self.assertEqual((a_uno.estado_alerta, a_otro.estado_alerta), ("resuelta", "activa"))

    def test_post_j_se_reevalua_la_alerta_bajo_el_minimo_y_se_crea_si_el_ajuste_lo_baja(self):
        """Postcondición j: se reevalúa el stock bajo el mínimo: una rotura que deja el libre por debajo del mínimo genera la alerta."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D("8"))
        resultado = self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"})
        alerta = self.activas(BAJO_MINIMO).get()
        self.assertEqual(alerta.agronomo_id, self.agronomo.pk)
        self.assertIn(alerta.pk, [a.pk for a in resultado.alertas_creadas])

    def test_post_j_se_reevalua_la_alerta_bajo_el_minimo_y_se_resuelve_si_el_ajuste_la_cubre(self):
        """Postcondición j: una carga inicial que sube el stock por encima del mínimo resuelve la alerta activa."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D("20"))
        self.reevaluar()
        self.assertEqual(self.activas(BAJO_MINIMO).count(), 1)
        resultado = self.confirmar(CARGA_INICIAL, {"cantidad": "15", "vencimiento": self.vence})
        self.assertEqual(self.activas(BAJO_MINIMO).count(), 0)
        self.assertEqual([a.tipo_alerta for a in resultado.alertas_resueltas], [BAJO_MINIMO])

    # ---- postcondición m y paso 15 ----

    def test_post_m_las_alertas_creadas_van_en_los_datos_de_la_auditoria(self):
        """Postcondición m (D-36): ``alertas_creadas`` con la referencia de cada alerta creada, en el mismo registro del ajuste."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(cant_min_insumo=D("8"))
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "5"})
        alerta = self.activas(BAJO_MINIMO).get()
        datos = RegistroAuditoria.objects.get(accion=AJUSTE).detalle["datos"]
        self.assertEqual([r["id"] for r in datos["alertas_creadas"]], [alerta.pk])
        self.assertNotIn("alertas_resueltas", datos)

    def test_post_m_sin_alertas_el_detalle_no_lleva_esas_claves(self):
        """docs/api/alertas.md: solo las claves que no estén vacías."""
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"})
        datos = RegistroAuditoria.objects.get(accion=AJUSTE).detalle["datos"]
        self.assertNotIn("alertas_creadas", datos)
        self.assertNotIn("alertas_resueltas", datos)

    def test_paso_15_sin_alerta_de_inconsistencia_el_resultado_no_dice_nada(self):
        """Paso 15: si nunca hubo «stock inconsistente», ``inconsistente`` es ``None``."""
        self.assertIsNone(self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"}).inconsistente)

    def test_paso_15_el_resultado_informa_el_stock_actual(self):
        """Paso 15: lo registrado y el stock actual del insumo."""
        resultado = self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "4"})
        self.assertEqual((resultado.stock_actual, len(resultado.movimientos)), (D("6"), 1))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento="ajuste_negativo").count(), 1)

    def test_post_h_e_i_las_alertas_siguen_la_destinataria_del_invernadero(self):
        """D-41: la alerta que crea el ajuste va al Agrónomo del invernadero."""
        faltante(self.iin, 15)
        self.confirmar(ROTURA, {"lote_id": self.l1.pk, "cantidad": "1"})
        alerta = self.activas(INCONSISTENTE).get()
        self.assertEqual((alerta.agronomo_id, alerta.para_gerente), (self.agronomo.pk, False))
