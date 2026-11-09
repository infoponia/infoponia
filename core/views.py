# Vistas de core: inicio de sesión, cierre de sesión e inicio de cada cuenta. Solo orquestan.

from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render

from core.forms import FormularioInicioSesion


class IniciarSesionView(LoginView):
    """Pantalla de inicio de sesión (USR-INI-SES, SEG-01). Exenta del login obligatorio por Django.

    Una cuenta que ya tiene sesión es llevada directamente a su inicio.
    """

    template_name = "core/iniciar_sesion.html"
    authentication_form = FormularioInicioSesion
    redirect_authenticated_user = True


# SEG-08: Django vacía la sesión en el servidor, no solo la cookie, y solo acepta POST.
# Se exime del login obligatorio para que una sesión ya vencida pueda cerrarse sin rebotar.
cerrar_sesion = login_not_required(LogoutView.as_view())


def inicio(request):
    """Inicio de la cuenta: indica con qué rol opera (USR-INI-SES postcondición a, vHome).

    El contenido del panel de cada rol llega con los módulos de negocio.
    """
    return render(request, "core/inicio.html")
