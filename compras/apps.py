# Configuración de la app `compras` (nivel 6 de D-37): registra su entrada del menú de `core` y su sección del Inicio (regla A4 de D-37).
from django.apps import AppConfig


class ComprasConfig(AppConfig):
    """Registra la app `compras` (nivel 6 de D-37, D-87). Importa de `core`, `contabilidad`, `maestros` e `inventario`;
    **nunca** de `comercial` ni de `produccion` (A1: `compras` y `comercial` no se importan entre sí). En ``ready()``
    registra los pasos diarios 60 a 62 (CMP-03), la entrada «Compras» del menú del Gerente y del Agrónomo (``core.menu.registrar_entrada``) y la sección «Compras» del Inicio del
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
        # CMP-03 (D-87 punto 6): el Contador ve «Compras» solo con las órdenes, en solo lectura.
        registrar_entrada(("Compras", "compras:ordenes", "pkg"), (Usuario.Rol.CONTADOR,))
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

        # CMP-03 (D-14 y D-42): lo que espera al Gerente (las órdenes por aprobar) cuenta en sus pendientes; la ventana de baja de su cuenta lo muestra.
        from compras.servicios import ordenes as servicio_de_ordenes

        extensiones.registrar_contador_de_pendientes(servicio_de_ordenes.pendientes_de_aprobacion)

        # CMP-03 (D-87 punto 4, D-56): los pasos diarios 60, 61 y 62. ``registrar_paso_diario`` es idempotente con la misma función.
        from compras import procesos
        from core.procesos import registrar_paso_diario

        registrar_paso_diario(procesos.CODIGO_VENCIDOS, "Pedidos vencidos", 60, procesos.paso_pedidos_vencidos)
        registrar_paso_diario(procesos.CODIGO_RECORDATORIO, "Recordatorio de validez de cotizaciones", 61, procesos.paso_recordatorio_de_validez)
        registrar_paso_diario(procesos.CODIGO_SIN_ELEGIBLE, "Pedidos sin cotización elegible", 62, procesos.paso_pedidos_sin_cotizacion_elegible)

        # CMP-04 (D-87 punto 5, A4): el tipo de alerta «recepción con inconvenientes» (para el Gerente) con su enlace a la ficha de la orden, y el enlace del asiento a la recepción en el libro de gestión.
        from compras.servicios import recepciones
        from contabilidad import extensiones as extensiones_de_contabilidad
        from maestros.alertas import Clase, Destinatario, TipoAlerta, registrar_tipo_de_alerta
        from maestros.models import Alerta

        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=recepciones.TIPO_DE_ALERTA,
                nombre="Recepción con inconvenientes",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.EVENTO,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((recepciones.TIPO_DE_ALERTA,), recepciones.enlaces_de_alertas)
        extensiones_de_contabilidad.registrar_enlace_de_origen("recepcion", recepciones.enlace_de_origen)
