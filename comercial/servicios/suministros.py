# Servicios de suministro (COM-03a): COM-PCT-SUM, Pactar Suministro, y COM-CNS-SUM, Consultar Suministro (docs/casos_de_uso/comercial/suministro.md,
# «Cómo se aplica en la ronda «Comercial 1»»). La consulta se suma en el paso 5 de la tarea, en este mismo archivo.
#
# El pacto en curso NO se guarda (pasos 2 a 13): vive en el formulario, como en COM-02. Cada cambio vuelve a pedir `datos_del_formulario`, que
# no escribe ni bloquea: calcula la fecha de fin, el calendario y el precio de cada detalle (`calendario.py`) y verifica el stock de los
# períodos de la ventana con `stock_maduro.simular_varias` (una consulta por tabla: nada por detalle). `pactar_suministro` es la única que escribe.
#
# Bloqueos de `pactar_suministro` (docs/patrones/stock_maduro.md, sección 3; ``FOR NO KEY UPDATE``): las cuentas del actor y del Vendedor (una
# consulta, por id) → los invernaderos considerados (`bloquear_invernadero_activo`, por id) → el cliente (y sus direcciones) → las variedades
# (por id) → los lotes y las partidas candidatos (por id, SOLO si algún período cae en la ventana) → las filas del contrato (suministro,
# cláusulas, detalles, reservas). Con todo bloqueado, el resultado de `asignar` ES la verificación del paso 14: si algún período no se cubre
# entero, `stock_insuficiente` y se revierte todo (extensión 14a). El correo sale DESPUÉS de confirmar (D-14, D-54).

import hashlib
import logging
import re
from collections import namedtuple
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404

from comercial.models import (
    AlertaComercial,
    Cliente,
    ClausulaSuministrado,
    ClausulaSuministrante,
    DetalleReserva,
    DetalleSuministro,
    DireccionCliente,
    DiscrepanciaEntrega,
    Entrega,
    Suministro,
)
from comercial.servicios import calendario, comprobantes, entregas, stock_maduro
from comercial.servicios import clientes as api_clientes
from comercial.servicios.compra_ventas import (
    CENTAVOS,
    MENSAJE_SIN_ACCESO,
    MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR,
    MENSAJE_SIN_VENDEDORES,
    NO_CAMPO,
    _entero,
    _exigir_actor,
    _fecha,
    _texto,
    _vendedores_con_invernaderos,
)
from comercial.servicios.pre_reserva import TIPO_DE_ALERTA as TIPO_DE_ALERTA_DE_PERIODO
from comercial.servicios.stock_maduro import Periodo
from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from core.procesos import ResumenDePaso
from inventario.servicios import stock
from inventario.servicios.variedades import bloquear_variedad
from maestros.models import Alerta, Direccion, Invernadero, Variedad
from maestros.servicios.invernaderos import bloquear_invernadero_activo

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR
MECANISMOS = DetalleSuministro.Mecanismo.values
IMPORTE_MAXIMO = Decimal("9999999.99")  # los `DecimalField(9, 2)` de las cláusulas y del precio
MULTA_MAXIMA = Decimal("99999999.99")  # el `DecimalField(10, 2)` de la multa
FECHAS_VISIBLES = 12  # paso 9: «si hay más de 12 fechas, las primeras 12 y “y N más”»
MENSAJE_STOCK_CAMBIO = "El stock cambió mientras cargabas el contrato."
CAMPOS = (
    "variedad", "direccion", "cantidad", "periodo", "primera_entrega", "mecanismo", "precio", "porcentaje", "meses", "plazo_entrega",
    "indemnizacion_retraso", "cantidad_minima", "indemnizacion_faltante", "continuar",
)
# El atributo de `RenglonDeSuministro` de cada campo del formulario (los demás se llaman igual).
ATRIBUTOS = {"variedad": "variedad_id", "direccion": "direccion_id", "continuar": "continuar_superpuesto"}


