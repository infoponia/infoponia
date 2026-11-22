# Error de negocio de `produccion` (docs/api/produccion.md, sección 1): lo lanzan los servicios ante cualquier rechazo de una regla.
# Lleva un código estable (para las pruebas y las pantallas), el mensaje para la persona y, si corresponde, el campo del formulario.


class ErrorDeProduccion(Exception):
    """Rechazo de una regla de negocio de `produccion`. `codigo` es estable (`stock_insuficiente`, `orden_no_pendiente`, ...);
    `campo` es el campo del formulario al que pertenece el error, o `None` si es general. `datos` es un dict con lo que la pantalla
    necesita para ofrecer cómo resolverlo (por ejemplo, los ids para enlazar a otra pantalla); vacío si el rechazo no trae nada."""

    def __init__(self, codigo, mensaje, campo=None, datos=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.campo = campo
        self.datos = dict(datos or {})
