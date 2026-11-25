# Pruebas de concurrencia de `registrar_asiento_automatico` (CON-02 paso 4; D-84 punto 4; D-86 punto 2; docs/patrones/bloqueos.md, sección «Contabilidad»,
# y docs/patrones/asientos.md, sección 2 «El orden de bloqueos: el ejercicio va último»). Dos hilos con `correr_a_la_vez`: la primera operación se
# detiene en un punto fijo y entonces arranca la otra. Cada una tiene que fallar si se quita el bloqueo del ejercicio o se invierte el orden.
# CON-03b suma al final `ConRegAsiConcurrenciaTests` y `ConCtrAsiConcurrenciaTests` (asiento manual y contraasiento); las de CON-02 no se tocan.
import datetime
from decimal import Decimal

from django.test import TransactionTestCase, tag

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import (
    asegurar_plan_de_cuentas,
    asiento_de_prueba,
    ejercicio,
    ejercicio_abierto,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import Contador, Gerente, Notificacion
from core.tests.concurrencia import correr_a_la_vez
from core.tests.fabricas import crear_cuenta

INICIO = datetime.date(2027, 1, 1)
HOY = datetime.date(2027, 6, 15)
MOVIMIENTOS = [(cuentas.INSUMOS_EN_STOCK, DEBE, Decimal("3000.00")), (cuentas.PROVEEDORES, HABER, Decimal("3000.00"))]


def _asentar(origen, hoy=HOY, fecha=HOY):
    return lambda: asientos.registrar_asiento_automatico(None, origen, fecha, MOVIMIENTOS, hoy=hoy)


@tag("concurrencia")
class AsientosConcurrenciaTests(TransactionTestCase):
    """D-84 punto 4 y D-86 punto 2: la numeración sin huecos y un solo asiento por origen aunque dos operaciones asienten a la vez."""

    def setUp(self):
        asegurar_plan_de_cuentas()  # el `flush` de este TransactionTestCase vacía el plan en cada prueba
        self.ejercicio = ejercicio_abierto(INICIO)

    def test_regla_h8_dos_asientos_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8 y D-84 punto 4: dos asientos (orígenes distintos) a la vez toman el 1 y el 2: el segundo espera el bloqueo del ejercicio y relee el número."""
        origen_a, origen_b = origen_de_prueba(), origen_de_prueba()

        resultados = correr_a_la_vez(_asentar(origen_a), _asentar(origen_b), primera="a")

        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual(errores, [])
        self.assertEqual(sorted(r.numero_asiento for r in resultados.values()), [1, 2])
        self.assertEqual(resultados["a"].numero_asiento, 1)  # la primera tomó el bloqueo antes
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 2)
        verificar_invariantes_contables()

    def test_regla_d86_mismo_origen_a_la_vez_uno_solo_gana(self):
        """D-86 punto 5: dos llamadas a la vez con el MISMO origen: una asienta y la otra recibe `origen_con_asiento` de la verificación hecha con el ejercicio ya bloqueado."""
        origen = origen_de_prueba()

        resultados = correr_a_la_vez(_asentar(origen), _asentar(origen), primera="a")

        exitos = [r for r in resultados.values() if isinstance(r, AsientoContable)]
        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual(len(exitos), 1)
        self.assertEqual(len(errores), 1)
        self.assertIsInstance(errores[0], ErrorContable)
        self.assertEqual(errores[0].codigo, "origen_con_asiento")
        self.assertIsNone(
            errores[0].__cause__,
            "el rechazo tiene que salir de la verificación posterior al bloqueo, no del IntegrityError de la restricción única",
        )
        self.assertEqual(AsientoContable.objects.count(), 1)
        self.assertEqual(EjercicioContable.objects.get().ultimo_numero_asiento, 1)
        verificar_invariantes_contables()

    def test_regla_d86_el_ejercicio_es_lo_ultimo_que_se_bloquea(self):
        """D-86 punto 2: la primera se detiene justo ANTES de bloquear el ejercicio y la otra asienta completa (toma el 1): si la primera ya hubiera bloqueado el ejercicio, la otra esperaría y el orden sería el inverso."""
        origen_a, origen_b = origen_de_prueba(), origen_de_prueba()

        resultados = correr_a_la_vez(
            _asentar(origen_a), _asentar(origen_b), primera="a", detener_antes_de=(asientos, "_bloquear_ejercicio")
        )

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(resultados["b"].numero_asiento, 1)
        self.assertEqual(resultados["a"].numero_asiento, 2)
        verificar_invariantes_contables()

    def test_regla_5_dos_asientos_a_la_vez_con_el_abierto_vencido_abren_un_solo_ejercicio(self):
        """CON-ABR-EJE regla 5: la autorrecuperación a la vez abre UN solo ejercicio nuevo y los dos asientos numeran 1 y 2 en él."""
        hoy = datetime.date(2028, 2, 10)
        origen_a, origen_b = origen_de_prueba(), origen_de_prueba()

        resultados = correr_a_la_vez(
            _asentar(origen_a, hoy=hoy, fecha=hoy), _asentar(origen_b, hoy=hoy, fecha=hoy), primera="a"
        )

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(EjercicioContable.objects.count(), 2)
        nuevo = EjercicioContable.objects.get(estado_ejercicio=EjercicioContable.Estado.ABIERTO)
        self.assertEqual(sorted((r.ejercicio_id, r.numero_asiento) for r in resultados.values()), [(nuevo.pk, 1), (nuevo.pk, 2)])
        verificar_invariantes_contables()


# --- CON-03b: asiento manual y contraasiento --------------------------------------------------------------------------------------------------------

EN_CIERRE_INICIO = datetime.date(2026, 1, 1)
DEL_EN_CIERRE = datetime.date(2026, 12, 1)
MOTIVO = "Se cargó un importe de más"
GASTO = [(cuentas.GASTOS_GENERALES, DEBE, Decimal("1000.00")), (cuentas.CAJA, HABER, Decimal("1000.00"))]


class _EscenarioDeManuales:
    """Un ejercicio en cierre (2026) y uno abierto (2027), un Contador y un Gerente activos; hoy es el 15/6/2027. Lo usan las dos clases de abajo."""

    def preparar(self):
        asegurar_plan_de_cuentas()  # el `flush` de este TransactionTestCase vacía el plan en cada prueba
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com", nombre="Cora", apellido="Díaz")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com", nombre="Gabriela", apellido="Sosa")
        self.en_cierre = ejercicio(EjercicioContable.Estado.EN_CIERRE, EN_CIERRE_INICIO)
        self.abierto = ejercicio(EjercicioContable.Estado.ABIERTO, INICIO)

    def manual(self, fecha=HOY, descripcion="Gasto de prueba"):
        return lambda: asientos.registrar_asiento_manual(self.contador, fecha, descripcion, GASTO, hoy=HOY)

    def contraasentar(self, asiento, fecha=HOY):
        return lambda: asientos.contraasentar(self.contador, asiento.pk, fecha, MOTIVO, hoy=HOY)

    def cerrar_el_ejercicio_en_cierre(self):
        return lambda: ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)


@tag("concurrencia")
class ConRegAsiConcurrenciaTests(_EscenarioDeManuales, TransactionTestCase):
    """CON-REG-ASI, requisitos especiales: `select_for_update` sobre el ejercicio da numeración correlativa sin huecos y el registro respeta el cierre."""

    def setUp(self):
        self.preparar()

    def test_regla_h8_dos_asientos_manuales_a_la_vez_toman_numeros_consecutivos_sin_hueco(self):
        """H8 y requisitos especiales de CON-REG-ASI: dos manuales a la vez toman el 1 y el 2; el segundo espera el bloqueo del ejercicio y relee el número."""
        resultados = correr_a_la_vez(self.manual(descripcion="Uno"), self.manual(descripcion="Dos"), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual((resultados["a"].numero_asiento, resultados["b"].numero_asiento), (1, 2))  # la primera tomó el bloqueo antes
        self.assertEqual(EjercicioContable.objects.get(pk=self.abierto.pk).ultimo_numero_asiento, 2)
        verificar_invariantes_contables()

    def test_ext_7b_si_el_cierre_toma_el_bloqueo_primero_el_manual_se_rechaza(self):
        """Extensión 7b: el cierre del ejercicio toma el bloqueo primero; el manual (con fecha en ese ejercicio) espera, lo ve «cerrado» y no registra nada
        (`cambio_simultaneo`)."""
        resultados = correr_a_la_vez(self.cerrar_el_ejercicio_en_cierre(), self.manual(DEL_EN_CIERRE), primera="a")

        self.assertEqual(resultados["a"].estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "cambio_simultaneo")
        self.assertIsNone(resultados["b"].__cause__)
        self.assertFalse(AsientoContable.objects.exists())
        self.assertEqual(EjercicioContable.objects.get(pk=self.en_cierre.pk).ultimo_numero_asiento, 0)
        verificar_invariantes_contables()

    def test_ext_7b_si_el_manual_toma_el_bloqueo_primero_entra_y_despues_se_cierra(self):
        """Al revés: el manual toma el bloqueo primero y entra con el número 1; el cierre espera y cierra después, con el asiento ya dentro."""
        resultados = correr_a_la_vez(self.manual(DEL_EN_CIERRE), self.cerrar_el_ejercicio_en_cierre(), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(resultados["a"].numero_asiento, 1)
        self.assertEqual(resultados["b"].estado_ejercicio, EjercicioContable.Estado.CERRADO)
        self.assertEqual(AsientoContable.objects.filter(ejercicio_id=self.en_cierre.pk).count(), 1)
        verificar_invariantes_contables()


@tag("concurrencia")
class ConCtrAsiConcurrenciaTests(_EscenarioDeManuales, TransactionTestCase):
    """CON-CTR-ASI, requisitos especiales: dos usuarios no anulan el mismo asiento a la vez, dos asientos no toman el mismo número y se bloquea primero el
    asiento y después el ejercicio (docs/patrones/asientos.md, sección 2)."""

    def setUp(self):
        self.preparar()
        self.original = asiento_de_prueba(self.abierto, datetime.date(2027, 2, 1), GASTO, descripcion="Pago de la luz")

    def test_ext_6a_dos_contraasientos_del_mismo_asiento_a_la_vez_gana_uno_solo(self):
        """Extensión 6a: dos contraasientos del mismo asiento a la vez; uno gana, el otro espera el bloqueo del asiento y recibe `asiento_no_anulable`, que sale
        de la verificación posterior al bloqueo (no de la restricción única de la base). Queda un solo contraasiento, un solo aviso y numeración sin hueco."""
        resultados = correr_a_la_vez(self.contraasentar(self.original), self.contraasentar(self.original), primera="a")

        self.assertIsInstance(resultados["a"], AsientoContable)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "asiento_no_anulable")
        self.assertIn("N.º 2", resultados["b"].mensaje)
        self.assertIsNone(resultados["b"].__cause__, "el rechazo tiene que salir de la verificación posterior al bloqueo, no del IntegrityError de R161")
        self.assertEqual(AsientoContable.objects.filter(anula=self.original).count(), 1)
        self.assertEqual(AsientoContable.objects.count(), 2)
        self.assertEqual(EjercicioContable.objects.get(pk=self.abierto.pk).ultimo_numero_asiento, 2)
        self.assertEqual(Notificacion.objects.count(), 1)
        verificar_invariantes_contables()

    def test_regla_h8_dos_contraasientos_de_asientos_distintos_a_la_vez_toman_numeros_consecutivos(self):
        """H8: dos contraasientos de asientos distintos a la vez toman el 3 y el 4 (el 1 y el 2 son los originales); el segundo espera el bloqueo del ejercicio."""
        otro = asiento_de_prueba(EjercicioContable.objects.get(pk=self.abierto.pk), datetime.date(2027, 2, 3), GASTO, descripcion="Otro gasto")

        resultados = correr_a_la_vez(self.contraasentar(self.original), self.contraasentar(otro), primera="a")

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual((resultados["a"].numero_asiento, resultados["b"].numero_asiento), (3, 4))
        verificar_invariantes_contables()

    def test_regla_orden_de_bloqueos_el_contraasiento_ya_tiene_el_asiento_antes_de_pedir_el_ejercicio(self):
        """Orden de bloqueos (asiento antes que ejercicio): se detiene al primero justo ANTES de bloquear el ejercicio, cuando ya tiene el asiento. El segundo
        intenta el mismo asiento, queda esperando y pierde: gana el que se detuvo. Con el orden invertido, el primero no tendría nada tomado, el segundo
        pasaría de largo y ganaría él."""
        resultados = correr_a_la_vez(
            self.contraasentar(self.original),
            self.contraasentar(self.original),
            primera="a",
            detener_antes_de=(asientos, "_bloquear_ejercicio"),
        )

        self.assertIsInstance(resultados["a"], AsientoContable)
        self.assertIsInstance(resultados["b"], ErrorContable)
        self.assertEqual(resultados["b"].codigo, "asiento_no_anulable")
        verificar_invariantes_contables()

    def test_regla_orden_de_bloqueos_el_contraasiento_no_tiene_el_ejercicio_hasta_haber_bloqueado_el_asiento(self):
        """Orden de bloqueos (el ejercicio, lo último): se detiene al contraasiento justo ANTES de bloquear el asiento y un asiento manual corre completo (toma el
        número 2). Si el contraasiento ya hubiera bloqueado el ejercicio, el manual esperaría y los números saldrían al revés."""
        resultados = correr_a_la_vez(
            self.contraasentar(self.original),
            self.manual(datetime.date(2027, 2, 5), "Manual en medio"),
            primera="a",
            detener_antes_de=(asientos, "_bloquear_asiento"),
        )

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(resultados["b"].numero_asiento, 2)  # el manual terminó primero
        self.assertEqual(resultados["a"].numero_asiento, 3)
        verificar_invariantes_contables()