def siguiente_numero():
    """El número del próximo suministro, de la secuencia ``comercial_suministro_numero_seq`` (D-52 punto 3). Puede haber huecos si una
    transacción se deshace. Nunca un ``max()+1``."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_suministro_numero_seq')")
        return cursor.fetchone()[0]


# ---- lo que carga el formulario ----


@dataclass
class RenglonDeSuministro:
    """Un detalle del formulario, tal como llegó (texto). ``indice`` es su posición (nombra sus campos y sus errores). ``continuar_superpuesto``
    es la casilla «Continuar igual» de la advertencia 9d."""

    indice: int = 0
    variedad_id: str = ""
    direccion_id: str = ""
    cantidad: str = ""
    periodo: str = ""
    primera_entrega: str = ""
    mecanismo: str = "fijo"
    precio: str = ""
    porcentaje: str = ""
    meses: str = ""
    plazo_entrega: str = ""
    indemnizacion_retraso: str = ""
    cantidad_minima: str = ""
    indemnizacion_faltante: str = ""
    continuar_superpuesto: str = ""

    @property
    def vacio(self):
        """True si no se cargó nada (el mecanismo y la casilla no cuentan: tienen valor por omisión)."""
        return not any(
            _texto(getattr(self, ATRIBUTOS.get(c, c)))
            for c in CAMPOS
            if c not in ("mecanismo", "continuar")
        )


@dataclass
class DatosDeSuministro:
    """Lo que carga el formulario de COM-PCT-SUM, todo como texto. ``vendedor_id`` solo lo elige el Gerente (extensión 1a)."""

    vendedor_id: str = ""
    cliente_id: str = ""
    duracion: str = ""
    tolerados: str = ""
    multa: str = ""
    plazo_pago: str = ""
    indemnizacion_pago: str = ""
    renglones: list = field(default_factory=list)

    @classmethod
    def desde_post(cls, datos):
        """Arma los datos de un ``QueryDict`` (POST o GET): ``vendedor``, ``cliente``, ``duracion``, ``tolerados``, ``multa``, ``plazo_pago``,
        ``indemnizacion_pago`` y ``detalle-<i>-<campo>`` (``variedad``, ``direccion``, ``cantidad``, ``periodo``, ``primera_entrega``,
        ``mecanismo``, ``precio``, ``porcentaje``, ``meses``, ``plazo_entrega``, ``indemnizacion_retraso``, ``cantidad_minima``,
        ``indemnizacion_faltante`` y ``continuar``)."""
        renglones = {}
        for clave in datos:
            coincidencia = re.fullmatch(r"detalle-(\d+)-([a-z_]+)", clave)
            if coincidencia and coincidencia.group(2) in CAMPOS:
                indice, campo = int(coincidencia.group(1)), coincidencia.group(2)
                renglon = renglones.setdefault(indice, RenglonDeSuministro(indice))
                setattr(renglon, ATRIBUTOS.get(campo, campo), datos.get(clave, ""))
        return cls(
            vendedor_id=datos.get("vendedor", ""),
            cliente_id=datos.get("cliente", ""),
            duracion=datos.get("duracion", ""),
            tolerados=datos.get("tolerados", ""),
            multa=datos.get("multa", ""),
            plazo_pago=datos.get("plazo_pago", ""),
            indemnizacion_pago=datos.get("indemnizacion_pago", ""),
            renglones=[renglones[i] for i in sorted(renglones)],
        )


@dataclass
class Advertencia:
    """Una advertencia que no bloquea: ``superposicion`` (9d, con ``contrato``) o ``ajuste_sin_efecto`` (9f)."""

    codigo: str
    mensaje: str
    contrato: object = None


@dataclass
class PeriodoDeLaVentana:
    """Un período que cae dentro de la ventana de pre-reserva (se reserva al pactar): lo pedido y lo disponible después de los anteriores."""

    fecha: date
    cantidad: int
    disponible: int

    @property
    def alcanza(self):
        """True si lo disponible cubre lo pedido."""
        return self.disponible >= self.cantidad


@dataclass
class FilaDeSuministro:
    """Un detalle ya interpretado: sus valores, su calendario y su precio, su verificación de stock y sus errores y advertencias por campo."""

    renglon: RenglonDeSuministro
    variedad: object = None
    direccion: object = None
    cantidad: int | None = None
    periodo: int | None = None
    primera: date | None = None
    mecanismo: str = "fijo"
    precio: Decimal | None = None
    porcentaje: Decimal | None = None
    meses: int | None = None
    plazo_entrega: int | None = None
    indemnizacion_retraso: Decimal | None = None
    cantidad_minima: int | None = None
    indemnizacion_faltante: Decimal | None = None
    errores: dict = field(default_factory=dict)  # {campo sin prefijo: mensaje}
    advertencias: list = field(default_factory=list)
    cantidad_de_entregas: int = 0
    total_de_plantas: int = 0
    fechas_visibles: list = field(default_factory=list)
    fechas_restantes: int = 0
    ultima_fecha: date | None = None
    tramos_de_precio: list = field(default_factory=list)
    periodos_de_la_ventana: list = field(default_factory=list)
    fechas: list = field(default_factory=list)  # todas las del calendario (para ver cuáles caen en la ventana)


@dataclass
class FormularioDeSuministro:
    """Lo que muestra la pantalla de «Pactar suministro» en cada cambio (``datos_del_formulario``)."""

    datos: DatosDeSuministro
    es_gerente: bool
    vendedor: object  # el responsable (el actor, o el que eligió el Gerente), o None
    vendedores: list  # [(Vendedor, [Invernadero])] para el Gerente (extensión 1a)
    cliente: object
    direcciones: list  # las direcciones activas del cliente (hijas)
    habilitados: list  # los invernaderos de donde puede salir el stock
    fecha_fin: date | None
    contrato: object  # los datos del contrato ya interpretados (duracion, tolerados, multa, plazo_pago, indemnizacion_pago)
    ventana: date
    variedades_ofrecidas: list
    filas: list
    errores: dict  # {campo: [mensaje]}; las generales, bajo NO_CAMPO
    codigos: dict  # {campo: [código]}, en el mismo orden
    seccion_2_habilitada: bool
    seccion_3_habilitada: bool
    cliente_sin_correo: bool

    @property
    def cargadas(self):
        """Los detalles con algo cargado. En pantalla (no estricto) ``filas`` también trae los renglones en blanco que dejó «Agregar detalle»;
        estos no cuentan como detalles del contrato."""
        return [f for f in self.filas if not f.renglon.vacio]

    @property
    def puede_revisar(self):
        """Se puede abrir el resumen: nada con error, al menos un detalle cargado, el cliente elegido y el Vendedor responsable definido."""
        return not self.errores and bool(self.cargadas) and self.cliente is not None and self.vendedor is not None


# ---- validación de valores ----


class _Errores:
    """Los errores del análisis por campo, con su código: ``mensajes[campo] = [texto]`` y ``codigos[campo] = [código]``."""

    def __init__(self):
        self.mensajes = {}
        self.codigos = {}

    def agregar(self, campo, codigo, mensaje):
        self.mensajes.setdefault(campo, []).append(mensaje)
        self.codigos.setdefault(campo, []).append(codigo)


def _decimal(texto):
    """El ``Decimal`` de un texto con coma decimal («1.500,50», «1500,50») o con punto («1500.50»), de hasta dos decimales; ``None`` si no vale."""
    texto = _texto(texto).replace(" ", "").replace("$", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", texto):
        return None
    valor = Decimal(texto)
    return valor if valor == valor.quantize(CENTAVOS) else None


def _importe(texto, minimo, maximo):
    """El importe de ``texto`` entre ``minimo`` y ``maximo`` (con dos decimales), o ``None``."""
    valor = _decimal(texto)
    return valor.quantize(CENTAVOS) if valor is not None and minimo <= valor <= maximo else None


def _entero_entre(texto, minimo, maximo):
    """El entero de ``texto`` entre ``minimo`` y ``maximo``, o ``None``."""
    valor = _entero(texto)
    return valor if valor is not None and minimo <= valor <= maximo else None


def _fecha_texto(fecha):
    """«dd/mm/aaaa»."""
    return f"{fecha:%d/%m/%Y}"


# ---- el análisis (compartido por el formulario, el resumen y el registro) ----


def puede_pactar(actor):
    """Precondiciones b y c: ``(True, "")`` si hay con qué pactar; si no, ``(False, motivo)`` para mostrar «Pactar suministro» deshabilitado."""
    _exigir_actor(actor)
    if rol_de(actor) == GERENTE:
        if not _vendedores_con_invernaderos():
            return False, MENSAJE_SIN_VENDEDORES
    elif not Invernadero.objects.filter(vendedor_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).exists():
        return False, MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR
    if not Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO).exists():
        return False, "No hay variedades activas."
    return True, ""


def _analizar(actor, datos, estricto):
    """Interpreta los ``datos`` sin escribir ni bloquear: el Vendedor responsable, el cliente, el contrato, cada detalle con su calendario, su
    precio y su verificación de stock acumulada, con sus errores por campo (pasos 1 a 12). Con ``estricto`` (resumen y registro) exige además lo
    que falte; sin él (cada cambio de la pantalla) lo que todavía no se eligió no es un error, y una dirección que ya no corresponde se descarta
    en silencio (extensiones 13a.1a a 13a.1c). Devuelve un ``FormularioDeSuministro``."""
    _exigir_actor(actor)
    hoy = stock.hoy()
    ventana = calendario.ventana(hoy)  # una sola lectura de la configuración, no una por detalle
    err = _Errores()
    es_gerente = rol_de(actor) == GERENTE

    # Paso 1 y extensión 1a: el Vendedor responsable (regla «Vendedor responsable»).
    vendedores, vendedor, invernaderos_del_vendedor = [], None, []
    if es_gerente:
        vendedores = _vendedores_con_invernaderos()
        elegido = _entero(datos.vendedor_id)
        encontrado = next(((v, i) for v, i in vendedores if v.pk == elegido), None)
        if encontrado:
            vendedor, invernaderos_del_vendedor = encontrado
        elif _texto(datos.vendedor_id):
            err.agregar("vendedor", "vendedor_invalido", "Elegí un Vendedor activo con invernaderos activos.")
        elif estricto:
            err.agregar("vendedor", "vendedor_obligatorio", "Elegí el Vendedor responsable del contrato.")
    else:
        vendedor = actor
        invernaderos_del_vendedor = list(
            Invernadero.objects.filter(vendedor_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("pk")
        )
        if estricto and not invernaderos_del_vendedor:
            err.agregar(NO_CAMPO, "vendedor_sin_invernaderos", MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR)

    # Pasos 2 a 4 y 3a: el cliente (solo activo y con correo, regla 18 de 8.20).
    cliente = None
    if _texto(datos.cliente_id):
        cliente = Cliente.objects.filter(pk=_entero(datos.cliente_id)).first() if _entero(datos.cliente_id) else None
        if cliente is None:
            err.agregar("cliente", "cliente_obligatorio", "Elegí un cliente de la lista.")
        elif not cliente.activo:
            err.agregar("cliente", "cliente_inactivo", "El cliente está dado de baja: reactivalo para pactarle un suministro.")
    elif estricto:
        err.agregar("cliente", "cliente_obligatorio", "Elegí el cliente.")
    cliente_valido = cliente is not None and cliente.activo
    cliente_sin_correo = bool(cliente_valido and not cliente.email_cliente)
    if cliente_sin_correo and estricto:
        err.agregar(
            "cliente",
            "cliente_sin_correo",
            "El cliente no tiene correo. Hace falta para el comprobante y para los enlaces de confirmación de cada entrega.",
        )
    seccion_2 = cliente_valido and not cliente_sin_correo

    # Pasos 5, 6 y 6a: los datos del contrato y de la cláusula del suministrado.
    def validar(campo, texto, valor, codigo, mensaje):
        if not _texto(texto):
            if estricto:
                err.agregar(campo, codigo, mensaje)
        elif valor is None:
            err.agregar(campo, codigo, mensaje)

    duracion = _entero_entre(datos.duracion, 1, 120)
    contrato = SimpleNamespace(  # los datos del contrato ya interpretados (``None`` si no valen), para el resumen
        duracion=duracion,
        tolerados=_entero_entre(datos.tolerados, 0, 99),
        multa=_importe(datos.multa, Decimal(0), MULTA_MAXIMA),
        plazo_pago=_entero_entre(datos.plazo_pago, 0, 365),
        indemnizacion_pago=_importe(datos.indemnizacion_pago, Decimal(0), IMPORTE_MAXIMO),
    )
    validar("duracion", datos.duracion, duracion, "duracion_invalida", "Ingresá un número entero de meses, de 1 a 120.")
    validar("tolerados", datos.tolerados, contrato.tolerados, "tolerados_invalidos", "Ingresá un número entero, de 0 a 99.")
    validar("multa", datos.multa, contrato.multa, "multa_invalida", "Ingresá un importe de $ 0 a $ 99.999.999,99.")
    validar("plazo_pago", datos.plazo_pago, contrato.plazo_pago, "plazo_pago_invalido", "Ingresá un número entero de días, de 0 a 365.")
    validar(
        "indemnizacion_pago", datos.indemnizacion_pago, contrato.indemnizacion_pago,
        "indemnizacion_pago_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.",
    )
    fecha_fin = calendario.sumar_meses(hoy, duracion) if duracion is not None else None

    direcciones = api_clientes.direcciones_activas(cliente) if cliente_valido else []
    por_direccion = {d.pk: d for d in direcciones}
    activas = list(
        Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO).select_related("cultivo").order_by("cultivo__nombre_cultivo", "nombre_variedad")
    )
    por_variedad = {v.pk: v for v in activas}

    # Pasos 7 a 11: cada detalle. En pantalla (no estricto) los renglones en blanco se conservan, sin errores; al resumir o registrar se ignoran.
    renglones = [r for r in datos.renglones if estricto is False or not r.vacio]
    filas = [_fila(r, estricto, err, hoy, duracion, fecha_fin, por_variedad, por_direccion, cliente_valido) for r in renglones]
    cargadas = [f for f in filas if not f.renglon.vacio]
    if estricto and not cargadas:
        err.agregar(NO_CAMPO, "sin_detalles", "El contrato tiene que tener al menos un detalle.")

    # Extensión 9c: el contrato no repite el par (variedad, dirección).
    vistos = {}
    for posicion, fila in enumerate(cargadas, start=1):
        if fila.variedad is not None and fila.direccion is not None:
            par = (fila.variedad.pk, fila.direccion.pk)
            if par in vistos:
                err.agregar(
                    f"detalle-{fila.renglon.indice}-variedad",
                    "par_repetido",
                    f"El contrato ya tiene {fila.variedad} para esa dirección: es el detalle {vistos[par]}.",
                )
            else:
                vistos[par] = posicion

    _repartir_errores(filas, err)  # los de validación y los del par repetido: con ellos, el detalle no entra en la verificación de stock
    _advertir_superposiciones(cargadas, cliente if cliente_valido else None, estricto, err)
    habilitados = invernaderos_del_vendedor if vendedor is not None else []
    _verificar_stock(cargadas, vendedor, habilitados, ventana, err)
    _repartir_errores(filas, err)
    ofrecidas = activas
    return FormularioDeSuministro(
        datos=datos,
        es_gerente=es_gerente,
        vendedor=vendedor,
        vendedores=vendedores,
        cliente=cliente if cliente_valido else None,
        direcciones=direcciones,
        habilitados=habilitados,
        fecha_fin=fecha_fin,
        contrato=contrato,
        ventana=ventana,
        variedades_ofrecidas=ofrecidas,
        filas=filas,
        errores=err.mensajes,
        codigos=err.codigos,
        seccion_2_habilitada=seccion_2,
        seccion_3_habilitada=seccion_2,
        cliente_sin_correo=cliente_sin_correo,
    )


def _repartir_errores(filas, err):
    """Pone en cada detalle sus errores por campo (sin el prefijo ``detalle-<i>-``): el primer mensaje de cada uno."""
    for fila in filas:
        prefijo = f"detalle-{fila.renglon.indice}-"
        fila.errores = {c[len(prefijo):]: m[0] for c, m in err.mensajes.items() if c.startswith(prefijo)}


def _fila(renglon, estricto, err, hoy, duracion, fecha_fin, por_variedad, por_direccion, cliente_valido):
    """Interpreta un detalle: sus valores, sus errores (pasos 8 a 11 y extensiones 8a, 8b, 9a, 9b, 11a y 11b) y su calendario y su precio (paso 9)."""
    fila = FilaDeSuministro(renglon)
    if renglon.vacio:  # solo llega acá en pantalla: se muestra para completar, sin validar nada
        return fila
    nombre = lambda campo: f"detalle-{renglon.indice}-{campo}"  # noqa: E731

    def validar(campo, texto, valor, codigo, mensaje):
        """Un error si el texto está cargado y no vale, o si falta y se exige (resumen y registro)."""
        if (_texto(texto) or estricto) and valor is None:
            err.agregar(nombre(campo), codigo, mensaje)
        return valor

    # Variedad (paso 7: solo las activas).
    if not _texto(renglon.variedad_id):
        if estricto:
            err.agregar(nombre("variedad"), "variedad_obligatoria", "Elegí la variedad.")
    else:
        fila.variedad = por_variedad.get(_entero(renglon.variedad_id))
        if fila.variedad is None:
            err.agregar(nombre("variedad"), "variedad_inactiva", "Esa variedad no está disponible.")
    # Dirección (8a): una activa del cliente; si no corresponde (cambió el cliente, 13a.1b), en pantalla se descarta sin error.
    if not _texto(renglon.direccion_id):
        if estricto:
            err.agregar(nombre("direccion"), "direccion_obligatoria", "Elegí la dirección de entrega.")
    else:
        fila.direccion = por_direccion.get(_entero(renglon.direccion_id))
        if fila.direccion is None and estricto:
            err.agregar(nombre("direccion"), "direccion_no_valida", "Esa no es una dirección activa del cliente.")
    # Datos del detalle (9b).
    fila.cantidad = validar("cantidad", renglon.cantidad, _entero_entre(renglon.cantidad, 1, 500000), "cantidad_invalida", "Ingresá un número entero de plantas, de 1 a 500.000.")
    fila.periodo = validar("periodo", renglon.periodo, _entero_entre(renglon.periodo, 1, 365), "periodo_invalido", "Ingresá un número entero de días, de 1 a 365.")
    # Primera entrega (9a): entre hoy y la fecha de fin.
    if not _texto(renglon.primera_entrega):
        if estricto:
            err.agregar(nombre("primera_entrega"), "fecha_obligatoria", "Ingresá la fecha de la primera entrega.")
    else:
        fecha = _fecha(renglon.primera_entrega)
        if fecha is None:
            err.agregar(nombre("primera_entrega"), "fecha_invalida", "Ingresá una fecha válida (dd/mm/aaaa).")
        elif fecha < hoy or (fecha_fin is not None and fecha > fecha_fin):
            if fecha_fin is not None:
                mensaje = f"Entre el {_fecha_texto(hoy)} y el {_fecha_texto(fecha_fin)}."
            else:
                mensaje = f"No puede ser anterior al {_fecha_texto(hoy)}."
            err.agregar(nombre("primera_entrega"), "fecha_fuera_de_rango", mensaje)
        else:
            fila.primera = fecha
    # Precio y mecanismo (8b, «Datos del precio»).
    mecanismo = _texto(renglon.mecanismo)
    if mecanismo not in MECANISMOS:
        err.agregar(nombre("mecanismo"), "mecanismo_invalido", "Elegí el mecanismo de precio: fijo o ajuste periódico.")
    else:
        fila.mecanismo = mecanismo
    fila.precio = validar("precio", renglon.precio, _importe(renglon.precio, Decimal("0.01"), IMPORTE_MAXIMO), "precio_invalido", "Ingresá un precio de $ 0,01 a $ 9.999.999,99, con hasta dos decimales.")
    if fila.mecanismo == DetalleSuministro.Mecanismo.AJUSTE_PERIODICO:
        porcentaje = _importe(renglon.porcentaje, Decimal("0.01"), Decimal(100))
        fila.porcentaje = validar("porcentaje", renglon.porcentaje, porcentaje, "porcentaje_invalido", "Ingresá un porcentaje de 0,01 a 100.")
        fila.meses = validar("meses", renglon.meses, _entero_entre(renglon.meses, 1, 60), "meses_invalidos", "Ingresá un número entero de meses, de 1 a 60.")
    # Cláusula del suministrante (10, 11a y 11b).
    fila.plazo_entrega = validar("plazo_entrega", renglon.plazo_entrega, _entero_entre(renglon.plazo_entrega, 0, 365), "plazo_entrega_invalido", "Ingresá un número entero de días, de 0 a 365.")
    fila.indemnizacion_retraso = validar(
        "indemnizacion_retraso", renglon.indemnizacion_retraso, _importe(renglon.indemnizacion_retraso, Decimal(0), IMPORTE_MAXIMO),
        "indemnizacion_retraso_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.",
    )
    tope = fila.cantidad or 500000
    fila.cantidad_minima = validar(
        "cantidad_minima", renglon.cantidad_minima, _entero_entre(renglon.cantidad_minima, 1, tope), "cantidad_minima_invalida",
        f"Ingresá un número entero de plantas, de 1 a {tope}.",
    )
    fila.indemnizacion_faltante = validar(
        "indemnizacion_faltante", renglon.indemnizacion_faltante, _importe(renglon.indemnizacion_faltante, Decimal(0), IMPORTE_MAXIMO),
        "indemnizacion_faltante_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.",
    )
    # Extensión 9f: un ajuste que nunca se aplica.
    if fila.meses is not None and duracion is not None and fila.meses > duracion:
        fila.advertencias.append(
            Advertencia(
                "ajuste_sin_efecto",
                f"El precio no se ajustará durante el contrato: el primer ajuste sería el {_fecha_texto(calendario.sumar_meses(hoy, fila.meses))}, después del fin.",
            )
        )
    # Paso 9: calendario y precio de cada entrega.
    if fila.periodo is not None and fila.primera is not None and fecha_fin is not None:
        provisorio = SimpleNamespace(
            fecha_primer_entrega=fila.primera,
            periodo_entrega_dias=fila.periodo,
            fecha_fin_detalle=None,
            suministro=SimpleNamespace(fecha_fin=fecha_fin),
            mecanismo_precio=fila.mecanismo,
            precio_unitario_suministro=fila.precio if fila.precio is not None else Decimal(0),
            porcentaje_ajuste=fila.porcentaje,
            meses_ajuste=fila.meses,
            fecha_base_ajuste=hoy,
        )
        fechas = calendario.calendario(provisorio)
        fila.cantidad_de_entregas = len(fechas)
        fila.total_de_plantas = len(fechas) * (fila.cantidad or 0)
        fila.fechas_visibles = fechas[:FECHAS_VISIBLES]
        fila.fechas_restantes = max(0, len(fechas) - FECHAS_VISIBLES)
        fila.ultima_fecha = fechas[-1] if fechas else None
        if fila.precio is not None and (fila.mecanismo == "fijo" or (fila.porcentaje is not None and fila.meses is not None)):
            fila.tramos_de_precio = calendario.tramos_de_precio(provisorio)
        fila.fechas = fechas
    return fila


def _advertir_superposiciones(cargadas, cliente, estricto, err, excluir=None):
    """Extensión 9d: el cliente ya tiene otro suministro vigente de la misma variedad a la misma dirección. Advertencia con el código del otro
    contrato y su casilla «Continuar igual»; al resumir o registrar, sin la casilla, es un error (continuar es una decisión explícita). Dos
    consultas, igual con uno que con muchos detalles. ``excluir`` es el contrato que se modifica (COM-MOD-SUM): no se superpone consigo mismo."""
    pares = [(f.variedad.pk, f.direccion.pk) for f in cargadas if f.variedad is not None and f.direccion is not None]
    if cliente is None or not pares:
        return
    filas = DetalleSuministro.objects.filter(
        suministro__cliente=cliente,
        suministro__estado_suministro=Suministro.Estado.VIGENTE,
        estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE,
        variedad_id__in={v for v, _ in pares},
        direccion_id__in={d for _, d in pares},
    )
    if excluir is not None:  # COM-MOD-SUM (5b.2): los detalles del propio contrato los trata el par vigente, no la superposición
        filas = filas.exclude(suministro_id=excluir)
    filas = filas.order_by("suministro_id").values_list("variedad_id", "direccion_id", "suministro_id")
    de_cada_par = {}
    for variedad_id, direccion_id, suministro_id in filas:
        de_cada_par.setdefault((variedad_id, direccion_id), suministro_id)
    contratos = {s.pk: s for s in Suministro.objects.filter(pk__in=set(de_cada_par.values()))}
    for fila in cargadas:
        if fila.variedad is None or fila.direccion is None:
            continue
        otro = contratos.get(de_cada_par.get((fila.variedad.pk, fila.direccion.pk)))
        if otro is None:
            continue
        fila.advertencias.append(
            Advertencia(
                "superposicion",
                f"El cliente ya tiene el suministro vigente {otro.codigo} de {fila.variedad} a esa dirección. Si querés cambiar sus condiciones, "
                "corresponde modificarlo.",
                otro,
            )
        )
        if estricto and _texto(fila.renglon.continuar_superpuesto) != "1":
            err.agregar(
                f"detalle-{fila.renglon.indice}-continuar",
                "superposicion_sin_confirmar",
                f"Marcá «Continuar igual» para pactarlo aunque el cliente ya tenga {otro.codigo}.",
            )


def _verificar_stock(cargadas, vendedor, habilitados, ventana, err):
    """Extensión 9e y regla «Stock maduro libre»: los períodos de la ventana de pre-reserva de todos los detalles se cubren **en orden de fecha**
    (después, el orden del formulario), por variedad, cada uno contra lo que dejan libre los anteriores (``simular_varias``, una consulta por
    tabla). Guarda en cada detalle sus períodos con lo disponible y marca el primero que no alcanza."""
    pedidos = {}  # {variedad_id: [(fecha, cantidad, fila)]}
    for fila in cargadas:
        if fila.variedad is None or fila.cantidad is None or not fila.fechas:
            continue
        for fecha in fila.fechas:
            if fecha <= ventana:
                pedidos.setdefault(fila.variedad.pk, []).append((fecha, fila.cantidad, fila))
    if not pedidos or vendedor is None or not habilitados:
        return
    for lista in pedidos.values():
        lista.sort(key=lambda p: p[0])  # estable: a igual fecha, el orden del formulario
    cobertura = stock_maduro.simular_varias(
        {v: [(fecha, cantidad) for fecha, cantidad, _ in lista] for v, lista in pedidos.items()}, [i.pk for i in habilitados], "suministro"
    )
    for variedad_id, lista in pedidos.items():
        for (fecha, cantidad, fila), cubierta in zip(lista, cobertura[variedad_id]):
            fila.periodos_de_la_ventana.append(PeriodoDeLaVentana(fecha, cantidad, cubierta.disponible))
            campo = f"detalle-{fila.renglon.indice}-cantidad"
            if not fila.periodos_de_la_ventana[-1].alcanza and campo not in err.mensajes:
                err.agregar(
                    campo,
                    "supera_disponible",
                    f"El {fecha:%d/%m} hay {cubierta.disponible} plantas disponibles de {fila.variedad} después de los períodos anteriores.",
                )
    for fila in cargadas:
        fila.periodos_de_la_ventana.sort(key=lambda p: p.fecha)


def datos_del_formulario(actor, datos):
    """Lo que muestra la pantalla en cada cambio (pasos 2 a 11 y extensiones 1a, 8a, 8b, 9a a 9f, 11a, 11b y 13a.1a a 13a.1c): el Vendedor,
    las direcciones, la fecha de fin, el calendario y el precio de cada detalle, los períodos de la ventana con su disponible, las
    advertencias y los errores por campo. **No escribe ni bloquea**; consultas fijas, sin consultas por detalle."""
    return _analizar(actor, datos, estricto=False)


def _lanzar(errores, codigos):
    """Un ``ValidationError`` con un error por campo y su código."""
    raise ValidationError(
        {campo: [ValidationError(mensaje, code=codigos[campo][i]) for i, mensaje in enumerate(mensajes)] for campo, mensajes in errores.items()}
    )


# ---- resumen (paso 12) ----


@dataclass
class ResumenDeSuministro:
    """El resumen del paso 12: cliente, Vendedor responsable, contrato y cada detalle con su calendario, su precio y su cláusula."""

    formulario: FormularioDeSuministro

    @property
    def filas(self):
        return self.formulario.cargadas


def resumen(actor, datos):
    """Paso 12: valida todo como al registrar (``ValidationError`` por campo si algo falta o ya no alcanza) y arma el resumen. No escribe."""
    formulario = _analizar(actor, datos, estricto=True)
    if formulario.errores:
        _lanzar(formulario.errores, formulario.codigos)
    return ResumenDeSuministro(formulario)


# ---- pacto (pasos 13 a 16) ----


def _error_de_campo(campo, mensaje, codigo):
    """Un ``ValidationError`` de un solo campo."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def _periodos_a_reservar(filas, ventana):
    """Los períodos de la ventana de todos los detalles, en el orden de la sección 7 del patrón: por fecha, después por variedad, después por
    el orden de los detalles en el formulario. ``[(fecha, variedad_id, posición, fila)]``."""
    lista = [
        (fecha, fila.variedad.pk, posicion, fila)
        for posicion, fila in enumerate(filas)
        for fecha in fila.fechas
        if fecha <= ventana
    ]
    lista.sort(key=lambda p: p[:3])
    return lista


