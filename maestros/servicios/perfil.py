# Servicio de PerfilOrganizacion (MAE-04, ADM-MOD-ORG). Mismo esquema que ``configuracion.py``: una función por caso de uso
# en ``transaction.atomic()``, fila única bloqueada con ``FOR NO KEY UPDATE`` y releída, todo o nada con los errores por campo
# juntos, sin cambios no audita (D-28) y auditoría con el antes y el después (D-36). Fuente:
# docs/casos_de_uso/maestros/configuracion.md. El logo (regla 4, D-106 puntos 10 a 15; reemplaza a D-45) lo procesa
# ``core/imagenes.py``.

import re

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import transaction

from core import imagenes
from core.extensiones import Identidad
from core.models import RegistroAuditoria, Usuario, rol_de
from core.validadores import validar_telefono
from maestros.models import PerfilOrganizacion
from maestros.servicios.invernaderos import _actor_sigue_activo
from maestros.validadores import validar_cuit

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
LADO_DEL_LOGO = 512  # D-106 punto 11: lado mayor, sin recortar y sin agrandar
CARPETA_DEL_LOGO = "logos"
MENSAJE_LOGO_Y_QUITAR = "Elegí un logo nuevo o marcá «Quitar el logo», pero no las dos cosas."


def obtener():
    """La fila única; si faltara la crea con el nombre de ``NOMBRE_ORGANIZACION`` (red de seguridad, ``get_or_create`` sobre
    ``singleton=1``: seguro ante pedidos simultáneos)."""
    return PerfilOrganizacion.objects.get_or_create(
        singleton=1, defaults={"nombre_organizacion": settings.NOMBRE_ORGANIZACION}
    )[0]


def identidad():
    """La ``Identidad`` (nombre, color principal y ``logo_url``) del perfil guardado (D-48, D-106 punto 15), o ``None`` si no hay
    fila o el nombre está vacío: ``core`` usa entonces ``NOMBRE_ORGANIZACION``. Es solo lectura y no crea la fila. Un color sin
    cargar es ``""``; ``logo_url`` es la URL firmada que da el almacenamiento (vence a la hora) o ``None`` sin logo."""
    fila = PerfilOrganizacion.objects.filter(singleton=1).first()
    if fila is None or not fila.nombre_organizacion.strip():
        return None
    return Identidad(fila.nombre_organizacion, fila.color_primario, fila.logo.url if fila.logo else None)


def _exigir_gerente(actor):
    """Precondición a: ``actor`` es un Gerente con la cuenta activa (SEG-13, regla 1)."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede modificar el perfil de la organización.")


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
    if cuit:  # vacío está permitido (ADM-MOD-ORG): solo se valida si viene informado
        try:
            validar_cuit(cuit)  # D-58 punto 4: el mismo cálculo, ahora público
        except ValidationError as problema:
            error("cuit_organizacion", problema.messages[0], problema.code)
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


def modificar_perfil(actor, logo=None, quitar_logo=False, **datos):
    """ADM-MOD-ORG: modifica los datos indicados (``campo=valor``; lo que no se indica queda como está) y devuelve el perfil.

    - Precondición a y regla 1: Gerente activo (``PermissionDenied``); la fila no se crea ni se elimina.
    - Reglas 2, 3 y 5: ver ``_validar``. Regla 7: todo o nada, con todos los errores juntos, un error por campo.
    - Regla 4 y D-106 puntos 10 a 13: ``logo`` es el archivo subido (``None`` = no se envió y el logo queda como está) y
      ``quitar_logo`` la casilla «Quitar el logo». ``core.imagenes`` lo valida y lo procesa (512 px, sin recorte, con
      transparencia, WebP); su error va en el campo ``logo`` junto con los demás. Un logo nuevo con ``quitar_logo`` a la vez es
      un error en ``logo`` (código ``logo_y_quitar``, precisión de D-106). El archivo se guarda solo si todo es válido.
    - D-28: sin cambios no se escribe ni se audita (quitar un logo que no hay tampoco). Postcondición b (D-36):
      ``modificacion_perfil`` con el antes y el después de cada dato que cambió; un opcional vacío va como nulo. Del logo se
      registra que cambió, no la imagen: «sin logo» → «con logo», «con logo» → «logo nuevo» y «con logo» → «sin logo».
    - D-106 punto 7: el archivo anterior se borra al confirmar la transacción; si no se confirma, se borra el nuevo.
    - Un campo desconocido es un error de programación (``TypeError``).
    """
    desconocidos = set(datos) - set(CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR)
    if desconocidos:
        raise TypeError(f"Datos desconocidos: {', '.join(sorted(desconocidos))}.")
    _exigir_gerente(actor)

    # El logo se valida y se procesa antes de bloquear la fila: es trabajo de CPU que no necesita el bloqueo.
    contenido, errores_del_logo = None, {}
    if logo is not None and quitar_logo:
        errores_del_logo["logo"] = [ValidationError(MENSAJE_LOGO_Y_QUITAR, code="logo_y_quitar")]
    elif logo is not None:
        try:
            contenido = imagenes.procesar(logo, LADO_DEL_LOGO)
        except ValidationError as problema:
            errores_del_logo["logo"] = [ValidationError(problema.message, code=problema.code)]

    with transaction.atomic():
        obtener()
        fila = PerfilOrganizacion.objects.select_for_update(no_key=True).get(singleton=1)  # releída ya bloqueada
        _actor_sigue_activo(actor)

        vigentes = {campo: getattr(fila, campo) for campo in CAMPOS_DE_TEXTO + CAMPOS_DE_COLOR}
        limpios, errores = _validar(vigentes | datos)
        errores |= errores_del_logo
        if errores:
            raise ValidationError(errores)

        cambios = {
            campo: {"antes": getattr(fila, campo) or None, "despues": limpios[campo] or None}
            for campo in datos
            if getattr(fila, campo) != limpios[campo]
        }
        for campo in cambios:
            setattr(fila, campo, limpios[campo])

        anterior = fila.logo.name
        nuevo = None
        if contenido is not None:
            nuevo = imagenes.guardar(contenido, CARPETA_DEL_LOGO)
            cambios["logo"] = {"antes": "con logo" if anterior else "sin logo", "despues": "logo nuevo" if anterior else "con logo"}
            fila.logo = nuevo
        elif quitar_logo and anterior:
            cambios["logo"] = {"antes": "con logo", "despues": "sin logo"}
            fila.logo = ""

        if cambios:
            try:
                fila.save(update_fields=list(cambios))
                RegistroAuditoria.objects.registrar(
                    usuario=actor,
                    accion=RegistroAuditoria.Accion.MODIFICACION_PERFIL,
                    afectados=[fila],
                    detalle={"cambios": cambios},
                )
            except BaseException:
                imagenes.borrar(nuevo)  # el archivo nuevo ya se guardó y la transacción se deshace: no queda huérfano
                raise
            if "logo" in cambios:
                imagenes.borrar_al_confirmar(anterior)
        return fila
