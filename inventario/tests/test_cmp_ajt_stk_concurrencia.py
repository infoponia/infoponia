# Pruebas de CMP-AJT-STK · concurrencia y la extensión 14a (docs/casos_de_uso/inventario/ajuste_de_stock.md: «Requisitos especiales» y extensión 14a;
# docs/patrones/stock.md, sección 5; INV-02, paso 6). El contrato del servicio, en ``inventario/tests/ajustes_comunes.py``.
#
# Dos pasos y una confirmación: ``calcular_ajuste`` devuelve la «huella» del estado que usó (las cantidades disponibles de los lotes que usó, el
# faltante si lo usó, y las RESERVAS activas del insumo: cambian el stock libre y la cobertura); ``confirmar_ajuste`` bloquea (invernadero → existencia →
# lotes), recalcula y, si la huella ya no coincide, lanza ``AjusteDesactualizado`` (extensión 14a): no cambia nada y trae lo vigente en ``.vigente``
# (``{"lotes": {lote_id: disponible}, "reservado": Decimal}``) para que la pantalla vuelva al paso con los valores de ahora. Los bloqueos impiden que
# un ajuste y un consumo simultáneos dejen un lote común negativo o descuenten dos veces lo mismo.

import datetime
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, tag

from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import asegurar_plan_de_cuentas, ejercicio, ejercicio_abierto
from core.models import Contador, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_cuenta
from inventario.models import LoteInsumo, MovimientoInsumo
from inventario.tests.ajustes_comunes import RECUENTO, ROTURA, BaseDeAjustes, ajustes
from inventario.tests.fabricas import (
    asegurar_datos_de_inventario,
    existencia,
    lote,
    origen_falso,
    perezoso,
    reservas_de_prueba,
    verificar_invariantes,
)
from inventario.tests.test_salida_por_consumo import consumo_simulado
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_invernadero_con_geografia_propia
from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

stock = perezoso("inventario.servicios.stock")
D = Decimal
AJUSTE = RegistroAuditoria.Accion.AJUSTE_STOCK
CONSUMO = MovimientoInsumo.TipoMovimiento.SALIDA_POR_CONSUMO


class CmpAjtStkDesactualizadoTests(BaseDeAjustes, TestCase):
    """Extensión 14a: entre la carga y la confirmación otra operación cambió lo que el ajuste usó."""

    def setUp(self):
        iniciar_contabilidad_para_pruebas()  # CON-05, regla 9: sin ejercicio no hay asiento
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
        asegurar_plan_de_cuentas()  # CON-04b: el ajuste asienta y el ``flush`` de la prueba anterior vació el plan
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


# ---- CON-04b · el asiento del ajuste contra el cierre del ejercicio y entre ajustes (docs/patrones/asientos.md, secciones 2 y 4; D-86 punto 2; D-102) ----

VENCE_LEJOS = datetime.date(2030, 1, 1)


