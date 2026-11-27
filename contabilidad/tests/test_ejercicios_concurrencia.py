# Pruebas de concurrencia de la apertura de ejercicios (CON-02 paso 3; CON-ABR-EJE «Pruebas»; D-84 punto 2; docs/patrones/bloqueos.md, sección «Contabilidad»):
# dos aperturas a la vez de un abierto vencido (una sola crea) (la puesta en marcha a la vez la prueba CON-INI-EJE, paso 2 de CON-05: sin ejercicio la apertura no escribe nada y no hay qué disputar). Dos hilos con `correr_a_la_vez`: la primera operación se detiene después de auditar
# (con el bloqueo tomado y sin confirmar) y entonces arranca la otra. Cada una tiene que fallar si se quita la protección que cuida.
import datetime
from decimal import Decimal

from django.core.cache import cache
from django.test import TransactionTestCase, tag

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios
from contabilidad.tests.fabricas import (
    asegurar_plan_de_cuentas,
    ejercicio,
    ejercicio_abierto,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import Contador, RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
INICIO = datetime.date(2027, 1, 1)
DIA_SIGUIENTE = datetime.date(2028, 1, 1)


@tag("concurrencia")
class ConAbrEjeConcurrenciaTests(TransactionTestCase):
    """CON-ABR-EJE: la apertura es una sola función idempotente aunque corra dos veces a la vez (paso diario y autorrecuperación)."""

    def test_regla_5_dos_aperturas_a_la_vez_de_un_abierto_vencido_crean_un_solo_ejercicio(self):
        """Regla 5 de CON-ABR-EJE y D-84 punto 2: la segunda espera el bloqueo del ejercicio, relee y no hace nada; no se duplica el nuevo."""
        ejercicio_abierto(INICIO)

        def abrir():
            return ejercicios.abrir_ejercicio_si_corresponde(DIA_SIGUIENTE)

        resultados = correr_a_la_vez(abrir, abrir, primera="a")

        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual(errores, [])
        hicieron_algo = [r for r in resultados.values() if r.nuevo_abierto is not None]
        self.assertEqual(len(hicieron_algo), 1)
        self.assertEqual(EjercicioContable.objects.count(), 2)
        self.assertEqual(
            {e.fecha_inicio_ejercicio: e.estado_ejercicio for e in EjercicioContable.objects.all()},
            {INICIO: Estado.EN_CIERRE, DIA_SIGUIENTE: Estado.ABIERTO},
        )
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_EJERCICIO_CONTABLE).count(), 1)
        verificar_invariantes_contables()


