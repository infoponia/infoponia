# Fábricas compartidas por las pruebas de inventario/tests/ (docs/patrones/stock.md, sección 7). Arman categorías, insumos,
# existencias, lotes y faltantes directo en la base, con sus movimientos para que se cumpla la regla 1 de 8.19, y verifican
# las invariantes del kárdex. Reutilizan las fábricas de cuentas y de invernaderos de maestros. NO armes lotes a mano.
#
# Un lote nace con un movimiento «ajuste positivo / carga inicial» (sin origen): es lo que hará INV-02 y la única forma de
# ingreso que existe en esta ronda (el ingreso por recepción es de `compras`, que exige un `origen`).

import importlib
from contextlib import contextmanager
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.db import connection
from django.utils import timezone

from contabilidad.models import OrigenDocumento
from inventario import extensiones
from inventario.models import Insumo, InsumoInvernadero, LoteInsumo, MovimientoInsumo, TipoInsumo
from maestros.tests.fabricas import ConDatosDeMaestros

Mov = MovimientoInsumo.TipoMovimiento


class perezoso:
    """Un módulo importado la primera vez que se le pide algo (``tipos = perezoso("inventario.servicios.tipos_de_insumo")``).
    Las pruebas de un servicio lo usan para no fallar todas juntas al importar el archivo mientras el servicio no existe
    (convención de ``maestros``: «tomado del módulo dentro de cada prueba»)."""

    def __init__(self, ruta):
        self._ruta = ruta

    def __getattr__(self, nombre):
        return getattr(importlib.import_module(self._ruta), nombre)


INGRESOS = (Mov.AJUSTE_POSITIVO, Mov.ENTRADA_POR_CORRECCION, Mov.INGRESO_POR_RECEPCION)
SALIDAS = (Mov.AJUSTE_NEGATIVO, Mov.SALIDA_POR_CONSUMO, Mov.SALIDA_POR_CORRECCION)


def asegurar_datos_de_inventario():
    """Deja cargadas y confirmadas las cuatro categorías del sistema en la base de pruebas. La migración ``0002`` las carga
    al crear la base, pero un ``TransactionTestCase`` vacía todas las tablas al terminar y, con ``--keepdb``, la base queda
    sin ellas. Si faltan, se vuelven a cargar con la misma función de la migración y se corre ``ANALYZE``
    (docs/patrones/datos_de_migracion.md). Hay que llamarla fuera de la transacción de una clase."""
    if TipoInsumo.objects.filter(es_del_sistema=True).count() < 4:
        importlib.import_module("inventario.migrations.0002_cargar_categorias_del_sistema").cargar(apps, None)
        with connection.cursor() as cursor:
            cursor.execute("ANALYZE inventario_tipoinsumo")


class ConDatosDeInventario(ConDatosDeMaestros):
    """Mixin: ``class MisTests(ConDatosDeInventario, TestCase)``. Asegura las categorías del sistema (y, por herencia, Georef
    y los datos de maestros que usan los invernaderos) en ``setUpClass``, antes de que ``TestCase`` abra la transacción de la
    clase. Las clases de concurrencia (``TransactionTestCase``) también lo heredan y, dentro de cada prueba, llaman a
    ``asegurar_datos_de_inventario()`` y a ``asegurar_datos_de_maestros()`` en ``setUp`` porque el ``flush`` de la prueba
    anterior vacía las tablas."""

    @classmethod
    def setUpClass(cls):
        asegurar_datos_de_inventario()
        super().setUpClass()


def categoria_del_sistema(codigo):
    """Una de las cuatro categorías del sistema (``semillas``, ``envases``, ``repuestos_de_hardware``, ``infraestructura``)."""
    return TipoInsumo.objects.get(codigo=codigo)


def tipo_de_insumo(nombre="Limpieza", consumo="como_gasto", activo=True):
    """Una categoría común (no del sistema) creada directo en la base."""
    return TipoInsumo.objects.create(
        nombre_tipo_insumo=nombre,
        consumo_directo=consumo,
        estado_tipo_insumo="activo" if activo else "inactivo",
    )


