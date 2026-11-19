# Datos de Georef, 18/11/2026

Fuente: Servicio Georef de la Presidencia de la Nación (https://www.argentina.gob.ar/georef), descargado el 18/11/2026
de `https://apis.datos.gob.ar/georef/api/v2.0/`. Licencia Creative Commons Atribución 4.0 (CC BY 4.0).

Modificaciones (hechas con `maestros/datos/preparar_georef.py`): solo se conservan el id, el nombre y el id del padre;
se descartan las 105 «Entidad» que repiten el nombre de otra localidad del mismo departamento y los 2 departamentos que
quedan sin localidades (Antártida Argentina y Tolhuin).

Estos archivos no se editan: la migración `0002_cargar_georef` siempre tiene que dar lo mismo. Una actualización va en
una carpeta nueva y una migración nueva (D-39).
