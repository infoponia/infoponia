# Recorrido de CON-02 (D-96, `docs/patrones/verificacion_a_mano.md`): una prueba larga que hace de punta a punta lo que hará la persona en la
# «Verificación a mano», con `hoy` simulado. La tarea no tiene pantallas: el recorrido usa el comando, los servicios y el proceso diario.
# Puesta en marcha → primer ejercicio → asiento automático (con sus movimientos y su auditoría) → numeración → asiento desbalanceado →
# paso diario 5 con fechas simuladas (el ejercicio abierto pasa a «en cierre» al día siguiente de su fecha de cierre) → asiento en cada
# ejercicio → un año más (el que estaba en cierre se cierra solo).
import datetime
import io
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable
from contabilidad.servicios import asientos, libro
from contabilidad.tests.fabricas import PlanDeCuentasMixin, origen_de_prueba, verificar_invariantes_contables
from core.models import Contador, Notificacion, RegistroAuditoria
from core.tests.fabricas import crear_cuenta

Estado = EjercicioContable.Estado
HOY = datetime.date(2027, 3, 10)


def _movimientos(importe):
    return [(cuentas.INSUMOS_EN_STOCK, DEBE, Decimal(importe)), (cuentas.PROVEEDORES, HABER, Decimal(importe))]


