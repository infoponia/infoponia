# Lo que `produccion` registra en las otras apps desde `ProduccionConfig.ready()` (PRD-01, regla A4 de D-37; docs/api/produccion.md,
# sección 3). `maestros`, `inventario` y `core` son de nivel menor y no pueden importar `produccion`: ellas preguntan por sus puntos
# de extensión y estas funciones contestan. Cada una devuelve lo que pide su contrato, con una consulta por tabla para toda la
# lista de ids (nunca una por fila) y, sin datos, su resultado neutro. Todos los textos están en voseo rioplatense.
#
# Contrato de bloqueo (docs/patrones/bloqueos.md): corren dentro de la transacción del servicio que las llama, después de que este
# tomó el invernadero; las que bloquean filas propias (el traspaso) lo hacen en orden de id.
#
# Los filtros por tipo de orden usan listas de tipos permitidos (`tipo_orden__in`), nunca «todo menos X» (D-67 punto 1). La baja
# del invernadero es la excepción buscada: cuenta las órdenes «a realizar» de TODOS los tipos (D-64 punto 12).

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.template.loader import render_to_string
from django.urls import reverse

from core.extensiones import Asignacion, SeccionDeInicio
from core.models import Usuario, rol_de
from inventario.extensiones import USO_NEUTRO, OrdenQueReserva, UsoDeVariedad
from maestros.extensiones import Aviso, Contenido, Impedimento
from maestros.models import Invernadero
from produccion.models import Lote, OcupacionSector, OrdenTrabajo, ReservaInsumo, Siembra, TransicionEtapa
from produccion.servicios import lotes as api_lotes
from produccion.servicios import bitacora, ordenes

Estado = OrdenTrabajo.Estado
Tipo = OrdenTrabajo.Tipo


def _plural(cantidad, singular, plural):
    """«1 lote» o «3 lotes»."""
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def _url_de_la_orden(orden):
    """El enlace a la orden: solo para los tipos que `produccion` muestra; una entrega o un mantenimiento no tienen pantalla acá (D-30)."""
    if orden.tipo_orden in ordenes.TIPOS_DE_PRODUCCION:
        return reverse("produccion:orden", args=[orden.pk])
    return None


# ---- maestros: sectores ----


def agujeros_de_sector(ids):
    """`registrar_agujeros_de_sector`: `{sector_id: (ocupados, comprometidos)}`, derivados de las ocupaciones (D-50 punto 4).
    Ocupados = Σ `cant_agujeros_ocupados`; comprometidos = Σ `cant_agujeros_planificados` de las órdenes «a realizar» (regla 4 de
    8.13). Los sectores sin ocupaciones no figuran (valen `(0, 0)`)."""
    filas = (
        OcupacionSector.objects.filter(sector_id__in=list(ids))
        .values("sector_id")
        .annotate(
            ocupados=Sum("cant_agujeros_ocupados"),
            comprometidos=Sum("cant_agujeros_planificados", filter=Q(orden__estado_orden=Estado.A_REALIZAR)),
        )
    )
    return {f["sector_id"]: (f["ocupados"] or 0, f["comprometidos"] or 0) for f in filas}


def impedimentos_de_baja_de_sector(sector):
    """`registrar_impedimento_de_baja_de_sector`: `agujeros_ocupados` (lotes que lo ocupan) y `agujeros_comprometidos` (órdenes
    «a realizar» que lo tienen reservado), con su detalle (reglas 2 de PROD-BAJ-SCT). Dos consultas fijas."""
    lotes = list(
        Lote.objects.filter(ocupaciones__sector=sector, ocupaciones__cant_agujeros_ocupados__gt=0).distinct().order_by("id")
    )
    pendientes = list(
        OrdenTrabajo.objects.filter(ocupaciones__sector=sector, estado_orden=Estado.A_REALIZAR).distinct().order_by("id")
    )
    impedimentos = []
    if lotes:
        nombres = ", ".join(lote.codigo for lote in lotes)
        impedimentos.append(
            Impedimento(
                "agujeros_ocupados",
                f"Lo ocupan {_plural(len(lotes), 'lote', 'lotes')}: {nombres}.",
                "Ponelo fuera de servicio para reubicar las plantas o registrarlas como merma.",
            )
        )
    if pendientes:
        nombres = ", ".join(orden.codigo for orden in pendientes)
        impedimentos.append(
            Impedimento(
                "agujeros_comprometidos",
                f"Lo tienen reservado {_plural(len(pendientes), 'orden a realizar', 'órdenes a realizar')}: {nombres}.",
                "Cancelá esas órdenes o ponelo fuera de servicio.",
            )
        )
    return impedimentos


