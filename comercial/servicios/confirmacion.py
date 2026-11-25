# Confirmación de la entrega por el cliente (COM-CNF-ENT, COM-06b; docs/casos_de_uso/comercial/confirmacion.md, «Servicios» y «Registrar la respuesta»; D-65 y D-68): el cliente abre el enlace que
# recibió con el comprobante, ve su entrega (sin las plantas perdidas ni los costos), y confirma, presenta quejas o dice que no la recibió. `datos_para_el_cliente` (paso 2), `resumen_de_respuesta`
# (paso 4, no escribe) y `registrar_respuesta` (paso 6 o 3b.4, una transacción) son lo que usan las páginas públicas (`views_cliente.py`); `reenviar_acuse` es la extensión 8a.
# Bloqueos (`FOR NO KEY UPDATE`, docs/patrones/bloqueos.md, «Confirmar una entrega»): la cuenta del Vendedor → el invernadero de origen (`bloquear_invernadero_para_alertas`: activo o no, porque crea alertas;
# D-64 punto 12) → la entrega (`OrdenTrabajo`) → el enlace (`enlaces.bloquear_enlace`, al final: patrón del enlace, sección 5). Con todo tomado se verifica de nuevo que el enlace sirva y que la entrega siga
# «concretada» y «no confirmado». Los avisos van dentro de la transacción (D-42); el acuse, con `on_commit` (D-14). Sin asientos ni cobro (D-57, COM-08).

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from comercial.models import AlertaComercial, Contrato, EnlaceCliente, Entrega, LineaDiscrepancia, Queja
from comercial.servicios import enlaces, entregas, indemnizaciones, solicitudes
from comercial.servicios.comprobantes import Destinatario
from core import correo, notificaciones
from core.models import RegistroAuditoria, Usuario, referencia
from inventario.servicios import stock
from maestros.servicios import alertas
from maestros.servicios.alertas import bloquear_invernadero_para_alertas
from produccion.models import OrdenTrabajo

logger = logging.getLogger("infoponia.confirmacion")

TIPO_QUEJA = "comercial_queja"  # EVENTO, GERENTE, ADVERTENCIA, origen SOLICITUD_REVISION (postcondición f)
TIPO_NO_RECONOCIDA = "comercial_entrega_no_reconocida"  # EVENTO, GERENTE, CRITICA, origen ENTREGA (postcondición j)
LARGO_DEL_MOTIVO = 500  # `Queja.motivo_queja` y el motivo de «no recibí»
LARGO_DE_LA_ALERTA = 200  # `Alerta.descripcion_alerta`
CONFORME, CON_QUEJAS, NO_RECIBI = "conforme", "con_quejas", "no_recibi"
RESPUESTAS = (CONFORME, CON_QUEJAS, NO_RECIBI)
Tipo = Queja.TipoDeQueja
TIPOS = tuple(Tipo.values)  # el orden en que se ofrecen y se registran: estado de la mercadería, retraso y otro
TEXTO_DEL_TIPO = dict(Tipo.choices)
TEXTO_EN_EL_AVISO = {Tipo.ESTADO_MERCADERIA: "queja por el estado de la mercadería", Tipo.RETRASO: "queja por retraso", Tipo.OTRO: "queja"}
ADVERTENCIA_DEL_ENVIO = "Después de enviarla, este enlace no podrá volver a usarse."


def _error(campo, codigo, mensaje, **params):
    """Levanta un `ValidationError` por campo con su código (y `params` si el llamador los necesita: `enlace_no_sirve` trae el motivo)."""
    raise ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params or None)]})


# ---- lo que ve el cliente (paso 2 y 2b) ----


@dataclass
class LineaDeLaEntrega:
    """Una línea como la ve el cliente: la variedad, la fecha prometida (el período), las cantidades planificada, entregada y devuelta, el precio guardado, el monto y los días de retraso. **Nunca** las
    plantas perdidas ni los costos (garantía mínima). `en_revision`: el detalle está en una discrepancia «pendiente de revisión» (2b)."""

    detalle_id: int
    variedad: str
    fecha_prometida: object
    planificada: int
    entregada: int
    devuelta: int
    precio: object
    monto: object
    dias_de_retraso: int
    en_revision: bool


