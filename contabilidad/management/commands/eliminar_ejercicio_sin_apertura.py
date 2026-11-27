# Comando de USO ÚNICO ``eliminar_ejercicio_sin_apertura`` (tarea CON-05, paso 6; decisión «Puesta en marcha contable», punto 4): borra el ejercicio que creó la puesta en marcha automática
# (D-84 punto 3, retirada) en producción el 26/11/2026, que quedó sin asientos y sin capital inicial. Después, la contabilidad se inicia desde «Iniciar ejercicio» (CON-INI-EJE).
# Sin opciones NO escribe nada: dice qué borraría o por qué no puede. Con ``--confirmar`` hace todo en una transacción: bloquea los ejercicios, verifica con los datos bloqueados, audita
# ``baja_ejercicio_contable`` (actor ``None``: InfoPonia) y borra. Se retira en una tarea posterior.
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contabilidad.models import AsientoContable, EjercicioContable
from core.models import RegistroAuditoria

MOTIVO = "puesta en marcha automática reemplazada por CON-INI-EJE"


def _por_que_no(ejercicios):
    """El motivo por el que NO se puede borrar (texto) o `None` si se puede. Condiciones: exactamente un ejercicio, «abierto», con `ultimo_numero_asiento == 0` y sin asientos
    (se mira `AsientoContable` y no solo el número: no depende del `PROTECT` de la base, que igual respalda)."""
    if not ejercicios:
        return "No hay ningún ejercicio contable: no hay nada que borrar."
    if len(ejercicios) > 1:
        return f"Hay más de un ejercicio contable ({len(ejercicios)}): este comando solo borra el único ejercicio de la puesta en marcha automática."
    ejercicio = ejercicios[0]
    if ejercicio.estado_ejercicio != EjercicioContable.Estado.ABIERTO:
        return f"El ejercicio no está «abierto» (está «{ejercicio.get_estado_ejercicio_display()}»)."
    if ejercicio.ultimo_numero_asiento != 0:
        return f"El ejercicio ya tomó el número de asiento {ejercicio.ultimo_numero_asiento}: no es el de la puesta en marcha automática."
    if AsientoContable.objects.filter(ejercicio=ejercicio).exists():
        return "El ejercicio tiene asientos (y sus movimientos): no se puede borrar."
    return None


class Command(BaseCommand):
    """Borra el ejercicio sin apertura de la puesta en marcha automática. ADVERTENCIA: es de un solo uso y se retira en una tarea posterior.

    Uso (PowerShell, con el entorno virtual activo y, para producción, ``DATABASE_URL`` solo en esa ventana; lo corre el estudiante, nunca Claude Code):

        python manage.py eliminar_ejercicio_sin_apertura               # simula: no escribe nada
        python manage.py eliminar_ejercicio_sin_apertura --confirmar   # borra y audita
    """

    help = "Uso único: borra el ejercicio contable sin asientos de la puesta en marcha automática. Sin opciones solo muestra qué borraría."

    def add_arguments(self, parser):
        parser.add_argument("--confirmar", action="store_true", help="Borra de verdad (sin esto, solo simula).")

    def handle(self, *args, **opciones):
        if not opciones["confirmar"]:
            ejercicios = list(EjercicioContable.objects.order_by("id"))
            motivo = _por_que_no(ejercicios)
            if motivo:
                self.stdout.write(f"No se puede borrar: {motivo} (no se escribió nada).")
            else:
                e = ejercicios[0]
                self.stdout.write(
                    f"Se borraría el ejercicio {e} (del {e.fecha_inicio_ejercicio:%d/%m/%Y} al {e.fecha_cierre_ejercicio:%d/%m/%Y}, sin asientos). "
                    "Para hacerlo, corré el comando con --confirmar."
                )
            return
        with transaction.atomic():
            # Bloquea TODOS los ejercicios antes de verificar: lo verificado vale hasta el final de la transacción (docs/patrones/bloqueos.md).
            ejercicios = list(EjercicioContable.objects.select_for_update(no_key=True).order_by("id"))
            motivo = _por_que_no(ejercicios)
            if motivo:
                raise CommandError(f"No se borró nada. {motivo}")
            ejercicio = ejercicios[0]
            texto = f"{ejercicio}"
            RegistroAuditoria.objects.registrar(
                None,
                RegistroAuditoria.Accion.BAJA_EJERCICIO_CONTABLE,
                [ejercicio],
                {
                    "cambios": {
                        "fecha_inicio_ejercicio": {"antes": ejercicio.fecha_inicio_ejercicio.isoformat(), "despues": None},
                        "fecha_cierre_ejercicio": {"antes": ejercicio.fecha_cierre_ejercicio.isoformat(), "despues": None},
                        "estado_ejercicio": {"antes": ejercicio.estado_ejercicio, "despues": None},
                    },
                    "datos": {"motivo": MOTIVO},
                },
            )
            ejercicio.delete()
        self.stdout.write(f"Ejercicio {texto} eliminado. La contabilidad queda sin iniciar: usá «Iniciar ejercicio».")
