# Cargador de datos de verificación de `comercial` (COM-01; docs/patrones/datos_de_verificacion.md; CLAUDE.md, «Datos para la verificación a mano»).
# Lo registra ``ComercialConfig.ready()`` en ``core.verificacion`` (orden 20: después de `maestros` e `iot`; regla A4 de D-37) y lo corre
# ``manage.py cargar_datos_de_verificacion``. SIEMPRE llama a los servicios de las apps (nunca inserciones directas: quedan la auditoría y las
# reglas como en una pantalla real), no borra nada y es idempotente: lo que ya existe se reutiliza.
#
# Deja la base lista para la «Verificación a mano» de COM-01 (docs/tareas/comercial/COM-01-clientes-y-vehiculos.md):
#   - cuentas ``vendedor@prueba5.local``, ``transportista@prueba5.local`` y ``transportista2@prueba5.local`` (prueba1 y prueba2 son de
#     `maestros`; prueba3, de `iot`; prueba4, de `produccion`). El Gerente es el activo de la base (solo puede haber uno, D-09): se usa el suyo.
#   - un invernadero «Invernadero Comercial», sin personal, con ``transportista@prueba5.local`` ya agregado desde «Logística» (MAE-05); el otro
#     transportista queda sin invernadero (para probar los dos estados);
#   - clientes en cada estado que hay que probar: una persona jurídica con correo y dos direcciones (una urbana y una rural), una persona
#     física sin correo ni direcciones y una persona jurídica dada de baja (para «Reactivarlo» y el aviso al Gerente);
#   - un vehículo dado de baja (para «Reactivar»). NO se carga el vehículo de los pasos 7 a 9 (patente AE123CD): lo registra la persona.
# Los CUIT son válidos y de fantasía (empiezan con 30 50 0000, 20 50 0000) para no chocar con los que se escriban a mano.

from core import verificacion
from core.models import Gerente, Transportista, Usuario, Vendedor
from core.servicios import ACCESO_TEMPORAL, alta_usuario, cambiar_contrasena
from core.verificacion import ErrorDeCarga
from comercial.models import Cliente, Vehiculo
from comercial.servicios import clientes as servicio_clientes
from comercial.servicios import vehiculos as servicio_vehiculos
from comercial.servicios.clientes import DatosDeCliente
from comercial.servicios.vehiculos import DatosDeVehiculo
from maestros.models import Invernadero, Localidad, TransportistaInvernadero
from maestros.servicios import invernaderos as servicio_invernaderos
from maestros.servicios import transportistas as servicio_transportistas

CODIGO = "comercial"
SUFIJO = "prueba5.local"  # el número de cuenta de este cargador (maestros: 1 y 2; iot: 3; produccion: 4)
NOMBRE_DEL_INVERNADERO = "Invernadero Comercial"
# (rol, correo local, nombre, apellido)
CUENTAS = (
    ("vendedor", "vendedor", "Valeria", "de prueba"),
    ("transportista", "transportista", "Tomás", "de prueba"),
    ("transportista", "transportista2", "Teresa", "de prueba"),
)
CUIT_CON_DIRECCIONES = "30-50000001-1"
CUIT_FISICA = "20-50000003-2"
CUIT_DADO_DE_BAJA = "30-50000004-6"
PATENTE_DADA_DE_BAJA = "ZZZ999"


def _gerente_activo():
    """El Gerente activo, que da de alta cuentas e invernaderos y registra vehículos. Sin Gerente no se puede cargar nada."""
    gerente = Gerente.objects.filter(is_active=True).first()
    if gerente is None:
        raise ErrorDeCarga("No hay un Gerente activo: creá uno antes de cargar los datos de verificación.")
    return gerente


def _cuenta(gerente, rol, correo, nombre, apellido, contrasena, creado, cuentas):
    """La cuenta ``<correo>@prueba5.local``: se reutiliza si existe; si no, se da de alta con ``alta_usuario`` y se le pone la contraseña de
    quien trabaja con ``cambiar_contrasena`` (la temporal se descarta: nunca se muestra)."""
    email = f"{correo}@{SUFIJO}"
    cuenta = Usuario.objects.filter(email__iexact=email).first()
    if cuenta is None:
        cuenta, _ = alta_usuario(gerente, rol, nombre, apellido, email, acceso=ACCESO_TEMPORAL)
        cambiar_contrasena(cuenta, contrasena)
        creado.append(f"Cuenta {email} ({rol}).")
    cuentas.append(f"{email} · {rol}")
    return cuenta


