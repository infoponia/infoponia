# Asientos automáticos (D-86, D-84 puntos 4, 5, 6 y 9): `registrar_asiento_automatico`, la única puerta por la que las demás apps asientan.
# Corre dentro de la transacción de quien llama, con sus bloqueos ya tomados. EL EJERCICIO SE BLOQUEA AL FINAL (`_bloquear_ejercicio`, D-86
# punto 2, docs/patrones/asientos.md sección 2): es lo último que cualquier servicio bloquea, para no cruzar el orden de D-30 y D-32.
from collections import namedtuple
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable, ErroresContables
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import ejercicios, responsables
from contabilidad.templatetags.formato_contable import pesos
from core import notificaciones
from core.models import Gerente, RegistroAuditoria, Usuario, referencia, rol_de

Accion = RegistroAuditoria.Accion
CENTAVOS = Decimal("0.01")
# `DecimalField(max_digits=14, decimal_places=2)`: hasta 12 dígitos enteros.
LIMITE_DEL_IMPORTE = Decimal(10) ** 12
LARGO_MAXIMO_DE_DESCRIPCION = 300
SEPARADOR = " — "


def _validar_movimientos(movimientos):
    """Valida tipo e importe de cada línea (errores de programación, docs/api/asientos.md) y devuelve `[(codigo, tipo, importe)]`
    con el importe en dos decimales. El importe tiene que ser `Decimal` finito, no negativo, con a lo sumo dos decimales."""
    lineas = []
    for codigo, tipo, importe in movimientos:
        if tipo not in (DEBE, HABER):
            raise ErrorContable(
                "tipo_de_movimiento_invalido", f"El tipo de movimiento {tipo!r} no es válido: usá «D» (Debe) o «H» (Haber)."
            )
        if (
            not isinstance(importe, Decimal)
            or not importe.is_finite()
            or importe < 0
            or importe >= LIMITE_DEL_IMPORTE
            or importe != importe.quantize(CENTAVOS)
        ):
            raise ErrorContable(
                "importe_invalido",
                f"El importe {importe!r} de la cuenta {codigo} no es válido: tiene que ser un Decimal no negativo con dos decimales.",
            )
        lineas.append((codigo, tipo, importe.quantize(CENTAVOS)))
    return lineas


def _cuentas_por_codigo(lineas):
    """`{codigo: CuentaContable}` de todas las líneas (también las de importe cero); `cuenta_inexistente` si falta alguna."""
    codigos = {codigo for codigo, _, _ in lineas}
    cuentas = {c.codigo_cuenta: c for c in CuentaContable.objects.filter(codigo_cuenta__in=codigos)}
    for codigo in sorted(codigos - set(cuentas)):
        raise ErrorContable("cuenta_inexistente", f"La cuenta contable {codigo} no existe en el plan de cuentas.")
    return cuentas


def _descripcion_con_aclaracion(descripcion, aclaracion):
    """La descripción de quien llama primero, separada por « — » de la aclaración de la fecha real (H10). Si pasa de 300 caracteres se
    recorta la de quien llama (termina en «…»); la aclaración nunca se recorta, porque la fecha real no se puede perder."""
    if not descripcion:
        return aclaracion
    completa = f"{descripcion}{SEPARADOR}{aclaracion}"
    if len(completa) <= LARGO_MAXIMO_DE_DESCRIPCION:
        return completa
    lugar = LARGO_MAXIMO_DE_DESCRIPCION - len(SEPARADOR) - len(aclaracion)
    if lugar < 2:
        return aclaracion
    return f"{descripcion[: lugar - 1]}…{SEPARADOR}{aclaracion}"


def _bloquear_ejercicio(ejercicio_id):
    """Bloquea el ejercicio con `FOR NO KEY UPDATE` y devuelve la fila releída (D-86 punto 2). Es LO ÚLTIMO que se bloquea."""
    return EjercicioContable.objects.select_for_update(no_key=True).get(pk=ejercicio_id)


