# Pruebas de CON-CRR-EJE «Cerrar Ejercicio Contable» (CON-03a paso 3; docs/casos_de_uso/contabilidad/ejercicio.md; D-84 puntos 2, 5 y 9; D-85 punto 5; D-102):
# `ejercicios.cerrar_ejercicio` y `ejercicios.resumen_para_cierre`. Cada prueba arma sus datos y recibe «hoy» (nunca lee la hora sola).
# Escenario común: el ejercicio de 2026 «en cierre» y el de 2027 «abierto»; hoy es el 10/3/2027.
import datetime
from decimal import Decimal
from unittest import mock

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, ejercicios, libro
from contabilidad.tests.fabricas import (
    PlanDeCuentasMixin,
    asiento_de_prueba,
    ejercicio,
    origen_de_prueba,
    verificar_invariantes_contables,
)
from core.models import Agronomo, Contador, Gerente, RegistroAuditoria, Vendedor
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion
HOY = datetime.date(2027, 3, 10)
FECHA_DE_2026 = datetime.date(2026, 12, 1)


def _d(texto):
    return Decimal(texto)


def _caja_a_ventas(importe="100.00"):
    return [(cuentas.CAJA, DEBE, _d(importe)), (cuentas.VENTAS, HABER, _d(importe))]


class ConCrrEjeBase(PlanDeCuentasMixin, TestCase):
    def setUp(self):
        self.contador = crear_cuenta(Contador, email="contador@infoponia.com")
        self.gerente = crear_cuenta(Gerente, email="gerente@infoponia.com")
        self.en_cierre = ejercicio(Estado.EN_CIERRE, datetime.date(2026, 1, 1))
        self.abierto = ejercicio(Estado.ABIERTO, datetime.date(2027, 1, 1))

    def recargar(self, ej):
        return EjercicioContable.objects.get(pk=ej.pk)

    def registros_de_cierre(self):
        return RegistroAuditoria.objects.filter(accion=Accion.MODIFICACION_EJERCICIO_CONTABLE, afectados__contains=[{"id": self.en_cierre.pk}])


class ConCrrEjePermisosTests(ConCrrEjeBase):
    """Precondición a y regla 5: lo cierra el Contador; el Gerente solo si no hay un Contador activo."""

    def test_regla_5_el_contador_activo_cierra(self):
        """Regla 5 de CON-CRR-EJE: el Contador cierra el ejercicio en cierre."""
        cerrado = ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        self.assertEqual(cerrado.estado_ejercicio, Estado.CERRADO)

    def test_regla_5_el_gerente_cierra_si_no_hay_contador_activo(self):
        """Regla 5 y D-85 punto 4: sin Contador activo, el Gerente hace lo del Contador."""
        Contador.objects.update(is_active=False)

        cerrado = ejercicios.cerrar_ejercicio(self.gerente, self.en_cierre.pk)

        self.assertEqual(cerrado.estado_ejercicio, Estado.CERRADO)

    def test_regla_5_el_gerente_con_contador_activo_es_rechazado(self):
        """Regla 5: el Gerente solo cierra si no hay un Contador activo; con uno, `PermissionDenied` y no cambia nada."""
        with self.assertRaises(PermissionDenied):
            ejercicios.cerrar_ejercicio(self.gerente, self.en_cierre.pk)

        self.assertEqual(self.recargar(self.en_cierre).estado_ejercicio, Estado.EN_CIERRE)
        self.assertFalse(self.registros_de_cierre().exists())

    def test_regla_5_el_vendedor_y_los_demas_roles_son_rechazados(self):
        """Regla 5 y D-85 punto 8: el Vendedor y los demás roles no cierran, ni siquiera sin Contador activo."""
        Contador.objects.update(is_active=False)
        for clase, email in ((Vendedor, "v@infoponia.com"), (Agronomo, "a@infoponia.com")):
            with self.subTest(rol=clase.__name__):
                with self.assertRaises(PermissionDenied):
                    ejercicios.cerrar_ejercicio(crear_cuenta(clase, email=email), self.en_cierre.pk)

        self.assertEqual(self.recargar(self.en_cierre).estado_ejercicio, Estado.EN_CIERRE)

    def test_precondicion_a_un_contador_dado_de_baja_o_ninguna_cuenta_no_cierran(self):
        """Precondición a: «cuenta activa»; un Contador dado de baja (aunque la instancia en memoria siga activa) o ninguna cuenta se rechazan."""
        instancia_vieja = self.contador
        Contador.objects.update(is_active=False)

        with self.assertRaises(PermissionDenied):
            ejercicios.cerrar_ejercicio(instancia_vieja, self.en_cierre.pk)
        with self.assertRaises(PermissionDenied):
            ejercicios.cerrar_ejercicio(None, self.en_cierre.pk)

    def test_precondicion_a_si_dejo_de_ser_el_responsable_mientras_esperaba_no_cierra(self):
        """D-84 punto 9 y orden del cierre (3): después de bloquear el ejercicio se verifica de nuevo que el actor siga siendo quien cierra."""
        with mock.patch.object(ejercicios.responsables, "puede_registrar_asientos", side_effect=[True, False]):
            with self.assertRaises(PermissionDenied):
                ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        self.assertEqual(self.recargar(self.en_cierre).estado_ejercicio, Estado.EN_CIERRE)
        self.assertFalse(self.registros_de_cierre().exists())


