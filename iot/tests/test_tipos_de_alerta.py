# Pruebas de los 11 tipos de alerta del IoT (IOT-01, paso 2; docs/modelo/iot.md, «Tipos de alerta del IoT», MD-108 y MD-109;
# docs/api/alertas.md, sección 1): están registrados con su código, nombre, destinatario, severidad, clase y origen, y registrarlos
# dos veces no falla (``AppConfig.ready()`` puede correr más de una vez).

from django.apps import apps
from django.test import SimpleTestCase

from iot.alertas import TIPOS_DE_ALERTA_DE_IOT, registrar_tipos_de_iot
from maestros.alertas import Clase, Destinatario, Origen, tipo_de_alerta
from maestros.models import Alerta

# La tabla de docs/modelo/iot.md, escrita acá aparte de ``iot/alertas.py``: (código, nombre visible, severidad, origen).
ESPERADOS = [
    ("iot_fuera_de_umbral", "Fuera de umbral efectivo", Alerta.Severidad.ADVERTENCIA, Origen.TELEMETRIA),
    ("iot_fotoperiodo_fuera_de_umbral", "Fuera de umbral efectivo (fotoperíodo)", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_solucion_fuera_de_rango", "Solución fuera de rango", Alerta.Severidad.ADVERTENCIA, Origen.TELEMETRIA),
    ("iot_nivel_solucion_bajo", "Nivel de solución bajo", Alerta.Severidad.CRITICA, Origen.TELEMETRIA),
    ("iot_lectura_invalida", "Lectura inválida", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_sin_actividad", "Dispositivo sin actividad", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_en_falla", "Dispositivo en falla", Alerta.Severidad.CRITICA, Origen.HARDWARE),
    ("iot_comando_fallido", "Comando fallido", Alerta.Severidad.CRITICA, Origen.HARDWARE),
    ("iot_configuracion_incompatible", "Configuración incompatible", Alerta.Severidad.ADVERTENCIA, Origen.HARDWARE),
    ("iot_dispositivo_no_registrado", "Dispositivo no registrado", Alerta.Severidad.INFORMATIVA, None),
    ("iot_nodo_sin_comunicacion", "Nodo sin comunicación", Alerta.Severidad.CRITICA, None),
]


class TiposDeAlertaDeIotTests(SimpleTestCase):
    """MD-108 y MD-109: los 11 tipos de alerta del IoT los registra ``IotConfig.ready()``."""

    def test_md108_son_once(self):
        """docs/modelo/iot.md: hay 11 tipos de alerta del IoT."""
        self.assertEqual(len(ESPERADOS), 11)
        self.assertEqual(len(TIPOS_DE_ALERTA_DE_IOT), 11)

    def test_md108_estan_registrados_con_sus_datos(self):
        """Cada tipo está registrado con su código, nombre, severidad y origen (la tabla de «Tipos de alerta del IoT»)."""
        for codigo, nombre, severidad, origen in ESPERADOS:
            with self.subTest(codigo=codigo):
                tipo = tipo_de_alerta(codigo)
                self.assertEqual(tipo.nombre, nombre)
                self.assertEqual(tipo.severidad, severidad)
                self.assertEqual(tipo.origen, origen)

    def test_md109_todos_van_al_agronomo_o_al_gerente_y_son_de_estado(self):
        """MD-109: todos con ``destinatario = AGRONOMO_O_GERENTE`` y ``clase = ESTADO`` (a lo sumo una activa por invernadero,
        tipo y clave; se resuelven solas)."""
        for codigo, *_ in ESPERADOS:
            with self.subTest(codigo=codigo):
                tipo = tipo_de_alerta(codigo)
                self.assertEqual(tipo.destinatario, Destinatario.AGRONOMO_O_GERENTE)
                self.assertEqual(tipo.clase, Clase.ESTADO)

    def test_md108_las_criticas_son_cuatro(self):
        """MD-108: son críticas el nivel de solución bajo, el dispositivo en falla, el comando fallido y el nodo sin comunicación."""
        criticas = {codigo for codigo, _, severidad, _ in ESPERADOS if severidad == Alerta.Severidad.CRITICA}
        self.assertEqual(
            criticas,
            {"iot_nivel_solucion_bajo", "iot_dispositivo_en_falla", "iot_comando_fallido", "iot_nodo_sin_comunicacion"},
        )

    def test_md108_el_fotoperiodo_tiene_su_propio_codigo_con_origen_en_el_sensor(self):
        """MD-108: el fotoperíodo usa un código propio porque su origen es el sensor (hardware) y no una lectura."""
        self.assertEqual(tipo_de_alerta("iot_fotoperiodo_fuera_de_umbral").origen, Origen.HARDWARE)
        self.assertEqual(tipo_de_alerta("iot_fuera_de_umbral").origen, Origen.TELEMETRIA)

    def test_los_codigos_llevan_el_prefijo_de_la_app_y_caben_en_50_caracteres(self):
        """docs/api/alertas.md, sección 1: código único, de hasta 50 caracteres y con el prefijo de la app."""
        for codigo, *_ in ESPERADOS:
            with self.subTest(codigo=codigo):
                self.assertTrue(codigo.startswith("iot_"))
                self.assertLessEqual(len(codigo), 50)

    def test_registrar_dos_veces_no_falla_ni_cambia_nada(self):
        """docs/api/alertas.md: registrar dos veces la misma definición no hace nada (``ready()`` puede correr más de una vez)."""
        antes = {codigo: tipo_de_alerta(codigo) for codigo, *_ in ESPERADOS}
        registrar_tipos_de_iot()
        apps.get_app_config("iot").ready()
        for codigo, tipo in antes.items():
            with self.subTest(codigo=codigo):
                self.assertEqual(tipo_de_alerta(codigo), tipo)
