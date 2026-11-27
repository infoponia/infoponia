# Inicio de «Contabilidad» (CON-03a; docs/disparadores.md, «Cuando se programe CON-03a»; D-43): la sección que `contabilidad` registra con
# `registrar_seccion_de_inicio` en `AppConfig.ready()` (``panelCon`` del prototipo, la alerta del ejercicio en cierre). La ve solo quien puede cerrar el
# ejercicio: el Contador activo y, sin Contador activo, el Gerente (D-85 punto 5; el Gerente con un Contador activo no la ve). Solo lectura.
from django.urls import reverse

from contabilidad.servicios import ejercicios, responsables
from core.extensiones import ItemDeAlerta, SeccionDeInicio
from core.models import Usuario, rol_de


def seccion_de_inicio(usuario):
    """``registrar_seccion_de_inicio``: la alerta «ejercicio en cierre» del Panel del responsable contable; ``None`` para los demás o si no hay ejercicio en cierre.

    El rol se mira primero, sin consultar nada, para que los Panel de los demás roles no paguen consultas de contabilidad.
    """
    if not getattr(usuario, "is_active", False) or rol_de(usuario) not in (Usuario.Rol.CONTADOR, Usuario.Rol.GERENTE):
        return None
    ejercicio = ejercicios.ejercicio_en_cierre()
    if ejercicio is None or not responsables.puede_registrar_asientos(usuario):
        return None
    return SeccionDeInicio(
        "contabilidad/_inicio.html", {"ejercicio": ejercicio, "numero": ejercicios.numero_de_ejercicio(ejercicio)}
    )


def items_de_campana(usuario):
    """Fuente de la campana (`core.extensiones.registrar_fuente_de_alertas`; regla 10 de CON-INI-EJE, tarea CON-05): mientras no exista ningún ejercicio, la alerta «Falta iniciar la contabilidad»
    para el responsable contable (el Contador activo o, sin Contador activo, el Gerente), con el acceso a la pantalla de inicio. Es una consulta liviana y no crea alertas en la base: el rol se
    mira primero, sin consultar nada (la campana corre en cada pantalla), después un `exists()` y, solo si falta iniciar, quién es el responsable."""
    if not getattr(usuario, "is_active", False) or rol_de(usuario) not in (Usuario.Rol.CONTADOR, Usuario.Rol.GERENTE):
        return []
    if ejercicios.contabilidad_iniciada() or not responsables.puede_registrar_asientos(usuario):
        return []
    return [
        ItemDeAlerta(
            "advertencia",
            "Falta iniciar la contabilidad",
            "Iniciá el primer ejercicio y cargá el capital inicial antes de registrar operaciones que generan asientos.",
            reverse("contabilidad:iniciar"),
            False,
        )
    ]
