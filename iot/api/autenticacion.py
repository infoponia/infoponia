# Autenticación del nodo central (D-70, punto 3; docs/api/nodo/respuestas_y_errores.md, sección 1): el pedido trae el token del sistema IoT en
# ``Authorization: Bearer <token>`` y se busca el sistema por el RESUMEN SHA-256 (``core.enlaces.resumen_de``). El token nunca se guarda, no se
# compara, no se registra ni se devuelve: vive en esta función el tiempo justo para calcular su resumen. Sin sesión ni cookies.


def resumen_del_encabezado(valor):
    """El SHA-256 del token del encabezado ``Authorization``, o ``None`` si no hay token (verificación 3 del contrato: ``token_ausente``). Lo que
    no es ``Bearer`` seguido de algo es «ausente»; un token con espacios o raro SÍ tiene resumen y se rechaza después como ``token_invalido``."""
    from core.enlaces import resumen_de

    partes = (valor or "").strip().split(None, 1)
    if len(partes) != 2 or partes[0].lower() != "bearer":
        return None
    token = partes[1].strip()
    return resumen_de(token) if token else None
