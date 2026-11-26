# Atender una entrega no reconocida (COM-ATN-ENR, COM-06b; docs/casos_de_uso/comercial/confirmacion.md, «Atender una entrega no reconocida»; D-68 punto 9, MD-137): el Gerente abre la alerta crítica que
# crea la respuesta «no recibí» del cliente, ve todo lo que generó la entrega (regla 1) y registra qué averiguó (regla 2). Sin reversión automática (regla 3): no anula la concreción, no toca asientos,
# stock ni incumplimientos; la corrección contable es manual. Los asientos de la regla 1 y el cobro (regla 5) son de la ronda de contabilidad y de COM-08 (D-57).
# Bloqueos (`FOR NO KEY UPDATE`, docs/patrones/bloqueos.md, «Confirmar una entrega»): las cuentas (el Gerente, el Vendedor y el responsable contable, en orden de id) → el invernadero de origen
# (`bloquear_invernadero_para_alertas`) → la entrega (`OrdenTrabajo`) → la `AlertaComercial`. Va en el mismo orden que `confirmacion.registrar_respuesta`: no se cruzan.

from dataclasses import dataclass
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.urls import reverse

from comercial.models import AlertaComercial, Entrega, LineaPago, Vehiculo
from comercial.servicios import asientos_comerciales, concrecion, entregas
from comercial.servicios.compra_ventas import texto_de_pesos
from comercial.servicios.confirmacion import TIPO_NO_RECONOCIDA
from contabilidad.servicios import responsables
from contabilidad.servicios.responsables import responsable_contable
from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.servicios import alertas
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import Consumo, Merma, OrdenTrabajo

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
LARGO_DE_LA_DESCRIPCION = 500
GERENTE = Usuario.Rol.GERENTE
Resultado = AlertaComercial.Resultado
SIN_COBRO = "Sin cobro registrado"
TEXTO_DEL_RESULTADO_EN_EL_AVISO = {
    Resultado.NO_LLEGO_PERDIDO: "no llegó al cliente (producto perdido)",
    Resultado.NO_LLEGO_DEVUELTO: "no llegó al cliente (producto devuelto)",
}