def registrar_asiento_automatico(actor, origen, fecha, movimientos, *, descripcion="", hoy=None):
    """Crea el asiento automático de una operación, sus movimientos y su auditoría, de una vez o ninguno (D-86; docs/api/asientos.md).

    ``origen``: instancia ya guardada de `OrigenDocumento` o de una hija. ``fecha``: la del HECHO (H10). ``movimientos``: lista de
    `(codigo_cuenta, "D" | "H", Decimal)`. Devuelve el `AsientoContable` o `None` si no corresponde (importes cero omitidos y menos de
    dos movimientos, H11). Lanza `ErrorContable` (`tipo_de_movimiento_invalido`, `importe_invalido`, `cuenta_inexistente`,
    `asiento_desbalanceado`, `origen_con_asiento`) ante un error de programación.

    Orden: (1) valida todo sin tocar la base de datos más que para leer cuentas; (2) autorrecuperación del ejercicio (H9); (3) elige el ejercicio
    destino, que nunca rechaza por fecha (decisión de CON-02); (4) **bloquea el ejercicio**; (5) con el ejercicio bloqueado, verifica de nuevo
    el origen y toma el número siguiente; (6) crea el asiento y los movimientos y audita.
    """
    if getattr(origen, "pk", None) is None:
        raise ValueError("El documento de origen tiene que estar guardado antes de crear su asiento.")
    hoy = hoy or timezone.localdate()
    lineas = _validar_movimientos(movimientos)
    cuentas = _cuentas_por_codigo(lineas)
    lineas = [linea for linea in lineas if linea[2] > 0]  # H11: los de importe 0 se omiten
    if len(lineas) < 2:
        return None  # H11: sin asiento, y quien llama no falla
    total_debe = sum(importe for _, tipo, importe in lineas if tipo == DEBE)
    total_haber = sum(importe for _, tipo, importe in lineas if tipo == HABER)
    if total_debe != total_haber:
        raise ErrorContable(
            "asiento_desbalanceado", f"El asiento no está balanceado: Debe {total_debe} y Haber {total_haber}."
        )

    with transaction.atomic():
        ejercicios.abrir_ejercicio_si_corresponde(hoy)  # autorrecuperación (H9): antes de bloquear el ejercicio destino
        for _ in range(3):
            destino = ejercicios.destino_del_asiento(fecha, automatico=True, hoy=hoy)
            ejercicio = _bloquear_ejercicio(destino.ejercicio.pk)
            if ejercicio.estado_ejercicio == destino.ejercicio.estado_ejercicio:
                break
            # Otro cambió el estado entre elegir y bloquear (cierre o apertura a la vez): se elige de nuevo.
        else:
            raise ErrorContable("cambio_simultaneo", "El ejercicio cambió mientras se registraba el asiento; probá de nuevo.")

        # Con el ejercicio bloqueado: la verificación que cierra la carrera por el mismo origen (la restricción única es solo el respaldo).
        if AsientoContable.objects.filter(origen_id=origen.pk).exists():
            raise ErrorContable("origen_con_asiento", f"El documento de origen ({origen}) ya tiene su asiento contable.")

        fecha_asiento = fecha
        if destino.motivo is not None:  # H10: el hecho no cae en un ejercicio que admita su fecha
            fecha_asiento = hoy
            aclaracion = (
                f"Fecha del hecho: {fecha:%d/%m/%Y} ({ejercicios.MOTIVOS[destino.motivo]}); se registra con la fecha de hoy."
            )
            descripcion = _descripcion_con_aclaracion(descripcion, aclaracion)

        try:
            asiento = _crear_y_auditar(
                actor,
                ejercicio,
                fecha_asiento,
                descripcion,
                lineas,
                cuentas,
                origen_id=origen.pk,
                afectados=[origen],
                cambios_extra={"origen": {"antes": None, "despues": referencia(origen)}},
            )
        except IntegrityError as error:
            if AsientoContable.objects.filter(origen_id=origen.pk).exists():
                raise ErrorContable("origen_con_asiento", f"El documento de origen ({origen}) ya tiene su asiento contable.") from error
            raise
    return asiento


