# API de alertas de maestros (MAE-02a, D-41; docs/api/alertas.md). Todo corre dentro de la transacción de quien llama, que
# audita en los ``datos`` de su caso de uso lo que esta API devuelve (D-36, D-41). Orden de bloqueos (D-40, ampliado): las
# cuentas, el invernadero, las alertas de ese invernadero (en orden de id) y recién después las filas de las apps altas.
# El invernadero bloqueado es el candado de sus alertas: quien crea o resuelve una alerta lo bloquea ANTES (si no, la baja
# del invernadero, cuyo UPDATE no ve una fila sin confirmar, deja una alerta activa en un invernadero inactivo).

from collections import namedtuple

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from maestros.alertas import (
    Destinatario,
    TipoAlerta,
    Clase,
    codigos_con_destinatario,
    registrar_tipo_de_alerta,
    tipo_de_alerta,
)
from maestros.models import Alerta, Invernadero

# Lo que hizo ``sincronizar_alertas_de_personal``: listas de ``Alerta``.
Cambios = namedtuple("Cambios", "creadas resueltas")

# Texto de la entrada de la regla 2 de PROD-MOD-INV.
LARGO_DESCRIPCION = Alerta._meta.get_field("descripcion_alerta").max_length


def registrar_tipos_de_personal():
    """Registra los cuatro tipos «invernadero sin {rol} activo» (regla 3 de 8.22; D11 de MAE-02: destinatario ``GERENTE``,
    porque esa regla es la específica de estos cuatro tipos y la regla 4, la general). Son de estado: a lo sumo una activa
    por invernadero y tipo. Idempotente (``ready()`` puede correr más de una vez)."""
    for atributo, nombre in Invernadero.ROLES:
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=f"sin_{atributo}",
                nombre=f"Invernadero sin {nombre} activo",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.ESTADO,
            )
        )


def bloquear_invernadero_para_alertas(invernadero_id):
    """Bloquea el invernadero (``FOR NO KEY UPDATE``), lo lee de nuevo y lo devuelve, esté activo o no (a diferencia de
    ``bloquear_invernadero_activo``, que rechaza uno inactivo: la post e de PROD-BAJ-INV dice que «dejó de generar
    alertas», no que sea un error). ``Http404`` si no existe. Todo creador de alertas la llama antes de crear una; hay que
    llamarla dentro de ``transaction.atomic()``. Es reentrante: si la misma transacción ya lo bloqueó, no espera."""
    invernadero = Invernadero.objects.select_for_update(no_key=True).filter(pk=invernadero_id).first()
    if invernadero is None:
        raise Http404("No existe ese invernadero.")
    return invernadero


def _destinatarios(tipo, invernadero):
    """``(para_gerente, agronomo)`` de una alerta de ``tipo`` (regla 1 de 8.9 y reglas 2 a 4 de 8.22). El Agrónomo cuenta solo
    si su cuenta está activa; si no, queda el Gerente (MD-61), así siempre hay al menos un destinatario."""
    agronomo = invernadero.agronomo if invernadero.agronomo_id and invernadero.agronomo.is_active else None
    if tipo.destinatario == Destinatario.GERENTE:
        return True, None
    if tipo.destinatario == Destinatario.AGRONOMO_O_GERENTE:
        return (False, agronomo) if agronomo else (True, None)
    return True, agronomo  # AGRONOMO_Y_GERENTE


def _nueva(invernadero, tipo, clave, descripcion):
    """Crea la alerta (activa, no leída) con los destinatarios del tipo y la severidad del tipo."""
    para_gerente, agronomo = _destinatarios(tipo, invernadero)
    return Alerta.objects.create(
        invernadero=invernadero,
        tipo_alerta=tipo.codigo,
        descripcion_alerta=(descripcion or tipo.nombre)[:LARGO_DESCRIPCION],
        nivel_severidad=tipo.severidad,
        para_gerente=para_gerente,
        agronomo=agronomo,
        clave_estado=clave,
    )


