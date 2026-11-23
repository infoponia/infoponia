# Pruebas de la API del nodo con los ejemplos del contrato (IOT-03, paso 6; docs/api/nodo/ejemplos/README.md; D-70, «Consecuencias»). Cada `*.pedido.json` se
# manda con el escenario del README y su respuesta se compara con el `*.respuesta.json` CAMPO POR CAMPO, salvo `servidor_en`. Los que solo tienen respuesta
# (sin token, token inválido, desconectado, el pedido 121, 262.145 bytes, 501 lecturas, `text/plain`, `GET`, ruta inexistente) se arman acá. Los archivos se leen
# desde `settings.BASE_DIR / "docs/api/nodo/ejemplos"`: si cambia un ejemplo, la prueba lo sigue. Los de comandos (`comando*`) son de IOT-05.

import json
from datetime import datetime, timezone
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase

from core.enlaces import resumen_de
from core.tests.fabricas import crear_gerente
from iot.models import TipoActuador
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector

EJEMPLOS = settings.BASE_DIR / "docs/api/nodo/ejemplos"
TOKEN = "token-de-ejemplo-no-es-secreto"
AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)  # «Hora de InfoPonia» del escenario
URL = "/api/iot/v1/"


def _respuesta_de(nombre):
    """El `*.respuesta.json` del ejemplo, sin `servidor_en` (la hora de InfoPonia, que cambia)."""
    esperada = json.loads((EJEMPLOS / f"{nombre}.respuesta.json").read_text(encoding="utf-8"))
    esperada.pop("servidor_en")
    return esperada


