# Pruebas de las vistas de la API del nodo (IOT-03, paso 6; docs/api/nodo/respuestas_y_errores.md, secciones 3 y 4; D-70, D-74). Cada fila de la tabla de códigos,
# el orden de verificación, que no hace falta sesión ni CSRF, la comunicación del nodo, el error inesperado por elemento y que el token no aparece en ningún registro.

import json
from datetime import datetime, timezone
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from iot.models import NodoCentral, Telemetria
from iot.servicios import lecturas as servicio_lecturas
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

TOKEN = "token-secreto-que-no-debe-aparecer-en-ningun-lado"
AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)
URL = "/api/iot/v1/"
VACIO = b'{"lecturas": []}'


class ApiNodoVistaTests(fabricas.ConCatalogoIot, TestCase):
    """`iot/api/vistas.py`: traducen y orquestan; el orden de verificación es el de la sección 3 del contrato."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.enterContext(mock.patch("iot.api.reloj.ahora", return_value=AHORA))
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de(TOKEN))
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/temp")
        self.cliente = Client(enforce_csrf_checks=True)

    def enviar(self, ruta, cuerpo=VACIO, token=TOKEN, tipo="application/json", metodo="post"):
        extra = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        if metodo == "get":
            return self.cliente.get(f"{URL}{ruta}", **extra)
        return self.cliente.post(f"{URL}{ruta}", data=cuerpo, content_type=tipo, **extra)

    def error(self, respuesta):
        return json.loads(respuesta.content)["error"]

    def comunicacion(self):
        self.nodo.refresh_from_db()
        return self.nodo.ultima_comunicacion

    # ---- la tabla de códigos ----

    def test_regla_200_un_pedido_correcto_responde_version_y_servidor_en(self):
        """Toda respuesta trae `version` y `servidor_en`."""
        cuerpo = json.loads(self.enviar("lecturas").content)
        self.assertEqual((cuerpo["version"], cuerpo["servidor_en"]), ("v1", "2026-11-21T17:05:00Z"))

    def test_regla_404_una_ruta_que_no_existe_no_pide_token(self):
        respuesta = self.enviar("telemetria", token=None)
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (404, "ruta_inexistente"))

    def test_regla_404_las_rutas_de_comandos_existen_desde_iot_05_y_las_demas_siguen_sin_existir(self):
        """IOT-05 sumó `comandos` y `comandos/<id>/resultado` (antes eran `ruta_inexistente`): ya no lo son; una ruta parecida, sí."""
        self.assertEqual(self.enviar("comandos", metodo="get").status_code, 200)
        self.assertNotEqual(self.error(self.enviar("comandos/1/resultado", b'{"resultado": "ejecutado"}')), "ruta_inexistente")
        self.assertEqual(self.error(self.enviar("comandos/abc/resultado", b"{}")), "ruta_inexistente")
        self.assertEqual(self.error(self.enviar("comandos/1/otra", b"{}")), "ruta_inexistente")

    def test_regla_405_un_metodo_que_no_es_el_de_la_ruta_lleva_allow(self):
        respuesta = self.enviar("lecturas", metodo="get")
        self.assertEqual((respuesta.status_code, respuesta["Allow"], self.error(respuesta)), (405, "POST", "metodo_no_permitido"))

    def test_regla_401_sin_encabezado_es_token_ausente_con_www_authenticate(self):
        respuesta = self.enviar("lecturas", token=None)
        self.assertEqual((respuesta.status_code, self.error(respuesta), respuesta["WWW-Authenticate"]), (401, "token_ausente", "Bearer"))

    def test_regla_401_un_token_con_espacios_es_token_invalido_y_no_ausente(self):
        respuesta = self.enviar("lecturas", token="con espacios")
        self.assertEqual((respuesta.status_code, self.error(respuesta), respuesta["WWW-Authenticate"]), (401, "token_invalido", "Bearer"))

    def test_regla_401_el_token_de_un_sistema_dado_de_baja_es_invalido(self):
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save(update_fields=["estado_sistema"])
        self.assertEqual(self.error(self.enviar("lecturas")), "token_invalido")

    def test_regla_429_el_pedido_121_lleva_retry_after_con_los_segundos_que_faltan(self):
        for _ in range(120):
            self.enviar("lecturas")
        respuesta = self.enviar("lecturas")
        self.assertEqual((respuesta.status_code, respuesta["Retry-After"], self.error(respuesta)), (429, "60", "demasiados_pedidos"))

    def test_regla_403_un_sistema_desconectado_responde_403_y_no_registra_la_comunicacion(self):
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        respuesta = self.enviar("lecturas")
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (403, "sistema_desconectado"))
        self.assertIsNone(self.comunicacion())

    def test_regla_413_el_cuerpo_de_mas_de_256_kb_y_las_501_lecturas(self):
        self.assertEqual(self.enviar("lecturas", b" " * 262145).status_code, 413)
        grande = json.dumps({"lecturas": [{"identificador": "a", "valor": 1}] * 501}).encode()
        respuesta = self.enviar("lecturas", grande)
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (413, "demasiados_elementos"))
        self.assertIsNone(self.comunicacion())

    def test_regla_415_un_tipo_que_no_es_json_y_un_charset_que_no_es_utf8(self):
        self.assertEqual(self.enviar("lecturas", tipo="text/plain").status_code, 415)
        self.assertEqual(self.enviar("lecturas", tipo="application/json; charset=latin-1").status_code, 415)
        self.assertEqual(self.enviar("lecturas", tipo="application/json; charset=utf-8").status_code, 200)

    def test_regla_400_json_invalido_y_mensaje_mal_formado_tampoco_registran_la_comunicacion(self):
        self.assertEqual(self.error(self.enviar("lecturas", b"no es json")), "json_invalido")
        self.assertEqual(self.error(self.enviar("lecturas", b'{"lecturas": [], "x": 1}')), "mensaje_mal_formado")
        self.assertEqual(self.error(self.enviar("modo", b'{"modo": "auto"}')), "mensaje_mal_formado")
        self.assertIsNone(self.comunicacion())

    def test_regla_un_lote_vacio_es_el_latido_y_si_registra_la_comunicacion(self):
        self.enviar("lecturas", VACIO)
        self.assertEqual(self.comunicacion(), AHORA)
        self.nodo.ultima_comunicacion = None
        self.nodo.save()
        self.enviar("estados", b'{"estados": []}')
        self.assertEqual(self.comunicacion(), AHORA)

    def test_regla_un_lote_con_todo_rechazado_responde_200_y_registra_la_comunicacion(self):
        """D-74, punto 2: mensaje aceptado = 200, aunque todas sus lecturas se rechacen."""
        respuesta = self.enviar("lecturas", b'{"lecturas": [{"identificador": "no/existe", "valor": 1}]}')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(json.loads(respuesta.content)["rechazadas"], 1)
        self.assertEqual(self.comunicacion(), AHORA)

    # ---- el orden de verificación ----

    def test_regla_orden_el_metodo_va_antes_que_el_token(self):
        self.assertEqual(self.error(self.enviar("lecturas", token=None, metodo="get")), "metodo_no_permitido")

    def test_regla_orden_el_limite_va_antes_que_el_token_invalido_y_cuenta_los_pedidos_rechazados(self):
        """D-74, punto 8: cuenta todo pedido que trae un token, también el inválido (frena a quien prueba tokens)."""
        for _ in range(120):
            self.enviar("lecturas", token="adivinando")
        self.assertEqual(self.error(self.enviar("lecturas", token="adivinando")), "demasiados_pedidos")

    def test_regla_orden_el_sistema_desconectado_va_antes_que_el_tamano_y_el_tipo(self):
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        self.assertEqual(self.error(self.enviar("lecturas", b" " * 262145, tipo="text/plain")), "sistema_desconectado")

    def test_regla_orden_el_tipo_va_antes_que_el_json(self):
        self.assertEqual(self.error(self.enviar("lecturas", b"no es json", tipo="text/plain")), "tipo_no_soportado")

    # ---- sin sesión ni CSRF ----

    def test_regla_no_hace_falta_sesion_ni_token_csrf_y_no_redirige_a_iniciar_sesion(self):
        """El cliente exige CSRF y no tiene sesión: la API igual responde 200 (nada de 302 a «Iniciar sesión» ni de 403 de CSRF)."""
        respuesta = self.enviar("lecturas")
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn("Location", respuesta)
        self.assertEqual(respuesta["Cache-Control"].split(",")[0].strip(), "max-age=0")

    # ---- errores inesperados ----

    def test_regla_un_error_inesperado_en_una_lectura_da_error_interno_en_esa_y_procesa_las_demas(self):
        """Garantías mínimas: una transacción por lectura; la que falla vuelve `error_interno` y las demás se guardan."""
        real = servicio_lecturas.registrar_lectura
        llamadas = []

        def falla_la_primera(contexto, lectura, ahora):
            llamadas.append(lectura.indice)
            if lectura.indice == 0:
                raise RuntimeError("falla simulada")
            return real(contexto, lectura, ahora)

        cuerpo = json.dumps({"lecturas": [{"identificador": "norte/temp", "valor": 20}, {"identificador": "norte/temp", "valor": 21}]}).encode()
        with mock.patch("iot.servicios.lecturas.registrar_lectura", side_effect=falla_la_primera), self.assertLogs("iot.api", "ERROR"):
            respuesta = self.enviar("lecturas", cuerpo)
        resultados = json.loads(respuesta.content)["resultados"]
        self.assertEqual((respuesta.status_code, resultados[0]["motivo"], resultados[1]["resultado"]), (200, "error_interno", "aceptada"))
        self.assertEqual(resultados[0]["detalle"], "InfoPonia no pudo procesar este elemento; los demás se procesaron.")
        self.assertEqual(Telemetria.objects.count(), 1)

    def test_regla_una_falla_inesperada_antes_de_responder_es_500_error_interno(self):
        with mock.patch("iot.servicios.lecturas.contexto_del_mensaje", side_effect=RuntimeError("falla")), self.assertLogs("iot.api", "ERROR"):
            respuesta = self.enviar("lecturas")
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (500, "error_interno"))

    # ---- modo y anuncio ----

    def test_regla_el_modo_guarda_y_responde_cambio(self):
        respuesta = json.loads(self.enviar("modo", b'{"modo": "local"}').content)
        self.assertEqual((respuesta["modo"], respuesta["cambio"]), ("local", True))
        self.assertFalse(json.loads(self.enviar("modo", b'{"modo": "local"}').content)["cambio"])

    def test_regla_el_anuncio_registra_la_comunicacion(self):
        self.enviar("anuncio", b'{"equipos": []}')
        self.assertEqual(self.comunicacion(), AHORA)

    # ---- el token nunca se guarda, se audita, se registra ni se imprime ----

    def test_regla_el_token_no_aparece_en_ningun_registro_ni_en_la_auditoria_ni_en_la_base(self):
        """Respuestas_y_errores.md, sección 1 y 4: un pedido con rechazos y una falla simulada; ni el token ni el encabezado en los registros del servidor, en
        `RegistroAuditoria` o en el cuerpo de la respuesta; la base solo guarda el resumen."""
        cuerpo = json.dumps(
            {"lecturas": [{"identificador": "no/existe", "valor": 450}, {"identificador": "norte/temp", "valor": 999}, {"identificador": "norte/temp", "valor": 7, "x": 1}]}
        ).encode()
        with self.assertLogs("iot.api", level="DEBUG") as registros:
            respuesta = self.enviar("lecturas", cuerpo)
            self.enviar("lecturas", token="otro-token-distinto")
            logging_extra = mock.patch("iot.servicios.lecturas.registrar_lectura", side_effect=RuntimeError(f"falla"))
            with logging_extra:
                self.enviar("lecturas", b'{"lecturas": [{"identificador": "norte/temp", "valor": 1}]}')
        texto = "\n".join(registros.output)
        self.assertNotIn(TOKEN, texto)
        self.assertNotIn("Bearer", texto)
        self.assertNotIn(TOKEN, respuesta.content.decode())
        self.assertGreater(RegistroAuditoria.objects.filter(accion="entrega_informacion_iot").count(), 0)
        for registro in RegistroAuditoria.objects.all():
            self.assertNotIn(TOKEN, json.dumps([registro.detalle, registro.afectados]))
            self.assertNotIn(resumen_de(TOKEN), json.dumps([registro.detalle, registro.afectados]))
        self.sistema.refresh_from_db()
        self.assertEqual(self.sistema.token_resumen, resumen_de(TOKEN))
