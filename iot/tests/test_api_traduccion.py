# Pruebas del contrato en código (IOT-03, paso 1): `iot/api/traduccion.py` (la forma de cada mensaje), `limites.py` (el contador de pedidos),
# `respuestas.py` y `autenticacion.py`. Fuente: docs/api/nodo/mensajes.md y respuestas_y_errores.md; D-74 (puntos 5 y 7) y D-75 (punto 5).
# No usan la base: la traducción no la consulta (D-70, punto 4).

from datetime import datetime, timezone

from django.core.cache import cache
from django.test import SimpleTestCase

from core.enlaces import resumen_de
from iot.api import autenticacion, limites, respuestas, traduccion
from iot.api.traduccion import ElementoMalFormado, EquipoRecibido, JsonInvalido, LecturaRecibida, MensajeMalFormado

AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)


class ApiTraduccionLecturasTests(SimpleTestCase):
    """`POST lecturas`: la envoltura y cada elemento (mensajes.md, sección 1; respuestas_y_errores.md, sección 4)."""

    def test_regla_json_nan_es_json_invalido(self):
        """D-74, punto 7: `NaN` e `Infinity` no son JSON válido (400 `json_invalido`)."""
        for cuerpo in (b'{"lecturas": [{"identificador": "a", "valor": NaN}]}', b'{"lecturas": [{"identificador": "a", "valor": Infinity}]}'):
            with self.subTest(cuerpo=cuerpo), self.assertRaises(JsonInvalido):
                traduccion.leer_objeto(cuerpo)

    def test_regla_json_que_no_es_un_objeto_es_json_invalido(self):
        """Verificación 9: el cuerpo es JSON válido, en UTF-8 y un objeto: una lista, un texto o bytes que no son UTF-8 no lo son."""
        for cuerpo in (b"[]", b'"hola"', b"no es json", b"\xff\xfe", b""):
            with self.subTest(cuerpo=cuerpo), self.assertRaises(JsonInvalido):
                traduccion.leer_objeto(cuerpo)

    def test_regla_json_lee_los_decimales_sin_pasar_por_float(self):
        """D-74, punto 7 y «Números»: los decimales se leen como `Decimal` (24.5 exacto) y los enteros, como `int`."""
        objeto = traduccion.leer_objeto(b'{"lecturas": [{"identificador": "a", "valor": 24.5}, {"identificador": "b", "valor": 7}]}')
        from decimal import Decimal

        self.assertEqual(objeto["lecturas"][0]["valor"], Decimal("24.5"))
        self.assertIsInstance(objeto["lecturas"][0]["valor"], Decimal)
        self.assertIsInstance(objeto["lecturas"][1]["valor"], int)

    def test_regla_envoltura_un_campo_desconocido_arriba_rechaza_el_mensaje_con_el_campo(self):
        """D-74, punto 7: un campo de más en el objeto de arriba es 400 `mensaje_mal_formado`, con `campo` y el texto «nodo: no existe en este mensaje.»."""
        with self.assertRaises(MensajeMalFormado) as contexto:
            traduccion.lista_de_lecturas({"lecturas": [], "nodo": "nodo-norte"})
        self.assertEqual(contexto.exception.campo, "nodo")
        self.assertEqual(contexto.exception.detalle, "nodo: no existe en este mensaje.")
        self.assertIsNone(contexto.exception.indice)

    def test_regla_envoltura_sin_la_lista_o_con_algo_que_no_es_lista(self):
        """La lista es obligatoria y tiene que ser una lista."""
        with self.assertRaisesMessage(MensajeMalFormado, "lecturas: falta."):
            traduccion.lista_de_lecturas({})
        with self.assertRaisesMessage(MensajeMalFormado, "lecturas: tiene que ser una lista."):
            traduccion.lista_de_lecturas({"lecturas": {"identificador": "a"}})

    def test_regla_envoltura_acepta_la_lista_vacia_el_latido(self):
        """D-74, punto 2: `{"lecturas": []}` es el latido: una envoltura válida sin elementos."""
        self.assertEqual(traduccion.lista_de_lecturas({"lecturas": []}), [])

    def test_regla_lectura_valida_conserva_el_identificador_enviado_y_el_recortado(self):
        """El identificador se compara sin los espacios del borde; la respuesta lleva el que mandó el nodo, tal cual."""
        [lectura] = traduccion.traducir_lecturas([{"identificador": " Norte/Temp ", "valor": 24, "medida_en": "2026-11-21T14:04:30-03:00"}])
        self.assertEqual(
            lectura, LecturaRecibida(0, " Norte/Temp ", "Norte/Temp", 24, "2026-11-21T14:04:30-03:00")
        )

    def test_regla_lectura_sin_medida_en_es_valida(self):
        """`medida_en` es optativa (extensión 3e): la forma la acepta ausente, y el servicio usa la hora de recepción."""
        [lectura] = traduccion.traducir_lecturas([{"identificador": "a", "valor": 1}])
        self.assertIsNone(lectura.medida_en)

    def test_regla_lectura_un_campo_desconocido_rechaza_ese_elemento_mal_formada(self):
        """D-74, punto 7: un campo desconocido en un elemento rechaza solo ese elemento (`mal_formada`), con el texto «el campo «medido_en» no existe»."""
        resultado = traduccion.traducir_lecturas(
            [{"identificador": "norte/sectorA/temperatura", "valor": 25, "medido_en": "2026-11-21T14:04:30-03:00"}]
        )
        self.assertEqual(
            resultado,
            [
                ElementoMalFormado(
                    0, "norte/sectorA/temperatura", "mal_formada", "No tiene la forma del contrato: el campo «medido_en» no existe."
                )
            ],
        )

    def test_regla_lectura_un_identificador_de_65_caracteres_es_mal_formada(self):
        """D-75, punto 5: más de 64 caracteres no es un identificador posible: `mal_formada`, no «dispositivo no registrado»."""
        [resultado] = traduccion.traducir_lecturas([{"identificador": "a" * 65, "valor": 1}])
        self.assertEqual(resultado.motivo, "mal_formada")
        self.assertEqual(
            resultado.detalle, "No tiene la forma del contrato: el identificador tiene más de 64 caracteres o caracteres no permitidos."
        )
        [valido] = traduccion.traducir_lecturas([{"identificador": "a" * 64, "valor": 1}])
        self.assertIsInstance(valido, LecturaRecibida)

    def test_regla_lectura_un_identificador_con_espacios_o_signos_es_mal_formada(self):
        """D-75, punto 5: espacios adentro u otros signos hacen `mal_formada`."""
        for identificador in ("norte sectorA", "norte/sector#A", "ñandú", ""):
            with self.subTest(identificador=identificador):
                [resultado] = traduccion.traducir_lecturas([{"identificador": identificador, "valor": 1}])
                self.assertEqual(resultado.motivo, "mal_formada")

    def test_regla_lectura_identificador_que_no_es_texto_es_mal_formada_y_vuelve_null(self):
        """Respuesta: `identificador` es el que mandó el nodo si era texto y `null` si no vino o no era texto."""
        sin_identificador = traduccion.traducir_lecturas([{"valor": 1}])[0]
        numerico = traduccion.traducir_lecturas([{"identificador": 7, "valor": 1}])[0]
        self.assertEqual((sin_identificador.motivo, sin_identificador.identificador_enviado), ("mal_formada", None))
        self.assertEqual((numerico.motivo, numerico.identificador_enviado), ("mal_formada", None))
        self.assertIn("falta «identificador»", sin_identificador.detalle)

    def test_regla_lectura_falta_el_valor_es_mal_formada(self):
        """Falta `valor`: «falta «valor»»."""
        [resultado] = traduccion.traducir_lecturas([{"identificador": "a"}])
        self.assertEqual(resultado.detalle, "No tiene la forma del contrato: falta «valor».")

    def test_regla_lectura_un_elemento_que_no_es_un_objeto_es_mal_formada(self):
        """Un elemento que no es un objeto: «no es un objeto», sin identificador."""
        resultado = traduccion.traducir_lecturas(["texto", 5, None, ["a"]])
        self.assertEqual({r.detalle for r in resultado}, {"No tiene la forma del contrato: no es un objeto."})
        self.assertEqual([r.indice for r in resultado], [0, 1, 2, 3])
        self.assertTrue(all(r.identificador_enviado is None for r in resultado))

    def test_regla_lectura_la_forma_no_juzga_el_valor_ni_la_fecha(self):
        """La traducción verifica solo la forma: un valor de texto o una fecha rara pasan (los juzgan los servicios, que dependen del sensor)."""
        [lectura] = traduccion.traducir_lecturas([{"identificador": "a", "valor": "71", "medida_en": "no es fecha"}])
        self.assertIsInstance(lectura, LecturaRecibida)
        self.assertEqual((lectura.valor, lectura.medida_en), ("71", "no es fecha"))


