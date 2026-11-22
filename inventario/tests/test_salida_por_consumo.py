# Pruebas de `registrar_salida_por_consumo` (INV-02, paso 5; docs/patrones/stock.md, sección 3; docs/api/stock.md, «Escritura»; D-50 punto 7;
# D-52 punto 5; regla 5 de 8.13 y regla 4 de 8.23).
#
# Se prueba (inventario/servicios/stock.py), tomado del módulo dentro de cada prueba:
#   registrar_salida_por_consumo(iin_id, partes, *, origen_id, fecha=None) -> list[MovimientoInsumo]
#     - La llama `produccion` dentro de su transacción, con el invernadero ya bloqueado; vuelve a leer y bloquea la existencia y sus
#       lotes en orden de id. ``partes`` es ``[(lote_id, cantidad)]``.
#     - ``origen_id`` es OBLIGATORIO (D-52 punto 5): el id del ``OrigenDocumento`` (el Consumo) que origina cada movimiento. Sin él, falla.
#     - Descuenta de cada lote y crea UN movimiento «salida por consumo» por lote, con ``origen = origen_id``.
#     - Lo que no cabe en el lote, o lo que ningún lote cubre, NO bloquea (regla 5 de 8.13): sale del FALTANTE SIN LOTE, que se crea con
#       la primera salida que lo necesita (sin ingresada, ingreso ni vencimiento) y baja su ``cantidad_disponible`` (negativa). Genera su
#       propio movimiento, también con ``origen = origen_id``.
#     - ``fecha`` (D-50 punto 7): la fecha del movimiento es esa con la hora actual; sin ella, la de hoy.
#     - Al final llama a ``reevaluar_alertas_del_insumo`` (deja la alerta «stock inconsistente» si corresponde).
#     - Cada cantidad tiene que ser mayor que cero y cada lote, un lote común de esa existencia (``ValueError``; no cambia nada).

from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.test import TestCase, TransactionTestCase, tag
from django.utils import timezone

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.fabricas import (
    ConDatosDeInventario,
    asegurar_datos_de_inventario,
    existencia,
    faltante,
    insumo,
    lote,
    origen_falso,
    perezoso,
    tipo_de_insumo,
    verificar_invariantes,
)
from maestros.models import Alerta
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from maestros.tests.fabricas import (
    asegurar_datos_de_maestros,
    crear_agronomo,
    crear_alerta,
    crear_invernadero,
    crear_invernadero_con_geografia_propia,
)

stock = perezoso("inventario.servicios.stock")
CONSUMO = MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO
D = Decimal


