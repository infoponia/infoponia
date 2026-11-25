# Ejercicios contables (CON-ABR-EJE, D-84 puntos 2, 3, 5 y 10): apertura automática (paso diario 5 y autorrecuperación), primer ejercicio,
# lecturas, elección del ejercicio donde va un asiento y el cierre manual (CON-CRR-EJE, CON-03a).
# Bloqueos (docs/patrones/asientos.md, sección 2): la apertura bloquea la fila del abierto y la del en cierre, en orden de `id`, y nada más; el
# primer ejercicio no tiene nada que bloquear y lo respalda la restricción única de la base (el perdedor atrapa el `IntegrityError` y relee).
# El cierre bloquea SOLO la fila del ejercicio que cierra (FOR NO KEY UPDATE) y no bloquea nada después: así no cruza el orden de nadie.
import datetime
from collections import namedtuple
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.utils import timezone

from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import responsables
from core.models import RegistroAuditoria, referencia, rol_de
from core.procesos import ResumenDePaso

Estado = EjercicioContable.Estado
Accion = RegistroAuditoria.Accion

# Lo que hizo `abrir_ejercicio_si_corresponde` (docs/api/asientos.md): cada uno de los cuatro primeros, la última instancia afectada o `None`.
# Los dos contadores son un agregado de CON-02: con varias vueltas (sistema apagado) el resumen del paso diario necesita el total.
ResultadoApertura = namedtuple(
    "ResultadoApertura",
    "primero_creado paso_a_en_cierre cerrado_solo nuevo_abierto cantidad_creados cantidad_cerrados_solos",
    defaults=(0, 0),
)
# El ejercicio donde va un asiento y, si no es el de su fecha, el motivo (`cerrado`, `anterior` o `futura`; `None` si es el de su fecha).
Destino = namedtuple("Destino", "ejercicio motivo")

# Tope de seguridad de vueltas dentro de una misma apertura (CON-ABR-EJE, «Primer ejercicio sin condición de fecha»).
MAXIMO_DE_VUELTAS = 10
# Cómo se escribe el motivo en la aclaración de la fecha del hecho (H10) y qué error lanza un asiento manual.
MOTIVOS = {
    "cerrado": "el ejercicio de esa fecha ya está cerrado",
    "anterior": "anterior al primer ejercicio",
    "futura": "posterior a la fecha de hoy",
}
CODIGOS_DE_FECHA = {
    "cerrado": "fecha_en_ejercicio_cerrado",
    "anterior": "fecha_anterior_al_primer_ejercicio",
    "futura": "fecha_futura",
}


def cierre_previsto(inicio):
    """Fecha de cierre prevista de un ejercicio que empieza en ``inicio``: un año menos un día después (12 meses, MD-115, regla 3 de
    CON-ABR-EJE). Un 29 de febrero se toma como 1 de marzo del año siguiente (el cierre cae el 28 de febrero)."""
    try:
        mismo_dia = inicio.replace(year=inicio.year + 1)
    except ValueError:  # 29 de febrero
        mismo_dia = datetime.date(inicio.year + 1, 3, 1)
    return mismo_dia - datetime.timedelta(days=1)


# --- Lecturas (no escriben ni bloquean) -------------------------------------------------------------------------------------------------------------


def ejercicio_abierto():
    """El `EjercicioContable` abierto o `None`."""
    return EjercicioContable.objects.filter(estado_ejercicio=Estado.ABIERTO).first()


def ejercicio_en_cierre():
    """El `EjercicioContable` en cierre o `None`."""
    return EjercicioContable.objects.filter(estado_ejercicio=Estado.EN_CIERRE).first()


