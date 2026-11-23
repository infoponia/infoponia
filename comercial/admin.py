# Admin de `comercial`, de solo lectura (como el de las demás apps). Existe solo en desarrollo: lo apagan las rutas, no el
# registro (SEG-18 y D-30). Los clientes y los vehículos se crean y cambian solo con los servicios, que aplican sus reglas.

from django.contrib import admin

from .models import Cliente, CompraVenta, DetalleReserva, DetalleVenta, DireccionCliente, ReservaStock, Vehiculo


class SoloLectura(admin.ModelAdmin):
    """Lista y ficha sin alta, edición ni baja."""

    def has_add_permission(self, request):
        """No se crean a mano."""
        return False

    def has_change_permission(self, request, obj=None):
        """No se modifican a mano."""
        return False

    def has_delete_permission(self, request, obj=None):
        """No se borran a mano."""
        return False


@admin.register(Cliente)
class ClienteAdmin(SoloLectura):
    """Clientes: CUIT, nombre visible y estado."""

    list_display = ("cuit_cliente", "nombre_visible", "tipo_cliente", "estado_cliente")
    list_filter = ("tipo_cliente", "estado_cliente")


@admin.register(DireccionCliente)
class DireccionClienteAdmin(SoloLectura):
    """Vínculos entre un cliente y sus direcciones (D-58)."""

    list_display = ("cliente", "direccion")


@admin.register(Vehiculo)
class VehiculoAdmin(SoloLectura):
    """Vehículos: patente, tipo, capacidad, estado y transportista."""

    list_display = ("patente", "tipo_vehiculo", "capacidad_carga", "estado_vehiculo", "transportista")
    list_filter = ("tipo_vehiculo", "estado_vehiculo")


@admin.register(CompraVenta)
class CompraVentaAdmin(SoloLectura):
    """Compra-ventas: código, cliente, Vendedor, fecha pactada y estado (se crean solo con `registrar_compra_venta`)."""

    list_display = ("id", "numero", "cliente", "vendedor", "fecha_pactada_venta", "estado_venta")
    list_filter = ("estado_venta", "modalidad_entrega")


@admin.register(DetalleVenta)
class DetalleVentaAdmin(SoloLectura):
    """Detalles de venta: venta, variedad, cantidad, precio y estado."""

    list_display = ("id", "compra_venta", "variedad", "cant_solicitada_venta", "precio_unitario_de_venta", "estado_detalle_venta")


@admin.register(ReservaStock)
class ReservaStockAdmin(SoloLectura):
    """Reservas de stock: detalle, invernadero, fecha de entrega y estado."""

    list_display = ("id", "detalle_venta", "invernadero", "fecha_entrega_reserva", "estado_reserva")
    list_filter = ("estado_reserva",)


@admin.register(DetalleReserva)
class DetalleReservaAdmin(SoloLectura):
    """Líneas de reserva: reserva, lote o partida y cantidad reservada."""

    list_display = ("id", "reserva", "lote", "partida", "cantidad_reservada", "cantidad_cosechada")
