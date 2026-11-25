# Pantallas del pago a proveedores (CMP-05; prototipo: ``tabPag`` y ``VIEWS.c_pag``). Las vistas solo orquestan: leen lo que se envió, llaman al servicio (``compras/servicios/pagos.py``) y renderizan; las
# reglas son de los servicios. La entrada de menú «Pagos a proveedores» es del Contador y del Gerente (D-87 punto 6): el Gerente con un Contador activo ve la bandeja y lo ya pagado **en solo lectura**
# (D-91 punto 6; D-30: sin botones que lleven a un 403). El formulario funciona **sin JavaScript** y sin validar mientras se escribe (.claude/rules/interfaz.md): «Ver resumen» muestra el paso 6 y
# «Confirmar pago» registra el paso 8. Lo que el prototipo traía de más o de menos se corrige según el caso de uso (D-61): cuatro medios (no tres), fecha elegible (no fija en hoy), resumen antes de
# confirmar y sin número de comprobante (el modelo no lo tiene).

from datetime import date

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe

from compras.errores import ErrorDeCompras
from compras.models import Pago
from compras.servicios import pagos as api
from contabilidad.errores import ErrorContable
from contabilidad.models import AsientoContable
from contabilidad.servicios import responsables
from core.acceso import rol_requerido
from core.models import Usuario
from inventario.servicios import stock
from inventario.servicios.formato import texto_precio

GERENTE = Usuario.Rol.GERENTE
CONTADOR = Usuario.Rol.CONTADOR
MAXIMO_DE_REGISTRADOS = 100


@rol_requerido(GERENTE, CONTADOR)
@require_safe
def pagos(request):
    """«Pagos a proveedores» (CMP-REG-PAG paso 2): los proveedores para pagar, del que espera hace más tiempo al más reciente (proveedor, orden, listo desde, líneas y monto), y los pagos registrados. El botón
    «Registrar pago» solo lo ve quien puede registrarlo; el Gerente con un Contador activo mira sin botones. No audita."""
    return render(
        request,
        "compras/pagos/lista.html",
        {
            "pendientes": api.pagos_pendientes(),
            "registrados": Pago.objects.select_related("orden", "proveedor").order_by("-fecha_pago", "-id")[:MAXIMO_DE_REGISTRADOS],
            "puede_registrar": responsables.puede_registrar_asientos(request.user),
            "hay_contador": responsables.contador_activo() is not None,
        },
    )


def _fecha(texto):
    """``date`` de ``AAAA-MM-DD``; ``None`` si no es una fecha."""
    try:
        return date.fromisoformat((texto or "").strip())
    except ValueError:
        return None


@rol_requerido(GERENTE, CONTADOR)
@never_cache
def pago_nuevo(request, orden_id, proveedor_id):
    """«Registrar pago a proveedor» (CMP-REG-PAG pasos 3 a 10, ``VIEWS.c_pag``). GET: el detalle (paso 4) y el formulario con el medio **sin preselección** y la fecha de hoy. POST con ``revisar``: el resumen
    del paso 6 (con el asiento); ``confirmar``: registra (paso 8) y vuelve a la bandeja; ``editar``: vuelve al formulario. Un error de negocio vuelve al formulario con lo escrito (5a, 5b, 8b); un par que ya no
    está para pagar (2a, 8a) lleva a la ficha de la orden con el aviso. El Gerente con un Contador activo es 403 (1a) y una orden inexistente, 404."""
    hoy = stock.hoy()
    try:
        detalle = api.detalle_del_pago(request.user, orden_id, proveedor_id)
    except ErrorDeCompras as error:
        if error.codigo == "proveedor_ajeno":
            raise Http404("Ese proveedor no está en la orden.") from error
        (messages.info if error.codigo == "pago_ya_registrado" else messages.error)(request, error.mensaje)
        return redirect("compras:orden_ficha", orden_id=orden_id)
    contexto = {"detalle": detalle, "medios": Pago.MedioPago.choices, "medio": "", "fecha": hoy.isoformat(), "hoy": hoy.isoformat(), "errores": {}}
    if request.method != "POST":
        return render(request, "compras/pagos/formulario.html", contexto)

    medio = request.POST.get("medio_pago", "")
    texto_fecha = request.POST.get("fecha", "") or hoy.isoformat()
    contexto.update(medio=medio, fecha=texto_fecha)
    accion = request.POST.get("accion", "")
    if accion not in ("revisar", "confirmar"):
        return render(request, "compras/pagos/formulario.html", contexto)
    fecha = _fecha(texto_fecha)
    if fecha is None:
        contexto["errores"] = {"fecha": "Escribí la fecha como una fecha válida."}
        return render(request, "compras/pagos/formulario.html", contexto)
    try:
        if accion == "revisar":
            resumen = api.resumir_pago(request.user, orden_id, proveedor_id, medio, fecha, hoy=hoy)
            return render(request, "compras/pagos/resumen.html", {**contexto, "resumen": resumen, "movimientos": resumen.movimientos, "medio_texto": Pago.MedioPago(resumen.medio).label})
        pago = api.registrar_pago(request.user, orden_id, proveedor_id, medio, fecha, hoy=hoy)
    except ErrorDeCompras as error:
        if error.campo == "medio_pago":
            contexto["errores"] = {"medio_pago": error.mensaje}
            return render(request, "compras/pagos/formulario.html", contexto)
        (messages.info if error.codigo == "pago_ya_registrado" else messages.error)(request, error.mensaje)
        return redirect("compras:orden_ficha", orden_id=orden_id)
    except ErrorContable as error:
        contexto["errores"] = {error.campo or "general": error.mensaje}
        return render(request, "compras/pagos/formulario.html", contexto)
    asiento = AsientoContable.objects.filter(origen_id=pago.pk).first()
    messages.success(
        request,
        f"Registramos el pago {pago} de ${texto_precio(pago.monto_pago)} a {pago.proveedor.nombre_para_mostrar}."
        + (f" Asiento N.º {asiento.numero_asiento} del libro de gestión." if asiento else ""),
    )
    return redirect("compras:pagos")