def pactar_suministro(actor, datos):
    """COM-PCT-SUM: pacta el suministro con sus cláusulas, detalles, reservas y cosechas, y lo devuelve (con ``periodos_reservados`` y
    ``cosechas_programadas``).

    - Precondición a: Vendedor o Gerente activo (``PermissionDenied``). Reglas y extensiones 1a, 3a, 4a, 4b, 6a, 8a, 8b, 9a a 9e, 11a, 11b y 12a:
      ``ValidationError`` por campo (``cliente_sin_correo``, ``fecha_fuera_de_rango``, ``par_repetido``, ``superposicion_sin_confirmar``,
      ``supera_disponible``, ``sin_detalles``…).
    - Paso 14 en UNA transacción, con los bloqueos del encabezado: cuentas, invernaderos, cliente (vuelve a verificar que siga activo, con
      correo y con cada dirección activa y suya), variedades, y, solo si algún período cae en la ventana, lotes y partidas. Por cada período de
      la ventana, ``asignar``; si alguno queda sin cubrir, ``stock_insuficiente`` con lo que había y se revierte todo (extensión 14a).
    - Postcondiciones a a e: el suministro «vigente», su cláusula del suministrado, sus detalles «vigentes» con su cláusula del suministrante,
      una reserva por invernadero de cada período de la ventana y sus cosechas (``stock_maduro``).
    - Postcondiciones h e i y D-36: UN registro ``pacto_suministro`` (el Gerente queda como quien lo cargó; el Vendedor responsable va en ``datos``).
    - Paso 15, FUERA de la transacción (D-14, D-54): el comprobante. Queda «para imprimir» (sin correo), «enviado» o «pendiente de envío».
    - Postcondición f (planificar la entrega de un período que salió todo de cámara): `entregas.programar_para_reservas` (COM-05a1), con `on_commit`.
    """
    previo = _analizar(actor, datos, estricto=True)
    if previo.errores:
        _lanzar(previo.errores, previo.codigos)
    vendedor_id = previo.vendedor.pk
    filas = previo.cargadas
    hoy = stock.hoy()
    periodos = _periodos_a_reservar(filas, previo.ventana)
    with transaction.atomic():
        cuentas = {
            u.pk: u
            for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, vendedor_id}).order_by("pk")
        }
        quien = cuentas.get(actor.pk)
        if quien is None or not quien.is_active or rol_de(quien) not in (GERENTE, VENDEDOR):
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        responsable = cuentas.get(vendedor_id)
        if responsable is None or not responsable.is_active or rol_de(responsable) != VENDEDOR:
            raise _error_de_campo("vendedor", "El Vendedor ya no está activo.", "vendedor_inactivo")

        bloqueados = []
        for invernadero in previo.habilitados:
            try:
                actual = bloquear_invernadero_activo(invernadero.pk)
            except ValidationError:
                continue  # se dio de baja mientras se cargaba el contrato
            if actual.vendedor_id == vendedor_id:
                bloqueados.append(actual)
        ahora = set(
            Invernadero.objects.filter(vendedor_id=vendedor_id, estado_invernadero=Invernadero.Estado.ACTIVO).values_list("pk", flat=True)
        )
        if not bloqueados and not ahora:
            raise _error_de_campo(NO_CAMPO, MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR, "vendedor_sin_invernaderos")
        if not ahora <= {i.pk for i in bloqueados}:
            raise ValidationError(
                "Mientras cargabas el contrato, cambiaron los invernaderos del Vendedor. Volvé a intentarlo.", code="cambio_simultaneo"
            )

        cliente = Cliente.objects.select_for_update(no_key=True).filter(pk=previo.cliente.pk).first()
        if cliente is None or not cliente.activo:
            raise _error_de_campo("cliente", "El cliente se dio de baja mientras cargabas el contrato.", "cliente_inactivo")
        if not cliente.email_cliente:
            raise _error_de_campo("cliente", "El cliente ya no tiene correo: hace falta para pactar un suministro.", "cliente_sin_correo")
        activas = set(
            DireccionCliente.objects.filter(cliente=cliente, direccion__estado_direccion=Direccion.Estado.ACTIVO).values_list("direccion_id", flat=True)
        )
        for fila in filas:
            if fila.direccion.pk not in activas:
                raise _error_de_campo(f"detalle-{fila.renglon.indice}-direccion", "La dirección ya no está activa: elegí otra.", "direccion_no_valida")

        for variedad_id in sorted({f.variedad.pk for f in filas}):
            try:
                bloquear_variedad(variedad_id)
            except ValidationError as error:
                fila = next(f for f in filas if f.variedad.pk == variedad_id)
                raise _error_de_campo(f"detalle-{fila.renglon.indice}-variedad", "Esa variedad ya no está disponible.", "variedad_inactiva") from error
        if periodos:  # sin períodos en la ventana no se lee ni se bloquea nada de lotes ni de partidas
            stock_maduro.bloquear_candidatos(sorted({f.variedad.pk for f in filas}), [i.pk for i in bloqueados])

        suministro = Suministro.objects.create(
            tipo_contrato=Suministro.Tipo.SUMINISTRO,
            numero=siguiente_numero(),
            fecha_realizacion=hoy,
            estado_comprobante=Suministro.EstadoDelComprobante.PENDIENTE_ENVIO,  # el envío lo pasa a «enviado» o «para imprimir»
            cliente=cliente,
            vendedor_id=vendedor_id,
            duracion_meses=int(datos.duracion),
            estado_suministro=Suministro.Estado.VIGENTE,
            fecha_fin=previo.fecha_fin,
            incumplimientos_tolerados=int(datos.tolerados),
            multa_resolucion=_importe(datos.multa, Decimal(0), MULTA_MAXIMA),
        )
        clausula = ClausulaSuministrado.objects.create(
            suministro=suministro,
            plazo_pago_dias=int(datos.plazo_pago),
            indemnizacion_retraso_pago=_importe(datos.indemnizacion_pago, Decimal(0), IMPORTE_MAXIMO),
        )
        detalles, clausulas = [], []
        for fila in filas:
            ajuste = fila.mecanismo == DetalleSuministro.Mecanismo.AJUSTE_PERIODICO
            detalle = DetalleSuministro.objects.create(
                suministro=suministro,
                direccion_id=fila.direccion.pk,
                variedad=fila.variedad,
                periodo_entrega_dias=fila.periodo,
                fecha_primer_entrega=fila.primera,
                cantidad_por_periodo=fila.cantidad,
                mecanismo_precio=fila.mecanismo,
                estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE,
                precio_unitario_suministro=fila.precio,
                porcentaje_ajuste=fila.porcentaje if ajuste else None,
                meses_ajuste=fila.meses if ajuste else None,
                fecha_base_ajuste=hoy,
            )
            detalles.append(detalle)
            clausulas.append(
                ClausulaSuministrante.objects.create(
                    detalle=detalle,
                    plazo_entrega_dias=fila.plazo_entrega,
                    indemnizacion_retraso_entrega=fila.indemnizacion_retraso,
                    cantidad_minima=fila.cantidad_minima,
                    indemnizacion_faltante=fila.indemnizacion_faltante,
                )
            )
        por_fila = dict(zip(map(id, filas), detalles))

        reservas, cosechas, maximos = [], [], {}
        for fecha, _variedad_id, posicion, fila in periodos:
            resultado = stock_maduro.asignar(actor, Periodo(por_fila[id(fila)], fecha), fila.cantidad, fecha, "suministro")
            reservas.extend(resultado.reservas)
            cosechas.extend(resultado.cosechas)
            if resultado.sin_cubrir:
                maximos[posicion] = min(maximos.get(posicion, resultado.cubierta), resultado.cubierta)
        if maximos:
            errores = {
                f"detalle-{filas[posicion].renglon.indice}-cantidad": [
                    ValidationError(f"Hay {maximo} plantas disponibles para esa fecha.", code="stock_insuficiente")
                ]
                for posicion, maximo in maximos.items()
            }
            errores[NO_CAMPO] = [ValidationError(MENSAJE_STOCK_CAMBIO, code="stock_insuficiente")]
            raise ValidationError(errores)  # revierte todo (extensión 14a; garantía mínima 1)

        lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).select_related("lote", "partida").order_by("pk"))
        datos_de_auditoria = {
            "suministro": referencia(suministro),
            "vendedor": referencia(responsable),
            "cliente": referencia(cliente),
            "fecha_realizacion": f"{hoy:%d/%m/%Y}",
            "duracion_meses": str(suministro.duracion_meses),
            "fecha_fin": f"{suministro.fecha_fin:%d/%m/%Y}",
            "estado_suministro": suministro.estado_suministro,
            "incumplimientos_tolerados": str(suministro.incumplimientos_tolerados),
            "multa_resolucion": f"{suministro.multa_resolucion:.2f}",
            "clausula_suministrado": f"pago a {clausula.plazo_pago_dias} días; atraso {clausula.indemnizacion_retraso_pago:.2f} por día",
            "detalles": [
                f"{d.variedad}: {d.cantidad_por_periodo} cada {d.periodo_entrega_dias} días desde {d.fecha_primer_entrega:%d/%m/%Y} a {d.precio_unitario_suministro}"
                for d in detalles
            ],
            "periodos_reservados": str(len(periodos)),
            "reservas": [f"{r} · {r.invernadero} · {r.get_estado_reserva_display().lower()}" for r in reservas],
            "lineas": [
                f"{next(r for r in reservas if r.pk == l.reserva_id)} → {(l.lote or l.partida).codigo}: {l.cantidad_reservada}" for l in lineas
            ],
            "cosechas": [c.codigo for c in cosechas],
        }
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.PACTO_SUMINISTRO,
            afectados=[suministro, clausula, *[x for par in zip(detalles, clausulas) for x in par], *reservas, *lineas, *cosechas],
            detalle={"datos": datos_de_auditoria},
        )
        entregas.programar_para_reservas([r.pk for r in reservas])  # postcondición f (D-66 punto 5): los períodos que salieron todo de cámara se planifican después de confirmar

    # Paso 15 y extensión 15a: FUERA de la transacción (D-14, D-54).
    suministro.estado_comprobante = comprobantes.enviar_comprobante(suministro)
    if suministro.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        comprobantes.avisar_comprobante_pendiente(actor, suministro)
    suministro.periodos_reservados = len(periodos)
    suministro.cosechas_programadas = len(cosechas)
    return suministro


def datos_del_comprobante(suministro):
    """Lo que dicen el comprobante por correo y la página imprimible (variación de datos 15a): el contrato, el cliente, el Vendedor, la cláusula del
    suministrado y, por detalle, variedad, dirección, cantidad, período, **calendario resumido** (primera y última fecha, cantidad de entregas y
    tramos de precio; no cada fecha, que puede pasar de 500), precio y mecanismo y su cláusula del suministrante."""
    suministro = Suministro.objects.select_related("cliente", "vendedor", "clausula_suministrado").get(pk=suministro.pk)
    filas = []
    for d in suministro.detalles.select_related("variedad__cultivo", "clausula_suministrante").order_by("pk"):
        fechas = calendario.calendario(d)
        hija = api_clientes.direccion_hija(d.direccion_id)
        filas.append(
            SimpleNamespace(
                detalle=d,
                variedad=d.variedad,
                direccion=f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else "",
                cantidad=d.cantidad_por_periodo,
                periodo=d.periodo_entrega_dias,
                primera_fecha=fechas[0] if fechas else None,
                ultima_fecha=fechas[-1] if fechas else None,
                cantidad_de_entregas=len(fechas),
                tramos_de_precio=calendario.tramos_de_precio(d),
                mecanismo=d.get_mecanismo_precio_display(),
                precio_inicial=d.precio_unitario_suministro,
                porcentaje=d.porcentaje_ajuste,
                meses=d.meses_ajuste,
                clausula=d.clausula_suministrante,
            )
        )
    return {
        "suministro": suministro,
        "cliente": suministro.cliente,
        "vendedor": suministro.vendedor,
        "clausula": suministro.clausula_suministrado,
        "filas": filas,
    }


# ---- consulta (COM-CNS-SUM) ----

POR_PAGINA = 50
POR_PAGINA_DEL_CALENDARIO = 100
DIAS_ATRAS_DEL_CALENDARIO = 30
DIAS_ADELANTE_DEL_CALENDARIO = 28
TEXTOS_DE_SITUACION = {"pasado": "Pasado", "reservado": "Reservado", "fuera_de_la_ventana": "Fuera de la ventana", "entrega_planificada": "Entrega planificada", "entregado": "Entregado"}


@dataclass
class FiltrosDeSuministros:
    """Regla 2 de COM-CNS-SUM: cliente, estado, rango de fechas (de realización o de fin) y, solo para el Gerente, Vendedor."""

    cliente_id: str = ""
    cliente_texto: str = ""  # buscador del cliente: CUIT, nombre, apellido o razón social (desde 2 caracteres)
    estado: str = ""
    fecha_de: str = "realizacion"
    desde: str = ""
    hasta: str = ""
    vendedor_id: str = ""

    @classmethod
    def desde_get(cls, datos):
        """Los filtros de la URL (se pueden compartir y volver con «Atrás»)."""
        return cls(
            cliente_id=datos.get("cliente", ""),
            cliente_texto=datos.get("cliente_q", ""),
            estado=datos.get("estado", ""),
            fecha_de=datos.get("fecha_de", "realizacion"),
            desde=datos.get("desde", ""),
            hasta=datos.get("hasta", ""),
            vendedor_id=datos.get("vendedor", ""),
        )