def destino_del_asiento(fecha, *, automatico, hoy=None):
    """Devuelve el `Destino` de un asiento con esa fecha del hecho (D-84 punto 5, H10).

    - Una fecha posterior a hoy es «futura»; una que cae en un ejercicio abierto o en cierre va a ese ejercicio.
    - Si no, es «anterior» al primer ejercicio o está en un ejercicio «cerrado».
    - Un asiento **automático** nunca se rechaza por la fecha (decisión de CON-02): en esos tres casos va al ejercicio abierto y el motivo
      queda en el `Destino`. Uno **manual** (o un contraasiento) lanza `ErrorContable` con el código del motivo.
    """
    hoy = hoy or timezone.localdate()
    motivo = None
    if fecha > hoy:
        motivo = "futura"
    else:
        en_rango = EjercicioContable.objects.filter(
            estado_ejercicio__in=[Estado.ABIERTO, Estado.EN_CIERRE],
            fecha_inicio_ejercicio__lte=fecha,
            fecha_cierre_ejercicio__gte=fecha,
        ).first()
        if en_rango is not None:
            return Destino(en_rango, None)
        primero = EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id").first()
        motivo = "anterior" if primero is None or fecha < primero.fecha_inicio_ejercicio else "cerrado"
    if not automatico:
        rangos = list(
            EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id").values_list("fecha_inicio_ejercicio", "fecha_cierre_ejercicio")
        )
        raise _error_de_fecha(motivo, fecha, hoy, rangos)
    abierto = ejercicio_abierto()
    if abierto is None:
        raise ErrorContable("sin_ejercicio_abierto", "No hay un ejercicio contable abierto donde asentar.")
    return Destino(abierto, motivo)


def _error_de_fecha(motivo, fecha, hoy, rangos):
    """El `ErrorContable` de un asiento manual o contraasiento con una fecha que no admite (C2, extensiones 5e y 3c): el mensaje explica el motivo.
    ``rangos`` es la lista `[(inicio, cierre)]` de todos los ejercicios, del más viejo al más nuevo."""
    texto = f"{fecha:%d/%m/%Y}"
    if motivo == "futura":
        mensaje = f"La fecha {texto} es posterior a hoy ({hoy:%d/%m/%Y}): un asiento no puede llevar una fecha posterior a hoy."
    elif motivo == "anterior":
        desde = f", que empieza el {rangos[0][0]:%d/%m/%Y}" if rangos else ""
        mensaje = f"La fecha {texto} es anterior al primer ejercicio contable{desde}."
    else:
        inicio, cierre = next(((i, c) for i, c in rangos if i <= fecha <= c), (None, None))
        donde = f"al ejercicio del {inicio:%d/%m/%Y} al {cierre:%d/%m/%Y}, que está" if inicio else "a un ejercicio"
        mensaje = f"La fecha {texto} pertenece {donde} cerrado y ya no recibe asientos."
    return ErrorContable(CODIGOS_DE_FECHA[motivo], mensaje, campo="fecha")


# El ejercicio donde iría un asiento si se registrara ahora, sin haber escrito nada (`destino_previsto`).
DestinoPrevisto = namedtuple("DestinoPrevisto", "numero inicio cierre estado por_abrir")


