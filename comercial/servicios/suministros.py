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

import re
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
    Cliente,
    ClausulaSuministrado,
    ClausulaSuministrante,
    DetalleReserva,
    DetalleSuministro,
    DireccionCliente,
    Suministro,
)
from comercial.servicios import calendario, comprobantes, stock_maduro
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
from comercial.servicios.stock_maduro import Periodo
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import stock
from inventario.servicios.variedades import bloquear_variedad
from maestros.models import Direccion, Invernadero, Variedad
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


def _advertir_superposiciones(cargadas, cliente, estricto, err):
    """Extensión 9d: el cliente ya tiene otro suministro vigente de la misma variedad a la misma dirección. Advertencia con el código del otro
    contrato y su casilla «Continuar igual»; al resumir o registrar, sin la casilla, es un error (continuar es una decisión explícita). Dos
    consultas, igual con uno que con muchos detalles."""
    pares = [(f.variedad.pk, f.direccion.pk) for f in cargadas if f.variedad is not None and f.direccion is not None]
    if cliente is None or not pares:
        return
    filas = DetalleSuministro.objects.filter(
        suministro__cliente=cliente,
        suministro__estado_suministro=Suministro.Estado.VIGENTE,
        estado_detalle_suministro=DetalleSuministro.Estado.VIGENTE,
        variedad_id__in={v for v, _ in pares},
        direccion_id__in={d for _, d in pares},
    ).order_by("suministro_id").values_list("variedad_id", "direccion_id", "suministro_id")
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
    - Postcondición f (planificar la entrega de un período que salió todo de cámara): se completa en COM-05.
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
TEXTOS_DE_SITUACION = {"pasado": "Pasado", "reservado": "Reservado", "fuera_de_la_ventana": "Fuera de la ventana"}


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
    """Regla 6: un período (fecha, detalle) con su situación: ``pasado``, ``reservado``, ``sin_cobertura`` o ``fuera_de_la_ventana``."""

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
    filas = []
    for fecha, detalle, reemplazado in fechas:
        faltan = 0
        if fecha < hoy:
            situacion, texto = "pasado", TEXTOS_DE_SITUACION["pasado"]
        elif fecha <= ventana:
            faltan = sin_cubrir[Periodo(detalle, fecha)]
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
        historial, anterior = [], por_id.get(d.reemplaza_a_id)
        while anterior is not None:
            historial.insert(0, anterior)
            anterior = por_id.get(anterior.reemplaza_a_id)
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
    )


def calendario_completo(actor, suministro_id, pagina=1):
    """«Ver todo el calendario» (regla 6): la ``Page`` (de a 100) de todos los períodos de todos los detalles, por fecha, con su situación. La
    situación se calcula solo para los de la página. 404 si no existe; ``PermissionDenied`` si no es del alcance."""
    suministro = suministro_del_alcance(actor, suministro_id)
    hoy = stock.hoy()
    pagina_de_fechas = Paginator(_fechas_de(_detalles_de(suministro)), POR_PAGINA_DEL_CALENDARIO).get_page(pagina)
    pagina_de_fechas.object_list = _filas_de_calendario(list(pagina_de_fechas.object_list), hoy, calendario.ventana(hoy))
    return pagina_de_fechas
