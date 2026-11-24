# Servicios de compra-venta (COM-02): COM-REG-CVT, Registrar Compra-venta, y COM-CNS-CVT, Consultar Compra-venta
# (docs/casos_de_uso/comercial/compra_venta.md, «Cómo se aplica en la ronda «Comercial 1»»).
#
# La venta en curso NO se guarda (pasos 2 a 13): vive en el formulario. Cada cambio vuelve a pedir `datos_del_formulario`, que no escribe ni
# bloquea y usa `stock_maduro.disponible` (una consulta por tabla: nada por renglón). `registrar_compra_venta` es la única que escribe.
#
# Bloqueos de `registrar_compra_venta` (docs/patrones/stock_maduro.md, sección 3; ``FOR NO KEY UPDATE``): las cuentas del actor y del
# Vendedor (una consulta, por id) → los invernaderos considerados (`bloquear_invernadero_activo`, por id) → el cliente → las variedades (por
# id) → los lotes y las partidas candidatos (por id) → las filas nuevas. Con todo bloqueado, el resultado de `asignar` ES la verificación del
# paso 14: si algún detalle no se cubre entero, `stock_insuficiente` y se revierte todo (extensión 14a). El correo sale DESPUÉS de confirmar.

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.shortcuts import get_object_or_404

from comercial.models import Cliente, CompraVenta, DetalleReserva, DetalleVenta, DireccionCliente, ReservaStock
from comercial.servicios import clientes as api_clientes
from comercial.servicios import comprobantes, stock_maduro
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario.servicios import stock
from inventario.servicios.variedades import bloquear_variedad
from maestros.models import Direccion, Invernadero, Variedad
from maestros.servicios.invernaderos import bloquear_invernadero_activo

GERENTE = Usuario.Rol.GERENTE
VENDEDOR = Usuario.Rol.VENDEDOR
Modalidad = CompraVenta.Modalidad
NO_CAMPO = "__all__"  # la clave de los errores que no son de un campo (`NON_FIELD_ERRORS`)
PRECIO_MAXIMO = Decimal("9999999999.99")  # el `DecimalField(12, 2)`
CENTAVOS = Decimal("0.01")
MENSAJE_SIN_ACCESO = "Tu cuenta no tiene acceso a esta acción."
POR_PAGINA = 50
MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR = "No tenés invernaderos activos asignados: pedile al Gerente que te asigne uno."
MENSAJE_SIN_VENDEDORES = "No hay Vendedores con invernaderos activos."