def _crear_y_auditar(actor, ejercicio, fecha, descripcion, lineas, cuentas, *, origen_id=None, anula_id=None, afectados=(), cambios_extra=None, datos=None):
    """Con el ejercicio YA BLOQUEADO: toma el número siguiente, crea el asiento y sus movimientos y audita el asiento y cada movimiento (D-84 puntos 4 y 9).

    Lo comparten el asiento automático, el manual y el contraasiento. ``lineas``: `[(codigo, "D"|"H", Decimal)]` ya validadas y sin importes cero;
    ``cuentas``: `{codigo: CuentaContable}`. ``afectados`` suma instancias a las del registro del asiento; ``cambios_extra``, entradas a su `cambios`
    (el origen, o el asiento que anula); ``datos``, el contexto sin antes y después (D-36). Un `IntegrityError` al crear el asiento lo propaga quien llama."""
    numero = ejercicio.ultimo_numero_asiento + 1  # D-84 punto 4: leído DESPUÉS de bloquear
    ejercicio.ultimo_numero_asiento = numero
    ejercicio.save(update_fields=["ultimo_numero_asiento"])
    with transaction.atomic():
        asiento = AsientoContable.objects.create(
            ejercicio=ejercicio,
            numero_asiento=numero,
            fecha_asiento=fecha,
            descripcion_asiento=descripcion,
            origen_id=origen_id,
            anula_id=anula_id,
        )
    creados = MovimientoContable.objects.bulk_create(
        [
            MovimientoContable(asiento=asiento, cuenta=cuentas[codigo], tipo_movimiento=tipo, importe_movimiento=importe)
            for codigo, tipo, importe in lineas
        ]
    )
    # D-84 punto 9 y D-36: un registro por el asiento y uno por cada movimiento; fechas en ISO e importes como texto.
    cambios = {
        "numero_asiento": {"antes": None, "despues": numero},
        "fecha_asiento": {"antes": None, "despues": fecha.isoformat()},
        "descripcion_asiento": {"antes": None, "despues": descripcion},
        "ejercicio": {"antes": None, "despues": referencia(ejercicio)},
        **(cambios_extra or {}),
    }
    detalle = {"cambios": cambios, **({"datos": datos} if datos else {})}
    RegistroAuditoria.objects.registrar(actor, Accion.ALTA_ASIENTO_CONTABLE, [asiento, *afectados], detalle)
    for movimiento in creados:
        RegistroAuditoria.objects.registrar(
            actor,
            Accion.ALTA_MOVIMIENTO_CONTABLE,
            [movimiento, asiento],
            {
                "cambios": {
                    "cuenta_contable": {"antes": None, "despues": referencia(movimiento.cuenta)},
                    "tipo_movimiento": {"antes": None, "despues": movimiento.tipo_movimiento},
                    "importe_movimiento": {"antes": None, "despues": str(movimiento.importe_movimiento)},
                }
            },
        )
    return asiento


# --- CON-REG-ASI: asiento manual (CON-03b) -----------------------------------------------------------------------------------------------------------

# Una línea del resumen previo y el resumen completo (paso 5 de CON-REG-ASI). El ejercicio se describe con sus datos y no con la instancia, porque
# puede no existir todavía (``ejercicio_por_abrir``: el registro lo abriría, H9).
LineaDeResumen = namedtuple("LineaDeResumen", "indice codigo nombre tipo_cuenta tipo_cuenta_texto tipo_movimiento importe")
ResumenDeAsiento = namedtuple(
    "ResumenDeAsiento",
    "ejercicio_numero ejercicio_inicio ejercicio_cierre ejercicio_estado ejercicio_por_abrir lineas total_debe total_haber diferencia omitidas",
)


def _exigir_responsable(actor):
    """Regla «Quién registra» (D-85 punto 5): el Contador activo o, sin Contador activo, el Gerente. Si no, `PermissionDenied`; al Gerente con un
    Contador activo le dice que lo registra el Contador (extensión 1a, punto 3)."""
    if responsables.puede_registrar_asientos(actor):
        return
    es_gerente = actor is not None and getattr(actor, "is_active", False) and rol_de(actor) == Usuario.Rol.GERENTE
    if es_gerente and responsables.contador_activo() is not None:
        raise PermissionDenied("Lo registra el Contador: mientras haya un Contador activo, el Gerente no registra asientos.")
    raise PermissionDenied("Solo el Contador, o el Gerente si no hay un Contador activo, registra asientos.")


