# Servicios de Cliente (COM-01): alta con su reactivación (COM-ALT-CLT), modificación (COM-MOD-CLT), baja (COM-BAJ-CLT) y consulta
# (COM-CNS-CLT). Cada caso de uso es una función dentro de ``transaction.atomic()`` y audita con el formato de D-36
# (docs/patrones/auditoria.md). Casos de uso: docs/casos_de_uso/comercial/clientes.md («Cómo se aplica»); direcciones: D-58 y
# docs/api/direcciones.md.
#
# Bloqueos (docs/patrones/bloqueos.md, sección «comercial»; siempre ``FOR NO KEY UPDATE``): la cuenta de quien actúa, después la
# fila del cliente y, por último, sus ``DireccionCliente`` en orden de id; todo se vuelve a leer ya bloqueado. El alta no tiene
# fila que bloquear: dos altas con el mismo CUIT las ordena la restricción única de la base (el ``IntegrityError`` se traduce al
# mismo error de campo, nunca un 500). Dos modificaciones a la vez del mismo cliente: gana la última (D-40), salvo el CUIT.
#
# Lo que completan otras tareas, escrito ya como funciones: ``direcciones_en_uso`` y ``pendientes_del_cliente`` (COM-02 las completó con
# las compra-ventas; COM-03, COM-06 y COM-08a suman las suyas) e ``impide_quitar_el_correo`` (COM-03, hoy siempre False).

import re
from dataclasses import dataclass, field

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Q, Value
from django.db.models.functions import Coalesce, Concat, Lower, NullIf
from django.http import Http404
from django.shortcuts import get_object_or_404

from comercial.models import Cliente, CompraVenta, DireccionCliente
from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.validadores import validar_telefono
from maestros.models import Direccion, DireccionRural, DireccionUrbana
from maestros.servicios import direcciones
from maestros.validadores import formatear_cuit, validar_cuit

Estado = Cliente.Estado

ACCION_MODIFICAR = "modificar"
ACCION_BAJA = "baja"
ACCION_REACTIVAR = "reactivar"

POR_PAGINA = 50
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."

# Atributo del modelo de cada dato escalar de ``DatosDeCliente`` (la clave es también el nombre en ``cambios`` de la auditoría
# salvo ``cuit``, que va como texto con guiones).
_ATRIBUTOS = {
    "tipo_cliente": "tipo_cliente",
    "cuit": "cuit_cliente",
    "razon_social": "razon_social_cliente",
    "nombre": "nombre_cliente",
    "apellido": "apellido_cliente",
    "telefono": "telefono_cliente",
    "email": "email_cliente",
}
_LARGOS = {
    "razon_social": Cliente._meta.get_field("razon_social_cliente").max_length,
    "nombre": Cliente._meta.get_field("nombre_cliente").max_length,
    "apellido": Cliente._meta.get_field("apellido_cliente").max_length,
    "email": Cliente._meta.get_field("email_cliente").max_length,
}


@dataclass
class DatosDeCliente:
    """Lo que carga el formulario del cliente (alta, modificación y reactivación). Las direcciones son los datos de
    ``maestros.servicios.direcciones.validar_direccion``: las nuevas, en orden; las corregidas, como pares
    (id de la ``Direccion``, datos nuevos); las desactivadas y las borradas, como ids de ``Direccion``."""

    tipo_cliente: str = ""
    cuit: str = ""
    razon_social: str = ""
    nombre: str = ""
    apellido: str = ""
    telefono: str = ""
    email: str = ""
    direcciones_nuevas: list = field(default_factory=list)
    direcciones_corregidas: list = field(default_factory=list)
    direcciones_desactivadas: list = field(default_factory=list)
    direcciones_borradas: list = field(default_factory=list)

    @classmethod
    def desde_post(cls, post):
        """Arma los datos del formulario: los campos simples por su nombre, ``nueva-<i>-<campo>`` (por posición),
        ``corregida-<id de la dirección>-<campo>``, y ``desactivar`` y ``borrar`` (ids). Un id mal formado se ignora."""
        nuevas, corregidas = {}, {}
        for clave in post:
            for prefijo, destino in (("nueva", nuevas), ("corregida", corregidas)):
                coincidencia = re.fullmatch(rf"{prefijo}-(\d+)-(.+)", clave)
                if coincidencia:
                    destino.setdefault(int(coincidencia.group(1)), {})[coincidencia.group(2)] = post.get(clave)
        return cls(
            tipo_cliente=post.get("tipo_cliente", ""),
            cuit=post.get("cuit", ""),
            razon_social=post.get("razon_social", ""),
            nombre=post.get("nombre", ""),
            apellido=post.get("apellido", ""),
            telefono=post.get("telefono", ""),
            email=post.get("email", ""),
            direcciones_nuevas=[nuevas[i] for i in sorted(nuevas)],
            direcciones_corregidas=[(i, corregidas[i]) for i in sorted(corregidas)],
            direcciones_desactivadas=_ids(post.getlist("desactivar")),
            direcciones_borradas=_ids(post.getlist("borrar")),
        )