@dataclass
class DatosDeEntregaParaElCliente:
    """El paso 2: el contrato y la fecha real de la entrega, las líneas, el total, lo que queda a pagar (con las indemnizaciones descontadas, PCU 16), el vencimiento del pago, hasta cuándo sirve el
    enlace y el contacto del Vendedor."""

    enlace: object
    entrega: object
    contrato: object
    fecha_real: object
    lineas: list
    total: object
    a_pagar: object
    vencimiento_del_pago: object
    vence_el_enlace: object
    contacto: object

    @property
    def hay_retraso(self):
        return any(linea.dias_de_retraso > 0 for linea in self.lineas)

    @property
    def hay_descuento(self):
        return self.a_pagar != self.total


def contacto_del_vendedor(contrato_id):
    """Los datos del Vendedor del contrato (nombre, teléfono y correo de su cuenta) para «Este enlace no se puede usar» (extensiones 2a y 6a)."""
    contrato = Contrato.objects.filter(pk=contrato_id).first()
    vendedor = Usuario.objects.filter(pk=contrato.vendedor_id).first() if contrato is not None else None
    if vendedor is None:
        return SimpleNamespace(nombre="", telefono="", email="")
    return SimpleNamespace(nombre=vendedor.get_full_name() or vendedor.email, telefono=vendedor.telefono, email=vendedor.email)


def contacto_de_la_entrega(entrega_id):
    """El contacto del Vendedor del contrato de la entrega (lo que necesita la pantalla «Este enlace no se puede usar»)."""
    contrato_id = Entrega.objects.filter(pk=entrega_id).values_list("contrato_entrega_id", flat=True).first()
    return contacto_del_vendedor(contrato_id)


def _entrega_del_enlace(enlace):
    """La entrega del enlace con su contrato, cliente y Vendedor."""
    return Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor", "invernadero").get(pk=enlace.entrega_id)


def _exigir_que_sirva(enlace, entrega, hoy):
    """Extensiones 2a y 6a: el enlace tiene que ser de confirmación y servir (vigente, dentro de la vigencia calculada), y la entrega seguir «concretada» y «no confirmado». Si no, `enlace_no_sirve` con el
    motivo (`params["motivo"]`: `no_valido`, `vencido`, `usado` o `anulado`)."""
    situacion = enlaces.NO_VALIDO if enlace.tipo != EnlaceCliente.Tipo.CONFIRMACION_ENTREGA else enlaces.situacion_del_enlace(enlace, hoy)
    if situacion == enlaces.SIRVE and (entrega.estado_orden != OrdenTrabajo.Estado.CONCRETADA or entrega.estado_confirmacion_cliente != Entrega.Confirmacion.NO_CONFIRMADO):
        situacion = enlaces.USADO if entrega.estado_confirmacion_cliente == Entrega.Confirmacion.CONFIRMADO else enlaces.ANULADO
    if situacion != enlaces.SIRVE:
        _error("__all__", "enlace_no_sirve", enlaces.texto_del_motivo(situacion, EnlaceCliente.Tipo.CONFIRMACION_ENTREGA), motivo=situacion)


