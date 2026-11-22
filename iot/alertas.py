# Los 11 tipos de alerta del IoT (docs/modelo/iot.md, «Tipos de alerta del IoT», MD-108 y MD-109; docs/api/alertas.md, sección 1).
# Todos van al Agrónomo del invernadero o, sin Agrónomo activo, al Gerente, y son de clase ESTADO (a lo sumo una activa por
# invernadero, tipo y clave; se resuelven solas, nunca a mano). Los registra ``IotConfig.ready()`` (regla A4 de D-37).
# La clave de cada alerta (``sensor:<id>``, ``hw:<id>``, ``id:<identificador>``, ``nodo:<id>``) la arma quien la crea (IOT-03 en adelante).

from maestros.alertas import Clase, Destinatario, Origen, TipoAlerta, registrar_tipo_de_alerta
from maestros.models import Alerta

# (código, nombre visible, severidad, origen). El fotoperíodo usa un código propio porque su origen es el sensor y no una
# lectura: un ``TipoAlerta`` tiene un solo origen.
TIPOS_DE_ALERTA_DE_IOT = (
    ("iot_fuera_de_umbral", "Fuera de umbral efectivo", Alerta.Severidad.ADVERTENCIA, Origen.TELEMETRIA),
    ("iot_fotoperiodo_fuera_de_umbral", "Fuera de umbral efectivo (fotoperíodo)", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_solucion_fuera_de_rango", "Solución fuera de rango", Alerta.Severidad.ADVERTENCIA, Origen.TELEMETRIA),
    ("iot_nivel_solucion_bajo", "Nivel de solución bajo", Alerta.Severidad.CRITICA, Origen.TELEMETRIA),
    ("iot_lectura_invalida", "Lectura inválida", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_sin_actividad", "Dispositivo sin actividad", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_en_falla", "Dispositivo en falla", Alerta.Severidad.CRITICA, Origen.HARDWARE),
    ("iot_comando_fallido", "Comando fallido", Alerta.Severidad.CRITICA, Origen.HARDWARE),
    ("iot_configuracion_incompatible", "Configuración incompatible", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_no_registrado", "Dispositivo no registrado", Alerta.Severidad.INFORMATIVA, None),
    ("iot_nodo_sin_comunicacion", "Nodo sin comunicación", Alerta.Severidad.CRITICA, None),
)


def registrar_tipos_de_iot():
    """Registra los 11 tipos de alerta del IoT en ``maestros.alertas``. Idempotente: ``ready()`` puede correr más de una vez."""
    for codigo, nombre, severidad, origen in TIPOS_DE_ALERTA_DE_IOT:
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=codigo,
                nombre=nombre,
                destinatario=Destinatario.AGRONOMO_O_GERENTE,
                severidad=severidad,
                clase=Clase.ESTADO,
                origen=origen,
            )
        )
