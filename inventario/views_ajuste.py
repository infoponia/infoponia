# Vista de «Ajustar stock de insumo» (INV-02, paso 8; CMP-AJT-STK, ``VIEWS.ajuste`` del prototipo). Una sola pantalla con dos formas:
#   - Con HTMX (``HX-Request``): devuelve solo el formulario (``_formulario.html``). Un cambio de selector o «Agregar lote nuevo» solo lo
#     redibuja (sin validar ni calcular); «Ver resumen» (``calcular``) valida y calcula. Nunca escribe: solo llama a ``calcular_ajuste``.
#   - Sin JavaScript: cada envío es un POST completo con la acción elegida (``calcular``, ``agregar_lote`` o ``confirmar``) y la página vuelve
#     entera. Los pasos 1 a 5 del CU funcionan igual (respaldo completo).
# La vista solo orquesta: arma ``entrada`` con lo escrito, llama a ``situacion_del_insumo``, ``calcular_ajuste`` y ``confirmar_ajuste`` y
# muestra sus errores por campo. Todas las reglas, los cálculos y la «huella» son del servicio (inventario/servicios/ajustes.py).
# Solo el Agrónomo a cargo del invernadero: otros roles, 403 (``rol_requerido``); un invernadero ajeno, 403 (``PermissionDenied``).
#
# La «firma» es una marca de lo que se calculó (invernadero, insumo, motivo y datos). Al confirmar se compara con lo enviado: si la
# persona cambió un dato después de ver el resumen y confirmó sin recalcular (algo posible sin JavaScript), no se confirma lo que no vio:
# se recalcula y se muestra el resumen nuevo.

import hashlib
import json
import re

from django.contrib import messages
from django.core.exceptions import NON_FIELD_ERRORS, PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.decorators.vary import vary_on_headers

from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import ajustes, alertas_de_stock
from inventario.servicios import insumos_invernadero as api_iin
from maestros.models import Invernadero

AGRONOMO = Usuario.Rol.AGRONOMO
MAXIMO_DE_LOTES_NUEVOS = 20
CAMPOS_SIMPLES = ("cantidad", "vencimiento", "lote_id", "origen_id", "destino_id", "sentido", "descripcion")
# El servicio nombra el error de un campo sin «_id»; la pantalla lo busca bajo ese nombre y lo mira en el campo de la entrada.
CAMPO_DE_ENTRADA = {"lote": "lote_id", "origen": "origen_id", "destino": "destino_id"}


