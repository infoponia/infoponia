# Pruebas de CMP-AJT-STK · el recuento físico por lote (docs/casos_de_uso/inventario/ajuste_de_stock.md: pasos 6 a 15, extensiones 10b y 10c,
# postcondiciones a, b, c, d, g, k, l y m, y «Cómo se aplica en la ronda»; INV-02, paso 6). El contrato del servicio está en
# ``inventario/tests/ajustes_comunes.py``.
#
# El recuento es de TODO el insumo y por lote (manda el CU, L7, no el prototipo, que cuenta un lote por vez): el Agrónomo indica solo los
# lotes que difieren (los demás quedan con su cantidad registrada), puede agregar lotes nuevos (10b) y quitarlos (10c); el faltante sin lote
# siempre queda en cero (post c). El resumen del paso 12 lleva las cinco partes: lotes que cambian, lotes nuevos, faltante que queda en cero,
# stock antes y después, y valor (cantidad × precio de referencia, sin asiento: D-45).

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase

from contabilidad import cuentas
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from core.models import RegistroAuditoria
from inventario.models import InsumoInvernadero, LoteInsumo, MovimientoInsumo
from inventario.tests.ajustes_comunes import RECUENTO, BaseDeAjustes, ajustes
from inventario.tests.fabricas import existencia, faltante, insumo, lote
from maestros.tests.fabricas import crear_agronomo
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

D = Decimal
Mov = MovimientoInsumo.TipoMovimiento
AJUSTE = RegistroAuditoria.Accion.AJUSTE_STOCK


class SituacionDelInsumoTests(BaseDeAjustes, TestCase):
    """Pasos 4 a 6 del CU: lo que la pantalla presenta antes de elegir el motivo."""

    def setUp(self):
        self.preparar()

    def situacion(self):
        return ajustes.situacion_del_insumo(self.agronomo, self.iin.invernadero_id, self.iin.insumo_id)

    def test_paso_6_presenta_stock_lotes_faltante_precio_y_vencimiento(self):
        """Paso 6: stock actual, lotes con cantidad y vencimiento, faltante sin lote, precio de referencia y si controla vencimiento."""
        con_stock = lote(self.iin, 10, vence=self.vence)
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=5)
        falta = faltante(self.iin, 2)
        s = self.situacion()
        self.assertEqual((s.stock_actual, s.precio, s.controla_vencimiento), (D("8"), D("100"), True))
        self.assertEqual(s.faltante.pk, falta.pk)
        self.assertEqual([l.lote.pk for l in s.lotes], [con_stock.pk, agotado.pk, falta.pk])

    def test_paso_6_los_lotes_con_stock_van_primero_y_por_vencimiento(self):
        """Interpretación aprobada: en el recuento se muestran todos los lotes, los que tienen stock primero (por vencimiento), después
        los agotados y por último el faltante."""
        tarde = lote(self.iin, 5, vence=self.vence + timedelta(days=30))
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=5)
        pronto = lote(self.iin, 5, vence=self.vence)
        self.assertEqual([l.lote.pk for l in self.situacion().lotes], [pronto.pk, tarde.pk, agotado.pk])

    def test_paso_6_sin_faltante_el_faltante_es_none(self):
        """Sin faltante sin lote, ``faltante`` es ``None``."""
        lote(self.iin, 3, vence=self.vence)
        self.assertIsNone(self.situacion().faltante)

    def test_paso_6_los_motivos_son_los_seis_del_cu_en_el_orden_del_prototipo(self):
        """Paso 6.6 y regla «Motivos»."""
        self.assertEqual(
            [codigo for codigo, _ in self.situacion().motivos],
            ["recuento_fisico", "rotura_o_perdida", "carga_inicial", "vencimiento", "correccion_entre_lotes", "otro"],
        )


