# Servicios de variedades (INV-03, D-49): la lectura, el bloqueo, la advertencia de rangos y el umbral efectivo (paso 3) y el alta (paso 4).
# La modificación, la reactivación y la baja se suman en los pasos 5 y 6. Contrato: docs/api/variedades.md. Las tablas
# `Variedad`, `Ciclo` y `EtapaProductiva` son de `maestros`; `Semilla`, de `inventario`. Lo de `produccion` (lotes, órdenes, variedades
# presentes) llega por los puntos de `inventario/extensiones.py`: sin registrantes, todo da su resultado neutro.

import re
from collections import defaultdict, namedtuple
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Value
from django.db.models.functions import Lower
from django.http import Http404
from django.shortcuts import get_object_or_404

from core import notificaciones
from core.models import RegistroAuditoria, Usuario, referencia, rol_de
from inventario import extensiones
from inventario.models import InsumoInvernadero, Semilla
from inventario.servicios import alertas_de_stock, ciclos, semillas
from inventario.servicios import stock as servicio_de_stock
from inventario.servicios.insumos_invernadero import _datos_de_alertas
from inventario.servicios.insumos import _nombre_del_agronomo
from maestros.models import Ciclo, Cultivo, EtapaProductiva, Invernadero, TipoEtapa, Variedad
from maestros.servicios.invernaderos import _actor_sigue_activo, _error_general, _tiene_contenido
from maestros.servicios.sectores import FaltaConfirmarAdvertencia

# ---- tipos de resultado (docs/api/variedades.md) ----

RangoAmbiental = namedtuple("RangoAmbiental", "minimo maximo")
Rangos = namedtuple("Rangos", "temp_ambiente humedad intensidad_luz fotoperiodo")
ResultadoGestion = namedtuple("ResultadoGestion", "puede quienes")
AccionesDeVariedad = namedtuple("AccionesDeVariedad", "modificar dar_de_baja reactivar motivo")
# Una incompatibilidad de rangos (regla 5 de PROD-MOD-VAR): el invernadero, la variable y la variedad con la que choca.
Incompatibilidad = namedtuple("Incompatibilidad", "invernadero_id variable variedad_id")
LimitesDelUmbral = namedtuple("LimitesDelUmbral", "minimo maximo variedad_minimo_id variedad_maximo_id")
UmbralEfectivo = namedtuple("UmbralEfectivo", "temp_ambiente humedad intensidad_luz fotoperiodo variedad_ids")
VariableIncompatible = namedtuple("VariableIncompatible", "variable variedad_limitante_id")

VARIABLES = Rangos._fields


# ---- lectura ----


def obtener_variedad(variedad_id):
    """La variedad con su cultivo (una consulta). ``Http404`` si no existe."""
    return get_object_or_404(Variedad.objects.select_related("cultivo"), pk=variedad_id)


def semilla_de(variedad_ids):
    """``{variedad_id: Semilla}``: la semilla de cada variedad (siempre existe: se crea con ella). Una consulta."""
    return {s.variedad_id: s for s in Semilla.objects.filter(variedad_id__in=list(variedad_ids))}


def rangos_de(variedad_ids):
    """``{variedad_id: Rangos}`` con ``Decimal``: lo que cruza el «umbral efectivo». Una consulta."""
    columnas = [f"{v}_{lado}" for v in VARIABLES for lado in ("min", "max")]
    resultado = {}
    for fila in Variedad.objects.filter(pk__in=list(variedad_ids)).values("pk", *columnas):
        resultado[fila["pk"]] = Rangos(*[RangoAmbiental(fila[f"{v}_min"], fila[f"{v}_max"]) for v in VARIABLES])
    return resultado


def uso_de_variedades(variedad_ids):
    """``{variedad_id: UsoDeVariedad}``: lo que informan los registrantes de `produccion` (neutro sin ellos)."""
    return extensiones.uso_de_variedades(variedad_ids)


def variedades_presentes(invernadero_ids):
    """``{invernadero_id: set[int]}``: variedades con lotes activos u órdenes de siembra a realizar (neutro sin registrantes)."""
    return extensiones.variedades_presentes(invernadero_ids)


def impedimentos_de_baja_de_variedad(variedad):
    """Los impedimentos de baja de los registrantes, juntos (regla 2 de PROD-BAJ-VAR)."""
    return extensiones.impedimentos_de_baja_de_variedad(variedad)


def invernaderos_que_usan(variedad_ids):
    """``{variedad_id: set[int]}``: ids de los invernaderos ACTIVOS que usan la variedad, esto es, con su semilla habilitada
    (``InsumoInvernadero`` activo) o con lotes activos de ella (regla 1 de PROD-MOD-VAR). Todo id pedido figura. Sin consultas por
    variedad: una por las existencias y una para verificar el estado de los invernaderos de los lotes."""
    from inventario.models import InsumoInvernadero

    ids = list(variedad_ids)
    usan = defaultdict(set, {i: set() for i in ids})
    habilitadas = InsumoInvernadero.objects.filter(
        insumo__semilla__variedad_id__in=ids,
        estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO,
        invernadero__estado_invernadero=Invernadero.Estado.ACTIVO,
    ).values_list("insumo__semilla__variedad_id", "invernadero_id")
    for variedad_id, invernadero_id in habilitadas:
        usan[variedad_id].add(invernadero_id)
    con_lotes = {i: uso.invernaderos_con_lotes_activos for i, uso in uso_de_variedades(ids).items()}
    de_lotes = set().union(*con_lotes.values()) if con_lotes else set()
    if de_lotes:
        activos = set(
            Invernadero.objects.filter(pk__in=de_lotes, estado_invernadero=Invernadero.Estado.ACTIVO).values_list("pk", flat=True)
        )
        for variedad_id, invernaderos in con_lotes.items():
            usan[variedad_id] |= set(invernaderos) & activos
    return {i: usan[i] for i in ids}


def _es_agronomo_activo(actor):
    return actor is not None and actor.is_active and rol_de(actor) == Usuario.Rol.AGRONOMO


def gestion_de(actor, variedades):
    """``{variedad_id: ResultadoGestion}`` para varias variedades a la vez (la tabla de la consulta, sin consultas por fila): las mismas
    reglas que ``puede_gestionar``, con una consulta para saber qué invernaderos usan cada una y otra para sus Agrónomos."""
    ids = [v.pk for v in variedades]
    usan = invernaderos_que_usan(ids)
    todos = set().union(*usan.values()) if usan else set()
    por_id = {g.pk: g for g in Invernadero.objects.filter(pk__in=todos).select_related("agronomo")} if todos else {}
    resultado = {}
    for variedad_id in ids:
        invernaderos = sorted(
            (por_id[i] for i in usan[variedad_id] if i in por_id),
            key=lambda g: (g.nombre_invernadero.lower(), g.pk),
        )
        puede = _es_agronomo_activo(actor) and (not invernaderos or any(g.agronomo_id == actor.pk for g in invernaderos))
        if puede:
            resultado[variedad_id] = ResultadoGestion(True, [])
        else:
            resultado[variedad_id] = ResultadoGestion(False, [f"{g.nombre_invernadero} ({_nombre_del_agronomo(g)})" for g in invernaderos])
    return resultado


