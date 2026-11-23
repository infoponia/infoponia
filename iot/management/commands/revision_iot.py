# Comando ``revision_iot`` (IOT-04, D-71): corre a mano la revisión periódica del IoT (extensión *b de IOT-ENT-INF). No tiene lógica propia: valida las opciones, llama a
# ``revision.revisar(ahora)`` por el módulo, imprime y, si algún sistema falló, termina con código 1 (``CommandError``), como ``proceso_diario`` (D-56). Es el «cron job sin
# cron job»: el cron del IoT, cuando se arme (disparador «Cuando se arme el cron único»), ejecutará este mismo comando.

import re
import time
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from iot.servicios import revision

FORMATO_DE_AHORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
SEGUNDOS_MINIMOS = 10


def _leer_ahora(texto):
    """Convierte ``AAAA-MM-DDTHH:MM`` (hora local del proyecto) en un ``datetime`` con zona; cualquier otro formato o una fecha imposible es ``CommandError``."""
    try:
        if not FORMATO_DE_AHORA.match(texto):
            raise ValueError
        return timezone.make_aware(datetime.strptime(texto, "%Y-%m-%dT%H:%M"))
    except ValueError:
        raise CommandError(f"Hora inválida: «{texto}». Usá el formato AAAA-MM-DDTHH:MM, por ejemplo 2026-11-23T12:00.") from None


def _n(cantidad, singular, plural):
    """«1 alerta generada» o «2 alertas generadas»."""
    return f"{cantidad} {singular if cantidad == 1 else plural}"


class Command(BaseCommand):
    """Corre la revisión periódica del IoT (D-71): sensores sin actividad, nodos sin comunicación, resúmenes, fotoperíodo, retención y correos.

    Uso en la máquina local (PowerShell, con el entorno virtual activo):

        python manage.py revision_iot
        python manage.py revision_iot --ahora 2026-11-23T12:00
        python manage.py revision_iot --cada 60

    Termina con código 0 si ningún sistema falló y con 1 si alguno falló (los demás igual se revisan)."""

    help = "Corre la revisión periódica del IoT (D-71). Opciones: --ahora, --cada."

    def add_arguments(self, parser):
        parser.add_argument("--ahora", help="Simula esa hora local (AAAA-MM-DDTHH:MM) en lugar de la actual.")
        parser.add_argument("--cada", type=int, metavar="N", help="Repite cada N segundos (N >= 10) hasta Ctrl+C. Útil para probar con Node-RED.")

    def handle(self, *args, **opciones):
        # Las opciones se validan primero: un error de uso no corre nada.
        fija = _leer_ahora(opciones["ahora"]) if opciones["ahora"] is not None else None
        cada = opciones["cada"]
        if cada is not None and cada < SEGUNDOS_MINIMOS:
            raise CommandError(f"--cada tiene que ser de {SEGUNDOS_MINIMOS} segundos o más.")
        if cada is None:
            self._una_vez(fija)
            return
        try:
            while True:
                self._una_vez(fija)
                time.sleep(cada)
        except KeyboardInterrupt:
            self.stdout.write("Revisión detenida.")

    def _una_vez(self, fija):
        """Una corrida: la hora usada, una línea por sistema y la de los correos. Si algún sistema falló, ``CommandError`` (después de imprimir todo)."""
        ahora = fija or timezone.now()
        resumen = revision.revisar(ahora)
        self.stdout.write(f"Revisión periódica del IoT: {timezone.localtime(ahora):%d/%m/%Y %H:%M}.")
        if not resumen.sistemas:
            self.stdout.write("No hay sistemas IoT activos.")
        for r in resumen.sistemas:
            nombre = r.sistema.invernadero.nombre_invernadero
            if r.error:
                self.stdout.write(f"{nombre}: FALLÓ: {r.error}")
                continue
            self.stdout.write(
                f"{nombre}: {_n(r.alertas_generadas, 'alerta generada', 'alertas generadas')} · {_n(r.alertas_resueltas, 'resuelta', 'resueltas')} · "
                f"{_n(r.resumenes, 'resumen', 'resúmenes')} · {_n(r.fotoperiodos, 'fotoperíodo', 'fotoperíodos')} · "
                f"{_n(r.lecturas_borradas, 'lectura borrada', 'lecturas borradas')}"
            )
        c = resumen.correos
        self.stdout.write(
            f"Correos: {_n(c.enviados, 'enviado', 'enviados')} · {_n(c.fallidos, 'fallido', 'fallidos')} · "
            f"{_n(c.pendientes_sin_servidor, 'pendiente', 'pendientes')} sin servidor de correo"
        )
        if resumen.hubo_fallos:
            fallidos = [r for r in resumen.sistemas if r.error]
            raise CommandError(f"Fallaron {len(fallidos)} de {len(resumen.sistemas)} sistemas.")
