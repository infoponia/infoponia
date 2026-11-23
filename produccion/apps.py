# Configuración de la app `produccion` (nivel 5 de D-37). En `ready()` registra sus funciones en los puntos de extensión de
# `maestros`, `inventario` y `core` (regla A4 de D-37; docs/api/produccion.md, sección 3).
from django.apps import AppConfig


class ProduccionConfig(AppConfig):
    """Registra la app `produccion`, sus registrantes (PRD-01) y los dos tipos de alerta de la merma (PRD-02)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'produccion'

    def ready(self):
        """Registra los puntos de extensión de `maestros`, `inventario` y `core`. Con guarda en cada uno: ``ready()`` puede correr
        más de una vez y ningún registrante debe quedar duplicado (los de `maestros` e `inventario` no son idempotentes)."""
        from core import extensiones as extensiones_de_core
        from inventario import extensiones as extensiones_de_inventario
        from maestros import extensiones as extensiones_de_maestros
        from produccion.servicios import registrantes

        # `maestros`: sectores.
        for lista, funcion, registrar in (
            (extensiones_de_maestros._AGUJEROS, registrantes.agujeros_de_sector, extensiones_de_maestros.registrar_agujeros_de_sector),
            (
                extensiones_de_maestros._IMPEDIMENTOS_DE_SECTOR,
                registrantes.impedimentos_de_baja_de_sector,
                extensiones_de_maestros.registrar_impedimento_de_baja_de_sector,
            ),
            (extensiones_de_maestros._CONTENIDOS, registrantes.contenido_de_sectores, extensiones_de_maestros.registrar_contenido_de_sector),
            (extensiones_de_maestros._PERFILES, registrantes.perfil_de_sector, extensiones_de_maestros.registrar_perfil_de_sector),
            (
                extensiones_de_maestros._AVISOS_DE_CAMBIO_DE_TIPO,
                registrantes.avisos_de_cambio_de_tipo,
                extensiones_de_maestros.registrar_aviso_de_cambio_de_tipo,
            ),
            # `maestros`: invernadero. PRD-01 no registra efecto de baja: con lotes u órdenes la baja no se hace (PRD-04 sí, abajo).
            (
                extensiones_de_maestros._IMPEDIMENTOS,
                registrantes.impedimentos_de_baja_del_invernadero,
                extensiones_de_maestros.registrar_impedimento_de_baja,
            ),
            # PRD-04: el cierre del registro «Fuera de servicio» (vuelta a servicio, baja del sector y baja del invernadero).
            (extensiones_de_maestros._VUELTAS_A_SERVICIO, registrantes.efecto_de_vuelta_a_servicio, extensiones_de_maestros.registrar_efecto_de_vuelta_a_servicio),
            (extensiones_de_maestros._EFECTOS_DE_BAJA_DE_SECTOR, registrantes.efecto_de_baja_de_sector, extensiones_de_maestros.registrar_efecto_de_baja_de_sector),
            (extensiones_de_maestros._EFECTOS_DE_BAJA, registrantes.efecto_de_baja_del_invernadero, extensiones_de_maestros.registrar_efecto_de_baja),
            # `inventario`.
            (extensiones_de_inventario._RESERVAS, registrantes.reservas_de_insumo, extensiones_de_inventario.registrar_reservas_de_insumo),
            (
                extensiones_de_inventario._ORDENES_QUE_RESERVAN,
                registrantes.ordenes_que_reservan,
                extensiones_de_inventario.registrar_ordenes_que_reservan,
            ),
            (extensiones_de_inventario._USOS_DE_VARIEDAD, registrantes.uso_de_variedad, extensiones_de_inventario.registrar_uso_de_variedad),
            (
                extensiones_de_inventario._VARIEDADES_PRESENTES,
                registrantes.variedades_presentes,
                extensiones_de_inventario.registrar_variedades_presentes,
            ),
            (
                extensiones_de_inventario._IMPEDIMENTOS_DE_BAJA_DE_VARIEDAD,
                registrantes.impedimentos_de_baja_de_variedad,
                extensiones_de_inventario.registrar_impedimento_de_baja_de_variedad,
            ),
        ):
            if funcion not in lista:
                registrar(funcion)

        # `maestros`: el traspaso de las órdenes del Capataz (el punto admite varios registrantes y recibe el rol) y la pestaña.
        if (registrantes.contar_traspaso, registrantes.traspasar_ordenes) not in extensiones_de_maestros._TRASPASOS:
            extensiones_de_maestros.registrar_traspaso(registrantes.contar_traspaso, registrantes.traspasar_ordenes)
        if not any(clave == "lotes" for clave, _, _ in extensiones_de_maestros._PESTANAS):
            extensiones_de_maestros.registrar_pestana_de_invernadero("lotes", "Lotes activos", registrantes.pestana_de_lotes)
        # PRD-03: la pestaña «Bitácora» de la ficha del invernadero (el Agrónomo a cargo y el Gerente; el Capataz no la ve).
        if not any(clave == "bitacora" for clave, _, _ in extensiones_de_maestros._PESTANAS):
            extensiones_de_maestros.registrar_pestana_de_invernadero("bitacora", "Bitácora", registrantes.pestana_de_bitacora)
        # PRD-03: «Bitácora» en el menú del Gerente (solo consulta), después de «Producción». El Agrónomo entra desde «Producción»; el Capataz, desde su bandeja
        # (no tiene menú lateral, D-25). `registrar_entrada` no repite una entrada ya registrada.
        from core.menu import registrar_entrada
        from core.models import Usuario

        registrar_entrada(("Bitácora", "produccion:bitacora", "clock"), (Usuario.Rol.GERENTE,), despues_de="Producción")

        # `maestros.alertas`: los dos tipos de alerta de la merma (PRD-02; docs/api/produccion.md, sección 3). Nombres y severidades
        # del prototipo (decisión del estudiante, 22/11/2026). Registrar dos veces la misma definición no hace nada.
        from maestros.alertas import Clase, Destinatario, Origen, TipoAlerta, registrar_tipo_de_alerta
        from maestros.models import Alerta

        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo="produccion_merma_umbral",
                nombre="Merma sobre el umbral",
                destinatario=Destinatario.AGRONOMO_Y_GERENTE,
                severidad=Alerta.Severidad.CRITICA,
                clase=Clase.EVENTO,
                origen=Origen.MERMA,
            )
        )
        registrar_tipo_de_alerta(
            TipoAlerta(
                codigo="produccion_plantas_comprometidas",
                nombre="Plantas comprometidas por una transición",
                destinatario=Destinatario.AGRONOMO_O_GERENTE,
                severidad=Alerta.Severidad.ADVERTENCIA,
                clase=Clase.EVENTO,
                origen=Origen.MERMA,
            )
        )

        # PRD-03: el cargador de datos para la verificación a mano (core/verificacion.py; docs/patrones/datos_de_verificacion.md). Orden 15: después de `maestros` (5) e `iot` (10).
        from core import verificacion
        from produccion import verificacion as verificacion_produccion

        verificacion.registrar_cargador(
            verificacion_produccion.CODIGO, "Producción: lote con merma previa, transición a realizar e insumos", 15, verificacion_produccion.cargar
        )

        # `core`: ``registrar_*`` es idempotente.
        extensiones_de_core.registrar_asignaciones_de_cuenta(registrantes.asignaciones_de_cuenta)
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_inicio)
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_inicio_del_agronomo)  # PRD-04