def _asegurar(invernadero, tipo, clave, descripcion):
    """``(alerta, creada)``: la alerta de estado activa de ese tipo y clave, creándola si falta. El invernadero ya está
    bloqueado, así que nadie más la crea a la vez; el índice parcial ``alerta_de_estado_unica`` es el respaldo: si salta, se
    devuelve la que ya existía (nunca un error sin traducir)."""
    filtro = {"invernadero": invernadero, "tipo_alerta": tipo.codigo, "clave_estado": clave, "estado_alerta": "activa"}
    existente = Alerta.objects.filter(**filtro).first()
    if existente is not None:
        return existente, False
    try:
        with transaction.atomic():  # savepoint: el IntegrityError no rompe la transacción de quien llama
            return _nueva(invernadero, tipo, clave, descripcion), True
    except IntegrityError:
        return Alerta.objects.get(**filtro), False


def _resolver(alerta):
    """Pasa la alerta a «resuelta» y carga su fecha (regla 7 de 8.18). No toca la lectura: son estados independientes."""
    alerta.estado_alerta = Alerta.Estado.RESUELTA
    alerta.fecha_resolucion = timezone.now()
    alerta.save(update_fields=["estado_alerta", "fecha_resolucion"])
    return alerta


def crear_alerta_de_evento(invernadero_id, tipo, descripcion):
    """Crea una alerta de un tipo de evento y la devuelve; ``None`` si el invernadero está inactivo (post e de PROD-BAJ-INV).
    Bloquea el invernadero y lo lee de nuevo, así los destinatarios se calculan con el Agrónomo de ahora. ``tipo`` es el
    código registrado (``ValueError`` si no lo está). Los destinatarios salen del tipo (docs/api/alertas.md)."""
    tipo_registrado = tipo_de_alerta(tipo)
    invernadero = bloquear_invernadero_para_alertas(invernadero_id)
    if not invernadero.activo:
        return None
    return _nueva(invernadero, tipo_registrado, None, descripcion)


def asegurar_alerta_de_estado(invernadero_id, tipo, clave="", descripcion=None):
    """Idempotente: devuelve la alerta de estado activa de ese invernadero, tipo y clave, y si no hay, la crea; ``None``
    si el invernadero está inactivo. Bloquea el invernadero. Sin ``descripcion``, usa el nombre del tipo (el invernadero ya está
    en la FK y su nombre quedaría viejo si se lo renombra)."""
    tipo_registrado = tipo_de_alerta(tipo)
    invernadero = bloquear_invernadero_para_alertas(invernadero_id)
    if not invernadero.activo:
        return None
    return _asegurar(invernadero, tipo_registrado, clave, descripcion)[0]


def resolver_alerta_de_estado(invernadero_id, tipo, clave=""):
    """Pasa a «resuelta» (con su fecha) la alerta de estado activa de ese invernadero, tipo y clave y la devuelve; ``None``
    si no había una activa. Bloquea el invernadero (activo o no: resolver siempre se puede)."""
    tipo_registrado = tipo_de_alerta(tipo)
    invernadero = bloquear_invernadero_para_alertas(invernadero_id)
    alerta = (
        Alerta.objects.select_for_update(no_key=True)
        .filter(invernadero=invernadero, tipo_alerta=tipo_registrado.codigo, clave_estado=clave, estado_alerta="activa")
        .first()
    )
    return _resolver(alerta) if alerta else None


def resolver_alerta(alerta_id):
    """Pasa a «resuelta» una alerta (de evento, por lo general) y la devuelve; ``None`` si ya estaba resuelta.
    ``Http404`` si no existe. Bloquea el invernadero de la alerta y después la alerta (orden de D-40)."""
    alerta = Alerta.objects.filter(pk=alerta_id).first()
    if alerta is None:
        raise Http404("No existe esa alerta.")
    bloquear_invernadero_para_alertas(alerta.invernadero_id)
    alerta = Alerta.objects.select_for_update(no_key=True).get(pk=alerta_id)  # releída ya bloqueada
    return _resolver(alerta) if alerta.estado_alerta == Alerta.Estado.ACTIVA else None


