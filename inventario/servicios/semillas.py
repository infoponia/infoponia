# Servicios de la semilla de una variedad (INV-03, D-49): la semilla nace con su variedad (PROD-ALT-VAR postcondición c) y se renombra,
# se da de baja y se reactiva solo con ella (PROD-MOD-VAR, PROD-BAJ-VAR) o con su cultivo (PROD-MOD-CLT). Estas funciones corren DENTRO de
# la transacción del caso de uso que las llama, con el cultivo y la variedad ya bloqueados (docs/patrones/stock.md, sección 5), y NO
# auditan: el caso de uso escribe su único registro (D-36). Ninguna toca las existencias de la semilla (``InsumoInvernadero``): habilitarla
# es un paso aparte (CMP-HAB-IIN, regla 9 de PROD-ALT-VAR). La categoría se busca por ``codigo``, nunca por nombre (regla 1 de 8.23).

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.models import RegistroAuditoria
from inventario.categorias import SEMILLAS
from inventario.models import Insumo, Semilla, TipoInsumo
from inventario.servicios.insumos import _nombre_repetido

LARGO_DEL_NOMBRE = Insumo._meta.get_field("nombre_insumo").max_length
RESTRICCION_NOMBRE_UNICO = "insumo_nombre_unico"
UNIDAD_DE_LA_SEMILLA = "unidad"


def nombre_de_semilla(nombre_cultivo, nombre_variedad):
    """«Semilla {cultivo} {variedad}» (postcondición c de PROD-ALT-VAR)."""
    return f"Semilla {nombre_cultivo} {nombre_variedad}"


def _error_de_nombre(mensaje, codigo):
    """Un error del campo ``nombre`` (el de la variedad o el del cultivo, según quién provoca el cambio)."""
    return ValidationError({"nombre": [ValidationError(mensaje, code=codigo)]})


def error_de_nombre_repetido(nombre):
    """El error de campo de una semilla cuyo nombre ya usa otro insumo (decisión del 22/11/2026): ``semilla_repetida``."""
    return _error_de_nombre(f"Ya existe un insumo llamado «{nombre}». Elegí otro nombre.", "semilla_repetida")


def verificar_nombre(nombre, excluir_pk=None):
    """Valida el nombre de una semilla SIN escribir: hasta 100 caracteres (si un nombre ya guardado pasara, se rechaza en vez de
    truncar) y que no lo use otro insumo, sin distinguir mayúsculas, activo o inactivo. Lanza un error del campo ``nombre``."""
    if len(nombre) > LARGO_DEL_NOMBRE:
        raise _error_de_nombre(
            f"El nombre de la semilla («{nombre}») supera los {LARGO_DEL_NOMBRE} caracteres. Acortá el nombre.",
            "semilla_demasiado_larga",
        )
    if _nombre_repetido(nombre, excluir_pk=excluir_pk):
        raise error_de_nombre_repetido(nombre)


def traducir_integridad(error, nombre):
    """Si ``error`` es la restricción única del nombre del insumo (dos pedidos eligieron el mismo nombre a la vez), lanza el mismo
    error de campo ``semilla_repetida`` (nunca un 500); si no, vuelve a lanzar ``error``. Para usar dentro de ``except IntegrityError``."""
    if RESTRICCION_NOMBRE_UNICO in str(error):
        raise error_de_nombre_repetido(nombre) from error
    raise error


def crear_semilla(variedad):
    """Crea la semilla de ``variedad`` y la devuelve: «Semilla {cultivo} {variedad}», categoría ``semillas`` (por ``codigo``), unidad
    ``unidad``, con control de vencimiento y estado igual al de la variedad. No la habilita en ningún invernadero. Un nombre que ya usa
    otro insumo, o de más de 100 caracteres, es un error del campo ``nombre`` (``semilla_repetida`` o ``semilla_demasiado_larga``)."""
    nombre = nombre_de_semilla(variedad.cultivo.nombre_cultivo, variedad.nombre_variedad)
    verificar_nombre(nombre)
    try:
        with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción del caso de uso
            return Semilla.objects.create(
                nombre_insumo=nombre,
                tipo_insumo=TipoInsumo.objects.get(codigo=SEMILLAS),
                unidad_medida_insumo=UNIDAD_DE_LA_SEMILLA,
                controla_vencimiento=True,
                estado_insumo=variedad.estado_variedad,
                variedad=variedad,
            )
    except IntegrityError as error:
        traducir_integridad(error, nombre)


def bloquear_semilla(variedad):
    """La fila de ``Insumo`` de la semilla de ``variedad``, bloqueada (``FOR NO KEY UPDATE``) y releída. Es el ÚLTIMO nivel del orden
    cultivo -> variedad -> insumo (docs/patrones/stock.md, sección 5): se llama con el cultivo y la variedad ya bloqueados."""
    semilla_id = Semilla.objects.filter(variedad=variedad).values_list("pk", flat=True).get()
    return Insumo.objects.select_for_update(no_key=True).get(pk=semilla_id)