def insumo(nombre="Detergente", tipo=None, unidad="l", controla_vencimiento=False, activo=True, descripcion=""):
    """Un insumo del catálogo. Sin ``tipo``, crea (o reutiliza) la categoría «Limpieza»."""
    if tipo is None:
        tipo = TipoInsumo.objects.filter(nombre_tipo_insumo="Limpieza").first() or tipo_de_insumo()
    return Insumo.objects.create(
        nombre_insumo=nombre,
        descripcion_insumo=descripcion,
        tipo_insumo=tipo,
        unidad_medida_insumo=unidad,
        controla_vencimiento=controla_vencimiento,
        estado_insumo="activo" if activo else "inactivo",
    )


def existencia(insumo, invernadero, minimo=0, precio="10.00", activo=True, transito=0):
    """El ``InsumoInvernadero`` de ``insumo`` en ``invernadero`` (habilitado, sin lotes y con stock 0)."""
    return InsumoInvernadero.objects.create(
        insumo=insumo,
        invernadero=invernadero,
        cant_min_insumo=Decimal(str(minimo)),
        cant_transito_insumo=Decimal(str(transito)),
        referencia_precio=Decimal(str(precio)),
        estado_insumo_invernadero="activo" if activo else "inactivo",
    )


def origen_falso():
    """Un ``OrigenDocumento`` (tipo «orden de trabajo») para los movimientos que exigen origen, como la salida por consumo.
    Se crea con ``bulk_create`` porque ``OrigenDocumento.save()`` solo permite guardar sus hijas directas (D-52)."""
    return OrigenDocumento.objects.bulk_create([OrigenDocumento(tipo=OrigenDocumento.Tipo.ORDEN_DE_TRABAJO)])[0]


def movimiento(lote, tipo, cantidad, motivo=None, descripcion="", origen=None):
    """Un movimiento del lote creado directo en la base. Los ajustes llevan ``motivo`` y no llevan origen; los demás, origen
    (si no se pasa, uno falso). No cambia la cantidad del lote: la fábrica que lo llama ya la dejó como debe quedar."""
    sin_origen = tipo in (Mov.AJUSTE_POSITIVO, Mov.AJUSTE_NEGATIVO, Mov.SALIDA_POR_CORRECCION)
    if tipo in (Mov.AJUSTE_POSITIVO, Mov.AJUSTE_NEGATIVO) and motivo is None:
        motivo = MovimientoInsumo.MotivoAjuste.CARGA_INICIAL
    return MovimientoInsumo.objects.create(
        lote_insumo=lote,
        cantidad=Decimal(str(cantidad)),
        tipo_movimiento=tipo,
        motivo_ajuste=motivo,
        descripcion_ajuste=descripcion,
        origen=None if sin_origen else (origen or origen_falso()),
    )


def lote(existencia, disponible, vence=None, ingreso=None, ingresada=None):
    """Un lote de la existencia con su movimiento de ingreso («ajuste positivo / carga inicial»), para que se cumpla la regla 1
    de 8.19. ``ingresada`` es lo que entró (por omisión, ``disponible``); si hay menos disponible, la diferencia sale con una
    «salida por consumo». Un lote en 0 se conserva (pasá ``ingresada``)."""
    disponible = Decimal(str(disponible))
    ingresada = Decimal(str(ingresada)) if ingresada is not None else disponible
    nuevo = LoteInsumo.objects.create(
        insumo_invernadero=existencia,
        cantidad_ingresada=ingresada,
        cantidad_disponible=disponible,
        fecha_ingreso=ingreso or timezone.localdate(),
        fecha_vencimiento=vence,
    )
    movimiento(nuevo, Mov.AJUSTE_POSITIVO, ingresada)
    if ingresada > disponible:
        movimiento(nuevo, Mov.SALIDA_POR_CONSUMO, ingresada - disponible)
    return nuevo


def faltante(existencia, cantidad):
    """El faltante sin lote de la existencia, con ``cantidad`` faltante (se pasa en positivo; queda negativa)."""
    cantidad = Decimal(str(cantidad))
    nuevo = LoteInsumo.objects.create(
        insumo_invernadero=existencia, cantidad_disponible=-cantidad, es_faltante_sin_lote=True
    )
    movimiento(nuevo, Mov.SALIDA_POR_CONSUMO, cantidad)
    return nuevo