def _invernadero(gerente, creado):
    """«Invernadero Comercial», sin personal (``alta_invernadero``). Si ya existe, se reutiliza."""
    invernadero = Invernadero.objects.filter(nombre_invernadero__iexact=NOMBRE_DEL_INVERNADERO).first()
    if invernadero is None:
        localidad = Localidad.objects.filter(nombre_localidad="Garupá").first() or Localidad.objects.order_by("id").first()
        if localidad is None:
            raise ErrorDeCarga("Falta la geografía de Georef (migración 0002 de maestros).")
        invernadero = servicio_invernaderos.alta_invernadero(
            gerente, NOMBRE_DEL_INVERNADERO, tipo_direccion="urbana", localidad_id=localidad.pk, calle="Calle de prueba", numero_calle="200"
        )
        creado.append(f"Invernadero «{NOMBRE_DEL_INVERNADERO}» (sin personal).")
    return invernadero


def _transportista_en_el_invernadero(gerente, invernadero, transportista, creado):
    """Agrega al Transportista al invernadero desde «Logística» (``agregar_transportista``, MAE-05) si todavía no tiene uno."""
    if not TransportistaInvernadero.objects.filter(transportista_id=transportista.pk).exists():
        servicio_transportistas.agregar_transportista(gerente, invernadero.pk, transportista.pk)
        creado.append(f"{transportista.email} agregado a «{invernadero.nombre_invernadero}».")


def _direccion(localidad, tipo, **datos):
    """Los datos de una dirección para ``DatosDeCliente`` (los nombres de ``docs/api/direcciones.md``)."""
    return {"tipo_direccion": tipo, "localidad": localidad.pk, **datos}


def _clientes(gerente, vendedor, creado):
    """Los tres clientes (``alta_cliente`` y ``baja_cliente``): jurídica con correo y dos direcciones, física sin correo y una jurídica
    dada de baja. Se reconocen por su CUIT."""
    localidad = Localidad.objects.filter(nombre_localidad="Garupá").first() or Localidad.objects.order_by("id").first()
    pendientes = (
        (
            vendedor,
            DatosDeCliente(
                tipo_cliente="juridica",
                cuit=CUIT_CON_DIRECCIONES,
                razon_social="Verdulería Los Pinos S.R.L. (prueba)",
                email="compras@lospinos.prueba",
                telefono="+54 376 400-1001",
                direcciones_nuevas=[
                    _direccion(localidad, "urbana", calle="San Martín", numero_calle="123", barrio="Centro"),
                    _direccion(localidad, "rural", ruta="Ruta 12", kilometro="1034"),
                ],
            ),
            False,
        ),
        (vendedor, DatosDeCliente(tipo_cliente="fisica", cuit=CUIT_FISICA, nombre="Marta", apellido="Gómez (prueba)"), False),
        (gerente, DatosDeCliente(tipo_cliente="juridica", cuit=CUIT_DADO_DE_BAJA, razon_social="Cerrado S.A. (prueba)"), True),
    )
    for actor, datos, dar_de_baja in pendientes:
        cuit = datos.cuit.replace("-", "")
        existente = Cliente.objects.filter(cuit_cliente=cuit).first()
        if existente is None:
            cliente = servicio_clientes.alta_cliente(actor, datos)
            creado.append(f"Cliente «{cliente}» (CUIT {datos.cuit}).")
            if dar_de_baja:
                servicio_clientes.baja_cliente(gerente, cliente.pk)
                creado.append(f"«{cliente}» dado de baja (para probar «Reactivarlo»).")


def _vehiculo_dado_de_baja(gerente, creado):
    """Un vehículo dado de baja (``alta_vehiculo`` y ``baja_vehiculo``), para probar «Reactivar». No se carga el de los pasos 7 a 9."""
    if not Vehiculo.objects.filter(patente=PATENTE_DADA_DE_BAJA).exists():
        vehiculo = servicio_vehiculos.alta_vehiculo(
            gerente, DatosDeVehiculo(PATENTE_DADA_DE_BAJA, "furgon", "Fiat", "Ducato", "1250,5")
        )
        servicio_vehiculos.baja_vehiculo(gerente, vehiculo.pk)
        creado.append(f"Vehículo {PATENTE_DADA_DE_BAJA} dado de baja (para probar «Reactivar»).")


def cargar(contrasena):
    """El cargador de `comercial`: ver el encabezado del archivo. Devuelve un ``ResumenDeCarga``. Nunca imprime ni devuelve la contraseña."""
    creado, cuentas = [], []
    gerente = _gerente_activo()
    por_correo = {}
    for rol, correo, nombre, apellido in CUENTAS:
        por_correo[correo] = _cuenta(gerente, rol, correo, nombre, apellido, contrasena, creado, cuentas)
    vendedor = Vendedor.objects.get(pk=por_correo["vendedor"].pk)
    transportista = Transportista.objects.get(pk=por_correo["transportista"].pk)
    invernadero = _invernadero(gerente, creado)
    _transportista_en_el_invernadero(gerente, invernadero, transportista, creado)
    _clientes(gerente, vendedor, creado)
    _vehiculo_dado_de_baja(gerente, creado)
    cuentas.append("(el Gerente: el de la base, que es el único activo)")
    return verificacion.ResumenDeCarga(creado=tuple(creado), cuentas=tuple(cuentas), pendiente=())