def _armar(enlace, entrega, hoy):
    """Los `DatosDeEntregaParaElCliente` de `entrega`: una consulta por tabla, sin consultas por línea."""
    lineas = list(
        entrega.lineas.select_related("detalle_suministro__variedad__cultivo", "detalle_suministro__clausula_suministrante").order_by("pk")
    )
    en_revision = set(
        LineaDiscrepancia.objects.filter(detalle_entrega__entrega_id=entrega.pk, discrepancia__estado_solicitud="pendiente").values_list("detalle_entrega_id", flat=True)
    )
    filas = []
    for l in lineas:
        planificada = (l.cant_entregada or 0) + (l.cant_perdida or 0) + (l.cant_devuelta or 0)
        if planificada == 0:  # una línea quitada (D-66 punto 4): el cliente no la ve
            continue
        retraso = indemnizaciones.dias_de_retraso(entrega.fecha_resolucion_orden, l.fecha_periodo, l.detalle_suministro.clausula_suministrante.plazo_entrega_dias)  # regla «Queja por retraso» (COM-07a la sacó a `indemnizaciones`)
        filas.append(
            LineaDeLaEntrega(
                l.pk, str(l.detalle_suministro.variedad), l.fecha_periodo, planificada, l.cant_entregada or 0, l.cant_devuelta or 0, l.precio_unitario, l.monto_pagar, retraso, l.pk in en_revision
            )
        )
    contrato = entrega.contrato_entrega
    return DatosDeEntregaParaElCliente(
        enlace=enlace,
        entrega=entrega,
        contrato=contrato,
        fecha_real=entrega.fecha_resolucion_orden,
        lineas=filas,
        total=entrega.monto_total_entrega,
        a_pagar=entregas.monto_a_cobrar([entrega.pk])[entrega.pk],
        vencimiento_del_pago=entrega.fecha_vencimiento_pago,
        vence_el_enlace=enlaces.vencimiento_de(enlace),
        contacto=contacto_del_vendedor(contrato.pk),
    )


def datos_para_el_cliente(enlace, hoy=None):
    """Paso 2 y 2b. Verifica que el enlace sirva (`enlace_no_sirve` con su motivo: 2a) y arma lo que ve el cliente. Nunca las plantas perdidas ni los costos."""
    hoy = hoy or stock.hoy()
    entrega = _entrega_del_enlace(enlace)
    _exigir_que_sirva(enlace, entrega, hoy)
    return _armar(enlace, entrega, hoy)


def tipos_de_queja_disponibles(datos):
    """3a.2: `[(valor, texto)]` de los tipos que se ofrecen: «estado de la mercadería», «otro» y, solo si algún detalle llegó con retraso (días `> 0`), «retraso». En el orden de `TIPOS`."""
    return [(valor, texto) for valor, texto in Tipo.choices if valor != Tipo.RETRASO or datos.hay_retraso]


# ---- lo que responde el cliente ----


@dataclass
class QuejaPedida:
    """Una queja de la respuesta: el tipo, los ids de los `DetalleEntrega` a los que se refiere y el motivo."""

    tipo: str
    lineas: list = field(default_factory=list)
    motivo: str = ""


@dataclass
class DatosDeRespuesta:
    """La respuesta del cliente (paso 3): `conforme`, `con_quejas` (con sus `quejas`, a lo sumo una por tipo) o `no_recibi` (con su motivo). 4a (cambiar de respuesta) es de la pantalla: el servicio recibe
    solo lo último, y las quejas solo cuentan con `con_quejas`."""

    respuesta: str = ""
    quejas: list = field(default_factory=list)
    motivo_no_recibi: str = ""


def _lista(post, clave):
    """Los valores de `clave` de un `QueryDict` (`getlist`) o de un diccionario común (un valor o una lista)."""
    if hasattr(post, "getlist"):
        return post.getlist(clave)
    valor = post.get(clave)
    if valor is None:
        return []
    return list(valor) if isinstance(valor, (list, tuple)) else [valor]


def datos_de_respuesta(post):
    """Arma los `DatosDeRespuesta` de un `request.POST` (o un diccionario): `respuesta` (`conforme`, `con_quejas` o `no_recibi`), por cada tipo `queja_<tipo>` (marcado = se presenta), `lineas_<tipo>` (ids de
    línea) y `motivo_<tipo>`, y `motivo_no_recibi`. Lo que no corresponde a la respuesta se descarta (4a). No valida."""
    respuesta = (post.get("respuesta") or "").strip()
    datos = DatosDeRespuesta(respuesta=respuesta)
    if respuesta == CON_QUEJAS:
        for tipo in TIPOS:
            if post.get(f"queja_{tipo}"):
                lineas = [int(x) for x in _lista(post, f"lineas_{tipo}") if str(x).isdigit()]
                datos.quejas.append(QuejaPedida(tipo, lineas, (post.get(f"motivo_{tipo}") or "").strip()))
    elif respuesta == NO_RECIBI:
        datos.motivo_no_recibi = (post.get("motivo_no_recibi") or "").strip()
    return datos