class RecorridoDeNucleoContableTests(PlanDeCuentasMixin, TestCase):
    """Recorrido por estado del ejercicio: abierto → en cierre → cerrado solo (D-84, CON-ABR-EJE, D-86)."""

    def test_recorrido_de_la_puesta_en_marcha_al_cierre_automatico(self):
        contador = crear_cuenta(Contador, email="contador@infoponia.com")

        # 1. Puesta en marcha con el comando: el primer ejercicio empieza el 1/1/2027.
        salida = io.StringIO()
        with mock.patch("django.utils.timezone.localdate", return_value=HOY):
            call_command("poner_en_marcha_contabilidad", "--fecha-inicio", "2027-01-01", stdout=salida)
        primero = EjercicioContable.objects.get()
        self.assertEqual((primero.estado_ejercicio, primero.fecha_cierre_ejercicio), (Estado.ABIERTO, datetime.date(2027, 12, 31)))
        self.assertIn("01/01/2027", salida.getvalue())

        # 2. Asiento automático (una recepción de 3.000): número 1, sus dos movimientos y su auditoría.
        recepcion = origen_de_prueba()
        asiento = asientos.registrar_asiento_automatico(contador, recepcion, datetime.date(2027, 3, 9), _movimientos("3000.00"), hoy=HOY)
        self.assertEqual((asiento.numero_asiento, asiento.ejercicio_id, asiento.tipo), (1, primero.pk, "automatico"))
        self.assertEqual(asiento.movimientos.count(), 2)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_asiento_contable", usuario=contador).count(), 1)
        self.assertEqual(RegistroAuditoria.objects.filter(accion="alta_movimiento_contable", usuario=contador).count(), 2)

        # 3. Numeración: el segundo asiento toma el 2; un asiento desbalanceado se rechaza y no consume número.
        segundo = asientos.registrar_asiento_automatico(contador, origen_de_prueba(), HOY, _movimientos("500.00"), hoy=HOY)
        self.assertEqual(segundo.numero_asiento, 2)
        with self.assertRaises(ErrorContable) as contexto:
            asientos.registrar_asiento_automatico(
                contador,
                origen_de_prueba(),
                HOY,
                [(cuentas.CAJA, DEBE, Decimal("10.00")), (cuentas.VENTAS, HABER, Decimal("9.00"))],
                hoy=HOY,
            )
        self.assertEqual(contexto.exception.codigo, "asiento_desbalanceado")
        self.assertEqual(AsientoContable.objects.count(), 2)

        # 4. El libro lee lo asentado: Insumos en Stock debe 3.500, Proveedores haber 3.500.
        saldos = libro.saldo_por_cuenta(primero.pk)
        self.assertEqual((saldos[cuentas.INSUMOS_EN_STOCK].saldo, saldos[cuentas.PROVEEDORES].saldo), (Decimal("3500.00"), Decimal("3500.00")))

        # 5. Paso diario 5 el último día del ejercicio: no pasa nada.
        with mock.patch("django.utils.timezone.localdate", return_value=datetime.date(2027, 12, 31)):
            call_command("proceso_diario", solo="abrir_ejercicio", stdout=io.StringIO())
        primero.refresh_from_db()
        self.assertEqual(primero.estado_ejercicio, Estado.ABIERTO)
        self.assertEqual(EjercicioContable.objects.count(), 1)

        # 6. Al día siguiente: el abierto pasa a «en cierre», se abre el 2028 y se avisa al Contador.
        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2028-01-01", stdout=io.StringIO())
        primero.refresh_from_db()
        nuevo = EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO)
        self.assertEqual(primero.estado_ejercicio, Estado.EN_CIERRE)
        self.assertEqual((nuevo.fecha_inicio_ejercicio, nuevo.fecha_cierre_ejercicio), (datetime.date(2028, 1, 1), datetime.date(2028, 12, 31)))
        self.assertEqual(Notificacion.objects.get(destinatario=contador).titulo, "El ejercicio N.º 1 pasó a «en cierre»")

        # 7. Asientos del día: uno de 2028 (número 1 en el nuevo) y uno con fecha de 2027 (va al «en cierre», número 3, con su fecha real).
        hoy = datetime.date(2028, 1, 2)
        de_2028 = asientos.registrar_asiento_automatico(contador, origen_de_prueba(), hoy, _movimientos("100.00"), hoy=hoy)
        de_2027 = asientos.registrar_asiento_automatico(
            contador, origen_de_prueba(), datetime.date(2027, 12, 30), _movimientos("200.00"), hoy=hoy
        )
        self.assertEqual((de_2028.ejercicio_id, de_2028.numero_asiento), (nuevo.pk, 1))
        self.assertEqual((de_2027.ejercicio_id, de_2027.numero_asiento, de_2027.fecha_asiento), (primero.pk, 3, datetime.date(2027, 12, 30)))
        self.assertEqual(de_2027.descripcion_asiento, "")

        # 8. Las patrimoniales arrastran de un ejercicio al siguiente.
        self.assertEqual(libro.saldo_por_cuenta(nuevo.pk)[cuentas.INSUMOS_EN_STOCK].saldo_inicial, Decimal("3700.00"))

        # 9. Un hecho de un ejercicio que ya no admite su fecha se asienta hoy, con la fecha real en la descripción.
        con_aclaracion = asientos.registrar_asiento_automatico(
            contador, origen_de_prueba(), datetime.date(2026, 5, 5), _movimientos("1.00"), hoy=hoy
        )
        self.assertEqual((con_aclaracion.ejercicio_id, con_aclaracion.fecha_asiento), (nuevo.pk, hoy))
        self.assertIn("05/05/2026 (anterior al primer ejercicio)", con_aclaracion.descripcion_asiento)

        # 10. Un año más: el que estaba «en cierre» se cierra solo (sin Contador) y el 2028 pasa a «en cierre».
        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2029-01-01", stdout=io.StringIO())
        primero.refresh_from_db()
        nuevo.refresh_from_db()
        self.assertEqual((primero.estado_ejercicio, primero.contador), (Estado.CERRADO, None))
        self.assertEqual(nuevo.estado_ejercicio, Estado.EN_CIERRE)
        self.assertEqual(EjercicioContable.objects.get(estado_ejercicio=Estado.ABIERTO).fecha_inicio_ejercicio, datetime.date(2029, 1, 1))
        self.assertTrue(Notificacion.objects.filter(destinatario=contador, titulo="El ejercicio N.º 1 se cerró solo").exists())

        # 11. Corrido otra vez el mismo día, el paso no hace nada más (idempotente) y todo sigue consistente.
        cantidad = EjercicioContable.objects.count()
        call_command("proceso_diario", solo="abrir_ejercicio", fecha="2029-01-01", stdout=io.StringIO())
        self.assertEqual(EjercicioContable.objects.count(), cantidad)
        verificar_invariantes_contables()