def puede_gestionar(actor, variedad):
    """Regla 1 de PROD-MOD-VAR: ``ResultadoGestion(puede, quienes)``. Un Agrónomo activo gestiona la variedad si es el Agrónomo de algún
    invernadero que la usa; si ningún invernadero la usa, cualquier Agrónomo activo. Si no puede, ``quienes`` nombra los invernaderos
    que la usan y sus Agrónomos («Invernadero Norte (Ana Pérez)» o «Invernadero Sur (sin Agrónomo)»). Si todos los que la usan están sin
    Agrónomo, nadie la gestiona hasta que el Gerente asigne uno. Se llama también DESPUÉS de bloquear (no solo al abrir la pantalla)."""
    return gestion_de(actor, [variedad])[variedad.pk]


def _acciones(actor, variedad, gestion):
    """Las acciones de una variedad según ``gestion`` (el resultado de ``puede_gestionar`` de esa variedad)."""
    if not gestion.puede:
        motivo = f"Solo la usa {', '.join(gestion.quienes)}." if gestion.quienes and _es_agronomo_activo(actor) else ""
        return AccionesDeVariedad(False, False, False, motivo)
    if variedad.activa:
        return AccionesDeVariedad(True, True, False, "")
    if not variedad.cultivo.activo:
        return AccionesDeVariedad(False, False, False, f"Primero reactivá el cultivo {variedad.cultivo.nombre_cultivo}.")
    return AccionesDeVariedad(False, False, True, "")


def acciones_permitidas(actor, variedad):
    """Regla 4 de PROD-CNS-VAR: qué botones ofrece la consulta. Variedad activa y gestora: modificar y dar de baja; inactiva: solo
    reactivar, y solo si su cultivo está activo («Primero reactivá el cultivo X.»); sin permiso: todo deshabilitado con el motivo
    «Solo la usa …». Ningún botón lleva a un 403 (D-30)."""
    return _acciones(actor, variedad, puede_gestionar(actor, variedad))


def acciones_de(actor, variedades):
    """``{variedad_id: AccionesDeVariedad}`` de varias variedades (con su cultivo ya cargado) sin consultas por fila."""
    variedades = list(variedades)
    gestion = gestion_de(actor, variedades)
    return {v.pk: _acciones(actor, v, gestion[v.pk]) for v in variedades}


def variedades_activas(cultivo_id=None):
    """Las variedades activas de cultivos activos, con su ciclo y su cultivo en la misma consulta: lo que PRD-01 ofrece para sembrar."""
    variedades = Variedad.objects.filter(
        estado_variedad=Variedad.Estado.ACTIVO, cultivo__estado_cultivo="activo"
    ).select_related("cultivo", "ciclo")
    if cultivo_id is not None:
        variedades = variedades.filter(cultivo_id=cultivo_id)
    return variedades.order_by(Lower("cultivo__nombre_cultivo"), Lower("nombre_variedad"), "id")


# ---- bloqueo ----


def bloquear_variedad(variedad_id):
    """``FOR NO KEY UPDATE`` sobre la variedad, ya releída, SOLO si está activa (``ValidationError`` ``variedad_inactiva``). La llama
    quien crea un lote o una orden de la variedad, antes de crear, con el invernadero ya bloqueado (docs/patrones/stock.md, sección 5):
    la FK sola no alcanza, porque toma ``FOR KEY SHARE``, que no choca con el ``FOR NO KEY UPDATE`` de una baja. Hay que llamarla
    dentro de ``transaction.atomic()``."""
    variedad = Variedad.objects.select_for_update(no_key=True).filter(pk=variedad_id).first()
    if variedad is None:
        raise Http404("No existe esa variedad.")
    if not variedad.activa:
        raise ValidationError("La variedad está inactiva.", code="variedad_inactiva")
    return variedad


# ---- advertencia de rangos (regla 5 de PROD-MOD-VAR) ----


def _se_cruzan(uno, otro):
    """Dos rangos son compatibles si ``max(mínimos) <= min(máximos)``: tocarse en un extremo no es incompatibilidad."""
    return max(uno.minimo, otro.minimo) <= min(uno.maximo, otro.maximo)


def incompatibilidades_de_rangos(variedad, rangos_nuevos):
    """Las incompatibilidades que causaría darle a ``variedad`` los ``rangos_nuevos``: para cada invernadero donde tiene lotes activos
    se compara el rango NUEVO con el de cada OTRA variedad presente (lotes activos u órdenes de siembra a realizar). Se compara de a
    pares, que equivale a mirar la intersección y permite nombrar con quién choca. Ordenadas por invernadero, variable y variedad.
    Sin lotes activos o sin variedades presentes (hasta PRD-01), siempre vacía."""
    invernaderos = sorted(uso_de_variedades([variedad.pk])[variedad.pk].invernaderos_con_lotes_activos)
    if not invernaderos:
        return []
    presentes = variedades_presentes(invernaderos)
    otras = set().union(*presentes.values()) - {variedad.pk}
    if not otras:
        return []
    rangos_de_otras = rangos_de(otras)
    resultado = []
    for invernadero_id in invernaderos:
        for variable in VARIABLES:
            nuevo = getattr(rangos_nuevos, variable)
            for otra_id in sorted(presentes[invernadero_id] - {variedad.pk}):
                if not _se_cruzan(nuevo, getattr(rangos_de_otras[otra_id], variable)):
                    resultado.append(Incompatibilidad(invernadero_id, variable, otra_id))
    return resultado


# ---- umbral efectivo (docs/api/variedades.md, «Umbral efectivo») ----


def umbral_efectivo(invernadero_ids):
    """``{invernadero_id: UmbralEfectivo | None}``: la intersección de los rangos de las variedades presentes en cada invernadero.
    ``None`` si no tiene variedades presentes (todos, hasta PRD-01). Cada variable vale ``None`` si en ella los rangos no se
    superponen. ``minimo`` es el mayor de los mínimos y ``maximo`` el menor de los máximos, con la variedad que fija cada uno; en un
    empate, la de menor id. No se guarda: se calcula en cada llamada. Una consulta (``rangos_de``) para todos los invernaderos."""
    ids = list(invernadero_ids)
    presentes = variedades_presentes(ids)
    todas = set().union(*presentes.values()) if presentes else set()
    rangos = rangos_de(todas) if todas else {}
    resultado = {}
    for invernadero_id in ids:
        variedades = presentes.get(invernadero_id) or set()
        if not variedades:
            resultado[invernadero_id] = None
            continue
        limites = {}
        for variable in VARIABLES:
            minimo, variedad_minimo = max(
                ((getattr(rangos[v], variable).minimo, v) for v in variedades), key=lambda par: (par[0], -par[1])
            )
            maximo, variedad_maximo = min(
                ((getattr(rangos[v], variable).maximo, v) for v in variedades), key=lambda par: (par[0], par[1])
            )
            limites[variable] = None if minimo > maximo else LimitesDelUmbral(minimo, maximo, variedad_minimo, variedad_maximo)
        resultado[invernadero_id] = UmbralEfectivo(**limites, variedad_ids=frozenset(variedades))
    return resultado


