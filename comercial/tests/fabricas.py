# Fábricas compartidas por las pruebas de comercial/tests/: clientes, direcciones de clientes y vehículos creados directo en
# la base (sin pasar por los servicios), con datos válidos por defecto. Reutilizan las de core y maestros. Una sola firma
# por función.

import itertools

from django.utils import timezone

from comercial.models import Cliente, DireccionCliente, Vehiculo

_secuencia = itertools.count(1)
# Los CUIT automáticos arrancan lejos de los que las pruebas escriben a mano (30000000090, 30712345671...).
_cuits = itertools.count(5_000_000)
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(numero=None):
    """Un CUIT de persona jurídica («30…») con dígito verificador correcto, sin guiones. ``numero`` (hasta 8 dígitos) lo hace
    reproducible; sin él, uno nuevo en cada llamada."""
    automatico = numero is None
    while True:
        numero = next(_cuits) if automatico else numero
        base = f"30{int(numero):08d}"
        resto = 11 - sum(p * int(d) for p, d in zip(_PESOS_CUIT, base)) % 11
        verificador = 0 if resto == 11 else resto
        if verificador != 10:  # con 10 no hay CUIT válido: se pasa al número siguiente
            return f"{base}{verificador}"
        if not automatico:
            numero += 1


def cliente(
    tipo="juridica",
    cuit=None,
    razon_social="Verdulería Los Pinos S.R.L.",
    nombre="Marta",
    apellido="Gómez",
    telefono="",
    email="",
    activo=True,
):
    """Un cliente creado directo. En una persona jurídica solo cuenta la razón social; en una física, el nombre y el apellido
    (la restricción de la base lo exige)."""
    juridica = tipo == Cliente.Tipo.JURIDICA
    return Cliente.objects.create(
        tipo_cliente=tipo,
        cuit_cliente=cuit or cuit_valido(),
        razon_social_cliente=razon_social if juridica else "",
        nombre_cliente="" if juridica else nombre,
        apellido_cliente="" if juridica else apellido,
        telefono_cliente=telefono,
        email_cliente=email,
        estado_cliente=Cliente.Estado.ACTIVO if activo else Cliente.Estado.INACTIVO,
    )


def direccion_de_cliente(cliente_, tipo="urbana", localidad_id=None, **extra):
    """Una dirección activa del cliente, creada con la API pública de direcciones de `maestros` (D-58) y su vínculo
    ``DireccionCliente``. ``extra`` pisa los datos de la dirección (``calle``, ``ruta``…)."""
    from maestros.servicios import direcciones
    from maestros.tests.fabricas import localidad

    datos = {"tipo_direccion": tipo, "localidad": localidad_id or localidad().pk}
    datos.update(
        {"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"}
    )
    datos.update(extra)
    hija = direcciones.crear_direccion(direcciones.validar_direccion(datos))
    return DireccionCliente.objects.create(cliente=cliente_, direccion=hija.direccion_ptr)


def vehiculo(
    patente=None,
    tipo="camioneta",
    marca="Ford",
    modelo="Ranger",
    capacidad="800",
    activo=True,
    transportista=None,
    en_ruta_hoy=False,
):
    """Un vehículo creado directo. ``en_ruta_hoy`` lo deja con la ruta iniciada hoy (MD-118: en COM-01 nadie inicia una ruta,
    lo hace COM-06). Un vehículo inactivo no puede tener transportista (restricción de la base)."""
    return Vehiculo.objects.create(
        patente=patente or f"AB{next(_secuencia):03d}CD",
        tipo_vehiculo=tipo,
        marca=marca,
        modelo=modelo,
        capacidad_carga=capacidad,
        estado_vehiculo=Vehiculo.Estado.ACTIVO if activo else Vehiculo.Estado.INACTIVO,
        transportista=transportista,
        en_ruta=en_ruta_hoy,
        fecha_inicio_ruta=timezone.localdate() if en_ruta_hoy else None,
    )


CUIT_VALIDO = "30-71234567-1"  # el de los ejemplos de docs/api/direcciones.md


def datos_de_direccion(tipo="urbana", localidad_id=None, **extra):
    """Los datos de una dirección para ``DatosDeCliente`` (los nombres de ``docs/api/direcciones.md``). ``extra`` los pisa."""
    from maestros.tests.fabricas import localidad

    datos = {"tipo_direccion": tipo, "localidad": localidad_id or localidad().pk}
    datos.update({"calle": "San Martín", "numero_calle": "123"} if tipo == "urbana" else {"ruta": "Ruta 12", "kilometro": "1034"})
    datos.update(extra)
    return datos


def datos_de_cliente(**extra):
    """Un ``DatosDeCliente`` válido (persona jurídica con CUIT con guiones). ``extra`` pisa cualquier campo."""
    from comercial.servicios.clientes import DatosDeCliente

    campos = {"tipo_cliente": "juridica", "cuit": CUIT_VALIDO, "razon_social": "Verdulería Los Pinos S.R.L."}
    campos.update(extra)
    return DatosDeCliente(**campos)


def datos_de_cliente_de(cliente_, **extra):
    """Los datos guardados de ``cliente_`` como ``DatosDeCliente`` (sin direcciones), para modificarlo cambiando solo ``extra``."""
    from comercial.servicios.clientes import DatosDeCliente

    campos = {
        "tipo_cliente": cliente_.tipo_cliente,
        "cuit": cliente_.cuit_cliente,
        "razon_social": cliente_.razon_social_cliente,
        "nombre": cliente_.nombre_cliente,
        "apellido": cliente_.apellido_cliente,
        "telefono": cliente_.telefono_cliente,
        "email": cliente_.email_cliente,
    }
    campos.update(extra)
    return DatosDeCliente(**campos)


def datos_de_vehiculo(**extra):
    """Un ``DatosDeVehiculo`` válido (una camioneta de 800 kg sin transportista). ``extra`` pisa cualquier campo."""
    from comercial.servicios.vehiculos import DatosDeVehiculo

    campos = {"patente": "AE123CD", "tipo_vehiculo": "camioneta", "marca": "Ford", "modelo": "Ranger", "capacidad_carga": "800"}
    campos.update(extra)
    return DatosDeVehiculo(**campos)


def datos_de_vehiculo_de(vehiculo_, **extra):
    """Los datos guardados de ``vehiculo_`` como ``DatosDeVehiculo``, para modificarlo cambiando solo ``extra``."""
    from comercial.servicios.vehiculos import DatosDeVehiculo

    campos = {
        "patente": vehiculo_.patente,
        "tipo_vehiculo": vehiculo_.tipo_vehiculo,
        "marca": vehiculo_.marca,
        "modelo": vehiculo_.modelo,
        "capacidad_carga": str(vehiculo_.capacidad_carga),
        "transportista_id": vehiculo_.transportista_id,
    }
    campos.update(extra)
    return DatosDeVehiculo(**campos)