class CmpAjtStkRecuentoTests(BaseDeAjustes, TestCase):
    """Flujo del recuento físico: calcular (paso 12) y confirmar (pasos 13 a 15)."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
        self.preparar()
        self.l1 = lote(self.iin, 10, vence=self.vence)
        self.l2 = lote(self.iin, 20, vence=self.vence + timedelta(days=30))

    # ---- calcular: el resumen del paso 12 ----

    def test_paso_12_el_resumen_trae_lo_que_cambia_el_stock_antes_y_despues_y_el_valor(self):
        """Paso 12: por cada lote que cambia, la cantidad registrada, la contada y la diferencia; stock antes y después; valor."""
        r = self.calcular(RECUENTO, {"contados": {self.l1.pk: "8"}})
        [cambio] = r.lotes
        self.assertEqual((cambio.lote.pk, cambio.registrada, cambio.contada, cambio.diferencia), (self.l1.pk, D("10"), D("8"), D("-2")))
        self.assertEqual((r.stock_antes, r.stock_despues, r.diferencia), (D("30"), D("28"), D("-2")))
        self.assertEqual((r.valor, r.con_valor), (D("-200.00"), True))
        self.assertEqual((r.lotes_nuevos, r.faltante_a_cero, r.advertencia), ([], D("0"), None))

    def test_paso_12_el_valor_es_la_diferencia_por_el_precio_de_referencia_con_dos_decimales(self):
        """Regla «Valor del ajuste»: cantidad × precio de referencia, en pesos con 2 decimales, positivo o negativo."""
        InsumoInvernadero.objects.filter(pk=self.iin.pk).update(referencia_precio=D("33.33"))
        r = self.calcular(RECUENTO, {"contados": {self.l1.pk: "12.5"}})
        self.assertEqual(r.valor, D("83.33"))  # 2.5 × 33.33 = 83.325 → 83.33

    def test_paso_12_solo_los_lotes_que_difieren_figuran_en_el_resumen(self):
        """Paso 8: el Sistema propone la cantidad registrada; un lote contado igual que lo registrado no cambia ni figura."""
        r = self.calcular(RECUENTO, {"contados": {self.l1.pk: "10", self.l2.pk: "25"}})
        self.assertEqual([c.lote.pk for c in r.lotes], [self.l2.pk])

    def test_paso_10_la_cantidad_contada_puede_ser_cero(self):
        """Regla «Cantidad válida»: en el recuento la cantidad contada puede ser cero."""
        r = self.calcular(RECUENTO, {"contados": {self.l1.pk: "0"}})
        self.assertEqual((r.lotes[0].contada, r.lotes[0].diferencia), (D("0"), D("-10")))

    def test_paso_12_calcular_no_escribe_nada(self):
        """Dos pasos: ``calcular_ajuste`` valida y calcula pero no cambia lotes, movimientos, alertas ni auditoría."""
        antes = (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count())
        self.calcular(RECUENTO, {"contados": {self.l1.pk: "8"}, "nuevos": [{"cantidad": "2", "vencimiento": self.vence}]})
        self.assertEqual(
            (LoteInsumo.objects.count(), MovimientoInsumo.objects.count(), RegistroAuditoria.objects.count()), antes
        )
        self.assertEqual(self.disponible(self.l1), D("10"))

    def test_paso_12_el_resumen_trae_los_lotes_nuevos_con_su_cantidad_y_su_vencimiento(self):
        """Extensión 10b y paso 12.2: los lotes nuevos con su cantidad y su vencimiento."""
        r = self.calcular(RECUENTO, {"nuevos": [{"cantidad": "2", "vencimiento": self.vence}]})
        [nuevo] = r.lotes_nuevos
        self.assertEqual((nuevo.cantidad, nuevo.vencimiento), (D("2"), self.vence))
        self.assertEqual((r.stock_antes, r.stock_despues, r.valor), (D("30"), D("32"), D("200.00")))

    def test_paso_12_el_faltante_sin_lote_figura_como_lo_que_queda_en_cero(self):
        """Paso 12.3 y regla «Faltante sin lote»: el recuento lo deja en cero; el resumen dice cuánto faltaba."""
        faltante(self.iin, 3)
        r = self.calcular(RECUENTO, {})
        self.assertEqual(r.faltante_a_cero, D("3"))
        self.assertEqual((r.stock_antes, r.stock_despues, r.valor), (D("27"), D("30"), D("300.00")))

    def test_extension_10c_quitar_un_lote_nuevo_lo_saca_del_resumen_y_de_la_diferencia_total(self):
        """Extensión 10c: el Agrónomo quita un lote nuevo y el Sistema presenta la diferencia total del recuento sin él."""
        dos = [{"cantidad": "2", "vencimiento": self.vence}, {"cantidad": "5", "vencimiento": self.vence}]
        con_dos = self.calcular(RECUENTO, {"nuevos": dos})
        con_uno = self.calcular(RECUENTO, {"nuevos": dos[:1]})
        self.assertEqual((len(con_dos.lotes_nuevos), con_dos.diferencia), (2, D("7")))
        self.assertEqual((len(con_uno.lotes_nuevos), con_uno.diferencia), (1, D("2")))

    def test_extension_10b_se_repite_por_cada_fecha_de_vencimiento_distinta(self):
        """Extensión 10b: «repite esta extensión por cada fecha de vencimiento distinta que encuentre»: un lote nuevo por cada una."""
        nuevos = [
            {"cantidad": "2", "vencimiento": self.vence},
            {"cantidad": "3", "vencimiento": self.vence + timedelta(days=10)},
        ]
        resultado = self.confirmar(RECUENTO, {"nuevos": nuevos})
        self.assertEqual(
            sorted((l.cantidad_disponible, l.fecha_vencimiento) for l in resultado.lotes_nuevos),
            [(D("2"), self.vence), (D("3"), self.vence + timedelta(days=10))],
        )

    # ---- confirmar: las postcondiciones ----

    def test_post_a_y_d_cada_lote_que_cambia_queda_ajustado_con_un_movimiento(self):
        """Postcondiciones a y d: la cantidad disponible ajustada y UN movimiento por lote (regla 1 de 8.19): tipo según el sentido, cantidad
        positiva igual a la diferencia, motivo y sin documento de origen."""
        antes = MovimientoInsumo.objects.count()
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8", self.l2.pk: "25"}})
        self.assertEqual((self.disponible(self.l1), self.disponible(self.l2)), (D("8"), D("25")))
        self.assertEqual(MovimientoInsumo.objects.count() - antes, 2)
        baja = MovimientoInsumo.objects.get(lote_insumo=self.l1, tipo_movimiento=Mov.AJUSTE_NEGATIVO)
        sube = MovimientoInsumo.objects.get(lote_insumo=self.l2, tipo_movimiento=Mov.AJUSTE_POSITIVO, motivo_ajuste="recuento_fisico")
        self.assertEqual((baja.cantidad, sube.cantidad), (D("2"), D("5")))
        for movimiento in (baja, sube):
            self.assertEqual((movimiento.motivo_ajuste, movimiento.origen_id), ("recuento_fisico", None))
        self.invariantes()

    def test_post_d_el_movimiento_lleva_la_fecha_y_la_hora_actuales_y_la_descripcion(self):
        """Postcondición d: la fecha y la hora actuales y la descripción, si se indicó."""
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}, "descripcion": "Contamos a la mañana"})
        movimiento = MovimientoInsumo.objects.get(lote_insumo=self.l1, tipo_movimiento=Mov.AJUSTE_NEGATIVO)
        self.assertEqual(movimiento.fecha.astimezone().date(), self.hoy)
        self.assertEqual(movimiento.descripcion_ajuste, "Contamos a la mañana")

    def test_post_b_la_mercaderia_encontrada_crea_un_lote_nuevo_con_su_movimiento(self):
        """Postcondición b: un lote nuevo por cada ingreso, con cantidad ingresada y disponible iguales, fecha de ingreso de hoy y el
        vencimiento indicado, y su movimiento «ajuste positivo»."""
        resultado = self.confirmar(RECUENTO, {"nuevos": [{"cantidad": "2", "vencimiento": self.vence}]})
        [nuevo] = resultado.lotes_nuevos
        nuevo.refresh_from_db()
        self.assertEqual(
            (nuevo.cantidad_ingresada, nuevo.cantidad_disponible, nuevo.fecha_ingreso, nuevo.fecha_vencimiento, nuevo.es_faltante_sin_lote),
            (D("2"), D("2"), self.hoy, self.vence, False),
        )
        self.assertEqual(nuevo.insumo_invernadero_id, self.iin.pk)
        movimiento = MovimientoInsumo.objects.get(lote_insumo=nuevo)
        self.assertEqual((movimiento.tipo_movimiento, movimiento.cantidad, movimiento.motivo_ajuste), (Mov.AJUSTE_POSITIVO, D("2"), "recuento_fisico"))
        self.invariantes()

    def test_post_b_un_insumo_que_no_controla_vencimiento_crea_el_lote_sin_fecha(self):
        """Postcondición b: «la fecha de vencimiento indicada, o vacía si el insumo no controla vencimiento»."""
        bolsas = existencia(insumo("Bolsas", tipo=self.tipo, unidad="unidad"), self.invernadero)
        resultado = self.confirmar(RECUENTO, {"nuevos": [{"cantidad": "5"}]}, iin=bolsas)
        self.assertIsNone(resultado.lotes_nuevos[0].fecha_vencimiento)
        self.invariantes(bolsas)

    def test_post_c_el_faltante_sin_lote_queda_en_cero_con_su_movimiento_y_se_conserva(self):
        """Postcondición c y paso 14.3: el faltante queda en cero con un «ajuste positivo» por lo que faltaba; el lote se conserva."""
        falta = faltante(self.iin, 3)
        self.confirmar(RECUENTO, {})
        self.assertEqual(self.disponible(falta), D("0"))
        movimiento = MovimientoInsumo.objects.get(lote_insumo=falta, tipo_movimiento=Mov.AJUSTE_POSITIVO)
        self.assertEqual((movimiento.cantidad, movimiento.motivo_ajuste, movimiento.origen_id), (D("3"), "recuento_fisico", None))
        self.assertTrue(LoteInsumo.objects.filter(pk=falta.pk, es_faltante_sin_lote=True).exists())
        self.invariantes()

    def test_post_c_el_recuento_combina_diferencias_lotes_nuevos_y_faltante_en_una_sola_operacion(self):
        """Paso 14: actualiza los lotes, crea los nuevos y deja el faltante en cero, todo junto (un movimiento por lote que cambió)."""
        falta = faltante(self.iin, 3)
        antes = MovimientoInsumo.objects.count()
        resultado = self.confirmar(
            RECUENTO, {"contados": {self.l1.pk: "8"}, "nuevos": [{"cantidad": "2", "vencimiento": self.vence}]}
        )
        self.assertEqual(MovimientoInsumo.objects.count() - antes, 3)  # l1, el lote nuevo y el faltante
        self.assertEqual((self.disponible(self.l1), self.disponible(falta)), (D("8"), D("0")))
        self.assertEqual(resultado.stock_actual, D("30"))  # 8 + 20 + 2 + 0
        self.invariantes()

    def test_post_g_el_stock_actual_queda_actualizado(self):
        """Postcondición g: el stock actual es la suma de lo disponible de sus lotes; el resultado lo informa (paso 15)."""
        resultado = self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}})
        self.assertEqual(resultado.stock_actual, D("28"))
        self.assertIsNone(resultado.inconsistente)

    def test_paso_14_un_lote_no_contado_no_cambia_y_no_genera_movimiento(self):
        """Un lote que no figura en ``contados`` conserva su cantidad y no tiene movimiento nuevo."""
        antes = MovimientoInsumo.objects.filter(lote_insumo=self.l2).count()
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}})
        self.assertEqual(self.disponible(self.l2), D("20"))
        self.assertEqual(MovimientoInsumo.objects.filter(lote_insumo=self.l2).count(), antes)

    def test_paso_14_el_recuento_puede_dejar_un_lote_en_cero_y_se_conserva(self):
        """Un lote en 0 se conserva (trazabilidad)."""
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "0"}})
        self.assertEqual(self.disponible(self.l1), D("0"))
        self.assertTrue(LoteInsumo.objects.filter(pk=self.l1.pk).exists())
        self.invariantes()

    def test_paso_14_un_lote_vencido_puede_bajar_en_el_recuento(self):
        """Contar menos en un lote vencido es válido (lo vencido no ingresa, pero sí puede descontarse)."""
        viejo = lote(self.iin, 5, vence=self.vencido)
        self.confirmar(RECUENTO, {"contados": {viejo.pk: "2"}})
        self.assertEqual(self.disponible(viejo), D("2"))
        self.invariantes()

    # ---- postcondiciones k, l y m: la auditoría ----

    def test_post_k_l_y_m_un_solo_registro_con_el_stock_los_lotes_y_los_movimientos(self):
        """Postcondiciones k, l y m (D-36): un registro ``ajuste_stock`` por ajuste, con el stock antes y después (como texto) y, en los
        datos, el motivo, los lotes tocados y los movimientos creados (referencias)."""
        resultado = self.confirmar(
            RECUENTO, {"contados": {self.l1.pk: "8"}, "nuevos": [{"cantidad": "2", "vencimiento": self.vence}]}
        )
        registro = RegistroAuditoria.objects.get(accion=AJUSTE)
        self.assertEqual(registro.usuario_id, self.agronomo.pk)
        # El stock queda igual (−2 + 2): D-36 rechaza un cambio con antes igual a después, así que no figura ``cambios``.
        self.assertNotIn("cambios", registro.detalle)
        datos = registro.detalle["datos"]
        self.assertEqual(datos["motivo_ajuste"], "recuento_fisico")
        self.assertEqual(datos["insumo"]["texto"], "Nutriente A")
        self.assertEqual({r["id"] for r in datos["movimientos"]}, {m.pk for m in resultado.movimientos})
        self.assertIn(self.l1.pk, {r["id"] for r in datos["lotes"]})
        self.assertIn(resultado.lotes_nuevos[0].pk, {r["id"] for r in datos["lotes"]})
        modelos = {(a["modelo"], a["id"]) for a in registro.afectados}
        self.assertIn(("inventario.insumoinvernadero", self.iin.pk), modelos)
        self.assertIn(("maestros.invernadero", self.invernadero.pk), modelos)

    def test_post_k_el_cambio_de_stock_va_como_texto_con_antes_y_despues(self):
        """D-36: el ``Decimal`` va como texto con los decimales de la unidad."""
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}})
        cambios = RegistroAuditoria.objects.get(accion=AJUSTE).detalle["cambios"]
        self.assertEqual(cambios, {"stock": {"antes": "30.000", "despues": "28.000"}})

    def test_post_l_los_movimientos_no_se_auditan_uno_por_uno(self):
        """docs/patrones/stock.md, sección 6: los movimientos van como referencias en el registro del caso de uso. Desde CON-04b el ajuste además
        crea asientos (que audita ``contabilidad``: un alta por asiento y una por movimiento contable, D-84 punto 9): lo que NO es contable sigue
        siendo UN solo registro (el del ajuste), y los contables son los esperados."""
        self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8", self.l2.pk: "25"}})
        acciones = RegistroAuditoria.Accion
        contables = [acciones.ALTA_ASIENTO_CONTABLE, acciones.ALTA_MOVIMIENTO_CONTABLE, acciones.ALTA_EJERCICIO_CONTABLE]
        self.assertEqual(RegistroAuditoria.objects.filter(accion=AJUSTE).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.exclude(accion__in=contables).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=acciones.ALTA_ASIENTO_CONTABLE).count(), 2)  # uno por lote que cambió
        self.assertEqual(RegistroAuditoria.objects.filter(accion=acciones.ALTA_MOVIMIENTO_CONTABLE).count(), 4)  # dos líneas por asiento

    def test_regla_9_sin_ejercicio_el_ajuste_no_se_registra_y_el_resumen_sigue_mostrando_el_valor(self):
        """Regla 9 de CON-INI-EJE (CON-05; reemplaza `test_d92_sin_ejercicio_el_ajuste_se_registra_abre_el_primero_y_muestra_el_valor`, de D-92 punto 2 y H9): sin ejercicio el resumen sigue
        mostrando el valor del ajuste, pero confirmarlo se rechaza con `contabilidad_no_iniciada` y no cambia ni el stock ni el ejercicio."""
        EjercicioContable.objects.all().delete()  # la clase trae el ejercicio del helper
        resumen = self.calcular(RECUENTO, {"contados": {self.l1.pk: "8"}})
        self.assertEqual(resumen.valor, D("-200.00"))
        with self.assertRaises(ErrorContable) as contexto:
            self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8"}})
        self.assertEqual(contexto.exception.codigo, "contabilidad_no_iniciada")
        self.assertEqual(EjercicioContable.objects.count(), 0)
        self.l1.refresh_from_db()
        self.assertEqual(self.l1.cantidad_disponible, D("10"))

    # ---- CON-04b: un asiento por cada movimiento de ajuste del recuento (postcondición e, R012) ----

    def test_post_e_un_recuento_que_toca_tres_lotes_genera_tres_asientos(self):
        """Postcondición e, paso 14.4 y R012: l1 baja 2 (÷ $ 100 = 200), l2 sube 5 (500) y el faltante sin lote (3) queda en cero (300): tres movimientos,
        tres asientos, cada uno con su lado (positivo: Debe Insumos en Stock / Haber Diferencias; negativo, al revés), con números consecutivos."""
        falta = faltante(self.iin, 3)
        resultado = self.confirmar(RECUENTO, {"contados": {self.l1.pk: "8", self.l2.pk: "25"}})
        self.assertEqual(len(resultado.movimientos), 3)
        por_lote = {m.lote_insumo_id: self.lineas_de(m) for m in resultado.movimientos}

        def sube(importe):
            return [(cuentas.INSUMOS_EN_STOCK, "D", D(importe)), (cuentas.DIFERENCIAS_DE_INVENTARIO, "H", D(importe))]

        self.assertEqual(
            por_lote,
            {
                self.l1.pk: [(cuentas.INSUMOS_EN_STOCK, "H", D("200.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, "D", D("200.00"))],
                self.l2.pk: sube("500.00"),
                falta.pk: sube("300.00"),
            },
        )
        self.assertEqual(sorted(a.numero_asiento for a in resultado.asientos), [1, 2, 3])
        self.assertEqual(AsientoContable.objects.count(), 3)
        self.invariantes()

    def test_post_c_y_e_el_faltante_que_queda_en_cero_asienta_insumos_contra_diferencias(self):
        """Postcondiciones c y e: el movimiento que deja en cero el faltante sin lote (ajuste positivo de 3 × $ 100) también origina su asiento."""
        falta = faltante(self.iin, 3)
        resultado = self.confirmar(RECUENTO, {})
        [movimiento] = resultado.movimientos
        self.assertEqual(movimiento.lote_insumo_id, falta.pk)
        self.assertEqual(
            self.lineas_de(movimiento),
            [(cuentas.INSUMOS_EN_STOCK, "D", D("300.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, "H", D("300.00"))],
        )
        self.invariantes()

    def test_post_b_y_e_el_lote_nuevo_del_recuento_asienta_como_diferencia_y_no_como_capital_inicial(self):
        """Postcondiciones b y e: la mercadería encontrada en un recuento (lote nuevo de 2 × $ 100) es un ajuste positivo «recuento físico»: va contra
        Diferencias de Inventario; solo el motivo «carga inicial» va contra Capital Inicial (D-92 punto 7)."""
        resultado = self.confirmar(RECUENTO, {"nuevos": [{"cantidad": "2", "vencimiento": self.vence}]})
        [movimiento] = resultado.movimientos
        self.assertEqual(
            self.lineas_de(movimiento),
            [(cuentas.INSUMOS_EN_STOCK, "D", D("200.00")), (cuentas.DIFERENCIAS_DE_INVENTARIO, "H", D("200.00"))],
        )
        self.invariantes()