def renombrar_semilla(insumo, nombre):
    """Le pone ``nombre`` a la semilla ``insumo`` (ya bloqueada) y devuelve el nombre anterior. Un nombre que ya usa otro insumo, o de más
    de 100 caracteres, es un error del campo ``nombre`` (``semilla_repetida`` o ``semilla_demasiado_larga``), también si el choque
    ocurre a la vez en otro pedido (el ``IntegrityError`` se traduce)."""
    anterior = insumo.nombre_insumo
    verificar_nombre(nombre, excluir_pk=insumo.pk)
    insumo.nombre_insumo = nombre
    try:
        with transaction.atomic():
            insumo.save(update_fields=["nombre_insumo"])
    except IntegrityError as error:
        traducir_integridad(error, nombre)
    return anterior


def reactivar_semilla(insumo):
    """Deja activa la semilla ``insumo`` (ya bloqueada) junto con su variedad (regla 9 de PROD-MOD-VAR). NO toca sus existencias: no
    vuelve a habilitar las que estaban deshabilitadas y las que quedaron activas con la baja siguen activas."""
    insumo.estado_insumo = Insumo.Estado.ACTIVO
    insumo.save(update_fields=["estado_insumo"])
    return insumo


def dar_de_baja_semilla(insumo):
    """Deja inactiva la semilla ``insumo`` (ya bloqueada) junto con su variedad (postcondición b de PROD-BAJ-VAR). NO deshabilita sus
    existencias: el stock que queda sigue registrado y se descarta con un ajuste (regla 3; docs/modelo/inventario.md, «Diferencias» n.º 6)."""
    insumo.estado_insumo = Insumo.Estado.INACTIVO
    insumo.save(update_fields=["estado_insumo"])
    return insumo


# ---- lo que `inventario` registra en `maestros` para PROD-MOD-CLT (docs/api/extensiones_de_maestros.md, «Cultivos») ----


def contar_semillas_del_cultivo(cultivo):
    """Cuántas semillas cambian de nombre si se renombra ``cultivo`` (regla 3 de PROD-MOD-CLT): las de TODAS sus variedades, activas o
    inactivas. Una consulta. Es el ``contar`` de ``registrar_semillas_de_cultivo``."""
    return Semilla.objects.filter(variedad__cultivo=cultivo).count()


def renombrar_semillas_del_cultivo(actor, cultivo, nombre_anterior):
    """El ``renombrar`` de ``registrar_semillas_de_cultivo`` (postcondiciones a y d de PROD-MOD-CLT): con ``cultivo`` YA renombrado, deja la
    semilla de cada variedad como «Semilla {cultivo} {variedad}» y devuelve cuántas cambiaron. ``nombre_anterior`` lo exige la firma del punto
    de extensión; el nombre viejo de cada semilla se lee de su fila de ``Insumo`` ya bloqueada.

    - Bloquea las filas de ``Insumo`` de las semillas en UNA sentencia, con ``ORDER BY id`` y antes de escribir (último nivel del orden
      cultivo -> variedad -> insumo; ``modificar_cultivo`` ya tomó el cultivo).
    - Escribe UN registro ``modificacion_semilla`` por semilla que cambia (semilla, variedad y cultivo como afectados; el nombre antes y
      después). Lo que ya tiene su nombre no se escribe ni se audita (D-28).
    - Todo o nada: un nombre que ya usa otro insumo (o que la restricción única rechaza a la vez en otro pedido) es un error del campo
      ``nombre`` (``semilla_repetida``) y no queda ninguna renombrada."""
    with transaction.atomic():
        filas = list(Semilla.objects.filter(variedad__cultivo=cultivo).select_related("variedad").order_by("pk"))
        insumos = {i.pk: i for i in Insumo.objects.select_for_update(no_key=True).filter(pk__in=[f.pk for f in filas]).order_by("id")}
        renombradas = 0
        for semilla in filas:
            insumo = insumos[semilla.pk]
            nuevo = nombre_de_semilla(cultivo.nombre_cultivo, semilla.variedad.nombre_variedad)
            if insumo.nombre_insumo == nuevo:
                continue
            anterior = renombrar_semilla(insumo, nuevo)
            RegistroAuditoria.objects.registrar(
                usuario=actor,
                accion=RegistroAuditoria.Accion.MODIFICACION_SEMILLA,
                afectados=[semilla, semilla.variedad, cultivo],
                detalle={"cambios": {"nombre": {"antes": anterior, "despues": nuevo}}},
            )
            renombradas += 1
    return renombradas
