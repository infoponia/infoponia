# Configuración de la app `comercial` (nivel 6 de D-37): clientes y vehículos (COM-01) y, más adelante, contratos y entregas. En
# `ready()` registra su entrada del menú y sus funciones en los puntos de extensión de `maestros` y de `core` (regla A4 de D-37).
from django.apps import AppConfig


class ComercialConfig(AppConfig):
    """Registra la app `comercial` (nivel 6 de D-37: importa de `core`, `contabilidad`, `maestros`, `inventario` y `produccion`;
    nunca de `compras` ni de `iot`)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'comercial'

    def ready(self):
        """Registra la entrada «Comercial» del menú y los registrantes de `maestros` («Logística») y de `core` (ficha de la cuenta). Con
        guarda en cada uno: ``ready()`` puede correr más de una vez (las pruebas lo vuelven a llamar) y ningún registrante debe quedar
        duplicado (el de «Logística» admite uno solo y una segunda llamada lanza ``RuntimeError``)."""
        from comercial.servicios import vehiculos
        from core import extensiones as extensiones_de_core
        from core.menu import registrar_entrada
        from core.models import Usuario
        from maestros import extensiones as extensiones_de_maestros

        # Menú: «Comercial» para el Gerente (después de «Producción») y el Vendedor (que no tiene «Producción»: queda después de «Panel de
        # control»). ``registrar_entrada`` no repite una entrada ya registrada.
        registrar_entrada(
            ("Comercial", "comercial:inicio", "cart"), (Usuario.Rol.GERENTE, Usuario.Rol.VENDEDOR), despues_de="Producción"
        )

        # `maestros`: la «Logística» de la ficha del invernadero (vehículo y situación de cada Transportista; D-55). Un solo registrante.
        if vehiculos.logistica_de_transportistas not in extensiones_de_maestros._LOGISTICA:
            extensiones_de_maestros.registrar_logistica_de_transportista(vehiculos.logistica_de_transportistas)

        # `core`: el «Vehículo» del Transportista en la ficha de su cuenta y en «Mi perfil» (decisión del estudiante del 21/11/2026).
        # ``registrar_*`` es idempotente.
        extensiones_de_core.registrar_datos_de_cuenta(vehiculos.datos_de_cuenta_del_transportista)

        # Datos para la verificación a mano (core/verificacion.py; docs/patrones/datos_de_verificacion.md): el cargador de `comercial`, orden 20
        # (después de `maestros`, `iot` y `produccion`). ``registrar_cargador`` no repite un código ya registrado.
        from comercial import verificacion as verificacion_comercial
        from core import verificacion

        verificacion.registrar_cargador(
            verificacion_comercial.CODIGO,
            "Comercial: clientes en cada estado, un vehículo dado de baja y transportistas con y sin invernadero",
            20,
            verificacion_comercial.cargar,
        )
