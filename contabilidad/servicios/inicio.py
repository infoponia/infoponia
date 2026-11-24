# Inicio de «Contabilidad» (CON-03a; docs/disparadores.md, «Cuando se programe CON-03a»; D-43): la sección que `contabilidad` registra con
# `registrar_seccion_de_inicio` en `AppConfig.ready()` (``panelCon`` del prototipo, la alerta del ejercicio en cierre). La ve solo quien puede cerrar el
# ejercicio: el Contador activo y, sin Contador activo, el Gerente (D-85 punto 5; el Gerente con un Contador activo no la ve). Solo lectura.
from contabilidad.servicios import ejercicios, responsables
from core.extensiones import SeccionDeInicio
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