def _error(campo, codigo, mensaje):
    raise ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _exigir_gerente(actor):
    """El Gerente con la cuenta activa, leída de la base (una cuenta que se dio de baja después de cargarse no atiende). Cualquier otro rol: `PermissionDenied` (403)."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None and getattr(actor, "pk", None) else None
    if vigente is None or not vigente.is_active or rol_de(vigente) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def _vinculo_de(alerta_id):
    """La `AlertaComercial` de una alerta «entrega no reconocida» (con su alerta y su entrega), o `Http404` si no existe o es de otro tipo."""
    vinculo = AlertaComercial.objects.select_related("alerta").filter(alerta_id=alerta_id, entrega__isnull=False, alerta__tipo_alerta=TIPO_NO_RECONOCIDA).first()
    if vinculo is None:
        raise Http404("No existe esa alerta de entrega no reconocida.")
    return vinculo


def alerta_activa_de(entrega_id):
    """El id de la alerta «entrega no reconocida» **activa** de la entrega, o `None`. Para el enlace «Atender» de la ficha del suministro."""
    return (
        AlertaComercial.objects.filter(entrega_id=entrega_id, alerta__tipo_alerta=TIPO_NO_RECONOCIDA, alerta__estado_alerta=Alerta.Estado.ACTIVA)
        .order_by("-pk")
        .values_list("alerta_id", flat=True)
        .first()
    )


@dataclass
class FichaDeNoReconocida:
    """Regla 1 de COM-ATN-ENR: todo lo que generó la entrega. `lineas` (variedad, planificada, entregada, perdida y devuelta), el transportista y su vehículo, cuándo se concretó, los intentos fallidos, la
    confirmación del cliente con su motivo, los consumos de envases, el cobro y los asientos (fuera de la ronda)."""

    alerta: object
    entrega: object
    contrato: object
    cliente: object
    vendedor: object
    lineas: list
    transportista: object
    vehiculo: object
    concretada_en: object
    intentos: list
    confirmacion: str
    motivo_del_cliente: str
    consumos: list
    cobro: str
    asientos: list  # regla 1 (CON-04d): los asientos de la entrega, de sus mermas y consumos y del cobro vigente: `SimpleNamespace(titulo, numero, fecha, filas)`, texto sin enlace
    resultados: list


def _registro_de(accion, entrega_id):
    """El registro de auditoría más reciente de `accion` que afectó a la entrega, o `None`."""
    return (
        RegistroAuditoria.objects.filter(accion=accion, afectados__contains=[{"modelo": "comercial.entrega", "id": entrega_id}]).order_by("-fecha_hora", "-pk").first()
    )


def ficha_de_no_reconocida(actor, alerta_id):
    """Paso 1 de COM-ATN-ENR (regla 1): lo que ve el Gerente. Solo el Gerente activo (`PermissionDenied`); `Http404` si no existe una alerta de ese tipo; `alerta_resuelta` (en `__all__`) si ya no está activa."""
    _exigir_gerente(actor)
    vinculo = _vinculo_de(alerta_id)
    if vinculo.alerta.estado_alerta != Alerta.Estado.ACTIVA:
        _error("__all__", "alerta_resuelta", "Esta alerta ya fue resuelta.")
    entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor", "transportista", "invernadero").get(pk=vinculo.entrega_id)
    lineas = [
        SimpleNamespace(
            variedad=str(l.detalle_suministro.variedad), planificada=(l.cant_entregada or 0) + (l.cant_perdida or 0) + (l.cant_devuelta or 0), entregada=l.cant_entregada, perdida=l.cant_perdida, devuelta=l.cant_devuelta
        )
        for l in entrega.lineas.select_related("detalle_suministro__variedad__cultivo").order_by("pk")
    ]
    concreto = _registro_de(RegistroAuditoria.Accion.CONCRECION_ENTREGA, entrega.pk)
    respuesta = _registro_de(RegistroAuditoria.Accion.RESPUESTA_CLIENTE_ENTREGA, entrega.pk)
    motivo = ((respuesta.detalle or {}).get("datos", {}).get("motivo_no_reconocida", "") if respuesta is not None else "") or vinculo.alerta.descripcion_alerta
    consumos = [
        f"{c.insumo_invernadero.insumo.nombre_insumo}: {c.cant_consumo.normalize():f}".replace(".", ",")
        for c in Consumo.objects.filter(orden_id=entrega.pk).select_related("insumo_invernadero__insumo").order_by("pk")
    ]
    return FichaDeNoReconocida(
        alerta=vinculo.alerta,
        entrega=entrega,
        contrato=entrega.contrato_entrega,
        cliente=entrega.contrato_entrega.cliente,
        vendedor=entrega.contrato_entrega.vendedor,
        lineas=lineas,
        transportista=entrega.transportista,
        vehiculo=Vehiculo.objects.filter(transportista_id=entrega.transportista_id).first() if entrega.transportista_id else None,
        concretada_en=concreto.fecha_hora if concreto is not None else None,
        intentos=concrecion.intentos_fallidos([entrega.pk])[entrega.pk],
        confirmacion=entrega.get_estado_confirmacion_cliente_display() or "",
        motivo_del_cliente=motivo,
        consumos=consumos,
        cobro=_texto_del_cobro(entrega),
        asientos=_asientos_de_la_entrega(entrega),
        resultados=list(Resultado.choices),
    )


def _asientos_de_la_entrega(entrega):
    """Regla 1 de COM-ATN-ENR: todo lo asentado por la entrega, para que el Gerente vea qué corregir: el asiento de la venta y del costo (origen: la entrega), el de cada merma «daño en la entrega» y el de cada consumo de envase, y
    el del cobro vigente, si lo hay. Lista vacía si nada se asentó (anterior a CON-04c). Solo lectura."""
    origenes = [("Venta y costo de la entrega", entrega.pk)]
    origenes += [("Merma de la entrega", m.pk) for m in Merma.objects.filter(orden_id=entrega.pk).order_by("pk")]
    origenes += [("Consumo de envases", c.pk) for c in Consumo.objects.filter(orden_id=entrega.pk).order_by("pk")]
    linea = LineaPago.objects.filter(entrega_id=entrega.pk, vigente=True).first()
    if linea is not None:
        origenes.append(("Cobro de la entrega", linea.pago_id))
    asientos = []
    for titulo, origen_id in origenes:
        a = asientos_comerciales.asiento_de(origen_id)
        if a is not None:
            a.titulo = titulo
            asientos.append(a)
    return asientos


def _tiene_cobro_vigente(entrega):
    """Regla 5: si la entrega ya se cobró (tiene una `LineaPago` vigente, COM-08a), hay que anular primero el cobro (COM-ANL-CBR). Un cobro anulado no cuenta."""
    return LineaPago.objects.filter(entrega_id=entrega.pk, vigente=True).exists()


def _texto_del_cobro(entrega):
    """Regla 1: «COB-0032 · 25/11/2026 · Transferencia · $ 47.200,00» (el código, la fecha, el medio y el monto del cobro vigente) o «Sin cobro registrado»."""
    linea = LineaPago.objects.select_related("pago").filter(entrega_id=entrega.pk, vigente=True).first()
    if linea is None:
        return SIN_COBRO
    pago = linea.pago
    return f"{pago.codigo} · {pago.fecha_pago:%d/%m/%Y} · {pago.get_medio_pago_display()} · {texto_de_pesos(pago.monto_pagado)}"


def atender_entrega_no_reconocida(actor, alerta_id, resultado, descripcion):
    """COM-ATN-ENR, postcondiciones a a c: carga el `resultado` de la averiguación (`llego`, `no_llego_perdido` o `no_llego_devuelto`, regla 2) y la `descripcion` obligatoria (de 1 a 500, sin espacios al borde),
    y resuelve la alerta. Devuelve la `Alerta` resuelta. Solo el Gerente activo (`PermissionDenied`); `Http404` si la alerta no es de este tipo.

    Errores (`ValidationError`, por campo): `resultado_obligatorio` y `resultado_invalido` (`resultado`), `descripcion_obligatoria` y `descripcion_larga` (`descripcion`), `alerta_resuelta` y `entrega_cobrada`
    (regla 5: «Primero anulá el cobro.», solo con «no llegó») en `__all__`. Con «no llegó», un aviso SOLO al responsable contable (el Contador o, sin Contador, el Gerente), sin el Gerente que atiende (H21):
    corresponde corregir los asientos a mano. El Vendedor ya no lo recibe (CON-04d). No toca la entrega, el stock, los asientos ni los incumplimientos (regla 3). Una transacción, con los bloqueos del encabezado y un registro `atencion_entrega_no_reconocida`."""
    _exigir_gerente(actor)
    descripcion = (descripcion or "").strip()
    resultado = (resultado or "").strip()
    if not resultado:
        _error("resultado", "resultado_obligatorio", "Elegí el resultado de la averiguación.")
    if resultado not in Resultado.values:
        _error("resultado", "resultado_invalido", "Elegí uno de los resultados de la lista.")
    if not descripcion:
        _error("descripcion", "descripcion_obligatoria", "Contá qué averiguaste: la descripción es obligatoria.")
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        _error("descripcion", "descripcion_larga", f"La descripción pasa de {LARGO_DE_LA_DESCRIPCION} caracteres.")
    previo = _vinculo_de(alerta_id)
    entrega_previa = Entrega.objects.select_related("contrato_entrega").get(pk=previo.entrega_id)
    responsable = responsable_contable()
    with transaction.atomic():
        cuentas = {actor.pk} | ({responsable.pk} if responsable is not None else set())  # el Vendedor ya no recibe el aviso: no se bloquea
        list(Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk"))
        quien = _exigir_gerente(actor)  # después de bloquear: una baja de la cuenta que esperaba, ya está
        bloquear_invernadero_para_alertas(entrega_previa.invernadero_id)
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=entrega_previa.pk))
        vinculo = AlertaComercial.objects.select_for_update(no_key=True, of=("self",)).select_related("alerta").get(pk=previo.pk)
        alerta = Alerta.objects.get(pk=vinculo.alerta_id)
        if alerta.estado_alerta != Alerta.Estado.ACTIVA or vinculo.resultado_averiguacion is not None:
            _error("__all__", "alerta_resuelta", "Esta alerta ya fue resuelta.")
        entrega = Entrega.objects.select_related("contrato_entrega__cliente").get(pk=entrega_previa.pk)
        if resultado != Resultado.LLEGO and _tiene_cobro_vigente(entrega):
            _error("__all__", "entrega_cobrada", "Primero anulá el cobro.")  # regla 5
        AlertaComercial.objects.filter(pk=vinculo.pk).update(resultado_averiguacion=resultado, descripcion_averiguacion=descripcion)
        resuelta = alertas.resolver_alerta(alerta.pk)  # la API de maestros (D-41); `None` si ya estaba resuelta (no puede: se verificó arriba)
        if resultado != Resultado.LLEGO:  # postcondición b
            # CON-04d (D-85 punto 8, D-92 punto 11): el aviso va SOLO al responsable contable (el Contador activo o, sin Contador, el Gerente), nunca al Vendedor, que dejó de registrar asientos. Sin Contador el
            # responsable es el Gerente que atiende y no se le avisa a quien actúa (H21, D-85 punto 7): no queda aviso. Decisión del estudiante del 26/11/2026.
            responsables.notificar_al_responsable_contable(
                entregas._acotar(f"Corregir los asientos de {entrega.codigo}", entregas.LARGO_DEL_TITULO),
                entregas._acotar(f"{entrega.codigo} {TEXTO_DEL_RESULTADO_EN_EL_AVISO[resultado]}: corresponde corregir los asientos a mano.", entregas.LARGO_DEL_DETALLE),
                excluir=quien,
            )
        RegistroAuditoria.objects.registrar(  # postcondición c
            usuario=quien,
            accion=RegistroAuditoria.Accion.ATENCION_ENTREGA_NO_RECONOCIDA,
            afectados=[alerta, entrega],
            detalle={
                "datos": {
                    "alerta": referencia(alerta),
                    "entrega": referencia(entrega),
                    "resultado_averiguacion": resultado,
                    "descripcion_averiguacion": descripcion,
                    "alertas_resueltas": [str(alerta)],
                }
            },
        )
        return resuelta or Alerta.objects.get(pk=alerta.pk)


def enlaces_de_alertas(usuario, alertas_no_reconocidas):
    """`registrar_enlace_de_alerta` para `comercial_entrega_no_reconocida` (D-62): solo el Gerente la recibe; lleva a la pantalla de COM-ATN-ENR de su entrega. Una consulta para toda la lista."""
    alertas_no_reconocidas = list(alertas_no_reconocidas)
    if not alertas_no_reconocidas or rol_de(usuario) != GERENTE:
        return {}
    enlaces = {}
    vinculos = AlertaComercial.objects.filter(alerta_id__in=[a.pk for a in alertas_no_reconocidas], entrega__isnull=False).select_related("entrega__contrato_entrega__cliente")
    for vinculo in vinculos:
        e = vinculo.entrega
        enlaces[vinculo.alerta_id] = Enlace(reverse("comercial:entrega_no_reconocida", args=[e.pk]), f"{e.codigo} · {e.contrato_entrega.cliente.nombre_visible}")
    return enlaces