@tag("concurrencia")
class CmpAjtStkAsientoConcurrenciaTests(BaseDeAjustes, TransactionTestCase):
    """El asiento de un ajuste bloquea el ejercicio AL FINAL (D-86 punto 2) y NUNCA rechaza por la fecha (D-102): un ajuste que se cruza con el cierre del
    ejercicio no falla; su asiento queda en el ejercicio que corresponde y nunca en uno cerrado. «Hoy» es siempre un argumento (el servicio no lee la hora).

    Escenario A: el ejercicio de 2026 «en cierre» (id menor) y el de 2027 abierto; hoy = 10/03/2027. Escenario B (autorrecuperación): hoy = 10/01/2028,
    cuando el abierto de 2027 ya venció. Se usan dos hilos con ``correr_a_la_vez``; las pruebas no desactivan ningún bloqueo."""

    HOY = datetime.date(2027, 3, 10)
    HOY_VENCIDO = datetime.date(2028, 1, 10)

    def setUp(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_datos_de_inventario()
        asegurar_datos_de_maestros()
        asegurar_plan_de_cuentas()  # el ``flush`` de este TransactionTestCase vacía el plan en cada prueba
        self.preparar(geografia_propia=True)
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.l1 = lote(self.iin, 10, vence=VENCE_LEJOS)

    def con_ejercicios(self):
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio_abierto(datetime.date(2027, 1, 1))

    def ajuste(self, hoy, iin=None, actor=None, lote_a_romper=None):
        """Un ajuste por rotura de 2 L, ya calculado con ``hoy``: devuelve la operación para ``correr_a_la_vez``."""
        iin = iin or self.iin
        entrada = {"lote_id": (lote_a_romper or self.l1).pk, "cantidad": "2"}
        huella = self.calcular(ROTURA, entrada, actor=actor, iin=iin, hoy=hoy).huella
        return lambda: self.confirmar(ROTURA, entrada, huella=huella, actor=actor, iin=iin, hoy=hoy)

    def cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def sin_errores(self, resultados):
        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])

    def test_d102_el_cierre_primero_y_el_ajuste_a_la_vez_el_ajuste_termina_y_su_asiento_va_al_abierto(self):
        """El cierre del 2026 ya tomó su fila (sin confirmar); el ajuste de hoy (2027) no la necesita: termina bien y su asiento, de fecha hoy y sin la
        aclaración de H10, es el N.º 1 del 2027. El 2026 queda cerrado y sin asientos. Ninguno de los dos falla (D-102)."""
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.cierre(), self.ajuste(self.HOY), primera="a")
        self.sin_errores(resultados)
        [asiento] = resultados["b"].asientos
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento, asiento.numero_asiento), (self.abierto.pk, self.HOY, 1))
        self.assertNotIn("Fecha del hecho", asiento.descripcion_asiento)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.assertEqual(AsientoContable.objects.filter(ejercicio=self.en_cierre).count(), 0)
        self.assertEqual(self.disponible(self.l1), D("8"))
        self.invariantes()

    def test_d102_el_ajuste_primero_y_el_cierre_a_la_vez_los_dos_terminan_y_el_asiento_queda_en_el_abierto(self):
        """El ajuste ya creó su asiento y tiene el ejercicio abierto bloqueado (sin confirmar); el cierre del 2026 toca solo su fila y termina: los dos
        terminan bien y el asiento está en el 2027."""
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.ajuste(self.HOY), self.cierre(), primera="a")
        self.sin_errores(resultados)
        self.assertEqual([a.ejercicio_id for a in resultados["a"].asientos], [self.abierto.pk])
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.invariantes()

    def test_d102_el_cierre_primero_y_un_ajuste_con_el_abierto_vencido_espera_y_va_al_nuevo_ejercicio(self):
        """Hoy = 10/01/2028: el abierto de 2027 venció. El cierre del 2026 tiene su fila tomada; el ajuste, al autorrecuperar (H9), espera esa fila, la relee
        ya «cerrada», pasa el 2027 a «en cierre», abre el 2028 y su asiento es el N.º 1 del 2028, con fecha hoy. No hay *deadlock* ni error."""
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.cierre(), self.ajuste(self.HOY_VENCIDO), primera="a")
        self.sin_errores(resultados)
        nuevo = EjercicioContable.objects.get(estado_ejercicio=EjercicioContable.Estado.ABIERTO)
        self.assertEqual(nuevo.fecha_inicio_ejercicio, datetime.date(2028, 1, 1))
        [asiento] = resultados["b"].asientos
        self.assertEqual((asiento.ejercicio_id, asiento.fecha_asiento, asiento.numero_asiento), (nuevo.pk, self.HOY_VENCIDO, 1))
        estados = {e.pk: e.estado_ejercicio for e in EjercicioContable.objects.all()}
        self.assertEqual(estados[self.en_cierre.pk], EjercicioContable.Estado.CERRADO)
        self.assertEqual(estados[self.abierto.pk], EjercicioContable.Estado.EN_CIERRE)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).contador_id, self.contador.pk)  # lo cerró el Contador, no «cierre automático»
        self.invariantes()

    def test_d102_la_autorrecuperacion_del_ajuste_primero_y_el_cierre_manual_recibe_que_ya_no_esta_en_cierre(self):
        """Hoy = 10/01/2028: el ajuste autorrecupera primero: cierra solo el 2026 (C1) y todavía no confirmó. El cierre manual espera esa fila, la relee
        «cerrada» y recibe ``ejercicio_no_esta_en_cierre``; el ajuste termina con su asiento en el 2028."""
        self.con_ejercicios()
        resultados = correr_a_la_vez(self.ajuste(self.HOY_VENCIDO), self.cierre(), primera="a")
        self.assertNotIsInstance(resultados["a"], Exception)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "ejercicio_no_esta_en_cierre")
        nuevo = EjercicioContable.objects.get(estado_ejercicio=EjercicioContable.Estado.ABIERTO)
        self.assertEqual([a.ejercicio_id for a in resultados["a"].asientos], [nuevo.pk])
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.invariantes()

    # ---- docs/patrones/asientos.md, sección 4: numeración sin huecos y el ejercicio se bloquea último ----

    def preparar_segundo_invernadero(self):
        """Otro Agrónomo con otro invernadero y el mismo insumo, para que los dos ajustes no se esperen en el invernadero (solo en el ejercicio)."""
        self.invernadero_b = crear_invernadero_con_geografia_propia("Invernadero Sur", agronomo=self.otro)
        self.iin_b = existencia(self.insumo, self.invernadero_b, minimo=0, precio="100")
        self.lote_b = lote(self.iin_b, 10, vence=VENCE_LEJOS)

    def test_regla_h8_dos_ajustes_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8: dos ajustes (invernaderos distintos) a la vez asientan con los números 1 y 2: el segundo espera el bloqueo del ejercicio, relee el número."""
        ejercicio_abierto(datetime.date(2027, 1, 1))
        self.preparar_segundo_invernadero()
        a = self.ajuste(self.HOY)
        b = self.ajuste(self.HOY, iin=self.iin_b, actor=self.otro, lote_a_romper=self.lote_b)
        resultados = correr_a_la_vez(a, b, primera="a")
        self.sin_errores(resultados)
        self.assertEqual(resultados["a"].asientos[0].numero_asiento, 1)  # la primera tomó el bloqueo del ejercicio antes
        self.assertEqual(resultados["b"].asientos[0].numero_asiento, 2)
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 2)
        self.invariantes()
        verificar_invariantes(self.iin_b)

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_el_ajuste_bloquea(self):
        """D-86 punto 2: el ajuste A se detiene justo ANTES de bloquear el ejercicio, con sus bloqueos de inventario ya tomados; el ajuste B (otro
        invernadero) asienta completo y toma el N.º 1. Si A hubiera bloqueado el ejercicio antes que sus filas, B esperaría y el orden sería el inverso."""
        ejercicio_abierto(datetime.date(2027, 1, 1))
        self.preparar_segundo_invernadero()
        a = self.ajuste(self.HOY)
        b = self.ajuste(self.HOY, iin=self.iin_b, actor=self.otro, lote_a_romper=self.lote_b)
        resultados = correr_a_la_vez(a, b, primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio"))
        self.sin_errores(resultados)
        self.assertEqual(resultados["b"].asientos[0].numero_asiento, 1)
        self.assertEqual(resultados["a"].asientos[0].numero_asiento, 2)
        self.invariantes()
