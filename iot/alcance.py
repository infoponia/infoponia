# Alcance del IoT por usuario, en un único lugar (D-28; docs/casos_de_uso/iot/sistema_iot.md, «Para los cinco»; regla 4 de 8.22
# reescrita por MD-98): el IoT se opera por invernadero. Lo usan los ``QuerySet`` de ``iot/models.py`` y los servicios.
# Este módulo no importa ``iot.models``: lo importa ``iot.models``.

from django.db.models import Q

from core.models import Usuario, rol_de
from maestros.models import Invernadero


def _activo(usuario):
    """Verdadero si ``usuario`` es una cuenta con sesión y activa."""
    return usuario is not None and getattr(usuario, "is_active", False)


def invernaderos_que_opera(usuario):
    """Invernaderos cuyo IoT ``usuario`` opera (MD-98): el Agrónomo activo, los activos a su cargo; el Gerente activo, los
    activos SIN Agrónomo activo (sin asignar o con el asignado inactivo), hasta que se asigne uno; cualquier otro, ninguno."""
    if not _activo(usuario):
        return Invernadero.objects.none()
    activos = Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO)
    rol = rol_de(usuario)
    if rol == Usuario.Rol.AGRONOMO:
        return activos.filter(agronomo_id=usuario.pk)
    if rol == Usuario.Rol.GERENTE:
        return activos.filter(Q(agronomo__isnull=True) | Q(agronomo__is_active=False))
    return Invernadero.objects.none()


def invernaderos_que_consulta(usuario):
    """Invernaderos cuyo IoT ``usuario`` consulta (MD-98): el Agrónomo activo, los activos a su cargo; el Gerente activo,
    todos; cualquier otro, ninguno. Es el alcance de consulta de ``Invernadero`` (``en_alcance_de``)."""
    return Invernadero.objects.en_alcance_de(usuario)


def puede_operar(usuario, invernadero):
    """Verdadero si ``usuario`` opera el IoT de ``invernadero``. Los servicios la vuelven a llamar DESPUÉS de bloquear el
    invernadero: si salió del alcance mientras esperaba, se rechaza (extensión 8b de IOT-REG-SIS)."""
    return invernaderos_que_opera(usuario).filter(pk=invernadero.pk).exists()
