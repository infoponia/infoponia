# Rutas de `comercial` (COM-06a): COM-INI-RUT (iniciar la ruta del día), COM-FIN-RUT (finalizarla) y el intento fallido (extensión 4a de COM-CNC-ENT y regla 1 de COM-FIN-RUT, una sola
# función para los dos casos de uso). El Transportista inicia la ruta con todas sus entregas del día, concreta o registra un intento fallido de cada una y finaliza.
# Fuente: docs/casos_de_uso/comercial/rutas.md («Cómo se aplica en la ronda «Comercial 1»»), D-66 punto 11 y D-68 punto 6; bloqueos en `docs/patrones/bloqueos.md`
# («Iniciar y finalizar la ruta, y el intento fallido»).
#
# Bloqueos (`FOR NO KEY UPDATE`): la cuenta del Transportista (y, en el intento fallido, la del Vendedor) → el INVERNADERO de su `TransportistaInvernadero` (es el semáforo de
# las planificaciones, asignaciones, envasados y cancelaciones de sus entregas: se toma ANTES de cambiar el vehículo) → el vehículo → las entregas de la ruta, releídas. Después
# de bloquear se vuelve a verificar todo. Los avisos van dentro de la transacción (D-42) y el correo al cliente, después de confirmar (D-14).

import json
from collections import defaultdict, namedtuple
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404

from comercial.models import DetalleEntrega, Entrega, IntentoFallido, Vehiculo
from comercial.servicios import entregas
from core.models import RegistroAuditoria, Transportista, Usuario, referencia, rol_de
from inventario.servicios import stock
from maestros.models import TransportistaInvernadero
from maestros.servicios.invernaderos import bloquear_invernadero_activo
from produccion.models import OrdenTrabajo, ReservaInsumo

MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
LARGO_DE_LA_DESCRIPCION = 300
A_REALIZAR = OrdenTrabajo.Estado.A_REALIZAR
ENVIO = Entrega.Modalidad.ENVIO

# `situacion` es una de «sin_vehiculo» (1a), «en_ruta» (1b), «ruta_vencida» (1c; `fecha_ruta_vencida` es la de esa ruta) o «lista». `entregas` son las de la ruta (con envío, «a realizar»,
# asignadas al Transportista y con fecha programada de hoy o anterior), las demoradas primero; `proximas`, las de fecha futura (informativo). `huella` es lo que se confirma (5c).
FilaDeRuta = namedtuple("FilaDeRuta", "entrega codigo cliente destino localidad fecha dias_de_retraso contenido con_envasado peso")
RutaDelDia = namedtuple(
    "RutaDelDia", "vehiculo situacion fecha_ruta_vencida entregas proximas cantidad localidades peso capacidad proxima_fecha huella"
)