def sincronizar_alertas_de_personal(invernadero, roles=None):
    """Deja las alertas «invernadero sin {rol} activo» como pide la condición actual: asegura la de cada rol de
    ``invernadero.roles_faltantes()`` (sin persona o con la persona inactiva; el Técnico solo con sistema IoT, regla 3 de
    8.22) y resuelve las de los demás. Devuelve ``Cambios(creadas, resueltas)``, en el orden de ``Invernadero.ROLES``. Con un
    invernadero inactivo no hace nada. Lee el invernadero de nuevo, bloqueado: sirve para quien ya lo guardó.

    ``roles`` (MAE-02b, D-43): lista de atributos del invernadero (``"capataz"``...). Con ``None`` se ocupa de los cuatro
    roles, como siempre. Con una lista, solo asegura y resuelve las alertas de esos roles y no toca ni bloquea las de los
    demás (la baja y la reactivación de una cuenta sincronizan solo el rol de la cuenta)."""
    atributos = [atributo for atributo, _ in Invernadero.ROLES if roles is None or atributo in roles]
    if roles is not None and set(roles) - set(atributos):
        raise ValueError(f"Roles desconocidos: {sorted(set(roles) - set(atributos))}.")
    actual = bloquear_invernadero_para_alertas(invernadero.pk)
    if not actual.activo:
        return Cambios([], [])
    faltan = {atributo for atributo, _, _ in actual.roles_faltantes()}
    activas = {
        alerta.tipo_alerta: alerta
        for alerta in Alerta.objects.select_for_update(no_key=True)
        .filter(
            invernadero=actual,
            estado_alerta="activa",
            clave_estado="",
            tipo_alerta__in=[f"sin_{atributo}" for atributo in atributos],
        )
        .order_by("pk")
    }
    creadas, resueltas = [], []
    for atributo in atributos:
        codigo = f"sin_{atributo}"
        if atributo in faltan:
            if codigo not in activas:
                alerta, creada = _asegurar(actual, tipo_de_alerta(codigo), "", None)
                if creada:
                    creadas.append(alerta)
        elif codigo in activas:
            resueltas.append(_resolver(activas[codigo]))
    return Cambios(creadas, resueltas)


def bloquear_alertas_activas(invernadero_id):
    """Bloquea (``FOR NO KEY UPDATE``) las alertas activas del invernadero, en orden de id, y las devuelve. Va después del
    invernadero y antes de las filas de las apps altas (orden de D-40)."""
    return list(
        Alerta.objects.select_for_update(no_key=True)
        .filter(invernadero_id=invernadero_id, estado_alerta="activa")
        .order_by("pk")
    )


def resolver_alertas_activas(invernadero):
    """Pasa a «resuelta» todas las alertas activas del invernadero (de estado y de evento; post e de PROD-BAJ-INV) y las
    devuelve. Bloquea las alertas en orden de id, después del invernadero (que quien llama ya bloqueó)."""
    return [_resolver(alerta) for alerta in bloquear_alertas_activas(invernadero.pk)]


def _ids_de_agronomo(cuenta):
    return cuenta.pk if cuenta is not None else None