def variables_incompatibles(umbral, rangos):
    """Las variables en las que una variedad con esos ``rangos`` dejaría vacío el ``umbral`` (regla de compatibilidad de PROD-PNF-SMB).
    Función pura, sin consultas. Con ``umbral`` en ``None`` (invernadero sin variedades), vacía. Una variable del umbral que ya es
    ``None`` es incompatible, con limitante ``None``; si no, la limitante es la variedad del máximo si el mínimo de ``rangos`` lo
    supera, o la del mínimo si su máximo queda por debajo."""
    if umbral is None:
        return []
    resultado = []
    for variable in VARIABLES:
        limites, rango = getattr(umbral, variable), getattr(rangos, variable)
        if limites is None:
            resultado.append(VariableIncompatible(variable, None))
        elif rango.minimo > limites.maximo:
            resultado.append(VariableIncompatible(variable, limites.variedad_maximo_id))
        elif rango.maximo < limites.minimo:
            resultado.append(VariableIncompatible(variable, limites.variedad_minimo_id))
    return resultado


# ---- alta (PROD-ALT-VAR) ----

LARGO_DEL_NOMBRE = Variedad._meta.get_field("nombre_variedad").max_length
RESTRICCION_NOMBRE_UNICO = "variedad_nombre_unico_por_cultivo"
MAXIMO_DE_DIGITOS_ENTEROS = 5  # DecimalField(max_digits=7, decimal_places=2)
_ENTERO = re.compile(r"^\d+$", re.ASCII)
_DOS_DECIMALES = Decimal("0.01")

# (variable, género del rótulo, tope mínimo, tope máximo). Topes aprobados el 19/11/2026 (D-49): humedad 0 a 100 y fotoperíodo 0 a 24.
RANGOS = (
    ("temp_ambiente", "f", None, None),
    ("humedad", "f", Decimal(0), Decimal(100)),
    ("intensidad_luz", "f", None, None),
    ("fotoperiodo", "m", Decimal(0), Decimal(24)),
)
COLUMNAS_DE_RANGO = [f"{variable}_{lado}" for variable, *_ in RANGOS for lado in ("min", "max")]


@dataclass(frozen=True)
class DatosDeVariedad:
    """Lo que escribe la persona en el formulario de una variedad (alta y modificación), SIN normalizar: textos o números crudos que el
    servicio valida. ``etapas`` son pares ``(codigo_de_tipo_de_etapa, dias)``; los rangos aceptan coma o punto decimal."""

    nombre: str = ""
    perfil_familia: str = ""
    etapas: tuple = ()
    temp_ambiente_min: str = ""
    temp_ambiente_max: str = ""
    humedad_min: str = ""
    humedad_max: str = ""
    intensidad_luz_min: str = ""
    intensidad_luz_max: str = ""
    fotoperiodo_min: str = ""
    fotoperiodo_max: str = ""
    duracion_post_cosecha: str = ""
    peso_promedio_planta: str = ""


# Datos ya validados y normalizados: ``etapas`` en el orden del catálogo, como ``(TipoEtapa, dias)``.
DatosValidos = namedtuple("DatosValidos", "nombre perfil_familia etapas rangos duracion_post_cosecha peso_promedio_planta")
# Lo que muestra el resumen antes de crear (regla 8 de PROD-ALT-VAR); ``etapas`` son ``(codigo, nombre, dias)``.
ResumenDeAlta = namedtuple(
    "ResumenDeAlta",
    "cultivo nombre perfil_familia etapas duracion_del_ciclo dias_hasta_maduracion nombre_semilla rangos "
    "duracion_post_cosecha peso_promedio_planta",
)


def _agregar(errores, campo, mensaje, codigo):
    """Anota un error de campo (el primero de cada campo manda)."""
    errores.setdefault(campo, [ValidationError(mensaje, code=codigo)])


def _texto(valor):
    return "" if valor is None else str(valor).strip()


def _validar_nombre(datos, errores):
    """Regla 2 de PROD-ALT-VAR (parte sin base): obligatorio, con contenido y de hasta 50 caracteres. Devuelve el nombre recortado."""
    nombre = _texto(datos.nombre)
    if not nombre:
        _agregar(errores, "nombre", "Ingresá el nombre de la variedad.", "obligatorio")
    elif not _tiene_contenido(nombre):
        _agregar(errores, "nombre", "Ingresá un texto con al menos una letra o un número.", "sin_contenido")
    elif len(nombre) > LARGO_DEL_NOMBRE:
        _agregar(errores, "nombre", f"Usá como máximo {LARGO_DEL_NOMBRE} caracteres.", "demasiado_largo")
    return nombre


def _validar_etapas(etapas, perfil, perfil_valido, errores, campo_no_permitida="etapas"):
    """Reglas 3 a 5 de PROD-ALT-VAR: tipos del catálogo, sin repetir, permitidos por el perfil, con Germinación y Maduración, cada una con
    una duración entera mayor que cero. Devuelve ``[(TipoEtapa, dias)]`` en el orden del catálogo (el servicio no confía en la pantalla).
    Una etapa no permitida se informa en ``campo_no_permitida``: ``etapas``, o ``perfil_familia`` cuando es el CAMBIO de perfil el que la
    deja sin permiso (variedades.md, «Perfil y etapas permitidas»)."""
    tipos = {tipo.codigo: tipo for tipo in TipoEtapa.objects.all()}
    elegidas = {}
    for codigo, dias in etapas:
        if codigo not in tipos:
            _agregar(errores, "etapas", f"«{codigo}» no es un tipo de etapa.", "etapa_invalida")
        elif codigo in elegidas:
            _agregar(errores, "etapas", f"{tipos[codigo].nombre_etapa} está repetida.", "etapa_repetida")
        else:
            elegidas[codigo] = dias
    for codigo in elegidas:
        if perfil_valido and perfil not in tipos[codigo].perfiles_permitidos:
            _agregar(errores, campo_no_permitida, f"{tipos[codigo].nombre_etapa} no se ofrece para ese perfil familiar.", "etapa_no_permitida")
    if "germinacion" not in elegidas or "maduracion" not in elegidas:
        _agregar(errores, "etapas", "Germinación y Maduración son obligatorias.", "etapa_obligatoria")
    validas = []
    for codigo, tipo in sorted(tipos.items(), key=lambda par: par[1].puesto_global):
        if codigo not in elegidas:
            continue
        texto = _texto(elegidas[codigo])
        if not texto:
            _agregar(errores, f"duracion_{codigo}", "Ingresá los días.", "obligatorio")
        elif not _ENTERO.match(texto) or int(texto) < 1:
            _agregar(errores, f"duracion_{codigo}", "Ingresá un entero mayor que 0.", "entero_mayor_que_cero")
        else:
            validas.append((tipo, int(texto)))
    return validas


def _numero(texto):
    """``Decimal`` de 2 decimales de un texto con coma o punto; ``None`` si no es un número (o no entra en la columna) y el texto
    ``"demasiados"`` si trae más de 2 decimales."""
    try:
        valor = Decimal(texto.replace(",", "."))
    except InvalidOperation:
        return None
    if not valor.is_finite() or abs(valor) >= 10**MAXIMO_DE_DIGITOS_ENTEROS:
        return None
    if valor != valor.quantize(_DOS_DECIMALES):
        return "demasiados"
    return valor.quantize(_DOS_DECIMALES)