def buscar_suministros(actor, filtros, pagina=1):
    """COM-CNS-SUM, reglas 1 a 3: la ``Page`` de suministros del alcance de ``actor`` (el Vendedor, los suyos; el Gerente, todos) con sus
    filtros, por fecha de realización y número descendentes (50 por página). Cada uno trae ``detalles_vigentes`` calculado en la base, con
    el cliente y el Vendedor ya cargados: sin consultas por fila. No audita (SEG-14)."""
    _exigir_actor(actor)
    lista = (
        Suministro.objects.en_alcance_de(actor)
        .select_related("cliente", "vendedor")
        .annotate(detalles_vigentes=Count("detalles", filter=Q(detalles__estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE)))
    )
    if _entero(filtros.cliente_id):
        lista = lista.filter(cliente_id=_entero(filtros.cliente_id))
    if len(_texto(filtros.cliente_texto)) >= 2:
        coinciden = api_clientes.buscar_clientes(actor, filtros.cliente_texto).object_list
        lista = lista.filter(cliente_id__in=[c.pk for c in coinciden])
    if filtros.estado in Suministro.Estado.values:
        lista = lista.filter(estado_suministro=filtros.estado)
    if rol_de(actor) == GERENTE and _entero(filtros.vendedor_id):
        lista = lista.filter(vendedor_id=_entero(filtros.vendedor_id))
    campo = "fecha_fin" if filtros.fecha_de == "fin" else "fecha_realizacion"
    if desde := _fecha(filtros.desde):
        lista = lista.filter(**{f"{campo}__gte": desde})
    if hasta := _fecha(filtros.hasta):
        lista = lista.filter(**{f"{campo}__lte": hasta})
    return Paginator(lista.order_by("-fecha_realizacion", "-numero"), POR_PAGINA).get_page(pagina)


@dataclass
class FilaDeDetalle:
    """Regla 5: una línea por cadena «reemplaza a» (la última versión), con lo que rigió antes en ``historial`` (de la más vieja a la más
    nueva) y «Con cambios desde el dd/mm»."""

    detalle: object
    historial: list
    precio_hoy: Decimal
    con_cambios_desde: date | None
    direccion: str


@dataclass
class FilaDeCalendario:
    """Regla 6: un período (fecha, detalle) con su situación: ``entrega_planificada`` (COM-05a2), ``pasado``, ``reservado``, ``sin_cobertura`` o ``fuera_de_la_ventana``."""

    fecha: date
    detalle: object
    variedad: object
    cantidad: int
    precio: Decimal
    situacion: str
    texto: str
    faltan: int
    condiciones_anteriores: bool


@dataclass
class FichaDeSuministro:
    """La ficha de COM-CNS-SUM (en lo que existe hoy): el contrato, su cláusula, los detalles, el calendario por tramos, el aviso de límite y las
    acciones. La rescisión, el historial, las entregas, las solicitudes y el cobro los suman COM-03b, COM-05 a COM-08 (D-25)."""

    suministro: object
    clausula: object
    detalles: list
    calendario: list
    desde: date
    hasta: date
    hay_mas_calendario: bool
    ventana: date
    aviso_de_limite: str | None
    acciones: frozenset
    aviso_de_rescision: str | None = None  # COM-03b: la rescisión acordada o el contrato rescindido
    entregas: list = field(default_factory=list)  # COM-05a2 (regla 7): las entregas del contrato (`entregas.entregas_del_contrato`)
    hay_historial: bool = False  # COM-03b: alguna cadena «reemplaza a» con más de una versión («Ver historial de cambios»)
    discrepancias: list = field(default_factory=list)  # COM-06a (regla 8 de COM-CNS-SUM): las discrepancias de entrega del contrato


def suministro_del_alcance(actor, suministro_id):
    """El suministro ``suministro_id`` con lo que muestra la ficha. 404 si no existe; ``PermissionDenied`` (403 con mensaje, SEG-13) si no es del
    alcance de ``actor``."""
    _exigir_actor(actor)
    suministro = get_object_or_404(
        Suministro.objects.select_related("cliente", "vendedor", "clausula_suministrado"), pk=suministro_id
    )
    if not Suministro.objects.en_alcance_de(actor).filter(pk=suministro.pk).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    return suministro


def _detalles_de(suministro):
    """Todos los detalles del suministro, con la variedad y la cláusula cargadas y el suministro ya asignado (el calendario lo lee)."""
    detalles = list(
        suministro.detalles.select_related("variedad__cultivo", "clausula_suministrante").order_by("pk")
    )
    for d in detalles:
        d.suministro = suministro
    return detalles


def _filas_de_calendario(fechas, hoy, ventana):
    """Arma las ``FilaDeCalendario`` de ``fechas`` (``[(fecha, detalle, reemplazado)]``): la situación de cada período (regla 6) con **una**
    consulta para todos los de la ventana. «Reservado» si no tiene cantidad sin cubrir; «Sin cobertura completa · faltan N» si la tiene."""
    en_la_ventana = [Periodo(d, f) for f, d, _ in fechas if hoy <= f <= ventana]
    sin_cubrir = stock_maduro.sin_cubrir_de_periodos(en_la_ventana)
    # COM-03b: un período con la alerta «sin cobertura completa» ACTIVA también muestra lo que falta (el N de la alerta) aunque el cálculo dé 0, como el de un
    # detalle finalizado hasta COM-04a (D-64, punto 8). Una consulta para toda la página.
    con_alerta = (
        {
            (detalle_id, fecha): faltan
            for detalle_id, fecha, faltan in AlertaComercial.objects.filter(
                alerta__tipo_alerta=TIPO_DE_ALERTA_DE_PERIODO,
                alerta__estado_alerta=Alerta.Estado.ACTIVA,
                detalle_suministro_id__in={p.detalle.pk for p in en_la_ventana},
                fecha_periodo__range=(hoy, ventana),
            ).values_list("detalle_suministro_id", "fecha_periodo", "cantidad_sin_cubrir")
        }
        if en_la_ventana
        else {}
    )
    # COM-05a2 (regla 6): un período con línea en una entrega «a realizar» dice «Entrega planificada», sea cual sea su fecha. Dos consultas para toda la página.
    con_entrega = entregas.periodos_con_entrega([(detalle.pk, fecha) for fecha, detalle, _ in fechas])
    entregados = entregas.periodos_entregados([(detalle.pk, fecha) for fecha, detalle, _ in fechas])  # COM-06a (regla 6): «Entregado», con la entrega concretada
    filas = []
    for fecha, detalle, reemplazado in fechas:
        faltan = 0
        if (detalle.pk, fecha) in con_entrega:
            situacion, texto = "entrega_planificada", TEXTOS_DE_SITUACION["entrega_planificada"]
        elif (detalle.pk, fecha) in entregados:
            situacion, texto = "entregado", TEXTOS_DE_SITUACION["entregado"]
        elif fecha < hoy:
            situacion, texto = "pasado", TEXTOS_DE_SITUACION["pasado"]
        elif fecha <= ventana:
            faltan = sin_cubrir[Periodo(detalle, fecha)] or con_alerta.get((detalle.pk, fecha), 0)
            if faltan:
                situacion, texto = "sin_cobertura", f"Sin cobertura completa · faltan {faltan}"
            else:
                situacion, texto = "reservado", TEXTOS_DE_SITUACION["reservado"]
        else:
            situacion, texto = "fuera_de_la_ventana", TEXTOS_DE_SITUACION["fuera_de_la_ventana"]
        filas.append(
            FilaDeCalendario(
                fecha=fecha,
                detalle=detalle,
                variedad=detalle.variedad,
                cantidad=detalle.cantidad_por_periodo,
                precio=calendario.precio_en(detalle, fecha),
                situacion=situacion,
                texto=texto,
                faltan=faltan,
                condiciones_anteriores=reemplazado,
            )
        )
    return filas


def _fechas_de(detalles, desde=None, hasta=None):
    """``[(fecha, detalle, reemplazado)]`` del calendario de todos los detalles (o solo del tramo), por fecha y después por variedad."""
    reemplazados = {d.reemplaza_a_id for d in detalles if d.reemplaza_a_id}
    fechas = [(f, d, d.pk in reemplazados) for d in detalles for f in calendario.calendario(d, desde=desde, hasta=hasta)]
    fechas.sort(key=lambda x: (x[0], str(x[1].variedad), x[1].pk))
    return fechas


def _aviso_de_limite(suministro):
    """Regla 9 (textos del prototipo): con un incumplimiento tolerado restante, o con todos usados, un aviso; con margen o sin estar vigente,
    nada. Con 0 tolerados el primero ya resuelve el contrato."""
    if not suministro.al_limite:
        return None
    if suministro.incumplimientos_tolerados == 0:
        return "El contrato no tolera incumplimientos: el primero lo resuelve y se aplica la multa."
    if suministro.cantidad_incumplimientos >= suministro.incumplimientos_tolerados:
        return (
            f"El contrato ya usó sus {suministro.incumplimientos_tolerados} incumplimientos tolerados: "
            "el próximo lo resuelve y se aplica la multa."
        )
    return "Al contrato le queda un incumplimiento tolerado."


def _aviso_de_rescision(suministro):
    """Los textos de la ficha para la rescisión (COM-CNS-SUM, «Rescisión en la ficha y en la lista»): acordada (el contrato sigue «vigente» hasta la última entrega) o
    ya rescindido. Sin rescisión, ``None``."""
    if suministro.motivo_rescision is None:
        return None
    motivo = suministro.get_motivo_rescision_display().lower()
    if suministro.descripcion_rescision:
        motivo = f"{motivo}: {suministro.descripcion_rescision}"
    acuerdo, ultima = _fecha_texto(suministro.fecha_acuerdo_rescision), _fecha_texto(suministro.fecha_ultima_entrega_rescision)
    if suministro.estado_suministro == Suministro.Estado.RESCINDIDO:
        return f"Rescindido por mutuo acuerdo (acordado el {acuerdo}, {motivo}). La última entrega fue el {ultima}."
    if suministro.estado_suministro == Suministro.Estado.VIGENTE:
        return f"Rescisión acordada el {acuerdo} ({motivo}). Se entrega hasta el {ultima}; los períodos posteriores no se entregan."
    return None


def _versiones_anteriores(detalle, por_id):
    """Las versiones anteriores de ``detalle`` en su cadena «reemplaza a» (MD-131), de la más vieja a la más nueva."""
    historial, anterior = [], por_id.get(detalle.reemplaza_a_id)
    while anterior is not None:
        historial.insert(0, anterior)
        anterior = por_id.get(anterior.reemplaza_a_id)
    return historial


@dataclass
class TramoDeHistorial:
    """Un tramo de una cadena «reemplaza a»: qué detalle rigió ``desde`` ``hasta`` (``None``: rige hasta el fin del contrato) y si sigue «vigente»."""

    detalle: object
    desde: date
    hasta: date | None
    vigente: bool


@dataclass
class CadenaDeHistorial:
    """Las versiones de un detalle (``MODALS.sumhist``): la variedad, a dónde se entrega y sus tramos, del más viejo al más nuevo."""

    variedad: object
    direccion: str
    tramos: list


def historial_de_cambios(actor, suministro_id):
    """«Ver historial de cambios» (regla 5): ``[CadenaDeHistorial]`` de las cadenas «reemplaza a» con más de una versión, por variedad. 404 si no existe;
    ``PermissionDenied`` si no es del alcance. No audita (los cambios del contrato están en la auditoría de cada modificación)."""
    suministro = suministro_del_alcance(actor, suministro_id)
    detalles = _detalles_de(suministro)
    por_id = {d.pk: d for d in detalles}
    reemplazados = {d.reemplaza_a_id for d in detalles if d.reemplaza_a_id}
    cadenas = []
    for ultimo in sorted((d for d in detalles if d.pk not in reemplazados and d.reemplaza_a_id), key=lambda d: (str(d.variedad), d.pk)):
        versiones = [*_versiones_anteriores(ultimo, por_id), ultimo]
        hija = api_clientes.direccion_hija(ultimo.direccion_id)
        cadenas.append(
            CadenaDeHistorial(
                variedad=ultimo.variedad,
                direccion=f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else "",
                tramos=[
                    TramoDeHistorial(v, v.fecha_primer_entrega, v.fecha_fin_detalle, v.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE)
                    for v in versiones
                ],
            )
        )
    return cadenas


def ficha_de_suministro(actor, suministro_id):
    """COM-CNS-SUM, reglas 4 a 6, 9 y 10 (en lo que existe hoy): el contrato y su cláusula del suministrado, los detalles (una línea por cadena
    «reemplaza a», con el precio vigente hoy), el calendario por defecto (de los últimos 30 días a 28 días después del fin de la ventana) con la
    situación de cada período, el aviso de límite y las acciones. 404 si no existe; ``PermissionDenied`` si no es del alcance. Sin consultas
    por período. No audita."""
    suministro = suministro_del_alcance(actor, suministro_id)
    hoy = stock.hoy()
    ventana = calendario.ventana(hoy)
    detalles = _detalles_de(suministro)
    por_id = {d.pk: d for d in detalles}
    reemplazados = {d.reemplaza_a_id for d in detalles if d.reemplaza_a_id}
    filas = []
    for d in sorted((d for d in detalles if d.pk not in reemplazados), key=lambda d: (str(d.variedad), d.pk)):
        historial = _versiones_anteriores(d, por_id)
        hija = api_clientes.direccion_hija(d.direccion_id)
        filas.append(
            FilaDeDetalle(
                detalle=d,
                historial=historial,
                precio_hoy=calendario.precio_en(d, hoy),
                con_cambios_desde=d.fecha_primer_entrega if historial else None,
                direccion=f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else "",
            )
        )
    desde, hasta = hoy - timedelta(days=DIAS_ATRAS_DEL_CALENDARIO), ventana + timedelta(days=DIAS_ADELANTE_DEL_CALENDARIO)
    hay_mas = any(
        calendario.calendario(d, hasta=desde - timedelta(days=1)) or calendario.calendario(d, desde=hasta + timedelta(days=1)) for d in detalles
    )
    acciones = {"ver_cliente"}
    if suministro.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO and suministro.cliente.email_cliente:
        acciones.add("reenviar_comprobante")
    # Regla 10 (COM-03b): solo lo que la persona puede hacer (ningún botón lleva a un 403). «Modificar»: su Vendedor o el Gerente (el alcance ya lo garantiza);
    # «Rescindir» y «Dejar sin efecto la rescisión», solo el Gerente; esta última mientras la última entrega conservada no haya pasado (`rescision_cerrada`).
    es_gerente = rol_de(actor) == GERENTE
    if suministro.estado_suministro == Suministro.Estado.VIGENTE:
        if suministro.motivo_rescision is None:
            acciones.add("modificar")
            if es_gerente:
                acciones.add("rescindir")
        elif es_gerente and suministro.fecha_ultima_entrega_rescision >= hoy:
            acciones.add("dejar_sin_efecto")
    hay_historial = any(d.reemplaza_a_id for d in detalles)
    if hay_historial:
        acciones.add("ver_historial")
    return FichaDeSuministro(
        suministro=suministro,
        clausula=suministro.clausula_suministrado,
        detalles=filas,
        calendario=_filas_de_calendario(_fechas_de(detalles, desde, hasta), hoy, ventana),
        desde=desde,
        hasta=hasta,
        hay_mas_calendario=hay_mas,
        ventana=ventana,
        aviso_de_limite=_aviso_de_limite(suministro),
        acciones=frozenset(acciones),
        aviso_de_rescision=_aviso_de_rescision(suministro),
        hay_historial=hay_historial,
        entregas=entregas.entregas_del_contrato(suministro.pk, hoy),
        discrepancias=list(
            DiscrepanciaEntrega.objects.filter(entrega__contrato_entrega_id=suministro.pk).select_related("entrega").prefetch_related("lineas").order_by("numero")
        ),
    )


