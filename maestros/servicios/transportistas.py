# Servicios de los transportistas del invernadero (MAE-05, D-55): agregar, trasladar y quitar desde el bloque «Logística» de la
# ficha, que es parte de PROD-MOD-INV (postcondición g y reglas 8 a 11). Cada caso de uso es una función dentro de
# ``transaction.atomic()``, audita con el formato de D-36 (docs/patrones/auditoria.md, acción ya existente
# ``modificacion_invernadero``) y avisa al Transportista con ``core.notificaciones`` (D-42). Archivo propio para que
# ``invernaderos.py`` no siga creciendo (D-37).
#
# ORDEN DE BLOQUEOS (siempre ``FOR NO KEY UPDATE``; docs/patrones/bloqueos.md, D-30, D-32 y D-40: las cuentas primero):
#   1. quien actúa sigue activo;
#   2. la fila ``Usuario`` del Transportista (serializa contra ``baja_usuario`` y contra otro agregado del mismo Transportista);
#   3. los invernaderos que intervienen (destino y, en un traslado, origen), en orden ascendente de id. El destino con
#      ``bloquear_invernadero_activo``: agregar a un Transportista activo crea algo que impide la baja del invernadero
#      (contrato de ``maestros/extensiones.py``). El origen, con un bloqueo común, sin exigir que esté activo: así se puede
#      sacar a un Transportista de un invernadero inactivo.
#   Después se vuelve a leer la fila de ``TransportistaInvernadero``. Los registrantes de impedimentos corren recién acá.

from collections import namedtuple

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import transaction
from django.db.models.functions import Lower
from django.http import Http404
from django.utils import timezone

from core import notificaciones
from core.extensiones import DatoDeCuenta
from core.models import RegistroAuditoria, Transportista, Usuario, referencia
from maestros import extensiones
from maestros.models import Invernadero, TransportistaInvernadero
from maestros.servicios.invernaderos import (
    MENSAJE_INACTIVO_NO_SE_MODIFICA,
    _actor_sigue_activo,
    _bloquear_invernadero,
    _error_general,
    _exigir_gerente,
    bloquear_invernadero_activo,
)

# Un candidato de la ventana «Agregar transportista» (regla 8): el Transportista y el invernadero para el que trabaja hoy
# (``None`` si no tiene).
Candidato = namedtuple("Candidato", "transportista invernadero")

MENSAJE_TRANSPORTISTA_INACTIVO = "Solo se agregan transportistas activos."
MENSAJE_YA_PERTENECE = "Ese transportista ya trabaja para este invernadero."
MENSAJE_NO_PERTENECE = "Ese transportista no trabaja para este invernadero."


class FaltaConfirmarTraslado(Exception):
    """Regla 8 de PROD-MOD-INV: el Transportista elegido trabaja para otro invernadero y la persona todavía no confirmó el
    traslado. No se cambió nada. ``origen`` es el ``Invernadero`` donde trabaja hoy (sin bloquear: es solo para el aviso)."""

    def __init__(self, origen):
        super().__init__("Hay un traslado de transportista sin confirmar.")
        self.origen = origen


def _error_de_impedimentos(impedimentos):
    """Reglas 9 y 10: un ``ValidationError`` general con un error por impedimento (``texto`` y ``como_resolver``), cada uno con
    su código. Se informan todos, sin quedarse con el primero."""
    return ValidationError(
        {NON_FIELD_ERRORS: [ValidationError(f"{i.texto} {i.como_resolver}", code=i.codigo) for i in impedimentos]}
    )


def _invernadero_para_consultar(invernadero_id):
    """El invernadero sin bloquear: ``Http404`` si no existe y ``invernadero_inactivo`` si está inactivo (regla 5)."""
    invernadero = Invernadero.objects.filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    if not invernadero.activo:
        raise _error_general(MENSAJE_INACTIVO_NO_SE_MODIFICA, "invernadero_inactivo")
    return invernadero


