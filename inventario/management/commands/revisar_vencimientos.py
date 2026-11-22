# Comando ``revisar_vencimientos`` (CMP-REV-VNC, INV-02, paso 7; D-56): sin lógica propia. Valida ``--fecha``, llama a
# ``inventario.servicios.vencimientos.revisar_vencimientos`` (la misma función que usa el paso 10 del proceso diario), imprime el resumen y,
# si hubo fallas, termina con ``CommandError`` (código de salida distinto de cero, para que Render marque la corrida como fallida).

from django.core.management.base import BaseCommand, CommandError

from core.management.commands.proceso_diario import _leer_fecha
from inventario.servicios import vencimientos


class Command(BaseCommand):
    """Revisa los vencimientos de insumos de todos los invernaderos activos.

    Uso (PowerShell, con el entorno virtual activo):
        python manage.py revisar_vencimientos
        python manage.py revisar_vencimientos --fecha 2026-12-15   (simula ese día)
    """

    help = "Revisa los vencimientos de insumos y genera o resuelve sus alertas (CMP-REV-VNC). Opción: --fecha."

    def add_arguments(self, parser):
        parser.add_argument("--fecha", help="Simula ese día (AAAA-MM-DD) en lugar de hoy.")

    def handle(self, *args, **opciones):
        # La fecha se valida primero: un error de uso no debe correr nada.
        hoy = _leer_fecha(opciones["fecha"]) if opciones["fecha"] else None
        resultado = vencimientos.revisar_vencimientos(hoy=hoy)
        self.stdout.write(f"Invernaderos revisados: {resultado.revisados}")
        self.stdout.write(f"Alertas creadas: {len(resultado.creadas)}")
        self.stdout.write(f"Alertas resueltas: {len(resultado.resueltas)}")
        if resultado.fallas:
            detalle = "; ".join(f"invernadero {id_}: {error}" for id_, error in resultado.fallas)
            raise CommandError(f"Fallaron {len(resultado.fallas)} invernadero(s): {detalle}")