class ApiTraduccionEstadosYModoTests(SimpleTestCase):
    """`POST estados` y `POST modo` (mensajes.md, secciones 2 y 3)."""

    def test_regla_estado_valido_y_con_fecha_optativa(self):
        """Un estado trae `identificador` y `estado`; `informado_en` es optativa."""
        [estado] = traduccion.traducir_estados([{"identificador": "norte/sectorA/ventilador", "estado": "encendido"}])
        self.assertEqual((estado.identificador, estado.estado, estado.informado_en), ("norte/sectorA/ventilador", "encendido", None))

    def test_regla_estado_sin_estado_o_con_campo_desconocido_es_mal_formado(self):
        """Falta `estado`: «falta «estado»»; un campo desconocido, «el campo «x» no existe»."""
        [falta, desconocido] = traduccion.traducir_estados([{"identificador": "a"}, {"identificador": "a", "estado": "en_linea", "x": 1}])
        self.assertEqual(falta.detalle, "No tiene la forma del contrato: falta «estado».")
        self.assertEqual(desconocido.detalle, "No tiene la forma del contrato: el campo «x» no existe.")

    def test_regla_estado_identificador_de_65_caracteres_es_mal_formada(self):
        """D-75, punto 5, también en los estados."""
        [resultado] = traduccion.traducir_estados([{"identificador": "a" * 65, "estado": "en_linea"}])
        self.assertEqual(resultado.motivo, "mal_formada")

    def test_regla_estados_acepta_la_lista_vacia_y_rechaza_el_campo_de_mas(self):
        """La lista vacía cuenta como mensaje aceptado; un campo de más arriba es 400."""
        self.assertEqual(traduccion.lista_de_estados({"estados": []}), [])
        with self.assertRaisesMessage(MensajeMalFormado, "lecturas: no existe en este mensaje."):
            traduccion.lista_de_estados({"estados": [], "lecturas": []})

    def test_regla_modo_acepta_remoto_y_local(self):
        """Mensajes.md, sección 3: `remoto` o `local`."""
        self.assertEqual(traduccion.traducir_modo({"modo": "remoto"}), "remoto")
        self.assertEqual(traduccion.traducir_modo({"modo": "local"}), "local")

    def test_regla_modo_otro_valor_o_forma_es_mensaje_mal_formado(self):
        """Otro valor del modo, sin `modo` o con un campo de más: 400 `mensaje_mal_formado` con el campo."""
        casos = {
            "tiene que ser «remoto» o «local»": [{"modo": "auto"}, {"modo": None}, {"modo": ["local"]}],
            "falta": [{}],
            "no existe en este mensaje": [{"modo": "local", "x": 1}],
        }
        for razon, objetos in casos.items():
            for objeto in objetos:
                with self.subTest(objeto=objeto), self.assertRaises(MensajeMalFormado) as contexto:
                    traduccion.traducir_modo(objeto)
                self.assertTrue(contexto.exception.razon.endswith(razon))


