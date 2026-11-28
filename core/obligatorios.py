# Ayudante común de UI-06, paso 3 (D-109 punto 9, UX-27): en un formulario, los campos obligatorios que no dependen de otros se muestran todos juntos, no de a uno.
# Hoy un servicio rechaza en el primer obligatorio vacío (o la vista corta antes de llamarlo) y la pantalla muestra solo ese error. Cada vista, cuando el envío se rechazó, suma los obligatorios
# que vinieron vacíos y que el servicio todavía no había mirado, con el MISMO texto que el servicio (cada vista lo cita). No valida nada nuevo ni cambia un servicio: el del servicio gana en su campo.
# Solo se usa al enviar («Ver resumen», «Confirmar», «Guardar»…): nunca al redibujar campos (accion «actualizar», regla de INV-02).


def esta_vacio(valor):
    """El criterio de «vacío» de los servicios (p. ej. `inventario/servicios/insumos_invernadero.py:_vacio`): `None` o un texto de solo espacios."""
    return valor is None or (isinstance(valor, str) and not valor.strip())


def faltantes(datos, obligatorios):
    """`{clave: texto}` de los campos obligatorios que vinieron vacíos en ``datos`` (un `QueryDict` o un diccionario).

    ``obligatorios`` es una secuencia de ``(clave del error, nombre del campo en el formulario, texto)``: la clave es la que usa la plantilla para mostrar el error; el texto, el que el servicio
    da para ese campo (con su cita en la vista que lo define)."""
    return {clave: texto for clave, nombre, texto in obligatorios if esta_vacio(datos.get(nombre))}


def sumar_faltantes(errores, datos, obligatorios, como_lista=False):
    """Suma a ``errores`` los obligatorios vacíos que todavía no tienen error (el del servicio gana en su campo) y devuelve ``errores``. ``como_lista=True`` guarda ``[texto]``
    (las pantallas cuyos errores son listas de mensajes por campo)."""
    for clave, texto in faltantes(datos, obligatorios).items():
        errores.setdefault(clave, [texto] if como_lista else texto)
    return errores
