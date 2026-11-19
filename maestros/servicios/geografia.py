# Consultas de la geografía precargada de Georef (MD-88, regla 3 de PROD-ALT-INV): las listas encadenadas de provincia,
# departamento y localidad. Solo lectura: no tienen ABM. Archivo del bloque «geografía» (D-37 pide uno por entidad
# raíz; las tres entidades son un solo bloque del modelo y se consultan siempre juntas).

from maestros.models import Departamento, Localidad, Provincia


def provincias():
    """Todas las provincias, por nombre."""
    return Provincia.objects.all()


def departamentos_de(provincia_id):
    """Departamentos de la provincia ``provincia_id`` (vacío si el id no es un número o no existe), por nombre."""
    try:
        return Departamento.objects.filter(provincia_id=int(provincia_id))
    except (TypeError, ValueError):
        return Departamento.objects.none()


def localidades_de(departamento_id):
    """Localidades del departamento ``departamento_id`` (vacío si el id no es un número o no existe), por nombre."""
    try:
        return Localidad.objects.filter(departamento_id=int(departamento_id))
    except (TypeError, ValueError):
        return Localidad.objects.none()