def _validar_rangos(datos, errores):
    """Regla 6 de PROD-ALT-VAR y topes de D-49: mínimo y máximo obligatorios, numéricos, con hasta 2 decimales; humedad de 0 a 100 y
    fotoperíodo de 0 a 24; el mínimo no supera al máximo. Devuelve ``{columna: Decimal}`` de lo que pasó."""
    valores = {}
    for variable, genero, tope_minimo, tope_maximo in RANGOS:
        articulo = "el" if genero == "m" else "la"
        palabras = {"min": "mínimo" if genero == "m" else "mínima", "max": "máximo" if genero == "m" else "máxima"}
        for lado, palabra in palabras.items():
            campo = f"{variable}_{lado}"
            texto = _texto(getattr(datos, campo))
            if not texto:
                _agregar(errores, campo, f"Ingresá {articulo} {palabra}.", "obligatorio")
                continue
            valor = _numero(texto)
            if valor is None:
                _agregar(errores, campo, "Ingresá un número válido.", "numero_invalido")
            elif valor == "demasiados":
                _agregar(errores, campo, "Ingresá hasta 2 decimales.", "demasiados_decimales")
            elif tope_minimo is not None and not tope_minimo <= valor <= tope_maximo:
                _agregar(errores, campo, f"Ingresá un valor entre {tope_minimo} y {tope_maximo}.", "fuera_de_rango")
            else:
                valores[campo] = valor
        minimo, maximo = valores.get(f"{variable}_min"), valores.get(f"{variable}_max")
        if minimo is not None and maximo is not None and minimo > maximo:
            _agregar(
                errores,
                f"{variable}_max",
                f"{articulo.capitalize()} {palabras['max']} no puede ser menor que {articulo} {palabras['min']}.",
                "minimo_mayor_que_maximo",
            )
    return valores


def _validar_postcosecha_y_peso(datos, errores):
    """Regla 7 de PROD-ALT-VAR: postcosecha entera de 1 a 60 días; peso entero de gramos mayor que cero. Devuelve ``(postcosecha, peso)``."""
    postcosecha = peso = None
    texto = _texto(datos.duracion_post_cosecha)
    if not texto:
        _agregar(errores, "duracion_post_cosecha", "Ingresá los días de postcosecha.", "obligatorio")
    elif not _ENTERO.match(texto) or not 1 <= int(texto) <= 60:
        _agregar(errores, "duracion_post_cosecha", "Ingresá un entero entre 1 y 60.", "entero_entre_1_y_60")
    else:
        postcosecha = int(texto)
    texto = _texto(datos.peso_promedio_planta)
    if not texto:
        _agregar(errores, "peso_promedio_planta", "Ingresá el peso promedio por planta.", "obligatorio")
    elif not _ENTERO.match(texto) or int(texto) < 1:
        _agregar(errores, "peso_promedio_planta", "Ingresá un número entero mayor que 0, en gramos.", "entero_mayor_que_cero")
    else:
        peso = int(texto)
    return postcosecha, peso


def _nombre_de_variedad_repetido(cultivo, nombre, excluir_pk=None):
    """True si otra variedad del cultivo tiene ese nombre, sin distinguir mayúsculas, activa o inactiva (regla 2 de PROD-ALT-VAR)."""
    existentes = Variedad.objects.filter(cultivo=cultivo).annotate(_minuscula=Lower("nombre_variedad"))
    if excluir_pk is not None:
        existentes = existentes.exclude(pk=excluir_pk)
    return existentes.filter(_minuscula=Lower(Value(nombre))).exists()


def _validar_datos(cultivo, datos, variedad=None, semilla=None, uso=None, etapas_actuales=()):
    """Valida TODO sin escribir (reglas 2 a 7 de PROD-ALT-VAR) y devuelve ``DatosValidos``; si algo falla, un solo ``ValidationError``
    con un error por campo. Va después de bloquear el cultivo: el nombre repetido y el choque del nombre de la semilla se miran contra lo
    que otra alta ya confirmó.

    Para MODIFICAR, ``variedad`` (la actual), ``semilla`` (su ``Insumo``), ``uso`` (``UsoDeVariedad``) y ``etapas_actuales`` suman las
    reglas 3 y 4 de PROD-MOD-VAR: con lotes (aunque estén terminados) no se agregan ni se quitan etapas (``etapas_con_lotes``); con lotes
    activos u órdenes a realizar no se cambia el perfil (``perfil_con_lotes_u_ordenes``). El nombre propio no cuenta como repetido."""
    errores = {}
    nombre = _validar_nombre(datos, errores)
    perfil = _texto(datos.perfil_familia)
    perfil_valido = perfil in dict(Variedad._meta.get_field("perfil_familia").choices)
    if not perfil:
        _agregar(errores, "perfil_familia", "Elegí el perfil familiar.", "obligatorio")
    elif not perfil_valido:
        _agregar(errores, "perfil_familia", "Elegí un perfil familiar de la lista.", "perfil_invalido")
    cambia_el_perfil = variedad is not None and perfil_valido and perfil != variedad.perfil_familia
    if cambia_el_perfil and (uso.lotes_activos or uso.ordenes_a_realizar):
        _agregar(
            errores, "perfil_familia",
            "El perfil no se cambia mientras la variedad tenga lotes activos u órdenes a realizar.", "perfil_con_lotes_u_ordenes",
        )
    etapas = _validar_etapas(datos.etapas, perfil, perfil_valido, errores, "perfil_familia" if cambia_el_perfil else "etapas")
    if variedad is not None and uso.con_lotes and {codigo for codigo, _ in datos.etapas} != {e.codigo for e in etapas_actuales}:
        _agregar(
            errores, "etapas",
            "Esta variedad ya tiene lotes: no se pueden agregar ni quitar etapas (sí cambiar sus duraciones).", "etapas_con_lotes",
        )
    rangos = _validar_rangos(datos, errores)
    postcosecha, peso = _validar_postcosecha_y_peso(datos, errores)
    if "nombre" not in errores:
        if _nombre_de_variedad_repetido(cultivo, nombre, excluir_pk=variedad.pk if variedad else None):
            _agregar(errores, "nombre", f"Ya existe la variedad {cultivo.nombre_cultivo} {nombre}.", "nombre_repetido")
        elif variedad is None or nombre != variedad.nombre_variedad:
            try:
                semillas.verificar_nombre(
                    semillas.nombre_de_semilla(cultivo.nombre_cultivo, nombre), excluir_pk=semilla.pk if semilla else None
                )
            except ValidationError as error:
                errores["nombre"] = error.error_dict["nombre"]
    if errores:
        raise ValidationError(errores)
    return DatosValidos(nombre, perfil, etapas, rangos, postcosecha, peso)


def _texto_de_etapa(nombre, dias):
    """«Germinación: 5 días» (el texto de la auditoría, D-36)."""
    return f"{nombre}: {dias} día{'' if dias == 1 else 's'}"


def _exigir_agronomo(actor):
    """Precondición a de ALT, MOD y BAJ: ``actor`` es un Agrónomo con la cuenta activa (SEG-13)."""
    if not _es_agronomo_activo(actor):
        raise PermissionDenied("Solo un Agrónomo activo puede gestionar variedades.")


