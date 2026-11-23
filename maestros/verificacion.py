# Cargador de datos de verificación de MAE-02d (CLAUDE.md, «Datos para la verificación a mano»; docs/patrones/datos_de_verificacion.md). Lo creó MAE-02d como
# comando propio en ``maestros``; con IOT-03 el comando es UNO solo, en ``core`` (``manage.py cargar_datos_de_verificacion``), y cada app aporta su función. Esta es la
# de ``maestros``, con el mismo comportamiento que tenía: la registra ``MaestrosConfig.ready()`` en ``core.verificacion`` (regla A4 de D-37).
#
# Deja: dos invernaderos, cada uno con su Agrónomo, y un Capataz sin invernadero (para probar el 403). El invernadero 1 no tiene Capataz: por la regla 3 de 8.22 tiene la
# alerta «Invernadero sin Capataz activo», la que usa la verificación a mano. No crea un Gerente (D-09: uno solo activo; la base local ya tiene el del estudiante), no toca al
# Administrador ni a ninguna cuenta que no creó (las cuentas de prueba son ``<rol>@prueba<N>.local``) y no borra nada. La contraseña la recibe del comando y nunca se escribe.

from django.db import transaction

from core import verificacion
from core.models import Agronomo, Capataz, Gerente
from core.verificacion import ErrorDeCarga
from maestros.models import Alerta, Invernadero, Localidad
from maestros.servicios import alertas as api_alertas
from maestros.servicios.invernaderos import alta_invernadero

CODIGO = "maestros"
INVERNADERO_1 = "Invernadero Verificación 1"
INVERNADERO_2 = "Invernadero Verificación 2"
CUENTAS = (
    # (clase, correo, nombre, apellido)
    (Agronomo, "agronomo@prueba1.local", "Agustina", "Prueba Uno"),
    (Agronomo, "agronomo@prueba2.local", "Armando", "Prueba Dos"),
    (Capataz, "capataz@prueba1.local", "Camila", "Prueba Uno"),
)


def _cuentas(contrasena):
    """Crea las cuentas de prueba que falten (no toca las que ya existen) y devuelve ``{correo: cuenta}``."""
    cuentas = {}
    for clase, correo, nombre, apellido in CUENTAS:
        cuenta = clase.objects.filter(email=correo).first()
        if cuenta is None:
            cuenta = clase.objects.create_user(email=correo, password=contrasena, first_name=nombre, last_name=apellido)
        cuentas[correo] = cuenta
    return cuentas


def _invernadero(gerente, nombre, agronomo):
    """El invernadero de prueba ``nombre``; si no existe, lo da de alta con el servicio real (que audita y avisa, D-22)."""
    existente = Invernadero.objects.filter(nombre_invernadero=nombre).first()
    if existente is not None:
        return existente
    localidad = Localidad.objects.order_by("id").first()
    if localidad is None:
        raise ErrorDeCarga("Falta la geografía de Georef (migración 0002 de maestros).")
    return alta_invernadero(
        gerente,
        nombre,
        tipo_direccion="urbana",
        localidad_id=localidad.pk,
        calle="Calle de prueba",
        numero_calle="100",
        agronomo_id=agronomo.pk,
    )


def _alerta_sin_capataz(invernadero):
    """Deja activa y no leída la alerta «sin Capataz» del invernadero 1 (la repone si se resolvió) y la devuelve."""
    invernadero.refresh_from_db()
    if invernadero.capataz_id is not None:
        raise ErrorDeCarga(
            f"«{invernadero.nombre_invernadero}» ya tiene un Capataz y la alerta «sin Capataz» no puede existir: "
            "quitale el Capataz desde la ficha para repetir la verificación."
        )
    api_alertas.sincronizar_alertas_de_personal(invernadero, roles=["capataz"])
    alerta = Alerta.objects.activas().get(invernadero=invernadero, tipo_alerta="sin_capataz")
    Alerta.objects.filter(pk=alerta.pk).update(estado_lectura_alerta=Alerta.Lectura.NO_LEIDA)
    alerta.refresh_from_db()
    return alerta


def cargar(contrasena):
    """El cargador de ``maestros``: ver el encabezado. Todo en una transacción (si algo falla, no queda nada). Devuelve un ``ResumenDeCarga``."""
    with transaction.atomic():
        gerente = Gerente.objects.filter(is_active=True).first()
        if gerente is None:
            raise ErrorDeCarga("No hay un Gerente activo: hace falta uno para dar de alta los invernaderos de prueba.")
        cuentas = _cuentas(contrasena)
        invernadero_1 = _invernadero(gerente, INVERNADERO_1, cuentas["agronomo@prueba1.local"])
        _invernadero(gerente, INVERNADERO_2, cuentas["agronomo@prueba2.local"])
        alerta = _alerta_sin_capataz(invernadero_1)
    return verificacion.ResumenDeCarga(
        creado=(f"«{INVERNADERO_1}»: alerta «{alerta.descripcion_alerta}» (id {alerta.pk}), no leída.",),
        cuentas=tuple(f"{correo} · {type(cuenta).__name__}" for correo, cuenta in cuentas.items()),
    )
