# Resolución de un suministro por incumplimientos (COM-RSV-SUM, COM-07b; docs/casos_de_uso/comercial/resolucion.md). En COM-07a existe solo el punto de entrada que llaman las aceptaciones de las
# solicitudes con `transaction.on_commit` (COM-EVL-DSC y COM-RSV-QJA, extensión 6b; D-69, punto 13), igual que COM-01 dejó neutras las funciones de clientes. COM-07b la completa.


def resolver_si_corresponde(suministro_id):
    """Disparador 1 de COM-RSV-SUM. **Se completa en COM-07b**: en COM-07a no hace nada. Mientras tanto, un contrato «vigente» con más incumplimientos que los tolerados queda así hasta que el paso
    diario 33 de COM-07b lo resuelva (estado de paso, D-69 punto 1; `docs/temas_abiertos.md`). Devuelve ``None``."""
    return None