def calendario_completo(actor, suministro_id, pagina=1):
    """«Ver todo el calendario» (regla 6): la ``Page`` (de a 100) de todos los períodos de todos los detalles, por fecha, con su situación. La
    situación se calcula solo para los de la página. 404 si no existe; ``PermissionDenied`` si no es del alcance."""
    suministro = suministro_del_alcance(actor, suministro_id)
    hoy = stock.hoy()
    pagina_de_fechas = Paginator(_fechas_de(_detalles_de(suministro)), POR_PAGINA_DEL_CALENDARIO).get_page(pagina)
    pagina_de_fechas.object_list = _filas_de_calendario(list(pagina_de_fechas.object_list), hoy, calendario.ventana(hoy))
    return pagina_de_fechas


# ---- modificar (COM-MOD-SUM, COM-03b) ----
#
# Una modificación no se guarda mientras se arma: vive en el formulario, igual que el pacto. `datos_de_modificacion` (la pantalla),
# `resumen_de_modificacion` (paso 8) y `modificar_suministro` (paso 10) usan el MISMO análisis (`_analizar_modificacion`), que no escribe ni
# bloquea. `modificar_suministro` lo corre dos veces: antes de bloquear (para saber qué bloquear y rechazar rápido) y después de bloquear todo,
# con los datos ya serializados (10a y 10b se verifican acá, sobre lo que quedó confirmado por la operación anterior); la segunda vez no mira
# el stock: el resultado de `asignar` es la verificación del paso 10, como en el pacto (extensión 14a).
#
# Bloqueos de `modificar_suministro` (docs/patrones/stock_maduro.md, sección 3; ``FOR NO KEY UPDATE``): cuentas → (solo con detalles nuevos)
# invernaderos del Vendedor, cliente, variedades, lotes y partidas → el `Suministro` y sus detalles. Sin detalles nuevos no toma invernaderos ni
# lotes (docs/patrones/bloqueos.md, sección `comercial`, «Suministros»): no puede cruzarse con una pre-reserva.

ACCIONES_DE_DETALLE = ("sin_cambios", "modificar", "terminar")
CAMPOS_DE_CAMBIO = (
    "cantidad", "periodo", "precio", "mecanismo", "porcentaje", "meses", "plazo_entrega", "indemnizacion_retraso", "cantidad_minima",
    "indemnizacion_faltante",
)
MENSAJE_CONTRATO_CAMBIO = (
    "El contrato cambió mientras lo modificabas (por ejemplo, se resolvió o lo modificó otra persona). Volvé a abrirlo."
)
MENSAJE_VENTANA_CAMBIO = "Desde que abriste la pantalla, un período entró en la ventana. Revisá las fechas nuevas."
MENSAJE_CON_RESCISION = "Tiene una rescisión acordada: dejala sin efecto para modificarlo."
MENSAJE_SIN_PERIODOS = "Todos sus períodos ya están dentro de la ventana de pre-reserva."
OPCIONES_DE_RIGE = 60  # cuántos períodos posteriores a la ventana ofrece el desplegable de «Rige desde»

CambioResumido = namedtuple("CambioResumido", "texto rige_desde")


@dataclass
class CambioDeDetalle:
    """Lo que se hace con un detalle VIGENTE del contrato, todo texto (como llegó). ``accion``: ``sin_cambios``, ``modificar`` o ``terminar``.
    **Un campo vacío es «sin cambio»** (el formulario viene cargado con los valores actuales: lo igual al actual tampoco es un cambio).
    ``rige_desde`` es la fecha elegida (5a; vacía, la propuesta) y ``rige_visto`` la propuesta que vio la persona al abrir la pantalla
    (oculta; vacía, no se compara: 10a)."""

    detalle_id: int = 0
    accion: str = "sin_cambios"
    rige_desde: str = ""
    rige_visto: str = ""
    cantidad: str = ""
    periodo: str = ""
    precio: str = ""
    mecanismo: str = ""
    porcentaje: str = ""
    meses: str = ""
    plazo_entrega: str = ""
    indemnizacion_retraso: str = ""
    cantidad_minima: str = ""
    indemnizacion_faltante: str = ""


@dataclass
class CambiosDeSuministro:
    """Lo que carga el formulario de COM-MOD-SUM: los datos del contrato (vacío = sin cambio; ``vendedor_id`` solo lo cambia el Gerente), un
    `CambioDeDetalle` por detalle vigente tocado y los detalles nuevos (los `RenglonDeSuministro` de COM-PCT-SUM). El cliente y la fecha de
    realización no se leen (extensión 5g)."""

    vendedor_id: str = ""
    duracion: str = ""
    tolerados: str = ""
    multa: str = ""
    plazo_pago: str = ""
    indemnizacion_pago: str = ""
    detalles: list = field(default_factory=list)
    nuevos: list = field(default_factory=list)

    @classmethod
    def desde_post(cls, datos):
        """Arma los cambios de un ``QueryDict`` (o un diccionario): ``vendedor``, ``duracion``, ``tolerados``, ``multa``, ``plazo_pago``,
        ``indemnizacion_pago``, ``modificar-<id>-<campo>`` (``accion``, ``rige_desde``, ``rige_visto`` y los de ``CAMPOS_DE_CAMBIO``) y los
        ``detalle-<i>-<campo>`` de los detalles nuevos."""
        por_id = {}
        for clave in datos:
            coincidencia = re.fullmatch(r"modificar-(\d+)-([a-z_]+)", clave)
            if coincidencia and coincidencia.group(2) in ("accion", "rige_desde", "rige_visto", *CAMPOS_DE_CAMBIO):
                cambio = por_id.setdefault(int(coincidencia.group(1)), CambioDeDetalle(detalle_id=int(coincidencia.group(1))))
                setattr(cambio, coincidencia.group(2), datos.get(clave, ""))
        return cls(
            vendedor_id=datos.get("vendedor", ""),
            duracion=datos.get("duracion", ""),
            tolerados=datos.get("tolerados", ""),
            multa=datos.get("multa", ""),
            plazo_pago=datos.get("plazo_pago", ""),
            indemnizacion_pago=datos.get("indemnizacion_pago", ""),
            detalles=[por_id[i] for i in sorted(por_id)],
            nuevos=DatosDeSuministro.desde_post(datos).renglones,
        )


@dataclass
class FilaDeModificacion:
    """Un detalle vigente en la pantalla de modificar: desde cuándo rige un cambio (``rige_desde``, ``None`` si ya no le quedan períodos fuera
    de la ventana), los períodos entre los que elegir (5a), el precio propuesto para el sucesor y sus errores por campo (sin el prefijo)."""

    detalle: object
    rige_desde: date | None
    opciones: list
    precio_propuesto: Decimal
    errores: dict = field(default_factory=dict)


@dataclass
class DatosDeModificacion:
    """Lo que muestra la pantalla de COM-MOD-SUM y lo que usan el resumen y el registro (``plan``: lo que se aplica al confirmar)."""

    suministro: object
    hoy: date
    ventana: date
    huella: str
    filas: list = field(default_factory=list)
    nuevas: list = field(default_factory=list)  # los detalles nuevos ya interpretados (`FilaDeSuministro`)
    errores: dict = field(default_factory=dict)
    codigos: dict = field(default_factory=dict)
    equivale_a_terminar_el_contrato: bool = False
    duracion_sugerida: int | None = None
    fecha_sugerida: date | None = None
    cambios: list = field(default_factory=list)  # [CambioResumido]
    plan: object = None
    vendedor_final: object = None
    habilitados: list = field(default_factory=list)


@dataclass
class ResumenDeModificacion:
    """El resumen del paso 8: cada cambio con la fecha desde la que rige."""

    datos: DatosDeModificacion

    @property
    def cambios(self):
        return self.datos.cambios


def huella_de(suministro):
    """10b: un texto que resume el estado del contrato (estado, duración, tolerados, acumulados, multa, cláusula del suministrado, Vendedor, los id de
    los detalles vigentes y los datos de la rescisión). La misma usan COM-RSC-SUM y COM-ANL-RSC. Los detalles y la cláusula se leen de la base."""
    clausula = ClausulaSuministrado.objects.filter(suministro_id=suministro.pk).values_list("plazo_pago_dias", "indemnizacion_retraso_pago").first()
    vigentes = sorted(
        DetalleSuministro.objects.filter(suministro_id=suministro.pk, estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE).values_list("pk", flat=True)
    )
    partes = [
        suministro.estado_suministro, suministro.duracion_meses, suministro.incumplimientos_tolerados, suministro.cantidad_incumplimientos,
        suministro.multa_resolucion, suministro.vendedor_id, clausula, vigentes, suministro.motivo_rescision, suministro.descripcion_rescision,
        suministro.fecha_acuerdo_rescision, suministro.fecha_registro_rescision, suministro.fecha_ultima_entrega_rescision,
        suministro.fecha_rescision, suministro.fecha_resolucion_suministro,
    ]
    return hashlib.sha256("|".join(repr(p) for p in partes).encode()).hexdigest()


def _ultimo_periodo_de_la_ventana(detalles, ventana):
    """La mayor de las últimas fechas dentro de la ventana de todos los ``detalles`` (cualquier estado), o ``None`` si ninguno tiene."""
    ultimas = [fechas[-1] for d in detalles if (fechas := calendario.calendario(d, hasta=ventana))]
    return max(ultimas) if ultimas else None


def _duracion_que_incluye(realizacion, fecha):
    """Los meses mínimos (de 1 a 120) para que la fecha de fin del contrato no sea anterior a ``fecha`` (extensión 5c.1a)."""
    for meses in range(1, 121):
        if calendario.sumar_meses(realizacion, meses) >= fecha:
            return meses
    return 120


