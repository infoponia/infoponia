# Bloqueo de las cuentas con contraseña temporal (USR-INI-SES regla 4, SEG-04, D-18): hasta que la
# persona la reemplaza por una propia, solo puede ver la pantalla de elegirla y cerrar sesión.

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def permitido_con_contrasena_temporal(vista):
    """Marca una vista como accesible con contraseña temporal (la de elegir contraseña, cerrar sesión).

    Mismo patrón que ``LoginRequiredMiddleware`` con ``@login_not_required`` de Django: un único
    punto (el middleware) bloquea todo por defecto y cada excepción se declara en la propia vista.
    Así una pantalla nueva queda bloqueada para estas cuentas sin que haya que acordarse de nada.
    """
    vista.permitido_con_contrasena_temporal = True
    return vista


class ContrasenaTemporalMiddleware:
    """Redirige a elegir contraseña a toda cuenta con sesión y contraseña temporal (SEG-04).

    Bloquea cualquier vista sin la marca ``@permitido_con_contrasena_temporal``, incluido el panel
    de administración de Django. Va después de ``AuthenticationMiddleware`` y de
    ``LoginRequiredMiddleware``. Una contraseña temporal que vence con la sesión ya abierta no
    bloquea nada más: quien tiene la sesión ya se identificó y puede reemplazarla igual.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Devuelve la redirección si la cuenta tiene temporal y la vista no está permitida."""
        usuario = request.user
        if not usuario.is_authenticated or not usuario.tiene_contrasena_temporal:
            return None
        if getattr(view_func, "permitido_con_contrasena_temporal", False):
            return None

        destino = reverse("core:elegir_contrasena")
        if request.headers.get("HX-Request") == "true":
            # Un pedido de HTMX no puede recibir un 302: el navegador lo seguiría solo y HTMX
            # metería la pantalla entera dentro del fragmento. Con HX-Redirect, HTMX cambia de página.
            respuesta = HttpResponse(status=200)
            respuesta["HX-Redirect"] = destino
            return respuesta
        return redirect(destino)