class SalidaPorConsumoTests(ConDatosDeInventario, TestCase):
    """Reglas de la sección 3 de docs/patrones/stock.md. Cada prueba verifica las invariantes del kárdex."""

    def setUp(self):
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero("Norte", agronomo=self.agronomo)
        self.insumo = insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l", controla_vencimiento=True)
        self.iin = existencia(self.insumo, self.invernadero)
        self.origen = origen_falso()
        self.vence = timezone.localdate() + timedelta(days=60)

    def consumir(self, partes, **extra):
        return stock.registrar_salida_por_consumo(self.iin.pk, partes, origen_id=self.origen.pk, **extra)

    def disponible(self, un_lote):
        return LoteInsumo.objects.get(pk=un_lote.pk).cantidad_disponible

    def el_faltante(self):
        return LoteInsumo.objects.filter(insumo_invernadero=self.iin, es_faltante_sin_lote=True).first()

    # ---- el origen y los argumentos ----

    def test_d52_el_origen_es_obligatorio(self):
        """D-52 punto 5: sin ``origen_id`` falla (es un argumento obligatorio, no opcional) y no cambia nada."""
        l = lote(self.iin, 10, vence=self.vence)
        with self.assertRaises(TypeError):
            stock.registrar_salida_por_consumo(self.iin.pk, [(l.pk, D("3"))])
        self.assertEqual(self.disponible(l), D("10"))

    def test_regla_8_19_1_cada_movimiento_lleva_el_origen_y_es_una_salida_por_consumo(self):
        """D-52: cada movimiento queda con ``origen = origen_id`` y el tipo «salida por consumo»."""
        l = lote(self.iin, 10, vence=self.vence)
        [movimiento] = self.consumir([(l.pk, D("4"))])
        self.assertEqual((movimiento.tipo_movimiento, movimiento.origen_id, movimiento.lote_insumo_id), (CONSUMO, self.origen.pk, l.pk))
        self.assertEqual(movimiento.cantidad, D("4"))
        self.assertIsNone(movimiento.motivo_ajuste)
        verificar_invariantes(self.iin)

    def test_regla_cantidad_cero_o_negativa_se_rechaza_sin_cambiar_nada(self):
        """Una parte tiene que ser mayor que cero."""
        l = lote(self.iin, 10, vence=self.vence)
        for cantidad in ("0", "-1"):
            with self.subTest(cantidad=cantidad), self.assertRaises(ValueError):
                self.consumir([(l.pk, D(cantidad))])
        self.assertEqual(self.disponible(l), D("10"))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento=CONSUMO).count(), 0)

    def test_regla_8_23_2_una_cantidad_con_mas_decimales_que_la_unidad_se_rechaza_sin_cambiar_nada(self):
        """Regla 2 de 8.23: los decimales de la unidad (L: 3). Es un error de uso (``ValueError``) y no cambia nada."""
        l = lote(self.iin, 10, vence=self.vence)
        with self.assertRaises(ValueError):
            self.consumir([(l.pk, D("1.2345"))])
        self.assertEqual(self.disponible(l), D("10"))
        self.assertEqual(MovimientoInsumo.objects.filter(tipo_movimiento=CONSUMO).count(), 0)

    def test_regla_8_23_2_una_cantidad_que_no_es_un_numero_se_rechaza(self):
        """Un texto que no es una cantidad da ``ValueError``; una cantidad como texto válida se acepta."""
        l = lote(self.iin, 10, vence=self.vence)
        with self.assertRaises(ValueError):
            self.consumir([(l.pk, "mucho")])
        self.consumir([(l.pk, "2.5")])
        self.assertEqual(self.disponible(l), D("7.5"))

    def test_regla_un_lote_de_otra_existencia_se_rechaza(self):
        """Los lotes tienen que ser de esta existencia."""
        ajena = existencia(insumo("Otro", unidad="l"), self.invernadero)
        de_otra = lote(ajena, 10)
        with self.assertRaises(ValueError):
            self.consumir([(de_otra.pk, D("1"))])
        self.assertEqual(self.disponible(de_otra), D("10"))

    def test_regla_8_23_4_no_se_consume_directo_del_faltante_sin_lote(self):
        """El faltante no es un lote físico: nadie lo nombra, solo se crea o crece cuando falta."""
        falta = faltante(self.iin, 2)
        with self.assertRaises(ValueError):
            self.consumir([(falta.pk, D("1"))])

    # ---- cubre ----

    def test_regla_5_8_13_cubre_exacto_el_lote_y_lo_deja_en_cero(self):
        """Lo pedido es exactamente lo disponible: el lote queda en 0 (se conserva) y no hay faltante."""
        l = lote(self.iin, 10, vence=self.vence)
        [movimiento] = self.consumir([(l.pk, D("10"))])
        self.assertEqual(self.disponible(l), D("0"))
        self.assertIsNone(self.el_faltante())
        self.assertEqual(movimiento.cantidad, D("10"))
        verificar_invariantes(self.iin)

    def test_regla_5_8_13_descuenta_parcialmente_un_lote(self):
        """Pedir menos de lo disponible descuenta solo eso."""
        l = lote(self.iin, 10, vence=self.vence)
        self.consumir([(l.pk, D("4"))])
        self.assertEqual(self.disponible(l), D("6"))
        verificar_invariantes(self.iin)

    def test_regla_8_19_1_de_varios_lotes_crea_un_movimiento_por_lote(self):
        """Regla 1 de 8.19: una operación que toca varios lotes genera un movimiento por lote."""
        a = lote(self.iin, 5, vence=self.vence)
        b = lote(self.iin, 8, vence=self.vence + timedelta(days=5))
        antes = MovimientoInsumo.objects.count()
        movimientos = self.consumir([(a.pk, D("5")), (b.pk, D("3"))])
        self.assertEqual(MovimientoInsumo.objects.count() - antes, 2)
        self.assertEqual({m.lote_insumo_id: m.cantidad for m in movimientos}, {a.pk: D("5"), b.pk: D("3")})
        self.assertEqual((self.disponible(a), self.disponible(b)), (D("0"), D("5")))
        verificar_invariantes(self.iin)

    def test_regla_8_19_1_un_lote_repetido_en_las_partes_genera_un_solo_movimiento_por_la_suma(self):
        """Un cambio de cantidad de un lote = exactamente un movimiento, aunque el lote aparezca dos veces."""
        l = lote(self.iin, 10, vence=self.vence)
        movimientos = self.consumir([(l.pk, D("2")), (l.pk, D("3"))])
        self.assertEqual([m.cantidad for m in movimientos], [D("5")])
        self.assertEqual(self.disponible(l), D("5"))
        verificar_invariantes(self.iin)

    def test_regla_8_19_1_devuelve_los_movimientos_creados(self):
        """Devuelve la lista de ``MovimientoInsumo`` (los que el consumo enlaza por ``origen``)."""
        l = lote(self.iin, 10, vence=self.vence)
        movimientos = self.consumir([(l.pk, D("1"))])
        self.assertTrue(all(isinstance(m, MovimientoInsumo) and m.pk for m in movimientos))

    # ---- faltante sin lote ----

    def test_regla_5_8_13_si_falta_crea_el_faltante_sin_lote_con_lo_que_no_cubrio_el_lote(self):
        """Faltante nuevo: el lote queda en 0 y lo que faltó sale del faltante, que se crea con la primera salida que lo necesita."""
        l = lote(self.iin, 5, vence=self.vence)
        movimientos = self.consumir([(l.pk, D("8"))])
        falta = self.el_faltante()
        self.assertEqual((self.disponible(l), falta.cantidad_disponible), (D("0"), D("-3")))
        self.assertEqual({m.lote_insumo_id: m.cantidad for m in movimientos}, {l.pk: D("5"), falta.pk: D("3")})
        verificar_invariantes(self.iin)

    def test_regla_8_23_4_el_faltante_nuevo_no_tiene_ingresada_ingreso_ni_vencimiento(self):
        """Regla 4 de 8.23: el faltante se crea sin cantidad ingresada, sin fecha de ingreso y sin vencimiento."""
        l = lote(self.iin, 1, vence=self.vence)
        self.consumir([(l.pk, D("2"))])
        falta = self.el_faltante()
        self.assertTrue(falta.es_faltante_sin_lote)
        self.assertEqual((falta.cantidad_ingresada, falta.fecha_ingreso, falta.fecha_vencimiento), (None, None, None))

    def test_regla_5_8_13_el_movimiento_del_faltante_tambien_lleva_el_origen(self):
        """El faltante genera su propio movimiento «salida por consumo» con ``origen = origen_id``."""
        l = lote(self.iin, 1, vence=self.vence)
        self.consumir([(l.pk, D("2"))])
        movimiento = MovimientoInsumo.objects.get(lote_insumo=self.el_faltante())
        self.assertEqual((movimiento.tipo_movimiento, movimiento.origen_id, movimiento.cantidad), (CONSUMO, self.origen.pk, D("1")))

    def test_regla_5_8_13_sin_ningun_lote_todo_sale_del_faltante(self):
        """Una parte sobre un lote que ya está en 0: todo lo pedido es faltante."""
        agotado = lote(self.iin, 0, vence=self.vence, ingresada=5)
        self.consumir([(agotado.pk, D("4"))])
        self.assertEqual(self.el_faltante().cantidad_disponible, D("-4"))
        self.assertEqual(self.disponible(agotado), D("0"))
        verificar_invariantes(self.iin)

    def test_regla_8_23_4_un_faltante_existente_crece_en_vez_de_crear_otro(self):
        """Faltante existente: baja más y sigue habiendo uno solo (restricción de la base)."""
        falta = faltante(self.iin, 2)
        l = lote(self.iin, 5, vence=self.vence)
        self.consumir([(l.pk, D("9"))])
        self.assertEqual(LoteInsumo.objects.filter(insumo_invernadero=self.iin, es_faltante_sin_lote=True).count(), 1)
        self.assertEqual(self.disponible(falta), D("-6"))
        self.assertEqual(self.disponible(l), D("0"))
        verificar_invariantes(self.iin)

    def test_regla_5_8_13_un_consumo_que_alcanza_no_toca_un_faltante_existente(self):
        """Si el lote cubre, el faltante que ya había queda como estaba (no se cancela con consumos)."""
        falta = faltante(self.iin, 2)
        l = lote(self.iin, 5, vence=self.vence)
        antes = MovimientoInsumo.objects.filter(lote_insumo=falta).count()
        self.consumir([(l.pk, D("3"))])
        self.assertEqual(self.disponible(falta), D("-2"))
        self.assertEqual(MovimientoInsumo.objects.filter(lote_insumo=falta).count(), antes)

    # ---- fecha ----

    def test_d50_7_sin_fecha_la_del_movimiento_es_la_de_hoy(self):
        """Sin ``fecha``, la del movimiento es la de hoy."""
        l = lote(self.iin, 10, vence=self.vence)
        [movimiento] = self.consumir([(l.pk, D("1"))])
        self.assertEqual(timezone.localtime(movimiento.fecha).date(), timezone.localdate())

    def test_d50_7_con_una_fecha_pasada_el_movimiento_lleva_esa_fecha_con_la_hora_actual(self):
        """D-50 punto 7: la fecha efectiva de la siembra puede ser anterior a hoy; la hora es la de la operación."""
        l = lote(self.iin, 10, vence=self.vence)
        pasada = timezone.localdate() - timedelta(days=3)
        ahora = timezone.localtime()
        [movimiento] = self.consumir([(l.pk, D("1"))], fecha=pasada)
        registrado = timezone.localtime(movimiento.fecha)
        self.assertEqual(registrado.date(), pasada)
        esperado = timezone.make_aware(datetime.combine(pasada, ahora.time()))
        self.assertAlmostEqual((registrado - esperado).total_seconds(), 0, delta=300)

    def test_d50_7_la_fecha_tambien_rige_para_el_movimiento_del_faltante(self):
        """Todos los movimientos de la operación llevan la fecha efectiva."""
        l = lote(self.iin, 1, vence=self.vence)
        pasada = timezone.localdate() - timedelta(days=2)
        movimientos = self.consumir([(l.pk, D("3"))], fecha=pasada)
        self.assertEqual({timezone.localtime(m.fecha).date() for m in movimientos}, {pasada})
        self.assertEqual(len(movimientos), 2)

    # ---- alertas ----

    def test_regla_6_8_13_deja_la_alerta_stock_inconsistente_cuando_se_creo_un_faltante(self):
        """Paso 4 de la sección 3: llama a ``reevaluar_alertas_del_insumo``; el faltante deja el stock vigente negativo."""
        l = lote(self.iin, 2, vence=self.vence)
        self.consumir([(l.pk, D("5"))])
        alerta = Alerta.objects.get(tipo_alerta="inv_stock_inconsistente", estado_alerta="activa")
        self.assertEqual((alerta.clave_estado, alerta.agronomo_id), (f"insumo:{self.iin.pk}", self.agronomo.pk))

    def test_regla_6_8_13_un_consumo_que_alcanza_no_crea_alerta_de_inconsistencia(self):
        """Sin faltante ni reservas descubiertas no hay alerta."""
        l = lote(self.iin, 10, vence=self.vence)
        self.consumir([(l.pk, D("4"))])
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_stock_inconsistente").count(), 0)

    def test_regla_6_8_13_deja_bajo_el_minimo_si_el_consumo_lo_baja(self):
        """La reevaluación incluye «bajo el mínimo»."""
        self.iin.cant_min_insumo = D("10")
        self.iin.save(update_fields=["cant_min_insumo"])
        l = lote(self.iin, 12, vence=self.vence)
        self.consumir([(l.pk, D("5"))])
        self.assertEqual(Alerta.objects.filter(tipo_alerta="inv_insumo_bajo_minimo", estado_alerta="activa").count(), 1)

    def test_regla_7_de_rev_vnc_el_consumo_que_agota_un_lote_resuelve_su_alerta_de_vencimiento(self):
        """Regla 7 de CMP-REV-VNC: la alerta de vencimiento se resuelve cuando la cantidad disponible llega a cero, por consumo."""
        l = lote(self.iin, 4, vence=timezone.localdate() - timedelta(days=1))
        crear_alerta(
            self.invernadero, "inv_insumo_vencido", para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{l.pk}"
        )
        self.consumir([(l.pk, D("4"))])
        self.assertEqual(Alerta.objects.get(tipo_alerta="inv_insumo_vencido").estado_alerta, "resuelta")

    def test_regla_7_de_rev_vnc_un_consumo_parcial_no_resuelve_la_alerta_de_vencimiento(self):
        """Mientras quede algo en el lote, la alerta sigue."""
        l = lote(self.iin, 4, vence=timezone.localdate() - timedelta(days=1))
        crear_alerta(
            self.invernadero, "inv_insumo_vencido", para_gerente=False, agronomo=self.agronomo, clave_estado=f"lote:{l.pk}"
        )
        self.consumir([(l.pk, D("1"))])
        self.assertEqual(Alerta.objects.get(tipo_alerta="inv_insumo_vencido").estado_alerta, "activa")

    def test_no_audita_lo_hace_el_caso_de_uso_que_llama(self):
        """docs/api/stock.md, «Escritura»: no audita; los movimientos son el kárdex y van como referencias en el caso de uso."""
        l = lote(self.iin, 10, vence=self.vence)
        antes = RegistroAuditoria.objects.count()
        self.consumir([(l.pk, D("1"))])
        self.assertEqual(RegistroAuditoria.objects.count(), antes)


