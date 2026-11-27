# Error de negocio de `contabilidad` (docs/api/asientos.md, «Escritura»): lo lanzan los servicios ante cualquier rechazo de una regla o un
# uso incorrecto del servicio de asientos. Lleva un código estable (para las pruebas y las pantallas), el mensaje para la persona y, si
# corresponde, el campo del formulario. Mismo molde que `ErrorDeProduccion` y `ErrorDeCompras`.


# Código del error de la regla 9 de CON-INI-EJE («sin ejercicio no hay asiento», tarea CON-05). Lo atiende `contabilidad.middleware`; nadie más lo atrapa.
CODIGO_NO_INICIADA = "contabilidad_no_iniciada"


class ErrorContable(Exception):
    """Rechazo de una regla de `contabilidad`. `codigo` es estable (`asiento_desbalanceado`, `cuenta_inexistente`, `origen_con_asiento`,
    `importe_invalido`, `tipo_de_movimiento_invalido`, `fecha_en_ejercicio_cerrado`, `fecha_futura`,
    `fecha_anterior_al_primer_ejercicio`, `ejercicios_atrasados`, ...); `campo` es el campo del formulario al que pertenece el error, o
    `None` si es general. `datos` es un dict con lo que la pantalla necesita para ofrecer cómo resolverlo; vacío si el rechazo no trae
    nada. Los de `registrar_asiento_automatico` son errores de programación: la pantalla no los muestra como error de un campo."""

    def __init__(self, codigo, mensaje, campo=None, datos=None):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje
        self.campo = campo
        self.datos = dict(datos or {})

    @property
    def errores(self):
        """La lista de errores que lleva este rechazo: uno solo (él mismo). `ErroresContables` lleva varios (CON-03b, patrón ABM sección 2)."""
        return [self]


def relanzar_si_no_iniciada(error):
    """Para las vistas que atrapan `ErrorContable` de forma general: si es `contabilidad_no_iniciada`, lo vuelve a lanzar para que lo atienda el middleware (regla 9 de CON-INI-EJE).
    Se llama primero dentro del `except`; con cualquier otro código no hace nada."""
    if error.codigo == CODIGO_NO_INICIADA:
        raise error


class ErroresContables(ErrorContable):
    """Varios errores de campo juntos (descripción y líneas de un asiento manual, CON-03b): la pantalla los marca todos a la vez. Su `codigo`,
    `mensaje` y `campo` son los del primero; `errores` los trae a todos, en el orden en que se encontraron."""

    def __init__(self, errores):
        primero = errores[0]
        super().__init__(primero.codigo, primero.mensaje, primero.campo, primero.datos)
        self._errores = list(errores)

    @property
    def errores(self):
        return self._errores