class ApiTraduccionAnuncioTests(SimpleTestCase):
    """`POST anuncio` (mensajes.md, sección 4): se procesa entero o nada."""

    def test_regla_anuncio_valido(self):
        """Sensores sin `comandos` y actuadores con ellos; el identificador queda recortado."""
        equipos = traduccion.traducir_anuncio(
            [
                {"identificador": "norte/sectorA/temperatura", "clase": "sensor"},
                {"identificador": " norte/sectorA/ventilador ", "clase": "actuador", "comandos": ["ENCENDER", "APAGAR"]},
            ]
        )
        self.assertEqual(
            equipos,
            [
                EquipoRecibido("norte/sectorA/temperatura", "sensor", ()),
                EquipoRecibido("norte/sectorA/ventilador", "actuador", ("ENCENDER", "APAGAR")),
            ],
        )

    def test_regla_anuncio_un_comando_fuera_del_catalogo_rechaza_todo_con_indice_y_campo(self):
        """Ejemplo `anuncio_mal_formado`: «GIRAR» en el equipo 1 es 400, con `indice` 1 y `campo` `equipos[1].comandos`."""
        with self.assertRaises(MensajeMalFormado) as contexto:
            traduccion.traducir_anuncio(
                [
                    {"identificador": "norte/sectorA/ventilador", "clase": "actuador", "comandos": ["ENCENDER", "APAGAR"]},
                    {"identificador": "norte/sectorA/ventana", "clase": "actuador", "comandos": ["ABRIR", "GIRAR"]},
                ]
            )
        error = contexto.exception
        self.assertEqual((error.indice, error.campo), (1, "equipos[1].comandos"))
        self.assertEqual(error.detalle, "equipos[1].comandos: «GIRAR» no está en el catálogo de comandos.")

    def test_regla_anuncio_un_identificador_repetido_con_otras_mayusculas_rechaza_todo(self):
        """El identificador no se repite en el anuncio, sin distinguir mayúsculas: 400 con `indice` y `campo`."""
        with self.assertRaises(MensajeMalFormado) as contexto:
            traduccion.traducir_anuncio(
                [
                    {"identificador": "Norte/Temp", "clase": "sensor"},
                    {"identificador": "otro", "clase": "sensor"},
                    {"identificador": "norte/temp", "clase": "sensor"},
                ]
            )
        error = contexto.exception
        self.assertEqual((error.indice, error.campo), (2, "equipos[2].identificador"))
        self.assertEqual(error.razon, "el identificador «norte/temp» se repite en el anuncio")

    def test_regla_anuncio_las_demas_formas_malas(self):
        """Clase desconocida, sensor con `comandos`, actuador sin `comandos`, comando repetido, identificador mal formado, elemento que no es un objeto."""
        casos = [
            ({"identificador": "a", "clase": "nodo"}, "equipos[0].clase", "tiene que ser «sensor» o «actuador»"),
            ({"identificador": "a", "clase": "sensor", "comandos": []}, "equipos[0].comandos", "un sensor no lleva comandos"),
            ({"identificador": "a", "clase": "actuador"}, "equipos[0].comandos", "falta"),
            ({"identificador": "a", "clase": "actuador", "comandos": "ENCENDER"}, "equipos[0].comandos", "tiene que ser una lista"),
            (
                {"identificador": "a", "clase": "actuador", "comandos": ["ENCENDER", "ENCENDER"]},
                "equipos[0].comandos",
                "el comando «ENCENDER» se repite",
            ),
            (
                {"identificador": "a b", "clase": "sensor"},
                "equipos[0].identificador",
                "el identificador tiene más de 64 caracteres o caracteres no permitidos",
            ),
            ({"identificador": "a"}, "equipos[0].clase", "falta"),
            ({"clase": "sensor"}, "equipos[0].identificador", "falta"),
            ({"identificador": "a", "clase": "sensor", "x": 1}, "equipos[0].x", "no existe en este mensaje"),
            ("texto", "equipos[0]", "tiene que ser un objeto"),
        ]
        for equipo, campo, razon in casos:
            with self.subTest(equipo=equipo), self.assertRaises(MensajeMalFormado) as contexto:
                traduccion.traducir_anuncio([equipo])
            self.assertEqual((contexto.exception.campo, contexto.exception.razon, contexto.exception.indice), (campo, razon, 0))

    def test_regla_anuncio_una_lista_vacia_es_valida(self):
        """Mensajes.md, sección 4: una lista vacía es válida (el nodo no tiene equipos)."""
        self.assertEqual(traduccion.traducir_anuncio([]), [])

    def test_regla_anuncio_los_seis_comandos_del_catalogo_son_validos(self):
        """El catálogo de la guía (sección 9): ENCENDER, APAGAR, FIJAR_NIVEL, ABRIR, CERRAR y FIJAR_POSICION."""
        comandos = ["ENCENDER", "APAGAR", "FIJAR_NIVEL", "ABRIR", "CERRAR", "FIJAR_POSICION"]
        [equipo] = traduccion.traducir_anuncio([{"identificador": "a", "clase": "actuador", "comandos": comandos}])
        self.assertEqual(equipo.comandos, tuple(comandos))


