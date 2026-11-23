# Ayudantes de las alertas del IoT (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md, «Servicios», `alertas_iot.py`; D-72, punto 4). Llaman a
# ``maestros.servicios.alertas`` (que bloquea el invernadero, reentrante) y dejan el ``AlertaIot`` de cada alerta: el sistema y su origen (R052 hardware o
# R053 telemetría). Los usan la API del nodo (lecturas, estados) y ``recalcular_compatibilidad`` (IOT-02): una sola forma de crear un ``AlertaIot``.
#
# Orden de bloqueos (docs/api/alertas.md, sección 3): quien llama ya bloqueó el invernadero antes de sus propias filas; estas funciones lo vuelven a
# pedir sin esperar (``bloquear_invernadero_para_alertas`` es reentrante) y bloquean después la alerta.

from collections import namedtuple

from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas

from iot.models import AlertaIot

# ``alerta`` es la alerta activa (``None`` si el invernadero está inactivo: no se crea nada y no es un error) y ``creada`` dice si esta llamada la creó.
ResultadoDeAlerta = namedtuple("ResultadoDeAlerta", "alerta creada")


def asegurar_alerta_iot(invernadero_id, sistema, tipo, clave, descripcion, hardware=None, telemetria=None):
    """Idempotente: devuelve la alerta de estado ACTIVA de ese invernadero, tipo y ``clave`` y, si no había, la crea con ``descripcion`` (que no se actualiza
    mientras siga activa). Deja su ``AlertaIot`` con el ``sistema`` y el origen (``hardware`` o ``telemetria``, a lo sumo uno); nunca crea un segundo
    ``AlertaIot`` para la misma alerta (es ``OneToOne``): ``get_or_create``, igual que ``recalcular_compatibilidad`` de IOT-02. Con el invernadero
    inactivo no crea nada. Corre dentro de la transacción de quien llama."""
    ya_estaba = Alerta.objects.filter(
        invernadero_id=invernadero_id, tipo_alerta=tipo, clave_estado=clave, estado_alerta=Alerta.Estado.ACTIVA
    ).exists()
    alerta = api_alertas.asegurar_alerta_de_estado(invernadero_id, tipo, clave, descripcion)
    if alerta is None:
        return ResultadoDeAlerta(None, False)
    AlertaIot.objects.get_or_create(alerta=alerta, defaults={"sistema": sistema, "hardware": hardware, "telemetria": telemetria})
    return ResultadoDeAlerta(alerta, not ya_estaba)


def resolver_alerta_iot(invernadero_id, tipo, clave):
    """Pasa a «resuelta» la alerta activa de ese invernadero, tipo y ``clave`` y la devuelve; ``None`` si no había. Su ``AlertaIot`` se conserva."""
    return api_alertas.resolver_alerta_de_estado(invernadero_id, tipo, clave)
