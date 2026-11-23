# El reloj de la API (docs/casos_de_uso/iot/entregar_informacion.md, «La API», `reloj.py`). Las vistas llaman a ``ahora()`` UNA vez por pedido y
# pasan ese valor a los servicios, que nunca leen la hora por su cuenta: así las pruebas la reemplazan con ``unittest.mock.patch`` en un solo lugar.

from django.utils import timezone


def ahora():
    """La hora actual con zona (``timezone.now()``). Las pruebas la parchean: ``mock.patch("iot.api.reloj.ahora", return_value=...)``."""
    return timezone.now()
