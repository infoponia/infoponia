# Pruebas de concurrencia de la revisión periódica (IOT-04, paso 9; docs/casos_de_uso/iot/entregar_informacion.md, «La revisión periódica», «Bloqueos y concurrencia»; D-71 punto 2 y D-76;
# docs/patrones/bloqueos.md). Dos hilos, dos conexiones, el orden fijado con ``primera`` y ``detener_antes_de`` (core/tests/concurrencia.py). ``TransactionTestCase``: su ``flush`` vacía
# todas las tablas, así que cada prueba vuelve a asegurar los datos en ``setUp``.
#
# Orden de bloqueos de la revisión y de la API (docs/api/alertas.md, sección 3): invernadero → sistema → equipos (nodo y sensores), en orden de id. Cada prueba con barrera se detiene a ``primera`` en
# un punto donde el orden se nota, y FALLA si la revisión toma los bloqueos en otro orden (se verificó invirtiéndolo: ver el «Cierre» de IOT-04):
#   - lectura primera, detenida ANTES de tomar el sensor (``_equipo_de``): con la revisión tomando el sensor antes que el invernadero, las dos se esperan entre sí (deadlock);
#   - revisión primera, detenida ANTES de tomar nodo y sensores (``_bloquear_equipos``): con el orden invertido ya no tiene tomado nada en ese punto y la lectura la pasa por encima;
#   - dos revisiones: la segunda espera a la primera y encuentra todo hecho; con el orden invertido, la que se detiene no tiene nada tomado y la otra hace el trabajo.
# El correo no depende de un bloqueo de filas (hay que enviarlo fuera de la transacción, D-14): se reserva con un ``UPDATE`` condicional; ver ``enviar_correos_pendientes``.

import importlib
from datetime import datetime, timedelta
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.db import transaction
from django.test import TransactionTestCase, override_settings, tag

from core.models import RegistroAuditoria
from core.tests.concurrencia import correr_a_la_vez, separar
from core.tests.fabricas import crear_gerente
from inventario.tests.fabricas import perezoso
from iot.api.traduccion import LecturaRecibida
from iot.models import AlertaIot, FotoperiodoDiario, Hardware, NodoCentral, ResumenHorario, Telemetria
from iot.tests import fabricas
from maestros.models import Alerta
from maestros.tests.fabricas import asegurar_datos_de_maestros, crear_agronomo, crear_invernadero_con_geografia_propia

lecturas = perezoso("iot.servicios.lecturas")
revision = perezoso("iot.servicios.revision")
alertas_iot = perezoso("iot.servicios.alertas_iot")
modulo_lecturas = importlib.import_module("iot.servicios.lecturas")  # los reales: un parche sobre el proxy no llega al módulo
modulo_revision = importlib.import_module("iot.servicios.revision")
modulo_correo = importlib.import_module("core.correo")

LOCAL = ZoneInfo("America/Argentina/Buenos_Aires")
AHORA = datetime(2026, 11, 23, 12, 0, tzinfo=LOCAL)
SIN_ACTIVIDAD = "iot_dispositivo_sin_actividad"


