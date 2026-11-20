# API de notificaciones de core (NOT-01, D-42; contrato en docs/api/notificaciones.md). Una notificación es un aviso de
# texto para una cuenta: no tiene estado, severidad ni enlace (D-38). Las funciones se llaman DENTRO de la transacción del
# caso de uso que las dispara (regla de uso 1): si el caso de uso falla, no queda ninguna. No se auditan (D-42).
#
# Esta capa no importa ``core.servicios`` (evita un ciclo: ``alta_usuario`` la usa) ni ninguna app de nivel mayor (A1 de
# D-37): lo que viene de ``maestros`` llega por los puntos de extensión de ``core.extensiones``.

from core import extensiones
from core.models import Notificacion, Usuario

# Largos de las columnas (D-42): se rechazan acá con ``ValueError`` y no con un error de la base.
LARGO_TITULO = Notificacion._meta.get_field("titulo").max_length
LARGO_DETALLE = Notificacion._meta.get_field("detalle").max_length


def _texto_valido(titulo, detalle):
    """Valida y recorta el título y el detalle: con contenido y dentro del largo; si no, ``ValueError`` (error de uso de
    quien notifica, no de la persona). Devuelve ``(titulo, detalle)`` recortados."""
    titulo = (titulo or "").strip()
    detalle = (detalle or "").strip()
    if not titulo:
        raise ValueError("El título de la notificación no puede estar vacío.")
    if not detalle:
        raise ValueError("El detalle de la notificación no puede estar vacío.")
    if len(titulo) > LARGO_TITULO:
        raise ValueError(f"El título de la notificación pasa de {LARGO_TITULO} caracteres.")
    if len(detalle) > LARGO_DETALLE:
        raise ValueError(f"El detalle de la notificación pasa de {LARGO_DETALLE} caracteres.")
    return titulo, detalle


def notificar(destinatario, titulo, detalle):
    """Crea una notificación para ``destinatario`` (un ``Usuario`` o cualquiera de sus roles) y la devuelve.

    ``ValueError`` si el título o el detalle están vacíos o pasan el largo."""
    titulo, detalle = _texto_valido(titulo, detalle)
    return Notificacion.objects.create(destinatario=destinatario, titulo=titulo, detalle=detalle)


def notificar_al_gerente(titulo, detalle):
    """La crea para el Gerente activo. Sin Gerente activo no hace nada, no falla y devuelve ``None`` (D-14: lo que espera
    al Gerente no se asigna a una persona; la notificación sin destinatario se omite). El texto se valida igual: un texto
    vacío es un error de uso aunque no haya a quién avisarle."""
    titulo, detalle = _texto_valido(titulo, detalle)
    gerente = Usuario.objects.filter(rol=Usuario.Rol.GERENTE, is_active=True).first()
    if gerente is None:
        return None
    return Notificacion.objects.create(destinatario=gerente, titulo=titulo, detalle=detalle)


def notificar_a_varios(cuentas, titulo, detalle, *, excluir=None):
    """Una notificación por cuenta de ``cuentas``, sin repetir cuentas, sin ``None`` (un rol sin responsable) y sin la cuenta
    ``excluir`` (el actor: notificarse a uno mismo es un error de uso). Las cuentas se comparan por ``pk``, así que da lo
    mismo que lleguen como ``Usuario`` o como su rol. Devuelve la lista de las creadas."""
    titulo, detalle = _texto_valido(titulo, detalle)
    vistas = {excluir.pk} if excluir is not None else set()
    creadas = []
    for cuenta in cuentas:
        if cuenta is None or cuenta.pk in vistas:
            continue
        vistas.add(cuenta.pk)
        creadas.append(Notificacion.objects.create(destinatario=cuenta, titulo=titulo, detalle=detalle))
    return creadas


def de_la_cuenta(usuario):
    """Las notificaciones de ``usuario``, de la más reciente a la más antigua (las usa la campana). ``QuerySet``."""
    return Notificacion.objects.filter(destinatario_id=usuario.pk)


def marcar_vistas(usuario, ids):
    """Marca como leídas las notificaciones de ``usuario`` con esos ids; ignora las ajenas, las que no existen y las ya
    leídas. Es una sola sentencia condicional (no bloquea filas ni suma un bloqueo al orden global). Devuelve la cantidad
    marcada."""
    ids = list(ids)
    if not ids:
        return 0
    return Notificacion.objects.filter(destinatario_id=usuario.pk, pk__in=ids, leida=False).update(leida=True)


def pendientes_del_gerente():
    """Lo que espera una resolución del Gerente (D-14, D-42): ``(total, detalle)``, con el total y la lista de
    ``(descripción, cantidad)`` de los contadores registrados en ``core.extensiones``, solo con cantidad mayor que cero.
    Sin nada pendiente, ``(0, [])``. Lo usan USR-ALT-USR (postcondición d) y USR-BAJ-USR (postcondición c)."""
    detalle = [(descripcion, cantidad) for descripcion, cantidad in extensiones.contadores_de_pendientes() if cantidad > 0]
    return sum(cantidad for _, cantidad in detalle), detalle


def estado_de_la_campana(usuario):
    """Lo que dice el botón de la campana de ``usuario`` (D-42): ``{"punto": bool, "sin_leer": int}``. ``punto`` es verdadero si
    hay alguna alerta activa NO leída (la pestaña «Alertas» lista y cuenta todas las activas, pero el punto rojo solo avisa de
    las no leídas) o alguna notificación sin leer; ``sin_leer`` es la cantidad de notificaciones sin leer."""
    sin_leer = de_la_cuenta(usuario).filter(leida=False).count()
    hay_alerta_sin_leer = any(not item.leida for item in extensiones.alertas_para(usuario))
    return {"punto": hay_alerta_sin_leer or sin_leer > 0, "sin_leer": sin_leer}
