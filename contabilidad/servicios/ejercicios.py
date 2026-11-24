# Ejercicios contables (CON-ABR-EJE, D-84 puntos 2, 3, 5 y 10): apertura automática (paso diario 5 y autorrecuperación), primer ejercicio,
# lecturas y elección del ejercicio donde va un asiento. El cierre manual es CON-03a y no está acá.
# Bloqueos (docs/patrones/asientos.md, sección 2): la apertura bloquea la fila del abierto y la del en cierre, en orden de `id`, y nada más; el
# primer ejercicio no tiene nada que bloquear y lo respalda la restricción única de la base (el perdedor atrapa el `IntegrityError` y relee).
import datetime
from collections import namedtuple

from django.db import IntegrityError, transaction
from django.utils import timezone

from contabilidad.errores import ErrorContable
from contabilidad.models import EjercicioContable
from contabilidad.servicios import responsables
from core.models import RegistroAuditoria, referencia  # noqa: F401 - `referencia` lo reusan los servicios hermanos
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
        raise ErrorContable(
            CODIGOS_DE_FECHA[motivo], f"La fecha {fecha:%d/%m/%Y} no admite un asiento: {MOTIVOS[motivo]}.", campo="fecha"
        )
    abierto = ejercicio_abierto()
    if abierto is None:
        raise ErrorContable("sin_ejercicio_abierto", "No hay un ejercicio contable abierto donde asentar.")
    return Destino(abierto, motivo)


def ejercicio_para(fecha, *, automatico, hoy=None):
    """El ejercicio donde iría un asiento con esa fecha (docs/api/asientos.md, «Lectura»); ver `destino_del_asiento`."""
    return destino_del_asiento(fecha, automatico=automatico, hoy=hoy).ejercicio


# --- Apertura (CON-ABR-EJE) --------------------------------------------------------------------------------------------------------------------------


def _numero_de(ejercicio):
    """Posición del ejercicio por fecha de inicio («Ejercicio 1»): para los textos de los avisos."""
    return EjercicioContable.objects.filter(fecha_inicio_ejercicio__lte=ejercicio.fecha_inicio_ejercicio).count()


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