def _exigir_cultivo_activo(cultivo):
    """Precondición b de PROD-ALT-VAR, ya con el cultivo bloqueado."""
    if not cultivo.activo:
        raise _error_general(f"El cultivo {cultivo.nombre_cultivo} está inactivo: reactivalo antes de crear variedades.", "cultivo_inactivo")


def resumen_de_alta(actor, cultivo_id, datos):
    """PROD-ALT-VAR regla 8: valida TODO como el alta y devuelve el ``ResumenDeAlta`` (datos, duración del ciclo, cosecha estimada y nombre
    de la semilla) SIN escribir ni bloquear. «Crear variedad» vuelve a validar todo dentro de la transacción."""
    _exigir_agronomo(actor)
    cultivo = get_object_or_404(Cultivo, pk=cultivo_id)
    _exigir_cultivo_activo(cultivo)
    validos = _validar_datos(cultivo, datos)
    return ResumenDeAlta(
        cultivo=cultivo.nombre_cultivo,
        nombre=validos.nombre,
        perfil_familia=validos.perfil_familia,
        etapas=[(tipo.codigo, tipo.nombre_etapa, dias) for tipo, dias in validos.etapas],
        duracion_del_ciclo=sum(dias for _, dias in validos.etapas),
        dias_hasta_maduracion=sum(dias for tipo, dias in validos.etapas if tipo.codigo != ciclos.MADURACION),
        nombre_semilla=semillas.nombre_de_semilla(cultivo.nombre_cultivo, validos.nombre),
        rangos=validos.rangos,
        duracion_post_cosecha=validos.duracion_post_cosecha,
        peso_promedio_planta=validos.peso_promedio_planta,
    )