def destino_previsto(fecha, *, hoy=None):
    """Dónde iría un asiento MANUAL (o un contraasiento) con esa fecha, calculado SOLO EN MEMORIA (decisión del 25/11/2026): reproduce las vueltas de
    `abrir_ejercicio_si_corresponde(hoy)` sobre una copia de los ejercicios, sin crear ni cambiar nada, y después aplica las reglas de
    `destino_del_asiento` (C2, C3). Así el resumen previo no rechaza una fecha válida porque el abierto venció y falta abrir el siguiente.
    Devuelve `DestinoPrevisto(numero, inicio, cierre, estado, por_abrir)` (``por_abrir``: el ejercicio todavía no existe); lanza los mismos
    `ErrorContable` de fecha que el registro."""
    hoy = hoy or timezone.localdate()
    simulados = [
        {"id": e.pk, "inicio": e.fecha_inicio_ejercicio, "cierre": e.fecha_cierre_ejercicio, "estado": e.estado_ejercicio}
        for e in EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id")
    ]

    def con_estado(estado):
        return next((e for e in simulados if e["estado"] == estado), None)

    def nuevo(inicio):
        return {"id": None, "inicio": inicio, "cierre": cierre_previsto(inicio), "estado": Estado.ABIERTO}

    def necesita_apertura():
        abierto = con_estado(Estado.ABIERTO)
        return abierto is None or hoy > abierto["cierre"]

    vueltas = 0
    while necesita_apertura():
        if vueltas >= MAXIMO_DE_VUELTAS:
            raise ErrorContable(
                "ejercicios_atrasados", f"Hay más de {MAXIMO_DE_VUELTAS} ejercicios atrasados: revisá la fecha del sistema."
            )
        vueltas += 1
        abierto = con_estado(Estado.ABIERTO)
        if not simulados:
            simulados.append(nuevo(hoy))
        elif abierto is None:
            ultimo = max(simulados, key=lambda e: e["cierre"])
            simulados.append(nuevo(ultimo["cierre"] + datetime.timedelta(days=1)))
        else:
            previo = con_estado(Estado.EN_CIERRE)
            if previo is not None:
                previo["estado"] = Estado.CERRADO
            abierto["estado"] = Estado.EN_CIERRE
            simulados.append(nuevo(abierto["cierre"] + datetime.timedelta(days=1)))

    rangos = [(e["inicio"], e["cierre"]) for e in simulados]
    if fecha > hoy:
        raise _error_de_fecha("futura", fecha, hoy, rangos)
    for numero, e in enumerate(simulados, start=1):
        if e["estado"] in (Estado.ABIERTO, Estado.EN_CIERRE) and e["inicio"] <= fecha <= e["cierre"]:
            return DestinoPrevisto(numero, e["inicio"], e["cierre"], e["estado"], e["id"] is None)
    raise _error_de_fecha("anterior" if fecha < simulados[0]["inicio"] else "cerrado", fecha, hoy, rangos)


def ejercicio_para(fecha, *, automatico, hoy=None):
    """El ejercicio donde iría un asiento con esa fecha (docs/api/asientos.md, «Lectura»); ver `destino_del_asiento`."""
    return destino_del_asiento(fecha, automatico=automatico, hoy=hoy).ejercicio


# --- Apertura (CON-ABR-EJE) --------------------------------------------------------------------------------------------------------------------------


def _numero_de(ejercicio):
    """Posición del ejercicio por fecha de inicio («Ejercicio 1»): para los textos de los avisos."""
    return EjercicioContable.objects.filter(fecha_inicio_ejercicio__lte=ejercicio.fecha_inicio_ejercicio).count()


def numero_de_ejercicio(ejercicio):
    """El «N.º» de un ejercicio (su posición por fecha de inicio) para las pantallas y los avisos; ver `ejercicios_numerados` para una lista."""
    return _numero_de(ejercicio)


# Un ejercicio con su número («Ejercicio 1») y la cantidad de asientos, para la lista de ejercicios y el selector del libro.
EjercicioNumerado = namedtuple("EjercicioNumerado", "numero ejercicio cantidad_de_asientos")


def ejercicios_numerados():
    """Todos los ejercicios, del más viejo al más nuevo, con su número (posición por fecha de inicio) y su cantidad de asientos: una sola consulta."""
    lista = EjercicioContable.objects.select_related("contador").annotate(cantidad_de_asientos=Count("asientos")).order_by("fecha_inicio_ejercicio", "id")
    return [EjercicioNumerado(numero, ejercicio, ejercicio.cantidad_de_asientos) for numero, ejercicio in enumerate(lista, start=1)]