def contenido_de_sectores(sectores):
    """`registrar_contenido_de_sector`: `{sector_id: [Contenido]}`: los lotes que lo ocupan (con su variedad y las plantas que
    tienen ahí) y las órdenes «a realizar» que lo reservan (con su fecha y sus agujeros reservados). Dos consultas."""
    sectores = list(sectores)
    contenido = {sector.pk: [] for sector in sectores}
    ocupaciones = OcupacionSector.objects.filter(sector__in=sectores)
    for o in ocupaciones.filter(cant_agujeros_ocupados__gt=0, lote__isnull=False).select_related(
        "lote__siembra__variedad__cultivo"
    ).order_by("id"):
        contenido[o.sector_id].append(
            Contenido("lote", f"{o.lote.codigo} · {o.lote.siembra.variedad}", o.cant_agujeros_ocupados, None, None)
        )
    for o in ocupaciones.filter(orden__estado_orden=Estado.A_REALIZAR).select_related("orden").order_by("id"):
        texto = f"{o.orden.codigo} · {Tipo(o.orden.tipo_orden).label}"
        contenido[o.sector_id].append(
            Contenido("orden", texto, o.cant_agujeros_planificados, o.orden.fecha_programada_orden, _url_de_la_orden(o.orden))
        )
    return contenido


def perfil_de_sector(ids):
    """`registrar_perfil_de_sector`: el perfil familiar de las plantas del sector, o `None` si está vacío."""
    return api_lotes.perfil_de_sector(ids)


def avisos_de_cambio_de_tipo(invernadero, tipo_etapa):
    """`registrar_aviso_de_cambio_de_tipo` (regla 4 de PROD-MOD-SCT y de PROD-BAJ-SCT): lo que queda sin un sector activo de
    ``tipo_etapa``: los lotes activos que todavía deben pasar por esa etapa (con la fecha en que la necesitan, que es el fin de su
    etapa actual) y las siembras a realizar que la usan."""
    avisos = []
    ids = set(
        Lote.objects.filter(
            invernadero=invernadero,
            estado_lote=Lote.Estado.ACTIVO,
            etapa__tipo_etapa__puesto_global__lt=tipo_etapa.puesto_global,
            siembra__variedad__ciclo__etapas__tipo_etapa=tipo_etapa,
        ).values_list("pk", flat=True)
    )
    afectados = [f for f in api_lotes.lotes_activos_de([invernadero.pk]) if f.lote_id in ids] if ids else []
    if afectados:
        detalle = ", ".join(
            f"{f.codigo} (la necesita desde el {f.fecha_estimada_de_fin:%d/%m/%Y})" if f.fecha_estimada_de_fin else f.codigo
            for f in afectados
        )
        avisos.append(
            Aviso(
                f"{_plural(len(afectados), 'lote todavía tiene', 'lotes todavía tienen')} que pasar por {tipo_etapa.nombre_etapa}: {detalle}.",
                len(afectados),
            )
        )
    siembras = list(
        Siembra.objects.filter(
            invernadero=invernadero, estado_orden=Estado.A_REALIZAR, variedad__ciclo__etapas__tipo_etapa=tipo_etapa
        ).order_by("id")
    )
    if siembras:
        nombres = ", ".join(s.codigo for s in siembras)
        avisos.append(
            Aviso(
                f"{_plural(len(siembras), 'siembra a realizar pasa', 'siembras a realizar pasan')} por {tipo_etapa.nombre_etapa}: {nombres}.",
                len(siembras),
            )
        )
    # PRD-02: las transiciones «a realizar» cuyo destino es una etapa de ese tipo.
    transiciones = list(
        TransicionEtapa.objects.filter(
            invernadero=invernadero, estado_orden=Estado.A_REALIZAR, etapa_destino__tipo_etapa=tipo_etapa
        ).order_by("id")
    )
    if transiciones:
        nombres = ", ".join(t.codigo for t in transiciones)
        avisos.append(
            Aviso(
                f"{_plural(len(transiciones), 'transición a realizar va', 'transiciones a realizar van')} a {tipo_etapa.nombre_etapa}: {nombres}.",
                len(transiciones),
            )
        )
    return avisos


