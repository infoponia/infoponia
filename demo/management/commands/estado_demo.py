# Comando ``estado_demo`` (DAT-02, paso 4; decisión de la demo, hoy ``docs/decisiones/D-01-demo.md``): SOLO LECTURA. Dice si la demo está lista
# para el guion de la defensa: las fechas, las escenas, las piezas del repo y las cuentas. Pasa por el mismo doble candado que ``cargar_demo``
# (``INFOPONIA_DEMO=1`` y la base ``infoponia_demo``), pero NO exige que la base esté vacía ni los secretos. Nunca imprime la contraseña ni el token.

from django.core.management.base import BaseCommand
from django.utils import timezone

from demo import candado, estado


class Command(BaseCommand):
    """Muestra el estado de la demo.

    Uso (Shell del servicio demo de Render, con ``INFOPONIA_DEMO=1``):

        python manage.py estado_demo
    """

    help = "Muestra qué escenas del guion de la demo están listas y qué piezas del repo están (solo lectura)."

    def handle(self, *args, **opciones):
        candado.verificar_candado()
        for linea in estado.armar_informe(timezone.localdate()):
            self.stdout.write(linea)