def _crear(inicio, origen):
    """Crea un ejercicio abierto que empieza en ``inicio`` y lo audita con actor `None` (InfoPonia): `alta_ejercicio_contable`."""
    cierre = cierre_previsto(inicio)
    nuevo = EjercicioContable.objects.create(
        fecha_inicio_ejercicio=inicio, fecha_cierre_ejercicio=cierre, estado_ejercicio=Estado.ABIERTO
    )
    RegistroAuditoria.objects.registrar(
        None,
        Accion.ALTA_EJERCICIO_CONTABLE,
        [nuevo],
        {
            "cambios": {
                "fecha_inicio_ejercicio": {"antes": None, "despues": inicio.isoformat()},
                "fecha_cierre_ejercicio": {"antes": None, "despues": cierre.isoformat()},
                "estado_ejercicio": {"antes": None, "despues": Estado.ABIERTO},
            },
            "datos": {"origen": origen},
        },
    )
    return nuevo


def _cambiar_estado(ejercicio, nuevo_estado, datos=None):
    """Cambia el estado del ejercicio y lo audita con actor `None`: `modificacion_ejercicio_contable` (D-84 punto 9)."""
    antes = ejercicio.estado_ejercicio
    ejercicio.estado_ejercicio = nuevo_estado
    ejercicio.save(update_fields=["estado_ejercicio"])
    detalle = {"cambios": {"estado_ejercicio": {"antes": antes, "despues": nuevo_estado}}}
    if datos:
        detalle["datos"] = datos
    RegistroAuditoria.objects.registrar(None, Accion.MODIFICACION_EJERCICIO_CONTABLE, [ejercicio], detalle)


def _necesita_apertura(hoy):
    """Lectura sin bloquear: ¿hay algo que hacer? Sin abierto sí; con abierto, solo si venció (hoy es posterior a su cierre, regla 2)."""
    abierto = ejercicio_abierto()
    return abierto is None or hoy > abierto.fecha_cierre_ejercicio


def abrir_ejercicio_si_corresponde(hoy=None):
    """CON-ABR-EJE: abre ejercicios hasta que haya un abierto que no venció; devuelve `ResultadoApertura`. Idempotente (regla 5).

    Si el abierto no venció, no escribe nada. Si hay que actuar, en una transacción bloquea el abierto y el en cierre (orden de `id`),
    vuelve a leer y, por cada vuelta: cierra solo el que estaba en cierre (C1, sin Contador), pasa el abierto a «en cierre» y crea el
    siguiente (que empieza el día siguiente al cierre previsto del anterior). Sin ningún ejercicio crea el primero, que empieza hoy
    (D-84 punto 3). Hasta 10 vueltas; superado, `ErrorContable` `ejercicios_atrasados` y no queda nada escrito.
    """
    hoy = hoy or timezone.localdate()
    if not _necesita_apertura(hoy):
        return ResultadoApertura(None, None, None, None)

    primero = en_cierre = cerrado = nuevo = None
    creados = cerrados = vueltas = 0
    with transaction.atomic():
        # El bloqueo va ANTES de releer: si otra apertura lo tenía, esperamos y vemos su resultado (read committed).
        list(
            EjercicioContable.objects.select_for_update(no_key=True)
            .filter(estado_ejercicio__in=[Estado.ABIERTO, Estado.EN_CIERRE])
            .order_by("id")
        )
        while _necesita_apertura(hoy):
            if vueltas >= MAXIMO_DE_VUELTAS:
                raise ErrorContable(
                    "ejercicios_atrasados",
                    f"Hay más de {MAXIMO_DE_VUELTAS} ejercicios atrasados: revisá la fecha del sistema.",
                )
            vueltas += 1
            abierto = ejercicio_abierto()
            if not EjercicioContable.objects.exists():
                # Primera operación contable: no hay nada que bloquear; si otra la crea a la vez, la restricción única nos frena.
                try:
                    with transaction.atomic():
                        primero = _crear(hoy, "puesta en marcha")
                except IntegrityError:
                    continue  # otra operación creó el primero: se relee y se sigue
                creados += 1
                continue
            if abierto is None:
                ultimo = EjercicioContable.objects.order_by("-fecha_cierre_ejercicio", "-id").first()
                nuevo = _crear(ultimo.fecha_cierre_ejercicio + datetime.timedelta(days=1), "apertura automática")
                creados += 1
                continue
            previo = ejercicio_en_cierre()
            if previo is not None:
                _cambiar_estado(previo, Estado.CERRADO, {"origen": "cierre automático"})
                cerrado = previo
                cerrados += 1
                responsables.notificar_al_responsable_contable(
                    f"El ejercicio N.º {_numero_de(previo)} se cerró solo",
                    f"Se cerró solo porque venció el siguiente (terminó el {previo.fecha_cierre_ejercicio:%d/%m/%Y}).",
                )
            _cambiar_estado(abierto, Estado.EN_CIERRE)
            en_cierre = abierto
            responsables.notificar_al_responsable_contable(
                f"El ejercicio N.º {_numero_de(abierto)} pasó a «en cierre»",
                f"Terminó el {abierto.fecha_cierre_ejercicio:%d/%m/%Y}. Revisá el libro de gestión y cerralo cuando estés conforme.",
            )
            nuevo = _crear(abierto.fecha_cierre_ejercicio + datetime.timedelta(days=1), "apertura automática")
            creados += 1
    return ResultadoApertura(primero, en_cierre, cerrado, nuevo, creados, cerrados)