def verificar_invariantes(existencia):
    """Invariantes que toda prueba de un servicio de stock verifica (docs/patrones/stock.md, sección 7): para cada lote,
    ingresos − salidas = ``cantidad_disponible``; ningún lote común queda negativo; el faltante nunca es positivo; a lo sumo un
    faltante. Lanza ``AssertionError`` si alguna falla. («Cada cambio de cantidad tiene exactamente un movimiento» lo
    verifica cada prueba que cambia cantidades, contando los movimientos antes y después.)"""
    lotes = list(existencia.lotes.all())
    faltantes = [l for l in lotes if l.es_faltante_sin_lote]
    assert len(faltantes) <= 1, "Hay más de un faltante sin lote."
    for l in lotes:
        entradas = sum((m.cantidad for m in l.movimientos.filter(tipo_movimiento__in=INGRESOS)), Decimal("0"))
        salidas = sum((m.cantidad for m in l.movimientos.filter(tipo_movimiento__in=SALIDAS)), Decimal("0"))
        assert entradas - salidas == l.cantidad_disponible, (
            f"{l}: ingresos − salidas ({entradas - salidas}) no es la cantidad disponible ({l.cantidad_disponible})."
        )
        if l.es_faltante_sin_lote:
            assert l.cantidad_disponible <= 0, "El faltante sin lote nunca es positivo."
        else:
            assert l.cantidad_disponible >= 0, f"{l} quedó negativo."


@contextmanager
def reservas_de_prueba(reservado=None, ordenes=None, impedimentos=None):
    """Registrantes falsos de los tres puntos de `inventario`, que se quitan al salir (no contaminan el registro global).

    - ``reservado``: ``{iin_id: Decimal}`` de lo reservado por cada ``InsumoInvernadero`` (el resto, 0).
    - ``ordenes``: ``{iin_id: [OrdenQueReserva, ...]}``.
    - ``impedimentos``: ``{iin_id: [Impedimento, ...]}`` de deshabilitación (los de `compras`).
    Cada uno registra a lo sumo un registrante falso; los que no se pasan quedan sin registrantes.
    """
    reservado = reservado or {}
    ordenes = ordenes or {}
    impedimentos = impedimentos or {}

    def reservas(ids):
        return {i: Decimal(str(reservado[i])) for i in ids if i in reservado}

    def ordenes_que_reservan(ids):
        return {i: list(ordenes[i]) for i in ids if i in ordenes}

    def impedimentos_de(iin):
        return list(impedimentos.get(iin.pk, []))

    with (
        mock.patch.object(extensiones, "_RESERVAS", [reservas] if reservado else []),
        mock.patch.object(extensiones, "_ORDENES_QUE_RESERVAN", [ordenes_que_reservan] if ordenes else []),
        mock.patch.object(
            extensiones, "_IMPEDIMENTOS_DE_DESHABILITACION", [impedimentos_de] if impedimentos else []
        ),
    ):
        yield


def ajuste_simulado(actor, existencia, cantidad):
    """Un ajuste de stock simulado para las pruebas de concurrencia (INV-02 escribe el real): dentro de una transacción
    bloquea el invernadero (contrato de D-40) y la existencia (docs/patrones/stock.md, sección 5), carga un lote con
    ``cantidad`` y registra la auditoría; ``correr_a_la_vez`` lo detiene después de registrarla, antes de confirmar."""
    from django.db import transaction

    from core.models import RegistroAuditoria
    from maestros.servicios.invernaderos import bloquear_invernadero_activo

    with transaction.atomic():
        bloquear_invernadero_activo(existencia.invernadero_id)
        bloqueada = InsumoInvernadero.objects.select_for_update(no_key=True).get(pk=existencia.pk)
        nuevo = lote(bloqueada, cantidad)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_INSUMO,
            afectados=[existencia.insumo],
            detalle={"cambios": {"nombre": {"antes": "a", "despues": "b"}}},
        )
    return nuevo
