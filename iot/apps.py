# Configuración de la app `iot` (nivel 7 de D-37): registra sus tipos de alerta en `maestros` y su entrada del menú de `core`
# (regla A4 de D-37).
from django.apps import AppConfig

class IotConfig(AppConfig):
    """Registra la app `iot` (nivel 7 de D-37: importa hasta `produccion`; ninguna app de nivel menor la importa). En
    ``ready()`` registra los 11 tipos de alerta del IoT (IOT-01, docs/modelo/iot.md) y la entrada «IoT» del menú del Gerente y
    del Agrónomo, justo después de «Producción» (``core.menu.registrar_entrada``)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'iot'
    verbose_name = 'IoT'

    def ready(self):
        """Registra los tipos de alerta y la entrada del menú. Los dos son idempotentes (``ready()`` puede correr más de una vez)."""
        from core.menu import registrar_entrada
        from core.models import Usuario
        from iot.alertas import registrar_tipos_de_iot

        registrar_tipos_de_iot()
        # IOT-01, paso 4: «IoT» lo ven el Gerente y el Agrónomo (los demás roles reciben 403 en todo el módulo).
        registrar_entrada(
            ("IoT", "iot:inicio", "activity"),
            (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO),
            despues_de="Producción",
        )
        self._registrar_en_maestros()

    def _registrar_en_maestros(self):
        """IOT-02 (docs/api/extensiones_de_maestros.md): conecta `iot` con `maestros` por sus puntos de extensión (regla A4 de D-37): el estado del IoT del invernadero, los impedimentos
        de baja del invernadero y del sector y el contenido del sector. Con guarda: ``ready()`` puede correr más de una vez y estos puntos no deben duplicar sus registrantes
        (el del estado admite uno solo)."""
        from maestros import extensiones
        from iot.servicios import hardware, sistemas

        if not any(registrado[0] is sistemas.estados_de_sistemas for registrado in extensiones._ESTADO_IOT):
            extensiones.registrar_estado_iot(sistemas.estados_de_sistemas, sistemas.url_de_registro)
        if sistemas.impedimentos_de_baja_del_invernadero not in extensiones._IMPEDIMENTOS:
            extensiones.registrar_impedimento_de_baja(sistemas.impedimentos_de_baja_del_invernadero)
        if hardware.impedimentos_de_baja_del_sector not in extensiones._IMPEDIMENTOS_DE_SECTOR:
            extensiones.registrar_impedimento_de_baja_de_sector(hardware.impedimentos_de_baja_del_sector)
        if hardware.contenido_de_sectores not in extensiones._CONTENIDOS:
            extensiones.registrar_contenido_de_sector(hardware.contenido_de_sectores)
        # IOT-04 (D-62): adónde lleva cada alerta del IoT en la campana y en «Alertas». ``registrar_enlace_de_alerta`` es idempotente con la misma función.
        from iot.alertas import CODIGOS_DE_ALERTAS_IOT
        from iot.servicios import alertas_iot

        extensiones.registrar_enlace_de_alerta(CODIGOS_DE_ALERTAS_IOT, alertas_iot.enlaces_de_alertas_iot)
