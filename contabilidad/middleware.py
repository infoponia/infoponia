# Middleware de la regla 9 de CON-INI-EJE, «Sin ejercicio no hay asiento» (tarea CON-05; docs/casos_de_uso/contabilidad/ejercicio.md, «Cómo se aplica»).
# Cuando una operación con asiento se intenta sin ningún ejercicio, el servicio de asientos lanza `ErrorContable` `contabilidad_no_iniciada` y la transacción de quien llama se
# deshace entera; este middleware convierte esa excepción en la ventana o la página que corresponde, en UN solo lugar (ninguna vista arma su propio aviso).
# Solo tiene `process_exception`: no mira ningún pedido, no consulta la base y no redirige nunca, así que no puede bloquear el login, el logout, los estáticos ni la
# pantalla de iniciar, ni armar un bucle de redirecciones. Deja pasar cualquier otra excepción (devuelve `None`).
from urllib.parse import urlencode, urlsplit

from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from contabilidad.errores import CODIGO_NO_INICIADA, ErrorContable
from contabilidad.servicios import responsables

TEXTO_DEL_RESPONSABLE = (
    "Lo que estás registrando genera un asiento contable y la contabilidad todavía no está iniciada. La operación no se registró."
)
TEXTO_DE_OTROS = "La contabilidad no está iniciada. Pedile al Contador o al Gerente que la inicie. La operación no se registró."
TEXTO_EXTERNO = "No pudimos registrar la operación. Probá de nuevo más tarde."


def _ruta_del_mismo_sitio(request):
    """La ruta (con su consulta) del `Referer` si es una pantalla de este mismo sitio; si no, `None` (nunca una URL de otro host: evita la redirección abierta)."""
    referer = request.META.get("HTTP_REFERER", "")
    if not referer or not url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return None
    partes = urlsplit(referer)
    ruta = partes.path + (f"?{partes.query}" if partes.query else "")
    return ruta if ruta.startswith("/") and not ruta.startswith("//") else None


class ContabilidadNoIniciadaMiddleware:
    """Arma la respuesta de `contabilidad_no_iniciada` según quién opera y cómo (HTMX o pedido común). Va en `MIDDLEWARE` después de los de sesión, autenticación y mensajes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        """Atiende SOLO `ErrorContable` con el código `contabilidad_no_iniciada` (respuesta con estado 200); cualquier otra excepción sigue su camino.

        - Pedido HTMX (`HX-Request`): la ventana `contabilidad/_ventana_contabilidad_no_iniciada.html`, con `HX-Retarget: body` y `HX-Reswap: beforeend` para agregarla encima de la pantalla
          actual. «Iniciar ejercicio» abre la pantalla de inicio en otra pestaña (así la operación queda con lo que se escribió).
        - Pedido común: la página `contabilidad/contabilidad_no_iniciada.html`; «Iniciar ejercicio» lleva a la pantalla de inicio con `?volver=<ruta del Referer del mismo sitio>`.
        - Texto: el responsable contable (`responsables.puede_registrar_asientos`) ve el botón; otro usuario con cuenta, el aviso sin botón; sin usuario (pantallas de enlace), el
          mensaje genérico que no nombra la contabilidad.
        """
        if not isinstance(exception, ErrorContable) or exception.codigo != CODIGO_NO_INICIADA:
            return None
        usuario = getattr(request, "user", None)
        con_cuenta = usuario is not None and usuario.is_authenticated
        puede_iniciar = con_cuenta and responsables.puede_registrar_asientos(usuario)
        htmx = request.headers.get("HX-Request") == "true"
        ruta_de_origen = _ruta_del_mismo_sitio(request)
        url_iniciar = reverse("contabilidad:iniciar")
        if puede_iniciar:
            titulo, texto = "Falta iniciar la contabilidad", TEXTO_DEL_RESPONSABLE
            if not htmx and ruta_de_origen:
                url_iniciar = f"{url_iniciar}?{urlencode({'volver': ruta_de_origen})}"
        elif con_cuenta:
            titulo, texto = "Falta iniciar la contabilidad", TEXTO_DE_OTROS
        else:
            titulo, texto = "No se pudo registrar la operación", TEXTO_EXTERNO
        contexto = {
            "titulo": titulo,
            "texto": texto,
            "puede_iniciar": puede_iniciar,
            "url_iniciar": url_iniciar,
            "en_otra_pestana": htmx,
            "url_cerrar": ruta_de_origen or (reverse("core:inicio") if con_cuenta else None),
            "base_de_la_pagina": "core/base_con_sesion.html" if con_cuenta else "core/base_sin_sesion.html",
        }
        if htmx:
            respuesta = render(request, "contabilidad/_ventana_contabilidad_no_iniciada.html", contexto)
            respuesta["HX-Retarget"] = "body"
            respuesta["HX-Reswap"] = "beforeend"
            return respuesta
        return render(request, "contabilidad/contabilidad_no_iniciada.html", contexto)
