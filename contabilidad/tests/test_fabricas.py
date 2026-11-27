# Pruebas de las utilidades de prueba para las demás apps (CON-02 paso 5; docs/api/asientos.md, «Pruebas de tu app»): las fábricas de ejercicio y de
# asiento y `verificar_invariantes_contables`, que tiene que dejar pasar lo correcto y atrapar cada invariante roto.
import datetime
from decimal import Decimal

from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import asientos
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    asiento_de_prueba,
    ejercicio,
    ejercicio_abierto,
    origen_de_prueba,
    verificar_invariantes_contables,
)

Estado = EjercicioContable.Estado
INICIO = datetime.date(2027, 1, 1)


class FabricasTests(PlanDeCuentasMixin, TestCase):
    """Las fábricas arman datos válidos y `verificar_invariantes_contables` los acepta (docs/api/asientos.md, «Pruebas de tu app»)."""

    def test_api_ejercicio_abierto_usa_hoy_y_el_cierre_previsto(self):
        """API: `ejercicio_abierto(inicio=None, cierre=None)` crea el abierto (hoy por defecto) con cierre de doce meses menos un día."""
        creado = ejercicio_abierto(INICIO)

        self.assertEqual((creado.estado_ejercicio, creado.fecha_cierre_ejercicio), (Estado.ABIERTO, datetime.date(2027, 12, 31)))

    def test_api_ejercicio_crea_en_el_estado_pedido(self):
        """API: `ejercicio(estado, inicio, cierre)` crea un ejercicio en ese estado."""
        creado = ejercicio(Estado.CERRADO, INICIO, datetime.date(2027, 6, 30))

        self.assertEqual((creado.estado_ejercicio, creado.fecha_cierre_ejercicio), (Estado.CERRADO, datetime.date(2027, 6, 30)))

    def test_api_asiento_de_prueba_numera_y_balancea(self):
        """API: `asiento_de_prueba` toma el número siguiente, suma `ultimo_numero_asiento` y por defecto es Caja a Capital Inicial por 100,00."""
        abierto = ejercicio_abierto(INICIO)
        primero = asiento_de_prueba(abierto, INICIO)
        segundo = asiento_de_prueba(abierto, INICIO, origen=origen_de_prueba())

        self.assertEqual((primero.numero_asiento, segundo.numero_asiento, abierto.ultimo_numero_asiento), (1, 2, 2))
        self.assertEqual(primero.descripcion_asiento, "Asiento de prueba")
        self.assertEqual(segundo.descripcion_asiento, "")
        self.assertEqual(
            sorted(primero.movimientos.values_list("cuenta__codigo_cuenta", "tipo_movimiento", "importe_movimiento")),
            [(cuentas.CAJA, "D", Decimal("100.00")), (cuentas.CAPITAL_INICIAL, "H", Decimal("100.00"))],
        )
        verificar_invariantes_contables()

    def test_api_origen_de_prueba_crea_un_documento_de_origen_valido(self):
        """API: `origen_de_prueba` crea una fila de `OrigenDocumento` con un tipo válido, sin hijas de nivel mayor (A1)."""
        origen = origen_de_prueba()

        self.assertIsNotNone(origen.pk)
        self.assertEqual(origen.tipo, "bitacora")

    def test_api_las_fabricas_y_el_servicio_conviven_y_pasan_los_invariantes(self):
        """API: `verificar_invariantes_contables()` al final de una prueba que mezcla asientos de la fábrica y del servicio."""
        abierto = ejercicio_abierto(INICIO)
        asiento_de_prueba(abierto, INICIO)
        hecho = asientos.registrar_asiento_automatico(
            None,
            origen_de_prueba(),
            INICIO,
            [(cuentas.CAJA, DEBE, Decimal("5.00")), (cuentas.VENTAS, HABER, Decimal("5.00"))],
            hoy=INICIO,
        )

        self.assertEqual(hecho.numero_asiento, 2)
        verificar_invariantes_contables()