def crear_primer_ejercicio(fecha_inicio, hoy=None):
    """La puesta en marcha (D-84 punto 3): crea el primer ejercicio, que empieza en ``fecha_inicio`` (no puede ser futura).

    Idempotente: si ya existe algún ejercicio no hace nada y devuelve el primero que hay. Respaldada por la restricción única si dos
    puestas en marcha corren a la vez.
    """
    hoy = hoy or timezone.localdate()
    if fecha_inicio > hoy:
        raise ErrorContable(
            "fecha_futura", "La fecha de inicio del primer ejercicio no puede ser futura.", campo="fecha_inicio"
        )

    def existente():
        return EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id").first()

    with transaction.atomic():
        if existente() is not None:
            return existente()
        try:
            with transaction.atomic():
                return _crear(fecha_inicio, "puesta en marcha")
        except IntegrityError:
            return existente()  # otra operación lo creó a la vez


# --- Cierre manual (CON-CRR-EJE) ---------------------------------------------------------------------------------------------------------------------

# Resumen que la pantalla muestra antes de confirmar el cierre (regla 4): el ejercicio (con su rango) y lo que tiene asentado.
ResumenDeCierre = namedtuple("ResumenDeCierre", "ejercicio cantidad_de_asientos total_debe total_haber")


def resumen_para_cierre(ejercicio_id):
    """El resumen del ejercicio para el paso previo al cierre (regla 4 de CON-CRR-EJE): rango, cantidad de asientos y total del Debe y del Haber.
    Solo lectura: no bloquea ni audita; las sumas son una consulta agregada y no una por asiento. Un id inexistente es 404."""
    try:
        ejercicio = EjercicioContable.objects.get(pk=ejercicio_id)
    except EjercicioContable.DoesNotExist:
        raise Http404("No existe ese ejercicio.") from None
    sumas = MovimientoContable.objects.filter(asiento__ejercicio_id=ejercicio_id).aggregate(
        debe=Sum("importe_movimiento", filter=Q(tipo_movimiento=DEBE)),
        haber=Sum("importe_movimiento", filter=Q(tipo_movimiento=HABER)),
    )
    cantidad = AsientoContable.objects.filter(ejercicio_id=ejercicio_id).count()
    cero = Decimal("0.00")
    return ResumenDeCierre(ejercicio, cantidad, sumas["debe"] or cero, sumas["haber"] or cero)


