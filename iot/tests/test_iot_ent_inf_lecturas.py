# Pruebas de IOT-ENT-INF, parte de las lecturas y de la comunicación del nodo (IOT-03; docs/casos_de_uso/iot/entregar_informacion.md). El paso 2
# trae `IotEntInfNodoServicioTests` (postcondición a, `sistema_por_resumen`) e `IotEntInfAlertasServicioTests` (`asegurar_alerta_iot`, `resolver_alerta_iot`);
# el paso 3 suma `IotEntInfLecturasServicioTests` (abajo). Se escribieron ANTES que el servicio (`.claude/rules/pruebas.md`).
#
# Servicios que se prueban:
#   iot/servicios/lecturas.py:     contexto_del_mensaje(sistema, ahora) -> ContextoDeLecturas      (los parámetros y el umbral, UNA vez por pedido)
#                                  registrar_lectura(contexto, lectura, ahora) -> ResultadoDeLectura(resultado, valida, atrasada, motivo, detalle)
#                                  tiene_lecturas(sensor)
#   iot/servicios/nodo.py:         sistema_por_resumen(resumen) -> SistemaIoT | None
#                                  registrar_comunicacion(sistema_id, ahora)
#   iot/servicios/alertas_iot.py:  asegurar_alerta_iot(invernadero_id, sistema, tipo, clave, descripcion, hardware=None, telemetria=None) -> ResultadoDeAlerta(alerta, creada)
#                                  resolver_alerta_iot(invernadero_id, tipo, clave) -> Alerta | None

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from core.enlaces import resumen_de
from core.models import RegistroAuditoria
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso, variedad_con_semilla, variedades_presentes_de_prueba
from iot.api.traduccion import LecturaRecibida
from iot.models import AlertaIot, NodoCentral, Telemetria
from iot.servicios import sistemas
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import crear_agronomo, crear_invernadero, crear_sector

nodo = perezoso("iot.servicios.nodo")
alertas_iot = perezoso("iot.servicios.alertas_iot")

AHORA = datetime(2026, 11, 21, 17, 5, 0, tzinfo=timezone.utc)