def consumo_simulado(actor, iin, partes, origen, bloquea_el_invernadero=True):
    """Lo que hace `produccion` al consumir, para las pruebas de concurrencia: en una transacción, bloquea el invernadero (contrato de
    D-40; ``bloquea_el_invernadero=False`` lo omite para probar solo los bloqueos de la propia función), llama a
    ``registrar_salida_por_consumo`` y audita; ``correr_a_la_vez`` lo detiene después de registrar la auditoría."""
    with transaction.atomic():
        if bloquea_el_invernadero:
            bloquear_invernadero_activo(iin.invernadero_id)
        movimientos = perezoso("inventario.servicios.stock").registrar_salida_por_consumo(iin.pk, partes, origen_id=origen.pk)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO_INVERNADERO,
            afectados=[iin],
            detalle={"cambios": {"cant_min_insumo": {"antes": "1.000", "despues": "2.000"}}},
        )
    return movimientos


@tag("concurrencia")
class SalidaPorConsumoConcurrenciaTests(ConDatosDeInventario, TransactionTestCase):
    """Requisito especial de CMP-AJT-STK y sección 5 de docs/patrones/stock.md: dos consumos simultáneos sobre el mismo lote no dejan
    un lote común negativo ni descuentan dos veces lo mismo."""

    def setUp(self):
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        self.agronomo = crear_agronomo()
        self.invernadero = crear_invernadero_con_geografia_propia("Invernadero Uno", agronomo=self.agronomo)
        self.iin = existencia(insumo("Nutriente A", tipo=tipo_de_insumo("Nutrientes"), unidad="l"), self.invernadero)
        self.lote = lote(self.iin, 10)
        self.origen_a = origen_falso()
        self.origen_b = origen_falso()

    def verificar_resultado(self, resultados):
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(LoteInsumo.objects.get(pk=self.lote.pk).cantidad_disponible, D("0"))
        falta = LoteInsumo.objects.get(insumo_invernadero=self.iin, es_faltante_sin_lote=True)
        self.assertEqual(falta.cantidad_disponible, D("-4"))  # 7 + 7 pedidos contra 10 disponibles: faltan 4, una sola vez
        salidas = MovimientoInsumo.objects.filter(tipo_movimiento=CONSUMO)
        self.assertEqual(sum(m.cantidad for m in salidas.filter(lote_insumo=self.lote)), D("10"))
        self.assertEqual(sum(m.cantidad for m in salidas.filter(lote_insumo=falta)), D("4"))
        verificar_invariantes(self.iin)

    def test_dos_consumos_sobre_el_mismo_lote_no_lo_dejan_negativo_ni_descuentan_dos_veces(self):
        """Con el invernadero bloqueado por quien llama: el segundo espera, relee el lote ya descontado, toma lo que queda y manda lo
        demás al faltante."""
        resultados = correr_a_la_vez(
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_a),
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_b),
            primera="a",
        )
        self.verificar_resultado(resultados)

    def test_dos_consumos_sobre_el_mismo_lote_se_protegen_con_los_bloqueos_de_la_propia_funcion(self):
        """Sin el bloqueo del invernadero de quien llama, la función protege el lote por sí sola: bloquea la existencia y los lotes
        (orden de id) y los relee antes de descontar. Sin esos bloqueos, los dos leen 10 y el lote quedaría en 3."""
        resultados = correr_a_la_vez(
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_a, False),
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_b, False),
            primera="a",
        )
        self.verificar_resultado(resultados)

    def test_el_origen_de_cada_consumo_queda_en_sus_movimientos(self):
        """Cada consumo conserva su ``origen``: el segundo no pisa ni mezcla los movimientos del primero."""
        correr_a_la_vez(
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_a),
            lambda: consumo_simulado(self.agronomo, self.iin, [(self.lote.pk, D("7"))], self.origen_b),
            primera="a",
        )
        por_origen = {
            origen.pk: sum(m.cantidad for m in MovimientoInsumo.objects.filter(origen_id=origen.pk))
            for origen in (self.origen_a, self.origen_b)
        }
        self.assertEqual(por_origen, {self.origen_a.pk: D("7"), self.origen_b.pk: D("7")})