def _analizar_modificacion(actor, suministro_id, cambios, huella, *, estricto, verificar_stock):
    """Interpreta ``cambios`` sin escribir ni bloquear (pasos 2 a 8 y extensiones 1a, 5a a 5g, 6a, 7a, 10a y 10b): qué rige desde cuándo, los
    errores por campo y lo que se aplicaría (``plan``). Con ``huella`` verifica además 10b; con ``estricto`` exige lo que falte y rechaza la
    modificación vacía (7a); con ``verificar_stock`` simula la ventana de los detalles nuevos (9e). ``PermissionDenied`` / ``Http404`` como la
    ficha (``suministro_del_alcance``)."""
    s = suministro_del_alcance(actor, suministro_id)
    hoy = stock.hoy()
    ventana = calendario.ventana(hoy)
    es_gerente = rol_de(actor) == GERENTE
    err = _Errores()
    datos = DatosDeModificacion(suministro=s, hoy=hoy, ventana=ventana, huella=huella_de(s))
    plan = SimpleNamespace(contrato={}, modificar=[], terminar=[], autofinalizar=[], nuevas=[], vendedor_nuevo=None, textos=[])
    datos.plan = plan

    def cerrar():
        datos.errores, datos.codigos = err.mensajes, err.codigos
        return datos

    # Regla «Quién modifica»: el Vendedor responsable lo cambia solo el Gerente.
    pide_vendedor = _texto(cambios.vendedor_id) and _texto(cambios.vendedor_id) != str(s.vendedor_id)
    if pide_vendedor and not es_gerente:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)

    # 10b: el contrato sigue «vigente», sin rescisión acordada y sin cambios desde la lectura.
    if s.estado_suministro != Suministro.Estado.VIGENTE:
        err.agregar(NO_CAMPO, "contrato_cambio", MENSAJE_CONTRATO_CAMBIO)
        return cerrar()
    if s.tiene_rescision_acordada:
        err.agregar(NO_CAMPO, "rescision_acordada", MENSAJE_CON_RESCISION)
        return cerrar()
    if huella is not None and huella != datos.huella:
        err.agregar(NO_CAMPO, "contrato_cambio", MENSAJE_CONTRATO_CAMBIO)
        return cerrar()

    todos = _detalles_de(s)
    vigentes = [d for d in todos if d.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE]
    por_id = {d.pk: d for d in vigentes}
    pedidos = {}
    for cambio in cambios.detalles:
        if cambio.accion == "sin_cambios":
            continue
        if cambio.detalle_id not in por_id:  # ya no es un detalle vigente del contrato: lo modificó otra operación
            err.agregar(NO_CAMPO, "contrato_cambio", MENSAJE_CONTRATO_CAMBIO)
            return cerrar()
        pedidos[cambio.detalle_id] = cambio

    # Paso 4: desde cuándo rige un cambio de cada detalle (el primer período posterior a la ventana).
    primero_fuera = ventana + timedelta(days=1)
    for d in vigentes:
        opciones = calendario.calendario(d, desde=primero_fuera)
        propuesta = opciones[0] if opciones else None
        datos.filas.append(
            FilaDeModificacion(
                detalle=d,
                rige_desde=propuesta,
                opciones=opciones[:OPCIONES_DE_RIGE],
                precio_propuesto=calendario.precio_en(d, propuesta) if propuesta else d.precio_unitario_suministro,
            )
        )
    filas = {f.detalle.pk: f for f in datos.filas}

    # 10a: la propuesta que vio la persona sigue siendo la de hoy.
    for detalle_id, cambio in pedidos.items():
        if _texto(cambio.rige_visto) and _fecha(cambio.rige_visto) != filas[detalle_id].rige_desde:
            err.agregar(NO_CAMPO, "ventana_cambio", MENSAJE_VENTANA_CAMBIO)
            return cerrar()

    # Los datos del contrato (postcondiciones d, e, f y g).
    contrato = plan.contrato
    duracion, nuevo_fin = s.duracion_meses, s.fecha_fin
    if _texto(cambios.duracion):
        meses = _entero_entre(cambios.duracion, 1, 120)
        if meses is None:
            err.agregar("duracion", "duracion_invalida", "Ingresá un número entero de meses, de 1 a 120.")
        elif meses != s.duracion_meses:
            duracion, nuevo_fin = meses, calendario.sumar_meses(s.fecha_realizacion, meses)
            minimo = _ultimo_periodo_de_la_ventana(todos, ventana)
            if nuevo_fin < s.fecha_fin and minimo is not None and nuevo_fin < minimo:
                err.agregar(
                    "duracion", "fin_anterior_a_la_ventana", f"La fecha de fin más cercana posible es el {_fecha_texto(minimo)}."
                )
            else:
                contrato["duracion_meses"] = (s.duracion_meses, meses)
                contrato["fecha_fin"] = (s.fecha_fin, nuevo_fin)
    if _texto(cambios.tolerados):
        tolerados = _entero_entre(cambios.tolerados, 0, 99)
        if tolerados is None:
            err.agregar("tolerados", "tolerados_invalidos", "Ingresá un número entero, de 0 a 99.")
        elif tolerados < s.cantidad_incumplimientos:
            acumulados = s.cantidad_incumplimientos
            texto = f"{acumulados} incumplimiento{'s' if acumulados != 1 else ''} ya acumulado{'s' if acumulados != 1 else ''}"
            err.agregar("tolerados", "tolerados_menores_que_acumulados", f"No puede ser menor que los {texto}.")
        elif tolerados != s.incumplimientos_tolerados:
            contrato["incumplimientos_tolerados"] = (s.incumplimientos_tolerados, tolerados)
    if _texto(cambios.multa):
        multa = _importe(cambios.multa, Decimal(0), MULTA_MAXIMA)
        if multa is None:
            err.agregar("multa", "multa_invalida", "Ingresá un importe de $ 0 a $ 99.999.999,99.")
        elif multa != s.multa_resolucion:
            contrato["multa_resolucion"] = (s.multa_resolucion, multa)
    clausula = s.clausula_suministrado
    if _texto(cambios.plazo_pago):
        plazo = _entero_entre(cambios.plazo_pago, 0, 365)
        if plazo is None:
            err.agregar("plazo_pago", "plazo_pago_invalido", "Ingresá un número entero de días, de 0 a 365.")
        elif plazo != clausula.plazo_pago_dias:
            contrato["plazo_pago_dias"] = (clausula.plazo_pago_dias, plazo)
    if _texto(cambios.indemnizacion_pago):
        indemnizacion = _importe(cambios.indemnizacion_pago, Decimal(0), IMPORTE_MAXIMO)
        if indemnizacion is None:
            err.agregar("indemnizacion_pago", "indemnizacion_pago_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.")
        elif indemnizacion != clausula.indemnizacion_retraso_pago:
            contrato["indemnizacion_retraso_pago"] = (clausula.indemnizacion_retraso_pago, indemnizacion)
    vendedor_final = s.vendedor
    if pide_vendedor:
        elegido = _entero(cambios.vendedor_id)
        encontrado = next((v for v, _ in _vendedores_con_invernaderos() if v.pk == elegido), None)
        if encontrado is None:
            err.agregar("vendedor", "vendedor_invalido", "Elegí un Vendedor activo con invernaderos activos.")
        else:
            plan.vendedor_nuevo = vendedor_final = encontrado
            contrato["vendedor"] = (s.vendedor, encontrado)

    # Los detalles vigentes: modificar y terminar (postcondiciones a y c, extensiones 5a, 5c y 6a).
    quedan = []  # los vigentes que siguen como están
    for d in vigentes:
        cambio = pedidos.get(d.pk)
        if cambio is None:
            quedan.append(d)
            continue
        fila = filas[d.pk]
        nombre = lambda campo, d=d: f"modificar-{d.pk}-{campo}"  # noqa: E731
        if cambio.accion not in ACCIONES_DE_DETALLE:
            err.agregar(nombre("accion"), "accion_invalida", "Elegí qué hacer con el detalle.")
            continue
        if fila.rige_desde is None or fila.rige_desde > nuevo_fin:
            err.agregar(nombre("accion"), "detalle_sin_periodos_posteriores", MENSAJE_SIN_PERIODOS)
            continue
        if cambio.accion == "terminar":
            ultimas = calendario.calendario(d, hasta=ventana)
            fin = ultimas[-1] if ultimas else ventana
            plan.terminar.append((d, fin))
            plan.textos.append(
                (f"Se termina {d.variedad}: se entrega por última vez el {_fecha_texto(fin)}. Sin multa: es de mutuo acuerdo.", fila.rige_desde)
            )
            continue
        rige = fila.rige_desde
        if _texto(cambio.rige_desde):
            elegido = _fecha(cambio.rige_desde)
            if elegido is None or elegido <= ventana or elegido > nuevo_fin or calendario.calendario(d, desde=elegido, hasta=elegido) != [elegido]:
                err.agregar(nombre("rige_desde"), "rige_desde_invalido", "Elegí un período del calendario posterior a la ventana de pre-reserva.")
                continue
            rige = elegido
        antes = sum(len(v) for v in err.mensajes.values())

        def leer(campo, interpretar, actual, codigo, mensaje, cambio=cambio, nombre=nombre):
            """El valor nuevo de ``campo`` (``actual`` si viene vacío); un error de ``campo`` si no vale."""
            if not _texto(getattr(cambio, campo)):
                return actual
            valor = interpretar(getattr(cambio, campo))
            if valor is None:
                err.agregar(nombre(campo), codigo, mensaje)
            return valor

        cl = d.clausula_suministrante
        cantidad = leer("cantidad", lambda t: _entero_entre(t, 1, 500000), d.cantidad_por_periodo, "cantidad_invalida", "Ingresá un número entero de plantas, de 1 a 500.000.")
        periodo = leer("periodo", lambda t: _entero_entre(t, 1, 365), d.periodo_entrega_dias, "periodo_invalido", "Ingresá un número entero de días, de 1 a 365.")
        mecanismo = _texto(cambio.mecanismo) or d.mecanismo_precio
        if mecanismo not in MECANISMOS:
            err.agregar(nombre("mecanismo"), "mecanismo_invalido", "Elegí el mecanismo de precio: fijo o ajuste periódico.")
        precio = leer("precio", lambda t: _importe(t, Decimal("0.01"), IMPORTE_MAXIMO), fila.precio_propuesto, "precio_invalido", "Ingresá un precio de $ 0,01 a $ 9.999.999,99, con hasta dos decimales.")
        porcentaje = meses_ajuste = None
        if mecanismo == DetalleSuministro.Mecanismo.AJUSTE_PERIODICO:
            porcentaje = leer("porcentaje", lambda t: _importe(t, Decimal("0.01"), Decimal(100)), d.porcentaje_ajuste, "porcentaje_invalido", "Ingresá un porcentaje de 0,01 a 100.")
            meses_ajuste = leer("meses", lambda t: _entero_entre(t, 1, 60), d.meses_ajuste, "meses_invalidos", "Ingresá un número entero de meses, de 1 a 60.")
            if porcentaje is None and not _texto(cambio.porcentaje):
                err.agregar(nombre("porcentaje"), "porcentaje_invalido", "Ingresá un porcentaje de 0,01 a 100.")
            if meses_ajuste is None and not _texto(cambio.meses):
                err.agregar(nombre("meses"), "meses_invalidos", "Ingresá un número entero de meses, de 1 a 60.")
        plazo_entrega = leer("plazo_entrega", lambda t: _entero_entre(t, 0, 365), cl.plazo_entrega_dias, "plazo_entrega_invalido", "Ingresá un número entero de días, de 0 a 365.")
        retraso = leer("indemnizacion_retraso", lambda t: _importe(t, Decimal(0), IMPORTE_MAXIMO), cl.indemnizacion_retraso_entrega, "indemnizacion_retraso_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.")
        minima = leer("cantidad_minima", lambda t: _entero_entre(t, 1, 500000), cl.cantidad_minima, "cantidad_minima_invalida", "Ingresá un número entero de plantas, de 1 a 500.000.")
        faltante = leer("indemnizacion_faltante", lambda t: _importe(t, Decimal(0), IMPORTE_MAXIMO), cl.indemnizacion_faltante, "indemnizacion_faltante_invalida", "Ingresá un importe de $ 0 a $ 9.999.999,99.")
        if minima is not None and cantidad is not None and minima > cantidad and nombre("cantidad_minima") not in err.mensajes:
            err.agregar(nombre("cantidad_minima"), "cantidad_minima_invalida", f"Ingresá un número entero de plantas, de 1 a {cantidad}.")
        if sum(len(v) for v in err.mensajes.values()) > antes:
            continue
        diferencias = []
        for texto, actual, nuevo in (
            ("cantidad por período", d.cantidad_por_periodo, cantidad), ("período de entrega (días)", d.periodo_entrega_dias, periodo),
            ("precio inicial", fila.precio_propuesto, precio),
            ("mecanismo de precio", d.mecanismo_precio, mecanismo), ("porcentaje de ajuste", d.porcentaje_ajuste, porcentaje),
            ("meses de ajuste", d.meses_ajuste, meses_ajuste), ("tolerancia de entrega (días)", cl.plazo_entrega_dias, plazo_entrega),
            ("indemnización por retraso", cl.indemnizacion_retraso_entrega, retraso), ("cantidad mínima", cl.cantidad_minima, minima),
            ("indemnización por faltante", cl.indemnizacion_faltante, faltante),
        ):
            if actual != nuevo:
                diferencias.append(f"{texto}: de {actual} a {nuevo}")
        if not diferencias:
            err.agregar(nombre("accion"), "detalle_sin_cambios", 'Cambiá al menos un dato o elegí "Sin cambios".')
            continue
        ultimas = calendario.calendario(d, hasta=rige - timedelta(days=1))
        plan.modificar.append(
            SimpleNamespace(
                detalle=d, rige=rige, fin_anterior=ultimas[-1] if ultimas else rige - timedelta(days=1),
                valores=dict(
                    cantidad=cantidad, periodo=periodo, precio=precio, mecanismo=mecanismo, porcentaje=porcentaje, meses=meses_ajuste,
                    plazo_entrega=plazo_entrega, retraso=retraso, minima=minima, faltante=faltante,
                ),
            )
        )
        plan.textos.append((f"{d.variedad}: {'; '.join(diferencias)}. Rige desde el {_fecha_texto(rige)}.", rige))

    # Extensión 5d.2: los vigentes que con la nueva fecha de fin se quedan sin períodos posteriores a la ventana pasan a «finalizado».
    if nuevo_fin < s.fecha_fin:
        tocados = {d.pk for d, _ in plan.terminar} | {x.detalle.pk for x in plan.modificar}
        for d in list(quedan):
            if d.pk in tocados:
                continue
            if not calendario.calendario(d, desde=primero_fuera, hasta=nuevo_fin):
                hasta = calendario.calendario(d, hasta=nuevo_fin)
                plan.autofinalizar.append((d, hasta[-1] if hasta else nuevo_fin))
                quedan.remove(d)
                plan.textos.append((f"{d.variedad} pasa a finalizado: no le quedan períodos después de la nueva fecha de fin.", hoy))

    # Los detalles nuevos (postcondición b y extensión 5b).
    renglones = [r for r in cambios.nuevos if estricto is False or not r.vacio]
    por_variedad = {
        v.pk: v for v in Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO).select_related("cultivo")
    }
    por_direccion = {d.pk: d for d in api_clientes.direcciones_activas(s.cliente)}
    filas_nuevas = [_fila(r, estricto, err, hoy, duracion, nuevo_fin, por_variedad, por_direccion, True) for r in renglones]
    cargadas = [f for f in filas_nuevas if not f.renglon.vacio]
    liberados = {d.pk for d, _ in plan.terminar}
    vigentes_pares = {(d.variedad_id, d.direccion_id): d for d in vigentes if d.pk not in liberados}
    vistos = {}
    for posicion, fila in enumerate(cargadas, start=1):
        if fila.variedad is None or fila.direccion is None:
            continue
        par = (fila.variedad.pk, fila.direccion.pk)
        campo = f"detalle-{fila.renglon.indice}-variedad"
        if par in vigentes_pares:
            err.agregar(campo, "par_vigente", f"El contrato ya tiene {fila.variedad} para esa dirección: modificá ese detalle.")
        elif par in vistos:
            err.agregar(campo, "par_repetido", f"El contrato ya tiene {fila.variedad} para esa dirección: es el detalle {vistos[par]}.")
        else:
            vistos[par] = posicion
    _repartir_errores(filas_nuevas, err)
    _advertir_superposiciones(cargadas, s.cliente, estricto, err, excluir=s.pk)
    habilitados = list(Invernadero.objects.filter(vendedor_id=vendedor_final.pk, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("pk"))
    if verificar_stock and cargadas:
        _verificar_stock(cargadas, vendedor_final, habilitados, ventana, err)
    _repartir_errores(filas_nuevas, err)
    datos.nuevas = filas_nuevas
    plan.nuevas = cargadas
    datos.vendedor_final = vendedor_final
    datos.habilitados = habilitados
    for fila in cargadas:
        if fila.variedad is not None and fila.primera is not None:
            plan.textos.append((f"Se agrega {fila.variedad}: {fila.cantidad} plantas cada {fila.periodo} días desde el {_fecha_texto(fila.primera)}.", fila.primera))

    # Extensión 5c.1a: terminar el único detalle equivale a terminar el contrato.
    datos.equivale_a_terminar_el_contrato = bool(plan.terminar) and not (quedan or plan.modificar or cargadas)
    if datos.equivale_a_terminar_el_contrato:
        ultimo = _ultimo_periodo_de_la_ventana(todos, ventana)
        if ultimo is not None:
            datos.duracion_sugerida = _duracion_que_incluye(s.fecha_realizacion, ultimo)
            datos.fecha_sugerida = calendario.sumar_meses(s.fecha_realizacion, datos.duracion_sugerida)

    # El resumen (paso 8): cada cambio con la fecha desde la que rige.
    nombres = {
        "duracion_meses": "Duración (meses)", "fecha_fin": "Fecha de fin", "incumplimientos_tolerados": "Incumplimientos tolerados",
        "multa_resolucion": "Multa por resolución", "plazo_pago_dias": "Plazo de pago (días)",
        "indemnizacion_retraso_pago": "Indemnización por atraso en el pago (rige para las entregas que se concreten desde hoy)",
        "vendedor": "Vendedor responsable",
    }
    datos.cambios = [CambioResumido(f"{nombres[c]}: de {a} a {n}", hoy) for c, (a, n) in contrato.items() if c != "fecha_fin"]
    datos.cambios += [CambioResumido(texto, rige) for texto, rige in plan.textos]
    if estricto and not err.mensajes and not (contrato or plan.terminar or plan.modificar or plan.autofinalizar or cargadas):
        err.agregar(NO_CAMPO, "sin_cambios", "No indicaste ningún cambio.")
    return cerrar()


def datos_de_modificacion(actor, suministro_id, cambios):
    """Lo que muestra la pantalla de «Modificar suministro» en cada cambio (pasos 2 a 6 y extensiones 5a a 5g y 6a): desde cuándo rige un cambio de
    cada detalle, el precio propuesto, la simulación de la ventana de los detalles nuevos y los errores por campo (no los lanza). **No escribe
    ni bloquea.**"""
    return _analizar_modificacion(actor, suministro_id, cambios, None, estricto=False, verificar_stock=True)


def resumen_de_modificacion(actor, suministro_id, cambios, huella):
    """Paso 8: valida todo como al registrar (``ValidationError`` por campo) y arma el resumen con cada cambio y la fecha desde la que rige. No
    escribe."""
    datos = _analizar_modificacion(actor, suministro_id, cambios, huella, estricto=True, verificar_stock=True)
    if datos.errores:
        _lanzar(datos.errores, datos.codigos)
    return ResumenDeModificacion(datos)


def _texto_de_fecha(fecha):
    """«dd/mm/aaaa» para la auditoría."""
    return f"{fecha:%d/%m/%Y}"


def modificar_suministro(actor, suministro_id, cambios, huella):
    """COM-MOD-SUM: aplica los cambios y devuelve el suministro (con ``detalles_finalizados`` y ``detalles_creados``).

    - Precondición a: Vendedor del contrato o Gerente activo (``PermissionDenied``). Errores por campo como en ``resumen_de_modificacion``;
      10a (``ventana_cambio``) y 10b (``contrato_cambio``, ``rescision_acordada``) se verifican con el contrato ya bloqueado.
    - Paso 10 en UNA transacción (bloqueos en el encabezado de la sección): finaliza y crea los detalles (el sucesor lleva su cláusula nueva; las
      reservas siguen con el detalle anterior), actualiza el contrato y su cláusula, reserva los períodos de la ventana de los detalles nuevos
      (``asignar``; si alguno no se cubre, ``stock_insuficiente`` y se revierte todo), y pasa el contrato a «finalizado» si no le queda ningún período.
    - Postcondiciones i y j y D-36: las notificaciones (dentro de la transacción, D-42) y UN registro ``modificacion_suministro``.
    - Paso 11, FUERA de la transacción (D-14, D-54): el comprobante del contrato modificado.
    """
    previo = _analizar_modificacion(actor, suministro_id, cambios, huella, estricto=True, verificar_stock=True)
    if previo.errores:
        _lanzar(previo.errores, previo.codigos)
    vendedor_actual_id = previo.suministro.vendedor_id
    vendedor_final_id = previo.vendedor_final.pk
    periodos_previos = _periodos_a_reservar(previo.plan.nuevas, previo.ventana)
    periodos = periodos_previos
    with transaction.atomic():
        cuentas = {
            u.pk: u
            for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, vendedor_actual_id, vendedor_final_id}).order_by("pk")
        }
        quien = cuentas.get(actor.pk)
        if quien is None or not quien.is_active or rol_de(quien) not in (GERENTE, VENDEDOR):
            raise PermissionDenied(MENSAJE_SIN_ACCESO)
        if vendedor_final_id != vendedor_actual_id and (not cuentas[vendedor_final_id].is_active or rol_de(cuentas[vendedor_final_id]) != VENDEDOR):
            raise _error_de_campo("vendedor", "Elegí un Vendedor activo con invernaderos activos.", "vendedor_invalido")

        bloqueados = []
        if previo.plan.nuevas:
            for invernadero in previo.habilitados:
                try:
                    actual = bloquear_invernadero_activo(invernadero.pk)
                except ValidationError:
                    continue  # se dio de baja mientras se cargaba la modificación
                if actual.vendedor_id == vendedor_final_id:
                    bloqueados.append(actual)
            ahora = set(
                Invernadero.objects.filter(vendedor_id=vendedor_final_id, estado_invernadero=Invernadero.Estado.ACTIVO).values_list("pk", flat=True)
            )
            if periodos_previos and not ahora <= {i.pk for i in bloqueados}:
                raise ValidationError(
                    "Mientras cargabas los cambios, cambiaron los invernaderos del Vendedor. Volvé a intentarlo.", code="cambio_simultaneo"
                )
            cliente = Cliente.objects.select_for_update(no_key=True).get(pk=previo.suministro.cliente_id)
            activas = set(
                DireccionCliente.objects.filter(cliente=cliente, direccion__estado_direccion=Direccion.Estado.ACTIVO).values_list("direccion_id", flat=True)
            )
            for fila in previo.plan.nuevas:
                if fila.direccion.pk not in activas:
                    raise _error_de_campo(f"detalle-{fila.renglon.indice}-direccion", "La dirección ya no está activa: elegí otra.", "direccion_no_valida")
            for variedad_id in sorted({f.variedad.pk for f in previo.plan.nuevas}):
                try:
                    bloquear_variedad(variedad_id)
                except ValidationError as error:
                    fila = next(f for f in previo.plan.nuevas if f.variedad.pk == variedad_id)
                    raise _error_de_campo(f"detalle-{fila.renglon.indice}-variedad", "Esa variedad ya no está disponible.", "variedad_inactiva") from error
            if periodos_previos:
                stock_maduro.bloquear_candidatos(sorted({f.variedad.pk for f in previo.plan.nuevas}), [i.pk for i in bloqueados])

        # El contrato y sus detalles, al final (el mismo orden que la pre-reserva).
        Suministro.objects.select_for_update(no_key=True).get(pk=suministro_id)
        list(DetalleSuministro.objects.select_for_update(no_key=True).filter(suministro_id=suministro_id).order_by("pk"))

        # Con todo bloqueado, 10a y 10b se verifican sobre lo ya confirmado por las demás operaciones; el stock lo decide `asignar`.
        datos = _analizar_modificacion(actor, suministro_id, cambios, huella, estricto=True, verificar_stock=False)
        if datos.errores:
            _lanzar(datos.errores, datos.codigos)
        plan, hoy = datos.plan, datos.hoy
        periodos = _periodos_a_reservar(plan.nuevas, datos.ventana)
        if periodos and not periodos_previos:  # un período entró en la ventana después de bloquear: nada de lotes tomado
            raise ValidationError(MENSAJE_VENTANA_CAMBIO, code="ventana_cambio")
        s = Suministro.objects.get(pk=suministro_id)
        cambios_de_auditoria = {}

        def anotar(campo, antes, despues):
            cambios_de_auditoria[campo] = {"antes": antes, "despues": despues}

        # Postcondiciones d, e, f y g: el contrato y su cláusula.
        for campo, (antes, despues) in plan.contrato.items():
            if campo == "vendedor":
                s.vendedor = despues
                anotar("vendedor", referencia(antes), referencia(despues))
            elif campo in ("plazo_pago_dias", "indemnizacion_retraso_pago"):
                setattr(s.clausula_suministrado, campo, despues)
                anotar(campo, str(antes), str(despues))
            else:
                setattr(s, campo, despues)
                anotar(campo, _texto_de_fecha(antes) if campo == "fecha_fin" else str(antes), _texto_de_fecha(despues) if campo == "fecha_fin" else str(despues))
        if plan.contrato:
            s.save()
            s.clausula_suministrado.save()

        # Postcondiciones a y c: finalizar los detalles (primero, para liberar el par vigente) y crear los sucesores.
        finalizados, creados, clausulas = [], [], []
        a_finalizar = (
            [(x.detalle, x.fin_anterior) for x in plan.modificar] + list(plan.terminar) + list(plan.autofinalizar)
        )
        for d, fin in a_finalizar:
            DetalleSuministro.objects.filter(pk=d.pk).update(estado_detalle_suministro=DetalleSuministro.Estado.FINALIZADO, fecha_fin_detalle=fin)
            finalizados.append(DetalleSuministro.objects.get(pk=d.pk))
        for x in plan.modificar:
            v = x.valores
            ajuste = v["mecanismo"] == DetalleSuministro.Mecanismo.AJUSTE_PERIODICO
            sucesor = DetalleSuministro.objects.create(
                suministro=s, direccion_id=x.detalle.direccion_id, variedad_id=x.detalle.variedad_id, periodo_entrega_dias=v["periodo"],
                fecha_primer_entrega=x.rige, cantidad_por_periodo=v["cantidad"], mecanismo_precio=v["mecanismo"],
                estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE, precio_unitario_suministro=v["precio"],
                porcentaje_ajuste=v["porcentaje"] if ajuste else None, meses_ajuste=v["meses"] if ajuste else None,
                fecha_base_ajuste=x.rige, reemplaza_a=x.detalle,
            )
            creados.append(sucesor)
            clausulas.append(
                ClausulaSuministrante.objects.create(
                    detalle=sucesor, plazo_entrega_dias=v["plazo_entrega"], indemnizacion_retraso_entrega=v["retraso"],
                    cantidad_minima=v["minima"], indemnizacion_faltante=v["faltante"],
                )
            )

        # Postcondición b: los detalles nuevos, con su cláusula y los períodos de la ventana reservados.
        nuevos_detalles = []
        for fila in plan.nuevas:
            ajuste = fila.mecanismo == DetalleSuministro.Mecanismo.AJUSTE_PERIODICO
            nuevo = DetalleSuministro.objects.create(
                suministro=s, direccion_id=fila.direccion.pk, variedad=fila.variedad, periodo_entrega_dias=fila.periodo,
                fecha_primer_entrega=fila.primera, cantidad_por_periodo=fila.cantidad, mecanismo_precio=fila.mecanismo,
                estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE, precio_unitario_suministro=fila.precio,
                porcentaje_ajuste=fila.porcentaje if ajuste else None, meses_ajuste=fila.meses if ajuste else None,
                fecha_base_ajuste=fila.primera,
            )
            nuevos_detalles.append(nuevo)
            creados.append(nuevo)
            clausulas.append(
                ClausulaSuministrante.objects.create(
                    detalle=nuevo, plazo_entrega_dias=fila.plazo_entrega, indemnizacion_retraso_entrega=fila.indemnizacion_retraso,
                    cantidad_minima=fila.cantidad_minima, indemnizacion_faltante=fila.indemnizacion_faltante,
                )
            )
        por_fila = dict(zip(map(id, plan.nuevas), nuevos_detalles))
        reservas, cosechas, maximos = [], [], {}
        for fecha, _variedad_id, posicion, fila in periodos:
            resultado = stock_maduro.asignar(actor, Periodo(por_fila[id(fila)], fecha), fila.cantidad, fecha, "suministro")
            reservas.extend(resultado.reservas)
            cosechas.extend(resultado.cosechas)
            if resultado.sin_cubrir:
                maximos[posicion] = min(maximos.get(posicion, resultado.cubierta), resultado.cubierta)
        if maximos:
            errores = {
                f"detalle-{plan.nuevas[posicion].renglon.indice}-cantidad": [
                    ValidationError(f"Hay {maximo} plantas disponibles para esa fecha.", code="stock_insuficiente")
                ]
                for posicion, maximo in maximos.items()
            }
            errores[NO_CAMPO] = [ValidationError(MENSAJE_STOCK_CAMBIO, code="stock_insuficiente")]
            raise ValidationError(errores)  # revierte todo (paso 10; garantía mínima 1)

        # Estado del contrato al terminar todo (regla 5 de 8.11): sin detalles vigentes y sin períodos desde hoy, pasa a «finalizado».
        restantes = _detalles_de(s)
        if not any(d.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE for d in restantes) and not any(
            calendario.calendario(d, desde=hoy) for d in restantes
        ):
            anotar("estado_suministro", "vigente", "finalizado")
            s.estado_suministro = Suministro.Estado.FINALIZADO
            s.save(update_fields=["estado_suministro"])

        resumen = "; ".join(c.texto for c in datos.cambios)
        resumen = resumen if len(resumen) <= 380 else resumen[:377] + "…"
        if vendedor_final_id != vendedor_actual_id:
            notificaciones.notificar(
                cuentas[vendedor_actual_id], "Suministro reasignado", f"{s.codigo} pasó a {cuentas[vendedor_final_id].get_full_name()}."
            )
            notificaciones.notificar(
                cuentas[vendedor_final_id], "Suministro a tu cargo", f"Quedó a cargo de {s.codigo}, de {s.cliente}."
            )
        elif rol_de(quien) == GERENTE:
            notificaciones.notificar(cuentas[vendedor_actual_id], "Suministro modificado", f"El Gerente modificó {s.codigo}: {resumen}.")

        lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).select_related("lote", "partida").order_by("pk"))
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_SUMINISTRO,
            afectados=[s, *finalizados, *creados, *clausulas, *reservas, *lineas, *cosechas],
            detalle={
                "cambios": cambios_de_auditoria,
                "datos": {
                    "suministro": referencia(s),
                    "detalles_finalizados": [f"{d.variedad}: hasta el {_texto_de_fecha(d.fecha_fin_detalle)}" for d in finalizados],
                    "detalles_creados": [
                        f"{d.variedad}: {d.cantidad_por_periodo} cada {d.periodo_entrega_dias} días desde {_texto_de_fecha(d.fecha_primer_entrega)} a {d.precio_unitario_suministro}"
                        for d in creados
                    ],
                    "periodos_reservados": str(len(periodos)),
                    "reservas": [f"{r} · {r.invernadero} · {r.get_estado_reserva_display().lower()}" for r in reservas],
                    "cosechas": [c.codigo for c in cosechas],
                },
            },
        )

    # Paso 11 y extensión 11a: FUERA de la transacción (D-14, D-54).
    s.estado_comprobante = comprobantes.enviar_comprobante(s, tipo="modificacion", cambios=datos.cambios)
    if s.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        comprobantes.avisar_comprobante_pendiente(actor, s)
    s.detalles_finalizados = finalizados
    s.detalles_creados = creados
    return s