def cerrar_ejercicio(actor, ejercicio_id):
    """CON-CRR-EJE: cierra de forma definitiva un ejercicio «en cierre» y lo devuelve (docs/api/asientos.md, «Escritura»).

    Orden: (1) permisos (`responsables.puede_registrar_asientos`: el Contador activo o, sin Contador activo, el Gerente; si no, `PermissionDenied`);
    (2) bloquea el ejercicio (`FOR NO KEY UPDATE`) y lo relee: si ya no está «en cierre» (otro lo cerró, o la apertura lo cerró sola, C1) lanza
    `ErrorContable` `ejercicio_no_esta_en_cierre`; (3) vuelve a verificar que el actor siga siendo quien cierra (pudo dejar de serlo mientras esperaba);
    (4) pasa a «cerrado», asocia al Contador si es él (R010; si es el Gerente queda vacío) y audita `modificacion_ejercicio_contable`.
    No genera asientos de cierre ni refundición (regla 3) y no tiene verificaciones que lo bloqueen (regla 4). Lo único que bloquea es esa fila,
    y nada después: no cruza el orden de bloqueos de `docs/patrones/asientos.md`, sección 2."""
    if not responsables.puede_registrar_asientos(actor):
        raise PermissionDenied("Solo el Contador, o el Gerente si no hay un Contador activo, cierra un ejercicio.")
    with transaction.atomic():
        try:
            ejercicio = EjercicioContable.objects.select_for_update(no_key=True).get(pk=ejercicio_id)
        except EjercicioContable.DoesNotExist:
            raise Http404("No existe ese ejercicio.") from None
        if ejercicio.estado_ejercicio != Estado.EN_CIERRE:
            raise ErrorContable(
                "ejercicio_no_esta_en_cierre",
                "Ese ejercicio ya no está en cierre (alguien lo cerró mientras tanto, o todavía no terminó). Actualizá la pantalla.",
            )
        if not responsables.puede_registrar_asientos(actor):  # revalida después de bloquear (orden del cierre, punto 3)
            raise PermissionDenied("Ya no sos quien cierra los ejercicios.")
        rol = rol_de(actor)
        cambios = {"estado_ejercicio": {"antes": Estado.EN_CIERRE, "despues": Estado.CERRADO}}
        ejercicio.estado_ejercicio = Estado.CERRADO
        if rol == "contador":  # R010: el Contador que lo cerró; si lo cerró el Gerente, queda vacío y la persona está en la auditoría
            ejercicio.contador_id = actor.pk
            cambios["contador"] = {"antes": None, "despues": referencia(actor)}
        ejercicio.save(update_fields=["estado_ejercicio", "contador"])
        RegistroAuditoria.objects.registrar(
            actor, Accion.MODIFICACION_EJERCICIO_CONTABLE, [ejercicio], {"cambios": cambios, "datos": {"cerrado_por": rol}}
        )
    return ejercicio


# --- Paso diario 5 -----------------------------------------------------------------------------------------------------------------------------------


def paso_abrir_ejercicio(hoy):
    """Paso 5 del proceso diario (D-56, CON-ABR-EJE): llama a `abrir_ejercicio_si_corresponde(hoy)` y resume lo que hizo."""
    existia = ejercicio_abierto() is not None
    resultado = abrir_ejercicio_si_corresponde(hoy)
    partes = []
    if resultado.primero_creado is not None:
        partes.append(f"primer ejercicio creado ({resultado.primero_creado})")
    if resultado.cerrado_solo is not None:
        partes.append(f"{resultado.cantidad_cerrados_solos} cerrado(s) solo(s)")
    if resultado.paso_a_en_cierre is not None:
        partes.append(f"{resultado.paso_a_en_cierre} pasó a «en cierre»")
    if resultado.nuevo_abierto is not None:
        partes.append(f"abierto: {resultado.nuevo_abierto}")
    return ResumenDePaso(
        procesados=1 if existia else 0,
        creados=resultado.cantidad_creados,
        resueltos=resultado.cantidad_cerrados_solos,
        detalle="; ".join(partes) or "sin cambios",
    )
