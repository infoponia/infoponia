# Configuración de la app `compras` (nivel 6 de D-37): registra su entrada del menú de `core` y su sección del Inicio (regla A4 de D-37).
from django.apps import AppConfig


class ComprasConfig(AppConfig):
    """Registra la app `compras` (nivel 6 de D-37, D-87). Importa de `core`, `contabilidad`, `maestros` e `inventario`;
    **nunca** de `comercial` ni de `produccion` (A1: `compras` y `comercial` no se importan entre sí). En ``ready()``
    registra la entrada «Compras» del menú del Gerente y del Agrónomo (``core.menu.registrar_entrada``) y la sección «Compras» del Inicio del
    Agrónomo (``core.extensiones.registrar_seccion_de_inicio``, CMP-02a). Cada tarea de la ronda «Compras 1» suma lo suyo."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compras'
    verbose_name = 'Compras'

    def ready(self):
        """Registra el menú y la sección del Inicio. Es idempotente: ``ready()`` puede correr más de una vez."""
        from compras.servicios import inicio
        from core import extensiones
        from core.menu import registrar_entrada
        from core.models import Usuario

        # CMP-01 y CMP-02a: «Compras» lo ven el Gerente y el Agrónomo (el Contador la verá con CON-02, solo lectura, D-87 punto 6) y abre en su primera pestaña, «Pedidos»
        # (la de «Proveedores» está a un clic). Lugar del NAV del prototipo: después de «Producción» (el Gerente) y de «Inventario» (el Agrónomo).
        registrar_entrada(("Compras", "compras:pedidos", "pkg"), (Usuario.Rol.GERENTE,), despues_de="Producción")
        registrar_entrada(("Compras", "compras:pedidos", "pkg"), (Usuario.Rol.AGRONOMO,), despues_de="Inventario")
        # CMP-02a: «Insumos bajo el mínimo» con «Pedir» y «Esperando cotizaciones» en el Inicio del Agrónomo (D-87 punto 5).
        extensiones.registrar_seccion_de_inicio(inicio.seccion_de_inicio)

        # CMP-02b (D-87 punto 5). Los registrantes de ``maestros`` e ``inventario`` no son idempotentes: se guardan con una guarda, porque ``ready()`` puede correr más de una vez.
        from compras.servicios import registrantes
        from inventario import extensiones as extensiones_de_inventario
        from maestros import extensiones as extensiones_de_maestros

        extensiones.registrar_efecto_de_baja_de_cuenta(registrantes.efecto_de_baja_de_cuenta)
        extensiones.registrar_asignaciones_de_cuenta(registrantes.asignaciones_de_cuenta)
        if (registrantes.contar_traspaso, registrantes.traspasar_pedidos) not in extensiones_de_maestros._TRASPASOS:
            extensiones_de_maestros.registrar_traspaso(registrantes.contar_traspaso, registrantes.traspasar_pedidos)
        if registrantes.aviso_de_traspaso not in extensiones_de_maestros._AVISOS_DE_TRASPASO:
            extensiones_de_maestros.registrar_aviso_de_traspaso(registrantes.aviso_de_traspaso)
        if registrantes.impedimento_de_deshabilitacion not in extensiones_de_inventario._IMPEDIMENTOS_DE_DESHABILITACION:
            extensiones_de_inventario.registrar_impedimento_de_deshabilitacion(registrantes.impedimento_de_deshabilitacion)