@dataclass
class FichaDelCliente:
    """La ficha de COM-CNS-CLT: el cliente y sus direcciones (las hijas, urbana o rural), activas e inactivas."""

    cliente: Cliente
    direcciones_activas: list
    direcciones_inactivas: list


# ---- lo que completan otras tareas (hoy devuelven «nada») ----


def direcciones_en_uso(ids):
    """Los ids de ``Direccion`` (de ``ids``) que usa una compra-venta o un detalle de suministro (regla 3 de 8.18, MD-19): esas
    no se modifican ni se borran. Desde COM-02 cuenta las compra-ventas con envío, **en cualquier estado** (una dirección usada nunca se
    modifica ni se borra, aunque la venta esté cancelada); **COM-03 suma los detalles de suministro**."""
    ids = list(ids)
    if not ids:
        return set()
    return set(CompraVenta.objects.filter(direccion_envio_id__in=ids).values_list("direccion_envio_id", flat=True))


def impide_quitar_el_correo(cliente):
    """Regla 3 de COM-MOD-CLT: True si al cliente no se le puede quitar el correo porque tiene un suministro vigente (los enlaces
    de confirmación y las quejas solo llegan por correo, regla 18 de 8.20). **Se completa en COM-03**. En COM-01, siempre False."""
    return False


def pendientes_del_cliente(cliente, actor):
    """Regla 1 de COM-BAJ-CLT: lo que el cliente tiene pendiente, como textos para la ventana de baja (entregas sin cobrar,
    suministros vigentes, compra-ventas abiertas, quejas y discrepancias pendientes). Desde COM-02 informa las compra-ventas abiertas o
    pendientes de decisión (de todos los Vendedores: solo el Gerente da de baja); **COM-03** suma los suministros, **COM-06** las entregas
    sin cobrar, las quejas y las discrepancias, **COM-08a** el estado de pago."""
    codigos = [
        f"CV-{numero:04d}"
        for numero in CompraVenta.objects.filter(
            cliente=cliente, estado_venta__in=[CompraVenta.Estado.ABIERTA, CompraVenta.Estado.PENDIENTE_DECISION]
        )
        .order_by("numero")
        .values_list("numero", flat=True)
    ]
    return [f"Compra-ventas abiertas: {len(codigos)} ({', '.join(codigos)})."] if codigos else []


def contratos_del_cliente(actor, cliente):
    """Las compra-ventas del cliente que ``actor`` puede ver (el Vendedor, solo las suyas; el Gerente, todas), con su monto, de la más
    reciente a la más antigua: para la ficha del cliente (COM-02; COM-03 suma los suministros). Una consulta."""
    return list(
        CompraVenta.objects.en_alcance_de(actor)
        .filter(cliente=cliente)
        .con_monto()
        .order_by("-fecha_realizacion", "-numero")
    )


def contratos_vigentes_por_cliente(actor, clientes_):
    """``{cliente_id: cantidad}`` de compra-ventas abiertas o pendientes de decisión de cada cliente de ``clientes_``, dentro del alcance de
    ``actor``: la columna «Contratos vigentes» de la lista (COM-02), en una sola consulta."""
    filas = (
        CompraVenta.objects.en_alcance_de(actor)
        .filter(
            cliente__in=list(clientes_), estado_venta__in=[CompraVenta.Estado.ABIERTA, CompraVenta.Estado.PENDIENTE_DECISION]
        )
        .values("cliente_id")
        .annotate(cantidad=Count("pk"))
    )
    return {fila["cliente_id"]: fila["cantidad"] for fila in filas}


def direcciones_activas(cliente):
    """Las direcciones activas del cliente (las hijas, urbana o rural, con su localidad), por id: las que se ofrecen para un envío (regla 23
    de 8.6; D-58). Dos consultas."""
    ids = list(
        DireccionCliente.objects.filter(cliente=cliente, direccion__estado_direccion=Direccion.Estado.ACTIVO)
        .order_by("direccion_id")
        .values_list("direccion_id", flat=True)
    )
    hijas = _hijas(ids)
    return [hijas[i] for i in ids if i in hijas]


