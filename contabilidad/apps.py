# Configuración de la app `contabilidad` (nivel 2 de D-37).
from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    """Registra la app `contabilidad`: el núcleo contable (CON-02, D-84) y sus pantallas (CON-03a). En ``ready()`` registra el paso diario de orden 5, la entrada
    «Contabilidad» del menú del Gerente y del Contador y la alerta del «ejercicio en cierre» en el Inicio del responsable contable (``core`` es de nivel 1 y no
    puede importar `contabilidad`: regla A4 de D-37, ``core.menu.registrar_entrada`` y ``core.extensiones.registrar_seccion_de_inicio``)."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contabilidad'

    def ready(self):
        """Registra el paso 5 «Abrir ejercicio contable» del proceso diario (D-56, CON-ABR-EJE), la entrada del menú y la sección del Inicio (CON-03a).
        Todo es idempotente: ``ready()`` puede correr más de una vez."""
        from contabilidad.servicios import ejercicios, inicio
        from core import extensiones
        from core.menu import registrar_entrada
        from core.models import Usuario
        from core.procesos import registrar_paso_diario

        registrar_paso_diario("abrir_ejercicio", "Abrir ejercicio contable", 5, ejercicios.paso_abrir_ejercicio)
        # CON-03a: «Contabilidad» (libro de gestión, ejercicios y plan de cuentas) lo ven el Contador y el Gerente (el Gerente siempre consulta, haya o no Contador).
        registrar_entrada(("Contabilidad", "contabilidad:libro", "book"), (Usuario.Rol.GERENTE, Usuario.Rol.CONTADOR), despues_de="Panel de control")
        # CON-03a (disparador «Cuando se programe CON-03a»): la alerta del ejercicio en cierre, solo para quien puede cerrarlo.
        extensiones.registrar_seccion_de_inicio(inicio.seccion_de_inicio)
