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
        from inventario.servicios import insumos_invernadero, semillas, variedades, vencimientos
        from inventario import views_variedades as variedades_de_cultivos_vista
        from maestros import extensiones as extensiones_de_maestros

        registrar_tipos_de_stock()
        # INV-02: la baja de un invernadero se rechaza con stock o tránsito de insumos y, si pasa, deshabilita sus insumos
        # (precondición f y postcondición c de PROD-BAJ-INV). Con guarda: ``ready()`` puede correr más de una vez.
        if insumos_invernadero.impedimentos_de_baja_de_invernadero not in extensiones_de_maestros._IMPEDIMENTOS:
            extensiones_de_maestros.registrar_impedimento_de_baja(insumos_invernadero.impedimentos_de_baja_de_invernadero)
        if insumos_invernadero.efecto_de_baja_de_invernadero not in extensiones_de_maestros._EFECTOS_DE_BAJA:
            extensiones_de_maestros.registrar_efecto_de_baja(insumos_invernadero.efecto_de_baja_de_invernadero)
        # INV-03, paso 7: las semillas y el uso de un cultivo (PROD-MOD-CLT reglas 3 y 4; docs/api/extensiones_de_maestros.md, «Cultivos»).
        # Con guarda: ``ready()`` puede correr más de una vez y estos puntos no deben duplicar sus registrantes.
        if (semillas.contar_semillas_del_cultivo, semillas.renombrar_semillas_del_cultivo) not in extensiones_de_maestros._SEMILLAS:
            extensiones_de_maestros.registrar_semillas_de_cultivo(
                semillas.contar_semillas_del_cultivo, semillas.renombrar_semillas_del_cultivo
            )
        if variedades.invernaderos_que_usan_el_cultivo not in extensiones_de_maestros._USOS_DE_CULTIVO:
            extensiones_de_maestros.registrar_uso_de_cultivo(variedades.invernaderos_que_usan_el_cultivo)
        # INV-03, paso 8: la tabla de variedades de cada tarjeta de cultivo (PROD-CNS-VAR). Admite un solo registrante: con guarda.
        if variedades_de_cultivos_vista.variedades_de_cultivos not in extensiones_de_maestros._VARIEDADES:
            extensiones_de_maestros.registrar_variedades_de_cultivo(variedades_de_cultivos_vista.variedades_de_cultivos)
        # INV-02, paso 7 (D-56): la revisión de vencimientos es el paso 10 del proceso diario. ``registrar_paso_diario`` es idempotente.
        registrar_paso_diario("revisar_vencimientos", "Revisar vencimientos de insumos", 10, vencimientos.paso_diario)
        registrar_entrada(("Inventario", "inventario:existencias", "box"), (Usuario.Rol.AGRONOMO,), despues_de="Producción")
