# Envío de correo público de core (USR-10, D-54). Lo usan la recuperación de contraseña y la invitación (vía
# ``_enviar_correo`` de core/servicios.py) y cualquier app de nivel mayor que necesite mandar un correo (la primera es
# iot, IOT-04). core no conoce a quienes la llaman (regla A4): cada una trae su propia plantilla.

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from core.identidad import nombre_de_la_organizacion

logger = logging.getLogger(__name__)


def correo_configurado():
    """True si el envío de correo está configurado (D-33, SEG-12).

    Lee ``settings.CORREO_CONFIGURADO`` en cada llamada, sin guardar una copia: la única fuente de verdad es el ajuste,
    y las pruebas lo cambian con ``override_settings``.
    """
    return settings.CORREO_CONFIGURADO


def enviar_correo(cuenta, asunto, plantilla, contexto):
    """Envía a ``cuenta`` un correo en texto plano con ``plantilla`` y devuelve True si salió (D-33, D-35, D-54).

    ``cuenta`` necesita ``pk`` y ``email``. El contexto de la plantilla es ``contexto`` más ``nombre_organizacion``
    (D-48).

    Si el envío falla, la falla queda en los registros de errores (``logger.exception``) con el id de la cuenta y
    nunca con el contenido del correo, que puede llevar un enlace que da acceso a la cuenta (SEG-12, regla 11 de
    USR-ALT-USR); devuelve False y quien llama decide qué ve la persona.

    Se llama siempre fuera de una transacción: un servidor SMTP lento (hasta ``EMAIL_TIMEOUT``) no puede mantener
    bloqueos tomados (D-14).
    """
    cuerpo = render_to_string(plantilla, {**contexto, "nombre_organizacion": nombre_de_la_organizacion()})
    try:
        send_mail(asunto, cuerpo, settings.DEFAULT_FROM_EMAIL, [cuenta.email])
    except Exception:
        logger.exception("No se pudo enviar el correo «%s» a la cuenta %s.", asunto, cuenta.pk)
        return False
    return True
