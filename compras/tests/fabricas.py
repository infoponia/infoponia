# Fábricas compartidas por las pruebas de compras/tests/ (CMP-01): CUIT válidos, un proveedor creado directo en la base (sin pasar por el
# servicio de alta) y los datos de un alta. Reutilizan las fábricas de cuentas de core y de maestros. Una sola firma por función.

from compras.models import Proveedor
from inventario.tests.fabricas import tipo_de_insumo  # noqa: F401  (lo reexportan para las pruebas de compras)

# Marca de «el actor por defecto» de los auxiliares de las pruebas: ``None`` es un actor válido (sin cuenta) y tiene que llegar al servicio.
GERENTE = object()

_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(n=1):
    """El ``n``-ésimo CUIT válido de la fábrica (11 dígitos, sin guiones), distinto para cada ``n``. Calcula el verificador por su cuenta
    (módulo 11), sin usar ``maestros.validadores``: así una prueba del validador no depende de lo que verifica. Salta los números cuyo
    verificador daría 10, que no son válidos."""
    base = 3_000_000_000 + n * 13
    while True:
        resto = sum(peso * int(digito) for peso, digito in zip(_PESOS_CUIT, str(base))) % 11
        verificador = 11 - resto
        if verificador == 11:
            verificador = 0
        if verificador != 10:
            return f"{base}{verificador}"
        base += 1


def con_guiones(cuit):
    """``cuit`` (11 dígitos) como «30-71234567-1»."""
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10:]}"


def proveedor(
    razon_social="Semillas del Sur S. A.",
    n=1,
    cuit=None,
    tipo="juridica",
    nombre="",
    apellido="",
    email="ventas@semillasdelsur.com",
    telefono="",
    activo=True,
    especialidades=(),
):
    """Un proveedor creado directo en la base. Por defecto es una persona jurídica activa con el CUIT número ``n``; con
    ``tipo="fisica"`` hay que pasar ``nombre`` y ``apellido`` (y la razón social se deja vacía)."""
    if tipo == "fisica":
        razon_social = ""
    else:
        nombre = apellido = ""
    creado = Proveedor.objects.create(
        tipo_proveedor=tipo,
        cuit_proveedor=cuit or cuit_valido(n),
        razon_social_proveedor=razon_social,
        nombre_proveedor=nombre,
        apellido_proveedor=apellido,
        email_proveedor=email,
        telefono_proveedor=telefono,
        estado_proveedor="activo" if activo else "inactivo",
    )
    creado.especialidades.set(especialidades)
    return creado


def datos_de_alta(**cambios):
    """Los datos de un alta de proveedor (una persona jurídica) con el CUIT número 1; ``cambios`` pisa lo que se indique. Las claves son
    las del servicio: ``tipo``, ``cuit``, ``razon_social``, ``nombre``, ``apellido``, ``email``, ``telefono`` y ``especialidades``."""
    datos = {
        "tipo": "juridica",
        "cuit": cuit_valido(1),
        "razon_social": "Semillas del Sur S. A.",
        "nombre": "",
        "apellido": "",
        "email": "ventas@semillasdelsur.com",
        "telefono": "",
        "especialidades": [],
    }
    datos.update(cambios)
    return datos


def datos_de(proveedor, **cambios):
    """Los datos de una modificación o de una reactivación que dejan al ``proveedor`` igual que está; ``cambios`` pisa lo que se indique.
    Las claves son las del servicio (como ``datos_de_alta``, con el CUIT en 11 dígitos)."""
    datos = {
        "cuit": proveedor.cuit_proveedor,
        "razon_social": proveedor.razon_social_proveedor,
        "nombre": proveedor.nombre_proveedor,
        "apellido": proveedor.apellido_proveedor,
        "email": proveedor.email_proveedor,
        "telefono": proveedor.telefono_proveedor,
        "especialidades": [categoria.pk for categoria in proveedor.especialidades.all()],
    }
    datos.update(cambios)
    return datos


def ref(objeto, texto=None):
    """Cómo queda una referencia en el detalle de la auditoría (D-36): ``{"id", "texto"}``; el texto es el ``__str__`` del objeto
    (o ``texto`` si se indica)."""
    return {"id": objeto.pk, "texto": texto if texto is not None else str(objeto)}


def afectado_de(proveedor):
    """Cómo queda un proveedor entre los afectados de un registro de auditoría (D-36), sin el rol (solo lo llevan las cuentas)."""
    return {"modelo": "compras.proveedor", "id": proveedor.pk, "texto": str(proveedor)}
