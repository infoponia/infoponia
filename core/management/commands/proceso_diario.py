# Comando ``proceso_diario`` (DIA-01, D-56): corre a mano los pasos diarios registrados en ``core/procesos.py``. No tiene
# lógica propia: valida las opciones, llama a ``correr_proceso_diario`` e imprime. Es el «cron job sin cron job»: el cron
# único que se arme al final de la implementación ejecutará exactamente este comando.

import datetime
import sys

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core import procesos


def _leer_fecha(texto):
    """Convierte ``AAAA-MM-DD`` en ``date``. Rechaza fechas imposibles (2026-13-01) y formatos sin ceros (2026-1-5):
    ``strptime`` acepta estos últimos, por eso se compara con ``isoformat()``."""
    try:
        fecha = datetime.datetime.strptime(texto, "%Y-%m-%d").date()
    except ValueError:
        fecha = None
    if fecha is None or fecha.isoformat() != texto:
        raise CommandError(f"Fecha inválida: «{texto}». Usá el formato AAAA-MM-DD, por ejemplo 2026-12-15.")
    return fecha


class Command(BaseCommand):
    """Corre el proceso diario: todos los pasos registrados, en orden (D-56).

    Uso en la máquina local (PowerShell, con el entorno virtual activo):

        python manage.py proceso_diario --listar
        python manage.py proceso_diario
        python manage.py proceso_diario --fecha 2026-12-15
        python manage.py proceso_diario --solo revisar_vencimientos

    En Render también se puede correr a mano desde la «Shell» del web service, sin crear ningún cron job.
    Termina con código 0 si todos los pasos salieron bien y con 1 si alguno falló (los demás igual corren).
    """

    help = "Corre a mano los pasos del proceso diario, en orden (D-56). Opciones: --fecha, --solo, --listar."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Simula ese día (AAAA-MM-DD) en lugar de hoy.")
        parser.add_argument("--solo", metavar="CODIGO", help="Corre solo el paso con ese código.")
        parser.add_argument("--listar", action="store_true", help="Muestra los pasos en orden, sin correr nada.")

    def handle(self, *args, **opciones):
        # La fecha se valida primero: un error de uso no debe correr ni listar nada.
        # Se lee una sola vez y se pasa a los pasos: el encabezado y los pasos ven el mismo día.
        hoy = _leer_fecha(opciones["fecha"]) if opciones["fecha"] else timezone.localdate()

        if opciones["listar"]:
            return self._listar()

        if not procesos.pasos_diarios():
            self.stdout.write("No hay pasos registrados.")
            return

        try:
            resultados = procesos.correr_proceso_diario(hoy=hoy, solo=opciones["solo"])
        except ValueError as error:  # ``--solo`` con un código que no existe
            raise CommandError(str(error)) from error

        self.stdout.write(f"Proceso diario del {hoy.isoformat()}.")
        fallidos = []
        for paso, resumen, error in resultados:
            if error is not None:
                fallidos.append(paso)
                self.stdout.write(f"{paso.nombre}: FALLÓ: {type(error).__name__}: {error}")
                continue
            linea = (
                f"{paso.nombre}: procesados {resumen.procesados} · creados {resumen.creados} · "
                f"resueltos {resumen.resueltos}"
            )
            if resumen.detalle:
                linea += f" · {resumen.detalle}"
            self.stdout.write(linea)

        correctos = len(resultados) - len(fallidos)
        self.stdout.write(f"Pasos correctos: {correctos} · fallidos: {len(fallidos)}.")
        if fallidos:
            # Código de salida 1: así el cron del futuro marca la corrida como fallida (D-56, punto 5).
            raise CommandError(
                f"Fallaron {len(fallidos)} de {len(resultados)} pasos: {', '.join(p.codigo for p in fallidos)}."
            )

    def _listar(self):
        """Muestra ``orden · codigo · nombre`` por paso, o «No hay pasos registrados.»"""
        pasos = procesos.pasos_diarios()
        if not pasos:
            self.stdout.write("No hay pasos registrados.")
            return
        for paso in pasos:
            self.stdout.write(f"{paso.orden} · {paso.codigo} · {paso.nombre}")