def _importe_valido(importe):
    """True si es un `Decimal` finito, mayor que cero, con a lo sumo dos decimales y que entra en la columna."""
    return (
        isinstance(importe, Decimal)
        and importe.is_finite()
        and 0 < importe < LIMITE_DEL_IMPORTE
        and importe == importe.quantize(CENTAVOS)
    )


def _errores_de_linea(indice, codigo, tipo, importe, cuentas):
    """Los errores de una línea (no nula): tipo, cuenta e importe, cada uno con su campo `movimientos[i].…` (extensiones 5c y 7a)."""
    errores = []
    if tipo not in (DEBE, HABER):
        errores.append(ErrorContable("tipo_de_movimiento_invalido", f"El tipo de movimiento {tipo!r} no es válido.", campo=f"movimientos[{indice}].tipo"))
    if not codigo or codigo not in cuentas:
        mensaje = f"La cuenta contable {codigo} no existe en el plan de cuentas." if codigo else "Elegí la cuenta."
        errores.append(ErrorContable("cuenta_inexistente", mensaje, campo=f"movimientos[{indice}].cuenta"))
    if not _importe_valido(importe):
        errores.append(
            ErrorContable("importe_invalido", "El importe tiene que ser un número mayor que cero, con hasta dos decimales.", campo=f"movimientos[{indice}].importe")
        )
    return errores


def _validar_manual(descripcion, movimientos):
    """Valida sin tocar la base más que para leer cuentas (CON-REG-ASI, pasos 2 y 5; extensiones 5a, 5b, 5c y 7a). Devuelve
    `(descripcion, lineas, cuentas, omitidas)` con `lineas = [(indice, codigo, tipo, importe)]` (``indice``: posición en la lista recibida, para marcar la
    fila). Junta TODOS los errores de campo y los lanza a la vez (patrón ABM): descripción, líneas y, si las líneas están bien, el balance."""
    errores = []
    descripcion = (descripcion or "").strip()
    if not descripcion:
        errores.append(ErrorContable("descripcion_obligatoria", "La descripción es obligatoria: explicá el motivo del asiento.", campo="descripcion"))
    elif len(descripcion) > LARGO_MAXIMO_DE_DESCRIPCION:
        mensaje = f"La descripción tiene {len(descripcion)} caracteres y el máximo es {LARGO_MAXIMO_DE_DESCRIPCION}."
        errores.append(ErrorContable("descripcion_muy_larga", mensaje, campo="descripcion"))
    cuentas = {c.codigo_cuenta: c for c in CuentaContable.objects.filter(codigo_cuenta__in={m[0] for m in movimientos if m[0]})}
    lineas, omitidas, errores_de_lineas = [], 0, []
    for indice, (codigo, tipo, importe) in enumerate(movimientos):
        if isinstance(importe, Decimal) and importe.is_finite() and importe == 0:
            omitidas += 1  # H11: se omite antes de validar nada más de la línea
            continue
        de_la_linea = _errores_de_linea(indice, codigo, tipo, importe, cuentas)
        errores_de_lineas.extend(de_la_linea)
        if not de_la_linea:
            lineas.append((indice, codigo, tipo, importe.quantize(CENTAVOS)))
    errores.extend(errores_de_lineas)
    if not errores_de_lineas:  # con una línea inválida no se puede calcular el balance
        debe = sum((i for _, _, t, i in lineas if t == DEBE), Decimal("0.00"))
        haber = sum((i for _, _, t, i in lineas if t == HABER), Decimal("0.00"))
        if len(lineas) < 2:
            errores.append(
                ErrorContable("faltan_movimientos", "Un asiento necesita al menos dos movimientos con importe mayor que cero.", campo="movimientos")
            )
        elif debe != haber:
            mensaje = f"El Debe ({pesos(debe)}) y el Haber ({pesos(haber)}) no coinciden: la diferencia es de {pesos(abs(debe - haber))}."
            errores.append(ErrorContable("asiento_desbalanceado", mensaje, campo="movimientos"))
    if errores:
        raise errores[0] if len(errores) == 1 else ErroresContables(errores)
    return descripcion, lineas, cuentas, omitidas


