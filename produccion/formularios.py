# Lo que envían los formularios de `produccion` (PRD-01, paso 8) convertido en los datos de los servicios (`DatosDeSiembra`,
# `DatosDeConcrecion`). Las vistas solo orquestan: acá no hay reglas de negocio, solo conversión. Un valor que no se puede convertir
# (un texto en lugar de un número, una fecha mal escrita) NO se arregla en silencio: se pasa como valor inválido y es el servicio el que
# lo rechaza con su código y su campo, así la pantalla muestra el mismo error que mostraría cualquier otro cliente.

from datetime import date

from django.utils import timezone

from produccion.servicios import aplicaciones, bitacora, mermas, sectores_fuera_de_servicio, siembras, transiciones

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


# ---- Registrar merma, aplicación de insumos y evento, y consultar la bitácora (PRD-03) ----


def pares(texto):
    """`"3:10,4:2"` → `((3, "10"), (4, "2"))`: lo que las pantallas guardan en un campo oculto de «lo que se vio» (12a y 10d). Vacío → `()`."""
    resultado = []
    for parte in str(texto or "").split(","):
        izquierda, _, derecha = parte.partition(":")
        if entero(izquierda) is not None:
            resultado.append((entero(izquierda), derecha.strip()))
    return tuple(resultado)


def _con_prefijo(datos, prefijo):
    """`{id: valor}` de los campos `<prefijo>_<id>` del formulario."""
    resultado = {}
    for clave, valor in datos.items():
        if clave.startswith(prefijo + "_") and entero(clave[len(prefijo) + 1 :]) is not None:
            resultado[entero(clave[len(prefijo) + 1 :])] = valor
    return resultado


def merma_desde_post(datos, con_vistos=True):
    """`DatosDeMerma` desde el formulario: una cantidad por sector (`cant_<sector>`; vacía = 0; un texto que no es un número se pasa tal cual y el
    servicio lo rechaza), la causa, la descripción y, con `con_vistos`, lo que la persona vio (`visto_cantidad` y `visto_ocupados`, para la extensión 10d).
    «Ver resumen» no los usa (`con_vistos=False`): lo visto es lo que mostró el resumen; solo «Confirmar» lo compara."""
    cantidades = []
    for sector_id, texto in sorted(_con_prefijo(datos, "cant").items()):
        texto = str(texto).strip()
        cantidades.append((sector_id, 0 if texto == "" else (entero(texto) if entero(texto) is not None else texto)))
    visto = pares(datos.get("visto_ocupados"))
    return mermas.DatosDeMerma(
        lote_id=entero(datos.get("lote")),
        cantidades=tuple(cantidades),
        causa=datos.get("causa", ""),
        descripcion=datos.get("descripcion", ""),
        cantidad_actual=entero(datos.get("visto_cantidad")) if con_vistos else None,
        ocupados=(
            tuple((s, int(v)) for s, v in visto)
            if con_vistos and "visto_ocupados" in datos and all(entero(v) is not None for _, v in visto)
            else None
        ),
    )


def aplicacion_desde_post(datos, existencia_ids, con_vistos=True):
    """`DatosDeAplicacion` desde el formulario: el alcance (`alcance` y `sectores`), una cantidad por insumo (`cantidad_<existencia>`; vacía = no se usó), el
    reparto corregido de un insumo con vencimiento (`reparto_<existencia>_<lote>`), la descripción y lo que la persona vio (`vistos_<existencia>` y
    `plantas_vistas`, para la extensión 12a; solo con `con_vistos`, como en la merma). Un número que no es un número lo rechaza el servicio."""
    lineas = []
    for existencia_id in existencia_ids:
        texto = str(datos.get(f"cantidad_{existencia_id}", "")).strip()
        if texto == "":
            continue
        reparto = tuple(
            (lote_id, cantidad(valor))
            for lote_id, valor in sorted(_con_prefijo(datos, f"reparto_{existencia_id}").items())
            if str(valor).strip() != ""
        )
        vistos = datos.get(f"vistos_{existencia_id}") if con_vistos else None
        lineas.append(
            aplicaciones.LineaDeAplicacion(
                existencia_id, cantidad(texto), reparto or None, None if vistos is None else tuple((l, d) for l, d in pares(vistos))
            )
        )
    plantas = datos.get("plantas_vistas") if con_vistos else None
    return aplicaciones.DatosDeAplicacion(
        invernadero_id=entero(datos.get("invernadero")),
        alcance=datos.get("alcance", "todo"),
        sector_ids=tuple(i for i in (entero(s) for s in datos.getlist("sectores")) if i is not None),
        lineas=tuple(lineas),
        descripcion=datos.get("descripcion", ""),
        plantas_vistas=None if plantas is None else tuple((l, int(v)) for l, v in pares(plantas) if entero(v) is not None),
    )