def _entero(valor):
    """``valor`` como ``int`` o ``None`` (los ids llegan como texto)."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _vacio(datos, campo):
    """True si el campo no trae nada escrito (en la pantalla en vivo no se marcan como error los campos que todavía están vacíos)."""
    return not any(v.strip() for v in datos.getlist(campo))


def _entrada(datos):
    """La ``entrada`` del servicio a partir de lo enviado, más ``posiciones``: el número de pantalla de cada lote nuevo con datos (las filas
    totalmente vacías se ignoran; el servicio numera sus errores sobre las filas que recibe)."""
    entrada = {campo: datos.get(campo, "").strip() for campo in CAMPOS_SIMPLES}
    entrada["lotes"] = datos.getlist("lotes")
    entrada["contados"] = {
        clave[len("contado_"):]: valor.strip() for clave, valor in datos.items() if clave.startswith("contado_") and valor.strip()
    }
    nuevos, posiciones = [], []
    for n in range(_cantidad_de_nuevos(datos)):
        fila = {"cantidad": datos.get(f"nuevo_{n}_cantidad", "").strip(), "vencimiento": datos.get(f"nuevo_{n}_vencimiento", "").strip()}
        if fila["cantidad"] or fila["vencimiento"]:
            nuevos.append(fila)
            posiciones.append(n)
    entrada["nuevos"] = nuevos
    return entrada, posiciones


def _cantidad_de_nuevos(datos):
    """Cuántas filas de «lote nuevo» muestra el recuento (0 a ``MAXIMO_DE_LOTES_NUEVOS``)."""
    return max(0, min(MAXIMO_DE_LOTES_NUEVOS, _entero(datos.get("nuevos_n")) or 0))


def _firma(invernadero_id, insumo_id, motivo, entrada):
    """Marca de lo que se calculó: cambia si cambia cualquier dato del ajuste."""
    texto = json.dumps([invernadero_id, insumo_id, motivo, entrada], sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


def _huella_a_texto(huella):
    """La huella del servicio (``((lote_id, cantidad_texto), ...), reservado_texto``) como texto para un campo oculto."""
    lotes, reservado = huella
    return json.dumps([[[i, c] for i, c in lotes], reservado])


def _huella_de_texto(texto):
    """Lo inverso de ``_huella_a_texto``; ``None`` si no es una huella válida."""
    try:
        lotes, reservado = json.loads(texto)
        return tuple((int(i), str(c)) for i, c in lotes), str(reservado)
    except (TypeError, ValueError):
        return None


def _errores(error, posiciones, datos, explicito):
    """``({campo: mensaje}, [mensajes generales])`` de un ``ValidationError`` del servicio. Los errores de «lote nuevo» se renumeran a la fila
    de la pantalla. En vivo (sin ``explicito``) no se muestran los de campos todavía vacíos ni los generales: la persona sigue escribiendo."""
    campos, generales = {}, []
    for campo, lista in error.error_dict.items():
        mensaje = lista[0].messages[0]
        if campo == NON_FIELD_ERRORS:
            if explicito:
                generales.append(mensaje)
            continue
        fila = re.fullmatch(r"nuevo_(\d+)_(cantidad|vencimiento)", campo)
        if fila and int(fila[1]) < len(posiciones):
            campo = f"nuevo_{posiciones[int(fila[1])]}_{fila[2]}"
        if not explicito and _vacio(datos, CAMPO_DE_ENTRADA.get(campo, campo)):
            continue
        campos[campo] = mensaje
    return campos, generales


def _ids_de(lotes_con_estado):
    return {str(lc.lote.pk) for lc in lotes_con_estado}


@rol_requerido(AGRONOMO)
@never_cache
@vary_on_headers("HX-Request")
@require_http_methods(["GET", "HEAD", "POST"])
def ajuste(request):
    """«Ajustar stock de insumo» (CMP-AJT-STK). Pasos 1 a 3: invernadero, insumo y motivo; paso 4 a 6: stock y lotes; pasos 7 a 12: datos del
    motivo y resumen; paso 13 y 14: confirmar. Abrirla (GET) o cambiar un dato (HTMX) no escribe nada; solo confirmar escribe."""
    usuario = request.user
    datos = request.POST if request.method == "POST" else request.GET
    accion = datos.get("accion", "") if request.method == "POST" else ""
    en_vivo = request.headers.get("HX-Request") == "true"
    invernaderos = list(Invernadero.objects.en_alcance_de(usuario).order_by("nombre_invernadero", "id"))

    invernadero = None
    if datos.get("invernadero"):
        invernadero_id = _entero(datos.get("invernadero"))
        if invernadero_id is None:
            raise PermissionDenied(api_iin.MENSAJE_AJENO)
        get_object_or_404(Invernadero, pk=invernadero_id)
        invernadero = next((g for g in invernaderos if g.pk == invernadero_id), None)
        if invernadero is None:  # existe, pero no está a su cargo (o está inactivo): D-28
            raise PermissionDenied(api_iin.MENSAJE_AJENO)
    habilitados = api_iin.habilitados(invernadero.pk) if invernadero else []
    existencia = next((e for e in habilitados if e.insumo_id == _entero(datos.get("insumo"))), None)
    motivo = datos.get("motivo", "") if datos.get("motivo", "") in ajustes.CODIGOS_DE_MOTIVO else ""

    contexto = {
        "pestana": "existencias",
        "invernaderos": invernaderos,
        "invernadero": invernadero,
        "habilitados": habilitados,
        "existencia": existencia,
        "motivo": motivo,
        "motivos": ajustes.MOTIVOS,
        "valores": {clave: valor for clave, valor in datos.items()},
        "marcados": set(datos.getlist("lotes")),
        "errores": {},
        "errores_generales": [],
        "resumen": None,
        "huella": "",
        "firma": "",
        "desactualizado": False,
        "cambio_la_firma": False,
        "nuevos_n": _cantidad_de_nuevos(datos),
    }

    if existencia is not None and motivo:
        entrada, posiciones = _entrada(datos)
        firma = _firma(invernadero.pk, existencia.insumo_id, motivo, entrada)
        explicito = accion in ("calcular", "confirmar")
        if accion == "agregar_lote":
            contexto["nuevos_n"] = min(MAXIMO_DE_LOTES_NUEVOS, contexto["nuevos_n"] + 1)
        elif accion == "confirmar":
            huella = _huella_de_texto(datos.get("huella"))
            if huella is None or datos.get("firma") != firma:
                contexto["cambio_la_firma"] = True  # cambió un dato después del resumen: se recalcula y se vuelve a mostrar
            else:
                try:
                    resultado = ajustes.confirmar_ajuste(usuario, invernadero.pk, existencia.insumo_id, motivo, entrada, huella)
                except ajustes.AjusteDesactualizado:
                    contexto["desactualizado"] = True  # extensión 14a: no se cambió nada; abajo se vuelve a calcular con lo vigente
                except ValidationError as error:
                    contexto["errores"], contexto["errores_generales"] = _errores(error, posiciones, datos, True)
                    explicito = None  # ya se mostraron los errores: no se recalcula
                else:
                    messages.success(request, _mensaje_de_exito(existencia, resultado))
                    if resultado.inconsistente == "activa":
                        messages.warning(request, "El stock sigue sin cubrir las reservas de las órdenes: revisalo con un recuento.")
                    return redirect("inventario:existencias")
        # Solo «Ver resumen» y «Confirmar ajuste» validan y calculan (cambio de criterio sobre el paso 8 de INV-02, pedido en la revisión a mano):
        # cambiar un selector o agregar un lote solo redibuja el formulario. Abrir la pantalla (GET, p. ej. «Dar de baja») calcula sin errores.
        if accion != "agregar_lote" and explicito is not None and (explicito or request.method != "POST"):
            try:
                resumen = ajustes.calcular_ajuste(usuario, invernadero.pk, existencia.insumo_id, motivo, entrada)
            except ValidationError as error:
                errores, generales = _errores(error, posiciones, datos, explicito or contexto["desactualizado"])
                contexto["errores"].update(errores)
                contexto["errores_generales"] += generales
            else:
                contexto["resumen"] = resumen
                contexto["huella"] = _huella_a_texto(resumen.huella)
                contexto["firma"] = firma

    if existencia is not None:
        situacion = ajustes.situacion_del_insumo(usuario, invernadero.pk, existencia.insumo_id)  # tras escribir o fallar: lo vigente
        todos = situacion.lotes
        contexto.update(
            situacion=situacion,
            unidad=situacion.insumo.unidad_medida_insumo,
            lotes_recuento=[lc for lc in todos if lc.estado != "faltante"],
            lotes_con_stock=[lc for lc in todos if lc.estado != "faltante" and lc.lote.cantidad_disponible > 0],
            lotes_destino=list(todos),
            lotes_vencidos=[lc for lc in todos if lc.estado == "vencido" and lc.lote.cantidad_disponible > 0],
            filas_nuevas=range(contexto["nuevos_n"]),
        )
    plantilla = "inventario/ajuste/_formulario.html" if en_vivo else "inventario/ajuste/pantalla.html"
    return render(request, plantilla, contexto)


def _mensaje_de_exito(existencia, resultado):
    """El aviso breve de un ajuste registrado: el insumo y el stock en que quedó."""
    unidad = existencia.insumo.unidad_medida_insumo
    return (
        f"Ajuste registrado: {existencia.insumo.nombre_insumo} queda con "
        f"{alertas_de_stock._con_unidad(resultado.stock_actual, unidad)} en {existencia.invernadero.nombre_invernadero}."
    )