def registrar_asiento_manual(actor, fecha, descripcion, movimientos, *, hoy=None):
    """CON-REG-ASI: registra un asiento manual y lo devuelve (docs/api/asientos.md, «Escritura»; D-84 puntos 2, 4, 5 y 9).

    ``movimientos``: `[(codigo_cuenta, "D"|"H", Decimal)]`. Orden: (1) permisos (`PermissionDenied`); (2) valida sin bloquear (`ErrorContable`, errores
    por línea); (3) dentro de una transacción, autorrecuperación del ejercicio (H9) ANTES de validar la fecha (D-84 punto 2, decisión del 25/11/2026: sin ella
    se rechazaría como «cerrado» una fecha válida cuando el abierto venció); (4) la fecha con `destino_del_asiento(automatico=False)` (C2); (5) verifica
    de nuevo que el actor siga siendo el responsable (D-30); (6) **bloquea el ejercicio, lo último**, y revalida su estado y su rango (`cambio_simultaneo`,
    extensión 7b); (7) crea el asiento y sus movimientos y audita. Todo o nada."""
    hoy = hoy or timezone.localdate()
    _exigir_responsable(actor)
    descripcion, lineas, cuentas, _ = _validar_manual(descripcion, movimientos)
    lineas = [(codigo, tipo, importe) for _, codigo, tipo, importe in lineas]
    with transaction.atomic():
        ejercicios.abrir_ejercicio_si_corresponde(hoy)
        destino = ejercicios.destino_del_asiento(fecha, automatico=False, hoy=hoy)
        _exigir_responsable(actor)
        ejercicio = _bloquear_ejercicio(destino.ejercicio.pk)
        _exigir_que_la_fecha_siga_cayendo(ejercicio, fecha)
        return _crear_y_auditar(actor, ejercicio, fecha, descripcion, lineas, cuentas, afectados=[ejercicio])


def _exigir_que_la_fecha_siga_cayendo(ejercicio, fecha):
    """Con el ejercicio bloqueado y releído: sigue abierto o en cierre y su rango contiene la fecha; si no, `cambio_simultaneo` (extensiones 7b y 6b)."""
    Estado = EjercicioContable.Estado
    cae = ejercicio.fecha_inicio_ejercicio <= fecha <= ejercicio.fecha_cierre_ejercicio
    if ejercicio.estado_ejercicio not in (Estado.ABIERTO, Estado.EN_CIERRE) or not cae:
        raise ErrorContable(
            "cambio_simultaneo",
            f"El ejercicio pasó a «{ejercicio.get_estado_ejercicio_display().lower()}» mientras registrabas: revisá la fecha y volvé a confirmar.",
            campo="fecha",
        )


def resumir_asiento_manual(actor, fecha, descripcion, movimientos, *, hoy=None):
    """Paso 5 de CON-REG-ASI: las mismas validaciones que `registrar_asiento_manual` y el resumen, SIN escribir, auditar ni bloquear. Si el abierto
    venció y falta abrir el siguiente, no lo abre: calcula en memoria el ejercicio que se abriría (`ejercicios.destino_previsto`)."""
    hoy = hoy or timezone.localdate()
    _exigir_responsable(actor)
    descripcion, lineas, cuentas, omitidas = _validar_manual(descripcion, movimientos)
    destino = ejercicios.destino_previsto(fecha, hoy=hoy)
    filas = [
        LineaDeResumen(
            indice, codigo, cuentas[codigo].nombre_cuenta, cuentas[codigo].tipo_cuenta, cuentas[codigo].get_tipo_cuenta_display(), tipo, importe
        )
        for indice, codigo, tipo, importe in lineas
    ]
    debe = sum((f.importe for f in filas if f.tipo_movimiento == DEBE), Decimal("0.00"))
    haber = sum((f.importe for f in filas if f.tipo_movimiento == HABER), Decimal("0.00"))
    return ResumenDeAsiento(
        destino.numero, destino.inicio, destino.cierre, destino.estado, destino.por_abrir, filas, debe, haber, debe - haber, omitidas
    )


# --- CON-CTR-ASI: contraasiento (CON-03b) ------------------------------------------------------------------------------------------------------------

