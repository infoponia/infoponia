# Pruebas de los cuatro modelos del núcleo contable (CON-02 paso 1, D-84; `docs/modelo/contabilidad.md`): cada restricción de la base
# se verifica con un `IntegrityError`, y la inmutabilidad y el tipo derivado del asiento con sus errores. Cada prueba arma sus datos.
# Las cuentas de prueba usan códigos «9.x» para no chocar con el plan de cuentas cargado por la migración (paso 2).
import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from contabilidad.models import (
    AsientoContable,
    AsientoInmutableError,
    CuentaContable,
    EjercicioContable,
    MovimientoContable,
)
from contabilidad.tests.fabricas import origen_de_prueba
from core.models import Contador
from core.tests.fabricas import crear_cuenta

INICIO = datetime.date(2027, 1, 1)
CIERRE = datetime.date(2027, 12, 31)


def _ejercicio(estado=EjercicioContable.Estado.ABIERTO, inicio=INICIO, cierre=CIERRE, **extra):
    return EjercicioContable.objects.create(
        fecha_inicio_ejercicio=inicio, fecha_cierre_ejercicio=cierre, estado_ejercicio=estado, **extra
    )


def _asiento(ejercicio, numero=1, **extra):
    extra.setdefault("descripcion_asiento", "Asiento de prueba")
    return AsientoContable.objects.create(
        ejercicio=ejercicio, numero_asiento=numero, fecha_asiento=INICIO, **extra
    )


def _cuenta(codigo="9.9.01", nombre="Cuenta de prueba"):
    return CuentaContable.objects.create(
        codigo_cuenta=codigo, nombre_cuenta=nombre, tipo_cuenta=CuentaContable.Tipo.ACTIVO
    )


