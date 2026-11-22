# Configuración de la app `produccion` (nivel 5 de D-37). En `ready()` registra sus funciones en los puntos de extensión de
# `maestros`, `inventario` y `core` (regla A4 de D-37; docs/api/produccion.md, sección 3).
from django.apps import AppConfig


class ProduccionConfig(AppConfig):
    """Registra la app `produccion` y sus registrantes (PRD-01). Los dos tipos de alerta (`produccion_merma_umbral` y
    `produccion_plantas_comprometidas`) los registra PRD-02."""

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
            # `maestros`: invernadero. PRD-01 no registra efecto de baja: con lotes u órdenes la baja no se hace (PRD-04 sí).
            (
                extensiones_de_maestros._IMPEDIMENTOS,
                registrantes.impedimentos_de_baja_del_invernadero,
                extensiones_de_maestros.registrar_impedimento_de_baja,
            ),
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

        # `core`: ``registrar_*`` es idempotente.
        extensiones_de_core.registrar_asignaciones_de_cuenta(registrantes.asignaciones_de_cuenta)
        extensiones_de_core.registrar_seccion_de_inicio(registrantes.seccion_de_inicio)
