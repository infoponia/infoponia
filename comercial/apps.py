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
        from comercial.servicios import asientos_comerciales, atencion, camara, cobranza, concrecion, confirmacion, enlaces, entregas, pre_reserva, registrantes, resoluciones, solicitudes, stock_maduro, suministros, vehiculos
        from contabilidad import extensiones as extensiones_de_contabilidad
        from core import extensiones as extensiones_de_core
        from core.menu import registrar_entrada
        from core.models import Usuario
        from core.procesos import registrar_paso_diario
        from inventario import extensiones as extensiones_de_inventario
        from maestros import extensiones as extensiones_de_maestros
        from maestros.alertas import Clase, Destinatario, Origen, TipoAlerta, registrar_tipo_de_alerta
        from maestros.models import Alerta
        from produccion import extensiones as extensiones_de_produccion

        # `contabilidad` (CON-04c): el texto de origen, sin dirección, de los asientos de la cosecha (su movimiento «salida por cosecha») y de la entrega. Idempotente.
        extensiones_de_contabilidad.registrar_enlace_de_origen("movimiento_de_stock", asientos_comerciales.enlace_de_movimiento_de_stock)
        extensiones_de_contabilidad.registrar_enlace_de_origen("orden_de_trabajo", asientos_comerciales.enlace_de_orden_de_trabajo)
        # CON-04d: lo mismo para los asientos del cobro (y de lo entregado al cancelar una compra-venta), de la indemnización, de las anulaciones y de la multa.
        extensiones_de_contabilidad.registrar_enlace_de_origen("pago_cliente", asientos_comerciales.enlace_de_pago_cliente)
        extensiones_de_contabilidad.registrar_enlace_de_origen("solicitud_revision", asientos_comerciales.enlace_de_solicitud_revision)
        extensiones_de_contabilidad.registrar_enlace_de_origen("anulacion", asientos_comerciales.enlace_de_anulacion)
        extensiones_de_contabilidad.registrar_enlace_de_origen("contrato", asientos_comerciales.enlace_de_contrato)

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
        # COM-04a (D-64 punto 11): los botones de `comercial` en las pantallas de `produccion` y el grupo «Cosechas» del Inicio del Agrónomo (después de la
        # sección de PRD-04: `comercial` está después de `produccion` en INSTALLED_APPS).
        extensiones_de_produccion.registrar_acciones_de_cosecha(registrantes.acciones_de_cosechas)
        extensiones_de_produccion.registrar_entradas_de_comercial(registrantes.entradas_de_comercial)
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_cosechas)

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

        # COM-04b (D-64 puntos 9 y 10, D-62 y D-56): la cámara. Las dos alertas (con su enlace a la pestaña «Cámara»), los pasos 20 (vencer partidas) y 25 (reasignar cámara; recupera
        # PROD-ASG-CAM) y la pestaña «Cámara» de la ficha del invernadero (que se registra una sola vez: `ready()` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=camara.TIPO_POR_VENCER,
                nombre="Partida por vencer",
                destinatario=Destinatario.AGRONOMO_O_GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.ESTADO,
                origen=Origen.STOCK_COSECHADO,
            )
        )
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=camara.TIPO_MERMA_RESERVADA,
                nombre="Merma en cámara con producto reservado",
                destinatario=Destinatario.AGRONOMO_O_GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.EVENTO,
                origen=Origen.MERMA,
            )
        )
        # COM-06a (PROD-VNC-CAM 3b): «partida vencida en una entrega en curso» para el Gerente (crítica), con el mismo enlace a la pestaña «Cámara».
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=camara.TIPO_EN_ENTREGA_EN_CURSO,
                nombre="Partida vencida en una entrega en curso",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.CRITICA,
                clase=Clase.ESTADO,
                origen=Origen.STOCK_COSECHADO,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta(
            (camara.TIPO_POR_VENCER, camara.TIPO_MERMA_RESERVADA, camara.TIPO_EN_ENTREGA_EN_CURSO), camara.enlaces_de_alertas_de_camara
        )
        registrar_paso_diario("vencer_partidas_en_camara", "Vencer partidas en cámara", 20, camara.vencer_partidas_en_camara)
        registrar_paso_diario("reasignar_camara", "Reasignar cámara", 25, camara.reasignar_camara)
        # COM-04c (D-65 punto 7): el paso 27 pasa a «vencido» el enlace de decisión sin respuesta y avisa al Vendedor una sola vez.
        registrar_paso_diario("avisar_enlaces_vencidos", "Avisar enlaces vencidos", 27, enlaces.avisar_enlaces_vencidos)
        if "camara" not in [clave for clave, _, _ in extensiones_de_maestros._PESTANAS]:
            extensiones_de_maestros.registrar_pestana_de_invernadero("camara", "Cámara", camara.pestana_de_camara)

        # COM-05a1 (D-66, D-62 y D-56): las entregas. La alerta «entrega sin transportista» (para el Gerente, con su enlace a la lista de entregas), el paso diario 50 (COM-PNF-ENT) y lo
        # que protege a las entregas en las tareas anteriores: el impedimento de baja de un transportista de un invernadero, lo que se informa al dar de baja una cuenta y su efecto. Todos
        # idempotentes (``ready()`` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=entregas.TIPO_SIN_TRANSPORTISTA,
                nombre="Entrega sin transportista",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.ESTADO,
                origen=Origen.ENTREGA,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((entregas.TIPO_SIN_TRANSPORTISTA,), entregas.enlaces_de_alertas)
        registrar_paso_diario("planificar_entregas", "Planificar entregas", 50, entregas.planificar_entregas)
        if entregas.impedimentos_de_transportista not in extensiones_de_maestros._IMPEDIMENTOS_DE_TRANSPORTISTA:
            extensiones_de_maestros.registrar_impedimento_de_transportista(entregas.impedimentos_de_transportista)
        extensiones_de_core.registrar_asignaciones_de_cuenta(entregas.asignaciones_de_cuenta)
        extensiones_de_core.registrar_efecto_de_baja_de_cuenta(entregas.efecto_de_baja_de_cuenta)
        # COM-05a2: el grupo «Entregas» del Inicio del Gerente y del Vendedor (después de la sección de cosechas del Agrónomo; `registrar_seccion_de_inicio` es idempotente).
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_entregas)
        # COM-06a (D-68): la discrepancia de una entrega de suministro (alerta de evento para el Gerente, con su enlace a la ficha del suministro) y lo que protege a una ruta iniciada: la baja de la
        # cuenta de un Transportista en ruta (los demás registrantes de «Transportista en ruta» están en `entregas.impedimentos_de_transportista`).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=concrecion.TIPO_DISCREPANCIA,
                nombre="Discrepancia de entrega",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.EVENTO,
                origen=Origen.SOLICITUD_REVISION,
            )
        )
        # COM-07a (1a de COM-EVL-DSC y de COM-RSV-QJA): las alertas de discrepancia y de queja llevan al Gerente a la ficha de la solicitud (`solicitudes.enlaces_de_alertas`); COM-06a y COM-06b las llevaban a la ficha del suministro.
        extensiones_de_maestros.registrar_enlace_de_alerta((concrecion.TIPO_DISCREPANCIA, confirmacion.TIPO_QUEJA), solicitudes.enlaces_de_alertas)
        # COM-06b (D-68, D-62): la queja del cliente (alerta de evento para el Gerente; hasta COM-07 lleva a la ficha del suministro, como la discrepancia) y la entrega no reconocida (crítica; lleva a la
        # pantalla de COM-ATN-ENR). Solo la reciben los Gerentes. Idempotentes (``ready()`` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=confirmacion.TIPO_QUEJA,
                nombre="Queja de un cliente",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.EVENTO,
                origen=Origen.SOLICITUD_REVISION,
            )
        )
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=confirmacion.TIPO_NO_RECONOCIDA,
                nombre="Entrega no reconocida por el cliente",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.CRITICA,
                clase=Clase.EVENTO,
                origen=Origen.ENTREGA,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((confirmacion.TIPO_NO_RECONOCIDA,), atencion.enlaces_de_alertas)
        # COM-07b (D-69 punto 14, D-63 punto 2): la alerta «suministro resuelto» (de evento, para el Gerente; el caso de uso dice severidad «alto» y la API tiene tres niveles: crítica).
        # La crea COM-RSV-SUM con su `AlertaComercial(suministro=…)`; el Gerente la da por atendida desde la ficha. Idempotente (`ready()` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=resoluciones.TIPO_DE_ALERTA,
                nombre="Suministro resuelto por incumplimientos",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.CRITICA,
                clase=Clase.EVENTO,
                origen=Origen.SUMINISTRO,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((resoluciones.TIPO_DE_ALERTA,), resoluciones.enlaces_de_alertas)  # la campana del Gerente lleva a la ficha del suministro (MAE-02d)
        # COM-07b (D-56 punto 6, enmendado por D-69 punto 7): el paso 33 recupera la resolución que falló o no llegó a ejecutarse; va antes del 35, el 40 y el 50.
        registrar_paso_diario("resolver_suministros", "Resolver suministros con incumplimientos superados", 33, resoluciones.resolver_suministros_pendientes)
        # COM-08a (D-94 puntos 6 y 7, D-62 y D-56): la alerta «pago en mora» (de estado, para el Gerente, crítica, con su enlace a «Registrar cobro» con la entrega ya elegida) y el paso diario 30.
        # Idempotentes (`ready()` puede correr más de una vez).
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo=cobranza.TIPO_PAGO_EN_MORA,
                nombre="Pago en mora",
                destinatario=Destinatario.GERENTE,
                severidad=Alerta.Severidad.CRITICA,
                clase=Clase.ESTADO,
                origen=Origen.ENTREGA,
            )
        )
        extensiones_de_maestros.registrar_enlace_de_alerta((cobranza.TIPO_PAGO_EN_MORA,), cobranza.enlaces_de_alertas)
        registrar_paso_diario("vencer_pagos", "Vencer pagos de suministro", 30, cobranza.vencer_pagos)
        extensiones_de_core.registrar_impedimento_de_baja_de_cuenta(entregas.impedimentos_de_baja_de_cuenta)
        # COM-06a: la entrada «Mi ruta» (solo para el Transportista; es de campo, sin menú lateral, así que su acceso real es la sección «Ruta de hoy» de su Panel de control).
        registrar_entrada(("Mi ruta", "comercial:ruta", "truck"), (Usuario.Rol.TRANSPORTISTA,))
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_ruta)
