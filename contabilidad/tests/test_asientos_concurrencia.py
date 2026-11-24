# Pruebas de concurrencia de `registrar_asiento_automatico` (CON-02 paso 4; D-84 punto 4; D-86 punto 2; docs/patrones/bloqueos.md, sección «Contabilidad»,
# y docs/patrones/asientos.md, sección 2 «El orden de bloqueos: el ejercicio va último»). Dos hilos con `correr_a_la_vez`: la primera operación se
# detiene en un punto fijo y entonces arranca la otra. Cada una tiene que fallar si se quita el bloqueo del ejercicio o se invierte el orden.
import datetime
from decimal import Decimal

from django.test import TransactionTestCase, tag

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import (
    asegurar_plan_de_cuentas,
    ejercicio_abierto,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.tests.concurrencia import correr_a_la_vez

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