def _validar(datos, respuesta):
    """3a.4a, 3a.4b, 3a.6a y 3b.1a, y los límites del servicio. Junta todos los errores por campo antes de levantar. Códigos: `respuesta_obligatoria` (`respuesta`), `quejas_vacias` (`__all__`),
    `tipo_no_disponible` y `queja_repetida` (`queja_<tipo>`), `queja_sin_detalles` y `linea_no_valida` (`lineas_<tipo>`), `motivo_obligatorio` y `motivo_largo` (`motivo_<tipo>` o `motivo_no_recibi`)."""
    errores = {}

    def agregar(campo, codigo, mensaje):
        errores.setdefault(campo, []).append(ValidationError(mensaje, code=codigo))

    if respuesta.respuesta not in RESPUESTAS:
        agregar("respuesta", "respuesta_obligatoria", "Indicá si recibiste la entrega.")
    elif respuesta.respuesta == CON_QUEJAS:
        if not respuesta.quejas:
            agregar("__all__", "quejas_vacias", "Agregá al menos una queja o indicá que recibiste la entrega y estás conforme.")  # 3a.6a
        disponibles = {valor for valor, _ in tipos_de_queja_disponibles(datos)}
        lineas = {l.detalle_id: l for l in datos.lineas}
        vistos = set()
        for q in respuesta.quejas:
            if q.tipo not in disponibles:
                agregar(f"queja_{q.tipo}", "tipo_no_disponible", "Este tipo de queja no está disponible para esta entrega.")
                continue
            if q.tipo in vistos:
                agregar(f"queja_{q.tipo}", "queja_repetida", "Ya agregaste una queja de este tipo.")
                continue
            vistos.add(q.tipo)
            if not q.lineas:
                agregar(f"lineas_{q.tipo}", "queja_sin_detalles", "Elegí al menos un producto.")  # 3a.4a
            elif any(i not in lineas or (q.tipo == Tipo.RETRASO and lineas[i].dias_de_retraso <= 0) for i in q.lineas):
                agregar(f"lineas_{q.tipo}", "linea_no_valida", "Elegí solo productos de esta entrega" + (" que llegaron con retraso." if q.tipo == Tipo.RETRASO else "."))
            motivo = (q.motivo or "").strip()
            if len(motivo) > LARGO_DEL_MOTIVO:
                agregar(f"motivo_{q.tipo}", "motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.")
            elif not motivo and q.tipo != Tipo.RETRASO:
                agregar(f"motivo_{q.tipo}", "motivo_obligatorio", "El motivo es obligatorio para este tipo de queja.")  # 3a.4b
    elif respuesta.respuesta == NO_RECIBI:
        motivo = (respuesta.motivo_no_recibi or "").strip()
        if len(motivo) > LARGO_DEL_MOTIVO:
            agregar("motivo_no_recibi", "motivo_largo", f"El motivo pasa de {LARGO_DEL_MOTIVO} caracteres.")
        elif not motivo:
            agregar("motivo_no_recibi", "motivo_obligatorio", "Contanos qué pasó: el motivo es obligatorio.")  # 3b.1a
    if errores:
        raise ValidationError(errores)


@dataclass
class ResumenDeRespuesta:
    """El resumen del paso 4 (o de 3b.2): qué se va a registrar y la advertencia de que el enlace no podrá volver a usarse. `quejas` trae, por cada una, `tipo`, `texto`, los `productos` y el `motivo`."""

    respuesta: str
    quejas: list
    motivo_no_recibi: str
    advertencia: str = ADVERTENCIA_DEL_ENVIO