class EjercicioContableModeloTests(TestCase):
    """Restricciones de base de `EjercicioContable` (modelo de contabilidad, «Restricciones de la base»; D-84 puntos 2 y 4)."""

    def test_regla_un_solo_ejercicio_abierto(self):
        """Modelo, EjercicioContable: a lo sumo un ejercicio «abierto» (`un_solo_ejercicio_abierto`, H1)."""
        _ejercicio()
        with self.assertRaises(IntegrityError), transaction.atomic():
            _ejercicio(inicio=datetime.date(2028, 1, 1), cierre=datetime.date(2028, 12, 31))

    def test_regla_un_solo_ejercicio_en_cierre(self):
        """Modelo, EjercicioContable: a lo sumo un ejercicio «en cierre» (`un_solo_ejercicio_en_cierre`, H1)."""
        _ejercicio(EjercicioContable.Estado.EN_CIERRE)
        with self.assertRaises(IntegrityError), transaction.atomic():
            _ejercicio(
                EjercicioContable.Estado.EN_CIERRE, inicio=datetime.date(2028, 1, 1), cierre=datetime.date(2028, 12, 31)
            )

    def test_regla_pueden_convivir_un_abierto_un_en_cierre_y_varios_cerrados(self):
        """Modelo, EjercicioContable: las parciales solo limitan «abierto» y «en cierre»; los cerrados no tienen tope."""
        _ejercicio(EjercicioContable.Estado.CERRADO, datetime.date(2025, 1, 1), datetime.date(2025, 12, 31))
        _ejercicio(EjercicioContable.Estado.CERRADO, datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        _ejercicio(EjercicioContable.Estado.EN_CIERRE, datetime.date(2027, 1, 1), datetime.date(2027, 12, 31))
        _ejercicio(EjercicioContable.Estado.ABIERTO, datetime.date(2028, 1, 1), datetime.date(2028, 12, 31))

        self.assertEqual(EjercicioContable.objects.count(), 4)

    def test_regla_cierre_no_anterior_al_inicio(self):
        """Modelo, EjercicioContable: `fecha_cierre_ejercicio >= fecha_inicio_ejercicio` (CheckConstraint)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            _ejercicio(inicio=datetime.date(2027, 6, 1), cierre=datetime.date(2027, 5, 31))

    def test_regla_cierre_igual_al_inicio_es_valido(self):
        """Modelo, EjercicioContable: la desigualdad es «mayor o igual»."""
        _ejercicio(inicio=INICIO, cierre=INICIO)

    def test_regla_ultimo_numero_no_negativo(self):
        """Modelo, EjercicioContable: `ultimo_numero_asiento >= 0` (D-84 punto 4); lo respalda la base."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            _ejercicio(ultimo_numero_asiento=-1)

    def test_regla_ultimo_numero_empieza_en_cero(self):
        """Modelo, EjercicioContable: `ultimo_numero_asiento` es 0 por defecto (D-84 punto 4)."""
        self.assertEqual(_ejercicio().ultimo_numero_asiento, 0)

    def test_regla_contador_solo_si_esta_cerrado(self):
        """Modelo, EjercicioContable: `contador` solo puede estar lleno si el estado es «cerrado» (CheckConstraint, R010)."""
        contador = crear_cuenta(Contador, email="contador@infoponia.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _ejercicio(EjercicioContable.Estado.EN_CIERRE, contador=contador)
        cerrado = _ejercicio(EjercicioContable.Estado.CERRADO, contador=contador)
        self.assertEqual(cerrado.contador.pk, contador.pk)
        self.assertEqual(list(contador.ejercicios_cerrados.all()), [cerrado])

    def test_regla_contador_vacio_vale_en_cualquier_estado(self):
        """Modelo, EjercicioContable: lo cerró el Gerente o el Sistema (C1) ⇒ `contador` vacío también en «cerrado»."""
        _ejercicio(EjercicioContable.Estado.CERRADO)

    def test_texto_del_ejercicio_muestra_su_rango(self):
        """`__str__` (lo usa la auditoría, `referencia()`): el rango del ejercicio."""
        self.assertEqual(str(_ejercicio()), "Ejercicio 01/01/2027 al 31/12/2027")


class CuentaContableModeloTests(TestCase):
    """Restricciones de base de `CuentaContable` (modelo de contabilidad: una cuenta por `codigo_cuenta`)."""

    def test_regla_codigo_unico(self):
        """Modelo, CuentaContable: `codigo_cuenta` único."""
        _cuenta("9.9.01", "Una")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _cuenta("9.9.01", "Otra")

    def test_regla_nombre_unico(self):
        """Modelo, CuentaContable: `nombre_cuenta` único."""
        _cuenta("9.9.01", "Una")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _cuenta("9.9.02", "Una")


class AsientoContableModeloTests(TestCase):
    """Restricciones de base y reglas de `AsientoContable` (modelo de contabilidad; D-84 punto 1)."""

    def test_regla_numero_unico_por_ejercicio(self):
        """Modelo, AsientoContable: único `(ejercicio, numero_asiento)`."""
        ejercicio = _ejercicio()
        _asiento(ejercicio, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            _asiento(ejercicio, 1)

    def test_regla_el_mismo_numero_vale_en_otro_ejercicio(self):
        """Modelo, AsientoContable: el número se reinicia en cada ejercicio (H8)."""
        viejo = _ejercicio(EjercicioContable.Estado.CERRADO, datetime.date(2026, 1, 1), datetime.date(2026, 12, 31))
        _asiento(viejo, 1)
        _asiento(_ejercicio(), 1)

    def test_regla_un_origen_un_asiento(self):
        """Modelo, AsientoContable, R012: `origen` es `OneToOne` (D-86 punto 5)."""
        ejercicio = _ejercicio()
        origen = origen_de_prueba()
        _asiento(ejercicio, 1, origen=origen, descripcion_asiento="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            _asiento(ejercicio, 2, origen=origen, descripcion_asiento="")

    def test_regla_el_origen_llega_a_su_asiento_por_asiento_contable(self):
        """Modelo, AsientoContable, R012: el accesorio inverso es `asiento_contable` (D-83, no el de una hija)."""
        origen = origen_de_prueba()
        asiento = _asiento(_ejercicio(), origen=origen, descripcion_asiento="")
        self.assertEqual(origen.asiento_contable.pk, asiento.pk)

    def test_regla_un_asiento_se_anula_una_sola_vez(self):
        """Modelo, AsientoContable, R161: `anula` es `OneToOne` (un asiento tiene a lo sumo un contraasiento)."""
        ejercicio = _ejercicio()
        original = _asiento(ejercicio, 1)
        _asiento(ejercicio, 2, anula=original)
        with self.assertRaises(IntegrityError), transaction.atomic():
            _asiento(ejercicio, 3, anula=original)

    def test_regla_anulado_se_deriva_del_contraasiento(self):
        """Modelo, AsientoContable, R161: «anulado» es `hasattr(asiento, "contraasiento")`."""
        ejercicio = _ejercicio()
        original = _asiento(ejercicio, 1)
        self.assertFalse(hasattr(original, "contraasiento"))
        contraasiento = _asiento(ejercicio, 2, anula=original)
        original = AsientoContable.objects.get(pk=original.pk)
        self.assertEqual(original.contraasiento.pk, contraasiento.pk)

    def test_regla_no_puede_tener_origen_y_anula_a_la_vez(self):
        """Modelo, AsientoContable, «Tipo»: un asiento no puede tener `origen` y `anula` a la vez (CheckConstraint)."""
        ejercicio = _ejercicio()
        original = _asiento(ejercicio, 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            _asiento(ejercicio, 2, origen=origen_de_prueba(), anula=original, descripcion_asiento="")

    def test_regla_16_sin_origen_la_descripcion_es_obligatoria(self):
        """Regla 16 de 8.20 y modelo, AsientoContable: sin `origen`, `descripcion_asiento` no vacía (CheckConstraint)."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            _asiento(_ejercicio(), descripcion_asiento="")

    def test_regla_16_con_origen_la_descripcion_puede_estar_vacia(self):
        """Modelo, AsientoContable: en un automático la descripción es opcional."""
        asiento = _asiento(_ejercicio(), origen=origen_de_prueba(), descripcion_asiento="")
        self.assertEqual(asiento.descripcion_asiento, "")

    def test_regla_15_tipo_se_deduce_y_no_se_guarda(self):
        """Regla 15 de 8.20: `automatico` si tiene origen, `contraasiento` si tiene `anula`, `manual` si no tiene ninguno."""
        ejercicio = _ejercicio()
        manual = _asiento(ejercicio, 1)
        automatico = _asiento(ejercicio, 2, origen=origen_de_prueba(), descripcion_asiento="")
        contraasiento = _asiento(ejercicio, 3, anula=manual)

        self.assertEqual(manual.tipo, AsientoContable.Tipo.MANUAL)
        self.assertEqual(automatico.tipo, AsientoContable.Tipo.AUTOMATICO)
        self.assertEqual(contraasiento.tipo, AsientoContable.Tipo.CONTRAASIENTO)
        self.assertNotIn("tipo", [campo.name for campo in AsientoContable._meta.get_fields()])

    def test_regla_nadie_borra_el_documento_de_origen(self):
        """D-52 y modelo, AsientoContable: la clave del origen es `PROTECT`."""
        origen = origen_de_prueba()
        _asiento(_ejercicio(), origen=origen, descripcion_asiento="")
        with self.assertRaises(IntegrityError), transaction.atomic():
            origen.delete()

    def test_regla_un_ejercicio_con_asientos_no_se_borra(self):
        """Modelo, EjercicioContable, R013: `AsientoContable.ejercicio` es `PROTECT`."""
        ejercicio = _ejercicio()
        _asiento(ejercicio)
        from django.db.models import ProtectedError

        with self.assertRaises(ProtectedError):
            ejercicio.delete()

    def test_d84_un_asiento_existente_no_se_modifica(self):
        """D-84 punto 1: `save()` sobre una fila existente lanza `AsientoInmutableError`."""
        asiento = _asiento(_ejercicio())
        asiento.descripcion_asiento = "Otra"
        with self.assertRaises(AsientoInmutableError):
            asiento.save()
        self.assertEqual(AsientoContable.objects.get(pk=asiento.pk).descripcion_asiento, "Asiento de prueba")

    def test_d84_un_asiento_no_se_borra(self):
        """D-84 punto 1: `delete()` lanza `AsientoInmutableError`."""
        asiento = _asiento(_ejercicio())
        with self.assertRaises(AsientoInmutableError):
            asiento.delete()
        self.assertEqual(AsientoContable.objects.count(), 1)

    def test_d84_el_queryset_de_asientos_no_modifica_ni_borra(self):
        """D-84 punto 1: `update`, `bulk_update` y `delete` del queryset lanzan `AsientoInmutableError`."""
        asiento = _asiento(_ejercicio())
        with self.assertRaises(AsientoInmutableError):
            AsientoContable.objects.update(descripcion_asiento="x")
        with self.assertRaises(AsientoInmutableError):
            AsientoContable.objects.bulk_update([asiento], ["descripcion_asiento"])
        with self.assertRaises(AsientoInmutableError):
            AsientoContable.objects.all().delete()
        self.assertEqual(AsientoContable.objects.get().descripcion_asiento, "Asiento de prueba")


class MovimientoContableModeloTests(TestCase):
    """Restricciones de base y reglas de `MovimientoContable` (modelo de contabilidad; D-84 punto 1)."""

    def setUp(self):
        self.asiento = _asiento(_ejercicio())
        self.cuenta = _cuenta()

    def _movimiento(self, importe="100.00", tipo=MovimientoContable.Tipo.DEBE):
        return MovimientoContable.objects.create(
            asiento=self.asiento, cuenta=self.cuenta, tipo_movimiento=tipo, importe_movimiento=Decimal(importe)
        )

    def test_regla_importe_mayor_que_cero(self):
        """Modelo, MovimientoContable: `importe_movimiento > 0` (CheckConstraint); cero y negativo se rechazan."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._movimiento("0.00")
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._movimiento("-1.00")

    def test_regla_importe_con_dos_decimales(self):
        """Modelo, MovimientoContable: `DecimalField(14, 2)`; el importe se guarda con dos decimales."""
        movimiento = self._movimiento("12345678901.23")
        movimiento.refresh_from_db()
        self.assertEqual(movimiento.importe_movimiento, Decimal("12345678901.23"))

    def test_regla_los_movimientos_cuelgan_del_asiento_y_de_la_cuenta(self):
        """Modelo, MovimientoContable, R014 y R015: accesorios `movimientos` del asiento y de la cuenta."""
        movimiento = self._movimiento()
        self.assertEqual(list(self.asiento.movimientos.all()), [movimiento])
        self.assertEqual(list(self.cuenta.movimientos.all()), [movimiento])

    def test_regla_no_se_borra_una_cuenta_con_movimientos(self):
        """Modelo, MovimientoContable, R015: la FK a la cuenta es `PROTECT`."""
        from django.db.models import ProtectedError

        self._movimiento()
        with self.assertRaises(ProtectedError):
            self.cuenta.delete()

    def test_d84_un_movimiento_existente_no_se_modifica_ni_se_borra(self):
        """D-84 punto 1: `save()` y `delete()` sobre una fila existente, y `update`/`delete` del queryset, lanzan `AsientoInmutableError`."""
        movimiento = self._movimiento()
        movimiento.importe_movimiento = Decimal("5.00")
        with self.assertRaises(AsientoInmutableError):
            movimiento.save()
        with self.assertRaises(AsientoInmutableError):
            movimiento.delete()
        with self.assertRaises(AsientoInmutableError):
            MovimientoContable.objects.update(importe_movimiento=Decimal("5.00"))
        with self.assertRaises(AsientoInmutableError):
            MovimientoContable.objects.all().delete()
        self.assertEqual(MovimientoContable.objects.get().importe_movimiento, Decimal("100.00"))

    def test_d84_se_pueden_crear_movimientos_en_bloque(self):
        """D-84 punto 1: la inmutabilidad no impide crear (el servicio de asientos usa `bulk_create`)."""
        MovimientoContable.objects.bulk_create(
            [
                MovimientoContable(
                    asiento=self.asiento, cuenta=self.cuenta, tipo_movimiento="D", importe_movimiento=Decimal("1.00")
                ),
                MovimientoContable(
                    asiento=self.asiento, cuenta=self.cuenta, tipo_movimiento="H", importe_movimiento=Decimal("1.00")
                ),
            ]
        )
        self.assertEqual(self.asiento.movimientos.count(), 2)