def _bloquear_transportista(transportista_id):
    """La cuenta del Transportista bloqueada (``FOR NO KEY UPDATE`` sobre su fila ``Usuario``), leída de nuevo con su estado
    real, como ``Transportista``. ``Http404`` si no existe o no es de un Transportista. Dentro de ``transaction.atomic()``,
    después de verificar a quien actúa."""
    bloqueada = Usuario.objects.select_for_update(no_key=True).filter(pk=transportista_id, rol=Usuario.Rol.TRANSPORTISTA).first()
    if bloqueada is None:
        raise Http404("No existe ese transportista.")
    return Transportista.objects.get(pk=bloqueada.pk)


def _referencias(invernadero):
    """Los transportistas del invernadero hoy, como lista de referencias (D-36), por apellido y nombre."""
    return [referencia(t) for t in invernadero.transportistas()]


def _auditar(actor, invernadero, transportista, antes):
    """Un ``modificacion_invernadero`` del ``invernadero`` que cambió, con sus transportistas antes y después (D-36). Los
    afectados son el invernadero y la cuenta."""
    RegistroAuditoria.objects.registrar(
        usuario=actor,
        accion=RegistroAuditoria.Accion.MODIFICACION_INVERNADERO,
        afectados=[invernadero, transportista],
        detalle={"cambios": {"transportistas": {"antes": antes, "despues": _referencias(invernadero)}}},
    )


def candidatos(actor, invernadero_id):
    """Regla 8 de PROD-MOD-INV: los Transportistas que se ofrecen para agregar a ``invernadero_id``: los **activos** que no
    trabajan para ese invernadero, como ``Candidato(transportista, invernadero)`` con el invernadero actual o ``None``.
    Primero los que no tienen invernadero y después por nombre del invernadero y por apellido y nombre (sin distinguir
    mayúsculas). Solo lectura: no bloquea ni audita.

    Precondición a: ``actor`` es un Gerente activo (``PermissionDenied``). Regla 5: un invernadero inactivo no se modifica
    (``invernadero_inactivo``); uno inexistente da ``Http404``.
    """
    _exigir_gerente(actor, "modificar")
    invernadero = _invernadero_para_consultar(invernadero_id)
    # El orden lo hace la base (con su collation, como ``Invernadero.transportistas``): ordenar en Python mandaría «Álvarez»
    # después de «Sosa». Sin invernadero primero (nulos primero), después por invernadero y por apellido y nombre.
    cuentas = (
        Transportista.objects.filter(is_active=True)
        .exclude(invernadero_asignado__invernadero=invernadero)
        .select_related("invernadero_asignado__invernadero")
        .order_by(
            Lower("invernadero_asignado__invernadero__nombre_invernadero").asc(nulls_first=True),
            Lower("last_name"),
            Lower("first_name"),
            "pk",
        )
    )
    lista = []
    for cuenta in cuentas:
        fila = getattr(cuenta, "invernadero_asignado", None)  # sin fila, el acceso falla con una subclase de AttributeError
        lista.append(Candidato(cuenta, fila.invernadero if fila else None))
    return lista