# El resumen previo del contraasiento (paso 4 de CON-CTR-ASI): el asiento a anular, el ejercicio destino (como en `ResumenDeAsiento`), las líneas ya
# invertidas, el total y si el asiento es automático (para advertir que el contraasiento no anula la operación de origen, C5).
ResumenDeContraasiento = namedtuple(
    "ResumenDeContraasiento",
    "asiento ejercicio_numero ejercicio_inicio ejercicio_cierre ejercicio_estado ejercicio_por_abrir lineas total es_automatico",
)


def _bloquear_asiento(asiento_id):
    """Bloquea el asiento a anular con `FOR NO KEY UPDATE` y devuelve la fila releída. Va ANTES que `_bloquear_ejercicio` (docs/patrones/asientos.md, sección 2)."""
    return AsientoContable.objects.select_for_update(no_key=True).get(pk=asiento_id)


def _validar_motivo(motivo):
    """El motivo es la descripción del contraasiento (extensión 3a, regla «Motivo»): obligatorio y de hasta 300 caracteres. Devuelve el texto recortado."""
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorContable("descripcion_obligatoria", "El motivo es obligatorio: contá por qué se anula el asiento.", campo="descripcion")
    if len(motivo) > LARGO_MAXIMO_DE_DESCRIPCION:
        mensaje = f"El motivo tiene {len(motivo)} caracteres y el máximo es {LARGO_MAXIMO_DE_DESCRIPCION}."
        raise ErrorContable("descripcion_muy_larga", mensaje, campo="descripcion")
    return motivo


def _leer_asiento(asiento_id):
    """El asiento sin bloquear, con su ejercicio y su origen; `Http404` si no existe."""
    try:
        return AsientoContable.objects.select_related("ejercicio", "origen").get(pk=asiento_id)
    except AsientoContable.DoesNotExist:
        raise Http404("No existe ese asiento.") from None


def _verificar_anulable(asiento):
    """Extensiones 1b y 6a (R161; regla 17 de 8.20): un contraasiento no se anula y un asiento se anula una sola vez. Con el asiento ya bloqueado esta
    es la verificación que cierra la carrera entre dos usuarios; antes de bloquear sirve para rechazar sin esperar."""
    if asiento.anula_id is not None:
        raise ErrorContable("asiento_no_anulable", "Un contraasiento no se puede anular: un asiento se anula una sola vez y su contraasiento queda como está.")
    existente = AsientoContable.objects.select_related("ejercicio").filter(anula_id=asiento.pk).first()
    if existente is not None:
        donde = f" ({existente.ejercicio})" if existente.ejercicio_id != asiento.ejercicio_id else ""
        raise ErrorContable(
            "asiento_no_anulable",
            f"Ese asiento ya fue anulado: su contraasiento es el N.º {existente.numero_asiento}{donde}.",
            datos={"contraasiento_ejercicio_id": existente.ejercicio_id, "contraasiento_numero": existente.numero_asiento},
        )


def _movimientos_del_asiento(asiento):
    """Los movimientos del asiento en orden de alta, con su cuenta."""
    return list(asiento.movimientos.select_related("cuenta").order_by("id"))


def _invertir(tipo):
    return HABER if tipo == DEBE else DEBE