# ---- rescindir y dejar sin efecto la rescisión (COM-RSC-SUM y COM-ANL-RSC, COM-03b) y el cierre diario ----
#
# La rescisión es por mutuo acuerdo (art. 1076 del Código Civil y Comercial): produce efectos solo hacia el futuro. Registrarla conserva los períodos que ya
# están en la ventana de pre-reserva (fija `fecha_fin_detalle` de cada detalle vigente) y no reserva nada más; el contrato sigue «vigente» hasta la última
# entrega conservada y el paso diario 35 (`cerrar_rescisiones`) lo pasa a «rescindido». Dejarla sin efecto vuelve todo atrás mientras no pase esa fecha.
#
# Bloqueos (docs/patrones/bloqueos.md, sección `comercial`, «Suministros»; ``FOR NO KEY UPDATE``): las cuentas (quien actúa y el Vendedor del contrato) → el
# `Suministro` y sus detalles. No toma stock: no bloquea invernaderos ni lotes, así que no se cruza con una pre-reserva más que en la cuenta del Vendedor y en
# el contrato. Sale siempre en una sola transacción; el correo, después (D-14, D-54).

MOTIVOS_DE_RESCISION = Suministro.MotivoDeRescision.values
LARGO_MAXIMO_DE_TEXTO = 500
MENSAJE_YA_RESCINDIDO = "Ya tiene una rescisión acordada."
MENSAJE_SIN_RESCISION = "El contrato no tiene una rescisión acordada."
MENSAJE_RESCISION_CERRADA = "Ya pasó la fecha de la última entrega: la rescisión no se puede dejar sin efecto."
logger = logging.getLogger("infoponia.suministros")


@dataclass
class PedidoDeRescision:
    """Lo que carga la ventana «Rescindir suministro», todo texto (como llegó): ``acuerdo`` es «1» si el Gerente marcó «Confirmo que la rescisión se acordó con
    el cliente»."""

    motivo: str = ""
    descripcion: str = ""
    fecha_acuerdo: str = ""
    acuerdo: str = ""

    @classmethod
    def desde_post(cls, datos):
        """Arma el pedido de un ``QueryDict`` (o un diccionario): ``motivo``, ``descripcion``, ``fecha_acuerdo`` y ``acuerdo``."""
        return cls(
            motivo=datos.get("motivo", ""),
            descripcion=datos.get("descripcion", ""),
            fecha_acuerdo=datos.get("fecha_acuerdo", ""),
            acuerdo=datos.get("acuerdo", ""),
        )


@dataclass
class DatosDeRescision:
    """Lo que presenta la ventana de rescindir (paso 2): los períodos que se conservan y la fecha de la última entrega."""

    suministro: object
    hoy: date
    ventana: date
    huella: str
    conservados: list  # [(id del detalle, fecha)], por fecha y, con la misma, por detalle
    fecha_ultima_entrega: date | None
    rescinde_en_el_acto: bool  # 2a: no hay períodos conservados


def periodos_conservados(suministro, hoy):
    """Regla «Períodos que se conservan»: los de los detalles vigentes con fecha entre ``hoy`` y ``hoy`` + días de pre-reserva (los ya reservados, con cosecha o con
    entrega planificada), por fecha y, con la misma fecha, por id del detalle. ``[(id del detalle, fecha)]``."""
    ventana = calendario.ventana(hoy)
    conservados = [
        (d.pk, fecha)
        for d in _detalles_de(suministro)
        if d.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE
        for fecha in calendario.calendario(d, desde=hoy, hasta=ventana)
    ]
    return sorted(conservados, key=lambda c: (c[1], c[0]))


def _exigir_gerente(actor):
    """Solo el Gerente rescinde y deja sin efecto la rescisión (regla «Quién rescinde»)."""
    _exigir_actor(actor)
    if rol_de(actor) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _exigir_vigente_sin_rescision(suministro, huella):
    """6b: el contrato sigue «vigente», sin rescisión acordada y sin cambios desde la lectura (``huella``; ``None`` no la compara)."""
    if suministro.estado_suministro != Suministro.Estado.VIGENTE:
        raise _error_de_campo(NO_CAMPO, MENSAJE_CONTRATO_CAMBIO, "contrato_cambio")
    if suministro.tiene_rescision_acordada:
        raise _error_de_campo(NO_CAMPO, MENSAJE_YA_RESCINDIDO, "rescision_acordada")
    if huella is not None and huella != huella_de(suministro):
        raise _error_de_campo(NO_CAMPO, MENSAJE_CONTRATO_CAMBIO, "contrato_cambio")


def datos_de_rescision(actor, suministro_id):
    """Pasos 1 y 2: lo que ve el Gerente al abrir «Rescindir suministro»: los períodos que se conservan (los de la ventana de pre-reserva), la fecha de la última
    entrega y la huella del contrato. **No escribe ni bloquea.** ``PermissionDenied`` si no es el Gerente; ``ValidationError`` (``contrato_cambio`` o
    ``rescision_acordada``) si el contrato no se puede rescindir."""
    _exigir_gerente(actor)
    s = suministro_del_alcance(actor, suministro_id)
    _exigir_vigente_sin_rescision(s, None)
    hoy = stock.hoy()
    conservados = periodos_conservados(s, hoy)
    return DatosDeRescision(
        suministro=s,
        hoy=hoy,
        ventana=calendario.ventana(hoy),
        huella=huella_de(s),
        conservados=conservados,
        fecha_ultima_entrega=max((f for _, f in conservados), default=None),
        rescinde_en_el_acto=not conservados,
    )