def resumen_de_respuesta(datos, respuesta):
    """Paso 4 (y 3b.2): valida la respuesta (`_validar`) y arma el resumen. No escribe nada."""
    _validar(datos, respuesta)
    por_id = {l.detalle_id: l.variedad for l in datos.lineas}
    quejas = []
    if respuesta.respuesta == CON_QUEJAS:
        for q in sorted(respuesta.quejas, key=lambda x: TIPOS.index(x.tipo)):
            quejas.append(SimpleNamespace(tipo=q.tipo, texto=TEXTO_DEL_TIPO[q.tipo], productos=[por_id[i] for i in q.lineas], motivo=(q.motivo or "").strip()))
    return ResumenDeRespuesta(respuesta.respuesta, quejas, (respuesta.motivo_no_recibi or "").strip() if respuesta.respuesta == NO_RECIBI else "")


# ---- registrar (paso 6 o 3b.4) ----


@dataclass
class Respuesta:
    """Lo que dejó `registrar_respuesta`: el enlace usado, la entrega, la respuesta, las quejas y las alertas creadas y el resultado del acuse (`acuse_enviado`: `True`, `False` si no se pudo enviar, 7a.3, o
    `None` si todavía no salió: dentro de una transacción mayor el envío espera a su confirmación)."""

    enlace: object
    entrega: object
    respuesta: str
    quejas: list
    alertas: list
    _acuse: dict

    @property
    def acuse_enviado(self):
        return self._acuse.get("enviado")


def _contexto_del_acuse(entrega, contrato, respuesta, quejas, cuando):
    """Postcondición h y 7a: lo que dice el acuse: la entrega, la fecha y la hora de la respuesta y, según corresponda, la confirmación, el número y el tipo de cada queja o la constancia de que no la reconoció."""
    return {
        "codigo": entrega.codigo,
        "contrato": contrato.codigo,
        "cliente": contrato.cliente.nombre_visible,
        "cuando": timezone.localtime(cuando),
        "respuesta": respuesta,
        "quejas": [{"codigo": q.codigo, "tipo": TEXTO_DEL_TIPO[q.tipo_queja]} for q in quejas],
        "vendedor": contrato.vendedor,
    }


def _enviar_acuse(cliente_id, email, contexto, resultado):
    """Postcondición b: el acuse al cliente, DESPUÉS de confirmar (fuera de la transacción). Si falla o el correo del sistema no está configurado, la respuesta sigue registrada (7a): `resultado["enviado"]`
    queda `False` y la pantalla final ofrece «Reenviar acuse» (8a)."""
    if not correo.correo_configurado():
        logger.warning("No se envió el acuse de %s: el correo del sistema no está configurado.", contexto["codigo"])
        resultado["enviado"] = False
        return
    resultado["enviado"] = bool(correo.enviar_correo(Destinatario(cliente_id, email), f"Acuse de tu respuesta sobre la entrega {contexto['codigo']}", "comercial/correos/acuse_confirmacion.txt", contexto))
    if not resultado["enviado"]:
        logger.warning("No se pudo enviar el acuse de %s al cliente %s.", contexto["codigo"], cliente_id)


def _texto_de_productos(n):
    return f"{n} producto" + ("" if n == 1 else "s")