def alta_variedad(actor, cultivo_id, datos):
    """PROD-ALT-VAR: crea la variedad, su ciclo, sus etapas y su semilla, en una sola transacción, y devuelve la variedad.

    - Precondición a y regla 1: Agrónomo activo (cualquiera: la variedad no es de un invernadero). Precondición b: el cultivo está activo
      (``cultivo_inactivo``), verificado DESPUÉS de bloquearlo; un cultivo inexistente es ``Http404``.
    - Reglas 2 a 7: todos los errores juntos, uno por campo; nada se crea si algo falla. El nombre repetido se mira después de bloquear
      el cultivo (dos altas a la vez: la segunda ve el nombre ya usado); la restricción única de la base lo respalda.
    - Postcondiciones a, b y c: variedad activa, ciclo con una etapa por tipo incluido (en el orden del catálogo) y semilla
      «Semilla {cultivo} {variedad}», sin habilitar. Un nombre de semilla que choca con otro insumo es un error del campo ``nombre``.
    - Postcondición d y D-36: UN registro ``alta_variedad`` con variedad, ciclo, etapas y semilla como afectados.
    Orden de bloqueos (docs/patrones/stock.md, sección 5): cultivo -> (variedad nueva, semilla nueva)."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        cultivo = Cultivo.objects.select_for_update(no_key=True).filter(pk=cultivo_id).first()
        if cultivo is None:
            raise Http404("No existe ese cultivo.")
        _actor_sigue_activo(actor)
        _exigir_cultivo_activo(cultivo)
        validos = _validar_datos(cultivo, datos)
        try:
            with transaction.atomic():  # punto de guardado: un IntegrityError no rompe la transacción de afuera
                variedad = Variedad.objects.create(
                    cultivo=cultivo,
                    nombre_variedad=validos.nombre,
                    perfil_familia=validos.perfil_familia,
                    estado_variedad=Variedad.Estado.ACTIVO,
                    duracion_post_cosecha=validos.duracion_post_cosecha,
                    peso_promedio_planta=validos.peso_promedio_planta,
                    **validos.rangos,
                )
        except IntegrityError as error:
            if RESTRICCION_NOMBRE_UNICO in str(error):
                raise ValidationError(
                    {"nombre": [ValidationError(f"Ya existe la variedad {cultivo.nombre_cultivo} {validos.nombre}.", code="nombre_repetido")]}
                ) from error
            raise
        ciclo = Ciclo.objects.create(variedad=variedad)
        etapas = [
            EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo, duracion_estimada_dias=dias) for tipo, dias in validos.etapas
        ]
        semilla = semillas.crear_semilla(variedad)
        cambios = {
            "nombre": {"antes": None, "despues": validos.nombre},
            "perfil_familia": {"antes": None, "despues": validos.perfil_familia},
            "estado": {"antes": None, "despues": Variedad.Estado.ACTIVO.value},
        }
        for columna in COLUMNAS_DE_RANGO:
            cambios[columna] = {"antes": None, "despues": str(validos.rangos[columna])}
        cambios["duracion_post_cosecha"] = {"antes": None, "despues": str(validos.duracion_post_cosecha)}
        cambios["peso_promedio_planta"] = {"antes": None, "despues": str(validos.peso_promedio_planta)}
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.ALTA_VARIEDAD,
            afectados=[variedad, ciclo, *etapas, semilla],
            detalle={
                "cambios": cambios,
                "datos": {
                    "cultivo": referencia(cultivo),
                    "etapas": [_texto_de_etapa(tipo.nombre_etapa, dias) for tipo, dias in validos.etapas],
                    "nombre_semilla": semilla.nombre_insumo,
                },
            },
        )
    return variedad


# ---- modificación y reactivación (PROD-MOD-VAR) ----

# Lo que muestra el resumen antes de guardar (regla 8 de PROD-MOD-VAR). ``cambios`` es ``{campo: (antes, despues)}`` como texto (las
# etapas, como listas de textos); ``nombre_semilla`` es el nombre nuevo de la semilla o ``None`` si no cambia; ``a_notificar`` son los
# invernaderos cuyo Agrónomo recibirá un aviso; ``advertencias`` son las ``Incompatibilidad`` de rangos.
ResumenDeModificacion = namedtuple(
    "ResumenDeModificacion",
    "hay_cambios cambios nombre_semilla a_notificar advertencias duracion_del_ciclo dias_hasta_maduracion",
)
# Campos cuyo cambio se avisa a los otros invernaderos que usan la variedad (regla 7): nombre, duraciones, etapas y rangos.
CAMPOS_QUE_SE_AVISAN = {"nombre", "etapas", *COLUMNAS_DE_RANGO}
# Todo lo que prepara una modificación después de validar (sin escribir).
_Preparada = namedtuple("_Preparada", "validos cambios rangos_nuevos")


def _error_en_uso_por_otros(gestion):
    """Precondición b de PROD-MOD-VAR: qué invernaderos la usan y quiénes son sus Agrónomos."""
    return _error_general(
        f"Solo la usa {', '.join(gestion.quienes)}. La modifica el Agrónomo de alguno de esos invernaderos.", "variedad_en_uso_por_otros"
    )


def _exigir_que_pueda_gestionar(actor, variedad):
    """Precondición b de PROD-MOD-VAR y regla 1: se verifica DESPUÉS de bloquear, no solo al abrir la pantalla."""
    gestion = puede_gestionar(actor, variedad)
    if not gestion.puede:
        raise _error_en_uso_por_otros(gestion)


def _como_texto(valor):
    return str(valor)


def _diferencias(variedad, etapas_actuales, validos):
    """``{campo: (antes, despues)}`` de lo que cambia con ``validos`` (texto; las etapas, listas de textos). Vacío si no cambia nada (D-28)."""
    cambios = {}
    if validos.nombre != variedad.nombre_variedad:
        cambios["nombre"] = (variedad.nombre_variedad, validos.nombre)
    if validos.perfil_familia != variedad.perfil_familia:
        cambios["perfil_familia"] = (variedad.perfil_familia, validos.perfil_familia)
    antes_etapas = [(e.codigo, e.duracion_dias) for e in etapas_actuales]
    despues_etapas = [(tipo.codigo, dias) for tipo, dias in validos.etapas]
    if antes_etapas != despues_etapas:
        cambios["etapas"] = (
            [_texto_de_etapa(e.nombre, e.duracion_dias) for e in etapas_actuales],
            [_texto_de_etapa(tipo.nombre_etapa, dias) for tipo, dias in validos.etapas],
        )
    for columna in COLUMNAS_DE_RANGO:
        if getattr(variedad, columna) != validos.rangos[columna]:
            cambios[columna] = (_como_texto(getattr(variedad, columna)), _como_texto(validos.rangos[columna]))
    for columna, nuevo in (("duracion_post_cosecha", validos.duracion_post_cosecha), ("peso_promedio_planta", validos.peso_promedio_planta)):
        if getattr(variedad, columna) != nuevo:
            cambios[columna] = (_como_texto(getattr(variedad, columna)), _como_texto(nuevo))
    return cambios


def _rangos_nuevos(validos):
    """Los ``Rangos`` que quedarían, para la advertencia de la regla 5."""
    return Rangos(*[RangoAmbiental(validos.rangos[f"{v}_min"], validos.rangos[f"{v}_max"]) for v in VARIABLES])


def _invernaderos_a_avisar(variedad, actor):
    """Regla 7 de PROD-MOD-VAR: ``{Agrónomo: [invernaderos]}`` de los invernaderos ACTIVOS que usan la variedad, cuyo Agrónomo está
    activo y no es ``actor``; una entrada por cuenta (no por invernadero), con sus invernaderos por nombre. Sin Agrónomo no se avisa (D-14)."""
    usan = invernaderos_que_usan([variedad.pk])[variedad.pk]
    por_cuenta = {}
    invernaderos = Invernadero.objects.filter(pk__in=usan).select_related("agronomo")
    for invernadero in sorted(invernaderos, key=lambda g: (g.nombre_invernadero.lower(), g.pk)):
        agronomo = invernadero.agronomo
        if agronomo is not None and agronomo.is_active and agronomo.pk != actor.pk:
            por_cuenta.setdefault(agronomo.pk, (agronomo, []))[1].append(invernadero.nombre_invernadero)
    return list(por_cuenta.values())


def _preparar(actor, variedad, cultivo, semilla, datos):
    """Valida y calcula los cambios de una modificación (sin escribir): el trabajo común de ``resumen_de_modificacion`` y
    ``modificar_variedad``. La variedad tiene que estar activa y el actor poder gestionarla (el llamador ya bloqueó, si corresponde)."""
    if not variedad.activa:
        raise _error_general("La variedad está inactiva: solo se puede reactivar.", "variedad_inactiva")
    _exigir_que_pueda_gestionar(actor, variedad)
    etapas_actuales = ciclos.etapas_de([variedad.pk])[variedad.pk]
    uso = uso_de_variedades([variedad.pk])[variedad.pk]
    validos = _validar_datos(cultivo, datos, variedad=variedad, semilla=semilla, uso=uso, etapas_actuales=etapas_actuales)
    return _Preparada(validos, _diferencias(variedad, etapas_actuales, validos), _rangos_nuevos(validos)), etapas_actuales


def resumen_de_modificacion(actor, variedad_id, datos):
    """PROD-MOD-VAR regla 8: valida y exige lo mismo que ``modificar_variedad`` y devuelve el ``ResumenDeModificacion`` (los cambios con
    su valor anterior, el nombre nuevo de la semilla, a quiénes se avisará y las advertencias de rangos) SIN escribir, bloquear ni notificar."""
    _exigir_agronomo(actor)
    variedad = obtener_variedad(variedad_id)
    cultivo = variedad.cultivo
    semilla = Semilla.objects.filter(variedad=variedad).first()
    preparada, _ = _preparar(actor, variedad, cultivo, semilla, datos)
    cambios = preparada.cambios
    advertencias = incompatibilidades_de_rangos(variedad, preparada.rangos_nuevos) if set(cambios) & set(COLUMNAS_DE_RANGO) else []
    avisa = bool(set(cambios) & CAMPOS_QUE_SE_AVISAN)
    return ResumenDeModificacion(
        hay_cambios=bool(cambios),
        cambios=cambios,
        nombre_semilla=semillas.nombre_de_semilla(cultivo.nombre_cultivo, preparada.validos.nombre) if "nombre" in cambios else None,
        a_notificar=[nombre for _, nombres in _invernaderos_a_avisar(variedad, actor) for nombre in nombres] if avisa else [],
        advertencias=advertencias,
        duracion_del_ciclo=sum(dias for _, dias in preparada.validos.etapas),
        dias_hasta_maduracion=sum(dias for tipo, dias in preparada.validos.etapas if tipo.codigo != ciclos.MADURACION),
    )


def _bloquear_para_modificar(actor, variedad_id):
    """El orden de bloqueo de la modificación y la reactivación (docs/patrones/stock.md, sección 5): cultivo -> variedad -> insumo de la
    semilla, cada uno releído. Se lee el cultivo de la variedad sin bloquear solo para saber cuál bloquear. Verifica que quien actúa siga
    activo. Devuelve ``(cultivo, variedad, insumo)``; ``Http404`` si la variedad no existe. Dentro de ``transaction.atomic()``."""
    cultivo_id = Variedad.objects.filter(pk=variedad_id).values_list("cultivo_id", flat=True).first()
    if cultivo_id is None:
        raise Http404("No existe esa variedad.")
    cultivo = Cultivo.objects.select_for_update(no_key=True).get(pk=cultivo_id)
    _actor_sigue_activo(actor)
    variedad = Variedad.objects.select_for_update(no_key=True).filter(pk=variedad_id).first()
    if variedad is None:
        raise Http404("No existe esa variedad.")
    variedad.cultivo = cultivo
    return cultivo, variedad, semillas.bloquear_semilla(variedad)


def _guardar_variedad(variedad, campos, cultivo):
    """Guarda ``campos`` de la variedad; si dos pedidos eligieron el mismo nombre a la vez, la restricción única da un
    ``IntegrityError`` que se traduce al mismo error de campo ``nombre_repetido`` (nunca un 500)."""
    try:
        with transaction.atomic():
            variedad.save(update_fields=campos)
    except IntegrityError as error:
        if RESTRICCION_NOMBRE_UNICO in str(error):
            raise ValidationError(
                {"nombre": [ValidationError(f"Ya existe la variedad {cultivo.nombre_cultivo} {variedad.nombre_variedad}.", code="nombre_repetido")]}
            ) from error
        raise


def _escribir_etapas(variedad, validos):
    """Deja las etapas del ciclo como ``validos.etapas``: actualiza las que siguen (misma fila), crea las nuevas y borra las que se
    quitan (solo posible sin lotes, regla 3). Devuelve las filas creadas o modificadas (las borradas ya no existen)."""
    ciclo = Ciclo.objects.get(variedad=variedad)
    existentes = {e.tipo_etapa.codigo: e for e in EtapaProductiva.objects.filter(ciclo=ciclo).select_related("tipo_etapa")}
    nuevas = {tipo.codigo for tipo, _ in validos.etapas}
    for codigo, etapa in existentes.items():
        if codigo not in nuevas:
            etapa.delete()
    tocadas = []
    for tipo, dias in validos.etapas:
        etapa = existentes.get(tipo.codigo)
        if etapa is None:
            tocadas.append(EtapaProductiva.objects.create(ciclo=ciclo, tipo_etapa=tipo, duracion_estimada_dias=dias))
        elif etapa.duracion_estimada_dias != dias:
            etapa.duracion_estimada_dias = dias
            etapa.save(update_fields=["duracion_estimada_dias"])
            tocadas.append(etapa)
    return ciclo, tocadas


def _avisar_a_los_otros_invernaderos(actor, variedad, nombre_anterior, cambios, cultivo):
    """Postcondición c y regla 7 de PROD-MOD-VAR: una notificación por Agrónomo de otro invernadero que usa la variedad, solo si cambió el
    nombre, las duraciones, las etapas o los rangos, dentro de la transacción y sin bloquear el cambio. No se audita (D-42)."""
    if not set(cambios) & CAMPOS_QUE_SE_AVISAN:
        return
    quien = actor.get_full_name() or actor.email
    for agronomo, invernaderos in _invernaderos_a_avisar(variedad, actor):
        rige = f"Rige para {', '.join(invernaderos)} desde ahora."
        if "nombre" in cambios:
            otros = " También modificó duraciones, etapas o rangos." if set(cambios) & (CAMPOS_QUE_SE_AVISAN - {"nombre"}) else ""
            detalle = f"{quien} le cambió el nombre a {variedad.nombre_variedad}.{otros} {rige}"
        else:
            detalle = f"{quien} modificó sus duraciones, etapas o rangos. {rige}"
        notificaciones.notificar(agronomo, f"Cambió la variedad {cultivo.nombre_cultivo} {nombre_anterior}", detalle[: notificaciones.LARGO_DETALLE])


def modificar_variedad(actor, variedad_id, datos, *, advertencia_confirmada=False):
    """PROD-MOD-VAR: modifica los datos, el ciclo y los rangos de una variedad activa y la devuelve.

    - Precondición a: Agrónomo activo. Precondición b y regla 1: puede gestionarla (``variedad_en_uso_por_otros``), verificado DESPUÉS de
      bloquear. Regla 9: una variedad inactiva no se modifica (``variedad_inactiva``). Precondición c y reglas 2 a 4: validación completa,
      un error por campo (mismos campos y códigos que el alta, más ``etapas_con_lotes`` y ``perfil_con_lotes_u_ordenes``).
    - D-28: sin cambios no se escribe, no se audita ni se notifica.
    - Regla 5: si cambian los rangos y la variedad tiene lotes activos, se advierte (``FaltaConfirmarAdvertencia``) salvo que
      ``advertencia_confirmada``; los lotes en producción siguen donde están.
    - Postcondiciones a y b y regla 6: actualiza la variedad, su ciclo y sus etapas y, si cambió el nombre, el de su semilla, en la misma
      transacción. Postcondición c y regla 7: avisa a los otros invernaderos. Postcondición e y D-36: UN registro ``modificacion_variedad``.
    Orden de bloqueos: cultivo -> variedad -> insumo (docs/patrones/stock.md, sección 5)."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        cultivo, variedad, insumo = _bloquear_para_modificar(actor, variedad_id)
        preparada, etapas_actuales = _preparar(actor, variedad, cultivo, insumo, datos)
        cambios, validos = preparada.cambios, preparada.validos
        if not cambios:
            return variedad
        if set(cambios) & set(COLUMNAS_DE_RANGO) and not advertencia_confirmada:
            advertencias = incompatibilidades_de_rangos(variedad, preparada.rangos_nuevos)
            if advertencias:
                raise FaltaConfirmarAdvertencia(advertencias)
        nombre_anterior = variedad.nombre_variedad
        campos = []
        for campo in ("perfil_familia", *COLUMNAS_DE_RANGO, "duracion_post_cosecha", "peso_promedio_planta"):
            if campo in cambios:
                valor = validos.perfil_familia if campo == "perfil_familia" else (
                    validos.rangos[campo] if campo in validos.rangos else getattr(validos, campo)
                )
                setattr(variedad, campo, valor)
                campos.append(campo)
        if "nombre" in cambios:
            variedad.nombre_variedad = validos.nombre
            campos.append("nombre_variedad")
        if campos:
            _guardar_variedad(variedad, campos, cultivo)
        afectados = [variedad]
        if "etapas" in cambios:
            ciclo, tocadas = _escribir_etapas(variedad, validos)
            afectados += [ciclo, *tocadas]
        if "nombre" in cambios:
            nombre_de_la_semilla = semillas.nombre_de_semilla(cultivo.nombre_cultivo, validos.nombre)
            anterior = semillas.renombrar_semilla(insumo, nombre_de_la_semilla)
            afectados.append(Semilla.objects.get(variedad=variedad))
            cambios = {**cambios, "nombre_semilla": (anterior, nombre_de_la_semilla)}
        _avisar_a_los_otros_invernaderos(actor, variedad, nombre_anterior, cambios, cultivo)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.MODIFICACION_VARIEDAD,
            afectados=afectados,
            detalle={"cambios": {campo: {"antes": antes, "despues": despues} for campo, (antes, despues) in cambios.items()}},
        )
    return variedad