def _validar_pedido_de_rescision(pedido, hoy):
    """Paso 3 y extensión 4a: el motivo (lista cerrada), la descripción (obligatoria con «otro», hasta 500), la fecha del acuerdo (no futura) y la casilla del
    acuerdo con el cliente. Devuelve ``(errores, motivo, descripcion, fecha)``."""
    err = _Errores()
    motivo, descripcion = _texto(pedido.motivo), _texto(pedido.descripcion)
    if not motivo:
        err.agregar("motivo", "motivo_obligatorio", "Elegí el motivo de la rescisión.")
    elif motivo not in MOTIVOS_DE_RESCISION:
        err.agregar("motivo", "motivo_invalido", "Elegí uno de los motivos de la lista.")
    if len(descripcion) > LARGO_MAXIMO_DE_TEXTO:
        err.agregar("descripcion", "descripcion_larga", f"Hasta {LARGO_MAXIMO_DE_TEXTO} caracteres.")
    elif motivo == Suministro.MotivoDeRescision.OTRO and not descripcion:
        err.agregar("descripcion", "descripcion_obligatoria", "Con el motivo «Otro», contá cuál fue.")
    fecha = None
    if not _texto(pedido.fecha_acuerdo):
        err.agregar("fecha_acuerdo", "fecha_obligatoria", "Ingresá la fecha en que acordaron la rescisión.")
    elif (fecha := _fecha(pedido.fecha_acuerdo)) is None:
        err.agregar("fecha_acuerdo", "fecha_invalida", "Ingresá una fecha válida (dd/mm/aaaa).")
    elif fecha > hoy:
        err.agregar("fecha_acuerdo", "fecha_futura", f"No puede ser posterior al {_fecha_texto(hoy)}.")
    if _texto(pedido.acuerdo) != "1":
        err.agregar("acuerdo", "acuerdo_sin_confirmar", "Confirmá que la rescisión se acordó con el cliente: sin su acuerdo no se puede rescindir.")
    return err, motivo, descripcion, fecha


def _bloquear_para_rescision(actor, suministro_id):
    """Los bloqueos de la sección: las cuentas (quien actúa y el Vendedor del contrato) y después el `Suministro` y sus detalles. Devuelve ``(cuentas, suministro)``
    con el suministro releído ya bloqueado y sus detalles asignados."""
    vendedor_id = Suministro.objects.values_list("vendedor_id", flat=True).get(pk=suministro_id)
    cuentas = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in={actor.pk, vendedor_id}).order_by("pk")}
    quien = cuentas.get(actor.pk)
    if quien is None or not quien.is_active or rol_de(quien) != GERENTE:
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    Suministro.objects.select_for_update(no_key=True).get(pk=suministro_id)
    list(DetalleSuministro.objects.select_for_update(no_key=True).filter(suministro_id=suministro_id).order_by("pk"))
    return cuentas, Suministro.objects.select_related("cliente", "vendedor", "clausula_suministrado").get(pk=suministro_id)


def rescindir_suministro(actor, suministro_id, pedido, huella, conservados):
    """COM-RSC-SUM: registra la rescisión por mutuo acuerdo y devuelve el suministro.

    - Precondición a y regla «Quién rescinde»: solo el Gerente activo (``PermissionDenied``). Extensión 4a: ``ValidationError`` por campo (``motivo``,
      ``descripcion``, ``fecha_acuerdo`` y ``acuerdo``).
    - Paso 6 en UNA transacción, con los bloqueos de la sección: vuelve a verificar que el contrato siga «vigente» sin rescisión acordada y sin cambios (6b:
      ``contrato_cambio`` o ``rescision_acordada``; ``huella`` ``None`` no se compara) y que los períodos que se conservan sean los que vio el Gerente
      (``conservados``; 6a: ``ventana_cambio``; ``None`` no se compara). Después carga los datos de la rescisión y la fecha de fin de cada detalle vigente: su último
      período dentro de la ventana o, sin ninguno, el último día de la ventana. Sin períodos conservados (2a) el contrato queda «rescindido» en el acto, con la
      fecha de la última entrega y la de rescisión en hoy (la restricción de la base exige la fecha), y sus detalles «finalizados».
    - No aplica multa ni indemnización y no suma incumplimientos (postcondición d). Postcondiciones f y g y D-36: la notificación al Vendedor (D-42) y UN registro
      ``rescision_suministro``.
    - Paso 7, FUERA de la transacción: la constancia (``estado_comprobante``: «pendiente de envío» o «para imprimir», 7a y 7b).
    """
    _exigir_gerente(actor)
    suministro_del_alcance(actor, suministro_id)
    err, motivo, descripcion, fecha_acuerdo = _validar_pedido_de_rescision(pedido, stock.hoy())
    if err.mensajes:
        _lanzar(err.mensajes, err.codigos)
    with transaction.atomic():
        cuentas, s = _bloquear_para_rescision(actor, suministro_id)
        _exigir_vigente_sin_rescision(s, huella)
        hoy = stock.hoy()
        ventana = calendario.ventana(hoy)
        actuales = periodos_conservados(s, hoy)
        if conservados is not None and sorted(tuple(c) for c in conservados) != sorted(actuales):
            raise _error_de_campo(NO_CAMPO, MENSAJE_VENTANA_CAMBIO, "ventana_cambio")
        if fecha_acuerdo > hoy:  # el día cambió entre la validación y el bloqueo
            raise _error_de_campo("fecha_acuerdo", f"No puede ser posterior al {_fecha_texto(hoy)}.", "fecha_futura")
        ultima = max((f for _, f in actuales), default=hoy)
        en_el_acto = not actuales
        vigentes = [d for d in _detalles_de(s) if d.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE]
        lineas_de_detalles, afectados = [], [s]
        for d in vigentes:
            hasta = calendario.calendario(d, hasta=ventana)
            fin = hasta[-1] if hasta else ventana
            DetalleSuministro.objects.filter(pk=d.pk).update(
                fecha_fin_detalle=fin, **({"estado_detalle_suministro": DetalleSuministro.Estado.FINALIZADO} if en_el_acto else {})
            )
            lineas_de_detalles.append(f"{d.variedad}: fecha de fin del detalle {_fecha_texto(fin)}")
            afectados.append(DetalleSuministro.objects.get(pk=d.pk))
        s.motivo_rescision, s.descripcion_rescision = motivo, descripcion
        s.fecha_acuerdo_rescision, s.fecha_registro_rescision, s.fecha_ultima_entrega_rescision = fecha_acuerdo, hoy, ultima
        if en_el_acto:
            s.estado_suministro, s.fecha_rescision = Suministro.Estado.RESCINDIDO, hoy
        s.save()
        notificaciones.notificar(
            cuentas[s.vendedor_id],
            "Rescisión de suministro",
            f"El Gerente registró la rescisión de {s.codigo} ({s.cliente}) por mutuo acuerdo. "
            + ("El contrato quedó rescindido." if en_el_acto else f"Se entrega hasta el {_fecha_texto(ultima)}."),
        )
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.RESCISION_SUMINISTRO,
            afectados=afectados,
            detalle={
                **({"cambios": {"estado_suministro": {"antes": "vigente", "despues": "rescindido"}}} if en_el_acto else {}),
                "datos": {
                    "motivo_rescision": motivo,
                    "descripcion_rescision": descripcion or "—",
                    "fecha_acuerdo_rescision": _fecha_texto(fecha_acuerdo),
                    "fecha_ultima_entrega_rescision": _fecha_texto(ultima),
                    "detalles": lineas_de_detalles,
                },
            },
        )
    s.estado_comprobante = comprobantes.enviar_comprobante(s, tipo="rescision")
    if s.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        comprobantes.avisar_comprobante_pendiente(actor, s)
    return s


def dejar_sin_efecto_rescision(actor, suministro_id, motivo, huella):
    """COM-ANL-RSC: vuelve atrás la rescisión acordada y devuelve el suministro.

    - Solo el Gerente (``PermissionDenied``). Regla 1: ``motivo`` obligatorio, en texto libre, hasta 500 caracteres (``motivo_obligatorio``, ``motivo_largo``).
    - Regla 2, en UNA transacción con los bloqueos de la sección: el contrato sigue «vigente» (``contrato_cambio``), con una rescisión acordada
      (``sin_rescision``), sin cambios desde la lectura (``huella``) y la fecha actual no es posterior a la de la última entrega (``rescision_cerrada``).
    - Postcondición a: los seis campos de la rescisión vuelven a nulo/vacío (la historia queda en la auditoría) y cada detalle VIGENTE sin fecha de fin. La
      pre-reserva diaria toma los períodos que entraron en la ventana (postcondición b). Postcondiciones c y d: la notificación al Vendedor, UN registro
      ``anulacion_rescision`` con el motivo y la rescisión que quedó sin efecto, y la constancia (regla 4), fuera de la transacción.
    """
    _exigir_gerente(actor)
    suministro_del_alcance(actor, suministro_id)
    motivo = _texto(motivo)
    if not motivo:
        raise _error_de_campo("motivo", "Contá por qué se deja sin efecto la rescisión.", "motivo_obligatorio")
    if len(motivo) > LARGO_MAXIMO_DE_TEXTO:
        raise _error_de_campo("motivo", f"Hasta {LARGO_MAXIMO_DE_TEXTO} caracteres.", "motivo_largo")
    with transaction.atomic():
        cuentas, s = _bloquear_para_rescision(actor, suministro_id)
        if s.estado_suministro != Suministro.Estado.VIGENTE:
            raise _error_de_campo(NO_CAMPO, MENSAJE_CONTRATO_CAMBIO, "contrato_cambio")
        if not s.tiene_rescision_acordada:
            raise _error_de_campo(NO_CAMPO, MENSAJE_SIN_RESCISION, "sin_rescision")
        if huella is not None and huella != huella_de(s):
            raise _error_de_campo(NO_CAMPO, MENSAJE_CONTRATO_CAMBIO, "contrato_cambio")
        if s.fecha_ultima_entrega_rescision < stock.hoy():
            raise _error_de_campo(NO_CAMPO, MENSAJE_RESCISION_CERRADA, "rescision_cerrada")
        anterior = SimpleNamespace(
            motivo=s.motivo_rescision, descripcion=s.descripcion_rescision, acuerdo=s.fecha_acuerdo_rescision, ultima=s.fecha_ultima_entrega_rescision
        )
        afectados, lineas_de_detalles = [s], []
        for d in [d for d in _detalles_de(s) if d.estado_detalle_suministro == DetalleSuministro.Estado.VIGENTE]:
            lineas_de_detalles.append(f"{d.variedad}: tenía fecha de fin {_fecha_texto(d.fecha_fin_detalle) if d.fecha_fin_detalle else 'sin fecha'}")
            DetalleSuministro.objects.filter(pk=d.pk).update(fecha_fin_detalle=None)
            afectados.append(DetalleSuministro.objects.get(pk=d.pk))
        s.motivo_rescision, s.descripcion_rescision = None, ""
        s.fecha_acuerdo_rescision = s.fecha_registro_rescision = s.fecha_ultima_entrega_rescision = None
        s.save()
        notificaciones.notificar(
            cuentas[s.vendedor_id],
            "Rescisión sin efecto",
            f"El Gerente dejó sin efecto la rescisión de {s.codigo} ({s.cliente}). El contrato sigue como estaba.",
        )
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ANULACION_RESCISION,
            afectados=afectados,
            detalle={
                "datos": {
                    "motivo_anulacion": motivo,
                    "motivo_rescision": anterior.motivo,
                    "descripcion_rescision": anterior.descripcion or "—",
                    "fecha_acuerdo_rescision": _fecha_texto(anterior.acuerdo),
                    "fecha_ultima_entrega_rescision": _fecha_texto(anterior.ultima),
                    "detalles": lineas_de_detalles,
                }
            },
        )
    s.estado_comprobante = comprobantes.enviar_comprobante(s, tipo="anulacion_rescision")
    if s.estado_comprobante == Suministro.EstadoDelComprobante.PENDIENTE_ENVIO:
        comprobantes.avisar_comprobante_pendiente(actor, s)
    return s


def _cerrar_rescision(suministro_id, hoy):
    """Cierra la rescisión de un contrato en su transacción: ``True`` si lo pasó a «rescindido», ``False`` si ya no correspondía (otra operación lo cambió)."""
    with transaction.atomic():
        vendedor_id = Suministro.objects.values_list("vendedor_id", flat=True).get(pk=suministro_id)
        list(Usuario.objects.select_for_update(no_key=True).filter(pk=vendedor_id))
        Suministro.objects.select_for_update(no_key=True).get(pk=suministro_id)
        list(DetalleSuministro.objects.select_for_update(no_key=True).filter(suministro_id=suministro_id).order_by("pk"))
        s = Suministro.objects.get(pk=suministro_id)
        if not s.tiene_rescision_acordada or s.fecha_ultima_entrega_rescision >= hoy:
            return False
        if Entrega.objects.filter(contrato_entrega_id=suministro_id, estado_orden="a_realizar").exists():
            return False  # punto 6 de «Cuando exista Entrega»: el cierre espera las entregas del contrato (si queda una atrasada, sigue «vigente»)
        s.estado_suministro, s.fecha_rescision = Suministro.Estado.RESCINDIDO, s.fecha_ultima_entrega_rescision
        s.save()
        vigentes = list(s.detalles.filter(estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE).order_by("pk"))
        s.detalles.filter(pk__in=[d.pk for d in vigentes]).update(estado_detalle_suministro=DetalleSuministro.Estado.FINALIZADO)
        RegistroAuditoria.objects.registrar(
            usuario=None,
            accion=RegistroAuditoria.Accion.CIERRE_RESCISION,
            afectados=[s, *s.detalles.filter(pk__in=[d.pk for d in vigentes]).order_by("pk")],
            detalle={
                "cambios": {"estado_suministro": {"antes": "vigente", "despues": "rescindido"}},
                "datos": {"fecha_rescision": _fecha_texto(s.fecha_rescision), "detalles": [f"{d.variedad}: finalizado" for d in vigentes]},
            },
        )
        return True


def cerrar_rescisiones(hoy):
    """Paso diario 35 (D-56): pasa a «rescindido» los suministros «vigentes» con rescisión acordada cuya última entrega conservada ya pasó (el día siguiente), con
    ``fecha_rescision`` = esa fecha, y sus detalles vigentes a «finalizado». Un contrato por transacción; idempotente; nunca lee la fecha por su cuenta. Un contrato que
    falla queda en el log y los demás siguen. Desde COM-05a1 espera las entregas del contrato «a realizar» (si queda una atrasada, sigue «vigente» y se cierra el día que se concrete o se cancele).
    Devuelve ``ResumenDePaso(procesados=N, creados=0, resueltos=N, detalle="N suministros rescindidos")``."""
    pendientes = list(
        Suministro.objects.filter(
            estado_suministro=Suministro.Estado.VIGENTE, motivo_rescision__isnull=False, fecha_ultima_entrega_rescision__lt=hoy
        )
        .exclude(pk__in=Entrega.objects.filter(estado_orden="a_realizar").values("contrato_entrega_id"))  # el cierre espera las entregas a realizar del contrato
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    cerrados = 0
    for suministro_id in pendientes:
        try:
            cerrados += 1 if _cerrar_rescision(suministro_id, hoy) else 0
        except Exception:  # noqa: BLE001 - un contrato que falla no puede dejar a los demás sin cerrar (D-56, punto 5)
            logger.exception("Falló el cierre de la rescisión del suministro %s", suministro_id)
    return ResumenDePaso(cerrados, 0, cerrados, f"{cerrados} suministros rescindidos")