def evento_desde_post(datos):
    """`DatosDeEvento` desde el formulario."""
    return bitacora.DatosDeEvento(
        invernadero_id=entero(datos.get("invernadero")),
        descripcion=datos.get("descripcion", ""),
        lote_id=entero(datos.get("lote")),
        sector_id=entero(datos.get("sector")),
    )


def filtros_de_bitacora(datos):
    """`FiltrosDeBitacora` desde la consulta (`q`, `tipo`, `lote`, `sector`, `desde`, `hasta`)."""
    return bitacora.FiltrosDeBitacora(
        texto=datos.get("q", ""),
        tipo=datos.get("tipo", ""),
        lote_id=entero(datos.get("lote")),
        sector_id=entero(datos.get("sector")),
        desde=fecha(datos.get("desde", "")),
        hasta=fecha(datos.get("hasta", "")),
    )


def fuera_de_servicio_desde_post(datos, con_vistos=True):
    """`DatosDeFueraDeServicio` desde el formulario de «Poner fuera de servicio» (PROD-PNR-FDS): el sector, el motivo, la fecha, una cantidad por lote y
    destino (`reub_<lote>_<destino>`; vacía = 0; un texto que no es un número se pasa tal cual y el servicio lo rechaza), la causa y la descripción por
    lote (`causa_<lote>` y `desc_<lote>`) y, con `con_vistos`, lo que la persona vio (`visto_plantas`, `visto_libres` y `visto_ordenes`, para la extensión
    14a). «Ver resumen» no los usa (`con_vistos=False`): lo visto es lo que muestra el resumen; solo «Confirmar» lo compara."""
    reubicaciones = []
    for clave, texto in sorted(datos.items()):
        partes = clave.split("_")
        if len(partes) != 3 or partes[0] != "reub" or entero(partes[1]) is None or entero(partes[2]) is None:
            continue
        texto = str(texto).strip()
        reubicaciones.append((int(partes[1]), int(partes[2]), 0 if texto == "" else (entero(texto) if entero(texto) is not None else texto)))
    causas = tuple(
        (lote_id, datos.get(f"causa_{lote_id}", ""), datos.get(f"desc_{lote_id}", ""))
        for lote_id in sorted(_con_prefijo(datos, "causa"))
    )
    plantas, libres = pares(datos.get("visto_plantas")), pares(datos.get("visto_libres"))
    ordenes = [entero(i) for i in str(datos.get("visto_ordenes", "")).split(",") if i.strip()]
    return sectores_fuera_de_servicio.DatosDeFueraDeServicio(
        sector_id=entero(datos.get("sector")),
        motivo=datos.get("motivo", ""),
        fecha=fecha(datos.get("fecha")),
        reubicaciones=tuple(reubicaciones),
        causas=causas,
        plantas_vistas=tuple((l, int(p)) for l, p in plantas) if con_vistos and "visto_plantas" in datos and all(entero(p) is not None for _, p in plantas) else None,
        libres_vistos=tuple((s, int(v)) for s, v in libres) if con_vistos and "visto_libres" in datos and all(entero(v) is not None for _, v in libres) else None,
        ordenes_vistas=tuple(ordenes) if con_vistos and "visto_ordenes" in datos and None not in ordenes else None,
    )
