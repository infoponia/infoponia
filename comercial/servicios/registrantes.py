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