class ApiEjemplosTests(fabricas.ConCatalogoIot, TestCase):
    """El escenario de `docs/api/nodo/ejemplos/README.md` y cada ejemplo, contra la API real (cliente de Django, sin sesión ni CSRF)."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.enterContext(mock.patch("iot.api.reloj.ahora", return_value=AHORA))
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(
            self.norte, token_resumen=resumen_de(TOKEN), temp_solucion_min="18.0", temp_solucion_max="24.0"
        )
        sector = crear_sector(self.norte, "Sector A")
        fabricas.sensor(self.sistema, "norte/sectorA/temperatura", "temperatura", sector=sector, valor_calibracion_min=-10, valor_calibracion_max=60)
        fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad", sector=sector, valor_calibracion_min=0, valor_calibracion_max=100)
        fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", sector=sector, valor_calibracion_min=0, valor_calibracion_max=100000)
        fabricas.sensor(self.sistema, "norte/tanque1/temp-solucion", "temperatura_solucion", valor_calibracion_min=0, valor_calibracion_max=50)
        fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        fabricas.actuador(self.sistema, TipoActuador.objects.get(nombre_actuador="Ventilador"), "norte/sectorA/ventilador", sector=sector)
        fabricas.actuador(self.sistema, TipoActuador.objects.get(nombre_actuador="Ventana"), "norte/sectorA/ventana", sector=sector)
        fabricas.sensor(self.sistema, "norte/sectorA/temp-vieja", "temperatura", estado="inactivo", sector=sector, valor_calibracion_min=-10, valor_calibracion_max=60)
        self.cliente = Client()

    # ---- ayudas ----

    def enviar(self, ruta, cuerpo=b"", token=TOKEN, tipo="application/json", metodo="post"):
        extra = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        enviar = getattr(self.cliente, metodo)
        if metodo == "post":
            return enviar(f"{URL}{ruta}", data=cuerpo, content_type=tipo, **extra)
        return enviar(f"{URL}{ruta}", **extra)

    def pedido(self, nombre, ruta):
        return self.enviar(ruta, (EJEMPLOS / f"{nombre}.pedido.json").read_bytes())

    def comparar(self, respuesta, nombre, codigo=200):
        self.assertEqual(respuesta.status_code, codigo)
        cuerpo = json.loads(respuesta.content)
        self.assertEqual(cuerpo.pop("servidor_en"), "2026-11-21T17:05:00Z")
        self.assertEqual(cuerpo, _respuesta_de(nombre))

    # ---- los que tienen pedido y respuesta ----

    def test_ejemplo_lecturas_aceptadas(self):
        self.comparar(self.pedido("lecturas_aceptadas", "lecturas"), "lecturas_aceptadas")

    def test_ejemplo_lecturas_reenviadas_la_segunda_respuesta_son_todas_duplicadas(self):
        self.pedido("lecturas_aceptadas", "lecturas")
        self.comparar(self.pedido("lecturas_aceptadas", "lecturas"), "lecturas_reenviadas")

    def test_ejemplo_lecturas_latido(self):
        self.comparar(self.pedido("lecturas_latido", "lecturas"), "lecturas_latido")

    def test_ejemplo_lecturas_con_rechazos(self):
        self.comparar(self.pedido("lecturas_con_rechazos", "lecturas"), "lecturas_con_rechazos")

    def test_ejemplo_estados(self):
        self.comparar(self.pedido("estados", "estados"), "estados")

    def test_ejemplo_modo_local(self):
        self.comparar(self.pedido("modo_local", "modo"), "modo_local")

    def test_ejemplo_modo_remoto(self):
        self.comparar(self.pedido("modo_remoto", "modo"), "modo_remoto")

    def test_ejemplo_anuncio(self):
        self.comparar(self.pedido("anuncio", "anuncio"), "anuncio")

    def test_ejemplo_anuncio_mal_formado(self):
        self.comparar(self.pedido("anuncio_mal_formado", "anuncio"), "anuncio_mal_formado", 400)

    def test_ejemplo_error_mensaje_mal_formado(self):
        self.comparar(self.pedido("error_mensaje_mal_formado", "lecturas"), "error_mensaje_mal_formado", 400)

    def test_ejemplo_error_json_invalido(self):
        pedido = (EJEMPLOS / "error_json_invalido.pedido.txt").read_bytes()
        self.comparar(self.enviar("lecturas", pedido), "error_json_invalido", 400)

    # ---- los que solo tienen respuesta ----

    def test_ejemplo_error_token_ausente(self):
        respuesta = self.enviar("lecturas", b'{"lecturas": []}', token=None)
        self.comparar(respuesta, "error_token_ausente", 401)
        self.assertEqual(respuesta["WWW-Authenticate"], "Bearer")

    def test_ejemplo_error_token_invalido(self):
        respuesta = self.enviar("lecturas", b'{"lecturas": []}', token="otro-token")
        self.comparar(respuesta, "error_token_invalido", 401)
        self.assertEqual(respuesta["WWW-Authenticate"], "Bearer")

    def test_ejemplo_error_sistema_desconectado_no_registra_la_comunicacion(self):
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        self.comparar(self.enviar("lecturas", b'{"lecturas": []}'), "error_sistema_desconectado", 403)
        self.assertIsNone(self.sistema.equipos.get(clase="nodo").nodocentral.ultima_comunicacion)

    def test_ejemplo_error_demasiados_pedidos_el_121(self):
        for _ in range(120):
            self.assertEqual(self.enviar("lecturas", b'{"lecturas": []}').status_code, 200)
        respuesta = self.enviar("lecturas", b'{"lecturas": []}')
        self.comparar(respuesta, "error_demasiados_pedidos", 429)
        self.assertEqual(respuesta["Retry-After"], "60")

    def test_ejemplo_error_mensaje_demasiado_grande(self):
        self.comparar(self.enviar("lecturas", b" " * 262145), "error_mensaje_demasiado_grande", 413)

    def test_ejemplo_error_demasiados_elementos(self):
        lecturas = [{"identificador": "norte/sectorA/temperatura", "valor": 20}] * 501
        self.comparar(self.enviar("lecturas", json.dumps({"lecturas": lecturas}).encode()), "error_demasiados_elementos", 413)

    def test_ejemplo_error_tipo_no_soportado(self):
        self.comparar(self.enviar("lecturas", b'{"lecturas": []}', tipo="text/plain"), "error_tipo_no_soportado", 415)

    def test_ejemplo_error_metodo_no_permitido(self):
        respuesta = self.enviar("lecturas", metodo="get")
        self.comparar(respuesta, "error_metodo_no_permitido", 405)
        self.assertEqual(respuesta["Allow"], "POST")

    def test_ejemplo_error_ruta_inexistente(self):
        self.comparar(self.cliente.post(f"{URL}telemetria", data=b"{}", content_type="application/json"), "error_ruta_inexistente", 404)
