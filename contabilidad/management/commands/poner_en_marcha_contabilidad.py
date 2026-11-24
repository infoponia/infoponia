# Comando ``poner_en_marcha_contabilidad`` (CON-ABR-EJE, D-84 punto 3): crea el primer ejercicio contable. Idempotente: si ya hay uno, no
# hace nada y lo dice. Sin lógica propia: valida la fecha, llama a ``crear_primer_ejercicio`` e imprime.

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from contabilidad.errores import ErrorContable
from contabilidad.models import EjercicioContable
from contabilidad.servicios import ejercicios
from core.management.commands.proceso_diario import _leer_fecha


class Command(BaseCommand):
    """Pone en marcha la contabilidad.

    Uso (PowerShell, con el entorno virtual activo):

        python manage.py poner_en_marcha_contabilidad
        python manage.py poner_en_marcha_contabilidad --fecha-inicio 2026-11-01
    """

    help = "Crea el primer ejercicio contable (empieza hoy o en --fecha-inicio). Si ya hay un ejercicio, no hace nada."

    def add_arguments(self, parser):
        parser.add_argument("--fecha-inicio", help="Día en que empieza el primer ejercicio (AAAA-MM-DD); por defecto hoy.")

    def handle(self, *args, **opciones):
        hoy = timezone.localdate()
        inicio = _leer_fecha(opciones["fecha_inicio"]) if opciones["fecha_inicio"] else hoy
        if inicio > hoy:
            raise CommandError("La fecha de inicio no puede ser futura.")
        previo = EjercicioContable.objects.order_by("fecha_inicio_ejercicio", "id").first()
        if previo is not None:
            self.stdout.write(f"Ya existe un ejercicio contable ({previo}): no se hizo nada.")
            return
        try:
            primero = ejercicios.crear_primer_ejercicio(inicio, hoy=hoy)
        except ErrorContable as error:
            raise CommandError(error.mensaje) from error
        self.stdout.write(
            f"Primer ejercicio creado: del {primero.fecha_inicio_ejercicio:%d/%m/%Y} al {primero.fecha_cierre_ejercicio:%d/%m/%Y}."
        )