def ids_de_direcciones(cliente):
    """Los ids de ``Direccion`` del cliente (activas e inactivas), por id. Una consulta."""
    return list(DireccionCliente.objects.filter(cliente=cliente).order_by("direccion_id").values_list("direccion_id", flat=True))


def direccion_hija(direccion_id):
    """La hija (urbana o rural) de la ``Direccion`` ``direccion_id`` con su localidad, o ``None``."""
    return _hijas([direccion_id]).get(direccion_id)


# ---- comunes ----


def _ids(valores):
    """Los ``valores`` que son números, como enteros (el resto se ignora)."""
    ids = []
    for valor in valores:
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue
    return ids


def _texto(valor):
    """``valor`` como texto recortado (``None`` es vacío)."""
    return "" if valor is None else str(valor).strip()


def _exigir_quien_consulta(actor):
    """Precondición a de ALT, MOD, CNS (y regla 3 de CNS): Vendedor o Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR):
        raise PermissionDenied("Solo un Vendedor o un Gerente activo puede gestionar clientes.")


def _exigir_gerente(actor):
    """Precondición a de BAJ (MD-47): solo el Gerente activo da de baja."""
    if actor is None or not actor.is_active or rol_de(actor) != Usuario.Rol.GERENTE:
        raise PermissionDenied("Solo un Gerente activo puede dar de baja a un cliente.")


def _error_general(mensaje, codigo):
    """Un ``ValidationError`` general con ``mensaje`` y ``codigo``."""
    return ValidationError(mensaje, code=codigo)


def _bloquear_actor(actor):
    """Bloquea la cuenta de quien actúa (lo primero, D-30) y verifica que siga activa: pudo quedar inactiva mientras esperaba."""
    fila = Usuario.objects.select_for_update(no_key=True).filter(pk=actor.pk, is_active=True).first()
    if fila is None:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _bloquear_cliente(actor, cliente_id):
    """La cuenta de quien actúa y, después, el cliente, bloqueados y leídos de nuevo con su estado real; 404 si no existe."""
    _bloquear_actor(actor)
    cliente = Cliente.objects.select_for_update(no_key=True).filter(pk=cliente_id).first()
    if cliente is None:
        raise Http404("No existe ese cliente.")
    return cliente


def _hijas(ids):
    """``{id: hija}`` de las direcciones ``ids`` (urbanas o rurales), con su localidad."""
    hijas = {}
    for modelo in (DireccionUrbana, DireccionRural):
        for hija in modelo.objects.filter(pk__in=ids).select_related("localidad__departamento__provincia"):
            hijas[hija.pk] = hija
    return hijas


def _hija_sin_guardar(validada):
    """Una dirección **sin guardar** con los datos de ``validada``, para calcular su ``clave_de_ubicacion`` con la misma función
    que usa la API (D-58 punto 6)."""
    campos = {direcciones.ATRIBUTO_DE_LA_DIRECCION.get(c, c): v for c, v in validada.campos.items()}
    modelo = DireccionUrbana if validada.zona == "urbana" else DireccionRural
    return modelo(localidad=validada.localidad, **campos)


def _error_de_cuit(cuit, excluir_pk=None):
    """Regla 2 de COM-ALT-CLT: si el CUIT ya es de otro cliente, el error con su id (``params``) para ofrecer «Abrir su ficha»
    (activo) o «Reactivarlo» (inactivo); si no, ``None``."""
    otro = Cliente.objects.filter(cuit_cliente=cuit).exclude(pk=excluir_pk).first()
    if otro is None:
        return None
    if otro.activo:
        return ValidationError(
            "Ya hay un cliente con ese CUIT. Abrí su ficha en lugar de cargarlo de nuevo.",
            code="cuit_de_cliente_activo",
            params={"cliente_id": otro.pk},
        )
    return ValidationError(
        "Ese CUIT es de un cliente dado de baja. Podés reactivarlo en lugar de cargarlo de nuevo.",
        code="cuit_de_cliente_inactivo",
        params={"cliente_id": otro.pk},
    )


@dataclass
class _Validado:
    """Los datos del cliente ya limpios (``{clave de DatosDeCliente: valor}``) y las direcciones ya validadas."""

    limpios: dict
    nuevas: list
    corregidas: list  # [(id, DireccionValidada)]


def _validar(datos, excluir_pk=None):
    """Valida y limpia los datos sin escribir (patrón ABM, sección 2, paso 2): junta todos los errores en un solo
    ``ValidationError`` con un error por campo. Reglas 1, 3, 4, 5 y 6 de COM-ALT-CLT. En una persona jurídica solo cuenta la razón
    social; en una física, el nombre y el apellido (regla 3): los del otro tipo se vacían."""
    errores = {}
    limpios = {clave: _texto(getattr(datos, clave)) for clave in _ATRIBUTOS}

    tipo = limpios["tipo_cliente"]
    if tipo not in Cliente.Tipo.values:
        errores["tipo_cliente"] = [_error_general("Elegí si es una persona jurídica o una persona física.", "tipo_invalido")]
    else:
        pedidos = {"razon_social": "Ingresá la razón social."} if tipo == Cliente.Tipo.JURIDICA else {
            "nombre": "Ingresá el nombre.",
            "apellido": "Ingresá el apellido.",
        }
        for clave in ("razon_social", "nombre", "apellido"):
            if clave not in pedidos:
                limpios[clave] = ""
            elif not limpios[clave]:
                errores[clave] = [_error_general(pedidos[clave], "obligatorio")]
            elif len(limpios[clave]) > _LARGOS[clave]:
                errores[clave] = [_error_general(f"Usá como máximo {_LARGOS[clave]} caracteres.", "demasiado_largo")]

    if not limpios["cuit"]:
        errores["cuit"] = [_error_general("Ingresá el CUIT.", "obligatorio")]
    else:
        try:
            limpios["cuit"] = validar_cuit(limpios["cuit"])
        except ValidationError as error:
            errores["cuit"] = error.error_list
        else:
            if error := _error_de_cuit(limpios["cuit"], excluir_pk):
                errores["cuit"] = [error]

    try:
        validar_telefono(limpios["telefono"])
    except ValidationError as error:
        errores["telefono"] = error.error_list

    if limpios["email"]:
        try:
            validate_email(limpios["email"])
        except ValidationError as error:
            errores["email"] = error.error_list
        else:
            if len(limpios["email"]) > _LARGOS["email"]:
                errores["email"] = [_error_general(f"Usá como máximo {_LARGOS['email']} caracteres.", "demasiado_largo")]

    nuevas, corregidas = [], []
    for i, pedido in enumerate(datos.direcciones_nuevas):
        validada = _validar_direccion(pedido, f"nueva-{i}", errores)
        nuevas.append(validada)
    retiradas = set(datos.direcciones_desactivadas) | set(datos.direcciones_borradas)
    for direccion_id, pedido in datos.direcciones_corregidas:
        if direccion_id in retiradas:
            continue  # la pantalla manda la corrección de todas; si se desactiva o se borra, esa corrección no cuenta
        validada = _validar_direccion(pedido, f"corregida-{direccion_id}", errores)
        corregidas.append((direccion_id, validada))

    if errores:
        raise ValidationError(errores)
    return _Validado(limpios, nuevas, corregidas)


def _validar_direccion(pedido, prefijo, errores):
    """Valida una dirección con la API de `maestros`; sus errores van como ``<prefijo>-<campo>``. ``None`` si falló."""
    try:
        return direcciones.validar_direccion(pedido)
    except ValidationError as error:
        for campo, lista in error.error_dict.items():
            errores[f"{prefijo}-{campo}"] = lista
        return None


# ---- direcciones ----


@dataclass
class _Efecto:
    """Lo que hicieron las direcciones, para la auditoría: referencias (``datos``) y las hijas afectadas."""

    creadas: list = field(default_factory=list)
    corregidas: list = field(default_factory=list)
    reemplazadas: list = field(default_factory=list)
    desactivadas: list = field(default_factory=list)
    borradas: list = field(default_factory=list)  # solo referencias: la fila ya no existe
    afectadas: list = field(default_factory=list)

    @property
    def hubo_cambios(self):
        return bool(self.creadas or self.corregidas or self.reemplazadas or self.desactivadas or self.borradas)

    def datos(self):
        """Los ``datos`` de auditoría (D-36): solo las listas que no están vacías, como referencias."""
        listas = {
            "direcciones_creadas": self.creadas,
            "direcciones_corregidas": self.corregidas,
            "direcciones_reemplazadas": self.reemplazadas,
            "direcciones_desactivadas": self.desactivadas,
        }
        datos = {clave: [referencia(h) for h in hijas] for clave, hijas in listas.items() if hijas}
        if self.borradas:
            datos["direcciones_borradas"] = self.borradas
        return datos


def _misma_ubicacion_y_datos(hija, validada):
    """True si corregir ``hija`` con ``validada`` no cambiaría nada (D-28: sin cambios no se escribe)."""
    if validada.zona != hija.ZONA or validada.localidad.pk != hija.localidad_id:
        return False
    nuevos = {campo: valor or None for campo, valor in validada.campos.items()}
    return nuevos == direcciones.datos_de_la_direccion(hija)


def _chequear_direcciones(cliente, validado, datos, vinculos, errores):
    """Con el cliente y sus vínculos ya bloqueados: las direcciones que se tocan son de este cliente (``direccion_invalida``),
    y ninguna queda idéntica a otra activa, contra las que permanecen activas del cliente y entre las enviadas en el mismo
    formulario (``direccion_repetida``, regla 6 y D-58 punto 6). Devuelve ``{id: hija}`` de las direcciones del cliente."""
    hijas = _hijas([v.direccion_id for v in vinculos])
    propias = {v.direccion_id for v in vinculos}
    invalidas = [
        i for i in (*datos.direcciones_desactivadas, *datos.direcciones_borradas) if i not in propias
    ] + [i for i, _ in validado.corregidas if i not in propias or hijas[i].estado_direccion != Direccion.Estado.ACTIVO]
    if invalidas:
        errores["direcciones"] = [_error_general("Esa dirección no es una dirección activa de este cliente.", "direccion_invalida")]
        return hijas

    retiradas = set(datos.direcciones_desactivadas) | set(datos.direcciones_borradas)
    corregidas = {i for i, _ in validado.corregidas}
    vistas = set()
    for direccion_id in sorted(propias):
        hija = hijas[direccion_id]
        if direccion_id in retiradas or direccion_id in corregidas or hija.estado_direccion != Direccion.Estado.ACTIVO:
            continue
        vistas.add(direcciones.clave_de_ubicacion(hija))
    enviadas = [(f"corregida-{i}", v) for i, v in validado.corregidas] + [
        (f"nueva-{i}", v) for i, v in enumerate(validado.nuevas)
    ]
    for clave_del_campo, validada in enviadas:
        clave = direcciones.clave_de_ubicacion(_hija_sin_guardar(validada))
        if clave in vistas:
            errores[clave_del_campo] = [
                _error_general("El cliente ya tiene esa dirección.", "direccion_repetida")
            ]
        vistas.add(clave)
    return hijas


def _aplicar_direcciones(cliente, validado, datos, vinculos, hijas):
    """Escribe las direcciones (postcondiciones b a e de COM-MOD-CLT; la dirección en uso, regla 4 y D-58 punto 5) y devuelve
    lo hecho. Orden: borrar, corregir, desactivar, crear. Cada ``Direccion`` nueva lleva su ``DireccionCliente`` en la misma
    transacción, y nunca se vincula una existente (C6)."""
    efecto = _Efecto()
    por_id = {v.direccion_id: v for v in vinculos}
    ids_a_tocar = [*datos.direcciones_borradas, *(i for i, _ in validado.corregidas)]
    en_uso = direcciones_en_uso(ids_a_tocar) if ids_a_tocar else set()

    en_uso_borradas = [i for i in datos.direcciones_borradas if i in en_uso]
    if en_uso_borradas:
        raise ValidationError(
            {
                "direcciones": [
                    _error_general(
                        "Una dirección que usa una venta o un suministro no se borra: desactivala y cargá otra.",
                        "direccion_en_uso",
                    )
                ]
            }
        )

    for direccion_id in datos.direcciones_borradas:
        hija = hijas[direccion_id]
        efecto.borradas.append(referencia(hija))  # antes de borrarla: después ya no tiene id
        por_id[direccion_id].delete()
        direcciones.borrar_direccion(hija)

    for direccion_id, validada in validado.corregidas:
        hija = hijas[direccion_id]
        if _misma_ubicacion_y_datos(hija, validada):
            continue  # D-28: corregirla con lo que ya tiene no cambia nada
        if direccion_id in en_uso:
            # Regla 4: la usa un contrato; se crea otra con los datos corregidos y la anterior pasa a «inactiva» (la conserva).
            nueva = direcciones.crear_direccion(validada)
            DireccionCliente.objects.create(cliente=cliente, direccion=nueva.direccion_ptr)
            direcciones.inactivar_direccion(hija)
            efecto.creadas.append(nueva)
            efecto.reemplazadas.append(hija)
            efecto.afectadas.extend([nueva, hija])
        elif validada.zona == hija.ZONA:
            efecto.corregidas.append(direcciones.corregir_direccion(hija, validada))
            efecto.afectadas.append(hija)
        else:
            # Cambio de zona: es otra dirección. Se crea la nueva, el vínculo pasa a apuntar a ella y recién después se borra la
            # anterior (con el vínculo apuntando a la vieja, el PROTECT lo impide).
            nueva = direcciones.crear_direccion(validada)
            vinculo = por_id[direccion_id]
            vinculo.direccion = nueva.direccion_ptr
            vinculo.save(update_fields=["direccion"])
            direcciones.borrar_direccion(hija)
            efecto.corregidas.append(nueva)
            efecto.afectadas.append(nueva)

    for direccion_id in datos.direcciones_desactivadas:
        hija = hijas[direccion_id]
        if hija.estado_direccion == Direccion.Estado.ACTIVO and direccion_id not in datos.direcciones_borradas:
            direcciones.inactivar_direccion(hija)
            efecto.desactivadas.append(hija)
            efecto.afectadas.append(hija)

    for validada in validado.nuevas:
        nueva = direcciones.crear_direccion(validada)
        DireccionCliente.objects.create(cliente=cliente, direccion=nueva.direccion_ptr)
        efecto.creadas.append(nueva)
        efecto.afectadas.append(nueva)
    return efecto


# ---- alta, reactivación, modificación y baja ----


def _cambios_del_alta(cliente):
    """Los ``cambios`` de un alta (D-36): «antes» nulo; solo los datos que se cargaron (el CUIT, con guiones)."""
    cambios = {"tipo_cliente": {"antes": None, "despues": cliente.tipo_cliente}}
    for clave, atributo in _ATRIBUTOS.items():
        if clave == "tipo_cliente":
            continue
        valor = getattr(cliente, atributo)
        if clave == "cuit":
            valor = formatear_cuit(valor)
        if valor:
            cambios[clave] = {"antes": None, "despues": valor}
    cambios["estado"] = {"antes": None, "despues": cliente.estado_cliente}
    return cambios


def alta_cliente(actor, datos):
    """COM-ALT-CLT: registra un cliente nuevo y lo devuelve.

    - Precondición a: Vendedor o Gerente activo. Reglas 1 y 2: el CUIT es obligatorio, válido y único entre activos e inactivos;
      si es de otro cliente se rechaza con ``cuit_de_cliente_activo`` o ``cuit_de_cliente_inactivo`` y el id del cliente.
    - Reglas 3 a 6: tipo, teléfono, correo y direcciones (opcionales, ninguna idéntica a otra). Postcondiciones a y b: cliente
      «activo» y sus direcciones «activas», cada una nueva (C6) con su ``DireccionCliente``.
    - Postcondición d y D-36: un registro ``alta_cliente`` con el cliente y cada dirección creada.
    - Dos altas con el mismo CUIT a la vez: la segunda recibe el mismo error de campo, no un 500.
    """
    _exigir_quien_consulta(actor)
    validado = _validar(datos)
    errores = {}
    _chequear_direcciones(None, validado, datos, [], errores)  # sin vínculos: solo las enviadas entre sí
    if errores:
        raise ValidationError(errores)
    limpios = validado.limpios
    with transaction.atomic():
        _bloquear_actor(actor)
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no aborta la transacción de afuera
                cliente = Cliente.objects.create(**{atributo: limpios[clave] for clave, atributo in _ATRIBUTOS.items()})
        except IntegrityError as error:
            # Otra alta con el mismo CUIT confirmó primero: el mismo error de campo, con el id del cliente que ganó.
            if repetido := _error_de_cuit(limpios["cuit"]):
                raise ValidationError({"cuit": [repetido]}) from error
            raise
        efecto = _aplicar_direcciones(cliente, validado, datos, [], {})
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_CLIENTE,
            afectados=[cliente, *efecto.afectadas],
            detalle={"cambios": _cambios_del_alta(cliente), **({"datos": efecto.datos()} if efecto.hubo_cambios else {})},
        )
    return cliente


def _actualizar(actor, cliente_id, datos, *, reactivar):
    """El núcleo de la modificación y de la reactivación: bloquea (cuenta, cliente, vínculos), relee, aplica los datos del
    cliente y las direcciones y audita. Devuelve ``(cliente, cambios, efecto, hubo_cambios)``."""
    if not Cliente.objects.filter(pk=cliente_id).exists():
        raise Http404("No existe ese cliente.")  # antes de validar: el CUIT propio no cuenta como repetido de un cliente que no existe
    validado = _validar(datos, excluir_pk=cliente_id)
    with transaction.atomic():
        cliente = _bloquear_cliente(actor, cliente_id)
        vinculos = list(
            DireccionCliente.objects.select_for_update(no_key=True, of=("self",)).filter(cliente=cliente).order_by("pk")
        )
        if reactivar and cliente.activo:
            raise _error_general("El cliente no está dado de baja.", "cliente_no_inactivo")
        errores = {}
        if repetido := _error_de_cuit(validado.limpios["cuit"], cliente.pk):
            errores["cuit"] = [repetido]
        hijas = _chequear_direcciones(cliente, validado, datos, vinculos, errores)
        limpios = validado.limpios
        # Regla 3 de COM-MOD-CLT: no se quita el correo de un cliente con suministro vigente.
        if cliente.email_cliente and not limpios["email"] and impide_quitar_el_correo(cliente):
            errores["email"] = [
                _error_general(
                    "No se puede quitar el correo: tiene un suministro vigente y los enlaces y las quejas llegan solo por correo.",
                    "correo_con_suministro_vigente",
                )
            ]
        if errores:
            raise ValidationError(errores)

        cambios = {}
        for clave, atributo in _ATRIBUTOS.items():
            antes, despues = getattr(cliente, atributo), limpios[clave]
            if antes != despues:
                cambios[clave] = {
                    "antes": formatear_cuit(antes) if clave == "cuit" else antes,
                    "despues": formatear_cuit(despues) if clave == "cuit" else despues,
                }
                setattr(cliente, atributo, despues)
        campos = [_ATRIBUTOS[clave] for clave in cambios]
        if reactivar:
            cambios["estado"] = {"antes": Estado.INACTIVO.value, "despues": Estado.ACTIVO.value}
            cliente.estado_cliente = Estado.ACTIVO
            campos.append("estado_cliente")
        if campos:
            try:
                with transaction.atomic():
                    cliente.save(update_fields=campos)
            except IntegrityError as error:
                if repetido := _error_de_cuit(limpios["cuit"], cliente.pk):
                    raise ValidationError({"cuit": [repetido]}) from error
                raise
        efecto = _aplicar_direcciones(cliente, validado, datos, vinculos, hijas)
        if cambios or efecto.hubo_cambios:  # D-28: sin cambios no se audita
            detalle = {"cambios": cambios}
            if efecto.hubo_cambios:
                detalle["datos"] = efecto.datos()
            accion = (
                RegistroAuditoria.Accion.REACTIVACION_CLIENTE if reactivar else RegistroAuditoria.Accion.MODIFICACION_CLIENTE
            )
            RegistroAuditoria.objects.registrar(
                usuario=actor, accion=accion, afectados=[cliente, *efecto.afectadas], detalle=detalle
            )
        return cliente, efecto


def modificar_cliente(actor, cliente_id, datos):
    """COM-MOD-CLT: actualiza los datos de contacto y las direcciones de un cliente, activo o inactivo, y lo devuelve.

    - Precondición a: Vendedor o Gerente activo. Precondición b: el CUIT nuevo no es el de otro cliente (con su id).
    - Regla 2: un cliente inactivo se modifica y no se reactiva. Regla 3: no se quita el correo con un suministro vigente
      (``impide_quitar_el_correo``). Regla 4 y postcondiciones b a e: agregar, corregir (en el lugar si nada la usa; si la usa una
      venta o un suministro, se crea otra y la anterior pasa a «inactiva»), desactivar y borrar direcciones.
    - D-28: sin cambios no se escribe ni se audita. Postcondición f y D-36: ``modificacion_cliente``.
    """
    _exigir_quien_consulta(actor)
    cliente, _ = _actualizar(actor, cliente_id, datos, reactivar=False)
    return cliente


def reactivar_cliente(actor, cliente_id, datos):
    """COM-ALT-CLT (postcondición c y regla 2; no es parte de MOD): reactiva a un cliente inactivo con los datos del formulario
    del alta (que el actor pudo corregir) y suma las direcciones nuevas. Si lo reactiva un Vendedor, el Gerente recibe la
    notificación «Cliente reactivado: {cliente}» (MD-47); sin Gerente activo se omite y no falla (D-14). Se audita como
    ``reactivacion_cliente``."""
    _exigir_quien_consulta(actor)
    cliente, _ = _actualizar(actor, cliente_id, datos, reactivar=True)
    if rol_de(actor) == Usuario.Rol.VENDEDOR:
        notificaciones.notificar_al_gerente(
            f"Cliente reactivado: {cliente}",
            f"{actor.get_full_name() or actor.email} reactivó al cliente {cliente} (CUIT {formatear_cuit(cliente.cuit_cliente)}). "
            "Si no correspondía, podés darlo de baja desde su ficha.",
        )
    return cliente


def baja_cliente(actor, cliente_id):
    """COM-BAJ-CLT: da de baja lógica a un cliente activo y lo devuelve.

    - Precondición a y MD-47: solo el Gerente activo. Precondición b: el cliente está activo (``cliente_inactivo``).
    - Regla 1: la baja no se bloquea nunca; lo pendiente se informa antes (``pendientes_del_cliente``). Postcondición a: pasa a
      «inactivo»; sus direcciones y sus contratos no cambian. Postcondición c y D-36: un registro ``baja_cliente``.
    """
    _exigir_gerente(actor)
    with transaction.atomic():
        cliente = _bloquear_cliente(actor, cliente_id)
        if not cliente.activo:
            raise _error_general("El cliente ya está dado de baja.", "cliente_inactivo")
        cliente.estado_cliente = Estado.INACTIVO
        cliente.save(update_fields=["estado_cliente"])
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_CLIENTE,
            afectados=[cliente],
            detalle={"cambios": {"estado": {"antes": Estado.ACTIVO.value, "despues": Estado.INACTIVO.value}}},
        )
    return cliente


# ---- consulta (COM-CNS-CLT) ----


def buscar_clientes(actor, texto="", estado="", pagina=1):
    """COM-CNS-CLT, regla 1: la ``Page`` de clientes (50 por página) que coinciden con ``texto`` (CUIT con o sin guiones desde 2
    dígitos, razón social, nombre, apellido o «nombre apellido», sin distinguir mayúsculas) y con el ``estado`` (vacío: todos), por
    nombre visible y después id. Regla 3: Vendedor y Gerente ven todos. No audita (SEG-14)."""
    _exigir_quien_consulta(actor)
    lista = Cliente.objects.en_alcance_de(actor).annotate(
        nombre_completo=Concat("nombre_cliente", Value(" "), "apellido_cliente"),
        _orden=Lower(Coalesce(NullIf("razon_social_cliente", Value("")), "nombre_completo")),
    )
    texto = _texto(texto)
    if texto:
        coincide = (
            Q(razon_social_cliente__icontains=texto)
            | Q(nombre_cliente__icontains=texto)
            | Q(apellido_cliente__icontains=texto)
            | Q(nombre_completo__icontains=texto)
        )
        digitos = re.sub(r"\D", "", texto)
        if len(digitos) >= 2:
            coincide |= Q(cuit_cliente__contains=digitos)
        lista = lista.filter(coincide)
    if estado in Estado.values:
        lista = lista.filter(estado_cliente=estado)
    return Paginator(lista.order_by("_orden", "id"), POR_PAGINA).get_page(pagina)


def direcciones_activas_por_cliente(clientes_):
    """``{cliente_id: cantidad}`` de direcciones activas de cada cliente de ``clientes_``, en una sola consulta (la columna
    «Direcciones» de la lista, sin una consulta por fila)."""
    filas = (
        DireccionCliente.objects.filter(cliente__in=list(clientes_), direccion__estado_direccion=Direccion.Estado.ACTIVO)
        .values("cliente_id")
        .annotate(cantidad=Count("pk"))
    )
    return {fila["cliente_id"]: fila["cantidad"] for fila in filas}


def ficha_del_cliente(actor, cliente_id):
    """COM-CNS-CLT, regla 2: el cliente con sus direcciones, activas e inactivas (las hijas, por id). Los contratos y las
    entregas sin cobrar se suman en COM-02, COM-03, COM-06 y COM-08a. 404 si no existe; ``PermissionDenied`` fuera del alcance."""
    _exigir_quien_consulta(actor)
    cliente = get_object_or_404(Cliente.objects.en_alcance_de(actor), pk=cliente_id)
    ids = list(cliente.direcciones.order_by("direccion_id").values_list("direccion_id", flat=True))
    hijas = _hijas(ids)
    ordenadas = [hijas[i] for i in ids if i in hijas]
    return FichaDelCliente(
        cliente=cliente,
        direcciones_activas=[h for h in ordenadas if h.estado_direccion == Direccion.Estado.ACTIVO],
        direcciones_inactivas=[h for h in ordenadas if h.estado_direccion != Direccion.Estado.ACTIVO],
    )


def acciones_permitidas(actor, cliente):
    """D-30: los botones que ``actor`` ve sobre ``cliente`` (un ``frozenset``): Vendedor y Gerente, «modificar» siempre; en un
    inactivo, «reactivar»; en un activo, «baja» solo el Gerente. Cualquier otro actor, ninguno. Ningún botón lleva a un 403."""
    if actor is None or not actor.is_active or rol_de(actor) not in (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR):
        return frozenset()
    acciones = {ACCION_MODIFICAR}
    if not cliente.activo:
        acciones.add(ACCION_REACTIVAR)
    elif rol_de(actor) == Usuario.Rol.GERENTE:
        acciones.add(ACCION_BAJA)
    return frozenset(acciones)
