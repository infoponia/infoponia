# Servicio de PerfilOrganizacion (MAE-04, ADM-MOD-ORG). Mismo esquema que ``configuracion.py``: una función por caso de uso
# en ``transaction.atomic()``, fila única bloqueada con ``FOR NO KEY UPDATE`` y releída, todo o nada con los errores por campo
# juntos, sin cambios no audita (D-28) y auditoría con el antes y el después (D-36). Fuente:
# docs/casos_de_uso/maestros/configuracion.md. Sin logo (D-45).

import re

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction

from core.extensiones import Identidad
from core.models import RegistroAuditoria, Usuario, rol_de
from core.validadores import validar_telefono
from maestros.models import PerfilOrganizacion
from maestros.servicios.invernaderos import _actor_sigue_activo

CAMPOS_DE_TEXTO = (
    "nombre_organizacion",
    "cuit_organizacion",
    "telefono_organizacion",
    "email_organizacion",
    "direccion_organizacion",
)
CAMPOS_DE_COLOR = ("color_primario", "color_secundario", "color_terciario", "color_cuaternario")
CAMPOS = CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR  # los datos que modifica ``modificar_perfil``
_LARGOS = {
    campo: PerfilOrganizacion._meta.get_field(campo).max_length
    for campo in ("nombre_organizacion", "direccion_organizacion", "email_organizacion")
}
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}\Z")
_PESOS_CUIT = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)  # módulo 11, como ``cuitOk`` del prototipo


def obtener():
    """La fila única; si faltara la crea con el nombre de ``NOMBRE_ORGANIZACION`` (red de seguridad, ``get_or_create`` sobre
    ``singleton=1``: seguro ante pedidos simultáneos)."""
    return PerfilOrganizacion.objects.get_or_create(
        singleton=1, defaults={"nombre_organizacion": settings.NOMBRE_ORGANIZACION}
    )[0]


def identidad():
    """La ``Identidad`` (nombre y color principal) del perfil guardado (D-48), o ``None`` si no hay fila o el nombre está
    vacío: ``core`` usa entonces ``NOMBRE_ORGANIZACION``. Es solo lectura y no crea la fila. Un color sin cargar es ``""``."""
    fila = PerfilOrganizacion.objects.filter(singleton=1).first()
    if fila is None or not fila.nombre_organizacion.strip():
        return None
    return Identidad(fila.nombre_organizacion, fila.color_primario)


def _exigir_gerente(actor):
    """Precondición a: ``actor`` es un Gerente con la cuenta activa (SEG-13, regla 1)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede modificar el perfil de la organización.")


def _cuit_valido(digitos):
    """True si ``digitos`` son 11 dígitos con el verificador correcto (módulo 11; 11 cuenta como 0 y 10 no es válido)."""
    if not re.fullmatch(r"\d{11}", digitos, re.ASCII):
        return False
    verificador = 11 - sum(p * int(d) for p, d in zip(_PESOS_CUIT, digitos)) % 11
    if verificador == 11:
        verificador = 0
    return verificador != 10 and verificador == int(digitos[10])


def _texto(valor):
    """``valor`` como texto recortado (``None`` es vacío)."""
    return "" if valor is None else str(valor).strip()


def _validar(datos):
    """``(normalizados, errores)`` de los datos ya fusionados con los vigentes. Regla 2 (nombre obligatorio; largos),
    regla 3 (email y CUIT), D-21 (teléfono) y regla 5 (colores ``#RRGGBB`` en mayúsculas y cargados en orden)."""
    errores, limpios = {}, {}

    def error(campo, mensaje, codigo):
        errores[campo] = [ValidationError(mensaje, code=codigo)]

    for campo in CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR:
        limpios[campo] = _texto(datos[campo])
    if not limpios["nombre_organizacion"]:
        error("nombre_organizacion", "Ingresá el nombre de la organización.", "obligatorio")
    for campo, largo in _LARGOS.items():
        if len(limpios[campo]) > largo and campo not in errores:
            error(campo, f"Usá como máximo {largo} caracteres.", "demasiado_largo")

    cuit = re.sub(r"[\s-]", "", limpios["cuit_organizacion"])
    if cuit and not _cuit_valido(cuit):
        error("cuit_organizacion", "El CUIT no es válido: revisá los números (11 dígitos, con su dígito verificador).",
              "cuit_invalido")
    limpios["cuit_organizacion"] = cuit

    try:
        validar_telefono(limpios["telefono_organizacion"])
    except ValidationError as e:
        errores["telefono_organizacion"] = [ValidationError(e.message, code=e.code)]

    email = limpios["email_organizacion"]
    if email and "email_organizacion" not in errores:
        try:
            validate_email(email)
        except ValidationError:
            error("email_organizacion", "Ingresá un email válido. Ej. nombre@empresa.com", "email_invalido")

    for posicion, campo in enumerate(CAMPOS_DE_COLOR):
        color = limpios[campo]
        if not color:
            continue
        if not _COLOR.match(color):
            error(campo, "Ingresá el color con el formato #RRGGBB.", "color_formato")
            continue
        limpios[campo] = color.upper()
        # Regla 5: en orden. El anterior tiene que estar cargado (un formato inválido ya se marcó en su propio campo).
        if posicion and not limpios[CAMPOS_DE_COLOR[posicion - 1]]:
            error(campo, f"Cargá primero el color {posicion}.", "color_fuera_de_orden")
    return limpios, errores


def modificar_perfil(actor, **datos):
    """ADM-MOD-ORG: modifica los datos indicados (``campo=valor``; lo que no se indica queda como está) y devuelve el perfil.

    - Precondición a y regla 1: Gerente activo (``PermissionDenied``); la fila no se crea ni se elimina.
    - Reglas 2, 3 y 5: ver ``_validar``. Regla 7: todo o nada, con todos los errores juntos, un error por campo.
    - D-28: sin cambios no se escribe ni se audita. Postcondición b (D-36): ``modificacion_perfil`` con el antes y el después
      de cada dato que cambió; un opcional vacío va como nulo. Un campo desconocido (por ejemplo ``logo``, D-45) es un
      error de programación (``TypeError``).
    """
    desconocidos = set(datos) - set(CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR)
    if desconocidos:
        raise TypeError(f"Datos desconocidos: {', '.join(sorted(desconocidos))}.")
    _exigir_gerente(actor)
    with transaction.atomic():
        obtener()
        fila = PerfilOrganizacion.objects.select_for_update(no_key=True).get(singleton=1)  # releída ya bloqueada
        _actor_sigue_activo(actor)

        vigentes = {campo: getattr(fila, campo) for campo in CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR}
        limpios, errores = _validar(vigentes | datos)
        if errores:
            raise ValidationError(errores)

        cambios = {
            campo: {"antes": getattr(fila, campo) or None, "despues": limpios[campo] or None}
            for campo in datos
            if getattr(fila, campo) != limpios[campo]
        }
        if cambios:
            for campo in cambios:
                setattr(fila, campo, limpios[campo])
            fila.save(update_fields=list(cambios))
            RegistroAuditoria.objects.registrar(
                usuario=actor,
                accion=RegistroAuditoria.Accion.MODIFICACION_PERFIL,
                afectados=[fila],
                detalle={"cambios": cambios},
            )
        return fila
