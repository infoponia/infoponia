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
        from comercial.servicios import pre_reserva, registrantes, stock_maduro, suministros, vehiculos
        from core import extensiones as extensiones_de_core
        from core.menu import registrar_entrada
        from core.models import Usuario
        from core.procesos import registrar_paso_diario
        from inventario import extensiones as extensiones_de_inventario
        from maestros import extensiones as extensiones_de_maestros
        from maestros.alertas import Clase, Destinatario, Origen, TipoAlerta, registrar_tipo_de_alerta
        from maestros.models import Alerta
        from produccion import extensiones as extensiones_de_produccion

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

        # D-60: el cambio de Vendedor de un invernadero pasa sus compra-ventas al Vendedor nuevo (el punto admite varios registrantes y recibe
        # el rol). Precondición f de PROD-BAJ-VAR: una variedad con compra-ventas abiertas no se da de baja.
        if (registrantes.contar_contratos, registrantes.traspasar_contratos) not in extensiones_de_maestros._TRASPASOS:
            extensiones_de_maestros.registrar_traspaso(registrantes.contar_contratos, registrantes.traspasar_contratos)
        if registrantes.impedimentos_de_baja_de_variedad not in extensiones_de_inventario._IMPEDIMENTOS_DE_BAJA_DE_VARIEDAD:
            extensiones_de_inventario.registrar_impedimento_de_baja_de_variedad(registrantes.impedimentos_de_baja_de_variedad)

        # `produccion` (D-59, punto 3; docs/api/extensiones_de_produccion.md): lo reservado de cada lote y el detalle de cada cosecha. Un solo
        # registrante por punto; ``registrar_*`` es idempotente con la misma función.
        extensiones_de_produccion.registrar_reservado_de_lote(stock_maduro.reservado_de_lotes)
        extensiones_de_produccion.registrar_detalle_de_cosecha(stock_maduro.detalle_de_cosechas)

        # COM-03b (D-62, D-63 y D-56): la primera alerta comercial («período sin cobertura completa», MD-133) con su enlace en la campana (el Gerente va a
        # la ficha del suministro; el Agrónomo, a la del invernadero) y el paso diario 40, que pre-reserva los períodos que entran en la ventana. Los tres
        # registros son idempotentes (``ready()`` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=pre_reserva.TIPO_DE_ALERTA,
                nombre="Período sin cobertura completa",
                destinatario=Destinatario.AGRONOMO_O_GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.ESTADO,
                origen=Origen.DETALLE_SUMINISTRO,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((pre_reserva.TIPO_DE_ALERTA,), pre_reserva.enlaces_de_alertas_de_periodo)
        registrar_paso_diario("pre_reservar_suministros", "Pre-reservar suministros", 40, pre_reserva.pre_reservar_suministros)
        registrar_paso_diario("cerrar_rescisiones", "Cerrar rescisiones de suministros", 35, suministros.cerrar_rescisiones)  # COM-RSC-SUM, regla «Cierre»