def contraasentar(actor, asiento_id, fecha, descripcion, *, hoy=None):
    """CON-CTR-ASI: anula un asiento con un contraasiento y lo devuelve (docs/api/asientos.md; D-84 puntos 1, 2, 4, 5 y 9; D-42).

    ``descripcion`` es el motivo. Orden: (1) permisos (`PermissionDenied`); (2) motivo; (3) lee el asiento sin bloquear (`Http404`) y rechaza uno que no se
    puede anular; (4) en una transacción, autorrecuperación del ejercicio (H9) antes de validar la fecha (C2, C3) y de nuevo el permiso (D-30); (5) **bloquea
    el asiento a anular** y verifica de nuevo que se pueda anular (extensiones 1b y 6a); (6) **bloquea el ejercicio destino, lo último**, y revalida su estado
    y su rango (6b); (7) crea el contraasiento con los movimientos invertidos, vinculado al anulado, y audita; (8) avisa al Gerente dentro de la
    transacción (D-42), salvo que él sea quien registra; sin Gerente activo no falla y la auditoría lo deja anotado (7a)."""
    hoy = hoy or timezone.localdate()
    _exigir_responsable(actor)
    motivo = _validar_motivo(descripcion)
    _verificar_anulable(_leer_asiento(asiento_id))
    gerente = Gerente.objects.filter(is_active=True).first()
    with transaction.atomic():
        ejercicios.abrir_ejercicio_si_corresponde(hoy)
        destino = ejercicios.destino_del_asiento(fecha, automatico=False, hoy=hoy)
        _exigir_responsable(actor)
        asiento = _bloquear_asiento(asiento_id)
        _verificar_anulable(asiento)
        ejercicio = _bloquear_ejercicio(destino.ejercicio.pk)
        _exigir_que_la_fecha_siga_cayendo(ejercicio, fecha)
        movimientos = _movimientos_del_asiento(asiento)
        lineas = [(m.cuenta.codigo_cuenta, _invertir(m.tipo_movimiento), m.importe_movimiento) for m in movimientos]
        cuentas = {m.cuenta.codigo_cuenta: m.cuenta for m in movimientos}
        constancia = {"aviso_al_gerente": "no enviado: sin Gerente activo"} if gerente is None else None
        contraasiento = _crear_y_auditar(
            actor,
            ejercicio,
            fecha,
            motivo,
            lineas,
            cuentas,
            anula_id=asiento.pk,
            afectados=[asiento],
            cambios_extra={"anula": {"antes": None, "despues": referencia(asiento)}},
            datos=constancia,
        )
        notificaciones.notificar_a_varios(
            [gerente],
            f"Contraasiento N.º {contraasiento.numero_asiento} del asiento N.º {asiento.numero_asiento}",
            f"Lo registró {actor.get_full_name() or actor.email} el {fecha:%d/%m/%Y}. Motivo: {motivo}",
            excluir=actor,
        )
    return contraasiento


def resumir_contraasiento(actor, asiento_id, fecha, descripcion, *, hoy=None):
    """Paso 4 de CON-CTR-ASI: las mismas validaciones que `contraasentar` y el resumen, SIN escribir, auditar, avisar ni bloquear. Con el abierto vencido
    calcula en memoria el ejercicio que se abriría (`ejercicios.destino_previsto`)."""
    hoy = hoy or timezone.localdate()
    _exigir_responsable(actor)
    _validar_motivo(descripcion)
    asiento = _leer_asiento(asiento_id)
    _verificar_anulable(asiento)
    destino = ejercicios.destino_previsto(fecha, hoy=hoy)
    lineas = [
        LineaDeResumen(
            indice, m.cuenta.codigo_cuenta, m.cuenta.nombre_cuenta, m.cuenta.tipo_cuenta, m.cuenta.get_tipo_cuenta_display(), _invertir(m.tipo_movimiento), m.importe_movimiento
        )
        for indice, m in enumerate(_movimientos_del_asiento(asiento))
    ]
    total = sum((l.importe for l in lineas if l.tipo_movimiento == DEBE), Decimal("0.00"))
    return ResumenDeContraasiento(
        asiento, destino.numero, destino.inicio, destino.cierre, destino.estado, destino.por_abrir, lineas, total, asiento.origen_id is not None
    )


def datos_para_correccion(actor, asiento_id):
    """La precarga del asiento correcto (C4; CON-REG-ASI extensión 1b): `{"descripcion", "movimientos", "numero_anulado"}` con las líneas del asiento
    ANULADO (no las invertidas) y «corrección del asiento N.º X». Si se pasa el contraasiento, usa el asiento que anuló. No escribe: el asiento correcto es
    un manual común que se registra con `registrar_asiento_manual`, sin vínculo con el contraasiento."""
    _exigir_responsable(actor)
    asiento = _leer_asiento(asiento_id)
    if asiento.anula_id is not None:
        asiento = _leer_asiento(asiento.anula_id)
    movimientos = [(m.cuenta.codigo_cuenta, m.tipo_movimiento, m.importe_movimiento) for m in _movimientos_del_asiento(asiento)]
    return {
        "descripcion": f"corrección del asiento N.º {asiento.numero_asiento}",
        "movimientos": movimientos,
        "numero_anulado": asiento.numero_asiento,
    }
