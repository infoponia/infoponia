# Pruebas de las vistas de comandos de la API del nodo (IOT-05, paso 5; docs/api/nodo/mensajes.md, secciones 5 y 6; respuestas_y_errores.md, secciones 3 y 4b; D-77, D-78).
# El orden de verificación es el de la sección 3: el retiro (un GET sin cuerpo) salta las verificaciones 7 a 11; el resultado verifica la forma (400) antes de buscar
# el comando (404, verificación 12). Los ejemplos del contrato están en `test_api_ejemplos.py`.

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.cache import cache
from django.test import Client, TestCase

from core.enlaces import resumen_de
from core.tests.fabricas import crear_gerente
from iot.models import Comando, NodoCentral, RegistroComando
from iot.tests import fabricas
from maestros.tests.fabricas import crear_agronomo, crear_invernadero

TOKEN = "token-secreto-que-no-debe-aparecer-en-ningun-lado"
AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)
URL = "/api/iot/v1/"


class ApiComandosTests(fabricas.ConCatalogoIot, TestCase):
    """`GET comandos` y `POST comandos/<id>/resultado`."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.enterContext(mock.patch("iot.api.reloj.ahora", return_value=AHORA))
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte, token_resumen=resumen_de(TOKEN))
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.tipo = fabricas.tipo_actuador("Extractor")
        self.actuador = fabricas.actuador(self.sistema, self.tipo, "norte/extractor")
        self.encender = self.tipo.acciones.order_by("id").first()
        self.comando = fabricas.comando(self.actuador, self.encender)
        self.cliente = Client(enforce_csrf_checks=True)

    # ---- ayudas ----

    def retirar(self, token=TOKEN, metodo="get", **extra):
        cabeceras = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        if metodo == "get":
            return self.cliente.get(f"{URL}comandos", **cabeceras, **extra)
        return self.cliente.post(f"{URL}comandos", data=b"{}", content_type="application/json", **cabeceras)

    def resultado(self, cuerpo, comando_id=None, token=TOKEN, tipo="application/json"):
        cabeceras = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode()
        return self.cliente.post(f"{URL}comandos/{comando_id or self.comando.pk}/resultado", data=datos, content_type=tipo, **cabeceras)

    def retirado(self):
        """El comando ya fue entregado una vez (intento 1, hace 10 s)."""
        Comando.objects.filter(pk=self.comando.pk).update(cantidad_intentos=1, ultimo_intento_en=AHORA - timedelta(seconds=10))

    def json(self, respuesta):
        return json.loads(respuesta.content)

    def error(self, respuesta):
        return self.json(respuesta)["error"]

    def comunicacion(self):
        self.nodo.refresh_from_db()
        return self.nodo.ultima_comunicacion

    # ---- el retiro ----

    def test_retiro_un_405_con_allow_get_si_se_manda_otro_metodo(self):
        """Verificación 2: el retiro solo acepta GET, con el encabezado `Allow: GET` y el texto del contrato."""
        respuesta = self.retirar(metodo="post")
        self.assertEqual((respuesta.status_code, respuesta["Allow"], self.error(respuesta)), (405, "GET", "metodo_no_permitido"))
        self.assertEqual(self.json(respuesta)["detalle"], "Esta ruta solo acepta GET.")

    def test_resultado_un_405_con_allow_post_si_se_manda_un_get(self):
        """Verificación 2: el resultado solo acepta POST."""
        respuesta = self.cliente.get(f"{URL}comandos/{self.comando.pk}/resultado")
        self.assertEqual((respuesta.status_code, respuesta["Allow"], self.error(respuesta)), (405, "POST", "metodo_no_permitido"))

    def test_retiro_no_lleva_cuerpo_ni_content_type_ni_pide_sesion_ni_csrf(self):
        """El retiro es un GET sin cuerpo: salta las verificaciones 7 a 11 (no exige `Content-Type`) y no usa sesión ni CSRF."""
        respuesta = self.retirar()
        self.assertEqual(respuesta.status_code, 200)
        cuerpo = self.json(respuesta)
        self.assertEqual((cuerpo["version"], cuerpo["servidor_en"], cuerpo["modo"]), ("v1", "2026-11-21T17:05:00Z", "remoto"))

    def test_retiro_sin_token_y_con_token_invalido_es_401(self):
        """Verificaciones 3 y 5, también en el retiro."""
        self.assertEqual(self.error(self.retirar(token=None)), "token_ausente")
        self.assertEqual(self.error(self.retirar(token="otro-token")), "token_invalido")

    def test_retiro_con_el_sistema_desconectado_es_403_y_no_registra_nada(self):
        """Verificación 6 (extensión *a): sin entregar comandos ni registrar la comunicación."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        respuesta = self.retirar()
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (403, "sistema_desconectado"))
        self.assertIsNone(self.comunicacion())
        self.assertEqual(Comando.objects.get(pk=self.comando.pk).cantidad_intentos, 0)

    def test_retiro_cuenta_como_comunicacion_del_nodo(self):
        """Postcondición a: cada retiro actualiza la última comunicación (un nodo que consulta cada 5 s no necesita el latido, D-77 punto 1)."""
        self.assertIsNone(self.comunicacion())
        self.retirar()
        self.assertEqual(self.comunicacion(), AHORA)

    def test_retiro_cuenta_en_el_limite_de_pedidos_por_minuto(self):
        """El contador de pedidos cuenta todo pedido con token, también el retiro (D-74, punto 8): el 121 del minuto es 429."""
        for _ in range(120):
            self.retirar()
        respuesta = self.retirar()
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (429, "demasiados_pedidos"))

    def test_retiro_entrega_el_comando_con_los_campos_del_contrato(self):
        """`mensajes.md`, sección 5: id, identificador, comando, valor, intento y espera."""
        entrega = self.json(self.retirar())["comandos"]
        self.assertEqual(
            entrega, [{"id": self.comando.pk, "identificador": "norte/extractor", "comando": "ENCENDER", "valor": None, "intento": 1, "espera_segundos": 60}]
        )

    def test_retiro_un_error_inesperado_es_500_error_interno_sin_token(self):
        """Una falla inesperada es 500 `error_interno` y no se escribe el token en el registro."""
        with mock.patch("iot.servicios.comandos.retirar_comandos", side_effect=RuntimeError("falla")), self.assertLogs("iot.api", "ERROR") as registro:
            respuesta = self.retirar()
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (500, "error_interno"))
        self.assertNotIn(TOKEN, "\n".join(registro.output))

    # ---- el resultado: 404 ----

    def test_resultado_404_comando_inexistente_para_un_id_que_no_existe(self):
        """Verificación 12 y extensión 4e: 404, con el texto del contrato y sin registrar la comunicación."""
        respuesta = self.resultado({"resultado": "ejecutado"}, comando_id=99999)
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (404, "comando_inexistente"))
        self.assertEqual(self.json(respuesta)["detalle"], "El comando 99999 no existe o no es de un actuador de este nodo.")
        self.assertIsNone(self.comunicacion())

    def test_resultado_404_comando_inexistente_para_el_comando_de_otro_sistema(self):
        """Extensión 4e: el comando es de un actuador de otro sistema IoT."""
        sur = crear_invernadero("Sur", agronomo=crear_agronomo("otro@infoponia.com"))
        ajeno = fabricas.comando(fabricas.actuador(fabricas.sistema(sur), self.tipo, "sur/extractor"), self.encender, cantidad_intentos=1, ultimo_intento_en=AHORA)
        respuesta = self.resultado({"resultado": "ejecutado"}, comando_id=ajeno.pk)
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (404, "comando_inexistente"))
        ajeno.refresh_from_db()
        self.assertEqual(ajeno.estado_comando, "pendiente")

    def test_resultado_404_comando_inexistente_para_uno_nunca_entregado_y_si_registra_la_comunicacion(self):
        """D-78, punto 12: pendiente con 0 intentos. A diferencia de 4e, ya se bloqueó y se registró la comunicación del nodo."""
        respuesta = self.resultado({"resultado": "ejecutado"})
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (404, "comando_inexistente"))
        self.assertEqual(self.comunicacion(), AHORA)
        self.assertEqual(Comando.objects.get(pk=self.comando.pk).estado_comando, "pendiente")

    # ---- el resultado: 400 por cada campo ----

    def test_resultado_400_por_cada_campo(self):
        """Verificación 10: un `resultado`, `detalle`, `estado` o fecha inválidos, o un campo de más, rechazan el mensaje entero con su `campo`."""
        self.retirado()
        casos = [
            ({"resultado": "falló"}, "resultado", "tiene que ser «ejecutado», «fallo» o «rechazado»"),
            ({"resultado": 5}, "resultado", "tiene que ser «ejecutado», «fallo» o «rechazado»"),
            ({}, "resultado", "falta"),
            ({"resultado": "ejecutado", "otro": 1}, "otro", "no existe en este mensaje"),
            ({"resultado": "fallo", "detalle": "x" * 301}, "detalle", "tiene más de 300 caracteres"),
            ({"resultado": "fallo", "detalle": 5}, "detalle", "tiene que ser un texto"),
            ({"resultado": "ejecutado", "estado": "volando"}, "estado", "no es un estado operativo de un actuador"),
            ({"resultado": "ejecutado", "estado": "nivel:abc"}, "estado", "no es un estado operativo de un actuador"),
            ({"resultado": "ejecutado", "estado": 7}, "estado", "no es un estado operativo de un actuador"),
            ({"resultado": "ejecutado", "informado_en": "ayer"}, "informado_en", "tiene que ser una fecha ISO 8601 con zona horaria"),
            ({"resultado": "ejecutado", "informado_en": "2026-11-21T14:00:00"}, "informado_en", "tiene que ser una fecha ISO 8601 con zona horaria"),
            ({"resultado": "ejecutado", "informado_en": "2026-11-21T14:30:00-03:00"}, "informado_en", "es más de 5 minutos posterior a la hora de InfoPonia"),
        ]
        for cuerpo, campo, razon in casos:
            respuesta = self.resultado(cuerpo)
            datos = self.json(respuesta)
            self.assertEqual((respuesta.status_code, datos["error"], datos["campo"], datos["detalle"]), (400, "mensaje_mal_formado", campo, f"{campo}: {razon}."), cuerpo)
        self.assertEqual(Comando.objects.get(pk=self.comando.pk).estado_comando, "pendiente")

    def test_resultado_un_detalle_de_exactamente_300_y_los_campos_opcionales_se_aceptan(self):
        """El límite es inclusive, y `detalle`, `estado` e `informado_en` son optativos."""
        self.retirado()
        respuesta = self.resultado({"resultado": "ejecutado", "detalle": "x" * 300, "estado": "encendido", "informado_en": "2026-11-21T14:04:58-03:00"})
        self.assertEqual((respuesta.status_code, self.json(respuesta)["resultado"]), (200, "aceptado"))

    def test_resultado_la_verificacion_de_la_forma_va_antes_que_la_del_comando(self):
        """Orden de la sección 3: un mensaje mal formado para un comando que no existe es 400, no 404."""
        respuesta = self.resultado({"resultado": "falló"}, comando_id=99999)
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (400, "mensaje_mal_formado"))

    def test_resultado_415_y_400_json_invalido_como_el_resto_de_la_api(self):
        """Verificaciones 8 y 9."""
        self.retirado()
        self.assertEqual(self.error(self.resultado(b'{"resultado": "ejecutado"}', tipo="text/plain")), "tipo_no_soportado")
        self.assertEqual(self.error(self.resultado(b"[1]")), "json_invalido")
        self.assertEqual(self.error(self.resultado(b'{"resultado": NaN}')), "json_invalido")

    # ---- el resultado: 200 ----

    def test_resultado_aceptado_ejecutado(self):
        """`mensajes.md`, sección 6: `aceptado` con el id y el estado del comando."""
        self.retirado()
        cuerpo = self.json(self.resultado({"resultado": "ejecutado", "detalle": "Listo", "estado": "encendido"}))
        self.assertEqual((cuerpo["resultado"], cuerpo["comando"], cuerpo["estado_comando"]), ("aceptado", self.comando.pk, "ejecutado"))
        self.assertEqual(RegistroComando.objects.filter(comando=self.comando, resultado="ejecutado").count(), 1)

    def test_resultado_ya_resuelto_responde_200_y_deja_constancia_en_el_registro_tecnico(self):
        """Extensión 4d y D-77 punto 2: 200 `ya_resuelto` con el estado final; el registro técnico (`iot.api`) lo anota y no cambia nada."""
        self.retirado()
        self.resultado({"resultado": "ejecutado"})
        antes = RegistroComando.objects.count()
        with self.assertLogs("iot.api", logging.WARNING) as registro:
            cuerpo = self.json(self.resultado({"resultado": "ejecutado"}))
        self.assertEqual((cuerpo["resultado"], cuerpo["estado_comando"]), ("ya_resuelto", "ejecutado"))
        self.assertIn("ya_resuelto", "\n".join(registro.output))
        self.assertNotIn(TOKEN, "\n".join(registro.output))
        self.assertEqual(RegistroComando.objects.count(), antes)

    def test_resultado_comando_inexistente_tambien_queda_en_el_registro_tecnico(self):
        """Extensión 4e: «deja constancia en el registro técnico de errores»."""
        with self.assertLogs("iot.api", logging.WARNING) as registro:
            self.resultado({"resultado": "ejecutado"}, comando_id=99999)
        self.assertIn("comando_inexistente", "\n".join(registro.output))

    def test_resultado_con_el_sistema_desconectado_es_403(self):
        """Verificación 6."""
        self.retirado()
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save()
        respuesta = self.resultado({"resultado": "ejecutado"})
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (403, "sistema_desconectado"))
        self.assertEqual(Comando.objects.get(pk=self.comando.pk).estado_comando, "pendiente")

    def test_resultado_cuenta_como_comunicacion_y_no_necesita_sesion_ni_csrf(self):
        """El resultado es una comunicación del nodo; el cliente exige CSRF y no hay sesión: igual responde."""
        self.retirado()
        self.assertIsNone(self.comunicacion())
        self.assertEqual(self.resultado({"resultado": "fallo", "detalle": "x"}).status_code, 200)
        self.assertEqual(self.comunicacion(), AHORA)

    def test_resultado_un_error_inesperado_es_500_error_interno(self):
        self.retirado()
        with mock.patch("iot.servicios.comandos.registrar_resultado", side_effect=RuntimeError("falla")), self.assertLogs("iot.api", "ERROR"):
            respuesta = self.resultado({"resultado": "ejecutado"})
        self.assertEqual((respuesta.status_code, self.error(respuesta)), (500, "error_interno"))