def reactivar_variedad(actor, variedad_id):
    """PROD-MOD-VAR postcondición d y regla 9: reactiva una variedad dada de baja y su semilla, y devuelve la variedad.

    - Precondición a: Agrónomo activo. Regla 1: puede gestionarla (``variedad_en_uso_por_otros``), después de bloquear. Una variedad que
      no está inactiva se rechaza (``variedad_no_inactiva``). Regla 9: el cultivo tiene que estar activo (``cultivo_inactivo``); se
      bloquea antes de verificarlo.
    - NO toca las existencias de la semilla: no vuelve a habilitar las deshabilitadas y las que siguen activas siguen activas.
    - Postcondición e y D-36: UN registro ``reactivacion_variedad`` con el cambio de estado, con la variedad y su semilla.
    Orden de bloqueos: cultivo -> variedad -> insumo."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        cultivo, variedad, insumo = _bloquear_para_modificar(actor, variedad_id)
        if variedad.activa:
            raise _error_general("La variedad ya está activa.", "variedad_no_inactiva")
        if not cultivo.activo:
            raise _error_general(f"Primero reactivá el cultivo {cultivo.nombre_cultivo}.", "cultivo_inactivo")
        _exigir_que_pueda_gestionar(actor, variedad)
        variedad.estado_variedad = Variedad.Estado.ACTIVO
        variedad.save(update_fields=["estado_variedad"])
        semillas.reactivar_semilla(insumo)
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.REACTIVACION_VARIEDAD,
            afectados=[variedad, Semilla.objects.get(variedad=variedad)],
            detalle={"cambios": {"estado": {"antes": Variedad.Estado.INACTIVO.value, "despues": Variedad.Estado.ACTIVO.value}}},
        )
    return variedad


# ---- baja (PROD-BAJ-VAR) ----

# Lo que informa la baja antes de confirmar (reglas 2 y 3 de PROD-BAJ-VAR): los impedimentos de los registrantes, los invernaderos donde la
# semilla está habilitada y el stock que queda por invernadero (``StockDeSemilla``). Solo lectura.
InformeDeBaja = namedtuple("InformeDeBaja", "impedimentos habilitada_en stock")
StockDeSemilla = namedtuple("StockDeSemilla", "invernadero cantidad")


def _existencias_activas_de_la_semilla(variedad_id):
    """Las ``InsumoInvernadero`` ACTIVAS de la semilla de la variedad, por id, con su invernadero."""
    return list(
        InsumoInvernadero.objects.filter(
            insumo__semilla__variedad_id=variedad_id, estado_insumo_invernadero=InsumoInvernadero.Estado.ACTIVO
        )
        .select_related("invernadero")
        .order_by("id")
    )


def informe_de_baja(variedad):
    """PROD-BAJ-VAR reglas 2 y 3: ``InformeDeBaja(impedimentos, habilitada_en, stock)``. ``impedimentos`` son los de los registrantes
    (lotes activos, órdenes a realizar, contratos); ``habilitada_en``, los nombres de los invernaderos donde la semilla está habilitada, por
    nombre; ``stock``, un ``StockDeSemilla(invernadero, cantidad)`` por cada uno donde queda stock (sin bloquear la baja). Solo lectura:
    no bloquea ni escribe."""
    existencias = _existencias_activas_de_la_semilla(variedad.pk)
    actuales = servicio_de_stock.stock_actual_de([e.pk for e in existencias])
    por_nombre = sorted(existencias, key=lambda e: (e.invernadero.nombre_invernadero.lower(), e.pk))
    return InformeDeBaja(
        impedimentos=impedimentos_de_baja_de_variedad(variedad),
        habilitada_en=[e.invernadero.nombre_invernadero for e in por_nombre],
        stock=[StockDeSemilla(e.invernadero.nombre_invernadero, actuales[e.pk]) for e in por_nombre if actuales[e.pk] > 0],
    )


def baja_variedad(actor, variedad_id):
    """PROD-BAJ-VAR: da de baja lógica la variedad y su semilla y devuelve la variedad.

    - Precondición a: Agrónomo activo. Precondiciones b a f, DESPUÉS de bloquear y TODAS juntas (regla 2): no gestora
      (``variedad_en_uso_por_otros``), ya inactiva (``variedad_inactiva``) y lo que informan los registrantes (``lotes_activos``,
      ``ordenes_a_realizar``, ``contratos_abiertos``), cada uno con su texto y cómo resolverlo. Sin registrantes la f no se verifica.
    - Postcondiciones a y b y reglas 1 y 3: variedad y semilla quedan inactivas, con ciclo, etapas e historial; las existencias de la
      semilla NO se deshabilitan (el stock que queda se descarta con un ajuste, CMP-AJT-STK). Se reevalúan las alertas de CADA existencia
      activa (la de «bajo el mínimo» se resuelve porque el insumo está inactivo).
    - Postcondición c y D-36: UN registro ``baja_variedad`` con la variedad y su semilla y el cambio de estado.
    Orden de bloqueos (docs/patrones/stock.md, sección 5): los invernaderos donde la semilla está habilitada (leídos sin bloquear, bloqueados
    en orden de id y vueltos a leer) -> cultivo -> variedad -> insumo. Si al releer aparece un invernadero que no se bloqueó, se rechaza con
    ``cambio_simultaneo``: reintentar bloquearía el invernadero después del insumo, fuera de orden."""
    _exigir_agronomo(actor)
    with transaction.atomic():
        leidos = {e.invernadero_id for e in _existencias_activas_de_la_semilla(variedad_id)}
        if leidos:
            list(Invernadero.objects.select_for_update(no_key=True).filter(pk__in=leidos).order_by("id"))
        cultivo, variedad, insumo = _bloquear_para_modificar(actor, variedad_id)
        existencias = _existencias_activas_de_la_semilla(variedad_id)
        if {e.invernadero_id for e in existencias} - leidos:
            raise _error_general(
                "Mientras se daba de baja, la semilla se habilitó en otro invernadero. Volvé a intentarlo.", "cambio_simultaneo"
            )
        impedimentos = []
        gestion = puede_gestionar(actor, variedad)
        if not gestion.puede:
            impedimentos.append(
                ("variedad_en_uso_por_otros", f"Solo la usa {', '.join(gestion.quienes)}. La da de baja el Agrónomo de alguno de esos invernaderos.")
            )
        if not variedad.activa:
            impedimentos.append(("variedad_inactiva", "La variedad ya está dada de baja."))
        for impedimento in impedimentos_de_baja_de_variedad(variedad):
            impedimentos.append((impedimento.codigo, f"{impedimento.texto} {impedimento.como_resolver}"))
        if impedimentos:
            raise ValidationError({NON_FIELD_ERRORS: [ValidationError(texto, code=codigo) for codigo, texto in impedimentos]})
        variedad.estado_variedad = Variedad.Estado.INACTIVO
        variedad.save(update_fields=["estado_variedad"])
        semillas.dar_de_baja_semilla(insumo)
        creadas, resueltas = [], []
        for existencia in existencias:
            reevaluacion = alertas_de_stock.reevaluar_alertas_del_insumo(existencia.pk)
            creadas += reevaluacion.creadas
            resueltas += reevaluacion.resueltas
        detalle = {"cambios": {"estado": {"antes": Variedad.Estado.ACTIVO.value, "despues": Variedad.Estado.INACTIVO.value}}}
        datos = _datos_de_alertas({}, alertas_de_stock.Reevaluacion(creadas, resueltas))
        if datos:
            detalle["datos"] = datos
        RegistroAuditoria.objects.registrar(
            usuario=actor,
            accion=RegistroAuditoria.Accion.BAJA_VARIEDAD,
            afectados=[variedad, Semilla.objects.get(variedad=variedad)],
            detalle=detalle,
        )
    return variedad


def invernaderos_que_usan_el_cultivo(cultivo):
    """El ``registrar_uso_de_cultivo`` de `inventario` (regla 4 de PROD-MOD-CLT): ids de los invernaderos ACTIVOS que usan alguna variedad
    del cultivo (semilla habilitada o lotes activos): la unión de ``invernaderos_que_usan`` de todas sus variedades, activas o no (la baja de
    la variedad no deshabilita sus existencias). Sin una consulta por variedad."""
    ids = list(Variedad.objects.filter(cultivo=cultivo).values_list("pk", flat=True))
    if not ids:
        return set()
    return set().union(*invernaderos_que_usan(ids).values())
