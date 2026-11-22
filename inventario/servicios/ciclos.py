# Lectura del ciclo de una variedad (INV-03, paso 3; docs/api/variedades.md, «Lectura (ciclos.py)»). Solo lee: no bloquea ni escribe.
# Las etapas salen en el orden del catálogo (``TipoEtapa.puesto_global``, regla 4 de PROD-ALT-VAR); la duración del ciclo es la suma de
# sus etapas y NUNCA se guarda (MD-70); la cosecha estimada llega al entrar en Maduración (regla 5 de PROD-ALT-VAR). Cada función hace
# UNA consulta para toda la lista de ids: nada de una consulta por variedad (contrato de docs/api/extensiones_de_inventario.md).

from collections import defaultdict, namedtuple

from django.db.models import Sum

from maestros.models import EtapaProductiva, TipoEtapa

# Una etapa del ciclo, ya con los datos de su tipo (docs/api/variedades.md).
EtapaDelCiclo = namedtuple("EtapaDelCiclo", "etapa_id tipo_id codigo nombre puesto_global duracion_dias")

MADURACION = "maduracion"


def etapas_de(variedad_ids):
    """``{variedad_id: [EtapaDelCiclo, ...]}``: las etapas de cada variedad en el orden del catálogo. Todo id pedido figura (lista
    vacía si no tiene etapas). Una consulta."""
    ids = list(variedad_ids)
    etapas = {i: [] for i in ids}
    filas = (
        EtapaProductiva.objects.filter(ciclo__variedad_id__in=ids)
        .order_by("ciclo__variedad_id", "tipo_etapa__puesto_global")
        .values_list(
            "pk",
            "tipo_etapa_id",
            "tipo_etapa__codigo",
            "tipo_etapa__nombre_etapa",
            "tipo_etapa__puesto_global",
            "duracion_estimada_dias",
            "ciclo__variedad_id",
        )
    )
    for etapa_id, tipo_id, codigo, nombre, puesto, dias, variedad_id in filas:
        etapas[variedad_id].append(EtapaDelCiclo(etapa_id, tipo_id, codigo, nombre, puesto, dias))
    return etapas


def _sumas(etapas, ids):
    """``{variedad_id: suma de duracion_estimada_dias}`` de ``etapas`` (un queryset ya filtrado), con 0 para los ids sin etapas."""
    total = defaultdict(int, {i: 0 for i in ids})
    for variedad_id, suma in etapas.values_list("ciclo__variedad_id").annotate(suma=Sum("duracion_estimada_dias")):
        total[variedad_id] = suma
    return dict(total)


def duracion_del_ciclo(variedad_ids):
    """``{variedad_id: días}``: la suma de las duraciones de sus etapas (derivada, MD-70). Una consulta."""
    ids = list(variedad_ids)
    return _sumas(EtapaProductiva.objects.filter(ciclo__variedad_id__in=ids), ids)


def dias_hasta_maduracion(variedad_ids):
    """``{variedad_id: días}``: la suma de las etapas ANTERIORES a Maduración (la Maduración misma no cuenta). La cosecha estimada
    de una siembra es ``fecha_siembra + dias_hasta_maduracion`` (regla 5 de PROD-ALT-VAR). Una consulta."""
    ids = list(variedad_ids)
    anteriores = EtapaProductiva.objects.filter(ciclo__variedad_id__in=ids).exclude(tipo_etapa__codigo=MADURACION)
    return _sumas(anteriores, ids)


def tipos_de_etapa_de(variedad):
    """Los tipos de etapa incluidos en el ciclo de ``variedad``, en orden (PRD-01 exige un sector por cada uno)."""
    return list(TipoEtapa.objects.filter(etapas__ciclo__variedad=variedad).order_by("puesto_global"))
