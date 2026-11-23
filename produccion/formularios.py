# Lo que envían los formularios de `produccion` (PRD-01, paso 8) convertido en los datos de los servicios (`DatosDeSiembra`,
# `DatosDeConcrecion`). Las vistas solo orquestan: acá no hay reglas de negocio, solo conversión. Un valor que no se puede convertir
# (un texto en lugar de un número, una fecha mal escrita) NO se arregla en silencio: se pasa como valor inválido y es el servicio el que
# lo rechaza con su código y su campo, así la pantalla muestra el mismo error que mostraría cualquier otro cliente.

from datetime import date

from django.utils import timezone

from produccion.servicios import siembras, transiciones

PRIORIDADES = (("", "Sin prioridad (cuenta como media)"), ("alta", "Alta"), ("media", "Media"), ("baja", "Baja"))


def entero(valor):
    """`valor` como `int`, o `None` si está vacío o no es un número entero."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def fecha(valor):
    """`valor` («aaaa-mm-dd», lo que envía un campo de fecha) como `date`, o `None` si está vacío o es inválido."""
    try:
        return date.fromisoformat(str(valor).strip())
    except ValueError:
        return None


def cantidad(valor):
    """Una cantidad escrita con coma o con punto, como texto para que el servicio la valide con los decimales de la unidad."""
    return str(valor).strip().replace(",", ".")


def siembra_desde_post(datos):
    """Los `DatosDeSiembra` de «Nueva siembra»: los campos `sector_<id>` (plantines por sector de germinación) y `insumo_<id>` (cantidad
    de cada insumo adicional) que traen algo escrito."""
    distribucion = tuple(
        (int(clave[len("sector_"):]), entero(valor) if entero(valor) is not None else -1)
        for clave, valor in datos.items()
        if clave.startswith("sector_") and clave[len("sector_"):].isdigit() and valor.strip()
    )
    adicionales = tuple(
        (int(clave[len("insumo_"):]), cantidad(valor))
        for clave, valor in datos.items()
        if clave.startswith("insumo_") and clave[len("insumo_"):].isdigit() and valor.strip()
    )
    return siembras.DatosDeSiembra(
        invernadero_id=entero(datos.get("invernadero")),
        variedad_id=entero(datos.get("variedad")),
        cantidad=entero(datos.get("cantidad")),
        fecha_programada=fecha(datos.get("fecha_programada")),
        distribucion=distribucion,
        prioridad=datos.get("prioridad") or None,
        descripcion=datos.get("descripcion", ""),
        insumos_adicionales=adicionales,
    )


def concrecion_desde_post(datos, reservas):
    """Los `DatosDeConcrecion` de «Concretar siembra». `reservas` son las filas de la propuesta: de cada una se leen, si traen algo,
    `utilizada_<existencia>` (menos la semilla, que es el total sembrado), `devuelta_<existencia>` y `lote_<existencia>_<lote>` (los lotes
    elegidos, extensión 17b). Lo que queda vacío toma lo que propone el sistema."""
    fecha_efectiva = fecha(datos.get("fecha_efectiva")) if datos.get("fecha_efectiva", "").strip() else None
    if datos.get("fecha_efectiva", "").strip() and fecha_efectiva is None:
        fecha_efectiva = date.max  # una fecha inválida no se ignora: el servicio la rechaza como posterior a hoy
    sembrado = tuple(
        (int(clave[len("sembrado_"):]), entero(valor) if entero(valor) is not None else -1)
        for clave, valor in datos.items()
        if clave.startswith("sembrado_") and clave[len("sembrado_"):].isdigit() and valor.strip()
    )
    ajustes = []
    for fila in reservas:
        utilizada = cantidad(datos.get(f"utilizada_{fila.existencia_id}", "")) or None
        devuelta = cantidad(datos.get(f"devuelta_{fila.existencia_id}", "")) or None
        lotes = tuple(
            (int(clave.rsplit("_", 1)[1]), cantidad(valor))
            for clave, valor in datos.items()
            if clave.startswith(f"lote_{fila.existencia_id}_") and valor.strip()
        )
        if utilizada or devuelta or lotes:
            ajustes.append(
                siembras.AjusteDeInsumo(fila.existencia_id, None if fila.es_semilla else utilizada, devuelta, lotes or None)
            )
    return siembras.DatosDeConcrecion(
        fecha_efectiva=fecha_efectiva,
        sembrado=sembrado or None,
        motivo_diferencia=datos.get("motivo_diferencia", ""),
        ajustes=tuple(ajustes),
    )


def transicion_desde_post(datos):
    """Los `DatosDeTransicion` de «Nueva transición»: los campos `sector_<id>` (plantas por sector destino) que traen algo escrito (un sector
    en blanco o en 0 no entra: «quitar un sector», extensión 8-9a), y lo que la persona VIO del lote (`cantidad_vista` y `etapa_vista`), para
    que el servicio detecte si cambió (extensiones 13a y 13b)."""
    distribucion = []
    for clave, valor in datos.items():
        if clave.startswith("sector_") and clave[len("sector_"):].isdigit() and valor.strip():
            plantas = entero(valor)
            if plantas != 0:  # 0 quita el sector; un valor que no es número pasa como -1 y lo rechaza el servicio
                distribucion.append((int(clave[len("sector_"):]), plantas if plantas is not None else -1))
    return transiciones.DatosDeTransicion(
        lote_id=entero(datos.get("lote")),
        fecha_programada=fecha(datos.get("fecha_programada")),
        distribucion=tuple(distribucion),
        prioridad=datos.get("prioridad") or None,
        descripcion=datos.get("descripcion", ""),
        cantidad=entero(datos.get("cantidad_vista")),
        etapa_actual_id=entero(datos.get("etapa_vista")),
    )


def concrecion_de_transicion_desde_post(datos):
    """Los `DatosDeConcrecionDeTransicion` de «Concretar transición»: la fecha (en blanco, hoy), los `ubicadas_<id>` que traen algo
    (los demás toman lo propuesto, paso 8), la causa y la descripción de la merma, y la cantidad actual que la persona vio."""
    texto = datos.get("fecha_efectiva", "").strip()
    fecha_efectiva = (fecha(texto) or date.max) if texto else timezone.localdate()  # una fecha inválida la rechaza el servicio
    cantidades = tuple(
        (int(clave[len("ubicadas_"):]), entero(valor) if entero(valor) is not None else -1)
        for clave, valor in datos.items()
        if clave.startswith("ubicadas_") and clave[len("ubicadas_"):].isdigit() and valor.strip()
    )
    return transiciones.DatosDeConcrecionDeTransicion(
        fecha_efectiva=fecha_efectiva,
        cantidades=cantidades,
        causa=datos.get("causa", ""),
        descripcion=datos.get("descripcion", ""),
        cantidad=entero(datos.get("cantidad_vista")),
    )