@tag("concurrencia")
class RevisionConcurrenciaTests(fabricas.ConCatalogoIot, TransactionTestCase):
    """Una revisión y una lectura del nodo a la vez, dos revisiones a la vez y dos corridas del correo a la vez."""

    def setUp(self):
        fabricas.asegurar_datos_de_iot()
        asegurar_datos_de_maestros()
        self.enterContext(fabricas.con_iot_registrado())
        crear_gerente()
        self.laura = crear_agronomo("laura@infoponia.com")
        self.norte = crear_invernadero_con_geografia_propia("Norte", agronomo=self.laura)
        self.sistema = fabricas.sistema(self.norte)
        self.nodo = NodoCentral.objects.get(sistema=self.sistema)
        self.temp = fabricas.sensor(self.sistema, "norte/sectorA/temperatura")
        self.n = 0

    # ---- ayudas ----

    def sin_actividad(self):
        """El sensor lleva 30 minutos sin mensajes: la revisión le generaría «dispositivo sin actividad»."""
        Hardware.objects.filter(pk=self.temp.pk).update(ultimo_mensaje_en=AHORA - timedelta(minutes=30))

    def lectura_del_sensor(self):
        """Una operación para ``correr_a_la_vez``: una lectura válida de la temperatura, con su contexto y su propia transacción (como un pedido del nodo)."""
        contexto = lecturas.contexto_del_mensaje(self.sistema, AHORA)
        medida = (AHORA - timedelta(seconds=30)).isoformat()
        lectura = LecturaRecibida(self.n, "norte/sectorA/temperatura", "norte/sectorA/temperatura", Decimal("22"), medida)
        self.n += 1
        return lambda: lecturas.registrar_lectura(contexto, lectura, AHORA)

    def alertas(self, tipo):
        return Alerta.objects.filter(tipo_alerta=tipo)

    # ---- una revisión y una lectura de la API sobre el mismo sensor ----

    def test_regla_comun_una_lectura_detenida_antes_de_tomar_el_sensor_no_se_cruza_con_la_revision(self):
        """Orden invernadero → sistema → equipo en toda la API y la revisión (docs/api/alertas.md, sección 3): la lectura se detiene con el invernadero y el sistema tomados y SIN el sensor (antes de
        `_equipo_de`); la revisión arranca, espera el invernadero y, cuando la lectura confirma, relee el sensor con su mensaje nuevo: no genera «sin actividad». Nada de deadlock ni de error, y ninguna
        alerta."""
        self.sin_actividad()
        resultados = correr_a_la_vez(
            self.lectura_del_sensor(), lambda: revision.revisar(AHORA), primera="a", detener_antes_de=(modulo_lecturas, "_equipo_de")
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(resultados["a"].resultado, "aceptada")
        self.assertEqual((resultados["b"].sistemas[0].error, resultados["b"].sistemas[0].alertas_generadas), (None, 0))
        self.assertEqual(self.alertas(SIN_ACTIVIDAD).count(), 0)
        self.assertEqual(Hardware.objects.get(pk=self.temp.pk).ultimo_mensaje_en, AHORA)

    def test_regla_comun_una_revision_detenida_antes_de_tomar_los_equipos_hace_que_la_lectura_espere_y_resuelva_su_alerta(self):
        """La revisión se detiene con el invernadero y el sistema tomados y sin el nodo ni los sensores (antes de `_bloquear_equipos`); la lectura arranca y espera el invernadero. La revisión genera
        «sin actividad» y confirma; la lectura sigue, ve la alerta y la resuelve: UNA sola alerta (resuelta), el mensaje del sensor al día y ningún error."""
        self.sin_actividad()
        resultados = correr_a_la_vez(
            lambda: revision.revisar(AHORA), self.lectura_del_sensor(), primera="a", detener_antes_de=(modulo_revision, "_bloquear_equipos")
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual(resultados["a"].sistemas[0].alertas_generadas, 1)
        self.assertEqual(resultados["b"].resultado, "aceptada")
        (alerta,) = self.alertas(SIN_ACTIVIDAD)
        self.assertEqual(alerta.estado_alerta, "resuelta")
        self.assertEqual(AlertaIot.objects.filter(alerta=alerta).count(), 1)
        self.assertEqual(Hardware.objects.get(pk=self.temp.pk).ultimo_mensaje_en, AHORA)

    # ---- dos revisiones a la vez ----

    def armar_trabajo_pendiente(self):
        """Todo lo que una revisión hace: un sensor y un nodo sin actividad (dos alertas), un día entero de lecturas de luz de ayer (24 resúmenes y un fotoperíodo) y lecturas de temperatura."""
        self.sin_actividad()
        NodoCentral.objects.filter(pk=self.nodo.pk).update(ultima_comunicacion=AHORA - timedelta(minutes=10))
        luz = fabricas.sensor(self.sistema, "norte/sectorA/luz", "intensidad_luz", valor_calibracion_min=0, valor_calibracion_max=100000)
        ayer = datetime(2026, 11, 22, tzinfo=LOCAL)
        Telemetria.objects.bulk_create(
            Telemetria(
                sensor=luz, medida_en=ayer + timedelta(minutes=m), valor_medido=Decimal("5000" if 8 * 60 <= m < 18 * 60 else "100"), valida=True, unidad_medida_telemetria="lux"
            )
            for m in range(24 * 60)
        )
        fabricas.telemetria(self.temp, "21", medida_en=AHORA - timedelta(minutes=50))

    def test_regla_comun_dos_revisiones_a_la_vez_no_duplican_alertas_resumenes_ni_fotoperiodos(self):
        """Regla común de «La revisión periódica» (idempotencia) con concurrencia: la primera se detiene con el invernadero y el sistema tomados; la segunda espera. Cuando la primera confirma, la segunda
        relee y encuentra todo hecho: la primera generó las 2 alertas, los resúmenes y el fotoperíodo; la segunda, nada (0 y sin error). Una alerta de cada tipo, un fotoperíodo y un solo registro de
        auditoría."""
        self.armar_trabajo_pendiente()
        resultados = correr_a_la_vez(
            lambda: revision.revisar(AHORA), lambda: revision.revisar(AHORA), primera="a", detener_antes_de=(modulo_revision, "_bloquear_equipos")
        )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        primera, segunda = resultados["a"].sistemas[0], resultados["b"].sistemas[0]
        self.assertEqual((primera.error, primera.alertas_generadas, primera.fotoperiodos), (None, 2, 1))
        self.assertGreater(primera.resumenes, 0)
        self.assertEqual(
            (segunda.error, segunda.alertas_generadas, segunda.alertas_resueltas, segunda.resumenes, segunda.fotoperiodos, segunda.lecturas_borradas), (None, 0, 0, 0, 0, 0)
        )
        self.assertEqual((self.alertas(SIN_ACTIVIDAD).count(), self.alertas("iot_nodo_sin_comunicacion").count()), (1, 1))
        self.assertEqual(FotoperiodoDiario.objects.count(), 1)
        self.assertEqual(ResumenHorario.objects.count(), 25)  # 24 horas de luz de ayer y la hora de la temperatura
        self.assertEqual(RegistroAuditoria.objects.filter(accion="revision_periodica_iot").count(), 1)

    # ---- dos corridas del correo a la vez ----

    @override_settings(CORREO_CONFIGURADO=True)
    def test_regla_correos_dos_revisiones_a_la_vez_mandan_el_correo_de_una_alerta_una_sola_vez(self):
        """DECISIÓN de IOT-04 (reserva antes de enviar), con conexiones reales: la primera corrida reserva la alerta y se detiene justo antes de llamar a `enviar_correo`; la segunda arranca, no encuentra nada
        pendiente y termina. El `mock` de `enviar_correo` cuenta las llamadas: una sola. (Con la marca de «enviado» cargada después de enviar, como en D-76 punto 7, las dos mandarían el mismo correo.)"""
        with transaction.atomic():  # las funciones de alertas bloquean filas: piden una transacción abierta
            alerta = alertas_iot.asegurar_alerta_iot(
                self.norte.pk, self.sistema, "iot_nodo_sin_comunicacion", f"nodo:{self.nodo.pk}", "Nodo de prueba · sin comunicación"
            ).alerta
        with mock.patch("core.correo.enviar_correo", return_value=True) as envios:
            resultados = correr_a_la_vez(
                lambda: revision.enviar_correos_pendientes(AHORA),
                lambda: revision.enviar_correos_pendientes(AHORA),
                primera="a",
                detener_antes_de=(modulo_correo, "enviar_correo"),
            )
        exitos, rechazos, otros = separar(resultados)
        self.assertEqual((len(exitos), len(rechazos), otros), (2, 0, []))
        self.assertEqual((resultados["a"].enviados, resultados["b"].enviados, resultados["b"].fallidos), (1, 0, 0))
        self.assertEqual(envios.call_count, 1)
        vinculo = AlertaIot.objects.get(alerta=alerta)
        self.assertEqual((vinculo.correo_enviado_en, vinculo.intentos_correo), (AHORA, 0))
