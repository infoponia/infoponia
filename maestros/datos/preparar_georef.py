# Prepara los CSV de Georef que carga la migración 0002 de maestros (MAE-01, decisión 2 de D-39).
# Se corre a mano, una vez por versión de datos: baja provincias, departamentos y localidades del Servicio Georef
# (https://apis.datos.gob.ar/georef/api/v2.0/, licencia CC BY 4.0), deja solo id, nombre y padre, y descarta:
#   - las «Entidad» que repiten el nombre de otra localidad del mismo departamento (105 filas);
#   - los departamentos que quedan sin ninguna localidad (Antártida Argentina y Tolhuin).
# Uso: python maestros/datos/preparar_georef.py maestros/datos/georef_AAAA-MM-DD
# Usa solo la biblioteca estándar. Los CSV generados no se modifican: una actualización va en una carpeta nueva.

import csv
import io
import sys
import urllib.request
from pathlib import Path

URL = "https://apis.datos.gob.ar/georef/api/v2.0/"


def bajar(recurso):
    """Descarga ``recurso`` (provincias, departamentos o localidades) como lista de diccionarios."""
    with urllib.request.urlopen(f"{URL}{recurso}.csv", timeout=120) as respuesta:
        return list(csv.DictReader(io.TextIOWrapper(respuesta, encoding="utf-8")))


def escribir(ruta, columnas, filas):
    """Escribe un CSV UTF-8 con ``columnas`` y ``filas`` (listas), ordenadas por id."""
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(columnas)
        escritor.writerows(sorted(filas, key=lambda f: f[0]))


def main(carpeta):
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    provincias, departamentos, localidades = (bajar(r) for r in ("provincias", "departamentos", "localidades"))
    # Una «Entidad» se descarta si otra localidad que no es entidad, del mismo departamento, tiene su mismo nombre.
    reales = {(x["departamento_id"], x["nombre"].strip().lower()) for x in localidades if x["categoria"] != "Entidad"}
    quedan = [
        x
        for x in localidades
        if not (x["categoria"] == "Entidad" and (x["departamento_id"], x["nombre"].strip().lower()) in reales)
    ]
    con_localidades = {x["departamento_id"] for x in quedan}
    departamentos = [x for x in departamentos if x["id"] in con_localidades]
    escribir(carpeta / "provincias.csv", ["id_georef", "nombre"], [[x["id"], x["nombre"].strip()] for x in provincias])
    escribir(
        carpeta / "departamentos.csv",
        ["id_georef", "nombre", "provincia_id_georef"],
        [[x["id"], x["nombre"].strip(), x["provincia_id"]] for x in departamentos],
    )
    escribir(
        carpeta / "localidades.csv",
        ["id_georef", "nombre", "departamento_id_georef"],
        [[x["id"], x["nombre"].strip(), x["departamento_id"]] for x in quedan],
    )
    print(len(provincias), "provincias,", len(departamentos), "departamentos,", len(quedan), "localidades")


if __name__ == "__main__":
    main(sys.argv[1])