def _pasan_al_entrante(alertas, saliente, entrante):
    """De ``alertas`` (activas), las que pasan al Agrónomo ``entrante`` (D4, MD-60): las del saliente y, si hay entrante,
    las que fueron al Gerente por falta de Agrónomo (de tipo ``AGRONOMO_O_GERENTE`` o ``AGRONOMO_Y_GERENTE``)."""
    sin_agronomo = set(codigos_con_destinatario(Destinatario.AGRONOMO_O_GERENTE)) | set(
        codigos_con_destinatario(Destinatario.AGRONOMO_Y_GERENTE)
    )
    saliente_id = _ids_de_agronomo(saliente)
    for alerta in alertas:
        if saliente_id is not None and alerta.agronomo_id == saliente_id:
            yield alerta
        elif entrante is not None and alerta.agronomo_id is None and alerta.tipo_alerta in sin_agronomo:
            yield alerta


def traspasar_alertas_del_agronomo(invernadero, saliente, entrante):
    """MD-60, regla 3 de PROD-MOD-INV y D4 (D-41): cuando cambia el Agrónomo de ``invernadero`` (cuentas de ``Agronomo``
    o ``None``), mueve sus alertas activas y devuelve las que cambiaron. Con saliente, pasan al entrante; sin entrante
    (rol vacío), las del saliente quedan sin Agrónomo y para el Gerente (MD-61); con entrante, las que habían ido al Gerente
    por falta de Agrónomo pasan a él (``AGRONOMO_O_GERENTE`` deja de ir al Gerente; ``AGRONOMO_Y_GERENTE`` sigue yendo;
    ``GERENTE`` no se toca). Bloquea las alertas en orden de id, después del invernadero."""
    codigos_o = set(codigos_con_destinatario(Destinatario.AGRONOMO_O_GERENTE))
    cambiadas = []
    for alerta in _pasan_al_entrante(bloquear_alertas_activas(invernadero.pk), saliente, entrante):
        if entrante is None:
            alerta.agronomo, alerta.para_gerente = None, True
        else:
            alerta.agronomo = entrante
            if alerta.tipo_alerta in codigos_o:
                alerta.para_gerente = False
        alerta.save(update_fields=["agronomo", "para_gerente"])
        cambiadas.append(alerta)
    return cambiadas


def contar_alertas_que_recibe(invernadero, saliente, entrante):
    """Cuántas alertas activas pasarían al Agrónomo entrante (el «Recibe» de la regla 2 de PROD-MOD-INV). No cambia nada y
    no bloquea. Sin entrante (rol vacío), ninguna."""
    if entrante is None:
        return 0
    activas = Alerta.objects.filter(invernadero_id=invernadero.pk, estado_alerta="activa")
    return sum(1 for _ in _pasan_al_entrante(activas, saliente, entrante))


def abrir_alerta(actor, alerta_id):
    """Regla 7 de 8.18 (MAE-02b): un destinatario abre la alerta y su ``estado_lectura_alerta`` pasa a «leída». No toca
    ``estado_alerta`` ni audita (D-41, SEG-14) y devuelve la alerta releída. ``Http404`` si no existe (D-28);
    ``PermissionDenied`` si ``actor`` no la recibe (``Alerta.objects.para``), sin cambiar nada.

    Una sola sentencia condicional: ``UPDATE ... WHERE id = X AND <es destinatario> AND no_leida``. No bloquea el
    invernadero ni toma otra fila que la de la alerta, así que no puede cerrar un ciclo con el orden invernadero → alertas
    de D-40. Si un traspaso simultáneo cambia el destinatario, PostgreSQL (Read Committed) espera la fila y vuelve a
    evaluar el ``WHERE`` sobre la versión confirmada: no la marca para quien dejó de recibirla (razonado, no probado:
    D-43)."""
    if not Alerta.objects.filter(pk=alerta_id).exists():
        raise Http404("No existe esa alerta.")
    with transaction.atomic():
        propias = Alerta.objects.para(actor).filter(pk=alerta_id)
        if not propias.exists():
            raise PermissionDenied("Esa alerta no es para vos.")
        propias.filter(estado_lectura_alerta=Alerta.Lectura.NO_LEIDA).update(
            estado_lectura_alerta=Alerta.Lectura.LEIDA
        )
        return Alerta.objects.get(pk=alerta_id)
