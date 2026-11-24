# Pruebas de concurrencia de la apertura de ejercicios (CON-02 paso 3; CON-ABR-EJE «Pruebas»; D-84 punto 2; docs/patrones/bloqueos.md, sección «Contabilidad»):
# dos aperturas a la vez de un abierto vencido (una sola crea) y dos primeras puestas en marcha a la vez (una sola crea; la otra atrapa el
# `IntegrityError` de la restricción única y sigue). Dos hilos con `correr_a_la_vez`: la primera operación se detiene después de auditar
# (con el bloqueo tomado y sin confirmar) y entonces arranca la otra. Cada una tiene que fallar si se quita la protección que cuida.
import datetime

from django.db import IntegrityError
from django.test import TransactionTestCase, tag

from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios
from contabilidad.tests.fabricas import ejercicio_abierto, verificar_invariantes_contables
from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez

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

    def test_regla_4_dos_puestas_en_marcha_a_la_vez_crean_un_solo_primer_ejercicio(self):
        """Regla 4 de CON-ABR-EJE y docs/patrones/asientos.md, sección 2: sin nada que bloquear, la restricción única respalda; la segunda atrapa el `IntegrityError`, relee y sigue."""
        hoy = datetime.date(2027, 5, 20)

        def crear():
            return ejercicios.abrir_ejercicio_si_corresponde(hoy)

        resultados = correr_a_la_vez(crear, crear, primera="a")

        errores = [r for r in resultados.values() if isinstance(r, Exception)]
        self.assertEqual(errores, [], "la segunda no puede fallar con un IntegrityError: tiene que releer y seguir")
        self.assertFalse([r for r in resultados.values() if isinstance(r, IntegrityError)])
        creados = [r for r in resultados.values() if r.primero_creado is not None]
        self.assertEqual(len(creados), 1)
        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion=RegistroAuditoria.Accion.ALTA_EJERCICIO_CONTABLE).count(), 1)

    def test_regla_4_crear_primer_ejercicio_a_la_vez_deja_uno_solo(self):
        """D-84 punto 3: el comando y la primera operación a la vez no duplican el primer ejercicio."""
        hoy = datetime.date(2027, 5, 20)

        resultados = correr_a_la_vez(
            lambda: ejercicios.crear_primer_ejercicio(datetime.date(2027, 5, 1), hoy=hoy),
            lambda: ejercicios.abrir_ejercicio_si_corresponde(hoy),
            primera="a",
        )

        self.assertEqual([r for r in resultados.values() if isinstance(r, Exception)], [])
        self.assertEqual(EjercicioContable.objects.count(), 1)
        self.assertEqual(EjercicioContable.objects.get().fecha_inicio_ejercicio, datetime.date(2027, 5, 1))