class VerificarInvariantesTests(PlanDeCuentasMixin, TestCase):
    """Cada invariante roto lo atrapa `verificar_invariantes_contables` (por eso el resto de las pruebas pueden confiar en ella)."""

    def setUp(self):
        self.abierto = ejercicio_abierto(INICIO)

    def test_api_sin_datos_pasa(self):
        """Sin ejercicios ni asientos no hay nada que romper."""
        EjercicioContable.objects.all().delete()
        verificar_invariantes_contables()

    def test_api_atrapa_un_asiento_desbalanceado(self):
        """Invariante: Debe = Haber en cada asiento."""
        asiento_de_prueba(self.abierto, INICIO, [(cuentas.CAJA, DEBE, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("9.00"))])

        with self.assertRaisesRegex(AssertionError, "no está balanceado"):
            verificar_invariantes_contables()

    def test_api_atrapa_un_asiento_con_un_solo_movimiento(self):
        """Invariante: dos o más movimientos por asiento."""
        asiento_de_prueba(self.abierto, INICIO, [(cuentas.CAJA, DEBE, Decimal("10.00"))])

        with self.assertRaisesRegex(AssertionError, "hacen falta dos o más"):
            verificar_invariantes_contables()

    def test_api_atrapa_un_hueco_en_la_numeracion(self):
        """Invariante: numeración correlativa sin huecos por ejercicio."""
        asiento_de_prueba(self.abierto, INICIO)
        self.abierto.ultimo_numero_asiento = 2  # la fábrica toma el siguiente: el 3, salteando el 2
        asiento_de_prueba(self.abierto, INICIO)

        with self.assertRaisesRegex(AssertionError, "correlativa"):
            verificar_invariantes_contables()

    def test_api_atrapa_un_ultimo_numero_que_no_coincide(self):
        """Invariante: `ultimo_numero_asiento` es el último número usado."""
        asiento_de_prueba(self.abierto, INICIO)
        EjercicioContable.objects.filter(pk=self.abierto.pk).update(ultimo_numero_asiento=5)

        with self.assertRaisesRegex(AssertionError, "ultimo_numero_asiento"):
            verificar_invariantes_contables()

    def test_api_atrapa_rangos_que_se_pisan(self):
        """Invariante: los rangos de dos ejercicios no se superponen (no hay restricción de base: la verifica esta función)."""
        ejercicio(Estado.CERRADO, datetime.date(2026, 6, 1), datetime.date(2027, 5, 31))

        with self.assertRaisesRegex(AssertionError, "se pisan"):
            verificar_invariantes_contables()


class HelperDeContabilidadIniciadaTests(PlanDeCuentasMixin, TestCase):
    """`iniciar_contabilidad_para_pruebas` (CON-05, paso 5): deja la contabilidad iniciada para las pruebas de otras apps, y un ejercicio abierto propio de la prueba lo reemplaza."""

    def test_api_el_helper_crea_el_ejercicio_abierto_desde_hoy_sin_auditoria_ni_asientos(self):
        """API: crea el ejercicio abierto que empieza hoy (como la creación automática que reemplaza), sin auditoría ni asiento de apertura."""
        from contabilidad.servicios import ejercicios
        from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas
        from core.models import RegistroAuditoria

        creado = iniciar_contabilidad_para_pruebas()

        self.assertTrue(ejercicios.contabilidad_iniciada())
        self.assertEqual((creado.estado_ejercicio, creado.fecha_inicio_ejercicio), (Estado.ABIERTO, datetime.date.today()))
        self.assertFalse(AsientoContable.objects.exists())
        self.assertFalse(RegistroAuditoria.objects.exists())

    def test_api_el_helper_acepta_un_inicio_propio(self):
        """API: `iniciar_contabilidad_para_pruebas(inicio)` empieza en esa fecha."""
        from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

        self.assertEqual(iniciar_contabilidad_para_pruebas(INICIO).fecha_inicio_ejercicio, INICIO)

    def test_convencion_un_ejercicio_abierto_propio_reemplaza_al_del_helper(self):
        """Convención: la prueba que arma su propio ejercicio abierto no choca con la restricción de un solo abierto: el suyo reemplaza al del helper (sin asientos)."""
        from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

        iniciar_contabilidad_para_pruebas()
        propio = ejercicio_abierto(INICIO)

        self.assertEqual(list(EjercicioContable.objects.values_list("pk", flat=True)), [propio.pk])

    def test_convencion_un_ejercicio_cerrado_o_en_cierre_propio_no_reemplaza_al_del_helper(self):
        """Convención: un ejercicio cerrado o en cierre propio convive con el abierto del helper (las pruebas de H10 lo usan: el asiento va al abierto)."""
        from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

        abierto = iniciar_contabilidad_para_pruebas()
        ejercicio(Estado.CERRADO, datetime.date(2020, 1, 1))
        ejercicio(Estado.EN_CIERRE, datetime.date(2021, 1, 1))

        self.assertEqual(EjercicioContable.objects.count(), 3)
        self.assertTrue(EjercicioContable.objects.filter(pk=abierto.pk).exists())

    def test_convencion_el_del_helper_con_asientos_no_se_reemplaza(self):
        """Convención: si el ejercicio del helper ya tiene asientos no se borra (un asiento no se borra ni se mueve): crear otro abierto falla por la restricción única, a la vista."""
        from django.db import IntegrityError, transaction

        from contabilidad.tests.fabricas import iniciar_contabilidad_para_pruebas

        abierto = iniciar_contabilidad_para_pruebas()
        asiento_de_prueba(abierto, abierto.fecha_inicio_ejercicio)

        with self.assertRaises(IntegrityError), transaction.atomic():
            ejercicio_abierto(INICIO)
        self.assertTrue(EjercicioContable.objects.filter(pk=abierto.pk).exists())
