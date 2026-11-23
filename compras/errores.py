# Error de negocio de `compras` (CMP-01): lo lanzan los servicios cuando un estado o una precondición impide la operación y la pantalla necesita
# el código y los datos para ofrecer cómo seguir (por ejemplo, reactivar al proveedor que tiene ese CUIT). Los errores de los datos de un
# formulario siguen siendo ``ValidationError`` por campo (docs/patrones/abm.md, sección 2). Misma forma que `produccion/errores.py`.


class ErrorDeCompras(Exception):
    """Rechazo de una regla de negocio de `compras`. ``codigo`` es estable (``cuit_de_inactivo``, ``proveedor_inactivo``,
    ``proveedor_no_inactivo``, ``baja_con_impedimentos``, ...); ``mensaje`` es el texto para la persona; ``campo`` es el campo del
    formulario al que pertenece el error, o ``None`` si es general. ``datos`` es un dict con lo que la pantalla necesita para ofrecer
    cómo resolverlo (los ids para enlazar, la lista de impedimentos); vacío si el rechazo no trae nada."""

    def __init__(self, codigo, mensaje, campo=None, datos=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.campo = campo
        self.datos = dict(datos or {})