def registrar_respuesta(enlace_id, respuesta, hoy=None):
    """COM-CNF-ENT, paso 6 (conforme o con quejas) y 3b.4 (no recibí): registra la respuesta del cliente en UNA transacción y devuelve la `Respuesta`.

    - `respuesta` son los `DatosDeRespuesta`. Errores (`ValidationError` con `error_dict`): los de `_validar` y `enlace_no_sirve` (2a y 6a, con `params["motivo"]`: `no_valido`, `vencido`, `usado` o `anulado`).
    - Bloqueos: la cuenta del Vendedor → el invernadero de origen → la entrega → el enlace; con todo tomado vuelve a verificar que el enlace sirva y que la entrega siga «concretada» y «no confirmado».
    - **Conforme o con quejas:** la entrega pasa a «confirmado» (confirmar es reconocer que se recibió, aunque haya quejas; no toca el estado de la orden, los montos, el cobro, el stock ni los incumplimientos).
      Por cada queja: una `Queja` «pendiente» (`solicitudes.crear_solicitud`), su alerta `comercial_queja` para el Gerente con su `AlertaComercial(solicitud=…)` y el aviso al Vendedor.
    - **No recibí:** la entrega sigue «no confirmado»; la alerta crítica `comercial_entrega_no_reconocida` con el motivo y el aviso al Vendedor. Ninguna queja.
    - El enlace queda `usado`. Un registro de auditoría `respuesta_cliente_entrega` sin cuenta (`rol_externo="cliente_enlace"`). El acuse sale con `on_commit`."""
    enlace_previo = EnlaceCliente.objects.filter(pk=enlace_id).first()
    if enlace_previo is None or enlace_previo.tipo != EnlaceCliente.Tipo.CONFIRMACION_ENTREGA:
        _error("__all__", "enlace_no_sirve", enlaces.texto_del_motivo(enlaces.NO_VALIDO, EnlaceCliente.Tipo.CONFIRMACION_ENTREGA), motivo=enlaces.NO_VALIDO)
    previa = _entrega_del_enlace(enlace_previo)
    resultado_del_acuse = {}
    with transaction.atomic():
        list(Usuario.objects.select_for_update(no_key=True).filter(pk=previa.contrato_entrega.vendedor_id))
        bloquear_invernadero_para_alertas(previa.invernadero_id)
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=previa.pk))
        enlace = enlaces.bloquear_enlace(enlace_id)
        entrega = _entrega_del_enlace(enlace)
        hoy = hoy or stock.hoy()
        _exigir_que_sirva(enlace, entrega, hoy)
        datos = _armar(enlace, entrega, hoy)
        _validar(datos, respuesta)
        contrato = entrega.contrato_entrega
        cliente = contrato.cliente
        vendedor = entregas._usuario_activo(contrato.vendedor_id)
        quejas, alertas_creadas, cambios = [], [], {}

        if respuesta.respuesta in (CONFORME, CON_QUEJAS):  # postcondición d
            Entrega.objects.filter(pk=entrega.pk).update(estado_confirmacion_cliente=Entrega.Confirmacion.CONFIRMADO)
            cambios["estado_confirmacion_cliente"] = {"antes": Entrega.Confirmacion.NO_CONFIRMADO.value, "despues": Entrega.Confirmacion.CONFIRMADO.value}
        if respuesta.respuesta == CON_QUEJAS:
            for pedida in sorted(respuesta.quejas, key=lambda x: TIPOS.index(x.tipo)):  # postcondiciones e a g
                queja = solicitudes.crear_solicitud(Queja, entrega, tipo_queja=pedida.tipo, motivo_queja=(pedida.motivo or "").strip(), cliente=cliente)
                queja.detalles.set(pedida.lineas)
                quejas.append(queja)
                descripcion = f"{entrega.codigo} · {queja.codigo} · {TEXTO_DEL_TIPO[pedida.tipo]} · {_texto_de_productos(len(pedida.lineas))}"
                alerta = alertas.crear_alerta_de_evento(entrega.invernadero_id, TIPO_QUEJA, entregas._acotar(descripcion, LARGO_DE_LA_ALERTA))
                if alerta is not None:  # con el invernadero inactivo no se crea (como la discrepancia de COM-06a)
                    AlertaComercial.objects.create(alerta=alerta, solicitud=queja)
                    alertas_creadas.append(alerta)
                if vendedor is not None:
                    notificaciones.notificar(
                        vendedor,
                        entregas._acotar(f"Queja de un cliente en {entrega.codigo}", entregas.LARGO_DEL_TITULO),
                        entregas._acotar(f"{entrega.codigo} · {queja.codigo}: {TEXTO_EN_EL_AVISO[pedida.tipo]} del cliente {cliente.nombre_visible}.", entregas.LARGO_DEL_DETALLE),
                    )
        elif respuesta.respuesta == NO_RECIBI:  # postcondiciones i a k
            motivo = (respuesta.motivo_no_recibi or "").strip()
            descripcion = f"{entrega.codigo} · el cliente dice que no la recibió: “{motivo}”"
            alerta = alertas.crear_alerta_de_evento(entrega.invernadero_id, TIPO_NO_RECONOCIDA, entregas._acotar(descripcion, LARGO_DE_LA_ALERTA))
            if alerta is not None:
                AlertaComercial.objects.create(alerta=alerta, entrega=entrega)
                alertas_creadas.append(alerta)
            if vendedor is not None:
                notificaciones.notificar(
                    vendedor,
                    entregas._acotar(f"El cliente no reconoce {entrega.codigo}", entregas.LARGO_DEL_TITULO),
                    entregas._acotar(f"{entrega.codigo}: el cliente {cliente.nombre_visible} dice que no recibió la entrega: “{motivo}”.", entregas.LARGO_DEL_DETALLE),
                )

        ahora = timezone.now()
        EnlaceCliente.objects.filter(pk=enlace.pk).update(estado=EnlaceCliente.Estado.USADO, fecha_uso=ahora)  # postcondición a
        enlace.estado, enlace.fecha_uso = EnlaceCliente.Estado.USADO, ahora

        datos_de_auditoria = {"entrega": referencia(entrega), "cliente": referencia(cliente), "respuesta_cliente": respuesta.respuesta, "enlace": str(enlace)}
        if quejas:
            datos_de_auditoria["quejas_creadas"] = [str(q) for q in quejas]
        if alertas_creadas:
            datos_de_auditoria["alertas_creadas"] = [str(a) for a in alertas_creadas]
        if respuesta.respuesta == NO_RECIBI:
            datos_de_auditoria["motivo_no_reconocida"] = (respuesta.motivo_no_recibi or "").strip()
        detalle = {"datos": datos_de_auditoria}
        if cambios:
            detalle["cambios"] = cambios
        afectados = [entrega, cliente, enlace, *quejas]
        RegistroAuditoria.objects.registrar(usuario=None, accion=RegistroAuditoria.Accion.RESPUESTA_CLIENTE_ENTREGA, afectados=afectados, detalle=detalle, rol_externo="cliente_enlace")

        if cliente.email_cliente:  # postcondiciones b y h: después de confirmar
            contexto = _contexto_del_acuse(entrega, contrato, respuesta.respuesta, quejas, ahora)
            transaction.on_commit(partial(_enviar_acuse, cliente.pk, cliente.email_cliente, contexto, resultado_del_acuse))
        entrega.refresh_from_db()
    return Respuesta(enlace, entrega, respuesta.respuesta, quejas, alertas_creadas, resultado_del_acuse)