# ---- maestros: invernadero ----


def impedimentos_de_baja_del_invernadero(invernadero):
    """`registrar_impedimento_de_baja` (precondiciones c y d de PROD-BAJ-INV): `lotes_activos` y `ordenes_a_realizar`. Las órdenes
    se cuentan de TODOS los tipos (siembra, transición, cosecha, entrega, mantenimiento): D-64 punto 12 y punto 5 de «Tipos futuros»."""
    cantidad_de_lotes = Lote.objects.filter(invernadero=invernadero, estado_lote=Lote.Estado.ACTIVO).count()
    cantidad_de_ordenes = OrdenTrabajo.objects.filter(invernadero=invernadero, estado_orden=Estado.A_REALIZAR).count()
    impedimentos = []
    if cantidad_de_lotes:
        impedimentos.append(
            Impedimento(
                "lotes_activos",
                f"Tiene {_plural(cantidad_de_lotes, 'lote activo', 'lotes activos')}.",
                "Terminalos con su cosecha o registrá su merma.",
            )
        )
    if cantidad_de_ordenes:
        impedimentos.append(
            Impedimento(
                "ordenes_a_realizar",
                f"Tiene {_plural(cantidad_de_ordenes, 'orden de trabajo a realizar', 'órdenes de trabajo a realizar')}.",
                "Concretalas o cancelalas.",
            )
        )
    return impedimentos


def _ordenes_a_traspasar(invernadero, entrante):
    """Las órdenes «a realizar» del invernadero que todavía no son del Capataz entrante, por cada tabla hija con Capataz (D-53).
    Solo de los tipos de `TIPOS_DE_PRODUCCION` (D-67 punto 1): así no se superpone con los registrantes de COM-02 e IOT-07.
    Si el rol había quedado vacío, pasan también las del Capataz que se fue (MD-60)."""
    for clase in ordenes._HIJAS_CON_CAPATAZ:
        yield clase, clase.objects.filter(
            invernadero=invernadero,
            estado_orden=Estado.A_REALIZAR,
            tipo_orden__in=list(ordenes.TIPOS_DE_PRODUCCION),
        ).exclude(capataz_id=entrante.pk)


def contar_traspaso(invernadero, rol, saliente, entrante):
    """`registrar_traspaso`, `contar`: lo que recibiría el Capataz entrante, para el aviso de la regla 2 y la notificación de la
    postcondición c de PROD-MOD-INV. Solo para el rol `capataz` y con persona entrante."""
    if rol != "capataz" or entrante is None:
        return []
    cantidad = sum(consulta.count() for _, consulta in _ordenes_a_traspasar(invernadero, entrante))
    return [("órdenes de trabajo a realizar", cantidad)] if cantidad else []


def traspasar_ordenes(actor, invernadero, rol, saliente, entrante):
    """`registrar_traspaso`, `traspasar`: las órdenes «a realizar» pasan al Capataz entrante, actualizando `capataz` en cada tabla
    hija (D-53) con una consulta por tabla. Las bloquea en orden de id, después del invernadero (que ya tiene bloqueado quien
    llama). Devuelve las instancias tocadas, para que queden en el registro `modificacion_invernadero` (D-36, D-60 punto 4)."""
    if rol != "capataz" or entrante is None:
        return []
    tocadas = []
    for clase, consulta in _ordenes_a_traspasar(invernadero, entrante):
        pendientes = list(consulta.select_for_update(no_key=True, of=("self",)).order_by("pk"))
        if pendientes:
            clase.objects.filter(pk__in=[o.pk for o in pendientes]).update(capataz_id=entrante.pk)
            for orden in pendientes:
                orden.capataz_id = entrante.pk
            tocadas.extend(pendientes)
    return tocadas


