# Constantes del contrato con el nodo central que NO son tablas (docs/modelo/iot.md, «Catálogo de capacidades»; IOT-ALT-TAC,
# reglas 7, 8 y 10; D-72, punto 3). Cambian solo con una versión nueva de la API del nodo (D-70), nunca desde una pantalla.

# IOT-ALT-TAC, regla 10: lista cerrada de unidades de cada comando con valor, como pares (valor guardado, texto visible).
# Se evita el texto libre para que la misma unidad no se escriba de maneras distintas.
UNIDADES_POR_COMANDO = {
    "FIJAR_NIVEL": [
        ("%", "% (porcentaje de la potencia)"),
        ("rpm", "rpm (vueltas por minuto)"),
        ("L/min", "L/min (litros por minuto)"),
    ],
    "FIJAR_POSICION": [
        ("%", "% (porcentaje de apertura)"),
        ("°", "° (grados)"),
        ("cm", "cm (centímetros)"),
    ],
}

# D-80 (regla 4 de IOT-ALT-TAC): el rango de una acción depende de su unidad. «%» va de 0 a 100; «rpm», «L/min» y «cm» no tienen tope pero
# su mínimo es 0 o más; «°» no tiene límite fijo.
UNIDAD_PORCENTAJE = "%"
RANGO_DEL_PORCENTAJE = (0, 100)
UNIDADES_CON_MINIMO_CERO = ("rpm", "L/min", "cm")

# docs/modelo/iot.md, «Catálogo de capacidades»: el estado que deja cada comando en el actuador (extensión 6c de IOT-EMT-CMD,
# «ya está en ese estado»). Los comandos con valor dejan ``nivel:<n>`` o ``posicion:<n>``: el ``{valor}`` se completa con
# ``estado_que_deja``. El contrato de la API fija los mismos textos.
ESTADO_QUE_DEJA = {
    "ENCENDER": "encendido",
    "APAGAR": "apagado",
    "ABRIR": "abierto",
    "CERRAR": "cerrado",
    "FIJAR_NIVEL": "nivel:{valor}",
    "FIJAR_POSICION": "posicion:{valor}",
}


def estado_que_deja(comando, valor=None):
    """El estado que queda en el actuador después de ejecutar ``comando`` (su código), con ``valor`` si el comando lo lleva."""
    return ESTADO_QUE_DEJA[comando].format(valor=valor)


# `docs/casos_de_uso/iot/sistema_iot.md`, «IOT-REG-SIS»: la guía de integración del nodo es el README de `docs/api/nodo/`; el enlace
# apunta a su copia pública en GitHub. Hasta que exista el archivo (lote I2a), el enlace lleva a una página vacía: es esperado.
URL_GUIA_DEL_NODO = "https://github.com/infoponia/infoponia/blob/main/docs/api/nodo/README.md"