@tag("concurrencia")
class ConCrrEjeConcurrenciaTests(TransactionTestCase):
    """CON-CRR-EJE (CON-03a paso 3; docs/patrones/asientos.md, sección 2): el cierre bloquea SOLO la fila del ejercicio (`FOR NO KEY UPDATE`) y relee su estado
    después de bloquear; un asiento o la apertura que llegan a la vez ven el ejercicio ya cerrado, o entran antes del cierre, pero nunca quedan en uno cerrado.

    Escenario: el ejercicio de 2026 «en cierre» (id menor) y el de 2027 «abierto». «Hoy» es siempre un argumento: ninguna operación lee la hora sola."""

    HOY = datetime.date(2027, 3, 10)
    FECHA_DE_2026 = datetime.date(2026, 12, 1)
    MOVIMIENTOS = [(cuentas.CAJA, DEBE, Decimal("100.00")), (cuentas.VENTAS, HABER, Decimal("100.00"))]

    def setUp(self):
        cache.clear()  # el responsable contable no debe quedar en un caché de otra prueba
        asegurar_plan_de_cuentas()  # el `flush` de este TransactionTestCase vacía el plan en cada prueba
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio_abierto(datetime.date(2027, 1, 1))

    def _cerrar(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

    def _asentar(self):
        origen = origen_de_prueba()
        return lambda: asientos.registrar_asiento_automatico(None, origen, self.FECHA_DE_2026, self.MOVIMIENTOS, hoy=self.HOY)

    def _auditorias_del_2026(self):
        return RegistroAuditoria.objects.filter(
            accion=RegistroAuditoria.Accion.MODIFICACION_EJERCICIO_CONTABLE, afectados__contains=[{"id": self.en_cierre.pk}]
        )

    def test_regla_2_el_cierre_primero_y_un_asiento_a_la_vez_el_asiento_va_al_abierto(self):
        """El cierre ya tomó el bloqueo del ejercicio (sin confirmar) y el asiento, que eligió ese ejercicio «en cierre», espera; al confirmarse el cierre relee, lo ve «cerrado» y va al abierto con la aclaración de H10 (D-102)."""
        resultados = correr_a_la_vez(self._cerrar(), self._asentar(), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        asiento = resultados["b"]
        self.assertEqual(asiento.ejercicio_id, self.abierto.pk)
        self.assertEqual(asiento.fecha_asiento, self.HOY)
        self.assertIn("Fecha del hecho: 01/12/2026", asiento.descripcion_asiento)
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.assertEqual(AsientoContable.objects.filter(ejercicio=self.en_cierre).count(), 0)
        verificar_invariantes_contables()

    def test_regla_2_el_asiento_primero_y_el_cierre_a_la_vez_el_asiento_entra_antes_del_cierre(self):
        """El asiento ya tomó el bloqueo del ejercicio «en cierre» y numeró; el cierre espera, y al confirmarse el asiento cierra el ejercicio con ese asiento adentro (entró antes del cierre)."""
        resultados = correr_a_la_vez(self._asentar(), self._cerrar(), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(resultados["a"].ejercicio_id, self.en_cierre.pk)
        self.assertEqual(resultados["a"].numero_asiento, 1)
        cerrado = EjercicioContable.objects.get(pk=self.en_cierre.pk)
        self.assertEqual((cerrado.estado_ejercicio, cerrado.ultimo_numero_asiento), (EjercicioContable.Estado.CERRADO, 1))
        verificar_invariantes_contables()

    def test_regla_5_dos_cierres_a_la_vez_cierran_una_sola_vez(self):
        """Orden del cierre (2): el segundo espera el bloqueo, relee, ve el ejercicio «cerrado» y recibe `ejercicio_no_esta_en_cierre`; una sola auditoría."""
        resultados = correr_a_la_vez(self._cerrar(), self._cerrar(), primera="a")

        self.assertEqual(resultados["a"].estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "ejercicio_no_esta_en_cierre")
        self.assertEqual(self._auditorias_del_2026().count(), 1)
        verificar_invariantes_contables()

    def test_regla_1_el_cierre_primero_y_la_apertura_a_la_vez_el_sistema_no_lo_cierra_dos_veces(self):
        """CON-ABR-EJE (C1) contra el cierre manual: el abierto de 2027 venció; el cierre toma el bloqueo del «en cierre» y la apertura espera; al confirmarse la apertura relee, ya no hay «en cierre» que cerrar solo y pasa el abierto a «en cierre». Queda uno cerrado por el Contador (no «cierre automático»)."""
        hoy = datetime.date(2028, 1, 10)

        resultados = correr_a_la_vez(self._cerrar(), lambda: ejercicios.abrir_ejercicio_si_corresponde(hoy), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertIsNone(resultados["b"].cerrado_solo)
        cerrado = EjercicioContable.objects.get(pk=self.en_cierre.pk)
        self.assertEqual((cerrado.estado_ejercicio, cerrado.contador_id), (EjercicioContable.Estado.CERRADO, self.contador.pk))
        self.assertEqual(
            {e.fecha_inicio_ejercicio.year: e.estado_ejercicio for e in EjercicioContable.objects.all()},
            {2026: "cerrado", 2027: "en_cierre", 2028: "abierto"},
        )
        self.assertEqual(self._auditorias_del_2026().count(), 1)
        verificar_invariantes_contables()

    def test_regla_1_la_apertura_primero_y_el_cierre_a_la_vez_el_cierre_ve_que_ya_se_cerro_solo(self):
        """La apertura cerró sola el ejercicio «en cierre» (C1) y todavía no confirmó; el cierre espera, relee y recibe `ejercicio_no_esta_en_cierre`: no se cierra dos veces ni se pisa el cierre del Sistema."""
        hoy = datetime.date(2028, 1, 10)

        resultados = correr_a_la_vez(lambda: ejercicios.abrir_ejercicio_si_corresponde(hoy), self._cerrar(), primera="a")

        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "ejercicio_no_esta_en_cierre")
        cerrado = EjercicioContable.objects.get(pk=self.en_cierre.pk)
        self.assertEqual((cerrado.estado_ejercicio, cerrado.contador_id), (EjercicioContable.Estado.CERRADO, None))
        self.assertEqual(self._auditorias_del_2026().count(), 1)
        verificar_invariantes_contables()


@tag("concurrencia")
class ConIniEjeConcurrenciaTests(TransactionTestCase):
    """CON-INI-EJE, requisito especial y extensión 7a: dos inicios a la vez crean un solo ejercicio. Sin ejercicio no hay fila que bloquear: la que lo evita es
    la restricción única de la base (`un_solo_ejercicio_abierto`); el segundo espera, recibe el `IntegrityError` y lo traduce a `contabilidad_ya_iniciada`."""

    HOY = datetime.date(2027, 3, 10)
    IMPORTES = {cuentas.CAJA: Decimal("1000.00"), cuentas.CAPITAL_INICIAL: Decimal("1000.00")}

    def setUp(self):
        cache.clear()
        asegurar_plan_de_cuentas()
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")

    def _iniciar(self, fecha):
        return lambda: ejercicios.iniciar_ejercicio(self.contador, fecha, self.IMPORTES, hoy=self.HOY)

    def test_requisito_dos_inicios_a_la_vez_uno_gana_y_el_otro_recibe_contabilidad_ya_iniciada(self):
        """Requisito especial y 7a: la primera ya creó el ejercicio (sin confirmar) y la segunda espera; al confirmarse la primera, la segunda recibe
        `contabilidad_ya_iniciada` (nunca un `IntegrityError`) y queda un solo ejercicio con un solo asiento, el de apertura."""
        resultados = correr_a_la_vez(self._iniciar(datetime.date(2027, 1, 1)), self._iniciar(datetime.date(2027, 2, 1)), primera="a")

        self.assertIsInstance(resultados["a"], AsientoContable)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "contabilidad_ya_iniciada")
        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertEqual(EjercicioContable.objects.get().fecha_inicio_ejercicio, datetime.date(2027, 1, 1))
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_EJERCICIO_CONTABLE).count(), 1)
        verificar_invariantes_contables()

    def test_requisito_si_gana_la_segunda_el_resultado_es_simetrico(self):
        """Requisito especial: da lo mismo cuál de las dos arranca primero; la que llega segunda recibe `contabilidad_ya_iniciada`."""
        resultados = correr_a_la_vez(self._iniciar(datetime.date(2027, 1, 1)), self._iniciar(datetime.date(2027, 2, 1)), primera="b")

        self.assertIsInstance(resultados["b"], AsientoContable)
        self.assertEqual(resultados["a"].codigo, "contabilidad_ya_iniciada")
        self.assertEqual(EjercicioContable.objects.get().fecha_inicio_ejercicio, datetime.date(2027, 2, 1))
        self.assertEqual(AsientoContable.objects.count(), 1)