def pestana_de_lotes(actor, invernadero):
    """`registrar_pestana_de_invernadero("lotes", "Lotes activos", ...)`: el HTML de los lotes activos del invernadero, o `None` si
    `actor` no ve la ficha (solo el Agrónomo a cargo y el Gerente, este en solo lectura)."""
    if not Invernadero.objects.en_alcance_de(actor).filter(pk=invernadero.pk).exists():
        return None
    return render_to_string("produccion/_pestana_lotes.html", {"lotes": api_lotes.lotes_activos_de([invernadero.pk])})


# ---- inventario ----


def reservas_de_insumo(ids):
    """`registrar_reservas_de_insumo`: `{existencia_id: Decimal}`: lo reservado por las reservas ACTIVAS de cualquier tipo de
    orden (punto 4 de «Tipos futuros»: los envases de una entrega restan del stock libre)."""
    filas = (
        ReservaInsumo.objects.filter(insumo_invernadero_id__in=list(ids), estado=ReservaInsumo.Estado.ACTIVA)
        .values("insumo_invernadero_id")
        .annotate(total=Sum("cantidad_reservada"))
    )
    return {f["insumo_invernadero_id"]: Decimal(f["total"]) for f in filas}


def ordenes_que_reservan(ids):
    """`registrar_ordenes_que_reservan`: `{existencia_id: [OrdenQueReserva]}`: las órdenes con una reserva activa. Se nombran
    «OT-0231 · Siembra»; las que `produccion` no muestra («OT-0231 · Entrega») van sin enlace (D-30)."""
    reservas = (
        ReservaInsumo.objects.filter(insumo_invernadero_id__in=list(ids), estado=ReservaInsumo.Estado.ACTIVA)
        .select_related("orden")
        .order_by("id")
    )
    por_existencia = defaultdict(list)
    for r in reservas:
        orden = r.orden
        por_existencia[r.insumo_invernadero_id].append(
            OrdenQueReserva(
                orden.pk,
                f"{orden.codigo} · {Tipo(orden.tipo_orden).label}",
                r.cantidad_reservada,
                orden.fecha_programada_orden,
                _url_de_la_orden(orden),
            )
        )
    return dict(por_existencia)


def uso_de_variedad(variedad_ids):
    """`registrar_uso_de_variedad`: `{variedad_id: UsoDeVariedad}`: si tiene lotes (aunque estén terminados), cuántos activos,
    cuántas órdenes «a realizar» (siembras de la variedad y, desde PRD-02, las transiciones de sus lotes) y en qué invernaderos
    hay lotes activos. Tres consultas."""
    ids = list(variedad_ids)
    con_lotes, activos, invernaderos = set(), defaultdict(int), defaultdict(set)
    for variedad_id, estado, invernadero_id in Lote.objects.filter(siembra__variedad_id__in=ids).values_list(
        "siembra__variedad_id", "estado_lote", "invernadero_id"
    ):
        con_lotes.add(variedad_id)
        if estado == Lote.Estado.ACTIVO:
            activos[variedad_id] += 1
            invernaderos[variedad_id].add(invernadero_id)
    pendientes = {
        f["variedad_id"]: f["n"]
        for f in Siembra.objects.filter(variedad_id__in=ids, estado_orden=Estado.A_REALIZAR)
        .values("variedad_id")
        .annotate(n=Count("pk"))
    }
    for fila in (
        TransicionEtapa.objects.filter(lote__siembra__variedad_id__in=ids, estado_orden=Estado.A_REALIZAR)
        .values(variedad_id=F("lote__siembra__variedad_id"))
        .annotate(n=Count("pk"))
    ):
        pendientes[fila["variedad_id"]] = pendientes.get(fila["variedad_id"], 0) + fila["n"]
    resultado = {}
    for variedad_id in ids:
        uso = UsoDeVariedad(
            variedad_id in con_lotes, activos[variedad_id], pendientes.get(variedad_id, 0), frozenset(invernaderos[variedad_id])
        )
        if uso != USO_NEUTRO:
            resultado[variedad_id] = uso
    return resultado


