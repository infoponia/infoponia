# Costo de un lote de plantas (PRD-01): costo por planta y costo de las plantas perdidas, con el promedio ponderado móvil de MD-79.
# PRD-03 suma `repartir_en_centavos`: el reparto del costo de una aplicación de insumos entre los lotes del alcance (D-51 punto 4).
# Fuente: docs/patrones/costo_del_lote.md y D-50 punto 5. Todo con Decimal y ROUND_HALF_UP, nunca float. Estas funciones NO escriben:
# quien baja el costo del lote (la merma, PRD-02 y PRD-03) lo hace con el lote bloqueado y dentro de su transacción.

from decimal import ROUND_HALF_UP, Decimal

CENTAVO = Decimal("0.01")


def redondear_monto(valor):
    """Redondea un monto a 2 decimales con ROUND_HALF_UP (docs/patrones/costo_del_lote.md)."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def costo_por_planta(lote):
    """Costo acumulado ÷ cantidad actual, a 2 decimales, solo para mostrar; `None` si el lote no tiene plantas."""
    if lote.cantidad_actual <= 0:
        return None
    return redondear_monto(Decimal(lote.costo_acumulado) / lote.cantidad_actual)


def costo_de_la_merma(lote, cantidad):
    """Lo que cuestan `cantidad` plantas perdidas de `lote` (con `0 < cantidad <= cantidad_actual`; si no, `ValueError`).

    Si se pierde el lote entero, es el costo acumulado completo (así no sobran ni faltan centavos); si no,
    `redondear(K × n ÷ c)`. Las plantas que quedan conservan su costo unitario (salvo el redondeo de a lo sumo un centavo)."""
    if not 0 < cantidad <= lote.cantidad_actual:
        raise ValueError(f"La merma ({cantidad}) debe ser mayor que 0 y no superar las plantas del lote ({lote.cantidad_actual}).")
    costo = Decimal(lote.costo_acumulado)
    if cantidad == lote.cantidad_actual:
        return redondear_monto(costo)
    return redondear_monto(costo * cantidad / lote.cantidad_actual)


def repartir_en_centavos(monto, plantas_por_lote):
    """Reparte `monto` (un consumo de aplicación, 2 decimales) entre los lotes de plantas del alcance y devuelve `{lote_id: parte}`.

    `plantas_por_lote` es `{lote_id: plantas del lote en los sectores del alcance}`. Método del resto mayor, en centavos enteros
    (docs/patrones/costo_del_lote.md, «Reparto del costo de una aplicación de insumos entre lotes»; D-51 punto 4; regla «Reparto del costo
    entre los lotes de plantas» de PROD-REG-APL):

    1. cada lote recibe la parte entera de su cuota `centavos × plantas ÷ total de plantas`;
    2. los centavos que sobran (siempre menos que la cantidad de lotes) se asignan de a uno a los lotes con mayor resto; si empatan, al
       lote con más plantas y, si sigue el empate, al de menor id.

    La suma de las partes es exactamente `monto` y nunca hay una parte negativa. Los lotes con 0 plantas no reciben ni figuran; sin lotes
    con plantas devuelve `{}` (el consumo va a gasto). Un lote puede recibir 0,00: quien llama no crea la imputación de cero.
    Función pura: no consulta ni escribe. Montos o plantas negativos son un error de uso (`ValueError`).
    """
    monto = Decimal(monto)
    if monto < 0 or any(plantas < 0 for plantas in plantas_por_lote.values()):
        raise ValueError("El monto y las plantas de cada lote no pueden ser negativos.")
    con_plantas = {lote_id: plantas for lote_id, plantas in plantas_por_lote.items() if plantas > 0}
    total = sum(con_plantas.values())
    if not total:
        return {}
    centavos = int(redondear_monto(monto) * 100)
    partes, restos = {}, {}
    for lote_id, plantas in con_plantas.items():
        partes[lote_id], restos[lote_id] = divmod(centavos * plantas, total)  # los restos comparten denominador: se comparan exactos
    sobran = centavos - sum(partes.values())
    # Mayor resto, después más plantas, después menor id (el desempate del caso de uso).
    for lote_id in sorted(con_plantas, key=lambda i: (-restos[i], -con_plantas[i], i))[:sobran]:
        partes[lote_id] += 1
    return {lote_id: (Decimal(partes[lote_id]) / 100).quantize(CENTAVO) for lote_id in sorted(partes)}