def agregar_transportista(actor, invernadero_id, transportista_id, *, traslado_confirmado=False):
    """PROD-MOD-INV, regla 8 y postcondición g: agrega a ``transportista_id`` al invernadero (si no tiene invernadero) o lo
    traslada (si trabaja para otro). Devuelve la ``TransportistaInvernadero`` resultante.

    - Precondición a: ``actor`` es un Gerente activo (``PermissionDenied``). Ids inexistentes, o una cuenta que no es de un
      Transportista: ``Http404``.
    - Rechazos (``ValidationError`` general, con su código): ``transportista_inactivo`` (solo se agregan activos, regla 8),
      ``ya_pertenece`` e ``invernadero_inactivo`` (regla 5). Se verifican después de bloquear la cuenta, así que un Transportista
      que se da de baja mientras tanto no se agrega.
    - Regla 8: si trabaja para otro invernadero es un traslado y el Sistema lo informa antes de confirmar: sin
      ``traslado_confirmado`` lanza ``FaltaConfirmarTraslado`` (con el origen) y no cambia nada. Confirmado, pide
      ``impedimentos_de_transportista``: con alguno (reglas 9 y 10, los registra `comercial`), rechaza con SUS códigos y no
      cambia nada. Sin registrantes no hay impedimentos.
    - Postcondición g: se crea la fila (o se cambian ``invernadero`` y ``desde``), el Transportista recibe una notificación y
      queda un ``modificacion_invernadero`` por cada invernadero que cambió (el destino y, en un traslado, también el origen).
    - Regla 11: no se toca nada más (ni el personal, ni el vehículo, ni las alertas).
    Bloqueos: ver el encabezado de este archivo.
    """
    _exigir_gerente(actor, "modificar")
    with transaction.atomic():
        _actor_sigue_activo(actor)
        cuenta = _bloquear_transportista(transportista_id)
        if not cuenta.is_active:
            raise _error_general(MENSAJE_TRANSPORTISTA_INACTIVO, "transportista_inactivo")
        # La fila de este Transportista no puede cambiar mientras tengamos su cuenta bloqueada (agregar, trasladar y quitar
        # la bloquean primero), así que se sabe el origen antes de bloquear los invernaderos.
        origen_id = TransportistaInvernadero.objects.filter(transportista_id=cuenta.pk).values_list("invernadero_id", flat=True).first()
        if origen_id == invernadero_id:
            raise _error_general(MENSAJE_YA_PERTENECE, "ya_pertenece")
        destino = origen = None
        for pk in sorted({invernadero_id, origen_id} - {None}):  # orden ascendente de id (D-40)
            if pk == invernadero_id:
                destino = bloquear_invernadero_activo(pk)
            else:
                origen = Invernadero.objects.select_for_update(no_key=True, of=("self",)).get(pk=pk)
        fila = TransportistaInvernadero.objects.filter(transportista_id=cuenta.pk).first()  # se vuelve a leer
        if fila is not None:
            if not traslado_confirmado:
                raise FaltaConfirmarTraslado(origen)
            impedimentos = extensiones.impedimentos_de_transportista(cuenta)
            if impedimentos:
                raise _error_de_impedimentos(impedimentos)
        antes_destino = _referencias(destino)
        antes_origen = _referencias(origen) if origen else None
        if fila is None:
            fila = TransportistaInvernadero.objects.create(transportista=cuenta, invernadero=destino, desde=timezone.now())
            titulo = f"Trabajás para {destino.nombre_invernadero}"
            detalle = f"Desde ahora podés recibir entregas de {destino.nombre_invernadero}."
        else:
            fila.invernadero = destino
            fila.desde = timezone.now()
            fila.save(update_fields=["invernadero", "desde"])
            titulo = f"Te pasaron a {destino.nombre_invernadero}"
            detalle = (
                f"Dejás de trabajar para {origen.nombre_invernadero}. "
                f"Desde ahora podés recibir entregas de {destino.nombre_invernadero}."
            )
        notificaciones.notificar_a_varios([cuenta], titulo, detalle, excluir=actor)
        _auditar(actor, destino, cuenta, antes_destino)
        if origen is not None:
            _auditar(actor, origen, cuenta, antes_origen)
    return fila


def _fila_para_quitar(invernadero_id, transportista_id):
    """La fila del Transportista en ese invernadero, o ``no_pertenece`` si trabaja para otro o para ninguno."""
    fila = TransportistaInvernadero.objects.filter(
        transportista_id=transportista_id, invernadero_id=invernadero_id
    ).first()
    if fila is None:
        raise _error_general(MENSAJE_NO_PERTENECE, "no_pertenece")
    return fila