class ConCrrEjeReglasTests(ConCrrEjeBase):
    """Reglas 1 a 3 y postcondiciones a, b y c."""

    def test_regla_1_el_ejercicio_abierto_no_se_cierra_a_mano(self):
        """Regla 1: solo se cierra uno «en cierre»; el abierto pasa a «en cierre» solo, con CON-ABR-EJE."""
        with self.assertRaises(ErrorContable) as contexto:
            ejercicios.cerrar_ejercicio(self.contador, self.abierto.pk)

        self.assertEqual(contexto.exception.codigo, "ejercicio_no_esta_en_cierre")
        self.assertEqual(self.recargar(self.abierto).estado_ejercicio, Estado.ABIERTO)

    def test_regla_2_el_cierre_es_definitivo_y_no_hay_reapertura(self):
        """Regla 2: un ejercicio cerrado no se cierra otra vez ni vuelve a otro estado (un segundo cierre es `ejercicio_no_esta_en_cierre`)."""
        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        with self.assertRaises(ErrorContable) as contexto:
            ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        self.assertEqual(contexto.exception.codigo, "ejercicio_no_esta_en_cierre")
        self.assertEqual(self.recargar(self.en_cierre).estado_ejercicio, Estado.CERRADO)
        self.assertEqual(self.registros_de_cierre().count(), 1)

    def test_un_ejercicio_inexistente_es_404(self):
        """Un id que no existe es 404 (D-28)."""
        with self.assertRaises(Http404):
            ejercicios.cerrar_ejercicio(self.contador, 999999)

    def test_regla_2_despues_del_cierre_un_asiento_automatico_con_fecha_en_su_rango_va_al_abierto(self):
        """Regla 2 y D-102 punto 1: «los que caerían en su rango van al ejercicio abierto»: el automático nunca se rechaza por la fecha; va al abierto con la fecha de hoy y la aclaración de H10."""
        antes = asientos.registrar_asiento_automatico(None, origen_de_prueba(), FECHA_DE_2026, _caja_a_ventas(), hoy=HOY)
        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        despues = asientos.registrar_asiento_automatico(None, origen_de_prueba(), FECHA_DE_2026, _caja_a_ventas(), hoy=HOY)

        self.assertEqual(antes.ejercicio, self.en_cierre)  # control: mientras estaba «en cierre» el asiento entraba en él
        self.assertEqual(despues.ejercicio, self.abierto)
        self.assertEqual(despues.fecha_asiento, HOY)
        self.assertIn("Fecha del hecho: 01/12/2026 (el ejercicio de esa fecha ya está cerrado); se registra con la fecha de hoy.", despues.descripcion_asiento)
        verificar_invariantes_contables()

    def test_regla_2_despues_del_cierre_un_asiento_manual_con_fecha_en_su_rango_se_rechaza(self):
        """Regla 2 y D-102 punto 3: un manual o un contraasiento (CON-03b) con fecha en un ejercicio cerrado se rechaza: `ejercicio_para(..., automatico=False)` lanza `fecha_en_ejercicio_cerrado`."""
        self.assertEqual(ejercicios.ejercicio_para(FECHA_DE_2026, automatico=False, hoy=HOY), self.en_cierre)  # control
        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        with self.assertRaises(ErrorContable) as contexto:
            ejercicios.ejercicio_para(FECHA_DE_2026, automatico=False, hoy=HOY)

        self.assertEqual(contexto.exception.codigo, "fecha_en_ejercicio_cerrado")

    def test_regla_3_el_cierre_no_genera_asientos_ni_cambia_los_saldos(self):
        """Regla 3 (H2.3): sin asientos de cierre ni refundición; el libro sigue calculando los saldos como antes (patrimoniales acumulados, de resultado por ejercicio)."""
        asiento_de_prueba(self.en_cierre, FECHA_DE_2026, _caja_a_ventas("500.00"))
        antes = libro.saldo_por_cuenta(self.abierto.pk)
        cantidad = AsientoContable.objects.count()

        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        self.assertEqual(AsientoContable.objects.count(), cantidad)
        self.assertEqual(libro.saldo_por_cuenta(self.abierto.pk), antes)
        self.assertEqual(antes[cuentas.CAJA].saldo_inicial, _d("500.00"))  # la patrimonial acumula
        self.assertEqual(antes[cuentas.VENTAS].saldo_inicial, _d("0.00"))  # la de resultado no

    def test_regla_4_el_cierre_no_tiene_verificaciones_que_lo_bloqueen(self):
        """Regla 4: cierra igual con asientos, anulados o sin ningún asiento; no hay nada que lo impida."""
        original = asiento_de_prueba(self.en_cierre, FECHA_DE_2026, _caja_a_ventas())
        asiento_de_prueba(self.en_cierre, FECHA_DE_2026, _caja_a_ventas(), anula=original)

        cerrado = ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        self.assertEqual(cerrado.estado_ejercicio, Estado.CERRADO)

    def test_post_a_y_b_el_contador_que_cierra_queda_asociado(self):
        """Postcondiciones a y b: pasó a «cerrado» y, si lo cerró el Contador, el ejercicio queda asociado a él (R010)."""
        cerrado = ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        guardado = self.recargar(self.en_cierre)
        self.assertEqual(guardado.estado_ejercicio, Estado.CERRADO)
        self.assertEqual(guardado.contador_id, self.contador.pk)
        self.assertEqual(cerrado.contador_id, self.contador.pk)

    def test_post_b_si_lo_cierra_el_gerente_la_asociacion_queda_vacia(self):
        """Postcondición b (patrón de R050, MD-61): si lo cerró el Gerente, la asociación queda vacía y la persona está en el log."""
        Contador.objects.update(is_active=False)

        ejercicios.cerrar_ejercicio(self.gerente, self.en_cierre.pk)

        self.assertIsNone(self.recargar(self.en_cierre).contador_id)

    def test_post_c_el_cierre_del_contador_se_audita_con_su_cambio_de_estado_y_el_contador(self):
        """Postcondición c y D-36: `modificacion_ejercicio_contable` con el usuario, su rol, el ejercicio afectado, `estado_ejercicio` en_cierre → cerrado, `contador` None → él y `datos.cerrado_por`."""
        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        registro = self.registros_de_cierre().get()
        self.assertEqual((registro.usuario_id, registro.rol), (self.contador.pk, "contador"))
        self.assertEqual(registro.afectados[0]["modelo"], "contabilidad.ejerciciocontable")
        self.assertEqual(registro.detalle["cambios"]["estado_ejercicio"], {"antes": "en_cierre", "despues": "cerrado"})
        self.assertEqual(registro.detalle["cambios"]["contador"]["antes"], None)
        self.assertEqual(registro.detalle["cambios"]["contador"]["despues"]["id"], self.contador.pk)
        self.assertEqual(registro.detalle["datos"], {"cerrado_por": "contador"})

    def test_post_c_el_cierre_del_gerente_se_audita_sin_cambio_de_contador(self):
        """Postcondición c: si cierra el Gerente el `contador` no cambia (queda vacío), así que no figura en `cambios`; sí `datos.cerrado_por`."""
        Contador.objects.update(is_active=False)

        ejercicios.cerrar_ejercicio(self.gerente, self.en_cierre.pk)

        registro = self.registros_de_cierre().get()
        self.assertEqual((registro.usuario_id, registro.rol), (self.gerente.pk, "gerente"))
        self.assertEqual(list(registro.detalle["cambios"]), ["estado_ejercicio"])
        self.assertEqual(registro.detalle["datos"], {"cerrado_por": "gerente"})

    def test_post_c_todo_o_nada_si_falla_la_auditoria_el_ejercicio_no_se_cierra(self):
        """D-22: la auditoría va en la misma transacción; si falla, el ejercicio sigue «en cierre»."""
        with mock.patch.object(RegistroAuditoria.objects, "registrar", side_effect=RuntimeError("falla")):
            with self.assertRaises(RuntimeError):
                ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        guardado = self.recargar(self.en_cierre)
        self.assertEqual((guardado.estado_ejercicio, guardado.contador_id), (Estado.EN_CIERRE, None))

    def test_el_cierre_no_toca_al_ejercicio_abierto(self):
        """El cierre solo cambia el ejercicio elegido: el abierto y su numeración quedan como estaban."""
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas())

        ejercicios.cerrar_ejercicio(self.contador, self.en_cierre.pk)

        abierto = self.recargar(self.abierto)
        self.assertEqual((abierto.estado_ejercicio, abierto.ultimo_numero_asiento), (Estado.ABIERTO, 1))
        verificar_invariantes_contables()