def siguiente_numero():
    """El número de la próxima compra-venta, de la secuencia ``comercial_compraventa_numero_seq`` (D-52 punto 3, como
    ``produccion.servicios.ordenes.siguiente_numero``). Puede haber huecos si una transacción se deshace (``docs/temas_abiertos.md``,
    «Huecos en el número de orden»). Nunca un ``max()+1``."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT nextval('comercial_compraventa_numero_seq')")
        return cursor.fetchone()[0]


def texto_de_pesos(valor):
    """«$ 1.500,50»: pesos con dos decimales, punto de miles y coma decimal (los precios y montos son en pesos argentinos)."""
    valor = Decimal(valor).quantize(CENTAVOS)
    entero, decimales = f"{abs(valor):.2f}".split(".")
    entero = f"{int(entero):,}".replace(",", ".")
    return f"{'-' if valor < 0 else ''}$ {entero},{decimales}"


# ---- lo que carga el formulario ----


@dataclass
class Renglon:
    """Un renglón del formulario, tal como llegó (texto). ``indice`` es su posición en el formulario (nombra sus campos y sus errores)."""

    indice: int = 0
    variedad_id: str = ""
    cantidad: str = ""
    precio: str = ""

    @property
    def vacio(self):
        """True si no se cargó nada."""
        return not (self.variedad_id.strip() or self.cantidad.strip() or self.precio.strip())


@dataclass
class DatosDeCompraVenta:
    """Lo que carga el formulario de COM-REG-CVT, todo como texto. ``vendedor_id`` solo lo elige el Gerente (extensión 1a)."""

    vendedor_id: str = ""
    cliente_id: str = ""
    fecha_pactada: str = ""
    modalidad: str = ""
    direccion_id: str = ""
    invernadero_id: str = ""
    renglones: list = field(default_factory=list)

    @classmethod
    def desde_post(cls, datos):
        """Arma los datos de un ``QueryDict`` (POST o GET): ``vendedor``, ``cliente``, ``fecha``, ``modalidad``, ``direccion``,
        ``invernadero`` y ``renglon-<i>-variedad|cantidad|precio``."""
        renglones = {}
        for clave in datos:
            coincidencia = re.fullmatch(r"renglon-(\d+)-(variedad|cantidad|precio)", clave)
            if coincidencia:
                renglones.setdefault(int(coincidencia.group(1)), Renglon(int(coincidencia.group(1))))
                setattr(
                    renglones[int(coincidencia.group(1))],
                    "variedad_id" if coincidencia.group(2) == "variedad" else coincidencia.group(2),
                    datos.get(clave, ""),
                )
        return cls(
            vendedor_id=datos.get("vendedor", ""),
            cliente_id=datos.get("cliente", ""),
            fecha_pactada=datos.get("fecha", ""),
            modalidad=datos.get("modalidad", ""),
            direccion_id=datos.get("direccion", ""),
            invernadero_id=datos.get("invernadero", ""),
            renglones=[renglones[i] for i in sorted(renglones)],
        )


@dataclass
class FilaDeRenglon:
    """Un renglón ya interpretado: la variedad, lo que hay disponible, el precio propuesto, el subtotal estimado y sus errores por campo."""

    renglon: Renglon
    variedad: object = None
    cantidad: int | None = None
    precio: Decimal | None = None
    disponible: int | None = None
    precio_propuesto: Decimal | None = None
    errores: dict = field(default_factory=dict)  # {"variedad"|"cantidad"|"precio": mensaje}

    @property
    def subtotal(self):
        """Cantidad × precio, si los dos son válidos (monto estimado: pasos 10 y 12)."""
        if self.cantidad is None or self.precio is None:
            return None
        return (Decimal(self.cantidad) * self.precio).quantize(CENTAVOS)


@dataclass
class FormularioDeCompraVenta:
    """Lo que muestra la pantalla de «Nueva compra-venta» en cada cambio (``datos_del_formulario``)."""

    datos: DatosDeCompraVenta
    es_gerente: bool
    vendedor: object  # el responsable (el actor, o el que eligió el Gerente), o None
    vendedores: list  # [(Vendedor, [Invernadero])] para el Gerente (extensión 1a)
    cliente: object
    direcciones: list  # las direcciones activas del cliente (hijas), para un envío
    direccion: object  # la elegida (hija) o None
    invernaderos_de_retiro: list  # los invernaderos activos del Vendedor, para un retiro
    invernadero_de_retiro: object
    habilitados: list  # los invernaderos de donde puede salir el stock
    fecha: date | None
    variedades_ofrecidas: list  # [(Variedad, Disponible)] con stock libre, más las ya cargadas
    filas: list
    monto_estimado: Decimal
    errores: dict  # {campo: [mensaje]}; las generales, bajo NO_CAMPO
    entrega_habilitada: bool
    variedades_habilitadas: bool
    sin_stock: bool
    cliente_sin_correo: bool

    @property
    def cargadas(self):
        """Los renglones con algo cargado. En el cálculo de pantalla (no estricto) ``filas`` también trae los renglones en blanco que dejó
        «Agregar variedad» (paso 9: siempre hay uno para completar); estos no cuentan como variedades de la venta."""
        return [f for f in self.filas if not f.renglon.vacio]

    @property
    def puede_revisar(self):
        """Se puede abrir el resumen: nada con error y al menos un renglón cargado."""
        return not self.errores and bool(self.cargadas)


# ---- el análisis (compartido por el formulario, el resumen y el registro) ----


def _texto(valor):
    """``valor`` como texto recortado (``None`` es vacío)."""
    return "" if valor is None else str(valor).strip()


def _entero(texto):
    """El entero positivo de un texto de dígitos (hasta 9), o ``None``."""
    texto = _texto(texto)
    return int(texto) if re.fullmatch(r"\d{1,9}", texto) else None


def _fecha(texto):
    """La fecha de un texto ``aaaa-mm-dd`` (calendario) o ``dd/mm/aaaa`` (teclado), o ``None``."""
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(_texto(texto), formato).date()
        except ValueError:
            continue
    return None


def _precio(texto):
    """El precio de un texto con coma decimal («1500,50» o «1.500,50») o con punto («1500.50»): mayor que cero, hasta dos decimales y
    hasta 9.999.999.999,99. ``None`` si no vale."""
    texto = _texto(texto).replace(" ", "").replace("$", "")
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", texto):
        return None
    valor = Decimal(texto)
    if valor != valor.quantize(CENTAVOS) or valor <= 0 or valor > PRECIO_MAXIMO:
        return None
    return valor.quantize(CENTAVOS)


def _exigir_actor(actor):
    """Precondición a: Vendedor o Gerente con la cuenta activa (SEG-13)."""
    if actor is None or not actor.is_active or rol_de(actor) not in (GERENTE, VENDEDOR):
        raise PermissionDenied(MENSAJE_SIN_ACCESO)


def _agregar(errores, campo, mensaje):
    """Suma un mensaje a los errores de ``campo``."""
    errores.setdefault(campo, []).append(mensaje)


def _vendedores_con_invernaderos():
    """``[(Vendedor, [Invernadero])]`` de los Vendedores activos con al menos un invernadero activo (extensión 1a y precondición b), por
    nombre. Una consulta."""
    por_vendedor = {}
    invernaderos = (
        Invernadero.objects.filter(estado_invernadero=Invernadero.Estado.ACTIVO, vendedor__is_active=True)
        .select_related("vendedor")
        .order_by("vendedor__last_name", "vendedor__first_name", "vendedor_id", "pk")
    )
    for invernadero in invernaderos:
        por_vendedor.setdefault(invernadero.vendedor_id, (invernadero.vendedor, []))[1].append(invernadero)
    return list(por_vendedor.values())


def puede_registrar(actor):
    """Precondición b: ``(True, "")`` si hay con qué vender; si no, ``(False, motivo)`` para mostrar «Nueva compra-venta» deshabilitado.
    La precondición c (stock libre) no se verifica de antemano: depende de la fecha (extensión 8a)."""
    _exigir_actor(actor)
    if rol_de(actor) == GERENTE:
        return (True, "") if _vendedores_con_invernaderos() else (False, MENSAJE_SIN_VENDEDORES)
    hay = Invernadero.objects.filter(vendedor_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).exists()
    return (True, "") if hay else (False, MENSAJE_SIN_INVERNADEROS_DEL_VENDEDOR)


def _ultimos_precios(variedad_ids):
    """``{variedad_id: último precio}`` de cualquier compra-venta, Vendedor y estado (paso 9: «el último precio usado para ella»; confirmado
    por el estudiante el 21/11/2026): el detalle más reciente por fecha de realización del contrato y después por id. Una consulta."""
    filas = (
        DetalleVenta.objects.filter(variedad_id__in=list(variedad_ids))
        .order_by("variedad_id", "-compra_venta__fecha_realizacion", "-pk")
        .distinct("variedad_id")
        .values_list("variedad_id", "precio_unitario_de_venta")
    )
    return dict(filas)


def _analizar(actor, datos, estricto):
    """Interpreta los ``datos`` sin escribir ni bloquear: el Vendedor responsable, el cliente, la entrega, lo disponible y cada renglón, con
    sus errores por campo (pasos 1 a 12). Con ``estricto`` (resumen y registro) exige además lo que falte; sin él (cada cambio de la
    pantalla) lo que todavía no se eligió no es un error y una dirección o un invernadero que ya no corresponden se descartan en silencio
    (extensiones 13a.1a y 13a.1b). Devuelve un ``FormularioDeCompraVenta``."""
    _exigir_actor(actor)
    hoy = stock.hoy()
    errores = {}
    es_gerente = rol_de(actor) == GERENTE

    # Paso 1 y extensión 1a: el Vendedor responsable (regla 1 de 8.11).
    vendedores, vendedor, invernaderos_del_vendedor = [], None, []
    if es_gerente:
        vendedores = _vendedores_con_invernaderos()
        elegido = _entero(datos.vendedor_id)
        encontrado = next(((v, i) for v, i in vendedores if v.pk == elegido), None)
        if encontrado:
            vendedor, invernaderos_del_vendedor = encontrado
        elif _texto(datos.vendedor_id):
            _agregar(errores, "vendedor", "Elegí un Vendedor activo con invernaderos activos.")
        elif estricto:
            _agregar(errores, "vendedor", "Elegí el Vendedor responsable de la venta.")
    else:
        vendedor = actor
        invernaderos_del_vendedor = list(
            Invernadero.objects.filter(vendedor_id=actor.pk, estado_invernadero=Invernadero.Estado.ACTIVO).order_by("pk")
        )

    # Pasos 2 a 4 y 3a: el cliente (solo activos).
    cliente = None
    if _texto(datos.cliente_id):
        cliente = Cliente.objects.filter(pk=_entero(datos.cliente_id)).first() if _entero(datos.cliente_id) else None
        if cliente is None:
            _agregar(errores, "cliente", "Elegí un cliente de la lista.")
        elif not cliente.activo:
            _agregar(errores, "cliente", "El cliente está dado de baja: reactivalo para venderle.")
    elif estricto:
        _agregar(errores, "cliente", "Elegí el cliente.")
    cliente_valido = cliente is not None and cliente.activo

    # Pasos 5 y 6 y extensión 6a: fecha pactada y modalidad.
    fecha = None
    if _texto(datos.fecha_pactada):
        fecha = _fecha(datos.fecha_pactada)
        if fecha is None:
            _agregar(errores, "fecha_pactada", "Ingresá una fecha válida (dd/mm/aaaa).")
        elif fecha < hoy:
            _agregar(errores, "fecha_pactada", "La fecha pactada no puede ser anterior a hoy.")
            fecha = None
    elif estricto:
        _agregar(errores, "fecha_pactada", "Ingresá la fecha pactada.")
    modalidad = _texto(datos.modalidad)
    if modalidad not in Modalidad.values:
        if modalidad or estricto:
            _agregar(errores, "modalidad", "Elegí la modalidad de entrega.")
        modalidad = ""

    # Pasos 7 y 5a: la dirección de envío (activa y del cliente) o el invernadero de retiro (activo y del Vendedor).
    direcciones, direccion, retiros, retiro = [], None, [], None
    if modalidad == Modalidad.ENVIO and cliente_valido:
        direcciones = api_clientes.direcciones_activas(cliente)
        direccion = next((d for d in direcciones if d.pk == _entero(datos.direccion_id)), None)
        if direccion is None and estricto:
            _agregar(errores, "direccion", "Elegí la dirección de envío." if not _texto(datos.direccion_id) else "Esa no es una dirección activa del cliente.")
    elif modalidad == Modalidad.ENVIO and estricto:
        _agregar(errores, "direccion", "Elegí la dirección de envío.")
    if modalidad == Modalidad.RETIRO:
        retiros = invernaderos_del_vendedor
        retiro = next((i for i in retiros if i.pk == _entero(datos.invernadero_id)), None)
        if retiro is None and len(retiros) == 1 and (not estricto or not _texto(datos.invernadero_id)):
            retiro = retiros[0]  # `retiroFld` del prototipo: con un solo invernadero queda elegido (al registrar, solo si no se mandó otro)
        if retiro is None and estricto:
            _agregar(
                errores,
                "invernadero",
                "Elegí el invernadero de retiro." if not _texto(datos.invernadero_id) else "Ese invernadero no es uno de los activos del Vendedor.",
            )
    destino_listo = (modalidad == Modalidad.ENVIO and direccion is not None) or (modalidad == Modalidad.RETIRO and retiro is not None)
    entrega_habilitada = cliente_valido
    variedades_habilitadas = bool(fecha and destino_listo and vendedor is not None)
    habilitados = []
    if variedades_habilitadas:
        habilitados = invernaderos_del_vendedor if modalidad == Modalidad.ENVIO else [retiro]

    # Pasos 8 a 10: lo disponible de cada variedad y los renglones.
    activas = list(Variedad.objects.filter(estado_variedad=Variedad.Estado.ACTIVO).select_related("cultivo").order_by("cultivo__nombre_cultivo", "nombre_variedad"))
    por_id = {v.pk: v for v in activas}
    disponibles = (
        stock_maduro.disponible([v.pk for v in activas], [i.pk for i in habilitados], fecha, "compra_venta")
        if variedades_habilitadas
        else {}
    )
    # Paso 9 de COM-REG-CVT: en pantalla (no estricto) los renglones en blanco se conservan, sin errores, para que «Agregar variedad» y el
    # renglón inicial se vean; al resumir o registrar (estricto) se ignoran, y sin ninguno cargado vale «Cargá al menos una variedad.»
    renglones = [r for r in datos.renglones if estricto is False or not r.vacio]
    propuestos = _ultimos_precios({_entero(r.variedad_id) for r in renglones if _entero(r.variedad_id)} | {v.pk for v in activas if disponibles.get(v.pk) and disponibles[v.pk].total})
    filas, vistas = [], set()
    for renglon in renglones:
        fila = FilaDeRenglon(renglon)
        if renglon.vacio:  # solo llega acá en pantalla: se muestra para completar, sin validar nada
            filas.append(fila)
            continue
        variedad_id = _entero(renglon.variedad_id)
        variedad = por_id.get(variedad_id)
        if not _texto(renglon.variedad_id):
            fila.errores["variedad"] = "Elegí la variedad."
        elif variedad is None:
            fila.errores["variedad"] = "Esa variedad no está disponible."
        elif variedad_id in vistas:
            fila.errores["variedad"] = "La venta ya tiene esa variedad: corregí ese renglón."
        else:
            vistas.add(variedad_id)
            fila.variedad = variedad
            fila.precio_propuesto = propuestos.get(variedad_id)
            if variedades_habilitadas:
                fila.disponible = disponibles[variedad_id].total
        if _texto(renglon.cantidad) or estricto:
            cantidad = _entero(renglon.cantidad)
            if cantidad is None or cantidad < 1:
                fila.errores["cantidad"] = "Ingresá un número entero de plantas."
            elif fila.disponible is not None and cantidad > fila.disponible:
                fila.errores["cantidad"] = f"Hay {fila.disponible} plantas disponibles para esa fecha."
            else:
                fila.cantidad = cantidad
        if _texto(renglon.precio) or estricto:
            fila.precio = _precio(renglon.precio)
            if fila.precio is None:
                fila.errores["precio"] = "Ingresá un precio mayor que cero, con hasta dos decimales (por ejemplo 1500,50)."
        filas.append(fila)
    for fila in filas:
        for campo, mensaje in fila.errores.items():
            _agregar(errores, f"renglon-{fila.renglon.indice}-{campo}", mensaje)
    if estricto and not filas:
        _agregar(errores, NO_CAMPO, "Cargá al menos una variedad.")

    ofrecidas = [
        (v, disponibles[v.pk]) for v in activas if v.pk in disponibles and (disponibles[v.pk].total > 0 or v.pk in vistas)
    ]
    return FormularioDeCompraVenta(
        datos=datos,
        es_gerente=es_gerente,
        vendedor=vendedor,
        vendedores=vendedores,
        cliente=cliente if cliente_valido else None,
        direcciones=direcciones,
        direccion=direccion,
        invernaderos_de_retiro=retiros,
        invernadero_de_retiro=retiro,
        habilitados=habilitados,
        fecha=fecha,
        variedades_ofrecidas=ofrecidas,
        filas=filas,
        monto_estimado=sum((f.subtotal for f in filas if f.subtotal is not None), Decimal("0.00")),
        errores=errores,
        entrega_habilitada=entrega_habilitada,
        variedades_habilitadas=variedades_habilitadas,
        sin_stock=bool(variedades_habilitadas and not any(d.total for d in disponibles.values())),
        cliente_sin_correo=bool(cliente_valido and not cliente.email_cliente),
    )


def datos_del_formulario(actor, datos):
    """Lo que muestra la pantalla en cada cambio (pasos 2 a 10, extensiones 1a, 5a, 8a, 9a, 10a a 10c y 9-10a): el Vendedor, las direcciones o
    los invernaderos de retiro, las variedades con su disponible y su precio propuesto, los subtotales, el monto estimado y los errores por
    campo. **No escribe ni bloquea**; consultas fijas, sin consultas por renglón (requisito «no más de 1 segundo»)."""
    return _analizar(actor, datos, estricto=False)


def _lanzar(errores):
    """Un ``ValidationError`` con un error por campo: ``{campo: [mensaje]}`` → ``{campo: [ValidationError]}`` con su código."""
    codigos = {
        "vendedor": "vendedor_invalido",
        "cliente": "cliente_inactivo",
        "fecha_pactada": "fecha_invalida",
        "modalidad": "modalidad_invalida",
        "direccion": "direccion_no_valida",
        "invernadero": "invernadero_no_habilitado",
    }
    resultado = {}
    for campo, mensajes in errores.items():
        for mensaje in mensajes:
            resultado.setdefault(campo, []).append(ValidationError(mensaje, code=_codigo(campo, mensaje, codigos)))
    raise ValidationError(resultado)


def _codigo(campo, mensaje, codigos):
    """El código de un error (docs de COM-02, «Códigos de error»), a partir de su campo y su mensaje."""
    if campo == NO_CAMPO:
        return "sin_renglones"
    coincidencia = re.fullmatch(r"renglon-\d+-(variedad|cantidad|precio)", campo)
    if coincidencia:
        if coincidencia.group(1) == "variedad":
            return "variedad_repetida" if "ya tiene esa variedad" in mensaje else ("variedad_obligatoria" if "Elegí" in mensaje else "variedad_inactiva")
        if coincidencia.group(1) == "cantidad":
            return "supera_disponible" if mensaje.startswith("Hay ") else "cantidad_invalida"
        return "precio_invalido"
    if campo == "fecha_pactada":
        return "fecha_pasada" if "anterior a hoy" in mensaje else ("fecha_obligatoria" if "Ingresá la fecha" in mensaje else "fecha_invalida")
    if campo == "cliente":
        return "cliente_inactivo" if "baja" in mensaje else "cliente_obligatorio"
    if campo == "vendedor":
        return "vendedor_obligatorio" if mensaje.startswith("Elegí el Vendedor") else "vendedor_invalido"
    if campo == "direccion":
        return "direccion_obligatoria" if mensaje.startswith("Elegí") else "direccion_no_valida"
    if campo == "invernadero":
        return "invernadero_obligatorio" if mensaje.startswith("Elegí") else "invernadero_no_habilitado"
    return codigos.get(campo, "invalido")


# ---- resumen (paso 12) ----


@dataclass
class ResumenDeCompraVenta:
    """El resumen del paso 12: cliente, Vendedor responsable, modalidad con su destino, fecha, renglones y monto estimado."""

    formulario: FormularioDeCompraVenta
    destino: str

    @property
    def filas(self):
        return self.formulario.filas


def resumen(actor, datos):
    """Paso 12: valida todo como al registrar (``ValidationError`` por campo si algo falta o ya no alcanza) y arma el resumen. No escribe."""
    formulario = _analizar(actor, datos, estricto=True)
    if formulario.errores:
        _lanzar(formulario.errores)
    if formulario.direccion:
        destino = f"{formulario.direccion.texto()}, {formulario.direccion.localidad.nombre_localidad}"
    else:
        retiro = formulario.invernadero_de_retiro
        hija = api_clientes.direccion_hija(retiro.direccion_id)
        destino = f"{retiro.nombre_invernadero} ({hija.texto()})" if hija else retiro.nombre_invernadero
    return ResumenDeCompraVenta(formulario, destino)


# ---- registro (pasos 13 a 17) ----


def _error_de_campo(campo, mensaje, codigo):
    """Un ``ValidationError`` de un solo campo."""
    return ValidationError({campo: [ValidationError(mensaje, code=codigo)]})


def registrar_compra_venta(actor, datos):
    """COM-REG-CVT: registra la compra-venta con sus detalles, reservas y cosechas, y la devuelve (con ``cosechas_programadas``).

    - Precondición a: Vendedor o Gerente activo (``PermissionDenied``). Reglas 1 a 5 y extensiones 1a, 3a, 5a, 6a, 9a, 10a a 10c, 11a:
      ``ValidationError`` por campo (``cliente_obligatorio``, ``fecha_pasada``, ``direccion_no_valida``, ``supera_disponible``,
      ``variedad_repetida``, ``precio_invalido``, ``sin_renglones``…).
    - Pasos 14 y 15 en UNA transacción, con los bloqueos del encabezado: cuentas, invernaderos, cliente (vuelve a verificar que siga activo y,
      en un envío, que la dirección siga activa y sea suya), variedades, lotes y partidas. Una venta en una compra-venta con retiro exige que
      el invernadero siga siendo del Vendedor (``invernadero_no_habilitado``). Por cada detalle, ``asignar``; si alguno queda sin cubrir,
      ``stock_insuficiente`` con el nuevo máximo de cada uno y se revierte todo (extensión 14a).
    - Postcondiciones a a f: la venta «abierta», sus detalles «abiertos», una reserva por invernadero y su cosecha (``stock_maduro``).
    - Postcondiciones i y j y D-36: UN registro ``registro_compra_venta`` (el Gerente queda como quien la cargó; el Vendedor responsable va
      en ``datos``).
    - Paso 16, FUERA de la transacción: el comprobante (``comprobantes.enviar_comprobante``). La venta queda «para imprimir» (sin correo),
      «enviado» o «pendiente de envío» (falla: el Vendedor responsable recibe un aviso si registró el Gerente).
    - Postcondición g (planificar la entrega si todo salió de cámara): se completa en COM-05.
    """
    previo = _analizar(actor, datos, estricto=True)
    if previo.errores:
        _lanzar(previo.errores)
    vendedor_id = previo.vendedor.pk
    retiro = previo.invernadero_de_retiro is not None
    filas = sorted(previo.filas, key=lambda f: f.variedad.pk)
    hoy = stock.hoy()
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
                actual = None  # se dio de baja mientras se cargaba la venta
            if actual is None or actual.vendedor_id != vendedor_id:
                if retiro:
                    raise _error_de_campo("invernadero", "Ese invernadero ya no es uno de los activos del Vendedor.", "invernadero_no_habilitado")
                continue
            bloqueados.append(actual)
        if not retiro:
            ahora = set(
                Invernadero.objects.filter(vendedor_id=vendedor_id, estado_invernadero=Invernadero.Estado.ACTIVO).values_list("pk", flat=True)
            )
            if not ahora <= {i.pk for i in bloqueados}:
                raise ValidationError(
                    "Mientras registrabas, cambiaron los invernaderos del Vendedor. Volvé a intentarlo.", code="cambio_simultaneo"
                )

        cliente = Cliente.objects.select_for_update(no_key=True).filter(pk=previo.cliente.pk).first()
        if cliente is None or not cliente.activo:
            raise _error_de_campo("cliente", "El cliente se dio de baja mientras cargabas la venta.", "cliente_inactivo")
        if previo.direccion is not None and not DireccionCliente.objects.filter(
            cliente=cliente, direccion_id=previo.direccion.pk, direccion__estado_direccion=Direccion.Estado.ACTIVO
        ).exists():
            raise _error_de_campo("direccion", "La dirección ya no está activa: elegí otra.", "direccion_no_valida")

        for fila in filas:
            try:
                bloquear_variedad(fila.variedad.pk)
            except ValidationError as error:
                raise _error_de_campo(f"renglon-{fila.renglon.indice}-variedad", "Esa variedad ya no está disponible.", "variedad_inactiva") from error
        stock_maduro.bloquear_candidatos([f.variedad.pk for f in filas], [i.pk for i in bloqueados])

        venta = CompraVenta.objects.create(
            tipo_contrato=CompraVenta.Tipo.COMPRA_VENTA,
            numero=siguiente_numero(),
            fecha_realizacion=hoy,
            # Decisión de aplicación: nace «para imprimir» si el cliente no tiene correo y «pendiente de envío» si lo tiene; el envío lo pasa a
            # «enviado». Así una caída entre confirmar y enviar deja el estado correcto.
            estado_comprobante=(
                CompraVenta.EstadoDelComprobante.PENDIENTE_ENVIO if cliente.email_cliente else CompraVenta.EstadoDelComprobante.PARA_IMPRIMIR
            ),
            cliente=cliente,
            vendedor_id=vendedor_id,
            estado_venta=CompraVenta.Estado.ABIERTA,
            fecha_pactada_venta=previo.fecha,
            modalidad_entrega=Modalidad.RETIRO if retiro else Modalidad.ENVIO,
            direccion_envio_id=None if retiro else previo.direccion.pk,
            invernadero_retiro_id=previo.invernadero_de_retiro.pk if retiro else None,
        )
        detalles = [
            DetalleVenta.objects.create(
                compra_venta=venta, variedad=f.variedad, cant_solicitada_venta=f.cantidad, precio_unitario_de_venta=f.precio
            )
            for f in filas
        ]
        reservas, cosechas, faltantes = [], [], {}
        for fila, detalle in zip(filas, detalles):
            resultado = stock_maduro.asignar(actor, detalle, fila.cantidad, previo.fecha, "compra_venta")
            reservas.extend(resultado.reservas)
            cosechas.extend(resultado.cosechas)
            if resultado.sin_cubrir:
                faltantes[fila.renglon.indice] = resultado.cubierta
        if faltantes:
            errores = {
                f"renglon-{indice}-cantidad": [ValidationError(f"Hay {maximo} plantas disponibles para esa fecha.", code="stock_insuficiente")]
                for indice, maximo in faltantes.items()
            }
            errores[NO_CAMPO] = [ValidationError("El stock cambió mientras cargabas la venta.", code="stock_insuficiente")]
            raise ValidationError(errores)  # revierte todo (extensión 14a; garantía mínima 1)

        lineas = list(DetalleReserva.objects.filter(reserva__in=reservas).select_related("lote", "partida").order_by("pk"))
        monto = sum((d.cant_solicitada_venta * d.precio_unitario_de_venta for d in detalles), Decimal("0.00"))
        datos_de_auditoria = {
            "compra_venta": referencia(venta),
            "vendedor": referencia(responsable),
            "cliente": referencia(cliente),
            "fecha_realizacion": f"{hoy:%d/%m/%Y}",
            "fecha_pactada_venta": f"{venta.fecha_pactada_venta:%d/%m/%Y}",
            "modalidad_entrega": venta.modalidad_entrega,
            "estado_venta": venta.estado_venta,
            "monto_estimado": f"{monto:.2f}",
            "detalles": [f"{d.variedad}: {d.cant_solicitada_venta} × {d.precio_unitario_de_venta}" for d in detalles],
            "reservas": [f"{r} · {r.invernadero} · {r.get_estado_reserva_display().lower()}" for r in reservas],
            "lineas": [
                f"{r} → {(l.lote or l.partida).codigo}: {l.cantidad_reservada}" for l in lineas for r in [next(x for x in reservas if x.pk == l.reserva_id)]
            ],
            "cosechas": [c.codigo for c in cosechas],
        }
        if retiro:
            datos_de_auditoria["invernadero_retiro"] = referencia(previo.invernadero_de_retiro)
        else:
            datos_de_auditoria["direccion_envio"] = {"id": previo.direccion.pk, "texto": previo.direccion.texto()}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REGISTRO_COMPRA_VENTA,
            afectados=[venta, *detalles, *reservas, *[l for l in lineas], *cosechas],
            detalle={"datos": datos_de_auditoria},
        )

    # Paso 16 y extensiones 16a y 16b: FUERA de la transacción (D-14, D-54).
    venta.estado_comprobante = comprobantes.enviar_comprobante(venta)
    if venta.estado_comprobante == CompraVenta.EstadoDelComprobante.PENDIENTE_ENVIO:
        comprobantes.avisar_comprobante_pendiente(actor, venta)
    venta.cosechas_programadas = len(cosechas)
    return venta


def datos_del_comprobante(venta):
    """Lo que dicen el comprobante por correo y la página imprimible: la venta, el cliente, el destino, los renglones y el monto estimado."""
    venta = CompraVenta.objects.select_related("cliente", "vendedor", "invernadero_retiro").get(pk=venta.pk)
    detalles = list(venta.detalles.select_related("variedad__cultivo").order_by("variedad_id"))
    if venta.modalidad_entrega == Modalidad.ENVIO:
        hija = api_clientes.direccion_hija(venta.direccion_envio_id)
        destino = f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else ""
    else:
        hija = api_clientes.direccion_hija(venta.invernadero_retiro.direccion_id)
        destino = f"{venta.invernadero_retiro.nombre_invernadero} ({hija.texto()})" if hija else venta.invernadero_retiro.nombre_invernadero
    filas = [
        SimpleNamespace(
            variedad=d.variedad, cantidad=d.cant_solicitada_venta, precio=d.precio_unitario_de_venta,
            subtotal=(Decimal(d.cant_solicitada_venta) * d.precio_unitario_de_venta).quantize(CENTAVOS),
        )
        for d in detalles
    ]
    return {
        "venta": venta,
        "cliente": venta.cliente,
        "destino": destino,
        "filas": filas,
        "monto": sum((f.subtotal for f in filas), Decimal("0.00")),
    }


# ---- consulta (COM-CNS-CVT) ----


@dataclass
class FiltrosDeCompraVentas:
    """Regla 2 de COM-CNS-CVT: cliente, estado, rango de fechas (pactada o de realización) y, solo para el Gerente, Vendedor."""

    cliente_id: str = ""
    cliente_texto: str = ""  # buscador del cliente: CUIT, nombre, apellido o razón social (desde 2 caracteres)
    estado: str = ""
    fecha_de: str = "pactada"
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
            fecha_de=datos.get("fecha_de", "pactada"),
            desde=datos.get("desde", ""),
            hasta=datos.get("hasta", ""),
            vendedor_id=datos.get("vendedor", ""),
        )


def buscar_compra_ventas(actor, filtros, pagina=1):
    """COM-CNS-CVT, reglas 1 a 3: la ``Page`` de compra-ventas del alcance de ``actor`` (el Vendedor, las suyas; el Gerente, todas) con sus
    filtros, por fecha de realización y número descendentes (50 por página). Cada una trae su ``monto`` calculado en la base («estimado» si no
    está concretada ni cancelada, ``monto_es_final``) con el cliente y el Vendedor ya cargados: sin consultas por fila. No audita (SEG-14)."""
    _exigir_actor(actor)
    lista = CompraVenta.objects.en_alcance_de(actor).select_related("cliente", "vendedor", "invernadero_retiro").con_monto()
    if _entero(filtros.cliente_id):
        lista = lista.filter(cliente_id=_entero(filtros.cliente_id))
    if len(_texto(filtros.cliente_texto)) >= 2:
        coinciden = api_clientes.buscar_clientes(actor, filtros.cliente_texto).object_list
        lista = lista.filter(cliente_id__in=[c.pk for c in coinciden])
    if filtros.estado in CompraVenta.Estado.values:
        lista = lista.filter(estado_venta=filtros.estado)
    if rol_de(actor) == GERENTE and _entero(filtros.vendedor_id):
        lista = lista.filter(vendedor_id=_entero(filtros.vendedor_id))
    campo = "fecha_realizacion" if filtros.fecha_de == "realizacion" else "fecha_pactada_venta"
    if desde := _fecha(filtros.desde):
        lista = lista.filter(**{f"{campo}__gte": desde})
    if hasta := _fecha(filtros.hasta):
        lista = lista.filter(**{f"{campo}__lte": hasta})
    return Paginator(lista.order_by("-fecha_realizacion", "-numero"), POR_PAGINA).get_page(pagina)


@dataclass
class FichaDeCompraVenta:
    """La ficha de COM-CNS-CVT, regla 4 (en lo que existe hoy): la venta, sus renglones con su subtotal, el monto y a qué destino va."""

    venta: object
    detalles: list
    monto: Decimal
    destino: str
    acciones: frozenset
    pendiente: object = None  # COM-04c: lo que espera una venta «pendiente de decisión del cliente» (`faltantes.estado_del_faltante`)


def ficha_de_compra_venta(actor, venta_id):
    """COM-CNS-CVT, regla 4: cliente, Vendedor, modalidad con su destino, las tres fechas, los detalles (variedad, solicitada, entregada,
    precio, subtotal y estado) y el estado del comprobante. 404 si no existe; ``PermissionDenied`` (403 con mensaje, SEG-13) si no es del
    alcance de ``actor``. Las entregas, el cobro, la cancelación y el vencimiento del enlace los suman COM-04, COM-05, COM-06 y COM-08."""
    _exigir_actor(actor)
    venta = get_object_or_404(CompraVenta.objects.select_related("cliente", "vendedor", "invernadero_retiro"), pk=venta_id)
    if not CompraVenta.objects.en_alcance_de(actor).filter(pk=venta.pk).exists():
        raise PermissionDenied(MENSAJE_SIN_ACCESO)
    detalles = list(venta.detalles.select_related("variedad__cultivo").order_by("variedad_id"))
    filas = []
    for d in detalles:
        if d.estado_detalle_venta == DetalleVenta.Estado.CONFIRMADO:
            subtotal = Decimal(d.cant_entregada_venta or 0) * d.precio_unitario_de_venta
        elif d.estado_detalle_venta in (DetalleVenta.Estado.ABIERTO, DetalleVenta.Estado.PENDIENTE_DECISION):
            subtotal = Decimal(d.cant_solicitada_venta) * d.precio_unitario_de_venta
        else:
            subtotal = Decimal(0)
        filas.append(SimpleNamespace(detalle=d, subtotal=subtotal.quantize(CENTAVOS)))
    if venta.modalidad_entrega == Modalidad.ENVIO:
        hija = api_clientes.direccion_hija(venta.direccion_envio_id)
        destino = f"{hija.texto()}, {hija.localidad.nombre_localidad}" if hija else ""
    else:
        hija = api_clientes.direccion_hija(venta.invernadero_retiro.direccion_id)
        destino = f"{venta.invernadero_retiro.nombre_invernadero} ({hija.texto()})" if hija else venta.invernadero_retiro.nombre_invernadero
    acciones = {"ver_cliente"}
    if venta.estado_comprobante == CompraVenta.EstadoDelComprobante.PENDIENTE_ENVIO and venta.cliente.email_cliente:
        acciones.add("reenviar_comprobante")
    from comercial.servicios import faltantes  # `faltantes` importa de `cosechas`, que importa de este módulo: se importa acá para no cruzarlos

    return FichaDeCompraVenta(
        venta, filas, sum((f.subtotal for f in filas), Decimal("0.00")), destino, frozenset(acciones), faltantes.estado_del_faltante(venta, actor)
    )