def reenviar_acuse(enlace_id):
    """Extensión 8a: reenvía el acuse al correo registrado del cliente (nunca a otro: el correo no se puede cambiar desde el enlace) y devuelve si salió. Solo con el enlace ya usado (la sesión de la pantalla
    final lo controla). Rearma lo que dijo el acuse desde la base: las quejas de la entrega, la confirmación o la constancia de que no la reconoció. Corre fuera de toda transacción."""
    enlace = EnlaceCliente.objects.select_related("cliente").filter(pk=enlace_id, tipo=EnlaceCliente.Tipo.CONFIRMACION_ENTREGA).first()
    if enlace is None or enlace.estado != EnlaceCliente.Estado.USADO:
        _error("__all__", "acuse_no_disponible", "Todavía no hay una respuesta registrada con este enlace.")
    entrega = _entrega_del_enlace(enlace)
    quejas = list(Queja.objects.filter(entrega_id=entrega.pk).order_by("numero"))
    if quejas:
        respuesta = CON_QUEJAS
    else:
        respuesta = CONFORME if entrega.estado_confirmacion_cliente == Entrega.Confirmacion.CONFIRMADO else NO_RECIBI
    contexto = _contexto_del_acuse(entrega, entrega.contrato_entrega, respuesta, quejas, enlace.fecha_uso)
    resultado = {}
    if enlace.cliente.email_cliente:
        _enviar_acuse(enlace.cliente.pk, enlace.cliente.email_cliente, contexto, resultado)
    return bool(resultado.get("enviado"))
