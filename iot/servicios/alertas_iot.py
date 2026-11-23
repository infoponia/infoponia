# Ayudantes de las alertas del IoT (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md, «Servicios», `alertas_iot.py`; D-72, punto 4). Llaman a
# ``maestros.servicios.alertas`` (que bloquea el invernadero, reentrante) y dejan el ``AlertaIot`` de cada alerta: el sistema y su origen (R052 hardware o
# R053 telemetría). Los usan la API del nodo (lecturas, estados) y ``recalcular_compatibilidad`` (IOT-02): una sola forma de crear un ``AlertaIot``.
#
# Orden de bloqueos (docs/api/alertas.md, sección 3): quien llama ya bloqueó el invernadero antes de sus propias filas; estas funciones lo vuelven a
# pedir sin esperar (``bloquear_invernadero_para_alertas`` es reentrante) y bloquean después la alerta.

from collections import namedtuple
from urllib.parse import quote

from django.db.models.functions import Lower
from django.urls import reverse

from maestros.extensiones import Enlace
from maestros.models import Alerta
from maestros.servicios import alertas as api_alertas

from iot.alcance import invernaderos_que_opera
from iot.models import AlertaIot, Hardware

# ``alerta`` es la alerta activa (``None`` si el invernadero está inactivo: no se crea nada y no es un error) y ``creada`` dice si esta llamada la creó.
ResultadoDeAlerta = namedtuple("ResultadoDeAlerta", "alerta creada")
TIPO_NO_REGISTRADO = "iot_dispositivo_no_registrado"
TIPO_NODO_SIN_COMUNICACION = "iot_nodo_sin_comunicacion"


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


# ---- los enlaces de las alertas del IoT (IOT-04, paso 5; D-62; docs/casos_de_uso/iot/consultar_lecturas.md, «Enlaces de las alertas del IoT») ----


def bajas_por_identificador(sistema_ids, identificadores):
    """``{(sistema_id, identificador en minúsculas): Hardware}``: el último equipo DADO DE BAJA de cada sistema que tenía ese identificador, solo si ningún equipo vigente lo usa
    hoy (regla 12 de IOT-ALT-HDW). UNA consulta para toda la lista (con el ``Sensor`` y el ``Actuador`` cargados, para nombrarlo). Los usan el enlace de «dispositivo no
    registrado» y el panel de monitoreo."""
    minusculas = {i.lower() for i in identificadores}
    if not minusculas:
        return {}
    equipos = (
        Hardware.objects.filter(sistema_id__in=sistema_ids)
        .annotate(_minuscula=Lower("identificador_equipo"))
        .filter(_minuscula__in=minusculas)
        .select_related("sensor", "actuador__tipo_actuador")
        .order_by("pk")
    )
    bajas, en_uso = {}, set()
    for equipo in equipos:
        clave = (equipo.sistema_id, equipo._minuscula)
        if equipo.estado_hardware == "inactivo":
            bajas[clave] = equipo
        else:
            en_uso.add(clave)
    return {clave: equipo for clave, equipo in bajas.items() if clave not in en_uso}


def nombre_de_equipo_de_baja(equipo):
    """El nombre con que se nombra un equipo en «{identificador} era de {equipo}»: la variable del sensor o el tipo del actuador (``hwName`` del prototipo)."""
    if equipo.clase == "sensor":
        return equipo.sensor.get_tipo_variable_sensor_display()
    return equipo.actuador.tipo_actuador.nombre_actuador


def enlaces_de_alertas_iot(usuario, alertas):
    """Registrante de ``maestros.extensiones.registrar_enlace_de_alerta`` para las alertas del IoT (IOT-04, D-62): ``{id de alerta: Enlace(url, detalle)}`` con UNA consulta
    por clase de dato, nunca una por alerta (lista vacía: ``{}`` sin consultar). Nunca un enlace a un 403: Agrónomo y Gerente consultan todo lo del módulo en su alcance.

    - Con equipo (R052) o con lectura (R053, su sensor): la ficha del equipo; el detalle, la descripción de la alerta.
    - «Nodo sin comunicación»: el panel (``iot:monitoreo``) del invernadero.
    - «Dispositivo no registrado» de un identificador que era de un equipo dado de baja: la ficha de ese equipo (que ofrece «Reactivar») y «{id} era de {equipo}, dado de
      baja el DD/MM». De otro identificador: el alta con ``?identificador=`` a quien opera el IoT del invernadero y el panel a quien solo consulta."""
    alertas = list(alertas)
    if not alertas:
        return {}
    vinculos = {v.alerta_id: v for v in AlertaIot.objects.filter(alerta__in=alertas).select_related("telemetria")}
    no_registradas = {a.pk: a.clave_estado.removeprefix("id:") for a in alertas if a.tipo_alerta == TIPO_NO_REGISTRADO and a.pk in vinculos}
    bajas, operados = {}, set()
    if no_registradas:
        sistemas = {v.sistema_id for pk, v in vinculos.items() if pk in no_registradas}
        bajas = bajas_por_identificador(sistemas, no_registradas.values())
        operados = set(invernaderos_que_opera(usuario).filter(pk__in={a.invernadero_id for a in alertas}).values_list("pk", flat=True))
    enlaces = {}
    for alerta in alertas:
        vinculo = vinculos.get(alerta.pk)
        if vinculo is None:
            continue
        panel = f"{reverse('iot:monitoreo')}?invernadero={alerta.invernadero_id}"
        equipo_id = vinculo.hardware_id or (vinculo.telemetria.sensor_id if vinculo.telemetria is not None else None)
        if equipo_id is not None:
            enlaces[alerta.pk] = Enlace(f"{reverse('iot:hardware_ficha', args=[equipo_id])}?invernadero={alerta.invernadero_id}", alerta.descripcion_alerta)
        elif alerta.tipo_alerta == TIPO_NODO_SIN_COMUNICACION:
            enlaces[alerta.pk] = Enlace(panel, alerta.descripcion_alerta)
        elif alerta.pk in no_registradas:
            identificador = no_registradas[alerta.pk]
            baja = bajas.get((vinculo.sistema_id, identificador.lower()))
            if baja is not None:
                fecha = f", dado de baja el {baja.fecha_baja:%d/%m}" if baja.fecha_baja else ", dado de baja"
                detalle = f"{baja.identificador_equipo} era de {nombre_de_equipo_de_baja(baja)}{fecha}"
                enlaces[alerta.pk] = Enlace(f"{reverse('iot:hardware_ficha', args=[baja.pk])}?invernadero={alerta.invernadero_id}", detalle)
            elif alerta.invernadero_id in operados:
                alta = f"{reverse('iot:hardware_nuevo')}?invernadero={alerta.invernadero_id}&identificador={quote(identificador, safe='')}"
                enlaces[alerta.pk] = Enlace(alta, alerta.descripcion_alerta)
            else:
                enlaces[alerta.pk] = Enlace(panel, alerta.descripcion_alerta)
    return enlaces