class ApiLimitesTests(SimpleTestCase):
    """`contar_pedido` (D-70, punto 5; D-74, punto 8): ventana fija por minuto, por resumen de token."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_regla_los_primeros_120_pasan_y_el_121_da_retry_after(self):
        """Respuestas_y_errores.md, sección 2: el pedido 120 pasa; el 121 da 429, con los segundos que faltan para el minuto siguiente (60 a las hh:mm:00)."""
        for numero in range(1, limites.PEDIDOS_POR_MINUTO + 1):
            self.assertIsNone(limites.contar_pedido("a" * 64, AHORA), numero)
        self.assertEqual(limites.contar_pedido("a" * 64, AHORA), 60)

    def test_regla_retry_after_son_los_segundos_que_faltan_del_minuto(self):
        """A las hh:mm:45 faltan 15 segundos."""
        tarde = AHORA.replace(second=45)
        for _ in range(limites.PEDIDOS_POR_MINUTO):
            limites.contar_pedido("a" * 64, tarde)
        self.assertEqual(limites.contar_pedido("a" * 64, tarde), 15)

    def test_regla_el_minuto_siguiente_vuelve_a_empezar(self):
        """Ventana fija: después del límite, el minuto de reloj siguiente tiene su propio contador."""
        for _ in range(limites.PEDIDOS_POR_MINUTO + 1):
            limites.contar_pedido("a" * 64, AHORA)
        self.assertIsNone(limites.contar_pedido("a" * 64, AHORA.replace(minute=6)))

    def test_regla_dos_resumenes_no_se_mezclan(self):
        """El contador es por nodo: uno que llegó al límite no frena a otro."""
        for _ in range(limites.PEDIDOS_POR_MINUTO + 1):
            limites.contar_pedido("a" * 64, AHORA)
        self.assertIsNone(limites.contar_pedido("b" * 64, AHORA))

    def test_regla_la_clave_usa_los_16_primeros_caracteres_del_resumen_y_el_minuto(self):
        """D-70 / «La API»: la clave es `iot:pedidos:<16 primeros caracteres>:<AAAAMMDDHHMM>` y no lleva el resumen entero."""
        resumen = "0123456789abcdef" + "f" * 48
        limites.contar_pedido(resumen, AHORA)
        self.assertEqual(cache.get("iot:pedidos:0123456789abcdef:202611211705"), 1)

    def test_regla_los_limites_son_los_del_contrato(self):
        """D-70, punto 5: 120 pedidos por minuto, 256 KB y 500 elementos."""
        self.assertEqual(
            (limites.PEDIDOS_POR_MINUTO, limites.BYTES_POR_PEDIDO, limites.ELEMENTOS_POR_PEDIDO), (120, 262144, 500)
        )


class ApiRespuestasYAutenticacionTests(SimpleTestCase):
    """`respuestas.py` y `autenticacion.py` (respuestas_y_errores.md, secciones 1 y 3)."""

    def test_regla_respuesta_ok_trae_version_y_servidor_en_en_utc_con_z(self):
        """Mensajes.md, sección 0: toda respuesta trae `version` y `servidor_en` (UTC con `Z`)."""
        import json

        respuesta = respuestas.respuesta_ok({"aceptadas": 0}, AHORA)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(json.loads(respuesta.content), {"version": "v1", "servidor_en": "2026-11-21T17:05:00Z", "aceptadas": 0})

    def test_regla_respuesta_error_las_401_suman_www_authenticate(self):
        """Respuestas_y_errores.md, sección 3: las 401 llevan `WWW-Authenticate: Bearer`."""
        respuesta = respuestas.respuesta_error(401, "token_ausente", AHORA, "Falta el encabezado «Authorization: Bearer <token>».")
        self.assertEqual(respuesta["WWW-Authenticate"], "Bearer")

    def test_regla_respuesta_error_405_y_429_llevan_sus_encabezados(self):
        """`Allow` en la 405 y `Retry-After` en la 429, que pasa quien llama."""
        r405 = respuestas.respuesta_error(405, "metodo_no_permitido", AHORA, "Esta ruta solo acepta POST.", encabezados={"Allow": "POST"})
        r429 = respuestas.respuesta_error(429, "demasiados_pedidos", AHORA, "...", encabezados={"Retry-After": "60"})
        self.assertEqual((r405["Allow"], r429["Retry-After"]), ("POST", "60"))

    def test_regla_respuesta_error_trae_campo_e_indice_y_los_textos_sin_escapar(self):
        """El cuerpo de un `mensaje_mal_formado` trae `campo` e `indice`; las «» y las tildes van tal cual."""
        import json

        respuesta = respuestas.respuesta_error(
            400, "mensaje_mal_formado", AHORA, "equipos[1].comandos: «GIRAR» no está.", campo="equipos[1].comandos", indice=1
        )
        self.assertIn("«GIRAR»".encode(), respuesta.content)
        self.assertEqual(json.loads(respuesta.content)["indice"], 1)

    def test_regla_token_el_encabezado_bearer_da_el_resumen_y_nunca_el_token(self):
        """Respuestas_y_errores.md, sección 1: se busca por el SHA-256; el resumen no es el token."""
        resumen = autenticacion.resumen_del_encabezado("Bearer token-de-ejemplo-no-es-secreto")
        self.assertEqual(resumen, resumen_de("token-de-ejemplo-no-es-secreto"))
        self.assertNotIn("token-de-ejemplo", resumen)

    def test_regla_token_ausente_cuando_no_hay_bearer_con_algo_despues(self):
        """Verificación 3: sin encabezado, con otro esquema o con `Bearer` solo, el token está ausente."""
        for valor in (None, "", "Bearer", "Bearer   ", "Basic abc", "abc"):
            with self.subTest(valor=valor):
                self.assertIsNone(autenticacion.resumen_del_encabezado(valor))

    def test_regla_token_mal_formado_tiene_resumen_y_se_rechaza_despues_como_invalido(self):
        """Un token con espacios no es «ausente»: tiene resumen (cuenta en el límite) y la verificación 5 lo rechaza como `token_invalido`."""
        self.assertIsNotNone(autenticacion.resumen_del_encabezado("Bearer con espacios adentro"))
        self.assertIsNotNone(autenticacion.resumen_del_encabezado("bearer minuscula"))
