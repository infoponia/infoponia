# Configuración de la app `maestros` (nivel 3 de D-37): registra su entrada del menú de `core` (regla A4 de D-37).
from django.apps import AppConfig


class MaestrosConfig(AppConfig):
    """Registra la app `maestros`. En ``ready()`` agrega «Producción» (la lista de invernaderos, MAE-01) al menú del
    Gerente y del Agrónomo, cada uno con su alcance (regla 1 de PROD-CNS-INV), después de «Panel de control»: ``core`` no
    puede importar `maestros`, así que la entrada se registra en su punto de extensión (``core.menu.registrar_entrada``).
    `maestros` tiene sus propios puntos de extensión en ``maestros/extensiones.py``."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'maestros'

    def ready(self):
        """Registra la entrada «Producción» en el menú de `core`, los cuatro tipos de alerta de personal (MAE-02a) y, en
        ``core.extensiones`` (MAE-02b, D-43), los efectos de la baja y la reactivación de una cuenta con invernaderos a cargo,
        lo que la ventana de baja informa y la sección «Personal por asignar» del Inicio del Gerente; y (NOT-01, D-42) la
        fuente de alertas de la campana y el contador de pendientes del Gerente; (MAE-04, D-48) la identidad de la organización y la entrada «Configuración»."""
        from core import extensiones
        from core.menu import registrar_entrada
        from core.models import Usuario
        from maestros import extensiones as extensiones_de_maestros
        from maestros.servicios import invernaderos, perfil, sectores, transportistas
        from maestros.servicios.alertas import registrar_tipos_de_personal

        registrar_tipos_de_personal()
        # MAE-03: al dar de baja un invernadero, sus sectores pasan a inactivos con un log por sector (postcondición f de
        # PROD-BAJ-INV).
        extensiones_de_maestros.registrar_efecto_de_baja(sectores.efecto_de_baja_de_invernadero)

        extensiones.registrar_efecto_de_baja_de_cuenta(invernaderos.efectos_de_baja_de_cuenta)
        extensiones.registrar_efecto_de_reactivacion_de_cuenta(invernaderos.efectos_de_reactivacion_de_cuenta)
        extensiones.registrar_asignaciones_de_cuenta(invernaderos.asignaciones_de_cuenta)
        extensiones.registrar_seccion_de_inicio(invernaderos.seccion_de_inicio)
        # MAE-05 (D-55): el «Invernadero» del Transportista, solo para consultar en la ficha de la cuenta y en «Mi perfil».
        # ``registrar_datos_de_cuenta`` es idempotente (``ready()`` puede correr más de una vez): no duplica el registro.
        extensiones.registrar_datos_de_cuenta(transportistas.datos_de_cuenta)
        # NOT-01 (D-42): las alertas de la campana y el contador de pendientes del Gerente.
        extensiones.registrar_fuente_de_alertas(invernaderos.items_de_campana)
        extensiones.registrar_contador_de_pendientes(invernaderos.pendientes_de_alertas)
        # MAE-04 (D-48): el nombre y el color principal de la organización salen del perfil; ``core`` los consulta sin
        # conocer a ``maestros`` (regla A1 de D-37).
        extensiones.registrar_identidad_de_la_organizacion(perfil.identidad)

        registrar_entrada(
            ("Producción", "maestros:invernaderos", "leaf"),
            (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO),
            despues_de="Panel de control",
        )
        # MAE-02c (CU-46): «Alertas», del Gerente y del Agrónomo, después de «Producción». ``registrar_entrada`` no repite una
        # entrada ya registrada (``ready()`` puede correr más de una vez). Sin contador: el menú de ``core`` no los admite y el
        # punto rojo de la campana ya avisa de las no leídas.
        registrar_entrada(
            ("Alertas", "alertas:lista", "bell"), (Usuario.Rol.GERENTE, Usuario.Rol.AGRONOMO), despues_de="Producción"
        )
        # MAE-04: «Configuración» (parámetros operativos y perfil de la organización), solo del Gerente, al final del menú.
        registrar_entrada(("Configuración", "configuracion:pantalla", "gear"), (Usuario.Rol.GERENTE,), despues_de="Auditoría")
        # Datos para la verificación a mano (CLAUDE.md; docs/patrones/datos_de_verificacion.md): el cargador de ``maestros`` (MAE-02d) en el comando único de ``core``.
        from core import verificacion
        from maestros import verificacion as verificacion_de_maestros

        verificacion.registrar_cargador(
            verificacion_de_maestros.CODIGO, "Maestros: invernaderos de verificación y alerta «sin Capataz»", 5, verificacion_de_maestros.cargar
        )
