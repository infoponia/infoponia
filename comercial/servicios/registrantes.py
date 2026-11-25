# Lo que `comercial` registra en las apps de nivel menor desde `ComercialConfig.ready()` (COM-02; regla A4 de D-37): el traspaso de las
# compra-ventas al Vendedor nuevo de un invernadero (D-60, `maestros.extensiones.registrar_traspaso`) y el impedimento de baja de una
# variedad con compra-ventas abiertas (precondición f de PROD-BAJ-VAR, `inventario.extensiones.registrar_impedimento_de_baja_de_variedad`).
# COM-03a suma los suministros vigentes a las mismas funciones. Corren dentro de la transacción del servicio que las llama, después de que
# este tomó el invernadero; las que bloquean filas propias lo hacen en orden de id (docs/patrones/bloqueos.md, sección «comercial»).

from django.db.models import Count, Q

from comercial.models import CompraVenta, Contrato, Suministro
from maestros.extensiones import Impedimento
from maestros.models import Invernadero

ABIERTAS = (CompraVenta.Estado.ABIERTA, CompraVenta.Estado.PENDIENTE_DECISION)


def _ids_a_traspasar(invernadero, saliente):
    """Los ids de las compra-ventas «abiertas» o «pendientes de decisión» del Vendedor saliente que pasan al entrante (D-60, punto 2):
    **todas** si el saliente no conserva otro invernadero activo; si lo conserva, solo las atadas a este invernadero: un retiro en él, o
    una venta cuyas reservas no liberadas son todas de este invernadero (al menos una)."""
    del_saliente = CompraVenta.objects.filter(vendedor_id=saliente.pk, estado_venta__in=ABIERTAS)
    conserva_otro = (
        Invernadero.objects.filter(vendedor_id=saliente.pk, estado_invernadero=Invernadero.Estado.ACTIVO)
        .exclude(pk=invernadero.pk)
        .exists()
    )
    if not conserva_otro:
        return list(del_saliente.order_by("pk").values_list("pk", flat=True))
    atadas = (
        del_saliente.annotate(
            en_este=Count("detalles__reservas", filter=Q(detalles__reservas__invernadero=invernadero) & ~Q(detalles__reservas__estado_reserva="liberada"), distinct=True),
            en_otros=Count("detalles__reservas", filter=~Q(detalles__reservas__invernadero=invernadero) & ~Q(detalles__reservas__estado_reserva="liberada"), distinct=True),
        )
        .filter(Q(invernadero_retiro=invernadero) | Q(en_este__gt=0, en_otros=0))
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return list(atadas)


def _ids_de_suministros_a_traspasar(invernadero, saliente):
    """Los ids de los suministros «vigentes» del Vendedor saliente que pasan al entrante (D-60, punto 2): **todos** si el saliente no conserva
    otro invernadero activo; si lo conserva, solo los atados a este invernadero (todas sus reservas no liberadas son de este, al menos una)."""
    del_saliente = Suministro.objects.filter(vendedor_id=saliente.pk, estado_suministro=Suministro.Estado.VIGENTE)
    conserva_otro = (
        Invernadero.objects.filter(vendedor_id=saliente.pk, estado_invernadero=Invernadero.Estado.ACTIVO)
        .exclude(pk=invernadero.pk)
        .exists()
    )
    if not conserva_otro:
        return list(del_saliente.order_by("pk").values_list("pk", flat=True))
    no_liberada = ~Q(detalles__reservas__estado_reserva="liberada")
    atados = (
        del_saliente.annotate(
            en_este=Count("detalles__reservas", filter=Q(detalles__reservas__invernadero=invernadero) & no_liberada, distinct=True),
            en_otros=Count("detalles__reservas", filter=~Q(detalles__reservas__invernadero=invernadero) & no_liberada, distinct=True),
        )
        .filter(en_este__gt=0, en_otros=0)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    return list(atados)


def contar_contratos(invernadero, rol, saliente, entrante):
    """`registrar_traspaso`, `contar` (D-60, punto 4): lo que recibiría el Vendedor entrante, para el aviso de la regla 2 y la notificación
    de PROD-MOD-INV: «Compra-ventas abiertas: N». Solo con el rol `vendedor`, un saliente y una entrante."""
    if rol != "vendedor" or saliente is None or entrante is None:
        return []
    lineas = [
        ("Compra-ventas abiertas", len(_ids_a_traspasar(invernadero, saliente))),
        ("Suministros vigentes", len(_ids_de_suministros_a_traspasar(invernadero, saliente))),
    ]
    return [(texto, cantidad) for texto, cantidad in lineas if cantidad]


def traspasar_contratos(actor, invernadero, rol, saliente, entrante):
    """`registrar_traspaso`, `traspasar` (D-60): pasa al Vendedor entrante las compra-ventas que corresponden (misma regla que `contar`).
    Cambia solo el `vendedor` del contrato: las reservas no se mueven. Bloquea los contratos DESPUÉS del invernadero, en orden de id, y los
    vuelve a leer (``FOR NO KEY UPDATE``). Devuelve las instancias tocadas para el registro `modificacion_invernadero` (D-36). Sin saliente o
    sin entrante (la baja de un Vendedor no reasigna contratos, MD-60), no hace nada."""
    if rol != "vendedor" or saliente is None or entrante is None:
        return []
    ids_de_ventas = _ids_a_traspasar(invernadero, saliente)
    ids_de_suministros = _ids_de_suministros_a_traspasar(invernadero, saliente)
    if not ids_de_ventas and not ids_de_suministros:
        return []
    # Los contratos de las dos clases, juntos y en orden de id (`Contrato` es el padre de las dos).
    list(Contrato.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=ids_de_ventas + ids_de_suministros).order_by("pk"))
    # Ya bloqueados: se vuelve a leer qué sigue siendo del saliente y está abierto o vigente.
    tocadas = list(
        CompraVenta.objects.filter(pk__in=ids_de_ventas, vendedor_id=saliente.pk, estado_venta__in=ABIERTAS).order_by("pk")
    ) + list(
        Suministro.objects.filter(
            pk__in=ids_de_suministros, vendedor_id=saliente.pk, estado_suministro=Suministro.Estado.VIGENTE
        ).order_by("pk")
    )
    if tocadas:
        Contrato.objects.filter(pk__in=[c.pk for c in tocadas]).update(vendedor_id=entrante.pk)
        for contrato in tocadas:
            contrato.vendedor_id = entrante.pk
    return tocadas


def impedimentos_de_baja_de_variedad(variedad):
    """`registrar_impedimento_de_baja_de_variedad` (precondición f de PROD-BAJ-VAR): código `contratos_abiertos` si la variedad está en un
    detalle abierto o pendiente de una compra-venta abierta o pendiente de decisión, o en un detalle vigente de un suministro vigente
    («Tiene contratos abiertos: 2 compra-ventas y 1 suministro.»: el número que vale 0 se omite y se usa el singular, COM-03a)."""
    compra_ventas = (
        CompraVenta.objects.filter(
            estado_venta__in=ABIERTAS,
            detalles__variedad=variedad,
            detalles__estado_detalle_venta__in=["abierto", "pendiente_decision"],
        )
        .distinct()
        .count()
    )
    suministros = (
        Suministro.objects.filter(
            estado_suministro=Suministro.Estado.VIGENTE,
            detalles__variedad=variedad,
            detalles__estado_detalle_suministro="vigente",
        )
        .distinct()
        .count()
    )
    partes = []
    if compra_ventas:
        partes.append(f"{compra_ventas} compra-venta{'s' if compra_ventas != 1 else ''}")
    if suministros:
        partes.append(f"{suministros} suministro{'s' if suministros != 1 else ''}")
    if not partes:
        return []
    return [Impedimento("contratos_abiertos", f"Tiene contratos abiertos: {' y '.join(partes)}.", "Esperá a que se concreten o se cancelen.")]


# ---- COM-04a: lo que `comercial` le contesta a las pantallas de `produccion` (D-64 punto 11; docs/api/extensiones_de_produccion.md, puntos 3 y 4) ----


def acciones_de_cosechas(usuario, cosecha_ids):
    """`registrar_acciones_de_cosecha`: por cosecha, las URL de lo que `usuario` puede hacer (`AccionesDeCosecha`): `concretar` solo para el Capataz
    asignado, `modificar` y `cancelar` solo para el Agrónomo a cargo del invernadero, y todas `None` si la cosecha ya no está «a realizar» o su
    invernadero no está activo. **Nunca una URL a un 403** (D-30). Una consulta, sin consultas por cosecha."""
    from django.urls import reverse

    from core.models import Usuario, rol_de
    from produccion.extensiones import AccionesDeCosecha
    from produccion.models import Cosecha, OrdenTrabajo

    rol = rol_de(usuario) if getattr(usuario, "is_active", False) else None
    resultado = {}
    for cosecha in Cosecha.objects.filter(pk__in=list(cosecha_ids)).select_related("invernadero"):
        posible = cosecha.estado_orden == OrdenTrabajo.Estado.A_REALIZAR and cosecha.invernadero.activo
        concretar = posible and rol == Usuario.Rol.CAPATAZ and cosecha.capataz_id == usuario.pk
        del_agronomo = posible and rol == Usuario.Rol.AGRONOMO and cosecha.invernadero.agronomo_id == usuario.pk
        resultado[cosecha.pk] = AccionesDeCosecha(
            reverse("comercial:cosecha_concretar", args=[cosecha.pk]) if concretar else None,
            reverse("comercial:cosecha_modificar", args=[cosecha.pk]) if del_agronomo else None,
            reverse("comercial:cosecha_cancelar", args=[cosecha.pk]) if del_agronomo else None,
        )
    return resultado


def entradas_de_comercial(usuario):
    """`registrar_entradas_de_comercial`: «Planificar cosecha» para el Agrónomo con algún invernadero activo a su cargo y `merma_en_camara` (COM-04b, extensión 4a de
    PROD-REG-MRM) para el Agrónomo o el Capataz con algún invernadero activo con partidas disponibles (extensión 4b: aunque no tenga lotes activos). Nunca una URL a un 403."""
    from django.urls import reverse

    from comercial.servicios import merma_camara

    from core.models import Usuario, rol_de
    from produccion.extensiones import EntradasDeComercial

    planificar = None
    if getattr(usuario, "is_active", False) and rol_de(usuario) == Usuario.Rol.AGRONOMO:
        if Invernadero.objects.filter(agronomo_id=usuario.pk, estado_invernadero=Invernadero.Estado.ACTIVO).exists():
            planificar = reverse("comercial:cosecha_planificar")
    merma_en_camara = reverse("comercial:merma_camara") if merma_camara.invernaderos_con_merma_en_camara(usuario) else None
    # COM-05a2: «Envasado» (PROD-PNF-ENV) para el mismo Agrónomo que puede planificar cosechas: con algún invernadero activo a su cargo. Nunca una URL a un 403.
    envasado = reverse("comercial:envasado") if planificar is not None else None
    return EntradasDeComercial(planificar, merma_en_camara, envasado)


def seccion_de_cosechas(usuario):
    """`registrar_seccion_de_inicio` (`secCosecha` del prototipo, COM-04a y COM-04b): el grupo «Cosechas y cámara» del Inicio del Agrónomo, después de la sección de PRD-04:
    las cosechas «a realizar» de sus invernaderos activos que son de hoy, las vencidas (fecha programada anterior a hoy) y las de invernaderos sin Capataz activo, y los
    indicadores de la cámara (partidas por vencer y plantas libres). `None` para los demás roles. Una consulta de cosechas y una de partidas."""
    from comercial.servicios import camara
    from core.models import Usuario, rol_de
    from core.extensiones import SeccionDeInicio
    from django.utils import timezone
    from comercial.models import Entrega
    from produccion.models import Cosecha, OrdenTrabajo, ReservaInsumo

    if not getattr(usuario, "is_active", False) or rol_de(usuario) != Usuario.Rol.AGRONOMO:
        return None
    hoy = timezone.localdate()
    filas = list(
        Cosecha.objects.filter(
            estado_orden=OrdenTrabajo.Estado.A_REALIZAR, invernadero__agronomo_id=usuario.pk, invernadero__estado_invernadero=Invernadero.Estado.ACTIVO
        ).values_list("fecha_programada_orden", "invernadero__capataz__is_active")
    )
    invernaderos = list(Invernadero.objects.filter(agronomo_id=usuario.pk, estado_invernadero=Invernadero.Estado.ACTIVO).values_list("pk", flat=True))
    indicadores = camara.indicadores_de_camara(invernaderos, hoy)
    # COM-05a2 («Entregas sin envasado», `secCosecha`; entregas.md, «Pantallas»): las entregas «a realizar» de sus invernaderos activos sin ninguna reserva de insumo activa. Una consulta.
    sin_envasado = (
        Entrega.objects.filter(estado_orden=OrdenTrabajo.Estado.A_REALIZAR, invernadero_id__in=invernaderos)
        .exclude(pk__in=ReservaInsumo.objects.filter(estado=ReservaInsumo.Estado.ACTIVA).values("orden_id"))
        .count()
    )
    datos = {
        "sin_envasado": sin_envasado,
        "camara": {"por_vencer": indicadores["por_vencer"], "libres": indicadores["libres"], "dias_de_aviso": indicadores["dias_de_aviso"]},
        "a_realizar": len(filas),
        "hoy": sum(1 for fecha, _ in filas if fecha == hoy),
        "vencidas": sum(1 for fecha, _ in filas if fecha < hoy),
        "sin_capataz": sum(1 for _, activo in filas if not activo),
    }
    return SeccionDeInicio("comercial/cosechas/_seccion_de_inicio.html", {"cosechas": datos})


def seccion_de_entregas(usuario):
    """`registrar_seccion_de_inicio` (`secComercial` del prototipo, COM-05a2): el grupo «Entregas» del Inicio del Gerente y del Vendedor, dentro de su alcance: «Entregas de hoy» (a realizar con
    fecha ≤ hoy), «Sin transportista» (con envío) y «Próximas entregas» (las 5 primeras, con «Ver todas»). No incluye cobranza ni solicitudes (COM-08, COM-07). `None` para los demás roles.
    Dos consultas para todo el grupo."""
    from django.urls import reverse

    from comercial.servicios import entregas, solicitudes
    from core.models import Usuario, rol_de
    from core.extensiones import SeccionDeInicio
    from inventario.servicios import stock

    if not getattr(usuario, "is_active", False) or rol_de(usuario) not in (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR):
        return None
    panel = entregas.entregas_del_panel(usuario, stock.hoy())
    datos = {
        "a_realizar": panel.a_realizar,
        "de_hoy": panel.de_hoy,
        "sin_transportista": panel.sin_transportista,
        "proximas": panel.proximas,
        "url_de_la_lista": entregas.url_de_entregas(),
        "url_sin_transportista": entregas.url_de_entregas(transportista="_"),
        # COM-07a: el grupo «Solicitudes» (solo el Gerente; `None` para el Vendedor, regla 4 de COM-CNS-SRV: las resuelve el Gerente), dentro de esta misma sección.
        "solicitudes_pendientes": solicitudes.pendientes_para(usuario),
        "url_de_solicitudes_pendientes": reverse("comercial:solicitudes") + "?estado=pendiente",
    }
    return SeccionDeInicio("comercial/entregas/_seccion_de_inicio.html", {"entregas": datos})


def seccion_de_ruta(usuario):
    """`registrar_seccion_de_inicio` (COM-06a): la sección «Ruta de hoy» del Panel de control del Transportista: su situación (sin vehículo, lista o en ruta), cuántas entregas lleva y el peso, con el
    acceso a «Mi ruta». `None` para los demás roles. Hoy el Transportista no tiene ninguna otra sección ni entrada de menú (es de campo, sin menú lateral): no se duplica nada."""
    from comercial.servicios import rutas
    from core.extensiones import SeccionDeInicio
    from core.models import Usuario, rol_de

    if not getattr(usuario, "is_active", False) or rol_de(usuario) != Usuario.Rol.TRANSPORTISTA:
        return None
    datos = rutas.ruta_del_dia(usuario)
    return SeccionDeInicio(
        "comercial/rutas/_seccion_de_inicio.html",
        {"ruta": {"situacion": datos.situacion, "cantidad": datos.cantidad, "peso": datos.peso, "proxima_fecha": datos.proxima_fecha, "pendientes": datos.cantidad}},
    )