class IotEntInfNodoServicioTests(fabricas.ConCatalogoIot, TestCase):
    """Precondición a, postcondición a y extensión *a: el token identifica al sistema y cada mensaje aceptado registra la comunicación del nodo."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.resumen = resumen_de("token-de-ejemplo-no-es-secreto")
        self.sistema = fabricas.sistema(self.norte, token_resumen=self.resumen)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)

    def test_regla_origen_el_sistema_activo_y_el_desconectado_se_encuentran_por_su_resumen(self):
        """Respuestas_y_errores.md, sección 1: se busca por el resumen SHA-256; el desconectado también se encuentra (la verificación 6 lo rechaza con 403)."""
        self.assertEqual(nodo.sistema_por_resumen(self.resumen), self.sistema)
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        self.assertEqual(nodo.sistema_por_resumen(self.resumen), self.sistema)

    def test_regla_origen_un_sistema_dado_de_baja_no_se_encuentra_por_su_resumen(self):
        """Respuestas_y_errores.md, sección 3 (verificación 5): un token de un sistema dado de baja es `token_invalido`; un resumen desconocido, también."""
        self.sistema.estado_sistema = "inactivo"
        self.sistema.save(update_fields=["estado_sistema"])
        self.assertIsNone(nodo.sistema_por_resumen(self.resumen))
        self.assertIsNone(nodo.sistema_por_resumen(resumen_de("otro-token")))

    def test_post_a_la_comunicacion_actualiza_ultima_comunicacion_y_deja_al_nodo_en_linea(self):
        """Postcondición a: se registró la fecha y la hora de la comunicación y el nodo queda «en línea»."""
        self.assertIsNone(self.nodo.ultima_comunicacion)
        nodo.registrar_comunicacion(self.sistema.pk, AHORA)
        self.nodo.refresh_from_db()
        self.assertEqual(self.nodo.ultima_comunicacion, AHORA)
        self.assertEqual(sistemas.conectividad(self.nodo, AHORA).estado, "en_linea")

    def test_post_a_la_comunicacion_resuelve_la_alerta_nodo_sin_comunicacion(self):
        """Postcondición a: si tenía activa la alerta «nodo sin comunicación» (clave `nodo:<id>`), pasó a «resuelta»; se audita, con la alerta resuelta."""
        clave = f"nodo:{self.nodo.pk}"
        alerta = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_nodo_sin_comunicacion", clave, "Nodo de prueba · sin comunicación"
        ).alerta
        nodo.registrar_comunicacion(self.sistema.pk, AHORA)
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")
        [registro] = RegistroAuditoria.objects.filter(accion="entrega_informacion_iot")
        self.assertEqual(registro.detalle["datos"]["alertas_resueltas"], [{"id": alerta.pk, "texto": str(alerta)}])
        self.assertIn(("maestros.alerta", alerta.pk), [(a["modelo"], a["id"]) for a in registro.afectados])

    def test_post_z_la_comunicacion_sola_no_se_audita(self):
        """«Auditoría»: solo se audita si cambió algo además de la comunicación; un mensaje que solo la registra no deja registro."""
        nodo.registrar_comunicacion(self.sistema.pk, AHORA)
        self.assertFalse(RegistroAuditoria.objects.filter(accion="entrega_informacion_iot").exists())

    def test_ext_astar_un_sistema_desconectado_no_registra_la_comunicacion(self):
        """Extensión *a: «rechaza el mensaje sin registrar ningún cambio»: `SistemaDesconectado` y la comunicación queda como estaba."""
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        with self.assertRaises(nodo.SistemaDesconectado):
            nodo.registrar_comunicacion(self.sistema.pk, AHORA)
        self.nodo.refresh_from_db()
        self.assertIsNone(self.nodo.ultima_comunicacion)


class IotEntInfAlertasServicioTests(fabricas.ConCatalogoIot, TestCase):
    """`alertas_iot.py`: llama a `maestros.servicios.alertas` y deja el `AlertaIot` de cada alerta (D-72, punto 4), sin duplicar."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.sensor = fabricas.sensor(self.sistema, "norte/temp")

    def asegurar(self, **extra):
        datos = {"tipo": "iot_lectura_invalida", "clave": f"hw:{self.sensor.pk}", "descripcion": "norte/temp · 999", "hardware": self.sensor}
        return alertas_iot.asegurar_alerta_iot(self.norte.pk, self.sistema, **(datos | extra))

    def test_regla_una_alerta_nueva_crea_su_alerta_iot_con_el_sistema_y_el_origen(self):
        """«Alertas: textos y origen»: la alerta nueva queda activa, con su `AlertaIot` (sistema y el hardware de origen) y la descripción dada."""
        resultado = self.asegurar()
        self.assertTrue(resultado.creada)
        self.assertEqual((resultado.alerta.estado_alerta, resultado.alerta.descripcion_alerta), ("activa", "norte/temp · 999"))
        vinculo = AlertaIot.objects.get(alerta=resultado.alerta)
        self.assertEqual((vinculo.sistema, vinculo.hardware_id, vinculo.telemetria_id), (self.sistema, self.sensor.pk, None))

    def test_regla_una_alerta_con_origen_en_la_telemetria_vincula_la_lectura(self):
        """R053: las alertas de umbral, de rango y de nivel tienen origen en la telemetría."""
        lectura = fabricas.telemetria(self.sensor, "70")
        resultado = self.asegurar(tipo="iot_fuera_de_umbral", clave=f"sensor:{self.sensor.pk}", hardware=None, telemetria=lectura)
        vinculo = AlertaIot.objects.get(alerta=resultado.alerta)
        self.assertEqual((vinculo.telemetria_id, vinculo.hardware_id), (lectura.pk, None))

    def test_regla_una_alerta_sin_origen_no_lleva_hardware_ni_telemetria(self):
        """«dispositivo no registrado»: sin origen en el modelo; el identificador va en la clave y en la descripción, y el sistema siempre."""
        resultado = self.asegurar(tipo="iot_dispositivo_no_registrado", clave="id:norte/sectorb/co2", hardware=None)
        vinculo = AlertaIot.objects.get(alerta=resultado.alerta)
        self.assertEqual((vinculo.sistema, vinculo.hardware_id, vinculo.telemetria_id), (self.sistema, None, None))

    def test_regla_no_crea_un_segundo_alerta_iot_para_una_alerta_que_ya_existia(self):
        """Tarea, paso 2: asegurar dos veces no crea otro `AlertaIot` ni otra alerta: la segunda devuelve la misma, con `creada` en falso, y la descripción no se actualiza."""
        primera = self.asegurar()
        segunda = self.asegurar(descripcion="norte/temp · 1000")
        self.assertEqual(segunda.alerta.pk, primera.alerta.pk)
        self.assertTrue(primera.creada)
        self.assertFalse(segunda.creada)
        self.assertEqual(AlertaIot.objects.filter(alerta=primera.alerta).count(), 1)
        self.assertEqual(Alerta.objects.filter(tipo_alerta="iot_lectura_invalida").count(), 1)
        self.assertEqual(segunda.alerta.descripcion_alerta, "norte/temp · 999")

    def test_regla_en_un_invernadero_inactivo_no_crea_nada(self):
        """docs/api/alertas.md, sección 2: con el invernadero inactivo no se crea la alerta (no es un error): `alerta` nula y ningún `AlertaIot`."""
        self.norte.estado_invernadero = "inactivo"
        self.norte.save(update_fields=["estado_invernadero"])
        resultado = self.asegurar()
        self.assertEqual((resultado.alerta, resultado.creada), (None, False))
        self.assertFalse(AlertaIot.objects.exists())

    def test_regla_resolver_pasa_a_resuelta_y_conserva_el_vinculo(self):
        """Resolver devuelve la alerta resuelta y deja su `AlertaIot` (se resuelven solas, pero no se borran); sin alerta activa devuelve `None`."""
        alerta = self.asegurar().alerta
        resuelta = alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_lectura_invalida", f"hw:{self.sensor.pk}")
        self.assertEqual((resuelta.pk, resuelta.estado_alerta), (alerta.pk, "resuelta"))
        self.assertTrue(AlertaIot.objects.filter(alerta=alerta).exists())
        self.assertIsNone(alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_lectura_invalida", f"hw:{self.sensor.pk}"))

    def test_regla_una_alerta_resuelta_deja_crear_otra_nueva_con_su_propio_vinculo(self):
        """A lo sumo una ACTIVA por equipo y tipo: después de resolverla, la condición puede volver y crea una nueva con su propio `AlertaIot`."""
        primera = self.asegurar().alerta
        alertas_iot.resolver_alerta_iot(self.norte.pk, "iot_lectura_invalida", f"hw:{self.sensor.pk}")
        segunda = self.asegurar()
        self.assertTrue(segunda.creada)
        self.assertNotEqual(segunda.alerta.pk, primera.pk)
        self.assertEqual(AlertaIot.objects.filter(sistema=self.sistema).count(), 2)


# ---------------------------------------------------------------------------------------------------------------------------------------------------
# Paso 3: las lecturas (pasos 3 a 5 y extensiones 3a a 5g de IOT-ENT-INF; «Una lectura» de «Cómo se aplica»; D-74 y D-75).
# ---------------------------------------------------------------------------------------------------------------------------------------------------

lecturas = perezoso("iot.servicios.lecturas")

HACE_30_S = (AHORA - timedelta(seconds=30)).isoformat()


class IotEntInfLecturasServicioTests(fabricas.ConCatalogoIot, TestCase):
    """`registrar_lectura`: los 11 pasos de «Una lectura», en ese orden, con el contexto del mensaje calculado una vez por pedido. El umbral efectivo sale de
    ``variedades_presentes_de_prueba`` (docs/api/variedades.md): temperatura 18 a 24 °C, humedad 60 a 80 % HR y luz 200 a 400 lux, salvo que la prueba pida
    otras variedades. Histéresis iniciales: 1 °C, 3 % HR, 2.000 lux y 1 °C en la solución."""

    def setUp(self):
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.norte = crear_invernadero("Norte", agronomo=crear_agronomo("laura@infoponia.com"))
        self.sistema = fabricas.sistema(self.norte)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        self.contador = 0

    # ---- ayudas ----

    def con_umbral(self, *variedades):
        """Deja presentes las variedades dadas (por omisión, una con los rangos por defecto de las fábricas)."""
        variedades = variedades or (variedad_con_semilla(nombre="Crespa"),)
        self.enterContext(variedades_presentes_de_prueba({self.norte.pk: {v.pk for v in variedades}}))

    def registrar(self, identificador, valor, medida_en=HACE_30_S, ahora=AHORA, contexto=None):
        """Registra UNA lectura con su propio contexto del mensaje (como un pedido de una lectura)."""
        contexto = contexto or lecturas.contexto_del_mensaje(self.sistema, ahora)
        lectura = LecturaRecibida(self.contador, identificador, identificador.strip(), valor, medida_en)
        self.contador += 1
        return lecturas.registrar_lectura(contexto, lectura, ahora)

    def temperatura(self, valor, **extra):
        return self.registrar("norte/sectorA/temperatura", Decimal(str(valor)), **extra)

    def alertas(self, tipo, estado="activa"):
        return Alerta.objects.filter(tipo_alerta=tipo, estado_alerta=estado)

    def auditorias(self):
        return RegistroAuditoria.objects.filter(accion="entrega_informacion_iot")

    # ---- postcondición b y c: guardar ----

    def test_post_b_guarda_la_telemetria_con_valor_unidad_fecha_y_marca_valida(self):
        """Postcondición b: telemetría con el valor medido, la unidad del sensor, la fecha de medición y la marca «válida», asociada al sensor."""
        resultado = self.temperatura("24.5")
        lectura = Telemetria.objects.get(sensor=self.temp)
        self.assertEqual((lectura.valor_medido, lectura.unidad_medida_telemetria, lectura.valida), (Decimal("24.50"), "°C", True))
        self.assertEqual(lectura.medida_en, AHORA - timedelta(seconds=30))
        self.assertEqual(
            (resultado.resultado, resultado.valida, resultado.atrasada, resultado.motivo), ("aceptada", True, False, None)
        )

    def test_post_b_redondea_a_dos_decimales_con_el_medio_hacia_arriba(self):
        """D-74, punto 7 y «Números»: se guardan con dos decimales, redondeo al más cercano; el medio, hacia arriba."""
        self.temperatura("24.555")
        self.assertEqual(Telemetria.objects.get().valor_medido, Decimal("24.56"))

    def test_post_b_un_entero_json_se_guarda_como_decimal(self):
        """Un valor entero (71, no 71.0) es un número JSON válido."""
        humedad = fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad", valor_calibracion_min=0, valor_calibracion_max=100)
        self.registrar("norte/sectorA/humedad", 71)
        self.assertEqual((Telemetria.objects.get(sensor=humedad).valor_medido, Telemetria.objects.get().unidad_medida_telemetria), (Decimal("71.00"), "% HR"))

    def test_post_b_en_el_nivel_se_guarda_el_estado_sin_valor_ni_unidad_ni_marca(self):
        """Docs/modelo/iot.md, «Telemetria»: en el nivel, `estado_nivel_medido` y nada más (valor, unidad y `valida` nulos)."""
        nivel = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        resultado = self.registrar("norte/tanque1/nivel", "normal")
        lectura = Telemetria.objects.get(sensor=nivel)
        self.assertEqual(
            (lectura.estado_nivel_medido, lectura.valor_medido, lectura.unidad_medida_telemetria, lectura.valida), ("normal", None, None, None)
        )
        self.assertEqual((resultado.resultado, resultado.valida), ("aceptada", None))

    def test_post_b_la_lectura_deja_al_sensor_de_estar_sin_confirmar(self):
        """Regla «Estado actual de un equipo»: con su primer mensaje deja de estar «sin confirmar» (`ultimo_mensaje_en` = ahora)."""
        self.assertIsNone(self.temp.ultimo_mensaje_en)
        self.temperatura("24")
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.ultimo_mensaje_en, AHORA)

    def test_post_c_resuelve_la_alerta_sin_actividad_del_sensor(self):
        """Postcondición c: si el sensor tenía activa «dispositivo sin actividad», pasó a «resuelta»."""
        alerta = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", "sin actividad", hardware=self.temp
        ).alerta
        self.temperatura("24")
        alerta.refresh_from_db()
        self.assertEqual(alerta.estado_alerta, "resuelta")

    # ---- postcondiciones d y e, extensiones 4a y 4b: la calibración ----

    def test_post_d_una_lectura_fuera_de_calibracion_es_invalida_y_genera_la_alerta(self):
        """Postcondición d y extensión 4a: valor fuera del rango de calibración (−10 a 60): `valida` falso, alerta «lectura inválida» con origen en el sensor (R052)."""
        resultado = self.temperatura("999")
        self.assertEqual((resultado.resultado, resultado.valida), ("aceptada", False))
        self.assertFalse(Telemetria.objects.get().valida)
        [alerta] = self.alertas("iot_lectura_invalida")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).hardware_id, self.temp.pk)
        self.assertEqual(alerta.clave_estado, f"hw:{self.temp.pk}")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/temperatura · 999 °C, fuera de la calibración (-10 a 60)")

    def test_post_d_una_segunda_lectura_invalida_no_genera_otra_alerta(self):
        """Garantía: nunca dos alertas activas del mismo tipo para el mismo sensor."""
        self.temperatura("999")
        self.temperatura("998", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_lectura_invalida").count(), 1)

    def test_ext_4a_la_lectura_invalida_no_se_compara_ni_dispara_reglas(self):
        """Extensión 4a: una lectura inválida no se compara con el umbral ni evalúa reglas."""
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.temperatura("999")
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        reglas.assert_not_called()

    def test_post_e_una_lectura_valida_resuelve_la_alerta_lectura_invalida(self):
        """Postcondición e y extensión 4b: con una lectura válida, la alerta «lectura inválida» pasó a «resuelta»."""
        self.temperatura("999")
        self.temperatura("22", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertFalse(self.alertas("iot_lectura_invalida").exists())
        self.assertEqual(self.alertas("iot_lectura_invalida", "resuelta").count(), 1)

    # ---- postcondición f y extensiones 5a, 5b, 5c: el umbral efectivo y la histéresis ----

    def test_post_f_fuera_del_umbral_genera_la_alerta_con_origen_en_la_telemetria(self):
        """Postcondición f y extensión 5a: temperatura sobre el máximo efectivo (24): alerta «fuera de umbral efectivo» con origen en esa telemetría (R053)."""
        self.con_umbral()
        self.temperatura("26.4")
        [alerta] = self.alertas("iot_fuera_de_umbral")
        self.assertEqual(AlertaIot.objects.get(alerta=alerta).telemetria_id, Telemetria.objects.get().pk)
        self.assertEqual(alerta.clave_estado, f"sensor:{self.temp.pk}")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/temperatura · 26,4 °C (máximo efectivo 24 °C)")

    def test_post_f_bajo_el_minimo_dice_minimo_efectivo(self):
        """El texto con el límite superado: «(mínimo efectivo 18 °C)»."""
        self.con_umbral()
        self.temperatura("15")
        [alerta] = self.alertas("iot_fuera_de_umbral")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/temperatura · 15 °C (mínimo efectivo 18 °C)")

    def test_post_f_una_lectura_dentro_del_umbral_no_genera_alertas(self):
        """Flujo principal, pasos 4 y 5: válida, reciente y dentro del umbral: ninguna alerta."""
        self.con_umbral()
        self.temperatura("21")
        self.assertFalse(Alerta.objects.exists())

    def test_post_f_una_segunda_lectura_fuera_no_genera_otra_alerta(self):
        """Garantía: una alerta activa por sensor y tipo."""
        self.con_umbral()
        self.temperatura("26")
        self.temperatura("27", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)

    def test_regla_histeresis_la_alerta_sale_apenas_pasa_el_maximo(self):
        """Regla «Histéresis»: una alerta de umbral se genera apenas la lectura sale del límite (24,01 con máximo 24)."""
        self.con_umbral()
        self.temperatura("24")
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        self.temperatura("24.01", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)

    def test_regla_histeresis_entre_el_maximo_y_el_maximo_menos_h_sigue_activa_y_a_mas_de_h_se_resuelve(self):
        """Extensión 5b: dentro del umbral, la alerta sigue activa hasta quedar a más de la histéresis (1 °C) del límite: 23,5 sigue; 22,9 la resuelve."""
        self.con_umbral()
        self.temperatura("25")
        self.temperatura("23.5", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)
        self.temperatura("22.9", medida_en=(AHORA - timedelta(seconds=10)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        self.assertEqual(self.alertas("iot_fuera_de_umbral", "resuelta").count(), 1)

    def test_regla_histeresis_en_el_limite_inferior_es_simetrica(self):
        """La histéresis vale en cada límite: sale con 17,9; sigue con 18,5; se resuelve con 19,1."""
        self.con_umbral()
        self.temperatura("17.9")
        self.temperatura("18.5", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)
        self.temperatura("19.1", medida_en=(AHORA - timedelta(seconds=10)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_regla_histeresis_con_un_umbral_angosto_usa_la_mitad_del_ancho(self):
        """D-75, punto 2: con un umbral de 23 a 24 (más angosto que dos histéresis) se usa `min(1, 0,5)`: la alerta se resuelve con 23,5 y no antes."""
        self.con_umbral(variedad_con_semilla(nombre="Crespa"), variedad_con_semilla(nombre="Lisa", temp_ambiente_min="23", temp_ambiente_max="30"))
        self.temperatura("25")
        self.temperatura("23.9", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)
        self.temperatura("23.5", medida_en=(AHORA - timedelta(seconds=10)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_regla_histeresis_con_un_umbral_de_un_solo_valor_se_resuelve_con_ese_valor(self):
        """D-75, punto 2: variedades que se tocan en un extremo (umbral 24 a 24): la histéresis es 0 y la alerta se resuelve con una lectura igual a ese valor."""
        self.con_umbral(variedad_con_semilla(nombre="Crespa"), variedad_con_semilla(nombre="Lisa", temp_ambiente_min="24", temp_ambiente_max="30"))
        self.temperatura("25")
        self.temperatura("24", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_d75_3_una_variable_del_umbral_vacia_no_se_compara(self):
        """D-75, punto 3: variedades presentes que no se superponen en la temperatura (18-20 y 22-24): esa variable no se compara, aunque la lectura sea 30."""
        self.con_umbral(
            variedad_con_semilla(nombre="Crespa", temp_ambiente_min="18", temp_ambiente_max="20"),
            variedad_con_semilla(nombre="Lisa", temp_ambiente_min="22", temp_ambiente_max="24"),
        )
        self.temperatura("30")
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_d75_4_sin_umbral_se_resuelve_la_alerta_activa(self):
        """D-75, punto 4: la alerta activa «fuera de umbral» se resuelve con la próxima lectura válida y reciente cuando el invernadero se queda sin umbral."""
        self.con_umbral()
        self.temperatura("26")
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)
        self.enterContext(variedades_presentes_de_prueba())  # ya no hay variedades presentes
        self.temperatura("26", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_ext_5c_sin_umbral_efectivo_no_se_compara_ni_se_evalua(self):
        """Extensión 5c: sin variedades presentes no hay umbral: la lectura se guarda pero no se compara ni evalúa reglas."""
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            resultado = self.temperatura("40")
        self.assertEqual(resultado.resultado, "aceptada")
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        reglas.assert_not_called()

    def test_ext_5a_una_lectura_comparada_evalua_las_reglas_de_actuacion(self):
        """Paso 10 de «Una lectura»: la lectura que llegó hasta acá (válida, reciente, sensor activo, comparada) llama a `evaluar_reglas_de_la_lectura` (IOT-06)."""
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.temperatura("21")
        reglas.assert_called_once()
        contexto, sensor, telemetria, ahora = reglas.call_args.args  # IOT-06 suma ``ahora``: los servicios no leen la hora
        self.assertEqual(ahora, AHORA)
        self.assertEqual((sensor.pk, telemetria.pk), (self.temp.pk, Telemetria.objects.get().pk))

    def test_ext_6_evaluar_reglas_de_la_lectura_no_toca_las_reglas_dadas_de_baja(self):
        """«Reparto» (completado en IOT-06; antes quedaba sin hacer nada): solo se evalúan las reglas ACTIVAS del sensor; una dada de baja no se toca y no se emite nada."""
        regla = fabricas.regla(self.temp, fabricas.actuador(self.sistema, identificador="norte/vent"), estado_regla="inactiva")
        self.con_umbral()
        contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        telemetria = fabricas.telemetria(self.temp, 40)
        self.assertEqual(lecturas.evaluar_reglas_de_la_lectura(contexto, self.temp, telemetria, AHORA), [])
        regla.refresh_from_db()
        self.assertEqual((regla.ultima_evaluacion, regla.contador_confirmacion), ("sin_evaluar", 0))

    # ---- humedad y luz ----

    def test_post_f_la_humedad_se_compara_con_su_rango_y_su_histeresis(self):
        """Humedad: umbral 60 a 80 % HR e histéresis 3: 85 genera la alerta con «% HR»; 79 sigue; 76 la resuelve."""
        humedad = fabricas.sensor(self.sistema, "norte/sectorA/humedad", "humedad", valor_calibracion_min=0, valor_calibracion_max=100)
        self.con_umbral()
        self.registrar("norte/sectorA/humedad", Decimal("85"))
        [alerta] = self.alertas("iot_fuera_de_umbral")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/humedad · 85 % HR (máximo efectivo 80 % HR)")
        self.registrar("norte/sectorA/humedad", Decimal("79"), medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)
        self.registrar("norte/sectorA/humedad", Decimal("76"), medida_en=(AHORA - timedelta(seconds=10)).isoformat())
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        self.assertEqual(humedad.telemetrias.count(), 3)

    def test_post_f_la_luz_se_compara_en_lux_con_punto_de_miles(self):
        """Luz: umbral 200 a 400 lux; 32.000 lux genera la alerta con el valor escrito con punto de miles y la unidad."""
        fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000)
        self.con_umbral()
        self.registrar("norte/sectorA/luz", Decimal("32000"))
        [alerta] = self.alertas("iot_fuera_de_umbral")
        self.assertEqual(alerta.descripcion_alerta, "norte/sectorA/luz · 32.000 lux (máximo efectivo 400 lux)")

    def test_ext_5e_una_lectura_de_luz_fuera_del_horario_no_se_compara_pero_se_guarda(self):
        """Extensión 5e: luz fuera del horario de luz (8 a 18 h, hora local): sin comparar ni reglas, y la lectura sí queda guardada (cuenta para el fotoperíodo)."""
        luz = fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000)
        self.con_umbral()
        de_noche = datetime(2026, 11, 21, 3, 0, 0, tzinfo=timezone.utc)  # 00:00 en Argentina
        resultado = self.registrar("norte/sectorA/luz", Decimal("32000"), medida_en=de_noche.isoformat(), ahora=de_noche + timedelta(seconds=30))
        self.assertEqual(resultado.resultado, "aceptada")
        self.assertEqual(luz.telemetrias.count(), 1)
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())

    def test_ext_5e_la_luz_dentro_del_horario_si_se_compara_y_el_limite_de_las_18_ya_no(self):
        """Horario [8, 18): a las 17:59 local se compara; a las 18:00 ya no."""
        fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000)
        self.con_umbral()
        a_las_18 = datetime(2026, 11, 21, 21, 0, 0, tzinfo=timezone.utc)  # 18:00 en Argentina
        self.registrar("norte/sectorA/luz", Decimal("32000"), medida_en=a_las_18.isoformat(), ahora=a_las_18 + timedelta(seconds=30))
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        a_las_1759 = a_las_18 - timedelta(minutes=1)
        self.registrar("norte/sectorA/luz", Decimal("32000"), medida_en=a_las_1759.isoformat(), ahora=a_las_1759 + timedelta(seconds=30))
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)

    # ---- extensión 5d y D-75 punto 7: sector fuera de servicio ----

    def test_ext_5d_un_sensor_en_un_sector_fuera_de_servicio_no_compara_la_temperatura(self):
        """Extensión 5d y D-75, punto 7: la temperatura ambiente de un sensor de un sector fuera de servicio no se compara ni evalúa reglas."""
        sector = crear_sector(self.norte, "Sector A", "germinacion", 50, estado="fuera_de_servicio")
        fabricas.sensor(self.sistema, "norte/sectorB/temperatura", sector=sector)
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.registrar("norte/sectorB/temperatura", Decimal("40"))
        self.assertFalse(self.alertas("iot_fuera_de_umbral").exists())
        reglas.assert_not_called()

    def test_ext_5d_en_un_sector_fuera_de_servicio_el_nivel_bajo_y_la_lectura_invalida_si_generan_alertas(self):
        """D-75, punto 7: la temperatura y el nivel de la solución son del tanque, no del ambiente (el nivel bajo es crítico), y «lectura inválida» (paso 4,
        anterior a 5d) es una falla del equipo: las dos se generan igual."""
        sector = crear_sector(self.norte, "Sector A", "germinacion", 50, estado="fuera_de_servicio")
        fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion", sector=sector)
        fabricas.sensor(self.sistema, "norte/sectorB/temperatura", sector=sector)
        self.registrar("norte/tanque1/nivel", "bajo")
        self.registrar("norte/sectorB/temperatura", Decimal("999"))
        self.assertEqual(self.alertas("iot_nivel_solucion_bajo").count(), 1)
        self.assertEqual(self.alertas("iot_lectura_invalida").count(), 1)

    # ---- extensión 5f: temperatura de la solución ----

    def test_ext_5f_la_temperatura_de_la_solucion_se_compara_con_el_rango_del_sistema(self):
        """Extensión 5f: con el rango 18 a 24 °C del sistema, 27 genera «solución fuera de rango» con origen en la telemetría; se resuelve a más de la histéresis (1 °C)."""
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("18.0"), Decimal("24.0")
        self.sistema.save()
        fabricas.sensor(self.sistema, "norte/tanque1/temp-solucion", "temperatura_solucion", valor_calibracion_min=0, valor_calibracion_max=50)
        self.registrar("norte/tanque1/temp-solucion", Decimal("27"))
        [alerta] = self.alertas("iot_solucion_fuera_de_rango")
        self.assertIsNotNone(AlertaIot.objects.get(alerta=alerta).telemetria_id)
        self.assertEqual(alerta.descripcion_alerta, "norte/tanque1/temp-solucion · 27 °C (máximo de la solución 24 °C)")
        self.registrar("norte/tanque1/temp-solucion", Decimal("23.5"), medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual(self.alertas("iot_solucion_fuera_de_rango").count(), 1)
        self.registrar("norte/tanque1/temp-solucion", Decimal("22.9"), medida_en=(AHORA - timedelta(seconds=10)).isoformat())
        self.assertFalse(self.alertas("iot_solucion_fuera_de_rango").exists())

    def test_ext_5f_el_minimo_de_la_solucion_dice_minimo_de_la_solucion(self):
        """El texto con el límite inferior: «(mínimo de la solución 18 °C)»."""
        self.sistema.temp_solucion_min, self.sistema.temp_solucion_max = Decimal("18.0"), Decimal("24.0")
        self.sistema.save()
        fabricas.sensor(self.sistema, "norte/tanque1/temp-solucion", "temperatura_solucion", valor_calibracion_min=0, valor_calibracion_max=50)
        self.registrar("norte/tanque1/temp-solucion", Decimal("12.5"))
        [alerta] = self.alertas("iot_solucion_fuera_de_rango")
        self.assertEqual(alerta.descripcion_alerta, "norte/tanque1/temp-solucion · 12,5 °C (mínimo de la solución 18 °C)")

    def test_ext_5f_sin_rango_en_el_sistema_no_se_compara_y_no_evalua_reglas(self):
        """Extensión 5f: sin rango (`temp_solucion_min` nulo) no la compara; y la temperatura de la solución no admite reglas."""
        fabricas.sensor(self.sistema, "norte/tanque1/temp-solucion", "temperatura_solucion", valor_calibracion_min=0, valor_calibracion_max=50)
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.registrar("norte/tanque1/temp-solucion", Decimal("45"))
        self.assertFalse(self.alertas("iot_solucion_fuera_de_rango").exists())
        reglas.assert_not_called()

    # ---- extensión 5g y 4c: nivel de la solución ----

    def test_ext_5g_el_nivel_bajo_genera_la_alerta_critica_y_normal_la_resuelve(self):
        """Extensión 5g y postcondición h: «bajo» genera «nivel de solución bajo» (crítica, origen en la telemetría, sin correo todavía); «normal» la resuelve."""
        fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        self.registrar("norte/tanque1/nivel", "bajo")
        [alerta] = self.alertas("iot_nivel_solucion_bajo")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((alerta.nivel_severidad, vinculo.correo_enviado_en, vinculo.intentos_correo), ("critica", None, 0))
        self.assertIsNotNone(vinculo.telemetria_id)
        self.assertEqual(alerta.descripcion_alerta, "norte/tanque1/nivel · informa «bajo»")
        self.registrar("norte/tanque1/nivel", "normal", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertFalse(self.alertas("iot_nivel_solucion_bajo").exists())

    def test_ext_5g_el_nivel_no_evalua_reglas(self):
        """Extensión 5g: el nivel de la solución no admite reglas."""
        fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.registrar("norte/tanque1/nivel", "bajo")
        reglas.assert_not_called()

    def test_ext_4c_un_valor_de_nivel_que_no_es_normal_ni_bajo_se_rechaza_valor_invalido(self):
        """Extensión 4c: el nivel solo admite «normal» o «bajo»; otro texto o un número: `valor_invalido`, sin guardar nada."""
        nivel = fabricas.sensor(self.sistema, "norte/tanque1/nivel", "nivel_solucion")
        for valor in ("medio", 3, Decimal("1.5"), None, True):
            with self.subTest(valor=valor):
                resultado = self.registrar("norte/tanque1/nivel", valor)
                self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "valor_invalido"))
                self.assertEqual(resultado.detalle, "El nivel de la solución solo admite «normal» o «bajo».")
        self.assertFalse(nivel.telemetrias.exists())

    def test_d74_7_un_valor_que_no_es_un_numero_json_se_rechaza_valor_invalido(self):
        """D-74, punto 7: «71» (texto), `true`, `null` o una lista no son números: `valor_invalido` con «El valor tiene que ser un número.»."""
        for valor in ("71", True, None, [1], {"a": 1}):
            with self.subTest(valor=valor):
                resultado = self.registrar("norte/sectorA/temperatura", valor)
                self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "valor_invalido"))
                self.assertEqual(resultado.detalle, "El valor tiene que ser un número.")
        self.assertFalse(Telemetria.objects.exists())

    def test_d74_7_un_valor_de_mas_de_9999999_99_se_rechaza(self):
        """D-74, punto 7: hasta 9.999.999,99 en valor absoluto; 9.999.999,99 entra y 10.000.000 no (con su texto)."""
        self.registrar("norte/sectorA/temperatura", Decimal("9999999.99"))
        resultado = self.registrar("norte/sectorA/temperatura", Decimal("-10000000"), medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "valor_invalido"))
        self.assertEqual(resultado.detalle, "El valor pasa del máximo admitido (9.999.999,99).")
        self.assertEqual(Telemetria.objects.count(), 1)

    # ---- extensiones 3d, 3e y 3f: fechas ----

    def test_ext_3d_una_fecha_de_mas_de_5_minutos_adelantada_se_rechaza_fecha_futura(self):
        """Extensión 3d: más de 5 minutos posterior a la hora de InfoPonia: `fecha_futura`, con el texto enviado; justo 5 minutos todavía se acepta."""
        futura = (AHORA + timedelta(minutes=5, seconds=1)).isoformat()
        resultado = self.temperatura("24", medida_en=futura)
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "fecha_futura"))
        self.assertEqual(resultado.detalle, f"La fecha {futura} es más de 5 minutos posterior a la hora de InfoPonia.")
        self.assertFalse(Telemetria.objects.exists())
        self.assertEqual(self.temperatura("24", medida_en=(AHORA + timedelta(minutes=5)).isoformat()).resultado, "aceptada")

    def test_d74_5_una_fecha_sin_zona_o_mal_escrita_se_rechaza_fecha_invalida(self):
        """D-74, punto 5: sin zona horaria, mal escrita o que no es texto: `fecha_invalida`, sin reemplazarla por la hora de recepción."""
        casos = {
            "2026-11-21T14:04:30": "«2026-11-21T14:04:30» no es una fecha ISO 8601 con zona horaria.",
            "ayer": "«ayer» no es una fecha ISO 8601 con zona horaria.",
            "": "«» no es una fecha ISO 8601 con zona horaria.",
            1732212270: "La fecha tiene que ser un texto ISO 8601 con zona horaria.",
            True: "La fecha tiene que ser un texto ISO 8601 con zona horaria.",
        }
        for medida_en, detalle in casos.items():
            with self.subTest(medida_en=medida_en):
                resultado = self.temperatura("24", medida_en=medida_en)
                self.assertEqual((resultado.resultado, resultado.motivo, resultado.detalle), ("rechazada", "fecha_invalida", detalle))
        self.assertFalse(Telemetria.objects.exists())

    def test_d74_5_se_aceptan_la_z_y_las_fracciones_de_segundo(self):
        """Mensajes.md, sección 0: `2026-11-21T17:03:00Z` y las fracciones de segundo son válidas."""
        self.assertEqual(self.temperatura("24", medida_en="2026-11-21T17:03:00Z").resultado, "aceptada")
        self.assertEqual(self.temperatura("24", medida_en="2026-11-21T14:04:00.250-03:00").resultado, "aceptada")
        self.assertEqual(Telemetria.objects.count(), 2)

    def test_ext_3e_sin_fecha_de_medicion_se_usa_la_de_recepcion(self):
        """Extensión 3e: la lectura sin `medida_en` usa la hora en que se recibió (`ahora`), y la lectura no es atrasada."""
        resultado = self.temperatura("24", medida_en=None)
        self.assertEqual(Telemetria.objects.get().medida_en, AHORA)
        self.assertFalse(resultado.atrasada)

    def test_ext_3f_una_lectura_atrasada_se_guarda_y_lo_dice_pero_no_genera_alertas(self):
        """Extensión 3f: medida hace más que la antigüedad máxima (5 minutos): se guarda con su marca, `atrasada` verdadero y ninguna alerta de lectura inválida,
        de umbral, de rango ni de nivel."""
        self.con_umbral()
        vieja = (AHORA - timedelta(minutes=15)).isoformat()
        inv = self.temperatura("999", medida_en=vieja)
        fuera = self.temperatura("30", medida_en=(AHORA - timedelta(minutes=14)).isoformat())
        self.assertEqual((inv.resultado, inv.valida, inv.atrasada), ("aceptada", False, True))
        self.assertEqual((fuera.resultado, fuera.valida, fuera.atrasada), ("aceptada", True, True))
        self.assertEqual(Telemetria.objects.count(), 2)
        self.assertFalse(Alerta.objects.exists())

    def test_ext_3f_una_lectura_exactamente_en_el_limite_de_antiguedad_no_es_atrasada(self):
        """«Se midió hace más que» la antigüedad máxima: justo 5 minutos no es atrasada; 5 minutos y un segundo sí."""
        self.assertFalse(self.temperatura("24", medida_en=(AHORA - timedelta(minutes=5)).isoformat()).atrasada)
        self.assertTrue(self.temperatura("24", medida_en=(AHORA - timedelta(minutes=5, seconds=1)).isoformat()).atrasada)

    def test_ext_3f_una_lectura_atrasada_resuelve_sin_actividad_pero_no_las_otras_alertas(self):
        """Extensión 3f: resuelve «dispositivo sin actividad» (el sensor habló) y no resuelve «lectura inválida» ni «fuera de umbral» activas."""
        self.con_umbral()
        self.temperatura("30")  # fuera de umbral (esta lectura reciente no es la que se prueba)
        sin_actividad = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_dispositivo_sin_actividad", f"hw:{self.temp.pk}", "sin actividad", hardware=self.temp
        ).alerta
        invalida = alertas_iot.asegurar_alerta_iot(
            self.norte.pk, self.sistema, "iot_lectura_invalida", f"hw:{self.temp.pk}", "inválida", hardware=self.temp
        ).alerta
        self.temperatura("21", medida_en=(AHORA - timedelta(minutes=20)).isoformat())
        sin_actividad.refresh_from_db()
        invalida.refresh_from_db()
        self.assertEqual((sin_actividad.estado_alerta, invalida.estado_alerta), ("resuelta", "activa"))
        self.assertEqual(self.alertas("iot_fuera_de_umbral").count(), 1)

    def test_ext_3f_una_lectura_atrasada_no_evalua_reglas(self):
        """Garantía: una lectura atrasada nunca dispara reglas."""
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            self.temperatura("21", medida_en=(AHORA - timedelta(minutes=20)).isoformat())
        reglas.assert_not_called()

    # ---- extensión 3c: sensor fuera de servicio ----

    def test_ext_3c_un_sensor_fuera_de_servicio_registra_la_lectura_pero_no_la_compara(self):
        """Extensión 3c: la lectura se registra, pero no se compara ni evalúa reglas, ni genera «lectura inválida»: el sensor tiene una falla informada."""
        self.temp.estado_hardware = "fuera_de_servicio"
        self.temp.save(update_fields=["estado_hardware"])
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            resultado = self.temperatura("30")
            self.temperatura("999", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        self.assertEqual((resultado.resultado, resultado.valida), ("aceptada", True))
        self.assertEqual(Telemetria.objects.count(), 2)
        self.assertFalse(Alerta.objects.exists())
        reglas.assert_not_called()

    # ---- extensiones 3a y 3b y postcondición t: identificadores ----

    def test_ext_3a_un_identificador_desconocido_se_rechaza_y_genera_la_alerta_no_registrado(self):
        """Extensión 3a y postcondición t: rechaza `equipo_no_registrado` y genera «dispositivo no registrado» (informativa), sin hardware ni telemetría, con el
        sistema, clave `id:<minúsculas>` y el valor recibido en la descripción."""
        resultado = self.registrar("Norte/SectorB/CO2", Decimal("450"))
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "equipo_no_registrado"))
        self.assertEqual(resultado.detalle, "«Norte/SectorB/CO2» no es un equipo registrado de este sistema IoT.")
        [alerta] = self.alertas("iot_dispositivo_no_registrado")
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual(
            (alerta.clave_estado, alerta.nivel_severidad, vinculo.sistema, vinculo.hardware_id, vinculo.telemetria_id),
            ("id:norte/sectorb/co2", "informativa", self.sistema, None, None),
        )
        self.assertEqual(vinculo.ultimo_mensaje_en, AHORA)
        self.assertEqual(
            alerta.descripcion_alerta, "El nodo envió una lectura de «Norte/SectorB/CO2» (450), que no está registrado."
        )
        self.assertFalse(Telemetria.objects.exists())

    def test_ext_3a_dos_rechazos_del_mismo_identificador_no_crean_dos_alertas_y_el_segundo_actualiza_el_ultimo_mensaje(self):
        """D-76, punto 3: una sola alerta por identificador; cada rechazo posterior actualiza `AlertaIot.ultimo_mensaje_en` (con ella la revisión la resuelve
        sin mensajes recientes), también con otras mayúsculas."""
        self.registrar("norte/sectorB/co2", Decimal("450"))
        mas_tarde = AHORA + timedelta(minutes=2)
        self.registrar("NORTE/sectorB/CO2", Decimal("460"), ahora=mas_tarde, medida_en=mas_tarde.isoformat())
        self.assertEqual(self.alertas("iot_dispositivo_no_registrado").count(), 1)
        self.assertEqual(AlertaIot.objects.get().ultimo_mensaje_en, mas_tarde)

    def test_ext_3a_un_equipo_dado_de_baja_se_rechaza_equipo_dado_de_baja_con_la_misma_alerta(self):
        """Extensión 3a: el identificador de un equipo dado de baja del sistema (y de ninguno vigente): `equipo_dado_de_baja`, y la alerta «no registrado» con
        la clave `id:<minúsculas>`; el vínculo con el equipo no se guarda."""
        fabricas.sensor(self.sistema, "norte/sectorA/temp-vieja", estado="inactivo")
        resultado = self.registrar("norte/sectorA/temp-vieja", Decimal("22.1"))
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "equipo_dado_de_baja"))
        self.assertEqual(resultado.detalle, "«norte/sectorA/temp-vieja» era de un equipo dado de baja de este sistema IoT.")
        [alerta] = self.alertas("iot_dispositivo_no_registrado")
        self.assertEqual(alerta.clave_estado, "id:norte/sectorA/temp-vieja".lower())
        self.assertIsNone(AlertaIot.objects.get(alerta=alerta).hardware_id)

    def test_ext_3a_un_reemplazo_con_el_identificador_de_uno_dado_de_baja_se_acepta(self):
        """Regla de MD-100: un reemplazo puede reusar el identificador de uno dado de baja; las lecturas van al vigente."""
        fabricas.sensor(self.sistema, "norte/sectorA/temperatura", estado="inactivo")
        resultado = self.temperatura("24")
        self.assertEqual(resultado.resultado, "aceptada")
        self.assertEqual(Telemetria.objects.get().sensor_id, self.temp.pk)

    def test_ext_3a_el_identificador_se_reconoce_sin_distinguir_mayusculas_ni_espacios_del_borde(self):
        """Mensajes.md, sección 0: se compara sin distinguir mayúsculas y sin los espacios del borde."""
        resultado = self.registrar(" NORTE/SECTORA/TEMPERATURA ", Decimal("24"))
        self.assertEqual(resultado.resultado, "aceptada")
        self.assertFalse(self.alertas("iot_dispositivo_no_registrado").exists())

    def test_ext_3a_un_equipo_de_otro_sistema_no_es_de_este(self):
        """Origen de los mensajes: solo sobre los equipos registrados del propio sistema: el sensor de otro sistema es «no registrado»."""
        otro = fabricas.sistema(crear_invernadero("Sur", agronomo=crear_agronomo("ana@infoponia.com")))
        fabricas.sensor(otro, "sur/temperatura")
        resultado = self.registrar("sur/temperatura", Decimal("24"))
        self.assertEqual(resultado.motivo, "equipo_no_registrado")

    def test_ext_3b_una_lectura_de_un_actuador_se_rechaza_no_es_sensor_sin_alertas(self):
        """Extensión 3b: rechaza `no_es_sensor` y deja constancia en el registro técnico; no genera la alerta «no registrado» (el equipo existe)."""
        fabricas.actuador(self.sistema, identificador="norte/sectorA/ventilador")
        resultado = self.registrar("norte/sectorA/ventilador", Decimal("1"))
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "no_es_sensor"))
        self.assertEqual(resultado.detalle, "«norte/sectorA/ventilador» es un actuador: las lecturas son solo de sensores.")
        self.assertFalse(Alerta.objects.exists())

    # ---- D-74 punto 6: duplicadas ----

    def test_d74_6_una_lectura_repetida_es_duplicada_y_no_toca_nada(self):
        """D-74, punto 6: mismo sensor y misma `medida_en`: `duplicada`; no se procesa de nuevo (ni alertas, ni reglas, ni el último mensaje del equipo)."""
        self.con_umbral()
        self.temperatura("26")
        self.temp.refresh_from_db()
        antes = self.temp.ultimo_mensaje_en
        con_alerta = Alerta.objects.count()
        with mock.patch("iot.servicios.lecturas.evaluar_reglas_de_la_lectura") as reglas:
            resultado = self.temperatura("21", ahora=AHORA + timedelta(seconds=10))
        self.assertEqual((resultado.resultado, resultado.valida, resultado.atrasada), ("duplicada", None, None))
        self.assertEqual(Telemetria.objects.count(), 1)
        self.assertEqual(Telemetria.objects.get().valor_medido, Decimal("26.00"))
        self.temp.refresh_from_db()
        self.assertEqual(self.temp.ultimo_mensaje_en, antes)
        self.assertEqual(Alerta.objects.count(), con_alerta)
        reglas.assert_not_called()

    def test_d74_6_si_la_base_rechaza_la_repetida_tambien_es_duplicada_nunca_un_error(self):
        """D-74, punto 6: aunque la verificación previa no la vea (mensajes simultáneos), el índice único de la base respalda y su `IntegrityError` es `duplicada`."""
        self.temperatura("24")
        with mock.patch("iot.servicios.lecturas._ya_existe_la_lectura", return_value=False):
            resultado = self.temperatura("24")
        self.assertEqual(resultado.resultado, "duplicada")
        self.assertEqual(Telemetria.objects.count(), 1)

    # ---- extensión *a: sistema desconectado durante el pedido ----

    def test_ext_astar_un_sistema_que_se_desconecto_rechaza_la_lectura_sin_escribir(self):
        """Extensión *a y respuestas_y_errores.md, sección 4: si el sistema se desconectó mientras se procesaba el pedido: `sistema_desconectado`, sin escribir."""
        contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        self.sistema.estado_sistema = "desconectado"
        self.sistema.save(update_fields=["estado_sistema"])
        resultado = self.registrar("norte/sectorA/temperatura", Decimal("24"), contexto=contexto)
        self.assertEqual((resultado.resultado, resultado.motivo), ("rechazada", "sistema_desconectado"))
        self.assertEqual(resultado.detalle, "El sistema IoT se desconectó mientras se procesaba el pedido.")
        self.assertFalse(Telemetria.objects.exists())

    # ---- contexto del mensaje ----

    def test_regla_el_contexto_se_calcula_una_vez_por_pedido(self):
        """«Una lectura»: `contexto_del_mensaje` trae los parámetros y el umbral efectivo UNA vez por pedido: dos lecturas con el mismo contexto no vuelven a pedirlo."""
        self.con_umbral()
        with mock.patch("iot.servicios.lecturas.umbral_efectivo", wraps=lecturas.umbral_efectivo) as umbral:
            contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
            self.temperatura("21", contexto=contexto)
            self.temperatura("22", contexto=contexto, medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        umbral.assert_called_once()

    # ---- postcondición z: auditoría ----

    def test_post_z_una_lectura_que_no_cambia_nada_no_se_audita(self):
        """«Auditoría»: las lecturas que no generan ni resuelven nada no se auditan una por una."""
        self.con_umbral()
        self.temperatura("21")
        self.assertEqual(self.auditorias().count(), 0)

    def test_post_z_una_lectura_que_genera_una_alerta_se_audita_con_el_formato_de_d36(self):
        """Postcondición z y D-36: un registro con actor `None`, `datos` (origen, sistema como referencia, mensaje `lectura`, identificador, alertas) y como
        afectados el sensor y la alerta; sin la clave `cambios` (no cambió ningún dato del equipo). Nunca el token."""
        self.con_umbral()
        self.temperatura("26")
        [registro] = self.auditorias()
        [alerta] = self.alertas("iot_fuera_de_umbral")
        self.assertIsNone(registro.usuario)
        self.assertEqual(set(registro.detalle), {"datos"})
        self.assertEqual(
            registro.detalle["datos"],
            {
                "origen": "nodo_central",
                "sistema": {"id": self.sistema.pk, "texto": str(self.sistema)},
                "mensaje": "lectura",
                "identificador": "norte/sectorA/temperatura",
                "alertas_generadas": [{"id": alerta.pk, "texto": str(alerta)}],
                "alertas_resueltas": [],
            },
        )
        self.assertEqual({(a["modelo"], a["id"]) for a in registro.afectados}, {("iot.sensor", self.temp.pk), ("maestros.alerta", alerta.pk)})

    def test_post_z_una_lectura_que_resuelve_una_alerta_se_audita(self):
        """Postcondición z: resolver una alerta también es un cambio que se audita."""
        self.con_umbral()
        self.temperatura("26")
        self.temperatura("21", medida_en=(AHORA - timedelta(seconds=20)).isoformat())
        ultimo = self.auditorias().order_by("-id").first()
        self.assertEqual(self.auditorias().count(), 2)
        self.assertEqual(len(ultimo.detalle["datos"]["alertas_resueltas"]), 1)
        self.assertEqual(ultimo.detalle["datos"]["alertas_generadas"], [])

    def test_post_z_un_rechazo_que_solo_actualiza_el_ultimo_mensaje_no_se_audita_pero_el_que_genera_la_alerta_si(self):
        """«Auditoría»: solo se audita si cambió algo además del último mensaje: el primer rechazo de un identificador (alerta nueva) sí; los siguientes, no."""
        self.registrar("norte/sectorB/co2", Decimal("450"))
        self.registrar("norte/sectorB/co2", Decimal("451"), ahora=AHORA + timedelta(minutes=1))
        [registro] = self.auditorias()
        self.assertEqual(registro.detalle["datos"]["identificador"], "norte/sectorB/co2")
        self.assertEqual(len(registro.detalle["datos"]["alertas_generadas"]), 1)

    # ---- tiene_lecturas (la regla 3 de IOT-MOD-HDW la usa) ----

    def test_regla_3_de_iot_mod_hdw_tiene_lecturas_con_lecturas_reales(self):
        """«Lo que completa en Hardware»: `tiene_lecturas(sensor)` es verdadero cuando la API guardó alguna lectura del sensor."""
        from iot.servicios.hardware import tiene_lecturas

        self.assertFalse(tiene_lecturas(self.temp))
        self.temperatura("24")
        self.assertTrue(tiene_lecturas(self.temp))
        self.assertTrue(lecturas.tiene_lecturas(self.temp))