def quitar_transportista(actor, invernadero_id, transportista_id):
    """PROD-MOD-INV, reglas 5, 9 y 10 y postcondición g: quita a ``transportista_id`` del invernadero; queda sin invernadero.
    Devuelve la cuenta del Transportista.

    - Precondición a: ``actor`` es un Gerente activo (``PermissionDenied``). Ids inexistentes o una cuenta que no es de un
      Transportista: ``Http404``.
    - Rechazos (con su código): ``invernadero_inactivo`` (regla 5), ``no_pertenece`` y los impedimentos de
      ``impedimentos_de_transportista`` (reglas 9 y 10): se informan todos y no se cambia nada.
    - Un Transportista **inactivo** se puede quitar (D-55, punto 8): los impedimentos se piden igual.
    - Postcondición g: se borra la fila, el Transportista recibe una notificación y se audita (un ``modificacion_invernadero``).
    Bloqueos: la cuenta y, después, el invernadero (encabezado de este archivo).
    """
    _exigir_gerente(actor, "modificar")
    with transaction.atomic():
        _actor_sigue_activo(actor)
        cuenta = _bloquear_transportista(transportista_id)
        invernadero = _bloquear_invernadero(invernadero_id)
        if not invernadero.activo:
            raise _error_general(MENSAJE_INACTIVO_NO_SE_MODIFICA, "invernadero_inactivo")
        fila = _fila_para_quitar(invernadero.pk, cuenta.pk)
        impedimentos = extensiones.impedimentos_de_transportista(cuenta)
        if impedimentos:
            raise _error_de_impedimentos(impedimentos)
        antes = _referencias(invernadero)
        fila.delete()
        notificaciones.notificar_a_varios(
            [cuenta],
            f"Ya no trabajás para {invernadero.nombre_invernadero}",
            "No vas a recibir entregas hasta que te agreguen a otro invernadero.",
            excluir=actor,
        )
        _auditar(actor, invernadero, cuenta, antes)
    return cuenta


def impedimentos_para_quitar(actor, invernadero_id, transportista_id):
    """Reglas 9 y 10 de PROD-MOD-INV: los impedimentos de quitar (o de trasladar) a ese Transportista, para la ventana. Solo
    lectura: no bloquea, no cambia nada y no audita; ``quitar_transportista`` los vuelve a verificar con todo bloqueado.

    Los mismos rechazos previos que ``quitar_transportista``: ``Http404``, ``invernadero_inactivo`` y ``no_pertenece``.
    """
    _exigir_gerente(actor, "modificar")
    transportista = Transportista.objects.filter(pk=transportista_id).first()
    if transportista is None:
        raise Http404("No existe ese transportista.")
    invernadero = _invernadero_para_consultar(invernadero_id)
    _fila_para_quitar(invernadero.pk, transportista.pk)
    return extensiones.impedimentos_de_transportista(transportista)


# ---- La cuenta del Transportista (USR-CNS-USR regla 3 y USR-GST-PRF regla 1, D-55 punto 2) ----

NOTA_DEL_INVERNADERO = "Se asigna desde la ficha del invernadero, en “Logística”."


def datos_de_cuenta(cuenta):
    """Lo que `maestros` registra en ``core.extensiones.registrar_datos_de_cuenta`` (desde ``MaestrosConfig.ready()``): para un
    Transportista, ``DatoDeCuenta("Invernadero", nombre o "Sin invernadero", nota)``; para los demás roles, nada. Solo lectura:
    una consulta para el Transportista (con ``select_related``) y ninguna para los otros. La ficha de la cuenta muestra la nota;
    «Mi perfil», no. Un Transportista inactivo conserva su invernadero (la fila queda como historial, D-55 punto 8)."""
    if cuenta.rol != Usuario.Rol.TRANSPORTISTA:
        return []
    fila = TransportistaInvernadero.objects.select_related("invernadero").filter(transportista_id=cuenta.pk).first()
    valor = fila.invernadero.nombre_invernadero if fila else "Sin invernadero"
    return [DatoDeCuenta("Invernadero", valor, NOTA_DEL_INVERNADERO)]