class ConCrrEjeResumenTests(ConCrrEjeBase):
    """Regla 4: el resumen previo (rango, cantidad de asientos, total del Debe y del Haber) que la pantalla muestra antes de confirmar."""

    def test_regla_4_el_resumen_trae_rango_cantidad_y_totales(self):
        """Regla 4 de CON-CRR-EJE: rango, cantidad de asientos, total del Debe y total del Haber (iguales: Debe = Haber)."""
        asiento_de_prueba(self.en_cierre, FECHA_DE_2026, _caja_a_ventas("100.00"))
        asiento_de_prueba(self.en_cierre, FECHA_DE_2026, [(cuentas.GASTOS_GENERALES, DEBE, _d("40.50")), (cuentas.CAJA, HABER, _d("40.50"))])
        asiento_de_prueba(self.abierto, HOY, _caja_a_ventas("999.00"))  # de otro ejercicio: no cuenta

        resumen = ejercicios.resumen_para_cierre(self.en_cierre.pk)

        self.assertEqual(resumen.ejercicio, self.en_cierre)
        self.assertEqual((resumen.ejercicio.fecha_inicio_ejercicio, resumen.ejercicio.fecha_cierre_ejercicio), (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)))
        self.assertEqual(resumen.cantidad_de_asientos, 2)
        self.assertEqual((resumen.total_debe, resumen.total_haber), (_d("140.50"), _d("140.50")))

    def test_regla_4_un_ejercicio_sin_asientos_tiene_el_resumen_en_cero(self):
        """El resumen de un ejercicio sin asientos no falla: cantidad 0 y totales en cero."""
        resumen = ejercicios.resumen_para_cierre(self.en_cierre.pk)

        self.assertEqual((resumen.cantidad_de_asientos, resumen.total_debe, resumen.total_haber), (0, _d("0.00"), _d("0.00")))

    def test_regla_4_el_resumen_es_de_lectura_y_no_audita(self):
        """«Hecho cuando» y SEG-14: el resumen no escribe nada."""
        antes = RegistroAuditoria.objects.count()

        ejercicios.resumen_para_cierre(self.en_cierre.pk)

        self.assertEqual(RegistroAuditoria.objects.count(), antes)
        self.assertEqual(self.recargar(self.en_cierre).estado_ejercicio, Estado.EN_CIERRE)

    def test_el_resumen_de_un_ejercicio_inexistente_es_404(self):
        """Un id que no existe es 404."""
        with self.assertRaises(Http404):
            ejercicios.resumen_para_cierre(999999)

    def test_el_resumen_hace_una_consulta_agregada_y_no_una_por_asiento(self):
        """CON-CRR-EJE, «Cómo se aplica»: «una consulta agregada»; con 1 o con 10 asientos hace las mismas consultas."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as pocas:
            ejercicios.resumen_para_cierre(self.en_cierre.pk)
        for _ in range(10):
            asiento_de_prueba(self.en_cierre, FECHA_DE_2026, _caja_a_ventas())
        with CaptureQueriesContext(connection) as muchas:
            ejercicios.resumen_para_cierre(self.en_cierre.pk)

        self.assertEqual(len(pocas), len(muchas))