def variedades_presentes(invernadero_ids):
    """`registrar_variedades_presentes`: `{invernadero_id: set[variedad_id]}`: las variedades de los lotes activos y de las siembras
    «a realizar» (la definición del «umbral efectivo» de PROD-PNF-SMB). Dos consultas."""
    ids = list(invernadero_ids)
    presentes = defaultdict(set)
    for invernadero_id, variedad_id in Lote.objects.filter(
        invernadero_id__in=ids, estado_lote=Lote.Estado.ACTIVO
    ).values_list("invernadero_id", "siembra__variedad_id"):
        presentes[invernadero_id].add(variedad_id)
    for invernadero_id, variedad_id in Siembra.objects.filter(
        invernadero_id__in=ids, estado_orden=Estado.A_REALIZAR
    ).values_list("invernadero_id", "variedad_id"):
        presentes[invernadero_id].add(variedad_id)
    return dict(presentes)


def impedimentos_de_baja_de_variedad(variedad):
    """`registrar_impedimento_de_baja_de_variedad` (precondiciones d y e de PROD-BAJ-VAR): `lotes_activos` y `ordenes_a_realizar`."""
    uso = uso_de_variedad([variedad.pk]).get(variedad.pk, USO_NEUTRO)
    impedimentos = []
    if uso.lotes_activos:
        impedimentos.append(
            Impedimento(
                "lotes_activos",
                f"Tiene {_plural(uso.lotes_activos, 'lote activo', 'lotes activos')}.",
                "Terminalos con su cosecha o registrá su merma.",
            )
        )
    if uso.ordenes_a_realizar:
        impedimentos.append(
            Impedimento(
                "ordenes_a_realizar",
                f"Tiene {_plural(uso.ordenes_a_realizar, 'orden de trabajo a realizar', 'órdenes de trabajo a realizar')}.",
                "Concretalas o cancelalas.",
            )
        )
    return impedimentos


# ---- core ----


def asignaciones_de_cuenta(cuenta):
    """`registrar_asignaciones_de_cuenta` (regla 4 de USR-BAJ-USR): las órdenes «a realizar» de un Capataz, por
    `ordenes_del_capataz` (D-53); y qué pasará con ellas."""
    if rol_de(cuenta) != Usuario.Rol.CAPATAZ:
        return []
    cantidad = len(ordenes.ordenes_del_capataz(cuenta, estado=Estado.A_REALIZAR))
    if not cantidad:
        return []
    return [
        Asignacion(
            "Órdenes de trabajo a realizar",
            cantidad,
            "Pasan a quien el Gerente asigne como Capataz al modificar el invernadero (regla 3 de 8.22).",
        )
    ]


def seccion_de_inicio(usuario):
    """`registrar_seccion_de_inicio`: la bandeja del Capataz (vencidas, hoy y próximas) en su Inicio; `None` para los demás roles.
    La del Agrónomo la suma PRD-04."""
    if not getattr(usuario, "is_active", False) or rol_de(usuario) != Usuario.Rol.CAPATAZ:
        return None
    return SeccionDeInicio("produccion/_seccion_de_inicio.html", {"bandeja": ordenes.bandeja_del_capataz(usuario)})


def pestana_de_bitacora(actor, invernadero):
    """`registrar_pestana_de_invernadero("bitacora", "Bitácora", ...)` (PRD-03): el HTML de la bitácora del invernadero (la primera página, con sus filtros y, para el
    Agrónomo a cargo, los botones «Registrar evento» y «Registrar aplicación» con el invernadero ya elegido), o `None` si `actor` no la ve: la ven el Agrónomo a
    cargo y el Gerente (también de un invernadero dado de baja, regla 2 de PROD-CNS-BIT). El Capataz no consulta la bitácora."""
    from produccion.views_bitacora import contexto_de_la_consulta  # adentro: las vistas importan los servicios que importan este módulo

    if rol_de(actor) not in (Usuario.Rol.AGRONOMO, Usuario.Rol.GERENTE):
        return None
    if invernadero.pk not in {i.pk for i in bitacora.invernaderos_de_bitacora(actor)}:
        return None
    return render_to_string("produccion/_pestana_bitacora.html", contexto_de_la_consulta(actor, invernadero.pk, {}))
