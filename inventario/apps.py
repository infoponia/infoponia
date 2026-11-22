# Configuración de la app `inventario` (nivel 4 de D-37): registra sus tipos de alerta en `maestros` (regla A4 de D-37).
from django.apps import AppConfig


class InventarioConfig(AppConfig):
    """Registra la app `inventario`. En ``ready()`` registra sus cuatro tipos de alerta (INV-01, docs/patrones/stock.md,
    sección 4) en ``maestros.alertas``; los usa INV-02, pero la baja del insumo (CMP-BAJ-INS) ya resuelve «bajo el mínimo».
    También registra la entrada «Inventario» del menú del Agrónomo (``core.menu.registrar_entrada``, regla A4 de D-37), después de «Producción»."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventario'

    def ready(self):
        """Registra los cuatro tipos de alerta de `inventario` (idempotente: ``ready()`` puede correr más de una vez)."""
        from core.menu import registrar_entrada
        from core.models import Usuario
        from inventario.alertas import registrar_tipos_de_stock
        from core.procesos import registrar_paso_diario
        from inventario.servicios import insumos_invernadero, vencimientos
        from maestros import extensiones as extensiones_de_maestros

        registrar_tipos_de_stock()
        # INV-02: la baja de un invernadero se rechaza con stock o tránsito de insumos y, si pasa, deshabilita sus insumos
        # (precondición f y postcondición c de PROD-BAJ-INV). Con guarda: ``ready()`` puede correr más de una vez.
        if insumos_invernadero.impedimentos_de_baja_de_invernadero not in extensiones_de_maestros._IMPEDIMENTOS:
            extensiones_de_maestros.registrar_impedimento_de_baja(insumos_invernadero.impedimentos_de_baja_de_invernadero)
        if insumos_invernadero.efecto_de_baja_de_invernadero not in extensiones_de_maestros._EFECTOS_DE_BAJA:
            extensiones_de_maestros.registrar_efecto_de_baja(insumos_invernadero.efecto_de_baja_de_invernadero)
        # INV-02, paso 7 (D-56): la revisión de vencimientos es el paso 10 del proceso diario. ``registrar_paso_diario`` es idempotente.
        registrar_paso_diario("revisar_vencimientos", "Revisar vencimientos de insumos", 10, vencimientos.paso_diario)
        registrar_entrada(("Inventario", "inventario:existencias", "box"), (Usuario.Rol.AGRONOMO,), despues_de="Producción")
