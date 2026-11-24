# Configuración de la app `contabilidad` (nivel 2 de D-37).
from django.apps import AppConfig


class ContabilidadConfig(AppConfig):
    """Registra la app `contabilidad`: el núcleo contable (CON-02, D-84). En ``ready()`` registra el paso diario de orden 5."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contabilidad'

    def ready(self):
        """Registra el paso 5 «Abrir ejercicio contable» del proceso diario (D-56, CON-ABR-EJE). ``registrar_paso_diario`` es idempotente."""
        from contabilidad.servicios import ejercicios
        from core.procesos import registrar_paso_diario

        registrar_paso_diario("abrir_ejercicio", "Abrir ejercicio contable", 5, ejercicios.paso_abrir_ejercicio)