def _rechazar(codigo, mensaje, campo="__all__", params=None):
    """Un `ValidationError` con código estable (y datos de apoyo en `params`), como el resto de `comercial`."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo, params=params)]})


def _exigir_transportista(actor):
    """Precondiciones a y b: el Transportista está autenticado y activo. Lee la cuenta de la base (el objeto del pedido pudo quedar viejo). Devuelve la cuenta vigente."""
    vigente = Usuario.objects.filter(pk=actor.pk).first() if actor is not None else None
    if vigente is None or not vigente.is_active or rol_de(vigente) != Usuario.Rol.TRANSPORTISTA:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return vigente


def _de_la_ruta(transportista_id, hoy):
    """Las entregas de la ruta: con envío, «a realizar», asignadas al Transportista y con fecha programada de hoy o anterior (regla «Entregas de la ruta»)."""
    return Entrega.objects.filter(transportista_id=transportista_id, modalidad_entrega=ENVIO, estado_orden=A_REALIZAR, fecha_programada_orden__lte=hoy)


def _con_destino(consulta):
    return consulta.select_related(
        "contrato_entrega__cliente", "invernadero", "direccion_destino__localidad", "direccion_destino__direccionurbana", "direccion_destino__direccionrural"
    )


def huella_de_la_ruta(lista):
    """Ids y fechas programadas, ordenados: lo que el Transportista vio al iniciar (5c)."""
    return json.dumps(sorted([e.pk, f"{e.fecha_programada_orden:%Y-%m-%d}"] for e in lista))


def _contenidos(entrega_ids):
    """``{id de entrega: "100 Lechuga Crespa, 40 Rúcula"}`` con lo planificado de cada línea (las quitadas no figuran). Dos consultas."""
    lineas = list(DetalleEntrega.objects.filter(entrega_id__in=list(entrega_ids)).select_related("detalle_venta__variedad__cultivo", "detalle_suministro__variedad__cultivo").order_by("pk"))
    planificadas = entregas.cantidades_planificadas([linea.pk for linea in lineas])
    partes = defaultdict(list)
    for linea in lineas:
        if planificadas[linea.pk] > 0:
            partes[linea.entrega_id].append(f"{planificadas[linea.pk]} {(linea.detalle_venta or linea.detalle_suministro).variedad}")
    return {i: ", ".join(partes[i]) for i in entrega_ids}


def _filas(lista, hoy):
    """Las `FilaDeRuta` de `lista`, sin consultas por entrega (una por tabla)."""
    lista = list(lista)
    ids = [e.pk for e in lista]
    pesos = entregas.peso_de_entregas(ids)
    contenidos = _contenidos(ids)
    con_envasado = set(ReservaInsumo.objects.filter(orden_id__in=ids, estado=ReservaInsumo.Estado.ACTIVA).values_list("orden_id", flat=True))
    filas = []
    for e in lista:
        filas.append(
            FilaDeRuta(
                entrega=e,
                codigo=e.codigo,
                cliente=e.contrato_entrega.cliente.nombre_visible,
                destino=entregas._destino_de_la_fila(e),
                localidad=e.direccion_destino.localidad.nombre_localidad if e.direccion_destino_id else "",
                fecha=e.fecha_programada_orden,
                dias_de_retraso=max(0, (hoy - e.fecha_programada_orden).days),
                contenido=contenidos[e.pk],
                con_envasado=e.pk in con_envasado,
                peso=pesos[e.pk],
            )
        )
    return filas


def _orden_de_presentacion(fila):
    """Regla «Orden de presentación»: primero las demoradas (las más atrasadas antes) y después las demás, agrupadas por localidad de destino."""
    return (0 if fila.dias_de_retraso > 0 else 1, -fila.dias_de_retraso, fila.localidad.lower(), fila.fecha, fila.entrega.pk)


def ruta_del_dia(actor, hoy=None):
    """COM-INI-RUT, pasos 1 a 3 (y extensiones 1a, 1b, 1c, 2a, 2b y 2c). Solo lectura: no bloquea ni audita. Devuelve la `RutaDelDia` del Transportista: el vehículo, la situación, las
    entregas de la ruta (las demoradas primero, con sus días de retraso, y si tienen envasado), la cantidad, las localidades distintas, el peso y la capacidad, las próximas, la
    próxima fecha si no hay entregas (2a) y la huella. Una consulta por tabla. `PermissionDenied` si no es un Transportista activo."""
    hoy = hoy or stock.hoy()
    actor = _exigir_transportista(actor)
    vehiculo = Vehiculo.objects.filter(transportista_id=actor.pk, estado_vehiculo=Vehiculo.Estado.ACTIVO).first()
    if vehiculo is None:
        situacion, vencida = "sin_vehiculo", None
    elif vehiculo.esta_en_ruta(hoy):
        situacion, vencida = "en_ruta", None
    elif vehiculo.en_ruta:
        situacion, vencida = "ruta_vencida", vehiculo.fecha_inicio_ruta
    else:
        situacion, vencida = "lista", None
    de_la_ruta = list(_con_destino(_de_la_ruta(actor.pk, hoy)))
    filas = sorted(_filas(de_la_ruta, hoy), key=_orden_de_presentacion)
    futuras = list(
        _con_destino(
            Entrega.objects.filter(transportista_id=actor.pk, modalidad_entrega=ENVIO, estado_orden=A_REALIZAR, fecha_programada_orden__gt=hoy)
        ).order_by("fecha_programada_orden", "pk")
    )
    proximas = _filas(futuras, hoy)
    proxima_fecha = futuras[0].fecha_programada_orden if futuras and not filas else None
    return RutaDelDia(
        vehiculo,
        situacion,
        vencida,
        filas,
        proximas,
        len(filas),
        len({f.localidad for f in filas if f.localidad}),
        sum((f.peso for f in filas), Decimal("0.00")),
        vehiculo.capacidad_carga if vehiculo is not None else None,
        proxima_fecha,
        huella_de_la_ruta(de_la_ruta),
    )


def iniciar_ruta(actor, huella):
    """COM-INI-RUT, paso 5, en UNA transacción con los bloqueos del encabezado. Después de bloquear vuelve a verificar: `vehiculo_inactivo` (5b: el vehículo ya no es del Transportista
    o dejó de estar activo) o `sin_vehiculo` (1a), `ruta_ya_iniciada` (5a), `sin_entregas_de_ruta` (5d) y `ruta_cambio` (5c, con `params` `agregadas` y `quitadas`: las entregas que
    se sumaron y las que se quitaron desde que se presentó la lista; la pantalla vuelve al paso 2). Efecto: `en_ruta = True` y `fecha_inicio_ruta = hoy` (1c reemplaza una fecha
    vieja); no toca ninguna entrega ni reserva. Auditoría `inicio_ruta`. Devuelve el `Vehiculo`. `PermissionDenied` si no es un Transportista activo."""
    previa = _exigir_transportista(actor)
    tenia_vehiculo = Vehiculo.objects.filter(transportista_id=previa.pk).exists()
    asignacion = TransportistaInvernadero.objects.filter(transportista_id=previa.pk).first()
    with transaction.atomic():
        quien = Usuario.objects.select_for_update(no_key=True).get(pk=previa.pk)
        if not quien.is_active or rol_de(quien) != Usuario.Rol.TRANSPORTISTA:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        if asignacion is not None:
            bloquear_invernadero_activo(asignacion.invernadero_id)  # el semáforo de las entregas del Transportista (D-66, punto 11)
        vehiculo = Vehiculo.objects.select_for_update(no_key=True).filter(transportista_id=quien.pk).first()
        hoy = stock.hoy()
        if vehiculo is None or not vehiculo.activo:
            if tenia_vehiculo:
                raise _rechazar("vehiculo_inactivo", "Tu vehículo ya no está activo o ya no es tuyo. Comunicate con el Gerente.")  # 5b
            raise _rechazar("sin_vehiculo", "No tenés un vehículo activo para iniciar la ruta. Comunicate con el Gerente, que asigna los vehículos.")  # 1a
        if vehiculo.esta_en_ruta(hoy):
            raise _rechazar("ruta_ya_iniciada", "La ruta de hoy ya estaba iniciada.")  # 5a
        if asignacion is not None:
            list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=_de_la_ruta(quien.pk, hoy).values("pk")).order_by("pk"))
        actuales = list(_de_la_ruta(quien.pk, hoy).order_by("pk")) if asignacion is not None else []
        if not actuales:
            raise _rechazar("sin_entregas_de_ruta", "Ya no tenés entregas para iniciar la ruta.")  # 2a y 5d
        if huella_de_la_ruta(actuales) != huella:
            vistas = _ids_de_la_huella(huella)
            ahora = {e.pk: e for e in actuales}
            agregadas = [ahora[i].codigo for i in sorted(set(ahora) - vistas)]
            quitadas = [OrdenTrabajo.objects.get(pk=i).codigo for i in sorted(vistas - set(ahora)) if OrdenTrabajo.objects.filter(pk=i).exists()]
            raise _rechazar(
                "ruta_cambio", "Las entregas de tu ruta cambiaron mientras la mirabas. Revisalas y confirmá de nuevo.", params={"agregadas": agregadas, "quitadas": quitadas}
            )  # 5c
        antes_en_ruta, antes_fecha = vehiculo.en_ruta, vehiculo.fecha_inicio_ruta
        Vehiculo.objects.filter(pk=vehiculo.pk).update(en_ruta=True, fecha_inicio_ruta=hoy)
        vehiculo.refresh_from_db()
        cambios = {}
        if not antes_en_ruta:
            cambios["en_ruta"] = {"antes": False, "despues": True}
        if antes_fecha != hoy:
            cambios["fecha_inicio_ruta"] = {"antes": f"{antes_fecha:%d/%m/%Y}" if antes_fecha else None, "despues": f"{hoy:%d/%m/%Y}"}
        RegistroAuditoria.objects.registrar(
            usuario=quien,
            accion=RegistroAuditoria.Accion.INICIO_RUTA,
            afectados=[vehiculo],
            detalle={"cambios": cambios, "datos": {"entregas_de_la_ruta": [e.codigo for e in actuales]}},
        )
        return vehiculo


def _ids_de_la_huella(huella):
    """Los ids de entrega de una huella (vacío si no se puede leer)."""
    try:
        return {int(fila[0]) for fila in json.loads(huella)}
    except (TypeError, ValueError, IndexError, KeyError):
        return set()


def pendientes_de_la_ruta(actor, hoy=None):
    """Las `FilaDeRuta` de las entregas «a realizar» de la ruta del Transportista (lo que impide finalizarla, regla 1 de COM-FIN-RUT). Solo lectura."""
    hoy = hoy or stock.hoy()
    actor = _exigir_transportista(actor)
    return sorted(_filas(_con_destino(_de_la_ruta(actor.pk, hoy)), hoy), key=_orden_de_presentacion)


def finalizar_ruta(actor):
    """COM-FIN-RUT: `en_ruta = False` (`fecha_inicio_ruta` queda: regla 3, puede iniciar otra ruta hoy). En UNA transacción: cuenta → invernadero → vehículo → entregas de la ruta, releídas.
    Errores: `ruta_no_iniciada` (precondición b: la de ayer ya venció sola, regla 4) y `ruta_con_entregas_pendientes` (regla 1, con `params` `pendientes`: los códigos). Auditoría `fin_ruta`
    con los intentos fallidos que registró hoy. Devuelve el `Vehiculo`. `PermissionDenied` si no es un Transportista activo."""
    previa = _exigir_transportista(actor)
    asignacion = TransportistaInvernadero.objects.filter(transportista_id=previa.pk).first()
    with transaction.atomic():
        quien = Usuario.objects.select_for_update(no_key=True).get(pk=previa.pk)
        if not quien.is_active or rol_de(quien) != Usuario.Rol.TRANSPORTISTA:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        if asignacion is not None:
            bloquear_invernadero_activo(asignacion.invernadero_id)
        vehiculo = Vehiculo.objects.select_for_update(no_key=True).filter(transportista_id=quien.pk).first()
        hoy = stock.hoy()
        if vehiculo is None or not vehiculo.esta_en_ruta(hoy):
            raise _rechazar("ruta_no_iniciada", "No tenés una ruta iniciada hoy: no hay nada que finalizar.")
        if asignacion is not None:
            list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk__in=_de_la_ruta(quien.pk, hoy).values("pk")).order_by("pk"))
        pendientes = list(_de_la_ruta(quien.pk, hoy).order_by("pk"))
        if pendientes:
            raise _rechazar(
                "ruta_con_entregas_pendientes",
                f"Todavía te quedan {len(pendientes)} entregas sin resolver: concretalas o registrá el intento fallido de cada una.",
                params={"pendientes": [e.codigo for e in pendientes]},
            )
        Vehiculo.objects.filter(pk=vehiculo.pk).update(en_ruta=False)
        vehiculo.refresh_from_db()
        intentos = list(IntentoFallido.objects.filter(transportista_id=quien.pk, fecha_hora__date=hoy).select_related("entrega").order_by("pk"))
        datos = {"intentos_fallidos": [f"{i.entrega.codigo}: {i.get_motivo_display()}" for i in intentos]}
        RegistroAuditoria.objects.registrar(
            usuario=quien,
            accion=RegistroAuditoria.Accion.FIN_RUTA,
            afectados=[vehiculo, *intentos],
            detalle={"cambios": {"en_ruta": {"antes": True, "despues": False}}, "datos": datos},
        )
        return vehiculo


def registrar_intento_fallido(actor, entrega_id, motivo, descripcion=""):
    """COM-CNC-ENT 4a y COM-FIN-RUT regla 1 (la misma función para los dos). Con envío, el Transportista asignado con la ruta iniciada. Bloquea: cuentas (el Transportista y el Vendedor
    del contrato) → el invernadero de origen → la entrega; relee y verifica. Efecto: un `IntentoFallido`; la entrega sigue «a realizar» con `fecha_programada_orden = hoy + 1` y sin transportista (sus
    reservas de insumo siguen activas y no se registra ningún consumo); aviso al Vendedor, correo al cliente con `estado_aviso_cliente` y auditoría `intento_fallido_entrega`. No es un
    incumplimiento de la empresa. Errores: `motivo_obligatorio`, `descripcion_larga`, `ruta_no_iniciada` y `entrega_no_concretable` (14a). `Http404` si la entrega no existe; `PermissionDenied`
    si no es del Transportista. Devuelve el `IntentoFallido`."""
    actor = _exigir_transportista(actor)
    previa = Entrega.objects.select_related("contrato_entrega").filter(pk=entrega_id).first()
    if previa is None:
        raise Http404("La entrega no existe.")
    if previa.transportista_id not in (None, actor.pk):  # sin transportista (ya pasó a mañana) se informa como 14a; la de otro, 403
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    if motivo not in IntentoFallido.Motivo.values:
        raise _rechazar("motivo_obligatorio", "Elegí el motivo.", "motivo")
    descripcion = (descripcion or "").strip()
    if len(descripcion) > LARGO_DE_LA_DESCRIPCION:
        raise _rechazar("descripcion_larga", f"La descripción admite hasta {LARGO_DE_LA_DESCRIPCION} caracteres.", "descripcion")
    with transaction.atomic():
        cuentas = {c for c in (actor.pk, previa.contrato_entrega.vendedor_id) if c}
        por_id = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in=cuentas).order_by("pk")}
        quien = por_id.get(actor.pk)
        if quien is None or not quien.is_active or rol_de(quien) != Usuario.Rol.TRANSPORTISTA:
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        bloquear_invernadero_activo(previa.invernadero_id)
        list(OrdenTrabajo.objects.select_for_update(no_key=True, of=("self",)).filter(pk=previa.pk))
        entrega = Entrega.objects.select_related("contrato_entrega__cliente", "contrato_entrega__vendedor").get(pk=previa.pk)
        hoy = stock.hoy()
        if entrega.estado_orden != A_REALIZAR or entrega.transportista_id != quien.pk or entrega.modalidad_entrega != ENVIO or entrega.fecha_programada_orden > hoy:
            raise _rechazar("entrega_no_concretable", f"La entrega {entrega.codigo} ya no está a realizar o ya no es tuya.")  # 14a
        vehiculo = Vehiculo.objects.filter(transportista_id=quien.pk).first()
        if vehiculo is None or not vehiculo.esta_en_ruta(hoy):
            raise _rechazar("ruta_no_iniciada", "Iniciá la ruta del día antes de registrar un intento fallido.")
        contrato = entrega.contrato_entrega
        programada = entrega.fecha_programada_orden
        nueva_fecha = hoy + timedelta(days=1)
        intento = IntentoFallido.objects.create(entrega=entrega, transportista=Transportista.objects.get(pk=quien.pk), fecha_programada=programada, motivo=motivo, descripcion=descripcion)
        Entrega.objects.filter(pk=entrega.pk).update(
            fecha_programada_orden=nueva_fecha, transportista=None, recordatorio_para=None, aviso_atrasada_para=None  # para que los avisos de COM-05a1 vuelvan a correr por la fecha nueva
        )
        entrega.fecha_programada_orden, entrega.transportista = nueva_fecha, None
        motivo_texto = intento.get_motivo_display().lower()
        entregas._avisar_al_vendedor(
            contrato,
            f"No se pudo entregar {entrega.codigo}",
            f"{entrega.codigo} · no se pudo entregar: {motivo_texto}. Pasa al {nueva_fecha:%d/%m/%Y}, sin transportista." + (f" {descripcion}" if descripcion else ""),
        )
        entregas._marcar_aviso_pendiente(entrega, contrato, cambio_de_fecha=True)  # el correo al cliente sale después de confirmar y lo reintenta el paso 50
        RegistroAuditoria.objects.registrar(
            usuario=quien,
            accion=RegistroAuditoria.Accion.INTENTO_FALLIDO_ENTREGA,
            afectados=[entrega, intento],
            detalle={
                "cambios": {
                    "fecha_programada_orden": {"antes": f"{programada:%d/%m/%Y}", "despues": f"{nueva_fecha:%d/%m/%Y}"},
                    "transportista": {"antes": referencia(quien), "despues": None},
                },
                "datos": {"motivo": motivo, "descripcion": descripcion, "contrato": contrato.codigo},
            },
        )
        return intento


def entrega_de_la_ruta(actor, entrega_id, hoy=None):
    """La `FilaDeRuta` de una entrega del Transportista (para las pantallas del intento fallido y de finalizar). `Http404` si no existe; `PermissionDenied` si no es una entrega suya con envío."""
    hoy = hoy or stock.hoy()
    actor = _exigir_transportista(actor)
    entrega = _con_destino(Entrega.objects.filter(pk=entrega_id)).first()
    if entrega is None:
        raise Http404("La entrega no existe.")
    if entrega.transportista_id is None and entrega.modalidad_entrega == ENVIO:  # ya pasó a mañana (intento fallido) o la dejó sin transportista otra operación: extensión 14a
        raise _rechazar("entrega_no_concretable", f"La entrega {entrega.codigo} ya no está en tu ruta.")
    if entrega.transportista_id != actor.pk or entrega.modalidad_entrega != ENVIO:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return _filas([entrega], hoy)[0]
