# Utilidades de prueba de `contabilidad` para esta app y para las demás (docs/api/asientos.md, «Pruebas de tu app»; CON-02 paso 5).
# Contiene: el plan de cuentas cargado una vez (`PlanDeCuentasMixin`), un documento de origen sin hijas de nivel mayor (`origen_de_prueba`),
# las fábricas de ejercicio y de asiento y `verificar_invariantes_contables`.
import importlib
from collections import defaultdict
from decimal import Decimal

from django.apps import apps
from django.db import connection
from django.utils import timezone

from contabilidad import cuentas
from contabilidad.constantes import DEBE, HABER
from contabilidad.models import (
    AsientoContable,
    CuentaContable,
    EjercicioContable,
    MovimientoContable,
    OrigenDocumento,
)
from contabilidad.servicios.ejercicios import cierre_previsto


def asegurar_plan_de_cuentas():
    """Carga y confirma las 19 cuentas si la base de pruebas las perdió, y corre ANALYZE (`docs/patrones/datos_de_migracion.md`).

    Con `--keepdb`, un `TransactionTestCase` de cualquier app vacía la base con un `TRUNCATE` y se llevaría el plan que cargó la migración.
    Usa la misma función que la migración: los datos son siempre los mismos.
    """
    if CuentaContable.objects.count() < 19:
        importlib.import_module("contabilidad.migrations.0005_plan_de_cuentas").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE contabilidad_cuentacontable")


class PlanDeCuentasMixin:
    """Mixin para las clases de pruebas que usan cuentas: `class MisTests(PlanDeCuentasMixin, TestCase)` (va primero en las bases).

    Carga el plan en `setUpClass`, antes de que `TestCase` abra la transacción de la clase, así queda confirmado y sirve a todas las
    clases y corridas siguientes. En un `TransactionTestCase` el `flush` lo borra en cada prueba: ahí se llama a
    `asegurar_plan_de_cuentas()` en `setUp`.
    """

    @classmethod
    def setUpClass(cls):
        asegurar_plan_de_cuentas()
        super().setUpClass()


def origen_de_prueba(tipo=OrigenDocumento.Tipo.BITACORA):
    """Crea un documento de origen para una prueba y lo devuelve.

    `contabilidad` es de nivel 2 y no puede importar las hijas de nivel mayor (regla A1 de D-37), así que la fila del padre se crea con
    `bulk_create`, que no pasa por `OrigenDocumento.save()` (el que exige una hija directa). Solo para pruebas y verificación a mano.
    """
    return OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo=tipo)])[0]


def ejercicio(estado, inicio, cierre=None):
    """Crea un ejercicio en el `estado` dado (`EjercicioContable.Estado`), directo en la base: sin auditoría ni avisos. El cierre
    previsto es de doce meses menos un día si no se pasa (el mismo que calcula el servicio)."""
    return EjercicioContable.objects.create(
        fecha_inicio_ejercicio=inicio,
        fecha_cierre_ejercicio=cierre or cierre_previsto(inicio),
        estado_ejercicio=estado,
    )


def ejercicio_abierto(inicio=None, cierre=None):
    """Crea el ejercicio abierto; empieza hoy (`timezone.localdate()`) si no se pasa `inicio`."""
    return ejercicio(EjercicioContable.Estado.ABIERTO, inicio or timezone.localdate(), cierre)


def asiento_de_prueba(ejercicio, fecha, movimientos=None, *, origen=None, descripcion=None, anula=None):
    """Crea un asiento con sus movimientos directo en la base (sin pasar por el servicio): toma el número siguiente del ejercicio y lo
    suma a `ultimo_numero_asiento`. `movimientos` es una lista de `(codigo_cuenta, "D" | "H", Decimal)`; por defecto Caja a Capital
    Inicial por 100,00. Sin `origen` ni `anula` y sin `descripcion`, la descripción es «Asiento de prueba» (la base la exige)."""
    if movimientos is None:
        movimientos = [(cuentas.CAJA, DEBE, Decimal("100.00")), (cuentas.CAPITAL_INICIAL, HABER, Decimal("100.00"))]
    if descripcion is None:
        descripcion = "" if origen is not None else "Asiento de prueba"
    numero = ejercicio.ultimo_numero_asiento + 1
    asiento = AsientoContable.objects.create(
        ejercicio=ejercicio,
        numero_asiento=numero,
        fecha_asiento=fecha,
        descripcion_asiento=descripcion,
        origen=origen,
        anula=anula,
    )
    por_codigo = {c.codigo_cuenta: c for c in CuentaContable.objects.filter(codigo_cuenta__in={m[0] for m in movimientos})}
    MovimientoContable.objects.bulk_create(
        [
            MovimientoContable(asiento=asiento, cuenta=por_codigo[codigo], tipo_movimiento=tipo, importe_movimiento=importe)
            for codigo, tipo, importe in movimientos
        ]
    )
    EjercicioContable.objects.filter(pk=ejercicio.pk).update(ultimo_numero_asiento=numero)
    ejercicio.ultimo_numero_asiento = numero
    return asiento


def verificar_invariantes_contables():
    """Verifica los invariantes de la contabilidad (docs/api/asientos.md, «Pruebas de tu app»); lanza `AssertionError` con lo que falla:
    Debe = Haber en cada asiento, dos o más movimientos por asiento, numeración correlativa sin huecos por ejercicio (y
    `ultimo_numero_asiento` igual al último), a lo sumo un ejercicio abierto y uno en cierre, y rangos de ejercicios que no se pisan.
    Llamala al final de toda prueba que cree asientos."""
    sumas = defaultdict(lambda: {DEBE: Decimal("0"), HABER: Decimal("0")})
    cantidades = defaultdict(int)
    for tipo, importe, asiento_id in MovimientoContable.objects.values_list("tipo_movimiento", "importe_movimiento", "asiento_id"):
        sumas[asiento_id][tipo] += importe
        cantidades[asiento_id] += 1
    for asiento in AsientoContable.objects.select_related("ejercicio"):
        suma = sumas[asiento.pk]
        assert cantidades[asiento.pk] >= 2, f"{asiento} tiene {cantidades[asiento.pk]} movimiento(s): hacen falta dos o más."
        assert suma[DEBE] == suma[HABER], f"{asiento} no está balanceado: Debe {suma[DEBE]} y Haber {suma[HABER]}."

    ejercicios = list(EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id"))
    for ej in ejercicios:
        numeros = list(AsientoContable.objects.filter(ejercicio=ej).order_by("numero_asiento").values_list("numero_asiento", flat=True))
        assert numeros == list(range(1, len(numeros) + 1)), f"{ej}: la numeración no es correlativa sin huecos: {numeros}."
        assert ej.ultimo_numero_asiento == len(numeros), (
            f"{ej}: ultimo_numero_asiento es {ej.ultimo_numero_asiento} y tiene {len(numeros)} asiento(s)."
        )
    for estado in (EjercicioContable.Estado.ABIERTO, EjercicioContable.Estado.EN_CIERRE):
        cantidad = sum(1 for ej in ejercicios if ej.estado_ejercicio == estado)
        assert cantidad <= 1, f"Hay {cantidad} ejercicios en estado «{estado}»: a lo sumo uno."
    for anterior, siguiente in zip(ejercicios, ejercicios[1:]):
        assert siguiente.fecha_inicio_ejercicio > anterior.fecha_cierre_ejercicio, f"{anterior} y {siguiente} se pisan."
