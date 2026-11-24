# Asientos automáticos (D-86, D-84 puntos 4, 5, 6 y 9): `registrar_asiento_automatico`, la única puerta por la que las demás apps asientan.
# Corre dentro de la transacción de quien llama, con sus bloqueos ya tomados. EL EJERCICIO SE BLOQUEA AL FINAL (`_bloquear_ejercicio`, D-86
# punto 2, docs/patrones/asientos.md sección 2): es lo último que cualquier servicio bloquea, para no cruzar el orden de D-30 y D-32.
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from contabilidad.constantes import DEBE, HABER
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable, CuentaContable, EjercicioContable, MovimientoContable
from contabilidad.servicios import ejercicios
from core.models import RegistroAuditoria, referencia

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

        numero = ejercicio.ultimo_numero_asiento + 1  # D-84 punto 4: leído DESPUÉS de bloquear
        ejercicio.ultimo_numero_asiento = numero
        ejercicio.save(update_fields=["ultimo_numero_asiento"])
        try:
            with transaction.atomic():
                asiento = AsientoContable.objects.create(
                    ejercicio=ejercicio,
                    numero_asiento=numero,
                    fecha_asiento=fecha_asiento,
                    descripcion_asiento=descripcion,
                    origen_id=origen.pk,
                )
        except IntegrityError as error:
            if AsientoContable.objects.filter(origen_id=origen.pk).exists():
                raise ErrorContable("origen_con_asiento", f"El documento de origen ({origen}) ya tiene su asiento contable.") from error
            raise
        creados = MovimientoContable.objects.bulk_create(
            [
                MovimientoContable(asiento=asiento, cuenta=cuentas[codigo], tipo_movimiento=tipo, importe_movimiento=importe)
                for codigo, tipo, importe in lineas
            ]
        )

        # D-84 punto 9 y D-36: un registro por el asiento y uno por cada movimiento; fechas en ISO e importes como texto.
        RegistroAuditoria.objects.registrar(
            actor,
            Accion.ALTA_ASIENTO_CONTABLE,
            [asiento, origen],
            {
                "cambios": {
                    "numero_asiento": {"antes": None, "despues": numero},
                    "fecha_asiento": {"antes": None, "despues": fecha_asiento.isoformat()},
                    "descripcion_asiento": {"antes": None, "despues": descripcion},
                    "ejercicio": {"antes": None, "despues": referencia(ejercicio)},
                    "origen": {"antes": None, "despues": referencia(origen)},
                }
            },
        )
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
